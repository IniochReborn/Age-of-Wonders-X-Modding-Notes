---
name: aowx-taskbar-coords
description: "Taskbar cursor-hex coordinate label (2026-09-14, patch_aowx_cursor_coords.py, section .xcrd): TTBWindow DFM layout, PInd overlap trap, map-mouse getters via HSEPack delta, DisplayMouseMove wrapper"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2eb9e75f-d259-4a21-8f8a-bfb22139df71
  modified: 2026-09-13T03:57:25.393Z
---

**Feature (applied to the 410 prerelease AoWx.exe 2026-09-14, `patch scripts\patch_aowx_cursor_coords.py`,
backup `.bak_cursorcoords`, section `.xcrd` @VA 0x612000, SizeOfImage 0x212000→0x21C000; user-approved):**
the world taskbar message box shows "X,Y,Z" of the hex under the cursor at its right end, "-,-,-" when
none. Same technique as the item banner: relocated TTBWINDOW DFM (res data entry @file 0x731a0) with a
TAOWLabel `CoordLbl` cloned from TimeLbl (font Age10, awRight RightOffset 355, ahBottom BottomOffset 6,
Priority 60), field table +1 (CoordLbl @+0x144, class idx 4 = TAOWLabel), instance 0x144→0x148
(VMT 0x456cac, sites @file 0x56080/0x56090). Global TTBWindow instance var = 0x45b2c8.

- **Taskbar layout trap:** TBMessEdit is awBoth LeftOffset 48 / RightOffset 275, but the player/race turn
  indicator frame **PInd (75 px, RightOffset 275, priority 10) is drawn OVER the edit's right 75 px** — the
  visible text area ends 350 px from the right edge. A label at RightOffset 280 sat on the indicators and
  made them flicker/recolour on every repaint. TimeLbl/TimerImg/TimeIcn/WGoldPnl/WManaPnl sit further right.
- **Map cursor → hex:** TMWindow.MapWindowMouseMove @0x450EF8 (only runs when the cursor is inside the map
  viewport) updates THSMapMouse ([[0x45df7c]]+0xC) via VMT+0x20; hook @0x450F77 (7 B). Hex from HSEPack
  THSMapMouse.GetXhx/GetYhx (link 0x5560b6b0/0x5560b718, eax=self, −1 = none), reached rebase-safely as
  [IAT 0x45d9d8] (TMapContainer.GetField, link 0x55608d84) + delta; level = [map+0x88].
- **"Not on map" detection:** TMainForm.DisplayMouseMove (0x4536e8, method-table dword @file 0x51bb0, args
  eax/edx/cl + X,Y on stack, ret 8) dispatches synchronously; wrapper clears a flag, calls it, flag still 0
  → blank. Text only pushed on hex change, via SetGText thunk 0x403254 with two alternating static
  AnsiStrings (refcount −1) so the label never gets the pointer it already holds.

**Why:** any further taskbar widget (or status text) must avoid the PInd overlap and can reuse the
DFM-relocation + method-table-wrapper recipe here. Related: [[aowx-item-hpmv]], [[aowint-toolkit-internals]].
