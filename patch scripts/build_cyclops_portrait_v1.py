#!/usr/bin/env python3
r"""
Cyclops portrait (103x128, FACES\Add_UNITS.ILB) from the user's reference art (2026-11-07; user: "the portrait is bad,
make it based on the portraits i sent you").  The three reference images (736x1104 webp, supplied by the user in chat)
are cropped to the 103:128 portrait aspect around the cyclops' head, then reduced the way the vanilla portraits look:
painterly mode-filter at 2x, LANCZOS down to 103x128, muted/darker grade, light unsharp.  Writes candidates
portrait_<n>.png + a comparison sheet next to the vanilla Giant / Troll portraits.  PREVIEW ONLY (no ILB write).
Usage: build_cyclops_portrait_v1.py <ref dir> <out dir>
"""
import os, sys
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance

REF, OUT = sys.argv[1], sys.argv[2]
GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROPS = {  # ref image -> crop box (x0, y0, width); height = width * 128 / 103
    32: (196, 22, 370),
    33: (140, 70, 380),
    34: (178, 120, 400),
}


def portrait(src, box):
    x0, y0, w = box
    h = int(round(w * 128 / 103))
    im = src.convert("RGB").crop((x0, y0, x0 + w, y0 + h))
    im = im.resize((206, 256), Image.LANCZOS).filter(ImageFilter.ModeFilter(3))
    im = im.resize((103, 128), Image.LANCZOS)
    im = ImageEnhance.Color(im).enhance(0.82)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    a = np.asarray(im).astype(float)
    a = 255.0 * (np.clip(a / 255.0, 0, 1) ** 1.12)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.UnsharpMask(1.0, 50, 2))


