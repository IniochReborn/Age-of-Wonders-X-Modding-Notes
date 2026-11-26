#!/usr/bin/env python3
r"""
SMOKESCREEN (spell 225, Fire tier 2, 2026-10-17) - the SMOKE HEXES on the combat map.  AoWTCPCK.dll.
Needs patch_smokescreen_v1.py applied first (AoWEPACK export sm_sync @0x5587A820).  The field half is a copy of
patch_tc_sanctify_field_v1.py's consecrated hex (TCombatFire VMT clone, 3-turn countdown, own Show, PlaceOnMap
sync); the cast is the Mend Walls v2 recipe (no strikes, everything done once at the NextStrike gate).

Spell: TOoze clone (pipeline, pfs donor 134, tc_type 0x0A) aliased 225 -> 0x7C (patch_tc_spell_alias_v1) = the
19-hex Ooze preview + long range (pipeline poke 0x39 = 12) + the hail TE; ATK / DMG 0 -> fast combat and the AI's
damage scoring see a harmless spell.
Behaviour:
  gate  both `call NextStrike` sites 0x40B6F1 (phase 0) / 0x40CBE7 (phase 1), chained IN FRONT of whatever they call
        (decoded at apply time, kept at zone+0 for an exact revert; today the Mend Walls gate 0x448460).  eax = te.
        te spell [te+0x18] == 225 and strike count [te+0x28] != 0 -> once: [te+0x28] := 0 (no strikes; phase 1 ends
        the te as soon as the map effect list is empty), the spell's cast sound (cue 0, TSFXLibrary.Play, only when
        sound is on [map+0x129] - a hail-class cast sound is otherwise played by the first strike), the view centred
        on the target hex (map VMT+0xBC, as NextStrike does before every vanilla strike), then for HN 0..18 around the
        target [te+0x20]/[te+0x22] (HSEngine.CenterHNtoHX, in-level bounds [level+0xC]/[level+0x10] - GetField has no
        bounds check):
          the hex's SMOKE HS is created (or an existing one refreshed: owner := the turn player [map+0xED], 3 turns)
          and placed (THSMap.PlaceHX, level 0 - combat maps are single-level; freed if PlaceHX refuses);
          a kind-0x26 effect at the hex centre (HXtoHP + 16/16; [fx+0x14] = 0x34, [fx+0x18] = 225, marker 0 -> the
          vanilla slot pick = gfx SLOT 1 = the smoke burst).  No RNG anywhere -> MP-identical.
        Returns without calling NextStrike.  Every other te / pass -> the previous chain target.
  SMOKE HS = a runtime CLONE of the TCombatFire VMT (VMT-0x40..+0x110, all 68 slots) in AoWEPACK's BSS page slack at
        CLONE_EP (0x558FAB00..0x558FAC50, VMT ptr +0x40; referenced by nothing else - Gravity 0x558FA400..550,
        defender scratch ..0x558FAA00, los flags 0x558FAA40/41, Sanctify 0x558FAD00..E50), reached through the
        TCombatUnit.SetUnit import-slot delta; instance size 0x1C (+0x14 owner, +0x19 turns left).  Slots:
          +0x24 ClassID      -> 0x22010F (unused anywhere; 0x22010B oil / 0x22010C gravity / 0x22010E sanctify)
          +0x44 MsgProc      -> inherited TEObject.MsgProc, then the countdown: at the start of each of the CASTER's
                                turns (broadcast 0x20021001 with [map+0xED] == owner, not while [map+0x3C] & 2) turns -=
                                1; at 0 the hex expires (its unit loses 0xC6) and the HS frees itself.  Cast in T0 ->
                                active through the enemy turns and the caster's T1, T2 -> gone when T3 begins.
          +0x64 / +0x8C / +0xD0 -> TCOozeHS's GetLevel / GetShowPriority / CanMoveOn (a ground decal: no movement or
                                line-of-sight effect)
          +0xA8 Show         -> spell 225's own image list [spell+0x2C] slot FIELD_SLOT (3), frame by time
                                (TImageSequence.GetFrameIndex(tick, phase = self>>2) - every hex churns out of step),
                                drawn at HXtoHP(hex) - view + the sequence offsets
          +0xAC PlaceOnMap   -> THexagonSprite.PlaceOnMap, then sm_sync(the unit already on the hex, 1)
        A unit that ENDS a move on / leaves a smoke hex is synced by the AoWEPACK pom hook.
Zone 0x44C000..0x44C800 (CODE, zero, reloc-free).  PIC call/pop delta for every in-image absolute (TCPCK rebases).
Thunks import-table checked.  Dry-run default; --apply / --revert / --dis / --dll <copy> [--ep <AoWEPACK copy>].
Backup <game>\backup\AoWTCPCK.dll.bak_smokescreen (pre-v1); the v2 upgrade backs up the v1 state as .bak_smokescreen2.
v2 2026-10-17 (user: "gfx looks meh - I wanted a variant of the CLOUD OF ASHES smoke"): like the vanilla Cloud of
  Ashes (ONE image over the whole area: Misc_Obj.ILB 40, drawMode 1026 multiply), the smoke is now one bank drawn
  only by the CENTRE hex's smoke HS: plc flags the HN-0 hex ([hs+0x1A] := 1, on create and on refresh; a hex that was
  a centre once keeps its flag) and Show returns at once when the flag is clear.  Slot 3 = the 272x208 bank (DualDF
  5670-5717, 48 frames x 3 ticks), slot 1 = the per-hex burst (5650-5669).  Gameplay (0xC6 on every smoke hex, the
  3-turn countdown) unchanged.  Caveats: the bank is culled with its centre hex (scrolled so the centre hex is well
  off screen, the whole bank goes); the flag byte is not streamed, so smoke restored from a combat save shows no bank.
v3 2026-10-17 (user: "a distinct HEX-shaped gfx at the beginning looks janky"; "units and map objects aren't covered
  by the smoke - fix that, keep their race orb + HP bar above the cloud; walls and houses float above the smoke"):
  * the hexagon = the 19 per-hex cast puffs (slot 1 kind-0x26 effects): 19 dark gaussians on the 2-ring hex lattice
    add up to a hard-edged hexagon of darkness over the fresh bank.  plc no longer spawns them; instead the bank
    itself GROWS IN: its centre HS keeps a start frame (table at W+0x10, set by plc on creation, else on the first
    draw), Show picks frame k = (frame counter - start) / 3 by hand (no TImageSequence state): k < n4 -> slot 4 (the
    INTRO = loop frames 0..n4-1 under a growing, wobbly round mask + density ramp, the last one == loop frame n4-1),
    else slot 3 frame k mod n3 -> seamless hand-over.
  * LAYERING: TAoWCombatMap.DrawDynamicScene's `call THSMap.DrawDynamicScene` (0x41BFCA) -> zone-2 cave dds.  The
    dynamic list [map+0x20] (built by UpdateDynamicScene before this) is scanned for live bank HS (clone VMT, flag
    +0x1A); none -> plain tail-jump (vanilla).  Otherwise: defer := 1, the vanilla dynamic draw runs (the bank's own
    Show returns at once unless post-pass; every TTacticalCombatUnitHS.Show is cut at its OVERLAY block 0x4228A8 -
    the team/race orb + HP bar - and the overlay's inputs (self, x, y, race [ebp-3C], target) are recorded instead,
    jump to the block's end 0x422B00), defer := 0, then the POST PASS: (1) every bank (post := 1, its Show); (2) walls,
    gates and combat structures (TCityWall / TCityWallDoor / TWorkshop / TTownhall / THouse / TMainStructure, by VMT)
    from the static [map+0x1C] then dynamic list whose anchor hex is within 5 of a bank centre, re-shown above the
    smoke; (3) recorded units standing on an INTACT wall/gate hex near a bank, re-shown whole (raised like the wall);
    (4) every recorded overlay replayed: a fabricated Show frame ([ebp-4/-8/-C/-3C], [ebp+8]) jumps into 0x4228A8 with
    replay := 1, and the hook at 0x422B00 unwinds that frame back to dds.  Rocks, trees, corpses, units = covered.
    Writable state: AoWEPACK .idata RW page slack W = 0x5590B600 (+0 defer, +1 replay, +2 post, +4 overlay count,
    +8 start-table cursor, +0x10 8 x (hs, start), +0x60 64 x 20-byte overlay records; ends 0x5590BB60), reached
    through the SetUnit import-slot delta.  Zone 2 = 0x449400..0x449C00 (CODE, zero, reloc-free), header +0 = the
    previous DDS call target, +4 / +0x10 = the original OVL / END bytes (exact revert).
v3.1 2026-10-17 (user: "when a building/wall has smokescreen, the bottom half of its hex should have smoke on it -
  seeing the base is weird, I want the TOPS to protrude"): the post-pass re-shows of walls / gates / structures (2)
  and of units on walls (3) go through cshow: if the object's hex owns a smoke HS (field VMT+0x80 FindOwnedChild
  0x22010F) it is re-shown CLIPPED above the smoke line - the target lock descriptor's clip rect (+0x10 / +0x14 /
  +0x18 / +0x1C = left / top / right / bottom, set by Gfxepack's Lock 0x5500C7B4 and honoured by its blitters) is
  narrowed per COLW (8)-px column from hex-centre x - SPAN (96) to + SPAN (columns aligned to MAP x), each column's
  bottom = the hex-centre row (HXtoHP + 16/16, CUT 0) + WAVE[(map x / 8 + tick / 6) & 15] (+-2 px, a lapping line,
  wavelength 128 px, ~2.8 s per cycle); the two remainders outside the span are cut flat at the line; every rect is
  clamped to the original clip and the original clip is restored afterwards.  The bank (drawn first) therefore stays
  over the structure's base pixels (no second multiply anywhere -> no double darkening).  Hex not under smoke ->
  the plain Show as in v3.  The orb / HP-bar replay (4) stays last and unclipped.  Zone 2 grows to 1543 B (wtbl,
  cshow).  In-place upgrade from v3 (zone 2 rewritten, sites unchanged); backup .bak_smokescreen31 = the v3 state.
v3.3 2026-10-17 (user: 'half-smoke edges are bright GREEN'; 'earth walls still get covered'): (1) the blend assumed RGB565 -
  the surface is 555 on this setup (lock descriptor +0x2C = R mask 0x7C00, +0x28 PFID 0x55509310) -> 565 masks on 555
  data saturate G (verified: G=31 artefacts).  c_fclamp now reads the R mask: 0xF800 -> 0x07E0F81F, 0x7C00 ->
  0x03E07C1F (kept in [ebp-0x6C]), anything else -> the hard cut (no blend).  (2) underground earth walls ('Wall'
  resource, TCOMBAT\BASE_HEX\H_EARTH.ILB, 36 images 44x68) are IL-terrain tiles drawn through the resource's
  SEQUENCE LIST ([res+0x24] != 0) - v3.2's iltall rejected every sequence tile.  iltall now also measures sequence
  tiles (seqlist +4 items / +8 count, item [obj+0x14] -> part +0x10 library -> image 0 height) and TCombatFixedILTerrain
  (VMT 0x404644) is tested like TCombatILTerrain.  Live check tool: combat_objects_probe.py (read-only).
v3.2 2026-10-17 (user: "make the edges of the half smoke smoother, like the outer edges of the main smoke; also apply
  the half-smoke effect to underground pillars (kind of like earth walls)"):
  * SOFT EDGE (true blend, pixel-exact): per COLW column cshow first SAVES the FEATHER (16) rows just above the column's
    smoke line straight from the locked target surface (lock descriptor +0x20 bits, +0xC pitch, +8 bpp - 16 bpp only;
    Gfxepack TSurface.LockEx 0x5500C7B4) into a 256-byte buffer (AoWEPACK .idata page slack BUF_EP 0x5590BB80, via the
    SetUnit import-slot delta), re-shows the structure clipped to [clip top, line) as before, then BLENDS the band back
    565-wise: out = (drawn * (32 - w) + saved * w) >> 5 with w = FWT[row] (smoothstep 0 at the top -> 32 at the line =
    the smoked share).  Pixels the structure did not touch are left alone (saved == drawn), so the soft edge sits only
    on the structure itself - no halo, no double multiply, no dither (row dithering was tried and read as stripes at
    the 3x DPI upscale).  The flat outer remainders beyond +-SPAN keep the hard cut; non-16-bpp targets fall back to it.
  * PILLARS: the post pass also re-shows (through cshow, so half-smoked) TCombatObstacle (VMT 0x431BB8; comb_res
    resource class 0x22052B = only the dungeon / ruin battlefield 'Wall' and 'Pillar' pieces), their tall tops
    TCombatObstacleOverlay (VMT 0x431A20, drawn by the obstacle at +8 -> ofld takes the obstacle's hex) and every
    TCombatILTerrain tile (exact VMT 0x404378 - the base-hex tiles) whose current image is taller than TALLH 44 px:
    the H_EARTH earth-wall columns of underground battlefields (56..68 px; floors / rubble / roads are 32) - iltall:
    resource +0x20 library .Get(tile +0x14) -> TLibraryImage height +0x24.  Rocks, stones, trees, bones (TCombatTerrain
    0x220167 decorations) stay covered.  Zone 2 grows to 2129 B (ZONE2_END 0x449E00; 0x449C00..0x449E00 zero, reloc-free).
  In-place upgrade from v3.1 (zone 2 rewritten, sites unchanged); backup .bak_smokescreen32 = the v3.1 state.
v3.4 2026-10-17 (user, underground battle: earth walls still covered; the floor hexes in FRONT of the walls lost half their smoke;
  'all earth walls contain pure black'): the earth walls are NOT IL-terrain - they are the base hexes (TCombatHexagon, static) of
  the comb_res 'Wall' resource = TCOMBAT\BASE_HEX\H_EARTH.ILB: black hex tops (ids 40-44, 48x32) + brown cliff faces hanging
  BELOW the hex (ids 0-27, 86x107, content to ~88-107 px under the hex's top-left).  (1) TCombatHexagon (exact VMT 0x40340C) whose
  base library image 0 is >= 100 px tall (ehtest) is re-shown after the bank within NEAR_E 3 hexes, CLIPPED at HXtoHP.y + EARTH_CUT
  64 (+ wave, soft blended): the black top and the upper face protrude, ~24 px of the face base stays smoked - no smoke-tile test
  (earth hexes never carry one).  (2) The half-smoked floors were the 75x91 CITY tiles (TCOMBAT\CITY\c_tile.ILB, TCombatILTerrain)
  that v3.3's TALLH 44 let through: TALLH -> 100 (only H_EARTH-sized IL tiles, which take the earth path too).  cshow gains a
  stack mode argument (0 = structure: smoke-tile test + hex-centre line; 1 = earth) and returns with ret 4.
v3.5 2026-10-17 (live listing in an underground battle: v3.4's ehtest found 0 earth hexes - every TCombatHexagon there is a
  48x32 H_DR floor): the earth walls are STATIC TIsometricCombatHexagon objects (exact VMT 0x43386C, resource
  TIsometricCombatHexagonResource, seq item-0 library = H_EARTH image 0 86x107).  They draw through ShowDynamic (VMT+0x124,
  TCPCK override 0x433B34 = HSEPack TUpperIsometricHexagon.ShowDynamic: black top 0x28+(flags>>6) at (HP.x-8, HP.y) - view,
  cliff faces 0x12.. at y-0x26-..; their plain Show +0xA8 draws nothing while [obj+0x10] != 0).  The post pass now also
  matches ISO_VMT (ehtest-confirmed) within NEAR_E and re-draws it through cshow MODE 2 = slot +0x124 (cshow keeps the slot
  in [ebp-0x70]: 0xA8 for modes 0/1) with line = HP.y - view + EARTH_CUT_ISO 40 (+ wave, soft blend).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll"); DEFAULT_EP = game_file("AoWEPACK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x44C000, 0x44C800
HDR = 0x10                        # zone header: +0 previous gate call target
SPELL_ID, FIELD_CLASSID, UNITHS_CLASSID, FX_STRIKE = 225, 0x22010F, 0x220104, 0x34
FIELD_SLOT, TURNS, NHEX = 3, 3, 19
INTRO_SLOT = 4                    # v3: the bank's grow-in (DualDF 5718..5737), then slot 3 loops on
ZONE2, ZONE2_END = 0x449400, 0x449E00   # v3.2: + 0x449C00..0x449E00 (zero, reloc-free; 0x449E00 = the Oil Spring cue0 cave)
HDR2 = 0x20                       # zone-2 header: +0 previous DDS call target, +4 OVL original bytes, +0x10 END original bytes
DDS_SITE, DDS_VANILLA = 0x41BFCA, 0x40229C           # TAoWCombatMap.DrawDynamicScene: call THSMap.DrawDynamicScene (thunk)
OVL_SITE, OVL_ORIG = 0x4228A8, bytes.fromhex("8b45fc8b10")   # TTacticalCombatUnitHS.Show: overlay block (orb + HP bar)
END_SITE, END_ORIG = 0x422B00, bytes.fromhex("33c05a5959")   # ... its end (xor eax,eax / pop edx / pop ecx / pop ecx)
W_EP, W_END = 0x5590B600, 0x5590BB60                    # AoWEPACK .idata RW page slack (beyond raw data, zero at load)
NOVL = 64
VMT_TALL = (0x405008, 0x4052AC, 0x4334E0, 0x4341F8, 0x434584, 0x435310)   # TCityWall, TCityWallDoor, TWorkshop, TTownhall, THouse, TMainStructure
NEAR = 5
HCX, HCY = 16, 16                 # v3.1: HXtoHP + 16/16 = the hex centre (as the Mend Walls / Wall of Flames effects)
CUT = 0                           # v3.1: smoke line = the hex centre row (+ the wave) -> the lower half of a structure's hex stays smoked
SPAN, COLW = 96, 8                # v3.1: clipped columns cx-SPAN..cx+SPAN, COLW px wide (outer remainders cut flat at the line)
WAVE = (0, 1, 1, 2, 2, 2, 1, 1, 0, -1, -1, -2, -2, -2, -1, -1)   # v3.1: the smoke line laps +-2 px (phase = map x / COLW + tick / 6)
FEATHER = 16                      # v3.2: soft edge - the FEATHER rows above each column's smoke line are BLENDED pixel by pixel
FWT = tuple(int(round(32 * (lambda u: u * u * (3 - 2 * u))((i + 0.5) / FEATHER))) for i in range(FEATHER))   # smoked share 0..32, top -> line
BUF_EP = 0x5590BB80               # v3.2: AoWEPACK .idata RW page slack: the band save buffer (FEATHER x COLW 16-bit pixels, after W)
FILTER_VMT = 0x404644              # v3.3: TCombatFixedILTerrain (subclass of TCombatILTerrain) - also height-tested
OVL_VMT, OBST_VMT, ILTER_VMT = 0x431A20, 0x431BB8, 0x404378   # v3.2: TCombatObstacleOverlay / TCombatObstacle / TCombatILTerrain (exact)
TALLH = 100                       # v3.4: was 44 - the 75x91 CITY tiles (TCOMBAT\CITY\c_tile.ILB) qualified and their floors got half smoke; only H_EARTH (86x107) now
EH_VMT, EH_H = 0x40340C, 100       # v3.4: TCombatHexagon (exact VMT) whose base-hex resource library image 0 is >= 100 px tall = the H_EARTH 'Wall'
                                  #       base hex (the underground earth walls: black hex tops 40-44 + 86x107 cliff faces 0-27; floors are 48x32)
EARTH_CUT = 64                    # v3.4: earth-wall smoke line = HXtoHP.y + EARTH_CUT (+ wave): the cliff faces end ~88..107 px below their
                                  #       hex's top-left, so ~24 px of the face base stays smoked; the black top and the upper face protrude
ISO_VMT, ISO_SLOT = 0x43386C, 0x124   # v3.5: TIsometricCombatHexagon (exact VMT) = the REAL underground earth walls (live listing
                                  #       10/17); drawn by ShowDynamic = VMT+0x124 (0x433B34: black H_EARTH top 40-43 at HP-8/HP, cliff faces
                                  #       0x12.. at y-0x26-..: content ~-35..+50 px around the hex top-left)
EARTH_CUT_ISO = 28                # v3.5: iso earth smoke line = HXtoHP.y - view + 40 (+ wave): the black top + faces protrude, the face
                                  #       bases (ending +34..+50) keep their lowest few px in smoke
NEAR_E = 3                        # v3.4: earth hexes are re-shown only within 3 hexes of a bank centre (cost: ~26 clipped draws each)
TURN_MSG = 0x20021001
SETUNIT_SLOT, SETUNIT_VA = 0x46E858, 0x55725194
EP_SYNC = 0x5587A820              # patch_smokescreen_v1.py export: jmp sm_sync (eax = TUnit, dl = on)
EP_ZONE = (0x5587A800, 0x5587B000)
CLONE_EP, VMT_LO, VMT_HI = 0x5590B240, 0x40, 0x110   # 10/17 MOVED: AoWEPACK .idata RW page slack 0x5590B200..0x5590B350 (beyond raw data, zero at load) - 0x558FAB00 collided with Wall of Flames' TCombatFire clone
MAPLIST, TICKOBJ, HSSET, XYZCLS = 0x469420, 0x46E8D4, 0x46E8D0, 0x46EB24
FIRE_CELL, OOZE_CELL, FIRE_CREATE, ADDEFFECT = 0x406AE4, 0x41275C, 0x406F68, 0x41C6EC
(T_MSGPROC, T_FREE, T_PLACEON, T_GETSPELL, T_GETSEQ, T_FRAMEIDX, T_LIBGET, T_HXTOHP, T_PLACEHX, T_GETLEVEL, T_GETFIELD,
 T_HN2HX, T_SNDPLAY, T_CREATE, T_XYZADD) = (0x401404, 0x401050, 0x401C5C, 0x4029B4, 0x4016E4, 0x4016D4, 0x4016F4, 0x4022BC,
                                         0x402264, 0x401E64, 0x401E54, 0x4022AC, 0x4022F4, 0x401040, 0x402DE4)
THUNKS = {T_MSGPROC: "TEObject.MsgProc", T_FREE: "TObject.Free", T_PLACEON: "THexagonSprite.PlaceOnMap",
          T_GETSPELL: "TSpellControl.GetSpell", T_GETSEQ: "GetImageSequence", T_FRAMEIDX: "TImageSequence.GetFrameIndex",
          T_LIBGET: "TCustomImageLibrary.Get", T_HXTOHP: "HSEngine.HXtoHP", T_PLACEHX: "THSMap.PlaceHX",
          T_GETLEVEL: "TMapContainer.GetMapLevel", T_GETFIELD: "TMapLevel.GetField", T_HN2HX: "CenterHNtoHX",
          T_SNDPLAY: "TSFXLibrary.Play", T_CREATE: "TObject.Create", T_XYZADD: "TXYZList.Add"}
GATE_SITES = [0x40B6F1, 0x40CBE7]  # `call <NextStrike chain>`

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    """PIC delta idiom `call $D / pop R / sub R, $D` (R = ebx, esi, edi): every anchor patched with its own VA."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("ebx", "esi", "edi"): s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0]); n = 0
    for pop, sub in ((0x5B, 0xEB), (0x5E, 0xEE), (0x5F, 0xEF)):
        anchor = bytes([0xE8, 0, 0, 0, 0, pop, 0x81, sub]) + b"\xff\xff\xff\x7f"
        k = b.find(anchor)
        while k >= 0:
            struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build(prev, w2):
    out = bytearray(HDR); where = {}
    struct.pack_into("<I", out, 0, prev)
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    P = {"slot": SETUNIT_SLOT, "suva": SETUNIT_VA, "sync": EP_SYNC, "clone": CLONE_EP, "maplist": MAPLIST, "hsset": HSSET,
         "tick": TICKOBJ, "xyz": XYZCLS, "fire": FIRE_CELL, "ooze": OOZE_CELL, "create": FIRE_CREATE, "addfx": ADDEFFECT,
         "msgproc": T_MSGPROC, "free": T_FREE, "placeon": T_PLACEON, "getspell": T_GETSPELL, "getseq": T_GETSEQ,
         "frameidx": T_FRAMEIDX, "libget": T_LIBGET, "hxtohp": T_HXTOHP, "placehx": T_PLACEHX, "getlevel": T_GETLEVEL,
         "getfield": T_GETFIELD, "hn2hx": T_HN2HX, "sndplay": T_SNDPLAY, "ocreate": T_CREATE, "xyzadd": T_XYZADD,
         "id": SPELL_ID, "fcls": FIELD_CLASSID, "ucls": UNITHS_CLASSID, "kind": FX_STRIKE, "fslot": FIELD_SLOT,
         "turns": TURNS, "nhex": NHEX, "turn": TURN_MSG, "lo": VMT_LO, "ndw": (VMT_LO + VMT_HI) // 4, "prev": prev,
         "w": W_EP, "islot": INTRO_SLOT, "tsget": w2["tsget"], "tsset": w2["tsset"]}
    place("classid", "mov eax, %(fcls)#x\n ret" % P)
    # unit_sync(eax = field, dl = on): the unit standing on the field (if any) -> AoWEPACK sm_sync; preserves all regs
    place("usync", """
        pushal
        mov bl, dl
        test eax, eax
        jz u_out
        mov edx, %(ucls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz u_out
        mov eax, [eax + 0x1c]
        test eax, eax
        jz u_out
        mov eax, [eax + 0x4c]
        test eax, eax
        jz u_out
        push eax
        call $D
        pop esi
        sub esi, $D
        mov ecx, [esi + %(slot)#x]
        sub ecx, %(suva)#x
        add ecx, %(sync)#x
        pop eax
        mov dl, bl
        call ecx
    u_out:
        popal
        ret
    """ % P)
    place("placeon", """
        push esi
        mov esi, eax
        call %(placeon)#x
        push eax
        mov eax, [esi + 4]
        mov dl, 1
        call %(usync)#x
        pop eax
        pop esi
        ret
    """ % dict(P, usync=where["usync"]))
    # MsgProc(eax = self, edx = msg, ecx): inherited; on the turn broadcast count the caster's turns down
    place("msg", """
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        call %(msgproc)#x
        cmp dword ptr [edi], %(turn)#x
        jne m_out
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        test byte ptr [eax + 0x3c], 2
        jnz m_out
        movsx eax, byte ptr [eax + 0xed]
        cmp eax, [esi + 0x14]
        jne m_out
        dec byte ptr [esi + 0x19]
        jg m_out
        mov eax, [esi + 4]
        xor edx, edx
        call %(usync)#x
        mov eax, esi
        call %(free)#x
    m_out:
        pop edi
        pop esi
        pop ebx
        ret
    """ % dict(P, usync=where["usync"]))
    # Show(eax = self, edx = dx, ecx = dy, [ebp+8] = surface; ret 4).  v3: only the CENTRE hex's HS draws, and only in
    # the dds post pass (W+2); frame k = (frame counter - start) / 3 picked by hand: k < n(slot 4) -> the intro frame k,
    # else slot 3 frame k mod n3 (the intro's last frame == loop frame n4-1 -> seamless)
    place("show", """
        push ebp
        mov ebp, esp
        add esp, -0x24
        push ebx
        push esi
        push edi
        mov [ebp - 0xc], ecx
        mov [ebp - 8], edx
        mov [ebp - 4], eax
        cmp byte ptr [eax + 0x1a], 0
        je s_fin
        call $D
        pop esi
        sub esi, $D
        mov ecx, [esi + %(slot)#x]
        sub ecx, %(suva)#x
        add ecx, %(w)#x
        cmp byte ptr [ecx + 2], 0
        je s_fin
        lea eax, [ebp - 0x1c]
        push eax
        lea ecx, [ebp - 0x18]
        mov eax, [ebp - 4]
        mov eax, [eax + 4]
        movsx edx, byte ptr [eax + 0x11]
        movsx eax, byte ptr [eax + 0x10]
        call %(hxtohp)#x
        mov eax, [ebp - 0x18]
        sub eax, [ebp - 8]
        mov [ebp - 8], eax
        mov eax, [ebp - 0x1c]
        sub eax, [ebp - 0xc]
        mov [ebp - 0xc], eax
        mov eax, [esi + %(hsset)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz s_fin
        mov eax, [eax + 0x2c]
        test eax, eax
        jz s_fin
        mov [ebp - 0x20], eax
        mov eax, [ebp - 4]
        call %(tsget)#x
        mov edx, [esi + %(tick)#x]
        mov edx, [edx]
        mov edx, [edx + 0x40]
        sub edx, eax
        mov eax, edx
        xor edx, edx
        mov ecx, 3
        div ecx
        mov [ebp - 0x24], eax
        mov eax, [ebp - 0x20]
        mov edx, %(islot)d
        call %(getseq)#x
        test eax, eax
        jz s_loop
        mov ecx, [eax + 0x1c]
        test ecx, ecx
        jz s_loop
        mov edx, [ebp - 0x24]
        cmp edx, [ecx + 8]
        jae s_loop
        mov [ebp - 0x10], eax
        jmp s_draw
    s_loop:
        mov eax, [ebp - 0x20]
        mov edx, %(fslot)d
        call %(getseq)#x
        test eax, eax
        jz s_fin
        mov [ebp - 0x10], eax
        mov ecx, [eax + 0x1c]
        test ecx, ecx
        jz s_fin
        mov ebx, [ecx + 8]
        test ebx, ebx
        jle s_fin
        mov eax, [ebp - 0x24]
        xor edx, edx
        div ebx
    s_draw:
        mov eax, [ebp - 0x10]
        mov ecx, [eax + 0x1c]
        mov ecx, [ecx + 4]
        mov edx, [ecx + edx*4]
        mov eax, [ebp + 8]
        push eax
        mov eax, [ebp - 0x10]
        mov eax, [eax + 0x10]
        call %(libget)#x
        mov ecx, [ebp - 0xc]
        mov edx, [ebp - 0x10]
        add ecx, [edx + 0x28]
        mov edx, [ebp - 8]
        mov ebx, [ebp - 0x10]
        add edx, [ebx + 0x24]
        mov ebx, [eax]
        call dword ptr [ebx + 0x84]
    s_fin:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 4
    """ % P)
    # getcls -> eax = the clone VMT (built on first use from TCombatFire's VMT + TCOozeHS's decal slots); keeps regs
    place("getcls", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov edx, [ebx + %(slot)#x]
        sub edx, %(suva)#x
        add edx, %(clone)#x
        cmp dword ptr [edx - 0x40], 0
        jne g_done
        mov esi, [ebx + %(fire)#x]
        sub esi, %(lo)d
        lea edi, [edx - %(lo)d]
        mov ecx, %(ndw)d
        .byte 0xf3, 0xa5
        mov [edx - 0x40], edx
        lea ecx, [ebx + %(classid)#x]
        mov [edx + 0x24], ecx
        lea ecx, [ebx + %(msg)#x]
        mov [edx + 0x44], ecx
        lea ecx, [ebx + %(show)#x]
        mov [edx + 0xa8], ecx
        lea ecx, [ebx + %(placeon)#x]
        mov [edx + 0xac], ecx
        mov esi, [ebx + %(ooze)#x]
        mov ecx, [esi + 0x64]
        mov [edx + 0x64], ecx
        mov ecx, [esi + 0x8c]
        mov [edx + 0x8c], ecx
        mov ecx, [esi + 0xd0]
        mov [edx + 0xd0], ecx
    g_done:
        mov eax, edx
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % dict(P, classid=where["classid"], msg=where["msg"], show=where["show"], placeon=where["placeon"]))
    # plc(edx = x, ecx = y; ebx = delta, esi = level): create / refresh the hex's smoke HS + spawn the burst effect
    place("plc", """
        push edi
        push ebp
        push ecx
        push edx
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz p_out
        mov edx, %(fcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz p_new
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [eax + 0x14], edx
        mov byte ptr [eax + 0x19], %(turns)d
        test ebp, ebp
        jnz p_fx
        mov byte ptr [eax + 0x1a], 1
        jmp p_fx
    p_new:
        call %(getcls)#x
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov edi, eax
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [edi + 0x14], edx
        mov byte ptr [edi + 0x19], %(turns)d
        test ebp, ebp
        jnz p_nc
        mov byte ptr [edi + 0x1a], 1
        mov eax, edi
        call %(tsset)#x
    p_nc:
        push dword ptr [esp + 4]
        push 0
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov edx, edi
        mov ecx, [esp + 8]
        call %(placehx)#x
        test al, al
        jnz p_fx
        mov eax, edi
        call %(free)#x
        jmp p_out
    p_fx:
        jmp p_out
        sub esp, 8
        lea eax, [esp + 4]
        push eax
        mov ecx, esp
        add ecx, 4
        mov edx, [esp + 0x10]
        mov eax, [esp + 0xc]
        call %(hxtohp)#x
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov dl, 0x26
        call %(addfx)#x
        mov edi, eax
        mov dword ptr [edi + 0x14], %(kind)d
        mov dword ptr [edi + 0x18], %(id)d
        mov dword ptr [edi + 0x24], 0
        mov dword ptr [edi + 0x2c], 0
        mov dl, 1
        mov eax, [ebx + %(xyz)#x]
        call %(ocreate)#x
        mov edx, [esp]
        add edx, 16
        mov [eax + 4], edx
        mov edx, [esp + 4]
        add edx, 16
        mov [eax + 8], edx
        mov edx, eax
        mov eax, [edi + 0x1c]
        call %(xyzadd)#x
        add esp, 8
    p_out:
        add esp, 8
        pop ebp
        pop edi
        ret
    """ % dict(P, getcls=where["getcls"]))
    # gate: `call <prev NextStrike chain>` sites; eax = te
    place("gate", """
        cmp dword ptr [eax + 0x18], %(id)d
        jne g_prev
        cmp dword ptr [eax + 0x28], 0
        jne g_go
    g_prev:
        jmp %(prev)#x
    g_go:
        pushal
        mov dword ptr [eax + 0x28], 0
        mov edi, eax
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        cmp byte ptr [eax + 0x129], 0
        je g_nosnd
        mov eax, [ebx + %(hsset)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz g_nosnd
        mov eax, [eax + 0x28]
        test eax, eax
        jz g_nosnd
        xor edx, edx
        call %(sndplay)#x
    g_nosnd:
        push 0
        movzx ecx, word ptr [edi + 0x22]
        movzx edx, word ptr [edi + 0x20]
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov esi, [eax]
        call dword ptr [esi + 0xbc]
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov eax, [eax + 0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        je g_out
        mov esi, eax
        sub esp, 8
        xor ebp, ebp
    g_hn:
        lea eax, [esp]
        push eax
        lea eax, [esp + 8]
        push eax
        mov ecx, ebp
        movzx eax, word ptr [edi + 0x20]
        movzx edx, word ptr [edi + 0x22]
        call %(hn2hx)#x
        mov edx, [esp]
        mov ecx, [esp + 4]
        test edx, edx
        js g_next
        test ecx, ecx
        js g_next
        cmp edx, [esi + 0xc]
        jge g_next
        cmp ecx, [esi + 0x10]
        jge g_next
        call %(plc)#x
    g_next:
        inc ebp
        cmp ebp, %(nhex)d
        jb g_hn
        add esp, 8
    g_out:
        popal
        ret
    """ % dict(P, plc=where["plc"]))
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def build2(prev_dds):
    """Zone 2 (v3 layering): dds / ovl / end / replay + the bank start table (tsget / tsset)."""
    out = bytearray(HDR2); where = {}
    struct.pack_into("<I", out, 0, prev_dds); out[4:9] = OVL_ORIG; out[0x10:0x15] = END_ORIG
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE2 + len(out); where[name] = va; out.extend(asm_delta(src, va))
    P = {"slot": SETUNIT_SLOT, "suva": SETUNIT_VA, "w": W_EP, "tick": TICKOBJ, "clone": CLONE_EP, "prev": prev_dds,
         "novl": NOVL, "near": NEAR, "near2": 2 * NEAR, "neare": NEAR_E, "neare2": 2 * NEAR_E, "ovl": OVL_SITE, "ovl5": OVL_SITE + 5, "end": END_SITE,
         "end5": END_SITE + 5}
    # tsget(eax = bank HS) -> eax = its start frame (inserted at the current frame on first sight); keeps the rest.
    # tsset(eax = bank HS) -> start := now (insert or overwrite); keeps all registers.
    TS_HEAD = """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        push eax
        mov edi, eax
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebx + %(slot)#x]
        sub esi, %(suva)#x
        add esi, %(w)#x
        xor ecx, ecx
    t_l:
        cmp [esi + 0x10 + ecx*8], edi
        je t_hit
        inc ecx
        cmp ecx, 8
        jb t_l
        mov ecx, [esi + 8]
        and ecx, 7
        inc dword ptr [esi + 8]
        mov [esi + 0x10 + ecx*8], edi
        mov eax, [ebx + %(tick)#x]
        mov eax, [eax]
        mov eax, [eax + 0x40]
        mov [esi + 0x14 + ecx*8], eax
        jmp t_out
    t_hit:
    """ % P
    TS_GET = TS_HEAD + """
        mov eax, [esi + 0x14 + ecx*8]
    t_out:
        add esp, 4
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """
    TS_SET = TS_HEAD + """
        mov eax, [ebx + %(tick)#x]
        mov eax, [eax]
        mov eax, [eax + 0x40]
        mov [esi + 0x14 + ecx*8], eax
    t_out:
        pop eax
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % P
    place("tsget", TS_GET)
    place("tsset", TS_SET)
    # ovl (jmp from 0x4228A8, inside TTacticalCombatUnitHS.Show's frame): while dds defers (and not replaying), record
    # the overlay inputs and skip the block; otherwise run it
    place("ovl", """
        pushal
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebx + %(slot)#x]
        sub esi, %(suva)#x
        add esi, %(w)#x
        cmp byte ptr [esi + 1], 0
        jne o_van
        cmp byte ptr [esi], 0
        je o_van
        mov ecx, [esi + 4]
        cmp ecx, %(novl)d
        jae o_van
        lea edi, [ecx + ecx*4]
        lea edi, [esi + 0x60 + edi*4]
        mov eax, [ebp - 4]
        mov [edi], eax
        mov eax, [ebp - 8]
        mov [edi + 4], eax
        mov eax, [ebp - 0xc]
        mov [edi + 8], eax
        mov eax, [ebp - 0x3c]
        mov [edi + 0xc], eax
        mov eax, [ebp + 8]
        mov [edi + 0x10], eax
        inc dword ptr [esi + 4]
        popal
        jmp %(end)#x
    o_van:
        popal
        mov eax, [ebp - 4]
        mov edx, [eax]
        jmp %(ovl5)#x
    """ % P)
    # end (jmp from 0x422B00): a replayed overlay ends here -> unwind replay's frame (ret 4 to dds); else the original
    place("end", """
        push esi
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebx + %(slot)#x]
        sub esi, %(suva)#x
        add esi, %(w)#x
        cmp byte ptr [esi + 1], 0
        je e_van
        mov byte ptr [esi + 1], 0
        lea esp, [ebp - 0x9c]
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 4
    e_van:
        pop ebx
        pop esi
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        jmp %(end5)#x
    """ % P)
    # replay(eax = overlay record, [esp+4] = target; ret 4): fabricate the Show frame the overlay block reads
    place("replay", """
        push ebp
        mov ebp, esp
        sub esp, 0x90
        push ebx
        push esi
        push edi
        mov ecx, [eax]
        mov [ebp - 4], ecx
        mov ecx, [eax + 4]
        mov [ebp - 8], ecx
        mov ecx, [eax + 8]
        mov [ebp - 0xc], ecx
        mov ecx, [eax + 0xc]
        mov [ebp - 0x3c], ecx
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebx + %(slot)#x]
        sub esi, %(suva)#x
        add esi, %(w)#x
        mov byte ptr [esi + 1], 1
        jmp %(ovl)#x
    """ % P)
    SHOW = """
        push dword ptr [ebp - 8]
        mov ecx, [ebp - 4]
        mov edx, [ecx + 0x80]
        mov ecx, [ecx + 0x84]
        mov ebx, [eax]
        call dword ptr [ebx + 0xa8]
    """
    # v3.1 cshow(eax = obj, edx = map, ecx = target): re-show a wall / building / unit-on-wall in the post pass.  Its hex
    # under smoke (the field owns a smoke HS, ClassID FIELD_CLASSID) -> drawn CLIPPED above the smoke line (the target
    # descriptor's clip rect +0x10/+0x14/+0x18/+0x1C = left/top/right/bottom, honoured by the Gfxepack blitters) in
    # COLW-wide columns whose bottom follows a gentle lapping wave, so its base stays under the bank and only the top
    # protrudes; the descriptor's clip is restored afterwards.  Not under smoke -> the plain Show (v3 behaviour).
    # v3.2 ofld(eax = obj) -> eax = the hex field it stands for (a TCombatObstacleOverlay -> its obstacle's field);
    # keeps every other register
    place("ofld", """
        push ebx
        push ecx
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [eax]
        lea ebx, [ebx + %(ovl)#x]
        cmp ecx, ebx
        jne of_own
        mov eax, [eax + 8]
        test eax, eax
        jz of_out
    of_own:
        mov eax, [eax + 4]
    of_out:
        pop ecx
        pop ebx
        ret
    """ % dict(ovl=OVL_VMT))
    # v3.2 iltall(eax = a TCombatILTerrain) -> al = 1 when its current tile image (resource +0x20 library, tile +0x14,
    # TLibraryImage height +0x24) is taller than TALLH: an earth-wall column of an underground battlefield (H_EARTH
    # tiles 56..68 px vs 32 px floors / rubble / roads); keeps ebx / ecx / edx / esi / edi
    place("iltall", """
        push ebx
        push ecx
        push edx
        mov ecx, [eax + 8]
        test ecx, ecx
        jz it_no
        mov edx, [eax + 0x14]
        mov ebx, [ecx + 0x24]
        test ebx, ebx
        jnz it_seq
        mov eax, [ecx + 0x20]
        jmp it_get
    it_seq:
        test edx, edx
        jl it_no
        cmp edx, [ebx + 8]
        jge it_no
        mov ebx, [ebx + 4]
        mov ebx, [ebx + edx*4]
        test ebx, ebx
        jz it_no
        mov eax, [ebx + 0x10]
        xor edx, edx
    it_get:
        test eax, eax
        jz it_no
        call %(libget)#x
        test eax, eax
        jz it_no
        cmp dword ptr [eax + 0x24], %(tallh)d
        jle it_no
        mov al, 1
        jmp it_out
    it_no:
        xor eax, eax
    it_out:
        pop edx
        pop ecx
        pop ebx
        ret
    """ % dict(libget=T_LIBGET, tallh=TALLH))
    # v3.4 ehtest(eax = a TCombatHexagon) -> al = 1 when its base-hex resource ([hex+8]) draws from an H_EARTH-sized library:
    # sequence list [res+0x24] item 0 -> part +0x10 library -> image 0 height >= EH_H (the earth 'Wall' base hex: 86x107 cliff
    # faces; every other base-hex library is 48x32).  The same lookup TCombatHexagon.Show (0x403CAC) uses; keeps ebx/ecx/edx
    place("ehtest", """
        push ebx
        push ecx
        push edx
        mov ecx, [eax + 8]
        test ecx, ecx
        jz e_no
        mov ebx, [ecx + 0x24]
        test ebx, ebx
        jz e_no
        cmp dword ptr [ebx + 8], 0
        jle e_no
        mov ebx, [ebx + 4]
        mov ebx, [ebx]
        test ebx, ebx
        jz e_no
        mov eax, [ebx + 0x10]
        test eax, eax
        jz e_no
        xor edx, edx
        call %(libget)#x
        test eax, eax
        jz e_no
        cmp dword ptr [eax + 0x24], %(ehh)d
        jl e_no
        mov al, 1
        jmp e_out
    e_no:
        xor eax, eax
    e_out:
        pop edx
        pop ecx
        pop ebx
        ret
    """ % dict(libget=T_LIBGET, ehh=EH_H))
    place("wtbl", ".byte " + ", ".join(str(v & 0xFF) for v in WAVE))
    place("ftbl", ".byte " + ", ".join(str(v) for v in FWT))
    # v3.1/v3.2 cshow(eax = obj, edx = map, ecx = target): re-show a wall / building / pillar / unit-on-wall in the post
    # pass.  Its hex under smoke (the field owns a smoke HS) -> re-shown CLIPPED above the smoke line (the target lock
    # descriptor's clip rect +0x10/+0x14/+0x18/+0x1C) per COLW column whose line follows the lapping wave.  v3.2: the
    # FEATHER rows just above each column's line are SAVED from the locked surface (descriptor +0x20 bits, +0xC pitch,
    # +8 bpp; 16 bpp only) before the structure is drawn and BLENDED back afterwards with a smoothstep weight (FWT,
    # 0..32 = the smoked share, top -> line): every pixel the structure did not touch is unchanged (saved == drawn ->
    # skipped), every structure pixel fades from clear to the bank's own smoked value at the line - a true soft edge,
    # no halo, no dither.  Hex not under smoke -> the plain Show.  The flat outer remainders keep the hard cut.
    place("cshow", """
        push ebp
        mov ebp, esp
        sub esp, 0x70
        pushal
        mov [ebp - 4], eax
        mov [ebp - 8], edx
        mov [ebp - 0xc], ecx
        mov dword ptr [ebp - 0x70], 0xa8
        cmp dword ptr [ebp + 8], 2
        jne c_sl
        mov dword ptr [ebp - 0x70], %(isoslot)#x
    c_sl:
        call $D
        pop ebx
        sub ebx, $D
        mov [ebp - 0x10], ebx
        mov ecx, [ebx + %(slot)#x]
        sub ecx, %(suva)#x
        add ecx, %(buf)#x
        mov [ebp - 0x60], ecx
        call %(ofld)#x
        test eax, eax
        jz c_plain
        mov [ebp - 0x14], eax
        cmp dword ptr [ebp + 8], 0
        jne c_go
        mov edx, %(fcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz c_plain
    c_go:
        lea eax, [ebp - 0x1c]
        push eax
        lea ecx, [ebp - 0x18]
        mov eax, [ebp - 0x14]
        movsx edx, byte ptr [eax + 0x11]
        movsx eax, byte ptr [eax + 0x10]
        call %(hxtohp)#x
        mov ecx, [ebp - 8]
        mov eax, [ebp - 0x18]
        sub eax, [ecx + 0x80]
        add eax, %(hcx)d
        mov [ebp - 0x18], eax
        mov eax, [ebp - 0x1c]
        sub eax, [ecx + 0x84]
        add eax, %(hcy)d
        mov [ebp - 0x1c], eax
        mov eax, [ebp + 8]
        test eax, eax
        je c_hy
        imul eax, eax, %(ecutd)d
        add eax, %(ecut0)d
        add [ebp - 0x1c], eax
    c_hy:
        mov esi, [ebp - 0xc]
        mov eax, [esi + 0x10]
        mov [ebp - 0x20], eax
        mov eax, [esi + 0x14]
        mov [ebp - 0x24], eax
        mov eax, [esi + 0x18]
        mov [ebp - 0x28], eax
        mov eax, [esi + 0x1c]
        mov [ebp - 0x2c], eax
        mov ebx, [ebp - 0x10]
        mov eax, [ebx + %(tick)#x]
        mov eax, [eax]
        mov eax, [eax + 0x40]
        xor edx, edx
        mov ecx, 6
        div ecx
        mov [ebp - 0x30], eax
        mov ecx, [ebp - 8]
        mov ecx, [ecx + 0x80]
        mov [ebp - 0x34], ecx
        mov eax, [ebp - 0x18]
        sub eax, %(span)d
        add eax, ecx
        and eax, %(colmask)d
        sub eax, ecx
        mov edi, eax
        mov eax, [ebp - 0x18]
        add eax, %(span)d
        mov [ebp - 0x38], eax
        mov eax, [ebp - 0x20]
        mov edx, edi
        mov ecx, [ebp - 0x1c]
        call c_cd
    c_col:
        cmp edi, [ebp - 0x38]
        jge c_right
        mov eax, edi
        add eax, [ebp - 0x34]
        sar eax, %(colsh)d
        add eax, [ebp - 0x30]
        and eax, 15
        mov ebx, [ebp - 0x10]
        movsx ecx, byte ptr [ebx + eax + %(wtbl)#x]
        add ecx, [ebp - 0x1c]
        mov eax, edi
        lea edx, [edi + %(colw)d]
        call c_cd
        add edi, %(colw)d
        jmp c_col
    c_right:
        mov eax, edi
        mov edx, [ebp - 0x28]
        mov ecx, [ebp - 0x1c]
        call c_cd
        mov esi, [ebp - 0xc]
        mov eax, [ebp - 0x20]
        mov [esi + 0x10], eax
        mov eax, [ebp - 0x24]
        mov [esi + 0x14], eax
        mov eax, [ebp - 0x28]
        mov [esi + 0x18], eax
        mov eax, [ebp - 0x2c]
        mov [esi + 0x1c], eax
        jmp c_out
    c_plain:
        push dword ptr [ebp - 0xc]
        mov ecx, [ebp - 8]
        mov edx, [ecx + 0x80]
        mov ecx, [ecx + 0x84]
        mov eax, [ebp - 4]
        mov ebx, [eax]
        add ebx, [ebp - 0x70]
        call dword ptr [ebx]
    c_out:
        popal
        mov esp, ebp
        pop ebp
        ret 4
    c_cd:
        push edi
        mov [ebp - 0x40], eax
        mov [ebp - 0x44], edx
        mov [ebp - 0x48], ecx
        call c_fclamp
        mov [ebp - 0x5c], eax
        test al, al
        jz c_cd1
        call c_save
    c_cd1:
        mov eax, [ebp - 0x40]
        mov edx, [ebp - 0x44]
        mov ecx, [ebp - 0x48]
        call c_rect
        cmp byte ptr [ebp - 0x5c], 0
        je c_cd2
        call c_blend
    c_cd2:
        pop edi
        ret
    c_fclamp:
        mov eax, [ebp - 0x44]
        sub eax, [ebp - 0x40]
        cmp eax, %(colw)d
        jg c_fno
        mov esi, [ebp - 0xc]
        cmp dword ptr [esi + 8], 16
        jne c_fno
        mov eax, [esi + 0x2c]
        cmp eax, 0xf800
        jne c_f555
        mov dword ptr [ebp - 0x6c], 0x07E0F81F
        jmp c_fm
    c_f555:
        cmp eax, 0x7c00
        jne c_fno
        mov dword ptr [ebp - 0x6c], 0x03E07C1F
    c_fm:
        mov eax, [ebp - 0x40]
        cmp eax, [ebp - 0x20]
        jge c_f1
        mov eax, [ebp - 0x20]
    c_f1:
        mov [ebp - 0x4c], eax
        mov eax, [ebp - 0x44]
        cmp eax, [ebp - 0x28]
        jle c_f2
        mov eax, [ebp - 0x28]
    c_f2:
        mov [ebp - 0x50], eax
        mov eax, [ebp - 0x48]
        sub eax, %(fea)d
        cmp eax, [ebp - 0x24]
        jge c_f3
        mov eax, [ebp - 0x24]
    c_f3:
        mov [ebp - 0x54], eax
        mov eax, [ebp - 0x48]
        cmp eax, [ebp - 0x2c]
        jle c_f4
        mov eax, [ebp - 0x2c]
    c_f4:
        mov [ebp - 0x58], eax
        mov eax, [ebp - 0x4c]
        cmp eax, [ebp - 0x50]
        jge c_fno
        mov eax, [ebp - 0x54]
        cmp eax, [ebp - 0x58]
        jge c_fno
        mov eax, 1
        ret
    c_fno:
        xor eax, eax
        ret
    c_save:
        mov edx, [ebp - 0x54]
    c_sy:
        cmp edx, [ebp - 0x58]
        jge c_sout
        mov esi, [ebp - 0xc]
        mov eax, edx
        imul eax, [esi + 0xc]
        add eax, [esi + 0x20]
        mov ecx, [ebp - 0x4c]
        lea esi, [eax + ecx*2]
        mov edi, edx
        sub edi, [ebp - 0x54]
        shl edi, %(rsh)d
        add edi, [ebp - 0x60]
    c_sx:
        cmp ecx, [ebp - 0x50]
        jge c_sn
        mov ax, word ptr [esi]
        mov word ptr [edi], ax
        add esi, 2
        add edi, 2
        inc ecx
        jmp c_sx
    c_sn:
        inc edx
        jmp c_sy
    c_sout:
        ret
    c_blend:
        mov edx, [ebp - 0x54]
    c_by:
        cmp edx, [ebp - 0x58]
        jge c_bout
        push edx
        mov eax, edx
        sub eax, [ebp - 0x48]
        add eax, %(fea)d
        mov ebx, [ebp - 0x10]
        movzx eax, byte ptr [ebx + eax + %(ftbl)#x]
        mov [ebp - 0x64], eax
        mov ecx, 32
        sub ecx, eax
        mov [ebp - 0x68], ecx
        mov esi, [ebp - 0xc]
        mov eax, edx
        imul eax, [esi + 0xc]
        add eax, [esi + 0x20]
        mov ecx, [ebp - 0x4c]
        lea esi, [eax + ecx*2]
        mov edi, edx
        sub edi, [ebp - 0x54]
        shl edi, %(rsh)d
        add edi, [ebp - 0x60]
        mov ebx, ecx
    c_bx:
        cmp ebx, [ebp - 0x50]
        jge c_bny
        movzx eax, word ptr [esi]
        movzx edx, word ptr [edi]
        cmp eax, edx
        je c_bn
        mov ecx, eax
        shl ecx, 16
        or eax, ecx
        and eax, [ebp - 0x6c]
        mov ecx, edx
        shl ecx, 16
        or edx, ecx
        and edx, [ebp - 0x6c]
        imul eax, [ebp - 0x68]
        imul edx, [ebp - 0x64]
        add eax, edx
        shr eax, 5
        and eax, [ebp - 0x6c]
        mov ecx, eax
        shr ecx, 16
        or eax, ecx
        mov word ptr [esi], ax
    c_bn:
        add esi, 2
        add edi, 2
        inc ebx
        jmp c_bx
    c_bny:
        pop edx
        inc edx
        jmp c_by
    c_bout:
        ret
    c_rect:
        cmp eax, [ebp - 0x20]
        jge c_r1
        mov eax, [ebp - 0x20]
    c_r1:
        cmp edx, [ebp - 0x28]
        jle c_r2
        mov edx, [ebp - 0x28]
    c_r2:
        cmp ecx, [ebp - 0x2c]
        jle c_r3
        mov ecx, [ebp - 0x2c]
    c_r3:
        cmp eax, edx
        jge c_rn
        cmp ecx, [ebp - 0x24]
        jle c_rn
        mov ebx, [ebp - 0xc]
        mov [ebx + 0x10], eax
        mov [ebx + 0x18], edx
        mov [ebx + 0x1c], ecx
        mov eax, [ebp - 0x24]
        mov [ebx + 0x14], eax
        push ebx
        mov ecx, [ebp - 8]
        mov edx, [ecx + 0x80]
        mov ecx, [ecx + 0x84]
        mov eax, [ebp - 4]
        mov ebx, [eax]
        add ebx, [ebp - 0x70]
        call dword ptr [ebx]
    c_rn:
        ret
    """ % dict(P, fcls=FIELD_CLASSID, hxtohp=T_HXTOHP, hcx=HCX, hcy=HCY + CUT, span=SPAN, colw=COLW,
               colmask=-COLW & 0xFFFFFFFF, colsh=COLW.bit_length() - 1, wtbl=where["wtbl"], ofld=where["ofld"],
               ftbl=where["ftbl"], fea=FEATHER, buf=BUF_EP, rsh=(COLW * 2).bit_length() - 1, ecutd=EARTH_CUT_ISO - EARTH_CUT, ecut0=2 * (EARTH_CUT - HCY - CUT) - (EARTH_CUT_ISO - HCY - CUT), isoslot=ISO_SLOT))   # v3.5: line += mode 1 -> EARTH_CUT, mode 2 -> EARTH_CUT_ISO (linear in mode)
    # dds(eax = map, edx = target): the vanilla dynamic draw, then (only while smoke banks are on screen) the post pass
    src = """
        push ebp
        mov ebp, esp
        sub esp, 0x60
        pushal
        mov [ebp - 4], eax
        mov [ebp - 8], edx
        call $D
        pop ebx
        sub ebx, $D
        mov [ebp - 0x14], ebx
        mov esi, [ebx + %(slot)#x]
        sub esi, %(suva)#x
        lea edi, [esi + %(clone)#x]
        add esi, %(w)#x
        mov [ebp - 0xc], esi
        mov byte ptr [esi], 0
        mov byte ptr [esi + 1], 0
        mov byte ptr [esi + 2], 0
        xor ecx, ecx
        mov eax, [ebp - 4]
        mov eax, [eax + 0x20]
        test eax, eax
        jz d_se
        mov edx, [eax + 0xc]
        mov eax, [eax + 0x14]
    d_sc:
        dec edx
        js d_se
        mov ebx, [eax + edx*8 + 4]
        test ebx, ebx
        jz d_sc
        cmp [ebx], edi
        jne d_sc
        cmp byte ptr [ebx + 0x1a], 0
        je d_sc
        cmp ecx, 8
        jae d_sc
        mov [ebp - 0x60 + ecx*4], ebx
        inc ecx
        jmp d_sc
    d_se:
        mov [ebp - 0x10], ecx
        test ecx, ecx
        jnz d_smoke
        popal
        mov esp, ebp
        pop ebp
        jmp %(prev)#x
    d_smoke:
        mov byte ptr [esi], 1
        mov dword ptr [esi + 4], 0
        mov eax, [ebp - 4]
        mov edx, [ebp - 8]
        call %(prev)#x
        mov esi, [ebp - 0xc]
        mov byte ptr [esi], 0
        mov byte ptr [esi + 2], 1
        xor edi, edi
    d_b:
        cmp edi, [ebp - 0x10]
        jae d_be
        mov eax, [ebp - 0x60 + edi*4]
    @SHOW@
        inc edi
        jmp d_b
    d_be:
        mov esi, [ebp - 0xc]
        mov byte ptr [esi + 2], 0
        mov dword ptr [ebp - 0x18], 0x1c
    d_l2:
        mov eax, [ebp - 4]
        mov ecx, [ebp - 0x18]
        mov eax, [eax + ecx]
        test eax, eax
        jz d_l2n
        mov edi, [eax + 0xc]
        mov eax, [eax + 0x14]
        mov [ebp - 0x1c], eax
    d_w:
        dec edi
        js d_l2n
        mov eax, [ebp - 0x1c]
        mov eax, [eax + edi*8 + 4]
        test eax, eax
        jz d_w
        mov edx, [eax]
        mov ebx, [ebp - 0x14]
@TALL@
        jmp d_w
    d_il:
        push eax
        call %(iltall)#x
        test al, al
        pop eax
        jz d_w
    d_wte:
        mov [ebp - 0x20], eax
        call d_neare
        test al, al
        jz d_w
        mov eax, [ebp - 0x20]
    @CSHOWE@
        jmp d_w
    d_iso:
        push eax
        call %(ehtest)#x
        test al, al
        pop eax
        jz d_w
        mov [ebp - 0x20], eax
        call d_neare
        test al, al
        jz d_w
        mov eax, [ebp - 0x20]
    @CSHOWI@
        jmp d_w
    d_wt:
        mov [ebp - 0x20], eax
        call d_near
        test al, al
        jz d_w
        mov eax, [ebp - 0x20]
    @CSHOW@
        jmp d_w
    d_l2n:
        cmp dword ptr [ebp - 0x18], 0x20
        je d_u0
        mov dword ptr [ebp - 0x18], 0x20
        jmp d_l2
    d_u0:
        xor edi, edi
    d_u:
        mov esi, [ebp - 0xc]
        cmp edi, [esi + 4]
        jae d_r0
        lea eax, [edi + edi*4]
        lea eax, [esi + 0x60 + eax*4]
        mov [ebp - 0x20], eax
        mov eax, [eax]
        call d_near
        test al, al
        jz d_un
        mov eax, [ebp - 0x20]
        mov eax, [eax]
        mov eax, [eax + 4]
        test eax, eax
        jz d_un
        mov [ebp - 0x24], eax
        mov edx, 0x220504
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jnz d_uw
        mov eax, [ebp - 0x24]
        mov edx, 0x220506
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz d_un
    d_uw:
        cmp dword ptr [eax + 0x20], 0
        jle d_un
        mov eax, [ebp - 0x20]
        mov eax, [eax]
    @CSHOW@
    d_un:
        inc edi
        jmp d_u
    d_r0:
        xor edi, edi
    d_r:
        mov esi, [ebp - 0xc]
        cmp edi, [esi + 4]
        jae d_out
        lea eax, [edi + edi*4]
        lea eax, [esi + 0x60 + eax*4]
        push dword ptr [eax + 0x10]
        call %(replay)#x
        inc edi
        jmp d_r
    d_out:
        popal
        mov esp, ebp
        pop ebp
        ret
    d_near:
        push ebx
        push esi
        call %(ofld)#x
        test eax, eax
        jz dn_no
        movsx esi, byte ptr [eax + 0x10]
        movsx ebx, byte ptr [eax + 0x11]
        xor ecx, ecx
    dn_l:
        cmp ecx, [ebp - 0x10]
        jae dn_no
        mov eax, [ebp - 0x60 + ecx*4]
        mov eax, [eax + 4]
        test eax, eax
        jz dn_n
        movsx edx, byte ptr [eax + 0x10]
        sub edx, esi
        add edx, %(near)d
        cmp edx, %(near2)d
        ja dn_n
        movsx edx, byte ptr [eax + 0x11]
        sub edx, ebx
        add edx, %(near)d
        cmp edx, %(near2)d
        ja dn_n
        mov al, 1
        jmp dn_out
    dn_n:
        inc ecx
        jmp dn_l
    dn_no:
        xor eax, eax
    dn_out:
        pop esi
        pop ebx
        ret
    d_neare:
        push ebx
        push esi
        call %(ofld)#x
        test eax, eax
        jz de_no
        movsx esi, byte ptr [eax + 0x10]
        movsx ebx, byte ptr [eax + 0x11]
        xor ecx, ecx
    de_l:
        cmp ecx, [ebp - 0x10]
        jae de_no
        mov eax, [ebp - 0x60 + ecx*4]
        mov eax, [eax + 4]
        test eax, eax
        jz de_n
        movsx edx, byte ptr [eax + 0x10]
        sub edx, esi
        add edx, %(neare)d
        cmp edx, %(neare2)d
        ja de_n
        movsx edx, byte ptr [eax + 0x11]
        sub edx, ebx
        add edx, %(neare)d
        cmp edx, %(neare2)d
        ja de_n
        mov al, 1
        jmp de_out
    de_n:
        inc ecx
        jmp de_l
    de_no:
        xor eax, eax
    de_out:
        pop esi
        pop ebx
        ret
    """
    CSHOW = "        push 0\n        mov edx, [ebp - 4]\n        mov ecx, [ebp - 8]\n        call %#x\n" % where["cshow"]
    CSHOWE = "        push 1\n        mov edx, [ebp - 4]\n        mov ecx, [ebp - 8]\n        call %#x\n" % where["cshow"]   # v3.4 earth mode (no smoke-tile test, line = EARTH_CUT)
    CSHOWI = "        push 2\n        mov edx, [ebp - 4]\n        mov ecx, [ebp - 8]\n        call %#x\n" % where["cshow"]   # v3.5 iso earth (ShowDynamic, EARTH_CUT_ISO)
    src = src.replace("@CSHOWI@", CSHOWI).replace("@CSHOWE@", CSHOWE).replace("@CSHOW@", CSHOW).replace("@SHOW@", SHOW).replace("@TALL@", '        lea ecx, [ebx + 0x405008]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + 0x4052ac]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + 0x4334e0]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + 0x4341f8]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + 0x434584]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + 0x435310]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + %#x]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + %#x]\n        cmp edx, ecx\n        je d_wt\n        lea ecx, [ebx + %#x]\n        cmp edx, ecx\n        je d_il\n        lea ecx, [ebx + %#x]\n        cmp edx, ecx\n        je d_il\n        lea ecx, [ebx + %#x]\n        cmp edx, ecx\n        je d_iso' % (OBST_VMT, OVL_VMT, ILTER_VMT, FILTER_VMT, ISO_VMT))   # v3.5: v3.4's TCombatHexagon (EH_VMT) test dropped - live: every one is a 48x32 floor
    place("dds", src % dict(P, replay=where["replay"], ofld=where["ofld"], iltall=where["iltall"], ehtest=where["ehtest"]))
    zone = bytes(out)
    assert ZONE2 + len(zone) <= ZONE2_END, hex(ZONE2 + len(zone))
    assert W_END <= BUF_EP and BUF_EP + FEATHER * COLW * 2 <= 0x5590C000, 'feather buffer outside the .idata page slack'
    return zone, where


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def check_thunks(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {}
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in ent.imports: iat[imp.address] = imp.name or b""
    for va, want in THUNKS.items():
        b = d[va - V2F:va - V2F + 6]
        assert b[:2] == b"\xff\x25", "thunk %#x is not jmp [mem]: %s" % (va, b.hex())
        slot = struct.unpack_from("<I", b, 2)[0]
        name = iat.get(slot, b"").decode("latin-1")
        assert all(p in name for p in want.split(".")), "thunk %#x -> %r, wanted %r" % (va, name, want)
    assert "SetUnit" in iat.get(SETUNIT_SLOT, b"").decode("latin-1"), "import slot %#x is %r" % (SETUNIT_SLOT, iat.get(SETUNIT_SLOT))
    assert 0x5590B200 <= CLONE_EP - VMT_LO and CLONE_EP + VMT_HI <= 0x5590C000, "clone room outside the AoWEPACK .idata page slack"
    assert CLONE_EP + VMT_HI <= 0x5590B400 and 0x5590B414 <= W_EP and W_EP + 0x60 + 20 * NOVL <= W_END <= 0x5590C000, \
        "v3 state room overlaps the clone / Wall of Flames counters or leaves the .idata page slack"


def ep_ready(path):
    """The AoWEPACK export must be live (patch_smokescreen_v1.py applied)."""
    d = open(path, "rb").read(); o = EP_SYNC - 0x55700C00
    if d[o] != 0xE9: return "AoWEPACK export missing (apply patch_smokescreen_v1.py first)"
    t = EP_SYNC + 5 + struct.unpack_from("<i", d, o + 1)[0]
    return None if EP_ZONE[0] <= t < EP_ZONE[1] else "AoWEPACK export points outside its zone (%#x)" % t


def call_target(d, va):
    b = d[va - V2F:va - V2F + 5]
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE8 else None


def jmp_target(d, va):
    b = d[va - V2F:va - V2F + 5]
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL); ap.add_argument("--ep", default=DEFAULT_EP)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    check_thunks(d)
    inzone = lambda t: t is not None and ZONE <= t < ZONE_END
    inzone2 = lambda t: t is not None and ZONE2 <= t < ZONE2_END
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F]); z2l = bytes(d[ZONE2 - V2F:ZONE2_END - V2F])
    cur = [call_target(d, s) for s in GATE_SITES]
    if any(t is None for t in cur) or len(set(cur)) != 1:
        state, prev = "OTHER(%s)" % [hex(t) if t else None for t in cur], 0
    elif inzone(cur[0]):
        state, prev = "ours", struct.unpack_from("<I", zl, 0)[0]
    else:
        state, prev = "chain", cur[0]
    # v3 zone 2 + its three sites
    ddst = call_target(d, DDS_SITE)
    if inzone2(ddst): s_dds, prev_dds = "ours", struct.unpack_from("<I", z2l, 0)[0]
    elif ddst is not None: s_dds, prev_dds = ("vanilla" if ddst == DDS_VANILLA else "chain"), ddst
    else: s_dds, prev_dds = "OTHER", 0
    def site_state(va, orig):
        b = bytes(d[va - V2F:va - V2F + 5])
        if b == orig: return "vanilla"
        return "ours" if inzone2(jmp_target(d, va)) else "OTHER"
    s_ovl, s_end = site_state(OVL_SITE, OVL_ORIG), site_state(END_SITE, END_ORIG)
    zone2, where2 = build2(prev_dds if prev_dds else DDS_VANILLA)
    zone, where = build(prev if prev else 0x7FFFFFF0, where2)
    rl = reloc_set(bytes(d))
    sites5 = GATE_SITES + [DDS_SITE, OVL_SITE, END_SITE]
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or ZONE2 - 3 <= r < ZONE2_END or any(s - 3 <= r < s + 5 for s in sites5)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) \
        else "ours(old)" if state == "ours" else "DIFFERS"
    v3on = s_dds == "ours" or s_ovl == "ours" or s_end == "ours"
    z2state = "zero" if not any(z2l) else "ours" if z2l[:len(zone2)] == zone2 and not any(z2l[len(zone2):]) \
        else "ours(old)" if v3on else "DIFFERS"
    epmsg = ep_ready(a.ep)
    print("AoWTCPCK smokescreen: gate %s (prev %#x) | zone %s (%d B: %s) | relocs %s | AoWEPACK %s" % (
        state, prev, zstate, len(zone), ", ".join("%s=%#x" % kv for kv in where.items()), bad or "none", epmsg or "export ok"))
    print("  v3 layering: dds %s (prev %#x) | ovl %s | end %s | zone2 %s (%d B: %s)" % (
        s_dds, prev_dds, s_ovl, s_end, z2state, len(zone2), ", ".join("%s=%#x" % kv for kv in where2.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for zb, zz, ww in ((ZONE, zone, where), (ZONE2, zone2, where2)):
            cav = sorted((v, k) for k, v in ww.items()) + [(zb + len(zz), None)]
            for (va, nm), (nx, _n) in zip(cav, cav[1:]):
                print("  [%s]" % nm)
                for i in md.disasm(zz[va - zb:nx - zb], va):
                    print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state.startswith("OTHER") or zstate == "DIFFERS" or "OTHER" in (s_dds, s_ovl, s_end) or z2state == "DIFFERS":
        print("ABORT (relocs / foreign hook / zone not free)"); return 1
    if a.revert:
        if state != "ours": print("ABORT revert: not applied, or another patch is chained in front (%s)" % state); return 1
        if s_dds == "chain": print("ABORT revert: another patch is chained in front of the DDS site"); return 1
        for s in GATE_SITES: d[s - V2F:s - V2F + 5] = b"\xe8" + struct.pack("<i", prev - (s + 5))
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        if s_dds == "ours": d[DDS_SITE - V2F:DDS_SITE - V2F + 5] = b"\xe8" + struct.pack("<i", prev_dds - (DDS_SITE + 5))
        if s_ovl == "ours": d[OVL_SITE - V2F:OVL_SITE - V2F + 5] = z2l[4:9]
        if s_end == "ours": d[END_SITE - V2F:END_SITE - V2F + 5] = z2l[0x10:0x15]
        d[ZONE2 - V2F:ZONE2_END - V2F] = bytes(ZONE2_END - ZONE2)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (gate sites -> %#x, DDS -> %#x, overlay sites original, both zones zeroed)" % (prev, prev_dds)); return 0
    if epmsg: print("ABORT (%s)" % epmsg); return 1
    if state == "ours" and zstate == "ours" and z2state == "ours" and (s_dds, s_ovl, s_end) == ("ours",) * 3:
        print("already applied (v3.5)"); return 0
    if zstate == "ours(old)" or z2state == "ours(old)": print("older build of this patch detected -> rewriting the zones in place (v3.5 upgrade)")
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    for s in GATE_SITES: d[s - V2F:s - V2F + 5] = b"\xe8" + struct.pack("<i", where["gate"] - (s + 5))
    d[ZONE2 - V2F:ZONE2_END - V2F] = bytes(ZONE2_END - ZONE2); d[ZONE2 - V2F:ZONE2 - V2F + len(zone2)] = zone2
    d[DDS_SITE - V2F:DDS_SITE - V2F + 5] = b"\xe8" + struct.pack("<i", where2["dds"] - (DDS_SITE + 5))
    d[OVL_SITE - V2F:OVL_SITE - V2F + 5] = b"\xe9" + struct.pack("<i", where2["ovl"] - (OVL_SITE + 5))
    d[END_SITE - V2F:END_SITE - V2F + 5] = b"\xe9" + struct.pack("<i", where2["end"] - (END_SITE + 5))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, ".bak_smokescreen35")   # v3.2 10/17: the v3.1 state (.bak_smokescreen = pre-v1, 2 = v1, 3 = v2, 31 = v3)
    if a.dll == DEFAULT_DLL and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
