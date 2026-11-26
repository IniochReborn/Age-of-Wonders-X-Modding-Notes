#!/usr/bin/env python3
r"""
Miracle (209, Life tier 4 combat spell, research 250 / cost 7; 2026-10-16): "Unit is resurrected until end of combat with
random HP (min 30%) and random MP (no minimum)."   AoWEPACK.dll half (TCPCK half = patch_tc_miracle_v1.py).

Registered by patch_dual_sphere_spells_v1.py as a TRecallSpirit instance (donor TRecallSpirit = vmtSelfPtr 0x557F66D0 /
Create 0x557FA19C, pfs_donor 139, SpellTypes 0x27 like Recall Spirit / Animate Dead / Harvest Souls).  Its CreateCA
(VMT+0x78 0x557FA29C) builds a TRecallSpiritCA with [ca+0x18] = spell id, so everything below keys on [ca+0x18] == 209.

RE - vanilla Recall Spirit (id 0x81):  TRecallSpiritCA.Execute 0x557FA0D4 (eax = ca, edx = combat; push ebx/esi/edi ->
CA = [esp+8] inside):  edi = caster CU (0x55728C68([combat+0xC], [ca+0xC])), esi = target corpse CU ([ca+0xD]),
ebx = TUnit.Create(class [0x55710C6C] = TUnit), SetType(GetType(list [g+0x5C], 0x82 Spirit Puppet)), owner
VMT+0x16C(caster TUnit [+0x24]), ExpandAbility VMT+0x94(0x82 = TCombatResurrectedAbility "brought back from the dead"),
VMT+0x184, corpse CU VMT+0x134(new unit) (= the corpse's TCombatUnit now carries the new TUnit), clear the corpse's
destroyed bit ([cu+0x47] &= ~1), corpse CU VMT+0x68(caster side [+0x45]).  End of combat: 0x55724D44 (per CU, esi = CU)
sent dead units AND holders of 0x82 to 0x55724F16 (CU VMT-4 Free, dl = 1 = the unit is gone).  This mod changed both:
the puppet-type hook 0x557FA126 -> 0x5580D98D (rdtsc-picked puppet by corpse type) and 0x557FA149 -> 0x5580C6D2 (grants
Summoned 0x9B instead of 0x82 - raised units now PERSIST); the 0x82 removal at 0x55724D66 is NOPed (0x82 was briefly
repurposed as Hero Slaying - legacy map units may carry it).

Miracle = the same CA, with these caves in front (all other spell ids fall through to the current targets):
  A  0x557FA0E4 (10 B `cmp byte [ebx+0x14],0 / je 0x557FA191`):  209 -> refuse (end, nothing happens) unless the corpse
     CU is on the CASTER'S side ([cu+0x45]) and its TUnit is a plain TUnit (VMT == [0x55710C6C]; THero / TLeader derive
     from TAbstractUnit, not TUnit -> heroes and leaders are excluded, Resurrect / Animate Hero cover them).
  B  0x557FA126 (jmp -> 0x5580D98D):  209 -> edx = the corpse's own unit type id (0x5574D3C8([TUnit+0x40])) -> 0x557FA12B,
     i.e. the unit rises as ITSELF (a fresh copy of its type: base level, no medals/items).
  C  0x557FA149 (jmp -> 0x5580C6D2):  209 -> ExpandAbility(0x82) like vanilla (hover: "brought back from the dead";
     NOT Summoned 0x9B -> no upkeep, does not persist) + record the new TUnit in TAB -> 0x557FA158.
  D  0x557FA187 (10 B `mov dl,[edi+0x45] / mov eax,esi / mov ecx,[eax] / call [ecx+0x68]`): replay, then 209 ->
     HP := lo + RandInt(max - lo + 1), lo = ceil(30 % of max) (>= 1)   (TUnit VMT+0xD0 max / +0xE4 set),
     MP := RandInt(cap + 1) into [cu+0x5C] (cap = CU VMT+0x94 GetMoves - Second Wind's recipe).
     RandInt = 0x55701080, the generator ExecuteDamageRole rolls with -> deterministic in replays / LAN.
  E  0x55724D66 (the 6 NOPs after `HasAbility(0x82)`, al = result): al != 0 AND [cu+0x4C] listed in TAB -> 0x55724F16
     (gone at the end of combat, exactly vanilla's Recall Spirit fate); otherwise on (legacy 0x82 map units untouched).
  F  0x55724F16 (6 B `mov dl,1 / mov eax,esi / mov ecx,[eax]`, the shared "unit is gone" path - also every unit that
     died again): drop [cu+0x4C] from TAB, replay -> 0x55724F1C.
TAB = 16 x TUnit* at DATA zero-fill slack 0x558E9FC0..0x558EA000 (past Second Wind's 0x558E9F80 table; beyond raw DATA,
below BSS).  Insert: first empty slot, else slot (unit >> 4) & 15 (that unit would then survive - 16+ miracles per battle).
Zone AoWEPACK 0x5584E000..0x5584E400 (zero, no relocs): the first 8 bytes hold the previous B / C jmp targets (for
--revert).  PIC throughout (call/pop delta for TAB and the [0x55710C6C] class cell; rel32 inside the image).

v2 (2026-10-16, user: v1 raised a SPIRIT PUPPET; it must revive the ORIGINAL unit / hero, and never target living units):
ROOT CAUSE of the puppet - hooks B/C/D read the CA as [esp+8], but Execute pushes ebx BEFORE loading it (push ebx/esi/edi;
mov ebx,eax), so [esp+8] is the CALLER'S ebx, not the CA (and ebx itself becomes the new unit at 0x557FA11A).  The 209 test
in B/C/D therefore failed -> the mod's rdtsc puppet pick (0x5580D98D) + Summoned grant (0x5580C6D2) ran: a random,
persistent puppet.  v2 drops B/C/D (B/C back to their previous jmps, D to the vanilla bytes) and does EVERYTHING in A,
where ebx still is the CA:  corpse CU dead + on the caster's side + has a TUnit ->  [unit+0x25] &= ~0x10 (the 'killed'
flag TUnit.Killed's 0x5578087c sets); THero/TLeader (IsClass THero via its vmtSelfPtr cell 0x55711FAC): [hero+0x55] &= ~1
(THero.Killed's dead flag) and owner := [hero+0x5C] (the owner THero.Killed saved); plain units: owner := the caster's
player (Killed set -1).  SetOwner = VMT+0x16C.  HP := rand 30-100 % of max (VMT+0xD0 / +0xE4), CU status &= ~1
(SetStatus 0x557256BC), CU VMT+0x68(side) like Recall, MP := rand 0..GetMoves into [cu+0x5C]; the unit -> TAB.  TCPCK
0x4240AD then gives the alive CU a new unit HS (as for Recall's puppet).  No 0x82 grant (a later Resurrect Hero would keep
'brought back from the dead').  End of combat (E): a LIVING CU whose unit is in TAB -> unit VMT+0x1AC Killed again (the
call its first death made: dead flags, owner -1, out of its army, enchantments dropped; THero drops items again (none),
TLeader defers its defeat as before), SetHP 0, -> the shared 'unit gone' path F (drops it from TAB, frees the CU =
exactly what a dead unit gets).  A revived unit that dies again takes the normal dead path (DestroyObject -> Killed, F).
The script recognises the v1 / v2 builds and upgrades in place; --revert from v1, v2 or v3 restores the pre-Miracle bytes.
v3 (2026-10-16, user: a revived unit with Leadership no longer gave its party the bonus):  the first death's
TUnit.Killed (0x55782818 -> VMT+0x188 RemoveFromMap -> [unit+0x20] list VMT+0xB0 -> unit VMT+8 SetArmy(nil)) took the unit
OUT of its TArmy ([unit+4] := 0), and CU.Destroy's combat notification ran TCombatUnit.UpdateParty -> SetParty(nil).  v2
never put it back, so TArmy.UpdateFormation 0x5578D034 (iterates [army+8]) - the only place the Leadership aura is
computed - never saw it.  v3: after the side is restored, SetParty(cu, nil) 0x55725094 (clears a stale [cu+0x50]) then
UpdateParty(cu) 0x557250E0 -> SetParty(the combat party) -> unit.SetArmy([party+8]) (TArmy.Add 0x5578E810: re-places a
map army's unit on the map via VMT+0x184 and sets owner = army owner) + UpdateFormation (aura + '+N received' + the
[vmt+0x90] stat caches).  Dying again / the end-of-combat re-kill take it out again through the same Killed path.
Cursor / click refusal: patch_tc_miracle_target_v1.py (TCPCK).
Backup <game>\backup\AoWEPACK.dll.bak_miracle.  Dry-run default; --apply / --revert; --dll <copy> for scratch runs.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_miracle"
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5584E000, 0x5584E400
SPELL = 209
TAB, TAB_N = 0x558E9FC0, 16
GETCU, GETTYPEID, RANDINT, TUNIT_CELL = 0x55728C68, 0x5574D3C8, 0x55701080, 0x55710C6C
A_SITE, A_ORIG, A_GO, CA_END = 0x557FA0E4, bytes.fromhex("807b14000f84a3000000"), 0x557FA0EE, 0x557FA191
B_SITE, B_BACK = 0x557FA126, 0x557FA12B
C_SITE, C_BACK = 0x557FA149, 0x557FA158
D_SITE, D_ORIG = 0x557FA187, bytes.fromhex("8a57458bc68b08ff5168")
E_SITE, E_ORIG, E_BACK = 0x55724D66, b"\x90" * 6, 0x55724D6C
F_SITE, F_ORIG, F_BACK = 0x55724F16, bytes.fromhex("b2018bc68b08"), 0x55724F1C
ABIL_RES = 0x82
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build_v1(prev_b, prev_c):
    out = bytearray(struct.pack("<II", prev_b, prev_c)); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    pic = lambda reg, lbl: "    call %s\n%s:\n    pop %s\n    sub %s, %s\n" % (lbl, lbl, reg, reg, lbl)
    place("A", """
        cmp byte ptr [ebx + 0x14], 0
        je a_end
        cmp dword ptr [ebx + 0x18], %(spell)d
        jne a_go
        push edi
        push esi
        movzx edx, byte ptr [ebx + 0xc]
        mov eax, [esi + 0xc]
        call %(getcu)#x
        mov edi, eax
        movzx edx, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(getcu)#x
        test eax, eax
        je a_fail
        test edi, edi
        je a_fail
        mov dl, byte ptr [eax + 0x45]
        cmp dl, byte ptr [edi + 0x45]
        jne a_fail
        mov eax, [eax + 0x4c]
        test eax, eax
        je a_fail
        mov eax, [eax]
