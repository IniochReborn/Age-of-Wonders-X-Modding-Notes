---
name: keeper2-armycombatmovete-crash
description: "Keeper2.csm TE crashes: all AV-family bugs fixed & shipped in 404; OPEN = GetChild 'Index out of bounds' (vichan's Delgates-capture 100% repro on HIS machine only — diagnostic kit sent 8/14, awaiting screenshots) + one-off MP LogbookChanged triage."
metadata: 
  node_type: memory
  type: project
  originSessionId: b6d320bc-2062-4946-bd64-d75f46d799f0
  modified: 2026-08-14T21:37:09.170Z
---

## ▶ 2026-08-14 — VICHAN REPORT (campaign scen. 1, capture DELGATES = final objective) + REMOTE DIAGNOSTIC KIT SHIPPED
Player vichan: capturing Delgates crashes EVERY time on his machine — attack ⇒
`...TArmyCombatMoveTE`, buy ⇒ `...TENegotiate` — but his save
(`X/Save/vichan test.acg`) plays FINE on the user's machine, all routes. Both
routes converge on city-capture processing ⇒ likely ONE bug behind both TE
dialogs; prime suspect = the still-open GetChild raise (crash #7 pattern:
deterministic for one player, unreproducible for another, identical binaries).
He's believed on 404 (if <404 the stale-reloc mechanism explains it outright).
✅ **KIT BUILT: `share to discord/AoWx_diagnostic_kit_delgates.zip`** (source
dir `share to discord/vichan diagnostic/`): probed **HSEPack.dpl** (getchild
probe v3 APPLIED to a COPY — live file reverted, hash back to 404's
1298256e…) + diagnostic **Network.dpl** (v2 detail, our live copy) + player
README. Decode when screenshots arrive: 2nd dialog gives module+offset for ANY
exception; if it's the GetChild raise the probe instead makes it
`EAccessViolation ... Read of address 8XXXXXXX` ⇒ **caller static VA =
value & 0x7FFFFFFF**. Neither file is behavior-changing in normal play; told
him to restore originals after + not to play MP with them.
**GetChild caller RE (2026-08-14, static hunt — why the probe is the only way):**
- NO direct E8 callers anywhere: HSEPack internal = 0; AoWEPACK & AoWTCPCK
  import it only as jmp-thunks (0x55701FB4 / file-VA 0x401D84) with ZERO E8
  callers — those thunks exist solely to fill descendant VMT slots.
- Hierarchy: TMapField VMT **0x55602500** (HSEPack) → TAoWMapField VMT
  **0x5570C764** (AoWEPACK) → sibling TAoWCombatMapField VMT **0x411C8C**
  (AoWTCPCK). GetChild = VMT+0x4C in all three; every call is virtual.
  (VMT self-ptr at −0x40, classname ptr at −0x20 — useful for future VMT ID.)
- ★ Raise semantics: `cmp edx,ecx; jl` ⇒ **GetChild(0) on a 0-child field
  raises** — any caller ASSUMING a hex has ≥1 child (e.g. "city hex ⇒ has an
  HS") raises the moment capture-processing removes/re-adds children.
- Count-read+GetChild proximity scan: only clean iterators found
  (TTransportMEC.CalculateMoves @0x55741D36 reads count first; HSEPack's own
  Find*/GetMaxLevel* families likewise). TAoWHexagon.UpdateTransition's
  call[+0x4C] is a FALSE positive (not a TMapField descendant).
- Machine-dependence theory for a raised (state-driven) exception: synchronous
  UI redraw inside the TE's try-block is VIEWPORT-dependent — different
  camera/resolution ⇒ different hexes touched. Cheap experiment: user reruns
  the capture at vichan's resolution / camera centered on Delgates.

## ▶ 2026-08-14 — MP "Exception occurred during LogbookChanged event (TAoWMapControl)" (one player, once) — TRIAGED, PARKED
6h MP session otherwise clean, no CombatMoveTE. That dialog family =
TAoWMapControl event-handler wrappers in AoWEPACK (strings @file 0x105251..
0x106a0d; combat twins in AoWTCPCK @0x35da1..) — each wrapper try/excepts the
user's On* handler and prints ONLY the fixed string (Network.dpl diagnostic
does NOT cover these — separate reporter from the TE one).
Path RE'd: OnLogbookChanged → AoWx.exe `TheMapLogbookChanged` @0x44F97C
(fires only if event's player == local player [engine+0xA5] — **why exactly
one player saw it**) → refresh @0x423304 → `TEventLogbook.ListEvents`
@0x557FDA00 (per event: vcall+0x60 visible-check, vcall+0x4C GetText, add to
list) → `TAOWListBox.SetListOff(count-1)` (aowInt).
- THeroUpgradeEventLog.GetText @0x55785558 is NIL-GUARDED (missing hero ⇒
  clean skip) — mod's level-up event NOT implicated; AddEvent cave 0x5580F600
  re-disassembled 8/14: correct, gated to hero-upgrade events only, and its
  exceptions would surface under a TE dialog, not LogbookChanged.
