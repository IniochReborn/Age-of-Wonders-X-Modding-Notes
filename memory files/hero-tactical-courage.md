---
name: hero-tactical-courage
description: "✅ BOTH CONFIRMED 2026-08-15: (1) hero/leader melee courage (3 tunable bytes: self-retaliation fear hero x2->x1, leader net x4->x2, hero melee 50%->80%); (2) AoO awareness (all units: provoking moves scaled to 60% pre-sort). Full TCAI move-pipeline RE (move records, phase-3 bonuses, phase-4 sort, phase-5 dispatch). Tactical-only."
metadata:
  type: project
---

# AI hero/leader tactical-combat courage (2026-08-15)

USER PROBLEM: AI heroes/leaders uselessly passive in tactical combat when out
of mana/casting: with an ADJACENT enemy they move instead of attacking, eat
the opportunity attack (the AI does not model AoO at all), and end turns
doing nothing. Combat SPELL usage is fine ("decent now") — the pathology is
the no-casting fallback. Fast/auto combat must not change.

## ROOT CAUSE (AoWTCPCK TCAI; all tactical-only)
- **tcDVtoDEV @0x413664** — THE attack scorer:
  `DEV = (val2(target)*attackDV - val2(SELF)*retaliationDV)/100`
  where val2 = vcall [obj+0x5C] unit value, x2 if [obj+0x4C] IsClass THero
  ([0x46E914]), x2 AGAIN if TLeader ([0x46E910] — leaders net x4). Applied to
  BOTH sides: target-side amp = good (killing enemy heroes pays); SELF-side
  amp = hero/leader retaliation-fear multiplier -> own-hero melee almost never
  scores positive. Args confirmed at Melee Check call site 0x415535:
  callee [ebp+8]=TARGET (val x attackDV), [ebp+0xC]=SELF (val x retaliation);
  SELF identified by the [unit+0x66] flee-byte write on [caller ebp+0x14].
  Self-amp imm bytes: hero @0x41371B, leader @0x41373E (both imul ...,2).
  Target-amp imms @0x4136A8/0x4136CB (LEAVE — they drive hero-hunting).
- **Melee Check hero 50% @0x41572C** (mov [ebp-0x14],0x32 vs 0x64 non-hero;
  feeds MultDEV) — the ONLY hero percent penalty: spell/touch/ranged have
  none (their hero refs at 0x4155AC-pattern are a hero-only BONUS sub-block,
  0 for non-heroes; 0x0A=10% sites 0x41722F/0x417D0A are wall-context).
- AoO is simply not modeled anywhere in move costing.

## ✅ PATCH APPLIED (awaiting test): `patch scripts/build_hero_melee_courage.py`
(--apply/--revert/--status; backup AoWTCPCK.dll.bak_herocourage; 3 tunable
imm bytes, context-checked):
- hero self-amp 2 -> **1** (@0x41371B)
- leader extra self-amp 2 -> **2** kept (leaders net x2 instead of x4 —
  leader death loses the game, moderated cowardice is correct)
- hero melee move pct 0x32 -> **0x50** (80%)
Expected: out-of-mana heroes/leaders attack adjacent enemies instead of
wandering into AoOs; ranged/spell behavior unchanged; enemy-hero targeting
unchanged. If still passive: next suspects = phase-4 hero regroup moves
(UnitSafe-scored, compete with attacks) and the hero-only bonus sub-blocks.


## ✅ COURAGE PATCH USER-CONFIRMED ("an improvement") + AoO AWARENESS APPLIED (2026-08-15)
Follow-up: AI still walked away from an adjacent swordsman (eating the AoO)
to attack an IDENTICAL one farther off — wanted a PROPORTIONAL AoO bias.
**NEW RE — the move pipeline endgame:**
- [cai+0x14] move records: +4 type (0=move, 1=touch, 2=melee, 3=approach,
  4=temp-deleted-in-phase-4-tail, 5=ranged/cast-from-position), +0xC VALUE
  (the decisive score), **+0x10 = group-support bonus** (phase 3 computes:
  moves with destinations near other units' moves get bonuses; phase-4 tail
  adds bonus/4 into value for |value|<100M), **+0x1C/+0x1E = destination x/y
  words** (what phase-5 feeds SetDestinationPos; +6/+8 are NOT the dest!),
  +0x14 unit HS (live pos via vcalls +0x74=X/+0x78=Y).
- **Phase-4 tail @0x41A3C0 = descending INSERTION SORT by [move+0xC]**
  (TList thunk 0x401554 move-item); phase 5 executes list[0] best-first
  (type dispatch table @0x41A4E8: 0/5→0x41A500, 1→0x41ABD0, 2→0x41A9EA,
  3→0x41AE24, 4→0x41AEF1).
