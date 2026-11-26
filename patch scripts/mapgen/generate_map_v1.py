# -*- coding: utf-8 -*-
"""
AoWx random map generator — PROTOTYPE v1 (terrain only).

Rewrites the terrain of an editor-made template .hsm in place (template-rewrite approach,
see memory hsm-map-format.md). Every painted hex keeps its 14-byte record size, so no
offset fixups are needed anywhere: we only swap each hex's (classword, resourceUID).

Usage (from game root):
    py "patch scripts/mapgen/generate_map_v1.py" [seed]
Reads  : Scenario/Custom/xTest Grass.hsm   (fully-painted 48x48 template)
         Release/Release.hss               (terrain-variant resource UIDs)
Writes : Scenario/Custom/xGenerated.hsm

Terrain model: fractal value-noise elevation + climate.
  elevation < sea level        -> Water (0)
  otherwise by climate band    -> Snow (3) / Steppe (4) / Grass (1) / Desert (2)
  blight noise pockets         -> Wasteland (5), with rare Lava (9) cores
Water/ice use the animated hexagon class (0x2073E); land uses fixed class (0x20153),
picking a random tile variant per hex like the editor brush does.
"""
import struct, zlib, random, sys, os

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(1 << 30)
TEMPLATE = 'Scenario/Custom/xTest Grass.hsm'
OUT = 'Scenario/Custom/xGenerated.hsm'

# ---------------------------------------------------------------- HSS helpers
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

# ---------------------------------------------------------------- terrain variant UIDs
def load_variants():
    d = open('Release/Release.hss', 'rb').read()
    root, base = tbl(d, 0x37)
    f5, b5 = tbl(d, base + root[5])
    kids, kb = tbl(d, b5 + f5[1])
    var = {}                       # terrain byte -> list of (classid, uid)
    for cid, off in sorted(kids.items()):
        cls = struct.unpack_from('<I', d, kb + off)[0]
        if cls not in (0x20153, 0x2073E):
            continue
        f, b1 = tbl(d, kb + off + 4)
        if 1 not in f or 7 not in f:
            continue
        uid = struct.unpack_from('<I', d, b1 + f[1])[0]
        cnt = struct.unpack_from('<I', d, b1 + f[7])[0]
        if not (1 <= cnt <= 4):
            continue
        terr = d[b1 + f[7] + 4]
        var.setdefault(terr, []).append((cls, uid))
    # water & ice: prefer the animated class (what the editor brush uses)
    for t in (0, 6):
        anim = [v for v in var.get(t, []) if v[0] == 0x2073E]
        if anim:
            var[t] = anim
    return var

# ---------------------------------------------------------------- value noise
def make_noise(w, h, rnd, octaves=4, base_cell=16.0):
    grids = []
    for o in range(octaves):
        cell = max(2.0, base_cell / (2 ** o))
        gw, gh = int(w / cell) + 3, int(h / cell) + 3
        grids.append((cell, [[rnd.random() for _ in range(gw)] for _ in range(gh)]))
    def sample(x, y):
        v, amp, tot = 0.0, 1.0, 0.0
        for cell, g in grids:
            fx, fy = x / cell, y / cell
            ix, iy = int(fx), int(fy)
            tx, ty = fx - ix, fy - iy
            tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty)
            a = g[iy][ix] + (g[iy][ix+1] - g[iy][ix]) * tx
            b = g[iy+1][ix] + (g[iy+1][ix+1] - g[iy+1][ix]) * tx
            v += (a + (b - a) * ty) * amp
            tot += amp; amp *= 0.5
        return v / tot
    return sample

# ---------------------------------------------------------------- generate
rnd = random.Random(SEED)
raw = open(TEMPLATE, 'rb').read()
inner = bytearray(zlib.decompress(raw[5:]))

root, base = tbl(inner, 0x13)
kids, kb = tbl(inner, base + root[1])
coff = kb + sorted(kids.items(), key=lambda x: x[1])[0][1]
cf, cb = tbl(inner, coff + 4)
W, H = inner[cb + cf[3]], inner[cb + cf[4]]
lk, lkb = tbl(inner, cb + cf[1])
lf, lb = tbl(inner, lkb + sorted(lk.items())[0][1] + 4)
q, e = lb + 2, lb + lf[1]

variants = load_variants()
elev = make_noise(W, H, rnd, octaves=4, base_cell=18.0)
clim = make_noise(W, H, rnd, octaves=3, base_cell=22.0)
blight = make_noise(W, H, rnd, octaves=3, base_cell=10.0)

SEA = 0.42
def pick_terrain(x, y):
    ev, cv, bv = elev(x, y), clim(x, y), blight(x, y)
    if ev < SEA:
        return 0                                    # Water
    if bv > 0.78:
        return 9 if bv > 0.90 else 5                # Lava core inside Wasteland pockets
    if cv < 0.34:
        return 3                                    # Snow
    if cv < 0.46:
        return 4                                    # Steppe
    if cv > 0.70:
        return 2                                    # Desert
    return 1                                        # Grass

CHAR = {0: '~', 1: '.', 2: 'd', 3: '*', 4: ',', 5: 'w', 9: 'L', None: ' '}
grid = [[None] * W for _ in range(H)]
idx = 0
changed = 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    x, y = idx % W, idx // W
    # only rewrite hexes the template has painted (14-byte, non-border);
    # the terrain-15 "random land" border ring stays untouched
    if L == 14:
        cls = struct.unpack_from('<H', inner, q + 4 + 3)[0]
        if cls != 0x0557:                            # 0x0557 = border fill class word
            t = pick_terrain(x, y)
            ccls, uid = rnd.choice(variants[t])
            struct.pack_into('<H', inner, q + 4 + 3, (ccls & 0xFFFF) - 1)
            struct.pack_into('<I', inner, q + 4 + 10, uid)
            grid[y][x] = t
            changed += 1
    q += 4 + L
    idx += 1

out = b'CFS\x00\x02' + zlib.compress(bytes(inner), 9)
open(OUT, 'wb').write(out)
print('seed %d | %dx%d | %d hexes painted -> %s (%d KB)' % (SEED, W, H, changed, OUT, len(out) // 1024))
counts = {}
for row in grid:
    for t in row:
        if t is not None:
            counts[t] = counts.get(t, 0) + 1
NAMES = {0: 'Water', 1: 'Grass', 2: 'Desert', 3: 'Snow', 4: 'Steppe', 5: 'Wasteland', 9: 'Lava'}
print(' | '.join('%s %d' % (NAMES[t], n) for t, n in sorted(counts.items())))
print()
for row in grid:
    print(''.join(CHAR[t] for t in row))
