
## ⚠️ CAVE RULE — AoWEPACK.dll REBASES between launches (seen at 0x01170000; preferred 0x55700000). ANY cave that DEREFERENCES an in-image absolute (`mov r,[0x55..]`, `mov r,0x55..addr`, `push 0x55..addr`, bare `[disp32]`) is a LATENT REBASE CRASH — the loader relocates only the game's own refs, not ours. Symptom: "Runtime error 216 at 00003924" at STARTUP (intermittent: works one launch, crashes next). USE the PIC delta-trick for data: `call $+5; pop reg; sub reg,<pop's preferred VA>` then `[reg+abs]`/`lea reg,[reg+abs]`. rel32 call/jmp are already PI. Bit us via Path-of-Sand caves 2026-07-23 (fixed). See [[path-of-sand-ability]].

## Restore point (latest): "RESTORE POINT 2026-07-27 - FULL (arena cost-xp + warmonger 20xp + all prior)" in backup/. Adds the three 2026-07-27 AoWEPACK arena/warmonger patches (all CONFIRMED in-game 2026-07-27) + everything since 23c (weakness abilities, hero-AI chooser, AI spell once-per-combat, road cost, registry isolation, dlgdirs, Legendary icon in Images/Combat.ILB — Images/ included). (Prev: "RESTORE POINT 2026-07-23c - FULL (MP default race CPU Emperor + all prior)".) Adds (both AoWEPACK.dll) hero level-up event fixed-location ([[hero-levelup-event-fixed-location]]) + MP LAN default race Free→CPU Emperor ([[mp-default-race-cpu-emperor]]), on top of the 23b point. All CONFIRMED in-game. (Prev: "RESTORE POINT 2026-07-23b - FULL (spheres + Path of Sand + True Seeing + all prior)" — sphere combining + Path of Sand (0x9F) + True Seeing vs-invisible ATK penalty + night-vision city-production crash fix + Path-of-Sand PIC/rebase fix.) (Prev latest: "RESTORE POINT 2026-07-23 - FULL (mouse wheel + About rebrand + underground night vision)".) (Prev: "RESTORE POINT 2026-07-22 - FULL (portrait filter + editor dir-memory + registry isolation + English)".)
COMPLETE self-contained snapshot: all 8 key binaries + Release.hss + custom Images/Combat.ILB +
14 blood ILBs + patch scripts (incl. wav2it.py/wav2it_drop.py) + 11 custom music .IT + AoWxBard.exe
in Songs/ + README. Covers waves 1-2 (leveled abilities, ability costs, XP overhaul, medal HP-cap),
wave 3 (morale->ATK/RES, capture XP cap, healing crash fix), wave 4 (blue/green blood), custom music,
PLUS new 2026-07-22: Designer-Only/Reserved portrait filter restored ([[designer-only-portrait-toggle]]),
editor renamed AoWDevEd->AoWDevX.exe, editor Open-dialog dir-memory v3 ([[editor-dialog-dir-memory]]),
registry isolation to "Age of Wonders X" + forced-English language ([[registry-isolation]]).
Files differing from vanilla: AoWEPACK.dll, AoWTCPCK.dll, HSEPack.dpl, AoWDevX.exe, Release.hss,
Combat.ILB + 14 blood ILBs. Per-feature revert .bak_* in game root. Supersedes "FULL + all 11 custom
tracks"; earlier restore points kept as checkpoints.

## AoWEPACK.dll (VA = file_off + 0x55700C00)
| Offset | From | To | Purpose |
|--------|------|----|---------|
| C12A0 | 83 78 08 01 | 31 C0 90 90 | Allow tactical combat UI for exploration sites in MP |
| 24166 | 0F 85 AA 01 00 00 | 90*6 | Animate Dead units persist after combat |
| F9526 | BA 82 00 00 00 | E9 62 38 01 00 | JMP to Recall Spirit spawn cave |
| F9549 | BA 82 00 00 00 | E9 84 25 01 00 | JMP to TRecallSpiritCA v5 summoned cave |
| F9746 | BA C9 00 00 00 | E9 C2 2A 01 00 | JMP to Animate Dead spawn cave (v3) |
| F9769 | BA 82 00 00 00 | E9 9A 23 01 00 | JMP to TAnimateDeadCA v5 summoned cave |
| 10BAD2 | 00*54 | (cave 54B) | TRecallSpiritCA v5: ExpandAbility(0x9B), SetSource, call upkeep sub |
| 10BB08 | 00*54 | (cave 54B) | TAnimateDeadCA v5: same as above |
| 10C20D | 00*902 | (cave 902B) | AD spawn: 18 groups, RDTSC RNG, 293B table. RAM(62-64)->249, HOUND(38,182,228,237,239,242)->202, HOUND_SELF(202)->202 |
| 10CD8D | 00*608 | (cave 608B) | RS spawn: 8 groups, RDTSC RNG, 293B table |
| 10D04D | 00*171 | (sub 171B) | Upkeep sub v2: 133->10, 243/216->8, 204/206/44->6, 200/223/241->3, else->2 |
| D47E3 | C6 46 44 01, 45 00, 64 00, 58 01 | C6 46 45 00, 64 00, 58 01, 5B 01 | Pool ctor: razeable=1 + rebuild days=1 (was 2, reduced 2026-07-04); dropped redundant +44h write (base sets it). Supersedes old single-byte D47F2 patch (see [[reflecting-pool-raze]]) |
| 10B6A0/10B6D8/10B700/10B740 | 00 | (4 caves) | Pool GetRazed/ReadWrite/SetRazed-v2/PVP-guard |
| D3CE0/D3E14/D3E18 | (VMT ptrs) | cave VAs | Pool VMT slots +0x18/+0x14C/+0x150 |
| D4630 | 53 56 51 88 14 24 | E9 0B 71 03 00 90 | PoolVisionPlayer razed-guard hook |
| 10B754 | 00*41 | (cave 41B) | Pool ownership helper: list→1 if ≥1 NON-razed pool (fixes vision granted during rebuild) |
| D464F/D468B | 8B 10 FF 52 54 | E8 rel32 (to 10B754 cave) | PoolVisionPlayer: both Count!=0 checks → non-razed count |
| 10B705 | 74 1C | 74 76 | SetRazed cave unraze path → ext cave |
| 10B77D | 00*16 | (ext cave 16B) | Unraze ext: clear bit +39h, call UpdateReflectingPoolsExploration, jmp cave common |
| 10B790 | 00*45 | (gfx cave 45B) | GetTerrainTypeImage: building ([+24h]!=FF) → imgs 0x19/1A/1B BEFORE razed check (rebuild anim, idx 25-27 in DevEd) |
| 5DAA0 | 53 56 8B F2 8B D8 | E9 EB DC 0A 00 90 | TStructure.GetTerrainTypeImage entry hook → gfx cave |

**Movement-predictor fix (applied 2026-07-19, ported from BXL v4; script `patch_move_predictor_v1.py`, backup AoWEPACK.dll.bak_move_predictor).** Fixes mixed-ability stacks predicting AND executing with MIN(MP)×MAX(cost). All four hooks were vanilla `E8` calls, verified before patch:
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 46F01 | 0x55747B01 | call MovePointsToPos → cave_exec | TMoveArmyTE.Setup — execution path no longer truncated |
| 4976E | 0x5574A36E | call MovePointsToPos → cave_movearmy | MoveArmyEx — destination-reached (attack/combine) at true range |
| 92AA3 | 0x557936A3 | 13B (mov/call/store) → call cave_display + 8 NOP | TSelectedArmy.Update — synthetic budget B* into TMoveSettings+14h |
| 91E18 | 0x55792A18 | call PosToMovePoints → cave_calcpath | TSelectedArmy.CalculateMovePath — budget refreshed when path built (v4) |
| 10D240 | 0x5580DE40 | 00*432 → cave | cave_exec/DE40, cave_movearmy/DE51, cave_display/DE5F, cave_calcpath/DE9A, true_reach/DECB, unit_walk/DF4C. TrueReachPos: per-unit CreateMovePointTable + own MP walk, reach = worst unit stop. Includes BXL's v2 PIC AoWHSMap read (call/pop delta), v3 MOVSX terrain/road (signed, road −1=none, +1 column shift). AI sites + multi-day tail deliberately vanilla. MP: both peers need patched DLL. |

**5-level Leadership + disable-bug fix (applied 2026-07-19, CONFIRMED WORKING in-game 2026-07-19; ported from BXL leadership4+leadership_fix; script `patch_leadership5_v1.py`, backup AoWEPACK.dll.bak_leadership5).** Curve: I +1/0, II +1/+1, III +2/+1, IV +2/+2, V +3/+3; cost 10/level → **5/level since cost-retune 2026-07-20** (25 to V). NOTE: level 1 is weaker than vanilla (+2/+1 is now level III).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 65587 | 0x55766187 | imm32 1→5 | TLeadershipAbility.Create cap stomp `mov [esi+0x28],1` → 5 |
| 655A2 | 0x557661A2 | call Put → cave_lscosts | ctor cost init → Put(list,1..5,10) |
| 65607/6561B | 0x55766207/0x5576621B | disp32 → 0x5580E0C0/0x5580E0C8 | GetAttack/GetDefense bonus tables relocated (both disp32s carry .reloc — value repoint only, rebase-safe) |
| 21514 | 0x55722114 | VMT+0x10C → cave_lsname | GetLevelName appends " I".." V" (reuses Marksmanship literals 0x557BBF18/24/30/40 + framework " V" @0x5576DE04) |
| 4E94D/4E95B | 0x5574F54D/0x5574F55B | 8B 08 FF 91 84 00 00 00 → call cave_abinherent + 3 NOP | UpdateDefaultAbilities compares INHERENT levels (ability VMT+0x94) not effective — fixes Leadership permanently lost when ranking up inside another leader's aura |
| 10D3F0 | 0x5580DFF0 | caves+data 0x5580DFF0–0x5580E118 | cave_lscosts/DFF0(32B), cave_lsname/E020(94B, PIC call-pop), data tables+suffix ptrs/E0C0(40B), cave_abinherent/E0E8(49B, PIC) |
Known separate defect NOT fixed (data-side): Crown of Kings item has bare Leadership bit with no record → level 0, never worked (ITEMS.PFS, per BXL).

**Leadership aura instant-refresh (applied 2026-07-19, CONFIRMED WORKING in-game 2026-07-19; script `patch_leadership_aura_refresh_v1.py`, backup AoWEPACK.dll.bak_leadership_aura).** After buying a Leadership level, party units now get the aura bonus immediately (was: only on next move/turn).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 848E0 | 0x557854E0 | call UpdateDefaultAbilities → cave_auraup | THeroUpgradeTE.Execute tail hook (right before flag-clear `mov byte [edi+54h],0`; EDI=hero) |
| 10D520 | 0x5580E120 | 51B cave | cave_auraup: call UDA, then army=[hero+4]; if non-nil && IsClass(army,TArmy) → TArmy.UpdateFormation(army). PIC classref read (TArmy classref global 0x557130AC, IsClass thunk 0x557010C0, UpdateFormation 0x5578D034). MP-safe (TE runs on all peers). |
Facts learned: TAbstractUnit+0x4 = containing container (guard with IsClass TArmy — vanilla MovedTo does the same); hero upgrade-pending flag = [hero+0x54] (cleared at end of TE = what locks the level-up UI).

