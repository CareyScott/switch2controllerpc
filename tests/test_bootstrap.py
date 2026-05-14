"""Tests for the ViGEmBus bootstrap module.

These are intentionally narrow — we don't actually install drivers or fetch
network resources. We just verify the detection plumbing and the public API
shape so a CI run catches accidental breakage.
"""
from __future__ import annotations

import sys

import pytest

# Bootstrap module needs winreg.
if sys.platform != "win32":
    pytest.skip("ViGEmBus bootstrap is Windows-only.", allow_module_level=True)

from switch2pc.bootstrap import ViGEmBusError, ensure_vigembus, is_installed  # noqa: E402
from switch2pc.bootstrap import vigem as vigem_module  # noqa: E402


def test_public_api_is_exported():
    assert callable(ensure_vigembus)
    assert callable(is_installed)
    assert issubclass(ViGEmBusError, Exception)


def test_is_installed_returns_a_bool():
    # We can't know what the CI runner has, but the function must not blow up
    # and must return a bool.
    result = is_installed()
    assert isinstance(result, bool)


def test_ensure_vigembus_raises_when_prompt_disabled_and_driver_missing(monkeypatch):
    monkeypatch.setattr(vigem_module, "is_installed", lambda: False)
    with pytest.raises(ViGEmBusError):
        ensure_vigembus(prompt=False)


def test_ensure_vigembus_no_op_when_already_installed(monkeypatch):
    monkeypatch.setattr(vigem_module, "is_installed", lambda: True)
    assert ensure_vigembus() is True
