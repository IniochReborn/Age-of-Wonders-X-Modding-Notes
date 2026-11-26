# -*- coding: utf-8 -*-
"""Harvest EXTRA structure records missing from the AtF/Slugfest palette
-> obj_extra.pkl (merged into OBJ by generate_map_v4).

Wanted (user request 2026-08-03):
  Builder's Guild #2  STR_BLDM   guids 0x0441CED6 / 0x0DD559CF   -> building2+pad1
  Shipyard            PRO_SYRD   guids 0x3C / 0x6B               -> shipyard
  Blood Shrine        STR_BLDS   guids 0x0CDE791A / 0x0BCB5493   -> blds+pad1
  Arena (surface)     STR_AREN   guids 0x0604881B/0x288863/0x777B46F -> aren+pad1
  Reflecting Pool     STR_RF     guids 0x01808751 / 0x08A2A872   -> pad1+str_rf
(the last two already have harvested records; extra instances just widen the
terrain coverage — the real fix is adding the groups to the placement rotation)

Scans EVERY official .hsm on disk (generated x* maps excluded), level 0 only,
using the same record parser/patch builder as harvest_objects.py.
Usage: py "patch scripts/mapgen/harvest_extra.py"
"""
import struct, zlib, os, glob, pickle, collections, re

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
HERE = os.path.dirname(os.path.abspath(__file__))

WANT = {
    0x0441CED6: 'building2+pad1', 0x0DD559CF: 'building2+pad1',
    0x3C: 'shipyard', 0x6B: 'shipyard',
    0x0CDE791A: 'blds+pad1', 0x0BCB5493: 'blds+pad1',
    0x0604881B: 'aren+pad1', 0x00288863: 'aren+pad1', 0x0777B46F: 'aren+pad1',
    0x01808751: 'pad1+str_rf', 0x08A2A872: 'pad1+str_rf',
}

def make_tbl(dd):
    def tbl(p):
        b = dd[p]; p += 1; nd = 0
        if b & 0x80:
            nd = struct.unpack_from('<I', dd, p)[0]; p += 4
        nb = b & 0x7F; f = {}
        for _ in range(nb):
            f[dd[p]] = dd[p+1]; p += 2
        for _ in range(nd):
            t, o = struct.unpack_from('<II', dd, p); f[t] = o; p += 8
        return f, p
    return tbl

# registry (for KNOWN_STORED + terrain of hexagon variants)
d = open('Release/Release.hss', 'rb').read()
t = make_tbl(d)
root, base = t(0x37)
f5, b5 = t(base + root[5])
kids, kb = t(b5 + f5[1])
order = sorted(kids.items(), key=lambda kv: kv[1])
guid2cls, guid2terr = {}, {}
for i, (cid, off) in enumerate(order):
    cls = struct.unpack_from('<I', d, kb + off)[0]
    f, b1 = t(kb + off + 4)
    if 1 not in f: continue
    guid = struct.unpack_from('<I', d, b1 + f[1])[0]
    guid2cls[guid] = cls
    if 7 in f and struct.unpack_from('<I', d, b1 + f[7])[0] == 1:
        guid2terr[guid] = d[b1 + f[7] + 4]
KNOWN_STORED = {cls - 1 for cls in set(guid2cls.values())}
HEX_CLS = (0x20153, 0x2073E)
DECOR_CLS = (0x20167, 0x20169)
SKIP_CLS = {0x20393, 0x20395, 0x203A0, 0x20392, 0x20394, 0x2039F,
            # v4.23: hex-attached EVENTS (0x2056C, 0x2056E Message Event) — they
            # index the source map's root event/text data, which generated maps
            # don't carry -> editor "Oh dear, it's the end...." + EngineP AV
            0x2056C, 0x2056E}

