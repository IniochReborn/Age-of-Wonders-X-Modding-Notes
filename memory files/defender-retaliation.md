---
name: defender-retaliation
description: "✅ COMPLETE & USER-CONFIRMED 2026-08-14 (v5.2): AI defender that takes unit damage and whose attacker flees combat hunts THE ATTACKING PARTY specifically (mark follows the marked unit through splits), returns to its home hex when the target dies/escapes, then DEMOTES back to its original behavior. build_defender_retaliation.py, 4 hooks + BSS mark table. Deep RE bank: combat results, AI groups/behaviors, GuardArea state machine."
metadata: 
  node_type: memory
  type: project
  originSessionId: c789e62f-993f-417b-8ab1-88a32d8c934d
  modified: 2026-08-15T00:04:27.793Z
---

# Defender retaliation vs attack-and-flee (user request 2026-08-14)

Exploit: attack an AI army, cast spells, retreat from tactical combat,
re-attack later — AI never pursues. User wants chase-then-return (Guard-Area
style, no pulling guards off POIs permanently), and for empire AIs with
multiple nearby parties, an all-parties response (Phase 2).

## ✅ PHASE 1 APPLIED 2026-08-14 — `patch scripts/build_defender_retaliation.py`
(--apply/--revert/--status, backup `AoWEPACK.dll.bak_retaliate`; **v2** applied &
disasm-verified 8/14 after the v1 flee-crash). Hook @ **0x55749913** (TArmyCombatMoveTE.CombatExecuted
common exit, displaced `59 5a 5d 5f 5e 5b c3`) → cave **@0x55811120 (160 B,
next free AoWEPACK cave 0x558111C0)**:
if [combat+0x14]==9 (fled result) → defender field via **TCombatData
[combat+0xC] pos +8/+0xC/+0x10 → GetFieldXYL thunk 0x557020FC** (⚠ v1 used
the TE's path list [te+0x14] — NIL at TTerminateCombatTE-driven flee
termination → AV in HSEPack TXYLList.Get @0x55605685 'Read of 00000008',
'Exception occured during TTerminateCombatTE'; caught live via grabwin +
detail dialog, fixed same day = v2) → army HS via vcall [field
vmt+0x80](classid 0x20217) → TArmy=[hs+0x1C] → gate: [army+0x12]==0
(independents) OR GetPlayers([M+0x140],id)@0x557544D0 → [player+0xA7]!=0 (AI)
→ if GetBehavior(army,0xFF)@0x5578C578 != 3 → **SetBehavior(army, mask 0xFF,
3=GuardArea) @0x5578C590**. PIC delta for the [M]=0x558FA040 absolute; ebx=
combat & [esp]=TE at hook site. Runs on every machine (TE ctx) ⇒ MP-lockstep;
AI groups are serialized ⇒ save-safe.
Expected: fled-from defenders hunt the attacker on their next activation
(GuardArea radius ~7 around captured home) and walk back to their exact home
hex afterward (vanilla TGuardAreaAGC state 2). Human defenders untouched.
Note: promotion is permanent (Guard→GuardArea); returns home by design, so
POIs stay guarded; revisit if bait-tethering (≤7 hexes, always returns) is
abused.


## ★★ v3 (2026-08-14, APPLIED, disasm-verified) — TARGETED retaliation
v2 user test: chase+return WORKED (independents open-hex, independents city,
AI-player party) but targeting was indiscriminate — GuardArea attacks anyone
in its area, "rarely my leader that attacked". v3 = marked-target system,
same script `build_defender_retaliation.py` (revert v2 first — v3 has THREE
hooks; caves @0x55811120, 507 B: c1@0x55811120 c2@0x55811265 c3@0x55811305,
**next free AoWEPACK cave 0x5581131B**). ⚠ v3.0 crashed on flee (AV @c1
0x558111E6, 'Read of 00000000'): read [combat+0x1C] as a plain TList — the
side object wraps the real TList at **[[side+8]]** (items +4/count +8, per
vanilla AliveCount @0x55726E3F); fixed v3.1 same day:
1. **Combat-end cave c1 @0x55811120** (hook 0x55749913 as before): after the
   GuardArea promotion, pick a MARK UNIT from the combat's attacker side list
   [combat+0x1C] (combat objs; alive=[obj+0x48]&1; TUnit via helper
   0x55810F00; **THero VMT 0x55711FAC preferred** via @IsClass 0x557010C0) →
   token=[unit+0x18] → group=TArmy.GetGroup(army,0xFF) @0x5578C4A0, verify
   vcall [grp+0xD0]==3 → **[group+0x54]=token**. +0x54 sits inside
   TGuardAreaAG's serialized 0x32-byte block @+0x50 (vanilla uses only
   +0x50..52=home) ⇒ save/MP-carried; old saves = 0 = no mark.
2. **Filter cave c2 @0x5581125A** (hook TGuardAreaAGC.TargetFoundEvent entry
   0x557D8CB8, displaced `55 8bec 53 56`): marked group only accepts targets
   whose [tgt+0x30..0x32] pos == marked unit's CURRENT hex
   (token→0x5577E948([M+0xFC]) →TUnit.GetLocation 0x5577ED94; GetLocation
   forwards to [unit+4]=current army ⇒ **mark follows the unit through party
   splits/merges**). Unit dead/unplaced ⇒ mark cleared ⇒ vanilla. Reject =
   `ret 4` (event swallowed, target not added). No mark ⇒ fully vanilla
   (map-designed GuardArea guards unaffected).
