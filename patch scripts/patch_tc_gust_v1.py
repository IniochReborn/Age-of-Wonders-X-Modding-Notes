#!/usr/bin/env python3
r"""
GUST (212, Air L1, 2026-10-16) - PUSHBACK.  AoWTCPCK.dll only.

User spec: combat spell, breath AOE, ATK 8 / DMG 3 Physical, "pushes all units in AOE one hex away from caster (if hex
valid)".  The spell itself is a pipeline TColdBreath clone (class 5 breath cone: 20 strikes over the 12-hex fan, the
damage = the generic landing's CreateCA, pokes ATK/DMG/type); this patch adds the push.

RE (TCAbRangedTE.Execute 0x40B2F8, te = [ebp-4]):
  * generic strike landing 0x40C31F: fx = [ebp-0x20]; if [fx+0xC] and target [fx+0x2C] alive -> CreateCA ...
    0x40C339 `mov eax,[ebp-0x20] / mov eax,[eax+0x2c]` (6 B) is reached once per landing ON A LIVING TARGET.
  * token end (phase 1, all strikes thrown + effect list [map+0x11C] empty): 0x40CB46 `mov eax,[ebp-4] / mov eax,
    [eax+0x10]` (6 B) runs exactly ONCE, right before `mov byte [ebp-9],1` (token done) - after every hit resolved.
Hooks (call cave + nop; a site that is already a `call prev; nop` chain is chained IN FRONT, prev decoded at apply
time and kept in the zone header for an exact --revert):
  REC 0x40C339: for te spell 212 record the struck combat object [fx+0x2C] in a 16-entry table (deduped; the table is
      tagged with the te, a new te resets it).  BSS slack 0x46C640..0x46C6D0 (table + dist2 array; zero at load, unused).
  END 0x40CB46: for te spell 212 with a table of this te: PUSH, then clear the table.
PUSH (deterministic - runs inside the broadcast token on every machine, no RNG):
  1. for each recorded object: alive (vmt+0x60), has a unit HS [cu+0x60] that is THE unit on its own hex
     (FindOwnedChild 0x220104 == HS - walls / dead / moved objects drop out); dist2 = pixel distance^2 from the caster
     hex (HXtoHP of te caster hex [+0x1C]/[+0x1E]).
  2. far-to-near (max dist2 first) so the outer ring makes room for the inner one: the destination = the neighbour
     (CenterHNtoHX ring 1) of the unit's hex FARTHEST from the caster (must be strictly farther than the unit itself;
     first wins ties); it must be on the map, hold no unit, and pass the ENGINE's own per-unit validity: a
     TCombatMoveControlSettings built for THAT unit (CreateMovePointTable from its own resource, as TCAI.EvalBattle /
     Void Step v4) -> TMoveControl.Activate -> ValidLocation -> Deactivate.  Invalid -> the unit stays.
  3. the move = Void Step's proven one-step warp: path TXYLList[dest, src] (cost 0 -> no MP spent), CreateCombatMoveTE
     (unit, path) -> Validate -> [te+0x18]=1 -> ExecuteDefaultMove (TUnitHS.MoveTo + AddHS + MovedTo + explore/redraw)
     -> Free.
Zone AoWTCPCK 0x442800..0x442C00 (verified zero, reloc-free): +0 prev REC, +4 prev END (0 = vanilla), code at +8.

v2 2026-10-16 (user: "it didn't push anyone back") - ROOT CAUSE: a breath (category 5) strike NEVER carries a target
object: NextStrike's common tail forces [fx+0x2C] = 0 for category 5 (0x40F0A8), so REC (0x40C339, after the
`[fx+0x2C] != 0` test) never fires for Gust -> empty table -> END pushed nothing.  Breath damage goes another way:
the no-target landing switch 0x40C6DD -> [fx+0x14]=0x34 -> 0x40C856 (hurlboulder-glow jmp 0x43B120 -> category) ->
category 5 @0x40C871: if [fx+0x24] > 0 (the strike's damage hex; 0 = blocked) broadcast map msg 0x31013 (caster,
spell) to the field [fx+0x24]/[fx+0x28]; the unit HS there creates + executes the CA.  New site BRE 0x40C87E
(`mov dword [ebp-0x64],0x31013`, 7 B, reloc-free, vanilla) -> cave in ZONE2 0x443800..0x443C00 (+0 prev BRE): replays
the mov, then for te spell 212 records the combat unit on that damage hex ([hs+0x1C] of FindOwnedChild(0x220104))
into the same te-tagged table.  So every unit in the cone whose strike was not blocked is pushed (hit or miss).
REC stays (harmless; other categories); END unchanged.
v3 2026-10-16 (user: "the gfx sucks and looks like a breath - make it like SHOCKWAVE but only forward to the AOE";
"shake the units in the AOE before moving them, then a very slight hop, at most 3/4 of their height"):
  RE: vanilla Shockwave (id 0x7F, pfs key 137, SpellTypes 0x2C) = one long kind-0x2C effect at the caster whose
  NewFrame (0x42B2CA) spawns kind-0x1F particles (AddEffect 0x41C6EC dl 0x1F, [+0x14]/[+0x18] copied) on swarm paths
  round the caster; a kind-0x1F particle draws its spell's gfx slot 0 (PARTICLE.ILB 0-2 blue-white orbs for 0x7F)
  through GFXE's intensity table, fading over its path; its landing ([fx+0xC] set at path end, kind 0x1F, no target)
  falls through every Execute landing branch (0x43B120 only acts on kinds 5 / 7 / 0xA) -> pure visual.
  Winds of Fury's flight (kind 0x2F, NewFrame 0x42BC69): idle 20 ticks, then each tick t draws the carried unit HS
  ([fx+0x2C] = combat unit, its HS = [cu+0x60]) at offset p[t-20] - p[0] ([hs+0x2C] = dx, [hs+0x30] = dy - z, [hs+0x44]
  = 1) while spinning it (SetDirection each tick, 0x42BF56..0x42BF97); after the last point: cue-1 sound, then
  TUnitHS.MoveTo (HS VMT+0x10C = AoWEPACK 0x557843EC) onto the last point's field, offsets reset (0x42BD1E..0x42BDA5).
  v3 hooks (zone 3 AoWTCPCK 0x444800..0x445000 (2 KB), +0 = the slot site's previous jmp target; BSS slack 0x46C700..0x46C788
  = push snapshot):
  SPR 0x40F0A8 (NextStrike common tail `mov eax,[ebp-4] / cmp byte [eax+0x24],5`, 7 B, once per strike, path built):
      for te spell 212 spawn N_PART kind-0x1F particles per breath strike along that strike's direction (start 1/8 out
      from the caster, ends at 7/8..10/8 of the strike length, spread sideways up to 2 x SPREAD px, mirrored on odd
      strikes, 10..15 steps = different speeds) -> a forward-only shockwave spray filling the cone.  No RNG.  Replays the
      2 instructions (their flags feed the vanilla jne).
  SLT 0x42E4C4 (kind-0x1F sprite slot pick; chained in front of the soulsiphon / Ashes chain, prev decoded at apply):
      kind-0x1F of 212 asking for slot 0 -> slot 1 (the particle sprite).  Gust's slot 0 (the breath strikes) = blank.
  END 0x40CB46 now calls END3 (zone 3): it snapshots every recorded victim's hex, calls the v2 END (= the push, logic
      unchanged), then for every victim whose hex changed spawns one kind-0x2F effect: [fx+0x2C] = cu, path p0 = the
      destination (reference point, never drawn: [fx+0x10] preset 20), SHAKE points jittering +-4..1 px round the old
      hex, then MakeArcPathXY old -> new (~HOP_PTS points, height HOP_H px) -> the unit shakes, then hops over.  The HS
      offset is preset to (old - new) so it never flashes at the new hex.  If any animation was spawned END3 returns to
      0x40CB69 (the 'effects still running' path) instead of 0x40CB4B, so the token WAITS for the animations; the next
      END finds the table cleared and finishes normally (MP: everything is decided before the effects exist).
  SPN 0x42BF4D (6 B): kind-0x2F of spell 212 skips Winds' spin -> straight to [hs+0x44] = 1.
  LND 0x42BD1E (7 B): kind-0x2F of spell 212 skips the landing MoveTo (the v2 warp already moved the unit): resets the HS
      offsets itself and DETACHES the unit ([fx+0x2C] = 0 - the NewFrame common tail 0x42E3A3 then sets [fx+0xC] = 1 and the
      TE generic landing 0x40C31F would otherwise re-hit and re-record it), then 0x42BDCE (tick = -1; the map frame
      0x41C440 frees every [fx+0xC] effect).
  Sounds: cue 0 never ([fx+0x24]/[fx+0x28] = -5); cue 1 would play at this landing AND at every breath-strike landing
  (kind 5 plays cue 1), Gust has no cue 1 -> both silent (Sound.TSFXLibrary.Play returns quietly for a missing id).
v4 2026-10-16 (user: "the breath part is too short; the unit is displaced too late - move it DURING the breath; shake
as soon as the breath reaches them until they move; units that can't be pushed still shake"):
  TCK 0x40CB84 (phase-1 `call NextStrike`, category 5, every tick; vanilla rel call, reloc-free) -> zone 4 0x445400..0x445800:
      for te spell 212: one strike every CAD (2) ticks ([te+0x30] = countdown, unused by category 5); once every strike is
      thrown AND no strike of 212 is still flying (effect list scan: kind != 0x1F particle / 0x2F carrier, [fx+0xC] = 0)
      -> PUSH PHASE once (latch PUSHED = te): snapshot victim hexes, call the v2 END cave (push far-to-near + clear table),
      end every victim's shake carrier (detach + tick = count+20, only if still listed and carrying it), reset the HS
      offsets, and for every unit whose hex changed spawn a hop carrier (p0 = destination, MakeArcPathXY old -> new).
      All decisions inside the deterministic TE token (no RNG) - every hit has resolved before anyone moves.
  SHAKE (zone 4, called by BRE when a unit is first recorded = the first breath strike that reaches its hex): a kind-0x2F
      carrier holding the unit, p0 = its hex centre + SHN (150) jitter points (+-3 px x, +-1 px y) -> it trembles from the
      first hit until the push phase ends it (blocked / unpushable units shake too, then settle in place).
  SPR particles: steps PSTEP (20) + j + j/2 (v3 10..15) -> the spray lingers longer.  END3 clears the PUSHED latch; the
  real END finds the table cleared (v3 fallback push + shake/hop only if the push phase never ran).  zone 3's hexof /
  addpt moved to its top (zone 4 calls them).  BSS slack: CARR 0x46C788 (16 dwords), PUSHED 0x46C7C8.
v6 2026-10-16 (user: "abandon the v5 gfx idea, revert to the one I liked two attempts ago (v3) and polish it"): v4's
mechanics (TCK cadence, shake from first contact incl. unpushable, mid-breath push) + v3's forward SPR spray (PSTEP 10 ->
10..15 steps) + POLISH: the v4 "giant circles" were WoF's per-tick kind-0x1F swirl particles (0x42BFE8 loop, spell 212 ->
our slot-1 orbs) spawned round every victim by the long SHAKE carriers for the whole breath; SPN now sends a carrier with
> 60 path points (= a shake) straight to the tail 0x42E3A3 after setting [hs+0x44] (no swirl, no extra Random calls);
the short HOP carriers keep v3's swirl puff.  The v5 wave is retired: TCK no longer calls zone 5, which stays zero.
v5 2026-10-16 (user: "I don't like the gfx and the giant circles - like SHOCKWAVE, which after a build-up releases the
circle smoothly, but just a half / quadrant of the circle in the direction of the AOE"): Shockwave (NewFrame 0x42B2CA) =
120 ticks of 20 swirl particles/tick (0x402E0C) then at tick 120 one particle per DEGREE on MakeLinePath to an ellipse
(200 x 100, 75 steps) + 10 slower trails every 10 deg.  v5 WAVE (zone 5 0x445C00..0x446000, called by TCK each tick):
BU ticks of NB swirl particles at the caster (strikes HELD), then the release restricted to +-HALF deg round the caster
-> target direction (RR x RR*RY8/8 ellipse, RSTEP steps, NTR trails / 10 deg).  SPR no longer sprays (replay only);
212's slot 1 = Shockwave's own PARTICLE.ILB [0,1,2,1] (pipeline).  Private LCG (WRN), BSS WTE/WTK/WRN 0x46C7CC..0x46C7D8.
v7 2026-10-17 (Crashing Wave, Water L1 id 220 = "Gust with blue water particles that damages walls"): every Gust cave now
serves a FAMILY {212, 220} - each `cmp dword [R+0x18], 212` became `call fam_R` (zone 5 helpers, 5 B instead of 7 B: ZF = id
in {212, 220}; on a match the id is latched in CUR = .idata page slack 0x479FF0, PIC), every spawned effect's
`mov dword [R+0x18], 212` became `call setid_R` (copies CUR) - SPR copies the te's own id - so 220's particles / shake / hop
carriers carry 220 and draw 220's own (blue) gfx slot 1.  SPR: for 220 the spray ends at 8..7 eighths of the (wall-truncated)
strike instead of 10..7, so the water never visibly passes a wall.  Wall damage itself = patch_tc_crashingwave_v1.py.
v8 2026-10-17 (user: "crashing wave should not push units onto walls (unless 0 HP / gone); same for gust"): the push
destination test (unit on the hex) became `call blkchk` (zone 5): a unit OR an intact wall / gate section (HP [+0x20] > 0)
blocks the push (the unit stays, like any blocked push); rubble (HP 0) does not.  Zone 1 shrinks by 8 B.
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_gust.
"""
import argparse, os, re, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x442800, 0x442C00
CODE = ZONE + 8
SPELL = 212
SPELL2 = 220                                                           # v7: Crashing Wave (Water L1) shares every Gust cave
CUR = 0x479FF0                                                         # v7: .idata page slack (vsize ends 0x479EC8, page to 0x47A000; RW): latched family id
MAXN = 16
TAB_TE, TAB_N, TAB, DIST = 0x46C640, 0x46C644, 0x46C648, 0x46C690   # BSS slack: table 16 dwords + per-victim dist2 16 dwords (-> 0x46C6D0)
SITES = [("REC", 0x40C339, bytes.fromhex("8b45e08b402c"), "rec"),
         ("END", 0x40CB46, bytes.fromhex("8b45fc8b4010"), "end")]
