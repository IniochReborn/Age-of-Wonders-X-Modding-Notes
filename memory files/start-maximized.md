---
name: start-maximized
description: 2026-11-19 AoWx.exe starts maximised in windowed mode (patch_start_maximized_v1, stub .xedt 0x62FF80) - APPLIED, untested
metadata:
  type: project
---

User 11/19: in windowed mode the game should start as a maximised window (no manual maximise each start).

RE: TMainForm.FormCreate 0x453184: `call GetMainWindowState` @0x45329D (thunk 0x401FAC, eax = registry) →
SetWindowState @0x4532A6; state is saved at exit (FormDestroy 0x45393D). TAoWRegistry.GetDisplayMode (thunk 0x401F24,
AoWEPACK 0x5570476C) returns an integer in eax: 0 windowed, 1 fullscreen, 2 "Fullscreen (Optimized)".

Build: `patch scripts\patch_start_maximized_v1.py` (`.bak_startmax`, in-place): site call → stub **.xedt 0x62FF80**
(22 B): display mode == 0 → return 2 (wsMaximized), else the saved state. Exe .xedt map now: indicator +0..0x7F0 (rig
stub 0x62F7C8), cityspy 0x62F800–0x62FB00, royal ambition 0x62FB00–0x62FD00, shake 0x62FD00.., rig 0x62FF40–0x62FF80,
start-max 0x62FF80–0x62FFA0; free 0x62FFA0–0x630000.

**Status:** APPLIED 11/19, USER-CONFIRMED 11/19 ("good"). The 2P/3P sim launchers un-maximise copies 1+2 themselves (Place restores first).
