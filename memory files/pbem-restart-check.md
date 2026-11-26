---
name: pbem-restart-check
description: 2026-11-19 RE (read-only) of the play-by-email anti-cheat - egames.pfs ledger + per-turn security ID stored in the save; how a replayed turn is detected
metadata:
  type: reference
---

User 11/19 asked how the PBEM anti-cheat works (explain only, nothing patched). Static RE, AoWEPACK:

- Ledger: `<game>\EmailIn\egames.pfs` = TEmailGameList of TEmailGame records {+8 string (tag 0x14), +0xC local unique
  id (0x15), +0x10 game id (0x16, random at creation), +0x18 string (0x17), +0x14 **security id** (0x18), +0x1C turn
  marker}. TEmailGameControl.Save 0x55732A80 writes it and stores its CRC32 in the registry
  (TAoWRegistry.SetEmailGamesCRC); Load 0x557329BC reads the file ONLY if its CRC matches the registry value
  (mismatch / missing = empty ledger).
- Each human PBEM player in the save carries TPBEMPlayerSettings ([player+0xA0]) → a copy of that player's TEmailGame
  (local id, game id, security id).
- End of turn: TEmailGameControl.UpdateGame 0x55732BF8 → GenerateSecurityID 0x55732BE4 (random from the millisecond
  clock) written to BOTH the ledger record and the save, ledger saved.
- Loading a PBEM save: TPBEMPlayerControl.ValidateLoadedMap 0x55758750 → FindEmailGame 0x55732B78 (local id + game id
  must match) and EmailGameRestarted 0x55732BBC (save's security id != ledger's). Restarted → TriggerGameRestartedEvents
  0x55757FE8 distributes a message event to the players ("Game is restarted for unknown reason, contact %s for more
  information"; resource PBEMRestartCheatRStr) and the game continues. No ledger record → a new one is created.
- ValidateIncommingGame 0x55732CF0 (incoming mail in EmailIn): PBEM save ([map+0x13A]==2), current player's e-mail ==
  local address, compares against the ledger / an existing copy before accepting the file.
Not traced: exact field meanings of +8/+0x18 (file / address strings), the full ValidateIncommingGame tail.
