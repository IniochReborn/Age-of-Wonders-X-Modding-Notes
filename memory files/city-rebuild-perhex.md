---
name: city-rebuild-perhex
description: 2026-10-18 razed-city rebuild takes 1 turn per city hex (was a hard 5); TCity.GetRebuildInfo RE; patch_city_rebuild_perhex_v1 (AoWEPACK cave 0x55863F80)
metadata:
  type: project
---
`TCity.GetRebuildInfo` 0x557AB50C (VMT +0x1DC) returns cost + turns; vanilla turns = size+1, an old unscripted AoWx in-place edit @0x557AB524 hard-coded 5; cost from cave 0x5580CC40 (25/50/100/250). ExecuteRebuild stores turns in [struct+0x25], NewTurn counts down; CanRebuild + TRebuildConstructionControl UI read the same function. `patch_city_rebuild_perhex_v1.py` (8 B @0x557AB524 → 56-B cave **0x55863F80**, `.bak_rebuildhex`) = count of city-resource terrain entries ([[city+8]+0x28], +4 count, +8 data, 2 B each, byte ≠ 0xFE), min 1. Footprints believed 1/2/3/4 hexes for sizes 1-4 (unverified). APPLIED 10/18, VEH 6, untested. ⚠ 0x55864000–0x55864900 = patch_drought_v1 (next-free-caves memory was stale).
