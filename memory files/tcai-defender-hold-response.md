---
name: tcai-defender-hold-response
description: "Defender-AI passivity vs infinite-range spells: root cause = TCAI [cai+0x34] 'battle joined' threat-scan failing; FIX APPLIED 2026-08-14 (build_defender_damage_response.py, AoWEPACK+AoWTCPCK): defending side that takes unit damage becomes 'threatened' and engages. AWAITING USER TEST. Full corrected TCAI RE inside."
metadata: 
  node_type: memory
  type: project
  originSessionId: c789e62f-993f-417b-8ab1-88a32d8c934d
  modified: 2026-08-14T23:20:11.222Z
---

# Defender AI responds to damage — APPLIED 2026-08-14, awaiting in-game test

**User request:** attacker with infinite-range spells can bombard the defending
AI forever; defenders stand still and die. Confirmed on 1.37.404 in BOTH open
field and siege.

## ✅ FIX: `patch scripts/build_defender_damage_response.py` (--apply/--revert/--status)
Backups `AoWEPACK.dll.bak_defresp` + `AoWTCPCK.dll.bak_defresp`. Applied &
disasm-verified 2026-08-14. Four coordinated patches:
1. **Per-side damage flags** in AoWEPACK BSS: 0x558FAF23 (side 0/attacker),
   0x558FAF24 (side 1/defender) — next to the AI-spell per-combat flags.
2. **Cave @0x558110C0 (94 B, next free AoWEPACK cave 0x5581111E)** hooked into
   BOTH universal damage sinks (entry hooks, displaced bytes replayed):
   - 0x55726C58 = shared vmt+0x124 damage impl (eax=victim, edx=dmg) — melee/
     combat damage, ALL classes (walls incl., filtered in cave);
   - 0x55724C1C = TCombatUnit vmt+0x128 impl (eax=victim, dx=dmg) — spell/CA
     damage routed to the TUnit (0x55781ED8).
   Cave: dmg>0 → victim IsClass TCombatUnit via wall-fix helper 0x55810F00
   (walls do NOT trigger → catapult-vs-wall pacing unchanged) → GetSide
   0x55726660 (al; 2=detached, guarded `cmp al,1; ja`) → flag[side]=1 (PIC).
