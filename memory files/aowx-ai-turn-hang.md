---
name: aowx-ai-turn-hang
description: "Athendore AI never-ending-turn livelock — diagnosis state, AI engine RE map, live-probe tooling"
metadata: 
  node_type: memory
  type: project
  originSessionId: 64f23c3c-c707-4f6d-951f-7cfeb00abf5a
  modified: 2026-08-24T03:52:30.864Z
---

**Bug:** On "AoWx - Athendore" (huge, teleporter-heavy), AI players sometimes never end their turn (reported: Frostlings turn 8; reproduced live: Azracs day 6, 2026-08-23). NOT a hard hang and NOT slow computation: a **livelock** — one AI group cycles target-select→move-execute→abort ~13x/s forever, so the queued TEndTurnAIPA never runs.

**Live diagnosis (game running, PID attach):** AI runs time-sliced on the MAIN thread from TAoWHSMap.NewFrame → TAIExecuter.Process (map+0x128) → per-player TAIPlayerControl.Process. Stuck player p3 "King Grinton" (Azracs): phase=1, action list stuck at 6 with curact = **TGroupControlAIPA**, whose current group control = **TNormalAGC** stayed pinned on ONE army for minutes. Queue behind it: TStructurePhase2AIPA, TDiplomacyAIPA, TCityAIPA, TAutoProduceAIPA, TEndTurnAIPA.

**AI engine RE (AoWEPACK.dll, preferred 0x55700000; use AoWEPACK.asm listing):**
- Global `AoWE.AoWHSMap` export @RVA 0x1FA040 → map object. map+0x118/0x11C gate NewFrame AI; map+0x128 TAIExecuter; map+0x12C TAIPlayerActionManager; map+0x140 TPlayerList; map+0x239 phase byte (1=?, 2=in-turn); map+0x23C token control.
- TPlayerList+0x08 → TList{+4 items,+8 count}. TPlayer: +0x48 busy-lock, +0x88 TAIPlayerControl, +0xA6 index byte, +0xD4 leader(+0x60 name string).
- TAIExecuter: +0x08 tick ctr, +0x0C TByteList AI players, +0x10 cur player, +0x14 cycles, +0x18 flags, +0x30 lock.
- TAIPlayerControl: +0x08 player, +0x0C TAIPlayerActionList(+0x08 TList), +0x10 cur action, +0x1C TAIMoveExecuter, +0x20 phase byte (1=actions, 2=?).
- TGroupControlAIPA: +0x14 work ctr, +0x18 current TAIGroupControl(TNormalAGC), +0x1C group idx?
- TNormalAGC: +0x08 loop ctr (~13/s when stuck), +0x0C TNormalAG group, +0x14 field idx, +0x18 TArmy cur, +0x1C TArmyHS, +0x24 TAIGroupControlTargetList (had 101 targets), +0x44/+0x48 packed locs.
- TNormalAG (is-a TUnitList): +0x04 TAIGroupManager, +0x08 TEObjectList units, +0x18 leader TUnit, +0x38 current target loc.
- TArmyHS+0x04 → ptr INTO map field array (TAoWMapField records, stride 0x1C, rec+0x10 = field index).
- **Location encoding: (level<<16)|(y<<8)|x** (256x256 grid per level).
- Stuck army @ level 2 (Depths) (x=59,y=46); its group target @ level 1 (x=71,y=25). Delphi class names readable at runtime: [[obj]]→VMT, name ShortString ptr at VMT-32.

**Tooling (session scratchpad, rewrite from this spec if gone):** aiprof.py = elevated WOW64 EIP/stack sampler w/ AoWEPACK export symbolization (Wow64GetThreadContext offsets: Ebp=180 Eip=184 Esp=196 of 716-byte ctx; game runs ELEVATED → probes need RunAs/UAC); aistate*.py = live AI-state readers via the AoWHSMap global. AoWEPACK exports dumped by name+RVA (10036 syms) for symbolization.

