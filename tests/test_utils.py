"""Tests for pure functions in switch2pc.utils.

Anything that touches win32api / vgamepad / bleak can't run in CI without a
real Switch controller plus ViGEmBus, so we only exercise the pure helpers.
"""
from __future__ import annotations

import pytest

# Importing switch2pc.utils transitively imports config, which imports win32api.
# On Windows CI runners this is fine; skip if win32api isn't available.
pytest.importorskip("win32api")

from switch2pc.utils import (  # noqa: E402
    convert_mac_string_to_value,
    decodes,
    decodeu,
    get_stick_xy,
    reverse_bits,
    signed_looping_difference_16bit,
    to_hex,
)


def test_to_hex_formats_each_byte_as_two_hex_chars():
    assert to_hex(b"\x00\x0f\xab\xff") == "00 0f ab ff"


def test_decodeu_is_little_endian_unsigned():
    assert decodeu(b"\x01\x00") == 1
    assert decodeu(b"\x00\x01") == 256
    assert decodeu(b"\xff\xff") == 65535


def test_decodes_is_little_endian_signed():
    assert decodes(b"\xff\xff") == -1
    assert decodes(b"\x00\x80") == -32768
    assert decodes(b"\xff\x7f") == 32767


def test_convert_mac_string_to_value_parses_colon_separated_hex():
    assert convert_mac_string_to_value("00:00:00:00:00:01") == 1
    assert convert_mac_string_to_value("01:00:00:00:00:00") == 0x010000000000


def test_get_stick_xy_packs_two_12bit_values_into_3_bytes():
    # x = 0xABC, y = 0xDEF -> packed little-endian = BC FA DE
    x, y = get_stick_xy(b"\xbc\xfa\xde")
    assert x == 0xABC
    assert y == 0xDEF


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (10, 20, 10),       # forward wrap-free
        (20, 10, -10),      # backward, no wrap
        (65530, 5, 11),     # forward across 16-bit boundary
        (5, 65530, -11),    # backward across 16-bit boundary
        (0, 32768, -32768), # at the half-point chooses the negative direction
    ],
)
def test_signed_looping_difference_16bit_handles_wraparound(a, b, expected):
    assert signed_looping_difference_16bit(a, b) == expected


@pytest.mark.parametrize(
    "value,bits,expected",
    [
        (0b0001, 4, 0b1000),
        (0b1010, 4, 0b0101),
        (0b11110000, 8, 0b00001111),
        (0, 4, 0),
    ],
)
def test_reverse_bits(value, bits, expected):
    assert reverse_bits(value, bits) == expected
