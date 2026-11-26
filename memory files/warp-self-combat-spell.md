---
name: warp-self-combat-spell
description: "PLANNED custom spell 'Warp Self' — Secret L3 TACTICAL-COMBAT spell: caster teleports to a target hex ≤8 away (valid+empty terrain). RE/architecture DONE 2026-08-10; build not started. Uses full custom-spell toolchain + reuse synced combat-move path."
metadata: 
  node_type: memory
  type: project
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-11T02:27:25.758Z
---

**GOAL (user spec 2026-08-10):** new **Secret sphere, level 3, TACTICAL-COMBAT**
spell. Target a hex up to **8** away; caster (ONLY the caster) teleports there.
Must be valid terrain, unoccupied. Movement cost = standard (casting a spell
consumes all the caster's MP, like any usable ability — handled by the normal
cast pipeline, no extra work). Design LOCKED: targeted hex (not random).

## FEASIBILITY: confirmed. Architecture RE'd, build NOT started.

**Chassis (routine, all proven this session):** clone a hex-targeting combat
spell. Combat spells = CombatSpells module (AoWEPACK). TCallFlames.Create
@0x557F8CE4 is the model: TCombatSpell.Create @0x557F7200, then id [+0x10],
name [+8], and a **combat param block @[spell+0x34]**: byte[0]=kind(9),
byte[1]=power(4), word[2]=?, byte[4]=flags(1), **byte[5]=RANGE(0xC=12)**,
byte[6]=1. So set range=8 there. Combat spells are **kind-dispatched** in the TC
engine (same kind family as the SpellTypes bytes we fixed) — a NEW id with a
known kind fires fine (unlike the hurl-skull trap). RegisterCombatSpells
@0x557FA50C is the reg hook site.

**Targeting (exists):** combat pack imports HSEngine.THexagonSpriteSelection.
SelectLocation — TC CAN select an empty hex. Map-side hex-target model =
TGlobalTargetSpell.SetupTargetSelection @0x5579E590: TTargetSelectionControl.
Initialize @0x557635FC; flags byte [sel+0xd] (hex=0x0D, unit-spell=0x08/0x04);
caster loc → [sel+0x24/28/2c]; **max range → [sel+0x20]** (GlobalTargetSpell
uses 0xc); ValidTarget @0x55763338. Per-spell validity vcall = ValidTargetSelectionMapF (e.g. TFreezeWater.ValidTargetSelectionMapF @0x5579EBDC) —
hook ours: require passable + **unoccupied** + dist 3..8 (user said "up to 8";
min-3 optional).

**THE TELEPORT CORE (the one hard part, NOT yet built):** live TC unit hex is
in HSEngine map-field occupancy + the unit's **TTacticalCombatUnitHS** (AoWTCPCK
@0x412D08). GetX/GetY = vcall [fieldHS_vmt+0x74]/[+0x78]; map-field flags word
[field+0x18] (0x4000/0x2000/0x2000000 = redraw/dirty bits, see UpdateMapField
@0x420CC4). ⚠ **TUnitPositionControl.SetUnitPosition @0x4289C0 is the 8×7
DEPLOYMENT grid (bounds y<7,x<8), NOT the live hex map — do not use for
teleport.** **CORRECT approach = reuse the game's own SYNCED move:
CombatTE.MoveCombatUnit @0x40F584 / CreateCombatMoveTE @0x40F548 /
TCombatMoveTE (@0x4076D4; DefaultMove @0x408864 reads src field [TE+0x1c],
dst field [TE+0x2c], each [+0x60]=fieldHS).** Driving a move-TE from caster
hex→target hex keeps MP-lockstep (hand-poking map fields WOULD desync — cf
[[lan-desync-investigation]] movedraw). RE task remaining: how a MoveTE is
constructed/queued for a single unit to an arbitrary dest, and whether to bypass
its pathfinding (warp = ignore path, straight place) vs let it walk. Simplest
build v1: from the combat-cast handler for our id, build+dispatch a MoveTE
caster→target (teleport, no walk anim) via the token manager.

