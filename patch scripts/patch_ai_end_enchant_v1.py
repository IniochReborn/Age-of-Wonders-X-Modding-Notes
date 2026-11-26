r"""
AI END-OF-TURN UNIT ENCHANTMENTS (strategic map), 2026-10-19.  AoWEPACK.dll only.

User: "I'd like to see the AI make greater use of unit enchantments, but make sure they don't always spend all their
mana and have none left when attacked by players.  Before they would otherwise end their turn, they should use up
about 50% of their casting points on unit enchantments if there are any units available to enchant, with priority
given to units within the AI leader's party (which are often weak)."

RE (vanilla machinery, all reused - nothing re-implemented):
  * AI turn = TAIPlayerControl.Process 0x5573416C running the player's AI actions (PAs) one at a time; a PA's
    Process (VMT+0x60) returns al=1 "still working, call me again" / 0 "done".  Between calls the controller stops
    while TPlayer.GetBusy 0x557516D0 is true (pending token events), so every TE a PA submits has EXECUTED before the
    PA's next Process call.
  * TEndTurnAIPA (VMT 0x55718EDC, priority 0x0A = last) Process 0x55734A64: if [player+0x2C] == 0 it submits the
    TEndTurnTE and returns 1.  This is "before they would otherwise end their turn".
  * Vanilla unit-spell AI: TCastSpellAIPA (priority 0x17) lets at most CastingHeroesMax = 1 + mana/250 heroes start ONE
    cast each per turn, gated by the AI budget manager (TSpell.AIRequestCastSpellExpense -> TAIBudgetManager), so
    unit enchantments are rare.  Its building blocks are what this patch calls:
      TUnitSpell VMT+0xC0 AIRetrieveOptimalTargetUnit 0x5577B460 (eax spell, edx hero, ecx army, push &unit, push
        &score; ret 8): over the HERO'S OWN ARMY, spell VMT+0x9C ValidTarget (the enchantment classes refuse units that
        already have their ability), unit status (+0x114) != 2, score = unit level (VMT+0xA0) + AI priority [spell+0x40];
      TUnitSpell VMT+0x60 AIExecuteCastSpellAction 0x5577B658 (eax spell, edx hero): re-picks the target the same
        way, books the expense, and - when THero.CanCastSpellInstantly - mints the SAME TUnitSpellTE a human cast
        creates (caster-cost wallet hook 0x5577B6ED charges CastingMana), submitted through the player's token control.
      THero.CanCastSpellInstantly 0x55789640 (eax hero, edx id, ecx [spell+0x14], push &str; ret 4; wallet-aware),
      THero.CastingMana 0x557894EC (eax hero, edx spell; caster-cost discounts), TPlayerMagicControl.ListSpells
      0x5577D148 (mask 6, as TCastSpellAIPA), GetManaIncome 0x5577C95C / GetManaUpkeep 0x5577C964, mana [magic+0x24],
      player magic [player+0x54], heroes [player+0x80] (GetHero 0x5578A208), leader [[player+0xD4]+4],
      casting points [hero+0x80] (signed byte, this turn) / max VMT+0x128, casting in progress [hero+0x84].

PATCH: TEndTurnAIPA VMT+0x60 (0x55718F3C, relocated slot) -> cave PR (zone 0x5581D400..0x5581E000, 'AEN1'):
  if the turn is not over yet and the player index is 1..13, find ONE best cast and execute it through the spell's own
  VMT+0x60, then return 1 (the controller waits for the cast TE, then calls again); when nothing qualifies (or after
  MAXCASTS casts this day) fall through to the original Process (end-turn TE).  A cast qualifies when:
    - spell IS a TUnitSpell, AI priority [spell+0x40] != -1, it is a lasting ENCHANTMENT (upkeep [spell+0x1C] > 0)
      and net mana income (GetManaIncome - GetManaUpkeep) covers its upkeep (no upkeep death-spiral);
    - caster: leader or hero, own army, Spell Casting (0x34), not channelling ([+0x84] == 0), not flagged [+0x25]&0x10,
      casting points after the cast >= KEEP_PCT % of its max (KEEP_PCT 45 -> "about 50 %" spent, at most ~55 %);
    - player mana after the cast >= RES_PCT % of the mana it had when this pass started that day (RES_PCT 50);
    - CanCastSpellInstantly (instant only - never starts multi-turn channelling) and the target finder returns a unit.
  Priority: phase 0 = casters standing in the LEADER'S ARMY (leader first) - the target finder works on the caster's
  own army, so this enchants the leader's party first, lowest-level units first; phase 1 = every other caster.  Within
  a phase the highest finder score (AI priority + unit level) wins.
  Per-player day state (14 x 8 B, AoWEPACK .idata page slack 0x5590BE50..0x5590BEC0, runtime zero): +0 day,
  +4 mana at pass start (24 bit) | casts this day << 24 (0xFF = nothing left to cast).
  MP: AI PAs run identically on every machine (see ai-explores-sites memory); everything here is deterministic game
  state, no RNG, and the cast is the vanilla AI's own TE path -> same as vanilla AI casting.

Dry-run default; --apply / --revert / --dis / --dll <scratch>.  Backup <game>\backup\AoWEPACK.dll.bak_aiendench.
NOTE: patch_ai_site_recruit_v1.py declares ZONE_END 0x5581E000 and zeroes it on revert - set its ZONE_END to
0x5581D400 first (this script refuses otherwise).
"""
import argparse, os, re, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581D400, 0x5581E000
MAGIC = b"AEN1"
H_DELTA, PR, FIND = ZONE + 0x10, ZONE + 0x20, ZONE + 0x180

