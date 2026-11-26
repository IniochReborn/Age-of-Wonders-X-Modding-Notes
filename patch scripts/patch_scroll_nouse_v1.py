#!/usr/bin/env python3
r"""
Scrolls can no longer be "Used" (AoWEPACK.dll, 2026-10-30).  Part of the scroll-spells rework.

Vanilla TItem.CanUse 0x557940AC: itScroll with [item+0x38] != 0 and the spell not yet researched -> True, and
TItem.ExecuteUse 0x55793F68 then teaches the spell to the hero's WHOLE player and destroys the scroll.  The new
design (patch_scroll_spells_store_v1 + patch_exe_scroll_spells_v1) makes a held scroll grant its spells to the
holder only, so the Use path is closed: @0x557940DF `je 0x55794160` (74 7F) -> `jmp` (EB 7F) - every scroll takes
the vanilla "cannot use" branch.  1 byte, no reloc.  Dry-run default; --apply / --revert.
Backup AoWEPACK.dll.bak_scrollnouse.
"""
import os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE = 0x55700000
SITE, OLD, NEW = 0x557940DF, b"\x74\x7f", b"\xeb\x7f"


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d, fast_load=True)
    o = pe.get_offset_from_rva(SITE - BASE)
    assert d[o - 4:o] == bytes.fromhex("837e3800"), d[o - 4:o].hex()
    cur = d[o:o + 2]
    st = "vanilla" if cur == OLD else "ours" if cur == NEW else "OTHER"
    print("CanUse scroll gate %#x %s -> %s" % (SITE, cur.hex(), st))
    if st == "OTHER":
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_scrollnouse")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        f.seek(o); f.write(OLD if revert else NEW)
    assert open(DLL, "rb").read()[o:o + 2] == (OLD if revert else NEW)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
