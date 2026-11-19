#!/usr/bin/env python3
"""Draws the Avatar element animations for the nice!view as 68x68 1-bit PBM
frames: air, water, fire, earth, and the Avatar state. Every animation loops
seamlessly. Run it again after changing a drawing; it writes ../art/<name>/.

    python3 make_elements.py [--sheet preview.png]
"""

import math
import os
import struct
import sys
import zlib

SIZE = 68
FRAMES = 12
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "..", "art")


class Canvas:
    def __init__(self):
        self.px = [[0] * SIZE for _ in range(SIZE)]

    def set(self, x, y, v=1):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < SIZE and 0 <= y < SIZE:
            self.px[y][x] = v

    def disc(self, cx, cy, r, v=1):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.set(x, y, v)

    def ring(self, cx, cy, r, w=1.0, v=1):
        for y in range(int(cy - r - w - 1), int(cy + r + w + 2)):
            for x in range(int(cx - r - w - 1), int(cx + r + w + 2)):
                d = math.hypot(x - cx, y - cy)
                if abs(d - r) <= w / 2:
                    self.set(x, y, v)

    def line(self, x0, y0, x1, y1, w=1.0, v=1):
        steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for i in range(steps + 1):
            t = i / steps
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if w <= 1:
                self.set(x, y, v)
            else:
                self.disc(x, y, w / 2, v)

    def polyline(self, pts, w=1.0, v=1):
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], w, v)

    def polygon(self, pts, v=1):
        ys = [p[1] for p in pts]
        for y in range(max(0, int(min(ys))), min(SIZE, int(max(ys)) + 1)):
            xs = []
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                for x in range(int(math.ceil(a)), int(math.floor(b)) + 1):
                    self.set(x, y, v)

    def rect(self, x, y, w, h, v=1):
        for yy in range(int(y), int(y + h)):
            for xx in range(int(x), int(x + w)):
                self.set(xx, yy, v)


def phase(f):
    return 2 * math.pi * f / FRAMES


def air(f):
    """A three-armed swirl spinning a third of a turn per loop."""
    c = Canvas()
    spin = phase(f) / 3
    for arm in range(3):
        base = spin + arm * 2 * math.pi / 3
        pts = []
        for i in range(60):
            t = i / 59
            theta = base + t * 2.6 * math.pi
            r = 2 + t * 24
            pts.append((34 + r * math.cos(theta), 34 + r * math.sin(theta)))
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            w = 1.2 + 2.6 * (i / len(pts))
            c.line(a[0], a[1], b[0], b[1], w)
    c.disc(34, 34, 3)
    # Gusts circling the swirl.
    for k in range(3):
        a0 = -spin * 2 + k * 2 * math.pi / 3
        pts = [(34 + 31 * math.cos(a0 + s * 0.05), 34 + 31 * math.sin(a0 + s * 0.05)) for s in range(12)]
        c.polyline(pts, 1)
    return c


