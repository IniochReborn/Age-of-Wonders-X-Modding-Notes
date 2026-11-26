---
name: mp-reload-remember-races
description: "10/22 READ-ONLY RE + design (not built) for MP save re-host auto-reassigning each human's saved race by matching lobby player name to the saved leader name; host-only, via vanilla preferred-race claim"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T07:18:59.205Z
---

**Request (user, 10/22, for 422):** when a saved MP game is re-hosted, the lobby should "remember" each human's race so nobody has to re-assign. Status: static RE + design only, nothing applied.

## Why vanilla forgets
`hPickMap` 0x557E20C8 (host only, map header object = [ebp-0xC], freed at 0x557E23F4):
- **Resets every remote player's preferred race** to 0xFF (0x557E228A) and the host's local record (0x557E225F).
- Builds one TPlayerSetupSettings per TPlayer (index 1..n-1, **skips status [p+0x45]==2**). The fields:
  - rec+0x20 = player index (the **"race" key**: IndexOfRace 0x557DF668 matches this, and the preferred race is a player INDEX, not a race id)
  - rec+0x18 = race byte [p+0xA5]
  - rec+0x1C = TLeader assigned from [p+0x58]
  - rec+0x21 = [p+0xA8]
  - [p+0xA9] = map-assigned → flags |= Forced
- Remote branch @0x557E2389: when not map-assigned, rec+8 and rec+0x10 are set to 7 (Emperor; our mprace patch) **regardless of saved [p+0xA7]** (0 = human). So every saved human, and every saved AI level, comes back as CPU Emperor.
- The save does NOT store the lobby player name separately. But `SetupMap` 0x557E0B64 (0x557E0CE7..0x557E0D52), for a networked game, writes the claiming TRemotePlayer's name (rp+8) into the leader hero's name **[[p+0xD4]+0x60]** for every Human slot when the game is loaded ([settings+0x20]!=0) OR CustomizeLeaders is off. With customize on in a new game, the leader name = the customized name, which [[customize-name-registry]] also saves as the player's lobby name. ⇒ **leader name == lobby name** in practice.
  - Use the raw [hero+0x60], NOT TPlayer.GetName 0x55752104: GetName appends a separator plus hero vcall +0x1B8 text.
  - Fallback when [p+0xD4]==0 (no leader): AnsiString [p+0x4C] (map player name; SetName 0x557522DC writes it).

## Lobby structures (verified)
- TSetupControl: [+0x28] TSetupSettings, [+0x34] own local TRemotePlayer, [+0x25] phase (1 = setup players), [+0x30] UpdateSettings nesting.
- TSetupSettings: [+0x8] TList of records, [+0x20] game-in-progress (save) marker, [+0x38] TRemotePlayerList (TList: GetPlayers 0x557DF3C8, IndexOfRemoteID 0x557DF3D4).
- TRemotePlayer (ReadWrite 0x557DF364): +8 name AnsiString, +0xC remote id, **+0x10 preferred race (player index, 0xFF = none)**, +0x11 status (3 = host), +0x14 version.
- Record: +8 owner type byte / +0xC owner id (0 = unclaimed), +0x10/+0x14 fallback pid, +0x18 race, +0x19 flags (bit 2 = Forced), +0x1C TLeader, +0x20 index, +0x21.
- Claim path: `UpdatePreferredRaces` 0x557E1484 (host). For each rp with pref != 0xFF:
  - rec = IndexOfRace(pref); claim iff rec+0xC == 0 and the flag gate passes and the player's current rec is not Forced.
  - Claim = release the old one (ResetPlayerSettings 0x557E1378) and set rec+8 = 0, rec+0xC = rp id.
  - **pref == 0xFF releases** the player's current non-forced race.
- Callers:
  - hUpdatePlayer 0x557DFE2C (client msg: Assign the whole rp incl. pref → UpdatePreferredRaces → UpdateSettings)
  - hSetPlayerID 0x557E1EB4 (host dropdown; Forced flag when [ebp+8])
- hConnectPlayer 0x557DFCD0 adds the rp with the client's own pref and calls UpdateSettings, but NOT UpdatePreferredRaces.
- Client side: SetPreferredRace 0x557E135C changes local [ctrl+0x34]+0x10 and sends it to the host only on change. The client never reads the host's value back into its local record.

