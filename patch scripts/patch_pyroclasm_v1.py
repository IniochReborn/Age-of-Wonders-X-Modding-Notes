"""
PYROCLASM (spell 227, Fire tier 4; Spells.pfs key 237) - a GLOBAL enchantment (Research 200, Cost 75, Upkeep 10) that
slowly turns the medium and large mountains of the surface into VOLCANOES; volcanoes spill lava and the lava creeps.
AoWEPACK.dll only.  v1 2026-10-17, v2 2026-10-17 (round 2).
v2 2026-10-17 (user round 2) - see the V2 section below; everything above still holds unless V2 says otherwise.


Spec (user): "Global Spell. Slowly transforms medium/large mountains across the map into volcanoes.  Volcanoes have a
50% chance of spawning lava in one random adjacent hex per turn.  Lava has a 50% chance of spreading to one random
adjacent hex per turn."

PLUMBING = Tectonic Shift's Air Mastery clone recipe (patch_tectonic_v1.py), CHAINED IN FRONT of whatever owns each
site at apply time (normally Tectonic's caves, which chain to Overgrowth's).  Every hook's previous bytes are stored in
the table at the head of the zone, so --revert puts back exactly what was there.
  CE  0x557F06E4 (TAirMastery.CreateEnchantment, jmp-hooked): 227 -> replay the create, MARKER [ench+0x14] := 227,
      spell name -> [ench+0x1C]; else jmp prev (or our own `ce_plain` replay on a vanilla site).
  MM  0x557F061C (sphere-mastery message call): 227 -> skipped; else jmp prev.
  AC / DE  VMT +0x68 @0x557EDE24 / +0x60 @0x557EDE1C: marker 227 -> base TGlobalEnchantment.Activate/Deactivate only.
  CHK VMT +0x64 @0x557EDE20: marker 227 -> base check + once-per-player; else jmp prev.
  NT  0x5577D293 (player NEW TURN msg 0x20020002, synced): prev first, then for the player whose turn starts with an
      ACTIVE Pyroclasm of his -> the ENGINE (surface level only; all choices = map.Random 0x5577827C -> MP-safe).
  GLOW 0x55764C5B (TFrozenWaterHS.Show, 10 B; owner chain Drought -> Tectonic -> us): our markers -> a pure frame
      pick of spell 227 gfx slot 3 (GLOW_PERIOD ticks per frame, hex phase), `ret 0x10`; anything else -> previous owner
      with every register as it came.  Visual only.
  The cast animation / sound need no hooks: the vanilla Air Mastery map-wide drift draws spell 227's slots 0-2 (surface
  view only) and patch_tectonic_shake_v1.py v2.1 makes every Air Mastery clone play its own cast sound.

VOLCANOES (engine, per caster turn): CONV cap = area/CONV_DIV + 1 conversions (96x96 -> 3, 64x64 -> 2, 44x34 -> 1),
PICKS = cap*PICK_MULT random surface hexes.  A pick counts when its hex carries a TMountainMO whose resource is NOT a
volcano (list length <= 19) and has 4 (medium) or 9 (large) used slots.  The vanilla catalogue has ONE small and ONE
large volcano (MOUNTAIN\\WL_VOLCS.ILB / WL_VOLCL.ILB: TMountainMOR, wasteland, 65-entry lists, same shapes as the
medium / large mountain) -> a medium becomes the small volcano, a large the large one, placed at the SAME anchor (MO
+0x10/+0x11).  Requirements: every real hex of the old footprint without a structure or a foreign TFrozenWaterHS marker
(Tectonic / Drought / ... hexes stay theirs); every volcano slot inside the 19-hex window and on the map; a volcano
real hex that is NOT one of the old mountain's own blocking hexes (= "new") must pass Tectonic's growth checks (no
structure / foreign marker / ARMY / road / bridge / multi-hex decoration / other mountain object; land terrain 1..5 or
dirt; overlay bare / forest / hill / vegetation; SIMPLE connectivity, one after the other via the virtual-blocked list);
art-only volcano hexes: no structure / foreign marker / army / other mountain (CanPlace refuses a footprint over a hex
whose top HS has show priority >= 10).  Then the old footprint and the volcano footprint are ClearTerrain'd twice (a
multi-hex mountain cleared on one hex re-places 1-hex mountains on its other slots) and the volcano is created with
TAoWHSMap.PlaceTerrain's recipe (RandSeed := Random(0xFFFFFF), resource VMT+0x68 PlaceResourceUser).  TMountainMO.
CanPlace (0x557A2E54) checks map bounds + the top HS of every slot, NOT the terrain: a wasteland volcano can stand on
grass / snow / desert.  If the volcano is not found on the anchor afterwards, the OLD mountain resource is re-placed
there (no mountain is ever lost).  The anchor gets a VOLCANO marker.
LAVA: volcano markers (code 0xF): if the volcano MO is gone -> the marker is destroyed; else 1 in 2 (map.Random(2)):
up to VTRIES tries of (random window slot 0..18 of the anchor, random direction 1..6) for a hex that touches a volcano
hex and is a valid lava target -> LAVA.  Lava markers: a lava hex (still terrain 9) whose marker is not new this turn
-> 1 in 2: one random direction 1..6 -> lava when valid.  Valid lava target = surface hex, terrain 1..5 or dirt 0xC,
overlay bare / forest / vegetation (forest and vegetation are burnt = ClearTerrain), no structure / foreign marker /
ARMY (never under units - DEFAULT, documented), no road / bridge, no multi-hex decoration, no mountain object (not even
art overhang), and SIMPLE (a new lava hex never splits an open area: lava is impassable, so this also keeps every unit /
structure reachable).  Water, ice, lava, cave terrain, hills and mountains are never turned to lava.  The change =
ClearTerrain + ChangeTerrain(9) (map VMT+0xD0, Tectonic's recipe).  LAVA budget per turn = area/LAVA_DIV + LAVA_ADD
(96x96 -> 32): growth is ~exponential otherwise (every lava hex may spread), the budget caps it; the walk stops when
the budget is spent.  Lava created this turn carries [+0xC] = 1 and does not spread before the caster's next turn (a
READY pass clears it at the start of each turn), so one turn = one step.  Only lava and volcanoes made by THIS caster's
Pyroclasm act (markers owner 0x40|caster); map volcanoes / lava lakes stay inert.

MARKERS (TFrozenWaterHS, the Drought / Overgrowth / Ice Age / Tectonic carrier; saved with the game by
build_raiseterrain_matrix.py's tags -> survive save/load, identical in MP): +0xC  lava: 1 = created this turn / 0 ready;
volcano: the original mountain's terrain (| 0x80 for a large) - kept for a future revert;  +0xD 0x40|caster (the vanilla /
Drought / raise-terrain per-player ticks never match);  +0xE 0x10 | code: code 0xF volcano, else the hex's ORIGINAL
terrain before it became lava (1..5, 0xC) - enough for a future revert (forest / vegetation are not remembered);
+0xF the hex's current terrain (TFrozenWaterHS VMT+0xA0 frees the marker when the terrain changes).  Flag namespace:
0x10..0x1F (bits 0xE0 clear, > 0xD): not vanilla ice (0), not raise-terrain (<= 0xD), not Drought (0x80), Overgrowth
(0x40), Ice Age (0xC0) or Tectonic (0x20) -> every other engine treats them as FOREIGN and keeps off our hexes, and we
keep off theirs.  No revert is implemented (the changes are permanent); the markers make one possible later.

AI: the pipeline poke (0x34, 4, 0xFFFFFFFF) = priority -1 -> the AI never casts it.

Zone 0x5587B800..0x5587D800 (table + data + engine + glow + hook caves; verified zero and reloc-free 10/17, inside CODE).
Dry-run default; --apply / --revert (restores the six sites + the glow site, zeroes the zone) / --dis / --dll <path>
(scratch copy, no backup).  Backup <game>\\backup\\AoWEPACK.dll.bak_pyroclasm.
!! Order: apply AFTER patch_tectonic_v1.py (and everything it chains to); revert BEFORE re-running / reverting
Tectonic, Overgrowth or patch_drought_glow_v1.py (their scripts see our hooks as OTHER and abort) - LIFO.  Our
--apply / --revert refuse while a site no longer points at us.
V2 (2026-10-17, user round 2).  Spec: "lava should be able to spawn under units (potentially killing them, which is what
would happen if a unit with Fire Halo stood on lava then lost Fire Halo).  When the spell is removed, lava should slowly
change to wasteland rather than original terrain; volcanoes should slowly change to wasteland mountains of the same size
(inert volcano) rather than original.  Any snow terrain adjacent to lava should melt (-> steppe).  The spell should make
any existing lava underground and in the depths have a 50% chance of expanding, but not onto earth/rock (only dirt);
this underground lava slowly reverts to original terrain when the spell is removed.  When the spell is first cast, all
existing volcanoes spawn one to three hexes of lava on an adjacent hex; whenever a mountain changes to a volcano it
spawns one or two.  Each turn every magic lava hex rolls 50% to spawn adjacent lava, but any hex that has already
spawned lava drops to 10% (lines / rivers of lava instead of pools)."

LAVA UNDER UNITS (RE): THSMap.ChangeTerrain (HSEPack 0x5560C688; eax map, edx SOURCE object, ecx x; stack terrain,
radius, level, y) asks every child of the field TMapField.CanChangeTerrainEx -> VMT+0x98 with {source, field, subhex}.
TArmyHS.CanChangeTerrain (0x55790DAC) VETOES a terrain its units cannot stand on (TArmy.ValidTerrain 0x5578DD64) -
UNLESS the source's ClassID is 0x2016C (TFrozenWaterHS) or 0x2123E (or subhex != 0).  The accepted change then calls
TMapField.TerrainChanged -> TArmyHS.TerrainChanged (0x55790E08) -> TArmy.ValidateTerrain (0x5578CF70) ->
ValidateTerrainEx (0x5578CC9C): every unit that cannot stand on the new terrain dies through the vanilla TE (lava: the
"units burn" event, the same path a Fire Halo unit takes when the halo goes and the lava stays; frozen water melting
under an army = "units drown").  v1 passed source nil -> armies vetoed lava -> v1 also excluded armies.  v2: every
ChangeTerrain of ours (t_chg) passes an UNPLACED TFrozenWaterHS (created lazily per engine run with TEObject.Create,
destroyed at the end) as the source, and lava targets no longer exclude armies (t_guard2 = structure / foreign marker
only).  Units able to stand on lava (fire immune / Fire Halo) survive; everything else on the hex dies.  Runs inside the
synced new-turn broadcast on every machine -> MP-identical (the TE executes locally, like Freeze Water's expiry).
SNOW MELT: whenever OUR lava is created, and every turn for each of OUR lava hexes (surface), the 6 neighbours that are
SNOW (3) with overlay bare / vegetation, no structure / foreign marker / road / bridge / mountain object / multi-hex
decoration -> vegetation cleared, terrain -> STEPPE (4).  Permanent (no marker; the revert does not re-freeze it).
Snow forest (overlay 1), hills, roads and other spells' hexes are not melted (documented choice).
FIRST CAST / FRESH VOLCANO BURSTS: each caster turn a surface walk (p_mvolc) finds every volcano MO whose ANCHOR is the
hex and that carries NO TFrozenWaterHS marker at all (= a map volcano nobody's Pyroclasm touched yet) -> 1..CAST_MAX
lava hexes adjacent to it (t_burst: up to VTRIES tries per lava, like an eruption) and a marker code 0xE (+0xC 0) on
its anchor = "erupted once" (one-shot per volcano per caster; glows like ours; the map volcano itself stays inert
afterwards and is never converted / reverted).  A conversion that succeeds -> 1..CONV_MAX lava around the new volcano.
Bursts do not consume the per-turn lava budget (they are bounded by conversions / map volcanoes).
SPREAD: every lava marker carries +0xC bit 1 "has spawned"; a ready lava hex rolls Random(2) == 0 (never spawned) or
Random(SPAWNED_DIV) == 0 (spawned before) -> one random direction -> lava if valid -> bit 1 set.  Volcano eruptions stay
1 in 2 per turn.
UNDERGROUND / DEPTHS (levels 1..MAXLEV-1, every caster turn while active): READY pass, then every LAVA hex of the level:
  OUR marker (this caster) -> the same 50% / 10% spread;  no marker (map lava) -> Random(2) == 0 -> one random direction
  -> lava if valid -> the SOURCE gets a marker code 9 (+0xC 2 = spawned: from then on 10%);  another caster's / a
  foreign marker -> skipped.  Valid UG target: terrain DIRT (0xC) only (earth 7 / rock 8 / cave water 0xA / cave ice
  0xD never), overlay bare / forest / vegetation (cleared), no structure / foreign marker / road / bridge / multi-hex
  decoration, SIMPLE connectivity (lava is impassable - no passage is ever cut); armies allowed (they burn).  Budget per
  UG level = area/UG_DIV + UG_ADD.  The new lava's marker code = its ORIGINAL terrain (0xC).
REVERT (NT of a player while NO player has an active Pyroclasm; walks every level, this player's markers only):
  code 9 (map-lava source) / 0xE (erupted map volcano) -> marker destroyed (nothing else changes).
  otherwise: +0xC bit 0x40 clear -> countdown := 0x40 | (REV_BASE + Random(REV_RND)); else decremented each turn; at 1:
    lava marker: SURFACE -> WASTELAND (5), UNDERGROUND -> its original terrain (code, dirt) - marker destroyed FIRST,
      then ChangeTerrain (same source trick; wasteland / dirt are valid for every land unit).  A hex that is no longer
      lava -> the stale marker is just destroyed.
    volcano marker: TMountainMO swap (t_conv mode 1) volcano -> the WASTELAND MOUNTAIN of the same size (d_ms / d_ml:
      MOUNTAIN.ILB, terrain 5, list <= 19 - footprints identical to WL_VOLCS / WL_VOLCL, verified in the catalogue) at
      the same anchor; the marker is destroyed before the swap (the anchor re-inits).  If the swap fails (no resource /
      CanPlace) the volcano is re-placed and gets a FRESH marker with a new countdown (retried later).  A volcano marker
      whose volcano is gone -> destroyed.
  If any Pyroclasm becomes active again, the READY pass clears the countdown bits (lava keeps its spawned bit).
MARKER +0xC (v2):  lava: bit0 new this turn, bit1 has spawned, 0x40|n revert countdown;  volcano (0xF): v1 value (old
  mountain terrain | 0x80 large) with bit 0x40 cleared every shift turn, 0x40|n revert countdown;  0xE / 9: 0 / 2.
  +0xE codes: 1..5 / 0xC lava (original terrain), 9 map-lava source (UG), 0xE erupted map volcano, 0xF our volcano.
  v1 saves load cleanly: their +0xC values never carry 0x40.
UPGRADE: --apply on the live v1 rebuilds the zone in place (table magic PYROCLv1 accepted, the stored original site
bytes kept, hooks re-pointed), backup <game>\\backup\\AoWEPACK.dll.bak_pyroclasm2 = the v1 state.  --revert from v1 or
v2 restores the pre-Pyroclasm bytes.  Same zone, same sites, same LIFO chain (in front of Tectonic).

V3 (2026-10-17, user: "it definitely seems like lava can't spawn below units" + "mountains spawned by Tectonic Rift
should be able to turn into volcanoes").  REQUIRES patch_terrain_armyhooks_v1.py (--apply refuses without it).
  * ROOT CAUSE of "no lava under units": THSMap.ChangeTerrain writes the NEW terrain into [field+0x14] before asking the
    children; TArmyHS.CanChangeTerrain honours a TFrozenWaterHS source only when [field+0x14] == 0 (water) -> for lava it
    always asked TArmy.ValidTerrain and vetoed.  v2's source trick never worked (its emulator modelled the veto wrongly).
    v3: t_chg publishes its source in ALLOW_SRC (0x5590B500) around the ChangeTerrain call; the armyhooks cave accepts a
    change whose source == ALLOW_SRC; the vanilla TerrainChanged -> TArmy.ValidateTerrain then burns the units that
    cannot stand on lava (the Fire-Halo-lost path).  ALLOW_SRC is cleared right after every call.
  * TAKEOVER of Tectonic mountains: the conversion's footprint checks (t_oldok / t_vfpok) accept TECTONIC markers
    ([+0xE] & 0xE0 == 0x20) as well as ours; after a successful conversion (volcano found on the anchor) t_untect
    destroys the Tectonic markers on every REAL hex of the old mountain and of the volcano BEFORE our volcano marker is
    placed -> Tectonic's shift / revert never touch the volcano again.  On Pyroclasm's revert the volcano becomes the
    wasteland mountain of the same size (spec) - PERMANENT, also once Tectonic has ended (its markers are gone): FINAL
    STATE when both spells end = a wasteland mountain where Tectonic had raised the mountain; Tectonic's other changes
    around it revert as usual.  Lava still keeps off Tectonic's hexes (they stay foreign for the lava rules).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_pyroclasm"
BAK_SUFFIX_V2 = ".bak_pyroclasm2"                # backup taken by the v1 -> v2 upgrade (= the v1 state)
BAK_SUFFIX_V3 = ".bak_pyroclasm3"                # backup taken by the v2 -> v3 upgrade (= the v2 state)
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5587B800, 0x5587D800
MAGIC = b"PYROCLv3"
MAGIC_V1 = b"PYROCLv1"                            # an in-place upgrade reads the v1 table
MAGIC_V2 = b"PYROCLv2"                            # ... or the v2 table (same layout)
ALLOW_SRC = 0x5590B500                            # v3: patch_terrain_armyhooks_v1.py - TArmyHS.CanChangeTerrain accepts our source
SPELL_ID = 227
# ---- tuning ----
CONV_DIV, PICK_MULT = 4000, 48                     # conversions per turn = area/4000 + 1 (96x96 -> 3); picks = 48x that
LAVA_DIV, LAVA_ADD = 300, 2                        # new lava hexes per turn <= area/300 + 2 (96x96 -> 32)
VTRIES = 8                                         # an eruption tries up to 8 random hexes around the volcano
VOLC_MINLEN = 20                                   # a TMountainMOR list longer than 19 = a volcano (the vanilla ones: 65)
VOLC_TERRAIN, LAVA = 5, 9                          # the vanilla volcanoes are wasteland resources; lava terrain id
GLOW_SLOT, GLOW_PERIOD = 3, 2                      # glow = spell 227 gfx slot 3, 2 ticks per frame (48-frame loop)
# ---- v2 tuning ----
UG_DIV, UG_ADD = 400, 1                           # new UNDERGROUND lava per level per turn <= area/400 + 1 (96x96 -> 24)
SPAWNED_DIV = 10                                  # a lava hex that already spawned lava: 1 in 10 (else 1 in 2) -> rivers
CAST_MAX, CONV_MAX = 3, 2                         # first cast: every map volcano 1..3 lava; a fresh volcano 1..2
REV_BASE, REV_RND = 2, 4                          # revert: a marker acts 2..5 of its caster's turns after the countdown starts
MAXLEV = 3                                        # surface + underground + depths
WASTELAND, STEPPE = 5, 4                          # lava -> wasteland (surface revert); snow -> steppe (melt)

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
RES_GLOBAL, RANDSEED_SLOT = 0x558FA044, 0x558FB720
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
AM_CHK_MSG, AM_CHK_SEH = 0x557F0306, 0x557F0374
AM_ENCH_CREATE, AM_ENCH_CELL = 0x557F0204, 0x557EDD7C
LSTRASG = 0x55701150
MAP_RANDOM = 0x5577827C
GETMAPLEVEL, LEVEL_GETFIELD = 0x557020EC, 0x557020DC
FIND_NT_HS, STRUCT_CLASSREF = 0x55702004, 0x55713BD8
FIND_HS, FW_CLASSREF = 0x55701FFC, 0x55714774
EO_CREATE, PLACEHX = 0x55703064, 0x557025F4
CLEAR_TERRAIN, CHANGE_SLOT = 0x557025DC, 0xD0
MTN_MO_VMT = 0x557A266C
TMO_CID = 0x20166
CLASSID_ARMY = 0x20217
CLASSID_ROAD, CLASSID_BRIDGE, CLASSID_HBRIDGE = 0x20164, 0x20174, 0x2087A
CLS_MTNRES = 0x20169
GLOW_SITE, GLOW_VANILLA = 0x55764C5B, bytes.fromhex("ba46000000e8b7dcf9ff")
SHOWLOOPEDEX = 0x5570291C
GETSPELL, GETIMAGESEQ, IMAGEEXIST, LIBGET, AOWHSSET = 0x55779AC8, 0x557028E4, 0x55702944, 0x55702934, 0x558FA044
HN_TAB = bytes.fromhex("000000ff01ff01000001ff00ffff00fe01fe02ff0200020101010002ff01fe01fe00fefffffe000000ff010001010001ff01ff0000fe01ff02ff0200020101020002ff02fe01fe00feffffff")
ADJ19 = bytes.fromhex("01020304050607080200061208090a030001020a0b0c040000030c0d0e050600040e0f10120100051011ffff080112ffffff09020107ffffff0a020809ffff0b03020affffff0c03030bffff0d04040cffffff0e05040dffff0f10050effffff1106050fffffff120610ffffff07010611ff")
# volcano picker descriptors: classid, used-slot count, (slot, overlay) A, (slot, overlay) B, max list length, MIN list length
DESCS = (("d_vs", CLS_MTNRES, 4, 0, 2, 1, 0, 65, VOLC_MINLEN), ("d_vl", CLS_MTNRES, 9, 0, 0, 4, 2, 65, VOLC_MINLEN),
         # v2 revert targets: the wasteland medium / large MOUNTAIN (same shapes = same footprint as the two volcanoes)
         ("d_ms", CLS_MTNRES, 4, 0, 2, 1, 0, 19, 0), ("d_ml", CLS_MTNRES, 9, 0, 0, 4, 2, 19, 0))

CE_VANILLA = bytes.fromhex("33c9b201a1")
SITES = {
    "CE":  (0x557F06E4, "jmp", "ce"),
    "MM":  (0x557F061C, "call", "mm"),
    "NT":  (0x5577D293, "call", "nt"),
    "AC":  (0x557EDE24, "vmt", "ac"),
    "DE":  (0x557EDE1C, "vmt", "de"),
    "CHK": (0x557EDE20, "vmt", "chk"),
}
ORDER = ["CE", "MM", "NT", "AC", "DE", "CHK"]
TABLE_LEN = 0x30                                   # MAGIC + 3x5 + 3x4 + the glow site's 10 original bytes = 45 B

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    """Assemble; every `call $D` / `pop R` / `sub R, $D` triple gets the anchor (the VA after the call) patched in."""
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


def pack_table(orig, glow):
    t = bytearray(MAGIC)
    for nm in ORDER: t += orig[nm]
    t += glow
    return bytes(t) + bytes(TABLE_LEN - len(t))


def unpack_table(b):
    if b[:8] not in (MAGIC, MAGIC_V1, MAGIC_V2): return None, None
    out, p = {}, 8
    for nm in ORDER:
        n = 4 if SITES[nm][1] == "vmt" else 5
        out[nm] = bytes(b[p:p + n]); p += n
    return out, bytes(b[p:p + 10])


def prev_target(nm, orig):
    """Where our cave falls through to for everything that is not Pyroclasm (None = our ce_plain replay)."""
    va, kind, _c = SITES[nm]
    if kind == "vmt": return struct.unpack("<I", orig)[0]
    if nm == "CE" and orig == CE_VANILLA: return None
    if orig[0] != (0xE9 if kind == "jmp" else 0xE8): raise ValueError("%s @%#x: unexpected bytes %s" % (nm, va, orig.hex()))
    return va + 5 + struct.unpack_from("<i", orig, 1)[0]


def build(orig, glow_orig):
    """-> (zone bytes, where)."""
    out = bytearray(pack_table(orig, glow_orig)); where = {}
    prev = {nm: prev_target(nm, orig[nm]) for nm in ORDER}
    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        s = src % dict(C, **where)
        out.extend(asm_pic(s, va) if pic else bytes(ks.asm(s, va)[0]))
    def place_data(name, data):
        while len(out) % 16: out.append(0)
        where[name] = ZONE + len(out); out.extend(data)
    C = {"id": SPELL_ID, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT, "bdeact": BASE_DEACT, "bchk": BASE_CHK,
         "ammsg": AM_CHK_MSG, "amseh": AM_CHK_SEH, "amcreate": AM_ENCH_CREATE, "amcell": AM_ENCH_CELL, "lstrasg": LSTRASG,
         "rnd": MAP_RANDOM, "getlevel": GETMAPLEVEL, "getfield": LEVEL_GETFIELD, "findnt": FIND_NT_HS,
         "structref": STRUCT_CLASSREF, "findhs": FIND_HS, "fwcls": FW_CLASSREF, "clear": CLEAR_TERRAIN,
         "cslot": CHANGE_SLOT, "armyid": CLASSID_ARMY, "resg": RES_GLOBAL, "randseed": RANDSEED_SLOT,
         "mtnvmt": MTN_MO_VMT, "roadid": CLASSID_ROAD, "bridgeid": CLASSID_BRIDGE, "hbridgeid": CLASSID_HBRIDGE,
         "eocreate": EO_CREATE, "placehx": PLACEHX, "tmocid": TMO_CID, "slx": SHOWLOOPEDEX, "getspell": GETSPELL,
         "getseq": GETIMAGESEQ, "exist": IMAGEEXIST, "libget": LIBGET, "hsset": AOWHSSET, "gslot": GLOW_SLOT,
         "gperiod": GLOW_PERIOD, "convdiv": CONV_DIV, "picks": PICK_MULT, "lavadiv": LAVA_DIV, "lavaadd": LAVA_ADD,
         "vtries": VTRIES, "minlen": VOLC_MINLEN, "vterr": VOLC_TERRAIN, "lava": LAVA,
         "ugdiv": UG_DIV, "ugadd": UG_ADD, "spawned": SPAWNED_DIV, "castmax": CAST_MAX, "convmax": CONV_MAX,
         "revbase": REV_BASE, "revrnd": REV_RND, "maxlev": MAXLEV, "wasteland": WASTELAND, "steppe": STEPPE,
         "allow": ALLOW_SRC}
    place_data("hntab", HN_TAB)
    place_data("adj", ADJ19)
    for nm, cls, used, sa, oa, sb, ob, mx, mn in DESCS:
        place_data(nm, struct.pack("<IBBBBBBBB", cls, used, sa, oa, sb, ob, mx, mn, 0))
    # ENGINE: ebx = delta, edi = player.  Frame (ebp, 0x140): -4 map, -0xC level index (0), -0x10 conversion cap, -0x14
    # picks left, -0x18 conversions done, -0x1C/-0x20 x/y (walk / pick), -0x24 wanted terrain (volcano 5), -0x28 volcano
    # resource, -0x2C current mountain MO (t_mtnof exclusion / t_hasown target), -0x30/-0x34 anchor x/y, -0x38 virtual-
    # blocked count, -0x74/-0x78 candidate hex, -0x7C/-0x80 picker count/index, -0x84 scratch field, -0x8C slot word,
    # -0x90 list, -0x94 passes, -0xA4 owner byte (0x40 | player), -0xC0 old size, -0xC4 temp / descriptor / old terrain,
    # -0xC8 walk mode, -0xCC area, -0xD0 lava budget, -0xD4 tries, -0xD8 current marker, -0xDC current field, -0xE0 old
    # resource, -0x100..-0xE4 virtual-blocked list.  esi = the surface TMapLevel throughout.
    place("engine", """
    engine:
        push ebp
        mov ebp, esp
        sub esp, 0x140
        push esi
        push edi
        mov [ebp-0x120], eax
        mov eax, edi
        and eax, 0x3f
        or eax, 0x40
        mov [ebp-0xA4], eax
        xor eax, eax
        mov [ebp-0x108], eax
        mov [ebp-0x10C], eax
        mov [ebp-0x11C], eax
        mov [ebp-0xC], eax
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        test eax, eax
        jz e_out
        mov eax, [eax+0x10]
        test eax, eax
        jz e_out
        mov eax, [eax+8]
        test eax, eax
        jz e_out
        mov ecx, [eax+8]
        cmp ecx, %(maxlev)d
        jle e_cnt
        mov ecx, %(maxlev)d
    e_cnt:
        mov [ebp-8], ecx
    lv_lp:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-8]
        jge e_done
        mov edx, eax
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        call %(getlevel)#x
        test eax, eax
        jz lv_nx
        mov esi, eax
        cmp dword ptr [esi+0xc], 3
        jl lv_nx
        cmp dword ptr [esi+0x10], 3
        jl lv_nx
        xor eax, eax
        mov [ebp-0x38], eax
        mov [ebp-0x2C], eax
        mov [ebp-0x18], eax
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        mov [ebp-0xCC], eax
        cmp dword ptr [ebp-0x120], 0
        jne lv_rev
        cmp dword ptr [ebp-0xC], 0
        jne lv_ug
        mov eax, [ebp-0xCC]
        xor edx, edx
        mov ecx, %(lavadiv)d
        div ecx
        add eax, %(lavaadd)d
        mov [ebp-0xD0], eax
        xor eax, eax
        call p_walk
        mov eax, 2
        call p_walk
        mov eax, 1
        call p_walk
        mov eax, [ebp-0xCC]
        xor edx, edx
        mov ecx, %(convdiv)d
        div ecx
        inc eax
        mov [ebp-0x10], eax
        imul eax, eax, %(picks)d
        mov [ebp-0x14], eax
    c_lp:
        mov eax, [ebp-4]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebp-0x1C], eax
        mov eax, [ebp-4]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebp-0x20], eax
        mov edx, [ebp-0x1C]
        mov ecx, eax
        call t_getf
        test eax, eax
        jz c_nx
        call t_conv
    c_nx:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0x10]
        jae lv_nx
        dec dword ptr [ebp-0x14]
        jnz c_lp
        jmp lv_nx
    lv_ug:
        mov eax, [ebp-0xCC]
        xor edx, edx
        mov ecx, %(ugdiv)d
        div ecx
        add eax, %(ugadd)d
        mov [ebp-0xD0], eax
        xor eax, eax
        call p_walk
        mov eax, 3
        call p_walk
        jmp lv_nx
    lv_rev:
        mov eax, 4
        call p_walk
    lv_nx:
        inc dword ptr [ebp-0xC]
        jmp lv_lp
    e_done:
        mov eax, [ebp-0x10C]
        test eax, eax
        jz e_out
        call t_kill
    e_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    p_walk:
        mov [ebp-0xC8], eax
        xor eax, eax
        mov [ebp-0x20], eax
    pw_y:
        mov eax, [ebp-0x20]
        cmp eax, [esi+0x10]
        jge pw_out
        xor eax, eax
        mov [ebp-0x1C], eax
    pw_x:
        mov eax, [ebp-0x1C]
        cmp eax, [esi+0xc]
        jge pw_ny
        mov edx, eax
        mov ecx, [ebp-0x20]
        call t_getf
        test eax, eax
        jz pw_nx
        mov [ebp-0xDC], eax
        mov ecx, [ebp-0xC8]
        cmp ecx, 1
        je pw_bud
        cmp ecx, 3
        jne pw_nb
    pw_bud:
        cmp dword ptr [ebp-0xD0], 0
        jle pw_out
    pw_nb:
        cmp ecx, 2
        jne pw_n2
        call p_mvolc
        jmp pw_nx
    pw_n2:
        cmp ecx, 3
        jne pw_n3
        call p_ug
        jmp pw_nx
    pw_n3:
        call t_mine
        test eax, eax
        jz pw_nx
        mov [ebp-0xD8], eax
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf
        mov ecx, [ebp-0xC8]
        test ecx, ecx
        jnz pw_m1
        cmp dl, 0xf
        jne pw_r1
        and byte ptr [eax+0xc], 0xbf
        jmp pw_nx
    pw_r1:
        and byte ptr [eax+0xc], 2
        jmp pw_nx
    pw_m1:
        cmp ecx, 4
        jne pw_act
        call p_rev
        jmp pw_nx
    pw_act:
        cmp dl, 0xf
        jne pw_la
        call p_volc
        jmp pw_nx
    pw_la:
        cmp dl, 0xe
        je pw_nx
        call p_lava
    pw_nx:
        inc dword ptr [ebp-0x1C]
        jmp pw_x
    pw_ny:
        inc dword ptr [ebp-0x20]
        jmp pw_y
    pw_out:
        ret

    t_mine:
        call t_ours
        test eax, eax
        jz mi_x
        mov dl, byte ptr [eax+0xd]
        cmp dl, byte ptr [ebp-0xA4]
        je mi_x
        xor eax, eax
    mi_x:
        ret

    p_volc:
        mov eax, [ebp-0xDC]
        call t_volcof
        test eax, eax
        jz pv_kill
        mov [ebp-0x2C], eax
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        test eax, eax
        jnz pv_out
        mov dword ptr [ebp-0xD4], %(vtries)d
    pv_try:
        mov eax, [ebp-4]
        mov edx, 19
        call %(rnd)#x
        mov ecx, [ebp-0x2C]
        movzx edx, byte ptr [ecx+0x10]
        movzx ecx, byte ptr [ecx+0x11]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        inc eax
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_adjv
        test eax, eax
        jz pv_nt
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_getf
        test eax, eax
        jz pv_nt
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_lavaok
        test eax, eax
        jz pv_nt
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_mklava
        jmp pv_out
    pv_nt:
        dec dword ptr [ebp-0xD4]
        jnz pv_try
    pv_out:
        xor eax, eax
        mov [ebp-0x2C], eax
        ret
    pv_kill:
        mov eax, [ebp-0xD8]
        call t_kill
        ret

    t_adjv:
        push edi
        push edx
        push ecx
        mov edi, 1
    av_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call t_hn
        call t_getf
        test eax, eax
        jz av_n
        call t_hasown
        test eax, eax
        jnz av_yes
    av_n:
        inc edi
        cmp edi, 7
        jb av_l
        xor eax, eax
        jmp av_out
    av_yes:
        mov eax, 1
    av_out:
        pop ecx
        pop edx
        pop edi
        ret

    p_lava:
        mov eax, [ebp-0xD8]
        test byte ptr [eax+0xc], 1
        jnz pl_out
        mov eax, [ebp-0xDC]
        cmp byte ptr [eax+0x14], %(lava)d
        jne pl_out
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_melt
        mov eax, [ebp-0xD8]
        test byte ptr [eax+0xc], 2
        jz pl_50
        mov eax, [ebp-4]
        mov edx, %(spawned)d
        call %(rnd)#x
        test eax, eax
        jnz pl_out
        jmp pl_go
    pl_50:
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        test eax, eax
        jnz pl_out
    pl_go:
        call t_spread
        test eax, eax
        jz pl_out
        mov eax, [ebp-0xD8]
        or byte ptr [eax+0xc], 2
    pl_out:
        ret

    t_spread:
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        inc eax
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_getf
        test eax, eax
        jz sp_no
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_lavaok
        test eax, eax
        jz sp_no
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_mklava
        ret
    sp_no:
        xor eax, eax
        ret

    p_ug:
        mov eax, [ebp-0xDC]
        cmp byte ptr [eax+0x14], %(lava)d
        jne pu_out
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz pu_map
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf0
        cmp dl, 0x10
        jne pu_out
        mov dl, byte ptr [eax+0xd]
        cmp dl, byte ptr [ebp-0xA4]
        jne pu_out
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf
        cmp dl, 0xe
        jae pu_out
        mov [ebp-0xD8], eax
        call p_lava
        ret
    pu_map:
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        test eax, eax
        jnz pu_out
        call t_spread
        test eax, eax
        jz pu_out
        mov eax, [ebp-0xDC]
        mov edx, 9
        mov ecx, 2
        call t_mark
    pu_out:
        ret

    p_mvolc:
        mov eax, [ebp-0xDC]
        call t_volcof
        test eax, eax
        jz pm_out
        movzx edx, byte ptr [eax+0x10]
        cmp edx, [ebp-0x1C]
        jne pm_out
        movzx edx, byte ptr [eax+0x11]
        cmp edx, [ebp-0x20]
        jne pm_out
        push eax
        mov eax, [ebp-0xDC]
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        pop eax
        jnz pm_out
        mov [ebp-0x2C], eax
        mov eax, [ebp-4]
        mov edx, %(castmax)d
        call %(rnd)#x
        inc eax
        call t_burst
        mov eax, [ebp-0xDC]
        mov edx, 0xe
        xor ecx, ecx
        call t_mark
        xor eax, eax
        mov [ebp-0x2C], eax
    pm_out:
        ret

    t_burst:
        mov [ebp-0x110], eax
        imul eax, eax, %(vtries)d
        mov [ebp-0x114], eax
    tb_l:
        cmp dword ptr [ebp-0x110], 0
        jle tb_out
        cmp dword ptr [ebp-0x114], 0
        jle tb_out
        dec dword ptr [ebp-0x114]
        mov eax, [ebp-4]
        mov edx, 19
        call %(rnd)#x
        mov ecx, [ebp-0x2C]
        movzx edx, byte ptr [ecx+0x10]
        movzx ecx, byte ptr [ecx+0x11]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        inc eax
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_adjv
        test eax, eax
        jz tb_l
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_getf
        test eax, eax
        jz tb_l
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_lavaok
        test eax, eax
        jz tb_l
        inc dword ptr [ebp-0xD0]
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_mklava
        test eax, eax
        jnz tb_ok
        dec dword ptr [ebp-0xD0]
        jmp tb_l
    tb_ok:
        dec dword ptr [ebp-0x110]
        jmp tb_l
    tb_out:
        ret

    t_melt:
        cmp dword ptr [ebp-0xC], 0
        jne tm_ret
        push edi
        push edx
        push ecx
        mov edi, 1
    tm_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call t_hn
        mov [ebp-0x128], edx
        mov [ebp-0x12C], ecx
        call t_getf
        test eax, eax
        jz tm_n
        mov [ebp-0x118], eax
        cmp byte ptr [eax+0x14], 3
        jne tm_n
        mov cl, byte ptr [eax+0x15]
        cmp cl, 0xff
        je tm_ov
        cmp cl, 3
        jne tm_n
    tm_ov:
        mov eax, [ebp-0x118]
        call t_guard2
        test eax, eax
        jz tm_n
        push dword ptr [ebp-0x2C]
        mov dword ptr [ebp-0x2C], 0
        mov eax, [ebp-0x118]
        call t_mtnof
        pop dword ptr [ebp-0x2C]
        test eax, eax
        jnz tm_n
        mov eax, [ebp-0x118]
        call t_roads
        test eax, eax
        jnz tm_n
        mov eax, [ebp-0x118]
        call t_multi
        test eax, eax
        jnz tm_n
        mov eax, [ebp-0x118]
        cmp byte ptr [eax+0x15], 3
        jne tm_chg
        mov edx, [ebp-0x128]
        mov ecx, [ebp-0x12C]
        call t_clear
    tm_chg:
        mov eax, %(steppe)d
        mov edx, [ebp-0x128]
        mov ecx, [ebp-0x12C]
        call t_chg
    tm_n:
        inc edi
        cmp edi, 7
        jb tm_l
        pop ecx
        pop edx
        pop edi
    tm_ret:
        ret

    t_chg:
        push esi
        push edi
        mov edi, eax
        cmp dword ptr [ebp-0x10C], 0
        jne tc_have
        push edx
        push ecx
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(fwcls)#x]
        call %(eocreate)#x
        mov [ebp-0x10C], eax
        pop ecx
        pop edx
    tc_have:
        push ecx
        push dword ptr [ebp-0xC]
        push 0
        push edi
        mov ecx, edx
        mov edx, [ebp-0x10C]
        mov [ebx+%(allow)#x], edx
        mov eax, [ebp-4]
        mov esi, [eax]
        call dword ptr [esi+%(cslot)#x]
        mov dword ptr [ebx+%(allow)#x], 0
        pop edi
        pop esi
        ret

    p_rev:
        mov eax, [ebp-0xD8]
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf
        cmp dl, 9
        je pr_kill
        cmp dl, 0xe
        je pr_kill
        mov cl, byte ptr [eax+0xc]
        test cl, 0x40
        jnz pr_cnt
        call t_cntdn
        ret
    pr_cnt:
        and cl, 0x3f
        cmp cl, 1
        jbe pr_act
        dec byte ptr [eax+0xc]
        ret
    pr_act:
        cmp dl, 0xf
        jne pr_lava
        jmp t_inert
    pr_lava:
        mov ecx, [ebp-0xDC]
        cmp byte ptr [ecx+0x14], %(lava)d
        jne pr_kill
        cmp dword ptr [ebp-0xC], 0
        jne pr_ug
        mov edx, %(wasteland)d
        jmp pr_set
    pr_ug:
        movzx edx, dl
    pr_set:
        mov [ebp-0x124], edx
        call t_kill
        mov eax, [ebp-0x124]
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_chg
        ret
    pr_kill:
        call t_kill
        ret

    t_cntdn:
        push eax
        mov eax, [ebp-4]
        mov edx, %(revrnd)d
        call %(rnd)#x
        add eax, %(revbase)d
        or eax, 0x40
        mov edx, eax
        pop eax
        mov byte ptr [eax+0xc], dl
        ret

    t_inert:
        mov eax, [ebp-0x1C]
        mov [ebp-0x30], eax
        mov eax, [ebp-0x20]
        mov [ebp-0x34], eax
        mov eax, [ebp-0xDC]
        xor edx, edx
        call t_anch
        test eax, eax
        jnz ti_go
        mov eax, [ebp-0xD8]
        call t_kill
        ret
    ti_go:
        mov eax, [ebp-0xD8]
        mov [ebp-0x11C], eax
        mov dword ptr [ebp-0x108], 1
        mov eax, [ebp-0xDC]
        call t_conv
        xor eax, eax
        mov [ebp-0x108], eax
        mov [ebp-0x11C], eax
        ret

    t_anch:
        push ecx
        push edx
        push edi
        push esi
        mov esi, edx
        movzx ecx, byte ptr [eax+0xd]
        mov edi, [eax+8]
    an_lp:
        dec ecx
        js an_no
        mov eax, [edi+ecx*4]
        test eax, eax
        jz an_lp
        lea edx, [ebx+%(mtnvmt)#x]
        cmp [eax], edx
        jne an_lp
        movzx edx, byte ptr [eax+0x10]
        cmp edx, [ebp-0x30]
        jne an_lp
        movzx edx, byte ptr [eax+0x11]
        cmp edx, [ebp-0x34]
        jne an_lp
        mov edx, [eax+8]
        test edx, edx
        jz an_lp
        mov edx, [edx+0x28]
        test edx, edx
        jz an_lp
        cmp dword ptr [edx+4], %(minlen)d
        jb an_short
        test esi, esi
        jz an_out
        jmp an_lp
    an_short:
        test esi, esi
        jnz an_out
        jmp an_lp
    an_no:
        xor eax, eax
    an_out:
        pop esi
        pop edi
        pop edx
        pop ecx
        ret

    t_lavaok:
        push edi
        push edx
        push ecx
        mov edi, eax
        movzx eax, byte ptr [edi+0x14]
        cmp dword ptr [ebp-0xC], 0
        jne lo_ug
        cmp eax, 0xc
        je lo_t
        cmp eax, 1
        jb lo_no
        cmp eax, 5
        ja lo_no
        jmp lo_t
    lo_ug:
        cmp eax, 0xc
        jne lo_no
    lo_t:
        mov al, [edi+0x15]
        cmp al, 0xff
        je lo_o
        cmp al, 1
        je lo_o
        cmp al, 3
        jne lo_no
    lo_o:
        mov eax, edi
        call t_guard2
        test eax, eax
        jz lo_no
        push dword ptr [ebp-0x2C]
        mov dword ptr [ebp-0x2C], 0
        mov eax, edi
        call t_mtnof
        pop dword ptr [ebp-0x2C]
        test eax, eax
        jnz lo_no
        mov eax, edi
        call t_roads
        test eax, eax
        jnz lo_no
        mov eax, edi
        call t_multi
        test eax, eax
        jnz lo_no
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_simple
        test eax, eax
        jz lo_no
        mov eax, 1
        jmp lo_out
    lo_no:
        xor eax, eax
    lo_out:
        pop ecx
        pop edx
        pop edi
        ret

    t_mklava:
        push esi
        push edi
        push edx
        push ecx
        call t_getf
        test eax, eax
        jz mk_no
        mov edi, eax
        movzx eax, byte ptr [edi+0x14]
        mov [ebp-0xC4], eax
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_clear
        mov eax, %(lava)d
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_chg
        cmp byte ptr [edi+0x14], %(lava)d
        jne mk_no
        mov eax, edi
        mov edx, [ebp-0xC4]
        mov ecx, 1
        call t_mark
        dec dword ptr [ebp-0xD0]
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_melt
        mov eax, 1
        jmp mk_out
    mk_no:
        xor eax, eax
    mk_out:
        pop ecx
        pop edx
        pop edi
        pop esi
        ret

    t_mark:
        push esi
        push edi
        push ecx
        mov esi, eax
        mov edi, edx
        call t_ours
        test eax, eax
        jnz mk_have
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(fwcls)#x]
        call %(eocreate)#x
        push eax
        mov edx, edi
        and dl, 0xf
        or dl, 0x10
        mov byte ptr [eax+0xe], dl
        mov dl, byte ptr [ebp-0xA4]
        mov byte ptr [eax+0xd], dl
        mov dl, byte ptr [esi+0x14]
        mov byte ptr [eax+0xf], dl
        mov dl, byte ptr [esp+4]
        mov byte ptr [eax+0xc], dl
        movzx ecx, byte ptr [esi+0x11]
        push ecx
        movzx ecx, byte ptr [esi+0x12]
        push ecx
        movzx ecx, byte ptr [esi+0x10]
        mov edx, eax
        mov eax, [ebx+%(map)#x]
        call %(placehx)#x
        pop eax
        jmp mkm_x
    mk_have:
        mov dl, byte ptr [esi+0x14]
        mov byte ptr [eax+0xf], dl
    mkm_x:
        pop ecx
        pop edi
        pop esi
        ret

    t_volcof:
        push ecx
        push edx
        push edi
        movzx ecx, byte ptr [eax+0xd]
        mov edi, [eax+8]
        lea edx, [ebx+%(mtnvmt)#x]
    vo_lp:
        dec ecx
        js vo_no
        mov eax, [edi+ecx*4]
        test eax, eax
        jz vo_lp
        cmp [eax], edx
        jne vo_lp
        push eax
        mov eax, [eax+8]
        test eax, eax
        jz vo_skip
        mov eax, [eax+0x28]
        test eax, eax
        jz vo_skip
        cmp dword ptr [eax+4], %(minlen)d
        jb vo_skip
        pop eax
        jmp vo_out
    vo_skip:
        pop eax
        jmp vo_lp
    vo_no:
        xor eax, eax
    vo_out:
        pop edi
        pop edx
        pop ecx
        ret

    t_conv:
        push edi
        mov edi, eax
        xor eax, eax
        mov [ebp-0x2C], eax
        mov [ebp-0x38], eax
        cmp dword ptr [ebp-0x108], 0
        jne cv_pk1
        mov eax, edi
        call t_mtnof
        jmp cv_got
    cv_pk1:
        mov eax, edi
        xor edx, edx
        call t_anch
    cv_got:
        test eax, eax
        jz cv_out
        mov ecx, [eax+8]
        test ecx, ecx
        jz cv_out
        mov ecx, [ecx+0x28]
        test ecx, ecx
        jz cv_out
        cmp dword ptr [ebp-0x108], 0
        jne cv_m1
        cmp dword ptr [ecx+4], 19
        ja cv_out
        jmp cv_lok
    cv_m1:
        cmp dword ptr [ecx+4], %(minlen)d
        jb cv_out
    cv_lok:
        mov [ebp-0x2C], eax
        mov ecx, [eax+8]
        mov [ebp-0xE0], ecx
        call t_size
        mov [ebp-0xC0], eax
        cmp eax, 4
        je cv_s
        cmp eax, 9
        jne cv_out
        lea eax, [ebx+%(d_vl)#x]
        cmp dword ptr [ebp-0x108], 0
        je cv_sz
        lea eax, [ebx+%(d_ml)#x]
        jmp cv_sz
    cv_s:
        lea eax, [ebx+%(d_vs)#x]
        cmp dword ptr [ebp-0x108], 0
        je cv_sz
        lea eax, [ebx+%(d_ms)#x]
    cv_sz:
        mov [ebp-0xC4], eax
        mov eax, [ebp-0x2C]
        movzx edx, byte ptr [eax+0x10]
        mov [ebp-0x30], edx
        movzx edx, byte ptr [eax+0x11]
        mov [ebp-0x34], edx
        mov eax, [ebp-0xE0]
        call t_oldok
        test eax, eax
        jz cv_out
        mov dword ptr [ebp-0x24], %(vterr)d
        mov eax, [ebp-0xC4]
        call t_pick
        test eax, eax
        jz cv_out
        mov [ebp-0x28], eax
        call t_vfpok
        test eax, eax
        jz cv_out
        cmp dword ptr [ebp-0x108], 0
        je cv_clr
        mov eax, [ebp-0x11C]
        test eax, eax
        jz cv_clr
        call t_kill
        xor eax, eax
        mov [ebp-0x11C], eax
    cv_clr:
        mov eax, [ebp-0xE0]
        call t_clearfp
        mov eax, [ebp-0x28]
        call t_clearfp
        mov eax, [ebp-0x28]
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_create
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_getf
        test eax, eax
        jz cv_fail
        mov edi, eax
        cmp dword ptr [ebp-0x108], 0
        jne cv_v1
        xor edx, edx
        call t_anch
        test eax, eax
        jz cv_fail
        push eax
        call t_untect
        mov ecx, [ebp-0xE0]
        mov ecx, [ecx+0x28]
        mov ecx, [ecx+8]
        movzx ecx, byte ptr [ecx]
        cmp dword ptr [ebp-0xC0], 9
        jne cv_mk
        or ecx, 0x80
    cv_mk:
        mov eax, edi
        mov edx, 0xf
        call t_mark
        inc dword ptr [ebp-0x18]
        pop eax
        mov [ebp-0x2C], eax
        xor eax, eax
        mov [ebp-0x38], eax
        mov eax, [ebp-4]
        mov edx, %(convmax)d
        call %(rnd)#x
        inc eax
        call t_burst
        jmp cv_out
    cv_v1:
        mov edx, 1
        call t_anch
        test eax, eax
        jz cv_fail
        jmp cv_out
    cv_fail:
        mov eax, [ebp-0xE0]
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_create
        cmp dword ptr [ebp-0x108], 0
        je cv_out
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_getf
        test eax, eax
        jz cv_out
        push eax
        mov eax, [ebp-4]
        mov edx, %(revrnd)d
        call %(rnd)#x
        add eax, %(revbase)d
        or eax, 0x40
        mov ecx, eax
        pop eax
        mov edx, 0xf
        call t_mark
    cv_out:
        cmp dword ptr [ebp-0x108], 0
        je cv_x
        mov eax, [ebp-0x11C]
        test eax, eax
        jz cv_x
        call t_cntdn
        xor eax, eax
        mov [ebp-0x11C], eax
    cv_x:
        xor eax, eax
        mov [ebp-0x2C], eax
        mov [ebp-0x38], eax
        pop edi
        ret

    t_guard2t:
        push eax
        mov edx, [ebx+%(structref)#x]
        call %(findnt)#x
        test eax, eax
        jnz g2t_no
        mov eax, [esp]
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz g2t_yes
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf0
        cmp dl, 0x10
        je g2t_yes
        and dl, 0xe0
        cmp dl, 0x20
        jne g2t_no
    g2t_yes:
        pop eax
        mov eax, 1
        ret
    g2t_no:
        pop eax
        xor eax, eax
        ret

    t_guardt:
        push eax
        call t_guard2t
        test eax, eax
        jz gtt_no
        mov eax, [esp]
        mov edx, %(armyid)d
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz gtt_no
        pop eax
        mov eax, 1
        ret
    gtt_no:
        pop eax
        xor eax, eax
        ret

    t_untect:
        push edi
        mov eax, [ebp-0xE0]
        call ut_one
        mov eax, [ebp-0x28]
        call ut_one
        pop edi
        ret
    ut_one:
        mov eax, [eax+0x28]
        mov [ebp-0x134], eax
        xor edi, edi
    ut_l:
        mov eax, [ebp-0x134]
        cmp edi, [eax+4]
        jge ut_x
        cmp edi, 19
        jae ut_x
        mov eax, [eax+8]
        cmp byte ptr [eax+edi*2], 0x80
        jae ut_n
        mov eax, edi
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call t_getf
        test eax, eax
        jz ut_n
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz ut_n
        mov dl, byte ptr [eax+0xe]
        and dl, 0xe0
        cmp dl, 0x20
        jne ut_n
        call t_kill
    ut_n:
        inc edi
        jmp ut_l
    ut_x:
        ret

    t_oldok:
        push edi
        mov eax, [eax+0x28]
        mov [ebp-0x90], eax
        xor edi, edi
    ok_l:
        mov eax, [ebp-0x90]
        cmp edi, [eax+4]
        jge ok_yes
        cmp edi, 19
        jae ok_yes
        mov eax, [eax+8]
        cmp byte ptr [eax+edi*2], 0x80
        jae ok_n
        mov eax, edi
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call t_getf
        test eax, eax
        jz ok_no
        call t_guard2t
        test eax, eax
        jz ok_no
    ok_n:
        inc edi
        jmp ok_l
    ok_yes:
        mov eax, 1
        pop edi
        ret
    ok_no:
        xor eax, eax
        pop edi
        ret

    t_vfpok:
        push edi
        mov eax, [ebp-0x28]
        mov eax, [eax+0x28]
        mov [ebp-0x90], eax
        xor edi, edi
    vf_l:
        mov eax, [ebp-0x90]
        cmp edi, [eax+4]
        jge vf_yes
        mov eax, [eax+8]
        movzx eax, word ptr [eax+edi*2]
        mov [ebp-0x8C], eax
        cmp ax, 0xfefe
        je vf_n
        cmp al, 0x80
        jb vf_used
        cmp ah, 0x80
        jae vf_n
    vf_used:
        cmp edi, 19
        jae vf_no
        mov eax, edi
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_getf
        test eax, eax
        jz vf_no
        mov [ebp-0x84], eax
        cmp byte ptr [ebp-0x8C], 0x80
        jae vf_art
        cmp byte ptr [eax+0x15], 0
        jne vf_new
        call t_hasown
        test eax, eax
        jnz vf_n
    vf_new:
        mov eax, [ebp-0x84]
        call t_guardt
        test eax, eax
        jz vf_no
        mov eax, [ebp-0x84]
        call t_mtnof
        test eax, eax
        jnz vf_no
        mov eax, [ebp-0x84]
        call t_roads
        test eax, eax
        jnz vf_no
        mov eax, [ebp-0x84]
        call t_multi
        test eax, eax
        jnz vf_no
        mov eax, [ebp-0x84]
        movzx ecx, byte ptr [eax+0x14]
        cmp ecx, 0xc
        je vf_ter
        cmp ecx, 1
        jb vf_no
        cmp ecx, 5
        ja vf_no
    vf_ter:
        mov cl, [eax+0x15]
        cmp cl, 0xff
        je vf_ov
        cmp cl, 1
        je vf_ov
        cmp cl, 2
        je vf_ov
        cmp cl, 3
        jne vf_no
    vf_ov:
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_simple
        test eax, eax
        jz vf_no
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_vadd
        jmp vf_n
    vf_art:
        mov eax, [ebp-0x84]
        call t_guardt
        test eax, eax
        jz vf_no
        mov eax, [ebp-0x84]
        call t_mtnof
        test eax, eax
        jnz vf_no
    vf_n:
        inc edi
        jmp vf_l
    vf_yes:
        mov eax, 1
        pop edi
        ret
    vf_no:
        xor eax, eax
        pop edi
        ret

    t_clearfp:
        push edi
        mov eax, [eax+0x28]
        mov [ebp-0x90], eax
        mov dword ptr [ebp-0x94], 2
    cf_p:
        xor edi, edi
    cf_l:
        mov eax, [ebp-0x90]
        cmp edi, [eax+4]
        jge cf_np
        cmp edi, 19
        jae cf_np
        mov eax, [eax+8]
        cmp byte ptr [eax+edi*2], 0x80
        jae cf_n
        mov eax, edi
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        push edx
        push ecx
        call t_getf
        pop ecx
        pop edx
        test eax, eax
        jz cf_n
        call t_clear
    cf_n:
        inc edi
        jmp cf_l
    cf_np:
        dec dword ptr [ebp-0x94]
        jnz cf_p
        pop edi
        ret

    t_getf:
        test edx, edx
        js tg_no
        test ecx, ecx
        js tg_no
        cmp edx, [esi+0xc]
        jge tg_no
        cmp ecx, [esi+0x10]
        jge tg_no
        mov eax, esi
        call %(getfield)#x
        ret
    tg_no:
        xor eax, eax
        ret

    t_hn:
        push edi
        lea edi, [ebx+%(hntab)#x]
        test dl, 1
        jz hn_e
        add edi, 38
    hn_e:
        lea edi, [edi+eax*2]
        movsx eax, byte ptr [edi]
        add edx, eax
        movsx eax, byte ptr [edi+1]
        add ecx, eax
        pop edi
        ret

    t_open:
        test eax, eax
        jz to_no
        movzx edx, byte ptr [eax+0x14]
        test edx, edx
        jz to_no
        cmp edx, 7
        jb to_ov
        cmp edx, 0xa
        jbe to_no
    to_ov:
        cmp byte ptr [eax+0x15], 0
        je to_no
        mov eax, 1
        ret
    to_no:
        xor eax, eax
        ret

    t_openxy:
        push edx
        push ecx
        mov eax, ecx
        shl eax, 16
        and edx, 0xffff
        or eax, edx
        mov ecx, [ebp-0x38]
    ox_lp:
        dec ecx
        js ox_real
        cmp eax, [ebp+ecx*4-0x100]
        jne ox_lp
        pop ecx
        pop edx
        xor eax, eax
        ret
    ox_real:
        mov ecx, [esp]
        mov edx, [esp+4]
        call t_getf
        call t_open
        pop ecx
        pop edx
        ret

    t_vadd:
        mov eax, [ebp-0x38]
        cmp eax, 8
        jae va_x
        push edx
        push ecx
        shl ecx, 16
        and edx, 0xffff
        or ecx, edx
        mov [ebp+eax*4-0x100], ecx
        inc dword ptr [ebp-0x38]
        pop ecx
        pop edx
    va_x:
        ret

    t_simple:
        push edi
        push edx
        push ecx
        push 0
        xor edi, edi
    ts_l:
        mov edx, [esp+8]
        mov ecx, [esp+4]
        lea eax, [edi+1]
        call t_hn
        call t_openxy
        test eax, eax
        jz ts_n
        mov ecx, edi
        mov eax, 1
        shl eax, cl
        or [esp], eax
    ts_n:
        inc edi
        cmp edi, 6
        jb ts_l
        mov eax, [esp]
        mov edx, eax
        shr edx, 1
        mov ecx, eax
        shl ecx, 5
        or edx, ecx
        and edx, 0x3f
        not edx
        and eax, edx
        lea edx, [eax-1]
        test eax, edx
        jz ts_yes
        push 0
        mov edi, 1
    tw_l:
        mov edx, [esp+0xc]
        mov ecx, [esp+8]
        mov eax, edi
        call t_hn
        call t_openxy
        test eax, eax
        jz tw_n
        bts dword ptr [esp], edi
    tw_n:
        inc edi
        cmp edi, 19
        jb tw_l
        push esi
        lea esi, [ebx+%(adj)#x]
        bsf ecx, dword ptr [esp+8]
        inc ecx
        xor eax, eax
        bts eax, ecx
    tw_it:
        mov edx, eax
        xor edi, edi
    tw_s:
        bt edx, edi
        jnc tw_sn
        push edx
        lea ecx, [edi+edi*2]
        add ecx, ecx
        push edi
        mov edi, 6
    tw_d:
        movzx edx, byte ptr [esi+ecx]
        cmp edx, 19
        jae tw_dn
        bt dword ptr [esp+0xc], edx
        jnc tw_dn
        bts eax, edx
    tw_dn:
        inc ecx
        dec edi
        jnz tw_d
        pop edi
        pop edx
    tw_sn:
        inc edi
        cmp edi, 19
        jb tw_s
        cmp eax, edx
        jne tw_it
        mov edx, [esp+8]
        shl edx, 1
        and eax, edx
        cmp eax, edx
        sete al
        movzx eax, al
        pop esi
        add esp, 4
        jmp ts_out
    ts_yes:
        mov eax, 1
    ts_out:
        add esp, 4
        pop ecx
        pop edx
        pop edi
        ret

    t_ours:
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz ou_x
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf0
        cmp dl, 0x10
        je ou_x
        xor eax, eax
    ou_x:
        ret

    t_guard2:
        push eax
        mov edx, [ebx+%(structref)#x]
        call %(findnt)#x
        test eax, eax
        jnz g2_no
        mov eax, [esp]
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz g2_yes
        mov dl, byte ptr [eax+0xe]
        and dl, 0xf0
        cmp dl, 0x10
        jne g2_no
    g2_yes:
        pop eax
        mov eax, 1
        ret
    g2_no:
        pop eax
        xor eax, eax
        ret

    t_guard:
        push eax
        call t_guard2
        test eax, eax
        jz gd_no
        mov eax, [esp]
        mov edx, %(armyid)d
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz gd_no
        pop eax
        mov eax, 1
        ret
    gd_no:
        pop eax
        xor eax, eax
        ret

    t_mtnof:
        push ecx
        push edx
        push edi
        movzx ecx, byte ptr [eax+0xd]
        mov edi, [eax+8]
        lea edx, [ebx+%(mtnvmt)#x]
    mo_lp:
        dec ecx
        js mo_no
        mov eax, [edi+ecx*4]
        test eax, eax
        jz mo_lp
        cmp [eax], edx
        jne mo_lp
        cmp eax, [ebp-0x2C]
        je mo_lp
        jmp mo_out
    mo_no:
        xor eax, eax
    mo_out:
        pop edi
        pop edx
        pop ecx
        ret

    t_hasown:
        push ecx
        push edi
        movzx ecx, byte ptr [eax+0xd]
        mov edi, [eax+8]
        mov edx, [ebp-0x2C]
        xor eax, eax
        test edx, edx
        jz ho_out
    ho_lp:
        dec ecx
        js ho_out
        cmp [edi+ecx*4], edx
        jne ho_lp
        inc eax
    ho_out:
        pop edi
        pop ecx
        ret

    t_multi:
        push esi
        push edi
        push ebp
        mov esi, eax
        movzx edi, byte ptr [esi+0xd]
    ml_lp:
        dec edi
        js ml_no
        mov eax, [esi+8]
        mov eax, [eax+edi*4]
        test eax, eax
        jz ml_lp
        mov ebp, eax
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, %(tmocid)#x
        jne ml_lp
        mov eax, ebp
        call t_size
        cmp eax, 1
        jbe ml_lp
        movzx edx, byte ptr [esi+0xc]
        shl edx, 2
        add edx, [esi+8]
        movzx ecx, byte ptr [edx+edi]
        mov eax, [ebp+8]
        mov eax, [eax+0x28]
        cmp ecx, [eax+4]
        jae ml_yes
        mov edx, [eax+8]
        cmp byte ptr [edx+ecx*2+1], 2
        je ml_lp
    ml_yes:
        mov eax, 1
        jmp ml_out
    ml_no:
        xor eax, eax
    ml_out:
        pop ebp
        pop edi
        pop esi
        ret

    t_roads:
        push esi
        push edi
        push 0
        mov esi, eax
        movzx edi, byte ptr [esi+0xd]
    rd_lp:
        dec edi
        js rd_out
        mov eax, [esi+8]
        mov eax, [eax+edi*4]
        test eax, eax
        jz rd_lp
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, %(roadid)#x
        jne rd_b
        or dword ptr [esp], 1
        jmp rd_lp
    rd_b:
        cmp eax, %(bridgeid)#x
        je rd_br
        cmp eax, %(hbridgeid)#x
        jne rd_lp
    rd_br:
        or dword ptr [esp], 2
        jmp rd_lp
    rd_out:
        pop eax
        pop edi
        pop esi
        ret

    t_clear:
        push dword ptr [ebp-0xC]
        push 0
        push -1
        mov eax, [ebp-4]
        call %(clear)#x
        ret

    t_create:
        push edi
        push eax
        push edx
        push ecx
        mov eax, [ebp-4]
        mov edx, 0xffffff
        call %(rnd)#x
        mov edx, [ebx+%(randseed)#x]
        mov [edx], eax
        pop ecx
        pop edx
        pop eax
        mov edi, [eax]
        push ecx
        push dword ptr [ebp-0xC]
        mov cl, dl
        mov edx, [ebp-4]
        call dword ptr [edi+0x68]
        pop edi
        ret

    t_pick:
        push edi
        push esi
        mov edi, eax
        xor eax, eax
        mov [ebp-0x7C], eax
        or dword ptr [ebp-0x80], -1
    tp_pass:
        mov eax, [ebx+%(resg)#x]
        test eax, eax
        jz tp_none
        mov eax, [eax+0x24]
        test eax, eax
        jz tp_none
        mov eax, [eax+8]
        test eax, eax
        jz tp_none
        mov esi, [eax+4]
        push dword ptr [eax+8]
    tp_lp:
        dec dword ptr [esp]
        js tp_end
        mov eax, [esp]
        mov eax, [esi+eax*4]
        test eax, eax
        jz tp_lp
        push eax
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, [edi]
        pop eax
        jne tp_lp
        cmp byte ptr [eax+0x44], 0
        jne tp_lp
        mov edx, [eax+0x28]
        test edx, edx
        jz tp_lp
        push eax
        mov ecx, [edx+4]
        movzx eax, byte ptr [edi+9]
        cmp ecx, eax
        ja tp_rej
        movzx eax, byte ptr [edi+10]
        cmp ecx, eax
        jb tp_rej
        mov edx, [edx+8]
        test edx, edx
        jz tp_rej
        push ecx
        xor eax, eax
    tp_u:
        dec ecx
        js tp_ud
        cmp byte ptr [edx+ecx*2], 0x80
        jae tp_u
        inc eax
        jmp tp_u
    tp_ud:
        pop ecx
        cmp al, [edi+4]
        jne tp_rej
        movzx eax, byte ptr [edi+5]
        cmp eax, ecx
        jae tp_rej
        push ecx
        mov cl, [edx+eax*2]
        cmp cl, byte ptr [ebp-0x24]
        jne tp_rej1
        mov cl, [edx+eax*2+1]
        cmp cl, [edi+6]
        jne tp_rej1
        pop ecx
        movzx eax, byte ptr [edi+7]
        cmp al, 0xff
        je tp_ok
        cmp eax, ecx
        jae tp_rej
        push ecx
        mov cl, [edx+eax*2]
        cmp cl, byte ptr [ebp-0x24]
        jne tp_rej1
        mov cl, [edx+eax*2+1]
        cmp cl, [edi+8]
        jne tp_rej1
        pop ecx
    tp_ok:
        pop eax
        cmp dword ptr [ebp-0x80], -1
        jne tp_sel
        inc dword ptr [ebp-0x7C]
        jmp tp_lp
    tp_sel:
        cmp dword ptr [ebp-0x80], 0
        je tp_found
        dec dword ptr [ebp-0x80]
        jmp tp_lp
    tp_rej1:
        pop ecx
    tp_rej:
        pop eax
        jmp tp_lp
    tp_found:
        add esp, 4
        jmp tp_out
    tp_end:
        add esp, 4
        cmp dword ptr [ebp-0x80], -1
        jne tp_none
        mov edx, [ebp-0x7C]
        test edx, edx
        jz tp_none
        mov eax, [ebp-4]
        call %(rnd)#x
        mov [ebp-0x80], eax
        jmp tp_pass
    tp_none:
        xor eax, eax
    tp_out:
        pop esi
        pop edi
        ret

    t_size:
        push ecx
        push edx
        xor ecx, ecx
        mov edx, [eax+8]
        test edx, edx
        jz sz_x
        mov edx, [edx+0x28]
        test edx, edx
        jz sz_x
        mov ecx, [edx+4]
        mov edx, [edx+8]
        xor eax, eax
    sz_u:
        dec ecx
        js sz_out
        cmp byte ptr [edx+ecx*2], 0x80
        jae sz_u
        inc eax
        jmp sz_u
    sz_x:
        xor eax, eax
    sz_out:
        pop edx
        pop ecx
        ret

    t_kill:
        mov dl, 1
        mov ecx, [eax]
        call dword ptr [ecx-4]
        ret

    """)
    # GLOW: called from the TFrozenWaterHS.Show site (ebx = marker, eax = list, ecx = x; stack: ret, surface, phase,
    # tick, y).  Our markers ([+0xE] & 0xF0 == 0x10) -> pure frame pick of spell 227 gfx slot GLOW_SLOT, `ret 0x10`.
    # Anything else -> the previous owner (Tectonic's glow cave) with every register as it came.
    if glow_orig[0] == 0xE8:
        gprev = "jmp %#x" % (GLOW_SITE + 5 + struct.unpack_from("<i", glow_orig, 1)[0])
    elif glow_orig[:5] == GLOW_VANILLA[:5] and glow_orig[5] == 0xE8:
        gprev = "mov edx, 0x46\n        jmp %#x" % (GLOW_SITE + 10 + struct.unpack_from("<i", glow_orig, 6)[0])
    else:
        raise ValueError("glow site %#x: unexpected bytes %s" % (GLOW_SITE, glow_orig.hex()))
    place("glow", """
        mov dl, byte ptr [ebx+0xe]
        and dl, 0xf0
        cmp dl, 0x10
        je gl_ours
        """ + gprev + """
    gl_ours:
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        push ecx
        call $D
        pop esi
        sub esi, $D
        mov eax, [esi+%(hsset)#x]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz gl_out
        mov eax, [eax+0x2c]
        test eax, eax
        jz gl_out
        mov edx, %(gslot)d
        call %(getseq)#x
        test eax, eax
        jz gl_out
        mov esi, eax
        mov edi, [esi+0x1c]
        mov ecx, [edi+8]
        test ecx, ecx
        jz gl_out
        mov eax, [ebp+0x10]
        xor edx, edx
        mov ebx, %(gperiod)d
        div ebx
        add eax, [ebp+0xc]
        xor edx, edx
        div ecx
        mov eax, [edi+4]
        mov edi, [eax+edx*4]
        mov edx, edi
        mov eax, [esi+0x10]
        call %(exist)#x
        test al, al
        jz gl_out
        push dword ptr [ebp+8]
        mov edx, edi
        mov eax, [esi+0x10]
        call %(libget)#x
        mov ecx, [ebp+0x14]
        add ecx, [esi+0x28]
        mov edx, [ebp-0x10]
        add edx, [esi+0x24]
        mov ebx, [eax]
        call dword ptr [ebx+0x84]
    gl_out:
        pop ecx
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10
    """, pic=True)
    # ce_plain: the vanilla CreateEnchantment body (only reached when the CE site was vanilla at apply time)
    place("ce_plain", """
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(amcell)#x]
        pop ebx
        xor ecx, ecx
        mov dl, 1
        call %(amcreate)#x
        ret
    """, pic=True)
    C.update(prev_ce=prev["CE"] if prev["CE"] is not None else where["ce_plain"], prev_mm=prev["MM"], prev_nt=prev["NT"],
             prev_ac=prev["AC"], prev_de=prev["DE"], prev_chk=prev["CHK"])
    # oga: dl = player index (0x80 = any), ecx = spell id -> al = 1 if an ACTIVE enchantment of that spell exists
    place("oga", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        push ebp
        mov ebp, ecx
        movsx edi, dl
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz oga_no
        mov eax, [eax+0x188]
        test eax, eax
        jz oga_no
        mov esi, [eax+0x14]
        test esi, esi
        jz oga_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    oga_lp:
        dec ecx
        js oga_no
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz oga_lp
        cmp dword ptr [eax+0x14], ebp
        jne oga_lp
        test byte ptr [eax+0x10], 1
        jz oga_lp
        cmp edi, -0x80
        je oga_yes
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne oga_lp
    oga_yes:
        mov eax, 1
        jmp oga_out
    oga_no:
        xor eax, eax
    oga_out:
        pop ebp
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """, pic=True)
    place("ce", """
        cmp dword ptr [eax+0x10], %(id)d
        jne ce_prev
        push eax
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(amcell)#x]
        pop ebx
        xor ecx, ecx
        mov dl, 1
        call %(amcreate)#x
        pop edx
        mov dword ptr [eax+0x14], %(id)d
        push eax
        lea eax, [eax+0x1c]
        mov edx, [edx+8]
        call %(lstrasg)#x
        pop eax
        ret
    ce_prev:
        jmp %(prev_ce)#x
    """, pic=True)
    place("mm", """
        cmp dword ptr [edi+0x10], %(id)d
        je mm_skip
        jmp %(prev_mm)#x
    mm_skip:
        ret
    """)
    place("ac", """
        cmp dword ptr [eax+0x14], %(id)d
        je ac_ours
        jmp %(prev_ac)#x
    ac_ours:
        jmp %(bact)#x
    """)
    place("de", """
        cmp dword ptr [eax+0x14], %(id)d
        je de_ours
        jmp %(prev_de)#x
    de_ours:
        jmp %(bdeact)#x
    """)
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        jmp %(prev_chk)#x
    chk_ours:
        push eax
        push ecx
        push edx
        call %(bchk)#x
        test al, al
        pop edx
        pop ecx
        pop eax
        jnz chk_base_ok
        xor eax, eax
        ret
    chk_base_ok:
        push eax
        push ecx
        mov ecx, %(id)d
        call %(oga)#x
        pop ecx
        test al, al
        pop eax
        jnz chk_refuse
        mov eax, 1
        ret
    chk_refuse:
        push ebp
        mov ebp, esp
        add esp, -0x18
        push ebx
        push esi
        push edi
        xor ebx, ebx
        mov [ebp-8], ebx
        mov [ebp-0x14], ebx
        mov [ebp-0x18], ebx
        mov edi, ecx
        mov [ebp-1], dl
        mov esi, eax
        call $D
        pop eax
        sub eax, $D
        add eax, %(amseh)#x
        push ebp
        push eax
        xor eax, eax
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        jmp %(ammsg)#x
    """, pic=True)
    # NT (called; eax = pmc): the previous owner first; then for the player whose turn starts: an ACTIVE Pyroclasm of
    # his -> SHIFT (engine eax = 0); NO active Pyroclasm of ANY player -> REVERT (eax = 1) of this player's markers.
    place("nt", """
        push eax
        call %(prev_nt)#x
        pop eax
        pushad
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [esi+0x10]
        test eax, eax
        jz nt_out
        mov dl, byte ptr [eax+0xa6]
        movsx edi, dl
        mov ecx, %(id)d
        call %(oga)#x
        test al, al
        jz nt_rev
        xor eax, eax
        call %(engine)#x
        jmp nt_out
    nt_rev:
        mov dl, 0x80
        mov ecx, %(id)d
        call %(oga)#x
        test al, al
        jnz nt_out
        mov eax, 1
        call %(engine)#x
    nt_out:
        popad
        ret
    """, pic=True)
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


def site_off(d, nm):
    va, kind, _c = SITES[nm]
    return (data_off(d, va), 4) if kind == "vmt" else (vaoff(va), 5)


def hook_bytes(nm, where):
    va, kind, cave = SITES[nm]
    tgt = where[cave]
    if kind == "vmt": return struct.pack("<I", tgt)
    return (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", tgt - (va + 5))


def glow_hook(where, glow_orig):
    """10 bytes at the glow site: `call glow` + the original tail (the 5 nops behind a chained call) or 5 nops."""
    tail = glow_orig[5:10] if glow_orig[0] == 0xE8 else b"\x90" * 5
    return b"\xe8" + struct.pack("<i", where["glow"] - (GLOW_SITE + 5)) + tail


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=None, help="patch this file instead of the live AoWEPACK.dll (scratch testing)")
    a = ap.parse_args()
    dll = a.dll or game_file("AoWEPACK.dll")
    d = bytearray(open(dll, "rb").read())
    print("target:", dll)
    assert vaoff(ZONE_END) <= len(d), "zone past the end of the file"
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or GLOW_SITE <= r < GLOW_SITE + 10
           or any(SITES[nm][1] != "vmt" and SITES[nm][0] <= r < SITES[nm][0] + 5 for nm in ORDER)]
    noreloc = [nm for nm in ORDER if SITES[nm][1] == "vmt" and SITES[nm][0] not in rl]
    if bad or noreloc: print("ABORT: relocs in zone/code sites %s | VMT slots without reloc %s" % (bad, noreloc)); return 1
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)])
    live = {}
    for nm in ORDER:
        o, n = site_off(d, nm); live[nm] = bytes(d[o:o + n])
    live_glow = bytes(d[vaoff(GLOW_SITE):vaoff(GLOW_SITE) + 10])
    stored, gstored = unpack_table(zl)
    if stored is None and any(zl):
        print("ABORT: zone %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    orig = stored if stored is not None else live
    glow_orig = gstored if gstored is not None else live_glow
    try:
        code, where = build(orig, glow_orig)
    except ValueError as e:
        print("ABORT:", e); return 1
    assert ZONE + len(code) <= ZONE_END, "zone overflow"
    want = {nm: hook_bytes(nm, where) for nm in ORDER}
    want_glow = glow_hook(where, glow_orig)
    state = {}
    for nm in ORDER:
        if stored is None: state[nm] = "free"; continue
        if live[nm] == want[nm]: state[nm] = "ours"; continue
        va, kind, _c = SITES[nm]
        t = (struct.unpack("<I", live[nm])[0] if kind == "vmt" else
             va + 5 + struct.unpack_from("<i", live[nm], 1)[0] if live[nm][0] in (0xE8, 0xE9) else None)
        state[nm] = "ours(old)" if t is not None and ZONE <= t < ZONE_END else "OTHER"
    if stored is None: gstate = "free"
    elif live_glow == want_glow: gstate = "ours"
    elif live_glow[0] == 0xE8 and ZONE <= GLOW_SITE + 5 + struct.unpack_from("<i", live_glow, 1)[0] < ZONE_END: gstate = "ours(old)"
    else: gstate = "OTHER"
    if stored is None: zstate = "zero"
    elif zl[:len(code)] == code and not any(zl[len(code):]): zstate = "ours"
    else: zstate = "ours(old)"
    print("zone %s (%d B of %d) | sites %s | glow %s (prev %s)" % (zstate, len(code), ZONE_END - ZONE, state, gstate, glow_orig.hex()))
    print("chained to: " + ", ".join("%s->%s" % (nm, "ce_plain" if prev_target(nm, orig[nm]) is None else "%#x" % prev_target(nm, orig[nm])) for nm in ORDER))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        inv = {v: k for k, v in where.items()}
        st = where["engine"]
        for i in md.disasm(code[st - ZONE:], st):
            if i.address in inv: print("  -- %s" % inv[i.address])
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if stored is None: print("already vanilla (zone free)"); return 0
        if any(s == "OTHER" for s in state.values()) or gstate == "OTHER":
            print("ABORT: a site no longer points at us (something chained in front - revert that first): %s glow %s" % (state, gstate)); return 1
        for nm in ORDER:
            o, n = site_off(d, nm); d[o:o + n] = stored[nm]
        d[vaoff(GLOW_SITE):vaoff(GLOW_SITE) + 10] = gstored
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        with open(dll, "r+b") as f: f.write(bytes(d))
        print("reverted (sites restored: %s; glow %s; zone zeroed)" % (", ".join("%s=%s" % (nm, stored[nm].hex()) for nm in ORDER), gstored.hex())); return 0
    if zstate == "ours" and all(s == "ours" for s in state.values()) and gstate == "ours":
        print("already applied (v3)"); return 0
    if stored is not None and (any(s == "OTHER" for s in state.values()) or gstate == "OTHER"):
        print("ABORT: zone is ours but a site was taken over by someone else (revert that patch first, LIFO): %s glow %s" % (state, gstate)); return 1
    new = bytearray(d)
    new[vaoff(ZONE):vaoff(ZONE_END)] = code + bytes(ZONE_END - ZONE - len(code))
    for nm in ORDER:
        o, n = site_off(new, nm); new[o:o + n] = want[nm]
    new[vaoff(GLOW_SITE):vaoff(GLOW_SITE) + 10] = want_glow
    print("%d bytes change" % sum(1 for x, y in zip(d, new) if x != y))
    if stored is not None and zl[:8] in (MAGIC_V1, MAGIC_V2): print("(in-place upgrade %s -> v3)" % zl[6:8].decode())
    import patch_terrain_armyhooks_v1 as AH
    if not AH.applied(bytes(d)):
        print("ABORT: patch_terrain_armyhooks_v1.py is not applied - v3 spreads lava under armies only through its CanChangeTerrain hook (apply it first)"); return 1
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll is None:
        bak = bak_path(dll, (BAK_SUFFIX_V2 if zl[:8] == MAGIC_V1 else BAK_SUFFIX_V3) if stored is not None else BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(dll, bak); print("backup ->", bak)
    with open(dll, "r+b") as f: f.write(bytes(new))
    assert open(dll, "rb").read() == bytes(new); print("AoWEPACK: written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
