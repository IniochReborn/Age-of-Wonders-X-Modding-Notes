---
name: mp-default-race-cpu-emperor
description: "LAN MP lobby: default race owner changed from Free(5) to CPU Emperor(7). A player's Preferred Race still overrides it, and host-Forced/map-assigned races still win. AoWEPACK.dll, applied 2026-07-23 (Ghidra-verified model). CONFIRMED WORKING in-game."
metadata:
  node_type: project
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T21:40:13.192Z
---

**GOAL (user):** In LAN MP setup, unassigned races should default to **CPU Emperor** instead of **Free**; a player's **Preferred Race** must still be able to claim/override that default (as it did with Free); host-**Forced**/map-assigned races keep precedence. User simplified: preferred races only need to override the new Emperor default (other CPU ranks only appear if host-set → leave protected). **APPLIED 2026-07-23**, backup `AoWEPACK.dll.bak_mprace`. Supersedes the earlier SHELVED note (whose hand-RE data model was WRONG — see below).

**CORRECTED DATA MODEL (Ghidra, AoWEPACK.dll unit "AoWSetup"; CODE va=file+0x55700C00, but DATA/BSS need per-section mapping — the old note's pointer-vs-byte confusion came from reading DATA globals with the CODE formula):**
- **Per-race record** (setup[+0x28] list, via `GetSettings @0x557DF5F4` = `[[setup+8]+4][idx*4]`; `IndexOfRace @0x557DF610` matches race byte at `[rec+0x20]`): **[rec+8] = owner-TYPE byte enum** (NOT a pointer); [rec+0xc]=owner-id dword (0=unclaimed); [rec+0x10]=fallback/forced-type byte; [rec+0x14]=forced id; [rec+0x19]=flags (bit1=2 = Forced-lock).
- **Type enum:** 0=Human,1=CPU Warrior,2=Knight,3=Lord,4=Independent,**5=Free**,6=CPU King,**7=CPU Emperor**.
- **pid globals** = 8-byte {enumDword, 0} structs @0x558E8E58 stride 8: pidFree={5}, pidHuman={0}, pidCPU1={1}, pidCPU2={2}, pidCPU3={3}, pidCPU4/King={6}, **pidCPU5/Emperor={7} @0x558E8E88**, pidIndep={4}.
- **Default-setter = race-record builder @~0x557E2380** (NOT ResetPlayerSettings, which is only reset/release): `call GetRemote(0x557e125c); je host_branch;` then if `byte[src+0xa9]==0` (src=[ebp-0x14]=map slot; a9!=0 ⇒ map-assigned ⇒ host branch) → **MP default: `mov byte[rec+8],5` @0x557E2398 + `mov byte[rec+0x10],5` @0x557E239F**. Host/SP branch uses map type `src[0xa7]` or CPU1(1). ⇒ the Free default is **MP-only, non-map-assigned races only**. GetRemote (byte[Self+0x24]&4) is TRUE on the LAN host too (means "networked game", not "am I a client") — that's why the host sees Free.
- **Claim = `UpdatePreferredRaces @0x557E1484`** (host-only): for each player with pref race, `rec=GetSettings(IndexOfRace(pref))`; claim iff **`rec[0xc]==0`** (unclaimed) **AND `(rec[0x19] & DAT_557e1658)==DAT_557e165c`** (flag gate). Claim = release player's old race (ResetPlayerSettings unless Forced bit2) then `rec[8]=0(Human); rec[0xc]=playerid`. **Claim never checks the type enum** → default 5 vs 7 is equally claimable; host-Forced (flag) slots are skipped. So changing only the default type gives the user's exact behavior with ZERO claim-logic change.
- `GetPlayerSetupValid @0x557E1AB0`: `rec[8]!=5` = "assigned"; counts as real player if `rec[8]<4 || rec[8]-6<2` (i.e. {0,1,2,3,6,7}). Emperor(7) counts as a real player ✓. Only site reading `cmp byte[rec+8],5` (@0x557E1AE4) — no code treats Free as "empty" via type; unclaimed is detected by rec[0xc]==0.

**PATCHES APPLIED (3, all MP-only, rebase-safe):**
1. `0x557E2398`: `c6 40 08 05`→`c6 40 08 07` — MP default owner Free→Emperor.
2. `0x557E239F`: `c6 40 10 05`→`c6 40 10 07` — MP default fallback Free→Emperor (so a released race reverts to Emperor, not Free).
3. `0x557E1406`: `8b 15 58 8e 8e 55`→`8b 15 88 8e 8e 55` — ResetPlayerSettings remote-branch reads pidCPU5(7) instead of pidFree(5); paired id-read @0x557E140F unchanged (both pidFree+4 and pidCPU5+4 = 0 ⇒ rec[0xc]=0). Base-reloc at 0x557E1408 verified intact.
SP/single-player default (host branch, CPU1/map-type) deliberately untouched. Map-assigned & host-Forced races untouched.

**CONFIRMED WORKING in-game 2026-07-23** (LAN lobby default now CPU Emperor; preferred-race override + host precedence intact). In restore point 2026-07-23c.

**TEST (LAN):** host a LAN game → all unclaimed races should show **CPU Emperor** (not Free). A player setting a Preferred Race should still claim/override an Emperor slot. Host-forcing a player to a race should still win. Releasing a claimed race → reverts to CPU Emperor. Start should be allowed with 1 human + rest CPU Emperors. Ghidra workflow: see [[designer-only-portrait-toggle]]. Rebase rule: [[rebase-crash-runtime-error-216]].

**⚠ 2026-09-03:** the sibling defaults patch `patch_mp_setup_defaults.py` (CustomizeLeaders default ON) exposed a VANILLA handshake bug — MP save-resume hung forever at "Waiting for other players". Engine-level fix applied (keep the default ON): see [[mp-reload-customize-hang]].
