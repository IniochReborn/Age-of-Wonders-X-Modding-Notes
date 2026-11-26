#!/usr/bin/env python3
r"""
Release.hss: Ziggurat's underground Ziggurat + 6 underground altars (2026-10-31).

User ruling 10/31: "copy Ziggurat's underground Ziggurat structure and the 6 underground altars" (new unique
ResourceIDs - Ziggurat's underground copies reuse the surface RIDs, which our maps must never see twice).
Records copied verbatim from Ziggurat's Release.hss to our palette page 23 (uStructuresMOR), same cells, appended
as new children; only field 1 (ResourceID) is changed:
  Z 701  TPyramidResource-class 0x2038F  cell 41  Ziggurat (EPL_ZIG frames 12-16 = "ziggurat_expl1-5")
  Z 711  0x2023B cell 68 Fire altar         Z 712  0x2030D cell 72 Pestilence altar
  Z 713  0x2023E cell 73 Lightning altar    Z 1106 0x20234 cell 76 Life altar
  Z 1107 0x20236 cell 77 Death altar        Z 1108 0x2024C cell 78 Ice altar
Art: every referenced ILB is byte-identical in ours except Images\Epl_zig.ILB (ours 11 images, Ziggurat 16 - its
first 11 decode identically), which is replaced by Ziggurat's superset (⚠ ship it in the release).
Backups: <game>\backup\Release\Release.hss.bak_ugstruct + Images\Epl_zig.ILB.bak_ugstruct (restored by --revert).
⚠ apply after the cloud / rnd-preview / sky-bridge HSS scripts (their --revert restores older backups).
Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
from bakpath import bak_path, game_file
import build_rndhex_previews_hss_v1 as H

PAGE = 23
COPIES = [(701, 0x5A1A0001), (711, 0x5A1A0002), (712, 0x5A1A0003), (713, 0x5A1A0004),
          (1106, 0x5A1A0005), (1107, 0x5A1A0006), (1108, 0x5A1A0007)]
ILB_OURS = game_file(os.path.join("Images", "Epl_zig.ILB"))
ILB_ZIG = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\Images\EPL_ZIG.ILB"


def rid(r):
    fo, td = H.fields(r)
    return struct.unpack_from("<I", r, td + fo[1])[0] if 1 in fo else None


def build(b, z):
    A = H.parse(b); Z = H.parse(z)
    rids = {rid(r) for r in A["recs"].values()}
    done = [nr in rids for _, nr in COPIES]
    if all(done):
        return None
    assert not any(done)
    cells = {H.u32(r, 3) for r in A["recs"].values() if H.u32(r, 2) == PAGE}
    new = []
    for zc, nr in COPIES:
        r = bytearray(Z["recs"][zc])
        assert H.u32(r, 2) == PAGE and H.u32(r, 3) not in cells, (zc, H.u32(r, 3))
        fo, td = H.fields(r)
        struct.pack_into("<I", r, td + fo[1], nr)
        new.append(bytes(r))
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
    assert {c: bytes(v) for c, v in N["recs"].items() if c < nxt} == \
           {c: bytes(v) for c, v in H.parse(b)["recs"].items()}
    return bytes(nb)


def ilb_state():
    from aowxlib import ilb
    o = open(ILB_OURS, "rb").read(); z = open(ILB_ZIG, "rb").read()
    if o == z:
        return "ours"
    lo, lz = ilb.read(o), ilb.read(z)
    assert len(lo.images) == 11 and len(lz.images) == 16
    for i in range(11):
        assert ilb.decode_record(lo, lo.images[i].primary) == ilb.decode_record(lz, lz.images[i].primary), i
    return "vanilla"


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(H.OURS, ".bak_ugstruct"); ibak = bak_path(ILB_OURS, ".bak_ugstruct")
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    busy = "AoWx.exe" in r or "AoWDevX.exe" in r
    if revert:
        if busy:
            print("game/editor running - close it first"); return 1
        for src, dst in ((bak, H.OURS), (ibak, ILB_OURS)):
            if os.path.exists(src):
                shutil.copy2(src, dst); print("restored", src)
        return 0
    b = open(H.OURS, "rb").read()
    nb = build(b, open(H.ZIG, "rb").read())
    ist = ilb_state()
    print("Release.hss:", "already applied" if nb is None else "7 records appended (%d -> %d B)" % (len(b), len(nb)),
          "| Epl_zig.ILB:", ist)
    if nb is None and ist == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if busy:
        print("game/editor running - close it first"); return 1
    if nb is not None:
        if not os.path.exists(bak):
            shutil.copy2(H.OURS, bak)
        with open(H.OURS, "r+b") as f:
            f.write(nb); f.truncate()
        assert open(H.OURS, "rb").read() == nb
    if ist != "ours":
        if not os.path.exists(ibak):
            shutil.copy2(ILB_OURS, ibak)
        shutil.copyfile(ILB_ZIG, ILB_OURS)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
