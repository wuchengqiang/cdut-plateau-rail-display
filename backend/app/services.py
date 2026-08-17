from __future__ import annotations

import asyncio
import logging
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol


logger = logging.getLogger("polar_rail")
Publish = Callable[[dict[str, Any]], Awaitable[None]]


class MotorProvider(Protocol):
    machine: dict[str, Any]

    async def initialize(self) -> None: ...
    async def move_to(self, position: str) -> bool: ...
    async def home(self) -> bool: ...
    async def stop(self) -> None: ...
    async def get_state(self) -> str: ...
    async def ping(self) -> str: ...
    async def dispose(self) -> None: ...


class MotorProtocolError(RuntimeError):
    """The controller returned an error or did not satisfy the published protocol."""


@dataclass
class SystemState:
    current_scene: int | None = None
    target_scene: int | None = None
    motor_state: str = "idle"
    playback_state: str = "idle"
    carousel_mode: bool = False
    carousel_direction: str = "forward"
    video_id: str | None = None
    error: str | None = None
    last_command: dict[str, str] = field(default_factory=lambda: {"method": "SYSTEM", "path": "/"})

    def payload(self) -> dict[str, Any]:
        return {
            "currentScene": self.current_scene,
            "targetScene": self.target_scene,
            "motorState": self.motor_state,
            "playbackState": self.playback_state,
            "carouselMode": self.carousel_mode,
            "carouselDirection": self.carousel_direction,
            "videoId": self.video_id,
            "error": self.error,
            "lastCommand": self.last_command,
        }


class MockMotorProvider:
    """Development-only motor abstraction. It deliberately sends no real hardware commands."""

    def __init__(self, state: SystemState, machine: dict[str, Any], publish: Publish) -> None:
        self.state, self.machine, self.publish = state, machine, publish
        self.position: str | None = None

    async def initialize(self) -> None:
        self.position = self.machine["homePosition"]
        self.state.motor_state = "arrived"
        await self.publish(self.state.payload())

    async def move_to(self, position: str) -> bool:
        self.state.motor_state = "moving"
        await self.publish(self.state.payload())
        await asyncio.sleep(self.machine["mockMoveDurationMs"] / 1000)
        self.position = position
        self.state.motor_state = "arrived"
        await self.publish(self.state.payload())
        return True

    async def home(self) -> bool:
        return await self.move_to(self.machine["homePosition"])

    async def stop(self) -> None:
        self.state.motor_state = "idle"
        await self.publish(self.state.payload())

    async def get_state(self) -> str:
        return self.state.motor_state

    async def ping(self) -> str:
        return "PONG (mock)"

    async def dispose(self) -> None:
        return None


