#!/usr/bin/env python3
r"""
MEND WALLS v2 (216, Earth L1 combat, 2026-10-17 round 2).  AoWTCPCK.dll only.  Replaces patch_tc_mendwalls_v1.py
(revert that one first - this script refuses to apply while its LND/TGT hooks are live).

User: "i dont like the mend walls gfx, it shouldnt be like hail/ooze. it should simply make walls within the AOE glow
green or have some kind of magical effect. also, it should restore their appearance to suit their HP. its hard to
tell if theyre healing since their HP isnt displayed anywhere".

No strikes any more.  The spell keeps its Ooze chassis (pipeline TOoze clone, alias 216 -> 0x7C: 19-hex preview,
unlimited range, hail class 0x0A), but the te never fires one:
  gate  both `call NextStrike` sites 0x40B6F1 (phase 0) / 0x40CBE7 (phase 1), chained IN FRONT of whatever they call
        (decoded at apply time, kept at zone+0 for an exact revert; today the Suffocate gate 0x43FE00).  eax = te.
        te spell ([te+0x18]) == 216 and [te+0x28] (strike count, 19 from the Ooze alias) != 0 -> the MEND, once:
        [te+0x28] := 0 (no strikes: NextStrike's own `[te+0x34] >= [te+0x28]` exit; phase 1 ends the te as soon as the
        map effect list is empty), then for HN 0..18 around the target hex [te+0x20]/[te+0x22] (HSEngine.CenterHNtoHX
        thunk 0x4022AC, in-level bounds [level+0xC]/[level+0x10] - GetField has NO bounds check) the field's TCityWall
        (FindOwnedChild 0x220504) or TCityWallDoor (0x220506) is mended:
          HP <= 0 (destroyed) or HP >= max -> untouched, no glow;
          else HP += max/4 + RandInt(max/2 + 1)  (25..75 % of max, capped; System.@RandInt thunk 0x401020 = the synced
               combat stream, one draw per damaged wall in HN order -> MP-deterministic) via TCityWall.SetHitPoints
               0x405AE4 (stores HP, recomputes the image state [+0x24]: 0 full / 1 > half / 2 <= half / 3 destroyed;
               TCityWall.Show 0x4062FC draws image table[material] + terrain offset + [+0x24]);
          APPEARANCE: a mended wall at >= 75 % of max gets image state 0 (intact) - vanilla shows "intact" only at
               exactly max, so most mends kept the cracked image; < 75 % keeps SetHP's state (> half = cracked);
          REDRAW: walls are STATIC-scene sprites (layer VMT+0x64 <= 15) and SetHitPoints never invalidates them, so a
               new image only appeared after some unrelated static redraw.  THSMap.InvalidateStaticScene 0x5560D708's
               effect is reproduced: byte [map+0x30] := 1, map = [[[wall+4] field +4] level +0x1C];
          GLOW: a kind-0x26 effect on the wall hex (AddEffect([[0x469420]], 0x26) 0x41C6EC, xyz = HXtoHP + (16,16) =
               the hex centre, [fx+0x14] = 0x34 / [fx+0x18] = 216 / [fx+0x2C] = 0 / marker [fx+0x24] = 0) = the
               spell's gfx SLOT 1 (no kind-0x26 slot-pick cave claims 216 -> the vanilla `mov edx/eax, 1`).
        After the sweep: when every wall in [[[0x469420]]+0x120] has HP > 0, the breach flag
        [[[map]+0xE4]+0xC]+0x4D (set by SetHP at HP 0, read by the AI ram focus) is cleared again (as v1).
        Returns without calling NextStrike.  Every other te / pass -> the previous chain target.
v4 (2026-10-17 round 4, user: "rebuild destroyed structures (ie: houses) on tactical combat maps as well" / "the camera
seems to center on the caster when cast, it should center on the AOE"):
  CAMERA: the mend first centres the view on the target hex - map VMT+0xBC (eax map, edx hx [te+0x20], ecx hy [te+0x22],
        push level 0; ret 4) = what NextStrike does before every vanilla strike (0x40D884); with no strikes nothing did.
  STRUCTURES: after the wall / gate of each hex, its TCombatStructure kids (THouse 0x220512, TWorkshop 0x220508,
        TTownhall 0x220510, TMainStructure 0x22051C; FindOwnedChild = exact class id + owner) are mended: HP [+0x20],
        max 5 (TCombatStructure.Create SetHP(5)); HP 5 -> untouched; HP 1..4 -> + 5/4 + RandInt(5/2+1) = 1..3, capped;
        HP 0 (DESTROYED: THouse.Show 0x4348D0 draws the ruin sequence 0x32 at HP 0, movement cost 0x43320C = the
        passable rubble entry, overlay class 0x4332D4 6) -> REBUILT the same way (1..3 HP: intact image, blocking
        again) unless a unit stands in the rubble (FindOwnedChild 0x220104 TTacticalCombatUnitHS on the field) - a
        rebuilt house would wall the unit in.  TCombatStructure.SetHP 0x432930 (raising HP only stores it + [+0x24]=1;
        no sound / debris / RNG), static scene invalidated as for walls, glow + debris spawned like a mended wall.
        RandInt draws: one per mended structure, HN order, after that hex's wall -> MP-deterministic.
v5 (2026-10-17 round 5, user: "dont repair houses, revert that" / debris shakes in place with a subtle green glow,
  then is flung at the wall; small subtle green burst on impact):
  STRUCTURES dropped again - walls + gates only (v4's THouse/TWorkshop/TTownhall/TMainStructure handling is gone; the
        camera centring stays).
  THREE kind-0x26 effects per mended wall: debris (marker 3/4 by (x+y)&1 = slot 3/4, alpha), its additive glow halo
        (marker 5/6 = slot 5/6, following the same debris paths) and the wall glow (marker 0 = slot 1).  The slot-pick
        caves now map every marker 3..6 of spell 216 to the slot of the same number (range check), others pass on.
v7 (2026-10-17 round 7, user: "I meant only one debris at a time from any hex, they should ALL launch one after the
  other, and only one debris from each source hex... when debris hits the wall I want a subtle crunch/hail noise"):
  ONE global queue per cast instead of 6 pre-drawn pieces per wall.  The sweep only MENDS and records the mended walls
  (<= 19, packed x | y << 16 on the stack); then Mp = min(M, NMAX 10) walls get per = clamp(10 // Mp, 1, 3) pieces each,
  N = per * Mp, handed out ROUND-ROBIN (piece k -> wall k % Mp, its j-th piece j = k // Mp).  Each piece gets its OWN
  source hex: HN 7..36 (rings 2-3) around its wall via CenterHNtoHX, searched from a deterministic start
  (wx*5 + wy*3 + j*11) mod 30, accepted when inside the level with a 1-hex margin, not a wall / gate hex and not already
  used by an earlier piece of this cast (no RNG -> MP-identical; a piece with no free source is simply skipped).
  Per piece three kind-0x26 effects share one timeline: MOVER slot 3 (grey rock) / 4 (brown stick, k % 3 == 1) and
  slot 5 (its additive green halo + the arrival burst) carry 3 points (item 0 = drawn position, 1 = source, 2 = target
  on the wall body = wall centre + TARGETS[j]); slot 7 = the hole in the ground, stationary at the source.  Marker dword
  [fx+0x24]: byte 0 = slot, byte 1 = the effect's clock c (ticks since the mend, advanced by the NF cave), byte 2 =
  launch tick L = LEAD + DELTA*k (20 + 6k), byte 3 = grow-start P = min(2k, 10).  Every wall also gets its glow (slot 1)
  with byte 3 = S = its first impact (IMP0 + DELTA*w = 25 + 6w; walls past Mp: 25).
  NF cave (every frame, all clients): c := clock, clock += 1; the frame [fx+0x10] is SET from c (blank before P, 8 grow
  frames, the 12 tremble frames LOOPED until L, then 15 post frames: 5 flight, shrink / burst, blank; glow: blank
  before S, then c - S + 1) - so one art set serves every delay; the movers' item 0 := source + (target - source) *
  ETAB[u] / 256 (y - ATAB[u]), u = clamp(c - L, 0, FLY): flung on an accelerating arc, ONE piece in flight at a time
  (flight 5 < spacing 6).  At c == L + FLY the rock / stick plays sound cue 2 (DUALER_MENDHIT.WAV) when sound is on
  ([map+0x129]; sound only -> MP-safe).  The show cave returns byte 0 of the marker.  Spell-216 kind-0x26 effects with
  another slot byte (0 / 2 / 6) pass on to the vanilla path as before.
Zone AoWTCPCK 0x448400..0x448C00 (verified zero, reloc-free, CODE): +0 prev gate target, +4 version, +8 prev nf,
+0xC prev show, +0x10 v7 data tables (ETAB / ATAB / TARGETS), caves after.
Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_mendwalls2
(first apply) / .bak_mendwalls<N> (in-place upgrade to vN).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
_ks = Ks(KS_ARCH_X86, KS_MODE_32)

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x448400, 0x448C00
VERSION = 7
PICK_SITES = [0x42A5E9, 0x430059]                   # kind-0x26 NewFrame / Show slot-pick `call` sites (v3)
SPELL = 216
GATE_SITES = [0x40B6F1, 0x40CBE7]                     # `call <NextStrike chain>`
V1_ZONE = (0x447400, 0x447800)                         # patch_tc_mendwalls_v1.py
V1_SITES = [(0x40C922, 0xE9), (0x40E35D, 0xE8)]
# v7 debris queue (ticks = the effect's own clock, byte [fx+0x25], counted from the mend frame; ~34.5 ticks/s)
NMAX, PERMAX = 10, 3                                  # at most 10 pieces per cast, at most 3 per wall
LEAD, DELTA, FLY = 20, 6, 5                           # piece k is flung at LEAD + DELTA*k for FLY ticks -> ONE in flight at a time
PMAX = 10                                             # piece k grows out of the ground at min(2k, PMAX)
POP, TREM, POST = 8, 12, 15                           # art: blank + 8 grow + 12 tremble (looped) + 15 post (5 flight + shrink/burst)
GLEN = 52                                             # wall glow: blank + 51 frames; frame 1 = the wall's first impact
IMP0 = LEAD + FLY                                     # first impact tick (wall w < Mp is first hit at IMP0 + DELTA*w)
HITCUE = 2                                            # sound cue 2 = DUALER_MENDHIT.WAV (third entry of the 216 sfx list)
SRCDY = 2                                             # px below the source hex centre where a piece sits
ETAB = [0, 19, 59, 113, 179, 256]                     # flight ease x256, u = 0..FLY: accelerating ~(u/5)^1.6 = flung
ATAB = [0, 9, 13, 13, 9, 0]                           # flight arc lift, px
TARGETS = [(-12, -44), (10, -48), (-3, -31)]           # px from the wall hex centre (MEND3_TARGETS[0:3]): on the wall body
PIECE_SLOTS = (3, 4, 5, 7)                            # 3 rock / 4 stick (movers, alpha), 5 halo (mover, additive), 7 hole (stationary)

GATE = """
    cmp dword ptr [eax+0x18], %(spell)d
    jne prev
    cmp dword ptr [eax+0x28], 0
    jne mend
