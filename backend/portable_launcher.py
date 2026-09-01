from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def external_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="滑轨屏播控系统绿色版")
    parser.add_argument("--no-browser", action="store_true", help="兼容 WakeFusion 启动参数；服务默认不打开浏览器")
    parser.parse_args()

    root = external_root()
    os.environ["RAIL_DISPLAY_ROOT"] = str(root)

    import uvicorn
    from app.main import app

    # WakeFusion 通过同机内嵌浏览器访问；不将控制接口暴露到局域网。
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
