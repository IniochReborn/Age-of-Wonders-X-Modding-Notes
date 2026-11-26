#!/usr/bin/env python3
r"""
Tactical AI: Healing priority rework (AoWTCPCK.dll, 2026-09-16) -- part 2 of the "AI healing priority" work.
Companion: patch_heal_ai_epack_v1.py (AoWEPACK: level-aware amount + Poisoned cure value, and it parks the raw
heal amount in the valuation record at +0xC = [ebp-0x9C] in CheckUnit).  This script works without it
(amount then defaults to 5) but the pair is the intended install.

RE facts (all verified 2026-09-16, see memory aowx-tactical-ai-scoring):
  TCAI.CheckUnit @0x4152A8 frame: [ebp-4] cai, [ebp+0x10] TARGET, [ebp+0x14] SELF (mover; +0x5C = remaining
  move points), [ebp-0x5C] ability id, [ebp-0x64] DEV, [ebp-0x68] path list, [ebp-0x89] adjacent flag,
  [ebp-0x10] hero position-safety score, [ebp-0x14] AddMove pct, [ebp-0xA8] valuation record (DV, +4 hp,
  +8 retaliation DV, +0xC raw amount [EPACK patch]).  Free slots used here: [ebp-0x7C] flags, [ebp-0x98] log
  record, [ebp-0xA0] touch value (record+8, dead after 0x416EDD).
  TCombatUnit (live class TTacticalCombatUnit, instance size 0x68): HP is NOT a field - VMT+0x84 GetHits (max)
  / VMT+0x88 GetHitPoints (cur), byte results (movsx al); the 2026-09-16 build read [obj+0x84]/[obj+0x88] as
  fields = out-of-bounds garbage -> "Error during Touch Check" (fixed 2026-09-17).  In CheckUnit's frame the
  caller already passes target max/cur as [ebp+0x1C]/[ebp+0x20].  +0x47 bit0|bit3 = dead/fled, +0x4C strategic unit,
  +0x5C remaining moves, +0x60 hex-space object (VMT+0x74/+0x78/+0x7C = x/y/z).  VMT+0x5C GetTargetStrength,
  +0x78 GetDamage, +0x94 GetMoves.
  Lists: [cai+8] own units (heroes last), [cai+0x10] enemies, [cai+0x14] moves.  Phase machine: one move
  executed per cycle, everything re-evaluated after.
  Vanilla healing: DV = 100*min(5,missing); value = strength(T)*DV/100 *2 hero *2 leader, * maxHP/curHP (so a
  badly wounded low-value unit dominates), then AddMove pct = 1 (!) when the healer is a hero, 100 otherwise.
  Heroes skip every target loop once any unit proposed an attack ([cai+0x2C]); self as a target never
  reaches the ability loop (path to self = -1).

Patch (all caves position-independent: rel32 + call/pop delta for the four global reads):
  A  0x416F6A  after the net combiner, healing only: V = C * (1 + missing/max), then for tier-3 targets:
        hopeless (low-value AND cur+E <= adjacent enemy damage) x HOPELESS_PCT, else danger (cur <= adjacent
        enemy damage) x DANGER_PCT; top-up damping when E < amount/2; party reservation R = best expected
        alternative heal among the other own units (hurt: full weight; unhurt: enemy/own strength ratio with
        round decay); V *= clamp(V/R, FLOOR, 1), FLOOR_HOLD when the alternative is a hero/leader missing
        >= amount.  Tiers (target hero/leader): 1 = missing >= T1_PCT% of max, 2 = missing >= amount.
        Vanilla's max/cur multiplier is bypassed (pct 1, divisor 1).
  C  0x4171A2  a hero/leader healer with a tier-1/2 target that is adjacent ignores the position-danger gate
        (which otherwise turns the heal into a deleted temp record).
  B  0x4171DD  AddMove pct for hero/leader movers: heal tier 1/2 = 100 (self-heal tier 1 = SELF_T1_PCT),
        heal tier 3 = HERO_HEAL_PCT, any other touch ability = HERO_TOUCH_PCT (vanilla: 1 for all).
  E  0x41726C  after the heal touch move of a hero/leader (tier 1/2, target != self): retreat-and-heal --
        best adjacent-to-target hex that is out of more enemies' reach (reach = moves/HEX_MP + 1), reachable
        for <= moves-HEAL_MP, unoccupied, and only when no living enemy is adjacent to the healer (no AoO);
        proposed as a type-0 move worth RETREAT_PCT% of the heal + 1 (the heal itself follows next cycle).
  F  0x419212  hero/leader SELF-heal: proposed directly from the friendly-target phase (CheckUnit cannot
        evaluate self): CanTouch + valuation via the ability, same scoring, AddMove type 1 on own hex, plus
        the retreat search within RETREAT_RADIUS when tier 1/2.
  G  0x4191AE  hero gate removed for the FRIENDLY target loop only (jne -> nop nop).
Log: ring buffer in BSS page slack (REC), one 32-B record per healing evaluation; --read dumps it from the
running game.  Backup AoWTCPCK.dll.bak_healai.  Caves 0x439100.. (zero-verified).  Dry-run default;
--apply; --revert; --dis; --read.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_healai"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x400000

# ---- tunables -------------------------------------------------------------------------------
T1_PCT = 40            # tier 1: hero/leader target missing >= this % of max HP
DANGER_PCT = 150       # tier-3 target with cur HP <= adjacent enemies' damage
HOPELESS_PCT = 25      # ... and low value and even the heal does not lift it above that damage
LOWVAL_PCT = 40        # "low value" = strength below this % of the strongest living own unit
FLOOR_PCT = 25         # reservation floor (score never scaled below this % of itself)
FLOOR_HOLD_PCT = 5     # ... when the better alternative is a hero/leader missing >= amount (hold the charge)
DECAY_END = 7          # unhurt-unit reservation weight fades linearly to 0 by this combat round
HERO_HEAL_PCT = 25     # hero/leader healing an ordinary unit (tier 3)
HERO_TOUCH_PCT = 50    # hero/leader using any other touch ability (Dominate, Seduce, Web ...)
SELF_T1_PCT = 200      # hero/leader self-heal at tier 1
HEAL_MP = 3            # move points a heal needs after the retreat
HEX_MP = 4             # move points per hex (enemy reach estimate)
RETREAT_RADIUS = 2     # self-heal retreat search radius (hexes)
RETREAT_PCT = 110      # retreat move value as % of the heal it prepares (+1)
REC_N = 44             # log ring size (10/18: was 60 - the ring ran to 0x46CF90 over Oil Spring's VMT clone 0x46CDC0..0x46CF10; live fix = patch_tcpck_slack_fix_v1.py)

# ---- engine facts ---------------------------------------------------------------------------
ISCLASS, DHX, NET, ADDMOVE = 0x401058, 0x4022A4, 0x413664, 0x4135B8
NEWOBJ, SETSTART, SETDEST, MOVETYPES, UNITFLAG = 0x40263C, 0x40266C, 0x402674, 0x4029BC, 0x402544
PATHEVAL, LISTGET_PATH, FREEOBJ, MAPLAYER, MAPCELL, GETABIL = 0x413BD0, 0x401B1C, 0x401050, 0x401E64, 0x401E54, 0x402704
IAT_THERO, IAT_TLEADER, G_MAP, G_ABILCTL, CLS_PATHCTX = 0x46E914, 0x46E910, 0x46C064, 0x46E8D0, 0x4129A8
REC = 0x46C800         # BSS page slack (BSS vsz ends 0x46C0A1, page runs to 0x46D000)
CAVE_BASE, CAVE_END = 0x439100, 0x43A400

H_A = ("score", 0x416F6A, bytes.fromhex("8bd08b4d1c8b45fc"), 0x416F72)
H_C = ("gate-c", 0x4171A2, bytes.fromhex("8b4598837808010f8efe010000837df0007d0d8b45fc"), 0x4171B8)
H_B = ("pct", 0x4171DD, bytes.fromhex("8b45148b404c"), 0x4171E3)
H_E = ("retreat", 0x41726C, bytes.fromhex("e847c3ffff"), 0x417271)
H_F = ("selfheal", 0x419212, bytes.fromhex("8b45d0e8367efeff"), 0x41921A)
HOOKS = [H_A, H_C, H_B, H_E, H_F]
GATE = (0x4191AE, bytes.fromhex("7556"), bytes.fromhex("9090"))
ABILLOOP_NEXT = (0x418053, bytes.fromhex("ff45e0"))   # sanity: ability-loop continue point
BOUNDS_VA = 0x4180A8                                   # bound pair for hex coords

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def pic(va, pre):
    """emit `pre` then `call next`; returns (bytes, next_va).  Body must start with `pop ebx / sub ebx, next_va`."""
    p = asm(pre, va) if pre.strip() else b""
    call_at = va + len(p)
    next_va = call_at + 5
    p += asm(f"call {next_va:#x}", call_at)
    return p, next_va


# ---- subroutines (ebx = load delta, set by the caller) ---------------------------------------
def sub_pos(va):
    return asm("""
        push esi
        mov esi, [eax+0x60]
        mov eax, esi
        mov edx, [esi]
        call [edx+0x74]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, [esi]
        call [edx+0x78]
        movsx edx, al
        pop eax
        pop esi
        ret
    """, va)


def sub_distxy(va, S):
    return asm(f"""
        push ebp
        mov ebp, esp
        mov eax, [ebp+8]
        call {S['pos']:#x}
        push edx
        mov ecx, eax
        mov eax, [ebp+0xC]
        mov edx, [ebp+0x10]
        call {DHX:#x}
        pop ebp
        ret
    """, va)


def sub_dist(va, S):
    return asm(f"""
        push ebp
        mov ebp, esp
        mov eax, [ebp+0xC]
        call {S['pos']:#x}
        push edx
        push eax
        push dword ptr [ebp+8]
        call {S['distxy']:#x}
        add esp, 12
        pop ebp
        ret
    """, va)


def sub_reach(va, S):
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 8
        push esi
        push edi
        mov dword ptr [ebp-4], 0x7FFF
        xor edi, edi
    r_loop:
        mov eax, [ebp+8]
        mov eax, [eax+0x10]
        cmp edi, [eax+8]
        jge r_end
        mov eax, [eax+4]
        mov esi, [eax+edi*4]
        inc edi
        test esi, esi
        jz r_loop
        test byte ptr [esi+0x47], 9
        jnz r_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x94]
        cdq
        mov ecx, {HEX_MP}
        idiv ecx
        inc eax
        mov [ebp-8], eax
        push dword ptr [ebp+0x10]
        push dword ptr [ebp+0xC]
        push esi
        call {S['distxy']:#x}
        add esp, 12
        sub eax, [ebp-8]
        cmp eax, [ebp-4]
        jge r_loop
        mov [ebp-4], eax
        jmp r_loop
    r_end:
        mov eax, [ebp-4]
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """, va)


def sub_pathcost(va, S):
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 0x10
        push esi
        push edi
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+{CLS_PATHCTX:#x}]
        call {NEWOBJ:#x}
        mov esi, eax
        mov eax, [ebp+0xC]
        mov edi, [eax+0x60]
        mov eax, edi
        mov edx, [edi]
        call [edx+0x7C]
        movsx eax, al
        push eax
        mov eax, edi
        mov edx, [edi]
        call [edx+0x78]
        movsx eax, al
        push eax
        mov eax, edi
        mov edx, [edi]
        call [edx+0x74]
        movsx edx, al
        pop ecx
        mov eax, esi
        call {SETSTART:#x}
        push 0
        mov edx, [ebp+0x10]
        mov ecx, [ebp+0x14]
        mov eax, esi
        call {SETDEST:#x}
        mov [esi+0x9C], edi
        mov byte ptr [esi+0x1AC], 2
        lea edx, [esi+0xAC]
        mov eax, [ebp+0xC]
        mov eax, [eax+0x4C]
        call {MOVETYPES:#x}
        mov eax, [ebp+0xC]
        call {UNITFLAG:#x}
        mov [esi+0x6C], al
        mov eax, [ebx+{G_MAP:#x}]
        mov eax, [eax+0xFC]
        mov edx, esi
        mov ecx, [eax]
        call [ecx+4]
        mov eax, [esi+0x68]
        cmp dword ptr [eax+8], 2
        jl pc_fail
        lea eax, [ebp-8]
        push eax
        push dword ptr [ebp+0xC]
        push 0
        push 0
        push 0
        push 0
        lea ecx, [esi+0x68]
        mov edx, esi
        mov eax, [ebp+8]
        call {PATHEVAL:#x}
        cmp eax, -1
        je pc_fail
        mov eax, [esi+0x68]
        mov edx, [eax+8]
        sub edx, 2
        call {LISTGET_PATH:#x}
        shr eax, 24
        movsx eax, al
        test eax, eax
        jle pc_fail
        mov [ebp-0xC], eax
        mov eax, esi
        call {FREEOBJ:#x}
        mov eax, [ebp-0xC]
        jmp pc_out
    pc_fail:
        mov eax, esi
        call {FREEOBJ:#x}
        mov eax, -1
    pc_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """, va)


def sub_retreat(va, S, lo, hi):
    R = RETREAT_RADIUS
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 0x20
        push esi
        push edi
        mov dword ptr [ebp-4], -1
        mov eax, [ebp+0xC]
        call {S['pos']:#x}
        mov [ebp-0xC], eax
        mov [ebp-0x10], edx
        xor edi, edi
    rt_adj:
        mov eax, [ebp+8]
        mov eax, [eax+0x10]
        cmp edi, [eax+8]
        jge rt_adj_ok
        mov eax, [eax+4]
        mov esi, [eax+edi*4]
        inc edi
        test esi, esi
        jz rt_adj
        test byte ptr [esi+0x47], 9
        jnz rt_adj
        push dword ptr [ebp+0xC]
        push esi
        call {S['dist']:#x}
        add esp, 8
        cmp eax, 1
        jle rt_fail
        jmp rt_adj
    rt_adj_ok:
        push dword ptr [ebp-0x10]
        push dword ptr [ebp-0xC]
        push dword ptr [ebp+8]
        call {S['reach']:#x}
        add esp, 12
        mov [ebp-8], eax
        mov dword ptr [ebp-0x18], {-R}
    rt_dy:
        mov dword ptr [ebp-0x14], {-R}
    rt_dx:
        mov eax, [ebp+0x10]
        add eax, [ebp-0x14]
        mov [ebp-0x1C], eax
        mov eax, [ebp+0x14]
        add eax, [ebp-0x18]
        mov [ebp-0x20], eax
        cmp dword ptr [ebp-0x1C], {lo}
        jl rt_next
        cmp dword ptr [ebp-0x1C], {hi}
        jg rt_next
        cmp dword ptr [ebp-0x20], {lo}
        jl rt_next
        cmp dword ptr [ebp-0x20], {hi}
        jg rt_next
        mov eax, [ebp-0x1C]
        cmp eax, [ebp-0xC]
        jne rt_d
        mov eax, [ebp-0x20]
        cmp eax, [ebp-0x10]
        je rt_next
    rt_d:
        push dword ptr [ebp+0x14]
        mov eax, [ebp-0x1C]
        mov edx, [ebp-0x20]
        mov ecx, [ebp+0x10]
        call {DHX:#x}
        cmp dword ptr [ebp+0x18], 0
        jne rt_mode1
        test eax, eax
        jz rt_next
        cmp eax, {R}
        jg rt_next
        jmp rt_occ
    rt_mode1:
        cmp eax, 1
        jne rt_next
    rt_occ:
        mov eax, [ebx+{G_MAP:#x}]
        mov eax, [eax+0x10]
        xor edx, edx
        call {MAPLAYER:#x}
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call {MAPCELL:#x}
        test eax, eax
        jz rt_next
        mov esi, eax
        mov edx, 0x220104
        mov ecx, [esi]
        call [ecx+0x80]
        test eax, eax
        jnz rt_next
        mov eax, esi
        mov edx, 0x220504
        mov ecx, [esi]
        call [ecx+0x80]
        test eax, eax
        jnz rt_next
        mov eax, esi
        mov edx, 0x220506
        mov ecx, [esi]
        call [ecx+0x80]
        test eax, eax
        jnz rt_next
        push dword ptr [ebp-0x20]
        push dword ptr [ebp-0x1C]
        push dword ptr [ebp+8]
        call {S['reach']:#x}
        add esp, 12
        cmp eax, [ebp-8]
        jle rt_next
        mov edi, eax
        push dword ptr [ebp-0x20]
        push dword ptr [ebp-0x1C]
        push dword ptr [ebp+0xC]
        push dword ptr [ebp+8]
        call {S['pathcost']:#x}
        add esp, 16
        test eax, eax
        jle rt_next
        cmp eax, [ebp+0x1C]
        jg rt_next
        mov [ebp-8], edi
        mov eax, [ebp-0x20]
        shl eax, 8
        or eax, [ebp-0x1C]
        mov [ebp-4], eax
    rt_next:
        inc dword ptr [ebp-0x14]
        cmp dword ptr [ebp-0x14], {R}
        jle rt_dx
        inc dword ptr [ebp-0x18]
        cmp dword ptr [ebp-0x18], {R}
        jle rt_dy
        mov eax, [ebp-4]
        jmp rt_out
    rt_fail:
        mov eax, -1
    rt_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """, va)


def sub_log(va):
    return asm(f"""
        push ebp
        mov ebp, esp
        push esi
        mov eax, [ebx+{REC:#x}]
        inc dword ptr [ebx+{REC:#x}]
        xor edx, edx
        mov ecx, {REC_N}
        div ecx
        imul edx, edx, 32
        lea esi, [ebx+{REC + 0x10:#x}]
        add esi, edx
        mov eax, [ebp+8]
        mov [esi], eax
        mov eax, [ebp+0xC]
        mov [esi+4], eax
        mov eax, [ebp+0x10]
        mov [esi+8], eax
        mov eax, [ebp+0x14]
        mov [esi+0xC], eax
        mov eax, [ebp+0x18]
        mov [esi+0x10], eax
        mov eax, [ebp+0x1C]
        mov [esi+0x14], eax
        push edi
        mov eax, [ebp+0xC]
        mov edx, [eax]
        call [edx+0x84]
        movsx edi, al
        mov eax, [ebp+0xC]
        mov edx, [eax]
        call [edx+0x88]
        movsx eax, al
        mov ecx, eax
        and ecx, 0xFF
        mov edx, edi
        and edx, 0xFF
        shl edx, 8
        or ecx, edx
        mov edx, [ebp+0x20]
        and edx, 0xFF
        shl edx, 16
        or ecx, edx
        mov edx, edi
        sub edx, eax
        and edx, 0xFF
        shl edx, 24
        or ecx, edx
        mov [esi+0x18], ecx
        pop edi
        mov dword ptr [esi+0x1C], -1
        mov eax, esi
        pop esi
        pop ebp
        ret
    """, va)


def sub_value(va, S):
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 0x30
        push esi
        push edi
        mov dword ptr [ebp-8], 0x10
        mov eax, [ebp+0x10]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jz v_t1
        or dword ptr [ebp-8], 0x20
    v_t1:
        mov eax, [ebp+0x10]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jz v_t2
        or dword ptr [ebp-8], 0x60
    v_t2:
        mov eax, [ebp+0xC]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jnz v_s1
        mov eax, [ebp+0xC]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jz v_s2
    v_s1:
        or dword ptr [ebp-8], 4
    v_s2:
        mov eax, [ebp+0xC]
        cmp eax, [ebp+0x10]
        jne v_s3
        or dword ptr [ebp-8], 8
    v_s3:
        test dword ptr [ebp-8], 0x20
        jz v_tier_done
        mov ecx, [ebp+0x28]
        test ecx, ecx
        jle v_tier_done
        mov eax, [ebp+0x20]
        imul eax, eax, 100
        imul ecx, ecx, {T1_PCT}
        cmp eax, ecx
        jl v_tier2
        or dword ptr [ebp-8], 1
        jmp v_tier_done
    v_tier2:
        mov eax, [ebp+0x20]
        cmp eax, [ebp+0x18]
        jl v_tier_done
        or dword ptr [ebp-8], 2
    v_tier_done:
        mov eax, [ebp+0x14]
        mov [ebp-4], eax
        mov dword ptr [ebp-0xC], -1
        mov ecx, [ebp+0x28]
        test ecx, ecx
        jle v_w_done
        mov eax, [ebp+0x20]
        imul eax, eax, 100
        cdq
        idiv ecx
        add eax, 100
        mov ecx, eax
        mov eax, [ebp-4]
        imul ecx
        mov ecx, 100
        idiv ecx
        mov [ebp-4], eax
    v_w_done:
        test dword ptr [ebp-8], 3
        jnz v_done
        cmp dword ptr [ebp-4], 0
        jle v_done
        xor eax, eax
        mov [ebp-0x14], eax
        mov [ebp-0x18], eax
        mov [ebp-0x24], eax
        mov [ebp-0x28], eax
        mov [ebp-0x1C], eax
    v_own_loop:
        mov eax, [ebp+8]
        mov eax, [eax+8]
        mov ecx, [ebp-0x1C]
        cmp ecx, [eax+8]
        jge v_own_end
        mov eax, [eax+4]
        mov esi, [eax+ecx*4]
        inc dword ptr [ebp-0x1C]
        test esi, esi
        jz v_own_loop
        test byte ptr [esi+0x47], 9
        jnz v_own_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x5C]
        test eax, eax
        jle v_own_loop
        add [ebp-0x24], eax
        cmp eax, [ebp-0x14]
        jle v_own_loop
        mov [ebp-0x14], eax
        jmp v_own_loop
    v_own_end:
        xor eax, eax
        mov [ebp-0x1C], eax
    v_en_loop:
        mov eax, [ebp+8]
        mov eax, [eax+0x10]
        mov ecx, [ebp-0x1C]
        cmp ecx, [eax+8]
        jge v_en_end
        mov eax, [eax+4]
        mov esi, [eax+ecx*4]
        inc dword ptr [ebp-0x1C]
        test esi, esi
        jz v_en_loop
        test byte ptr [esi+0x47], 9
        jnz v_en_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x5C]
        test eax, eax
        jle v_en_s
        add [ebp-0x28], eax
    v_en_s:
        push dword ptr [ebp+0x10]
        push esi
        call {S['dist']:#x}
        add esp, 8
        cmp eax, 1
        jg v_en_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x78]
        movsx eax, al
        add [ebp-0x18], eax
        jmp v_en_loop
    v_en_end:
        mov eax, [ebp+0x10]
        mov edx, [eax]
        call [edx+0x5C]
        imul eax, eax, 100
        mov ecx, [ebp-0x14]
        imul ecx, ecx, {LOWVAL_PCT}
        cmp eax, ecx
        jge v_danger
        cmp dword ptr [ebp-0x18], 0
        jle v_damp
        mov eax, [ebp+0x24]
        add eax, [ebp+0x1C]
        cmp eax, [ebp-0x18]
        jg v_danger
        mov eax, [ebp-4]
        imul eax, eax, {HOPELESS_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        mov [ebp-4], eax
        jmp v_damp
    v_danger:
        cmp dword ptr [ebp-0x18], 0
        jle v_damp
        mov eax, [ebp+0x24]
        cmp eax, [ebp-0x18]
        jg v_damp
        mov eax, [ebp-4]
        imul eax, eax, {DANGER_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        mov [ebp-4], eax
    v_damp:
        mov eax, [ebp+0x1C]
        add eax, eax
        cmp eax, [ebp+0x18]
        jge v_resv
        mov eax, [ebp+0x1C]
        imul eax, eax, 200
        cdq
        idiv dword ptr [ebp+0x18]
        mov [ebp-0x2C], eax
        mov eax, [ebp-4]
        imul dword ptr [ebp-0x2C]
        mov ecx, 100
        idiv ecx
        imul dword ptr [ebp-0x2C]
        idiv ecx
        mov [ebp-4], eax
    v_resv:
        xor eax, eax
        mov [ebp-0x20], eax
        mov ecx, [ebp-0x24]
        test ecx, ecx
        jle v_w_ok
        mov eax, [ebp-0x28]
        imul eax, eax, 100
        cdq
        idiv ecx
        cmp eax, 100
        jle v_w1
        mov eax, 100
    v_w1:
        mov ecx, [ebx+{G_MAP:#x}]
        mov ecx, [ecx+0x134]
        mov edx, {DECAY_END}
        sub edx, ecx
        jle v_w_ok
        imul edx, edx, 100
        mov ecx, eax
        mov eax, edx
        cdq
        push ecx
        mov ecx, {DECAY_END - 1}
        idiv ecx
        pop ecx
        cmp eax, 100
        jle v_w2
        mov eax, 100
    v_w2:
        imul eax, ecx
        cdq
        mov ecx, 100
        idiv ecx
        mov [ebp-0x20], eax
    v_w_ok:
        xor eax, eax
        mov [ebp-0xC], eax
        mov [ebp-0x10], eax
        mov [ebp-0x1C], eax
    v_r_loop:
        mov eax, [ebp+8]
        mov eax, [eax+8]
        mov ecx, [ebp-0x1C]
        cmp ecx, [eax+8]
        jge v_r_end
        mov eax, [eax+4]
        mov esi, [eax+ecx*4]
        inc dword ptr [ebp-0x1C]
        test esi, esi
        jz v_r_loop
        cmp esi, [ebp+0x10]
        je v_r_loop
        test byte ptr [esi+0x47], 9
        jnz v_r_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x5C]
        test eax, eax
        jle v_r_loop
        imul eax, dword ptr [ebp+0x18]
        mov [ebp-0x2C], eax
        mov eax, esi
        mov edx, [esi]
        call [edx+0x84]
        movsx edi, al
        mov eax, esi
        mov edx, [esi]
        call [edx+0x88]
        movsx eax, al
        sub edi, eax
        mov [ebp-0x30], edi
        xor edi, edi
        mov eax, [esi+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jz v_r_nh
        shl dword ptr [ebp-0x2C], 1
        mov edi, 1
    v_r_nh:
        mov eax, [esi+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jz v_r_nl
        shl dword ptr [ebp-0x2C], 1
        mov edi, 1
    v_r_nl:
        mov ecx, 100
        cmp dword ptr [ebp-0x30], 0
        jg v_r_w
        mov ecx, [ebp-0x20]
    v_r_w:
        mov eax, [ebp-0x2C]
        imul ecx
        mov ecx, 100
        idiv ecx
        cmp eax, [ebp-0xC]
        jle v_r_loop
        mov [ebp-0xC], eax
        xor ecx, ecx
        test edi, edi
        jz v_r_h
        mov eax, [ebp-0x30]
        cmp eax, [ebp+0x18]
        jl v_r_h
        mov ecx, 1
    v_r_h:
        mov [ebp-0x10], ecx
        jmp v_r_loop
    v_r_end:
        mov ecx, [ebp-0xC]
        test ecx, ecx
        jle v_done
        mov eax, [ebp-4]
        cmp eax, ecx
        jge v_done
        imul eax, eax, 100
        cdq
        idiv ecx
        mov ecx, {FLOOR_PCT}
        cmp dword ptr [ebp-0x10], 0
        je v_fl
        mov ecx, {FLOOR_HOLD_PCT}
    v_fl:
        cmp eax, ecx
        jge v_q
        mov eax, ecx
    v_q:
        mov ecx, eax
        mov eax, [ebp-4]
        imul ecx
        mov ecx, 100
        idiv ecx
        mov [ebp-4], eax
    v_done:
        mov eax, [ebp-4]
        mov edx, [ebp-8]
        mov ecx, [ebp-0xC]
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """, va)


# ---- hook caves -----------------------------------------------------------------------------
def build_cave_a(va, S):
    head = asm(f"""
        cmp dword ptr [ebp-0x5C], 0x2F
        je a_go
        mov edx, eax
        mov ecx, [ebp+0x1C]
        mov eax, [ebp-4]
        jmp {H_A[3]:#x}
    a_go:
        push eax
        push ebx
        push esi
        push edi
    """, va)
    call_at = va + len(head)
    nva = call_at + 5
    head += asm(f"call {nva:#x}", call_at)
    body = asm(f"""
        pop ebx
        sub ebx, {nva:#x}
        mov edi, [esp+12]
        mov eax, [ebp-0x9C]
        test eax, eax
        jg a_ok
        mov dword ptr [ebp-0x9C], 5
    a_ok:
        mov ecx, [ebp+0x1C]
        mov edx, [ebp+0x20]
        push ecx
        push edx
        sub ecx, edx
        push ecx
        push dword ptr [ebp-0xA4]
        push dword ptr [ebp-0x9C]
        push edi
        push dword ptr [ebp+0x10]
        push dword ptr [ebp+0x14]
        push dword ptr [ebp-4]
        call {S['value']:#x}
        add esp, 0x24
        mov [ebp-0x7C], edx
        mov esi, eax
        push dword ptr [ebp-0x9C]
        push edx
        push ecx
        push esi
        push edi
        push dword ptr [ebp+0x10]
        push dword ptr [ebp+0x14]
        call {S['log']:#x}
        add esp, 0x1C
        mov [ebp-0x98], eax
        mov edx, esi
        pop edi
        pop esi
        pop ebx
        add esp, 4
        mov ecx, 1
        mov dword ptr [esp], 1
        mov eax, [ebp-4]
        jmp {H_A[3]:#x}
    """, nva)
    return head + body


def build_cave_c(va, S):
    return asm(f"""
        mov eax, [ebp-0x68]
        cmp dword ptr [eax+8], 1
        jle c_skip
        cmp dword ptr [ebp-0x5C], 0x2F
        jne c_van
        mov eax, [ebp-0x7C]
        test eax, 0x10
        jz c_van
        test eax, 3
        jz c_van
        test eax, 4
        jz c_van
        cmp byte ptr [ebp-0x89], 0
        je c_van
        jmp 0x4171C2
    c_van:
        cmp dword ptr [ebp-0x10], 0
        jge 0x4171C2
        mov eax, [ebp-4]
        jmp {H_C[3]:#x}
    c_skip:
        jmp 0x4173AD
    """, va)


def build_cave_b(va, S):
    head = asm("push ebx", va)
    call_at = va + len(head)
    nva = call_at + 5
    head += asm(f"call {nva:#x}", call_at)
    body = asm(f"""
        pop ebx
        sub ebx, {nva:#x}
        mov eax, [ebp+0x14]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jnz b_hero
        mov eax, [ebp+0x14]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jnz b_hero
        pop ebx
        jmp 0x4171FB
    b_hero:
        cmp dword ptr [ebp-0x5C], 0x2F
        jne b_touch
        mov eax, [ebp-0x7C]
        test eax, 0x10
        jz b_touch
        mov ecx, {HERO_HEAL_PCT}
        test eax, 3
        jz b_set
        mov ecx, 100
        test eax, 1
        jz b_set
        test eax, 8
        jz b_set
        mov ecx, {SELF_T1_PCT}
        jmp b_set
    b_touch:
        mov ecx, {HERO_TOUCH_PCT}
        mov [ebp-0x14], ecx
        pop ebx
        jmp 0x41723F
    b_set:
        mov [ebp-0x14], ecx
        mov eax, [ebp-0x98]
        test eax, eax
        jz b_nolog
        mov edx, ecx
        shl edx, 16
        or [eax+0x14], edx
    b_nolog:
        pop ebx
        jmp 0x41723F
    """, nva)
    return head + body


def build_cave_e(va, S):
    head = asm(f"""
        mov eax, [esp+0x10]
        mov [ebp-0xA0], eax
        mov eax, [ebp-4]
        call {ADDMOVE:#x}
        cmp dword ptr [ebp-0x5C], 0x2F
        jne e_out
        mov eax, [ebp-0x7C]
        test eax, 0x10
        jz e_out
        test eax, 3
        jz e_out
        test eax, 4
        jz e_out
        test eax, 8
        jnz e_out
        push ebx
        push esi
        push edi
        jmp e_pic
    e_out:
        jmp {H_E[3]:#x}
    e_pic:
    """, va)
    call_at = va + len(head)
    nva = call_at + 5
    head += asm(f"call {nva:#x}", call_at)
    body = asm(f"""
        pop ebx
        sub ebx, {nva:#x}
        mov eax, [ebp+0x14]
        mov eax, [eax+0x5C]
        sub eax, {HEAL_MP}
        jle e_done
        push eax
        push 1
        mov eax, [ebp+0x10]
        call {S['pos']:#x}
        push edx
        push eax
        push dword ptr [ebp+0x14]
        push dword ptr [ebp-4]
        call {S['retreat']:#x}
        add esp, 0x18
        cmp eax, -1
        je e_done
        mov esi, eax
        mov eax, [ebp-0xA0]
        imul eax, eax, {RETREAT_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        inc eax
        mov edx, esi
        shr edx, 8
        push edx
        push eax
        push 0x2F
        push 0
        push dword ptr [ebp+0x14]
        push dword ptr [ebp+0x10]
        mov ecx, esi
        and ecx, 0xFF
        xor edx, edx
        mov eax, [ebp-4]
        call {ADDMOVE:#x}
        mov eax, [ebp-0x98]
        test eax, eax
        jz e_done
        mov [eax+0x1C], esi
    e_done:
        pop edi
        pop esi
        pop ebx
        jmp {H_E[3]:#x}
    """, nva)
    return head + body


def build_cave_f(va, S):
    head = asm("push ebx\npush esi\npush edi", va)
    call_at = va + len(head)
    nva = call_at + 5
    head += asm(f"call {nva:#x}", call_at)
    body = asm(f"""
        pop ebx
        sub ebx, {nva:#x}
        mov eax, [ebp-0x28]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jnz f_hero
        mov eax, [ebp-0x28]
        mov eax, [eax+0x4C]
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jz f_done
    f_hero:
        xor edi, edi
    f_l:
        mov eax, [ebp-0x38]
        cmp edi, [eax+8]
        jge f_done
        mov eax, [eax+4]
        mov eax, [eax+edi*4]
        inc edi
        test eax, eax
        jz f_l
        cmp dword ptr [eax+4], 0x2F
        jne f_l
        mov eax, [ebx+{G_ABILCTL:#x}]
        mov eax, [eax]
        mov eax, [eax+0x80]
        mov edx, 0x2F
        call {GETABIL:#x}
        test eax, eax
        jz f_done
        mov esi, eax
        mov edx, [ebp-0x28]
        mov ecx, edx
        mov edi, [esi]
        call [edi+0x11C]
        test al, al
        jz f_done
        sub esp, 0x14
        mov edi, esp
        push edi
        mov eax, esi
        mov edx, [ebp-0x28]
        mov ecx, edx
        mov esi, [esi]
        call [esi+0xEC]
        mov eax, [edi]
        test eax, eax
        jle f_pop
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-0x28]
        xor ecx, ecx
        mov edx, eax
        mov eax, [ebp-4]
        call {NET:#x}
        mov esi, eax
        mov eax, [ebp-0x28]
        mov edx, [eax]
        call [edx+0x84]
        movsx ecx, al
        push ecx
        mov eax, [ebp-0x28]
        mov edx, [eax]
        call [edx+0x88]
        movsx edx, al
        push edx
        mov ecx, [esp+4]
        sub ecx, edx
        push ecx
        push dword ptr [edi+4]
        mov edx, [edi+0xC]
        test edx, edx
        jg f_a
        mov edx, 5
    f_a:
        push edx
        push esi
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-4]
        call {S['value']:#x}
        add esp, 0x24
        test eax, eax
        jle f_pop
        mov [edi+0x10], edx
        mov [edi+8], ecx
        mov [edi+4], eax
        mov ecx, {HERO_HEAL_PCT}
        test edx, 3
        jz f_p
        mov ecx, 100
        test edx, 1
        jz f_p
        mov ecx, {SELF_T1_PCT}
    f_p:
        mov edx, ecx
        shl edx, 16
        or [edi+0x10], edx
        imul eax, ecx
        mov [edi], eax
        mov edx, [ebp-4]
        inc dword ptr [edx+0x2C]
        mov eax, [ebp-0x28]
        call {S['pos']:#x}
        push edx
        push dword ptr [edi]
        push 0x2F
        push 0
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-0x28]
        mov ecx, eax
        mov dl, 1
        mov eax, [ebp-4]
        call {ADDMOVE:#x}
        push dword ptr [edi+0xC]
        push dword ptr [edi+0x10]
        push dword ptr [edi+8]
        push dword ptr [edi+4]
        push esi
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-0x28]
        call {S['log']:#x}
        add esp, 0x1C
        mov esi, [edi+0x10]
        mov [edi+0x10], eax
        test esi, 3
        jz f_pop
        mov eax, [ebp-0x28]
        mov eax, [eax+0x5C]
        sub eax, {HEAL_MP}
        jle f_pop
        push eax
        push 0
        mov eax, [ebp-0x28]
        call {S['pos']:#x}
        push edx
        push eax
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-4]
        call {S['retreat']:#x}
        add esp, 0x18
        cmp eax, -1
        je f_pop
        mov esi, eax
        mov eax, [edi]
        imul eax, eax, {RETREAT_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        inc eax
        mov edx, esi
        shr edx, 8
        push edx
        push eax
        push 0x2F
        push 0
        push dword ptr [ebp-0x28]
        push dword ptr [ebp-0x28]
        mov ecx, esi
        and ecx, 0xFF
        xor edx, edx
        mov eax, [ebp-4]
        call {ADDMOVE:#x}
        mov eax, [edi+0x10]
        mov [eax+0x1C], esi
    f_pop:
        add esp, 0x14
    f_done:
        pop edi
        pop esi
        pop ebx
        mov eax, [ebp-0x30]
        call {FREEOBJ:#x}
        jmp {H_F[3]:#x}
    """, nva)
    return head + body


def build_all(lo, hi):
    """-> (subs dict name->va, [(hook, cave_va, bytes)])"""
    va = CAVE_BASE
    S = {}
    subs = []
    order = [("pos", lambda v: sub_pos(v)), ("distxy", lambda v: sub_distxy(v, S)), ("dist", lambda v: sub_dist(v, S)),
             ("reach", lambda v: sub_reach(v, S)), ("pathcost", lambda v: sub_pathcost(v, S)),
             ("retreat", lambda v: sub_retreat(v, S, lo, hi)), ("log", lambda v: sub_log(v)),
             ("value", lambda v: sub_value(v, S))]
    for name, builder in order:
        S[name] = va
        c = builder(va)
        subs.append((name, va, c))
        va = (va + len(c) + 15) & ~15
    out = []
    for hook, builder in ((H_A, build_cave_a), (H_C, build_cave_c), (H_B, build_cave_b),
                          (H_E, build_cave_e), (H_F, build_cave_f)):
        c = builder(va, S)
        out.append((hook, va, c))
        va = (va + len(c) + 15) & ~15
    assert va <= CAVE_END, "caves overflow the reserved zone (%#x)" % va
    return S, subs, out


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


def read_log():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32

    class PE32(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
                    ('szExeFile', ctypes.c_char * 260)]

    class ME32(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('GlblcntUsage', wintypes.DWORD), ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.c_void_p),
                    ('modBaseSize', wintypes.DWORD), ('hModule', ctypes.c_void_p), ('szModule', ctypes.c_char * 256),
                    ('szExePath', ctypes.c_char * 260)]
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(PE32); pid = 0
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.lower() == b'aowx.exe':
                pid = pe.th32ProcessID; break
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    if not pid:
        print("AoWx.exe not running"); return 1
    snap = k32.CreateToolhelp32Snapshot(0x18, pid)
    me = ME32(); me.dwSize = ctypes.sizeof(ME32); base = None
    if k32.Module32First(snap, ctypes.byref(me)):
        while True:
            if me.szModule.lower() == b'aowtcpck.dll':
                base = me.modBaseAddr; break
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    if base is None:
        print("AoWTCPCK.dll not found in process"); return 1
    h = k32.OpenProcess(0x10, False, pid)
    sz = 0x10 + REC_N * 32
    buf = (ctypes.c_byte * sz)(); got = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(base + (REC - BASE)), buf, sz, ctypes.byref(got))
    k32.CloseHandle(h)
    b = bytes(buf)
    count = struct.unpack_from("<I", b, 0)[0]
    n = min(count, REC_N)
    print(f"TCPCK base {base:#x} (delta {base - BASE:+#x}); heal evaluations={count} (showing last {n})")
    for r in range(count - n, count):
        off = 0x10 + (r % REC_N) * 32
        f = struct.unpack_from("<7iI", b, off)
        flags = f[5] & 0xFFFF; pct = (f[5] >> 16) & 0xFFFF
        tier = flags & 3
        cur, mx, A, miss = f[6] & 0xFF, (f[6] >> 8) & 0xFF, (f[6] >> 16) & 0xFF, (f[6] >> 24) & 0xFF
        who = ("hero" if flags & 4 else "unit") + (" SELF" if flags & 8 else "")
        tgt = "hero/leader" if flags & 0x20 else "unit"
        rt = "" if f[7] == 0xFFFFFFFF else f" retreat->({f[7] & 0xFF},{(f[7] >> 8) & 0xFF})"
        print(f"  [{r:3}] {who} {f[0] & 0xFFFFFFFF:#010x} -> {tgt} {f[1] & 0xFFFFFFFF:#010x} hp {cur}/{mx} miss {miss} amt {A}"
              f" tier {tier} C {f[2]} V {f[3]} R {f[4]} pct {pct}{rt}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="tactical AI healing priority rework")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    ap.add_argument("--read", action="store_true", help="dump the heal-evaluation log from the running game")
    a = ap.parse_args()
    if a.read:
        return read_log()
    dll = a.dll
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        bak = open(bak_path(dll, BAK), "rb").read()
        assert len(bak) == os.path.getsize(dll), "size differs from backup; refusing"
        write_inplace(dll, bak); print("restored AoWTCPCK.dll from" + BAK); return 0

    d = bytearray(open(dll, "rb").read())
    lo, hi = struct.unpack_from("<ii", d, va2off(d, BOUNDS_VA))
    assert -128 <= lo < hi <= 127, "unexpected coordinate bounds %r" % ((lo, hi),)
    assert bytes(d[va2off(d, ABILLOOP_NEXT[0]):][:3]) == ABILLOOP_NEXT[1], "ability-loop continue point moved"
    bss = [s for s in sections(d) if s[0] == "BSS"][0]
    assert BASE + bss[2] + bss[1] <= REC and REC + 0x10 + REC_N * 32 <= ((BASE + bss[2] + bss[1] + 0xFFF) & ~0xFFF), "log ring outside BSS slack"
    S, subs, plan = build_all(lo, hi)
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for name, sva, c in subs:
            print("--- sub %s @%#x (%d B)" % (name, sva, len(c)))
            for i in md.disasm(c, sva):
                print("   %08x  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        for hook, cva, c in plan:
            print("--- cave %s @%#x (%d B)" % (hook[0], cva, len(c)))
            for i in md.disasm(c, cva):
                print("   %08x  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    for name, sva, c in subs:
        print("%-15s sub  %#x %4d B" % (name, sva, len(c)))
    states = set()
    for hook, cva, c in plan:
        name, hva, orig, resume = hook
        ho = va2off(d, hva)
        hookb = b"\xE9" + struct.pack("<i", cva - (hva + 5)) + b"\x90" * (len(orig) - 5)
        cur = bytes(d[ho:ho + len(orig)])
        co = va2off(d, cva)
        if cur == hookb and bytes(d[co:co + len(c)]) == c:
            st = "patched"
        elif cur == orig:
            st = "vanilla"
        else:
            print("%s @%#x: unexpected bytes %s" % (name, hva, cur.hex())); return 1
        states.add(st)
        print("%-15s hook %#x (%s) -> cave %#x %4d B" % (name, hva, st, cva, len(c)))
    go = va2off(d, GATE[0])
    gcur = bytes(d[go:go + 2])
    gst = "patched" if gcur == GATE[2] else "vanilla" if gcur == GATE[1] else None
    assert gst, "gate site unexpected: " + gcur.hex()
    states.add(gst)
    print("%-15s site %#x (%s) jne -> nop nop" % ("gate-g", GATE[0], gst))
    if states == {"patched"}:
        print("ALL ALREADY PATCHED"); return 0
    assert states == {"vanilla"}, "mixed state - inspect"
    lo_, hi_ = va2off(d, CAVE_BASE), va2off(d, CAVE_END)
    assert bytes(d[lo_:hi_]) == b"\0" * (hi_ - lo_), "cave zone not zero"
    ranges = [(h[1], h[1] + len(h[2])) for h in HOOKS] + [(CAVE_BASE, CAVE_END), (GATE[0], GATE[0] + 2)]
    r = [hex(v) for v in relocs(d) if any(lo2 <= v < hi2 or lo2 < v + 4 <= hi2 for lo2, hi2 in ranges)]
    assert not r, "relocs intersect: " + ", ".join(r)
    bad = branch_into_displaced(d, HOOKS)
    assert not bad, "branches into displaced bytes: " + ", ".join("%#x->%#x" % b for b in bad)
    print("checks OK: vanilla sites, zero caves, no relocs, no branches into displaced bytes, bounds %d..%d" % (lo, hi))
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWTCPCK.dll" + BAK)
    for name, sva, c in subs:
        so = va2off(d, sva)
        d[so:so + len(c)] = c
    for hook, cva, c in plan:
        name, hva, orig, resume = hook
        ho, co = va2off(d, hva), va2off(d, cva)
        d[ho:ho + len(orig)] = b"\xE9" + struct.pack("<i", cva - (hva + 5)) + b"\x90" * (len(orig) - 5)
        d[co:co + len(c)] = c
    d[go:go + 2] = GATE[2]
    write_inplace(dll, bytes(d))
    back = open(dll, "rb").read()
    for hook, cva, c in plan:
        co = va2off(back, cva)
        assert back[co:co + len(c)] == c and back[va2off(back, hook[1])] == 0xE9, "read-back failed"
    assert back[go:go + 2] == GATE[2]
    print("applied.  tier1 %d%%, danger %d%%, hopeless %d%% (low value < %d%%), floor %d%%/%d%%, decay end round %d,"
          " hero heal %d / touch %d / self-T1 %d, heal MP %d, hex MP %d, retreat radius %d @ %d%%"
          % (T1_PCT, DANGER_PCT, HOPELESS_PCT, LOWVAL_PCT, FLOOR_PCT, FLOOR_HOLD_PCT, DECAY_END, HERO_HEAL_PCT,
             HERO_TOUCH_PCT, SELF_T1_PCT, HEAL_MP, HEX_MP, RETREAT_RADIUS, RETREAT_PCT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
