---
name: Project state — confirmed working 2026-07-04
description: Snapshot of confirmed-working DLL state after rollback + AD/RS re-implementation. Use as revert reference.
type: project
originSessionId: 95f8d8d3-ecf1-4b23-b17b-97d2f2aac6d0
---
Game confirmed fully working as of 2026-07-04 (AD/RS, exploration sites, all features).

**Why:** Previous session accumulated broken Hero Slaying / Monster Slaying patches that caused runtime error 216 crashes. Full rollback to Jul 29 2025 base was performed, then only the confirmed-functional AD/RS changes were re-applied via `patch_ad_rs_combined_rollback.py`.

**How to revert:** Restore from `pre-claude rollback/Age of Wonders X - rollback/` (copy all files to project root, replacing everything), then run `patch_ad_rs_combined_rollback.py`. No other scripts needed.

## AoWEPACK.dll — Active patches

| Offset | From | To | Purpose |
|--------|------|----|---------|
| C12A0 | 83 78 08 01 | 31 C0 90 90 | Allow tactical combat UI for exploration sites in MP |
| 24166 | 0F 85 AA 01 00 00 | 90*6 | Animate Dead units persist after combat |
| F9526 | BA 82 00 00 00 | E9 62 38 01 00 | JMP to Recall Spirit spawn cave |
| F9549 | BA 82 00 00 00 | E9 84 25 01 00 | JMP to TRecallSpiritCA v5 summoned cave |
| F9746 | BA C9 00 00 00 | E9 C2 2A 01 00 | JMP to Animate Dead spawn cave |
| F9769 | BA 82 00 00 00 | E9 9A 23 01 00 | JMP to TAnimateDeadCA v5 summoned cave |
| 10BAD2 | 00*54 | (cave 54B) | TRecallSpiritCA v5: ExpandAbility(0x9B)+SetSource+upkeep |
| 10BB08 | 00*54 | (cave 54B) | TAnimateDeadCA v5: same |
| 10C20D | 00*902 | (cave 902B) | AD spawn: 18 groups, RDTSC RNG, 293B table |
| 10CD8D | 00*608 | (cave 608B) | RS spawn: 8 groups, RDTSC RNG, 293B table |
| 10D04D | 00*171 | (sub 171B) | Upkeep sub v2: 133->10, 243/216->8, 204/206/44->6, 200/223/241->3, else->2 |

## AoWTCPCK.dll — Active patches (present in rollback base, unchanged)

| Offset | From | To | Purpose |
|--------|------|----|---------|
| 1C7C | FF 25 30 E6 46 00 | B8 01 00 00 00 C3 | Defenders always attack turn 1 |
| 1AEDE | FF 91 F8 00 00 00 | 90*6 | NOP autocombat in SetSeatedCombatPlayer |

## AoWEPACK.dll — Additional patches

| Offset | From | To | Purpose |
|--------|------|----|---------|
| 5BA0E | 8B D9 | B3 01 | All units pre-installed in cities (VA 0x5575C60E) |
| C2D11 | 75 0F | 90 90 | Construct Towers underground |

## NOT currently applied (existed pre-rollback, now gone)
Monster Slaying (66D04/66D09), Hero Slaying cave+name (65ACF/10BB3E/B9DE0/10D169),
SE category patches (B9D08/B9E50), TResurrectHero vtable (EB5F0)

## Exploration site MP crash — pre-existing issue
AoWHSMap.NewFrame crash in AoWTCPCK.dll is a pre-existing MP bug, not caused by our patches.
Root cause and failed fix attempts documented in exploration-site-fix.md.
