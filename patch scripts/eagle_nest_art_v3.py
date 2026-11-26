#!/usr/bin/env python3
r"""
Great Eagle's Nest map sprite v3 (2026-10-31) - an ORIGINAL crag (no PRO_DRGN pixels).

User after v4: "i think the problem is the mountains are too similar to vanilla. make original ones with a more
realistic shape, the nest is still too wide compared to top of mountain".
  map_frames(gd) -> 5 RGBA 60x65 (same canvas / anchor as PRO_DRGN so the Release.hss offsets stay valid):
    a steep-sided butte - broad flat top (~38 px) well wider than the nest (~20 px), stepped cliff faces with an
    outcrop, scree flaring into the ground - painted with crag_paint.facet_rock (lit planes from the upper left,
    crevices, sunlit top); the foot is tinted per terrain variant from the original frame's ground colours (grass /
    steppe / desert / swamp / snow; frame 4 also gets snow on every upward surface).  Nest + perched eagle on top.
--preview <dir>.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eagle_nest_art as V1  # noqa: E402
import eagle_nest_art_v2 as V2  # noqa: E402
import crag_paint as CP  # noqa: E402

W, H, SS = 60, 65, 4
TOP_Y, TOP_L, TOP_R = 17.0, 13.0, 47.0      # flat top (sprite px)
NEST_RX = 9.5
RAZED_SEEDS = (0xEAA1, 0xEAA2, 0xEAA3)


def _outline(rng):
    """butte silhouette, sprite px: flat top, stepped faces, outcrop on the left, scree to the foot ellipse"""
    left = [(TOP_L, TOP_Y), (TOP_L - 0.8, TOP_Y + 6), (TOP_L + 0.6, TOP_Y + 11), (TOP_L - 1.4, TOP_Y + 15),
            (TOP_L - 1.0, TOP_Y + 22), (TOP_L - 3.5, TOP_Y + 26), (TOP_L - 4.0, TOP_Y + 32), (TOP_L - 7.0, TOP_Y + 37),
            (TOP_L - 8.5, TOP_Y + 41), (6.0, 61.0)]
    right = [(TOP_R, TOP_Y), (TOP_R + 0.6, TOP_Y + 7), (TOP_R - 0.4, TOP_Y + 12), (TOP_R + 1.2, TOP_Y + 18),
             (TOP_R + 1.0, TOP_Y + 25), (TOP_R + 3.5, TOP_Y + 30), (TOP_R + 4.5, TOP_Y + 36), (TOP_R + 7.0, TOP_Y + 40),
             (54.5, 61.0)]
    foot = [(6.0 + 48.5 * t, 61.0 + 2.6 * math.sin(math.pi * t)) for t in np.linspace(0, 1, 14)]
    top = [(TOP_L + (TOP_R - TOP_L) * t, TOP_Y - 0.6 * math.sin(math.pi * t) + rng.uniform(-0.25, 0.25))
           for t in np.linspace(0, 1, 10)]
    pts = top + right[1:] + foot[::-1][1:-1] + left[::-1][:-1]
    return [(x + rng.uniform(-0.35, 0.35), y + rng.uniform(-0.2, 0.2)) for x, y in pts]


def _ground_colour(gd, k):
    lib, by = V1._load(gd, "PRO_DRGN.ILB")
    a = V1._rgba(lib, by[k].primary)
    reg = a[50:65][a[50:65, :, 3] > 0][:, :3].astype(float)
    return reg.mean(0) if len(reg) else np.array((90, 110, 60.0))


def map_frames(gd, seed=0xEA90, broken=None, terrains=range(5)):
    """broken = None (intact nest + eagle) or a list of debris seeds (razed: one frame per seed, terrain 0)"""
    from PIL import Image, ImageDraw, ImageFilter
    out = []
    jobs = [(k, None) for k in terrains] if broken is None else [(0, b) for b in broken]
    for k, bseed in jobs:
        rng = np.random.default_rng(seed)                 # same crag on every terrain
        w, h = W * SS, H * SS
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).polygon([(x * SS, y * SS) for x, y in _outline(rng)], fill=255)
        mask = np.array(m) > 127
        snow = k == 4
        g = _ground_colour(gd, k)
        # v4 polish (user: "polish the mountain, it looks a bit low quality"): vanilla-mountain look = two layers
        # of tall column facets (big planes + fine detail), strong warm-light / violet-shadow contrast, few cracks
        kw = dict(light=(-0.80, -0.32, 0.50), ambient=0.10, top_px=3 * SS // 2,
                  lit_col=(238, 226, 190) if not snow else (236, 238, 246),
                  shade_col=(62, 52, 88) if not snow else (110, 112, 140),
                  top_col=(246, 232, 196) if not snow else (252, 252, 255), crevice_col=(40, 30, 50))
        big = CP.facet_rock(mask, rng, cell=5.5 * SS, aspect=0.18, tilt=0.20, crevice_px=0.55 * SS, crev_frac=0.55, **kw)
        fine = CP.facet_rock(mask, rng, cell=2.4 * SS, aspect=0.25, tilt=0.30, crevice_px=0.3 * SS, crev_frac=0.35, **kw)
        rock = big * 0.6 + fine * 0.4
        yy = np.mgrid[0:h, 0:w][0] / SS
        # ground at the foot: the terrain's own colours creeping up the scree
        gm = np.clip((yy - 50.0) / 10.0, 0, 1)
        from PIL import Image as _I
        blob = np.array(_I.fromarray((rng.random((H // 3, W // 3)) * 255).astype(np.uint8)).resize((w, h), _I.BICUBIC)) / 255.0
        gm = np.clip(gm * 1.4 - (1 - blob) * 0.5, 0, 1)                    # soft vegetation patches creeping up
        veg = g[None, None, :] * (0.65 + 0.55 * blob[..., None])
        rock = rock + (veg - rock) * (gm * 0.9)[..., None]
        a = np.zeros((h, w, 4)); a[..., :3] = rock; a[..., 3] = mask * 255
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
        d = ImageDraw.Draw(img)
        # flat top plane (seen slightly from above) + its sunlit front lip
        cx = (TOP_L + TOP_R) / 2
        tc = (226, 204, 160, 255) if not snow else (246, 248, 255, 255)
        d.ellipse([TOP_L * SS, (TOP_Y - 2.2) * SS, TOP_R * SS, (TOP_Y + 2.4) * SS], fill=tc)
        d.arc([TOP_L * SS, (TOP_Y - 2.2) * SS, TOP_R * SS, (TOP_Y + 2.4) * SS], 20, 160,
              fill=(150, 128, 104, 255) if not snow else (200, 206, 220, 255), width=SS // 2 + 1)
        img = img.filter(ImageFilter.GaussianBlur(SS * 0.22)).resize((W, H), Image.LANCZOS)
        a = np.array(img)
        if bseed is None:
            a = V2._composite(a, V2._paint_layer(W, H, V2.nest_painter(cx, TOP_Y - 1.4, NEST_RX - 2.6, 2.9, 0xEA70 + k)))
            a = V2._composite(a, V2._paint_layer(W, H, V2.eagle_painter(cx + 1, TOP_Y - 4.6, 16, perched=True)))
        else:
            a = V2._composite(a, V2._paint_layer(W, H, broken_nest_painter(cx, TOP_Y, bseed)))
        a[..., 3] = np.where(a[..., 3] > 96, 255, 0)
        out.append(a)
    return out


def broken_nest_painter(cx, ty, seed):
    """razed nest: a flattened, scattered twig heap, a few sticks hanging over the cliff edge, a white feather"""
    rng = np.random.default_rng(seed)

    def fn(d, s):
        X, Y = cx * s, ty * s
        d.ellipse([X - 8 * s, Y - 2.4 * s, X + 6 * s, Y + 1.6 * s], fill=(44, 30, 18, 255))         # collapsed heap
        d.ellipse([X + 7 * s, Y - 1.2 * s, X + 11 * s, Y + 1.0 * s], fill=(52, 36, 22, 255))        # scattered clump
        for _ in range(260):
            ox = rng.normal(-1.0, 5.5); oy = rng.normal(-0.4, 1.1)
            x0, y0 = X + ox * s, Y + oy * s
            ang = rng.uniform(0, math.pi); ln = rng.uniform(1.5, 5) * s
            c = np.array((128, 94, 56)) * rng.uniform(0.55, 1.1)
            d.line([x0, y0, x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln * 0.3],
                   fill=tuple(int(v) for v in c) + (255,), width=max(1, s // 2))
        for k in range(6):                                                           # snapped sticks poking up
            px = X + rng.uniform(-7, 5) * s; py = Y + rng.uniform(-1.5, 0.5) * s
            d.line([px, py, px + rng.uniform(-2.5, 2.5) * s, py - rng.uniform(2.5, 4.5) * s],
                   fill=(110, 80, 48, 255), width=max(1, s // 2 + 1))
        for k in range(5):                                                           # sticks over the edge
            ex = X + rng.uniform(-14, 14) * s; ey = Y + rng.uniform(1.0, 2.2) * s
            d.line([ex, ey - 1.5 * s, ex + rng.uniform(-2, 2) * s, ey + rng.uniform(2.5, 5) * s],
                   fill=(92, 66, 40, 255), width=max(1, s // 2 + 1))
        fx, fy = X + rng.uniform(3, 8) * s, Y - 0.5 * s
        d.line([fx - 1.5 * s, fy, fx + 1.5 * s, fy - 0.6 * s], fill=(240, 238, 230, 255), width=max(1, s // 2 + 1))
    return fn


def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out_dir, exist_ok=True)
    mf = map_frames(gd); bf = V2.bird_frames()
    s = Image.new("RGBA", (5 * 64, 80), (88, 120, 60, 255))
    for i, f in enumerate(mf):
        s.alpha_composite(Image.fromarray(f, "RGBA"), (i * 64, 12))
        s.alpha_composite(Image.fromarray(bf[i * 5 % 24], "RGBA"), (i * 64 - 1, 4))
    s.resize((s.width * 4, s.height * 4), Image.NEAREST).save(os.path.join(out_dir, "eagle_map3.png"))
    rz = map_frames(gd, broken=RAZED_SEEDS)
    s = Image.new("RGBA", (3 * 64, 70), (88, 120, 60, 255))
    for i, f in enumerate(rz):
        s.alpha_composite(Image.fromarray(f, "RGBA"), (i * 64, 2))
    s.resize((s.width * 4, s.height * 4), Image.NEAREST).save(os.path.join(out_dir, "eagle_razed.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
