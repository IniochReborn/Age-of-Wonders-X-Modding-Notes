---
name: underground-terrain-variants
description: 2026-10-31 community suggestions (Neutrinos Touch): structures + cave mouths on surface terrain (snow) underground should use that terrain's art; cave part APPLIED, structure part open
metadata:
  type: project
---

**Cave mouths — APPLIED 10/31, untested:** `patch_cave_underground_terrain_v1.py` (.bak_caveug AoWEPACK/Release.hss). TCave.GetTerrainTypeImage 0x557B361C: surface mouth slot = terrain, underground mouth = terrain+30 → surface terrains 1..5 underground hit slots 31..35 = BORDER tags (cave "disappears"). Now underground on 1..5 → slot 50+terrain (cave 0x558E0400 'CVU1'); all four TCaveResource (0x2037F) records got slots 51..55 = copies of 1..5.

**Structures — APPLIED 10/31, untested:** `patch_ug_structure_terrain_v1.py` (.bak_ugterrain Release.hss). Real cause: the underground Release.hss records only carry slots 10..13 (11/12 art); on underground surface terrain (slots 1..5) they had nothing. 21 records (216-259 underground nodes/mine/teleporter/blood shrine/arena/pool/keep/dungeon/lair/crypt/guilds/shipyard/tower fort/wizard tower, 286 Machinereum-art guild <- 285, 702 sign) got slots 1..5 copied from the same-class full-set record (prefers same ILB, then same description). Skipped 229 Sanctuary, 238 Water Node; 696/697 underground gems/crystals have no twin.

**Earlier notes (structures):** TStructure.ForceTerrainType (VMT +0x130, 0x5575E93C, TCave inherits it) returns 0xC (underground dirt) whenever [edx+8] (level) != 0 → underground structures are forced to dirt art. TerrainChanged 0x5575EC80: if res+0x44 → [struct+0x18] = terrain, image = vmt+0x12C GetTerrainTypeImage(terrain) (TStructure entry is our gfx cave 0x5580C390, slot = terrain via 0x5570353C). Next: find who calls +0x130 for structures (HSE placement / terrain paint) and its args (edx = pos rec, cl, push byte), then let underground structures keep land terrains 1..5 when the hex is painted with them. Related: [[tunnel-cave-structures]], [[eagle-nest-gfx]].