def parse_record(rec):
    tt = make_tbl(rec)
    try:
        hdr, p = tt(0)
    except Exception:
        return None
    offs = sorted(o for t2, o in hdr.items() if t2 >= 0x32)
    allobs = sorted(hdr.values())
    if not offs or offs[0] != 0:
        return None
    bounds_all = [p + o for o in allobs] + [len(rec)]
    if any(b > len(rec) for b in bounds_all):
        return None
    out = []
    for i in range(len(offs)):
        cs = p + offs[i]
        ce = next(b for b in bounds_all + [len(rec)] if b > cs)
        if ce - cs < 5: return None
        stored = struct.unpack_from('<I', rec, cs)[0]
        if stored not in KNOWN_STORED: return None
        try:
            f, b1 = tt(cs + 4)
        except Exception:
            return None
        fitems = sorted(f.items(), key=lambda kv: kv[1])
        sizes = {}
        for j, (tag, o) in enumerate(fitems):
            sizes[tag] = (fitems[j+1][1] - o) if j+1 < len(fitems) else (ce - (b1 + o))
        out.append(dict(cls=stored + 1, f=f, base=b1, sizes=sizes,
                        guid=(struct.unpack_from('<I', rec, b1 + f[1])[0]
                              if 1 in f and sizes.get(1, 0) >= 4 else None)))
    return out

def walk_level0(path):
    raw = open(path, 'rb').read()
    if raw[:3] != b'CFS':
        return
    inner = zlib.decompress(raw[5:])
    tm = make_tbl(inner)
    root_m, base_m = tm(0x13)
    kids_m, kb_m = tm(base_m + root_m[1])
    csort = sorted(kids_m.items(), key=lambda x: x[1])
    cf, cb = tm(kb_m + csort[0][1] + 4)
    W, H = inner[cb + cf[3]], inner[cb + cf[4]]
    lf_all, lkb = tm(cb + cf[1])
    lf, lb = tm(lkb + lf_all[0] + 4)
    s, e = lb + lf[6], lb + lf[1]
    q, idx = s, 0
    while q < e and idx < W * H:
        L = struct.unpack_from('<I', inner, q)[0]
        yield idx % W, idx // W, bytes(inner[q+4:q+4+L])
        q += 4 + L; idx += 1

files = []
for pat in ('Scenario/**/*.hsm', 'Scenario/**/*.HSM',
            'pre-claude rollback/**/*.hsm', 'TCMaps/**/*.hsm', 'User/**/*.hsm'):
    files += glob.glob(pat, recursive=True)
files = sorted(set(os.path.normpath(f) for f in files))
files = [f for f in files if not any(k in os.path.basename(f).lower()
         for k in ('xgen5', 'ximg5', 'xdiag', 'xtemplate', 'xgenerated', 'ximagemap'))]
print('%d candidate maps' % len(files))

harvest = collections.defaultdict(list)
seen_hash = set()
for path in files:
    try:
        it = walk_level0(path)
    except Exception:
        continue
    for x, y, rec in it:
        try:
            if len(rec) <= 33:
                continue
            ch = parse_record(rec)
            if ch is None:
                continue
            obj = [c for c in ch if c['cls'] not in HEX_CLS + DECOR_CLS]
            grp = next((WANT[c['guid']] for c in obj if c['guid'] in WANT), None)
            if grp is None:
                continue
            if any(c['cls'] in SKIP_CLS for c in ch):
                continue
            if ch[0]['cls'] not in HEX_CLS or 1 not in ch[0]['f']:
                continue
            if any(c['cls'] == 0x20109 for c in obj):   # city combos: skip
                continue
            if any(c['cls'] == 0x20218 for c in ch):    # garrison stacks: skip
                continue
            h = hash(rec)
            if h in seen_hash:
                continue
            seen_hash.add(h)
            patch = dict(hexvar=ch[0]['base'] + ch[0]['f'][1],
                         coords=[], ids=[], name=None)
            ok = True
            for c in ch:
                f, b1, sz = c['f'], c['base'], c['sizes']
                if 3 in f and 4 in f and sz.get(3) == 1 and sz.get(4) == 1:
                    patch['coords'].append((b1 + f[3], b1 + f[4]))
                if 98 in f:
                    if sz.get(98, 0) < 4: ok = False
                    else: patch['ids'].append(b1 + f[98])
            if not ok:
                continue
            harvest[grp].append(dict(
                rec=rec.hex(), terr=guid2terr.get(ch[0]['guid']),
                src=os.path.basename(path), at=(x, y), patch=patch, race=None,
                children=[(c['cls'], c['guid']) for c in ch]))
        except Exception:
            continue

for g, lst in sorted(harvest.items()):
    terrs = collections.Counter(e['terr'] for e in lst)
    print('  %-16s x%-3d terrains=%s from %s' %
          (g, len(lst), dict(terrs),
           sorted({e['src'] for e in lst})[:5]))
out = os.path.join(HERE, 'obj_extra.pkl')
pickle.dump(dict(harvest), open(out, 'wb'))
print('wrote', out)
