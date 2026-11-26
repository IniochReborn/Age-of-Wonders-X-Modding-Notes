---
name: city-crop-spacing
description: 2026-10-31 city crop spacing RE + "wall of cities" patch (cities may touch; shared crop → city>farm, larger, nearer, placed first) APPLIED untested
metadata:
  node_type: memory
  type: project
  originSessionId: 68556280-d707-4a00-a5ee-7f75589fbb89
  modified: 2026-11-01T01:03:41.515Z
---

**Status: IMPLEMENTED 10/31 (see bottom)** (user: mapmaker wants a wall of cities; no duplicated crop income, larger city gets a shared crop, cities may touch but not overlap; a city hex on another city's crop spot is no crop).

RE (AoWEPACK, Crops unit; city class TCity 0x20108 / res 0x20109, farm 0x2036E / 0x2036F, crop TCrop 0x2036A / res 0x2036B, TPlayerCropStructure classref cell [0x557A55F4]):
- **Spacing limit = TPlayerCropStructure.CanPlace 0x557A6904**: after TStructure.CanPlace (0x5575ECC8, already an AoWx hook → 0x5581B0C0; pad/footprint check = no overlap) it walks every crop offset in the resource's crop pattern ([res+0x74]: +4 word array, +8 count; offsets decoded by 0x55702694 from the structure x/y) and that hex's 6 neighbours (edi 0..6); any TPlayerCropStructure there → refuse. That is the "crop ring + 1" spacing.
- Income: GetIncome = byte [self+0x3C]; UpdateIncome 0x557A6230 → SetIncome(GetCropCount) unless razed/building; **GetCropCount 0x557A6480** counts pattern hexes holding a TCrop whose owner [crop+0x1C] == self → a crop has ONE owner, income is never duplicated today.
- Ownership: TCrop.LinkToCropOwner 0x557A5DAC — radius-1 spiral (0x557026D4) from the crop hex, FIRST TPlayerCropStructure found becomes owner (SetCropOwner 0x557A5CBC) → arbitrary when two cities touch the same crop.
- Crop placement: CanPlaceCrop 0x557A651C (field class 0x20217 relation check, terrain 1..4 / 0xC / 5 needs race 0xB) + TCrop.CanPlace 0x557A5F40 (blocking objects) — a city's pad hex should already refuse a crop (verify).
- Also: CropTrampled / RegrowCrops / UpdateCrops / NeighbourTerrainChanged re-place crops (re-link points).

Proposal given to user: (1) skip the neighbour test in CanPlace (keep the TStructure pad check = touch, no overlap); (2) LinkToCropOwner → choose among all crop structures whose pattern contains the hex: city over farm, larger city size, then nearer centre (hex distance), then lower unique id (deterministic for MP); re-link on city growth/razing/capture; (3) crop spots on another city's pad: no crop (confirm CanPlaceCrop/TCrop.CanPlace refuse). Related: [[eagle-nest-gfx]].

**IMPLEMENTED 10/31 (option A), untested** — `patch scripts/patch_city_wall_v1.py` (.bak_citywall AoWEPACK): CanPlace 0x557A6947 → jmp 0x557A6A09 (neighbour test skipped, footprint kept); LinkToCropOwner entry → cave 0x558E0580 'CWL1' (PIC; crop's own hex holding a crop structure → owner nil; candidates in ring 1 not razed + hex in their pattern; city > farm, size [res+0x78], hex distance (axial q=x, r=y−x/2), lower unique id [struct+0x1C]; fallback first adjacent); UpdateCropSettings call 0x557A63E6 retargeted → LinkToCropOwner (re-check on growth/raze/capture). HSE helpers: InitHNWalk(eax=iter, edx=x, ecx=y, push radius; radius≥1 starts AT ring `radius`, centre not visited; iter +0xC ring, +0x10 x, +0x14 y), WalkToNextHN, TMapLevel.GetField, TMapField.FindNoneTransparentHS(field, classref), CenterHNtoHX(eax=x, edx=y, ecx=code, push &x, push &y). Next free AoWEPACK 0x558E0800.
