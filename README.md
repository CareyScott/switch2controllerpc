# switch2controllerpc

Use Nintendo Switch 2 Joy-cons and the Pro Controller 2 as PC gamepads on Windows 10/11, with high-precision gyro mouse aiming, DualShock 4 / Xbox 360 emulation, and on-the-fly layout switching.

## Why this fork

This project is a clean repackage of [TommyWabg/switch2-controllers-windows10-gyro](https://github.com/TommyWabg/switch2-controllers-windows10-gyro), which in turn forked [Nadeflore/switch2-controllers](https://github.com/Nadeflore/switch2-controllers). Differences here:

- **First-run ViGEmBus bootstrap.** The app detects whether the [ViGEmBus driver](https://github.com/nefarius/ViGEmBus) is installed; if it isn't, it downloads the official installer and runs it with a single UAC prompt. No separate driver install step.
- **Standard Python project layout** (`src/`, `pyproject.toml`) so contributors can install with `pip install -e .[dev]`.
- **UTF-8 everywhere** (the upstream `requirements.txt` was UTF-16 LE and tripped some tooling).
- **No leaked personal data.** The shipped default config has no MAC-address-keyed gyro calibration; each user calibrates their own controllers on first run.
- **CI release pipeline** that builds a signed-when-possible `.exe` on every tagged release.
- **License.** MIT, with attribution to both upstream authors. (Upstream projects had no explicit license at the time of forking.)

The controller protocol code is upstream's work; the bootstrap, packaging, and project hygiene are new here.

## Quick start (end users)

1. Go to [Releases](https://github.com/CareyScott/switch2controllerpc/releases) and download `switch2pc.exe`.
2. Double-click it. If ViGEmBus isn't installed, you'll get one UAC prompt — accept it and the driver installs automatically.
3. Press any button on a paired Switch 2 controller, or hold the Sync button on an unpaired one.
4. The controller appears in the app window. Tweak settings in the bottom panel.

**Do not** pair the controller manually in Windows Bluetooth settings — the app uses GATT auto-discovery. If you previously paired it via Windows, remove it first.

## Steam configuration

The app emulates either Xbox 360 or DualShock 4 (toggle from the settings panel). To stop Steam Input from double-remapping buttons:

1. Steam → Settings → Controller → Show Advanced Settings.
2. Enable **"Enable Steam Input for Xbox controllers"**.
3. Set **"PlayStation Controller Support"** to **Enabled** (not "Enabled in Games w/o Supports").

## Gyro calibration

To eliminate drift:

1. Place the controller flat and still.
2. Click **Calibrate Gyro** in the settings panel.
3. Wait for the 2-second countdown to finish. Bias is saved per-controller (keyed by MAC address) in `config.yaml`.

## Features

Carried over from upstream:

- Dynamic Xbox 360 ↔ DS4 emulation toggle (DS4 mode exposes native motion to Steam Input and DS4-aware games).
- 1000 Hz interpolation loop for smooth gyro and Joy-con mouse output.
- Gyro mouse mode (FPS aiming) and gyro steering wheel mode (racing games).
- Joy-con mouse mode (slide the Joy-con on a flat surface) with a toggle in the UI.
- On-the-fly Nintendo / Xbox layout switching.
- Split/merge of paired Joy-cons without restart.
- Vertical / Horizontal hold for single Joy-con use.
- Per-player vibration test button for identifying which controller is which.
- Capture button mapped to `Win+PrtScn`.
- Per-controller disconnect button in the UI.
- Configurable extra-button mapping (`GL`, `GR`, `SL_R`, `SR_L`, `C`).
- Stick assist (right stick adds to gyro aim).
- ThroughputOptimized BLE connection parameter request on Windows 10/11 for lower input latency.

## Building from source

Requires Python 3.11+ on Windows 10/11.

```powershell
# Clone
git clone https://github.com/CareyScott/switch2controllerpc
cd switch2controllerpc

# Create a venv and install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]

# Run from source
python -m switch2pc

# Build the .exe
.\scripts\build.ps1
# Output lands in dist\switch2pc.exe
```

## How it works (short version)

- `discoverer.py` uses [bleak](https://github.com/hbldh/bleak) to scan for Switch 2 Bluetooth LE advertisements (Nintendo manufacturer ID `0x0553`) and pair / reconnect via GATT.
- `controller.py` parses input reports, handles vibration, LEDs, calibration, and runs a 1 kHz interpolation thread for mouse motion.
- `virtual_controller.py` uses [vgamepad](https://github.com/yannbouteiller/vgamepad) (which wraps [ViGEmBus](https://github.com/nefarius/ViGEmBus)) to expose either an XInput Xbox 360 device or a DualShock 4 device to Windows.
- `bootstrap/vigem.py` checks for ViGEmBus before any of the above runs, and offers to install it if missing.
- `gui.py` is the tkinter UI.

## Credits

- [Nadeflore](https://github.com/Nadeflore) — original Switch 2 controller protocol reverse engineering.
- [TommyWabg](https://github.com/TommyWabg) — Windows 10/11 gyro fork that this repo is based on.
- [Nefarius](https://github.com/nefarius) — [ViGEmBus](https://github.com/nefarius/ViGEmBus), the kernel driver that makes virtual-controller emulation possible on Windows.
- [yannbouteiller](https://github.com/yannbouteiller) — [vgamepad](https://github.com/yannbouteiller/vgamepad) Python bindings.

## License

[MIT](LICENSE). See the LICENSE file for the attribution note on upstream code.