prev:
    jmp %(prev)#x
mend:
    pushal
    mov dword ptr [eax+0x28], 0
    mov edi, eax
    call $D
    pop ebx
    sub ebx, $D
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    cmp byte ptr [eax+0x129], 0
    je nosnd
    mov eax, [ebx+0x46e8d0]
    mov eax, [eax]
    mov eax, [eax+0x84]
    mov edx, %(spell)d
    call 0x4029b4
    mov eax, [eax+0x28]
    xor edx, edx
    call 0x4022f4
nosnd:
    push 0
    movzx ecx, word ptr [edi+0x22]
    movzx edx, word ptr [edi+0x20]
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    mov esi, [eax]
    call dword ptr [esi+0xbc]
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    mov eax, [eax+0x10]
    xor edx, edx
    call 0x401e64
    test eax, eax
    je out
    mov esi, eax
    sub esp, 0xc0
    mov dword ptr [esp+0x08], 0
    xor ebp, ebp
hn:
    lea eax, [esp]
    push eax
    lea eax, [esp+8]
    push eax
    mov ecx, ebp
    movzx eax, word ptr [edi+0x20]
    movzx edx, word ptr [edi+0x22]
    call 0x4022ac
    mov edx, [esp]
    mov ecx, [esp+4]
    call wallat
    test eax, eax
    je next
    call mendone
    test al, al
    je next
    mov eax, [esp+0x08]
    mov edx, [esp+4]
    shl edx, 16
    or edx, [esp]
    mov [esp+0x20+eax*4], edx
    inc dword ptr [esp+0x08]
