---
name: possess-leader-transfer
description: "10/22 READ-ONLY RE + design for moving leader status through Possess and the Incarnate chain (defeat when the chain ends, crown on the party shield); nothing built or applied"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T07:24:49.262Z
---

**User request (10/22, for 422 or later):** when a leader possesses a unit, the possessed unit becomes the "leader". So do later possessions, and the Incarnate it turns into when it dies. When that chain finally dies, the player loses. The overworld party shield keeps the gold leader crown.

**Vanilla mechanics (AoWEPACK, static RE):**
- **Leader = the class TLeader** (classref cell 0x557121F8 → VMT 0x55712238, ClassID 0x20232). [player+0xD4] is the setup TLeader object (ValidateLeader); it is NOT the alive check. Leader status cannot be moved by changing a unit's class (TUnit, THero and TLeader have different layouts).
- **Defeat in combat:** TCombatUnit.DestroyObject 0x557256F0 (+0x82) and TCombatUnit.Surrender 0x557257B8 (+0x32) do `mov eax,[cu+0x4C]; mov edx,[0x557121F8]; call IsClass 0x557010C0`. If true, owner [cu+0x45] is added to the combat defeat list [[combat+0xC]+0x2C], and TCombat.Finalize fires GameOver(p,2) (see [[mp-leader-kill-freeze]]).
- **Defeat outside combat:** TLeader.Killed 0x5578B51C calls GameOver(owner [u+0x24], 2) only if [u+0x25]&2 (active) and [map+0x120]==0 (no combat).
- **Possess** = TPossessCA.Execute 0x557696E0. Fast combat goes through the same CA (TPossessAbility.fcExecuteCombatCommand → CreatePossessCA → TCombat.ExecuteCombatAction).
  - ebp = possessor combat object, edi = target combat object, ebx = possessor STRATEGIC unit (the leader).
  - Steps: target.SetUnit(nil) + DestroyObject. Leader.AddRef, Killed (vmt+0x1AC), SetOwner(0) (vmt+0x08). The possessor's combat object then SetUnit(target strategic unit).
  - Target gets Possessed 0x6B. Its data +0xC = (possessor's 0x6B data+0xC, or possessor GetExperience) + target GetUnitLevel. That value becomes the Incarnate's XP.
  - **Why the player never loses:** the leader's combat object is reused, never destroyed, and Killed runs during combat, so GameOver is skipped.
- **Incarnate:**
  - In combat: TPossessedAbility.CombatObjectDestroyed 0x55769A08 clears the dead status bit, creates TUnit res 0x98 with SetExperience(data+0xC), calls Killed on the old unit, and SetUnit(incarnate). Because the status bit is cleared, DestroyObject skips the defeat block.
  - Overworld: TArmy.Validate 0x5578CF7C (+0x3A..+0x8E): a dead unit with 0x6B → new incarnate (res 0x98), old.Killed, army AddChild (vmt+0xAC).
- **Crown:** TArmyHS.Show 0x557914D8 draws it when [army+0x10]&0x20. TArmy.UpdateConcealment 0x5578C98C sets that bit when TArmy.Leader 0x5578DFBC (first unit with vmt+0x24 ClassID == 0x20232) is non-nil and not concealed. TArmy.Leader is also called by the AI: UpdateAITarget, AIMovePriority.
- **TLeader-only immunities, all via the same IsClass call:**
  - Possess targets: TPossessAbility.CanTouch +0x60 @0x55769C90, CanTouchUnit +0x3A @0x55769CDE.
  - Seduce/Charm/Dominate: TCommandAbility.CreateCommandCA @0x5577037D, fcGetDamageValueEx @0x557702A9.
  - TLeader.CanDisband = 0 (VMT +0x190).
- Other TLeader IsClass users, all left alone: UpdateMoraleValue, THero.NewDay, TMindDecay, TResurrectHero/TAnimateHero, campaign transfer, TUnitList.MainReadWrite, TCombatUnit/TFastCombatUnit.Initialize ([cu+0x5C]=8 AI value).
- **Persistence:**
  - Ability BITS are serialized: TAbilityOwner.ReadWrite 0x5574F318 → TCustomAbilityList.ReadWrite (AbCount + bits); records go via a tag-0x31 id list.
  - Not yet verified that TUnit/THero.ReadWrite reach it. Possessed 0x6B persisting in vanilla saves suggests they do.
  - TPossessedAbilityData has a hard-coded GetAbilityID 0x6B, so cloning a data ability is heavy. Don't.

**Design (MP-safe; game state only: ability bit, class, owner):**
- Marker = new bit-only status ability "Leader's Soul" (custom id, next free about 0xC8/0xC9; verify like the 0xC6 Smoke Screened / 0xC7 Reversed registrations) + an Ability.pfs record. It is never learnable.
- Helper IsLeaderOrVessel(eax=unit): nil→0; IsClass TLeader → 1; else HasAbility vmt+0x148(edx=V). About 40 B.
- **Six rel32 call swaps (IsClass → helper):**
  - DestroyObject 0x5572577B, Surrender 0x557257F0 → the chain's final death = defeat (tactical + auto).
  - Possess CanTouch 0x55769C90 / CanTouchUnit 0x55769CDE → the enemy can't possess our vessel.
  - CreateCommandCA 0x5577037D / fcGetDamageValueEx 0x557702A9 → immune to Seduce/Charm/Dominate like a leader, so the marker can't change sides.
  - Only the call disp32 changes; the preceding `mov edx,[0x557121F8]` reloc is untouched.
- **Grant on possess:** hook TPossessCA.Execute @0x557697E7 (`ba6b000000`, no reloc). If IsLeaderOrVessel(ebx = possessor strategic unit) → set bit V on [ebp+0x4C] (the new body). Re-execute the mov edx,0x6B; jmp 0x557697EC.
- **Inherit on Incarnate:**
  - In combat: hook CombatObjectDestroyed after incarnate creation (edi = new, [esi+0x4C] = old).
  - Overworld: hook TArmy.Validate (ebp = new, esi = old).
  - Both: if old has V → new gets V.
- **Overworld death:** redirect the `call TAbstractUnit.Killed 0x5578087C` sites at TUnit.Killed 0x5578281D and THero.Killed 0x557871F6 to a cave. If unit has V, lacks 0x6B, is active ([u+0x25]&2) and [map+0x120]==0 → GameOver(map, dl=[u+0x24], cl=2), mirroring TLeader.Killed. Then jmp 0x5578087C. Map global via the PIC delta ([[rebase-crash-runtime-error-216]]).
- **Crown + AI:** TArmy.Leader @0x5578DFD8 (`mov eax,[eax]; call [eax+0x24]; cmp eax,0x20232`, 10 B) → call a cave that sets flags as if ClassID==0x20232 when IsLeaderOrVessel. Preserve ebx/esi/edi/ebp.
- **No disband:** TUnit and THero VMT +0x190 → cave: has V → 0, else the original 0x557825B0. VMT dwords carry relocs; in-image values are fine.
- Total about 450 B of code plus registration and a Ability.pfs record. About 12 sites.

**Risks / open:**
- Verify the bit survives save/load (unit ReadWrite chain) and AssignAb/UI copies.
- Resurrect Hero could revive the dead TLeader while a vessel lives (two "leaders") — decide.
- Army Desert (unpaid upkeep mutiny) removes the vessel without Killed? Unchecked; option: make vessel upkeep 0.
- The tactical leader icon (TCUIcon, TCPCK) is not handled; optional.
- The vessel is not a spellcaster (same as today after possession).
- Old saves with an already-possessed leader stay leaderless (no marker).
- Re-run the reloc scan at every site.

**Test plan:**
1. SP: a leader with Possess possesses a unit → crown on that army; save/load → crown and ability still there.
2. That unit dies in tactical combat → Incarnate keeps the marker; the Incarnate dies → defeat. Repeat in autocombat.
3. The vessel possesses again → the marker moves.
4. Overworld death (storm/plague) of a possessed vessel → Incarnate inherits; of the Incarnate → defeat.
5. The enemy tries Possess/Seduce/Charm on the vessel → refused.
6. Disband is greyed out.
7. LAN two machines: all of the above with no OOS.

**Verdict:** feasible, medium effort (about a day of patching + testing). Not too ambitious, because every defeat, crown and immunity path funnels through a handful of TLeader IsClass checks.

**10/22 user rules (build sent to the fork, zone AoWEPACK 0x55836800-0x55837800):**
- Only the owner can resurrect or animate the dead leader. It auto-rejoins the owner with no join offer.
- The soul then returns to the leader: the vessel loses the marker and Possessed. An incarnate vessel just vanishes.
- Soul units are upkeep-free with morale locked High.
- The user thinks possessed heroes with Spellcasting can cast the player's spells. The fork is to verify this.

## 10/22 IMPLEMENTED (scripts written + dry-run OK, NOT applied: the coordinator applies sequentially)
The user approved with these rules:
- Only the owner can resurrect or animate the dead leader. It rejoins directly, never roams, and the soul returns. The marked body loses the marker and Possessed; an Incarnate is removed with no defeat.
- Soul units have no upkeep and their morale is locked High.
- Casting: verify only, don't change.

**`patch scripts\patch_leader_soul_v1.py`** (AoWEPACK zone 0x55836800–0x55837800, 1451 B used; `.bak_leadersoul`; header saves every site + 6 VMT pointers):
- **Marker:** ability 0xCE "Leader's Soul", a plain TAbility (VMT 0x5570F254), [+0x24]=4, [+0x20]=0 so it is never learnable. Registered by chaining 0x557BCF6E (prev decoded at apply = 0x55817480 on 10/22).
- **isl** (IsClass OR has 0xCE) at seven call sites:
  - DestroyObject 0x5572577B, Surrender 0x557257F0
  - Possess CanTouch 0x55769C90, CanTouchUnit 0x55769CDE
  - CreateCommandCA 0x5577037D, fcGetDamageValueEx 0x557702A9
  - UpdateMoraleValue 0x5577F0A5
- **pg** 0x557697E7: grant to the new body, clear from the old one.
- **ic** 0x55769A4C: combat Incarnate inherits. **iv** 0x5578CFF4: overworld Incarnate inherits.
- **kd** at TUnit.Killed 0x5578281D and THero.Killed 0x557871F6: GameOver if the unit holds 0xCE, has no 0x6B, is active, and no combat is running.
- **cr** TArmy.Leader 0x5578DFD8: crown and AI.
- **vc**: TUnit and THero VMT +0x9C upkeep→0, +0x17C morale→0x5A, +0x190 CanDisband→0.
- **Resurrect/Animate Hero:**
  - rf 0x557EC152 / 0x557EC6BA: remember the caster's own dead TLeader ([hero+0x5C] death owner == caster owner) in FOUND.
  - rp 0x557EC1A7 / 0x557EC70F: the pool becomes only FOUND (PICK).
  - oj 0x557EC2CA / 0x557EC832: PICK → TArmy.SetPlayer(army=[hero+0x20], owner), then the soul search over [player+0x28] armies. The first 0xCE unit loses the marker. A Possessed body loses 0x6B (unit VMT+0x98 RemoveAbility, then +0x90 Changed). An Incarnate gets Killed. Returns 0 (vanilla info-log branch).
  - Scratch FOUND/PICK in .idata slack 0x5590B3C0/0x5590B3C4.
- **Vanilla facts:**
  - Resurrect/Animate Hero always exclude TLeaders (IsClass filter) and pick a RANDOM dead hero; OfferToJoin (THero vmt+0x19C) leads to a join offer.
  - Dead flag is [hero+0x55]&1; death owner is [hero+0x5C].
  - THeroList vcalls: +0x54 count, +0x6C remove, +0x70 add.
- **SetAbSet** (owner vmt+0x50, eax/edx=id/cl) is hooked by a mod cave at 0x55810800 that grows the set, so old saves are fine.

**`patch scripts\patch_leader_soul_ability_pfs_v1.py`:** record key 216 (needs 215 present; highest key is 215 now).
- LADDER += 0xCE in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py (edited 10/22).
- Re-run both after the pfs apply → bound 0xCF.

**Apply order:**
1. patch_leader_soul_v1 --apply
2. patch_leader_soul_ability_pfs_v1 --apply
3. banner ceilings --apply
4. tcablist ceiling --apply

LIFO: revert leader_soul before any script that chains 0x557BCF6E.

**Casting verdict (static):**
- Overworld TUnitSpellCaster.CanCast: the selected unit must be alive and have its own casting points (vmt+0x12C), plus player mana. There is NO leader requirement.
- Combat TCombatSpellCaster: requires IsClass THero (TLeader included) + Spellcasting 0x34.
- Casting points: THero = Spellcasting level×10 (mod cave 0x558190D0); TAbstractUnit (units and Incarnates) = 0.
- So a possessed HERO with Spellcasting still casts normally (the user is right). Possessed normal units and Incarnates can't, same as vanilla.
- The dead leader's TLeader.GetPowerGeneration (mana income from its Spellcasting) is lost while it is dead; the vessel doesn't replace it. Reported, not changed.
- Possess CanTouchUnit rejects GetUnitType==0 (THero returns 0) while combat CanTouch doesn't. Whether heroes can actually be possessed is unverified.

## 10/22 v1 BUG → v2 (`patch scripts\patch_leader_soul_v2.py`, dry-run only, NOT applied)
**Symptom:** with v1 applied, the game showed "Runtime error 217 at 000038EE" on exit. The VEH log: invalid-pointer FreeInstance in TAbility.Destroy+0xE (freeing the TStringList at [+0x10]) ← TAbilityControl.UnregisterAbility.

**Root cause:** v1's reg cave did `mov byte ptr [eax+0x24],4`, copied from Possessed/Reversed. But a plain TAbility instance is only **36 bytes** (VMT-28 instsize; TAdjustableAbility is 40, TDurationAbility 44). The write corrupted the next heap block's header, which is the ability's own TStringList.

**Fix (v2):** drop that write. TAbility.GetAbilityType returns 0 anyway, and [+0x24] belongs to TAdjustableAbility.
- reg is the last cave, so every other cave address is identical.
- v2 `--apply` upgrades a v1 zone in place: 35 bytes in 0x55836D88..0x55836DAA. `--revert` accepts v1 or v2. Both were tested on a scratch DLL copy.

**⚠ Lesson for every new reg cave:** check the instance size of the class you instantiate (u32(VMT-28)) before writing fields copied from a subclass recipe.

**Finalization audit:** nothing else in Leader's Soul runs at exit.
- VMT trampolines and crown/isl only read the bitset.
- kd runs only on Killed. FOUND/PICK are written only inside Resurrect/Animate.
- The name string is freed by the vanilla CleanupInstance.

## 10/22 v3 (`patch scripts\patch_leader_soul_v3.py`): built + scratch-tested, NOT applied (the coordinator applies)
User live test of v2: Resurrect/Animate of the dead leader CRASHED; morale High only after combat; asked for an immunity audit. The user also changed the rule: the leader comes back on a 50 % coin flip.

**Crash root cause (static):** v2's oj gave the army away with `TArmy.SetPlayer([hero+0x20])`. **[unit+0x20] is NOT the army.**
- The parent army is **[unit+4]**. TArmy.AddChild 0x5578E86C = unit VMT+8 SetParent(army), and it succeeds iff [unit+4]==army. TUnitList.RemoveChild 0x55782F6C = SetParent(nil).
- [+0x20] is another holder object. TAbstractUnit.Killed calls its VMT+0xB0; THero.OfferToJoin checks its VMT+0xD0 == 5.
- So v2 either ran SetPlayer on a foreign or stale object (crash), or skipped it (leader stays independent).
- Also note: unit VMT+8 is SetParent, NOT SetOwner. The earlier note "Possess: SetOwner(0) (vmt+0x08)" really means SetParent(nil).

**v3 changes:**
- oj uses [hero+4]. The soul return is wrapped like TArmy.Validate 0x5578CF7C:
  - map lock 0x55776830 / unlock 0x55776774 (defers GameOver)
  - army BeginUpdate 0x55703284 / EndUpdate 0x5570328C
  - Incarnate → VMT+0x1AC Killed. A possessed body → RemoveAbility 0x6B + Changed + UpdateMoraleValue.
- rpc coin flip, applied only when FOUND:
  - vanilla pool empty → the leader;
  - else TAoWHSMap.Random 0x5577827C (eax=[[0x558E9494]], edx=2; the synced [map+0x230] stream, the same call and map pointer vanilla's pick uses next): 0 → the leader, 1 → the vanilla pool (leader excluded), and PICK stays 0.
- pg/ic/iv call **UpdateMoraleValue 0x5577F058** on the new body or Incarnate. [unit+0x26] = the morale byte, read live by combat (0x5573A41A/0x5573AC9C). Base = VMT+0x17C → vc 0x5A; c7 skips the modifiers.
- **c8** Mind Decay CreateCA 0x557F85DC: its leader refusal IsClass @0x557F866C is now isl. Mind Decay grants TDecayAbility 0x83, turns the victim to the caster's side, and it dies at combat end.

**Immunity audit (all TLeader IsClass in AoWEPACK + TCPCK):**
- Covered:
  - Seduce/Charm/Dominate/Tame Animal (0xC9 = a TDominateAbility instance): all run TCommandAbility.CreateCommandCA 0x55770358 (c5, VMT+0x128) and fcGetDamageValueEx 0x55770274 (c6, VMT+0xE4). Their CanTouch (+0x11C 0x55770008) has NO leader test in vanilla; the refusal is in the CA.
  - Possess c3/c4, Mind Decay c8, disband (vc +0x190), desertion (c7 + upkeep 0).
- Not changed:
  - Turn Undead (grants 0x22 with [+0xF]=turner side), Holy Fear and Panic: no leader exemption in vanilla.
  - The remaining sites are NOT control effects: TCombatUnit/TFastCombatUnit+0xCC AI value, campaign transfer, TUnitList RW, THero NewDay (0x55786CA4), TArmyEventLog, unit enchantment +0x114 targets (Enchanted Weapon/Fury/Blessed/Dark Gift/Liquid Form), TFury, TFortifyAGC AI, THeroControlGrid UI.
  - TCPCK imports TLeader (IAT 0x46E910): 0x41369C/0x413732/0x413947 are TCAI target value ×2 (AI scoring only), and 0x438BF6+ are mod AI caves.

**Script:**
- c8 is appended to the v2 SITES (a v2 header is a prefix).
- Recognises a v1/v2/v3 zone by its code bytes. --apply upgrades in place (986 bytes on the live-state copy). --revert accepts any of them.
- Backup `.bak_leadersoul3`.
- Scratch tests on copies of the live DLL all passed:
  - v2→v3 upgrade OK; re-run says "already applied"; v2's own script ABORTs on v3.
  - v3 revert is byte-identical to v2 revert.
  - A fresh v3 apply on the reverted copy is byte-identical to the upgraded copy.
- Zone 1543 B; no relocs.

**Other facts:**
- TResurrectHero.ExecuteTE: dead pool THeroList (+0x54 count, +0x6C remove, +0x70 add); pick = Random(count) @0x557EC1D8; revive = hero VMT+0x1B0 (Animate +0x1B4).
- Placement 0x557810FC(hero, x, y, push z, owner=0, flag) builds a TArmyHS (+0x1C TArmy) with SetPlayer(owner) and AddChild. It returns nil after 30 failed tries.
- Then OfferToJoin (VMT+0x19C; true → THeroEmergeEventLog, false → TArmyInfoEventLog with [armyHS+0x1C]).
- TLeader VMT+0x16C (0x5578B4F0): only owner 0 → THero version (registers with the player); otherwise SetParent(nil)+Changed.
- TArmy VMT 0x557130EC (inst 0x2C): +0xAC AddChild, +0xB0 RemoveChild. [army+0x20] = its TArmyHS.

## 10/22 v4 (`patch_leader_soul_v4.py`): built + scratch-tested, NOT applied
**Symptom with v3 live:** Resurrect Hero on the dead leader gave AV 0x557EC271, read of 0. That is the placer 0x557810FC returning nil.

**Root cause (static, strong; the diag counters confirm it live):**
- The placer spirals over 30 rings around the caster's army, building a TArmyHS each time and adding the hero. The flag byte at 0x557EC40C = 5: bit0 keeps spiralling, bit2 never merges into an army on the hex.
- HSE map.Place → TArmyHS VMT+0x110 0x557911F8 → **TArmy.CanBePlacedAt 0x5578DDC4**. For an unplaced army it requires every unit's **VMT+0x180**.
- **TLeader+0x180 0x5578B54C** = THero+0x180 (registered hero, [+0x98]=1 via THeroControl) **plus 0x557873AC = Engine.TEObject.Compare(setup leader [player+0xD4], leader)**: a full stream compare (EngineP 0x55519114).
- [player+0xD4] = the setup TLeader (TPlayer 0x55752C58, saved). A dead and revived leader no longer streams equal, so every hex fails → nil → AV.
- This is presumably why vanilla excludes leaders from Resurrect/Animate.
- TArmy.Add 0x5578E810 also asks +0x180 when the army is placed ([+0x10]&1 = placed; GetXYZ 0x5578E884).
- The caster is NOT the problem:
  - TResurrectHero.Cast 0x557EC410 puts [castingUnit+0x18] into TE+0x14; TE.Init is 0x55779884.
  - TSpellTE.Execute (0x55779948 → mod 0x55816670 → 0x5577994F) resolves it and passes it as ecx.
  - TUnitSpellCaster.CanCast 0x5577A578 refuses dead casters ([+0x25]&0x10).
  - 0x5577ED94 = [unit+4] IsClass TUnitList → army VMT+0x98 (TArmy 0x5578E884: [+0x13..15] if [+0x10]&1, else 0xFF).

**v4 changes:**
- **lv:** TLeader VMT slot 0x557123B8 → cave. It runs the original. On refusal it accepts when THero+0x180 accepts AND (leader == PICK, or the leader holds 0x80 (granted by the revive 0x557808DC) or 0x81 (Animate 0x5578091C)). So the revived leader can also join placed armies later.
- **lc1/lc2:** 0x557EC1C3 / 0x557EC72B location. If the caster's army is 0xFF, use the army holding the 0xCE unit, else the player's first positioned army. Never a city.
- **ng1/ng2:** 0x557EC211 / 0x557EC779. On a nil placer, re-mark the hero dead ([+0x25]|=0x10, [+0x55]|=1), clear PICK, and go to the vanilla no-hero branch 0x557EC392 / 0x557EC8FA.
- **Diag** at 0x5590B3C8: +0 refusals, +4 overrides, +8 nil aborts, +0xC location fallbacks. Read it with `patch scripts\leader_soul_probe.py`.
- **Header:** v4 site bytes at 0xE0..0xFA (lc1, lc2, ng1, ng2, the lv original pointer).

**Scratch tests:**
- v3→v4 upgrade, fresh apply on a reverted copy, and v2→v4 upgrade all give byte-identical results.
- v4 revert is identical to v3 revert. v3's own script ABORTs on a v4 zone.
- 2011 B used; no relocs at the code sites; the lv slot keeps its reloc.

**Not affected:** other caster-located spells (Summon etc.). The caster is always a living unit with an army; the cast-effect at 0x557EC054 uses the same getter and is fine with a living caster.

## 10/22 v5 (`patch_leader_soul_v5.py`): built + scratch-tested, NOT applied
**v4 LAN test results:**
- (1) "No other dead hero" still revived nothing.
- (2) On the leader pick: "Exception during TSpellTE", then an AV through a garbage method pointer in VCL30. The spell was not consumed.
- (3) Runtime error 217 at exit.

**Vanilla pool:**
- = THeroControl [map+0xF8], every hero with [+0x55]&1, of ANY owner (enemy and independent dead heroes too).
- Minus TLeaders, minus level 0x55787740 > [castingPlayer+0x6C]+2.
- So v3/v4 flipped the coin even with no own dead hero. Tails revived a stranger (independent next to the caster, easy to miss).

**Placer hazard:**
- 0x557810FC creates TArmyHS+TArmy and runs AddChild(hero) BEFORE map.Place. If Place refuses, it frees the TArmyHS (→ TArmyHS.Destroy 0x557908FC frees its TArmy; the EngineP list dtor 0x5570323C drops the children), then retries the next hex with the same hero.
- This is the prime suspect for the freed-object AV and the 217. Unconfirmed: v4 diag was not captured.

**v5 changes:**
- **rpc5** (rp1/rp2 now call it): count only pool heroes with death owner [+0x5C] == the caster's player. Zero → the leader always; else the synced flip as before.
- **pj1/pj2** (placer calls 0x557EC20C / 0x557EC774): for PICK, the leader is AddChild'ed into the army holding the 0xCE soul unit (TArmy.Add asks +0x180 → lv accepts PICK). The cave returns [army+0x20] TArmyHS as the placer result. No new army, no Place. If refused → vanilla placer + ng.
- **ojw** wraps oj (breadcrumbs). **ng5** = ng + breadcrumbs.
- **Breadcrumbs** at 0x5590B3D8:
  - STAGE: 1 picked, 2 tails, 3 join try, 4 joined, 5 join refused, 6 placer ok, 7/8 oj in/out, 9 nil abort.
  - hero, soul army and the AddChild result are also recorded.
  - `leader_soul_probe.py` reads them, even while an error dialog is up.
- **Header:** pj1 at 0xD8, pj2 at 0xFA.
- **Scratch tests:** v4→v5, v3→v5, v2→v5 and a fresh apply are all byte-identical; v5 revert == v4 revert; 2.8 KB of the zone used.

## 10/22 v6 (`patch_leader_soul_v6.py`): built + scratch-tested, NOT applied
**v5 live: WORKS** (STAGE 8, AddChild 1, clean exit).
The handled EFCreateError at the cast is benign. AoWEPACK+0x55247 = TPlayerControl+0x58 (0x55755128), the autosave writer: "X\Save\autosave.asg" via [0x558FA048] VMT+0xAC inside try/except. Two instances on one PC write the same file; this has nothing to do with Leader's Soul.

**User rules for where the leader appears:**
- Join the CASTER's stack ([TE caster [ebp-0xC]]+4, IsClass TArmy).
- Else a new army on a free hex, searching outward like summons (≤30 rings).
- Else fizzle cleanly. Never the soul's stack.

**pj6** (pj1/pj2 now point here; v5's pj is unused):
1. AddChild into the caster's army.
2. Else a ring search with HSE InitHNWalk 0x557026D4 / WalkToNextHN 0x557026DC around the placer's x/y (the caster hex), rings 1..29. For each hex:
   - hex check 0x55781008(hero, x, y; z, owner = leader owner, flag 5 = no merge)
   - new TArmyHS (cell 0x55713360, ctor 0x557908BC)
   - SetPlayer(owner) → AddChild → THSMap.PlaceHX 0x557025F4(map, hs, x; y, z)
   - If Place fails: hero.SetParent(nil) (VMT+8) BEFORE Free(hs), so nothing is freed under the hero. Next hex.
3. No hex → return nil → ng5 abort. Vanilla summons fizzle the same way: TSummonSpellTE 0x557E410C uses the placer with owner = caster owner and flag 1; a nil result just releases the unit. The spell is consumed, because the TE completes through the no-hero branch.

**Breadcrumbs:** STAGE 10/11 caster join try/joined, 12 ring search, 13 placed, 14 no hex (then 9). [+0x18] = target army, [+0x20] hexes tried. The probe is updated.

**Scratch tests:** upgrades from the live v5 copy, v4 and v2, and a fresh apply, are all byte-identical. v6 revert == v5 revert. 3.6 KB of the zone used.

**Facts:** the summon placer flag byte at 0x557E43E8 = 1; the leader game-start placer flag at 0x5578B750 = 0 (TLeader+0x1C4 0x5578B6D0, owner = the leader's).

## 10/22 v7 (`patch_leader_soul_v7.py`): built + scratch-tested, NOT applied
**Bug:** a Possessed TLEADER dying spawned an Incarnate without 0xCE. ic/iv only inherited from 0xCE holders; the leader is a leader by class.

**v7 changes:**
- **ic7** (0x55769A4C) and **iv7** (0x5578CFF4) test islv (TLeader || 0xCE) on the dying unit. The Incarnate gets 0xCE + UpdateMoraleValue.
- iv7 additionally clears the TLeader's [+0x25]&2 (active) around its overworld Killed call and then restores it. Without that, TLeader.Killed 0x5578B51C → GameOver would end the game although the soul lives on.
- Combat needs no extra handling: Killed skips GameOver while [map+0x120] != 0, and DestroyObject's defeat block (c1) is skipped because CombatObjectDestroyed clears the dead status bit first.
- Everything else keys on 0xCE: cr, kd/c1/c2, vc traps (the Incarnate is a TUnit), immunities, oj, the AoWx.exe portrait.

**Scratch tests:** v6→v7 = fresh apply; v7 revert == v6 revert; zone 3.4 KB of 4 KB. The live DLL has another fork's cave at 0x55837800+ (just past our zone end) and a hook at 0x55749914; neither touches us.

**Bug 2** ("AV at 00CB1BF7 in AoWEPACK, read of 000003EE" when that Incarnate possesses in the same combat): the base is unknown. Plausible instruction starts at VA 0x557?1BF7:
- 0x55771BF7 TAoWMapField.GetExplored `mov edx,[eax+0x18]` (eax = 0x3D6 garbage field)
- 0x557C1BF7 TExplorationSite `call [esi+0x1F4]`
0x55731BF7 is mid-instruction, so not that one. In v6 that Incarnate had no 0xCE, so pg did nothing → probably vanilla or another hook. A VEH-logger repro is needed.
