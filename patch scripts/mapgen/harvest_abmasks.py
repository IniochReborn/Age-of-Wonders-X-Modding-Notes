# -*- coding: utf-8 -*-
"""Harvest per-TYPE ability masks for fresh units -> ab_masks.pkl.

Scans all official .hsm maps for 0x20214 unit records. KEY = f10 (u16 unit type =
TUnitResourceList index — the field the engine actually resolves the type from;
'unit resource missing (N)' exception if invalid). f2 = ability BIT COUNT and
f3 = ability bitmask of ceil(f2/8) bytes (AoWE.TCustomAbilityList.ReadWrite) —
per-instance CURRENT abilities. Records carrying an enchant list (f49) are
skipped so enchant-granted ability bits don't pollute the fresh-unit masks;
among the rest the SMALLEST mask (fewest bits) per type wins.

Usage: py harvest_abmasks.py
"""
import struct, zlib, os, glob, pickle, collections

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

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

def parse_fields(dd, tbl_pos, end):
    f, fb = tbl(dd, tbl_pos)
    fo = sorted(f.items(), key=lambda kv: kv[1])
    return [(t, bytes(dd[fb+o: fb+fo[j+1][1] if j+1 < len(fo) else end]))
            for j, (t, o) in enumerate(fo)]

def bits(b):
    return [i for i in range(len(b) * 8) if b[i // 8] >> (i % 8) & 1]

files = []
for pat in ('Scenario/**/*.hsm', 'Scenario/**/*.HSM',
            'pre-claude rollback/**/*.hsm', 'TCMaps/**/*.hsm', 'User/**/*.hsm'):
    files += glob.glob(pat, recursive=True)
files = sorted(set(os.path.normpath(f) for f in files))
files = [f for f in files if not any(k in os.path.basename(f).lower()
         for k in ('xgen5', 'ximg5', 'xdiag', 'xtemplate', 'xgenerated', 'ximagemap'))]
print('%d candidate maps' % len(files))

masks = {}          # ty -> (nbits, sorted bit list)
n_rec = n_ench = 0
pat214 = struct.pack('<I', 0x20214 - 1)

for path in files:
    try:
        raw = open(path, 'rb').read()
        if raw[:3] != b'CFS':
            continue
        inner = zlib.decompress(raw[5:])
    except Exception:
        continue
    i = -1
    while True:
        i = inner.find(pat214, i + 1)
        if i < 0:
            break
        try:
            fl = dict(parse_fields(inner, i + 4, i + 4 + 400))
            if 2 not in fl or 3 not in fl or 10 not in fl:
                continue
            cnt = struct.unpack('<I', fl[2][:4])[0]
            if not 1 <= cnt <= 400:
                continue
            need = (cnt + 7) // 8
            if len(fl[3]) < need:          # false positive / truncated parse
                continue
            ty = struct.unpack('<H', fl[10][:2])[0]
            if ty > 400:
                continue
            n_rec += 1
            if 49 in fl:
                n_ench += 1
                continue
            bl = bits(fl[3][:need])
            if not bl or bl[0] != 0:       # every genuine unit has ability 0
                continue
            if ty not in masks or len(bl) < len(masks[ty][1]):
                masks[ty] = (cnt, bl)
        except Exception:
            continue

print('records seen %d (%d enchanted, skipped) -> %d types with masks'
      % (n_rec, n_ench, len(masks)))
RACE_BASE = {0: 0, 1: 18, 3: 36, 2: 54, 4: 72, 5: 90, 6: 108, 7: 126,
             8: 144, 9: 162, 10: 180, 11: 198}
need = sorted(b + s for b in RACE_BASE.values() for s in (0, 1, 2, 3))
have = [t for t in need if t in masks]
print('party-slot coverage: %d/%d  missing: %s'
      % (len(have), len(need), [t for t in need if t not in masks]))
for ty in need:
    if ty in masks:
        print('   ty %3d cnt %3d bits %s' % (ty, masks[ty][0], masks[ty][1]))

out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'ab_masks.pkl'))
pickle.dump({t: v[1] for t, v in masks.items()}, open(out, 'wb'))
print('wrote', out)
