---
name: exploration-site-fix
description: "✅ COMPLETE + user-confirmed 2026-08-11: MP tactical combat at exploration sites (lair/dungeon/crypt/ruin/pyramid) fully works — dialog, observer vision through the explorer, observer camera follows both sides, defenders engage immediately. Root cause of years of crashes: the always-1 GetExplored stub was masking a nil-field deref."
metadata: 
  node_type: memory
  type: project
  originSessionId: 369fb823-fe98-4958-bb73-a369ba9e9683
  modified: 2026-08-11T19:46:09.403Z
---

## ✅✅ ALL WORKING — USER CONFIRMED 2026-08-11 ("everything works perfectly")
Final live patch set (all in AoWTCPCK.dll, apply order as listed):
1. `patch scripts/build_mp_site_observer_vision.py` — cave 0x438500-0x4385C0,
   hook 0x41BED8. Observer views through the explorer; seat cleared to 0xFF so
   they get vision only (no unit control, no end-turn, no gold/mana).
   ⚠ do NOT --revert (its backup predates the nil-guard).
2. `patch scripts/build_getexplored_nilguard.py` — thunk 0x40287C → cave
   0x4385C0 (54 B). Real exploration semantics + nil-field guard + observer
   clause (seat==0xFF ⇒ report explored, so the camera follows BOTH sides).
   This is the correct revert entry point for the GetExplored work.
3. `patch scripts/build_defenders_engage_immediately.py` — 5 bytes @0x4183B7.
Helper: `patch scripts/toggle_getexplored_stub.py` (now reports UNKNOWN — see below).
**Next free AoWTCPCK cave: 0x438620.**

**GOAL:** in MP, entering an exploration site (lair/dungeon/crypt/ruin/pyramid/
item site) should offer the tactical-vs-auto dialog like SP does. Two earlier
attempts made the dialog appear but the tactical map was BLACK for observing
players, or crashed. Both reverted. **Only surviving change: the
`AoWE.TAoWMapField.GetExplored` import thunk in AoWTCPCK.dll (file 0x1C7C,
VA 0x40287C) stubbed to `b8 01 00 00 00 c3` = `mov eax,1; ret`** (always
"explored") — the "defenders attack immediately instead of waiting to be seen"
behaviour the user kept. Verified 2026-08-11 that the old cave/site patches
(1AF03, 1AF14, 28D35, 1B154, 3738B) are all back to stock; 0x373DA region now
holds the unrelated blood-mod cave.

## THE CHAIN (all RE'd 2026-08-11)
1. **UI trigger:** `TIWindow.MainBtnClick` (AoWx.exe @0x442328). At 0x442426 it
   IsClass-tests the selection against classref [0x45E650] (exploration site)
   and calls **vcall [site_vmt+0x200] = `Search`**. No MP gate here.
2. **`ExploreS.TExplorationSite.Search` @0x557C1E5C** decides dialog vs auto:
   ```
   mov edi,[map+0x140]        ; TPlayerList
   mov eax,[edi+0x18]
   cmp dword [eax+8],1        ; <-- MOD PATCH: replaced by `xor eax,eax; nop; nop`
   je  dialog                 ;     so the dialog branch is ALWAYS taken
   cmp byte [map+0x139],0 / je auto
   ```
   ⚠ **The `xor eax,eax` at 0x557C1EA0 is BASELINE mod** (present in all 120+
   AoWEPACK.dll.bak_*; stock AoWEPACK.dpl has `83 78 08 01`). Do not mistake it
   for a leftover of the shelved attempt.
3. **Dialog raised** at 0x557C1EF4: `push site; push RequestCombatTypeCallBack;
   cl=1; edx=eventlog; call [map_vmt+0x12c]` =
   **`TAoWHSMap.TriggerExecuteEventLog` @0x55776624**: `cl!=0` →
   `TriggerNotifyEvents([map+0x1D0])` (fire immediately, UNQUEUED);
   `cl==0` → `TExecuteEventLogCallBackList.Add([map+0x1D4])` + ExecuteNextEventLog
   (QUEUED, serialized, Done-callback driven).
4. **UI handler:** `TMapEvents.TheMapExecuteEventLog` (AoWx.exe) dispatches by
   class; combat-type log → **0x00439ADC (a `TTCFCDialog` method)**.
