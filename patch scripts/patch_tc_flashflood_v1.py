#!/usr/bin/env python3
r"""
FLASH FLOOD (223, Water L4, 2026-10-17) - engine half.  AoWTCPCK.dll only.

User spec: combat spell, infinite range, targets ALL units on the battlefield (both sides, like Tremors) without
Floating / Flying / Sailing / Wind Walking; R200 C6; ATK 8 / DMG 5 Physical; -50 % damage vs units with Swimming /
Liquid Form / Swampwalk (0xBA) / Water Walking; displaces every targetable unit in a random direction by up to 4 hexes,
no two units on one hex; Tremors-like presentation: a dense influx of flowing blue water particles over the whole
view with rolling crests + a gentle shake (gentler than Tremors, EVEN pixel offsets only - the fog-stipple lesson).

The spell is a pipeline TTremors clone (TTremors: classref cell 0x557F50C0 / Create 0x557F8C74 / site 0x557FA698; id
0x70, SpellTypes class 29 = 0x1D, pfs key 122).  RE (AoWTCPCK):
  * class 29 TE (TCAbRangedTE.Execute 0x40B2F8) throws ONE strike = a kind-29 effect ([fx+0x34] = 0x1D, [fx+0x14] =
    0x34, [fx+0x18] = spell) whose NewFrame (kind table 0x429EF7 -> 0x42D83E) is the Tremors CAMERA shake: tick 0
    saves the view origin [map+0x80]/[+0x84] as point 0 of [fx+0x1C]; ticks 1..119 SetOrigin (map VMT+0xC0: eax map,
    edx x, ecx y, [esp] = level [map+0x88]) to origin + RandInt jitter (ramp 1-29, +-5 px 30-89, fade 90-119); tick
    120 -> [fx+0x10] = -1.  Kind 29 draws nothing (Show table 0x42F9DF -> 0x43012E).
  * the damage: TE Execute's per-effect chain (loop over [map+0x11C], fx = [ebp-0x20]) case 0x40BA83: [fx+0x14] ==
    0x34, [fx+0x18] == 0x70 (HARD-CODED), [fx+0x10] == 0x59 -> map msg 0x31004 (msg+8 = caster [te+0x10]) to every
    field x 6..0x3A, y 6..0x34; the unit HS handler (0x42165F) skips movement bit 0x02 (flying / floating / wind
    walking) and terrain 0 / 9 hexes, then CreateCA = GetSpell(0x70 HARD-CODED).VMT+0x78 (push 0, edx caster, ecx cu)
    -> [ca+0x10] = rolled damage (TCombatSpellCA.Setup) -> hurt anim 0x4236E0 (hs, dl 4) -> [map+0xE4].Add(ca) ->
    ca.VMT+0x2C.  Walls / structures answer 0x31004 too (0x406222 / 0x4107F7 / 0x4330F2, GetSpell(0x70)).
Hooks (both sites vanilla, reloc-free; the zone keeps their original bytes for an exact --revert):
  TEK 0x40BA8C (`mov eax,[ebp-0x20] / cmp [eax+0x18],0x70 / jne 0x40BB09`, 9 B) -> jmp tek: 0x70 -> vanilla; spell 223
      kind 29 at tick FLOOD_TICK (0x59) -> FLOOD (once), other 223 effects (the particles) -> done; else next case.
  NF  0x42D83E (`mov eax,[ebp-8] / mov eax,[eax+0x10]`, 6 B) -> jmp nf: kind-29 of 223 -> our NewFrame (tick 0 =
      vanilla origin save; ticks 1..END-1 = VIS; END -> tick -1), else vanilla.
FLOOD (TE token = deterministic on every machine; walls / structures are never touched - no map broadcast):
  1. collect every unit HS on fields x 6..58 / y 6..52 (FindOwnedChild 0x220104): cu alive (VMT+0x60), unit movement
     bit 0x02 clear (VMT+0xE8: flyer / floater / wind walker, Grounded units count as walkers) and not Sailing (0x17,
     GetAbilityEnabled VMT+0x148) -> list (scan order x-major, max MAXN).
  2. damage, per listed unit in order = the vanilla handler's sequence with GetSpell(223); [ca+0x10] -> d - d/2 when
     the unit has Swimming 2 / Liquid Form 0xA6 / Swampwalk 0xBA / Water Walking 0xA4 (creation-time, MP-safe).
  3. displacement, per listed unit in order, still alive and still its own hex's unit: r = RandInt(60) (the SYNCED
     combat RNG 0x401020, one draw per such unit); candidates = HN (r + k) % 60 + 1, k = 0..59 (CenterHNtoHX rings 1..4
     round the unit = every hex up to 4 away); the first one on the battlefield (6..58 / 6..52), holding no unit and
     ValidLocation for THIS unit (TCombatMoveControlSettings built for it, Activated ONCE per unit, Gust v2's recipe)
     wins -> Void Step's one-step warp (path [dest, src] cost 0, CreateCombatMoveTE -> Validate -> ExecuteDefaultMove).
     Units move one after another, so a later unit sees the earlier ones on their new hexes: no two share a hex.
     No candidate -> the unit stays.
VIS (kind-29 NewFrame of 223; visual only - a private hash, never the game's Random):
  * shake ticks SHK0..SHK1: SetOrigin(origin + (ox, oy)), ox in {-A, 0, +A}, oy in {-2, 0, +2}, A = 2 (4 during the
    surge SURGE0..SURGE1 round the flood hit); new offset every 2 ticks; all offsets EVEN; SHK1 restores the origin.
  * particles ticks P0..P1: each tick N_SPRAY kind-0x1F particles at hashed positions over the CURRENT viewport
    ([map+0x80..+0x90]) + every BAND_EVERY ticks a curved crest band of BAND_N particles sharing one phase; every
    particle drifts right (U0..U0+3 px/tick, a slight downward drift) on an elliptical orbit (R0..R0+7 px, period
    64/W ticks) = rolling water; life LMIN..LMIN+15 ticks.  A kind-0x1F particle draws 223's gfx slot 0 frame
    (fx address mod 3) through GFXE's intensity table, fading over its path; its path end is a no-target landing
    (pure visual, like Gust / Shockwave).
Zone AoWTCPCK 0x44B000..0x44C000 (verified zero, reloc-free): +0 magic 'FFLD' + version, +8 TEK original (9 B),
+0x11 NF original (6 B), code at +0x20.  PIC (call/pop delta) for every in-image absolute (AoWTCPCK rebases).
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_flashflood.
Chain notes: nothing else hooks these two sites today.  A later patch that chains in front of TEK / NF must be
reverted before this one (LIFO); this script refuses to revert when a site no longer jumps into its zone.
v2 (2026-10-17, user: "change to 4 ATK / 7 DMG ... move all targetable units even if not hit ... before it sweeps
across the whole map I want it to start on one side and sweep across"):
  * stats = pipeline pokes (ATK 4 / DMG 7); displacement already covered missed / 0-damage units (the move loop walks
    the whole collected list, independent of the rolled damage) - verified in the emulator (tmp\flood2).
  * SWEEP: ticks F0..F1 a flood FRONT crosses the view: S = (vw + 480) * (t - F0) / (F1 - F0); spray x only in
    [vx - 240, vx - 240 + S), crest bands only while S > 40, plus N_FRONT surf particles per tick right on the front;
    from F1 on, the v1 full-field rolling water (unchanged).  Direction: TEK latches {fx, dir} in .idata slack SIDE
    (0x479FF8) while the carrier's tick < F0 from the caster [te+0x10] (cu -> HS [cu+0x60], back-pointer checked,
    VMT+0x74 x): caster x < XMID -> dir 1 (enters left, flows right), else dir 2 = everything mirrored about the view
    centre (spawn x' = 2 vx + vw - x, path dx negated).  vis uses the latch only when it names THIS carrier (else dir 1).
  * shake now starts at SHK0 = 28 (front half-way); still EVEN offsets, surge +-4 round the hit (tick 0x59 unchanged).
v3 (2026-10-17, user follow-up): units with Swimming (2) / Water Walking (0xA4) / Liquid Form (0xA6) are displaced only
HALF as far (rings 1..2 = HN 1..18 instead of 1..60); SAILING (0x17) units are now collected too: NO damage (no CA, no
hurt, no list entry) and half distance, landing only where ValidLocation allows them (water).  Swampwalk (0xBA) keeps
the FULL distance (it is not a swimming/water-walking ability; it still takes half damage).  Flyers / floaters / wind
walkers stay excluded.  Entry +8 = flags (bit0 no damage, bit1 half distance); one synced RandInt(n) per moved unit,
n = 18 for half-distance units else 60, candidates HN (r + k) % n + 1, k < n.
v4 (2026-10-17, user: "flash flood sfx seems to continue on loop after spell finishes ... swampwalk should only move 2
hexes like the other swimmers ... units should not be pushed onto walls (unless they have 0 HP / are gone)"):
  * LOOP ROOT CAUSE: class 29's TE Execute (TCAbRangedTE.Execute 0x40B642, the class-0x1D branch of the dispatch at
    0x40B636) plays sound 0 with SoundP TSFXLibrary.PlayEx(loop flag p3 = 1, count p2 = 0 = forever), stores the sample
    in [te+0x2c] and only frees (= stops) it when the TE ends (0x40CC55: effect list empty).  Vanilla Tremors (0x70) is
    excluded from the caster's cast-animation sound (0x421D7A), so it plays exactly that one looped rumble.  223 is NOT
    in that exclusion (castsnd cave 0x43C900), so it ALSO gets the one-shot cue 0 at the cast animation, and the TE's
    looped copy kept repeating the 4.5 s flood WAV until the TE ended (and restarts whenever the TE outlives the WAV).
    FIX: new site SND 0x40B642 (the 10-byte push block `6a01 6a00 6a01 6a00 6a00`) -> snd: spell 223 skips the PlayEx
    entirely ([te+0x2c] stays 0, so the TE-end free is skipped too) and continues at 0x40B679; every other spell runs
    the original pushes.  223's sound = the cast animation's one-shot Play (no loop, auto-freed by SoundP).
  * Swampwalk (0xBA) joins the half-distance group (HN 1..18); it keeps half damage.
  * destination check: a candidate hex holding a TCityWall (0x220504) or TCityWallDoor (0x220506) with HP [+0x20] > 0
    is rejected (destroyed sections, HP <= 0, stay valid), before ValidLocation.
  Header grows to 0x30 (+0x17 SND original, 10 B); code at +0x30.
"""
import argparse, os, re, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x44B000, 0x44C000
CODE = ZONE + 0x30
MAGIC, VERSION = b"FFLD", 4
SPELL = 223
SITES = [("TEK", 0x40BA8C, bytes.fromhex("8b45e0837818707574"), "tek"),
         ("NF", 0x42D83E, bytes.fromhex("8b45f88b4010"), "nf"),
         ("SND", 0x40B642, bytes.fromhex("6a016a006a016a006a00"), "snd")]     # v4: class-29 TE looped PlayEx

