---
name: lan-desync-investigation
description: "LAN out-of-sync SOLVED 8/9: FIX #8 movedraw (NOP the discarded per-move synced Random @0x557478ED) + fixes #1 noanim, #2 aiowner, #4 joindest. USER-CONFIRMED WORKING (recruit-moles repro, state-consistent). All diag reverted. Failed approaches #3/#5/#5b/#6/#7 reverted."
metadata:
  node_type: memory
  type: project
  originSessionId: 8f3078ba-61f6-4cbb-b65b-212a6b0b5d73
  modified: 2026-09-01T01:16:33.646Z
---

**8/31 ⚠→✅ FIX #1 "noanim" v2 — THE "TELEPORTING AI MOVES" BUG (user-bisected 401 vs 402).** v1's gate `byte [map+0x239]==2` was believed network-only but ALSO HOLDS IN SINGLE PLAYER → since 1.37.402 every AI strategic move was instant/non-animated in SP (user report 8/31: "AI units teleport"; confirmed absent in 401, present in 402). v2 (`patch scripts/build_desync_fix_noanim2.py`, hot-swapped the cave @0x55812000, now 151B; hook unchanged; new backup .bak_noanim = pre-v2-with-current-patches, the OLD pre-fix backup lives in backup/): inserts a scan of comm records idx 0..11 — **no player with [rec+8]==1 (Remote) → vanilla MoveVisible (SP/hotseat animate again)**; any Remote → v1 behavior (AI moves instant in LAN, the OOS protection — divergence needs a second machine). [map+0x239]==2 kept as pre-filter. SP animation retest ✅ (user 8/31). **THEN FULLY REVERTED same day (user call): fix #1 noanim is OFF entirely — vanilla MoveVisible restored, AI moves animate in SP AND MP.** Rationale: fix #8 removed the per-move synced Random (the actual OOS mechanism), so animation timing can no longer shift the seed; #1 was a never-retested belt-and-braces layer. ⚠ RESIDUAL RISK untested: timing skew still changes WHEN each machine's AI pump mints follow-up tokens (counter-collision drop = SILENT state divergence, not an OOS dialog). **LAN TEST REQUIRED: recruit-a-neutral(moles) repro w/ AI active + multi-turn state-consistency check. If divergence returns → re-apply build_desync_fix_noanim2.py --apply (v2: SP animates, LAN protected).**

## ⭐ 8/31 THE TWO-RNG MODEL (found auditing Mind Decay — applies to ALL future OOS work)
There are **two generators sharing one seed variable**:
* `AoWE.TAoWHSMap.Random` @0x5577827C = the **synced** one. Its body (verified):
  `mov eax,[System.RandSeed]; mov edx,[map+0x230]; mov [eax],edx` → draw via
  `@RandInt` → `mov [map+0x230],RandSeed` (writes back @0x557782AD). So
  **`[map+0x230]` is the synced store and Delphi's `RandSeed` is only the
  carrier**; every synced draw RELOADS RandSeed first, so unsynced draws can
  never corrupt the synced stream.
* Bare **`VCL30!System.@RandInt`** (IAT AoWEPACK 0x558FB6DC / TCPCK 0x46DBF4).
  `AoWE.HitRole` @0x55725D98 is the combat roll: clamps a 10..90 chance then
  `@RandInt(100)`. **It advances RandSeed but never writes back to [map+0x230].**

⇒ **Combat rolls are invisible to the sync check** (TSyncTE compares
`[map+0x230]`), **but they are only reproducible across machines if both
consume the SAME NUMBER of `@RandInt` draws between two synced draws.** A
conditional/asymmetric `@RandInt` therefore causes *silent* divergence
(different to-hit/resist results → different deaths → later synced-draw skew →
OOS dialog), which is the same bug class as FIX #8 one layer down.
`HitRole` callers: TStrikeCA.Generate (×2), TTouchAbility.CombatTouchRole (×2),
TTurnUndeadAbility.CreateTurnUndeadCA, ExecuteLifeMasteryFearRole,
ExecuteDeathMasteryCurseRole, **ExecuteResistanceRole @0x55781B48**,
TBurningAbility.NewCombatTurn, **TMindDecay/TSlow/TEntangle.CreateCA**,
TFastCombatTerrorCA/TTacticalCombatTerrorCA.Generate.

### Mind Decay audit (user asked 8/31; static only, no playtest)
`CombatSpells.TMindDecay` = **mind control**. `TMindDecayCA.Execute`
@0x557F8428 (CA fields: +0xC caster id, +0xD target id, **+0x14 = outcome
flag**, +0x18 spell): base `TExclusiveCombatSpellCA.Execute` → if +0x14 → XP to
caster (`GetExperience`/`SetExperience` = TCombatUnit VMT +0x98/+0x9C) → 3×
`TCommandAbility.ResetCommandedUnits` + 3× `.Uncommand` over `CommandAbilityIDs`
→ `GetAbility(0x83).Expand([target+0x4C])` → **`SetCombatPlayer`** (VMT+0x68)
= the side switch. AoWTCPCK's only reference (`TCAbRangedTE.Execute+0x1257`,
classref IAT 0x46EF60) is cosmetic: if the CA landed, `SetAction(unit,4)`.
* **Execute consumes ZERO draws — synced or unsynced** (walked ~46 functions
  incl. the resolved vcall targets and the modded SetExperience cave 0x5580C200).
  No locality/visibility gate, no `[map+0xA5]` read anywhere in the chain.
  So Mind Decay's *execution* cannot shift either seed.
* The outcome is rolled once in **`TMindDecay.CreateCA` @0x557F85DC**, and that
  `HitRole` call sits behind **five gates, four of which dereference the
  target's STRATEGIC unit `[combatunit+0x4C]`** — unique among combat spells
  (TSlow/TEntangle gate on ONE check via the combat unit's own virtuals):
  `IsClass(target,TCombatUnit)` → `u.GetUnitType()!=2` → `u.GetRace()!=0x0B` →
  `!u.GetAbilityEnabled(0x81)` → `!IsClass(u,TLeader)` (classref 0x557121F8).
  So Mind Decay has by far the widest surface for a one-sided `@RandInt`.
* ⚠ **All of that gate is byte-identical to vanilla AoWEPACK.dpl** — so if Mind
  Decay really does desync, it is a VANILLA defect, not something we introduced.
  Only 2 mod deltas exist in the whole spell, both deterministic:
  `Execute@0x557F8473` (vanilla `GetLevel&0xFF` → cave 0x5580F160 = XP by
  level+rank; returns 1 when `[target+0x1C]==[caster+0x1C]`; reads the caller's
  `[esp+4]` for the caster — correct for the `53 56 57 51` prologue but
  fragile) and `Create@0x557F8598` (`[spell+0x39]` 0xFF→0x0C).
  Cave 0x5580F160 → shared helper **0x5580F060**, the same rank-bonus cave
  hooked into `TCombatObject.DoDamage`/`TDamageEffectCA.Execute` that caused the
  wall crash — [[keeper2-armycombatmovete-crash]]'s IsClass guard (cave
  0x55810E80) protects this path too.
* **Our OOS fixes do NOT cover this.** FIX #8 was strategic-layer movement;
  nothing we shipped touches combat-spell CA creation. Assume still exposed.
* 🐞 Separate CRASH risk (not OOS): `[target+0x4C]` is dereferenced at
  0x557F862C with only an `IsClass(TCombatUnit)` guard, **no nil check** — a
  combat unit with no strategic unit would AV.
**Ability ids in that gate (resolved 8/31 by the inline-Create scan of
[[ability-id-map]] — `c7 4x 0c <id32>`):**
`0x81 = PassiveAb.TAnimatedAbility` ("Animated" — mind control fails on
mindless constructs/undead), `0x82 = TCombatResurrectedAbility` (matches the
vestigial-HeroSlaying note), **`0x83 = PassiveAb.TDecayAbility`** = the status
Execute applies, `0x84 = TSlowEnchantmentAbility` (what TSlow.CreateCA checks).
⚠ Correction to the first pass: **Animated is a static unit trait, so the "our
ability mods might make the gate disagree" lead is WEAK.** THero VMT+0x148 is
redirected to our cave 0x55812760 (`build_item_healing_daily.py`) but that is a
clean pass-through for every id except 0x2F — NOT implicated.

