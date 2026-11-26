#!/usr/bin/env python3
r"""
Minimal .hsm (CFS) hex-grid reader/writer (2026-10-31) - the level-0 field stream as mapgen/generate_map_v4 walks it.

Layout (from mapgen): root field table at 0x13; root[1] -> kids table; first kid = the map: fields 3/4 = W/H,
field 1 = levels table; level 0 record: field table at loff+4, its hex stream = [lb+2, lb+lf[1]) =
W*H x ([u32 len][hex record]).  Hex record = field table (child tags 0x32.. at offsets) + children; child =
<u32 resource-class - 1><field table><data>.  After resizing the stream, the level's field 1 offset and every
later level offset grow by the delta (exactly mapgen's fix-up).
  load(path) / loads(cfs_bytes) -> Grid (W, H, recs: list of bytes per hex, x = i % W, y = i // W)
  dumps(grid) -> cfs bytes
  children(rec) -> [(tag, bytes)];  build(children) -> rec
"""
import struct, zlib


def tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from("<I", dd, p)[0]; p += 4
    f = {}
    for _ in range(b & 0x7F):
        f[dd[p]] = dd[p + 1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from("<II", dd, p); f[t] = o; p += 8
    return f, p


def tbl_entry_pos(dd, p, want):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from("<I", dd, p)[0]; p += 4
    for _ in range(b & 0x7F):
        if dd[p] == want:
            return "u8", p + 1
        p += 2
    for _ in range(nd):
        if struct.unpack_from("<I", dd, p)[0] == want:
            return "u32", p + 4
        p += 8
    return None


def enc_tblhdr(pairs):
    bp = [(t, o) for t, o in pairs if t <= 255 and o <= 255]
    dp = [(t, o) for t, o in pairs if not (t <= 255 and o <= 255)]
    out = bytearray([len(bp) | (0x80 if dp else 0)])
    if dp:
        out += struct.pack("<I", len(dp))
    for t, o in bp:
        out += bytes([t, o])
    for t, o in dp:
        out += struct.pack("<II", t, o)
    return bytes(out)


def children(rec):
    hdr, p0 = tbl(rec, 0)
    items = sorted(hdr.items(), key=lambda kv: kv[1])
    out = []
    for j, (t, o) in enumerate(items):
        e = p0 + items[j + 1][1] if j + 1 < len(items) else len(rec)
        out.append((t, bytes(rec[p0 + o:e])))
    return out


def build(kids):
    pairs, off = [], 0
    for t, c in kids:
        pairs.append((t, off)); off += len(c)
    return enc_tblhdr(pairs) + b"".join(c for _, c in kids)


class Grid:
    pass


def load(path):
    return loads(open(path, "rb").read())


def loads(raw):
    assert raw[:5] == b"CFS\x00\x02"
    inner = bytearray(zlib.decompress(raw[5:]))
    root, base = tbl(inner, 0x13)
    kids, kb = tbl(inner, base + root[1])
    coff = kb + sorted(kids.items(), key=lambda x: x[1])[0][1]
    cf, cb = tbl(inner, coff + 4)
    g = Grid()
    g.inner, g.cb, g.cf = inner, cb, cf
    g.W, g.H = inner[cb + cf[3]], inner[cb + cf[4]]
    g.lvls = sorted(tbl(inner, cb + cf[1])[0].items())
    lk, g.lkb = tbl(inner, cb + cf[1])
    g.loff = g.lkb + dict(g.lvls)[0]
    lf, lb = tbl(inner, g.loff + 4)
    g.s, g.e = lb + 2, lb + lf[1]
    g.recs = []
    q = g.s
    while q < g.e and len(g.recs) < g.W * g.H:
        L = struct.unpack_from("<I", inner, q)[0]
        g.recs.append(bytes(inner[q + 4:q + 4 + L])); q += 4 + L
    assert q == g.e and len(g.recs) == g.W * g.H, (q, g.e, len(g.recs))
    return g


def dumps(g):
    stream = b"".join(struct.pack("<I", len(r)) + r for r in g.recs)
    delta = len(stream) - (g.e - g.s)
    out = bytearray(g.inner[:g.s]) + stream + g.inner[g.e:]
    kind, pos = tbl_entry_pos(out, g.loff + 4, 1)
    assert kind == "u32" or delta == 0 or out[pos] + delta <= 255
    if kind == "u32":
        struct.pack_into("<I", out, pos, struct.unpack_from("<I", out, pos)[0] + delta)
    else:
        out[pos] += delta
    for lid, lo in g.lvls:
        if g.lkb + lo > g.loff:
            k2, p2 = tbl_entry_pos(out, g.cb + g.cf[1], lid)
            if k2 == "u32":
                struct.pack_into("<I", out, p2, struct.unpack_from("<I", out, p2)[0] + delta)
            else:
                out[p2] += delta
    return b"CFS\x00\x02" + zlib.compress(bytes(out), 9)
