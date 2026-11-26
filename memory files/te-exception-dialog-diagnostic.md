---
name: te-exception-dialog-diagnostic
description: "\"Exception occured during <TEclass>\" is raised by NetworkE.TTokenExecuter.ExecuteTokenEvent (Network.dpl) which swallows the real exception; diagnostic patch build_te_exception_detail.py adds a 2nd dialog with the exception's own Message (AV address+module, or Assert msg+file+line). Includes the full AoWEPACK assert inventory. Applied 2026-08-12 while chasing the Keeper2.csm TArmyCombatMoveTE crash."
metadata: 
  node_type: memory
  type: reference
  originSessionId: b6d320bc-2062-4946-bd64-d75f46d799f0
  modified: 2026-08-12T20:22:39.622Z
---

## THE DIALOG'S SOURCE (any "Exception occured during X" report)
`NetworkE.TTokenExecuter.ExecuteTokenEvent` **@0x55803D24 (Network.dpl)**:
```
call [TE_vmt+0x4C]                 ; the TE's Execute
except:  @0x55803D90
  PStrCpy(' Exception occured during ' shortstr @0x55803E14)
  PStrCat(TObject.ClassName(TE))
  LStrFromString -> ShowMessage     ; call @0x55803DD2
  bl=1; @DoneExcept
  inc [executer+0x20]; [executer+0x48]=0
```
⚠ The exception object is **discarded** — the player only ever sees the TE class
name. The TE is then marked done and the token stream advances, so this is a
**swallowed** crash: play continues with that turn event's effects lost (in MP
that is a guaranteed desync). The string `'Exception occured during '` (single
'r', ShortString, len 0x19) lives at file 0x3214 — it is the ONLY such template
in the game, so every report of this shape comes from here.
**Network.dpl:** base 0x55800000, **VA = file + 0x55800C00**; cave = the
all-zero CODE tail **0x55806210..0x55806400 (0x1F0 B, file 0x5610)** — inside
SizeOfRawData so it is mapped+executable. Network.dpl rebases (its preferred
base overlaps AoWEPACK) ⇒ **PIC required**.

## ✅ DIAGNOSTIC PATCH — `patch scripts/build_te_exception_detail.py`
Applied 2026-08-12, backup `Network.dpl.bak_texcdetail`, `--apply`/`--revert`.
Hook = the 5-byte `call Dialogs.ShowMessage` @0x55803DD2 → 55 B cave @0x55806210:
shows the original dialog, then `ShowMessage(E.Message)`.
**⚠ DIAGNOSTIC ONLY — `--revert` before packaging a release.**
Trick worth reusing: **get an un-imported RTL function via a fixed delta from an
imported neighbour in the same module.** Network.dpl imports
`SysUtils.Exception.Create` (IAT 0x55809564); in VCL30
`Exception.Create`=0x4130F444, `ExceptObject`=0x4130F13C, `ExceptAddr`=0x4130F15C,
`ExceptionErrorMessage`=0x4130F188 ⇒ ExceptObject = IAT value − **0x308**
(ExceptAddr −0x2E8, ExceptionErrorMessage −0x2BC). `Exception.FMessage` is at
**+4** (proved by `lea eax,[edi+4]; call @LStrAsg` inside Exception.Create).
ExceptObject returns nil when no exception is active, so the cave nil-guards and
degrades to the stock dialog. Game verified to launch with it applied.
**What the 2nd dialog gives you:** AV → `Access violation at address XXXXXXXX in
module 'YYY', read of address ZZZ` (exact faulting instruction). Delphi Assert →
`<msg> (<file>, line <n>)` — Delphi's SAssertError is `'%s (%s, line %d)'`.

## ASSERTS ARE A REAL EXCEPTION SOURCE (not just AVs)
56 `System.@Assert` (0x55701138) sites in AoWEPACK.dll; convention is
`eax=msg, edx=filename, ecx=line`. Scan for `E8 rel32 → 0x55701138` and read the
three preceding `mov reg,imm32` to recover **message + source file + line**.
Named ones reachable from combat/army/move code:
- Combat.pas — 'target already exists use update target' (AddTarget), 'Invalid
  Damage Value' (ExecuteDamage), 'Combat Finalize Failure', **'Combat already
  activated' (TCombat.Activate)**, 'Combat Failure during Deactivating'
