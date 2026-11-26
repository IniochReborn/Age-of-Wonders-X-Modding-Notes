#!/usr/bin/env python3
r"""AoWx -- elemental nodes heal & bless their corresponding units.

USER SPEC 2026-08-30: standing an army on a node heals + grants Nature's
Blessing (exactly the Spring of Life effect) to that node's units:
  Fire node  : Fire Elemental 226, Fire Sprite 228, Yaka Avatar 22,
               Dwarf First Born 115
  Water node : Water Elemental 227, Frost Queen 42
  Life node  : Spirit Puppet 130, Greater Spirit Puppet 241,
               Gold Dragon 216, Astra 133, Nature Elemental 80
  Death node : Black Dragon 217, Resurrected Dragon 243, plus ANY undead
               (the engine's own Turn Undead test: GetRace vmt+0xA4 == 0x0B
               or GetAbilityEnabled(0x81 Animated))
  Earth node : Earth Elemental 225, Nature Elemental 80
  Air node   : Air Elemental 224, Silver Dragon 252, Frost Queen 42
  Mana node  : Syron 221
(unit resource-indices resolved 2026-08-30 from Unitres.pfs children table +
manual display names; Dwarf First Born pinned by level-4 + stat match)
The wasteland modulation of Spring of Life does NOT apply here (our spring
patch lives inside TSpringOfLife.ExecuteNaturesBlessing only), and nodes
grant nothing in combat (this fires on the strategic ArmyPlaced only) --
both per spec, both by construction.

MECHANISM: the seven node classes inherit TStructure.ArmyPlaced @0x5575F360
(VMT slot +0x180, same slot as TSpringOfLife.ArmyPlaced @0x557A3F38). Each
class's slot is repointed to a tiny stub (push <class index>; jmp common).
The common cave: runs the INHERITED TStructure.ArmyPlaced first (capture
behaviour preserved), then army = [MO+0x1C] (ArmyPlaced's EDX is the placed
TArmyHS; the owner read in ExecuteNaturesBlessing proves the offset), loops
units (count = [army vmt+0x54], TUnitList.GetUnit @0x5578309C), and for each
matching unit does the Spring's per-unit action verbatim:
    mov edx,0x63 ; mov ecx,[unit] ; call [ecx+0x94]   ; ExpandAbility
which heals AND grants Nature's Blessing (proven by our spring cave). The
death node additionally blesses any unit passing the undead test. No sound/
sparkle is played (silent bless -- can be added later if wanted).

Class VMTs (found via vmtSelfPtr, ArmyPlaced slot verified inherited):
  TFireNode 0x557BF624  TWaterNode 0x557C092C  TEarthNode 0x557BFAE0
  TAirNode 0x557C0DF4   TLifeNode 0x557C046C   TDeathNode 0x557BFFA4
  TPowerNode 0x557CFFE4 (plain mana node). TRandomNode is left alone (it
  resolves into a concrete node type; if a live TRandomNode ever appears
  un-transformed it simply stays vanilla).

PIC: rel32 + register/virtual calls; the match tables are addressed off a
call/pop anchor (pop the RUNTIME anchor, displacement = target - anchor).
VMT slot dwords keep their .reloc entries (new values are in-image VAs).

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_elemnodes"

D = 0x55700C00
# nodes inherit TPlayerStructure.ArmyPlaced (capture behaviour), NOT the
# TStructure base -- verified from the live slots 2026-08-30
STRUCT_ARMYPLACED = 0x55760F24
GETUNIT = 0x5578309C
SLOT = 0x180
AB_BLESSING = 0x63
AB_ANIMATED = 0x81
RACE_UNDEAD = 0x0B

# v2 additions (user 2026-08-30): Hell Hound 202 -> fire AND death; Shadow
# Dragon 288 + Spider Queen 150 -> death; Ent 282 + Forest Dragon 290 +
# Druid 238/276 (two roster records, both included) -> earth; Elder Dragon
# 292 -> mana.
NODES = [  # (name, vmt, unit index list, undead_flag)
    ("TFireNode", 0x557BF624, [226, 228, 22, 115, 202], 0),
    ("TWaterNode", 0x557C092C, [227, 42], 0),
    ("TEarthNode", 0x557BFAE0, [225, 80, 282, 290, 238, 276], 0),
    ("TAirNode", 0x557C0DF4, [224, 252, 42], 0),
    ("TLifeNode", 0x557C046C, [130, 241, 216, 133, 80], 0),
    ("TDeathNode", 0x557BFFA4, [217, 243, 202, 288, 150], 1),
    ("TPowerNode", 0x557CFFE4, [221, 292], 0),
]

CAVE = 0x55814300
CAVE_HI = 0x55814500


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    # layout: [stubs][common][table-of-offsets][u16 lists]
    # assemble common at a guessed address first to learn its size, then lay
    # out for real -- simpler: two-pass with fixed stub block size.
    stub_size = 7 * 8                    # push imm8(2) + jmp rel32(5) + pad(1)
    common_at = CAVE + stub_size

    def asm_common(addr, tbl_disp):
        src = f"""
            pop  ecx
            push ebx
            push esi
            push edi
            push ebp
            push ecx
            mov  ebx, eax
            mov  esi, edx
            call 0x{STRUCT_ARMYPLACED:X}
            mov  eax, ebx
            mov  edx, [eax]
            call dword ptr [edx+0x150]
            test al, al
            jnz  _done
            mov  ebp, [esi+0x1C]
            test ebp, ebp
            jz   _done
            call _a
        _a:
            pop  ebx
            xor  esi, esi
        _loop:
            mov  eax, ebp
            mov  edx, [eax]
            call dword ptr [edx+0x54]
            cmp  esi, eax
            jge  _done
            mov  eax, ebp
            mov  edx, esi
            call 0x{GETUNIT:X}
            inc  esi
            test eax, eax
            jz   _loop
            push eax
            mov  edx, [eax+0x40]
            test edx, edx
            jz   _next
            mov  eax, [edx+4]
            mov  ecx, [eax]
            call dword ptr [ecx+0x84]
            mov  edx, [esp+4]
            lea  ecx, [ebx + {tbl_disp} + edx*4]
            movzx ecx, word ptr [ecx]
            add  ecx, ebx
        _match:
            movzx edi, word ptr [ecx]
            cmp  edi, 0xFFFF
            je   _nomatch
            cmp  eax, edi
            je   _bless
            add  ecx, 2
            jmp  _match
        _nomatch:
            mov  edx, [esp+4]
            cmp  edx, 5
            jne  _next
            mov  eax, [esp]
            mov  edx, [eax]
            call dword ptr [edx+0xA4]
            cmp  al, {RACE_UNDEAD}
            je   _bless
            mov  eax, [esp]
            mov  edx, {AB_ANIMATED}
            mov  ecx, [eax]
            call dword ptr [ecx+0x148]
            test al, al
            jz   _next
        _bless:
            pop  eax
            mov  edx, {AB_BLESSING}
            mov  ecx, [eax]
            call dword ptr [ecx+0x94]
            jmp  _loop
        _next:
            pop  eax
            jmp  _loop
        _done:
            pop  ecx
            pop  ebp
            pop  edi
            pop  esi
            pop  ebx
            ret
        """
        src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
        code, _ = ks.asm(src, addr)
        return bytearray(code)

    # first pass to measure, second with real table displacement
    probe = asm_common(common_at, 0x1000)
    tables_at = common_at + len(probe)
    # anchor VA inside common: find call-next/pop ebx
    i = next(k for k in range(len(probe) - 5)
             if probe[k] == 0xE8 and probe[k + 1:k + 5] == b"\x00\x00\x00\x00"
             and probe[k + 5] == 0x5B)
    anchor = common_at + i + 5
    tbl_disp = tables_at - anchor
    common = asm_common(common_at, tbl_disp)
    assert len(common) == len(probe), "common size changed between passes"

    # tables: 7 u16 offsets (relative to anchor) then the u16 lists
    lists = bytearray()
    offs = []
    base = tables_at + 7 * 4            # offset table entries are u32-read via
    for _nm, _vmt, ids, _ud in NODES:   # movzx word -> store u16 in u32 slots
        offs.append(base + len(lists) - anchor)
        for u in ids:
            lists += struct.pack("<H", u)
        lists += b"\xff\xff"
    tblblk = bytearray()
    for o in offs:
        assert 0 <= o <= 0xFFFF, o
        tblblk += struct.pack("<I", o)
    tables = bytes(tblblk) + bytes(lists)

    # stubs
    stubs = bytearray()
    for idx in range(7):
        va = CAVE + len(stubs)
        stubs += bytes([0x6A, idx])                       # push idx
        stubs += b"\xE9" + struct.pack("<i", common_at - (va + 2 + 5))
        stubs += b"\x90"
    assert len(stubs) == stub_size

    blob = bytes(stubs) + bytes(common) + tables
    return blob, [CAVE + i * 8 for i in range(7)]


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    blob, stub_vas = build()
    assert CAVE + len(blob) <= CAVE_HI, len(blob)

    edits = [(CAVE, bytes(len(blob)), blob, "nodes cave (stubs+common+tables)")]
    for (nm, vmt, _ids, _ud), stub in zip(NODES, stub_vas):
        edits.append((vmt + SLOT, struct.pack("<I", STRUCT_ARMYPLACED),
                      struct.pack("<I", stub), "%s ArmyPlaced repoint" % nm))
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-34s @0x%08X  %s" % (nm, va, st))
    if "FOREIGN" in states:
        print("FOREIGN - refusing (a node class may override ArmyPlaced?)")
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
    print("APPLIED - test: walk each listed unit onto its node -> healed to "
          "full + Nature's Blessing; wrong units/nodes -> nothing; node "
          "capture still works; death node blesses any undead; no combat "
          "effect from nodes; wasteland under a node changes nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
