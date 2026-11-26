#!/usr/bin/env python3
r"""
Release.hss: real editor previews for the 9 TRndHexagonResource brushes (2026-10-31).

User: some editor palette cells (Surface > Objects Lava/Dirt/Border, EResourceGrid1 Border/Grass/Steppe/Desert,
DirtMOR Snow/Wasteland) show a BLACK preview where BXL's Ziggurat shows real art.  Cause (vanilla 1.36 too): the
records' last field (f8) is an empty 32-byte embedded mini-ILB stub.  BXL filled each with a 50x42 'raised hex on a
plinth' bitmap.  This copies his f8 blob into our records (matched by class/EditID/EditIndex + terrain list); our
ResourceIDs and names stay.  Records grow ~3.4 KB each -> children region rebuilt, root offsets shifted, CRC32 fixed.
--sky (optional, NOT default) also re-skins the 8 Coast + 15 uWasteland tiles with BXL's Sky/Chasm art (art only).

Source: C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\Release\Release.hss (read only).
NOTE: apply AFTER build_cloud_variants_hss_v1 (its --revert restores .bak_cloudvar and would drop this).
Backup <game>\backup\Release\Release.hss.bak_rndhex.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

OURS = game_file(os.path.join("Release", "Release.hss"))
ZIG = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\Release\Release.hss"


def table(b, p):
    t = b[p]; p += 1; nd = 0
    if t & 0x80:
        nd = struct.unpack_from("<I", b, p)[0]; p += 4
    ents = []
    for _ in range(t & 0x7F):
        ents.append([b[p], b[p + 1], "b"]); p += 2
    for _ in range(nd):
        i, o = struct.unpack_from("<II", b, p); ents.append([i, o, "d"]); p += 8
    return ents, p


def enc_table(ents):
    for e in ents:
        if e[2] == "b" and (e[1] > 255 or e[0] > 255):
            e[2] = "d"
    bt = [e for e in ents if e[2] == "b"]; dt = [e for e in ents if e[2] == "d"]
    out = bytearray([len(bt) | (0x80 if dt else 0)])
    if dt:
        out += struct.pack("<I", len(dt))
    for i, o, _ in bt:
        out += bytes([i, o])
    for i, o, _ in dt:
        out += struct.pack("<II", i, o)
    return bytes(out)


def parse(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[:-4]) & 0xFFFFFFFF, "CRC bad"
    root, rds = table(b, 0x37)
    f5 = [e for e in root if e[0] == 5][0][1]
    oe, ods = table(b, rds + f5)
    ctp = ods + [e for e in oe if e[0] == 1][0][1]
    ce, cbase = table(b, ctp)
    region_end = rds + min(o for i, o, k in root if o > f5)
    order = sorted(ce, key=lambda e: e[1])
    recs = {}
    for k, e in enumerate(order):
        s = cbase + e[1]
        t = cbase + order[k + 1][1] if k + 1 < len(order) else region_end
        recs[e[0]] = bytearray(b[s:t])
    return dict(root=root, rds=rds, f5=f5, ctp=ctp, ce=ce, cbase=cbase, region_end=region_end,
                order=[e[0] for e in order], recs=recs)


def fields(rec):
    te, td = table(rec, 4)
    return {x[0]: x[1] for x in te}, td


def u32(rec, f):
    fo, td = fields(rec)
    return struct.unpack_from("<I", rec, td + fo[f])[0] if f in fo else None


def key(rec):
    return (struct.unpack_from("<I", rec, 0)[0], u32(rec, 2), u32(rec, 3))


def terr(rec):
    fo, td = fields(rec)
    n = struct.unpack_from("<I", rec, td + fo[7])[0]
    return bytes(rec[td + fo[7] + 4: td + fo[7] + 4 + 2 * n])


def emb_span(rec):
    k = rec.index(b"\x04ILB\x00")
    return k, k + struct.unpack_from("<I", rec, k + 20)[0]


def build(b, z, sky):
    A = parse(b); Z = parse(z)
    zk = {}
    for cid, r in Z["recs"].items():
        zk.setdefault(key(r), []).append(cid)
    log = []
    n_done = 0
    for cid, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != 0x20154:
            continue
        zc = zk.get(key(r))
        assert zc and len(zc) == 1, ("no Z partner", cid, key(r))
        zr = Z["recs"][zc[0]]
        assert terr(r) == terr(zr), (cid, terr(r), terr(zr))
        fo, td = fields(r); zfo, ztd = fields(zr)
        assert max(fo.values()) == fo[8] and max(zfo.values()) == zfo[8]
        old = bytes(r[td + fo[8]:]); new = bytes(zr[ztd + zfo[8]:])
        if old == new:
            n_done += 1; continue
        assert len(old) == 32 and old.startswith(b"\x04ILB"), (cid, len(old))
        A["recs"][cid] = bytearray(r[:td + fo[8]] + new)
        log.append("rnd  ch%d (%d,%d) terr %s  +%d B" % (cid, key(r)[1], key(r)[2], terr(r).hex(), len(new) - len(old)))
    if sky:
        for cid, r in A["recs"].items():
            if struct.unpack_from("<I", r, 0)[0] != 0x20153 or terr(r) not in (b"\x0e\xfe", b"\x0b\xfe"):
                continue
            zc = zk.get(key(r)); assert zc and len(zc) == 1, (cid, key(r))
            zr = Z["recs"][zc[0]]
            s, e = emb_span(r); zs, ze = emb_span(zr)
            assert e - s == ze - zs and terr(r) == terr(zr)
            if r[s:e] != zr[zs:ze]:
                r[s:e] = zr[zs:ze]
                log.append("tile ch%d (%d,%d) terr %s" % (cid, key(r)[1], key(r)[2], terr(r).hex()))
    if not log:
        return None, log, n_done
    new_region = bytearray(); ce = A["ce"]; offs = {}
    for cid in A["order"]:
        offs[cid] = len(new_region); new_region += A["recs"][cid]
    for e in ce:
        e[1] = offs[e[0]]
    ct = enc_table(ce)
    assert len(ct) == A["cbase"] - A["ctp"], "children table size changed"
    growth = len(new_region) - (A["region_end"] - A["cbase"])
    nb = bytearray(b[:A["ctp"]] + ct + new_region + b[A["region_end"]:-4])
    root = A["root"]
    for x in root:
        if x[1] > A["f5"]:
            x[1] += growth
    rt = enc_table(root); assert len(rt) == A["rds"] - 0x37
    nb[0x37:A["rds"]] = rt
    nb += struct.pack("<I", zlib.crc32(bytes(nb)) & 0xFFFFFFFF)
    N = parse(bytes(nb))
    assert bytes(nb[N["region_end"]:-4]) == b[A["region_end"]:-4], "tail moved wrongly"
    return bytes(nb), log, n_done


def running():
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    return "AoWx.exe" in r or "AoWDevX.exe" in r


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv; sky = "--sky" in sys.argv
    bak = bak_path(OURS, ".bak_rndhex")
    if revert:
        if not os.path.exists(bak):
            print("no backup", bak); return 1
        if running():
            print("game/editor running - close it first"); return 1
        shutil.copy2(bak, OURS); print("restored", bak); return 0
    b = open(OURS, "rb").read(); z = open(ZIG, "rb").read()
    nb, log, n_done = build(b, z, sky)
    print("\n".join(log) if log else "nothing to change (%d rnd records already carry the art)" % n_done)
    if nb is None:
        print("already applied"); return 0
    print("size %d -> %d (+%d)" % (len(b), len(nb), len(nb) - len(b)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if running():
        print("game/editor running - close it first"); return 1
    if not os.path.exists(bak):
        shutil.copy2(OURS, bak); print("backup ->", bak)
    with open(OURS, "r+b") as f:
        f.write(nb); f.truncate()
    assert open(OURS, "rb").read() == nb
    parse(nb)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