class NetworkMotorProvider:
    """Common command semantics for the documented TCP/UDP motion protocol."""

    def __init__(self, state: SystemState, machine: dict[str, Any], publish: Publish) -> None:
        self.state, self.machine, self.publish = state, machine, publish
        self.position: str | None = None
        network = machine.get("network", {})
        self.host = str(network.get("host", "")).strip()
        self.port = int(network.get("port", 8080))
        self.shared_key = str(network.get("sharedKey", ""))
        self.command_timeout = int(network.get("commandTimeoutMs", 5000)) / 1000
        self.move_timeout = int(network.get("moveTimeoutMs", 60000)) / 1000

    def _wire_command(self, command: str) -> bytes:
        prefix = f"KEY {self.shared_key};" if self.shared_key else ""
        return f"{prefix}{command}\r\n".encode("ascii")

    def _target_mm(self, position: str) -> float:
        value = self.machine.get("positionsMm", {}).get(position)
        if value is None:
            raise MotorProtocolError(f"未配置点位 {position} 的毫米坐标（config/machine.json -> positionsMm）")
        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise MotorProtocolError(f"点位 {position} 的毫米坐标无效：{value!r}") from error

    @staticmethod
    def _format_mm(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    async def _request(self, command: str, timeout: float | None = None) -> str:
        raise NotImplementedError

    async def ping(self) -> str:
        reply = await self._request("PING")
        if reply.upper() != "PONG":
            raise MotorProtocolError(f"PING 响应异常：{reply}")
        return reply

    async def initialize(self) -> None:
        await self.ping()
        await self.get_state()

    async def move_to(self, position: str) -> bool:
        target_mm = self._target_mm(position)
        self.state.motor_state = "moving"
        self.state.error = None
        await self.publish(self.state.payload())
        reply = await self._request(f"MOVE {self._format_mm(target_mm)}", self.move_timeout)
        if not reply.upper().startswith("OK:MOVE"):
            raise MotorProtocolError(f"MOVE 响应异常：{reply}")
        self.position = position
        self.state.motor_state = "arrived"
        await self.publish(self.state.payload())
        return True

    async def home(self) -> bool:
        # The published protocol has no HOME command. Home is the configured absolute P1 position,
        # never ZERO (ZERO changes the controller's coordinate reference).
        return await self.move_to(self.machine["homePosition"])

    async def stop(self) -> None:
        reply = await self._request("STOP")
        if not reply.upper().startswith("OK:STOP"):
            raise MotorProtocolError(f"STOP 响应异常：{reply}")
        self.state.motor_state = "idle"
        await self.publish(self.state.payload())

    async def get_state(self) -> str:
        reply = await self._request("STATUS")
        if reply.upper().startswith("ERR:"):
            raise MotorProtocolError(reply)
        fields = {key.upper(): value for key, value in re.findall(r"([A-Za-z]+)=([^;\s]+)", reply)}
        alarm = fields.get("ALM", "").upper()
        ready = fields.get("RDY", "").upper()
        if alarm and alarm not in {"0", "OK", "NONE", "FALSE"}:
            self.state.motor_state = "error"
            self.state.error = f"控制器告警：{alarm}"
        elif ready in {"1", "TRUE", "READY", "OK"}:
            self.state.motor_state = "arrived"
        else:
            self.state.motor_state = "idle"
        await self.publish(self.state.payload())
        return self.state.motor_state

    async def dispose(self) -> None:
        return None


class TcpMotorProvider(NetworkMotorProvider):
    """TCP controller implementation with optional protocol WATCH position monitoring."""

    def __init__(self, state: SystemState, machine: dict[str, Any], publish: Publish) -> None:
        super().__init__(state, machine, publish)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._responses: asyncio.Queue[str] = asyncio.Queue()
        self._command_lock = asyncio.Lock()
        self.last_position_mm: float | None = None
        self._closing = False

    async def _connect(self) -> None:
        if self._writer and not self._writer.is_closing():
            return
        if not self.host:
            raise MotorProtocolError("真实硬件未配置 network.host；请先保持 provider=mock 或填写控制器 IP")
        connect_timeout = int(self.machine.get("network", {}).get("connectTimeoutMs", 5000)) / 1000
        self._reader, self._writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), connect_timeout)
        self._reader_task = asyncio.create_task(self._reader_loop(), name="motor-tcp-reader")

    async def _reader_loop(self) -> None:
        assert self._reader
        try:
            while True:
                raw = await self._reader.readline()
                if not raw:
                    raise ConnectionError("控制器已关闭 TCP 连接")
                line = raw.decode("utf-8", errors="replace").strip()
                match = re.fullmatch(r"POS:([+-]?\d+(?:\.\d+)?)mm", line, flags=re.IGNORECASE)
                if match:
                    self.last_position_mm = float(match.group(1))
                    continue
                await self._responses.put(line)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not self._closing:
                logger.error("电机 TCP 连接中断：%s", error)
                self.state.motor_state = "error"
                self.state.error = str(error)
                await self.publish(self.state.payload())

    async def _request(self, command: str, timeout: float | None = None) -> str:
        await self._connect()
        assert self._writer
        async with self._command_lock:
            self._writer.write(self._wire_command(command))
            await self._writer.drain()
            try:
                reply = await asyncio.wait_for(self._responses.get(), timeout or self.command_timeout)
            except TimeoutError as error:
                raise MotorProtocolError(f"控制器命令超时：{command}") from error
            if reply.upper().startswith("ERR:"):
                raise MotorProtocolError(reply)
            return reply

    async def initialize(self) -> None:
        await super().initialize()
        interval = int(self.machine.get("network", {}).get("watchIntervalMs", 100))
        if interval > 0:
            reply = await self._request(f"WATCH {max(10, interval)}")
            if not reply.upper().startswith("OK:WATCH"):
                raise MotorProtocolError(f"WATCH 响应异常：{reply}")

    async def dispose(self) -> None:
        self._closing = True
        try:
            if self._writer and not self._writer.is_closing():
                try:
                    await self._request("UNWATCH")
                except Exception:
                    pass
                self._writer.close()
                await self._writer.wait_closed()
        finally:
            if self._reader_task:
                self._reader_task.cancel()
            self._reader = None
            self._writer = None