# battlefield + displacement
X0, X1, Y0, Y1 = 6, 0x3B, 6, 0x35          # Tremors' own field range (x 6..58, y 6..52)
MAXN = 64                                   # listed units (64 x 16 B on the stack)
NHN = 60                                    # HN 1..60 = rings 1..4
NHALF = 18                                  # v3: HN 1..18 = rings 1..2 (half distance)
HALFAB = (0x02, 0xA6, 0xA4, 0xBA)           # v3: Swimming / Liquid Form / Water Walking (+ v4 Swampwalk) -> half distance
FLOOD_TICK = 0x59                           # the vanilla Tremors damage tick (~2.6 s)
RESIST = (0x02, 0xA6, 0xBA, 0xA4)           # Swimming / Liquid Form / Swampwalk / Water Walking
SAILING = 0x17
# visuals
END = 112                                   # kind-29 carrier life (ticks)
SHK0, SHK1 = 28, 104                        # shake window (SHK1 restores the origin); v2: starts once the front is half-way
SURGE0, SURGE1 = 84, 96                     # +-4 px surge round the hit
P0, P1 = 4, 98                              # particle spawn window (v2: P0 = F0, the sweep start)
F0, F1 = 4, 52                              # v2 sweep: the flood front crosses the view (+-240 px margins) over ticks F0..F1 (~1.4 s)
N_FRONT = 8                                 # v2: extra particles per tick ON the advancing front (the leading surf)
XMID = (X0 + X1) // 2                       # v2: caster hex x < XMID -> the flood enters from the left (flows away from the caster)
SIDE = 0x479FF8                             # v2: .idata page slack (RW, zero in the file; Gust v7 uses 0x479FF0): {fx, dir}
N_SPRAY = 10                                # scattered particles per tick
BAND_EVERY, BAND_N = 4, 18                  # crest band cadence / size
BAND_DY, CURV8 = 22, 5                      # band spacing (px) / crest curvature (eighths of a px per m^2)
LMIN, U0, R0, W = 30, 7, 4, 3               # life, drift px/tick, orbit radius, orbit step (64 = full turn)

