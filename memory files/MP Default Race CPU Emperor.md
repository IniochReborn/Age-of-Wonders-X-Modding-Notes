# MP Default Race: CPU Emperor

**One-line:** In the LAN multiplayer lobby, unassigned races default to **CPU Emperor** instead of **Free**. A player's Preferred Race still claims/overrides it, and host-Forced / map-assigned races still win.
**Status:** CONFIRMED working in-game, applied 2026-07-23 (Ghidra-verified data model). 3 MP-only byte edits, no caves.

---

## Files patched
- **AoWEPACK.dll**, unit `AoWSetup` (ImageBase 0x55700000; CODE VA = file_offset + 0x55700C00). Backup: `AoWEPACK.dll.bak_mprace`.

> Note on addressing: CODE follows VA = file + 0x55700C00, but DATA/BSS globals are in different sections — do not use the CODE formula to read data globals (that mistake produced a wrong "pointer vs byte" model in an earlier abandoned attempt).

---

## RE findings (data model)

**Per-race setup record** — list at `setup[+0x28]`, reached via
`GetSettings @0x557DF5F4` = `[[setup+8]+4][idx*4]`; `IndexOfRace @0x557DF610` matches the race byte at `[rec+0x20]`. Record fields:
- **`[rec+8]` = owner-TYPE byte (enum, NOT a pointer)**
- `[rec+0xC]` = owner-id dword (0 = unclaimed)
- `[rec+0x10]` = fallback / forced-type byte
- `[rec+0x14]` = forced id
- `[rec+0x19]` = flags (bit1 = 2 = Forced-lock)
- `[rec+0x20]` = race byte

**Owner-type enum:** 0=Human, 1=CPU Warrior, 2=Knight, 3=Lord, 4=Independent, **5=Free**, 6=CPU King, **7=CPU Emperor**.

**pid globals** — 8-byte `{enumDword, 0}` structs at 0x558E8E58, stride 8:
`pidHuman={0}`, `pidCPU1={1}`, `pidCPU2={2}`, `pidCPU3={3}`, `pidIndep={4}`, `pidFree={5}`, `pidCPU4/King={6}`, **`pidCPU5/Emperor={7}` @0x558E8E88**.

**Default-setter = race-record builder @~0x557E2380** (this is where the default owner is stamped; it is NOT `ResetPlayerSettings`, which only resets/releases):
```
call GetRemote (0x557E125C)   ; byte[Self+0x24] & 4  => "networked game" (TRUE on the LAN host too)
je   host_branch
; if byte[src+0xa9]==0  (src=[ebp-0x14]=map slot; a9!=0 => map-assigned => host branch)
mov  byte[rec+8], 5           ; @0x557E2398  <-- MP DEFAULT owner  = Free
mov  byte[rec+0x10], 5        ; @0x557E239F  <-- MP DEFAULT forced = Free
```
So the Free default is **MP-only and only for non-map-assigned races**. The host/SP branch uses the map type `src[0xA7]` or CPU1(1). `GetRemote` returns true for the host as well (it means "networked", not "am I a client") — which is why the host sees Free by default.

**Claim = `UpdatePreferredRaces @0x557E1484`** (host-only). For each player with a Preferred Race: `rec = GetSettings(IndexOfRace(pref))`; claim iff `rec[0xC]==0` (unclaimed) AND `(rec[0x19] & DAT_557E1658)==DAT_557E165C` (flag gate). Claim releases the player's old race (via `ResetPlayerSettings` unless Forced) then sets `rec[8]=0 (Human); rec[0xC]=playerid`.
**Key insight:** the claim logic never inspects the owner-type enum — unclaimed is detected purely by `rec[0xC]==0`. So default 5 vs 7 is equally claimable, and host-Forced slots are skipped by the flag gate. Changing only the default type gives exactly the desired behavior with ZERO claim-logic change.

**`GetPlayerSetupValid @0x557E1AB0`:** treats `rec[8]!=5` as "assigned"; counts a slot as a real player if `rec[8]<4 || rec[8]-6<2` (i.e. type in {0,1,2,3,6,7}). Emperor(7) counts as a real player, so a start with 1 human + rest Emperors is allowed. The only site that compares `byte[rec+8]` to 5 is @0x557E1AE4 — no code treats Free as "empty" by type; empty is `rec[0xC]==0`.

**`ResetPlayerSettings` remote branch @~0x557E1400:** reads a pid global into edx then its id (+4). Repointing the type-read from `pidFree` to `pidCPU5` makes a *released* race revert to Emperor instead of Free (both globals have id dword = 0 at +4, so the paired id-read is unaffected).

---

## The patch (3 MP-only byte edits — VA / file offset / old -> new)

| # | file off | VA | old bytes | new bytes | meaning |
|---|---|---|---|---|---|
| 1 | 0x0E1798 | 0x557E2398 | `C6 40 08 05` | `C6 40 08 07` | MP default owner Free(5) -> Emperor(7) |
| 2 | 0x0E179F | 0x557E239F | `C6 40 10 05` | `C6 40 10 07` | MP default fallback Free(5) -> Emperor(7) |
| 3 | 0x0E0806 | 0x557E1406 | `8B 15 58 8E 8E 55` | `8B 15 88 8E 8E 55` | ResetPlayerSettings remote reads pidCPU5(7) @0x558E8E88 instead of pidFree(5) @0x558E8E58 |

Edit #3 changes only the operand low byte at file 0x0E0808 (0x58 -> 0x88), redirecting the global pointer from 0x558E8E58 to 0x558E8E88. The base-reloc entry covering 0x557E1408 was verified intact (so it still rebases correctly).

Single-player / host-branch default (CPU1 / map type) and all map-assigned and host-Forced races are deliberately **untouched**.

---

## Mechanism
The only thing that changes is which owner-type enum the MP default-setter stamps onto an unassigned, non-map race (Free 5 -> Emperor 7), plus the released-race revert value. Because claim/override and "real player" detection key off `rec[0xC]` (owner-id) and the flags word — never the owner-type enum — Preferred-Race claiming, host-Forced locking, and map-assigned precedence all keep working with no other change.

---

## Landmines & notes
- **Rebase-safe:** edits 1 and 2 are immediate byte constants; edit 3 only changes a global's low operand byte and its base-reloc is intact. No PIC concerns.
- Do NOT "fix" the SP/host branch — leaving it on CPU1/map-type is intentional; other CPU ranks (King, etc.) only appear when the host sets them, and those Forced slots are protected by the flag gate.
- `GetRemote` being true on the host is not a bug — it means "networked game." Both the host and clients see the Emperor default; the host's `UpdatePreferredRaces` then resolves claims.
- Test (LAN): host a game -> all unclaimed races show **CPU Emperor**; a player setting a Preferred Race claims/overrides an Emperor slot; host-forcing a race still wins; releasing a claimed race reverts to CPU Emperor; start allowed with 1 human + rest Emperors.
