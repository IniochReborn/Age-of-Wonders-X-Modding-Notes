#!/usr/bin/env python3
r"""
AoWDevX: Spells tab re-layout so Combat Info is visible (2026-10-31).  Same technique as
patch_devx_ability_layout_v1 (run after it; both edit TMAINFORM in place).

User: "for window resizing, we need to do the same for spells (cut off combat info)".  TMAINFORM > Settings >
PageControl3 > Spells > Panel9 stacked Description 8/157, Settings 176/185, SFX 368/65, GFX 440/65 and
'Combat Info:' (SpellInfoGroup) LAST at 512..713.
New column (Top / Height): Description 4/120 (memo 64, Edit 88) | Combat Info 128/180 (memo 152) |
Settings 312/185 | SFX + GFX side by side 500/56 (each 104 wide, buttons 20/22) -> ends at y 556.
Backup .bak_spelllayout.  Dry-run default; --apply; --revert.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_devx_ability_layout_v1 as AL  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

LAYOUT = {
    "GroupBox2": {"Top": (8, 4), "Height": (157, 120)},
    "SpellDescription": {"Height": (89, 64)},
    "EditSpellText": {"Top": (120, 88)},
    "SpellInfoGroup": {"Top": (512, 128), "Height": (201, 180)},
    "SpellInfoMemo": {"Height": (173, 152)},
    "GroupBox3": {"Top": (176, 312)},
    "GroupBox4": {"Top": (368, 500), "Width": (213, 104), "Height": (65, 56)},
    "EditSpellSFX": {"Left": (80, 20), "Top": (24, 22)},
    "GroupBox5": {"Top": (440, 500), "Left": (120, 229), "Width": (213, 104), "Height": (65, 56)},
    "EditSpellGFX": {"Left": (80, 20), "Top": (24, 22)},
}
PARENTS = {"GroupBox2": "Panel9", "SpellInfoGroup": "Panel9", "GroupBox3": "Panel9", "GroupBox4": "Panel9",
           "GroupBox5": "Panel9", "SpellDescription": "GroupBox2", "EditSpellText": "GroupBox2",
           "SpellInfoMemo": "SpellInfoGroup", "EditSpellSFX": "GroupBox4", "EditSpellGFX": "GroupBox5"}


def main():
    AL.LAYOUT, AL.PARENTS = LAYOUT, PARENTS
    AL.SHEET = "Spells"
    bk = bak_path(AL.EXE, ".bak_spelllayout")
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if SP.busy():
            print("editor running - close it first"); return 1
        if os.path.exists(bk):
            shutil.copy2(bk, AL.EXE); print("restored", bk)
        return 0
    d = open(AL.EXE, "rb").read()
    out, info = AL.build(d)
    print("AoWDevX TMAINFORM Spells tab:", info)
    if out is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("editor running - close it first"); return 1
    if not os.path.exists(bk):
        shutil.copy2(AL.EXE, bk)
    with open(AL.EXE, "r+b") as f:
        f.write(out); f.truncate()
    assert open(AL.EXE, "rb").read() == out
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
