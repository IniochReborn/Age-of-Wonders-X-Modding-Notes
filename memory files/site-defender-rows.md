---
name: site-defender-rows
description: 2026-10-18 site defender/prisoner/raze-defender lists — game has no 10-row cap (flat list of unit ids, rows of 8, random row via GetRndCollection 0x557835B4, 10 re-rolls); editor grid MinRowCount 8→20 via patch_devx_unitlist_rows_v1
metadata:
  type: project
---
Lists live in Release.hss site-type resources (not maps/saves). Game reads any length (live data already has 11-row tables); `GetRndCollection` 0x557835B4 picks a random row, re-rolls ≤10 times on empty rows (`mov edi,0Ah` @0x557835BA), then first non-empty. Editor only showed MinRowCount 8 (+1 past last full row). `patch_devx_unitlist_rows_v1.py --apply --raze` = DFM MinRowCount → 20 for exploration Defenders (file 0x04C894), dungeon Prisoners (0x04BA30), Raze Defenders (0x04AE4B); `--rows N`, `.bak_unitrows`. APPLIED 10/18 (with --raze), untested. Ship AoWDevX.exe + Release.hss after the user fills rows.
**10/18 later:** user asked 25 → applied `--apply --raze --rows 25`.
