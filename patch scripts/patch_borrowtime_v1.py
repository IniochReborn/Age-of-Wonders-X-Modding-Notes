#!/usr/bin/env python3
r"""
Borrow Time (346): the Air/Death tier-3 combat spell - "the target friendly unit does not die when it reaches 0 HP,
but dies at the end of its next turn" (2026-10-15).  AoWEPACK.dll only.

Registered by patch_dual_sphere_spells_v1.py as a TRemedy instance (donor TRemedy, pfs 45 - like Martyr 360 /
Cleansing Flame 361: friendly single target, range 12 = long, pokes make it a COMBAT spell).  This script adds:

  ability 0xBB "Borrowed Time" = a SECOND TDecayAbility instance (Mind Decay's 0x83 class: a combat-only duration
     ability, mode [+0x28] = 3, whose VMT owns NewCombatTurn (+0xF8 = 0x557BA728) and CombatDone (+0xFC = 0x557BA784)
     outright - no other spell or patch uses those two slots).  Registered by splicing the vanilla
     `call RegisterAbility` @0x557BCE65 (the 0x83 site 0x557BCD81 is already oil spring's splice).  ecx = 0 for the
     ctor (the patch_slow_v1 216 lesson), name via LStrAsg of an in-cave AnsiString, [+0x24] = 4 (beneficial, like
     High Prayer's blessing / Oiled; Decay's own 1 = harmful).
  State lives in the ability DATA (TDurationAbility data: +0xC byte duration, +0xD combat player, +0xE id word):
     [data+0xC] = 0 protected / 1 DOOMED (lethal damage was refused) / 2 its NEXT own turn has begun / 3 dying.
     Expand writes GetDuration() there - the ex cave resets it to 0.

  ex  (chained in FRONT of Martyr's TRemedy.ExecuteSpell cave, site 0x557E736C):  spell 346 -> ValidTarget (VMT+0x9C),
      ability(0xBB).Expand(unit) (VMT+0xD0), [data+0xC] := 0, unit.Changed (VMT+0x90); other spells -> previous target.
  vt  (chained in front of Martyr's ValidTarget cave, site 0x557E7434):  346 -> TUnitSpell base check 0x5577ACAC AND
      NOT GetAbilityEnabled(0xBB) (unit VMT+0x148).
  dmg (TCombatUnit.ExecuteDamage 0x55726C58 body, the `mov eax,esi / mov edx,[eax] / call [edx+0x120]` DestroyObject
      call @0x55726CC5, 10 B -> call + 5 nops; runs for tactical AND fast combat units - the same method sits in both
      VMTs, and Mind Decay's per-turn damage (VMT+0x124) comes through here too):  if the unit HasAbility(0xBB)
      (CU VMT+0xA8) and its state < 3: state 0 -> 1 (doomed), HP := 1 (CU VMT+0x8C) and NO DestroyObject.  HP is held
      at 1, not 0: AoWE.DVtoDEV 0x55725F10 (AI damage valuation) divides by curHP*100 in the FPU with zero-divide
      unmasked -> a 0-HP live unit would raise EZeroDivide in the AI.  Every later lethal hit is refused the same way.
  nt  (TDecayAbility VMT+0xF8 NewCombatTurn; called by the per-turn combat action 0x5572A308 for EVERY object with
      cl = the combat player whose turn starts - a CA, so replay/LAN deterministic):  id 0x83 -> vanilla Decay.
      0xBB: state 1 and cl == the unit's own player [cu+0x45] -> 2 ("its next turn" has begun); state 2 and cl is
      ANOTHER player -> 3, HP := 1 (a healed unit too; ExecuteDamage asserts dmg < 50)
      and ExecuteDamage(1) through VMT+0x124 (exactly Mind Decay's kill path: DestroyObject,
      corpse, die anim, KillUnit, XP) = the unit dies at the END of its next turn.
  cd  (TDecayAbility VMT+0xFC CombatDone; called for every object when the combat ends):  0x83 -> vanilla (kill).
      0xBB: a doomed unit still alive -> HP 0 + DestroyObject (VMT+0x120, as vanilla Decay/Martyr do here) - the
      battle ending before the deadline does not save it; then TDurationAbility.CombatDone 0x55764E00 (removes the
      combat-only ability; a never-doomed unit just loses the enchantment).
  Healing a doomed unit does NOT save it (the state is a flag, the borrowed time runs out regardless).  Not covered:
  effects that destroy a unit directly without HP damage (they never reach the ExecuteDamage site).

v2 (2026-10-15, user test feedback; upgrades the applied v1 in place - build_v1 is kept only to recognise it):
  * the death is UNCONDITIONAL: state 0 at the cast (always during the caster's turn); nt: the unit's own player's
    next turn start -> 1; the next OTHER player's turn start after that -> 3 + death (Mind Decay's kill path) = the
    unit dies at the END of the caster's next turn.  dmg: ANY lethal hit is refused (HP held at 1) while state < 3
    (no 'doom' step).  Target = friendly, so "the caster's turn" = the target CU's own player [cu+0x45].
  * cd: EVERY unit still carrying 0xBB at combat end dies (HP 0 + DestroyObject, vanilla Decay's CombatDone).  v1 only
    killed units that had refused a lethal hit - the user's never had, hence "it didn't die after winning/fleeing".
    Coverage verified: TCombat VMT+0x6C EndCombat 0x55727E38 calls CombatDone (CU VMT+0xF8 0x55724B54 -> ability
    owner loop 0x5574FEC4 over [cu+0x4C] = the TUnit, which holds 0xBB) for every object in TCombatData; it runs from
    TCombat.Destroy 0x55727138 whenever the combat is still active, so win / loss / flee (TTerminateCombatTE) /
    auto-combat (TFastCombat, same slot) all pass through it.
  * gn: the "(combat only)" suffix is TDurationAbility.GetName 0x55764E38's mode-3 branch (resourcestring 65314;
    65313 "(%s/%s turns)", 65312 "(%s/%s days)").  The mode switch @0x55764E5A is Bloodbath's 7-B jmp (-> 0x55862170):
    chained in FRONT of it - ability 0xBB -> TAbility.GetName 0x5574E97C + " (1 turn left)" (state 0) or
    " (last turn)" (state 1+) via _LStrCatN, exit 0x55764FF7; everything else -> Bloodbath's cave.
    ⚠ with v2 applied, patch_bloodbath_v1.py's GetName site points at this patch: revert Borrow Time before touching it.
Caves AoWEPACK 0x55838000..0x55838400 (zero, no relocs).  PIC: rel32 calls + call/pop delta for the class cell and the
name.  VMT slots keep their relocs.  Chained sites decode the previous jmp target on apply; --revert restores it and
refuses if another hook has been placed in front of ours.  Backup <game>\backup\AoWEPACK.dll.bak_borrowtime.
After applying: patch_borrowtime_ability_pfs_v1.py (record 197), then LADDER += 0xBB in patch_tcablist_ceiling_v1.py and
patch_aowx_banner_ceilings_v1.py and re-run both (bound 0xBC).  Dry-run default.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_borrowtime"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55838000, 0x55838400
SPELL, ABIL = 346, 0xBB
DECAY_CELL, DECAY_CREATE, DECAY_VMT = 0x557B5CAC, 0x557BA680, 0x557B5CEC
DECAY_NT, DECAY_CD = 0x557BA728, 0x557BA784
DUR_COMBATDONE = 0x55764E00
LSTRASG, REGABIL = 0x55701150, 0x55750238
ABCTRL, GETABILITY, GETABILITYDATA = 0x558E92E8, 0x557501C0, 0x5574F1C4
BASECHECK = 0x5577ACAC
EX_EPI, VT_EPI = 0x557E742A, 0x557E74DB
EX_SITE, VT_SITE = 0x557E736C, 0x557E7434                    # TRemedy ExecuteSpell / ValidTarget entries (Martyr's jmps)
EX_VANILLA, VT_VANILLA = bytes.fromhex("558bec515356"), bytes.fromhex("53568bf18bce")
REG_SITE, REG_ORIG = 0x557BCE65, bytes.fromhex("e8ce33f9ff")  # call RegisterAbility (unhooked vanilla site)
DMG_SITE, DMG_ORIG = 0x55726CC5, bytes.fromhex("8bc68b10ff9220010000")
SLOTS = [(DECAY_VMT + 0xF8, DECAY_NT, "nt"), (DECAY_VMT + 0xFC, DECAY_CD, "cd")]
GN_SITE, GN_EXIT = 0x55764E5A, 0x55764FF7                     # TDurationAbility.GetName mode switch (Bloodbath's 7-B jmp) / common exit
BASENAME, LSTRCATN = 0x5574E97C, 0x55701198                   # TAbility.GetName (eax ab, edx owner, ecx result) / _LStrCatN (eax dest, edx n)
SUFFIX_LEFT, SUFFIX_LAST = " (1 turn left)", " (last turn)"
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def jmp_target(d, va):
    b = d[va - CODE_V2F:va - CODE_V2F + 5]
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def build_v1(prev_ex, prev_vt):
    """The v1 zone exactly as applied 2026-10-15 (kept only to recognise and upgrade it in place)."""
    out = bytearray(); where = {}
    lit = b"Borrowed Time"
    out += struct.pack("<ii", -1, len(lit)); where["name"] = ZONE + len(out); out += lit + b"\0"

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("getab", """
        push edx
        call next
    next:
        pop ecx
        sub ecx, next
        mov eax, [ecx + %(ctrl)#x]
        mov eax, [eax]
        mov eax, [eax + 0x80]
        pop edx
        call %(get)#x
        ret
    """ % {"ctrl": ABCTRL, "get": GETABILITY})

    # ex: spell 346 handled here with the vanilla frame (so the vanilla epilogue fits); everything else -> previous hook.
    place("ex", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        mov ebx, ecx
        mov [ebp - 4], edx
        mov esi, eax
        mov ecx, ebx
        mov edx, [ebp - 4]
        mov eax, esi
        mov esi, [eax]
        call [esi + 0x9c]
        test al, al
        je fail
        mov edx, %(abil)d
        call %(getab)#x
        mov edx, ebx
        mov ecx, [eax]
        call [ecx + 0xd0]
        mov edx, %(abil)d
        mov eax, ebx
        call %(gad)#x
        test eax, eax
        je nodata
        mov byte ptr [eax + 0xc], 0
    nodata:
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0x90]
        mov al, 1
        jmp %(epi)#x
    fail:
        xor eax, eax
        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev_ex, "abil": ABIL, "getab": where["getab"], "gad": GETABILITYDATA, "epi": EX_EPI})

    # vt: (eax spell, edx caster, ecx unit) -> al, vanilla frame push ebx / push esi.
    place("vt", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebx
        push esi
        mov esi, ecx
        call %(base)#x
        test al, al
        je no
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x148]
        test al, al
        jne no
        mov al, 1
        jmp %(epi)#x
    no:
        xor eax, eax
        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev_vt, "base": BASECHECK, "abil": ABIL, "epi": VT_EPI})

    # dmg: replaces the DestroyObject call in ExecuteDamage (esi = the combat unit; ebp/ebx/edi must survive).
    place("dmg", """
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0xa8]
        test al, al
        je kill
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xb8]
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        je kill
        cmp byte ptr [eax + 0xc], 3
        jae kill
        cmp byte ptr [eax + 0xc], 0
        jne keep
        mov byte ptr [eax + 0xc], 1
    keep:
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x8c]
        ret
    kill:
        mov eax, esi
        mov edx, [eax]
        call [edx + 0x120]
        ret
    """ % {"abil": ABIL, "gad": GETABILITYDATA})

    # nt: TDecayAbility.NewCombatTurn (eax ability, edx combat unit, cl = player whose turn starts).
    place("nt", """
        cmp dword ptr [eax + 0xc], %(abil)d
        je mine
        jmp %(orig)#x
    mine:
        push ebx
        push esi
        push edi
        mov esi, edx
        mov bl, cl
        test byte ptr [esi + 0x47], 1
        jne out
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xb8]
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        je out
        mov edi, eax
        mov al, byte ptr [edi + 0xc]
        test al, al
        je out
        cmp bl, byte ptr [esi + 0x45]
        jne other
        cmp al, 1
        jne out
        mov byte ptr [edi + 0xc], 2
        jmp out
    other:
        cmp al, 2
        jne out
        mov byte ptr [edi + 0xc], 3
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x8c]
        mov edx, 1
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x124]
    out:
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"abil": ABIL, "orig": DECAY_NT, "gad": GETABILITYDATA})

    # cd: TDecayAbility.CombatDone (eax ability, edx combat unit).
    place("cd", """
        cmp dword ptr [eax + 0xc], %(abil)d
        je mine
        jmp %(orig)#x
    mine:
        push ebx
        push esi
        mov ebx, eax
        mov esi, edx
        test byte ptr [esi + 0x47], 1
        jne base
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xb8]
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        je base
        cmp byte ptr [eax + 0xc], 0
        je base
        mov byte ptr [eax + 0xc], 3
        xor edx, edx
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x8c]
        mov eax, esi
        mov edx, [eax]
        call [edx + 0x120]
    base:
        mov eax, ebx
        mov edx, esi
        pop esi
        pop ebx
        jmp %(dur)#x
    """ % {"abil": ABIL, "orig": DECAY_CD, "gad": GETABILITYDATA, "dur": DUR_COMBATDONE})

    # reg: the vanilla registration, then a second TDecayAbility instance as 0xBB "Borrowed Time" (ebx = control).
    place("reg", """
        call %(reg)#x
        push esi
        call next
    next:
        pop esi
        sub esi, next
        lea eax, [esi + %(cell)#x]
        mov eax, [eax]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(abil)d
        mov byte ptr [eax + 0x24], 4
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "cell": DECAY_CELL, "create": DECAY_CREATE, "abil": ABIL, "name": where["name"], "lstrasg": LSTRASG})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def build(prev_ex, prev_vt, prev_gn):
    """v2 zone (2026-10-15 user feedback): unconditional death at the end of the caster's next turn, a timer in the
    ability's name instead of '(combat only)', and the combat-end kill for EVERY unit still carrying 0xBB."""
    out = bytearray(); where = {}
    def lit(key, text):
        b = text.encode("latin-1")
        out.extend(struct.pack("<ii", -1, len(b))); where[key] = ZONE + len(out); out.extend(b + b"\0")
        while len(out) % 4: out.append(0)
    lit("name", "Borrowed Time")
    lit("left", SUFFIX_LEFT)
    lit("last", SUFFIX_LAST)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("getab", """
        push edx
        call next
    next:
        pop ecx
        sub ecx, next
        mov eax, [ecx + %(ctrl)#x]
        mov eax, [eax]
        mov eax, [eax + 0x80]
        pop edx
        call %(get)#x
        ret
    """ % {"ctrl": ABCTRL, "get": GETABILITY})

    # ex: unchanged from v1 (grant 0xBB, state := 0).
    place("ex", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        mov ebx, ecx
        mov [ebp - 4], edx
        mov esi, eax
        mov ecx, ebx
        mov edx, [ebp - 4]
        mov eax, esi
        mov esi, [eax]
        call [esi + 0x9c]
        test al, al
        je fail
        mov edx, %(abil)d
        call %(getab)#x
        mov edx, ebx
        mov ecx, [eax]
        call [ecx + 0xd0]
        mov edx, %(abil)d
        mov eax, ebx
        call %(gad)#x
        test eax, eax
        je nodata
        mov byte ptr [eax + 0xc], 0
    nodata:
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0x90]
        mov al, 1
        jmp %(epi)#x
    fail:
        xor eax, eax
        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev_ex, "abil": ABIL, "getab": where["getab"], "gad": GETABILITYDATA, "epi": EX_EPI})

    # vt: unchanged from v1.
    place("vt", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebx
        push esi
        mov esi, ecx
        call %(base)#x
        test al, al
        je no
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x148]
        test al, al
        jne no
        mov al, 1
        jmp %(epi)#x
    no:
        xor eax, eax
        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev_vt, "base": BASECHECK, "abil": ABIL, "epi": VT_EPI})

    # dmg v2: a 0xBB unit is held at 1 HP by ANY lethal hit until the timer kills it (state 3) - no 'doom' step any more.
    place("dmg", """
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0xa8]
        test al, al
        je kill
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xb8]
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        je kill
        cmp byte ptr [eax + 0xc], 3
        jae kill
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x8c]
        ret
    kill:
        mov eax, esi
        mov edx, [eax]
        call [edx + 0x120]
        ret
    """ % {"abil": ABIL, "gad": GETABILITYDATA})

    # nt v2 (eax ability, edx combat unit, cl = player whose turn starts):  state 0 (cast during the caster's turn) ->
    # 1 when the unit's own side's NEXT turn starts; state 1 -> 3 + death when any OTHER player's turn starts after it
    # (= the end of the caster's next turn).  Mind Decay's kill path: HP := 1, ExecuteDamage(1) through VMT+0x124.
    place("nt", """
        cmp dword ptr [eax + 0xc], %(abil)d
        je mine
        jmp %(orig)#x
    mine:
        push ebx
        push esi
        push edi
        mov esi, edx
        mov bl, cl
        test byte ptr [esi + 0x47], 1
        jne out
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xb8]
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        je out
        mov edi, eax
        mov al, byte ptr [edi + 0xc]
        cmp al, 3
        jae out
        cmp bl, byte ptr [esi + 0x45]
        jne other
        test al, al
        jne out
        mov byte ptr [edi + 0xc], 1
        jmp out
    other:
        cmp al, 1
        jne out
        mov byte ptr [edi + 0xc], 3
        mov dl, 1
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x8c]
        mov edx, 1
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x124]
    out:
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"abil": ABIL, "orig": DECAY_NT, "gad": GETABILITYDATA})

    # cd v2 (eax ability, edx combat unit; TCombat.EndCombat VMT+0x6C runs it for every combat object - win, loss,
    # retreat/flee (TTerminateCombatTE -> TCombat.Destroy -> EndCombat while active) and auto-combat (TFastCombat)):
    # every 0xBB unit still alive dies (HP 0 + DestroyObject, as vanilla Decay's CombatDone), then the base CombatDone.
    place("cd", """
        cmp dword ptr [eax + 0xc], %(abil)d
        je mine
        jmp %(orig)#x
    mine:
        push ebx
        push esi
        mov ebx, eax
        mov esi, edx
        test byte ptr [esi + 0x47], 1
        jne base
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xb8]
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        je dokill
        mov byte ptr [eax + 0xc], 3
    dokill:
        xor edx, edx
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x8c]
        mov eax, esi
        mov edx, [eax]
        call [edx + 0x120]
    base:
        mov eax, ebx
        mov edx, esi
        pop esi
        pop ebx
        jmp %(dur)#x
    """ % {"abil": ABIL, "orig": DECAY_CD, "gad": GETABILITYDATA, "dur": DUR_COMBATDONE})

    # gn (TDurationAbility.GetName mode switch @0x55764E5A, chained in front of Bloodbath's cave): ebx = ability,
    # esi = owner (non-nil), edi = result string, [ebp-4] = a finalized temp.  0xBB -> base name + " (1 turn left)" while
    # state 0, " (last turn)" from the caster's next turn on; everything else (and 0xBB without data) -> previous hook.
    place("gn", """
        cmp dword ptr [ebx + 0xc], %(abil)d
        je mine
        jmp %(prev)#x
    mine:
        mov eax, esi
        mov edx, %(abil)d
        call %(gad)#x
        test eax, eax
        jne have
        jmp %(prev)#x
    have:
        push eax
        call next
    next:
        pop ecx
        sub ecx, next
        pop edx
        lea eax, [ecx + %(left)#x]
        cmp byte ptr [edx + 0xc], 0
        je chosen
        lea eax, [ecx + %(last)#x]
    chosen:
        push eax
        lea ecx, [ebp - 4]
        mov edx, esi
        mov eax, ebx
        call %(basename)#x
        pop eax
        push dword ptr [ebp - 4]
        push eax
        mov eax, edi
        mov edx, 2
        call %(catn)#x
        jmp %(exit)#x
    """ % {"abil": ABIL, "prev": prev_gn, "gad": GETABILITYDATA, "left": where["left"], "last": where["last"],
           "basename": BASENAME, "catn": LSTRCATN, "exit": GN_EXIT})

    # reg: unchanged from v1.
    place("reg", """
        call %(reg)#x
        push esi
        call next
    next:
        pop esi
        sub esi, next
        lea eax, [esi + %(cell)#x]
        mov eax, [eax]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(abil)d
        mov byte ptr [eax + 0x24], 4
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "cell": DECAY_CELL, "create": DECAY_CREATE, "abil": ABIL, "name": where["name"], "lstrasg": LSTRASG})
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
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    inzone = lambda va: va is not None and ZONE <= va < ZONE_END

    def cave_prev(cave):                     # our chained caves all start `cmp dword [reg+disp8], imm32 / je rel8 / jmp rel32`
        o = cave - CODE_V2F
        assert d[o + 7] == 0x74 and d[o + 9] == 0xE9, "cave layout unexpected @%#x" % cave
        return cave + 14 + struct.unpack_from("<i", d, o + 10)[0]

    # the three chained sites (TRemedy ExecuteSpell / ValidTarget = Martyr's jmps, GetName mode switch = Bloodbath's jmp):
    # decode the previous target - from the live jmp, or from our own cave (v1 or v2) when the site already points at us
    cur = {k: jmp_target(d, va) for k, va in (("ex", EX_SITE), ("vt", VT_SITE), ("gn", GN_SITE))}
    assert cur["ex"] and cur["vt"], "TRemedy sites are not jmp-hooked (patch_martyr_cleansing_v1.py must be applied first): %s %s" % (g(EX_SITE, 6).hex(), g(VT_SITE, 6).hex())
    assert cur["gn"] and g(GN_SITE, 7)[5:] == b"\x90\x90", "GetName switch @%#x is not Bloodbath's 7-byte jmp (patch_bloodbath_v1.py must be applied first): %s" % (GN_SITE, g(GN_SITE, 7).hex())
    prev = {k: (cave_prev(t) if inzone(t) else t) for k, t in cur.items()}
    zone, where = build(prev["ex"], prev["vt"], prev["gn"])
    z1, w1 = build_v1(prev["ex"], prev["vt"])
    chained = [("ex", EX_SITE, 6), ("vt", VT_SITE, 6), ("gn", GN_SITE, 7)]
    fixed = [("reg", REG_SITE, REG_ORIG, 0xE8), ("dmg", DMG_SITE, DMG_ORIG, 0xE8)]
    st = {}
    for k, va, n in chained:
        t = cur[k]
        st[k] = "ours" if t == where[k] else "v1" if k in w1 and t == w1[k] else "prev" if not inzone(t) else "OTHER"
    for k, va, orig, op in fixed:
        l = g(va, len(orig))
        st[k] = "ours" if l == rel(op, va, where[k], len(orig)) else "v1" if l == rel(op, va, w1[k], len(orig)) else "vanilla" if l == orig else "OTHER"
    for va, orig, c in SLOTS:
        l = struct.unpack_from("<I", d, va - CODE_V2F)[0]
        st[c + "@vmt"] = "ours" if l == where[c] else "v1" if l == w1[c] else "vanilla" if l == orig else "OTHER"
    zstate = ("zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):])
              else "v1" if zl[:len(z1)] == z1 and not any(zl[len(z1):]) else "DIFFERS")
    rl = reloc_set(d)
    spans = [(va, va + n) for _k, va, n in chained] + [(va, va + len(o)) for _k, va, o, _op in fixed]
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(lo - 3 <= r < hi for lo, hi in spans)]
    for va, _o, _c in SLOTS: assert va in rl, "VMT slot %#x has no reloc" % va
    print("sites %s | chain ex -> %#x, vt -> %#x, gn -> %#x | zone %s (%d B) | relocs %s | caves %s"
          % (st, prev["ex"], prev["vt"], prev["gn"], zstate, len(zone), bad or "none",
             ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        names = sorted((v, k) for k, v in where.items() if k not in ("name", "left", "last"))
        for (s, name), nxt in zip(names, [n[0] for n in names[1:]] + [ZONE + len(zone)]):
            print("  --", name)
            for i in md.disasm(zone[s - ZONE:nxt - ZONE], s): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    mine = ("ours", "v1")
    if a.revert:
        if not any(v in mine for v in st.values()): print("nothing to revert"); return 0
        out = bytearray(d)
        for k, va, n in chained:
            if st[k] in mine: out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, prev[k], n)
        for k, va, orig, _op in fixed:
            if st[k] in mine: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        for va, orig, c in SLOTS:
            if st[c + "@vmt"] in mine: out[va - CODE_V2F:va - CODE_V2F + 4] = struct.pack("<I", orig)
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out))
        print("reverted (chained sites -> ex %#x / vt %#x / gn %#x)" % (prev["ex"], prev["vt"], prev["gn"])); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "ours" and not any(v == "ours" for v in st.values()): print("ABORT: zone not free"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va, n in chained: out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, where[k], n)
    for k, va, orig, op in fixed: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = rel(op, va, where[k], len(orig))
    for va, orig, c in SLOTS: out[va - CODE_V2F:va - CODE_V2F + 4] = struct.pack("<I", where[c])
    print("%d bytes change%s" % (sum(1 for x, y in zip(d, out) if x != y), " (v1 applied: --apply upgrades it in place)" if zstate == "v1" else ""))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