SLOT, ORIG_PROC = 0x55718F3C, 0x55734A64          # TEndTurnAIPA VMT 0x55718EDC + 0x60 -> Process
TABLE, NSLOT = 0x5590BE50, 14
KEEP_PCT, RES_PCT, MAXCASTS = 45, 50, 12
REQUIRE_UPKEEP, UPKEEP_GUARD = 1, 1

MAPCELL = 0x558FA040
CLS_ARMY, CLS_USPELL, CLS_SPELLLIST = 0x557130AC, 0x55723550, 0x55722F14
SPELLLIST_CREATE, LISTSPELLS, SL_COUNT, SL_GET = 0x55779FA0, 0x5577D148, 0x5577A034, 0x5577A00C
GETHERO, ISCLASS, OBJFREE, LSTRCLR = 0x5578A208, 0x557010C0, 0x557010B8, 0x55701140
CASTMANA, CANINSTANT, MANAINC, MANAUPK = 0x557894EC, 0x55789640, 0x5577C95C, 0x5577C964
LIST_MASK = 6
GETUNIT, USTRENGTH = 0x5578309C, 0x5577F924     # TUnitList.GetUnit / TAbstractUnit.GetStrength(eax unit, dx mask)
EXPMADE, CLS_USPELLTE, TE_CREATE, TE_INIT = 0x557797A0, 0x557233A8, 0x5577A8B8, 0x5577A994
INTLIST_ADD, GETTOKCTRL = 0x55702E74, 0x5570372C