3. **Expiry cave c3 @0x558112FA** (hook MoveExecuterDone home-arrival reset
   0x557D8D5E, displaced `8b500c c74250ffffff00`): the vanilla
   [ag+0x50]=0xFFFFFF home-reset now also clears [ag+0x54] ⇒ once the guard
   walks back home the mark is gone and it's a plain GuardArea again.
Net behavior: chase THE attacker's stack while it's in the area; attacker
leaves area/dies ⇒ no targets ⇒ walk home ⇒ mark cleared. ⚠ branch-target
prechecker has 2 whitelisted false positives (imm bytes of
`mov eax,[0x557D7F70]` @0x557D8C38 decode as jcc).
KNOWN LIMITS: mark = one unit (hero preferred); if the player detaches that
unit as bait, guards chase the bait stack (acceptable). While mark is live
and attacker out of area, other intruders are ignored until the guard
re-parks (mark then clears).

## ▶ v3.1 FAILED in test (2026-08-14 late) → v3.2 APPLIED with recorder
User test of v3.1: STILL indiscriminate; plus an in-game autosave LOAD left the
game in a per-frame error loop ('Exception occurred during UpdateFrame event' /
'Exception during AoWHSMap.NewFrame' alternating every frame — these wrappers
carry no detail; cause unproven, suspects: marked-group state after load, or
c2 reject interacting with finder, or pre-existing).
★ ROOT-CAUSE CANDIDATE for no-filtering: **[combatobj+0x48] bit0 is NOT
'alive' — it is a ctor-set 'is-a-unit' flag** (only 2 writers, both ctors:
unit ctor writes [0x55724A68]=1?, wall ctor writes 0). Real state bits:
**[combatobj+0x47] bit0=DEAD, bit3(0x8)=FLED** (AliveCount masks +0x47 with 9
and requires ==0). v3.1's mark-picker accepted DEAD units → first list entry
(likely a corpse) marked → token resolved nil in c2 → mark cleared → vanilla
indiscriminate chase. ✓ fits observed behavior exactly.
**v3.2 (APPLIED, disasm-verified; caves 617 B @0x55811120: c1@0x55811120
c2@0x55811292 c3@0x55811373, next free 0x55811389):**
- candidate now requires is-unit AND NOT [obj+0x47]&1 (fled bit fine);
- **BSS diagnostic recorder @0x558FAF60** (14 dwords): +0 c1 triggers, +4 army,
  +8 group, +C groupVMT (→static = TGuardAreaAG 0x557D80A8 check!), +0x10 mark
  token, +0x14 sidelist count, +0x18 c2 calls, +0x1C marked calls, +0x20
  accepts, +0x24 rejects, +0x28 resolved unit, +0x2C unit pos, +0x30 target
  pos. **`build_defender_retaliation.py --read` pulls it from the RUNNING game**
  (Toolhelp+RPM). Read after flee (mark written?) and after AI turn
  (accept/reject) — decide next step from DATA.
⚠ jump-range gotchas while building: rel8 to far labels (twice now) — c2 uses
jcc32/trampoline for early exits; jecxz can only do rel8 (trampoline pattern).

## 🛑 v3.2 ALSO FAILED (2026-08-14 night) — FULLY REVERTED, feature back to drawing board
v3.2 test: attack+flee → defender attacked ANOTHER of the user's stacks (filter
STILL ineffective) → then HARD CRASH TO DESKTOP (process died; recorder BSS
lost, no dialog — zero forensics). Retaliation patch fully reverted
(`--revert`, all 3 sites stock, caves zeroed); baseline = damage-response
patch only (stable, confirmed). Backups kept.
★ LEADING THEORY for why the filter never worked: **TGuardAreaAGC's ATTACK
targets do not (only) come through TGuardAreaAGC.TargetFoundEvent** — the AI
has a whole separate targeting stack (`TAIGroupTargetSelector` .Process/
.GetValidTargets/GetRequired*Strength + AGCPlugins.TAIGroupDefendTargetSelector,
`TAIMoveTargetSelector` with TriggerTargetFound/buffered targets) that was
never RE'd. Both v2/v3 observations fit: promoted guard attacks the attacking
player's OTHER stacks (nearest?) — a selector-driven choice, not the
area-finder event. The hard CTD may be my c2 reject (`ret 4` swallowing the
event) breaking the finder/selector record lifecycle (refcounted
TAIGroupControlTarget) → UAF later, or a c1 edge on the follow-up combat.
UNKNOWN — do not re-attempt from guesses.
★ REQUIRED BEFORE NEXT ATTEMPT: full RE of the strategic AI targeting chain:
TAIGroupTargetFinder → TAIGroupControl.TargetFoundEvent → target list →
**TAIGroupTargetSelector (+plugins) → TAIMoveTargetSelector → move executer**,
incl. which stage picks the ATTACK target and where a per-group filter/bias
belongs. Also RE THuntAG/THuntAGC (HuntingPlayer @0x557396A0 — hunts a
specific PLAYER; no return-home though).
★ Residue in user saves: v3-era marks in [AG+0x54] (inside serialized block)
— benign under vanilla/reverted code (nothing reads +0x54); v2/v3-promoted
GuardArea groups persist in saves = armies now chase-anyone-in-area+return
(vanilla behavior, acceptable).
★ The in-game-load per-frame error loop (UpdateFrame/NewFrame) from the v3.1
session remains UNEXPLAINED — retest vanilla in-game load on the baseline
before blaming any future patch.