class UdpMotorProvider(NetworkMotorProvider):
    """UDP implementation of the same controller commands. WATCH is TCP-only by protocol."""

    def __init__(self, state: SystemState, machine: dict[str, Any], publish: Publish) -> None:
        super().__init__(state, machine, publish)
        self._socket: socket.socket | None = None
        self._command_lock = asyncio.Lock()

    async def _connect(self) -> None:
        if self._socket:
            return
        if not self.host:
            raise MotorProtocolError("真实硬件未配置 network.host；请先保持 provider=mock 或填写控制器 IP")
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)

    async def _request(self, command: str, timeout: float | None = None) -> str:
        await self._connect()
        assert self._socket
        async with self._command_lock:
            loop = asyncio.get_running_loop()
            await loop.sock_sendto(self._socket, self._wire_command(command), (self.host, self.port))
            try:
                raw, _ = await asyncio.wait_for(loop.sock_recvfrom(self._socket, 4096), timeout or self.command_timeout)
            except TimeoutError as error:
                raise MotorProtocolError(f"控制器 UDP 命令超时：{command}") from error
            reply = raw.decode("utf-8", errors="replace").strip()
            if reply.upper().startswith("ERR:"):
                raise MotorProtocolError(reply)
            return reply

    async def dispose(self) -> None:
        if self._socket:
            self._socket.close()
            self._socket = None


def create_motor_provider(state: SystemState, machine: dict[str, Any], publish: Publish) -> MotorProvider:
    provider = str(machine.get("provider", "mock")).lower()
    if provider == "mock":
        return MockMotorProvider(state, machine, publish)
    if provider == "tcp":
        return TcpMotorProvider(state, machine, publish)
    if provider == "udp":
        return UdpMotorProvider(state, machine, publish)
    raise ValueError(f"不支持的电机 provider：{provider}（可选 mock、tcp、udp）")


class MediaService:
    def __init__(self, state: SystemState, publish: Publish) -> None:
        self.state, self.publish = state, publish

    async def load(self, scene_id: int) -> None:
        self.state.playback_state = "loading"
        self.state.video_id = f"scene-{scene_id}-video"
        await self.publish(self.state.payload())

    async def play(self) -> None:
        self.state.playback_state = "playing"
        await self.publish(self.state.payload())

    async def pause(self) -> None:
        if self.state.video_id:
            self.state.playback_state = "paused"
            await self.publish(self.state.payload())

    async def stop(self) -> None:
        self.state.playback_state = "stopped"
        await self.publish(self.state.payload())


