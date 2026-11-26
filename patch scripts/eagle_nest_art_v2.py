#!/usr/bin/env python3
r"""
Great Eagle's Nest art v2 (2026-10-31) - on top of eagle_nest_art (helpers reused).

User after v1: "the nest connecting to the mountain is janky, make the mountain flat top with nest on it. and make
the birds white. and more birds circling... side image is bad, refer to vanilla art style and try again".
  map_frames(gd)   -> 5 RGBA 60x65: spire cut at the neck with a sunlit stone plateau cap, painted twig nest on it,
                      perched eagle (painted at 4x, alpha thresholded to the sprite's 1-bit mask)
  bird_frames()    -> 24 RGBA 64x48: three WHITE birds circling (different radii / heights / phases / directions)
  side_images(gd)  -> vanilla B_ANode portrait (air node: wind-swept rock pinnacles) + nest on the tallest pinnacle
                      + perched eagle + three soaring eagles; top / filler strips copied from B_ANode
  window_icon(gd)  -> 85x102 structure-window picture (I-* style): the same scene enlarged, nest + eagles
--preview <dir>.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eagle_nest_art as V1  # noqa: E402


def _paint_layer(w, h, draw_fn, ss=4):
    from PIL import Image, ImageDraw
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(big), ss)
    return big.resize((w, h), Image.LANCZOS)


def _composite(base_rgba, layer):
    from PIL import Image
    b = Image.fromarray(base_rgba, "RGBA")
    b.alpha_composite(layer)
    return np.array(b)


def nest_painter(cx, cy, rx, ry, seed):
    rng = np.random.default_rng(seed)

    def fn(d, s):
        X, Y, RX, RY = cx * s, cy * s, rx * s, ry * s
        d.ellipse([X - RX, Y - RY * 0.6, X + RX, Y + RY * 1.3], fill=(70, 48, 26, 255))
        for _ in range(int(rx * ry * 9)):
            t = rng.uniform(0, 2 * math.pi); r = math.sqrt(rng.uniform(0.2, 1.05))
            x0, y0 = X + math.cos(t) * RX * r, Y + math.sin(t) * RY * r + RY * 0.25
            ang = rng.uniform(-0.6, 0.6) + (math.pi if rng.random() < 0.5 else 0)
            ln = rng.uniform(2.5, 7) * s
            c = rng.uniform(0.55, 1.15)
            base = np.array((128, 94, 56)) * c * (0.75 + 0.35 * max(0, math.sin(t)))
            d.line([x0, y0, x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln * 0.45],
                   fill=tuple(int(min(255, v)) for v in base) + (255,), width=max(1, int(s * 0.6)))
        d.ellipse([X - RX * 0.62, Y - RY * 0.75, X + RX * 0.62, Y + RY * 0.25], fill=(40, 27, 15, 255))
    return fn


def eagle_painter(cx, cy, span, flap=0.0, perched=False):
    """soaring (or perched) eagle: dark brown body/wings, white head + tail, yellow beak"""
    def fn(d, s):
        X, Y, S = cx * s, cy * s, span * s
        brown, light, white = (64, 42, 26, 255), (104, 72, 44, 255), (240, 238, 228, 255)
        if perched:
            b = S * 0.22
            d.polygon([(X - b * 0.25, Y + b * 0.9), (X + b * 0.25, Y + b * 0.9), (X + b * 0.1, Y + b * 1.6),
                       (X - b * 0.4, Y + b * 1.6)], fill=white)                                    # tail
            d.polygon([(X - b * 0.2, Y - b * 1.0), (X + b * 0.55, Y - b * 0.8), (X + b * 0.7, Y - b * 0.1),
                       (X + b * 0.45, Y + b * 0.9), (X - b * 0.5, Y + b * 1.0), (X - b * 0.75, Y - b * 0.2)],
                      fill=brown)                                                                  # body
            d.polygon([(X - b * 0.7, Y - b * 0.6), (X - b * 0.1, Y - b * 0.7), (X + b * 0.1, Y + b * 0.3),
                       (X - b * 0.3, Y + b * 1.3), (X - b * 0.8, Y + b * 0.5)], fill=light)           # folded wing
            for k in range(3):
                yy = Y - b * 0.1 + k * b * 0.38
                d.line([X - b * 0.65, yy, X - b * 0.05, yy + b * 0.3], fill=(44, 29, 17, 255), width=max(1, s // 2))
            d.ellipse([X - b * 0.3, Y - b * 1.65, X + b * 0.55, Y - b * 0.75], fill=white)           # head
            d.polygon([(X + b * 0.45, Y - b * 1.4), (X + b * 0.95, Y - b * 1.3), (X + b * 0.8, Y - b * 1.05),
                       (X + b * 0.45, Y - b * 1.1)], fill=(232, 180, 44, 255))                     # hooked beak
            d.ellipse([X + b * 0.18, Y - b * 1.38, X + b * 0.32, Y - b * 1.24], fill=(20, 14, 8, 255))
            return
        lift = flap * S * 0.18
        for side in (-1, 1):
            pts = [(X + side * S * 0.06, Y - S * 0.02), (X + side * S * 0.26, Y - S * 0.10 - lift),
                   (X + side * S * 0.50, Y - S * 0.06 - lift * 1.4), (X + side * S * 0.47, Y + S * 0.01 - lift),
                   (X + side * S * 0.42, Y + S * 0.03 - lift * 0.7), (X + side * S * 0.24, Y + S * 0.04),
                   (X + side * S * 0.06, Y + S * 0.06)]
            d.polygon(pts, fill=brown)
            d.line(pts[:3], fill=light, width=max(1, int(s * 0.7)))
            for k in range(4):
                fx = X + side * S * (0.40 + k * 0.025); fy = Y - S * 0.02 - lift * (1.1 + k * 0.08)
                d.line([fx, fy, fx + side * S * 0.05, fy + S * 0.035], fill=(36, 24, 14, 255), width=max(1, s // 2))
        d.ellipse([X - S * 0.06, Y - S * 0.07, X + S * 0.06, Y + S * 0.12], fill=brown)
        d.polygon([(X - S * 0.05, Y + S * 0.10), (X + S * 0.05, Y + S * 0.10), (X + S * 0.07, Y + S * 0.20),
                   (X - S * 0.07, Y + S * 0.20)], fill=white)
        d.ellipse([X - S * 0.045, Y - S * 0.14, X + S * 0.045, Y - S * 0.05], fill=white)
        d.polygon([(X - S * 0.015, Y - S * 0.14), (X + S * 0.015, Y - S * 0.14), (X, Y - S * 0.18)],
                  fill=(232, 180, 44, 255))
    return fn


CUT = 31          # v4 (user: "the nest should not be extending past the mountain ... widen the mountain at the top")
FLARE_W, FLARE_ROWS = 38, 14     # the top FLARE_ROWS rows are stretched outward to FLARE_W px (a flat mesa cap)


def _flare(a, cut, cx, want, rows):
    from PIL import Image
    out = a.copy()
    for y in range(cut, min(a.shape[0], cut + rows + 1)):
        xs = np.nonzero(a[y, :, 3])[0]
        if len(xs) == 0:
            continue
        cur = xs.max() - xs.min() + 1
        t = (y - cut) / rows
        tw = max(cur, cur + (want - cur) * (1 - t) ** 1.4)
        row = Image.fromarray(a[y:y + 1, xs.min():xs.max() + 1])
        nw = int(round(tw))
        row = np.array(row.resize((nw, 1), Image.BILINEAR))
        row[..., 3] = np.where(row[..., 3] > 0, 255, 0)
        out[y, :] = 0
        s0 = int(round(cx - nw / 2))
        lo, hi = max(0, s0), min(a.shape[1], s0 + nw)
        out[y, lo:hi] = row[0, lo - s0:hi - s0]
    return out


def map_frames(gd):
    lib, by = V1._load(gd, "PRO_DRGN.ILB")
    out = []
    for k in range(5):
        a = V1._rgba(lib, by[k].primary).copy()
        hsv = V1._hsv(a)
        m = a[..., 3] > 0
        purple = m & (hsv[..., 0] > 0.62) & (hsv[..., 0] < 0.97) & (hsv[..., 1] > 0.10)
        lum = a[..., :3].astype(float) @ np.array([0.299, 0.587, 0.114])
        for c, t in enumerate((1.02, 0.97, 0.90)):
            a[..., c] = np.where(purple, np.clip(lum * t * 1.05, 0, 255), a[..., c])
        cut = CUT
        xs = [x for x in range(a.shape[1]) if a[cut, x, 3]]
        x0, x1 = min(xs), max(xs)
        cx = (x0 + x1) / 2
        rowcol = a[cut + 2, x0:x1 + 1, :3].astype(float).mean(0)
        a[:cut, :, 3] = 0; a[:cut, :, :3] = 0
        a = _flare(a, cut, cx, FLARE_W, FLARE_ROWS)
        x0, x1 = cx - FLARE_W / 2, cx + FLARE_W / 2
        rx = (x1 - x0) / 2 + 1.0                       # plateau = the flared top; the nest stays inside

        def cap(d, s, cx=cx, rx=rx, rowcol=rowcol):
            top = tuple(int(min(255, v * 1.25)) for v in rowcol) + (255,)
            side = tuple(int(v * 0.7) for v in rowcol) + (255,)
            d.ellipse([(cx - rx) * s, (cut - 2.5) * s, (cx + rx) * s, (cut + 3.5) * s], fill=side)
            d.ellipse([(cx - rx) * s, (cut - 3.5) * s, (cx + rx) * s, (cut + 1.5) * s], fill=top)
        a = _composite(a, _paint_layer(a.shape[1], a.shape[0], cap))
        a = _composite(a, _paint_layer(a.shape[1], a.shape[0], nest_painter(cx, cut - 3.0, rx - 8.5, 3.2, 0xEA70 + k)))
        a = _composite(a, _paint_layer(a.shape[1], a.shape[0], eagle_painter(cx + 1, cut - 6.5, 17, perched=True)))
        a[..., 3] = np.where(a[..., 3] > 96, 255, 0)
        out.append(a)
    return out


def bird_frames(n=24):
    frames = []
    loops = [(24, 8, 22, 0.0, 1), (18, 6, 14, 0.33, -1), (28, 9, 28, 0.66, 1)]   # rx, ry, cy, phase, direction
    for i in range(n):
        a = np.zeros((48, 64, 4), np.uint8)
        for rx, ry, cy, ph, dr in loops:
            t = (i / n + ph) * 2 * math.pi * dr
            x = 32 + rx * math.cos(t); y = cy + ry * math.sin(t)
            far = math.sin(t) * dr < 0
            col = (196, 200, 210) if far else (250, 250, 250)
            shade = (150, 154, 166) if far else (200, 204, 214)
            span = 2 if far else 3
            flap = ((i + int(ph * 10)) // 2) % 2
            cx, cy2 = int(round(x)), int(round(y))
            V1._put(a, cx, cy2, shade)
            for s in range(1, span + 1):
                dy = -s if flap else (-1 if s == span else 0)
                V1._put(a, cx - s, cy2 + dy, col)
                V1._put(a, cx + s, cy2 + dy, col)
        frames.append(a)
    return frames


def side_images(gd):
    lib, by = V1._load(gd, "BORDER.ILB")
    top, mid, bot = (V1._rgba(lib, by[i].primary) for i in (12, 13, 14))
    bot = bot.copy()
    w, h = bot.shape[1], bot.shape[0]
    rock = bot[176:182, 9:12, :3].reshape(-1, 3).astype(float).mean(0)

    def ledge(d, s):   # flat rock shelf on the pinnacle tip, tapering into it (no floating nest)
        top = tuple(int(min(255, v * 1.05)) for v in rock) + (255,)
        side = tuple(int(v * 0.62) for v in rock) + (255,)
        d.polygon([(1 * s, 171 * s), (19 * s, 171 * s), (13 * s, 180 * s), (11.5 * s, 186 * s), (8 * s, 186 * s),
                   (6.5 * s, 180 * s)], fill=side)
        d.ellipse([1 * s, 168.5 * s, 19 * s, 173.5 * s], fill=top)
    bot = _composite(bot, _paint_layer(w, h, ledge))
    bot = _composite(bot, _paint_layer(w, h, nest_painter(10, 168.5, 9.5, 3.6, 0xEA81)))
    bot = _composite(bot, _paint_layer(w, h, eagle_painter(10.5, 162, 26, perched=True)))
    for cx, cy, span, flap in ((32, 104, 40, 0.15), (16, 58, 20, -0.25), (44, 40, 13, 0.4)):
        bot = _composite(bot, _paint_layer(w, h, eagle_painter(cx, cy, span, flap=flap)))
    bot[..., 3] = 255
    return top, mid, bot


def window_icon(gd):
    from PIL import Image
    lib, by = V1._load(gd, "BORDER.ILB")
    base = Image.fromarray(V1._rgba(lib, by[14].primary), "RGBA").crop((0, 140, 57, 278))
    base = base.resize((85, int(138 * 85 / 57)), Image.LANCZOS).crop((0, 104, 85, 206))
    a = np.array(base)
    a = _composite(a, _paint_layer(85, 102, nest_painter(14, 50, 14, 5.2, 0xEA91)))
    a = _composite(a, _paint_layer(85, 102, eagle_painter(15.5, 41, 38, perched=True)))
    a = _composite(a, _paint_layer(85, 102, eagle_painter(56, 22, 44, flap=0.2)))
    a[..., 3] = 255
    return a


def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out_dir, exist_ok=True)
    mf = map_frames(gd); bf = bird_frames()
    s = Image.new("RGBA", (5 * 64, 80), (88, 120, 60, 255))
    for i, f in enumerate(mf):
        s.alpha_composite(Image.fromarray(f, "RGBA"), (i * 64, 12))
        s.alpha_composite(Image.fromarray(bf[i * 5 % 24], "RGBA"), (i * 64 - 1, 0))
    s.resize((s.width * 4, s.height * 4), Image.NEAREST).save(os.path.join(out_dir, "eagle_map2.png"))
    t, m, b = side_images(gd)
    ic = window_icon(gd)
    c = Image.new("RGBA", (57 + 8 + 85, 278), (30, 30, 30, 255))
    c.alpha_composite(Image.fromarray(b, "RGBA"), (0, 0)); c.alpha_composite(Image.fromarray(ic, "RGBA"), (65, 0))
    c.resize((c.width * 3, c.height * 3), Image.NEAREST).save(os.path.join(out_dir, "eagle_side2.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
