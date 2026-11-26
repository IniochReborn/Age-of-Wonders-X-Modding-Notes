---
name: magic-sight-spell-re
description: "RE for adding the custom \"Magic Sight\" spell (Secret sphere, grants Night Vision+True Seeing) — spell/enchantment structure decoded, clone template found; implementation not yet built"
metadata: 
  node_type: memory
  type: project
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-10T08:00:36.216Z
---

**GOAL:** custom spell "Magic Sight" — unit enchantment granting Night Vision
(ability 0x27) + True Seeing (0x29). Secret sphere. Level 1, cast 5, upkeep 1.
Obtainability SOLVED: user says Secret-sphere spells are dispensed by the
Wizard's Tower structure (vanilla feature) — so just tag it Secret + Tower
metadata and it's obtained there. NO new sphere, no item needed.

**CLONE TEMPLATE = `UnitSpells.TWaterWalking`** (spell @0x557E7CD8) +
`PassiveAb.TWaterWalkingEnchantment` (@0x557BB9B0). Reference recipe from
[[aowx-re-reference]] / BXL `Adding_New_Spells_Abilities` (Tier-1 clone: init
cave after a Register* call, clone class, poke fields, RegisterSpell).

**TSpell / TUnitSpell field layout (decoded from TWaterWalking.Create):**
base ctor `TUnitSpell.Create` @0x5577AC34. Fields on the spell object (esi):
+0x08 name (AnsiString; set via LoadResString→TranslateRStr→@LStrAsg @0x55701150),
+0x0C default byte, +0x10 spell ID (int; WaterWalking=0x2A), +0x14 mana cost
(=5), +0x18 research cost, +0x20 sphere byte (WaterWalking=6=Water; **Secret =
a sphere id 7+ with no picks**, see SecretRStr @0x55706DE4), +0x21 research tier
byte (=2; want 1), +0x22 category byte, +0x30 AI value, +0x38 int (=0xC) &
+0x3C byte (=6) = TUnitSpell-specific params (upkeep/ability link — NOT yet
pinned; decode TUnitSpell.Create + TWaterWalking.ExecuteSpell @0x557E7D90).
Sphere ids: 0 Cosmos,1 Life,2 Death,3 Earth,4 Air,5 Fire,6 Water.

**Enchantment mechanism (decoded):** `TUnitEnchantmentAbility` (base ctor
@0x55765518) is-a TAbility; sets +0x24=4, +0x20=0. Subclass ctor (e.g.
TWaterWalkingEnchantment) sets name + **[ench+0x0C] = the GRANTED ability id**
(WaterWalking ench = 0xA4). `GetAbilityID` = `movzx eax,[eax+0xC]`. `Expand`
@0x55765894: reads [ench+0xC], calls TAbilityOwner.GetAbilityData(unit, id) →
adds/works that ability on the unit. `TUnitEnchantmentAbilityData` (data class
@0x55765438, ptr @0x55722244) holds the per-unit instance; SetEnchantment
@0x557654B0. **=> one TUnitEnchantmentAbility grants exactly ONE ability id.**

**KEY DESIGN FORK — granting TWO abilities (0x27 + 0x29):**
(A) ONE custom enchantment, custom Expand/Remove that adds BOTH 0x27 and 0x29
    to the unit (Tier-2: clone the enchantment VMT at runtime, repoint Expand/
    Remove to a cave). Cleaner: single "Magic Sight" line, single upkeep.
(B) Spell casts TWO plain TUnitEnchantmentAbility instances (+0xC=0x27 and
    +0xC=0x29), both named "Magic Sight". Simpler (no new VMT) but shows two
    enchantment lines / upkeep bookkeeping doubles.
Recommend (A).

**★ CONFIRMED 8/9 (user corrections):** Wizard's Tower = editor-time config
(one random spell from a chosen sphere) — NO code needed for obtainability,
just tag Secret. **SECRET SPHERE ID = 7** (verified: TCosmeticSurgery.Create
@0x557E8674 sets [esi+0x20]=7). Summon Mermaid was GLOBAL sphere 2 (not the
template). **Real template = the vanilla Secret ENCHANTMENT spell
`UnitSpells.TCosmeticSurgery`** @0x557E8674 (id 0x3B, [+0x21]tier=1,
[+0x22]cat=1, [+0x20]sphere=7, [+0x3c]=0xA, [+0x38]=-1; cost via base default).
Its ExecuteSpell @0x557E8730 creates TCosmeticSurgeryEnchantment (ench ctor
@0x55765E40). User chose APPROACH A (one custom enchantment granting both).
Sphere-name RStr ptrs live near 0x558E8120 (data).

