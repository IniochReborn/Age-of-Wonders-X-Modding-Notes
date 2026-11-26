---
name: ilb-icon-generator
description: "patch scripts\\build_ilb_items_x2026.py — procedural 41x42 item-icon painter + full ILB writer; produced Images\\Items\\I_x2026.ilb (72 icons, 6 slots x 12) on 2026-09-11"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21f7e6ff-a6ad-493d-b21b-e5bbe92ddefb
  modified: 2026-09-11T04:29:11.017Z
---

`patch scripts\build_ilb_items_x2026.py` is a from-scratch ILB *generator* (not a byte-append patch): it paints
72 item icons procedurally with PIL at 4x, downsamples (premultiplied Lanczos, alpha cut 110, 1-px 0.42 dark
outline) and writes a complete v4.0 library through `old modding tools\research\ilbcodec.py`. Output
`Images\Items\I_x2026.ilb` (97 KB) — ids 0-71, names `head01..12`, `armor01..12`, `weapon01..12`,
`shield01..12`, `ring01..12`, `use01..12` (.bmp suffix). No item references it yet; it exists for the user's
future custom items, like I_x2025 before it.

**Why:** the user wanted a reserve of new slot graphics without hand-drawing them; the record layout was copied
exactly from I_x2025 (type 17 RLESprite16, info 3, drawMode 256, blend 0, transp 19755, clip_x 0, no palettes,
contiguous pixel data) so the game treats it identically.

**How to apply:** to add/replace icons, add a draw function to the `ICONS` table and re-run with `--force`
(default output is the game folder; `--out`/`--preview` redirect). `verify()` re-reads the file with the reference
codec and decodes every pixel back against the source image, and an opaque pixel that happens to quantise to
0x4D2B gets its low bit flipped so it can never become transparent. Preview contact sheet lands next to the
script as `I_x2026_preview.png`. Weapons are drawn in a local upright frame and rotated (-30..-45 deg, tip
top-left) via `local()`; big axe/scythe heads sit close to the canvas edge, so the build prints a note when a
clip box touches the border. Related: [[ilb-image-format]], [[aowx-project-overview]].


## ⚠ SUPERSEDED 2026-09-21: `patch scriptsuild_ilb_items_x2026_v2.py`
User disliked the 72 procedural icons (never referenced by any item, not in 409). `I_x2026.ilb` now holds **210 icons from the user's art** in `reference files\_2026 new items\` (attack 33, body 33, defense 30, head 25, ring 35, use 54; ids sequential in that order, names attack01.bmp..use54.bmp). Old library kept as `backup\Images\Items\I_x2026.ilb.bak_v1`. Pipeline: flood-fill chroma key on a quarter-scale copy (median border colour, L1 tol 40) + global tight key (30) for ring holes + green-aware edge spill removal (green-dominant pixels within 24 px of the background) + island drop (<3 % of item, translucent smoke/glow) + 1 quarter-px erosion; crop to bbox and fit into per-slot boxes matching vanilla clip sizes (attack 36x38, body 37x39, defense 34x39, head 33x33, ring 22x21, use 34x34), premultiplied Lanczos, alpha cut 50 %, RLE16 key 0x4D2B, v4 41x42 type 17 like I_x2025. Re-run `--apply` after adding PNGs (names `<slot><n>.png`). Do NOT run the old build_ilb_items_x2026.py again (it would overwrite with the procedural set — it refuses without --force).

**ITEMGFX registration (2026-09-21, `patch scripts\patch_itemgfx_x2026.py`, backup `backup\Release\ITEMGFX.PFS.bak_x2026gfx`, APPLIED, game launch OK):** Item GFX ids **426..635** = I_x2026 frames 0..209 (423-425 left blank on purpose; vanilla+x2025 end at 422). Record shape copied from the x2025 editor records: classid 0x20269, tags 1 uid (u32, unique), 2 = 26, 3 = global id (== child id), 6 = Pascal short-string path `ITEMS\I_X2026.ILB`, 7 = frame, 8 = slot byte (0 Head 1 Body 2 Attack 3 Defense 4 Ring 6 Use). Kids table ctrl 0x86 (6 narrow + nd wide (id,off)); offsets are relative to the table end so growing the table moves nothing; records appended, existing 372 byte-identical (order matters to the game/editor). CRC = crc32(bytes after the magic, before the tail) as with the other .pfs. Also ship ITEMGFX.PFS + I_x2026.ilb at the 410 cut.

- 2026-09-21: user rejected the glowing eyes on head11/head15/head19 (Item GFX 532/536/540 = head n → id 521+n); eye sockets painted near-black in the source PNGs (hand ellipses/polygons, Gaussian-feathered), originals kept in `reference files\_2026 new items\_orig_glowing_eyes\`, library rebuilt (same frame order, ITEMGFX untouched).

- 2026-09-22 `patch scripts
estyle_old_itemgfx.py` (backups `backup\Images\Items\I_custom1.ilb.bak_restyle`, `I_Zigad.ilb.bak_restyle`): Item GFX 117 gold plate (I_custom1 #12), 142 trident (I_Zigad #68, key 0xFF), 228 knight helm (#16), 229 monster mask (#18) restyled in place — **REVERTED by the user the same day (result not good enough); script kept for its ILB record-replace helper only.** Filter-only: flat sources stay flat-ish — better fix is swapping the Item GFX record's path/frame to a look-alike from I_x2026 (patch_itemgfx_x2026 record layout). Generic ILB record-replace helper `replace_records()` lives in this script.

- 2026-09-22: all attack sources rotated so the business end points top-left / grip bottom-right (house convention for weapons): 90° CCW for 4,7,11-15,17,19,23-28,30,31; 90° CW for 9,18,20,33; 180° for 8; 45° CCW (bicubic, background fill) for 21,32; 1,2,3,5,6,10,22,29 already correct; 16 is a shield. Originals in `reference files\_2026 new items\_orig_rotated\`; library rebuilt (same frame order).
- 2026-09-22 follow-up: single-edged axes/cleavers must have the EDGE facing down-left (attack2/6 reference); 11, 13, 17, 24, 26 mirrored across the handle diagonal (Image.TRANSPOSE) to flip the edge side; library rebuilt.
