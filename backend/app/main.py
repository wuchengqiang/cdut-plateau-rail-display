from __future__ import annotations

import asyncio
import hmac
import logging
import os
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, STATIC_ROOT, load_admin_password, load_configuration, load_wakefusion_configuration
from .services import CarouselService, MediaService, MotorProtocolError, MotorProvider, SceneService, SystemState, create_motor_provider


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("polar_rail")


class DisplayRuntime:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.app_config, self.scenes, self.machine = load_configuration()
        self.wakefusion = load_wakefusion_configuration()
        # Host injects this at process start. It is deliberately never persisted or logged.
        self.wakefusion_token = os.environ.get("WAKEFUSION_APP_TOKEN", "")
        self.admin_password = load_admin_password()
        self.admin_token = secrets.token_urlsafe(32)
        self.state = SystemState(current_scene=self._home_scene())
        self.motor: MotorProvider = create_motor_provider(self.state, self.machine, self.publish)
        self.media = MediaService(self.state, self.publish)
        self.scene = SceneService(self.state, self.scenes, self.motor, self.media, self.publish)
        self.carousel = CarouselService(self.state, self.scene, self.app_config, self.publish)
        self.ready = False
        self._initialize_task: asyncio.Task[None] | None = None
        self._wakefusion_lock = asyncio.Lock()
        self._idempotency: OrderedDict[str, tuple[float, int, dict[str, Any]]] = OrderedDict()

    def _home_scene(self) -> str | None:
        return next((scene_id for scene_id, scene in self.scenes.items() if scene["motorPosition"] == self.machine["homePosition"]), None)

    async def publish(self, payload: dict[str, Any]) -> None:
        message = {"type": "status", "data": payload}
        stale: list[WebSocket] = []
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)

    async def reload_content(self) -> dict[str, Any]:
        self.app_config, self.scenes, self.machine = load_configuration()
        self.wakefusion = load_wakefusion_configuration()
        self.admin_password = load_admin_password()
        self.scene.scenes = self.scenes
        self.carousel.app_config = self.app_config
        self.motor.machine = self.machine
        return {"success": True, "message": "Content configuration reloaded"}

    async def start(self) -> None:
        """Keep the web service available while optional hardware initialization completes."""
        self.ready = False
        self.state.error = None
        self._initialize_task = asyncio.create_task(self._initialize_hardware(), name="motor-initialize")

    async def _initialize_hardware(self) -> None:
        try:
            await self.motor.initialize()
        except Exception as error:  # The page must remain available when the controller is offline.
            logger.exception("滑轨控制器初始化失败")
            self.state.motor_state = "error"
            self.state.error = "滑轨控制器暂不可用"
        finally:
            self.ready = True
            await self.publish(self.state.payload())

    async def shutdown(self) -> None:
        if self._initialize_task and not self._initialize_task.done():
            self._initialize_task.cancel()
            try:
                await self._initialize_task
            except asyncio.CancelledError:
                pass
        await self.carousel.stop()
        await self.motor.dispose()

    def action_for_scene(self, scene_id: str | None) -> dict[str, Any] | None:
        if scene_id:
            return next((action for action in self.wakefusion["actions"] if action["handler"] == "scene" and action.get("target") == scene_id), None)
        return None

    def public_actions(self) -> list[dict[str, Any]]:
        return [{key: action[key] for key in ("index", "name", "description", "keywords")} for action in self.wakefusion["actions"]]

    def state_for_wakefusion(self) -> dict[str, Any]:
        active_scene = self.state.target_scene or self.state.current_scene
        active_action = self.action_for_scene(active_scene)
        if active_action is None and self.state.current_scene == self.machine["homePosition"]:
            active_action = next((action for action in self.wakefusion["actions"] if action["handler"] == "home"), None)
        active_view = self.scenes.get(active_scene or "", {}).get("title")
        if not active_view and active_action:
            active_view = active_action["name"]

        if not self.ready:
            public_state = "starting"
        elif self.state.error:
            public_state = "error"
        elif self.state.playback_state == "paused":
            public_state = "paused"
        elif self.state.target_scene or self.state.motor_state == "moving" or self.state.carousel_mode or self.state.playback_state == "playing":
            public_state = "running"
        else:
            public_state = "idle"

        return {
            "activeActionIndex": active_action["index"] if active_action else None,
            "activeView": active_view,
            "playing": self.state.playback_state == "playing",
            "state": public_state,
            "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "details": {
                "motorState": self.state.motor_state,
                "playbackState": self.state.playback_state,
                "carouselMode": self.state.carousel_mode,
            },
        }

    def get_cached_action(self, key: str) -> tuple[int, dict[str, Any]] | None:
        cutoff = time.monotonic() - 600
        while self._idempotency:
            first_key = next(iter(self._idempotency))
            if self._idempotency[first_key][0] >= cutoff:
                break
            self._idempotency.popitem(last=False)
        cached = self._idempotency.get(key)
        return (cached[1], cached[2]) if cached else None

    def cache_action(self, key: str, status_code: int, payload: dict[str, Any]) -> None:
        self._idempotency[key] = (time.monotonic(), status_code, payload)
        self._idempotency.move_to_end(key)
        while len(self._idempotency) > 1000:
            self._idempotency.popitem(last=False)


