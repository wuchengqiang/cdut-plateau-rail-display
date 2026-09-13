"""Isolated gateway and launcher tests; temporary loopback sockets and mock motor only."""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from starlette.responses import JSONResponse
from app.remote_control import ListenerRouter, RemoteSettings, load_network_settings


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []

        async def local_app(scope, receive, send):
            self.calls.append((scope['method'], scope['path']))
            await JSONResponse({'success': True})(scope, receive, send)

        self.settings = RemoteSettings(True, '0.0.0.0', 8001,
            (ipaddress.IPv4Network('192.168.1.0/24'),), ('http://tablet.test:9000',), 'a' * 43)
        self.router = ListenerRouter(local_app, 8000, self.settings)

    async def request(self, path='/api/status', method='GET', *, peer='192.168.1.120', port=8001, key='a' * 43, extra=None):
        headers = {'host': '192.168.1.105:8001', **(extra or {})}
        if key is not None:
            headers['authorization'] = f'Bearer {key}'
        scope = {'type': 'http', 'method': method, 'path': path, 'scheme': 'http', 'http_version': '1.1',
                 'server': ('127.0.0.1' if port == 8000 else '192.168.1.105', port),
                 'client': (peer, 12345), 'headers': [(k.encode(), v.encode()) for k, v in headers.items()]}
        messages = []

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        async def send(message):
            messages.append(message)

        await self.router(scope, receive, send)
        return messages[0]['status'], dict(messages[0]['headers'])

    async def test_all_documented_actions_and_reads(self):
        for path in ['/api/status', '/api/points']:
            self.assertEqual((await self.request(path))[0], 200)
        for path in [*[f'/api/control/points/p0{i}/activate' for i in range(1, 5)],
                     *[f'/api/control/{name}' for name in ['play', 'pause', 'stop', 'home', 'carousel/start', 'carousel/stop', 'emergency-stop']]]:
            self.assertEqual((await self.request(path, 'POST'))[0], 200)
        self.assertEqual(len(self.calls), 13)

    async def test_keys_peer_filter_and_forwarded_header_spoofing(self):
        for key in [None, '', '2468', 'host-token', 'wrong-key']:
            status, headers = await self.request('/api/control/play', 'POST', key=key)
            self.assertEqual(status, 401)
            self.assertEqual(headers[b'cache-control'], b'no-store')
        status, _ = await self.request(peer='10.20.30.40', extra={'x-forwarded-for': '192.168.1.120', 'forwarded': 'for=127.0.0.1'})
        self.assertEqual(status, 403)
        status, _ = await self.request(key=None, extra={'host': '127.0.0.1:8000', 'x-forwarded-for': '127.0.0.1'})
        self.assertEqual(status, 401)  # Header cannot change the accepted socket.
        self.assertEqual(self.calls, [])

    async def test_no_admin_host_feedback_assets_or_get_motion(self):
        for path in ['/', '/docs', '/openapi.json', '/content/videos/p01.mp4', '/api/display-config',
                     '/api/admin/login', '/api/admin/reload', '/api/admin/hardware/ping',
                     '/api/wakefusion/v1/health', '/api/wakefusion/v1/actions/0/execute', '/api/media/events',
                     '/api/control/scene/p01', '/api/control/points/p01/activate/extra']:
            self.assertEqual((await self.request(path, 'POST'))[0], 403)
        self.assertEqual((await self.request('/api/control/home'))[0], 405)
        self.assertEqual(self.calls, [])
        self.assertEqual((await self.request('/api/admin/login', 'POST', peer='127.0.0.1', port=8000, key=None))[0], 200)
        self.assertEqual(len(self.calls), 1)  # Local listener retains the existing app checks.

    async def test_cors_is_explicit_and_not_an_auth_bypass(self):
        good = 'http://tablet.test:9000'
        self.assertEqual((await self.request(extra={'origin': 'https://untrusted.test'}))[0], 403)
        code, headers = await self.request(extra={'origin': good})
        self.assertEqual(code, 200)
        self.assertEqual(headers[b'access-control-allow-origin'], good.encode())
        self.assertNotIn(b'access-control-allow-credentials', headers)
        code, headers = await self.request('/api/control/play', 'OPTIONS', key=None,
            extra={'origin': good, 'access-control-request-method': 'POST', 'access-control-request-headers': 'authorization,content-type'})
        self.assertEqual(code, 204)
        self.assertEqual((await self.request('/api/control/play', 'POST', key=None, extra={'origin': good}))[0], 401)
        self.assertEqual((await self.request('/api/admin/login', 'OPTIONS', key=None,
            extra={'origin': good, 'access-control-request-method': 'POST'}))[0], 403)

    async def test_remote_websocket_denied_even_with_key(self):
        output = []

        async def send(message):
            output.append(message)

        await self.router({'type': 'websocket', 'path': '/ws', 'server': ('192.168.1.105', 8001)}, None, send)
        self.assertEqual(output, [{'type': 'websocket.close', 'code': 1008}])


