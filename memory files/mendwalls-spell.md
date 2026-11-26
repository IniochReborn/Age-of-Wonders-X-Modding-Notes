---
name: mendwalls-spell
description: Earth L1 combat spell 216 Mend Walls (Ooze clone, 19-hex area, repairs/rebuilds city walls + gates) — applied 2026-10-17, untested; user's spec line was truncated
metadata:
  type: project
---
User spec 2026-10-17 (Earth L1): "Mend Walls — Combat spell, infinite range, medium AOE, Research 40, Cost 4" + a truncated tail ("...mountains, and digging/burying tunnels (increased in depths)") — interpreted as wall repair; user told to correct if different. APPLIED 2026-10-17, VEH clean, untested.

- 216 = TOoze clone (pfs_donor 134, sphere 3 Earth, tier 1, mana 4, research 40, pfs key 226), ALIAS 216 → 0x7C (19 strikes, Ooze's 19-hex preview, range 0xFF).
- `patch_tc_mendwalls_v1.py` (TCPCK zone 0x447400–0x447530; prev targets stored at 0x447400): LND 0x40C922 (Ooze landing, in front of the Ooze-extinguish jmp 0x43AC40): per strike hex, find the wall/gate segment and set full HP for its material via the game's own HP setter (restores intact image + re-blocks the hex); destroyed segments rebuilt only if no unit AND no corpse on the hex; clears the city breach flag when all walls > 0 HP; skips Ooze mud/extinguish. TGT 0x40E35D (in front of Oil Spring's target cave 0x43D890): 216 strikes get no target unit. ⚠ Revert Mend Walls before re-running patch_ooze_extinguish_v1 / patch_oilspring_v1.
- Limits: glow plays on all 19 hexes; fast combat does nothing (its wall objects not updated); AI never casts (DMG 0).
- Art: icon glyph_mendwalls (crenellated wall with a breach, blocks flying back; Earth cloud 40); fx DualDF 3954–3989 (mend_stone tumbling block, mend_trail amber grit, mend_impact dust ring + golden glow); sfx DUALER_MENDWALLS (2.4 s) + DUALER_MENDSTONE1/2 (slot-1 sub-list, REQUIRED — hail landings play sound 1).
- **Mend Walls v2 APPLIED (2026-10-17):** per hex: HP 0 → skip (no rebuild), full → skip, else + max/4 + RandInt(max/2+1) (25–75 %, capped) via System.@RandInt (TCPCK thunk 0x401020 = synced combat stream) and the wall HP setter 0x405AE4; desc updated.
