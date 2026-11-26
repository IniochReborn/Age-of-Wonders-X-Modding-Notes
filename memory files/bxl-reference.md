---
name: bxl-reference
description: "Bing Xi Lao (Ziggurat mod) reference — feature catalog, cave-address collision map vs our mod, reusable RE knowledge, landmines. Reviewed 2026-07-19."
metadata: 
  node_type: memory
  type: reference
  originSessionId: bd10b7eb-475b-4439-8297-a7be881f5568
---

# BXL (Ziggurat mod) Reference — reviewed 2026-07-19

Source: `reference files\BXL\` — notes/scripts from fellow modder Bing Xi Lao, who patches the SAME AoW binaries with Claude. Restore point made before any adoption: `backup\RESTORE POINT 2026-07-19 - confirmed working pre-BXL\`.

## His conventions (differ from ours!)
- **His LIVE file is AoWEPACK.dpl** (we use .dll as live, .dpl as original). His backups are `<file>.pre-<feature>`.
- Same base binary as ours: his `AoWEPACK_original_backup.dpl` vs our `AoWEPACK.dpl` = same size, only 2,167 bytes differ (his earlier mods vs AoWx pre-Claude patches). Same VA math: VA = file_off + 0x55700C00.
- Build scripts (`BXL\build_scripts\*.py`): self-contained keystone/capstone Python; dry-run default, `--apply` writes, verify-before-write, idempotent, auto-backup. Need `pip install capstone keystone-engine`. Game dir resolved 2 levels up or `AOW_GAME_DIR` env.
- His RE toolkit `BXL\re_tools\` (pescan/dasm/xref/vmt_find/ftall/mtab/dfm_parse/aowsyms + UI-automation + sampler profiler) works on ANY module — useful to us for AoWTCPCK/HSEPack/exe work where we lack Ghidra.

## ⚠ CAVE COLLISION MAP — do NOT run his AoWEPACK scripts as-is
His cave VAs overlap OUR caves directly (ours: file 0x10B6A0–0x10D23D = VA 0x5580C2A0–0x5580DE3D). Collisions:
- His undoc'd combat caves 0x5580C240 (marksmanship-ranged) & **0x5580C390 (XP-on-hit) = EXACTLY our gfx cave** (file 0x10B790); 0x5580C2xx overlaps our pool caves.
- His raze zone 0x5580C910–0x5580D640 overlaps our **AD spawn cave** (VA 0x5580CE0D–0x5580D192): his cave_razedone 0x5580CC00, cave_forcefail 0x5580D150 land inside it.
- His spellcast caves 0x5580D900+ overlap our **RS spawn cave** (0x5580D98D–0x5580DC14).
- His lifesteal cave_lsround 0x5580DC80 lands inside our **upkeep sub v2** (0x5580DC4D–0x5580DCF7).
- His path caves 0x5580DD30/DD60 overlap our **"Hero Slaying" string** (0x5580DD69).
- Probably safe-in-ours (verify zeros first): 0x5580DF00+ (Path of Sand), 0x5580E070+ (slayers/TrueSeeing/TurnUndead), 0x5580E440+ (combat log), 0x5580ED80+ (tier research), 0x5580EFC0+ (Leadership). Our caves end 0x10D23D (VA 0x5580DE3D); his notes say free to 0x55811000.
- **BSS scratch 0x558FA800–0x558FAFFF**: he uses 0x558FA800–0x558FA840; WE use none → free for us, but if we ever adopt his scripts verbatim, his flags live there.
- His caves CHAIN (TrueSeeing repoints Assassin caves' exit jmps; Path of Sand depends on path_outerring; tierresearch exe depends on dll) — adopting one feature may require its dependency or a rewrite.
- Also: his addresses assume HIS binary (has his earlier mods at hook sites, e.g. slayer blocks, side-swapped CanRaze, Desiccate'd Rejuvenate). Verify original bytes on OUR binary before every hook.
- Hook-site overlap with our patches: none found so far (our F9xxx AD/RS hooks, C12A0, 24166, D47E3/D46xx pool, 5DAA0 gfx are untouched by his work).

## Feature catalog (status as of his notes, 2026-07-20)
**Confirmed working in-game (his binaries):**
- Unit Spellcasting suite (units cast from player's book; card display; multi-turn; tier gate; book filter; save-persist) — AoWEPACK+AoWTCPCK+AoW.exe(+AoWCompat), `.sc` exe section 0x60C000
- Tier Research (research whole (sphere,tier); costs 100/200/400/800; grouped book UI) — dll caves 0x5580ED80+, exe `.tres` section 0x611000
- 4-level Leadership (cut content; curve +1/0,+1/+1,+2/+1,+2/+2; 10/level) + Leadership disable-bug fix (2 separate scripts)
- Assassin ability (id 0x38, +3/+3 vs heroes — SAME concept as our Hero Slaying 0x82!) + ranged slayer bonuses
- Lifesteal on round attack (0x76 + his 0xA9 "Dark Gift")
- Turn Undead dmg = 0.5×level×RES; Fire heals Fire Elemental/Sprite; Ice Storm lava→wasteland; Raise Terrain lava→dirt; Path radius+1 w/ 25% outer ring; Path of Sand (NEW ability id 0x9F — first from-scratch ability, proven recipe); transport-gate fix
- simfly (predictor simulates flying); tower raze-as-real-battle Stage 1; AI-raze v5 fix; movement-predictor fix (build_patch.py)
- Editor: FrameRate 15→60 (THE 4K lag fix — 1 DFM byte: AoWDevEd 0x751A0, AoWEd 0x743E0, 0x0F→0x3C); cursor dead-zone fix (HSEPack NOPs @0x5560B917/23); dialog-dir memory; toolbar; Ctrl+S
- Combat Log GUI v6 (full combat-log window, `.clog` exe section 0x60D000 + dll caves 0x5580E440+)
**Applied-untested:** TrueSeeing (+3 melee/+1 ranged atk vs invisible); loot-as-battle; loot 10×; combat log v7–v9.
**Design-only:** city raze/rebellion as battles; editor area copy/paste w/ rotation; scrolls; item HP/MV; HP/MV spell costs; storm-debuff protections (~90% feasible, one cave); command-abilities revert-on-death; Enchanted Weapon ranged; racial/Sandworm move costs.
**Withdrawn/do-not-retry:** build_glowboost (ghosting); DCPACK GetMousePos hack; per-unit different-cost movement writes (unsolved breakage); registering slayers via strike factory (use CreateEnhancementAbility 0x5576601C); THero gate flip @0x407E43 (crashes); NewTurn VMT repoint to THero.NewTurn (ValidateHeroUpgrade crashes units).

## Reusable RE gold (AoWEPACK.dpl VAs, base 0x55700000)
- **CODE section is read+execute ONLY — caves must NEVER write to themselves** (his v1 simfly crashed). Mutable scratch → BSS page slack **0x558FA800–0x558FAFFF** (declared BSS ends ~0x558FA231, page-committed+zeroed to 0x558FAFFF; .idata wall 0x558FB000).
- **MP-safe RNG rule:** TAoWHSMap.Random @0x5577827C is MP-lockstep (asserts "Invalid AoWHSMap.Random use" outside synced context; guard flag (*0x558FA040)+0x3c & 8) — use ONLY in synchronized game logic. For UI/AI/anim: System.@RandInt thunk 0x55701080 (dll) / 0x401030 (exe).
- **Combat math (fully decoded):** to-hit% = clamp(50 + 10×(atk−def), 10, 90) — HitRole @0x55725D98. Damage roll ExecuteDamageRole @0x55725EAC: R=RandInt(20); R≤1→0 (10% fumble); R≥18→full (10% max); T=10−2·diff; R<T→miss; else 1+round((dmg−1)(R−T)/(18−T)). No crit multiplier.
- **Damage-type bits:** 0x01 Fire, 0x02 Cold, 0x04 Lightning, 0x08 Magic, 0x10 Poison, 0x20 Death, 0x40 Holy, 0x80 Physical. Protections 0x46–0x4D, Immunities 6–0xD.
- **Ability IDs harvested:** Flying 1, Marksmanship 0x20, Tunneling 0x2A, Leadership 0x2E, True Vision 0x29, Regeneration 0x31, Cause Fear 0x33, Spellcasting 0x34, Invisibility 0x36, Assassin 0x38 (his), Fearless 0x43, Paths 0x44/0x45/0x6D, LifeStealing 0x76, hero-expandable 0x7A, Enchanted Weapon 0x9A, his Path of Sand 0x9F, Concealments 0x8A–0x91, size-slayers 0x92/0x93/0xA0/0xA1, Bloodlust 0xA8, his Dark Gift 0xA9. Debuffs: Cursed 0x5d, Entangled 0x5e, Poisoned 0x60, Vertigo 0x62, Panicked 0x6c. **Free ability IDs:** 0x21, 0x3B(?), 0x4E–0x55, 0x5B, 0x66–0x69, 0x6E, 0x85–0x89, 0x97 (his list; 0x9F now his).
- **New-ability recipe PROVEN** (Path of Sand): CreateEnhancementAbility @0x5576601C, set +0xC id / +0x8 name(LStrAsg) / +0x20 category, RegisterAbility @0x55750238; hook a sibling registration call. Collision = loud "Ability already registered" at startup (matches our runtime-216 experience with 0x80!).
- **Terrain bytes:** 0 Water, 1 Grass, 2 Desert, 3 Snow, 4 Steppe, 5 Wasteland, 6 Ice, 7 EarthWall, 8 RockWall, 9 Lava, A CaveWater, B CaveWasteland, C Dirt, D CaveIce. Map-field: +0x10 x, +0x11 y, +0x12 level, +0x14 terrain byte.
- **Key fn addresses:** TDamageCA.Generate 0x55729C20 / GenerateEx 0x55729C98 (all damage funnels); global CreateStrikeCA 0x557665E4 (has our Monster Slaying block @0x557666A1 = file 0x65AA1 area — our Hero Slaying hook is at file 0x65ACF!); TMeleeRound.CreateStrikeCA 0x55767E68; CreateRangedAttackCA 0x5576EAE4; ExecuteDamageRole (strategic) 0x55781AC4; ExecuteStormDamage 0x55780668; ExecuteDamageEffects 0x55781E28; TSpellControl.GetSpell 0x55779AC8 (TSpell: +0x14 mana, +0x18 research cost, +0x20 sphere 0=Cosmos, +0x21 tier, +0x22 category); GetSpherePicks 0x5578B17C (confirms our file-0x8A57C note); TAbilityControl.GetAbility 0x557501C0; IsClass thunk 0x557010C0; LStr thunks 0x55701140–0x557011B0, IntToStr 0x5570158C, Format 0x557015E4; TIntegerList.Put 0x55702EB4; AoWHSSet global 0x558FA044, map global 0x558E9494/0x558FA040; dHXtoHN 0x557026A4 (ring detection: ring r = 6r hexes, cumulative 1+3r(r+1)).
- **VMT slots (combat obj):** +0x6C GetAttack, +0x70 GetDefense, +0x74 GetResistance, +0x78 GetDamage, +0x88/+0x8C Get/SetHitPoints, +0xA8 GetAbilityEnabled, +0xB0 GetAbilityLevel, +0x108 DoDamage, +0x124 ExecuteDamage. Strategic unit: +0xA0 GetUnitLevel, +0xD0 GetMaxHP, +0xE4 SetHitPoints, +0xEC GetImmunityTypes, +0xF0 GetProtectionTypes, +0x144 GetAbilityLevel, +0x148 GetAbilityEnabled. CA fields: +0xC flags(bit0 defensive), +0xD/+0xE attacker/target id, +0x10 rolled dmg, +0x11 eff types, +0x13 effect types, +0x15 applied dmg, +0x18 effect-flag bits.
- **Delphi 3 VMT metadata:** self-ptr −0x40, method table −0x28, field table −0x2C, name −0x20, instance size −0x1C, parent −0x18. Instance-growth trick: bump size word at [VMT−0x1C] site → Delphi zero-fills new fields (used to give TUnit casting state).
- **Exe techniques:** add new PE section for caves (his `.sc` 0x60C000, `.clog` 0x60D000, `.tres` 0x611000 in AoW.exe); AoW.exe and AoWCompat.exe byte-identical except 1 byte (foff 0x3BB7C) — he patches both; our AoWx.exe is a different build (we used .idata+EXECUTE header trick instead).
- **Research system decode** (TPlayerMagicControl @player+0x54): +0x24 mana, +0x2C research %, +0x30 researched-ID list, +0x34 current research ID, +0x38 points left. ValidResearchSpell 0x5577CFF0 (tier ladder: 2 spells of tier N unlock N+1; picks gate tier≤GetSpherePicks). NewTurn 0x5577CC2C (day-1 grants 3 random tier-1). Cast picker and research picker = same TSpellBook form, mode byte +0x220.
- **Movement decode:** 8×256B cost tables @0x558EA040 base; unit table = elementwise MIN of its ability tables, army = MAX across units (the predictor bug); CreateMovePointTable 0x5577FDC4 (unit) / 0x5578DC40 (army); move-type bits: 0x01 Walk, 0x02 Fly, 0x04 Swim, 0x08 Forestry, 0x10 Cave, 0x20 Mountaineer, 0x40 Fire, 0x80 Tunneling.
- **Editor lag fix insight:** map-view FrameRate DFM byte paces the whole message pump; pump vblank-locked to 60 Hz (values >60 ignored).
- Raze framework fn map (his docs; complements our reflecting-pool work): TStructure VMT base 0x55713C18, slots 0x14C SetRazed/0x150 GetRazed/0x154 GetRazeable/0x158 RazeEx/0x1A8 GenerateRazeDefenders/0x1AC PlaceRazeDefenders/0x1B0 ExecuteRaze/0x1E8 Raze/0x1EC CanRaze — matches our pool VMT offsets (+0x14C/+0x150/+0x18).

## Landmines (his hard-won, apply to us)
- TCombatPredictor result enum ≠ TFastCombat result enum (predictor 3=attacker-side wiped; fastcombat 3=defender wiped) — never mix.
- player[+0xA7]: 0=human, ≠0=AI.
- BSS flags persist across turns/session — any set-flag/call/clear-flag pattern leaks on Delphi exception (no try/finally in caves); prefer structural re-entry tests over flags.
- Keystone: no `;` comments, labels col 0, avoid label `done`.
- Delphi published-field/DFM: handlers bound BY NAME via method table → can add DFM controls wired to existing handlers with zero code.
- His docs for full detail: `Investigation_INDEX_2026-07-08.md` (feasibility scorecard), `Unit_Spellcasting_INDEX.md` (spellcast master), `Raze_CombatPredictor_Analysis.md` (raze master, 1200 lines), `Spell_Research_System_2026-07-18.md`, `Combat_Log_Implementation_Design.md`, `HOWTO_PerHex_Ring_Detection.md`, `Adding_New_Spells_Abilities_2026-07-05.md`.

## ADOPTED: Blue/Green Blood (CONFIRMED WORKING 2026-07-21) — patch_blood_mod_v1.py v2; details in active-patches.md.
Spurts + ground + corpse, per-unit colour. **His build script install_blood_mod.py was a BUGGY DRAFT** (show-call
rels 4 bytes off -> ShowScene crash; corpse hook wrong addr 0x4205A6 vs real 0x4205C3; MISSING corpse render hook
0x41BADE). The working patches were extracted by **diffing his live `AoW Ziggurat/AoWTCPCK.dpl` vs vanilla** — his
patched binaries live in `reference files/AoW Ziggurat/` (AoWTCPCK.dpl, AoWEPACK.dpl, etc.). **RULE: adopt from his
LIVE PATCHED BINARIES, not his build scripts.** Combat ISL: count 71 @our file 0x293F0D (not his 0x29B735); red BH=1/2/3
Gnd=4 BF=30/31/32; clone red entries into NULL slots 33-39/47-49/51-54 (his hardcoded ISL f20 values crash our renderer).
Blood-type getter [unittype+0x110] is vanilla.

## Adoption guidance
Whatever we adopt must be **re-caved into OUR free space** (0x5580DE3D+ / verify zeros; or the 0x10BB7A/0x10C593/0x10D0F8 gaps for small caves) and hook-site original bytes re-verified against OUR AoWEPACK.dll. His hook-site addresses are trustworthy as *locations* (same base build); his surrounding original bytes may differ where either mod already patched. Cleanest first candidates (self-contained, no cave chains, no overlap with our features): editor FrameRate fix (different files entirely), cursor dead-zone fix (HSEPack), Turn Undead RES, storm protections, Lifesteal-on-round, Leadership fix+4-level. Overlapping-concept features needing reconciliation: his Assassin 0x38 vs our Hero Slaying 0x82 (same feature, different IDs/mechanisms — pick one).
