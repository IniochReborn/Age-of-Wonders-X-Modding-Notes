r"""
AI END-OF-TURN UNIT ENCHANTMENTS v2 (strategic map), 2026-10-19.  AoWEPACK.dll only.  In-place upgrade of
patch_ai_end_enchant_v1.py (same slot, same zone, same per-player day table, same PR cave; FIND rewritten).

User (on v1): "(1) a caster can enchant units outside its own party (12-hex range if I recall).  Add this for AI casters,
but at lower priority than own party.  (2) Sometimes the AI likes to cast expensive global spells (summoning level-4
units, level-4 mastery spells etc).  I don't want this to be lost, as those really help the AI."

RE (1) - the human rule, vanilla:
  * TUnitSpell.SetupTargetSelection 0x5577B014: [sel+0xD] |= 8, and when the spell's dword [spell+0x38] != -1 also |= 4
    with [sel+0x20] = [spell+0x38] (the RANGE) and [sel+0x24/+0x28] = the caster's location (TAbstractUnit.GetLocation
    0x5577ED94).  TTargetSelectionControl.ValidTarget 0x55763338: flag 4 -> HSEngine.dHXtoRad(caster x,y, target x,y)
    <= range; flag 2 (same level) is NOT set for unit spells -> the range is 2-D, any level.  TUnitSpell.OnValidateTarget
    0x5577AE80 then wants the hex explored (0x557759F8) and, for foreign armies, no Magic Shield.
  * The cast TE re-checks it: TUnitSpellTE.Validate 0x5577AA1C - every target alive (+0xE0), owner [unit+0x24] ==
    [te+0x28] (OWN units only; no allies on the world map) and, when [spell+0x38] != -1, dHXtoRad(caster, target) <=
    [spell+0x38].  So "range" = the spell's own [spell+0x38] (Remedy 12; -1 = unlimited), measured from the caster.
  v2: after nothing in the caster's OWN party qualifies (phases 0/1, = v1), phases 2/3 scan every other army of the
  player ([player+0x28] TArmyList, TArmyList.GetArmy 0x55750808) for own units within [spell+0x38] of the caster
  (dHXtoRad, any level; -1 = anywhere) - the leader's party first (bias 0x40000000; the leader himself 0x7FFFFFFF),
  then the strongest unit (all-kinds strength).  Same casters, same spell rules, same TE (Validate accepts it).

RE (2) - how the vanilla AI pays for big globals:
  * TCastSpellAIPA (priority 0x17) runs BEFORE TEndTurnAIPA (0x0A, last), so it always gets first pick of casting
    points and mana each turn; v1 only ever touched what was left over.
  * Its mana gate = TSpell.AIRequestCastSpellExpense 0x557796E4 -> TAIBudgetManager.RequestBudgetExpenseEx 0x55736C5C:
    the free mana pool [mgr+0x34] (player mana minus group/budget reservations, UpdateBudgets 0x55736900) plus the
    savings budget [mgr+0x38] (TAISavingsBudget, created on msg 0x20000008: target 150, +15 mana a day).  There is no
    per-spell plan - a big spell happens when enough unspent mana has piled up (and the caster channels it over
    several turns, [hero+0x84] = spell id, mana booked when it completes).
  * v1's floor (keep 50 % of the mana held at the start of the day) still let mana HALVE every day, so a 60-75 mana
    tier-4 global (Ice Age 75, Nimue's Favour 60 ...) might never be reached.
  v2 protection (simple, deterministic, game state only):
    a) while ANY of the player's casters (leader or hero) is channelling a spell ([hero+0x84] != 0) - nothing is
       cast by this pass (the AI is mid-way through something bigger);
    b) SAVINGS TARGET S = the highest mana cost [spell+0x14] among the player's known non-unit spells (not a
       TUnitSpell: globals, masteries, summons, city/terrain spells) with AI priority != -1, from the SAME list the vanilla
       AI chooses from (TPlayerMagicControl.ListSpells mask 6 = book types 1/2 [spell+0x22]), that is reachable within N_TURNS (6) turns: cost <= mana + 6 x max(net income, 0).  The
       pass may only spend mana ABOVE S (floor = max(v1 floor, S)); a spell out of reach within 6 turns does not block
       (so a far-off 750-cost spell can't freeze enchanting forever, the next reachable one counts instead);
    c) upkeep: a new enchantment's upkeep must be <= half the current net mana income (v1: <= net income), so at
       least half the income keeps flowing into savings; each later call recomputes net income after the new upkeep.
  Numbers (6-turn window): mana 40, net +10, best global 75 -> 75 <= 40+60 -> S 75 -> floor 75 > 40 -> no enchant;
  mana 120 -> floor max(60, 75) = 75 -> may spend 45.  Mana 40, net +3, best 75 (> 40+18) -> next reachable (e.g. a
  summon at 30) -> floor max(20, 30) = 30 -> may spend 10.

Dry-run default; --apply / --revert / --dis / --dll <scratch>.  Upgrades v1 in place; --revert = vanilla (exactly what
v1 --revert gives).  Backup <game>\backup\AoWEPACK.dll.bak_aiendench2.  patch_ai_site_recruit_v1.py ZONE_END must be
0x5581D400 (as for v1).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_end_enchant_v1 as V1
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V1.BASE, V1.V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"AEN2"
H_DELTA, PR, FIND = V1.H_DELTA, V1.PR, V1.FIND
SLOT, ORIG_PROC = V1.SLOT, V1.ORIG_PROC
N_TURNS, UPK_DIV = 6, 2
GETARMY, GETLOC, HXRAD = 0x55750808, 0x5577ED94, 0x5570266C   # TArmyList.GetArmy / TAbstractUnit.GetLocation / dHXtoRad thunk

# FIND: eax = player, edx = mana floor (v1: RES % of start mana), ecx = delta -> eax spell, edx caster, ecx target unit.
# locals: -4 player -8 floor -0xc delta -0x10 spelllist -0x14 leader army -0x18 leader -0x1c phase -0x20 best spell
# -0x24 best caster -0x28 best ukey -0x2c caster idx -0x30 hero count -0x34 best skey -0x38 spell idx -0x3c spell count
# -0x40 keep CP -0x44 caster CP -0x48 lstr -0x4c best unit -0x50 unit idx -0x54 mana -0x58 net -0x5c unit count
# -0x60 skey -0x64 unit -0x68 ValidTarget -0x6c army idx -0x70 army count -0x74 army -0x78 range -0x7c caster loc (3 B)
# -0x80 target loc (3 B) -0x84 S / temp -0x88 limit -0x8c bias
SRC_FIND = """
    push ebp
    mov  ebp, esp
    sub  esp, 0x90
    push ebx
    push esi
    push edi
    mov  [ebp-4], eax
    mov  [ebp-8], edx
    mov  [ebp-0xc], ecx
    xor  eax, eax
    mov  [ebp-0x20], eax
    mov  [ebp-0x24], eax
    mov  [ebp-0x34], eax
    mov  [ebp-0x48], eax
    mov  [ebp-0x4c], eax
    mov  [ebp-0x10], eax
    mov  [ebp-0x84], eax
    mov  dword ptr [ebp-0x28], -1
    mov  ebx, [ebp-4]
    mov  eax, [ebx+0xd4]
    test eax, eax
    jz   f_nl
    mov  eax, [eax+4]