**Presentation (routine):** Teleport-in/out frames EXIST — Effects/Magic.ILB
recs 0-11 = Teleport00-11 (image ids 0-0xb). Icon = free SPELLICN id (52 free,
or a new pair). pfs record via build_summon_mermaid-style script + CRC.
**MUST set SpellTypes[newid] byte** (AoWTCPCK file 0x662F4+id) — combat spell,
pick the kind matching the donor (Call Flames path) so Token Start doesn't error
(cf [[summon-mermaid-spell]] SpellTypes rule).

## MOVER FULLY RE'd 8/10 (the "long pole" — now DONE, no unknowns left):
Combat-spell **effect dispatcher** = the big jump-table func @ AoWTCPCK 0x415990:
reads `SpellTypes[spellid]` @0x4159EC (value 0..0x2f) → `jmp [eax*4+0x415A39]`
(table of ~48 combat-effect handlers keyed by SpellType). **So a combat spell's
in-combat EFFECT is chosen by its SpellTypes byte.** Warp = give our spell a
SpellType whose handler we hook (or a free/unused SpellType index → add a case).
**TCombatMoveTE** (@0x4076D4): [TE+0x1c]=combat unit, [TE+0x14]=path (HSEngine
TXYLList of hexes), [TE+0x18]=step index, [TE+0x2c]=dest field, unit's current
field = [combatunit+0x60], player=[+0x45], moveMP=[+0x5c]. `ExecuteDefaultMove`
@0x408278 single-steps: reads next path hex, calls **TTacticalCombatUnit.MovedTo
@0x41CF88** (`MovedTo(eax=unit, edx=?, ecx=?, [ebp+8]=movecost)`: subtracts cost
from [unit+0x5c], clamps ≥0, then fire-trail if !HasAbility(0x2b)), swaps the
field pointer, then vision: **ExploreArea (AoWE vcall)** @0x4084B2 + **MapChangedRad**
@0x4084FD + TriggerMapChangedEvent @0x4028D4 (redraw old+new rects). GetX/GetY of
a field = vcall [fieldHS_vmt+0x74]/[+0x78]. Field lookup: TMapLevel.GetField
(HSEPack) by (x,y); THSMap.PlaceHX @0x402264 places an object on a hex.
map singleton = [0x469420]→[+..]. **Teleport = build a MoveTE with path =
[caster_hex, target_hex] (2-point, straight warp — no walk) and let the token
system run it (fully synced, no hand-poke → no desync); OR direct: free unit from
old field, set [unit+0x60]=targetfield + occupancy, MovedTo, ExploreArea+
MapChangedRad both hexes.** Prefer MoveTE path (reuses synced token pipeline).
⚠ SYNC MODEL still unverified (does TC sync per-action over LAN?) — MoveTE-path
is safe either way; direct field-poke is only safe if TC is local-resolve. Verify
or just use MoveTE.

