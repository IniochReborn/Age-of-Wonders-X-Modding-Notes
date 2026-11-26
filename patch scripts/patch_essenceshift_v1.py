#!/usr/bin/env python3
"""patch_essenceshift_v1.py - Essence Shift (spell 231, Cosmos L4 global, 2026-10-17; user spec: "Target mana node
(regular or elemental) transforms to the elemental node matching the caster's highest sphere count (or randomized
tiebreaker)").

The spell is a TRejuvenate clone (dual-sphere pipeline entry 231: donor TRejuvenate = a global HEX-target spell with a
cast effect + sound at the target).  This patch chains in FRONT of the per-spell caves of patch_terrain_spells_v1.py
(Rejuvenate 204 / Wither 205) at the vanilla TRejuvenate sites and handles id 231 itself; every other id passes
through to the previous owner unchanged.

RE (AoWEPACK unless noted):
  * Nodes (all TPlayerStructure descendants, on the map as structures):
      TPowerNode (regular mana node) VMT 0x557CFFE4 size 0x44, ClassID 0x2019A (resource 0x2019B)
      TLifeNode 0x20371 / TDeathNode 0x204AE / TEarthNode 0x204CE / TAirNode 0x2094E / TFireNode 0x203DE /
      TWaterNode 0x204B3 (elemental, TProductionPlace children, size 0x4C; resource ClassID = +1);
      TRandomNode 0x20822 (the editor's random node).  GetMagicSphere VMT+0x230: Life 1, Death 2, Earth 3, Air 4,
      Fire 5, Water 6 (Cosmos = 0, no Cosmos node).
  * Owner = byte [obj+0x30] (0xFF none); resource [obj+8]; main field [obj+4] (x/y/level bytes +0x10/+0x11/+0x12).
    SetPlayer VMT+0x1F0 (dl) - SetPlayer(0xFF) unregisters the structure from its owner's lists; RemoveFromMap
    VMT+0xB0; TObject.Free (thunk 0x557010B8) -> TStructure.Destroy (unregisters from the game, 0x557763C8).
  * Placement: the resource's VMT+0x68 = TPlayerStructureResource.PlaceResourceUser 0x55761A9C (eax res, edx map,
    cl x, push y, push level; ret 8) -> nil when the map refuses.  Resources: [[0x558FA044]+0x24]+8 (the list
    Tectonic's picker uses), matched by resource ClassID (VMT+0x24).  RandSeed is set from map.Random first (as
    TAoWHSMap.PlaceTerrain / Tectonic do) so any random art choice stays in MP sync.
  * Armies (guards) on the node hex would make HSEngine.TMapObject.CanPlace refuse (top HS priority >= 10; TArmyHS =
    0x1A).  This patch chains a wrapper in front of the TArmyHS VMT+0x64 slot (0x55713404, owned by
    patch_terrain_armyhooks_v1.py): while OUR flag ESS_FLAG is set and the caller is TMapObject.CanPlace (HSEPack
    `call [edx+0x64]` @0x55609CB5, return 0x55609CB8; HSEPack runtime base from the import slot 0x558FBEE4) it
    answers 9.  PLACE_FLAG (armyhooks, 0x5590B504) is set too, so the army CanChangeTerrain veto is lifted for our
    placement only.  REQUIRES patch_terrain_armyhooks_v1.py (applied live since 10/17).
  * Caster spheres: TPlayer [+0xD4] = the leader; [leader+0xA0] = the sphere pick byte list (TLeader.GetSpheres
    0x5578B1B4 / GetSphereCount 0x5578B1C4: items +4 (bytes), count +8).  count[s] = picks equal to s, s = 1..6.

BEHAVIOUR
  * Valid target (both TRejuvenate predicates, sites V1 0x5579F617 / V2 0x5579F63F): the base predicate holds AND
    the hex holds a node (any of the 8 classes, main hex or art hex) AND the caster's best-sphere set minus the
    node's own sphere is not empty (a node that already IS the caster's single best sphere cannot be targeted).
  * Execute (TRejuvenateTE +0x54 site EX 0x5579F3F8; eax = TE, edx = the casting TPlayer), before the vanilla body:
    best = the spheres 1..6 with the highest pick count (no elemental picks -> all six); the node's own sphere is
    removed; one is chosen with map.Random (only when >1 remain - synced, the TE runs in the synced turn).  The old
    node is unregistered from its owner, removed and freed; a node of the chosen sphere is placed at its main hex
    (first matching resource that the map accepts); the old owner is re-applied (guards stay on the hex, a captured
    owner keeps it, a neutral node stays neutral; a razed node comes back un-razed).  If no resource of the chosen
    type can be placed, the OLD resource is placed back (the spell is then a no-op).  TPlayer.UpdateIncome for the
    owner and the caster afterwards.
  * The vanilla body then plays the spell's own cast effect + sound at the target (pipeline gfx slot 0 / sfx 0);
    its terrain sweep is reduced to radius 0 (site R3 0x5579F4F8) and the per-hex terrain callback (site MAP
    0x5579F3E5) is a no-op for 231 -> no terrain changes.  The targeting preview is 1 hex (site SEL 0x5579F66B,
    RadToHN(1)).
  * Spell id read from [te+0x10] / [spell+0x10] or G_TSPELL (0x558E9B64, set by patch_terrain_spells_v1.py's own
    exec / sel caves which run AFTER ours) - MAP / SEL read G_TSPELL.

Zone AoWEPACK 0x5587F000..0x5587F800 (zero, reloc-free): header 'ESSHIFT1' + 6 x 8 B original site bytes + prio slot
dword; caves.  ESS_FLAG dword @0x5590BD00 (.idata page slack beyond the raw data = zero at load).
v2 2026-10-18 (user: "I should be able to cast it underground. And I should have to OWN the node to target it."):
  * UNDERGROUND: the only level block is TGlobalTargetSpell's target-error routine 0x5579E73C, which refuses a
    non-surface target when [spell+0x39] (surface-only flag, set to 1 by TRejuvenate.Create) != 0.  Cleared for 231
    ONLY by the pipeline poke (0x39, 1, 0) in entry 231 (no engine change; Rejuvenate / Wither / Scorch untouched).
    The predicates, the TE body and our exc are level-agnostic (level = [te+0x22]).
  * OWNERSHIP: both predicates (pred) refuse a node whose owner byte [node+0x30] != the casting player's index
    [spell+0x38] (unowned 0xFF / enemy refused); exc re-checks owner == [te+0x14] (the TE's player index) and then
    does nothing (the vanilla cast fx/sfx still play) - defence in depth.
  * Upgrade in place from v1 (header 'ESSHIFT1' accepted, same layout; sites/prio pointing into our zone = ours(old));
    backup .bak_essence2 = the v1 state; --revert from v1 or v2 restores the exact pre-v1 bytes.
v3 2026-10-18 (user: "targeting is weird - I shouldn't be able to target non-valid targets, no razed nodes either"
and "it doesn't actually work, nothing happens to nodes"):
  * ROOT CAUSE 'nothing happens': v2's exc owner check read [te+0x14] as the player index - but the TE init
    (0x55779884: [te+0x10] = spell id, [te+0x14] = [spell+0x14] = the spell's MANA value, byte [te+0x18] = the
    casting player's index [player+0x24], [te+0x1C] = [player+0x18]) stores the index at +0x18 -> the check never
    matched and every cast bailed out before the transform.  v3 compares [node+0x30] with byte [te+0x18].
  * CLICK VALIDITY: TGlobalTargetSpell's click handler (VMT+0xA0 0x5579E4E0, state 2) only asks VMT+0xAC before
    casting - and TRejuvenate's +0xAC is the inherited always-true 0x5579E4DC (the per-hex predicate +0xB0 only
    colours the preview).  v3 re-points the TRejuvenate VMT slot +0xAC (0x5579D5C0, relocated; shared by every
    TRejuvenate clone) to a cave `clk`: id 231 -> field of the selection (x/y/level = [sel+0x39]/[sel+0x3A]/[sel+0x3B])
    -> the spell's own +0xB0 predicate (base explored check + our pred); other ids -> the previous slot value.
  * RAZED: pred and exc also refuse a node whose GetRazed (VMT+0x150: TPowerNode [obj+0x3C]&1, elemental nodes
    [obj+0x48]==1) is true.
  * Header 'ESSHIFT3' (v1/v2 accepted); the old +0xAC value is stored at header +0x44 (zero padding in v1/v2 zones).
v4 2026-10-18 (user: "casting it on a node CRASHES the game now" - WER: two AppHangB1 'top level window is idle' at
01:52, no dump; and "targeting should be a wand with a red crossed-out circle when hovering an invalid hex, the wand
when over a valid node"):
  * ROOT CAUSE (static RE; v3 was the first build whose transform actually ran): v3 FREED the old node
    (SetPlayer(0xFF) + RemoveFromMap + TObject.Free) and placed a new one.  Vanilla NEVER frees a game structure at
    runtime (raze / rebuild / capture all work IN PLACE through TEs; the only RemoveFromMap+Free pairs in AoWEPACK are
    TItem / TAoWEngine destructors), so nothing that caches a structure pointer (TIWindow / the general's selection,
    AI target + PA caches, player 'seen' memory, token lists ...) is ever told - the next use of the freed node is a
    use-after-free -> the hang/lock.  Secondary: TAoWHSMap.Random (0x5577827C) pops Dialogs.ShowMessage('Invalid
    AoWHSMap.Random use') unless the map is synchronised - v3 called it for the art seed + tie-break inside the TE.
  * FIX: no structure is ever freed any more.
      - elemental -> elemental (TLife/TDeath/TEarth/TAir/TFire/TWaterNode share one layout: size 0x4C, same parent,
        VMTs identical except +0x24 ClassID / +0x180 / +0x230 GetMagicSphere): IN PLACE - SetPlayer(0xFF) under the
        old class (unregisters the sphere-specific power entries [obj+0x3C]/[obj+0x40]), swap [obj] = the target
        class VMT and [obj+8] = its resource (TPlayerStructure.Show draws via the resource every frame), re-create the
        shadow (VMT+0x190 TStructure.CreateShadow) when it had one, SetPlayer(owner) under the new class.  No
        placement, no army veto, no new object.
      - power node (TPowerNode 0x44, different hierarchy) -> elemental: SetPlayer(0xFF) + RemoveFromMap, the old object
        is RETIRED (kept alive, never freed: stale references stay valid), then the new node is placed as before
        (fallback: the old resource re-placed).  TRandomNode targets are refused (pred + exc).
      - [game+0x174] is zeroed around the SetPlayer round trip (SetPlayer only consults it to fire StructureCaptured
        VMT+0x214 -> no spurious 'captured / lost' events), restored afterwards; static scene invalidated ([map+0x30]).
      - Random wrapped in TAoWHSMap.SynchroniseBegin / End (0x557755F8 / 0x55775600) - harmless when already synced.
      - diag dwords @0x5590BD10 (.idata slack): +0 last stage reached (1 start, 2 events off, 3 unregistered /
        removed, 4 swapped / placed, 5 done, 9 sync ended), +4 casts, +8 path (1 in place, 2 replace), +0xC sphere.
  * CURSOR: TTargetSelectionControl.NewFrameEvent shows the animated wand (cursor 0x6E+) when its 'valid' flag is
    set and cursor 0x78 (the crossed-out wand) otherwise; the flag comes from ValidTarget (0x55763338), which calls
    the optional OnValidTarget method pointer [sel+0x18] (code) / [sel+0x1C] (data) - never set for global target
    spells.  selc (TRejuvenate SetupTargetSelection tail, esi = selection) now installs our vcb for 231 (data = the
    spell = [sel+0x14]) and removes it for other TRejuvenate clones; vcb answers via the spell's +0xB0 predicate and
    passes through untouched unless [sel+0x14] is still our spell (other spell classes never see a stale verdict).
  * Header 'ESSHIFT4' (v1..v3 accepted); upgrade backup .bak_essence4 = the previous state.
v5 2026-10-18 (user test of v4: power node -> "the gfx/sfx didn't play, ERROR WINDOWS popped up, then the node changed
to an elemental node - but the WRONG one (4 Fire spheres -> Death node)"; elemental node -> CRASH; "remove the red glow
dot, just the wand"; "it lets me target some hexes ADJACENT to nodes"):
  * ROOT CAUSES (static RE, no dump - the dialogs are the TE executor's exception reports):
      - the transform ran in exc = BEFORE the vanilla TE body, so any exception inside it aborted the whole TE: no
        cast fx (0x557FB300 effect) and no sound - exactly 'gfx/sfx didn't play + error windows'.
      - v4's power path left the old node's SHADOW (TStructure +0x28) on the map (RemoveFromMap does not touch it;
        TStructure.Destroy calls DestroyShadow VMT+0x194 first) - an orphan shadow of a structure no longer on the map
        is drawn every frame; and the map's structure listeners ([map+0x21C], TAoWHSMap.StructureDestroyed
        0x557763C8 - AI caches, the strategic panel ...) were never told the old node is gone.
      - v4's elemental IN-PLACE VMT swap: the elemental node constructor (0x557BE10C) builds sphere-specific members
        ([obj+0x44] production place object via VMT+0x224, [obj+0x40]/[obj+0x3C] power / production entries chosen by
        GetMagicSphere) - swapping only the VMT + resource leaves those members of the OLD sphere and re-runs
        CreateShadow on top of a live shadow -> the crash.
      - 'wrong sphere': the sphere counts and the TMagicSphere numbering (Cosmos 0, Life 1, Death 2, Earth 3, Air 4,
        Fire 5, Water 6) and the node ClassIDs / resources (+1) all check out; the choice is the caster's HIGHEST pick
        count with a synced random tie-break - a leader with as many (or more) Death picks than Fire picks legitimately
        gets Death.  v5 records the candidate mask + caster index in the diag block and essence_probe.py prints every
        leader's picks so this can be verified live.
      - adjacent hexes: f_find accepted a node child on ANY of its hexes (multi-hex footprint art hexes too).
  * FIX:
      - exc is a pure pass-through; the transform (xform) runs from r3c = AFTER TSpellTE.Process, the cast effect and
        the sound (site R3 0x5579F4F8, ebx = TE, esi = player), then the radius-0 sweep as before.
      - ONE path for every node: retire the old node (SetPlayer(0xFF) with [map+0x174] zeroed, DestroyShadow when it
        has one, RemoveFromMap, StructureDestroyed notify unless [map+0x3C]&8 - mirroring TStructure.Destroy - but
        NEVER freed), place the chosen type with PlaceResourceUser (the class constructor builds a complete node), own
        it; no VMT swap any more.  Diag path = 3.
      - Delphi try/except around the retire/place (System.@HandleAnyException / @DoneExcept idiom, registration
        [next, handler, ebp]): an exception is caught silently (diag bit 0x80, exception object at +0x14); if the old
        node was already retired and nothing was placed, a second guarded attempt re-places the OLD node type (0x20;
        0x40 if that raised too).  Flags / [map+0x174] / synchronise are always restored.
      - caster = the TE's player index (byte [te+0x18]) via GetPlayers (the same index the ownership check uses).
      - f_find only accepts a node whose MAIN field [node+4] is the hex (anchor hex only) - pred, click, cursor and
        the transform alike.
      - SEL: no preview entries for 231 (jump to the SetupTargetSelection epilogue 0x5579F68A) - no red highlight,
        the wand / crossed-wand cursor (vcb) stays.
      - diag dwords @0x5590BD10: +0 stage (1..5, 9) | 0x80 exception | 0x20 recovered | 0x40 recovery raised, +4 casts,
        +8 path 3, +0xC sphere, +0x10 candidate mask, +0x14 exception object, +0x18 targeted node ClassID,
        +0x1C caster index.  Read with essence_probe.py (read-only).
  * Header 'ESSHIFT5' (v1..v4 accepted); upgrade backup .bak_essence5 = the previous state.
v6 2026-10-18 (user: "gfx stops abruptly, it needs to smoothly fade out"; "cast on nodes UNDERGROUND they transform
correctly but the node gfx shows as a LUMP OF EARTH - use the underground node gfx underground / in the depths"):
  * ROOT CAUSE fade: the TRejuvenateTE cast effect is the particle emitter class [0x557FB300] (setup 0x557FC008 with
    the pushes 0x1E / 0x32 / 0x40 / 0x64 at 0x5579F450: [eff+0x40] = 100 particles, [eff+0x44] = 64 px radius,
    [eff+0x4C] = 30 = per-particle birth jitter Random(30), [eff+0x48] = 50 = LIFE).  Each frame (0x557FBE50) every
    particle shows the sequence at age = t - birth (GetUnloopedFrameIndex) and the emitter FREES ITSELF at t >= 50
    -> particles born late are only ~20 ticks into the 44 x 2-tick swirl2 when everything vanishes, the fade tail
    (frames 28-43) never shows.  FIX: new site FX 0x5579F488 (`movsx eax, byte [ebx+0x21] / push eax`, right after the
    setup, edi = the emitter) -> fxc: id 231 -> [edi+0x48] = FX_LIFE 120 (30 jitter + 88 + 2); replays the 5 bytes.
    Rejuvenate / Wither / Scorch keep 50.
  * ROOT CAUSE lump: every node class has TWO resources in Release.hss - tag 2 = Engine.TEResource [res+0x10] (editor
    group) 21 = surface art, 23 = underground art (e.g. TPowerNode cid 196 STR_NODE 0-8 vs cid 216 STR_NODE 5/8 cave
    art).  pcls took the FIRST matching resource = always the surface one.  FIX: pcls prefers the resource whose
    [res+0x10] == (level > 0 ? 23 : 21), then (pass 2) any matching resource - the old-node recovery re-place uses
    the same rule.  The retire path (shadow destroyed, removed, listeners told, static scene invalidated) leaves no
    stale art.
  * Header 'ESSHIFT6' (v1..v5 accepted); the FX site's original bytes at header +0x48; upgrade backup .bak_essence6.
LIFO: chained in front of patch_terrain_spells_v1.py (6 sites) and patch_terrain_armyhooks_v1.py (prio slot) - revert
this first before re-running either.  Dry-run default; --apply / --revert / --dis / --dll <path>.  Backup .bak_essence.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_essence"
BAK_SUFFIX2 = ".bak_essence2"          # v2 in-place upgrade: backup of the v1 state
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5587F000, 0x55880000   # v4: extended (0x5587F800..0x55880000 verified zero + reloc-free 10/18)
MAGIC = b"ESSHIFT8"                 # v8 10/18 altars IN PLACE + Pestilence = Earth; v7 10/18 altars; v6 10/18; v5 = ESSHIFT5 ... v1 = ESSHIFT1 (v6 adds the FX original bytes at header +0x48)
MAGICS = (b"ESSHIFT1", b"ESSHIFT2", b"ESSHIFT3", b"ESSHIFT4", b"ESSHIFT5", b"ESSHIFT6", b"ESSHIFT7", b"ESSHIFT8")
BAK_SUFFIX8 = ".bak_essence8"          # v8 in-place upgrade: backup of the v1..v7 state
BAK_SUFFIX7 = ".bak_essence7"          # v7 in-place upgrade: backup of the v1..v6 state
BAK_SUFFIX6 = ".bak_essence6"          # v6 in-place upgrade: backup of the v1..v5 state
# v6: cast-effect lifetime site (TRejuvenateTE body, right after the particle effect setup 0x557FC008: `movsx eax, byte [ebx+0x21] / push eax`)
FX_SITE, FX_VANILLA, FX_RESUME, FX_HDR = 0x5579F488, bytes.fromhex("0fbe432150"), 0x5579F48D, 0x48
FX_LIFE = 120                        # v6: particle effect life in ticks for 231: birth jitter Random(30) + 44 frames x 2 ticks + 2
GROUP_SURFACE, GROUP_UG = 21, 23     # v6: Release.hss resource tag 2 = [res+0x10] (Engine.TEResource.ReadWrite): node resources come in pairs, group 21 = surface art, 23 = underground (cave) art
BAK_SUFFIX5 = ".bak_essence5"          # v5 in-place upgrade: backup of the v1..v4 state
SEL_EMPTY = 0x5579F68A               # v5: TRejuvenate SetupTargetSelection epilogue (pop esi / pop ebx / ret) = no preview entries
HANY, DONEEXC = 0x557010E8, 0x55701108   # v5: thunks System.@HandleAnyException / System.@DoneExcept (Delphi try/except idiom)
STRUCT_DESTROYED = 0x557763C8        # v5: TAoWHSMap.StructureDestroyed (eax map, edx structure): notifies [map+0x21C] listeners
BAK_SUFFIX4 = ".bak_essence4"          # v4 in-place upgrade: backup of the v1/v2/v3 state
SYNC_BEGIN, SYNC_END = 0x557755F8, 0x55775600   # TAoWHSMap.SynchroniseBegin / SynchroniseEnd (inc / dec [map+0x234])
DIAG = 0x5590BD10                    # v4 diag dwords (.idata page slack beyond the raw data, zero at load)
# v4: elemental node class VMTs (same layout, size 0x4C) by GetMagicSphere value
SPH_VMT = {1: 0x557C046C, 2: 0x557BFFA4, 3: 0x557BFAE0, 4: 0x557C0DF4, 5: 0x557BF624, 6: 0x557C092C}
BAK_SUFFIX3 = ".bak_essence3"          # v3 in-place upgrade: backup of the v1/v2 state
CLK_SLOT = 0x5579D5C0                # TRejuvenate VMT 0x5579D514 + 0xAC (click validity; vanilla 0x5579E4DC = always true)
CLK_HDR = 0x44                      # header offset of the stored original +0xAC value (v3)
SPELL_ID = 231
SITES = (("EX", 0x5579F3F8, "jmp"), ("MAP", 0x5579F3E5, "call"), ("V1", 0x5579F617, "call"),
         ("V2", 0x5579F63F, "call"), ("R3", 0x5579F4F8, "jmp"), ("SEL", 0x5579F66B, "jmp"))
PRIO_SLOT = 0x55713404
R3_RESUME, SEL_RESUME = 0x5579F4FF, 0x5579F670
MAPVAR, GAME, RESG, G_TSPELL = 0x558E9494, 0x558FA040, 0x558FA044, 0x558E9B64
PLACE_FLAG, ESS_FLAG, RANDSEED_SLOT = 0x5590B504, 0x5590BD00, 0x558FB720
HSE_IMPORT, HSE_IMPORT_PREF, HSE_CANPLACE_RET = 0x558FBEE4, 0x5560824C, 0x55609CB8
GETMAPLEVEL, GETFIELD, GETPLAYERS, UPDATEINCOME, RANDOM, FREE = (0x557020EC, 0x557020DC, 0x557544D0, 0x55751F88,
                                                                 0x5577827C, 0x557010B8)
NODES = ((0x20371, 1), (0x204AE, 2), (0x204CE, 3), (0x2094E, 4), (0x203DE, 5), (0x204B3, 6), (0x2019A, 0), (0x20822, 7))
SPH_CID = {1: 0x20371, 2: 0x204AE, 3: 0x204CE, 4: 0x2094E, 5: 0x203DE, 6: 0x204B3}
# v7 10/18 (user: "also target ALTARS and change their element similarly"): the six vanilla altar classes (TAltar
# subclasses; ClassID = VMT+0x24, resource ClassID = +1).  Their element = the sphere of the storm spell each one
# raises (vanilla Spells.pfs: Divine Storm 1 Life, Death Storm 2 / Pestilence 2 Death, Lightning Storm 4 Air,
# Fire Storm 5, Blizzard 6 Water) - there is NO Earth altar.  f_sph returns 0x100 | sphere for an altar.
ALTARS = ((0x20233, 1), (0x20235, 2), (0x2030C, 3), (0x2023D, 4), (0x2023A, 5), (0x2024B, 6))
ALT_CID = {1: 0x20233, 2: 0x20235, 3: 0x2030C, 4: 0x2023D, 5: 0x2023A, 6: 0x2024B}   # target altar per sphere (Death -> Altar of Death)
ALT_MASK = sum(1 << s for s in ALT_CID)            # v8: 0x7E (all six spheres have an altar)
# v8 10/18 (user: "casting it on an altar just makes them DISAPPEAR, not transform; Pestilence altar = EARTH"):
#   Pestilence = Earth (3).  The six altar classes (TAltarOfLife 0x557D1BCC / Death 0x557D2094 / Pestilence 0x557D255C /
#   Lightning 0x557D16F4 / Fire 0x557CF5F8 / Ice 0x557CFAF0, all TAltar 0x557CE7C4 children, instance size 0x44) differ
#   ONLY in VMT+0x24 ClassID and +0x224 (the storm-spell factory: a fresh TSpell each call, no cached state;
#   TAltarOfFire's +0x20 ctor override just calls the inherited one).  So an altar is shifted IN PLACE: SetPlayer(0xFF),
#   destroy the shadow (VMT+0x194), [obj] = target class VMT, [obj+8] = its resource (Release.hss: one resource per
#   altar, ClassID = object ClassID + 1, group 21), re-create the shadow (VMT+0x190) when it had one, SetPlayer(owner).
#   Nothing is removed from the map or placed, so the altar can never be lost (v7 removed the old altar first and the
#   CreateAndPlace of the new one - and the fallback re-place of the old one - both failed: the altar vanished).
ALT_VMT = {1: 0x557D1BCC, 2: 0x557D2094, 3: 0x557D255C, 4: 0x557D16F4, 5: 0x557CF5F8, 6: 0x557CFAF0}

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    """Assemble; every `call $D / pop R / sub R, $D` triple gets its anchor (the VA after the call) patched in."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0])
    k = 0
    while True:
        k = b.find(b"\xe8\x00\x00\x00\x00", k)
        if k < 0: break
        if 0x58 <= b[k + 5] <= 0x5F:
            if b[k + 6] == 0x2D and b[k + 7:k + 11] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 7, va + k + 5)
            elif b[k + 6] == 0x81 and b[k + 8:k + 12] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 8, va + k + 5)
        k += 5
    assert b"\xff\xff\xff\x7f" not in b, "unpatched PIC anchor"
    return bytes(b)


