# -*- coding: utf-8 -*-
"""
AoWx random map generator — PROTOTYPE v2: terrain + vegetation scatter.

v1 rewrote 14-byte hex records in place. v2 also APPENDS decor entries (forests, cactus,
shrubs, stones...) which grows records 14 -> 25 bytes, so the level's field stream is
rebuilt and the tail offsets are fixed:
  - the level record's property-table entry for field 1 (points past the stream) += delta
  - container children-table offsets of any LEVELS AFTER the grown one += delta
  (nothing above the container stores absolute offsets into the tail — verified)

Record shapes (see memory hsm-map-format.md):
  bare hex   : [len=14][01][32 00][11B hexagon child]
  hex + decor: [len=25][02][32 00][33 0B][11B hexagon child][11B decor child]
  child (11B): [classid:u32][ctrl 01][pair 01 00][resourceUID:u32]

Usage: py "patch scripts/mapgen/generate_map_v2.py" [seed]
"""
import struct, zlib, random, sys, os, pickle

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(1 << 30)
HERE = os.path.dirname(os.path.abspath(__file__))
# real decor children (class 0x20166, 17 bytes) harvested per terrain from shipped maps —
# emitted verbatim so field3/field5 (rotation/variant) are always engine-valid.
DECOR = {t: [bytes.fromhex(h) for h in v]
         for t, v in pickle.load(open(os.path.join(HERE, 'decor_palette.pkl'), 'rb')).items()}
TEMPLATE = 'Scenario/Custom/xTest Grass.hsm'
OUT = 'Scenario/Custom/xGenerated2.hsm'

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

def tbl_entry_pos(dd, p, want_tag):
    """File position of the OFFSET value for a tag inside a property table (for patching)."""
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F
    for _ in range(nb):
        if dd[p] == want_tag:
            return ('u8', p + 1)
        p += 2
    for _ in range(nd):
        t = struct.unpack_from('<I', dd, p)[0]
        if t == want_tag:
            return ('u32', p + 4)
        p += 8
    return None

# ---------------------------------------------------------------- resources
def load_resources():
    d = open('Release/Release.hss', 'rb').read()
    root, base = tbl(d, 0x37)
    f5, b5 = tbl(d, base + root[5])
    kids, kb = tbl(d, b5 + f5[1])
    terr_var = {}          # terrain -> [(cls, uid)] hexagon variants
    decor = {}             # name -> {terrain: [uid, ...]}  (single-hex decors only)
    for cid, off in sorted(kids.items()):
        cls = struct.unpack_from('<I', d, kb + off)[0]
        if cls not in (0x20153, 0x2073E, 0x20167):
            continue
        f, b1 = tbl(d, kb + off + 4)
        if 1 not in f or 7 not in f:
            continue
        uid = struct.unpack_from('<I', d, b1 + f[1])[0]
        cnt = struct.unpack_from('<I', d, b1 + f[7])[0]
        if cls in (0x20153, 0x2073E):
            if cnt == 1:
                terr_var.setdefault(d[b1 + f[7] + 4], []).append((cls, uid))
        else:                                             # decor resource
            if cnt != 1:                                  # skip multi-hex decors (hills chains etc.)
                continue
            terr = d[b1 + f[7] + 4]
            nm = ''
            if 6 in f:
                ln = d[b1 + f[6]]
                s = d[b1 + f[6] + 1:b1 + f[6] + 1 + ln]
                if 2 < ln < 30 and all(0x20 <= c < 0x7f for c in s):
                    nm = s.decode()
            if nm:
                decor.setdefault(nm, {}).setdefault(terr, []).append(uid)
    for t in (0, 6):                                      # water/ice -> animated class
        anim = [v for v in terr_var.get(t, []) if v[0] == 0x2073E]
        if anim:
            terr_var[t] = anim
    return terr_var, decor

# ---------------------------------------------------------------- noise
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
terr_var, decor = load_resources()