### 🔨 PATCH APPLIED 8/31 — `patch scripts/build_minddecay_oos.py`
(backup `AoWEPACK.dll.bak_minddecayoos`; dry-run/--apply/--revert surgical.)
Makes the draw **unconditional** and gates only the STORE:
gates → `eligible` 0/1 (no early exit) → ALWAYS
`eax = [spell+0x34] − target.GetResistance(); call HitRole` → store to
`[ca+0x14]` only if eligible (else left 0, as vanilla).
* Safe to hoist because the roll's inputs never touch `[target+0x4C]`:
  resistance comes from the target's own **VMT+0x74** (a TCombatObject
  base-class slot — TCombatUnit/TCombatWall/TCombatObject all implement it)
  and `[spell+0x34]` is a constant from TMindDecay.Create.
* Eligible targets: identical outcome AND identical draw order to vanilla.
  Ineligible: one extra `@RandInt` consumed+discarded, **uniformly on every
  machine** ⇒ determinism preserved exactly as FIX #8 preserved it.
* Also adds the **nil check vanilla lacks** on `[target+0x4C]` (fixes the AV).
* Hook 5 B @0x557F861B (also the `je` target from 0x557F8613) → cave
  **0x55815120** (174 B, PIC: `call $+5/pop/sub` delta kept in a stack slot,
  both classrefs as `[delta+prefVA]`); 3 orphan bytes NOP'd.
  ⚠ **The displaced `mov edx,[0x55715A54]` carries a reloc on its imm32 at
  0x557F861F, INSIDE the 5-byte jmp** — script neutralises it (type 3→0) on
  apply and restores it on revert ([[patching-over-relocs-gotcha]]).
  Revert verified byte-identical to the backup; re-apply reproduces identical
  bytes. **Next free AoWEPACK cave is now 0x558151D0.**
* ⚠ **HONEST SCOPE — untested in MP.** This removes the one concrete,
  mechanically-verifiable RNG asymmetry unique to Mind Decay. The gates read
  synced state, so on two correctly-synced machines they *should* already
  agree — i.e. this stops a divergence CASCADING through every later combat
  roll, but is not a proven root-cause fix. It cannot make things worse.

**8/31 SYNCED-RNG FULL AUDIT (post-noanim-removal hardening check) — ALL CLEAN.** Method: enumerate every caller of TAoWHSMap.Random 0x5577827C (E8 scan), label via the export table, check (a) discarded-result pattern (#8's class: eax overwritten immediately) and (b) draws inside visibility-gated branches. Results: **AoWEPACK 114 sites** — all turn/token/AI-deterministic contexts (AIPAs/AI run on ALL machines identically — that is the engine sync model; Global players' tokens are LOCALLY generated+executed per machine, not broadcast), zero discarded draws besides the fixed #8, zero locality-gated draws (SmokeCloud/PoisonCloud/Fire Update* are turn-driven, not frame-driven). **AoWx.exe** imports only TRndTacHsm.RandomMap (combat setup, token ctx). **AoWTCPCK 74 sites** (thunk @0x40298C, IAT 0x46E5A8) — CombatTE executors + MapFieldMsgProc handlers (all-machine); the 4 GetExplored visual gates (0x408DDE/0x409129/0x409D99/0x40B4A6) skip ONLY camera/visual calls — no gated draws. ⇒ post-#8 RNG discipline is solid; the ONLY remaining theoretical OOS surface is TOKEN ORDERING under timing skew (animation/frame-rate) — untestable statically. **Definitive future fix if a desync ever reappears: decouple AI move-token completion (instant state on all machines) from a detached cosmetic sprite walk** — the machinery (TMoveTE state machine, SetupNextMove, MoveVisible, TArmyHS MoveFirst/GetMoveStatus) is half-RE'd in the noanim notes below. ⚠ Correction to [[ai-explores-sites]]: its "AIPA runs on one machine" MP reasoning is wrong (they run everywhere); the feature is still MP-safe — deterministic state-gated mints produce identical local tokens on every machine.

**8/9 ✅✅ SOLVED — FIX #8 "movedraw" USER-CONFIRMED WORKING ("holy shit it
worked"), state-consistent. ALL DIAGNOSTICS REVERTED, clean build shipped.**
FINAL STATE (byte-verified): fix #8 @0x557478ED = 90 90 90 90 90 (Random draw
NOP'd); fixes #1 noanim (cave 0x55812000), #2 aiowner (A 0x557428B2/B
0x557427D1, cave 0x55812100), #4 joindest (0x5578FC24, cave 0x55812200) all
intact; diag v6 (AoWEPACK: H1 Random..H13 ExecMv + H3 reloc restored) and
diag v7 (Network.dpl H1 send/H2 recv) FULLY REVERTED; failed approaches
#3 remoteowner / #5 noresume / #5b clicklock / #6 noautoplot / #7 burstdefer
all reverted, shared cave 0x55812280 zeroed, GetBusy call @0x5574A347 vanilla.
Backups: .bak_movedraw (pre-fix-8). REMAINING SITES if ever needed: the two
DIAG scripts (build_desync_diag6.py, build_desync_diag7_net.py) + enhanced
re_tools (desync_dump.py NET ring + CRE decode, tc_dump.py exec-pending+
counters, hook_probe.py) are kept for future OOS work.
THE BUG IN ONE LINE: TMoveTE.Execute drew a synced Random(0xFFFFF) once per
move token's first execute and DISCARDED the result (@0x557478ED, eax
overwritten @0x557478F2) — a pure seed-advance. When a human move onto a
neutral (recruit) executed at machine-divergent stream positions vs the
concurrent AI token burst, that lone draw advanced one machine's seed and
not the other's at the sync-compare point → OOS. Removing it (uniformly on
both, identical DLL) makes move execution consume ZERO synced draws →
determinism preserved, timing no longer observable. 15 repros, transport
RE (Network.dpl), CRE3/CRE5 caller-tracing, and NET send/recv rings led here.

**8/9 EARLIER: REPRO #15 -> FIX #8 "movedraw" (approach C) APPLIED, awaited
STATE-CONSISTENCY test.**
Repro #15 (clean signature, both machines): creator B (p1 Local) CRE5
SelectPath+0x73 -> CREA (44,10,2) -> **TMoveTE.Execute+0x36 draws Random,
seed F3480932 -> BEB5F5FB** -> next SYNC BEB5F5FB -> BOOM. Peer A (p1 Remote)
never executes (44,10,2), seed STUCK F3480932 -> BOOM. **The move's ONLY
synced side-effect is the discarded Random @0x557478ED** (H1 logs it as
caller "TMoveTE.Execute+0x36"; result overwritten by mov eax,[ebx+14h] @
0x557478F2). tc_dump (enhanced, exec PENDING list [exec+0x10] + counters):
both pending lists EMPTY at freeze; exec counts 424(B) vs 425(A) diverged by
1; the (44,10,2) move ABSENT from A entirely (not pending, not executed);
post-BOOM both machines' Global TCs held DIFFERENT freshly-generated
counter=-1 AI moves (p2 (11,70,0)+p4 (75,81,0) on one; p4 (76,82,0) on
other) = post-divergence drift, inconclusive re drop-vs-defer.
**AMBIGUITY:** static evidence (exec-count skew, move absent on A) hints the
move is DROPPED on the peer (counter overtaken by concurrent AI tokens =
real divergence -> C would MASK it); BUT user reports moves DO eventually
execute on the peer, and the single-discarded-draw signature is textbook C.
Inconclusive by static analysis -> resolve EMPIRICALLY.
**FIX #8** `build_desync_fix_movedraw.py` (backup .bak_movedraw): NOP the
5-byte `call Random` @0x557478ED (E88A090300 -> 9090909090). Move tokens
then consume ZERO synced draws; RNG stream advances one-fewer per move
UNIFORMLY on both (identical DLL) -> determinism preserved, recruit move's
timing no longer perturbs the seed. **CRITICAL TEST = STATE CONSISTENCY:**
after a recruit, BOTH clients must agree on army/mole positions and play on
cleanly. If they diverge silently (no dialog but desynced state) -> C masked
a real drop -> REVERT (--revert) and go to approach (B): serialize the human
move vs concurrent AI token generation (gate AI token gen during human move
commit/broadcast; levers: ActivateNextTC round-robin counter assignment,
CaptureTokenCycles lock window, or the AI move-gen pump). STATE: fixes
#1+#2+#4+#8 + diag v6/v7 (record-only) applied; #3/#5/#5b/#6/#7 reverted.