**Lifesteal on round attack (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_lifesteal_round_v1.py`, backup AoWEPACK.dll.bak_lifesteal_round; ported from BXL, adapted).** Life Stealing (0x76) now heals on ALL offensive strikes (normal melee + round attack), not retaliation, wired like Cause Fear/Entangle (flag in Generate, plain flag-block heal in Execute).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 65B8C | 0x5576678C | 80 7B 15 00 74 3D → E9 rel32 90 | TStrikeCA.Execute → cave_lsround; jumps back 0x557667CF, SKIPS old CA+0x15 block (old lifesteal path incl. pre-Claude cave at 0x5580C110 now dead but left in place; CA+0x18 bit 0x02 still set by TMeleeRound but never read — vestigial) |
| 65CE2 | 0x557668E2 | BA 33 00 00 00 → E9 rel32 | TStrikeCA.Generate → cave_lsgen (site is inside CA+0x10≠0 block → hit-gated; EBX=CA, EDI=attacker, ESI=target) |
| 10D560 | 0x5580E160 | 36B cave | cave_lsround: flag 0x08 → heal attacker +2 (GetHitPoints +0x88 / SetHitPoints +0x8C, clamps). +2 matches live AoWx tune (vanilla was +1 inc edx; .dpl has vanilla bytes) |
| 10D5A0 | 0x5580E1A0 | 87B cave | cave_lsgen: offensive gate (CA+0xC bit0) → attacker GetAbilityEnabled(0x76) → vanilla target gate KEPT (IsClass TCombatUnit via PIC classref 0x55715A54 + [target+0x4C]≠nil + GetUnitType≠2) → or CA+0x18,0x08; replay mov edx,0x33 |
Facts: TStrikeCA.Generate(EAX=CA,EDX=attacker,ECX=target); vanilla 0x33 Cause Fear/0x77 Entangle flags use RES-based HitRole rolls in Generate. DEFENSIVE=True in script re-applies with retaliation lifesteal. Pre-Claude cave found: 0x10B510 (8B, heal+2 helper, now dead).

**Leveled Life Stealing I/II/III = +1/+2/+3 HP (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_lifesteal_leveled_v1.py`, backup AoWEPACK.dll.bak_lifesteal_leveled; REQUIRES lifesteal-round patch).** 0x76 flyweight converted to TMultiLevelAbility (cap 3, cost 10/level like Leadership).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 6670A | 0x5576730A | call 0x5576727C → cave_mlcreate | RegisterStrikeAbilities: 0x76 factory swap (old factory made TStrikeEnhancementAbility; args EAX=id, EDX=translated name, CX=icon word) |
| 1D4DC | 0x5571E0DC | dword 0x55765230 → cave_lsnames | TMultiLevelAbility OWN VMT+0x10C GetLevelName (base renders "Unknown N"!). Safe: no vanilla plain-ML instance exists; subclass VMTs are static copies |
| 10D560 | 0x5580E160 | cave_lsround v2 (57B) | heal = combat GetAbilityLevel(+0xB0→strategic +0x144), level 0 (legacy bit-only unit data) → 1. NOTE: legacy lifestealers now +1 (was flat +2) until re-authored with level II in DevEd; heroes buy levels at level-up |
| 10D600 | 0x5580E200 | cave_mlcreate (129B, PIC) | ML ctor (Object_Entry 0x5571DF90, Create 0x55765168) + icon/id/name + cap=3 + Put costs |
| 10D6A0 | 0x5580E2A0 | cave_lsnames (66B, PIC) + suffix tab @0x5580E2F0 | "Life Stealing"+" I/II/III" (reuses Marksmanship literals; name from [ability+8]) |
Facts: TMultiLevelAbility Object_Entry 0x5571DF90 / VMT 0x5571DFD0 / Create 0x55765168 / base GetLevelName 0x55765230 ("Unknown N") / GetName 0x55765298 (calls [vmt+0x70] GetLevel then [vmt+0x10C]); ML ctor sets cap[+0x28]=4 + cost list[+0x2C], subclass Puts costs; ExpandCost = Get(cost list, inherent+1); old factory SUB_0x5576727C = TStrikeEnhancementAbility (+0x20 icon word, +0xC id, +8 name); combat VMT+0xB0 GetAbilityLevel = `mov eax,[eax+4C]; call [vmt+0x144]` (NOT null-safe alone — safe here because +0xA8 gate precedes).

**Hero Slaying I/II/III — NEW leveled ability id 0x38 (+1/+1, +2/+2, +3/+3 ATK/DMG vs hero/leader melee targets) (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_hero_slaying_leveled_v1.py`, backup AoWEPACK.dll.bak_hero_slaying_lvl; REQUIRES lifesteal-leveled patch — reuses its generic cave_lsnames for " I/II/III").** Concept = BXL's Assassin, rebuilt on TMultiLevelAbility. Cost 10/level. NOT hooked (same scope as BXL's confirmed Assassin): autocombat DV fn slayer block (@0x557665xx fn) and CalculateUnitStrikes @0x55767904 — fast-combat gets no HS bonus.
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 66713 | 0x55767313 | call RegisterAbility → cave_hsreg | RegisterStrikeAbilities: after lifesteal registration, also create+register HS (id 0x38, icon word 0x209 from [0x557675F0], name from embedded refcnt=-1 AnsiString, cap 3, cost 10/lvl → 5/lvl since cost-retune 2026-07-20) |
| 65AA1 | 0x557666A1 | BA 70 00 00 00 → E9 rel32 | CreateStrikeCA Monster block → cave_hsmelee (EBP=attacker, ESI=target, BL=atk acc, [ESP+3]=dmg acc); replays mov edx,0x70 → 0x557666A6 |
| 6705C | 0x55767C5C | BA 70 00 00 00 → E9 rel32 | TMeleeRound.CalculateStrikes Monster block → cave_hsmelee2 (ESI=attacker, EDI=target, [EBX]/[EBX+4] atk/dmg dwords); → 0x55767C61 |
| 10D700 | 0x5580E300 | cave_hsreg 137B (PIC) + name const @0x5580E390 | |
| 10D7B0 | 0x5580E3B0/0x5580E410 | cave_hsmelee 89B / cave_hsmelee2 88B (PIC) | gates: attacker enabled(0x38) [null-safe +0xA8] → [target+0x4C]≠nil → IsClass(THero classref global 0x55711FAC → covers TLeader) → level=+0xB0 (min 1) → add |
**MEMORY CORRECTION (2026-07-20, from disasm):** 0x70 = Monster Slaying (ATTACKER ability), 0x3F = Dragon/Monster marker (TARGET) — aowx-re-reference.md and old notes had them SWAPPED. Both melee slayer blocks check 0x70 on attacker + 0x3F on target, +3/+3.

**Monster Slaying I/II/III leveled (+1/+1, +2/+2, +3/+3 vs 0x3F targets) (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_monster_slaying_leveled_v1.py`, backup AoWEPACK.dll.bak_monster_slaying_lvl; REQUIRES lifesteal-leveled patch — reuses cave_mlcreate + cave_lsnames).**
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 66774 | 0x55767374 | call factory → cave_mscost (was cave_mlcreate; retargeted by cost-retune 2026-07-20) | 0x70 flyweight becomes ML (cap 3, cost 3/lvl via wrapper); translated name + icon 0x209 pass through |
| 65AC7 | 0x557666C7 | 80 C3 03 80 44 24 03 03 → call cave_msmelee + 3 NOP | CreateStrikeCA +3/+3 tail → +lvl/+lvl (EBP=attacker; dmg acc [esp+7] inside call) |
| 67082 | 0x55767C82 | 83 03 03 83 43 04 03 → call cave_msmelee2 + 2 NOP | CalculateStrikes +3/+3 tail → +lvl/+lvl (ESI=attacker) |
| 10D870/10D8A0 | 0x5580E470/0x5580E4A0 | 27B/26B caves | GetAbilityLevel(+0xB0, safe post-gate), level 0 → 1 |
**BALANCE:** legacy bare-bit possessors now +1/+1 (was +3/+3) — re-author units at Monster Slaying III in DevEd for vanilla parity. Autocombat/DV slayer copy NOT hooked (still flat +3). Verified-inert side effect: TStrikeAbility.Remove's is-TStrikeEnhancementAbility sweep (@0x55766AC7 area, on melee-attack loss) no longer matches converted 0x70/0x76.

**Slayers on ranged: Hero+Monster Slaying apply to short/medium-range shots, NOT long (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_slayers_ranged_v1.py`, backup AoWEPACK.dll.bak_slayers_ranged; REQUIRES both leveled-slayer patches).**
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 6E234 | 0x5576EB34 | 50 8B C6 8B 10 → E9 rel32 | CreateRangedAttackCA damage-push hook (BXL's proven site). At hook: EAX=damage, EBX=ability, ESI=shooter, [EBP-4]=target combat obj, [ESP]=pushed attack |
| 10D900 | 0x5580E500 | 173B cave (PIC) | Gate: ability range byte +0x28 (GetRangeRA, shared impl all 4 ranged VMTs, no overrides; 1=short/2=medium/3=long via CombatRangeToCombatMode 1→mode3, 2→4, 3→5) < 3. MS: shooter 0x70 + target 0x3F → +lvl atk/dmg; HS: shooter 0x38 + target strategic IsClass THero → +lvl. Level min 1. Adds to pushed attack [esp+4] + damage in EDI; replays push/mov/mov → 0x5576EB39 |
Notes: breath attacks (TBreathAbility) use same builder, are short/medium → get bonus. Autocombat DV estimators not hooked (consistent scope). Pre-Claude archery cave SUB_0x5580BF70 lives in GetAttackRA (marksmanship rework — file 0x10B370 area, different site, no conflict). Ranged fn map: CreateRangedAttackCA 0x5576EAE4 (attack push @0x5576EB1D after `sub al,[ebp+8]` wall malus; damage push @0x5576EB34); fcExecuteCombatCommand 0x5576EB70 loops GetAttackRepeatRA (+0x2D) shots; GetRangeRA=+0x28, GetAttackRA=+0x2A (MODDED pre-Claude: cave 0x5580BF70 = +1/+2/+3/+4 atk for Marksmanship I–IV), GetDamageRA=+0x29 base (VANILLA, verified dll==dpl: Marksmanship dmg ladder II/III/IV = +1/+1/+2, rank I no dmg), GetDamageTypesRA=+0x2B word. Slayer bonuses add AFTER both getters → stack additively with Marksmanship on both attack and damage.

**Marksmanship V (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_marksmanship5_v1.py`, backup AoWEPACK.dll.bak_marksmanship5).** Curve: I +1/0, II +2/+1, III +3/+1, IV +4/+2, **V +5/+2**; cost 3/level (vanilla).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| BB160 | 0x557BBD60 | imm 4→5 | TMarksmanshipAbility.Create cap |
| BB1AA | 0x557BBDAA | call Put → cave_mk5cost | 4th Put displaced; cave Put(4,3) + tail-jmp Put(5,3) |
| 10B370 | 0x5580BF70 | ladder → `test eax,eax; jle; add bl,al; ret` | pre-Claude attack cave REWRITTEN in place (was +1..+4 else 0; now +level, V=+5). Orig cave bytes preserved in script ATK_ORIG |
| 6DA4A | 0x5576E64A | 74→7D (jz→jge) | GetDamageRA ladder: level≥4 → +2 dmg (IV unchanged, V +2). Vanilla fn |
| BB207 | 0x557BBE07 | ja rel32 → cave_mk5name | GetLevelName `cmp edx,4; ja default` retargeted; cave: level==5 → LoadResString(RStr slot 0x558E9498, PIC)+TranslateRStr+LStrCat3(" V" lit 0x5576DE04, PIC) using fn frame locals (finally clears them); else jmp 0x557BBEE6. **EAX dead at ja (SEH setup zeroes it)** — cannot read self |
| 10D9B0/10D9D0 | 0x5580E5B0/0x5580E5D0 | 23B/64B caves | |
Facts: TMarksmanshipAbility.Create @0x557BBCF8 region (icon word [0x557BBDE8]=0x237, id 0x20, cat byte +0x24=0); GetLevelName jump-table @0x557BBE14 (5 entries, levels 0–4); helpers LoadResString thunk 0x55701210, TranslateRStr 0x557249FC. ExpandName(level+1) routes through same GetLevelName → dialog shows "Marksmanship V" when buying.

