#!/usr/bin/env python3
r"""
AI heroes pick up ALL scroll items, not just one (AoWEPACK.dll, 2026-10-30).

The AI item-loot backpack pass (patch_ai_itemloot_use_v1: pickup cave 0x5581C220, up to 8 places per firing into
backpack slots 6..13) and the "would this hero take it" targeting cave (cave_target 0x55814D40) only accepted Use
items (type 6); scrolls (type 5, now useful: they grant spells while held) fell through to the equip pass (no slot
-> never taken; the one scroll the user saw came from the engine's own single AutoPlaceItem path).
Both tests `cmp type,6 / jne` -> `cmp type,5 / jb` (types 5 and 6 -> backpack; 0..4 -> equip; no type > 6):
  0x5581C2B0  80 78 34 06 75 31  ->  80 78 34 05 72 31       (pickup use pass)
  0x55814E43  83 7C 24 18 06 75 23 -> 83 7C 24 18 05 72 23   (targeting)
Dry-run default; --apply / --revert.  Backup AoWEPACK.dll.bak_aipickscroll.
"""
import os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
SITES = [(0x5581C2B0, bytes.fromhex("807834067531"), bytes.fromhex("807834057231")),
         (0x55814E43, bytes.fromhex("837c2418067523"), bytes.fromhex("837c2418057223"))]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d, fast_load=True)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    sts = []
    for s, o, n in SITES:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
        print("%#x %s %s" % (s, c.hex(), sts[-1]))
    if "OTHER" in sts or len(set(sts)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_aipickscroll")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        for s, o, n in SITES:
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in SITES)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
