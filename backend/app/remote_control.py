"""Separate, allowlisted central-control gateway; never expose the Host/UI listener."""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, Response


@dataclass(frozen=True)
class RemoteSettings:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8001
    allowed_clients: tuple[ipaddress.IPv4Network, ...] = ()
    allowed_origins: tuple[str, ...] = ()
    api_key: str = field(default="", repr=False)


def _port(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{name} 必须是 1～65535 的整数")
    return value


def _installation_key(root: Path) -> str:
    path = root / "config" / "remote-control.key"
    # One random secret per installation; never put it in public JSON, URLs or logs.
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="ascii") as file:
            file.write(secrets.token_urlsafe(32) + "\n")
            file.flush()
            os.fsync(file.fileno())
    key = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", key):
        raise ValueError("config/remote-control.key 格式无效，需要32～128位随机英文、数字、-或_，不能使用管理员密码")
    return key


def load_network_settings(root: Path) -> tuple[str, int, RemoteSettings]:
    app = json.loads((root / "config" / "app.json").read_text(encoding="utf-8-sig"))
    host = app.get("apiHost", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("数字人及页面服务的 apiHost 必须保持 127.0.0.1；局域网入口请配置 remote-control.json")
    port = _port(app.get("apiPort", 8000), "apiPort")
    path = root / "config" / "remote-control.json"
    if not path.is_file():
        return host, port, RemoteSettings()  # Older installations stay local-only.
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not isinstance(raw.get("enabled", False), bool):
        raise ValueError("remote-control.json 的 enabled 必须为布尔值")
    if not raw.get("enabled", False):
        return host, port, RemoteSettings()
    remote_host = str(raw.get("host", "0.0.0.0"))
    ipaddress.IPv4Address(remote_host)
    remote_port = _port(raw.get("port", 8001), "中控端口")
    if remote_port == port:
        raise ValueError("中控端口不能与本机数字人端口相同")
    clients = raw.get("allowedClients", [])
    if not isinstance(clients, list) or not 1 <= len(clients) <= 64 or not all(isinstance(item, str) for item in clients):
        raise ValueError("enabled=true 时 allowedClients 必须配置1～64个允许的IP或网段")
    networks = tuple(ipaddress.IPv4Network(item, strict=False) for item in clients)
    if any(network.prefixlen == 0 for network in networks):
        raise ValueError("中控来源不能配置为所有地址，请指定实际设备IP或局域网网段")
    origins = raw.get("allowedOrigins", [])
    if not isinstance(origins, list) or len(origins) > 32:
        raise ValueError("allowedOrigins 必须为最多32个明确的网页来源")
    for origin in origins:
        if not isinstance(origin, str):
            raise ValueError("allowedOrigins 必须是字符串数组")
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or "*" in origin or parsed.port == 0
                or any(character.isspace() for character in origin)):
            raise ValueError("allowedOrigins 只接受明确的 http(s)://主机[:端口]，不能使用通配符或路径")
    return host, port, RemoteSettings(True, remote_host, remote_port, networks, tuple(origins), _installation_key(root))


READ_PATHS = {"/api/status", "/api/points"}
CONTROL_PATHS = {
    "/api/control/play", "/api/control/pause", "/api/control/stop", "/api/control/home",
    "/api/control/carousel/start", "/api/control/carousel/stop", "/api/control/emergency-stop",
}
POINT_PATH = re.compile(r"^/api/control/points/[^/]+/activate$")


def allowed_method(path: str) -> str | None:
    if path in READ_PATHS:
        return "GET"
    if path in CONTROL_PATHS or POINT_PATH.fullmatch(path):
        return "POST"
    return None


class RemoteControlGateway:
    def __init__(self, app: Any, settings: RemoteSettings) -> None:
        self.app, self.settings = app, settings

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin", "")
        permitted_origin = origin in self.settings.allowed_origins
        cors_headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if permitted_origin else {}

        async def fail(status: int, code: str, message: str) -> None:
            extra = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
            await JSONResponse({"success": False, "error": code, "message": message}, status_code=status,
                               headers={"Cache-Control": "no-store", **cors_headers, **extra})(scope, receive, send)

        if not self.settings.enabled:
            await fail(503, "REMOTE_DISABLED", "中控远程入口未启用")
            return
        try:
            peer = ipaddress.ip_address(scope.get("client", ("", 0))[0])
        except (ValueError, TypeError):
            peer = None
        # Trust the socket peer only. The launcher disables Uvicorn proxy headers.
        if peer is None or not any(peer in network for network in self.settings.allowed_clients):
            await fail(403, "CLIENT_NOT_ALLOWED", "此设备不在中控允许来源内")
            return
        if origin and not permitted_origin:
            await fail(403, "ORIGIN_NOT_ALLOWED", "此网页来源未获允许，请通过中控后台转发")
            return
        method = allowed_method(scope["path"])
        if scope["method"] == "OPTIONS":
            requested_headers = {name.strip().lower() for name in headers.get("access-control-request-headers", "").split(",") if name.strip()}
            if not permitted_origin or not method or headers.get("access-control-request-method") != method or not requested_headers <= {"authorization", "content-type"}:
                await fail(403, "PREFLIGHT_DENIED", "跨域预检不符合中控接口约定")
                return
            await Response(status_code=204, headers={**cors_headers, "Cache-Control": "no-store",
                "Access-Control-Allow-Methods": method, "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Max-Age": "600"})(scope, receive, send)
            return
        scheme, separator, token = headers.get("authorization", "").partition(" ")
        if not (self.settings.api_key and separator and scheme.lower() == "bearer"
                and hmac.compare_digest(token.encode("utf-8"), self.settings.api_key.encode("ascii"))):
            await fail(401, "AUTH_REQUIRED", "缺少或错误的中控接口密钥")
            return
        if method is None:
            await fail(403, "ROUTE_NOT_ALLOWED", "远程入口只开放已交接的点位、播控、巡展和状态接口")
            return
        if scope["method"] != method:
            await fail(405, "METHOD_NOT_ALLOWED", f"此接口必须使用 {method}")
            return

        async def send_response(message: dict) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": list(message.get("headers", []))}
                response_headers = MutableHeaders(scope=message)
                response_headers["Cache-Control"] = "no-store"
                for name, value in cors_headers.items():
                    response_headers[name] = value
            await send(message)

        await self.app(scope, receive, send_response)


class ListenerRouter:
    """Route by actual accepted socket, not a forgeable Host or forwarded header."""
    def __init__(self, local_app: Any, local_port: int, remote: RemoteSettings) -> None:
        self.local_app, self.local_port, self.remote = local_app, local_port, remote
        self.gateway = RemoteControlGateway(local_app, remote)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await self.local_app(scope, receive, send)
        elif scope.get("server") and scope["server"][1] == self.local_port:
            await self.local_app(scope, receive, send)
        else:
            await self.gateway(scope, receive, send)
