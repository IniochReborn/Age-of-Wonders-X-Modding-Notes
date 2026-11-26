#!/usr/bin/env python3
r"""AoWx -- editor: surface tunnels preview as NORMAL tunnels, not water ones.

USER REPORT 2026-08-31: in the editor's structure-placement side panel the
preview for SURFACE tunnels shows the water-tunnel art, while the
UNDERGROUND ones preview as normal tunnels. Wanted: normal-tunnel art for
both. Water tunnels must keep WORKING (this is display only).

RE (this session)
-----------------
A tunnel is `Cave.TCave` (VMT 0x557B3018, resource TCaveResource 0x557B326C).
Byte **[cave+0x30]** is the entrance SIDE: TCave.Create sets it to 1, and it
is streamed as tag 6 by TCave.ReadWrite. 1 = the upper/surface mouth,
0 = the paired mouth on the level below -- proven by TCave.PlaceHX, which
only creates the partner (level+1) when [+0x30]==1, and by TCave.CanPlace,
which only demands "a level exists below" when [+0x30]!=0.

The editor palette preview is drawn by **TStructure.ShowBorderImageDC**
@0x5575FAB4 -- it has NO caller inside AoWEPACK and AoWDevX.exe imports it
(verified), so the editor is the caller. It reads the structure's border
images through the virtuals [vmt+0x138/0x13C/0x140] = Get{Top,Middle,Bottom}
BorderImage, which TCave overrides at 0x557B3538 / 0x557B3584 / 0x557B35D0.
Each override is the same shape:

    cmp byte ptr [cave+0x30], 0
    jne  <base TStructure implementation>     ; SURFACE side -> tags 0x1E/1F/20
    ...  look up tag 0x21 / 0x22 / 0x23 ...   ; UNDERGROUND side -> cave art

and the two tag sets resolve to different pictures in Release.hss: the
0x1E-0x20 set points into **BORDER.ILB** while the 0x21-0x23 set points into
**STR_CAVE.ILB images 5, 5, 6** (both tunnel records in Release.hss are
identical -- parsed 2026-08-31 at file offsets 0xC1CAF and 0xC4AEF). The
underground side therefore renders the plain cave art the user wants, and
the surface side renders the BORDER.ILB variant they see as the water
tunnel.

THE FIX: neutralise that one branch in all three getters (`jne` -> two NOPs)
so BOTH entrance sides take the STR_CAVE tag path. Three 2-byte edits, no
cave, no reloc concerns (verified reloc-free), fully reversible.

SCOPE / SAFETY
  * Display only. Placement rules (TCave.CanPlace), the paired-entrance
    logic (PlaceHX), movement and entering (CanEnter/Enter/EnterEx) are all
    untouched, so water tunnels keep working exactly as before.
  * Affects only TCave (no descendants); every other structure keeps its
    own border art.
  * Also changes the map placement-border preview to the same normal-tunnel
    art, which matches the intent ("preview should be a normal tunnel").

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_tunnelpreview"

D = 0x55700C00
ORIG = bytes.fromhex("7536")        # jne <base impl>
NEW = bytes.fromhex("9090")         # fall through to the cave-art path
SITES = [
    (0x557B3540, "TCave.GetTopBorderImage"),
    (0x557B358C, "TCave.GetMiddleBorderImage"),
    (0x557B35D8, "TCave.GetBottomBorderImage"),
]
# the `cmp byte ptr [ebx+0x30],0` immediately before each branch -- proves we
# are at the right instruction before writing
GUARD = bytes.fromhex("807b3000")


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    want = ORIG if revert else NEW

    states = []
    for va, nm in SITES:
        assert bytes(d[va - 4 - D:va - D]) == GUARD, \
            "%s: guard bytes missing at %#x" % (nm, va - 4)
        cur = bytes(d[va - D:va - D + 2])
        st = "original" if cur == ORIG else "applied" if cur == NEW else "FOREIGN"
        states.append(st)
        print("  %-28s @0x%08X  %s" % (nm, va, st))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if all(bytes(d[va - D:va - D + 2]) == want for va, _ in SITES):
        print("already in the requested state")
        return 0
    if not (apply or revert):
        print("dry run (--apply / --revert)")
        return 0
    if apply and not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("  backed up")
    for va, _ in SITES:
        d[va - D:va - D + 2] = want
    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe / AoWx.exe and retry")
        return 1
    print("reverted" if revert else
          "APPLIED - test: in the editor's structure palette, SURFACE tunnels "
          "now preview as normal tunnels (same art as the underground ones); "
          "placing tunnels still works on land and water; existing maps and "
          "the in-game look of placed tunnels are unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
