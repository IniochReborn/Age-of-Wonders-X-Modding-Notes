# HSM map format — objects layer (cities, structures, resources) — 2026-07-31

**Status: DECODED + GENERATOR BUILT (v4), AWAITING IN-GAME CONFIRMATION.**
As-built: `patch scripts/mapgen/harvest_objects.py` → `obj_records.pkl` (verbatim record
templates + patch maps), `generate_map_v4.py` = v3 + object pass (neutral raceless cities with
randomized same-length names, farms near cities, mines near mountains, towers/nodes/explore
sites/misc with AtF-derived densities, water nodes+whirlpools on water; fresh field-98 ids
allocated from & written back to the root-38 counter — **note: counter value tag is 10, not 1**).
Record header parsing: tags 0x32+ = children, tag 0x4 = trailer chunk (bounds last child).
Outputs `xGen4 <SIZE>.hsm`; both S & L walk-validated (stream tiles exactly, names/coords/ids
verified). Water-hexagon templates (animated class) are only placed on water; land placements
restamp static variants of the destination terrain.

v4.1 additions (same session):
- **Roads**: MST over cities + Dijkstra paths. Road child = `[0x20164][{1:0}][road GUID u32]`
  appended to a plain hex record (27B total, header `02 32 00 33 0b`). NO connection mask —
  engine auto-links adjacent road hexes (like mountain ranges). Road GUIDs by terrain:
  grass 0x26, desert 0x15, snow 0x2F, steppe 0x30, wasteland 0x31.
- **Hex adjacency (file coords), inferred from AtF road-hex offset stats**: column parity —
  all of (x,y±1),(x±1,y), plus (x±1,y−1) when x is EVEN, (x±1,y+1) when x is ODD.
- **Racial cities**: region noise assigns races; racial harvested templates (with matching
  field-18 rosters) preferred, else neutral template + race byte (field 13) stamped.
  `RNG_CITY_FRAC` (0.35, user-requested) of cities stay 0xFF so the game rolls a random race
  per playthrough — deliberate replayability mix, confirmed working in-game with the rest.
  ⚠ UNVERIFIED: whether a race-stamped city with the minimal neutral roster blob offers
  that race's units in-game (runtime-derived?) — user to test; if not, transplant roster
  blobs per race (record surgery: lengths differ → header/tbl offset fixups needed).
