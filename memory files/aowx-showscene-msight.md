---
name: aowx-showscene-msight
description: MapViewer.ShowScene error flood diagnosed 2026-09-17 = missing Images\Effects\MSight.ILB in the 410 prerelease install (Magic Sight cast FX); release-zip recipe carries the previous namelist so NEW files must be added by hand; diag_veh_logger fixes
metadata: 
  node_type: memory
  type: project
  originSessionId: 48505c9f-7655-4ff6-a2a6-f29a8d9c6de1
  modified: 2026-09-17T23:55:26.555Z
---

**"Exception during MapViewer.ShowScene" flood (2026-09-17, 410 prerelease, user first blamed AI Azracs summoning):** VEH log showed 46× AV read at 0x44 in ILPACK `TCustomImageLibrary.ImageExist` (ILPACK+0x1A91C) called from the AoWEPACK map-effect draw routine 0x557FBD08 (loops `[self+0x3C]` TImageSequence list, `[seq+0x10]` = image library, next at +0xC) inside HSEPack ShowScene (+0xD691 vcall VMT+0xA8 per map object). The TImageSequence's path was `EFFECTS\MSIGHT.ILB` and its library was nil: **Spells.pfs record 210 (Magic Sight, added 1.37.409) references the file but the 410 prerelease `Images\Effects` did not contain `MSight.ILB`** (only the project root `Images\Effects\MSight.ILB` had it, from build_magic_sight_castfx.py). One dialog per drawn frame until the cast animation expires; harmless otherwise. Fixed by copying the file into the 410 folder (2026-09-17). Not related to the healing/melee AI patches.

**Why:** `build_release_zip.py` re-reads the PREVIOUS zip's namelist, so a brand-new shipped file never enters the zip unless appended by hand — 409 was cut on the laptop and probably shipped without MSight.ILB too (no 409 zip on this desktop to verify). Before cutting 410: diff the project `Images` tree against the zip list (I_x2026.ilb for the x2026 items is another new file to check) and add the new entries. Player report "many ShowScene errors after casting Magic Sight" = this.

**How to apply:** `patch scripts\diag_veh_logger.py` now defaults to the `Age of Wonders X - 410 prerelease` folder (optional argv[1] = game dir) and skips 64-bit modules in the WOW64 module list (the old code picked the 64-bit ntdll and crashed in probe_addveh). Launch the game through it, reproduce, read `patch scripts\veh_log.txt`; the ring at 0x001D1000 (32×0x440) stays readable in the live process for full stack copies. Related: [[aowx-bag-ability-crash]], [[aowx-release-process]], [[aowx-410-pending-tests]].
