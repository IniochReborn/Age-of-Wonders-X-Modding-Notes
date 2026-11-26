---
name: comb-res-lost-records
description: "2026-11-02 comb_res.pfs lost the water combat hex, node centre structure and Sky hex (engine re-save drops palette-cell-sharing clones) → water battles grass+flashing; repair_comb_res_v1.py; 1.37.430 shipped the broken file"
metadata:
  node_type: memory
  type: project
  originSessionId: 712cd838-db3e-4743-9a21-0d55de64f3b1
  modified: 2026-11-03T02:53:49.493Z
---

**Symptom (MP 11/01, user screenshots):** water-node battle (Altar of the Gods, node at 64,73) = all grass + flashing hexes; flashing hexes in a village battle too. User suspected Eagle's Nest — the Nest's combat-map hook (TCPCK 0x4249E1 → NST1) only fires for RID 0xE1608C, so it was not the cause.

**Cause:** live Release\comb_res.pfs had been RE-SAVED by the engine (30 records differ only in anim start-frame bytes) twice: between 10/31 04:47–16:36 and after 18:46 (mtime 22:33). The save keeps ONE resource per palette cell (record field 2 = page, field 3 = cell). Clones copied their source's cell, so the save dropped: **0x5A8502 water combat hexagon** (vanilla child 569) and **0xAA0E01 Sky hex** (shared cell 6 with Chasm 0xAA0B01), then **0x15F5B08 node centre structure** (vanilla child 579, shared with the Nest clone 0xE1608C). Child numbers shifted by the removals, so any script indexing by child number (eagle v3–v10, sky polish) read the wrong records afterwards. The .bak_eagle3/4/5/10 backups are ALREADY broken; the last good one is `.bak_skypolish5`.

**Fix:** `patch scripts\repair_comb_res_v1.py` (.bak_repair1): vanilla order 0..580 (live bytes, lost ones from .bak_skypolish5) + 581 Sky / 582 Chasm / 583 Nest; RIDs verified unique. Status: APPLIED 11/02 after the user closed AoWDevX (closing it did NOT re-save comb_res; mtime stayed 10-31 22:33); awaiting in-game retest of the water node.
⚠ **1.37.430 release zip ships the broken comb_res.pfs** → a re-cut is needed.
⚠ Lessons: look up pfs records by RID, never by child number. Give a cloned record its own palette cell, or the next engine save deletes either the clone or its source (but a 4th Sky clone on its own cell crashed the editor; see [[map-levels-29-plan]]). After any editor session, check that comb_res.pfs mtime hasn't changed. Related: [[eagle-nest-gfx]].

**11/04 recurrence + PERMANENT FIX (APPLIED, awaiting editor-save test):** user's Hydra SFX edit = AoWDevX data save
at 20:40 re-wrote ALL Release files -> comb_res lost 0x5A8502 + 0x15F5B08 again (damaged copy
backup\Release\comb_res.pfs.bak_editorsave1104); repair_comb_res_v1 --apply restored them. Root fix
`fix_comb_res_cells_v1.py` (.bak_cells1): clones moved to free cells - Sky 0xAA0E01 34/6->34/2, Chasm 0xAA0B01
34/6->34/3, Nest 0xE1608C 38/1->38/5 (field 3 u32 in place, CRC fixed). Release.hss scanned: 0 shared cells.
User edits in AoWDevX regularly -> after their next data save, verify comb_res still has 584 records.
