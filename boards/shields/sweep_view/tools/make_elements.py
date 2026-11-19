#!/usr/bin/env python3
"""Draws the nation emblems for the nice!view as 68x68 1-bit PBM frames:
air, water, earth, and fire, plus a still Bluetooth symbol. Each emblem
draws itself the way you'd scratch it into the dirt with a stick: one
stroke at a time, each line growing from where the stick starts, with a
short pause whenever the stick lifts. The last frame is the finished
emblem, which the screen rests on. Run it again after changing a drawing;
it writes ../art/<name>/.

    python3 make_elements.py [--sheet preview.png]
"""

import math
import os
import struct
import sys
import zlib

SIZE = 68
FRAMES = 28
PEN_UP = 0.07  # pause between strokes, as a share of all the line drawn
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

    def stroke(self, pts, w0, w1=None, v=1, upto=1.0, profile=None):
        """A polyline whose width runs from w0 to w1 along its length (or
        follows profile, a list of (fraction, width) points). Only the
        first upto of its length is drawn, for strokes still being drawn."""
        w1 = w0 if w1 is None else w1
        profile = profile or [(0.0, w0), (1.0, w1)]

        def width(u):
            for (u0, a), (u1, b) in zip(profile, profile[1:]):
                if u <= u1:
                    return a + (b - a) * ((u - u0) / (u1 - u0) if u1 > u0 else 1)
            return profile[-1][1]

        lengths = [0.0]
        for a, b in zip(pts, pts[1:]):
            lengths.append(lengths[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total = lengths[-1] or 1
        stop = total * upto
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            if lengths[i] >= stop:
                break
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            steps = max(1, int(seg * SCALE))
            for k in range(steps + 1):
                t = k / steps
                if lengths[i] + seg * t > stop:
                    break
                u = (lengths[i] + seg * t) / total
                self._dot(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, width(u) / 2, v)

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

    def contour(self, mask):
        """The outer edge of a filled mask as one closed path, in screen
        pixels, traced clockwise (Moore neighbor tracing)."""
        n = self.n
        start = None
        for y in range(n):
            x = mask[y].find(1)
            if x != -1:
                start = (x, y)
                break
        if start is None:
            return []
        dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
        path, (cx, cy), d = [start], start, 0
        for _ in range(n * n):
            for i in range(8):
                k = (d + 6 + i) % 8
                nx, ny = cx + dirs[k][0], cy + dirs[k][1]
                if 0 <= nx < n and 0 <= ny < n and mask[ny][nx]:
                    cx, cy, d = nx, ny, k
                    break
            else:
                break
            if (cx, cy) == start:
                break
            path.append((cx, cy))
        # Smooth the pixel steps away and go back to screen pixels.
        smooth = []
        m = len(path)
        for i in range(0, m, 3):
            xs = [path[(i + j) % m][0] for j in range(-6, 7)]
            ys = [path[(i + j) % m][1] for j in range(-6, 7)]
            smooth.append(((sum(xs) / len(xs) + 0.5) / SCALE, (sum(ys) / len(ys) + 0.5) / SCALE))
        return smooth

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


class Stroke:
    def __init__(self, pts, w0, w1=None, profile=None, clip=None):
        self.pts, self.w0, self.w1, self.profile, self.clip = pts, w0, w1, profile, clip
        self.length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def draw_on(strokes, f, count=FRAMES):
    """Frame f of drawing the strokes in order at a steady hand speed, the
    stick lifting briefly between strokes. The last frame is complete."""
    total = sum(st.length for st in strokes)
    gap = total * PEN_UP
    timeline = total + gap * (len(strokes) - 1)
    now = timeline * (f + 1) / count
    c = Canvas()
    t = 0.0
    for st in strokes:
        if now <= t:
            break
        c.clip = st.clip
        c.stroke(st.pts, st.w0, st.w1, upto=min(1.0, (now - t) / st.length), profile=st.profile)
        t += st.length + gap
    c.clip = None
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


def circle(cx, cy, r, start=-math.pi / 2, steps=120):
    return [(cx + r * math.cos(start + 2 * math.pi * i / steps), cy + r * math.sin(start + 2 * math.pi * i / steps))
            for i in range(steps + 1)]


def air_strokes():
    """Three swirls in a ring, each drawn from its center outward and on
    into a long tail."""
    strokes = []
    for k in range(3):
        a = k * 2 * math.pi / 3 - math.pi / 2 - math.pi / 3
        sx, sy = 34 + 12.5 * math.cos(a), 34 + 12.5 * math.sin(a)
        body = spiral(sx, sy, 10, 1.65, a, clockwise=True)
        tail = []
        for i in range(1, 30):
            t = i / 29
            ang = a + t * 1.55
            r = 22 + 3.5 * t
            tail.append((34 + r * math.cos(ang), 34 + r * math.sin(ang)))
        pts = body + tail
        split = Stroke(body, 1).length / Stroke(pts, 1).length
        strokes.append(Stroke(pts, 0, profile=[(0, 1.6), (split, 3.2), (1, 0.9)]))
    return strokes


def water_strokes():
    """The circle, then three curls with tails streaming off to the right,
    then the waves underneath."""
    inside = (34, 34, 28.4)
    strokes = [Stroke(circle(34, 34, 30.5), 2.6)]
    for sx, sy, r in [(16, 25, 5.8), (29, 19, 5.8), (42, 14, 5.4)]:
        body = spiral(sx, sy, r, 1.45, math.pi / 2, clockwise=False)
        e = body[-1]
        tail = [(e[0] + d * 0.75, e[1] + 3.2 * (1 - math.exp(-d * 0.75 / 5))) for d in range(1, 61)]
        tail = [p for p in tail if (p[0] - 34) ** 2 + (p[1] - 34) ** 2 < 28.4 ** 2]
        pts = body + tail
        split = Stroke(body, 1).length / Stroke(pts, 1).length
        strokes.append(Stroke(pts, 0, profile=[(0, 1.2), (split, 2.3), (1, 2.3)], clip=inside))
    for row, (y0, amp) in enumerate([(44, 2.6), (52, 2.6)]):
        pts = [(x / 2, y0 + amp * math.sin(2 * math.pi * (x / 2) / 40 + row * 1.3)) for x in range(0, 137)]
        pts = [p for p in pts if (p[0] - 34) ** 2 + (p[1] - 34) ** 2 < 28.4 ** 2]
        strokes.append(Stroke(pts, 2.3, clip=inside))
    return strokes


def earth_strokes():
    """The rounded trapezoid on its two feet in one line, the bars across
    the feet, then the swirl inside."""
    outline = [
        (25, 8), (43, 8), (46, 10),
        (61, 51), (61, 58), (39, 58),
        (39, 52), (29, 52), (29, 58),
        (7, 58), (7, 51), (22, 10), (25, 8),
    ]
    strokes = [Stroke(outline, 2.6)]
    for y in (45, 50):
        strokes.append(Stroke([(13, y), (26, y)], 2.2))
        strokes.append(Stroke([(42, y), (55, y)], 2.2))
    strokes.append(Stroke(spiral(34, 27, 9.5, 1.7, -math.pi / 2, clockwise=True), 1.3, 2.6))
    return strokes


def fire_strokes():
    """The swirl, then the flames traced in one continuous line from the
    bottom, up and over each tongue and back round."""
    c = Canvas()
    m = c.mask()

    def tongue(base, c1, c2, tip, width):
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

    tongue((34, 44), (28, 30), (42, 16), (35, 2), 8.0)
    tongue((25, 47), (19, 34), (20, 22), (10, 11), 6.0)
    tongue((43, 47), (49, 34), (48, 22), (58, 11), 6.0)
    tongue((16, 53), (10, 47), (11, 38), (3, 30), 4.5)
    tongue((52, 53), (58, 47), (57, 38), (65, 30), 4.5)
    c.fill([(34 + 26 * math.cos(a / 40 * math.pi), 47 + 15 * math.sin(a / 40 * math.pi)) for a in range(0, 41)], m)
    c.fill([(14, 54), (22, 44), (30, 38), (38, 38), (46, 44), (54, 54)], m)
    edge = c.contour(m)
    # Start at the bottom of the bowl, so the stick goes up the left side.
    bottom = max(range(len(edge)), key=lambda i: edge[i][1] - abs(edge[i][0] - 34) * 0.3)
    edge = edge[bottom:] + edge[: bottom + 1]
    # Pull the line in by half its width, so it sits where the outline was.
    swirl = spiral(34, 50, 8.5, 1.55, -math.pi / 2, clockwise=True)
    return [Stroke(swirl, 1.2, 2.3), Stroke(edge, 2.0)]


def bluetooth_strokes():
    return [Stroke([(22, 22), (44, 44), (33, 55), (33, 13), (44, 24), (22, 46)], 3.4)]


def drawing(strokes_for, count=FRAMES):
    strokes = strokes_for()
    return lambda f: draw_on(strokes, f, count)


ANIMATIONS = {
    "air": (drawing(air_strokes), FRAMES),
    "water": (drawing(water_strokes), FRAMES),
    "earth": (drawing(earth_strokes), FRAMES),
    "fire": (drawing(fire_strokes), FRAMES),
    "bluetooth": (drawing(bluetooth_strokes, 1), 1),
}


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
