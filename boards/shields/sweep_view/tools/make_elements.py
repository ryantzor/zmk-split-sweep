#!/usr/bin/env python3
"""Draws the nation emblems for the nice!view as 68x68 1-bit PBM frames:
air, water, earth, and fire, plus a still Bluetooth symbol. Each animation
starts and ends on the plain emblem, so the screen rests on a clean
picture when it stops. Run it again after changing a drawing; it writes
../art/<name>/.

    python3 make_elements.py [--sheet preview.png]
"""

import math
import os
import struct
import sys
import zlib

SIZE = 68
FRAMES = 12
SCALE = 4  # drawn this much larger, then shrunk, for smooth curves
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "..", "art")


class Canvas:
    """Coordinates and widths are in screen pixels (0..68)."""

    def __init__(self):
        n = SIZE * SCALE
        self.n = n
        self.px = [bytearray(n) for _ in range(n)]
        self.clip = None  # (cx, cy, r): only draw inside this circle

    def _dot(self, x, y, r, v):
        s = SCALE
        cx, cy, rr = x * s, y * s, max(0.5, r * s)
        for yy in range(max(0, int(cy - rr)), min(self.n, int(cy + rr) + 1)):
            dy = yy + 0.5 - cy
            span = rr * rr - dy * dy
            if span < 0:
                continue
            half = math.sqrt(span)
            row = self.px[yy]
            for xx in range(max(0, int(cx - half)), min(self.n, int(cx + half) + 1)):
                if self.clip:
                    ccx, ccy, cr = self.clip
                    if ((xx + 0.5) / s - ccx) ** 2 + ((yy + 0.5) / s - ccy) ** 2 > cr * cr:
                        continue
                row[xx] = v

    def stroke(self, pts, w0, w1=None, v=1):
        """A polyline whose width runs from w0 to w1 along its length."""
        w1 = w0 if w1 is None else w1
        lengths = [0.0]
        for a, b in zip(pts, pts[1:]):
            lengths.append(lengths[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total = lengths[-1] or 1
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            steps = max(1, int(seg * SCALE))
            for k in range(steps + 1):
                t = k / steps
                u = (lengths[i] + seg * t) / total
                self._dot(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, (w0 + (w1 - w0) * u) / 2, v)

    def fill(self, pts, mask):
        """Fills a polygon into a separate mask (a list of bytearrays)."""
        sp = [(x * SCALE, y * SCALE) for x, y in pts]
        ys = [p[1] for p in sp]
        for yy in range(max(0, int(min(ys))), min(self.n, int(max(ys)) + 1)):
            yc = yy + 0.5
            xs = []
            for (x0, y0), (x1, y1) in zip(sp, sp[1:] + sp[:1]):
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            row = mask[yy]
            for a, b in zip(xs[::2], xs[1::2]):
                for xx in range(max(0, int(a)), min(self.n, int(b) + 1)):
                    row[xx] = 1

    def mask(self):
        return [bytearray(self.n) for _ in range(self.n)]

    def outline(self, mask, w):
        """Inks the edge of a filled mask, w pixels thick, inside the shape."""
        k = max(1, int(round(w * SCALE)))
        n = self.n

        def erode_rows(src):
            out = []
            for row in src:
                r = bytearray(n)
                run = 0
                # A pixel survives when the whole window around it is set.
                pref = [0] * (n + 1)
                for i in range(n):
                    pref[i + 1] = pref[i] + row[i]
                for i in range(n):
                    a, b = max(0, i - k), min(n, i + k + 1)
                    r[i] = 1 if pref[b] - pref[a] == b - a else 0
                out.append(r)
            return out

        def transpose(m):
            return [bytearray(col) for col in zip(*m)]

        eroded = transpose(erode_rows(transpose(erode_rows(mask))))
        for y in range(n):
            row, src, er = self.px[y], mask[y], eroded[y]
            for x in range(n):
                if src[x] and not er[x]:
                    row[x] = 1

    def ring(self, cx, cy, r, w):
        pts = [(cx + r * math.cos(a / 90 * math.pi), cy + r * math.sin(a / 90 * math.pi)) for a in range(181)]
        self.stroke(pts, w)

    def frame(self):
        """Shrinks to 68x68: a pixel is ink when at least 40% of it is."""
        out = [[0] * SIZE for _ in range(SIZE)]
        s = SCALE
        for y in range(SIZE):
            rows = self.px[y * s : y * s + s]
            for x in range(SIZE):
                ink = sum(sum(r[x * s : x * s + s]) for r in rows)
                out[y][x] = 1 if ink >= 0.4 * s * s else 0
        return out


def spiral(cx, cy, radius, turns, start, clockwise=True, steps=90):
    """An Archimedean spiral from its center out to radius, ending at angle
    start (radians). Screen y points down, so clockwise means increasing angle."""
    pts = []
    total = turns * 2 * math.pi
    sign = 1 if clockwise else -1
    for i in range(steps + 1):
        t = i / steps
        theta = start - sign * total * (1 - t)
        r = radius * t
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return pts


def phase(f):
    return 2 * math.pi * f / FRAMES


def ease(f):
    """0 at the first frame, rising and falling once per loop."""
    return math.sin(math.pi * f / FRAMES) ** 2


def air(f):
    """Three swirls in a ring, each sweeping into a long tail, turning a
    third of a circle per loop (so the loop ends where it began)."""
    c = Canvas()
    spin = 2 * math.pi / 3 * f / FRAMES
    for k in range(3):
        a = spin + k * 2 * math.pi / 3 - math.pi / 2 - math.pi / 3
        sx, sy = 34 + 12.5 * math.cos(a), 34 + 12.5 * math.sin(a)
        # The swirl ends pointing away from the middle, then the tail
        # carries on around the outside.
        body = spiral(sx, sy, 10, 1.65, a, clockwise=True)
        tail = []
        for i in range(1, 30):
            t = i / 29
            ang = a + t * 1.55
            r = 22 + 3.5 * t
            tail.append((34 + r * math.cos(ang), 34 + r * math.sin(ang)))
        c.stroke(body, 1.6, 3.2)
        c.stroke([body[-1]] + tail, 3.2, 0.9)
    return c.frame()


def bezier(p0, p1, p2, steps=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / steps for i in range(steps + 1))]


def cubic(p0, p1, p2, p3, steps=30):
    out = []
    for i in range(steps + 1):
        t = i / steps
        a, b, c_, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0[0] + b * p1[0] + c_ * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c_ * p2[1] + d * p3[1]))
    return out


