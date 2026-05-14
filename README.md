# switch2controllerpc

**Use your Nintendo Switch 2 controllers as a regular PC gamepad.** Pair your Joy-Cons or Pro Controller 2 to Windows over Bluetooth and your PC sees them as an Xbox 360 or PlayStation 4 controller — so they Just Work in Steam, Game Pass, emulators, and most native PC games.

Includes high-precision gyro aiming, on-the-fly Joy-Con split / merge, and a button preview so you can verify every button works before booting a game.

## Will it work for me?

You need:

- A PC running **Windows 10 or 11** with Bluetooth (built in, or a USB Bluetooth dongle).
- A **Switch 2 Joy-Con, pair of Joy-Cons, or Pro Controller 2**.

You **do not** need a Switch console or a Nintendo Online account.

## Getting started (about 5 minutes)

### 1. Download

Grab the latest `switch2pc.exe` from the [Releases page](https://github.com/CareyScott/switch2controllerpc/releases). It's a single file — put it anywhere you like (Desktop, Downloads, a folder of your choice).

### 2. Run it

Double-click `switch2pc.exe`.

The first time you launch it, the app checks for [ViGEmBus](https://github.com/nefarius/ViGEmBus) — the virtual-gamepad driver that lets Windows see your controller as an Xbox or PS4 pad. If it's not installed yet:

- You'll see **one UAC prompt** asking to install it. Click yes.
- The installer runs automatically and the app finishes starting.

You won't see this prompt on later launches.

### 3. Connect a controller

The app window shows a "press button to pair" hint. What you do depends on whether this app has seen your controller before:

- **First time with this app** — Hold the small **Sync button** on the controller (recessed, on the side rail of a Joy-Con; on the top edge of the Pro Controller next to the USB-C port) until the player LEDs start flashing. The app pairs it and adds it to a player slot.
- **Already used it with this app before** — Just press any button on the controller. It reconnects automatically.

> **Important:** do **not** pair the controller through Windows Settings → Bluetooth. This app uses its own (faster, lower-latency) pairing path. If you previously paired the controller via Windows, remove it from Windows Bluetooth first, then sync it here.

That's it. The controller appears as a card at the top of the app window and is now usable as a gamepad in any game.

## The app window, explained

### Player cards (top of the window)

Each connected controller gets a card with a **live preview** of its inputs. Press any button on the physical controller and you'll see the matching button light up red on the diagram — handy for confirming every button works before you load a game.

Each card has:

- **✕** — disconnect this controller (the app keeps running so you can reconnect later).
- **Split / Merge** (when two Joy-Cons are connected) — combine the pair into one virtual gamepad, or split them into two single-player gamepads.
- **V / H** (on a single Joy-Con) — vertical hold (one hand) or horizontal hold (sideways, like a tiny NES pad).
- **L / R** (on combined Joy-Cons) — which Joy-Con's gyro the game receives.
- **Vibrate** — buzzes the controller. Useful for figuring out which physical controller is "player 1".

### General settings

- **Emulation: Xbox vs PS4** — pick what your controller pretends to be.
  - *Xbox* (default): looks like an Xbox 360 pad. Works in basically every PC game.
  - *PS4*: looks like a DualShock 4, with native motion sensing. Pick this for games that have proper PS4 / gyro support.
- **Layout: Xbox vs Switch** — Switch and Xbox have A/B/X/Y in different positions on the face.
  - *Xbox*: position-based. Pressing the bottom face button reports as A.
  - *Switch*: label-based. The button physically labeled A reports as A, even though it's in a different spot than an Xbox A. Pick this if you want what the controller says to match what the game shows.
- **Joy-Con Mouse** — turn this on to use a Joy-Con as a mouse by sliding it on a flat surface (it has an optical sensor on the rail).
- **Mouse Sens.** — how fast the mouse moves when you slide the Joy-Con.

### Gyro settings

The Switch 2 controllers have a gyroscope, which lets you aim by tilting the controller. This is *much* more precise than a thumbstick once you get used to it.

- **Mode**
  - *FPS* (yaw) — turning the controller left/right turns the camera. The setting for shooters.
  - *Steering* (roll) — tilting the controller works like a steering wheel. Good for racing games.
- **Sensitivity** — how fast the camera moves per degree of tilt.
- **Activation**
  - *Toggle* — press the gyro-trigger button once to enable aiming, again to disable.
  - *Hold* — only aim while you hold the trigger.
- **Stick Assist** — adds extra fine-tune from the right stick on top of gyro motion. Useful for quick 180s while gyro handles the precision.
- **Calibrate Gyro** — place the controller flat and still on a desk, then click. The 2-second countdown measures your controller's "resting" state so it doesn't drift. Do this once per controller; redo if you ever notice drift. Calibration is saved per controller (by MAC address) in `config.yaml`.

### Custom button mappings

Switch 2 controllers have buttons that PC games don't know about (GL/GR back buttons, Chat, the rail SR/SL on detached Joy-Cons, Home, Capture). Map them to whatever you like:

- **Pro Buttons** — the GL/GR back paddles on the Pro Controller, plus the Chat / C button.
- **Joy-Con Rail** — Left SR and Right SL (the rail buttons that face you when a Joy-Con is detached).
- **Shortcuts** — HOME and Capture. Map them to launch Steam Big Picture, the Xbox Game Bar, your Steam library, etc.

## Using it with Steam

Steam adds its own controller layer that can double-remap buttons on top of what this app sends. To stop that:

1. Open Steam → **Settings → Controller** → click **Show Advanced Settings**.
2. Turn on **Enable Steam Input for Xbox controllers**.
3. Set **PlayStation Controller Support** to **Enabled** (not "Enabled in Games w/o Support").

Now Steam passes through what this app sends without re-remapping.

## Troubleshooting

**Nothing happens when I press a button on the controller.**
- Make sure Bluetooth is actually turned on in Windows.
- If you previously paired the controller with Windows directly, open Settings → Bluetooth, remove it, and try again with the Sync button.
- Hold Sync until the LEDs flash — a quick tap doesn't trigger pairing mode.

**The controller pairs, then disconnects after a few seconds.**
- Another app might be grabbing it (Steam in controller-setup mode, BetterJoy, JoyToKey, etc.). Close those and restart switch2pc.
- The battery may be very low. Charge the controller for a few minutes and retry.

**Gyro slowly drifts when I'm not moving.**
- Click **Calibrate Gyro** with the controller flat and still on a desk.

**The ViGEmBus install failed or got skipped.**
- Download and install it manually from the [ViGEmBus releases page](https://github.com/nefarius/ViGEmBus/releases), then relaunch switch2pc.

**The window looks blurry or scaled weirdly.**
- The app sets itself DPI-aware on launch. If it still looks off, right-click `switch2pc.exe` → Properties → Compatibility → Change high DPI settings → "Override high DPI scaling behavior", set to "Application".

## Building from source

If you want to hack on the code:

```powershell
git clone https://github.com/CareyScott/switch2controllerpc
cd switch2controllerpc

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]

# Run from source
python -m switch2pc

# Build the .exe
.\scripts\build.ps1
# Output lands in dist\switch2pc.exe
```

Requires Python 3.11+ on Windows 10 or 11.

## How it works (technical sketch)

- `discoverer.py` uses [bleak](https://github.com/hbldh/bleak) to scan for Switch 2 Bluetooth LE advertisements (Nintendo manufacturer ID `0x0553`) and pair via GATT.
- `controller.py` parses the controller's input reports and drives vibration, LEDs, and calibration. A 1 kHz interpolation thread keeps mouse motion smooth even when reports arrive less often.
- `virtual_controller.py` uses [vgamepad](https://github.com/yannbouteiller/vgamepad) (over [ViGEmBus](https://github.com/nefarius/ViGEmBus)) to expose either an XInput Xbox 360 device or a DualShock 4 device to Windows.
- `bootstrap/vigem.py` checks for ViGEmBus on launch and offers to install it if missing.
- `gui.py` plus `preview.py` are the tkinter UI and the live-input preview canvas.

## About this fork

This repo started as a clean repackage of [TommyWabg/switch2-controllers-windows10-gyro](https://github.com/TommyWabg/switch2-controllers-windows10-gyro), which itself forked [Nadeflore/switch2-controllers](https://github.com/Nadeflore/switch2-controllers). The controller protocol code is upstream's work; this fork adds packaging and first-run UX:

- **First-run ViGEmBus bootstrap** — the app detects whether the driver is installed and runs the official installer with a single UAC prompt if not. No separate install step.
- **Standard Python project layout** (`src/`, `pyproject.toml`) so contributors can install with `pip install -e .[dev]`.
- **UTF-8 everywhere** (upstream `requirements.txt` was UTF-16 LE and tripped some tooling).
- **No leaked personal data** — the shipped default config has no MAC-address-keyed gyro calibration; each user calibrates their own controllers on first run.
- **CI release pipeline** that builds a signed-when-possible `.exe` on every tagged release.
- **License** — MIT, with attribution to both upstream authors.

## Credits

- [Nadeflore](https://github.com/Nadeflore) — original Switch 2 controller protocol reverse engineering.
- [TommyWabg](https://github.com/TommyWabg) — Windows 10/11 gyro fork that this repo is based on.
- [Nefarius](https://github.com/nefarius) — [ViGEmBus](https://github.com/nefarius/ViGEmBus), the kernel driver that makes virtual-controller emulation possible on Windows.
- [yannbouteiller](https://github.com/yannbouteiller) — [vgamepad](https://github.com/yannbouteiller/vgamepad) Python bindings.

## License

[MIT](LICENSE). See the LICENSE file for the attribution note on upstream code.
