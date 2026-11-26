#!/usr/bin/env python3
r"""
Release.hss: bridges over Sky and Chasm (2026-10-31; Ziggurat's records).

User: "it doesnt let me place bridges over sky/chasm, it should".  Bridges are road-tool data on page 6
(HiddenResourceGrid): the road brush places the bridge resource whose terrain list matches the field.  Ziggurat
added four (art embedded in each record, so no ILB files needed) - copied verbatim, appended as new children:
  Z 1127 TBridgeResource        rid 0x5A190002  cell 38  terrain Chasm(0xB) ov5  (Uwa_bdge art)
  Z 1128 THexagonBridgeResource rid 0x5A190003  cell 39  terrain Chasm         (U_brdg)
  Z 1129 TBridgeResource        rid 0x5A190004  cell 40  terrain Sky(0xE)      (Wa_bdge)
  Z 1130 THexagonBridgeResource rid 0x5A190005  cell 41  terrain Sky           (Str_brdg)
and, like Ziggurat, the vanilla water bridge (child 126, rid 0x32) is re-keyed Coast(0xE) -> Water(0): 0xE is Sky
now and has its own bridge.  Movement already allows walkers on the bridge overlay (patch_sky_chasm_engine_v1).
Rids/cells verified unused in ours.  Backup <game>\backup\Release\Release.hss.bak_skybridge (restored by --revert).
⚠ apply after the cloud-variant / rnd-preview scripts (their --revert restores older backups).
Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path
import build_rndhex_previews_hss_v1 as H

ZIG_CHILDREN = [1127, 1128, 1129, 1130]
WATER_BRIDGE_RID = 0x32


def rid(r):
    fo, td = H.fields(r)
    return struct.unpack_from("<I", r, td + fo[1])[0] if 1 in fo else None


def build(b, z):
    A = H.parse(b); Z = H.parse(z)
    rids = {rid(r) for r in A["recs"].values()}
    new = [bytes(Z["recs"][c]) for c in ZIG_CHILDREN]
    done = [rid(r) in rids for r in new]
    if all(done):
        return None
    assert not any(done)
    p6 = {H.u32(r, 3) for r in A["recs"].values() if H.u32(r, 2) == 6}
    for r in new:
        assert H.u32(r, 2) == 6 and H.u32(r, 3) not in p6, (hex(rid(r)), H.u32(r, 3))
    wb = [c for c, r in A["recs"].items() if rid(r) == WATER_BRIDGE_RID]
    assert len(wb) == 1
    r = A["recs"][wb[0]]
    fo, td = H.fields(r)
    pos = td + fo[7] + 4
    assert r[pos:pos + 2] == b"\x0e\x05", r[pos:pos + 2]
    r[pos] = 0x00
    nxt = max(A["recs"]) + 1
    for k, rec in enumerate(new):
        A["recs"][nxt + k] = bytearray(rec)
        A["order"].append(nxt + k)
        A["ce"].append([nxt + k, 0, "d"])
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
    # owner table: child table lives inside f5 (owner); its own entries after field 1 need the table growth too
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
    for k, rec in enumerate(new):
        assert bytes(N["recs"][nxt + k]) == rec
    assert {c: bytes(v) for c, v in N["recs"].items() if c < nxt and c != wb[0]} == \
           {c: bytes(v) for c, v in H.parse(b)["recs"].items() if c != wb[0]}
    return bytes(nb)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(H.OURS, ".bak_skybridge")
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
    print("4 bridge records appended, water bridge 0x32 -> terrain 0 | size %d -> %d" % (len(b), len(nb)))
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
