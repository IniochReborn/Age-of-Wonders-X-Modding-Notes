#!/usr/bin/env python3
r"""AoWEPACK.dll: SUMMON SPELLS CASTABLE IN TACTICAL COMBAT - model side (2026-10-24, user request).
Pairs with patch_tc_combat_summon_v1.py (AoWTCPCK: class 0x27 + instant cast + map object / placement).

Design (RE in memory combat-summons.md):
  * Combat CA = TAnimateDeadCA.  Every summon class VMT (TSummonSpell 0x557E3004 + its 13 subclasses; the pipeline's
    summon clones are TSummonMermaid objects) gets slot +0x78 CreateCA := TAnimateDead.CreateCA 0x557FA4BC (vanilla
    TSpell.CreateCA 0x55779450 returns nil).  CreateCA stores caster/target COIDs, the summon's own spell id ([ca+0x18]
    = self+0x10) and - with the push-1 flag - the cost THero.CastingMana(caster, self) (caster-cost wallet cave), so the
    summon is charged its own (Conjurer-discounted) price by TExclusiveCombatSpellCA.Execute -> CombatCastingDone.
  * EX hook: TAnimateDeadCA.Execute 0x557FA2F4 (5 B `push ebx/esi/edi; mov esi,edx`) -> cave: spell [ca+0x18] with
    category [spell+0x22] == 2 (stGlobal: only our summons reach an AnimateDead CA) -> SUMMON, else replay + 0x557FA2F9.
    SUMMON: base TExclusiveCombatSpellCA.Execute (cost); caster cu = FindID([combat+0xC], [ca+0xC]); unit id =
    [spell+0x38] TIntegerList item 0; new TUnit exactly like TSummonSpellTE.Process 0x557E4058 (TAbstractUnit.Create
    [0x55710C6C] / SetUnitResource / player = caster unit +0x24 via VMT+0x16C / ExpandAbility 0x9B Summoned: data
    VMT+0x54 upkeep = spell+0x1C (Conjurer III -> reduced like cave 0x55816770), VMT+0x58 player, +0x14 =
    0x557E4460(spell, unit)); combat unit = combat VMT+0x58; COID = TCombat.CreateUniqueCOID; position byte =
    caster's party nibble | first free slot 8..15 (TCombatData.FindPosition) - slots > 7 are skipped by the normal
    post-combat return and placed by TCombatUnit.Finalize pass 2 at the battle hex = the captured-unit path (joins the
    stack if room, else adjacent - patch_overflow_army_v1); TCombatUnit.Setup (player idx = caster [cu+0x45]) ->
    TCombatData.AddObject -> VMT+0xCC Initialize -> VMT+0xBC Activate (side list, party, gfx); [ca+0xD] := new COID
    (the TC side builds the map object for it); unit reference released.
  * LS hook: TPlayerMagicControl.ListSpells type test 0x5577D1AB (5 B `mov al,[ebx+0x22] / cmp al,7`): while a battle
    runs ([[0x558FA040]+0x120] != 0) and the requested set contains stCombat, a summon (VMT+0x78 == our CreateCA) is
    listed as a combat spell -> the spell book's combat page shows it; THero.CanCastCombatSpell has no type check.
PIC everywhere (AoWEPACK may rebase): data via call/pop delta, calls rel32 inside the image.
Zone 0x558B0000..0x558B0800 'CSU1'.  Backup <game>\backup\AoWEPACK.dll.bak_combatsummon.  Dry run / --apply / --revert.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
V2F = 0x55700C00
ZONE, ZONE_END = 0x558B0000, 0x558B0800
MAGIC = b"CSU1"
SUMMON_VMTS = [0x557E3004, 0x557E3120, 0x557E323C, 0x557E3354, 0x557E346C, 0x557E3594, 0x557E36C0, 0x557E37EC,
               0x557E3918, 0x557E3A3C, 0x557E3B64, 0x557E3C88, 0x557E3DAC, 0x557E3ED4]
SLOT_CA, CA_OLD, CA_NEW = 0x78, 0x55779450, 0x557FA4BC
EX_SITE, EX_ORIG, EX_BACK = 0x557FA2F4, bytes.fromhex("5356578bf2"), 0x557FA2F9
LS_SITE, LS_ORIG, LS_BACK = 0x5577D1AB, bytes.fromhex("8a43223c07"), 0x5577D1B0
U_EX, U_LS = 0x40, 0x400

F = dict(getspell=0x55779AC8, base_ex=0x557F6C84, findid=0x55728C68, intget=0x55702E94, ucreate=0x5577EB28,
         getres=0x55785050, setres=0x55782BE4, abdata=0x5574F1C4, conjlvl=0x558165E0, conjred=0x55816580,
         sumbyte=0x557E4460, coid=0x557272D4, findpos=0x55728CA4, setup=0x55724AA4, addobj=0x55728CE0,
         g_units=0x558E92E8, c_unit=0x55710C6C, g_map=0x558FA040, ca_new=CA_NEW, ex_back=EX_BACK, ls_back=LS_BACK)


def pic(reg, at):
    """call $+5 / pop reg / sub reg, <address of pop> -> reg = load delta."""
    r = {"eax": 0, "ecx": 1, "edx": 2, "ebx": 3, "esi": 6, "edi": 7}[reg]
    return b"\xe8\x00\x00\x00\x00" + bytes([0x58 + r, 0x81, 0xE8 + r]) + struct.pack("<I", at + 5)


EX_SRC = """
    push eax
    push edx
    push ecx
    mov  edx, dword ptr [eax + 0x18]
    mov  eax, dword ptr [ecx + {g_units:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x84]
    call {getspell:#x}
    pop  ecx
    test eax, eax
    jz   notsum
    cmp  byte ptr [eax + 0x22], 2
    jne  notsum
    pop  edx
    pop  eax
    add  esp, 4
    jmp  summon
notsum:
    pop  edx
    pop  eax
    pop  ecx
    push ebx
    push esi
    push edi
    mov  esi, edx
    jmp  {ex_back:#x}
summon:
    push ebx
    push esi
    push edi
    push ebp
    mov  ebp, esp
    sub  esp, 0x30
    mov  dword ptr [ebp - 4], ecx
    mov  ebx, eax
    mov  esi, edx
    mov  eax, ebx
    mov  edx, esi
    call {base_ex:#x}
    movzx edx, byte ptr [ebx + 0xc]
    mov  eax, dword ptr [esi + 0xc]
    call {findid:#x}
    mov  edi, eax
    test edi, edi
    jz   s_out
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {g_units:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x84]
    mov  edx, dword ptr [ebx + 0x18]
    call {getspell:#x}
    mov  dword ptr [ebp - 0x20], eax
    mov  eax, dword ptr [eax + 0x38]
    xor  edx, edx
    call {intget:#x}
    mov  dword ptr [ebp - 0xc], eax
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {c_unit:#x}]
    xor  ecx, ecx
    mov  dl, 1
    call {ucreate:#x}
    mov  dword ptr [ebp - 8], eax
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {g_units:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x5c]
    mov  edx, dword ptr [ebp - 0xc]
    call {getres:#x}
    mov  edx, eax
    mov  eax, dword ptr [ebp - 8]
    call {setres:#x}
    mov  eax, dword ptr [edi + 0x4c]
    mov  dl, byte ptr [eax + 0x24]
    mov  eax, dword ptr [ebp - 8]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x16c]
    mov  edx, 0x9b
    mov  eax, dword ptr [ebp - 8]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x94]
    test al, al
    jz   s_noab
    mov  edx, 0x9b
    mov  eax, dword ptr [ebp - 8]
    call {abdata:#x}
    mov  dword ptr [ebp - 0x10], eax
    mov  eax, dword ptr [ebp - 0x20]
    mov  eax, dword ptr [eax + 0x1c]
    mov  dword ptr [ebp - 0x24], eax
    mov  eax, dword ptr [edi + 0x4c]
    mov  edx, 0xad
    call {conjlvl:#x}
    cmp  eax, 3
    jl   s_up
    mov  eax, dword ptr [ebp - 0x24]
    mov  edx, 1
    call {conjred:#x}
    mov  dword ptr [ebp - 0x24], eax
s_up:
    mov  edx, dword ptr [ebp - 0x24]
    mov  eax, dword ptr [ebp - 0x10]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x54]
    mov  eax, dword ptr [edi + 0x4c]
    mov  dl, byte ptr [eax + 0x24]
    mov  eax, dword ptr [ebp - 0x10]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x58]
    mov  eax, dword ptr [ebp - 0x20]
    mov  edx, dword ptr [ebp - 8]
    call {sumbyte:#x}
    mov  edx, dword ptr [ebp - 0x10]
    mov  byte ptr [edx + 0x14], al
s_noab:
    mov  eax, esi
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x58]
    mov  dword ptr [ebp - 0x14], eax
    mov  eax, esi
    call {coid:#x}
    movzx eax, al
    mov  dword ptr [ebp - 0x18], eax
    movzx eax, byte ptr [edi + 0x46]
    and  eax, 0xf0
    or   eax, 8
    mov  dword ptr [ebp - 0x1c], eax
s_pos:
    mov  edx, dword ptr [ebp - 0x1c]
    mov  eax, dword ptr [esi + 0xc]
    call {findpos:#x}
    test eax, eax
    jz   s_haspos
    inc  dword ptr [ebp - 0x1c]
    test byte ptr [ebp - 0x1c], 0xf
    jnz  s_pos
    jmp  s_rel
s_haspos:
    push dword ptr [ebp - 8]
    push dword ptr [ebp - 0x1c]
    movzx eax, byte ptr [edi + 0x45]
    push eax
    mov  edx, dword ptr [ebp - 0x18]
    xor  ecx, ecx
    mov  eax, dword ptr [ebp - 0x14]
    call {setup:#x}
    mov  edx, dword ptr [ebp - 0x14]
    mov  eax, dword ptr [esi + 0xc]
    call {addobj:#x}
    mov  edx, esi
    mov  eax, dword ptr [ebp - 0x14]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0xcc]
    mov  edx, esi
    mov  eax, dword ptr [ebp - 0x14]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0xbc]
    mov  eax, dword ptr [ebp - 0x18]
    mov  byte ptr [ebx + 0xd], al
s_rel:
    mov  eax, dword ptr [ebp - 8]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x2c]
s_out:
    mov  esp, ebp
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""

LS_SRC = """
    mov  al, byte ptr [ebx + 0x22]
    cmp  al, 2
    jne  back
    test byte ptr [esp + 0xc], 1
    jz   back
    mov  edx, dword ptr [ecx + {g_map:#x}]
    cmp  dword ptr [edx + 0x120], 0
    je   back
    lea  edx, [ecx + {ca_new:#x}]
    mov  ecx, dword ptr [ebx]
    cmp  dword ptr [ecx + 0x78], edx
    jne  back
    xor  eax, eax
back:
    pop  edx
    pop  ecx
    cmp  al, 7
    jmp  {ls_back:#x}
"""


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    va = ZONE + U_EX
    head = b"\x51" + pic("ecx", va + 1)                       # push ecx ; ecx = delta
    body = bytes(ks.asm(EX_SRC.format(**F), va + len(head))[0])
    ex = head + body
    assert U_EX + len(ex) <= U_LS, len(ex)
    z[U_EX:U_EX + len(ex)] = ex
    va = ZONE + U_LS
    head = b"\x51\x52" + pic("ecx", va + 2)                   # push ecx / push edx ; ecx = delta
    body = bytes(ks.asm(LS_SRC.format(**F), va + len(head))[0])
    ls = head + body
    assert U_LS + len(ls) <= len(z)
    z[U_LS:U_LS + len(ls)] = ls
    jmp = lambda site, to: b"\xe9" + struct.pack("<i", to - (site + 5))
    return bytes(z), jmp(EX_SITE, ZONE + U_EX), jmp(LS_SITE, ZONE + U_LS)


def relocs(path, ranges):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in b.entries:
            if e.type and any(lo - 3 <= ib + e.rva < hi for lo, hi in ranges):
                out.append(hex(ib + e.rva))
    return out


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zone, ex_new, ls_new = build()
    slots = [struct.unpack("<I", g(v + SLOT_CA, 4))[0] for v in SUMMON_VMTS]
    st_slots = "vanilla" if all(s == CA_OLD for s in slots) else "ours" if all(s == CA_NEW for s in slots) else "MIXED"
    ex, ls, zn = g(EX_SITE, 5), g(LS_SITE, 5), g(ZONE, ZONE_END - ZONE)
    st_ex = "vanilla" if ex == EX_ORIG else "ours" if ex == ex_new else "OTHER"
    st_ls = "vanilla" if ls == LS_ORIG else "ours" if ls == ls_new else "OTHER"
    st_z = "zero" if not any(zn) else "ours" if zn == zone else "older" if zn[:4] == MAGIC else "OTHER"
    print("VMT slots %s | EX %s | LS %s | zone %s (EX %d B)" % (st_slots, st_ex, st_ls, st_z, len(zone.rstrip(b'\0'))))
    if "OTHER" in (st_ex, st_ls, st_z) or st_slots == "MIXED": print("ABORT"); return 1
    bad = relocs(DLL, [(EX_SITE, EX_SITE + 5), (LS_SITE, LS_SITE + 5), (ZONE, ZONE_END)])
    if bad: print("ABORT relocs", bad); return 1
    done = (st_slots, st_ex, st_ls) == (("vanilla",) * 3 if revert else ("ours",) * 3) and st_z == ("zero" if revert else "ours")
    if done: print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_combatsummon")
    if not revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    writes = [(ZONE, bytes(len(zone)) if revert else zone), (EX_SITE, EX_ORIG if revert else ex_new),
              (LS_SITE, LS_ORIG if revert else ls_new)]
    writes += [(v + SLOT_CA, struct.pack("<I", CA_OLD if revert else CA_NEW)) for v in SUMMON_VMTS]
    with open(DLL, "r+b") as f:                       # in-place (house rule)
        for va, b in writes:
            f.seek(va - V2F); f.write(b)
    d2 = open(DLL, "rb").read()
    assert all(d2[va - V2F:va - V2F + len(b)] == b for va, b in writes)
    print("reverted" if revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
