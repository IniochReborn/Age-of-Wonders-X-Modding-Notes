---
name: poison-plants-wasteland-gfx
description: Poison Plants get the unused withered GND_POIS.ILB image 11 on wasteland (Release.hss slot-5 edit, build_poison_wasteland_gfx.py, 9/21 applied); holds the TILTerrainMO terrain→image-sequence RE and the TImageSequenceList stream format.
metadata:
  type: project
---

**Applied 2026-09-21, awaiting test** (`patch scripts/build_poison_wasteland_gfx.py`, backup `backup\Release.hss.bak_poiswaste`).
User: snow negates poison plants and has its own art; wasteland negates too but showed the live green art.

**RE:**
- `PoisonP.TPoisonPlant` (AoWEPACK VMT 0x557C3A78, ClassID 0x2039E; resource `TPoisonPlantResource` VMT 0x557C3C28,
  ClassID 0x2039F) descends from HSEPack `ILTer.TILTerrainMO` (exports 0x556186F4..0x55618C10). `PoisonPlantActive`
  0x557C3F90: `[self+0x18]` terrain == 3 (snow) or 5 (wasteland) → inactive.
- TILTerrainMO: `[+0x18]` terrain type, `[+0x14]` = GetTerrainTypeImage(terrain) (identity @0x5561883C; TStructure
  overrides) = INDEX into the resource's `TImageSequenceList` `[res+0x20]` (`[res+0x24]` alt list); Show 0x55618940 draws
  that sequence; ValidTerrainType 0x5561873C = "slot exists". TerrainChanged/ChangeTerrain 0x55618888/0x556188D8 refresh.
- **TImageSequenceList stream** (ILPACK 0x552190D8 / TImageSequence.LoadFromStream 0x55218A60): `u32 count; per slot u8
  nil(≠0)`; sequence = Delphi string ILB name, u8, u8, u8 mode, i32 frame, i32 xoff, i32 yoff, [mode 4/5: u32 0, u32 n,
  n×u32 frames], u8 hasSub (chained sequence). Lookups: TImageSequenceList.GetImageSequence 0x5521942C.
- Release.hss holds TWO TPoisonPlantResource records (lists at 0xA78E0 and 0x1A8031; 13 slots; slots 1,2,4,5,12 =
  frames 0..9, slot 3 = [10] snow). GND_POIS.ILB: 0-9 green anim, 10 frozen white, **11 withered dark (was unreferenced)**.
  Release.hss is uncompressed ("4HSS" tree); same-length edits need no size fixups. Decoder/encoder: `modding tools\aowxlib\ilb.py`.
- **Edit:** slot-5 frame lists at file 0xA7A2D / 0x1A817E: [0..9] → [11]×10 (static withered plant).
