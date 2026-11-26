---
name: customize-name-registry
description: MP lobby player name persisted from the customize-leader screen (patch_customize_name_registry_v1, AoWx.exe .xbfs 0x60EB00); holds the player-name plumbing RE (registry General\strings\0, TLeaderSetupWin finish routine).
metadata:
  type: project
---

**Applied 2026-09-21, awaiting test.** `patch scripts/patch_customize_name_registry_v1.py` (backup `backup\AoWx.exe.bak_custname`).
User ask: a name changed in leader customization must survive exit + rejoin of the MP lobby without the pre-lobby rename step.

**Plumbing (AoWx.exe):**
- Player name = registry `General\strings\0` (TAoWRegistry.GetString/SetString id 0; id 1 = email). Registry object = `[[[0x45DF74]]+0x5C]`; exe thunks GetString 0x401EFC / SetString 0x401F04 (eax=reg, edx=id, ecx=str).
- Pre-lobby name dialog: GetString(0) → edit `[[0x45A598]]+0x90` (0x4535C2); OK → SetString(0, edit text) (0x45395C).
- `TLeaderSetupWin` (VMT 0x414BA0, published methods table 0x41557D; Delphi-3 VMT: name ptr at VMT+0x20): `NameEditChange` 0x417110 copies the edit text into `[[win+0x2E4]+0x60]`; [win+0x2D8] = TCustomizeLeaderControl, [win+0x2DC] = step 1..3; finish routine 0x416D9C: `[ctl+0x1C]=2`, DirectPlay name push via 0x41468C (only if `TSetupControl.GetRemote([[0x45A454]]+0x48)` — MP session), then ctl.Done (VMT+0x4C → AoWSetup.TCustomizeLeaderControl.Done 0x557DF7E0 → LeaderCustomized token) and free. Name = `[[ctl+0x14]+0x60]`.
- `TSetupEvents` (exe) published handlers: SetupControlCustomizeLeader 0x4141E0 → 0x416988 shows the window.
- AoWSetup (AoWEPACK): TSetupControl.Create 0x557DF7F0 ([+0x28] TSetupSettings, [+0x34] local player setup with +8 = name), Get/SetPlayerName 0x557E12C8/0x557E12E0, ValidatePlayerName 0x557E185C.

**v1 FAILED** (name reverted on exit): `TMainForm.FormDestroy` 0x453910 (published method; site of the borderless-fullscreen .xbfs hook) re-saves settings at shutdown incl. SetString(0, text of the pre-lobby edits `[[0x45A598]]+0x90`/`+0xC4`, TAOWEdit +0x90 = text). **v2 (applied 9/21):** cave 0x60EB00 (125 B) = MP-gated SetString(0,name) + `AoWEdit.TAOWEdit.SetGText` (thunk 0x40326C) on both edits, then the displaced ctl.Done call. `.xbfs` next free **0x60EB80**.
