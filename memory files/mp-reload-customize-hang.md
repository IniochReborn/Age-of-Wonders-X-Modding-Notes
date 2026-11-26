---
name: mp-reload-customize-hang
description: "MP save-resume hang ('Waiting for other players' forever) root-caused 9/3: vanilla hValidateSetupMap requires the leader-customized bit even on loaded games (where customization is skipped) whenever CustomizeLeaders is on — exposed by our mpdefaults patch defaulting it ON. Fix build_mpreload_customize_fix.py ✅ USER-CONFIRMED WORKING 9/3, ships in 1.37.408. Holds the full TSetupControl handshake RE."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4b6bfb53-91e1-4cc3-8699-ddc7e9ed419a
  modified: 2026-09-03T06:32:19.630Z
---

**Symptom (user report 2026-09-03):** in yesterday's MP session, every attempt to
reload/resume a saved game (autosave, to give a dead player another chance) left ALL
players stuck on the "Waiting for other players" screen. Deterministic — every attempt.

## Root cause — VANILLA logic bug, exposed by [[mp-default-race-cpu-emperor]]'s defaults patch
`patch_mp_setup_defaults.py` (applied, live) defaults **CustomizeLeaders ON**
(`TSetupSettings.Reset` @0x557DF5B2: `mov byte [ebx+2Ah],1`). Vanilla defaults it OFF,
which is the only reason vanilla players don't hit this:

* The network game-start handshake = **AoWSetup.TSetupControl (AoWEPACK.dll)**.
  Phases enum: spIdle 0, spSetupPlayers 1, spCustomizeLeaders 2, spSendMap 3,
  spLoadMap 4, **spSynchronize 5**, spSetupMap 6 (phase byte = [ctrl+0x25]).
* "Waiting for other players" = **TSynchronizeDlg** (AoWx.exe DFM @file 0x1C7B00;
  class VMT 0x413334, published DlgShow 0x413570/FaceFramePreDraw 0x4134F8) — dumb UI
  shown by the OnSynchronize event ([ctrl+0x68], fired at phase 5).
* Each machine: LoadMap (phase 4, OnLoadMap loads the file) → `MapLoaded` @0x557E060C →
  if **TSetupSettings+0x20 != 0** (game-in-progress marker, see below) → phase 5 +
  OnSynchronize (customization SKIPPED); clients send **setup msg 7** to host; host
  `hMapLoaded` @0x557E05C0 sets **bit 0x08** in TPlayerSetupSettings+0x19.
* Host barrier `hValidateSetupMap` @0x557E1168: every counted slot
  (skip `[psettings+8]!=0`) needs **bit 0x08**, AND — whenever `[settings+0x2A]`
  (CustomizeLeaders) is on — **bit 0x04** (leader customized, set only by
  `hLeaderCustomized` @0x557E06F0 via the customize flow). **No loaded-game exemption**,
  though MapLoaded skips the whole customize flow for loaded games ⇒ bit 4 never set for
  anyone ⇒ barrier never passes ⇒ host never broadcasts **msg 6** (SetupMap) ⇒ everyone
  waits forever. All machines stuck = exactly the observed symptom.
* `TSetupSettings+0x20` is written in `hPickMap` @0x557E21A8 from the picked file's
  +0x174 field — nonzero for saves/autosaves ("game in progress"), 0 for virgin maps.
  Same field gates SetupMap's hero-library refresh (new games only) @0x557E0CA5.

## Fix — `patch scripts/build_mpreload_customize_fix.py` 🔨 APPLIED 9/3, awaiting LAN test
Backup `AoWEPACK.dll.bak_mpreload`; dry-run/--apply/--revert surgical; reloc-scans
hook+cave at run time (clean). Displaces the 6-byte gate @0x557E11AA
(`cmp byte [ebx+2Ah],0 / je 557E11C3`; ebx=TSetupSettings loaded @0x557E11A7) to cave
**0x55815500–0x55815530** (22 B, all rel32/reg-relative = PIC-safe under rebase):
`[ebx+0x20]!=0 → satisfied; [ebx+0x2A]==0 → satisfied; else vanilla bit-4 check
@0x557E11B0`. Mirrors MapLoaded's own skip logic exactly.
**Next free AoWEPACK cave: 0x55815530.**

* Host-side logic but ships in AoWEPACK.dll (identical on all machines anyway).
* Fallbacks if it misbehaves: `--revert`, or host unchecks Customize Leaders in the
  resume lobby, or revert `patch_mp_setup_defaults.py`.
* TEST: LAN host+join, autosave, resume the save both ways (in-session load AND lobby
  re-host picking the .asg): must pass "Waiting for other players" and continue. Also
  retest a NEW game with customize leaders on (vanilla path must still gate on bit 4).

## Handshake RE bank (for future setup-flow work)
* `TSetupControl.PackageReceived` @0x557E0088 msg switch (ids 0..0xB, table 0x557E00A2):
  0 hConnectPlayer · 1 hDisconnectPlayer (host) · 2 hUpdatePlayer (host) ·
  3 map-info+ValidateMap (client, phase 1) · 4 map data → ValidateMap → OnLoadMap →
  LoadMap (client) · 5 hLeaderCustomized (host) · **6 → SetupMap (client; the barrier
  release)** · **7 hMapLoaded (host)** · 8 → SetupMap-adjacent (host event [ +0x98]) ·
  9 hValidateSendMap (host) · 0xA SendMessage+LoadMap (client send-map flow) ·
  0xB host event [+0x80].
* `ValidateMap` @0x557DFF90: settings +0x14 filename, +0x18 CRC32 (GetFileCRC32),
  +0x1C HSSet id; result 1=wrong set / 2=missing-or-CRC-mismatch (→ map transfer) /
  3=have identical file.
* TPlayerSetupSettings+0x19 flag bits: 0x08 map loaded · 0x04 leader customized.
* `TSetupSettings.Reset` @0x557DF5A4 shows the mpdefaults patch bytes live
  (+0x3D=2 tcaAlways, +0x2A=1 CustomizeLeaders, +0x3E=1 AlwaysViewTC).
* Official resume flow (vanilla Readme §5): re-host from Scenario Setup picking the
  .asg — goes through this same handshake, so it hung identically with customize on.

Related: [[lan-desync-investigation]] (token layer, NOT involved here),
[[patching-over-relocs-gotcha]], [[rebase-crash-runtime-error-216]].


## Index note (moved verbatim from MEMORY.md 2026-09-21)
- ✅ [mp-reload-customize-hang.md](mp-reload-customize-hang.md) — MP save-resume "Waiting for other players" forever: VANILLA hValidateSetupMap bug (requires leader-customized bit on loaded games where customization is skipped), exposed by mpdefaults' CustomizeLeaders-ON default. Fix USER-CONFIRMED 9/3, shipped in **1.37.408** (cut 9/3: fix + user's campaign typo edits; see [[aowx-release-process]]). ⭐ Holds the full TSetupControl lobby/resume handshake RE (msg map, phase enum, flag bits).
