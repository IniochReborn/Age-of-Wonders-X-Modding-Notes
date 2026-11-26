---
name: item-name-cost-limits
description: 2026-10-31 editor item gold cost max 1000→9999 + item name max 20→64 with red chars past 20; patch_devx_item_name_cost_v1 APPLIED untested
metadata:
  node_type: memory
  type: project
  originSessionId: 68556280-d707-4a00-a5ee-7f75589fbb89
  modified: 2026-10-31T05:39:14.649Z
---

**Request 10/31:** item max gold 9999; item name 64 chars, chars past the old limit (20) red like hero names [[sign-text-hero-name-limits]].

Storage was never the cap: TItem cost = dword [item+0x2C] (ReadWrite tag 0x13, dword stream), name AnsiString [item+0x18]. No 1000 cap in game code (AoWEPACK 0x55798536 cmp 0x3E8 is unrelated formatting).

`patch_devx_item_name_cost_v1.py` (.bak_itemnamecost): TITEMEDITFORM DFM in .xdfm — CostEdit (TSpinEdit, form+0x210, CostEditChange 0x413B84) MaxValue int16 @VA 0x4E8528 record; ItemNameEdit (form+0x204) MaxLength int8 @VA 0x4E8340 record. Red overlay = own copy of the hero rl_proc (prop "AoWxRI", LIMIT 20) in .xthm 0x4E4240..0x4E4800 (ends ~0x4E47A2); FormCreate entry @file 0x12489 now → 0x4E44A0, which calls the scroll wrapper 0x4E4040 (→ hpmv → FormCreate).

LIFO: revert this before patch_devx_scroll_spells_v1 (scroll script's zone shrunk to 0x4E4000..0x4E4240; it recognises the INC1 chain and refuses revert while chained). Anything that rebuilds .xdfm wipes the two DFM edits → re-run after it.

**Why:** editor-only limits; in-game UI may clip long names (hence red).
**How to apply:** AoWDevX .xthm is now full; no editor caves left except .xitm raw tail 0x4E5230..0x4E5400.
