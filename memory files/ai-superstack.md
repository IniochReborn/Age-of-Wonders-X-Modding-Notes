---
name: ai-superstack
description: 2026-10-20 AI leader superstacks (adjacent-only): at turn start pull strongest adjacent own units into the leader stack / swap out weaker (≥15 % better), no garrison minimum (user 10/20), ≤8 moves/day; patch_ai_superstack_v1 (TInitializeAIPA.Process slot 0x55719014, zone 0x55819400–0x55819C00)
metadata:
  type: project
---
Hook: TInitializeAIPA Process slot 0x55719014 (reloc'd) → cave entry 0x55819410 ('SST1', 1048 B): AI step loop re-calls while it returns 1, so one move per call. Move = human MoveArmyXYL 0x5574A490 with unit mask onto the leader army (combine), queued on the AI's per-player move queue (MP same as normal AI moves). Leader = [player+0xD4], army [leader+4]; neighbours = own armies on the 6 adjacent hexes same level (engine ring walk); units with MP left ranked by all-kinds strength 0x5577F924 mask 0xFFFF; city armies: NO minimum (MIN_GARRISON 0 per user — it was new, not vanilla); room → pull strongest; full → push weakest out if neighbour best ≥15 % stronger (then pull next call); ≤8 moves/player/day (table .idata 0x5590B5A0–0x5590B5E0); refused move ends the day. Tunables MAXMOVES/MIN_GARRISON/SWAP_PCT. Not done: 2–3-hex gathering, AI group mission awareness. `.bak_superstack`. APPLIED 10/20, VEH 6, untested.
