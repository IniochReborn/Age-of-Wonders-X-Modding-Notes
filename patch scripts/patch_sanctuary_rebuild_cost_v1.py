#!/usr/bin/env python3
r"""
Magic Sanctuary rebuild cost 75 gold (2026-10-31).  Companion of patch_sanctuary_raze_v1.

User: "change rebuild cost to 75 gold for sanctuary".  TStructure.GetRebuildInfo 0x5575F18C hardcodes the cost
(`mov [edx],0x32`) for every structure, days = [res+0x5B].  All rebuild paths call it through vmt+0x1DC (UI, the
existing cost hook 0x5585C260, ExecuteRebuild), so TMagicSanctuary's VMT slot +0x1DC (0x557D43D0) gets its own
copy returning 75.  Cave AoWEPACK 0x558E0200 'SNC2' (rel-free).  Backup .bak_sanctcost.  Dry-run; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
VMT, SLOT, ORIG_FN = 0x557D41F4, 0x1DC, 0x5575F18C
ZONE, ZONE_END, MAGIC = 0x558E0200, 0x558E0240, b"SNC2"
COST = 75


def patches():
    code = OV.asm(f"""
        push ebx
        mov ebx, dword ptr [eax + 8]
        mov dword ptr [edx], {COST}
        xor eax, eax
        mov al, byte ptr [ebx + 0x5b]
        mov dword ptr [ecx], eax
        pop ebx
        ret
    """, ZONE + 0x10)
    z = MAGIC + bytes(12) + code
    assert ZONE + len(z) <= ZONE_END
    return [(VMT + SLOT, struct.pack("<I", ORIG_FN), struct.pack("<I", ZONE + 0x10)), (ZONE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read(); pe = pefile.PE(data=d)
    P = patches()
    st, bad = SP.state(d, pe, BASE, P)
    bad = [x for x in bad if x != hex(VMT + SLOT)]        # the VMT slot is a relocated pointer (expected)
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    bk = bak_path(DLL, ".bak_sanctcost")
    if not revert and not os.path.exists(bk):
        shutil.copy2(DLL, bk)
    SP.write_bytes(DLL, BASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