def rel_target(site, raw):
    return site + 5 + struct.unpack_from("<i", raw, 1)[0]


def build(orig, prio_orig, clk_orig, fx_orig=FX_VANILLA):
    """orig = {name: 5 original bytes}; prio_orig / clk_orig = the slots' previous pointers; fx_orig = the FX site's 5 bytes."""
    prev = {n: rel_target(va, orig[n]) for n, va, _ in SITES}
    hdr = bytearray(MAGIC + bytes(8))
    for n, va, _ in SITES: hdr += orig[n] + bytes(3)
    hdr += struct.pack("<I", prio_orig)
    assert len(hdr) == CLK_HDR
    hdr += struct.pack("<I", clk_orig)
    hdr += fx_orig + bytes(3)                 # v6: FX site original bytes at header +0x48
    out = bytearray(hdr); where = {}
    C = dict(sbeg=SYNC_BEGIN, send=SYNC_END, diag=DIAG, id=SPELL_ID, mapvar=MAPVAR, game=GAME, resg=RESG, gts=G_TSPELL, pflag=PLACE_FLAG, eflag=ESS_FLAG,
             rseed=RANDSEED_SLOT, himp=HSE_IMPORT, hpref=HSE_IMPORT_PREF, hret=HSE_CANPLACE_RET,
             getlevel=GETMAPLEVEL, getfield=GETFIELD, getpl=GETPLAYERS, updinc=UPDATEINCOME, rnd=RANDOM, free=FREE,
             r3res=R3_RESUME, selres=SEL_RESUME, prio_prev=prio_orig, clk_prev=clk_orig, selempty=SEL_EMPTY,
             hany=HANY, doneexc=DONEEXC, sdes=STRUCT_DESTROYED, fxlife=FX_LIFE, fxres=FX_RESUME, gsurf=GROUP_SURFACE, gug=GROUP_UG,
             altmask=ALT_MASK, **{"p_" + n.lower(): prev[n] for n, _, _ in SITES})
    nodecmp = "\n".join("        cmp eax, %#x\n        je sp_%d" % (cid, s) for cid, s in NODES)
    noderet = "\n".join("    sp_%d:\n        mov eax, %d\n        ret" % (s, s) for _, s in NODES)
    nodecmp += "\n" + "\n".join("        cmp eax, %#x\n        je sa_%x" % (cid, cid) for cid, s in ALTARS)       # v7
    noderet += "\n" + "\n".join("    sa_%x:\n        mov eax, %#x\n        ret" % (cid, 0x100 | s) for cid, s in ALTARS)
    acidcmp = "\n".join("        cmp eax, %d\n        jne ad_n%d\n        mov eax, %#x\n        ret\n    ad_n%d:" % (s, s, cid, s)
                       for s, cid in ALT_CID.items())
    vmtcmp = "\n".join("        cmp eax, %d\n        jne vt_n%d\n        mov eax, %#x\n        ret\n    vt_n%d:" % (s, s, v, s)
                       for s, v in SPH_VMT.items())
    cidcmp = "\n".join("        cmp eax, %d\n        jne cd_n%d\n        mov eax, %#x\n        ret\n    cd_n%d:" % (s, s, cid, s)
                       for s, cid in SPH_CID.items())

    avmtcmp = chr(10).join(("        cmp eax, %d" + chr(10) + "        jne av_n%d" + chr(10) + "        mov eax, %#x" + chr(10) + "        ret" + chr(10) + "    av_n%d:") % (s, s, v, s) for s, v in ALT_VMT.items())

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm_pic(src % C, va))
    # one unit holds every routine (shared labels); the entry points get their own names below
    src = """
    clk:
        cmp dword ptr [eax+0x10], %(id)d
        jne ck_prev
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        test esi, esi
        jz ck_no
        call getd
        mov ecx, dword ptr [eax+%(mapvar)#x]
        test ecx, ecx
        jz ck_no
        mov ecx, dword ptr [ecx]
        test ecx, ecx
        jz ck_no
        mov eax, dword ptr [ecx+0x10]
        movsx edx, byte ptr [esi+0x3b]
        call %(getlevel)#x
        test eax, eax
        jz ck_no
        mov edi, eax
        movsx edx, byte ptr [esi+0x39]
        movsx ecx, byte ptr [esi+0x3a]
        test edx, edx
        js ck_no
        test ecx, ecx
        js ck_no
        cmp edx, dword ptr [edi+0xc]
        jge ck_no
        cmp ecx, dword ptr [edi+0x10]
        jge ck_no
        mov eax, edi
        call %(getfield)#x
        test eax, eax
        jz ck_no
        mov edx, eax
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0xb0]
        jmp ck_out
    ck_no:
        xor eax, eax
    ck_out:
        pop edi
        pop esi
        pop ebx
        ret
    ck_prev:
        jmp %(clk_prev)#x

    getd:
        call $D
        pop eax
        sub eax, $D
        ret

    f_sph:
        test eax, eax
        jz sp_no
        mov eax, dword ptr [eax]
        push ecx
        push edx
        call dword ptr [eax+0x24]
        pop edx
        pop ecx
%(nodecmp)s
    sp_no:
        or eax, -1
        ret
%(noderet)s

    f_cid:
%(cidcmp)s
        xor eax, eax
        ret

    f_acid:
%(acidcmp)s
        xor eax, eax
        ret

    f_avmt:
%(avmtcmp)s
        xor eax, eax
        ret

    rfind:
        push ebx
        push esi
        push edi
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+%(resg)#x]
        test eax, eax
        jz rf_none
        mov eax, dword ptr [eax+0x24]
        test eax, eax
        jz rf_none
        mov eax, dword ptr [eax+8]
        test eax, eax
        jz rf_none
        mov esi, dword ptr [eax+4]
        mov edi, dword ptr [eax+8]
        test esi, esi
        jz rf_none
        xor ebx, ebx
    rf_lp:
        cmp ebx, edi
        jge rf_none
        mov eax, dword ptr [esi+ebx*4]
        test eax, eax
        jz rf_nx
        push eax
        mov eax, dword ptr [eax]
        call dword ptr [eax+0x24]
        cmp eax, dword ptr [ebp-0x34]
        pop eax
        je rf_out
    rf_nx:
        inc ebx
        jmp rf_lp
    rf_none:
        xor eax, eax
    rf_out:
        pop edi
        pop esi
        pop ebx
        ret

    xa_ip:
        mov eax, dword ptr [ebp-0x34]
        call rfind
        test eax, eax
        jz xa_none
        mov dword ptr [ebp-0x40], eax
        mov eax, dword ptr [ebp-0x1c]
        call f_avmt
        test eax, eax
        jz xa_none
        add eax, dword ptr [ebp-4]
        mov dword ptr [ebp-0x18], eax
        mov dword ptr [ebp-0x48], 0
        call getd
        lea ecx, [eax+xf_hnd3]
        xor eax, eax
        push ebp
        push ecx
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x], 2
        mov dword ptr [edx+%(diag)#x+8], 4
        cmp dword ptr [ebp-0x20], 0xff
        je xa_nounreg
        mov eax, ebx
        mov dl, 0xff
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x1f0]
    xa_nounreg:
        cmp dword ptr [ebx+0x28], 0
        je xa_nosh
        mov dword ptr [ebp-0x48], 1
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x194]
    xa_nosh:
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x], 3
        mov eax, dword ptr [ebp-0x18]
        mov dword ptr [ebx], eax
        mov eax, dword ptr [ebp-0x40]
        mov dword ptr [ebx+8], eax
        cmp dword ptr [ebp-0x48], 0
        je xa_nosh2
        cmp dword ptr [ebx+0x28], 0
        jne xa_nosh2
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x190]
    xa_nosh2:
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x], 4
        cmp dword ptr [ebp-0x20], 0xff
        je xa_end
        mov eax, ebx
        mov dl, byte ptr [ebp-0x20]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x1f0]
    xa_end:
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp xf_clean
    xf_hnd3:
        jmp %(hany)#x
        mov edx, dword ptr [ebp-4]
        or dword ptr [edx+%(diag)#x], 0x80
        mov dword ptr [edx+%(diag)#x+0x14], eax
        call %(doneexc)#x
        jmp xf_clean
    xa_none:
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x+8], 5
        jmp xf_clean

    vcb:
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov edi, dword ptr [esp+0x10]
        test ebx, ebx
        jz vc_ret
        test esi, esi
        jz vc_ret
        cmp dword ptr [esi+0x14], ebx
        jne vc_ret
        cmp dword ptr [ebx+0x10], %(id)d
        jne vc_ret
        test edi, edi
        jz vc_ret
        cmp byte ptr [edi], 0
        je vc_ret
        push ecx
        call getd
        mov eax, dword ptr [eax+%(mapvar)#x]
        test eax, eax
        jz vc_badp
        mov eax, dword ptr [eax]
        test eax, eax
        jz vc_badp
        mov eax, dword ptr [eax+0x10]
        movsx edx, byte ptr [esp+0x18]
        call %(getlevel)#x
        test eax, eax
        jz vc_badp
        movsx edx, byte ptr [esp]
        movsx ecx, byte ptr [esp+0x1c]
        test edx, edx
        js vc_badp
        test ecx, ecx
        js vc_badp
        cmp edx, dword ptr [eax+0xc]
        jge vc_badp
        cmp ecx, dword ptr [eax+0x10]
        jge vc_badp
        call %(getfield)#x
        pop ecx
        test eax, eax
        jz vc_bad
        mov edx, eax
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0xb0]
        mov byte ptr [edi], al
        jmp vc_ret
    vc_badp:
        pop ecx
    vc_bad:
        mov byte ptr [edi], 0
    vc_ret:
        pop edi
        pop esi
        pop ebx
        ret 0xc

    f_find:
        push ebx
        push esi
        push edi
        mov esi, eax
        xor edi, edi
        test esi, esi
        jz ff_none
    ff_lp:
        movzx eax, byte ptr [esi+0xd]
        cmp edi, eax
        jge ff_none
        mov eax, dword ptr [esi+8]
        mov ebx, dword ptr [eax+edi*4]
        test ebx, ebx
        jz ff_nx
        mov eax, ebx
        call f_sph
        test eax, eax
        jns ff_hit
    ff_nx:
        inc edi
        jmp ff_lp
    ff_hit:
        cmp dword ptr [ebx+4], esi
        jne ff_nx
        mov eax, ebx
        jmp ff_out
    ff_none:
        xor eax, eax
    ff_out:
        pop edi
        pop esi
        pop ebx
        ret

    f_mask:
        push ebx
        push esi
        sub esp, 8
        mov dword ptr [esp], 0
        mov dword ptr [esp+4], 0
        test eax, eax
        jz fm_cd
        mov eax, dword ptr [eax+0xd4]
        test eax, eax
        jz fm_cd
        mov eax, dword ptr [eax+0xa0]
        test eax, eax
        jz fm_cd
        mov ecx, dword ptr [eax+8]
        mov esi, dword ptr [eax+4]
        test esi, esi
        jz fm_cd
        cmp ecx, 64
        ja fm_cd
    fm_lp:
        dec ecx
        js fm_cd
        movzx edx, byte ptr [esi+ecx]
        cmp edx, 1
        jb fm_lp
        cmp edx, 6
        ja fm_lp
        inc byte ptr [esp+edx]
        jmp fm_lp
    fm_cd:
        xor ebx, ebx
        mov ecx, 1
    fm_mx:
        movzx edx, byte ptr [esp+ecx]
        cmp edx, ebx
        jbe fm_mx2
        mov ebx, edx
    fm_mx2:
        inc ecx
        cmp ecx, 7
        jb fm_mx
        xor eax, eax
        mov ecx, 1
    fm_mk:
        movzx edx, byte ptr [esp+ecx]
        cmp edx, ebx
        jne fm_mk2
        bts eax, ecx
    fm_mk2:
        inc ecx
        cmp ecx, 7
        jb fm_mk
        add esp, 8
        pop esi
        pop ebx
        ret

    pred:
        pushfd
        cmp dword ptr [ebx+0x10], %(id)d
        jne pr_prev
        popfd
        test al, al
        jz pr_ret0
        pushal
        mov eax, esi
        call f_find
        test eax, eax
        jz pr_no
        mov cl, byte ptr [ebx+0x38]
        cmp byte ptr [eax+0x30], cl
        jne pr_no
        push eax
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x150]
        test al, al
        pop eax
        jnz pr_no
        call f_sph
        mov ebp, eax
        cmp ebp, 7
        je pr_no
        call getd
        mov ecx, dword ptr [eax+%(game)#x]
        test ecx, ecx
        jz pr_nopl
        mov eax, dword ptr [ecx+0x140]
        test eax, eax
        jz pr_nopl
        movsx edx, byte ptr [ebx+0x38]
        call %(getpl)#x
        jmp pr_m
    pr_nopl:
        xor eax, eax
    pr_m:
        call f_mask
        mov ecx, ebp
        and ecx, 0xff
        test ebp, 0x100
        jz pr_nalt
        and eax, %(altmask)#x
    pr_nalt:
        cmp ecx, 1
        jb pr_chk
        cmp ecx, 6
        ja pr_chk
        btr eax, ecx
    pr_chk:
        test eax, eax
        jz pr_no
        popal
        mov al, 1
        ret
    pr_no:
        popal
    pr_ret0:
        xor eax, eax
        ret
    pr_prev:
        popfd
        jmp %(p_v1)#x

    mapc:
        push eax
        call getd
        cmp dword ptr [eax+%(gts)#x], %(id)d
        pop eax
        je mp_ret
        jmp %(p_map)#x
    mp_ret:
        ret

    r3c:
        cmp dword ptr [ebx+0x10], %(id)d
        jne r3_prev
        pushal
        mov eax, ebx
        mov edx, esi
        call xform
        popal
        movsx eax, byte ptr [ebx+0x22]
        push eax
        push 0
        jmp %(r3res)#x
    r3_prev:
        jmp %(p_r3)#x

    selc:
        push eax
        push ebx
        call getd
        lea ebx, [eax+vcb]
        cmp dword ptr [eax+%(gts)#x], %(id)d
        jne sl_other
        test esi, esi
        jz sl_set_done
        mov dword ptr [esi+0x18], ebx
        mov ebx, dword ptr [esi+0x14]
        mov dword ptr [esi+0x1c], ebx
    sl_set_done:
        pop ebx
        pop eax
        jmp %(selempty)#x
    sl_other:
        test esi, esi
        jz sl_prev
        cmp dword ptr [esi+0x18], ebx
        jne sl_prev
        mov dword ptr [esi+0x18], 0
        mov dword ptr [esi+0x1c], 0
    sl_prev:
        pop ebx
        pop eax
        jmp %(p_sel)#x

    prio:
        push eax
        push ecx
        call getd
        cmp dword ptr [eax+%(eflag)#x], 0
        je pp_prev
        mov ecx, dword ptr [eax+%(himp)#x]
        sub ecx, %(hpref)#x
        add ecx, %(hret)#x
        cmp dword ptr [esp+8], ecx
        jne pp_prev
        pop ecx
        pop eax
        mov al, 9
        ret
    pp_prev:
        pop ecx
        pop eax
        jmp %(prio_prev)#x

    exc:
        jmp %(p_ex)#x

    xform:
        pushal
        mov ebp, esp
        sub esp, 0x60
        xor ecx, ecx
        mov dword ptr [ebp-0xc], ecx
        mov dword ptr [ebp-0x38], ecx
        mov dword ptr [ebp-0x40], ecx
        mov dword ptr [ebp-0x44], ecx
        mov dword ptr [ebp-0x4c], ecx
        mov dword ptr [ebp-0x50], ecx
        mov dword ptr [ebp-0x20], 0xff
        mov dword ptr [ebp-0x14], eax
        mov dword ptr [ebp-0x10], edx
        call getd
        mov dword ptr [ebp-4], eax
        mov ecx, dword ptr [eax+%(mapvar)#x]
        test ecx, ecx
        jz xf_out
        mov ecx, dword ptr [ecx]
        test ecx, ecx
        jz xf_out
        mov dword ptr [ebp-8], ecx
        mov eax, ecx
        call %(sbeg)#x
        mov dword ptr [ebp-0x38], 1
        mov esi, dword ptr [ebp-0x14]
        movzx edx, byte ptr [esi+0x18]
        mov eax, dword ptr [ebp-4]
        mov dword ptr [eax+%(diag)#x+0x1c], edx
        mov eax, dword ptr [eax+%(game)#x]
        test eax, eax
        jz xf_nopl
        mov eax, dword ptr [eax+0x140]
        test eax, eax
        jz xf_nopl
        movsx edx, byte ptr [esi+0x18]
        call %(getpl)#x
        test eax, eax
        jz xf_nopl
        mov dword ptr [ebp-0x10], eax
    xf_nopl:
        mov esi, dword ptr [ebp-0x14]
        mov eax, dword ptr [ebp-8]
        mov eax, dword ptr [eax+0x10]
        movsx edx, byte ptr [esi+0x22]
        call %(getlevel)#x
        test eax, eax
        jz xf_out
        mov edi, eax
        movsx edx, byte ptr [esi+0x20]
        movsx ecx, byte ptr [esi+0x21]
        test edx, edx
        js xf_out
        test ecx, ecx
        js xf_out
        cmp edx, dword ptr [edi+0xc]
        jge xf_out
        cmp ecx, dword ptr [edi+0x10]
        jge xf_out
        mov eax, edi
        call %(getfield)#x
        test eax, eax
        jz xf_out
        call f_find
        test eax, eax
        jz xf_out
        mov ecx, dword ptr [ebp-0x14]
        mov cl, byte ptr [ecx+0x18]
        cmp byte ptr [eax+0x30], cl
        jne xf_out
        push eax
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x150]
        test al, al
        pop eax
        jnz xf_out
        mov dword ptr [ebp-0xc], eax
        call f_sph
        mov ebx, eax
        cmp ebx, 7
        je xf_out
        mov ecx, ebx
        and ecx, 0x100
        mov dword ptr [ebp-0x50], ecx
        mov eax, dword ptr [ebp-0x10]
        call f_mask
        mov ecx, ebx
        and ecx, 0xff
        cmp dword ptr [ebp-0x50], 0
        je xf_nalt
        and eax, %(altmask)#x
    xf_nalt:
        cmp ecx, 1
        jb xf_m1
        cmp ecx, 6
        ja xf_m1
        btr eax, ecx
    xf_m1:
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x+0x10], eax
        test eax, eax
        jz xf_out
        mov dword ptr [ebp-0x18], eax
        xor ecx, ecx
        mov edx, eax
    xf_pc:
        test edx, edx
        jz xf_pcd
        mov ebx, edx
        dec ebx
        and edx, ebx
        inc ecx
        jmp xf_pc
    xf_pcd:
        xor eax, eax
        cmp ecx, 1
        je xf_pick
        mov edx, ecx
        mov eax, dword ptr [ebp-8]
        call %(rnd)#x
    xf_pick:
        mov edx, dword ptr [ebp-0x18]
        mov ecx, 1
    xf_pk:
        bt edx, ecx
        jnc xf_pkn
        test eax, eax
        jz xf_pkd
        dec eax
    xf_pkn:
        inc ecx
        cmp ecx, 7
        jb xf_pk
        jmp xf_out
    xf_pkd:
        mov dword ptr [ebp-0x1c], ecx
        mov edx, dword ptr [ebp-4]
        inc dword ptr [edx+%(diag)#x+4]
        mov dword ptr [edx+%(diag)#x+0xc], ecx
        mov dword ptr [edx+%(diag)#x+8], 3
        mov dword ptr [edx+%(diag)#x], 1
        mov dword ptr [edx+%(diag)#x+0x14], 0
        mov ebx, dword ptr [ebp-0xc]
        mov eax, dword ptr [ebx]
        call dword ptr [eax+0x24]
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x+0x18], eax
        mov eax, dword ptr [ebx+8]
        mov dword ptr [ebp-0x24], eax
        mov eax, dword ptr [ebx+4]
        test eax, eax
        jz xf_out
        movzx edx, byte ptr [eax+0x10]
        mov dword ptr [ebp-0x28], edx
        movzx edx, byte ptr [eax+0x11]
        mov dword ptr [ebp-0x2c], edx
        movzx edx, byte ptr [eax+0x12]
        mov dword ptr [ebp-0x30], edx
        mov eax, dword ptr [ebp-0x1c]
        cmp dword ptr [ebp-0x50], 0
        jne xf_acid
        call f_cid
        jmp xf_cidd
    xf_acid:
        call f_acid
    xf_cidd:
        test eax, eax
        jz xf_out
        inc eax
        mov dword ptr [ebp-0x34], eax
        mov edx, dword ptr [ebp-4]
        mov edx, dword ptr [edx+%(game)#x]
        test edx, edx
        jz xf_out
        movzx eax, byte ptr [ebx+0x30]
        mov dword ptr [ebp-0x20], eax
        mov eax, dword ptr [edx+0x174]
        mov dword ptr [ebp-0x3c], eax
        mov dword ptr [edx+0x174], 0
        mov dword ptr [ebp-0x4c], 1
        cmp dword ptr [ebp-0x50], 0
        jne xa_ip
        call getd
        lea ecx, [eax+xf_hnd]
        xor eax, eax
        push ebp
        push ecx
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x], 2
        cmp dword ptr [ebp-0x20], 0xff
        je xr_nounreg
        mov eax, ebx
        mov dl, 0xff
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x1f0]
    xr_nounreg:
        cmp dword ptr [ebx+0x28], 0
        je xr_nosh
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x194]
    xr_nosh:
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0xb0]
        mov dword ptr [ebp-0x44], 1
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+%(game)#x]
        test byte ptr [eax+0x3c], 8
        jnz xr_nodes
        mov edx, ebx
        call %(sdes)#x
    xr_nodes:
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x], 3
        call pcls
        test eax, eax
        jnz xr_placed
        mov eax, dword ptr [ebp-0x24]
        call pres
        test eax, eax
        jz xr_end
    xr_placed:
        mov dword ptr [ebp-0x40], eax
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(diag)#x], 4
        cmp dword ptr [ebp-0x20], 0xff
        je xr_end
        mov ecx, dword ptr [eax]
        mov dl, byte ptr [ebp-0x20]
        call dword ptr [ecx+0x1f0]
    xr_end:
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp xf_clean
    xf_hnd:
        jmp %(hany)#x
        mov edx, dword ptr [ebp-4]
        or dword ptr [edx+%(diag)#x], 0x80
        mov dword ptr [edx+%(diag)#x+0x14], eax
        call %(doneexc)#x
        cmp dword ptr [ebp-0x44], 0
        je xf_clean
        cmp dword ptr [ebp-0x40], 0
        jne xf_clean
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(pflag)#x], 0
        mov dword ptr [edx+%(eflag)#x], 0
        call getd
        lea ecx, [eax+xf_hnd2]
        xor eax, eax
        push ebp
        push ecx
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        mov eax, dword ptr [ebp-0x24]
        call pres
        test eax, eax
        jz xr2_end
        mov dword ptr [ebp-0x40], eax
        mov edx, dword ptr [ebp-4]
        or dword ptr [edx+%(diag)#x], 0x20
        cmp dword ptr [ebp-0x20], 0xff
        je xr2_end
        mov ecx, dword ptr [eax]
        mov dl, byte ptr [ebp-0x20]
        call dword ptr [ecx+0x1f0]
    xr2_end:
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp xf_clean
    xf_hnd2:
        jmp %(hany)#x
        mov edx, dword ptr [ebp-4]
        or dword ptr [edx+%(diag)#x], 0x40
        call %(doneexc)#x
    xf_clean:
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(pflag)#x], 0
        mov dword ptr [edx+%(eflag)#x], 0
        test dword ptr [edx+%(diag)#x], 0xe0
        jnz xc_st
        mov dword ptr [edx+%(diag)#x], 5
    xc_st:
        cmp dword ptr [ebp-0x4c], 0
        je xc_n174
        mov edx, dword ptr [edx+%(game)#x]
        mov eax, dword ptr [ebp-0x3c]
        mov dword ptr [edx+0x174], eax
    xc_n174:
        mov eax, dword ptr [ebp-8]
        mov byte ptr [eax+0x30], 1
        cmp dword ptr [ebp-0x20], 0xff
        je xc_inc2
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+%(game)#x]
        mov eax, dword ptr [eax+0x140]
        test eax, eax
        jz xc_inc2
        mov edx, dword ptr [ebp-0x20]
        call %(getpl)#x
        test eax, eax
        jz xc_inc2
        call %(updinc)#x
    xc_inc2:
        mov eax, dword ptr [ebp-0x10]
        test eax, eax
        jz xf_out
        call %(updinc)#x
    xf_out:
        cmp dword ptr [ebp-0x38], 0
        je xf_out2
        mov eax, dword ptr [ebp-8]
        call %(send)#x
        mov edx, dword ptr [ebp-4]
        cmp dword ptr [edx+%(diag)#x], 5
        jne xf_out2
        mov dword ptr [edx+%(diag)#x], 9
    xf_out2:
        mov esp, ebp
        popal
        ret

    pres:
        push esi
        mov esi, eax
        test esi, esi
        jz ps_none
        mov eax, dword ptr [ebp-8]
        mov edx, 0xffffff
        call %(rnd)#x
        mov edx, dword ptr [ebp-4]
        mov edx, dword ptr [edx+%(rseed)#x]
        mov dword ptr [edx], eax
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(pflag)#x], 1
        mov dword ptr [edx+%(eflag)#x], 1
        push dword ptr [ebp-0x2c]
        push dword ptr [ebp-0x30]
        mov cl, byte ptr [ebp-0x28]
        mov edx, dword ptr [ebp-8]
        mov eax, esi
        mov esi, dword ptr [eax]
        call dword ptr [esi+0x68]
        mov edx, dword ptr [ebp-4]
        mov dword ptr [edx+%(pflag)#x], 0
        mov dword ptr [edx+%(eflag)#x], 0
        pop esi
        ret
    ps_none:
        xor eax, eax
        pop esi
        ret

    pcls:
        push ebx
        push edi
        push esi
        sub esp, 4
        mov eax, %(gsurf)d
        cmp dword ptr [ebp-0x30], 0
        je pc_g
        mov eax, %(gug)d
    pc_g:
        mov dword ptr [esp], eax
        call pc_scan
        test eax, eax
        jnz pc_done
        mov dword ptr [esp], -1
        call pc_scan
    pc_done:
        add esp, 4
        pop esi
        pop edi
        pop ebx
        ret

    pc_scan:
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+%(resg)#x]
        test eax, eax
        jz ps2_none
        mov eax, dword ptr [eax+0x24]
        test eax, eax
        jz ps2_none
        mov eax, dword ptr [eax+8]
        test eax, eax
        jz ps2_none
        mov esi, dword ptr [eax+4]
        mov edi, dword ptr [eax+8]
        test esi, esi
        jz ps2_none
        xor ebx, ebx
    ps2_lp:
        cmp ebx, edi
        jge ps2_none
        mov eax, dword ptr [esi+ebx*4]
        test eax, eax
        jz ps2_nx
        push eax
        mov eax, dword ptr [eax]
        call dword ptr [eax+0x24]
        cmp eax, dword ptr [ebp-0x34]
        pop eax
        jne ps2_nx
        mov ecx, dword ptr [esp+4]
        cmp ecx, -1
        je ps2_take
        cmp ecx, dword ptr [eax+0x10]
        jne ps2_nx
    ps2_take:
        call pres
        test eax, eax
        jnz ps2_out
    ps2_nx:
        inc ebx
        jmp ps2_lp
    ps2_none:
        xor eax, eax
    ps2_out:
        ret

    fxc:
        cmp dword ptr [ebx+0x10], %(id)d
        jne fx_o
        mov dword ptr [edi+0x48], %(fxlife)d
    fx_o:
        movsx eax, byte ptr [ebx+0x21]
        push eax
        jmp %(fxres)#x
    """
    C2 = dict(C, nodecmp=nodecmp, noderet=noderet, cidcmp=cidcmp, vmtcmp=vmtcmp, acidcmp=acidcmp, avmtcmp=avmtcmp)
    assert prev["V1"] == prev["V2"], "the two predicate sites have different previous owners"
    while len(out) % 16: out.append(0)
    va0 = ZONE + len(out)
    labels = ["exc", "mapc", "pred", "r3c", "selc", "prio", "clk", "getd", "f_find", "f_mask", "pres", "pcls", "vcb",
              "xform", "xf_hnd", "xf_hnd2", "fxc", "xf_hnd3", "rfind", "xa_ip"]
    full = (src % C2) + "\n    __tab:\n" + "\n".join("        .long %s" % lab for lab in labels) + "\n"
    code = asm_pic(full, va0)
    tab = code[-4 * len(labels):]
    for k, lab in enumerate(labels): where[lab] = struct.unpack_from("<I", tab, 4 * k)[0]
    code = code[:-4 * len(labels)]
    out.extend(code)
    return bytes(out), where


