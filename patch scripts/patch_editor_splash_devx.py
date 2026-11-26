"""patch_editor_splash_devx.py - rebrand the editor splash (EDIMAGES\\Splash.BMP).

Three edits, everything else byte-identical:
  1. Title "AoWed"  ->  "AoWDevX"   - Age14G glyphs at 1.5x (3x supersample
     halved), black face + gold rim lit from below-right, matching the old art.
  2. Subtitle "Editor for Age of Wonders"  ->  "Editor for Age of Wonders X"
     - Age14G downscaled with the same 0.457 x-squeeze / 13px height as before.
  3. The arm holding the sword in the bottom-right corner (Julia's sword arm
     from the source art) is removed and the scene behind it reconstructed.

Background facts (established 2026-08-26): the splash's bottom band is the
title-screen art - Int\\TitleM.ILB image id 0 (TitleFull.BMP, 640x480) - pasted
at src_x = 1.1225*x - 39, src_y = 1.1275*y + 88 (NCC 0.987). The source can
NOT be used to refill the text zones: in the source that area is a pale stone
face, which the splash author covered with a near-black fill to carry the
text - so the text zones are refilled the same way, by horizontal lerp
between the dark pixels just outside each zone (never sampling the gold
border row above the band). The arm IS part of the source painting (Julia's
sword arm), so that region is clone-inpainted: mountains from the clean strip
between the two spires, valley from the dark ground left of it, with jitter,
band-dependent blur and a feathered mask.

Usage:  py patch_editor_splash_devx.py            (dry run: writes preview PNG)
        py patch_editor_splash_devx.py --apply
        py patch_editor_splash_devx.py --revert
Backup: EDIMAGES\\Splash.BMP.bak_devx  (made before first write)
"""
import math
import os
import random
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
SPLASH = os.path.join(GAME, "EDIMAGES", "Splash.BMP")
BACKUP = SPLASH + ".bak_devx"
sys.path.insert(0, os.path.join(GAME, "modding tools"))
from aowxlib import ilb  # noqa: E402

W, H = 320, 276
PIXOFF = 138            # BITMAPV5, 32bpp BI_BITFIELDS, bottom-up, no padding

TITLE_ZONE = (10, 167, 222, 206)     # old "AoWed" (x0, y0, x1, y1) exclusive
SUB_ZONE = (11, 207, 196, 224)       # old "Editor for Age of Wonders"
TITLE_POS = (10, 167)
SUB_POS = (12, 209)

ARM_POLY = [(250, 276), (250, 260), (252, 235), (254, 215), (258, 200),
            (263, 188), (266, 178), (272, 170), (278, 166), (320, 166),
            (320, 276)]


# --------------------------------------------------------------------------
# BMP in-place pixel access
# --------------------------------------------------------------------------
def read_bmp(raw):
    assert struct.unpack_from("<I", raw, 10)[0] == PIXOFF
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        row = PIXOFF + (H - 1 - y) * W * 4
        for x in range(W):
            b, g, r = raw[row + x * 4: row + x * 4 + 3]
            px[x, y] = (r, g, b)
    return im


def write_pixels(raw, img, box):
    """Write img pixels inside box back into the raw BMP bytes (alpha 255)."""
    out = bytearray(raw)
    px = img.load()
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        row = PIXOFF + (H - 1 - y) * W * 4
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            out[row + x * 4: row + x * 4 + 4] = bytes((b, g, r, 255))
    return bytes(out)


# --------------------------------------------------------------------------
# Age14G text rendering
# --------------------------------------------------------------------------
def load_font():
    lib = ilb.read(os.path.join(GAME, "Int", "Fonts", "Age14G.ILB"))
    gl = {}
    for g in lib.images:
        if not g.empty and g.parts:
            w, h, rows = ilb.decode_record(lib, g.primary)
            gi = Image.new("RGBA", (w, h))
            gi.putdata([p for r in rows for p in r])
            gl[g.id] = gi
    return gl


def compose_native(gl, text, spacing=1):
    ims = [gl[ord(c)] if c != " " else None for c in text]
    tw = sum((i.size[0] if i else 5) + spacing for i in ims) - spacing
    th = max(i.size[1] for i in ims if i)
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    x = 0
    for i in ims:
        if i is None:
            x += 5 + spacing
            continue
        out.alpha_composite(i, (x, th - i.size[1]))
        x += i.size[0] + spacing
    return out