- Race bytes observed in harvested maps: 0x01..0x0B (+0xFF none); byte↔race-name mapping
  still unmapped (harvested templates keep byte+roster consistent so it wasn't needed).
Groundwork for mapgen v4 (add cities/structures/resources). Extends the terrain-layer knowledge
embedded in `patch scripts/mapgen/generate_map_v3.py` (which documents the container: CFS\0\x02 +
zlib, root tbl @0x13, map child W/H fields 3/4, level stream = field 1 of level child, records
`[len u32][record]` row-major, one per hex; tbl format = `[ctrl b; nd=dword-entries if b&0x80;
nb=b&0x7F][nb×(tag u8,off u8)][nd×(tag u32,off u32)]`, offsets relative to table end).

## Reference conventions
- Map children reference Release.hss registry entries by the entry's **field-1 GUID dword**
  (NOT the registry child-table id). Class id stored in map = hss class − 1 (v3's `child()`).
- Registry: root tbl @0x37 → field5 → field1 = children table; 1142 GUID-keyed entries, 57 classes.
  Entries carry gfx filenames (`.ILB`/`.BMP`) that identify them (no display-name strings in hss).

## Hex record anatomy
`[tbl header {0x32:0, 0x33:…, 0x34/0x35 when more children}] [child]*`
child = `[stored_class u32][tbl][payload]`; payload field offsets from tbl end; field sizes from
offset gaps (last field: usually u32; fields 3/4 are 1-byte x/y).
- Plain hex (14B): hexagon child only (cls 0x20153, field1=terrain-variant GUID).
- Water hexes: cls 0x2073E animated variant; border fill: cls 0x20558 (H_Border), skip via
  the 0x0557 check (v3).
- Veg/mtn (33B): + decor child 0x20167 / 0x20169, fields 3/4 = hex x/y (v3 restamps).
- Roads: child cls 0x20165, field1 = road-type GUID (Rd_gr/sn/st/de/wl per terrain),
  extra u32 field = **connection bitmask** to adjacent road hexes (values like 0x2f). 852 road
  hexes in After the Fall (AtF), 27B records typical.
- Crops/farmland decor: cls 0x2036B guid 0x29 (Crops.bmp), 33B, 446× in AtF.

## Common object-child fields (verified across classes)
| field | meaning | notes |
|---|---|---|
| 1 | registry GUID (u32) | which object |
| 3 / 4 | x / y (bytes) | must match host hex |
| 98 (0x62) | **per-instance unique id** (u32) | monotonically allocated per map; structures + cities have it. Editor's "next id" source unknown — safest: max(all field-98)+1 when adding |
| 6,8,9,10… | class-specific | explore sites: defender/loot lists |

## Cities = PAD child + CITY child on the same hex
- PAD cls 0x20107, guids 0x11–0x14 = PAD1–PAD4.ILB (city size 1–4). PAD alone (no CITY) is the
  base plate for other structures (farm, etc. sit on PAD guid 0x11 + their own child).
- CITY cls 0x20109, guids: 0x16=CITY1, 0x39=CITY2, 0x3A=CITY3, 0x3B=CITY4 (match PAD size).
- CITY child fields (from 46 AtF instances + Slugfest 3P/6P/12P diff):
  - 1 GUID (size), 3/4 x/y, **12 = name as Pascal short string** ("Primas", "Shower Vale", …)
  - **13 = race byte** (0xFF = none: all Slugfest cities are 0xFF; AtF has clustered 3,5,6,7,8,9,0xB
    per region). Race byte values = editor race order (extract exact mapping from game data when needed).
  - 15 = walls level (0–3 observed; Slugfest CITY4 center cities have 2)
  - 16 = 1 (2 on the Slugfest CITY4s — TBD), 22 = 0, 27 = 0/2/3/4 (TBD), 29 = 0x101 (u16?)
  - 18 = variable blob: city upgrades + recruitable-unit roster (unit-type ids inside repeated
    `99 02 02 00 02 14 00 15 04 <id u32>` runs). Copy verbatim from a template city of the right race.
  - 5 = garrison unit count — present only on big records (698–726B) which serialize garrison
    stacks after the CITY child (0x20218 children + unit data, format NOT yet decoded).
- **Ownership & start positions are NOT in the hex stream**: Slugfest 3P vs 12P streams are
  byte-identical; owner/starts live in the map-root player section (root fields TBD — next step).

## Structure vocabulary seen in AtF (= the "legit" generator palette per the user; the hss
registry also contains dev-only structures NOT used in AtF — do not place anything not seen here)
| cls | guid(s) | gfx | what | AtF count |
|---|---|---|---|---|
| 0x20109/0x20107 | 0x16/0x39/0x3A/0x3B + 0x11–0x14 | CITY1–4/PAD1–4 | cities | 46 (32 sz1) |
| 0x2036F | 0x2A | STR_FARM | farm (on PAD 0x11) | 4 |
| 0x2089F | 0x05D311A5 | STR_WTWR | watchtower | 3 |
| 0x20105 | 0x2B | STR_TELE | teleporter | 2 |
| 0x204B4 | 0x24 | STR_NRCK+STR_NODE | power node (rock) | 3 |
| 0x204AF | 0x36 | STR_NODE | power node | 2 |
| 0x204CF | 0x0E56002B | STR_NODE | power node | 2 |
| 0x204BF | 0x3C | PRO_SYRD+SMOKE | node/site | 4 |
| 0x203DF | 0x0A8BF70A | STR_NODE | node | 1 |
| 0x2094F | 0x04F522F4 | STR_NODE | node | 1 |
| 0x20372 | 0x37 | PRO_GROV+STR_NODE | grove node | 2 |
| 0x2063F | 0x01808751 | STR_RF | structure | 5 |
| 0x2092F | 0x0482CFBC | STR_BLDG+SMOKE | building | 5 |
| 0x20101 | 0x0634DC99 | STR_SOL | structure | 1 |
| 0x2089B | 0x06EE5274 | STR_SANT | sanctuary | 1 |
| 0x2032B | 0x08D4DE0D | EPL_DNG2 | dungeon (explore) | 4 |
| 0x2032F | 0x38 | EPL_MONS | monster lair | 4 |
| 0x2038F | 0x04870B74 | EPL_ZIG | ziggurat | 2 |
| 0x2030B | 0x63 | EPL_CASR | ruins | 1 |
| 0x20234/0x2023E/0x2030D | var | A_LIFE/A_LGHTN/A_PEST | altars | 2/1/1 |
| 0x20392/0x20394/0x2039F | 0x42/0x41/0x2D | GNDUHOLY/GND_HOLY/GND_POIS | ground effects | 4/6/4 |
| 0x203AF/0x203BF | 0x2E/var | MISC_OBJ | misc objects | 6/2 |
| 0x2019B | var | (site) | 9 · 0x2043F ×27 · 0x20101… | see catalog |
| 0x20169 | volcano guids | MOUNTAIN\WL_VOLC[LS] | volcanoes (decor) | 2 |

Full inventory dump: scratchpad `catalog_objects.py` (rebuildable). Explore-site records embed
defender/loot lists (191–421B) — harvest verbatim; do NOT synthesize.

## Bridges, rivers, mountain size variants (v4.4, 2026-08-01)
- **Bridge = cls 0x2087B child on a wet hexagon record** — 27 B, header `02 32 00 33 0b`,
  child 1 = hexagon (surface water keeps the ANIMATED 0x2073E class; UG water/lava = static
  0x20153 HU_WA/Hu_la), child 2 = `[0x2087A][{1:guid}]`. NO road child — the engine
  auto-links adjacent roads to bridges (like road↔road). Bridge guids by hexagon terrain
  (from Release.hss + verified across all AoWx maps): terr 0 surface water `0xB3AC32`,
  terr 6 ice `0x56D135E`, terr 9 lava `0x9132B58` (used on surface L0 AND underground),
  terr 10 UG water `0x403557D`, terr 13 UG ice `0x815A375`. Official maps place bridges on
  1-hex-wide crossings (the wet usually continues sideways: 2-4 same-wet neighbors);
  most UG bridges are road-less.
- **Road guid on cave-floor dirt (terr 12) = 0x31** (wasteland road), all levels.
- **BRIDGE DIRECTION RULE (v4.8, found via editor EAccessViolation)**: bridges store NO
  direction in the map record — `HxBridge.THexagonBridge.Create` inits the direction
  byte (+11h) to 0xFF and `UpdateTransitions`/`DirectionValid` compute it on load: a
  direction d (0..2) is valid iff BOTH opposite neighbors (d+1, d+4 via CenterHNtoHX)
  have `AoWE.Land()` terrain (pure terrain test — water/lava fail; mountains/decor are
  irrelevant). If NO axis qualifies, direction stays -1 and `THexagonBridge.Show` does
  `ImageLib.Get(lib, -1)` -> garbage image pointer -> **EAccessViolation in
  AoWEPACK @ +0x99ABA (`mov ebx,[eax]`)** the moment the bridge scrolls into view
  (editor AND game share this code). Generator rule: a wet hex is road-crossable only
  if some opposite-neighbor axis is land-land (`bridgeable()`); standalone/UG bridges
  already required a walkable/floor pair. `check_bridges.py` (scratchpad) validates.
- **Mountain decor size classes** (cls 0x20169, gfx MOUNTAIN.ILB; three guids per terrain;
  classified by isolation stats over all official maps — Large clusters, Small stands
  alone): grass L/M/S = `0xA75015A/0xCBA6DB5/0x809390E`, desert `0x8242C29/0x46/0xF0E0F39`,
  snow `0xDC7534F/0xF/0x628B441`, steppe `0xDD613C7/0x47/0xD95930C`, wasteland
  `0x7DB7950/0xA/0x50368B`; volcanoes (wasteland) `0xECC4395` (large), `0x5C` (small).
  Official maps run **35-48% isolated mountain hexes**; clusters are mostly pairs/triples
  (neighbor histogram ≈ {0: 40%, 1: 40%, 2: 12%, 3+: rare}) — dense noise-threshold blobs
  never appear.
- **HILLS = cls 0x20167 MOUNTAIN.ILB decors** (per-terrain guid trios like the 0x20169
  mountains; passable). NOTE: the veg_records.pkl harvest swept these up as "trees"
  (55-121 of 400 recs per terrain) — v4.5 splits them into their own HILLREC pool via
  decor-gfx check ('mountain' in gfx).
- **TRUE GRAPHIC SIZES (v4.6 — the behavioral L/M/S classification was INVERTED!)**:
  the registry decor entry's field 10 holds [path][…][ILB frame index u32]; field 12/13
  are draw x/y offsets; field 6 (when present) is the editor brush name ("Mountain",
  "Hills"). MOUNTAIN.ILB's image table ([len u32][name.BMP][w u32][h u32]… scan) gives
  per-terrain frames 60x50 / 93x66 x2 / 125x101 / **188x128**. The cluster-happy
  terr-marked guids (0xA75015A etc.) draw the SMALL 60px frame — official ranges are
  many small graphics stacked; the isolation-happy guids (0x809390E etc.) draw the
  **188px giant** whose skirt covers ring 1 + both x±2 side hexes + 2 hexes up. Hex ≈
  60px wide. Size classes by width: S<=60 (1 hex), M<=93 (sliver spill), L<=125
  (covers ring 1), XL=188 (ring 1 + side hexes).
- **FOOTPRINTS DECODED (v4.10 — supersedes ALL radius-based overlap rules)**: decor
  registry **field 7 is the footprint mask**: `[count u32]` then count 2-byte slot
  pairs; slot k covered iff pair != (0xFE,0xFE) ((0xFF,0xFF) counts as covered).
  **Slot order: 0 = center, 1-6 = ring 1, 7-18 = ring 2, directions starting NORTH,
  clockwise** (axial N=(0,-1); ring2 walk starts (0,-2)); validated against all
  official maps (structure-in-footprint minimized: 808 vs 1600-2000 for wrong
  rotations — officials are ~3% sloppy) AND matches the editor's red footprint
  highlight. Examples: grass 125px = {0,1,2,6} = center+N+NE+NW (4 hexes); 188px
  giant = {0..7,10,16} = center+ring1+N2+E2+W2 (the "two side hexes"); snow 125px =
  {0,1,2,6,7,8,18} (7 hexes — footprints are PER GUID, not per size class!); 60px
  mountains & most hills = {0}. Offset conversion: q=x, r=y-x//2; target tx=q+dq,
  ty=r+dr+tx//2.
- **User overlap rules (v4.10, footprint-based)**: structures may sit right AGAINST a
  mountain of any size but never occupy a footprint hex; nothing (veg/rocks/hills/
  roads/bridges) inside any footprint. Enforced: mountain record size chosen at
  write-prep by rolling the wanted size then falling back until the guid's footprint
  avoids all placed/road/bridge hexes; veg+scatter cleared under chosen footprints;
  hills placed via veg restricted to single-hex-footprint guids (93px hill guids have
  multi-hex footprints!). Roads still never run OVER a mountain hex. Validator
  asserts obj/road/decor-in-footprint = 0.
- **UG cities (v4.6)**: placed on every map (not just ELABORATE rolls), count scales
  with carved floor (~1 per 45 floor hexes, 30 when elaborate), spacing 10.
- **v4.4 generation**: rivers flow from high-elevation sources down to the sea (greedy
  descent + momentum), width mostly 1 with widened stretches that narrow back; landlocked
  rivers end in small lakes. Roads may cross exactly one wet hex at a time (wet→wet A*
  steps banned) and write a bridge record there; standalone bridges are also placed at
  narrow river/lava points (opposite-neighbor pair walkable), and underground at wet
  cells with carved floor on an opposite pair (L1+L2). Mountains: cluster-size sampling
  (70% singles, pairs/triples, occasional 4-7 chains) grown along the ridge score, with
  record size chosen by final neighbor count (iso→S-heavy+occasional volcano, clusters→
  L-heavy). Walk-validated S/M/L/XL: streams tile exactly, all records parse, bridge
  guid↔terrain pairs correct on L0/L1/L2.

## Teleporters + ice (v4.11, 2026-08-01)
- **TELEPORTER child cls 0x20105** (STR_TELE; guid 0x2B surface gfx, 0xE5691ED UG gfx):
  fields **3/4 = own x/y, 7/8 = DESTINATION x/y, 9 = destination LEVEL (byte, absent =
  level 0), 10 = 0 (byte)**, 98 = instance id. Destination is arbitrary — need not be
  another teleporter (officials have one-ways and cross-level exits). Two-way pair =
  two teleporters pointing at each other. Teleporter registry footprint = {0,1}
  (center + N). Sanctuary (cls 0x2089B) footprint = {0,1,2,6,7,8,18}; its TOP hex
  (min y, center column) is the user's landing spot for one-way sanctuary gates.
  Verbatim template embedded in generate_map_v4.py (TELE_REC, from After the Fall).
- **AoWE.Land() (disasm @ AoWEPACK)**: NOT land = terrains {0 water, 6 ice, 9 lava,
  10 UG water, 13 UG ice} — ice hexes can host bridges but never count as a bridge's
  land-side axis, and are unbuildable.
- **ICE**: terrain 6 = surface ice (ICEHEX.ILB animated + H_Ic static variants; ice
  bridge guid 0x56D135E); terrain 13 = UG ice (hu_ic.BMP; UG ice bridge 0x815A375).
  v4.11 generation: water near snow freezes (5x5 snow-fraction + noise -> river
  stretches, lakes, shore fringes, with open-water gaps); UG water below surface snow
  freezes at 65% (L1) / 40% (depths), never adjacent to lava.
- **STRUCTURE footprints enforced everywhere (v4.11)**: all placement goes through a
  register() that records each object's registry-field-7 footprint; no object/veg/
  scatter inside another's footprint; roads avoid non-CITY footprints (roads INTO city
  graphics = official gate style); UG furnish/decor get a post-pass (ug_footfix).
  Veg-hills restricted to single-hex-footprint guids.

