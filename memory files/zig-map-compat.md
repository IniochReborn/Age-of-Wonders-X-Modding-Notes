---
name: zig-map-compat
description: "2026-11-07 Ziggurat-made maps in AoWx: offline .hsm scan vs both Release.hss; UG Ziggurat RID alias 0x06023E87 appended (build_zig_rid_alias_hss_v1); APPLIED untested"
metadata:
  type: project
---

User 11/07: "Highpass (Rockfeller_Route).hsm" (Ziggurat map) crashes the editor after a bunch of errors.
- Offline scan (scratchpad hsm_scan.py / hsm_units.py pattern): every level's hex stream = level record field table at loff+4, stream [lb+lf[6], lb+lf[1]) (level 1+ have an extra field 5 - hsm_grid's `lb+2` only fits level 0); hex children with tag ≥0x32 = objects: u32 class + table, field 1 = ResourceID (== HSS record field 1; HSS key = (resource class, EditID f2, EditIndex f3), map object class = resource class − 1). Units = class 0x20213 (TUnit) field 10 = unit type index (found by brute scan of the whole stream, not nested in hex records); TArmyHS 0x20217, THero 0x20230, TLeader 0x20232, TItemHS 0x20271, TExplorationSite 0x203C1.
- Result: only RID 0x06023E87 x2 (level 1) unresolved = Ziggurat's UNDERGROUND Ziggurat (their child 701), which build_underground_structures_hss_v1 re-numbered to 0x5A1A0001 in ours. Units ≤261 all exist; all classes known.
- ❌ REVERTED 11/07 (user: "revert that change. you copied his ziggurat defender list which i dont want"): build_zig_rid_alias_hss_v1.py appended a copy of our 0x5A1A0001 record (= Zig child 701 verbatim incl. Zig's defender list) under RID 0x06023E87; restored from .bak_zigalias. Do NOT re-apply. The map holds TWO full UG Ziggurat structure objects (level 1 (32,12) and (19,71), tag 51, fields 1,3,4,5,6,8,9,98); user had noticed only one.
- If the map still crashes: it's not a missing resource - get the error text / VEH log. Ship Release\Release.hss.
- **11/07 v2 APPLIED** (user: 'now i cant open the map ... redo the fix, except this time keep my defender list, not his'): alias child 1163 RID 0x06023E87 = our UG Ziggurat 0x5A1A0001 record, no EditID/EditIndex, with field 25 (defender groups: ffffffff-separated unit-index lists) taken from OUR surface Ziggurat 0x04870B74 (the user's edited list; only content field differing from Zig). ⚠ our own UG Ziggurat 0x5A1A0001 still carries Zig's field 25 (user not asked yet).
- ⭐ **11/07 REAL CAUSE of grey view + "exception occurred during CloseHSM"** (found with `diag_veh_logger.py --exe AoWDevX.exe --args "<map.hsm>"` - the agent shell IS elevated, editor opens ParamStr(1) .hsm): AV [nil+0x10] in AoWE.TAbstractUnit.RegisterEnchantments+0x56 (0x5577F2F2, from TArmyHS.Activate at map open) and UnregisterEnchantments+0x56 (0x5577F37E, at close): unit HasAbility (VMT+0x4C) true but GetAbility 0x5574F1C4 (guard cave 0x55811000 + own list [unit+0x10]) returns nil for a Highpass hero/leader. Fix `patch scripts/patch_enchant_nil_guard_v1.py` (.bak_enchnil): sites 0x5577F2F0 / 0x5577F37C (`8B D8 8B 43 10`) → cave 0x558E16C0..0x558E1700, nil → loop skip 0x5577F31D / 0x5577F3A9. APPLIED; re-run under the logger = 0 exceptions during open. Which ability is mismatched is NOT yet identified (probably granted from outside the unit's own list, e.g. items).
- ⚠ Never use ImageGrab/desktop screenshots to check the editor - it captured the user's private browser (deleted). Check via the VEH log / ask the user.

- ✅ **11/07 FIXED (user angry: "underground ziggurat has all the BXL/ziggurat defenders. i specifically told you to ensure our AoWx defender list was preserved")**: `patch scripts/fix_ug_ziggurat_guards_v1.py` (.bak_ugzigguards). Field 25 of 0x5A1A0001 (child 1151) := the CURRENT field 25 of the surface Ziggurat 0x04870B74; only that field changed (asserted). Today's editor save had regrouped Zig's list and changed field 10; that edit is kept.
- The 6 UG altars (0x5A1A0002..07) have NO field 25 → nothing to fix there.
- 🛑 11/07 follow-up: the user said surface and UG lists "had different defender lists. refer to previous version".
  - Copying the surface list was WRONG, so I reverted it (restored .bak_ugzigguards = their 21:13 save).
  - No on-disk version ever had a distinct AoWx UG list. 0x02F45441 = the Azrac Great Pyramid, not a Ziggurat.
  - The user then EDITED THE UG ZIGGURAT LIST MANUALLY in the editor.
  - NEVER touch field 25 of 0x5A1A0001 again. Do not re-run fix_ug_ziggurat_guards_v1.py.
