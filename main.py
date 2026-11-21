#!/usr/bin/env python3
"""VELMARA - a travel poster for a place that does not exist.

Draws a 1024x1024 vintage-style travel poster with pure Python stdlib
(no third-party packages, no network) and writes it to /output/entry.png.

The poster: a floating island with a lighthouse and a waterfall, a low
golden sun on a violet-amber dusk sky, a teal sea carrying the sun's
glittering path, and the invented place name VELMARA set in large cream
capitals across the lower third.
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

# --- palette ---------------------------------------------------------------
INK = (20, 18, 52)        # deep indigo, top of the sky
VIOLET = (96, 72, 140)
ROSE = (216, 122, 142)
AMBER = (247, 183, 51)
SUN = (255, 226, 138)
CREAM = (247, 234, 208)
GOLD = (232, 178, 80)
TEAL = (16, 76, 96)
TEAL_DARK = (8, 44, 62)
TEAL_LIGHT = (26, 112, 130)
AQUA = (150, 220, 215)
WHITE = (255, 255, 255)
RED = (178, 52, 52)


def lerp(a, b, t):
    """Linear blend of two RGB colours."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


class Canvas:
    def __init__(self, w, h, color):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)
        r, g, b = color
        row = bytes((r, g, b)) * w
        for y in range(h):
            self.px[y * w * 3:(y + 1) * w * 3] = row

    def hspan(self, y, x0, x1, color):
        """Fill a horizontal run of pixels on row y."""
        if y < 0 or y >= self.h:
            return
        x0 = max(0, int(x0))
        x1 = min(self.w - 1, int(x1))
        if x1 < x0:
            return
        r, g, b = color
        base = (y * self.w + x0) * 3
        self.px[base:base + (x1 - x0 + 1) * 3] = bytes((r, g, b)) * (x1 - x0 + 1)

    def vgrad(self, y0, y1, stops):
        """Vertical gradient. stops: list of (position 0..1, colour)."""
        for y in range(y0, y1):
            t = (y - y0) / max(1, y1 - y0 - 1)
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= t <= p1:
                    u = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
                    self.hspan(y, 0, self.w - 1, lerp(c0, c1, u))
                    break
            else:
                self.hspan(y, 0, self.w - 1, stops[-1][1])

    def disc(self, cx, cy, r, color):
        """Filled circle."""
        cx = int(cx)
        cy = int(cy)
        r = int(r)
        if r <= 0:
            return
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(r * r - dy * dy))
            self.hspan(cy + dy, cx - dx, cx + dx, color)

    def ellipse(self, cx, cy, rx, ry, color):
        """Filled ellipse."""
        cx = int(cx)
        cy = int(cy)
        rx = int(rx)
        ry = int(ry)
        if rx <= 0 or ry <= 0:
            return
        for dy in range(-ry, ry + 1):
            t = dy / ry
            dx = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
            self.hspan(cy + dy, cx - dx, cx + dx, color)

    def polygon(self, pts, color):
        """Scanline-filled polygon."""
        ys = [p[1] for p in pts]
        y0, y1 = int(min(ys)), int(max(ys))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, ya = pts[i]
                x1, yb = pts[(i + 1) % n]
                if (ya <= y < yb) or (yb <= y < ya):
                    t = (y - ya) / (yb - ya)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hspan(y, xs[i], xs[i + 1], color)

    def thick_line(self, x0, y0, x1, y1, w, color):
        """A line of width w, drawn by stamping discs along it."""
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length / max(1.0, w * 0.4)))
        for i in range(steps + 1):
            t = i / steps
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, w / 2, color)