## Underground levels — DECODED + GENERATED (v4.2, 2026-07-31)
- **Stream framing**: stream = level child's **field 6** data; `s = lb + lf[6]` (level 0 has
  lf[6]=2, underground levels have an extra byte field 5 → lf[6]=3). v3's `lb+2` only worked
  for level 0 by luck. Templates have 3 levels (0/1/2); maps can have 2 (AtF) or 3 (VBV).
- **Solid rock** = hexagon class **0x20171**: EARTHHEX.ILB (terr 7, diggable) / ROCKHEX.ILB
  (terr 8, hard — VBV uses mostly this). Border = 0x20558 as on the surface.
- **Carved terrain** (class 0x20153 variants): hu_ca.BMP terr 12 (cave floor), HU_WA.BMP
  terr 10 (underground water), Hu_la.BMP terr 9 (underground lava — SHARES terr id 9 with
  surface lava; distinguish by gfx prefix `hu_`).
- **Cave entrances = class 0x2037F**. Level transition = PAIRED same-(x,y) children on both
  levels. ⚠ **The GUID encodes WHICH level-pair the entrance connects** (verified across
  AtF/VBV/Slugfest, all pairs use the same guid on both sides):
  guid **0x2C** = surface↔underground (L0+L1) · guid **0x0416D713** (STR_CAVE) =
  underground↔depths (L1+L2). **AND the cave child's field 6 = side flag: 1 on the UPPER
  level of the pair, 0 on the LOWER level** (L0=1/L1=0 for surface pairs; L1=1/L2=0 for
  depth pairs — verified in all three source maps). Wrong guid OR wrong side flag leaves
  half-linked entrances → the editor throws a non-stop "exception occurred during closehsm"
  on close/reopen (map may still appear to play fine). Root-caused in two stages 2026-07-31:
  first Slugfest's L1+L2 records (0x416D713) polluted the harvested L1 pool (guid mismatch),
  then reusing L1-side records for L2 sides left both ends flagged "upper" (side mismatch).
  v4 now stamps both guid (via split template pools) and side flag per placement.
