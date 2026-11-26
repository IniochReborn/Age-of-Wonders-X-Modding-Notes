---
name: map-level-vision
description: "2026-11-22 per-map 'Map Level Vision' (Night Vision required? per level): storage + rules (AoWEPACK) + editor tab (AoWxShot) APPLIED, emulator-tested only"
metadata:
  node_type: memory
  type: project
  originSessionId: 5c12d565-3244-4a28-ba8c-c8f2ac12c9a3
  modified: 2026-11-22T23:20:56.489Z
---

User 11/22: editor Options -> Map Settings gets a tab "Map Level Vision": every map level with a tick "Night Vision required?"; default = existing rule (Firmament 3 / Surface 0 off, all others on). User added: exploration sites always require Night Vision regardless of level.

**APPLIED 11/22 (game + editor closed), emulator-tested only, NOT run in game/editor, not shipped:**
- `patch_levelvision_v1.py` (.bak_levelvision, zone 0x558BAE00..0x558BB000 'LVV1'; `--test`): dword TAoWHSMap +0x480 (InstanceSize 0x5570E858 0x480 -> 0x484), bit L = level L toggled away from the default (0 = old behaviour); stream tag 0x10064, chained on the Ban List cave exit 0x558BA284. `NVREQ` 0x558BAE04 (al = level -> ZF=1 when NOT required, all regs kept, PIC). Rule sites: V1 TAbstractUnit.VisibilityRange 0x55780F32 (was -> engine_v1 cave 0x55851130), A1/A2/A3 the underground attack-penalty caves 0x5580F247 / 0x5580F306 / 0x5580F37F (my choice to make them follow the tick; side effect: Firmament no longer gives those penalties).
- ⚠ LIFO: revert this before patch_banlist_storage_v1 (now reports OTHER), patch_map_levels_engine_v1 or the night-vision caves.
- Editor tab = `aowxshot_levelvision.py` in AoWxShot.dll, called from the Ban List hooks (bl_fcwrap -> lv_build, bl_ok -> lv_store; backups backup\*.bak_prelevelvision); test `test_aowxshot_levelvision_emu.py`. Map = [[0x43289C]] (AoWDevX import AoWE.AoWHSMap), level count [[map+0x10]+0x14], hidden mask [map+0x41C], names NAMEFN AoWEPACK RVA 0x151710. No tab unless InstanceSize == 0x484.
- RE: tactical combat sight (TCombatUnit.GetVisibilityRange 0x55724AD0) halves without Night Vision ONLY when [combat+0x40] == 1 = exploration-site battle (set in TExplorationSite.SetupCombat 0x557C1A17; 2 = default armies); ordinary underground battles never halve. Untouched, which is what the user asked for.
- 11/22 user: tab + rule work in game ("good it works in game"); captions shortened to 'Night Vision required?' / 'Exploration sites always require Night Vision.', list at y30 h336.
- 11/22 editor Fog of War did not follow new ticks: armies CACHE their sight in [army+0x29] (TArmy.UpdateVisibilityRanges 0x5578E10C, run from TArmy.Update 0x5578D1B0). lv_store now calls lv_refresh when the mask changed: TArmy.Update on the army ([unit+4], exact TArmy VMT RVA 0x130EC) of every unit in [map+0xFC]->[+0x10], then TAoWHSMap.UpdateVisibility 0x55778408. Emulator-tested, not yet seen in the editor.
- 11/22 v2 of patch_levelvision_v1.py: InstanceSize now 0x488, second dword +0x484 / tag 0x10065 for editor settings (see [[devx-city-names]]); the editor tab checks 0x488.
- Ship: AoWEPACK.dll + AoWxShot.dll. MP: every player needs it. Next free AoWEPACK cave 0x558BB000 (verify zero).
Related: [[ban-list]], [[map-levels-29-plan]], [[underground-nightvision-atk-penalty]].