def relocs(d):
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


def vaoff(va):
    return va - CODE_V2F


def data_off(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva = va - BASE
    for k in range(nsec):
        vs, sva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if sva <= rva < sva + max(vs, rs): return ro + rva - sva
    raise ValueError(hex(va))


ENTRY = {"EX": "exc", "MAP": "mapc", "V1": "pred", "V2": "pred", "R3": "r3c", "SEL": "selc"}


def want_site(name, va, kind, where):
    op = b"\xe9" if kind == "jmp" else b"\xe8"
    return op + struct.pack("<i", where[ENTRY[name]] - (va + 5))


def state_of(d):
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)])
    live = {n: bytes(d[vaoff(va):vaoff(va) + 5]) for n, va, _ in SITES}
    live_prio = struct.unpack_from("<I", d, data_off(d, PRIO_SLOT))[0]
    live_clk = struct.unpack_from("<I", d, data_off(d, CLK_SLOT))[0]
    v3 = zl[:8] in (b"ESSHIFT3", b"ESSHIFT4", b"ESSHIFT5", b"ESSHIFT6", b"ESSHIFT7", b"ESSHIFT8")
    live_fx = bytes(d[vaoff(FX_SITE):vaoff(FX_SITE) + 5])
    fx_orig = zl[FX_HDR:FX_HDR + 5] if zl[:8] in (b"ESSHIFT6", b"ESSHIFT7", b"ESSHIFT8") else (live_fx if live_fx[0] != 0xE9 else FX_VANILLA)
    if zl[:8] in MAGICS:
        orig = {n: zl[0x10 + 8 * k:0x10 + 8 * k + 5] for k, (n, _, _) in enumerate(SITES)}
        prio_orig = struct.unpack_from("<I", zl, 0x10 + 8 * len(SITES))[0]; stored = True
        clk_orig = struct.unpack_from("<I", zl, CLK_HDR)[0] if v3 else live_clk
    elif any(zl):
        return "FOREIGN", None, None, None, None, None
    else:
        orig, prio_orig, clk_orig, stored = live, live_prio, live_clk, False
    code, where = build(orig, prio_orig, clk_orig, fx_orig)
    st = {}
    for n, va, kind in SITES:
        tgt = rel_target(va, live[n]) if live[n][0] in (0xE8, 0xE9) else 0
        st[n] = ("free" if not stored else "ours" if live[n] == want_site(n, va, kind, where)
                 else "ours(old)" if ZONE <= tgt < ZONE_END else "OTHER")
    st["PRIO"] = ("free" if not stored else "ours" if live_prio == where["prio"]
                  else "ours(old)" if ZONE <= live_prio < ZONE_END else "OTHER")
    st["CLK"] = ("free" if not (stored and v3) else "ours" if live_clk == where["clk"]
                 else "ours(old)" if ZONE <= live_clk < ZONE_END else "OTHER")
    want_fx = bytes([0xE9]) + struct.pack("<i", where["fxc"] - (FX_SITE + 5))
    fxt = rel_target(FX_SITE, live_fx) if live_fx[0] == 0xE9 else 0
    st["FX"] = ("ours" if live_fx == want_fx else "free" if live_fx == FX_VANILLA
                else "ours(old)" if ZONE <= fxt < ZONE_END else "OTHER")
    zs = "zero" if not stored else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "ours(old)"
    return zs, stored, orig, (prio_orig, clk_orig, v3, fx_orig, want_fx), code, (where, st, live, live_prio)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=None)
    a = ap.parse_args()
    dll = a.dll or game_file("AoWEPACK.dll")
    d = bytearray(open(dll, "rb").read())
    print("target:", dll)
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va - 3 < r < va + 5 for _, va, _ in SITES) or FX_SITE - 3 < r < FX_SITE + 5]
    if bad or PRIO_SLOT not in rl or CLK_SLOT not in rl:
        print("ABORT: relocs in zone/sites %s or prio/clk slot not relocated" % bad); return 1
    res = state_of(d)
    zs = res[0]
    if zs == "FOREIGN": print("ABORT: zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    _, stored, orig, (prio_orig, clk_orig, zv3, fx_orig, want_fx), code, (where, st, live, live_prio) = res
    for n, va, kind in SITES:
        if live[n][0] != (0xE9 if kind == "jmp" else 0xE8) and st[n] != "ours":
            print("ABORT: site %s %#x is not a %s: %s" % (n, va, kind, live[n].hex())); return 1
    arm = bytes(d[vaoff(0x5587A600):vaoff(0x5587A608)])
    if arm != b"TARMYHv1" and not a.revert: print("ABORT: patch_terrain_armyhooks_v1.py is not applied (required)"); return 1
    print("zone %s (%d B of %d) | sites %s | prev %s" % (zs, len(code), ZONE_END - ZONE, st,
          {n: hex(rel_target(va, orig[n])) for n, va, _ in SITES}))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); inv = {v: k for k, v in where.items()}
        s0 = min(where.values())
        for i in md.disasm(code[s0 - ZONE:], s0):
            if i.address in inv: print("  -- %s" % inv[i.address])
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if not stored: print("already vanilla"); return 0
        # v2: a v1 zone (ours(old) sites) reverts the same way - the header layout is unchanged
        if "OTHER" in st.values(): print("ABORT: a site was taken over by someone else (LIFO): %s" % st); return 1
        for n, va, _ in SITES: d[vaoff(va):vaoff(va) + 5] = orig[n]
        struct.pack_into("<I", d, data_off(d, PRIO_SLOT), prio_orig)
        if zv3: struct.pack_into("<I", d, data_off(d, CLK_SLOT), clk_orig)
        if st["FX"] != "free": d[vaoff(FX_SITE):vaoff(FX_SITE) + 5] = fx_orig
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        with open(dll, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if zs == "ours" and all(v == "ours" for v in st.values()): print("already applied"); return 0
    if "OTHER" in st.values(): print("ABORT: a site was taken over by someone else: %s" % st); return 1
    new = bytearray(d)
    new[vaoff(ZONE):vaoff(ZONE_END)] = code + bytes(ZONE_END - ZONE - len(code))
    for n, va, kind in SITES: new[vaoff(va):vaoff(va) + 5] = want_site(n, va, kind, where)
    struct.pack_into("<I", new, data_off(new, PRIO_SLOT), where["prio"])
    struct.pack_into("<I", new, data_off(new, CLK_SLOT), where["clk"])
    new[vaoff(FX_SITE):vaoff(FX_SITE) + 5] = want_fx
    print("%d bytes change" % sum(1 for x, y in zip(d, new) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll is None:
        bak = bak_path(dll, BAK_SUFFIX8 if stored else BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(dll, bak); print("backup ->", bak)
    with open(dll, "r+b") as f: f.write(bytes(new))
    assert open(dll, "rb").read() == bytes(new); print("AoWEPACK: written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
