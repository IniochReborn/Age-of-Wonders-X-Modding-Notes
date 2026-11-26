---
name: hero-levelup-event-fixed-location
description: "Hero level-up events in the event log now center on the ORIGINAL level-up location (fixed) instead of following the hero's current position (which let players track enemy heroes). AoWEPACK.dll, 2026-07-23. CONFIRMED WORKING in-game."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T20:13:35.113Z
---

**GOAL (user):** In the event log, right-clicking a **hero level-up** event centered on the hero's CURRENT location (it FOLLOWED the hero even after it moved) → let players track enemy heroes. Fixed so it centers on the ORIGINAL location where the level-up happened (like battle events do). Applied 2026-07-23. Backup `AoWEPACK.dll.bak_heroevt`.

**RE (AoWEPACK.dll, VA=file+0x55700C00; EventLog is a Delphi unit with exported class methods):**
- Event class = **THeroUpgradeEventLog**, VMT base **0x55711B88** (vtable+0x74 = ViewLocation). Fields: [+0x18]=hero ID (4b, resolved via 0x5577E948 = get-unit-by-token on [mapglobal 0x558fa040 +0xfc]); [+0x1c]/[+0x1d]=old/new level (used by GetText); **[+0x20]=4b, SERIALIZED (ReadWrite tag 0x1c @0x55785545) but otherwise UNUSED** → repurposed to store the location.
- **THeroUpgradeEventLog.ViewLocation @0x557857E0** (the culprit): resolves hero from [+0x18], calls GetLocation(hero) @0x5577ED94 (CURRENT loc), centers via **TEventLog.CenterViewTo @0x557FD5F4** (`push level; cl=y; dl=x; eax=Self; ret 4`). Base TEventLog.ViewLocation @0x557FD64C uses the virtual GetLocation instead; THeroUpgradeEventLog overrides ViewLocation to follow.
- Battle events (TCombatEventLog.ViewLocation @0x55729274) center on a STORED fixed loc — the desired pattern.

**FIX (2 caves, both PIC-safe; free space after true-seeing caves):**
1. **cave_evtcap @0x5580F600 (118B)** — hooked into **TEventLogbook.AddEvent @0x557FDB9D** (stole the rel32 `call 0x55775608`, re-emit + jmp 0x557FDBA2). Runs when ANY event is added (hero still at the level-up spot). If the event's VMT ([esi]) == THeroUpgradeEventLog VMT (computed PIC via delta since the object's VMT ptr is rebased): resolve hero from [esi+0x18], GetLocation → 3 output bytes, store to **[esi+0x20]/[+0x21]/[+0x22]** and set **[esi+0x23]=1** (valid flag). Captures the same 3 bytes ViewLocation reads (no need to know which is x/y/level — just replay them). Skips if not hero-upgrade / hero gone / unplaced.
2. **cave_vloc @0x5580F6C0 (38B)** — the **VMT ViewLocation slot @0x55711BFC repointed** 0x557857E0→cave_vloc. If [event+0x23]!=0: CenterViewTo(dl=[+0x20], cl=[+0x21], push [+0x22]) = the STORED original location. Else: `jmp 0x557857E0` (original follow-hero, for pre-mod/old-save events).

**SAVE/MP-SAFE by design:** [+0x20] is already serialized, so the stored location persists in savegames AND network sync automatically. Old events (flag byte=0, since objects zero-init and the field was unused) fall back to the original behavior. VMT-slot repoint keeps its base-reloc entry so it rebases correctly. Emulation-verified at preferred AND rebased (0x01170000) base: capture correct, fallback correct, stack balanced.

**CONFIRMED WORKING in-game 2026-07-23** (right-click centers on the original level-up spot, not the moving hero). Restore point 2026-07-23b refreshed with this fix. (Test done: SP — hero levels up, MOVE it, then right-click the level-up event → jumps to the ORIGINAL spot, not the hero.) MP — an enemy hero (in your vision) levels up + moves → right-click → jumps to where it leveled up (can't track it). Regression — battle/production/other events still center correctly; your OWN hero level-up also jumps to the original spot (acceptable). If MP observers still track, the capture may need to move from AddEvent to the actual event-creation site (factory-created; not yet located).