**Turn Undead V (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20 — required the inherent-level follow-up fix below; script `patch_turnundead5_v1.py`, backup AoWEPACK.dll.bak_turnundead5).** Curve (touch ATK/DMG): I 6/4, II 7/5, III 8/6, IV 9/7, **V 10/10** (V dmg re-tuned 8→10 on 2026-07-20; V special-cased in dmg ladder, I–IV still level+3); cost flat 5/level (vanilla) → **3/level since cost-retune 2026-07-20** (ExpandCost imm @6A4E7 AND GetSkillPoints ×5→×3 @6A531 — both, per display=charge rule).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 6A4E3/6A51B/6A58C | 0x5576B0E3/0x5576B11B/0x5576B18C | imm 4→5 ×3 | ExpandCost / CanExpand / Expand caps (TU is NOT ML-based — TTurnUndeadAbility : TTouchAbility : TAbility, own level machinery, data = TMultiLevelAbilityData at +0xC) |
| 6A5F4 | 0x5576B1F4 | 29B ladder → `level+5` (else 4) | GetTouchAttack (EDX=level; vanilla dec-edx chain 6/7/8/9) |
| 6A614 | 0x5576B214 | 29B ladder → `level+3` (else 0) | GetTurnUndeadDamage (vanilla 4/5/6/7) |
| 6A357 | 0x5576AF57 | ja rel32 → cave_tu5name | GetLevelName jump-table guard; cave @0x5580E640 (63B, file 0x10DA40): level 5 → LoadResString(TurnUndeadRStr **immediate** 0x557078D4, PIC add)+Translate+LStrCat3 " V"; else 0x5576B036 |
Facts: TU id 0x26; ctor sets +0x24=3, icon [0x5576ADC0]; ExpandCost=flat 5, GetSkillPoints=5×level (both handle 5 fine); GetCombatInfo/estimators call the getters with level → display auto-consistent; NOTE BXL's doc ATK values (9-12) did NOT match our binary (6-9). Both getter fns + caps verified dll==dpl vanilla before patch.

**Inherent-level follow-up fix (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_inherent_level_fix_v1.py`, backup AoWEPACK.dll.bak_inherent_fix).** The leadership disable-bug fix (cave_abinherent, compares ability VMT+0x94 GetInherentLevel in UpdateDefaultAbilities) silently broke level purchases/rank-grants for the TWO leveled abilities with own machinery + base GetInherentLevel (returns 0 → 0 vs 0 → grant skipped; points spent, no level — found in-game buying TU V). Full 70-VMT sweep confirmed only these two:
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 1F290 | 0x5571FE90 | dword 0x5574E954 → 0x5576AE8C | TTurnUndeadAbility VMT+0x94 → own GetLevel |
| 21408 | 0x55721E0C | dword 0x5574E954 → 0x5576CEFC | TDispelMagicAbility VMT+0x94 → own GetLevel |
Rule for future: **any leveled ability must have a real GetInherentLevel at VMT+0x94** or UpdateDefaultAbilities grants skip. ML-based abilities are fine (ML overrides +0x94). Trap-check: VMT+0x70 ≠ base 0x5574E9B0 while VMT+0x94 == base 0x5574E954.

**Dispel Magic IV + V (applied 2026-07-20; script `patch_dispelmagic5_v1.py`, backup AoWEPACK.dll.bak_dispelmagic5; REQUIRES inherent-level fix).** Vanilla cap was 3! **NO mana cost — "GetDispelMana" (10L+20) is a power rating only.** TEnchantment.DispelChance @0x5577C19C: chance% = clamp(dispelValue − 10×ench[+0x14] + 50, 10, 90) = 10×(dispelLvl − enchRating) + 70 clamped 10–90%, rolled vs Random(100) per enchantment. Each level = flat +10%/enchantment up to the 90% cap. Skill cost flat 1/level (vanilla ExpandCost).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 6C563 | 0x5576D163 | imm 3→5 | CanExpand cap |
| 6C5D0 | 0x5576D1D0 | imm 3→5 | Expand increment cap (`cmp byte [data+0xD],3`) |
| 6C361 | 0x5576CF61 | E9 → cave_dm5name | GetLevelName dec-chain default (already a 5B near-jmp; EDX=level−3 at hook) |
| 10DA80 | 0x5580E680 | 88B cave (PIC) | " IV" (lit 0x557BBF40) / " V" (0x5576DE04) via LoadResString(DispelMagicRStr 0x55709AEC)+Translate+LStrCat3; else default 0x5576CFF8 |
Facts: DM id 0x3C, icon [0x5576CE08]=0x241; data record TDispelMagicAbilityData: +0xC = per-turn enabled TOGGLE, **+0xD = level** (no-record → level 1); GetDispelMana @0x5576CEA8 = 10L+20, called from all 3 dispel paths (fcExecuteCombatCommand, CreateCA, strategic TE @0x5576D866 loop: per-enchantment DispelChance(ench, strength) vs TAoWHSMap.Random(100)) → NO value-ladder patches needed, levels scale automatically; ExpandCost = flat `mov eax,1`; Expand quirk: post-inc ==1 → bumped to 2 (level-0 toggle-created records).

**Healing I/II/III = 5/7/10 HP (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20 incl. v1b cost fix; script `patch_healing_leveled_v1.py`, backup AoWEPACK.dll.bak_healing_lvl; REQUIRES lifesteal-leveled patch — calls its generic cave_lsnames 0x5580E2A0).** Healing id 0x2F, THealingAbility : TTouchAbility (VMT file 0x20BBC / VA 0x557217BC), NOT ML-based — level machinery added TU/DM-style. Level stored at THealingAbilityData+0xD (byte; +0xC stays transient used-flag; no rec or 0 → level 1 → legacy/authored healers = 5 HP = vanilla). Data RW gains tagged byte field 0xB (clone of TDispelMagicAbilityData.ReadWrite) — old saves load fine (missing tag → 0 → level 1). Cost: 5/level — vanilla [self+0x14]=5 (confirmed in-game via display); cave_expcost returns [self+0x14] (10 fallback if 0). **RULE (v1b bug): level-up CHARGE = GetSkillPoints DELTA, dialog DISPLAY = ExpandCost — a leveled ability's GetSkillPoints must be level×ExpandCost or display≠charge** (v1 had level×10 → charged 10, showed 5; fixed 2026-07-20: cave_skillpt = level×[self+0x14], 14B). Heroes buy at level-up (mask gate [self+0x20]=0x241 kept, same classes as Dispel Magic).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 20C2C/20C50 | VMT+0x70/+0x94 | → cave_getlvl 0x5580E720 | GetLevel + GetInherentLevel (HasAbility→0; rec+0xD, 0→1, cap 3) — satisfies inherent-level rule |
| 20C3C | VMT+0x80 | → cave_skillpt 0x5580E7B0 | GetSkillPoints = level×[self+0x14] (v1b; delta = charge, must equal ExpandCost) |
| 20C80/20C84/20C88 | VMT+0xC4/C8/CC | → caves 0x5580E770/E7A0/E7C0 | CanExpand (mask & level<3) / ExpandCost / ExpandName (level+1 via cave_lsnames) |
| 20C8C/20C90 | VMT+0xD0/+0xD4 | → cave_expand 0x5580E7F0 / cave_remove 0x5580E870 | Expand (create rec: enabled=1, level=hasbit?2:1, PIC classref [0x55721550]; else inc +0xD cap 3) / Remove (level>1 → dec, else orig 0x5576C04C) |
| 20C94/20C98 | VMT+0xD8/+0xDC | → cave_est1 0x5580E8A0 / cave_est2 0x5580E8F0 | strategic AI value fns rewritten leveled (EDX=healer, ECX=target; min(maxHP−HP, amt)×100; est2 out-rec word +0x10=0x200) |
| 209A8 | DataVMT+0x18 | → cave_datarw 0x5580EAB0 | ReadWrite: parent + tag 0xA byte(+0xC via stream+0x38) + tag 0xB byte(+0xD via stream+0x30) |
| 6B774 | 0x5576C374 | 53 56 8B F2 33 DB → E9+NOP | HealUnit → cave_heal 0x5580E9B0 full rewrite; NEW CONTRACT: EAX=healer strategic unit (was unused flyweight). Heals min(missing, 5/7/10), cures 0x60/0x35/0x6C, update via vmt+0x90 |
| 6B124 | 0x5576BD24 | GetAbility(0x2F) 21B → 8B 47 4C + 18 NOP | THealingCA.Execute passes healer [edi+0x4C] (EDI=attacker combat unit) |
| 6BB8D | 0x5576C78D | 8B C5 → 8B C6 | THealingTE.Execute passes healer ESI (strategic) |
| 6B71F | 0x5576C31F | call GetHealHitPoints 0x5576C074 → call cave_esthp 0x5580E970 | combat estimator (+0xE4): healer combat read from caller frame [ebp-4] → [+0x4C] strat; GetHealHitPoints now dead code |
| 6B3BF | 0x5576BFBF | mov eax,edi; mov edx,[ebx+8]; call LStrLAsg (10B) → call cave_gnplain 0x5580EA90 + 5 NOP | GetName plain branch → "Healing I/II/III"; "(used)" Format branch untouched (shows unsuffixed) |
| 10DAE0–10DEE1 | 0x5580E6E0–0x5580EAE1 | 14 caves | healamt/E6E0(53B: rec+0xD→5/7/10, nil-safe, preserves ecx/edx), getlvl/E720(73B), canexp/E770(46B), expcost/E7A0(13B), skillpt/E7B0(11B), expname/E7C0(34B), expand/E7F0(124B PIC), remove/E870(45B), est1/E8A0(75B), est2/E8F0(127B), esthp/E970(62B), heal/E9B0(224B), gnplain/EA90(20B tail-jmp lsnames), datarw/EAB0(50B) |
Facts: healing amount was flat 5 inlined in 4 fns (HealUnit 0x5576C374 REAL heal for both combat CA + strategic TE; GetHealHitPoints 0x5576C074 combat est; +0xD8 0x5576C214 / +0xDC 0x5576C258 strategic est). THealingCA.Execute heals the TARGET'S STRATEGIC twin via HealUnit. Used-flag lifecycle: SetEnabled(unit,0) on use (rec +0xC=0); re-enable via +0xAC fn 0x5576BF58 (sets +0xC=1, rec kept → level survives); rec deleted ONLY by Remove (+0xD4, orig 0x5576C04C = base bit-remove 0x5574E91C + RemoveData 0x5574F2B8) — cave_remove decrements level >1 first, only tail-jmps to orig full-remove at level ≤1. GetEnabled default (no rec) = enabled.

**Charge I/II/III (+2/+3/+4 DMG) & Parry I/II/III (−2/−3/−4 ATK) (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_charge_parry_leveled_v1.py`, backup AoWEPACK.dll.bak_charge_parry; REQUIRES lifesteal-leveled patch — reuses cave_mlcreate 0x5580E200 + generic cave_lsnames via ML VMT+0x10C).** Charge=0x6F (initiating side's first melee strike, dmg bonus), Parry=0x71 (defender of each side's first strike, atk malus). Bonus = level+1, level 0 (legacy bit-only) → 1. **Vanilla was INCONSISTENT: tactical +2/−2, fast combat +3/−3** — now uniform 2/3/4 (legacy units: tactical unchanged, fast combat 3→2). Cost 3/level since same-day retarget to cave_mscost (ML flat list; ML ExpandCost & GetSkillPoints consistent for flat lists — no healing-style display bug: skillpts = level×cost[level], delta = cost ✓).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 6673F/667A9 | 0x5576733F/0x557673A9 | call factory 0x5576727C → cave_mscost (was cave_mlcreate; retargeted 2026-07-20, script `patch_charge_parry_cost_v1.py`, backup .bak_chgpar_cost) | 0x6F/0x71 flyweights become ML (cap 3, cost 3/lvl); names "Charge/Parry I-III" automatic |
| 66FC6 | 0x55767BC6 | 84 C0 74 04 83 43 04 02 → call cave_chgmel + 3 NOP | TMeleeRound.CalculateStrikes charge (ESI=striker combat, EBX=strike rec; +0xB0 level post-+0xA8-gate) |
| 66FDD | 0x55767BDD | 84 C0 74 03 83 2B 02 → call cave_parmel + 2 NOP | tactical parry (EDI=defender) |
| 66C6E | 0x5576786E | 84 C0 74 04 83 43 04 03 → call cave_chgfast + 3 NOP | CalculateUnitStrikes (fast combat, STRATEGIC units, +0x144 level) charge |
| 66C85 | 0x55767885 | 84 C0 74 03 83 2B 03 → call cave_parfast + 2 NOP | fast parry |
| 10DEF0–10DF6B | 0x5580EAF0/EB10/EB30/EB50 | 4 caves 29/28/29/28B | AL-gated: re-test HasAbility result, GetAbilityLevel min 1, +1, apply to [ebx+4]/[ebx] |
Facts: strike-calc copies: TMeleeRound.CalculateStrikes 0x55767B24 (tactical, combat units +0xA8), CalculateUnitStrikes loop 0x55767811 (fast, strategic +0x148), autocombat DV fn has NO charge/parry. Strike rec = 20B: [0]=atk dw, [4]=dmg dw, [8]=hit%, [0xC]=side. First-strike guard: idx==0 OR (idx==1 && side≠initial). Charge gated to side 0 only (initiator). 0x557FA9xx & 0x55767600 = id-list registrations (no values); 0x55787B1E = AI upgrade picker via virtual CanExpand/ExpandCost (ML-compatible). Verified-inert: TStrikeAbility.Remove SE sweep no longer matches converted 0x6F/0x71 (same as 0x70/0x76).

