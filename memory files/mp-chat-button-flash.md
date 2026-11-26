---
name: mp-chat-button-flash
description: RE of the in-game MP chat notification (AoWx.exe): DPlayChatMessage sets a 136-tick flash counter on the taskbar; ChatBtnUpdate toggles the button image every 15 ticks (5 flashes) then stops; no persistent unread state. Explored 2026-09-21, no patch yet.
metadata:
  type: project
---

**Ask (2026-09-21):** explore how the MP chat tab signals an unread message (user forgot whether it lights up or flashes). Answer: it FLASHES 5 times then returns to normal; nothing stays lit; opening the chat window does not cancel the flash. Candidate improvement (not built): keep the lit image until ChatBtnClick/ChatWinShow, or flash until read.

## RE (AoWx.exe, Delphi published methods)
- **DPlayChatMessage 0x413F70** (main form OnChatMessage handler; edx=^string): lobby active (`[[0x45A30C]+0xA0]+0x75`≠0) → lobby memo `[[..]+0x44]+0x118` VMT+0x34 Add + `[form+0x344]=1` (ChatSBUpdate 0x412C8C scrolls to bottom). In-game → game-window chat memo `[[0x45A490]+0x48]+0x118` Add, **`word [[0x45A0CC]+0x140] = 0x88`** (taskbar TTBWindow flash counter), `[[0x45A490]+0x70]=1` (ChatMemoUpdate 0x41306C scrolls), PlaySample("SFX\EVENTS\CHAT.WAV") via 0x401D64.
- **ChatBtnUpdate 0x457EBC** (TTBWindow; OnUpdate of both `ChatBtn` (strategic, field [tb+0x78]) and `TCChatBtn` (combat) TAOWButtons per DFM): eax=taskbar, edx=button. If counter>0: at 0x88/0x6A/0x4C/0x2E/0x10 → `SetILUIndex(0x14)` (lit frame), at 0x79/0x5B/0x3D/0x1F/1 → `SetILUIndex(0xE)` (normal); also `[btn+0xA4]=0`; then `dec counter`. => 5 flashes of 15 ticks lit / 15 normal, ends normal. Tick = one UI frame (aowInt OnUpdate; main loop Sleep(1)/Sleep(0) @0x452E87 free-runs, hooked by borderless patch at 0x452E50).
- **ChatBtnClick 0x457480**: click sound 0x455DFC(x,0), toggles chat window `[[0x45A490]+0x44]+0x75` via SetVisible VMT+0x6C. Does NOT touch the counter. ChatWinShow 0x413040 / ChatWinHide 0x413058 → taskbar helpers 0x456AAC/0x456B34 (dock layout), no counter either.
- **Counter reset**: game-start init (big function ending 0x4552E0) sets `[tb+0x13C]=0` (TBWorldUpdate countdown, unrelated) and `[tb+0x140]=0` + ChatBtn image 0xE @0x455270-0x4552A0.
- TAOWButton (aowInt VMT 0x59810DC0): +0xA0 SetILUIndex, +0x6C SetVisible. Globals: 0x45A0CC taskbar, 0x45A490 game window (+0x44 chat window, +0x48 chat-memo owner), 0x45A30C setup form.
