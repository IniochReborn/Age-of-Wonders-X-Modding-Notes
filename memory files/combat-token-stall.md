---
name: combat-token-stall
description: "2026-11-21 RE of two tactical-battle freezes (Wrath of the Three, day 1, independents attack Orc hero + 2 AI allies): MP stall = stranded unsequenced AI event in a seat that the battle switched to remote (vanilla ordering bug in TTacticalCombat.Initialize); SP freeze = TCombatMoveTE.DefaultMove returns 1 forever (cause not pinned). MP fix APPLIED 11/21 (patch_combat_remote_tc_purge_v1, untested in game); Ctrl+F report now dumps the stuck unit."
metadata:
  node_type: memory
  type: project
  originSessionId: 108b2769-0a18-4fbc-868e-7c4d29f920b0
  modified: 2026-11-21T23:15:47.505Z
---

User report 11/21 (~18:00, logs + 2 bug saves in `X\Bug Report`): battle freezes, no error pop-up. Likely the same thing as the shelved 11/16 silent MP lock-up in [[mp-host-migration-oos-handler]] (log format: [[error-log-oos]]).

**MP stall (2 instances, 17:58 session) — root cause found statically:**
- TTokenExecuter.Process 0x55803FD0 asks the active token control `VMT+4` (Fetch 0x55803A0C). Remote mode (1): counts head events whose seq [ev+0xC] == executed+i (0x5580398C); 0 → Process returns and waits. Local (0) / global (2): numbers its events and hands them over (local also adds TSyncTE + TPassTokenTE).
- AoWTC.TTacticalCombat.Initialize 0x429088 (TCPCK): (1) controlling human [combat+0x4C] = FIRST human on the MAP (kind [player+0xA7]==0, [player+0x45]!=2), not a battle participant; (2) every non-human combat player gets that human's PCC connection mode + system id; (3) only THEN ClearEvents on token controls that are Local or Global (loop 0x4292FF).
- So on every machine except the controlling human's, the AI seats are already remote at step 3 and keep their queued unsequenced AI events (seq -1). Seen: TNegotiateTE (AI diplomacy) at the head of seat 11's list, with the real remote events (TSyncTE 0x1AA ...) sorted behind it → that machine waits for ever at executed 426, status 0, lock 0.
- Needs: network game, AI player in the battle, that AI has a pending world-map event at battle start (common in simultaneous turns), and a non-controlling machine.
- **Fix APPLIED 11/21 (user: "fix it"; NOT yet run in game): `patch_combat_remote_tc_purge_v1.py`** (`.bak_tcpurge`): the `call TTokenControl.Global` at 0x429332 -> cave 0x43E820 (88 B; next free TCPCK cave 0x43E880, zone to 0x43E900): global -> vanilla ClearEvents; otherwise delete only the events with seq == -1 (counted remote events stay: the controlling machine may already have sent them). Network.dpl list routines reached from the ClearEvents import slot 0x46EA1C + fixed distances (PIC). Ship AoWTCPCK.dll to every player.

**SP freeze (17:56 session, network 0):** seat 10 (human) TCombatMoveTE, state [te+0x10]=1, steps [te+0x18]=1, retried every frame (tries 356 in 11 s). TMoveTE.Execute 0x557478BC → ProcessMove → LastMove → CombatTE.TCombatMoveTE.DefaultMove 0x408864 (TCPCK). It returns 1 (= still moving) for ever when: the unit [te+0x1C] fails TCombatUnit.GetEnabled 0x55724B70 (TUnit nil, flags [+0x47]&9, or byte [+0x54]); or the unit HS keeps Moving; or the turn call HS VMT+0x11C never starts a step. [+0x54]=1 is set in TCombat.AddArmy 0x55727804 for a unit that is not ValidTerrain on the battle terrain while the army's Transporter is (passenger). Which branch it was is NOT known — the report does not dump the unit. Battle was at x 0x24, y 0x29, level 4, terrain bytes [data+0x20]=3, [data+0x21]=7.

Other facts: combat player records are keyed by (army owner [army+0x12], [army+0x16]) (TCombatPlayerList.IndexOf 0x557288E0), record +8 map player, +0xA side; GetSide reads the record of the unit's combat player. Event Execute = VMT+0x4C; an exception inside is caught by the executer and counts as done. AoWEPACK/TCPCK export Delphi symbol names (pefile export table) — use them to name routines.

**11/21 user on the SP freeze:** the only unit he controlled was the Orc hero, and he only MOVED it (no attack). Walk-frame overflow ruled out (GetMoveSteps 6..12; tactical 0x420738 by movement-speed setting). To pin it, the Ctrl+F report (AoWxLog.dll 53248 B, installed in the project, emulator 76 checks, not shipped) now dumps for the first event of the executing list: object at [ev+0x1C] (0x70 B; combat unit: +0x45 player, +0x47 flags, +0x4C TUnit, +0x54 disabled, +0x60 HS), its +0x60 (HS: +8 flags, +0x14 direction, +0x15 move frame, 0xFF = not moving) and its +0x4C. NEXT: user reproduces the SP freeze and presses Ctrl+F; read those three blocks. Backups backup\AoWxLog.dll.bak_preunit / build_aowxlog.py.bak_preunit.
