#!/usr/bin/env python3
r"""
AoWEPACK.dll: summoned units' dispel resistance = unit level x 2 + 1 per medal (2026-11-07, v2).

User: "for dispel magic summoned resistance, change it to (unit level X 2) + 1 for each medal".
v1 (patch_summon_dispel_res_v1) made PassiveAb.TSummonedAbility.GetDefaultDispelResistance @0x557BB1E4 return
level x 2 in place (vanilla: level + 7).  v2 replaces that tail (0x557BB202: movsx/add/pop ebx/ret, 8 bytes) with a
jmp to cave 'SDR2' @0x558E1400:
    movsx eax, al ; add eax, eax ; push eax ; mov eax, ebx ; call TUnit.GetRank 0x5578294C ; movzx edx, al ;
    pop eax ; add eax, edx ; pop ebx ; ret
ebx = the unit (already IsInstance-checked TUnit by the vanilla head).  GetRank = earned medals from XP
([unit+0x3C] >= 10 silver = 1, >= 20 gold = 2), the same rank that drives the medal icon and rank stat bonuses.
Level 1..4 -> 2..8, +0..2 for medals.  Relative jumps only (PIC), no relocations touched.
Works from vanilla or from v1 state; --revert restores VANILLA (level + 7) and clears the cave.
Backup <game>\backup\AoWEPACK.dll.bak_sumdispel2.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_sumdispel2"
V2F = 0x55700C00
SITE = 0x557BB202
CTX = bytes.fromhex("ff92a0000000")                 # call [edx+0xA0] (GetUnitLevel) @0x557BB1FC
VANILLA = bytes.fromhex("0fbec083c0075bc3")
V1 = bytes.fromhex("0fbec001c0905bc3")
CAVE, CAVE_END = 0x558E1400, 0x558E1440
GETRANK = 0x5578294C


def rel(at, to):
    return struct.pack("<i", to - (at + 5))


def build():
    c = bytearray(bytes.fromhex("0fbec0" "01c0" "50" "89d8"))
    c += b"\xe8" + rel(CAVE + len(c), GETRANK)
    c += bytes.fromhex("0fb6d0" "58" "01d0" "5b" "c3")
    assert len(c) <= CAVE_END - CAVE
    site = b"\xe9" + rel(SITE, CAVE) + b"\x90\x90\x90"
    return site, bytes(c)


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
    f, fc = SITE - V2F, CAVE - V2F
    if d[f - len(CTX):f] != CTX:
        print("ABORT: context mismatch at %#x" % SITE); return 1
    site, cave = build()
    live, lcave = bytes(d[f:f + 8]), bytes(d[fc:fc + CAVE_END - CAVE])
    zero = bytes(CAVE_END - CAVE)
    if live == site and lcave[:len(cave)] == cave:
        state = "ours"
    elif live in (VANILLA, V1) and lcave == zero:
        state = "vanilla" if live == VANILLA else "v1"
    else:
        state = "OTHER"
    print("site %#x: %s (%s)" % (SITE, state, live.hex()))
    if state == "OTHER":
        print("ABORT"); return 1
    if a.revert:
        if state == "vanilla":
            print("already vanilla"); return 0
        d[f:f + 8] = VANILLA; d[fc:fc + len(zero)] = zero
    else:
        if state == "ours":
            print("already applied"); return 0
        d[f:f + 8] = site; d[fc:fc + len(cave)] = cave
    if not a.apply and not a.revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as fh:
        fh.seek(f); fh.write(d[f:f + 8]); fh.seek(fc); fh.write(d[fc:fc + len(zero)])
    assert open(a.dll, "rb").read() == bytes(d)
    print("reverted to vanilla" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