%(pic)s        cmp eax, [ecx + %(cell)#x]
        jne a_fail
        pop esi
        pop edi
    a_go:
        jmp %(go)#x
    a_fail:
        pop esi
        pop edi
    a_end:
        jmp %(end)#x
    """ % {"spell": SPELL, "getcu": GETCU, "cell": TUNIT_CELL, "go": A_GO, "end": CA_END, "pic": pic("ecx", "a_d")})
    place("B", """
        mov ecx, [esp + 8]
        cmp dword ptr [ecx + 0x18], %(spell)d
        jne b_prev
        push eax
        mov eax, [esi + 0x4c]
        mov eax, [eax + 0x40]
        call %(tid)#x
        mov edx, eax
        pop eax
        jmp %(back)#x
    b_prev:
        jmp %(prev)#x
    """ % {"spell": SPELL, "tid": GETTYPEID, "back": B_BACK, "prev": prev_b})
    place("C", """
        mov ecx, [esp + 8]
        cmp dword ptr [ecx + 0x18], %(spell)d
        jne c_prev
        mov edx, %(ab)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    c_l:
        mov eax, [ecx + edx*4]
        cmp eax, ebx
        je c_done
        test eax, eax
        je c_put
        inc edx
        cmp edx, %(n)d
        jb c_l
        mov edx, ebx
        shr edx, 4
        and edx, %(m)d
    c_put:
        mov [ecx + edx*4], ebx
    c_done:
        jmp %(back)#x
    c_prev:
        jmp %(prev)#x
    """ % {"spell": SPELL, "ab": ABIL_RES, "tab": TAB, "n": TAB_N, "m": TAB_N - 1, "back": C_BACK, "prev": prev_c,
           "pic": pic("ecx", "c_d")})
    place("D", """
        mov dl, byte ptr [edi + 0x45]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x68]
        mov ecx, [esp + 8]
        cmp dword ptr [ecx + 0x18], %(spell)d
        jne d_end
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0xd0]
        movsx edi, al
        test edi, edi
        jle d_mp
        lea eax, [edi + edi*2 + 9]
        mov ecx, 10
        cdq
        idiv ecx
        test eax, eax
        jg d_lo
        mov eax, 1
    d_lo:
        cmp eax, edi
        jle d_lo2
        mov eax, edi
    d_lo2:
        push eax
        mov eax, edi
        sub eax, [esp]
        inc eax
        call %(rnd)#x
        pop edx
        add edx, eax
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xe4]
    d_mp:
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x94]
        test eax, eax
        jg d_mp2
        xor eax, eax
        mov [esi + 0x5c], eax
        jmp d_end
    d_mp2:
        inc eax
        call %(rnd)#x
        mov [esi + 0x5c], eax
    d_end:
        jmp %(end)#x
    """ % {"spell": SPELL, "rnd": RANDINT, "end": CA_END})
    place("E", """
        test al, al
        je e_back
        mov eax, [esi + 0x4c]
        test eax, eax
        je e_back
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    e_l:
        cmp [ecx + edx*4], eax
        je e_gone
        inc edx
        cmp edx, %(n)d
        jb e_l
    e_back:
        jmp %(back)#x
    e_gone:
        jmp %(gone)#x
    """ % {"tab": TAB, "n": TAB_N, "back": E_BACK, "gone": F_SITE, "pic": pic("ecx", "e_d")})
    place("F", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je f_rep
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    f_l:
        cmp [ecx + edx*4], eax
        jne f_n
        mov dword ptr [ecx + edx*4], 0
    f_n:
        inc edx
        cmp edx, %(n)d
        jb f_l
    f_rep:
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        jmp %(back)#x
    """ % {"tab": TAB, "n": TAB_N, "back": F_BACK, "pic": pic("ecx", "f_d")})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where



