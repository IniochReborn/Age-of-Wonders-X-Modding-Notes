#!/usr/bin/env python3
r"""AoWx -- fix the VANILLA "Blt Error" when an HP bar is drawn from a
NEGATIVE hit-point value (in practice: a wall crushed past 0 by Wall
Crushing).

ADOPTED 2026-08-31 from BXL/Ziggurat's build_hpbar_clamp.py (his RE kept):
AoWE.HitPointsToHitPcnt @0x5575A804 converts hp->0..100% with a SIGNED
divide and clamps the TOP only; a negative hp byte (wall byte [wall+0x4D],
driven below 0 by Wall Crushing overkill) yields a NEGATIVE percentage,
which ShowHitPcnt @0x5575A830 turns into an inverted clip rectangle -> the
blitter rejects it -> aowInt raises "Blt Error" (surfaced as the
"Error - FCWin" dialog) and the bar stops repainting. Damage is applied
fine; the fault is display-only.

FIX: displace the 12-byte tail @0x5575A824 (cmp/jle/mov 100/pop/ret) to a
cave adding the missing LOWER clamp (negative -> 0 = empty bar; a thing at
or below 0 HP is destroyed). Register-only, rel8 branches: naturally PIC.
Inbound jumps (0x5575A819/0x5575A81D) land on the FIRST displaced byte
(= our jmp) -- safe; nothing jumps into the middle. Both callers
(TCombatWall.Show, TAbstractUnit.ShowEx) fixed alike. Site + cave
reloc-scanned clean on our DLL 2026-08-31.

Cave @0x55815100..0x55815120 (next free after this = 0x55815120).

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_hpbarclamp"

D = 0x55700C00
HOOK = 0x5575A824
ORIG = bytes.fromhex("83f8647e05b8640000005bc3")   # cmp/jle/mov 100/pop ebx/ret
CAVE = 0x55815100
CAVE_HI = 0x55815120


def make_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = """
        cmp  eax, 0x64
        jle  _hi
        mov  eax, 0x64
    _hi:
        test eax, eax
        jns  _lo
        xor  eax, eax
    _lo:
        pop  ebx
        ret
    """
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)
    return bytes(code)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_cave()
    assert CAVE + len(cave) <= CAVE_HI, len(cave)
    hook = b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5)) + b"\x90" * 7

    edits = [(CAVE, bytes(len(cave)), cave, "cave_hpbarclamp"),
             (HOOK, ORIG, hook, "HitPointsToHitPcnt tail")]
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-26s @0x%08X  %s (%d B)" % (nm, va, st, len(nb)))
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
    print("APPLIED - test: overkill a wall with Wall Crushing (ram/giant) in "
          "tactical combat: no Blt Error/FCWin dialog, bar empties correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
