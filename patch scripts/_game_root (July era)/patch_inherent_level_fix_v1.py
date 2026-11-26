#!/usr/bin/env python3
"""
Follow-up fix for the Leadership disable-bug patch (AoWEPACK.dll, 2026-07-20).

BUG FOUND IN-GAME: buying Turn Undead V (or any TU level) at hero level-up
deducted the points but never applied the level. Root cause: our leadership
fix (patch_leadership5_v1.py, cave_abinherent) makes UpdateDefaultAbilities
compare INHERENT levels via ability VMT+0x94 GetInherentLevel. That is right
for TMultiLevelAbility-based abilities (they override +0x94), but TWO leveled
abilities implement their own level machinery and inherit the BASE
TAbility.GetInherentLevel (returns 0): the purchase template compares 0 vs 0
-> the level record is never copied to the hero.

Full sweep of all 70 ability VMTs found exactly two such classes:
  - TTurnUndeadAbility  VMT 0x5571FDFC: own GetLevel @0x5576AE8C
  - TDispelMagicAbility VMT 0x55721D78: own GetLevel @0x5576CEFC

FIX: repoint each VMT's +0x94 slot to that class's own GetLevel. Semantically
correct: neither ability has aura-borrowed levels, so inherent == own level.
Also fixes unit medal rank-ups whose templates carry TU/DM levels. VMT slots
carry relocs -> value swap is rebase-safe.

Dry-run default; --apply. Backup: AoWEPACK.dll.bak_inherent_fix
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_inherent_fix"
FILE_DELTA = 0x55700C00
BASE_INH = 0x5574E954

patches = [
    (0x5571FDFC + 0x94, struct.pack("<I", BASE_INH), struct.pack("<I", 0x5576AE8C),
     "TTurnUndeadAbility VMT+0x94: base GetInherentLevel -> own GetLevel"),
    (0x55721D78 + 0x94, struct.pack("<I", BASE_INH), struct.pack("<I", 0x5576CEFC),
     "TDispelMagicAbility VMT+0x94: base GetInherentLevel -> own GetLevel"),
]

data = bytearray(open(DLL, 'rb').read())
ok = True; applied = 0
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    cur = bytes(data[off:off+len(orig)])
    if cur == new: applied += 1
    elif cur != orig:
        print(f"MISMATCH @0x{va:X} ({desc}):\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok = False
if applied == len(patches):
    print("ALL ALREADY PATCHED"); sys.exit(0)
if not ok:
    print("Aborting."); sys.exit(1)
if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