next:
    inc ebp
    cmp ebp, 19
    jb hn
    mov eax, [esp+0x08]
    test eax, eax
    je fin
    cmp eax, %(nmax)d
    jbe m1
    mov eax, %(nmax)d
m1:
    mov [esp+0x0c], eax
    mov ecx, eax
    mov eax, %(nmax)d
    xor edx, edx
    div ecx
    cmp eax, %(permax)d
    jbe m2
    mov eax, %(permax)d
m2:
    imul eax, dword ptr [esp+0x0c]
    mov [esp+0x10], eax
    xor ebp, ebp
gl:
    cmp ebp, [esp+0x08]
    jae pcs
    mov eax, %(imp0)d
    cmp ebp, [esp+0x0c]
    jae gl1
    imul ecx, ebp, %(delta)d
    add eax, ecx
gl1:
    shl eax, 24
    or eax, 1
    mov [esp+0xb8], eax
    mov eax, [esp+0x20+ebp*4]
    call hexc
    mov eax, [esp+0xb8]
    call mkfx
    inc ebp
    jmp gl
pcs:
    mov dword ptr [esp+0x98], 0
    xor ebp, ebp
pk:
    cmp ebp, [esp+0x10]
    jae fin
    mov eax, ebp
    xor edx, edx
    div dword ptr [esp+0x0c]
    mov [esp+0xa0], eax
    mov eax, [esp+0x20+edx*4]
    mov [esp+0x9c], eax
    movzx ecx, ax
    shr eax, 16
    lea eax, [eax+eax*2]
    lea ecx, [ecx+ecx*4]
    add eax, ecx
    imul ecx, dword ptr [esp+0xa0], 11
    add eax, ecx
    xor edx, edx
    mov ecx, 30
    div ecx
    mov [esp+0x1c], edx
    mov dword ptr [esp+0x18], 0
