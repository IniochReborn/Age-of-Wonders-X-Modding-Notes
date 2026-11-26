---
name: ug-dirt-roads
description: 2026-11-04 roads on underground dirt (terrain 0x0C) = Ziggurat Release.hss child 1126 copied (rid 0x5A190001, page 6 cell 37); combat already has a 0x0C TCombatRoad; APPLIED untested
metadata:
  type: project
---
`build_ug_dirt_road_hss_v1.py` (.bak_ugroad) APPLIED 11/04, untested. Roads are pure data: HSE TAbstractRoad.CanPlace
(0x5560A820) requires [field+0x14] == the road resource's field-7 terrain (u32 count, u8 terrain, u8 overlay 4); placed
road sets [field+0x15] = 4. Vanilla TRoadResource (0x20165) records: terrains 1-5 (cells 0,1,2,3,5). Ziggurat added the
Wasteland road (Rd_Wl art embedded) keyed to 0x0C - copied verbatim, same rid/cell so Zig maps load.
Combat: comb_res already has TCombatRoad 0x220503 rid 0xDE69F39 terrain 0x0C (UG combat page 0x1D cell 1, H_STDR art);
AoWTCPCK generator 0x425353 lays roads when [field+0x15]==4 via road control [[0x46E8D0]+0x90] vcall +0x50 - so UG
battles on a road should show road tiles with no comb_res change (verify in game). Untested: in-game Build Road
(TSelectedArmy.SelectBuildRoad 0x55793B98) on UG dirt. Road palette page 6 cells now used: 0-8,12-16,20,21,24-28,32,33,36-41.
Related: [[map-levels-29-plan]], [[comb-res-lost-records]].

**Construct on UG dirt (11/04, APPLIED untested):** `patch_build_road_ug_v1.py` (.bak_ugbuildroad): AoWEPACK 0x55770FF0 =
can-build-road-on-field (terrain [f+0x14] in 1..5, overlay [f+0x15] not 0/2/4/5, no blocking structure; used by
road-build cost 0x55771138 and placer 0x55771068) - site 0x55771018 -> cave 0x558E0E00 'URB1' also accepts 0x0C.
Ziggurat does NOT patch this (its construct can't build UG roads). Next free AoWEPACK 0x558E0E40.
**Part 2 (11/04, APPLIED untested):** `patch_build_road_ug_v2.py` (.bak_ugbuildroad2): Construct ability CanActivate
0x55770EAC refused every level != 0 ("Cannot build %s in underground", the only use of CannotBuildXInUndergroundRStr)
-> jne @0x55770EE9 NOPed. Now ALL levels (Caverns/Depths/Firmament/Abyss) allowed; where a road may go is decided by
the per-field terrain check (surface 1..5 + 0x0C; Sky 0xE / Chasm 0xB / rock refused). User also wanted Firmament.
