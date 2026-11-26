---
name: devx-autosave
description: "2026-10-31 AoWDevX toggle autosave button (floppy+hourglass) + Options > Autosave Timer; map SaveToFile to \"autosave - / autosave2 - <name>\"; USER-CONFIRMED 10/31"
metadata:
  node_type: memory
  type: project
  originSessionId: 68556280-d707-4a00-a5ee-7f75589fbb89
  modified: 2026-11-01T00:31:26.156Z
---

**✅ USER-CONFIRMED 10/31 (v1.1)** — `patch scripts/patch_devx_autosave_v1.py` (.bak_autosave = whole-exe backup; --revert restores it → re-run any later AoWDevX patch).
- TMAINFORM DFM (.xprn @RVA 0xED000): TSpeedButton `AutoSaveBtn` in Panel2 after SaveBtn at x84 (SaveBtn glyph + hourglass, AllowAllUp, GroupIndex 0x4D, no OnClick, no Enabled=False); Panel2 buttons right of x44 shifted +40.
- FormCreate method-table entry (table 0x4EB800, entry addr was 0x42841C) → wrapper @0x4ECC00 (code zone 0x4ECC00..0x4ED000 = unused tail of text_limits' zone); data .xitm 0x4E5240..0x4E5400. Wrapper finds the button in Form.Components (+0x10 TList, name [comp+8]), reads registry General\"Editor Autosave Interval" (digit 0..5, default 1 = 5 min) via AoWEPACK rwString, builds Options (form+0x204) > "Autosave Timer" radio submenu (OnClick +0x60/+0x64, data = index), creates TTimer (imports 0x432678/670/66C; SetOnTimer takes the method on the stack: push Data, push Code, ret 8; FOnTimer +0x2C/+0x30) at 10 s.
- Tick: TSpeedButton.FDown = +0xC0; HSMEdit form+0x22C: +0x1BC loaded, +0x1C0 map, +0x1E4 file name ("noname.hsm" = unsaved, no folder → skipped). Save = map VMT+0xAC SaveToFile(eax=map, edx=name, stack Code=HSE 0x5561509C(+delta from IAT THSMEdit.Save 0x433360 − 0x55614ED0), Data=HSMEdit) — same call THSMEdit.Save 0x55614ED0 makes; modified flag [[map+0x3C]+0x3C] bit0 IS cleared by SaveToFile (v1 assumed otherwise → Save greyed after an autosave) — v1.1 restores it. THSSEdit (mapset/ruleset) never touched.
- keystone: `push label` → KS_ERR_ASM_FIXUP_INVALID; use `mov ecx, label; push ecx`.
- ⚠ Other TMAINFORM-rebuilding scripts (terrain palette, sky polish, ability/spell layouts) now see the extra button; re-check their asserts if re-run. Related: [[aowdevx-binary-notes]].
- **v1.1 APPLIED 10/31** (same script re-applies code/data when the button already exists): timer 1 s (elapsed in seconds); button enabled only while a map is loaded (TControl.FEnabled +0x45, SetEnabled thunk 0x401550, disable also SetDown(0) thunk 0x402318; starts disabled). ⭐ map SaveToFile DOES clear the modified bit [[map+0x3C]+0x3C] bit0 — that bit drives SaveBtn enabling (HSMEditUpdateFrame 0x428D7E) and the close prompt → saved before / OR-ed back after the autosave.