- Underground decor 0x20167: Ug_Rocks/Ug_Vegetation/Ug_Rubble/Ug_Cracks/ca_toad/ca_bones.
  Underground objects seen: mines, cities (distinct cave-city GUIDs, "city0" in harvest),
  CAVEMLAIR, nodes, teleporters, towers, U_brdg bridges, arena.
- **v4 generation** (v4.3 redesign after user feedback — caves were too small/single-entrance):
  cave SYSTEMS, 65% attempted as TUNNELS with two surface entrances 8–22 hexes apart —
  pairs whose surface hex-line crosses ≥2 mountain/water hexes preferred (shortcut under
  the obstacle); obstacle-free pairs still accepted at 45%. Rest are single-entrance
  pockets (12–26 hexes, elaborate 20–45). Separate systems within 20 hexes get flooded
  connector corridors (water 10, or underground lava 9 — elaborate more/lava-heavier;
  35%/60% connect chance). Plus ponds inside systems, mines/lairs/cave-cities/nodes,
  Ug decor 14%. 25% of maps roll ELABORATE. Level-1 splice requires offset fixup of ALL
  later levels (level 2!) — missing this corrupts the map.
- **Depths (level 2, v4.4)**: ~2/3 of L1 systems spawn a DOWN-entrance on their cave floor
  (paired 0x2037F at same coords on L1+L2, same mechanism as surface↔L1). Nearby down-holes
  pair into depth tunnels (60%). Depths are LAVA-HEAVY: ponds 75% lava, connector corridors
  80% lava, denser ponds (div 20). Same furnishing (mines/lairs/nodes; cities when elaborate).
  Level-2 splice offsets shift by BOTH earlier deltas (surface + L1).

## Map root (partially decoded via Slugfest 3P/6P/12P diff)
- **field 21 = player list**: tbl{1,2} → child table, entries id 0..N. id 0 = neutral player.
  Player record class 0x20020, ~20 fields: f2=race (0xFF neutral), f5=starting gold (0x3E8),
  f18=player number (1..N; absent on neutral), f29=1 for real players, f30=known-spells blob,
  f3=0x6 players/0x4 neutral. No start x/y in the player record — starts are player-owned unit
  stacks in the hex stream (the only stream difference between 3P/6P/12P; stack format TBD).
- **field 38 = next-instance-id counter**: `01 0a 00` + u32 (≥ max field-98 in map). Bump when adding.
- field 28 = 4 random bytes (save id?); fields 24/44 = 17947B twins (fog/explored per player? TBD).

## Key play-format fact
Slugfest's cities are ALL race 0xFF (none) + neutral, and the map is fully playable/capturable →
random maps can ship all-neutral cities (Slugfest-style) without decoding ownership or race rosters.

