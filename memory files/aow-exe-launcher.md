---
name: aow-exe-launcher
description: AoW.exe in the game root is a compiled AutoHotkey launcher (not the game); patched 2026-09-21 to just run AoWx.exe after the retired "Scroll of Slickness" helper made it error out. Also: `start AoW.exe` from a shell resolves to the vanilla install via App Paths - use the full path.
metadata:
  type: project
---

**AoW.exe (710656 B, AutoHotkey v1.1.37.02 compiled)** = launcher only: its script (RCDATA ">AUTOHOTKEY SCRIPT<", plain text, 204 B @file 0xACEF8) used to `Run "AoWx - Scroll of Slickness.exe"` then `Run AoWx.exe`, wait, kill the helper. The helper was retired when wheel scrolling went native, so Run failed → "crash". **Patched 9/21 by `patch scripts\patch_aow_exe_launcher.py`** (backup `backup\AoW.exe.bak_launcher`): script rewritten in place, same length, to `Run "%A_ScriptDir%\AoWx.exe", %A_ScriptDir%` + `ExitApp`. Verified: launches AoWx.exe and exits. AoW.exe must keep existing: AoWSetup's install check and Start button target `aow.exe` ([[aowsetup-installcheck-devtab]]).

**Why:** vanilla `AoW.exe` is a different program at `C:\Program Files (x86)\Triumph Studios\Age of Wonders Unpatched\`; the mod root's AoW.exe is only a shim. ⚠ `start "" AoW.exe` from the mod root launched the VANILLA game (App Paths / PATH resolution) — always launch by full path when testing.
**How to apply:** future launcher tweaks = edit the script bytes in place (≤204 B, space-pad); AHK does not checksum it. The release zip ships AoW.exe — include the patched one ([[aowx-release-process]]).
