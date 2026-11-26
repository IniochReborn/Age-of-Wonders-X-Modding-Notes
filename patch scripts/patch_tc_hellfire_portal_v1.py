#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Hellfire's projectiles pour out of a hell portal hanging above the target area (2026-10-07).

The hail-class strikes (TCAbRangedTE.Execute phase 0 -> NextStrike PROC0005) start 300 px above the target hex.
The portal is a kind-0x26 combat effect (the one the High Prayer cast spawns per unit at tick 100): its NewFrame
lives frames*(delay+1) ticks and its Show draws a spell-list sequence at the effect's XYZ - both hard-code slot 1
(`mov edx,1` @0x42A5E9 in NewFrame, `mov eax,1` @0x430059 in Show - jump table CASE_PROCTABLE_0042F9DF[0x26]).
Three hooks:
  A 0x40B550 (15 B, the class-0x0A branch of phase 0 that sets the strike count 0x15; Hellfire reaches it through
    the id alias) -> cave: replay, and for spell 354 ([te+0x18]) spawn one kind-0x26 effect at (hex px+16,
    hex py+16-300) with [fx+0x14]=0x34, [fx+0x18]=354, built like PROC0002 @0x42DE3D builds its aura effects
    (HXtoHP 0x4022BC, AddEffect 0x41C6EC, TXYZ class IAT 0x46EB24, TObject.Create 0x401040, TXYZList.Add 0x402DE4,
    TXYZList.GetXYZ 0x402DF4, combat map global 0x46C064); resumes at 0x40B630.
    ⚠ [fx+0x2C] must stay NIL: the effect sits in the same list the TE's phase-1 loop walks as "strikes"
    ([map+0x11C]); a strike whose done flag [+0xC] is set and whose [+0x2C] is a unit gets GetSpell.CreateCA(caster,
    unit) applied at impact - with the caster stored there the finished portal hit the CASTER (v1 bug, 2026-10-08).
  The "nf" cave also serves BLOODBATH (350): when a sword effect's tick reaches BLOOD_TICK it leaves the engine's
  own PERMANENT ground-blood decal under the unit.  v13 (2026-10-09): the only thing in the engine that persists
  blood until the end of combat is TCCorpseHS (classref 0x4125DC, created by the unit-death routine @0x420477..
  0x42063A only): a TSingleHS on the map field whose Show (0x423970) draws general-FX-list slot [+0x24] (the GndBlood
  sprites, offset [+0x1C]/[+0x20] = rand(10)-5) and the corpse frame [+0x18] of the unit's image owner [+0x10].
  We build one exactly like the death code does but with [+0x18] = -1 (GetUnloopedFrameIndex -> -1 -> no corpse
  drawn) and [+0xC] = nil (no dead unit to raise): field = GetField(GetMapLevel([map+0x10], 0), hs.X, hs.Y)
  (skipped for terrain 0/9 = water, as vanilla), TEObject.Create(class, 1, field), [+0x10] = [hs+0x10],
  [+0x24] = blood slot from the unit's blood type (TUnit VMT+0x110) and variant (VMT+0x178 & 0x7F) with the same
  mapping as the home-PC cave 0x43803C (type 1: +0x1E cap 0x20, type 2: +0x34 cap 0x36, type 3: +0x25 cap 0x27;
  type 0 = no blood -> nothing created), then VMT+0xE0 (Activate) registers it.  No SetAction -> no hit grunt
  (v12 played the hit animation, which the user rejected); the gush itself is baked into the sword frames.
  B 0x42A5E9 / C 0x430059 -> call caves: slot = 3 when the effect's spell is 354, else 1 (NewFrame: fx = [ebp-8],
    eax must survive; Show: fx = [ebp-4]).  Slot 3 of Hellfire's gfx list = the portal sequence
    (patch_dual_sphere_spells_v1.py; 40 frames x 3 ticks = 120 ticks, the length of the rain).
