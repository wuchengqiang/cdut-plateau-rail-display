from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def read_json(relative_path: str) -> dict[str, Any]:
    with (ROOT / relative_path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_admin_password() -> str:
    password = str(read_json("config/admin.json").get("password", ""))
    if len(password) < 8:
        raise ValueError("管理员密码至少需要 8 位")
    return password


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
