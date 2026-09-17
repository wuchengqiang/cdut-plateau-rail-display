from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def request(url: str, method: str = "GET", body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], dict[str, Any]]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data:
        request_headers["Content-Type"] = "application/json"
    query = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(query, timeout=2) as response:
            return response.status, dict(response.headers.items()), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), json.loads(error.read().decode("utf-8"))


def request_text(url: str) -> tuple[int, dict[str, str], str]:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.status, dict(response.headers.items()), response.read().decode("utf-8")


def wakefusion_body(request_id: str) -> dict[str, str]:
    return {
        "schemaVersion": "wakefusion.embedded-app/v1",
        "requestId": request_id,
        "source": "wakefusion-host",
    }


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def header(headers: dict[str, str], name: str) -> str:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), "")


def main() -> None:
    port = available_port()
    base_url = f"http://127.0.0.1:{port}"
    token = "local-development-token"
    auth_headers = {"Authorization": f"Bearer {token}"}
    # Always isolate tests from the deployment's real controller configuration.
    temporary = tempfile.TemporaryDirectory(prefix="rail-contract-")
    test_root = Path(temporary.name)
    shutil.copytree(ROOT.parent / "config", test_root / "config")
    shutil.copytree(ROOT / "static", test_root / "backend" / "static")
    (test_root / "content").mkdir()
    # Contract fixture only: presence selects video mode; this test does not decode media.
    (test_root / "content" / "videos").mkdir()
    (test_root / "content" / "videos" / "p01.mp4").write_bytes(b"contract-media-fixture")
    machine_path = test_root / "config" / "machine.json"
    machine = json.loads(machine_path.read_text(encoding="utf-8"))
    machine["provider"] = "mock"
    machine["mockMoveDurationMs"] = 40
    machine_path.write_text(json.dumps(machine), encoding="utf-8")
    app_path = test_root / "config" / "app.json"
    app_config = json.loads(app_path.read_text(encoding="utf-8"))
    app_config['carouselDwellSeconds'] = .2
    app_path.write_text(json.dumps(app_config), encoding='utf-8')
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        env={**os.environ, "WAKEFUSION_APP_TOKEN": token, "RAIL_DISPLAY_ROOT": str(test_root)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                health_status, health_headers, health = request(f"{base_url}/api/wakefusion/v1/health", headers=auth_headers)
                if health_status == 200 and health["ready"] is True:
                    break
            except urllib.error.URLError:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError("WakeFusion health endpoint did not become ready")

        assert header(health_headers, "Cache-Control") == "no-store"
        assert header(health_headers, "Content-Type").startswith("application/json; charset=utf-8")
        assert health["appId"] == "cdut-slider-screen"
        assert health["version"] == "1.1.7"

        status_code, _, status = request(f"{base_url}/api/wakefusion/v1/status", headers=auth_headers)
        assert status_code == 200 and {"state", "playing", "updatedAt", "actionsHash"}.issubset(status)
        assert len(status["actionsHash"]) == 64

        actions_started = time.monotonic()
        actions_code, _, actions_response = request(f"{base_url}/api/wakefusion/v1/actions", headers=auth_headers)
        assert time.monotonic() - actions_started < 1
        actions = actions_response["actions"]
        assert actions_code == 200 and len(actions) == 10
        assert "revision" not in actions_response
        assert all("index" not in action for action in actions)
        assert actions[0]["name"] == "高原启程" and actions[4]["name"] == "播放"

        request_id = str(uuid.uuid4())
        headers = {**auth_headers, "Idempotency-Key": request_id}
        first = request(f"{base_url}/api/wakefusion/v1/actions/0/execute", "POST", wakefusion_body(request_id), headers)
        duplicate = request(f"{base_url}/api/wakefusion/v1/actions/0/execute", "POST", wakefusion_body(request_id), headers)
        assert first[0] == 200 and first[2]["ok"] is True and first[2]["index"] == 0
        assert duplicate[0] == 200 and duplicate[2] == first[2]

        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            state_code, _, current_state = request(f"{base_url}/api/wakefusion/v1/status", headers=auth_headers)
            if state_code == 200 and current_state["playing"] is True and current_state["activeView"] == "高原启程" and current_state["details"]["motorState"] == "arrived":
                break
            time.sleep(0.05)
        else:
            raise AssertionError('Mock rail never reported arrival')
        conflict_id = str(uuid.uuid4())
        conflict = request(
            f"{base_url}/api/wakefusion/v1/actions/0/execute",
            "POST",
            wakefusion_body(conflict_id),
            {**auth_headers, "Idempotency-Key": conflict_id},
        )
        assert conflict[0] == 409 and conflict[2]["error"]["code"] == "action_conflict"

        missing_id = str(uuid.uuid4())
        missing = request(f"{base_url}/api/wakefusion/v1/actions/99/execute", "POST", wakefusion_body(missing_id), {**auth_headers, "Idempotency-Key": missing_id})
        assert missing[0] == 404 and missing[2]["error"]["code"] == "action_not_found"

        unauthenticated = request(f"{base_url}/api/wakefusion/v1/health")
        assert unauthenticated[0] == 401 and unauthenticated[2]["error"]["code"] == "auth_failed"

        invalid_id = str(uuid.uuid4())
        invalid = request(
            f"{base_url}/api/wakefusion/v1/actions/not-a-number/execute",
            "POST",
            wakefusion_body(invalid_id),
            {**auth_headers, "Idempotency-Key": invalid_id},
        )
        assert invalid[0] == 400 and invalid[2]["error"]["code"] == "invalid_request"

        page_code, _, page_html = request_text(f"{base_url}/")
        assert page_code == 200 and page_html.count('name="wakefusion:embedded-app"') == 1
        config_code, _, config_html = request_text(f"{base_url}/subscriptconfig.html")
        assert config_code == 200 and "数字人动作配置" in config_html
        assert "wakefusion:embedded-app" not in config_html

        admin_password = json.loads((ROOT.parent / "config" / "admin.json").read_text(encoding="utf-8"))["password"]
        login_code, login_headers, _ = request(
            f"{base_url}/api/admin/login",
            "POST",
            {"password": admin_password},
        )
        admin_cookie = header(login_headers, "Set-Cookie").split(";", 1)[0]
        config_api_code, _, config_api = request(
            f"{base_url}/api/admin/wakefusion/actions",
            headers={"Cookie": admin_cookie},
        )
        assert login_code == 200 and config_api_code == 200
        assert config_api["safeToSave"] is False and len(config_api["actions"]) == 10
        assert config_api["actions"][0]["index"] == 0

        presentation_code, _, presentation = request(f"{base_url}/api/admin/presentation", headers={"Cookie": admin_cookie})
        assert presentation_code == 200 and presentation['presentation']['mode'] == 'demo'
        saved_mode_code, _, saved_mode = request(
            f"{base_url}/api/admin/presentation", "PUT", {"mode": "compact", "moveToRestPoint": False}, {"Cookie": admin_cookie}
        )
        assert saved_mode_code == 200 and saved_mode['presentation']['mode'] == 'compact' and saved_mode['moved'] is False
        _, _, display_after_mode = request(f'{base_url}/api/display-config')
        assert display_after_mode['presentation']['mode'] == 'compact'
        assert request(f"{base_url}/api/admin/presentation", "PUT", {"mode": "demo", "moveToRestPoint": False}, {"Cookie": admin_cookie})[0] == 200
        controls_code, _, controls = request(f"{base_url}/api/admin/public-controls", headers={"Cookie": admin_cookie})
        assert controls_code == 200 and controls['publicControls']['showHome'] is False
        updated_controls = {**controls['publicControls'], 'showCarousel': True, 'showHome': True}
        saved_controls_code, _, saved_controls = request(
            f"{base_url}/api/admin/public-controls", "PUT", updated_controls, {"Cookie": admin_cookie}
        )
        assert saved_controls_code == 200 and saved_controls['publicControls'] == updated_controls
        _, _, display_with_controls = request(f'{base_url}/api/display-config')
        assert display_with_controls['publicControls'] == updated_controls
        assert request(
            f"{base_url}/api/admin/public-controls", "PUT", controls['publicControls'], {"Cookie": admin_cookie}
        )[0] == 200

        # The central controller's unchanged HTTP endpoints drive the new policy.
        _, _, display = request(f'{base_url}/api/display-config')
        assert [point['videoAvailable'] for point in display['points']] == [True, False, False, False]
        assert request(f'{base_url}/api/control/carousel/start', 'POST')[2]['accepted'] is True
        assert request(f'{base_url}/api/control/carousel/start', 'POST')[2]['accepted'] is False
        time.sleep(.3)  # Longer than the fallback dwell: a video must not be skipped.
        _, _, playback = request(f'{base_url}/api/status')
        assert playback['currentPointId'] == 'p01' and playback['carouselMode'] is True
        ended = {'sessionId': playback['mediaSessionId'], 'revision': playback['playbackRevision'], 'event': 'ended'}
        assert request(f'{base_url}/api/media/events', 'POST', {**ended, 'event': 'move'})[0] == 422
        assert request(f'{base_url}/api/media/events', 'POST', {**ended, 'sessionId': '0' * 32})[2]['accepted'] is False
        assert request(f'{base_url}/api/media/events', 'POST', ended)[2]['accepted'] is True
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            _, _, playback = request(f'{base_url}/api/status')
            if playback['currentPointId'] == 'p02' and playback['targetPointId'] is None:
                break
            time.sleep(.01)
        else:
            raise AssertionError('Media end did not advance the mock tour to point 2')
        assert playback['playbackState'] == 'showing' and playback['videoId'] is None
        assert request(f'{base_url}/api/media/events', 'POST', ended)[2]['accepted'] is False
        assert request(f'{base_url}/api/control/carousel/stop', 'POST')[2]['accepted'] is True
        time.sleep(.3)
        _, _, stopped_tour = request(f'{base_url}/api/status')
        assert stopped_tour['currentPointId'] == 'p02' and stopped_tour['carouselMode'] is False
        assert request(f'{base_url}/api/control/play', 'POST')[0] == 409  # Do not jump back to point 1 from an image-only point.

        manifest = json.loads((ROOT.parent / "wakefusion" / "app.json").read_text(encoding="utf-8"))
        assert manifest["type"] == "service"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        temporary.cleanup()

    print("WakeFusion V1.1 smoke test passed")


if __name__ == "__main__":
    main()
