---
name: seeker-bolts
description: Seeker Bolts (unit ability 0x3A, Ability.pfs record 68) gold/blue rework 10/18 — startup orb spin + held launch, art/sfx, scripts and LIFO
metadata:
  type: project
---
2026-10-18 APPLIED (VEH 6, untested): Seeker Bolts = unit ABILITY 0x3A (vanilla 'Shoot Black Javelin' renamed), kind-6 projectile like Magic Missile; art/sound from Ability.pfs record 68.
- patch_seekerbolts_pfs_v1.py: record 68 slots → DualDF 7000–7007 head, 7008–7015 trail, 7016–7045 spin (30 frames), 7046–7061 impact; sounds SEEKER_CHARGE / SEEKER_LAUNCH / SEEKER_HIT.WAV (no DUAL prefix; ship via --add).
- patch_tc_seekerbolts_v1.py: holds the bolt 30 ticks (HOLD) while 3 gold/blue orbs spin ~20 px (LAUNCH_PX) in front of the caster, then launches from there with SEEKER_LAUNCH; impact burst spawned; sits at the HEAD of the kind-6 chain (gust → soulsiphon → Ashes → Hellfire) → revert it first before touching those.
- New synths seekcharge / seeklaunch / seekhit in the sfx builder.
- Risks: tick rate assumption 34.5/s for the flash/sound sync; charge hum starts with the attack anim; adds ~1.3 s per Seeker shot (AI turns).

**v2 2026-10-18 (user: startup skipped, bolt unchanged, no blue, no new hit):** ROOT CAUSE = the shot is a **kind-1** TfxHS, not kind 6. TCPCK ability→fx-kind table DATA **0x467248** (read via [0x4693DC] @0x409D07 → [ca+0x60] → AddEffect 0x40A170) maps 0x3A→1 (like Archery/Javelin; Magic Bolts 0x79→3); never edit it (~12 AI/CA readers treat 1-3 as ranged). Kind 1 picks the gfx slot from [fx+0x20] = flight direction 0..23 (hence 24 BOLTS slots). `patch_tc_seekerbolts_v2.py` (upgrades v1 in place, `.bak_seeker2`, revert only with v2) tests kind 1 + new hook SHW @0x42F9CB in TfxHS.Show dispatching 0x3A kind-1 as kind 6 (head slot 0 + trail slot 1). Art v2: head drawMode 258/95 solid gold orb + blue fire ring; trail 770/70. Sfx v2: seekcharge2 + Vortex + reversed MagicA04 / Shockw+MagicA04+A_Force2+seekzap / Explod1+seekhit+A_Force1+seekzap. APPLIED, VEH 6, untested.

**v3 2026-10-18 (user: v2 "awesome"; bolt more like the start-up orbs, lighter blue/glowier; layer in the original sfx; hits at the feet):** `patch_tc_seekerbolts_v3.py` (in-place over v2, `.bak_seeker3`, revert only with v3; zone 0x44F000–0x44F2E0) adds a draw-only lift: Show's camera-Y local [ebp-0x18] raised 0 → LIFT 18 px (even) over the last 40 % of the path + impact helper spawned 18 px higher. Art: seeker_head3 (258/75) + seeker_trail3 (770/80). Sfx: v2 + HOLYSPIRITDEATH (charge/launch) + DREAM_ESSENCE_CORPSE_COLLECT (hit) at ~25-30 %. APPLIED, VEH 6.
**v4 10/18:** head4 additive 770/90 (spin-up glow look), trail4, impact2 with gold flash/ring/sparks; sfx v4 = HOLYSPIRITDEATH only under LAUNCH (0.55, 1.6 s, ~14 %), FADE_OUT launch 0.6. APPLIED, VEH 6.
**v5 10/18:** colours swapped (blue core / gold halo, light-blue/gold/light-blue orbs) + ×0.78 width (seeker_head5/seeker_trail5); impact unchanged. APPLIED.