# --- a small geometric stroke font -----------------------------------------
# Each glyph is a list of polylines on a 5-wide by 7-tall grid (y down).
GLYPHS = {
    "V": [[(0, 0), (2, 6.5), (4, 0)]],
    "E": [[(4, 0), (0, 0), (0, 6.5), (4, 6.5)], [(0, 3.2), (3, 3.2)]],
    "L": [[(0, 0), (0, 6.5), (4, 6.5)]],
    "M": [[(0, 6.5), (0, 0), (2, 3.2), (4, 0), (4, 6.5)]],
    "A": [[(0, 6.5), (2, 0), (4, 6.5)], [(1.1, 4.2), (2.9, 4.2)]],
    "R": [[(0, 6.5), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)],
          [(2.6, 3), (4, 6.5)]],
}


def draw_text(canvas, text, cx, y, scale, color, weight, spacing=1.2):
    """Draw centred capitals; y is the top of the cap height."""
    total = 4 * scale * len(text) + spacing * scale * (len(text) - 1)
    x = cx - total / 2
    for ch in text:
        for stroke in GLYPHS[ch]:
            pts = [(x + px * scale, y + py * scale) for px, py in stroke]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                canvas.thick_line(x0, y0, x1, y1, weight * scale, color)
        x += 4 * scale + spacing * scale


# --- the poster -------------------------------------------------------------
HORIZON = 560


def sky_color_at(y):
    """The sky gradient colour at row y (for blending soft shapes)."""
    stops = [(0.0, INK), (0.35, VIOLET), (0.62, ROSE), (0.85, AMBER),
             (1.0, AMBER)]
    t = y / (HORIZON - 1)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            u = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return lerp(c0, c1, u)
    return stops[-1][1]