**Ability cost retune (applied 2026-07-20; script `patch_ability_costs_v1.py`, backup AoWEPACK.dll.bak_ability_costs).** Hero Slaying 10→5 (3 imms in cave_hsreg @10D750/10D762/10D774), Monster Slaying 10→3 (NEW cave_mscost 0x5580EB70 wraps cave_mlcreate + re-Puts — mlcreate is SHARED, Life Stealing/Charge/Parry stay 10), Leadership 10→5 (imm in cave_lscosts @10D3FE), Turn Undead 5→3 (ExpandCost imm @6A4E7 + GetSkillPoints ×5→×3 lea @6A531). Costs summary now: DM 1 (vanilla), Marksmanship 3 (vanilla), MS 3, TU 3, Charge 3, Parry 3, Wall Crushing 3, HS 5, Leadership 5, Healing 5, Life Stealing 10. cave_mscost 0x5580EB70 = GENERIC ml-cost-3 wrapper (calls cave_mlcreate then Puts 3s) — used by MS/Charge/Parry; only Life Stealing still uses cave_mlcreate directly (10/lvl).

**Wall Crushing I/II/III = dmg 2-5 / 3-10 / 4-15 (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20 incl. v1b preview fix; script `patch_wallcrush_leveled_v1.py`, backup AoWEPACK.dll.bak_wallcrush_lvl; REQUIRES healing-leveled (reuses generic cave_hlcanexp 0x5580E770 + cave_hlexpname 0x5580E7C0) + lifesteal-leveled (cave_lsnames)).** WC id 0x75 (TWallCrushingAbility : TTouchAbility, VMT file 0x20714). Touch attack keeps ATK 6; DMG = 5×level (5/10/15) — engine damage roll vs wall def 0 yields exactly 2-5/3-10/4-15. Legacy bare-bit = level I (vanilla DMG 6 rolled 2-6 → max drops 6→5). Level in GENERIC ML-data rec (classref [0x5571DEB8], id word rec+0xE, level rec+0xC — TU pattern, save-persists; old saves → level I). Cost: **flat 3/level since 2026-07-20 cost tweak, CONFIRMED in-game (displays & charges 3)** (cave_wcexpcost @10E050 rewritten `mov eax,3; ret`, backup .bak_wallcrush_cost; was [self+0x14]-else-3); skillpts = level×cost (auto-follows).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 2076C/20784/20794/207A8 | VMT+0x58/+0x70/+0x80/+0x94 | → wcgetname 0x5580EC80 / wclvl 0x5580EC00 ×2 / wcskillpt 0x5580EC60 | name "Wall Crushing I-III"; GetLevel+Inherent (HasAbility→0, rec+0xC min1 cap3); level×cost |
| 207D8/207DC/207E0 | VMT+0xC4/C8/CC | → 0x5580E770(reuse) / wcexpcost 0x5580EC50 / 0x5580E7C0(reuse) | CanExpand mask+cap3 / cost / ExpandName |
| 207E4/207E8 | VMT+0xD0/+0xD4 | → wcexpand 0x5580ECB0 / wcremove 0x5580ED30 | Expand (create ML-data rec id=0x75, level=hasbit?2:1, PIC classref; else inc cap 3) / Remove (TU-clone: dec >1, full remove at 1) |
| 207EC/207F0 | VMT+0xD8/+0xDC | → wcest1 0x5580ED90 / wcest2 0x5580EDF0 | strategic estimators REWRITTEN (owner EDX → wclvl5s dmg; types 0x101/0x100; atk 6 kept; value 0x55726094(EAX=atk,EDX=dmg), hit 0x55725FE0) |
| 67CF7 | 0x557688F7 | mov ecx,6 → call wcexec 0x5580EEB0 | fcExecuteCombatCommand: cave overwrites pushed DMG at [esp+8] with 5×level([esi+0x4C]), restores ecx=6 ATK. CA factory 0x55729F18: ECX=ATK, 1st push=DMG, 2nd=types |
| 67B52 | 0x55768752 | mov edx,6 → call wcestdmg 0x5580EED0 | +0xE4 combat estimator: owner combat at [ebp-8] → +0x4C → 5×level; preserves CX |
| 20818 | VMT+0x104 | 0x557688A8 → cave_wcinfo 0x5580EEF0 | **v1b preview fix**: GetCombatInfo record ([+1]=ATK byte, [+2]=DMG byte, [+3]=types word, [+5]=range, [0]=flags) was hardcoded 6/6 ignoring EDX=unit; cave: ATK 6, DMG=5×level (script `patch_wallcrush_preview_v1.py`, backup .bak_wallcrush_preview) |
| 67C32 | 0x55768832 | mov edx,6 → call wcestdmg | v1b: third combat estimator (+0xEC, ret 4 variant, same [ebp-8]=owner frame) leveled |
| 10DFC0–10E2E3 | 0x5580EBC0–0x5580EEE3 | 11 caves | wclvl5s/EBC0(49B: strat unit|nil → 5×clamp(lvl,1,3), preserves ecx/edx), wclvl/EC00(73B), wcexpcost/EC50, wcskillpt/EC60, wcgetname/EC80, wcexpand/ECB0(128B PIC), wcremove/ED30(85B), wcest1/ED90(96B), wcest2/EDF0(188B), wcexec/EEB0(18B), wcestdmg/EED0(20B) |