ZONE2, ZONE2_END = 0x443800, 0x443C00                                  # v2: the breath-hit recorder (BRE)
SITE2 = ("BRE", 0x40C87E, bytes.fromhex("c7459c13100300"), "bre")      # mov dword [ebp-0x64], 0x31013 (category-5 landing)
ZONE3, ZONE3_END = 0x444800, 0x445000                                  # v3: particles, push animation, slot / spin / landing hooks
SNAPN, ANIMN, SNAP = 0x46C700, 0x46C704, 0x46C708                      # BSS slack: push snapshot (16 x {cu, packed old hex}) -> 0x46C788
N_PART, SPREAD, HOP_H, HOP_PTS, SHAKE = 4, 14, 24, 9, 14       # r7 (user: move completes right BEFORE the animation ends): hop 12 -> 9 pts
# v4 (2026-10-16): longer breath, shake from the first hit, push DURING the breath
ZONE4, ZONE4_END = 0x445400, 0x445800                                  # v4: per-tick driver (TCK), shake spawner, mid-breath push
CARR, PUSHED = 0x46C788, 0x46C7C8                                      # BSS slack: per-victim shake carrier (16 dwords) + 'pushed' te
CAD = 2                                                                # 1 breath strike every CAD ticks (vanilla 1 per tick)
PSTEP = 16                                                             # v6: back to v3's 10..15 steps (v4's 20..25 lingered)
SHN = 150                                                              # shake points per carrier (ticks; ended early at the push)
TCK_SITE, TCK_ORIG = 0x40CB84, bytes.fromhex("e807070000")             # phase-1 `call NextStrike` (category 5 only, every tick)
# v5 (2026-10-16): Shockwave-style build-up + released ring ARC (sector) instead of the per-strike spray
ZONE5, ZONE5_END = 0x445C00, 0x446000                                  # v5: wave (build-up swirl + sector release)
WTE, WTK, WRN = 0x46C7CC, 0x46C7D0, 0x46C7D4                           # BSS slack: wave te tag, wave tick, visual LCG state
BU = 20                                                                # build-up ticks (strikes held until the release)
NB = 8                                                                 # build-up swirl particles per tick (Shockwave: 20)
HALF = 55                                                              # sector half-angle (deg) round the caster -> target direction
RR = 120                                                               # release radius (px); ellipse ry = RR * RY8 / 8
RY8 = 7
RSTEP = 40                                                             # release ring path steps (trails: RSTEP + 5*j, j = 1..NTR)
NTR = 6                                                                # trailing particles every 10 deg (Shockwave: 10)
SWIRL = 0x402E0C                                                       # Shockwave's swirl-path maker (eax steps, edx radius, ecx angle; stack rnd360, x, y, rnd2, &list)
# (tag, site, original bytes, cave) - every one is `jmp/call cave` + nops; SPR is a call (the cave replays + rets)
SITES3 = [("SPR", 0x40F0A8, bytes.fromhex("8b45fc80782405"), "spr", "call"),
          ("SPN", 0x42BF4D, bytes.fromhex("8b45f88b402c"), "spn", "jmp"),
          ("LND", 0x42BD1E, bytes.fromhex("8d45e4508b45f8"), "lnd", "jmp")]
SLT_SITE = 0x42E4C4                                                    # a 7-B `jmp prev / nop / nop` chain head
A = dict(wte=WTE, wtk=WTK, wrn=WRN, bu=BU, nb=NB, half=HALF, rr=RR, ry8=RY8, rstep=RSTEP, ntr=NTR, swirl=SWIRL, zone5=ZONE5,
         spell=SPELL, maxn=MAXN, gmap=0x46C064, addfx=0x41C6EC, txyz=0x46EB24, tobjcreate=0x401040,
         xyzadd=0x402DE4, xyzget=0x402DF4, xyzcount=0x402DFC, mkline=0x402E04, mkarc=0x402E24,
         snapn=SNAPN, animn=ANIMN, snap=SNAP, carr=CARR, pushed=PUSHED, cad=CAD, pstep=PSTEP, shn=SHN, nextstrike=0x40D290, npart=N_PART, spread=SPREAD, hoph=HOP_H, hoppts=HOP_PTS, shake=SHAKE, tabte=TAB_TE, tabn=TAB_N, tab=TAB, dist=DIST,
         map=0x469420, tcg=0x46C064, setcls=0x4129A8, xylcls=0x46E940,
         getmaplevel=0x401E64, getfield=0x401E54, hn2hx=0x4022AC, hxtohp=0x4022BC,
         setcreate=0x40263C, setsrcpos=0x40263C + 0x30, setrelease=0x40265C, cmptable=0x4029BC, getplayer=0x402544,
         xylcreate=0x401AFC, xyladd=0x401B04, objfree=0x401050,
         createmovete=0x40F548, validate=0x4081EC, execdefmove=0x408278,
         iat_gp=0x46E7CC, gp_s=0x557268E4, ep_act=0x5574646C, ep_valid=0x557458E8, ep_deact=0x557466B4)
assert A["setsrcpos"] == 0x40266C


# ---- v7: family helpers (zone 5).  fam_R: ZF = ([R+0x18] in {SPELL, SPELL2}); on a match CUR := the id; preserves every
# register (only the flags change).  setid_R: [R+0x18] := CUR; preserves every register.  PIC (call/pop delta).
def helpers_src():
    out = []
    for r in ("eax", "ecx", "esi"):
        out.append(("fam_" + r, """
            push edx
            mov edx, [%s+0x18]
            cmp edx, %d
            je fm_%s
            cmp edx, %d
            jne fx_%s
        fm_%s:
            push ebx
            call $D
            pop ebx
            sub ebx, $D
            mov [ebx+%#x], edx
            pop ebx
            cmp edx, edx
        fx_%s:
            pop edx
            ret
        """ % (r, SPELL, r, SPELL2, r, r, CUR, r)))
    for r in ("eax", "edi"):
        out.append(("setid_" + r, """
            push edx
            push ebx
            call $D
            pop ebx
            sub ebx, $D
            mov edx, [ebx+%#x]
            mov [%s+0x18], edx
            pop ebx
            pop edx
            ret
        """ % (CUR, r)))
    # v8 2026-10-17 (user: "crashing wave should not push units onto walls (unless the wall has 0 HP / is gone); same for
    # gust"): blkchk - eax = the destination field (non-nil); returns eax != 0 when the field holds a unit (FindOwnedChild
    # 0x220104, the v2 test) OR an INTACT wall (TCityWall 0x220504) / gate (TCityWallDoor 0x220506) section = HP [+0x20] > 0.
    # Destroyed sections (HP 0, rubble) do not block.  Clobbers eax / ecx / edx only (as the FindOwnedChild call it replaces).
    out.append(("blkchk", """
        push esi
        mov esi, eax
        mov edx, 0x220104
        mov ecx, [esi]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz bk_out
        mov eax, esi
        mov edx, 0x220504
        mov ecx, [esi]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz bk_gate
        cmp dword ptr [eax+0x20], 0
        jg bk_out
    bk_gate:
        mov eax, esi
        mov edx, 0x220506
        mov ecx, [esi]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz bk_out
        cmp dword ptr [eax+0x20], 0
        jg bk_out
        xor eax, eax
    bk_out:
        pop esi
        ret
    """))
    return out