**✅ PATCH APPLIED: `patch scripts/build_ai_aoo_awareness.py`**
(--apply/--revert/--status; backup AoWTCPCK.dll.bak_aoo; hook @0x41A3C0
(12 B sort prologue) → cave @0x438660 (293 B, fully rebase-proof: no
absolutes; **next free AoWTCPCK cave 0x438785**)): pre-sort pass over the
move list — unit adjacent (dHXtoRad≤1) to a LIVING enemy ([e+0x47]&9==0):
types 1/2 provoked iff dist(unit,dest)>1 (attacking the adjacent enemy = no
AoO), types 0/3 provoked iff dist>0, type 5 never ⇒ positive value ×
**AOO_PCT=60**/100 (tunable; widening imul — values reach 100M, 32-bit
imul would overflow). Proportional ⇒ never freezes: equal targets → adjacent
wins; sufficiently bigger prize still pulls the unit out.
**USER-CONFIRMED WORKING 2026-08-15** (adjacent-swordsman scenario resolves
correctly). Then v3 (raw-value pen + own-HP frailty) FAILED live: recorder showed real
unit values are ~300 (swordsman) / ~612 (cavalier) so pen always maxed, the
frailty read was garbage (**hits/maxhits are FIELDS [o+0x88]/[o+0x84], NOT
vcalls**), and -- decisive -- **move values are a value^2-ish currency
(~98K approach on a swordsman) while melee vs a defended equal target scores
NEGATIVE (~-128 retaliation fear): percent scaling can NEVER flip that; it is
also exactly why vanilla walks away.** Then v4 (subtractive pen + safe-attack
boost in the move-value currency) still failed on identical cavaliers: CHK
instrumentation @0x415551 proved **target selection compares tcDVtoDEV-scale
scores per candidate and breaks ties by list order** (294 vs 294 -> far one
picked; the adjacent-attack move is then never generated at all).

**FINAL = v5, USER-CONFIRMED 8/15 ("everything seems to work correctly"),
`build_ai_aoo_awareness.py` (--apply/--revert/--status/--read):**
1. **Selector bias** hook @0x415551 (CheckUnit melee score store, 6B
   `89459c8b4510`) -> cave2 @0x438a70: adjSum = sum over living enemies
   adjacent to self of min(value,RAW_CAP); if evaluated target NOT adjacent:
   score -= adjSum/**CHK_DIV=4** (~75/swordsman, ~153/cavalier in DEV
   currency). Ties break toward the adjacent enemy; better far targets still
   win. CheckUnit RE: [ebp+0x14]=self obj, [ebp+0x10]=target obj, [ebp-4]=cai,
   [ebp-0x64]=score, [ebp-0x68]=path list (count<=1 -> no move), [ebp-0x89]=
   can-strike-this-turn; selector phase calls CheckUnit pathless (pathcnt 0,
   score only), then re-calls with a real path for the CHOSEN target to emit
   moves (melee = move+attack in ONE type2 move, dest=attack hex).
2. **Move-list pass** hook @0x41A3C0 (12B sort prologue) -> cave @0x438660:
   per move classify safe attack (type1/2 dist<=1, type5) vs provoked
   (type1/2 dist>1, type0/3 dist>0); threatSum = sum adj living enemies of
   min(raw,RAW_CAP)^2 (~90K/swordsman); f100 = 200-ownHP% (FIELD reads);
   eff = threatSum*f100/100; safe: val += min(eff*BOOST_PCT/100, BOOST_CAP);
   provoked: val -= eff*PEN_PCT/100, floored at val*MIN_KEEP/100 only if val
   was positive (negatives sink, no floor). The BOOST is what lets melee-
   adjacent (negative base) outbid walk-off (+98K); the CAP stops suicide
   charges into adjacent dragons.
Constants: PEN_PCT=80 BOOST_PCT=80 BOOST_CAP=150000 MIN_KEEP=25 RAW_CAP=2000
CHK_DIV=4. **SHIPPED BUILD = RECORD=False (re-applied 8/15): caves 0x438660
(639B) + 0x4388e0 (281B); next free AoWTCPCK cave 0x4389f9** (revert clears
0x800 from 0x438660). All widening imuls (values reach 100M).
Recorder recipes kept in-script (flip RECORD=True + re-apply to re-instrument):
diagnostic ring @0x46c100 in TCPCK BSS page slack (BSS vsz ends 0x46c0a1,
page runs to 0x46d000; +0 count +4 passes, 100x32B records; --read attaches
live); ring in own-module BSS slack via call/pop delta; CHK records marker
0xEEEEEEEE.

## RE nuggets
- [0x46E904]=TCombatUnit, [0x46E914]=THero, [0x46E910]=TLeader classref slots
  (TCPCK imports). [0x412B0C] classref used as tcDVtoDEV pre-check.
- CheckUnit block bounds via error-string refs: Melee ..0x4158C6, Spell
  0x4158E0-0x416D87, Touch ..0x41740B, Ranged ..0x418043.
- CheckUnit stack args: [ebp+0x10]=target enemy obj, [ebp+0x14]=self obj.
- TMeleeRound.GetAttackerDV thunk 0x40281C / GetDefenderDV 0x402824 feed
  tcDVtoDEV (retaliation = GetDefenderDV).

Related: [[tcai-defender-hold-response]] (TCAI phase RE), [[defender-retaliation]],
[[ai-combat-spell-once-per-combat]] (player combat-spell AI, separate system).


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- ✅ [hero-tactical-courage.md](hero-tactical-courage.md) — **BOTH CONFIRMED 8/15**: courage + AoO awareness **v5** (build_ai_aoo_awareness.py, 2 hooks: selector bias @0x415551 score−=adjSum/4 for non-adjacent melee targets — fixes tie-break picking the FAR twin — + move-list pass @0x41A3C0 boosting safe attacks / sinking provoked moves in the value² currency w/ own-HP frailty; caves 0x438660-0x4389f9, **recorder stripped, release-ready**; full CheckUnit/selector/move-pipeline RE + live-recorder recipe inside). Courage: 3 tunable bytes (tcDVtoDEV self-retaliation fear hero×2→×1, leader net ×4→×2 @0x41371B/0x41373E; hero melee move 50%→80% @0x41572C). ⚠ v1/v2/v3/v4 histories in file are superseded — v5 section is authoritative. Tactical-only.