class SettingsTests(unittest.TestCase):
    def test_defaults_validation_and_persistent_installation_key(self):
        with tempfile.TemporaryDirectory(prefix='rail-network-config-') as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            app_path = root / 'config/app.json'
            remote_path = root / 'config/remote-control.json'
            app_path.write_text(json.dumps({'apiHost': '127.0.0.1', 'apiPort': 8000}), encoding='utf-8')
            self.assertFalse(load_network_settings(root)[2].enabled)
            raw = {'enabled': True, 'host': '0.0.0.0', 'port': 8001, 'allowedClients': ['192.168.1.0/24'], 'allowedOrigins': []}
            remote_path.write_text(json.dumps(raw), encoding='utf-8-sig')
            first = load_network_settings(root)[2]
            self.assertEqual(first.api_key, load_network_settings(root)[2].api_key)
            self.assertGreaterEqual(len(first.api_key), 32)
            self.assertNotIn(first.api_key, repr(first))
            self.assertNotIn(first.api_key, remote_path.read_text('utf-8-sig'))
            for override in [{'port': 8000}, {'port': True}, {'port': 0}, {'allowedClients': []},
                             {'allowedClients': ['0.0.0.0/0']}, {'allowedOrigins': ['*']},
                             {'allowedOrigins': ['http://tablet.test/path']}, {'enabled': 'true'}]:
                remote_path.write_text(json.dumps({**raw, **override}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_network_settings(root)
            remote_path.write_text(json.dumps(raw), encoding='utf-8')
            (root / 'config/remote-control.key').write_text('2468', encoding='ascii')
            with self.assertRaises(ValueError):
                load_network_settings(root)
            app_path.write_text(json.dumps({'apiHost': '0.0.0.0', 'apiPort': 8000}), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_network_settings(root)


class LauncherTests(unittest.TestCase):
    def test_busy_remote_listener_aborts_before_runtime_import(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='rail-port-conflict-') as directory, socket.socket() as occupied, socket.socket() as local_probe:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen(1)
            local_probe.bind(('127.0.0.1', 0))
            local_port, remote_port = local_probe.getsockname()[1], occupied.getsockname()[1]
            local_probe.close()
            root = Path(directory)
            (root / 'config').mkdir()
            (root / 'config/app.json').write_text(json.dumps({'apiHost': '127.0.0.1', 'apiPort': local_port}), encoding='utf-8')
            (root / 'config/remote-control.json').write_text(json.dumps({
                'enabled': True, 'host': '127.0.0.1', 'port': remote_port, 'allowedClients': ['127.0.0.1'],
            }), encoding='utf-8')
            # Deliberately no machine configuration: reaching app import would fail.
            launcher = ('import os,sys; from pathlib import Path; import portable_launcher as entry; '
                        'entry.external_root=lambda: Path(os.environ["RAIL_TEST_ROOT"]); '
                        'sys.argv=["test", "--no-browser"]; sys.exit(entry.main())')
            result = subprocess.run([sys.executable, '-c', launcher], cwd=project / 'backend',
                env={**os.environ, 'RAIL_TEST_ROOT': str(root), 'PYTHONIOENCODING': 'utf-8'}, capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f'Port {remote_port} is already in use'.encode(), result.stdout)
            self.assertNotIn(b'machine.json', result.stdout)
            with socket.socket() as released:
                released.bind(('127.0.0.1', local_port))

    def test_real_dual_listener_with_mock_and_no_browser(self):
        project = Path(__file__).resolve().parents[1]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with tempfile.TemporaryDirectory(prefix='rail-remote-api-') as directory:
            root = Path(directory)
            shutil.copytree(project / 'config', root / 'config', ignore=shutil.ignore_patterns('*.key'))
            shutil.copytree(project / 'backend/static', root / 'backend/static')
            (root / 'content/videos').mkdir(parents=True)
            (root / 'content/videos/p01.mp4').write_bytes(b'contract-fixture')
            probes = [socket.socket(), socket.socket()]
            for probe in probes:
                probe.bind(('127.0.0.1', 0))
            local_port, remote_port = [probe.getsockname()[1] for probe in probes]
            for probe in probes:
                probe.close()
            app_config = json.loads((root / 'config/app.json').read_text('utf-8'))
            app_config['apiPort'] = local_port
            (root / 'config/app.json').write_text(json.dumps(app_config), encoding='utf-8')
            (root / 'config/remote-control.json').write_text(json.dumps({
                'enabled': True, 'host': '127.0.0.1', 'port': remote_port,
                'allowedClients': ['127.0.0.1/32'], 'allowedOrigins': ['http://tablet.test:9000'],
            }), encoding='utf-8')
            machine_path = root / 'config/machine.json'
            machine = json.loads(machine_path.read_text('utf-8'))
            machine.update(provider='mock', mockMoveDurationMs=30)
            machine_path.write_text(json.dumps(machine), encoding='utf-8')
            launcher = ('import os,sys; from pathlib import Path; import portable_launcher as entry; '
                        'entry.external_root=lambda: Path(os.environ["RAIL_TEST_ROOT"]); '
                        'sys.argv=["test", "--no-browser"]; sys.exit(entry.main())')
            process = subprocess.Popen([sys.executable, '-c', launcher], cwd=project / 'backend',
                env={**os.environ, 'RAIL_TEST_ROOT': str(root), 'WAKEFUSION_APP_TOKEN': 'test-host-token', 'PYTHONIOENCODING': 'utf-8'},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            def request(path, method='GET', key=None, port=remote_port, extra=None):
                headers = {**(extra or {})}
                if key is not None:
                    headers['Authorization'] = f'Bearer {key}'
                query = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method, headers=headers)
                try:
                    with opener.open(query, timeout=2) as response:
                        return response.status, response.read(), dict(response.headers)
                except urllib.error.HTTPError as error:
                    return error.code, error.read(), dict(error.headers)

            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    try:
                        if request('/api/status', port=local_port)[0] == 200:
                            break
                    except urllib.error.URLError:
                        pass
                    time.sleep(.05)
                else:
                    self.fail('Test launcher did not start')
                key = (root / 'config/remote-control.key').read_text('ascii').strip()
                self.assertEqual(request('/api/status')[0], 401)
                self.assertEqual(request('/api/status', key='test-host-token')[0], 401)
                self.assertEqual(request('/api/status', key=key)[0], 200)
                self.assertEqual(request('/api/status', key=key, extra={'X-Forwarded-For': '10.20.30.40'})[0], 200)
                for path in ['/', '/api/admin/login', '/api/media/events', '/api/wakefusion/v1/health']:
                    self.assertEqual(request(path, key=key)[0], 403)
                self.assertEqual(request('/', port=local_port)[0], 200)
                self.assertEqual(request('/api/wakefusion/v1/health', key='test-host-token', port=local_port)[0], 200)
                self.assertEqual(request('/api/wakefusion/v1/health', key=key, port=local_port)[0], 401)
                for point in ['p01', 'p02', 'p03', 'p04']:
                    self.assertTrue(json.loads(request(f'/api/control/points/{point}/activate', 'POST', key)[1])['accepted'])
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        state = json.loads(request('/api/status', key=key)[1])
                        if state['currentPointId'] == point and state['targetPointId'] is None:
                            break
                        time.sleep(.01)
                    else:
                        self.fail(f'Mock never arrived at {point}')
                self.assertEqual(request('/api/control/carousel/start', 'POST', key)[0], 200)
                self.assertEqual(request('/api/control/carousel/stop', 'POST', key)[0], 200)
                self.assertEqual(request('/api/control/home', 'POST', key)[0], 200)
                time.sleep(.08)
                self.assertEqual(json.loads(request('/api/status', key=key)[1])['currentPointId'], 'p00')
                self.assertEqual(request('/api/control/play', 'POST', key)[0], 200)
                self.assertEqual(request('/api/control/pause', 'POST', key)[0], 200)
                self.assertEqual(request('/api/control/stop', 'POST', key)[0], 200)
                self.assertEqual(request('/api/control/emergency-stop', 'POST', key)[0], 200)
                self.assertEqual(request('/api/control/home', key=key)[0], 405)
                self.assertEqual(request('/api/control/home', 'POST', extra={'Host': f'127.0.0.1:{local_port}', 'X-Forwarded-For': '127.0.0.1'})[0], 401)
                code, _, _ = request('/api/control/play', 'OPTIONS', extra={'Origin': 'http://tablet.test:9000',
                    'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization'})
                self.assertEqual(code, 204)
            finally:
                process.terminate()
                try:
                    output = process.communicate(timeout=5)[0]
                except subprocess.TimeoutExpired:
                    process.kill()
                    output = process.communicate(timeout=5)[0]
                if (root / 'config/remote-control.key').exists():
                    self.assertNotIn((root / 'config/remote-control.key').read_text('ascii').strip().encode(), output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