- Never touches TMapField ⇒ almost certainly NOT the GetChild bug.
- Likely: some other event class's GetText derefing a stale ref (candidates:
  TCombatEventLog/TSpellCast/TDiplomaticAction/TCityRebellion GetText).
  One-off ⇒ parked; if it recurs, extend the detail diagnostic to these
  wrappers (they're in SHIPPED AoWEPACK though — local-only, revert per cut).

## 📦 RELEASED as 1.37.404 (2026-08-13) — `upload/AoWx_1_37_404.zip` (208.0 MB, 658 files)
Contents vs 403 = exactly **3 changed files**: `AoWEPACK.dll`, `AoWSetup.exe`,
`.AoWx Manual.html`. Version bumped via **`patch scripts/patch_version_404.py`**
(file 0x9701B `93010000`→`94010000`, backup `.bak_version403`).
★ **A REUSABLE PACKAGING SCRIPT NOW EXISTS: `patch scripts/build_release_zip.py`**
(`--prev 403 --next 404 [--apply] [--manual]`) — re-reads the previous zip's
namelist from disk, REFUSES to cut if any listed file is missing, prints the
changed-file diff, verifies the written zip (entry order + testzip), and with
`--manual` refreshes `upload/.AoWx Manual.zip` + `upload/index.zip` (single
entry `index.html`). Also hand-refresh `upload/index.html` (loose web copy).
Manual rebuilt with `patch scripts/manual_build/build_manual_from_game.py`
after editing its hardcoded `version=`/`lastupdated=` line (~line 1263).
⚠⚠ **PRE-RELEASE GOTCHA HIT THIS CUT: `HSEPack.dpl` IS SHIPPED, and the
GetChild caller probe was still armed in it.** Reverted before packaging
(`build_getchild_caller_probe.py --revert`) — otherwise players would get a
deliberate ACCESS VIOLATION instead of the engine's normal handled
'Index out of bounds'. (Contrast Network.dpl, which is NOT shipped, so the
TE-detail diagnostic there can stay applied forever.) ★ Rule: before any cut,
check every armed diagnostic against the zip's namelist, not from memory.
Shipped in 404: heal-executor fix, 4 stale-reloc neutralizations, GetAbilityData
guard v3.1 + recorder, lifesteal nil guard, all AoWSetup v3 work.

## ✅✅ 2026-08-13 — **COMPLETE LEVEL-LOOKUP AUDIT: all 11 sites accounted for, only lifesteal was broken**
Prompted by the user asking about Charge/Parry. Definitive inventory of EVERY
multilevel level-lookup in mod cave space 0x5580C000-0x55812000
(scan `ff 9x b0 00 00 00` = combat GetAbilityLevel, `ff 9x 44 01 00 00` =
strategic TUnit.GetAbilityLevel):
| site | ability | gate | verdict |
|------|---------|------|---------|
| 0x5580E174 | Life Stealing 0x76 | CA flag 0x08 from *Generate* | ⚠ WAS THE BUG → nil-guarded |
| 0x5580E3EE / 0x5580E44E | Hero Slaying 0x38 | +0xA8 in-block | ✓ |
| 0x5580E479 / 0x5580E4A9 | Monster Slaying 0x70 | **caller-gated**: vanilla blocks do +0xA8 on attacker (0x557666AA / 0x55767C65) AND +0xA8 0x3F on target, both `test al,al; je` before `call cave` | ✓ |
| 0x5580E53D / 0x5580E58F | ranged 0x70 / 0x38 | +0xA8 in-block | ✓ |
| **0x5580EAFD** | **Charge 0x6F** | caller does `call [ecx+0xA8]` on **esi** @0x55767BC0, cave opens `test al,al; je` and uses the SAME esi | ✓ SAFE |
| **0x5580EB1D** | **Parry 0x71** | same shape on **edi** @0x55767BD7 | ✓ SAFE |
| **0x5580EB3D / 0x5580EB5D** | Charge/Parry, **strategic** | operate on a TUnit via +0x148 gate → +0x144; **never a combat object, so no [obj+0x4C] deref exists** | ✓ SAFE |
★ The distinguishing rule confirmed: a level lookup is safe iff its nil-safe
+0xA8 (or strategic +0x148) check is on the SAME object in the SAME function.
Life Stealing was the lone case where the gate lived in a different function
(Generate) from the deref (Execute) — which is exactly why it was the one that
could fault.

## ✅ 2026-08-13 — LIFE STEALING AUDITED & GUARDED (user asked "we fixed healing, what about lifestealing?")
**The user's hunch was right — and it was the ONLY remaining hole.**
★ KEY ENGINE ASYMMETRY (settles this whole family):
`TCombatUnit.GetAbilityEnabled` **VMT+0xA8 @0x55725004 IS nil-safe**
(`mov ecx,[eax+0x4C]; test ecx,ecx; je → 0`) but
`TCombatUnit.GetAbilityLevel` **VMT+0xB0 @0x55725028 is NOT**
(`mov eax,[eax+0x4C]; mov ecx,[eax]; call [ecx+0x144]`).
⇒ **a nil [combatobj+0x4C] is a NORMAL engine state** (vanilla defends it), and
+0xB0 is only ever legal directly behind an +0xA8 gate.
**Full audit of every mod call to +0xB0** (scan `ff 9x b0 00 00 00` in
0x5580C000-0x55812000): melee Hero-Slaying 0x5580E3EE/0x5580E44E, ranged HS
0x5580E53D/0x5580E58F, Monster Slaying 0x5580E479/0x5580E4A9, WallCrushing
0x5580EAFD/0x5580EB1D — **all sit immediately behind an +0xA8 gate ✓ safe**.
**ONLY `cave_lsround` @0x5580E16F (leveled Life Stealing) was unguarded**: its
gate is CA flag 0x08 set back in *Generate* (cave_lsgen 0x5580E1A0), while the
deref happens later in *Execute* (hook @0x5576678C) after the attacker object
is re-resolved by id (GetObject @0x55766748) — a dead/detached attacker gives
+0x4C = nil ⇒ AV. Vanilla's own lifesteal block @0x557667B8 heals purely via
virtual +0x88/+0x8C and never touches +0x4C, so this was mod-introduced —
same "added a dereference the original never made" family as the heal executor
and the mlheal disaster.
✅ **FIX: `patch scripts/build_lifesteal_level_nilguard.py`** (APPLIED
2026-08-13, backup `.bak_lsnilguard`, `--apply/--revert/--status`): rewrites
cave_lsround **in place, 62 B inside its existing 64 B slot** (nothing moves)
adding `mov eax,[edi+0x4C]; test eax,eax; je level1` before the +0xB0 call;
nil ⇒ level-1 default (the value the cave already used for legacy level-0
data) and the heal proceeds through the nil-safe virtuals ⇒ **zero behaviour
change except that the crash case now heals instead of faulting**. Encoding
squeezed with `push 0x76/pop edx` to fit. Verified: disasm on disk, slot tail
still zero, hook untouched, 63,878-reloc rebase simulation leaves it intact.

## ★★★★★ 2026-08-13 NIGHT — RECORDER NAMED THE CULPRIT + STALE-RELOC DISCOVERY (biggest find of the hunt)
**CRASH #9** detail = guard vtable read @0x5581103**5** with node **0xE0000**
(slipped the 0x10000 floor). But recorder scratch had already caught the FIRST
bogus call: **caller static 0x5580E6F0 = the `call GetAbilityData` inside the
Healing-level helper cave 0x5580E6E0, ability 0x2F (Healing), owner
0x0D98EE08 with [own+0x10]=0x3C62** (stale/freed-unit signature; junk varies
per call: 0x3C62, 0xE0000, and by extension 0x47280000).
**ROOT CAUSE CHAIN (all verified by disasm + .dpl diff):** the July leveled-
Healing patch repurposed HealUnit(0x5576C374)'s Self from vanilla's Healing
ABILITY object (GetAbility(0x2F)) to the HEALER's TUnit so cave 0x5580E9B0
can look up the healing level. At the COMBAT executor site **0x5576BD24**
(fn 0x5576BCE0 = heal CA Execute: CA+0xD/+0xE object ids → 0x55728C68
GetObject → edi=healer/ebx=target) it feeds `mov eax,[edi+0x4C]` RAW — no
nil/class check — and vanilla's tolerance of junk there was load-bearing
(vanilla never walked it as an ability owner). Site 2 @0x5576C78F
(strategic path, 1-byte 8BC5→8BC6) gets a CanUse-validated unit = low risk.
Audits missed it 4× because it lives in PATCHED VANILLA CODE, not a cave.
✅ **FIX BUILT: `build_combat_heal_owner_fix.py`** (29 B in-place @0x5576BD24,
dry-verified): healer & target both through TCombatUnit-check helper
0x55810F00 (⚠ helper CLOBBERS ECX, preserves EDX); owner nil → helper
0x5580E6E0's nil-check → default heal 5 = vanilla-flat; target bogus → skip
HealUnit (POP before `je` — pop doesn't touch flags). Backup .bak_healowner.
**★★ STALE-RELOC DISCOVERY:** the fix's reloc precheck found the vanilla
absolute's reloc **@0x5576BD25 STILL TYPE 3** under the patch's NOPs ⇒ since
AoWEPACK ALWAYS rebases, every load materializes a BASE-DEPENDENT JUNK
INSTRUCTION inside the heal executor (this machine's usual deltas → harmless
AAA/cmp; other bases → junk reads/jmps/rets/WRITES). **Full audit (live vs
AoWEPACK.dpl, all type-3 relocs over changed dwords): 53 hits, 48 = intended
absolute rewrites (KEEP active), 5 = July-era patched-over relocs = the
defect.** The other 4 (all `build_stale_reloc_neutralizer.py`, backup
.bak_relocfix): **0x55726A4C + 0x55726AE1** (damage-halving-removal NOP runs
in the damage calc — runs EVERY damage event!), **0x55781B26** (3rd copy),
**0x55782B77** (dead padding after rewritten stat getter, inert). Other
binaries CLEAN (AoWTCPCK vs .dpl; HSEPack/aowInt/VCL30/Dcpack vs `pre-claude
rollback/Age of Wonders X - rollback/` pristine copies; AoWx.exe never
rebases). **This is THE mechanism for "crashes on his machine every time,
never on mine, identical files"** — junk decode is deterministic per load
base, and bases are stable per machine/boot. Friend's MP siege crashes are
prime candidates.
⚠ ALL 3 STAGED, AWAITING GAME CLOSE TO APPLY: heal-owner fix (+BD25 reloc
neutralize inside it), reloc neutralizer (4 sites), guard v3.1 re-apply
(NODE_MIN 0x10000→**0x400000**; apply assert relaxed to hook-only).
★ LESSON: audit sweeps must include PATCHED VANILLA SITES + their relocs,
not just caves. ★ Ship-worthy for 404: all wall fixes + guard v3.1 + heal
fix + reloc neutralizer would fix the friend without any diagnostic on his
machine.

## ▶▶▶▶ CRASH #8 (2026-08-13 later) — GUARD'S BLIND SPOT HIT; RECORDER INSTRUMENTATION LIVE
Second crash of the day was NOT GetChild: detail dialog =
`EAccessViolation in AoWEPACK.dll at 0011102D ... Read of address 47280000`
= the owner-guard cave's own `mov eax,[ecx]` node-vtable read @0x5581102D —
an ability-chain NODE = **0x47280000** (in old plausible range 0x10000..
0x7F000000 but unmapped = the guard's documented honest limit; NB the value
is float 43008.0 / packed words 0x4728,0x0000 — heap corruption, not a
pointer). So TWO distinct live bugs share the TArmyCombatMoveTE dialog:
(a) GetChild index≥count raise, (b) wild ability-chain corruption (the old
"loose end" family). ⚠ The GetChild probe correctly did NOT fire for (b).
**BOTH INSTRUMENTED & APPLIED 2026-08-13 (game-verified launch pending):**
1. `patch scripts/build_abilitydata_guard_recorder.py` (--apply/--revert/
   --status/**--read**; backup `AoWEPACK.dll.bak_abguardrec`) = guard v3,
   same hook 0x5574F1C4 + same cave slot 0x55811000 (192 B now): node
   ceiling tightened to **0x40000000** (real TAbilityData nodes are low-heap;
   vtable range stays ..0x7F000000 — vtables sit in rebased modules) ⇒
   0x47280000-class junk now DETECTED → nil return, NO crash, combat
   survives; and the FIRST bogus call is recorded sticky to BSS scratch
   **@0x558FAF40** (+0 flag, +4 caller runtime, +8 owner, +C bad node
   (1 = Self itself bad), +0x10 ability id, +0x14 delta). `--read` pulls it
   from the RUNNING game via Toolhelp+ReadProcessMemory (no crash needed).
   --revert restores plain v2 guard cave (rebuilds from old script).
   Residual: node in 0x10000..0x40000000 yet unmapped still faults (narrow).
2. `build_getchild_caller_probe.py` **v3** (99 B cave, same hook/cave): keeps
   the raise-case encoded-caller AV AND adds a SILENT negative-index logger
   → HSEPack DATA-page scratch **@0x5562E700** (+0 count, +4 last caller
   runtime, +8 first caller runtime, +C delta), `--read` works live.
   Tests the unifying theory: vanilla GetChild(-1) garbage reads may be the
   heap-corruption SOURCE feeding family (b).
NEXT: user plays normally; run both `--read`s after odd behavior or anytime
(no dialog required). Decode: static = runtime − delta.

## ▶▶▶ CRASH #7 = CRASH #3 CONFIRMED LIVE (2026-08-13) — `TMapField.GetChild` IS THE SURVIVING BUG
With all 403 fixes verified live (every shipped binary hash-matched the final
zip), the crash STILL fires: user re-ran campaign scenario 1 and hit
`TArmyCombatMoveTE`; captured live (grabwin recipe, forms 0x4790edc→0x47a0edc):
**`Exception Exception in module HSEPack.dpl at 00006EA7. Index out of
bounds.`** = the raise inside **HSEngine.TMapField.GetChild @0x55606E88**
(ExceptAddr = instr after `call @RaiseExcept` @0x55606EA2). So the wall/Hero-
Slaying family is genuinely fixed and the remaining bug is crash #3's raised
exception, which no AV probe could ever catch. Also reported by a player
online (aowx Discord), and almost certainly the friend's MP siege crash
(goblins+Butcher attacking a city, autocombat; crashed deterministically for
him on every reload, never for the user — action-sequence-dependent RNG
stream, NOT machine-dependent: both replayed with identical binaries).
★ GetChild disasm: `xor ecx,ecx; mov cl,[eax+0xD](count); cmp edx,ecx;
jl body(0x55606E8D→+8 array fetch)` — the check is **SIGNED `jl`, so a
NEGATIVE index silently reads garbage at [children-4·n]** (a possible source
of the older wild-pointer AVs!); index≥count raises.
**PROBE v2 APPLIED 2026-08-13:**
`patch scripts/build_getchild_caller_probe.py --apply/--revert/--status`,
backup `HSEPack.dpl.bak_getchildprobe`. Hook = 5 B @0x55606E88 (displaced
`33c98a480d`; verified: no relocs in range, no branch targets into displaced
bytes) → cave 38 B **@0x5562D820** (HSEPack CODE-tail slack 0x5562D818–
0x5562DA00, file-backed zeros; HSEPack cave space now starts 0x5562D850).
**SIGNED `jge` check = exactly vanilla's raise case**; bad index → AV on
`staticVA(caller retaddr)|0x80000000` (delta-corrected in-cave); valid AND
negative → re-enter 0x55606E8D with ecx=count, zero behaviour change. Decode: dialog `Read of address 8XXXXXXX` → caller VA =
value&0x7FFFFFFF.
★★ **v1 LESSON (2026-08-13): v1 used unsigned `jae` to also trap negative
indexes — WRONG: benign `GetChild(-1)` calls happen in NORMAL play (fired
before scenario 1 even started + "Exception occurred during DeselectHS event
(TAoWMapControl)") and vanilla tolerates the garbage read. A caller-probe
must replicate the original's failure condition EXACTLY, not "improve" it.**
Bonus fact learned: negative-index GetChild calls are routine ⇒ vanilla's
signed `jl` garbage reads DO happen in normal play — candidate source for
the older wild-pointer AVs, revisit after the raise-case culprit is caught.
⚠ The DeselectHS-event dialog path has NO detail dialog (Network.dpl
diagnostic only covers the TE "Exception occured during X" reporter), so
probe firings outside TEs print no address — if the culprit turns out to
fire there, extend the diagnostic or make the probe log to memory and read
it with ReadProcessMemory while the game is still open.
**2026-08-13 RE nuggets (from ruling out the lifesteal theory before the
capture):** Goblin Butcher (uid 189) kit = Hero Slaying I, Life Stealing II,
Monster Slaying II, Leadership I, Round Attack, Death Strike — densest
crash-family carrier in the game. Fast combat has its OWN vanilla lifesteal
path: gate @0x55767EDA sets bit 0x02 in [strike+0x18] (only reader
0x55766792 sits in the block cave_lsround's hook SKIPS); CalculateUnitStrikes
region is dual-mode (ctx+0x10/+0x14 = combat objects, +0x20/+0x24 = strategic
TUnits used when objects nil, via TUnit vmt+0x148/+0x114); vanilla reads
[target+0x4C] with NO nil check @0x55767FA6 (post-IsClass). Tactical
cave_lsgen (0x5580E1A0) disasm-verified well-guarded; cave_lsround
(0x5580E160) Execute-side heal does NO revalidation — GetAbilityLevel
(+0xB0) dispatches through [attacker+0x4C]; stale-attacker-after-mid-round-
death exposure is PLAUSIBLE but unproven and deprioritized now GetChild is
confirmed.

**SYMPTOM:** on the campaign's first scenario **Keeper2.csm** a dialog
`Exception occured during TArmyCombatMoveTE` appears; no other tested map does
it. **User confirmed the glitch already existed in 1.37.401**, so it is NOT
caused by the 8/10–8/11 work. Probably the same underlying fault as the earlier
Keeper2 "TurnEventTE" report — same dialog, different TE class
(see [[te-exception-dialog-diagnostic]] for why only the class name is shown).

**MEANING:** `TArmyCombatMoveTE` = an army MOVING INTO COMBAT (it also fires
when an army walks onto an exploration site). Its Execute is `TMoveTE.Execute`
@0x557478BC → Validate(+0x58) → InitializeMove(+0x5C) → ProcessMove(+0x54) /
Move(+0x68) / LastMove(+0x6C) / FinishMove(+0x60), with SetupCombat 0x55748D18,
ExecuteCombat 0x55749924, CombatExecuted 0x557496D4. Exception is swallowed and
the TE is dropped ⇒ the move/combat result is lost, play limps on.

## ✅ RULED OUT (do not redo)
- **Not a 401→402 regression.** Full binary diff done; the 402 deltas on this
  path are only the movedraw NOP (`TMoveTE.Execute+0x31`) and the
  `TMoveArmyTE.MoveVisible` hook, both post-dating the bug.
- **Map content is stock.** Keeper2.csm is byte-identical in 401, 402 and live
  (a 2021 file) — md5 eb48b50ab47ae1ead93179263a16b219.
- **"Ability bit with no data node" is NOT Keeper2-specific.** Keeper2 has ~350
  such units (Leadership ×160+, Parry, Charge, Archery, Lifestealing, Healing,
  DispelMagic; incl. `TLeader@0xbf58f` Lifestealing) — but **After the Fall,
  which plays fine, has the same condition**. So presence alone is not the
  trigger. (Scanner: scratchpad `scan_ml_bits.py`.)
- **Enchantment data is clean** in both maps (`scan_ench.py`) — the
  RegisterEnchantments nil-deref documented in [[te-exception-dialog-diagnostic]]
  is latent here, not this bug.
- **Mod code on the path is sound.** Only 6 mod-modified byte ranges are
  reachable (depth ≤4) from the TE roots; the two hooks that matter were
  disassembled and verified correct: `TCombat.Create` → cave 0x5580DCE8 (clears
  3 per-combat AI-spell BSS flags @0x558FAF20-22, replays the 5-byte prologue,
  preserves eax/edx/ecx) and `TEventLogbook.AddEvent+0xd` → cave 0x5580F600
  (hero level-up event location fix; stack + eax balanced on all 3 exits).
- **`TExplorationSite.Search` baseline patch is safe** — the mod's
  `xor eax,eax; nop; nop` @0x557C1EA0 (replacing `cmp [eax+8],1`, forcing the
  combat-type dialog) clobbers eax, but the branch target 0x557C1EB6 reloads
  eax immediately. ⚠ live bytes are `31 C0 90 90`, not the `33 C0` in older notes.
- **`TCustomAbilityList.GetAbSet` @0x5574E0E0 is bounds-checked** (`cmp edx,
  [eax+0xc]; jae → 0`), so Keeper2's small stored AbCounts (112/118/119/121/122
  vs a ~171-ability registry) cannot read out of bounds.
- **`TAbilityControl.GetAbility` asserts only on a NEGATIVE id**; id ≥ count
  returns nil.

## ★★ ROOT CAUSE LOCATED 2026-08-12 (user reproduced on TURN 2; live capture)
The diagnostic dialog read:
`Access violation at address 0122294F in module 'AoWEPACK.dll'. Read of address 0000003D`
AoWEPACK loaded at **0x011A0000** that run ⇒ RVA 0x8294F ⇒ **static VA 0x5578294F
= `AoWE.TUnit.GetRank+0x3`, `mov dl, byte ptr [eax+0x3c]`.**
⚠ Read address 0x3D = eax+0x3C ⇒ **eax = 1, NOT nil** — something calls
`TUnit.GetRank` with the integer **1** as Self. (1 is a plausible *rank* value,
so the prime suspicion is a caller that clobbers/reuses EAX after a GetRank and
then passes the RANK where the UNIT belongs.)
- The faulting instruction exists **identically in vanilla**, so the deref is not
  the mod's doing — but note the mod fully rewrote GetRank (`patch_rank_unsigned_v1`):
  vanilla computed rank from `[unit+0x40]→[res+0x2F]` and returned a full EAX;
  **the mod version sets only AL** (`mov al,0/1/2` from XP thresholds 10/20),
  leaving EAX's upper 24 bits untouched. Any caller relying on a full-EAX result
  is a candidate.
- The call must be **direct** (E8): a virtual dispatch on Self=1 would have
  faulted earlier at `mov edx,[eax]` reading address 00000001.
- 19 direct callers; the thin TUnit stat getters (`GetAttack`/`GetDefense`/
  `GetDamage`/`GetResistance`/`GetInherent*`, all `+0x5`) forward Self straight
  through, so the culprit may be one level further up.
- Mod caves that call GetRank were cleared: 0x5580F010 (nil-guards + does a
  vtable call on the object first) and the SetExperience cave 0x5580FF20
  (`0x5580FF2F`/`0x5580FF3B`) — both load EAX correctly.

**`'Combat already created'` (2nd error the user saw) is FALLOUT, not a 2nd bug.**
`Exception.Create('Combat already created')` @0x55778798 in
`TAoWHSMap.CreateCombat+0x85` (string @0x557787BC). Sequence: combat object is
created → the GetRank AV aborts the TE → ExecuteTokenEvent swallows it and marks
the event done, so the half-built combat is never torn down → the next combat
attempt trips CreateCombat's guard.

## ★★★ SOLVED 2026-08-12 — DAMAGE TO A COMBAT **WALL** CRASHES COMBAT
Probe #2 reported `Read of address D580F08F` ⇒ caller return = **0x5580F08F**,
i.e. the `call TUnit.GetRank` at **0x5580F08A** inside the mod's damage cave
**@0x5580F060** (hooked over the `call [edx+0xA0]` GetLevel in
`TCombatObject.DoDamage` @0x55726B7F and `TDamageEffectCA.Execute` @0x5572A00C).
The cave does `mov ebx,[esi+0x4c]` and, after only a **nil** check, calls
`TUnit.GetRank(ebx)`.
**`[obj+0x4C]` is the underlying TUnit only for `TCombatUnit`** (written by
`TCombatUnit.SetUnit`; read by GetHits/GetHitPoints/GetAbilityOwner/GetMoves…).
The hook is on the **base class** `TCombatObject`, whose tree is
`TCombatObject → TCombatUnit → TFastCombatUnit`, **plus sibling `TCombatWall`**.
On a wall +0x4C is a packed BYTE pair, not a pointer:
`TCombatWall.GetHits @0x55725C30 = cmp byte [eax+0x4c],2` (wall type) and
`GetHitPoints @0x55725C3C = mov al,byte [eax+0x4d]` (wall HP) ⇒ the dword read
comes back tiny (**observed 1**), survives the nil check, and is used as Self.
⇒ **ANY damage dealt to a city/fort wall access-violates.** That is why it looked
map-specific: it needs a fight where a wall takes damage (Keeper2 = first campaign
scenario, turn 2), not anything about Keeper2's stored data. Nothing to do with
the ability-data/enchantment theories.
The 16 NOPs at 0x5580F077 (present in 72 `AoWEPACK.dll.bak_*`, hence pre-401)
are where a validity test `mov edx,[eax]; call [edx+0x114]; test al,al; je skip`
used to sit — dropped during the victim-XP / no-halving work. ⚠ Restoring THAT
would not have helped: it dereferences the same bogus pointer one instruction
earlier.

## ✅ FIX — `patch scripts/build_wall_damage_rank_crash_fix.py`
**APPLIED 2026-08-12, awaiting the user's Keeper2 turn-2 retest.** Verified:
disassembles as designed, GetRank probe fully reverted, exactly **37 bytes**
differ from `AoWEPACK.dll.bak_wallrank` spanning only 0x5580F077-0x55810E9B,
game launches clean.
Backup `AoWEPACK.dll.bak_wallrank`; `--apply`/`--revert`. Fills the 16 spare NOP
bytes with a real type check (`push eax; mov eax,esi; call cave; test al,al;
pop eax; je 0x5580F09E`) — POP does not touch flags, and 0x5580F09E is the
routine's existing "no bonus" exit (`pop ebx; ret`) returning the plain GetLevel
result = vanilla behaviour for walls. Cave **@0x55810E80** (28 B, PIC:
call/pop delta then `lea edx,[delta+0x55715A94]` = runtime TCombatUnit VMT as the
class operand for `@IsClass` thunk 0x557010C0). `@IsClass` matches descendants, so
TFastCombatUnit keeps the bonus. Script asserts the surrounding bytes
(`8b5e4c85db7427` @0x5580F070) so it refuses to run on a different build.
⚠ Run `build_getrank_caller_probe.py --revert` first — same cave.
**Next free AoWEPACK cave after the fix: 0x55810EA0.**

## ▶ CRASH #2 (2026-08-12, AFTER the wall fix — the crash MOVED, so the wall fix works)
`Access violation at address 01260C93 in module 'AoWEPACK.dll'. Read of address 9EED7398`
AoWEPACK base 0x01150000 that run ⇒ static **0x55810C93** = `mov eax,[edi+0x10]`
at the top of the **multilevel-ability-heal cave** (0x55810C80) — i.e.
`TAbilityOwner.GetAbilityData` walking the data chain. edi = Self = **0x9EED7388**,
which is **> 0x80000000 ⇒ not a heap pointer at all** (garbage, not nil).
⚠ The heal cave is only the messenger: vanilla GetAbilityData @0x5574F1C4 does
`mov ebx,[eax+0x10]` just as eagerly. A CALLER hands it a bogus owner.
Prime suspicion = the same class-confusion family as the wall bug (0x9EED7388 is
consistent with a TCombatWall's packed +0x4C..+0x4F bytes). Mod caves still doing
a raw `[reg+0x4C]` read: **0x5580CE0F, 0x5580D98F, 0x5580E435, 0x5580E576,
0x5580E97B** (0x5580F010 is dead code — nothing references 0x5580F000-0x5580F05F;
0x5580F070 is the one already fixed).
⚠ Note the mod caves that call GetAbilityData are only **nil**-checked, so a
garbage non-nil owner sails straight through them.
Cleared as safe for walls: the weakness helper @0x5580FA00 (probes 8 ids through
vcall `[obj+0xA8]`; on a wall that resolves to `TCombatObject.GetAbilityEnabled`
@0x557268D4 = `xor eax,eax; ret`) and the two damage-role caves 0x5580FB00 /
0x5580FB80 that use it.

## ▶ CRASH #3 (2026-08-12, probe #3 applied but did NOT fire — different fault)
Dialog #2 read simply **`Index out of bounds`** — a *raised* Delphi exception,
not an AV, so probe #3 never triggered (owner was fine that run).
String lives only in **HSEPack.dpl** ×4 @ VA 0x55606EB8 / 0x55606EFC /
0x55606F60 / 0x55606FB0 (⚠ HSEPack VA = file + 0x55600C00 — do not add 0x1000).
Raisers = `HSEngine.TMapField.GetChild` @0x55606E88, `.SetChild` @0x55606ECC,
`.GetHN`, `.SetHN`; all guard `cmp edx,[obj+0x0D]` (child-count byte) then
`Exception.Create('Index out of bounds')` + `@RaiseExcept`. GetChild is virtual
(TMapField VMT+0x4C), so callers are not statically xref-able.
⚠ **KEY TOOLING GAP:** the Network.dpl diagnostic prints only `E.Message`, which
for a *raised* exception carries **no address**. Fix = rebuild that cave around
`SysUtils.ExceptionErrorMessage` (IAT delta **−0x2BC** from Exception.Create;
eax=ExceptObject, edx=ExceptAddr, ecx=Buffer, Size pushed, returns len in eax) —
it formats "Exception <class> in module <mod> at <addr>. <msg>" for EVERY
exception type. Build a ShortString by writing the returned length in the byte
before the buffer, then @LStrFromString → ShowMessage → @LStrClr.

## 📦 RELEASED as 1.37.403 (2026-08-12) — `upload/AoWx_1_37_403.zip` (197.8 MB, 657 files)
Diagnostic reverted (Network.dpl back to `.bak_texcdetail`), in-game version
bumped 402→403 via **`patch scripts/patch_version_403.py`** (file 0x9701B,
backup `.bak_version402`), changelog entry prepended to
X/Documentation/changelogs.txt, manual rebuilt (version+date strings are
hardcoded near the end of `build_manual_from_game.py` — edit them each release).
Also refreshed `upload/.AoWx Manual.html` + `.AoWx Manual.zip` (entry `index.html`).
★ RELEASE-PACKAGING NOTES (no build script exists — the zip is hand-made):
- Rebuild by taking the PREVIOUS zip's namelist and re-reading each path from
  disk (scratchpad recipe); 402→403 parity was exact apart from intended deltas.
- **`X/Documentation/changelogs.txt` is NOT shipped** — players get the changelog
  through the manual HTML, which bakes it in at build time.
- **`Network.dpl` is NOT shipped** (unmodified vanilla file) — which is why the
  diagnostic there could never have reached players.
- 3 maps are named with `_` on disk but were `'` in the 402 zip
  (Greed_s Paradise / Igor_s Folly / Oracle_s Eye) — ship the DISK names.
- `Songs/ASHENSTE.IT` was a duplicate the user deleted — dropped from 403.

## ✅✅ FINAL STATE 2026-08-12 — 3 REAL FIXES + 1 SHIPPABLE GUARD
1. `build_wall_damage_rank_crash_fix.py` — wall damage vs TUnit.GetRank (pre-401)
2. `build_ranged_heroslay_wall_fix.py` — ranged Hero-Slaying vs a wall target (pre-401)
3. `build_multilevel_heal_disable.py` — removed the memory-corrupting heal patch
4. `build_abilitydata_owner_guard.py` — **SHIPPABLE** guard: GetAbilityData
   validates Self + the whole [Self+0x10] chain (≤32 nodes: pointer AND vtable
   plausible); healthy data replays the displaced bytes and re-enters the stock
   body @0x5574F1CB (zero behaviour change), bogus returns **nil** — exactly the
   stock "ability not found" result, which every caller already handles.
   Cave 88 B @0x55811000; backup `.bak_abdataguard`. **Next free cave 0x55811060.**
⚠ HONEST LIMITS of #4: it MASKS the wrong-class caller (never identified — after
the wall fixes the chain-validating probe would not fire in ~10 attempts), and an
in-range-but-UNMAPPED pointer can still fault when its vtable is read. It closes
the 4 observed AVs, not every conceivable one.
★ The 4 observed AVs, all one bug wearing different junk:
  0x5574F1C8 owner 0x9EEB2048 · 0x55810C93 owner 0x9EED7388 ·
  0x55810C9B node 0xFFFFFFFF · 0x5574F1D8 node vtable 0x1400
**BEFORE RELEASE:** revert ONLY the diagnostic
`build_te_exception_detail.py --revert` (Network.dpl). Keep 1-4.
⚠ `upload/AoWx_1_37_402.zip` (Aug 11) contains the BAD heal patch and none of
these fixes — do not ship it; re-cut after the revert.

## ⚠ SUPERSEDED (2026-08-12): "user played to TURN 5 TWICE with NO ERRORS"
— I called it fixed on that evidence and was WRONG; the bug is intermittent, so
clean runs are weak evidence. It crashed again afterwards (node vtable 0x1400).
★ LESSON: for an intermittent fault, do not declare victory on a handful of
clean runs — state it as "not reproduced yet" until the mechanism is understood
or a guard makes it structurally impossible.
(previously the crash hit reliably ~turn 2 every run). The clean runs are with
the standalone GetAbilityData probe armed — and the probe prevents nothing, it
only labels bad calls — so they are genuinely clean. Considered FIXED by:
wall/GetRank fix + ranged Hero-Slaying fix + mlheal removal.
⚠ REMAINING LOOSE END: the last pre-fix crash (wild owner 0x9EEB2048 reaching
STOCK GetAbilityData, caller unknown) is unexplained — nondeterministic path or
residue of the mlheal build. The probe stays armed to name it if it recurs
(dialog shows '... at 8XXXXXXX'; caller VA = value & 0x7FFFFFFF).
**BEFORE ANY RELEASE:** `build_abilitydata_caller_probe.py --revert` +
`build_te_exception_detail.py --revert` (diagnostics). KEEP the two wall fixes
and the mlheal disable (never rerun build_multilevel_ability_heal.py).
Changelog-worthy: both wall bugs are pre-401 and hit EVERY siege with wall
damage, not just Keeper2.

## ★★ BUILD STATE AT THAT POINT (2026-08-12 — superseded by OUTCOME above; the
probe was re-applied standalone afterwards, see CRASH #6 section)
Live AoWEPACK.dll differs from `AoWEPACK.dll.bak_wallrank` by **140 bytes**, all
accounted for:
- `0x5574F1C4` (7 B) — **GetAbilityData restored to STOCK** (mlheal + probe both
  removed, via `build_multilevel_heal_disable.py`; backup `.bak_mlhealoff`)
- `0x5580F077` + cave `0x55810E80` — wall/GetRank fix ✅
- `0x5580E576` + cave `0x55810F00` — ranged Hero-Slaying wall fix ✅
- `0x55810EA0-0x55810EE3` — orphaned probe cave (unreferenced, harmless)
Network.dpl still carries the **v2 diagnostic** (revert before shipping).
Game smoke-tests clean. **Next free AoWEPACK cave: 0x55810F30.**

## ▶▶ CRASH #6 — TURN 18, DETERMINISTIC REPRO (2026-08-12 evening, IN PROGRESS)
User hit `TArmyCombatMoveTE` again on **turn 18** of Keeper2 after long clean
play — and **loading the turn-18 autosave reproduces it EVERY time**. Repro
preserved as `X\Save\autosave - Copy.acg` (⚠ campaign saves are **.acg**, not
.asg; `X\Save\autosave.acg` gets overwritten by play). Detail dialog captured
live (TMessageForm/grabwin recipe):
`Exception EAccessViolation in module VCL30.dpl at 00003A18` /
`read of address 00001902` ⇒ **System.@IsClass @0x41303A18 `mov eax,[eax]`** —
some AoWEPACK caller passes garbage object ptr **0x1902** to `@IsClass`
(nil-safe but not garbage-safe). Same wrong-class family, surfacing through a
type test — so the GetAbilityData guard could never catch it. Note both wall
fixes call @IsClass helpers ⇒ own fixes are among the suspects.
★ CORRECTION: **Network.dpl is NOT in the release zip** ⇒ the
`build_te_exception_detail.py` diagnostic can stay applied PERMANENTLY (never
needs the pre-release revert previously prescribed).
**Probe history (two hard lessons):**
1. v1 detoured `@IsClass` entry in VCL30 → **runtime 216 at startup**: its own
   loop back-edge `jne 0x41303A18` @0x41303A23 lands INSIDE the displaced
   bytes. ★ LESSON: .reloc scan is not enough — also scan for **branch targets
   inside the displacement range**. Reverted.
2. v2 hooked AoWEPACK's private `@IsClass` import thunk **0x557010C0**
   (`jmp [0x558FB6BC]`) but the cave tail-jumped through ECX on the false
   belief @IsClass clobbers it → **@IsClass touches ONLY EAX/EDX**, so every
   call site with a live ECX was corrupted: "CloseHSM" errors + runtime 217 on
   ANY map load. Menu-only smoke test missed it. Reverted
   (`AoWEPACK.dll.bak_isclsprobe` = clean pre-probe state with all fixes).
3. v3 fixed ECX (pass path: `push ecx` → PIC IAT lookup in ecx →
   `mov ecx,[ecx]` → `xchg ecx,[esp]` → `ret`, regs+stack fully intact) — but
   **STILL broke map load identically**. Real killer (both v2 AND v3): the
   stock thunk's absolute operand has a **type-3 .reloc at 0x557010C2**
   (entry @file 0x272638) sitting inside the written E9 rel32; AoWEPACK always
   rebases, so the loader added the delta into the rel32 → jmp into garbage.
   ★ LESSON: the patching-over-relocs rule applies to **IMPORT THUNKS** too,
   and a menu-only smoke test misses it (@IsClass first fires on map load).
4. **v4 APPLIED & VERIFIED**: v3 cave + reloc entry neutralized (type 3→0) on
   apply; verified by SIMULATING the loader (applied all 63,882 relocs with a
   real observed delta — thunk bytes unchanged). Cave **69 B @0x55811060**
   (occupies the "next free" slot while armed; limit 0x55811100). Bogus =
   non-nil outside 0x10000..0x7F000000 → deliberate fault on
   `staticVA(retaddr)|0x80000000`. Launch smoke test clean.
   `build_isclass_caller_probe.py --apply/--revert` (revert = full-file restore
   from `.bak_isclsprobe`, relocs included).
**★★★ PROBE FIRED & CULPRIT FIXED (2026-08-12 late):** dialog read
`... at 001110A2 ... Read of address D580E441` ⇒ caller ret addr **0x5580E441**
= the `call @IsClass` @0x5580E43C in the **MELEE Hero-Slaying cave**
(0x5580E415 body): `mov eax,[edi+0x4c]; test; je; call @IsClass(->THero)` —
raw +0x4C read on the TARGET combat object, nil-check only, so a wall's packed
bytes (0x1902) reached @IsClass as Self. **Exact twin of ranged fix #2; the
combat-object audit wrongly CLEARED 0x5580E435 because it "does IsClass" — the
IsClass ARGUMENT was already the garbage.**
✅ **FIX #5 = `patch scripts/build_melee_heroslay_wall_fix.py`** (APPLIED;
**USER-CONFIRMED 2026-08-12: the turn-18 autosave — previously crashing 100%
of loads — now loads and plays fine.** Strong evidence since the repro was
deterministic, unlike the earlier intermittent ones.
Backup `.bak_meleeheroslay`): 7 bytes in-place @0x5580E435 →
`mov eax,edi; call 0x55810F00` (REUSES the ranged fix's TCombatUnit-check
helper — preserves EDX/THero; nil result flows into nil-safe @IsClass → AL=0 →
existing `je` = vanilla no-bonus path). No new cave. Pre-verified: no relocs,
no branch targets in the 7 displaced bytes; disasm + launch clean.
⇒ SHIPPED: **`upload/AoWx_1_37_403.zip` REBUILT 2026-08-12 ~11 PM** with fix
#5 (same 658-entry namelist re-read from disk; deltas vs the 8:48 PM cut =
AoWEPACK.dll + user's own 10:35/10:40 PM edits to challenge1/2.csm; changelog
+ manual untouched by user request; pre-rebuild copy in session scratchpad).
**Probe was REVERTED for the release** — ⚠ its `--revert` is a full-file
restore predating fix #5, so the required order (followed) is: probe revert →
delete stale `.bak_meleeheroslay` (it contained the probe) → re-apply fix #5
(fresh clean backup). Verified after: all 4 fixes + guard present, thunk
`ff25bcb68f55` restored, probe cave zeroed, **thunk reloc entry back to
type 3**, launch clean. Re-arm the probe anytime with
`build_isclass_caller_probe.py --apply` if the dialog family ever returns.
Live-capture rerun notes: dialogs captured via ctypes EnumWindows/ANSI +
grabwin + PostMessage BM_CLICK — PowerShell-in-bash escaping mangles `$o=0u`,
use Python ctypes directly.

## ★★ TWIN SITE FOUND & FIXED (2026-08-12, prompted by user's Monster Slaying question)
**Monster Slaying (attacker 0x70 / target marker 0x3F) is WALL-SAFE** — both
vanilla melee blocks check it via the virtual GetAbilityEnabled `[vmt+0xA8]`,
which TCombatWall answers `xor eax,eax; ret`. Hero Slaying alone needed the
class lookup (heroes have no ability bit) — that raw `[obj+0x4C]`+IsClass is
the whole defect family. But the question triggered a fresh systematic scan
(all `call @IsClass` E8s + all `8B mod01 4C` reads in caves 0x5580C000-
0x55812000) which found the **melee Hero-Slaying insert exists in BOTH vanilla
strike blocks**: the fixed 0x5580E435 (CalculateStrikes) **and an identical
unfixed twin @0x5580E3D5 (CreateStrikeCA block, target in ESI)** — missed by
the earlier audit. Fixed the same way (7 B → `mov eax,esi; call 0x55810F00`);
`build_melee_heroslay_wall_fix.py` now patches BOTH sites (idempotent
per-site, single clean `.bak_meleeheroslay`). **Zip re-cut again with it
(sole delta vs previous cut).**
Scan also cleared: lifesteal cave (IsClass BEFORE the +0x4C read — canonical
correct order), WallCrushing feature stubs 0x5580EEB0/0x5580EED0 (attacker-
side, helper 0x5580EBC0 nil-checks, and GetAbilityData is guard-protected),
0x5580EED8 = interior label not an entry. ★ LESSON: when a defect is found in
a hook, grep for its SIBLINGS — the mod inserted the same code into every
vanilla block that needed the feature, and the audit only cleared the copies
it happened to walk.

## ★ CRASH #5 = SELF-INFLICTED (the mlheal patch) — see [[multilevel-ability-heal]]
`Exception EAccessViolation in module AoWEPACK.dll at **00110CB6**` /
`read of address 0C0A004C` ⇒ static **0x55810CB6** = the heal cave's MISS path
`mov ecx,[eax]; call [ecx+0x4c]` with a bogus VMT 0x0C0A0000.
**Vanilla GetAbilityData never dereferences the owner's VMT** (proved against
`AoWEPACK.dll.bak_mlheal`): it reads `[owner+0x10]`, walks nodes, returns nil on
a miss. The cave added a virtual call on the OWNER, plus a heal branch that
**writes** `[owner+0x10]` and adopts the junk there as `next` — corrupting
wrong-class objects and manufacturing garbage chains. That plausibly *caused*
crashes #2 (wild owner) and #4 (chain = 0xFFFFFFFF) on later calls.
⇒ **DISABLED.** ★ LESSON: re-implementing an engine function in a cave must not
add dereferences or writes the original never made — vanilla's tolerance of junk
arguments is load-bearing.

## ▶ CRASH #4 (2026-08-12, after both wall fixes — v2 diagnostic's first catch)
`Exception EAccessViolation in module AoWEPACK.dll at **00110C9B**.` /
`Access violation at address 01300C9B ... Read of address **FFFFFFFF**`
⇒ static VA = 0x55700000 + 0x110C9B = **0x55810C9B** = `mov edx,[eax]` in the
heal cave's chain walk, with **eax = 0xFFFFFFFF**.
★ Note how much better v2 is: the module-relative offset is printed directly, so
no live module-base lookup is needed.
Unlike crash #2 the OWNER was a valid pointer (we got past `[edi+0x10]`); it is
the **chain field that is -1**, i.e. the object passed to GetAbilityData is *not
a TAbilityOwner* — junk at +0x10. Same family: something is passing the wrong
class as an ability owner.
⚠ 0x55810C9B sits **inside the walk loop** (0x55810C96 ← 0x55810CA8), so the bad
pointer may be the head `[owner+0x10]` OR a later `[node+8]`.
Cleared: the virtual route is safe — `GetAbilityOwner` is VMT slot **+0xB8**, and
on TCombatWall it resolves to `TCombatObject.GetAbilityOwner` @0x557268D0 =
`xor eax,eax; ret` (nil). So the culprit reads a field directly instead of
calling the virtual.
**Probe #3 extended (68 B, dry-run OK, NOT yet applied — game was running):** now
also checks the chain head is nil-or-plausible before entering the heal cave, so
this exact case reports the caller. ECX is safe to clobber (Delphi scratch; the
heal cave never reads it).

## ★ FULL COMBAT-OBJECT AUDIT (2026-08-12, user-requested) — the defect family
**Defect:** mod code reads `[obj+0x4C]` (the underlying TUnit) on something that
is not a `TCombatUnit`. Tree: `TCombatObject → TCombatUnit → TFastCombatUnit`,
**+ sibling `TCombatWall`** where +0x4C/+0x4D are packed BYTES (type / hit
points). Method: diff live vs vanilla → every hook site → disassemble each cave
**from its hook entry** (linear sweeps desync and miss/​invent instructions —
scratchpad `audit2.py`), then flag `[reg+0x4C]` reads lacking an `@IsClass`.
**78 live cave entries; only 3 mod hooks sit in `TCombatObject` BASE methods**
(the only ones a wall traverses):
- `DoDamage+0x4a` → cave 0x5580F060 — **the wall/GetRank bug, FIXED**
- `ExecuteDamageRole+0x4a` → 0x5580FB00 and `ExecuteDamageRoleEx+0x63` → 0x5580FB80
  — **safe**: they only use virtual calls (`[obj+0x80]`, and the weakness helper
  @0x5580FA00 which probes 8 ids via `[obj+0xA8]`; on a wall that resolves to
  `TCombatObject.GetAbilityEnabled` @0x557268D4 = `xor eax,eax; ret`).
Live `[+0x4C]` reads: 0x5580E1D6 (lifesteal cave) **IsClass-guarded ✓**;
0x5580F070 **fixed**; **0x5580E576 UNGUARDED → fixed (see below)**.
⚠ **Two caves are DEAD CODE** — nothing references them, so they are red
herrings: **0x5580F000-0x5580F041** (older copy of the damage routine, still has
the `[edx+0x114]` test) and **0x5580E96F-…** (older Healing copy; the live one is
0x5580E9B0 via `THealingAbility.HealUnit`). Verify with an unaligned search for
refs before blaming a cave.

## ✅ FIX #2 — `patch scripts/build_ranged_heroslay_wall_fix.py` (APPLIED)
Ranged **Hero Slaying** (0x38) in cave 0x5580E500 (hook
`TRangedAttackAbility.CreateRangedAttackCA+0x50`) did
`mov eax,[ebp-4]` (the TARGET combat object) → `mov eax,[eax+0x4c]` → nil-check →
`@IsClass(...,THero)`. On a wall +0x4C reads as a small int (e.g. 1) which is
non-nil, so `@IsClass` dereferenced it ⇒ **a Hero-Slaying unit shooting a wall
crashed**. Replaced those 10 bytes with `mov eax,[ebp-4]; call helper; je skip`;
helper @**0x55810F00** (46 B) returns the TUnit only if the object IsClass
TCombatUnit, else nil, and sets ZF for the caller's `je`.
⚠ **EDX must be preserved** — the caller loaded the THero class into it two
instructions earlier and uses it for the following `@IsClass`; the helper
save/restores it. Backup `AoWEPACK.dll.bak_rangedheroslay`.
**Next free AoWEPACK cave: 0x55810F30.**

## ✅ DIAGNOSTIC v2 (applied) — addresses for RAISED exceptions too
`build_te_exception_detail.py` rewritten around **SysUtils.ExceptionErrorMessage**
(IAT delta −0x2BC; `eax=ExceptObject, edx=ExceptAddr, ecx=Buffer, Size pushed`,
returns len in eax, **`ret 4`** = callee cleans — all verified). Cave v2 147 B.
Now prints `Exception <class> in module <mod> at <offset>. <msg>` for EVERY
exception type ⇒ **static VA = 0x55700000 + offset**, no module-base lookup.
⚠ **GOTCHA HIT:** `push 250` as `6A FA` is `push imm8` **sign-extended to −6** —
must use `68 imm32`. Caught by disassembling the built cave; always re-read it.

## ⚠ SUSPECTED SOURCE OF CRASH #2 (NOT confirmed — the audit CLEARED this)
**0x5580E97B** `mov eax,[eax+0x4c]` in the Healing cave @0x5580E970: it nil-checks
the combat object at `[ebp-4]` but does **no class check** before reading +0x4C and
passing it to **0x5580E6E0** (= Healing-level lookup: `mov edx,0x2F` →
`GetAbilityData`). A non-TCombatUnit there yields garbage exactly like the wall bug.
Contrast the Hero-Slaying caves 0x5580E435 / 0x5580E576, which DO `IsClass` (vs
THero @0x55711FAC) before using +0x4C — so the guard pattern is already
established in this codebase.
Cleared: 0x5580CE0F / 0x5580D98F (`[esi+0x4c]→[+0x40]` face-resource lookups) and
the WallCrushing GetLevel cave 0x5580EC00 (nil-checks the owner AND vcalls
`[owner+0x4C]` GetAbSet first, so a garbage owner would fault there, not inside
GetAbilityData — hence not crash #2's path).

## ▶ PROBE #3 — `patch scripts/build_abilitydata_caller_probe.py` (APPLIED; did not fire)
Re-points the existing GetAbilityData hook 0x5574F1C4 `jmp 0x55810C80` →
`jmp 0x55810EA0`; the probe range-checks Self (0x10000..0x7F000000) and on a
bogus value faults on `staticVA(retaddr)|0x80000000`, else falls through to the
heal cave. Cave 45 B @0x55810EA0. Same decode: `value & 0x7FFFFFFF`.

## ▶ PROBE #2 (diagnostic, revert before shipping) — `patch scripts/build_getrank_caller_probe.py`
Backup `AoWEPACK.dll.bak_rankprobe`; hook = 6 B at GetRank 0x5578294C → cave
**0x55810E80** (44 B; next free AoWEPACK cave now **0x55810F00**), resumes at
0x55782952. If Self < 0x10000 it deliberately faults on
`staticVA(returnAddress) | 0x80000000`, so the dialog prints
`Read of address 8XXXXXXX` where **value & 0x7FFFFFFF = the static VA right after
the offending `call TUnit.GetRank`** (already rebase-corrected in-cave, so no
module-base lookup needed). Normal path costs one cmp+jb.

## LIVE-CAPTURE RECIPE (worked well; reuse it)
Game frozen on the modal dialog ⇒ enumerate windows with **ANSI** `GetClassNameA`/
`GetWindowTextA` (the W variants return every-other-char garbage on these Delphi
ANSI windows). The dialog is class **`TMessageForm`**; its message is painted by a
TLabel (a TGraphicControl = **not** a child window), so `GetWindowText` cannot
read it — **screenshot it** with `re_tools/grabwin.py <hwnd-hex> out.png` and read
the image. To advance to the next dialog, **PostMessage** BM_CLICK (0x00F5) to the
`TButton` child — never SendMessage, which deadlocks against the nested modal loop.
Module bases for a 32-bit target from 64-bit Python: CreateToolhelp32Snapshot with
`TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32` (PowerShell `$p.Modules` returns nothing).
⚠ Patching AoWEPACK.dll fails with PermissionError while the game runs (the backup
is still written first, so the DLL stays intact — just re-run after closing).

## ▶ EARLIER STEP (done, still applied)
`patch scripts/build_te_exception_detail.py` is **APPLIED** to Network.dpl — it
adds a second dialog carrying the exception's own Message. One reproduction now
yields either `Access violation at address XXXXXXXX in module 'YYY'…` or an
Assert's `msg (file, line)`. Prime named assert suspects on this path (full list
in [[te-exception-dialog-diagnostic]]): **'Army already activated'**
(TArmy.Activate), **'CombatObject Position/ID double defined'**
(TCombatData.AddObject), **'Combat already activated'**, and the six MoveT.PAS
`TMoveControl` asserts. ⚠ `--revert` before packaging a release.


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- 📦 [keeper2-armycombatmovete-crash.md](keeper2-armycombatmovete-crash.md) — **8/14: vichan's Delgates-capture crash (his machine only) → diagnostic kit sent (`share to discord/AoWx_diagnostic_kit_delgates.zip` = probed HSEPack + detail Network.dpl), awaiting screenshots; GetChild RE: all calls virtual (VMT+0x4C; TMapField 0x55602500→TAoWMapField 0x5570C764/TAoWCombatMapField 0x411C8C), GetChild(0) on empty hex raises. MP LogbookChanged one-off triaged (ListEvents/GetText path, not GetChild), parked. 1.37.404 RELEASED 8/13; **1.37.405 CUT 8/15 (`upload/AoWx_1_37_405.zip`, 658 files; changed vs 404: manual + AoWEPACK.dll + AoWTCPCK.dll + Tribute To The Fall.hsm) — ships damage response, retaliation, courage, AoO v5; manual changelog JSON is in `.AoWx Manual.html` `"changelog": [` (json.dumps-compatible format, .ind4 CSS added), version badge + lastupdated fields nearby.** Root cause of the 8/13 crashes: leveled-Healing's combat executor passed a raw `[obj+0x4C]` as ability owner (recorder named it) — fixed; **plus 5 July-era patches left ACTIVE relocs under their NOPs = base-dependent junk instructions, the mechanism behind "crashes on his machine, not mine, identical files"** — neutralized. Life Stealing had the same unguarded `GetAbilityLevel` (+0xB0 is NOT nil-safe; +0xA8 is) — guarded. ⚠ **HSEPack.dpl SHIPS — revert `build_getchild_caller_probe.py` before any cut** (the GetChild index bug itself is still unfixed/unreproduced). New: `build_release_zip.py` automates cutting a release. Keeper2/siege crashes: 3 real fixes shipped in 403 (wall/GetRank, ranged Hero-Slaying vs walls; + **mlheal patch removed** — never rerun it) + shippable GetAbilityData guard. **CRASH #6 (turn 18) SOLVED & USER-CONFIRMED 8/12: melee Hero-Slaying vs wall — same +0x4C defect, audit had wrongly cleared it; FIX #5 `build_melee_heroslay_wall_fix.py` (reuses helper 0x55810F00) fixed the 100%-repro autosave — **and patches a 2nd identical twin site @0x5580E3D5 (CreateStrikeCA block) found via the user's Monster Slaying question; Monster Slaying itself is wall-safe (virtual ability-bit check)**. **403 zip REBUILT with both 8/12 ~11 PM** (+ user's challenge1/2.csm edits). Probe now REVERTED (⚠ probe revert predates fix #5 — order: revert probe → delete stale fix-5 bak → re-apply fix #5; done & verified). Probe lessons: v1→216 branch-into-displaced-bytes; v2→217 thunk reloc 0x557010C2 must be neutralized (+ECX preserve).** ★ Network.dpl detail diagnostic is NOT shipped ⇒ may stay applied permanently. ⚠ Don't ship `upload/AoWx_1_37_402.zip`. Holds the live-capture recipe (TMessageForm/grabwin/PostMessage) + full combat-object audit + the "don't trust a few clean runs on an intermittent bug" lesson.
