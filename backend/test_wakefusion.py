from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def request(url: str, method: str = "GET", body: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], dict[str, Any]]:
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
    # Uses the configured mock provider only; no hardware command is emitted.
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                health_status, health_headers, health = request(f"{base_url}/api/wakefusion/v1/health")
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

        status_code, _, status = request(f"{base_url}/api/wakefusion/v1/status")
        assert status_code == 200 and {"state", "playing", "updatedAt"}.issubset(status)

        actions_code, _, actions_response = request(f"{base_url}/api/wakefusion/v1/actions")
        actions = actions_response["actions"]
        assert actions_code == 200 and [action["index"] for action in actions] == list(range(1, 11))
        assert all(set(action) == {"index", "name", "description", "keywords"} for action in actions)

        request_id = str(uuid.uuid4())
        headers = {"Idempotency-Key": request_id}
        first = request(f"{base_url}/api/wakefusion/v1/actions/1/execute", "POST", wakefusion_body(request_id), headers)
        duplicate = request(f"{base_url}/api/wakefusion/v1/actions/1/execute", "POST", wakefusion_body(request_id), headers)
        assert first[0] == 200 and first[2]["ok"] is True
        assert duplicate[0] == 200 and duplicate[2] == first[2]

        missing_id = str(uuid.uuid4())
        missing = request(f"{base_url}/api/wakefusion/v1/actions/99/execute", "POST", wakefusion_body(missing_id), {"Idempotency-Key": missing_id})
        assert missing[0] == 404 and missing[2]["error"]["code"] == "action_not_found"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    print("WakeFusion V1 smoke test passed")


if __name__ == "__main__":
    main()
