---
name: leader-fog-depths-report
description: 2026-11-14 MP report - a player's leader in the Depths was under fog and unselectable the turn after moving next to a portal; not reproducible, no save; suspect = LOS-terrain turn-start fog rebuild skipping his army
metadata:
  type: project
---
Report 11/14 (screenshot only): leader moved to a hex beside a portal in the Depths, ended turn; next turn his own hex was fogged and he could not be selected. User suspects the "can't see behind walls underground" change (build_los_terrain.py, see [[los-terrain-lavadirt]]). My read: the blocking rule excludes both endpoints (own hex always visible), so the likely path is the NewTurn PENDING rebuild (FLAG broadcast 0x20020008 → observers re-register) missing that army. User could NOT reproduce 11/14. If it recurs: get the save / exact map + hex, then probe fog refcounts live. Do not patch blind (refcount-critical).