**Minimum 1 XP per kill (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20; script `patch_xp_min1_v1.py`, backup AoWEPACK.dll.bak_xp_min1).** Fixes 0-XP kills (victim 3+ effective levels below killer). 2-byte hook + 10B stub INSIDE the pre-Claude XP cave:
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 10B675 | 0x5580C275 | 00 C8 (add al,cl) → EB 1E | jmp to stub at gain/curXP merge (only kill path with delta>0 reaches it; gain=0 only in the diff≥3 & victim-lvl-1 case) |
| 10B695 | 0x5580C295 | 00*10 → stub | test al,al; jnz+; inc al; add al,cl; jmp 0x5580C277 (fills the old 11B free gap before pool caves). **SUPERSEDED 2026-07-20 by capxp2x: now jmp cave_merge2 0x5580EFD0 (min-1 + capped-victim ×2 live there)** |
**Post-gold HP cap + XP overflow fix (applied 2026-07-20, NOT YET GAME-TESTED; script `patch_hp_cap_v1.py`, backup AoWEPACK.dll.bak_hp_cap; REQUIRES xp-min1).** Fixes "80/25 HP" + medal-loss bug and caps leveling HP at base×3/2.5/2/1.5 for tiers 1-4.
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 10B215 | 0x5580BE15 | pre-Claude GetMaxHP cave (48B) REWRITTEN (57B, region 0x6B to 0x10B27F) | MaxHP = min(base[res+0x2C] + 2×(XP/10), base×(7−tier[res+0x2F])>>1). Old cave: base + 2×(XP/10) uncapped (vanilla dpl was base + BSS table[0x558E83D4+medal]) |
| 81CC5 | 0x557828C5 | 81 FF 64 00 00 00 7E 05 BF 64 00 00 00 → 13 NOP | TUnit.SetExperience 100-clamp removed — stored XP >100 made byte delta (proposed−current) wrap to garbage victim-levels → runaway XP |
| 10B686 | 0x5580C286 | 3C 14 EB 02 90 90 (dead vanilla cap) → 38 C8 73 02 B0 FA | XP cave wrap-guard: cmp al,cl; jae store; mov al,0xFA — new<old ⟺ byte overflow → pin 250. XP monotonic ≤255, medals/MaxHP never drop |
Root cause chain: hero victims NOT excluded from unit kill-XP (the 0x80/0x81 DoDamage check is dead in AoWx — heroes don't carry 0x80), hero kill → (heroLvl+1−unitLvl)×5 XP → >100 → byte chaos → wrap at 256. TUnit fields: +0x3C XP byte, +0x3E cur HP byte (SetHitPoints clamps vs GetMaxHP), +0x40 resource (+0x2C base HP, +0x2F tier). Old-save units with curHP>new cap show over-max until next HP change (self-heals). Also decoded: 2nd pre-Claude cave 0x5580BE80 (hero-kill XP tiering — REWRITTEN v2 by medal-killxp patch 2026-07-20, see below; caller 0x55787675); vanilla ExperienceToLevel (XP/10 uncapped) was pre-Claude-replaced with medal cap 2 @0x5578294C.
**⚠ TOOLING RULE (hard-won 2026-07-20): Python bytearray slice assignment with mismatched length INSERTS/DELETES bytes (shifts the whole file!) — first hp-cap attempt inserted 9 bytes (57B cave into 48B slice) corrupting everything past 0x10B215; caught via file size + misaligned disasm, restored from .bak_hp_cap. ALWAYS assert len(new)==len(slice) and file size unchanged.**

**Pre-Claude XP cave DECODED (0x5580C200, file 0x10B600, called from TUnit.SetExperience 0x557828B4 — AoWx custom XP formula):** inputs ESI=unit, EDI=newXP (delta=EDI−[esi+0x3C] = victim level, from DoDamage kill tail 0x55726B6F: killer.XP += victim.GetUnitLevel). Killer effective level = base tier [[esi+0x40]+0x2F] +1 if XP≥10 (silver) +1 more if XP≥20 (gold). Gain: victim < killer → diff 1→2 XP, 2→1, ≥3→0 (NOW MIN 1); floors: victim lvl≥4→5, ≥3→min 2, ≥2→min 1. victim ≥ killer → (victim+1−killer)×5. Crossing 10 XP: excess halved. XP clamp 100 (SetExperience), stored [unit+0x3C] byte. Heroes excluded from this path (DoDamage skips victims with 0x80/0x81; hero XP separate).

**HP-cap medal icon (applied 2026-07-20, NOT YET GAME-TESTED; script `patch_medal_icon_v1.py`, backup AoWEPACK.dll.bak_medal_icon; REQUIRES hp-cap patch + user-added Combat.ilb index 8).** Unit's medal icon becomes index 8 when max HP hits the cap (else silver 5 / gold 6 as before).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 81B12/81B3B | 0x55782712/0x5578273B | mov edx,5 / mov edx,6 → call cave entry5/entry6 | THE shared unit-card medal painter (serves all displays): TUnit.GetRank branch @0x557826F5, image list [0x558FA044]+0x50, GetImage 0x55702934(EAX=list,EDX=idx), draw vmt+0x84; EBX=TUnit at both sites |
| 10E310 | 0x5580EF10 | 74B cave | entry5(+0)/entry6(+7) set default; common(+12): capped ⟺ base+2×(XP/10) ≥ base×(7−tier)>>1 → EDX=8; preserves eax/ecx/esi/edi |
Facts: **medal display = ONE shared painter in AoWEPACK** (fn ~0x557826xx, gated `test byte [esi+1],2` display-flag); TUnit.GetRank (=ExperienceToLevel 0x5578294C) is EXPORTED by name but imported by NO module — displays all go through this painter. Other `edx=5` GetImage sites (0x5579FB47/0x557EA02F/0x557EA93D use [0x558E92E8]+0x48 list; 0x55773409 uses [0x558FA044]+0x48) are DIFFERENT image lists, not medals. Rank bonus tables: atk [0x558E83C4+rank], def [0x558E83CC+rank], res? [0x558E83C8+rank] (patched w/ call 0x5580D800 pre-Claude), dmg [0x558E83D0+rank], vanilla maxhp table [0x558E83D4+rank] (dead since pre-Claude GetMaxHP cave).

**HP-cap fine-tune: min one level past gold + capped ATK/RES bonus (applied 2026-07-20, NOT YET GAME-TESTED; script `patch_capfinetune_v1.py`, backup AoWEPACK.dll.bak_capfinetune; REQUIRES hp-cap + medal-icon patches — REWRITES both their caves).** Effective HP cap = **max(base×(7−tier)>>1, base+6)** — base+6 ⟺ XP 30 ⟺ ≥10 XP past gold before capping (base 7 tier4 → 13 HP, base 10 tier4 → 16 HP). Units AT the cap get **+1 ATK, +2 RES** (and medal icon 8).
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 10B215 | 0x5580BE15 | GetMaxHP cave v3 (64B) | effcap = max(cap, base+6) inline |
| 10E310 | 0x5580EF10 | medalicon cave v2 (25B) | entry5/entry6 defaults; call cave_iscap; JAE→edx=8 |
| 10E360 | 0x5580EF60 | cave_iscap 62B | (EBX=TUnit) → flags: **JAE=capped, JB=not** (cmp uncapped,effcap then flag-preserving pops); preserves eax/ecx/edx/edi |
| 10E3A0 | 0x5580EFA0 | cave_atkwrap 15B | call 0x5580D800 (pre-Claude atk chain: 3 sub-caves 0x5580D820/D840/D860 + base atk [res+0x29]) → capped? inc al |
| 10E3B0 | 0x5580EFB0 | cave_rescap 15B | rank-res add al,[edx] → capped? al+=2 → movsx edx,al (1..50 clamp still runs after) |
| 81DE4/81E00 | 0x557829E4/0x55782A00 | E8 rel32 retargets → cave_atkwrap | BOTH TUnit GetAttack getters (inherent 0x557829D0 / effective +0xC0 0x557829EC) |
| 81F18 | 0x55782B18 | 02 02 0F BE D0 → call cave_rescap | TUnit.GetResistance (+0xCC, 0x55782AE8) tail |
**STAT GETTER MAP (verified via combat routing +0x6C/70/74/78 → strategic +0xC0/C4/CC/C8):** TUnit strategic VMT: **+0xC0 GetAttack** (rank tab [0x558E83C8], base [res+0x29] added by pre-Claude cave 0x5580D800, enchant [unit+0x44]), +0xC4 GetDefense (tab [0x558E83C4], base [res+0x2A], ench +0x45, parapet tab [0x558E83E0+0x5577F178()]), +0xC8 GetDamage (tab [0x558E83CC], base [res+0x2B], ench +0x47), **+0xCC GetResistance** (rank tab [0x558E83D0], base [res+0x2E], ench +0x46, extra tab [0x558E83D8+0x5577F178()]), +0xD0 GetMaxHP. Inherent variants: atk 0x557829D0, def 0x55782A24, dmg 0x55782A8C. Effective getters clamp 1..50. Enchant mod bytes [unit+0x44..0x47] refreshed by 0x55782B34.

**Capped-medal victims grant +10 kill XP (was ×2 until 2026-07-20; changed to flat +10 per user, backup .bak_capxp_plus10; CONFIRMED WORKING in-game 2026-07-20). Capped = gold gain +10 (fresh L3 vs L4: gold 20 → capped 30) (applied 2026-07-20, NOT YET GAME-TESTED; script `patch_capxp2x_v1.py`, backup AoWEPACK.dll.bak_capxp2x; REQUIRES xp-min1 + hp-cap + capfinetune).** Victim-side flag: DoDamage kill tail (victim level fetch @0x55726B7F, 11B → call cave_victimxp 0x5580F000/50B + 6 NOP) sets bit 7 on level when victim = capped TUnit (GetUnitType +0x114 excludes heroes/leaders; cave_iscap tests cap; EBX killer-XP accum preserved). XP cave strips flag → DH=1 (cave_flag 0x5580EFC0/10B via old dead slot @0x10B619; **DH survives the whole gain path**: inc edx medal adj no byte-carry, branches touch only DL/AH, mul ah writes AX only). Merge: old min-1 stub @0x10B695 → jmp cave_merge2 0x5580EFD0/19B: min-1 → DH? gain×2 → add al,cl → 0x5580C277 (silver-halving + wrap-guard still run after ✓). Non-kill SetExperience deltas ≥128 would false-flag (pre-existing script-grant quirk domain, accepted).

**GetRank unsigned fix (applied 2026-07-20; script `patch_rank_unsigned_v1.py`, backup AoWEPACK.dll.bak_rank_unsigned).** Pre-Claude TUnit.GetRank (=ExperienceToLevel 0x5578294C) used SIGNED `jl` on the XP byte → XP≥128 read negative → rank 0 → medal icon (incl. capped icon 8) AND silver/gold rank stat bonuses lost, while cap logic (movzx) kept working. Fix: 2 bytes, `jl`→`jb` @0x81D55/0x81D5A. **RULE: any byte-field compare in caves/patches must use UNSIGNED jcc (jb/jae) — XP byte legitimately reaches 250.** GetNextLevelExperience (0x55782920) verified unsigned (returns 10/20 — XP>20 shows "X/20", cosmetic vanilla quirk).

**Victim medals count toward kill XP — units AND heroes (applied 2026-07-20, NOT YET GAME-TESTED; script `patch_medal_killxp_v1.py` (verify-only), backup AoWEPACK.dll.bak_medal_killxp; REQUIRES capxp2x chain).** cave_victimxp v2 (0x5580F000/66B, region zeros verified to 0x10E460): victim effective level = tier + GetRank(strategic victim) for TUnit victims (heroes/leaders raw), then |0x80 capped flag — ONE source feeds unit-killer XP cave AND hero SetExperience. Unit numbers (plain L3 killer vs L4 victim): silver 15 / gold 20 / capped 40 via (tier+rank+1−killer)×5 ×2. **Hero XP tier cave (pre-Claude, 0x5580BE80) REWRITTEN v2 (93B/112B region 0x10B280–0x10B2EF):** keeps delta≤0 direct-store + dh==0xFF raw-add escape; strips 0x80 capped flag; ladder eff-level 1/2/3/4/≥5 → +1/+5/+15/+25/+50; capped → ×2 (silver-1 kill +5, gold-1 +15, capped-1 +30, capped-4 +100). Caller: THero.SetExperience @0x55787674 (call @0x55787675; [hero+0x48]=dword hero XP; cave clobbers ESI as original did). Victim-medal floors also raise the unit-cave's < branch floors (bl incl. rank) — intended.
**v1b (2026-07-20, backup .bak_killxp_sites): THREE MORE kill-XP award sites found & hooked — there are FOUR total, all `killer.GetXP([+0x98]) + victim.GetUnitLevel([+0xA0])&0xFF → SetXP([+0x9C])`:** (1) TCombatUnit.DoDamage tail 0x55726B7F (victim ESI, direct→cave_victimxp); (2) damage-CA kill 0x5572A00C (victim ESI, direct); (3) kill-CA 0x5576FCB8 (victim EDI → wrapper cave_vicxp_edi 0x5580F050/10B @0x10E450: push esi/mov esi,edi/call/pop); (4) 0x557F8473 (victim EDI, wrapper; killer=[esp]). Original patch only hooked (1) → tactical/CA-dependent paths bypassed victim rank — user-observed. Sweep pattern `FF 9? A0 00 00 00 25 FF 00 00 00` now clean (only our cave remains). All 11-byte sites → E8+6 NOP.

**⚠ CORRECTION (2026-07-20): 0x22 = TTurnedUndeadAbility, 0x6B = TPossessedAbility — NOT medals! Medals are PURELY XP-based (GetRank 0x5578294C: XP≥10→silver, ≥20→gold; verified by emulation). The v3 "ability medal" check was checking the wrong abilities (bug: killing a possessed/turned-undead victim gave spurious XP). REVERTED to v4 (GetRank-only, 64B, backup .bak_victimxp_v4). The 0x55787094 `has 0x6b→image 5` is a Possessed-unit indicator, not a medal.**
**ACTUAL BUG FOUND & FIXED — cave_victimxp v5 (2026-07-20, backup .bak_victimxp_v5).** The combat unit DOES carry the victim's medal XP (diagnostic: unconditional [victim+0x4C].XP read gave 185XP = level4+XP35 for a medal'd leprechaun). The bug: cave_victimxp had a **GetUnitType(+0x114) guard** (meant to skip heroes/leaders → raw level) that ALSO fired for regular units whose resource byte [res+0x30]==0 (leprechauns and apparently many units) → jumped past GetRank → returned raw tier, ignoring the medal. **FIX: NOP'd the 16-byte GetUnitType block @0x10E477 (VA 0x5580F077) so GetRank runs for ALL non-nil victims.** Emulation (leprechaun-like victim, GetUnitType byte=0): no-medal→L4, silver→L5, gold→L6, capped→L6+flag → fresh-L3 killer gains 10/15/20/40 ✓. (Earlier "COMBAT UNITS DON'T CARRY XP" conclusion below was WRONG — misled by diagnostic-2 which read XP only on the post-guard main path, and by diag-3's raw-XP values overflowing/colliding with the store-cave 0x80 flag. GetUnitType-byte-0 units are common, NOT just heroes; my [[aowx-re-reference]] note 'GetUnitType==0 means hero/leader' is too narrow.) NOTE: hero VICTIMS now also get GetRank added (minor over-count, acceptable; heroes rarely victims). Diagnostics reverted. **CONFIRMED WORKING in-game 2026-07-20 — victim medals now grant scaled kill XP (10/15/20/40 for none/silver/gold/capped) in both tactical AND autocombat.** Throwaway diag backups deleted; .bak_victimxp_v5 kept.

