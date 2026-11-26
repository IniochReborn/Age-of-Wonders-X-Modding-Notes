---
name: shockwave-push
description: 2026-10-18 vanilla Shockwave (0x7F) pushes hit units 1 hex outward using Gust v8 push + hop; patch_tc_shockwave_push_v1 (TCPCK hook 0x40BE50, zone 0x450400–0x450C00)
metadata:
  type: project
---
Shockwave TE: ticks 175/200/225 send map msg 0x3100D to rings 1/2/3 round te+0x20/+0x22 (branch 0x40BCD1); unit handler 0x42144E resolves damage immediately; ring-3 loop exits `0x40BE50 jmp 0x40CAF2`. `patch_tc_shockwave_push_v1.py` hooks there (cave 0x450400, 1452 B, `.bak_swpush`): survivors on the 36 ring hexes (not the caster) pushed farthest-first to the neighbour farthest from centre if on-map, empty, no intact wall, movement-valid (Void Step 1-step warp); hop fx kind 0x2F tagged spell 212 (Gust hooks handle it). Requires Gust hop hooks; revert BEFORE patch_tc_gust_v1. No push in auto-combat. APPLIED 10/18, VEH 6, untested. Next free TCPCK ~0x450C00.
**v2 10/18 (user: hop puff too much):** patch_tc_shockwave_push_v2 marks Shockwave hops [fx+0x28]=-6 and thins Gust swirl orbs to 1 in 4 (hook 0x42BFD4 → cave 0x450C00–0x450C26, MASK=3); revert with v2 only. APPLIED.