## ★ STAGE 1 ✅ USER-CONFIRMED 8/10 (all 4 checks pass: registers/shows, hex-target ≤8, placeholder flames fire, vanilla Call Flames unaffected). Built by `build_warp_self_stage1.py`:
spell id **0xCA (202)** "Warp Self", Secret L3, cast 8, **TCallFlames clone**
(classref [0x557F51D0], Create 0x557F8CE4) w/ range byte [spell+0x39]=8. Hook =
last RegisterSpell in RegisterCombatSpells @0x557FA83F (`E8 FCF2F7FF`, ebx=
control); cave @0x55810A00 (105B). SpellTypes[202]=7 set (AoWTCPCK). pfs key 212
= copy of Call Flames key 123 w/ desc/icon id 52 (placeholder boot glyph)/cast 8/
sphere 7/level 3, root-append + CRC. Backups *.bak_warpself (all 3 files).
**PLACEHOLDER EFFECT = Call Flames fire** — casting works end-to-end; STAGE 2
replaces effect w/ teleport (hook TCAbRangedTE.Execute @0x40B2F8 flames branch:
if [token+0x18]==0xCA → move caster to target hex via the RE'd mover instead).
Test asks: spell registers/shows? combat cast targets hex ≤8? flames placeholder
fires? vanilla Call Flames unaffected?

## ★ STAGE 2 v4 APPLIED 8/10 (awaiting test). History: v3 fake-ctx CanMoveOn
passed rocks (only blocks overlay==8/water); v3.1 obstacle-class guard
(0x22052A) ALSO failed (rocks aren't found that way / dirt walls are terrain,
not objects). User also wants wall rules per abilities (wall climbing/pass
wall/flying ok, others blocked). **v4 = use the ENGINE's own per-unit validity
end-to-end — the TMoveControl.CanMove pattern:**
1. settings = TCombatMoveControlSettings.Create (classref [0x4129A8], AoWEPACK
   TMoveControlSettings.Create thunk 0x40263C), filled EXACTLY like the AI donor
   **TCAI.EvalBattle @0x418D73**: SetSourcePos(thunk 0x40266C, casterX/Y, lvl0);
   [set+0x9C]=casterHS; [set+0x1AC]=0x1A (byte [0x41B0A8]); [set+0x65]=0
   (=ResetState); CreateMovePointTable([caster+0x4C] unit RESOURCE, &set+0xAC)
   (thunk 0x4029BC — builds the per-terrain cost matrix from the unit's own
   movement abilities); [set+0x6C]=GetPlayer (thunk 0x402544); [set+0x98]=0xC8.
2. control = [[0x46C064]+0xFC] (live combat TMoveControl). **Activate(control,
   settings) @0x5574646C** (bail to release+fizzle if false — no Deactivate on
   fail, per CanMove @0x55746804). Per-candidate verdict = **TMoveControl.
   ValidLocation @0x557458E8 (eax=ctrl, edx=x, ecx=y, stack=lvl, ret4) → al**:
   base terrain matrix + full object CanMoveOn chain — rocks, UG dirt walls,
   water, walls all per caster abilities. Then **Deactivate @0x557466B4**,
   settings **Release (thunk 0x40265C, refcounted free)**.
3. Unit-occupancy guard (FindOwnedChild 0x220104) kept — engine check allows
   friendly pass-through. Cross-module AoWEPACK calls: delta from GetPlayer IAT
   slot 0x46E7CC − static 0x557268E4. Cave 692B @0x438100 (limit 0x438400).
KEY VMT/RE: TMoveControl: matrix@+0x30(rows of 16 by [field+0x14]/[+0x15]),
unitHS@+0x1E0, flags@+0x1E4, settings@+0x1DC, MoveOnMovePointProc fnptr@+0x140
(self@+0x144); TCombatMoveControl VMT@0x412AC4 tiny {SetupMove thunk,
ProcessMove 0x41D038}; Activate asserts ctrl-not-active + srcpos≠-1.
FindOwnedChild matches child vcall+0x24 = owner classid (unit 0x220104,
fleeloc 0x220528, obstacle 0x22052A). vcall [unit+0xA8]=GetAbilityEnabled. v2 teleport CONFIRMED WORKING by
user (warp ✓ / occupied-fizzle ✓ / Call Flames unaffected ✓), BUT blocked-hex
target teleported INSIDE obstacles → v3 adds **summon-style destination
search**: loop HN 0..6 via CenterHNtoHX thunk 0x4022AC (SPIRAL index: 0=center,
1..6=ring1; args eax=x,edx=y,ecx=HN, stack &outX,&outY, ret 8) around target;
per candidate: bounds vs TMapLevel +0xC width/+0x10 height (⚠ GetField has NO
bounds check — off-map = garbage ptr, must pre-check), skip if unit
(FindOwnedChild 0x220104 — must stay separate: unit CanMoveOn ALLOWS friendly
pass-through), skip if **TMapField.CanMoveOn(field, fakectx, 0, 0) == -1**;
first valid hex wins (deterministic → LAN-safe); none → fizzle. **fakectx** =
zeroed 0x1E8-byte stack block, only [ctx+0x1E0]=casterHS needed (→+0x1C=unit;
all implementers checked: obstacle/terrain block ability-0x3B-Walking when
GetOverlay==8 [water], flyers pass; citywall reads flags +0x1E4 & gate-target
+0x18/+0x1C — zeros = conservative path; fire/fleeloc cost-only, never -1;
TMovementHS [self+0xC]==0 → -1). CanMoveOn (HSEPack, NOT in AoWTCPCK IAT)
called cross-module rebase-proof: addr = [IAT 0x46E22C (GetField slot)] -
0x55608D84 + 0x55608130. CanMoveOn sig: (eax=field, edx=ctx, ecx=cost_in,
stack=arg) → eax=cost, -1=blocked; iterates children vcall [vmt+0xD0](obj,
&{ctx,field,arg,lvlbyte}, &{cost,?,done}).

## STAGE 2 build detail (v2, teleport core — CONFIRMED):
**v1 BUG (user hit "ton of errors / error during token start" on cast):** I set
step [te+0x18]=0 before ExecuteDefaultMove — but its ENTRY vcall [vmt+0x64] =
**TMoveTE.Move which PRE-DECREMENTS [te+0x18]** (`dec [eax+0x18]` first insn!)
→ step became -1 → path Get(-1) garbage → exceptions every tick. Fix: set
step=1 (mirrors InitializeMove's count-1); Move decs → 0 = dest entry. ⚠ RULE:
never call ExecuteDefaultMove with step N to process entry N — pass N+1.
TCombatMoveTE VMT (@0x4076D4): +0x4C Execute/+0x50 GetMapF/+0x54 ProcessMove/
+0x58 Validate/+0x5C InitializeMove/+0x60 FinishMove/+0x64 Move(pre-dec)/
+0x68 LastMove/+0x6C DefaultMove/+0x70 Setup.
**Teleport effect live.** Hook @AoWTCPCK 0x40B452 (phase 0 of TCAbRangedTE.Execute,
5-byte `mov eax,[0x469420]` right AFTER the CombatSpellCast block) → call cave
@VA 0x438100 (file 0x37500, 222B, inside the big CODE zero region 0x37480+).
Cave: if [token+0x14]==0x34 && [token+0x18]==0xCA → GetField(map, [tok+0x20],
[tok+0x22], 0); fizzle if FindOwnedChild(field, 0x220104) (unit there — incl.
self-target); else TXYLList[dest,src] (cost/level 0 → survives Setup at 0 MP),
CreateCombatMoveTE(caster=[tok+0x10]) → Validate → [te+0x18]=0 →
**ExecuteDefaultMove** (one-step warp: TUnitHS.MoveTo + AddHS + MovedTo +
ExploreArea/MapChangedRad/redraw) → Free te+path; zero caster MP (mirror
0x40B6F6); [ebp-9]=1 (token done); jmp 0x40B70F epilogue → phase-1 flames never
runs. **Sync model: effect runs deterministically inside the broadcast token on
every machine — no new token queued (MoveCombatUnit UNUSABLE here: its
PlayerReady gate = "no tokens executing" = always false inside Execute).**
Reloc: hook operand's HIGHLOW @.reloc word file 0x827C0 neutralized 3→0
(AoWTCPCK ALWAYS rebases — base collides with AoWx.exe; cave is PIC via
ret-addr delta, calls rel32). Backup AoWTCPCK.dll.bak_warpself2.
KEY RE (this session): TCAbRangedTE token = **spell-as-ranged-action**:
+0x14=ability id (0x34=cast-spell marker), +0x18=spell id, +0x1c/1e=CASTER hex
(words, used to re-find caster→[+0x10]), +0x20/22=TARGET hex, +0x24=type byte,
+0x2c=sound handle, +0x38=phase. Call Flames=id **0x75**, its fire effect
hardcoded per-id in phase 1 (TList [map+0x11c] scan). Path lists are
**[dest…src] reversed**; entry=x|y<<8|lvl<<16|cost<<24; Validate resolves unit
from LAST entry; MovePointsToPos(0-cost,0 MP)=0 ✓; TMapField vcalls:
+0x7c FindChild/+0x80 FindOwnedChild/+0x84 FindChildIndex; unitHS vcall
+0x10c=TUnitHS.MoveTo; AddHS auto-grows (no capacity refusal → EDM's -1
"unit removed" branch unreachable). TMoveTE.Create(edx=0)=unregistered,
Destroy frees path — safe to Free unqueued TE.
KNOWN GAPS (stage 3 candidates): targeting validity still TCallFlames' (can
select occupied/obstacle hex — occupied fizzles [MP+mana still spent];
obstacle/water hex NOT guarded — unit may stand on rocks; proper fix = hook
ValidTargetSelectionMapF for empty+passable), no teleport visual (Magic.ILB
Teleport00-11 frames exist), no sound (skipped PlayEx block).
TEST ASKS: cast at empty hex ≤8 → caster warps there, MP 0, no flames? cast at
occupied hex → nothing happens (fizzle)? vanilla Call Flames still fires?
LAN 2-PC: warp on both screens, no OOS? obstacle-hex target → what happens?

## ★ SIEGE QUALIFICATION APPLIED 8/10 (`build_warp_self_siege.py`, awaiting
test): knowing Warp Self lets a hero attack WALLED structures (like breach
spells). **STAGE 2 v4 (engine-validity dest search) USER-CONFIRMED ✓** (rocks,
UG dirt walls, walls all correct). Siege RE: army wall-gate chain ends in
**TSpellCastingAbility.CanCastBreachWallSpell @0x5576DEF0 (AoWEPACK)**: unit
must be THero; loops player's known-spell ids ([playermagic+0x30] TIntegerList,
magic=[player+0x54], idx ebx, magic cached [ebp-0x18]); per spell: [spell+0x22]
must be 0, vcall [spell_vmt+0x7C](spell, unit, &4-byte TWallCombatFeatures rec
@[ebp-0xD]) → **bit1 of [ebp-0xA] = "breaches walls"**, then
THero.CanCastCombatSpell @0x55789A3C gates castability. GetCheatEnabled
short-circuits true. Patch: 6-byte hook @0x5576DF90 (`test [ebp-0xA],1;je`) →
call cave @0x55810B00 (35B, no PIC needed — only rel32): breach-bit OR
spellid==0xCA (re-derived via TIntegerList.Get([[ebp-0x18]+0x30], ebx)) →
qualify (ret→0x5576DF96); else add esp,4; jmp 0x5576DFB4 (reject path).
Backup AoWEPACK.dll.bak_warpsiege. **Next free AoWEPACK cave: 0x55810B80.**

