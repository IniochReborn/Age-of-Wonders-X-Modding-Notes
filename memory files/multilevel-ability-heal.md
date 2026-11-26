---
name: multilevel-ability-heal
description: "Engine-wide lazy heal for old maps/saves whose units own multilevel-converted abilities (e.g. Lifestealing) without the level data node — fixes TurnEventTE freeze (keeper2.csm). Hook in TAbilityOwner.GetAbilityData. Applied 2026-08-10, awaiting test."
metadata: 
  node_type: memory
  type: project
  originSessionId: 68a26f78-5efa-41a9-b957-f58c326322dc
  modified: 2026-08-12T21:49:41.307Z
---

## 🛑 DISABLED 2026-08-12 — THIS PATCH ADDS CRASH SURFACE AND CAN CORRUPT MEMORY
Use `patch scripts/build_multilevel_heal_disable.py` (restores the 7 stock bytes
at 0x5574F1C4; backup `AoWEPACK.dll.bak_mlhealoff`).
⚠ **NEVER use this file's own `--revert`** — `AoWEPACK.dll.bak_mlheal` predates
the HP top-up, Summon Silver Dragon, Void Step and the 2026-08-12 wall fixes and
would wipe them all. Always disable surgically.
**Why:** vanilla `GetAbilityData` only reads `[owner+0x10]` and walks the node
chain — it **never dereferences the owner's VMT** and just returns nil on a miss.
The cave adds (a) `mov ecx,[eax]; call [ecx+0x4c]` = a **virtual call on the
owner**, so an owner vanilla tolerated now AVs (observed @0x55810CB6, bogus VMT
0x0C0A0000); and (b) on the heal branch it **writes**
`mov ecx,[edi+0x10] / mov [eax+8],ecx / mov [edi+0x10],eax` — storing a node into
`[owner+0x10]` and adopting whatever junk was there as `next`. Given a
wrong-class "owner" that **corrupts the object and builds a garbage chain**,
which then AVs on a later walk (observed @0x55810C9B reading 0xFFFFFFFF, and
@0x55810C93 reading 0x9EED7398).
**It also never fixed the bug it was written for:** it shipped only in 1.37.402
(the 401→402 diff lists GetAbilityData as a change) yet the crash predates 401.
The original Keeper2 "TurnEventTE" freeze is far better explained by the
wall/GetRank bug — see [[keeper2-armycombatmovete-crash]]. If a genuine bit-only
multilevel-ability failure ever reappears, rebuild it **guarded**: prove the
owner is a real TAbilityOwner before the virtual call or any write.

**PROBLEM** (player-reported, user-reproduced on campaign keeper2.csm): game
froze immediately ("TurnEventTE" error) because a map-stored LEADER owned
**Lifestealing (0x76)**, which the mod later converted to a MULTILEVEL ability
(via the generic 3-level builder cave @0x5580E202 — creates TMultiLevelAbility,
max level [ab+0x28]=3, costs 10/10/10; same helper family as Hero Slaying
@0x5580E31E). Old maps/saves store abilities only as a BIT in the owner's
ability set (TCustomAbilityList bitset, vcall [owner+0x4C]=GetAbSet
@0x5574E0E0 bt-test) — **no TMultiLevelAbilityData node**. Engine invariant:
owned multilevel ability ⇒ data node in the [owner+0x10] singly-linked chain
(node: [+8]=next, [+0xC]=level byte, [+0xE]=ability id word, vcall+0x4C=
GetAbilityID; ClassID 0x22001). GetLevel @0x557651D8 = GetAbilityData →
byte[data+0xC], null→0 — level-0 state wedges turn processing. Removing the
ability in the editor per-map fixes one map; user wanted a global fix.

**FIX APPLIED 8/10** (`build_multilevel_ability_heal.py`, backup
AoWEPACK.dll.bak_mlheal): **lazy self-heal in TAbilityOwner.GetAbilityData
@0x5574F1C4** — function re-implemented in cave @0x55810C80 (143B; **next free
AoWEPACK cave 0x55810D80**), entry 7 bytes → jmp cave. On miss: if
GetAbSet(owner,id) AND GetAbility([AoWHSSet 0x558FA044 +0x80], id) is
IsClass(TMultiLevelAbility classref [0x5571DF90]) → replicate
TMultiLevelAbility.Expand's create branch @0x55765392: cls=vcall[ab+0x108]
(AbilityDataClass), data=ctor vcall[cls+0x20](dl=1), [data+0xE]=id,
[data+0xC]=1, link head of [owner+0x10]. Healed nodes SAVE back → content
self-repairs. Deterministic → MP-safe. Non-owners/non-multilevel unchanged.
⚠ Do NOT use TAbilityOwner.GetAbLevel @0x5574FD44 for ownership tests in this
context — it vcalls [ability+0x70] which for multilevel = GetLevel →
GetAbilityData → would recurse into the heal.

KEY RE: TAbility.SetAb @0x5574E718 = owner vcall+0x50 SetAbSet; ability id @
[ability+0xC]; ability control = [AoWHSSet+0x80], spell control +0x84.
TEST: any OLD campaign/scenario map with a pre-conversion Lifestealing (etc.)
leader should now load and run turn 1 without the freeze, no editor edits.
