#!/usr/bin/env python3
r"""
Release.hss: underground Ziggurat (RID 0x5A1A0001) gets the AoWx defender list (2026-11-07).

User: "i see underground ziggurat has all the BXL/ziggurat defenders. i specifically told you to ensure our AoWx
defender list was preserved".  Cause: build_underground_structures_hss_v1 (10/31) copied Ziggurat's child 701
verbatim INCLUDING its defender groups (field 25); the Highpass alias (0x06023E87, v2) was given the user's list but this
record never was (noted in memory, not raised with the user - my miss).
Fix: field 25 of 0x5A1A0001 := field 25 of OUR surface Ziggurat 0x04870B74 (the user's list, read from the CURRENT
Release.hss so today's editor edits are kept).  Only that one field of that one record changes: every other field of the
record (incl. field 10 the user's editor save changed today) and every other record are asserted byte-identical; the
file tail after the children region is asserted unmoved.  Backup <game>\backup\Release\Release.hss.bak_ugzigguards.
Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import build_zig_rid_alias_hss_v1 as Z  # noqa: E402

TARGET, SOURCE, FIELD = 0x5A1A0001, 0x04870B74, 25
TAG = ".bak_ugzigguards"


def rebuild_record(src, field, value):
    """same field order / table form, one field's bytes replaced"""
    order, data = Z.fdata(src)
    data[field] = value
    ents, body = [], bytearray()
    for t in order:
        ents.append([t, len(body), "b"]); body += data[t]
    r = bytes(src[:4] + H.enc_table(ents) + body)
    o2, d2 = Z.fdata(r)
    assert o2 == order and all(d2[t] == data[t] for t in order)
    return r


def build(b):
    A = H.parse(b)
    by_rid = {Z.rid(bytes(r)): k for k, r in A["recs"].items()}
    cid = by_rid[TARGET]
    guards = Z.fdata(bytes(A["recs"][by_rid[SOURCE]]))[1][FIELD]
    old = bytes(A["recs"][cid])
    if Z.fdata(old)[1][FIELD] == guards:
        return None, cid, guards
    A["recs"][cid] = bytearray(rebuild_record(old, FIELD, guards))
    region = bytearray(); offs = {}
    for c in A["order"]:
        offs[c] = len(region); region += A["recs"][c]
    for e in A["ce"]:
        e[1] = offs[e[0]]
    ct = H.enc_table(A["ce"])
    shift_tbl = len(ct) - (A["cbase"] - A["ctp"])
    growth = len(region) - (A["region_end"] - A["cbase"]) + shift_tbl
    nb = bytearray(b[:A["ctp"]] + ct + region + b[A["region_end"]:-4])
    root = A["root"]
    for x in root:
        if x[1] > A["f5"]:
            x[1] += growth
    rt = H.enc_table(root); assert len(rt) == A["rds"] - 0x37
    nb[0x37:A["rds"]] = rt
    if shift_tbl:
        oe, ods = H.table(nb, A["rds"] + A["f5"])
        for x in oe:
            if x[1] > [e for e in oe if e[0] == 1][0][1]:
                x[1] += shift_tbl
        ot = H.enc_table(oe)
        st = A["rds"] + A["f5"]
        assert len(ot) == ods - st
        nb[st:ods] = ot
    nb += struct.pack("<I", zlib.crc32(bytes(nb)) & 0xFFFFFFFF)
    N = H.parse(bytes(nb))
    assert bytes(nb[N["region_end"]:-4]) == b[A["region_end"]:-4], "tail moved wrongly"
    B0 = H.parse(b)
    for c, v in N["recs"].items():
        if c == cid:
            o_new, d_new = Z.fdata(bytes(v)); o_old, d_old = Z.fdata(old)
            assert o_new == o_old and d_new[FIELD] == guards
            assert all(d_new[t] == d_old[t] for t in o_old if t != FIELD), "another field changed"
        else:
            assert bytes(v) == bytes(B0["recs"][c]), c
    return bytes(nb), cid, guards


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bk = bak_path(H.OURS, TAG)
    if (apply or revert) and H.running():
        print("game/editor running - close it first"); return 1
    if revert:
        if os.path.exists(bk):
            shutil.copy2(bk, H.OURS); print("restored", bk)
        return 0
    b = open(H.OURS, "rb").read()
    nb, cid, guards = build(b)
    g = struct.unpack_from("<%di" % (len(guards) // 4), guards)
    print("underground Ziggurat child %d: defender list := surface Ziggurat's (%d groups, %d entries)"
          % (cid, g.count(-1), len(g)))
    if nb is None:
        print("already applied"); return 0
    print("Release.hss %d -> %d B" % (len(b), len(nb)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bk):
        shutil.copy2(H.OURS, bk)
    with open(H.OURS, "r+b") as fh:
        fh.seek(0); fh.write(nb); fh.truncate()
    assert open(H.OURS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
