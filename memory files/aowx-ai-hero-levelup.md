---
name: aowx-ai-hero-levelup
description: "AI hero/leader level-up chooser (ExecuteUpgradeHeroAI, July 2026 heroai_build.py caves) — layout, the 30-entry weight table, and the 2026-09-14 Marksmanship-needs-ranged-attack gate"
metadata: 
  node_type: memory
  type: project
  originSessionId: fc7da3cb-ec2d-410c-8c83-b8a1a366ca80
  modified: 2026-09-15T01:41:46.903Z
---

**Chooser:** `THero.ExecuteUpgradeHeroAI 0x55787A24` (AoWEPACK.dll). Vanilla weighted list (TDoubleItemList at edi; `0x55702FCC` = AddWeighted(eax=list, edx=pick id, ecx=weight)); ebx = hero, esi = skill points, ebp = &AoWHSSet 0x558FA044 ([set+0x80] = TAbilityControl). Stats are picks 0..4 (weights retuned to 100/255/50/50/100 at 0x55787A67/…/0x55787B04). The July 2026 expansion (script only in `backup\RESTORE POINT 2026-07-24b…\patch scripts\heroai_build.py`, NOT in patch scripts) hooks 0x55787B15 → **eligibility cave 0x5580FD40** (ebp becomes the PIC delta; loops a 30-byte id table @0x5580FDD5 with u16 unaffordable weights @0x5580FDF4 and affordable weights @0x5580FE30; per entry: GetAbility 0x557501C0 → `[vmt+0xC4]` CanTake(hero) → `[vmt+0xC8]` cost vs esi → AddWeighted with id) and 0x55787C60 → **apply cave 0x5580FE6C** (picks 0-4 → vanilla stat code, else GetAbility/cost check/`[hero vmt+0x94]` expand). Caves end 0x5580FEE8; 0x5580FF00 is a different (rank×level XP) cave.

**Marksmanship gate (2026-09-14, `patch scripts\patch_ai_marksmanship_gate_v1.py`, backup `.bak_aimsgate`, applied, untested):** the CanTake call at 0x5580FD7B → cave 0x55816100: after CanTake, if the table entry is 0x20 the hero must own an ability that `System.@IsClass` (thunk 0x557010C0) says descends from `AoWE..TRangedAttackAbility` (VMT 0x5571E8D4, PIC via ebp delta), scanning ids 1..0xFF through `GetAbility` (nil past count) and the hero's merged `[vmt+0x148]` GetAbilityEnabled. Stack at the hook: [esp+4] pushed ability, [esp+8] table index.

**Weight retunes:** `patch scripts\patch_ai_levelup_weights_v1.py` (backup `.bak_aiweights`) edits the u16 tables in place by ability id with expect-old asserts — the way to change any weight now (the July table: Marksmanship was 5/5 → **20/20 on 2026-09-14**).

**Why:** user report 2026-09-14 — AI heroes occasionally banked for/picked Marksmanship with no ranged attack. Related: [[aowepack-ability-system]].