5. **✗ NOT A GATE — hypothesis KILLED 2026-08-11. 0x00439AE5:**
   ```
   mov eax,[0x45A5FC]; mov eax,[eax]      ; global UI object (var @0x45B288)
   cmp byte [eax+0xAD],0
   je  0x439B22                            ; 0 -> actually SHOW the dialog
   ; else auto-answer, no window:
   ;   [dlg+0x74]+0xB0 ("always tactical" pref) ? Select(2) : Select(1)
   ;   then `call [ebp+8]` -> the callback runs immediately
   ```
   `Select` = `[log+0x18] = dl`. **Combat type values: 1 = AUTO-RESOLVE,
   2 = TACTICAL, 0 = cancel** (confirmed by `ExecuteSearch`:
   `cmp byte [ebp-1],1 / jne tactical`; the ==1 branch does CreateCombat +
   resolve + TCombatEventLog logbook entry).
   **★★ THE OBJECT IS `TDWin`** (the generic yes/no dialog window; VMT
   0x00450334, methods DButtonClick/yesBtnClick/DebugDOkBtnClick/DialogKeyDown;
   its "show confirm" entry is 0x4505BC, used by Disband/Quit/EndTurn/
   FormCloseQuery). Chain: `M[0x45A5FC] = 0x45B288` (BSS var) → object.
   **★★ THERE IS NO WRITER — the auto-answer branch is DEAD CODE.**
   Exhaustive scan of AoWx.exe for every x86 encoding of a byte access at
   disp32 0xAD (88 /r, 8A /r, C6 /0, 80 /7, 0F B6, all 8 base regs × all 8
   source regs) found exactly ONE write, `mov [ebx+0xAD],al` @0x00433016 —
   and that belongs to the **Disjunction dialog** storing a map-location
   triple at +0xAC/+0xAE, a different class. Live ReadProcessMemory probe
   (scratchpad probe_ad.py) reads **[TDWin+0xAD] = 0** at the main menu and
   after load. So `je 0x439B22` is always taken ⇒ **the dialog is always
   shown; this is NOT the reason MP auto-resolves.** Hypothesis eliminated.
6. **Callback → networked TE:** `RequestCombatTypeCallBack` @0x557C1DBC sets
   `[TE+0x18]=0`, **`[TE+0x20] = chosen combat type`**, then
   `TTokenManager.GetTokenControl([map+0x23C], player)` → `[ctrl+0x10]` →
   the TE runs on **every** client → `TExplorationSite.ExecuteSearch` @0x557C1A20.

## WHY THE OLD ATTEMPTS GLITCHED (hypothesis, now well-supported)
`TArmyCombatMoveTE.SetupCombat` @0x55748D18 — the army-vs-army path that DOES
work in MP — does three things the exploration path does NOT:
- **seated-player gate** @0x5574964D: `cmp [map+0xA5], [log+0x19]`; if this
  machine is not the attacker it first calls `[map_vmt+0xBC]` (centre camera)
  — observers are handled explicitly. ([map+0xA5] = local seated player,
  0xFF = none; [map+0xA4] = current player index, see [[map-password-unlock]].)
- **`[log+0x1A] = TAoWMapField.GetPlayer(field)`** = the DEFENDING player.
  Exploration hardcodes **`[log+0x1A] = 0`** (0x557C1EF0) — player 0 is a REAL
  player id, not "neutral".
- raises the request with **cl=0 (queued)**; exploration uses **cl=1
  (immediate)** so it is not serialized against the token stream.
Since `[TE+0x20]` is transmitted, observers DO execute the tactical branch of
ExecuteSearch — but with no defender player and an unqueued request, which is
where the black map / `TStructureTE` ctor access violation came from (old
receiver note: AoWTCPCK 0x41BD50 `cmp byte [eax+8],1; je 0x41BED8` →
PlaySample + `InitMsg(0x20021001)` + vcall `[combatmap_vmt+0x68]`).

## ★ USER MP TEST 2026-08-11 — dialog CONFIRMED WORKING in MP
Candidate (c) below was right: the tactical/auto window **does** appear in MP
now. Remaining symptoms:
- **Observer**: is correctly pulled into combat observation, but the site's
  tactical map is 100% black/unexplored.
- **Exploring player**: cannot move; many access violations in AoWTCPCK +
  "NewFrame" errors.