## ★ RENAMED "VOID STEP" + CUSTOM ICON APPLIED 8/10 (awaiting icon check).
v6 presentation USER-CONFIRMED WORKING ✓ (Warp Party teleport anim + one-shot
sound + turn-1 fix all good). **User edited desc+cost (cast now 5) IN THE
EDITOR — never regenerate/rebuild record 212 wholesale; pfs record content is
user-managed now (icon section only via scripts).** Rename: name literal lives
in stage-1 cave @VA 0x55810A60 (AoWEPACK); "Warp Self"→"Void Step" same 9
chars in-place (`build_void_step_rename.py`, bak AoWEPACK.dll.bak_voidstep;
stage1 script NAME updated too). Icon (`build_void_step_icon.py`, bak
SPELLICN.ILB.bak_voidstep): image id 52 pair = **recs 88 (cloud) / 89
(glyph)**; cloud ← copy of rec 144 (Mermaid id-88 pair's SECRET dark
blue-purple cloud; Magic Sight rec 210 identical); glyph = person upper body
dissolving into 3 teleport rings, painted on rec 89's own colorkey **0x4148**
(NOT white — key is per-record in header!). ILB record header after marker
0x10935056: [dd subW][dd subH][dd subX][dd subY][dd colorkey]...[FFFFFFFF then
dd imageid only on cloud recs]. Concealment = sphere 3, icon id 156 (recs
220/221, glyph 28x31 sub @(6,2)) — the id-42 pair note in magic-sight script
is stale. Spell record key↔id mapping still unknown (212↔0xCA works).

