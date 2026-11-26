#!/usr/bin/env python3
r"""AoWx -- ROOT-CAUSE fix for the defeat freeze ([[mp-leader-kill-freeze]]):
unit enchantments created by OUR Summoned-ability caves carry unit id 0.

patch_summoned_ability_v5.py (TRecallSpiritCA / TAnimateDeadCA caves) grants
the combat-spawned unit the Summoned ability (0x9B) like this:
    mov [unit+0x18], 1        ; fake unit id to pass Expand's assert
    ExpandAbility(0x9B)       ; -> TUnitEnchantment, [ench+0x18] := [unit+0x18]
    mov [ench+0x18], 0        ; "clear source unit ID"   <-- the bug
    SetSource(player)         ; -> RegisterEnchantment
When the unit persists after combat (Recall Spirits / Animate Dead spawns),
TAbstractUnit.Activate -> TUnitControl.RegisterUnit assigns it a REAL id, but
the enchantment keeps 0. Anything that later needs "the unit of this
enchantment" (TUnitEnchantment.Dispel -> FindUnit) fails: the caster's
defeat cleanup livelocked on it (fixed generically by
build_defeat_enchant_hang.py), Dispel Magic can't remove the Summoned effect,
the AI's upkeep management can't shed it, etc.

FIX (engine-side, generic, heals every path incl. loading old saves):
in TAbstractUnit.RegisterEnchantments @0x5577F2A4, which Activate calls right
AFTER RegisterUnit (the unit id is final by then) for every unit-enchantment
ability the unit holds, re-point the enchantment at its holder before
registering:  [ench+0x18] := [unit+0x18].  A TUnitEnchantment always belongs
to the unit whose ability data references it, so this is always correct.
Hook = the 5-byte `call RegisterEnchantment` @0x5577F318 (edi=unit,
eax=caster's TPlayerMagicControl, edx=enchantment) -> cave3 (14 B, rel32 only).

Cave3 @0x558155E0..0x558155EE (inside the defeatench zone, which ends at
0x55815600; next free AoWEPACK cave stays 0x55815600).

Usage: dry run default; --apply; --revert.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_summonuid"

IB = 0x55700000
D = 0x55700C00
HOOK = 0x5577F318                 # call RegisterEnchantment inside RegisterEnchantments
REGISTER = 0x5577D358             # TPlayerMagicControl.RegisterEnchantment
ORIG = b"\xE8" + struct.pack("<i", REGISTER - (HOOK + 5))   # e8 3b e0 ff ff
CAVE = 0x558155E0
CAVE_LIMIT = 0x55815600


def make_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = """
        push ecx
        mov  ecx, [edi+0x18]
        mov  [edx+0x18], ecx
        pop  ecx
        call 0x%X
        ret
    """ % REGISTER
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)
    return bytes(code)


def relocs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt
    raw = rsz = None
    for i in range(n):
        b = tbl + i * 40
        if d[b:b + 8].rstrip(b"\0") == b".reloc":
            _vsz, _va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
    off, end = raw, raw + rsz
    while off < end - 8:
        page, size = struct.unpack_from("<II", d, off)
        if size < 8 or size > 0x1000:
            break
        for i in range(off + 8, off + size, 2):
            w = struct.unpack_from("<H", d, i)[0]
            if w >> 12 == 3:
                yield IB + page + (w & 0xFFF)
        off += size


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_cave()
    assert CAVE + len(cave) <= CAVE_LIMIT, len(cave)
    hook = b"\xE8" + struct.pack("<i", CAVE - (HOOK + 5))
    edits = [(HOOK, ORIG, hook, "RegisterEnchantments call"),
             (CAVE, bytes(len(cave)), cave, "cave3 (unit-id heal)")]
    states = []
    for va, ob, nb, nm in edits:
        cur = bytes(d[va - D:va - D + len(nb)])
        st = "original" if cur == ob else "applied" if cur == nb else "FOREIGN"
        states.append(st)
        print("  %-26s @0x%08X  %-8s (%d B)" % (nm, va, st, len(nb)))
    bad = [va for va in relocs(d) if any(lo <= va < lo + len(nb) for lo, _, nb, _ in edits)]
    if bad:
        print("reloc inside patched range: %s - refusing" % ", ".join("0x%08X" % v for v in bad))
        return 1
    if "FOREIGN" in states:
        print("FOREIGN bytes - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        try:
            open(DLL, "wb").write(bytes(d))
        except PermissionError:
            print("LOCKED - close AoWx.exe / AoWDevX.exe and retry")
            return 1
        print("reverted")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not do_apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(cave, CAVE):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply / --revert)")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWx.exe / AoWDevX.exe and retry")
        return 1
    print("APPLIED - test: Recall Spirits / Animate Dead in tactical combat, keep "
          "the spawn alive past combat, then Dispel Magic it (should remove the "
          "Summoned effect) and defeat/surrender its owner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