f_nl:
    mov  [ebp-0x18], eax
    xor  edx, edx
    test eax, eax
    jz   f_la
    mov  edx, [eax+4]
f_la:
    mov  [ebp-0x14], edx
    mov  eax, [ebx+0x54]
    mov  eax, [eax+0x24]
    mov  [ebp-0x54], eax
    mov  eax, [ebx+0x54]
    call {MINC}
    mov  [ebp-0x58], eax
    mov  eax, [ebx+0x54]
    call {MUPK}
    sub  [ebp-0x58], eax
    mov  ecx, [ebp-0xc]
    mov  eax, [ecx+{CSL}]
    mov  dl, 1
    call {SLC}
    mov  [ebp-0x10], eax
    lea  edx, [ebp-0x10]
    mov  eax, [ebx+0x54]
    mov  cl, {MASK}
    call {LSP}
    mov  eax, [ebp-0x10]
    call {SLN}
    mov  [ebp-0x3c], eax
    xor  edx, edx
    mov  eax, [ebx+0x80]
    test eax, eax
    jz   f_hc
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  edx, eax
f_hc:
    mov  [ebp-0x30], edx
    mov  eax, [ebp-0x18]
    test eax, eax
    jz   f_ch0
    cmp  dword ptr [eax+0x84], 0
    jne  f_done
