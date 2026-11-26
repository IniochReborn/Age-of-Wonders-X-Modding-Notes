#!/usr/bin/env python3
r"""
Cyclops unit sprites v1 (2026-11-07) - PREVIEW ONLY (writes PNG sheets, no game files).

User: "now i want to try making a new cyclops unit. it should be comparable in size to Giant. maybe look at troll for
shape inspiration too. but it should look like a cyclops. take a shot at making a cyclops GFX" + "cyclops should not
have a giant's club btw".

Base = Images\UNITS\Gbn\troll.ILB (72 frames 64x64: directions 1..6 x 12 frames; unarmed, claws/fists).  Giant is
~38 px tall on average vs troll ~33 px -> every frame is scaled by SCALE about the bottom-centre of the figure.
Per pixel (troll colours separate cleanly by hue):
  * green skin            -> flesh ramp (luminance-mapped, so the troll's shading is kept)
  * dark grey hair/scalp  -> bald scalp (same flesh ramp, a little darker) inside the head zone
  * brown leather         -> kept (loincloth + shoulder strap)
  * front-facing directions (1, 2, 6): one big eye drawn in the middle of the face (white, dark iris, red rim,
    heavy brow) after scaling, at the head found from the troll's hair band.
Output: <scratch>\cyclops\frames\<id>.png (RGBA) + preview sheets.
"""
import colorsys, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
from aowxlib import ilb  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TROLL = os.path.join(GAME, "Images", "UNITS", "Gbn", "troll.ILB")
GIANT = os.path.join(GAME, "Images", "UNITS", "Dwr", "giant.ILB")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "cyclops")
SCALE = 1.15
FRONT = {1, 2, 6}
SKINS = {
    "flesh": [(0.00, (58, 38, 34)), (0.35, (128, 88, 70)), (0.65, (192, 148, 120)), (1.00, (244, 212, 184))],
    "stone": [(0.00, (40, 40, 46)), (0.35, (96, 94, 98)), (0.65, (156, 152, 146)), (1.00, (220, 216, 204))],
}
SKIN = SKINS[os.environ.get("CYC_SKIN", "flesh")]


def load(path):
    lib = ilb.read(open(path, "rb").read())
    out = {}
    for im in lib.images:
        w, h, rows = ilb.decode_record(lib, im.primary)
        p = Image.new("RGBA", (w, h), (0, 0, 0, 0)); px = p.load()
        for y in range(h):
            for x in range(w):
                q = rows[y][x]
                if q and q[3]:
                    px[x, y] = tuple(q[:3]) + (255,)
        out[im.id] = p
    return out


def kind(c):
    """v1.1: troll skin = green hues + its yellow-grey highlights (h 45-62, low sat) + purple-grey edge shadows
    (h >= 280 or < 10); leather = saturated browns; neutral greys = hair / outline / claws"""
    r, g, b = c
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    h *= 360
    if s >= 0.08 and 62 < h <= 190:
        return "skin"
    if s >= 0.06 and 42 <= h <= 62:
        return "skin"
    if s >= 0.08 and (h >= 280 or h < 10):
        return "skin"
    if s >= 0.22 and 10 <= h < 42:
        return "leather"
    if max(c) - min(c) < 14:
        return "grey"
    return "other"