## ✅ v4 APPLIED (2026-08-14 night) — STABLE BASE + DAMAGE GATE + OBSERVER
User confirmed: baseline in-game load is FINE ⇒ the load error-loop WAS v3's
filter (event-swallow lifecycle corruption, most likely). New user requirement:
retaliate ONLY if the defender took damage.
v4 (same script; caves 598 B: c1@0x55811120 c2@0x558112A6 c3@0x55811360, next
free 0x55811376):
- c1 = v2 logic + **DAMAGE GATE: requires [delta+0x558FAF24]!=0** (defender-
  side unit-damage flag from build_defender_damage_response, per-combat ⇒
  attack-and-flee without damaging them = NO chase) + **typed mark write**
  (IsClass group vs TGuardAreaAG VMT 0x557D80A8 before touching +0x54 —
  eliminates the wrong-class-corruption vector) + recorder.
- c2 = **PURE OBSERVER** on TGuardAreaAGC.TargetFoundEvent: counts calls/
  marked-calls/match/mismatch + records resolved unit & positions; CHANGES
  NOTHING (always falls through to vanilla). Purpose: one clean test run
  answers (a) does this event fire during the chase at all, (b) does the mark
  match the picked target's hex — the facts needed to design targeted-chase
  correctly. `--read` pulls live.
- c3 unchanged (mark cleared on return-home).
⚠ EXPECTED behavior this build: chase is STILL indiscriminate (v2 behavior) —
by design until observer data arrives. DEPENDENCY: requires
build_defender_damage_response applied (flag 0x558FAF24).

## ★★★ v5 APPLIED (2026-08-14 night) — data-driven redesign from the v4 recorder run
**v4 recorder findings (the run that unlocked everything):** c1_triggers=10 for
one flee (CombatExecuted exit hit repeatedly — idempotent, fine); army recorded
but sidelist_count NEVER ⇒ **[combat+0x1C] side lists are torn down in the
flee path — mark could never be written there**; c2: 53 calls, 53 'marked'(!),
53 mismatches correctly detected ⇒ **TargetFoundEvent IS the chase-feeder and
pos-compare works** — but the nonzero 'mark' came from a field WE never wrote ⇒
**[AG+0x54] is vanilla-used — v3 squatted a real engine field** (bogus marks +
v3 c2/c3 writes to it = the likely CTD). Defender was chasing (13,10,1) while
the resolved unit sat at (20,10,1).
**v5 (applied & disasm-verified; caves 791 B @0x55811120: c1@0x55811120
c2@0x558112AE c3@0x558113BD c4@0x5581140A; next free AoWEPACK cave
0x55811437; 4 hooks: 0x55749913 / 0x557D8E06 / 0x557D8D5E / 0x557748A4):**
1. c1: result 9 + damage gate ([0x558FAF24]) + AI defender → promote →
   **mark from TCombatData OBJECT list** (GetCount 0x55728BEC/GetObjects
   0x55728BF8 — alive at this point; objects with ([+0x47]&9)==8 = FLED
   not-dead; helper +THero-pref) → token=[unit+0x18] → **BSS MARK TABLE
   @0x558FAFA0** (12×{groupid,token}, ends at BSS page end 0x558FB000 — do
   NOT grow past it), keyed by [group+0x24] id. NO engine fields touched.
2. c2: hook TGuardAreaAGC.ProcessStates state-1 @0x557D8E06 (displaced
   `8b4624 e8faf3f5ff` = list+Validate call, re-emitted): after Validate,
   if group marked → resolve token → pos (unplaced ⇒ 0xFFFFFF matches
   nothing) → sweep target list TOP-DOWN deleting non-matching entries via
   **engine TAIGroupControlTargetList.Delete 0x557381EC** (refcount-correct;
   same thing Validate itself does) → empty list ⇒ vanilla state 2 = walk
   home. Dead token ⇒ clear table entry. ebx/edi dead at hook site (verified:
   first uses at 0x557D8E29/0x557D8E57 are writes); ebp preserved.
3. c3 (home-arrival): clears the TABLE entry (id lookup) — no AG writes.
4. c4 (TAoWHSMap.Create entry, displaced `55 8bec 83c4c8`): wipes the table
   (24 dwords) ⇒ no stale group-id association across new game/in-game load.
