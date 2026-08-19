"""Derive a tag's BLE MAC address from its advertisement key, for registering
in server/tags.json.

The firmware sets the tag's static random address to the first 6 bytes of the
28-byte advertisement key, with the first byte's top two bits forced to 1
(BLE static-address requirement) — see firmware-tag/main.go.

Usage:
  python tools/mac_from_key.py <base64-advertisement-key>
  python tools/mac_from_key.py findmy/keys/tag-04.keys
"""

import base64
import re
import sys
from pathlib import Path


def key_from_text(text: str) -> bytes:
    """Find the advertisement key in free-form .keys file text: prefer a
    base64 token on a line mentioning 'adv', else any token that decodes
    to 28 bytes."""
    candidates = []
    for line in text.splitlines():
        for tok in re.findall(r"[A-Za-z0-9+/=]{30,}", line):
            try:
                raw = base64.b64decode(tok, validate=True)
            except Exception:
                continue
            if len(raw) == 28:
                candidates.append(("adv" in line.lower(), raw))
    if not candidates:
        raise SystemExit("no 28-byte base64 advertisement key found")
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    arg = sys.argv[1]
    if Path(arg).exists():
        key = key_from_text(Path(arg).read_text())
    else:
        key = base64.b64decode(arg)
        if len(key) != 28:
            raise SystemExit(f"advertisement key must be 28 bytes, got {len(key)}")
    mac = bytes([key[0] | 0xC0]) + key[1:6]
    print(":".join(f"{b:02X}" for b in mac))


if __name__ == "__main__":
    main()
