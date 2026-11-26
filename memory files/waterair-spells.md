---
name: waterair-spells
description: Water/Air dual-sphere spells (pair 21, ids 396-399) - Misty Step / Flashfreeze / Nimue's Favour / Ice Age; applied 2026-10-15, untested
metadata:
  type: project
---
Water/Air = sphere pair 21, ids 396-399 (pair formula fits; 400-403 free). All APPLIED 2026-10-15, startup clean.

- **396 Misty Step**: TCallFlames clone (Void Step's chassis, pfs 212), range 4. patch_mistystep_v1.py routes 396 into Void Step's teleport cave (TCPCK 0x438100 via hook 0x40B452): E1 0x43811B id check → chk cave TCPCK 0x43B400 (0xCA or 396), E2 0x43833B sound lookup uses [esi+0x18], E3 0x438456 puff tag = casting spell id; S1 AoWEPACK 0x55810B13 siege check → chk 0x55834000. One-step warp, so walls never block; destination validated vs the caster's movement, spirals to the nearest valid hex. gfx DualDF 2110-2121 mist_swirl (origin + destination); sfx DUALWA_MISTYSTEP.
  - ⚠ build_warp_self_siege.py now dry-runs "would apply" because S1 changed - DO NOT re-run the old build_warp_self_* scripts (the others assert "already exists").
- **397 Flashfreeze**: TVaporize clone (pfs 131, class 7 raw id), ATK 7 / DMG 2 / Cold 0x02 / shots 3 (+0x38 honoured statically @0x40B5C0) / range 4 / roll vs DEF (0x3C=0). No code. gfx DualDF 2170-2185 frost_burst (NOT 2130 - Nimue uses it); sfx DUALWA_FLASHFREEZE.
- **398 Nimue's Favour**: Earth Mastery shared (patch_goldenage_v1.py v3: Golden Age 302 + Black Tide 342 + Nimue 398; world-FX mark 4). nfp after btp in the CreateMovePointTable hook: own/allied (relation 2 or self) units' passable water costs c → max(1, floor(c*10/13)); Black Tide penalty applies first. gfx 2130-2132 silver_motes; sfx DUALWA_NIMUE.
- **399 Ice Age**: Air Mastery shared (patch_overgrowth_v1.py v4: 383 + 327 + 399; oga gained an "any player" mode dl=0x80). Turn order Overgrowth → World Healer → Ice Age. Grass/Steppe/Wasteland/Dirt (bare or hill) → snow (3); bare water without an army → ice (6); skips structures, markers, desert, lava, forest, mountains, roads, bridges. Permanent. While any Ice Age is active World Healer leaves snow alone and vice versa (no flip-flop). Knobs ICE_PM 15 / ICE_PICKS_PM 600 / ICE_SEED_DIV 300. gfx 2150-2152 snow_drift; sfx DUALWA_ICEAGE.
- Icons (CLOUDS Air 0 → Water 100): mist arc over a wall to a cloaked figure / three ice shards into a frost burst / arm rising from waves with a sword / snowflake over snowy mountains.
- Ship: Sfx\Zsp\DUALWA_*.WAV + DualDF.ILB.

Related: [[waterdeath-spells]], [[lifewater-spells]], [[warp-self-combat-spell]].

## v2 round (2026-10-15, user feedback) — APPLIED, VEH startup clean, untested in game
- **Icons:** Misty Step = Void Step icon top (snapshot `patch scripts\voidstep_ink.png`, live SpellIcn 52, thresholded >230) + drawn water splash crown. Flashfreeze = ring of inward ice shards + 3 spikes. Nimue = Holy Champion ring (`champion_ring_ink.png`, live 155) + Cleansing Flame hands + Water Walking wave (vanilla 101 rows 17-28). Ice Age = Level Terrain mountains (vanilla 50, arrow masked) + 5 snowflakes. Helper `_ink_png(fname)` in the icons builder.
- **Sfx:** MISTYSTEP v2 (reversed wind, shimmer, Teleport, waterlg + M_Swim1 splash; DRIVE 2.4). Flashfreeze: DUALWA_FFRING (cue 0, icy in-rush 1.1 s) + DUALWA_FLASHFREEZE (cue 1, per hit).
- **Flashfreeze ring:** `patch_tc_flashfreeze_v1.py` — gate at TCPCK 0x43B440 (273 B) in front of the NextStrike chain (sites 0x40B6F1/0x40CBE7 → 0x43B440 → Hurl Boulder 0x43B180 → ...); wait dword 0x46BFE4; ring 30 ticks then strikes +10 ticks gap; 397 added to castsnd exclusion list 0x43C900. Per-hit cue 1 is native (0x42D3E5 on the burst's last frame). Art `frost_ring()` DualDF 2190-2205 (160x96, slot 1). ⚠ re-running patch_hurlboulder_glow_v1 now ABORTs (expected); revert flashfreeze first.
- **Nimue gfx v2:** silver_motes = blue water drop → ripple frames, blend 90.
- **Ice Age v5:** patch_overgrowth_v1 knobs 30/1200/150; thaw markers TFrozenWaterHS +0xE = 0xC0|orig terrain, +0xD = 0x40|player, +0xC = delay 1-10; thaw caves rcb 0x55824C40 / irev 0x55824C50 / nt 0x55824D90 (zone 3607/8192). Glow = patch_drought_glow_v1 v3 (cave 252/256 B FULL) drawing 399 slot 3 = `ice_sparkle()` DualDF 2210-2221 (SWARM 20-31 copies, blend 55). DualDF next free 2222.

## v3 round (2026-10-15, 2nd feedback) — APPLIED, VEH startup clean, untested in game
- Icons: Misty Step v3 = Void Step figure at 3/4 over a hand-drawn crown splash (curling tongues after `art import export\splash.jpg`; a direct trace was speckle noise at 40x35). Flashfreeze v3 = traced `flashfreeze.jpg` at drawing res → `flashfreeze_user_mask.png` (320x280, thr 128). Ice Age v3 = 8 uneven flakes (rnd 3990), small ones in the valleys. Nimue v3 = ring of 18 round particles (not solid), hands 22x27 sunk into the wave (wave over the wrists, water band below). ⚠ PIL MaxFilter(1) = native divide-by-zero crash (exit 127, no traceback).
- Sfx: new synths `splash:secs` (heavy plunge) + `icering:secs` (glassy in-rush). MISTYSTEP v3 = splash + slowed waterlg/swims + Splat. FFRING v2 = icering + subswell + reversed Iceloop.
- Hit sync: frost_burst v2 builds up over frames 0-11 and shatters/flashes on 12-15 (the hit + cue 1 land on the LAST frame).
- Drought (391) slot 1 v3 = `drought_sparkle()` (SWARM 20-31 recoloured red/orange) DualDF 2222-2233, anchor (-33,-39), blend 60; patch_drought_glow v4 steps Drought AND Ice at ICE_PERIOD 3 (only Overgrowth keeps 6). drought_glow 1450-1461 unused. DualDF next free 2234.

## v4 round (2026-10-15, 3rd feedback) — APPLIED, VEH startup clean, untested in game
- Icons: Misty Step v4 = full-size Void Step figure (crop row 17) rising from a jagged splash mass (9 spikes 20-160°, bubbles, ripple rings, drops). Ice Age v4 = straight regular flakes, 9 scattered positions (user: "symmetrical" meant placement). Nimue v4 = no bottom water; everything under the wave crest cleared so the hands are cut off at the water line.
- Misty Step gfx v2 (mist_swirl, 2110-2121) = blue flash + splash ring + 34 glowing blue droplets on arcs.
- FFRING v3 = new synth `glasswind:f0:f1:secs` (Implosion's wind-up as glass partials) x2 octaves + subswell + vacuum + reversed Ice/Iceloop; DRIVE 2.3.
- ⭐ Flashfreeze sync RE: kind-7 burst frame = counter/(f18+1), life n*(f18+1) ticks; cue 1 + landed byte on the LAST tick (0x42D3A5→0x42D3E5); TCAbRangedTE.Execute 0x40C31F applies damage/popup/flinch that tick; f20 ignored for kind 7. Desync = 32-tick bursts overlapping (strikes ~15 ticks apart) + a hit WAV without a hard attack. Fix: frost_burst 8 frames (2170-2177, flash peak last), GAP_TICKS 14, RING_TICKS 24, FLASHFREEZE.WAV = first 0.14 s of Ice + AIce + bells.
- Drought v3: map-wide Air-Mastery drift via patch_drought_worldfx_v1.py v3 (DRIFT routine 0x5585FC00, 91 B, replays Air Mastery's anim setup for 391; donor stays TWaterMastery); slots 0-2 = heat_drift() DualDF 2234-2236 (blend 40); hex glow moved to slot 3 (patch_drought_glow GLOW_SLOT 3), blend 32. Cue 1 DROUGHTP no longer plays. 1274-1276 + 1450-1461 unused. DualDF next free 2237.

## v5 round (2026-10-15, 4th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v5: full Void Step figure rows 0-19 (arms/hands/legs restored) with row 12 repeated 4x (longer torso); splash drawn alone then cleared 1.6 px around the figure.
- Ice Age icon v5: mountains = vanilla 50 ink UNthresholded (>30), unscaled, shifted +3 rows; arrow mask [14,0,26,22]; flakes skipped if their box touches the mountain.
- Nimue icon v5: only the wave's top run per column (gap under the erased walker's feet bridged by interpolation), everything below the crest cleared, 1-px gap above it.
- FFRING v4 = Implosion's ring recipe a fifth up (growlhorn 120:255 + 60:128, subswell, reversed MagicA01) + reversed Ice/Iceloop + shimmer + bell. Hit WAV restored to v2 (Ice+AIce+bell) trimmed to 0.5 s.
- frost_burst v3: + 26 glowing blue droplets + splash ring erupting over frames 4-7 (widest on the hit frame).
- Drought glow blend 22.

## v6 round (2026-10-15, 5th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v6: v4 splash drawn whole; figure rows 0-19 (EXT 0) + torso (row 12) continued to the bottom, then the figure is CUT 1.6 px clear of the splash (splash wins).
- Nimue icon v6: Water Walking wave at full grey detail (>30), walker erased as rows 0-16 + legs [15..19 x ≤19] [21..23 x ≤17]; below-crest clear per column.
- Ice Age icon: bottom flake R 3.0, new small flake (27.0, 20.0, 1.7).
- ⭐ patch_tc_flashfreeze_v1.py v3: early cue hook at kind-7 landing test 0x42D3A2 (fx [+0x14]==0x34, [+0x18]==397): cue 1 CUE_EARLY=3 ticks before landing, vanilla cue skipped for 397; at landing spawns a kind-0x26 fade driver (marker [fx+0x24]=2) drawing slot 2 = frost_fade() DualDF 2240-2251 (12 frames f18=1); slot-pick caves in front of 0x42A5E9/0x430059 chains (→0x43E3A0/0x43E3D0); GAP_TICKS 10. v2 copy in job tmp. DualDF next free 2252.

## v7 round (2026-10-15, 6th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v7: original figure rows 0-19 (arms) WINS over the splash (splash cleared 1.6 px round it); only the torso extension below row 20 is cut to the splash.
- Flashfreeze ring slower: frost_ring 20 frames (DualDF 2190-2209), RING_TICKS 30. Script now detects the ring-24 v3 zone ("v3r24", RING_TICKS_V3) for in-place upgrade — ⚠ any future constant change in patch_tc_flashfreeze_v1.py needs the same "previous state" recognition (zone bytes embed the constants).
- Nimue icon v7: wave band cropped from row 12, only the walker erased ([0..39 x ≤11], [12..25 x ≤16] + legs) → the crest curl right of the walker (rows 14-17, x 27-31) kept.
- Ice Age icon: flakes (8.0,13.8,2.8) left, lowest (19.6,22.4,3.6); valley minis removed; conflict check = disc test (R+1.0).

## v8 round (2026-10-15, 7th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v8: SPLASH takes precedence (figure cut 1.6 px round it); figure LIFT 2 rows so the arms clear the splash; lower body = row 19 (crossed-legs width) repeated down; splash keeps only the OUTWARD sheets (150/136/160 + 46/32/20) so the dome top is clean.
- ⭐ Nimue icon v8: `_hands_px()` = Cleansing's reference hands rebuilt at icon res (silhouette BOX→thr, finger seams on the 3 densest 45° diagonals ≥3 apart, thumb/cuff seams = 1-px row maxima ≥40) — technique for any fine-lined art at 40x35 (thin seams alias to a grey checkerboard). Pasted at (20-w/2+2, 4).
- Flashfreeze v5: RING_TICKS 22 (hit 1 lands ~tick 38 as the 40-tick ring collapses), FFRING stretched to 1.25 s; script recognises earlier ring holds via RING_TICKS_PREV (24, 30).

## v9 round (2026-10-15, 8th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v9: splash from the user's refs — base = `splash.jpg` rows 540+ (flare + ripple rings) 38x10 at the bottom, crown = `splash2.jpg` 32x12 at row 18.6 with inner holes flood-filled; no lower-body extension (figure LIFT 2 ends at its crossed legs); splash still cuts the figure (1.6 px).
- Flashfreeze ring v3: frost_ring 24 frames → DualDF 2252-2275 (2190-2209 unused), RING_TICKS 30 (PREV 24, 22), FFRING 1.5 s.
- Nimue icon v9: user rejected the pixel `_hands_px` (kept in the file, unused) — hands now built EXACTLY like glyph_cleansing (ref webp, seams MaxFilter 5, 27*S LANCZOS, halo) pasted 1:1 centred (20, 17.6). Lesson: re-sampling a finished glyph (crop + NEAREST rescale) jags fine lines; rebuild from source at the target size.
- DualDF next free 2276.

## v10 round (2026-10-15, 9th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v10: LIFT 0; lower body filled per column down to (smoothed ±1.5 px) splash top − 1.2 px.
- Flashfreeze: RING_TICKS 24, CUE_EARLY 5; script recognises older builds via RING_TICKS_PREV (24,22,30) × CUE_EARLY_PREV (3,).
- Nimue icon v10: hands placed by ink centroid at (20, 17).

## v11 round (2026-10-15, 10th feedback) — APPLIED, VEH clean, untested in game
- Misty Step icon v11: torso fill limited to x 13-27, figure cleared beside the torso below row 19 (no crossed-leg stubs).
- FFRING v6: all layers end at 1.35 s with a 0.3 s fade (fades under the first hit sound ~1.17 s).
- Nimue icon v11: sleeves masked off the reference (polygon below the wrists) before building; scale kept from the full (sleeved) height.
- Misty Step icon v12: below the arms (row ≥18) only x 15-24 kept; torso bottom smoothed over ±4 px of the crown top (flat clean edge).
- Misty Step icon v13 (user: cutoff too straight): torso bottom follows the crown top closely (smoothing k 0.6 px, gap 1.2 px).
