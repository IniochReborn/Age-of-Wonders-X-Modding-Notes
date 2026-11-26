---
name: hero-ai-levelup-chooser
description: "CONFIRMED WORKING 2026-07-24: expanded the AI hero/leader level-up ability chooser (ExecuteUpgradeHeroAI) from vanilla's 3 abilities to 30 abilities + retuned 5 stats, with a two-weight banking/lock-in framework. Caves @0x5580FD40 region in AoWEPACK.dll. Fully tunable via heroai_build*.py. Ability-id map in [[ability-id-map]]."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-25T02:15:17.585Z
---

**GOAL:** AI heroes/leaders leveled up from only 3 vanilla ability options (Parry/DragonSlaying/Spellcasting) + 5 stats. Expanded the pool to **30 abilities** with per-ability weights, and retuned stat weights, so AI heroes gain a rich, weighted spread. CONFIRMED WORKING (start-clean + end-turn OK; all 30 appear per weights).

## THE FUNCTION — `ExecuteUpgradeHeroAI` (AoWEPACK.dll)
Vanilla builds a `TDoubleItemList` (EngineP.dpl) of weighted options, RNG-picks one via `RandomChanceItemB`, applies it, and **LOOPS** (0x55787A40 top) applying MORE upgrades until SkillPoints hit 0 **or the eligibility list is empty**. Key funcs:
- **AddAB** = `Engine.TDoubleItemList.AddAB` thunk 0x55702fcc (eax=list, edx=optId/itemA, ecx=weight/itemB). Grows dynamically (no cap).
- **RandomChanceItemB** thunk 0x5570300c; **Get** 0x55702fe4; **Clear** 0x55702fd4.
- **GetAbility** 0x557501c0 (eax=control, edx=id → eax=ability or null). control = `[[0x558fa044]+0x80]` (GMGR=0x558fa044).
- VMT: **CanExpand** [ability+0xc4], **ExpandCost** [ability+0xc8]; hero **ExpandAbility** [hero_vtable+0x94].
- SkillPoints(hero) = 0x557875c4. Points held in **esi** through the whole function (preserved by all pick calls — verified push/pop esi).
- **DONE 0x55787d2a** = loop-back check: `cmp [edi+8],0; je exit; call SkillPoints; test eax; je exit; test esi; jne 0x55787a40(top)`.
- **EXIT 0x55787d43** = free list (0x557010b8) + epilogue + ret.
- Original apply dispatch: `mov eax,[esp+4](optId)` @0x55787C5C, then `cmp eax,7; ja done; jmp [table]`. Stat handlers @0x55787c90/ca0/cad/cba/cc7 (ATK/DEF/RES/DMG/HP), each `jmp DONE`.

## THE MECHANIC — two-weight banking + lock-in
Each ability carries **two weights**: **unaff** (banking — used while hero can't afford it) and **aff** (lock-in — used the instant it's affordable). Always in the pool if `CanExpand` (learnable/not-maxed). Affordability = `esi(points) >= ExpandCost`.
- **cave_elig** (replaces the 3 hardcoded ability options): loop TABLE; per id → GetAbility (null→skip) → CanExpand (false→skip) → ExpandCost → pick aff or unaff weight → AddAB(list=edi, optId=id, weight).
- **cave_apply** (replaces `cmp eax,7`): optId 0–4 → original stat handlers; else (ability id) re-check affordability: **affordable → ExpandAbility → jmp DONE (loop-back, apply more)**; **unaffordable → jmp EXIT (bank the rest, terminate)**.
- ⚠️ **The exit-on-unaffordable is CRITICAL**: always-add keeps the list non-empty, so vanilla's "empty-list → exit" never fires; without exit-on-save the loop **infinite-loops** when a hero has leftover points < cheapest option. (This was the "new game crashes / end-turn hangs" bug.)
- **Dynamics:** unaff drives accumulation (high-weight expensive options get picked while unaffordable → bank → save toward them). aff makes an option grabbed the instant affordable (vanilla did this for Spellcasting only, 9999 affordable/100 unaffordable — we generalized it). Weights are relative (its weight ÷ sum of offered), 1–65535 (word).

## CAVES / HOOKS (AoWEPACK.dll, PIC-safe)
- **cave_elig @0x5580FD40**; then **TABLE_ID** (1 byte/id), **TABLE_UN** (word), **TABLE_AF** (word) — 3 parallel arrays indexed by loop idx; then **cave_apply**. End ~0x5580FEE8 (**limit 0x5580FF00** — ~24B headroom at 30 abilities; near full).
- PIC: `push ebp;call gd;gd:pop ebp;sub ebp,gd` → ebp=delta; `[ebp+0x558fa044]` for GMGR, `[ebp+TABLE_x]` for tables. rel32 for GetAbility/AddAB/DONE/EXIT/PICK.
- **Hook1 @0x55787B15** (`8b 45 00`) → `jmp cave_elig`. **Hook2 @0x55787C60** (`83 f8 07`) → `jmp cave_apply`.
- **Stat weight immediates** (edited in place, low byte after `b9`): ATK@0x55787A67=100, RES@0x55787AB4=50, DMG@0x55787ADC=50, HP@0x55787B04=100. **DEF@0x55787A8C stays 0xff(255)**. Stat point-gates UNTOUCHED (ATK/RES/HP `cmp esi,5`; DEF/DMG `cmp esi,0xa`) — this is why DEF can lag ATK (offered less often); folding stats into the two-weight pool is the fix if wanted.

## BUILD / TUNE
- Script: **`patch scripts/heroai_build.py`** (final = heroai_build11.py; keystone-engine + capstone). Rebuilds fresh from **`AoWEPACK.dll.bak_preheroai`** each run. Two-pass assembler resolves TABLE VAs. Edit the `ABILS=[(id,"name",unaff,aff),...]` table + `STAT` weights, re-run. Dedup + cave-overflow asserts.
- **Backup: `AoWEPACK.dll.bak_preheroai`** (= pre-feature state).

## CURRENT WEIGHTS (2026-07-24, confirmed working)
Stats: ATK 100(≥5) · DEF 255(≥10) · RES 50(≥5) · DMG 50(≥10) · HP 100(≥5).
Abilities (id · unaff/aff): Archery 0x16 5/5 · Charge 0x6F 25/25 · Cold Immunity 0x08 5/5 · Cold Strike 0x0F 25/500 · Death Immunity 0x0B 5/5 · Death Strike 0x12 5/5 · Dominate 0x1C 10/100 · Doom Gaze 0x37 25/250 · Extra Strike 0x73 25/50 · Fire Immunity 0x07 5/5 · Fire Strike 0x0E 10/10 · First Strike 0x74 250/5000 · Frost Bolts 0x7A 5/5 · Healing 0x2F 50/50 · Hero Slaying 0x38 75/150 · Holy Immunity 0x0C 5/5 · Holy Strike 0x13 5/5 · Leadership 0x2E 50/50 · Lifestealing 0x76 25/75 · Lightning Bolts 0x7B 5/25 · Lightning Immunity 0x09 5/5 · Lightning Strike 0x10 250/5000 · Magic Bolts 0x79 10/10 · Marksmanship 0x20 5/5 · Monster Slaying 0x70 25/25 · Parry 0x71 30/30 · Poison Strike 0x11 10/10 · Round Attack 0x72 5/5 · Seeker Bolts 0x3A 25/250 · Spellcasting 0x34 250/2000.
