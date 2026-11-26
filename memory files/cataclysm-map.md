---
name: cataclysm-map
description: "Cataclysm map (multi-level volcano): level layout, the level-to-level terrain rule, script-edit workflow on the Handover copy; 11/21 volcano lower half v1 APPLIED to the Handover copy, user has not reviewed it"
metadata:
  node_type: memory
  type: project
  originSessionId: 23444023-031b-41a8-8cd6-570f1513bc9f
  modified: 2026-11-21T19:12:37.530Z
---

**Map:** `Scenario\Custom\______Cataclysm.hsm` (127x127, 5 levels) = user's own map in progress; I work ONLY on the copy `______Cataclysm - Handover.hsm`. Theme: a volcano rising through all levels, centre ~(67,63). Display order: Firmament (lvl 3, peak in Sky) / Surface (0, Chasm around) / Caverns (1) / Depths (2 = the real ground: grass/snow/steppe/desert lands around a Chasm moat) / Abyss (4, rock root).

**Level rule read from the user's finished levels (they asked me to emulate it):** under the land of the level above = solid rock/earth (0x20171 uid 2 rock / 1 earth); the ring beyond the upper footprint = open wasteland slope with mountains ~10 % / hills ~5 % / decor ~5 %; lava streams cross that ground and their tips hang over Chasm with fire effects (0x2077f uid 0x21 small / 0x59770ef large, field tag 4 |= 0x20), landing on lakes one level down; lava gets broader each level (fingers -> streams -> lakes). Crater: lava lake on every level, magma-chamber cave network on Caverns.

**11/21 request** "finish the bottom half of the volcano on caverns/depths": `patch scripts\cataclysm_finish_volcano_v1.py` (dry run renders PNG previews; `--apply`; env SEED / FIRE=tips|none|full) APPLIED to the Handover copy (backup `backup\Scenario\Custom\...Handover.hsm.bak_volcano`, result copy `.volcano_v1_result`). Caverns: wasteland between the south-east lava streams (+82 hexes). Depths: shore band + peninsulas around the south/south-east lava lakes (+151 from Chasm, 69 rock crumbs -> wasteland), 2-hex moat kept. Both: decor from the map's own palette, fire on lava tips (39 / 32). No lava removed, no hex with objects touched, no structures/caves added. Not opened in the editor by me; user verdict pending. My reading of "bottom half" (= the lower levels, and within them the still-raw south/south-east parts) is an interpretation.

**Tooling facts:** hex adjacency is COLUMN parity (even x also touches (x±1,y-1), odd x (x±1,y+1)) - a row-parity render misled me at first. Terrain 11 = Chasm (Hu_wl tiles), 14 = Sky. The 8-byte no-uid desert records show as unknown terrain (harmless). Mountain/hill/decor child = 17 B (cls-1, `03 0100 0304 0405`, uid, x, y); multi-hex footprints via Release.hss field 7 (mapgen slots). Bash heredocs mangle backslashes and quotes in long scripts -> write scripts with the Write tool. See [[hsm-map-format]], [[map-levels-29-plan]].
