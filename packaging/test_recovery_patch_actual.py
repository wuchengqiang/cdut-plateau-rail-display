"""Install the real patch into a COPY of the baseline, preserving the original."""
from __future__ import annotations
import json
import re
from pathlib import Path
import shutil
from test_recovery_patch import snapshot, run

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'release/WakeFusion滑轨屏-中控巡展版-V1.1.7-20260913'
PATCH = ROOT / 'release/滑轨屏-V1.1.7-播放恢复与异常日志补丁-20261102-r2'
TEST = ROOT / 'tmp/recovery-patch-field-verification-20261102-r2'


def main():
    if TEST.exists():
        raise FileExistsError('Refusing to overwrite prior actual-package verification')
    before_base = snapshot(BASE)
    app = TEST / 'installed/app'
    shutil.copytree(BASE / 'app', app)
    for name, data in {
        'runtime/config/remote-control.key': b'fixture-only-control-key-not-a-real-secret-1234567890',
        'runtime/content/videos/patch-test-sentinel.mp4': b'fixture-video-must-not-be-overwritten',
        'runtime/browser-profile/Preferences': b'fixture-browser-state-must-not-change',
    }.items():
        destination = app / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    original = snapshot(app)
    code, output = run(PATCH, app)
    if code != 0:
        raise RuntimeError(output)
    changed = json.loads((PATCH / 'patch-manifest.json').read_text('utf-8'))['files']
    expected_changes = {'runtime/' + item['path']: item['sha256'] for item in changed}
    after = snapshot(app)
    for name, checksum in after.items():
        assert checksum == expected_changes.get(name, original.get(name)), name
    assert set(original).issubset(after)
    assert all(after[name] == checksum for name, checksum in expected_changes.items())
    # Exercise actual EXE/base_library/static rollback on a separate installation.
    rollback_app = TEST / 'rollback/app'
    shutil.copytree(BASE / 'app', rollback_app)
    rollback_before = snapshot(rollback_app)
    code, output = run(PATCH, rollback_app)
    assert code == 0, output
    code, output = run(PATCH, rollback_app, '-Rollback')
    assert code == 0, output
    assert snapshot(rollback_app) == rollback_before
    # Simulate the original UI generation: the current CSS/JS asset names do
    # not exist. The r2 patch must provide every current index.html dependency.
    legacy_app = TEST / 'legacy-ui/app'
    def without_current_assets(directory, names):
        return {'assets'} if Path(directory).as_posix().endswith('/_internal/backend/static') else set()
    shutil.copytree(BASE / 'app', legacy_app, ignore=without_current_assets)
    legacy_static = legacy_app / 'runtime/_internal/backend/static'
    (legacy_static / 'assets').mkdir()
    (legacy_static / 'assets/legacy.css').write_text('body { color: white; }', encoding='utf-8')
    (legacy_static / 'assets/legacy.js').write_text('/* old field UI */', encoding='utf-8')
    (legacy_static / 'index.html').write_text('<link href="/assets/legacy.css"><script src="/assets/legacy.js"></script>', encoding='utf-8')
    legacy_before = snapshot(legacy_app)
    code, output = run(PATCH, legacy_app)
    assert code == 0, output
    legacy_after = snapshot(legacy_app)
    for name, checksum in legacy_before.items():
        if not name.startswith('runtime/_internal/') and name != 'runtime/slider-screen-service.exe':
            assert legacy_after[name] == checksum, name
    refs = re.findall(r'(?:src|href)="/([^"?]+)"', (legacy_static / 'index.html').read_text('utf-8'))
    assert refs and all((legacy_static / name).is_file() for name in refs)
    assert (legacy_static / 'assets/legacy.css').is_file() and (legacy_static / 'assets/legacy.js').is_file()
    code, output = run(PATCH, legacy_app, '-Rollback')
    assert code == 0, output
    assert snapshot(legacy_app) == legacy_before
    assert snapshot(BASE) == before_base, 'Actual baseline must not change'
    report = {'passed': True, 'installedAppForExecutableTests': str(app),
              'changedProgramFiles': list(expected_changes), 'configurationMediaKeyUnchanged': True,
              'actualProgramRollbackPassed': True, 'baselineModified': False, 'exeStarted': False}
    report['legacyUiWithoutNewAssetsInstallAndRollbackPassed'] = True
    report['legacyUiNewIndexAssetsVerified'] = refs
    (TEST / 'installation-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