### Mechanism of the observer black map (SOLVED, fix not yet built)
Site combat maps carry a **per-player explored bitmask at `[combatfield+0x18]`**
— `AoWE.TAoWMapField.GetExplored(eax=field, edx=player)` @0x55771BF4 is
`stc; mov ecx,edx; mov edx,[eax+0x18]; rcr edx,cl; jb set` (bit player-1);
`SetExplored` @0x55771C04 sets/clears it. **Register convention, plain `ret`
— so the mod's always-true stub of the AoWTCPCK import thunk (file 0x1C7C /
VA 0x40287C → `b8 01 00 00 00 c3`) is stack-safe; it is NOT the crash cause.**
That stub only affects calls made FROM AoWTCPCK: DefaultMove, TCMeleeMoveTE/
TCAbTouchMoveTE.LastMove, TCAbRangedTE.Execute, TCAI.EvalBattle, and
**TCombatUnitSelectionControl.ExecuteMoveSelection ×3 / .UpdateMoveCursor ×2**
(this is the "defenders act immediately" behaviour the user keeps).
**Exploration is only ever seeded by PARTICIPANTS' units:**
`TAbstractAoWHSMap.ExploreArea` (AoWTCPCK thunk 0x4028FC) has exactly two
callers — `TCombatMoveTE.ExecuteDefaultMove+0x23A` (0x4084B2) and
`TTacticalCombatUnitHS.Activate+0xA2` (0x420DBA). An observer owns no units in
the combat ⇒ nothing ever explores for their player id ⇒ bitmask stays 0 ⇒
black. **Proposed fix (display-only, no desync risk): when the local machine is
not a combat participant, call `SetExplorationEnabled(false)` +
`SetFogEnabled(false)` on the combat map.** TAoWCombatMap already has both in
its vtable — thunks 0x4028AC / 0x4028A4, referenced from the class table at
0x413288 / 0x413284.

### ★★ ROOT CAUSE OF THE BLACK OBSERVER MAP — EXACT (2026-08-11)
`TAoWCombatMap.NewTurn` decides, per machine, whether the local box controls the
player whose turn it is. Decoded:
```
0041BCE6 dl=[map+0xED] (current combat player idx)
0041BCF8 TTacticalCombatPlayerList.GetPlayers -> combat player
0041BCFD edx = [combatplayer+8]              ; = the AoW PLAYER ID
0041BD0E TPlayerList.GetPlayers(edx)         ; -> TPlayer
0041BD13 cmp byte [player+0xA7],0 / jne 0x41BED8      ; AI/eliminated? -> "not me"
0041BD3B [AoWHSMap+0x240]+0x1C = TPlayerCommunicationControl
0041BD4B TPlayerCommunicationControl.GetPlayers(pid)
0041BD50 cmp byte [commsrec+8],1 / je 0x41BED8        ; ==1 => player is REMOTE
0041BD5A  <local path>  SetSeatedCombatPlayer([map+0xED]) -> GetNextUnit -> select
0041BED8  <remote path> PlaySample + InitMsg(0x20021001) + vcall [map_vmt+0x68]
```
**`[TPlayerCommunicationControl.GetPlayers(pid)+8] == 1` means "that player is
played on another machine".** On an observer every combat player is remote, so
NewTurn always takes 0x41BED8 and **`SetSeatedCombatPlayer` is never called** ⇒
`SetSeatedPlayer` never runs ⇒ no viewing player ⇒ the whole site map is black.
`SetSeatedCombatPlayer` @0x41BAB8: `[map+0xEC]=idx`; idx==0xFF → vcall
`[map_vmt+0xF8]`(SetSeatedPlayer, -1); else resolves
`[map+0xE4]→[+0xC]→[+0x38]` = TCombatPlayerList → GetPlayers(idx) →
`dl=[combatplayer+8]` (AoW player id) → **vcall `[map_vmt+0xF8]` =
`TAbstractAoWHSMap.SetSeatedPlayer`** (AoWTCPCK iat 0x46E5F8), then fires
`TriggerNotifyEvents([map+0xF8])` → `TAoWCombatMapControl.SeatedPlayerChanged`
(0x436D54) to refresh the view.

