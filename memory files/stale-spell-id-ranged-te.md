---
name: stale-spell-id-ranged-te
description: "2026-11-26 player bug reports - ranged abilities ran spell caves via a stale spell id in the ranged TE (factory fix), Rejuvenate/Wither converted Sky/Chasm (guard); patch_bugfix_1126_v1 APPLIED untested"
metadata:
  node_type: memory
  type: project
  originSessionId: 68b90611-fe84-4697-9c6a-555af87cda75
  modified: 2026-11-27T01:13:46.876Z
---

**Reports 11/26 (players):** (1) aim Sandstorm (or any spell), then use Hurl Skull / Archery / darts / breath -> many shots, spell animations, Hellfire -> lock-up; (2) Rejuvenate covered Sky on the surface; (3) made islands in the Firmament.

**Cause 1:** the ranged TE (TCPCK class cell 0x40795C, Execute 0x40B2F8, +0x14 ability, +0x18 spell id, +0x24 kind from SpellTypes or AbilTypes) has ONE factory 0x40F4B0, called only from 0x4238B5 with the unit HS's [hs+0x34] action and [hs+0x38] last-picked spell. [hs+0x38] is never cleared -> non-spell TEs carry a stale spell id. Vanilla reads [te+0x18] only behind `cmp [te+0x14],0x34`; our caves test the spell id alone.
**Cause 2/3:** patch_terrain_spells_v1 rule "anything but 0/6/9" (map caves 0x55862459 / 0x5586246C, target test 0x5586249E) included Sky 0xE / Chasm 0xB.

**Fix:** `patch_bugfix_1126_v1.py` (`.bak_bugfix1126`, both DLLs, --revert restores bytes): TCPCK factory store 0x40F52D -> cave 0x455000 (spell id kept only when ability == 0x34); AoWEPACK three 5-B jumps -> cave 0x558BB000..0x558BB0B0 (adds 0xB/0xE). APPLIED 11/26, NOT tested in game. Ship AoWTCPCK.dll + AoWEPACK.dll.

**11/26 user: both fixes WORK in game.** Follow-up same day: Freeze Terrain preview glowed over Sky etc. because patch_frost_terrain_v1 had widened both TFreezeWater gates (0x5579EBA0 field ebx, 0x5579EBF0 field esi) to accept everything -> `patch_freeze_terrain_targets_v1.py` (`.bak_freezetgt`, cave 0x558BB100..0x558BB140): valid = terrains the spell acts on {0,1,2,4,5,6,9,0xA,0xD} (my choice: snow/dirt/rock/earth/sky/chasm rejected; also blocks casting centred on those if the MapF gate is the click test - unverified). APPLIED, untested. AoWEPACK next free 0x558BB140.

Snow added to the valid set later the same day (user). **Thousand Threads 11/26 (user):** now ONE roll, Chance(web strength 4 − RES), no Defense roll (user rejected my strength 7: "4 like the Web ability"). Only the `cr` cave of patch_threads_v1.py changed, written IN PLACE (its EX site is chained by a later patch → the script ABORTs on apply/revert; script now has fixed CAVE_OFF layout + STRENGTH const; pre-change copy backup\AoWEPACK.dll.bak_threads2). Untested. ⚠ patch_dual_sphere_spells_v1 dry-run would rebuild Spells.pfs 140970 → 148205 B: the live pfs has later edits (e.g. descriptions rewritten) — do not --apply the pipeline without diffing first.

**Sky/Chasm audit 11/26 (subagent read of the scripts, not re-verified by me; nothing changed, awaiting user's pick):** no other spell converts 0xB/0xE (Drought/Overgrowth/World Healer/Ice Age/Pyroclasm lava/Tectonic use whitelists; Raise Terrain's per-hex conversion is filtered by the guarded ValidTargetMapF; Flood/storms/Paths guards live). Gaps: Drought `waterok` counts Sky/Chasm/rock/earth/lava neighbours as land (water beside the void gets desert-filled); Pyroclasm volcano conversion + Tectonic growth have no terrain check on old-footprint / art-only hexes (only matters for a mountain already on/next to Sky); `t_open` connectivity treats 0xB/0xD/0xE as walkable. **Roll audit:** Banshee Gale panic = damage hit then str 6 vs RES (double); Holy Water Turned gated on the ATK 7 vs DEF hit; Tame Animal = vanilla touch (2 rolls); others single/no roll.

**User picks 11/26:** fix Drought coast + t_open; volcano/mountain-overhang gaps and Banshee Gale / Holy Water / Tame rolls are FINE AS IS (do not re-raise). `patch_sky_void_checks_v1.py` (`.bak_skyvoid`): same-size in-place edits, Drought waterok 0x55864409 → land whitelist {1,2,3,4,5,0xC}; t_open Tectonic 0x55874FD2 / Pyroclasm 0x5587C8A8 → closed {0,7..0xB,0xE}; emulated for all 16 terrain ids, APPLIED, untested in game. ⚠ owning scripts' sources unchanged — re-run this after any re-sync of the drought / tectonic / pyroclasm zones.

**How to apply:** new TC caves keyed on a spell id should still be safe now, but targeting PREVIEW caves read [hs+0x38] directly (not fixed) - gate those on [hs+0x34]==0x34. A stale id also arose without the trick (hero casts, later shoots) - possible source of old silent combat lock-ups, see [[combat-token-stall]]. Other terrain-changing spells were not re-audited for Sky/Chasm beyond the guards listed in [[map-levels-29-plan]].
TCPCK free runs (scanned 11/26): 0x455040..0x45B800 is zero and unclaimed by any script; older "next free" notes (0x43E820, 0x43B100) are stale. AoWEPACK next free after this: 0x558BB100.
