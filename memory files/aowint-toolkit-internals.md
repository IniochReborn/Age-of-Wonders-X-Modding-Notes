---
name: aowint-toolkit-internals
description: "Reverse-engineered aowInt.dpl widget toolkit — VMT layout, field offsets, input dispatch"
metadata: 
  node_type: memory
  type: reference
  originSessionId: af9a924c-2966-4ffc-8efd-4b983e546f21
  modified: 2026-09-15T02:42:25.894Z
---

aowInt.dpl (base 0x59800000, CODE file-off = VA-0x59800C00) implements the game's widget toolkit (TAoWComponent/TAOWControl/TAOWListBox/TAOWEdit/TAOWWindow/TAOWWinManager, 35 classes).

- Delphi 2-style VMTs: self-ptr @VMT-64, classname @-32, instance size @-28, parent VMT ptr @-24 (points at parent's VMT-64). TAOWListBox VMT=0x59815F9C, TAOWControl=0x5980B6A0, TAOWEdit=0x59813C90, TAOWVScrollBar=0x5980C594.
- Common control fields: +0x2C init flag (set to 1 by ctors), +0x44/0x4C/0x6C/0x150 event method ptrs (each: dword code, word-at+2 assigned-check, dword+4 Self), +0x75 Visible, +0x78 input-claim flag (-1 = consumed this mouse/key event), +0x7C/0x80 width/height, +0x84/0x88 left/top, +0xA4 painted flag (0 = repaint), +0xD0 children TList (data +4, count +8), +0x10C parent.
- TAOWListBox: +0x114 items (virtual call [vmt+0x14] = Count, [vmt+0xC] = GetString), +0x118 linked TAOWVScrollBar, +0x11C visible rows, +0x120 selected index (-1 = none), +0x138 right inset (scrollbar), +0x14C item pixel height, +0x15C top-item offset. Click handler = VMT slot 33 @0x598171C4 (sets +0x120, +0xA4=0, fires OnChange +0x6C). Exports: SetIndex 0x598168B8, SetListOff 0x598168F4 (both clamp, neither fires events). Update = slot 15 @0x59817138 (re-syncs +0x15C from scrollbar FPos, clamps to count-vis, repaints). TAOWScrollBar: FPos +0x148, SetFPos 0x5980CA28 (eax=self, edx=pos, clamps), OnChange +0x6C/0x6E/0x70.
- TAOWComboBox (VMT 0x59811FCC, instance 0x1A0; used by the multiplayer lobby TSCENSETUP race/behaviour/preferred-race dropdowns): +0x118 dropped-down flag (−1 open, 0 closed; +0x80 height then spans the list), +0x11C items (VMT+0x14 Count), +0x120 own TAOWVScrollBar (DFM `VScrollBar` sibling, FMin/FMax/FNum/FPos + geometry set at drop in CheckMouseDown 0x59813254), +0x124 visible rows, +0x12C top item, +0x138 selected, +0x13C hovered item, +0x150 right inset, +0x168 item height. Update 0x598131CC syncs +0x12C from SB.FPos (+0x148). CheckMouseMove 0x59813A30 inside-marker `mov [ebx+0x78],-1` @0x59813AC1 (same 7-byte shape as listbox/memo).
- Keyboard pipeline: virtual slot 37 (VMT+0x94), args eax=self, edx=ptr to VK word, cl=shift (bit 4 = Ctrl). TAOWWinManager dispatch @0x598072FC iterates windows topmost-first; TAOWWindowControl @0x59804B80 forwards to ALL children (no early-out), claims window's +0x78 if any child claimed, then ALWAYS fires the window's own OnKeyDown (+0x64/0x66/0x68); window byte +0x104 = "eat all keys". Unclaimed keys fall to the manager's global hotkey event. TAOWEdit overrides slot 37 (Left/Right/Del, Ctrl+V only).
- AoWx.exe dialog classes bind events by NAME via published method tables (entry: u16 size, u32 addr, len-prefixed name) referenced near each class VMT; form streams are in-EXE resources. TFileDlgWindow VMT=0x41EB60 serves New Game/Load/Save; FileLB at dlg+0x58, companion columns +0xD8/+0xE8, FileLBChange=0x4201EC (syncs all three lists + info panel + filename edit), mSBarChange=0x42094C, FileDialogKeyDown=0x420DA8 (ESC only). Careful: the load/save view (form stream) has TWO sibling listboxes in frame SaveLBFr — SaveLB (no scrollbar) and DateLB (scrollbar SSBar) — BOTH with OnChange=FileLBChange; the New Game view has one (scrollbar NSBar). Any per-list input hook must dedup among siblings or keys act twice.

**Why:** every UI-behavior patch needs these offsets; re-deriving them costs hours.

**How to apply:** trust but spot-check with capstone (scratchpad helpers aow_pe.py/disasm.py pattern) before patching new sites. Related: [[aowx-project-overview]], [[aowint-cave-map]].