**8/9 EARLIER: FIX #7 REVERTED (approach A DEAD) -> tc_dump enhanced.**
Repro #15: fix #7 made clicking UNBEARABLE (every move refused, needs fast
repeated clicks) AND still OOS. Lesson: **the AI capture window bit
[aiexec+0x18]&0x02 is set ~CONTINUOUSLY in network games** (CaptureTokenCycles
fires back-to-back every frame regardless of whose turn) — so it is NOT a
"burst vs quiet" discriminator, and refusing on it = refuse ~all moves.
**Approach A (defer/refuse the human move) is DEAD: there is no quiet window
to defer into.** Fix #7 reverted (clicking normal again). New model of why
normal play still works: capture windows cycle continuously but usually
carry NO tokens (empty); the recruit specifically makes the neutral player's
AI PRODUCE tokens that then share counter space with the human's Local move
-> per-machine-independent counter assignment collides -> divergence. So the
real discriminator is "AI is PRODUCING tokens" (pending Global tokens), not
"capture window open".
**DECISION PENDING C vs B** hinges on: does the peer EVENTUALLY execute the
one-sided move (state converges -> option C = NOP the discarded Random
@0x557478ED is SAFE & is a 1-instruction fix) or is it dropped/collided
(real divergence -> option B = gate the neutral-AI wake). Instances freeze
at the sync check so the RNG ring can't show post-BOOM execution. **ANSWER
VIA tc_dump (enhanced, tool-only, no binary change):** now also dumps the
executer PENDING list [exec+0x10] (received-but-unexecuted tokens) with each
event's counter=[te+0xC], plus counters on TC pending events. If the peer's
[exec+0x10] holds the (44,10,2) move at freeze -> converges -> C safe. If
absent (and executed-count past its counter) -> dropped -> need B. Counter
values also expose collisions (same counter, different token across
machines). STATE: fixes #1+#2+#4 applied; #3/#5/#5b/#6/#7 reverted; diag v6
(AoWEPACK) + diag v7 (Network.dpl) applied. NEXT: repro #15 recruit, freeze,
run tc_dump on BOTH -> read exec PENDING lists -> pick C or B.

**8/9 EARLIER: FIX #7 "burstdefer" APPLIED (approach A) - since REVERTED.**
User picked approach (A) defer. **Precise "AI burst active" signal proven:
CaptureTokenCycles @0x5573466C sets bit 0x02 of [aiexec+0x18] (+Locks
executer); TokenCyclesCaptured @0x557346FC clears it (+Unlocks). Set ONLY
by the AI capture path = strictly narrower than the raw executer lock that
broke fix #5b (that lock also held during ordinary single-token exec +
combat/UI callbacks). aiexec = [map+0x128] (verified NewFrame+0x40
`mov eax,[ebx+0x128]; call Process`; Process gated [map+0x11C]==0 &&
[map+0x118]!=2). CaptureTokenCycles masks @0x557346F8/0x5573477C both =0x02.**
**FIX #7** `build_desync_fix_burstdefer.py` (backup .bak_burstdefer, cave
107B @0x55812280): replaces MoveArmyEx's `call TPlayer.GetBusy`
@0x5574A347 (runs only for UI callers w/o busy-skip flag [ebp+8]; MoveArmy
wrapper pushes 0) with cave: GetBusy; if not busy AND network AND
[[map+0x128]+0x18]&2 (capture window open) AND owner comm==Local(0) -> al=1
(MoveArmyEx's existing no-move path). Global/Remote owners never gated (AI
burst runs normally); esi=armyHS, owner via [[esi+0x1C]+0x12] + GetPlayers.
UX: a move-onto-neutral clicked mid-burst does nothing; re-click once the
moles/AI settle. Determinism preserved (move enters a quiet stream,
counter-aligns both machines). STATE: fixes #1+#2+#4+#7 + diag v6 (AoWEPACK)
+ diag v7 (Network.dpl) applied; #3/#5/#5b/#6 reverted. TEST: recruit repro
- if the click is refused mid-burst then succeeds when settled AND no OOS x2
-> WIN -> revert diag6 (build_desync_diag6.py --revert) + diag7
(build_desync_diag7_net.py --revert), final clean retest. If the click
still goes through mid-burst and OOS (landed in a between-window gap):
broaden gate from bit 0x02 to [aiexec+0x18]&1 (AI active) or add
pending-Global-TC check. If UX of manual re-click is bad: upgrade to
auto-queue (hold move, auto-issue when bit clears).

