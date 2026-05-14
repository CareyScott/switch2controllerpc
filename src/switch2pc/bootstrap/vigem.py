"""ViGEmBus driver bootstrap.

ViGEmBus is a Windows kernel-mode driver (signed by Nefarius) that vgamepad uses
to emulate Xbox 360 / DualShock 4 controllers. We can't bundle a kernel driver
inside our .exe (it has to be installed via a signed MSI with admin rights), so
on first launch we:

  1. Check whether ViGEmBus is already installed (registry + driver file).
  2. If not, ask the user (tkinter messagebox) for permission to install.
  3. Download the latest MSI from the official Nefarius GitHub releases.
  4. Run it elevated via ShellExecute "runas" verb. One UAC prompt, done.

If the user declines, we show a link to the manual installer and exit. If the
install fails (bad signature, no network, user cancels UAC), we surface the
error and let the user retry.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import urllib.request
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VIGEMBUS_RELEASES_API = "https://api.github.com/repos/nefarius/ViGEmBus/releases/latest"
VIGEMBUS_FALLBACK_URL = "https://github.com/nefarius/ViGEmBus/releases/latest"
VIGEMBUS_SERVICE_KEY = r"SYSTEM\CurrentControlSet\Services\ViGEmBus"
VIGEMBUS_DRIVER_PATH = r"C:\Windows\System32\drivers\ViGEmBus.sys"

USER_AGENT = "switch2controllerpc-bootstrap/0.1 (+https://github.com/CareyScott/switch2controllerpc)"


class ViGEmBusError(Exception):
    """Raised when the ViGEmBus driver can't be detected or installed."""


@dataclass
class _ReleaseAsset:
    name: str
    url: str
    size: int


def is_installed() -> bool:
    """Return True if the ViGEmBus driver appears to be installed on this machine.

    We check two independent signals (registry service entry and driver file)
    because each can lie on its own — a leftover registry key after a botched
    uninstall, or a `.sys` file from a manual copy that's not actually loaded.
    """
    if sys.platform != "win32":
        return False

    registry_present = False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, VIGEMBUS_SERVICE_KEY, 0, winreg.KEY_READ):
            registry_present = True
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"Registry probe for ViGEmBus failed: {e}")

    driver_present = os.path.exists(VIGEMBUS_DRIVER_PATH)

    if registry_present and driver_present:
        return True

    # Last resort: try importing vgamepad. This is more expensive but
    # catches the case where a driver upgrade left the registry stale.
    try:
        import vgamepad  # noqa: F401

        client = vgamepad.VX360Gamepad()
        del client
        return True
    except Exception as e:
        logger.info(f"vgamepad probe says ViGEmBus is not usable: {e}")
        return False


def _fetch_latest_release_asset() -> Optional[_ReleaseAsset]:
    """Look up the latest ViGEmBus release on GitHub and return the .msi asset."""
    req = urllib.request.Request(VIGEMBUS_RELEASES_API, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception as e:
        logger.error(f"Failed to fetch ViGEmBus release metadata: {e}")
        return None

    assets = data.get("assets", [])
    # Prefer the multi-arch .msi, fall back to anything ending in .msi.
    msi_assets = [a for a in assets if a.get("name", "").lower().endswith(".msi")]
    if not msi_assets:
        return None

    multiarch = [a for a in msi_assets if "x64" in a["name"].lower() and "arm64" in a["name"].lower()]
    pick = multiarch[0] if multiarch else msi_assets[0]
    return _ReleaseAsset(name=pick["name"], url=pick["browser_download_url"], size=pick.get("size", 0))


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)