## Proposed design (host-authoritative, reuses the vanilla claim)
State: a small writable table, about 13 × {AnsiString name, byte index}, about 80 B. Requirements:
- Address it PIC (call/pop delta).
- It must NOT be inside the 421 MPH1 reset ranges: hPickMap's map load may run TAoWHSMap.Create, which zeroes those.
- AnsiStrings are refcounted: LStrAsg 0x55701150 (eax=&dst, edx=src), LStrClr 0x55701140.

Hooks, each a 7-byte `mov eax,ebx; call` → jmp cave:
1. **hPickMap @0x557E23EA** (`8bc3 e80beeffff` = UpdateSettings), PickCave about 130 B:
   - LStrClr the whole table.
   - If GetRemote and [settings+0x20]!=0: for each TPlayer index 1..n-1 of [[ebp-0xC]+0x140] with status != 2 and [p+0xA7]==0, store name and index.
   - Then AutoClaim + UpdatePreferredRaces + UpdateSettings, and jmp 0x557E23F1.
   - [ebp-0xC] is still alive here.
   - A virgin map clears the table, so no stale claims.
2. **hConnectPlayer @0x557DFD57** (`8bc3 e89e140000`): AutoClaim + UpdatePreferredRaces + UpdateSettings, then jmp 0x557DFD5E. Covers players who join after the pick.
3. **hUpdatePlayer @0x557DFEC1** (`8bc3 e8bc150000`): AutoClaim, then the vanilla UpdatePreferredRaces, then jmp 0x557DFEC8. Re-applies when a client's update carries pref 0xFF, which would otherwise release the race.

**AutoClaim**, about 110 B: for each rp with pref == 0xFF, find a table entry with a case-insensitive ASCII-equal name (own loop, no import needed). If that index's record is unclaimed (rec+0xC==0) and not Forced, set rp+0x10 = index. An explicit client pref (≠0xFF) always wins.
- Hotseat (GetRemote false) and PBEM (hPickMap already bails on [map+0x13A]==2) are untouched.
- No change to the hValidateSetupMap / customize fix ([[mp-reload-customize-hang]]): claims use the same path as a manual preferred-race pick.
- **Optional extra:** remember AI levels. In the remote branch @0x557E2395, if [settings+0x20]!=0 and [p+0xA7]!=0, use [p+0xA7] (same type enum) instead of 7.

## Risks
- A name changed between sessions, or a dead/absent leader with a map-default [p+0x4C]: no match, falls back to manual (vanilla).
- A player who deliberately sets "no preference" gets re-claimed by hook 3. They can pick another race, or the host can Force.
- Saves with LeadersOnMap off: the leader name may not equal the lobby name, so no match.
- Lobby only, host-only computation broadcast by UpdateSettings, so no in-game desync risk.

## Live test (LAN, 2+ machines)
1. Start an MP game with fixed seats, save after 1-2 turns, quit to menu.
2. Re-host the save: everyone already in the lobby is assigned their old race; late joiners are assigned on join.
3. A client explicitly picks a different race: it sticks.
4. Rename a client: no auto-claim, manual still works.
5. Start → passes "Waiting for other players" (customize fix intact); the game continues with the correct seats.
6. New (virgin) map after a save pick: nobody is auto-claimed.
7. Hotseat reload unchanged.
- 10/22 user: do not restore AI difficulty levels (always Emperor), names → races only.

## 10/22 BUILT, NOT APPLIED (the coordinator applies sequentially)
Script: `patch scripts\patch_mp_reload_autoclaim_v1.py` (dry-run / --apply / --revert / --dis; backup `.bak_mpautoclaim`). The user approved it WITHOUT the AI-level restore, so AI slots stay Emperor.

Code zone: 0x55836400..0x55836800 ('MRA1', 595 B used). Entries:
- pick 0x55836410
- conn 0x55836501
- upd 0x5583651D

Each site is a 7-byte `jmp cave; nop; nop`:
- 0x557E23EA → resumes at 0x557E23F1
- 0x557DFD57 → resumes at 0x557DFD5E
- 0x557DFEC1 → resumes at 0x557DFEC8

**Name table: DATA zero-fill slack 0x558E9F10..0x558E9F78** (13 × 8 B: AnsiString name, slot index byte). The CODE section is not writable (0x60000020).
- Claimed neighbours: steadfast idx dword 0x558E9F00 and Second Wind FM_TAB 0x558E9F80.
- It is not in the MPH1 .idata ranges.

