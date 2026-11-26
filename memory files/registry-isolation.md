---
name: registry-isolation
description: "Mod uses its own isolated registry tree \"Age of Wonders X\" instead of vanilla \"Age of Wonders\" (fixes multi-mod registry conflicts). Applied 2026-07-22."
metadata: 
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-22T04:48:33.844Z
---

**GOAL:** AoW mods all write to the same registry, conflicting when multiple mods are installed. Gave AoWx its OWN registry tree so it's self-contained. Applied 2026-07-22, CONFIRMED clean patch.

**MECHANISM:** The game's entire per-user settings registry hangs off ONE Delphi string constant, **`\Software\Triumph Studios\Age of Wonders\`**, which lives ONLY in **AoWEPACK.dll** (6 copies — the low-level read/write helpers rwString/rwInteger/rwBool etc., all under `TAoWRegistry`). The game exe AND both editors route all registry access through AoWEPACK's `TAoWRegistry`, so changing this ONE file isolates everything. (The exe/editors' "Triumph Studios" strings are just company name in version info, NOT registry paths.) Settings live under subkeys General\{strings,booleans,rectangles}, Sound, Video, Workspace, Email; strings keyed by IntToStr(id) (see [[editor-dialog-dir-memory.md]] for TAoWRegistry.Get/SetString detail).

**PATCH (AoWEPACK.dll, backup `AoWEPACK.dll.bak_regiso`):** Each path string is a `-1` refcount Delphi const loaded by `mov edx,<addr>`, with 3-4 spare 00 bytes after it → edited IN PLACE (bump length prefix +2, insert " X" before the last `\`). The 6 copies:
- 0x55703BEC, 0x55703CDC, 0x55703DD4, 0x55703EC8, 0x557041BC: `\Software\Triumph Studios\Age of Wonders\` (len 41->43) -> `...Age of Wonders X\`
- 0x557046BC: `...Age of Wonders\General` (len 48->50) -> `...Age of Wonders X\General`
Refs (`mov edx`, unchanged since chars stay in place): 0x55703B60, C50, D40, E38, 0x5570410D, 0x55704670.
Result: mod uses `HKCU\Software\Triumph Studios\Age of Wonders X\...`, fully separate from vanilla + other mods. To revert: restore backup, or change " X" back out.

**LANGUAGE FORCED TO ENGLISH (already present in our AoWEPACK.dll, discovered 2026-07-22):** `TAoWRegistry.GetLanguage` @0x55704B6C is patched to return **1 = alEnglish** (`mov al,1; nop` = `b0 01 90` at file 0x4288, VA 0x55704B84) instead of vanilla/AoW+ `mov al,byte[esp]` (`8a 04 24` = return the registry value). `TAoWLanguage` enum = (alAuto=0, alEnglish=1,...). The text/localization system reads GetLanguage at 3 sites (0x5579769B, 0x55797C8B, 0x55797D14) then `and eax,0x7f` to pick the text-set index, so forcing 1 => game always uses the "English" (index 1) text entries, NOT "Auto (English)" (index 0) — eliminates users having to switch language Auto->English. Baked into the binary (overrides registry/UI). Origin undocumented (pre-existing in our AoWEPACK base or an uncaptured session). To revert: write `8a0424` back at 0x55704B84.

**SETTINGS MIGRATION:** Seeded the new key from the old one via `reg copy "HKCU\Software\Triumph Studios\Age of Wonders" "HKCU\Software\Triumph Studios\Age of Wonders X" /s /f` (non-destructive; old key untouched) so this machine keeps its current settings. For DISTRIBUTION: other users won't have the key seeded — the game just creates "Age of Wonders X" with defaults on first run (fine), or ship a .reg to seed. Dev-mode/portrait fix is UNAFFECTED (GetDeveloper is hardcoded, not registry-read). NOTE: file-association keys `\Software\Classes\.hsm|AOWMAP\...` (HKCR) are separate/system-wide and intentionally left alone.