SRC_PR = """
    push ebp
    mov  ebp, esp
    sub  esp, 0x20
    push ebx
    push esi
    push edi
    mov  [ebp-4], eax
    call {HD}
    mov  ebx, eax
    mov  eax, [ebp-4]
    mov  eax, [eax+0xc]
    mov  esi, [eax+8]
    cmp  byte ptr [esi+0x2c], 0
    jne  p_orig
    movsx eax, byte ptr [esi+0xa6]
    test eax, eax
    jle  p_orig
    cmp  eax, {NS}
    jge  p_orig
    lea  edi, [ebx+eax*8+{TBL}]
    mov  eax, [ebx+{MAP}]
    mov  eax, [eax+0x174]
    cmp  [edi], eax
    je   p_have
    mov  [edi], eax
    mov  eax, [esi+0x54]
    mov  eax, [eax+0x24]
    test eax, eax
    jge  p_m1
    xor  eax, eax
p_m1:
    cmp  eax, 0xffffff
    jbe  p_m2
    mov  eax, 0xffffff
p_m2:
    mov  [edi+4], eax
p_have:
    movzx eax, byte ptr [edi+7]
    cmp  eax, {MAXC}
    jae  p_orig
    mov  eax, [edi+4]
    and  eax, 0xffffff
    imul eax, eax, {RES}
    xor  edx, edx
    mov  ecx, 100
    div  ecx
    mov  edx, eax
    mov  ecx, ebx
    mov  eax, esi
    call {FIND}
    test eax, eax
    jz   p_none
    mov  [ebp-8], eax
    mov  [ebp-0xc], edx
    mov  [ebp-0x10], ecx
    inc  byte ptr [edi+7]
    mov  eax, [ebp-8]
    push dword ptr [eax+0x1c]
    push 0
    mov  ecx, [eax+0x14]
    mov  edx, [ebp-0xc]
    call {EXPM}
    xor  ecx, ecx
    mov  dl, 1
    mov  eax, [ebx+{CTE}]
    call {TEC}
    mov  [ebp-0x14], eax
    push 0
    mov  eax, [ebp-0xc]
    mov  edx, [ebp-8]
    call {CM}
    push eax
    mov  ecx, [ebp-0xc]
    mov  eax, [ebp-8]
    mov  edx, [eax+0x10]
    mov  eax, [ebp-0x14]
    call {TEI}
    mov  eax, [ebp-0xc]
    mov  al, byte ptr [eax+0x24]
    mov  edx, [ebp-0x14]
    mov  byte ptr [edx+0x28], al
    mov  eax, [ebp-0x10]
    mov  edx, [eax+0x18]
    mov  eax, [ebp-0x14]
    mov  eax, [eax+0x20]
    call {ILA}
    mov  eax, [ebp-0xc]
    movsx edx, byte ptr [eax+0x24]
    mov  eax, [ebx+{MAP}]
    mov  eax, [eax+0x23c]
    call {GTC}
    mov  edx, [ebp-0x14]
    mov  ecx, [eax]
    call dword ptr [ecx+0x10]
    mov  eax, [ebp-0x14]
    mov  edx, [eax]
    call dword ptr [edx+0x2c]
    mov  al, 1
    jmp  p_ret
p_none:
    mov  byte ptr [edi+7], 0xff
p_orig:
    mov  eax, [ebp-4]
    call {ORIG}
p_ret:
    pop  edi
    pop  esi
    pop  ebx
    mov  esp, ebp
    pop  ebp
    ret
"""

# FIND: eax = player, edx = mana reserve, ecx = delta  ->  eax = spell, edx = caster, ecx = target unit (eax 0 = none)
# Ranking: phase (casters in the leader's army first), then TARGET (the leader first, then the strongest unit by
# all-kinds strength TAbstractUnit.GetStrength(0xFFFF)), then SPELL (tier [spell+0x21], then raw cost [spell+0x14]).
SRC_FIND = """
    push ebp
    mov  ebp, esp
    sub  esp, 0x70
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
    cmp  dword ptr [ebp-0x1c], 0
    jne  f_ph1
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
    mov  eax, [esi+4]
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  [ebp-0x5c], eax
    mov  dword ptr [ebp-0x50], 0
f_unit:
    mov  eax, [ebp-0x50]
    cmp  eax, [ebp-0x5c]
    jge  f_snext
    mov  edx, eax
    mov  eax, [esi+4]
    call {GU}
    test eax, eax
    jz   f_unext
    mov  [ebp-0x64], eax
    mov  ecx, eax
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
    jge  f_uk
    xor  eax, eax
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
    cmp  dword ptr [ebp-0x1c], 2
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
"""


def upk_test():
    # eax = [spell+0x1C] upkeep.  REQUIRE_UPKEEP: only lasting enchantments; UPKEEP_GUARD: net income must cover it.
    s = []
    if REQUIRE_UPKEEP:
        s += ["test eax, eax", "jle  f_snext"]
    if UPKEEP_GUARD:
        s += ["cmp  eax, [ebp-0x58]", "jg   f_snext"]
    return "\n    ".join(s) or "nop"


