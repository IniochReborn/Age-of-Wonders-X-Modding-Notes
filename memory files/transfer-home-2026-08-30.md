---
name: transfer-home-2026-08-30
description: "Laptop→home-desktop full transfer prepared 2026-08-30; whole game folder is the package, memory snapshotted inside"
metadata: 
  node_type: memory
  type: project
  originSessionId: cb05c227-440f-4f5a-8069-218d4271d140
  modified: 2026-08-30T16:38:18.208Z
---

On 2026-08-30 the laptop→home-desktop transfer was prepared (same recipe as the 2026-08-09 one). The entire game folder is the package; Claude's memory (all 17 files) was snapshotted into `transfer to home PC\claude memory 2026-08-30\` for home-PC Claude to install into its own slug dir. Instructions in `transfer to home PC\README - FULL TRANSFER 2026-08-30.txt`. The 2026-08-09 staging (README + memory snapshot) was renamed OLD/SUPERSEDED and kept as history only.

Verified 2026-08-09 (still holds): no binary contains baked absolute paths, so any install path works; delete `AoWEd_LastDirs.ini` after copying; home PC needs Python 3.12 + keystone-engine/capstone/pillow + `AOW_GAME_DIR`.

If a session runs on the LAPTOP after 2026-08-30, the game dir here may be STALE relative to the home desktop.
