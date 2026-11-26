---
name: eagle-nest-gfx
description: 2026-10-31 Great Eagle's Nest (Release.hss child 282, builders-guild clone) new map art PRO_EAGL.ILB + circling bird + own side image BORDER 205-207; side-window picture = border slots 0x1E-0x20
metadata:
  type: project
---

**APPLIED 10/31, untested** — `patch_eagle_nest_gfx_v1.py` (.bak_eaglegfx Release.hss + BORDER.ILB; art `eagle_nest_art.py`).
- Nest = Release.hss child 282, TBuildersGuildResource 0x2092F (page 43 cell 14). Was vanilla-unused PRO_DRGN.ILB (purple dragon-egg spire) + SMOKE layer.
- New Images\PRO_EAGL.ILB (⚠ NEW file → release --add): ids 0..4 terrain sprites (PRO_DRGN spire recoloured grey, twig nest + perched eagle), ids 10..33 circling-bird anim (layer a1 delay 2 at (-16,-49)).
- **Side-window picture** = structure border images: AoWx TIWindow header 0x44275C calls vmt+0x138/0x13C/0x140 (Top/Middle/Bottom border image) = image-list slots 0x1E/0x1F/0x20 → BORDER.ILB frames (B_* records: 57x2 top, 57x50 filler, 57x278 portrait). Nest pointed at the Teleport's 39-41; now BORDER ids 205-207 (B_Eagle).
- Same patch moved Sanctuary crane layers 5 px up (y -26/-20).

**v2 APPLIED 10/31, untested** — `patch_eagle_nest_v2.py` (.bak_eagle2; art `eagle_nest_art_v2.py`). User rejected v1 (janky nest/mountain join, wanted white birds, more birds, vanilla-style side image, own combat map + window UI, no income).
- Nest ResourceID **0x00E16088** = `[[structure+8]+0xC]` (test used by every cave below).
- PRO_EAGL rebuilt: spire cut at row 31 + stone plateau cap + nest + small perched eagle; birds = 3 white loops on a 64x48 canvas, layer y -49 → -55.
- BORDER 205-207 = vanilla B_ANode (ids 12-14) pinnacles + painted rock shelf + nest + eagles.
- Window icon: CityWin.ILB id 69 I-Eagle (85x102, clone of 66 I-BGuild); AoWx 0x43F7E3 `mov edx,0x42` → .xibn cave 0x611940 'EGL1' (next free .xibn 0x611980).
- Combat map: new TCMaps\Nest0000.hsm (⚠ NEW file → release --add) = NodeE000 with 81 shrub/tree GUIDs swapped for rock decor (record tag `03 04 04 05` before each GUID). TCPCK 0x4249E1 je → cave 0x43EB00 'NST1' (refcount -1 literal + PIC; zone to 0x43EC00). Assumed the structure window background uses the same selector — unverified.
- No income: GetBaseIncome 0x557BE4E0 → AoWEPACK cave 0x558E0300 'EGI1' (next free 0x558E0340).

**v3 APPLIED 10/31, untested** — `patch_eagle_nest_v3.py` (.bak_eagle3 BORDER/comb_res/Nest0000). User: v2 side image "sucks" (wanted ORIGINAL art in vanilla style), combat map good but remove the elemental glow (also seen in the structure window).
- Side portrait = original painting `eagle_nest_side_v3.py` (dawn sky, flat-top crag, nest, eagles, gulls, mist/pines).
- Glow source: map object tag 0x22051C GUID 0x015F5B08 = comb_res child 578 (TCombatStructureResource 0x22051D: zs_fhole.ILB pit + STR_NODE.ILB 250-262 glow). New comb_res child **581** (clone, RID 0x00E1608C) → new Images\TCOMBAT\STRUCT\ZS_NEST.ILB (⚠ NEW → --add; id 0 boulder mound + nest at (-50,-45), birds 10-33 layer a1 at (-64,-75); art `eagle_nest_combat_art.py`). Nest0000 GUID swapped. Object records in .hsm: `03 04 04 05 <guid>` for decor AND structures.
- ⚠ running patch_eagle_nest_v2 dry-run now reports Nest0000 "write" (v3 owns it).
- v3 also re-made CityWin 69 window icon from the painting (window_icon = portrait at 1.5x cropped).

