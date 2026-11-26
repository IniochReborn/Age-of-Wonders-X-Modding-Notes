---
name: scenario-hp-topup
description: "Scenario-start HP top-up: map-placed units start at their CURRENT max HP, fixing 'Battering Ram 12/15' drift after the mod raises a unit type's HP. Hook in TAoWHSMap.StartNewMap. Applied 2026-08-10, awaiting test."
metadata: 
  node_type: memory
  type: project
  originSessionId: 68a26f78-5efa-41a9-b957-f58c326322dc
  modified: 2026-08-11T04:23:56.593Z
---

**PROBLEM** (user-reported): maps store each placed unit's CURRENT hp as a byte
`[unit+0x3e]` (TUnit.ReadWrite property 9). When the mod raises a unit type's
max HP (Battering Ram 12→15), units already placed in old maps (e.g. After the
Fall) start the scenario at **12/15** — permanently wounded-looking. Sibling
problem to [[multilevel-ability-heal]] (content saved under old rules).

**⚠ v1 WAS BROKEN — FIXED 8/11.** v1's cave did `push ebx/esi/edi; mov ebx,eax;
CALL body`. But **StartNewMap ends `pop edi; pop esi; pop ebx; ret`** (balancing
its own 3-push prologue) — the inserted call-return-address made those pops
consume the wrong slots and the `ret` jump to the map pointer ⇒ guaranteed
crash *if it ever ran*. It did NOT crash for the user ⇒ **StartNewMap never ran
in that test ⇒ they had LOADED A SAVE, not started the scenario fresh** (saves
correctly go to StartLoadedMap and keep their HP). ★ RULE: never `call` into a
Delphi function body past its prologue — replay the prologue and `jmp`, so the
callee's epilogue returns to the original caller. v2 = pushad/popad sandwich
for the top-up, then displaced prologue + `jmp` to body (111B).
★ Also verified ordering: TAbstractUnit.Activate→TUnitControl.RegisterUnit
(@0x5577FBC7), and Activate calls THSMap.Activate (units register) BEFORE the
StartNewMap/StartLoadedMap branch — so the unit list IS populated at top-up time.
Branch: `[map+0x3c]&2` skips both; else `[map+0x174]==0` → StartNewMap (fresh)
else StartLoadedMap (resumed) — the engine's own fresh-vs-loaded discriminator.
Map files = .hsm/.csm (loaded via THSEngine.LoadHSMfromStream — only 2 callers:
AoWE.TAoWEngine.LoadCampaignMap and AoWx!TSetupEvents.SetupControlLoadMap);
saves = **.asg**. Battering Ram = unit uid 250, base hits 15 (stats[4]).

**FIX APPLIED 8/10** (`build_scenario_hp_topup.py`, backup
AoWEPACK.dll.bak_hptopup): cave @0x55810D80 (130B; **next free AoWEPACK cave
0x55810E80**), hook = 5-byte entry of **TAoWHSMap.StartNewMap @0x55777D68**
→ jmp cave; cave re-does the prologue, `call`s the body at 0x55777D6D, then
iterates `[AoWHSMap 0x558FA040 +0xFC]` (TUnitControl) via GetCount 0x5577E908 /
GetUnit 0x5577E93C and per unit: max = vcall[+0xD0] GetHits, cur =
vcall[+0xE0] GetHitPoints; **if 0 < cur < max → vcall[+0xE4] SetHitPoints(max)**.
cur==0 skipped (dead/uninit); never lowers HP.

**WHY THIS HOOK IS SAFE (the key insight):** StartNewMap runs ONLY when a
scenario/new game begins — it seeds each player's starting gems/mana. Loading
a SAVE goes through the sibling **StartLoadedMap @0x55777F10** instead. So a
wounded unit in a saved game is never touched; only freshly-placed map units
get topped up. Deterministic from map state → LAN-safe.

**⚠ VMT SLOT TRAP:** on TUnit (@0x55710CAC) *and* THero (@0x55711FEC):
**+0xD0 GetHits (max HP), +0xE0 GetHitPoints (current), +0xE4 SetHitPoints**.
+0xCC = GetResistance and +0xD4 = GetMoves — my first guess used those and
would have called the wrong methods. ALWAYS verify a slot by scanning the vtable
for the known method VA rather than assuming adjacency.
HP model: current hp = byte `[unit+0x3e]`, clamped to [0,max] by SetHitPoints
@0x557827C4 (which also calls UpdateDefensiveStrength); max HP = GetHits
@0x55782B68 → **already a mod cave @0x5580BE15** computing from resource bytes
[res+0x2C] (base hits) / [res+0x2F] and unit rank byte [unit+0x3C]/10.

TEST: start (not load) After the Fall / any old scenario with a placed
Battering Ram → should begin 15/15, not 12/15. Loading an existing save must
NOT heal wounded units.