A = dict(nhalf=NHALF, spell=SPELL, x0=X0, x1=X1, y0=Y0, y1=Y1, maxn=MAXN, nhn=NHN, ftick=FLOOD_TICK, sailing=SAILING,
         end=END, f0=F0, f1=F1, fspan=F1 - F0, nfront=N_FRONT, xmid=XMID, side=SIDE, shk0=SHK0, shk1=SHK1, surge0=SURGE0, surge1=SURGE1, p0=P0, p1=P1, nspray=N_SPRAY,
         bandmask=BAND_EVERY - 1, bandn=BAND_N, bandhalf=BAND_N // 2, banddy=BAND_DY, curv8=CURV8, lmin=LMIN, u0=U0, r0=R0, w=W,
         mapptr=0x469420, gmap=0x46C064, p8d0=0x46E8D0, p8d4=0x46E8D4, pdc08=0x46DC08,
         f298c=0x40298C, getspell=0x4029B4, hurt=0x4236E0, listadd=0x40259C, randint=0x401020,
         getmaplevel=0x401E64, getfield=0x401E54, hn2hx=0x4022AC,
         setcls=0x4129A8, setcreate=0x40263C, setsrcpos=0x40266C, setrelease=0x40265C, cmptable=0x4029BC,
         getplayer=0x402544, xylcls=0x46E940, xylcreate=0x401AFC, xyladd=0x401B04, objfree=0x401050,
         createmovete=0x40F548, validate=0x4081EC, execdefmove=0x408278,
         iat_gp=0x46E7CC, gp_s=0x557268E4, ep_act=0x5574646C, ep_valid=0x557458E8, ep_deact=0x557466B4,
         addfx=0x41C6EC, txyz=0x46EB24, tobjcreate=0x401040, xyzadd=0x402DE4, xyzget=0x402DF4, xyzcount=0x402DFC,
         tek_van=0x40BA95, tek_next=0x40BB09, tek_done=0x40CAF2,
         nf_van=0x42D844, nf_tick0=0x42D878, nf_tail=0x42E3A3, snd_cont=0x40B64C, snd_skip=0x40B679)

SIN = [int(round(127 * __import__("math").sin(2 * __import__("math").pi * k / 64))) for k in range(64)]
COS = SIN[16:] + SIN[:16]


