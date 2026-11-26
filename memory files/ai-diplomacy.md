---
name: ai-diplomacy
description: 2026-10-19 AI diplomacy extras (tributes to humans, peace/alliance sweeteners, suggest war/break alliance vs disliked races, threats); patch_ai_diplomacy_v1 APPLIED 10/19 (VEH 6), untested
metadata:
  type: project
---
Race relation 0–100 (start 50); bands ≤29 Hateful, 30–49 Wary, 50–69 Neutral, 70–89 Polite, ≥90 Friendly. Diplomatic action types 0 Declare War, 1 Offer Peace, 2 Propose Alliance, 3 Message, 4 Threaten, 5 Tribute, 6 Break Alliance, 7 Message as Y, 8 Break Alliance with Y, 9 Declare War to Y; state 0 peace / 1 war / 2 alliance / 3 unknown; gold/mana leave sender on send, refunded on reject; one pending message per sender. Vanilla AI uses 0/1/2/6 with RNG seeded from game state + day (restored after). `patch_ai_diplomacy_v1.py` (code 0x55884000–0x55886000 — 0x55820000+ is patch_slow_v1's; memo 0x5590BF40; `.bak_aidiplo`): hook after the AI's own per-player diplomacy step → ≤1 extra action/AI/human/day (tribute → suggestion → threat), deferred if a message is pending; hook on AI peace/alliance offers → relation/2 % sweetener 1–50. Payments capped at half of current gold/mana; none while at war/unmet. Risk: humans receiving types 4/8/9 is an untested UI path.
