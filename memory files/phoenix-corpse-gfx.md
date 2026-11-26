---
name: phoenix-corpse-gfx
description: "10/22 RE + plan (NOT applied) for an orange Phoenix corpse; corpse gfx = the last slot of the unit's Unitgfx tag-5 stream (DeadUnit.ILB ids); unit 271 inherited the Great Eagle's 130/131"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T07:18:11.977Z
---

User 10/22 (pre-422 list): the Phoenix (unit 271, see [[lifefire-spells]]) leaves the Great Eagle's corpse; it should be orange.

**How a corpse graphic is chosen (data only, no code):**
- Release\Unitgfx.pfs, unit record, tag 5. It is a TImageSequenceList stream; the format is in build_phoenix_unit_v1.py `add_glow_layer`.
- Its LAST slot is the corpse: `00 | len32 "UNITS\DEADUNIT.ILB" | f8 00 | f18 09 (delay) | kind 04 (frames) | i32 f20=1 | i32 xs | i32 ys | i32 0 | u32 n | n×u32 image ids | u8 hasSub 00`.
  - The Eagle (234) and the Phoenix (271) both have xs -18, ys -20, ids 130, 131 ("D_Animal.BMP").
- build_phoenix_unit_v1 copied the eagle record and only swapped the EAGLE.ILB path, so the corpse stayed the eagle's.
- Every unit's corpse is in Images\UNITS\DeadUnit.ILB (vanilla, 495,989 B, 257 images, ids 0..322).
  - Add_DeadUnit.ilb (type-2, ids 101..712) is referenced by NO unit; it's a leftover.
  - Kind 0 (a still) is also used (unit 229).
  - Drawn tactically by TCCorpseHS (see [[aowx-dual-sphere-re-notes]]). There are no strategic-map corpses.
- DeadUnit images are **type 22 = RAW 16-bit 565**: size = cw*ch*2, transparent key word `transp` (31406), drawMode 256, no RLE. Images 130/131 are 46×28 at cx 7/12, cy 29 in a 62×62 frame.
- ilbcodec round-trips DeadUnit.ILB byte for byte.

**Plan, simulated in memory OK 10/22 (scratchpad phoenix_corpse_sim.py; preview phoenix_corpse_preview.png):** `build_phoenix_corpse_v1.py` (dry-run / --apply / --revert)
1. Append ids **323, 324** to DeadUnit.ILB. Each is ilbcodec.Rec(copy of 130/131) with name D_Phoenix.BMP and pixels recoloured: P.fire_ramp(lum*1.1); keep saturated blood-red pixels; never emit the key word. Size 495,989 → 501,339.
2. In Unitgfx.pfs record 271, the corpse ids 130,131 → 323,324 (P.split / rec_fields / rec_build / join). Exactly **8 bytes** change: the 4 id bytes plus the CRC.
   - Backups `.bak_phoenixcorpse`.
   - Idempotent state check: ids 323/324 present plus record ids.
   - Revert = restore both files.
- Order: run AFTER build_phoenix_unit_v1. Its unitgfx_record() re-derives 271 from the eagle and would reset the ids, so revert the corpse before re-running or reverting the phoenix.
- Release: DeadUnit.ILB and Unitgfx.pfs are existing files that change, so the zip's diff vs prev should pick them up. Verify the 422 zip contains DeadUnit.ILB.
- Variant B (P.brown_orange wing colours, softer) is in the same preview.
- Not covered: the blood-mod corpse pool colour (TCPCK corpse_cave, per-unit blood type) is separate and unchanged.
- 10/22 user: the corpse must not glow; use colours close to the Phoenix BASE sprite (no glow layer). Build sent back to the fork.

**10/22 user decision:** the corpse must NOT glow; its colours must match the Phoenix BASE sprite.
- `patch scripts\build_phoenix_corpse_v1.py` is WRITTEN but NOT applied. Dry run OK: DeadUnit.ILB grows 495,989 → 501,339 B; Unitgfx.pfs has 8 bytes differing.
- Recolour method: percentile matching of luminance.
  - Each corpse pixel's luminance percentile, among the corpse's non-blood pixels, is mapped onto the same percentile of every opaque PHNIX.ILB base pixel. That is 54,646 px, palette colours only; the glow layer lives in USHADOW.ILB and is not included.
  - Only the 4%–90% band is used, giving a ramp from (74,11,7) to (215,116,33).
  - Blood pixels are kept and darkened ×0.8.
- `--preview <png>`: eagle corpse | new corpse | Phoenix base frames 103/409. Scratchpad: phoenix_corpse_v1_preview.png.
- `--revert` rebuilds without our images and sets the ids back to 130/131; it notes if the result differs from the `.bak_phoenixcorpse` backups.
- The earlier fire_ramp / brown_orange previews are superseded.
