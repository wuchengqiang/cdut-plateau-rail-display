from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


def external_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_edge() -> Path:
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        directory = os.environ.get(variable)
        if directory:
            candidate = Path(directory) / "Microsoft/Edge/Application/msedge.exe"
            if candidate.is_file():
                return candidate
    executable = shutil.which("msedge.exe")
    if executable:
        return Path(executable)
    raise RuntimeError("Microsoft Edge was not found. Install Edge before standalone launch.")


def kiosk_command(edge: Path, root: Path, port: int = 8000) -> list[str]:
    # An app-owned profile prevents a normal Edge session from swallowing kiosk flags.
    return [str(edge), "--kiosk", f"http://127.0.0.1:{port}/", "--edge-kiosk-type=fullscreen",
            "--no-first-run", "--autoplay-policy=no-user-gesture-required",
            f"--user-data-dir={root / 'browser-profile'}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="滑轨屏播控系统绿色版")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--no-browser", action="store_true", help="数字人托管模式：只启动 Web 服务，不打开浏览器")
    mode.add_argument("--standalone", action="store_true", help="独立运行：自动打开全屏网页（默认）")
    options = parser.parse_args()

    root = external_root()
    os.environ["RAIL_DISPLAY_ROOT"] = str(root)

    from app.remote_control import ListenerRouter, load_network_settings

    listeners: list[socket.socket] = []
    try:
        local_host, local_port, remote = load_network_settings(root)
        endpoints = [(local_host, local_port)] + ([(remote.host, remote.port)] if remote.enabled else [])
        # Reserve both ports before any hardware initialization. Never reuse an
        # unknown process, or fall back to an unprotected shared listener.
        for host, port in endpoints:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listeners.append(listener)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind((host, port))
            except OSError:
                print(f"Port {port} is already in use or cannot bind to {host}. Close the conflicting service or check the configured address.", flush=True)
                raise
            listener.listen(128)
            listener.setblocking(False)
    except Exception as error:
        for listener in listeners:
            listener.close()
        print(f"Network startup failed: {error}", flush=True)
        return 1

    browser: subprocess.Popen | None = None
    failed: list[str] = []
    finished = threading.Event()
    worker: threading.Thread | None = None
    try:
        edge = None if options.no_browser else find_edge()
        import uvicorn
        from app.main import app

        # One runtime/lifespan, two separate sockets. Remote callers never reach
        # the local page/admin/Host routes, even when claiming localhost headers.
        application = ListenerRouter(app, local_port, remote)
        server = uvicorn.Server(uvicorn.Config(application, host=local_host, port=local_port, log_level="info", proxy_headers=False))
        print(f"Local page and Host API: http://127.0.0.1:{local_port}/", flush=True)
        if remote.enabled:
            print(f"Protected central-control API: {remote.host}:{remote.port}; key file: config/remote-control.key", flush=True)

        def supervise_browser() -> None:
            nonlocal browser
            deadline = time.monotonic() + 30
            while not server.started:
                if finished.wait(.1):
                    return
                if time.monotonic() >= deadline:
                    failed.append("Web service startup timed out; browser was not opened.")
                    server.should_exit = True
                    return
            try:
                assert edge is not None
                browser = subprocess.Popen(kiosk_command(edge, root, local_port))
                print("Standalone fullscreen opened. Alt+F4 closes the page and stops this service.", flush=True)
                while not finished.wait(.2):
                    if browser.poll() is not None:
                        server.should_exit = True
                        return
            except OSError as error:
                failed.append(f"Cannot open fullscreen browser: {error}")
                server.should_exit = True

        if edge:
            worker = threading.Thread(target=supervise_browser, name="standalone-browser", daemon=True)
            worker.start()
        server.run(sockets=listeners)
        if failed:
            print(failed[0], flush=True)
            return 1
        return 0
    except Exception as error:
        print(f"Startup failed: {error}", flush=True)
        return 1
    finally:
        finished.set()
        if worker:
            worker.join(timeout=3)
        # Only our dedicated browser process tree; never terminate normal Edge sessions.
        if browser and browser.poll() is None:
            subprocess.run(["taskkill", "/PID", str(browser.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        for listener in listeners:
            listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
