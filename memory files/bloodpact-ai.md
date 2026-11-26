---
name: bloodpact-ai
description: 2026-10-19 Blood Pact (350) recast every autocombat round — High Prayer clone AI scored by missing HP; patch_bloodpact_ai_v1 scores units lacking Bloodlust (0xA8) on VMT+0x88/+0x90/+0x98; 300/301/390 same flaw (fix pending)
metadata:
  type: project
---
Slots: +0x90 fcPrefetchCombatCommands 0x557F8008, +0x98 fcGetDamageValueEx 0x557F811C, +0x88 tcGetDamageValueEx 0x557F8224 (slot addrs 0x557F465C/64/54). Cave zone 0x5581E100–0x5581E29A 'BPA1' (prev slot targets kept: 0x5586B9C0 / 0x5586B990 / vanilla) → 300 per unit lacking 0xA8, 0 when all have it. `.bak_bloodpactai`; revert refuses if something chained in front. Awaken Spirit 300 / Blessing of the Forest 301 / Frenzied 390 = same scorer flaw + fast-combat Execute only maps 350 (they grant High Prayer blessing+heal) — fork building patch_highprayer_clones_fast_v1 (zone 0x5581E2A0–0x5581E400). APPLIED 10/19, VEH 6.
**v2 10/19:** `patch_highprayer_clones_fast_v1.py` upgrades the BPA zone in place (0x5581E100–0x5581E3F9, `.bak_hpclones`): need() per spell (350 lacks 0xA8; 301 lacks 0xB7; 300 non-hero creature lvl≤2 lacking 0xB6; 390 lacks 0xB3/0xB4) for all 3 scorers + fast-combat Execute slot 0x557F442C (was 0x557F7DA4) grants own abilities for 300/301/390 (no heal/blessing). Revert this first (restores BPA v1). APPLIED.
