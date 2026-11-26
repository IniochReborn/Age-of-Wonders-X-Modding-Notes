---
name: ally-enchant-targeting
description: 2026-10-18 combat unit enchantments castable on ALLIED units (same side, other player) — vanilla click handler compared player not side; patch_tc_ally_enchant_v1 (TCPCK 0x41F63B → cave 0x450000)
metadata:
  type: project
---
User: own-side unit enchantments couldn't target allies in combat (red crosshair, click refused). Click handler TCPCK 0x41F5A6–0x41F645 checks target PLAYER: same player + own-side spell → cast; other player → only other-side spells. `patch_tc_ally_enchant_v1.py` (10 B @0x41F63B → 55-B cave **0x450000**, `.bak_allyench`): other player → cast if spell other-side, or own-side spell and target on caster's side. Nothing downstream (path calc, TE, ExecuteCA) checks owner → MP-safe. Hover cursor 0x41F9A8 already compares SIDE, so a red cursor would mean the ally isn't on our side — probe `ally_side_probe.py` (needs ai_state_probe.py) logs players/sides. Caster pays upkeep for lasting enchantments on ally units. APPLIED 10/18, VEH 6, untested. Next free TCPCK cave 0x450040.