**✅ FIX APPLIED 2026-08-11 — `patch scripts/build_mp_site_observer_vision.py`
(backup AoWTCPCK.dll.bak_sitevision; --apply/--revert). AWAITING MP TEST.**
User's preference: observers see EXACTLY the explorer's vision (not fog-off).
Implementation: hook the 5-byte `mov eax,0x41BFA0` at **0x41BED8** (the entry of
the remote/observer branch, which BOTH `jne` @0x41BD1A and `je` @0x41BD54 reach)
→ `call cave @0x438500` (185 B; **next free AoWTCPCK cave now 0x4385C0**).
Cave (ebp still = NewTurn's frame, so `[ebp-4]` = the combat map):
 - local player id = `[[[0x46E8D4]]+0xA5]`;
 - walk `[map+0xE0]` TTacticalCombatPlayerList via GetCount(0x430BC0) /
   GetPlayers(0x430BF0, dl=idx), reading each `[combatplayer+8]` = AoW id;
 - if any equals the local id → **we are a participant, change nothing**
   (normal PvP untouched);
 - else remember the first NON-neutral (id != 0) index = the explorer, and if
   it differs from `[map+0xEC]` call `SetSeatedCombatPlayer` → SetSeatedPlayer.
 - restores eax = 0x41BFA0 (PIC) and returns into the original
   `call PlaySample` at 0x41BEDD.
PIC throughout (call/pop delta) because **AoWTCPCK always rebases**; the .reloc
HIGHLOW for the displaced imm32 at VA 0x41BED9 (file 0x83AFA) is neutralized
3→0. Verified: cave disassembles as intended, delta math
(0x4385B2-0x1C612=0x41BFA0) correct, game launches (module loads, relocs fine).

### ✅ OBSERVER VISION CONFIRMED WORKING 2026-08-11 (user: "observer can see the
same as explorer"). Next symptom reported: **"Error - TCAI: Error during Create
Unit List"**.

### "Error - TCAI: Error during Create Unit List" — LOCATED
`AoWTC.TCAI.EvalBattle` @0x418170. `[cai+0x1C]` is a phase counter (0..5)
dispatched through a jump table @0x4181DB. **Phase 0 = "Create Unit List"**, a
Delphi try/except spanning **0x4181F8..0x418ABE**; handler @0x418AC3 →
`MessageBoxA("Error - TCAI", "Error during Create Unit List")` @0x418AD6 →
`@DoneExcept` → `jmp 0x41AFAA` (execution continues, so it is a caught
exception, not a hard crash). The block frees/clears the AI's lists
(`[cai+8]/[+0xC]/[+0x10]/[+0x14]/[+0x18]`), then rebuilds from
`[[0x46C064]+0xE4]` (TCombat) → `[+0xC]` (TCombatData) → `[+0x38]`
(TCombatPlayerList) / `TCombatData.GetCount`. A nil anywhere in that chain
would throw here. EvalBattle is gated at 0x4181A4 on `[combatmap+0xA4]` via the
token manager (`[AoWHSMap+0x23C]` vcall +0x14), so it only runs on the machine
that owns the AI player.
**★ PRIME SUSPECT — the always-explored stub is called INSIDE this block:**
```
004183AA mov   edx,[0x46C064]        ; combat map
004183B0 movsx edx,byte [edx+0xA5]   ; the SEATED player id
004183B7 call  0x40287C              ; GetExplored(field, player)  <-- STUBBED
004183BC test  al,al / je ...        ; sets [ebp-0x33]
```
It reads **`[combatmap+0xA5]`** — the very field `SetSeatedPlayer` writes, i.e.
the field the new observer-vision patch changes. A/B toggle built:
**`patch scripts/toggle_getexplored_stub.py`** (`--restore` = vanilla thunk,
`--stub` = mod default, no args = status; backup
AoWTCPCK.dll.bak_getexplored). Run `--restore`, retest MP site combat: if the
TCAI error disappears, the stub is the cause and "defenders act immediately"
must be re-implemented narrowly (e.g. only for the defending player's own
units) instead of globally lying about exploration to all of AoWTCPCK.

### ✅ THE REAL BUG: the always-1 stub was MASKING A NIL-FIELD DEREF
A/B result (user, 2026-08-11): with the thunk **restored to vanilla** the TCAI
"Create Unit List" error DISAPPEARED and SP was fine, but MP then threw
**"Error - TCMoveToken: Error during Token"** on the OBSERVER only — explorer
played on, observer's combat froze. Handler = `CombatTE.TCombatMoveTE.DefaultMove`
try/except, message @0x408F5D/0x408F62 (strings 'Error - TCMoveToken' @0x408F84,
'Error during Token' @0x409030).
Cause, at **0x408DBF..0x408DE5** inside DefaultMove:
```
mov  eax,[0x469420]/[eax]/[eax+0x10]      ; the combat THSMap container
call HSEngine.TMapContainer.GetField      ; -> eax = dest field, CAN BE NIL
mov  edx,[0x469420]/[edx]
movsx edx,byte [edx+0xA5]                 ; seated (viewing) player
call 0x40287C                             ; GetExplored(field, player)
test al,al / je skip-the-move-visual
```
The real `TAoWMapField.GetExplored` @0x55771BF4 does `mov edx,[eax+0x18]`
**immediately**, so a NIL field access-violates → caught → "Error during Token"
→ that machine's token stalls. **The always-1 stub never touched eax, which is
precisely why it hid this for years.** (⚠ general lesson: that stub silently
null-guards all 10 AoWTCPCK GetExplored call sites.)
**FIX APPLIED: `patch scripts/build_getexplored_nilguard.py`** (backup
AoWTCPCK.dll.bak_nilguard; --apply/--revert). Thunk 0x40287C → `jmp cave
@0x4385C0` (27 B; **next free AoWTCPCK cave 0x438620**):
`test eax,eax / jz -> xor eax,eax; ret` else PIC tail-call the real import
(`call/pop ecx; sub static; add &IAT 0x46E630; jmp [ecx]`). Only ecx is
clobbered and the real routine overwrites ecx itself, so all 10 call sites are
unaffected. Reloc at THUNK+2 neutralised 3→0. Verified disassembly + launch.
⚠ This restores vanilla "defenders wait until seen" — the attack-immediately
behaviour must be re-added narrowly later (per defending unit), NOT by lying
about exploration globally.
Helper kept: `patch scripts/toggle_getexplored_stub.py` (--stub/--restore/status).

### ✅ MP CLEAN 2026-08-11 (user: "that fixed it, no errors in mp now")
Follow-up round applied, all AWAITING TEST:
1. **Observer seat → VIEW ONLY.** The observer could click the explorer's units
   ("cannot create remote"), press end-turn, and saw the explorer's gold/mana —
   because `SetSeatedCombatPlayer` sets `[map+0xEC]` (the combat SEAT, which the
   UI reads as "you are playing this player") as well as calling SetSeatedPlayer
   (`[map+0xA5]`, the VIEWING player used by GetExplored/fog) + the
   SeatedPlayerChanged redraw. Cave now writes **`mov byte [esi+0xEC],0xFF`**
   right after the call: keep vision + redraw, drop the seat. Cave grew to 192 B
   and now exactly fills 0x438500-0x4385C0. The script gained a "hook already
   installed → rewrite the cave in place" mode (⚠ do NOT --revert it now: its
   backup predates the nil-guard).
