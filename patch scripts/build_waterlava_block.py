#!/usr/bin/env python3
r"""AoWx -- Water Elementals cannot cross lava (despite fire immunity).

USER SPEC 2026-08-30: fire immunity grants lava crossing (the fire-immunity
ability contributes move-type bit 0x40 "Fire" -- TImmunityAbility.GetMoveTypes
@0x557BC054 returns [0x557BC068]=0x40 when the immunity mask has bit 0). That
makes sense for fire units but not the (fire-immune) Water Elemental. Block it
for unit resource-index 0xE3 specifically, unless Wind Walking (ability 0xA5,
set in TWindWalkingEnchantment.Create @0x557BBB0B) is enabled.

MECHANISM: wrap the unit-level GetMoveTypes -- VMT slot +0xE8, implementation
TAbstractUnit.GetMoveTypes @0x5577FFD0 shared by TUnit (VMT 0x55710CAC) and
TAdjustableUnit (VMT 0x55712A54). Both slots are repointed to a cave that
calls the original, then for index 0xE3 without ability 0xA5 clears bit 0x40.
Every consumer follows automatically (CreateMovePointTable @0x5577FDC4 unit
tables, army MAX combine, the movement predictor, pathing UI) -- no
inconsistency between shown and real movement, MP-deterministic.
Transported Water Elementals are unaffected (cargo does not contribute to the
army movement table), and Wind Walking's own lava allowance is applied
post-table in CreateMovePointTable, independent of bit 0x40 -- the 0xA5 check
in the cave is belt and braces per the user's explicit exception.

VMT slots carry .reloc entries -- kept valid (the new value is an in-image
VA, rebased along with everything else). Cave is register-relative + rel32.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_waterlava"

D = 0x55700C00
ORIG_IMPL = 0x5577FFD0
SLOTS = [("TUnit", 0x55710CAC + 0xE8), ("TAdjustableUnit", 0x55712A54 + 0xE8)]
WATER_EL = 0xE3
WINDWALK = 0xA5
CAVE = 0x55814180
CAVE_HI = 0x558141C0


def make_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        push ebx
        mov  ebx, eax
        call 0x{ORIG_IMPL:X}
        push eax
        mov  edx, [ebx+0x40]
        test edx, edx
        jz   _keep
        mov  eax, [edx+4]
        mov  ecx, [eax]
        call dword ptr [ecx+0x84]
        cmp  eax, {WATER_EL}
        jne  _keep
        mov  edx, {WINDWALK}
        mov  eax, ebx
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz  _keep
        pop  eax
        and  al, 0xBF
        pop  ebx
        ret
    _keep:
        pop  eax
        pop  ebx
        ret
    """
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)
    return bytes(code)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_cave()
    assert CAVE + len(cave) <= CAVE_HI, len(cave)
    edits = [(CAVE, bytes(len(cave)), cave, "cave_waterlava")]
    for nm, slot in SLOTS:
        edits.append((slot, struct.pack("<I", ORIG_IMPL),
                      struct.pack("<I", CAVE), "%s VMT+0xE8 repoint" % nm))
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-28s @0x%08X  %s" % (nm, va, st))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED - test: Water Elemental cannot enter/path across lava; "
          "CAN when carried by a transport or under Wind Walking; Fire "
          "Elemental/Sprite still cross lava; other fire-immune units "
          "unchanged; movement preview matches actual movement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
