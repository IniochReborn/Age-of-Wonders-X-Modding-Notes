---
name: sky-below-levels
description: "2026-11-13 Sky/Clear Sky shows the level below on EVERY level, nested (Firmament→Surface→Caverns); patch_sky_below_v1.py layered on the water overlay build; APPLIED untested"
metadata:
  node_type: memory
  type: project
  originSessionId: 2c63b60f-49b3-44ba-9088-66d07407269f
  modified: 2026-11-14T01:21:07.408Z
---

**APPLIED 11/13, untested in game** — `patch scripts/patch_sky_below_v1.py` (.bak_skybelow AoWEPACK; `--test` = unicorn test of the setup/chain logic, 15 cases). Layered byte patch over the installed water overlay build ([[sky-chasm-transitions]], [[map-levels-29-plan]]) → **revert it before re-running patch_sky_overlay_water_v1 / sky polish** (they would see OTHER).

- ⭐ Ziggurat cache builder RE (our relocated copy 0x558C0900, eax=map, edx=DC, ebp=delta): hard-coded level 0 at 0x558C093E (`mov edx,0` → GetLevel) and 0x558C0B06 (`mov [map+0x88],0`); renders the whole level in 608x608 chunks (15-hex steps, view fields map+0x80/84/88/94..A0 temporarily rewritten, objects' Show vmt+0xA8 for lists map+0x1C / +0x20, skips TArmyHS 0x557133A0 + TAoWBorderHexagon 0x5579A458), scales each chunk x0.6 (2x2 average, weight table 0x558C9870) into a temp buffer, crops to content, tiles it into BSS_BUF (W multiple of 192, H of 96; cap dword 0x558FAF18). Chunk DC copy = builder frame [esp+0x50]. No fog/explore handling (same as before: lower level terrain shows faintly even if unexplored).
- Patch: sites A/B → stubs read BLVL; site C 0x558C0CC6 (after a chunk is drawn, before scaling) → stub calls overlay core(map, chunk DC, mode 0) while COMPOSE=1 → the level's own Sky pixels get the INNER (next lower) cache blended (clouds frozen into the cache). Overlay `fmtok..timing` block replaced by `call setup` (cave 0x558E1900..0x558E1D00 'SKB1'): B = engine NeighbourLevel thunk 0x55851210 (dl=1, hidden mask aware); builds only when a Sky hex is in view; chain B, below(B).. while the level has any Sky hex (max 4), deepest first. Cache invalidated on viewed-level change or when the overlay was not called for 2 s (load / combat / full-screen window).
- State = AoWEPACK **DATA slack 0x558E9AA0..0x558E9ABC** (BSS page slack is a minefield of overlapping claims; DATA slack 0x558E9A88..0x558E9B00 was free). Next free AoWEPACK cave 0x558E1D00.
- Chasm does not show the level below (not asked).
- BSS-slack overlap seen in patch_retaliation_giveup_v1 vs Wall of Flames (0x558FAB00..) is STALE: v1 is superseded by live v3 (data at 0x558FAAE0, fixed 10/23, see [[oos-423-bss-slack-collisions]]); checked 11/13, no AoWEPACK code refs into 0x558FAB00..AC50.

**v2 11/13 APPLIED (replaces v1 in place; user confirmed v1 'sky thing worked')** — `patch_sky_below_v2.py`: cave 0x558E1900..0x558E1E00 'SKB2', entry table +0x10/+0x15/+0x1A for the screenshot DLL ([[devx-screenshot]]); state +SHOT 0x558E9ABC / SHOT_T 0x558E9AC0: while SHOT the overlay time is frozen (timing call in core -> gettime2), level-below image anchored at world 0, whole-level sky scan, idle rule off. Next free AoWEPACK cave 0x558E2000 (0x558E1E00..0x558E2000 = [[water-twin-fade]]).
