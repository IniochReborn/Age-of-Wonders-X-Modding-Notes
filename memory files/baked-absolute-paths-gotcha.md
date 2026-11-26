---
name: baked-absolute-paths-gotcha
description: Binary patches may embed absolute build-time paths — silently break when the game folder moves machines
metadata: 
  node_type: memory
  type: project
  originSessionId: 12b93ff5-7a39-44b4-a992-0ccf992938b0
  modified: 2026-08-09T08:54:13.095Z
---

The dlgdirs editor patch (`build_dlgdirs.py`) originally baked the absolute `AoWEd_LastDirs.ini` path into the `.dlgd` sections of `AoWDevX.exe` and `HSEPack.dpl` at build time. After the 2026-07-31 home-PC→laptop transfer this silently disabled the per-dialog directory memory (reads empty → vanilla fallback, writes fail without error). **Permanently fixed same day (v2)**: the cave now derives the path at runtime via `GetModuleFileNameA` (VCL30 IAT slot `0x413E43C0`), so shipped binaries work at any install path. Rebuilt from `.pre-dlgdirs` backups. Details in `reference files\BXL\Editor_Modernization_DialogDirs_Toolbar.md` (bottom of Feature 1). Build tooling (laptop was Python 3.12; **home PC 2026-08-09: Python 3.10 via `py -3.10`, keystone-engine + capstone + pillow all installed, AOW_GAME_DIR set as a persistent user env var** — 3.12 not installed at home, use `py -3.10` or plain `py`); run build scripts with `AOW_GAME_DIR` env var set to the game dir.

**Why:** the user moves this project between machines; any patch embedding build-time absolute paths will break the same way.

**How to apply:** when something patched "worked at home but not here," first search the patched binaries for embedded absolute paths (`C:/Users/...`). Also check `AoWEd_LastDirs.ini` contents for stale paths. Future patches should derive paths at runtime (e.g., `GetModuleFileNameA`) instead of baking them. Related: [[project-state-2026-07]].

**2026-09-20:** 31 laptop-era scripts shipped with `C:\Users\<user>\...410 prerelease` baked as DEFAULT_DLL/GAME/EXE; all rewritten to `from bakpath import game_dir, game_file` (`patch scripts\bakpath.py`: AOW_GAME_DIR if set and present, else the parent of the scripts folder). Use that helper in every new script. Related: [[transfer-home-2026-09-20]].
