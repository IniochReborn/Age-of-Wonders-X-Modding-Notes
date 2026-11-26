#!/usr/bin/env python3
r"""
Scroll items: spell book + item description (AoWx.exe, 2026-10-30).  Needs patch_scroll_spells_store_v1 (AoWEPACK).

Scroll = TItem type 5 ([item+0x34]); spells: slot 1 = [item+0x38] (spell id, vanilla), slots 2..7 =
[item+0x4C+4k] holding id+1 (0 = None).

1. Spell book (TSpellBook, ebx = book at every site): the 5 calls of TPlayerMagicControl.ListSpells
   (thunk 0x402654: eax=pmc, edx=&[book+0x224] TSpellList, cl=spell-type set) at 0x42F0F9 (strategic page),
   0x42F20C (combat page), 0x430D58 / 0x430DDE (strategic open), 0x430EDD (combat open) -> call sb_cave:
   the original call, then - if the book has a caster ([book+0x230] set, [book+0x22C] non-nil, IsClass THero) -
   every scroll in that hero's backpack ([hero+0x74] -> TList [+8]) adds its spells whose type [spell+0x22] is
   in the set and that are not already listed (TList.Add on [[list]+4]).  The sort that follows (SortOnLevel)
   still applies.  Only the holding hero sees them; the player's researched list is untouched.  Casting itself
   never checks "known" (CanCastSpellInstantly / CastSpell / CastCombatSpell / TSpellTE.Validate), so a listed
   scroll spell casts normally and identically on every machine.
2. Item popup (TItemBanner): after the granted-ability loop, @0x406DF7 (9 B `mov eax,[ebx+0x70] / mov eax,
   [eax+0x114]`) -> jmp ib_cave: for a scroll add one line "Spell: <name>" (LStrCat3 into [ebp-0xC], AbLB.Items
   AddObject, object 0) per real spell (slot 1 if the spell exists, slots 2..7 when non-zero); then the moved
   instructions and back to 0x406E00, where the height is computed from the line count.

Zone .xtut 0x638C00..0x639000 ('SCX1').  Exe never rebases (asserted).  Dry-run default; --apply / --revert.
Backup <game>\backup\AoWx.exe.bak_scrollspells.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWx.exe")
BASE = 0x400000
MAGIC = b"SCX1"
ZONE, ZONE_END = 0x638C00, 0x639000
LISTSPELLS, GETSPELL, LSTRCAT3 = 0x402654, 0x4025A4, 0x401120
IAT_ISCLASS, IAT_TLISTADD, IAT_THERO, IAT_HSSET = 0x45D354, 0x45D4D8, 0x45DFC4, 0x45DF78
SB_SITES = [0x42F0F9, 0x42F20C, 0x430D58, 0x430DDE, 0x430EDD]
IB_SITE, IB_ORIG, IB_BACK = 0x406DF7, bytes.fromhex("8b43708b8014010000"), 0x406E00
PREFIX = b"Spell: "
STR_VA = ZONE + 0x10                 # Delphi constant string: [-8] -1, [-4] len, chars, 0
CODE_SB = ZONE + 0x40
CODE_IB = ZONE + 0x200


def spell_loop(on_spell):
    """asm fragment: esi = scroll item; for each real slot spell -> eax = spell, run on_spell; uses edi as slot."""
    return f"""
    xor  edi, edi
sl_next:
    cmp  edi, 7
    jge  sl_end
    test edi, edi
    jnz  sl_extra
    mov  edx, dword ptr [esi + 0x38]
    jmp  sl_get
sl_extra:
    mov  edx, dword ptr [esi + edi*4 + 0x48]
    test edx, edx
    jz   sl_skip
    dec  edx
