---
name: aowint-cave-map
description: Allocated code caves in aowInt.dpl CODE tail — check before placing new ones
metadata: 
  node_type: memory
  type: project
  originSessionId: af9a924c-2966-4ffc-8efd-4b983e546f21
  modified: 2026-09-15T02:42:20.583Z
---

aowInt.dpl CODE-section tail zeros hold patch caves. Allocated as of 2026-08-20:
- 0x59822800/0x59822840/0x59822880 + 0x59823200/0x59823400: mouse-wheel patch (build_wheel_aowint.py; g_hover @0x5983E100 DATA slack, diag counters @0x5983E110)
- 0x59823600–0x59823963: power-slider patch (build_wheel_power_slider.py)
- 0x59823A00–0x59823B52: file-dialog arrow-key navigation (build_filedlg_keynav.py; TAOWListBox VMT slot 37 @0x59816030 repointed here, gated on OnChange==0x4201EC FileLBChange, with sibling dedup because SaveLB+DateLB are both bound to FileLBChange)

- 0x59823D00–0x59823D3E: memo scroll clamp (build_memo_scroll_clamp.py, 2026-08-21): TAOWMemo.SetFirstLine 0x59819298 hooked (6B: 53 56 8BF2 8BD8) → full cave reimpl clamping first-line to [0, Lines.Count-1] (0 when empty). PRE-EXISTING wheel-patch bug: WheelScroll's no-scrollbar fallback drove memo [+0x128] negative → EListError "List index out of bounds (-N)" in memo draw (raise ret-addr aowInt+0x19704) → per-widget "Error - <name> / Exception during Draw". TAOWMemo VMT 0x5981848C, fields: Lines TStringList [+0x188], first-line [+0x128], visible rows [+0x124], real scrollbar [+0x120] ([+0x118] is NOT the scrollbar on memos — different from TAOWListBox!). WheelScroll (current, evolved) dispatches by exact VMT: listbox→+0x118, memo→+0x120, else sibling TAOWVScrollBar hunt, else direct first-line fallback (the buggy path). Diag tooling: scratchpad excmon.py (attachable first-chance exception monitor, decodes Delphi raises: Info[0]=raise EIP, Info[1]=exception obj, msg at [obj+4]; survives game restarts), hoverpoll.py (samples g_hover).

- 0x59823D40–0x59823D68 + 0x59823D80–0x59823DD2: combo-box wheel (build_wheel_combo.py, 2026-09-14): TAOWComboBox.CheckMouseMove inside-marker @0x59813AC1 latches g_hover only while dropped down ([cb+0x118]≠0); WheelScroll's unknown-class fallthrough @0x59822915 (`kind:=2; edi:=0`, 9 B) redirected → if g_hover is a TAOWComboBox (VMT 0x59811FCC) and open: SetFPos([cb+0x120] scrollbar, ±3) + TAOWComboBox.Update 0x598131CC, then jmp the helper's success exit 0x59822A4E. ⚠ Any rebuild of the helper by build_wheel_aowint.py shifts 0x59822915/0x59822A4E and undoes this (and the memo-inert byte @0x59822A16) — re-apply both after.

- 0x59823E00–0x59823E80: power-slider TILT fine step (patch_power_slider_tilt_v1.py, 2026-10-12): TAOWWinManager key dispatch 0x598072FC prologue (7 B) hooked → VK_LEFT/RIGHT with g_pslider set = SetFPos ±1 + OnChange, key consumed. v2: pass-through path leaves eax/ecx/edx untouched (v1 clobbered cl = shift state → cheat mode stopped working).

Free zeros: ~0x59823E80 up to ~0x5983D000.

VCL30.dpl caves (CODE file = VA-0x41300C00, .idata file = VA-0x41302A00):
- 0x413A8400/0x413A8800: old WH_MOUSE hook (editor scrollbars)
- 0x413A8A00 pump cave, 0x413A8B00 LL wheel proc, 0x413A8C00 hook-owner threadproc (build_wheel_vcl_pump.py); lpfn dword @0x413A8C3E
- 0x413A8D00–0x413A9194 cave_chproc mouse chords (build_mouse_chords.py, 2026-08-21): chained LL proc (chords → tail-jmp 0x413A8B00), repointed lpfn. ⚠ PLAIN wheel policy (v3, final): send arrow keys ONLY when NONE of the wheel-armed aowInt globals {0x3E100 hover, 0x3E104, 0x3E10C, 0x3E148} is set (mirrors the CURRENT LL wheel proc's armed check @0x413A8B2B — if a future wheel patch adds an armed global, add it in BOTH places), then always pass through. v1 swallowed (killed power-slider wheel), v2 always sent (double action: events panel scrolled + map panned). Chorded wheel/tilt/middle are consumed (SoS parity). Related: build_memo_wheel_inert.py (aowInt 1-byte @0x59822A16: WheelScroll's no-scrollbar MEMO fallback → ret 0, city text boxes inert; listbox SetListOff fallback kept). Runtime state+config in .idata file-backed zeros: G2_STATE 0x413E7150 (held bits X1/X2/L/R), fn ptrs +4..+0x10 (keybd_event lazily resolved, 1=poisoned), diag counters 0x413E7164/68, **VK TABLE 0x413E7170 (20B, writable at runtime — the future AoWSetup Mouse tab edits exactly these bytes)**: rows wheelup/wheeldn/tiltL/tiltR/middle ×(plain,X1,X2), then L+X1, R+X1, X1+X2, Ctrl-combo vk, reserved. Wheel patch globals: G_PENDING trio 0x413E7140, G_AOWBASE 0x413E27FC, diag 0x413E27D4/0x413E27E0 (DATA slack).
- VCL30 free CODE zeros: 0x413A91C0..0x413E0928 (~220KB). Free .idata zeros: 0x413E7184..0x413E7200.
- chord_probe.py reads the live chord engine state.

**Why:** overlapping caves corrupt earlier patches; the build scripts assert zeros but knowing the map avoids trial-and-error.

**How to apply:** scan for nonzero runs before choosing a cave address, allocate from 0x59823D00 upward, and update this memory when a new cave is placed. Related: [[aowint-toolkit-internals]].