def asm(src, at):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def build():
    hd = b"\xe8\x00\x00\x00\x00\x58\x2d" + struct.pack("<I", H_DELTA + 5) + b"\xc3"   # eax = runtime - preferred
    find_src = SRC_FIND.replace("{UPK_TEST}", upk_test())
    fnd = asm(find_src.format(MINC=MANAINC, MUPK=MANAUPK, CSL=CLS_SPELLLIST, SLC=SPELLLIST_CREATE, MASK=LIST_MASK,
                              LSP=LISTSPELLS, SLN=SL_COUNT, GH=GETHERO, CAR=CLS_ARMY, IC=ISCLASS, KEEP=KEEP_PCT,
                              SLG=SL_GET, CUS=CLS_USPELL, CM=CASTMANA, CI=CANINSTANT, LSC=LSTRCLR, OF=OBJFREE,
                              GU=GETUNIT, US=USTRENGTH), FIND)
    pr = asm(SRC_PR.format(HD=H_DELTA, NS=NSLOT, TBL=TABLE, MAP=MAPCELL, MAXC=MAXCASTS, RES=RES_PCT, FIND=FIND,
                           ORIG=ORIG_PROC, EXPM=EXPMADE, CTE=CLS_USPELLTE, TEC=TE_CREATE, CM=CASTMANA,
                           TEI=TE_INIT, ILA=INTLIST_ADD, GTC=GETTOKCTRL), PR)
    assert len(pr) <= FIND - PR, len(pr)
    zone = bytearray(FIND - ZONE + len(fnd))
    zone[0:4] = MAGIC
    zone[4:8] = struct.pack("<I", ORIG_PROC)
    for addr, blob in ((H_DELTA, hd), (PR, pr), (FIND, fnd)):
        zone[addr - ZONE:addr - ZONE + len(blob)] = blob
    assert len(zone) <= ZONE_END - ZONE
    return bytes(zone)


def recruit_zone_end():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patch_ai_site_recruit_v1.py")
    if not os.path.exists(p): return None
    m = re.search(r"^ZONE, ZONE_END = 0x5581D000, (0x[0-9A-Fa-f]+)", open(p, encoding="utf-8").read(), re.M)
    return int(m.group(1), 16) if m else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    sv = struct.unpack_from("<I", d, SLOT - V2F)[0]
    sstate = "vanilla" if sv == ORIG_PROC else "ours" if sv == PR else "FOREIGN(%#x)" % sv
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END]
    rz = recruit_zone_end()
    print("  TEndTurnAIPA.Process slot %#x: %s | zone %#x..%#x %s (%d B) | table %#x x%d | relocs %s | recruit ZONE_END %s"
          % (SLOT, sstate, ZONE, ZONE_END, zstate, len(zone), TABLE, NSLOT, bad or "none",
             "n/a" if rz is None else hex(rz)))
    print("  KEEP_PCT %d  RES_PCT %d  MAXCASTS %d  REQUIRE_UPKEEP %d  UPKEEP_GUARD %d"
          % (KEEP_PCT, RES_PCT, MAXCASTS, REQUIRE_UPKEEP, UPKEEP_GUARD))
    if a.dis:
        import capstone
        for lo, hi in ((H_DELTA, PR), (PR, FIND), (FIND, ZONE + len(zone))):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:hi - ZONE].rstrip(b"\0") or b"\x90", lo):
                print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate.startswith("FOREIGN"): print("ABORT (slot/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate == "ours"): print("ABORT (mixed state)"); return 1
    if not a.revert and rz is not None and rz > ZONE:
        print("ABORT: set ZONE_END in patch_ai_site_recruit_v1.py to %#x first (its revert zeroes up to %#x)" % (ZONE, rz))
        return 1
    n = bytearray(d)
    if a.revert:
        struct.pack_into("<I", n, SLOT - V2F, ORIG_PROC)
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        struct.pack_into("<I", n, SLOT - V2F, PR)
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiendench")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