- Combat2.pas — **'CombatObject Position/ID double defined' (TCombatData.AddObject)**
- Army.PAS — **'Army already activated' (TArmy.Activate)**, 'Invalid Unit Index'
  (TArmyHS.Show), TArmyHS.UpdateUnitGFXResource
- MoveT.PAS ×6 — TMoveControl SetupMove('Invalid settings')/Process/
  CalculatePathEx/Activate×2/ProcessMove  ← same source file as the move TEs
- EventLog.pas — `TEventLogbook.AddEvent` asserts `TAoWHSMap.GetSynchronised`
- Ability.PAS — SetAbCount('Invalid AbCount Value'), `TAbilityControl.GetAbility`
  ('Invalid AbilityID') — **only fires on a NEGATIVE id**; id ≥ count returns nil.
- AI.pas ×3, AIGroup.pas ×6, Player.PAS ×5, AoWHSMap.PAS ×6

## ⚠ LATENT ENGINE BUG FOUND (unrelated to Keeper2, not yet triggered)
`TAbstractUnit.RegisterEnchantments` **@0x5577F2F2** (and the twin
`UnregisterEnchantments` @0x5577F377) do:
`GetAbilityData(unit,id)` → **`mov eax,[node+0x10]` with no nil check**.
The only guard is `GetAbilityEnabled` = vcall+0x148 → `TAbility.GetEnabled`
@0x5574EEF4, which is **just the bitset test** (`owner.GetAbSet(id)`), so a unit
whose ability BIT is set without a `TUnitEnchantmentAbilityData` node (classid
**0x202AC**, tag 0x0F = u16 ability id, tag 0x10 = source object) access-violates.
Callers: `Activate` (map load), `Deactivate`, **`Killed`** (so it can fire mid-combat).
Enchantment ability ids: 0x22 TurnedUndead, 0x5E Entangled, 0x5F Frozen,
0x7E CosmeticSurgery, 0x84 Slow, 0x98 Haste, 0x99 StoneSkin, 0x9A EnchantedWeapon,
0x9B Summoned, 0x9C Fury, 0x9D FreeMovement, 0x9E Blessed, 0xA0 HolyChampion,
0xA1 UnholyChampion, 0xA2 Concealment, 0xA3 FireAura, 0xA4 WaterWalking,
0xA5 WindWalking, 0xA6 LiquidForm, 0xA7 FireProtection, 0xA9 DarkGift.
(⚠ the mod's Path of Sand 0x9F sits inside that block.) Scanner:
scratchpad `scan_ench.py`. Keeper2 + After the Fall both scan CLEAN today.
Sibling of [[multilevel-ability-heal]]; a heal for enchantments is NOT covered by
that patch — `TUnitEnchantmentAbility` is **not** a `TMultiLevelAbility` descendant.

## VMT / CLASS-TREE RECIPE (Delphi 3 layout — differs from Delphi 4+!)
self-ptr **−0x40**, className **−0x20**, instanceSize **−0x1C**, parent **−0x18**
(parent is a PPointer → deref twice). Scan `[va-0x40]==va` to enumerate all VMTs
(857 in AoWEPACK). `TMultiLevelAbility` (VMT 0x5571DFD0) descendants = exactly
TTransportAbility, TLeadershipAbility, TSpellCastingAbility, TVisionAbility,
TMarksmanshipAbility. `TUnitEnchantmentAbility` (0x55722364) has 21 descendants.
Related: [[aowx-re-reference]], [[ability-id-map]], [[patching-over-relocs-gotcha]].

**⚠ 2026-09-03 (pre-408 cut):** the patch was found RE-APPLIED to Network.dpl and the
backup `Network.dpl.bak_texcdetail` was POISONED (contained the patched bytes — a
--revert restored the patch itself). Repaired by copying
`reference files/AoW Ziggurat/Network.dpl` (vanilla 1.36 install) over the backup —
verified the live file differs from vanilla ONLY in this patch's hook+cave regions, so
vanilla ref == correct pre-patch state; then --revert → byte-identical to vanilla.
**FACT: Network.dpl is NOT in the release zip at all** (players keep their vanilla
copy), so this diagnostic can never ship via a cut — the "revert before packaging"
rule protects only the user's own install/MP-parity, not the zip.
