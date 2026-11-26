#!/usr/bin/env python3
r"""
Tactical AI: melee-versus-ranged rebalance (AoWTCPCK.dll, 2026-09-15).

Everything lives in AoWTC.TCAI.CheckUnit @0x004152A8, the per-(self, target) evaluator of the tactical
AI.  Frame: [ebp-4] cai, [ebp+0x10] TARGET (TCombatUnit), [ebp+0x14] SELF (the attacker/mover; proven by
TMeleeRound.Calculate(edx=attacker=[ebp+0x14], ecx=defender=[ebp+0x10]) -- v1 as applied on 2026-09-15 had
these two SWAPPED in every hero/leader test below; corrected 2026-09-17), [ebp-8]/[ebp-0xC] self x/y,
[ebp-0x1C] hex distance self->target, [ebp-0x5C] ability id in the ability loop, [ebp-0x64] the
"DEV" score of the option being built (same currency for melee and ranged), [ebp-0x80]/[ebp-0x84]
two frame slots vanilla never touches (verified over the whole function) that this patch uses.

Vanilla scoring (RE 2026-09-15):
  melee   0x4154A4..: TMeleeRound.Calculate(self,target); ourDV = GetAttackerDV; theirDV = GetDefenderDV;
          net = 0x413664(cai, edx=ourDV, ecx=theirDV, target, self)
              = (targetValue * ourDV  [x2 THero, x2 TLeader]  -  selfValue * theirDV [x2 TLeader]) / 100
          -> tcDVtoDEV -> [ebp-0x64] -> AddMove type 2 (adjacent) @0x415766 / type 4 (approach) @0x4158A2.
  ranged  0x417420..: DV = ability VMT+0xF0 (expected damage with the ability's OWN attack, so accuracy is
          priced in) -> 0x413664 with ecx = 0 (NO retaliation term) -> [ebp-0x64] @0x417510 -> shoot-now
          type 5 / approach-to-shoot type 3.
  So a weak but free shot beats a strong but "expensive" swing, and strike-ability status effects are
  invisible to the melee simulation.

Patch (five hooks, six caves, all position-independent: rel32 only + call/pop delta for the two
class-reference reads):
  E  entry 0x4152A8 (9 B prologue)      zero [ebp-0x80] (melee DEV) and [ebp-0x84] (melee-added flag).
  M  melee 0x415535 (call 0x413664)     before the net-score call:
        ourDV   *= 1 + attacker strike bonus   (Entangle Strike 0x77 +50%, Lightning Strike 0x10 +30%,
                                                 Cold Strike 0x0F +25%; summed)
        theirDV *= 1 + defender strike bonus   (same table, DEF_SIDE)
        theirDV *= HERO_RETAL_PCT (50) if target unit is THero; := 0 if TLeader   (checked leader first)
        theirDV *= escort weight w when the ATTACKER is a hero/leader (ESCORT_RULE, see the tunables):
                   w = (60*min(1, escortAlive/ownValue) + 40*escortAlive/escortStart) / 100, escort =
                   the AI's own-unit list [cai+8] minus self, alive = ([obj+0x47]&9)==0 weighted by
                   cur/max hp from VMT+0x88 GetHitPoints / VMT+0x84 GetHits (byte results; the 2026-09-15
                   build wrongly read [obj+0x88]/[obj+0x84] as fields - instance size is only 0x68 - fixed
                   2026-09-17), value = TCombatUnit VMT+0x5C (cached, ability-based, no hp
                   term - verified 0x55725850/0x55726454).  Scales the whole own-value term, leader x2 included.
        theirDV *= 0 / 50% / 100% by the per-round bold-streak roll (LUCK_RULE): hero 10% all / 15% half,
                   leader 5% all / 10% half; roll = hash(combat map [0x46C064]+0x134 round, +0xED side,
                   index of self in [cai+8], self max HP (VMT+0x84), own/enemy list counts) % 100.
  S1 0x415766 / S2 0x4158A2 (AddMove)   after the melee / approach-melee move is actually added:
        [ebp-0x80] = [ebp-0x64]; [ebp-0x84] = 1.
  R1 0x417451 (ranged DV store)         DV *= 150% for the stunning shots Lightning Bolts 0x7B, Cosmic
                                        Breath 0x1E, Doom Gaze 0x37; 125% for the freezing shots Cold
                                        Breath 0x57, Frost Bolts 0x7A -- tables RANGED_STUN / RANGED_FREEZE.
                                        (All five carry AbilTypes categories 3/5/11, which the jump table
                                        @0x416DC2 routes to this handler -- verified 2026-09-15.)
  R2 0x417510 (ranged DEV store)        opportunity cost + flip, only when [ebp-0x84] == 1:
        flip = hash(self x,y, target x,y, both HP, moves-so-far) % 100 < FLIP_PCT (10), and both
               scores > 0.  Pure function of synchronised battle state: never touches the game RNG,
               identical on every machine whether the AI plans on the host only or on all clients.
        adjacent ([ebp-0x1C] <= 1):
            normal: if melee > ranged: ranged := melee * ADJ_PCT/100 (90)  (melee <= 0: melee-1)
            flip:   melee >= ranged -> ranged := melee*110/100 + 1 (shoot instead)
                    melee <  ranged -> ranged := melee * ADJ_PCT/100  (swing instead)
        farther:
            normal: if melee >= ranged * FAR_RATIO (2): ranged *= FAR_PCT/100 (60)
            flip:   the opposite condition (melee does NOT dominate) applies the same reduction.
        The reduced [ebp-0x64] feeds both the shoot-now and the approach-to-shoot moves.

Coexists with build_ai_aoo_awareness.py (hooks 0x41A3C0 and 0x415551; caves 0x438660/0x4388E0).
Caves here start at 0x438B00 (zero-verified run 0x438A9E..0x466BAC).  Backup AoWTCPCK.dll.bak_aimelee.
Dry-run default; --apply; --revert; --dis prints the assembled caves.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_aimelee"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x400000

# ---- tunables -------------------------------------------------------------------------------
STRIKE_BONUS = {0x77: 50, 0x10: 30, 0x0F: 25}      # Entangle / Lightning / Cold Strike, % added to melee DV
DEF_SIDE = True                                      # also weight the defender's retaliation by ITS strikes
HERO_RETAL_PCT = 50                                  # retaliation weight vs hero targets
LEADER_RETAL_PCT = 0                                 # retaliation weight vs leader targets
# Escort rule (attacker is a hero or leader): retaliation weight w = (WA*a + WB*b) / (WA+WB), where
#   a = min(1, escortAlive / ownValue)   (escortAlive = sum of living non-fled own units' value * hp%)
#   b = escortAlive / escortStart        (escortStart = sum of every own unit's value, dead ones included;
#                                         0 when the hero started alone -> b = 0)
# Both fall to 0 together as the escort dies, so a lone hero fights with no retaliation fear and a hero
# with a battered escort keeps a proportionally small one.  No hard floor.
ESCORT_RULE = True
ESCORT_WA, ESCORT_WB = 60, 40
# Per-turn "bold streak" (on top of everything above): a hero/leader rolls once per combat round and
# either loses ALL retaliation fear, HALF of it, or none.  roll = hash(round counter, index in the AI's
# own list, max HP, side, own-list size, enemy-list size) % 100 -- constant within the unit's turn,
# changes every round, identical on every machine, never touches the game RNG.
#   roll < ALL      -> fear x0
#   roll < HALF_END -> fear x50%
LUCK_RULE = True
HERO_LUCK_ALL, HERO_LUCK_HALF_END = 10, 25          # 10% all, 15% half
LEADER_LUCK_ALL, LEADER_LUCK_HALF_END = 5, 15       # 5% all, 10% half
RANGED_STUN = {0x7B: 150, 0x1E: 150, 0x37: 150}      # Lightning Bolts, Cosmic Breath (vanilla id 0x1E), Doom Gaze
RANGED_FREEZE = {0x57: 125, 0x7A: 125}               # Cold Breath, Frost Bolts
ADJ_PCT = 90                                         # adjacent: ranged capped at melee * this %
ADJ_FLIP_PCT = 110                                   # adjacent flip: ranged raised to melee * this % + 1
FAR_RATIO = 2                                        # farther: melee "dominates" when >= ranged * ratio
FAR_PCT = 60                                         # ... then ranged scaled to this %
FLIP_PCT = 10                                        # % of evaluations that do the opposite
FLIP_MIN_LEVEL = 3                                   # the flip applies only to heroes/leaders and units of this level or higher (2026-09-20)

# ---- engine facts ---------------------------------------------------------------------------
FN_NET = 0x413664          # TCAI melee/ranged net-value combiner
FN_ADDMOVE = 0x4135B8
FN_ISCLASS = 0x401058      # thunk -> System.@IsClass(eax=obj, edx=class) -> al
IAT_THERO, IAT_TLEADER = 0x46E914, 0x46E910
G_COMBATMAP = 0x46C064     # AoWTC combat map global; +0x134 round counter (TAoWCombatMap.NewTurn @0x41BB6E), +0xED side
VMT_GETABILITYENABLED = 0xA8   # TCombatObject slot (edx = id)
CAVE_BASE, CAVE_END = 0x438B00, 0x439100

# (name, hook VA, original bytes, resume VA)
H_ENTRY = ("entry", 0x4152A8, bytes.fromhex("558bec81c44cffffff"), 0x4152B1)
H_MELEE = ("melee", 0x415535, bytes.fromhex("e82ae1ffff"), 0x41553A)
H_S1 = ("stash-melee", 0x415766, bytes.fromhex("e84ddeffff"), 0x41576B)
H_S2 = ("stash-approach", 0x4158A2, bytes.fromhex("e811ddffff"), 0x4158A7)
H_R1 = ("ranged-dv", 0x417451, bytes.fromhex("8945d8837dd800"), 0x417458)
H_R2 = ("ranged-cmp", 0x417510, bytes.fromhex("89459c8b4510"), 0x417516)
HOOKS = [H_ENTRY, H_MELEE, H_S1, H_S2, H_R1, H_R2]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def s32(v):
    return v - (1 << 32) if v >= (1 << 31) else v


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_entry(va):
    return asm(f"""
        push ebp
        mov ebp, esp
        add esp, -0xB4
        mov dword ptr [ebp-0x80], 0
        mov dword ptr [ebp-0x84], 0
        jmp {H_ENTRY[3]}
    """, va)


def strike_block(objslot):
    lines = ["push 0"]
    for i, (aid, pct) in enumerate(STRIKE_BONUS.items()):
        lines += [f"mov eax, [ebp+{objslot:#x}]", f"mov edx, {aid:#x}", "mov ecx, [eax]",
                  f"call [ecx+{VMT_GETABILITYENABLED:#x}]", "test al, al", f"jz sb_{objslot}_{i}",
                  f"add dword ptr [esp], {pct}", f"sb_{objslot}_{i}:"]
    lines += ["pop eax", "add eax, 100"]
    return "\n".join(lines)


def cave_melee(va):
    pre = "push eax\npush ebx\npush esi\npush edi\nmov esi, edx\nmov edi, ecx\n"
    p1 = asm(pre, va)
    call_at = va + len(p1)
    next_va = call_at + 5
    p1 += asm(f"call {next_va:#x}", call_at)
    assert len(p1) == next_va - va
    body = f"""
        pop ebx
        sub ebx, {next_va:#x}
        {strike_block(0x14)}
        imul esi, eax
        mov eax, esi
        cdq
        mov ecx, 100
        idiv ecx
        mov esi, eax
    """
    if DEF_SIDE:
        body += f"""
        {strike_block(0x10)}
        imul edi, eax
        mov eax, edi
        cdq
        mov ecx, 100
        idiv ecx
        mov edi, eax
        """
    body += f"""
        mov eax, [ebp+0x10]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {FN_ISCLASS:#x}
        test al, al
        jz not_leader
        mov eax, edi
        imul eax, eax, {LEADER_RETAL_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        mov edi, eax
        jmp cls_done
    not_leader:
        mov eax, [ebp+0x10]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {FN_ISCLASS:#x}
        test al, al
        jz cls_done
        mov eax, edi
        imul eax, eax, {HERO_RETAL_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        mov edi, eax
    cls_done:
    """
    if ESCORT_RULE:
        body += f"""
        mov eax, [ebp+0x14]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {FN_ISCLASS:#x}
        test al, al
        jz esc_done
        sub esp, 16
        xor eax, eax
        mov [esp], eax
        mov [esp+4], eax
        mov [esp+8], eax
        mov eax, [ebp+0x14]
        mov edx, [eax]
        call [edx+0x5C]
        mov [esp+12], eax
    esc_loop:
        mov eax, [ebp-4]
        mov eax, [eax+8]
        mov ecx, [eax+8]
        cmp [esp+8], ecx
        jge esc_end
        mov edx, [esp+8]
        mov eax, [eax+4]
        mov eax, [eax+edx*4]
        test eax, eax
        jz esc_next
        cmp eax, [ebp+0x14]
        je esc_next
        push eax
        mov edx, [eax]
        call [edx+0x5C]
        pop ecx
        test eax, eax
        jle esc_next
        add [esp+4], eax
        test byte ptr [ecx+0x47], 9
        jnz esc_next
        push eax
        push ecx
        mov eax, ecx
        mov edx, [eax]
        call [edx+0x84]
        movsx edx, al
        test edx, edx
        jle esc_pop2
        push edx
        mov eax, [esp+4]
        mov edx, [eax]
        call [edx+0x88]
        movsx eax, al
        pop ecx
        pop edx
        pop edx
        imul eax, edx
        cdq
        idiv ecx
        add [esp], eax
        jmp esc_next
    esc_pop2:
        pop ecx
        pop eax
    esc_next:
        inc dword ptr [esp+8]
        jmp esc_loop
    esc_end:
        mov eax, [esp]
        imul eax, eax, 100
        mov ecx, [esp+12]
        test ecx, ecx
        jle esc_a100
        cdq
        idiv ecx
        cmp eax, 100
        jle esc_a_ok
    esc_a100:
        mov eax, 100
    esc_a_ok:
        mov [esp+8], eax
        mov ecx, [esp+4]
        test ecx, ecx
        jle esc_b0
        mov eax, [esp]
        imul eax, eax, 100
        cdq
        idiv ecx
        jmp esc_b_ok
    esc_b0:
        xor eax, eax
    esc_b_ok:
        imul eax, eax, {ESCORT_WB}
        mov ecx, [esp+8]
        imul ecx, ecx, {ESCORT_WA}
        add eax, ecx
        mov ecx, {ESCORT_WA + ESCORT_WB}
        cdq
        idiv ecx
        imul edi, eax
        mov eax, edi
        cdq
        mov ecx, 100
        idiv ecx
        mov edi, eax
        add esp, 16
    esc_done:
        """
    if LUCK_RULE:
        body += f"""
        mov eax, [ebp+0x14]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {FN_ISCLASS:#x}
        test al, al
        jz luck_done
        push {HERO_LUCK_HALF_END}
        push {HERO_LUCK_ALL}
        mov eax, [ebp+0x14]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {FN_ISCLASS:#x}
        test al, al
        jz luck_hero
        mov dword ptr [esp], {LEADER_LUCK_ALL}
        mov dword ptr [esp+4], {LEADER_LUCK_HALF_END}
    luck_hero:
        mov eax, [ebx+{G_COMBATMAP:#x}]
        movzx ecx, byte ptr [eax+0xED]
        imul ecx, ecx, {s32(0x27D4EB2F)}
        mov eax, [eax+0x134]
        imul eax, eax, {s32(0x9E3779B1)}
        xor ecx, eax
        xor edx, edx
    luck_idx:
        mov eax, [ebp-4]
        mov eax, [eax+8]
        cmp edx, [eax+8]
        jge luck_idx_end
        mov eax, [eax+4]
        mov eax, [eax+edx*4]
        cmp eax, [ebp+0x14]
        je luck_idx_end
        inc edx
        jmp luck_idx
    luck_idx_end:
        imul edx, edx, {s32(0x85EBCA6B)}
        xor ecx, edx
        mov eax, [ebp+0x14]
        push ecx
        mov edx, [eax]
        call [edx+0x84]
        pop ecx
        movsx eax, al
        imul eax, eax, {s32(0xC2B2AE35)}
        xor ecx, eax
        mov eax, [ebp-4]
        mov eax, [eax+8]
        mov eax, [eax+8]
        imul eax, eax, {s32(0x165667B1)}
        xor ecx, eax
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov eax, [eax+8]
        imul eax, eax, {s32(0xD3A2646C)}
        xor ecx, eax
        mov eax, ecx
        shr eax, 13
        xor ecx, eax
        imul ecx, ecx, {s32(0x5BD1E995)}
        mov eax, ecx
        shr eax, 15
        xor ecx, eax
        mov eax, ecx
        xor edx, edx
        mov ecx, 100
        div ecx
        cmp edx, [esp]
        jae luck_half
        xor edi, edi
        jmp luck_pop
    luck_half:
        cmp edx, [esp+4]
        jae luck_pop
        mov eax, edi
        cdq
        mov ecx, 2
        idiv ecx
        mov edi, eax
    luck_pop:
        add esp, 8
    luck_done:
        """
    body += f"""
        mov edx, esi
        mov ecx, edi
        pop edi
        pop esi
        pop ebx
        pop eax
        call {FN_NET:#x}
        jmp {H_MELEE[3]:#x}
    """
    return p1 + asm(body, next_va)


def cave_stash(va, resume):
    return asm(f"""
        call {FN_ADDMOVE:#x}
        mov eax, [ebp-0x64]
        mov [ebp-0x80], eax
        mov dword ptr [ebp-0x84], 1
        jmp {resume:#x}
    """, va)


def cave_rdv(va):
    lines = ["mov edx, [ebp-0x5C]"]
    table = list(RANGED_STUN.items()) + list(RANGED_FREEZE.items())
    for i, (aid, pct) in enumerate(table):
        lines += [f"cmp edx, {aid:#x}", f"jne r1_{i}", f"imul eax, eax, {pct}", "jmp r1_scale", f"r1_{i}:"]
    lines += ["jmp r1_store", "r1_scale:", "push ecx", "cdq", "mov ecx, 100", "idiv ecx", "pop ecx",
              "r1_store:", "mov [ebp-0x28], eax", "cmp dword ptr [ebp-0x28], 0", f"jmp {H_R1[3]:#x}"]
    return asm("\n".join(lines), va)


def cave_rcmp(va):
    return asm(f"""
        mov [ebp-0x64], eax
        cmp dword ptr [ebp-0x84], 1
        jne done
        push ebx
        push esi
        push edi
        push ecx
        push edx
        mov esi, [ebp-0x80]
        mov edi, [ebp-0x64]
        mov eax, [ebp-8]
        imul eax, eax, {s32(0x9E3779B1)}
        mov ebx, eax
        mov eax, [ebp-0xC]
        imul eax, eax, {s32(0x85EBCA6B)}
        xor ebx, eax
        mov eax, [ebp+0x14]
        mov eax, [eax+0x60]
        test eax, eax
        jz no_hs
        push eax
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        imul eax, eax, {s32(0xC2B2AE35)}
        xor ebx, eax
        pop eax
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        imul eax, eax, {s32(0x27D4EB2F)}
        xor ebx, eax
    no_hs:
        mov eax, [ebp+0x10]
        mov edx, [eax]
        call [edx+0x88]
        movsx eax, al
        imul eax, eax, {s32(0x165667B1)}
        xor ebx, eax
        mov eax, [ebp+0x14]
        mov edx, [eax]
        call [edx+0x88]
        movsx eax, al
        imul eax, eax, {s32(0xD3A2646C)}
        xor ebx, eax
        mov eax, [ebp-4]
        mov eax, [eax+0x2C]
        imul eax, eax, {s32(0x2545F491)}
        xor ebx, eax
        mov eax, ebx
        shr eax, 13
        xor ebx, eax
        imul ebx, ebx, {s32(0x5BD1E995)}
        mov eax, ebx
        shr eax, 15
        xor ebx, eax
        mov eax, ebx
        xor edx, edx
        mov ecx, 100
        div ecx
        xor ecx, ecx
        cmp edx, {FLIP_PCT}
        jae noflip
        push edx
        mov eax, [ebp+0x14]
        mov eax, [eax+0x4C]
        mov edx, [eax]
        call [edx+0x114]
        test al, al
        jz flip_elig
        mov eax, [ebp+0x14]
        mov edx, [eax]
        call [edx+0xA0]
        movzx eax, al
        cmp eax, {FLIP_MIN_LEVEL}
        jge flip_elig
        pop edx
        jmp noflip
    flip_elig:
        pop edx
        test esi, esi
        jle noflip
        test edi, edi
        jle noflip
        mov ecx, 1
    noflip:
        cmp dword ptr [ebp-0x1C], 1
        jg far
        test ecx, ecx
        jnz adj_flip
        cmp esi, edi
        jle done_pop
        mov eax, esi
        test eax, eax
        jle adj_neg
        imul eax, eax, {ADJ_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        jmp setr
    adj_neg:
        lea eax, [esi-1]
        jmp setr
    adj_flip:
        cmp esi, edi
        jl adj_flip_r
        mov eax, esi
        imul eax, eax, {ADJ_FLIP_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        inc eax
        jmp setr
    adj_flip_r:
        mov eax, esi
        imul eax, eax, {ADJ_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        jmp setr
    far:
        test edi, edi
        jle done_pop
        mov eax, edi
        imul eax, eax, {FAR_RATIO}
        xor edx, edx
        cmp esi, eax
        jl not_dom
        mov edx, 1
    not_dom:
        xor edx, ecx
        test edx, edx
        jz done_pop
        mov eax, edi
        imul eax, eax, {FAR_PCT}
        cdq
        mov ecx, 100
        idiv ecx
    setr:
        mov [ebp-0x64], eax
    done_pop:
        pop edx
        pop ecx
        pop edi
        pop esi
        pop ebx
    done:
        mov eax, [ebp+0x10]
        jmp {H_R2[3]:#x}
    """, va)


def build_all():
    """-> list of (hook, cave_va, cave_bytes) laid out from CAVE_BASE, 16-aligned."""
    va = CAVE_BASE
    out = []
    for hook, builder in ((H_ENTRY, cave_entry), (H_MELEE, cave_melee),
                          (H_S1, lambda v: cave_stash(v, H_S1[3])), (H_S2, lambda v: cave_stash(v, H_S2[3])),
                          (H_R1, cave_rdv), (H_R2, cave_rcmp)):
        c = builder(va)
        out.append((hook, va, c))
        va = (va + len(c) + 15) & ~15
    assert va <= CAVE_END, "caves overflow the reserved zone"
    return out


# ---- PE helpers ----------------------------------------------------------------------------
def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    out = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        out.append((s[:8].rstrip(b"\0").decode(),) + struct.unpack_from("<IIII", s, 8))
    return out


def va2off(d, va):
    for name, vs, va0, rs, ra in sections(d):
        if va0 <= va - BASE < va0 + max(vs, rs):
            return ra + (va - BASE - va0)
    raise ValueError(hex(va))


def relocs(d):
    for name, vs, va0, rs, ra in sections(d):
        if name != ".reloc":
            continue
        p, end = ra, ra + rs
        while p + 8 <= end:
            pr, sz = struct.unpack_from("<II", d, p)
            if sz == 0:
                break
            for q in range(p + 8, p + sz, 2):
                w = struct.unpack_from("<H", d, q)[0]
                if w >> 12 == 3:
                    yield BASE + pr + (w & 0xFFF)
            p += sz


def branch_into_displaced(d, hooks):
    """any rel8/rel32 branch elsewhere in CODE landing strictly inside a displaced range?"""
    name, vs, va0, rs, ra = [s for s in sections(d) if s[0] == "CODE"][0]
    ranges = [(h[1], h[1] + len(h[2])) for h in hooks]
    bad = []
    for o in range(ra, ra + rs - 6):
        va = BASE + va0 + (o - ra)
        if any(lo <= va < hi for lo, hi in ranges):
            continue
        b = d[o]
        if b in (0xE8, 0xE9):
            t = va + 5 + struct.unpack_from("<i", d, o + 1)[0]
        elif b == 0x0F and 0x80 <= d[o + 1] <= 0x8F:
            t = va + 6 + struct.unpack_from("<i", d, o + 2)[0]
        elif b == 0xEB or 0x70 <= b <= 0x7F:
            t = va + 2 + struct.unpack_from("<b", d, o + 1)[0]
        else:
            continue
        for lo, hi in ranges:
            if lo < t < hi:
                bad.append((va, t))
    return bad


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data)


def main():
    ap = argparse.ArgumentParser(description="tactical AI melee-vs-ranged rebalance")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        bak = open(bak_path(dll, BAK), "rb").read()
        assert len(bak) == os.path.getsize(dll), "size differs from backup; refusing"
        write_inplace(dll, bak); print("restored AoWTCPCK.dll from" + BAK); return 0

    d = bytearray(open(dll, "rb").read())
    plan = build_all()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for hook, cva, c in plan:
            print("--- cave %s @%#x (%d B)" % (hook[0], cva, len(c)))
            for i in md.disasm(c, cva):
                print("   %08x  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    states = set()
    for hook, cva, c in plan:
        name, hva, orig, resume = hook
        ho = va2off(d, hva)
        hookb = b"\xE9" + struct.pack("<i", cva - (hva + 5)) + b"\x90" * (len(orig) - 5)
        cur = bytes(d[ho:ho + len(orig)])
        co = va2off(d, cva)
        if cur == hookb and bytes(d[co:co + len(c)]) == c:
            st = "patched"
        elif cur == hookb:
            st = "stale"          # hooked by an older build of this script: caves get rewritten in place
        elif cur == orig:
            st = "vanilla"
        else:
            print("%s @%#x: unexpected bytes %s" % (name, hva, cur.hex())); return 1
        states.add(st)
        print("%-15s hook %#x (%s) -> cave %#x %3d B" % (name, hva, st, cva, len(c)))
    if states == {"patched"}:
        print("ALL ALREADY PATCHED"); return 0
    stale = "stale" in states
    assert states == {"vanilla"} or (stale and "vanilla" not in states), "mixed state - inspect"
    lo, hi = va2off(d, CAVE_BASE), va2off(d, CAVE_END)
    if stale:
        print("stale caves from an older build: will rewrite the cave zone in place (hooks unchanged)")
    else:
        assert bytes(d[lo:hi]) == b"\0" * (hi - lo), "cave zone not zero"
    ranges = [(h[1], h[1] + len(h[2])) for h in HOOKS] + [(CAVE_BASE, CAVE_END)]
    r = [hex(v) for v in relocs(d) if any(lo_ <= v < hi_ or lo_ < v + 4 <= hi_ for lo_, hi_ in ranges)]
    assert not r, "relocs intersect: " + ", ".join(r)
    bad = branch_into_displaced(d, HOOKS)
    assert not bad, "branches into displaced bytes: " + ", ".join("%#x->%#x" % b for b in bad)
    print("checks OK: vanilla sites, zero caves, no relocs, no branches into displaced bytes")
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWTCPCK.dll" + BAK)
    if stale:
        d[lo:hi] = b"\0" * (hi - lo)
    for hook, cva, c in plan:
        name, hva, orig, resume = hook
        ho, co = va2off(d, hva), va2off(d, cva)
        d[ho:ho + len(orig)] = b"\xE9" + struct.pack("<i", cva - (hva + 5)) + b"\x90" * (len(orig) - 5)
        d[co:co + len(c)] = c
    write_inplace(dll, bytes(d))
    back = open(dll, "rb").read()
    for hook, cva, c in plan:
        co = va2off(back, cva)
        assert back[co:co + len(c)] == c and back[va2off(back, hook[1])] == 0xE9, "read-back failed"
    print("applied.  Tunables: strikes %s (def side %s), hero retal %d%%, leader retal %d%%, ranged stun %s freeze %s,"
          " adj %d%%/%d%%, far ratio %d -> %d%%, flip %d%%" % (STRIKE_BONUS, DEF_SIDE, HERO_RETAL_PCT, LEADER_RETAL_PCT,
          RANGED_STUN, RANGED_FREEZE, ADJ_PCT, ADJ_FLIP_PCT, FAR_RATIO, FAR_PCT, FLIP_PCT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
