---
name: aowx-re-reference
description: "Core RE reference for our binaries — Delphi convention, ability IDs, StrikeEnhancement framework, key functions, AD/RS cave internals, GlobalSpells hierarchy, key globals"
metadata: 
  node_type: memory
  type: reference
  originSessionId: bd10b7eb-475b-4439-8297-a7be881f5568
  modified: 2026-07-20T17:24:08.770Z
---

# AoWx RE Reference (our binaries)

See [[active-patches]] for patch tables/free space; [[bxl-reference]] for BXL's decoded knowledge (combat math, BSS scratch, MP RNG rules, etc.).

## DLL Image Bases & Section Layout
- **AoWEPACK.dll**: ImageBase=0x55700000, CODE rawoff=0x400, RVA=0x1000 → VA = file_off + 0x55700C00
- **AoWTCPCK.dll**: ImageBase=0x400000, CODE rawoff=0x400, RVA=0x1000 → VA = file_off + 0x400C00
- **HSEPack.dpl**: ImageBase=0x55600000 → VA = file_off + 0x55600C00

## Delphi Calling Convention
- EAX=self, DL=byte param; EAX/ECX/EDX volatile; EBX/ESI/EDI/EBP preserved; return in EAX
- Vtable calls: `mov eax,[obj]; mov ecx,[eax]; call [ecx+N]`

## Animate Dead Cave (AoWEPACK.dll 0x10C20D) — v3, VERIFIED
- RDTSC mod 100 RNG; 293-byte group lookup table (position-independent: CALL/POP trick)
- Groups: 1=HORSE(→200,80%), 2=MUMMY(→223,80%), 3=MUMMY_SUB1(→206,10%/223,72%/201,18%), 4=MUMMY_166(→204,10%/223,72%), 5=MUMMY_SELF(→223,50%), 6=HORSE_SELF(→200,50%), 7=WRAITH(→206,80%), 8=WRAITH_I1(→206,20%), 9=WRAITH_I2(→206,10%), 10=WRAITH_SELF(→206,50%), 11=HORROR(→204,80%), 12=HORROR_SUB(→249,10%/204,70%), 13=HORROR_SELF(→204,50%), 14=DRAGON(→243,80%), 15=DRAGON_SELF(→243,50%), 16=RAM(→249,80%), 17=HOUND(→202,80%), 18=HOUND_SELF(→202,70%)
- Unit IDs: RAM corpses=[62,63,64], HOUND corpses=[38,182,228,237,239,242], HOUND_SELF(202 corpse)=30% swordsman anti-spam
- Backup: AoWEPACK.dll.bak_animate_dead_expand

