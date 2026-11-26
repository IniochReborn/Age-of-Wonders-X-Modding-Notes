#!/usr/bin/env python3
r"""build_ilb_items_x2026_v2.py - rebuild Images\Items\I_x2026.ilb from the user's item art (2026-09-21).

Replaces the 72 procedurally painted icons of build_ilb_items_x2026.py (user: unused, disliked) with the 210
PNGs in `reference files\_2026 new items\` (attack/body/defense/head/ring/use, ~1254x1254, flat green
background with slight noise).  Per image:
  1. chroma key: pixels within RGB distance KEY_TOL of the median border colour that are CONNECTED to the border
     (flood fill) become transparent, plus any pixel within 3/4 of that tolerance anywhere (ring holes); the mask is
     eroded by one quarter-scale pixel to drop green fringes and detached islands under 3 % of the item are dropped
     (translucent smoke/glow over the green) - green parts inside an item survive;
  2. crop to the opaque bounding box and fit it (aspect kept) into the slot's target box, centred on the 41x42
     canvas - targets follow the vanilla clip sizes (I_Attack/Body/Defend/Head/Use fill ~34-39 px, rings ~21);
  3. premultiplied Lanczos downsample, alpha cut at 50 % (the ILB has no alpha), RLESprite16 with the item key
     0x4D2B, exactly like the vanilla item libraries (v4.0, 41x42, type 17, info 3, drawMode 256).
Names: attack01.bmp .. use54.bmp, ids sequential in slot order attack, body, defense, head, ring, use.
Backup of the old library: backup\Images\Items\I_x2026.ilb.bak_v1 (kept once).
usage: py build_ilb_items_x2026_v2.py [--preview sheet.png] [--apply]
"""
import os, sys, struct, argparse, shutil, collections
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "old modding tools", "research"))
import ilbcodec  # noqa: E402
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402

SRC = os.path.join(ROOT, "reference files", "_2026 new items")
OUT = os.path.join(ROOT, "Images", "Items", "I_x2026.ilb")
BW, BH = 41, 42
TRANSP = 19755
PIXFMT = 0x56509310
SOMEID = 0x0040F000
KEY_TOL = 40
SPILL_BAND, SPILL_GREEN = 6, 30   # green-dominant pixels within 6 quarter-px (24 px) of the background are spill
ISLAND_MIN = 0.03           # opaque islands smaller than 3 % of the main item are dropped (smoke/glow flecks)
SLOTS = ["attack", "body", "defense", "head", "ring", "use"]
TARGET = {"attack": (36, 38), "body": (37, 39), "defense": (34, 39), "head": (33, 33), "ring": (22, 21), "use": (34, 34)}


def to565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def rle16(rows, back):
    out = bytearray()
    for row in rows:
        line = bytearray(); run = 0
        for v in row:
            if v == back:
                run += 1
            else:
                if run:
                    line += struct.pack('<HH', back, 2 * run); run = 0
                line += struct.pack('<H', v)
        if run:
            line += struct.pack('<HH', back, 2 * run)
        nvals = len(line) // 2
        out += struct.pack('<I', 2 * nvals + 4) + line
        if nvals % 2:
            out += struct.pack('<H', back)
    return bytes(out)