def water(f):
    """The water emblem: a circle holding three curls whose tails stream
    off to the right as nested wave lines, over rolling waves. The waves
    roll one wavelength per loop and the curls bob."""
    c = Canvas()
    t = phase(f)
    moving = 1 if f else 0
    c.ring(34, 34, 30.5, 2.6)
    c.clip = (34, 34, 28.4)
    for row, (y0, amp) in enumerate([(44, 2.6), (52, 2.6)]):
        pts = [(x / 2, y0 + amp * math.sin(2 * math.pi * (x / 2) / 40 + t + row * 1.3)) for x in range(0, 137)]
        c.stroke(pts, 2.3)
    for k, (sx, sy, r) in enumerate([(16, 25, 5.8), (29, 19, 5.8), (42, 14, 5.4)]):
        bob = 1.3 * math.sin(t + k * 2.1) * moving
        body = spiral(sx, sy + bob, r, 1.45, math.pi / 2, clockwise=False)
        c.stroke(body, 1.2, 2.3)
        e = body[-1]
        # Leaving the curl heading right, dropping a little, then running
        # level to the rim, with the far end swaying.
        tail = []
        for i in range(0, 61):
            d = i * 0.75
            sway = moving * 0.8 * (d / 45) * math.sin(t + d / 7 + k)
            tail.append((e[0] + d, e[1] + 3.2 * (1 - math.exp(-d / 5)) + sway))
        c.stroke(tail, 2.3)
    c.clip = None
    return c.frame()


def earth(f):
    """The earth emblem: a rounded trapezoid on two feet with a swirl
    inside. It stomps down once per loop, kicking up dust, while the
    swirl turns."""
    c = Canvas()
    stomp = ease(f)
    lift = -5 * math.sin(math.pi * min(1, f / (FRAMES * 0.5))) if f < FRAMES * 0.5 else 0
    dy = lift
    outline = [
        (25, 8), (43, 8), (46, 10),          # top, rounding the right corner
        (61, 51), (61, 58), (39, 58),        # right side and right foot
        (39, 52), (29, 52), (29, 58),        # the notch between the feet
        (7, 58), (7, 51), (22, 10), (25, 8),  # left foot and left side
    ]
    c.stroke([(x, y + dy) for x, y in outline], 2.6)
    # The bars across each foot.
    for y in (45, 50):
        c.stroke([(13, y + dy), (26, y + dy)], 2.2)
        c.stroke([(42, y + dy), (55, y + dy)], 2.2)
    swirl_turn = 2 * math.pi * f / FRAMES
    body = spiral(34, 27 + dy, 9.5, 1.7, -math.pi / 2 + swirl_turn, clockwise=True)
    c.stroke(body, 1.3, 2.6)
    # Dust where it lands, in the frames just after the stomp.
    if FRAMES * 0.5 <= f < FRAMES * 0.85:
        k = (f - FRAMES * 0.5) / (FRAMES * 0.35)
        for side in (-1, 1):
            for j in range(3):
                x = 34 + side * (30 + 5 * k + j * 2.5)
                y = 60 - 4 * k - j * 2
                c._dot(x, y, 0.9, 1)
    return c.frame()