Recorder retained @0x558FAF60 (+0x18 sweeps/+0x1C marked/+0x20 kept/+0x24
deleted...); `--read` also dumps the mark table. v4 script backup in session
scratchpad (build_defender_retaliation_v4.py.bak).
EXPECTED: damage+flee ⇒ chase YOUR stack only (splits follow the marked
unit's stack); no damage ⇒ no chase; out of reach/dead ⇒ walk home; arrival
or map load clears the mark.

## ▶ v5.1 (2026-08-14) — mark source corrected AGAIN (recorder-driven)
v5.0 live test: damage gate ✓ and return-home ✓ CONFIRMED; targeting still
failed — recorder showed mark table EMPTY, candidate loop found 0 objects:
**fled units are REMOVED from the TCombatData object list before
CombatExecuted runs** (the result-9 fled-bit scan happens earlier, at
result-assign). v5.1: mark unit taken from the **ATTACKER ARMY on the map**
at combat-data pos2 ([data+0x14/18/1C] = attacker hex; army guaranteed
present at result 9) → unit count = vcall [army vmt+0x54], units via
**TArmy.GetUnits 0x5578309C(eax=army, edx=idx)**, THero preferred, token =
[unit+0x18]. Unit count recorded to REC+0x14. Caves now 841 B
@0x55811120 (c1@0x55811120 c2@0x558112E0 c3@0x558113EF c4@0x5581143C),
**next free AoWEPACK cave 0x55811469**. Applied & disasm-verified; awaiting
the targeting test.

## ✅✅ FEATURE COMPLETE — v5.2 USER-CONFIRMED 2026-08-14 ('everything works correctly now, they went back to normal after returning home'). Ship-worthy; changelog-worthy alongside the tactical damage-response patch.

## ★★★ v5.1 TARGETING CONFIRMED + v5.2 APPLIED (2026-08-14 late night)
**v5.1 user test: TARGETED CHASE WORKS** — defender hunted and killed the
correct (marked) fleeing party. Recorder proof: mark written (group id 0x4F,
token 0xD8, attacker army 1 unit), c2 sweep 5 kept / 60 deleted with
unit_pos == last kept target_pos; after the marked unit died, resolve=nil →
entry cleared. Remaining flaw: after clearing, army stayed GuardArea →
vanilla area-chasing → left home to attack ANOTHER stack ("should go back to
normal").
**v5.2 (APPLIED, disasm-verified; caves 908 B: c1@0x55811120 c2@0x558112F8
c3@0x558113FC c4@0x5581147F, next free AoWEPACK cave 0x558114AC):**
- table entries now 12 B {group id, token, ORIG behavior} (8 entries,
  0x558FAFA0..0x558FB000; offset-stepped loops, stride 12);
- c1 stashes pre-promotion behavior (REC+0x34 scratch) into the entry;
- c2: token==0 = "homebound" state OR resolve-nil (token zeroed, id+orig
  kept) ⇒ matchpos=0xFFFFFF ⇒ ALL targets deleted ⇒ guard walks home even
  after the attacker dies (no mid-field release);
- c3 (home arrival): if orig ∉{0, GuardArea} → **SetBehavior([AGC+0x18]=TArmy,
  0xFF, orig) = demote back to pre-retaliation behavior** (AGC ptr via
  [esp+8]; ⚠ SetBehavior inside MoveExecuterDone = group surgery at a state
  boundary — watch for issues), then clear entry. Map-designed GuardArea
  armies (orig=3) stay GuardArea ✓.
- [agc+0x18] = TArmy confirmed (ProcessStates reads [agc+0x18]→[+0x12] player).
Full loop now: damage+flee → hunt marked stack only → kill it or lose it →
walk home → demote to original behavior → fully passive again.

## ▶ PHASE 2 / v6 APPLIED (2026-08-14) — MULTI-PARTY EMPIRE RETALIATION
Instead of RE-ing empire AG target selection, v6 reuses the entire proven v5
machinery per army: **c1 now promotes+marks EVERY same-player army within
RADIUS=6 hexes (square window, same level) of the defended hex** when the
defender belongs to a REAL AI player ([army+0x12]!=0; independents stay
victim-only so neighboring POI guards don't leave their posts). Each joiner
gets its own GuardArea group + table entry {id, token, orig} ⇒ all converge
on the marked stack, each returns to ITS OWN home hex, each demotes to its
own original behavior.
- **Garrisons/on-structure armies DO join** (user decision: a multi-hex city
  with 3 stacks must retaliate with all of them — refusing would let the
  attacker bait the AI out of a position of strength piecemeal; exposure is
  bounded by mark-only chase + return + demote).
- Table moved & enlarged: **32×12 B @0x558FA800-0x558FA980** (BXL BSS scratch
  region — his features not in our build; clear of flags/recorders at
  0x558FAF20+). Phase-2 scratch @0x558FA980: +0 cx +4 cy +8 cl +0xC player
  +0x10 dy +0x14 dx +0x18 joined-count (printed by --read).
- c1 restructured: token computed FIRST (attacker army @pos2, hero pref),
  then `sub_pm(eax=army)` = GetBehavior→stash orig(stack)→SetBehavior(3) if
  needed→GetGroup→upsert; called for victim + each scan hit. cmp-imm32
  encodings for TABLE_END=0x180 (imm8 overflow), c4 wipes 96 dwords.
- Caves 1153 B @0x55811120: c1@0x55811120 c2@0x558113E4 c3@0x558114EB
  c4@0x55811571; **next free AoWEPACK cave 0x558115A1**. Applied &
  scan-loop disasm-verified. AWAITING TEST: attack a multi-stack AI position,
  damage, flee ⇒ ALL nearby same-player stacks should converge; then each
  returns home & demotes. `--read` shows joined-count + table entries.

## ▶ v6.1 APPLIED (2026-08-14) — LONE-LEADER FIX (5th hook)
v6 test: multi-party works, BUT a LONE LEADER attacker was never chased;
adding any unit to the party made them attack (so NOT a strength eval —
correlation is backwards). RE'd the real gate:
- Targets come from field msg 0x1200 → TArmy.UpdateAITarget @0x55790618:
  gates = GetUnitsConcealedForPlayer / ValidAttackRelation(diplomacy;
  mode-1 msgs bypass war requirement); priority = **TArmy.Leader(0xFF)
  @0x5578DFBC → 300**, TArmy.Hero @0x5578DF44 → 100, else 50 — lone leaders
  are the TOP-priority target class, so valuation wasn't the blocker.
- The blocker: **TGuardAreaAGC.TargetFoundEvent's COMBAT-PREDICTOR gate** —
  it only Adds a target if predictor result ∈ accepted set AND predicted
  value > 0 ([agc+0x158] predictor, results via 0x5572B028 / value via
  0x5572B8AC). Vs a lone (powerful) leader the prediction fails ⇒ target
  never enters the list ⇒ sweep sees nothing ⇒ guard goes home.
**Fix (cave c5 @0x55811571, hook 5 = TargetFoundEvent entry 0x557D8CB8,
displaced `55 8bec 53 56`):** if the candidate target IS this group's marked
target (table lookup → resolve → GetLocation → pos==[tgt+0x30..32]) →
**TAIGroupControlTargetList.Add @0x557381E4 directly + ret 4** (exact mirror
of the vanilla BASE handler = lifecycle-correct), bypassing the predictor
gate — retaliation chases the attacker regardless of odds (user-desired).
Unmarked groups / other targets = fully vanilla. Force-add counter @SCR+0x1C
(`--read` prints 'forceadds').
Caves now 1355 B @0x55811120 (c1@0x55811120 c2@0x558113E4 c3@0x558114EB
c5@0x55811571 c4@0x5581163B), **next free AoWEPACK cave 0x5581166B**; 5 hooks
(+0x557D8CB8). ⚠ revert now zeroes 0x800 (v6 cave outgrew the old 0x400
clear — caused an 'ABORT: cave region not zero' during this swap).

## ▶ v6.2 APPLIED (2026-08-15 early) — ASSEMBLE-BEFORE-STRIKE (6th hook)
v6.1 test: lone leader now attacked ✓; new issue: 3-stack AI city retaliated
with only 2 stacks in the combat (one repositioned before the attack started;
AoW pulls ALL armies ADJACENT to the defended hex into a combat — cohort
members not adjacent at initiation miss it).
**Fix: 6th hook @0x557D8F32** (state-1 attack-move dispatch, 0x31 B displaced
`33d2...ff537c` — the 3×GetTargets(0) coord loads + vcall [agc vmt+0x7C]
move-to) → **cave c6**: if this group is MARKED and already ADJACENT
(dHXtoRad ≤1) to the chosen target, and another same-mark cohort entry's army
(resolved via NEW per-entry ownunit token) sits at dist 2..COHORT_MAX(3) of
the target — **move to OWN hex (wait in place)** instead of attacking, so the
whole cohort assembles and the eventual initiator brings everyone adjacent
into the fight. Not adjacent / no cohort pending / unmarked ⇒ vanilla move.
- Entries now **16 B {id, marktoken, orig, ownunit_token}** (TABLE_END 0x200,
  0x558FA800-0x558FAA00; scratch moved to **0x558FAA00**, +0x20 holds counter);
  sub_pm stores GetUnits(army,0) token; c2/c3/c5/c6 stride 16; c3 clears 4
  dwords; c4 wipes 0x80 dwords.
- **dHXtoRad thunk @0x5570266C: (eax=x1, edx=y1, ecx=x2, push y2) → hex dist**
  (signature verified from 2 callers). [army+0x13/14/15]=live x,y,l.
- Holding consumes the target entry (Delete at resume) but the async finder
  re-feeds each activation and c5 force-adds the marked target past the
  predictor ⇒ holder re-evaluates next activation. If a cohort member never
  closes (blocked), members >3 hexes out don't block the attack.
- ⚠ branch-precheck: range-whitelist 0x557D8F63-0x557D8FF0 added (operand
  bytes of the Delete-call/jmp/state-2 code decode as fake jcc; real disasm
  verified no genuine branches into the displaced range).
Caves 1769 B @0x55811120 (c1@0x55811120 c2@0x558113FD c3@0x55811504
c5@0x55811595 c6@0x5581165F c4@0x558117D9), **next free 0x55811809**; 6 hooks.
TEST RESULT (8/15): 3 of 4 stacks joined — recorder showed all 4 MARKED
(joined=4, 4 table entries) but holds=0: the 4th was beyond COHORT_MAX=3 of
the target, so the adjacent initiator didn't wait; also the tactical/auto
dialog PAUSES the AI turn mid-processing (c2_sweeps was only 1 — remaining
groups act after the combat resolves). ⇒ **COHORT_MAX raised 3→5** (applied,
verified `cmp eax,5` @0x55811789). Accepted trade-off: slow/blocked cohort
members within 5 of the target can delay the strike (marked chase persists).
RETEST: STILL 3-of-4 (holds=0 again) ⇒ found the v6.2 LOOPHOLE: the hold
only governed ALREADY-ADJACENT guards; a non-adjacent marked guard moving to
the target ATTACKS ON CONTACT without consulting the cohort.
**v6.3 (APPLIED 8/15, disasm-verified):** c6 rewritten — marked guard with
pending cohort (member at 2..COHORT_MAX=5 of target):
- adjacent ⇒ wait in place (as before);
- NOT adjacent ⇒ **stop short: move to a FREE hex adjacent to the target**
  (ring search n=1..6 via **CenterHNtoHX thunk 0x55702694: eax=x, edx=y,
  ecx=idx (0=center,1..6=ring1), stack &outX,&outY — push shape verbatim:
  `push esp; lea eax,[esp+8]; push eax`; outs: S0=x, S1=y**; bounds +
  GetFieldXYL + FindChild(0x20217)-free check; no free ring hex ⇒ attack
  anyway). No pending cohort ⇒ vanilla attack move.
Caves 1936 B (c6@0x5581165F..0x55811880, c4@0x55811880), **next free
AoWEPACK cave 0x558118B0**. 4-stack retest of v6.3: assembly mostly worked but a stack OSCILLATED
back-and-forth and the strike slipped to the next turn. Cause found:
**[army+0x13/14/15] position bytes are STALE after moves** — 'wait in place'
walked the guard back to an old cached position and distance checks were
wrong. **v6.4 (APPLIED 8/15, disasm-verified): c6 now fetches the army's LIVE
position via vcall [army vmt+0x98] (same convention as TUnit.GetLocation:
edx=&x, ecx=&y, push &z)**, caches it at SCR+0x28 per activation, and uses it
for the level check, dHXtoRad distance, AND the wait destination. ⚠ NEVER
trust [army+0x13..15] for live position — vcall +0x98 instead.
Caves 1991 B, c4@0x558118B7, **next free AoWEPACK cave 0x558118E7**.
RETEST: STILL JANKY (back-and-forth + indecision persisted) ⇒ **USER CALL
8/15: assemble-before-strike REMOVED entirely (SITE6/c6 gone; hooks back to
5)**. Final shipped behavior = v6.1 semantics: multi-party marking (±6 hexes,
garrisons join, independents victim-only) + targeted chase + predictor bypass
for the marked target + return-home + demote; combat participation decided by
NATURAL ADJACENCY at initiation (some cohort members may miss the first
combat — accepted; better than choreography jank). 16-byte entries kept
(ownunit token now unused). Caves 1391 B, c4@0x5581165F, **next free AoWEPACK
cave 0x5581168F**. ★ LESSON: multi-group movement choreography through
per-activation move substitution fights the engine's flow (stale positions,
paused turns at combat dialogs, activation ordering) — don't retry without a
fundamentally different mechanism (e.g., a real shared multi-army group).

## RE: combat result byte [combat+0x14] (TCombat AND TFastCombat share it)
Assigned @0x557282E4 (eax=combat): aliveCount([combat+0x1C]=attacker list) vs
aliveCount([combat+0x20]=defender list): att>0,def=0 → **3 "Battle Won"**;
att=0,def>0 → **4 "Battle Lost"**; both 0 → **5 "Battle Drawn"**; both >0 →
2 (if not already 7). Then if result∈{4,5} and ANY combat object has the
fled-bit **[obj+0x47]&8** (set by TFleeCA.Execute @0x5572A518) → **result=9**
(= fleeing involved; text falls through to "Battle Drawn").
★ TTerminateCombatTE drives CombatExecuted when a side flees the tactical
map — the hook fires there with ebx=combat valid; do NOT rely on the TE's
move-path fields at that point.
★ A fleeing DEFENDER produces result 3 (attacker holds the field) ⇒ result 9
happens ONLY when the ATTACKER (partly/fully) fled = the exact trigger.
Other writers: 1 @0x5574A8D0, 0 @0x5574ACEF (TE region), fast-combat writers
@0x5572AFC6..0x5572B013 (3/4/2/8; 2="Cannot inflict damage", 8="Cannot breach
wall", resourcestring idents 64828/64829/65370/65371/65372 in .rsrc
STRINGTABLE — decoder recipe in session 8/14).
CombatExecuted @0x557496D4: entry IsClass-skips **TFastCombat** ([0x5571D77C]
classref → jmp exit; our tail hook still runs — safe, +0x14 layout shared);
result==3 branch splits units flagged [unit+0x25]&4 (advance markers) into a
new army via 0x5574A248; [te+0x28]=attacker army HS; [te+0x14]=move-path
XYLList (elem 0 = destination/defender pos, same derivation SetupCombat uses).

## RE: army AI-behavior/group system (AoWEPACK)
- Behavior enum (from *.Behavior methods): 1=Patrol **2=Guard 3=GuardArea**
  4=Scout 5=Refuge 6=Raid(indep) 7=Aggressor 8=Defender 9=Fortify 0xA=Suicidal
  0xB=Passive 0xD=Hunt 0xE=Expander 0xF=Scorcher 0x10=Normal 0x11=Skirmish
  0x12=Transport. Independent classes in IndependentAG unit, empire classes in
  BehaviorAG/MainAG (TAbstractBehaviorAG has CooperateWithGroup — Phase 2 lead).
- Behavior = membership in a TAIGroup: **[unitentry+0x20] = group ptr** (per
  unit!); TArmy.GetGroup @0x5578C4A0 (eax=army, dl=unitmask → common group or
  nil); GetBehavior @0x5578C578 → vcall [group vmt+0xD0]; **SetBehavior
  @0x5578C590 (eax=army, dl=mask, cl=behavior) → CreateGroup @0x55737EB4
  ([M+0x130] global AI control, dl=[army+0x12] player, cl=[army+0x16],
  stack arg=behavior)**: searches [ctl+0x10] class registry by Behavior(),
  INSTANTIATES A FRESH GROUP ([grp+0x24]=new id via 0x55737F38, [grp+0x28]=
  player, [grp+0x34]=param), vcall [grp+0xAC](unit) per masked unit, vcall
  [grp+0x2C] finalize. 4th arg on stack, callee-cleaned (ret 4).
- [army+0x12]=player (0=independents), [army+0x13/14/15]=stored x,y,l,
  [army+0x16]=editor param (sign picks GuardArea/Patrol default),
  [unitentry+0x38]=legacy per-unit behavior byte (GetOldAIBehavior),
  [unitentry+0x25]&4=post-combat advance marker.
- InitializeGroupBehavior @0x5578C630: defaults — indep on structure→Passive
  0xB, else GuardArea/Patrol by [army+0x16] sign; empire→GetRandomGroupBehavior
  ([player+0x88] TAIPlayerControl). [player+0xA7]!=0 ⇒ AI-controlled (SetupCombat
  uses it to auto-resolve AI-vs-AI).
- **TGuardAreaAG**: [ag+0x50]=packed home XYL (init 0xFFFFFF sentinel;
  captured = army's CURRENT pos at first ProcessStates; serialized — 0x32-byte
  block @+0x50 in ReadWrite); [ag+0x4D]=1,[ag+0x4E]=2 params. TGuardAreaAGC
  states ([gc+0x16C]): 0=init (capture home, target-search radius setup
  [+0x132]=7, army speed [+0x23C]); 1=targets→chase moves w/ own strength
  eval (TargetFoundEvent adds distance-scaled score), none→state 2;
  2=**pathfind back to home [ag+0x50..0x52]**, arrived→done (MoveExecuterDone
  resets [gc+0xC]+0x50 to 0xFFFFFF on state-2 completion).

## PHASE 2 original design notes (superseded by v6 above)
On result 9 also record attacker army + hex as a "retaliation marker"; on the
AI player's activation make ALL parties within reach prioritize it — either
temporary shared Hunt(0xD) group assignment or injecting the marker into
empire AG target evaluation (preferred: inherits strength assessment +
CooperateWithGroup massing). Needs RE of BehaviorAG target selection
(TNormalAGC.ProcessStates etc.). True mid-player-turn retaliation rejected
(out-of-turn combat via token system = high desync risk).

Related: [[tcai-defender-hold-response]] (tactical damage-response, same
session), [[keeper2-armycombatmovete-crash]] (TE architecture),
[[exploration-site-fix]] ([player+0xA7], TE observer machinery).


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- ✅ [defender-retaliation.md](defender-retaliation.md) — v5.2 core CONFIRMED 8/14; **FINAL 8/15: assemble-before-strike REMOVED by user call (v6.2-6.4 choreography stayed janky) — shipped = v6.1 semantics: multi-party marks (±6, garrisons join), targeted chase w/ predictor bypass, return-home+demote; adjacency decides combat rosters. 5 hooks, caves 0x55811120-0x5581168F** — lone-leader fix CONFIRMED (predictor bypass c5); + 6th hook 0x557D8F32 'assemble-before-strike': adjacent marked guards WAIT while same-mark cohort members (dist 2-3 of target) close in, so the whole cohort joins the combat (engine pulls all adjacent armies in). Entries 16B {id,token,orig,ownunit} @0x558FA800-0xAA00, scratch 0x558FAA00, dHXtoRad thunk 0x5570266C. 6 hooks. Changelog-worthy. — targeted retaliation rebuilt on v4 recorder data: mark from TCombatData object list (side lists dead at flee; ⚠[AG+0x54] is VANILLA-USED — v3's squat = its crashes), marks in own BSS table 0x558FAFA0 (wiped on TAoWHSMap.Create), filter = engine-API Delete sweep post-Validate in ProcessStates state 1 (empty list ⇒ vanilla walks home), damage gate 0x558FAF24. 4 hooks, caves 0x55811120-0x55811437 — marked-target filter on TGuardAreaAGC.TargetFoundEvent never affected attack choice (real targets come from the un-RE'd TAIGroupTargetSelector/TAIMoveTargetSelector stack) + final attempt hard-CTD'd. v2 (untargeted GuardArea chase+return) was stable & user-confirmed if ever wanted as interim. Full RE bank inside (combat results, AI groups/behaviors, GuardArea state machine, [[side+8]] TList gotcha, [obj+0x47] dead/fled bits). NEXT: RE targeting stack before any retry. Full combat-result enum + TArmy/AI-group RE (SetBehavior creates fresh group; behavior enum 2=Guard 3=GuardArea 0xD=Hunt). Phase 2 = multi-party empire response, designed only.

## 🔨 10/22 GIVE-UP LAYER — `patch scripts/patch_retaliation_giveup_v1.py` (BUILT + scratch-tested, NOT applied; coordinator applies)
User report: retaliating AI vs a target it cannot damage (Incarnate w/ physical immunity) "spams combat" forever —
each combat ends as result 2 ("Cannot inflict damage" = both sides alive; fast-combat finalize 0x5572AF4C writes 2
when both sides survive the round limit), and c5 force-adds the marked target past the predictor every activation.
No pre-combat refusal exists (all 0x5572B028 callers are AI evaluations).
**Layer (live retaliation untouched; both hooks only re-point the existing `jmp cave` rel32, new caves end in jmp old):**
- A @0x55749913 (jmp c1 → cave A 0x55837840): result [combat+0x14]==2 → attacker army = [[TE=[esp]]+0x28] TArmyHS
  (IsClass [0x55713360]) → [hs+0x1C] TArmy → GetGroup(army,0xFF) → [grp+0x24] id in mark table w/ token≠0 →
  ATT[slot] = {id, token} ("attempted"). TE ctx = all machines.
- B @0x557D8CB8 (jmp c5 → cave B 0x55837900): attempted slot (id+token must still match) AND candidate target ==
  marked unit hex (c5's resolve) → run vanilla predictor (0x55738E8C setup + 0x5572B028 run) → scan side-1 list
  [[agc+0x158]+0x10] (items +4, count +8): any obj dead ([+0x50]&2) or [+0x4C] cur < [+0x10] start (both HP×100,
  reset by 0x5572A91C) ⇒ damage possible ⇒ nothing; ALL undamaged ⇒ table token := 0 (shipped homebound state:
  c5 skips, c2 deletes all targets, walk home, c3 demotes). Falls into c5 either way.
- Per group: each cohort member gives up after ITS OWN failed attempt. Lone-leader bypass unaffected (damage possible).
- Fast-combat object facts: [fc+0xC]/[+0x10] = side 0/1 lists; obj [+4] unit, [+0x10] start HP×100 (unit vmt+0xE0),
  [+0x4C] cur HP×100, [+0x50]&2 dead, [+0x14] side. Predictor: group = side 0 (0x5572B204), target hex armies side 1.
- ⚠ 0x558FAF24 damage flag is NOT usable per-combat: TFastCombatUnit shares the 0x55726C58 damage sink, so AI
  predictor sims set it, and only TCombat.Create clears it.
- Zone AoWEPACK 0x55837800-0x55837C00 ('RGU1' header + orig rel32s; borrowtime starts 0x55838000).
  BSS: CNT 0x558FAB00 (+0 attempts, +4 predictor checks, +8 give-ups, +0xC damage-possible), ATT 0x558FAB10..0x558FAC10.
  `--read` dumps them from the running game. Backup `.bak_retgiveup`.
- LIFO: revert this BEFORE build_defender_retaliation.py (its revert would overwrite our site jumps; its --status
  still says APPLIED with this layer on — it only checks the E9 opcode).
- Test: retaliate against an immune target → after the 1st "Cannot inflict damage" combat, --read shows attempts≥1,
  then give-ups≥1 on the group's next activation; the group walks home and returns to its old behaviour.
  If attempts stays 0, the failed attack never reaches CombatExecuted (then a different trigger is needed).

## 🔨 10/22 give-up v2 — `patch_retaliation_giveup_v2.py` (BUILT + scratch-tested; upgrades v1 in place)
v1 live LAN results: gave up only after a 2nd failed attempt, and sometimes "Exception occured during
TArmyCombatMoveTE" + VCL30 IsClass AV (read 6E6E612B = ASCII) — cave A read [TE+0x28] as the attacker TArmyHS;
on the TFastCombat path (CombatExecuted IsClass-jumps straight to the exit) that is NOT a live HS. ⚠ Never use
[TE+0x28] at the 0x55749913 hook. ⚠ On TFastCombat, [combat+0xC] is the side-0 LIST, not TCombatData — c1-style pos2
lookup is only valid for TCombat.
v2 (cave A only, 0x55837840, 325 B; site B restored to `jmp c5`; ATT table + predictor re-check retired):
on result 2 at the combat-end hook, split by IsClass(combat,[0x5571D77C] TFastCombat):
- fast: exact per-combat damage from the real object (side-1 objs all alive & [+0x4C] >= [+0x10]) ⇒ every living
  side-0 obj's army ([obj+4] unit → [unit+4], IsClass TUnitList [0x55710E88]) → GetGroup → table token := 0.
- tactical: attacker army via data pos2 → GetFieldXYL → FindChild(0x20217) → [hs+0x1C] (= vanilla's own
  0x55749833 lookup, valid at result 2) → token := 0 on result 2 alone (round limit; 0x558FAF24 not trusted).
Runs in TE context on all machines ⇒ table identical everywhere. Counters CNT 0x558FAB00: +0 result-2 combats,
+4 fast no-damage, +8 groups sent home, +0xC fast damage-dealt, +0x10 tactical result-2 (`--read`).
Backups .bak_retgiveup (pre-v1) / .bak_retgiveup2 (pre-v2). v1's script aborts on a v2 zone; v2 --revert takes v1 or v2.

## 🔨 10/22 give-up v3 — `patch_retaliation_giveup_v3.py` (BUILT + scratch-tested; upgrades v1/v2 in place)
v2 live: TACTICAL worked (gave up after one try); AUTO crashed at cave 0x5583787A `mov ecx,[eax+8]` with
eax=[TFastCombat+0x10]=4 → TE aborted, [map+0x120] stayed set → every later attack "Combat already created"
(raise 0x557787A9). ROOT CAUSE: ⚠ the real auto-combat class TFastCombat (cell 0x5571D77C, VMT 0x5571D7BC) INHERITS
TCombat (VMT-24 → cell 0x557170D4) = TCombat layout ([+0xC] TCombatData, [+0x14] result). The AI PREDICTOR
([agc+0x158]) is a different class whose objects are TCombatPredictorUnit (cell 0x5571563C) — only those have the
[+4] unit / [+0x10] / [+0x4C] HP×100 layout and [+0xC]/[+0x10] side lists.
v3 cave A (415 B @0x55837840): result 2 → IsClass TCombat (covers TFastCombat) → IsClass [combat+0xC] vs TCombatData
(self-ptr 0x55716E6C, VMT 0x55716EAC) → pos2 x,y ≤ 0xFF, l ≤ 3 → GetFieldXYL → FindChild(0x20217) → IsClass TArmyHS
→ [hs+0x1C] → IsClass TUnitList → GetGroup → token := 0. No damage scan (result 2 = both sides standing).
STAGE breadcrumb 0x558FAB14 (1..9, bit 0x10 OR-ed on clean exit; 0x19 = sent home), last combat 0x558FAB18;
CNT +0 result-2, +4 TFastCombat, +8 sent home, +0xC not-a-TCombat, +0x10 TCombat. Backup .bak_retgiveup3.
