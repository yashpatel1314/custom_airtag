"""Tests for the Find My advertisement decoder.

This is the parsing at the heart of the system — every sighting flows
through it — and it was previously duplicated between server/listener.py
and tools/scan_tags.py with the two copies drifting apart.
"""

import beacon


def frame(status=0x10, pct=0, length=27):
    """Build a Find My offline-finding advertisement payload.

    Layout (see firmware-tag/main.go): type, length, status, 22 key bytes,
    key-prefix bits, then our battery-percent hint byte.
    """
    data = bytearray([0x12, 0x19, status] + [0x5A] * 23 + [pct])
    return bytes(data[:length])


def test_rejects_non_findmy_frames():
    assert beacon.decode(bytes([0x07, 0x19, 0x10])) is None   # wrong type
    assert beacon.decode(bytes([0x12, 0x0A, 0x10])) is None   # wrong length byte


def test_rejects_empty_and_short_payloads():
    for bad in (None, b"", b"\x12", bytes([0x12, 0x19])):
        assert beacon.decode(bad) is None


def test_decodes_battery_levels():
    for status, level in ((0x10, "full"), (0x40, "medium"),
                          (0x80, "low"), (0xC0, "critical")):
        assert beacon.decode(frame(status=status))["batt_lvl"] == level


def test_unknown_status_bits_give_no_level():
    assert beacon.decode(frame(status=0x20))["batt_lvl"] is None


def test_decodes_precise_percentage():
    assert beacon.decode(frame(pct=87))["batt_pct"] == 87
    assert beacon.decode(frame(pct=100))["batt_pct"] == 100
    assert beacon.decode(frame(pct=1))["batt_pct"] == 1


def test_zero_percent_byte_means_unknown():
    """Stock go-haystack firmware leaves the hint byte at 0x00."""
    assert beacon.decode(frame(pct=0))["batt_pct"] is None


def test_out_of_range_percentage_rejected():
    """Foreign Apple devices put unrelated data in that byte — a scan really
    did report '220%' before this was validated."""
    assert beacon.decode(frame(pct=220))["batt_pct"] is None
    assert beacon.decode(frame(pct=101))["batt_pct"] is None


def test_missing_hint_byte_is_tolerated():
    """A 26-byte stock frame has no percent byte at all."""
    decoded = beacon.decode(frame(pct=99, length=26))
    assert decoded is not None
    assert decoded["batt_lvl"] == "full"
    assert decoded["batt_pct"] is None
