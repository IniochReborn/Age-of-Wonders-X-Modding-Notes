---
name: no-pair-start-spells
description: 2026-10-19 dual-sphere (pair 9–22) spells excluded from automatic starting-spell grants (day-1 G1 0x5577CCD6, campaign catch-up G2 0x55732244); patch_no_pair_start_spells_v1
metadata:
  type: project
---
Both grants test GetSpherePicks 0x5578B17C, which our pair rule makes picks(A)+picks(B) → pair spells eligible. G1 = day-1 starting spells 0x5577CC2C (entry hooked by drought; skipped when [game+0x11A]==1 and the map's known list [res+0x30] is non-empty — map-maker spells untouched); G2 = TAoWCampaign slot 0x55723EAC → 0x5573217C (AIs get tier ≤ completed/4+1). Caves 0x5581F100–0x5581F137 (zone to 0x5581F200), `.bak_nopairstart`. Research gate ValidResearchSpell untouched. Existing saves keep already-granted spells. APPLIED 10/19, VEH 6.

**10/20 research gate fix:** TPlayerMagicControl.ValidResearchSpell 0x5577CFF0 never checked known spells per component sphere (pair picks = picks(A)+picks(B)−1 ≥1 once both picked; tier ladder counts only the pair sphere itself; tier 1 free) → Air/Life researchable without a Life spell. `patch_pair_research_gate_v1.py` (hook 0x5577D01B → cave 0x5581DE00 'PRG1', 183 B, `.bak_pairgate`): pair spell (sphere 9–22) needs a KNOWN spell of exactly sphere A and of exactly B (Cosmos/Secret/pair spells don't count). Same rule for UI/AI/ListResearchSpells. In-progress research in saves continues. APPLIED.
