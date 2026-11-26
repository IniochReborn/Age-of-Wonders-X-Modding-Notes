#!/usr/bin/env python3
r"""
City battle map: only count the hexes of the city itself (2026-11-13).

User: "starting combat causes a bunch of errors" on a map another player made.  VEH log (attached to the live game):
EAccessViolation at AoWTCPCK 0x41B742 (write [nil+0xE4]) called from 0x424FB7 in the combat set-up 0x4245EC: the
tactical scene global [0x46C064] is nil because the battle map file did not load.
Cause: for a TCity the file name is TCMaps\0<digits>c000.HSM, one digit per neighbour direction 1..6 whose hexagon
holds a TCity (loop 0x424A02..0x424A82, FindObject(hex, TCity) = call 0x401DB4 at 0x424A42).  ANY city counts, so a
city touching another city (that map packs cities side by side) gets a digit combination no file exists for
(only 0xxx / 02xx / 05xx / 012x / 023x / 034x / 056x / 0126 / 0345).
Fix: the call goes through a cave that returns nil unless the city found is the city being fought over ([ebp-0x44]).
Cave 0x454500 (13 bytes, position independent).  Backup .bak_citytcmap1.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

DLL = game_file("AoWTCPCK.dll")
B = 0x400C00
SITE, CAVE, FIND = 0x424A42, 0x454500, 0x401DB4
TAG = ".bak_citytcmap1"


def rel(frm, to):
    return struct.pack("<i", to - (frm + 5))


OLD_SITE = b"\xE8" + rel(SITE, FIND)
NEW_SITE = b"\xE8" + rel(SITE, CAVE)
CODE = (b"\xE8" + rel(CAVE, FIND)      # call FindObject
        + b"\x3B\x45\xBC"              # cmp eax,[ebp-0x44]   (the city of this battle)
        + b"\x74\x02"                  # je +2
        + b"\x31\xC0"                  # xor eax,eax
        + b"\xC3")                     # ret
PAD = 16


def main():
    d = bytearray(open(DLL, "rb").read())
    s, c = SITE - B, CAVE - B
    assert bytes(d[s + 5:s + 9]) == b"\x85\xC0\x74\x30", "site context changed"
    site = bytes(d[s:s + 5]); cave = bytes(d[c:c + PAD])
    if site == OLD_SITE and cave == bytes(PAD):
        st = "vanilla"
    elif site == NEW_SITE and cave == CODE + bytes(PAD - len(CODE)):
        st = "ours"
    else:
        st = "OTHER"
    print("city battle-map neighbour test @%#x, cave %#x: %s" % (SITE, CAVE, st))
    if "--apply" in sys.argv or "--revert" in sys.argv:
        assert st != "OTHER", "unexpected bytes - not touching"
        assert not SP.busy(), "close the game / editor first"
        ap = "--apply" in sys.argv
        if (st == "ours") == ap:
            print("nothing to do"); return
        bk = bak_path(DLL, TAG)
        if not os.path.exists(bk):
            shutil.copy2(DLL, bk)
        with open(DLL, "r+b") as f:
            f.seek(c); f.write(CODE + bytes(PAD - len(CODE)) if ap else bytes(PAD))
            f.seek(s); f.write(NEW_SITE if ap else OLD_SITE)
        print("written")


if __name__ == "__main__":
    main()