def build_helpers():
    blob = bytearray(); where = {}
    for name, src in helpers_src():
        va = ZONE5 + len(blob); where[name] = va; blob += asm_pic(src, va)
        while len(blob) % 4: blob += b"\x90"
    assert ZONE5 + len(blob) <= ZONE5_END
    return bytes(blob), where


HELPERS, HELPER_AT = build_helpers()
A.update(HELPER_AT, spell2=SPELL2, cur=CUR)


def caves(prev):
    rec_tail = ("jmp %#x" % prev["REC"]) if prev["REC"] else "mov eax, [ebp-0x20]\n mov eax, [eax+0x2c]\n ret"
    end_tail = ("jmp %#x" % prev["END"]) if prev["END"] else "mov eax, [ebp-4]\n mov eax, [eax+0x10]\n ret"
    a = dict(A, rec_tail=rec_tail, end_tail=end_tail)
    return [
        # ---- REC: per landing on a living target ([ebp-0x20] = fx) ----
        ("rec", """
            mov eax, [ebp-4]
            cmp dword ptr [eax+0x14], 0x34
            jne r_out
            call %(fam_eax)#x
            jne r_out
            push ebx
            push ecx
            push edx
            call $D
            pop ebx
            sub ebx, $D
            cmp [ebx+%(tabte)#x], eax
            je r_have
            mov [ebx+%(tabte)#x], eax
            mov dword ptr [ebx+%(tabn)#x], 0
        r_have:
            mov edx, [ebp-0x20]
            mov edx, [edx+0x2c]
            xor ecx, ecx
        r_scan:
            cmp ecx, [ebx+%(tabn)#x]
            jge r_add
            cmp [ebx+ecx*4+%(tab)#x], edx
            je r_done
            inc ecx
            jmp r_scan
        r_add:
            cmp ecx, %(maxn)d
            jge r_done
            mov [ebx+ecx*4+%(tab)#x], edx
            inc dword ptr [ebx+%(tabn)#x]
        r_done:
            pop edx
            pop ecx
            pop ebx
        r_out:
            %(rec_tail)s
        """ % a),
        # ---- END: once per token, after every strike resolved ----
        ("end", """
            push ebx
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebp-4]
            call %(fam_eax)#x
            jne e_out
            cmp [ebx+%(tabte)#x], eax
            jne e_clear
            pushad
            mov esi, eax
            call push_all
            popad
        e_clear:
            and dword ptr [ebx+%(tabte)#x], 0
            and dword ptr [ebx+%(tabn)#x], 0
        e_out:
            pop ebx
            %(end_tail)s

        /* push_all: esi = te, ebx = PIC delta (both preserved) */
        push_all:
            push ebp
            mov ebp, esp
            sub esp, 0x60
            push edi
            /* AoWEPACK rebase delta (IAT GetPlayer) */
            mov eax, [ebx+%(iat_gp)#x]
            sub eax, %(gp_s)#x
            mov [ebp-0x18], eax
            /* map level 0 */
            mov eax, [ebx+%(map)#x]
            mov eax, [eax]
            mov eax, [eax+0x10]
            xor edx, edx
            call %(getmaplevel)#x
            mov [ebp-0x14], eax
            /* caster pixel */
            movzx eax, word ptr [esi+0x1c]
            movzx edx, word ptr [esi+0x1e]
            call hxp
            mov eax, [ebp-0x48]
            mov [ebp-8], eax
            mov eax, [ebp-0x4c]
            mov [ebp-0xc], eax
            /* n + per-victim distances (-1 = skip) */
            mov eax, [ebx+%(tabn)#x]
            mov [ebp-0x10], eax
            xor edi, edi
        d_loop:
            cmp edi, [ebp-0x10]
            jge d_end
            or dword ptr [ebx+edi*4+%(dist)#x], -1
            mov eax, [ebx+edi*4+%(tab)#x]
            test eax, eax
            jz d_next
            mov [ebp-0x3c], eax
            mov edx, [eax]
            call dword ptr [edx+0x60]
            test al, al
            jz d_next
            call vhex
            test eax, eax
            jz d_next
            mov eax, [ebp-0x1c]
            mov edx, [ebp-0x20]
            call hxp
            call dist2
            mov [ebx+edi*4+%(dist)#x], eax
        d_next:
            inc edi
            jmp d_loop
        d_end:
        /* far-to-near: pick the max remaining, process, mark done (-1) */
        p_round:
            or dword ptr [ebp-0x50], -1
            or dword ptr [ebp-0x34], -1
            xor edi, edi
        p_scan:
            cmp edi, [ebp-0x10]
            jge p_pick
            mov eax, [ebx+edi*4+%(dist)#x]
            cmp eax, [ebp-0x34]
            jle p_sn
            mov [ebp-0x34], eax
            mov [ebp-0x50], edi
        p_sn:
            inc edi
            jmp p_scan
        p_pick:
            mov edi, [ebp-0x50]
            test edi, edi
            js p_done
            mov eax, [ebx+edi*4+%(dist)#x]
            mov [ebp-0x54], eax
            or dword ptr [ebx+edi*4+%(dist)#x], -1
            mov eax, [ebx+edi*4+%(tab)#x]
            mov [ebp-0x3c], eax
            call vhex
            test eax, eax
            jz p_round
            call push_one
            jmp p_round
        p_done:
            pop edi
            mov esp, ebp
            pop ebp
            ret

        /* vhex: [ebp-0x3c] = cu -> [ebp-0x1c]/[ebp-0x20] = hex; eax = 1 if the cu's HS is the unit on that hex */
        vhex:
            mov eax, [ebp-0x3c]
            mov eax, [eax+0x60]
            test eax, eax
            jz vh_no
            mov edx, [eax]
            call dword ptr [edx+0x74]
            movsx eax, al
            mov [ebp-0x1c], eax
            mov eax, [ebp-0x3c]
            mov eax, [eax+0x60]
            mov edx, [eax]
            call dword ptr [edx+0x78]
            movsx eax, al
            mov [ebp-0x20], eax
            mov eax, [ebp-0x3c]
            mov eax, [eax+0x60]
            mov edx, [eax]
            call dword ptr [edx+0x24]
            cmp eax, 0x220104
            jne vh_no
            mov al, 1
            ret
        vh_no:
            xor eax, eax
            ret

        /* field_at(edx=x, ecx=y) -> eax = field or 0 when off the level */
        field_at:
            test edx, edx
            js fa_no
            test ecx, ecx
            js fa_no
            mov eax, [ebp-0x14]
            cmp edx, [eax+0xc]
            jge fa_no
            cmp ecx, [eax+0x10]
            jge fa_no
            call %(getfield)#x
            ret
        fa_no:
            xor eax, eax
            ret

        /* hxp(eax=x, edx=y) -> [ebp-0x48]/[ebp-0x4c] = pixel x/y */
        hxp:
            lea ecx, [ebp-0x4c]
            push ecx
            lea ecx, [ebp-0x48]
            call %(hxtohp)#x
            ret

        /* dist2 -> eax = (px-cpx)^2 + (py-cpy)^2 */
        dist2:
            mov eax, [ebp-0x48]
            sub eax, [ebp-8]
            imul eax, eax
            mov ecx, [ebp-0x4c]
            sub ecx, [ebp-0xc]
            imul ecx, ecx
            add eax, ecx
            ret

        /* push_one: cu [ebp-0x3c] at [ebp-0x1c]/[ebp-0x20], own dist2 [ebp-0x54] */
        push_one:
            mov eax, [ebp-0x54]
            mov [ebp-0x34], eax
            or dword ptr [ebp-0x2c], -1
            mov dword ptr [ebp-0x38], 1
        po_hn:
            lea eax, [ebp-0x24]
            push eax
            lea eax, [ebp-0x28]
            push eax
            mov ecx, [ebp-0x38]
            mov edx, [ebp-0x20]
            mov eax, [ebp-0x1c]
            call %(hn2hx)#x
            mov edx, [ebp-0x24]
            mov ecx, [ebp-0x28]
            call field_at
            test eax, eax
            jz po_next
            mov eax, [ebp-0x24]
            mov edx, [ebp-0x28]
            call hxp
            call dist2
            cmp eax, [ebp-0x34]
            jle po_next
            mov [ebp-0x34], eax
            mov eax, [ebp-0x24]
            mov [ebp-0x2c], eax
            mov eax, [ebp-0x28]
            mov [ebp-0x30], eax
        po_next:
            inc dword ptr [ebp-0x38]
            cmp dword ptr [ebp-0x38], 6
            jle po_hn
            cmp dword ptr [ebp-0x2c], -1
            je po_ret
            /* the destination must hold no unit - v8: and no INTACT wall / gate section (blkchk, zone 5) */
            mov edx, [ebp-0x2c]
            mov ecx, [ebp-0x30]
            call field_at
            call %(blkchk)#x
            test eax, eax
            jnz po_ret
            /* the engine's own validity for THIS unit */
            xor ecx, ecx
            mov dl, 1
            mov eax, [ebx+%(setcls)#x]
            call %(setcreate)#x
            mov [ebp-0x40], eax
            mov edi, eax
            push 0
            mov ecx, [ebp-0x20]
            mov edx, [ebp-0x1c]
            mov eax, edi
            call %(setsrcpos)#x
            mov eax, [ebp-0x3c]
            mov edx, [eax+0x60]
            mov [edi+0x9c], edx
            mov byte ptr [edi+0x1ac], 0x1a
            mov byte ptr [edi+0x65], 0
            lea edx, [edi+0xac]
            mov eax, [ebp-0x3c]
            mov eax, [eax+0x4c]
            call %(cmptable)#x
            mov eax, [ebp-0x3c]
            call %(getplayer)#x
            mov [edi+0x6c], al
            mov dword ptr [edi+0x98], 0xc8
            mov eax, [ebx+%(tcg)#x]
            mov eax, [eax+0xfc]
            mov [ebp-0x44], eax
            mov dword ptr [ebp-0x5c], 0
            mov edx, edi
            mov ecx, [ebp-0x18]
            add ecx, %(ep_act)#x
            call ecx
            test al, al
            jz po_rel
            mov eax, [ebp-0x44]
            mov edx, [ebp-0x40]
            mov ecx, [edx+0x9c]
            mov [eax+0x1e0], ecx
            mov cl, [edx+0x1ac]
            mov [eax+0x1e4], cl
            push 0
            mov ecx, [ebp-0x30]
            mov edx, [ebp-0x2c]
            mov eax, [ebp-0x44]
            mov edi, [ebp-0x18]
            add edi, %(ep_valid)#x
            call edi
            movzx eax, al
            mov [ebp-0x5c], eax
            mov eax, [ebp-0x44]
            mov ecx, [ebp-0x18]
            add ecx, %(ep_deact)#x
            call ecx
        po_rel:
            mov eax, [ebp-0x40]
            call %(setrelease)#x
            cmp dword ptr [ebp-0x5c], 0
            je po_ret
            /* the move: path [dest, src] at cost 0, Void Step's one-step warp */
            mov dl, 1
            mov eax, [ebx+%(xylcls)#x]
            call %(xylcreate)#x
            mov edi, eax
            mov [ebp-0x58], eax
            mov edx, [ebp-0x30]
            shl edx, 8
            or edx, [ebp-0x2c]
            mov eax, edi
            call %(xyladd)#x
            mov edx, [ebp-0x20]
            shl edx, 8
            or edx, [ebp-0x1c]
            mov eax, edi
            call %(xyladd)#x
            mov edx, edi
            mov eax, [ebp-0x3c]
            call %(createmovete)#x
            test eax, eax
            jz po_freepath
            push eax
            call %(validate)#x
            test al, al
            pop eax
            jz po_freete
            push eax
            mov dword ptr [eax+0x18], 1
            call %(execdefmove)#x
            pop eax
        po_freete:
            call %(objfree)#x
        po_freepath:
            mov eax, [ebp-0x58]
            call %(objfree)#x
        po_ret:
            ret
        """ % a),
    ]


