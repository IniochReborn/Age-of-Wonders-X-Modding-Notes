#!/usr/bin/env python3
r"""
Razeable Magic Sanctuary - side-window raze button (AoWx.exe, 2026-10-31).  Companion of patch_sanctuary_raze_v1.

User after patch_sanctuary_raze_v1: "i can set raze defenders in the editor, but nothing else works (not razeable)".
Cause: the side info window's class dispatcher (TIWindow, 0x443F88) only shows RazePnl in the per-class handlers
(city/production/mine/node/farm/tower/altar) and - since the Reflecting Pool raze UI patch - after the generic
handler on the OWNED TPlayerStructure path (0x444111 -> cave 0x46E380).  Unowned TStructures (the Sanctuary is one)
reach the same generic handler 0x443F44 from 0x4441F8 and never get the button.
Fix: the generic handler's tail (0x443F7F `mov ecx,[eax]; call [ecx+8]; pop esi; pop ebx; ret`) -> cave .xibn
0x611900: replays it, then RazePnl.SetVisible(structure.GetRazeable) (esi = structure, ebx = window, RazePnl =
[window+0x10C], SetVisible = [vmt+0x6C]).  Every structure handled generically (owned or not) now shows the raze
button iff GetRazeable; RazeBtnClick (CanRaze -> Raze) is generic.  The pool's cave keeps working (same result).
Backup .bak_sanctrazeui.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402   (state, write_bytes, busy)
import sky_clouds_overlay_asm as OV  # noqa: E402  (asm)

EXE, BASE = game_file("AoWx.exe"), 0x400000
SITE, ORIG = 0x443F7F, bytes.fromhex("8b08ff51085e5bc3")
CAVE, CAVE_END, MAGIC = 0x611900, 0x611940, b"SRZ1"


def patches():
    code = OV.asm("""
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 8]
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x154]
        mov dl, al
        mov eax, dword ptr [ebx + 0x10c]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x6c]
        pop esi
        pop ebx
        ret
    """, CAVE + 4)
    z = MAGIC + code
    assert len(z) <= CAVE_END - CAVE
    site = b"\xe9" + struct.pack("<i", CAVE + 4 - (SITE + 5)) + b"\x90" * 3
    return [(SITE, ORIG, site), (CAVE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read(); pe = pefile.PE(data=d)
    P = patches()
    st, bad = SP.state(d, pe, BASE, P)
    print("AoWx.exe %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    bk = bak_path(EXE, ".bak_sanctrazeui")
    if not revert and not os.path.exists(bk):
        shutil.copy2(EXE, bk)
    SP.write_bytes(EXE, BASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
