"""
TECTONIC SHIFT (spell 219, Earth tier 4; Spells.pfs key 229) - a GLOBAL enchantment that slowly reshapes the land
across the whole map.  AoWEPACK.dll only.  v1 2026-10-17 (plumbing + first shift), v2 2026-10-17 (terrain engine
rewrite), v3 2026-10-17 (rates, water encroachment, per-hex markers + glow, slow revert).

Spec (user): "Global Spell. Research 250, Cost 75, Upkeep 15. Slowly changes terrain across the map, spawning hills
and mountains, and digging/burying tunnels (increased in depths)."
v2 feedback: hills in every surface biome (matching variant, 1- and 2-hex), mountains on hills, 1 -> medium -> large
growth with a spawn buffer, long winding/straight 1-2 wide tunnels (more in the depths), burials; never on structures,
units (underground) or bridges.
v3 feedback: hills slightly more aggressive, mountains WAY more, underground a bit more (burying especially, not
impeded by vegetation; never ON units but around them is fine); hills/mountains never on water, but a GROWING mountain
may encroach onto water; a very subtle green glow on every changed hex; when the spell is removed the land slowly
reverts (large -> medium -> 1-hex -> hill -> original, 2-hex hills back, tunnels refilled, burials re-opened).

PLUMBING (zone A, unchanged since v1 except NT) = the Air Mastery clone recipe of patch_overgrowth_v1.py, CHAINED IN
FRONT of whatever owns each site at apply time (normally Overgrowth's caves; a vanilla site works too).  Every hook's
previous bytes are stored in a table at the head of zone A, so --revert puts back exactly what was there.
  CE  0x557F06E4 (TAirMastery.CreateEnchantment, jmp-hooked): 219 -> replay the create, MARKER [ench+0x14] := 219,
      spell name -> [ench+0x1C]; else jmp prev (or our own `ce_plain` replay on a vanilla site).
  MM  0x557F061C (sphere-mastery message call): 219 -> skipped; else jmp prev.
  AC / DE  VMT +0x68 @0x557EDE24 / +0x60 @0x557EDE1C: marker 219 -> base TGlobalEnchantment.Activate/Deactivate only.
  CHK VMT +0x64 @0x557EDE20: marker 219 -> base check + once-per-player; else jmp prev.
  NT  0x5577D293 (player NEW TURN msg 0x20020002, synced): prev first, then for the player whose turn starts: an
      ACTIVE Tectonic Shift of his -> SHIFT (engine eax = 0); NO active Tectonic Shift of ANY player -> REVERT (eax = 1)
      of this player's markers.  Runs before TTurnPlayerControl.NewTurn's InvalidateMap (= build_los_terrain.py's
      fog/LOS rebuild) -> dug / buried Earth walls are reflected in line of sight the same turn.

ENGINE RE (v3, verified in the binaries):
  * TMapField.Initialize 0x5560806C: terrain [f+0x14] / overlay [f+0x15] = the first child (top-down) answering VMT
    +0x4C / +0x58.  TMountainMO's +0x58 override 0x557A2DC8 answers overlay 0 for EVERY used slot (a medium's "hill
    foot" and "foothill" slots block too - v2 assumed some stayed passable, and its large growth could never pass its
    own medium's hexes); it answers its list terrain (TMapObject.GetTerrain), so a mountain slot over water reads the
    mountain's terrain and the water (the hexagon sprite's answer) comes back when the mountain is cleared.
  * A multi-hex MO also sits on its ART-ONLY slot hexes (terrain >= 0x80); TTerrainMO.MapFieldMsgProc 0x55616A6C
    ignores ClearTerrain there (subhex != 0), TMapObject's default 0x55609E30 frees road/bridge MOs on any clear.
  * TTerrainMO.ClearTerrain 0x556168F8 (VMT+0x128; eax MO, edx field, ecx subhex): single -> Free; multi -> a
    compatible single-hex resource is re-placed on every other used slot (2-hex hill -> 1-hex hill; medium -> m1s;
    a multi-hex decoration with no single variant simply vanishes from the neighbour too -> v3 never clears a hex
    that carries a multi-hex non-hill TTerrainMO).
  * TFrozenWaterHS (THexagonSprite: MapFieldMsgProc = ret, so ClearTerrain never touches it) = the markers Drought,
    Overgrowth, Ice Age and raise-terrain already use (+0xC countdown, +0xD owner, +0xE restore/flag, +0xF target;
    saved under tags 0x1E/0x1F/0x6E/0x6F by build_raiseterrain_matrix.py -> survive save/load, identical in MP).
    VMT+0xA0 (0x55764B6C + cave_tchg) runs after every field re-init: [+0xE] != 0 -> the marker frees itself unless
    the terrain == [+0xF].  The vanilla/Drought per-player tick (`cmp dl,[hs+0xD]`) never matches an owner byte with
    bit 0x40.  Flag namespace of [+0xE]: 0 vanilla ice, <= 0xD raise-terrain, 0x80|t Drought, 0x40|t Overgrowth,
    0xC0|t Ice Age -> TECTONIC = 0x20|code (bits 0xC0 clear, never a terrain, so nobody else ever acts on it).

TECTONIC MARKER (one per changed hex; created AFTER the change, fields set BEFORE PlaceHX):
  +0xC countdown (REV_BASE + Random(REV_RND) caster turns per revert stage; negative = failed-refill counter)
  +0xD 0x40 | caster        +0xE 0x20 | code        +0xF the hex's terrain (kept current; tchg frees it otherwise)
  code = what the hex WAS before Tectonic first touched it:
     0 bare  1 forest  2 vegetation  3 road (hill sat on the road)  4 map hill  5 map 1-hex mountain (key hex, grown)
     6 water (encroached by a growing mountain)  7 map medium mountain (key hex, grown)  8 dug (was EarthWall)
     9 buried (was Dirt).  A hex that already carries our marker keeps its code (= its true original).

SHIFT v3 (zone C; all state = synced map + map.Random 0x5577827C; frame on the stack):
 SURFACE (level 0): hill CAP = area*SURF_PM/1000 (|1) new hills per turn (96x96 -> 73), mountain events per turn <=
 CAP/M_CAP_DIV + 1 (74), PICKS = CAP*PICK_MULT random hexes.  A pick counts only on terrain 1 Grass / 2 Desert / 3 Snow
 / 4 Steppe / 5 Wasteland without a TStructure or a FOREIGN marker (ours are fine):
  * bare / forest / vegetation / road hex (overlay 0xFF/1/3/4), no mountain object on it, no bridge, no multi-hex
    decoration -> HILL of the hex's own terrain: 1 time in H2_ODDS a 2-HEX hill (second hex = NE or NW), else a 1-hex
    hill.  Covered hexes are ClearTerrain'd first except road hexes (the road stays, the hill sits on it).  Marked with
    their code (0..3).
  * hill (overlay 2), 1 time in M_ODDS -> 1-HEX MOUNTAIN: no army, no road/bridge, no mountain object on the hex and no
    BLOCKING mountain hex among its 6 neighbours (the spawn buffer: a new 1-hex mountain never touches another mountain), and passable connectivity
    kept (SIMPLE test below).  ClearTerrain first (a 2-hex hill leaves its other half as a 1-hex hill).  Marked 4 (map
    hill) unless already ours.
  * mountain carrying a TMountainMO: used slots 1 -> MEDIUM (anchor = S of the mountain M, G_ODDS); used slots 4 with
    the picked hex = slot 1 (N) of its anchor -> LARGE anchored on M (L_ODDS).  Every NEW real hex of the footprint
    (not M, not a hex where the old mountain itself stands = own MO there AND overlay 0 - art-only presence does not
    count) must be on the map with no structure / foreign marker / army / road / bridge / multi-hex decoration and no
    other mountain object ON it, and either (a) the mountain's terrain with overlay 0xFF/1/2/3 and pass the SIMPLE test
    one after the other (a virtual-blocked list of up to 8 holds the ones already accepted), or (b) bare WATER (terrain
    0, overlay 0xFF: no bridge, no ship) - the encroachment; water is not passable land, so it needs no SIMPLE test.
    Old-mountain hexes only need no structure / foreign marker.  Art-only hexes: no structure, no foreign marker, no
    other mountain object.  Then the old footprint + new real hexes are ClearTerrain'd (twice) and the new resource is
    placed at the anchor; new hexes are marked with their codes (water 6), M with 5 (from a map 1-hex) / 7 (from a map
    medium) unless already ours.
  Resources are picked like TAoWHSMap.PlaceTerrain does (RandSeed := map.Random(0xFFFFFF), map.Random(count) over the
  matches, resource VMT+0x68 CreateAndPlace) from our own filter over [[0x558FA044]+0x24]+8: ClassID 0x20167 (hills,
  trees, vegetation) or 0x20169 (TMountainMOR), decoration 0, list length <= 19, used-slot count + up to two (slot,
  overlay) shape checks, slot terrain = the wanted terrain.
 UNDERGROUND (level 1) / DEPTHS (level >= 2), per turn:
  * BURY worms (area*BURY_PM/10000 + 1): fill Dirt -> EarthWall; fillable = Dirt, any overlay but mountain (bare,
    rocks, rubble, vegetation are cleared away), no road/bridge, no multi-hex decoration, no structure / foreign marker /
    ARMY on the hex (units are never buried - burials still close in around them), SIMPLE.
  * DIG worms (area*WORM_PM/10000 + 1): EarthWall -> Dirt along straight or winding 1-2 wide corridors (longer, wider
    and more of them in the depths), never on the outer ring, blocked by Rock/Lava/water, no structure/army.
  The change = ClearTerrain + ChangeTerrain (map VMT+0xD0).  A hex carrying our marker that is changed back (dug again
  after a burial, buried again after a dig) is simply back to its original state -> the marker is destroyed; otherwise
  the new state gets a marker (8 dug / 9 buried).
 SIMPLE (every change that BLOCKS movement): the 6 neighbours in ring order; OPEN = on the map, terrain not 0/7/8/9/
  0xA, overlay != 0, not virtually blocked.  Accepted if the open neighbours form at most ONE contiguous run, or (v3)
  if they are all connected to each other through open hexes inside the 19-hex window around the hex (bitmask
  fixed-point flood over a precomputed window adjacency table ADJ19) -> never splits an open region, never cuts a
  unit / structure off.

REVERT v3 (same engine, eax = 1; the NT of a player while NO Tectonic Shift is active anywhere; walks every level
and field, acts on this player's markers only):
  * surface hex under a mountain: the mountain's key hex M (1-hex / large: its anchor, medium: N of its anchor) DRIVES
    the shrink (other footprint markers wait; if M has no marker the visiting one drives with code 4).  Key code 5 /
    7 = a map mountain we grew: it never shrinks below 1-hex / medium (the key marker goes once it is back).  After
    the countdown: large -> medium at S(M), medium -> 1-hex at M, 1-hex -> 1-hex hill at M; the old footprint is
    cleared, every hex leaving the footprint is restored from ITS marker (forest / vegetation re-planted, map hill
    re-placed, bare / road stay bare, water comes back by itself) and its marker destroyed.  The key marker stays for
    the next stage unless the original size is reached.  If no resource fits, it retries next turn.
  * our hill (overlay 2) with code 0..3: the hill MO alone is cleared (VMT+0x128 on its subhex - roads untouched; a
    2-hex hill leaves its other half, which reverts on its own marker), forest / vegetation re-planted.
  * underground code 9 (buried): re-opened.  Code 8 (dug): refilled when it passes the bury checks (no unit on it,
    SIMPLE); a refused refill retries every turn and is kept for good after MAXFAIL refusals in a row (a tunnel that
    now joins two caves would split them - "no passage is ever cut off" wins).
  * anything else (the hex was changed by something else since): the marker is just destroyed.
  -> removal / dispel / upkeep loss: the land settles back over the caster's following turns; a recast stops it.  An
  eliminated caster gets no more turns -> his changes stay (the Overgrowth / Drought caveat).
  Multiple casters: while ANY Tectonic Shift is active, nobody's changes revert (simple rule); markers of different
  casters never mix (a hex keeps the first marker).

GLOW (zone C): TFrozenWaterHS.Show (VMT 0x557147B4 +0xA8 = 0x55764BD0) site 0x55764C5B (10 B; patch_drought_glow_v1.py
made it `call drought_cave / 5 nops`) -> `call glow` in FRONT of the previous owner: our markers ([+0xE] & 0xE0 ==
0x20) -> pure frame pick of spell 219 gfx slot GLOW_SLOT every GLOW_PERIOD ticks (no shared sequence state; v3.1: 2 ticks
x 48 frames - the frame index = ([map+0x40] = THSMap.NewFrame counter, +1 per drawn frame) / PERIOD + hex phase), image
VMT+0x84 Draw at the marker's x/y + the sequence offsets, `ret 0x10`; anything else -> jmp to the previous owner
with every register as it came (or the vanilla `mov edx,0x46 / jmp ShowLoopedEx` on a vanilla site).  Visual only.

AI: the pipeline poke (0x34, 4, 0xFFFFFFFF) = priority -1 -> the AI never casts it.

Zones: A 0x55870000..0x55870800 (table + hook caves), B 0x55871000..0x55873000 (v2's engine; zeroed by v3),
C 0x55874C00..0x55878000 (header 'TECTSHv3' + the glow site's 10 original bytes, data, engine, glow; measured zero and
reloc free 10/17).  Dry-run default; --apply (fresh, or upgrades an applied v1/v2 in place keeping the stored
originals) / --revert (restores the six sites + the glow site, zeroes A, B and C) / --dis / --dll <path> (scratch copy,
no backup).  Backups <game>\\backup\\AoWEPACK.dll.bak_tectonic (fresh) / .bak_tectonic2 (v1 -> v2) / .bak_tectonic3
(state before the v3 upgrade).
!! Order: apply AFTER patch_overgrowth_v1.py and patch_drought_glow_v1.py; revert BEFORE re-running either (their
scripts see our hooks as OTHER and abort).  A later script that chains in front of our NT / glow site must be
reverted before this one is upgraded or reverted (LIFO); our --apply/--revert refuse while a site no longer points at
us.  patch_tectonic_shake_v1.py uses other sites (CE VMT slot 0x557EDF80, NewTurn 0x557569DA): independent.

V3.2 (2026-10-17, user: "I want mountains from Tectonic Rift to be able to spawn under units too" + "mountains spawned
by Tectonic Rift should be able to turn into volcanoes by Pyroclasm").  REQUIRES patch_terrain_armyhooks_v1.py (--apply
refuses without it; its --revert refuses while this is applied).
  * WHY hills / mountains never landed on armies before: TMountainMO.CanPlace and TTerrainMO.CanPlace (HSEPack, via
    VMT+0x120) refuse any slot whose top HS has show priority >= 10 - TArmyHS = 0x1A - and the map-level placement test
    (HSEPack 0x5560CD00) asks every child's CanChangeTerrain with the new overlay written (a mountain slot = overlay 0 ->
    TArmy.ValidTerrain refuses).  So v3.1's hill picks on army hexes silently failed (after the hex had been cleared).
  * v3.2: t_create sets PLACE_FLAG (0x5590B504) around every CreateAndPlace of ours -> the armyhooks caves let both tests
    pass for armies.  Afterwards t_valarm walks the 19-hex window of the anchor and, for every hex that is now BLOCKING
    (overlay 0) and carries an army, does exactly what TArmyHS.TerrainChanged does: BeginUpdate(army) /
    TArmy.ValidateTerrain(army, terrain, overlay) (0x5578CF70) / EndUpdate(army) -> the vanilla terrain validation:
    units that cannot stand on a mountain die through the vanilla event, flyers / mountaineers stay (CHOICE: kill, not
    displace - the engine has no army displacement; documented for the user).  Hills (overlay 2) never kill.
  * 1-hex mountain on a hill: army hexes allowed (t_guard2).  Growth footprint: LAND hexes allowed (t_guard2 in
    fp_common); WATER (encroach) hexes still refuse armies (no ship is ever buried).  Underground burials still never
    fill an army hex (unchanged).
  * Volcanoes (TMountainMOR list length > 19: the map's and Pyroclasm's) are never grown into regular mountains.
  * Pyroclasm v3 takes over a Tectonic mountain it converts: it destroys our markers on the converted footprint, so this
    engine (shift + revert) simply never sees those hexes again.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_tectonic"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55870000, 0x55870800            # zone A: original-bytes table + the hook caves (CE/MM/AC/DE/CHK/NT)
ZONE_B, ZONE_B_END = 0x55871000, 0x55873000        # zone B: v2's engine; v3 leaves it ZERO (kept in the checks so upgrades/reverts clean it)
ZONE_C, ZONE_C_END = 0x55874C00, 0x55878000        # zone C (v3): header (glow-site original bytes) + data + engine + glow cave
MAGIC = b"TECTSHv1"                                # zone A table format tag (unchanged since v1 so an applied v1/v2 upgrades in place)
MAGIC_C = b"TECTSHv3"                              # zone C header: MAGIC_C + the 10 original bytes of the glow site
SPELL_ID = 219
# ---- tuning (v3) ----
SURF_PM, PICK_MULT, MAX_LEVELS = 8, 24, 4          # surface: area*8/1000 (|1) new hills per turn (96x96 -> 73), picks = 24x that
H2_ODDS = 3                                        # a new hill is a 2-hex hill 1 time in 3 (when the second hex fits)
M_ODDS = 1                                         # a sampled hill always tries to become a 1-hex mountain (v2: 1 in 5)
# new 1-hex mountain: no mountain object on its hex and no BLOCKING mountain hex (overlay 0) among its 6 neighbours
# (v2: no mountain object at all within two rings - other mountains' art-only overhang refused 90 % of the hills)
G_ODDS, L_ODDS = 1, 1                              # a sampled 1-hex mountain grows to medium always / medium -> large always (v2: 1 in 2)
M_CAP_DIV = 1                                      # mountain events per turn <= hill cap / 1 + 1 (96x96 -> 74; v2: /3)
TRIES, WIND_ODDS, STRAIGHT_ODDS = 16, 2, 8         # worm start tries; turn chance per step 1/2 (winding) or 1/8 (straight)
# per depth index (0 = underground, 1 = depths and below): WORM_PM, LEN_BASE, LEN_RND, WIDE_NUM(/3), BURY_PM, BLEN_BASE, BLEN_RND
UG_PARAMS = ((5, 6, 9, 1, 6, 3, 6), (8, 9, 12, 2, 14, 4, 9))
REV_BASE, REV_RND = 2, 4                           # revert: each stage waits 2..5 of the caster's turns
MAXFAIL = 20                                       # a dug tunnel whose refill is refused 20 caster turns in a row (it now joins two open areas) is kept for good
GLOW_SLOT, GLOW_PERIOD = 3, 2                      # glow = spell 219 gfx slot 3; v3.1 2026-10-17: 2 ticks per frame (48-frame tectonic_glow2 loop; v3 = 4 ticks x 12 frames looked choppy)

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
RES_GLOBAL, RANDSEED_SLOT = 0x558FA044, 0x558FB720  # resource container (PlaceTerrain's list) / import slot -> System.RandSeed
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
AM_CHK_MSG, AM_CHK_SEH = 0x557F0306, 0x557F0374
AM_ENCH_CREATE, AM_ENCH_CELL = 0x557F0204, 0x557EDD7C
LSTRASG = 0x55701150
MAP_RANDOM = 0x5577827C
GETMAPLEVEL, LEVEL_GETFIELD = 0x557020EC, 0x557020DC
FIND_NT_HS, STRUCT_CLASSREF = 0x55702004, 0x55713BD8
FIND_HS, FW_CLASSREF = 0x55701FFC, 0x55714774
EO_CREATE, PLACEHX = 0x55703064, 0x557025F4         # TEObject.Create / THSMap.PlaceHX thunks (Drought / Overgrowth marker recipe)
CLEAR_TERRAIN, CHANGE_SLOT = 0x557025DC, 0xD0
MTN_MO_VMT = 0x557A266C                            # TMountainMO (ClassID 0x20168); its resources TMountainMOR = ClassID 0x20169
TMO_CID = 0x20166                                  # HSE Terrain.TTerrainMO.ClassID (hills, trees, decorations)
CLASSID_ARMY = 0x20217
CLASSID_ROAD, CLASSID_BRIDGE, CLASSID_HBRIDGE = 0x20164, 0x20174, 0x2087A
CLS_HILLRES, CLS_MTNRES = 0x20167, 0x20169
# v3.2 (2026-10-17): hills / mountains under armies - patch_terrain_armyhooks_v1.py's PLACE_FLAG (set around every
# CreateAndPlace of ours) lets CanPlace and CanChangeTerrain accept army hexes; afterwards every army on a now-blocking
# hex (overlay 0) of the 19-hex window is validated exactly like TArmyHS.TerrainChanged does it:
# BeginUpdate(army) / TArmy.ValidateTerrain(army, dl terrain, cl overlay) / EndUpdate(army) - units that cannot stand on
# the mountain die through the vanilla event, flyers / mountaineers stay.
PLACE_FLAG = 0x5590B504
ARMY_VALIDATE, BEGIN_UPDATE, END_UPDATE = 0x5578CF70, 0x55703284, 0x5570328C
# glow: TFrozenWaterHS.Show (VMT 0x557147B4 +0xA8 = 0x55764BD0) `mov edx,0x46 / call ShowLoopedEx` @0x55764C5B (10 B;
# patch_drought_glow_v1.py turned it into `call cave / 5 nops`)
GLOW_SITE, GLOW_VANILLA = 0x55764C5B, bytes.fromhex("ba46000000e8b7dcf9ff")
SHOWLOOPEDEX = 0x5570291C
GETSPELL, GETIMAGESEQ, IMAGEEXIST, LIBGET, AOWHSSET = 0x55779AC8, 0x557028E4, 0x55702944, 0x55702934, 0x558FA044
# CenterHNtoHX offsets (HSEngine 0x5560E17C, verified by emulation): slot 0 centre, 1..6 = N NE SE S SW NW, 7..18 = ring 2
HN_TAB = bytes.fromhex("000000ff01ff01000001ff00ffff00fe01fe02ff0200020101010002ff01fe01fe00fefffffe000000ff010001010001ff01ff0000fe01ff02ff0200020101020002ff02fe01fe00feffffff")
# t_simple's window check: for each of the 19 window slots (CenterHNtoHX numbering) its 6 neighbours' slots (0xFF = outside the window);
# the slot topology is the same for both column parities (verified when this table was generated)
ADJ19 = bytes.fromhex("01020304050607080200061208090a030001020a0b0c040000030c0d0e050600040e0f10120100051011ffff080112ffffff09020107ffffff0a020809ffff0b03020affffff0c03030bffff0d04040cffffff0e05040dffff0f10050effffff1106050fffffff120610ffffff07010611ff")
# resource picker descriptors: classid, used-slot count, (slot, overlay) A, (slot, overlay) B (0xFF = none), max list length
DESCS = (("d_h1", CLS_HILLRES, 1, 0, 2, 0xFF, 0), ("d_h2a", CLS_HILLRES, 2, 0, 2, 2, 2), ("d_h2b", CLS_HILLRES, 2, 0, 2, 6, 2),
         ("d_m1", CLS_MTNRES, 1, 0, 0, 0xFF, 0), ("d_m4", CLS_MTNRES, 4, 0, 2, 1, 0), ("d_m9", CLS_MTNRES, 9, 0, 0, 4, 2),
         ("d_f1", CLS_HILLRES, 1, 0, 1, 0xFF, 0), ("d_v1", CLS_HILLRES, 1, 0, 3, 0xFF, 0))   # v3: tree / vegetation re-planting on revert

CE_VANILLA = bytes.fromhex("33c9b201a1")
# name: (va, kind, our cave); jmp / call = 5-byte E9/E8 code hook, vmt = 4-byte VMT slot
SITES = {
    "CE":  (0x557F06E4, "jmp", "ce"),
    "MM":  (0x557F061C, "call", "mm"),
    "NT":  (0x5577D293, "call", "nt"),
    "AC":  (0x557EDE24, "vmt", "ac"),
    "DE":  (0x557EDE1C, "vmt", "de"),
    "CHK": (0x557EDE20, "vmt", "chk"),
}
ORDER = ["CE", "MM", "NT", "AC", "DE", "CHK"]
TABLE_LEN = 0x30                                   # MAGIC + 3x5 + 3x4 original bytes = 35 B

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


def pack_table(orig):
    t = bytearray(MAGIC)
    for nm in ORDER: t += orig[nm]
    return bytes(t) + bytes(TABLE_LEN - len(t))


def unpack_table(b):
    if b[:8] != MAGIC: return None
    out, p = {}, 8
    for nm in ORDER:
        n = 4 if SITES[nm][1] == "vmt" else 5
        out[nm] = bytes(b[p:p + n]); p += n
    return out


def prev_target(nm, orig):
    """Where our cave falls through to for everything that is not Tectonic Shift (None = our ce_plain replay)."""
    va, kind, _c = SITES[nm]
    if kind == "vmt": return struct.unpack("<I", orig)[0]
    if nm == "CE" and orig == CE_VANILLA: return None
    if orig[0] != (0xE9 if kind == "jmp" else 0xE8): raise ValueError("%s @%#x: unexpected bytes %s" % (nm, va, orig.hex()))
    return va + 5 + struct.unpack_from("<i", orig, 1)[0]



def build(orig, glow_orig):
    """-> (zone A bytes, zone C bytes, where).  Zone C is built first (the NT cave in zone A calls the engine)."""
    out, outc = bytearray(pack_table(orig)), bytearray(MAGIC_C + glow_orig); where = {}
    prev = {nm: prev_target(nm, orig[nm]) for nm in ORDER}
    def place(name, src, pic=False, zone="A"):
        buf, base = (out, ZONE) if zone == "A" else (outc, ZONE_C)
        while len(buf) % 16: buf.append(0)
        va = base + len(buf); where[name] = va
        s = src % dict(C, **where)
        buf.extend(asm_pic(s, va) if pic else bytes(ks.asm(s, va)[0]))
    def place_data(name, data):
        while len(outc) % 16: outc.append(0)
        where[name] = ZONE_C + len(outc); outc.extend(data)
    C = {"id": SPELL_ID, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT, "bdeact": BASE_DEACT, "bchk": BASE_CHK,
         "ammsg": AM_CHK_MSG, "amseh": AM_CHK_SEH, "amcreate": AM_ENCH_CREATE, "amcell": AM_ENCH_CELL, "lstrasg": LSTRASG,
         "rnd": MAP_RANDOM, "getlevel": GETMAPLEVEL, "getfield": LEVEL_GETFIELD, "findnt": FIND_NT_HS,
         "structref": STRUCT_CLASSREF, "findhs": FIND_HS, "fwcls": FW_CLASSREF, "clear": CLEAR_TERRAIN,
         "cslot": CHANGE_SLOT, "armyid": CLASSID_ARMY, "maxlev": MAX_LEVELS, "surfpm": SURF_PM, "pmult": PICK_MULT,
         "h2odds": H2_ODDS, "modds": M_ODDS, "godds": G_ODDS, "lodds": L_ODDS, "tries": TRIES, "wind": WIND_ODDS,
         "straight": STRAIGHT_ODDS, "resg": RES_GLOBAL, "randseed": RANDSEED_SLOT, "mtnvmt": MTN_MO_VMT,
         "mdiv": M_CAP_DIV, "roadid": CLASSID_ROAD, "bridgeid": CLASSID_BRIDGE, "hbridgeid": CLASSID_HBRIDGE,
         "eocreate": EO_CREATE, "placehx": PLACEHX, "tmocid": TMO_CID, "revbase": REV_BASE, "revrnd": REV_RND,
         "slx": SHOWLOOPEDEX, "getspell": GETSPELL, "getseq": GETIMAGESEQ, "exist": IMAGEEXIST, "libget": LIBGET,
         "hsset": AOWHSSET, "gslot": GLOW_SLOT, "gperiod": GLOW_PERIOD, "maxfail": MAXFAIL,
         "pflag": PLACE_FLAG, "validate": ARMY_VALIDATE, "beginupd": BEGIN_UPDATE, "endupd": END_UPDATE}
    place_data("hntab", HN_TAB)
    place_data("adj", ADJ19)
    for nm, cls, used, sa, oa, sb, ob in DESCS:
        place_data(nm, struct.pack("<IBBBBBBH", cls, used, sa, oa, sb, ob, 19, 0))
    place_data("prm", b"".join(struct.pack("<8I", *(p + (0,))) for p in UG_PARAMS))
    # ENGINE (zone C): eax = 0 -> SHIFT, eax != 0 -> REVERT; ebx = delta, edi = player.  Frame (ebp, 0x140):
    # -4 map, -8 level count, -0xC L, -0x10 cap/area, -0x14 picks left, -0x18 done, -0x1C x, -0x20 y, -0x24 terrain t,
    # -0x28 picked/old resource, -0x2C own mountain MO, -0x30/-0x34 anchor x/y, -0x38 virtual-blocked count, -0x4C/-0x50
    # worm x/y, -0x54 dir, -0x58 len, -0x5C turn odds, -0x60 wide side, -0x64 worms left, -0x68 tries, -0x6C depth index,
    # -0x70 2-hex hill slot, -0x74/-0x78 scratch hex x/y, -0x7C/-0x80 pick count/index, -0x84 slot k, -0x8C scratch
    # field, -0x90 slot (terrain | overlay<<8), -0x94 passes, -0x98 level params, -0x9C mountain events, -0xA0 mountain
    # cap, -0xA4 owner byte (0x40 | player), -0xA8/-0xAC hill codes, -0xB0/-0xB4 key hex M, -0xBC marker code, -0xC0
    # mountain size, -0xC4 temp, -0xC8 current marker, -0xCC current field, -0xD0 change marker, -0xD4 resource / MO,
    # -0xD8 subhex, -0x100..-0xE4 virtual-blocked list (y<<16|x) x8, -0x120..-0x10E per-slot codes (19 bytes).
    # esi = the current TMapLevel throughout.  Helpers are near-called with the same frame.
    place("engine", """
        test eax, eax
        jnz rev_entry
        push ebp
        mov ebp, esp
        sub esp, 0x140
        push esi
        push edi
        call t_enter
        test eax, eax
        jz s_out
    s_lev:
        call t_level
        test eax, eax
        js s_out
        jz s_nl
        xor eax, eax
        mov [ebp-0x18], eax
        mov [ebp-0x38], eax
        mov [ebp-0x2C], eax
        cmp dword ptr [ebp-0xC], 0
        jne s_under
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        imul eax, eax, %(surfpm)d
        xor edx, edx
        mov ecx, 1000
        div ecx
        or eax, 1
        mov [ebp-0x10], eax
        imul eax, eax, %(pmult)d
        mov [ebp-0x14], eax
        mov eax, [ebp-0x10]
        xor edx, edx
        mov ecx, %(mdiv)d
        div ecx
        inc eax
        mov [ebp-0xA0], eax
        xor eax, eax
        mov [ebp-0x9C], eax
    s_lp:
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
        jz s_nx
        call t_surf
    s_nx:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0x10]
        jb s_more
        mov eax, [ebp-0x9C]
        cmp eax, [ebp-0xA0]
        jae s_nl
    s_more:
        dec dword ptr [ebp-0x14]
        jnz s_lp
        jmp s_nl
    s_under:
        call t_ug
    s_nl:
        inc dword ptr [ebp-0xC]
        jmp s_lev
    s_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    rev_entry:
        push ebp
        mov ebp, esp
        sub esp, 0x140
        push esi
        push edi
        call t_enter
        test eax, eax
        jz r_out
    r_lev:
        call t_level
        test eax, eax
        js r_out
        jz r_nl
        xor eax, eax
        mov [ebp-0x20], eax
    r_y:
        mov eax, [ebp-0x20]
        cmp eax, [esi+0x10]
        jge r_nl
        xor eax, eax
        mov [ebp-0x1C], eax
    r_x:
        mov eax, [ebp-0x1C]
        cmp eax, [esi+0xc]
        jge r_ny
        mov edx, eax
        mov ecx, [ebp-0x20]
        call t_getf
        test eax, eax
        jz r_nx
        mov [ebp-0xCC], eax
        call t_ours
        test eax, eax
        jz r_nx
        mov dl, byte ptr [eax+0xd]
        cmp dl, byte ptr [ebp-0xA4]
        jne r_nx
        mov [ebp-0xC8], eax
        xor eax, eax
        mov [ebp-0x38], eax
        call r_hex
    r_nx:
        inc dword ptr [ebp-0x1C]
        jmp r_x
    r_ny:
        inc dword ptr [ebp-0x20]
        jmp r_y
    r_nl:
        inc dword ptr [ebp-0xC]
        jmp r_lev
    r_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    t_enter:
        mov eax, edi
        and eax, 0x3f
        or eax, 0x40
        mov [ebp-0xA4], eax
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        test eax, eax
        jz te_no
        mov eax, [eax+0x10]
        test eax, eax
        jz te_no
        mov eax, [eax+8]
        test eax, eax
        jz te_no
        mov ecx, [eax+8]
        cmp ecx, %(maxlev)d
        jle te_cnt
        mov ecx, %(maxlev)d
    te_cnt:
        mov [ebp-8], ecx
        xor eax, eax
        mov [ebp-0xC], eax
        inc eax
        ret
    te_no:
        xor eax, eax
        ret

    t_level:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-8]
        jge tl_end
        mov edx, eax
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        call %(getlevel)#x
        test eax, eax
        jz tl_skip
        mov esi, eax
        cmp dword ptr [esi+0xc], 3
        jl tl_skip
        cmp dword ptr [esi+0x10], 3
        jl tl_skip
        mov eax, 1
        ret
    tl_skip:
        xor eax, eax
        ret
    tl_end:
        or eax, -1
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
        and dl, 0xe0
        cmp dl, 0x20
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
        and dl, 0xe0
        cmp dl, 0x20
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

    t_hillmo:
        push esi
        push edi
        push ebp
        mov esi, eax
        movzx edi, byte ptr [esi+0xd]
    hm_lp:
        dec edi
        js hm_no
        mov eax, [esi+8]
        mov eax, [eax+edi*4]
        test eax, eax
        jz hm_lp
        mov ebp, eax
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, %(tmocid)#x
        jne hm_lp
        mov eax, [ebp+8]
        test eax, eax
        jz hm_lp
        cmp byte ptr [eax+0x44], 0
        jne hm_lp
        mov eax, [eax+0x28]
        test eax, eax
        jz hm_lp
        movzx edx, byte ptr [esi+0xc]
        shl edx, 2
        add edx, [esi+8]
        movzx ecx, byte ptr [edx+edi]
        cmp ecx, [eax+4]
        jae hm_lp
        mov edx, [eax+8]
        cmp byte ptr [edx+ecx*2+1], 2
        jne hm_lp
        mov eax, ebp
        jmp hm_out
    hm_no:
        xor eax, eax
        xor ecx, ecx
    hm_out:
        pop ebp
        pop edi
        pop esi
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

    t_nomtn:
        push edi
        push edx
        push ecx
        push eax
        mov edi, 1
    nm_l:
        mov edx, [esp+8]
        mov ecx, [esp+4]
        mov eax, edi
        call t_hn
        call t_getf
        test eax, eax
        jz nm_n
        call t_mtnof
        test eax, eax
        jnz nm_no
    nm_n:
        inc edi
        cmp edi, [esp]
        jb nm_l
        mov eax, 1
        jmp nm_out
    nm_no:
        xor eax, eax
    nm_out:
        pop ecx
        pop ecx
        pop edx
        pop edi
        ret

    t_noblk:
        push edi
        push edx
        push ecx
        mov edi, 1
    nb_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call t_hn
        call t_getf
        test eax, eax
        jz nb_n
        cmp byte ptr [eax+0x15], 0
        je nb_no
    nb_n:
        inc edi
        cmp edi, 7
        jb nb_l
        mov eax, 1
        jmp nb_out
    nb_no:
        xor eax, eax
    nb_out:
        pop ecx
        pop edx
        pop edi
        ret

    t_clear:
        push dword ptr [ebp-0xC]
        push 0
        push -1
        mov eax, [ebp-4]
        call %(clear)#x
        ret

    t_clearnr:
        push edx
        push ecx
        call t_roads
        pop ecx
        pop edx
        test al, 3
        jnz cn_x
        call t_clear
    cn_x:
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
        mov ecx, [esp]
        mov edx, [esp+4]
        mov eax, [esp+8]
        mov edi, [eax]
        push ecx
        push dword ptr [ebp-0xC]
        mov cl, dl
        mov edx, [ebp-4]
        mov dword ptr [ebx+%(pflag)#x], 1
        call dword ptr [edi+0x68]
        mov dword ptr [ebx+%(pflag)#x], 0
        mov [esp+8], eax
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_valarm
        pop ecx
        pop edx
        pop eax
        pop edi
        ret

    t_valarm:
        push edi
        push edx
        push ecx
        xor edi, edi
    vz_l:
        cmp edi, 19
        jae vz_x
        mov eax, edi
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_hn
        call t_getf
        test eax, eax
        jz vz_n
        cmp byte ptr [eax+0x15], 0
        jne vz_n
        push eax
        mov edx, %(armyid)d
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz vz_p
        mov ecx, [eax+0x1c]
        test ecx, ecx
        jz vz_p
        test byte ptr [ecx+0x10], 1
        jz vz_p
        push eax
        mov eax, ecx
        call %(beginupd)#x
        mov eax, [esp]
        mov eax, [eax+0x1c]
        mov edx, [esp+4]
        mov cl, byte ptr [edx+0x15]
        mov dl, byte ptr [edx+0x14]
        call %(validate)#x
        mov eax, [esp]
        mov eax, [eax+0x1c]
        call %(endupd)#x
        pop eax
    vz_p:
        pop eax
    vz_n:
        inc edi
        jmp vz_l
    vz_x:
        pop ecx
        pop edx
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

    t_ovcode:
        cmp byte ptr [eax+0x14], 0
        je oc_w
        mov al, byte ptr [eax+0x15]
        cmp al, 0xff
        je oc_0
        cmp al, 1
        je oc_1
        cmp al, 3
        je oc_2
        cmp al, 4
        je oc_3
        cmp al, 2
        je oc_4
        mov eax, 0xff
        ret
    oc_0:
        xor eax, eax
        ret
    oc_1:
        mov eax, 1
        ret
    oc_2:
        mov eax, 2
        ret
    oc_3:
        mov eax, 3
        ret
    oc_4:
        mov eax, 4
        ret
    oc_w:
        mov eax, 6
        ret

    t_cdset:
        push eax
        mov eax, [ebp-4]
        mov edx, %(revrnd)d
        call %(rnd)#x
        add eax, %(revbase)d
        pop edx
        mov byte ptr [edx+0xc], al
        ret

    t_mark:
        push esi
        push edi
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
        and dl, 0x1f
        or dl, 0x20
        mov byte ptr [eax+0xe], dl
        mov dl, byte ptr [ebp-0xA4]
        mov byte ptr [eax+0xd], dl
        mov dl, byte ptr [esi+0x14]
        mov byte ptr [eax+0xf], dl
        call t_cdset
        mov eax, [esp]
        movzx ecx, byte ptr [esi+0x11]
        push ecx
        movzx ecx, byte ptr [esi+0x12]
        push ecx
        movzx ecx, byte ptr [esi+0x10]
        mov edx, eax
        mov eax, [ebx+%(map)#x]
        call %(placehx)#x
        pop eax
    mk_have:
        mov dl, byte ptr [esi+0x14]
        mov byte ptr [eax+0xf], dl
        pop edi
        pop esi
        ret

    t_kill:
        mov dl, 1
        mov ecx, [eax]
        call dword ptr [ecx-4]
        ret

    t_h2ok:
        push edi
        mov edi, eax
        mov al, [edi+0x14]
        cmp al, byte ptr [ebp-0x24]
        jne h2_no
        mov al, [edi+0x15]
        cmp al, 0xff
        je h2_a
        cmp al, 1
        je h2_a
        cmp al, 3
        je h2_a
        cmp al, 4
        jne h2_no
    h2_a:
        mov eax, edi
        call t_guard2
        test eax, eax
        jz h2_no
        mov eax, edi
        call t_mtnof
        test eax, eax
        jnz h2_no
        mov eax, edi
        call t_roads
        test al, 2
        jnz h2_no
        mov eax, edi
        call t_multi
        test eax, eax
        jnz h2_no
        mov eax, 1
        pop edi
        ret
    h2_no:
        xor eax, eax
        pop edi
        ret

    t_surf:
        push edi
        mov edi, eax
        movzx eax, byte ptr [edi+0x14]
        cmp eax, 1
        jb sf_out
        cmp eax, 5
        ja sf_out
        mov [ebp-0x24], eax
        mov eax, edi
        call t_guard2
        test eax, eax
        jz sf_out
        xor eax, eax
        mov [ebp-0x2C], eax
        mov [ebp-0x38], eax
        mov al, [edi+0x15]
        test al, al
        je sf_mtn
        cmp al, 2
        je sf_h2m
        cmp al, 0xff
        je sf_hill
        cmp al, 1
        je sf_hill
        cmp al, 3
        je sf_hill
        cmp al, 4
        je sf_hill
        jmp sf_out

    sf_hill:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0x10]
        jae sf_out
        mov eax, edi
        call t_mtnof
        test eax, eax
        jnz sf_out
        mov eax, edi
        call t_roads
        test al, 2
        jnz sf_out
        mov eax, edi
        call t_multi
        test eax, eax
        jnz sf_out
        mov eax, edi
        call t_ovcode
        mov [ebp-0xA8], eax
        xor eax, eax
        mov [ebp-0x8C], eax
        mov eax, [ebp-4]
        mov edx, %(h2odds)d
        call %(rnd)#x
        test eax, eax
        jnz sf_h1
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        mov ecx, 2
        test eax, eax
        jz sf_s
        mov ecx, 6
    sf_s:
        mov [ebp-0x70], ecx
        mov eax, ecx
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_getf
        test eax, eax
        jz sf_h1
        mov [ebp-0x8C], eax
        call t_h2ok
        test eax, eax
        jz sf_h1z
        lea eax, [ebx+%(d_h2a)#x]
        cmp dword ptr [ebp-0x70], 2
        je sf_p2
        lea eax, [ebx+%(d_h2b)#x]
    sf_p2:
        call t_pick
        test eax, eax
        jz sf_h1z
        mov [ebp-0x28], eax
        mov eax, [ebp-0x8C]
        call t_ovcode
        mov [ebp-0xAC], eax
        mov eax, edi
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_clearnr
        mov eax, [ebp-0x8C]
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_clearnr
        jmp sf_put
    sf_h1z:
        xor eax, eax
        mov [ebp-0x8C], eax
    sf_h1:
        xor eax, eax
        mov [ebp-0x8C], eax
        lea eax, [ebx+%(d_h1)#x]
        call t_pick
        test eax, eax
        jz sf_out
        mov [ebp-0x28], eax
        mov eax, edi
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_clearnr
    sf_put:
        mov eax, [ebp-0x28]
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_create
        inc dword ptr [ebp-0x18]
        cmp byte ptr [edi+0x15], 2
        jne sf_p2m
        mov eax, edi
        mov edx, [ebp-0xA8]
        call t_mark
    sf_p2m:
        mov eax, [ebp-0x8C]
        test eax, eax
        jz sf_out
        cmp byte ptr [eax+0x15], 2
        jne sf_out
        mov edx, [ebp-0xAC]
        call t_mark
        jmp sf_out

    sf_h2m:
        mov eax, [ebp-0x9C]
        cmp eax, [ebp-0xA0]
        jae sf_out
        mov eax, [ebp-4]
        mov edx, %(modds)d
        call %(rnd)#x
        test eax, eax
        jnz sf_out
        mov eax, edi
        call t_guard2
        test eax, eax
        jz sf_out
        mov eax, edi
        call t_mtnof
        test eax, eax
        jnz sf_out
        mov eax, edi
        call t_roads
        test al, 3
        jnz sf_out
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_noblk
        test eax, eax
        jz sf_out
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_simple
        test eax, eax
        jz sf_out
        lea eax, [ebx+%(d_m1)#x]
        call t_pick
        test eax, eax
        jz sf_out
        mov [ebp-0x28], eax
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_clear
        mov eax, [ebp-0x28]
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_create
        cmp byte ptr [edi+0x15], 0
        jne sf_out
        inc dword ptr [ebp-0x9C]
        mov eax, edi
        mov edx, 4
        call t_mark
    sf_out:
        pop edi
        ret

    sf_mtn:
        mov eax, [ebp-0x9C]
        cmp eax, [ebp-0xA0]
        jae sf_out
        mov eax, edi
        call t_mtnof
        test eax, eax
        jz sf_out
        mov [ebp-0x2C], eax
        mov edx, [eax+8]
        test edx, edx
        jz sf_out
        mov edx, [edx+0x28]
        test edx, edx
        jz sf_out
        cmp dword ptr [edx+4], 19
        ja sf_out
        call t_size
        mov [ebp-0xC0], eax
        cmp eax, 1
        je sm_one
        cmp eax, 4
        jne sf_out
        mov eax, [ebp-0x2C]
        movzx edx, byte ptr [eax+0x10]
        movzx ecx, byte ptr [eax+0x11]
        mov eax, 1
        call t_hn
        mov [ebp-0x1C], edx
        mov [ebp-0x20], ecx
        call t_getf
        test eax, eax
        jz sf_out
        mov edi, eax
        cmp byte ptr [edi+0x15], 0
        jne sf_out
        mov eax, [ebp-4]
        mov edx, %(lodds)d
        call %(rnd)#x
        test eax, eax
        jnz sf_out
        mov eax, [ebp-0x1C]
        mov [ebp-0x30], eax
        mov eax, [ebp-0x20]
        mov [ebp-0x34], eax
        lea eax, [ebx+%(d_m9)#x]
        jmp sm_go
    sm_one:
        mov eax, [ebp-4]
        mov edx, %(godds)d
        call %(rnd)#x
        test eax, eax
        jnz sf_out
        mov eax, 4
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_hn
        mov [ebp-0x30], edx
        mov [ebp-0x34], ecx
        lea eax, [ebx+%(d_m4)#x]
    sm_go:
        call t_pick
        test eax, eax
        jz sf_out
        mov [ebp-0x28], eax
        call t_fpok
        test eax, eax
        jz sf_out
        call t_fpclear
        mov eax, [ebp-0x28]
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_create
        cmp byte ptr [edi+0x15], 0
        jne sf_out
        inc dword ptr [ebp-0x9C]
        call t_fpmark
        mov edx, 5
        cmp dword ptr [ebp-0xC0], 1
        je sm_mk
        mov edx, 7
    sm_mk:
        mov eax, edi
        call t_mark
        jmp sf_out

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

    t_fpok:
        push edi
        xor eax, eax
        mov [ebp-0x84], eax
    fp_l:
        mov edx, [ebp-0x28]
        mov edx, [edx+0x28]
        mov eax, [ebp-0x84]
        cmp eax, [edx+4]
        jge fp_yes
        cmp eax, 19
        jae fp_no
        mov byte ptr [ebp+eax-0x120], 0xfe
        mov edx, [edx+8]
        movzx ecx, word ptr [edx+eax*2]
        mov [ebp-0x90], ecx
        cmp cl, 0xfe
        je fp_n
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_getf
        mov edi, eax
        cmp byte ptr [ebp-0x90], 0x80
        jb fp_real
        test edi, edi
        jz fp_n
        mov eax, edi
        call t_guard2
        test eax, eax
        jz fp_no
        mov eax, edi
        call t_mtnof
        test eax, eax
        jnz fp_no
        jmp fp_n
    fp_real:
        test edi, edi
        jz fp_no
        mov eax, [ebp-0x74]
        cmp eax, [ebp-0x1C]
        jne fp_nk
        mov eax, [ebp-0x78]
        cmp eax, [ebp-0x20]
        je fp_n
    fp_nk:
        cmp byte ptr [edi+0x15], 0
        jne fp_nown
        mov eax, edi
        call t_hasown
        test eax, eax
        jz fp_nown
        mov eax, edi
        call t_guard2
        test eax, eax
        jz fp_no
        mov eax, edi
        call t_ours
        test eax, eax
        jz fp_n
        mov dl, byte ptr [eax+0xe]
        and edx, 0x1f
        cmp edx, 6
        jne fp_n
        mov eax, edx
        jmp fp_code
    fp_nown:
        mov al, [edi+0x14]
        test al, al
        jz fp_water
        cmp al, byte ptr [ebp-0x24]
        jne fp_no
        mov al, [edi+0x15]
        cmp al, 0xff
        je fp_ov
        cmp al, 1
        je fp_ov
        cmp al, 2
        je fp_ov
        cmp al, 3
        jne fp_no
    fp_ov:
        call fp_common
        test eax, eax
        jz fp_no
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_simple
        test eax, eax
        jz fp_no
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_vadd
        mov eax, edi
        call t_ovcode
        jmp fp_code
    fp_water:
        cmp byte ptr [edi+0x15], 0xff
        jne fp_no
        mov eax, edi
        call t_guard
        test eax, eax
        jz fp_no
        call fp_common
        test eax, eax
        jz fp_no
        mov eax, 6
    fp_code:
        mov ecx, [ebp-0x84]
        mov byte ptr [ebp+ecx-0x120], al
    fp_n:
        inc dword ptr [ebp-0x84]
        jmp fp_l
    fp_yes:
        mov eax, 1
        pop edi
        ret
    fp_no:
        xor eax, eax
        pop edi
        ret

    fp_common:
        mov eax, edi
        call t_guard2
        test eax, eax
        jz fc_cno
        mov eax, edi
        call t_mtnof
        test eax, eax
        jnz fc_cno
        mov eax, edi
        call t_roads
        test eax, eax
        jnz fc_cno
        mov eax, edi
        call t_multi
        test eax, eax
        jnz fc_cno
        mov eax, 1
        ret
    fc_cno:
        xor eax, eax
        ret

    t_fpmark:
        xor eax, eax
        mov [ebp-0x84], eax
    fm_l:
        mov eax, [ebp-0x84]
        cmp eax, 19
        jae fm_x
        mov edx, [ebp-0x28]
        mov edx, [edx+0x28]
        cmp eax, [edx+4]
        jge fm_x
        movzx ecx, byte ptr [ebp+eax-0x120]
        cmp ecx, 0x10
        jae fm_n
        mov [ebp-0xC4], ecx
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call t_getf
        test eax, eax
        jz fm_n
        mov edx, [ebp-0xC4]
        call t_mark
    fm_n:
        inc dword ptr [ebp-0x84]
        jmp fm_l
    fm_x:
        ret

    t_fpclear:
        mov dword ptr [ebp-0x94], 2
    fc_p:
        xor eax, eax
        mov [ebp-0x84], eax
    fc_l:
        mov edx, [ebp-0x28]
        mov edx, [edx+0x28]
        mov eax, [ebp-0x84]
        cmp eax, [edx+4]
        jge fc_np
        mov edx, [edx+8]
        cmp byte ptr [edx+eax*2], 0x80
        jae fc_n
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call t_clear
    fc_n:
        inc dword ptr [ebp-0x84]
        jmp fc_l
    fc_np:
        dec dword ptr [ebp-0x94]
        jnz fc_p
        ret

    t_change:
        push edi
        push esi
        push eax
        push edx
        push ecx
        push dword ptr [ebp-0xC]
        push 0
        push -1
        mov eax, [ebp-4]
        call %(clear)#x
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_getf
        test eax, eax
        jz tc_pop
        mov edi, eax
        call t_ours
        mov [ebp-0xD0], eax
        test eax, eax
        jz tc_go
        mov dl, byte ptr [esp+8]
        mov byte ptr [eax+0xf], dl
    tc_go:
        push dword ptr [esp]
        push dword ptr [ebp-0xC]
        push 0
        push dword ptr [esp+0x14]
        mov ecx, [esp+0x14]
        xor edx, edx
        mov eax, [ebp-4]
        mov esi, [eax]
        call dword ptr [esi+%(cslot)#x]
        movzx eax, byte ptr [edi+0x14]
        cmp eax, [esp+8]
        jne tc_fail
        inc dword ptr [ebp-0x18]
        mov eax, [ebp-0xD0]
        test eax, eax
        jz tc_new
        call t_kill
        jmp tc_pop
    tc_new:
        mov edx, 8
        cmp dword ptr [esp+8], 0xc
        je tc_nm
        mov edx, 9
    tc_nm:
        mov eax, edi
        call t_mark
        jmp tc_pop
    tc_fail:
        mov eax, [ebp-0xD0]
        test eax, eax
        jz tc_pop
        mov dl, byte ptr [edi+0x14]
        mov byte ptr [eax+0xf], dl
    tc_pop:
        pop ecx
        pop edx
        pop eax
        pop esi
        pop edi
        ret

    t_inner:
        xor eax, eax
        cmp edx, 1
        jl in_x
        cmp ecx, 1
        jl in_x
        push edx
        inc edx
        cmp edx, [esi+0xc]
        pop edx
        jge in_x
        push ecx
        inc ecx
        cmp ecx, [esi+0x10]
        pop ecx
        jge in_x
        inc eax
    in_x:
        ret

    t_step:
        push edx
        push ecx
        call t_inner
        test eax, eax
        jz st_blk
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_getf
        test eax, eax
        jz st_blk
        movzx edx, byte ptr [eax+0x14]
        cmp edx, 7
        je st_wall
        test edx, edx
        jz st_blk
        cmp edx, 8
        jb st_mv
        cmp edx, 0xa
        jbe st_blk
        jmp st_mv
    st_wall:
        call t_guard
        test eax, eax
        jz st_blk
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, 0xc
        call t_change
    st_mv:
        mov eax, 1
        jmp st_out
    st_blk:
        xor eax, eax
    st_out:
        pop ecx
        pop edx
        ret

    t_side:
        push edx
        push ecx
        call t_inner
        test eax, eax
        jz sd_x
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_getf
        test eax, eax
        jz sd_x
        cmp byte ptr [eax+0x14], 7
        jne sd_x
        call t_guard
        test eax, eax
        jz sd_x
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, 0xc
        call t_change
    sd_x:
        pop ecx
        pop edx
        ret

    t_fillok:
        push edx
        push ecx
        call t_getf
        test eax, eax
        jz fo_no
        cmp byte ptr [eax+0x14], 0xc
        jne fo_no
        cmp byte ptr [eax+0x15], 0
        je fo_no
        push eax
        call t_roads
        test eax, eax
        jnz fo_no2
        mov eax, [esp]
        call t_multi
        test eax, eax
    fo_no2:
        pop eax
        jnz fo_no
        call t_guard
        test eax, eax
        jz fo_no
        mov edx, [esp+4]
        mov ecx, [esp]
        call t_simple
        test eax, eax
        jz fo_no
        mov eax, 1
        jmp fo_out
    fo_no:
        xor eax, eax
    fo_out:
        pop ecx
        pop edx
        ret

    t_ug:
        xor eax, eax
        cmp dword ptr [ebp-0xC], 2
        setge al
        mov [ebp-0x6C], eax
        shl eax, 5
        lea eax, [ebx+eax+%(prm)#x]
        mov [ebp-0x98], eax
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        mov [ebp-0x10], eax
        mov ecx, [ebp-0x98]
        imul eax, dword ptr [ecx+16]
        xor edx, edx
        mov ecx, 10000
        div ecx
        inc eax
        mov [ebp-0x64], eax
    ug_b:
        call t_bworm
        dec dword ptr [ebp-0x64]
        jnz ug_b
        mov eax, [ebp-0x10]
        mov ecx, [ebp-0x98]
        imul eax, dword ptr [ecx]
        xor edx, edx
        mov ecx, 10000
        div ecx
        inc eax
        mov [ebp-0x64], eax
    ug_d:
        call t_dworm
        dec dword ptr [ebp-0x64]
        jnz ug_d
        ret

    t_dworm:
        mov dword ptr [ebp-0x68], %(tries)d
    dw_t:
        dec dword ptr [ebp-0x68]
        js dw_out
        mov eax, [ebp-4]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebp-0x4C], eax
        mov eax, [ebp-4]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebp-0x50], eax
        mov edx, [ebp-0x4C]
        mov ecx, eax
        call t_getf
        test eax, eax
        jz dw_t
        cmp byte ptr [eax+0x14], 0xc
        jne dw_t
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        mov [ebp-0x54], eax
        mov ecx, [ebp-0x98]
        mov edx, [ecx+8]
        mov eax, [ebp-4]
        call %(rnd)#x
        mov ecx, [ebp-0x98]
        add eax, [ecx+4]
        mov [ebp-0x58], eax
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        mov ecx, %(wind)d
        test eax, eax
        jz dw_w
        mov ecx, %(straight)d
    dw_w:
        mov [ebp-0x5C], ecx
        mov eax, [ebp-4]
        mov edx, 3
        call %(rnd)#x
        mov ecx, [ebp-0x98]
        xor edx, edx
        cmp eax, [ecx+12]
        jae dw_ws
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        mov edx, 1
        test eax, eax
        jz dw_ws
        mov edx, 5
    dw_ws:
        mov [ebp-0x60], edx
    dw_s:
        dec dword ptr [ebp-0x58]
        js dw_out
        mov eax, [ebp-4]
        mov edx, [ebp-0x5C]
        call %(rnd)#x
        test eax, eax
        jnz dw_nt
        mov eax, [ebp-4]
        mov edx, 2
        call %(rnd)#x
        lea eax, [eax*4+1]
        add eax, [ebp-0x54]
        xor edx, edx
        mov ecx, 6
        div ecx
        mov [ebp-0x54], edx
    dw_nt:
        mov dword ptr [ebp-0x68], 3
    dw_d:
        mov eax, [ebp-0x54]
        inc eax
        mov edx, [ebp-0x4C]
        mov ecx, [ebp-0x50]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_step
        test eax, eax
        jnz dw_mv
        dec dword ptr [ebp-0x68]
        js dw_out
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        mov [ebp-0x54], eax
        jmp dw_d
    dw_mv:
        mov eax, [ebp-0x74]
        mov [ebp-0x4C], eax
        mov eax, [ebp-0x78]
        mov [ebp-0x50], eax
        mov eax, [ebp-0x60]
        test eax, eax
        jz dw_s
        add eax, [ebp-0x54]
        xor edx, edx
        mov ecx, 6
        div ecx
        lea eax, [edx+1]
        mov edx, [ebp-0x4C]
        mov ecx, [ebp-0x50]
        call t_hn
        call t_side
        jmp dw_s
    dw_out:
        ret

    t_bworm:
        mov dword ptr [ebp-0x68], %(tries)d
    bw_t:
        dec dword ptr [ebp-0x68]
        js bw_out
        mov eax, [ebp-4]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebp-0x4C], eax
        mov eax, [ebp-4]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebp-0x50], eax
        mov edx, [ebp-0x4C]
        mov ecx, eax
        call t_fillok
        test eax, eax
        jz bw_t
        mov ecx, [ebp-0x98]
        mov edx, [ecx+24]
        mov eax, [ebp-4]
        call %(rnd)#x
        mov ecx, [ebp-0x98]
        add eax, [ecx+20]
        mov [ebp-0x58], eax
    bw_f:
        mov edx, [ebp-0x4C]
        mov ecx, [ebp-0x50]
        mov eax, 7
        call t_change
        dec dword ptr [ebp-0x58]
        jle bw_out
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        mov [ebp-0x54], eax
        mov dword ptr [ebp-0x68], 6
    bw_n:
        mov eax, [ebp-0x54]
        inc eax
        mov edx, [ebp-0x4C]
        mov ecx, [ebp-0x50]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
        call t_fillok
        test eax, eax
        jnz bw_go
        mov eax, [ebp-0x54]
        inc eax
        cmp eax, 6
        jb bw_r
        xor eax, eax
    bw_r:
        mov [ebp-0x54], eax
        dec dword ptr [ebp-0x68]
        jnz bw_n
        jmp bw_out
    bw_go:
        mov eax, [ebp-0x74]
        mov [ebp-0x4C], eax
        mov eax, [ebp-0x78]
        mov [ebp-0x50], eax
        jmp bw_f
    bw_out:
        ret

    r_cd:
        mov eax, [ebp-0xC8]
        dec byte ptr [eax+0xc]
        cmp byte ptr [eax+0xc], 0
        jg rc_no
        mov eax, 1
        ret
    rc_no:
        xor eax, eax
        ret

    r_hex:
        mov eax, [ebp-0xC8]
        movzx edx, byte ptr [eax+0xe]
        and edx, 0x1f
        mov [ebp-0xBC], edx
        cmp dword ptr [ebp-0xC], 0
        jne rh_ug
        cmp edx, 8
        jae rh_kill
        xor eax, eax
        mov [ebp-0x2C], eax
        mov eax, [ebp-0xCC]
        call t_mtnof
        test eax, eax
        jnz rh_mtn
        mov eax, [ebp-0xCC]
        cmp byte ptr [eax+0x15], 2
        jne rh_kill
        cmp dword ptr [ebp-0xBC], 3
        ja rh_kill
        call r_cd
        test eax, eax
        jz rh_x
        mov eax, [ebp-0xCC]
        call t_hillmo
        test eax, eax
        jz rh_kill
        mov [ebp-0xD4], eax
        mov [ebp-0xD8], ecx
        mov eax, [ebp-0xC8]
        call t_kill
        push esi
        mov ecx, [ebp-0xD8]
        mov edx, [ebp-0xCC]
        mov eax, [ebp-0xD4]
        mov esi, [eax]
        call dword ptr [esi+0x128]
        pop esi
        mov eax, [ebp-0xCC]
        mov edx, [ebp-0xBC]
        call r_restore
        ret
    rh_kill:
        mov eax, [ebp-0xC8]
        call t_kill
    rh_x:
        ret

    rh_ug:
        cmp edx, 8
        je rh_dug
        cmp edx, 9
        jne rh_kill
        mov eax, [ebp-0xCC]
        cmp byte ptr [eax+0x14], 7
        jne rh_kill
        call r_cd
        test eax, eax
        jz rh_x
        mov eax, 0xc
        jmp rh_chg
    rh_dug:
        mov eax, [ebp-0xCC]
        cmp byte ptr [eax+0x14], 0xc
        jne rh_kill
        call r_cd
        test eax, eax
        jz rh_x
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_fillok
        test eax, eax
        jnz rh_fill
        mov eax, [ebp-0xC8]
        movsx edx, byte ptr [eax+0xc]
        xor ecx, ecx
        cmp edx, -1
        jge rd_f0
        lea ecx, [edx+2]
        neg ecx
    rd_f0:
        inc ecx
        cmp ecx, %(maxfail)d
        jae rh_kill
        inc ecx
        neg ecx
        mov byte ptr [eax+0xc], cl
        ret
    rh_fill:
        mov eax, 7
    rh_chg:
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call t_change
        ret

    rh_mtn:
        mov [ebp-0x2C], eax
        call t_size
        mov [ebp-0xC0], eax
        mov eax, [ebp-0x2C]
        movzx edx, byte ptr [eax+0x10]
        movzx ecx, byte ptr [eax+0x11]
        mov [ebp-0x30], edx
        mov [ebp-0x34], ecx
        mov eax, [ebp-0xC0]
        cmp eax, 1
        je rm_key
        cmp eax, 9
        je rm_key
        cmp eax, 4
        jne rh_kill
        mov eax, 1
        call t_hn
    rm_key:
        mov [ebp-0xB0], edx
        mov [ebp-0xB4], ecx
        cmp edx, [ebp-0x1C]
        jne rm_nk
        cmp ecx, [ebp-0x20]
        jne rm_nk
        jmp rm_drv
    rm_nk:
        call t_getf
        test eax, eax
        jz rm_m4
        call t_ours
        test eax, eax
        jnz rh_x
    rm_m4:
        mov dword ptr [ebp-0xBC], 4
    rm_drv:
        mov eax, [ebp-0xBC]
        call r_min
        cmp [ebp-0xC0], eax
        jg rm_go
        mov eax, [ebp-0xB0]
        cmp eax, [ebp-0x1C]
        jne rh_x
        mov eax, [ebp-0xB4]
        cmp eax, [ebp-0x20]
        jne rh_x
        jmp rh_kill
    rm_go:
        call r_cd
        test eax, eax
        jz rh_x
        call r_shrink
        ret

    r_min:
        cmp eax, 5
        je mn_1
        cmp eax, 7
        je mn_4
        cmp eax, 4
        je mn_0
        or eax, -1
        ret
    mn_1:
        mov eax, 1
        ret
    mn_4:
        mov eax, 4
        ret
    mn_0:
        xor eax, eax
        ret

    r_shrink:
        mov edx, [ebp-0xB0]
        mov ecx, [ebp-0xB4]
        call t_getf
        test eax, eax
        jz rs_retry
        mov [ebp-0x8C], eax
        movzx eax, byte ptr [eax+0x14]
        mov [ebp-0x24], eax
        mov eax, [ebp-0xC0]
        lea edx, [ebx+%(d_h1)#x]
        cmp eax, 1
        je rs_pk
        lea edx, [ebx+%(d_m1)#x]
        cmp eax, 4
        je rs_pk
        lea edx, [ebx+%(d_m4)#x]
    rs_pk:
        mov eax, edx
        call t_pick
        test eax, eax
        jz rs_retry
        mov [ebp-0xD4], eax
        mov eax, [ebp-0xB0]
        mov [ebp-0x74], eax
        mov eax, [ebp-0xB4]
        mov [ebp-0x78], eax
        cmp dword ptr [ebp-0xC0], 9
        jne rs_a
        mov eax, 4
        mov edx, [ebp-0xB0]
        mov ecx, [ebp-0xB4]
        call t_hn
        mov [ebp-0x74], edx
        mov [ebp-0x78], ecx
    rs_a:
        mov eax, [ebp-0x2C]
        mov eax, [eax+8]
        mov [ebp-0x28], eax
        xor eax, eax
        mov [ebp-0x84], eax
    rs_l:
        mov eax, [ebp-0x84]
        cmp eax, 19
        jae rs_cl
        mov edx, [ebp-0x28]
        mov edx, [edx+0x28]
        cmp eax, [edx+4]
        jge rs_cl
        mov byte ptr [ebp+eax-0x120], 0xfe
        mov edx, [edx+8]
        cmp byte ptr [edx+eax*2], 0x80
        jae rs_n
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call r_keep
        test eax, eax
        jz rs_rm
        call t_getf
        test eax, eax
        jz rs_n
        call t_ours
        test eax, eax
        jz rs_n
        mov dl, byte ptr [eax+0xe]
        and edx, 0x1f
        cmp edx, 6
        jne rs_n
        mov ecx, [ebp-0x84]
        mov byte ptr [ebp+ecx-0x120], 0x16
        jmp rs_n
    rs_rm:
        call t_getf
        test eax, eax
        jz rs_n
        call t_ours
        mov ecx, [ebp-0x84]
        test eax, eax
        jz rs_none
        movzx edx, byte ptr [eax+0xe]
        and edx, 0x1f
        mov byte ptr [ebp+ecx-0x120], dl
        call t_kill
        jmp rs_n
    rs_none:
        mov byte ptr [ebp+ecx-0x120], 0xfd
    rs_n:
        inc dword ptr [ebp-0x84]
        jmp rs_l
    rs_cl:
        call t_fpclear
        xor eax, eax
        mov [ebp-0x84], eax
    rs_rl:
        mov eax, [ebp-0x84]
        cmp eax, 19
        jae rs_put
        mov edx, [ebp-0x28]
        mov edx, [edx+0x28]
        cmp eax, [edx+4]
        jge rs_put
        movzx ecx, byte ptr [ebp+eax-0x120]
        cmp ecx, 0x10
        jae rs_rn
        mov [ebp-0xC4], ecx
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call t_getf
        test eax, eax
        jz rs_rn
        mov edx, [ebp-0xC4]
        call r_restore
    rs_rn:
        inc dword ptr [ebp-0x84]
        jmp rs_rl
    rs_put:
        mov eax, [ebp-0x8C]
        movzx eax, byte ptr [eax+0x14]
        mov [ebp-0x24], eax
        mov eax, [ebp-0xD4]
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        call t_create
        xor eax, eax
        mov [ebp-0x84], eax
    rs_wl:
        mov eax, [ebp-0x84]
        cmp eax, 19
        jae rs_wx
        mov edx, [ebp-0x28]
        mov edx, [edx+0x28]
        cmp eax, [edx+4]
        jge rs_wx
        cmp byte ptr [ebp+eax-0x120], 0x16
        jne rs_wn
        mov edx, [ebp-0x30]
        mov ecx, [ebp-0x34]
        call t_hn
        call t_getf
        test eax, eax
        jz rs_wn
        cmp byte ptr [eax+0x15], 0
        jne rs_wn
        mov edx, 6
        call t_mark
    rs_wn:
        inc dword ptr [ebp-0x84]
        jmp rs_wl
    rs_wx:
        mov eax, [ebp-0x8C]
        call t_ours
        test eax, eax
        jz rs_drv
        mov [ebp-0xC8], eax
        movzx eax, byte ptr [eax+0xe]
        and eax, 0x1f
        call r_min
        mov ecx, [ebp-0xC0]
        xor edx, edx
        cmp ecx, 1
        je rs_ns
        mov edx, 1
        cmp ecx, 4
        je rs_ns
        mov edx, 4
    rs_ns:
        cmp edx, eax
        jg rs_keepm
        mov eax, [ebp-0xC8]
        call t_kill
        jmp rs_drv
    rs_keepm:
        mov eax, [ebp-0xC8]
        call t_cdset
    rs_drv:
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        cmp edx, [ebp-0xB0]
        jne rs_d2
        cmp ecx, [ebp-0xB4]
        je rs_x
    rs_d2:
        call t_getf
        test eax, eax
        jz rs_x
        call t_ours
        test eax, eax
        jz rs_x
        call t_cdset
    rs_x:
        ret
    rs_retry:
        mov eax, [ebp-0xC8]
        mov byte ptr [eax+0xc], 1
        ret

    r_keep:
        push edx
        push ecx
        cmp edx, [ebp-0xB0]
        jne rk_1
        cmp ecx, [ebp-0xB4]
        je rk_yes
    rk_1:
        cmp dword ptr [ebp-0xC0], 9
        jne rk_no
        cmp edx, [ebp-0x74]
        jne rk_2
        cmp ecx, [ebp-0x78]
        je rk_yes
    rk_2:
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        mov eax, 2
        call t_hn
        cmp edx, [esp+4]
        jne rk_3
        cmp ecx, [esp]
        je rk_yes
    rk_3:
        mov edx, [ebp-0x74]
        mov ecx, [ebp-0x78]
        mov eax, 6
        call t_hn
        cmp edx, [esp+4]
        jne rk_no
        cmp ecx, [esp]
        je rk_yes
    rk_no:
        xor eax, eax
        jmp rk_out
    rk_yes:
        mov eax, 1
    rk_out:
        pop ecx
        pop edx
        ret

    r_restore:
        push edi
        mov edi, eax
        movzx eax, byte ptr [edi+0x14]
        mov [ebp-0x24], eax
        lea eax, [ebx+%(d_f1)#x]
        cmp edx, 1
        je rr_pk
        lea eax, [ebx+%(d_v1)#x]
        cmp edx, 2
        je rr_pk
        lea eax, [ebx+%(d_h1)#x]
        cmp edx, 4
        jne rr_x
    rr_pk:
        cmp byte ptr [edi+0x15], 0xff
        jne rr_x
        call t_pick
        test eax, eax
        jz rr_x
        movzx edx, byte ptr [edi+0x10]
        movzx ecx, byte ptr [edi+0x11]
        call t_create
    rr_x:
        pop edi
        ret
    """, zone="C")
    # GLOW (zone C): called from the TFrozenWaterHS.Show site (ebx = marker, eax = list, ecx = x; stack: ret, surface,
    # phase, tick, y).  Our markers ([+0xE] & 0xE0 == 0x20) -> pure frame pick of spell 219 gfx slot GLOW_SLOT (no shared
    # sequence state), `ret 0x10`.  Anything else -> the previous owner (Drought's glow cave) with every register as it
    # came, or the vanilla `mov edx,0x46 / jmp ShowLoopedEx` when the site was vanilla.
    if glow_orig[0] == 0xE8:
        gprev = "jmp %#x" % (GLOW_SITE + 5 + struct.unpack_from("<i", glow_orig, 1)[0])
    elif glow_orig[:5] == GLOW_VANILLA[:5] and glow_orig[5] == 0xE8:
        gprev = "mov edx, 0x46\n        jmp %#x" % (GLOW_SITE + 10 + struct.unpack_from("<i", glow_orig, 6)[0])
    else:
        raise ValueError("glow site %#x: unexpected bytes %s" % (GLOW_SITE, glow_orig.hex()))
    place("glow", """
        mov dl, byte ptr [ebx+0xe]
        and dl, 0xe0
        cmp dl, 0x20
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
    """, pic=True, zone="C")
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
    # oga: dl = player index (0x80 = any), ecx = spell id -> al = 1 if an ACTIVE enchantment of that spell exists;
    # all other regs preserved (Overgrowth's oga, own copy so neither zone depends on the other's layout)
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
    # CE (jmp'ed to; eax = spell)
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
    # MM (called; edi = spell)
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
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast)
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
    # NT (called; eax = pmc): the previous owner first; then for the player whose turn starts: an ACTIVE Tectonic Shift
    # of his -> SHIFT; no active Tectonic Shift of ANY player -> REVERT (this player's markers step back one stage)
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
        jz nt_none
        xor eax, eax
        call %(engine)#x
        jmp nt_out
    nt_none:
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
    return bytes(out), bytes(outc), where


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
    """10 bytes at the glow site: `call glow` + the original tail (Drought's 5 nops) or 5 nops (vanilla site)."""
    tail = glow_orig[5:10] if glow_orig[0] == 0xE8 else b"\x90" * 5
    return b"\xe8" + struct.pack("<i", where["glow"] - (GLOW_SITE + 5)) + tail


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=None, help="patch this file instead of the live AoWEPACK.dll (scratch testing)")
    a = ap.parse_args()
    dll = a.dll or game_file("AoWEPACK.dll")
    d = bytearray(open(dll, "rb").read())
    print("target:", dll)
    assert vaoff(ZONE_C_END) <= len(d), "zone C past the end of the file"
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or ZONE_B <= r < ZONE_B_END or ZONE_C <= r < ZONE_C_END
           or GLOW_SITE <= r < GLOW_SITE + 10
           or any(SITES[nm][1] != "vmt" and SITES[nm][0] <= r < SITES[nm][0] + 5 for nm in ORDER)]
    noreloc = [nm for nm in ORDER if SITES[nm][1] == "vmt" and SITES[nm][0] not in rl]
    if bad or noreloc: print("ABORT: relocs in zone/code sites %s | VMT slots without reloc %s" % (bad, noreloc)); return 1
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)]); zb = bytes(d[vaoff(ZONE_B):vaoff(ZONE_B_END)])
    zc = bytes(d[vaoff(ZONE_C):vaoff(ZONE_C_END)])
    live = {}
    for nm in ORDER:
        o, n = site_off(d, nm); live[nm] = bytes(d[o:o + n])
    live_glow = bytes(d[vaoff(GLOW_SITE):vaoff(GLOW_SITE) + 10])
    stored = unpack_table(zl)
    if stored is None and any(zl):
        print("ABORT: zone A %#x..%#x is not free" % (ZONE, ZONE_END)); return 1
    if stored is None and (any(zb) or any(zc)):
        print("ABORT: zone B/C not free (B %s, C %s)" % (any(zb), any(zc))); return 1
    cstored = zc[8:18] if zc[:8] == MAGIC_C else None
    if cstored is None and any(zc):
        print("ABORT: zone C %#x..%#x is not free" % (ZONE_C, ZONE_C_END)); return 1
    orig = stored if stored is not None else live
    glow_orig = cstored if cstored is not None else live_glow
    try:
        code, codec, where = build(orig, glow_orig)
    except ValueError as e:
        print("ABORT:", e); return 1
    assert ZONE + len(code) <= ZONE_END and ZONE_C + len(codec) <= ZONE_C_END, "zone overflow"
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
    if cstored is None: gstate = "free"
    elif live_glow == want_glow: gstate = "ours"
    elif live_glow[0] == 0xE8 and ZONE_C <= GLOW_SITE + 5 + struct.unpack_from("<i", live_glow, 1)[0] < ZONE_C_END: gstate = "ours(old)"
    else: gstate = "OTHER"
    if stored is None: zstate = "zero"
    elif (zl[:len(code)] == code and not any(zl[len(code):]) and not any(zb)
          and zc[:len(codec)] == codec and not any(zc[len(codec):])): zstate = "ours"
    elif cstored is None: zstate = "ours(old: v1)" if not any(zb) else "ours(old: v2)"
    else: zstate = "ours(old)"
    print("zone %s (A %d B of %d, C %d B of %d; B %s) | sites %s | glow %s (prev %s)" % (
        zstate, len(code), ZONE_END - ZONE, len(codec), ZONE_C_END - ZONE_C, "zero" if not any(zb) else "v2 engine",
        state, gstate, glow_orig.hex()))
    print("chained to: " + ", ".join("%s->%s" % (nm, "ce_plain" if prev_target(nm, orig[nm]) is None else "%#x" % prev_target(nm, orig[nm])) for nm in ORDER))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        inv = {v: k for k, v in where.items()}
        for buf, st, base in ((code, where["ce_plain"], ZONE), (codec, where["engine"], ZONE_C)):
            for i in md.disasm(buf[st - base:], st):
                if i.address in inv: print("  -- %s" % inv[i.address])
                print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if stored is None: print("already vanilla (zone free)"); return 0
        if any(s == "OTHER" for s in state.values()) or gstate == "OTHER":
            print("ABORT: a site no longer points at us (something chained in front - revert that first): %s glow %s" % (state, gstate)); return 1
        for nm in ORDER:
            o, n = site_off(d, nm); d[o:o + n] = stored[nm]
        if cstored is not None: d[vaoff(GLOW_SITE):vaoff(GLOW_SITE) + 10] = cstored
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        d[vaoff(ZONE_B):vaoff(ZONE_B_END)] = bytes(ZONE_B_END - ZONE_B)
        d[vaoff(ZONE_C):vaoff(ZONE_C_END)] = bytes(ZONE_C_END - ZONE_C)
        with open(dll, "r+b") as f: f.write(bytes(d))
        print("reverted (sites restored: %s; glow %s; zones A+B+C zeroed)" % (
            ", ".join("%s=%s" % (nm, stored[nm].hex()) for nm in ORDER), cstored.hex() if cstored is not None else "untouched")); return 0
    if zstate == "ours" and all(s == "ours" for s in state.values()) and gstate == "ours":
        print("already applied (v3.2)"); return 0
    if stored is not None and (any(s == "OTHER" for s in state.values()) or gstate == "OTHER"):
        print("ABORT: zone is ours but a site was taken over by someone else (revert that patch first, LIFO): %s glow %s" % (state, gstate)); return 1
    new = bytearray(d)
    new[vaoff(ZONE):vaoff(ZONE_END)] = code + bytes(ZONE_END - ZONE - len(code))
    new[vaoff(ZONE_B):vaoff(ZONE_B_END)] = bytes(ZONE_B_END - ZONE_B)
    new[vaoff(ZONE_C):vaoff(ZONE_C_END)] = codec + bytes(ZONE_C_END - ZONE_C - len(codec))
    for nm in ORDER:
        o, n = site_off(new, nm); new[o:o + n] = want[nm]
    new[vaoff(GLOW_SITE):vaoff(GLOW_SITE) + 10] = want_glow
    print("%d bytes change%s" % (sum(1 for x, y in zip(d, new) if x != y), " (in-place upgrade %s -> v3.2)" % zstate if zstate.startswith("ours(old") else ""))
    import patch_terrain_armyhooks_v1 as AH
    if not AH.applied(bytes(d)):
        print("ABORT: patch_terrain_armyhooks_v1.py is not applied - v3.2 places hills / mountains over armies only through its hooks (apply it first)"); return 1
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll is None:
        suffix = BAK_SUFFIX if stored is None else BAK_SUFFIX + ("3" if zstate in ("ours(old: v1)", "ours(old: v2)") else "32")   # v3.2: a v3.x -> v3.2 upgrade backs up the v3.1 state
        bak = bak_path(dll, suffix)
        if not os.path.exists(bak): shutil.copy2(dll, bak); print("backup ->", bak)
    with open(dll, "r+b") as f: f.write(bytes(new))
    assert open(dll, "rb").read() == bytes(new); print("AoWEPACK: written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