def ramp(t):
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(SKIN, SKIN[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(int(round(c0[i] + (c1[i] - c0[i]) * f)) for i in range(3))
    return SKIN[-1][1]


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def bbox(p):
    return p.getbbox()


def head_info(p):
    """(cx, hair_bottom_y) of the dark hair band on top of the figure, or None"""
    px = p.load(); w, h = p.size
    bb = bbox(p)
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    zone = y0 + max(6, (y1 - y0) * 30 // 100)
    pts = [(x, y) for y in range(y0, zone) for x in range(x0, x1)
           if px[x, y][3] and kind(px[x, y][:3]) == "grey" and lum(px[x, y]) < 120]
    if len(pts) < 4:
        return None
    # largest horizontal cluster near the top = the hair band
    ys = sorted(set(y for _, y in pts))
    top = ys[0]
    band = [(x, y) for x, y in pts if y <= top + 4]
    cx = sum(x for x, _ in band) / len(band)
    hb = max(y for _, y in band)
    return cx, hb, zone


def recolour(p, lo, hi):
    px = p.load(); w, h = p.size
    hi_ = head_info(p)
    zone = hi_[2] if hi_ else -1
    q = p.copy(); qx = q.load()
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if not c[3]:
                continue
            k = kind(c[:3])
            L = lum(c)
            if k == "skin":
                qx[x, y] = ramp((L - lo) / (hi - lo)) + (255,)
            elif k == "grey" and y < zone and L > 18:
                qx[x, y] = ramp((L - lo) / (hi - lo) * 0.85 + 0.05) + (255,)     # bald scalp
    return q, hi_


def scale_frame(p):
    bb = bbox(p)
    if not bb:
        return p, (0, 0)
    x0, y0, x1, y1 = bb
    ax, ay = (x0 + x1) / 2.0, float(y1)                    # feet anchor
    W, H = p.size
    big = p.convert("RGBa").resize((int(round(W * SCALE)), int(round(H * SCALE))), Image.BICUBIC).convert("RGBA")
    a = big.split()[3].point(lambda v: 255 if v >= 110 else 0)
    big.putalpha(a)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ox, oy = int(round(ax - ax * SCALE)), int(round(ay - ay * SCALE))
    out.alpha_composite(big, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy)))
    return out, (ox, oy)


def eye(p, hx, hy, d):
    """the cyclops eye centred at (hx, hy) (already scaled coords); d = direction (shift toward facing side)"""
    dr = ImageDraw.Draw(p)
    x = int(round(hx + {1: 1, 2: 1, 6: -1}.get(d, 0)))
    y = int(round(hy))
    px = p.load()
    def put(a, b, c):
        if 0 <= a < p.width and 0 <= b < p.height and px[a, b][3]:
            px[a, b] = c
    brow, white, shade, iris, pupil, lid = ((34, 20, 18, 255), (246, 242, 230, 255), (196, 188, 172, 255),
                                            (176, 120, 24, 255), (8, 6, 6, 255), (70, 40, 34, 255))
    for a in range(x - 3, x + 3):                          # heavy brow ridge
        put(a, y - 3, brow)
    for a in range(x - 2, x + 2):                          # round eye: 4 / 4 / 2 rows
        put(a, y - 2, white if a in (x - 1, x) else shade)
        put(a, y - 1, white)
    put(x - 1, y, white); put(x, y, shade)
    put(x - 1, y - 1, iris); put(x, y - 1, iris)           # amber iris with a black pupil
    put(x - 1, y - 2, pupil if False else white)
    put(x, y - 1, pupil)
    for a in range(x - 2, x + 2):                          # lower lid
        put(a, y + 1, lid)


def main():
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
    tr = load(TROLL)
    sk = [lum(c[:3]) for p in tr.values() for c in p.getdata() if c[3] and kind(c[:3]) == "skin"]
    sk.sort()
    lo, hi = sk[len(sk) // 50], sk[-len(sk) // 100]
    frames = {}
    for fid, p in sorted(tr.items()):
        d = fid // 100
        q, hinfo = recolour(p, lo, hi)
        q, (ox, oy) = scale_frame(q)
        if d in FRONT and hinfo:
            cx, hb, _z = hinfo
            eye(q, cx * SCALE + ox, (hb + 3) * SCALE + oy, d)
        frames[fid] = q
        q.save(os.path.join(OUT, "frames", "%d.png" % fid))
    # preview: all frames 3x on grass-ish bg, and a 1x comparison strip giant / troll / cyclops
    sc = 3
    ids = sorted(frames)
    S = Image.new("RGB", (12 * 64 * sc, 6 * 64 * sc), (78, 96, 52))
    for k, fid in enumerate(ids):
        d, f = fid // 100 - 1, fid % 100 - 1
        S.paste(frames[fid].resize((64 * sc, 64 * sc), Image.NEAREST), (f * 64 * sc, d * 64 * sc), frames[fid].resize((64 * sc, 64 * sc), Image.NEAREST))
    S.save(os.path.join(OUT, "cyclops_all_3x.png"))
    gi = load(GIANT)
    C = Image.new("RGB", (6 * 64 * 3, 64 * 3 * 3), (78, 96, 52))
    for k, d in enumerate(range(1, 7)):
        for r, src in enumerate((gi, tr, frames)):
            im = src[d * 100 + 1].resize((64 * 3, 64 * 3), Image.NEAREST)
            C.paste(im, (k * 64 * 3, r * 64 * 3), im)
    C.save(os.path.join(OUT, "compare_giant_troll_cyclops_3x.png"))
    Z = Image.new("RGB", (6 * 64 * 8, 64 * 8), (78, 96, 52))
    for k, d in enumerate(range(1, 7)):
        im = frames[d * 100 + 1].resize((64 * 8, 64 * 8), Image.NEAREST)
        Z.paste(im, (k * 64 * 8, 0), im)
    Z.save(os.path.join(OUT, "cyclops_dirs_8x.png"))
    print("frames", len(frames), "skin lum", lo, hi, "->", OUT)


if __name__ == "__main__":
    main()
