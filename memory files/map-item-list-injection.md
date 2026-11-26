---
name: map-item-list-injection
description: How .hsm maps store their item list (root tag 0x1E, key 9 = last item id, editor library-import rules) and the tool add_library_items_to_maps.py that appended the x2026 library to 50 "AoWx - " maps on 2026-09-23 (awaiting in-editor/in-game check).
metadata:
  type: project
---

**Done 2026-09-23:** `patch scripts\add_library_items_to_maps.py --apply` appended all 164 items of `User\x2026.ail` to the 50 `Scenario\Custom\AoWx - *.hsm` maps that contain "Aegis of the Dawn" (= carry the xNew set; the 22 maps with their own unique item sets were skipped by that rule). Nothing removed; "Sun Ring" skipped in Frozen Waters of Seshedut (name already there). Backups `backup\Scenario\Custom\<map>.hsm.bak_x2026items`. Idempotent (re-run = "none"). ⚠ Not yet verified in the editor/game — open one map's Items list (should show 493 for the 329-item maps). ⚠ 410 release zip must ship these 50 maps.

**Map item list format (THSMap root node = inner[0x10:], 3-byte magic `01 00 00`):**
- Root tag **0x1E** = item list: 0-magic list node; entry **key 9 = int32 "last assigned item id"** (== max tag-0x11 over the records; the editor bumps it), keys 10.. = TItem records (magic `68 02 02 00`, TItem.ReadWrite tags as in [[aowx-item-hpmv]]). Keys are sequential; ≥0x80 or offset ≥0x100 → long-form table entries. Records: tag 2 uid (copied verbatim from the .ail, NOT unique per map), tag 3 bitset, **tag 0x11 = per-map item id** (unique; vanilla-era first record may lack it), 0x15 lib id / 0x16 lib name (`xNew`, `xZig`, `x2026`, `Ziggurat`, `Khazlkound Item Set`…), 0x17/0x18 HP/MV.
- **Editor "import from library" = copy the .ail record verbatim + set tag 0x0A to 0 + insert tag 0x11 = last id+1 before 0x15.** Tag 0x0A → TItem+0x45, read only by TCity.Loot (0x557AB09A); ITEMS.PFS items keep 1/2/3 there.
- Item uids/ids are NOT referenced from other root fields as raw u32 (hero inventories etc. hold their own copies), so appending is safe.
- Other root tags seen: 0x02 `RELEASE\Release.hss`, 0x0B description, 0x15/0x16/0x18/0x2C player & unit blobs, 0x19 map name, 0x1D/0x3C song, 0x01 map container (the big one, last).
- ⚠ `set_item_hpmv.parse_node` mis-sizes two entries that share one offset (a zero-length field followed by a real one: root tags 0x30/0x32) → whole-root rebuild loses 4 bytes on most maps. The tool therefore SPLICES: rebuilds only the 0x1E payload (list-level round-trip verified on all maps) and adds the size delta to every root-table offset above it (all long-form). Recompress = `b'CFS\x00\x02' + zlib.compress(inner, 9)`.

**How to reuse:** `--lib`, `--marker`, `--glob`, `--suffix` args; skip-by-name means running twice or with a newer library only adds new names. To add a library to maps WITHOUT the marker use `--marker` with an item every target map has.
