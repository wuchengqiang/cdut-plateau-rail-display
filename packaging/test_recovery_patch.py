"""Exercise update/rollback only in disposable synthetic app directories."""
from __future__ import annotations
import hashlib
import ctypes
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patch_builder', ROOT / 'packaging/build_recovery_patch.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def put(root, name, data):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)


def snapshot(root):
    return {p.relative_to(root).as_posix(): builder.digest(p) for p in root.rglob('*') if p.is_file() and 'patch-backups' not in p.parts}


def run(patch, app, *flags):
    result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(patch / 'apply-patch.ps1'), '-AppDirectory', str(app), '-Yes', *flags],
                            capture_output=True, timeout=45)
    return result.returncode, result.stdout.decode('utf-8', errors='replace') + result.stderr.decode('utf-8', errors='replace')


def main():
    folder = Path(tempfile.mkdtemp(prefix='patch-installer-test-', dir=ROOT / 'tmp'))
    base = folder / 'base'
    app = base / 'app'
    fresh = folder / 'fresh'
    prior = {
        'slider-screen-service.exe': b'fake-old-program',
        '_internal/python311.dll': b'unchanged-runtime',
        '_internal/backend/static/index.html': b'old-html',
        '_internal/backend/static/assets/old.js': b'old-ui-resource',
        '_internal/backend/static/assets/shared.css': b'current-css',
    }
    for name, data in prior.items():
        put(app / 'runtime', name, data)
    for name, data in {
        'app.json': b'{"appId":"cdut-slider-screen","type":"service"}',
        'start.bat': b'user-start-script',
        'runtime/config/machine.json': b'field-udp-settings',
        'runtime/config/remote-control.key': b'field-secret-not-in-patch',
        'runtime/config/points.json': b'field-points',
        'runtime/content/videos/p03.mp4': b'field-video',
        'runtime/browser-profile/Preferences': b'field-browser-settings',
    }.items():
        put(app, name, data)
    put(base, 'release-info.json', json.dumps({'version': '1.1.7', 'exeSha256': builder.digest(app / 'runtime/slider-screen-service.exe')}).encode())
    for name, data in {'slider-screen-service.exe': b'fake-new-program',
                       '_internal/python311.dll': b'unchanged-runtime',
                       '_internal/backend/static/index.html': b'new-html',
                       '_internal/backend/static/assets/shared.css': b'current-css',
                       '_internal/backend/static/assets/new.js': b'new-ui-resource'}.items():
        put(fresh, name, data)
    patch = folder / 'patch-V1.1.7-test'
    result = builder.build(base, fresh, patch, 'recovery-test')
    assert Path(result['patch']).name == 'patch-V1.1.7-test.zip'
    assert result['changedFiles'] == 4 and result['unchangedFilesReused'] == 1, result
    built_manifest = json.loads((patch / 'patch-manifest.json').read_text('utf-8'))
    assert not any(name.startswith('_internal/backend/static/') for name in built_manifest['requiredUnchangedFiles'])
    assert (patch / 'apply-patch.ps1').read_bytes().startswith(b'\xef\xbb\xbf')
    assert b'\r\n' in (patch / '安装补丁.bat').read_bytes()
    for file in (patch / 'payload').rglob('*'):
        if file.is_file():
            assert builder.allowed(file.relative_to(patch / 'payload').as_posix())
    before = snapshot(app)
    code, output = run(patch, app)
    assert code == 0, output
    after = snapshot(app)
    assert after['runtime/slider-screen-service.exe'] == builder.digest(fresh / 'slider-screen-service.exe')
    for name, checksum in before.items():
        if name not in {'runtime/slider-screen-service.exe', 'runtime/_internal/backend/static/index.html'}:
            assert after[name] == checksum, name
    assert 'runtime/_internal/backend/static/assets/old.js' in after
    code, output = run(patch, app)
    assert code == 1 and snapshot(app) == after, 'Duplicate update must be refused'
    code, output = run(patch, app, '-Rollback')
    assert code == 0, output
    assert snapshot(app) == before, 'Rollback must restore exact prior files, preserving field data'
    # A changed baseline EXE must fail before any backup or program mutation.
    wrong = folder / 'wrong/app'
    shutil.copytree(app, wrong, ignore=shutil.ignore_patterns('patch-backups'))
    put(wrong, 'runtime/slider-screen-service.exe', b'unknown-version')
    wrong_before = snapshot(wrong)
    code, output = run(patch, wrong)
    assert code == 1 and snapshot(wrong) == wrong_before
    assert not (wrong / 'patch-backups').exists()
    # A locked HTML file fails after the new JS was copied: installation must
    # remove that new JS and restore the complete previous program automatically.
    locked = folder / 'locked/app'
    shutil.copytree(app, locked, ignore=shutil.ignore_patterns('patch-backups'))
    locked_before = snapshot(locked)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(locked / 'runtime/_internal/backend/static/index.html'),
                                0x80000000, 1, None, 3, 0, None)
    assert handle not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
    try:
        code, output = run(patch, locked)
        assert code == 1, output
        assert snapshot(locked) == locked_before, output
        state = json.loads((locked / 'patch-backups/recovery-test/state.json').read_text('utf-8'))
        assert state['status'] == 'installation-failed-restored', output
    finally:
        kernel.CloseHandle(handle)
    # Malformed payload path cannot target site settings.
    malicious = folder / 'invalid-patch'
    shutil.copytree(patch, malicious)
    manifest = json.loads((malicious / 'patch-manifest.json').read_text('utf-8'))
    manifest['files'][0]['path'] = '../config/machine.json'
    (malicious / 'patch-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    code, output = run(malicious, wrong)
    assert code == 1 and snapshot(wrong) == wrong_before
    print(json.dumps({'passed': True, 'fixture': str(folder), 'checks': ['delta-only', 'utf8-bom/ascii-crlf',
        'configuration-video-key-preserved', 'old-ui-resources-preserved', 'backup-rollback-exact',
        'duplicate-refused', 'wrong-version-refused', 'locked-file-automatic-rollback', 'path-traversal-refused']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
