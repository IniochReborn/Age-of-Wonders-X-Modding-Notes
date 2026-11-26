---
name: save-skipped-units-abilitydata-guard
description: "11/22 a tester's Shattered Peaks saves: units vanish after reload because the save SKIPS units with a duplicate ability-data record (EDoublePrioriyID); suspected cause = GetAbilityData guard cave 0x55811000 address range; .asg unit parser recipe"
metadata:
  node_type: memory
  type: project
  originSessionId: 5c12d565-3244-4a28-ba8c-c8f2ac12c9a3
  modified: 2026-11-22T22:44:36.979Z
---

**Report (tester a tester, 1.37.434, hotseat, his map `AoWx - Shattered Peaks`, 11/22):** machines "disappear" (Guild Balloons, Flame Thrower Rams), a leader shows Marksmanship I although 9 points were spent, editor log `EDoublePrioriyID: Double priorityID found (158)` in TEWriteStorageStream.rwCreateEObject <- TAbilityOwner.ReadWrite <- TAbstractUnit.ReadWrite. The user loads the same saves without seeing a problem.

**Proven from the files (X\Save: autosave - combat2 -> autosave - combat -> autosave (3), one game, day 2):**
- 20 units are absent from the later saves with HOLES in the army slot numbering (7 armies, e.g. slots [1,4,5]); no other save on disk has slot holes. A hole = the unit was alive in memory and its write threw, so the writer dropped it; it is gone after the next load.
- All 20 are Leadership-aura FOLLOWERS (ability-data id 0x2E, class 0x202CE, tags B/19/1A = own 0, borrowed level, source name), of 8 different players, in a turn where only the Azrac player acted. The other 13 units lost in that step are battle casualties.
- The priority id in the message = ability-data id + 0x32 (TAbilityOwner.ReadWrite writes each record with tag id+0x32, list of ids in tag 0x31). 158 = id 108 (0x6C); a duplicate Leadership record would say 96.

**Suspected cause (my inference, NOT verified on a tester's machine):** `TAbilityOwner.GetAbilityData` 0x5574F1C4 is hooked to the guard cave 0x55811000 (`build_abilitydata_guard_recorder.py`, 8/13): it returns nil for the whole owner when any of the first 32 chain nodes lies outside 0x400000..0x40000000. Valid Delphi heap blocks outside that window (below the exe image or above 1 GB) make existing records invisible: SetExternalSource / ResetExternalSource then add a second 0x2E record on every formation update (duplicate -> save drops the unit), and a hero's level record is not found (Marksmanship shown as I). First rejection is recorded at 0x558FAF40 (`--read` on a live process).
**11/22 FIX APPLIED in the project, emulator-tested (12 checks, `--test`), NOT run in game, not shipped:** `patch scripts\patch_abilitydata_guard_v4.py` (backup backup\AoWEPACK.dll.bak_abguard4, cave 0x558BAC00..0x558BAD7E 'ABG4'; next free AoWEPACK cave 0x558BAE00). A: hook 0x5574F1C4 now -> new guard 0x558BAC04 (old cave 0x55811000 left as dead code; `build_abilitydata_guard_recorder.py --status` no longer recognises the hook, `--read` still works): a node outside 0x400000..0x40000000 is checked with VirtualQuery (VCL30 IAT 0x413E4304 via the RandInt slot 0x558FB6DC) instead of being rejected. B: TAbilityOwner.ReadWrite write branch 0x5574F40B -> dedupe 0x558BAD32: later records with an id already seen are unlinked before the id list is written, so a unit with duplicates is saved whole. Units already missing from a save cannot be brought back. Ship AoWEPACK.dll. Open: confirmation from a tester that units stop vanishing.

**.asg / .hsm unit parser recipe (scratch scripts are gone after the session):** CFS+zlib; root table 0x13; root tag 1 -> container (tags 3/4 W/H, 1 levels); level tag 6 = W*H x [u32 len][hex record] in saves; hex child class 0x20217 = army: tag 9, tag A -> table {4 player (absent = independent), 5 x, 6 y, 1 units by slot}; unit class 0x20213 (hero 0x20232 / 0x20230): tag 2 count, 3 ability bitset, 31 data-id list, id+0x32 data records, 5 unit id, A = unit type word (Unitres key; hero: name string), 9 HP-like byte, 8 moves. Root tag 0x10 current player, 0x13 day; players = root tag 0x15 -> tag 1 list (tag 0x10 gold, 0x17 event log).
Related: [[aowx-leadership]], [[aowepack-ability-system]], [[error-log-oos]].