def zone2_src(prev_bre, shake):
    tail = ("jmp %#x" % prev_bre) if prev_bre else "mov dword ptr [ebp-0x64], 0x31013\n ret"
    return """
        push eax
        push ebx
        push ecx
        push edx
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x14], 0x34
        jne b_out
        call %(fam_eax)#x
        jne b_out
        call $D
        pop ebx
        sub ebx, $D
        cmp [ebx+%(tabte)#x], eax
        je b_have
        mov [ebx+%(tabte)#x], eax
        mov dword ptr [ebx+%(tabn)#x], 0
        and dword ptr [ebx+%(pushed)#x], 0
    b_have:
        mov eax, [ebx+%(map)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getmaplevel)#x
        mov edx, [ebp-0x20]
        mov ecx, [edx+0x28]
        mov edx, [edx+0x24]
        call %(getfield)#x
        test eax, eax
        jz b_out
        mov edx, 0x220104
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz b_out
        mov edx, [eax+0x1c]
        test edx, edx
        jz b_out
        xor ecx, ecx
    b_scan:
        cmp ecx, [ebx+%(tabn)#x]
        jge b_add
        cmp [ebx+ecx*4+%(tab)#x], edx
        je b_out
        inc ecx
        jmp b_scan
    b_add:
        cmp ecx, %(maxn)d
        jge b_out
        mov [ebx+ecx*4+%(tab)#x], edx
        inc dword ptr [ebx+%(tabn)#x]
        call %(shake)#x
    b_out:
        pop edx
        pop ecx
        pop ebx
        pop eax
        %(tail)s
    """ % dict(A, tail=tail, shake=shake)


def build_zone2(prev_bre, shake):
    blob = bytearray(struct.pack("<I", prev_bre or 0))
    blob += asm_pic(zone2_src(prev_bre, shake), ZONE2 + 4)
    assert ZONE2 + len(blob) <= ZONE2_END, hex(ZONE2 + len(blob))
    return bytes(blob), ZONE2 + 4


def site2_state(d):
    tag, site, orig, _ = SITE2
    b = bytes(d[site - V2F:site - V2F + 7])
    if b == orig: return "vanilla", None
    if b[0] == 0xE8 and b[5:7] == b"\x90\x90":
        tgt = site + 5 + struct.unpack_from("<i", b, 1)[0]
        return ("ours" if ZONE2 <= tgt < ZONE2_END else "chain"), tgt
    return "OTHER", None


