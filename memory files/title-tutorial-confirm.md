---
name: title-tutorial-confirm
description: 2026-10-18 title-screen Tutorial button → "Start Tutorial?" Yes/No popup (save-prompt dialog, 2 buttons); patch_title_tutorial_confirm_v1 (AoWx.exe .xtut 0x634000); ⚠ AoWx.exe section table now FULL
metadata:
  type: project
---
Title button jump table (5 entries @0x41AEE1) → dispatcher in new section `.xtut` 0x634000 (originals kept there); Tutorial opens the mid-game save-prompt dialog in its Yes/No configuration (title = existing translated "Tutorial", body "Start Tutorial?" English). Yes sets a flag; the title WindowUpdate method ptr @0x4193DA → wrapper runs the original then starts the tutorial next frame (avoids the tutorial's own message reusing the dialog). Other title buttons ignored while open; dialog busy → ignore; dialog missing → old behaviour. Apply after patch_hexgrid_option_v1, revert first; `.bak_tutconfirm`. ⚠ **AoWx.exe section-header table is FULL now** (also .xbfs 0x60ED00 is used) — future exe patches must reuse existing sections. APPLIED 10/18, VEH 6, untested.
