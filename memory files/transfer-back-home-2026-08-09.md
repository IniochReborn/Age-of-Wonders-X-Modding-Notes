---
name: transfer-back-home-2026-08-09
description: "Laptop→home-PC full transfer prepared 2026-08-09; whole game folder is the package, memory snapshotted inside"
metadata: 
  node_type: memory
  type: project
  originSessionId: 48d27e42-fd53-46a7-a0ca-3edbed5bd4ee
  modified: 2026-08-09T06:08:01.854Z
---

On 2026-08-09 the user returned home and the laptop→home transfer was prepared. Unlike the 2026-08-01 delta, this is a FULL copy: the entire game folder (~7 GB) moves as-is. Verified same day that NO binary contains baked absolute paths (dlgdirs v2 is runtime-derived; "Desktop"/"Inioch" string hits were GetDesktopWindow imports, AoWE.DesktopWindow RStrs, and the intentional IniochReborn credit in AoWx.exe) — so any install path/name works at home.

Package layout inside `transfer to home PC\`:
- `README - FULL TRANSFER 2026-08-09.txt` — full instructions (rename home folder to a backup first, delete AoWEd_LastDirs.ini after copy, pip install keystone-engine capstone pillow, AOW_GAME_DIR env var).
- `claude memory 2026-08-09\` — snapshot of all 12 laptop memory files for home-PC Claude to install into its own slug dir.
- `OLD 2026-08-01 delta - SUPERSEDED do not copy\` — quarantined stale staging (its files are older than the game dir; never copy from it).

If this session is running on the LAPTOP after 2026-08-09, the game dir here may be stale relative to home. Related: [[project-state-2026-07]], [[baked-absolute-paths-gotcha]], [[lan-desync-investigation]].
