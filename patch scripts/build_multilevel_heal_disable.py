#!/usr/bin/env python3
r"""Surgically DISABLE the multilevel-ability-heal hook (build_multilevel_ability_heal.py)
by restoring TAbilityOwner.GetAbilityData's original 7 bytes.

⚠ DO NOT use build_multilevel_ability_heal.py --revert: that restores the whole
DLL from AoWEPACK.dll.bak_mlheal, which predates the scenario HP top-up, Summon
Silver Dragon, Void Step and the 2026-08-12 wall fixes. This script touches only
the 7-byte entry, so every later patch survives. It also removes the
GetAbilityData probe hook, since both live at the same entry.

WHY DISABLE IT (2026-08-12)
    The heal cave re-implements GetAbilityData and, on a MISS, does two things
    vanilla never does:

      1. `mov ecx,[eax]; call [ecx+0x4c]`  - a VIRTUAL call on the OWNER.
         Vanilla only reads [owner+0x10] and walks the node chain; it never
         dereferences the owner's VMT and simply returns nil on a miss. So an
         owner that vanilla tolerated now crashes:
             AV @0x55810CB6, read of 0x0C0A004C (bogus VMT 0x0C0A0000)
      2. On the heal branch it WRITES:
             mov ecx,[edi+0x10] / mov [eax+8],ecx / mov [edi+0x10],eax
         i.e. it stores a node pointer into [owner+0x10] and adopts whatever
         junk was already there as the node's `next`. Given a wrong-class
         "owner" this CORRUPTS that object and builds a chain containing
         garbage - which is exactly the later
             AV @0x55810C9B, read of 0xFFFFFFFF   (walking a -1 `next`)
         and plausibly
             AV @0x55810C93, read of 0x9EED7398   (wild owner)

    The patch was applied 2026-08-10 and shipped ONLY in 1.37.402 (the 401->402
    diff lists GetAbilityData as a change), yet the user's crash predates 401 -
    so it never fixed the reported bug. It was written for the old Keeper2
    "TurnEventTE" freeze, which the wall/GetRank bug fixed on 2026-08-12
    (build_wall_damage_rank_crash_fix.py) explains far better.

    Net: an unvalidated patch that adds crash surface and can corrupt memory,
    aimed at a problem now believed to be misdiagnosed. Disable, retest, and
    only revisit if a genuine bit-only multilevel ability failure reappears.

    Backup: AoWEPACK.dll.bak_mlhealoff. Dry-run default; --apply / --revert
    (--revert re-installs the jmp to the heal cave, NOT the probe).
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_mlhealoff"

VA2FILE = 0x55700C00
SITE = 0x5574F1C4
HEAL_CAVE = 0x55810C80
# push ebx; push esi; mov esi,edx; mov ebx,[eax+0x10]
ORIGINAL = bytes.fromhex("53568bf28b5810")


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, 'rb').read())
    off = SITE - VA2FILE
    cur = bytes(d[off:off + 7])

    if revert:
        d[off:off + 7] = (bytes([0xE9]) +
                          (HEAL_CAVE - (SITE + 5)).to_bytes(4, 'little', signed=True) +
                          b'\x90\x90')
        open(DLL, 'wb').write(d)
        print("re-installed the heal-cave hook at 0x%X" % SITE)
        return 0

    if cur == ORIGINAL:
        print("already disabled - GetAbilityData is stock.")
        return 0
    assert cur[0] == 0xE9, "unexpected bytes at GetAbilityData: " + cur.hex()
    tgt = SITE + 5 + struct.unpack_from('<i', cur, 1)[0]
    print("current hook: 0x%X -> 0x%X" % (SITE, tgt))
    d[off:off + 7] = ORIGINAL
    print("restoring stock: " + ORIGINAL.hex())
    if not apply:
        print("Dry run OK - rerun with --apply.")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written - GetAbilityData is now vanilla; heal + probe caves are orphaned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
