#!/usr/bin/env python3
r"""
Sky polish v6 (2026-10-31) - supersedes v5 (revert patch_sky_polish_v5 first; this one re-applies all of it).

The editor AV (EngineP TECustomResourceGrid.SetResource on a freed object) followed comb_res.pfs child 583 (the
Clear Sky combat hexagon) from palette cell 6 to cell 2 (VEH dump 10/31: esi = cell, grid page 0x22) - the
engine frees/loses that cloned resource for a reason not found.  v6 drops the extra combat resource entirely:
  * no comb_res.pfs change, no CLRHEX00 / CLRANM00 files;
  * a Clear Sky battle is drawn by the overlay: battle setup (AoWTCPCK 0x424700, centre field resource is Clear)
    sets AoWEPACK BSS byte 0x558FAF30 (CCLEAR; AoWEPACK delta via the AoWHSMap import), and in combat mode every
    matched Sky-tile pixel is replaced by the Clear tile pixel at the same position (variant (x*3+y)&3) and shaded
    as Clear Sky (pale blue + white clouds).
Everything else = patch_sky_polish_v5 / v4 / v3.  Backups .bak_skypolish6.  Dry-run default; --apply; --revert.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch_sky_polish_v5  # noqa: E402,F401  (installs the v3/v4/v5 overrides on v2)
import patch_sky_polish_v2 as V2  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

_tc_src = V2.tc_src


def tc_src(combat_entry):
    s = _tc_src(combat_entry)
    a = """        mov ecx, dword ptr [ebx + {:#x}]
        sub ecx, {:#x}
        mov eax, esi
        mov byte ptr [ecx + {:#x}], al""".format(V2.TC_IAT_GETFIELD, V2.HSE_GETFIELD, V2.V1.FLAG)
    assert s.count(a) == 1
    return s.replace(a, """        mov ecx, dword ptr [ebx + {:#x}]
        sub ecx, {:#x}
        mov eax, esi
        mov byte ptr [ecx + {:#x}], al""".format(V2.TC_IAT_AOWHSMAP, OV.GLOBAL_MAP, OV.CCLEAR))


V2.tc_src = tc_src
V2.pfs_build = lambda b: None
V2.ILB_NAMES = ["SKYHEX00.ILB", "SKYANM00.ILB", "CHSANM00.ILB"]
V2.NEW_FILES = []
V2.TAG = ".bak_skypolish6"

if __name__ == "__main__":
    sys.exit(V2.main())
