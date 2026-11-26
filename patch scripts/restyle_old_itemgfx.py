#!/usr/bin/env python3
r"""
Restyle flat old item graphics toward the vanilla/2026 painterly look and write them back into their ILBs
(2026-09-22).  Targets (Item GFX id -> library frame): 117 gold plate (I_custom1 #12), 142 trident
(I_Zigad #68), 228 knight helm (I_custom1 #16), 229 monster mask (I_custom1 #18).

Restyle (works on the 41x42 icon, 8x supersampled): 1-px near-black outline around the silhouette, ambient
occlusion / edge darkening from a distance transform, top-left key light (brighten) + bottom-right shadow,
local contrast + saturation lift, gentle grain, specular pop on the brightest 8 %, then Lanczos back to 41x42.
Records are re-encoded with the library's own key (I_custom1 0x4D2B, I_Zigad 0xFF) and the record offsets
rebuilt; every other record's bytes are kept verbatim.  Backups Images\Items\<lib>.bak_restyle (in <game>\backup\).
usage: py restyle_old_itemgfx.py [--preview sheet.png] [--apply] [--revert]
"""
import os, sys, struct, argparse, shutil, math, random
from PIL import Image, ImageFilter, ImageEnhance, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "old modding tools", "research")); import ilbcodec  # noqa
sys.path.insert(0, HERE); from bakpath import bak_path  # noqa

TARGETS = {117: ("I_custom1.ilb", 12), 142: ("I_Zigad.ilb", 68), 228: ("I_custom1.ilb", 16), 229: ("I_custom1.ilb", 18)}
BW, BH, S = 41, 42, 8


