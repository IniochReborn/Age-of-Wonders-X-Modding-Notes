#!/usr/bin/env python3
r"""
Great Eagle's Nest side portrait v3 (2026-10-31) - ORIGINAL painting in the vanilla BORDER style.

User after v2 (vanilla B_ANode + painted nest): "the side image sucks, it should be original but in vanilla art
style".  Vanilla portraits (B_syard, B_WatchT, B_SGrove ...): soft atmospheric gradient sky with brushed cloud
streaks, the subject in the lower half lit from one side, distant blue ridges, mist at the base, small white gulls.
  portrait()  -> 57x278 RGBA: dawn sky, far ridges, a tall flat-topped crag (warm left light / cool right shade,
                 strata + cracks as brush strokes), a big twig nest on the plateau with a perched eagle, one eagle
                 soaring mid-sky, a flock of small white birds circling, mist + dark pines at the foot.
  side_images(gd) -> (top 57x2, filler 57x50, portrait) - top/filler = sky strips taken from the painting.
Painted at SS x and LANCZOS-downsampled (soft painterly edges), then a little noise so it dithers like the vanilla
art.  --preview <dir>.
"""
import math, os, sys

import numpy as np

W, H, SS = 57, 278, 4


def _noise(h, w, scale, rng, octaves=4):
    from PIL import Image
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        sh, sw = max(2, int(h / scale * 2 ** o)), max(2, int(w / scale * 2 ** o))
        n = rng.random((sh, sw))
        out += amp * np.array(Image.fromarray((n * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)) / 255.0
        tot += amp; amp *= 0.5
    return out / tot


def _lerp(a, b, t):
    return np.asarray(a, float) + (np.asarray(b, float) - np.asarray(a, float)) * t


def portrait(seed=0xEA61, scale=1.0):
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    w, h = W * SS, H * SS
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]

    # ---- sky: cool blue-violet top -> warm pale gold at the horizon, brushed cloud streaks
    t = np.clip(yy / 0.62, 0, 1) ** 1.3
    sky = _lerp((58, 70, 112), (196, 186, 170), t[..., None])
    cl = _noise(h, w, 18, rng)
    streak = np.zeros((h, w))
    for o, (rows, amp) in enumerate(((22, 1.0), (48, 0.5), (96, 0.25))):
        n = (rng.random((rows, 3 + o * 2)) * 255).astype(np.uint8)
        streak += amp * np.array(Image.fromarray(n).resize((w, h), Image.BICUBIC)) / 255.0
    streak /= 1.75
    cloud = np.clip((0.55 * cl + 0.6 * streak - 0.52) * 3.2, 0, 1) * np.clip(1.1 - yy * 1.2, 0, 1)
    cloud_col = _lerp((150, 150, 176), (238, 226, 206), np.clip(yy * 1.6, 0, 1)[..., None])
    sky = _lerp(sky, cloud_col, (cloud * 0.75)[..., None])
    sun = np.exp(-(((xx - 0.18) / 0.35) ** 2 + ((yy - 0.55) / 0.09) ** 2))           # glow behind the left side
    sky = sky + sun[..., None] * np.array([60, 44, 18])
    img = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)

    # ---- distant ridges (two layers, hazy blue)
    for k, (base, amp, col) in enumerate(((0.60, 0.035, (128, 132, 158)), (0.655, 0.03, (104, 108, 136)))):
        pts = [(0, h)]
        ph = rng.uniform(0, 6)
        for x in range(0, w + 8, 8):
            u = x / w
            y = base - amp * (0.6 * math.sin(u * 7 + ph) + 0.4 * math.sin(u * 17 + ph * 2)) - (0.03 if k == 0 and 0.55 < u < 0.85 else 0)
            pts.append((x, y * h))
        pts.append((w, h))
        d.polygon(pts, fill=col + (255,))

    # ---- the crag: flat top at TOP, widening downward, jagged flanks
    TOP = 0.50 * h
    lft = [(0.20 * w, TOP)]
    rgt = [(0.80 * w, TOP)]
    for i in range(1, 20):
        v = i / 19
        y = TOP + v * (h - TOP)
        lft.append((w * (0.20 - 0.24 * v ** 1.4 + rng.uniform(-0.035, 0.035)), y))
        rgt.append((w * (0.80 + 0.22 * v ** 1.3 + rng.uniform(-0.035, 0.035)), y))
    poly = lft + rgt[::-1]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    m = np.array(mask) > 0
    # left-lit rock: x across the column -> warm light .. cool shade, noise mottling
    cx = np.clip((xx - 0.15) / 0.75, 0, 1)
    mott = _noise(h, w, 10, rng)
    rock = _lerp((232, 194, 142), (52, 48, 78), (cx ** 1.15)[..., None])
    rock = rock * (0.82 + 0.32 * mott[..., None])
    rock = _lerp(rock, (128, 120, 140), np.clip((yy - 0.6) / 0.4, 0, 1)[..., None] * 0.35)   # haze lower down
    a = np.array(img).astype(float)
    a[m, :3] = rock[m]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)
    # brush strokes on a translucent layer: curving cracks / ridges (dark) and sunlit facets (light), short and
    # irregular like the vanilla painted rock
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
    for _ in range(260):
        x0 = rng.uniform(0.0, 1.0) * w; y0 = rng.uniform(TOP + 6 * SS, h)
        if not m[int(min(h - 1, y0)), int(min(w - 1, x0))]:
            continue
        u = x0 / w
        light = rng.random() < 0.45 and u < 0.7
        ang = math.pi / 2 + rng.uniform(-0.5, 0.5) if rng.random() < 0.6 else rng.uniform(-0.35, 0.35)
        pts = [(x0, y0)]
        for _k in range(rng.integers(2, 5)):
            ang += rng.uniform(-0.35, 0.35); ln = rng.uniform(2, 6) * SS
            pts.append((pts[-1][0] + math.cos(ang) * ln, pts[-1][1] + math.sin(ang) * ln))
        if light:
            col = tuple(int(v) for v in _lerp((240, 214, 170), (150, 140, 160), u)) + (int(rng.uniform(70, 150)),)
        else:
            col = tuple(int(v) for v in _lerp((90, 66, 52), (28, 26, 46), u)) + (int(rng.uniform(80, 170)),)
        ld.line(pts, fill=col, width=int(rng.uniform(0.6, 1.6) * SS), joint="curve")
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(SS * 0.4)))
    d = ImageDraw.Draw(img)
    # plateau rim: sunlit top surface
    d.ellipse([0.17 * w, TOP - 4 * SS, 0.83 * w, TOP + 5 * SS], fill=(150, 128, 104, 255))
    d.ellipse([0.18 * w, TOP - 5 * SS, 0.82 * w, TOP + 2.5 * SS], fill=(218, 190, 146, 255))

    # ---- nest: many twigs, dark hollow, perched eagle
    NX, NY, NR = 0.5 * w, TOP - 3.5 * SS, 0.30 * w
    d.ellipse([NX - NR, NY - 3 * SS, NX + NR, NY + 5 * SS], fill=(66, 44, 26, 255))
    for _ in range(420):
        tt = rng.uniform(0, 2 * math.pi); r = math.sqrt(rng.uniform(0.15, 1.05))
        x0 = NX + math.cos(tt) * NR * r; y0 = NY + math.sin(tt) * 3.6 * SS * r + SS
        ang = rng.uniform(-0.5, 0.5) + (math.pi if rng.random() < 0.5 else 0)
        ln = rng.uniform(3, 9) * SS
        lit = 0.6 + 0.6 * max(0.0, -math.cos(tt))                                   # left side catches the light
        c = np.array((134, 98, 58)) * rng.uniform(0.6, 1.1) * lit
        d.line([x0, y0, x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln * 0.35],
               fill=tuple(int(min(255, v)) for v in c) + (255,), width=max(1, SS // 2 + 1))
    d.ellipse([NX - NR * 0.6, NY - 2.6 * SS, NX + NR * 0.6, NY + 1.2 * SS], fill=(34, 22, 12, 255))
    _eagle_perched(d, NX + 2 * SS, NY - 7 * SS, 7.5 * SS)

    # ---- mist at the foot + dark pines
    a = np.array(img).astype(float)
    mist = np.clip((yy - 0.80) / 0.2, 0, 1) * (0.5 + 0.5 * _noise(h, w, 8, rng))
    a[..., :3] = _lerp(a[..., :3], (196, 188, 190), (mist * 0.55)[..., None])
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)
    for _ in range(9):
        px = rng.uniform(-0.05, 1.05) * w; base = h + rng.uniform(0, 6) * SS
        ph = rng.uniform(14, 30) * SS; pw = ph * 0.32
        col = (30, 40, 40, 255) if px < w * 0.5 else (24, 28, 40, 255)
        for k in range(5):
            y1 = base - ph * (k / 5); y2 = base - ph * ((k + 1.6) / 5)
            ww = pw * (1 - k / 5.5)
            d.polygon([(px - ww, y1), (px + ww, y1), (px, y2)], fill=col)

    # ---- birds: one soaring eagle + a flock of small white birds circling above the crag
    _eagle_soaring(d, 0.62 * w, 0.30 * h, 22 * SS, flap=0.15)
    for k in range(9):
        tt = k / 9 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        bx = 0.5 * w + math.cos(tt) * 0.36 * w
        by = 0.40 * h + math.sin(tt) * 0.035 * h + rng.uniform(-4, 4) * SS
        s = rng.uniform(1.6, 2.6) * SS
        dip = s * (0.6 if k % 2 else -0.2)
        col = (250, 250, 246, 255) if math.sin(tt) > -0.3 else (214, 214, 222, 255)
        d.line([bx - s * 1.4, by - dip, bx, by], fill=col, width=max(1, SS // 2 + 1))
        d.line([bx, by, bx + s * 1.4, by - dip], fill=col, width=max(1, SS // 2 + 1))

    ow, oh = int(round(W * scale)), int(round(H * scale))
    img = img.filter(ImageFilter.GaussianBlur(SS * 0.35)).resize((ow, oh), Image.LANCZOS)
    out = np.array(img).astype(float)
    out[..., :3] += rng.normal(0, 3.0, (oh, ow, 1))
    out[..., 3] = 255
    return np.clip(out, 0, 255).astype(np.uint8)


def _eagle_perched(d, X, Y, b):
    brown, light, white = (58, 38, 24, 255), (110, 78, 48, 255), (244, 240, 230, 255)
    d.polygon([(X - b * 0.25, Y + b * 0.9), (X + b * 0.25, Y + b * 0.9), (X + b * 0.1, Y + b * 1.6),
               (X - b * 0.4, Y + b * 1.6)], fill=white)
    d.polygon([(X - b * 0.2, Y - b * 1.0), (X + b * 0.55, Y - b * 0.8), (X + b * 0.7, Y - b * 0.1),
               (X + b * 0.45, Y + b * 0.9), (X - b * 0.5, Y + b * 1.0), (X - b * 0.75, Y - b * 0.2)], fill=brown)
    d.polygon([(X - b * 0.7, Y - b * 0.6), (X - b * 0.1, Y - b * 0.7), (X + b * 0.1, Y + b * 0.3),
               (X - b * 0.3, Y + b * 1.3), (X - b * 0.8, Y + b * 0.5)], fill=light)
    d.ellipse([X - b * 0.3, Y - b * 1.65, X + b * 0.55, Y - b * 0.75], fill=white)
    d.polygon([(X + b * 0.45, Y - b * 1.4), (X + b * 0.95, Y - b * 1.3), (X + b * 0.8, Y - b * 1.05),
               (X + b * 0.45, Y - b * 1.1)], fill=(232, 180, 44, 255))


def _eagle_soaring(d, X, Y, S, flap=0.0):
    brown, light, white = (52, 36, 24, 255), (98, 70, 44, 255), (244, 240, 230, 255)
    lift = flap * S * 0.18
    for side in (-1, 1):
        pts = [(X + side * S * 0.06, Y - S * 0.02), (X + side * S * 0.26, Y - S * 0.10 - lift),
               (X + side * S * 0.50, Y - S * 0.06 - lift * 1.4), (X + side * S * 0.47, Y + S * 0.01 - lift),
               (X + side * S * 0.42, Y + S * 0.03 - lift * 0.7), (X + side * S * 0.24, Y + S * 0.04),
               (X + side * S * 0.06, Y + S * 0.06)]
        d.polygon(pts, fill=brown)
        d.line(pts[:3], fill=light, width=max(1, int(S * 0.02)))
    d.ellipse([X - S * 0.06, Y - S * 0.07, X + S * 0.06, Y + S * 0.12], fill=brown)
    d.polygon([(X - S * 0.05, Y + S * 0.10), (X + S * 0.05, Y + S * 0.10), (X + S * 0.07, Y + S * 0.20),
               (X - S * 0.07, Y + S * 0.20)], fill=white)
    d.ellipse([X - S * 0.045, Y - S * 0.14, X + S * 0.045, Y - S * 0.05], fill=white)


def window_icon(gd=None):
    """85x102 structure-window picture: the same painting at 1.5x, cropped around the nest"""
    p = portrait(scale=1.5)
    y0 = int(0.5 * p.shape[0]) - 62
    return p[y0:y0 + 102, :85].copy()


def side_images(gd=None):
    p = portrait()
    top = p[0:2].copy()
    mid = p[0:50].copy()
    return top, mid, p


def preview(out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    t, m, p = side_images()
    Image.fromarray(p, "RGBA").resize((W * 3, H * 3), Image.NEAREST).save(os.path.join(out_dir, "eagle_side3.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