**v4 APPLIED 10/31, untested** — `patch_eagle_nest_v4.py` (.bak_eagle4). User: nest must not overhang the mountain ("mountain top should be wider than nest"); side image + window icon still bad; remove v3 combat mound/birds, centre mostly empty with light vegetation (no trees).
- Map: eagle_nest_art_v2 `_flare` stretches the top 14 rows of the cut spire to a 38-px mesa cap (FLARE_W); nest rx = cap - 8.5.
- Side + CityWin 69 = `eagle_nest_side_v4.py` (cliff running off the right edge, nest on a ledge, rock = vanilla BORDER 14/8 luminance brushwork recoloured). User has rejected 3 procedural side images (v1 polygons, v2 vanilla B_ANode + nest, v3 line-drawn painting) — keep birds tiny, no cartoon eagles.
- Combat: comb_res 581 list → 3 chained ZGR_SHRB shrubs (mode-0 subs work in imgseq), ZS_NEST.ILB DELETED (no longer shipped). Footprint mask (f7) still the node's.

**v5 APPLIED 10/31, untested** — `patch_eagle_nest_v5.py` (.bak_eagle5 PRO_EAGL/BORDER/CityWin/comb_res). User: combat centre = city combat crop/hay; mountains too similar to vanilla → original realistic shape, nest narrower than the top; side image art style bad.
- ⭐ `crag_paint.facet_rock(mask, ...)` = painted-rock look (anisotropic Voronoi planes lit by silhouette-outward normal, sparse cracks via crev_frac, sunlit tops). Noise/blur rock was what looked "bad"; uniform cracks look like honeycomb → blend a big-plane layer (cell 13*SS, crev_frac .45) with a small one (4*SS, .3).
- Map: `eagle_nest_art_v3.py` original butte (top y17, x13..47 = 34 px; nest rx ~7), foot tinted from PRO_DRGN ground colours, frame 4 snow. Still 60x65 PRO_DRGN anchor.
- Side/icon: `eagle_nest_side_v5.py` (v4 composition + facet rock).
- Combat centre: comb_res 581 list = 10 chained ZGR_CROP clumps (frames 0-2) at staggered centres around the node pit centre (~16,31); hex px geometry NOT known — decor in .hsm is nested inside per-hex records (moving decor = stream rebuild).