sl_get:
    test edx, edx
    js   sl_skip
    mov  eax, dword ptr [{IAT_HSSET:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x84]
    call {GETSPELL:#x}
    test eax, eax
    jz   sl_skip
{on_spell}
sl_skip:
    inc  edi
    jmp  sl_next
sl_end:
"""


SB_SRC = f"""
    push ecx
    push edx
    call {LISTSPELLS:#x}
    pop  edx
    pop  ecx
    pushad
    sub  esp, 8
    mov  dword ptr [esp], ecx
    cmp  dword ptr [ebx + 0x230], 0
    je   sb_out
    mov  eax, dword ptr [ebx + 0x22C]
    test eax, eax
    jz   sb_out
    mov  ebp, eax
    mov  edx, dword ptr [{IAT_THERO:#x}]
    call dword ptr [{IAT_ISCLASS:#x}]
    test al, al
    jz   sb_out
    mov  eax, dword ptr [esp + 0x1C]
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   sb_out
    mov  eax, dword ptr [eax + 4]
    test eax, eax
    jz   sb_out
    mov  dword ptr [esp + 4], eax
    mov  eax, dword ptr [ebp + 0x74]
    test eax, eax
    jz   sb_out
    mov  eax, dword ptr [eax + 8]
    test eax, eax
    jz   sb_out
    mov  ebx, eax
    xor  ecx, ecx
it_next:
    cmp  ecx, dword ptr [ebx + 8]
    jge  sb_out
    mov  eax, dword ptr [ebx + 4]
    mov  esi, dword ptr [eax + ecx*4]
    test esi, esi
    jz   it_skip
    cmp  byte ptr [esi + 0x34], 5
    jne  it_skip
    push ecx
{spell_loop('''
    movzx ecx, byte ptr [eax + 0x22]
    mov  edx, dword ptr [esp + 4]
    bt   edx, ecx
    jnc  sl_skip
    mov  ecx, dword ptr [esp + 8]
    mov  edx, dword ptr [ecx + 4]
    mov  ecx, dword ptr [ecx + 8]
dup:
    dec  ecx
    js   add
    cmp  dword ptr [edx + ecx*4], eax
    je   sl_skip
    jmp  dup
add:
    mov  edx, eax
    mov  eax, dword ptr [esp + 8]
    call dword ptr [%s]''' % hex(IAT_TLISTADD))}
    pop  ecx
it_skip:
    inc  ecx
    jmp  it_next
sb_out:
    add  esp, 8
    popad
    ret
"""

IB_SRC = f"""
    pushad
    mov  esi, dword ptr [ebp - 4]
    test esi, esi
    jz   ib_out
    cmp  byte ptr [esi + 0x34], 5
    jne  ib_out
{spell_loop('''
    mov  ecx, dword ptr [eax + 8]
    mov  edx, %s
    lea  eax, [ebp - 0xC]
    call %s
    mov  eax, dword ptr [ebx + 0x70]
    mov  eax, dword ptr [eax + 0x114]
    mov  edx, dword ptr [ebp - 0xC]
    xor  ecx, ecx
    push edi
    mov  edi, dword ptr [eax]
    call dword ptr [edi + 0x38]
    pop  edi''' % (hex(STR_VA), hex(LSTRCAT3)))}
ib_out:
    popad
    mov  eax, dword ptr [ebx + 0x70]
    mov  eax, dword ptr [eax + 0x114]
    jmp  {IB_BACK:#x}
"""


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    sb = bytes(ks.asm(SB_SRC, CODE_SB)[0])
    ib = bytes(ks.asm(IB_SRC, CODE_IB)[0])
    assert CODE_SB + len(sb) <= CODE_IB and CODE_IB + len(ib) <= ZONE_END, (hex(len(sb)), hex(len(ib)))
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<iI", z, STR_VA - ZONE - 8, -1, len(PREFIX))
    z[STR_VA - ZONE:STR_VA - ZONE + len(PREFIX)] = PREFIX
    z[CODE_SB - ZONE:CODE_SB - ZONE + len(sb)] = sb
    z[CODE_IB - ZONE:CODE_IB - ZONE + len(ib)] = ib
    return bytes(z)


def callrel(at, tgt):
    return b"\xe8" + struct.pack("<i", tgt - (at + 5))


def game_running():
    try:
        return "AoWx.exe" in subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read()
    pe = pefile.PE(data=d)
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0, "AoWx.exe became DYNAMIC_BASE"
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone = build()
    patches = [(s, callrel(s, LISTSPELLS), callrel(s, CODE_SB)) for s in SB_SITES]
    patches.append((IB_SITE, IB_ORIG, b"\xe9" + struct.pack("<i", CODE_IB - (IB_SITE + 5)) + b"\x90" * 4))
    patches.append((ZONE, bytes(len(zone)), zone))
    rl = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type == 3:
                rl.add(BASE + e.rva)
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in patches)]
    sts = []
    for s, o, n in patches:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
        if s != ZONE:
            print("site %#x %s %s" % (s, c.hex(), sts[-1]))
    print("zone %#x %s | relocs %s" % (ZONE, sts[-1], bad or "none"))
    if "OTHER" in sts or bad or len(set(sts)) != 1:
        print("ABORT (mixed/foreign state)"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if game_running():
        print("AoWx.exe is running - close the game first"); return 1
    bak = bak_path(EXE, ".bak_scrollspells")
    if not revert and not os.path.exists(bak):
        shutil.copy2(EXE, bak); print("backup ->", bak)
    try:
        with open(EXE, "r+b") as f:                 # in-place (house rule); zone first
            for s, o, n in reversed(patches):
                f.seek(off(s)); f.write(o if revert else n)
    except PermissionError:
        print("LOCKED"); return 1
    d2 = open(EXE, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in patches)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