AutoClaim additionally requires [settings+0x20]!=0 (the current pick is a save), so a stale table can never seat anyone on a virgin map. It also skips players who already hold a seat (IndexOfRemoteID != -1).

Checks so far: relocs clean; dry-run OK; apply → revert round-trip on a DLL copy is byte-identical. Not yet tested live.

## 10/22 v1 live test FAILED → v2 built (not applied)
**Test:** two instances on one PC, re-hosting a turn-1 autosave, client joining afterwards. Nobody was auto-seated.

**Likely cause: the name source.** TPlayer.ReadWrite 0x5575314C:
- Reads the leader-hero reference [p+0xD4] (tag 0x13) only under engine-mode conditions, so the lobby's LoadHSM of the save (hPickMap, THSEngine VMT+0xA8 = LoadHSM) can leave it nil. v1 then stored [p+0x4C], which is not the lobby name.
- Tag 0x1E: on write (when [map+0x3C]&2 and the leader is alive) it streams the LIVE leader hero. On read it lands in [p+0x58] (TLeader), and hPickMap copies that into rec+0x1C. So **[[p+0x58]+0x60] = the leader's saved name**.

**v2** (`patch_mp_reload_autoclaim_v2.py`; 'MRA2', 715 B, same zone, table and sites; upgrades from v1; --revert goes to vanilla; backup `.bak_mpautoclaim2`):
- Name passes, in order: [p+0x58] → [p+0xD4] → [p+0x4C].
- Gate is (rec+0x19 & 3)==0, matching vanilla.
- Diag block DATA 0x558E9F78: players seen / humans / entries / runs / save marker.

**Probe:** `patch scripts\autoclaim_probe.py`. Read-only; dumps every AoWx.exe; finds TSetupControl by scanning for the TSetupSettings VMT; dumps the table, diag, own player, remote players, and records including the leader name [[rec+0x1C]+0x60].

**Other facts:**
- Host = in the remote list (SetupHost → hConnectPlayer for itself).
- Client pref is 0xFF at connect (SetupUser).
- SP: the pick cave only clears the table, so it can't cause the blank SP leader.

