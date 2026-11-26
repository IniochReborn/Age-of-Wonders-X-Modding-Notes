# -*- coding: utf-8 -*-
"""
AoWx random map generator — v3: coherent biomes + clustered vegetation.

v2 crashed then looked salt-and-peppery (lone snow hexes in grass, each correctly
vegetated -> "random snow trees"). v3 generates the whole terrain grid first, runs
majority-smoothing passes so biomes form contiguous regions, then scatters vegetation
in clusters that sit on interior biome hexes only. Terrain + decor encodings are the
verified ones from v2 (child classid = resource_class-1; decor = real 17-byte 0x20166
children harvested per terrain, emitted verbatim).

Usage: py "patch scripts/mapgen/generate_map_v3.py" [seed]
"""
import struct, zlib, random, sys, os, pickle

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(1 << 30)
# size: S/M/L/XL (48/64/96/127) — arg2, default S. Each needs an empty-grass template painted
# in the editor (the game bakes size-dependent minimap/camera/AI data we shouldn't fake).
SIZE = (sys.argv[2].upper() if len(sys.argv) > 2 else 'S')
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = {
    'S':  os.path.join(HERE,'xTemplate Small.hsm'),    # 48x48
    'M':  os.path.join(HERE,'xTemplate Medium.hsm'),   # 64x64
    'L':  os.path.join(HERE,'xTemplate Large.hsm'),    # 96x96
    'XL': os.path.join(HERE,'xTemplate XLarge.hsm'),   # 127x127
}
TEMPLATE = TEMPLATES.get(SIZE, TEMPLATES['S'])
if not os.path.exists(TEMPLATE):
    raise SystemExit('Missing template for size %s: %s\n'
                     '  -> in AoWDevX make a new empty map of that size, flood-fill it all grass,\n'
                     '     save it under exactly that name, then re-run.' % (SIZE, TEMPLATE))
OUT = 'Scenario/Custom/xGenerated %s.hsm' % SIZE
# full 33-byte hex records (hexagon + decor together) harvested verbatim per terrain —
# the editor's own curated pairings, so a decorated hex looks exactly like a real one.
VEGREC = {t: [bytes.fromhex(h) for h in v]
          for t, v in pickle.load(open(os.path.join(HERE, 'veg_records.pkl'), 'rb')).items()}
# mountain hexes (0x20168 decor) — per-hex; engine auto-links adjacent mountain hexes into ranges.
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
        if 1 not in f or 7 not in f: continue
        if struct.unpack_from('<I', d, b1 + f[7])[0] != 1: continue
        var.setdefault(d[b1 + f[7] + 4], []).append((cls, struct.unpack_from('<I', d, b1 + f[1])[0]))
    for t in (0, 6):
        anim = [v for v in var.get(t, []) if v[0] == 0x2073E]
        if anim: var[t] = anim
    return var

def make_noise(w, h, rnd, octaves, base_cell):
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

rnd = random.Random(SEED)
terr_var = load_variants()

raw = open(TEMPLATE, 'rb').read()
inner = bytearray(zlib.decompress(raw[5:]))
root, base = tbl(inner, 0x13)
kids, kb = tbl(inner, base + root[1])
csort = sorted(kids.items(), key=lambda x: x[1])
coff = kb + csort[0][1]
cf, cb = tbl(inner, coff + 4)
W, H = inner[cb + cf[3]], inner[cb + cf[4]]
lvls = sorted(tbl(inner, cb + cf[1])[0].items())
lk, lkb = tbl(inner, cb + cf[1])
loff = lkb + dict(lvls)[0]
lf, lb = tbl(inner, loff + 4)
s, e = lb + 2, lb + lf[1]

# ---- 1. base terrain grid (None = border/unpainted, keep template) ----
SCALE = W / 48.0                               # scale noise features so biomes stay proportional on bigger maps
elev = make_noise(W, H, rnd, 4, 20.0 * SCALE)
clim = make_noise(W, H, rnd, 2, 30.0 * SCALE)  # fewer octaves + big cells = smooth climate bands
blight = make_noise(W, H, rnd, 2, 16.0 * SCALE)
SEA = 0.42
def base_terrain(x, y):
    ev = elev(x, y)
    if ev < SEA: return 0
    bv = blight(x, y)
    if bv > 0.80: return 9 if bv > 0.93 else 5
    cv = clim(x, y)
    if cv < 0.33: return 3
    if cv < 0.44: return 4
    if cv > 0.72: return 2
    return 1