**8/9 EARLIER: REPRO #14 + USER REPRO STEPS = ROOT CAUSE NAILED, FIX #6
REVERTED (wrong target).**
**User's exact repro:** click own party; click moles once = movement-preview
arrow (NO oos); click moles a SECOND time = as the recruit/attack UI opens,
OOS fires BEFORE any selection. So the diverging token is the player's own
DELIBERATE move onto the neutral moles (two-click flow: MouseDownEvent ->
SelectPath+0x73 -> ExecuteMove -> MoveArmy), NOT a stale auto-path. Fix #6
(killed Update auto-preview) was aimed wrong -> REVERTED. TMoveTE.Execute
@0x557478BC: on the state 0->1 transition (Validate vcall+0x58 true) it
calls InitializeMove (vcall+0x5C) then **draws a synced Random(0xFFFFF)
@0x557478ED whose RESULT IS DISCARDED** (eax overwritten by path-count at
+0x557478F2) -- a pure seed-advancing draw, once per move token's first
execute.
**Repro #14 ring (decisive):** creator B (p1 Local) window CAPT617 ->
CRE5/CRE3/CREA (44,10,2) -> RELS617 -> executes the move @0x557478F2 (seed
250D4062 -> A184C9EB) -> next SYNC A184C9EB -> BOOM. Peer A (p1 Remote):
executes windows 617 AND 622 with seed STUCK at 250D4062 -- **A never
executes the move** -- sync-compares its 250D4062 vs B's advanced A184C9EB
-> BOOM. **Both machines show IDENTICAL CAPT/RELS window boundaries
(617,622,626)** yet the move occupies a counter slot on B that A fills with
a different (AI-burst) token: genuine TOKEN-STREAM divergence -- the human
move injected mid-AI-burst gets a counter that the peer's concurrent
locally-simulated Global-AI tokens have already claimed/overtaken. NET ring
CONFIRMS transport OK (B p1 batch=3 sent, A RECVs p1) -- so it is ordering,
not delivery. This is the ORIGINAL v2 "token-ordering divergence" with its
trigger finally proven: **human move onto a neutral stack while the AI
capture-burst (woken by approaching/recruiting) is churning Global tokens
on both machines asynchronously.**
**Why normal LAN play is fine:** quiet stream => human move counter lands
cleanly on both; only the recruit/neutral-contact burst races it.
**FIX FORK (user to choose - genuine tradeoff):**
(A) DEFER the human move-onto-neutral until the token executer/AI burst
drains (queue + auto-retry), so its counter lands in a quiet slice. Robust,
invisible when it works; move happens a beat later. (Proper version of the
failed fix #5b, which wrongly refused on executer-lock and broke clicks.)
(B) GATE/serialize the neutral-AI wake so AI tokens don't churn during the
human's recruit interaction (original "fix direction A" from 8/7). Smallest
conceptual change to the trigger; needs the recruit->AI-wake path.
(C) NOP the discarded Random @0x557478ED so a move consumes ZERO synced
draws -> timing can't shift the seed. REJECTED as primary: masks real
state divergence (A genuinely never executed the move; suppressing the
draw hides the desync detector, not the desync) -- the "hacky option C"
we flagged 8/7. Only viable if proven A executes the move later (state
converges) -- unverified.
STATE: fixes #1+#2+#4 applied; #3/#5/#5b/#6 reverted; diag v6 (AoWEPACK) +
diag v7 (Network.dpl) still applied. TMoveTE.Execute VMT: +0x54 ProcessMove
+0x58 Validate +0x5C InitializeMove +0x60 FinishMove +0x68/6C move dispatch.

**8/9 EARLIER: REPRO #13 (NET ring) -> DELIVERY EXONERATED, ORDER INVERSION
PROVEN -> FIX #6 "noautoplot" APPLIED (since REVERTED).**
NET ring: B's p1 batch=3 (Sync+molemove+PassToken, NET#777) was SENT and A
PREFETCHED an identical p1 batch=3 (NET#778) — **transport works**. The OOS
is ORDER INVERSION at the same stream count: at seed C9876796 A executed
the negotiate token + its (75,81,0) move while B executed the mole move
(B ran nego later @ADBE5DEF post-BOOM). Stream positions are per-machine
COUNTS (PrefetchTokenEvent: counter=[exec+0x18]+pending; remote accepts
when counter==its own count) — they self-align ONLY when both machines
interleave identical token counts; a UI move injected during the recruit
burst (Global tokens flowing) resolves differently per side. Quiet-time
clicks align trivially = why normal LAN play works.
**FIX #6** `build_desync_fix_noautoplot.py` (backup .bak_noautoplot, cave
57B @0x55812280): hook TSelectedArmy.Update auto-plot block entry
@0x557936D2 (10B F6431401 0F84E7000000; exit 0x557937C3; resume
0x557936DC): network games skip the ENTIRE auto-plot loop (dest-branch AND
lingering-path-branch — fix #5 failed by gating only the first). The stale
path never arms -> clicking the recruited army just selects it. Deliberate
moves unaffected (two-click flow = MouseDownEvent -> SelectPath's own
plot/confirm, independent of Update). MP-only visual cost: selected army's
stored-dest path preview doesn't auto-appear. STATE: fixes #1+#2+#4+#6 +
diag v6 (AoWEPACK) + diag v7 (Network.dpl) applied; #3/#5/#5b reverted.
Test: repro #14 (recruit + click the moles) — if clean x2, revert diag6+7,
final clean test. If STILL OOS with fix #6 in: the arming happened some
other way — CRE5 will again name the invoker.

**8/9 EARLIER: REPRO #12 -> FIX #5b REVERTED (broke click UX: executer lock
is held most of the time, and an unlock-gap click still produced the same
one-sided token) -> TOKEN TRANSPORT FULLY RE'd -> DIAG v7 (Network.dpl!)
APPLIED, awaiting repro #13.**
**TRANSPORT MODEL (Network.dpl RE, all disasm-verified):** local tokens:
MoveArmyEx tail -> TC.AddEvent @0x55803868 (vcall+0x10; refuses Remote) ->
TTokenControl.Add @0x558037B8 sorted-insert into TC list ([te+0xC]
counter, -1=unpositioned append). TTokenExecuter.Process @0x55803FD0 per
active TC: PrefetchTokenEvents (TC vmt+4 @0x55803A0C): LOCAL tc inserts
TSyncTE head (if [exec+0x32]) + TPassTokenTE tail, each event ->
PrefetchTokenEvent @0x55803CEC assigns counter=[exec+0x18]+pendingcount,
moves to executer pending [exec+0x10], TC list CLEARED; then Process calls
TC.TokenEventsPrefetched (vmt+8 @0x55803B48) with the pending list ->
STRICTLY-Local tc & count>0 -> distributer vcall+8 = SendTokenEvents
@0x558036B4 (broadcast 0x8000, package via TTokenPackage+SendDataPackage).
Receive: TokenPackageReceived @0x55803588 ([package+8]=src player) ->
remote TC list; GetPrefetchableTokenEvents @0x5580398C accepts only
counters == [exec+0x18]+i consecutively (until 0x554-class = TPassTokenTE).
**TNegotiateTE.Accept+0x135 / .Reject+0x95 are the ONLY callers of
TTokenExecuter.InsertExecuteEvent @0x55803E58** (thunk @0x557036AC, IAT
0x558FCA6C): direct append into the LIVE pending list, NEVER transmitted,
returns 0 (drop!) when executer not mid-batch — consistent only because
Accept executes on both machines. KEY UNKNOWN: for the one-sided mole move
(normal TC path!) did the owner SEND the batch / did the peer RECEIVE?
**DIAG v7** `build_desync_diag7_net.py` (patches **Network.dpl**, backup
Network.dpl.bak_diag7; Network REBASES - PIC w/ Network delta; cave 162B
@0x55806220 = CODE padding; mini-ring in Network BSS @0x55808100, RVA
0x8100): H1 TokenEventsPrefetched entry (playeridx|batchcount) per TC
activation, H2 TokenPackageReceived entry (src player, bit31 set).
desync_dump.py prints "NET ring". Note TTokenExecuter.Process also
revealed: executer pending list cleared (vcall+0x30=TTokenEventList.Clear)
before each prefetch; per-token event callback [exec+0x40/44/42] fires
ExecuteTokenEvent @0x55803D24. STATE: fixes #1+#2+#4 + diag v6 (AoWEPACK)
+ diag v7 (Network) applied; fixes #3/#5/#5b reverted. NEXT: repro #13 ->
NET ring shows send-cand for the owner idx with batch>2 (sync+move+pass) on
creator + RECV on peer (or absence -> the drop point is named).

**8/9 EARLIER: REPRO #11 -> CHAIN COMPLETE -> FIX #5b "clicklock" APPLIED
(since REVERTED - see above).** CRE5 = **TMoveSelector.SelectPath+0x73** -> ExecuteMove.
SelectPath's dispatchers (`call [reg+0x18]` scan) are ALL MOUSE handlers
(TMoveSelector.MouseDownEvent+0x64 @0x55763E6C, TAoWHSMapMouse.Down+0x4A
@0x557744D6, TSelectedArmy.MouseDownEvent+0x2E0 @0x55793068): **the user
clicking the recruited army whose stale path is auto-plotted (path[0] ==
army's own hex) confirm-executes the stale AI move — vanilla two-click UX.**
SelectPath logic @0x55763D48: clicked hex == current path first hex ->
vcall+0x24 ExecuteMove; else plot. The creation landed IMMEDIATELY after
CAPT tok#488 (executer LOCKED, mid-AI-burst) -> token races the sync
stream, executes one-sided. **KEY INSIGHT: TSyncTE compares seed VALUE =
f^n(seed0), so OOS == unequal DRAW COUNTS at the compare — order doesn't
matter. Idle-time clicks stay consistent (why normal LAN play works);
mid-burst injections don't.** Same window's OTHER creations ((9,50,0),
(10,33,1), setup-ok=0, no CRE5) appeared on BOTH machines in lockstep =
pump moves via fix2 cave — everything else exonerated.
**FIX #5b** `build_desync_fix_clicklock.py` (backup .bak_clicklock, cave
117B @0x55812280-0x55812300): replaces `call TPlayer.GetBusy` @0x5574A347
(5B E8 84730000) inside MoveArmyEx's busy check (runs only for callers
WITHOUT busy-skip [ebp+8] = the UI paths; MoveArmy wrapper pushes 0) with
cave: GetBusy, then if not busy AND network AND executer locked
([[[map+0x23C]+4]+0x4C]!=0) AND owner comm==LOCAL -> al=1 ("busy",
vanilla refusal exit @0x5574A46D). Pump (Global, runs inside lock) +
skip-flag callers untouched. UI effect: click during AI burst = brief
no-op, next click works. STATE: fixes #1+#2+#4+#5b + diag v6 applied
(fixes #3/#5 reverted). If repro #12 STILL desyncs, check whether the
creation now happens with lock=0 (widen gate: GetBusy-adjacent phase
flags) — CRE5/CRE3 still name everything.

**8/9 EARLIER: REPRO #10 -> FIX #5 WAS WRONG (reverted), DIAG v6 APPLIED.** Repro #10 (fix #5 verified live): STILL OOS, identical
signature (CRE3 MoveArmy+0xF, owner-local machine, mid-window 547, (44,10,2),
one-sided). **Fix #5 analysis error: TSelectedArmy VMT+0x08 =
CalculateMovePath — Update's vcall+8 in BOTH branches is DISPLAY PLOTTING
ONLY; TSelectedArmy.Update never executes moves.** Fix #5 gated a path
preview refresh → no effect → REVERTED (script kept). Full VMT map dumped:
+0 TMoveSelector.MouseMoveEvent +4 MouseDownEvent +8 CalculateMovePath
+C UpdateMoveCursor +10 CreateMCS +14 SetCurrentMove +18 SelectPath
+1C Unselect +20 ValidateSelection +24 ExecuteMove +28 Activate
+2C Deactivate (VMT @0x5570DD70). ExecuteMove dispatch-site scan
(`call [reg+0x24]`, 68 hits): plausible invokers = TMoveSelector.SelectPath
+0x70 @0x55763DB8, TSelectedArmy.SelectPath+0x1E3 @0x55792D4F,
TAoWHSMapKeyboard.KeyDown+0x2D0, TAoWHSMapMouse.DblClick+0x18
(TAoWHSMap.OnExecuteTokenEvent+0x45 = false positive — token-event VMT).
No-click invoker UNPROVEN → **DIAG v6** (bak_desync_diag6; diag5 reverted):
v5 + H13 'CRE5' at ExecuteMove entry @0x55793078 (6B 558BEC83C4E4, resume
0x5579307E) = invoker retaddr. Creation seq: CRE5→CRE3→CRE4→CREA→CRE2.
STATE: fixes #1+#2+#4 + diag v6 applied (fixes #3,#5 reverted).
NEXT: repro #11 → read CRE5 → fix #5b at the true invoker.

**8/9 EARLIER: REPRO #9 -> FIX #5 "noresume" APPLIED (since REVERTED).**
Repro #9 (fixes #1+#2+#4 verified live): STILL OOS, SAME creator (CRE3 =
MoveArmy+0xF <- TSelectedArmy.ExecuteMove on the owner-local machine B,
mid-window). Fix #4 held at the join but the destination CAME BACK:
**TMoveArmyTE.InitializeMove+0x126 re-writes [army+0x25..27] on EVERY move
token init** (synced state; a pre-join pump move for the then-Global moles
executed in LOCKSTEP post-join and re-seeded the dest on both machines).
Ring also showed classic ORDER SKEW: B injected its local mole token at
stream pos ~550 where A ran the negotiate token; the NEGOTIATE-ACCEPT token
executed at DIFFERENT positions on A vs B; A never received the mole token
at all (B locked at BOOM before sending?). Also observed: window WORK
counts CAN differ (A did an extra p4 work-unit in win 532 - positional
only, no draws; window length = 5 machine-local FRAMES, so per-window
work counts are not inherently deterministic).
**TSelectedArmy.Update @0x55793628 = the auto-resume driver** (loop over
current player [map+0xA5] armies): dest-branch @0x5579371C ([army+0x25]!=
0xFF/0 -> GetField -> vcall+0x20 valid -> vcall+8 plot+issue; invalid ->
ResetDestinationPos) vs path-branch @0x55793776 (UI path list nonempty ->
vcall+8 = the click flow). Both #8 and #9 creations = dest-branch.
NOTE: pre-existing BXL patch inside Update (+0x7B: call 0x5580DE5F + NOPs).
**FIX #5** `build_desync_fix_noresume.py` (backup .bak_noresume, cave 60B
@0x55812280-0x55812300): hook dest-check @0x5579371C (7B `8A4225 3CFF
7453`; resume 0x55793723; nodest target 0x55793776): network games ->
always take "no destination" exit. Effect: MP multi-turn orders don't
auto-continue (re-click each turn); clicks/paths untouched; SP unchanged.
May also fix the community's general "random LAN desync" reports (vanilla
auto-resume = machine-local token injection for ANY multi-turn order).
Fix #4 KEPT (harmless, still right at join). STATE: fixes #1+#2+#4+#5 +
diag v5 applied. Test: mole repro -> if OOS read CRE3 again; if PASS x2 ->
revert diag5 (build_desync_diag5.py --revert), final clean retest.