**ROOT CAUSE FOUND (2026-07-20, via in-game diagnostics): COMBAT UNITS DO NOT CARRY THE MAP UNIT'S XP.** Diagnostic proof: (1) cave_victimxp +20-to-level → kills gave 110XP in BOTH modes = cave IS on the kill path ✓. (2) cave reads [victim_combat+0x4C].XP byte directly → 0 even for a capped/maxed-XP victim in both modes. So the combat unit's [+0x4C] TUnit is a COMBAT INSTANCE with XP=0 (tier/resource preserved, XP not), decoupled from the map unit that holds the earned medal. GetRank([victim+0x4C])=0 → cave correctly returns raw tier → medal invisible. **Medals (XP-based: GetRank/GetMaxHP/icon all read [+0x3C]) live ONLY on the strategic map unit; combat instances start XP 0 (battle-XP-gained model, committed to map at combat end). IMPLICATION: the user's whole medal HP-bonus system likely affects only the strategic map, not in-combat stats (combat unit GetMaxHP via [+0x4C].XP=0 → base HP).** TCombatUnit.SetUnit 0x55725194 sets [+0x4C]=passed unit (only E8-caller is fast-combat thunk 0x55743AC4; tactical sets via vtable). **TO FIX victim-medal kill XP: must locate the combat-instance→map-unit link (for GetRank on the real unit) — NOT yet found; combat→map write-back at combat end would reveal it. Diagnostics reverted; cave = clean v4 (GetRank on [+0x4C], correct but sees XP 0 in combat). Confirmed-working & kept: min-1 XP, halving removed, HP cap, medal icons, stat bonuses (all strategic-map-side).**

**INVESTIGATION UPDATE (2026-07-20): kill XP = (rawVictimLevel+1−killerEffLevel)×5 via store cave 0x5580C200 — CONFIRMED shared by unit killers (killerLevel=tier) AND hero killers (killerLevel=0: hero L4-victim=25=(4+1)×5). min-1 works (store cave reached). BUT victim counted as RAW tier even for a capped/maxed-XP victim (user test: leprechaun killed L10 hero → capped/maxHP; then DISBANDED + killed by fresh L3 cavalier → cavalier got 10 = raw, SAME as killing a fresh leprechaun). cave_victimxp reads GetRank([victim_combat+0x4C]) → returns 0 at kill time despite the unit having earned max XP. combat +0xa0 (GetUnitLevel) on same [+0x4C] returns the tier correctly → so [+0x4C] is valid but its XP byte reads 0. **CONFOUND: all user tests used DISBANDED units (TAbstractUnit.Disband 0x557825FC → TDisbandUnitTE) to make own units attackable — disband/reassign may reset or not-carry the XP byte, making GetRank=0 CORRECT. NEED a non-disband test (hotseat: earned-medal victim killed by opponent's fresh unit) to determine if it's (a) disband invalidating the test [fix already works] or (b) combat uses XP-stripped strategic copies [need a different rank source than [+0x4C].XP].** All XP paths verified routing through store cave; cave_victimxp/GetRank/full-DoDamage all emulate correct (gold→20). Binary clean: v4 cave (GetRank-only), halving removed, GetRank unsigned all intact.**

**UNRESOLVED: user reports tactical melee kill XP ignores medals (gives raw 10 for L4 regardless) AND differs from autocombat (L10 hero: tactical→~20/gold, auto→~40/capped). GetRank + full-DoDamage emulation both give correct medal XP (gold L4→20, hero→40), so EITHER the victim's combat-time strategic lacks XP≥threshold (copy-pasted editor units may not carry XP byte → medal shown via another mechanism? OR combat uses XP-stripped copies) OR tactical melee uses an XP path NOT among the 4 hooked combat sites (TCombatObject.DoDamage 0x55726B7F, TDamageEffectCA 0x5572A00C, TCommandCA 0x5576FCB8, TMindDecayCA 0x557F8473 — all verified routing to cave). Combat XP architecture: all combat +0x9c SetXP → strategic +0x160 → store cave 0x5580C200. Next: determine if victim XP survives into tactical combat, and find the actual tactical melee award (hero-kill giving XP despite it being a hero rules out the 0x80/0x81 skip being relevant). NEED: does an EARNED-medal (not copy-pasted) victim give the bonus in autocombat?**

**cave_victimxp v3: count ability-granted medals (applied 2026-07-20, backup .bak_victimxp_v3).** ROOT CAUSE of "tactical kill XP ignores medals / always 10": medals exist in TWO forms — earned (XP byte → GetRank) and **ability-granted (0x6B=silver, 0x22=gold; editor-placed or ability-based units)**. The v1/v2 cave derived rank only from GetRank(XP) → ability-medal victims read rank 0 → no bonus. Confirmed: earned-medal victims (XP≥10/20) ALWAYS worked via DoDamage (emulated: earned-gold L4 → killer +15/+20); only ability-medal victims failed. **v3 cave_victimxp (128B @0x10E460, VA 0x5580F060): rank = max(GetRank(XP), 0x22?2 : 0x6B?1 : 0) via strategic GetAbilityEnabled +0x148; then |0x80 if capped.** All 4 kill sites repointed to v3 (DoDamage 0x25F7F, CA 0x2940C direct; wrapper 0x10E450 for the two EDI sites); old caves 0x5580F000/F050-inner now dead. Emulation-verified (unicorn) editor-silver/gold(xp0)→L5/L6, earned→L5/L6, capped→L6+flag, EBX preserved. NOTE: kill sites confirmed COMPLETE via `FF 9? A0000000 25FF000000` sweep (exactly 4). **Remaining vanilla nuance (NOT changed):** XP-store cave crossing-10 halving (`total≥10 & killerXP<10 → 10+(total−10)/2`) reduces a FRESH killer's first big kill (gold 20→15, capped 40→25); veteran killers (XP≥10) get full 15/20/40. Remove halving @0x5580C277-84 if full value on first kill is wanted.
**HALVING REMOVED (applied 2026-07-20, backup .bak_no_halving): 1 byte @0x10B67A (VA 0x5580C27A) `jae 0x5580C286` (73)→`jmp` (EB)** — always skips the crossing-10 halving; wrap-guard (0x5580C286 cmp al,cl/pin 250) kept. Emulation-confirmed FRESH L3 killer vs L4: plain +10, silver +15, gold +20, capped +40 (exact targets). Veteran killers gain less (higher effective level → smaller victim−killer gap; e.g. XP-15 L3 killer = silver rank = eff level 4 → gold victim +15) — intended level-difference scaling. Affects ALL SetExperience XP gains, not just kills (halving was general diminishing-returns).

**Morale debuffs ATK/RES instead of DEF/RES; Terrible = -3 (applied 2026-07-20, CONFIRMED WORKING in-game 2026-07-20 after v1b PIC reloc fix; script `patch_morale_atk_res_v1.py`, backup AoWEPACK.dll.bak_morale_atkres).** Vanilla morale modified DEF+RES via runtime-init tables 0x558E83E0(def)/0x558E83D8(res), indexed by morale level 0-4 (GetMorale 0x5577F178 = MoraleValueToMorale[unit+0x26]; value ≤20→L0 Terrible, 21-40→L1 Poor, 41-60→L2 Okay, 61-80→L3 Good, >80→L4 High). New: my own table MYMORALE=[-3,-2,-1,0,0] @0x5580F0A0 → applied to ATK & RES; DEF morale removed (repointed to ZEROTAB @0x5580F0A5). Emulation-confirmed value→modifier: Terrible -3, Poor -2, Okay -1, Good/High 0. Both TUnit & THero, EFFECTIVE getters only. **RELOCATION BUG FOUND & FIXED (v1b PIC, 2026-07-20, backup .bak_morale_prepic): the DLL loads at a non-preferred base (relocated at runtime). My caves' `movsx edx,[eax+0x5580F0A0]` used an ABSOLUTE address with NO .reloc entry → read wrong address → 0 in-game (RES/DEF repoints worked because their disp32s INHERITED the original .reloc entries from 0x558E83D8/E0). FIX: both caves rewritten PIC (call/pop delta: `call $+5; pop edx; sub edx,pop_link; movsx edx,[edx+eax+MYMORALE_link]`). cave_atkmorale 40B @0x5580F0B0, cave_heroatk 44B relocated to 0x5580F100 (hero hook 0x557883B1 jmp updated). LESSON: any absolute data address written into a hand-made cave MUST be PIC (call/pop delta) — raw disp32 fails under ASLR/rebase; only repointed EXISTING instructions inherit .reloc.** (Diagnostics: level-report showed correct morale level in-cave; isolate-read showed movsx returned 0 for all → pinpointed the reloc issue.)
| Offset | VA | Change | Purpose |
|--------|----|--------|---------|
| 10E4A0 | 0x5580F0A0 | 00*5 → FD FE FF 00 00 | MYMORALE table [-3,-2,-1,0,0] |
| 10E4B0 | 0x5580F0B0 | 27B cave_atkmorale | call cave_atkwrap; +MYMORALE[GetMorale(EBX unit)] |
| 10E4D0 | 0x5580F0D0 | 31B cave_heroatk | replay add al,dl; +MYMORALE[GetMorale(EBP hero)]; mov[esp],al; jmp 0x557883B6 |
| 55782AF7/5578856D | RES morale disp32 | 0x558E83D8 → 0x5580F0A0 | unit+hero GetResistance morale → MYMORALE (Terrible now -3) |
| 55782A6B/55788449 | DEF morale disp32 | 0x558E83E0 → 0x5580F0A5 | unit+hero GetDefense morale → ZEROTAB (0) |
| 55782A00 | unit eff GetAttack | call cave_atkwrap → cave_atkmorale | inject ATK morale (effective only; inherent 0x557829E4 untouched) |
| 557883B1 | hero GetAttack | 02 C2 88 04 24 (add al,dl; mov[esp],al) → E9 jmp cave_heroatk | inject hero ATK morale |
Facts: TUnit stat getters — GetAttack effective 0x557829EC(call@0x55782A00)/inherent 0x557829D0; GetDefense eff 0x55782A40; GetResistance eff 0x55782AE8. THero own getters: GetAttack 0x55788360, GetDefense 0x557883E8, GetResistance 0x5578850C. Morale only ever in EFFECTIVE getters (inherent/base exclude it). All effective stats clamp 1-50. Free space after: 0x10E4F0+ (~16B to 0x10E500, then unmapped-check).

(Raise Terrain patches REVERTED 2026-07-05 — failed attempt, see [[raise-terrain-underground]]. Regions 0xA2758/0xA29CB/0xA2A23/0x10B7C0 back to vanilla; Release.hss back to original.)

### Road-building cost 10→5 gold/tile (2026-07-23, bak_roadcost) — see [[road-build-cost]]
| Offset | From | To | Purpose |
|--------|------|----|---------|
| 704F5 | 0A | 05 | Actual gold charge @0x557710F3 (sub eax,10→5) per road tile |
| 70599 | 0A | 05 | UI cost prediction @0x55771195 (add [esp+4],10→5) "Constructing Road Costs X" |

### Road cost by decoration: open/light/bones=2, rocks/toadstools=3, veg/dense forest=5 (2026-07-23, CONFIRMED WORKING; bak_roadveg_final) — see [[road-build-cost]]
Supersedes the flat-5 above. cave_roadcost classifies via hex overlay [field+0x15] (255 open/9 light/1 forest) + decoration MO (found by MapFieldMsgProc==0x5579BE0C @vtable+0xCC) resource+0x44 category (rocks=1/bones=2/toadstools=4). ⚠️ scratch is in **writable BSS 0x558FA800** — a code-section scratch caused the "Exception during TArmyDefaultMoveTE" crash.
| Offset (VA) | From | To | Purpose |
|--------|------|----|---------|
| 0x5580F700 | 00* (117B) | cave_roadcost | field→cost 2/3/5; overlay + deco-MO(msgproc match)+cat |
| 0x5580F790 | 00* (14B) | cave_pred | UI: add [esp+8], roadcost([esp+0xC]) |
| 0x5580F7B0 | 00* (37B) | cave_capA | @actual: roadcost(esi=field)→scratch SC=0x558FA800(BSS); replay mov cl,[esi+0x10]/mov esi,[eax] |
| 0x5580F7F0 | 00* (23B) | cave_capB | @actual: replay movsx esi,bl/mov edx,esi; ebx=[SC] |
| 0x707B6 | 8a 4e 10 8b 30 | e8 →cave_capA | hook (field still in esi) |
| 0x707D8 | 0f be f3 8b d6 | e8 →cave_capB | hook (load cost into ebx) |
| 0x704F3 | 83 e8 05 | 2b c3 90 | sub eax,ebx (charge per-tile cost) |
| 0x70595 | 83 44 24 04 05 | e8 →cave_pred | UI prediction hook |
| (in cave) 0x5580F758 | 74 02 | 74 09 | toadstools je c5→c3 (cost 5→3) |

### MP default race → CPU Emperor (2026-07-23, applied, awaiting LAN test; bak_mprace) — see [[mp-default-race-cpu-emperor]]
| Offset | From | To | Purpose |
|--------|------|----|---------|
| E1798 | C6 40 08 05 | C6 40 08 07 | MP race-record builder: default owner Free(5)→CPU Emperor(7) (MP + non-map-assigned only) |
| E179F | C6 40 10 05 | C6 40 10 07 | same builder: default fallback type Free(5)→Emperor(7) (released race reverts to Emperor) |
| E0806 | 8B 15 58 8E 8E 55 | 8B 15 88 8E 8E 55 | ResetPlayerSettings remote branch reads pidCPU5(7) not pidFree(5); reloc @0x557E1408 kept |
Claim (UpdatePreferredRaces 0x557E1484) & host-Forced/map-assigned paths UNCHANGED — claim keys off rec[0xc]==0, not type byte [rec+8]. Enum: 0=Human,5=Free,7=Emperor.

### Arena train cost rework — v1, applied 2026-07-27, CONFIRMED WORKING in-game 2026-07-27
Script: patch_arena_cost_v1.py. Revert: AoWEPACK.dll.bak_arena (clean pre-feature).
Old: cost = 5 * (nextRankXP - curXP). New: **cost = (nextRankXP - curXP) * unitLevel * (1 silver-bound / 2 gold-bound)**
=> fresh unit->Silver = 10*level gold, fresh Silver->Gold = 20*level (rank thresholds 10/20 XP in TUnit.GetRank).
Heroes & gold-medal units were ALREADY -1/ineligible in vanilla TArena.UnitTrainCost (kept).
Hook: TArena.UnitTrainCost @0x557D6755 (`lea eax,[esi+esi*4]; jmp short` 8d04b6eb08 -> jmp cave), back to 0x557D6762.
Cave 32B @**0x5580FF00** (file 0x10F300): GetRank->movzx ecx,al->inc ecx; GetUnitLevel(0x55782B8C, returns AL only — movzx!)->imul ecx,esi. PIC (rel32 only).
esi=xpdiff survives (both getters preserve esi). All arena UI/exec paths funnel through UnitTrainCost.

### Arena XP fix — v1, applied 2026-07-27, CONFIRMED WORKING in-game 2026-07-27 (pairs with arena-cost rework)
Script: patch_arena_xp_v1.py. Revert: AoWEPACK.dll.bak_arenaxp (has cost rework, pre-XP-fix).
Problem: ExecuteTrainUnit called SetExperience(nextRankXP) but modded SetExperience (pre-Claude cave
0x5580C200) converts absolute sets into LEVEL-SCALED diminishing gains (+ XP-halving >10) => arena
granted wrong amounts. Fix: unit branch `call [ecx+0x160]` @0x557D67C5 (ff9160010000) -> call
**cave_arenaxp @0x5580FF20** (62B, PIC): clamp target to 20, write [unit+0x3C] DIRECTLY, then
replicate SetExperience's rank-up loop (per crossed rank: TAbilityOwner.UpdateDefaultAbilities
@0x5574F518 with owner=[resource+rank*4+0x38]). Caller's vtbl+0x90 Changed still refreshes.
Hero branch @0x557D678F untouched (heroes ineligible). Key RE: TUnit xp=[+0x3C] byte, rank
thresholds 10/20; resource ability owners base/silver/gold @+0x38/+0x3C/+0x40.

