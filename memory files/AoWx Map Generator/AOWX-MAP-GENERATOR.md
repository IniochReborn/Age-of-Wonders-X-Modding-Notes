# Age of Wonders 1 — Random / Image Map Generator

*Generate playable AoW1 maps from noise (random terrain) or from a top-down picture, straight
into `.hsm` files the editor and game load. Reverse-engineered + built for the AoWx project.*

Two tools:
- **`generate_map.py`** — procedural random maps (coherent biomes, vegetation, mountain ranges)
- **`image_to_map.py`** — turn any top-down image (satellite, game map, painted colour-key) into a map

Both work on any AoW1 install (vanilla or modded) — they only read `Release/Release.hss` and rewrite
editor-made template maps.

---

## Quick start

1. Put this whole folder anywhere inside your game (e.g. next to `AoW.exe`).
2. Python 3 + Pillow (`py -m pip install pillow`) — Pillow only needed for `image_to_map.py`.
3. From the **game root** run:

```
py "AoW Map Generator/generate_map.py" 12345 M
py "AoW Map Generator/image_to_map.py" "some_picture.png" L
```

Output lands in `Scenario/Custom/` (`xGenerated M.hsm`, `xImageMap L.hsm`). Open in the editor or game.

Args: **seed** (any number, reproducible) and **size** `S`/`M`/`L`/`XL` = 48/64/96/127.
`image_to_map.py` takes **image path** then size.

**Templates**: the four `xTemplate *.hsm` here are empty flood-filled-grass maps at each size.
Keep them beside the scripts. If you'd rather use your own (e.g. with players pre-placed), paint an
empty map that size in the editor and drop it in with the matching name.

**Palettes**: `veg_records.pkl` / `mtn_records.pkl` / `decor_palette.pkl` hold real vegetation &
mountain hexes harvested from maps. They reference `Release.hss` resource UIDs. If your mod changed
`Release.hss` and decor looks wrong, regenerate them for your install:
```
py "AoW Map Generator/build_palettes.py"
```

---

## How it works (and the `.hsm` format, for tool-builders)

### `.hsm` container
`43 46 53 00 02` ("CFS" + version 2) header, then a **zlib deflate stream** (no CRC).
`zlib.decompress(bytes[5:])` gives an **HSS property-object tree**; `b'CFS\x00\x02'+zlib.compress(inner)`
rebuilds it. Round-trips cleanly; the game doesn't care about exact deflate bytes.

### HSS property tables (used everywhere in AoW data)
`[ctrl:u8]` → if `ctrl&0x80` read `nd:u32`; then `(ctrl&0x7F)` byte-pairs `(tag:u8, off:u8)`; then
`nd` dword-pairs `(tag:u32, off:u32)`. **Offsets are relative to the table END.** Records are
`[classid:u32][table][data]`; a children list is `field 1 → a table of (childId → offset)`.

### Map object tree
- inner blob: root property table at **offset 0x13**.
- root child = **TMapContainer** (classid `0x00010103`): tag3 = **width** byte, tag4 = **height** byte,
  tag5 = **level count**, field1 = the levels.
- each level = **TMapLevel** (`0x00020013`): tag3/tag4 w/h, **field1 = the per-hex FIELD STREAM**
  (one blob, W×H consecutive records — not a child table).

### Per-hex records (the payload you edit)
Each record is `[len:u32][payload]`, W×H of them. Payloads:
- **bare hex (14B)**: `01 32 00 <hexChild:11B>`
- **decorated hex (33B)**: `02 32 00 33 0b <hexChild:11B> <decorChild:17B>`

**Child record**: `[classid:u32][ctrl][pairs][data]`.
⚠️ **The stored classid = resource_class − 1** (the MO userclass). Hexagon resource `0x20153` →
store `0x20152`; decor resource `0x20167` → `0x20166`; mountain `0x20169` → `0x20168`. Getting this
wrong = access violation on load.

- **hexagon child (11B)**: `[0x20152][01][01 00][terrainVariantUID:u32]` — field1 = a hexagon-variant
  resource UID from `Release.hss`. The UID's terrain type = its `TTerrainList` (tag7:
  `[count:u32][(terrain:u8, overlay:u8)…]`). Terrain enum: **0 Water, 1 Grass, 2 Desert, 3 Snow,
  4 Steppe, 5 Wasteland, 9 Lava, 12 Dirt, 15 "random land"**. Water/Ice use the animated hexagon
  class `0x2073E` instead of `0x20153`.
- **decor child (17B)**: `[0x20166 veg | 0x20168 mtn][ctrl 03][(1,0)(3,4)(4,5)][resUID:u32][f3:u8][f4:u8]`.
  **f3 = hex X, f4 = hex Y** (baked map coordinates!). Single-hex veg tolerates wrong coords, but
  **multi-hex mountains anchor off f3/f4 — set them to the hex or the sprite draws elsewhere /
  invisible.** Decor resources are named in `Release.hss` (Forest, Trees, Cactus, Pine Tree,
  Mountain…) with their own allowed-terrain list.

The engine computes terrain edge-blending and links adjacent mountain hexes at load, so you only
write raw per-hex types — no transition tiles needed.

### The generator's method (template-rewrite)
Rather than build a map from scratch (players, victory, minimap, camera, AI grids are all
size-dependent and easy to corrupt), it takes an **editor-made empty-grass template**, rewrites only
the interior terrain records, and re-zips. Growing records (adding decor) shifts the file tail, so it
patches 2–3 offsets: the level table's field-1 offset and any later-level container offsets. Decor is
never synthesised — it's **real hex records harvested from shipped maps** (see `build_palettes.py`),
so every decorated hex is a real editor pairing and can't render wrong.

---

## Tuning

- **`generate_map.py`**: `DENSITY` (per-terrain vegetation %), `MTN_FRAC` (mountain fraction), `SEA`
  (sea level), the climate thresholds in `base_terrain()`, and the `make_noise` cell sizes.
- **`image_to_map.py`**: the whole colour→terrain mapping is one small `classify()` function (HSV
  thresholds). Change what grey/urban becomes, enable snow, bias mountains, etc.

Shared by the AoWx project (The Chosen One / Claude), 2026. Have fun — share what you make.
