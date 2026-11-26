---
name: caster-evoker33
description: 2026-10-18 Evoker now covers combat-only unit-class spells (Suspend/Static Shield/Mimic/Reversal/Second Wind/Borrow Time/Martyr) + all four caster abilities −30 %→−33 % (Evoker III −50 % kept); patch_caster_evoker33_v1
metadata:
  type: project
---
Class pick caves 0x55816480 (cast) / 0x55816620 (research/upkeep classify) chose by spell class → Remedy/Dispel clones counted as Enchanter. New rule: unit spell is Evoker when [spell+0x22]==0 (combat book) or [spell+0x0C] lacks the map bit (vanilla unaffected). 33 %: cast cave /30 → 2/3 rounded; 0x55816580 (2v+1)/3 keeping min-1-off upkeep; turn estimate 0x55816A40 ×3/2 ceil; Ability.pfs 182–185 text 30%→33% (replaces only those records). 12 same-length edits + new cave 0x5581E000 (56 B). Revert BEFORE patch_caster_levels_v1 / patch_caster_research_upkeep_v1. Unchecked: Void Step/Mermaid/Silver Dragon/Magic Sight classes; Mimic's fallback real Dispel stays Enchanter. APPLIED 10/18, untested.