**v6 APPLIED 10/31, untested** — `patch_eagle_nest_v6.py` (.bak_eagle6 PRO_EAGL/Release.hss/AoWEPACK). User: razed = mountain + broken nest, no birds; builders on top of the mountain; hex must need mountaineering/flying like a mountain.
- PRO_EAGL ids 5-7 = razed crag (map_frames(broken=RAZED_SEEDS), grass foot). hss 282 razed slots 0x16-0x18 → PRO_EAGL 5/6/7 at (-15,-34); rebuild 0x19-0x1B → same + cranes at (-23,-61)/(-5,-62) with high-contrast frames (+20).
- ⭐ Movement RE: hex overlay = first object top-down whose VMT+0x58 GetOverlay(eax=obj, dl=subhex) answers ≥0 (TMapField.Initialize HSEPack 0x5560806C → [field+0x15]; terrain via VMT+0x4C → [field+0x14]). Cost = movsx [mc + terrain*16 + overlay + 0x31] (AoWEPACK callback 0x557454D8; hex flag 0x40 → TMapField.CanMoveOn 0x55608130 loops objects' VMT+0xD0 with a cost record). Mountain overlay 0, hill 2, bare 0xFF, TStructure.GetOverlay 0x5575EBF0 answers 7.
- TBuildersGuild VMT 0x557CA0DC (+0x58) → cave 0x558E0340 'EGO1': Nest → 0 (mountain). Next free AoWEPACK cave 0x558E0380.

**v7 APPLIED 10/31, untested** — `patch_eagle_nest_v7.py` (.bak_eagle7 Nest0000.hsm/AoWEPACK).
- ⭐ TCMaps .hsm decode: object = `<u32 cls> <table: count, (id,off)...> <data>`. Decor 0x220166 table `03 01 00 03 04 04 05` → field1 resource id, field3 x, field4 y. Deployment marker 0x220103: field 0x19 group (absent = 0 = DEFENDERS), 0x1A slot, 0x1B facing?; markers/decor are nested in per-hex records (0x220500) → only same-size edits are safe. Hex index ≈ 49*y + x - 590 in Nest0000. Defenders ring the structure at (32,28) 2-3 hexes out.
- Decor in box x29-35/y26-30 → crop GUIDs (23); leftover trees/pines/dead tree/shrub → rocks map-wide. Structure footprint (comb_res 581 f7 mask) still blocks the centre hexes.
- Flag: TPlayerStructure.Show draws at hex + (res+0x68, res+0x6C) (GenerateFlagPositions presets 0x557619E8; ShowFlag 0x5575A1E8 / ShowStructureFlag 0x5575A34C: pole 9x54 top-left at the point, foot +53). Sites 0x55761002 / 0x55761032 → cave 0x558E0380 'EGF1': Nest uses (25,-69). Next free AoWEPACK 0x558E0440 (cave fix took 0x558E0400).

**v8 APPLIED 10/31, untested** — `patch_eagle_nest_v8.py` (.bak_eagle8 Nest0000.hsm): +1531 crop decor children on every empty playable hex (all units spawn on crops). ⭐ `hsm_grid.py` = .hsm level-0 hex-stream reader/writer (W=65 H=59 for Nest0000; hex = [u32 len][field table: 0x32 base child (cls-1 0x220500 = combat hexagon), 0x33.. objects; tag 4 = a 2-byte field]; round-trip exact). Use it for future combat-map object insert/move (e.g. moving deployment markers 0x220103).

**v9 APPLIED 10/31, untested** — `patch_eagle_nest_v9.py` (.bak_eagle9 AoWEPACK/Release.hss). User screenshot: Nest battle on grey ground, no crop decor. ⭐ Cause: v6's GetOverlay=0 made the Nest's battles mountain-terrain battles; structure-map decor is re-mapped to the battle terrain by comb_res 0x220167 field 17 (terrain group 1 GR/2 DE/3 SN/4 ST/5 WL/12 UG) + field 18 (category; 9 = crops, WL's 9 = graves; f21 maybe density %, SN crops 25) → no crops there → dropped. v9 restores VMT+0x58 (EGO1 cave left as dead code; v6 dry-run now reports a mix) and puts the mountain rule in TBuildersGuild VMT+0xD0 CanMoveOn (TPlayerStructure.CanMoveOn 0x55761428; edx={mc,field,state,slot}, ecx={cost,0,stop}; -1 = impassable) → cave 0x558E0440 'EGM1': cost = max(cost, [mc+terrain*16+0x31]); 0xFF → -1 + stop. Assumes structure hexes carry field flag 0x40 (needed for TMapField.CanMoveOn to run) — untested. Next free AoWEPACK 0x558E04A0.
- Same patch: machine guild art. STR_BLDM/STR_BLDM2 frames 0-2 normal, 3-5 snow, 6-8 desert, 9-11 razed. Frost-blower guilds (produce 0x10A instead of 0xF7) = 692 (correct), 694 (had STR_BLDG on terrains 2-5 + razed) and 286 (STR_BLDM2); 285 Machinereum had snow = anim frame, razed = snow/desert building. 694 ← 692 slots 1-5,12,22-27; 285/286 ← same layout renamed STR_BLDM2.
- Firmament = internal level 3 (order Surface 0, Caverns 1, Depths 2, Firmament 3, Abyss 4..28). Teleporter Z spinner (AoWDevX 0x419714 form, max = map level count - 1) → a map with Firmament allows Z=3.

**v10 APPLIED 10/31, untested** — `patch_eagle_nest_v10.py` (.bak_eagle10 Nest0000/comb_res): user wanted crops ONLY inside the rock ring, every interior hex. ⭐ Decor within ~2-3 hexes of a combat-map structure is not shown (structure clears its surroundings) → interior crops moved into the structure image: comb_res 581 = one ZGR_CROP layer per interior hex (flood fill from the map edge through rock-free hexes, mapgen hexn adjacency; 38 hexes), offsets = Δhex·(32,32) + 16 px for odd columns, decor anchor (-17,-17). Map rebuilt from v7 (v8 outside fill dropped). Combat hex pitch 32x32 (odd columns +16) is an ASSUMPTION from the F5 hexgrid tile — verify in game.
**v11 APPLIED 10/31, untested** — `patch_eagle_nest_v11.py` (.bak_eagle11 PRO_EAGL/Flags.ilb/AoWEPACK): crag repaint (two facet layers cell 5.5/2.4·SS aspect .18/.25, warm-lit (238,226,190) vs violet shade (62,52,88), veg blobs, blur .22·SS); short pole Flags.ilb id 96 (top 30 rows of pole 4); pole pick hooks ShowFlag `mov edx,4` 0x5575A200 / ShowStructureFlag 0x5575A364 → cave 0x558E04A0 'EGP1': caller EBX at [ebp-0Ch], return addr == TPlayerStructure.Show sites 0x5576101B/0x55761046 (PIC two-pass), Nest → id 96; EGF1 flag y -69 → -45. ⚠ keystone: `add ecx, CONST - label` assembles as a MEMORY operand → compute deltas in a 2nd pass. Next free AoWEPACK 0x558E0580 (teleport cave took 0x558E0540).