f_ch0:
    mov  dword ptr [ebp-0x2c], 0
f_chl:
    mov  edx, [ebp-0x2c]
    cmp  edx, [ebp-0x30]
    jge  f_chd
    mov  eax, [ebx+0x80]
    call {GH}
    test eax, eax
    jz   f_chn
    cmp  dword ptr [eax+0x84], 0
    jne  f_done
f_chn:
    inc  dword ptr [ebp-0x2c]
    jmp  f_chl
f_chd:
    mov  eax, [ebp-0x58]
    test eax, eax
    jge  f_lp
    xor  eax, eax
f_lp:
    imul eax, eax, {NT}
    add  eax, [ebp-0x54]
    mov  [ebp-0x88], eax
    mov  dword ptr [ebp-0x38], 0
f_sl:
    mov  eax, [ebp-0x38]
    cmp  eax, [ebp-0x3c]
    jge  f_sd
    mov  edx, eax
    mov  eax, [ebp-0x10]
    call {SLG}
    test eax, eax
    jz   f_sn
    mov  edi, eax
    mov  ecx, [ebp-0xc]
    mov  edx, [ecx+{CUS}]
    call {IC}
    test al, al
    jnz  f_sn
    cmp  dword ptr [edi+0x40], -1
    je   f_sn
    mov  eax, [edi+0x14]
    test eax, eax
    jle  f_sn
    cmp  eax, [ebp-0x88]
    jg   f_sn
    cmp  eax, [ebp-0x84]
    jle  f_sn
    mov  [ebp-0x84], eax
f_sn:
    inc  dword ptr [ebp-0x38]
    jmp  f_sl
f_sd:
    mov  eax, [ebp-0x84]
    cmp  eax, [ebp-8]
    jle  f_s2
    mov  [ebp-8], eax
f_s2:
    mov  dword ptr [ebp-0x1c], 0
f_phase:
    mov  dword ptr [ebp-0x2c], -1
f_caster:
    mov  eax, [ebp-0x2c]
    cmp  eax, -1
    jne  f_hero
    mov  eax, [ebp-0x18]
    jmp  f_gotc
f_hero:
    cmp  eax, [ebp-0x30]
    jge  f_pend
    mov  edx, eax
    mov  eax, [ebx+0x80]
    call {GH}
    cmp  eax, [ebp-0x18]
    je   f_cnext
f_gotc:
    test eax, eax
    jz   f_cnext
    mov  esi, eax
    mov  eax, [esi+4]
    test eax, eax
    jz   f_cnext
    mov  ecx, [ebp-0x14]
    test dword ptr [ebp-0x1c], 1
    jnz  f_ph1
    test ecx, ecx
    jz   f_cnext
    cmp  eax, ecx
    jne  f_cnext
    jmp  f_phok
f_ph1:
    test ecx, ecx
    jz   f_phok
    cmp  eax, ecx
    je   f_cnext
