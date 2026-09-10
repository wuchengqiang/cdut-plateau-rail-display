"""Exercise the delivered Windows service against loopback UDP only.

Usage: python backend/test_udp_release.py <release/app> [silent]
The delivered config is checked, then only an isolated copy is changed.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid


def main():
    source = Path(sys.argv[1]).resolve()
    silent = len(sys.argv) > 2 and sys.argv[2] == 'silent'
    commands = []
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8000)) == 0:
            raise RuntimeError('Port 8000 occupied; existing process left untouched')
    machine = json.loads((source / 'runtime/config/machine.json').read_text('utf-8'))
    assert machine['provider'] == 'udp'
    assert machine['network']['host'] == '127.0.0.1' and machine['network']['port'] == 53500

    class Controller(socketserver.BaseRequestHandler):
        def handle(self):
            raw, sock = self.request
            command = raw.decode('ascii').strip()
            commands.append(command)
            if silent:
                return
            reply = {'PING': 'PONG', 'STATUS': 'OK:POS=0;ALM=0;RDY=1', 'STOP': 'OK:STOP'}.get(command)
            if command.startswith('MOVE '):
                time.sleep(.3)
                reply = 'OK:' + command
            sock.sendto((reply or 'ERR:UNKNOWN_CMD').encode() + b'\r\n', self.client_address)

    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='udp-release-', dir=project / 'tmp') as directory, socketserver.UDPServer(('127.0.0.1', 0), Controller) as server:
        work = Path(directory)
        shutil.copytree(source, work / 'app')
        machine['network'].update(host='127.0.0.1', port=server.server_address[1], commandTimeoutMs=60000 if silent else 1000)
        (work / 'app/runtime/config/machine.json').write_text(json.dumps(machine), encoding='utf-8')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        token = uuid.uuid4().hex
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def api(path, method='GET', data=None, authenticate=True):
            headers = {'Authorization': f'Bearer {token}'} if authenticate else {}
            if data is not None:
                headers.update({'Content-Type': 'application/json', 'Idempotency-Key': data['requestId']})
            req = urllib.request.Request('http://127.0.0.1:8000' + path, method=method,
                                         data=json.dumps(data).encode() if data is not None else None, headers=headers)
            try:
                response = opener.open(req, timeout=2)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, dict(response.headers), json.load(response)

        def execute(index):
            return api(f'/api/wakefusion/v1/actions/{index}/execute', 'POST', {
                'schemaVersion': 'wakefusion.embedded-app/v1', 'requestId': str(uuid.uuid4()), 'source': 'wakefusion-host'})

        log_path = project / 'tmp' / ('udp-release-silent.log' if silent else 'udp-release-normal.log')
        with log_path.open('wb') as log:
            process = subprocess.Popen(['cmd.exe', '/d', '/c', 'start.bat'], cwd=work / 'app',
                env={**os.environ, 'WAKEFUSION_APP_TOKEN': token}, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 12
                while True:
                    try:
                        code, headers, health = api('/api/wakefusion/v1/health')
                        break
                    except OSError:
                        if time.monotonic() > deadline or process.poll() is not None:
                            raise AssertionError(f'Service failed to start; inspect {log_path}')
                        time.sleep(.1)
                assert code == 200 and health['ready'] and health['version'] == '1.1.3', health
                assert {k.lower(): v for k, v in headers.items()}['cache-control'] == 'no-store'
                assert api('/api/wakefusion/v1/health', authenticate=False)[0] == 401
                for route in ('health', 'status', 'actions'):
                    started = time.monotonic()
                    assert api('/api/wakefusion/v1/' + route)[0] == 200
                    assert time.monotonic() - started < 1
                assert len(api('/api/wakefusion/v1/actions')[2]['actions']) == 10
                with opener.open('http://127.0.0.1:8000/?embed=1&avatarAnchor=right') as page:
                    assert page.status == 200 and page.read().decode().count('wakefusion:embedded-app') == 1
                if silent:
                    blocked = execute(0)
                    assert blocked[0] == 423 and blocked[2]['error']['code'] == 'application_busy'
                deadline = time.monotonic() + 18
                while True:
                    assert api('/api/wakefusion/v1/health')[2]['ready']
                    state = api('/api/wakefusion/v1/status')[2]
                    if not state['details']['hardwareInitializing']:
                        break
                    assert time.monotonic() < deadline, 'Hardware init must be bounded'
                    time.sleep(.1)
                if silent:
                    assert state['state'] == 'error' and commands == ['PING'], (state, commands)
                else:
                    assert state['details']['motorState'] == 'arrived'
                    assert execute(0)[2]['ok']
                    before = api('/api/status')[2]
                    assert before['playbackState'] == 'playing' and before['displayPointId'] == 'p01', before
                    deadline = time.monotonic() + 5
                    while True:
                        state = api('/api/status')[2]
                        if state['currentScene'] == 'p01' and state['playbackState'] == 'playing':
                            break
                        assert time.monotonic() < deadline, state
                        time.sleep(.05)
                    assert 'MOVE 1600' in commands
                    for index, expected in ((5, 'paused'), (4, 'playing'), (6, 'stopped')):
                        assert execute(index)[2]['ok']
                        assert api('/api/status')[2]['playbackState'] == expected
                    req = urllib.request.Request('http://127.0.0.1:8000/content/videos/p01.mp4', headers={'Range': 'bytes=0-1023'})
                    with opener.open(req) as video:
                        assert video.status == 206 and len(video.read()) == 1024
                    assert execute(7)[2]['ok']
                    deadline = time.monotonic() + 5
                    while api('/api/status')[2]['currentScene'] != 'p00':
                        assert time.monotonic() < deadline
                        time.sleep(.05)
                    assert 'MOVE 0' in commands
                assert not any('WATCH' in c or c == 'ZERO' for c in commands)
                print(json.dumps({'result': 'passed', 'silent': silent, 'version': health['version'],
                                  'udpCommands': commands, 'physicalControllerContacted': False}))
            finally:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                process.wait(timeout=10)
                server.shutdown()


if __name__ == '__main__':
    main()