## Unit stacks + player starts (v4.13, decoded 2026-08-02 via Slugfest 3P/6P/12P diff)
The 3P/6P/12P **surface** streams are byte-identical; the differences live in the **L1**
tile stream (Slugfest's starts are underground) + root fields 21/24/44/28.

### Stack child cls 0x20218 (garrisons, wandering parties, player starts — same format)
Appears as the LAST child of a hex record (also after CITY children for garrisons).
`[cls u32][tbl {9:+0, 10:+1}]`; f9 = u8 (3 observed); **f10 = nested stack record**:
- nested tbl, 1-byte fields: **f4 = owning player number (ABSENT on neutral stacks)**,
  **f5/f6 = x/y**, f7 = 1, f8/f9/f10 = 255 (unset color?), f11/f12/f13 = 0,
  **f1 = unit list** = standard child table (tags 0..N-1, same encoding as hex-record
  headers/root-21) of unit records.
- Unit record classes: **0x20214 = regular unit**, **0x20231 = hero**, **0x20233 = leader**.
  Common fields: f2 = unit-type registry GUID (u32), **f5 = per-instance unique id (u32,
  same namespace as field-98 — allocate from root-38 counter)**, f6 = u8 (50; leader 90),
  f47 = 1, f8/f9 = u8 stats, f10 = u16 exp (units) / Pascal NAME (hero/leader),
  f11 = Pascal epithet (hero "the Noble"), f7 = level, f24 = u32 movement (60),
  f3 = ability bitmask blob, f46 = stats blob (leader), f49 = blob,
  f96/f88/f102/f110/f114 = attached sub-records (0x202CF enchantments — Pascal caster
  name inside, e.g. "cast by Gromweyr"; self-referencing the stack's own leader).
- **One leader (0x20233) per player on the whole map.** Extra owned stacks are
  leaderless (hero + units): Slugfest 3P has 4 stacks per player, only one with leader.
- Slugfest 12P start stack composition: leader + hero (same race as leader) + 6 units.

### Root field 21 (player list) — details beyond the earlier notes
`tbl{2:+0, 1:+1}`; f2 = u8 constant 11; f1 = child table entries 0..N (0 = neutral).
Player record cls 0x20021: f2 = race (ABSENT = race 0; 255 = neutral), f3 = 6 players /
4 neutral, **f5 = starting gold u32 (Slugfest scales 3000/N: 3P=1000 6P=500 12P=250;
neutral always 250)**, f18 = player number 1..N, f29 = 1 active / 0 (template default),
**f30 = the player's LEADER unit record** (same 0x20233 shape as in the start stack),
f31 = 26B blob, f32/f33 = 8B ff-blobs, **f53 = relation bitmask blob (bit per player;
self + neutral cleared; template maps have all-zero = default; stale bits for
nonexistent players are harmless — 3P Slugfest still carries 12P bits)**, f58 = blob.
- **Templates (xTemplate *) already contain a valid neutral + 2 default players.**
- Root 24/44 (17947B twins in Slugfest, 29742B in templates): identical across map
  sizes AND player counts — global blobs, safe to leave untouched when changing players.
- Root 28 = 4 random bytes, differs per save (ignore).

### Generator implementation (v4.13, player_kit.pkl via harvest_players.py)
Matched pairs from Slugfest 12P: player record i + player i's leader stack (owner byte
already = i). Generated maps: root 21 rebuilt as neutral + players 1..N (gold patched
to 3000/N clamped 250..1000), each player's stack appended to a clear well-spread
surface hex (`[tbl {32:0,33:0xb}] hexagon(11B) stack`), x/y + all unit f5 ids
restamped (fresh_id), root 38 counter bumped. Root-21 splice shifts all later root
fields: their root-tbl entries are u32 dword entries, patched by +delta (field 21 is
the LAST byte-entry in template roots — asserted). CLI: 3rd arg = player count,
defaults S=4 M=6 L=8 XL=12. Validator: PLAYERS line (declared vs leader stacks,
owner/xy/id checks); 0x20217 whitelisted in KNOWN_STORED.

## Hero library, leaders, city ownership (v4.14, decoded 2026-08-02 via AtF)
Reference maps: "AoWx - After the Fall" (proper hero-library use; Slugfest's heroes
are custom) + "(no heroes)" variant (empty library) + xTemplate (default library).

### Race ids (= HERORES.PFS child order; used by player f2, city f13, hero f12)
0 Human, 1 Azrac, 2 Lizard, 3 Frostling, 4 Elf, 5 Halfling, 6 Dwarf, 7 High men,
8 Dark Elf, 9 Orc, 10 Goblin, 11 Undead. `Release/HERORES.PFS` children: 0-11 =
default racial heroes, 18-29 = generic "Leader" records, 36-47 = racial leaders
(tag 10 = race name, tags 15-20 = ATK DEF DMG HP Move RES, tag 8 = face id).
`Release/HEROES.PFS` = the default 195-entry map hero library source.

### Map hero library = root fields 24 AND 44 (byte-identical TWINS — keep in sync!)
`[tbl{20:+0}][tbl{1:+0}][child table 0..N-1][hero records]`. Template maps carry the
default 195 entries (193 heroes + 2 leader-like "Human"/"Azrac" cls-0x20233 entries).
Removing heroes from a map = removing entries from BOTH tables (renumbered 0..M-1;
AtF-no-heroes has 0). NOT fog/per-player data as earlier guessed.
- Hero record (cls 0x20231, same shape as in stacks): f2 = unit type, f3 = ability
  mask, **f7 = XP (u8)**, f10/f11 = name/epithet (Pascal), **f12 = race**,
  **f8 = HERORES portrait id (= race for heroes, 36+race on leader-like entries)**,
  f15 = gender (1 = female), f16-f21 = skills, f35 = library ordinal, f36/f37 = 257.
  Library entries have NO instance id (f5) / hp (f6) — added when placed in a stack.

### CITY child field 5 = OWNING PLAYER (u8; absent = independent/neutral)
All 12 AtF start cities carry f5 = player number (serialized between f98 and f6);
neutral cities lack it. (Earlier "f5 = garrison count" guess was WRONG.) AtF start
pattern: player's leader stack sits ON their size-1 own-race city hex.

### Leader records (cls 0x20233) + enchantment sub-records
Fresh-leader reference = AtF "Graham" (xp 6): f8 = u32 36+race, f2 = body unit type,
f5 = instance id, f6 = 90 (heroes/units 50), f47 (1-5, varies), f7 = XP, f24 = u32
movement (45), f45 = 7, f46 = 12B current-stats blob `00 07 00 00 00` + 7 values,
f22 = 4, no f11/f18-21/f35. **Player record f30 = the leader's stack record MINUS
its leading class u32** (tbl head like `97 02 00 00 00 08...` = count 0x80|0x17 with
nd=2). Unit/hero/leader **f49 = enchantment list [u32 0][u32 count][count× u32 id]**;
each id also has a sub-record at **field tag = id + 50** (46→f96, 52→f102, 111→f161):
12B `01 20 02 00 ...` blobs, or cls-0x202CF records whose f1a = Pascal caster name
("cast by <leader>") — rewrite the name when cloning units to another leader.
Official hex records holding stacks also carry a small header field TAG 4 (2B, after
the last child) — optional: v4.13/14 maps omit it and work in-game.

### v4.15 corrections (2026-08-02, after in-game test of v4.14)
- **Unit/hero/leader field 47 = OWNING PLAYER NUMBER** — the linkage the engine uses
  to create leaders/units for a player (v4.14 hard-coded 1 → only p1/p2 got leaders,
  p2's from the leftover template lib entry). Neutral units have NO f47.
- **The template's 2 lib entries "Human"/"Azrac" (cls 0x20233, ids 193/194, f47=1/2)
  are the editor's per-player leader roster** — the editor keeps one 0x20233 library
  entry per player; the UI's selectable/editable leader list reads THESE. AtF and
  Slugfest carry 0 lib leader entries (stack+f30 only) and still work in-game, but
  generated maps now write both: lib entry + f30 + stack copy, byte-identical.
- **UNIT-TYPE ID SPACE = Unitres.pfs child ids, organized as 18-slot RACE BLOCKS**:
  Human 0, Azrac 18, Frostling 36, Lizard 54, Elf 72, Halfling 90, Dwarf 108,
  Highmen 126, DarkElf 144, Orc 162, Goblin 180, Undead 198 (NOTE Lizard/Frostling
  swapped vs race-id order); ids ≥ ~216 = shared/raceless. Race-equivalent unit =
  same slot in another block (slot 0 archer, 1 priest, 2 cavalry/scout, 3 basic
  infantry — present for all 12 races with consistent levels; slots 4+ vary wildly).
  City f18 recruit rosters confirm (race r roster ⊂ its block + shared ids).
- Stack unit record state fields: **f8 = current movement, f9 = current HP** (match
  Unitres Move/HP for fresh units), f3 = per-instance state flags (varies between
  same-type instances; `01 00 20 00 00 40` works as a fresh default), f10 = u16
  (exp?, 0 ok). Constructed units: (2,3,5,6,47,8,9,10) suffice.
- **FIELD SIZES ARE FIXED PER TAG — the editor does fixed-size reads, wrong size =
  EAccessViolation (VCL30/AoWEPACK) on open or CloseHSM.** Canonical library LEADER
  entry (0x20233, from template ids 193/194): (8 u32, 2 u32, 3 var, 49 12B enchant
  list [46], 96 12B enchant-46 sub-rec, 5 u32, 6 u8=90, 47 u8=player, **7 u32 XP**,
  10 pascal, [12 u8 race, absent=0], 15 u8, 22 u8=1, 25 u8=0, 36 u32=257, 37 u32=257,
  46 = 5B EMPTY stats list `00 00000000`). NO f16/f17/f24/f45 in the library form
  (those appear only on leveled in-stack leaders like Graham). Library HERO f7 (XP)
  is also u32. First broken build wrote f7 as 1 byte + a 12B f46 → editor crashed;
  generator now clones the template entry and asserts the shape at startup.

### Generator v4.14 (player_kit.pkl v2 via harvest_players.py)
Leader = copy of a random same-race library hero (per the rules above); copied +
15%-case granted heroes are spliced OUT of root 24/44. Party = per-map rolled donor
records (AtF start units: types 112/47/118/74/77/149/125/72), same for every player,
fresh ids, caster names rewritten. Start = owned city (f5 inserted) or independent
own-race city with the stack 2-3 hexes away; equal rolled size 1-4; Lizard-only
small-island starts (< 25 hexes); races 6/8/10 may start on L1 (25% L2), cave city
"ug_city0". Root splice order: 44 → 24 → 21 (offset-desc, u32 root entries patched).

## v4.16 corrections (2026-08-03, from AoWEPACK.dll disassembly — SUPERSEDES earlier
## guesses about unit/hero/leader fields; verified against Slugfest/AtF/template bytes)

Decoded from `AoWE.TCustomAbilityList/TAbstractUnit/TUnit/THero.ReadWrite` +
`TUnit/THero.GetFace`, `TUnitResourceList.GetUnitResource` in AoWEPACK.asm:

- **f2 = ABILITY BIT COUNT, f3 = ability bitmask of ceil(f2/8) bytes**
  (`TCustomAbilityList.ReadWrite`: read u32 count → SetAbCount → read (count+7)>>3
  bytes). f2 is **NOT the unit type** (old harvests keyed by f2 are keyed by a
  bit count!). The old "len(f3) = ceil(type/8)" rule was this, seen sideways:
  writers size the mask to the highest set ability bit. Bit 0 (walking?) is set
  on every genuine unit; bit 46 appears only alongside the f49=[46] enchant.
- **UNIT (0x20214) f10 = u16 UNIT TYPE** = TUnitResourceList positional index
  (= Unitres cid; race blocks Human 0 / Azrac 18 / Frostling 36 / Lizard 54 /
  Elf 72 / Halfling 90 / Dwarf 108 / Highmen 126 / DarkElf 144 / Orc 162 /
  Goblin 180 / Undead 198 stay valid). Invalid index raises "unit resource
  missing (N)". The old "f10 = u16 exp" claim was WRONG — writing f10=0 made
  every constructed party unit render as type 0 = Human Archer.
  Unit f7 = u8 experience (optional), f8/f9 = current move/HP as before.
- **HERO/LEADER (0x20231/0x20233) f7 = u32 FACE INDEX** (R_FACES.ILB via
  TFaceResourceList; ability 0x7E carries an override face). NOT XP! Writing the
  same rolled XP into f7 gave all six generated leaders one identical wrong
  portrait. Lib heroes carry near-unique faces 1..397; template "Azrac" leader
  face 30, "Human" has no f7 (face 0).
- **HERO/LEADER f24 = u32 EXPERIENCE** (object +48h; prop 18h). NOT movement.
  f9 = legacy level blob, only consulted when f24 == 0 (level = (f9>>5)+1 →
  LevelToExperience); never write it. f22 = level. Slugfest leaders:
  f22=5, f24=60, faces all distinct — confirms all of the above.
- **f8 = HeroResourceIndex** (positional in THeroResourceList/HERORES):
  race id for heroes, 36+race racial-leader entries for leaders
  (`THero.LinkToResource(f8)` on load). Same as before — portraits do NOT come
  from f8.
- **Enchant sub-records**: f49 = [u32 0][u32 count][ids]; each id has a
  sub-record at tag id+50. The donor f96 blobs are nested cls-0x202CF records
  ending in a Pascal caster name. The generator's old hardcoded unit f96
  (`ce020200020a000b01022e00`) was a TRUNCATED 0x202CF (no caster name) →
  editor EAccessViolation on open + crash on close (xDiag F/H). Fresh
  constructed units now carry NO f49/f96 (xDiag G proved clean).
- Slugfest 12P: player f30 leader and the placed stack leader share ONE
  instance id (byte-identical records); template: f30 == lib entry (ids 1/2).
  So lib + f30 + stack sharing one id (generated maps) matches both precedents.
- Generator v4.16: `ab_masks.pkl` (harvest_abmasks.py) = smallest enchant-free
  official instance mask per unit type (40/48 party types covered; fallback
  slot patterns 0+22 archer / 0+20+47 priest / 0+21 melee / 0+21+111 rider).
  make_unit writes f10=type; make_leader copies the hero's f7 face and sets
  f24=XP, f22=1; hero_stack_rec keeps lib f7 and replaces/inserts f24=XP.

## v4.17 corrections (2026-08-03, after user test of the v4.16 maps: portraits/
## units/XP all correct; leaders showed "Free"; copied multilevel abilities lost
## their levels)

- **Leader roster "Used"/"Free" (LeadrGrd.TLeaderGrid.DrawCell): status = the
  player's leader object (TPlayer+0xD4) having a non-nil PARENT (+0x04)** — i.e.
  the leader sits in a stack's unit list = placed = "Used". `TLeader.Activate`
  hooks a loading leader into players[f47].Leader; a "Double leader used"
  exception is raised but CAUGHT AND IGNORED, so **the LAST activated 0x20233
  wins the slot**. Library entries (root 24/44) load after the map levels, so
  writing per-player lib leader entries (v4.15/16) clobbered the placed leaders
  → whole roster "Free". **A lib 0x20233 entry means "free/unplaced leader" —
  never write one for a placed leader.** Official maps never mix: template =
  lib-only (both Free), AtF/Slugfest = placed stack + f30 only (Used).
  Generated maps now carry NO lib leader entries (template's default pair
  dropped, nothing appended); v4.15's "editor's selectable leader list" reading
  of the template pair was wrong. TPlayer.ReadWrite streams f30 into a SCRATCH
  leader (+0x58), not into player.Leader, in the editor path.
- **Multilevel ability LEVELS live in the f49/f(id+50) sub-records** shared by
  the enchant mechanism: hero/leader f49 = [u32 0][u32 n][n× u32 ability id];
  each id has a 12-byte sub-record at tag id+50, `01 20 02 00 02 0a 00 0b 01
  <level> <id> 00` (cls 0x22002-style; enchant-46's uses cls marker
  `ce 02 02 00` = 0x202CF). Examples: Spellcasting=52→f102, id 0x70=112→f162
  (level byte 03 = "III"). Template leaders' f96 = id 46 level 1 = the default
  "Leadership I" — that's why Leadership leveled correctly while hero-copied
  abilities (whose sub-records make_leader dropped) showed unleveled and cost
  no skill points. make_leader now merges: f49 = [46]+hero ids, sub-records =
  template f96 + hero's id+50 blobs verbatim; mask bit 46 set (count bumped to
  ≥47 with mask re-sized to ceil(count/8)).
- Library HEROES also carry these (f49 + id+50 blobs) — hero_stack_rec copies
  them verbatim already.

## v4.18 additions (2026-08-03)
- **Leaders copy same-level heroes**: hero level = lib f22; LEADER_LVL rolled
  once from levels every present race can supply (all races have lvl 1 + lvl 5;
  2-4 have gaps), weights 45/25/15/10/5; leader f22 = the copied hero's level.
- **SIGN records**: child cls 0x20103 (STR_SIGNS guids 0x17F973E/0x69),
  **f7 = [u32 len][text]** — generator now writes location-relevant text
  (city name + compass direction via pre-rolled CITY_NAMES, nearby-structure
  flavor, terrain warnings, generic filler); record rebuilt via
  rec_children/enc_record since text length changes.
- **Missing structures added** (harvest_extra.py → obj_extra.pkl, scans ALL
  official maps): surface Arena STR_AREN (0x604881B/0x288863/0x777B46F, x58),
  Blood Shrine STR_BLDS (0xCDE791A/0xBCB5493, x91 — description string in
  Release.hss confirms "blood shrine increases units' attack and damage"),
  Reflecting Pool STR_RF (0x1808751/0x8A2A872, x288), Shipyard PRO_SYRD
  (guids 0x3C/0x6B, cls 0x204C0 — production-node family, x1010, coastal
  placement pred). **Builder's Guild #2 = STR_BLDM guid 0x0441CED6 (user's
  "resource id 71421654" decimal; #1 = STR_BLDG 0x0482CFBC = 75681724) appears
  on NO official map** — records synthesized by cloning STR_BLDG guild records
  and swapping the guid (same cls 0x20930; registry footprint via FOOT).
  STR_BLDM2 (0x3DAC00B/0x8A758CC) also exists in the registry, unused.
  All five join the misc rotation ('building+pad1'/'building2+pad1'/
  'blds+pad1'/'pad1+str_rf'/'aren+pad1' + coastal 'shipyard').

## v4.19 corrections (2026-08-03, from AoWEPACK disassembly + user feedback)
- **Player record f3 = TPlayerType**: 0 Human, 1 CPU Warrior, 2 CPU Knight,
  3 CPU Lord, 4 Independent, 6 CPU King, 7 CPU Emperor (Slugfest: players 6 =
  King, neutral 4 = Independent — the old "f3 = 6 players / 4 neutral" note
  was this enum). Generated maps: always 7 (Emperor).
- **Player record f29 = TPlayerBehavior** (byte at TPlayer+0xA8, indexes
  Player2GroupBehaviorTable in TAIPlayerControl.GetRandomGroupBehavior):
  0 pbNormal, 1 pbAggressor, 2 pbDefender, 3 pbExpander, 4 pbScorcher,
  5 pbRandom. NOT an "active" flag (old guess) — Slugfest donors carry 1 =
  the "always Aggressive" default. Generated: 60% Normal / 10% each 1-4.
- **Builder's Guild**: vanilla = STR_BLDG guids 0x0482CFBC (surface, dec
  75681724) + 0x039F9C6A (underground, dec 60791914). STR_BLDM 0x0441CED6 /
  0x0DD559CF (dec 71421654 / 232085967) are MOD-added and unwanted — filtered
  from the palette; ug_building+pad1 added to the UG furnish rotation.
