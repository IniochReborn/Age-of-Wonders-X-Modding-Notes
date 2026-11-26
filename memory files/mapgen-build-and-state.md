---
name: mapgen-build-and-state
description: "AoWxGen map generator — source layout, how to edit/test/rebuild the exe, current version (v6.4, mushroom groves on UG grass)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-13T00:17:06.094Z
---

**AoWxGen (random map generator) — current v6.4 (2026-08-09).**

SOURCE (`patch scripts/mapgen/`):
- `generate_map_v4.py` (~140KB) = the generator. Internally versioned v4.x AND
  the portable-release v6.x line. Loads its data (`*.pkl`) from its own dir;
  loads templates `Scenario/Custom/xTemplate *.hsm` and writes
  `Scenario/Custom/xGen6 <SIZE>.hsm` relative to CWD. argv = seed, SIZE(S/M/L/XL),
  [players]. Env forcing: `AOW_XLEVEL=off|limited|full` (terrain inversion),
  `AOW_LEVELS`, `AOW_LANDMASS`, `AOW_TPRESET`, `AOW_TSTRENGTH`.
- `aowx_mapgen_launcher.py` = the menu front-end; `VERSION` constant here
  (bump on release). runpy's the generator in-process.
- `validate_map.py`, harvest_*.py (data harvesters), image_to_map.py.

TERRAIN CODES (grid values): 0=water,1=grass,2=desert,3=snow,4=cold/steppe,
5=rock,6=ice,9=lava,12=dirt/cave-floor,13=UG-ice,10=UG-water. UG_LAND=(12,1,2,3,4,5).

TEST FROM SOURCE (fast, no rebuild): from game root,
`AOW_XLEVEL=limited py -3.10 "patch scripts/mapgen/generate_map_v4.py" <seed> L`
→ prints summary incl. the `xlevel: ... (sunlit N, M mushroom-grove | ...)` line.

REBUILD THE EXE (PyInstaller 6.x available on py-3.10; run from GAME ROOT — do
NOT pass --specpath, it breaks the relative --add-data paths):
`py -3.10 -m PyInstaller --onefile --console --name AoWxGen --noconfirm
 **--icon "reference files/aowxgen.ico"**
 --distpath ./_gendist --workpath ./_genbuild
 "patch scripts/mapgen/aowx_mapgen_launcher.py"
 --add-data "patch scripts/mapgen/generate_map_v4.py;."  (+ validate_map.py,
 image_to_map.py, each of the 9 *.pkl individually, and the 4 xTemplate *.hsm
 ;templates)`.
⚠⚠ **ALWAYS PASS `--icon "reference files/aowxgen.ico"`** — the v6.4 rebuild
(2026-08-09) omitted it and shipped with PyInstaller's default icon; user spotted
it 2026-08-11 and it was rebuilt (pre-fix copy kept as `.AoWxGen.exe.bak_noicon`).
The 9 pkls are: ab_masks, decor_palette, mtn_records, obj_extra, obj_records,
player_kit, unit_pool, veg_records, _img_override. Verify afterwards by checking
the .ico's largest image blob appears in the exe bytes (PE dir parsing needs the
PE32+ layout — these exes are 64-bit). Sibling icon: `reference files/bard_icon.ico`
— ✅ the shipped `.AoWxBard.exe` ALREADY carries it correctly (verified
2026-08-11; an earlier claim that it did not was a false negative from probing
it with the *wrong* .ico. **When testing "does exe X have icon Y", probe with
Y's own bytes.**) Do not rebuild the Bard just for its icon.
**Explorer showing a stale icon ≠ a missing icon:** if the taskbar/running app
shows the new icon but Explorer shows the old one, that is the Windows shell
icon cache (keyed by path, survives same-name replacement). Fix with
`ie4uinit.exe -show`; if it persists, delete
`%LocalAppData%\Microsoft\Windows\Explorer\iconcache_*.db` and restart explorer.exe.
Then deploy `_gendist/AoWxGen.exe` → `.AoWxGen.exe` (game root; leading dot!),
clean `_gendist/_genbuild`. The exe BUNDLES generate_map_v4.py — a source edit
does NOT reach users until rebuilt. exe auto-finds root via Release/Release.hss
in parent dirs. Smoke-test: `printf '2\n2\n2\n\n2\n\n\n' | ./.AoWxGen.exe`
(custom / M / surf+UG / players-blank / limited / defaults) → expect
"version 6.4" + "validation: OK".

**v6.5 CHANGE (user spec, 2026-08-12):** the CLASSIC landmass preset had too
much ocean; wanted "one giant landmass separated by large rivers, sometimes
oceans but not always". Isles/continents untouched (user: they're good). All in
`generate_map_v4.py`, guarded on `LANDMASS == 'classic'` so other presets keep
their exact RNG streams:
- `_LM['classic']` 20.0 → **28.0** (bigger elevation cells ⇒ land coheres).
- Water share is now **BIMODAL** instead of one flat range: 55% roll
  (0.09,0.19) = river-continent, else (0.21,0.32) = a real sea. Replaces
  `_WQ['classic']` (0.28,0.44) — that flat range averaged out the variety.
- `_LM_RIV={'classic':2.2}` river budget ×2.2 and `_LM_SEP={'classic':9}`
  (source spacing 12→9; the old spacing capped the count far below budget).
- `_WIDE_P` 0.12→0.20 and `_WIDE_L` 6→7 for classic; width roll 1/2/3
  (45/40/15%) instead of 1/2 (70/30). ⚠ Rivers MUST keep narrowing back to
  1 hex — single-hex points are the only legal bridge/road crossings
  (`bridgeable()` / THexagonBridge.DirectionValid).
MEASURED (L, 6 seeds): classic sea **14.9%** mean (3.5–22.5 range) + 12.7%
river, 17 rivers — vs continents 34.1% sea / 4.5% river / 6 rivers. River count
by size: S 2, M 6, L 17, XL 26; bridges present at every size; validation OK.
⚠ Menu text stays **"Classic - Default landmass generation."** — I reworded it to
describe the new behaviour and the user reverted that: the preset descriptions
name the preset's ROLE, not its current tuning. Don't re-edit them.
Backup of the prior exe: `.AoWxGen.exe.bak_v64`.

**v6.4 CHANGE (user spec):** limited terrain inversion grows MUSHROOM GROVES on
underground grass. In generate_map_v4.py `elif UG_SURF == 'limited':` branch:
UG grass cells (t0==1) are collected into `ug_grass`; a grove pass seeds
mushrooms (`_MUSHREC`) on ~45% of them then spreads at 70% into adjacent grass
×4 iterations → dense clusters. `nmush` counter added to the xlevel summary.
Non-grass UG terrain keeps the old occasional mushroom/dead-tree (30%/60%).
Backup of prior exe: `.AoWxGen.exe.bak_v63`. Changelog: `upload/AoWxGen changelog entry.txt`.
Related: [[mapgen-no-regen-after-changes]], [[hsm-map-format]].
