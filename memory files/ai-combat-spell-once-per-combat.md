---
name: ai-combat-spell-once-per-combat
description: "CONFIRMED WORKING 2026-07-26: stop the AI spamming combat spells in tactical combat. Turn Undead always-deprioritized; Terror / Slow(Hunter's Mark) / Ooze limited to ONE cast per combat (Slow also gets a first-cast priority boost). AoWEPACK.dll. Key breakthrough = TSpell.CombatCastingDone 0x557794E8 is the universal tactical combat-spell cast-completion. Extends [[aowx-re-reference]]."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-26T23:56:01.471Z
---

**GOAL (user):** AI in tactical combat spammed Ooze / Terror repeatedly, and cast Turn Undead on non-undead (pointless). Wanted: Terror/Slow(Hunter's Mark)/Ooze = **one cast per combat**; Turn Undead = **always score extremely low** (only cast if it's the AI's only researched spell). All CONFIRMED WORKING in-game.

## MECHANISM (per-combat flags in BSS scratch)
- **Flags** (writable BSS, PIC delta-addressed): `F_OOZE=0x558FAF20`, `F_TERROR=0x558FAF21`, `F_SLOW=0x558FAF22`.
- **Reset** at `TCombat.Create` @0x5572708C (hook→cave @0x5580DCE8): zeros all three flags at the start of each battle. Verified once-per-combat (not per-turn).
- **Pattern:** a *set-hook* flips the flag when the spell actually casts; a *value wrapper* on the spell's AI damage-value method shrinks/zeros the score when the flag is set. Value is **relative priority** → shrink deprioritizes.

## THE COMBAT-SPELL AI ARCHITECTURE (hard-won, reusable)
Two distinct combat contexts with **different value + cast paths** — this was the whole difficulty:
- **Fast/auto-resolve combat** uses the `fc*` methods: `fcPrefetchCombatCommands` (VMT **+0x90**) scores each target via `fcGetDamageValueEx` (**+0x98**), and **drops the command if the score is 0** (`cmp [output],0; je skip`; else priority = `DVtoDEV(value)`). Execution = `fcExecuteCombatCommand` (**+0x94**) → `CreateCA` (**+0x78**) → `TCombat.ExecuteCombatAction` 0x55727224.
- **Tactical combat** (what the player watches) uses the **`tc` value** = `tcGetDamageValueEx` (**+0x88**, base 0x5577969C) → which calls **`GetCombatDamageValueEx` +0x84** (the real per-target scorer). The cast is executed as a **combat action (CA)**: spell-specific CAs for some spells (`TTacticalCombatTerrorCA.Execute` 0x557F990C), but **generic CAs** (`TCombatSpellCA`/`TExclusiveCombatSpellCA`/`TMultiTargetCombatSpellCA`) for spells without a dedicated one (Ooze).
- **⭐ THE UNIVERSAL TACTICAL CAST-COMPLETION: `TSpell.CombatCastingDone` @0x557794E8.** Every generic combat-spell CA `.Execute` calls it (also `TSpell.CombatSpellCast`, `TUnitSpell.ExecuteCA`), always with **eax = the spell object**. This is THE reliable, spell-carrying, cast-only hook for tactical combat. Identify a specific spell by comparing `[eax]` (its VMT ptr) to the spell's runtime VMT (delta-trick: `lea reg,[delta+preferredVMT]`).
- The AI spell-list driver keys off VMT **+0x5c** `AIPrefetchCastSpellActions` — **but nothing calls [reg+0x5c]** (0 sites); Ooze's +0x5c is the empty base anyway. Don't rely on +0x5c.
- **Ooze VMT base = 0x557F5DD4** (TOoze). Slots: +0x50 ExecuteTE (empty ret, unused), +0x74 ActivateCombat (creates TCombatSpellCaster 0x5577a168 — only its caller), +0x78 CreateCA (shared base 0x557F72C0, in 21 combat-spell VMTs), +0x84 GetCombatDamageValueEx (0x557F9648), +0x88 tcGetDamageValueEx (base), +0x90/94/98 fc*. To find any spell's VMT base: search image for its known method ptr, subtract the slot offset.

## ⚠️ KEY LESSONS (cost ~10 test rounds on Ooze)
1. **÷64-floor-1 is NOT enough to stop fc/tc spam** — the driver drops a command only when the value is **exactly 0**; value≥1 keeps it as a (low-priority) candidate that still wins when the AI has nothing better. **Force the value to 0** to actually drop it. (Terror worked with ÷64 because its driver picks highest-priority, so ÷64 makes it lose — different driver semantics.)
2. **Tactical ≠ fast combat.** Ooze's cast never touched +0x74/+0x78/+0x94 (all fast-combat-only). Hooking the spell's own cast VMT methods failed; only `CombatCastingDone` (downstream of the generic-CA path) fired in tactical.
3. Terror/Turn Undead have their **own tc-value overrides / dedicated tactical CAs**, so hooking their tc-value slot + tactical CA Execute worked directly. Ooze/Slow **inherit base**, so needed the generic path.
4. Diagnostic that cracked it: force the candidate value method to **unconditional 0** → if the spell stops casting entirely, that method IS the control point (proves the value path before chasing the cast point).

## FINAL PATCH MAP (AoWEPACK.dll, all PIC delta-safe)
- **Turn Undead:** tc-value slot 0x557F4350 → cave @0x5580FA49 (unconditional ÷64, floor 1). Always low.
- **Terror:** set @0x5580DD14 (hook `TTacticalCombatTerrorCA.Execute` 0x557F990C, sets F_TERROR); value wrapper @0x5580DD34 (tc-slot 0x557F625C, ÷64 if F_TERROR). Reset shared.
- **Slow / Hunter's Mark:** set @0x5580DD68 (hook `TSlowCA.Execute` 0x557F8818, sets F_SLOW); boost/nerf wrapper @0x5580D2AA (tc-slot 0x557F4E88): **unflagged → value = value*8 + 100 (first-cast priority boost); flagged → ÷64**. (Boost needed because Slow's base priority was too low to ever be cast.)
- **Ooze:** flag set @0x5580D792 (hook `TSpell.CombatCastingDone` 0x557794E8, VMT-identity vs Ooze 0x557F5DD4 → set F_OOZE). Value gates: +0x84 slot 0x557F5E58 → 0x5580D6D4, +0x98 slot 0x557F5E6C → 0x5580D704 (both: **force value 0 if F_OOZE**). Redundant fast-combat set-thunks also present: +0x74→0x5580D738, +0x78→0x5580D69C, +0x94→0x5580D64E (harmless; give once-per-combat in fast combat too). Dead caves (not referenced): 0x5580D668, 0x5580D6B8.
- Cave free-space used: 0x5580D2AA region, 0x5580D64E–0x5580D7Bx, 0x5580DCE8–0x5580DE0D, 0x5580FA49, plus VMT-slot repoints. See [[active-patches.md]].

## BUILD / BACKUPS
- No single consolidated build script (built incrementally). Pre-feature backup: **`AoWEPACK.dll.bak_preturnundead`** (= chooser + version 0410, before any spell-AI work). Working state = current AoWEPACK.dll. Interim per-step backups exist (bak_preterror/preslow/preslowboost/preooze…/preoozeCCD) — safe to delete once satisfied.
- Behavior tunable: edit the ÷64 (`shr eax,6`), the Slow boost (`shl 3`/`add 100`), or Ooze force-0 in the respective caves.