- foot_clash now rejects land placements whose graphic FOOTPRINT covers water
  or leaves the map (a size-3 city with 2 footprint hexes on water rendered
  glitched/invisible); shipyards pass water_ok. Farms keep out of city
  footprint + 2 rings (farm crops must never share a hex with city crops);
  signs keep out of footprint + 1 ring (they replaced city crops).

## v4.20 (2026-08-03): city walls + defender strength
- **CITY child f15 = WALL TYPE**: 0 None, 1 Wood, 2 Stone, 3 Random
  (City.TCity.SetWallType writes +4C = ReadWrite prop 0x0F; TWallType enum
  wtNone/wtWood/wtStone, editor combo adds Random=3).
- **CITY child f27 = DEFENDER STRENGTH**: 0 None, 1 Random, 2 Weak,
  3 Average, 4 Strong (editor DefendersCB writes +74 = prop 0x1B).
  Both were misread as bools earlier; harvested records carry f15=0/f27=3
  (no walls / average) which the generator used to clone verbatim.
- Generator: per-city rolls (walls 40/20/15/25, defenders 10/25/20/25/20);
  ALL player spawn cities (surface + UG, both IN-city and NEAR modes) share
  ONE roll for equal starts (stamp(wd=) patches the bytes in place).

## v4.21 (2026-08-03): structure defender strength
- **Defender mode value space (all defended structures): 0 none/user-defined,
  1 weak, 2 average, 3 strong, 4 random** (GenerateDefenders rolls 1-3 on 4;
  budget = (mode-2)*25+25 gold for production places).
