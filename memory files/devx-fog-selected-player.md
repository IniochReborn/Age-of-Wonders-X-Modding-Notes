---
name: devx-fog-selected-player
description: "2026-11-22 editor Fog of War shows the vision of the player picked in the Players menu (AoWxShot in-memory hooks); APPLIED, emulator-tested only"
metadata:
  type: project
---

User 11/22: editor Fog of War always showed Independents' vision; wants the player selected in the Players menu.

RE (AoWDevX): fog is drawn for the map's SEATED player byte [map+0xA5] (DrawFog); the editor sets it to 0 once at map open (0x4211CE, map VMT+0xF8). Players menu = DefaultPlayersMI [form+0x57C], rebuilt at 0x428979, items' Tag = player index, shared OnClick 0x428944 stores the pick in byte [map+0x190] (`mov [edx+0x190],al` @0x428964). FogofWarClick 0x42BB64 -> `call [ecx+0x100]` @0x42BB94 = SetFogEnabled ([map+0xC8] + InvalidateMap only on change). Map VMT: +0xF8 SetSeatedPlayer (-> TPlayerControl.SetSeatedPlayer 0x557559C8, also recentres the view on the leader - not used), +0xFC SetCurrentPlayer ([map+0xA4]), +0x100 SetFogEnabled, +0x104 SetExplorationEnabled.

**APPLIED 11/22 (AoWxShot.dll only, no exe byte on disk), emulator-tested (`test_aowxshot_fogplayer_emu.py`), not yet seen in the editor:** `aowxshot_fogplayer.py`, Init -> `fpinit` (called after baninit in aowxshot_missing.py) patches in memory 0x42BB94 -> fp_fog (seated := fog on ? [map+0x190] : 0, then SetFogEnabled) and 0x428964 -> fp_pick (store; with fog on: seated := pick, SetFogEnabled off+on to redraw). Fog off = seated 0 again, the editor's own state.
**v1 FAILED (user 11/22, still Independents' vision):** writing the seated byte is not enough - each hex has an unfog counter (field +0x1A) fed only for the seated player (TArmy.UpdateUnfog 0x5578E228 compares [army+0x12] with [map+0xA5]; radius remembered in [army+0x17]). **v2 APPLIED 11/22, emulator-tested, user verdict pending:** fp_seat stores the byte and calls TAoWHSMap.SeatedPlayerChanged (AoWEPACK RVA 0x76294, events 0x20020006/9 -> every army/structure/city redoes its unfog; base from [0x43289C]-0x1FA040). That routine runs in the editor at every map open anyway (map is created with seated = 1, editor sets 0). ResetSeatedPlayerView skipped (would recentre the view).
Related: [[map-level-vision]], [[aowdevx-binary-notes]].
