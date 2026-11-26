#!/usr/bin/env python3
r"""
Paints the three AoWDevX toolbar glyphs used by patch_devx_prune_unused_v2.py:

  assets\devx_fog_btn.bmp           eye (the Preview button's own art) partly hidden by a cloud
  assets\devx_prune_heroes_btn.bmp  the "Delete hero" hooded figure + red X over a hex-grid map
  assets\devx_prune_items_btn.bmp   the "Delete item" sword + red X over a hex-grid map

Each is a 64x32 24-bpp BMP: left half = enabled glyph, right half = disabled glyph, exactly
like the editor's other toolbar buttons (TSpeedButton NumGlyphs=2; the bottom-left pixel,
(191,191,191), is the transparent colour).  Source art is lifted from the live exe's DFM
(PreviewBtn / RemoveHeroBtn / DeleteItemBtn Glyph.Data).  Also writes assets\devx_toolbar_preview.png (4x).
"""
import io, os, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
EXE = game_file(r"AoWDevX.exe")
BG = (191, 191, 191)


def glyph_from_exe(name):
    """Glyph.Data of TSpeedButton `name` in the TMAINFORM DFM (4-byte length prefix + BMP)."""
    d = open(EXE, "rb").read()
    lo = d.find(b"TPF0\x09TMainForm")            # other forms carry same-named buttons
    hi = d.find(b"TPF0", lo + 4)
    key = bytes([len(name)]) + name.encode() + b"\x04Left"
    i = d.find(key, lo, hi)
    assert i > 0, name
    j = d.find(b"\x0aGlyph.Data\x0a", i)
    n = struct.unpack_from("<I", d, j + 12)[0]
    blob = d[j + 16 + 4: j + 16 + n]          # skip vaBinary len + TBitmap 4-byte size prefix
    return Image.open(io.BytesIO(blob)).convert("RGB")


def transparent_mask(im, key=None):
    key = key or im.getpixel((0, im.height - 1))
    m = Image.new("L", im.size, 0)
    px, mp = im.load(), m.load()
    for y in range(im.height):
        for x in range(im.width):
            if px[x, y] != key:
                mp[x, y] = 255
    return m


def disabled_version(im, mask):
    """Pale, washed-out greyscale of the art (the editor's disabled glyphs are light grey)."""
    out = Image.new("RGB", im.size, BG)
    op, mp = out.load(), mask.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            if not mp[x, y]:
                continue
            r, g, b = im.getpixel((x, y))
            lum = (r * 299 + g * 587 + b * 114) // 1000
            v = 255 - int((255 - lum) * 0.5)          # compress toward white, keep contrast
            v = max(128, min(250, v))
            op[x, y] = (v, v, v)
    return out


def map_sheet():
    """A 32x32 parchment map with a hex grid; corners left transparent so BG stays unique."""
    im = Image.new("RGB", (32, 32), BG)
    # hex grid (pointy-top, radius 3) on its own layer, clipped to the parchment shape
    import math
    grid = Image.new("RGB", (32, 32), (226, 206, 156))
    gd = ImageDraw.Draw(grid)
    r = 3.2
    for row in range(-1, 7):
        for col in range(-1, 8):
            cx = 4 + col * r * 1.75 + (r * 0.875 if row % 2 else 0)
            cy = 5 + row * r * 1.5
            pts = [(cx + r * math.cos(math.radians(60 * k - 30)), cy + r * math.sin(math.radians(60 * k - 30))) for k in range(6)]
            gd.polygon(pts, outline=(178, 150, 96))
    shape = Image.new("L", (32, 32), 0)
    ImageDraw.Draw(shape).rounded_rectangle((1, 2, 30, 29), radius=4, fill=255)
    im.paste(grid, (0, 0), shape)
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((2, 3, 29, 28), radius=3, outline=(196, 172, 118))
    dr.rounded_rectangle((1, 2, 30, 29), radius=4, outline=(118, 88, 46))
    return im


def compose_over_map(art, key, scale=24, offset=(4, 4)):
    base = map_sheet()
    small = art.resize((scale, scale), Image.LANCZOS)
    # re-key: pixels that were the transparent colour become transparent again after resize
    m = transparent_mask(art, key).resize((scale, scale), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)
    base.paste(small, offset, m)
    return base


def cloud(im, fill, outline, shade, alpha=0.62):
    """A grey cloud filling the lower-right half of the tile, puffy along the diagonal."""
    puffs = [(7, 29, 5), (15, 22, 6), (23, 14, 6), (30, 6, 5)]
    body = Image.new("L", (32, 32), 0)
    bd = ImageDraw.Draw(body)
    bd.polygon([(31, 9), (31, 31), (9, 31)], fill=255)    # the diagonal half; puffs scallop its edge
    for cx, cy, r in puffs:
        bd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    bp, px = body.load(), im.load()
    for y in range(32):
        for x in range(32):
            if not bp[x, y]:
                continue
            edge = any(nx < 0 or ny < 0 or nx > 31 or ny > 31 or not bp[nx, ny]
                       for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
            col = outline if edge else (shade if (x + y) >= 50 else fill)
            a = min(1.0, alpha + 0.2) if edge else alpha          # translucent: the eye shows through
            old = px[x, y]
            px[x, y] = tuple(int(round(c * a + o * (1 - a))) for c, o in zip(col, old))


def fog_icon():
    eye = glyph_from_exe("PreviewBtn")
    on, off = eye.crop((0, 0, 32, 32)), eye.crop((32, 0, 64, 32))
    cloud(on, (96, 98, 106), (48, 50, 56), (72, 74, 82))
    cloud(off, (200, 200, 200), (128, 128, 128), (184, 184, 184))
    out = Image.new("RGB", (64, 32), BG)
    out.paste(on, (0, 0)); out.paste(off, (32, 0))
    return out


def prune_icon(src_name):
    art = glyph_from_exe(src_name)
    key = art.getpixel((0, 31))
    on = compose_over_map(art, key)
    off = disabled_version(on, transparent_mask(on, BG))
    out = Image.new("RGB", (64, 32), BG)
    out.paste(on, (0, 0)); out.paste(off, (32, 0))
    return out


def save_bmp(im, path):
    assert im.getpixel((0, 31)) == BG and im.getpixel((32, 31)) == BG, "bottom-left pixels must be the transparent colour"
    im.save(path, format="BMP")


def main():
    os.makedirs(ASSETS, exist_ok=True)
    icons = {"devx_fog_btn.bmp": fog_icon(), "devx_prune_heroes_btn.bmp": prune_icon("RemoveHeroBtn"),
             "devx_prune_items_btn.bmp": prune_icon("DeleteItemBtn")}
    sheet = Image.new("RGB", (64 * 4 * 3 + 16, 128), (255, 0, 255))
    for k, (name, im) in enumerate(icons.items()):
        save_bmp(im, os.path.join(ASSETS, name))
        sheet.paste(im.resize((256, 128), Image.NEAREST), (k * 264, 0))
        print("wrote", name, im.size)
    sheet.save(os.path.join(ASSETS, "devx_toolbar_preview.png"))


if __name__ == "__main__":
    sys.exit(main())
