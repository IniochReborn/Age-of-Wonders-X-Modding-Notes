#!/usr/bin/env python3
"""
Holy Champion (0x92) / Unholy Champion (0x93) become 3-level abilities
(I/II/III = +1/+1, +2/+2, +3/+3 ATK/DMG vs evil / vs good targets) and also
apply to SHORT and MEDIUM range projectile/breath shots (AoWEPACK.dll,
2026-09-12).  Stacks with Monster Slaying and Hero Slaying exactly like the
vanilla melee tables do (each block adds independently).

REQUIRES (already in the 410 dll): patch_lifesteal_leveled_v1 (cave_lsnames
" I/II/III" names on the plain TMultiLevelAbility VMT), patch_hero_slaying_
leveled_v1 + patch_monster_slaying_leveled_v1 (their melee caves sit next to
the blocks patched here; disjoint bytes), patch_slayers_ranged_v1 (its hook
@0x5576EB34 is RE-POINTED to the new 4-slayer ranged cave; its old cave
@0x5580E500 becomes dead bytes and is left in place).

Vanilla facts (410 dll, verified by disassembly):
  * THolyChampionAbility / TUnholyChampionAbility are TEnhancementAbility
    subclasses (ctor 0x557B9A50 / 0x557B9B34, registered @0x557BCA0E /
    0x557BCA25 in the enhancement-ability registration run).  Their ONLY
    behavioural override is VMT+0xC4 "CanTake(unit)": base check, then
    IsClass(unit, TAbstractUnit) && unit.Alignment(VMT+0xFC) in a bit-set:
    Holy allows alignments {0,1} (good), Unholy {4,5} (evil).  The bit-set
    pointers live in DATA vars 0x558E9418 / 0x558E9098.  Unit-type mask word
    (+0x20) = 0x237 for both.  Name = LoadResString([0x558E904C]/[0x558E8EBC])
    -> TranslateRStr (resource ids 64519/64520) - kept, so localisation works.
  * Melee bonus blocks (+2/+2 flat, innate ability OR enchantment 0xA0/0xA1,
    target alignment via combat VMT+0x90): CreateStrikeCA block
    @0x55766627.. (EBP=attacker, ESI=target, BL=atk acc, [ESP+3]=dmg acc) and
    TMeleeRound.CalculateStrikes @0x55767BE4.. (ESI=attacker, EDI=target,
    [EBX]=atk, [EBX+4]=dmg).  The two estimator copies (0x557664B0 helper and
    CalculateUnitStrikes 0x557677CC) are NOT hooked - same scope as the
    Monster/Hero Slaying leveled patches (they also left those flat).
  * Ranged: no Champion code anywhere in CreateRangedAttackCA.

What this patch does:
 A. REGISTRATION - both `call ctor` sites -> stubs -> cave_chml: builds a
    TMultiLevelAbility (id, translated resource name, mask 0x237, cap 3,
    cost COST_EACH/level) instead of the dedicated class.  The old classes
    stay in the binary, unused.  (Same flyweight approach as Monster Slaying;
    plain-ML instance => cave_lsnames gives "Holy Champion I/II/III".)
 B. ALIGNMENT GATE - TMultiLevelAbility VMT+0xC4 (CanExpand, shared with Life
    Stealing / Hero Slaying / Monster Slaying instances) -> cave_canexp: for
    self.id 0x92/0x93 re-applies the vanilla alignment bit-set test
    (IsClass TAbstractUnit, alignment 0..7, bt set) then falls through to the
    original ML CanExpand; other ids fall through untouched.  Covers hero
    level-up offers AND the Holy/Unholy Champion spell castability check
    (0x557E7760 calls ability.VMT+0xC4(unit)).
    ⚠ 2026-09-13 fix: an owner that is NOT a TAbstractUnit (the map editor's
    per-rank TAbilityOwner templates, items) skips the gate and gets the plain
    ML CanExpand, exactly as vanilla did (its `je` on IsClass kept the base
    result = true).  v1 returned false there, so the editor's ability picker
    refused Holy/Unholy Champion for every unit.
 C. MELEE LEVEL - the four flat +2/+2 add-tails become call-caves that add
    bonus = cave_chbonus(attacker, id):
       innate ability enabled -> level (0 => 1 for legacy bare-bit data),
       enchantment (id+0x0E) enabled -> at least 2 (vanilla spell strength),
    i.e. max(innate level, enchant ? 2 : 0).  The block's own gate
    (innate||enchant) && alignment-match already passed before the tail.
 D. RANGED - new cave_rngslay2 replaces the v1 ranged cave: range gate
    (ability byte +0x28 < 3 = short/medium), then Monster Slaying, Hero
    Slaying (unchanged logic from v1), Holy Champion, Unholy Champion blocks,
    each adding to both the pushed attack and the damage.

BALANCE NOTE: like Monster Slaying, every existing possessor with a bare
ability bit (no level record - all vanilla-authored units, existing saves)
drops from flat +2/+2 to level I = +1/+1 until re-authored in DevEd (which
loads this same dll, so the level spinner works) or bought up at level-up.
The enchantment spell keeps its +2/+2.

PIC throughout (call/pop delta for classref / DATA vars / VMT slot).
Caves in verified-zero, reloc-free space 0x55812C80.. (< 0x55813200).
Dry-run default; --apply; --revert; --dll <path>.
Backup: AoWEPACK.dll.bak_champion_lvl
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK_SUFFIX  = ".bak_champion_lvl"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE        = 0x55700000
FILE_DELTA  = 0x55700C00          # CODE: VA - FILE_DELTA = file offset

HOLY, UNHOLY   = 0x92, 0x93
ENCH_DELTA     = 0x0E             # 0x92->0xA0, 0x93->0xA1 (enchantment ids)
MS_ABIL, HS_ABIL, MARKER = 0x70, 0x38, 0x3F
MAX_LEVEL      = 3
COST_EACH      = 5                # skill points per level (Hero Slaying uses 5)
UNIT_MASK      = 0x237            # vanilla Champion unit-type mask word (+0x20)
ENCH_BONUS     = 2                # bonus when only the enchantment is present
RANGE_LONG     = 3                # ability byte +0x28 >= 3 -> no ranged bonus

# --- engine addresses (link-time VAs; rel32 or delta-adjusted at runtime) ---
LOADRESSTR   = 0x55701210
TRANSLATE    = 0x557249FC
LSTRASG      = 0x55701150
LSTRARRAYCLR = 0x55701148
ML_CREATE    = 0x55765168
ML_OBJENTRY  = 0x5571DF90         # dword -> TMultiLevelAbility VMT (relocated)
PUT_FN       = 0x55702EB4         # TIntegerList.Put(list, idx, val)
ISCLASS      = 0x557010C0
TABSUNIT_REF = 0x55710700         # dword -> TAbstractUnit VMT (relocated)
THERO_REF    = 0x55711FAC         # dword -> THero VMT (relocated)
HOLY_NAMEVAR, UNHOLY_NAMEVAR = 0x558E904C, 0x558E8EBC   # DATA: -> resstring rec
HOLY_SETVAR,  UNHOLY_SETVAR  = 0x558E9418, 0x558E9098   # DATA: -> alignment set
ML_VMT_CANEXP = 0x5571DFD0 + 0xC4                        # slot (has reloc entry)
ML_CANEXP_ORIG = 0x55765308

# --- hook sites ---
REG_H, REG_H_ORIG = 0x557BCA0E, 0x557B9A50   # call THolyChampionAbility.Create
REG_U, REG_U_ORIG = 0x557BCA25, 0x557B9B34   # call TUnholyChampionAbility.Create
M1H = 0x5576665D; M1U = 0x55766699           # CreateStrikeCA tails (8B each)
M1_ORIG = bytes.fromhex("80c302" "8044240302")   # add bl,2 / add byte [esp+3],2
M2H = 0x55767C1A; M2U = 0x55767C55           # CalculateStrikes tails (7B each)
M2_ORIG = bytes.fromhex("830302" "83430402")     # add [ebx],2 / add [ebx+4],2
RNG_HOOK, RNG_CONT = 0x5576EB34, 0x5576EB39
OLD_RNG_CAVE = 0x5580E500                    # v1 cave (becomes dead)

CAVE_LO, CAVE_HI = 0x55812C80, 0x55813200    # zero-verified, reloc-free


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []; self.fix32 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def dw(self, v): self.buf += (v & 0xFFFF).to_bytes(2, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def jcc32(self, op2, lab): self.db(0x0F, op2); self.fix32.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def pic_delta(self, reg_pop, reg_code):
        """call $+5 / pop reg / sub reg, link  -> reg = load delta."""
        self.call(self.here()+5); pop = self.here()
        self.db(0x58 + reg_pop)
        if reg_pop == 0: self.db(0x2D)                    # sub eax, imm32
        else:            self.db(0x81, 0xE8 + reg_pop)    # sub r32, imm32
        self.dd(pop)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127, (lab, rel)
            self.buf[off] = rel & 0xFF
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab]-(self.base+off+4)).to_bytes(4, 'little', signed=True)
        return bytes(self.buf)

# register numbers
EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI = range(8)

def enabled_call(a, attacker_reg, abil):
    """mov edx,abil ; mov eax,<attacker> ; mov ecx,[eax] ; call [ecx+0xA8] -> al"""
    a.db(0xBA); a.dd(abil)
    a.db(0x8B, 0xC0 | attacker_reg)          # mov eax, reg
    a.db(0x8B, 0x08)                         # mov ecx, [eax]
    a.db(0xFF, 0x91, 0xA8, 0, 0, 0)          # call [ecx+0xA8]

# --------------------------------------------------------------------------
# cave allocator
_next = CAVE_LO
def alloc(size_hint):
    global _next
    va = (_next + 15) & ~15
    _next = va + size_hint
    return va

caves = []   # (va, bytes, desc)
def emit(va, code, desc):
    global _next
    _next = max(_next, va + len(code))
    assert _next <= CAVE_HI, f"cave overflow: {desc} ends 0x{va+len(code):X}"
    caves.append((va, code, desc))

# --------------------------------------------------------------------------
# cave_chbonus: EAX=attacker (combat unit), EDX=ability id -> EAX = bonus
#   innate enabled -> level (min 1); enchantment enabled -> at least ENCH_BONUS
CAVE_BONUS = alloc(0x60)
a = Asm(CAVE_BONUS)
a.db(0x53); a.db(0x56)                       # push ebx / push esi
a.db(0x8B, 0xF0)                             # mov esi, eax   (attacker)
a.db(0x8B, 0xDA)                             # mov ebx, edx   (id)
a.db(0x8B, 0x08)                             # mov ecx, [eax]
a.db(0xFF, 0x91, 0xA8, 0, 0, 0)              # call [ecx+0xA8]  enabled(id)?
a.db(0x84, 0xC0); a.j8(0x74, 'ench_only')    # jz ench_only
a.db(0x8B, 0xD3)                             # mov edx, ebx
a.db(0x8B, 0xC6)                             # mov eax, esi
a.db(0x8B, 0x08)                             # mov ecx, [eax]
a.db(0xFF, 0x91, 0xB0, 0, 0, 0)              # call [ecx+0xB0]  GetAbilityLevel
a.db(0x85, 0xC0); a.j8(0x75, 'have')         # jnz have
a.db(0x40)                                   # inc eax          (bare bit -> 1)
a.label('have')
a.db(0x83, 0xF8, ENCH_BONUS); a.j8(0x7D, 'done')   # cmp eax,2 ; jge done
a.db(0x50)                                   # push eax
a.db(0x8D, 0x53, ENCH_DELTA)                 # lea edx, [ebx+0x0E]  enchantment id
a.db(0x8B, 0xC6); a.db(0x8B, 0x08)           # mov eax, esi ; mov ecx,[eax]
a.db(0xFF, 0x91, 0xA8, 0, 0, 0)              # call [ecx+0xA8]
a.db(0x84, 0xC0)                             # test al, al
a.db(0x58)                                   # pop eax (level)
a.j8(0x74, 'done')                           # jz done
a.label('ench_only')
a.db(0xB8); a.dd(ENCH_BONUS)                 # mov eax, ENCH_BONUS
a.label('done')
a.db(0x5E); a.db(0x5B); a.db(0xC3)           # pop esi / pop ebx / ret
emit(CAVE_BONUS, a.done(), "cave_chbonus (attacker,id -> bonus)")

# --------------------------------------------------------------------------
# melee call-caves
def melee1(va, abil):   # CreateStrikeCA: EBP=attacker, BL=atk acc, dmg acc [esp+7] (ret addr pushed)
    a = Asm(va)
    a.db(0x8B, 0xC5)                         # mov eax, ebp
    a.db(0xBA); a.dd(abil)                   # mov edx, abil
    a.call(CAVE_BONUS)
    a.db(0x02, 0xD8)                         # add bl, al
    a.db(0x00, 0x44, 0x24, 0x07)             # add [esp+7], al
    a.db(0xC3)
    return a.done()
def melee2(va, abil):   # CalculateStrikes: ESI=attacker, [EBX]=atk, [EBX+4]=dmg
    a = Asm(va)
    a.db(0x8B, 0xC6)                         # mov eax, esi
    a.db(0xBA); a.dd(abil)
    a.call(CAVE_BONUS)
    a.db(0x01, 0x03)                         # add [ebx], eax
    a.db(0x01, 0x43, 0x04)                   # add [ebx+4], eax
    a.db(0xC3)
    return a.done()
CAVE_M1H = alloc(0x20); emit(CAVE_M1H, melee1(CAVE_M1H, HOLY),   "cave_m1h (CreateStrikeCA Holy +lvl)")
CAVE_M1U = alloc(0x20); emit(CAVE_M1U, melee1(CAVE_M1U, UNHOLY), "cave_m1u (CreateStrikeCA Unholy +lvl)")
CAVE_M2H = alloc(0x20); emit(CAVE_M2H, melee2(CAVE_M2H, HOLY),   "cave_m2h (CalculateStrikes Holy +lvl)")
CAVE_M2U = alloc(0x20); emit(CAVE_M2U, melee2(CAVE_M2U, UNHOLY), "cave_m2u (CalculateStrikes Unholy +lvl)")

# --------------------------------------------------------------------------
# cave_rngslay2: hook @0x5576EB34 (push eax = damage).  EAX=damage, EBX=ability,
# ESI=shooter, [EBP-4]=target, [ESP]=pushed attack.  EDI saved -> damage acc,
# attack at [esp+4].
CAVE_RNG = alloc(0x1A0)
a = Asm(CAVE_RNG)
a.db(0x80, 0x7B, 0x28, RANGE_LONG)           # cmp byte [ebx+0x28], 3
a.jcc32(0x8D, 'out')                         # jge out (long range)
a.db(0x57)                                   # push edi
a.db(0x8B, 0xF8)                             # mov edi, eax
# ---- Monster Slaying (shooter 0x70 && target 0x3F) -> +level ----
enabled_call(a, ESI, MS_ABIL); a.db(0x84, 0xC0); a.j8(0x74, 'hs')
a.db(0xBA); a.dd(MARKER); a.db(0x8B, 0x45, 0xFC); a.db(0x8B, 0x08); a.db(0xFF, 0x91, 0xA8, 0, 0, 0)
a.db(0x84, 0xC0); a.j8(0x74, 'hs')
a.db(0xBA); a.dd(MS_ABIL); a.db(0x8B, 0xC6); a.db(0x8B, 0x08); a.db(0xFF, 0x91, 0xB0, 0, 0, 0)  # level
a.db(0x85, 0xC0); a.j8(0x75, 'ms_have'); a.db(0x40)
a.label('ms_have'); a.db(0x03, 0xF8); a.db(0x01, 0x44, 0x24, 0x04)       # dmg += ; atk +=
# ---- Hero Slaying (shooter 0x38 && target strategic is THero) -> +level ----
a.label('hs')
enabled_call(a, ESI, HS_ABIL); a.db(0x84, 0xC0); a.j8(0x74, 'holy')
a.pic_delta(EDX, EDX)                        # edx = delta
a.db(0x8B, 0x92); a.dd(THERO_REF)            # mov edx, [edx+THeroRef]
a.db(0x8B, 0x45, 0xFC); a.db(0x8B, 0x40, 0x4C)   # mov eax,[ebp-4] ; mov eax,[eax+0x4C]
a.db(0x85, 0xC0); a.j8(0x74, 'holy')
a.call(ISCLASS); a.db(0x84, 0xC0); a.j8(0x74, 'holy')
a.db(0xBA); a.dd(HS_ABIL); a.db(0x8B, 0xC6); a.db(0x8B, 0x08); a.db(0xFF, 0x91, 0xB0, 0, 0, 0)
a.db(0x85, 0xC0); a.j8(0x75, 'hs_have'); a.db(0x40)
a.label('hs_have'); a.db(0x03, 0xF8); a.db(0x01, 0x44, 0x24, 0x04)
# ---- Holy Champion: (0x92 || 0xA0) on shooter, target alignment in {4,5} ----
a.label('holy')
enabled_call(a, ESI, HOLY); a.db(0x84, 0xC0); a.j8(0x75, 'holy_al')
enabled_call(a, ESI, HOLY + ENCH_DELTA); a.db(0x84, 0xC0); a.j8(0x74, 'unholy')
a.label('holy_al')
a.db(0x8B, 0x45, 0xFC); a.db(0x8B, 0x10); a.db(0xFF, 0x92, 0x90, 0, 0, 0)   # target alignment -> al
a.db(0x04, 0xFC); a.db(0x2C, 0x02); a.j8(0x73, 'unholy')                    # add al,-4 ; sub al,2 ; jae
a.db(0x8B, 0xC6); a.db(0xBA); a.dd(HOLY); a.call(CAVE_BONUS)
a.db(0x03, 0xF8); a.db(0x01, 0x44, 0x24, 0x04)
# ---- Unholy Champion: (0x93 || 0xA1) on shooter, target alignment in {0,1} ----
a.label('unholy')
enabled_call(a, ESI, UNHOLY); a.db(0x84, 0xC0); a.j8(0x75, 'unholy_al')
enabled_call(a, ESI, UNHOLY + ENCH_DELTA); a.db(0x84, 0xC0); a.j8(0x74, 'done')
a.label('unholy_al')
a.db(0x8B, 0x45, 0xFC); a.db(0x8B, 0x10); a.db(0xFF, 0x92, 0x90, 0, 0, 0)
a.db(0x2C, 0x02); a.j8(0x73, 'done')                                        # sub al,2 ; jae
a.db(0x8B, 0xC6); a.db(0xBA); a.dd(UNHOLY); a.call(CAVE_BONUS)
a.db(0x03, 0xF8); a.db(0x01, 0x44, 0x24, 0x04)
a.label('done')
a.db(0x8B, 0xC7); a.db(0x5F)                 # mov eax, edi ; pop edi
a.label('out')
a.db(0x50); a.db(0x8B, 0xC6); a.db(0x8B, 0x10)   # replay: push eax ; mov eax,esi ; mov edx,[eax]
a.jmp32(RNG_CONT)
emit(CAVE_RNG, a.done(), "cave_rngslay2 (MS+HS+Holy+Unholy on short/medium shots)")

# --------------------------------------------------------------------------
# cave_canexp: TMultiLevelAbility.CanExpand(EAX=self, EDX=unit) with alignment gate
CAVE_CANEXP = alloc(0x80)
a = Asm(CAVE_CANEXP)
a.db(0x81, 0x78, 0x0C); a.dd(HOLY); a.j8(0x74, 'holy')       # cmp [eax+0xC],0x92
a.db(0x81, 0x78, 0x0C); a.dd(UNHOLY); a.j8(0x74, 'unholy')
a.jmp32(ML_CANEXP_ORIG)
a.label('holy');   a.db(0xB9); a.dd(HOLY_SETVAR);   a.j8(0xEB, 'gate')
a.label('unholy'); a.db(0xB9); a.dd(UNHOLY_SETVAR)
a.label('gate')
a.db(0x53); a.db(0x56); a.db(0x57)           # push ebx/esi/edi
a.db(0x8B, 0xD8); a.db(0x8B, 0xF2); a.db(0x8B, 0xF9)   # ebx=self esi=unit edi=setvar
a.db(0x85, 0xF6); a.j8(0x74, 'fail')         # nil unit -> false
a.pic_delta(EAX, EAX)                        # eax = delta
a.db(0x50)                                   # push eax (delta)
a.db(0x8B, 0x90); a.dd(TABSUNIT_REF)         # mov edx, [eax+TAbstractUnitRef]
a.db(0x8B, 0xC6); a.call(ISCLASS)            # IsClass(unit, TAbstractUnit)
a.db(0x84, 0xC0); a.j8(0x74, 'ok_pop')       # not a live unit (editor TAbilityOwner, item):
                                             #   no alignment gate, like vanilla -> base check only
a.db(0x8B, 0xC6); a.db(0x8B, 0x10); a.db(0xFF, 0x92, 0xFC, 0, 0, 0)   # unit.Alignment -> al
a.db(0x3C, 0x07); a.j8(0x77, 'fail_pop')     # cmp al,7 ; ja
a.db(0x83, 0xE0, 0x7F)                       # and eax, 0x7F
a.db(0x59)                                   # pop ecx (delta)
a.db(0x8B, 0x14, 0x0F)                       # mov edx, [edi+ecx]  (set ptr, relocated)
a.db(0x0F, 0xA3, 0x02)                       # bt [edx], eax
a.j8(0x73, 'fail')                           # jnc fail
a.label('ok')
a.db(0x8B, 0xC3); a.db(0x8B, 0xD6)           # mov eax,ebx ; mov edx,esi
a.db(0x5F); a.db(0x5E); a.db(0x5B)           # pop edi/esi/ebx
a.jmp32(ML_CANEXP_ORIG)                      # alignment ok -> original ML CanExpand
a.label('ok_pop'); a.db(0x59); a.j8(0xEB, 'ok')   # pop ecx ; jmp ok
a.label('fail_pop'); a.db(0x59)              # pop ecx
a.label('fail')
a.db(0x33, 0xC0); a.db(0x5F); a.db(0x5E); a.db(0x5B); a.db(0xC3)
emit(CAVE_CANEXP, a.done(), "cave_canexp (ML CanExpand + Champion alignment gate)")

# --------------------------------------------------------------------------
# cave_chml: EAX=id, EDX=name-var VA -> EAX = new TMultiLevelAbility
CAVE_CHML = alloc(0x90)
a = Asm(CAVE_CHML)
a.db(0x53); a.db(0x56); a.db(0x57)           # push ebx/esi/edi
a.db(0x83, 0xEC, 0x08)                       # sub esp, 8   (two string temps)
a.db(0x33, 0xC9); a.db(0x89, 0x0C, 0x24); a.db(0x89, 0x4C, 0x24, 0x04)   # zero temps
a.db(0x8B, 0xF0); a.db(0x8B, 0xFA)           # esi=id, edi=name var VA
a.pic_delta(EBX, EBX)                        # ebx = delta
a.db(0x8B, 0x04, 0x1F)                       # mov eax, [edi+ebx]  -> resstring rec (relocated)
a.db(0x8B, 0xD4)                             # mov edx, esp        (out temp1)
a.call(LOADRESSTR)
a.db(0x8B, 0x04, 0x24); a.db(0x8D, 0x54, 0x24, 0x04)   # mov eax,[esp] ; lea edx,[esp+4]
a.call(TRANSLATE)                            # temp2 = translated name
a.db(0x8B, 0x83); a.dd(ML_OBJENTRY)          # mov eax, [ebx+MLObjEntry]  VMT
a.db(0x33, 0xC9); a.db(0xB2, 0x01)           # xor ecx,ecx ; mov dl,1
a.call(ML_CREATE)
a.db(0x8B, 0xF8)                             # mov edi, eax  (obj)
a.db(0x66, 0xC7, 0x47, 0x20); a.dw(UNIT_MASK)          # mov word [edi+0x20], mask
a.db(0x89, 0x77, 0x0C)                       # mov [edi+0xC], esi  (id)
a.db(0x8D, 0x47, 0x08); a.db(0x8B, 0x54, 0x24, 0x04)   # lea eax,[edi+8] ; mov edx,[esp+4]
a.call(LSTRASG)                              # name := translated
a.db(0xC7, 0x47, 0x28); a.dd(MAX_LEVEL)      # cap
for lvl in range(1, MAX_LEVEL+1):
    a.db(0x8B, 0x47, 0x2C); a.db(0xBA); a.dd(lvl); a.db(0xB9); a.dd(COST_EACH); a.call(PUT_FN)
a.db(0x8B, 0xC4); a.db(0xBA); a.dd(2); a.call(LSTRARRAYCLR)   # clear temps
a.db(0x8B, 0xC7)                             # mov eax, edi
a.db(0x83, 0xC4, 0x08); a.db(0x5F); a.db(0x5E); a.db(0x5B); a.db(0xC3)
emit(CAVE_CHML, a.done(), f"cave_chml (build ML champion: cap {MAX_LEVEL}, cost {COST_EACH}/lvl)")

def stub(va, abil, namevar):
    a = Asm(va)
    a.db(0xB8); a.dd(abil); a.db(0xBA); a.dd(namevar); a.jmp32(CAVE_CHML)
    return a.done()
STUB_H = alloc(0x10); emit(STUB_H, stub(STUB_H, HOLY, HOLY_NAMEVAR),     "stub_holy -> cave_chml")
STUB_U = alloc(0x10); emit(STUB_U, stub(STUB_U, UNHOLY, UNHOLY_NAMEVAR), "stub_unholy -> cave_chml")
CAVE_END = _next

# --------------------------------------------------------------------------
def rel32(src, dst): return struct.pack("<i", dst-(src+5))
def callop(src, dst): return b"\xE8" + rel32(src, dst)
def jmpop(src, dst):  return b"\xE9" + rel32(src, dst)

patches = [(va, bytes(len(code)), code, desc) for va, code, desc in caves]
patches += [
    (REG_H, callop(REG_H, REG_H_ORIG), callop(REG_H, STUB_H), "registration: Holy ctor call -> stub_holy"),
    (REG_U, callop(REG_U, REG_U_ORIG), callop(REG_U, STUB_U), "registration: Unholy ctor call -> stub_unholy"),
    (ML_VMT_CANEXP, struct.pack("<I", ML_CANEXP_ORIG), struct.pack("<I", CAVE_CANEXP),
     "TMultiLevelAbility VMT+0xC4 CanExpand -> cave_canexp"),
    (M1H, M1_ORIG, callop(M1H, CAVE_M1H) + b"\x90"*3, "CreateStrikeCA Holy +2/+2 tail -> cave_m1h"),
    (M1U, M1_ORIG, callop(M1U, CAVE_M1U) + b"\x90"*3, "CreateStrikeCA Unholy +2/+2 tail -> cave_m1u"),
    (M2H, M2_ORIG, callop(M2H, CAVE_M2H) + b"\x90"*2, "CalculateStrikes Holy +2/+2 tail -> cave_m2h"),
    (M2U, M2_ORIG, callop(M2U, CAVE_M2U) + b"\x90"*2, "CalculateStrikes Unholy +2/+2 tail -> cave_m2u"),
    (RNG_HOOK, jmpop(RNG_HOOK, OLD_RNG_CAVE), jmpop(RNG_HOOK, CAVE_RNG),
     "CreateRangedAttackCA damage-push hook -> cave_rngslay2 (v1 cave now dead)"),
]

def reloc_check(dll_path):
    try:
        import pefile
    except ImportError:
        print("  (pefile not available - reloc check skipped)"); return True
    pe = pefile.PE(dll_path)
    ok = True
    relocs = [e.rva + BASE for blk in pe.DIRECTORY_ENTRY_BASERELOC for e in blk.entries if e.type]
    for va, old, new, desc in patches:
        if va == ML_VMT_CANEXP: continue        # VMT slot: reloc entry expected and wanted
        hits = [r for r in relocs if va <= r < va + len(new) or va < r + 4 <= va + len(new)]
        if hits:
            print(f"  RELOC INTERSECT @0x{va:X} ({desc}): {[hex(h) for h in hits]}"); ok = False
    return ok

def write_inplace(path, data):
    """Same-size in-place write (no truncate): a plain 'wb' open of this dll
    intermittently fails with EINVAL on this machine (AV/filter timing)."""
    assert len(data) == os.path.getsize(path), "size changed - refusing in-place write"
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    dll, bak = args.dll, bak_path(args.dll, BAK_SUFFIX)
    data = bytearray(open(dll, "rb").read())

    print(f"target: {dll}")
    print(f"caves 0x{CAVE_LO:X}..0x{CAVE_END:X} ({CAVE_END-CAVE_LO} B used of {CAVE_HI-CAVE_LO})")
    for va, code, desc in caves: print(f"  0x{va:X} {len(code):3d}B  {desc}")

    if args.revert:
        applied = all(bytes(data[va-FILE_DELTA:va-FILE_DELTA+len(new)]) == new for va, old, new, d in patches)
        if not applied:
            print("Not (fully) applied - nothing to revert."); return 1
        for va, old, new, desc in patches:
            data[va-FILE_DELTA:va-FILE_DELTA+len(old)] = old
        write_inplace(dll, data); print("Reverted all patches (caves zeroed, hooks restored).")
        return 0

    ok = True; applied = 0
    for va, old, new, desc in patches:
        off = va - FILE_DELTA
        cur = bytes(data[off:off+len(old)])
        if cur == new: applied += 1
        elif cur != old:
            print(f"MISMATCH @0x{va:X} ({desc}):\n  exp {old.hex(' ')[:80]}\n  got {cur.hex(' ')[:80]}"); ok = False
    if applied == len(patches):
        print("ALL ALREADY PATCHED"); return 0
    if applied: print(f"partial: {applied}/{len(patches)} already applied"); ok = False
    if not ok:
        print("Aborting."); return 1
    if not reloc_check(dll):
        print("Aborting (reloc)."); return 1
    print(f"\nHoly/Unholy Champion I/II/III: +1/+1, +2/+2, +3/+3 (melee + short/medium ranged); "
          f"cost {COST_EACH}/level; enchantment-only = +{ENCH_BONUS}/+{ENCH_BONUS}")
    if not args.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak):
        shutil.copyfile(dll, bak); print(f"Backup: {bak}")
    for va, old, new, desc in patches:
        data[va-FILE_DELTA:va-FILE_DELTA+len(new)] = new
        print(f"Patched: {desc}")
    write_inplace(dll, data)
    print("AoWEPACK.dll patched successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