def fire(f):
    """The fire emblem: curling tongues of flame rising from a bowl around a
    swirl, drawn as one outline. They flicker and settle back each loop."""
    c = Canvas()
    t = phase(f)
    calm = 1 if f else 0
    m = c.mask()

    def tongue(base, c1, c2, tip, width, ph):
        sway = calm * math.sin(t + ph)
        tip = (tip[0] + 2.4 * sway, tip[1] + calm * 1.8 * math.sin(2 * t + ph))
        c2 = (c2[0] + 1.6 * sway, c2[1])
        line = cubic(base, c1, c2, tip, 48)
        left, right = [], []
        for i, (x, y) in enumerate(line):
            u = i / (len(line) - 1)
            a, b = line[max(i - 1, 0)], line[min(i + 1, len(line) - 1)]
            nx, ny = b[0] - a[0], b[1] - a[1]
            n = math.hypot(nx, ny) or 1
            half = width * (1 - u) ** 0.75 * (0.7 + 0.3 * math.sin(math.pi * u))
            left.append((x - ny / n * half, y + nx / n * half))
            right.append((x + ny / n * half, y - nx / n * half))
        c.fill(left + right[::-1], m)

    # Each tongue leans out, then its tip curls back the other way.
    tongue((34, 44), (28, 30), (42, 16), (35, 2), 8.0, 0.0)
    tongue((25, 47), (19, 34), (20, 22), (10, 11), 6.0, 1.4)
    tongue((43, 47), (49, 34), (48, 22), (58, 11), 6.0, 2.6)
    tongue((16, 53), (10, 47), (11, 38), (3, 30), 4.5, 3.7)
    tongue((52, 53), (58, 47), (57, 38), (65, 30), 4.5, 4.8)
    bowl = [(34 + 26 * math.cos(a / 40 * math.pi), 47 + 15 * math.sin(a / 40 * math.pi)) for a in range(0, 41)]
    c.fill(bowl, m)
    # Fills between the tongues' roots, so the outline only traces the
    # outside of the fire.
    c.fill([(14, 54), (22, 44), (30, 38), (38, 38), (46, 44), (54, 54)], m)
    c.outline(m, 1.9)
    body = spiral(34, 50, 8.5, 1.55, -math.pi / 2 + calm * 0.6 * math.sin(t), clockwise=True)
    c.stroke(body, 1.2, 2.3)
    return c.frame()


def bluetooth(_f):
    """A plain Bluetooth rune, standing still."""
    c = Canvas()
    c.stroke([(22, 22), (44, 44), (33, 55), (33, 13), (44, 24), (22, 46)], 3.4)
    return c.frame()


ANIMATIONS = {"air": (air, FRAMES), "water": (water, FRAMES), "earth": (earth, FRAMES),
              "fire": (fire, FRAMES), "bluetooth": (bluetooth, 1)}


def write_pbm(path, px):
    rows = bytearray()
    for y in range(SIZE):
        byte, bits = 0, 0
        for x in range(SIZE):
            byte = (byte << 1) | px[y][x]
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
    cols = max(len(frames) for frames in sheet.values())
    w = cols * (SIZE * scale + gap) + gap
    h = len(names) * (SIZE * scale + gap) + gap
    img = [[200] * w for _ in range(h)]
    for r, name in enumerate(names):
        for f, px in enumerate(sheet[name]):
            ox, oy = gap + f * (SIZE * scale + gap), gap + r * (SIZE * scale + gap)
            for y in range(SIZE):
                for x in range(SIZE):
                    v = 30 if px[y][x] else 235
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
    only = [a for a in sys.argv[1:] if a in ANIMATIONS]
    sheet = {}
    for name, (draw, count) in ANIMATIONS.items():
        if only and name not in only:
            continue
        folder = os.path.join(ART, name)
        os.makedirs(folder, exist_ok=True)
        for old in os.listdir(folder):
            if old.endswith(".pbm"):
                os.remove(os.path.join(folder, old))
        sheet[name] = []
        for f in range(count):
            px = draw(f)
            write_pbm(os.path.join(folder, "%02d.pbm" % f), px)
            sheet[name].append(px)
    if "--sheet" in sys.argv:
        write_sheet(sys.argv[sys.argv.index("--sheet") + 1], sheet)


if __name__ == "__main__":
    main()