HERO_SELF = 0x55711FAC          # THero vmtSelfPtr cell (holds the THero VMT, reloc-fixed) -> IsClass arg (TLeader derives THero)
ISCLASS = 0x557010C0            # System.IsClass(eax obj, edx class) -> al
SETSTATUS = 0x557256BC          # TCombatUnit.SetStatus(eax cu, dl status)
SETPARTY = 0x55725094           # TCombatUnit.SetParty(eax cu, edx party): [cu+0x50] := party; unit.SetArmy([party+8]) (VMT+8) + TArmy.UpdateFormation
UPDPARTY = 0x557250E0           # TCombatUnit.UpdateParty(eax cu): active + alive + side matches -> SetParty(the combat party for [cu+0x46]>>4) else nil


def build_v2(prev_b, prev_c):
    """v2 (2026-10-16): Miracle revives the corpse's OWN unit (heroes / leaders included) instead of building a new one."""
    out = bytearray(struct.pack("<II", prev_b, prev_c)); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    pic = lambda reg, lbl: "    call %s\n%s:\n    pop %s\n    sub %s, %s\n" % (lbl, lbl, reg, reg, lbl)
    # A: ebx = CA (+0xC caster idx, +0xD corpse idx, +0x14 corpse-was-dead, +0x18 spell id), esi = combat.  Other spells ->
    # the vanilla body (0x557FA0EE).  209 -> revive the corpse's own unit in place, then the CA epilogue (0x557FA191 pops
    # edi/esi/ebx, so they are free here).
    place("A", """
        cmp byte ptr [ebx + 0x14], 0
        je a_end
        cmp dword ptr [ebx + 0x18], %(spell)d
        je a_mine
        jmp %(go)#x
    a_mine:
        movzx edx, byte ptr [ebx + 0xc]
        mov eax, [esi + 0xc]
        call %(getcu)#x
        mov edi, eax
        movzx edx, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(getcu)#x
        mov esi, eax
        test esi, esi
        je a_end
        test edi, edi
        je a_end
        test byte ptr [esi + 0x47], 1
        je a_end
        mov al, byte ptr [esi + 0x45]
        cmp al, byte ptr [edi + 0x45]
        jne a_end
        mov ebx, [esi + 0x4c]
        test ebx, ebx
        je a_end
        mov eax, [edi + 0x4c]
        test eax, eax
        je a_end
        and byte ptr [ebx + 0x25], 0xef
%(pic)s        mov edx, [ecx + %(heroself)#x]
        mov eax, ebx
        call %(isclass)#x
        test al, al
        je a_owner_caster
        and byte ptr [ebx + 0x55], 0xfe
        mov dl, byte ptr [ebx + 0x5c]
        jmp a_owner
    a_owner_caster:
        mov eax, [edi + 0x4c]
        mov dl, byte ptr [eax + 0x24]
    a_owner:
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x16c]
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0xd0]
        movsx ecx, al
        test ecx, ecx
        jg a_hp
        mov ecx, 1
    a_hp:
        push ecx
        lea eax, [ecx + ecx*2 + 9]
        push ecx
        mov ecx, 10
        cdq
        idiv ecx
        pop ecx
        test eax, eax
        jg a_lo
        mov eax, 1
    a_lo:
        cmp eax, ecx
        jle a_lo2
        mov eax, ecx
    a_lo2:
        push eax
        mov eax, ecx
        sub eax, [esp]
        inc eax
        call %(rnd)#x
        pop edx
        add edx, eax
        pop ecx
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xe4]
        mov dl, byte ptr [esi + 0x47]
        and dl, 0xfe
        mov eax, esi
        call %(setstatus)#x
        mov dl, byte ptr [edi + 0x45]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x68]
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x94]
        test eax, eax
        jg a_mp
        xor eax, eax
        mov [esi + 0x5c], eax
        jmp a_tab
    a_mp:
        inc eax
        call %(rnd)#x
        mov [esi + 0x5c], eax
    a_tab:
%(pic2)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    a_l:
        mov eax, [ecx + edx*4]
        cmp eax, ebx
        je a_end
        test eax, eax
        je a_put
        inc edx
        cmp edx, %(n)d
        jb a_l
        mov edx, ebx
        shr edx, 4
        and edx, %(m)d
    a_put:
        mov [ecx + edx*4], ebx
    a_end:
        jmp %(end)#x
    """ % {"spell": SPELL, "getcu": GETCU, "go": A_GO, "end": CA_END, "heroself": HERO_SELF, "isclass": ISCLASS,
           "rnd": RANDINT, "setstatus": SETSTATUS, "tab": TAB, "n": TAB_N, "m": TAB_N - 1,
           "pic": pic("ecx", "a_d"), "pic2": pic("ecx", "a_d2")})
    # E: end of combat, a LIVING CU (dead ones already left via 0x55724F16).  A unit revived by Miracle (in TAB) dies again:
    # unit VMT+0x1AC Killed (the same call its first death made - dead flags, owner -1, out of its army, enchantments
    # dropped; the THero / TLeader overrides included), HP 0, then the shared 'unit gone' path (F drops it from TAB).
    place("E", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je e_back
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    e_l:
        cmp [ecx + edx*4], eax
        je e_kill
        inc edx
        cmp edx, %(n)d
        jb e_l
    e_back:
        jmp %(back)#x
    e_kill:
        mov edx, [eax]
        call dword ptr [edx + 0x1ac]
        xor edx, edx
        mov eax, [esi + 0x4c]
        mov ecx, [eax]
        call dword ptr [ecx + 0xe4]
        jmp %(gone)#x
    """ % {"tab": TAB, "n": TAB_N, "back": E_BACK, "gone": F_SITE, "pic": pic("ecx", "e_d")})
    place("F", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je f_rep
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    f_l:
        cmp [ecx + edx*4], eax
        jne f_n
        mov dword ptr [ecx + edx*4], 0
    f_n:
        inc edx
        cmp edx, %(n)d
        jb f_l
    f_rep:
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        jmp %(back)#x
    """ % {"tab": TAB, "n": TAB_N, "back": F_BACK, "pic": pic("ecx", "f_d")})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where