def key_out(im):
    """RGBA with the connected green background removed."""
    im = im.convert("RGB")
    w, h = im.size
    small = im.resize((w // 4, h // 4), Image.BOX)           # key on a quarter-size copy (speed), upscale the mask
    px = small.load(); sw, sh = small.size
    border = [px[x, y] for x in range(sw) for y in (0, sh - 1)] + [px[x, y] for y in range(sh) for x in (0, sw - 1)]
    med = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    def isbg(p):
        return abs(p[0] - med[0]) + abs(p[1] - med[1]) + abs(p[2] - med[2]) <= KEY_TOL
    mask = bytearray(sw * sh)                                 # 1 = background
    stack = [(x, y) for x in range(sw) for y in (0, sh - 1)] + [(x, y) for y in range(sh) for x in (0, sw - 1)]
    for x, y in stack:
        mask[y * sw + x] = 2 if isbg(px[x, y]) else 0
    stack = [(x, y) for x, y in stack if mask[y * sw + x] == 2]
    while stack:
        x, y = stack.pop()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < sw and 0 <= ny < sh and mask[ny * sw + nx] == 0 and isbg(px[nx, ny]):
                mask[ny * sw + nx] = 2; stack.append((nx, ny))
    # enclosed background (ring holes etc.): any pixel very close to the key colour is background too
    tight = KEY_TOL * 3 // 4
    for i in range(sw * sh):
        if not mask[i]:
            p = px[i % sw, i // sw]
            if abs(p[0] - med[0]) + abs(p[1] - med[1]) + abs(p[2] - med[2]) <= tight:
                mask[i] = 1
    # drop small detached islands (translucent smoke/glow over the green reads as green flecks): keep only
    # components >= ISLAND_MIN of the largest one
    comp = [0] * (sw * sh); sizes = []; nid = 0
    for i0 in range(sw * sh):
        if mask[i0] or comp[i0]:
            continue
        nid += 1; comp[i0] = nid; st = [i0]; n = 0
        while st:
            i = st.pop(); n += 1; x, y = i % sw, i // sw
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < sw and 0 <= ny < sh:
                    j = ny * sw + nx
                    if not mask[j] and not comp[j]:
                        comp[j] = nid; st.append(j)
        sizes.append(n)
    big = max(sizes) if sizes else 0
    for i in range(sw * sh):
        if comp[i] and sizes[comp[i] - 1] < big * ISLAND_MIN:
            mask[i] = 1
    # green-aware edge erosion: green-dominant pixels within SPILL_BAND quarter-px of the background are spill
    # (translucent smoke/glow/antialiasing blended with the key), never item colour -> background
    bg = Image.frombytes("L", (sw, sh), bytes(255 if v else 0 for v in mask))
    band = bg
    for _ in range(SPILL_BAND):
        band = band.filter(ImageFilter.MaxFilter(3))
    bp = band.load()
    for i in range(sw * sh):
        if not mask[i] and bp[i % sw, i // sw]:
            r, g, b = px[i % sw, i // sw]
            if g > r + SPILL_GREEN and g > b + SPILL_GREEN:
                mask[i] = 1
    m = Image.frombytes("L", (sw, sh), bytes(0 if v else 255 for v in mask))
    m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))   # close pinholes
    m = m.filter(ImageFilter.MinFilter(3))                                    # erode 1 quarter-px: kills green fringes
    m = m.resize((w, h), Image.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
    out = im.convert("RGBA"); out.putalpha(m)
    return out, med


def fit_icon(rgba, slot):
    bb = rgba.split()[3].getbbox()
    if not bb:
        raise ValueError("nothing left after keying")
    obj = rgba.crop(bb)
    tw, th = TARGET[slot]
    sc = min(tw / obj.width, th / obj.height)
    nw, nh = max(1, round(obj.width * sc)), max(1, round(obj.height * sc))
    # premultiplied downsample so the key colour never bleeds into edges
    r, g, b, a = obj.split()
    pre = Image.merge("RGB", tuple(ch.point(lambda v: v) for ch in (r, g, b)))
    pre = Image.composite(pre, Image.new("RGB", obj.size, (0, 0, 0)), a)
    pre = pre.resize((nw, nh), Image.LANCZOS); a2 = a.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    ox, oy = (BW - nw) // 2, (BH - nh) // 2
    pp, ap = pre.load(), a2.load()
    for y in range(nh):
        for x in range(nw):
            al = ap[x, y]
            if al >= 128:
                pr, pg, pb = pp[x, y]
                out.putpixel((ox + x, oy + y), (min(255, pr * 255 // al), min(255, pg * 255 // al), min(255, pb * 255 // al), 255))
    return out


def encode_icon(im):
    px = im.load(); bb = im.split()[3].getbbox()
    x0, y0, x1, y1 = bb; rows = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a == 0:
                row.append(TRANSP)
            else:
                v = to565(r, g, b)
                if v == TRANSP:
                    v ^= 1
                row.append(v)
        rows.append(row)
    return rle16(rows, TRANSP), (x1 - x0, y1 - y0, x0, y0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default=os.path.join(HERE, "I_x2026_v2_preview.png"))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    files = []
    for slot in SLOTS:
        ns = sorted(int(f[len(slot):-4]) for f in os.listdir(SRC) if f.startswith(slot) and f[len(slot):-4].isdigit() and f.endswith(".png"))
        files += [(slot, n, os.path.join(SRC, f"{slot}{n}.png")) for n in ns]
    print(f"source: {SRC}: {len(files)} images {dict(collections.Counter(s for s, _, _ in files))}")
    icons = []; keys = collections.Counter()
    for slot, n, path in files:
        rgba, med = key_out(Image.open(path)); keys[med] += 1
        icons.append((f"{slot}{n:02d}.bmp", fit_icon(rgba, slot)))
    print("background keys:", keys.most_common(4))
    images = []; blob = bytearray()
    for idx, (name, im) in enumerate(icons):
        data, (cw, ch, cx, cy) = encode_icon(im)
        rec = ilbcodec.Rec(type=17, info=3, name=name.encode('latin1'), w=BW, h=BH, xs=0, ys=0, sub=0,
                           unkA=1, size=len(data), off=len(blob), totw=BW, toth=BH,
                           drawMode=256, blendValue=0, pixFmt=PIXFMT,
                           cw=cw, ch=ch, cx=cx, cy=cy, transp=TRANSP, clip_x=0)
        images.append({'id': idx, 'composite': False, 'parts': [rec], 'empty': False}); blob += data
    lib = {'someId': SOMEID, 'version': 4.0, 'hdrLength': 24, 'palettes': [], 'images': images, 'pixeldata': bytes(blob)}
    raw = ilbcodec.write(lib)
    chk = ilbcodec.read(raw); assert ilbcodec.write(chk) == raw and len(chk['images']) == len(icons)
    cols, sc = 15, 3; TW, TH = BW * sc + 4, BH * sc + 14
    rows = (len(icons) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * TW, rows * TH), (70, 60, 50, 255))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(icons):
        x, y = (i % cols) * TW, (i // cols) * TH
        sheet.alpha_composite(im.resize((BW * sc, BH * sc), Image.NEAREST), (x + 2, y))
        dr.text((x + 2, y + BH * sc), f"{i} {name[:-4]}", fill=(255, 255, 0, 255))
    sheet.save(a.preview); print("preview:", a.preview)
    print(f"library: {len(raw)} B, {len(icons)} images")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return 0
    bak = bak_path(OUT, ".bak_v1")
    if os.path.exists(OUT) and not os.path.exists(bak):
        shutil.copy2(OUT, bak); print("backup ->", bak)
    open(OUT, "wb").write(raw); print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
