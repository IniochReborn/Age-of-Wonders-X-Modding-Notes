---
name: sign-text-hero-name-limits
description: 2026-10-30 sign wheel scroll (non-capturing memos latch g_hover) + editor sign unlimited / hero name+title 64 with red chars past 15; patch_memo_wheel_nocapture_v1 + patch_devx_text_limits_v1 APPLIED untested
metadata:
  node_type: memory
  type: project
  originSessionId: 68556280-d707-4a00-a5ee-7f75589fbb89
  modified: 2026-10-31T01:11:06.480Z
---

**Request 10/30:** signs (map object; text shown in TIWindow SignPnl over the event log, wooden GenericT bg, "The sign reads:") wheel-scrollable + much longer text; hero names/titles longer with characters beyond the original limit drawn RED in the editor only. User decisions: sign unlimited, names+titles max 64, red from char 16 (titles had no limit; longest built-in title "the Necromancer" = 15).

**Storage is unbounded:** TSign text = TStrings [sign+0x30] (ReadWrite tag 7; Sign unit exports found via scratchpad exp.py — pefile's export list truncates AoWEPACK). THero name [+0x60] / nickname(title) [+0x64] AnsiStrings, tags 0xA/0xB. Only editor controls capped.

**Wheel cause:** TIWindow.SignText TAOWMemo has CaptureInput False (comp byte +0xC0) → TAOWPanel/TAOWWindow.CheckMouseMove child loops (0x5981E677 / 0x5980A2A6) skip it → its hover latch never runs. Also non-capturing scroll memos: HelpMemo, MessageDlg/MsgReceive/ItemsFound MessageMemo, Tutorial MessageMemo, WorldMap MemoL/R — now wheelable too. `patch_memo_wheel_nocapture_v1.py` (aowInt zone 0x59824600–0x59824700, latch @0x59824620, stubs 0x598246A0/C0; .bak_memowheel): hover-only latch (memo VMT + scrollbar + memo rect test), no input delivered.

**Editor:** `patch_devx_text_limits_v1.py` (.bak_textlimits): TSIGNEDITFORM SignText MaxLength byte @file 0xD41EC 100→0; THEROEDITFORM NameEdit MaxLength @0x5D819 15→64; THeroEditForm method-table FormCreate entry @0x414594 (0x415A58) → wrap @0x4EC770 (.xprn zone 0x4EC500–0x4ED000): CB_LIMITTEXT 64 on NicknameEdit [form+0x214], subclass NameEdit [form+0x218] + combo edit child (prop "AoWxRL"), WM_PAINT overlay TextOutA red for chars ≥15 outside the selection. ⚠ re-run after patch_devx_prune_unused_v2. Keystone: `mov ebp,esp` encodes 89 E5; label-as-push-imm fails (use int3 marker two-pass).

Next free: aowInt 0x59824700; AoWDevX .xprn none left before the TMAINFORM DFM @0x4ED000.