def zone3_src(prev_slt, end1):
    """Zone 3 caves.  prev_slt = the slot site's previous jmp target, end1 = the v2 END cave (zone 1)."""
    a = dict(A, prev_slt=prev_slt, end1=end1)
    return """
    /* hexof: esi = cu -> eax = packed hex (x | y << 16) of its HS, or -1.  Preserves ebx/esi/edi. */
    hexof:
        mov eax, [esi+0x60]
        test eax, eax
        jz hx_no
        push ecx
        mov edx, [eax]
        call dword ptr [edx+0x74]
        movsx ecx, al
        and ecx, 0xffff
        push ecx
        mov eax, [esi+0x60]
        mov edx, [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        shl eax, 16
        pop ecx
        or eax, ecx
        pop ecx
        ret
    hx_no:
        or eax, -1
        ret

    /* addpt: edi = fx, eax = x, edx = y -> appends a TXYZ (z = 0) to [fx+0x1C].  Preserves ebx/esi/edi. */
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
    /* ---- SPR: per breath strike (NextStrike frame: te = [ebp-4], fx = [ebp-0x10]) ---- */
    spr:
        mov eax, [ebp-4]
        call %(fam_eax)#x
        jne spr_van
        cmp dword ptr [eax+0x14], 0x34
        jne spr_van
        pushad
        mov esi, [ebp-0x10]
        mov edi, [ebp-4]
        call $D
        pop ebx
        sub ebx, $D
        push ebp
        mov ebp, esp
        sub esp, 0x40
        mov eax, [esi+0x1c]
        call %(xyzcount)#x
        cmp eax, 2
        jl spr_done
        dec eax
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzget)#x
        mov ecx, [eax+4]
        mov [ebp-0x0c], ecx
        mov ecx, [eax+8]
        mov [ebp-0x10], ecx
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(xyzget)#x
        mov ecx, [eax+4]
        mov [ebp-0x04], ecx
        mov ecx, [eax+8]
        mov [ebp-0x08], ecx
        mov eax, [ebp-0x0c]
        sub eax, [ebp-0x04]
        mov [ebp-0x14], eax
        mov eax, [ebp-0x10]
        sub eax, [ebp-0x08]
        mov [ebp-0x18], eax
        mov eax, [ebp-0x14]
        cdq
        xor eax, edx
        sub eax, edx
        mov ecx, eax
        mov eax, [ebp-0x18]
        cdq
        xor eax, edx
        sub eax, edx
        lea ecx, [ecx+eax+1]
        mov [ebp-0x1c], ecx
        mov eax, [ebp-0x18]
        neg eax
        imul eax, eax, %(spread)d
        cdq
        idiv dword ptr [ebp-0x1c]
        mov [ebp-0x20], eax
        mov eax, [ebp-0x14]
        imul eax, eax, %(spread)d
        cdq
        idiv dword ptr [ebp-0x1c]
        mov [ebp-0x24], eax
        test byte ptr [edi+0x34], 1
        jz spr_par
        neg dword ptr [ebp-0x20]
        neg dword ptr [ebp-0x24]
    spr_par:
        mov dword ptr [ebp-0x28], 0
    spr_loop:
        mov ecx, [ebp-0x28]
        cmp ecx, %(npart)d
        jge spr_done
        /* per particle: end factor (eighths) = 10 - 1*j ... (10, 9, 8, 7); side = (0, +1, -1, +2)[j]; steps = 10 + j + j/2 */
        mov eax, 10
        sub eax, ecx
        cmp dword ptr [edi+0x18], %(spell2)d
        jne spr_ef
        mov eax, ecx
        shr eax, 1
        neg eax
        add eax, 8
    spr_ef:
        mov [ebp-0x2c], eax
        mov eax, ecx
        and eax, 3
        lea edx, [ebx+sides]
        movsx eax, byte ptr [edx+eax]
        mov [ebp-0x30], eax
        mov eax, ecx
        shr eax, 1
        lea eax, [eax+ecx+%(pstep)d]
        mov [ebp-0x34], eax
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x1f
        call %(addfx)#x
        mov [ebp-0x38], eax
        mov dword ptr [eax+0x14], 0x34
        push dword ptr [edi+0x18]
        pop dword ptr [eax+0x18]
        mov dword ptr [eax+0x2c], 0
        mov dword ptr [eax+0x24], 0
        /* end point */
        mov eax, [ebp-0x14]
        imul eax, [ebp-0x2c]
        sar eax, 3
        add eax, [ebp-0x04]
        mov ecx, [ebp-0x20]
        imul ecx, [ebp-0x30]
        add eax, ecx
        mov [ebp-0x3c], eax
        mov eax, [ebp-0x18]
        imul eax, [ebp-0x2c]
        sar eax, 3
        add eax, [ebp-0x08]
        mov ecx, [ebp-0x24]
        imul ecx, [ebp-0x30]
        add eax, ecx
        push eax
        push dword ptr [ebp-0x34]
        mov eax, [ebp-0x38]
        add eax, 0x1c
        push eax
        /* start point: 1/8 out from the caster */
        mov eax, [ebp-0x18]
        sar eax, 3
        add eax, [ebp-0x08]
        mov edx, eax
        mov eax, [ebp-0x14]
        sar eax, 3
        add eax, [ebp-0x04]
        mov ecx, [ebp-0x3c]
        call %(mkline)#x
        inc dword ptr [ebp-0x28]
        jmp spr_loop
    spr_done:
        mov esp, ebp
        pop ebp
        popad
    spr_van:
        mov eax, [ebp-4]
        cmp byte ptr [eax+0x24], 5
        ret
    sides:
        .byte 0, 1, 0xff, 2

    /* ---- SLT: sprite slot pick (eax = slot, [esp+4] = the TfxHS method frame) ---- */
    slt:
        push ecx
        mov ecx, [esp+8]
        mov ecx, [ecx-4]
        cmp byte ptr [ecx+0x34], 0x1f
        jne slt_out
        call %(fam_ecx)#x
        jne slt_out
        test eax, eax
        jne slt_out
        mov eax, 1
    slt_out:
        pop ecx
        jmp %(prev_slt)#x

    /* ---- SPN / LND: kind-0x2F NewFrame (fx = [ebp-8]) ---- */
    spn:
        mov eax, [ebp-8]
        call %(fam_eax)#x
        jne spn_van
        cmp dword ptr [eax+0x14], 0x34
        jne spn_van
        /* v6: a SHAKE carrier (long path, > 60 points) must not spawn WoF's per-tick swirl particles (0x42BFA5..0x42C0E8)
           - over the whole breath they read as giant circles round every victim; it only gets the [hs+0x44] flag.  The
           short HOP carriers keep v3's look (the swirl puff during the hop). */
        push eax
        mov eax, [eax+0x1c]
        call %(xyzcount)#x
        cmp eax, 60
        pop eax
        jle spn_hop
        mov eax, [eax+0x2c]
        mov eax, [eax+0x60]
        mov byte ptr [eax+0x44], 1
        jmp 0x42E3A3
    spn_hop:
        jmp 0x42BF98
    spn_van:
        mov eax, [eax+0x2c]
        jmp 0x42BF53
    lnd:
        mov eax, [ebp-8]
        call %(fam_eax)#x
        jne lnd_van
        cmp dword ptr [eax+0x14], 0x34
        jne lnd_van
        /* our animation: reset the HS offsets ourselves and DETACH the unit ([fx+0x2C] = 0) - the common tail then sets
           [fx+0xC] = 1 and the TE's generic landing must not see a target (it would re-hit + re-record the unit) */
        mov ecx, [eax+0x2c]
        mov dword ptr [eax+0x2c], 0
        test ecx, ecx
        jz lnd_end
        mov ecx, [ecx+0x60]
        test ecx, ecx
        jz lnd_end
        xor edx, edx
        mov [ecx+0x2c], edx
        mov [ecx+0x30], edx
        mov byte ptr [ecx+0x44], 0
    lnd_end:
        jmp 0x42BDCE
    lnd_van:
        lea eax, [ebp-0x1c]
        push eax
        mov eax, [ebp-8]
        jmp 0x42BD25

    /* ---- END3: wraps the v2 END (Execute frame: te = [ebp-4]) ---- */
    end3:
        mov eax, [ebp-4]
        call %(fam_eax)#x
        jne e3_pass
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        and dword ptr [ebx+%(pushed)#x], 0
        cmp [ebx+%(tabte)#x], eax
        pop ebx
        jne e3_pass
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [ebx+%(tabn)#x]
        cmp ecx, %(maxn)d
        jle e3_n
        mov ecx, %(maxn)d
    e3_n:
        mov [ebx+%(snapn)#x], ecx
        mov dword ptr [ebx+%(animn)#x], 0
        xor edi, edi
    e3_snap:
        cmp edi, [ebx+%(snapn)#x]
        jge e3_snapd
        mov esi, [ebx+edi*4+%(tab)#x]
        mov [ebx+edi*8+%(snap)#x], esi
        or dword ptr [ebx+edi*8+%(snap)#x+4], -1
        test esi, esi
        jz e3_sn
        call hexof
        mov [ebx+edi*8+%(snap)#x+4], eax
    e3_sn:
        inc edi
        jmp e3_snap
    e3_snapd:
        popad
        call %(end1)#x
        push eax
        pushad
        call $D
        pop ebx
        sub ebx, $D
        xor edi, edi
    e3_anim:
        cmp edi, [ebx+%(snapn)#x]
        jge e3_animd
        mov esi, [ebx+edi*8+%(snap)#x]
        test esi, esi
        jz e3_an
        cmp dword ptr [ebx+edi*8+%(snap)#x+4], -1
        je e3_an
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz e3_an
        call hexof
        cmp eax, -1
        je e3_an
        cmp eax, [ebx+edi*8+%(snap)#x+4]
        je e3_an
        mov edx, [ebx+edi*8+%(snap)#x+4]
        call anim
        inc dword ptr [ebx+%(animn)#x]
    e3_an:
        inc edi
        jmp e3_anim
    e3_animd:
        mov ecx, [ebx+%(animn)#x]
        mov [esp+0x18], ecx
        popad
        pop eax
        test ecx, ecx
        jz e3_ret
        add dword ptr [esp], 0x1e
    e3_ret:
        ret
    e3_pass:
        jmp %(end1)#x

    /* anim: esi = cu, eax = new packed hex, edx = old packed hex.  ebx = PIC delta.  Preserves ebx/esi/edi. */
    anim:
        push ebp
        mov ebp, esp
        sub esp, 0x30
        push edi
        mov [ebp-0x04], eax
        mov [ebp-0x08], edx
        /* old pixel -> [ebp-0x0c]/[ebp-0x10], new pixel -> [ebp-0x14]/[ebp-0x18] (+16 = hex centre) */
        lea ecx, [ebp-0x10]
        push ecx
        lea ecx, [ebp-0x0c]
        movsx eax, word ptr [ebp-0x08]
        movsx edx, word ptr [ebp-0x06]
        call %(hxtohp)#x
        lea ecx, [ebp-0x18]
        push ecx
        lea ecx, [ebp-0x14]
        movsx eax, word ptr [ebp-0x04]
        movsx edx, word ptr [ebp-0x02]
        call %(hxtohp)#x
        add dword ptr [ebp-0x0c], 16
        add dword ptr [ebp-0x10], 16
        add dword ptr [ebp-0x14], 16
        add dword ptr [ebp-0x18], 16
        /* the effect */
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x2f
        call %(addfx)#x
        mov edi, eax
        mov dword ptr [edi+0x14], 0x34
        call %(setid_edi)#x
        mov [edi+0x2c], esi
        mov dword ptr [edi+0x24], -5
        mov dword ptr [edi+0x28], -5
        mov dword ptr [edi+0x10], 20
        /* p0 = the destination (reference, never drawn) */
        mov eax, [ebp-0x14]
        mov edx, [ebp-0x18]
        call addpt
        /* the shake: x jitter a = 4 - k/4, sign alternating */
        mov dword ptr [ebp-0x1c], 0
    an_sh:
        mov ecx, [ebp-0x1c]
        cmp ecx, %(shake)d
        jge an_shd
        mov eax, ecx
        shr eax, 2
        neg eax
        add eax, 4
        test cl, 1
        jz an_pos
        neg eax
    an_pos:
        add eax, [ebp-0x0c]
        mov edx, [ebp-0x10]
        call addpt
        inc dword ptr [ebp-0x1c]
        jmp an_sh
    an_shd:
        /* the hop: MakeArcPathXY old -> new, divisor = max(1, (|dx|+|dy|) / HOP_PTS) */
        mov eax, [ebp-0x14]
        sub eax, [ebp-0x0c]
        cdq
        xor eax, edx
        sub eax, edx
        mov ecx, eax
        mov eax, [ebp-0x18]
        sub eax, [ebp-0x10]
        cdq
        xor eax, edx
        sub eax, edx
        add eax, ecx
        xor edx, edx
        mov ecx, %(hoppts)d
        div ecx
        cmp eax, 1
        jge an_div
        mov eax, 1
    an_div:
        push dword ptr [ebp-0x18]
        push eax
        push %(hoph)d
        lea eax, [edi+0x1c]
        push eax
        mov eax, [ebp-0x0c]
        mov edx, [ebp-0x10]
        mov ecx, [ebp-0x14]
        call %(mkarc)#x
        /* the HS starts drawn at the OLD hex */
        mov eax, [esi+0x60]
        mov edx, [ebp-0x0c]
        sub edx, [ebp-0x14]
        mov [eax+0x2c], edx
        mov edx, [ebp-0x10]
        sub edx, [ebp-0x18]
        mov [eax+0x30], edx
        mov byte ptr [eax+0x44], 1
        pop edi
        mov esp, ebp
        pop ebp
        ret

    """ % a


