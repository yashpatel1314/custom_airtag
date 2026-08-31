"""Generate the PWA app icons — a beacon mark: solid dot with two rings.

Pure stdlib (no Pillow) so it runs anywhere. Rerun after changing colours:
  python tools/make_icons.py
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "server" / "static" / "icons"
BG = (18, 33, 46)       # deep navy
FG = (255, 255, 255)

# Ring geometry as fractions of the icon's width, all inside the middle 80%
# so a maskable icon never crops the mark.
DOT = 0.10
RINGS = ((0.22, 0.26), (0.34, 0.38))


def pixels(size):
    c = (size - 1) / 2
    for y in range(size):
        row = []
        for x in range(size):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5 / size
            on = d <= DOT or any(lo <= d <= hi for lo, hi in RINGS)
            row.append(FG if on else BG)
        yield row


def write_png(path, size):
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px)
                   for row in pixels(size))

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))
    print(f"wrote {path.name} ({size}x{size})")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        write_png(OUT / f"icon-{size}.png", size)
