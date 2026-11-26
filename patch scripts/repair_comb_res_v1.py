#!/usr/bin/env python3
r"""
repair_comb_res_v1 (2026-11-02) - restore records lost from Release\comb_res.pfs.

MP report 11/01: water-node battles all grass + flashing hexes.  Cause: comb_res.pfs had been RE-SAVED by the engine
(30 records differ only in animation start-frame bytes) between 10/31 04:47 and 16:36, and again after 18:46.  The
save keeps ONE resource per palette cell (field 2 page, field 3 cell); our clones shared their source's cell, so the
save dropped:  0x5A8502 water combat hexagon (vanilla child 569) + 0xAA0E01 Sky hex (cell shared with water/Chasm),
and later 0x15F5B08 node centre structure (vanilla child 579, cell shared with the Nest clone 0xE1608C).

Rebuild: children 0..580 = vanilla order (live bytes where the record survived, .bak_skypolish5 bytes for the lost
ones), 581 Sky (backup), 582 Chasm (live), 583 Nest (live).  Every RID verified unique.  Backup .bak_repair1.
Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_sky_chasm_combat_v1 as SC  # noqa: E402
from bakpath import game_file, bak_path  # noqa: E402

H = SC.H
PFS = game_file(os.path.join("Release", "comb_res.pfs"))
GOOD = game_file(os.path.join("backup", "Release", "comb_res.pfs.bak_skypolish5"))
TAG = ".bak_repair1"
TAIL = [0xAA0E01, 0xAA0B01, 0xE1608C]          # 581 Sky, 582 Chasm, 583 Nest


def by_rid(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[4:-4]) & 0xFFFFFFFF, "CRC"
    ce, cbase, recs = SC.pfs_records(b)
    order, d = [], {}
    for c in sorted(recs):
        s, t = recs[c]
        r = b[s:t]
        try:
            fo, td = H.fields(r)
            k = struct.unpack_from("<I", r, td + fo[1])[0]
        except Exception:
            k = ("noid", c)
        assert k not in d, ("dup rid", k)
        d[k] = r
        order.append(k)
    return order, d


def build(live, good):
    gorder, gd = by_rid(good)
    lorder, ld = by_rid(live)
    if len(lorder) == 584 and lorder[581:] == TAIL and all(k in ld for k in gorder):
        return None, []
    want = gorder[:581] + TAIL
    restored = []
    recs = []
    for k in want:
        if k in ld:
            recs.append(ld[k])
        else:
            recs.append(gd[k]); restored.append(k)
    extra = [k for k in lorder if k not in want]
    assert not extra, ("live has unexpected records", extra)
    ce, region = [], bytearray()
    for i, r in enumerate(recs):
        ce.append([i, len(region), "d"])
        region += r
    out = bytearray(live[:0xD]) + H.enc_table(ce) + region
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    o2, d2 = by_rid(bytes(out))
    assert o2 == want and all(d2[k] == (ld.get(k) or gd[k]) for k in want)
    return bytes(out), restored


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry"
    bak = bak_path(PFS, TAG)
    if mode == "--revert":
        shutil.copy2(bak, PFS); print("restored", bak); return 0
    live = open(PFS, "rb").read()
    out, restored = build(live, open(GOOD, "rb").read())
    if out is None:
        print("comb_res.pfs already repaired"); return 0
    print("comb_res.pfs: %d -> %d B, restored %s" % (len(live), len(out), [hex(k) for k in restored]))
    if mode == "--apply":
        if not os.path.exists(bak):
            shutil.copy2(PFS, bak)
        with open(PFS, "r+b") as f:
            f.write(out); f.truncate()
        assert open(PFS, "rb").read() == out
        print("written and verified; backup", bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
