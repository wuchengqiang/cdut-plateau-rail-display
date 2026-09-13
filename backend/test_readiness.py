"""Regression: a silent TCP controller must never hold Host readiness at 503."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import uuid

from test_wakefusion import available_port, header, request, request_text, wakefusion_body

ROOT = Path(__file__).resolve().parent
received: list[str] = []


class SilentController(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            while line := self.rfile.readline():
                received.append(line.decode('ascii').strip())
                # Accept the connection, but never return even the initial PONG.
        except ConnectionError:
            pass


class ControllerServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


class SilentUdpController(socketserver.DatagramRequestHandler):
    def handle(self) -> None:
        received.append(self.request[0].decode('ascii').strip())

    def finish(self) -> None:
        pass  # Do not send the default empty datagram.


def main() -> None:
    protocol = sys.argv[1] if len(sys.argv) > 1 else 'tcp'
    server_type, handler = (socketserver.UDPServer, SilentUdpController) if protocol == 'udp' else (ControllerServer, SilentController)
    with tempfile.TemporaryDirectory(prefix='rail-readiness-') as directory, server_type(('127.0.0.1', 0), handler) as controller:
        threading.Thread(target=controller.serve_forever, daemon=True).start()
        root = Path(directory)
        shutil.copytree(ROOT.parent / 'config', root / 'config')
        shutil.copytree(ROOT / 'static', root / 'backend' / 'static')
        (root / 'content').mkdir()
        machine_path = root / 'config/machine.json'
        machine = json.loads(machine_path.read_text('utf-8'))
        machine['provider'] = protocol
        machine['network'].update(host='127.0.0.1', port=controller.server_address[1], commandTimeoutMs=60000)
        machine_path.write_text(json.dumps(machine), encoding='utf-8')
        base_url = f'http://127.0.0.1:{available_port()}'
        token = uuid.uuid4().hex
        auth = {'Authorization': f'Bearer {token}'}
        process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', base_url.rsplit(':', 1)[1]],
            cwd=ROOT, env={**os.environ, 'RAIL_DISPLAY_ROOT': str(root), 'WAKEFUSION_APP_TOKEN': token},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 8
            while True:
                try:
                    code, headers, health = request(base_url + '/api/wakefusion/v1/health', headers=auth)
                    break
                except urllib.error.URLError:
                    if time.monotonic() >= deadline:
                        raise AssertionError('Service never started')
                    time.sleep(.05)
            assert code == 200 and health['ready'] is True and health['version'] == '1.1.5', (code, health)
            assert header(headers, 'Cache-Control') == 'no-store'
            assert request(base_url + '/api/wakefusion/v1/health')[0] == 401
            assert request_text(base_url + '/')[0] == 200
            for route in ('health', 'status', 'actions'):
                started = time.monotonic()
                assert request(base_url + '/api/wakefusion/v1/' + route, headers=auth)[0] == 200
                assert time.monotonic() - started < 1, route
            state = request(base_url + '/api/wakefusion/v1/status', headers=auth)[2]
            assert state['details']['hardwareInitializing'] is True
            rid = str(uuid.uuid4())
            blocked = request(base_url + '/api/wakefusion/v1/actions/0/execute', 'POST', wakefusion_body(rid), {**auth, 'Idempotency-Key': rid})
            assert blocked[0] == 423 and blocked[2]['error']['code'] == 'application_busy', blocked
            for route in ('points/p01/activate', 'home', 'carousel/start'):
                assert request(base_url + '/api/control/' + route, 'POST')[0] == 423

            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                assert request(base_url + '/api/wakefusion/v1/health', headers=auth)[0] == 200
                code, _, state = request(base_url + '/api/wakefusion/v1/status', headers=auth)
                assert code == 200
                if not state['details']['hardwareInitializing']:
                    break
                time.sleep(.2)
            else:
                raise AssertionError('Hardware initialization was not bounded')
            assert state['state'] == 'error' and state['details']['motorState'] == 'error', state
            assert received == ['PING'], received
            print(f'Readiness regression passed: silent {protocol}, immediate 200, <1s probes, 423 motion guard, bounded hardware timeout, no MOVE')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            controller.shutdown()


if __name__ == '__main__':
    main()
