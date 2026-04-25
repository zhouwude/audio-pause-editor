# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Electron 版 Python Sidecar (--onefile)"""
block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPEC)) if 'SPEC' in dir() else os.path.dirname(os.path.abspath(__file__))
# ROOT = D:\CustomProgram\audio-pause-editor-electron\sidecar
# project dir is one level up
PROJECT_ROOT = os.path.dirname(ROOT)
BACKEND = os.path.join(PROJECT_ROOT, 'backend')
FFMPEG_DIR = os.path.join(PROJECT_ROOT, 'ffmpeg')

datas = [
    (BACKEND, 'backend'),
]

if os.path.isdir(FFMPEG_DIR):
    datas.append((FFMPEG_DIR, 'ffmpeg'))

a = Analysis(
    ['sidecar_main.py'],
    pathex=[ROOT, BACKEND],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'python_multipart',
        'pydantic',
        'pydantic_core',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='audio-pause-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
