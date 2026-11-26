#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Ashes to Ashes (spell 353, Death/Fire tier 3) - burns every corpse on the battlefield one by one, then
hits the target once per corpse consumed plus one (2026-10-13, v3).

The spell is a TDeathRay clone (patch_dual_sphere_spells_v1.py: ATK 9, DMG 1, physical+death+fire 0x00A1, range 3,
SpellTypes class 7 = the DIRECT single-target class of Vaporize / Death Ray / Remedy - no projectile path, so it can
neither be blocked nor hit a friendly unit; v1's class 0x0B shot a projectile and crashed on the caster's own
blocking unit).  Two caves:

SWEEP - hook 0x40B33D in TCAbRangedTE.Execute 0x40B2F8 (`mov eax,[ebp-4] / mov eax,[eax+0x38]` = the phase switch;
  te = [ebp-4], [te+0x18] spell id, [te+0x38] phase).  For spell 353 in phase 0: walk every hex x 0..[level+0xC]-1 /
  y 0..[level+0x10]-1 of map level 0 (GetMapLevel 0x401E64 on [[0x469420]]+0x10, GetField 0x401E54 = [level+0x78][y]
  + [level+0x74][x] with NO bounds check, hence the level's own size - a fixed 6..0x3A sweep crashed), field
  VMT+0x80 FindOwnedChild(0x220108 = TCCorpseHS.GetClassID @0x423900): record each corpse's (x, y) in the QUEUE
  (DATA slack 0x46B900: +0 count, +4 next, +8 tick countdown, +0xC fresh flag, +0x10.. 64 x (word x, word y)),
  play the spell's sound 1 (the ignition hiss) when any were found.  Nothing is spawned or freed here.
GATE - both `call NextStrike` sites 0x40B6F1 (phase 0 = the immediate first strike) / 0x40CBE7 (phase 1 = the
  [te+0x30] countdown, retried every tick while we keep setting it to 1); eax = TE.  The sites already called the
  Hellfire gate 0x43C8D0 (patch_tc_hellfire_portal_v1.py) - ours CHAINS to whatever they called before (decoded at
  apply; --revert decodes it back out of our cave's last jmp).  For spell 353:
    * first call after a sweep (fresh): [te+0x28] (strikes to perform; NextStrike 0x40D290 stops at [te+0x34] >=
      [te+0x28]) := 1 + corpses recorded -> one hit per corpse plus one.  It is set here because Execute's phase-0
      setup writes [te+0x28] AFTER the sweep hook.
    * while corpses remain: every STEP ticks pop the next (x, y), re-find its TCCorpseHS, spawn a kind-0x26 effect
      on the hex (the Hellfire/Harvest recipe: HXtoHP 0x4022BC, AddEffect 0x41C6EC(map [0x46C064], dl 0x26), TXYZ
      0x46EB24 + Create 0x401040, XYZList.Add 0x402DE4 / GetXYZ 0x402DF4; [fx+0x14]=0x34, [fx+0x18]=353, [fx+0x2C]
      =nil -> its NewFrame draws the spell's gfx slot 1 = the burning corpse, 20 x 2 ticks) and FREE the corpse
      sprite (TObject.Free 0x401050 - what TCCorpseHS.MapFieldMsgProc does @0x424125; a freed corpse cannot be
      raised).  Refuse the strike meanwhile ([te+0x30] := 1; ret).
    * then while any kind-0x26 effect of spell 353 is still alive in the map's effect list ([[0x469420]]+0x11C
      TList; kind = [fx+0x34], AddEffect stores dl there): refuse.
    * else pass one strike every GAP ticks (the vanilla cadence is Random(3)+4 ticks, too fast to read as separate
      hits) -> each strike = the hit animation (gfx slot 0 at the target, sound 0 from the caster's cast animation
      like Vaporize's own) + a 9/1 damage CA.
  v4: the CAMERA follows - every popped corpse calls the map's VMT+0xBC (eax map, edx hx, ecx hy, push level 0 =
      what NextStrike's class-7 tail 0x40D884 does to centre the view on the target before each hit; THSMap.
      MakeVisible 0x5560C1CC calls the same slot when a point is outside the viewport), so the view centres on each
      burning corpse in turn and then, through the vanilla strike code, on the target.
Caves 0x43CF00.. (zero, no relocs; PIC via call/pop delta for the globals).  Backup <game>\backup\AoWTCPCK.dll.bak_ashes.
⚠ patch_tc_hellfire_portal_v1.py now reports its two gate sites as OTHER: revert this patch before re-applying it.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_ashes"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43CF00, 0x43D600          # v7: grown again (0x43D400..0x43D600 verified zero / no relocs)
SPELL_ID = 353
HOOK, ORIG, RESUME = 0x40B33D, bytes.fromhex("8b45fc8b4038"), 0x40B343
MAP_LIST_GLOBAL, MAP_GLOBAL, SPELLREG_GLOBAL = 0x469420, 0x46C064, 0x46E8D0
GETMAPLEVEL, GETFIELD, CORPSE_CLASSID = 0x401E64, 0x401E54, 0x220108
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, TXYZ_IAT, TOBJFREE, GETSPELL = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4, 0x46EB24, 0x401050, 0x4029B4
SFXPLAY = 0x4022F4
KIND = 0x26
FX_DX, FX_DY = 16 - 32, 16 - 44          # 64x64 burst centred on the hex, a little up
QUEUE, QMAX, STEP, GAP = 0x46B900, 64, 14, 7      # v9: GAP 7 (+ the vanilla Random(3)+4 reload = 11..13 ticks between hits, ~ one 12-tick slice); GAP = ticks between the hits (v4) so each repeat reads; DATA page slack (VirtualSize ends 0x46B7C8; hail ring ..0x46B814, Hellfire gate tick 0x46B840, Harvest latch 0x46B860)
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]
NEXTSTRIKE, HF_ZONE = 0x40D290, (0x43C500, 0x43CA00)
# v5 (2026-10-13): MOTES - every popped corpse also streams N_MOTES kind-0x1F sparkles from its hex to the caster's
# sprite on MakeLinePath 0x402E04 (eax x0, edx y0, ecx x1; pushed y1, steps, &[fx+0x1C]; Random 0x401020 jitter -
# Harvest's recipe, RNG calls identical on every machine).  A kind-0x1F sparkle draws the spell's gfx slot 0 (the
# hit cloud!), so the sprite-slot picker SUB_0042E4C4 (eax = slot, [esp+4] = the caller's frame, [frame-4] = fx) is
# hooked too: for a kind-0x1F effect of spell 353 slot 0 becomes MOTE_SLOT.  That site is already a `jmp` into the
# Hellfire cave (its own slot 4 for 354) - ours CHAINS in front of it exactly like the gate; on a vanilla site the
# cave replays the 7-byte prologue and resumes at 0x42E4CB instead.
RANDINT, MAKELINE = 0x401020, 0x402E04
N_MOTES, MOTE_SLOT = 7, 2
SLOT_SITE, SLOT_ORIG, SLOT_RESUME = 0x42E4C4, bytes.fromhex("558bec51894 5fc".replace(" ", "")), 0x42E4CB
# v6 (2026-10-13): the SWIRL is a kind-0x26 driver the gate spawns at the target on EVERY strike pass ([fx+0x24] = 1
# marks it; the corpse burns have 0) drawing gfx slot 3 (6 loop + 7 fade frames x 2 ticks); the strike effect itself
# (slot 0) is a 4-tick pulse so the damage lands right away.  The kind-0x26 NewFrame slot pick @0x42A5E9 (vanilla
# `mov edx,1`; now `call 0x43C5E0` = the Hellfire nf cave: 354 -> slot 3) is chained like the sprite-slot site: ours
# answers slot SWIRL_SLOT for a 353 effect with the marker and otherwise jumps on (or replays `mov edx,1; ret`).
NF_SITE, NF_ORIG, NF_RESUME = 0x42A5E9, bytes.fromhex("ba01000000"), 0x42A5EE
SWIRL_SLOT, SWIRL_DX, SWIRL_DY = 3, 16, 16
# v7 (user: the swirl restarted on every hit): ONE driver per cast - the gate spawns it on the first strike pass only
# (if none with the marker is alive) and, on the LAST strike ([te+0x34]+1 >= [te+0x28]), sets its tick [fx+0x10] to
# FADE_TICK = the first fade frame x (f18+1) so the 8-frame fade plays right after the last hit and the driver dies.
# v8: the drawn frame comes from the SEQUENCE's own counter (TImageSequence kind 4 steps itself every f18+1 ticks), so
# a tick jump cannot show a fade inside the same sequence.  Now: slot 3 = a 90-frame unit-height loop (one driver per
# cast, 180 ticks; GetTotalSequenceFrames = entries x (f18+1) ticks), and on the LAST strike the gate KILLS the loop
# driver (tick := KILL_TICK >= total -> the kind-0x26 handler marks it done next frame) and spawns a second driver with
# marker 2 drawing slot 4 = the 8-frame scatter/fade.  nf/show caves map marker m -> slot m + 2.
# v9 (user: per-hit swirls, short, no fade): every strike pass spawns ONE 12-tick driver whose marker = (strikes done & 3) + 1
# -> slots 3..6 = four 6-frame slices of a seamless 24-frame loop, so the spin is phase-continuous across hits and simply
# stops after the last one.  No scan, no kill, no fade.  nf/show caves: marker m (1..4) -> slot m + 2.
N_SLICES = 4
# v10 (user: still a gap between swirls): ONE driver, slot 3 = the full 24-frame loop (its kind-4 sequence draws
# frames[counter mod 24] forever); the gate RESETS its lifetime ([fx+0x10] := 0) on every call during the hit phase (the
# gate runs every tick except the engine's own 4-6 tick reload after a strike, far less than the 48-tick life), spawns
# it on the first strike pass if none is alive, and once ALL strikes are done ([te+0x34] >= [te+0x28]) kills it
# (tick := KILL_TICK) and passes straight through.  `finddrv` = an in-cave subroutine (eax = driver or 0).
KILL_TICK = 100000
# v11 (2026-10-13, found by the trace): the burn-wait scan refused strikes while ANY kind-0x26/353 effect lived - which
# included the swirl driver itself, so every hit waited ~48 ticks for the pillar to die and respawned it.  The scan now
# skips marked ([fx+0x24] != 0) effects.  Sounds: 0 = cast whirl (first strike's caster animation), 1 = per-hit impact
# (the kind-7 landing @0x42D3E0 plays sound 1 on EVERY hit), 2 = corpse ignition (the sweep plays it).
# v10t (2026-10-13): TRACE ring in DATA slack 0x46BB00 (+0 write index, +0x10.. 64 x {code, [te+0x34], [te+0x28], driver})
# written by the in-cave `tr` subroutine (ecx = code, edx = te, eax = driver, all preserved) at: 1 = all-strikes-done
# branch (kill), 2 = corpse pop, 4 = gap/refresh tick, 5 = strike pass (eax = driver found or 0 -> spawned).  Read live
# with ashes_probe.py while the game is still open after a cast.
TRACE = 0x46BB00
# v6b: the kind-0x26 SHOW slot pick @0x430059 (TfxHS.Show jump table [0x26] = 0x430058; vanilla `mov eax,1`, live = `call
# 0x43C8B0` = the Hellfire show cave; [ebp-4] = fx, eax = the slot to DRAW) must be chained as well - NewFrame's pick
# only sets the frame index, Show's pick chooses the sprite: without it the swirl driver drew slot 1 (the corpse burn).
SHOW_SITE, SHOW_ORIG = 0x430059, bytes.fromhex("b801000000")
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build_sweep():
    # frame: [esp+0] level, [esp+4] x, [esp+8] y.  (NO `;` comments inside the source: keystone hangs on brackets in them.)
    src = """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne back
        cmp dword ptr [eax+0x38], 0
        jne back
        push ebx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        lea edi, [ebx+%(q)#x]
        xor esi, esi
        mov dword ptr [edi+4], 0
        mov dword ptr [edi+8], 0
        mov dword ptr [edi+12], 1
        sub esp, 12
        mov eax, [ebx+%(maplist)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        mov [esp], eax
        test eax, eax
        jz done
        mov dword ptr [esp+8], 0
    yloop:
        mov dword ptr [esp+4], 0
    xloop:
        mov eax, [esp]
        mov edx, [esp+4]
        mov ecx, [esp+8]
        call %(getfield)#x
        test eax, eax
        jz nexthex
        mov edx, %(corpse)#x
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jz nexthex
        cmp esi, %(qmax)d
        jae nexthex
        mov eax, [esp+4]
        mov [edi+esi*4+16], ax
        mov eax, [esp+8]
        mov [edi+esi*4+18], ax
        inc esi
    nexthex:
        inc dword ptr [esp+4]
        mov eax, [esp]
        mov edx, [esp+4]
        cmp edx, [eax+0xc]
        jl xloop
        inc dword ptr [esp+8]
        mov edx, [esp+8]
        cmp edx, [eax+0x10]
        jl yloop
    done:
        mov [edi], esi
        test esi, esi
        jz nosound
        mov edx, [ebx+%(map)#x]
        cmp byte ptr [edx+0x129], 0
        je nosound
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        mov edx, 2
        call %(play)#x
    nosound:
        add esp, 12
        pop edi
        pop esi
        pop ebx
    back:
        mov eax, [ebp-4]
        mov eax, [eax+0x38]
        jmp %(resume)#x
    """ % {"id": SPELL_ID, "q": QUEUE, "qmax": QMAX, "maplist": MAP_LIST_GLOBAL, "getlevel": GETMAPLEVEL, "getfield": GETFIELD,
           "corpse": CORPSE_CLASSID, "map": MAP_GLOBAL, "reg": SPELLREG_GLOBAL, "getspell": GETSPELL, "play": SFXPLAY, "resume": RESUME}
    return asm_delta(src, ZONE)


def build_gate(va, chain):
    """eax = TE.  Spell 353: set the strike count once, consume the queued corpses one per STEP ticks, hold the strike
    while any burn is alive; everything else (and the pass) tail-jumps to `chain`."""
    # pop frame: [esp+0] py, [esp+4] px (HXtoHP scratch), [esp+8] x, [esp+12] y, [esp+16] fx
    src = """
        cmp dword ptr [eax+0x18], %(id)d
        jne pass
        push ebx
        push esi
        push edi
        push eax
        call $D
        pop ebx
        sub ebx, $D
        lea edi, [ebx+%(q)#x]
        cmp dword ptr [edi+12], 0
        je notfresh
        mov dword ptr [edi+12], 0
        mov ecx, [edi]
        inc ecx
        mov [eax+0x28], ecx
    notfresh:
        mov edx, [esp]
        mov ecx, [edx+0x34]
        cmp ecx, [edx+0x28]
        jb active
        call finddrv
        mov ecx, 1
        mov edx, [esp]
        call tr
        test eax, eax
        jz donepass
        mov dword ptr [eax+0x10], %(kill)d
    donepass:
        pop eax
        pop edi
        pop esi
        pop ebx
        jmp %(chain)#x
    active:
        mov ecx, [edi+4]
        cmp ecx, [edi]
        jae allpopped
        cmp dword ptr [edi+8], 0
        je popone
        dec dword ptr [edi+8]
        jmp refuse
    popone:
        mov dword ptr [edi+8], %(step)d
        inc dword ptr [edi+4]
        push eax
        push ecx
        mov ecx, 2
        mov edx, [esp+28]
        xor eax, eax
        call tr
        pop ecx
        pop eax
        mov eax, [edi+4]
        cmp eax, [edi]
        jb keepstep
        mov dword ptr [edi+8], 0
    keepstep:
        sub esp, 20
        movzx eax, word ptr [edi+ecx*4+16]
        mov [esp+8], eax
        movzx eax, word ptr [edi+ecx*4+18]
        mov [esp+12], eax
        mov edx, [esp+8]
        mov ecx, [esp+12]
        mov eax, [ebx+%(maplist)#x]
        mov eax, [eax]
        mov esi, [eax]
        push 0
        call [esi+0xbc]
        mov eax, [ebx+%(maplist)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz popdone
        mov edx, [esp+8]
        mov ecx, [esp+12]
        call %(getfield)#x
        test eax, eax
        jz popdone
        mov edx, %(corpse)#x
        mov ecx, [eax]
        call [ecx+0x80]
        test eax, eax
        jz popdone
        mov esi, eax
        lea ecx, [esp+4]
        push esp
        mov eax, [esp+12]
        mov edx, [esp+16]
        call %(hx)#x
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov [esp+16], eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esp+16]
        mov eax, [eax+0x1c]
        call %(xyzadd)#x
        mov eax, [esp+16]
        mov eax, [eax+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp+4]
        add edx, %(dx)d
        mov [eax+4], edx
        mov edx, [esp]
        add edx, %(dy)d
        mov [eax+8], edx
        mov eax, [esp+16]
        mov dword ptr [eax+0x14], 0x34
        mov dword ptr [eax+0x18], %(id)d
        mov dword ptr [eax+0x2c], 0
        mov eax, esi
        call %(free)#x
        mov eax, [esp+20]
        mov eax, [eax+0x10]
        test eax, eax
        jz popdone
        mov eax, [eax+0x60]
        test eax, eax
        jz popdone
        mov esi, eax
        mov edx, [esi]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, [esi]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        call %(hx)#x
        mov edi, %(nmotes)d
    mloop:
        mov eax, [ebx+%(map)#x]
        mov dl, 0x1f
        call %(add)#x
        mov esi, eax
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        mov eax, 12
        call %(rnd)#x
        add eax, [esp]
        add eax, 8
        push eax
        mov eax, 30
        call %(rnd)#x
        add eax, 30
        push eax
        lea eax, [esi+0x1c]
        push eax
        mov eax, 12
        call %(rnd)#x
        add eax, [esp+16]
        add eax, 10
        push eax
        mov eax, 16
        call %(rnd)#x
        add eax, [esp+24]
        add eax, 8
        push eax
        mov eax, 16
        call %(rnd)#x
        add eax, [esp+32]
        add eax, 8
        pop edx
        pop ecx
        call %(line)#x
        dec edi
        jnz mloop
        add esp, 8
    popdone:
        add esp, 20
        jmp refuse
    allpopped:
        mov esi, [ebx+%(maplist)#x]
        mov esi, [esi]
        mov esi, [esi+0x11c]
        mov ecx, [esi+8]
        mov esi, [esi+4]
        xor edx, edx
    gl:
        cmp edx, ecx
        jae gnone
        mov eax, [esi+edx*4]
        cmp byte ptr [eax+0x34], %(kind)d
        jne gn
        cmp dword ptr [eax+0x14], 0x34
        jne gn
        cmp dword ptr [eax+0x18], %(id)d
        jne gn
        cmp dword ptr [eax+0x24], 0
        jne gn
    refuse:
        pop eax
        pop edi
        pop esi
        pop ebx
        mov dword ptr [eax+0x30], 1
        ret
    gn:
        inc edx
        jmp gl
    gnone:
        call finddrv
        push eax
        call find26
        test eax, eax
        jz notrace26
        mov edx, eax
        mov ecx, 6
        mov eax, [edx+0x24]
        call tr
        mov ecx, 7
        mov eax, [edx+0x10]
        call tr
    notrace26:
        pop eax
        mov ecx, 4
        mov edx, [esp]
        call tr
        test eax, eax
        jz nodrv
        mov dword ptr [eax+0x10], 0
    nodrv:
        cmp dword ptr [edi+8], 0
        je strike
        dec dword ptr [edi+8]
        jmp refuse
    strike:
        mov dword ptr [edi+8], %(gap)d
        call finddrv
        mov ecx, 5
        mov edx, [esp]
        call tr
        test eax, eax
        jnz haveit
        mov eax, [esp]
        sub esp, 8
        lea ecx, [esp+4]
        push esp
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
        add edx, %(sdx)d
        mov [eax+4], edx
        mov edx, [esp]
        add edx, %(sdy)d
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        mov dword ptr [esi+0x24], 1
        add esp, 8
    haveit:
        pop eax
        pop edi
        pop esi
        pop ebx
    pass:
        jmp %(chain)#x
    finddrv:
        mov esi, [ebx+%(maplist)#x]
        mov esi, [esi]
        mov esi, [esi+0x11c]
        mov ecx, [esi+8]
        mov esi, [esi+4]
        xor edx, edx
    fl:
        cmp edx, ecx
        jae fnone
        mov eax, [esi+edx*4]
        cmp byte ptr [eax+0x34], %(kind)d
        jne fn
        cmp dword ptr [eax+0x18], %(id)d
        jne fn
        cmp dword ptr [eax+0x24], 1
        je fret
    fn:
        inc edx
        jmp fl
    fnone:
        xor eax, eax
    fret:
        ret
    find26:
        mov esi, [ebx+%(maplist)#x]
        mov esi, [esi]
        mov esi, [esi+0x11c]
        mov ecx, [esi+8]
        mov esi, [esi+4]
        xor edx, edx
    f2l:
        cmp edx, ecx
        jae f2n
        mov eax, [esi+edx*4]
        cmp byte ptr [eax+0x34], %(kind)d
        jne f2x
        cmp dword ptr [eax+0x18], %(id)d
        jne f2x
        ret
    f2x:
        inc edx
        jmp f2l
    f2n:
        xor eax, eax
        ret
    tr:
        push esi
        push edi
        push eax
        lea esi, [ebx+%(trace)#x]
        mov edi, [esi]
        inc dword ptr [esi]
        and edi, 63
        shl edi, 4
        lea edi, [esi+edi+16]
        mov [edi], ecx
        mov eax, [edx+0x34]
        mov [edi+4], eax
        mov eax, [edx+0x28]
        mov [edi+8], eax
        pop eax
        mov [edi+12], eax
        pop edi
        pop esi
        ret
    """ % {"id": SPELL_ID, "q": QUEUE, "step": STEP, "gap": GAP, "maplist": MAP_LIST_GLOBAL, "getlevel": GETMAPLEVEL, "getfield": GETFIELD,
           "corpse": CORPSE_CLASSID, "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE,
           "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": FX_DX, "dy": FX_DY, "free": TOBJFREE, "chain": chain,
           "nmotes": N_MOTES, "rnd": RANDINT, "line": MAKELINE, "sdx": SWIRL_DX, "sdy": SWIRL_DY, "kill": KILL_TICK, "trace": TRACE}
    return asm_delta(src, va)


def build_nf(va, chain):
    """kind-0x26 NewFrame slot pick (eax = the spell's sequence list, must survive; [ebp-8] = fx): a 353 effect carrying
    the swirl marker [fx+0x24]=1 draws SWIRL_SLOT; anything else goes on to `chain` (the Hellfire nf cave) or, on a
    vanilla site, replays `mov edx,1` and returns."""
    tail = "jmp %#x" % chain if chain is not None else "mov edx, 1\n        ret"
    src = """
        push eax
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %(id)d
        jne n_pass
        mov edx, [eax+0x24]
        test edx, edx
        jz n_pass
        cmp edx, %(nsl)d
        ja n_pass
        add edx, %(slot)d
        push ebx
        push esi
        push edi
        push ecx
        push edx
        call $D
        pop ebx
        sub ebx, $D
        lea esi, [ebx+%(trace)#x]
        mov edi, [esi]
        inc dword ptr [esi]
        and edi, 63
        shl edi, 4
        lea edi, [esi+edi+16]
        mov dword ptr [edi], 8
        mov ecx, [eax+0x10]
        mov [edi+4], ecx
        movzx ecx, word ptr [eax+0xc]
        mov [edi+8], ecx
        mov [edi+12], edx
        pop edx
        pop ecx
        pop edi
        pop esi
        pop ebx
        pop eax
        ret
    n_pass:
        pop eax
        %(tail)s
    """ % {"id": SPELL_ID, "slot": SWIRL_SLOT - 1, "tail": tail, "nsl": N_SLICES, "trace": TRACE}
    return asm_delta(src, va)


def build_slot(va, chain):
    """SUB_0042E4C4 entry (eax = slot, [esp+4] = caller frame -> [frame-4] = fx): kind-0x1F effects of spell 353 draw
    MOTE_SLOT instead of slot 0.  `chain` = the previous hook target (Hellfire's cave), or None = vanilla site:
    then the displaced prologue is replayed and the code resumes at SLOT_RESUME."""
    tail = "jmp %#x" % chain if chain is not None else ".byte " + ", ".join("%#x" % b for b in SLOT_ORIG) + "\n        jmp %#x" % SLOT_RESUME
    src = """
        push ecx
        mov ecx, [esp+8]
        mov ecx, [ecx-4]
        cmp byte ptr [ecx+0x34], 0x1f
        jne s_pass
        cmp dword ptr [ecx+0x18], %(id)d
        jne s_pass
        test eax, eax
        jne s_pass
        mov eax, %(slot)d
    s_pass:
        pop ecx
        %(tail)s
    """ % {"id": SPELL_ID, "slot": MOTE_SLOT, "tail": tail}
    return bytes(ks.asm(src, va)[0])


def build_show(va, chain):
    """TfxHS.Show kind-0x26 slot pick ([ebp-4] = fx, returns eax = slot): a 353 effect with the swirl marker draws
    SWIRL_SLOT; anything else goes on to `chain` (the Hellfire show cave) or, on a vanilla site, returns 1."""
    tail = "jmp %#x" % chain if chain is not None else "mov eax, 1\n        ret"
    src = """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne w_pass
        mov eax, [eax+0x24]
        test eax, eax
        jz w_pass
        cmp eax, %(nsl)d
        ja w_pass
        add eax, %(slot)d
        push ebx
        push esi
        push edi
        push ecx
        push edx
        mov edx, [ebp-4]
        call $D
        pop ebx
        sub ebx, $D
        lea esi, [ebx+%(trace)#x]
        mov edi, [esi]
        inc dword ptr [esi]
        and edi, 63
        shl edi, 4
        lea edi, [esi+edi+16]
        mov dword ptr [edi], 9
        mov ecx, [edx+0x10]
        mov [edi+4], ecx
        movzx ecx, word ptr [edx+0xc]
        mov [edi+8], ecx
        mov [edi+12], eax
        pop edx
        pop ecx
        pop edi
        pop esi
        pop ebx
        ret
    w_pass:
        %(tail)s
    """ % {"id": SPELL_ID, "slot": SWIRL_SLOT - 1, "tail": tail, "nsl": N_SLICES, "trace": TRACE}
    return asm_delta(src, va)


def site_target(d, site):
    b = d[site - CODE_V2F:site - CODE_V2F + 5]
    if b[0] != 0xE8: return None
    return site + 5 + struct.unpack_from("<i", b, 1)[0]


def asm_delta(src, va):
    """`call $D / pop ebx / sub ebx, $D` = the PIC delta idiom, resolved by a two-pass assembly (keystone hangs on a
    label used as the sub immediate): call rel32 0 + a 32-bit placeholder, then the pop address is patched in."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e8000000005b81ebffffff7f")
    k = b.find(anchor); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


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
    sweep = build_sweep(); gate_va = ZONE + ((len(sweep) + 15) & ~15)
    # the gate sites: vanilla `call NextStrike`, the Hellfire gate (chain through it), or an earlier build of ours
    targets = [site_target(d, st) for st, _ in GATE_SITES]
    ours_gate = all(ZONE <= t < ZONE_END for t in targets if t is not None) and None not in targets
    if ours_gate:
        # the applied gate's own tail = the first `pop ebx / jmp <outside the zone>` after gate_va (the applied gate may be
        # longer or shorter than the one being built; the other caves end with pop ecx / pop eax / ret before their jmp)
        gb = d[gate_va - CODE_V2F:ZONE_END - CODE_V2F]; chain = None; k = gb.find(b"\x5b\xe9")
        while k >= 0:
            t = gate_va + k + 6 + struct.unpack_from("<i", gb, k + 2)[0]
            if not (ZONE <= t < ZONE_END): chain = t; break
            k = gb.find(b"\x5b\xe9", k + 1)
        assert chain is not None, "applied gate tail not found"
    else:
        assert len(set(targets)) == 1, "gate sites disagree: %s" % [hex(t) for t in targets if t]
        chain = targets[0]
    assert chain == NEXTSTRIKE or HF_ZONE[0] <= chain < HF_ZONE[1], "unexpected gate-site target %#x" % chain
    gate = build_gate(gate_va, chain)
    # the slot-picker site: vanilla prologue, a jmp into the Hellfire cave, or already ours (then decode its chain)
    slot_va = gate_va + ((len(gate) + 15) & ~15)
    sb = d[SLOT_SITE - CODE_V2F:SLOT_SITE - CODE_V2F + 7]
    if sb == SLOT_ORIG: slot_chain, slot_prev = None, None
    else:
        assert sb[0] == 0xE9, "unexpected bytes at the slot site: %s" % sb.hex()
        t = SLOT_SITE + 5 + struct.unpack_from("<i", sb, 1)[0]
        if ZONE <= t < ZONE_END:                                                   # ours: decode the applied slot cave's OWN tail (pop ecx / [prologue] / jmp)
            tb = d[t - CODE_V2F:t - CODE_V2F + 0x80]; k = tb.rfind(b"\xe9"); assert k >= 0
            tgt = t + k + 5 + struct.unpack_from("<i", tb, k + 1)[0]
            slot_chain = None if tgt == SLOT_RESUME else tgt
        else:
            assert HF_ZONE[0] <= t < HF_ZONE[1], "unexpected slot-site target %#x" % t
            slot_chain = t
        slot_prev = slot_chain
    slot = build_slot(slot_va, slot_chain)
    # the kind-0x26 slot-pick site: vanilla `mov edx,1`, a call into the Hellfire nf cave, or already ours
    nf_va = slot_va + ((len(slot) + 15) & ~15)
    nb = d[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5]
    if nb == NF_ORIG: nf_chain = None
    else:
        assert nb[0] == 0xE8, "unexpected bytes at the nf site: %s" % nb.hex()
        t = NF_SITE + 5 + struct.unpack_from("<i", nb, 1)[0]
        if ZONE <= t < ZONE_END:                                                   # ours: decode the applied nf cave's tail
            tb = d[t - CODE_V2F:t - CODE_V2F + 0x200]; k = tb.find(b"\x58\xe9")        # pop eax / jmp chain   # window covers the traced cave
            if k >= 0: nf_chain = t + k + 6 + struct.unpack_from("<i", tb, k + 2)[0]
            else: nf_chain = None                                                  # pop eax / mov edx,1 / ret = vanilla tail
        else:
            assert HF_ZONE[0] <= t < HF_ZONE[1], "unexpected nf-site target %#x" % t
            nf_chain = t
    nf = build_nf(nf_va, nf_chain)
    # the kind-0x26 SHOW slot-pick site: vanilla `mov eax,1`, a call into the Hellfire show cave, or already ours
    show_va = nf_va + ((len(nf) + 15) & ~15)
    wb = d[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5]
    if wb == SHOW_ORIG: show_chain = None
    else:
        assert wb[0] == 0xE8, "unexpected bytes at the show site: %s" % wb.hex()
        t = SHOW_SITE + 5 + struct.unpack_from("<i", wb, 1)[0]
        if ZONE <= t < ZONE_END:                                                   # ours: decode the applied show cave's OWN tail (ret / jmp chain, or mov eax,1 / ret)
            tb = d[t - CODE_V2F:t - CODE_V2F + 0x200]; k = tb.find(b"\xc3\xe9")   # window covers the traced cave
            show_chain = (t + k + 6 + struct.unpack_from("<i", tb, k + 2)[0]) if k >= 0 else None
        else:
            assert HF_ZONE[0] <= t < HF_ZONE[1], "unexpected show-site target %#x" % t
            show_chain = t
    show = build_show(show_va, show_chain)
    zone = (sweep + bytes(gate_va - ZONE - len(sweep)) + gate + bytes(slot_va - gate_va - len(gate)) + slot
            + bytes(nf_va - slot_va - len(slot)) + nf + bytes(show_va - nf_va - len(nf)) + show)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    show_hook = b"\xe8" + struct.pack("<i", show_va - (SHOW_SITE + 5))
    show_restore = SHOW_ORIG if show_chain is None else b"\xe8" + struct.pack("<i", show_chain - (SHOW_SITE + 5))
    print("show site -> %s | show cave @%#x" % ("vanilla" if show_chain is None else "chain %#x" % show_chain, show_va))
    nf_hook = b"\xe8" + struct.pack("<i", nf_va - (NF_SITE + 5))
    nf_restore = NF_ORIG if nf_chain is None else b"\xe8" + struct.pack("<i", nf_chain - (NF_SITE + 5))
    print("nf site -> %s | nf cave @%#x" % ("vanilla" if nf_chain is None else "chain %#x" % nf_chain, nf_va))
    slot_hook = b"\xe9" + struct.pack("<i", slot_va - (SLOT_SITE + 5)) + b"\x90\x90"
    slot_restore = SLOT_ORIG if slot_chain is None else b"\xe9" + struct.pack("<i", slot_chain - (SLOT_SITE + 5)) + b"\x90\x90"
    print("slot site -> %s | slot cave @%#x" % ("vanilla" if slot_chain is None else "chain %#x" % slot_chain, slot_va))
    gate_hooks = {st: b"\xe8" + struct.pack("<i", gate_va - nx) for st, nx in GATE_SITES}
    chain_hooks = {st: b"\xe8" + struct.pack("<i", chain - nx) for st, nx in GATE_SITES}
    print("gate sites %s | chain -> %#x (%s) | gate @%#x" % ("ours" if ours_gate else "pass-through", chain, "NextStrike" if chain == NEXTSTRIKE else "Hellfire gate", gate_va))
    hook = b"\xe9" + struct.pack("<i", ZONE - (HOOK + 5)) + b"\x90" * (len(ORIG) - 5)
    live = d[HOOK - CODE_V2F:HOOK - CODE_V2F + len(ORIG)]; zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d); bad = [r for r in rl if ZONE <= r < ZONE_END or HOOK <= r < HOOK + len(ORIG) or any(st <= r < st + 5 for st, _ in GATE_SITES) or SLOT_SITE <= r < SLOT_SITE + 7 or NF_SITE <= r < NF_SITE + 5 or SHOW_SITE <= r < SHOW_SITE + 5]
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("hook %s | zone %s (%d B) | relocs %s" % (state, zstate, len(zone), bad or "none"))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        out = bytearray(d); out[HOOK - CODE_V2F:HOOK - CODE_V2F + len(ORIG)] = ORIG; out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        for st in gate_hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = chain_hooks[st]
        out[SLOT_SITE - CODE_V2F:SLOT_SITE - CODE_V2F + 7] = slot_restore
        out[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = nf_restore
        out[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = show_restore
        write_inplace(a.dll, bytes(out)); print("reverted (gate sites -> %#x, slot site -> %s, nf site -> %s)" % (chain, "vanilla" if slot_chain is None else "%#x" % slot_chain, "vanilla" if nf_chain is None else "%#x" % nf_chain)); return 0
    if state == "ours" and zstate == "ours" and all(t == gate_va for t in targets) and d[SLOT_SITE - CODE_V2F:SLOT_SITE - CODE_V2F + 7] == slot_hook and d[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] == nf_hook and d[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] == show_hook: print("already applied"); return 0
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone; out[HOOK - CODE_V2F:HOOK - CODE_V2F + len(ORIG)] = hook
    for st in gate_hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = gate_hooks[st]
    out[SLOT_SITE - CODE_V2F:SLOT_SITE - CODE_V2F + 7] = slot_hook
    out[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = nf_hook
    out[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = show_hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
