#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Crosswind (213) visual LCG gets a FIXED seed instead of the fx object's address (2026-10-24, MP OOS fix).

Bug (user, LAN 10/23 + 2-instance repro 10/24): cast Crosswind, move a unit right away -> OOS when the swirls end.
Live diff of both processes: every unit identical except the moved one - host walked it 7 hexes (32,25), the joiner
stopped it after 3 (29,22).  Waiting until both windows were still before moving -> no OOS.

Root cause: the cast step (TCAbRangedTE.Execute) only finishes when the map effect list is EMPTY (0x40CB23).  The
Crosswind wash (patch_tc_crosswind_fx_v1 tk cave) seeded its private LCG at tick 0 with `mov eax, esi` = the kind-0x25
fx object's ADDRESS (xor 0x2D1F7A3B) - different on every machine -> different cloud positions -> different v8 cull
ticks / particle paths -> each machine's effect list emptied at a different tick, so the step ended at a different
time.  The host accepted the move while the joiner was still inside the Crosswind step, and the joiner executed the
move differently (cut short).

Fix: @0x443D79 `mov eax, esi` (89 F0) -> `xor eax, eax` (31 C0): seed = 0x2D1F7A3B on every machine -> identical wash
and identical step length everywhere (the wash looks the same on every cast - visual only).  The source in
patch_tc_crosswind_fx_v1.py was changed the same way, so a rebuild keeps the fix.
Backup <game>\backup\AoWTCPCK.dll.bak_xwindseed.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_xwindseed"
V2F = 0x400C00
SITE = 0x443D79
CTX = bytes.fromhex("353b7a1f2d")          # xor eax, 0x2D1F7A3B (follows the site)
ORIG = bytes.fromhex("89f0")               # mov eax, esi
NEW = bytes.fromhex("31c0")                # xor eax, eax


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    f = SITE - V2F
    if d[f + 2:f + 2 + len(CTX)] != CTX: print("ABORT: context mismatch at %#x (Crosswind fx v8 expected)" % SITE); return 1
    live = d[f:f + 2]
    state = "vanilla" if live == ORIG else "ours" if live == NEW else "OTHER"
    print("site %#x: %s (%s)" % (SITE, state, live.hex()))
    if state == "OTHER": print("ABORT"); return 1
    want = ORIG if a.revert else NEW
    if live == want: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not a.apply and not a.revert: print("2 byte change. Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as fh:                 # in-place (house rule: "wb" is refused on the live DLLs)
        fh.seek(f); fh.write(want)
    assert open(a.dll, "rb").read()[f:f + 2] == want
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