2. **Defenders engage immediately, re-added NARROWLY** —
   `patch scripts/build_defenders_engage_immediately.py` (backup
   AoWTCPCK.dll.bak_engage). One 5-byte patch at **0x4183B7**:
   `call GetExplored` → `mov al,1; nop*3`, i.e. only TCAI.EvalBattle's
   "can the human see this tile?" test (result drives `[ebp-0x33]` =
   "we've been spotted"). All other 9 GetExplored call sites keep real
   semantics + the nil guard. Replaces the old global thunk stub.

3. **Observer camera now follows the DEFENDERS too** (user 2026-08-11: opening
   centre is a non-issue since it re-centres on the first move, but the camera
   only followed the explorer's units). The move-visual/centre gate in
   `TCombatMoveTE.DefaultMove` (and the melee/touch/ranged twins) is
   `GetExplored(destfield, viewingPlayer)`, so defender moves through tiles the
   explorer has not revealed were skipped. **Observer clause added to the
   nil-guard cave** (now 54 B @0x4385C0; next free 0x438620): after computing
   the real answer, if `[[0x46C064]+0xEC] == 0xFF` (no combat seat ⇒ this
   machine is an observer) return 1. ⚠ This does NOT reveal the map: fog is
   drawn by AoWEPACK's own `DrawFog`, which calls GetExplored internally and
   never goes through the AoWTCPCK thunk — only AoWTCPCK's own logic sees it,
   and on an observer that is just the camera/visual gate (they cannot move,
   select, or run the AI). Both scripts gained "already installed → rewrite the
   cave in place" modes.
   ⚠ `toggle_getexplored_stub.py` now reports UNKNOWN (the thunk holds our
   `jmp cave`) — that is expected; use build_getexplored_nilguard.py --revert.

### STILL OPEN
- Verify the gold/mana leak is gone with the seat change (it may have been
  driven by `[map+0xEC]`).

### The participant's AVs (SOLVED — was the nil deref above)
The old "receiver" @0x41BD50 is inside **`TAoWCombatMap.NewTurn`
(0x41BB30-0x41BFB8)** — which is exactly why the exploring player "can't move".
Layout: `[map+0xED]` = current combat player, `[map+0xE0]` =
TTacticalCombatPlayerList, `[map+0xE4]` = another list, `[map+0xA4]` = a player
byte used for `TTokenExecuter.ActivateTC`. **`[TTacticalCombatPlayer+8]`** is
the discriminator: `cmp byte [eax+8],0 / jne` @0x41BBFC → the ==0 path shows a
translated message via vcall `[map_vmt+0x110]` (independent/neutral turn — an
exploration site's defender is player **0**, cf. `Search` hardcoding
`[log+0x1A]=0`); `cmp byte [eax+8],1 / je 0x41BED8` @0x41BD50 → PlaySample +
`Engine.InitMsg(0x20021001)` + vcall `[map_vmt+0x68]` (the old notes' AV
vector, TStructureTE ctor); the fall-through is the "I control this player"
path → `SetSeatedCombatPlayer([map+0xED])` → `GetNextUnit` → select a unit.
NEXT: instrument/step `NewTurn` in an MP site combat to see which branch each
machine takes and where the AV lands.

## WHERE THAT LEAVES THE SEARCH (2026-08-11)
Static analysis now says the dialog **should** already appear in MP:
Search always requests it (mod patch, step 2) → the handler always shows it
(step 5, gate is dead). Also `TExplorationSite.ExecuteTE` @0x557C1D28
(`cmp [te+0x18],0` → `dl=[te+0x20]` → vcall `[site_vmt+0x1FC]` = ExecuteSearch)
proves the chosen type IS transmitted and replayed on every client.
So the MP divergence must be UPSTREAM of the dialog. Remaining candidates:
 a) in MP the click never reaches `Search` (different handler; site entered by
    army move → `TArmyCombatMoveTE` instead of `TIWindow.MainBtnClick`);
 b) no listener attached to the notify list `[map+0x1D0]` in MP, so the cl=1
    immediate raise is dropped and something else resolves the combat;
 c) the user's MP observation predates the `xor eax,eax` baseline patch, i.e.
    current builds may already prompt in MP — **cheapest thing to check first,
    just try it.**

