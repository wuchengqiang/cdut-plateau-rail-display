"""Run source and delivered-EXE regressions, record evidence before ZIP delivery."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def main():
    bundle = Path(sys.argv[1]).resolve()
    if bundle.parent != (ROOT / 'release').resolve() or not (bundle / 'release-info.json').is_file():
        raise ValueError('Only a prepared release bundle may be verified')
    checks = [
        ['node', 'frontend/test-media-controller.mjs'],
        *[[sys.executable, f'backend/{name}.py'] for name in [
            'test_remote_control', 'test_carousel', 'test_content_config', 'test_services',
            'test_motion_playback', 'test_initial_media', 'test_udp_motor', 'test_wakefusion']],
        [sys.executable, 'backend/test_udp_release.py', str(bundle / 'app')],
        [sys.executable, 'backend/test_udp_release.py', str(bundle / 'app'), 'silent'],
    ]
    results = []
    for command in checks:
        print('VERIFY: ' + ' '.join(command[1:]), flush=True)
        started = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                text=True, encoding='utf-8', capture_output=True, timeout=180)
        results.append({'command': command[1:], 'exitCode': result.returncode,
                        'seconds': round(time.monotonic() - started, 2),
                        'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            print(result.stdout + result.stderr, flush=True)
            break
        print('PASS', flush=True)
    report = {'passed': len(results) == len(checks) and all(item['exitCode'] == 0 for item in results),
              'verifiedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
              'physicalControllerContacted': False, 'packagedExeTested': True,
              'browserVisualTested': False, 'checks': results}
    (bundle / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not report['passed']:
        raise SystemExit(1)
    print(f'All {len(checks)} checks passed; physical hardware not contacted.', flush=True)


if __name__ == '__main__':
    main()
