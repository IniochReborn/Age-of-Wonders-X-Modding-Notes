# -*- coding: utf-8 -*-
"""
AoWx image -> map (gen5): turn a top-down picture into a FULL playable AoW1 map.

The picture drives terrain, forests and mountain ranges; everything else comes from
the gen5 engine (generate_map_v4.py in image mode): cities/objects, roads with
bridges, ice near snow, cave systems + underground + depths, teleporters, and all
footprint rules. Different seeds re-roll the objects on the same picture.

Usage:  py "patch scripts/mapgen/image_to_map.py" <image> [S|M|L|XL] [seed]
Writes: Scenario/Custom/xImg6 <SIZE>.hsm

Colour -> terrain (HSV based; tuneable in classify()):
  blue                 -> Water        green            -> Grass (dark/vivid -> Forest)
  yellow / tan         -> Desert       brown (dark red) -> Mountains (on desert base)
  grey / white (urban) -> Grass        (swap grey to 3 for snowy pictures -> ice forms)
"""
import struct, zlib, random, sys, os, pickle, colorsys, subprocess

if len(sys.argv) < 2:
    raise SystemExit('usage: image_to_map.py <image> [S|M|L|XL] [seed]')
IMG = sys.argv[1]
SIZE = (sys.argv[2].upper() if len(sys.argv) > 2 else 'S')
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else random.randrange(1 << 30)
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, '..', '..'))
os.chdir(GAME)
TEMPLATES = {'S': 'Scenario/Custom/xTemplate Small.hsm', 'M': 'Scenario/Custom/xTemplate Medium.hsm',
             'L': 'Scenario/Custom/xTemplate Large.hsm', 'XL': 'Scenario/Custom/xTemplate XLarge.hsm'}
TEMPLATE = TEMPLATES.get(SIZE, TEMPLATES['S'])
if not os.path.exists(TEMPLATE):
    raise SystemExit('missing template %s (paint an empty-grass map that size)' % TEMPLATE)

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

# ---------------------------------------------------------------- colour -> (terrain, decor)
# decor: None / 'veg' / 'mtn'. Terrain ints match Release.hss (0 water,1 grass,2 desert,
# 3 snow,4 steppe,5 wasteland,9 lava,12 dirt).
def classify(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r/255.0, g/255.0, b/255.0)
    if s < 0.16:                                   # greyscale: roads / urban / bare
        return (1, None)                           # -> grass (change to 3 for snowy pictures)
    if 0.45 < h < 0.75:                            # blue
        return (0, None)                           # water
    if 0.20 <= h <= 0.45:                          # green: only DARK green is forest
        return (1, 'veg' if (v < 0.50 or (s > 0.70 and v < 0.68)) else None)
    if (h < 0.065 or h > 0.92) and s > 0.35:       # red-brown rock (Death Mountain style)
        return (2, 'mtn')                          # mountains sit on desert base
    if 0.06 <= h < 0.14 and v < 0.55:              # dark tan/brown
        return (2, 'mtn')
    if 0.02 <= h < 0.14:                           # yellow / tan
        return (2, None)                           # desert
    return (1, None)                               # fallback -> grass

# ---------------------------------------------------------------- template paint mask
inner = zlib.decompress(open(TEMPLATE, 'rb').read()[5:])
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

# ---------------------------------------------------------------- fit + classify image
from PIL import Image
src = Image.open(IMG).convert('RGB')
sw, sh = src.size
target = iw / ih
if sw / sh > target:
    nw = int(sh * target); src = src.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
else:
    nh = int(sw / target); src = src.crop((0, (sh - nh) // 2, sw, (sh - nh) // 2 + nh))
src = src.resize((iw, ih), Image.BILINEAR)
sp = src.load()

grid = [[None] * W for _ in range(H)]
vegset, mtnset = set(), set()
for y in range(H):
    for x in range(W):
        if not paint[y][x]: continue
        r, g, b = sp[x - x0, y - y0]
        t, dc = classify(r, g, b)
        grid[y][x] = t
        if dc == 'veg': vegset.add((x, y))
        elif dc == 'mtn': mtnset.add((x, y))

# de-speckle (mild — keeps image detail): lone-hex outliers -> neighbour majority
ng = [row[:] for row in grid]
for y in range(H):
    for x in range(W):
        if grid[y][x] is None: continue
        cnt = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] is not None:
                    cnt[grid[ny][nx]] = cnt.get(grid[ny][nx], 0) + 1
        if cnt.get(grid[y][x], 0) <= 2:
            ng[y][x] = max(cnt, key=cnt.get)
grid = ng

# ---------------------------------------------------------------- hand off to gen5
ov_path = os.path.join(HERE, '_img_override.pkl')
pickle.dump(dict(grid=grid, veg=vegset, mtn=mtnset, image=os.path.basename(IMG)),
            open(ov_path, 'wb'))
print('%s -> %dx%d grid (%d forest, %d mountain hexes); running gen5 seed %d...'
      % (os.path.basename(IMG), W, H, len(vegset), len(mtnset), SEED))
env = dict(os.environ, AOW_IMG_OVERRIDE=ov_path)
r = subprocess.run([sys.executable, os.path.join(HERE, 'generate_map_v4.py'),
                    str(SEED), SIZE], cwd=GAME, env=env, text=True,
                   capture_output=True)
print(r.stdout)
if r.returncode != 0:
    print(r.stderr[-1500:])
    raise SystemExit('gen5 failed')