**BUILD SHAPE (Tier-2/3 — the hard content-add):** need a custom SPELL class
(custom ExecuteSpell that creates OUR enchantment, not deform-face) + a custom
ENCHANTMENT class (custom Expand/Remove granting BOTH 0x27 and 0x29). Runtime-
clone both VMTs (memcpy + repoint slots) to dodge .reloc surgery; init cave
after a Register*Spells call registers the spell (RegisterSpell @0x55779B40)
with a frozen ID above vanilla max. Still to pin at build time: TUnitSpell.Create
+ TCosmeticSurgery.ExecuteSpell/CastSpell (how ench is instantiated + can it be
parameterized to avoid a custom spell class); upkeep field ([+0x3c]? — Cosmetic
Surgery=0xA); what TUnitEnchantmentAbility.Expand actually does to the unit's
ability set (to replicate for 2 abilities); a free spell ID.

**★ STAGE 1 DONE & USER-CONFIRMED 8/9** (`patch scripts/build_magic_sight_stage1.py`,
bak_magicsight1): init cave @0x55810400 hooks the last RegisterSpell call in
RegisterUnitSpells @0x557E8E3A → replicate RegisterSpell(TDarkGift), then
create a TCosmeticSurgery clone (classref [0x557E697C], ctor 0x557E8674),
poke ID=**0xC8**, cost=5, sphere=7, level=1, cat=1, name="Magic Sight" (raw
Delphi literal, refcount -1, via @LStrAsg 0x55701150). PIC delta trick
(edi=delta, [edi+absVA]). Registers fine, appears correctly. Cost/upkeep =
user sets in editor (don't hardcode).

**★ STAGE 2 APPLIED 8/9 (awaiting test)** `patch scripts/build_magic_sight_stage2.py`
(bak_magicsight2, cave @0x55810480, hook @0x557E8730 TCosmeticSurgery.
ExecuteSpell entry, 5 displaced bytes 55 8BEC 51 53, resume 0x557E8735). Cave:
if [spell+0x10]==0xC8 → for each of 0x27/0x29: if !HasAbility (vcall[tgt+0x148])
then AddAbility (vcall[tgt+0x94]); mov al,1; ret. Else vanilla prologue+jmp
back (real Cosmetic Surgery untouched). Fully PIC (rel32/rel8 + vmt-indirect,
no absolutes). KEY REALIZATION that simplified it: [ability+0xc]=own id; each
ability IS its effect (engine queries HasAbility), no "grant a different
ability" mechanism — so grant sight by adding 0x27+0x29 directly (like
TWaterWalking adds 0xa4). CAVEAT: unit will show "Night Vision"+"True Seeing"
(the granted abilities), NOT a single "Magic Sight" enchantment line; and
whether they're dispellable/upkeep-tracked = same path as Water Walking
(AddAbility), to verify in test. If user wants a single "Magic Sight" line =
STAGE 2b (custom enchant ability 0xC9 + custom Expand adding both — bigger).

