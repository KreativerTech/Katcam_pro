# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# DLLs de OpenCV
binaries = collect_dynamic_libs('cv2')

# Imports “ocultos” necesarios
hiddenimports = [
    'tzlocal',               # zona horaria
    'PIL._tkinter_finder',   # evita problemas con ImageTk
]
# Submódulos completos
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('cv2')
# (opcional, por robustez) incluye submódulos de tzlocal
hiddenimports += collect_submodules('tzlocal')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    # incluye todo assets (subcarpetas) en el bundle
    datas=[('assets\\*', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KatcamPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # sin consola
    windowed=True,      # app de ventana (Tkinter)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/katcam_multi.ico',   # <-- icono del EXE
)