# which hexes are ours to paint (interior, non-border-fill 14B records)
paint = [[False] * W for _ in range(H)]
q, idx = s, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    if L == 14 and struct.unpack_from('<H', inner, q + 4 + 3)[0] != 0x0557:
        paint[idx // W][idx % W] = True
    q += 4 + L; idx += 1

grid = [[(base_terrain(x, y) if paint[y][x] else None) for x in range(W)] for y in range(H)]

# ---- 2. majority-smooth so biomes are contiguous (kills lone hexes) ----
def smooth(g):
    ng = [row[:] for row in g]
    for y in range(H):
        for x in range(W):
            t = g[y][x]
            if t is None: continue
            cnt = {}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and g[ny][nx] is not None:
                        cnt[g[ny][nx]] = cnt.get(g[ny][nx], 0) + (2 if dx == 0 and dy == 0 else 1)
            ng[y][x] = max(cnt, key=cnt.get)
    return ng
for _ in range(2):
    grid = smooth(grid)

# ---- 3. vegetation: per-terrain density (matched to hand-made maps e.g. "After the Fall"),
#         clustered via forest-noise percentile thresholding, thinned only at biome edges ----
forest = make_noise(W, H, rnd, 3, 8.0 * SCALE)
DENSITY = {1: 0.70, 3: 0.66, 4: 0.62, 2: 0.36, 5: 0.78, 12: 0.62}
def edge_hex(x, y, t):                        # touches a different biome
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dx or dy): continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] is not None and grid[ny][nx] != t:
                return True
    return False

# collect forest values per terrain, then take the top DENSITY fraction (highest = clustered cores)
buckets = {}
for y in range(H):
    for x in range(W):
        t = grid[y][x]
        if t is None or not VEGREC.get(t) or t in (0, 9): continue
        buckets.setdefault(t, []).append((forest(x, y), x, y))
veg = [[False] * W for _ in range(H)]
for t, cells in buckets.items():
    cells.sort(reverse=True)                  # highest forest value first
    take = int(len(cells) * DENSITY.get(t, 0.5))
    for i, (fv, x, y) in enumerate(cells):
        if i < take and not (edge_hex(x, y, t) and rnd.random() < 0.3):  # thin (not kill) edges
            veg[y][x] = True

# ---- 3b. mountains: high-elevation ridges, take priority over vegetation on those hexes ----
ridge = make_noise(W, H, rnd, 3, 11.0 * SCALE)        # separate field -> ranges run independently of forests
MTN_FRAC = 0.14                               # ~14% of land becomes mountains (peaks + ridge noise)
mtn = [[False] * W for _ in range(H)]
mcells = []
for y in range(H):
    for x in range(W):
        t = grid[y][x]
        if t is None or not MTNREC.get(t) or t in (0, 9): continue
        mcells.append((elev(x, y) * 0.6 + ridge(x, y) * 0.4, x, y, t))   # peaks + ridge lines
mcells.sort(reverse=True)
for score, x, y, t in mcells[:int(len(mcells) * MTN_FRAC)]:
    mtn[y][x] = True
    veg[y][x] = False                         # a hex is mountain OR forest, not both

# ---- 4. write field stream ----
def child(res_cls, uid):
    return struct.pack('<I', res_cls - 1) + b'\x01\x01\x00' + struct.pack('<I', uid)

def place_record(payload, x, y):
    """Stamp a harvested 33-byte record onto hex (x,y): the decor child's field3/field4 are
    the hex's map coordinates (f3=x, f4=y). Multi-hex decor (mountains) anchors off these, so
    they MUST match the destination hex or the sprite draws at the source location / overlaps."""
    rec = bytearray(payload)
    dc = 16                                   # decor child classid offset in a 33B record
    ct, cbb = tbl(rec, dc + 4)                # decor child's property table
    if 3 in ct: rec[cbb + ct[3]] = x & 0xFF
    if 4 in ct: rec[cbb + ct[4]] = y & 0xFF
    return bytes(rec)

new_stream = bytearray()
q, idx, nveg, nmtn, nter = s, 0, 0, 0, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    rec = bytes(inner[q + 4:q + 4 + L])
    x, y = idx % W, idx // W
    if paint[y][x]:
        t = grid[y][x]
        if mtn[y][x]:
            new_stream += struct.pack('<I', 33) + place_record(rnd.choice(MTNREC[t]), x, y)
            nmtn += 1
        elif veg[y][x]:
            new_stream += struct.pack('<I', 33) + place_record(rnd.choice(VEGREC[t]), x, y)
            nveg += 1
        else:
            hcls, huid = rnd.choice(terr_var[t])
            new_stream += struct.pack('<I', 14) + b'\x01\x32\x00' + child(hcls, huid)
        nter += 1
    else:
        new_stream += struct.pack('<I', L) + rec
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

blob = b'CFS\x00\x02' + zlib.compress(bytes(out), 9)
open(OUT, 'wb').write(blob)
CH = {0: '~', 1: '.', 2: 'd', 3: '*', 4: ',', 5: 'w', 9: 'L', None: ' '}
counts = {}
for row in grid:
    for t in row:
        if t is not None: counts[t] = counts.get(t, 0) + 1
NM = {0: 'Water', 1: 'Grass', 2: 'Desert', 3: 'Snow', 4: 'Steppe', 5: 'Wasteland', 9: 'Lava'}
print('seed %d | %dx%d | %d terrain, %d veg, %d mtn | %+d bytes -> %s (%d KB)'
      % (SEED, W, H, nter, nveg, nmtn, delta, OUT, len(blob) // 1024))
print(' | '.join('%s %d' % (NM[t], n) for t, n in sorted(counts.items())))
print()
for y in range(H):
    print(''.join(('^' if mtn[y][x] else 'T' if veg[y][x] else CH[grid[y][x]]) for x in range(W)))
