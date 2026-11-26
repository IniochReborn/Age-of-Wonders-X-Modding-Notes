#!/usr/bin/env python3
r"""
Great Eagle's Nest v7 (2026-10-31) - on top of patch_eagle_nest_v6.

User: "for the combat map unit placement, defenders should spawn in the nest "empty" area ... also adjust flag
placement on overworld. the flagpole should be mounted to top right side of mountain/nest".
  1. Combat (TCMaps\Nest0000.hsm): the defenders' deployment markers (TCMaps object class 0x220103: fields 0x19 =
     group (absent = 0 = defenders), 0x1A = slot, 0x1B = facing?) ring the centre structure at (32,28) 2-3 hexes
     out, many on hexes holding v2's rocks.  Every decor object inside DEF_BOX (decor record `03 01 00 03 04 04 05
     <guid> <x> <y>`: field 1 = resource id, 3 = x, 4 = y) becomes a crop/hay clump (ZGR_CROP resources 133/131/132)
     -> the defenders deploy in the hay field around the nest.  The remaining trees / pines / dead trees / shrubs
     v2 missed (TREES) become rocks map-wide.  Same-size GUID swaps only (markers are nested in
     the per-hex records; moving them would need the stream rebuilt).
  2. Overworld flag: TPlayerStructure.Show draws the owner flag at hex + (res+0x68, res+0x6C) via
     TFlagControl.ShowFlag 0x5575A1E8 / ShowStructureFlag 0x5575A34C (pole = 9x54 sprite with its top-left at that
     point, foot ~(+4,+53); cloth to its upper right).  Both call sites (0x55761002 / 0x55761032, `mov ecx,[eax+6Ch];
     add ecx,edi; mov e?x,[eax+68h]; add e?x,esi`) -> cave 0x558E0380: for the Nest (ResourceID 0x00E16088) use
     FLAG = (25,-69) -> pole foot on the top-right rim of the crag (sprite top-right corner ~(32,-17)).
Backups .bak_eagle7 (Nest0000.hsm, AoWEPACK.dll).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v3 as V3  # noqa: E402

TAG = ".bak_eagle7"
NESTMAP = V2.NESTMAP
DEF_BOX = (29, 35, 26, 30)                      # x0, x1, y0, y1 (inclusive) around the structure at (32, 28)
CROPS = (0x6AF9D09, 0xF39BD87, 0xE9B5BE7)
FLAG = (25, -69)
TREES = {0x4409E57: 0x91FCB65, 0x72C74D1: 0x9EAE2FB, 0x51D2637: 0x91FCB65, 0xAF11D29: 0x9EAE2FB,   # trees / pines /
         0xB2719C3: 0x4250DFE, 0x218373C: 0x0E7A7B7}                                              # dead tree, shrub -> rocks
CAVE, CAVE_END, MAGIC = 0x558E0380, 0x558E0400, b"EGF1"
SITES = [(0x55761002, bytes.fromhex("8b486c03cf8b406803c6"), 0x5576100C, "eax"),
         (0x55761032, bytes.fromhex("8b486c03cf8b506803d6"), 0x5576103C, "edx")]


def build_nestmap():
    raw, _ = V3.build_nestmap()
    d = bytearray(zlib.decompress(raw[5:]))
    tag = b"\x03\x01\x00\x03\x04\x04\x05"
    n = 0
    i = d.find(tag)
    while i >= 0:
        g = struct.unpack_from("<I", d, i + 7)[0]
        x, y = d[i + 11], d[i + 12]
        if g != V3.NEW_RID and DEF_BOX[0] <= x <= DEF_BOX[1] and DEF_BOX[2] <= y <= DEF_BOX[3]:
            struct.pack_into("<I", d, i + 7, CROPS[n % len(CROPS)]); n += 1
        elif g in TREES:                                    # v2 missed these: no trees on the Nest map at all
            struct.pack_into("<I", d, i + 7, TREES[g])
        i = d.find(tag, i + 1)
    return b"CFS\x00\x02" + zlib.compress(bytes(d), 9), n


def epk_patches():
    P = []
    at = CAVE + len(MAGIC)
    blob = bytearray(MAGIC)
    for site, orig, back, reg in SITES:
        code = OV.asm(f"""
            cmp dword ptr [eax + 0xc], {V2.RID:#x}
            je nest
            mov ecx, dword ptr [eax + 0x6c]
            add ecx, edi
            mov {reg}, dword ptr [eax + 0x68]
            add {reg}, esi
            jmp {back:#x}
        nest:
            mov ecx, {FLAG[1]}
            add ecx, edi
            mov {reg}, {FLAG[0]}
            add {reg}, esi
            jmp {back:#x}
        """, at)
        P.append((site, orig, b"\xe9" + struct.pack("<i", at - (site + 5)) + b"\x90" * 5))
        blob += code; at += len(code)
    assert len(blob) <= CAVE_END - CAVE
    P.append((CAVE, bytes(len(blob)), bytes(blob)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        bk = bak_path(NESTMAP, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, NESTMAP); print("restored", bk)
        return 0
    nm, n = build_nestmap()
    nm = None if open(NESTMAP, "rb").read() == nm else nm
    print("Nest0000.hsm", "already applied" if nm is None else "write (%d decor -> crops)" % n)
    if nm is None and st[0] == "ours":
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    if nm is not None:
        bk = bak_path(NESTMAP, TAG)
        if not os.path.exists(bk):
            shutil.copy2(NESTMAP, bk)
        with open(NESTMAP, "r+b") as fh:
            fh.write(nm); fh.truncate()
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
