#!/usr/bin/env python3
r"""
Tactical breath attacks v4 (AoWTCPCK.dll, 2026-10-19): v1's vanilla spray ANIMATION in the open; in a true ONE-hex
corridor the WHOLE breath (all 20 strikes) flies straight down the corridor's centre line.  In-place upgrade of
patch_breath_anim_v3.py / _v2.py / _v1.py (same sites, same zone).

User (on v3): "breath attacks STILL seem to always do the full sweep.  Also, I only want them narrowed in 1-hex-wide
corridors, i.e. when only the middle hexes of their AOE aren't blocked."

ROOT CAUSE (v2/v3 'straight' mode was never narrow).  The corridor branch only SKIPPED v1's re-path, i.e. it kept
patch_breath_line_v1's flight lines for strikes 0..11 - and those go to each strike's own DAMAGE hex, one per cone
hex (BreathHN: ring 1 = 1 hex, ring 2 = 3, ring 3 = 3, ring 4 = 5), so they fan across the whole +-30 deg cone.
MakeRangedPath never blocks on the line's own target hex (breath_line RE), so a jet aimed at a flank hex that IS a wall
still flies its full length into that wall; strikes 12..19 kept the vanilla -30..+24 deg sweep.  Net: even when CORR
said 'corridor', 12 jets to every cone hex + 8 sweeping strikes = it looks exactly like the full sweep.  (v3 also fired
in 2..4-wide lanes, which the user does not want.)

RULE v4 (decided ONCE per breath at strike 0 from map state only -> deterministic / MP-identical):
  D = BreathDir[dHXtoHN(shooter -> target) - 1] (as breath_line); cone = BreathHN row D, 12 hexes.  CENTRE line =
  cone entries 0 / 2 / 5 / 9 (rings 1..4 straight ahead: HN 1+3k(k-1)+(D-1)k); lateral-1 FLANKS (adjacent to the
  centre hex of their ring) = 1/3 (ring 2), 4/6 (ring 3), 8/10 (ring 4); 7/11 are ring 4's lateral-2 hexes, BEHIND 8/10
  (exploration-map walls are 1 hex thick with the next lane behind them, so 7/11 are often open floor - ignored).
  CORRIDOR  <=>  entry 0 open  AND  flanks 1,3 blocked  AND  (entry 2 blocked OR (flanks 4,6 blocked AND (entry 5
  blocked OR flanks 8,10 blocked)))  - i.e. walls hug the centre line on both sides as far as the breath gets.
  Blocked = v3's set: off the combat map, terrain [field+0x14] 0xF / 7, overlay [field+0x15] 8, a TCombatTerrain
  (0x220166) / TCombatObstacle (0x22052A) object, an INTACT city wall (0x220504) / gate (0x220506) section; units never.
  Straight end hex T = walk the centre entries 2, 5, 9: the first BLOCKED one (the breath splashes on the wall that
  closes the corridor), else entry 9 (the cone's full depth); an off-map centre hex stops the walk at the previous one.
  State C: 0x46BF38 = te, 0x46BF3C = flag: bit 0 corridor, byte 1 = T.x, byte 2 = T.y (combat maps are 65 x 59).
CORRIDOR LOOK: for EVERY strike s = 0..19 of a corridor breath the fan cave frees the strike's block records and
  re-runs MakeRangedPath shooter -> T with pixel offset 0 -> [fx+0x1C] = the straight centre line (no cut: T is the
  last open-or-wall centre hex).  Damage hexes / block results / RNG are untouched (the re-path happens after the
  block loop, MakeRangedPath draws no Random) -> MP-safe.  Not a corridor: s < 12 -> v1's fan exactly as before,
  s >= 12 -> vanilla (untouched).  Gust (212) / Crashing Wave (220) stay excluded.
  Fan-cave flow v4: latch match (te, s) for ANY s < 20 -> Gust/CW exclusion -> call CORR (s = 0 decides, s > 0 reads the
  stored flag when C.te == te, else 0) -> flag != 0 -> f_str (straight) | s >= 12 -> out | v1 fan.
PROBE SUPPORT: zone header +0x10..+0x17 = u16 offsets (from the zone base) of fan entry / f_str / f_mrp / c_done, read
  by diag_breath_corr_probe.py v4 (per-strike path log).  CORR's frame at c_done: [ebp-4] sx, [ebp-8] sy, [ebp-0xC] D,
  [ebp-0x2C] blocked mask (bit i = cone entry i), [ebp-0x34] required flank mask, [ebp-0x38] chosen centre
  entry, [ebp] te.
UPGRADE: a v1/v2/v3 zone ('BAN1'/'BAN2'/'BAN3') is rewritten in place as 'BAN4' (header prev_a / orig_b carried over);
  older scripts refuse a v4 zone.  --revert = the exact pre-breath-anim state (same file v1/v2/v3 --revert give).
  LIFO unchanged: revert this before patch_breath_line_v1.py (whose --revert is a whole-file restore!).
  Backup <game>\backup\AoWTCPCK.dll.bak_breathanim4.

v3 notes follow (its corridor rule and 'straight' look are superseded by the above).


Tactical breath attacks v3 (AoWTCPCK.dll, 2026-10-18): v1's vanilla spray ANIMATION in the open, the old STRAIGHT
per-hex jets (patch_breath_line_v1's damage-hex flight lines) down a corridor - with a corridor test that actually
fires in the game's corridors.  In-place upgrade of patch_breath_anim_v2.py / _v1.py (same sites, same zone).

User (on v2): "breath attacks in a corridor do the full sweep, not the narrowed animation."

ROOT CAUSE (v2).  v2 called a breath 'corridor' only when the cone's OWN flank hexes (BreathHN entries 1/4 and 3/6 =
the hexes one lateral row off the centre line at rings 2/3) were blocked, i.e. only in a corridor exactly ONE hex wide.
The corridors the user breathes down are the exploration-site combat maps (TCMaps\eDung / eCrpt / eRuin / eZigg):
1-hex-thick TCombatObstacle (ClassID 0x22052A) wall lines with lanes 1..4 hexes wide between them (parsed from the
.hsm files: CFS + zlib, 65 x 59 fields, odd-q layout).  Run over every floor hex x direction of those maps with the
REAL HSEngine CenterHNtoHX, v2 fired in only ~2-3 % of the breaths down 2- and 3-wide corridors (corridor_stats.txt).
The blocker set itself was fine (impassable obstacles put overlay 8 in [field+0x15], cf. MakeRangedPath), the state
latch / strike-0 gate / direction + table indexing were verified correct (BreathDir is the identity, BreathHN is the
HSEngine spiral: HN of k*d_j = 1 + 3k(k-1) + (j-1)k).

CORRIDOR RULE v3 (decided ONCE per breath at strike 0 from map state only -> deterministic / MP-identical):
  D = breath direction (dHXtoHN shooter -> target, 1..6 -> BreathDir), left side L = D-1, right side R = D+1 (wrapping).
  Centre-line hexes C_b = b steps along D from the shooter, b = 1..STEPS (3: the cone's depth before its widest ring).
  A side S is CLOSED at step b when one of the hexes C_b + a*d_S, a = 1..AMAX (3 lateral rows), is blocked.
  CORRIDOR = both sides closed at NEED (= all 3) steps -> lanes up to 3 hexes wide always fire (100 % on the real
  maps), 4-wide 50 %, 5-wide 29 %, rooms 6+ wide never (0 %).  Blocked = off the combat map, terrain [field+0x14] 0xF
  or 7, overlay [field+0x15] 8 (impassable obstacle / decoration), a TCombatTerrain (0x220166) or TCombatObstacle
  (0x22052A) object, an INTACT city wall (0x220504) or gate (0x220506) section (HP [+0x20] > 0); units never count.
  Hex stepping = HSEngine.CenterHNtoHX(x, y, hn = direction 1..6) one step at a time (odd-q parity handled by the
  engine).  Corridor -> strikes 0..11 keep breath_line's straight damage-hex flight path; strikes 12..19 stay vanilla
  (they sweep and are cut at the walls by the block loop = the pre-v1 hallway look).  Otherwise v1's fan.
  Diagnostics live in CORR's own frame at the c_done instruction (`mov eax,[ebx+0x46BF3C] / mov esp,ebp / pop x3 / ret`, located by
  diag_breath_corr_probe.py by byte pattern DONE_PAT): [ebp-4] sx, [ebp-8] sy, [ebp-0xC] D, [ebp-0x2C] blocked mask
  (bit side*9 + (b-1)*3 + (a-1); left = 0..8, right = 9..17; first blocked a per b only), [ebp-0x34] / [ebp-0x38]
  left / right closed-step counts (right only evaluated when left passed), [ebp] = te.
  State C (DATA slack 0x46BF38 te, 0x46BF3C flag) as v2.  CORR subroutine at 0x451400 (rel32 call from the fan cave,
  PIC via the fan cave's ebx delta; own ebp frame, preserves ebx/esi/edi/ebp; table pointer 0x469404, map list
  0x469420; GetMapLevel 0x401E64 / GetField 0x401E54 with an explicit bounds check against level +0xC width / +0x10
  height; CenterHNtoHX thunk 0x4022AC; dHXtoHN thunk 0x4022B4).

v2 / v1 notes follow (v2's corridor rule is superseded by the one above).

ROOT CAUSE.  A breath (ability category 5) is [te+0x28] = 0x14 = 20 strikes (TCAbRangedTE setup 0x40B520).  Each strike
is one fx (NextStrike 0x40D290, fx = [ebp-0x10]) that flies along ITS OWN path [fx+0x1C], and that path is exactly the
line MakeRangedPath 0x427630 builds for the obstruction test (0x40D65F: &blocks = [ebp-0x5C], &points = fx+0x1C).
Vanilla aims every strike at the cone's full depth rotated by (f*6-30) deg, f = s (s > 9: 19-s): strikes 0..9 sweep
-30 -> +24 deg, strikes 10..19 sweep back +24 -> -30 deg = the side-to-side spray.  patch_breath_line_v1 (0x40D5F1 ->
0x43AB40) re-aims strikes 0..11 at their own DAMAGE hex (BreathHN[BreathHit[s]], order 0,1,4,7,8,2,5,9,10,3,6,11) so
the 12 damaging strikes became short/long jets jumping between hexes (the "straight breath"), followed by the 8
untouched animation-only strikes 12..19 sweeping back (the "side-to-side breath").  The damage hex itself is written
after the call (0x40D671..0x40D72A) and is unaffected.

FIX (two hooks + 24 B of state, s < 12 only; strikes 12..19 stay vanilla):
  A 0x40D5F1 (the breath-line hook `jmp 0x43AB40`) -> SAVE cave: latch te / s and the VANILLA fan values the call is
    about to push (target hex [ebp-0x48]/[ebp-0x4C], pixel offset [ebp-0x3C]/[ebp-0x40]) into G, then jmp the
    breath-line cave (unchanged: it re-aims the block line at the damage hex).
  B 0x40F0B1 (category-5-only tail `mov eax,[ebp-0x10] / xor edx,edx / mov [eax+0x2C],edx`, 8 B, after the block loop
    0x40EE41..0x40F0A2 and Gust's SPR call at 0x40F0A8): for a breath strike s < 12 whose G latch matches (te, s), and
    not Gust / Crashing Wave (spell [te+0x14] == 0x34 and [te+0x18] in {212, 220}: their forward spray is built from the
    damage-hex path by Gust's SPR and their slot 0 is blank - unchanged):
      1. blocked = [fx+0x24] <= 0 (0x40F06F zeroes the damage hex when the block line is stopped; breath ignores units)
         -> D2 = squared pixel distance from the path's first to its (truncated) last point;
      2. free the block records in [ebp-0x5C] (the function epilogue 0x40F3F7 frees whatever the list holds);
      3. MakeRangedPath again with the SAVED vanilla values -> [fx+0x1C] = the vanilla fan line (TXYZList.Clear frees
         the old points), [ebp-0x5C] = its block records (freed by the epilogue as usual);
      4. blocked -> delete fan points from the end while they lie farther than D2 from the start, so the spray stops
         about where the strike was stopped (open space: never blocked -> full vanilla sweep).
    then replay the 8 bytes and jmp 0x40F0B9 (vanilla `jmp 0x40F227`).
  Damage hexes, block results ([fx+0x24]/[fx+0x28]/[fx+0x2C]), RNG use (MakeRangedPath calls no Random) and strike
  order are untouched -> every machine runs the same token code -> multiplayer-safe.  Only the fx path changes.
State G (DATA page slack past the raw size, zero-filled, unreferenced): 0x46BF20 te, +4 s, +8 x, +0xC y, +0x10 ox,
+0x14 oy (Ashes' trace ring ends 0x46BF10, oil gush 0x46BF40).  Zone AoWTCPCK 0x451000..0x451400: +0 'BAN1', +4 the
previous site-A target (0x43AB40), +8 site-B original 8 B, code at +0x20.  PIC (call/pop delta) for G; rel32 calls.
LIFO: apply AFTER patch_breath_line_v1.py; revert THIS before patch_breath_line_v1.py (whose --revert is a whole-file
restore of a 2026-09-21 backup - see full-file-backup-revert-gotcha) and before re-running it.  Site B is not used by
any other script (Gust's SPR is 0x40F0A8, Crashing Wave's BLK 0x40F06F).
v2 UPGRADE: a v1 zone ('BAN1') is rewritten in place as 'BAN2' (header prev_a / orig_b carried over); v1's script
refuses a v2 zone.  --revert (v2) = the exact pre-breath-anim state (site A -> prev_a, site B restored,
0x451000..0x451800 zeroed) = the same file v1's --revert gives; re-run v1 --apply afterwards to get v1 back.
LIFO unchanged: revert this before patch_breath_line_v1.py (whose --revert is a whole-file restore!).
Backup <game>\backup\AoWTCPCK.dll.bak_breathanim2.  Dry-run default; --apply; --revert (exact: sites + zone); --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_breathanim4"
BASE = 0x400000
MAGIC = b"BAN4"
MAGIC_V3 = b"BAN3"
MAGIC_V1 = b"BAN1"
MAGIC_V2 = b"BAN2"
ZONE, ZONE_END = 0x451000, 0x451800
CORR = 0x451400                   # corridor subroutine (v2 -> v3 rewritten in place)
ZONE_V1_END = 0x451400            # v1 zone end (v1 used 0x451000..0x451400)
CODE = ZONE + 0x20
G = 0x46BF20                      # te, s, x, y, ox, oy
G_END = G + 0x18
C_TE, C_FLAG, C_END = 0x46BF38, 0x46BF3C, 0x46BF40   # v2 corridor decision (te, flag)
SITE_A = 0x40D5F1                 # breath-line hook (jmp 0x43AB40)
PREV_A_EXPECT = 0x43AB40
SITE_B = 0x40F0B1
SITE_B_ORIG = bytes.fromhex("8b45f033d289502c")
RESUME_B = 0x40F0B9               # vanilla `jmp 0x40F227`
MRP = 0x427630                    # MakeRangedPath
SIDE = 0x40252C                   # thunk: side of the shooter HS (al)
LST_GET, OBJ_FREE = 0x40153C, 0x401050      # TList.Get(eax=list, edx=i) / TObject.Free(eax)
XYZ_GET, XYZ_DEL, XYZ_CNT = 0x402DF4, 0x402DEC, 0x402DFC   # TXYZList.GetXYZ / Delete / GetCount thunks
STRIKES = 12
GUST, CWAVE = 212, 220
P_BREATHDIR, P_BREATHHN = 0x469404, 0x46940C
MAPLIST = 0x469420
HX2DIR, HN2HX = 0x4022B4, 0x4022AC        # HSEngine.dHXtoHN(eax=x1, edx=y1, ecx=x2, [y2]) ret 4 / CenterHNtoHX(eax=x, edx=y, ecx=hn, [&X], [&Y]) ret 8
GETLEVEL, GETFIELD = 0x401E64, 0x401E54  # map list -> level (edx=0) / TMapLevel.GetField(eax=level, edx=X, ecx=Y) - NO bounds
CID_OBST, CID_WALL, CID_GATE = 0x220166, 0x220504, 0x220506   # TCombatTerrain / TCityWall / TCityWallDoor
CID_OBST2 = 0x22052A                     # TCombatObstacle (dungeon / crypt / ruin wall lines)
CENTRE = (0, 2, 5, 9)                    # cone entries straight ahead (rings 1..4)
FLANKS = (1, 3, 4, 6, 8, 10)            # lateral-1 flank entries (7 / 11 sit behind 8 / 10)
STRIKES_ALL = 20
AMAX, STEPS, NEED = 3, 3, 3              # lateral rows per side / centre-line steps / closed steps needed per side
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def cave_save(va, prev_a):
    # entered by `jmp` from SITE_A; must leave all registers / flags as found and continue at prev_a
    head = asm("pushfd\npush eax\npush ebx", va)
    c = va + len(head); nxt = c + 5
    body = asm(f"""
        pop ebx
        sub ebx, {nxt:#x}
        mov eax, [ebp-4]
        mov [ebx+{G:#x}], eax
        mov eax, [eax+0x34]
        mov [ebx+{G+4:#x}], eax
        mov eax, [ebp-0x48]
        mov [ebx+{G+8:#x}], eax
        mov eax, [ebp-0x4C]
        mov [ebx+{G+0xC:#x}], eax
        mov eax, [ebp-0x3C]
        mov [ebx+{G+0x10:#x}], eax
        mov eax, [ebp-0x40]
        mov [ebx+{G+0x14:#x}], eax
        pop ebx
        pop eax
        popfd
    """, nxt)
    p = head + asm(f"call {nxt:#x}", c) + body
    p += asm(f"jmp {prev_a:#x}", va + len(p))
    return p


def cave_fan(va):
    # entered by `jmp` from SITE_B (category 5 only); ends with the replayed 8 bytes + jmp RESUME_B
    head = asm("pushad\nsub esp, 8", va)
    c = va + len(head); nxt = c + 5
    body = f"""
        pop ebx
        sub ebx, {nxt:#x}
        mov edi, [ebp-4]
        mov esi, [edi+0x34]
        cmp esi, {STRIKES_ALL}
        jae f_out
        cmp [ebx+{G:#x}], edi
        jne f_out
        cmp [ebx+{G+4:#x}], esi
        jne f_out
        mov dword ptr [ebx+{G:#x}], 0
        cmp dword ptr [edi+0x14], 0x34
        jne f_go
        mov eax, [edi+0x18]
        cmp eax, {GUST}
        je f_out
        cmp eax, {CWAVE}
        je f_out
    f_go:
        call {CORR:#x}
        test eax, eax
        jnz f_str
        cmp esi, {STRIKES}
        jae f_out
        mov esi, [ebp-0x10]
        mov dword ptr [esp], 0
        mov dword ptr [esp+4], 0
        cmp dword ptr [esi+0x24], 0
        jg f_free
        mov dword ptr [esp], 1
        mov eax, [esi+0x1C]
        call {XYZ_CNT:#x}
        cmp eax, 2
        jl f_free
        lea edx, [eax-1]
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        push dword ptr [eax+8]
        push dword ptr [eax+4]
        xor edx, edx
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        pop ecx
        sub ecx, [eax+4]
        imul ecx, ecx
        pop edx
        sub edx, [eax+8]
        imul edx, edx
        add ecx, edx
        mov [esp+4], ecx
    f_free:
        mov eax, [ebp-0x5C]
        mov edi, [eax+8]
    f_fl:
        dec edi
        js f_mrp
        mov edx, edi
        mov eax, [ebp-0x5C]
        call {LST_GET:#x}
        call {OBJ_FREE:#x}
        jmp f_fl
    f_mrp:
        mov edi, [ebp-4]
        push 0x32
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        push eax
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        push dword ptr [ebx+{G+8:#x}]
        push dword ptr [ebx+{G+0xC:#x}]
        push dword ptr [ebx+{G+0x10:#x}]
        push dword ptr [ebx+{G+0x14:#x}]
        push 0
        lea eax, [esi+0x1C]
        push eax
        lea eax, [ebp-0x5C]
        push eax
        mov eax, [edi+0x10]
        call {SIDE:#x}
        mov cx, 0x14
        mov dx, 0x32
        call {MRP:#x}
        cmp dword ptr [esp], 0
        je f_out
    f_cut:
        mov eax, [esi+0x1C]
        call {XYZ_CNT:#x}
        cmp eax, 2
        jl f_out
        mov edi, eax
        lea edx, [eax-1]
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        push dword ptr [eax+8]
        push dword ptr [eax+4]
        xor edx, edx
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        pop ecx
        sub ecx, [eax+4]
        imul ecx, ecx
        pop edx
        sub edx, [eax+8]
        imul edx, edx
        add ecx, edx
        cmp ecx, [esp+4]
        jle f_out
        lea edx, [edi-1]
        mov eax, [esi+0x1C]
        call {XYZ_DEL:#x}
        jmp f_cut
    f_str:
        mov [esp], eax
        mov esi, [ebp-0x10]
        mov eax, [ebp-0x5C]
        mov edi, [eax+8]
    t_fl:
        dec edi
        js t_mrp
        mov edx, edi
        mov eax, [ebp-0x5C]
        call {LST_GET:#x}
        call {OBJ_FREE:#x}
        jmp t_fl
    t_mrp:
        push 0x32
        mov edi, [ebp-4]
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        push eax
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        movzx eax, byte ptr [esp+0xD]
        push eax
        movzx eax, byte ptr [esp+0x12]
        push eax
        push 0
        push 0
        push 0
        lea eax, [esi+0x1C]
        push eax
        lea eax, [ebp-0x5C]
        push eax
        mov eax, [edi+0x10]
        call {SIDE:#x}
        mov cx, 0x14
        mov dx, 0x32
        call {MRP:#x}
    f_out:
        add esp, 8
        popad
        mov eax, [ebp-0x10]
        xor edx, edx
        mov [eax+0x2C], edx
        jmp {RESUME_B:#x}
    """
    return head + asm(f"call {nxt:#x}", c) + asm(body, nxt)


F_STR_PAT = bytes.fromhex("890424" "8b75f0")       # f_str: mov [esp],eax / mov esi,[ebp-0x10]
F_MRP_PAT = bytes.fromhex("8b7dfc" "6a32")         # f_mrp: mov edi,[ebp-4] / push 0x32 (t_mrp pushes first)


def cave_corr(va):
    """in: ebx = fan-cave delta, edi = te, esi = s.  out: eax = flag (bit 0 corridor, byte 1 T.x, byte 2 T.y) / 0 = fan.
    Preserves ebx / esi / edi / ebp; clobbers eax / ecx / edx (the fan cave holds pushad).  Rule: see the docstring."""
    src = f"""
        test esi, esi
        jz c_new
        xor eax, eax
        cmp [ebx+{C_TE:#x}], edi
        jne c_ret0
        mov eax, [ebx+{C_FLAG:#x}]
    c_ret0:
        ret
    c_new:
        mov [ebx+{C_TE:#x}], edi
        mov dword ptr [ebx+{C_FLAG:#x}], 0
        push ebp
        push esi
        push edi
        mov ebp, esp
        sub esp, 0x40
        xor eax, eax
        mov [ebp-0xC], eax
        mov [ebp-0x10], eax
        mov [ebp-0x2C], eax
        mov [ebp-0x34], eax
        mov dword ptr [ebp-0x38], -1
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        mov [ebp-4], eax
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        mov [ebp-8], eax
        movzx eax, word ptr [edi+0x22]
        push eax
        mov eax, [ebp-4]
        mov edx, [ebp-8]
        movzx ecx, word ptr [edi+0x20]
        call {HX2DIR:#x}
        cmp eax, 1
        jl c_done
        cmp eax, 6
        jg c_done
        mov edx, [ebx+{P_BREATHDIR:#x}]
        mov eax, [edx+eax*4-4]
        cmp eax, 1
        jl c_done
        cmp eax, 6
        jg c_done
        mov [ebp-0xC], eax
        mov eax, [ebx+{MAPLIST:#x}]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call {GETLEVEL:#x}
        mov [ebp-0x10], eax
        test eax, eax
        jz c_done
        xor esi, esi
    c_loop:
        call c_hex
        call c_blk
        test eax, eax
        jz c_next
        mov ecx, esi
        mov eax, 1
        shl eax, cl
        or [ebp-0x2C], eax
    c_next:
        inc esi
        cmp esi, 12
        jl c_loop
        mov eax, [ebp-0x2C]
        test eax, 1
        jnz c_done
        mov ecx, 0x0A
        test eax, 4
        jnz c_need
        or ecx, 0x50
        test eax, 0x20
        jnz c_need
        or ecx, 0x500
    c_need:
        mov [ebp-0x34], ecx
        and eax, ecx
        cmp eax, ecx
        jne c_done
        mov dword ptr [ebp-0x38], 0
        mov esi, 2
        call c_try
        jnz c_pick
        mov esi, 5
        call c_try
        jnz c_pick
        mov esi, 9
        call c_try
    c_pick:
        mov esi, [ebp-0x38]
        call c_hex
        mov eax, [ebp-0x20]
        and eax, 0xFF
        shl eax, 8
        mov ecx, [ebp-0x1C]
        and ecx, 0xFF
        or eax, ecx
        shl eax, 8
        or eax, 1
        mov [ebx+{C_FLAG:#x}], eax
    c_done:
        mov eax, [ebx+{C_FLAG:#x}]
        mov esp, ebp
        pop edi
        pop esi
        pop ebp
        ret
    c_try:
        call c_hex
        mov edx, [ebp-0x10]
        mov eax, [ebp-0x1C]
        test eax, eax
        jl t_stop
        cmp eax, [edx+0xC]
        jge t_stop
        mov eax, [ebp-0x20]
        test eax, eax
        jl t_stop
        cmp eax, [edx+0x10]
        jge t_stop
        mov [ebp-0x38], esi
        mov ecx, esi
        mov eax, 1
        shl eax, cl
        test [ebp-0x2C], eax
        ret
    t_stop:
        or eax, 1
        ret
    c_hex:
        mov eax, [ebp-0xC]
        dec eax
        imul eax, eax, 12
        add eax, esi
        mov edx, [ebx+{P_BREATHHN:#x}]
        mov ecx, [edx+eax*4]
        mov eax, [ebp-4]
        mov [ebp-0x1C], eax
        mov eax, [ebp-8]
        mov [ebp-0x20], eax
        lea eax, [ebp-0x1C]
        push eax
        lea eax, [ebp-0x20]
        push eax
        mov eax, [ebp-4]
        mov edx, [ebp-8]
        call {HN2HX:#x}
        ret
    c_blk:
        mov edx, [ebp-0x10]
        mov eax, [ebp-0x1C]
        test eax, eax
        jl k_yes
        cmp eax, [edx+0xC]
        jge k_yes
        mov ecx, [ebp-0x20]
        test ecx, ecx
        jl k_yes
        cmp ecx, [edx+0x10]
        jge k_yes
        mov edx, eax
        mov eax, [ebp-0x10]
        call {GETFIELD:#x}
        test eax, eax
        jz k_no
        mov [ebp-0x28], eax
        movsx edx, byte ptr [eax+0x14]
        cmp edx, 0xF
        je k_yes
        cmp edx, 7
        je k_yes
        movsx edx, byte ptr [eax+0x15]
        cmp edx, 8
        je k_yes
        mov edx, {CID_OBST:#x}
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jnz k_yes
        mov eax, [ebp-0x28]
        mov edx, {CID_OBST2:#x}
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jnz k_yes
        mov eax, [ebp-0x28]
        mov edx, {CID_WALL:#x}
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jz k_gate
        cmp dword ptr [eax+0x20], 0
        jg k_yes
    k_gate:
        mov eax, [ebp-0x28]
        mov edx, {CID_GATE:#x}
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jz k_no
        cmp dword ptr [eax+0x20], 0
        jg k_yes
    k_no:
        xor eax, eax
        ret
    k_yes:
        mov eax, 1
        ret
    """
    return asm(src, va)


DONE_PAT = asm(f"mov eax, [ebx+{C_FLAG:#x}]\nmov esp, ebp\npop edi\npop esi\npop ebp\nret", 0)   # c_done (probe point)

def build(prev_a):
    sv = cave_save(CODE, prev_a)
    fan_va = (CODE + len(sv) + 15) & ~15
    fan = cave_fan(fan_va)
    assert fan_va + len(fan) <= CORR, hex(fan_va + len(fan))
    corr = cave_corr(CORR)
    assert CORR + len(corr) <= ZONE_END, hex(CORR + len(corr))
    return sv, fan_va, fan, corr


def labels(fan_va, fan, corr):
    """u16 offsets from ZONE of: fan entry, f_str, f_mrp, c_done (zone header +0x10, for the probe)."""
    ks_ = fan.find(F_STR_PAT); km = fan.find(F_MRP_PAT); kd = corr.find(DONE_PAT)
    assert ks_ > 0 and km > 0 and kd > 0 and fan.count(F_STR_PAT) == 1 and fan.count(F_MRP_PAT) == 1, (ks_, km, kd)
    return struct.pack("<4H", fan_va - ZONE, fan_va + ks_ - ZONE, fan_va + km - ZONE, CORR + kd - ZONE)


def va2off(pe, va):
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    n = struct.unpack_from("<H", pe, e + 6)[0]
    opt = struct.unpack_from("<H", pe, e + 20)[0]
    for i in range(n):
        s = e + 24 + opt + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(hex(va))


def reloc_hits(pe, ranges):
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    rva, sz = struct.unpack_from("<II", pe, e + 24 + 0x88)
    off = va2off(pe, BASE + rva); end = off + sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            ent = struct.unpack_from("<H", pe, off + 8 + 2 * i)[0]
            if ent >> 12:
                va = BASE + page + (ent & 0xFFF)
                if any(lo - 3 <= va < hi for lo, hi in ranges):
                    hits.append(va)
        off += bsz
    return hits


def g_refs(pe):
    """absolute references to the G slots anywhere in the image (should be none but ours)."""
    out = []
    for i in range(len(pe) - 3):
        v = struct.unpack_from("<I", pe, i)[0]
        if G <= v < G_END or C_TE <= v < C_END:
            out.append(i)
    return out


def jmp(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def rel_target(d, va):
    o = va2off(d, va)
    return va + 5 + struct.unpack_from("<i", d, o + 1)[0] if d[o] in (0xE8, 0xE9) else None


def state(d):
    oa, ob, oz = va2off(d, SITE_A), va2off(d, SITE_B), va2off(d, ZONE)
    ta = rel_target(d, SITE_A)
    zone = bytes(d[oz:oz + (ZONE_END - ZONE)])
    ours = zone[:4] == MAGIC
    v1 = zone[:4] == MAGIC_V1
    v2 = zone[:4] == MAGIC_V2
    v3 = zone[:4] == MAGIC_V3
    b = bytes(d[ob:ob + 8])
    return ta, b, ours, v1, v2, v3, zone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    ta, b, ours, v1, v2, v3, zone = state(d)
    older = v1 or v2 or v3
    print(f"target: {a.dll}")
    print(f"  site A {SITE_A:#x}: {'jmp %#x' % ta if ta else 'NOT A JMP ' + bytes(d[va2off(d, SITE_A):][:5]).hex()}"
          f"  site B {SITE_B:#x}: {b.hex()}  zone {ZONE:#x}: {'OURS (v4)' if ours else 'v3 (BAN3)' if v3 else 'v2 (BAN2)' if v2 else 'v1 (BAN1)' if v1 else 'zero' if not any(zone) else 'FOREIGN'}")
    rl = reloc_hits(d, [(SITE_A, SITE_A + 5), (SITE_B, SITE_B + 8), (ZONE, ZONE_END)])
    gr = [o for o in g_refs(d) if not (va2off(d, ZONE) <= o < va2off(d, ZONE_END))]
    print(f"  relocs: {[hex(v) for v in rl] or 'none'}; foreign refs to G {G:#x}..{G_END:#x}: {gr or 'none'}")

    if a.revert:
        if not (ours or older):
            sys.exit("breath-anim not applied (zone has no BAN1..BAN4 header) - nothing to revert")
        prev_a = struct.unpack_from("<I", zone, 4)[0]
        orig_b = zone[8:16]
        sv, fan_va, fan, corr = build(prev_a)
        if ta != CODE:
            sys.exit(f"site A no longer jumps to our cave ({ta and hex(ta)}) - a later script re-hooked it; refusing")
        tb = rel_target(d, SITE_B)
        if b[0] != 0xE9 or tb is None or not (ZONE <= tb < ZONE_END):
            sys.exit("site B is not our jmp - refusing")
        oa, ob, oz = va2off(d, SITE_A), va2off(d, SITE_B), va2off(d, ZONE)
        d[oa:oa + 5] = jmp(SITE_A, prev_a, 5)
        d[ob:ob + 8] = orig_b
        d[oz:oz + (ZONE_END - ZONE)] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f:
            f.seek(0); f.write(d)
        print(f"reverted: site A -> jmp {prev_a:#x}, site B restored, zone zeroed")
        return

    if ours or older:
        prev_a = struct.unpack_from("<I", zone, 4)[0]
        if ta != CODE:
            sys.exit(f"site A jumps to {ta and hex(ta)}, not our save cave - a later script re-hooked it; refusing")
    else:
        if ta is None or d[va2off(d, SITE_A)] != 0xE9:
            sys.exit("site A is not the breath-line jmp - apply patch_breath_line_v1.py first")
        prev_a = ta
        if prev_a != PREV_A_EXPECT:
            print(f"  note: site A jumps to {prev_a:#x}, not breath-line's {PREV_A_EXPECT:#x} - chaining to it")
    sv, fan_va, fan, corr = build(prev_a)
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in ((CODE, sv, "save"), (fan_va, fan, "fan"), (CORR, corr, "corridor")):
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
        lb = struct.unpack("<4H", labels(fan_va, fan, corr))
        print("\n  probe points: fan %#x  f_str %#x  f_mrp %#x  c_done %#x" % tuple(ZONE + o for o in lb))
    print(f"  caves: save {CODE:#x} ({len(sv)} B), fan {fan_va:#x} ({len(fan)} B, end {fan_va + len(fan):#x}),"
          f" corridor {CORR:#x} ({len(corr)} B, end {CORR + len(corr):#x})")
    if ours or older:
        orig_b = zone[8:16]
        if orig_b != SITE_B_ORIG:
            sys.exit(f"zone header's site-B original {orig_b.hex()} is not vanilla - refusing")
        old_fan = rel_target(d, SITE_B)
        if b[0] != 0xE9 or old_fan is None or not (ZONE <= old_fan < ZONE_END):
            sys.exit("site B is not a jmp into our zone - refusing")
        if v1 and any(zone[ZONE_V1_END - ZONE:]):
            sys.exit("0x451400..0x451800 not zero - refusing")
    if ours:
        want_b = jmp(SITE_B, fan_va, 8)
        same = (zone[0x20:0x20 + len(sv)] == sv and zone[fan_va - ZONE:fan_va - ZONE + len(fan)] == fan
                and zone[CORR - ZONE:CORR - ZONE + len(corr)] == corr and ta == CODE and b == want_b
                and zone[0x10:0x18] == labels(fan_va, fan, corr))
        print("  state: v4 APPLIED" + ("" if same else " (stale cave - will rewrite in place)"))
        if same:
            print("already applied"); return
    elif v3:
        print("  state: v3 applied - upgrading v3 -> v4 in place")
    elif v2:
        print("  state: v2 applied - upgrading v2 -> v4 in place")
    elif v1:
        print("  state: v1 applied - upgrading v1 -> v4 in place")
    else:
        if b != SITE_B_ORIG:
            sys.exit(f"site B bytes {b.hex()} are neither vanilla nor ours - refusing")
        if any(zone):
            sys.exit("zone not zero - refusing")
        orig_b = SITE_B_ORIG
        print("  state: vanilla (breath-line present)")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl:
        sys.exit("relocs intersect the patch - refusing")
    if gr:
        sys.exit("G slots are referenced elsewhere in the image - refusing")
    bak = bak_path(a.dll, BAK, create=True)
    if not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print(f"  backup -> {bak}")
    oz = va2off(d, ZONE)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC; struct.pack_into("<I", z, 4, prev_a); z[8:16] = orig_b
    z[0x10:0x18] = labels(fan_va, fan, corr)
    z[0x20:0x20 + len(sv)] = sv
    z[fan_va - ZONE:fan_va - ZONE + len(fan)] = fan
    z[CORR - ZONE:CORR - ZONE + len(corr)] = corr
    d[oz:oz + len(z)] = z
    oa, ob = va2off(d, SITE_A), va2off(d, SITE_B)
    d[oa:oa + 5] = jmp(SITE_A, CODE, 5)
    d[ob:ob + 8] = jmp(SITE_B, fan_va, 8)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied.")


if __name__ == "__main__":
    main()