f_phok:
    mov  ecx, [ebp-0xc]
    mov  edx, [ecx+{CAR}]
    mov  eax, [esi+4]
    call {IC}
    test al, al
    jz   f_cnext
    cmp  dword ptr [esi+0x84], 0
    jne  f_cnext
    test byte ptr [esi+0x25], 0x10
    jnz  f_cnext
    mov  eax, esi
    mov  edx, 0x34
    mov  ecx, [eax]
    call dword ptr [ecx+0x148]
    test al, al
    jz   f_cnext
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x128]
    movsx eax, al
    test eax, eax
    jle  f_cnext
    imul eax, eax, {KEEP}
    cdq
    mov  ecx, 100
    idiv ecx
    mov  [ebp-0x40], eax
    movsx eax, byte ptr [esi+0x80]
    mov  [ebp-0x44], eax
    cmp  dword ptr [ebp-0x1c], 2
    jl   f_noloc
    lea  eax, [ebp-0x7a]
    push eax
    lea  ecx, [ebp-0x7b]
    lea  edx, [ebp-0x7c]
    mov  eax, esi
    call {GL}
f_noloc:
    mov  dword ptr [ebp-0x38], 0
f_spell:
    mov  eax, [ebp-0x38]
    cmp  eax, [ebp-0x3c]
    jge  f_cnext
    mov  edx, eax
    mov  eax, [ebp-0x10]
    call {SLG}
    test eax, eax
    jz   f_snext
    mov  edi, eax
    mov  ecx, [ebp-0xc]
    mov  edx, [ecx+{CUS}]
    call {IC}
    test al, al
    jz   f_snext
    cmp  dword ptr [edi+0x40], -1
    je   f_snext
    mov  eax, [edi+0x1c]
    {UPK_TEST}
    mov  eax, esi
    mov  edx, edi
    call {CM}
    mov  ecx, [ebp-0x44]
    sub  ecx, eax
    cmp  ecx, [ebp-0x40]
    jl   f_snext
    mov  ecx, [ebp-0x54]
    sub  ecx, eax
    cmp  ecx, [ebp-8]
    jl   f_snext
    lea  eax, [ebp-0x48]
    push eax
    mov  ecx, [edi+0x14]
    mov  edx, [edi+0x10]
    mov  eax, esi
    call {CI}
    push eax
    lea  eax, [ebp-0x48]
    call {LSC}
    pop  eax
    test al, al
    jz   f_snext
    movzx eax, byte ptr [edi+0x21]
    shl  eax, 16
    mov  ecx, [edi+0x14]
    and  ecx, 0xffff
    or   eax, ecx
    mov  [ebp-0x60], eax
    mov  eax, [edi]
    mov  eax, [eax+0x9c]
    mov  [ebp-0x68], eax
    mov  eax, [edi+0x38]
    mov  [ebp-0x78], eax
    cmp  dword ptr [ebp-0x1c], 2
    jge  f_far
    mov  eax, [esi+4]
    mov  [ebp-0x74], eax
    mov  dword ptr [ebp-0x8c], 0
    call f_army
    jmp  f_snext
f_far:
    mov  eax, [ebx+0x28]
    test eax, eax
    jz   f_snext
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  [ebp-0x70], eax
    mov  dword ptr [ebp-0x6c], 0
f_al:
    mov  edx, [ebp-0x6c]
    cmp  edx, [ebp-0x70]
    jge  f_snext
    mov  eax, [ebx+0x28]
    call {GA}
    test eax, eax
    jz   f_an
    cmp  eax, [esi+4]
    je   f_an
    mov  [ebp-0x74], eax
    xor  ecx, ecx
    cmp  eax, [ebp-0x14]
    jne  f_ab
    mov  ecx, 0x40000000
f_ab:
    mov  [ebp-0x8c], ecx
    call f_army
f_an:
    inc  dword ptr [ebp-0x6c]
    jmp  f_al
f_snext:
    inc  dword ptr [ebp-0x38]
    jmp  f_spell
f_cnext:
    inc  dword ptr [ebp-0x2c]
    jmp  f_caster
f_pend:
    cmp  dword ptr [ebp-0x20], 0
    jne  f_done
    inc  dword ptr [ebp-0x1c]
    cmp  dword ptr [ebp-0x1c], 4
    jl   f_phase
