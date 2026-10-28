# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['launch_habit_tracker.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PyQt6.sip'],
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
    [],
    exclude_binaries=True,
    name='Advent of Habit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Advent of Habit',
)

app = BUNDLE(
    coll,
    name='Advent of Habit.app',
    bundle_identifier='com.adventofhabit.tracker',
    info_plist={
        'LSMinimumSystemVersion': '10.15',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'LSUIElement': True,
    }
) 