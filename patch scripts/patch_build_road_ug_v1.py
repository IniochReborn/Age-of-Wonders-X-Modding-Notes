#!/usr/bin/env python3
r"""
Construct (Build Road) on underground dirt (2026-11-04).

User: "i want to be able to build roads underground too, using the construct ability. like on the surface".
AoWEPACK 0x55770FF0 = can-build-a-road-on-field (used by the road-build cost/path code 0x55771138 and the road
placer 0x55771068): field level ok, terrain [field+0x14] in 1..5 (`dec eax / sub al,5 / jb`), overlay [field+0x15]
not 0/2/4/5 (4 = road already), no blocking structure.  Underground cave floor = terrain 0x0C, which now has a road
resource (build_ug_dirt_road_hss_v1: Ziggurat's rid 0x5A190001) -> allow 0x0C as well.
Site 0x55771018 (8 B) -> cave AoWEPACK 0x558E0E00 'URB1' (PIC).  Backup .bak_ugbuildroad.  Dry-run; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_ugbuildroad"
SITE, ORIG = 0x55771018, bytes.fromhex("8a4614482c057204")
OK, NO = 0x55771024, 0x55771020
CAVE, CAVE_END, MAGIC = 0x558E0E00, 0x558E0E40, b"URB1"
UG_DIRT = 0x0C


def patches():
    at = CAVE + len(MAGIC)
    code = OV.asm(f"""
        mov al, byte ptr [esi + 0x14]
        cmp al, {UG_DIRT:#x}
        je ok
        dec eax
        sub al, 5
        jb ok
        jmp {NO:#x}
    ok:
        jmp {OK:#x}
    """, at)
    z = MAGIC + code
    assert CAVE + len(z) <= CAVE_END
    return [(SITE, ORIG, b"\xe9" + struct.pack("<i", at - (SITE + 5)) + b"\x90" * 3),
            (CAVE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = patches()
    st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted")
        return 0
    if st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