### Warmonger XP fix — v1, applied 2026-07-27, CONFIRMED WORKING in-game 2026-07-27 (REQUIRES arena-xp patch's cave)
Script: patch_warmonger_xp_v1.py. Revert: AoWEPACK.dll.bak_warmonger (has both arena patches, pre-warmonger).
Vanilla: City.TCityProductionControl.CreateUnitProduction — Warmonger city flag = [city(+0x28 of ctl)+0x5C] bit3
-> SetRank(unit,1)->SetExperience(10); modded scaled SetExperience made fresh units get ~27 XP.
Fix: `mov dl,1`@0x557A8DBA -> `mov dl,0x14`; SetRank call @0x557A8DBE -> **cave_warmonger @0x5580FF60**
(16B: call cave_arenaxp then TUnit.Changed via vtbl+0x90). Warmonger-produced units spawn at exactly
20 XP = Gold w/ medal abilities. Key RE: TUnit.SetRank(0x55782978, dl rank: 0->xp0, 1->SetExp(10),
2->SetExp(20)) — single caller was this production site.

## AoWx.exe (VA = file_off + 0x400C00)
| Offset | From | To | Purpose |
|--------|------|----|---------|
| 43511 | E9 E7 00 00 00 | E9 6A A2 02 00 | Side-window generic handler: jmp to RazePnl cave |
| 6BF80 | 00*28 | (cave 28B) | Show RazePnl if GetRazeable (see [[reflecting-pool-raze]]) |
| 293 (hdr) | C0000040 | E0000040 | .idata +EXECUTE for cave |

## AoWTCPCK.dll (VA = file_off + 0x400C00)
| Offset | From | To | Purpose |
|--------|------|----|---------|
| 1C7C | FF 25 30 E6 46 00 | B8 01 00 00 00 C3 | Defenders always attack turn 1 |
| 1AEDE | FF 91 F8 00 00 00 | 90*6 | NOP autocombat call in SetSeatedCombatPlayer |
| 5BA0E | 8B D9 | B3 01 | All units pre-installed in cities |
| C2D11 | 75 0F | 90 90 | Construct Towers underground |

## AoWDevX.exe (developer editor; renamed from AoWDevEd.exe 2026-07-21) (patches applied 2026-07-19, from BXL)
| Offset | From | To | Purpose |
|--------|------|----|---------|
| 751A0 | 0F | 3C | Map-view FrameRate 15→60 — editor 4K lag fix (map FrameRate paces the whole message pump; >60 ignored, vblank-locked). Backup: AoWDevEd.exe.bak_edfps. Do NOT touch scanner FrameRate (match @D353A, value=1). AoWEd.exe NOT patched (user uses DevEd; its byte would be @743E0). |

## HSEPack.dpl (applied 2026-07-19, from BXL; live file — no .dll twin; base 0x55600000, VA = file_off + 0x55600C00)
| Offset | From | To | Purpose |
|--------|------|----|---------|
| AD17 | 7F 14 | 90 90 | Cursor dead-zone fix pt1 — THSMapMouse.Move (VA 0x5560B8F8) upper-bound X reject @0x5560B917 NOP'd |
| AD23 | 7F 08 | 90 90 | pt2 — upper-bound Y reject @0x5560B923 NOP'd. Fixes strategic-map cursor dead strip when small map centered in wide window (negative scroll origin vs GetMaxXhp=map width). Lower-bound (≥0) checks kept. Backup: HSEPack.dpl.bak_mapcursor |

## NOT currently applied (existed pre-rollback, now gone)
Monster Slaying (66D04/66D09), Hero Slaying cave+name (65ACF/10BB3E/B9DE0/10D169),
SE category patches (B9D08/B9E50), TResurrectHero vtable (EB5F0), Exploration site UI (C12A0)