PIC (rel32 thunks; data refs via the call/pop delta - the DLL is always relocated).  Caves 0x43C500..
Backup <game>\backup\AoWTCPCK.dll.bak_hfportal.  Surgical --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_hfportal"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43C500, 0x43CA00      # 0x43C480..0x43C500 = patch_tc_bloodbath_aura_v1.py; v13 grew past 0x43C800; v20 gate cave past 0x43C900 (next free 0x43CA00)
SPELL_ID, PORTAL_SLOT, KIND = 354, 3, 0x26
PORTAL_DX, PORTAL_DY = 16 - 102, 16 - 342         # trial-and-error with the user: left of the hex origin, above the drop (v17: 20 px further left; v20 2026-10-11: 12 px right + 12 px up; v22: +6/+6 more; v23: 4 px further up)
# v20 (2026-10-11): the stones WAIT for the portal to reach full size.  The driver effect's NewFrame (nf cave) publishes
# its tick counter [fx+0x10] into GATE_TICK_VA (a raw-only dword in the DATA page slack past the section's VirtualSize,
# like the hail-msg --trace ring at 0x46B7C8..0x46B814 - unreferenced, page-mapped, writable; the spawn cave zeroes it
# at the cast) and BOTH NextStrike call sites (phase 0 @0x40B6F1 = the immediate first strike, phase 1 @0x40CBE7 =
# the [te+0x30] countdown, reloaded to Random(3)+4 ticks) go through the "gate" cave: for spell 354 while the tick
# is < STRIKE_DELAY the call is skipped and [te+0x30] := 1 so the countdown retries next tick.  Other spells pass
# straight through.  The swirl reaches its full ring count at tick 49 (i = min(tick, 49)), so 50.
GATE_TICK_VA, STRIKE_DELAY = 0x46B840, 50
# v21 (2026-10-11): the loop sound starts at the cast.  Vanilla plays spell sound 0 from the CASTER's cast animation
# (TTacticalCombatUnitHS @0x421D65: action 0x34 -> GetSpell([hs+0x38]).sounds.Play(0), spells 0x70/0x7A/0x77 excluded)
# and NextStrike starts that animation with the FIRST strike (SetAction 0xC @0x40F3B6) - so with the strike delay
# there was silence until the stones.  Now the spawn cave plays sound 0 at tick 0 (if sounds are on: [map+0x129])
# and the caster site skips 354 ("castsnd" hook = 354 added to the exclusion list).  DUALDF_HFLOOP.WAV fades in
# over the delay (build_dual_sphere_sfx_v1.py FADE_IN) and carries no hard onset before it.
SPELLREG_GLOBAL, GETSPELL, SFXPLAY = 0x46E8D0, 0x4029B4, 0x4022F4    # [[0x46E8D0]]+0x84 = spell registry; TSFXLibrary.Play(eax=list, edx=idx)
BLOOD_SPELL, BLOOD_TICK = 350, 60                 # Bloodbath: at the sword-tip tick leave a permanent ground-blood decal (TCCorpseHS)
CORPSE_CLASSREF, TECREATE = 0x4125DC, 0x40137C    # TCCorpseHS classref (data, PIC via delta) / Engine.TEObject.Create(eax=class, dl=1, ecx=field)
GETMAPLEVEL, GETFIELD = 0x401E64, 0x401E54        # HSEngine.TMapContainer.GetMapLevel(eax, edx=0) / TMapLevel.GetField(eax, edx=x, ecx=y)
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4
MAP_GLOBAL, TXYZ_IAT = 0x46C064, 0x46EB24
HOOKS = [("spawn", 0x40B550, bytes.fromhex("8b45fcc7402815000000e9d1000000"), "jmp"),
         ("nf", 0x42A5E9, bytes.fromhex("ba01000000"), "call"),
         ("show", 0x430059, bytes.fromhex("b801000000"), "call"),      # TfxHS.Show jump table [0x26] = 0x430058
         # v2 (2026-10-08): the portal itself is Mind Decay's whirl = kind-0x1F sparkle effects on circular arc paths
         # drawn in the engine's "dark" mode.  D: Show[0x1F] @0x4300A1 draws dark only for spells 0x82/0x6A
         # (`cmp [fx+0x18],0x82 / je` @0x4300AE) -> also for 354.  E: SUB_0042E4C4(eax = slot) picks the sequence
         # every Show case draws -> for kind-0x1F effects of spell 354 slot 0 becomes slot 4 (the sparkle sprite
         # copied from PARTICLE 15-17 into DualDF 200-202; Hellfire's own slot 0 is the stone).  The spawner lives in
         # the "nf" cave: the driver effect's NewFrame (kind 0x26, spell 354) spawns min(tick,48)/2+3 sparkles every
         # other tick while its counter < SWIRL_TICKS, like TfxHS.NewFrame kind 0x2A @0x42C7BE does for Mind Decay
         # (AddEffect(0x1F), copy +0x14/+0x18, MakeArcPath(eax=radius 10..19, edx=phase, ecx=45 steps; pushed:
         # angle rand 360, cx, cy, dir rand 2, &fx.list)); the sparkle lives path-length ticks (NewFrame[0x1F]).
         ("dark", 0x4300AE, bytes.fromhex("81781882000000"), "jmp"),
         ("slot", 0x42E4C4, bytes.fromhex("558bec51894 5fc".replace(" ", "")), "jmp"),
         # v20: strike-delay gate on both `call NextStrike` sites (eax = the TE at both)
         ("gate", 0x40B6F1, bytes.fromhex("e89a1b0000"), "call"),
         ("gate", 0x40CBE7, bytes.fromhex("e8a4060000"), "call"),
         # v21: caster cast-animation sound site: `mov eax,[ebp-4] / cmp [eax+0x38],0x77 / je 0x421ECC` (13 B)
         ("castsnd", 0x421D91, bytes.fromhex("8b45fc837838770f842e010000"), "jmp")]
