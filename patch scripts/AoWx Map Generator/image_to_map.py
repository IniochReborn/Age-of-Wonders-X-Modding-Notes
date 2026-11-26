# -*- coding: utf-8 -*-
"""
AoWx image -> map: turn a top-down picture into a playable AoW1 map.

Same template-rewrite + verbatim-decor machinery as generate_map_v3, but the terrain grid
comes from classifying each hex's average colour in a source image instead of noise.
Vegetation (dark-green -> forest) and mountains (brown) also follow the image.

Usage:  py "patch scripts/mapgen/image_to_map.py" <image> [S|M|L|XL]
Writes: Scenario/Custom/xImageMap <SIZE>.hsm   + prints an ASCII preview.

Colour -> terrain (HSV based; tuneable in classify()):
  blue                 -> Water        green            -> Grass (dark/saturated -> Forest)
  yellow / tan         -> Desert       brown (dark red) -> Mountains
  grey / white (urban) -> Grass        very pale cold   -> Snow  (only if you want it)
"""
import struct, zlib, random, sys, os, pickle, colorsys

if len(sys.argv) < 2:
    raise SystemExit('usage: image_to_map.py <image> [S|M|L|XL]')
IMG = sys.argv[1]
SIZE = (sys.argv[2].upper() if len(sys.argv) > 2 else 'S')
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = {'S': os.path.join(HERE,'xTemplate Small.hsm'), 'M': os.path.join(HERE,'xTemplate Medium.hsm'),
             'L': os.path.join(HERE,'xTemplate Large.hsm'), 'XL': os.path.join(HERE,'xTemplate XLarge.hsm')}
TEMPLATE = TEMPLATES.get(SIZE, TEMPLATES['S'])
if not os.path.exists(TEMPLATE):
    raise SystemExit('missing template %s (paint an empty-grass map that size)' % TEMPLATE)
OUT = 'Scenario/Custom/xImageMap %s.hsm' % SIZE
SEED = 1234

VEGREC = {t: [bytes.fromhex(h) for h in v]
          for t, v in pickle.load(open(os.path.join(HERE, 'veg_records.pkl'), 'rb')).items()}
MTNREC = {t: [bytes.fromhex(h) for h in v]
          for t, v in pickle.load(open(os.path.join(HERE, 'mtn_records.pkl'), 'rb')).items()}

def tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F; f = {}
    for _ in range(nb):
        f[dd[p]] = dd[p+1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from('<II', dd, p); f[t] = o; p += 8
    return f, p

def tbl_entry_pos(dd, p, want):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F
    for _ in range(nb):
        if dd[p] == want: return ('u8', p + 1)
        p += 2
    for _ in range(nd):
        if struct.unpack_from('<I', dd, p)[0] == want: return ('u32', p + 4)
        p += 8
    return None

def load_variants():
    d = open('Release/Release.hss', 'rb').read()
    root, base = tbl(d, 0x37); f5, b5 = tbl(d, base + root[5]); kids, kb = tbl(d, b5 + f5[1])
    var = {}
    for cid, off in sorted(kids.items()):
        cls = struct.unpack_from('<I', d, kb + off)[0]
        if cls not in (0x20153, 0x2073E): continue
        f, b1 = tbl(d, kb + off + 4)
        if 1 not in f or 7 not in f or struct.unpack_from('<I', d, b1 + f[7])[0] != 1: continue
        var.setdefault(d[b1 + f[7] + 4], []).append((cls, struct.unpack_from('<I', d, b1 + f[1])[0]))
    for t in (0, 6):
        anim = [v for v in var.get(t, []) if v[0] == 0x2073E]
        if anim: var[t] = anim
    return var

# ---------------------------------------------------------------- colour -> (terrain, decor)
# decor: None / 'veg' / 'mtn'. Terrain ints match Release.hss (0 water,1 grass,2 desert,3 snow,
# 4 steppe,5 wasteland,9 lava,12 dirt). San Andreas has no snow -> grey urban maps to grass.
def classify(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
    if s < 0.16:                                   # greyscale: roads / urban / bare
        return (1, None)                           # -> grass (change to 3 for snowy pictures)
    if 0.45 < h < 0.75:                            # blue
        return (0, None)                           # water
    if 0.20 <= h <= 0.45:                          # green
        return (1, 'veg' if (v < 0.55 or s > 0.55) else None)   # dark/vivid green -> forest
    if 0.06 <= h < 0.14 and v < 0.55:              # dark tan/brown
        return (2, 'mtn')                          # mountains sit on desert base
    if 0.02 <= h < 0.14:                           # yellow / tan
        return (2, None)                           # desert
    if (h < 0.05 or h > 0.92) and v < 0.5:         # dark red-brown
        return (2, 'mtn')
    return (1, None)                               # fallback -> grass

# ---------------------------------------------------------------- load template + image
rnd = random.Random(SEED)
terr_var = load_variants()
inner = bytearray(zlib.decompress(open(TEMPLATE, 'rb').read()[5:]))
root, base = tbl(inner, 0x13)
kids, kb = tbl(inner, base + root[1])
coff = kb + sorted(kids.items(), key=lambda x: x[1])[0][1]
cf, cb = tbl(inner, coff + 4)
W, H = inner[cb + cf[3]], inner[cb + cf[4]]
lvls = sorted(tbl(inner, cb + cf[1])[0].items())
lk, lkb = tbl(inner, cb + cf[1])
loff = lkb + dict(lvls)[0]
lf, lb = tbl(inner, loff + 4)
s, e = lb + 2, lb + lf[1]

# which hexes are paintable interior + their bounding box (image is fitted to it)
paint = [[False] * W for _ in range(H)]
q, idx = s, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    if L == 14 and struct.unpack_from('<H', inner, q + 4 + 3)[0] != 0x0557:
        paint[idx // W][idx % W] = True
    q += 4 + L; idx += 1
xs = [x for y in range(H) for x in range(W) if paint[y][x]]
ys = [y for y in range(H) for x in range(W) if paint[y][x]]
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
iw, ih = x1 - x0 + 1, y1 - y0 + 1

from PIL import Image
src = Image.open(IMG).convert('RGB')
# center-crop to the interior aspect, then resize to the interior grid
sw, sh = src.size
target = iw / ih
if sw / sh > target:
    nw = int(sh * target); src = src.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
else:
    nh = int(sw / target); src = src.crop((0, (sh - nh) // 2, sw, (sh - nh) // 2 + nh))
src = src.resize((iw, ih), Image.BILINEAR)
sp = src.load()

grid = [[None] * W for _ in range(H)]
decor = [[None] * W for _ in range(H)]
for y in range(H):
    for x in range(W):
        if not paint[y][x]: continue
        r, g, b = sp[x - x0, y - y0]
        t, dc = classify(r, g, b)
        if not VEGREC.get(t) and t not in (0,):     # terrain we lack records for -> grass
            t = 1
        grid[y][x] = t
        decor[y][x] = dc

# de-speckle terrain (mild — keep image detail) : lone hex -> neighbour majority
def smooth(g):
    ng = [row[:] for row in g]
    for y in range(H):
        for x in range(W):
            if g[y][x] is None: continue
            cnt = {}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < H and 0 <= nx < W and g[ny][nx] is not None:
                        cnt[g[ny][nx]] = cnt.get(g[ny][nx], 0) + 1
            if cnt.get(g[y][x], 0) <= 2:            # only replace true outliers
                ng[y][x] = max(cnt, key=cnt.get)
    return ng
grid = smooth(grid)

def child(res_cls, uid):
    return struct.pack('<I', res_cls - 1) + b'\x01\x01\x00' + struct.pack('<I', uid)
def place(payload, x, y):
    rec = bytearray(payload)
    ct, cbb = tbl(rec, 16 + 4)
    if 3 in ct: rec[cbb + ct[3]] = x & 0xFF
    if 4 in ct: rec[cbb + ct[4]] = y & 0xFF
    return bytes(rec)

new_stream = bytearray(); q, idx = s, 0
nveg = nmtn = 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    x, y = idx % W, idx // W
    if paint[y][x]:
        t = grid[y][x]; dc = decor[y][x]
        if dc == 'mtn' and MTNREC.get(t):
            new_stream += struct.pack('<I', 33) + place(rnd.choice(MTNREC[t]), x, y); nmtn += 1
        elif dc == 'veg' and VEGREC.get(t):
            new_stream += struct.pack('<I', 33) + place(rnd.choice(VEGREC[t]), x, y); nveg += 1
        else:
            hcls, huid = rnd.choice(terr_var[t])
            new_stream += struct.pack('<I', 14) + b'\x01\x32\x00' + child(hcls, huid)
    else:
        new_stream += struct.pack('<I', L) + bytes(inner[q + 4:q + 4 + L])
    q += 4 + L; idx += 1

delta = len(new_stream) - (e - s)
out = bytearray(inner[:s]) + new_stream + inner[e:]
kind, pos = tbl_entry_pos(out, loff + 4, 1)
struct.pack_into('<I', out, pos, struct.unpack_from('<I', out, pos)[0] + delta)
for lid, lo in lvls:
    if lkb + lo > loff:
        k2, p2 = tbl_entry_pos(out, cb + cf[1], lid)
        v = struct.unpack_from('<I', out, p2)[0] if k2 == 'u32' else out[p2]
        if k2 == 'u32': struct.pack_into('<I', out, p2, v + delta)
        else: out[p2] = v + delta

open(OUT, 'wb').write(b'CFS\x00\x02' + zlib.compress(bytes(out), 9))
CH = {0: '~', 1: '.', 2: 'd', 3: '*', 4: ',', 5: 'w', 9: 'L', None: ' '}
import collections
counts = collections.Counter(grid[y][x] for y in range(H) for x in range(W) if grid[y][x] is not None)
NM = {0: 'Water', 1: 'Grass', 2: 'Desert', 3: 'Snow', 4: 'Steppe', 5: 'Wasteland', 9: 'Lava'}
print('%s -> %s  %dx%d | veg %d mtn %d' % (os.path.basename(IMG), OUT, W, H, nveg, nmtn))
print(' | '.join('%s %d' % (NM.get(t, t), n) for t, n in sorted(counts.items())))
print()
for y in range(H):
    print(''.join(('^' if decor[y][x] == 'mtn' else 'T' if decor[y][x] == 'veg' else CH[grid[y][x]])
                   for x in range(W)))
