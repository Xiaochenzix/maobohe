from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=collect_dynamic_libs('live2d') + collect_dynamic_libs('glfw'),
    datas=[('app.ico', '.'), ('assets/bongo', 'assets/bongo'), ('assets/models', 'assets/models'), ('assets/runtime', 'assets/runtime')] + collect_data_files('live2d'),
    hiddenimports=collect_submodules('live2d.v3') + ['OpenGL.platform.win32'],
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
    name='猫薄荷',
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
    version='version_info.txt',
    icon=['app.ico'],
)