def build(prev_b, prev_c):
    """v3 (2026-10-16): v2 + the revived unit re-joins its party (TArmy) -> Leadership aura / formation recomputed."""
    out = bytearray(struct.pack("<II", prev_b, prev_c)); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    pic = lambda reg, lbl: "    call %s\n%s:\n    pop %s\n    sub %s, %s\n" % (lbl, lbl, reg, reg, lbl)
    # A: ebx = CA (+0xC caster idx, +0xD corpse idx, +0x14 corpse-was-dead, +0x18 spell id), esi = combat.  Other spells ->
    # the vanilla body (0x557FA0EE).  209 -> revive the corpse's own unit in place, then the CA epilogue (0x557FA191 pops
    # edi/esi/ebx, so they are free here).
    place("A", """
        cmp byte ptr [ebx + 0x14], 0
        je a_end
        cmp dword ptr [ebx + 0x18], %(spell)d
        je a_mine
        jmp %(go)#x
    a_mine:
        movzx edx, byte ptr [ebx + 0xc]
        mov eax, [esi + 0xc]
        call %(getcu)#x
        mov edi, eax
        movzx edx, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(getcu)#x
        mov esi, eax
        test esi, esi
        je a_end
        test edi, edi
        je a_end
        test byte ptr [esi + 0x47], 1
        je a_end
        mov al, byte ptr [esi + 0x45]
        cmp al, byte ptr [edi + 0x45]
        jne a_end
        mov ebx, [esi + 0x4c]
        test ebx, ebx
        je a_end
        mov eax, [edi + 0x4c]
        test eax, eax
        je a_end
        and byte ptr [ebx + 0x25], 0xef
%(pic)s        mov edx, [ecx + %(heroself)#x]
        mov eax, ebx
        call %(isclass)#x
        test al, al
        je a_owner_caster
        and byte ptr [ebx + 0x55], 0xfe
        mov dl, byte ptr [ebx + 0x5c]
        jmp a_owner
    a_owner_caster:
        mov eax, [edi + 0x4c]
        mov dl, byte ptr [eax + 0x24]
    a_owner:
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x16c]
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0xd0]
        movsx ecx, al
        test ecx, ecx
        jg a_hp
        mov ecx, 1
    a_hp:
        push ecx
        lea eax, [ecx + ecx*2 + 9]
        push ecx
        mov ecx, 10
        cdq
        idiv ecx
        pop ecx
        test eax, eax
        jg a_lo
        mov eax, 1
    a_lo:
        cmp eax, ecx
        jle a_lo2
        mov eax, ecx
    a_lo2:
        push eax
        mov eax, ecx
        sub eax, [esp]
        inc eax
        call %(rnd)#x
        pop edx
        add edx, eax
        pop ecx
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xe4]
        mov dl, byte ptr [esi + 0x47]
        and dl, 0xfe
        mov eax, esi
        call %(setstatus)#x
        mov dl, byte ptr [edi + 0x45]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x68]
        xor edx, edx
        mov eax, esi
        call %(setparty)#x
        mov eax, esi
        call %(updparty)#x
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x94]
        test eax, eax
        jg a_mp
        xor eax, eax
        mov [esi + 0x5c], eax
        jmp a_tab
    a_mp:
        inc eax
        call %(rnd)#x
        mov [esi + 0x5c], eax
    a_tab:
%(pic2)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    a_l:
        mov eax, [ecx + edx*4]
        cmp eax, ebx
        je a_end
        test eax, eax
        je a_put
        inc edx
        cmp edx, %(n)d
        jb a_l
        mov edx, ebx
        shr edx, 4
        and edx, %(m)d
    a_put:
        mov [ecx + edx*4], ebx
    a_end:
        jmp %(end)#x
    """ % {"spell": SPELL, "getcu": GETCU, "go": A_GO, "end": CA_END, "heroself": HERO_SELF, "isclass": ISCLASS,
           "rnd": RANDINT, "setstatus": SETSTATUS, "setparty": SETPARTY, "updparty": UPDPARTY, "tab": TAB, "n": TAB_N, "m": TAB_N - 1,
           "pic": pic("ecx", "a_d"), "pic2": pic("ecx", "a_d2")})
    # E: end of combat, a LIVING CU (dead ones already left via 0x55724F16).  A unit revived by Miracle (in TAB) dies again:
    # unit VMT+0x1AC Killed (the same call its first death made - dead flags, owner -1, out of its army, enchantments
    # dropped; the THero / TLeader overrides included), HP 0, then the shared 'unit gone' path (F drops it from TAB).
    place("E", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je e_back
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    e_l:
        cmp [ecx + edx*4], eax
        je e_kill
        inc edx
        cmp edx, %(n)d
        jb e_l
    e_back:
        jmp %(back)#x
    e_kill:
        mov edx, [eax]
        call dword ptr [edx + 0x1ac]
        xor edx, edx
        mov eax, [esi + 0x4c]
        mov ecx, [eax]
        call dword ptr [ecx + 0xe4]
        jmp %(gone)#x
    """ % {"tab": TAB, "n": TAB_N, "back": E_BACK, "gone": F_SITE, "pic": pic("ecx", "e_d")})
    place("F", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je f_rep
%(pic)s        lea ecx, [ecx + %(tab)#x]
        xor edx, edx
    f_l:
        cmp [ecx + edx*4], eax
        jne f_n
        mov dword ptr [ecx + edx*4], 0
    f_n:
        inc edx
        cmp edx, %(n)d
        jb f_l
    f_rep:
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        jmp %(back)#x
    """ % {"tab": TAB, "n": TAB_N, "back": F_BACK, "pic": pic("ecx", "f_d")})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def rel(op, va, target, size):
    return bytes([op]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    jt = lambda va: va + 5 + struct.unpack_from("<i", g(va, 5), 1)[0] if g(va, 1) == b"\xE9" else None
    zl = d[ZONE - V2F:ZONE_END - V2F]
    inzone = lambda va: va is not None and ZONE <= va < ZONE_END
    zero = not any(zl)
    cur_b, cur_c = jt(B_SITE), jt(C_SITE)
    assert cur_b and cur_c, "Recall Spirit CA sites are not jmp-hooked as expected: %s %s" % (g(B_SITE, 5).hex(), g(C_SITE, 5).hex())
    prev_b, prev_c = (cur_b, cur_c) if zero else struct.unpack_from("<II", zl, 0)
    z1, w1 = build_v1(prev_b, prev_c)
    zv2, wv2 = build_v2(prev_b, prev_c)
    z2, w2 = build(prev_b, prev_c)                                   # v3 = the current build (names kept: z2/w2/want2 = 'wanted')
    fits = lambda z: zl[:len(z)] == z and not any(zl[len(z):])
    zstate = "zero" if zero else "v3" if fits(z2) else "v2" if fits(zv2) else "v1" if fits(z1) else "DIFFERS"
    ORIG = {"A": A_ORIG, "D": D_ORIG, "E": E_ORIG, "F": F_ORIG}
    SITES = [("A", A_SITE, 10), ("B", B_SITE, 5), ("C", C_SITE, 5), ("D", D_SITE, 10), ("E", E_SITE, 6), ("F", F_SITE, 6)]
    base = {k: (ORIG[k] if k in ORIG else rel(0xE9, va, prev_b if k == "B" else prev_c, n)) for k, va, n in SITES}
    want2 = {k: (rel(0xE9, va, w2[k], n) if k in w2 else base[k]) for k, va, n in SITES}
    want1 = {k: rel(0xE9, va, w1[k], n) for k, va, n in SITES}
    wantv2 = {k: (rel(0xE9, va, wv2[k], n) if k in wv2 else base[k]) for k, va, n in SITES}
    st = {}
    for k, va, n in SITES:
        cur = g(va, n)
        st[k] = ("v3" if k in w2 and cur == want2[k] else "v2" if k in wv2 and cur == wantv2[k] else "v1" if cur == want1[k] else "base" if cur == base[k]
                 else "prev" if k in ("B", "C") and not inzone(jt(va)) else "OTHER(%s)" % cur.hex())
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _k, va, n in SITES)]
    print("sites %s | prev B -> %#x, C -> %#x | zone %s (v3 %d B) | relocs %s | v3 caves %s"
          % (st, prev_b, prev_c, zstate, len(z2), bad or "none", ", ".join("%s=%#x" % kv for kv in w2.items())))
    if bad or zstate == "DIFFERS" or any(v.startswith("OTHER") for v in st.values()): print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(z2[8:], ZONE + 8): print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    out = bytearray(d)
    if a.revert:
        if zstate == "zero" and all(v in ("base", "prev") for v in st.values()): print("nothing to revert"); return 0
        for k, va, n in SITES: out[va - V2F:va - V2F + n] = base[k]
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (B -> %#x, C -> %#x)" % (prev_b, prev_c)); return 0
    if zstate == "v3" and all(g(va, n) == want2[k] for k, va, n in SITES): print("already applied"); return 0
    if zstate == "v1": print("v1 build found -> upgrading to v3 (B/C back to their previous hooks, D restored)")
    if zstate == "v2": print("v2 build found -> upgrading to v3 (revived unit re-joins its party)")
    out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - V2F:ZONE - V2F + len(z2)] = z2
    for k, va, n in SITES: out[va - V2F:va - V2F + n] = want2[k]
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll == DEFAULT_DLL:
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