## ★ PRESENTATION v6 APPLIED 8/10 — v5 had 3 bugs, all root-caused:
1. **SFX looped forever**: TSFXLibrary.PlayEx 5 stack args; the FIRST-pushed
   ([ebp+0x18]) is the LOOP flag → chained cl→…→PlaySampleEx vcall
   [sample+0x10](SetLooped). Vanilla passes loop=1 for ALL spell sounds and
   stops via [token+0x2c] handle freed at token end (epilogue 0x40CC55);
   our instant-end token must pass loop=0 (one-shot), don't store handle.
2. **Token error turn 1 / stale validity later**: base TMoveControl.Activate
   does NOT set [ctrl+0x1E0] (unitHS) / [ctrl+0x1E4] (flags) — the TC override
   TCombatMoveControl.ProcessMove @0x41D038 copies them from settings
   (+0x9C/+0x1AC) before calling base. Cave now copies them after Activate.
   (NULL on turn 1 → CanMoveOn NULL-deref only when target hex HAD a blocking
   object; stale unit later → wrong-ability validity.)
3. **fx invisible**: TfxHS anims are driven by NewFrame @0x429E78 (jmptable
   @0x429EF7 by [fx+0x34] type, 0..0x30; [fx+0x10] frame ctr starts -1;
   [fx+0xC]=done, [fx+0xD]=dead). **Type 0x22 handler @0x42DB6D resolves
   frames from the TAGGED spell/ability: [fx+0x14]==0x34 → GetSpell([fx+0x18])
   → [spell+0x2C] image-seq list → GetImageSequence(0); untagged → ability 0
   → no seq → instantly dead/invisible.** Cave now tags fx 0x34/0xCA.
   + `build_warp_self_castfx.py`: record 212 tag 0x0C cast-fx SECTION replaced
   with key 44's (vanilla teleport spell = **EFFECTS\MAGIC.ILB frames 0..0xB =
   Teleport00-11 = the Warp Party look**), our SPELLICN/BORDER sections kept
   (splice at `0C000000SPELLICN.ILB`; record 212 is LAST in file → rebuilt in
   place + CRC; tag order preserved, byte-pair table rebuilt). Backup
   Spells.pfs.bak_warpcastfx. Blob layout: [dd 0x17][00] then sections:
   [dd pathlen][path][00][flag][04][dd][dd xoff][dd yoff][dd][dd count]
   [count×dd frame ids][~12 byte flags]; spell record key ≠ spell id but
   record 212 serves spell 0xCA (mapping unknown, works).
   Cave now 917B @0x438100 (limit 0x438500).

