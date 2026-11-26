---
name: help-aowx-manual
description: 2026-10-19 Help menu item "www.ageofwonders.com" → "AoWx Manual" opening https://aowx.org/; patch_help_aowx_manual_v1 (exe URL literal + TPOPUPWINDOWS DFM + mld rows)
metadata:
  type: project
---
Click handler 0x4278D0 ShellExecute "open" on literal (file 0x26D0C, 28 B) — item picked by index. Label in TPOPUPWINDOWS DFM (file 0x149A6C; HelpMenu + TCHelpMenu item 3; resource size @0x73074 0x2CD3→0x2CC1). Dict\AoW.mld + AoWVan.MLD rows → "AoWx Manual" in all columns (keys untouched). `.bak_helplink`. Ship AoWx.exe + both mld. APPLIED 10/19.