def zone4_src(end1, hexof, addpt):
    """v4 zone 4: TCK (per-tick driver replacing the phase-1 `call NextStrike`), SHAKE (spawner, called by BRE), the
    mid-breath PUSH and its hop animation.  end1 = the v2 END cave (zone 1: push + clear the table)."""
    a = dict(A, end1=end1, hexof=hexof, addpt=addpt)
    return """
    /* inlist: eax = fx -> eax = fx if it is still in the combat map's effect list and not finished, else 0 */
    inlist:
        push ecx
        push edx
        mov edx, [ebx+%(map)#x]
        mov edx, [edx]
        mov edx, [edx+0x11c]
        mov ecx, [edx+8]
        mov edx, [edx+4]
    il_scan:
        dec ecx
        js il_no
        cmp [edx+ecx*4], eax
        jne il_scan
        cmp byte ptr [eax+0xc], 0
        jne il_no
        pop edx
        pop ecx
        ret
    il_no:
        xor eax, eax
        pop edx
        pop ecx
        ret

    /* hop: esi = cu, eax = new packed hex, edx = old packed hex -> one kind-0x2F carrier: p0 = the destination
       (reference), then MakeArcPathXY old -> new (HOP_H px high).  Preserves ebx/esi/edi. */
    hop:
        push ebp
        mov ebp, esp
        sub esp, 0x30
        push edi
        mov [ebp-0x04], eax
        mov [ebp-0x08], edx
        lea ecx, [ebp-0x10]
        push ecx
        lea ecx, [ebp-0x0c]
        movsx eax, word ptr [ebp-0x08]
        movsx edx, word ptr [ebp-0x06]
        call %(hxtohp)#x
        lea ecx, [ebp-0x18]
        push ecx
        lea ecx, [ebp-0x14]
        movsx eax, word ptr [ebp-0x04]
        movsx edx, word ptr [ebp-0x02]
        call %(hxtohp)#x
        add dword ptr [ebp-0x0c], 16
        add dword ptr [ebp-0x10], 16
        add dword ptr [ebp-0x14], 16
        add dword ptr [ebp-0x18], 16
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x2f
        call %(addfx)#x
        mov edi, eax
        mov dword ptr [edi+0x14], 0x34
        call %(setid_edi)#x
        mov [edi+0x2c], esi
        mov dword ptr [edi+0x24], -5
        mov dword ptr [edi+0x28], -5
        mov dword ptr [edi+0x10], 20
        mov eax, [ebp-0x14]
        mov edx, [ebp-0x18]
        call %(addpt)#x
        mov eax, [ebp-0x14]
        sub eax, [ebp-0x0c]
        cdq
        xor eax, edx
        sub eax, edx
        mov ecx, eax
        mov eax, [ebp-0x18]
        sub eax, [ebp-0x10]
        cdq
        xor eax, edx
        sub eax, edx
        add eax, ecx
        xor edx, edx
        mov ecx, %(hoppts)d
        div ecx
        cmp eax, 1
        jge hp_div
        mov eax, 1
    hp_div:
        push dword ptr [ebp-0x18]
        push eax
        push %(hoph)d
        lea eax, [edi+0x1c]
        push eax
        mov eax, [ebp-0x0c]
        mov edx, [ebp-0x10]
        mov ecx, [ebp-0x14]
        call %(mkarc)#x
        mov eax, [esi+0x60]
        mov edx, [ebp-0x0c]
        sub edx, [ebp-0x14]
        mov [eax+0x2c], edx
        mov edx, [ebp-0x10]
        sub edx, [ebp-0x18]
        mov [eax+0x30], edx
        mov byte ptr [eax+0x44], 1
        pop edi
        mov esp, ebp
        pop ebp
        ret

    /* ---- PUSH_PHASE: Execute frame ([ebp-4] = te); returns to TCK's caller ---- */
    push_phase:
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [ebx+%(tabn)#x]
        cmp ecx, %(maxn)d
        jle pp_n
        mov ecx, %(maxn)d
    pp_n:
        mov [ebx+%(snapn)#x], ecx
        xor edi, edi
    pp_snap:
        cmp edi, [ebx+%(snapn)#x]
        jge pp_snapd
        mov esi, [ebx+edi*4+%(tab)#x]
        mov [ebx+edi*8+%(snap)#x], esi
        or dword ptr [ebx+edi*8+%(snap)#x+4], -1
        test esi, esi
        jz pp_sn
        call %(hexof)#x
        mov [ebx+edi*8+%(snap)#x+4], eax
    pp_sn:
        inc edi
        jmp pp_snap
    pp_snapd:
        popad
        call %(end1)#x
        pushad
        call $D
        pop ebx
        sub ebx, $D
        xor edi, edi
    pp_fin:
        cmp edi, [ebx+%(snapn)#x]
        jge pp_done
        mov esi, [ebx+edi*8+%(snap)#x]
        /* end this victim's shake carrier (only if it is still a live effect carrying this unit) */
        mov eax, [ebx+edi*4+%(carr)#x]
        and dword ptr [ebx+edi*4+%(carr)#x], 0
        test eax, eax
        jz pp_nc
        call inlist
        test eax, eax
        jz pp_nc
        cmp [eax+0x2c], esi
        jne pp_nc
        and dword ptr [eax+0x2c], 0
        push eax
        mov eax, [eax+0x1c]
        call %(xyzcount)#x
        pop ecx
        add eax, 20
        mov [ecx+0x10], eax
    pp_nc:
        test esi, esi
        jz pp_next
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz pp_next
        mov eax, [esi+0x60]
        test eax, eax
        jz pp_next
        xor edx, edx
        mov [eax+0x2c], edx
        mov [eax+0x30], edx
        mov byte ptr [eax+0x44], 0
        cmp dword ptr [ebx+edi*8+%(snap)#x+4], -1
        je pp_next
        call %(hexof)#x
        cmp eax, -1
        je pp_next
        cmp eax, [ebx+edi*8+%(snap)#x+4]
        je pp_next
        mov edx, [ebx+edi*8+%(snap)#x+4]
        call hop
    pp_next:
        inc edi
        jmp pp_fin
    pp_done:
        popad
        ret

    /* ---- SHAKE: edx = victim cu, ecx = its table index (called by BRE when a unit is first hit).  Preserves all. ---- */
    shake:
        pushad
        push ebp
        mov ebp, esp
        sub esp, 0x20
        call $D
        pop ebx
        sub ebx, $D
        mov [ebp-4], ecx
        and dword ptr [ebx+ecx*4+%(carr)#x], 0
        mov esi, edx
        call %(hexof)#x
        cmp eax, -1
        je ss_out
        mov [ebp-8], eax
        lea ecx, [ebp-0x10]
        push ecx
        lea ecx, [ebp-0xc]
        movsx eax, word ptr [ebp-8]
        movsx edx, word ptr [ebp-6]
        call %(hxtohp)#x
        add dword ptr [ebp-0xc], 16
        add dword ptr [ebp-0x10], 16
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x2f
        call %(addfx)#x
        mov edi, eax
        mov dword ptr [edi+0x14], 0x34
        call %(setid_edi)#x
        mov [edi+0x2c], esi
        mov dword ptr [edi+0x24], -5
        mov dword ptr [edi+0x28], -5
        mov dword ptr [edi+0x10], 20
        mov eax, [ebp-0xc]
        mov edx, [ebp-0x10]
        call %(addpt)#x
        mov dword ptr [ebp-0x14], 0
    ss_loop:
        mov ecx, [ebp-0x14]
        cmp ecx, %(shn)d
        jge ss_done
        mov eax, ecx
        and eax, 7
        lea edx, [ebx+jx]
        movsx eax, byte ptr [edx+eax]
        add eax, [ebp-0xc]
        push eax
        mov eax, ecx
        and eax, 7
        lea edx, [ebx+jy]
        movsx edx, byte ptr [edx+eax]
        add edx, [ebp-0x10]
        pop eax
        call %(addpt)#x
        inc dword ptr [ebp-0x14]
        jmp ss_loop
    ss_done:
        mov ecx, [ebp-4]
        mov [ebx+ecx*4+%(carr)#x], edi
    ss_out:
        mov esp, ebp
        pop ebp
        popad
        ret
    jx:
        .byte 3, 0xfe, 2, 0xfd, 1, 0xfd, 3, 0xff
    jy:
        .byte 0, 1, 0xff, 0, 1, 0, 0xff, 0

    /* ---- TCK: eax = te (Execute frame, [ebp-4] = te); replaces `call NextStrike` @0x40CB84 ---- */
    tck:
        call %(fam_eax)#x
        jne tk_van
        cmp dword ptr [eax+0x14], 0x34
        jne tk_van
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [eax+0x34]
        cmp ecx, [eax+0x28]
        jge tk_thrown
        cmp [ebx+%(pushed)#x], eax
        jne tk_np
        and dword ptr [ebx+%(pushed)#x], 0
    tk_np:
        /* cadence: one strike every CAD ticks ([te+0x30] = countdown; unused by category 5) */
        dec dword ptr [eax+0x30]
        jg tk_ret
        mov dword ptr [eax+0x30], %(cad)d
        pop ebx
        jmp %(nextstrike)#x
    tk_ret:
        pop ebx
        ret
    tk_thrown:
        cmp [ebx+%(pushed)#x], eax
        je tk_ret
        /* every strike thrown: wait until none of this spell's strikes is still flying (particles 0x1F and our
           carriers 0x2F do not count) - then every hit has resolved and the push can run mid-animation */
        push esi
        push ecx
        push edx
        mov edx, [ebx+%(map)#x]
        mov edx, [edx]
        mov edx, [edx+0x11c]
        mov ecx, [edx+8]
        mov edx, [edx+4]
    tk_scan:
        dec ecx
        js tk_none
        mov esi, [edx+ecx*4]
        test esi, esi
        jz tk_scan
        call %(fam_esi)#x
        jne tk_scan
        cmp byte ptr [esi+0x34], 0x1f
        je tk_scan
        cmp byte ptr [esi+0x34], 0x2f
        je tk_scan
        cmp byte ptr [esi+0xc], 0
        jne tk_scan
        pop edx
        pop ecx
        pop esi
        pop ebx
        ret
    tk_none:
        pop edx
        pop ecx
        pop esi
        mov [ebx+%(pushed)#x], eax
        pop ebx
        jmp push_phase
    tk_van:
        jmp %(nextstrike)#x

    """ % a


