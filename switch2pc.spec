# PyInstaller spec for switch2controllerpc.
#
# Build with:  pyinstaller switch2pc.spec
# Or run:      scripts/build.ps1
#
# Resources (icons, config template) live under src/switch2pc/resources and
# need to be packed at the same relative path inside the exe so get_resource()
# can find them via sys._MEIPASS.
# ruff: noqa
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

block_cipher = None

ROOT = os.path.abspath(os.path.dirname(SPEC))
SRC = os.path.join(ROOT, "src", "switch2pc")

datas = [
    (os.path.join(SRC, "resources"), "resources"),
]
# vgamepad ships native DLLs (ViGEm client) that need to be picked up.
binaries = collect_dynamic_libs("vgamepad")

a = Analysis(
    [os.path.join(SRC, "__main__.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "switch2pc.bootstrap.vigem",
        "winrt.windows.devices.bluetooth",
        "winrt.windows.devices.bluetooth.advertisement",
        "winrt.windows.devices.bluetooth.genericattributeprofile",
        "winrt.windows.devices.enumeration",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.storage.streams",
    ],
    hookspath=[],
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
    a.zipfiles,
    a.datas,
    [],
    name="switch2pc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SRC, "resources", "images", "icon.ico"),
)