runtime = DisplayRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.shutdown()


app = FastAPI(title="Polar Rail Display", lifespan=lifespan)
app.mount("/content", StaticFiles(directory=ROOT / "content"), name="content")


@app.middleware("http")
async def wakefusion_response_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    if request.url.path.startswith("/api/wakefusion/v1"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


def command(request: Request) -> dict[str, str]:
    return {"method": request.method, "path": request.url.path}


async def manual_scene(scene_id: str, request: Request) -> dict[str, Any]:
    await runtime.carousel.stop()
    return await runtime.scene.activate_scene(scene_id, command(request))


def require_admin(request: Request) -> None:
    if not hmac.compare_digest(request.cookies.get("rail_admin", ""), runtime.admin_token):
        raise HTTPException(status_code=401, detail="需要管理员登录")


WAKEFUSION_SCHEMA = "wakefusion.embedded-app/v1"


def wakefusion_json(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status_code, media_type="application/json", headers={"Cache-Control": "no-store"})


def wakefusion_error(code: str, message: str, status_code: int, request_id: str | None = None) -> JSONResponse:
    payload: dict[str, Any] = {
        "schemaVersion": WAKEFUSION_SCHEMA,
        "ok": False,
        "error": {"code": code, "message": message},
    }
    if request_id:
        payload["requestId"] = request_id
    return wakefusion_json(payload, status_code)


def wakefusion_authorized(request: Request) -> bool:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    return bool(runtime.wakefusion_token) and separator == " " and scheme.lower() == "bearer" and hmac.compare_digest(token, runtime.wakefusion_token)


@app.get("/api/wakefusion/v1/health")
async def wakefusion_health(request: Request) -> JSONResponse:
    if not wakefusion_authorized(request):
        return wakefusion_error("auth_failed", "缺少或未通过标准 Bearer Token 鉴权", 401)
    payload: dict[str, Any] = {
        "schemaVersion": WAKEFUSION_SCHEMA,
        "ok": True,
        "ready": runtime.ready,
        "appId": runtime.wakefusion["appId"],
        "version": runtime.wakefusion["version"],
    }
    if not runtime.ready:
        payload["message"] = "正在加载业务数据"
        return wakefusion_json(payload, 503)
    return wakefusion_json(payload)


@app.get("/api/wakefusion/v1/status")
async def wakefusion_status(request: Request) -> JSONResponse:
    if not wakefusion_authorized(request):
        return wakefusion_error("auth_failed", "缺少或未通过标准 Bearer Token 鉴权", 401)
    if not runtime.ready:
        return wakefusion_error("application_not_ready", "应用正在初始化", 503)
    return wakefusion_json({"schemaVersion": WAKEFUSION_SCHEMA, "ok": True, **runtime.state_for_wakefusion()})


@app.get("/api/wakefusion/v1/actions")
async def wakefusion_actions(request: Request) -> JSONResponse:
    if not wakefusion_authorized(request):
        return wakefusion_error("auth_failed", "缺少或未通过标准 Bearer Token 鉴权", 401)
    if not runtime.ready:
        return wakefusion_error("application_not_ready", "应用正在初始化", 503)
    return wakefusion_json({"schemaVersion": WAKEFUSION_SCHEMA, "ok": True, "revision": runtime.wakefusion["revision"], "actions": runtime.public_actions()})


async def run_wakefusion_action(action: dict[str, Any], index: int) -> tuple[int, str, str]:
    """Run a server-side allowlisted action without exposing hardware implementation details."""
    handler = action["handler"]
    action_command = {"method": "POST", "path": f"/api/wakefusion/v1/actions/{index}/execute"}
    motion_actions = {"scene", "home", "carousel_start"}
    if handler in motion_actions and runtime.state.target_scene:
        return 423, "application_busy", "滑轨正在执行前一个动作"

    if handler == "scene":
        target = str(action["target"])
        if target not in runtime.scenes:
            logger.error("WakeFusion 动作 %s 配置了不存在的展项", index)
            return 500, "action_failed", "动作配置不可用"
        await runtime.carousel.stop(action_command)
        result = await runtime.scene.activate_scene(target, action_command)
    elif handler == "play":
        runtime.state.last_command = action_command
        await runtime.media.play()
        result = {"success": True, "accepted": True}
    elif handler == "pause":
        runtime.state.last_command = action_command
        await runtime.media.pause()
        result = {"success": True, "accepted": True}
    elif handler == "stop":
        runtime.state.last_command = action_command
        await runtime.media.stop()
        result = {"success": True, "accepted": True}
    elif handler == "home":
        await runtime.carousel.stop(action_command)
        result = await runtime.scene.go_home(action_command)
    elif handler == "carousel_start":
        result = await runtime.carousel.start(action_command)
    elif handler == "carousel_stop":
        result = await runtime.carousel.stop(action_command)
    else:  # Config validation prevents this branch; retain a safe public response.
        return 500, "action_failed", "动作配置不可用"

    if not result.get("success", False):
        return 500, "action_failed", "动作未能受理"
    return 200, "", f"已受理：{action['name']}"


@app.post("/api/wakefusion/v1/actions/{index}/execute")
async def wakefusion_execute(index: int, request: Request) -> JSONResponse:
    request_id = str(request.headers.get("Idempotency-Key", "")).strip()
    if not wakefusion_authorized(request):
        return wakefusion_error("auth_failed", "缺少或未通过标准 Bearer Token 鉴权", 401, request_id or None)
    try:
        body = await request.json()
    except Exception:
        return wakefusion_error("invalid_request", "请求体必须为 JSON 对象", 400, request_id or None)

    if not isinstance(body, dict) or body.get("schemaVersion") != WAKEFUSION_SCHEMA:
        return wakefusion_error("invalid_request", "协议版本或请求体格式不正确", 400, request_id or None)
    body_request_id = str(body.get("requestId", "")).strip()
    source = str(body.get("source", "")).strip()
    if not request_id or not body_request_id or request_id != body_request_id or not source:
        return wakefusion_error("invalid_request", "Idempotency-Key、requestId 和 source 必须有效且一致", 400, request_id or body_request_id or None)

    cached = runtime.get_cached_action(request_id)
    if cached:
        return wakefusion_json(cached[1], cached[0])

    action = next((item for item in runtime.wakefusion["actions"] if item["index"] == index), None)
    if action is None:
        return wakefusion_error("action_not_found", "动作不存在或未启用", 404, request_id)
    if not runtime.ready:
        return wakefusion_error("application_not_ready", "应用正在初始化", 503, request_id)

    async with runtime._wakefusion_lock:
        cached = runtime.get_cached_action(request_id)
        if cached:
            return wakefusion_json(cached[1], cached[0])
        try:
            status_code, error_code, message = await run_wakefusion_action(action, index)
        except Exception:
            logger.exception("WakeFusion 动作执行异常 requestId=%s index=%s", request_id, index)
            status_code, error_code, message = 500, "action_failed", "动作执行失败"

        if error_code:
            payload = {
                "schemaVersion": WAKEFUSION_SCHEMA,
                "ok": False,
                "error": {"code": error_code, "message": message},
                "requestId": request_id,
            }
        else:
            payload = {
                "schemaVersion": WAKEFUSION_SCHEMA,
                "ok": True,
                "requestId": request_id,
                "index": index,
                "message": message,
                "state": runtime.state_for_wakefusion(),
            }
        runtime.cache_action(request_id, status_code, payload)
        logger.info("WakeFusion 动作 requestId=%s index=%s status=%s", request_id, index, status_code)
        return wakefusion_json(payload, status_code)


@app.api_route("/api/control/scene/{scene_id}", methods=["GET", "POST"])
async def scene(scene_id: str, request: Request) -> dict[str, Any]:
    return await manual_scene(scene_id, request)


@app.api_route("/api/control/points/{point_id}/activate", methods=["GET", "POST"])
async def activate_point(point_id: str, request: Request) -> dict[str, Any]:
    """Stable external API: add a point in config/points.json, then call this endpoint."""
    return await manual_scene(point_id, request)


@app.get("/api/status")
async def status() -> dict[str, Any]:
    visible_point_ids = [point_id for point_id, point in runtime.scenes.items() if point.get("visible", True)]
    return {**runtime.state.payload(), "availablePointCount": len(visible_point_ids), "pointIds": visible_point_ids}


@app.get("/api/display-config")
async def display_config() -> dict[str, Any]:
    """Expose external display assets so the frontend never binds mascot filenames."""
    def asset_url(path: str) -> str:
        return "/" + path.replace("\\", "/").lstrip("/")

    return {
        "title": runtime.app_config["title"],
        "themeTitle": runtime.app_config["themeTitle"],
        "themeSubtitle": runtime.app_config.get("themeSubtitle", ""),
        "brandEnglish": runtime.app_config.get("brandEnglish", ""),
        "coordinatePrimary": runtime.app_config.get("coordinatePrimary", ""),
        "coordinateSecondary": runtime.app_config.get("coordinateSecondary", ""),
        "pointPrefix": runtime.app_config.get("pointPrefix", "POINT"),
        "coordinateLabel": runtime.app_config.get("coordinateLabel", ""),
        "emblemPath": asset_url(runtime.app_config["emblemPath"]),
        "labels": runtime.app_config.get("labels", {}),
        "mascots": {key: asset_url(path) for key, path in runtime.app_config["mascots"].items()},
        "points": [
            {
                **scene,
                "videoPath": asset_url(scene["videoPath"]),
                "posterPath": asset_url(scene["posterPath"]),
                "backgroundPath": asset_url(scene["backgroundPath"]),
            }
            for scene in runtime.scenes.values()
            if scene.get("visible", True)
        ],
    }


@app.get("/api/points")
async def points() -> list[dict[str, Any]]:
    """List the currently enabled configurable rail points for external callers."""
    return list((await display_config())["points"])


@app.api_route("/api/control/play", methods=["GET", "POST"])
async def play(request: Request) -> dict[str, Any]:
    runtime.state.last_command = command(request)
    await runtime.media.play()
    return {"success": True, "message": "Playback started"}


@app.api_route("/api/control/pause", methods=["GET", "POST"])
async def pause(request: Request) -> dict[str, Any]:
    runtime.state.last_command = command(request)
    await runtime.media.pause()
    return {"success": True, "message": "Playback paused"}


@app.api_route("/api/control/stop", methods=["GET", "POST"])
async def stop(request: Request) -> dict[str, Any]:
    runtime.state.last_command = command(request)
    await runtime.media.stop()
    return {"success": True, "message": "Playback stopped"}


@app.api_route("/api/control/home", methods=["GET", "POST"])
async def home(request: Request) -> dict[str, Any]:
    await runtime.carousel.stop()
    return await runtime.scene.go_home(command(request))


@app.api_route("/api/control/carousel/start", methods=["GET", "POST"])
async def carousel_start(request: Request) -> dict[str, Any]:
    return await runtime.carousel.start(command(request))


@app.api_route("/api/control/carousel/stop", methods=["GET", "POST"])
async def carousel_stop(request: Request) -> dict[str, Any]:
    return await runtime.carousel.stop(command(request))


@app.post("/api/admin/login")
async def admin_login(request: Request) -> JSONResponse:
    body = await request.json()
    password = str(body.get("password", ""))
    if not hmac.compare_digest(password, runtime.admin_password):
        raise HTTPException(status_code=401, detail="密码不正确")
    response = JSONResponse({"success": True})
    response.set_cookie("rail_admin", runtime.admin_token, httponly=True, samesite="strict")
    return response


@app.post("/api/admin/reload")
async def reload_content(request: Request) -> dict[str, Any]:
    require_admin(request)
    return await runtime.reload_content()


@app.post("/api/admin/hardware/ping")
async def hardware_ping(request: Request) -> dict[str, Any]:
    """Development-only connectivity check; no movement command is issued."""
    require_admin(request)
    try:
        reply = await runtime.motor.ping()
        return {"success": True, "provider": runtime.machine.get("provider", "mock"), "reply": reply}
    except MotorProtocolError as error:
        return {"success": False, "error": "MOTOR_PROTOCOL_ERROR", "message": str(error)}


@app.get("/api/admin/hardware/status")
async def hardware_status(request: Request) -> dict[str, Any]:
    require_admin(request)
    try:
        state = await runtime.motor.get_state()
        return {"success": True, "motorState": state, "provider": runtime.machine.get("provider", "mock")}
    except MotorProtocolError as error:
        return {"success": False, "error": "MOTOR_PROTOCOL_ERROR", "message": str(error)}


@app.websocket("/ws")
async def websocket_status(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime.clients.add(websocket)
    await websocket.send_json({"type": "status", "data": runtime.state.payload()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        runtime.clients.discard(websocket)


@app.get("/{path:path}")
async def display(path: str) -> FileResponse:
    static = STATIC_ROOT
    target = static / path
    if path and target.is_file():
        return FileResponse(target)
    return FileResponse(static / "index.html")