def water(f):
    """Rolling waves under a crescent moon."""
    c = Canvas()
    t = phase(f)
    # Moon: a disc with a bite out of it.
    c.disc(50, 13, 8)
    c.disc(54, 11, 7, 0)
    for layer, (y0, amp, k, speed, w) in enumerate(
        [(30, 3.0, 2, 1, 1.4), (40, 4.0, 1, -1, 2.0), (51, 5.0, 2, 1, 2.6)]
    ):
        pts = []
        for x in range(-2, SIZE + 3):
            y = y0 + amp * math.sin(2 * math.pi * k * x / SIZE + speed * t + layer)
            pts.append((x, y))
        c.polyline(pts, w)
        if layer == 2:
            # Fill under the front wave with a falling stripe pattern.
            for x, y in pts:
                for yy in range(int(y) + 3, SIZE):
                    if (yy + int(x) // 3 + f) % 4 == 0:
                        c.set(x, yy)
    # Spray drops riding the front crest.
    for d in range(3):
        x = (d * 23 + f * 68 / FRAMES) % SIZE
        y = 51 + 5 * math.sin(2 * math.pi * 2 * x / SIZE + t + 2) - 6 - 2 * math.sin(t * 2 + d)
        c.disc(x, y, 1.2)
    return c


def fire(f):
    """A flickering flame: solid outside, hollow middle, solid core, with embers."""
    c = Canvas()
    t = phase(f)

    def flame(scale, bottom, height, offset):
        left, right = [], []
        for i in range(height + 1):
            y = bottom - i
            u = i / height
            # Teardrop: wide near the base, a point at the top.
            half = scale * math.sin(math.pi * min(1.0, u * 1.15)) ** 0.8 * (1 - u) ** 0.35
            sway = (u ** 1.5) * (4 * math.sin(t + u * 3 + offset) + 2 * math.sin(2 * t + u * 5))
            half *= 1 + 0.12 * math.sin(3 * t + u * 7 + offset)
            left.append((34 + sway - half, y))
            right.append((34 + sway + half, y))
        return left + right[::-1]

    c.polygon(flame(21, 64, 56, 0))
    c.polygon(flame(14, 63, 40, 1), 0)
    c.polygon(flame(7, 62, 24, 2))
    for e in range(5):
        u = ((f / FRAMES) + e / 5) % 1
        x = 34 + 18 * math.sin(e * 2.3 + u * 4) * (0.5 + u)
        y = 50 - u * 50
        if u > 0.25:
            c.disc(x, y, 1.0 if u > 0.7 else 1.5)
    return c


def earth(f):
    """Rock pillars earthbending up out of the ground in turn."""
    c = Canvas()
    t = phase(f)
    ground = 60
    c.rect(0, ground, SIZE, 2)
    for x in range(0, SIZE, 3):
        c.set(x, ground + 4)
        c.set(x + 1, ground + 6)
    pillars = [(6, 16, 0.0), (26, 16, 2.1), (46, 16, 4.2)]
    for x, w, p in pillars:
        rise = max(0.0, math.sin(t + p))
        h = int(4 + 40 * rise)
        top = ground - h
        # Outline with a chipped top and cracks.
        c.rect(x, top, w, h)
        c.rect(x + 2, top + 2, w - 4, h - 2, 0)
        c.set(x, top, 0)
        c.set(x + w - 1, top, 0)
        c.line(x + 3, top + 2, x + 6, top + 7)
        c.line(x + w - 4, top + h * 0.5, x + w - 7, top + h * 0.5 + 6)
        for yy in range(top + 4, ground, 4):
            c.set(x + 5 + (yy // 4) % 5, yy)
        # Pebbles kicked up while it's rising.
        if 0.1 < rise < 0.95 and math.cos(t + p) > 0:
            k = 1 - rise
            c.disc(x - 2 - 4 * k, top - 3 - 6 * k, 1.2)
            c.disc(x + w + 1 + 4 * k, top - 1 - 8 * k, 1.0)
    return c


def avatar(f):
    """Aang's arrow, with the four elements circling it."""
    c = Canvas()
    t = phase(f)
    # The arrow: a shaft and a head pointing down.
    c.rect(31, 14, 6, 26)
    c.polygon([(21, 36), (47, 36), (34, 54)])
    c.ring(34, 34, 31, 1.2)
    glyph_r = 26
    for k in range(4):
        a = t + k * math.pi / 2 - math.pi / 2
        gx, gy = 34 + glyph_r * math.cos(a), 34 + glyph_r * math.sin(a)
        c.disc(gx, gy, 6, 0)
        if k == 0:  # air: a curl
            c.polyline([(gx + 3 * math.cos(s / 3) * (1 - s / 24), gy + 3 * math.sin(s / 3) * (1 - s / 24)) for s in range(20)], 1.2)
        elif k == 1:  # water: two waves
            for dy in (-1.5, 1.5):
                c.polyline([(gx - 4 + i, gy + dy + math.sin(i * 1.4)) for i in range(9)], 1)
        elif k == 2:  # fire: a small flame
            c.polygon([(gx, gy - 5), (gx + 3.5, gy + 3), (gx - 3.5, gy + 3)])
        else:  # earth: a square stone
            c.rect(gx - 3, gy - 3, 7, 7)
            c.rect(gx - 1, gy - 1, 3, 3, 0)
    return c


ANIMATIONS = {"air": air, "water": water, "fire": fire, "earth": earth, "avatar": avatar}


def write_pbm(path, canvas):
    rows = bytearray()
    for y in range(SIZE):
        byte, bits = 0, 0
        for x in range(SIZE):
            byte = (byte << 1) | canvas.px[y][x]
            bits += 1
            if bits == 8:
                rows.append(byte)
                byte, bits = 0, 0
        if bits:
            rows.append(byte << (8 - bits))
    with open(path, "wb") as out:
        out.write(b"P4\n%d %d\n" % (SIZE, SIZE))
        out.write(bytes(rows))


def write_sheet(path, sheet):
    """A PNG of every frame, for looking at the drawings."""
    scale, gap = 3, 4
    names = list(sheet)
    w = FRAMES * (SIZE * scale + gap) + gap
    h = len(names) * (SIZE * scale + gap) + gap
    img = [[200] * w for _ in range(h)]
    for r, name in enumerate(names):
        for f, canvas in enumerate(sheet[name]):
            ox, oy = gap + f * (SIZE * scale + gap), gap + r * (SIZE * scale + gap)
            for y in range(SIZE):
                for x in range(SIZE):
                    v = 30 if canvas.px[y][x] else 235
                    for dy in range(scale):
                        row = img[oy + y * scale + dy]
                        for dx in range(scale):
                            row[ox + x * scale + dx] = v
    raw = b"".join(b"\x00" + bytes(row) for row in img)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as out:
        out.write(png)


def main():
    sheet = {}
    for name, draw in ANIMATIONS.items():
        folder = os.path.join(ART, name)
        os.makedirs(folder, exist_ok=True)
        for old in os.listdir(folder):
            if old.endswith(".pbm"):
                os.remove(os.path.join(folder, old))
        sheet[name] = []
        for f in range(FRAMES):
            canvas = draw(f)
            write_pbm(os.path.join(folder, "%02d.pbm" % f), canvas)
            sheet[name].append(canvas)
    if "--sheet" in sys.argv:
        write_sheet(sys.argv[sys.argv.index("--sheet") + 1], sheet)


if __name__ == "__main__":
    main()
