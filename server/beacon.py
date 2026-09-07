"""Decoder for Find My (offline-finding) BLE advertisements.

Single source of truth for this parsing, shared by the BLE listener
(server/listener.py) and the verification tool (tools/scan_tags.py). It
used to live in both, and the copies drifted.

Payload layout, as emitted by firmware-tag/main.go:

    [0]     0x12    payload type (registered device)
    [1]     0x19    payload length
    [2]             status byte; top nibble carries the battery level
    [3:25]          22 bytes of advertising key
    [25]            top two bits of the key's first byte
    [26]            battery percent — our firmware's addition; stock
                    go-haystack leaves this 0x00
"""

APPLE_ID = 0x004C          # BLE manufacturer-data company identifier

PAYLOAD_TYPE = 0x12
PAYLOAD_LENGTH = 0x19

# Status byte (payload[2]) top nibble -> Apple's four battery levels.
BATTERY_LEVELS = {0x10: "full", 0x40: "medium", 0x80: "low", 0xC0: "critical"}

PCT_INDEX = 26


def decode(payload):
    """Decode one advertisement payload.

    Returns {"batt_lvl": str|None, "batt_pct": int|None}, or None if this is
    not a Find My offline-finding frame.
    """
    if not payload or len(payload) < 3:
        return None
    if payload[0] != PAYLOAD_TYPE or payload[1] != PAYLOAD_LENGTH:
        return None

    # A percent of 0 means "not reported" (stock firmware), and anything
    # above 100 is another vendor's data in that byte, not a battery level.
    pct = payload[PCT_INDEX] if len(payload) > PCT_INDEX else 0
    return {
        "batt_lvl": BATTERY_LEVELS.get(payload[2] & 0xF0),
        "batt_pct": pct if 0 < pct <= 100 else None,
    }
