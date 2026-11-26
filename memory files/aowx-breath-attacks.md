---
name: aowx-breath-attacks
description: Tactical breath attack RE (AoWTCPCK NextStrike category-5 case): 12 strikes, fan-angle obstruction lines not aimed at the damage hex, full-depth lines — why corridors/side walls block breaths. RE'd 2026-09-21, no patch yet.
metadata:
  type: reference
---

**Executor: CombatTE.TCAbRangedTE.NextStrike 0x40D290 (AoWTCPCK).** Jump table @0x40D2D3 on `[te+0x24]` = ability CATEGORY
(VMT+0x84; 5 = breath → case 0x40D345; default 0x40ED2D = MakeAbilPath 0x4271EC). CA object = [ebp-0x10]; [te+0x34] = strike
index; [te+0x20/0x22] = target hex; [te+0x10] shooter HS ([+0x60] combat unit, VMT+0x74/0x78 = x/y).
- Breath cone = `BreathHN` 0x467498 (12 entries per direction, indexed `BreathDir[dir-1]*12 + entry − 12`; BreathDir 0x4673A8,
  BreathHit 0x467378 = strike→entry order 0,1,4,7,8,2,5,9,10,3,6,11; runtime pointers 0x469404/0x46940C/0x469414). HN spiral:
  ring1 1..6, ring2 7..18, ring3 19..36, ring4 37..60, numbering starts straight ahead and goes clockwise. For dir "up":
  entries = 1 | 18,7,8 | 36,19,20 | 59,60,37,38,39 → cone depth 4 (1,3,3,5 hexes). Aim hex = entry 9 (ring-4 centre).
- Per strike s: f = s (s>9 → 19−s); angle = atan2(shooter→aim) + (f·6 − 30)° (consts @0x40F45C.. 9.0/19.0/6.0/30.0/π/180);
  endpoint = shooter + |aim−shooter|·(cos,sin) (pixels); `MakeRangedPath(side, dx=0x32, cx=0x14 arc, &blocks, &points,
  unitsBlock=0, …, endpoint, shooter)` @0x40D65F → then damage hex := BreathHN[BreathHit[s]] → [ca+0x24/0x28].
- Common tail 0x40EDA0: [ca+0x2C] = unit on damage hex; block loop 0x40EE41: `Random(100) < rec+8` → hex of the point: units
  skipped for breath, else obstacle 0x220166 / wall 0x220504 / gate 0x220506 / terrain 0xF,7 / overlay 8 → points truncated
  @0x40EFF0, and (not a unit) → [ca+0x2C]=0 and for breath **[ca+0x24]=0 → strike hits nothing** (0x40F06F).
**Flaws:** (1) the obstruction line angle is the animation frame (spray sweep), NOT a line to the damage hex — the adjacent
straight-ahead hex is tested with the −30° line, the far-centre hex with +12° → in a 1-hex corridor most strikes hit side
walls; (2) lines always run the full 4-hex depth → obstacles BEYOND the damage hex cancel it. AI EvalBreath 0x415138 =
EvalPath(units 0) on the centre line + 12 hexes (ignores the fan). UI CalculateRangedPath 0x41DC58 / TRangedPathHS.Show
0x427EE4 draw the cone (category 5 branch, tables 0x467248/0x4672F4 = ability→category) without block numbers.
**Proposed fix (user-approved exploration only, 2026-09-21):** per strike, build the block line from the shooter to the strike's
own damage hex and stop there; keep the fan for animation.

**patch_breath_line_v1.py APPLIED 2026-09-21 (awaiting test; backup `backup\AoWTCPCK.dll.bak_breathline`):** hook 0x40D5F1
(5 B, start of the MakeRangedPath pushes) → cave 0x43AB40 (218 B, PIC): for s < 12 recompute the strike's damage hex into
[ebp-0x48]/[ebp-0x4C] (the pushed "target hex") and zero the fan offsets [ebp-0x3C]/[ebp-0x40] → block line = shooter →
damage hex, ending there. Next free TCPCK cave **0x43AC20**.
