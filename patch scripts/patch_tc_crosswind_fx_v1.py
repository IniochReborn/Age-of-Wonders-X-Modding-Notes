#!/usr/bin/env python3
r"""
CROSSWIND (213) VISUALS.  AoWTCPCK.dll only.

v1 (2026-10-16): (1) the per-unit enchantment animation played above the CASTER's units - it must play on the ENEMY
units; (2) a battlefield-wide wash (a static grid of kind-0x26 drivers: re-rendered clouds + motes).
v2 (2026-10-16, user: the wash is "absolutely awful" - the clouds EXACTLY like Air Mastery and particles IDENTICAL to
Winds of Fury, going across the field like World Healer but in a different pattern): the v1 grid wash is gone; a
per-tick spawner now replays Air Mastery's own map-wide cloud draw and streams Winds of Fury's own particles.

RE: 213 is a THighPrayer clone (class 0x25).  Its cast effect = TfxHS kind 0x25 (NewFrame case @0x42DC19 - already a
`jmp 0x43C480` into patch_tc_bloodbath_aura_v1's tick dispatcher; 100 ticks, jump table 0x42DC9A): ticks 0,5,..95 ->
case @0x42DCA6 walks the combat object list and spawns a rising kind-0x1F sparkle (slot 0) on every object whose side
byte [obj+0x45] EQUALS the caster's (`cmp al,[edx+0x45] / jne skip` @0x42DD41); tick 100 -> PROC0002 @0x42DE3D does
the same walk (`cmp al,[edx+0x45] / jne` @0x42DED8) and spawns the kind-0x26 'aura' (slot 1) per unit.
  AIR MASTERY (strategic, AoWEPACK): TAirMastery.ExecuteTE starts an animation object whose draw callback 0x557F050C
  runs 90 ticks; EVERY tick it draws N = 5 / 20 / 10 (detail setting [[0x558E945C]+0x6D] = 0 / 1 / other) of the
  spell's gfx slots 0..2 (pfs 70: MAGIC.ILB 160 / 161 / 162 'Cloud01-03', 201x118, drawMode 770 blend 30, xs/ys
  -100/-53, -95/-53, -97/-56) at x = Random(screenW) + 2d, y = Random(screenH) - d, d = (tick - 45) * (Random(15) + 5),
  slot = Random(3) - fresh random positions every tick, so the clouds flicker while the whole field streaks up-right.
  WINDS OF FURY (combat): kind 0x2F; its particles are kind-0x1F effects spawned @0x42BFE8 with the parent's
  [fx+0x14]/[fx+0x18] (spell 0x7E) on a swirl path (0x402E0C) - a kind-0x1F draws GetSeq(slot 0 of [fx+0x18]) =
  pfs 136 slot 0 = PARTICLE.ILB [18,19,20,19] (19x19 glow orbs, 770/50, -9/-10), frame = frames[fx_ptr mod 3], through
  GFXE's Intensity table at L = 100 - 100*tick/pathLen (fading along its path).  A kind-0x1F with [fx+0x18] = 0x7E
  therefore IS a Winds of Fury particle.
  WORLD HEALER (327) = Air Mastery's draw with its own sprites (the per-tick random scatter).

Fix (1): both side tests inverted for spell 213 ([fx+0x18]; fx = [ebp-8]) -> sparkles + aura on every ENEMY unit.
Fix (2) v2: hook TK @0x42DC19 (chained in front of whatever `jmp` is there; prev kept in the zone header): for a 213
  kind-0x25 fx, on every tick 0..CLOUD_TICKS-1:
  * CLOUDS - Air Mastery's draw replayed in combat world pixels: N_CLOUDS kind-0x26 drivers per tick, each at
    x = R(W + 2*CX_PAD) - CX_PAD + 2d, y = R(H + 2*CY_PAD) - CY_PAD - d, d = (tick - 45) * (R(15) + 5), marker
    R(3) + 2 -> 213's gfx slot 2/3/4 = MAGIC.ILB 160/161/162 at Air Mastery's own xs/ys and draw mode, one frame,
    f18 = 2 (GetTotalSequenceFrames = frames * (f18+1) = 3 ticks, then the driver expires - the flicker).
  * PARTICLES - every WAVE_EVERY ticks up to WAVE_LAST: one wave of N_WAVE Winds of Fury particles (kind 0x1F,
    [fx+0x14] 0x34, [fx+0x18] 0x7E) on MakeLinePath (0x402E04) from just left of the field to just right of it: wave
    particle j starts in band j of the field's height (+ jitter + a 3-step phase per wave), drifts DOWN by ~30 %% of
    the height as it crosses (a diagonal sweep - streams, not World Healer's flicker-scatter), speed 9..13 px/tick.
  W/H = HXtoHP(cols-1, rows-1) of combat map level 0, measured at tick 0.  Randomness = an own LCG in BSS (seeded
  from the fx pointer at tick 0) - never the game's synced RNG; purely visual, nothing gameplay-relevant.
Slot picks (unchanged from v1): kind-0x26 NewFrame 0x42A5E9 / TfxHS.Show 0x430059 call-chains: 213 with marker 2..4
  -> slot = marker; anything else -> previous.
Hooks: S1 0x42DD41 / S2 0x42DED8 (9 B -> jmp cave + 4 nop, vanilla only); NF / SHOW call-hooks and TK jmp-hook chained
  in front of whatever is there (previous targets decoded at apply, kept in the zone header).
Zone 0x443C00..0x444000 (zero, reloc-free; PIC via call/pop).  BSS slack 0x46C6E0..0x46C6F0 (LATCH (v1, unused now),
  LCG, W, H).  Backup <game>\backup\AoWTCPCK.dll.bak_xwindfx.  A live v1 build is detected and upgraded in place.
v3 (2026-10-16, user: the Air Mastery clouds are nowhere near as smooth as Air Mastery - janky; move them the SAME
direction as the particles, clouds and particles at the same time; and no 'bubble' animations over the targeted units -
a very subtle swirl of Suspend-like motes round each enemy instead, gone when the spell's gfx is over):
  * CLOUDS are no longer 3-tick flicker drivers: at every particle wave tick (0, 4, .. 64) N_CW kind-0x26 cloud drivers
    spawn scattered over the field and DRIFT left->right with the particles (the NF cave moves each one every tick:
    x += CLOUD_DX, y += the particles' down-slope KDY (8.8 fixed, from the field size)); each plays a 30-frame x 3-tick
    sequence of Air Mastery's own cloud image at intensity 6 -> 30 -> 6 (fade in, hold, fade out = 90 ticks; 213 slots
    2/3/4 = MAGIC.ILB 160/161/162 copies at 5 blend levels, DualDF 3300-3314).  Same window as the particles.
  * S1 (the per-unit sparkle walk, ticks 0,5,..95): for 213 NO kind-0x1F sparkles any more; at tick 0 every ENEMY gets
    ONE kind-0x26 driver (marker 5 -> slot 5 = DualDF 3320-3383: five small white motes circling the unit, fading in,
    one turn, fading out, ~144 ticks) at its hex centre.  S2 (the tick-100 aura walk): 213 -> skipped entirely.
  RE: a kind-0x26 driver lives GetTotalSequenceFrames = frames * (seq byte +0x18 + 1) ticks (kind 4), frame =
  frames[tick / (+0x18 + 1)] - so the pipeline's f18 = ticks per frame - 1; its position is re-read from the TXYZ
  list every frame, so moving [xyz+4]/[xyz+8] in NewFrame moves it.
  Code that no longer fits zone 1 lives in zone 2 0x445800..0x445C00 (verified zero, reloc-free).  BSS 0x46C6E0 (the
  unused v1 latch) = KDY.  A live v2 (or v1) build is detected and upgraded in place; --revert zeroes both zones.
v4 (2026-10-16, user: the Crosswind DEBUFF no longer lands; not enough clouds; particles sooner and for the full
duration; the enemy swirl looks like it skips frames):
  * ROOT CAUSE of the missing debuff: the High Prayer CAs (whose Execute = the AoWEPACK `hx` cave that grants 0xC2) are
    NOT created by the cast itself - TCAbRangedTE.Execute scans the map effect list and, for every FINISHED effect of
    its spell with [fx+0x2C] set, creates GetSpell(id).CreateCA(caster, [fx+0x2C]) and executes it (the generic
    landing @0x40C31F..0x40C39B).  For High Prayer those effects are the tick-100 kind-0x26 AURAS (PROC0002 stores the
    unit object in [fx+0x2C] @0x42DFC4).  v3's S2 skipped the aura walk for 213 -> no aura -> no CA -> no 0xC2.
    Fix: the per-enemy swirl drivers spawned in S1 at tick 0 now carry the enemy's combat OBJECT in [fx+0x2C]
    (spawn26 returns the fx); when a swirl ends, the TE creates the CA for it -> `hx` grants 0xC2 to every living
    enemy (idempotent).  The grant lands as the swirls finish (~120 ticks after the cast).
  * WASH: N_CW 3 clouds per wave (v3 2) and N_CW x FIRST_CLOUDS at tick 0; particle waves every 4 ticks from tick 0
    to 96 (the whole kind-0x25 life; v3 stopped at 64); waves before tick EARLY_TICKS start at a random x across the
    first 70 %% of the field instead of off the left edge, so particles are on screen at once.
  * SWIRL art: see _crosswind5_integration.txt (60 frames x 2 ticks, envelope baked in - no dim/bright copy switch).
  A live v3 (or older) build is detected and upgraded in place (header 'XXW4').
v5 (2026-10-16, user: WAY more particles, WAY faster; particles AND clouds move in their current direction for HALF the
animation, then REVERSE for the rest - a smooth change (slow stop, slow acceleration the other way, then full speed)):
  * One shared displacement profile PHI(t) (unit speed: +1 until A = M - HW, a half-cosine velocity ease through zero at
    M, -1 from B = M + HW on; PHI is continuous and C1) baked into two int16 tables in zone 3: DP[t] = VP * PHI(t)
    (particles) and DC[t] = VC * PHI(t) (clouds), t = 0 .. TMAX-1, indexed by the GLOBAL cast tick (the kind-0x25 tick,
    published every tick in BSS GT 0x46C6F0; after the kind-0x25 ends GT stays at its last value, where the velocity is
    already the constant -V, so late clouds keep going left at full speed).  y follows x on the field's diagonal slope:
    y(t) = (D[t] * KDY) >> 11.
  * PARTICLES (pwave, zone 3): every PEVERY ticks up to PLAST, NP genuine Winds of Fury particles (kind 0x1F, spell
    0x7E) whose paths are written point by point (one TXYZ per tick, PN points) as x = x0 + DP[s+k] - DP[s] (and the
    matching y) for spawn tick s - so every particle shares the field-wide reversal (one spawned near the turn slows,
    stops and comes back).  x0/y0 are chosen so the path's MIDPOINT lands uniformly over the field.  (v4's MakeLinePath
    wave is retired.)
  * CLOUDS: spawned every CEVERY ticks up to CLAST (N_CW each, N_CW x FIRST_CLOUDS at tick 0); the NF cave moves each
    one per tick by DC[g+1] - DC[g] (g = GT, clamped) and the matching y step - clouds and particles reverse together.
  Zone 3 0x446000..0x446400 (verified zero, reloc-free, unclaimed: Gust's zone 5 ends at 0x446000).  Header 'XXW5'.
  A live v4 (or older) build is detected and upgraded in place; --revert zeroes all three zones.
v6 (2026-10-16, user: FADE IN smoother - the relatively sudden appearance is jarring; MORE particles but SMALLER; keep the
movement; FADE OUT smoother):
  * Ramps instead of bursts: per-wave particle COUNT from the table NTAB[s] (NMIN at tick 0 growing to NPF over the first
    RIN_P ticks, full, then shrinking back to NMIN over the last ROUT_P ticks before PLAST) and per-wave cloud count from
    CTAB[s] (1 at tick 0 growing to N_CW, then back to 1 - no burst of 9 clouds at tick 0); the clouds' own sequences
    (213 slots 2-4) fade in / out over 8 frames (24 ticks) each instead of 4.
  * Each particle also FADES IN: hook LF @0x42F68F (TfxHS particle draw 0x42F618, where the Intensity level L is
    stored: `mov [ebp-8],ecx / cmp dword [ebp-8],0`, 7 B, vanilla, reloc-free -> call cave + 2 nop): for a spell-213
    fx, L = min(L, tick * LIN) (full after ~100/LIN ticks); the replayed cmp's flags survive the ret into the vanilla jge.
  * Particles are tagged with spell 213 (was Winds of Fury's 0x7E), so a kind-0x1F draws 213's slot 0 = SMALL copies of
    Winds of Fury's own PARTICLE.ILB 18-20 orbs (0.6x, DualDF 3600-3602, `xwind_dust()` in _crosswind7_integration.txt;
    same Intensity-table look - kind 0x1F ignores the image's blend).  213 + kind 0x1F hits no other hook (the 0x43C860
    Shadow test is for 0x82/0x162/0x6A; Gust's SLT only remaps 212).  NPF 24 per wave (v5 14).
  Zone 4 0x446400..0x446800 (verified zero, reloc-free, unclaimed) holds the LF cave + the two ramp tables.  Header 'XXW6'.
  A live v5 (or older) build is detected and upgraded in place; --revert restores LF and zeroes all four zones.
v7 (2026-10-16, user: a bit more clouds; the SECOND HALF should last a bit longer and accelerate to a HIGHER speed; a
smoother fade-out):
  * The kind-0x25 used to end itself at tick 100 (PROC0002 -> 0x43C4D4 sets [fx+0x10] = -1 -> 0x42E3A3 sets done).  For
    213 the TK cave now keeps it alive past 100: ticks 100..TEND-1 go straight to the no-op default 0x42E3A3 (the generic
    NewFrame prologue 0x429ED5 keeps incrementing [fx+0x10]); at TEND it sets [fx+0x10] = -1 and leaves through 0x42DFDD
    ([fx+0x2C] := 0, done) - the vanilla ending.  (213 never spawns the tick-100 aura anyway - S2.)  GT is now published
    on EVERY tick (clamped to TMAX-1) so the clouds keep following the profile to the end.
  * Profile: after the reversal (B = M + HW) the backward speed keeps ACCELERATING (smoothstep) from 1x to K_REV x over
    B..C_ACC, then holds.  DP/DC tables (TMAX entries each) moved to zone 5 0x447000..0x447400 (verified zero,
    reloc-free, unclaimed - Suspend's fade-in zone ends at 0x447000); zone 3 now holds only the particle writer.
  * More clouds (N_CW 4, spawned up to CLAST 100 = through the second half); particle waves up to PLAST 132; longer
    ramp-downs (particles ROUT_P 50, clouds 40 ticks).  Header 'XXW7'.  A live v6 (or older) is upgraded in place.
v8 (2026-10-17, user: after the animation looks over there is a DELAY before I can move): the combat step only ends
when the map's WHOLE effect list is empty (TCAbRangedTE.Execute @0x40CB1D: [[0x469420]+0x11C]+8 != 0 -> 0x40CB69 'still
running').  v7 kept effects alive long after they were visible: the kind-0x25 parent to TEND 192, and every cloud for its
full 108-tick sequence (last spawn at tick 100 -> 208) although at 16..27 px/tick a cloud leaves the field within ~30-70
ticks.  Before: step done ~tick 208 vs last visible cloud ~140-170 (field width 900-1700 px) = 1.2-2 s of dead wait.
  * The NF cave now CULLS a cloud the moment it is off the field and moving away (x < -121 while drifting left, or
    x > EXW + 120 while drifting right; the 201-px cloud image is then fully outside): [fx+0x10] := -1 -> the vanilla
    expiry right after the hook (0x42A63B jg -> 0x42E3A3) marks it done.  Clouds still on the field finish their fade.
  * TEND 192 -> PLAST + 2 = 134: the parent only has to live to the last particle wave; GT then stays at 133 where the
    cloud speed is already the constant -VC*K_REV (C_ACC 110), so the late clouds' motion is unchanged.
  After: step done ~max(particles PLAST + PN = 168, last culled/faded cloud 141-171) = the last visible frame.  The
  look is unchanged (only invisible lifetime removed); the per-enemy swirls (CA -> 0xC2 grant at ~120) are untouched.
  Header 'XXW8'.  A live v7 (or older) is upgraded in place.
Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x443C00, 0x444000
ZONE2, ZONE2_END = 0x445800, 0x445C00
ZONE3, ZONE3_END = 0x446000, 0x446400                     # v5: displacement tables + the particle writer
ZONE4, ZONE4_END = 0x446400, 0x446800                     # v6: the particle fade-in cave + the ramp tables
ZONE5, ZONE5_END = 0x447000, 0x447400                     # v7: the DP / DC displacement tables (TMAX int16 each)
LF, LF_ORIG = 0x42F68F, bytes.fromhex("894df8837df800")   # v6: mov [ebp-8],ecx / cmp dword [ebp-8],0 (particle Intensity level)
GT = 0x46C6F0                                             # v5: BSS - the current global cast tick (kind-0x25 [fx+0x10])
SPELL, KIND, WOF = 213, 0x26, 0x7E
LCG, EXW, EXH, KDY = 0x46C6E4, 0x46C6E8, 0x46C6EC, 0x46C6E0
S1, S1_SKIP, S1_GO = 0x42DD41, 0x42DE2C, 0x42DD4A
S2, S2_SKIP, S2_GO = 0x42DED8, 0x42DFC7, 0x42DEE1
S1_ORIG, S2_ORIG = bytes.fromhex("3a42450f85e2000000"), bytes.fromhex("3a42450f85e6000000")
NF, SHOW, TK = 0x42A5E9, 0x430059, 0x42DC19
MAGIC3 = 0x33575858                                     # 'XXW3' marks a v3 build
MAGIC4 = 0x34575858                                     # 'XXW4' marks a v4 build
MAGIC5 = 0x35575858                                     # 'XXW5' marks a v5 build
MAGIC6 = 0x36575858                                     # 'XXW6' marks a v6 build
MAGIC7 = 0x37575858                                     # 'XXW7' marks a v7 build
MAGIC8 = 0x38575858                                     # 'XXW8' marks a v8 build
MAGIC2 = 0x32575858                                     # zone header dword 3 ('XXW2') marks a v2 build
MAP_G, TXYZ_IAT, MAPLIST_G = 0x46C064, 0x46EB24, 0x469420
ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, GETMAPLEVEL, HXTOHP = 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4, 0x401E64, 0x4022BC
MAKELINE = 0x402E04
# tuning
WAVE_EVERY, WAVE_LAST, N_WAVE = 4, 96, 8                  # v4: 25 waves x 8 Winds of Fury particles (ticks 0..96 = the whole kind-0x25 life)
EARLY_TICKS = 24                                          # v4: waves before this tick start ANYWHERE across the field (particles at once)
FIRST_CLOUDS = 3                                          # v4: tick 0 spawns N_CW x this clouds (the field fills at once)
N_CW, CLOUD_DX = 4, 8                                     # v4: clouds per wave (v3 2): 75 + 6 in all, ~70 alive at most; px/tick drift
SWIRL_MARKER = 5                                          # v3: the per-enemy mote swirl = 213 slot 5
# v5 motion profile (ticks; ~30 ticks/s): forward until A = M - HW, smooth reversal centred on M, backward from B = M + HW
M_REV, HW, TMAX = 68, 18, 200                             # the stop moment ~2.27 s after the cast; whole wash ~142 ticks (~4.7 s)
VP, VC = 24, 16                                           # px/tick at full speed: particles (v4 9..13), clouds (v4 8)
NP, PEVERY, PLAST, PN = 14, 2, 132, 36                     # particles per wave, every 2 ticks, waves up to tick 96, path points (life)
CEVERY, CLAST = 4, 100                                     # cloud waves every 4 ticks up to tick 52 (each cloud lives 90 ticks)
# v6 ramps
NPF, NMIN, RIN_P, ROUT_P = 36, 4, 24, 50                  # particles per wave: NMIN at tick 0 -> NPF by RIN_P; back to NMIN over the last ROUT_P ticks before PLAST
K_REV, C_ACC = 1.7, 110                                   # v7: backward speed accelerates 1x -> K_REV x over B..C_ACC
TEND = PLAST + 2                                          # v8: the kind-0x25 (and GT) lives to the last particle wave only (v7 192)
CULL_L, CULL_R = -121, 120                                # v8: a cloud is culled when x < CULL_L drifting left / x > EXW + CULL_R drifting right
CIN, COUT = 20, 40                                        # v7: cloud-count ramp in / out (ticks)
LIN = 10                                                  # particle fade-in: L <= tick * LIN (full after ~10 ticks)


def ntab():
    out = bytearray(PLAST + 1)
    for s_ in range(PLAST + 1):
        f = min(1.0, s_ / float(RIN_P), (PLAST - s_) / float(ROUT_P))
        out[s_] = int(round(NMIN + (NPF - NMIN) * max(0.0, f) ** 1.3))
    return bytes(out)


def ctab():
    out = bytearray(CLAST + 1)
    for s_ in range(0, CLAST + 1, CEVERY):
        f = min(1.0, (s_ + CEVERY) / float(CIN), (CLAST - s_ + CEVERY) / float(COUT))
        out[s_] = max(1, int(round(N_CW * f)))
    return bytes(out)


def phi(t):
    import math
    a, b = M_REV - HW, M_REV + HW
    if t <= a: return float(t)
    if t < b: return a + (2.0 * HW / math.pi) * math.sin(math.pi * (t - a) / (2.0 * HW))
    p, x = float(a), float(b)                             # v7: from B the backward speed accelerates to K_REV (smoothstep)
    while x < t:
        dt = min(1.0, t - x); u = min(1.0, max(0.0, (x + dt / 2 - b) / float(C_ACC - b)))
        p -= dt * (1.0 + (K_REV - 1.0) * u * u * (3 - 2 * u)); x += dt
    return p


def dtable(v): return b"".join(struct.pack("<h", int(round(v * phi(t)))) for t in range(TMAX))


def build(prev_nf, prev_show, prev_tk):
    out = bytearray(struct.pack("<IIII", prev_nf, prev_show, prev_tk, MAGIC8)); out2 = bytearray(); out3 = bytearray(); out4 = bytearray(); out5 = bytearray(); where = {}
    where["NTAB"] = ZONE4; out4 += ntab()
    while len(out4) % 4: out4.append(0)
    where["CTAB"] = ZONE4 + len(out4); out4 += ctab()
    out5 += dtable(VP); where["DP"] = ZONE5; out5 += dtable(VC); where["DC"] = ZONE5 + 2 * TMAX     # v7: tables in zone 5

    def place(name, src, z=1):
        buf, base = {1: (out, ZONE), 2: (out2, ZONE2), 3: (out3, ZONE3), 4: (out4, ZONE4)}[z]
        while len(buf) % 16: buf.append(0)
        va = base + len(buf); where[name] = va; buf.extend(asm_pic(src, va))

    # rnd: eax = n (> 0) -> eax = LCG % n.  ebx = PIC delta.  Keeps ecx / edx.
    place("rnd", """
        push edx
        push ecx
        mov ecx, eax
        mov eax, [ebx + %(lcg)#x]
        imul eax, eax, 1103515245
        add eax, 12345
        mov [ebx + %(lcg)#x], eax
        shr eax, 8
        xor edx, edx
        div ecx
        mov eax, edx
        pop ecx
        pop edx
        ret
    """ % dict(lcg=LCG))
    rnd = where["rnd"]
    # extents: [EXW]/[EXH] := HXtoHP(cols-1, rows-1) of combat map level 0 (defaults 1600 x 1000)
    place("ext", """
        push esi
        push edi
        mov dword ptr [ebx + %(exw)#x], 1600
        mov dword ptr [ebx + %(exh)#x], 1000
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov eax, [eax + 0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        je ex_done
        mov esi, [eax + 0xc]
        mov edi, [eax + 0x10]
        dec esi
        dec edi
        sub esp, 8
        lea eax, [esp + 4]
        push eax
        lea ecx, [esp + 4]
        mov eax, esi
        mov edx, edi
        call %(hxtohp)#x
        mov eax, [esp]
        add eax, 64
        cmp eax, 200
        jl ex_skip
        mov [ebx + %(exw)#x], eax
        mov eax, [esp + 4]
        add eax, 64
        cmp eax, 150
        jl ex_skip
        mov [ebx + %(exh)#x], eax
    ex_skip:
        add esp, 8
    ex_done:
        mov eax, [ebx + %(exh)#x]
        imul eax, eax, %(knum)d
        mov ecx, [ebx + %(exw)#x]
        add ecx, 260
        imul ecx, ecx, 10
        xor edx, edx
        div ecx
        mov [ebx + %(kdy)#x], eax
        pop edi
        pop esi
        ret
    """ % dict(exw=EXW, exh=EXH, maplist=MAPLIST_G, getlevel=GETMAPLEVEL, hxtohp=HXTOHP, kdy=KDY, knum=3 * 256 * CLOUD_DX))
    # spawn26: eax = x, edx = y, ecx = marker -> one kind-0x26 driver of spell 213 at world pixel (x, y)
    place("spawn26", """
        push esi
        push ecx
        push edx
        push eax
        mov eax, [ebx + %(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx + %(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi + 0x1c]
        call %(xyzadd)#x
        mov eax, [esi + 0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp]
        mov [eax + 4], edx
        mov edx, [esp + 4]
        mov [eax + 8], edx
        mov dword ptr [esi + 0x14], 0x34
        mov dword ptr [esi + 0x18], %(spell)d
        mov ecx, [esp + 8]
        mov [esi + 0x24], ecx
        mov dword ptr [esi + 0x2c], 0
        mov eax, esi
        add esp, 12
        pop esi
        ret
    """ % dict(map=MAP_G, kind=KIND, add=ADDEFFECT, txyz=TXYZ_IAT, create=TOBJCREATE, xyzadd=XYZADD, getxyz=GETXYZ,
               spell=SPELL))
    # cloud (v3): one drifting Air Mastery cloud scattered over the field (it moves in the NF cave), marker 2..4
    place("cloud", """
        mov eax, [ebx + %(exw)#x]
        add eax, 500
        call %(rnd)#x
        sub eax, 400
        push eax
        mov eax, [ebx + %(exh)#x]
        add eax, 160
        call %(rnd)#x
        sub eax, 120
        push eax
        mov eax, 3
        call %(rnd)#x
        add eax, 2
        mov ecx, eax
        pop edx
        pop eax
        call %(spawn)#x
        ret
    """ % dict(exw=EXW, exh=EXH, rnd=rnd, spawn=where["spawn26"]), 2)
    # pwave (v5): edi = global tick s -> NP Winds of Fury particles on hand-written paths following DP (the shared
    # reversal profile).  Locals: [esp] x0, [esp+4] y0, [esp+8] DP[s], [esp+12] Y[s], [esp+16] k.  ebx = PIC delta.
    place("pwave", """
        push esi
        push ebp
        sub esp, 20
        movzx esi, byte ptr [ebx + edi + %(ntab)#x]
        test esi, esi
        je pw_ret
    pw_loop:
        mov eax, [ebx + %(exw)#x]
        call %(rnd)#x
        mov [esp], eax
        movsx eax, word ptr [ebx + edi*2 + %(dph)#x]
        movsx edx, word ptr [ebx + edi*2 + %(dp)#x]
        sub eax, edx
        sub [esp], eax
        mov eax, [ebx + %(exh)#x]
        add eax, 60
        call %(rnd)#x
        sub eax, 40
        mov [esp + 4], eax
        movsx eax, word ptr [ebx + edi*2 + %(dph)#x]
        imul eax, [ebx + %(kdy)#x]
        sar eax, 11
        movsx edx, word ptr [ebx + edi*2 + %(dp)#x]
        imul edx, [ebx + %(kdy)#x]
        sar edx, 11
        sub eax, edx
        sub [esp + 4], eax
        movsx eax, word ptr [ebx + edi*2 + %(dp)#x]
        mov [esp + 8], eax
        imul eax, [ebx + %(kdy)#x]
        sar eax, 11
        mov [esp + 12], eax
        mov eax, [ebx + %(map)#x]
        mov dl, 0x1f
        call %(add)#x
        mov ebp, eax
        mov dword ptr [ebp + 0x14], 0x34
        mov dword ptr [ebp + 0x18], %(spell)d
        mov dword ptr [ebp + 0x2c], 0
        mov dword ptr [esp + 16], 0
    pw_pt:
        mov ecx, [esp + 16]
        lea eax, [edi + ecx]
        movsx eax, word ptr [ebx + eax*2 + %(dp)#x]
        mov edx, eax
        imul edx, [ebx + %(kdy)#x]
        sar edx, 11
        sub eax, [esp + 8]
        add eax, [esp]
        sub edx, [esp + 12]
        add edx, [esp + 4]
        push eax
        push edx
        mov dl, 1
        mov eax, [ebx + %(txyz)#x]
        call %(create)#x
        pop edx
        mov [eax + 8], edx
        pop edx
        mov [eax + 4], edx
        mov edx, eax
        mov eax, [ebp + 0x1c]
        call %(xyzadd)#x
        inc dword ptr [esp + 16]
        cmp dword ptr [esp + 16], %(pn)d
        jb pw_pt
        dec esi
        jnz pw_loop
    pw_ret:
        add esp, 20
        pop ebp
        pop esi
        ret
    """ % dict(ntab=where["NTAB"], exw=EXW, exh=EXH, rnd=rnd, dp=where["DP"], dph=where["DP"] + PN, kdy=KDY, map=MAP_G,
               add=ADDEFFECT, spell=SPELL, txyz=TXYZ_IAT, create=TOBJCREATE, xyzadd=XYZADD, pn=PN), 3)
    # TK: kind-0x25 NewFrame entry (in front of the previous jmp target) - 213's wash (v3: waves + drifting clouds together)
    place("tk", """
        push eax
        mov eax, [ebp - 8]
        cmp dword ptr [eax + 0x18], %(spell)d
        pop eax
        jne tk_prev
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebp - 8]
        mov edi, [esi + 0x10]
        test edi, edi
        jne tk_go
        xor eax, eax
        xor eax, 0x2d1f7a3b
        mov [ebx + %(lcg)#x], eax
        call %(ext)#x
    tk_go:
        mov eax, edi
        cmp eax, %(tlast)d
        jbe tk_gt
        mov eax, %(tlast)d
    tk_gt:
        mov [ebx + %(gt)#x], eax
        cmp edi, %(plast)d
        ja tk_cl0
        test edi, %(pmask)d
        jne tk_cl0
        call %(pwave)#x
    tk_cl0:
        cmp edi, %(clast)d
        ja tk_done
        test edi, %(cmask)d
        jne tk_done
        movzx ecx, byte ptr [ebx + edi + %(ctab)#x]
        test ecx, ecx
        je tk_done
    tk_cl:
        push ecx
        call %(cloud)#x
        pop ecx
        dec ecx
        jnz tk_cl
    tk_done:
        popad
        push eax
        mov eax, [ebp - 8]
        mov eax, [eax + 0x10]
        cmp eax, 100
        jb tk_go_prev
        cmp eax, %(tend)d
        jae tk_end
        pop eax
        jmp %(dflt)#x
    tk_end:
        mov eax, [ebp - 8]
        mov dword ptr [eax + 0x10], -1
        pop eax
        jmp %(fin)#x
    tk_go_prev:
        pop eax
    tk_prev:
        jmp %(prev)#x
    """ % dict(spell=SPELL, lcg=LCG, ext=where["ext"], ctab=where["CTAB"], cloud=where["cloud"],
               tlast=TMAX - 1, gt=GT, plast=PLAST, pmask=PEVERY - 1, clast=CLAST, cmask=CEVERY - 1,
               pwave=where["pwave"], prev=prev_tk, tend=TEND, dflt=0x42E3A3, fin=0x42DFDD))
    # S1 (v3): for 213 no sparkles; at tick 0 each living ENEMY gets one mote-swirl driver (marker 5) at its hex centre
    place("s1", """
        push ecx
        mov ecx, [ebp - 8]
        cmp dword ptr [ecx + 0x18], %(spell)d
        pop ecx
        jne s1_van
        cmp al, byte ptr [edx + 0x45]
        je %(skip)#x
        mov eax, [ebp - 8]
        cmp dword ptr [eax + 0x10], 0
        jne %(skip)#x
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(map)#x]
        mov eax, [eax + 0xe4]
        mov eax, [eax + 0xc]
        mov edx, [ebp - 0x10]
        call %(getobj)#x
        push eax
        mov esi, [eax + 0x60]
        test esi, esi
        je s1_pop
        sub esp, 8
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x78]
        movsx edi, al
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        lea edx, [esp + 4]
        push edx
        lea ecx, [esp + 4]
        mov edx, edi
        call %(hxtohp)#x
        mov eax, [esp]
        add eax, 16
        mov edx, [esp + 4]
        add edx, 16
        add esp, 8
        mov ecx, %(marker)d
        call %(spawn)#x
        pop edx
        mov [eax + 0x2c], edx
        jmp s1_done
    s1_pop:
        pop eax
    s1_done:
        popad
        jmp %(skip)#x
    s1_van:
        cmp al, byte ptr [edx + 0x45]
        jne %(skip)#x
        jmp %(go)#x
    """ % dict(spell=SPELL, skip=S1_SKIP, go=S1_GO, map=MAP_G, getobj=0x402634, hxtohp=HXTOHP, marker=SWIRL_MARKER,
               spawn=where["spawn26"]), 2)
    # S2 (v3): the tick-100 aura walk - 213 never spawns the aura
    place("s2", """
        push ecx
        mov ecx, [ebp - 8]
        cmp dword ptr [ecx + 0x18], %(spell)d
        pop ecx
        je %(skip)#x
        cmp al, byte ptr [edx + 0x45]
        jne %(skip)#x
        jmp %(go)#x
    """ % dict(spell=SPELL, skip=S2_SKIP, go=S2_GO))
    # NF (v3): 213 markers 2..5 -> slot = marker; clouds (2..4) also DRIFT one step per tick (x += DX, y += KDY slope)
    place("nf", """
        push eax
        mov eax, [ebp - 8]
        cmp dword ptr [eax + 0x18], %(spell)d
        jne nf_prev
        mov edx, [eax + 0x24]
        cmp edx, 2
        jb nf_prev
        cmp edx, %(maxm)d
        ja nf_prev
        cmp edx, 4
        ja nf_ret
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebp - 8]
        mov eax, [esi + 0x1c]
        xor edx, edx
        call %(getxyz)#x
        test eax, eax
        je nf_mv
        mov edi, eax
        mov ecx, [ebx + %(gt)#x]
        cmp ecx, %(gmax)d
        jbe nf_g
        mov ecx, %(gmax)d
    nf_g:
        movsx eax, word ptr [ebx + ecx*2 + %(dc1)#x]
        movsx edx, word ptr [ebx + ecx*2 + %(dc)#x]
        mov ecx, eax
        sub ecx, edx
        add [edi + 4], ecx
        imul eax, [ebx + %(kdy)#x]
        sar eax, 11
        imul edx, [ebx + %(kdy)#x]
        sar edx, 11
        sub eax, edx
        add [edi + 8], eax
        test ecx, ecx
        jz nf_mv
        js nf_left
        mov eax, [ebx + %(exw)#x]
        add eax, %(cr)d
        cmp dword ptr [edi + 4], eax
        jle nf_mv
        jmp nf_kill
    nf_left:
        cmp dword ptr [edi + 4], %(cl)d
        jge nf_mv
    nf_kill:
        mov dword ptr [esi + 0x10], -1
    nf_mv:
        popad
    nf_ret:
        pop eax
        ret
    nf_prev:
        pop eax
        jmp %(prev)#x
    """ % dict(spell=SPELL, prev=prev_nf, maxm=SWIRL_MARKER, getxyz=GETXYZ, kdy=KDY, gt=GT, gmax=TMAX - 2,
               dc=where["DC"], dc1=where["DC"] + 2, exw=EXW, cr=CULL_R, cl=CULL_L), 2)
    place("show", """
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(spell)d
        jne sh_prev
        mov eax, [eax + 0x24]
        cmp eax, 2
        jb sh_prev
        cmp eax, %(maxm)d
        ja sh_prev
        ret
    sh_prev:
        jmp %(prev)#x
    """ % dict(spell=SPELL, prev=prev_show, maxm=SWIRL_MARKER))
    # LF (v6): particle draw - for a spell-213 fx the Intensity level L (ecx) is capped by tick * LIN (fade-in); then the
    # replayed `mov [ebp-8],ecx / cmp dword [ebp-8],0` (its flags feed the vanilla jge after the site)
    place("lf", """
        push eax
        mov eax, [ebp + 8]
        mov eax, [eax - 4]
        cmp dword ptr [eax + 0x18], %(spell)d
        jne lf_done
        mov eax, [eax + 0x10]
        imul eax, eax, %(lin)d
        cmp ecx, eax
        jle lf_done
        mov ecx, eax
    lf_done:
        pop eax
        mov [ebp - 8], ecx
        cmp dword ptr [ebp - 8], 0
        ret
    """ % dict(spell=SPELL, lin=LIN), 4)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    assert ZONE4 + len(out4) <= ZONE4_END, hex(ZONE4 + len(out4))
    assert ZONE2 + len(out2) <= ZONE2_END, hex(ZONE2 + len(out2))
    assert ZONE3 + len(out3) <= ZONE3_END, hex(ZONE3 + len(out3))
    assert ZONE5 + len(out5) <= ZONE5_END, hex(ZONE5 + len(out5))
    assert PLAST + PN < TMAX and TEND <= TMAX
    return bytes(out), bytes(out2), bytes(out3), bytes(out4), bytes(out5), where


def jmp5(src, dst): return b"\xe9" + struct.pack("<i", dst - (src + 5))
def call5(src, dst): return b"\xe8" + struct.pack("<i", dst - (src + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); zl = bytes(d[ZONE - V2F:ZONE_END - V2F]); z2l = bytes(d[ZONE2 - V2F:ZONE2_END - V2F])
    z3l = bytes(d[ZONE3 - V2F:ZONE3_END - V2F]); z4l = bytes(d[ZONE4 - V2F:ZONE4_END - V2F]); z5l = bytes(d[ZONE5 - V2F:ZONE5_END - V2F])
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    inz = lambda t: ZONE <= t < ZONE_END or ZONE2 <= t < ZONE2_END or ZONE3 <= t < ZONE3_END or ZONE4 <= t < ZONE4_END or ZONE5 <= t < ZONE5_END   # v3/v5/v6/v7: our caves live in any zone

    def btarget(va, op):
        b = rd(va, 5); assert b[0] == op, "%#x is not a %s: %s" % (va, "call" if op == 0xE8 else "jmp", b.hex())
        return va + 5 + struct.unpack_from("<i", b, 1)[0]
    tnf, tsh, ttk = btarget(NF, 0xE8), btarget(SHOW, 0xE8), btarget(TK, 0xE9)
    hdr = struct.unpack_from("<IIII", zl, 0)
    v2 = hdr[3] in (MAGIC2, MAGIC3, MAGIC4, MAGIC5, MAGIC6, MAGIC7, MAGIC8)
    prev_nf = hdr[0] if inz(tnf) else tnf
    prev_sh = hdr[1] if inz(tsh) else tsh
    prev_tk = hdr[2] if inz(ttk) else ttk
    assert not inz(ttk) or v2, "TK points into the zone but the header is not v2"
    zone, zone2, zone3, zone4, zone5, where = build(prev_nf, prev_sh, prev_tk)
    lfb = rd(LF, 7)
    if lfb == LF_ORIG: lfst = "vanilla"
    elif lfb[0] == 0xE8 and inz(LF + 5 + struct.unpack_from("<i", lfb, 1)[0]):
        lfst = "ours" if lfb == call5(LF, where["lf"]) + bytes([0x90, 0x90]) else "ours(old)"
    else: lfst = "OTHER"
    inz2 = lambda t: ZONE2 <= t < ZONE2_END
    s1, s2 = rd(S1, 9), rd(S2, 9)

    def jstate(b, orig, cave):
        if b == orig: return "vanilla"
        if b[0] == 0xE9 and (inz(btarget_b(b, S1 if orig is S1_ORIG else S2)) or inz2(btarget_b(b, S1 if orig is S1_ORIG else S2))):
            return "ours" if b[:5] == jmp5(S1 if orig is S1_ORIG else S2, where[cave]) else "ours(old)"
        return "OTHER"

    def btarget_b(b, va): return va + 5 + struct.unpack_from("<i", b, 1)[0]
    st = {"S1": jstate(s1, S1_ORIG, "s1"), "S2": jstate(s2, S2_ORIG, "s2"),
          "NF": ("ours" if tnf == where["nf"] else "ours(old)") if (inz(tnf) or inz2(tnf)) else "chain",
          "SHOW": ("ours" if tsh == where["show"] else "ours(old)") if inz(tsh) else "chain",
          "TK": ("ours" if ttk == where["tk"] else "ours(old)") if inz(ttk) else "chain", "LF": lfst}
    anyours = any(v.startswith("ours") for v in st.values())
    z2ok = z2l[:len(zone2)] == zone2 and not any(z2l[len(zone2):])
    z3ok = z3l[:len(zone3)] == zone3 and not any(z3l[len(zone3):])
    z4ok = z4l[:len(zone4)] == zone4 and not any(z4l[len(zone4):])
    z5ok = z5l[:len(zone5)] == zone5 and not any(z5l[len(zone5):])
    if any(z2l) and not z2ok and hdr[3] not in (MAGIC3, MAGIC4, MAGIC5, MAGIC6, MAGIC7, MAGIC8): print("ABORT (zone 2 not free)"); return 1
    if any(z3l) and not z3ok and hdr[3] not in (MAGIC5, MAGIC6, MAGIC7, MAGIC8): print("ABORT (zone 3 not free)"); return 1
    if any(z4l) and not z4ok and hdr[3] not in (MAGIC6, MAGIC7, MAGIC8): print("ABORT (zone 4 not free)"); return 1
    if any(z5l) and not z5ok and hdr[3] not in (MAGIC7, MAGIC8): print("ABORT (zone 5 not free)"); return 1
    zstate = "zero" if not any(zl) and not any(z2l) and not any(z3l) and not any(z4l) and not any(z5l) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) and z2ok and z3ok and z4ok and z5ok \
        else ("v8-older" if hdr[3] == MAGIC8 else "v7" if hdr[3] == MAGIC7 else "v6" if hdr[3] == MAGIC6 else "v5" if hdr[3] == MAGIC5 else "v4" if hdr[3] == MAGIC4 else "v3" if hdr[3] == MAGIC3 else "v2" if hdr[3] == MAGIC2 else "v1")
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or ZONE2 - 3 <= r < ZONE2_END or ZONE3 - 3 <= r < ZONE3_END
           or ZONE4 - 3 <= r < ZONE4_END or ZONE5 - 3 <= r < ZONE5_END or LF - 3 <= r < LF + 7
           or any(s - 3 <= r < s + 9 for s in (S1, S2)) or any(s - 3 <= r < s + 5 for s in (NF, SHOW, TK))]
    print("AoWTCPCK crosswind fx v8: sites %s | prev nf %#x show %#x tk %#x | zone %s (%d B: %s) | relocs %s" % (
        st, prev_nf, prev_sh, prev_tk, zstate, len(zone) + len(zone2) + len(zone3) + len(zone4) + len(zone5), ", ".join("%s=%#x" % kv for kv in where.items()), bad or "none"))
    if a.dis:
        import capstone
        for blob, base in ((zone[16:], ZONE + 16), (zone2, ZONE2), (zone3, ZONE3), (zone4[where["lf"] - ZONE4:], where["lf"])):
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob, base):
                print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (relocs)"); return 1
    if "OTHER" in (st["S1"], st["S2"], st["LF"]): print("ABORT (foreign state)"); return 1
    if not anyours and zstate != "zero": print("ABORT (zone not free)"); return 1
    if zstate in ("v1", "v2", "v3", "v4", "v5", "v6", "v7"): print("%s build found -> upgrading to v8 (no dead wait after the animation: off-field clouds culled, parent ends at the last wave)" % zstate)
    n = bytearray(d)

    def wr(va, b): n[va - V2F:va - V2F + len(b)] = b
    if a.revert:
        if not anyours: print("already reverted"); return 0
        wr(S1, S1_ORIG); wr(S2, S2_ORIG); wr(NF, call5(NF, prev_nf)); wr(SHOW, call5(SHOW, prev_sh))
        wr(TK, jmp5(TK, prev_tk)); wr(ZONE, bytes(ZONE_END - ZONE)); wr(ZONE2, bytes(ZONE2_END - ZONE2)); wr(ZONE3, bytes(ZONE3_END - ZONE3))
        wr(ZONE4, bytes(ZONE4_END - ZONE4)); wr(ZONE5, bytes(ZONE5_END - ZONE5)); wr(LF, LF_ORIG)
    else:
        wr(ZONE, bytes(ZONE_END - ZONE)); wr(ZONE, zone); wr(ZONE2, bytes(ZONE2_END - ZONE2)); wr(ZONE2, zone2)
        wr(ZONE3, bytes(ZONE3_END - ZONE3)); wr(ZONE3, zone3); wr(ZONE4, bytes(ZONE4_END - ZONE4)); wr(ZONE4, zone4)
        wr(ZONE5, bytes(ZONE5_END - ZONE5)); wr(ZONE5, zone5)
        wr(LF, call5(LF, where["lf"]) + bytes([0x90, 0x90]))
        wr(S1, jmp5(S1, where["s1"]) + b"\x90" * 4); wr(S2, jmp5(S2, where["s2"]) + b"\x90" * 4)
        wr(NF, call5(NF, where["nf"])); wr(SHOW, call5(SHOW, where["show"])); wr(TK, jmp5(TK, where["tk"]))
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_xwindfx")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
