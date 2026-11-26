#!/usr/bin/env python3
r"""
Great Eagle's Nest side portrait v4 (2026-10-31).

User after v3: "side image still sucks, so does structure UI".  v3 problems: line-drawn rock, flat cartoon eagles
far too big for a 57-px portrait.  v4 follows the vanilla portraits more closely:
  * a new composition (wide flat-topped butte filling the lower half, nest on the plateau, eagles circling high in a
    warm evening sky) but the rock is TEXTURED WITH VANILLA BRUSHWORK: patches of the painted rock in B_ANode /
    B_cavup (BORDER 14 / 8), luminance only, re-coloured to a warm sandstone ramp and re-lit from the left;
  * sky = soft vertical gradient + large blurred cloud masses (vanilla skies are smooth, no streak texture);
  * birds = small silhouettes like the gulls in B_syard / B_cruin (eagles ~9 px dark with a 1-px white head,
    gulls 3-5 px white), nest = a small dark twig crown with a sunlit rim.
  painting(gd, w, h)  -> RGBA w x h (any size; the layout is in fractions)
  side_images(gd)     -> (top 57x2, filler 57x50, portrait 57x278)
  window_icon(gd)     -> 85x102 (the same painting at 1.5x, cropped around the plateau)
--preview <dir>.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eagle_nest_art as V1  # noqa: E402  (_load, _rgba)

SS = 4


def _blur_noise(h, w, cells, rng, sigma):
    from PIL import Image, ImageFilter
    n = (rng.random((max(2, h // cells), max(2, w // cells))) * 255).astype(np.uint8)
    im = Image.fromarray(n).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(sigma))
    return np.array(im) / 255.0


def _rock_luma(gd, w, h, rng):
    """vanilla painted-rock brushwork: luminance patches from BORDER 14 (air-node pinnacles) + 8 (cave mouth)"""
    from PIL import Image
    lib, by = V1._load(gd, "BORDER.ILB")
    srcs = []
    for i, box in ((14, (0, 190, 57, 278)), (8, (0, 120, 57, 230)), (14, (20, 200, 57, 278))):
        a = V1._rgba(lib, by[i].primary)[box[1]:box[3], box[0]:box[2], :3].astype(float)
        srcs.append(a @ np.array([0.299, 0.587, 0.114]))
    out = np.zeros((h, w)); wsum = np.zeros((h, w))
    ph, pw = h // 5 + 1, w // 2 + 1
    for y0 in range(-ph // 2, h, ph // 2):
        for x0 in range(-pw // 2, w, pw // 2):
            s = srcs[rng.integers(len(srcs))]
            sh, sw = s.shape
            k = rng.uniform(0.9, 1.4) * SS
            pat = np.array(Image.fromarray(s.astype(np.uint8)).resize((int(sw * k), int(sh * k)), Image.BICUBIC), float)
            if rng.random() < 0.5:
                pat = pat[:, ::-1]
            py, px = rng.integers(0, max(1, pat.shape[0] - ph)), rng.integers(0, max(1, pat.shape[1] - pw))
            pat = pat[py:py + ph, px:px + pw]
            yy, xx = np.mgrid[0:pat.shape[0], 0:pat.shape[1]]
            wt = np.sin(np.pi * (yy + 0.5) / pat.shape[0]) * np.sin(np.pi * (xx + 0.5) / pat.shape[1])
            ys, xs = slice(max(0, y0), min(h, y0 + pat.shape[0])), slice(max(0, x0), min(w, x0 + pat.shape[1]))
            oy, ox = ys.start - y0, xs.start - x0
            pp = pat[oy:oy + ys.stop - ys.start, ox:ox + xs.stop - xs.start]
            ww = wt[oy:oy + ys.stop - ys.start, ox:ox + xs.stop - xs.start]
            out[ys, xs] += (pp - pp.mean()) * ww; wsum[ys, xs] += ww
    return out / np.maximum(wsum, 1e-3)          # zero-mean detail, roughly +-60


def painting(gd, W=57, H=278, seed=0xEA64):
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    w, h = W * SS, H * SS
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w], float)[:, None, None]

    # sky: deep blue-violet -> rose -> warm gold at the horizon; big soft cloud masses, lit from below-left
    stops = [(0.0, (46, 58, 98)), (0.30, (92, 98, 138)), (0.48, (176, 150, 150)), (0.60, (230, 196, 150))]
    sky = np.zeros((h, w, 3))
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (yy >= t0) & (yy < t1)
        f = ((yy - t0) / (t1 - t0))[m][:, None]
        sky[m] = np.array(c0) + (np.array(c1) - np.array(c0)) * f
    sky[yy >= stops[-1][0]] = stops[-1][1]
    cl = _blur_noise(h, w, 18 * SS, rng, 3 * SS) * 0.7 + _blur_noise(h, w, 6 * SS, rng, 1.5 * SS) * 0.3
    cmask = np.clip((cl - 0.48) * 4.0, 0, 1) * np.clip(1.0 - yy * 1.5, 0, 1)
    ccol = np.stack([np.interp(yy, [0, 0.5], [120, 236]), np.interp(yy, [0, 0.5], [118, 200]),
                     np.interp(yy, [0, 0.5], [146, 182])], -1)
    under = np.clip((cl - 0.55) * 6, 0, 1) - np.clip((np.roll(cl, -3 * SS, 0) - 0.55) * 6, 0, 1)
    sky = sky + (ccol - sky) * (cmask * 0.8)[..., None] + np.clip(under, 0, 1)[..., None] * np.array([40, 26, 10])
    sun = np.exp(-(((xx - 0.1) / 0.35) ** 2 + ((yy - 0.56) / 0.07) ** 2))
    sky += sun[..., None] * np.array([50, 36, 14])
    img = np.clip(sky, 0, 255)

    # far mesas (hazy silhouettes)
    far = Image.new("L", (w, h), 0); fd = ImageDraw.Draw(far)
    fd.polygon([(0, 0.60 * h), (0.18 * w, 0.585 * h), (0.24 * w, 0.60 * h), (0.70 * w, 0.605 * h),
                (0.76 * w, 0.575 * h), (w, 0.57 * h), (w, h), (0, h)], fill=255)
    fm = np.array(far.filter(ImageFilter.GaussianBlur(SS * 0.6))) / 255.0
    img = img + (np.array((150, 128, 138)) - img) * (fm * 0.8)[..., None]

    # the eyrie: a cliff filling the right of the frame (running off it, like vanilla crops its subjects), with a
    # broad flat ledge on its left shoulder where the nest sits, a higher crag behind on the right
    TOP = 0.555

    def jag(pts, depth, amp):
        """midpoint displacement between control points (fractions) -> jagged outline"""
        for _ in range(depth):
            q = [pts[0]]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                L = math.hypot(x1 - x0, (y1 - y0) * h / w)
                q.append(((x0 + x1) / 2 + rng.normal(0, amp * L), (y0 + y1) / 2 + rng.normal(0, amp * L * 0.25)))
                q.append((x1, y1))
            pts = q
        return pts
    ctrl = [(0.30, 1.02), (0.24, 0.80), (0.20, 0.66), (0.10, TOP + 0.012), (0.08, TOP)]
    ledge = [(0.08, TOP), (0.40, TOP - 0.002), (0.66, TOP - 0.001)]
    crag = [(0.66, TOP - 0.001), (0.70, 0.50), (0.76, 0.455), (0.86, 0.43), (0.94, 0.395), (1.05, 0.38),
            (1.05, 1.02)]
    outline = jag(ctrl[::-1], 4, 0.10)[::-1] if False else jag(ctrl, 4, 0.10)
    outline = outline + ledge[1:] + jag(crag, 4, 0.09)[1:]
    bm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(bm).polygon([(x * w, y * h) for x, y in outline], fill=255)
    bmask = np.array(bm.filter(ImageFilter.GaussianBlur(SS * 0.5))) / 255.0
    solid = bmask > 0.5
    # light from the left: distance (px) from the left edge of each rock run, and top surfaces facing the sky
    dl = np.zeros((h, w))
    for y in range(h):
        row = solid[y]; run = 0
        for x in range(w):
            run = run + 1 if row[x] else 0
            dl[y, x] = run
    dlim = Image.fromarray(np.clip(np.where(solid, dl, 0.0) / w * 255, 0, 255).astype(np.uint8))
    dl = np.array(dlim.filter(ImageFilter.GaussianBlur(4 * SS)), float) / 255 * w
    face = np.clip(1.3 - dl / (0.42 * w), 0.45, 1.3)
    topsurf = solid & ~np.roll(solid, 3 * SS, 0)
    from PIL import Image as _I
    tsm = np.array(_I.fromarray((topsurf * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(SS))) / 255.0
    det = _rock_luma(gd, w, h, rng)
    vc = np.array(_I.fromarray((rng.random((7, 26)) * 255).astype(np.uint8)).resize((w, h), _I.BICUBIC)) / 255.0
    strata = 0.05 * np.sin(yy * 150 + 2 * np.sin(xx * 9)) - 0.9 * np.clip(0.28 - vc, 0, 1)
    warm = np.clip(face - 0.4, 0, 1)
    base = np.stack([104 + 128 * warm, 92 + 92 * warm, 104 + 14 * warm], -1)        # violet shade -> sandstone
    rock = base * (face * 0.8 + 0.25 + strata)[..., None] + det[..., None] * np.array([0.9, 0.8, 0.75])
    rock = rock + (np.array((244, 204, 150)) - rock) * (tsm * 0.7)[..., None]
    haze = np.clip((yy - 0.78) / 0.22, 0, 1)
    rock = rock + (np.array((176, 154, 160)) - rock) * (haze * 0.35)[..., None]
    img = img + (rock - img) * bmask[..., None]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(out)

    # nest: small dark twig crown with a lit left rim, a perched eagle silhouette
    NX, NY, NR = 0.36 * w, (TOP - 0.011) * h, 0.22 * w
    NH = 0.011 * h                                                                 # nest height (domed bowl)
    bowl = [(NX + math.cos(t) * NR * rng.uniform(0.95, 1.12), NY + max(0.0, math.sin(t)) * NH * rng.uniform(0.8, 1.25)
             - NH * 0.1) for t in np.linspace(0, math.pi, 24)]
    d.polygon(bowl + [(NX - NR, NY - NH * 0.2), (NX + NR, NY - NH * 0.2)], fill=(48, 32, 22, 255))      # bowl side
    d.ellipse([NX - NR, NY - NH * 0.55, NX + NR, NY + NH * 0.35], fill=(70, 48, 30, 255))   # rim
    for _ in range(int(520 * W / 57)):
        t = rng.uniform(0, 2 * math.pi); r = math.sqrt(rng.uniform(0.5, 1.05))
        side = rng.random() < 0.55
        if side:                                                                   # twigs on the bowl's side
            x0 = NX + rng.uniform(-0.98, 0.98) * NR; y0 = NY + rng.uniform(-0.1, 0.95) * NH
            u = (x0 - NX) / NR
            lit = 0.5 + 0.8 * max(0.0, -u) * (1 - (y0 - NY) / NH * 0.5)
        else:                                                                      # rim
            x0 = NX + math.cos(t) * NR * r; y0 = NY + math.sin(t) * NH * 0.45 * r - NH * 0.1
            lit = 0.75 + 0.7 * max(0.0, -math.cos(t + 0.5))
        ang = rng.uniform(-0.5, 0.5) + (math.pi if rng.random() < 0.5 else 0); ln = rng.uniform(2, 6) * SS
        c = np.array((152, 110, 66)) * rng.uniform(0.65, 1.05) * lit
        d.line([x0, y0, x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln * 0.3],
               fill=tuple(int(min(255, v)) for v in c) + (255,), width=SS // 2 + 1)
    d.ellipse([NX - NR * 0.62, NY - NH * 0.4, NX + NR * 0.62, NY + NH * 0.1], fill=(30, 20, 14, 255))   # hollow
    e = 2.1 * SS; ex, ey = NX + 0.05 * w, NY - NH * 0.2
    d.polygon([(ex - 1.2 * e, ey + 1.0 * e), (ex - 1.4 * e, ey - 1.6 * e), (ex, ey - 3.0 * e),
               (ex + 1.3 * e, ey - 1.4 * e), (ex + 1.0 * e, ey + 1.0 * e)], fill=(46, 32, 22, 255))
    d.polygon([(ex - 1.3 * e, ey - 1.4 * e), (ex - 0.2 * e, ey - 2.4 * e), (ex - 0.4 * e, ey + 0.6 * e)],
              fill=(96, 66, 40, 255))
    d.ellipse([ex - 0.9 * e, ey - 4.6 * e, ex + 1.1 * e, ey - 2.5 * e], fill=(242, 238, 228, 255))
    d.polygon([(ex + 0.9 * e, ey - 3.9 * e), (ex + 2.0 * e, ey - 3.5 * e), (ex + 0.9 * e, ey - 3.0 * e)],
              fill=(230, 176, 50, 255))

    # birds: two eagles soaring (dark, white head/tail) + a loose ring of small white gulls above the plateau
    def eagle(x, y, s, tilt):
        for side in (-1, 1):
            d.polygon([(x, y), (x + side * s * 0.5, y - s * (0.16 + tilt * side)), (x + side * s, y - s * (0.05 + tilt * side)),
                       (x + side * s * 0.55, y + s * 0.08)], fill=(40, 28, 24, 255))
        d.ellipse([x - s * 0.08, y - s * 0.16, x + s * 0.08, y], fill=(238, 234, 226, 255))
        d.polygon([(x - s * 0.07, y + s * 0.05), (x + s * 0.07, y + s * 0.05), (x, y + s * 0.22)], fill=(238, 234, 226, 255))
    eagle(0.36 * w, 0.27 * h, 5.5 * SS, 0.03)
    eagle(0.62 * w, 0.35 * h, 4.2 * SS, -0.04)
    for k in range(8):
        t = k / 8 * 2 * math.pi + rng.uniform(-0.25, 0.25)
        bx = 0.42 * w + math.cos(t) * 0.36 * w; by = 0.46 * h + math.sin(t) * 0.02 * h + rng.uniform(-3, 3) * SS
        s = rng.uniform(1.2, 1.9) * SS; dip = s * (0.5 if k % 2 else 0.0)
        col = (252, 248, 240, 255) if math.sin(t) > -0.2 else (226, 220, 222, 255)
        d.line([bx - s, by - dip, bx, by, bx + s, by - dip], fill=col, width=SS // 2 + 1)

    out = out.filter(ImageFilter.GaussianBlur(SS * 0.3)).resize((W, H), Image.LANCZOS)
    a = np.array(out).astype(float)
    a[..., :3] += rng.normal(0, 2.5, (H, W, 1))
    a[..., 3] = 255
    return np.clip(a, 0, 255).astype(np.uint8)


def side_images(gd):
    p = painting(gd)
    return p[0:2].copy(), p[0:50].copy(), p


def window_icon(gd):
    p = painting(gd, 85, 417)
    y0 = int(0.555 * 417) - 66
    return p[y0:y0 + 102].copy()


def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out_dir, exist_ok=True)
    t, m, p = side_images(gd); ic = window_icon(gd)
    c = Image.new("RGBA", (57 + 8 + 85, 278), (30, 30, 30, 255))
    c.alpha_composite(Image.fromarray(p, "RGBA"), (0, 0)); c.alpha_composite(Image.fromarray(ic, "RGBA"), (65, 0))
    c.resize((c.width * 3, c.height * 3), Image.NEAREST).save(os.path.join(out_dir, "eagle_side4.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