def zone5_src():
    """v5 zone 5: WAVE (eax = te; called by TCK every tick of a 212 token; returns eax = 1 while building up).
    Ticks 0..BU-1: NB Shockwave swirl particles per tick round the caster (vanilla 0x402E0C, radius growing) = the
    build-up; tick BU: the RELEASE - a ring ARC of kind-0x1F particles flying out from the caster along straight lines
    (MakeLinePath, RSTEP steps) to an ellipse (RR x RR*RY8/8) over the sector +-HALF deg round the caster -> target
    direction, one per degree, plus NTR slower trailing particles every 10 deg (Shockwave's own release recipe, 360 ->
    the sector).  Visual only: a private LCG (WRN), never the game's Random."""
    return """
    wave:
        pushad
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        cmp [ebx+%(wte)#x], esi
        je w_have
        mov [ebx+%(wte)#x], esi
        and dword ptr [ebx+%(wtk)#x], 0
        mov [ebx+%(wrn)#x], esi
    w_have:
        mov edi, [ebx+%(wtk)#x]
        cmp edi, %(bu)d
        jg w_ret0
        inc dword ptr [ebx+%(wtk)#x]
        push ebp
        mov ebp, esp
        sub esp, 0x60
        /* caster centre [ebp-4]/[ebp-8], target centre [ebp-0xc]/[ebp-0x10] (HXtoHP + 16) */
        movzx eax, word ptr [esi+0x1c]
        movzx edx, word ptr [esi+0x1e]
        lea ecx, [ebp-8]
        push ecx
        lea ecx, [ebp-4]
        call %(hxtohp)#x
        add dword ptr [ebp-4], 16
        add dword ptr [ebp-8], 16
        movzx eax, word ptr [esi+0x20]
        movzx edx, word ptr [esi+0x22]
        lea ecx, [ebp-0x10]
        push ecx
        lea ecx, [ebp-0xc]
        call %(hxtohp)#x
        add dword ptr [ebp-0xc], 16
        add dword ptr [ebp-0x10], 16
        cmp edi, %(bu)d
        je w_release
        /* ---- build-up: NB swirl particles ---- */
        mov dword ptr [ebp-0x14], 0
    w_b_loop:
        mov ecx, [ebp-0x14]
        cmp ecx, %(nb)d
        jge w_done
        call newp
        mov [ebp-0x18], eax
        mov eax, 360
        call rnd
        push eax
        push dword ptr [ebp-4]
        push dword ptr [ebp-8]
        mov eax, 2
        call rnd
        push eax
        mov eax, [ebp-0x18]
        add eax, 0x1c
        push eax
        mov eax, 6
        call rnd
        mov edx, edi
        shr edx, 1
        add edx, eax
        mov [ebp-0x1c], edx
        mov eax, [ebp-0x14]
        xor edx, edx
        mov ecx, 6
        div ecx
        imul ecx, edx, 60
        add ecx, edi
        mov eax, 10
        call rnd
        add eax, 10
        mov edx, [ebp-0x1c]
        call %(swirl)#x
        inc dword ptr [ebp-0x14]
        jmp w_b_loop
        /* ---- release: the sector arc ---- */
    w_release:
        mov eax, [ebp-0x10]
        sub eax, [ebp-8]
        mov [ebp-0x20], eax
        mov eax, [ebp-0xc]
        sub eax, [ebp-4]
        mov [ebp-0x24], eax
        fild dword ptr [ebp-0x20]
        fild dword ptr [ebp-0x24]
        fpatan
        fstp qword ptr [ebp-0x30]
        mov dword ptr [ebp-0x14], -%(half)d
    w_r_loop:
        cmp dword ptr [ebp-0x14], %(half)d
        jg w_done
        mov dword ptr [ebp-0x34], 180
        fild dword ptr [ebp-0x14]
        fldpi
        fmulp st(1), st(0)
        fild dword ptr [ebp-0x34]
        fdivp st(1), st(0)
        fadd qword ptr [ebp-0x30]
        fsincos
        mov eax, 5
        call rnd
        add eax, %(rr)d
        mov [ebp-0x38], eax
        fild dword ptr [ebp-0x38]
        fmulp st(1), st(0)
        fistp dword ptr [ebp-0x3c]
        mov eax, [ebp-0x38]
        imul eax, eax, %(ry8)d
        sar eax, 3
        mov [ebp-0x38], eax
        fild dword ptr [ebp-0x38]
        fmulp st(1), st(0)
        fistp dword ptr [ebp-0x40]
        mov eax, [ebp-0x3c]
        add eax, [ebp-4]
        mov [ebp-0x3c], eax
        mov eax, [ebp-0x40]
        add eax, [ebp-8]
        mov [ebp-0x40], eax
        mov dword ptr [ebp-0x44], 0
    w_t_loop:
        call newp
        mov [ebp-0x18], eax
        push dword ptr [ebp-0x40]
        mov eax, [ebp-0x44]
        imul eax, eax, 5
        add eax, %(rstep)d
        push eax
        mov eax, [ebp-0x18]
        add eax, 0x1c
        push eax
        mov eax, [ebp-4]
        mov edx, [ebp-8]
        mov ecx, [ebp-0x3c]
        call %(mkline)#x
        inc dword ptr [ebp-0x44]
        mov eax, [ebp-0x14]
        add eax, 1000
        xor edx, edx
        mov ecx, 10
        div ecx
        test edx, edx
        jnz w_r_next
        cmp dword ptr [ebp-0x44], %(ntr)d
        jle w_t_loop
    w_r_next:
        inc dword ptr [ebp-0x14]
        jmp w_r_loop
    w_done:
        mov esp, ebp
        pop ebp
        xor eax, eax
        cmp edi, %(bu)d
        setl al
        mov [esp+28], eax
        popad
        ret
    w_ret0:
        xor eax, eax
        mov [esp+28], eax
        popad
        ret

    newp:
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x1f
        call %(addfx)#x
        mov dword ptr [eax+0x14], 0x34
        mov dword ptr [eax+0x18], %(spell)d
        mov dword ptr [eax+0x2c], 0
        mov dword ptr [eax+0x24], 0
        ret

    rnd:
        push ecx
        push edx
        mov ecx, eax
        mov eax, [ebx+%(wrn)#x]
        imul eax, eax, 1103515245
        add eax, 12345
        mov [ebx+%(wrn)#x], eax
        shr eax, 16
        xor edx, edx
        div ecx
        mov eax, edx
        pop edx
        pop ecx
        ret
    """ % A


def build_zone5():
    """v6: the v5 wave is retired; v7: zone 5 holds the family helpers (fam_* / setid_*, see helpers_src)."""
    return HELPERS


def build_zone4(end1, hexof, addpt):
    src = re.sub(r"/\*.*?\*/", "", zone4_src(end1, hexof, addpt), flags=re.S)
    code = asm_pic(src, ZONE4)
    assert ZONE4 + len(code) <= ZONE4_END, hex(ZONE4 + len(code))
    where = {}
    lines = src.split("\n")
    for lab in ("tck", "shake"):
        k = next(i for i, l in enumerate(lines) if l.strip() == lab + ":")
        pre = "\n".join(lines[:k]) + "\n"
        where[lab] = ZONE4 + (len(asm_pic(pre, ZONE4)) if pre.strip() else 0)
    return bytes(code), where


def tck_state(d):
    b = bytes(d[TCK_SITE - V2F:TCK_SITE - V2F + 5])
    if b == TCK_ORIG: return "vanilla", None
    if b[0] == 0xE8:
        tgt = TCK_SITE + 5 + struct.unpack_from("<i", b, 1)[0]
        return ("ours" if ZONE4 <= tgt < ZONE4_END else "OTHER"), tgt
    return "OTHER", None


def build_zone3(prev_slt, end1):
    src = re.sub(r"/\*.*?\*/", "", zone3_src(prev_slt, end1), flags=re.S)
    blob = bytearray(struct.pack("<II", prev_slt, 0))
    code = asm_pic(src, ZONE3 + 8)
    blob += code
    assert ZONE3 + len(blob) <= ZONE3_END, hex(ZONE3 + len(blob))
    # label addresses: assemble prefixes (keystone has no symbol export) - locate each label by assembling up to it
    where = {}
    lines = src.split("\n")
    for lab in ("spr", "slt", "spn", "lnd", "end3", "hexof", "addpt"):
        k = next(i for i, l in enumerate(lines) if l.strip() == lab + ":")
        pre = "\n".join(lines[:k]) + "\n"
        where[lab] = ZONE3 + 8 + (len(asm_pic(pre, ZONE3 + 8)) if pre.strip() else 0)
    return bytes(blob), where


def site3_state(d, site, orig, how):
    n = len(orig); b = bytes(d[site - V2F:site - V2F + n])
    if b == orig: return "vanilla", None
    if b[0] in (0xE8, 0xE9) and b[5:] == b"\x90" * (n - 5):
        tgt = site + 5 + struct.unpack_from("<i", b, 1)[0]
        return ("ours" if ZONE3 <= tgt < ZONE3_END else "OTHER"), tgt
    return "OTHER", None


def slt_state(d):
    b = bytes(d[SLT_SITE - V2F:SLT_SITE - V2F + 7])
    if b[0] == 0xE9 and b[5:7] == b"\x90\x90":
        tgt = SLT_SITE + 5 + struct.unpack_from("<i", b, 1)[0]
        return ("ours" if ZONE3 <= tgt < ZONE3_END else "chain"), tgt
    return "OTHER", None


def build_zone(prev):
    blob = bytearray(struct.pack("<II", prev["REC"] or 0, prev["END"] or 0))
    where = {}
    for name, src in caves(prev):
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)                # keystone has no comment syntax for these
        va = ZONE + len(blob); where[name] = va; blob += asm_pic(src, va)
        while len(blob) % 4: blob += b"\x90"
    assert ZONE + len(blob) <= ZONE_END, hex(ZONE + len(blob))
    return bytes(blob), where


