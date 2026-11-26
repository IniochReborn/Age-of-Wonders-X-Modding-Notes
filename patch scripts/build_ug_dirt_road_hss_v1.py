#!/usr/bin/env python3
r"""
Release.hss: roads on underground dirt (2026-11-04; Ziggurat's record).

User: "allowing roads to be placed on dirt underground ... will probably also need combat maps to suit".
Roads are data: HSEngine TAbstractRoad.CanPlace (HSE 0x5560A820) only accepts a field whose terrain byte
[field+0x14] equals the road resource's terrain-list entry (record field 7 = u32 count, u8 terrain, u8 overlay 4);
vanilla has five TRoadResource (0x20165) records for terrains 1..5 only.  Ziggurat adds one more = the Wasteland road
(Rd_Wl art, embedded) keyed to terrain 0x0C (underground cave floor) - copied verbatim:
  Z 1126 TRoadResource  rid 0x5A190001  page 6 cell 37  terrain 0x0C overlay 4
Same rid/cell as Ziggurat, so Ziggurat maps with underground roads load in AoWx.  Cell 37 verified free.
Combat: nothing to add - comb_res already has a TCombatRoad for combat terrain 0x0C (rid 0xDE69F39, underground combat
page 0x1D cell 1, H_STDR art); the combat generator (AoWTCPCK 0x425353: [field+0x15] == 4 = road overlay) lays it.
Backup <game>\backup\Release\Release.hss.bak_ugroad (restored by --revert).  Dry-run default; --apply; --revert.
⚠ apply after the cloud-variant / rnd-preview / sky-bridge scripts (their --revert restores older backups).
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path
import build_rndhex_previews_hss_v1 as H
import build_sky_chasm_bridges_hss_v1 as B

ZIG_CHILD = 1126
RID, CELL, TERRAIN = 0x5A190001, 37, 0x0C


def build(b, z):
    A = H.parse(b); Z = H.parse(z)
    rec = bytes(Z["recs"][ZIG_CHILD])
    assert B.rid(rec) == RID and H.u32(rec, 2) == 6 and H.u32(rec, 3) == CELL
    fo, td = H.fields(rec)
    assert rec[td + fo[7]:td + fo[7] + 6] == struct.pack("<I", 1) + bytes([TERRAIN, 4])
    rids = {B.rid(r) for r in A["recs"].values()}
    if RID in rids:
        return None
    assert CELL not in {H.u32(r, 3) for r in A["recs"].values() if H.u32(r, 2) == 6}
    # graft through the bridge builder's append machinery with a one-record list
    saved = B.ZIG_CHILDREN, B.WATER_BRIDGE_RID
    try:
        B.ZIG_CHILDREN = [ZIG_CHILD]
        return append_one(b, rec, A)
    finally:
        B.ZIG_CHILDREN, B.WATER_BRIDGE_RID = saved


def append_one(b, rec, A):
    import zlib
    nxt = max(A["recs"]) + 1
    A["recs"][nxt] = bytearray(rec); A["order"].append(nxt); A["ce"].append([nxt, 0, "d"])
    region = bytearray(); offs = {}
    for cid in A["order"]:
        offs[cid] = len(region); region += A["recs"][cid]
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
        f1 = [e for e in oe if e[0] == 1][0][1]
        for x in oe:
            if x[1] > f1:
                x[1] += shift_tbl
        ot = H.enc_table(oe); st = A["rds"] + A["f5"]
        assert len(ot) == ods - st
        nb[st:ods] = ot
    nb += struct.pack("<I", zlib.crc32(bytes(nb)) & 0xFFFFFFFF)
    N = H.parse(bytes(nb))
    assert bytes(nb[N["region_end"]:-4]) == b[A["region_end"]:-4], "tail moved wrongly"
    assert bytes(N["recs"][nxt]) == rec
    old = H.parse(b)["recs"]
    assert all(bytes(N["recs"][c]) == bytes(v) for c, v in old.items())
    return bytes(nb)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(H.OURS, ".bak_ugroad")
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    busy = "AoWx.exe" in r or "AoWDevX.exe" in r
    if revert:
        if not os.path.exists(bak):
            print("no backup", bak); return 1
        if busy:
            print("game/editor running - close it first"); return 1
        shutil.copy2(bak, H.OURS); print("restored", bak); return 0
    b = open(H.OURS, "rb").read()
    nb = build(b, open(H.ZIG, "rb").read())
    if nb is None:
        print("already applied"); return 0
    print("UG dirt road appended (rid %#x, page 6 cell %d, terrain %#x) | size %d -> %d" % (RID, CELL, TERRAIN, len(b), len(nb)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if busy:
        print("game/editor running - close it first"); return 1
    if not os.path.exists(bak):
        shutil.copy2(H.OURS, bak); print("backup ->", bak)
    with open(H.OURS, "r+b") as f:
        f.write(nb); f.truncate()
    assert open(H.OURS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
