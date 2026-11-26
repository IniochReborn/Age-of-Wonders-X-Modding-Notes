---
name: eventlog-hover-nojump
description: Event tab stops auto-jumping to the newest entry while the cursor is over the event list (patch_eventlog_hover_v1, AoWx.exe .xbfs 0x60EC20, 9/21 applied awaiting test); logbook window RE.
metadata:
  type: project
---

**Applied 2026-09-21, awaiting test** (`patch scripts/patch_eventlog_hover_v1.py`, backup `backup\AoWx.exe.bak_evhover`).
User: the event tab jumps to the bottom on every new event, which fights clicking the level-up entry; wanted: no jump while the mouse is over the tab, normal otherwise.
**RE:** logbook window instance `[0x45A4FC]`; TMapEvents.TheMapLogbookChanged 0x44F97C (only for the current player) → 0x423304 refresh: list = `[win+0x54]` TAOWListBox, items `[+0x114]` cleared (VMT+0x40), refilled via `EventLog.TEventLogbook.ListEvents` (thunk 0x402194) from `[player+0xD8]`, then `TAOWListBox.SetListOff(list, count-1)` (thunk 0x403664, IAT 0x45EC94) @0x42336A = the jump. `TEventLogbook.GetLogs` thunk 0x40219C; double-click handler 0x423394 executes `[log vmt+0x70]` on the selected entry.
**Hook:** 0x42336A → cave 0x60EC20: `&g_hover = [IAT SetListOff] + (0x5983E100 − 0x598168F4)` (aowInt's wheel-patch hover global = TAOWListBox under the cursor, cleared each WinManager mouse-move sweep) → if g_hover == list skip SetListOff. Leaving the list does not jump by itself; the next event/turn does. **.xbfs next free 0x60EC40.**
