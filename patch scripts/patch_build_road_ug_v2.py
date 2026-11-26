#!/usr/bin/env python3
r"""
Construct (Build Road) underground, part 2: the level gate (2026-11-04).

v1 (patch_build_road_ug_v1) let terrain 0x0C pass the per-field check; user: "i still cant build roads underground
with the construct ability" -> the Construct ability's activation (AoWEPACK 0x55770EAC) calls TAbstractUnit.GetLocation
and refuses ANY level != 0 with "Cannot build %s in underground" (CannotBuildXInUndergroundRStr):
`cmp byte [ebp-3],0 / jne 0x55770EFA` @0x55770EE5 -> the jne is NOPed (the per-field terrain check still decides
where a road can go: surface 1..5 + UG dirt 0x0C; Sky/Chasm/rock stay refused).
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

TAG = ".bak_ugbuildroad2"
SITE, ORIG, NEW = 0x55770EE9, bytes.fromhex("750f"), bytes.fromhex("9090")


def patches():
    return [(SITE, ORIG, NEW)]


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
