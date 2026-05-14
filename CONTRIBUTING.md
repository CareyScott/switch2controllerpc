# Contributing

Bug reports and PRs welcome. A few practical notes:

## Setup

```powershell
git clone https://github.com/CareyScott/switch2controllerpc
cd switch2controllerpc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Run from source:

```powershell
python -m switch2pc
```

Run tests + lint:

```powershell
pytest
ruff check src tests
```

Build the .exe:

```powershell
.\scripts\build.ps1
```

## Style

- Python 3.11+, type hints encouraged but not required for short helpers.
- `ruff` for linting/formatting (config in `pyproject.toml`).
- Keep public modules importable on non-Windows for testability where possible — the win32-specific imports should be lazy inside functions when realistic.

## What's hard to change

- The Switch 2 BLE protocol code (`controller.py`, parts of `discoverer.py`) is the result of reverse engineering by [Nadeflore](https://github.com/Nadeflore) and changes here without an actual controller to test against are dangerous. Open an issue first if you want to touch packet parsing.
- The DS4 report layout (`vigem_commons.py`) mirrors ViGEm's C structs — don't drift from upstream.

## Reporting bugs

Please include:

- Your Windows version (`winver`).
- Which controllers you've connected (Joy-con L/R, Pro Controller 2, NSO GameCube).
- Whether ViGEmBus was already installed or the bootstrap had to install it.
- The log lines printed in the console window if you ran from source, or the contents of `config.yaml` next to the exe if relevant.