def rgb(v): return ((v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3)
def to565(r, g, b): return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def decode(lib, r):
    px = lib['pixeldata']; data = px[r['off']:r['off'] + r['size']]; o = 0; back = r['transp']; rows = []
    for y in range(r['ch']):
        ln = struct.unpack_from("<I", data, o)[0]; s = data[o + 4:o + ln]; o += ln
        if ((ln - 4) // 2) % 2 == 1:
            o += 2
        row = []; k = 0
        while k + 1 < len(s):
            v = struct.unpack_from("<H", s, k)[0]; k += 2
            if v == back:
                cnt = struct.unpack_from("<H", s, k)[0] // 2; k += 2; row += [None] * cnt
            else:
                row.append(v)
        rows.append(row[:r['cw']])
    return rows


def to_rgba(lib, fr):
    r = lib['images'][fr]['parts'][0]; im = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    for y, row in enumerate(decode(lib, r)):
        for x, v in enumerate(row):
            if v is not None:
                im.putpixel((r['cx'] + x, r['cy'] + y), rgb(v) + (255,))
    return im


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
        n = len(line) // 2; out += struct.pack('<I', 2 * n + 4) + line
        if n % 2:
            out += struct.pack('<H', back)
    return bytes(out)


def encode(im, back):
    px = im.load(); x0, y0, x1, y1 = im.split()[3].getbbox(); rows = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a < 128:
                row.append(back)
            else:
                v = to565(r, g, b); row.append(v ^ 1 if v == back else v)
        rows.append(row)
    return rle16(rows, back), (x1 - x0, y1 - y0, x0, y0)


def restyle(im, seed=1, thin=False):
    big = im.resize((BW * S, BH * S), Image.LANCZOS)
    a = big.split()[3].point(lambda v: 255 if v >= 128 else 0)
    # distance-to-edge (approx via repeated erosion), 0 at the border .. 1 deep inside
    dist = Image.new("L", a.size, 0); cur = a
    for k in range(1, 13):
        cur = cur.filter(ImageFilter.MinFilter(5))
        dist = ImageChops.lighter(dist, cur.point(lambda v, k=k: min(255, k * 21) if v else 0))
    dist = dist.filter(ImageFilter.GaussianBlur(3))
    rgb_ = big.convert("RGB")
    rgb_ = ImageEnhance.Contrast(rgb_).enhance(1.45)
    rgb_ = ImageEnhance.Color(rgb_).enhance(1.25)
    # bevel: emboss of the blurred silhouette lit from the top-left (adds volume to flat sources)
    soft = a.filter(ImageFilter.GaussianBlur(S * 1.6)); sp = soft.load(); W0, H0 = soft.size
    bev = Image.new('L', (W0, H0), 128); bp = bev.load(); d = S
    for y in range(H0):
        for x in range(W0):
            gx = sp[min(W0 - 1, x + d), y] - sp[max(0, x - d), y]; gy = sp[x, min(H0 - 1, y + d)] - sp[x, max(0, y - d)]
            bp[x, y] = max(0, min(255, 128 + (gx + gy) * 3 // 4))
    bev3 = Image.merge('RGB', (bev,) * 3)
    if not thin:   # thin objects (trident) keep their edges: no bevel / occlusion
        rgb_ = ImageChops.add(ImageChops.multiply(rgb_, bev3.point(lambda v: min(255, v + 64))), bev3.point(lambda v: max(0, v - 128) // 2))
        ao = dist.point(lambda v: int(120 + 135 * min(1.0, v / 120.0)))
        rgb_ = Image.composite(rgb_, Image.new("RGB", rgb_.size, (0, 0, 0)), ao)
    # key light top-left, shadow bottom-right
    W, H = rgb_.size; light = Image.new("L", (W, H))
    lp = light.load()
    for y in range(H):
        for x in range(W):
            t = (x / W + y / H) / 2.0
            lp[x, y] = int(255 * (1.18 - 0.42 * t))
    rgb_ = Image.composite(ImageChops.multiply(rgb_, Image.merge("RGB", (light, light, light))),
                           ImageChops.screen(rgb_, Image.merge("RGB", (light.point(lambda v: max(0, v - 200) * 2),) * 3)), light.point(lambda v: 255 if v <= 255 else 0))
    # grain
    rnd = random.Random(seed); g = Image.new("L", (W // 4, H // 4)); gp = g.load()
    for y in range(H // 4):
        for x in range(W // 4):
            gp[x, y] = 128 + rnd.randint(-14, 14)
    g = g.resize((W, H), Image.BILINEAR)
    rgb_ = Image.blend(rgb_, ImageChops.multiply(rgb_, Image.merge("RGB", (g.point(lambda v: v * 2 - 128),) * 3)), 0.35)
    # specular pop: brightest pixels get lifted
    lum = rgb_.convert("L"); hi = lum.point(lambda v: 255 if v > 205 else 0).filter(ImageFilter.GaussianBlur(2))
    rgb_ = Image.composite(ImageChops.add(rgb_, Image.new("RGB", rgb_.size, (40, 40, 30))), rgb_, hi)
    rgb_ = rgb_.filter(ImageFilter.UnsharpMask(radius=4, percent=60, threshold=2))
    out = Image.merge("RGBA", rgb_.split() + (a,))
    # outline: silhouette grown by ~1 icon px, near-black, under the item
    grown = a.filter(ImageFilter.MaxFilter((S if thin else S * 2) + 1))
    base = Image.new("RGBA", out.size, (14, 12, 16, 0)); base.putalpha(grown)
    base.alpha_composite(out)
    small = base.resize((BW, BH), Image.LANCZOS)
    al = small.split()[3].point(lambda v: 255 if v >= 128 else 0); small.putalpha(al)
    return small


def replace_records(lib, repl):
    """repl: {frame: rgba}.  Rebuild pixeldata with the replaced frames re-encoded."""
    px = lib['pixeldata']; recs = []
    for i, img in enumerate(lib['images']):
        for r in ([] if img['empty'] else img['parts']):
            recs.append((r['off'], i, r))
    recs.sort(); newpx = bytearray()
    for off, i, r in recs:
        if r['info'] == 1:
            continue
        if i in repl:
            data, (cw, ch, cx, cy) = encode(repl[i], r['transp'])
            r['cw'], r['ch'], r['cx'], r['cy'] = cw, ch, cx, cy
        else:
            data = px[off:off + r['size']]
        r['off'] = len(newpx); r['size'] = len(data); newpx += data
    lib['pixeldata'] = bytes(newpx)
    return lib


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--preview", default=os.path.join(HERE, "restyle_old_itemgfx_preview.png"))
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); a = ap.parse_args()
    libs = sorted(set(l for l, _ in TARGETS.values()))
    if a.revert:
        for l in libs:
            p = os.path.join(ROOT, "Images", "Items", l); b = bak_path(p, ".bak_restyle")
            if os.path.exists(b):
                shutil.copy2(b, p); print("reverted", p)
        return
    loaded = {l: ilbcodec.read(os.path.join(ROOT, "Images", "Items", l)) for l in libs}
    pairs = []
    for gid, (l, fr) in sorted(TARGETS.items()):
        orig = to_rgba(loaded[l], fr); new = restyle(orig, seed=gid, thin=(gid == 142)); pairs.append((gid, l, fr, orig, new))
    sc = 6; sheet = Image.new("RGBA", (len(pairs) * (BW * sc + 8), 2 * (BH * sc + 6)), (60, 60, 60, 255))
    for k, (gid, l, fr, o, n) in enumerate(pairs):
        sheet.alpha_composite(o.resize((BW * sc, BH * sc), Image.NEAREST), (k * (BW * sc + 8), 0))
        sheet.alpha_composite(n.resize((BW * sc, BH * sc), Image.NEAREST), (k * (BW * sc + 8), BH * sc + 6))
    sheet.save(a.preview); print("preview:", a.preview, "(top originals, bottom restyled)")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    for l in libs:
        p = os.path.join(ROOT, "Images", "Items", l); b = bak_path(p, ".bak_restyle")
        if not os.path.exists(b):
            shutil.copy2(p, b); print("backup ->", b)
        repl = {fr: n for gid, ll, fr, o, n in pairs if ll == l}
        lib = replace_records(loaded[l], repl); raw = ilbcodec.write(lib)
        chk = ilbcodec.read(raw); assert len(chk['images']) == len(lib['images'])
        for fr in repl:
            to_rgba(chk, fr)
        open(p, "wb").write(raw); print(f"wrote {p} ({len(raw)} B), frames {sorted(repl)} replaced")


if __name__ == "__main__":
    main()
