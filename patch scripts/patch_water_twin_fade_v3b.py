#!/usr/bin/env python3
r"""
Water twin fade v3b (2026-11-13) - layered on patch_water_twin_fade_v3.

User (editor screenshot): "crosslevel water transitions still bad" - sand shoreline between animated surface water
and cave water.  Reproduced live (test map Scenario\Custom\_wtest.hsm opened in AoWDevX + screen capture): the v3
fade wedges ARE drawn, but the sand comes back on top of them.  Cause: Ziggurat's gate 0x55850B10 in front of the
inherited HSE TLowerIsometricHexagon.ShowDynamic (import thunk 0x5579A178, draws the sand shore from the mask
[hex+0x14] + side bases [hex+0x19+dir]) skips that draw only when a masked side has base >= 0xA0 (Sky/Chasm);
our twin bases are 0x80 / 0x88 -> inherited shore drawn with ids 0x80+piece.
Fix: the gate's threshold 0xA0 -> 0x80 (imm8 at 0x55850B21).  Vanilla bases are 0 / 0x28 / 0x50, so only twin /
mixed sides are added; such a hexagon's other (real land) sides get their single shore pieces from the wc2 per-side
path, exactly as next to Sky.  The cloud overlay has its own >= 0xA0 test (unchanged).
Backup .bak_watertwin3b.  Dry-run default; --apply; --revert.  Revert before reverting v3.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

DLL = game_file("AoWEPACK.dll")
B = 0x55700C00
AT, CTX, OLD, NEW = 0x55850B21, bytes.fromhex("807c181a"), 0xA0, 0x80
TAG = ".bak_watertwin3b"


def main():
    d = bytearray(open(DLL, "rb").read())
    fo = AT - B
    assert bytes(d[fo - 4:fo]) == CTX and d[fo + 1] == 0x73, "gate not found (Ziggurat water gate 0x55850B10)"
    st = {OLD: "vanilla", NEW: "ours"}.get(d[fo], "OTHER")
    print("gate threshold @%#x: %s" % (AT, st))
    if "--apply" in sys.argv or "--revert" in sys.argv:
        assert not SP.busy(), "close the game / editor first"
        want = NEW if "--apply" in sys.argv else OLD
        assert st != "OTHER"
        if d[fo] == want:
            print("nothing to do"); return
        bk = bak_path(DLL, TAG)
        if not os.path.exists(bk):
            shutil.copy2(DLL, bk)
        with open(DLL, "r+b") as f:
            f.seek(fo); f.write(bytes([want]))
        print("written")


if __name__ == "__main__":
    main()
