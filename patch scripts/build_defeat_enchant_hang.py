#!/usr/bin/env python3
r"""AoWx -- fix the VANILLA freeze when a player is DEFEATED (leader killed /
surrender) while an ORPHANED unit enchantment sits in that player's list.

DIAGNOSED LIVE 2026-09-03 (MP autosave "AoWx - After the Fall", player 3
"Nate the Great" killed in tactical AND in auto combat -> hard hang both
times; a fresh game did not reproduce). EIP sampler on the hung main thread:

  TArmyCombatMoveTE.ExecuteCombat -> TCombat.Finalize -> TAoWHSMap.GameOver
  -> TPlayerControl.GameOver -> ...SetPlayerGameOverStatus
  -> TPlayer.SetGameOverStatus (defeat cleanup) -> TPlayerMagicControl.
  RemoveEnchantments -> ExecuteDispelEnchantment -> TUnitEnchantment.Dispel
  -> TUnitControl.FindUnit -> (nil) ... forever.

  RemoveEnchantments @0x5577CB9C:  while list.Count > 0 do
                                      ExecuteDispelEnchantment(Count-1)
  TUnitEnchantment.Dispel @0x55765E14: unit := FindUnit([ench+0x18]);
      if unit = nil then EXIT (enchantment stays in the list!)
      else unit.RemoveAbility([ench+0x1C])  (-> Unregister -> list shrinks)

  The hung save held ONE TUnitEnchantment (ability 0x9B, caster 3, unit id
  0 -> FindUnit fails) in player 3's TEnchantmentList -> Dispel is a no-op
  -> Count never drops -> livelock. Vanilla bytes at every site (checked
  against AoWEPACK.dpl). Writing that list's TList.Count to 0 in the live
  process unfroze the game instantly (same effect as this patch).

FIX (two edits, both PIC caves, rel32 only + one call/pop anchor):
 1. RemoveEnchantments -> cave1: same loop, but if Count did not shrink after
    ExecuteDispelEnchantment, force-remove the last element via
    TPlayerMagicControl.UnregisterEnchantment(mc, ench) (= TList.Remove +
    Update, the engine's own unregister path). Guarantees termination.
 2. TUnitEnchantment.Dispel -> cave2: when FindUnit returns nil AND the
    enchantment has a caster ([ench+0xC] >= 0), unregister it from that
    caster's magic control (so orphans also vanish when dispelled from the
    spell UI and stop charging upkeep). Returns 0 like vanilla.
    ⚠ the displaced `mov eax,[AoWE.AoWHSMap]` imm32 @0x55765E18 carries a
    base reloc that lands inside our jmp rel32 -> neutralised (type 3 -> 0)
    on apply, restored on revert ([[patching-over-relocs-gotcha]]).

Engine facts used: TPlayerMagicControl +0x3C = TEnchantmentList (TENode);
its children TEObjectList (TList-derived) at [list+8] (+4 items, +8 count);
TEnchantment +0xC caster byte (-1 none), +0x18 unit id, +0x1C ability id;
AoWHSMap global 0x558FA040; map+0xFC TUnitControl; map+0x140 TPlayerList;
player+0x54 TPlayerMagicControl. FindUnit 0x5577E948, GetPlayers 0x557544D0,
ExecuteDispelEnchantment 0x5577D43C, UnregisterEnchantment 0x5577D394.

Caves: cave1 @0x55815530, cave2 @0x55815580, zone to 0x55815600
(next free AoWEPACK cave after this = 0x55815600).

Usage: dry run default; --apply; --revert (surgical, restores the reloc).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_defeatench"

IB = 0x55700000
D = 0x55700C00

REM_HOOK = 0x5577CB9C          # TPlayerMagicControl.RemoveEnchantments (37 B)
REM_ORIG = bytes.fromhex("538bd8eb128b433c8b10ff52548bd04a8bc3e889080000"
                         "8b433c8b10ff525485c075e25bc3")
DIS_HOOK = 0x55765E14          # TUnitEnchantment.Dispel (43 B)
DIS_ORIG = bytes.fromhex("538bd8a140a08f558b80fc0000008b5318e81e8b010085c0"
                         "740d8b531c8b08ff91980000005bc333c05bc3")
DIS_RELOC_VA = 0x55765E18      # imm32 of the displaced mov eax,[AoWHSMap]

MAP_GLOBAL = 0x558FA040
FINDUNIT = 0x5577E948
GETPLAYERS = 0x557544D0
EXECDISPEL = 0x5577D43C
UNREGISTER = 0x5577D394

CAVE1 = 0x55815530
CAVE2 = 0x55815580
CAVE_LIMIT = 0x55815600


def asm(src, base):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    # keystone treats ';' as a statement separator -> strip our comments first
    src = "\n".join(line.split(";", 1)[0] for line in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, base)
    return bytes(code)


def make_cave1():
    # eax = TPlayerMagicControl
    return asm("""
        push ebx
        push esi
        mov  ebx, eax
    _loop:
        mov  eax, [ebx+0x3C]
        mov  edx, [eax]
        call dword ptr [edx+0x54]        ; Count
        test eax, eax
        jz   _done
        mov  esi, eax                    ; count before
        lea  edx, [eax-1]
        mov  eax, ebx
        call 0x%X                        ; ExecuteDispelEnchantment(mc, Count-1)
        mov  eax, [ebx+0x3C]
        mov  edx, [eax]
        call dword ptr [edx+0x54]
        cmp  eax, esi
        jl   _loop                       ; shrank -> keep going
        mov  eax, [ebx+0x3C]             ; stuck: ench = children.items[esi-1]
        mov  eax, [eax+8]
        mov  eax, [eax+4]
        mov  edx, [eax+esi*4-4]
        mov  eax, ebx
        call 0x%X                        ; UnregisterEnchantment(mc, ench)
        jmp  _loop
    _done:
        pop  esi
        pop  ebx
        ret
    """ % (EXECDISPEL, UNREGISTER), CAVE1)


def make_cave2():
    # entered from Dispel after `push ebx; mov ebx,eax` (ebx = enchantment)
    pre = b"\x56"                                   # push esi
    pre += b"\xE8\x00\x00\x00\x00"                  # call $+5
    anchor = CAVE2 + len(pre)                       # VA of the pop
    pre += b"\x58"                                  # pop eax  (= anchor)
    pre += b"\x8B\xB0" + struct.pack("<i", MAP_GLOBAL - anchor)  # mov esi,[eax+disp]
    body = asm("""
        mov  eax, [esi+0xFC]             ; TUnitControl
        mov  edx, [ebx+0x18]             ; unit id
        call 0x%X                        ; FindUnit
        test eax, eax
        jz   _orphan
        mov  edx, [ebx+0x1C]
        mov  ecx, [eax]
        call dword ptr [ecx+0x98]        ; unit.RemoveAbility(ability id)  (vanilla)
        pop  esi
        pop  ebx
        ret
    _orphan:
        movsx edx, byte ptr [ebx+0xC]    ; caster player (-1 = none)
        test edx, edx
        js   _fail
        mov  eax, [esi+0x140]            ; TPlayerList
        call 0x%X                        ; GetPlayers(list, idx) -> player / 0
        test eax, eax
        jz   _fail
        mov  eax, [eax+0x54]             ; TPlayerMagicControl
        mov  edx, ebx
        call 0x%X                        ; UnregisterEnchantment(mc, ench)
    _fail:
        xor  eax, eax
        pop  esi
        pop  ebx
        ret
    """ % (FINDUNIT, GETPLAYERS, UNREGISTER), CAVE2 + len(pre))
    return pre + body


def relocs(d, all_types=False):
    """Yield (file_offset_of_entry, va) for reloc entries (type 3 only unless all_types)."""
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
            if all_types or w >> 12 == 3:
                yield i, IB + page + (w & 0xFFF)
        off += size


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    c1, c2 = make_cave1(), make_cave2()
    assert CAVE1 + len(c1) <= CAVE2, len(c1)
    assert CAVE2 + len(c2) <= CAVE_LIMIT, len(c2)
    rem_hook = b"\xE9" + struct.pack("<i", CAVE1 - (REM_HOOK + 5))
    rem_hook += b"\x90" * (len(REM_ORIG) - len(rem_hook))
    dis_hook = b"\x53\x8B\xD8\xE9" + struct.pack("<i", CAVE2 - (DIS_HOOK + 8))
    dis_hook += b"\x90" * (len(DIS_ORIG) - len(dis_hook))

    edits = [(REM_HOOK, REM_ORIG, rem_hook, "RemoveEnchantments"),
             (DIS_HOOK, DIS_ORIG, dis_hook, "TUnitEnchantment.Dispel"),
             (CAVE1, bytes(len(c1)), c1, "cave1 (loop guard)"),
             (CAVE2, bytes(len(c2)), c2, "cave2 (orphan dispel)")]
    states = []
    for va, ob, nb, nm in edits:
        cur = bytes(d[va - D:va - D + len(nb)])
        st = "original" if cur == ob else "applied" if cur == nb else "FOREIGN"
        states.append(st)
        print("  %-26s @0x%08X  %-8s (%d B)" % (nm, va, st, len(nb)))
    # reloc audit: every type-3 entry touching our sites/caves
    ranges = [(va, va + len(nb)) for va, _, nb, _ in edits]
    hits = [(i, va) for i, va in relocs(d) if any(lo <= va < hi for lo, hi in ranges)]
    for i, va in hits:
        print("  reloc type 3 @0x%08X %s" % (va, "(expected: Dispel imm32)" if va == DIS_RELOC_VA else "!! UNEXPECTED"))
    if any(va != DIS_RELOC_VA for _, va in hits):
        print("unexpected reloc inside a patched range - refusing")
        return 1
    if "FOREIGN" in states:
        print("FOREIGN bytes - refusing")
        return 1

    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        for i, va in [(i, v) for i, v in relocs(d, all_types=True) if v == DIS_RELOC_VA]:
            w = struct.unpack_from("<H", d, i)[0]
            if w >> 12 == 0:
                struct.pack_into("<H", d, i, (3 << 12) | (w & 0xFFF))
                print("  reloc @0x%08X restored (type 0 -> 3)" % va)
        try:
            open(DLL, "wb").write(bytes(d))
        except PermissionError:
            print("LOCKED - close AoWx.exe / AoWDevX.exe and retry")
            return 1
        print("reverted")
        return 0

    if all(s == "applied" for s in states) and not hits:
        print("already applied")
        return 0
    if not do_apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            for nm, code, base in (("cave1", c1, CAVE1), ("cave2", c2, CAVE2)):
                print("  ---- %s ----" % nm)
                for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, base):
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
    for i, va in hits:
        w = struct.unpack_from("<H", d, i)[0]
        struct.pack_into("<H", d, i, w & 0x0FFF)          # type 3 -> 0 (skip)
        print("  reloc @0x%08X neutralised (type 3 -> 0)" % va)
    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWx.exe / AoWDevX.exe and retry")
        return 1
    print("APPLIED - test: reload the MP autosave, kill the leader (tactical "
          "and auto): defeat processes, no freeze. Sanity: cast/dispel a unit "
          "enchantment normally; kill an enchanted unit; surrender.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