## Known Ability IDs
- **CORRECTED 2026-07-20 (verified from disasm of both melee slayer blocks):** 0x70 = **Monster Slaying** (ATTACKER ability), 0x3F = **Dragon/Monster marker** (TARGET). The two entries below were originally recorded swapped; SE-framework notes referencing "0x3F=Monster Slaying" categories describe the S1/S2 matching items, whose id assignments should be re-checked against this correction before reuse.
- 0x3F = Dragon/Monster marker — checked on TARGET in melee slayer blocks (CreateStrikeCA @0x557666A1 block, CalculateStrikes @0x55767C5C block: attacker 0x70 + target 0x3F → +3/+3)
- 0x70 = Monster Slaying — ATTACKER ability
- 0x38 = Hero Slaying (OUR mod, 2026-07-20) — new TMultiLevelAbility, 3 levels, +lvl/+lvl vs THero/TLeader melee targets; registered via cave_hsreg
- 0x77 = Dragon/Monster creature type (vanilla) — System1 StrikeEnhancement target, category 0x0001; pairs with Monster Slaying (0x3F)
- 0x80 = Hero (renamed TResurrectedAbility) — TUnit static ability (vestigial; ability-based Hero Slaying approach was abandoned). S2 SE gap item, category=0x0002 (patched at B9D08 — vestigial).
- 0x82 = Hero Slaying (repurposed TCombatResurrectedAbility) — editor-assigned attacker ability; triggers +2/+2 vs heroes/leaders via runtime cave at 0x10BB3E when GetUnitType(target)==0 && HasAbility(attacker,0x82). Detection is class-hierarchy based (no ability needed on target). Name patched to "Hero Slaying" at B9DE0. S2 SE gap item, category=0x0002 (patched at B9E50 — vestigial).
- 0x84 = Animated — granted by TAnimateHero and (patched) TResurrectHero via MakeAnimated vtable[0x1B4]
- 0x9B = Summoned — uses TUnitEnchantmentAbility.Expand: creates TUnitEnchantmentAbilityData + TUnitEnchantment → CRASH if called via vtable[0x94] without Place(); fixed in v5 caves
- 0x65 = Crusader (not Summoned — wrong guess from previous session)
- 0x6F = Charge (dmg bonus on initiating side's first melee strike; vanilla tactical +2 / fast-combat +3 INCONSISTENT; leveled +2/+3/+4 by OUR mod 2026-07-20), 0x71 = Parry (atk malus on each side's first incoming strike; vanilla −2/−3 same inconsistency; leveled by OUR mod). 0x73 = extra melee strike (+1 to strike count in TMeleeRound ctors), 0x74 = First Strike (defender with it & attacker without → defender strikes first). 0x15 = melee-capable marker (gates global CreateStrikeCA).
- 0x75 = Wall Crushing (TWallCrushingAbility : TTouchAbility, VMT file 0x20714/VA 0x55721314, ctor 0x55768514, id set 0x55768544, name RStr 0x55709ACC, +0x20 mask 0x49). **Leveled I/II/III by OUR mod 2026-07-20: DMG 5×level → ranges 2-5/3-10/4-15** (see [[active-patches]]). NOT flat dmg: touch attack, vanilla **ATK 6 / DMG 6** (imms in fcExecuteCombatCommand @0x557688DC → CA factory 0x55729F18(ecx=dmg 6, stack: types word 0x100, atk 6) and in estimators +0xD8/+0xDC/+0xE4 via 0x55726094/0x55725FE0). Damage type = bit 0x100 (wall-crushing); TCombatWall immunities = NOT 0x100 (getter 0x55725C40) → walls immune to all else. TCombatWall (VMT file 0x15040/VA 0x55715C40, size 0x50): +0x4C wall type byte (2=stone), +0x4D current HP; GetMaxHP @0x55725C30: **stone=25, else(wooden)=5**; defense 0 (+0x70 getter) → 90% hit; RW streams +0x4C tag 0x14, +0x4D tag 0x15.
- 0x2F = Healing (THealingAbility : TTouchAbility : TAdjustableAbility : TAbility; VMT file 0x20BBC / VA 0x557217BC; ctor 0x5576BE3C; name RStr 0x557098BC; +0x20 mask word 0x241 = same hero-class gate as Dispel Magic). Leveled I/II/III=5/7/10 by OUR mod 2026-07-20 (see [[active-patches]]). Data: THealingAbilityData (classref global 0x55721550, VMT 0x55721590, size 0x10, +0xC used-flag, +0xD our level byte; class's +0x4C returns id 0x2F). Cured debuffs on heal: 0x60 Poisoned, 0x35 (?disease), 0x6C Panicked.
- (BXL's broader vanilla ability-ID harvest + free-ID list: see [[bxl-reference]])

## StrikeEnhancement framework (+2 atk/+2 dmg slaying bonuses)
Two registration systems called at game init:
- S1 fn (file 0x666B4): registers TARGET ability IDs via S1 creation sub (0x6667C); fn ends with SEH teardown `33 C0 5A 59 59` at 0x669C9 (RESTORED). Abilities: 0x76,0x6F,0x70,0x71,0x73,0x74,0x77,0x0E-0x14.
- S2 fn (file ~0xBBC00): registers ATTACKER ability IDs. Both S1 and S2 add to the SAME GLOBAL LIST (same EBX/list object). add-to-list sub at file 0x04F638 raises "already exists" if ability_id already in list.
- **CRITICAL**: S1 and S2 share one list. Adding ability already in S2 to S1 → "already exists" crash. Do NOT try to add 0x80 or 0x82 to SE S1 fn.
- **CRITICAL**: 0x55750238 = TAbilityControl.RegisterAbility (GENERAL ability registry, NOT SE-specific). Raises "Ability already registered" if slot already occupied. 0x80 is pre-registered in vanilla → calling RegisterAbility(0x80) crashes with runtime error 216. The S1 cave at 0x10D1C1 used this and caused the crash — JMP was reverted.
- **CRITICAL**: Adding ability 0x80 to heroes in editor data (HEROES.PFS) also crashes with runtime error 216 at startup — game tries to re-register 0x80 when loading those heroes. Do NOT assign 0x80 as a static hero ability. Hero Slaying detection uses GetUnitType class hierarchy instead (no ability assignment on heroes needed).
- **Hero Slaying bonus implemented via hardcoded runtime check** (file 0x65ACF → cave 0x10BB3E), NOT SE framework. SE category patches at B9D08/B9E50 are vestigial.
- S2 creation sub: file 0x5601C (different from S1 creation sub 0x6667C). ALL SE items have type=0 ([+24]=0x00) regardless of S1/S2; matching is symmetric by category.
- S2 gap items (43 items at 0xBBDEE-0xBC1B4): use `33 C9 B2 01 A1 [global_class] E8 [ctor] 8B D0 8B C3 E8 [add-to-list]` (23 bytes/entry). Gap item ctor structure: `C7 46 0C [id4] C6 46 24 00 66 A1 [cat_global4] 66 89 46 20` (sets ability_id, type=0, category from global). 0x82 ctor at B9DC4 (cat global=B9E50). 0x80 ctor around B9C80 (cat global=B9D08).
- S1 gap item at 0x666CC (ctor@65D78): ability_id=0x15, cat loaded from global at +0x3C. 0x80 is NOT in vanilla S1.
- Add-to-list sub (0x04F638): EAX=list obj, EDX=item; checks [item+0x0C]=ability_id; if already exists → exception at sub+0x4B.
- SE item structure: [+00]=VMT, [+0C]=ability_id(DWORD), [+1C]=runtime sub-obj (set by base_init_sub@0x4D9F4), [+20]=category(WORD), [+24]=type(BYTE, always 0).
- S1 creation sub (0x6667C): EAX=ability_id, ECX=category, EDX=0(nil name). Returns new SE item in EAX.
- Matching: bitwise AND of category words ≠ 0 → +2/+2 bonus (NOT equality). Vanilla S1 target items use 0x0009 (from global at file 0x669FC); Monster Slaying S2=0x0001; 0x0009&0x0001=1→match.
- Known category values: S2: 0x0001=MonsterSlaying(0x3F); 0x0002=HeroSlaying(0x82) [patched B9E50 — vestigial]. S1: vanilla=0x0009.

## HasAbility / Summoned / GetSourceName
- **HasAbility (vtable[0xA8])**: searches ability list on TCombatUnit. Call convention (confirmed from vanilla disassembly): `MOV EDX, <id32>; MOV EAX, <obj>; MOV ECX, [EAX]; CALL [ECX+0xA8]`. Returns AL (non-zero=has it). Use for editor-assigned abilities (0x80, 0x82, etc.). NOTE: file offset 0x08A57C is NOT HasAbility — that's TLeader.GetSpherePicks (BXL confirms, VA 0x5578B17C). Do NOT use a direct call to that address.
- **Summoned fix (v5)**: shared upkeep subroutine at 0x10D04D (v2). Calls UnitResourceIndex([unit+40h]) to get spawned unit type, sets [enchant+10h]. Sub v2: 133->10, 243/216->8, 204/206/44->6, 200/223/241->3, else->2. Caves at 0x10BAD2/0x10BB08, each 54 bytes.
- **GetSourceName logic**: if FindUnit([enchant+18h])=nil OR found unit's player != enchant.player → reads [enchant+0Ch] for player name display. So [enchant+18h]=0 forces correct-player display via L55765819 path.

## Ability Name Fix — DONE
- 0x82 name: B9DE0 patched. Replaces 3-call sequence (which called [0x558E8FE0] object to generate name) with direct LStrAsg of AnsiString constant "Hero Slaying" (VA 0x5580DD71, file 0x10D171). Constant stored at 0x10D169 (refcnt=-1, len=12).
- 0x80 (Hero) display: type byte at B9CC5 REVERTED to 00 (type=1 caused blank+draw errors). Hero ability remains hidden in unit inspector UI. Not critical for SE matching.
- IAT thunk 0x550 = LStrAsg (EAX=dest_addr, EDX=src_ptr). Thunk 0x610 takes object ref, NOT string — cannot use it directly.

## TAbility / ability framework facts (learned during Healing work 2026-07-20)
- Ability VMT slots: +0x58 GetName(self,unit,out); +0x70 GetLevel(self,unit strategic); +0x74 GetEnabled; +0x80 GetSkillPoints (**level-up CHARGE = its DELTA; dialog display = ExpandCost — leveled abilities MUST make GetSkillPoints = level×ExpandCost or display≠charge**; base = [self+0x14] if HasAbility; [self+0x14] = data-driven expand cost, Healing's = 5); +0x94 GetInherentLevel; +0x98 small type-byte getter; +0xAC per-round re-enable; +0xC4 CanExpand(self,unit); +0xC8 ExpandCost (base 0x5574E908 returns [self+0x14], often 0!); +0xCC ExpandName(self,unit,out) — level-up dialog name; +0xD0 Expand; +0xD4 Remove (called on ability loss; leveled abilities DEC one level per call, cf. TU 0x5576B19C); +0xD8/+0xDC strategic AI value fns (EDX=owner, ECX=target); +0xE4 combat AI value fn (out-record: [0]=value,[4]=amount,[0x10]=word type); +0x10C GetTouchAttack (touch abilities); **+0x104 GetCombatInfo(self,EDX=unit,ECX=out) = TACTICAL PREVIEW source — record: [+0]=flags, [+1]=ATK byte, [+2]=DMG byte, [+3..4]=dmg-types word, [+5]=range; leveled abilities MUST fill from level getters or preview shows stale values** (WC v1b lesson); +0x120 strategic CanTouch; +0x11C combat CanTouch(self,EDX=owner,ECX=target).
- Strategic-unit VMT: +0x4C HasAbility(id); +0x50 SetAbilityBit; +0x8C hero-class expand mask (ANDed with [ability+0x20]).
- Helpers: FindData 0x5574F1C4 (EAX=strat unit, EDX=id → data rec|nil); AddData 0x5574F278; RemoveData-by-id 0x5574F2B8; RemoveData-by-rec 0x5574F284; add/remove-bit-with-notify 0x5574E718 (EAX=ability,EDX=unit,ECX=id,push flag); TObjCreate 0x55703064 (EAX=class,DL=1,ECX=0); TAbilityData.ReadWrite base 0x5574E5EC.
- **Data records persist via TAGGED stream fields** (self-describing): RW pattern `lea edx,[self+ofs]; mov ecx,TAG; mov eax,stream; call [streamVMT+0x38]` (byte-ish; +0x30 = another byte variant). Adding a new tag = save-compatible both ways (missing tag → field unchanged). Precedent: TDispelMagicAbilityData.ReadWrite 0x5576CD34 (tags 0xA=+0xC, 0xB=+0xD).
- TU data class classref global 0x5571DEB8 (level at rec+0xC, id word at rec+0xE); DM/Healing data: +0xC toggle/used, +0xD level.
- cave_lsnames 0x5580E2A0 is generic+PIC: (EAX=ability, EDX=level, ECX=out) → out = [ability+8] + " I/II/III" (level 1..3), else plain copy. Reused by lifesteal/hero-slaying/monster-slaying/healing.

## Key Functions (AoWEPACK.dll file offsets)
- 0x4C7C8: TUnitResource.UnitResourceIndex — returns numeric unit type ID (index into resource list); EAX=self(TUnitResource), returns EAX=ID
- 0x84450: TUnitResourceList.GetUnitResource — EAX=list, EDX=unit_id, returns EAX=TUnitResource ptr
- **GetUnitType vtable[0x114]** on TUnit hierarchy: TAbstractUnit/THero/TLeader → returns 0; TUnit → reads byte [TUnitResource+0x30] (non-zero for regular units). **CORRECTION 2026-07-20: [res+0x30] is 0 for MANY regular units too (e.g. leprechaun), NOT just heroes/leaders — do NOT use GetUnitType==0 as a hero/leader test (it wrongly caught units in cave_victimxp; cost a long debug). Use IsClass(THero classref) for a real hero test.** TUnit VMT base VA = 0x55710cac. Vtable entry at 0x55710dc0. Use to identify hero/leader targets: GetUnitType(target)==0 means hero or leader.
- 0x59E4 (VA 0x557665E4): Runtime strike check (= global CreateStrikeCA per BXL) — EAX(→EBP)=target TCombatUnit, EDX(→ESI)=attacker TCombatUnit, BL=atk bonus accumulator, [ESP+3]=dmg bonus accumulator. Vanilla uses `MOV EDX,id; MOV EAX,obj; MOV ECX,[EAX]; CALL [ECX+0xA8]` for all HasAbility checks. Has hardcoded Monster(0x70)+MonsterSlaying(0x3F)→+3/+3 check at file 0x666A1. Hero Slaying JMP at file 0x65ACF; cave at 0x10BB3E (60 bytes).

## TAnimateDead.CreateCA / Execute register layout
- In Execute: **ESI = dead body TCombatUnit** (found via FindID([spell+0Dh]) where [spell+0Dh]=[dead_body+0Ch])
- EDI = spell caster or target hex slot (NOT the dead body)
- EBX = newly created TUnit (at patch points 0xF9549/0xF9769, and at cave entry)
- [ESI+4Ch] = dead body's TUnit; [TUnit+0x40] = TUnitResource; UnitResourceIndex → unit type ID
- Confirmed by CreateCA: ECX param = dead body, [dead_body+47h] bit0 = dead flag stored in spell action

## GlobalSpells Class Hierarchy (AoWEPACK.dll)
- TResurrectHero: TypeInfo at 0xE8B90 (tkClass,0x07), VMT at file 0xE8AE0 (VA 0x557E96E0)
- TAnimateHero:   TypeInfo at 0xE8CAD,              VMT at file 0xE8BFC (VA 0x557E97FC)
- Both VMTs share 28 of 30 slots; differ at slots 8 (constructor), 20 (ExecuteTE), 27 (Create?)
- ExecuteTE = VMT slot 20; TResurrectHero→0xEB414, TAnimateHero→0xEB97C
- Ability granting in ExecuteTE: `mov eax,[ebp-14h]; mov edx,[eax]; call [edx+vtable_off]`
  - vtable[0x1B0] = MakeResurrected (ability 0x82) ← original TResurrectHero
  - vtable[0x1B4] = MakeAnimated    (ability 0x84) ← used by TAnimateHero; now also TResurrectHero
- 0x82 (Resurrected) is NEVER granted via vtable[0x94] (ExpandAbility) in the binary; only via MakeResurrected
- Debug map section at 0x25D000–0x25E400 contains null-terminated symbol names

## Key Globals (AoWTCPCK.dll)
- 0x46C064: global pointer to AoWCombatMap object


## Kill/Capture XP mechanism (RE'd 2026-07-21)
- **XP write = get-modify-set**, uniform for units & heroes: `ebx = GetXP [killer+0x98];
  add <victim contribution from cave_victimxp>; edx = ebx; SetXP [killer+0x9c](edx)`.
  So a cave feeding this path returns the GAIN (added to current XP), NOT an absolute value.
- Three award sites, all calling shared cave_victimxp (0x5580f060):
  - KILL tactical: func 0x55726b1e, cave call @0x55726b7f (esi=victim, edi=killer, ebx=base).
  - KILL autocombat: func 0x55729fb0, cave call @0x5572a00c (same regs).
  - CAPTURE (battle-log result): callers 0x557f8473 & 0x5576fcb8, killer resolved from battle
    indices and left ON THE STACK; each -> thunk 0x5580f050 (`push esi; mov esi,edi(=victim);
    call cave_victimxp; pop esi; ret`). Victim = edi here, killer at caller [esp] / [esp+4].
- **Battle-unit owner/player index = byte [+0x1c]** (differs enemy-vs-enemy; after a
  seduce/charm/dominate the captured unit's [+0x1c] == captor's). [+0x24] is NOT owner
  (constant/shared across combatants). [+0x4c] = ptr to the strategic TUnit. [+0xc] = combat id.
- **THero SetExperience -> hero XP cave 0x5580BE80** (my medal-killxp cave; called from 0x55787675;
  [hero+0x48] = XP field). It treats edx as the NEW ABSOLUTE XP: `delta = edx - currentXP;
  if delta<=0 -> DIRECT-STORE edx as XP (pop edx; mov [esi+0x48],edx)`; else tier-ladder ADD by
  effective level (1->1,2->5,3->15,4->25,>=5->50; strips 0x80 cap bit -> x2). **LANDMINE: passing a
  small/negative absolute value to a high-XP hero direct-stores it and nukes the hero (saw -6000 /
  reset to L1). Any cave feeding hero XP must yield currentXP + positive_gain, never a bare small value.**
- Kill XP magnitude formula (unit killer): gain = (victimEffLevel + 1 - killerLevel) * 5, min 1,
  clamp 250. Heroes/leaders as victims keep RAW level; regular-unit victims use tier+rank (silver
  +1 / gold +2). Capture path scales differently (empirically total 200 -> 99 XP).

## Strike status-effect internals (2026-07-27, for manual display)
- **ExecuteDamageEffectsRole @0x55781BA4** (TAbstractUnit): per damage-mask bit, blocks are `[imm-check ability][test weakness bit][push typeidx][push ATK][call weakness-roll cave 0x5580FC00]`. **Damage mask bits: fire=0x01, cold=0x02, lightning=0x04, magic=0x08, poison=0x10, death=0x20, holy=0x40, physical=0x80, wall=0x100.**
- **Hidden status ATK immediates** (byte at site+3; site = `6a <type> 6a <ATK> e8`): Fire @0x55781C30 ATK 4 (Burning 0x7F), Cold @0x55781DE6 ATK 3 (Frozen 0x5F), Lightning @0x55781C90 ATK 6 (Stunned 0x5C), Poison @0x55781CE2 ATK 3 (Poisoned 0x60), Death @0x55781D34 ATK 4 (Cursed 0x5D "prevents healing"), Holy @0x55781D86 ATK 3 (Vertigo 0x62 "-2 ATK/-2 DEF"). Roll = HitRole(ATK - targetRES±3 weakness/protection). Status ability ids from ExecuteCombatDamageEffects @0x55781ED8 (result-bit→grant; fire also removes Frozen / cold removes Burning).
- **Entangle Strike (0x77)**: rolled in TStrikeCA.Generate @0x5576692F block — `mov eax,7` @0x5576694D, HitRole(7 - target[vtbl+0x74]) → Entangled (0x5E) via TEntangleCA.Execute. Touch Entangle (0x28) GetTouchAttack also = 7 (@0x5576A810).
- Manual regenerator reads these bytes LIVE from AoWEPACK.dll (build_manual_from_game.py `_sstat`) — retunes auto-display. ⚠️ User spreadsheet rows "Lightning/Cold Hidden ATK" point at site+1 (the weakness TYPE index our weakness patch added), not the ATK at site+3.
