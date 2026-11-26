---
name: aowx-bag-ability-crash
description: TArmyCombatMoveTE combat-start crash/soft-lock from unequipped ability item in hero backpack; fix patch_bag_ability_crash.py; token-event system offsets; 409-folder + laptop cave map
metadata: 
  node_type: memory
  type: project
  originSessionId: da93d5dd-691e-4170-9020-efa47704d08f
  modified: 2026-09-10T04:00:42.802Z
---

**Bug (diagnosed live 2026-09-09, player-reported save, game folder `Age of Wonders X - 409`):**
"Exception occurred during TArmyCombatMoveTE" when combat starts (choosing tactical/auto)
with a hero carrying an **unequipped ability item in the backpack** (repro item: Leadership III
in THeroInventory). After dismissing the error the attacker+defender stay vanished and the game
soft-locks (orders queue but never run).

**Root cause — an AoWx bug from 1.37.406** ([[aowepack-ability-system]] item-ability-levels v3):
cave_findrec @0x558124A0 searched BOTH hero containers unfiltered, but vanilla inventory legs
(e.g. THeroInventory.GetSuperlativeAbOwner 0x557861F4 @+0x4B) only count backpack items with
byte `[item+0x34]==6`. So GetAbilityLevel (THero.GetAbilityLevel 0x5578831C has a vanilla
owner=nil→self fallback at +0x16) returned 3 while GetAbilityOwner (raw finder 0x557881DC,
bit+filter based, no fallback) returned nil. Vanilla TArmy.UpdateFormation 0x5578D034 (scans
army for max Leadership id 0x2E when units are added during combat-party assembly:
TFastCombat.Activate → … → THero.SetOwner → TArmy.AddChild → Changed → Update →
UpdateFormation) derefs the nil owner at 0x5578D0E7 → AV → Delphi aborts the token event.

**FIX APPLIED 2026-09-09/10** to the 409 folder's AoWEPACK.dll: `patch scripts\patch_bag_ability_crash.py`
(dry-run/--apply/--revert, backup `.bak_bagability`):
- A) hook @0x55812543 (13B TItem-VMT check) → subcave @0x558125A8: same check + skip backpack
  items (container offset ebp==0x74) with `[item+0x34]!=6` — vanilla-consistent.
- B) hardening: UpdateFormation's `call [ecx+0x154]` @0x5578D0DE → guard cave @0x558125E0:
  nil owner → skip unit (jmp 0x5578D11E) instead of deref. Both caves in the reserved
  item-ability v2 slack; rel32-only, reloc-checked. Player saves need no repair (bag item is
  legal state). NOT applied to AoWEPACK.dev (different build) or the stale main-folder dll.
  Verification pending at session end: user to re-run the crash save on the patched dll.

**Token-event (TE) system internals** (offsets verified live in 409): map(TAoWHSMap)+0x23C →
TAoWTokenManager {+0x04 TTokenExecuter, +0x08 TTokenPackageDistributer, +0x10/+0x48 TList of
TTokenControl (per player?), +0x38 current TTokenControl, +0x44 TTokenEventList, +0x5C
TEventList, +0x4C/+0x50 event counters}. TTokenExecuter {+0x10 TTokenEventList, +0x18
received-count, +0x1C executed-count} — after the aborted TE the gap stuck at 12 = wedged
queue = the soft-lock (UI stays responsive, CPU normal; only game orders die).
TTokenEventList: linked TEReferenceNode structure at +0x08, TEObjectList at +0x18 (also
node-based, not array). TE objects are freed after their exception is caught — scan for live
instances finds only class-registration tables.

**Environment (since 2026-09-09):** user plays from `Age of Wonders X - 409\` subfolder on the
desktop; versions 407–409 were built on the LAPTOP with Claude — their patch scripts are NOT on
this desktop; desktop main-folder binaries are stale (8/26, ~406). 407–409 changes are readable
from the changelog JSON inside `409\.AoWx Manual.html`. ⚠ Laptop-made caves in 409's AoWEPACK.dll
occupy VA 0x55812000–0x5581206E and 0x55813200–0x558155EE — the old "free from 0x55812C80"
note in [[aowepack-ability-system]] is unsafe; verify zeros on the actual target dll before
allocating (0x55812C80 gap happened to be free in 409).

**Tooling:** `patch scripts\diag_veh_logger.py` — VEH **first-chance exception logger** variant
of diag_inject_veh.py ([[aowx-7th-language-crash]]): launches AoWx suspended from the 409
folder, injects a ring-buffer VEH that logs every exception (code/addr/regs + 1KB stack copy)
and CONTINUE_SEARCHes so the game behaves normally; python side symbolizes via live module list
+ AoWEPACK exports and decodes Delphi 0x0EEDFADE (raise addr + exception object). Beats the
Delphi-heap heisenbug AND catches handled exceptions. Startup always logs one benign ILB-load
Delphi exception from ILPACK+0x17850 — ignore it.
