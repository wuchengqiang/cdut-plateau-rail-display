from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def read_json(relative_path: str) -> dict[str, Any]:
    with (ROOT / relative_path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_configuration() -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[str, Any]]:
    app = read_json("config/app.json")
    scene_config = read_json("config/scenes.json")
    machine = read_json("config/machine.json")
    scenes = {scene["id"]: scene for scene in scene_config["scenes"] if scene.get("enabled", True)}
    if not scenes:
        raise ValueError("未配置可用场景")
    return app, scenes, machine
