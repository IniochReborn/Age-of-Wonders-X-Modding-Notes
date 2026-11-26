---
name: presence-game-state-re
description: "10/22 static RE for Discord Rich Presence - how an external ReadProcessMemory helper reads in-game / SP-MP / map name / turn / local race from AoWx.exe (AoWEPACK RVAs + offsets); probe script presence_probe.py, live check pending"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T04:00:27.752Z
---

Static RE only, done 10/22. Nothing has been checked against a live game yet: run `patch scripts\presence_probe.py [--watch]`. It may need an elevated prompt, because the game usually runs elevated. It is for [[discord-map-randomizer-bot]] (the same "Age of Wonders X" Discord app).

**⚠ AoWEPACK can be rebased.** An earlier probe saw it loaded at 0x00DF0000. Always take its base from the module list: toolhelp with TH32CS_SNAPMODULE|SNAPMODULE32, or EnumProcessModulesEx with LIST_MODULES_32BIT.

| What | Where | Evidence / confidence |
|---|---|---|
| map | `[AoWEPACK+0x1FA040]` (export AoWE.AoWHSMap) | Nil when no map is loaded: TAoWEngine.CloseHSM 0x557985E0 zeroes it, SetHSMap 0x55798668 sets it, and code everywhere nil-checks it. HIGH |
| in game | map != 0 **and** turn >= 1 | The map may already exist during lobby setup (TSetupControl.SetupMap writes map+0x13A), while the turn is still 0 there. MED, needs a live check |
| turn | int32 `[map+0x174]` | 0 at TAoWHSMap.Create+32E; `inc` in TPlayerControl.NewDay 0x55754DA4; stream tag 0x13. It is used as the turn number in the debug autosave name `DEBUG\<map><turn>_p…asg` (TPlayerControl.NewTurn+21E). HIGH. Whether the UI's first turn shows 1 needs a live check |
| map name | AnsiString `[map+0xE4]` (length at p-4) | Stream tag 0x19, which is the .hsm title (e.g. "After the Fall", no "AoWx - "). The same autosave-name concat proves it is an AnsiString. HIGH. For campaigns it is the scenario's own title |
| connection | byte `[map+0x13A]`, TPlayerConnectionType | RTTI 0x55708D60: 0 pcLocal, 1 pcNetwork, 2 pcEmail. Set by TAoWHSMap.SetupPlayerControl 0x55777F1C (cl) from TSetupSettings+0x3C. HIGH |
| play mode | byte `[map+0x239]`, TPlayMode | 0 none, 1 turn, 2 simultaneous |
| hotseat | byte `[map+0x139]` | TTurnPlayerControl.DefaultStartMap: (conn==2) or (conn==0 and local humans > 1) |
| players | `[map+0x140]` TPlayerList | `[+8]` is a TList of TPlayer (items `[+4]`, count `[+8]`; GetPlayers 0x557544D0). `[+0x1C]` is the int list of local HUMAN indices (count `[+8]`). TPlayerList.Update 0x55754370 also builds +0x10 active, +0x14 local, +0x18 humans |
| local player | int8 `[map+0xA5]` = seated index into the TList | Abstract SetSeatedPlayer 0x55772A78. `[map+0xA4]` = current player. It is briefly set to -1 inside hotseat NewDay |
| race | byte `[player+0xA5]` | TPlayer.SetRace 0x55752CF8. Ids are 0 Humans … 11 Undead |
| other TPlayer fields | `+0xA6` id, `+0xA7` TPlayerType (0 ptHuman), `+0x44` game-over, `+0x45` status | |

**Multiplayer rule:** conn is 1 or 2, or the local-human count is above 1 (hotseat).

Other RTTI enums decoded (scan for kind-3 typeinfo in AoWEPACK): TGameType gtCustom/gtCampaign/gtTutorial (field not located), TGameStatus, TSetupPhase.

**10/22 helper BUILT (not shipped):** `patch scripts\presence\` contains:
- `AoWxPresence\` with Program.cs, Discord.cs (IPC pipe), Memory.cs and GameState.cs, which reads the chains above.
- `build_presence.py --client-id <Discord app id>`, which writes ClientId.cs and client_id.txt (x86 csc build, copied to the game root).
- `aowx_discord_icon_1024.png`, the 32 px exe icon scaled 32x nearest-neighbour. The user uploads it as art asset key "aowx".

Display:
- Details: "Single-Player|Multiplayer - map".
- State: "Turn N - Playing as Race".
- The large and small images are both "aowx"; the start time is the game's process start time.
- When not in a game it shows only the elapsed time.
- Off switch: HKCU\...\Age of Wonders X\Presence `Enabled=0`.

Launch:
- `AoWxUpdater --game-start` calls StartPresence(pid) BEFORE its Mode check. The updater was rebuilt and copied to the game root.
- `patch_exe_presence_launch_v1.py` is APPLIED (`.bak_preslaunch`): the je at 0x63657A becomes NOPs, so AoWx.exe launches --game-start even with Mode=Off.

Tested against a fake Discord pipe: handshake, SET_ACTIVITY, and clear on exit all OK. The game-state reading has not been tested live yet.

**TODO:**
- The user creates the Discord app "Age of Wonders X" (shared with the /map bot) and sends the Application ID. Then build and live-test with Discord open.
- At the next cut, ADD AoWxPresence.exe to the installer staging and to the release zip `--add`.
- 10/22: Discord app "Age of Wonders X" id 1562676560949944400 (client_id.txt). Art keys: large `aowx4` (user-made; was aowx3) (square crop of aowx2, art import exportowx3_square.png) (user logo), small `aowx_icon`. User installed the desktop app: presence WORKS live; text lines not yet confirmed.
- 10/22: Playtest mode: if 2+ AoWx.exe processes are running, details become "Playtesting - map" and state is "Turn N" with no race (user request, for simulated LAN with two instances).
