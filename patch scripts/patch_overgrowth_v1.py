"""
OVERGROWTH (spell 383, Earth/Water sphere pair 19, tier 4) - a GLOBAL enchantment that slowly grows dense forest over
the map (2026-10-15).  AoWEPACK.dll only.

Spec (user): global spell, research 250, cost 75, upkeep 8, "slowly causes dense vegetation to grow over the map".

DONOR = Air Mastery (TAirMastery: spell class cell 0x557EDEA0, Create 0x557F0458 (id 0x3C = 60, Spells.pfs key 70),
registered @0x557F3A5B in the global-spell loop).  Water (Drought 391), Fire (Steam Power 406) and Earth (Golden Age
302) Mastery are taken; Life/Death/Air are free.  Recipe = patch_goldenage_v1.py:
  CE  TAirMastery.CreateEnchantment 0x557F06E4 (spell VMT+0xA0; `xor ecx,ecx / mov dl,1 / mov eax,[0x557EDD7C] /
      call TAirMasteryEnchantment.Create 0x557F0204 / ret`): `jmp cave` (5 B; the reloc'd cell operand behind it
      becomes dead code).  The cave replays it (cell read PIC) and for [spell+0x10] == 383 writes the MARKER
      [ench+0x14] := 383 (serialised -> survives saves) and copies the spell name [spell+8] into [ench+0x1C].
  AC/DE  TAirMasteryEnchantment VMT 0x557EDDBC +0x68 Activate 0x557F0384 / +0x60 Deactivate 0x557F03EC (mastery
      counter 0x5577E220/0x5577E228, the player's magic flag 4 [pmc+0x44], visibility refresh 0x5577C828) -> slots
      re-pointed: marker 383 -> the BASE TGlobalEnchantment.Activate 0x5577DBA0 / Deactivate 0x5577DC3C only.
  CHK +0x64 0x557F02AC ("already active": base check 0x5577DAE8, then pmc flag 4; message branch 0x557F0306):
      marker 383 -> base check, then our once-per-player test (an ACTIVE 383 cast by this player); refused through
      Air Mastery's own message branch after replaying its prologue (frame -0x18, SEH handler 0x557F0374 read PIC).
      Air Mastery's flag is NOT consulted (Air Mastery and Overgrowth don't block each other).
  MM  TAirMastery.ExecuteTE 0x557F05F8 (eax = edi = the spell): `call 0x557EF7C0` @0x557F061C = the sphere mastery
      message (dl = 4) -> skipped for spell 383.
  Kept from the donor: the event-log line (0x55775D5C) and the map-wide cast animation (callback 0x557F050C): it
  draws Random(3) = gfx slots 0..2 of the SPELL'S OWN image list [spell+0x2C] -> Overgrowth's record provides them.

PER TURN (NT): the only call of TPlayerMagicControl.NewTurn 0x5577CC2C is @0x5577D293 (eax = pmc, on every machine,
synced-RNG context; Drought's own hook is a jmp at the callee's prologue) -> call-hook: the cave calls 0x5577CC2C
first (Drought and all) and then, for the player [ [pmc+0x10]+0xA6 ] that owns an ACTIVE Overgrowth (list scan:
marker 383, caster [e+0x19], bit0 of [e+0x10]), grows the forest on the SURFACE level:
  caps from the level area A = w*h: GROW = A*GROW_PM/1000 (min 1) hexes, PICKS = A*PICKS_PM/1000 (min 1) random
  picks, SEEDS = A/SEED_DIV (min 1) new seeds.  Each pick (TAoWHSMap.Random 0x5577827C = synced stream):
    - a FOREST hex (overlay [f+0x15] == 1) -> one random neighbour (Random(6)) grows if it is growable;
    - a growable hex grows if it touches forest, else as one of the turn's SEEDS;
  stop at GROW growths or when the picks run out.  growable = terrain [f+0x14] in {Grass 1, Snow 3, Steppe 4,
  Wasteland 5}, overlay 0xFF (bare: no mountain/hill/road/bridge/vegetation), no TStructure on it
  (HSEngine FindNoneTransparentHS 0x55702004 with the TStructure classref [0x55713BD8], as the road builder
  0x55770FF0 does).  Desert is never grown (Drought's domain), and Drought never converts forest (its filters want
  overlay 0xFF / 2) -> when both run, every bare hex goes to whichever reaches it first and stays: no endless fight.
  grow(x, y) = THSMap.ClearTerrain(map, x, y; level 0, radius 0, terrain -1) (thunk 0x557025DC: removes rocks/bones
  decorations on the hex) + TREE PLACER = TAoWHSMap.PlaceTerrain 0x55778EEC with a decoration filter (the
  patch_level_terrain_rocks_v1.py cave_rocks recipe): scan the global resources ([[0x558FA044]+0x24]+8) for
  ClassID 0x20167 TTerrainMO resources with a single-hex TTerrainList (UsedTerrain == 1, GetTerrain(0) == the hex's
  terrain, GetOverlay(0) == 1) and decoration byte [res+0x44] == 0 = trees (Release.hss: "Forest" gr_tree / sn_tree /
  st_tree / wl_tree / pine trees...; toadstools 4, dead trees 3, rocks 1 are excluded), RandSeed := map.Random(
  0xFFFFFF) exactly like PlaceTerrain, pick map.Random(count), resource VMT+0x68 CreateAndPlace(res, map, x, y, 0).
  The placed tree object makes the hex a forest (overlay 1: forest movement cost, Forestry applies, road cost 5).
  All state is the synced map + RNG; locals live on the stack -> MP-deterministic.

v2 (2026-10-15, user: "like drought, it should have a custom hex glow (subtle green) and should slowly disappear
once spell removed"):
  * MARKER per grown hex = Drought's recipe: a TFrozenWaterHS (classref holder [0x55714774]; TEObject.Create
    0x55703064 + THSMap.PlaceHX 0x557025F4 on the field's x/y/level bytes +0x10/+0x11/+0x12), extended by
    build_raiseterrain_matrix.py (+0xC countdown, +0xD owner, +0xE restore, +0xF target; saved under tags
    0x1E/0x1F/0x6E/0x6F -> survives save/load, identical in MP):
        +0xC = map.Random(REVERT_SPREAD) + 1     (revert delay once the spell is gone)
        +0xD = OWNER_FLAG | (player & 0x3F)     (0x40 bit: the vanilla/Drought NewTurn `cmp dl,[hs+0xD]` never
                                                  matches -> the marker is never ticked or MeltIce'd by them)
        +0xE = OG_FLAG | terrain                (0x40 without 0x80: an Overgrowth marker; never equals a terrain, so
                                                  raise-terrain's frame-9 flip leaves it alone)
        +0xF = terrain                          (unchanged by the trees -> cave_tchg keeps the marker; any later
                                                  terrain change frees it and the forest just stays)
    Placed only when the tree really made the hex a forest (overlay [f+0x15] == 1).  g_ok now also refuses a hex
    that already carries ANY TFrozenWaterHS (ice / raise-terrain / Drought / ours).
  * GLOW: patch_drought_glow_v1.py v2 draws spell 383 gfx slot 3 for markers with +0xE & 0xC0 == 0x40.
  * REVERT: the NT cave, for the player whose turn starts and who has NO active Overgrowth, walks the surface and,
    for each of that player's markers, decrements +0xC; at <= 0 it Destroys the marker (vanilla MeltIce's
    `mov dl,1 / call [vmt-4]`) and, if the hex is still a forest, ClearTerrain()s it back to bare.  Runs in the
    player NewTurn context (synced, not inside the map-object broadcast), like the growth itself.
    -> removal / dispel / upkeep loss: the forest melts away over ~REVERT_SPREAD of the caster's turns; a recast
    stops it (markers just hold again).  v1-grown forests have no marker and stay forever.  An eliminated caster
    gets no more turns -> its forest stays (Drought caveat).
Zone 0x55824000..0x55826000 (zero, reloc-free; PIC via call/pop delta for every in-image absolute).
Dry-run default; --apply (upgrades an older build of this patch in place) / --revert / --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_overgrowth.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TAirMastery": (0x557EDEA0, 0x557F0458) (site 0x557F3A5B),
pfs_donor 70, tc_type None, sphere 19, tier 4, mana 75, research 250, upkeep 8, pokes [(0x34, 4, 0xFFFFFFFF)].

v3 (2026-10-15): WORLD HEALER (spell 327, Life/Water sphere pair 12, tier 4; research 250, cost 75, upkeep 15) shares
this TAirMastery-clone plumbing - "slowly causes grass to grow over the map (persists after spell removed)":
  * CE / MM / AC / DE / CHK treat marker 327 exactly like 383 (base Activate/Deactivate only, no mastery message,
    once per player per spell; Overgrowth and World Healer don't block each other).  `oga` now takes the spell id in
    ecx (dl = player as before).
  * NT: after Overgrowth's grow/revert, a player with an ACTIVE World Healer runs `heal` on the surface: caps from the
    level area like Overgrowth (HEAL_PM / HEAL_PICKS_PM / HEAL_SEED_DIV); each synced pick:
      - a GRASS hex (terrain 1) -> one random neighbour converts if healable (the grass front creeps);
      - a healable hex converts if it touches grass, else as one of the turn's SEEDS.
    healable = terrain Desert 2 / Snow 3 / Steppe 4 / Wasteland 5 / Dirt 0xC, overlay bare 0xFF or hill 2 (never
    forest/mountain/road/bridge), no TStructure, and NO TFrozenWaterHS on the hex (ice / raise-terrain / Drought /
    Overgrowth markers -> a Drought hex is left alone: Drought wins while it lasts, and its own revert later restores
    the original terrain, which World Healer may then green).  Water, ice and lava are never touched.
  * the change = THSMap.ChangeTerrainEx (map VMT+0xD4, Drought's `conv` recipe: eax map, edx 0, ecx x; push y, 0, 0,
    obj 0, callback, 0, 0; callee cleans) with callback `hcb` (surface, overlay 0xFF/2, terrain in the healable set ->
    Grass 1) -> the engine's own art refresh.  PERMANENT: no markers, nothing reverts when the spell ends.
  Pipeline entry: donor "TAirMastery", pfs_donor 70, tc_type None, sphere 12, tier 4, mana 75, research 250,
  upkeep 15, pokes [(0x34, 4, 0xFFFFFFFF)].

v4 (2026-10-15): ICE AGE (spell 399, Water/Air sphere pair 21, tier 4; research 250, cost 75, upkeep 15) shares the
same plumbing - "slowly changes terrain across the map to snow, and water to ice":
  * CE / MM / AC / DE / CHK treat marker 399 like 383/327.  `oga` gained an ANY-PLAYER mode (dl = 0x80).
  * NT: after Overgrowth and World Healer, a player with an ACTIVE Ice Age runs `ice` on the surface (caps from the
    level area: ICE_PM / ICE_PICKS_PM / ICE_SEED_DIV, as World Healer); each synced pick:
      - a SNOW (3) or ICE (6) hex -> one random neighbour converts if freezable (the frost front creeps);
      - a freezable hex converts if it touches snow/ice, else as one of the turn's SEEDS.
    freezable LAND = Grass 1 / Steppe 4 / Wasteland 5 / Dirt 0xC with overlay bare 0xFF or hill 2 (never forest,
    mountain, road, bridge; never Desert 2 (Drought's / arid) or Lava 9) -> Snow 3.
    freezable WATER = Water 0 with overlay 0xFF (no bridge) and NO TArmy on the hex (field VMT+0x80
    FindOwnedChild(0x20217), the Poison Plant's lookup: ships/swimmers are never frozen in) -> Ice 6.
    Both: no TStructure on the hex, no TFrozenWaterHS (vanilla Freeze Water ice / raise-terrain / Drought /
    Overgrowth markers -> those hexes are left alone: Drought wins, Freeze Water's ice melts back as vanilla).
  * the change = ChangeTerrainEx with callback `icb` (surface; water bare -> 6; land set + bare/hill -> 3).
    PERMANENT (no markers, nothing melts when the spell ends) - ice is plain terrain 6 like map-placed ice.
  * vs World Healer (which turns Snow into Grass): while ANY player has an active Ice Age, World Healer leaves Snow
    alone; while ANY player has an active World Healer, Ice Age leaves Grass alone -> a hex goes to whichever spell
    reaches it first and stays (no endless flip-flop).  Overgrowth never changes terrain (it only plants trees, incl.
    snow trees on bare snow) and Ice Age never touches forest -> no conflict.
  Pipeline entry: donor "TAirMastery", pfs_donor 70, tc_type None, sphere 21, tier 4, mana 75, research 250,
  upkeep 15, pokes [(0x34, 4, 0xFFFFFFFF)].

v5 (2026-10-15, user: "ice age spread too slow ... should have the same hex glow as freeze water but slightly more
subtle ... snow/ice should slowly revert after spell removed"):
  * speed x2: ICE_PM 15 -> 30, ICE_PICKS_PM 600 -> 1200, ICE_SEED_DIV 300 -> 150.
  * MARKER per frozen hex (Overgrowth's recipe, `i_mark`): after the ChangeTerrainEx the hex is re-read and, only if
    it really became Snow 3 / Ice 6, a TFrozenWaterHS is placed:
        +0xC = map.Random(ICE_REVERT_SPREAD) + 1   (thaw delay once the spell is gone)
        +0xD = OWNER_FLAG | (player & 0x3F)       (vanilla / Drought NewTurn `cmp dl,[hs+0xD]` never matches ->
                                                   never ticked or MeltIce'd by them; cave_melt never sees it)
        +0xE = ICE_FLAG 0xC0 | original terrain   (0xC0 = Ice Age; 0x80 alone = Drought, 0x40 alone = Overgrowth;
                                                   never equals a terrain -> raise-terrain's frame-9 flip ignores it;
                                                   Drought's water-origin test wants +0xE == 0x80 AND +0xF == 2)
        +0xF = the new terrain (3 / 6)            (cave_tchg keeps the marker while the hex holds it; any other
                                                   terrain change frees it and that hex keeps its new terrain)
    Marked hexes are refused by every spreader (g_ok / h_ok / i_ok / Drought's cvt: "any TFrozenWaterHS") -> no
    fights over them while the marker lives.  Only conversions that really happened count against the turn cap.
  * THAW (`irev`, the NT cave's else-branch for a player WITHOUT an active Ice Age): walk the surface; each of this
    player's Ice Age markers counts +0xC down; at <= 0 the marker is Destroyed (vanilla MeltIce's `mov dl,1 / call
    [vmt-4]`) and, if the hex still holds +0xF, it is restored to the original terrain (ChangeTerrainEx, callback
    `rcb` writes obj = the original terrain).  Water-origin ice is NOT thawed while a TArmy stands on it (field
    VMT+0x80 FindOwnedChild(0x20217); +0xC := 1, retried next turn) and stays frozen for good if its overlay is no
    longer bare.  A recast stops the thaw (the markers just hold again).  v4-frozen hexes carry no marker and stay
    forever.  An eliminated caster gets no more turns -> its frost stays (Drought caveat).
  * GLOW: patch_drought_glow_v1.py v3 draws spell 399 gfx slot 3 (pure frame pick) for markers with
    +0xE & 0xC0 == 0xC0 - the vanilla Freeze Water sparkle (general-FX slot 0x46 = EFFECTS\\SWARM.ILB 20-31) copied
    at a lower blend.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_overgrowth"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55824000, 0x55826000
SPELL_ID = 383
HEAL_ID = 327                                       # v3: World Healer (Life/Water) shares the plumbing
HEAL_PM, HEAL_PICKS_PM, HEAL_SEED_DIV = 15, 600, 300   # v3: grass per turn = 1.5 % of the level area (as Overgrowth v2.1); picks 60 %; seeds = area/300
HEAL_TERRAINS = (2, 3, 4, 5, 0xC)                   # v3: Desert, Snow, Steppe, Wasteland, Dirt -> Grass (never Water 0 / Ice 6 / Lava 9)
TERRAIN_SLOT = 0xD4                                 # v3: TAoWHSMap VMT+0xD4 = THSMap.ChangeTerrainEx (Drought's conv)
ICE_ID = 399                                        # v4: Ice Age (Water/Air) shares the plumbing
ICE_PM, ICE_PICKS_PM, ICE_SEED_DIV = 30, 1200, 150  # v5 (user: spread too slow; v4 15/600/300): frost per turn = 3 % of the level area; picks 120 %; seeds = area/150
ICE_FLAG, ICE_REVERT_SPREAD = 0xC0, 10              # v5: marker tag in +0xE (0xC0 | original terrain); thaw over 1..10 of the caster's turns
ICE_LAND = (1, 4, 5, 0xC)                           # v4: Grass, Steppe, Wasteland, Dirt -> Snow 3 (never Desert 2 / Lava 9); Water 0 -> Ice 6
CLASSID_ARMY = 0x20217                              # v4: TArmy ClassID (Poison Plant's FindOwnedChild lookup, field VMT+0x80)
GROW_PM, PICKS_PM, SEED_DIV = 15, 600, 300         # v2.1 10/15 (user: spread faster; was 6/300/600): growth per turn = 1.5 % of the level area; picks 60 %; seeds = area/300 (each min 1)
GROW_TERRAINS = (1, 3, 4, 5)                        # Grass, Snow, Steppe, Wasteland (never Desert 2 = Drought's)

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
AM_ACT, AM_DEACT, AM_CHK, AM_CHK_MSG, AM_CHK_SEH = 0x557F0384, 0x557F03EC, 0x557F02AC, 0x557F0306, 0x557F0374
AM_ENCH_CREATE, AM_ENCH_CELL = 0x557F0204, 0x557EDD7C
MASTERY_MSG, LSTRASG = 0x557EF7C0, 0x55701150
NEWTURN = 0x5577CC2C
MAP_RANDOM = 0x5577827C
GETMAPLEVEL, LEVEL_GETFIELD = 0x557020EC, 0x557020DC
FIND_NT_HS, STRUCT_CLASSREF = 0x55702004, 0x55713BD8
CLEAR_TERRAIN = 0x557025DC
G_RESHOLDER, IMP_TLIST, IMP_RANDSEED = 0x558FA044, 0x558FB94C, 0x558FB720
TOBJ_CREATE, TOBJ_FREE = 0x557010A8, 0x557010B8
TLIST_CLEAR, TLIST_ADD, TLIST_GET = 0x55701624, 0x5570161C, 0x5570163C
TL_USED, TL_GETTERRAIN, TL_GETOVERLAY = 0x55701CA4, 0x55701C8C, 0x55701C94
CLASSID_TERRAINMO = 0x20167
FW_CLASSREF, FIND_HS, EO_CREATE, PLACEHX, MAPPTR = 0x55714774, 0x55701FFC, 0x55703064, 0x557025F4, 0x558E9494   # v2 markers (Drought's recipe; thunks import-table checked)
REVERT_SPREAD, OWNER_FLAG, OG_FLAG = 10, 0x40, 0x40                                                             # v2: revert over 1..10 of the caster's turns
NBR_TAB = bytes([0, 0xFF, 1, 0xFF, 1, 0, 0, 1, 0xFF, 0, 0xFF, 0xFF,       # even x: N, NE, SE, S, SW, NW (= Drought's)
                 0, 0xFF, 1, 0, 1, 1, 0, 1, 0xFF, 1, 0xFF, 0])             # odd x

CODE_SITES = {
    "CE": (0x557F06E4, bytes.fromhex("33c9b201a1"), "jmp"),
    "MM": (0x557F061C, bytes.fromhex("e89ff1ffff"), "call"),
    "NT": (0x5577D293, bytes.fromhex("e894f9ffff"), "call"),
}
VMT_SLOTS = {
    "amAct":   (0x557EDE24, AM_ACT, "ac"),
    "amDeact": (0x557EDE1C, AM_DEACT, "de"),
    "amChk":   (0x557EDE20, AM_CHK, "chk"),
}
CAVE_OF = {"CE": "ce", "MM": "mm", "NT": "nt"}

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


def build():
    out = bytearray(); where = {}
    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        code = asm_pic(src % dict(C, **where), va) if pic else bytes(ks.asm(src % dict(C, **where), va)[0])
        out.extend(code)
    def place_data(name, data):
        while len(out) % 16: out.append(0)
        where[name] = ZONE + len(out); out.extend(data)
    C = {"id": SPELL_ID, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT, "bdeact": BASE_DEACT, "bchk": BASE_CHK,
         "amact": AM_ACT, "amdeact": AM_DEACT, "amchk": AM_CHK, "ammsg": AM_CHK_MSG, "amseh": AM_CHK_SEH,
         "amcreate": AM_ENCH_CREATE, "amcell": AM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "newturn": NEWTURN,
         "rnd": MAP_RANDOM, "getlevel": GETMAPLEVEL, "getfield": LEVEL_GETFIELD, "findnt": FIND_NT_HS,
         "structref": STRUCT_CLASSREF, "clear": CLEAR_TERRAIN, "resholder": G_RESHOLDER, "tlistref": IMP_TLIST,
         "randseed": IMP_RANDSEED, "tcreate": TOBJ_CREATE, "tfree": TOBJ_FREE, "tclear": TLIST_CLEAR, "tadd": TLIST_ADD,
         "tget": TLIST_GET, "tlused": TL_USED, "tlterr": TL_GETTERRAIN, "tlov": TL_GETOVERLAY, "clsid": CLASSID_TERRAINMO,
         "growpm": GROW_PM, "pickspm": PICKS_PM, "seeddiv": SEED_DIV,
         "fwcls": FW_CLASSREF, "findhs": FIND_HS, "eocreate": EO_CREATE, "placehx": PLACEHX, "mapptr": MAPPTR,
         "rspread": REVERT_SPREAD, "oflag": OWNER_FLAG, "ogflag": OG_FLAG,
         "hid": HEAL_ID, "hgrowpm": HEAL_PM, "hpickspm": HEAL_PICKS_PM, "hseeddiv": HEAL_SEED_DIV, "tslot": TERRAIN_SLOT,
         "iid": ICE_ID, "igrowpm": ICE_PM, "ipickspm": ICE_PICKS_PM, "iseeddiv": ICE_SEED_DIV, "armyid": CLASSID_ARMY,
         "iflag": ICE_FLAG, "irspread": ICE_REVERT_SPREAD}
    place_data("tab", NBR_TAB)
    # oga: dl = player index, ecx = spell id (v3: 383 Overgrowth / 327 World Healer, v4: 399 Ice Age) -> al = 1 if that
    # player has an ACTIVE enchantment of that spell; v4: dl = 0x80 = ANY player; all other regs preserved
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
    # CE: replayed CreateEnchantment + marker + name (jmp'ed to; eax = spell)
    place("ce", """
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
        mov ecx, [edx+0x10]
        cmp ecx, %(id)d
        je ce_mark
        cmp ecx, %(hid)d
        je ce_mark
        cmp ecx, %(iid)d
        jne ce_done
    ce_mark:
        mov dword ptr [eax+0x14], ecx
        push eax
        lea eax, [eax+0x1c]
        mov edx, [edx+8]
        call %(lstrasg)#x
        pop eax
    ce_done:
        ret
    """, pic=True)
    # MM: TAirMastery.ExecuteTE's sphere-mastery message (edi = the spell)
    place("mm", """
        cmp dword ptr [edi+0x10], %(id)d
        je mm_skip
        cmp dword ptr [edi+0x10], %(hid)d
        je mm_skip
        cmp dword ptr [edi+0x10], %(iid)d
        je mm_skip
        jmp %(mmsg)#x
    mm_skip:
        ret
    """)
    place("ac", """
        cmp dword ptr [eax+0x14], %(id)d
        je ac_ours
        cmp dword ptr [eax+0x14], %(hid)d
        je ac_ours
        cmp dword ptr [eax+0x14], %(iid)d
        je ac_ours
        jmp %(amact)#x
    ac_ours:
        jmp %(bact)#x
    """)
    place("de", """
        cmp dword ptr [eax+0x14], %(id)d
        je de_ours
        cmp dword ptr [eax+0x14], %(hid)d
        je de_ours
        cmp dword ptr [eax+0x14], %(iid)d
        je de_ours
        jmp %(amdeact)#x
    de_ours:
        jmp %(bdeact)#x
    """)
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast)
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        cmp dword ptr [eax+0x14], %(hid)d
        je chk_ours
        cmp dword ptr [eax+0x14], %(iid)d
        je chk_ours
        jmp %(amchk)#x
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
        mov ecx, [eax+0x14]
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
    # TREES: (eax = map, edx = x, ecx = y, [esp+4] = terrain, [esp+8] = level) -> ret 8.  PlaceTerrain with a
    # decoration filter: single-hex TTerrainMO resources of this terrain with overlay 1 and decoration 0 (trees).
    place("trees", """
        push ebp
        mov ebp, esp
        sub esp, 0x14
        push ebx
        push esi
        push edi
        mov [ebp-4], eax
        mov [ebp-8], edx
        mov [ebp-0xC], ecx
        call $D
        pop ebx
        sub ebx, $D
        mov dl, 1
        mov eax, [ebx+%(tlistref)#x]
        call %(tcreate)#x
        mov [ebp-0x10], eax
        call %(tclear)#x
        mov eax, [ebx+%(resholder)#x]
        mov eax, [eax+0x24]
        mov esi, [eax+8]
        xor edi, edi
    t_loop:
        cmp edi, [esi+8]
        jge t_pick
        mov eax, [esi+4]
        mov eax, [eax+edi*4]
        mov [ebp-0x14], eax
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, %(clsid)#x
        jne t_next
        mov eax, [ebp-0x14]
        mov eax, [eax+0x28]
        call %(tlused)#x
        cmp eax, 1
        jne t_next
        mov eax, [ebp-0x14]
        mov eax, [eax+0x28]
        xor edx, edx
        call %(tlterr)#x
        cmp al, [ebp+8]
        jne t_next
        mov eax, [ebp-0x14]
        mov eax, [eax+0x28]
        xor edx, edx
        call %(tlov)#x
        cmp al, 1
        jne t_next
        mov eax, [ebp-0x14]
        cmp byte ptr [eax+0x44], 0
        jne t_next
        mov edx, [ebp-0x14]
        mov eax, [ebp-0x10]
        call %(tadd)#x
    t_next:
        inc edi
        jmp t_loop
    t_pick:
        mov eax, [ebp-0x10]
        mov edx, [eax+8]
        test edx, edx
        jz t_free
        mov edx, 0xFFFFFF
        mov eax, [ebp-4]
        call %(rnd)#x
        mov edx, [ebx+%(randseed)#x]
        mov [edx], eax
        mov eax, [ebp-0x10]
        mov edx, [eax+8]
        mov eax, [ebp-4]
        call %(rnd)#x
        mov edx, eax
        mov eax, [ebp-0x10]
        call %(tget)#x
        mov edx, [ebp-0xC]
        push edx
        mov edx, [ebp+0xC]
        push edx
        mov ecx, [ebp-8]
        mov edx, [ebp-4]
        mov ebx, [eax]
        call dword ptr [ebx+0x68]
    t_free:
        mov eax, [ebp-0x10]
        call %(tfree)#x
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    """, pic=True)
    # GROW: ebx = delta, edi = player.  Frame locals: -4 map, -8 grown, -0xC grow cap, -0x10 picks left,
    # -0x14 seed cap, -0x18 seeds used, -0x1C x, -0x20 y, -0x24 nx, -0x28 ny; esi = surface level.
    place("grow", """
        push ebp
        mov ebp, esp
        sub esp, 0x28
        push esi
        push edi
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz g_out
        mov esi, eax
        xor eax, eax
        mov [ebp-8], eax
        mov [ebp-0x18], eax
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        push eax
        imul eax, eax, %(growpm)d
        xor edx, edx
        mov ecx, 1000
        div ecx
        or eax, 1
        mov [ebp-0xC], eax
        mov eax, [esp]
        imul eax, eax, %(pickspm)d
        xor edx, edx
        div ecx
        or eax, 1
        mov [ebp-0x10], eax
        pop eax
        xor edx, edx
        mov ecx, %(seeddiv)d
        div ecx
        or eax, 1
        mov [ebp-0x14], eax
    g_lp:
        mov eax, [ebp-4]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebp-0x1C], eax
        mov eax, [ebp-4]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebp-0x20], eax
        mov ecx, eax
        mov edx, [ebp-0x1C]
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz g_nx
        cmp byte ptr [eax+0x15], 1
        je g_creep
        call g_ok
        test eax, eax
        jz g_nx
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call g_fnbr
        test eax, eax
        jnz g_here
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0x14]
        jae g_nx
        inc dword ptr [ebp-0x18]
    g_here:
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call g_grow
        jmp g_nx
    g_creep:
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call g_nbr
        mov [ebp-0x24], edx
        mov [ebp-0x28], ecx
        call g_getf
        test eax, eax
        jz g_nx
        call g_ok
        test eax, eax
        jz g_nx
        mov edx, [ebp-0x24]
        mov ecx, [ebp-0x28]
        call g_grow
    g_nx:
        mov eax, [ebp-8]
        cmp eax, [ebp-0xC]
        jae g_out
        dec dword ptr [ebp-0x10]
        jnz g_lp
    g_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    g_ok:
        push eax
        movzx edx, byte ptr [eax+0x14]
        cmp edx, 1
        je ok_t
        cmp edx, 3
        je ok_t
        cmp edx, 4
        je ok_t
        cmp edx, 5
        jne ok_no
    ok_t:
        cmp byte ptr [eax+0x15], 0xff
        jne ok_no
        mov edx, [ebx+%(structref)#x]
        call %(findnt)#x
        test eax, eax
        jnz ok_no
        mov eax, [esp]
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jnz ok_no
        pop eax
        mov eax, 1
        ret
    ok_no:
        pop eax
        xor eax, eax
        ret

    g_getf:
        test edx, edx
        js gf_no
        test ecx, ecx
        js gf_no
        cmp edx, [esi+0xc]
        jge gf_no
        cmp ecx, [esi+0x10]
        jge gf_no
        mov eax, esi
        call %(getfield)#x
        ret
    gf_no:
        xor eax, eax
        ret

    g_nbr:
        test edx, 1
        jz nb_even
        add eax, 6
    nb_even:
        push edi
        lea edi, [ebx+%(tab)#x]
        lea edi, [edi+eax*2]
        movsx eax, byte ptr [edi]
        add edx, eax
        movsx eax, byte ptr [edi+1]
        add ecx, eax
        pop edi
        ret

    g_fnbr:
        push edi
        push edx
        push ecx
        xor edi, edi
    fn_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call g_nbr
        call g_getf
        test eax, eax
        jz fn_n
        cmp byte ptr [eax+0x15], 1
        je fn_y
    fn_n:
        inc edi
        cmp edi, 6
        jb fn_l
        xor eax, eax
        jmp fn_out
    fn_y:
        mov eax, 1
    fn_out:
        pop ecx
        pop edx
        pop edi
        ret

    g_grow:
        push edx
        push ecx
        call g_getf
        test eax, eax
        jz gr_out
        movzx eax, byte ptr [eax+0x14]
        mov edx, [esp+4]
        mov ecx, [esp]
        push eax
        push edx
        push ecx
        push 0
        push 0
        push -1
        mov eax, [ebp-4]
        call %(clear)#x
        pop ecx
        pop edx
        pop eax
        push 0
        push eax
        mov eax, [ebp-4]
        call %(trees)#x
        inc dword ptr [ebp-8]
        mov edx, [esp+4]
        mov ecx, [esp]
        call g_getf
        test eax, eax
        jz gr_out
        cmp byte ptr [eax+0x15], 1
        jne gr_out
        call g_mark
    gr_out:
        pop ecx
        pop edx
        ret

    g_mark:
        push esi
        push edi
        mov esi, eax
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(fwcls)#x]
        call %(eocreate)#x
        push eax
        movzx ecx, byte ptr [esi+0x11]
        push ecx
        movzx ecx, byte ptr [esi+0x12]
        push ecx
        movzx ecx, byte ptr [esi+0x10]
        mov edx, [esp+8]
        mov eax, [ebx+%(mapptr)#x]
        mov eax, [eax]
        call %(placehx)#x
        mov eax, [ebp-4]
        mov edx, %(rspread)d
        call %(rnd)#x
        inc eax
        pop edx
        mov byte ptr [edx+0xc], al
        mov eax, [esp]
        and al, 0x3f
        or al, %(oflag)d
        mov byte ptr [edx+0xd], al
        mov al, byte ptr [esi+0x14]
        mov byte ptr [edx+0xf], al
        or al, %(ogflag)d
        mov byte ptr [edx+0xe], al
        pop edi
        pop esi
        ret
    """, pic=True)
    # REV (v2): ebx = delta, edi = player WITHOUT an active Overgrowth.  Walk the surface; each of this player's
    # Overgrowth markers counts down; at <= 0 the marker is destroyed and a still-forested hex is cleared to bare.
    # Frame: -4 map, -8 y, -0xC owner byte, -0x10 x, -0x14 field; esi = surface level.
    place("rev", """
        push ebp
        mov ebp, esp
        sub esp, 0x14
        push esi
        push edi
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        test eax, eax
        jz r_out
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz r_out
        mov esi, eax
        mov eax, edi
        and eax, 0x3f
        or eax, %(oflag)d
        mov [ebp-0xC], eax
        xor eax, eax
        mov [ebp-8], eax
    r_y:
        mov eax, [ebp-8]
        cmp eax, [esi+0x10]
        jge r_out
        xor eax, eax
        mov [ebp-0x10], eax
    r_x:
        mov eax, [ebp-0x10]
        cmp eax, [esi+0xc]
        jge r_ny
        mov edx, eax
        mov ecx, [ebp-8]
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz r_nx
        mov [ebp-0x14], eax
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz r_nx
        mov dl, byte ptr [eax+0xe]
        and dl, 0xc0
        cmp dl, %(ogflag)d
        jne r_nx
        mov dl, byte ptr [eax+0xd]
        cmp dl, byte ptr [ebp-0xC]
        jne r_nx
        dec byte ptr [eax+0xc]
        cmp byte ptr [eax+0xc], 0
        jg r_nx
        mov dl, 1
        mov ecx, [eax]
        call dword ptr [ecx-4]
        mov eax, [ebp-0x14]
        cmp byte ptr [eax+0x15], 1
        jne r_nx
        push 0
        push 0
        push -1
        mov edx, [ebp-0x10]
        mov ecx, [ebp-8]
        mov eax, [ebp-4]
        call %(clear)#x
    r_nx:
        inc dword ptr [ebp-0x10]
        jmp r_x
    r_ny:
        inc dword ptr [ebp-8]
        jmp r_y
    r_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """, pic=False)
    # HCB (v3): World Healer's ChangeTerrainEx callback: eax = obj, edx = field, ecx = &terrain, [esp+4] = &overlay;
    # ret 4.  Surface, overlay bare/hill, terrain Desert/Snow/Steppe/Wasteland/Dirt -> Grass.
    place("hcb", """
        push ebp
        mov ebp, esp
        push ebx
        cmp byte ptr [edx+0x12], 0
        jne hc_done
        mov ebx, [ebp+8]
        mov bl, byte ptr [ebx]
        cmp bl, 0xff
        je hc_ov
        cmp bl, 2
        jne hc_done
    hc_ov:
        mov bl, byte ptr [ecx]
        cmp bl, 2
        je hc_set
        cmp bl, 3
        je hc_set
        cmp bl, 4
        je hc_set
        cmp bl, 5
        je hc_set
        cmp bl, 0xc
        jne hc_done
    hc_set:
        mov byte ptr [ecx], 1
    hc_done:
        pop ebx
        pop ebp
        ret 4
    """)
    # HEAL (v3): ebx = delta, edi = player with an ACTIVE World Healer.  Frame as GROW: -4 map, -8 converted, -0xC cap,
    # -0x10 picks left, -0x14 seed cap, -0x18 seeds used, -0x1C x, -0x20 y, -0x24 nx, -0x28 ny; esi = surface level.
    place("heal", """
        push ebp
        mov ebp, esp
        sub esp, 0x2c
        push esi
        push edi
        push ecx
        push edx
        mov dl, 0x80
        mov ecx, %(iid)d
        call %(oga)#x
        mov byte ptr [ebp-0x2c], al
        pop edx
        pop ecx
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        test eax, eax
        jz h_out
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz h_out
        mov esi, eax
        xor eax, eax
        mov [ebp-8], eax
        mov [ebp-0x18], eax
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        push eax
        imul eax, eax, %(hgrowpm)d
        xor edx, edx
        mov ecx, 1000
        div ecx
        or eax, 1
        mov [ebp-0xC], eax
        mov eax, [esp]
        imul eax, eax, %(hpickspm)d
        xor edx, edx
        div ecx
        or eax, 1
        mov [ebp-0x10], eax
        pop eax
        xor edx, edx
        mov ecx, %(hseeddiv)d
        div ecx
        or eax, 1
        mov [ebp-0x14], eax
    h_lp:
        mov eax, [ebp-4]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebp-0x1C], eax
        mov eax, [ebp-4]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebp-0x20], eax
        mov ecx, eax
        mov edx, [ebp-0x1C]
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz h_nx
        cmp byte ptr [eax+0x14], 1
        je h_creep
        call h_ok
        test eax, eax
        jz h_nx
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call h_fnbr
        test eax, eax
        jnz h_here
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0x14]
        jae h_nx
        inc dword ptr [ebp-0x18]
    h_here:
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call h_conv
        jmp h_nx
    h_creep:
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call h_nbr
        mov [ebp-0x24], edx
        mov [ebp-0x28], ecx
        call h_getf
        test eax, eax
        jz h_nx
        call h_ok
        test eax, eax
        jz h_nx
        mov edx, [ebp-0x24]
        mov ecx, [ebp-0x28]
        call h_conv
    h_nx:
        mov eax, [ebp-8]
        cmp eax, [ebp-0xC]
        jae h_out
        dec dword ptr [ebp-0x10]
        jnz h_lp
    h_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    h_ok:
        push eax
        movzx edx, byte ptr [eax+0x14]
        cmp edx, 2
        je hk_t
        cmp edx, 3
        je hk_snow
        cmp edx, 4
        je hk_t
        cmp edx, 5
        je hk_t
        cmp edx, 0xc
        jne hk_no
        jmp hk_t
    hk_snow:
        cmp byte ptr [ebp-0x2c], 0
        jne hk_no
    hk_t:
        mov dl, byte ptr [eax+0x15]
        cmp dl, 0xff
        je hk_ov
        cmp dl, 2
        jne hk_no
    hk_ov:
        mov edx, [ebx+%(structref)#x]
        call %(findnt)#x
        test eax, eax
        jnz hk_no
        mov eax, [esp]
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jnz hk_no
        pop eax
        mov eax, 1
        ret
    hk_no:
        pop eax
        xor eax, eax
        ret

    h_getf:
        test edx, edx
        js hf_no
        test ecx, ecx
        js hf_no
        cmp edx, [esi+0xc]
        jge hf_no
        cmp ecx, [esi+0x10]
        jge hf_no
        mov eax, esi
        call %(getfield)#x
        ret
    hf_no:
        xor eax, eax
        ret

    h_nbr:
        test edx, 1
        jz hn_even
        add eax, 6
    hn_even:
        push edi
        lea edi, [ebx+%(tab)#x]
        lea edi, [edi+eax*2]
        movsx eax, byte ptr [edi]
        add edx, eax
        movsx eax, byte ptr [edi+1]
        add ecx, eax
        pop edi
        ret

    h_fnbr:
        push edi
        push edx
        push ecx
        xor edi, edi
    hfn_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call h_nbr
        call h_getf
        test eax, eax
        jz hfn_n
        cmp byte ptr [eax+0x14], 1
        je hfn_y
    hfn_n:
        inc edi
        cmp edi, 6
        jb hfn_l
        xor eax, eax
        jmp hfn_out
    hfn_y:
        mov eax, 1
    hfn_out:
        pop ecx
        pop edx
        pop edi
        ret

    h_conv:
        push esi
        push ecx
        push 0
        push 0
        push 0
        lea eax, [ebx+%(hcb)#x]
        push eax
        push 0
        push 0
        mov ecx, edx
        xor edx, edx
        mov eax, [ebp-4]
        mov esi, [eax]
        call dword ptr [esi+%(tslot)#x]
        pop esi
        inc dword ptr [ebp-8]
        ret
    """)
    # ICB (v4): Ice Age's ChangeTerrainEx callback: eax = obj, edx = field, ecx = &terrain, [esp+4] = &overlay; ret 4.
    # Surface only; bare Water -> Ice 6; Grass/Steppe/Wasteland/Dirt with overlay bare/hill -> Snow 3.
    place("icb", """
        push ebp
        mov ebp, esp
        push ebx
        cmp byte ptr [edx+0x12], 0
        jne ic_done
        mov ebx, [ebp+8]
        mov bl, byte ptr [ebx]
        mov bh, byte ptr [ecx]
        test bh, bh
        jnz ic_land
        cmp bl, 0xff
        jne ic_done
        mov byte ptr [ecx], 6
        jmp ic_done
    ic_land:
        cmp bl, 0xff
        je ic_ov
        cmp bl, 2
        jne ic_done
    ic_ov:
        cmp bh, 1
        je ic_set
        cmp bh, 4
        je ic_set
        cmp bh, 5
        je ic_set
        cmp bh, 0xc
        jne ic_done
    ic_set:
        mov byte ptr [ecx], 3
    ic_done:
        pop ebx
        pop ebp
        ret 4
    """)
    # ICE (v4): ebx = delta, edi = player with an ACTIVE Ice Age.  Frame as HEAL: -4 map, -8 converted, -0xC cap,
    # -0x10 picks left, -0x14 seed cap, -0x18 seeds used, -0x1C x, -0x20 y, -0x24 nx, -0x28 ny, -0x2C byte = some
    # player has an active World Healer (then Grass is left alone); esi = surface level.
    place("ice", """
        push ebp
        mov ebp, esp
        sub esp, 0x2c
        push esi
        push edi
        push ecx
        push edx
        mov dl, 0x80
        mov ecx, %(hid)d
        call %(oga)#x
        mov byte ptr [ebp-0x2c], al
        pop edx
        pop ecx
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        test eax, eax
        jz i_out
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz i_out
        mov esi, eax
        xor eax, eax
        mov [ebp-8], eax
        mov [ebp-0x18], eax
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        push eax
        imul eax, eax, %(igrowpm)d
        xor edx, edx
        mov ecx, 1000
        div ecx
        or eax, 1
        mov [ebp-0xC], eax
        mov eax, [esp]
        imul eax, eax, %(ipickspm)d
        xor edx, edx
        div ecx
        or eax, 1
        mov [ebp-0x10], eax
        pop eax
        xor edx, edx
        mov ecx, %(iseeddiv)d
        div ecx
        or eax, 1
        mov [ebp-0x14], eax
    i_lp:
        mov eax, [ebp-4]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebp-0x1C], eax
        mov eax, [ebp-4]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebp-0x20], eax
        mov ecx, eax
        mov edx, [ebp-0x1C]
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz i_nx
        cmp byte ptr [eax+0x14], 3
        je i_creep
        cmp byte ptr [eax+0x14], 6
        je i_creep
        call i_ok
        test eax, eax
        jz i_nx
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call i_fnbr
        test eax, eax
        jnz i_here
        mov eax, [ebp-0x18]
        cmp eax, [ebp-0x14]
        jae i_nx
        inc dword ptr [ebp-0x18]
    i_here:
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call i_conv
        jmp i_nx
    i_creep:
        mov eax, [ebp-4]
        mov edx, 6
        call %(rnd)#x
        mov edx, [ebp-0x1C]
        mov ecx, [ebp-0x20]
        call i_nbr
        mov [ebp-0x24], edx
        mov [ebp-0x28], ecx
        call i_getf
        test eax, eax
        jz i_nx
        call i_ok
        test eax, eax
        jz i_nx
        mov edx, [ebp-0x24]
        mov ecx, [ebp-0x28]
        call i_conv
    i_nx:
        mov eax, [ebp-8]
        cmp eax, [ebp-0xC]
        jae i_out
        dec dword ptr [ebp-0x10]
        jnz i_lp
    i_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret

    i_ok:
        push eax
        movzx edx, byte ptr [eax+0x14]
        test edx, edx
        jnz ik_land
        cmp byte ptr [eax+0x15], 0xff
        jne ik_no
        mov edx, %(armyid)d
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jnz ik_no
        jmp ik_common
    ik_land:
        cmp edx, 1
        je ik_grass
        cmp edx, 4
        je ik_t
        cmp edx, 5
        je ik_t
        cmp edx, 0xc
        jne ik_no
        jmp ik_t
    ik_grass:
        cmp byte ptr [ebp-0x2c], 0
        jne ik_no
    ik_t:
        mov dl, byte ptr [eax+0x15]
        cmp dl, 0xff
        je ik_common
        cmp dl, 2
        jne ik_no
    ik_common:
        mov eax, [esp]
        mov edx, [ebx+%(structref)#x]
        call %(findnt)#x
        test eax, eax
        jnz ik_no
        mov eax, [esp]
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jnz ik_no
        pop eax
        mov eax, 1
        ret
    ik_no:
        pop eax
        xor eax, eax
        ret

    i_getf:
        test edx, edx
        js if_no
        test ecx, ecx
        js if_no
        cmp edx, [esi+0xc]
        jge if_no
        cmp ecx, [esi+0x10]
        jge if_no
        mov eax, esi
        call %(getfield)#x
        ret
    if_no:
        xor eax, eax
        ret

    i_nbr:
        test edx, 1
        jz iq_even
        add eax, 6
    iq_even:
        push edi
        lea edi, [ebx+%(tab)#x]
        lea edi, [edi+eax*2]
        movsx eax, byte ptr [edi]
        add edx, eax
        movsx eax, byte ptr [edi+1]
        add ecx, eax
        pop edi
        ret

    i_fnbr:
        push edi
        push edx
        push ecx
        xor edi, edi
    ifn_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call i_nbr
        call i_getf
        test eax, eax
        jz ifn_n
        cmp byte ptr [eax+0x14], 3
        je ifn_y
        cmp byte ptr [eax+0x14], 6
        je ifn_y
    ifn_n:
        inc edi
        cmp edi, 6
        jb ifn_l
        xor eax, eax
        jmp ifn_out
    ifn_y:
        mov eax, 1
    ifn_out:
        pop ecx
        pop edx
        pop edi
        ret

    i_conv:
        push edx
        push ecx
        call i_getf
        test eax, eax
        jz ic2_out
        movzx eax, byte ptr [eax+0x14]
        push eax
        push esi
        push dword ptr [esp+8]
        push 0
        push 0
        push 0
        lea eax, [ebx+%(icb)#x]
        push eax
        push 0
        push 0
        mov ecx, [esp+0x28]
        xor edx, edx
        mov eax, [ebp-4]
        mov esi, [eax]
        call dword ptr [esi+%(tslot)#x]
        pop esi
        mov edx, [esp+8]
        mov ecx, [esp+4]
        call i_getf
        test eax, eax
        jz ic2_pop
        movzx edx, byte ptr [eax+0x14]
        cmp edx, [esp]
        je ic2_pop
        cmp edx, 3
        je ic2_mark
        cmp edx, 6
        jne ic2_pop
    ic2_mark:
        inc dword ptr [ebp-8]
        mov ecx, [esp]
        call i_mark
    ic2_pop:
        pop eax
    ic2_out:
        pop ecx
        pop edx
        ret

    i_mark:
        push esi
        push ecx
        mov esi, eax
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(fwcls)#x]
        call %(eocreate)#x
        push eax
        movzx ecx, byte ptr [esi+0x11]
        push ecx
        movzx ecx, byte ptr [esi+0x12]
        push ecx
        movzx ecx, byte ptr [esi+0x10]
        mov edx, [esp+8]
        mov eax, [ebx+%(mapptr)#x]
        mov eax, [eax]
        call %(placehx)#x
        mov eax, [ebp-4]
        mov edx, %(irspread)d
        call %(rnd)#x
        inc eax
        pop edx
        mov byte ptr [edx+0xc], al
        mov eax, edi
        and al, 0x3f
        or al, %(oflag)d
        mov byte ptr [edx+0xd], al
        mov al, byte ptr [esi+0x14]
        mov byte ptr [edx+0xf], al
        mov al, byte ptr [esp]
        or al, %(iflag)d
        mov byte ptr [edx+0xe], al
        pop ecx
        pop esi
        ret
    """)
    # RCB (v5): Ice Age thaw callback (eax = obj = the original terrain, edx = field, ecx = &terrain; ret 4).
    place("rcb", """
        cmp byte ptr [edx+0x12], 0
        jne rc_done
        mov byte ptr [ecx], al
    rc_done:
        ret 4
    """)
    # IREV (v5): ebx = delta, edi = player WITHOUT an active Ice Age.  Walk the surface; each of this player's Ice Age
    # markers counts down; at <= 0 the marker is destroyed and a hex still holding +0xF thaws back to +0xE & 0x3F.
    # Frame: -4 map, -8 y, -0xC owner byte, -0x10 x, -0x14 field, -0x18 original terrain, -0x1C thaw flag.
    place("irev", """
        push ebp
        mov ebp, esp
        sub esp, 0x1c
        push esi
        push edi
        mov eax, [ebx+%(map)#x]
        mov [ebp-4], eax
        test eax, eax
        jz ir_out
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz ir_out
        mov esi, eax
        mov eax, edi
        and eax, 0x3f
        or eax, %(oflag)d
        mov [ebp-0xC], eax
        xor eax, eax
        mov [ebp-8], eax
    ir_y:
        mov eax, [ebp-8]
        cmp eax, [esi+0x10]
        jge ir_out
        xor eax, eax
        mov [ebp-0x10], eax
    ir_x:
        mov eax, [ebp-0x10]
        cmp eax, [esi+0xc]
        jge ir_ny
        mov edx, eax
        mov ecx, [ebp-8]
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz ir_nx
        mov [ebp-0x14], eax
        mov edx, [ebx+%(fwcls)#x]
        call %(findhs)#x
        test eax, eax
        jz ir_nx
        mov dl, byte ptr [eax+0xe]
        and dl, 0xc0
        cmp dl, %(iflag)d
        jne ir_nx
        mov dl, byte ptr [eax+0xd]
        cmp dl, byte ptr [ebp-0xC]
        jne ir_nx
        dec byte ptr [eax+0xc]
        cmp byte ptr [eax+0xc], 0
        jg ir_nx
        movzx edx, byte ptr [eax+0xe]
        and edx, 0x3f
        mov [ebp-0x18], edx
        xor edx, edx
        mov [ebp-0x1C], edx
        mov ecx, [ebp-0x14]
        mov dl, byte ptr [ecx+0x14]
        cmp dl, byte ptr [eax+0xf]
        jne ir_kill
        cmp dword ptr [ebp-0x18], 0
        jne ir_thaw
        cmp byte ptr [ecx+0x15], 0xff
        jne ir_kill
        push eax
        mov eax, ecx
        mov edx, %(armyid)d
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        pop eax
        jz ir_thaw
        mov byte ptr [eax+0xc], 1
        jmp ir_nx
    ir_thaw:
        mov dword ptr [ebp-0x1C], 1
    ir_kill:
        mov dl, 1
        mov ecx, [eax]
        call dword ptr [ecx-4]
        cmp dword ptr [ebp-0x1C], 0
        je ir_nx
        push esi
        push dword ptr [ebp-8]
        push 0
        push 0
        push dword ptr [ebp-0x18]
        lea eax, [ebx+%(rcb)#x]
        push eax
        push 0
        push 0
        mov ecx, [ebp-0x10]
        xor edx, edx
        mov eax, [ebp-4]
        mov esi, [eax]
        call dword ptr [esi+%(tslot)#x]
        pop esi
    ir_nx:
        inc dword ptr [ebp-0x10]
        jmp ir_x
    ir_ny:
        inc dword ptr [ebp-8]
        jmp ir_y
    ir_out:
        pop edi
        pop esi
        mov esp, ebp
        pop ebp
        ret
    """)
    # NT: call-hook on the only TPlayerMagicControl.NewTurn call (eax = pmc): run NewTurn (Drought's hook and all),
    # then grow the forest for this player's ACTIVE Overgrowth, or (v2) let this player's old overgrowth recede;
    # (v3) World Healer; (v4) Ice Age, or (v5) let this player's old frost thaw.
    # ebx/esi/edi/ebp preserved for the caller.
    place("nt", """
        push eax
        call %(newturn)#x
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
        call %(grow)#x
        jmp nt_heal
    nt_rev:
        call %(rev)#x
    nt_heal:
        mov eax, [esi+0x10]
        mov dl, byte ptr [eax+0xa6]
        movsx edi, dl
        mov ecx, %(hid)d
        call %(oga)#x
        test al, al
        jz nt_ice
        call %(heal)#x
    nt_ice:
        mov eax, [esi+0x10]
        mov dl, byte ptr [eax+0xa6]
        movsx edi, dl
        mov ecx, %(iid)d
        call %(oga)#x
        test al, al
        jz nt_irev
        call %(ice)#x
        jmp nt_out
    nt_irev:
        call %(irev)#x
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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    code, where = build()
    assert ZONE + len(code) <= ZONE_END
    rl = relocs(bytes(d))
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "DIFFERS"
    hooks, cstate = {}, {}
    for nm, (va, orig, kind) in CODE_SITES.items():
        tgt = where[CAVE_OF[nm]]
        h = (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", tgt - (va + 5)) + b"\x90" * (len(orig) - 5)
        hooks[nm] = h
        live = bytes(d[vaoff(va):vaoff(va) + len(orig)])
        old = live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END and all(b == 0x90 for b in live[5:])
        cstate[nm] = "vanilla" if live == orig else "ours" if live == h else "ours(old)" if old else "OTHER"
    vstate = {}
    for nm, (sva, orig, cave) in VMT_SLOTS.items():
        live = struct.unpack_from("<I", d, data_off(d, sva))[0]
        vstate[nm] = ("vanilla" if live == orig else "ours" if live == where[cave] else "ours(old)" if ZONE <= live < ZONE_END
                      else "OTHER(%#x)" % live)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for va, o, _k in CODE_SITES.values())]
    noreloc = [nm for nm, (sva, _o, _c) in VMT_SLOTS.items() if sva not in rl]
    print("code sites %s" % cstate)
    print("vmt slots  %s" % vstate)
    print("zone %s (%d B) | relocs in zone/sites %s | VMT slots without reloc %s" % (zstate, len(code), bad or "none", noreloc or "none"))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        inv = {v: k for k, v in where.items()}
        for i in md.disasm(code[where["oga"] - ZONE:], where["oga"]):
            if i.address in inv: print("  -- %s" % inv[i.address])
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or noreloc: print("ABORT: relocs"); return 1
    if any(s == "OTHER" for s in cstate.values()) or any(s.startswith("OTHER") for s in vstate.values()):
        print("ABORT: a site is owned by someone else"); return 1
    if a.revert:
        if zstate == "zero" and all(s == "vanilla" for s in cstate.values()) and all(s == "vanilla" for s in vstate.values()):
            print("already vanilla"); return 0
        for nm, (va, orig, _k) in CODE_SITES.items(): d[vaoff(va):vaoff(va) + len(orig)] = orig
        for nm, (sva, orig, _c) in VMT_SLOTS.items(): struct.pack_into("<I", d, data_off(d, sva), orig)
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        open(DLL, "r+b").write(bytes(d)); print("reverted"); return 0
    if zstate == "ours" and all(s == "ours" for s in cstate.values()) and all(s == "ours" for s in vstate.values()):
        print("already applied"); return 0
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in list(cstate.values()) + list(vstate.values())):
        print("ABORT: zone not free"); return 1
    new = bytearray(d)
    new[vaoff(ZONE):vaoff(ZONE_END)] = code + bytes(ZONE_END - ZONE - len(code))
    for nm, (va, orig, _k) in CODE_SITES.items(): new[vaoff(va):vaoff(va) + len(orig)] = hooks[nm]
    for nm, (sva, _o, cave) in VMT_SLOTS.items(): struct.pack_into("<I", new, data_off(new, sva), where[cave])
    print("%d bytes change" % sum(1 for x, y in zip(d, new) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(new))
    assert open(DLL, "rb").read() == bytes(new); print("AoWEPACK: written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