**ROOT CAUSE (confirmed 2026-08-23, second session of probing):** Deleting the stuck army just moved the livelock to ANOTHER army (single Nymph, curMP=0, at (86,40) lvl2, target (79,32) lvl2) → systemic. Full mechanism:
- TGroupControlAIPA.Process: picks next group without flag bit1 (group+0x10 & 2 = "processed"), runs TAIGroupControl.Process until it returns false (= flag set by Done).
- TNormalAGC.ProcessStates state machine (state dword agc+0x16C, active plugin agc+0x168, target selector agc+0x170): 0 DefenseControl → 1 TargetFinder (empty group→Done) → 2 RecruitmentGroupFinder (no targets→10) → 3 ProductionLocationFinder → 4 TargetSelector setup (float weights) → 5 selector runs; on completion reads selector+0x1C "kind": 5→activate TAIGroupRazeControl, state 6; 4→10 (DefendTargetSelector→11→Done); else→Done. **State 6: if player+0xA7 (AI level) ∈ {3,6,7} → state:=0 RESTART else Done.** Observed live: state cycle 5→(6,0,1 invisible)→2→3→4→5 every ~1.7s forever; p3+0xA7=7.
- Livelock = selector repeatedly yields kind=5 (raze target) that can never be executed (army 0 MP / unreachable), raze control no-ops, state 6 restarts pipeline. Each pass burns ~1.7s of pathfinding/battlefield scans (the "slow AI" CPU burn).
- **AoWx's pool-raze feature is the trigger amplifier**: patch_reflecting_pool_raze_v1.py sets TReflectingPoolResource razeable flag [res+0x58]=1 (vanilla: pools NOT razeable) → AI raze-target surface exploded on pool-rich maps like Athendore. TDefenderAGC (+ likely other AGC classes) have their OWN copies of the same state machine incl. the state-6 restart.
- More offsets: TUnit+0x3D curMP, [unit+0x40]=TUnitResource (+0x1C race name str? +0x24 type name str, +0x2D max moves, +0x20 race byte); TPlayer+0x2C endturn flag, +0xA5 race idx, +0xA7 AI level; TArmy+0x12 owner, +0x13/14/15 x/y/level; TAIGroup.GetMovesMin export usable.

**ACTUAL restart edge (found by live injection, superseding the state-6 theory):** the real uncapped restart is **TAIGroupControl.MoveExecuterDone** (AoWEPACK RVA 0x38C66): when TAIMoveExecuter result byte (mx+0x2C) == 5 (InvalidateMove / Process-exception "plan invalid"), it does `xor eax,eax; mov [agc+0x16C],eax` — resets the group's ProcessStates machine to 0 UNCONDITIONALLY. Live sampling: result byte pinned at 5, state cycling 5→2→3→4→5, ~1.7s/pass. Patching the AI-level byte 7→2 did NOT help (ruled out the state-6/level-gate theory). A GetMovesMin>0 gate also did NOT help (group had a 0-MP Nymph but the *group min* was 0, yet other units had MP — and re-planning still never converged). What DID work: **a restart counter.**

**FIX SHIPPED — build_ai_group_restart_cap.py (2026-08-23):** at RVA 0x38C66 (10-byte site `33C0 89836C010000 5BC3`) jump to cave RVA 0x10C3C0 (file 0x10B7C0, 0x40 zero slack right after pool-raze caves). Cave: `inc byte[ebx+0x156]` (restart counter in the padding byte after word@+0x154; ONLY other +0x156 user in AoWEPACK is TAoWMapControl, different class; objects zero-init so it resets per group-control activation), `cmp al,20; jb allow; else mov eax,ebx; call TAIGroupControl.Done (RVA 0x389B0); allow: original xor/mov/pop/ret`. Position-independent (ebx-rel + rel32); reloc table checked clear. **VERIFIED END-TO-END: injected live into the stuck game → dwarves ended turn in 52s** (a livelocked group now costs ≤~35s once, then Done marks it processed). Cap 20 restarts. House-pattern script, backup AoWEPACK.dll.bak_airestartcap.
APPLIED TO DISK 2026-08-23 (late evening, after user closed game + AoWDevX — the EDITOR also locks AoWEPACK.dll); bytes verified on disk and inside the zip. Changelog mirrored: user added "Fixed AI pathfinding bug" (+detail sub-bullet, and reordered the Misc section) to changelogs.txt; manual 406 items array REGENERATED wholesale from the txt (scratchpad update_manual_406e.py — parses the txt section, rebuilds the JSON items array in place with count/parse verification; backup .bak_406e). Final 406 artifacts (fourth cut that day): AoWx_1_37_406.zip + installer both contain the patched AoWEPACK.dll and updated manual — verified inside the zip. Everything shipped and consistent.
Live-injection tooling in scratchpad: inject_gate.py (site hook + GetMovesMin gate v1), inject_gate2.py (cave→restart-cap v2, the shipped logic), unstick.py (AI-level poke, didn't work), aistate7-11.py. WriteProcessMemory patching suspends all threads + checks none's EIP is in the patched range first.
