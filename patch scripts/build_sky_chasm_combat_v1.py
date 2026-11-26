#!/usr/bin/env python3
r"""
Sky / Chasm battles + names (2026-10-31).  Companion of patch_sky_chasm_engine_v1.

User: "combat maps are just grass. it should have combat maps similar to water (full water/sky/chasm over
water/sky/chasm, and partial ... when adjacent). literally copy the water combat maps but change water terrain to
sky/chasm" + "rename them to Sky and Chasm".

How battles get their ground (RE 10/31): with no structure/bridge on the hex, AoWTCPCK TRndTacHsm.RandomMap
(0x4245EC) loads TCMaps\Blank000.HSM and paints it from 7 terrain bytes [map+0x9F0..0x9F6] (centre + 6 neighbour
sectors).  Water rules: centre Water(0)/Lava(9)/CaveWater(0xA) -> every sector = centre; land centre -> neighbour
sectors that are Water/Border(0xF)/CaveWater/Lava take the centre terrain.  Each sector is then filled with the
comb_res.pfs combat hexagon resource for its terrain; Sky/Chasm had none -> grass fallback.
  1. AoWTCPCK: both rules also treat 0xB/0xE like water (hooks 0x42477A centre test, 0x424818 neighbour test ->
     cave 0x454400, PIC rel32 only).
  2. Release\comb_res.pfs: the water combat hexagon (TWaterCombatHexagonResource 0x220598, child 569, terrain 0,
     Waterhex.ILB + WaterAnm.ILB) cloned twice -> terrain 0xE (SKYHEX00/SKYANM00.ILB, ResourceID 0xAA0E01) and
     0xB (CHSHEX00/CHSANM00.ILB, 0xAA0B01), appended as children 581/582 (offsets are table-relative -> nothing
     else moves), payload CRC32 fixed.
  3. Images\SKY*/CHS* ILBs from sky_chasm_combat_art.py (base tiles = the strategic Sky/Chasm tiles, waves
     recoloured, no fish).  ⚠ new files -> build_release_zip.py --add.
  4. Dict\ResStr.mld + ResStrV.mld: terrain names Original 'Coast' -> Sky, 'Reserved' -> Chasm (English column +
     de/fr/it/es; the key stays, as patch_translations_aowx does).
Dry-run default; --apply; --revert.  Backups: <file>.bak_skycombat (AoWTCPCK.dll, comb_res.pfs, both mld).
"""
import os, shutil, struct, subprocess, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools", "aowxlib"))
from bakpath import bak_path, game_dir, game_file
import build_rndhex_previews_hss_v1 as H

TC, TCBASE = game_file("AoWTCPCK.dll"), 0x400000
ZONE, ZONE_END = 0x454400, 0x454480
CENTRE, CENTRE_ORIG = 0x42477A, bytes.fromhex("8b45f80fbe80f00900006683f80a7531")
NEIGH, NEIGH_ORIG = 0x424818, bytes.fromhex("0fbe8402f00900006683f809751c")
PFS = game_file(os.path.join("Release", "comb_res.pfs"))
WATER_CHILD = 569
CLONES = [(581, 0xAA0E01, 0x0E, b"SKYHEX00.ILB", b"SKYANM00.ILB"),
          (582, 0xAA0B01, 0x0B, b"CHSHEX00.ILB", b"CHSANM00.ILB")]
MLDS = ["ResStr", "ResStrV"]
NAMES = {"Coast": ["Sky", "Himmel", "Ciel", "Cielo", "Cielo"],
         "Reserved": ["Chasm", "Abgrund", "Gouffre", "Abisso", "Abismo"]}   # columns: en, de, fr, it, es


def tc_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        mov  eax, dword ptr [ebp - 8]
        movsx eax, byte ptr [eax + 0x9F0]
        cmp  ax, 0xA
        je   cfill
        cmp  ax, 0xB
        je   cfill
        cmp  ax, 0xE
        je   cfill
        jmp  0x4247BB
    cfill:
        jmp  0x42478A
    neigh:
        movsx eax, byte ptr [edx + eax + 0x9F0]
        cmp  ax, 9
        je   nfill
        cmp  ax, 0xB
        je   nfill
        cmp  ax, 0xE
        je   nfill
        jmp  0x424842
    nfill:
        jmp  0x424826
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, ZONE)[0])
    k = code.index(bytes.fromhex("0fbe8402f0090000"))
    return code, ZONE + k


def pfs_records(b):
    ce, cbase = H.table(b, 0xD)
    order = sorted(ce, key=lambda e: e[1])
    recs = {}
    for k, e in enumerate(order):
        s = cbase + e[1]
        t = cbase + order[k + 1][1] if k + 1 < len(order) else len(b) - 4
        recs[e[0]] = (s, t)
    return ce, cbase, recs


