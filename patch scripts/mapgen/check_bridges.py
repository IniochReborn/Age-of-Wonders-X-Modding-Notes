# -*- coding: utf-8 -*-
"""Check every bridge in generated maps against the engine's DirectionValid rule:
at least one opposite-neighbor axis where BOTH hexes are land terrain
(surface: not water/lava; UG: cave floor). Direction -1 = editor/game crash in
THexagonBridge.Show (ImageLib.Get(-1) -> garbage vtable)."""
import struct, zlib, os, re, collections, sys

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

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

d = open('Release/Release.hss', 'rb').read()
t = make_tbl(d)
root, base = t(0x37)
f5, b5 = t(base + root[5])
kids, kb = t(b5 + f5[1])
order = sorted(kids.items(), key=lambda kv: kv[1])
guid2terr, guid2cls = {}, {}
for i, (cid, off) in enumerate(order):
    cls = struct.unpack_from('<I', d, kb + off)[0]
    f, b1 = t(kb + off + 4)
    if 1 not in f: continue
    guid = struct.unpack_from('<I', d, b1 + f[1])[0]
    guid2cls[guid] = cls
    if 7 in f and struct.unpack_from('<I', d, b1 + f[7])[0] == 1:
        guid2terr[guid] = d[b1 + f[7] + 4]
KNOWN_STORED = {c - 1 for c in set(guid2cls.values())}

def parse_children(rec):
    tt = make_tbl(rec)
    try:
        hdr, p = tt(0)
    except Exception:
        return None
    offs = sorted(o for t2, o in hdr.items() if t2 >= 0x32)
    allobs = sorted(hdr.values())
    if not offs or offs[0] != 0: return None
    bounds_all = [p + o for o in allobs] + [len(rec)]
    if any(b > len(rec) for b in bounds_all): return None
    out = []
    for i in range(len(offs)):
        cs = p + offs[i]
        stored = struct.unpack_from('<I', rec, cs)[0]
        if stored not in KNOWN_STORED: return None
        try:
            f, b1 = tt(cs + 4)
        except Exception:
            return None
        out.append(dict(cls=stored + 1, f=f, base=b1,
                        guid=(struct.unpack_from('<I', rec, b1 + f[1])[0] if 1 in f else None)))
    return out

def walk_level(path, want_lid):
    inner = zlib.decompress(open(path, 'rb').read()[5:])
    tm = make_tbl(inner)
    root_m, base_m = tm(0x13)
    kids_m, kb_m = tm(base_m + root_m[1])
    csort = sorted(kids_m.items(), key=lambda x: x[1])
    cf, cb = tm(kb_m + csort[0][1] + 4)
    W, H = inner[cb + cf[3]], inner[cb + cf[4]]
    lf_all, lkb = tm(cb + cf[1])
    if want_lid not in lf_all: return None
    lf, lb = tm(lkb + lf_all[want_lid] + 4)
    s, e = lb + lf[6], lb + lf[1]
    recs = []
    q, idx = s, 0
    while q < e and idx < W * H:
        L = struct.unpack_from('<I', inner, q)[0]
        recs.append(bytes(inner[q+4:q+4+L]))
        q += 4 + L; idx += 1
    return W, H, recs

def nbr_dirs(x, y):
    if x % 2 == 0:
        return [(x, y-1), (x+1, y-1), (x+1, y), (x, y+1), (x-1, y), (x-1, y-1)]
    return [(x, y-1), (x+1, y), (x+1, y+1), (x, y+1), (x-1, y+1), (x-1, y)]

LAND_SURF = {1, 2, 3, 4, 5, 12}     # not water(0)/lava(9); solid-rock/void excluded
LAND_UG = {1, 2, 3, 4, 5, 12}

for path in sys.argv[1:]:
    print('==', os.path.basename(path))
    for lid in (0, 1, 2):
        r = walk_level(path, lid)
        if r is None: continue
        W, H, recs = r
        terr = {}
        bridges = []
        for idx, rec in enumerate(recs):
            x, y = idx % W, idx // W
            if len(rec) <= 5: continue
            ch = parse_children(rec) if len(rec) > 14 else None
            if len(rec) == 14:
                # plain hex: 01 32 00 [cls-1 u32][01 01 00][guid u32]
                g = struct.unpack_from('<I', rec, 10)[0]
                terr[(x, y)] = guid2terr.get(g)
                continue
            if not ch: continue
            ht = next((guid2terr.get(c['guid']) for c in ch
                       if c['cls'] in (0x20153, 0x2073E)), None)
            terr[(x, y)] = ht
            if any(c['cls'] == 0x2087B for c in ch):
                bridges.append((x, y))
        landset = LAND_SURF if lid == 0 else LAND_UG
        bad = []
        for (x, y) in bridges:
            nb = nbr_dirs(x, y)
            ok = False
            for dd_ in range(3):
                a, b = nb[dd_], nb[dd_ + 3]
                if terr.get(a) in landset and terr.get(b) in landset:
                    ok = True; break
            if not ok:
                bad.append((x, y, [terr.get(q) for q in nb]))
        print('  L%d: %d bridges, %d INVALID (direction=-1 -> crash)' %
              (lid, len(bridges), len(bad)))
        for b in bad[:12]:
            print('     at (%d,%d) neighbor terrains %s' % (b[0], b[1], b[2]))
