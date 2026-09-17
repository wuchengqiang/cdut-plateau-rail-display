"""Build the portable Web-service bundle; never include installation-specific keys.

Prepare: python packaging/build_release.py prepare
After isolated executable tests: python packaging/build_release.py archive <bundle-directory>
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"})


def digest(path: Path) -> str:
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def source_version() -> str:
    tree = ast.parse((ROOT / 'backend/app/main.py').read_text('utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'SERVICE_VERSION' for target in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError('Missing service version')


def exclude_video_files(directory: str, names: list[str]) -> set[str]:
    """Keep the generic green package compact and free of site-owned media."""
    return {name for name in names if (Path(directory) / name).suffix.lower() in VIDEO_EXTENSIONS}


def prepare() -> Path:
    version = source_version()
    wakefusion = json.loads((ROOT / 'config/wakefusion.json').read_text('utf-8'))
    if wakefusion['version'] != version:
        raise RuntimeError('Version mismatch')
    date = datetime.now().strftime('%Y%m%d')
    bundle = ROOT / 'release' / f'WakeFusion滑轨屏-中控巡展版-V{version}-{date}'
    if bundle.exists() or (bundle.parent / f'{bundle.name}.zip').exists():
        raise FileExistsError(f'Refusing to overwrite existing delivery: {bundle}')
    (ROOT / 'tmp').mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='release-build-', dir=ROOT / 'tmp'))
    subprocess.run(['npm.cmd', 'run', 'build'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--console',
        '--name', 'slider-screen-service', '--distpath', str(work / 'dist'), '--workpath', str(work / 'work'),
        '--specpath', str(work), '--paths', str(ROOT / 'backend'),
        '--add-data', f'{ROOT / "backend/static"};backend/static', '--collect-all', 'uvicorn', '--collect-all', 'fastapi',
        str(ROOT / 'backend/portable_launcher.py')], cwd=ROOT, check=True)
    staging = work / 'bundle'
    app = staging / 'app'
    runtime = app / 'runtime'
    shutil.copytree(work / 'dist/slider-screen-service', runtime)
    shutil.copytree(ROOT / 'config', runtime / 'config', ignore=shutil.ignore_patterns('*.key', '*.tmp'))
    (runtime / 'config/admin.json').write_text(json.dumps({'password': '2468'}, indent=2) + '\n', encoding='utf-8')
    shutil.copytree(ROOT / 'content', runtime / 'content', ignore=exclude_video_files)
    shutil.copy2(ROOT / 'wakefusion/app.json', app / 'app.json')
    for name in ['start.bat', 'start-standalone.bat']:
        text = (ROOT / 'wakefusion' / name).read_text('ascii')
        (app / name).write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii'))
    shutil.copy2(ROOT / 'packaging/部署步骤.md', staging / '部署步骤.md')
    for name in ['中控平板接入交接-青藏高原滑轨屏.md', '自动巡展规则与配置.md', '4号点位竖屏界面设计说明.md']:
        shutil.copy2(ROOT / 'docs' / name, staging / name)
    if list(staging.rglob('*.key')):
        raise RuntimeError('Installation key must never be included in a generic bundle')
    machine = json.loads((runtime / 'config/machine.json').read_text('utf-8'))
    remote = json.loads((runtime / 'config/remote-control.json').read_text('utf-8'))
    points = json.loads((runtime / 'config/points.json').read_text('utf-8'))['points']
    assert machine['provider'] == 'udp' and (machine['network']['host'], machine['network']['port']) == ('127.0.0.1', 53500)
    assert remote['enabled'] and remote['port'] == 8001
    assert [point['positionMm'] for point in points] == [0, 1600, 3200, 4800, 6400]
    assert not any(path.suffix.lower() in VIDEO_EXTENSIONS for path in (runtime / 'content').rglob('*') if path.is_file())
    info = {'version': version, 'createdAt': datetime.now().astimezone().isoformat(timespec='seconds'),
            'kind': 'portable-web-service', 'localPort': 8000, 'centralPort': 8001,
            'requiresBearer': True, 'installationKeyIncluded': False, 'videosIncluded': False,
            'exeSha256': digest(runtime / 'slider-screen-service.exe'),
            'videos': {path.name: {'bytes': path.stat().st_size, 'sha256': digest(path)} for path in (runtime / 'content/videos').glob('*.mp4')}}
    (staging / 'release-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    bundle.parent.mkdir(exist_ok=True)
    staging.rename(bundle)
    print(f'PREPARED: {bundle}', flush=True)
    return bundle


def archive(directory: str) -> None:
    bundle = Path(directory).resolve()
    if bundle.parent != (ROOT / 'release').resolve() or not (bundle / 'release-info.json').is_file():
        raise ValueError('Only a prepared bundle directly inside release may be archived')
    verification = json.loads((bundle / 'verification.json').read_text('utf-8'))
    if not verification.get('passed') or verification.get('physicalControllerContacted') is not False:
        raise ValueError('Isolated verification must pass before archiving')
    # Edge creates this cache on the first standalone run. It contains no
    # application data and must never bloat or personalize a delivery ZIP.
    browser_profile = bundle / 'app' / 'runtime' / 'browser-profile'
    if browser_profile.exists():
        shutil.rmtree(browser_profile)
    files = sorted(path for path in bundle.rglob('*') if path.is_file())
    if any(path.suffix.lower() == '.key' for path in files):
        raise ValueError('Remove installation credentials from the generic delivery before archiving')
    target = bundle.parent / f'{bundle.name}.zip'
    if target.exists():
        raise FileExistsError('Refusing to overwrite an existing ZIP')
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in files:
            archive.write(path, path.relative_to(bundle))
    with zipfile.ZipFile(target) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError(f'Archive CRC verification failed: {bad_file}')
    checksum = digest(target)
    (target.parent / f'{target.name}.sha256').write_text(f'{checksum}  {target.name}\n', encoding='utf-8')
    print(json.dumps({'archive': str(target), 'bytes': target.stat().st_size, 'sha256': checksum}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'archive'])
    parser.add_argument('directory', nargs='?')
    args = parser.parse_args()
    prepare() if args.action == 'prepare' else archive(args.directory)