**★ STAGE 2a USER TEST 8/9 — effect works but 6 issues (root cause: wrong base
+ direct grant). REBUILD needed (stage 2b).** Issues: (1) no spell icon,
(2) unlimited range (want ~Enchant Weapon's short range), (3) no side image in
cast window, (4) casting pops the COSMETIC SURGERY face-swap UI, (5) not shown
in unit spell/enchant tab (no name/upkeep/removal), (6) Night Vision + True
Seeing granted as PERMANENT innate abilities (not a dispellable/upkeep
enchantment). Causes: 1-4 = Magic Sight is a TCosmeticSurgery clone (inherits
its cast UI / range / icon handling); 5-6 = direct AddAbility(0x27/0x29) is a
raw permanent grant, not the tracked enchantment mechanism.
**★ PART A APPLIED 8/9 (awaiting test):** rebased Magic Sight on
**TEnchantWeapon** (classref [0x557E575C], ctor 0x557E6D98) instead of
TCosmeticSurgery — should fix issues 1-4 (icon plumbing, short range [+0x40=
0xe1 from EnchantWeapon.Create], cast side-image, NO face-swap UI). Both stage
scripts retargeted (stage 1 classref/ctor → EnchantWeapon; stage 2 hook moved
to **TEnchantWeapon.ExecuteSpell @0x557E6E60**, identical prologue 55 8BEC 51 53,
resume 0x557E6E65; EnchantWeapon's own ench-ability id=0x9a). Fresh backups
bak_magicsight1/2 (vanilla-based). Still uses direct AddAbility(0x27/0x29) →
issues 5-6 (permanent, not in spell tab) REMAIN = Part B. Icon art may show
EnchantWeapon's or blank (id 0xC8 has no ILB art) — user to report.
**★ PART A TEST 8/9:** face-swap FIXED, short range FIXED. STILL broken: no
side image, no icon, and **"exception occurred during TUnitSpellTE" on every
cast** (game survives after OK). Diagnosis: the direct-AddAbility shortcut (0x27/
0x29 are REGULAR abilities, not enchantment abilities) skips TUnitSpellTE's
enchantment bookkeeping → exception + no side image + permanent + not-in-tab.
Confirmed: shortcut is unfixable; MUST do proper enchantment. **STAGE 2 EFFECT
HOOK REVERTED** (build_magic_sight_stage2.py --revert) to stop the crash. CURRENT
STATE: stage 1 applied (Magic Sight = clean EnchantWeapon clone, registers +
appears right, cast = harmless weapon-enchant placeholder, NO crash); stage 2
reverted. Icon still blank (id 0xC8 no ILB art).

**★★ PART B BUILT & APPLIED 8/10 (awaiting test).** Proper enchantment. THREE
new/rewritten patches (all in `patch scripts/`, each own backup + revert):
- **stage3_ability** (NEW): registers effect-less enchantment ability **id 0xC9
  "Magic Sight"** = BASE TUnitEnchantmentAbility (classref **0x5572237C**, base
  Create **0x55765518**, no GetAttack/Damage override so no stat leak). Hook @
  **0x557BCC11** (`call RegisterAbility` for Enchanted Weapon); cave @0x55810700
  replays that reg then Creates+names+registers 0xC9. RegisterAbility=0x55750238,
  control=ebx. PIC delta (edi). bak_magicsight3.
- **stage4_expand** (NEW): hook TUnitEnchantmentAbility.**Expand @0x55765894**,
  gated `cmp [self+0xc],0xC9`; grants **0x27 + 0x29** (+ 0xC9 marker) by running
  the real Expand body 3× via trampoline with [self+0xc] temp-swapped (Expand
  creates enchant-data for whatever id is at [self+0xc]). No recursion (tramp =
  displaced prologue 53 56 57 55 51 + jmp 0x55765899). cave @0x55810800.
  bak_magicsight4.
- **stage2 REWRITTEN**: applies 0xC9 the proper way = verbatim clone of
  TEnchantWeapon.ExecuteSpell (0x557E6E60, 0x6E bytes) with the two `mov edx,0x9a`
  → 0xC9 and the one external `call GetAbilityData 0x5574F1C4` rel32 recomputed
  (internal je/jmp survive the copy). cave moved to **0x55810600** (out of
  stage-1's 0x400-0x600 zero-pad). Gate `cmp [spell+0x10],0xC8`. bak_magicsight2.
Cave map: s1=0x55810400, s2=0x55810600, s3=0x55810700, s4=0x55810800 (all verified
free). Expected fixes: exception GONE, side image shows, dispellable/upkeep, in
spell tab as "Magic Sight". STILL PENDING: **icon art** — both spell id 0xC8 AND
enchantment ability id 0xC9 have no ILB art, so icons blank until art added.

**★ PART B BUGFIX 8/10 — ability id 0xC9 → 0xAA (dense).** First Part-B build
crashed at STARTUP ("runtime error 216 at 00003924"). Cause: TAbilityControl.
RegisterAbility (0x55750238) stores the ability in a TList **indexed by id**,
padding with nils via a `while id>=Count: TList.Add(nil)` loop (0x557502BD). A
sparse/high id (0xC9=201, vanilla max 0xA9) left ~31 nil entries; the startup
ability-enumeration is NOT nil-safe → GPF calling a virtual on a nil. Fix: use
the **dense next-free id 0xAA** (max ability id is 0xA9 → Count==0xAA → appends
with no gap). NOTE: the 0xFA `[reg+0xc]` writes are a different class (they also
set [+0x1c]=7, not an image-seq ptr), NOT abilities. The SPELL id 0xC8 was fine
(different registry, tolerated). All 3 scripts updated (MS_ABILITY_ID=0xAA),
re-applied. Rule: **id-indexed registries need dense ids** — cf [[rebase-crash-runtime-error-216]].

**★★ PART B REAL BUGFIX 8/10 — base classref 0x5572237C→0x55722364.** The
startup GPF 216 was NOT the sparse id (0xAA change kept, still good). Real cause:
I used the WRONG base-class VMT ptr. Derived 0x5572237C from a bad Delphi
vmtClassName offset (-0x38); the object's [+0] = that wrong VMT, so load-time
enumeration calling a HIGH virtual slot (e.g. [vmt+0x108]) read into the class-
NAME string ("TUnitEnchantm"=0x6E555417...) → garbage ptr → GPF. **Ground truth:
classref = 0x55722364** (vmtSelfPtr @0x55722324 → 0x55722364; Create @+0x20 =
0x55765518; Expand @+0xD0 = 0x55765894; 63 inherited slots match Enchanted
Weapon's VMT, only 3 differ = EnchW's stat overrides which base lacks = no leak).
Method to get a Delphi classref right: **find a known method ptr's slot location,
subtract that method's offset-from-classref (read off a concrete subclass), or use
the self-ptr**. Isolation that nailed it: reverting ONLY stage 3 → game started →
proved stages 2+4 load-safe, stage 3 was the crash. Fixed & re-applied.

**★ PART B STAGE-4 REWRITE 8/10 — bitmap projection (was Expand grant).** Test
after the classref fix: startup+cast+enchant-in-list all WORK, but dispel removed
0xAA yet Night Vision/True Seeing STAYED. Cause: the old Expand hook created
PERSISTENT ability-DATA for 0x27/0x29, which every bitmap rebuild re-read. Real
model: HasAbility(id) = bit[id] in a per-unit BITMAP ([unit+8]=bits,[unit+0xc]=
count); rebuilt from the real ability list; **single writer =
TCustomAbilityList.SetAbSet @0x5574E0BC** (SetAbSet(eax=list,edx=id,cl=flag);
GetAbSet @0x5574E0E0; TUnit raw check inlines it @0x5577F618). NEW stage4
(`build_magic_sight_stage4_sight.py`, replaces _expand): hook SetAbSet, and when
bit 0xAA is being SET (cl!=0) also SetAbSet 0x27 + 0x29 via a trampoline (tramp
reconstructs cmp+jae→grow 0x5574E0D0+jmp resume 0x5574E0C1; only 5 bytes
overwritten so the grow path's re-entry @0x5574E0C1 stays intact). cave 0x55810800.
**UPDATE: dispel is INCREMENTAL (SetAbSet(0xAA,0), no rebuild)** — SET-only left
NV/TS behind. Fixed: hook now mirrors BOTH set & clear. On clear, NV/TS are
cleared only if **GetAbilityData(@0x5574F1C4) returns nil** for them (projected
bits carry no data; innate/other-source ones do) → innate sight preserved. Cave
grew (two branches); vanilla moved right after the entry cmp so all rel8 jumps
stay in range. Old _expand.py + its backup
deleted. STILL PENDING: icon art (spell 0xC8 + ability 0xAA blank).

**★ ICON + GFX BUILT 8/10 (`patch scripts/build_magic_sight_icon.py`, awaiting
test).** Spell visuals are DATA, not code: **Release/Spells.pfs key = spell id
+ 10** (like Ability.pfs) → key 210 = Magic Sight 0xC8. The EDITOR had already
written a stub record 210 (user's cost edit) with EMPTY gfx tag 0x0C → that's
why icon+side image were blank. Record tags: 0xA desc(len32+chars), 0xB ?, **0xC
gfx = TImageSequenceList stream** (entries `[len32][ILB path][3B pad][idx:u32]
[8B zero][01×9][00]`; spellbook icon entry = SPELLICN.ILB + record idx; also
EFFECTS\*.ILB cast anims + BORDER.ILB 0x39-0x3b frames), 0xD cast, 0xE ?, 0xF
research, 0x10 ?, 0x11 tail. **SPELLICN.ILB: 222 recs, 40×35 RGB565** (raw or
sub-bitmap w/ sub-dims at pf+4/+8), named per SPHERE (SI-Air/Death/…/Cosmos/
Secret via [len32]name.BMP in headers); icons = 2-frame pairs (cloud bg + ink
glyph, glyph overlays w/ **WHITE 0xFFFF colorkey**); ref idx = pair's first rec.
Used refs = 108; pair **56/57 free** → repainted: 56 = Secret purple cloud (copy
of rec 212) + custom EYE glyph baked, 57 = glyph on white (works under both draw
semantics). Record 210 rebuilt in place (it's the LAST pfs record): kept stub
tags, added desc + EnchW's whole gfx blob (key 26 tag 0xC, 1839B — gives cast
anim/side image/borders) w/ icon idx 120→56. Backups: SPELLICN.ILB.bak_magicsight,
Spells.pfs.bak_magicsight; revert = script --revert. NOTE: **Ability.pfs tag8
gfx is empty even for vanilla EnchW ability** → nothing needed ability-side.
Ability.pfs has NO key 180 (0xAA) record — add later only if desc text wanted.

**★ ICON ATTEMPTS 1-2 BROKE ALL SPELL GFX (8/10) — root-caused + v3 applied.**
Symptom: every spell lost icon/side-image, costs garbled. Cause chain: my rebuilt
record kept the editor stub's **truncated sub-stream tags** — stub 0x0B "sounds"
= `01 01 00 00` (sub-table {tag1→off0} with NO value bytes; tag1's value reads
whatever bytes FOLLOW). Stub-era it was followed by 0x0C=00000000 → sound count
0 → parsed safely BY LUCK. My rebuild put the 1839-byte gfx blob behind it →
sound reader parsed `17000000...` as 23 garbage sounds → exception during record
210 read (read LAST, key order) → aborts TAoWHSSet post-load finalize → ALL
spell gfx unlinked. Engine reader RE (EngineP.dpl imagebase 0x55500000):
TSpellControl.ReadWrite @0x55779A6C = per-spell rwObject(key=id+10);
rwEObject rva 0x116B0; PushTable @0x5550FC3C parses ctrl[nb|0x80][nd:u32]
[nb×(tag:b,off:b)][nd×(tag:u32,off:u32)]; FindOffset @0x5550FE70 = hint-cursor
[+0x10] + fallback scan from [+0x24]. Vanilla records: values in TAG ORDER,
ctrl 0x83 shape. Also: **vanilla 0x11 = single byte 01** (my earlier "big 0x11
blob" misread — those bytes were the NEXT record's table). **v3 fix (applied):
record 210 = byte-for-byte copy of EnchW's ENTIRE record** (real 46B sound
stream = EnchW cast sound, real 0x11=01, real 0x0F research=40) with only 0x0A
desc, 0x0C icon idx 120→56, 0x0D cast=5, 0x10 sphere=7 overridden. ILB paint
verified clean (recs 56/57 non-overlapping, no header CRC — dwords@4/8 are
constants across all ILBs).

**★★ ICON MODEL CORRECTED 8/10 (v2 painted; awaiting editor step).** Isolation
test proved ILB paint innocent & pfs growth "the trigger" — then the REAL model
fell out: **SPELLICN.ILB icons are keyed by a per-record IMAGE ID header field**
(`FF FF FF FF [id:u32] 00 01 00 00 16 00 00 00 03 [namelen] name` precedes each
record), NOT record ordinal. **Each image id = a PAIR of records** (cloud bg +
glyph overlay; id 120 = recs 192/193, id 0 = recs 0/1). Editor picker + pfs refs
both use ids. v1-v3 failures explained: painted ordinals 56/57 = **image id 32
(a real Death icon — hijacked!)** and pfs ref 56 = NONEXISTENT id → link throws
during load → ALL spell gfx abort (my 3 pfs-structure theories were ghosts; even
v1's encoding may have been fine). Free (present-but-never-referenced) image
ids: **52, 88, 151**. **v2 (`build_magic_sight_icon2.py`, APPLIED): eye baked
into id 151** = unused SI-Secret pair, rec210 (40×35 cloud+eye), rec211 (35×20
overlay @ (2,9)) filled pure 0xFFFF white = transparent; recs 56/57 restored
byte-exact. Spells.pfs = stub (untouched). **REMAINING STEP: user assigns icon
id 151 + description + EnchW-style side image/effects/sound in the EDITOR spell
gfx form** (editor's writer = the real serializer; hand-written pfs deprecated).
`build_magic_sight_icon.py` (v1) is DEPRECATED — do not run its pfs half.

**★★★ ICON WORKING IN GAME 8/10 — pfs mystery SOLVED: trailing file checksum.**
Editor save (icon 151) succeeded → diff vs my hand-written records gave ground
truth: (1) **Spells.pfs ends with a content-dependent 4-byte trailer** (stub
`6bc56b4f` → editor-icon-save `ef0dbb31`) — a checksum/stamp the engine
validates; my hand-written files omitted or invalidated it → THAT was the
global all-spells gfx wipe (cost garbling in v1/v2 was the separate
value-ordering bug). Algorithm not RE'd — **rule: NEVER hand-write
Release/*.pfs; use the EDITOR (its writer emits the trailer)**. ILB pixel edits
have no such guard (safe). (2) Editor's icon-only gfx tag 0x0C = 47B:
`[seqcount:u32=11][01×10 (empty slots)][00][len32 "SPELLICN.ILB"][3B pad]
[imageid:u32][8B zeros]` — icon = sequence SLOT 10; vanilla full lists have 23
slots (effects at 0-9, BORDER ids 0x39-0x3b at 11-13 = side/border images).
(3) TSpell.ReadWrite @0x55779234 tag map: 0xA=desc rwStrings [obj+0x24],
0xB=sound rwEObject [+0x28], **0xC=gfx rwStreamProc(read 0x557028dc/write
0x557028d4) [+0x2c]**, 0xD/0xE/0xF=cast/[+0x1c]/research rwIntegerEx,
0x10=[+0x20] 1-byte (sphere), 0x11=[+0x21] level byte. Read order = 0A..0x11.
**Icon repainted final: pure BLACK eye + brighter purple cloud (donor rec 212
pixels) at image id 151** (user: dark-ink v1 was hard to see; confirmed working
in game, awaiting contrast re-check). Forensic copy of my bad v4:
Spells.pfs.editorwipe_forensic (misnamed — editor never wrote; can delete).
REMAINING: user adds desc + side-image/cast-effect/sound (copy Enchant Weapon's
gfx form values) in EDITOR + save.

**★★★★ PFS FORMAT FULLY CRACKED 8/10 — trailing CRC-32.** `Release/*.pfs` =
**`[0x2144DF1C][payload][crc32(payload)]`** — trailing dword = zlib CRC-32 over
`file[4:-4]`, VERIFIED on 5 pfs files; leading dword = the CRC-32 residue
constant as a format tag (appears in NO binary — that's how it hid). Engine
validates at open; bad/missing tail → whole file rejected → the all-spells gfx
wipe. (Proof of global reject: the EDITOR — which has no Magic Sight registered
and never reads key 210 — also showed all gfx blank on my CRC-less files.)
**Hand-writing pfs is now SAFE: recompute tail after any edit.**
`build_magic_sight_icon.py` (pfs writer, current): asserts source CRC, splices
EnchW-mirror record 210 (desc, cast 5, research 40, sphere 7, level 1, icon id
**151**, EnchW sound + 23-slot gfx: twinkle cast anims slots 0-9, icon slot 10,
BORDER 0x39-0x3b side/border slots 11-13), appends fresh CRC. **APPLIED, verify
clean — awaiting final in-game test.** Backups: Spells.pfs.bak_magicsight
(vanilla+stub), .bak_editoricon (editor icon-only save). **ICON FINAL ART:**
original dark id-151 Secret cloud (user rejected bright purple = "Cosmos-y") +
prominent eye: pale ice-blue sclera (196,222,240), pure black outline/rays/
pupil, violet iris (148,118,220) — layered-mask render in
build_magic_sight_icon2.py (APPLIED to ILB).

**★ CAST-FX + ICON v3 8/10 (applied, awaiting test).** User: icon bg more
prominent + glyph black/transparent-only (no white); + EnchW-style fade-in/out
cast overlay but an EYE. RE: **EnchW's fade-sword = a FRAME-LIST entry in the
spell gfx blob**: `[len32]EFFECTS\MAGIC.ILB[3B flags 04 01 04][defaultid:u32]
[xoff:i32][yoff:i32][0:u32][count:u32][count×frameid:u32]` — EnchW: 27 frames =
7×**0x3E7 (=999 blank delay frames)** + ids 0x46-0x59 (EnchWpn00-19.BMP in
Effects/Magic.ILB, fade baked in frame brightness, additive-on-black). Magic.ILB
image-id map: Teleport00-11=0-0xb, Summon=~0x14+, free0021=0x3d, EnchWpn=0x46-
0x59, Spawn=0x5a-0x6d, Watcher00-11=0x78-0x83 (dim blue swirls — rejected),
fire-halo overlay ids 0xaa-0xb5 (44×42, used by modded ability 0xA3 whose
Ability.pfs tag8 shows the ABILITY-overlay gfx format = same entry + ping-pong
frame list). **Built `Images/Effects/MSight.ILB`** (new file, container cloned
from Magic.ILB: header [.ILB4][0x40F000][0x40800000][0x18][base][filesize];
rec0 prefix [filesize][0][0], recs 1+ [FFFFFFFF][id]; 16×64×64 RAW16 frames,
glowing violet eye, fade baked) via `build_magic_sight_castfx.py`; record 210's
MAGIC.ILB entry rewired → EFFECTS\MSIGHT.ILB, frames = 7 delays + 0..15, CRC
recomputed. bak: Spells.pfs.bak_castfx; revert deletes MSight.ILB + restores.
**Icon v3** (icon2 script): original blue-teal id-151 cloud ×1.75 brightness +
BLACK-only eye (outline/ring/pupil/rays; sclera transparent). If the new-file
ILB fails to load in-game → fallback = Watcher frames (0x78-0x83) in-place.

**★★ ILB v4 CONTAINER FULLY CRACKED 8/10 (after MSight.ILB v1 HUNG game+editor
— malformed stream → parser read pixel bytes as ids → SetLength(garbage)/giant
string reads → hang; reverted, root-caused via ILPACK RE, v2 written & applied).**
ILPACK.dpl imagebase 0x55200000; TCustomImageLibrary.LoadFromStream @0x5521A9C0;
**header dword @8 is a FLOAT version (4.0)**, v4 branch @0x5521AB7E copies the
header region (0x18..base) into a MEMORY stream and parses:
`[palettecount:u32=0]` then repeat `[imageid:u32][classtag:u32][class body]
[extra:u32=0xFFFFFFFF]`, terminated by id 0xFFFFFFFF. classtag matched against
registered classes' GetClassTag (vcall +0x68) via mapper @0x5521BAAC; **0x16 =
plain 16bpp image**, 0x100 = wrapper class (nested 0x16 node; used by SPELLICN).
Class-0x16 body: `[03][namelen:u32][name][cellw][cellh][12B zeros][01][size]
[doff rel-to-base][cellw][cellh][02 03 00 00][0x64][pixfmt 0x56509310][subw]
[subh][xoff][yoff][key:u32]`. File header 0x18B: `['\x04ILB'][0x40F000]
[float 4.0][0x18][base][filesize]`. Node reader @0x5521BC94 (Create + vcall
+0x58 LoadFromStreamEx(memstream, filestream) — pixel data read from FILE stream
@ lib[+0x3c]=base+doff). Validator parses vanilla Magic.ILB 86/86 plain records
cleanly (stops at Watcher's 0x100 wrapper = fine). **MSight.ILB v2 (132704B, 16
eye frames) + pfs rewire RE-APPLIED — awaiting test.** Magic.ILB extra facts:
recs 0-11 Teleport ids 0-11, EnchWpn sword recs 46-65 ids 0x46-0x59, Spawn recs
66-85, Watcher recs 86-111 ids 0x78-0x83, fire-halo 44×42 recs 132-143 ids
0xaa-0xb5.

**★ ICON v5 FINAL MODEL 8/10 (applied).** Screenshot analysis + Concealment
pair (icon id 42 = rec68 cloud + rec69 glyph) revealed **how the spellbook
draws icons: frame 0 (cloud) = ADDITIVE glow backdrop (black edges vanish on
parchment), frame 1 (glyph) = ink drawn with WHITE keyed out.** All prior "bake
eye into cloud / blank the glyph" versions were backwards (dark box, no ink).
v5: rec210 = ORIGINAL Secret cloud byte-restored (no boost/scale/eye); rec211
(35×20 sub @ (2,9)) = solid black eye silhouette w/ carved-out iris ring +
pupil on 0xFFFF white. Cast-fx eye (MSight.ILB) CONFIRMED WORKING in game.

**✅✅ FEATURE COMPLETE — USER SIGNED OFF "perfect" 2026-08-10.** Final state:
spell 0xC8 "Magic Sight" (Secret L1, cast 5, upkeep 1) = TEnchantWeapon clone;
enchantment ability 0xAA via SetAbSet bitmap projection (set+clear mirrored,
innate-protected); Spells.pfs record 210 = EnchW-mirror + desc + icon id 151 +
MSight.ILB eye cast-fx + EnchW sound/twinkles/borders, valid CRC; icon = Secret
cloud glow + ink OUTLINE eye glyph w/ lashes (35×20 frame 1); cast = 16-frame
fading glowing eye. Patches: stages 1/3 (E8 hooks), 2/4 (E9 hooks) in
AoWEPACK.dll + data files. Scripts: build_magic_sight_stage{1,2,3_ability,
4_sight}.py, build_magic_sight_icon.py (pfs), build_magic_sight_icon2.py (ILB
art), build_magic_sight_castfx.py (MSight.ILB+pfs). Backups: bak_magicsight1-4
(DLL), Spells.pfs.bak_magicsight (vanilla+stub) / .bak_editoricon / .bak_castfx,
SPELLICN.ILB.bak_magicsight. Delete-worthy: Spells.pfs.editorwipe_forensic.

**PART B design notes (if a rebuild is needed):**
- Rebase the SPELL on **`UnitSpells.TEnchantWeapon`** (@0x557E6D98) instead of
  TCosmeticSurgery — a clean unit-enchant spell w/ short range + proper enchant
  cast UI + icon/side-image. (Change stage-1 cave's classref+ctor to
  EnchantWeapon's; re-poke id/name/sphere/cost/level; keep ID 0xC8.)
- Make Magic Sight apply a PROPER "Magic Sight" enchantment ability (register a
  new TUnitEnchantmentAbility id 0xC9, name "Magic Sight", tracked/dispellable/
  upkeep) so it shows in the spell tab; its custom Expand adds 0x27+0x29 as
  ENCHANTMENT-tracked (removed on dispel). Gated ExecuteSpell hook adds 0xC9
  (not EnchantWeapon's ability).
- ICON: spells draw seq-10 from spell+0x2c TImageSequenceList; blank because
  id 0xC8 has no art. Reuse an existing spell's icon seq (or add to SpellIcn.ILB
  / Int spell ILB). TODO: find how spell icon seq is linked per-id.
- Need RE: TEnchantWeapon.Create (fields incl range) + ExecuteSpell (its ench
  ability id); how range is stored on the spell; register a TUnitEnchantmentAbility
  with custom Expand (runtime-clone VMT: repoint Expand @vmt slot to a cave
  that adds 0x27+0x29 enchant-tracked); RegisterAbility(eax=control [AoWHSSet+0x80],
  edx=ability; reads id from [ab+0xc]).
STATE: stage 1 (bak_magicsight1) + stage 2a (bak_magicsight2) applied; 2a to be
reverted/replaced by 2b. Backups chain: revert 2 then 1 to reach vanilla, or
build 2b atop.

**★ ORIGINAL STAGE 2 DESIGN (superseded by the simpler direct-grant above):** effect = casting adds a
registered ENCHANTMENT ABILITY to the unit; that ability's Expand grants
[self+0xc]. Model confirmed: TCosmeticSurgery.ExecuteSpell @0x557E8730 adds
ability 0x7e (HARDCODED `mov edx,0x7e` + vcall[target_vmt+0x94]=AddAbility);
TWaterWalking.ExecuteSpell @0x557E7D90 identically hardcodes 0xa4 (NOT field-
driven). TUnitEnchantmentAbility.Expand @0x55765894: GetAbilityData(unit,
[self+0xc]); if absent, make a TUnitEnchantmentAbilityData (@0x55722244) with
[data+0xc]=[self+0xc]. => grant TWO abilities by calling stock Expand twice.
Night Vision=0x27, True Seeing=0x29. Registered enchant-ability example:
TCosmeticSurgeryAbility.Create @0x55765F38 registered in RegisterPassiveAbilities
@0x557BCD1C (RegisterAbility @0x55750238). Note TVisionAbility @0x557B9864
exists (registered @0x557BCA00) — possible cleaner sight base, unexamined.
BUILD PLAN (3 caves, gated hooks — no custom VMTs): (1) extend init cave:
register a custom enchant-ability id **0xC9** "Magic Sight" ([+0xc]=0x27,
own id 0xC9) via RegisterAbility (need base TUnitEnchantmentAbility classref
+ Create @0x55765518). (2) gated hook on Expand @0x55765894: if self id==0xC9,
after granting 0x27 also grant 0x29 (temp set [self+0xc]=0x29, recall stock
Expand, restore). (3) gated hook on TCosmeticSurgery.ExecuteSpell entry
@0x557E8730: if [spell+0x10]==0xC8 → add 0xC9 to target (mimic the AddAbility
+ config: vcall+0x94 AddAbility, GetAbilityData, vcall+0x54/+0x58, [data+0x14]
=[spell+0x3c]) and skip vanilla; else vanilla. STILL to pin at build: exact
RegisterAbility(eax=control?,edx=ability) signature + the ability control
(AoWHSSet+0x80); base TUnitEnchantmentAbility classref for instantiation;
confirm AddAbility(vcall+0x94) triggers Expand immediately (else abilities
won't grant until recalc). CRASH-SENSITIVE (runs per-unit); MP = all peers
need the DLL. Task #1 tracks it.

**STILL TODO before building:** (1) TUnitSpell.Create + TWaterWalking.ExecuteSpell
— where upkeep lives + how the spell instantiates its enchantment on cast;
(2) the Secret sphere id value + what metadata makes a spell Wizard-Tower-
dispensed (find the tower's secret-spell list code — search WizardsTowerRStr
@0x55706794 / TowerRStr @0x55706874 xrefs + how it filters spells by sphere);
(3) pick a free spell ID above vanilla max (TSpellControl.GetCount after init)
+ freeze it; (4) icon (reuse an existing spell's seq-10 book icon); (5) the
init-cave hook site (after a Register*Spells call, e.g. RegisterCitySpells /
the UnitSpells register fn). Night Vision id 0x27, True Seeing 0x29 (verified,
[[underground-nightvision-atk-penalty]], [[trueseeing-vs-invisible-atk-penalty]]).
MP: all peers need the patched DLL. Ability ids: [[ability-id-map]].
STATUS: RE done to the design-fork point; NO code written yet.
