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
    probes = [socket.socket(), socket.socket()]
    for probe in probes:
        probe.bind(('127.0.0.1', 0))
    local_port, remote_port = [probe.getsockname()[1] for probe in probes]
    for probe in probes:
        probe.close()
    machine = json.loads((source / 'runtime/config/machine.json').read_text('utf-8'))
    assert machine['provider'] == 'udp'
    assert machine['network']['host'] == '127.0.0.1' and machine['network']['port'] == 53500
    assert not (source / 'runtime/config/remote-control.key').exists(), 'Generic package must not include real credentials'
    source_app = json.loads((source / 'runtime/config/app.json').read_text('utf-8'))
    source_remote = json.loads((source / 'runtime/config/remote-control.json').read_text('utf-8'))
    assert (source_app['apiHost'], source_app['apiPort']) == ('127.0.0.1', 8000)
    assert (source_remote['host'], source_remote['port'], source_remote['enabled']) == ('0.0.0.0', 8001, True)
    video_suffixes = {'.mp4', '.webm', '.mov', '.m4v', '.avi', '.mkv'}
    assert not [
        path
        for path in (source / 'runtime' / 'content').rglob('*')
        if path.is_file() and path.suffix.lower() in video_suffixes
    ], 'Generic package must not include video files'

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
        # Video files are intentionally excluded from the portable package. Add
        # a tiny disposable fixture only to exercise the delivered service.
        fixture = work / 'app/runtime/content/videos/p01.mp4'
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(b'contract-video-fixture' * 128)
        source_app['apiPort'] = local_port
        source_remote.update(host='127.0.0.1', port=remote_port, allowedClients=['127.0.0.1/32'])
        (work / 'app/runtime/config/app.json').write_text(json.dumps(source_app), encoding='utf-8')
        (work / 'app/runtime/config/remote-control.json').write_text(json.dumps(source_remote), encoding='utf-8')
        machine['network'].update(host='127.0.0.1', port=server.server_address[1], commandTimeoutMs=60000 if silent else 1000)
        (work / 'app/runtime/config/machine.json').write_text(json.dumps(machine), encoding='utf-8')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        token = uuid.uuid4().hex
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def api(path, method='GET', data=None, authenticate=True):
            headers = {'Authorization': f'Bearer {token}'} if authenticate else {}
            if data is not None:
                headers['Content-Type'] = 'application/json'
                if 'requestId' in data:
                    headers['Idempotency-Key'] = data['requestId']
            req = urllib.request.Request(f'http://127.0.0.1:{local_port}' + path, method=method,
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
                assert code == 200 and health['ready'] and health['version'] == '1.1.5', health
                assert {k.lower(): v for k, v in headers.items()}['cache-control'] == 'no-store'
                assert api('/api/wakefusion/v1/health', authenticate=False)[0] == 401
                for route in ('health', 'status', 'actions'):
                    started = time.monotonic()
                    assert api('/api/wakefusion/v1/' + route)[0] == 200
                    assert time.monotonic() - started < 1
                assert len(api('/api/wakefusion/v1/actions')[2]['actions']) == 10
                with opener.open(f'http://127.0.0.1:{local_port}/?embed=1&avatarAnchor=right') as page:
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
                    req = urllib.request.Request(f'http://127.0.0.1:{local_port}/content/videos/p01.mp4', headers={'Range': 'bytes=0-1023'})
                    with opener.open(req) as video:
                        assert video.status == 206 and len(video.read()) == 1024
                    assert execute(7)[2]['ok']
                    deadline = time.monotonic() + 5
                    while api('/api/status')[2]['currentScene'] != 'p00':
                        assert time.monotonic() < deadline
                        time.sleep(.05)
                    assert 'MOVE 0' in commands
                key_path = work / 'app/runtime/config/remote-control.key'
                central_key = key_path.read_text('ascii').strip()

                def central(path, method='GET', key=central_key):
                    headers = {'Authorization': f'Bearer {key}'} if key else {}
                    query = urllib.request.Request(f'http://127.0.0.1:{remote_port}{path}', method=method, headers=headers)
                    try:
                        response = opener.open(query, timeout=2)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        return response.status, json.load(response)

                before_commands = list(commands)
                assert central('/api/status', key='')[0] == 401
                assert central('/api/control/points/p01/activate', 'POST', key=token)[0] == 401
                for path in ['/', '/api/admin/login', '/api/wakefusion/v1/health', '/api/media/events']:
                    assert central(path)[0] == 403
                assert central('/api/control/home')[0] == 405
                assert commands == before_commands, 'Unauthorized traffic must not reach the motor'
                assert central('/api/status')[0] == 200 and len(central('/api/points')[1]) == 4
                assert api('/api/wakefusion/v1/health')[0] == 200, 'Host compatibility lost'
                if not silent:
                    for point, coordinate in [('p01', 1600), ('p02', 3200), ('p03', 4800), ('p04', 6400)]:
                        assert central(f'/api/control/points/{point}/activate', 'POST')[1]['accepted']
                        deadline = time.monotonic() + 5
                        while True:
                            state = central('/api/status')[1]
                            if state['currentPointId'] == point and state['targetPointId'] is None:
                                break
                            assert time.monotonic() < deadline
                            time.sleep(.02)
                        assert f'MOVE {coordinate}' in commands
                    # Start from home; verify a full video is awaited, using real
                    # packaged services and a local fake-controller acknowledgement.
                    assert central('/api/control/home', 'POST')[1]['success']
                    deadline = time.monotonic() + 5
                    while central('/api/status')[1]['currentPointId'] != 'p00':
                        assert time.monotonic() < deadline
                        time.sleep(.02)
                    assert central('/api/control/carousel/start', 'POST')[1]['accepted']
                    deadline = time.monotonic() + 5
                    while True:
                        state = central('/api/status')[1]
                        if state['currentPointId'] == 'p01' and state['targetPointId'] is None:
                            break
                        assert time.monotonic() < deadline
                        time.sleep(.02)
                    assert state['playbackState'] == 'playing'
                    assert central('/api/control/pause', 'POST')[1]['success']
                    assert central('/api/status')[1]['playbackState'] == 'paused'
                    assert central('/api/control/play', 'POST')[1]['success']
                    state = central('/api/status')[1]
                    api('/api/media/events', 'POST', {'sessionId': state['mediaSessionId'], 'revision': state['playbackRevision'], 'event': 'ended'})
                    deadline = time.monotonic() + 5
                    while central('/api/status')[1]['currentPointId'] != 'p02':
                        assert time.monotonic() < deadline
                        time.sleep(.02)
                    assert central('/api/control/carousel/stop', 'POST')[1]['accepted']
                    assert central('/api/control/stop', 'POST')[1]['success']
                    assert not central('/api/status')[1]['carouselMode']
                    # Restart the delivered executable with the same external
                    # config: a stored central key must not be rotated on upgrade/start.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    process.wait(timeout=10)
                    process = subprocess.Popen(['cmd.exe', '/d', '/c', 'start.bat'], cwd=work / 'app',
                        env={**os.environ, 'WAKEFUSION_APP_TOKEN': token}, stdout=log, stderr=log,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    deadline = time.monotonic() + 12
                    while True:
                        try:
                            if central('/api/status')[0] == 200:
                                break
                        except OSError:
                            pass
                        assert time.monotonic() < deadline
                        time.sleep(.05)
                    assert key_path.read_text('ascii').strip() == central_key
                assert not any('WATCH' in c or c == 'ZERO' for c in commands)
                print(json.dumps({'result': 'passed', 'silent': silent, 'version': health['version'],
                                  'udpCommands': commands, 'centralBearer': True, 'keyPreserved': not silent,
                                  'physicalControllerContacted': False}))
            finally:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                process.wait(timeout=10)
                server.shutdown()


if __name__ == '__main__':
    main()