f_done:
    mov  eax, [ebp-0x10]
    call {OF}
    mov  eax, [ebp-0x20]
    mov  edx, [ebp-0x24]
    mov  ecx, [ebp-0x4c]
    pop  edi
    pop  esi
    pop  ebx
    mov  esp, ebp
    pop  ebp
    ret

f_army:
    mov  eax, [ebp-0x74]
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  [ebp-0x5c], eax
    mov  dword ptr [ebp-0x50], 0
f_unit:
    mov  eax, [ebp-0x50]
    cmp  eax, [ebp-0x5c]
    jge  f_ar
    mov  edx, eax
    mov  eax, [ebp-0x74]
    call {GU}
    test eax, eax
    jz   f_unext
    mov  [ebp-0x64], eax
    cmp  dword ptr [ebp-0x1c], 2
    jl   f_vt
    mov  cl, byte ptr [eax+0x24]
    cmp  cl, byte ptr [ebx+0xa6]
    jne  f_unext
    cmp  dword ptr [ebp-0x78], -1
    je   f_vt
    lea  ecx, [ebp-0x7e]
    push ecx
    lea  ecx, [ebp-0x7f]
    lea  edx, [ebp-0x80]
    call {GL}
    movsx eax, byte ptr [ebp-0x7f]
    push eax
    movsx ecx, byte ptr [ebp-0x80]
    movsx edx, byte ptr [ebp-0x7b]
    movsx eax, byte ptr [ebp-0x7c]
    call {HX}
    cmp  eax, [ebp-0x78]
    jg   f_unext
f_vt:
    mov  ecx, [ebp-0x64]
    mov  edx, esi
    mov  eax, edi
    call dword ptr [ebp-0x68]
    test al, al
    jz   f_unext
    mov  eax, [ebp-0x64]
    mov  edx, [eax]
    call dword ptr [edx+0x114]
    cmp  al, 2
    je   f_unext
    mov  eax, [ebp-0x64]
    cmp  eax, [ebp-0x18]
    jne  f_str
    mov  eax, 0x7fffffff
    jmp  f_uk
f_str:
    mov  dx, 0xffff
    call {US}
    test eax, eax
    jge  f_s3
    xor  eax, eax
f_s3:
    cmp  eax, 0x3fffffff
    jbe  f_s4
    mov  eax, 0x3fffffff
f_s4:
    add  eax, [ebp-0x8c]
f_uk:
    cmp  eax, [ebp-0x28]
    jl   f_unext
    jg   f_take
    mov  ecx, [ebp-0x60]
    cmp  ecx, [ebp-0x34]
    jbe  f_unext
f_take:
    mov  [ebp-0x28], eax
    mov  eax, [ebp-0x60]
    mov  [ebp-0x34], eax
    mov  [ebp-0x20], edi
    mov  [ebp-0x24], esi
    mov  eax, [ebp-0x64]
    mov  [ebp-0x4c], eax
f_unext:
    inc  dword ptr [ebp-0x50]
    jmp  f_unit
f_ar:
    ret
