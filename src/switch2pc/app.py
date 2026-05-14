"""Entry point: run the ViGEmBus bootstrap, then launch the controller GUI."""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Bootstrap must run before any vgamepad / ViGEmBus-touching import.
    from .bootstrap import ensure_vigembus, ViGEmBusError

    try:
        ensure_vigembus()
    except ViGEmBusError as e:
        logger.error(f"ViGEmBus bootstrap failed: {e}")
        return 2

    # Only safe to import the GUI (and through it, vgamepad) once the driver is in place.
    from .gui import ControllerWindow

    window = ControllerWindow()
    window.init_interface()
    window.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