def src():
    a = dict(A)
    resist = "\n".join("""
        mov edx, %d
        mov eax, [ebp-0x5c]
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz d_half""" % r for r in RESIST)
    a["resist"] = resist
    a["halfchk"] = chr(10).join("""
        mov eax, [ebp-0x20]
        mov edx, %d
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz c_store""" % r for r in HALFAB)
    a["sintab"] = ", ".join(str(v & 0xFF) for v in SIN)
    a["costab"] = ", ".join(str(v & 0xFF) for v in COS)
    return """
    tek:
        mov eax, [ebp-0x20]
        cmp dword ptr [eax+0x18], 0x70
        je %(tek_van)#x
        cmp dword ptr [eax+0x18], %(spell)d
        jne %(tek_next)#x
        cmp byte ptr [eax+0x34], 0x1d
        jne %(tek_done)#x
        cmp dword ptr [eax+0x10], %(f0)d
        jge t_tick
        pushad
        call $D
        pop ebx
        sub ebx, $D
        call side
        popad
        mov eax, [ebp-0x20]
    t_tick:
        cmp dword ptr [eax+0x10], %(ftick)d
        jne %(tek_done)#x
        pushad
        mov esi, [ebp-4]
        call $D
        pop ebx
        sub ebx, $D
        call flood
        popad
        jmp %(tek_done)#x

    nf:
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %(spell)d
        jne nf_van
        cmp byte ptr [eax+0x34], 0x1d
        jne nf_van
        mov ecx, [eax+0x10]
        test ecx, ecx
        jz %(nf_tick0)#x
        cmp ecx, %(end)d
        jge nf_end
        pushad
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        call vis
        popad
        jmp %(nf_tail)#x
    nf_end:
        mov dword ptr [eax+0x10], -1
        jmp %(nf_tail)#x
    nf_van:
        mov eax, [eax+0x10]
        jmp %(nf_van)#x

    snd:
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(spell)d
        je snd_skip
        push 1
        push 0
        push 1
        push 0
        push 0
        jmp %(snd_cont)#x
    snd_skip:
        jmp %(snd_skip)#x

    flood:
        push ebp
        mov ebp, esp
        sub esp, 0x460
        mov [ebp-0x58], esi
        mov eax, [ebx+%(iat_gp)#x]
        sub eax, %(gp_s)#x
        mov [ebp-4], eax
        mov eax, [ebx+%(mapptr)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getmaplevel)#x
        mov [ebp-8], eax
        mov dword ptr [ebp-0xc], 0
        mov dword ptr [ebp-0x10], %(x0)d
    c_x:
        mov dword ptr [ebp-0x14], %(y0)d
    c_y:
        mov edx, [ebp-0x10]
        mov ecx, [ebp-0x14]
        call field_at
        test eax, eax
        jz c_next
        mov edx, 0x220104
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz c_next
        mov [ebp-0x24], eax
        mov eax, [eax+0x1c]
        test eax, eax
        jz c_next
        mov [ebp-0x1c], eax
        mov edx, [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz c_next
        mov eax, [ebp-0x1c]
        mov eax, [eax+0x4c]
        test eax, eax
        jz c_next
        mov [ebp-0x20], eax
        mov edx, [eax]
        call dword ptr [edx+0xe8]
        test al, 2
        jnz c_next
        mov edi, 3
        mov eax, [ebp-0x20]
        mov edx, %(sailing)d
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz c_store
        mov edi, 2
        %(halfchk)s
        xor edi, edi
    c_store:
        mov eax, [ebp-0xc]
        cmp eax, %(maxn)d
        jge c_next
        shl eax, 4
        lea edx, [ebp-0x460]
        add edx, eax
        mov ecx, [ebp-0x1c]
        mov [edx], ecx
        mov ecx, [ebp-0x24]
        mov [edx+4], ecx
        mov [edx+8], edi
        mov ecx, [ebp-0x14]
        mov [edx+12], ecx
        inc dword ptr [ebp-0xc]
    c_next:
        inc dword ptr [ebp-0x14]
        cmp dword ptr [ebp-0x14], %(y1)d
        jl c_y
        inc dword ptr [ebp-0x10]
        cmp dword ptr [ebp-0x10], %(x1)d
        jl c_x

        mov dword ptr [ebp-0x18], 0
    d_loop:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0xc]
        jge d_end
        shl eax, 4
        lea edi, [ebp-0x460]
        add edi, eax
        test byte ptr [edi+8], 1
        jnz d_nx
        mov eax, [ebx+%(p8d4)#x]
        mov eax, [eax]
        mov edx, 0xffffff
        call %(f298c)#x
        mov edx, [ebx+%(pdc08)#x]
        mov [edx], eax
        push 0
        mov eax, [ebx+%(p8d0)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(spell)d
        call %(getspell)#x
        mov edx, [ebp-0x58]
        mov edx, [edx+0x10]
        mov ecx, [edi]
        mov esi, [eax]
        call dword ptr [esi+0x78]
        mov [ebp-0x60], eax
        mov eax, [edi]
        mov eax, [eax+0x4c]
        mov [ebp-0x5c], eax
        test eax, eax
        jz d_hit
        %(resist)s
        jmp d_hit
    d_half:
        mov eax, [ebp-0x60]
        movzx ecx, byte ptr [eax+0x10]
        mov edx, ecx
        shr edx, 1
        sub ecx, edx
        mov [eax+0x10], cl
    d_hit:
        mov eax, [ebp-0x60]
        cmp byte ptr [eax+0x10], 0
        jbe d_add
        mov dl, 4
        mov eax, [edi+4]
        call %(hurt)#x
    d_add:
        mov eax, [ebx+%(gmap)#x]
        mov eax, [eax+0xe4]
        mov edx, [ebp-0x60]
        call %(listadd)#x
        mov eax, [ebp-0x60]
        mov edx, [eax]
        call dword ptr [edx+0x2c]
    d_nx:
        inc dword ptr [ebp-0x18]
        jmp d_loop
    d_end:

        mov dword ptr [ebp-0x18], 0
    m_loop:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0xc]
        jge m_end
        shl eax, 4
        lea edi, [ebp-0x460]
        add edi, eax
        mov eax, [edi]
        mov [ebp-0x1c], eax
        mov edx, [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz m_next
        mov eax, [ebp-0x1c]
        mov eax, [eax+0x60]
        test eax, eax
        jz m_next
        mov [ebp-0x24], eax
        mov edx, [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        mov [ebp-0x28], eax
        mov eax, [ebp-0x24]
        mov edx, [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        mov [ebp-0x2c], eax
        mov eax, [ebp-0x24]
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, 0x220104
        jne m_next
        mov eax, %(nhn)d
        test byte ptr [edi+8], 2
        jz m_nn
        mov eax, %(nhalf)d
    m_nn:
        mov [ebp-0x60], eax
        call %(randint)#x
        mov [ebp-0x30], eax
        mov dword ptr [ebp-0x48], 0
        call mk_settings
        test al, al
        jz m_rel
        mov dword ptr [ebp-0x34], 0
    m_cand:
        mov eax, [ebp-0x30]
        add eax, [ebp-0x34]
        xor edx, edx
        mov ecx, [ebp-0x60]
        div ecx
        inc edx
        mov ecx, edx
        lea eax, [ebp-0x38]
        push eax
        lea eax, [ebp-0x3c]
        push eax
        mov edx, [ebp-0x2c]
        mov eax, [ebp-0x28]
        call %(hn2hx)#x
        mov edx, [ebp-0x38]
        mov ecx, [ebp-0x3c]
        cmp edx, %(x0)d
        jl m_cn
        cmp edx, %(x1)d
        jge m_cn
        cmp ecx, %(y0)d
        jl m_cn
        cmp ecx, %(y1)d
        jge m_cn
        call field_at
        test eax, eax
        jz m_cn
        push eax
        mov edx, 0x220104
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz m_cnp
        mov eax, [esp]
        mov edx, 0x220504
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz m_gate
        cmp dword ptr [eax+0x20], 0
        jg m_cnp
    m_gate:
        mov eax, [esp]
        mov edx, 0x220506
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz m_free
        cmp dword ptr [eax+0x20], 0
        jg m_cnp
    m_free:
        add esp, 4
        push 0
        mov ecx, [ebp-0x3c]
        mov edx, [ebp-0x38]
        mov eax, [ebp-0x44]
        mov esi, [ebp-4]
        add esi, %(ep_valid)#x
        call esi
        test al, al
        jz m_cn
        mov eax, [ebp-0x38]
        mov [ebp-0x4c], eax
        mov eax, [ebp-0x3c]
        mov [ebp-0x50], eax
        mov dword ptr [ebp-0x48], 1
        jmp m_deact
    m_cnp:
        add esp, 4
    m_cn:
        inc dword ptr [ebp-0x34]
        mov eax, [ebp-0x34]
        cmp eax, [ebp-0x60]
        jl m_cand
    m_deact:
        mov eax, [ebp-0x44]
        mov ecx, [ebp-4]
        add ecx, %(ep_deact)#x
        call ecx
    m_rel:
        mov eax, [ebp-0x40]
        call %(setrelease)#x
        cmp dword ptr [ebp-0x48], 0
        je m_next
        call warp
    m_next:
        inc dword ptr [ebp-0x18]
        jmp m_loop
    m_end:
        mov esp, ebp
        pop ebp
        ret

    field_at:
        test edx, edx
        js fa_no
        test ecx, ecx
        js fa_no
        mov eax, [ebp-8]
        cmp edx, [eax+0xc]
        jge fa_no
        cmp ecx, [eax+0x10]
        jge fa_no
        call %(getfield)#x
        ret
    fa_no:
        xor eax, eax
        ret

    mk_settings:
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(setcls)#x]
        call %(setcreate)#x
        mov [ebp-0x40], eax
        mov esi, eax
        push 0
        mov ecx, [ebp-0x2c]
        mov edx, [ebp-0x28]
        mov eax, esi
        call %(setsrcpos)#x
        mov eax, [ebp-0x1c]
        mov edx, [eax+0x60]
        mov [esi+0x9c], edx
        mov byte ptr [esi+0x1ac], 0x1a
        mov byte ptr [esi+0x65], 0
        lea edx, [esi+0xac]
        mov eax, [ebp-0x1c]
        mov eax, [eax+0x4c]
        call %(cmptable)#x
        mov eax, [ebp-0x1c]
        call %(getplayer)#x
        mov [esi+0x6c], al
        mov dword ptr [esi+0x98], 0xc8
        mov eax, [ebx+%(gmap)#x]
        mov eax, [eax+0xfc]
        mov [ebp-0x44], eax
        mov edx, esi
        mov ecx, [ebp-4]
        add ecx, %(ep_act)#x
        call ecx
        test al, al
        jz ms_no
        mov eax, [ebp-0x44]
        mov ecx, [esi+0x9c]
        mov [eax+0x1e0], ecx
        mov cl, [esi+0x1ac]
        mov [eax+0x1e4], cl
        mov al, 1
        ret
    ms_no:
        xor eax, eax
        ret

    warp:
        mov dl, 1
        mov eax, [ebx+%(xylcls)#x]
        call %(xylcreate)#x
        mov [ebp-0x54], eax
        mov esi, eax
        mov edx, [ebp-0x50]
        shl edx, 8
        or edx, [ebp-0x4c]
        mov eax, esi
        call %(xyladd)#x
        mov edx, [ebp-0x2c]
        shl edx, 8
        or edx, [ebp-0x28]
        mov eax, esi
        call %(xyladd)#x
        mov edx, esi
        mov eax, [ebp-0x1c]
        call %(createmovete)#x
        test eax, eax
        jz w_fp
        push eax
        call %(validate)#x
        test al, al
        pop eax
        jz w_ft
        push eax
        mov dword ptr [eax+0x18], 1
        call %(execdefmove)#x
        pop eax
    w_ft:
        call %(objfree)#x
    w_fp:
        mov eax, [ebp-0x54]
        call %(objfree)#x
        ret

    side:
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov ecx, 1
        test eax, eax
        jz s_st
        mov edx, [eax+0x60]
        test edx, edx
        jz s_st
        cmp [edx+0x1c], eax
        jne s_st
        mov eax, edx
        mov edx, [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        mov ecx, 1
        cmp eax, %(xmid)d
        jl s_st
        mov ecx, 2
    s_st:
        mov eax, [ebp-0x20]
        mov [ebx+%(side)#x], eax
        mov [ebx+%(side)#x+4], ecx
        ret

    vis:
        push ebp
        mov ebp, esp
        sub esp, 0x70
        mov eax, [esi+0x10]
        mov [ebp-4], eax
        mov ecx, 1
        cmp [ebx+%(side)#x], esi
        jne v_dir
        mov ecx, [ebx+%(side)#x+4]
    v_dir:
        mov [ebp-0x64], ecx
        cmp eax, %(shk0)d
        jl v_noshake
        cmp eax, %(shk1)d
        jg v_noshake
        mov dword ptr [ebp-8], 2
        cmp eax, %(surge0)d
        jl v_amp
        cmp eax, %(surge1)d
        jge v_amp
        mov dword ptr [ebp-8], 4
    v_amp:
        cmp eax, %(shk1)d
        jne v_rand
        xor ecx, ecx
        mov [ebp-0xc], ecx
        mov [ebp-0x10], ecx
        jmp v_set
    v_rand:
        shr eax, 1
        xor eax, 0x5f17
        call hash
        mov ecx, eax
        and ecx, 3
        movsx ecx, byte ptr [ebx+ecx+sxtab]
        imul ecx, [ebp-8]
        mov [ebp-0xc], ecx
        shr eax, 2
        and eax, 3
        movsx eax, byte ptr [ebx+eax+sytab]
        add eax, eax
        mov [ebp-0x10], eax
    v_set:
        mov eax, [esi+0x1c]
        test eax, eax
        jz v_noshake
        call %(xyzcount)#x
        test eax, eax
        jz v_noshake
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(xyzget)#x
        mov edx, [eax+4]
        add edx, [ebp-0xc]
        mov ecx, [eax+8]
        add ecx, [ebp-0x10]
        mov eax, [ebx+%(gmap)#x]
        push dword ptr [eax+0x88]
        mov edi, [eax]
        call dword ptr [edi+0xc0]
    v_noshake:
        mov eax, [ebp-4]
        cmp eax, %(p0)d
        jl v_done
        cmp eax, %(p1)d
        jge v_done
        mov eax, [ebx+%(gmap)#x]
        mov ecx, [eax+0x80]
        mov [ebp-0x14], ecx
        mov ecx, [eax+0x84]
        mov [ebp-0x18], ecx
        mov ecx, [eax+0x8c]
        mov [ebp-0x1c], ecx
        mov ecx, [eax+0x90]
        mov [ebp-0x20], ecx
        mov dword ptr [ebp-0x68], 0x7fffffff
        mov eax, [ebp-4]
        cmp eax, %(f1)d
        jge v_full
        sub eax, %(f0)d
        mov ecx, [ebp-0x1c]
        add ecx, 480
        imul eax, ecx
        mov ecx, %(fspan)d
        xor edx, edx
        div ecx
        mov [ebp-0x68], eax
        mov dword ptr [ebp-0x24], 0
    v_fr:
        mov eax, [ebp-0x24]
        cmp eax, %(nfront)d
        jge v_full
        mov eax, [ebp-4]
        imul eax, eax, 613
        mov ecx, [ebp-0x24]
        imul ecx, ecx, 4099
        add eax, ecx
        add eax, 0x3c51
        call hash
        mov [ebp-0x28], eax
        and eax, 63
        mov ecx, [ebp-0x14]
        sub ecx, 240
        add ecx, [ebp-0x68]
        sub ecx, eax
        mov [ebp-0x2c], ecx
        mov eax, [ebp-0x28]
        shr eax, 11
        mov ecx, [ebp-0x20]
        add ecx, 40
        xor edx, edx
        div ecx
        mov eax, [ebp-0x18]
        sub eax, 30
        add eax, edx
        mov [ebp-0x30], eax
        mov eax, [ebp-0x28]
        call hash
        mov [ebp-0x34], eax
        or dword ptr [ebp-0x38], -1
        call spawn
        inc dword ptr [ebp-0x24]
        jmp v_fr
    v_full:
        mov dword ptr [ebp-0x24], 0
    v_sp:
        mov eax, [ebp-0x24]
        cmp eax, %(nspray)d
        jge v_band
        mov eax, [ebp-4]
        imul eax, eax, 131
        mov ecx, [ebp-0x24]
        imul ecx, ecx, 7919
        add eax, ecx
        add eax, 0x1f10
        call hash
        mov [ebp-0x28], eax
        mov ecx, [ebp-0x1c]
        add ecx, 160
        cmp ecx, [ebp-0x68]
        jle v_spw
        mov ecx, [ebp-0x68]
    v_spw:
        test ecx, ecx
        jle v_spn
        xor edx, edx
        div ecx
        mov eax, [ebp-0x14]
        sub eax, 240
        add eax, edx
        mov [ebp-0x2c], eax
        mov eax, [ebp-0x28]
        shr eax, 11
        mov ecx, [ebp-0x20]
        add ecx, 40
        xor edx, edx
        div ecx
        mov eax, [ebp-0x18]
        sub eax, 30
        add eax, edx
        mov [ebp-0x30], eax
        mov eax, [ebp-0x28]
        call hash
        mov [ebp-0x34], eax
        or dword ptr [ebp-0x38], -1
        call spawn
    v_spn:
        inc dword ptr [ebp-0x24]
        jmp v_sp
    v_band:
        mov eax, [ebp-4]
        and eax, %(bandmask)d
        jnz v_done
        mov eax, [ebp-4]
        imul eax, eax, 977
        add eax, 0xb4
        call hash
        mov [ebp-0x28], eax
        mov ecx, [ebp-0x1c]
        add ecx, 100
        mov edx, [ebp-0x68]
        sub edx, 40
        cmp ecx, edx
        jle v_bw
        mov ecx, edx
    v_bw:
        test ecx, ecx
        jle v_done
        xor edx, edx
        div ecx
        mov eax, [ebp-0x14]
        sub eax, 200
        add eax, edx
        mov [ebp-0x3c], eax
        mov eax, [ebp-0x28]
        shr eax, 11
        mov ecx, [ebp-0x20]
        add ecx, 80
        xor edx, edx
        div ecx
        mov eax, [ebp-0x18]
        sub eax, 40
        add eax, edx
        mov [ebp-0x40], eax
        mov eax, [ebp-0x28]
        call hash
        mov [ebp-0x34], eax
        mov eax, [ebp-0x28]
        shr eax, 20
        and eax, 63
        mov [ebp-0x44], eax
        mov dword ptr [ebp-0x24], 0
    v_bm:
        mov eax, [ebp-0x24]
        cmp eax, %(bandn)d
        jge v_done
        sub eax, %(bandhalf)d
        imul eax, eax
        imul eax, eax, %(curv8)d
        sar eax, 3
        mov ecx, [ebp-0x3c]
        sub ecx, eax
        mov [ebp-0x2c], ecx
        mov eax, [ebp-0x24]
        imul eax, eax, %(banddy)d
        add eax, [ebp-0x40]
        mov [ebp-0x30], eax
        mov eax, [ebp-0x24]
        add eax, eax
        add eax, [ebp-0x44]
        and eax, 63
        mov [ebp-0x38], eax
        call spawn
        inc dword ptr [ebp-0x24]
        jmp v_bm
    v_done:
        mov esp, ebp
        pop ebp
        ret

    spawn:
        cmp dword ptr [ebp-0x64], 2
        jne sp_m
        mov eax, [ebp-0x14]
        add eax, eax
        add eax, [ebp-0x1c]
        sub eax, [ebp-0x2c]
        mov [ebp-0x2c], eax
    sp_m:
        cmp dword ptr [ebp-0x2c], 0
        jge sp_x
        mov dword ptr [ebp-0x2c], 0
    sp_x:
        cmp dword ptr [ebp-0x30], 0
        jge sp_y
        mov dword ptr [ebp-0x30], 0
    sp_y:
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x1f
        call %(addfx)#x
        mov edi, eax
        mov dword ptr [edi+0x14], 0x34
        mov dword ptr [edi+0x18], %(spell)d
        mov dword ptr [edi+0x2c], 0
        mov dword ptr [edi+0x24], 0
        mov eax, [ebp-0x34]
        and eax, 15
        add eax, %(lmin)d
        mov [ebp-0x48], eax
        mov eax, [ebp-0x34]
        shr eax, 4
        and eax, 3
        add eax, %(u0)d
        mov [ebp-0x4c], eax
        mov eax, [ebp-0x34]
        shr eax, 6
        and eax, 7
        add eax, %(r0)d
        mov [ebp-0x50], eax
        mov eax, [ebp-0x38]
        test eax, eax
        jns sp_th
        mov eax, [ebp-0x34]
        shr eax, 9
        and eax, 63
    sp_th:
        mov [ebp-0x54], eax
        mov dword ptr [ebp-0x58], 0
    sp_pt:
        mov eax, [ebp-0x58]
        cmp eax, [ebp-0x48]
        jge sp_ret
        imul eax, eax, %(w)d
        add eax, [ebp-0x54]
        and eax, 63
        mov [ebp-0x5c], eax
        movsx ecx, byte ptr [ebx+eax+costab]
        imul ecx, [ebp-0x50]
        sar ecx, 7
        mov eax, [ebp-0x58]
        imul eax, [ebp-0x4c]
        add eax, ecx
        cmp dword ptr [ebp-0x64], 2
        jne sp_nx
        neg eax
    sp_nx:
        add eax, [ebp-0x2c]
        mov [ebp-0x60], eax
        mov eax, [ebp-0x5c]
        movsx ecx, byte ptr [ebx+eax+sintab]
        imul ecx, [ebp-0x50]
        sar ecx, 8
        mov eax, [ebp-0x58]
        shr eax, 2
        add eax, ecx
        add eax, [ebp-0x30]
        mov edx, eax
        mov eax, [ebp-0x60]
        call addpt
        inc dword ptr [ebp-0x58]
        jmp sp_pt
    sp_ret:
        ret

    addpt:
        push eax
        push edx
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(tobjcreate)#x
        pop edx
        mov [eax+8], edx
        pop edx
        mov [eax+4], edx
        mov edx, eax
        mov eax, [edi+0x1c]
        call %(xyzadd)#x
        ret

    hash:
        imul eax, eax, 0x9e3779b1
        mov edx, eax
        shr edx, 15
        xor eax, edx
        imul eax, eax, 0x85ebca6b
        mov edx, eax
        shr edx, 13
        xor eax, edx
        ret

    sxtab:
        .byte 0xff, 0, 1, 0xff
    sytab:
        .byte 0, 0xff, 0, 1
    sintab:
        .byte %(sintab)s
    costab:
        .byte %(costab)s
    """ % a


