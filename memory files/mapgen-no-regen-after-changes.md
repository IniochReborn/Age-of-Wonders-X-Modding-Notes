---
name: mapgen-no-regen-after-changes
description: "After generator code changes, never regenerate existing seed-named maps — generate NEW seeds"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f423df81-3d59-4dc5-a0d6-8f324fbcca5e
  modified: 2026-08-03T02:37:15.816Z
---

When the map generator (or any of its data/kit files) changes, do NOT regenerate previously delivered seed-named maps in place (`py generate_map_v4.py <old-seed> ...` → same filename). Generate a fresh batch with NEW random seeds instead.

**Why:** The user tracks maps by seed name; a file that silently changes contents under the same seed name is confusing (an "already tested" map is no longer what was tested), and old seeds reproduce nothing anyway once the RNG stream shifts.

**How to apply:** After any change to files under `patch scripts\mapgen\`, produce new maps via `gen_batch.py` (random seeds) and retire/delete the stale batch. Exception: the permanent image maps (`xImg5 Kanto (seed 151)`, `Zelda ALttP (1986)`, `San Andreas (1992)`) keep their user-chosen seeds — those seeds are content identifiers, and the picture drives the layout. See [[project-state-2026-07]].