3. **TCombat.Create clear block @0x5580DCF4 rewritten in place** (21 B): three
   byte-clears → `mov dword [delta+0x558FAF20],0` + byte-clear 0x558FAF24 +
   4 NOPs ⇒ all 5 BSS flags reset each tactical combat. (⚠ the
   ai-combat-spell script's byte expectations there are now stale.)
4. **AoWTCPCK: EvalBattle phase-0 `[cai+0x34] init` @0x4185A1 (16 B:
   8b45fc 80780400 0f94c0 8b55fc 884234) → jmp cave @0x438620 (54 B, next
   free AoWTCPCK cave 0x438656)**: side0→1 (vanilla), side1→damage-flag[1],
   side>1→0. Cross-module flag read PIC: delta via call/pop, IAT slot
   [0x46E8D4] = &`AoWE.AoWHSMap` var (static **0x558FA040**, verified via
   export table) → flag = ptr+0xEE4. Resume 0x4185B1.
MP-safe: damage lockstep on all machines; EvalBattle gated to the AI-owner
machine, decisions replicate as tokens. Fast combat sets flags harmlessly.
Script prechecks: byte asserts, .reloc scan (⚠ basereloc data-dir = opt+0x88),
branch-target scan (ignore sources inside replaced ranges), cave-zero check.

## ★★ CORRECTED TCAI MODEL (2026-08-14 — supersedes the first-pass reading)
AoWTCPCK `AoWTC.TCAI` (VA=file+0x400C00). ONE instance per combat map
@[combatmap+0x118], created in map-init (0x41B510); [map+0x11C]/[+0x120]/
[+0x124] = TLists created alongside. Turn driver: fn @0x41C440 (checks
[map+0xA4] player is AI via [player+0xA7], comm-control remote check, then
dispatch on [cai+0x36]: 0→BeginTurn 1→ContinueTurn) → EvalBattle @0x418170,
phase machine [cai+0x1C]: {0:0x4181F3 CreateUnitList+threat-scan, 1:0x418AE5
per-unit Eval+CreateMoveList (calls CheckUnit), 2:0x419541 WallCrush,
3:0x419C27 BuildGroupBonuses, 4:0x419EE0 AddGroupBonuses(+flee/regroup),
5:0x41A4AA PickMove}.
- **[cai+4] = side of the acting combat player** = [combatplayer+0xA], fetched
  @0x4182B0 via TCombatPlayerList.GetPlayers([combatdata+0x38],[data+0x31]).
  **Side 0 = ATTACKER, side 1 = DEFENDER.** TCombatObject.GetSide @0x55726660
  returns the same +0xA byte ([obj+0x45]=combat player idx; 0xFF ⇒ returns 2).
- **[cai+0x34] = "battle joined / we are threatened"** (NOT "is defender").
  Init @0x4185A1: `= (side==0)` — attackers always engaged. For defenders the
  phase-0 pair loop (own×enemy, 0x41861E-0x418A98, short-circuits once set)
  tries to set it: per enemy, distance dHXtoRad; then
  (a) ability scan ids 0x16..0xA9 via [enemy_obj vmt+0xA8], classified by byte
      table @file 0x467248[id], range tier via [ability vmt+0x84] (5→12 hexes,
      4→8, else 4), dist≤tier + [vmt+0xF0] damage>0 (+ some classes need
      EvalPath>0) → threatened;
  (b) **ability 0x34 = Spell Casting special case**: enemy [unit+0x4C] IsClass
      THero ([0x46E914]), [hero+0x24]=owner player (≤0 ⇒ skipped!), loops
      spell ids 0..0x83: spell-class table @file 0x4672F4[id]≠0, hero's player
      KNOWS it ([M+0x140]→GetPlayers→[+0x54]+0x30 IntegerList), combat-castable
      (flag bit 2 of [spell vmt+0x7C] props), **range byte ≥ dist OR ==0xFF
      (infinite handled!)**, [spell vmt+0x8C] damage-vs-unit >0, then most
      classes ALSO need **EvalPath(0x414DA8) > 0** → threatened.
  ⇒ vanilla DOES try to catch infinite-range spells but fails in practice
  (untested which link breaks: the [hero+0x24]≤0 guard, spell-class table,
  known-spell lookup, or EvalPath≤0 e.g. through walls). Our fix bypasses the
  scan: damaged ⇒ threatened.
- **Passivity mechanism**: CheckUnit's four approach-move families
  (0x415773/0x416BBD/0x417279/0x417E7C) gate on
  `[cai+0x34] OR ChargeFromPos(unit)` — not threatened ⇒ no approach moves ⇒
  units only react in-range ⇒ "waiting". Same mechanism open field AND siege.
  ChargeFromPos @0x413778: [unit+0x46]>>4 ≠0 ⇒ true; side==1 with walls
  intact ([data+0x4C]&&![data+0x4D]) ⇒ true; else wall-side-sections array
  [combatmap+0x12B..0x130] open-sides logic.
- **[combatmap+0x124] = TFleeLocation list** (FleeLoc.TFleeLocation.Activate
  @0x431420 self-registers; [fleeloc+0x14]=0x32 if [map+0x3C]&2). Phase 4 tail
  (side-0/ATTACKER only, @0x41A163-0x41A334): flee moves score
  0x68E7780(110M)−10×dist for units with [cai+0x35] OR [unit+0x66].
  **[cai+0x35] = attacker-facing-intact-walls** (= side==0 && [data+0x4C] &&
  ![data+0x4D], sole reader 0x41A21E) — withdraw-eligibility, NOT a
  defender-hold flag. [unit+0x66] init = (side==0); phase-4 first half
  (0x419EE0+, heroes only) = UnitSafe-based regroup-to-safer-friend-position,
  else side-0 hero marks +0x66=1 (flee eligible).
- UnitSafe @0x4138B8 = threat-balance score (own strength − dist-weighted
  enemies <15 + friends). tcDVtoDEV/MultDEV = eval scaling (MultDEV percent:
  hero 50%/other 100% @0x415729; 10% vs breached walls multi-something
  @0x41722F).
- TCombatData: [data+0x31]=current combat player idx, [+0x38]=combat player
  list, [+0x4C]=walls present, [+0x4D]=walls breached (serialized tags
  0x1B/0x1C). ⚠ TCombatWall's OWN +0x4D = wall HP byte — different object.
- Damage architecture (AoWEPACK): DoDamage export 0x55726B1C is a wrapper
  (eax=?, edx=victim, ecx=dmg; vcalls [victim vmt+0x124]). vmt+0x124 common
  impl **0x55726C58** for ALL combat classes (asserts dmg 0..0x31, vcall+0x88
  GetHits, +0x8C SetHits). vmt+0x128: units→**0x55724C1C** (→TUnit dmg
  0x55781ED8; used by TDamageEffectCA.Execute = spells), walls/base→0x55726B04
  stub. VMTs: TCombatObject 0x557158EC, TCombatUnit 0x55715A94, TFastCombatUnit
  0x5571D4BC, TCombatWall 0x55715C40.
- Phase-0 spotted-scan (unchanged by this fix): units skipped unless the
  seated human explored ≥1 of ~20 hexes around them; gated on
  [combatmap+0xC9]≈ExplorationEnabled; the shipped engage-immediately patch
  (@0x4183B7 `mov al,1`, since 402) already forces all-spotted in every
  tactical combat — proven NOT sufficient for engagement (user test 8/14):
  being in the lists ≠ generating approach moves.

## Expected new behavior (to test in-game)
- Bombard AI defenders from out of reach (open field or siege): after the
  FIRST unit takes damage, on the AI's next turn its whole side becomes
  "threatened" → generates approach/attack moves like an attacker → engages.
- Wall damage alone does NOT trigger. Vanilla behavior otherwise unchanged
  (attackers unchanged; defenders still ambush-wait until damaged/threatened).
- If defenders behind fully-sealed intact walls can't path out, they may still
  hold (no path = no move) — acceptable; gates/breaches open the sally.

Related: [[exploration-site-fix]] (engage-immediately patch, EvalBattle entry
RE), [[ai-combat-spell-once-per-combat]] (⚠ its clear-block bytes rewritten by
this patch), [[keeper2-armycombatmovete-crash]] (wall-fix helper 0x55810F00
reused; DoDamage region context), [[bxl-reference]].


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- ✅ [tcai-defender-hold-response.md](tcai-defender-hold-response.md) — **COMPLETE, user-confirmed 8/14**: `build_defender_damage_response.py` (AoWEPACK caves 0x558110C0 + AoWTCPCK 0x438620) — defending side that takes unit damage becomes "threatened" ([cai+0x34]) → engages; fixes infinite-range-spell stalling in open field AND siege. Corrected TCAI RE: side0=attacker, [cai+0x34]=battle-joined threat scan (vanilla handles range-0xFF spells but fails), [map+0x124]=FLEE locations, [cai+0x35]=attacker-withdraw flag. ⚠ new next-free caves: AoWEPACK 0x5581111E, AoWTCPCK 0x438656; TCombat.Create clear block rewritten (5 flags).
