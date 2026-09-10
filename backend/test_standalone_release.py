"""Windows-only packaged standalone test. Opens and closes its own kiosk window.

An isolated runtime copy always uses mock; no physical hardware is contacted.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import psutil


def windows_for(pids):
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    windows = []

    @callback_type
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.right - rect.left > 100:
                windows.append((hwnd, rect))
        return True

    user32.EnumWindows(visit, 0)
    return windows


def main():
    ctypes.windll.user32.SetProcessDPIAware()
    source = Path(sys.argv[1]).resolve()
    project = Path(__file__).resolve().parents[1]
    assert json.loads((source / 'runtime/config/machine.json').read_text('utf-8'))['provider'] == 'udp'
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', 8000)) != 0, 'Close the previous service first'
    # Keep this generated fixture for inspection; Chromium may briefly hold profile locks on exit.
    work = Path(tempfile.mkdtemp(prefix='standalone-check-', dir=project / 'tmp'))
    shutil.copytree(source, work / 'app')
    machine_path = work / 'app/runtime/config/machine.json'
    machine = json.loads(machine_path.read_text('utf-8'))
    machine['provider'] = 'mock'
    machine_path.write_text(json.dumps(machine), encoding='utf-8')
    env = dict(os.environ)
    env.pop('WAKEFUSION_APP_TOKEN', None)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    browser_pids = set()
    with (work / 'startup.log').open('wb') as log:
        process = subprocess.Popen(['cmd.exe', '/d', '/c', 'start-standalone.bat'], cwd=work / 'app',
                                   env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                children = psutil.Process(process.pid).children(recursive=True)
                browsers = [p for p in children if p.name().lower() == 'msedge.exe']
                browser_pids = {p.pid for p in browsers}
                windows = windows_for(browser_pids)
                if windows:
                    break
                time.sleep(.2)
            else:
                raise AssertionError('No standalone browser window; inspect ' + str(work))
            main_browser = next(p for p in browsers if '--kiosk' in p.cmdline())
            arguments = main_browser.cmdline()
            assert '--edge-kiosk-type=fullscreen' in arguments
            assert 'http://127.0.0.1:8000/' in arguments
            assert any(str(work) in arg and arg.startswith('--user-data-dir=') for arg in arguments)
            time.sleep(1)
            hwnd, rect = max(windows_for(browser_pids), key=lambda item: (item[1].right-item[1].left)*(item[1].bottom-item[1].top))
            screen_width = ctypes.windll.user32.GetSystemMetrics(0)
            screen_height = ctypes.windll.user32.GetSystemMetrics(1)
            assert rect.right - rect.left >= screen_width - 2 and rect.bottom - rect.top >= screen_height - 2, 'Window is not fullscreen'
            with opener.open('http://127.0.0.1:8000/') as response:
                assert response.status == 200
            with opener.open('http://127.0.0.1:8000/api/status') as response:
                assert json.load(response)['motorState'] == 'arrived'
            # A duplicate launch must fail rather than opening another browser or reusing Host.
            duplicate = subprocess.run([str(work / 'app/runtime/slider-screen-service.exe'), '--standalone'],
                env=env, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.returncode == 1 and b'Port 8000 is already in use' in duplicate.stdout
            user32 = ctypes.windll.user32
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # Close only this test's kiosk window (WM_CLOSE).
            assert process.wait(timeout=15) == 0, 'Closing the kiosk must exit standalone service'
            with socket.socket() as probe:
                assert probe.connect_ex(('127.0.0.1', 8000)) != 0, 'Standalone service still owns port 8000'
            print(json.dumps({'result': 'passed', 'fullscreen': [screen_width, screen_height],
                'automaticBrowser': True, 'duplicateRejected': True, 'closeStopsService': True,
                'physicalControllerContacted': False, 'fixture': str(work)}, ensure_ascii=True))
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