def title_sprite(gl):
    """'AoWDevX': black face + gold rim, built at 3x and halved to 1.5x."""
    random.seed(11)
    Z = 3
    nat = compose_native(gl, "AoWDevX", spacing=0)
    mz = nat.resize((nat.size[0] * Z, nat.size[1] * Z), Image.NEAREST)
    mw, mh = mz.size
    a = mz.load()
    P = Z + 1
    out = Image.new("RGBA", (mw + 2 * P, mh + 2 * P), (0, 0, 0, 0))
    o = out.load()

    def ink(x, y):
        return 0 <= x < mw and 0 <= y < mh and a[x, y][3] > 0

    for y in range(mh):
        for x in range(mw):
            if ink(x, y):
                o[x + P, y + P] = (2, 2, 2, 255)
    for y in range(mh + 2 * P):
        for x in range(mw + 2 * P):
            if o[x, y][3]:
                continue
            sx, sy = x - P, y - P
            below = any(ink(sx, sy - d) for d in range(1, Z + 1))
            right = any(ink(sx - d, sy) for d in range(1, Z))
            if below or right or ink(sx - 1, sy - 1):
                t = 0.62 + 0.22 * math.sin(x * 0.11 + y * 0.23) \
                    + random.uniform(-0.06, 0.06)
                t = max(0.25, min(1.0, t))
                dim, bright = (96, 80, 46), (208, 176, 108)
                o[x, y] = tuple(int(dim[i] + (bright[i] - dim[i]) * t)
                                for i in range(3)) + (255,)
    return out.resize((out.size[0] // 2, out.size[1] // 2), Image.LANCZOS)


def subtitle_sprite(gl):
    nat = compose_native(gl, "Editor for Age of Wonders X", spacing=1)
    return nat.resize((int(nat.size[0] * 0.457), 13), Image.LANCZOS)


# --------------------------------------------------------------------------
# text-zone refill: the author's near-black fill, extended sideways
# --------------------------------------------------------------------------
def fill_horizontal(img, box, seed=5):
    """Lerp each row between the dark pixels just outside the zone (the rows
    above the title are the gold border, so sideways is the safe direction)."""
    rnd = random.Random(seed)
    px = img.load()
    x0, y0, x1, y1 = box

    def avg(xs, y):
        cs = [px[x, y] for x in xs if 0 <= x < W]
        return tuple(sum(c[i] for c in cs) // len(cs) for i in range(3))

    for y in range(y0, y1):
        left = avg((x0 - 1, x0 - 2, x0 - 3), y)
        right = avg((x1, x1 + 1, x1 + 2), y)
        for x in range(x0, x1):
            t = (x - x0 + 1) / (x1 - x0 + 1)
            c = [int(left[i] + (right[i] - left[i]) * t + rnd.uniform(-3, 3))
                 for i in range(3)]
            px[x, y] = tuple(max(0, min(255, v)) for v in c)


# --------------------------------------------------------------------------
# arm removal
# --------------------------------------------------------------------------
def fill_arm(img):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(ARM_POLY, fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(5))
    ImageDraw.Draw(mask).rectangle([0, 0, W, 165], fill=0)  # keep gold border

    rnd = random.Random(3)
    mk = mask.load()
    jit = {}

    def jitter(x, y):
        k = (x // 6, y // 6)
        if k not in jit:
            jit[k] = rnd.randint(-2, 2)
        return jit[k]

    filled = img.copy()
    fp = filled.load()
    for x in range(230, 320):
        for y in range(166, 276):
            if not mk[x, y]:
                continue
            if y < 213 + jitter(x + 31, y):
                # mountain band: clean strip x185..232 between the two spires
                off = 65 if x < 300 + jitter(x, y + 57) * 2 else 115
                sy = min(212, max(168, y + jitter(x, y)))
            else:
                off = 55
                sy = min(275, max(215, y + jitter(x, y)))
            fp[x, y] = fp[x - off, sy]

    blur_hi = filled.filter(ImageFilter.GaussianBlur(1.0))
    blur_lo = filled.filter(ImageFilter.GaussianBlur(1.6))
    grad = Image.new("L", img.size, 0)
    gd = ImageDraw.Draw(grad)
    for y in range(166, 276):
        v = 0 if y < 205 else min(255, int((y - 205) * 255 / 30))
        gd.line([0, y, W, y], fill=v)
    blur = Image.composite(blur_lo, blur_hi, grad)
    soft = mask.filter(ImageFilter.GaussianBlur(1.5))
    out = Image.composite(blur, img, soft)
    img.paste(out)


# --------------------------------------------------------------------------
def build(preview_only):
    raw = open(BACKUP if os.path.exists(BACKUP) else SPLASH, "rb").read()
    img = read_bmp(raw)
    gl = load_font()
    # arm first: its clone sources overlap the title zone, and must see the
    # original dark-on-dark old title there, not the freshly drawn new one
    fill_arm(img)
    fill_horizontal(img, TITLE_ZONE, seed=5)
    fill_horizontal(img, SUB_ZONE, seed=6)
    rgba = img.convert("RGBA")
    rgba.alpha_composite(title_sprite(gl), TITLE_POS)
    rgba.alpha_composite(subtitle_sprite(gl), SUB_POS)
    img = rgba.convert("RGB")

    out = write_pixels(raw, img, (0, 160, W, H))
    pv = os.path.join(HERE, "splash_devx_preview.png")
    img.save(pv)
    if preview_only:
        print("dry run - preview written to", pv)
        return None
    return out


def main():
    apply_ = "--apply" in sys.argv
    if "--revert" in sys.argv:
        if not os.path.exists(BACKUP):
            print("no backup found -", BACKUP)
            return 1
        open(SPLASH, "wb").write(open(BACKUP, "rb").read())
        print("reverted from", BACKUP)
        return 0
    out = build(preview_only=not apply_)
    if apply_:
        if not os.path.exists(BACKUP):
            open(BACKUP, "wb").write(open(SPLASH, "rb").read())
            print("backup ->", BACKUP)
        open(SPLASH, "wb").write(out)
        print("applied ->", SPLASH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