def _run_elevated_msi(msi_path: Path) -> int:
    """Run msiexec elevated. Returns the process exit code (0 on success)."""
    import ctypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NO_CONSOLE = 0x00008000

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong),
            ("hIconOrMonitor", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    sei.lpVerb = "runas"
    sei.lpFile = "msiexec.exe"
    sei.lpParameters = f'/i "{msi_path}" /qb'
    sei.nShow = 1

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.GetLastError()
        # 1223 = ERROR_CANCELLED (user clicked No on UAC prompt)
        if err == 1223:
            raise ViGEmBusError("Installation cancelled at the UAC prompt.")
        raise ViGEmBusError(f"ShellExecuteEx failed (error {err}).")

    if not sei.hProcess:
        raise ViGEmBusError("Installer process handle is null.")

    WAIT_OBJECT_0 = 0
    WAIT_INFINITE = 0xFFFFFFFF
    wait_result = ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, WAIT_INFINITE)
    exit_code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(sei.hProcess)

    if wait_result != WAIT_OBJECT_0:
        raise ViGEmBusError("Wait on installer process failed.")
    return exit_code.value


def _prompt_install(asset_size_mb: float) -> bool:
    """Show a tkinter messagebox asking the user to confirm the install.

    Returns True if the user agreed.
    """
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        return messagebox.askyesno(
            title="switch2controllerpc — driver setup",
            message=(
                "This app needs the ViGEmBus virtual controller driver "
                "(by Nefarius) to emulate Xbox 360 / DualShock 4 controllers.\n\n"
                f"It isn't installed yet. Download and install it now "
                f"(~{asset_size_mb:.1f} MB)?\n\n"
                "You'll see one Windows admin prompt. The installer is the "
                "official signed release from "
                "https://github.com/nefarius/ViGEmBus/releases ."
            ),
        )
    finally:
        root.destroy()


def _show_error(message: str) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showerror("switch2controllerpc — setup error", message)
    finally:
        root.destroy()


def ensure_vigembus(*, prompt: bool = True) -> bool:
    """Make sure ViGEmBus is installed. Returns True if it is by the time we return.

    Raises ViGEmBusError on unrecoverable failures the caller should report.
    """
    if is_installed():
        logger.info("ViGEmBus already installed.")
        return True

    if not prompt:
        raise ViGEmBusError("ViGEmBus is not installed and prompting is disabled.")

    asset = _fetch_latest_release_asset()
    if asset is None:
        _show_error(
            "Could not reach github.com to download the ViGEmBus driver.\n\n"
            "Please install it manually from:\n"
            f"{VIGEMBUS_FALLBACK_URL}\n\n"
            "Then relaunch this app."
        )
        raise ViGEmBusError("Could not fetch ViGEmBus release metadata.")

    size_mb = asset.size / (1024 * 1024) if asset.size else 6.0
    if not _prompt_install(size_mb):
        raise ViGEmBusError("User declined ViGEmBus installation.")

    with tempfile.TemporaryDirectory(prefix="switch2pc-bootstrap-") as tmpdir:
        msi_path = Path(tmpdir) / asset.name
        logger.info(f"Downloading {asset.url} -> {msi_path}")
        try:
            _download(asset.url, msi_path)
        except Exception as e:
            _show_error(
                "Failed to download the ViGEmBus installer.\n\n"
                f"Error: {e}\n\n"
                f"You can install it manually from:\n{VIGEMBUS_FALLBACK_URL}"
            )
            raise ViGEmBusError(f"Download failed: {e}") from e

        logger.info("Running ViGEmBus installer (elevated)...")
        try:
            exit_code = _run_elevated_msi(msi_path)
        except ViGEmBusError:
            raise
        except Exception as e:
            raise ViGEmBusError(f"Installer launch failed: {e}") from e

        if exit_code != 0:
            _show_error(
                "The ViGEmBus installer exited with a non-zero code "
                f"({exit_code}). The driver may not have been installed.\n\n"
                "Try installing it manually from:\n"
                f"{VIGEMBUS_FALLBACK_URL}"
            )
            raise ViGEmBusError(f"Installer returned exit code {exit_code}.")

    if not is_installed():
        _show_error(
            "The installer finished but ViGEmBus still isn't detected.\n\n"
            "Try restarting Windows, then launching this app again."
        )
        raise ViGEmBusError("ViGEmBus still not detected after install.")

    logger.info("ViGEmBus installed successfully.")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        ensure_vigembus()
        print("ViGEmBus is installed.")
    except ViGEmBusError as e:
        print(f"Bootstrap failed: {e}", file=sys.stderr)
        sys.exit(1)