def draw_poster():
    cv = Canvas(W, H, INK)

    # Sky: indigo -> violet -> rose -> amber down to the horizon.
    cv.vgrad(0, HORIZON, [(0.0, INK), (0.35, VIOLET), (0.62, ROSE),
                           (0.85, AMBER), (1.0, AMBER)])

    # Early stars in the upper sky (fixed seed, deterministic).
    seed = 1234567

    def rnd():
        nonlocal seed
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    for _ in range(46):
        sx = int(rnd() * W)
        sy = int(rnd() * 300)
        if rnd() < 0.5:
            cv.hspan(sy, sx, sx + 1, lerp(CREAM, sky_color_at(sy), 0.25))
        else:
            cv.hspan(sy, sx, sx, lerp(CREAM, sky_color_at(sy), 0.4))

    # Soft clouds: thin flattened ellipses blended toward the local sky.
    for (cx, cy, rx, ry, tint, mix) in [
            (300, 150, 170, 7, ROSE, 0.55),
            (760, 210, 190, 8, CREAM, 0.5),
            (180, 330, 130, 6, CREAM, 0.45),
            (820, 420, 150, 7, ROSE, 0.5)]:
        cv.ellipse(cx, cy, rx, ry, lerp(tint, sky_color_at(cy), mix))

    # Sea: teal at the horizon, darker toward the viewer.
    cv.vgrad(HORIZON, H, [(0.0, TEAL), (0.45, (12, 62, 84)),
                           (1.0, TEAL_DARK)])

    # Sun: a soft halo, then the disc, straddling the horizon.
    sun_x, sun_y, sun_r = 680, 500, 62
    for (r, col) in [(150, lerp(AMBER, SUN, 0.18)),
                     (110, lerp(AMBER, SUN, 0.40)),
                     (85, lerp(AMBER, SUN, 0.62))]:
        cv.disc(sun_x, sun_y, r, col)
    cv.disc(sun_x, sun_y, sun_r, SUN)

    # The sun's glittering path on the sea, below the sun's disc.
    for i in range(12):
        y = 606 + i * 24
        w = 150 - i * 8
        dash = lerp(GOLD, TEAL, i / 14.0)
        cv.hspan(y, sun_x - w // 2, sun_x + w // 2, dash)
        cv.hspan(y + 1, sun_x - w // 3, sun_x + w // 3, lerp(dash, SUN, 0.4))

    # The floating island: a flat-topped landmass tapering to a point,
    # hanging in the dusk sky to the left of the sun.
    island = [(150, 330), (520, 330), (470, 400), (420, 452),
              (372, 500), (340, 452), (290, 405), (210, 372)]
    cv.polygon(island, INK)
    # A pale rim of light along the island's top edge.
    cv.hspan(330, 150, 520, lerp(ROSE, CREAM, 0.35))
    cv.hspan(331, 152, 518, lerp(ROSE, CREAM, 0.5))

    # The lighthouse on the island.
    lx = 350
    cv.polygon([(lx - 9, 330), (lx + 9, 330), (lx + 7, 286), (lx - 7, 286)],
               CREAM)
    cv.polygon([(lx - 11, 288), (lx + 11, 288), (lx + 8, 274), (lx - 8, 274)],
               RED)
    cv.disc(lx, 268, 5, SUN)
    # Its beam, a soft pale wedge into the evening sky.
    cv.polygon([(lx, 268), (lx + 110, 224), (lx + 110, 240)], lerp(SUN, VIOLET, 0.68))

    # The waterfall: pale bands pouring off the island's lower edge into
    # the sea, starting where the island's flank meets the sky.
    for (wx, ww, col) in [(300, 12, AQUA), (322, 8, lerp(AQUA, WHITE, 0.5)),
                           (284, 6, lerp(AQUA, TEAL_LIGHT, 0.3))]:
        for y in range(436, 612):
            wob = int(3 * math.sin((y - 436) / 26.0))
            cv.hspan(y, wx + wob - ww // 2, wx + wob + ww // 2, col)
    # Splash where the fall meets the sea.
    cv.ellipse(303, 612, 34, 9, lerp(WHITE, AQUA, 0.4))
    cv.ellipse(303, 618, 22, 6, lerp(WHITE, AQUA, 0.6))

    # Birds: small dark chevrons in the sky.
    for (bx, by, s) in [(520, 250, 12), (560, 285, 9), (610, 235, 10),
                        (240, 210, 9), (700, 330, 11)]:
        cv.thick_line(bx - s, by - s * 0.45, bx, by, 3, INK)
        cv.thick_line(bx, by, bx + s, by - s * 0.45, 3, INK)

    # Foreground headlands framing the view from below.
    cv.polygon([(0, 1024), (0, 900), (120, 872), (250, 900), (300, 1024)],
               INK)
    cv.polygon([(1024, 1024), (1024, 912), (900, 884), (790, 912),
                (740, 1024)], INK)
    # A pale rim on each headland's top edge.
    cv.thick_line(0, 900, 120, 872, 3, lerp(ROSE, CREAM, 0.4))
    cv.thick_line(120, 872, 250, 900, 3, lerp(ROSE, CREAM, 0.4))
    cv.thick_line(1024, 912, 900, 884, 3, lerp(ROSE, CREAM, 0.4))
    cv.thick_line(900, 884, 790, 912, 3, lerp(ROSE, CREAM, 0.4))

    # The place name, large cream capitals across the lower third.
    cv.hspan(772, 332, 692, GOLD)
    cv.hspan(774, 332, 692, lerp(GOLD, CREAM, 0.5))
    draw_text(cv, "VELMARA", W // 2, 800, 18.5, CREAM, 0.85)
    # A small diamond under the name.
    cv.polygon([(512, 946), (522, 956), (512, 966), (502, 956)], GOLD)

    return cv


def write_png(path, canvas):
    raw = bytearray()
    stride = canvas.w * 3
    for y in range(canvas.h):
        raw.append(0)  # filter: none
        raw += canvas.px[y * stride:(y + 1) * stride]

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    canvas = draw_poster()
    size = write_png("/output/entry.png", canvas)
    print(f"wrote /output/entry.png ({canvas.w}x{canvas.h}, {size} bytes)")


if __name__ == "__main__":
    main()