srch:
    mov eax, [esp+0x18]
    cmp eax, 30
    jae pnext
    inc dword ptr [esp+0x18]
    add eax, [esp+0x1c]
    xor edx, edx
    mov ecx, 30
    div ecx
    add edx, 7
    mov [esp+0x14], edx
    lea eax, [esp]
    push eax
    lea eax, [esp+8]
    push eax
    mov ecx, [esp+0x1c]
    movzx eax, word ptr [esp+0xa4]
    movzx edx, word ptr [esp+0xa6]
    call 0x4022ac
    mov edx, [esp]
    mov ecx, [esp+4]
    cmp edx, 1
    jl srch
    cmp ecx, 1
    jl srch
    mov eax, [esi+0xc]
    dec eax
    cmp edx, eax
    jge srch
    mov eax, [esi+0x10]
    dec eax
    cmp ecx, eax
    jge srch
    mov eax, ecx
    shl eax, 16
    or eax, edx
    mov [esp+0xa4], eax
    xor ecx, ecx
uc:
    cmp ecx, [esp+0x98]
    jae ucok
    cmp eax, [esp+0x70+ecx*4]
    je srch
    inc ecx
    jmp uc
ucok:
    mov edx, [esp]
    mov ecx, [esp+4]
    call wallat
    test eax, eax
    jne srch
    mov eax, [esp+0x98]
    mov ecx, [esp+0xa4]
    mov [esp+0x70+eax*4], ecx
    inc dword ptr [esp+0x98]
    mov eax, [esp+0xa4]
    call hexc
    add ecx, %(srcdy)d
    mov [esp+0xa8], edx
    mov [esp+0xac], ecx
    mov eax, [esp+0x9c]
    call hexc
    mov eax, [esp+0xa0]
    add edx, [ebx+%(tgt)#x+eax*8]
    add ecx, [ebx+%(tgt4)#x+eax*8]
    mov [esp+0xb0], edx
    mov [esp+0xb4], ecx
    lea eax, [ebp+ebp]
    cmp eax, %(pmax)d
    jbe tp
    mov eax, %(pmax)d
tp:
    shl eax, 24
    imul ecx, ebp, %(delta)d
    add ecx, %(lead)d
    shl ecx, 16
    or eax, ecx
    mov [esp+0xb8], eax
    mov eax, ebp
    xor edx, edx
    mov ecx, 3
    div ecx
    mov eax, 3
    cmp edx, 1
    jne rk
    mov eax, 4
rk:
    call mover
    mov eax, 5
    call mover
    mov eax, [esp+0xb8]
    or eax, 7
    mov edx, [esp+0xa8]
    mov ecx, [esp+0xac]
    call mkfx
pnext:
    inc ebp
    jmp pk
fin:
    add esp, 0xc0
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    test eax, eax
    je out
    mov esi, [eax+0xe4]
    test esi, esi
    je out
    mov esi, [esi+0xc]
    test esi, esi
    je out
    mov eax, [eax+0x120]
    test eax, eax
    je out
    mov ecx, [eax+8]
    mov edx, [eax+4]
lp:
    dec ecx
    js clear
    mov eax, [edx+ecx*4]
    test eax, eax
    je lp
    cmp dword ptr [eax+0x20], 0
    jle out
    jmp lp
clear:
    mov byte ptr [esi+0x4d], 0
out:
    popal
    ret

wallat:
    test edx, edx
    js wn
    test ecx, ecx
    js wn
    cmp edx, [esi+0xc]
    jge wn
    cmp ecx, [esi+0x10]
    jge wn
    mov eax, esi
    call 0x401e54
    test eax, eax
    je wn
    push eax
    mov edx, 0x220504
    mov ecx, [eax]
    call dword ptr [ecx+0x80]
    test eax, eax
    jne wy
    mov eax, [esp]
    mov edx, 0x220506
    mov ecx, [eax]
    call dword ptr [ecx+0x80]
wy:
    add esp, 4
    ret
wn:
    xor eax, eax
    ret

hexc:
    movzx edx, ax
    shr eax, 16
    mov ecx, eax
    shl ecx, 5
    add ecx, 16
    test dl, 1
    je hx1
    add ecx, 16
hx1:
    shl edx, 5
    add edx, 24
    ret

mover:
    or eax, [esp+0xbc]
    mov edx, [esp+0xac]
    mov ecx, [esp+0xb0]
    call mkfx
    push eax
    mov edx, [esp+0xb0]
    mov ecx, [esp+0xb4]
    call addpt
    mov eax, [esp]
    mov edx, [esp+0xb8]
    mov ecx, [esp+0xbc]
    call addpt
    add esp, 4
    ret

mkfx:
    push esi
    push eax
    push edx
    push ecx
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    mov dl, 0x26
    call 0x41c6ec
    mov esi, eax
    mov edx, [esp+4]
    mov ecx, [esp]
    call addpt
    mov eax, [esp+8]
    mov [esi+0x24], eax
    mov dword ptr [esi+0x14], 0x34
    mov dword ptr [esi+0x18], %(spell)d
    mov dword ptr [esi+0x2c], 0
    mov eax, esi
    add esp, 12
    pop esi
    ret

addpt:
    push esi
    push edx
    push ecx
    mov esi, eax
    mov dl, 1
    mov eax, [ebx+0x46eb24]
    call 0x401040
    mov edx, [esp+4]
    mov [eax+4], edx
    mov edx, [esp]
    mov [eax+8], edx
    mov edx, eax
    mov eax, [esi+0x1c]
    call 0x402de4
    add esp, 8
    pop esi
    ret

mendone:
    push esi
    push edi
    mov edi, eax
    movzx eax, byte ptr [edi+0x2d]
    dec eax
    cmp eax, 1
    ja m_no
    mov edx, [ebx+0x4693d0]
    test edx, edx
    je m_no
    mov esi, [edx+eax*4]
    mov eax, [edi+0x20]
    test eax, eax
    jle m_no
    cmp eax, esi
    jge m_no
    mov eax, esi
    shr eax, 1
    inc eax
    call 0x401020
    mov edx, esi
    shr edx, 2
    add eax, edx
    add eax, [edi+0x20]
    cmp eax, esi
    jle m_cap
    mov eax, esi
m_cap:
    mov edx, eax
    mov eax, edi
    call 0x405ae4
    mov eax, [edi+0x20]
    shl eax, 2
    lea edx, [esi+esi*2]
    cmp eax, edx
    jl m_look
    mov dword ptr [edi+0x24], 0
m_look:
    mov eax, [edi+4]
    test eax, eax
    je m_yes
    mov eax, [eax+4]
    test eax, eax
    je m_yes
    mov eax, [eax+0x1c]
    test eax, eax
    je m_yes
    mov byte ptr [eax+0x30], 1
m_yes:
    mov al, 1
    pop edi
    pop esi
    ret
m_no:
    xor eax, eax
    pop edi
    pop esi
    ret
"""

# NF (kind-0x26 NewFrame slot pick @0x42A5E9; eax = the spell's gfx list, [ebp-8] = fx; returns edx = slot, eax kept).
# Spell 216 with slot byte 1 / 3..7: drives the frame [fx+0x10] from the effect's clock, moves the movers, plays the hit.
NF = """
    push eax
    mov eax, [ebp-8]
    cmp dword ptr [eax+0x18], %(spell)d
    jne pass
    movzx eax, byte ptr [eax+0x24]
    cmp eax, 1
    je mine
    cmp eax, 3
    jb pass
    cmp eax, 7
    jbe mine
pass:
    pop eax
    jmp %(prev)#x
mine:
    push ebx
    push esi
    push edi
    mov esi, [ebp-8]
    call $D
    pop ebx
    sub ebx, $D
    movzx edi, byte ptr [esi+0x25]
    cmp edi, 0xff
    jae nclk
    inc byte ptr [esi+0x25]
nclk:
    movzx eax, byte ptr [esi+0x24]
    cmp eax, 1
    jne piece
    movzx edx, byte ptr [esi+0x27]
    xor eax, eax
    cmp edi, edx
    jb gset
    mov eax, edi
    sub eax, edx
    inc eax
    cmp eax, %(glast)d
    jbe gset
    mov eax, %(glast)d
gset:
    mov [esi+0x10], eax
    jmp done
piece:
    movzx edx, byte ptr [esi+0x27]
    xor eax, eax
    cmp edi, edx
    jb pset
    mov eax, edi
    sub eax, edx
    cmp eax, %(pop)d
    jae pa1
    inc eax
    jmp pset
pa1:
    movzx ecx, byte ptr [esi+0x26]
    cmp edi, ecx
    jae pb1
    sub eax, %(pop)d
    xor edx, edx
    push ecx
    mov ecx, %(trem)d
    div ecx
    pop ecx
    lea eax, [edx+%(trem0)d]
    jmp pset
pb1:
    mov eax, edi
    sub eax, ecx
    cmp eax, %(postlast)d
    jbe pc1
    mov eax, %(postlast)d
pc1:
    add eax, %(post0)d
pset:
    mov [esi+0x10], eax
    movzx eax, byte ptr [esi+0x24]
    cmp eax, 3
    jb done
    cmp eax, 5
    ja done
    call move
    movzx eax, byte ptr [esi+0x24]
    cmp eax, 5
    je done
    movzx eax, byte ptr [esi+0x26]
    add eax, %(fly)d
    cmp edi, eax
    jne done
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    cmp byte ptr [eax+0x129], 0
    je done
    mov eax, [ebx+0x46e8d0]
    mov eax, [eax]
    mov eax, [eax+0x84]
    mov edx, %(spell)d
    call 0x4029b4
    mov eax, [eax+0x28]
    mov edx, %(hitcue)d
    call 0x4022f4
done:
    movzx edx, byte ptr [esi+0x24]
    pop edi
    pop esi
    pop ebx
    pop eax
    ret

move:
    push ebp
    movzx eax, byte ptr [esi+0x26]
    mov ebp, edi
    sub ebp, eax
    jge mv1
    xor ebp, ebp
mv1:
    cmp ebp, %(fly)d
    jle mv2
    mov ebp, %(fly)d
mv2:
    mov eax, [esi+0x1c]
    mov edx, 1
    call 0x402df4
    test eax, eax
    je mvx
    push dword ptr [eax+4]
    push dword ptr [eax+8]
    mov eax, [esi+0x1c]
    mov edx, 2
    call 0x402df4
    test eax, eax
    je mvy
    push dword ptr [eax+4]
    push dword ptr [eax+8]
    mov eax, [esi+0x1c]
    xor edx, edx
    call 0x402df4
    test eax, eax
    je mvz
    mov ecx, eax
    mov eax, [esp+4]
    sub eax, [esp+12]
    imul eax, dword ptr [ebx+%(etab)#x+ebp*4]
    sar eax, 8
    add eax, [esp+12]
    mov [ecx+4], eax
    mov eax, [esp]
    sub eax, [esp+8]
    imul eax, dword ptr [ebx+%(etab)#x+ebp*4]
    sar eax, 8
    add eax, [esp+8]
    sub eax, dword ptr [ebx+%(atab)#x+ebp*4]
    mov [ecx+8], eax
mvz:
    add esp, 8
mvy:
    add esp, 8
mvx:
    pop ebp
    ret
"""

# SHOW (kind-0x26 Show slot pick @0x430059; [ebp-4] = fx; returns eax = slot).  Others go on with eax = fx (as v3-v5).
SHOW = """
    mov eax, [ebp-4]
    cmp dword ptr [eax+0x18], %(spell)d
    jne p
    movzx eax, byte ptr [eax+0x24]
    cmp eax, 1
    je mine
    cmp eax, 3
    jb p0
    cmp eax, 7
    ja p0
mine:
    ret
p0:
    mov eax, [ebp-4]
p:
    jmp %(prev)#x
"""


def tables():
    """v7 data: ETAB[6], ATAB[6] (dwords), TARGETS[3] (dx, dy dwords)."""
    b = struct.pack("<6i", *ETAB) + struct.pack("<6i", *ATAB)
    for dx, dy in TARGETS: b += struct.pack("<ii", dx, dy)
    return b


def build(prev, prev_nf, prev_show):
    """zone image + {data, gate, nf, show} addresses.  Header +0 prev gate, +4 version, +8 prev nf, +0xC prev show."""
    out = bytearray(struct.pack("<IIII", prev, VERSION, prev_nf, prev_show)); where = {}
    where["data"] = ZONE + len(out); data = tables(); out += data
    etab, atab, tgt = where["data"], where["data"] + 24, where["data"] + 48
    P = dict(spell=SPELL, nmax=NMAX, permax=PERMAX, imp0=IMP0, delta=DELTA, lead=LEAD, pmax=PMAX, srcdy=SRCDY,
             tgt=tgt, tgt4=tgt + 4, etab=etab, atab=atab, fly=FLY, pop=POP, trem=TREM, trem0=1 + POP,
             post0=1 + POP + TREM, postlast=POST - 1, glast=GLEN - 1, hitcue=HITCUE)
    for k, src in (("gate", GATE % dict(P, prev=prev)), ("nf", NF % dict(P, prev=prev_nf)), ("show", SHOW % dict(P, prev=prev_show))):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[k] = va
        out += asm_pic(src, va) if k in ("gate", "nf") else bytes(_ks.asm(src, va)[0])
    assert ZONE + len(out) <= ZONE_END, "zone overflow"
    return bytes(out), where


def call_target(d, site):
    b = d[site - V2F:site - V2F + 5]
    return site + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE8 else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    cur = [call_target(d, s) for s in GATE_SITES]
    if None in cur or len(set(cur)) != 1: print("ABORT: gate sites disagree / not calls: %s" % cur); return 1
    c = cur[0]
    hdr_prev, hdr_ver, hdr_nf, hdr_show = struct.unpack_from("<IIII", zl, 0)
    prev = hdr_prev if any(zl) else c
    pick = [call_target(d, s) for s in PICK_SITES]
    if None in pick: print("ABORT: slot-pick sites are not calls: %s" % pick); return 1
    v3 = any(zl) and hdr_ver >= 3
    prev_nf, prev_show = (hdr_nf, hdr_show) if v3 else (pick[0], pick[1])
    zone, where = build(prev, prev_nf, prev_show)
    gate = where["gate"]
    st = "ours" if c == gate else "ours(old layout)" if any(zl) and ZONE <= c < ZONE_END else "OTHER(%#x)" % c if any(zl) else "chain(%#x)" % c
    zst = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "older build (v%d)" % hdr_ver if st.startswith("ours") else "DIFFERS"
    pst = []
    for k, t in zip(("nf", "show"), pick):
        if t == where[k]: pst.append("ours")
        elif v3 and ZONE <= t < ZONE_END: pst.append("ours(old layout)")
        elif v3: pst.append("OTHER(%#x)" % t)
        else: pst.append("chain(%#x)" % t)
    v1 = []
    for site, op in V1_SITES:
        b = d[site - V2F:site - V2F + 5]
        t = site + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == op else None
        if t is not None and V1_ZONE[0] <= t < V1_ZONE[1]: v1.append(hex(site))
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + 5 for s in GATE_SITES + PICK_SITES)]
    print("AoWTCPCK gate %s | slot picks nf %s show %s | zone %s (%d B, data @%#x gate @%#x nf @%#x show @%#x) | prev gate %#x nf %#x show %#x | v1 hooks live: %s | relocs %s"
          % (st, pst[0], pst[1], zst, len(zone), where["data"], gate, where["nf"], where["show"], prev, prev_nf, prev_show, v1 or "none", bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for k in ("gate", "nf", "show"):
            print("  --", k)
            for i in md.disasm(zone[where[k] - ZONE:], where[k]):
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic == "int3" or (k == "show" and i.mnemonic == "jmp" and i.address > where["show"] + 0x20): break
    if bad or st.startswith("OTHER") or zst == "DIFFERS" or any(p.startswith("OTHER") for p in pst):
        print("ABORT (site/zone/reloc; a site chained by another patch since -> revert that one first, LIFO)"); return 1
    n = bytearray(d)
    if a.revert:
        if not st.startswith("ours"): print("already reverted"); return 0
        for s in GATE_SITES: n[s - V2F + 1:s - V2F + 5] = struct.pack("<i", prev - (s + 5))
        if v3:
            for s, p in zip(PICK_SITES, (hdr_nf, hdr_show)): n[s - V2F + 1:s - V2F + 5] = struct.pack("<i", p - (s + 5))
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if v1: print("ABORT: patch_tc_mendwalls_v1.py is still applied (%s) - run it with --revert first" % v1); return 1
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for s in GATE_SITES: n[s - V2F + 1:s - V2F + 5] = struct.pack("<i", gate - (s + 5))
        for s, k in zip(PICK_SITES, ("nf", "show")): n[s - V2F + 1:s - V2F + 5] = struct.pack("<i", where[k] - (s + 5))
    if n == d: print("already %s" % ("reverted" if a.revert else "applied (v%d)" % VERSION)); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)%s." % (" - in-place upgrade v%d -> v%d" % (hdr_ver, VERSION) if any(zl) and hdr_ver < VERSION and not a.revert else ""))
    if not (a.apply or a.revert): return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        suf = ".bak_mendwalls%d" % VERSION if any(zl) and hdr_ver < VERSION else ".bak_mendwalls2"
        bak = bak_path(a.dll, suf)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
