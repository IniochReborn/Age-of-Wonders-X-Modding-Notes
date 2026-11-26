---
name: devx-spellcheck
description: 2026-10-19 editor spell/ability description Text Editor gets red spell-check squiggles (ISpellChecker + GDI zigzag via a subclassed EDIT memo); patch_devx_spellcheck_v1 in AoWDevX .xprn 0x4E9700–0x4EA000
metadata:
  type: project
---
EditSpellTextClick 0x42C8DC / EditAbilityTextClick 0x42C724 open TTextEditDlg; memo [dlg+0x1E4] = EDIT. RichEdit IMF_SPELLCHECKING never drew squiggles on Win10 (prototyped) → instead: dialog-create calls 0x42C93B/0x42C783 → wrapper subclasses the memo HWND (SetWindowLongA); WM_PAINT draws red 1-px zigzags under ISpellChecker::Check errors (user locale, fallback en-US); invalidates on edit/scroll/selection/focus/size; restores on WM_NCDESTROY; LoadLibraryA/GetProcAddress via VCL30 IAT; init failure → vanilla. `.bak_spellchk`. ⚠ re-run after patch_devx_prune_unused_v2 (rebuilds .xprn). Ship AoWDevX.exe. APPLIED 10/19, untested in editor.