## PROPOSED NEXT STEP
Do NOT blind-patch again. 1) Have the user simply retest MP as-is (candidate c).
2) If it still auto-resolves, build an INSTRUMENTED AoWEPACK/AoWx that appends a
line to a log file at: `Search` entry, the branch taken at 0x557C1EA4, the
`TriggerExecuteEventLog` cl value, `TheMapExecuteEventLog` class dispatch, and
0x439AEC — then one 2-PC session pinpoints the divergence. Only then change
behaviour: make `Search` mirror `TArmyCombatMoveTE.SetupCombat` (seated-player
gate, real defender id in `[log+0x1A]` instead of hardcoded 0, and **cl=0**
queued raise) and test observers.
Related: [[lan-desync-investigation]] (MP sync rules), [[bxl-reference]].


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- ✅ [exploration-site-fix.md](exploration-site-fix.md) — **MP TACTICAL COMBAT AT EXPLORATION SITES WORKS (user-confirmed 8/11, "everything works perfectly")** — the long-shelved feature. Dialog + observer vision through the explorer (seat cleared → no control/gold leak) + observer camera follows both sides + defenders engage immediately (narrow 5-byte AI patch). ★ Root cause of years of crashes: the always-1 `GetExplored` thunk stub was **masking a nil-field deref**; replaced by a nil-guard wrapper. 3 scripts, revert via #2 not #1.