def veg_child(terr, forest_v):
    """Return a real decor-child byte string for this hex, or None."""
    pool = DECOR.get(terr)
    if not pool:
        return None
    if forest_v > 0.62:                                    # forest belt (dense)
        return rnd.choice(pool)
    if forest_v > 0.55 and rnd.random() < 0.35:            # forest fringe (thinner)
        return rnd.choice(pool)
    if rnd.random() < 0.02:                                # sparse clutter on open land
        return rnd.choice(pool)
    return None

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
GROW_LEVEL = 0
loff = lkb + dict(lvls)[GROW_LEVEL]
lf, lb = tbl(inner, loff + 4)
s, e = lb + 2, lb + lf[1]

elev = make_noise(W, H, rnd, 4, 18.0)
clim = make_noise(W, H, rnd, 3, 22.0)
blight = make_noise(W, H, rnd, 3, 10.0)
forest = make_noise(W, H, rnd, 4, 12.0)

SEA = 0.42
def pick_terrain(x, y):
    ev, cv, bv = elev(x, y), clim(x, y), blight(x, y)
    if ev < SEA: return 0
    if bv > 0.78: return 9 if bv > 0.90 else 5
    if cv < 0.34: return 3
    if cv < 0.46: return 4
    if cv > 0.70: return 2
    return 1

def child(res_cls, uid):
    # record stores the MO userclass = resource class - 1 (e.g. hexagon res 0x20153 -> 0x20152,
    # decor res 0x20167 -> 0x20166). Getting this wrong = access violation on load.
    return struct.pack('<I', res_cls - 1) + b'\x01\x01\x00' + struct.pack('<I', uid)

new_stream = bytearray()
grid = [[None] * W for _ in range(H)]
q, idx, nveg = s, 0, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    rec = bytes(inner[q + 4:q + 4 + L])
    x, y = idx % W, idx // W
    clsw = struct.unpack_from('<H', rec, 3)[0] if L >= 5 else 0
    if L == 14 and clsw != 0x0557:                 # painted interior hex -> regenerate
        t = pick_terrain(x, y)
        hcls, huid = rnd.choice(terr_var[t])
        hex_child = child(hcls, huid)
        vc = veg_child(t, forest(x, y)) if t not in (0, 9) else None
        if vc is not None:
            # decor child sits at offset 0x0b (11) = right after the hexagon child
            payload = b'\x02\x32\x00\x33\x0b' + hex_child + vc
            nveg += 1
            grid[y][x] = 'F'
        else:
            payload = b'\x01\x32\x00' + hex_child
            grid[y][x] = t
        new_stream += struct.pack('<I', len(payload)) + payload
    else:                                          # border / anything else: keep verbatim
        new_stream += struct.pack('<I', L) + rec
    q += 4 + L
    idx += 1

delta = len(new_stream) - (e - s)
out = bytearray()
out += inner[:s]
out += new_stream
out += inner[e:]

# fixup 1: level table field-1 offset (+delta)
kind, pos = tbl_entry_pos(out, loff + 4, 1)
assert kind == 'u32', 'level field1 expected dword entry'
struct.pack_into('<I', out, pos, struct.unpack_from('<I', out, pos)[0] + delta)
# fixup 2: container children offsets for levels stored after the grown one
for lid, lo in lvls:
    if lkb + lo > loff:
        kind2, pos2 = tbl_entry_pos(out, cb + cf[1], lid)
        v = struct.unpack_from('<I', out, pos2)[0] if kind2 == 'u32' else out[pos2]
        if kind2 == 'u32':
            struct.pack_into('<I', out, pos2, v + delta)
        else:
            out[pos2] = v + delta

blob = b'CFS\x00\x02' + zlib.compress(bytes(out), 9)
open(OUT, 'wb').write(blob)
NAMES = {0: '~', 1: '.', 2: 'd', 3: '*', 4: ',', 5: 'w', 9: 'L', 'F': 'T', None: ' '}
print('seed %d | %dx%d | veg on %d hexes | stream %+d bytes -> %s (%d KB)'
      % (SEED, W, H, nveg, delta, OUT, len(blob) // 1024))
for row in grid:
    print(''.join(NAMES[t] for t in row))
