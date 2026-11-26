---
name: overflow-army
description: Post-combat overflow (units that join a full stack via charm/dominate/convert) placed on an adjacent hex — patch_overflow_army_v1.py, TCombat.Finalize pass-2 RE
metadata:
  type: project
---
2026-10-18 APPLIED (VEH 6, untested): patch_overflow_army_v1.py (AoWEPACK cave 0x55882820, zone 0x55882800–0x55882C00, .bak_overflow).
- TCombat.Finalize 3 passes: 0/1 return units to their own party; side-switched units keep their old party index ([cu+0x46]) → placed in pass 2 via TAbstractUnit.Place (0x557810FC, spiral radius 29, flags 1 spiral / 2 ignore owner / 4 never join) at the combat target hex — call sites 0x55724EA9 / 0x55724ED1 / 0x55724F0E. Then TArmyCombatMoveTE.ExecuteCombat (0x55749D1D…) PlacePrivate's the movers onto the same hex → 2 armies on one hex.
- Fix: when the unit is the attacker's, movers + own units on target + 1 > TArmy.MaxSize and no foreign army there → spiral from ring 1 placing one hex at a time; else vanilla Place.
