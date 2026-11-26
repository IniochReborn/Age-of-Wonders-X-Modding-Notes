---
name: oos-420-superstack-getbusy
description: "10/21 LAN OOS in clean 1.37.420 shortly after turn start; prime suspect = AI superstack calling the human MoveArmyXYL path, whose TPlayer.GetBusy gate reads the in-progress combat [map+0x120] (timing-local)"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T01:50:43.650Z
---

**Report 10/21:** everyone on a clean 1.37.420 over LAN. Every machine gets the OOS (host included) shortly after the turn starts. The game has AI players and many roaming independents. A full relaunch by everyone did NOT help, so the stale `.idata` tables (below) are not the cause. The user said **no reverts**: fix forward only.

**Static findings (unproven, no MP log yet):**
- In vanilla AoWEPACK nothing calls `MoveArmyXYL` 0x5574A490. In 420 the only callers are the superstack cave (0x5581978B / 0x558197DD), see [[ai-superstack]].
- `MoveArmyXYL` builds a `TMoveControlSettings` (class cell 0x5570CC14) and runs `TMoveControl.ProcessMove` 0x557466F8 on `[map+0x184]` (TMoveControl). If the path count is above 1 it calls `MoveArmyEx` 0x5574A318, which queues the TE on `[map+0x23C]`.
  - Pathing uses `ExploredOnlyMoveOnMovePointProc` with mask `1 << (owner−1)`, where owner = `[settings+0x6C]` (the army owner). That is synced state, so the pathing is fine.
- `MoveArmyEx` with `[ebp+8] == 0` checks `TPlayer.GetBusy` 0x557516D0. The cave pushes 0, so it hits that check.
  - GetBusy reads `[player+0x48]`, the player's TE queue (vcall +0x14), and `[map+0x120]` = the combat in progress (set by `TAoWHSMap.CreateCombat` +23, cleared by `DestroyCombat`). It then inspects `[[map+0x120]+0xC]`, plus `[map+0x239]` and `[map+0xA4]`.
  - Every vanilla caller of `MoveArmyEx` is human UI: `TSelectedArmy.ExecuteMove`, GlobalTargetSpells, `TCave.EnterEx`. The vanilla AI moves through `TMultiMoveTE` instead.
- **Hypothesis:** whether a combat is in progress at the moment the AI step runs differs per machine. A refusal sets the cave's day count to MAXMOVES ("stop for the day"), so the AIs diverge.

**Proposed forward fix:** a superstack v2 that passes flag 1 (skips GetBusy) and/or never ends the day on a refusal. Confirm with the desync logger (see [[lan-desync-investigation]]) on the host plus one client.

**Secondary bug, real but not this OOS:** these per-process `.idata` tables are zero only at process start. They are not reset on a new game or on load, and they are not saved:
- superstack 0x5590B5A0
- converge A 0x5590BC80
- table B 0x5590B510
- loot C 0x5590B420
- end-enchant 0x5590BE50
- diplomacy PEND 0x5590BF40

So they desync after a second game in the same session. Fix: clear them at game start and on load.

**10/21 APPLIED (1.37.421 dev, untested in MP):** `patch scripts\patch_mp_hotfix_421_v1.py` (`.bak_mphotfix421`; dry-run/--apply/--revert/--dis):
- Fix A: the superstack flag push at 0x55819781 / 0x558197D3 changes from 6A00 to 6A01, so the GetBusy check is skipped. A refusal still ends the day, but refusals are now state-only.
- Fix B: the tail jmp of the defender-retaliation Create cave at 0x5581168A now goes to cave 0x55833000 ('MPH1', 167 B; zone to 0x55833100). That cave zeroes the 6 tables listed above, then continues at 0x557748AA.
- `patch_version_421.py` applied (imm 0x1A5; `.bak_ver421`).
- ⚠ The superstack v1 dry-run now says ABORT (its zone bytes changed). Revert the hotfix BEFORE reverting superstack.
- ⚠ The memory index's next-free note (AoWEPACK 0x55864300) was STALE: patch_drought_v1 uses it. Find free zones by scanning the scripts' range claims, not by trusting the index.
- Release cut not done yet: 421 waits for the leadership-retreat OOS fix (forked investigation, see the leadership memory).
