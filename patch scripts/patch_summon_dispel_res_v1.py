#!/usr/bin/env python3
r"""
AoWEPACK.dll: summoned units' dispel resistance = unit level x 2 (2026-11-07).

User: "currently, summoned units have 7 resistance to dispel magic (which unsummons them). i want to instead make it
(unit level X 2)".

PassiveAb.TSummonedAbility.GetDefaultDispelResistance @0x557BB1E4 (also reached through
SummonSpells.TSummonSpell.GetDispelResistance @0x557E4460):
    IsInstance(unit, TUnit) ? (movsx [unit VMT+0xA0] = TUnit.GetUnitLevel = [[unit+0x40]+0x2F] base tier) + 7 : 0
so vanilla is 7 + level (8..11 for levels 1..4), not a flat 7.  The value is the enchantment rating fed to
TEnchantment.DispelChance @0x5577C1A0: chance% = clamp(dispelValue - 10 x rating + 50, 10, 90).
Patch: `add eax, 7` (83 C0 07) @0x557BB205 -> `add eax, eax ; nop` (01 C0 90) = level x 2 (2..8).
Same length, no relocations in the range, only copy of this code in AoWEPACK / TCPCK / exe.
Backup <game>\backup\AoWEPACK.dll.bak_sumdispel.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_sumdispel"
CODE_V2F = 0x55700C00
SITE = 0x557BB202                                   # movsx eax, al ; add eax, 7
CTX = bytes.fromhex("ff92a0000000")                 # call [edx+0xA0] (GetUnitLevel) @0x557BB1FC
ORIG = bytes.fromhex("0fbec083c007")
NEW = bytes.fromhex("0fbec001c090")                 # movsx eax, al ; add eax, eax ; nop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    if a.apply or a.revert:
        import patch_sky_polish_v1 as SP
        if SP.busy():
            print("game/editor running - close it first"); return 1
    d = bytearray(open(a.dll, "rb").read())
    f = SITE - CODE_V2F
    if d[f - len(CTX):f] != CTX:
        print("ABORT: context mismatch at %#x" % SITE); return 1
    live = bytes(d[f:f + len(ORIG)])
    state = "vanilla" if live == ORIG else "ours" if live == NEW else "OTHER"
    print("site %#x: %s (%s)" % (SITE, state, live.hex()))
    if state == "OTHER":
        print("ABORT"); return 1
    want = ORIG if a.revert else NEW
    if live == want:
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    d[f:f + len(want)] = want
    if not a.apply and not a.revert:
        print("3 byte change. Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as fh:
        fh.seek(f); fh.write(want)
    assert open(a.dll, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