## Code Cave Free Space
- AoWTCPCK.dll: 0x3738B+: ~191K bytes free (all zeros)
- AoWEPACK.dll: 0x10B695–0x10B69E: 10B xp-min1 stub (2026-07-20); 0x10B69F: 1B free; 0x10B6A0–0x10B6F5: pool raze caves (0x10B6B0–0x10B6CD zeroed/dead); 0x10B700–0x10B753: pool raze v2 caves; 0x10B754–0x10B77C: 41B (pool non-razed-ownership helper); 0x10B77D–0x10B78C: 16B (unraze ext); 0x10B790–0x10B7BC: 45B (rebuild-gfx cave); 0x10B7BD–0x10B9FF: ~579 bytes free; 0x10BA18–0x10BAD1: free; 0x10BAD2–0x10BB07: 54B (TRecallSpiritCA v5); 0x10BB08–0x10BB3D: 54B (TAnimateDeadCA v5); 0x10BB3E–0x10BB79: 60B (Hero Slaying runtime cave); 0x10BB7A–0x10BBFF: ~134B free; 0x10C20D–0x10C592: 902B (Animate Dead cave v3); 0x10C593–0x10C5FF: 103B free; 0x10CD8D–0x10D014: 608B (RS spawn cave v1); 0x10D04D–0x10D0F7: 171B (upkeep sub v2); 0x10D0F8–0x10D168: ~113B free (dead code); 0x10D169–0x10D17D: 21B AnsiString "Hero Slaying"; 0x10D17E–0x10D1C0: ~67B free; 0x10D1C1–0x10D1E4: 36B (S1 cave — dead code, JMP reverted); 0x10D1E5–0x10D23D: ~89B free; 0x10D240–0x10D3EF: 432B (move-predictor cave, VA 0x5580DE40); 0x10D3F0–0x10D518: 297B (leadership5 caves, VA 0x5580DFF0–0x5580E118); 0x10D520–0x10D552: 51B (aura-refresh cave, VA 0x5580E120); 0x10D560–0x10D583: 36B (cave_lsround, VA 0x5580E160); 0x10D5A0–0x10D5F6: 87B (cave_lsgen, VA 0x5580E1A0); 0x10D5F7–0x10D5FF: 9B free; 0x10D600–0x10D6FB: leveled-lifesteal caves (mlcreate/E200, lsnames/E2A0, suftab/E2F0); 0x10D6FC–0x10D6FF: 4B free; 0x10D700–0x10D867: hero-slaying caves (hsreg/E300, name/E390, melee1/E3B0, melee2/E410); 0x10D870–0x10D8BA: monster-slaying caves (msmelee/E470 27B, msmelee2/E4A0 26B); 0x10D8BB–0x10D8FF: ~69B free (zeros verified); 0x10D900–0x10D9AC: 173B (cave_rngslay, VA 0x5580E500); 0x10D9B0–0x10DA10: marksmanship5 caves (mk5cost/E5B0 23B, mk5name/E5D0 64B); 0x10DA11–0x10DA3F: ~47B free (zeros verified); 0x10DA40–0x10DA7E: 63B (cave_tu5name, VA 0x5580E640); 0x10DA80–0x10DAD7: 88B (cave_dm5name, VA 0x5580E680); 0x10DAD8–0x10DADF: 8B free; 0x10DAE0–0x10DEE1: healing-leveled caves (14 caves, VA 0x5580E6E0–0x5580EAE1, see healing table); 0x10DEE2–0x10DEEF: 14B free; 0x10DEF0–0x10DF6B: charge/parry caves (VA 0x5580EAF0–0x5580EB6B); 0x10DF6C–0x10DF6F: 4B free; 0x10DF70–0x10DFB1: 66B cave_mscost (VA 0x5580EB70, calls cave_mlcreate then re-Puts MS costs 3/lvl); 0x10DFB2–0x10DFBF: 14B free; 0x10DFC0–0x10E2E3: wall-crushing caves (VA 0x5580EBC0–0x5580EEE3); 0x10E2E4–0x10E2EF: 12B free; 0x10E2F0–0x10E30F: 32B cave_wcinfo (VA 0x5580EEF0); 0x10E310–0x10E359: 74B cave_medalicon (VA 0x5580EF10); 0x10E35A–0x10E35F: 6B free; 0x10E360–0x10E39D: 62B cave_iscap; 0x10E39E–0x10E39F: 2B free; 0x10E3A0–0x10E3AE: 15B cave_atkwrap; 0x10E3B0–0x10E3BE: 15B cave_rescap; 0x10E3BF: 1B free; 0x10E3C0–0x10E3C9: 10B cave_flag; 0x10E3D0–0x10E3E2: 19B cave_merge2; 0x10E3E3–0x10E3FF: ~29B free; 0x10E400–0x10E441: 66B cave_victimxp v2 (VA 0x5580F000); 0x10E442–0x10E44F: zeros; 0x10E450–0x10E459: 10B cave_vicxp_edi (VA 0x5580F050); 0x10E45A–0x10E45F: zeros; 0x10F300–0x10F31F: 32B cave_arenacost (VA 0x5580FF00, 2026-07-27); 0x10F320–0x10F35D: 62B cave_arenaxp (VA 0x5580FF20, 2026-07-27); 0x10F360–0x10F36F: 16B cave_warmonger (VA 0x5580FF60, 2026-07-27); beyond 0x10E460 unverified — check zeros before use; beyond 0x10E400 unverified — check zeros before use; beyond 0x10E400 unverified — check zeros before use; ALSO pre-Claude archery cave at 0x5580BF70 (GetAttackRA marksmanship rework, live); ALSO pre-Claude-era cave at 0x10B510 (8B, dead since lifesteal-round patch); beyond 0x10D600 unmapped — verify zeros before use (BXL claims free to VA 0x55811000)


### Capture XP cap (seduce/charm/dominate = +1 XP) — v1, CONFIRMED 2026-07-21
Script: patch_capture_xp_cap_v1.py. Revert: AoWEPACK.dll.bak_capturexp (clean pre-feature).
MP anti-exploit (capture->disband->recapture farm). Captures now grant the captor only
**+1 XP** regardless of level; units AND heroes; tactical + autocombat. Normal kills untouched.
- **Captures use a SEPARATE XP path from kills.** Kills: defeat-handlers at 0x55726b7f (tactical)
  / 0x5572a00c (autocombat) -> cave_victimxp directly. Captures: battle-log result path, two
  callers 0x557f8473 & 0x5576fcb8 -> thunk 0x5580f050 -> cave_victimxp.
- Fix = reroute those two callers to new caves **cave_p3a @0x5580F160** (killer @[esp+4]) and
  **cave_p3b @0x5580F190** (killer @[esp+8]); thunk 0x5580f050 left intact/unused by them.
  Each: `mov ecx,[esp+disp]; mov al,[edi+0x1c]; cmp al,[ecx+0x1c]; jne .normal; xor eax,eax;
  inc eax; ret` (capture -> gain +1); `.normal: push esi; mov esi,edi; call cave_victimxp; pop esi; ret`.
- **Capture signal = captured unit's owner byte [+0x1c] == captor's [+0x1c]** (a capture makes the
  enemy join your side; a kill leaves it enemy). [+0x1c] is the battle-unit owner/player index.
  ([+0x24] is NOT owner — it's shared/constant across combatants; wrong first guess that capped ALL kills.)
- **HERO TRAP (see [[aowx-re-reference]]):** XP write is get-modify-set (ebx=GetXP[+0x98]; add cave
  return; SetXP[+0x9c]). The cave return is the GAIN. Hero SetXP -> hero cave 0x5580BE80 does
  `delta = edx - currentXP[+0x48]; if delta<=0 DIRECT-STORE edx as new absolute XP`. Forcing a
  NEGATIVE gain (early bug used `4 - ebx`) direct-stored garbage -> corrupted a L4 hero to ~-6000
  XP / level 1. FIX = return a POSITIVE CONSTANT +1 (never negative). Path-3 XP also scales
  differently than kills (empirically total 200 -> 99 XP).


### Healing leveled — tactical-combat crash FIXED 2026-07-21
Leveled Healing (I/II/III, patch_healing_leveled_v1) crashed in TACTICAL combat:
"Error during Token ExeStrike / TCTouchToken 47" (47 = 0x2F = Healing ability id;
the error msgs live in AoWTCPCK.dll, the tactical-combat pack).
CAUSE: the +0xE4 combat heal-estimator hook **cave_esthp** dereferenced the estimator's
source/healer param `[ebp-4]` -> `[+0x4c]` (strategic twin) -> FINDDATA(0x2F). In the
real-time touch-token ExeStrike path that param is NOT a strategic-capable unit, so
FINDDATA walked garbage and faulted. (The original GetHealHitPoints only read the
TARGET's HP, never that param.)
FIX: reverted that ONE hook at file 0x6B71F back to `call GetHealHitPoints` (0x5576c074).
cave_esthp cave left in place but DEAD/unreferenced. The actual heal (cave_heal/HealUnit
0x5576c374) already applies the correct 5/7/10, so combat healing stays fully leveled;
only the AI's internal heal *estimate* is vanilla flat-5 (cosmetic). Backup: .bak_healcrash.
LESSON: combat estimator/CA methods can be invoked from the tactical touch-token path
with different param validity than the strategic/AI path — don't assume an estimator's
params are strategic-capable units; only the actual apply-path (HealUnit) had valid ones.

### Blue/Green Blood mod (v2, VERBATIM from BXL live binary) — CONFIRMED WORKING 2026-07-21
Script: patch_blood_mod_v1.py (v2). Reverts: AoWTCPCK.dll.bak_preblood, Release/Release.hss.bak_preblood.
Per-unit colour blood (blood-type byte set in DevEd; 0=None/1=Red/2=Blue/3=Green; read via vanilla
[unittype+0x110]). Spurts + ground splatter + corpse pools, all coloured. Files: AoWTCPCK.DLL (our live)
10 patch regions; Release/Release.hss +14 ISL entries; 14 green/blue ILBs in Images/TCombat/Objects.
**KEY LESSON: his build script (install_blood_mod.py) was a BUGGY DRAFT — show-call rels 4 bytes off
(called garbage 0x438014/0x438028 -> ShowScene crash), corpse hook at wrong addr (0x4205A6 vs real 0x4205C3),
and it OMITTED the corpse render hook 0x41BADE (call [ecx+0xf8]). The REAL working patches came from DIFFING
his live patched binary `reference files/AoW Ziggurat/AoWTCPCK.dpl` vs vanilla. => When adopting BXL binary
patches, trust his LIVE PATCHED BINARY over his build scripts.**
- Blood caves (all in the free block VA 0x437FA0-0x438080; same base/VA as ours, va=file+0x400C00):
  bh_cave 0x437FA0 (blood-type -> add colour offset to spurt ISL idx [obj+0xc]); gnd_cave 0x437FE0
  (sets ebx=idx<<8: red 0x400/blue 0x2400/green 0x3300, jmp back; F1@0x420250 sets ebx, calls F0 setup@0x420048
  which uses it via gnd_inl1@0x42021A `mov edx,ebx;shr edx,8` + gnd_inl2@0x420232 `[obj+0x10]=ebx`; ebx survives
  F1->F0 because F0 doesn't touch it before 0x42021A); show3a@0x438018 & show3b@0x43802C decode [obj+0x10] at
  render (hooked 0x430279/0x4302AF); corpse_cave 0x43803C (blood-type + base idx [+0x178] -> clamped colour idx
  -> [obj+0x24]; hook 0x4205B0/jmp@0x4205C3; RENDER hook 0x41BADE).
- Release.hss ISL: combat ISL count 71 @our file 0x293F0D (his script hardcodes his 0x29B735 - WRONG for us).
  Red blood at idx BH=1/2/3, GndBlood=4, BF=30/31/32; green/blue CLONE those red entries (identical fields,
  only filename swapped) into NULL slots 33-39/47-49/51-54. (His hardcoded ISL field values, esp f20, are tuned
  for his red graphics and crash HSEPack.ShowScene on ours - clone red instead.) ISL sits right before the
  trailing CRC dword so growing it is safe; recalc CRC. See [[bxl-reference]].
