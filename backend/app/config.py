from __future__ import annotations

import json
import os
import hashlib
import re
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


WAKEFUSION_SCHEMA = "wakefusion.embedded-app/v1"
WAKEFUSION_TEXT_BLOCKLIST = (
    "<script",
    "javascript:",
    "ignore previous",
    "system prompt",
    "忽略系统",
    "忽略之前",
    "执行任意命令",
    "访问任意",
)
IPV4_PATTERN = re.compile(
    r"(?<!\d)(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?::\d{1,5})?(?!\d)"
)
ACTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _wakefusion_public_text(value: Any, maximum: int, label: str, *, required: bool) -> str:
    text = str(value).strip()
    lowered = text.lower()
    if required and not text:
        raise ValueError(f"{label}不能为空")
    if len(text) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError(f"{label}长度或字符不符合要求")
    if "<" in text or ">" in text or "http://" in lowered or "https://" in lowered or IPV4_PATTERN.search(text):
        raise ValueError(f"{label}不得包含标签、URL 或 IP 地址")
    if any(phrase in lowered for phrase in WAKEFUSION_TEXT_BLOCKLIST):
        raise ValueError(f"{label}包含不允许的指令文本")
    return text


def normalize_wakefusion_configuration(config: dict[str, Any]) -> dict[str, Any]:
    """Validate internal action mappings and V1.1 operator-editable text."""
    if config.get("schemaVersion") != "wakefusion.embedded-app/v1":
        raise ValueError("WakeFusion 协议版本必须为 wakefusion.embedded-app/v1")

    app_id = str(config.get("appId", ""))
    if not app_id or len(app_id) > 64 or any(not (char.isalnum() or char in "-_") for char in app_id):
        raise ValueError("WakeFusion appId 只能包含字母、数字、-、_")

    handlers = {"scene", "play", "pause", "stop", "home", "carousel_start", "carousel_stop"}
    actions = config.get("actions")
    if not isinstance(actions, list) or len(actions) > 100:
        raise ValueError("WakeFusion actions 必须是最多 100 项的数组")

    action_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for position, raw_action in enumerate(actions):
        if not isinstance(raw_action, dict):
            raise ValueError("WakeFusion action 必须是对象")
        action_id = str(raw_action.get("id", "")).strip()
        if not ACTION_ID_PATTERN.fullmatch(action_id) or action_id in action_ids:
            raise ValueError("WakeFusion action id 必须是唯一的 1～64 位字母、数字、-、_")
        action_ids.add(action_id)
        enabled = raw_action.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"WakeFusion action {action_id} 的 enabled 必须是布尔值")
        name = _wakefusion_public_text(raw_action.get("name", ""), 80, f"WakeFusion action {action_id} 名称", required=True)
        description = _wakefusion_public_text(raw_action.get("description", ""), 300, f"WakeFusion action {action_id} 说明", required=False)
        keywords = raw_action.get("keywords", [])
        negative_keywords = raw_action.get("negativeKeywords", [])
        handler = str(raw_action.get("handler", ""))
        if not isinstance(keywords, list) or len(keywords) > 20:
            raise ValueError(f"WakeFusion action {action_id} 的关键词不符合要求")
        if not isinstance(negative_keywords, list) or len(negative_keywords) > 20:
            raise ValueError(f"WakeFusion action {action_id} 的反向关键词不符合要求")
        normalized_keywords = [
            _wakefusion_public_text(word, 30, f"WakeFusion action {action_id} 关键词", required=True) for word in keywords
        ]
        normalized_negative_keywords = [
            _wakefusion_public_text(word, 30, f"WakeFusion action {action_id} 反向关键词", required=True)
            for word in negative_keywords
        ]
        if handler not in handlers:
            raise ValueError(f"WakeFusion action {action_id} 的 handler 不受支持")
        if handler == "scene" and not str(raw_action.get("target", "")).strip():
            raise ValueError(f"WakeFusion action {action_id} 缺少展项目标")
        normalized.append(
            {
                **raw_action,
                "id": action_id,
                "enabled": enabled,
                "name": name,
                "description": description,
                "keywords": normalized_keywords,
                "negativeKeywords": normalized_negative_keywords,
                "handler": handler,
                "_position": position,
            }
        )

    version = str(config.get("version", "1.0.0")).strip()
    if not version or len(version) > 100:
        raise ValueError("WakeFusion version 必须为 1～100 位非空字符串")
    normalized_config = {**config, "appId": app_id, "version": version, "actions": normalized}
    normalized_config.pop("revision", None)
    return normalized_config


def load_wakefusion_configuration() -> dict[str, Any]:
    """Load the internal V1.1 action contract and operator-editable text."""
    return normalize_wakefusion_configuration(read_json("config/wakefusion.json"))


def enabled_wakefusion_actions(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [action for action in config["actions"] if action["enabled"]]


def public_wakefusion_actions(config: dict[str, Any]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for action in enabled_wakefusion_actions(config):
        item: dict[str, Any] = {"name": action["name"]}
        if action["description"]:
            item["description"] = action["description"]
        if action["keywords"]:
            item["keywords"] = action["keywords"]
        if action["negativeKeywords"]:
            item["negativeKeywords"] = action["negativeKeywords"]
        public.append(item)
    return public


def wakefusion_actions_hash(config: dict[str, Any]) -> str:
    serialized = json.dumps(public_wakefusion_actions(config), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def save_wakefusion_text_configuration(updates: list[dict[str, Any]]) -> dict[str, Any]:
    """Atomically save text/enabled fields while preserving action order and internal mappings."""
    current_raw = read_json("config/wakefusion.json")
    current_actions = current_raw.get("actions", [])
    if not isinstance(updates, list) or not all(isinstance(item, dict) for item in updates):
        raise ValueError("actions 必须是数组")
    update_by_id = {str(item.get("id", "")): item for item in updates}
    current_ids = [str(item.get("id", "")) for item in current_actions]
    if len(update_by_id) != len(updates) or set(update_by_id) != set(current_ids):
        raise ValueError("动作集合与开发期契约不一致，不能新增、删除或重排内部动作")

    patched_actions: list[dict[str, Any]] = []
    for action in current_actions:
        action_id = str(action["id"])
        update = update_by_id[action_id]
        patched_actions.append(
            {
                **action,
                "enabled": update.get("enabled", action.get("enabled", True)),
                "name": update.get("name", action.get("name", "")),
                "description": update.get("description", action.get("description", "")),
                "keywords": update.get("keywords", action.get("keywords", [])),
                "negativeKeywords": update.get("negativeKeywords", action.get("negativeKeywords", [])),
            }
        )

    persisted = {**current_raw, "actions": patched_actions}
    persisted.pop("revision", None)
    normalized = normalize_wakefusion_configuration(persisted)
    for action in normalized["actions"]:
        action.pop("_position", None)
    config_path = ROOT / "config" / "wakefusion.json"
    temporary_path = config_path.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary_path, config_path)
    return normalize_wakefusion_configuration(normalized)


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