- **TExplorationSite family → child TAG 6** (mode byte at +30; editor site
  dialog writes ItemIndex+1): dungeon 0x2032B, monster lair 0x2032F, ruins
  0x2030B, crypt/EPL_CAS2 0x2039B, ziggurat 0x2038F. Tag 5 = user-defined
  defender unit list (used when mode = 0). CAUTION: cave entrances (0x2037F)
  also have a tag 6 = SIDE flag — never touch by tag alone, always by class.
- **TProductionPlace family → child TAG 9** (mode byte at +49;
  TProductionPlaceEditForm writes raw ItemIndex): Builder's Guild 0x2092F,
  Shipyard 0x204BF (tag 8 = defender list obj). TArena = plain TStructure
  (no defenders); blood shrine STR_BLDS has neither.
- Generator rolls mode 1-4 (25/30/20/25) per structure in stamp(); city walls
  reweighted 25/25/20/30 (v4.20's 40%-none + one shared spawn roll made maps
  with zero walls likely). Editor note: a city's Defenders dropdown is greyed
  when the city has an OWNER — the setting only drives independent-city
  garrison generation.

## Open questions (next steps)
1. Unit-stack record format in hex stream (player-owned starts, garrisons, wandering monsters).
2. City ownership encoding (likely stack/garrison-related in the big 698B city records).
3. Race byte ↔ race mapping; per-race recruit-roster blobs (field 18) if racial cities wanted.
4. Underground (level-1) stream framing.
5. City name (field 12) is a Pascal string mid-record: same-length replacement avoids shifting
   later field offsets in the child tbl.
