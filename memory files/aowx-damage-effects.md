---
name: aowx-damage-effects
description: "Combat damage-effect plumbing in AoWEPACK (ExecuteDamageEffectsRole branches, effect bitset, Burning/Stunned application) + the lightning-ignites-machines patch (2026-09-13)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2eb9e75f-d259-4a21-8f8a-bfb22139df71
  modified: 2026-09-16T00:00:15.459Z
---

**Effect landing chain (AoWEPACK.dll, verified 2026-09-13):** `TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4`
walks the surviving damage-type set in SI (`si = ~GetDamageTypes & incoming`; Delphi set over TDamageType:
bit0 fire, 1 cold, 2 lightning, 3 magic, 4 poison, 5 death, 6 holy, 7 physical, 8 wall, 9 none; bits 10-15
unused) and accumulates result bits in BP, returned in AX → `TDamageCA.Generate @0x55729C20` stores
`word [CA+0x13]` → `TDamageCA.Execute` → `TAbstractUnit.ExecuteCombatDamageEffects @0x55781ED8`: bit0 →
ExpandAbility(0x7F Burning) + RemoveAbility(0x5F Frozen) (@0x55781F0D), bit2 → Stunned, etc. Result-bit
constants: fire 0x0001 @0x55781E10, lightning/stun 0x0004 @0x55781E14. Lightning branch @0x55781C4B:
GetUnitType (VMT+0x114 → AL byte; TUnit.GetUnitType 0x55782808 = `[eax+0x40]+0x30`; 2 = machine; heroes
return 0) → machine = dead exit to 0x55781CAB; GetAbilityEnabled(9 Lightning Immunity) exits; Lightning
Protection ([esp+2] bit 4) adds +3 to cached RES [esp+4]; the roll in THIS build is our earlier cave
(`push 2; push 6; call 0x5580FC00` @0x55781C90, replacing vanilla `mov eax,6; sub eax,edi; call HitRole`).
⚠ `mov ax,[0x55781E14]` @0x55781CA0 carries a .reloc at 0x55781CA2 — never hook there.
TFastCombatUnit shares +0x118/+0x128 → auto-combat covered by the same code.

**patch_lightning_ignites_machines_v1.py (applied 2026-09-13, backup `.bak_lightning_ignites`, caves
0x55813910–0x55813955):** port of BXL's build_lightning_ignites (untested by him). B1 @0x55781C5C (9 B):
clear SI bit 15; machine && !GetAbilityEnabled(7 Fire Immunity) → set SI bit 15 (mark) and take the
normal roll; fire-immune machine → vanilla dead exit. B2 @0x55781CA6 (5 B): mark → `mov ax,1` (fire bit)
before `or ax,bp`. Result: machines get Burning (no on-hit fire damage) with the stun chance; never
stunned. User to play-test with Lightning Strike/lightning attacks on catapults etc.

**Strategic-map sibling (2026-09-15):** `TAbstractUnit.ExecuteDamageEffects @0x55781E28` (eax=unit, dx=mask; strips
immunity only, then ExpandAbility 0x60 Poisoned / 0x5D Cursed / 0x62 Vertigo for bits 0x10/0x20/0x40) is what
`ExecuteStormDamage 0x55780668` (call @0x55780811, only when base damage > 0) and `TPoisonPlant.TriggerArmyDamage`
(call @0x557C41D2) use — no RES roll, no protection. `patch scripts\patch_storm_effect_roll_v1.py` (port of BXL's
build_stormeffectroll, APPLIED to 410, backup `.bak_stormroll`, UNTESTED in game): entry hook → cave 0x55816180
(27 B, rel32 only): `and dx,0x70; call ExecuteDamageEffectsRole; mov dx,ax` then replays the prologue → only bits
that passed the roll are applied. The Role function's rolls in our build go through the roll cave 0x5580FC00
(args: push effect-idx, push strength → table lookup [0x558FA810 + idx*4] = weakness ability id → unit VMT+0x88
enabled → RES −3; then HitRole(strength − RES)); protection bonus is +3 (0x55781CD0). Safe off the tactical path
(no combat-log/ring state, unlike BXL's build where it needed build_effectroll_tacticalgate). **Debuff sources (2026-09-15, `patch_storm_debuff_sources_v1.py`, backup `.bak_stormsrc`, requires the roll patch):**
vanilla `ExecuteStormDamage` dispatch @0x557807EB only handles storm idx 2 Death (mask [0x55780840]=0x20) and
idx 6 Pestilence ([0x55780844]=0x10) — **Divine Storm (idx 3) has NO debuff in vanilla** (BXL added it in Ziggurat;
his "Divine → 0x40" table row is his build). Hook → cave 0x558161C0 adds idx 3 → 0x40 Vertigo. `THolyGround.
TriggerArmyDamage 0x557C7E18` / `TUnHolyGround 0x557C8FA4`: alignment gate (VMT+0xFC vs sets 0x558E9098 evil /
0x558E9418 good, `cmp al,6` skip), ability-1 exemption, ExecuteDamageRole (holy 0x40 / death 0x20), SetHitPoints
`call [ecx+0xE4]` @0x557C7F9E / @0x557C910B — vanilla applies no debuff; caves 0x55816200 / 0x55816240 replay the
call, then `GetHitPoints<>0 → ExecuteDamageEffects(0x40 / 0x20)` (Poison Plant's idiom @0x557C41BB). Poison Plant
is dormant when `[plant+0x18]` (terrain byte) is 3 Snow or 5 Wasteland — check fn 0x557C3F90, vanilla, untouched.
Vertigo gate `GetUnitType==2` is VMT+0x114: TUnit 0x55782808 (`[unit+0x40]+0x30`), THero/TLeader 0x55786C38 (returns 0).
⚠ Delphi VMT layout in this dll: class-name pointer at **VMT−0x20** (not −0x2C); TUnit VMT 0x55710CAC, THero
0x55711FEC, TLeader 0x55712238, TCombatUnit 0x55715A94. Next free cave in AoWEPACK.dll: **0x55816280** (zero to 0x55860000).

**Why:** any future damage-type/status change (e.g. new effects, machine/undead exemptions) goes
through this exact branch structure. Related: [[aowepack-ability-system]].
