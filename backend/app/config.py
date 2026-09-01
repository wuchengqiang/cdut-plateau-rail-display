from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("RAIL_DISPLAY_ROOT", Path(__file__).resolve().parents[2])).resolve()
PACKAGE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT)).resolve()
STATIC_ROOT = PACKAGE_ROOT / "backend" / "static"


def read_json(relative_path: str) -> dict[str, Any]:
    with (ROOT / relative_path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_admin_password() -> str:
    password = str(read_json("config/admin.json").get("password", ""))
    if len(password) < 8:
        raise ValueError("管理员密码至少需要 8 位")
    return password


def load_wakefusion_configuration() -> dict[str, Any]:
    """Load the only public action directory exposed to WakeFusion Host."""
    config = read_json("config/wakefusion.json")
    if config.get("schemaVersion") != "wakefusion.embedded-app/v1":
        raise ValueError("WakeFusion 协议版本必须为 wakefusion.embedded-app/v1")

    app_id = str(config.get("appId", ""))
    if not app_id or len(app_id) > 64 or any(not (char.isalnum() or char in "-_") for char in app_id):
        raise ValueError("WakeFusion appId 只能包含字母、数字、-、_")

    handlers = {"scene", "play", "pause", "stop", "home", "carousel_start", "carousel_stop"}
    actions = config.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("WakeFusion actions 必须是非空数组")

    indexes: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for raw_action in actions:
        if not isinstance(raw_action, dict):
            raise ValueError("WakeFusion action 必须是对象")
        index = raw_action.get("index")
        if not isinstance(index, int) or index <= 0 or index in indexes:
            raise ValueError("WakeFusion action index 必须为唯一正整数")
        indexes.add(index)
        name = str(raw_action.get("name", "")).strip()
        description = str(raw_action.get("description", "")).strip()
        keywords = raw_action.get("keywords", [])
        handler = str(raw_action.get("handler", ""))
        if not name or len(name) > 80 or not description or len(description) > 300:
            raise ValueError(f"WakeFusion action {index} 的名称或说明不符合要求")
        if not isinstance(keywords, list) or len(keywords) > 20 or any(not isinstance(word, str) or len(word) > 30 for word in keywords):
            raise ValueError(f"WakeFusion action {index} 的关键词不符合要求")
        if handler not in handlers:
            raise ValueError(f"WakeFusion action {index} 的 handler 不受支持")
        if handler == "scene" and not str(raw_action.get("target", "")).strip():
            raise ValueError(f"WakeFusion action {index} 缺少展项目标")
        normalized.append({**raw_action, "index": index, "name": name, "description": description, "keywords": keywords, "handler": handler})

    return {**config, "appId": app_id, "version": str(config.get("version", "1.0.0")), "actions": normalized}


def load_configuration() -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    app = read_json("config/app.json")
    point_config = read_json("config/points.json")
    machine = read_json("config/machine.json")
    points = [point for point in point_config["points"] if point.get("enabled", True)]
    if not points:
        raise ValueError("未配置可用点位")

    points.sort(key=lambda point: (point.get("order", 0), str(point["id"])))
    point_ids = [str(point["id"]) for point in points]
    if len(point_ids) != len(set(point_ids)):
        raise ValueError("点位 id 不能重复")

    configured: dict[str, dict[str, Any]] = {}
    positions: dict[str, float | None] = {}
    for point in points:
        point_id = str(point["id"])
        if "positionMm" not in point:
            raise ValueError(f"点位 {point_id} 缺少 positionMm")
        configured[point_id] = {**point, "id": point_id, "motorPosition": point_id}
        raw_position = point["positionMm"]
        positions[point_id] = None if raw_position is None else float(raw_position)

    home_point_id = str(point_config.get("homePointId", point_ids[0]))
    if home_point_id not in configured:
        raise ValueError("homePointId 必须是已启用点位")
    machine = {**machine, "homePosition": home_point_id, "positionsMm": positions}
    app = {**app, "tourMode": point_config.get("tourMode", "pingPong")}
    return app, configured, machine
