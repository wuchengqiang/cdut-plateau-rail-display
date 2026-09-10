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


def kiosk_command(edge: Path, root: Path) -> list[str]:
    # An app-owned profile prevents a normal Edge session from swallowing kiosk flags.
    return [str(edge), "--kiosk", "http://127.0.0.1:8000/", "--edge-kiosk-type=fullscreen",
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

    # Bind before importing the runtime or starting any hardware connection. Never
    # reuse an unknown service on port 8000 (it may belong to Host with another token).
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 8000))
        listener.listen(128)
        listener.setblocking(False)
    except OSError:
        listener.close()
        print("Port 8000 is already in use. Close Host or the previous standalone service, then retry.", flush=True)
        return 1

    browser: subprocess.Popen | None = None
    failed: list[str] = []
    finished = threading.Event()
    worker: threading.Thread | None = None
    try:
        edge = None if options.no_browser else find_edge()
        import uvicorn
        from app.main import app

        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info"))

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
                browser = subprocess.Popen(kiosk_command(edge, root))
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
        server.run(sockets=[listener])
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
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
