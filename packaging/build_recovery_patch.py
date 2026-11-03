"""Build a hash-delta runtime patch. Never modify the baseline delivery."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXE = 'slider-screen-service.exe'


def digest(file: Path) -> str:
    with file.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def allowed(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return bool(parts and '\\' not in name and ':' not in name and not name.startswith('/')
                and all(p not in ('', '.', '..') for p in name.split('/'))
                and (name == EXE or (len(parts) > 1 and parts[0] == '_internal'))
                and not any(p.lower() in {'config', 'content', 'browser-profile', 'logs', 'patch-backups'} for p in parts)
                and PurePosixPath(name).suffix.lower() not in {'.key', '.mp4', '.webm', '.mov', '.mkv', '.avi'})


def build(base: Path, fresh: Path, output: Path, patch_id: str) -> dict:
    base, fresh, output = base.resolve(), fresh.resolve(), output.resolve()
    archive_path = output.parent / (output.name + '.zip')
    if output.exists() or archive_path.exists():
        raise FileExistsError('Refusing to overwrite an existing patch')
    if not patch_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in patch_id):
        raise ValueError('Invalid patch ID')
    info = json.loads((base / 'release-info.json').read_text('utf-8-sig'))
    if info['version'] != '1.1.7':
        raise ValueError('Expected V1.1.7 baseline')
    original = base / 'app/runtime'
    base_hash = digest(original / EXE)
    if base_hash != info['exeSha256'].lower():
        raise ValueError('Baseline EXE differs from its release manifest')
    if not (fresh / EXE).is_file() or not (fresh / '_internal/backend/static/index.html').is_file():
        raise ValueError('Fresh PyInstaller runtime/static files missing')
    changed, requirements = [], {}
    for file in sorted(fresh.rglob('*')):
        if file.is_symlink():
            raise ValueError('Symlinks are not allowed in the build')
        if not file.is_file():
            continue
        relative = file.relative_to(fresh).as_posix()
        if not allowed(relative):
            raise ValueError('Non-program file in fresh runtime: ' + relative)
        checksum = digest(file)
        prior = original / relative
        # The local baseline already has the 2026-09-17 UI patch. A field app
        # may still have the original September UI, with different asset names.
        # Ship all current static assets rather than requiring a prior UI patch.
        if not relative.startswith('_internal/backend/static/') and prior.is_file() and digest(prior) == checksum:
            requirements[relative] = checksum
        else:
            changed.append({'path': relative, 'sha256': checksum, 'bytes': file.stat().st_size})
    if not any(entry['path'] == EXE for entry in changed):
        raise ValueError('Recovery patch must contain the newly built backend EXE')
    output.mkdir(parents=True)
    for entry in changed:
        destination = output / 'payload' / entry['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fresh / entry['path'], destination)
    manifest = {'schema': 'rail.runtime-delta-patch/v1', 'patchId': patch_id, 'baseVersion': '1.1.7',
                'appId': 'cdut-slider-screen', 'createdAt': datetime.now().astimezone().isoformat(timespec='seconds'),
                'baseExeSha256': base_hash, 'newExeSha256': digest(fresh / EXE),
                'files': changed, 'requiredUnchangedFiles': requirements,
                'preserves': ['config', 'content', 'browser-profile', 'app.json', 'start.bat', 'start-standalone.bat'],
                'deletesProgramFiles': False}
    (output / 'patch-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name in ['apply-patch.ps1', '安装补丁.bat', '回滚补丁.bat', '使用说明.txt']:
        source = ROOT / 'packaging/recovery-patch' / name
        if name.endswith('.bat'):
            data = source.read_text('ascii').replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii')
        else:
            data = source.read_text('utf-8-sig').replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8-sig')
        (output / name).write_bytes(data)
    target = archive_path
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(output.rglob('*')):
            if file.is_file():
                archive.write(file, file.relative_to(output))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP verification failed')
        for item in changed:
            if hashlib.sha256(archive.read('payload/' + item['path'])).hexdigest() != item['sha256']:
                raise ValueError('ZIP payload hash mismatch')
    return {'patch': str(target), 'bytes': target.stat().st_size, 'sha256': digest(target),
            'changedFiles': len(changed), 'payloadBytes': sum(f['bytes'] for f in changed),
            'unchangedFilesReused': len(requirements), 'baselineModified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('runtime', type=Path)
    parser.add_argument('--base', type=Path, default=ROOT / 'release/WakeFusion滑轨屏-中控巡展版-V1.1.7-20260913')
    parser.add_argument('--output', type=Path, default=ROOT / 'release/滑轨屏-V1.1.7-播放恢复与异常日志补丁-20261102-r2')
    parser.add_argument('--patch-id', default='media-recovery-logs-20261102-r2')
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.runtime, args.output, args.patch_id), ensure_ascii=False, indent=2))
