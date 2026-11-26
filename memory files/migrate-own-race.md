---
name: migrate-own-race
description: "2026-11-19 city migration to the player's OWN race allowed when any unrazed city of that race exists on the map (patch_migrate_own_race_v1, AoWEPACK cave 0x558BA000) - APPLIED, untested"
metadata:
  node_type: memory
  type: project
  originSessionId: 16e553f8-9d4e-4881-9bc5-93ea46d82e29
  modified: 2026-11-20T00:37:34.867Z
---

User 11/19: a player can only migrate a city to a race they (or an ally) already own a city of; wanted: migrating to
the player's OWN race is always allowed as long as at least one unrazed city of that race exists on the map (any owner,
independents included).

RE: `TCity.CanMigrate` 0x557AB1D0 (eax=city, dl=race): false if [city+0x45]==race; else City.RaceInCity 0x557AE0B8
(al=race, dl=player; walks [player+0x1C] structures, TCity class ref 0x557A73B0, finished = [st+0x24]==0xFF, race
[st+0x45]; does NOT test razed) for the owner [city+0x30] and for allied players (GetDiplomaticRelation == 2), players
count..1. Razed flag = [city+0x44] & 2. Player race = [player+0xA5]. Callers: CreateMigrationItem 0x557AB2F4 →
CreateMigrationSelection 0x557AB388 (UI list + UpdateAIMigration 0x557A9EA4, so the AI gets the rule too).

Build: `patch scripts\patch_migrate_own_race_v1.py` (`.bak_migrateown`, in-place apply/revert): exit 0x557AB245 → cave
**0x558BA000** (201 B, PIC): result false + race == owner's race → scan every player's structure list (index 0 =
independents included) for a finished, unrazed TCity of that race.

**Status:** APPLIED 11/19, USER-CONFIRMED 11/19 ("good it works"). MP: every player needs it (sync). Ship AoWEPACK.dll.
Not verified: whether razed cities / independent cities really sit in a player's structure list (assumed player 0 for
independents).