⚠ 10/22 MISTAKE: a `--revert` dry-run without `--dll` WRITES (house style: --revert writes). It reverted live autoclaim v1 in the real AoWEPACK.dll (only the 3 sites + zone; the other 1142 B of diffs vs .bak_turnmet are someone else's changes). Restoring with `v1 --apply` was blocked by permissions, so the coordinator must re-apply v1 or apply v2.

## 10/22 v2 live probe → v3 built (not applied; the live DLL is v2)
**Probe result:** v2's table held the MAP template names 'Elf'/'Dark Elf' (from [[p+0x58]+0x60]); [p+0xD4] and [p+0x4C] were empty.

**Why:** a normal save doesn't stream the player's leader reference (tag 0x13 is gated on stream flag 4). The lobby names live only in the TLeader unit objects.

**Offline check of X\Save\autosave.asg** (zlib at offset 5): there are 5 TLeader objects (class id 0x20232). Each carries a **tag-0x5A byte = owner slot**:
- 1 → 'Peewee the Peony'
- 5 → 'Peewee the Peony2'
- 2 → 'Azrac', 3 → 'Lizard', 4 → 'Frostling'

**v3** (`patch_mp_reload_autoclaim_v3.py`; 'MRA3', 968 B in the 1 KB zone; --apply from vanilla, v1 or v2; --revert goes to vanilla; backup `.bak_mpautoclaim3`). Name passes in order:
- pass 0: a TLeader unit in the player's armies. Walks [p+0x28] TArmyList → [[army+8]+4] units, checking ClassID vcall +0x24 == 0x20232. It does NOT call TArmy.Leader, because Leader Soul hooks it.
- pass 1: a TLeader in the loaded map's THeroControl [map+0xF8] with [hero+0x24] == [p+0xA6].
- pass 2: [p+0xD4].
- pass 3: [p+0x58] template.
- pass 4: [p+0x4C].

Diag block: +4..+7 = hits per source. The probe decodes v2/v3 diag by the zone magic.

**Open risk:** whether army lists / hero control are populated in the lobby-loaded map. LoadHSM installs the loaded map as the engine map, and army/hero load code uses the global map; the v3 diag will show which source hit. Scratch-copy round trip v2→v3→vanilla→v2 is byte-identical to the live DLL.

## 10/22 v3 live: no name source exists in the lobby → v4 built (not applied; the live DLL is v3)
**v3 diag:** army/hero-control TLeader passes had 0 hits. The lobby's LoadHSM of a save never materialises units, and the player records carry no name.

**v4** (`patch_mp_reload_autoclaim_v4.py`; 'MRA4', 840 B; upgrades v1/v2/v3; --revert goes to vanilla; backup `.bak_mpautoclaim4`):
- **TPlayer.InstanceSize** @VMT 0x5570C508−0x1C = **0x5570C4EC: 0xDC → 0xE0**. This adds a new AnsiString field **TPlayer+0xDC**.
  - There are no TPlayer subclasses; other modules import only TPlayer RStrs.
  - The field is not finalised, so a few bytes leak per destroyed player.
- **TPlayer.ReadWrite hook @0x5575320C** (`lea edx,[ebx+0xA6]`, 6 B): stream vcall +0x20 rwString(&[ebx+0xDC], **tag 0x10061**) in every mode.
  - The writer skips empty strings and raises on a duplicate tag.
  - The reader clears the field when the tag is missing.
  - The compare stream compares the values.
- **SetupMap hook @0x557E0CFD** (`cmp byte [eax+8],0; jne 0x557E0D57`, 6 B, inside the GetRemote branch; eax = record, esi = TPlayer): for a Human slot whose owner id is in the remote list, LStrAsg([esi+0xDC], lobby name). It runs on every machine.
- **Pick passes:** 0 [p+0xDC], 1 [[p+0xD4]+0x60], 2 [[p+0x58]+0x60], 3 [p+0x4C].
- **Diag:** +4..+7 = hits per pass.

Offline (pname_validate.py in the scratchpad, on autosave.asg): the real player tables (ids 1-5) carry tags 2 3 5 a 10 12 17 19 1c-24 27 33-36 3a, highest 0x3a. Appending 0x10061 leaves every original offset unchanged, and the missing tag reads as ''.

Scratch round trip v3 → v4 → vanilla → v3 is byte-identical to the live DLL. The probe shows the game map's [p+0xDC] names when a game is loaded. Pre-422 saves can't be helped.

**Live test:**
1. Start a NEW MP game on v4.
2. Probe in game: the human players show their lobby names.
3. Save, quit, re-host: the v4 diag pass-0 hits = humans, and both players are seated.
- 10/22 full offline scan (every X\Save\*.asg + Scenario\Custom\AoWx*.hsm): 6086 player-like tables (filter caps tags at 0x40, many false positives), tag 0x10061 absent everywhere, original offsets intact → ALL OK.

## 10/22 v4 live → v5 built (not applied; the live DLL is v4)
**v4 live:** the table names were right (TPlayer+0xDC hits 2), but the host was seated as AZRACS and the client not at all.

**ROOT CAUSE: [rp+0x10] preferred race is a RACE id.** TSetupSettings.IndexOfRace 0x557DF668 matches **rec+0x18** (race). rec+0x20 is IndexOfPlayer 0x557DF610's key. The earlier note above ("pref = player INDEX") is WRONG.
- v1-v4 stored the player index: 1 → Azracs; 5 → Halflings, which isn't on the map.

**Second bug:** v4 skipped seated players. The client's next hUpdatePlayer (Assign → pref 0xFF) then made vanilla UpdatePreferredRaces release the seat.

**v5** (`patch_mp_reload_autoclaim_v5.py`; 'MRA5', 886 B; upgrades v1..v4; --revert goes to vanilla; backup `.bak_mpautoclaim5`):
- The table stores [p+0xA5] (race).
- AutoClaim (re)sets pref = race when the record is free or already owned by this rp, and the rp isn't seated in a different record.

Offline model (scratchpad reloadre\autoclaim_v5_model.py) on the v4 autosave.asg: players 1/5 carry 0x10061 'Peewee the Peony' / '...2'. The model gives host → pref 4 Elves and client → pref 8 Dark Elves, still seated after a 0xFF update. **The v4 string record = length byte + chars**, stored at the position of the hook (after tag 0xA).

Scratch round trip v4 → v5 → vanilla → v4 is byte-identical to live. The probe labels v5 table keys as races.