def site_state(d, site, orig, zone_lo, zone_hi):
    b = bytes(d[site - V2F:site - V2F + 6])
    if b == orig: return "vanilla", None
    if b[0] == 0xE8 and b[5] == 0x90:
        tgt = site + 5 + struct.unpack_from("<i", b, 1)[0]
        return ("ours" if zone_lo <= tgt < zone_hi else "chain"), tgt
    return "OTHER", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    path = a.dll; d = bytearray(open(path, "rb").read())
    R = relocs(d, BASE)
    zr = [hex(r) for r in R if ZONE <= r < ZONE_END or ZONE2 <= r < ZONE2_END or ZONE3 <= r < ZONE3_END or ZONE4 <= r < ZONE4_END or ZONE5 <= r < ZONE5_END]
    sr = ([hex(r) for s_ in SITES for r in R if s_[1] - 3 <= r < s_[1] + 6] + [hex(r) for r in R if SITE2[1] - 3 <= r < SITE2[1] + 7] +
          [hex(r) for s_ in SITES3 for r in R if s_[1] - 3 <= r < s_[1] + len(s_[2])] + [hex(r) for r in R if SLT_SITE - 3 <= r < SLT_SITE + 7] +
          [hex(r) for r in R if TCK_SITE - 3 <= r < TCK_SITE + 5])
    zone = bytes(d[ZONE - V2F:ZONE_END - V2F]); zone2 = bytes(d[ZONE2 - V2F:ZONE2_END - V2F]); zone3 = bytes(d[ZONE3 - V2F:ZONE3_END - V2F])
    zone4 = bytes(d[ZONE4 - V2F:ZONE4_END - V2F]); stk = tck_state(d); zone5 = bytes(d[ZONE5 - V2F:ZONE5_END - V2F])
    states = {}
    for tag, site, orig, _ in SITES:
        st, tgt = site_state(d, site, orig, ZONE, ZONE_END)
        if st == "chain" and tgt is not None and ZONE3 <= tgt < ZONE3_END: st = "ours3"      # v3: END -> END3
        states[tag] = (st, tgt)
    st2 = site2_state(d)
    st3 = {tag: site3_state(d, site, orig, how) for tag, site, orig, cave, how in SITES3}
    stl = slt_state(d)
    hdr = struct.unpack_from("<II", zone, 0); hdr2 = struct.unpack_from("<I", zone2, 0)[0]; hdr3 = struct.unpack_from("<I", zone3, 0)[0]
    print("AoWTCPCK gust sites", {k: (v[0], hex(v[1]) if v[1] else None) for k, v in states.items()},
          "BRE", (st2[0], hex(st2[1]) if st2[1] else None), "v3", {k: v[0] for k, v in st3.items()},
          "SLT", (stl[0], hex(stl[1]) if stl[1] else None), "TCK", stk[0],
          "| zones", ["zero" if z == bytes(len(z)) else "used" for z in (zone, zone2, zone3, zone4)],
          "| relocs zone", zr or "none", "sites", sr or "none")
    if zr or sr: print("ABORT: relocations in a zone / under a site"); return 1
    if (any(v[0] == "OTHER" for v in states.values()) or st2[0] == "OTHER" or any(v[0] == "OTHER" for v in st3.values())
            or stl[0] == "OTHER" or stk[0] == "OTHER"):
        print("ABORT: a site holds unknown code"); return 1
    any_ours = (any(v[0] in ("ours", "ours3") for v in states.values()) or st2[0] == "ours" or
                any(v[0] == "ours" for v in st3.values()) or stl[0] == "ours" or stk[0] == "ours")
    if a.revert:
        if not any_ours: print("already reverted"); return 0
        prev = {"REC": hdr[0], "END": hdr[1]}
        for tag, site, orig, _ in SITES:
            if states[tag][0] not in ("ours", "ours3"): continue
            if prev[tag]: d[site - V2F:site - V2F + 6] = b"\xE8" + struct.pack("<i", prev[tag] - (site + 5)) + b"\x90"
            else: d[site - V2F:site - V2F + 6] = orig
        if st2[0] == "ours":
            tag, site, orig, _ = SITE2
            if hdr2: d[site - V2F:site - V2F + 7] = b"\xE8" + struct.pack("<i", hdr2 - (site + 5)) + b"\x90\x90"
            else: d[site - V2F:site - V2F + 7] = orig
        for tag, site, orig, cave, how in SITES3:
            if st3[tag][0] == "ours": d[site - V2F:site - V2F + len(orig)] = orig
        if stl[0] == "ours":
            d[SLT_SITE - V2F:SLT_SITE - V2F + 5] = b"\xE9" + struct.pack("<i", hdr3 - (SLT_SITE + 5))
        if stk[0] == "ours": d[TCK_SITE - V2F:TCK_SITE - V2F + 5] = TCK_ORIG
        for lo, hi in ((ZONE, ZONE_END), (ZONE2, ZONE2_END), (ZONE3, ZONE3_END), (ZONE4, ZONE4_END), (ZONE5, ZONE5_END)): d[lo - V2F:hi - V2F] = bytes(hi - lo)
        open(path, "r+b").write(d); print("reverted", path); return 0
    # ---- zone 1 (REC / END) ----
    v1_on = all(v[0] in ("ours", "ours3") for v in states.values())
    if v1_on:
        prev = {"REC": hdr[0], "END": hdr[1]}
        blob, where = build_zone(prev)
        z1_same = zone[:len(blob)] == blob
        if not z1_same: print("older build of zone 1 detected -> rewriting it in place")
    else:
        if any(v[0] in ("ours", "ours3") for v in states.values()): print("ABORT: mixed state"); return 1
        if zone != bytes(len(zone)): print("ABORT: zone not free"); return 1
        prev = {tag: (states[tag][1] if states[tag][0] == "chain" else 0) for tag, *_ in SITES}
        blob, where = build_zone(prev); z1_same = False
    # ---- zone 4 (v4: per-tick driver, shake, mid-breath push) ----
    if stk[0] != "ours" and zone4 != bytes(len(zone4)): print("ABORT: zone 4 not free"); return 1
    _b3, _w3 = build_zone3(stl[1] if stl[0] == "chain" else hdr3, where["end"])
    blob4, w4 = build_zone4(where["end"], _w3["hexof"], _w3["addpt"])
    z4_same = stk[0] == "ours" and zone4[:len(blob4)] == blob4
    # ---- zone 5 (v5: the Shockwave-style wave) - owned together with zone 4 (TCK calls it)
    blob5 = build_zone5()
    if zone5 != bytes(len(zone5)) and not (stk[0] == "ours" and zone5[:len(blob5)] == blob5):
        if stk[0] != "ours": print("ABORT: zone 5 not free"); return 1
    z5_same = zone5[:len(blob5)] == blob5 and zone5[len(blob5):] == bytes(len(zone5) - len(blob5))
    if stk[0] == "ours" and not z5_same: print("zone 5 differs -> rewriting it (v7: Gust / Crashing Wave family helpers)")
    # ---- zone 2 (BRE, v2) ----
    if st2[0] == "ours":
        prev2 = hdr2
    else:
        if zone2 != bytes(len(zone2)): print("ABORT: zone 2 not free"); return 1
        prev2 = st2[1] if st2[0] == "chain" else 0
        if v1_on: print("v1 build found (no breath recorder) -> upgrading to v2")
    blob2, bre = build_zone2(prev2, w4["shake"])
    z2_same = st2[0] == "ours" and zone2[:len(blob2)] == blob2
    # ---- zone 3 (v3: particles / animation / slot / spin / landing) ----
    v3_on = stl[0] == "ours" and all(v[0] == "ours" for v in st3.values()) and states["END"][0] == "ours3"
    if v3_on:
        prev_slt = hdr3
    else:
        if stl[0] == "ours" or any(v[0] == "ours" for v in st3.values()): print("ABORT: mixed v3 state"); return 1
        if zone3 != bytes(len(zone3)): print("ABORT: zone 3 not free"); return 1
        if stl[0] != "chain": print("ABORT: the slot site is not a jmp chain head"); return 1
        prev_slt = stl[1]
        if v1_on: print("v2 build found -> upgrading to v3 (forward shockwave particles, shake + hop)")
    blob3, w3 = build_zone3(prev_slt, where["end"])
    z3_same = v3_on and zone3[:len(blob3)] == blob3
    if v3_on and stk[0] != "ours": print("v3 build found -> upgrading to v4 (longer breath, shake from the first hit, push mid-breath)")
    if v1_on and z1_same and z2_same and z3_same and z4_same and z5_same:
        if a.dis: dis(d)
        print("already applied"); return 0
    print("zone %d B: %s; prev %s | zone2 %d B: bre %#x prev %#x | zone3 %d B: %s prev slot %#x" % (
          len(blob), {k: hex(v) for k, v in where.items()}, {k: hex(v) for k, v in prev.items()}, len(blob2), bre, prev2,
          len(blob3), {k: hex(v) for k, v in w3.items()}, prev_slt) + " | zone4 %d B: %s" % (len(blob4), {k: hex(v) for k, v in w4.items()}) + " | zone5 %d B" % len(blob5))
    if not (a.apply): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(path) == os.path.abspath(DLL):
        bak = bak_path(DLL, ".bak_gust")
        if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(blob)] = blob
    for tag, site, orig, cave in SITES:
        tgt = w3["end3"] if tag == "END" else where[cave]
        d[site - V2F:site - V2F + 6] = b"\xE8" + struct.pack("<i", tgt - (site + 5)) + b"\x90"
    d[ZONE2 - V2F:ZONE2_END - V2F] = bytes(ZONE2_END - ZONE2); d[ZONE2 - V2F:ZONE2 - V2F + len(blob2)] = blob2
    tag, site, orig, _ = SITE2
    d[site - V2F:site - V2F + 7] = b"\xE8" + struct.pack("<i", bre - (site + 5)) + b"\x90\x90"
    d[ZONE3 - V2F:ZONE3_END - V2F] = bytes(ZONE3_END - ZONE3); d[ZONE3 - V2F:ZONE3 - V2F + len(blob3)] = blob3
    for tag, site, orig, cave, how in SITES3:
        op = b"\xE8" if how == "call" else b"\xE9"
        d[site - V2F:site - V2F + len(orig)] = op + struct.pack("<i", w3[cave] - (site + 5)) + b"\x90" * (len(orig) - 5)
    d[SLT_SITE - V2F:SLT_SITE - V2F + 5] = b"\xE9" + struct.pack("<i", w3["slt"] - (SLT_SITE + 5))
    d[ZONE4 - V2F:ZONE4_END - V2F] = bytes(ZONE4_END - ZONE4); d[ZONE4 - V2F:ZONE4 - V2F + len(blob4)] = blob4
    d[ZONE5 - V2F:ZONE5_END - V2F] = bytes(ZONE5_END - ZONE5); d[ZONE5 - V2F:ZONE5 - V2F + len(blob5)] = blob5
    d[TCK_SITE - V2F:TCK_SITE - V2F + 5] = b"\xE8" + struct.pack("<i", w4["tck"] - (TCK_SITE + 5))
    open(path, "r+b").write(d); print("written", path)
    if a.dis: dis(d)
    return 0


def dis(d):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for i in md.disasm(bytes(d[ZONE - V2F:ZONE_END - V2F]), ZONE):
        if i.address >= ZONE + 8: print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
    print("---- zone 2 (BRE)")
    for i in md.disasm(bytes(d[ZONE2 + 4 - V2F:ZONE2_END - V2F]), ZONE2 + 4):
        print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
        if i.mnemonic == "ret": break
    print("---- zone 4 (v4)")
    for i in md.disasm(bytes(d[ZONE4 - V2F:ZONE4_END - V2F]), ZONE4):
        if i.bytes == b"\x00\x00": break
        print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
    print("---- zone 5 (v5 wave)")
    for i in md.disasm(bytes(d[ZONE5 - V2F:ZONE5_END - V2F]), ZONE5):
        if i.bytes == b"\x00\x00": break
        print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))
    print("---- zone 3 (v3)")
    for i in md.disasm(bytes(d[ZONE3 + 8 - V2F:ZONE3_END - V2F]), ZONE3 + 8):
        if i.bytes == b"\x00\x00": break
        print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))


if __name__ == "__main__":
    sys.exit(main())
