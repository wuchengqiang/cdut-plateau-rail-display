"""Create a frontend-only V1.1.7 patch and update a local bundle with a backup."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle')
    args = parser.parse_args()
    bundle = Path(args.bundle).resolve()
    if bundle.parent != (ROOT / 'release').resolve():
        raise ValueError('Expected a bundle directly inside release')
    info = json.loads((bundle / 'release-info.json').read_text('utf-8'))
    if info['version'] != '1.1.7':
        raise ValueError('This patch targets V1.1.7 only')
    source = ROOT / 'backend/static'
    relative = Path('app/runtime/_internal/backend/static')
    target = bundle / relative
    if not (target / 'index.html').is_file():
        raise ValueError('Missing previous frontend')
    refs = re.findall(r'(?:src|href)="/([^"?]+)"', (source / 'index.html').read_text('utf-8'))
    files = [Path('index.html'), *map(Path, refs)]
    for name in files:
        if not (source / name).is_file() or not (source / name).resolve().is_relative_to(source.resolve()):
            raise ValueError(f'Invalid asset: {name}')
    patch = ROOT / 'release/滑轨屏-V1.1.7-播控栏补丁-20260917.zip'
    backup = ROOT / 'release/滑轨屏-V1.1.7-补丁前页面备份-20260917.zip'
    if patch.exists() or backup.exists():
        raise FileExistsError('Refusing to overwrite a previous patch or backup')
    manifest = {'patchId': 'compact-controls-20260917', 'baseVersion': '1.1.7',
                'files': {str(relative / name).replace('\\', '/'): hashlib.sha256((source / name).read_bytes()).hexdigest() for name in files}}
    with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as archive:
        for file in target.rglob('*'):
            if file.is_file():
                archive.write(file, file.relative_to(bundle))
    with zipfile.ZipFile(patch, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(source / name, relative / name)
        archive.write(ROOT / 'packaging/UI补丁使用说明.md', '更新说明.md')
        archive.writestr('ui-patch-info.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(patch) as archive:
        assert archive.testzip() is None
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    # Assets first, entry point last; never delete site files/configuration.
    for name in [*map(Path, refs), Path('index.html')]:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target / name)
    (bundle / 'ui-patch-info.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
    print(json.dumps({'patch': str(patch), 'bytes': patch.stat().st_size, 'backup': str(backup), 'updatedBundle': str(bundle)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
