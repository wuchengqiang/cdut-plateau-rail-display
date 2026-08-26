from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def external_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def open_display(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url, new=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="滑轨屏播控系统绿色版")
    parser.add_argument("--no-browser", action="store_true", help="只启动本地服务，不自动打开浏览器")
    args = parser.parse_args()

    root = external_root()
    os.environ["RAIL_DISPLAY_ROOT"] = str(root)
    url = "http://127.0.0.1:8000/"
    if not args.no_browser:
        threading.Thread(target=open_display, args=(url,), daemon=True).start()

    import uvicorn
    from app.main import app

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
