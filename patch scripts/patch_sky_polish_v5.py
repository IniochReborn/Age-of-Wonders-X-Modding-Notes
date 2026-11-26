#!/usr/bin/env python3
r"""
Sky polish v5 (2026-10-31) - supersedes v4 (revert patch_sky_polish_v4 first; this one re-applies all of it).

Editor AV 0x0000247C captured with diag_veh_attach (elevated): EngineP TECustomResourceGrid.GenerateResourceEditList
-> SetResource calls through a garbage object (heap pointer as VMT) while filling the palette.  The only
palette-visible change since v1 (which worked) is comb_res.pfs child 583 (Clear Sky combat hexagon), a clone of
child 581 that also copied its palette slot: page 0x22 cell 6 then held FOUR resources (569 water, 581 Sky,
582 Chasm, 583 Clear).  v5 gives 583 its own free cell 2 on that page.
Everything else = patch_sky_polish_v4.  Backups .bak_skypolish5.  Dry-run default; --apply; --revert.
"""
import os, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch_sky_polish_v4  # noqa: E402,F401  (installs the v3/v4 overrides on v2)
import patch_sky_polish_v2 as V2  # noqa: E402

CLR_CELL = 2


def pfs_build(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[4:-4]) & 0xFFFFFFFF, "comb_res CRC"
    ce, cbase, recs = V2.SC.pfs_records(b)
    if any(e[0] == V2.CLR_CHILD for e in ce):
        return None
    assert max(e[0] for e in ce) == V2.CLR_CHILD - 1
    s, t = recs[V2.SKY_CHILD]
    sky = b[s:t]
    fo, td = V2.H.fields(sky)
    assert struct.unpack_from("<I", sky, td + fo[1])[0] == 0xAA0E01 and sky[td + fo[7] + 4] == 0x0E
    page = struct.unpack_from("<I", sky, td + fo[2])[0]
    used = set()
    for c, (cs, ct) in recs.items():
        r = b[cs:ct]
        f2, d2 = V2.H.fields(r)
        if 2 in f2 and 3 in f2 and struct.unpack_from("<I", r, d2 + f2[2])[0] == page:
            used.add(struct.unpack_from("<I", r, d2 + f2[3])[0])
    assert CLR_CELL not in used, sorted(used)
    r = bytearray(sky)
    struct.pack_into("<I", r, td + fo[1], V2.CLR_RID)
    struct.pack_into("<I", r, td + fo[3], CLR_CELL)
    r = bytes(r).replace(b"SKYHEX00.ILB", b"CLRHEX00.ILB").replace(b"SKYANM00.ILB", b"CLRANM00.ILB")
    region = bytearray(b[cbase:len(b) - 4])
    ce.append([V2.CLR_CHILD, len(region), "d"])
    region += r
    out = bytearray(b[:0xD]) + V2.H.enc_table(ce) + region
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    ce2, cb2, recs2 = V2.SC.pfs_records(bytes(out))
    s2, t2 = recs2[V2.CLR_CHILD]
    assert out[s2:t2] == r and out[recs2[V2.SKY_CHILD][0]:recs2[V2.SKY_CHILD][1]] == sky
    return bytes(out)


V2.pfs_build = pfs_build
V2.TAG = ".bak_skypolish5"

if __name__ == "__main__":
    sys.exit(V2.main())