def pfs_build(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[4:-4]) & 0xFFFFFFFF, "comb_res CRC"
    ce, cbase, recs = pfs_records(b)
    if any(e[0] == CLONES[0][0] for e in ce):
        return None
    assert max(e[0] for e in ce) == CLONES[0][0] - 1
    s, t = recs[WATER_CHILD]
    water = b[s:t]
    assert struct.unpack_from("<I", water, 0)[0] == 0x220598
    fo, td = H.fields(water)
    assert water[td + fo[7]:td + fo[7] + 6] == bytes.fromhex("0100000000fe")
    assert water.count(b"WATERHEX.ILB") >= 1 and water.count(b"WATERANM.ILB") >= 1
    region = bytearray(b[cbase:len(b) - 4])
    for child, rid, terr, hexf, anmf in CLONES:
        r = bytearray(water)
        struct.pack_into("<I", r, td + fo[1], rid)
        r[td + fo[7] + 4] = terr
        r = bytearray(bytes(r).replace(b"WATERHEX.ILB", hexf).replace(b"WATERANM.ILB", anmf))
        ce.append([child, len(region), "d"])
        region += r
    tbl = H.enc_table(ce)
    out = bytearray(b[:0xD]) + tbl + region
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    ce2, cb2, recs2 = pfs_records(bytes(out))
    for child, rid, terr, hexf, anmf in CLONES:
        s2, t2 = recs2[child]
        f2, d2 = H.fields(out[s2:t2])
        assert struct.unpack_from("<I", out, s2 + d2 + f2[1])[0] == rid and out[s2 + d2 + f2[7] + 4] == terr
    assert out[recs2[WATER_CHILD][0]:recs2[WATER_CHILD][1]] == water
    return bytes(out)


def mld_apply(path, revert_text=False):
    from mld import MLDFile
    m = MLDFile.load(path)
    n = 0
    for rec in m.records:
        o = rec.Original.decode("latin1")
        if o in NAMES and not rec.ClassName and not rec.ComponentName:
            for col, txt in enumerate(NAMES[o]):
                rec.translations[col] = txt.encode("latin1")
            n += 1
    return m, n


def mld_state(path):
    from mld import MLDFile
    m = MLDFile.load(path)
    st = set()
    for rec in m.records:
        o = rec.Original.decode("latin1")
        if o in NAMES and not rec.ClassName and not rec.ComponentName:
            st.add("ours" if rec.translations[0].decode("latin1") == NAMES[o][0] else "vanilla")
    return st


def running():
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    return "AoWx.exe" in r or "AoWDevX.exe" in r


def main():
    import pefile
    import sky_chasm_combat_art as ART
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    gd = game_dir()
    d = open(TC, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - TCBASE)  # noqa: E731
    cave, neigh_cave = tc_cave()
    assert ZONE + len(cave) <= ZONE_END
    P = [(CENTRE, CENTRE_ORIG, b"\xe9" + struct.pack("<i", ZONE - (CENTRE + 5)) + b"\x90" * 11),
         (NEIGH, NEIGH_ORIG, b"\xe9" + struct.pack("<i", neigh_cave - (NEIGH + 5)) + b"\x90" * 9),
         (ZONE, bytes(len(cave)), cave)]
    rl = {TCBASE + e.rva for blk in pe.DIRECTORY_ENTRY_BASERELOC for e in blk.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    sts = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    pb = open(PFS, "rb").read()
    pfs_new = pfs_build(pb)
    pst = "ours" if pfs_new is None else "vanilla"
    mst = set().union(*[mld_state(os.path.join(gd, "Dict", m + ".mld")) for m in MLDS])
    art = ART.OUT["sky"].values(), ART.OUT["chasm"].values()
    art_files = [os.path.join(gd, p) for grp in art for p in grp]
    ast = "ours" if all(os.path.exists(p) for p in art_files) else "vanilla"
    print("AoWTCPCK %s | relocs %s | comb_res %s | names %s | art %s" % (sts, bad or "none", pst, mst, ast))
    if "OTHER" in sts or bad or len(set(sts)) != 1 or len(mst) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if {sts[0], pst, ast} | mst == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if running():
        print("game/editor running - close it first"); return 1
    files = [TC, PFS] + [os.path.join(gd, "Dict", m + ".mld") for m in MLDS]
    if revert:
        for f in files:
            b = bak_path(f, ".bak_skycombat")
            if os.path.exists(b):
                shutil.copy2(b, f)
        for p in art_files:
            if os.path.exists(p):
                os.remove(p)
        print("reverted"); return 0
    for f in files:
        b = bak_path(f, ".bak_skycombat")
        if not os.path.exists(b):
            shutil.copy2(f, b)
    with open(TC, "r+b") as fh:
        for s, o, n in reversed(P):
            fh.seek(off(s)); fh.write(n)
    if pfs_new is not None:
        with open(PFS, "r+b") as fh:
            fh.write(pfs_new); fh.truncate()
    for m in MLDS:
        p = os.path.join(gd, "Dict", m + ".mld")
        mf, n = mld_apply(p)
        assert n == 2, (m, n)
        raw = mf.dump(exact=True)
        with open(p, "r+b") as fh:
            fh.write(raw); fh.truncate()
    for rel, raw in ART.build(gd).items():
        with open(os.path.join(gd, rel), "wb") as fh:
            fh.write(raw)
    d2 = open(TC, "rb").read()
    assert all(d2[off(s):off(s) + len(n)] == n for s, o, n in P)
    assert pfs_build(open(PFS, "rb").read()) is None
    assert set().union(*[mld_state(os.path.join(gd, "Dict", m + ".mld")) for m in MLDS]) == {"ours"}
    print("written and verified (AoWTCPCK, comb_res.pfs +2 records, 2 mld, %d ILBs)" % len(art_files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