**8/9 EARLIER: REPRO #8 NAMED THE CREATOR -> FIX #4 "joindest" APPLIED.** Diag v5 CRE3 caught the divergent creation live on the
machine where the recruiting human (p1) is LOCAL, mid-token-stream, outside
any AI window: `CRE3 MoveArmy+0xF -> CREA (44,10,2) -> [MOVE]+[ANIM owner=1]
on A only -> BOOM`; B never created it and it was never delivered (B ran to
tok#475 > A's position; tc_dump both pending=0 post-freeze). MoveArmy
@0x5574A478 disasm: thin `push ebx;push ebx;push 0;call MoveArmyEx;ret`
(CRE4 = saved ebx = heap noise, as suspected). MoveArmy's ONLY callers
(xref): fix#2 cave tail-jmp (pump - blocks non-Global owners, can't be it)
and **TSelectedArmy.ExecuteMove+0x1F4 = the UI selected-army path** ->
proven creator by elimination + retaddr. ExecuteMove @0x55793078 decode:
flag [selarmy+0x18]==1 -> direct MoveArmyEx @+0x14B (gold-checked); else ->
**TArmy.SetDestinationPos @0x5578CB70 (writes [army+0x25/26/27]=x/y/l) +
MoveArmy** = multi-turn continuation. TArmy.ResetDestinationPos @0x5578CB60
= FF FF FF sentinel; callers incl TSelectedArmy.Update+0x147 (the UI
destination manager = the machine-local auto-continue driver) +
TMoveArmyTE.InitializeMove+0xaf (writes dest on EVERY move token init -
this is how the pre-recruit AI move seeded the moles' destination).
**ROOT CAUSE: the negotiate JOIN keeps the army's stored destination; the
owner's machine UI auto-resumes the stale AI path (no click), creating a
never-broadcast one-sided token.**
**FIX #4** `build_desync_fix_joindest.py` (backup .bak_joindest, cave 63B
@0x55812200-0x55812280 = fix#3's vacated space): hook join-done in
TArmy.IncommingNegotiateOffer @0x5578FC24 (7B `8BC6 E85936F7FF` mov
eax,esi;call BeginUpdate; resume 0x5578FC2B; esi=joining army; site+lockstep
proven by diag v1) -> network games only: [esi+0x25..27]=FF (inline
ResetDestinationPos). Recruited armies stand still until commanded (matches
fix#2's pump-side behavior). STATE: fixes #1+#2+#4 + diag v5 applied.
NOTE: repro #7's one-sided GLOBAL (p4) pending token (75,82,0) is NOT
explained by the UI path (can't select AI armies) - if repro #9 still OOS,
read CRE3 for the new creator. Test: mole repro x2 -> no OOS -> revert
diag5, keep fixes, final retest.

**8/9 EARLIER: REPRO #7 STILL OOS -> FIX #3 REVERTED, DIAG v5 APPLIED.**
Repro #7 ran with fixes #1+#2+#3 ALL verified loaded live (hook_probe): still
OOS. `re_tools/tc_dump.py` (NEW: dumps token-control pending queues of frozen
AoWx pair; walks tokman [map+0x23C], TC list [tokman+0x10], pending events
[tc+4]->[tel+8], names TE VMTs via classref slots, comm per player) showed
BOTH executers frozen at executed-count=544 but machine A holding a pending
TArmyDefaultMoveTE first-hex=(75,82,0) in **player 4's TC - comm GLOBAL** -
while B held nothing: a one-sided token for a GLOBAL owner, which fix #3
(Remote-owner gate) cannot address by design -> **fix #3 reverted 1:40 PM**
(`build_desync_fix_remoteowner.py --revert`; script kept for reference; its
one-creator idea may return in broader form). Comm rosters that game:
A p0..p5=[2,1,2,0,2,2], B=[2,0,2,1,2,2] (TWO humans: p1+p3, host+join self).
CreateArmyMoveTE direct-caller xrefs (bypass MoveArmyEx - CRE2 shows these
distinctly): TNegotiateTE.Accept+0x11e/.Reject+0x7e,
TArmyCombatMoveTE.RequestCombatTypeCallBack+0xd1, CreateArmyMoveXYLTE+0xaf,
MoveArmyXYLEx+0xd6, TTeleport.Teleport+0x15d, TCave.EnterEx+0x1aa (EnterEx
ALSO calls MoveArmyEx @+0x1f8 - two create sites in one function).
**DIAG v5 APPLIED** (`build_desync_diag5.py`, bak_desync_diag5; diag4
reverted first; fix caves #1/#2 untouched, verified): all v4 hooks + H12 at
MoveArmyEx entry 0x5574A318 (fix #3's vacated site) logging 'CRE3' =
MoveArmyEx's return address (true caller, CRE2 can't see past the funnel)
+ 'CRE4' = dword above the 2 stack args (= grandparent retaddr when direct
caller is the thin MoveArmy wrapper, else frame noise). Creation sequence in
ring: CRE3->CRE4->CREA->CRE2. desync_dump.py decodes both (symbolized).
hook_probe.py updated (fix3 row -> diag5 CRE3 row). **NEXT: repro #8, dump
while frozen (desync_dump.py + tc_dump.py), read CRE3/CRE4 at the divergent
creation -> name the machine-local creator -> design fix #4 there.**

**8/9 EARLIER: FIX #3 "remoteowner" APPLIED (repro #6 analysis) - since
REVERTED, see above.** With fixes
#1+#2 verified loaded (hook_probe.py), repro #6 still OOS: the (44,10,2) move
was created OUTSIDE any window (mid-token-stream — NOT the pump; fix #2 held)
and **executed on one machine only** — the other machine's tok# counter ran
past that stream position without it: a NON-BROADCAST one-sided token.
RE: **MoveArmyEx @0x5574A318 (true entry; +0x126 CRE2 retaddr can't
distinguish its callers!) is the single move-token creator**: tail
@0x5574A444 adds the TE to GetTokenControl(**army OWNER**) on whichever
machine calls it. Callers: MoveArmy+0xA (wrapper; pump call site hooked by
fix #2, human-UI TSelectedArmy.ExecuteMove untouched), MoveArmyXYL+0xAF,
TSelectedArmy.ExecuteMove+0x14B, **TTeleport.Teleport+0x1B0**,
**TCave.EnterEx+0x1F8** (cave-transit continuation; EnterEx ← TCave.Enter
(VMT, no static refs) + TEnterCaveEventLog.Yes+0x3 — event-log dialog
callback = machine-local frame time!). MoveArmyEx also has a busy-check
skip flag [ebp+8] and mode [ebp+0xC]; ret 8.
**FIX #3** `build_desync_fix_remoteowner.py` (backup .bak_remoteowner, cave
109B @0x55812200-0x55812280, hook entry 6 bytes 55 8BEC 51 53 56, resume
0x5574A31E): in network games, if the army owner's comm status is REMOTE(1)
on this machine → return 0/ret 8 (no local creation — the OWNER's machine
creates + its Local TC broadcasts with an agreed stream position). Local(0)/
Global(2) unaffected. One creator per token, all funnel callers covered.
[SUPERSEDED - repro #7 failed, fix #3 reverted, diag v4->v5; see top block.]

**8/9 EARLIER: DIAG v4 + FIX #2 "aiowner" (still applied).**
Repro #5 dump: divergent move (44,10,2) executed then `[ANIM] owner=1` — the
mole army was ALREADY RECRUITED (human player 1 owns it) yet the move came
from `MoveArmyEx` in the AI pump: **stale AI move queue keeps commanding the
recruited army** (RetrieveArmy fetches whatever army sits on the stored hex;
TAIMoveExecuterUnit.Validate @0x5573EBC4 checks FindUnit existence + unit
flag 0x25&0x10, NEVER ownership — vanilla bug). Human-owned ⇒ exempt from
fix #1 ⇒ animates on the watching machine ⇒ token spans frames ⇒ draw at
different stream positions ⇒ OOS. STAT fingerprints identical zeros on both
machines at the divergence (busy48/combat/p44/cbq/elog all equal) — every
other suspect exonerated.
**FIX #2** `build_desync_fix_aiowner.py` (backup .bak_aiowner, cave 210B
@0x55812100-0x55812200): in network games ([map+0x239]==2), the AI pump
refuses to issue moves for armies whose owner comm-status != Global —
call-site hooks ONLY inside ProcessExecuteMoves: A) 0x557428B2 `call
MoveArmy` → cave (foreign ⇒ AL=0 = normal move-failure path; else tail-jmp
MoveArmy 0x5574A478; human-UI caller TSelectedArmy.ExecuteMove+0x1F4
untouched); B) multi path 0x557427D1 `test al,al;je;xor ecx,ecx` (6 bytes)
→ cave (foreign ⇒ original skip 0x5574284A; else displaced xor + resume
0x557427D7). Owner lookup = fix #1 pattern. Side benefit: fixes vanilla
quirk of recruited units wandering under AI orders (network games).
STATE: fix#1 + fix#2 + diag v4 ALL APPLIED. Test protocol: mole repro ×2 →
expect NO OOS; then revert diag v4 (build_desync_diag4.py --revert), keep
both fixes, retest once. If STILL OOS: dump again (diag in place).

**8/9 EARLIER: FIX #1 NECESSARY BUT NOT SUFFICIENT.** Repro #4 (fix applied) still
OOS, SAME signature: window tok#463 identical WORK sequence + RNG on both
machines, but only machine A's 4th p2 work created the mole move (44,10,2).
Live probe of the frozen processes (`re_tools/comm_probe.py`) verified EVERY
fix precondition true in-memory: hook+cave present and correctly targeted,
mode [map+0x239]=2, pcc chain valid, **player 2 = Global(2)** (p0/p4/p5
Global, p1 Local, p3 Remote). Remaining machine-local candidates: (a) HUMAN
(Local/Remote) army mid-animation as world-state timing (fix exempts
humans by design), (b) event-log delay queue ([map+0x1DC] 2-frame countdown
per log, callbacks [map+0x1D4] can create move TEs), (c) per-player busy
state ([player+0x48] counter / [player+0x44] / combat [map+0x120] — all read
by TPlayer.GetBusy @0x557516D0).

**DIAG v4 APPLIED 8/9** (`build_desync_diag4.py`, backup .bak_desync_diag4;
v3 reverted first; fix cave @0x55812000 untouched): all v3 hooks + 'ANIM'
(TArmyHS.MoveFirst entry @0x55792084 — EVERY animation start, val = dest
xyl + owner), 'ELOG' (SetExecuteEventLogDelay @0x5577653C — new|old delay +
cbcount), 'STAT' (after each WORK: busy48|combat|p44|cbq|elogdelay|player
fingerprint via [[[map+0x140]+8]+4][idx]). Cave 964B @0x55811000-0x55811500.
desync_dump.py decodes the new tags. NEXT: repro once, dump while frozen,
diff ANIM/STAT at the divergent window → name the input → design fix #2.

**AI-side RE facts (8/9):** TAIMoveExecuter.Process @0x55742A14 ([+0x2C]
state: 1 active, 2 move-failed, 3 all-done via ProcessMECS tail, 4 = some
unit result≠2 via UpdateMoveResult, 5 invalid; [+0x28] 1=queue→
ProcessExecuteMoves issues via MoveArmyEx/MoveArmy, 0→ProcessMECS runs MECs
Default/Adjacent/Transport via vcall+0x64 under GetProcessTimeLeft budget).
Move issuing needs TAIMoveExecuterMove.RetrieveArmy @0x5573EF84 =
GetField(stored xyl)→GetArmyHS — fails if army sprite not on expected hex.
[unit rec+0x35]=2 ("reached target") written ONLY by CreateMove planning
(SetMoveResult @0x5573ED5C). TAIMoveExecuter.UnitsMoveDone + FinishMoves =
DEAD CODE (no xrefs). TAIGroupControl.ExecuteME @0x55738D64 → ExecuteMove
@0x55742C2C. TPlayer.GetLocal @0x55753720 returns 1 for status 0 AND 2.
Event-log: delay ctr [map+0x1DC] (SetExecuteEventLogDelay max-writes,
UpdateExecuteEventLogDelay decrements → UnlockExecuteEventLog at 0), cb list
[map+0x1D4] (count [[l+4]+8]). ValidateObservation @0x55775D5C = local-viewer
watch/scroll display logic. TMoveArmyTE VMT slot map + MoveVisible details in
the fix section below.

**ORIGINAL FIX NOTES (still applied, keep):**
`build_desync_fix_noanim.py` (--apply/--revert, backup AoWEPACK.dll.bak_noanim
= diag-v3.2-but-no-fix state): hooks **TMoveArmyTE.MoveVisible @0x55748198**
(6 displaced bytes 53 56 8BF2 8BD8, jmp back 0x5574819E; PIC cave 110 B
@0x55812000, reloc-scan built into script, ranges verified clean). Cave
returns FALSE (→ instant, non-animated move — an existing vanilla path used
for off-screen/cross-level moves) when `byte[map+0x239]==2` (network game
only) AND army owner's comm record byte+8==2 (Global) via
`TPlayerCommunicationControl.GetPlayers` thunk @0x557035DC with
pcc=[[map+0x240]+0x1C], owner=[[[TE+0x28]+0x1C]+0x12]; every pointer
nil-checked → vanilla.

**Why this is the right choke point (RE 8/9):** TMoveTE.Execute is a state
machine; state 1 re-polls vcall+0x54 ProcessMove each frame while a move
ANIMATES; animation starts ONLY in shared TMoveArmyTE.SetupNextMove (vcall
+0x78, all 4 token subclasses Default/Negotiate/Combine/Combat share it),
which starts the sprite walk via TArmyHS VMT+0x11C MoveFirst ONLY if
`MoveVisible(step)` (local-viewer TAoWHSMap.Visible && !(army.flags&0x10))
or already-animating sticky [TE+0x34], AND the step's level == viewed level
[map+0x88] (or [map+0x180]). Not visible → SetupNextMove no-ops → Animating
(GetMoveStatus 0xFF idle; all Animating overrides bottom out on
GetMoveStatus) false → ExecuteMove→ProcessMove recursion completes the WHOLE
path in one Execute call. So move-completion time (and thus when the AI pump
may create the follow-up move) was machine-local ⇔ visibility/level of the
move on that machine. Full VMT map: +0x4C Execute +0x50 GetMapF +0x54
ProcessMove +0x58 Validate +0x5C InitializeMove +0x60 FinishMove +0x64 Move
+0x68 LastMove +0x6C DefaultMove +0x70 Animating +0x74 UpdateAnimation
+0x78 SetupNextMove +0x7C CanMoveNext +0x80 ExecuteMove.
Also serializes the v3.1 "created outside window" path: cave-transit /
event-log continuations fire from MoveTo during token execution once nothing
animates. Visual cost (network games only): AI/independent armies relocate
instantly instead of walking.

**8/9 home-PC repro (3rd consistent dump, diag v3.2):** window tok#634:
A created move (44,10,2) mid-window (CRE2 MoveArmyEx+0x126), B ran the
identical window (same WORK seq, same seed 911BFFE1) and created nothing;
both executed the same moves at different stream positions → BOOM. timemode=0
both. Confirms the laptop diagnosis on different hardware.

**TEST PROTOCOL:** user re-runs the Khazlkound mole repro (two instances)
twice: expect NO OOS, moles/AI teleport rather than walk. If OOS still fires,
run desync_dump.py while frozen (diag v3.2 still in). After PASS: revert diag
(`build_desync_diag3.py --revert`, restores hook sites + H3 reloc entry;
fix cave/hook untouched — fix script is independent of diag state), retest
once more clean.

**OOS mechanism (proven):** NetworkE.TSyncTE.Execute compares token value vs
TPlayerControl.GetSyncValue@0x55754CE8 = `[AoWHSMap+0x230]` = TAoWHSMap.Random
@0x5577827C's stored synced seed. OOS == clients consumed different synced
Random rolls. Mismatch → TPlayerControl.OutOfSync@0x55754D04 → dialog +
TTokenExecuter.Lock (both instances stay alive/frozen — dumps still readable).

**Repro:** map "AoWx - Towers of Khazlkound", two local instances (host + join
self), recruit the independent dwarf moles near the dwarf spawn → OOS.

**Ruled OUT by evidence:**
- The recruit/negotiate flow itself (msg 0x110E/0x110F, TNegotiateTE): executed
  IDENTICALLY on both clients in the v1 dump (both bailed at
  IncommingNegotiateOffer `[TE+0x24]==2` check, mode=1, no join). Recruit is
  the TRIGGER (wakes the neutral AI), not the divergence.
- TAutoProduceAIPA/GetBusy local-vs-remote asymmetry: DISPROVEN by confirm hook
  — GetBusy ring identical on both machines (player=2, busy=0,1,0,0 /
  local=1,1,1,1), all AutoProduce draws in lockstep.

**Current best evidence (v1+getbusy repro dump, fresh game):** both instances
in perfect lockstep (identical caller+seed sequences) through recruit and AI
production; the ONLY divergence = instance A did ONE extra synced draw at
`TMoveTE.Execute+0x36` (seed 8AF9ADE7, an AI move token for player 2, which is
local=1 on BOTH machines); B stopped one draw earlier → 1-draw seed offset →
next TSyncTE compare fails → OOS. Note the two instances loaded AoWEPACK.dll
at different bases (A rebased 0x2560000, B 0x55700000) — ASLR
pointer-ordering non-determinism in AI move generation is the prime suspect
(fits both user scenarios: any independent interaction wakes the neutral AI).

**VERDICT 8/7 ~10:45 PM (v2 dump, clean repro): TOKEN-ORDERING DIVERGENCE,
not move generation.** Rings lockstep ~115 entries, then at seed ADD45BEA:
A ran move first-hex=(7,8,0) → TCombat.Execute draw @13DA7393 → SYNC
@3B740DE0 → BOOM; B ran move (44,10,2) → SYNC @13DA7393 → BOOM → then STILL
executed the same (7,8,0) move @13DA7393 and same combat @3B740DE0. Same
tokens on both machines, different execution ORDER relative to each other and
to the sync-check token. Milder precursor mid-ring: same (44,10,2) move at
71AAE32E on both but B had one extra SYNC before it (sync token drifting
through the stream). Both machines BOOMed (A once, B twice — B kept executing
past its first BOOM). AutoProduce draws (TAIGroupProductionControl.Process
+0xAA @6AD07309) were in lockstep — production exoneration holds.

**Refined mechanism:** neutral-player AI (local=1 on BOTH machines) generates
move tokens locally on each machine mid-turn (woken by the recruit); those
tokens interleave with the network-delivered TSyncTE by frame timing /
machine-dependent order, and TMoveTE consumes a synced draw per execution, so
the seed at each machine's sync-check position differs → OOS. The moves
themselves were identical — determinism of the AI decisions is NOT the
problem; serialization of token execution order is.

**Fix directions (user chose: NOT yet — discuss first):**
(A) gate the mid-turn neutral-AI wake so AI moves only run at the
synchronized turn slice (kills the trigger; smallest patch; find the
recruit→AI-wake path); (B) host-only AI simulation + broadcast tokens
(robust, big architecture change); (C) defer/make sync check
order-insensitive (hacky, hides real desyncs). Recommended next RE: how
TTokenExecuter orders locally-generated vs network tokens, and where the
recruit wakes the neutral AI mid-turn.

**DIAG v2 = `build_desync_diag2.py`** (--apply/--revert, backup
.bak_desync_diag2): 4 record-only hooks, cave @0x55811000-0x55811200, ring
@0x558FAA00: H1 every TAoWHSMap.Random (caller+seed, null-safe via global),
H2 TMoveTE.Execute post-Random @0x557478F2 → 'MOVE' + first path hex
(TE+0x14 TXYLList: +4 data, +8 count, entry=x|y<<8|l<<16), H3 GetSyncValue
@0x55754D04 → 'SYNC' (fires on send AND check), H4 OutOfSync @0x55754D14 →
'BOOM'. Reader/differ: `reference files\BXL\re_tools\desync_dump.py` (prints
ring diff w/ content-shift alignment; run while both instances alive).

**v2 CRASH FOUND+FIXED 8/7 ~10:30 PM:** first two v2 launches (9:28 + 10:14)
died instantly with "Exception during AoWHSMap.NewFrame" on the rebased
instance. Cause: H3's displaced `mov eax,[AoWHSMap]` (A1 40A08F55) carries a
BASE RELOCATION on its imm32 (VA 0x55754D05, entry word @file 0x27DBD0) — on
a rebased load the loader applied that fixup ON TOP of our jmp rel32 → wild
jump every frame. Script now neutralizes the entry on apply (0x3D05→0x0D05,
type 3→0 = skipped) and restores on revert; other 3 hook sites + cave scanned
clean (only that one reloc intersects any patched byte). See
[[patching-over-relocs-gotcha]].

**ARCHITECTURE MAPPED 8/7 late (user chose fix direction A - gate/determinize
AI):** AI players are comm-status 2 "GLOBAL" ([players+8]: 0=Local 1=Remote
2=Global, see TTokenControl.Local/Global/Remote @0x55803920+) — simulated on
ALL machines by design; AI tokens are NOT broadcast, sync relies on identical
generation AND identical stream position. Serialization device = capture
windows: TTokenExecuter (Network.dpl base 0x55800000; executer=[tokman+4],
tokman=[map+0x23C], executed-count=[tokexec+0x18], lock=[+0x4C], round-robin
ActivateNextTC held off by [+0x54]) — TAoWHSMap event
TAIExecuter.TokenControlDoneEvent@0x557345C0 (mode-2 only, gated
[map+0xA4]==0 && [map+0x11C]==0) → CaptureTokenCycles(5)@0x5573466C →
TTokenExecuter.Lock; AI pump = NewFrame → TAIExecuter.Process@0x55734780
(aiexec=[map+0x128]; NewFrame gate: [map+0x11C]==0 && [map+0x118]!=2; also
AI-lock [aiexec+0x30] via TAIExecuter.Lock/Unlock — combat code
locks/unlocks incl UI callbacks like RestoreHotSeatModeCallBack!); does ≤1
work-unit (TAIPlayerControl.Process@0x5573416C) per frame per window; window
= [aiexec+0x2C] counts frames vs [aiexec+0x28]=5 → TokenCyclesCaptured
@0x557346FC → Unlock. Time budget: GetProcessTimeLeft@0x5573449C mode byte
[aiexec+0x1A]: 0 = LOGICAL (Create default! budget [aiexec+0x1C]=5000,
used [aiexec+0x20] reset each Process) = deterministic; 1 = REALTIME
GetElapsedMilliSeconds = machine-dependent. ~27 call sites across whole AI
stack use it. Static scan found NO write of mode=1 — mode may stay 0
(then realtime theory dies; suspicion shifts to combat-gate/AI-lock timing:
[map+0x11C]/[map+0x118]/UI-callback unlocks). Undecided → v3 diag measures.

**v3.2 CRE2 DUMP (8/8, decisive):** the skewed move (44,10,2) was created by
**MoveArmyEx+0x126** (= the call at 0x5574A439, i.e. MoveArmy ←
TAIMoveExecuter.ProcessExecuteMoves ← .Process ← TAIPlayerControl.Process —
the NORMAL AI pump, INSIDE capture window 776 on machine A) — while machine B
ran the *same window with the same work-unit sequence* (players 5,5,5,0,2)
from *provably identical RNG state* and created NOTHING (B issued the same
move windows later; in the earlier repro B was the EARLY one). So the AI
pump's non-RNG inputs differ across machines: the move-executer's per-army
"previous move done" state, which updates on machine-local timing —
working hypothesis: move ANIMATION/visibility completion (viewport-dependent:
the player watching the moles animates them, the other machine completes
instantly; both instances share one registry so SETTINGS are equal —
visibility is the only asymmetry). Relevant RE: TArmyHS.MoveFirst@0x55792084
reads GetMovementSpeed → step count [armyHS+0x22], level/viewport-scroll
logic; TArmyHS Move* only invoked via VMT (0x557133A0, MoveTo@+0x10C,
MoveFirst@+0x11C); TMoveArmyTE.InitializeMove+0x126 writes [army+0x25]
(army moving/dest flag, also TArmy.Set/ResetDestinationPos, ResetMoveDone —
ResetMoveDone + TAIMoveExecuter.UnitsMoveDone are DEAD CODE (no callers/refs);
lots of dead code in this engine — always xref before trusting a name).
TAIMoveExecuter.UpdateMoveResult@0x5574270C: [self+0x2C] 3→4 when all its
units' rec[+0x35]==2; writer of rec[+0x35]=2 on completion NOT yet found
(setter xrefs are all AI-side). RING HAS NO TIMESTAMPS — if temporal order
(stall vs no-stall) matters next session, add GetElapsedMilliSeconds to ring
entries (diag v4).

**FIX DESIGN (next session):** leading candidate = force the NO-ANIMATION
path for army moves whose owner is comm-status-2 (Global) in mode-2 games —
kills all animation-completion asynchrony at the source; visual cost: AI/
independent moves teleport. Entry points to find: TMoveTE.Execute@0x557478BC
→ InitializeMove/ProcessMove/Move/FinishMove chain — locate where sprite
animation starts (vcall VMT+0x11C MoveFirst) vs instant placement, and what
notifies the AI records on completion. Alternative: make the AI-record
completion write happen at token execution for Global armies. Verify with
diag still applied + one repro; then revert ALL diag hooks.

**v3 DUMP RESULTS (2 repros 8/8):** timemode=0 both machines (realtime-budget
theory DEAD); capture windows + WORK sequences PERFECTLY identical
(scheduling exonerated); divergence = two pending AI moves pulled in swapped
order from identical state. v3.1 CREA repro nailed it: window-created moves
((74,84,0),(17,60,0)) in lockstep, but move (44,10,2) (underground/mole army)
was CREATED OUTSIDE any capture window, mid-token-stream (between sync-token
executions), at positions a full window apart on the two machines (A: after
win-638; B: before win-638, executed pre-window). So: SOME FRAME-DRIVEN
(non-token, non-AI-pump) path creates AI moves at machine-local times.
Suspects: (a) event-log deferred callbacks — TAoWHSMap
Lock/UnlockExecuteEventLog + UpdateExecuteEventLogDelay@0x55776560:
[map+0x1DC] FRAME countdown (set to 2 per log) then ExecuteNextEventLog;
ExecuteEventLogDone runs stored callbacks; TCombatTypeRequestEventLog
callback = TArmyCombatMoveTE.RequestCombatTypeCallBack+0xd1 → CreateArmyMoveTE;
(b) Cave.TCave.EnterEx+0x1aa → CreateArmyMoveTE (cave transit continuation —
moles are underground!); (c) TNegotiateTE.Accept+0x11e (token-exec side,
deterministic, unlikely). CreateArmyMoveTE@0x5574A1A0 mode: 0=Default
1=Combat 2=Negotiate 3=Combine; full caller tree mapped (MoveArmy(Ex)←
TAIMoveExecuter.ProcessExecuteMoves←.Process←TAIPlayerControl.Process pump;
TSelectedArmy.ExecuteMove=human UI). TAIMoveExecuter.UnitsMoveDone = event
handler (no static caller) — move-completion driven. v3.2 adds 'CRE2' marker
(CreateArmyMoveTE caller retaddr [ebp+4]) right after each CREA → next repro
names the creator.

**STATE: DIAG v3 APPLIED 8/7 ~11:30 PM** (`build_desync_diag3.py`, backup
.bak_desync_diag3 = stock; v2 reverted first). v2's 4 hooks + reloc fix PLUS:
'CAPT' (CaptureTokenCycles) / 'RELS' (TokenCyclesCaptured) = tok-executed-
count low24 | timemode<<24; 'AIUL' (TAIExecuter.Unlock) = count | lockdepth
<<24; 'WORK' (post TAIPlayerControl.Process in mode-2 pump @0x557348D7,
displaced je re-encoded) = result | playerIdx<<8. Cave 546B
@0x55811000-0x55811300. desync_dump.py decodes new tags. NEXT: user repros
OOS once more (restart both instances), run desync_dump.py while frozen.
Read: where do CAPT/RELS tok# boundaries or WORK counts first differ, and is
timemode 0 or 1? That pins the nondeterminism source → then design fix
(candidates: force mode-0 logical budget everywhere / determinize the
divergent gate / defer AI wake).

Side note (resolved scare): "glitched inactive races / first turn won't end" —
map file untouched by us (mtime 7/31, player list identical across all copies:
Neutral + 5 races, all active-flag=0); symptom = map's own unfilled AI slots,
did not reproduce on stock DLL.

Related: [[spring-of-life-wasteland]] (same RNG/token knowledge),
[[aowepack-dll-is-live]].


## Index note (moved verbatim from MEMORY.md 2026-09-21)
- [lan-desync-investigation.md](lan-desync-investigation.md) — LAN OOS solved (FIX #8 movedraw). ⭐ Holds the **two-RNG model** (synced `[map+0x230]` vs bare `@RandInt`/HitRole sharing Delphi RandSeed — combat rolls are invisible to the sync check but must match in COUNT) + the Mind Decay audit and 🔨 build_minddecay_oos.py (applied 8/31, MP-untested). 8/31: fix #1 "noanim" caused teleporting AI moves in SP since 402; **noanim now FULLY REVERTED (user call) — AI animates in SP+MP; #8 alone should hold. ⚠ LAN moles-repro + state-consistency test REQUIRED; fallback = build_desync_fix_noanim2.py --apply (v2 remote-gated).**
