#!/usr/bin/env python3
r"""
Recall Spirits / Animate Dead: the raised unit's type roll used RDTSC (2026-11-14).

Both spawn caves (Recall Spirit 0x5580D98D, Animate Dead 0x5580CE0D..) pick the unit type from a per-unit-class table
plus a d100 that was `rdtsc / xor edx,edx / mov ecx,100 / div ecx / mov ecx,edx` - the CPU timestamp, different on
every machine -> in multiplayer each machine could raise a different unit on the same corpse (report 11/14: Recall
Spirits in MP raised 4 of 6 puppets, "Error - TCAI ..." dialogs on the rest; also an Out-of-Sync source).
Fix: the same 13 bytes become `mov eax,100 / call System.@RandInt (thunk 0x55701080) / mov ecx,eax / nop` - the bare
combat generator HitRole uses (same RandSeed stream on every machine as long as the draw count matches, which it does:
the combat action executes once per machine).  eax is restored by the `pop eax` that follows, edx is rewritten later.
Dry-run default; --apply / --revert.  Backup backup\AoWEPACK.dll.bak_raiserng.
"""
import os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, D = game_file("AoWEPACK.dll"), 0x55700C00
SITES = (0x5580D99B, 0x5580CE26)
OLD = bytes.fromhex("0f3131d2b964000000f7f189d1")
RANDINT = 0x55701080


def new(va):
    return b"\xB8\x64\x00\x00\x00" + b"\xE8" + struct.pack("<i", RANDINT - (va + 10)) + b"\x8B\xC8\x90"


def main():
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    b = bytearray(open(EP, "rb").read())
    assert bytes(b[RANDINT - D:RANDINT - D + 6]) == bytes.fromhex("ff25dcb68f55"), "RandInt thunk moved"
    st = []
    for va in SITES:
        cur = bytes(b[va - D:va - D + 13])
        st.append("old" if cur == OLD else "new" if cur == new(va) else "?")
    print("sites:", dict(zip(map(hex, SITES), st)))
    if "?" in st:
        print("ABORT: unexpected bytes"); return 1
    if revert:
        for va in SITES:
            b[va - D:va - D + 13] = OLD
        open(EP, "wb").write(b); print("reverted"); return 0
    if all(s == "new" for s in st):
        print("ALREADY PATCHED"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply"); return 0
    bk = bak_path(EP, ".bak_raiserng")
    if not os.path.exists(bk):
        shutil.copy2(EP, bk); print("backup ->", bk)
    for va in SITES:
        b[va - D:va - D + 13] = new(va)
    open(EP, "wb").write(b); print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