def gloomy_sky_32(src):
    """v2 (user: "the first portrait is best, but remove the 'cave' elements, and make the background sky more
    gloomy"): in crop coordinates of ref 32 - sky = blue-dominant bright pixels, plus hand masks for the cave rock
    (top-left / top-right) and the hero's head (bottom-left); the sky keeps its own cloud luminance but is regraded
    to a stormy slate, masked areas are filled with matching cloud noise; the figure is darkened a touch."""
    from PIL import ImageDraw
    x0, y0, w = CROPS[32]
    h = int(round(w * 128 / 103))
    im = src.convert("RGB").crop((x0, y0, x0 + w, y0 + h))
    a = np.asarray(im).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    cand = ((b > r + 12) & (b >= g) & (lum > 110)) | ((lum > 190) & (np.abs(r - b) < 30))
    # v3 (user: "grey patches on his body"): bright skin highlights matched the white-cloud test -> keep only sky
    # candidates CONNECTED to the image border (geodesic reconstruction); highlights are islands inside the figure
    seed = np.zeros_like(cand)
    seed[0, :] = cand[0, :]; seed[-1, :] = cand[-1, :]; seed[:, 0] = cand[:, 0]; seed[:, -1] = cand[:, -1]
    for _ in range(2000):
        grown = seed.copy()
        grown[1:] |= seed[:-1]; grown[:-1] |= seed[1:]; grown[:, 1:] |= seed[:, :-1]; grown[:, :-1] |= seed[:, 1:]
        grown &= cand
        if (grown == seed).all():
            break
        seed = grown
    sky = seed
    hand = Image.new("L", (w, h), 0); dr = ImageDraw.Draw(hand)
    dr.polygon([(0, 0), (98, 0), (90, 28), (62, 52), (30, 68), (0, 66)], fill=255)          # rock, top-left
    dr.polygon([(312, 0), (370, 0), (370, 32), (340, 24)], fill=255)                       # rock, top-right
    dr.ellipse((-40, 400, 48, 500), fill=255)                                              # hero's head
    handm = np.asarray(hand) > 0
    mask = sky | handm
    # soften the mask edge
    mk = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.5))
    m = np.asarray(mk).astype(float)[..., None] / 255.0
    # cloud field: the original sky luminance where it is sky, smooth noise elsewhere
    rng = np.random.RandomState(9)
    noise = Image.fromarray((rng.rand(h // 16 + 2, w // 16 + 2) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    noise = np.asarray(noise.filter(ImageFilter.GaussianBlur(6))).astype(float)
    # fill the masked rock / hero areas from the SURROUNDING sky brightness (normalised blur = push-pull inpaint)
    real = sky & ~handm
    Lw = Image.fromarray(np.clip(lum * real, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))
    Ww = Image.fromarray((real * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))
    fill = np.asarray(Lw).astype(float) / np.maximum(np.asarray(Ww).astype(float) / 255.0, 0.02)
    cl = np.where(real, lum, np.clip(fill, 120, 240) + (noise - 128) * 0.35)
    cl = np.asarray(Image.fromarray(np.clip(cl, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))).astype(float)
    t = np.clip((cl - 120) / 135.0, 0, 1)[..., None]
    yy = np.linspace(0, 1, h)[:, None, None]
    dark, light = np.array([40, 46, 54]), np.array([128, 134, 140])
    stormy = (dark + (light - dark) * t) * (1.05 - 0.35 * yy)            # darker toward the bottom
    fig = a * 0.95                                                          # (v5: 0.80 was too dark)
    out = fig * (1 - m) + stormy * m
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def kuwahara(img, r):
    """classic oil-paint filter: per pixel, the mean colour of the least-varying of the 4 (r+1)^2 quadrants"""
    a = np.asarray(img).astype(float)
    H, W = a.shape[:2]
    lum = a @ np.array([0.299, 0.587, 0.114])
    pad = r
    ap = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    lp = np.pad(lum, pad, mode="edge")
    def integ(x):
        return np.pad(x.cumsum(0).cumsum(1), ((1, 0), (1, 0)) + (((0, 0),) if x.ndim == 3 else ()))
    Ia, Il, Il2 = integ(ap), integ(lp), integ(lp * lp)
    def box(I, y0, x0):                         # sum over [y0, y0+r] x [x0, x0+r] for every output pixel
        ys = np.arange(H)[:, None] + y0; xs = np.arange(W)[None, :] + x0
        return I[ys + r + 1, xs + r + 1] - I[ys, xs + r + 1] - I[ys + r + 1, xs] + I[ys, xs]
    n = (r + 1) ** 2
    best_v = np.full((H, W), 1e18); out = np.zeros_like(a)
    for y0, x0 in ((0, 0), (0, r), (r, 0), (r, r)):
        m = box(Il, y0, x0) / n
        v = box(Il2, y0, x0) / n - m * m
        c = box(Ia, y0, x0) / n
        sel = v < best_v
        best_v = np.where(sel, v, best_v)
        out[sel] = c[sel]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def oil(im):
    """v4 (user: "make portrait look more like an oil painting"): Kuwahara brush patches at two scales, impasto
    relief from the luminance gradient lit from the upper left, canvas weave"""
    src = im.resize((370, 460), Image.LANCZOS)
    im = kuwahara(kuwahara(src, 3), 2)
    a = np.asarray(im).astype(float)
    # keep the eye crisp: blend the unfiltered image back in around it (crop coords of ref 32: eye ~ (175, 130))
    H0, W0 = a.shape[:2]
    yy0, xx0 = np.mgrid[0:H0, 0:W0]
    w_eye = np.clip(1.0 - np.hypot((xx0 - 175) / 34.0, (yy0 - 130) / 26.0), 0, 1)[..., None] ** 0.7 * 0.8
    a = a * (1 - w_eye) + np.asarray(src).astype(float) * w_eye
    lum = a @ np.array([0.299, 0.587, 0.114])
    gy, gx = np.gradient(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0)) and
                         np.asarray(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))).astype(float))
    relief = np.clip(-(gx + gy) * 0.06, -12, 12)                # light from the upper left
    H, W = lum.shape
    yy, xx = np.mgrid[0:H, 0:W]
    weave = 3.0 * np.sin(xx * 1.9) * np.sin(yy * 1.9)
    a = a + relief[..., None] + weave[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def portrait_img(im):
    # v3 (user: "maybe slightly too detailed"): stronger painterly simplification (vanilla portraits are loose paint)
    im = oil(im)
    im = im.resize((103, 128), Image.LANCZOS)
    im = ImageEnhance.Color(im).enhance(0.82)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    a = np.asarray(im).astype(float)
    # v5 (user: "portrait seems too dark/heavily shaded"): lift the shadows instead of darkening (gamma < 1)
    a = 255.0 * (np.clip(a / 255.0, 0, 1) ** 0.86)
    a = a + 10.0 * (1.0 - a / 255.0)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.UnsharpMask(1.0, 55, 2))


def vanilla(idx):
    sys.path.insert(0, os.path.join(GAME, "modding tools"))
    from aowxlib import ilb
    lib = ilb.read(open(os.path.join(GAME, "Images", "FACES", "UNITS.ILB"), "rb").read())
    w, h, rows = ilb.decode_record(lib, lib.images[idx].primary)
    q = Image.new("RGB", (w, h)); px = q.load()
    for y in range(h):
        for x in range(w):
            c = rows[y][x]; px[x, y] = tuple(c[:3]) if c else (0, 0, 0)
    return q


def main():
    os.makedirs(OUT, exist_ok=True)
    ims = [vanilla(26), vanilla(63)]
    for n, box in CROPS.items():
        p = portrait(Image.open(os.path.join(REF, "%d.webp" % n)), box)
        p.save(os.path.join(OUT, "portrait_%d.png" % n))
        ims.append(p)
    g = gloomy_sky_32(Image.open(os.path.join(REF, "32.webp")))
    g.save(os.path.join(OUT, "portrait_32_gloomy_full.png"))
    pg = portrait_img(g)
    pg.save(os.path.join(OUT, "portrait_final.png"))
    ims = [ims[0], ims[1], ims[2], pg]
    S = Image.new("RGB", (113 * len(ims), 128), (30, 30, 30))
    for k, q in enumerate(ims):
        S.paste(q, (k * 113, 0))
    S.resize((S.width * 3, S.height * 3), Image.NEAREST).save(os.path.join(OUT, "portraits_cmp.png"))
    print("ok", len(ims))


if __name__ == "__main__":
    main()