"""


def upk_test():
    # eax = [spell+0x1C] upkeep.  REQUIRE_UPKEEP: lasting enchantments only; guard: upkeep <= net income / UPK_DIV.
    s = []
    if V1.REQUIRE_UPKEEP:
        s += ["test eax, eax", "jle  f_snext"]
    if V1.UPKEEP_GUARD:
        s += ["imul eax, eax, %d" % UPK_DIV, "cmp  eax, [ebp-0x58]", "jg   f_snext"]
    return "\n    ".join(s) or "nop"


def asm(src, at):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def build():
    hd = b"\xe8\x00\x00\x00\x00\x58\x2d" + struct.pack("<I", H_DELTA + 5) + b"\xc3"
    find_src = SRC_FIND.replace("{UPK_TEST}", upk_test())
    fnd = asm(find_src.format(MINC=V1.MANAINC, MUPK=V1.MANAUPK, CSL=V1.CLS_SPELLLIST, SLC=V1.SPELLLIST_CREATE,
                              MASK=V1.LIST_MASK, LSP=V1.LISTSPELLS, SLN=V1.SL_COUNT, GH=V1.GETHERO, CAR=V1.CLS_ARMY,
                              IC=V1.ISCLASS, KEEP=V1.KEEP_PCT, SLG=V1.SL_GET, CUS=V1.CLS_USPELL, CM=V1.CASTMANA,
                              CI=V1.CANINSTANT, LSC=V1.LSTRCLR, OF=V1.OBJFREE, GU=V1.GETUNIT, US=V1.USTRENGTH,
                              NT=N_TURNS, GL=GETLOC, GA=GETARMY, HX=HXRAD), FIND)
    pr = asm(V1.SRC_PR.format(HD=H_DELTA, NS=V1.NSLOT, TBL=V1.TABLE, MAP=V1.MAPCELL, MAXC=V1.MAXCASTS, RES=V1.RES_PCT,
                              FIND=FIND, ORIG=ORIG_PROC, EXPM=V1.EXPMADE, CTE=V1.CLS_USPELLTE, TEC=V1.TE_CREATE,
                              CM=V1.CASTMANA, TEI=V1.TE_INIT, ILA=V1.INTLIST_ADD, GTC=V1.GETTOKCTRL), PR)
    assert len(pr) <= FIND - PR, len(pr)
    zone = bytearray(FIND - ZONE + len(fnd))
    zone[0:4] = MAGIC
    zone[4:8] = struct.pack("<I", ORIG_PROC)
    for addr, blob in ((H_DELTA, hd), (PR, pr), (FIND, fnd)):
        zone[addr - ZONE:addr - ZONE + len(blob)] = blob
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return bytes(zone)


def zstate_of(zl, zone):
    if not any(zl): return "zero"
    if zl[:len(zone)] == zone and not any(zl[len(zone):]): return "v2"
    v1 = V1.build()
    if zl[:len(v1)] == v1 and not any(zl[len(v1):]): return "v1"
    return "DIFFERS"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = zstate_of(zl, zone)
    sv = struct.unpack_from("<I", d, SLOT - V2F)[0]
    sstate = "vanilla" if sv == ORIG_PROC else "ours" if sv == PR else "FOREIGN(%#x)" % sv
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END]
    rz = V1.recruit_zone_end()
    print("  TEndTurnAIPA.Process slot %#x: %s | zone %#x..%#x %s (v2 %d B, ends %#x) | relocs %s | recruit ZONE_END %s"
          % (SLOT, sstate, ZONE, ZONE_END, zstate, len(zone), ZONE + len(zone), bad or "none",
             "n/a" if rz is None else hex(rz)))
    print("  KEEP_PCT %d  RES_PCT %d  MAXCASTS %d  N_TURNS %d  UPK_DIV %d" % (V1.KEEP_PCT, V1.RES_PCT, V1.MAXCASTS,
                                                                           N_TURNS, UPK_DIV))
    if a.dis:
        import capstone
        for lo, hi in ((H_DELTA, PR), (PR, FIND), (FIND, ZONE + len(zone))):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:hi - ZONE].rstrip(b"\0") or b"\x90", lo):
                print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate.startswith("FOREIGN"): print("ABORT (slot/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate in ("v1", "v2")): print("ABORT (mixed state)"); return 1
    if not a.revert and rz is not None and rz > ZONE:
        print("ABORT: set ZONE_END in patch_ai_site_recruit_v1.py to %#x first" % ZONE); return 1
    if zstate == "v1" and not a.revert: print("  state: v1 - upgrading v1 -> v2 in place")
    n = bytearray(d)
    if a.revert:
        struct.pack_into("<I", n, SLOT - V2F, ORIG_PROC)
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        struct.pack_into("<I", n, SLOT - V2F, PR)
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiendench2")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