CASTSND_SKIP, CASTSND_NEXT = 0x421ECC, 0x421D9E
NEXTSTRIKE = 0x40D290
RESUME_SPAWN = 0x40B630
DARK_YES, DARK_NEXT = 0x4300C4, 0x4300B7
SLOT_RESUME = 0x42E4CB
# SWIRL_TICKS: the spawner stops here; a spark lives 44 ticks, so the whirl is gone by SWIRL_TICKS+44.  v18: 120 -> 100
# and the driver sequence (slot 3 in patch_dual_sphere_spells_v1.py) cut from 200 to 148 ticks: the combat waits for
# every effect to die, and the invisible driver outliving the 120-tick rain by 80 ticks was the "inactionable delay"
# after Hellfire (last spark dies at ~142 < 148).
SPARK_SLOT, SWIRL_TICKS = 4, 150              # v20: rain now runs ~tick 50..185 -> swirl to 150 (last spark ~194), driver 200 ticks (50 frames)
RANDINT, MAKEARC = 0x401020, 0x402E0C
# v13 (2026-10-09): a replica of Mind Decay's spawner (TfxHS.NewFrame kind 0x2A @0x42C769, ticks 0..49, even
# ticks): for i in 0..min(tick, SWIRL_IMAX): (i/25+1) sparkles each on an arc of radius rand(10)+10, phase i/2,
# 45 steps, start angle rand(360), direction rand(2), centre (x+100-i, y-250+i) = a 50 px diagonal band whose rings
# turn in lock-step = the "sideways black tornado".  Ours keeps the same band shape centred on the portal point
# (cx = X0 + SWIRL_CX - i, cy = Y0 - SWIRL_CY + i) and keeps spawning for the whole rain (SWIRL_TICKS) instead of
# stopping at tick 49.
SWIRL_IMAX, SWIRL_PER = 49, 25                # i runs 0..49 (inclusive), i/25+1 sparkles per i (1, then 2 from i=25)
# v16 (2026-10-09): the user dropped the cone - "a wide oval frisbee of the Mind Decay spinning black things, with
# only a slight cone element so it isn't too flat".  Ring centres run along a wide, nearly horizontal band:
# cx = X0 + CX0 + 5*i/4 (0..61 px), cy = Y0 + CY0 + i/4 (0..12 px, a slight tilt down-right); the ring radius grows
# only gently, r = rand(RR)+R0 + i/8 (8..13 at the left end, 14..19 at the right) = the slight cone.  Envelope ~95 x 45 px.
# v17 (2026-10-10): the user saw the v16 disc "facing bottom-left" (major axis upper-left -> lower-right puts the
# disc normal on the lower-left/upper-right diagonal).  Mirrored: the band now rises to the right (cy = Y0 + CY0 -
# i/4, left end LOW, right end HIGH) and the rings are biggest at the LOW left end (r = R0 + rand(RR) + (IMAX-i)/8),
# so the near, wide edge sits lower-left and the disc faces lower-right (toward the drop column).
# v18 (2026-10-10): v17 (rising band, fat left end) read as "facing top-right"; v16 (falling band, fat right end)
# read as "facing bottom-left".  An offline mock (scratchpad whirl_sim.py) shows the whirl as a slanted sausage:
# the user's vertical word follows the slope, the horizontal word the THIN end.  Bottom-right = falling band
# (v16 tilt, CY0 -6, "add") with the fat end at the upper LEFT (v17 radius growth kept).
# v19 (2026-10-10), the user's explicit geometry: "the narrow part of the cone top-left, the wider base bottom-right,
# protrude less, base wider - flatten it out like a frisbee".  Ring centres: cx = X0 + CX0 + i/2 + (rand(i+1) - i/2)
# (a 24 px axis plus a horizontal SPREAD that grows to +-24 px at the base), cy = Y0 + CY0 + i/4 (12 px drop),
# r = R0 + rand(RR) + i/4 (7..12 at the narrow end, 19..24 at the base) -> base envelope ~96 x 48 px (2:1 flat
# ellipse), narrow end ~24 px, axis ~27 px long down-right.
SWIRL_CX0, SWIRL_CY0 = -30, -6                # narrow (top-left) end of the band relative to the portal point
SWIRL_TILT = "add"                            # cy = Y0 + CY0 +/- i/4: "add" = falling to the right, "sub" = rising
SWIRL_R0, SWIRL_RR = 7, 6                     # ring radius rand(6)+7, plus i/4 (see the nf cave)
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def asm_delta(src, va):
    """`call $D / pop ebx / sub ebx, $D` = the PIC delta idiom; $D is resolved by a two-pass assembly: the call is
    emitted as a literal rel32 = 0 (= "call next"), the sub gets a 32-bit placeholder, the anchor is located in the
    encoding and the real address is patched in by re-assembling."""
    if "$D" not in src: return asm(src, va)
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(asm(s1, va))
    anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    n, k = 0, b.find(anchor)
    while k >= 0:                       # every anchor gets its own pop address (a cave may use several)
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1
        k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") == src.count("sub ebx, $D"), "delta anchor(s) not found"
    return bytes(b)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    place("spawn", """
        mov eax, [ebp-4]
        mov dword ptr [eax+0x28], 0x15
        cmp dword ptr [eax+0x18], %(id)d
        jne done
        push ebx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov dword ptr [ebx+%(gt)#x], 0
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        mov eax, [ebp-4]
        movzx edx, word ptr [eax+0x22]
        movzx eax, word ptr [eax+0x20]
        call %(hx)#x
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzadd)#x
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp+4]
        add edx, %(dx)d
        mov [eax+4], edx
        mov edx, [esp]
        add edx, %(dy)d
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je nosound
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        xor edx, edx
        call %(play)#x
    nosound:
        add esp, 8
        pop edi
        pop esi
        pop ebx
    done:
        jmp %(resume)#x
    """ % {"id": SPELL_ID, "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND, "add": ADDEFFECT, "txyz": TXYZ_IAT,
           "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": PORTAL_DX, "dy": PORTAL_DY, "resume": RESUME_SPAWN,
           "gt": GATE_TICK_VA, "reg": SPELLREG_GLOBAL, "getspell": GETSPELL, "play": SFXPLAY})
    # nf cave: eax = the spell's sequence list (must survive), edx = slot for GetImageSequence; for the Hellfire
    # driver also run the swirl spawner.  ebx/esi/edi saved; eax saved across the spawner.
    place("nf", """
        push eax
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %(bb)d
        jne bb_done
        cmp dword ptr [eax+0x10], %(bbtick)d
        jne bb_done
        mov eax, [eax+0x2c]
        test eax, eax
        jz bb_done
        push ebx
        push esi
        push edi
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [esi+0x60]
        test eax, eax
        jz bb_out
        mov eax, [esi+0x4c]
        mov edx, [eax]
        call dword ptr [edx+0x110]
        cmp al, 1
        jb bb_out
        mov eax, [esi+0x60]
        mov edx, [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, [esi+0x60]
        mov edx, [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        push eax
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        pop edx
        pop ecx
        call %(getfield)#x
        mov cl, [eax+0x14]
        test cl, cl
        jz bb_out
        cmp cl, 9
        je bb_out
        mov ecx, eax
        mov dl, 1
        mov eax, [ebx+%(corpse)#x]
        call %(tecreate)#x
        mov edi, eax
        mov eax, [esi+0x60]
        mov eax, [eax+0x10]
        mov [edi+0x10], eax
        mov dword ptr [edi+0x18], -1
        mov dword ptr [edi+0xc], 0
        mov eax, [esi+0x4c]
        mov edx, [eax]
        call dword ptr [edx+0x110]
        movzx eax, al
        push eax
        mov eax, [esi+0x4c]
        mov edx, [eax]
        call dword ptr [edx+0x178]
        and eax, 0x7f
        pop ecx
        cmp cl, 2
        je bb_t2
        cmp cl, 3
        je bb_t3
        add eax, 0x1e
        cmp eax, 0x20
        jle bb_slot
        mov eax, 0x20
        jmp bb_slot
    bb_t2:
        add eax, 0x34
        cmp eax, 0x36
        jle bb_slot
        mov eax, 0x36
        jmp bb_slot
    bb_t3:
        add eax, 0x25
        cmp eax, 0x27
        jle bb_slot
        mov eax, 0x27
    bb_slot:
        mov [edi+0x24], eax
        mov eax, 10
        call %(rnd)#x
        sub eax, 5
        mov [edi+0x1c], eax
        mov eax, 10
        call %(rnd)#x
        sub eax, 5
        mov [edi+0x20], eax
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx+0xe0]
    bb_out:
        pop edi
        pop esi
        pop ebx
    bb_done:
        pop eax
        mov edx, 1
        push eax
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %(id)d
        pop eax
        jne done
        push eax
        push ebx
        push esi
        push edi
        mov edi, [ebp-8]
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [edi+0x10]
        mov [ebx+%(gt)#x], eax
        test dword ptr [edi+0x10], 1
        jnz spawned
        cmp dword ptr [edi+0x10], %(ticks)d
        jae spawned
        mov eax, [edi+0x10]
        cmp eax, %(imax)d
        jbe capped
        mov eax, %(imax)d
    capped:
        push eax
        push 0
    outer:
        mov eax, [esp]
        xor edx, edx
        mov ecx, %(per)d
        div ecx
        inc eax
        push eax
    inner:
        mov dl, 0x1f
        mov eax, [ebx+%(map)#x]
        call %(add)#x
        mov esi, eax
        mov eax, [edi+0x14]
        mov [esi+0x14], eax
        mov eax, [edi+0x18]
        mov [esi+0x18], eax
        mov eax, 360
        call %(rnd)#x
        push eax
        mov eax, [esp+8]
        inc eax
        call %(rnd)#x
        mov ecx, [esp+8]
        shr ecx, 1
        sub eax, ecx
        push eax
        mov eax, [edi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [eax+4]
        add edx, %(cx0)d
        mov ecx, [esp+12]
        shr ecx, 1
        add edx, ecx
        add edx, [esp]
        pop ecx
        push edx
        mov edx, [eax+8]
        add edx, %(cy0)d
        mov ecx, [esp+12]
        shr ecx, 2
        %(tilt)s edx, ecx
        push edx
        mov eax, 2
        call %(rnd)#x
        push eax
        lea eax, [esi+0x1c]
        push eax
        mov eax, %(rr)d
        call %(rnd)#x
        add eax, %(r0)d
        mov edx, [esp+24]
        shr edx, 2
        add eax, edx
        mov edx, [esp+24]
        shr edx, 1
        mov ecx, 45
        call %(arc)#x
        dec dword ptr [esp]
        jnz inner
        pop eax
        inc dword ptr [esp]
        mov eax, [esp]
        cmp eax, [esp+4]
        jbe outer
        add esp, 8
    spawned:
        pop edi
        pop esi
        pop ebx
        pop eax
        mov edx, %(slot)d
    done:
        ret
    """ % {"id": SPELL_ID, "slot": PORTAL_SLOT, "ticks": SWIRL_TICKS, "map": MAP_GLOBAL, "add": ADDEFFECT,
           "bb": BLOOD_SPELL, "bbtick": BLOOD_TICK, "corpse": CORPSE_CLASSREF, "tecreate": TECREATE,
           "getlevel": GETMAPLEVEL, "getfield": GETFIELD,
           "rnd": RANDINT, "getxyz": GETXYZ, "arc": MAKEARC, "imax": SWIRL_IMAX, "per": SWIRL_PER,
           "cx0": SWIRL_CX0, "cy0": SWIRL_CY0, "tilt": SWIRL_TILT, "r0": SWIRL_R0, "rr": SWIRL_RR, "gt": GATE_TICK_VA})
    place("dark", """
        cmp dword ptr [eax+0x18], 0x82
        je %(yes)#x
        cmp dword ptr [eax+0x18], %(id)d
        je %(yes)#x
        jmp %(next)#x
    """ % {"yes": DARK_YES, "id": SPELL_ID, "next": DARK_NEXT})
    place("slot", """
        push ebp
        mov ebp, esp
        push ecx
        mov [ebp-4], eax
        mov eax, [ebp+8]
        mov eax, [eax-4]
        cmp byte ptr [eax+0x34], 0x1f
        jne back
        cmp dword ptr [eax+0x18], %(id)d
        jne back
        cmp dword ptr [ebp-4], 0
        jne back
        mov dword ptr [ebp-4], %(spark)d
    back:
        jmp %(resume)#x
    """ % {"id": SPELL_ID, "spark": SPARK_SLOT, "resume": SLOT_RESUME})
    place("show", """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        mov eax, 1
        jne done
        mov eax, %(slot)d
    done:
        ret
    """ % {"id": SPELL_ID, "slot": PORTAL_SLOT})
    # gate: eax = TE.  Spell 354 strikes are refused until the driver's published tick reaches STRIKE_DELAY; the
    # countdown [te+0x30] is set to 1 so the phase-1 tail retries on the next tick.  Everything else tail-calls
    # NextStrike unchanged (rel32 into the same module = PIC).
    place("gate", """
        cmp dword ptr [eax+0x18], %(id)d
        jne pass
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        cmp dword ptr [ebx+%(gt)#x], %(delay)d
        pop ebx
        jae pass
        mov dword ptr [eax+0x30], 1
        ret
    pass:
        jmp %(ns)#x
    """ % {"id": SPELL_ID, "gt": GATE_TICK_VA, "delay": STRIKE_DELAY, "ns": NEXTSTRIKE})
    # 2026-10-15: also 365 Hurl Boulder - cue 0 plays at the pre-throw glow (patch_hurlboulder_glow_v1.py)
    # 2026-10-14: also 389 Implosion - its vacuum sound now plays at the cast start from patch_implosion_v1.py's cnt cave
    place("castsnd", """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x38], 0x77
        je %(skip)#x
        cmp dword ptr [eax+0x38], %(id)d
        je %(skip)#x
        cmp dword ptr [eax+0x38], 389
        je %(skip)#x
        cmp dword ptr [eax+0x38], 365
        je %(skip)#x
        jmp %(next)#x
    """ % {"id": SPELL_ID, "skip": CASTSND_SKIP, "next": CASTSND_NEXT})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def hook(va, orig, kind, target):
    return (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", target - (va + 5)) + b"\x90" * (len(orig) - 5)


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
    zone, where = build()
    hooks = [(va, orig, hook(va, orig, kind, where[name])) for name, va, orig, kind in HOOKS]
    live = [bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]) for va, orig, _h in hooks]
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _h in hooks)]
    def is_ours(l, va):
        return l[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", l, 1)[0] < ZONE_END and all(b == 0x90 for b in l[5:])
    state = ["vanilla" if l == orig else "ours" if is_ours(l, va) else "OTHER" for (va, orig, _h), l in zip(hooks, live)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s | relocs %s | caves %s" % (state, zstate, bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or "OTHER" in state: print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for name, s in where.items():
            print("  --", name)
            for i in md.disasm(zone[s - ZONE:], s):
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic == "ret" or (i.mnemonic == "jmp" and i.op_str in ("%#x" % RESUME_SPAWN, "%#x" % NEXTSTRIKE, "%#x" % CASTSND_NEXT)): break
    if a.revert:
        out = bytearray(d)
        for (va, orig, _h), st in zip(hooks, state):
            if st == "ours": out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in state) and zstate == "ours" and all(l == h for (va, orig, h), l in zip(hooks, live)):
        print("already applied"); return 0
    if "ours" not in state and zstate != "zero": print("ABORT: zone not zero on a vanilla dll"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, h in hooks: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = h
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
