#!/usr/bin/env python3
r"""
Title screen background: tile the scrolling panorama across the whole width (2026-10-31).

User (screenshot at ~1920+ wide: a smeared strip at the right edge): "at the intro screen, on certain screen
resolutions the background image loop-point gets all weird. its like it stretches then goes back to normal".
TTitleScene (VMT 0x4192F4) WindowDrawSurfaceEx 0x41A030 -> background helper 0x419C84: x0 = -((ticks + 0x1EA)
mod W) with W = Int\Scenes\title.ilb image 0 width (ScrollBackg5, 1514 px), then exactly TWO draws, at x0 and
x0 + W (0x419D45..0x419D88).  Whenever the surface is wider than 2W + x0 (at 1920 px: the last ~27 % of every
loop) the right edge is never repainted and shows stale pixels.
Fix (in place, 67 bytes, rel32 calls only, no relocs): a loop that draws at x0, x0+W, x0+2W, ... while x is left
of the surface width [esi+0x8C] (W <= 0 guard).  Loop x kept in [ebp-0x10] (first written by the function at
0x419E4B, after this block).
Backup .bak_titlebg.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

EXE, BASE = game_file("AoWx.exe"), 0x400000
SITE, END = 0x419D45, 0x419D88
TAG = ".bak_titlebg"


def patches(d, pe):
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    orig = d[off(SITE):off(END)]
    assert orig[:4] == bytes.fromhex("8b45fc50") and orig[-6:] == bytes.fromhex("8b18ff938400")[:0] + orig[-6:]
    code = OV.asm("""
    tl_loop:
        mov dword ptr [ebp - 0x10], ebx
        mov eax, dword ptr [ebp - 0x4]
        push eax
        xor edx, edx
        mov eax, dword ptr [esi + 0x44]
        call 0x401acc
        mov ecx, dword ptr [ebp - 0xc]
        mov edx, dword ptr [ebp - 0x10]
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0x84]
        xor edx, edx
        mov eax, dword ptr [esi + 0x44]
        call 0x401acc
        mov edx, dword ptr [eax + 0x20]
        test edx, edx
        jle tl_done
        mov ebx, dword ptr [ebp - 0x10]
        add ebx, edx
        cmp ebx, dword ptr [esi + 0x8c]
        jl tl_loop
    tl_done:
    """, SITE)
    assert len(code) <= END - SITE, len(code)
    new = code + b"\x90" * (END - SITE - len(code))
    return [(SITE, bytes(orig), new)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(EXE, "rb").read(); pe = pefile.PE(data=d)
    bk = bak_path(EXE, TAG)
    if revert:
        if os.path.exists(bk):
            o = open(bk, "rb").read()
            P = patches(o, pefile.PE(data=o))
            SP.write_bytes(EXE, BASE, P, True); print("reverted")
        return 0
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    if os.path.exists(bk):
        o = open(bk, "rb").read(); P = patches(o, pefile.PE(data=o))
    else:
        P = patches(d, pe)
    st, bad = SP.state(d, pe, BASE, P)
    print("AoWx.exe %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad:
        print("ABORT"); return 1
    if st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bk):
        shutil.copy2(EXE, bk)
    SP.write_bytes(EXE, BASE, P, False)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
