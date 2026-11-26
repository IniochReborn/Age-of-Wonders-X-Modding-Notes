#!/usr/bin/env python3
r"""FIX: melee Hero-Slaying vs a combat WALL crashed combat (wrong-class +0x4C).

FOUND 2026-08-12 by the @IsClass caller probe (build_isclass_caller_probe.py)
on the Keeper2 turn-18 autosave (deterministic repro):

    Exception EAccessViolation in module AoWEPACK.dll at 001110A2
    ... Read of address D580E441

    0xD580E441 & 0x7FFFFFFF = 0x5580E441 = return address of the
    `call @IsClass` @0x5580E43C in the MELEE Hero-Slaying cave:

        5580E42F  mov  edx,[delta+0x55711FAC]  ; THero class (PIC)
        5580E435  mov  eax,[edi+0x4c]   ; ⚠ raw +0x4C on the TARGET object
        5580E438  test eax,eax          ;   nil-check only
        5580E43A  je   0x5580e45e
        5580E43C  call 0x557010C0       ; @IsClass(->THero) derefs the value
        5580E441  test al,al

    [obj+0x4C] is the underlying TUnit only for TCombatUnit; on the sibling
    TCombatWall it is a packed byte pair (type/HP), e.g. 0x1902 - non-nil, so
    it survives the nil check and @IsClass faults dereferencing it.
    EXACT twin of the ranged bug fixed by build_ranged_heroslay_wall_fix.py
    (cave 0x5580E500 / helper 0x55810F00). The 2026-08-12 combat-object audit
    wrongly CLEARED this cave because it "does IsClass" - but the IsClass
    *argument* is already the garbage.

★ TWO SITES — the melee Hero-Slaying insert exists in BOTH vanilla melee
    strike blocks, and both had the bug:
      SITE 1 @0x5580E435 (CalculateStrikes block @0x55767C5C; target in EDI;
        the one the probe caught on the turn-18 autosave)
      SITE 2 @0x5580E3D5 (CreateStrikeCA block @0x557666A1; target in ESI;
        found 2026-08-12 by a fresh scan after the user asked whether Monster
        Slaying had the same bug — Monster Slaying itself is SAFE, it is
        checked via the virtual GetAbilityEnabled which walls answer "no" to)
    The 2026-08-12 combat-object audit missed site 2's [esi+0x4c] entirely.

THE FIX (7 bytes in-place per site, no new cave)
    Replace  8B 4x 4C 85 C0 74 xx   mov eax,[tgt+0x4c]; test; je skip
    with     89 xx E8 <rel32>       mov eax,tgt; call helper_0x55810F00

    The existing helper (from the ranged fix) returns [obj+0x4C] only if the
    object IsClass TCombatUnit (runtime VMT via PIC delta), else 0, and
    preserves EDX (the THero class ref). A nil result then flows into the
    nil-SAFE @IsClass -> AL=0 -> the existing `je` skips the bonus,
    i.e. exactly the vanilla no-bonus path. Other live regs untouched; ECX is
    scratch (reloaded right after at both sites).

    Verified before writing (both sites): no .reloc entries and no branch
    targets inside the 7 displaced bytes.

Backup: AoWEPACK.dll.bak_meleeheroslay. Dry-run default; --apply / --revert.
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_meleeheroslay"

VA2FILE = 0x55700C00
HELPER = 0x55810F00                     # from build_ranged_heroslay_wall_fix.py


def mk(site, old_hex, movreg_hex):
    old = bytes.fromhex(old_hex)
    new = (bytes.fromhex(movreg_hex) +
           b"\xE8" + (HELPER - (site + 2 + 5)).to_bytes(4, "little", signed=True))
    assert len(new) == len(old) == 7
    return site, old, new

SITES = [
    # site 1: CalculateStrikes block cave; target in EDI
    mk(0x5580E435, "8b474c85c07422", "89f8"),   # mov eax,[edi+0x4c];test;je / mov eax,edi
    # site 2: CreateStrikeCA block cave; target in ESI
    mk(0x5580E3D5, "8b464c85c07423", "89f0"),   # mov eax,[esi+0x4c];test;je / mov eax,esi
]

# context asserts: the PIC THero load before, the @IsClass call after each
# site, and the helper's first bytes (so we refuse to run if its cave moved)
CTX = [
    (0x5580E42F, bytes.fromhex("8b92ac1f7155")),  # site1: mov edx,[edx+0x55711FAC]
    (0x5580E43C, bytes.fromhex("e87f2cefff")),    # site1: call 0x557010C0
    (0x5580E3CF, bytes.fromhex("8b92ac1f7155")),  # site2: mov edx,[edx+0x55711FAC]
    (0x5580E3DC, bytes.fromhex("e8df2cefff")),    # site2: call 0x557010C0
]
HELPER_SIG = bytes.fromhex("85c074255250")        # test eax,eax; je; push edx; push eax


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL)
            print("restored AoWEPACK.dll from", os.path.basename(BAK))
            return 0
        print("no backup found:", BAK)
        return 1

    d = bytearray(open(DLL, "rb").read())
    for va, sig in CTX:
        got = bytes(d[va - VA2FILE:va - VA2FILE + len(sig)])
        assert got == sig, "context mismatch @0x%X: %s" % (va, got.hex())
    hgot = bytes(d[HELPER - VA2FILE:HELPER - VA2FILE + len(HELPER_SIG)])
    assert hgot == HELPER_SIG, "helper @0x%X changed: %s" % (HELPER, hgot.hex())

    todo = 0
    for site, old, new in SITES:
        o = site - VA2FILE
        cur = bytes(d[o:o + 7])
        if cur == new:
            print("site 0x%X: already applied" % site)
            continue
        assert cur == old, "unexpected bytes @0x%X: %s" % (site, cur.hex())
        d[o:o + 7] = new
        todo += 1
        print("patched 7 B @0x%X -> call helper 0x%X" % (site, HELPER))
    if not todo:
        print("nothing to do.")
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert).")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(DLL, "wb").write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
