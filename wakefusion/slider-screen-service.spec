# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH).resolve().parent
datas = [(str(project_root / 'backend' / 'static'), 'backend/static')]
binaries = []
hiddenimports = []
for package in ('uvicorn', 'fastapi'):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports

a = Analysis(
    [str(project_root / 'backend' / 'portable_launcher.py')],
    pathex=[str(project_root / 'backend')],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='slider-screen-service', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True,
    console=True, disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True,
    upx_exclude=[], name='slider-screen-service',
)
