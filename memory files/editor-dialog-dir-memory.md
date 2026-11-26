---
name: editor-dialog-dir-memory
description: "Editor Open Map / Open Mapset / Text dialogs each remember their own last directory + last file, PERSISTED ACROSS SESSIONS. Now uses BXL's build_dlgdirs.py fix (AoWDevX.exe + HSEPack.dpl, INI-backed) — replaced our earlier within-session-only version 2026-07-24. CONFIRMED WORKING."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-24T08:44:47.383Z
---

**GOAL:** Editor file dialogs (File>Open map *.hsm, Developer>Open Mapset *.hss, Text export/import) all shared Windows' one per-app "last folder", forcing constant re-navigation between the Scenario tree and Release\. Want each dialog TYPE to remember its own folder independently AND across editor restarts.

## ✅ CURRENT SHIPPED FIX 2026-07-24 — BXL's `build_dlgdirs.py` (cross-session, INI-backed)
Replaced our earlier within-session-only hack with **BXL/Ziggurat's fix** (`reference files/BXL/build_scripts/build_dlgdirs.py`, notes in `reference files/BXL/Editor_Modernization_DialogDirs_Toolbar.md`). CONFIRMED WORKING in-game (remembers separate Map vs Set folders across a full editor restart).
- **Per-dialog-type memory persisted in `<gamedir>\AoWEd_LastDirs.ini` [LastDirs]** keys `Map`/`Set`/`Text`. Open dialogs: before Execute, set FFileName(+0x6C)=remembered full path + FInitialDir(+0x60)=its dir → opens in that folder w/ last file preselected; after a pick, write path back. SaveAs (map+set): reroute their `SetInitialDir(GetCurrentDir)` to the remembered dir. First run/missing key = vanilla.
- **Adds a `.dlgd` PE section** to each of **AoWDevX.exe** + **HSEPack.dpl** (chars 0xE0000060 = code+data+W; INI read-buffer lives in-section). 16 sites hooked (5-byte `call thunk`→`call cave`). HSEPack cave is PIC (call/pop ebx delta) since it rebases.
- **Key trick — calling kernel32 profile APIs from modules that don't import them:** both modules import `VCL30!Dialogs.TOpenDialog.Create`; cave computes `vcl_delta = [own IAT slot] - 0x4137AFB0` then reads VCL30's IAT slots `GetPrivateProfileStringA @0x413E43B8`, `WritePrivateProfileStringA @0x413E42F8`. Own Create-IAT slots: AoWDevX.exe **0x432598**, HSEPack.dpl **0x556308DC**. INI buffer doubles as a static Delphi AnsiString (refcount -1) for LStrAsg into FFileName/FInitialDir.

### Apply / revert (this repo)
- **keystone required** — not preinstalled here; `py -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org keystone-engine`.
- Script targets `AoWDevEd.exe`; we renamed to **AoWDevX.exe** → run a copy with the MODULES key sed'd `AoWDevEd.exe`→`AoWDevX.exe`, and `AOW_GAME_DIR="<game root>"` env so the baked INI path + file paths point at the game root. Dry-run (no arg) verifies all 16 sites; `--apply` writes. Verified ALL 16 BXL sites byte-match our AoWDevX.exe (our About/FrameRate/cursor patches don't touch them) AND HSEPack.dpl.bak_dirmem.
- **Applied onto:** current AoWDevX.exe + **HSEPack.dpl reverted to `.bak_dirmem`** first (= mapcursor-only, our old dir-memory removed). Backups written: **AoWDevX.exe.pre-dlgdirs, HSEPack.dpl.pre-dlgdirs**. Revert = copy those back. `.dlgd` section now present in both.
- Scratchpad copy: build_dlgdirs_x.py. BXL also has a companion `build_editor_toolbar.py` (menu→toolbar rows + start maximized) — NOT applied, available if wanted.

## ROOT CAUSE (our earlier Ghidra RE, still valid)
Open Map = `HSMEdit.THSMEdit.Load` @0x55615244 (HSEPack) + exe OpenBtnClick @0x429820; Open Mapset = `HSSEdit.THSSEdit.Load` @0x55615e64. TOpenDialog fields: Filter +0x54, **InitialDir +0x60**, **FileName +0x6C**, DefaultExt +0x68 (all confirmed via VCL30 SetInitialDir/DoExecute).

## SUPERSEDED — our earlier attempts (2026-07-21/22), now reverted
Our v1-v4 hand-caves (HSEPack cave_map@0x5561AD00 / cave_mapset@0x5561AD40, exe cave@0x42F1B0, globals @0x5562EF00/EF04, @0x42FF00) gave only **within-session** independence. Lessons learned (why BXL's INI approach was needed): InitialDir(+0x60) loses to Windows' shell LastVisited MRU; FileName(+0x6C)-override beats MRU but in-memory globals reset on restart; DefaultExt(+0x68) keying does NOT re-key the MRU. **Cross-session is ONLY achievable via explicit disk persistence** (INI/registry) — which is exactly what BXL's fix does. All our v-caves are gone (HSEPack→bak_dirmem before BXL applied). Ghidra headless workflow: see [[designer-only-portrait-toggle]].