## (v5 notes, superseded): SIEGE patch USER-CONFIRMED ✓.
Sound: `build_warp_self_sound.py` — Spells.pfs rec 212 tag 0x0B embeds
length-prefixed sound path; swapped 'SFX\ATTACK\FIRESTRT.WAV' →
'SFX\PLACES\TELEPORT.WAV' (same 23-char len, in-place + CRC; vanilla teleporter
sound; bak Spells.pfs.bak_warpsound). Cave v5 found-path plays it via engine
block: GetSpell(0xCA)→[spell+0x28] sfx obj→PlayEx(thunk 0x4022FC, eax=sfx,
edx=0, ecx=0x40, 5 stack args 1,0,1,0,0) w/ null guards.
Visual: **TC fx system RE'd** — TAoWCombatMap.AddEffect @0x41C6EC (eax=map
[0x46C064], dl=TfxType) → TfxHS into list [map+0x11c] (list phase-1 scans by
[fx+0x14/0x18] ability/spell tags — leave 0!). Position: TObject.Create(classref
[0x46EB24]) point → TXYZList.Add([fx+0x1c]); HXtoHP (thunk 0x4022BC, eax=hexX,
edx=hexY, ecx=&px→[pt+4], stack=&py→[pt+8], ret4) + 0x10/0x10 center (PrayerGlow
donor 0x42DEC9); [pt+0xC]=variant (blood colors). **TfxType enum** (RTTI
@0x411632): 0xF SFOverlay, 0x19 Dispel, 0x1A WallSmoke, 0x1B Blood, 0x22
CloudPuff(=summon materialize, USED for warp puffs src+dest), 0x26 PrayerGlow,
0x27 Resurrect, 0x29 Frost, 0x2D DecayComet... makefx subroutine @cave+0x30D.
Cave now 865B @0x438100 (limit 0x438500). ⚠ AoWTCPCK zero-region has a PRIOR
occupant @0x437FA0 (MakeHitBlood blood-color patch caves) — cave space below
0x438100 NOT free. Donor sites: MakeHitBlood 0x40992C, CloudPuff summon
0x429B34, PrayerGlow 0x42DEC9. No fxTeleport type exists; Magic.ILB
Teleport00-11 unused by TC fx (would need new type = big job).

## BUILD PLAN (original): 
1. teleport primitive: MoveTE caster→hex, no-walk; test via temp trigger.
2. v1 spell: register (id ~0xCA, Secret L3, range 8), combat-cast handler hooks
   the donor kind's TC exec → if our id, teleport caster to selected hex;
   validity hook (empty+passable+≤8); SpellTypes byte; pfs+icon.
3. polish: teleport visual, min-range 3 if wanted, edge cases (no valid hex).
Cave space: next free 0x55810A00 (AoWEPACK). Related: [[summon-mermaid-spell]],
[[magic-sight-spell-re]] (toolchain), [[lan-desync-investigation]] (sync rule).
