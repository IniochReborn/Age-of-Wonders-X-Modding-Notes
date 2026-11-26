---
name: dispel-nodes-altars
description: 2026-10-19 own unit with Dispel Magic (0x3C, multilevel) on a node adds 2×level POWER (split by the mana/research slider); on an altar cuts recharge 10 → 10−level (min 1); highest level only; patch_dispel_nodes_altars_v1
metadata:
  type: project
---
Node power = structure VMT+0x1F8 GetPower (elemental + TRandomNode 0x557BE468: 10+5×picks; Power Node 0x557D03C8: 10); per-turn credit + magic window read it. Altars (base + Fire/Ice/Lightning/Life/Death/Pestilence): recharge 10 days, counter +1/day, early fire costs (10−counter)×50 mana. Patch repoints 15 VMT slots → cave 0x5581F310 (zone 0x5581F300–0x5581F800 'DMN1', `.bak_dispelnodes`): army on the structure's own hex, owned by the structure owner, highest unit VMT+0x144 level of 0x3C (cap 10); node power + 2×lvl only if power > 0; altar requirement max(1, 10−lvl), counter past it counts as charged. Next free AoWEPACK cave 0x5581F470. Unchecked: exe node/altar panel text. APPLIED 10/19, VEH 6 (user confirmed power, not mana, is intended).

**v2 10/19 (user: immediate):** power is NOT cached (TPlayerMagicControl.GetPower 0x5577CA00 calls node GetPower live) — only the UI refresh was missing: TPlayerMagicControl.Update 0x5577D248 ([player+0x54]) fired only on capture (0x557BEF08). `patch_dispel_nodes_altars_v2.py` (DMN2, code 0x5581F470–0x5581F52D, `.bak_dispelnodes2`): 8 node VMTs +0x180/+0x184 (army placed/removed via msgs 0x1102/0x1103, TArmyHS.PlaceOnMap 0x557909F4 / remove 0x55790A5C) → stubs calling the previous target (elemental bless caves 0x55814300.. or vanilla 0x55760F24/0x5575F364) then owner magic control Update. Not covered: ability gained while standing still. Revert before build_elemental_nodes. Next free AoWEPACK cave 0x5581F530. APPLIED.
