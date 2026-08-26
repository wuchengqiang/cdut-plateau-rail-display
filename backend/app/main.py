from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, STATIC_ROOT, load_admin_password, load_configuration
from .services import CarouselService, MediaService, MotorProtocolError, MotorProvider, SceneService, SystemState, create_motor_provider


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("polar_rail")


class DisplayRuntime:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.app_config, self.scenes, self.machine = load_configuration()
        self.admin_password = load_admin_password()
        self.admin_token = secrets.token_urlsafe(32)
        self.state = SystemState(current_scene=self._home_scene())
        self.motor: MotorProvider = create_motor_provider(self.state, self.machine, self.publish)
        self.media = MediaService(self.state, self.publish)
        self.scene = SceneService(self.state, self.scenes, self.motor, self.media, self.publish)
        self.carousel = CarouselService(self.state, self.scene, self.app_config, self.publish)

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
        self.admin_password = load_admin_password()
        self.scene.scenes = self.scenes
        self.carousel.app_config = self.app_config
        self.motor.machine = self.machine
        return {"success": True, "message": "Content configuration reloaded"}


runtime = DisplayRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.motor.initialize()
    yield
    await runtime.carousel.stop()
    await runtime.motor.dispose()


app = FastAPI(title="Polar Rail Display", lifespan=lifespan)
app.mount("/content", StaticFiles(directory=ROOT / "content"), name="content")


def command(request: Request) -> dict[str, str]:
    return {"method": request.method, "path": request.url.path}


async def manual_scene(scene_id: str, request: Request) -> dict[str, Any]:
    await runtime.carousel.stop()
    return await runtime.scene.activate_scene(scene_id, command(request))


def require_admin(request: Request) -> None:
    if not hmac.compare_digest(request.cookies.get("rail_admin", ""), runtime.admin_token):
        raise HTTPException(status_code=401, detail="需要管理员登录")


@app.api_route("/api/control/scene/{scene_id}", methods=["GET", "POST"])
async def scene(scene_id: str, request: Request) -> dict[str, Any]:
    return await manual_scene(scene_id, request)


@app.api_route("/api/control/points/{point_id}/activate", methods=["GET", "POST"])
async def activate_point(point_id: str, request: Request) -> dict[str, Any]:
    """Stable external API: add a point in config/points.json, then call this endpoint."""
    return await manual_scene(point_id, request)


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return {**runtime.state.payload(), "availablePointCount": len(runtime.scenes), "pointIds": list(runtime.scenes)}


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
