# -*- coding: utf-8 -*-
"""
build_palettes.py — (re)generate the decor palettes the map generators use, by harvesting real
decorated hexes out of your own maps. Run this ONCE if your mod's Release.hss differs from the
one these palettes were built against (different resource UIDs), or to widen variety.

Run from your GAME ROOT (next to AoW.exe), with this whole folder placed anywhere:
    py "AoW Map Generator/build_palettes.py"

Reads : Release/Release.hss   (terrain + decor resource table)
        Scenario/**/*.hsm      (your maps, as sample material)
Writes: veg_records.pkl, mtn_records.pkl, decor_palette.pkl  (beside this script)

The palettes are just real hex records grouped by terrain, so the generators emit the game's own
curated terrain+decor pairings verbatim (see AOW-MAP-GENERATOR.md for the format).
"""
import struct, zlib, glob, os, pickle, collections

HERE = os.path.dirname(os.path.abspath(__file__))

def tbl(d, p):
    b = d[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', d, p)[0]; p += 4
    nb = b & 0x7F; f = {}
    for _ in range(nb):
        f[d[p]] = d[p+1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from('<II', d, p); f[t] = o; p += 8
    return f, p

# ---- terrain of each hexagon-variant resource UID (Release.hss MOR) ----
d = open('Release/Release.hss', 'rb').read()
root, base = tbl(d, 0x37); f5, b5 = tbl(d, base + root[5]); kids, kb = tbl(d, b5 + f5[1])
hexterr = {}
for cid, off in sorted(kids.items()):
    cls = struct.unpack_from('<I', d, kb + off)[0]
    try: f, b1 = tbl(d, kb + off + 4)
    except Exception: continue
    if cls in (0x20153, 0x2073E) and 1 in f and 7 in f and struct.unpack_from('<I', d, b1 + f[7])[0] == 1:
        hexterr[struct.unpack_from('<I', d, b1 + f[1])[0]] = d[b1 + f[7] + 4]
print('hexagon terrain variants:', len(hexterr))

# ---- harvest full 33-byte records (hexagon 0x20152 + one decor child), bucket by terrain + decor class ----
veg = collections.defaultdict(collections.Counter)     # decor class 0x20166 (vegetation)
mtn = collections.defaultdict(collections.Counter)     # decor class 0x20168 (mountains)
decor17 = collections.defaultdict(collections.Counter) # the raw 17-byte decor children (0x20166)
nmaps = 0
for fn in glob.glob('Scenario/**/*.hsm', recursive=True):
    try:
        dd = zlib.decompress(open(fn, 'rb').read()[5:])
        r2, b2 = tbl(dd, 0x13); kk, kkb = tbl(dd, b2 + r2[1])
        coff = kkb + sorted(kk.items(), key=lambda x: x[1])[0][1]
        cf, cb = tbl(dd, coff + 4); lk, lkb = tbl(dd, cb + cf[1])
    except Exception:
        continue
    nmaps += 1
    for lid, lo in sorted(lk.items()):
        try: lf, lb = tbl(dd, lkb + lo + 4)
        except Exception: continue
        q = lb + 2; e = lb + lf[1]
        while q < e:
            L = struct.unpack_from('<I', dd, q)[0]; p = dd[q+4:q+4+L]; q += 4 + L
            if L != 33 or p[:5] != b'\x02\x32\x00\x33\x0b': continue
            if struct.unpack_from('<I', p, 5)[0] != 0x20152: continue
            dcls = struct.unpack_from('<I', p, 16)[0]
            t = hexterr.get(struct.unpack_from('<I', p, 5 + 7)[0])
            if t is None: continue
            if dcls == 0x20166:
                veg[t][p.hex()] += 1; decor17[t][p[16:].hex()] += 1
            elif dcls == 0x20168:
                mtn[t][p.hex()] += 1

def top(counter, n):
    return {t: [h for h, _ in c.most_common(n)] for t, c in counter.items()}

pickle.dump(top(veg, 400),     open(os.path.join(HERE, 'veg_records.pkl'), 'wb'))
pickle.dump(top(mtn, 300),     open(os.path.join(HERE, 'mtn_records.pkl'), 'wb'))
pickle.dump(top(decor17, 80),  open(os.path.join(HERE, 'decor_palette.pkl'), 'wb'))
print('scanned %d maps' % nmaps)
print('veg records / terrain:', {t: len(v) for t, v in sorted(top(veg, 400).items())})
print('mtn records / terrain:', {t: len(v) for t, v in sorted(top(mtn, 300).items())})
print('wrote veg_records.pkl, mtn_records.pkl, decor_palette.pkl')
