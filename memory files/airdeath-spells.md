---
name: airdeath-spells
description: Air/Death dual-sphere spells (pair 14, ids 344-347) - Banshee Gale / Suffocate / Borrow Time / Summon Succubus; applied 2026-10-15, untested
metadata:
  type: project
---
Air/Death = sphere pair 14; its id range 340-347 is shared — 340-343 were taken by Water/Death ([[waterdeath-spells]]), so Air/Death = 344-347. Icons CLOUDS Air 0 → Death 20. Sounds prefix DUALAD_. All APPLIED 2026-10-15, VEH startup clean, untested in game.

- **344 Banshee Gale** (T1, 4 mana, 50 RP): TWindsOfFury clone (vanilla id 0x7E, pfs 136, TC class 0x2F; DONOR added). `patch_banshee_v1.py`: 19-hex AoE around the target UNIT (needs a unit target; caster excluded, friends hit too), one strike per unit, push Random(18)+1 = 1-2 hexes (Winds Random(37)+1 = up to 3), landing hexes reserved per cast; Panicked 0x6C rolled Chance(6−RES) on dmg>0 (skips Fearless 0x43 / Lionheart 0xB1 / machines / already panicked) via a spare bit in the CA effects field (MP-safe). Caves TCPCK 0x43F800–0x43FB00 + DATA 0x46B870–0x46B8D8, AoWEPACK 0x55866800–0x55866A00. 19-hex preview: patch_tc_spell_alias SITE_ALIAS 0x42827A {344: 0x7C}. Art slot 0 = banshee_wisp DualDF 2300-2302 (trail particle); cue 0 DUALAD_BANSHEE (per strike, short), cue 1 DUALAD_BANSHEEHIT (landing).
- **345 Suffocate** (T2, 4, 90): TVaporize clone class 7, ATK 8/DMG 1/Death 0x20 (damage type my choice — spec didn't say)/5 strikes/range 6. Art suffocate_coil DualDF 2276-2283 (8 frames f18=0, peaks on the hit frame). DUALAD_SUFFOCATE (cast) + DUALAD_SUFFHIT (per hit).
- **346 Borrow Time** (T3, 6, 150): TRemedy donor (pfs 45). New ability **0xBB Borrowed Time** (TDecayAbility instance, combat only; Ability.pfs record 197 via patch_borrowtime_ability_pfs_v1.py). `patch_borrowtime_v1.py` (AoWEPACK 0x55838000–0x55838400): lethal hit → stays at 1 HP (0 HP would div-by-zero the AI's DVtoDEV); state byte [data+0xC] 0/1/2/3; dies at the start of the first OTHER player's turn after its own next turn (NewCombatTurn VMT+0xF8), or at combat end (CombatDone VMT+0xFC). Healed doomed units still die. Cast hooks chained in front of Martyr's caves → ⚠ patch_martyr_cleansing_v1.py dry-run ABORT is expected; revert Borrow Time first. Ceilings (tcablist + banner) LADDER now include 0xBB, bound 0xBC. Art borrow_hourglass DualDF 2284-2299 (16 fr f18=2 f20=11, -32/-50). DUALAD_BORROWTIME.
- **347 Summon Succubus** (T4, 50, 250, upkeep 8): TSummonMermaid clone, unit 229 (found via Unitres.pfs tag 0xA/0xB names).
- DualDF next free 2303. Ability next free 0xBC.
- ⚠ Banshee fork noticed (pre-existing): Sandstorm's unit list at 0x46BF68 (8 B/entry) overruns the Hurl Boulder/Flashfreeze wait dwords 0x46BFE0/E4 when ≥16 units are in its area — reported to the user, not fixed.

## v2 round (2026-10-15, user feedback) — APPLIED, VEH clean, untested in game
- Icons: Banshee v2 = procedural curl-cloud (after banshee.jpg; its hatching is noise when traced) with a wailing skull lead lobe. Suffocate v2 = grimacing head, hands crossed at the throat, torso, breath wisps (after suffocate.png). Succubus v2 = traced succubus.jpg → succubus_user_mask.png (x1.32 wider).
- Suffocate: Physical 0x80 only; one long cue DUALAD_SUFFOCATE (1.26 s: suck 0.85 s + gasps), no cue 1 (SUFFHIT removed via OLD_FILES); gfx v2 = 5 breath streams pulled up/out of the target. `patch_airdeath_fix_v1.py` (AoWEPACK 0x55866A00–0x55866C00, TCPCK 0x43F600–0x43F800): 345 can't target machines (VMT+0x114==2) or undead (race 0x0B / ability 0x81) — click/cursor/AI/fast-combat/EX hooks chained in front of Blood Boil's (⚠ patch_bloodboil_v1 dry-run ABORT expected); Banshee BW hook 0x42BE07 skips kind-0x2F's per-strike cue-0 plays → cue 0 only once (caster's cast animation), cue 1 per landing.
- ⭐ Cue facts: cue 0 = once per cast at the caster's cast-anim frame 0 (0x421D45; NextStrike starts the anim only on strike 0). Class 7 effects play only cue 1 (landing). Kind 0x2F effects play cue 0 twice per strike + cue 1. Missing cue = safe (TSFXLibrary.Play returns nil). Banshee cast ≈ 50 + (N−1)×5 ticks.
- Banshee sfx v2 = Tornado + Windloop + slowed m_Death + 3 whistle wails + D_FemN2/D_FemN1 screams (3.0 s); hit = short wind+sub thud.
- Borrow Time v2 (patch_borrowtime_v1.py upgraded in place): unconditional death at the end of the caster's (= unit owner's) next turn (state 0→1 at own next turn start → kill at next other player's turn start), lethal blows held at 1 HP until then, combat end (win/lose/flee/auto — all via TCombat.Destroy→EndCombat→CombatDone) kills any 0xBB carrier. v1 bug: combat-end kill was only for "doomed" units. Name shows "Borrowed Time (1 turn left)" / "(last turn)" via a cave in front of Bloodbath's GetName jmp at 0x55764E5A (⚠ patch_bloodbath_v1 dry-run ABORT expected). Zone 710/1024 B. Art v2 = icon-like hourglass, sand bottom→top. Sfx v2 = slowing tick-tock (bell ticks), reversed deep bell, reversed hiss, shimmer, chime.

## v3 round (2026-10-15) — APPLIED, VEH clean, untested in game
- Banshee icon v3: banshee2.jpg wraith traced (banshee2_ink_full.png) + curl lobes trailing right; hood hollow found by flood-fill (outside→128, holes = 0) and filled as a skull (eyes + mouth).
- ⭐ Banshee vortex: `patch_tc_banshee_vortex_v1.py` (TCPCK 0x43FB00–0x43FD00, latch DATA 0x46B8E0) = gate in FRONT of the NextStrike chain (→ Flashfreeze 0x43B440 → Hurl Boulder → …); spawns one kind-0x26 driver at the AoE centre drawing slot 1 = banshee_vortex() DualDF 2323-2366 (44 fr f18=1: rise 0-7 / loop 8-19 / copy 20-31 / fade 32-43, 224x160 at -112/-92), holds the first throw until the gale has risen, loops while throws are in flight (tick steps back one 24-tick cycle), then fades. Slot 0 trail = 340 (DFnone blank). ⚠ patch_tc_flashfreeze_v1 and everything behind now dry-run ABORT/not ours — revert the vortex first.
- Sandstorm list capped at MAX_LIST 15 (patch_sandstorm_v1.py) — fixes the overrun into 0x46BFE0/E4.
- Suffocate icon v3 = vanilla-style two-tone silhouette (head back, forearms crossed to the throat, breath curls). gfx v3 = 16 pale motes drifting up/away (f18=1). sfx v3 = escalating gasps (reversed wind bursts + hiss + grunt), 1.4 s.
- Succubus wings v3: `make_succubus_wings.py` keeps the traced body+hair (body polygon) and redraws bat/dragon wings (arm bone, clawed wrist, 5 finger bones, scalloped membrane) → succubus_user_mask.png; feathered original = succubus_feather_mask.png.
- Borrow Time: sfx = 4 slow deep ticks (bell 640/520 Hz at 0/0.55/1.15/1.85 s) + reversed bell/hiss + chime at 2.2 s; gfx 20 frames → DualDF 2303-2322 (2284-2299 unused).
- Banshee sfx v3 = Tornado/Windloop slowed + low drone + D_FemN1/2 shrieks pitched up + a reversed echo + thin keening. DualDF next free 2367.

## v4 round (2026-10-16) — APPLIED, VEH clean, untested in game
- Banshee icon v4: wraith cut at row 19, robe continues as 3 tapered wind ribbons (dark-edged, back→front) winding into curls.
- Banshee vortex v2: ALPHA 258/80 black smoke puffs (8 % dark purple), same 44-frame layout.
- `patch_banshee_hop_v1.py` (TCPCK 0x43FD00–0x43FE00): CAM hook 0x40DC1F centres the view once (strike 0) on the AoE centre G_CX/G_CY; HOP hook 0x40DC3E = one ~20-point 40-px arc to the landing hex (vanilla Winds: 30-pt ±15 px shake + two random ±150/±100 swoops); still consumes the same 64 Random draws (MP-safe).
- Banshee sfx v4 = slowed Tornado/Windloop + Zu/WraithDeath ×0.78 + xHero_Death/scream4 ×0.82 + reversed WraithDeath echo + drone (pitched-up FemN shrieks = "mice squeaking" — avoid speeds > 1 for screams).
- ⭐ New synth `gasp:secs:strain` (formant-filtered breath noise, rising F1/F2, sharp cut, optional glottal-pulse strain). No real gasp/breath samples exist in Sfx. Suffocate sfx v4 = 6 gasps of rising strain + reversed MALEHIT1/2 + H_Rough2 heave (1.54 s).
- Suffocate icon v4 = LINE ART (profile head thrown back, clawing hand at the throat, 3 breath curls); gfx v4 = 18 motes pulled from inside the body with 5-step fading tails + leaving mist.
- Succubus v4: `make_succubus_wings.py` now = feathered trace with wing slits closed (Max/Min 13) + bat scallops cut along a line from the outer wing point to the bottom by the body (4 arcs, sag 16 px) + a dark gap following the real body/hair outline. (v3 bat redraw rejected.)
- Borrow Time sfx v4 = reversed bell + hiss + ONLY 4 ticks (bell 330/262/330/247 Hz + sub thump at 0/0.85/1.75/2.7 s); gfx f18=3 (80 ticks).

## v5 round (2026-10-16) — APPLIED, VEH clean, untested in game
- Banshee vortex v3: ~460 OPAQUE black particles (7 % dark purple, 1-3 px + short orbit trail), 75 % on 3 spiral arms, one shared spin speed (2 turns/cycle), ALPHA 258/75 with alpha strictly 0/255 — ⚠ soft per-pixel alpha in 258 mode dithers into "transparent dots" (user complaint); use opaque pixels + the global blend instead.
- Banshee sfx v5: + Kain/CHOIR2 slowed, sub swell, reversed m_Death; WraithDeath/scream4 louder + a second cry; DRIVE 2.6.
- Suffocate gfx v5: 16 frames f18=2 (48 ticks/strike), 96x96 at -48/-87, motes travel 48-66 px; DualDF 2367-2382 (2276-2283 unused). Cast ≈ 2.3 s. Sfx v5 = gasps + gags (short strained gasp synth) + rattle-synth gurgles + heaves + reversed grunts, 2.34 s, DRIVE 2.0.
- Borrow Time ticks = Events/Clock.WAV's tick (0.16 s) at speed 0.62/0.52 (tick/tock), at 0/0.98/2.0/3.1 s.
- Succubus icon REVERTED to the feathered trace (succubus_user_mask.png = succubus_feather_mask.png); make_succubus_wings.py now writes succubus_wings_v4_rejected.png only. DualDF next free 2383.

## v6 round (2026-10-16) — APPLIED, VEH clean, untested in game
- ⭐ Banshee vortex v4 = drawMode **1026 (MULTIPLY/dark)** on a WHITE field stamping vanilla Mind Decay's particle (EFFECTS\PARTICLE.ILB 15-17 = Mind Decay pfs key 116 slot 0, kind 4; white field + dark core/halo) 380× per frame (halo ×0.75, 8 % purple tint), blend 90 — this is the real "black glow" (no dither problems; multiply darkens smoothly).
- Banshee icon v5: robe cut at row 19 → 3 smooth Bezier strands (start inside the robe, taper, thin dark edges) each winding into its spiral curl.
- sfx builder: new FADE_OUT dict (whole-mix fade to silence; mix(..., swell_out)); Banshee 1.2 s (layers extended to 3.6 s), Suffocate 0.35 s. New synth `tick:ping:body:secs` (mechanical clock tick: 2 ms click + escapement ping + wooden body + second click 14 ms later) — Borrow Time ticks = tick 1500/520 & 1150/400 at 0/0.98/2.0/3.1 s.
- ⭐ `patch_tc_suffocate_v1.py` (gate TCPCK 0x43FE00, 212 B, FRONT of the NextStrike chain now: suffocate → vortex 0x43FB00 → Flashfreeze 0x43B440 → Hurl Boulder → …; wait dword DATA 0x46BFE8): GAP_TICKS 14 → hits at ~0.53/1.13/1.73/2.33/2.93 s; strike 0 spawns a kind-0x26 driver drawing slot 1 (96 ticks). ⚠ vortex dry-run asserts "unexpected gate chain 0x43fe00", flashfreeze & behind ABORT — expected; revert from the front.
- Suffocate art: slot 0 = suffocate_puff DualDF 2383-2390 (8 fr f18=1, 74x80 at -37/-71); slot 1 = suffocate_drain 2391-2422 (32 fr f18=2, 160x120 at -80/-70, ~8 sparse motes drifting OUTWARD sideways). 2276-2283 + 2367-2382 unused. Sfx v6 3.5 s: gag+gurgle+heave on each hit time, gasps between, long wheeze, fade 0.35.
- Suffocate icon v5 = vanilla icon 23's skull (crop 10,13–30,31, ×0.72) on a windpipe forking into two lobed lungs with branching airways.
- DualDF next free 2423.

## v7 round (2026-10-16) — APPLIED, VEH clean, untested in game
- Banshee vortex v5: particles now travel ONE full turn per 12-frame cycle (30°/frame; v4's 2 turns = 60°/frame read as a static shimmer), 4-step afterglow tail, stamps darkened (gamma 1.35), 230 particles. patch_tc_banshee_vortex_v1.py T = 3 (f18 2 → rise 24 / cycle 36 / fade 36 ticks); pipeline 344 slot 1 f18=2. Re-chain recipe used: revert patch_tc_suffocate (front) → vortex --apply (upgrades in place) → suffocate --apply.
- sfx builder: 8th layer value = SOURCE OFFSET (s) — slice a sample. Banshee 4.4 s (+ a last scream at 2.7, fade 1.5). Suffocate v7 = real voices: xHero_Death/aaa.wav reversed slices (= gasps in), Zig collection/MDEATH.wav slices on each hit (chokes), light rattles. Borrow Time v7 = Events/Clock.WAV tick (offset 0, "click") / tock (offset 0.19, speed 0.8, "clock") + synth tick bodies; anim f18 4 (100 ticks).
- Suffocate drain v2: motes on cubic curves feet (y 68) → head (~24) → bending outward ±52-66 px, wide soft glow.

## v8 round (2026-10-16) — APPLIED, VEH clean, untested in game
- Banshee icon v6 = the banshee2 wraith only (centred, skull in the hood), no gust.
- Banshee vortex v6: 84 frames (rise 12 / 24-frame revolution = 15°/frame / ×2 / fade 24) f18=1 → DualDF 2423-2506 (2323-2366 unused); patch_tc_banshee_vortex_v1.py R_FR,C_FR,T = 12,24,2 (re-chained: suffocate revert → vortex apply → suffocate apply).
- Suffocate: drain 48 frames f18=1 → 2507-2554; per-hit puff 16 frames f18=0 → 2555-2570 (2383-2422 unused). Sfx v8 = new synth `croak:rate:secs` (Grudge vocal fry: jittered 40-55 Hz glottal pulses through 'uh' formants 620/1180/2500) — uhhh(0.95 s) / uh / uh / uhhhh(1.15 s) / uh + faint reversed-cry inhales. Icon v6 = icon 23 skull ×0.85 on top + windpipe + two Catmull-Rom spline lungs with thin airways.
- Borrow Time: the 2nd/4th tick = the same Clock.WAV tick (offset 0) at speed 0.86 (slightly lower) + synth tick 1900/600.
- DualDF next free 2571.

## v9 round (2026-10-16) — APPLIED, VEH clean, untested
- Banshee icon v7 = NEW banshee.jpg (three hooded wraiths, frame cropped) traced → banshee3_user_mask.png. Sfx: + WraithDeath ×1.25 / ×0.55 and scream4 ×1.2 / ×0.6 layers (high + deep copies).
- Suffocate icon v7 = lungs.jpg traced (lungs_ink_full.png; airways thickened MaxFilter 5) in the bottom 26 rows + icon-23 skull ×0.62 on top. Sfx v9: reversed aaa.wav layers removed (the "AHH"), fast rattle-synth crackles ("crrkk", 80-95 Hz, ~0.2 s) added between croaks.
- Borrow Time ticks evenly spaced 0 / 0.98 / 1.96 / 2.94 s.
- `inspiration.jpg` (radiant halo round a face) is in art import export — not yet used/mentioned.

## v10 round (2026-10-16) — APPLIED, VEH clean, untested
- ⚠⭐ ICON OVERRIDE TRAP: build_dual_sphere_icons_v1.py imports `art import export/<icon key>.png` as a hand-edit OVERRIDE of the drawn glyph. The user's reference `suffocate.png` matched icon key "suffocate" → the game showed the reference photo for Suffocate for ~6 rounds while every redraw was ignored. Fixed by renaming the key to "suffocate_lungs". Only other collision: `harvest.png` (Oct 14, 639 B = a genuine hand-edit, kept). ALWAYS check `--apply` output for "imported …" lines and render the LIVE ILB image after icon work.
- Banshee icon v9: the tall wraith alone (flood-filled out of banshee.jpg, ×1.32 wide) → banshee1_user_mask.png, hood opened at its head (29.4, 3.4) with two dark eyes. Sfx v8: immediate gust + screams from 0.05 s, stacked high/deep copies, 5.6 s with a 3.0 s FADE_OUT; vortex fade curve ^0.55 (lingers).
- Suffocate sfx v10 = new synth `glide:<path>:s0:s1:secs` (sample with a linear speed glide) — Attack/Vapor.wav 0.55 → 1.35 over 3.6 s, fade 0.5. Nothing else.

## v11 round (2026-10-16) — APPLIED, VEH clean, untested
- Banshee icon v10: NEW banshee.jpg = 15 ghost silhouettes; each cut out by flood fill → ghost_r<row>c<col>.png; icon = 4 of them (r0c1, r1c2, r0c2, r1c4) evenly round a circle (R 9.6), rotated so heads follow the counter-clockwise spin.
- ⭐ Vortex v4 (patch_tc_banshee_vortex_v1.py): HOLD = (R+C)*T−6 = 66 ticks (first throw ~2.2 s, one revolution after the rise; step-back only after strike 0 launches → no deadlock); the gate plays cue 0 itself at spawn (Flashfreeze recipe) + 344 added to the castsnd exclusion list 0x43C900 (cue 0 used to start only when strike 0 launched = after the hold). Rise starts at 12 % size. Timeline N=6: throws 2.2-3.0 s, fade ends ~7.2 s. Sfx 7.6 s (screams at the throws/landings, choir repeated — CHOIR2 is only 2 s), FADE_OUT 3.5.
- Suffocate: icon lungs 21 rows + skull ×0.84; glide synth got an optional curve exponent (`glide:path:s0:s1:secs:pow`) — Vapor 0.55 → 1.6, pow 0.45 (rises fast early).

## v12 round (2026-10-16) — APPLIED, VEH clean, untested
- Banshee icon v11: NEWEST banshee.jpg (long-haired banshee crawling out of a grey shroud swirl) via `make_banshee_icon_mask.py` → banshee4_user_mask.png: whole figure as ink (v<205), black hair/body (v<70) merged (close 15) and outlined by a clear ring (dilate 11), main component only (flood from a hair pixel). (Cut-out variant banshee4b rejected by me as unreadable.)
- Vortex v5: after the last landing the tick jumps straight into FADE at the same phase (cycle A += 2*C*T, cycle B += C*T) — no extra revolution; fade art shrinks to 30 % (grow 0.3+0.7·v^0.8, keep v^0.7). v4 script copy in job tmp.
- Suffocate: GAP_TICKS 10 → hits 0.53/1.00/1.47/1.93/2.40 s (sound 3.6 s); sfx reverted to v10 (Vapor glide 0.55→1.35 linear). Icon: skull ×0.72 + a thick neck (5.2 px wide, 2 vertebra lines) down into the windpipe.
- Re-chain recipe when changing suffocate constants: revert suffocate with the OLD file first (no in-place upgrade), then edit, then vortex --apply, then suffocate --apply.

## v13 round (2026-10-16) — APPLIED, VEH clean, untested
- Banshee icon v12 = NEWEST banshee.jpg (brushed ink whirlwind) traced: inverted, v>145 strokes, crop (0,250)-(736,894), → banshee5_user_mask.png.
- ⭐ Vortex v6 smooth fade: art 3-FOLD SYMMETRIC (77 particles ×3 at 120°) so the image repeats every 8 frames (SYM_T = 16 ticks); fade section = 8 frames at full strength then thin+shrink over 16. Gate end-logic: tick := fade_t + ((tick − rise_t) AND (SYM_T−1)) → always enters the fade at the matching image AND full strength (v5 jumped to the same phase in the fade → could enter half-faded = "skipped frames"). v5 script copy in job tmp.
- Suffocate icon v7.4: + an X-ray torso outline (neck → shoulders → flanks, 0.95 px, kept 1.6 px clear of the existing art); nothing else changed.

## v14 round (2026-10-16) — APPLIED, VEH clean, untested
- Banshee icon v12.1: swirl crop widened (940 px square round the eye), shrunk to 92 % height, clipped to an inset oval (no edge contact).
- Vortex art v11: fade = 8 full frames, then 13 frames shrinking into the centre (grow 0.06+0.94·v^1.1) and thinning fast (keep v^2.6), then 3 frames of ONE particle paling 1.0/0.6/0.3, then gone. No script change.
- Suffocate icon v7.5: lungs 18 rows, skull ×0.60, a narrow (3.6 px) longer neck with vertebra lines every 1.5 px, torso outline re-fitted (shoulders y 14-18). Sfx v13: glide 0.55→1.5, curve 0.65, FADE_OUT 1.2 s.

## v15 round (2026-10-16) — APPLIED, VEH clean, untested
- Vortex v12 art (108 frames, DualDF 2571-2678; 2423-2506 unused): rise 36 = 12 growing at 1 turn/24 fr + 24 ACCELERATING to 2 turns/24 fr; loop + fade at the fast speed, phase tracked continuously (seamless); fade = 8 full frames, then shrink + thin + `dark` 0.25..1 (stamps lightened = more transparent), last 3 frames one particle 0.7/0.4/0.18. Script: R_FR 36, HOLD fixed 66 (first throw unchanged ~2.2 s, now mid spin-up; assert HOLD < (R+C)*T); SYM_T 16 still valid (fast-speed image period = 4 frames divides 8).
- Banshee icon v13: swirl ×1.10 + shear 0.14, oval-fenced, clear disc at the eye + vanilla SpellIcn 22 (= Pestilence, confirmed from its pfs record key 19) shrunk to 40 %.
- Suffocate icon reverted to v7.3 (no torso; skull ×0.72, lungs 21 rows, neck 5.2 px with 2 vertebrae).
- Suffocate icon v8 (2026-10-16): v7.3 + a SOLID ink torso (neck→shoulders→flanks polygon) with the lung tissue cut out (clear) so the airways stay as ink = X-ray negative. APPLIED.

**10/19 EDITOR AV:** AoWDevX map load → "Access violation at 5586E017 in AoWEPACK.dll, read of 0060EFE0" = patch_staticshield_listhide_v1's AoWEPACK filter cave reads the LISTING flag at absolute AoWx.exe .xbfs 0x60EFE0, unmapped in the editor process (intermittent). ⚠ lesson: DLL caves must never touch AoWx.exe absolute addresses without a host check (hex-grid cave 0x5581F800 technique). Fix in progress.
Fix APPLIED 10/19: `patch_dll_host_guard_v1.py` (`.bak_hostguard`; AoWEPACK 0x5581F200–0x5581F300, TCPCK 0x451C00–0x451D00 'HGD1'): host check = image base 0x400000 + SizeOfImage ≥ 0x20F000 + dword [0x4574AC]==0xA1D88B53; guards listhide L1/L2 (0x5586E017/0x5586E047), end-turn hotkey ET (0x55860014 reads [0x45A0CC]), TCPCK listhide writes T1/T0 (0x444410/0x44441D). AoWDevX SizeOfImage 0x13CC00 (maps to 0x53CC00) and imports AoWTCPCK too. Already guarded: 0x55815370, hex grid 0x5581F814, 0x55873C20/0x55874410 ('TSHK'). Revert before listhide/endturn_hotkey_light.
