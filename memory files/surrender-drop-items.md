---
name: surrender-drop-items
description: 2026-11-19 surrendering (in combat or on the world map) drops the leader's/heroes' items on the map instead of destroying them (patch_surrender_drop_items_v1, AoWEPACK cave 0x558BA100) - APPLIED, untested
metadata:
  type: project
---

User 11/19: exploit — players surrender before dying so the opponent gets no items. Clarified by the user: combat
surrender removes ALL of that player's units/heroes/leader in the battle with their items; world-map (empire) surrender
removes only the LEADER with its items. Wanted: items drop as on death in both cases.

RE:
- Combat: TCPCK TAoWCombatMap.Surrender 0x41CC84 → CombatTE.TCEndCombatTE.Execute 0x407D10 → every combat unit of the
  side: VMT+0x11C = TCombatUnit.Surrender 0x557257B8 (≈ DestroyObject 0x557256F0 without the ability death handlers):
  flag, ResetTargets, combat VMT+0x50 (TCombat.ObjectDestroyed), VMT+0x138 KillUnit 0x557256E4 → unit VMT+0x1AC Killed.
  THero.Killed 0x55787164 → ExecutePlaceItem(item, slot 0xE) → map VMT+0x108 DropHeroItem: tactical version TCPCK
  0x41C9DC looks the hero up in the combat data and needs its HS position; not found → nothing (items die with the
  hero). World version 0x55773770 = TItem.PlaceOnMap at the unit location. Auto-combat: TFastCombatUnit.KillUnit
  0x55743A78 calls THero.DropItemsOnMap 0x557870D4 (eax=hero, edx=map, cl=x, push y, push level) at the battle
  location [[cu+8]+0xC]+8/+0xC/+0x10 when [combat+8]&1.
- World map: TPlayer.Surrender 0x55751B38 → TGameOverTE (status 2) → TPlayer.SetGameOverStatus 0x55751848: structures
  VMT+0x1F0(0), every army TArmy.SetPlayer(0) → units VMT+0x16C. TLeader.SetPlayer 0x5578B4F0: leader of a real
  player → VMT+8(nil) = removed (items untouched); heroes go through THero.SetPlayer and become independent.
- THero class ref cell 0x55711FAC; TAbstractUnit.GetLocation 0x5577ED94 (edx=&x, ecx=&y, push &level; 0xFF = no army).

Build: `patch scripts\patch_surrender_drop_items_v1.py` (`.bak_surrenderdrop`, in-place): TCombatUnit.Surrender entry →
cave **0x558BA100** h1 (hero → DropItemsOnMap at the battle location); TLeader.SetPlayer 0x5578B4FE → h2 (leader
location → DropItemsOnMap). 174 B, PIC.

**Status:** APPLIED 11/19, USER-CONFIRMED 11/19 ("it works"). Notes: world-map drop executed while the tactical map is active (fast combat does
it with the world map active); winner must pick the bag up from the battle hex. MP: all players need it.
Next free AoWEPACK cave after this: 0x558BA200.