class SceneService:
    def __init__(self, state: SystemState, scenes: dict[int, dict[str, Any]], motor: MotorProvider, media: MediaService, publish: Publish) -> None:
        self.state, self.scenes, self.motor, self.media, self.publish = state, scenes, motor, media, publish
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def activate_scene(self, scene_id: int, command: dict[str, str]) -> dict[str, Any]:
        if scene_id not in self.scenes:
            return {"success": False, "error": "INVALID_SCENE", "scene": scene_id}
        async with self._lock:
            if self.state.target_scene == scene_id or (self.state.current_scene == scene_id and self.state.motor_state == "arrived"):
                return {"success": True, "accepted": False, "scene": scene_id, "message": f"Scene {scene_id} already active or pending"}
            if self._task and not self._task.done():
                self._task.cancel()
            self.state.target_scene = scene_id
            self.state.error = None
            self.state.last_command = command
            self._task = asyncio.create_task(self._run_scene(scene_id), name=f"scene-{scene_id}")
            await self.publish(self.state.payload())
        return {"success": True, "accepted": True, "scene": scene_id, "message": f"Scene {scene_id} accepted"}

    async def _run_scene(self, scene_id: int) -> None:
        try:
            await self.media.stop()
            moved = await self.motor.move_to(self.scenes[scene_id]["motorPosition"])
            if not moved:
                raise RuntimeError("电机未到位")
            self.state.current_scene = scene_id
            self.state.target_scene = None
            await self.media.load(scene_id)
            await self.media.play()
        except asyncio.CancelledError:
            logger.info("场景任务被新命令取消")
            await self.motor.stop()
            raise
        except Exception as error:  # pragma: no cover - defensive hardware boundary
            logger.exception("场景切换失败")
            self.state.error = str(error)
            self.state.motor_state = "error"
            self.state.playback_state = "error"
            self.state.target_scene = None
            await self.publish(self.state.payload())

    async def go_home(self, command: dict[str, str]) -> dict[str, Any]:
        async with self._lock:
            if self._task and not self._task.done():
                self._task.cancel()
            self.state.last_command = command
            self.state.target_scene = None
            self.state.error = None
            self._task = asyncio.create_task(self._run_home(), name="home")
            await self.publish(self.state.payload())
        return {"success": True, "accepted": True, "message": "Home accepted"}

    async def _run_home(self) -> None:
        try:
            await self.media.stop()
            await self.motor.home()
            self.state.current_scene = next((scene_id for scene_id, scene in self.scenes.items() if scene["motorPosition"] == self.motor.machine["homePosition"]), None)
            await self.publish(self.state.payload())
        except asyncio.CancelledError:
            await self.motor.stop()
            raise


class CarouselService:
    def __init__(self, state: SystemState, scene_service: SceneService, app_config: dict[str, Any], publish: Publish) -> None:
        self.state, self.scene_service, self.app_config, self.publish = state, scene_service, app_config, publish
        self._task: asyncio.Task[None] | None = None

    async def start(self, command: dict[str, str]) -> dict[str, Any]:
        if self.state.carousel_mode:
            return {"success": True, "accepted": False, "message": "Carousel already running"}
        self.state.carousel_mode = True
        self.state.last_command = command
        self._task = asyncio.create_task(self._run(), name="carousel")
        await self.publish(self.state.payload())
        return {"success": True, "accepted": True, "message": "Carousel started"}

    async def stop(self, command: dict[str, str] | None = None) -> dict[str, Any]:
        if not self.state.carousel_mode:
            return {"success": True, "accepted": False, "message": "Carousel already stopped"}
        self.state.carousel_mode = False
        if command:
            self.state.last_command = command
        if self._task and self._task is not asyncio.current_task():
            self._task.cancel()
        await self.publish(self.state.payload())
        return {"success": True, "accepted": True, "message": "Carousel stopped"}

    def _next_scene(self) -> int:
        current = self.state.current_scene or 1
        direction = self.state.carousel_direction
        if current == 4:
            direction = "backward"
        elif current == 1:
            direction = "forward"
        self.state.carousel_direction = direction
        return current + (1 if direction == "forward" else -1)

    async def _run(self) -> None:
        try:
            while self.state.carousel_mode:
                scene_id = self._next_scene()
                result = await self.scene_service.activate_scene(scene_id, {"method": "SYSTEM", "path": "/carousel"})
                if result.get("accepted"):
                    while self.state.target_scene is not None and self.state.carousel_mode:
                        await asyncio.sleep(0.1)
                    await asyncio.sleep(self.app_config["carouselDwellSeconds"])
                else:
                    await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            raise
