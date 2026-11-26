#!/usr/bin/env python3
r"""
Razed Magic Sanctuary art (2026-10-31): cracked / rubbled versions of the five STR_SANT.ILB stone floors.

User: "make Sanctuary structure razeable. GFX should be easy, just remove the bubble and make a variant of the
'stone floor' that has cracks or rubble".
razed(img) -> darker, slightly desaturated disc with jagged cracks from the centre, two chunks broken out of the
rim (transparent, so the terrain shows through, with a dark broken edge) and scattered rubble stones.
One fixed seed -> the five terrain variants (ids 0..4 -> 20..24) share the same damage pattern.
--preview <dir> writes a before/after sheet.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
from aowxlib import ilb  # noqa: E402

SEED = 0x5A7C


def _inside(a):
    return a[..., 3] > 0


def razed(rgba):
    rng = np.random.default_rng(SEED)
    img = rgba.astype(float).copy()
    h, w = img.shape[:2]
    m = _inside(rgba)
    ys, xs = np.nonzero(m)
    cx, cy = xs.mean(), ys.mean() - 2
    rx, ry = (xs.max() - xs.min()) / 2, (ys.max() - ys.min()) / 2
    # 1. weathered: darker, a little desaturated
    lum = img[..., :3] @ np.array([0.299, 0.587, 0.114])
    for c in range(3):
        img[..., c] = (img[..., c] * 0.72 + lum * 0.28) * 0.80
    # 2. broken-out rim chunks (transparent -> terrain shows), dark edge
    yy, xx = np.mgrid[0:h, 0:w]
    ang = np.arctan2((yy - cy) / ry, (xx - cx) / rx)
    rad = np.hypot((xx - cx) / rx, (yy - cy) / ry)
    hole = np.zeros((h, w), bool)
    for a0, depth, width in ((0.55, 0.30, 0.55), (2.65, 0.22, 0.42), (-2.2, 0.18, 0.35)):
        d = np.angle(np.exp(1j * (ang - a0)))
        jag = 0.05 * np.sin(ang * 23 + a0 * 7) + 0.03 * np.sin(ang * 51)
        hole |= (np.abs(d) < width) & (rad > 1.0 - depth * (1 - (np.abs(d) / width) ** 2) + jag)
    hole &= m
    edge = np.zeros_like(hole)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        edge |= np.roll(np.roll(hole, dy, 0), dx, 1)
    edge &= m & ~hole
    img[edge, :3] *= 0.45
    alpha = np.where(hole, 0, img[..., 3])
    # 3. cracks: jagged random walks from near the centre outward (+ branches)
    crack = np.zeros((h, w), float)

    def walk(x, y, a, steps, depth):
        for i in range(steps):
            a += rng.normal(0, 0.22)
            x += math.cos(a) * 1.1; y += math.sin(a) * 0.62
            ix, iy = int(round(x)), int(round(y))
            if not (0 <= ix < w and 0 <= iy < h) or not m[iy, ix] or hole[iy, ix]:
                return
            crack[iy, ix] = 1.0
            if depth == 0 and i > 6 and rng.random() < 0.05:
                walk(x, y, a + rng.choice((-1, 1)) * rng.uniform(0.6, 1.1), int(steps * 0.45), 1)
    for k in range(4):
        a = k / 4 * 2 * math.pi + rng.uniform(-0.5, 0.5)
        walk(cx + rng.normal(0, 6), cy + rng.normal(0, 4), a, int(rng.integers(18, 34)), 0)
    lit = np.roll(crack, -1, 0) * (1 - crack)
    for c, (dk, lt) in enumerate(((52, 150), (44, 144), (36, 132))):
        img[..., c] = np.where(crack > 0, dk, img[..., c])
        img[..., c] = np.where((lit > 0) & m & ~hole, np.minimum(255, img[..., c] * 0.6 + lt * 0.4), img[..., c])
    # 4. rubble stones
    stones = []
    for a0 in (0.55, 2.65, -2.2):                      # heaps at the broken rim chunks
        for _ in range(6):
            t = a0 + rng.normal(0, 0.28)
            r = rng.uniform(0.62, 0.95)
            stones.append((cx + math.cos(t) * rx * r, cy + math.sin(t) * ry * r, rng.uniform(1.6, 3.4), rng.uniform(0.8, 1.1)))
    for _ in range(7):                                 # a few loose ones
        t = rng.uniform(0, 2 * math.pi); r = rng.uniform(0.2, 0.7)
        stones.append((cx + math.cos(t) * rx * r, cy + math.sin(t) * ry * r, rng.uniform(1.2, 2.2), rng.uniform(0.8, 1.05)))
    for sx, sy, sr, shade in stones:
        d = np.hypot(xx - sx, (yy - sy) * 1.5)
        st = d <= sr
        if not st.any():
            continue
        base = np.array([118, 110, 98]) * shade
        hi = st & (yy < sy - sr * 0.2)
        lo = st & (yy > sy + sr * 0.3)
        for c in range(3):
            img[..., c] = np.where(st, base[c], img[..., c])
            img[..., c] = np.where(hi, np.minimum(255, base[c] * 1.35), img[..., c])
            img[..., c] = np.where(lo, base[c] * 0.55, img[..., c])
        alpha = np.where(st, 255, alpha)
        sh = (np.hypot(xx - sx - 1, (yy - sy - 1) * 1.5) <= sr) & ~st & (alpha > 0)
        img[sh, :3] *= 0.6
    out = np.clip(img, 0, 255).astype(np.uint8)
    out[..., 3] = np.where(alpha > 0, 255, 0).astype(np.uint8)
    return out


def build(game_dir):
    """returns the new STR_SANT.ILB bytes (ids 20..24 appended, or replaced when present)"""
    import copy
    from PIL import Image
    path = os.path.join(game_dir, "Images", "STR_SANT.ILB")
    lib = ilb.read(open(path, "rb").read())
    base = {im.id: im for im in lib.images}
    lib.images = [im for im in lib.images if not 20 <= im.id <= 24]
    for k in range(5):
        rec = base[k].primary
        w, h, rows = ilb.decode_record(lib, rec)
        a = np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)
        nr = copy.deepcopy(rec)
        nr["name"] = "str_msanct_razed.BMP"
        ilb.encode_image(lib, nr, Image.fromarray(razed(a), "RGBA"))
        lib.images.append(ilb.Image(20 + k, parts=[nr]))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lib = ilb.read(build(gd))
    by = {im.id: im for im in lib.images}
    tiles = []
    for k in list(range(5)) + list(range(20, 25)):
        w, h, rows = ilb.decode_record(lib, by[k].primary)
        t = Image.new("RGBA", (w, h)); t.putdata([q or (0, 0, 0, 0) for row in rows for q in row]); tiles.append(t)
    W, H = max(t.width for t in tiles) + 4, max(t.height for t in tiles) + 4
    s = Image.new("RGBA", (5 * W, 2 * H), (88, 120, 60, 255))
    for i, t in enumerate(tiles):
        s.alpha_composite(t, ((i % 5) * W, (i // 5) * H))
    os.makedirs(out_dir, exist_ok=True)
    s.resize((s.width * 3, s.height * 3), Image.NEAREST).save(os.path.join(out_dir, "sanct_razed.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
