---
name: road-build-cost
description: "Road-building (Construct/Build Road) cost: was flat 10, now per-tile by decoration — open/light/bones=2, rocks/toadstools=3, veg/dense forest=5. AoWEPACK.dll. CONFIRMED WORKING in-game."
metadata:
  node_type: project
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-24T01:51:15.072Z
---

## DECORATION-DEPENDENT ROAD COST (CONFIRMED WORKING in-game; backup AoWEPACK.dll.bak_roadveg_final)
**Cost per road tile:** open ground=2, light vegetation=2, bones=2, **rocks=3, toadstools=3**, **Vegetation/Dense tree forest=5**. (Vanilla was flat 10; interim flat 5 = backup bak_roadveg / bak_roadcost.)

**Signals per hex (Ghidra + many in-game diagnostic rounds):**
- **[field+0x15] = cached overlay byte:** open/transparent=**255**, Light Veg=**9**, Vegetation & Dense (trees)=**1** (Veg & Dense share 1 — NOT separable; user accepted "tree forest = 5").
- **Decoration object** on the hex = a **TAoWTerrain MO** found by matching its **MapFieldMsgProc == 0x5579BE0C** at **vtable offset +0xCC** (this is how the engine's SendMapFieldMsg @HSEPack 0x55607944 dispatches — iterate children [field+8], count byte[field+0xd], child=[[field+8]+i*4], handler=[[child]+0xCC]). ⚠️ FindChild/FindNoneTransparentHS do NOT work (match by class +0x24 / is-a, which the veg MOs override or mismatch).
- **[MO+8] = resource; [resource+0x44] = decoration category:** trees=**0**, rocks=**1**, bones=**2**, toadstools=**4**. (This is decoration type, NOT density — all veg trees=0 regardless of Light/Veg/Dense.)
- Dead ends (do not retry): [resource+0x48]=combat tag (varies by BASE terrain, dense IDs overlap light's e.g. both hit 4 on snow); GetTerrain(list)=base terrain; GetOverlay=overlay value (1 for veg&dense); GetConcealmentActive=always 0 here. The editor's "overlay terrain type" (Light=25/Veg=19/Dense=17) is NOT stored in any per-hex-readable field.

**cave_roadcost logic (field in eax → cost 2/3/5 in eax):** overlay==9→2; overlay==1→5; else find deco MO (msgproc match) → none→2; cat==1(rocks)→3; cat==4(toadstools)→3; else(bones/other)→2.

**IMPLEMENTATION (all PIC-safe; caves @0x5580F700+; backup bak_roadveg_final):**
- **cave_roadcost @0x5580F700** (~117B): the classifier above; preserves edx/ecx/ebx/esi/edi/ebp. MSGPROC 0x5579BE0C computed via call$+5/pop/sub/add delta-trick.
- **cave_pred @0x5580F790**: hook pred adder @0x55771195 (`83 44 24 04 05`→`e8 →cave_pred`); field=[esp+0xC], `add [esp+8],cost`.
- **cave_capA @0x5580F7B0**: hook @0x557710B6 (`8a 4e 10 8b 30`→`e8`); field in esi (valid only until 0x557710B9!) → roadcost → store to scratch **SC=0x558FA800 (writable BSS! not code — a code-section scratch was the original crash)**; replay mov cl,[esi+0x10]/mov esi,[eax].
- **cave_capB @0x5580F7F0**: hook @0x557710D8 (`0f be f3 8b d6`→`e8`); replay movsx esi,bl/mov edx,esi; ebx=[SC].
- **edit @0x557710F3**: `83 e8 05`→`2b c3 90` (sub eax,ebx = charge per-tile cost).
- To change a cost: edit the imm in cave_roadcost's `mov eax,N` (c5@~0x5580F75B / c3@0x5580F762 / c2@0x5580F769) or retarget the `je` for a category (e.g. toadstools 5→3 was retargeting the cat==4 `je` from c5 to c3 @0x5580F758).
SC scratch is transient (capA writes, capB reads, same tile) → MP-safe. Prediction & actual use the same cave_roadcost so the UI preview always equals gold charged.

## RE reference (road system)
Charged per buildable tile (buildable helper FUN_55770ff0 @0x55770FF0: base terrain [field+0x14]∈{1..5}, overlay∉{0,2,4,5}, no TStructure MO). Actual road-construct fn @0x55771068 (field in esi until 0x557710B9, player idx ebx/bl until 0x557710D8, charge `sub eax,gold` @0x557710F3). UI prediction path-walker FUN_55771138 (field [esp+8], adder @0x55771195) fills `ConstructingRoadCostsXRStr` @0x5570777c (formatted @0x55792AE5). TSelectedArmy.SelectBuildRoad @0x55793B98 (UI targeting). GetMapObjectByClass thunks: FindChild @0x55701FEC, FindNoneTransparentHS @0x55702004 — both return children from [field+8] but match wrongly for veg (use the MapFieldMsgProc method above instead). GetTerrain thunk @0x55701c8c.
