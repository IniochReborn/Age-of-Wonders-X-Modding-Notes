#!/usr/bin/env python3
r"""
Great Eagle's Nest combat structure art (2026-10-31) - replaces the Node's pit + elemental glow in Nest0000.hsm.

User after v2: "combat map is good but get rid of elemental glow and replace with something more suitable. same with
structure UI image".
  mound()        -> RGBA MW x MH: a mound of piled, shaded boulders (lit from the top-left like the vanilla combat
                    art) crowned with a big twig nest and a perched eagle; 1-bit alpha (type-17 colour-key sprite)
  bird_frames()  -> BN RGBA BW x BH: four white birds circling above the mound (two loops, both directions)
--preview <dir>.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eagle_nest_side_v3 as SIDE  # noqa: E402  (_eagle_perched)

MW, MH, SS = 132, 124, 4
BW, BH, BN = 160, 96, 24


def _boulder(a, cx, cy, rx, ry, base, rng):
    """shaded ellipsoid boulder painted into float RGBA array a (SS scale)"""
    h, w = a.shape[:2]
    x0, x1 = int(max(0, cx - rx - 2)), int(min(w, cx + rx + 3))
    y0, y1 = int(max(0, cy - ry - 2)), int(min(h, cy + ry + 3))
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(float)
    # lumpy outline
    ang = np.arctan2(yy - cy, xx - cx)
    ph = rng.uniform(0, 6, 3)
    lump = 1 + 0.08 * np.sin(3 * ang + ph[0]) + 0.05 * np.sin(5 * ang + ph[1]) + 0.04 * np.sin(7 * ang + ph[2])
    u = (xx - cx) / (rx * lump); v = (yy - cy) / (ry * lump)
    r2 = u * u + v * v
    m = r2 <= 1
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    L = np.array([-0.55, -0.65, 0.52]); L /= np.linalg.norm(L)
    lit = np.clip(u * L[0] + v * L[1] + nz * L[2], 0, 1)
    tex = rng.random(m.shape)
    shade = 0.32 + 0.95 * lit ** 1.2 + 0.10 * (tex - 0.5)
    rim = np.clip((r2 - 0.82) / 0.18, 0, 1)                                    # dark contact edge
    col = np.asarray(base, float)[None, None, :] * shade[..., None]
    col = col * (1 - 0.55 * rim[..., None])
    sub = a[y0:y1, x0:x1]
    sub[m, :3] = col[m]
    sub[m, 3] = 255


def mound(seed=0xEA71):
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    w, h = MW * SS, MH * SS
    a = np.zeros((h, w, 4))
    # rows of boulders from the back (top) to the front (bottom): (y centre, half width, count, size)
    rows = [(0.42, 0.22, 3, 0.11), (0.54, 0.31, 4, 0.125), (0.67, 0.39, 5, 0.13), (0.80, 0.43, 5, 0.135)]
    stones = []
    for yc, hw, n, sz in rows:
        for k in range(n):
            t = (k + 0.5) / n
            cx = (0.5 + (t - 0.5) * 2 * hw + rng.uniform(-0.02, 0.02)) * w
            cy = (yc + rng.uniform(-0.025, 0.025) + 0.03 * (1 - (2 * t - 1) ** 2)) * h
            rx = sz * rng.uniform(0.85, 1.25) * w
            ry = rx * rng.uniform(0.62, 0.8)
            g = rng.uniform(0.85, 1.1)
            base = np.array((146, 140, 130)) * g + rng.uniform(-4, 4, 3)
            stones.append((cy, cx, rx, ry, base))
    for cy, cx, rx, ry, base in sorted(stones, key=lambda s: s[0]):
        _boulder(a, cx, cy, rx, ry, base, rng)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)
    # cracks + chips on each boulder (dark line with a light lower lip)
    for cy, cx, rx, ry, base in stones:
        for _ in range(int(rng.integers(1, 3))):
            ang = rng.uniform(0.6, 2.4); ln = rx * rng.uniform(0.4, 0.8)
            x0 = cx + rng.uniform(-0.4, 0.2) * rx; y0 = cy + rng.uniform(-0.5, 0.2) * ry
            x1, y1 = x0 + math.cos(ang) * ln * 0.6, y0 + math.sin(ang) * ln * 0.5
            d.line([x0, y0, x1, y1], fill=(54, 50, 50, 255), width=SS)
            d.line([x0 + SS, y0 + SS, x1 + SS, y1 + SS], fill=(190, 182, 168, 255), width=max(1, SS // 2))
    # moss / lichen dabs on the lit tops
    for _ in range(90):
        x = rng.uniform(0.1, 0.9) * w; y = rng.uniform(0.35, 0.9) * h
        if img.getpixel((int(x), int(y)))[3] == 0:
            continue
        r = rng.uniform(0.6, 1.6) * SS
        d.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6],
                  fill=(int(rng.uniform(80, 110)), int(rng.uniform(100, 130)), int(rng.uniform(50, 70)), 255))
    # twig nest crown
    NX, NY, NR, NRY = 0.5 * w, 0.30 * h, 0.27 * w, 0.075 * h
    d.ellipse([NX - NR, NY - NRY * 0.7, NX + NR, NY + NRY * 1.4], fill=(64, 42, 24, 255))
    for _ in range(900):
        tt = rng.uniform(0, 2 * math.pi); r = math.sqrt(rng.uniform(0.15, 1.08))
        x0 = NX + math.cos(tt) * NR * r; y0 = NY + math.sin(tt) * NRY * r + NRY * 0.3
        ang = rng.uniform(-0.55, 0.55) + (math.pi if rng.random() < 0.5 else 0)
        ln = rng.uniform(4, 13) * SS
        lit = 0.62 + 0.55 * max(0.0, -math.sin(tt + 0.6))
        c = np.array((136, 100, 60)) * rng.uniform(0.6, 1.12) * lit
        d.line([x0, y0, x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln * 0.35],
               fill=tuple(int(min(255, v)) for v in c) + (255,), width=max(1, SS // 2 + 1))
    d.ellipse([NX - NR * 0.62, NY - NRY * 0.75, NX + NR * 0.62, NY + NRY * 0.35], fill=(32, 21, 12, 255))
    SIDE._eagle_perched(d, NX + NR * 0.38, NY - NRY * 1.3, 11 * SS)
    img = img.filter(ImageFilter.GaussianBlur(SS * 0.25)).resize((MW, MH), Image.LANCZOS)
    out = np.array(img)
    out[..., 3] = np.where(out[..., 3] > 110, 255, 0)
    return out


def bird_frames(n=BN):
    from PIL import Image, ImageDraw
    loops = [(62, 16, 30, 0.0, 1), (44, 11, 20, 0.5, 1), (52, 13, 40, 0.25, -1), (34, 9, 12, 0.75, -1)]
    frames = []
    for i in range(n):
        img = Image.new("RGBA", (BW * SS, BH * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        for j, (rx, ry, cy, ph, dr) in enumerate(loops):
            t = (i / n + ph) * 2 * math.pi * dr
            x = (BW / 2 + rx * math.cos(t)) * SS; y = (cy + ry * math.sin(t)) * SS
            far = math.sin(t) * dr < 0
            s = (3.6 if far else 5.0) * SS
            col = (206, 208, 216, 255) if far else (252, 252, 250, 255)
            flap = math.sin((i + j * 5) / n * 2 * math.pi * 4)
            dip = s * 0.45 * flap
            heading = -math.sin(t) * dr                                       # wings tilt along the loop
            wx, wy = math.cos(0.25 * heading), math.sin(0.25 * heading)
            d.line([x - wx * s, y - wy * s - dip, x - wx * s * 0.4, y - s * 0.12, x, y], fill=col, width=int(1.7 * SS))
            d.line([x, y, x + wx * s * 0.4, y - s * 0.12, x + wx * s, y + wy * s - dip], fill=col, width=int(1.7 * SS))
            d.ellipse([x - 0.6 * SS, y - 0.5 * SS, x + 0.6 * SS, y + 0.9 * SS], fill=col)
        img = img.resize((BW, BH), Image.LANCZOS)
        a = np.array(img); a[..., 3] = np.where(a[..., 3] > 90, 255, 0)
        frames.append(a)
    return frames


def preview(out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    m = mound(); bf = bird_frames()
    s = Image.new("RGBA", (3 * 180, 190), (74, 98, 52, 255))
    for k in range(3):
        s.alpha_composite(Image.fromarray(m, "RGBA"), (k * 180 + 24, 60))
        s.alpha_composite(Image.fromarray(bf[k * 8], "RGBA"), (k * 180 + 10, 0))
    s.resize((s.width * 2, s.height * 2), Image.NEAREST).save(os.path.join(out_dir, "eagle_combat.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
