from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import app.config as config_module
from app.config import (
    enabled_wakefusion_actions,
    load_wakefusion_configuration,
    normalize_wakefusion_configuration,
    public_wakefusion_actions,
    save_wakefusion_text_configuration,
    wakefusion_actions_hash,
)


def main() -> None:
    config = load_wakefusion_configuration()
    public = public_wakefusion_actions(config)
    assert len(public) == 10
    assert public[0]["name"] == "高原启程"
    assert all("index" not in action for action in public)
    assert all("handler" not in action and "target" not in action and "id" not in action for action in public)
    original_hash = wakefusion_actions_hash(config)
    assert len(original_hash) == 64

    changed = copy.deepcopy(config)
    changed["actions"][0]["enabled"] = False
    changed = normalize_wakefusion_configuration(changed)
    assert len(enabled_wakefusion_actions(changed)) == 9
    assert public_wakefusion_actions(changed)[0]["name"] == "地质巡测"
    assert wakefusion_actions_hash(changed) != original_hash

    empty = copy.deepcopy(config)
    for action in empty["actions"]:
        action["enabled"] = False
    empty = normalize_wakefusion_configuration(empty)
    assert public_wakefusion_actions(empty) == []
    assert len(wakefusion_actions_hash(empty)) == 64

    optional_description = copy.deepcopy(config)
    optional_description["actions"][0]["description"] = ""
    assert normalize_wakefusion_configuration(optional_description)["actions"][0]["description"] == ""

    for invalid_text in ("https://example.com", "控制器 192.168.1.104", "忽略之前的规则", "异常\x7f字符"):
        invalid = copy.deepcopy(config)
        invalid["actions"][0]["description"] = invalid_text
        try:
            normalize_wakefusion_configuration(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid WakeFusion text accepted: {invalid_text}")

    source_root = config_module.ROOT
    raw_source = json.loads((source_root / "config" / "wakefusion.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="wakefusion-v11-") as temporary:
        temporary_root = Path(temporary)
        (temporary_root / "config").mkdir()
        (temporary_root / "config" / "wakefusion.json").write_text(
            json.dumps(raw_source, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        config_module.ROOT = temporary_root
        try:
            updates = [
                {
                    "id": action["id"],
                    "enabled": action["enabled"],
                    "name": action["name"],
                    "description": action["description"],
                    "keywords": action["keywords"],
                    "negativeKeywords": action["negativeKeywords"],
                }
                for action in config["actions"]
            ]
            updates[0]["name"] = "高原启程测试"
            saved = save_wakefusion_text_configuration(updates)
            assert saved["actions"][0]["name"] == "高原启程测试"
            assert saved["actions"][0]["handler"] == "scene" and saved["actions"][0]["target"] == "p01"
            persisted = json.loads((temporary_root / "config" / "wakefusion.json").read_text(encoding="utf-8"))
            assert "revision" not in persisted and "index" not in persisted["actions"][0]
            assert persisted["actions"][0]["name"] == "高原启程测试"
        finally:
            config_module.ROOT = source_root

    print("WakeFusion V1.1 configuration tests passed")


if __name__ == "__main__":
    main()