def build():
    s = re.sub(r"/\*.*?\*/", "", src(), flags=re.S)
    code = asm_pic(s, CODE)
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    where = {}
    for lab in ("tek", "nf", "snd", "flood", "vis", "spawn", "field_at", "mk_settings", "warp", "hash"):
        probe = s.replace("    %s:" % lab, "    %s:\n        .byte 0xcc, 0xcd, 0xce, 0xcf" % lab, 1)
        pc = asm_pic(probe, CODE)
        where[lab] = CODE + pc.find(b"\xcc\xcd\xce\xcf")
    assert where["tek"] == CODE, where
    return code, where


def site_state(d, site, orig):
    b = bytes(d[site - V2F:site - V2F + len(orig)])
    if b == orig: return "vanilla"
    if b[0] == 0xE9:
        t = site + 5 + struct.unpack_from("<i", b, 1)[0]
        if ZONE <= t < ZONE_END: return "ours"
    return "OTHER"


def zone_hdr(origs):
    h = bytearray(MAGIC + struct.pack("<I", VERSION))
    for _, _, o, _ in SITES: pass
    h += b"".join(origs)
    h += bytes(0x30 - len(h))
    return bytes(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    path = a.dll
    d = bytearray(open(path, "rb").read())
    R = relocs(bytes(d), BASE)
    bad = [hex(r) for r in R if ZONE - 3 <= r < ZONE_END] + \
          [hex(r) for _, s_, o, _ in SITES for r in R if s_ - 3 <= r < s_ + len(o)]
    if bad: print("ABORT: relocs in zone / sites", bad); return 1
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    st = {n: site_state(d, s_, o) for n, s_, o, _ in SITES}
    if zl[:4] == MAGIC: zstate = "ours (v%d)" % struct.unpack_from("<I", zl, 4)[0]
    elif any(zl): print("ABORT: zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    else: zstate = "zero"
    code, where = build()
    hdr = zone_hdr([o for _, _, o, _ in SITES])
    blob = hdr + code
    assert len(blob) <= ZONE_END - ZONE, "zone overflow %d" % len(blob)
    print("AoWTCPCK zone %s (%d B of %d) | sites %s | relocs none" % (zstate, len(blob), ZONE_END - ZONE, st))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(code, CODE):
            print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if zstate == "zero": print("already vanilla"); return 0
        if any(v == "OTHER" for v in st.values()):
            print("ABORT: a site no longer jumps into our zone (revert the later patch first)"); return 1
        zver = struct.unpack_from("<I", zl, 4)[0]
        stored = [zl[8:8 + 9], zl[0x11:0x11 + 6], zl[0x17:0x17 + 10] if zver >= 4 else None]
        for (n, s_, o, _), orig in zip(SITES, stored):
            if orig is None:                                   # site added after the installed version: must be vanilla
                assert st[n] == "vanilla", "%s hooked but not recorded by v%d" % (n, zver); continue
            assert orig == o, "stored original bytes of %s differ" % n
            d[s_ - V2F:s_ - V2F + len(o)] = orig
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        with open(path, "r+b") as f: f.write(bytes(d))
        print("reverted (sites restored, zone zeroed)"); return 0
    if any(v == "OTHER" for v in st.values()):
        print("ABORT: a site is taken by another patch:", st); return 1
    nd = bytearray(d)
    nd[ZONE - V2F:ZONE - V2F + len(blob)] = blob
    nd[ZONE - V2F + len(blob):ZONE_END - V2F] = bytes(ZONE_END - ZONE - len(blob))
    for n, s_, o, lab in SITES:
        rel = where[lab] - (s_ + 5)
        nd[s_ - V2F:s_ - V2F + len(o)] = b"\xE9" + struct.pack("<i", rel) + b"\x90" * (len(o) - 5)
    if nd == d: print("already applied (v%d)" % VERSION); return 0
    print("%d bytes change" % sum(1 for x, y in zip(nd, d) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if path == DLL:
        b = bak_path(path, ".bak_flashflood" if zstate == "zero" else ".bak_flashflood%d" % VERSION)
        if not os.path.exists(b): shutil.copy2(path, b); print("backup ->", b)
    with open(path, "r+b") as f: f.write(bytes(nd))
    chk = open(path, "rb").read()
    assert chk == bytes(nd)
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
