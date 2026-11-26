---
name: cyclops-unit-gfx
description: "2026-11-07 new Cyclops unit sprites, first pass = preview PNGs only (troll base scaled 1.15 to Giant size, flesh/stone skin, one eye); no game files written; awaiting user pick"
metadata:
  node_type: memory
  type: project
  originSessionId: 64f9d834-ce56-42d3-b058-494a867c0e87
  modified: 2026-11-07T22:42:48.828Z
---

**User request (11/07):** a new Cyclops unit, comparable in size to the Giant, Troll shape as inspiration. The user said **NO club** ("cyclops should not have a giant's club").

`patch scripts/build_cyclops_gfx_v1.py` (preview only): writes `<out>/frames/<id>.png` and preview sheets; `CYC_SKIN=flesh|stone`.
- Base: `Images\UNITS\Gbn\troll.ILB` (72 frames 64x64; ids d*100+f, d=1..6 direction, f=1..12). Front-facing directions are 1/2/6; 3/4/5 face away.
- Troll and Giant share the 82-colour unit palette. The Giant's skin shadows, hair and club share colours, so a palette swap was impossible there.
- Troll pixel classes:
  - green hues, yellow-grey highlights (h42-62) and purple-grey edges (h>=280/<10) = skin
  - saturated browns = leather
  - neutral grey = hair/outline
- Recolour: skin mapped by luminance onto a ramp; scalp in the top 30% made bald.
- Scale 1.15 about the feet (premultiplied bicubic, alpha threshold 110).
- Eye: drawn after scaling, 3 px under the hair band, on front directions only.

Known nits: the eye lands on the body in the death frame (x12); the dark hair band still shows on front views.

Next (once the look is approved):
- encode into an ILB on the unit palette (`ilb.encode_image`)
- pick a unit slot
- Unitres/Unitgfx records, the same way as the Phoenix (`build_phoenix_unit_v1.py`, see [[lifefire-spells]])
- portrait in `FACES`, corpse

**v1 REJECTED by the user:** "it looks terrible, like a janky recolor with a poorly drawn eye. maybe just restart from scratch". Don't recolour existing units for new creature types.

**v2 = `patch scripts/render_cyclops_v2.py`:** a CPU ray-marcher (numpy SDFs; no Blender or 3D libs on this PC). The model is smooth-union primitives on an FK skeleton:
- short legs, belly, chest with a back hump, long arms with fists
- forward head with ONE eye (white / amber iris / pupil), brow ridge, horn, ears, mouth groove
- ragged fur skirt and belt

Render settings: ortho camera at 38°, light (-0.70,0.62,0.30), AO, 4x4 supersampling → 64x64 hard alpha, 1-px darkened edge, PX_PER_UNIT 16.5, feet at (32,53).

Env vars: CYC_HIRES=1 (writes hires_<id>.png), CYC_SS. Full 72-frame render takes about 1.7 min.

⭐ Unit sheet layout (from the troll Unitgfx tag-5, 31 sequences):
- stand = frame 9; walk = 1-8; attack = 10-11; frame 12 = single-frame sequence (hit)
- sequence direction order 4,3,2,1,6,5
- offsets dx -16, dy -24
- shadows = USHADOW.ILB, corpse = DEADUNIT ids 100/101
- direction d: 1 front, 2 front-right, 3 back-right, 4 back, 5 back-left, 6 front-left (yaw 60*(d-1))

**ILB written 11/07:** `Images\UNITS\Monsters\CYCLOPS.ILB` by `patch scripts/build_cyclops_ilb_v1.py <frames dir>`.
- Built on the troll.ILB template: type-2 8-bit records, key index 0.
- Own palette: 200 median-cut bulk colours + 55 for badly matched pixels. A single median cut erased the eye and horn.
- Round-trip verified.
- NOT referenced by Unitgfx yet. It is a new file: the release zip must `--add` it.
- Eye: forced bright (shade >= 0.95) with radius 0.135, so it reads at 64 px.

**v3 (11/07)** `patch scripts/render_cyclops_v3.py`. User feedback on v2: "looks off ... texture/color/style ... too hunched over and blobby", plus "needs a corpse gfx too".
- Upright pose: lean 0.12 standing, 0.20 walking.
- Defined anatomy. Blend groups: limbs k 0.05; torso grp4 k 0.16 (tight blends made Michelin-man ridges); muscles grp5 k 0.09.
- Skin shading mapped onto the warm 7-step SKIN_RAMP, game style.
- White-noise grain on 120/unit cells.
- PX_PER_UNIT 18.5.
- `CYC_CORPSE=1` renders two 62x62 corpses (A on its back, B face down): 110 px canvas, then cropped around the body bbox.
- CYCLOPS.ILB rebuilt from the v3 frames.

Corpses are NOT in DeadUnit.ILB yet:
- type-22 16-bit records, 62x62
- troll ids 100/101; last used id 324, so the next free are 325/326
- see build_phoenix_corpse_v1.py

**v4 (11/07)** `patch scripts/render_cyclops_v4.py`. User: corpses must be FLATTENED like vanilla; "still looks off ... more vanilla style?"; reference art = bearded, long-haired one-eyed giant with a shaggy fringe loincloth and grimy skin.
- Hair: 48 two-segment strands plus a "cap" shell (FACE_CUT hairline).
- Beard: 34 strands.
- Unibrow (sprites); no horn or ears.
- Fringe: 44 strands round a short skirt.
- Speckled earthy SKIN_RAMP.
- Corpses: ELEV 75, CORPSE_SCALE 0.8, legsplay. They now match vanilla corpse size and flatness.
- CYC_PORTRAIT=1 → portrait.png, 103x128: close-up face detail (socket, nose, cheeks, brow tufts, open mouth + teeth), cave background, painterly pass. It is still cartoonish next to the vanilla painted portraits.
- `build_cyclops_ilb_v1.py`: CYC_PAL=vanilla keeps the troll/vanilla unit palette (worst error 24, looks the same). CYCLOPS.ILB in the game folder = the v4 vanilla-palette build.
- The full v4 render takes about 5 min (strands).

**v5 (11/07)** `render_cyclops_v5.py`. User on v4: "back looks too smooth", "clothes/cloth looks janky", "portrait is bad, make it based on the portraits i sent you", "corpse looks too much like T-pose ... flatter and more mangled".
- Back: scapulae, lats, smooth-carve spine groove (grp 6); skin bump mapping (vnoise, BUMP_A 0.42).
- Loincloth: "kilt" SDF (fold ridges, torn hem, open shell) plus front/back flaps; strand fringe removed. ⚠ The v4 skirt SDF had overwritten `p` in place, breaking every primitive after it. Fixed.
- Corpses: crumpled poses, ELEV 86, FLAT lighting 0.65.
- CYCLOPS.ILB in the game folder = v5, vanilla palette.
- Portrait = `build_cyclops_portrait_v1.py <images dir> <out>`: crops of the user's 3 reference images (scratch images 32/33/34.webp), mode-filter + grade to the vanilla look, 3 candidates. Awaiting the user's pick, then it goes into Add_UNITS.ILB (index 48).
- v5.1 (11/07): user approved the GFX overall.
  - Spine groove made subtle (r 0.018, carve k 0.07).
  - Corpse eye dulled (FLAT → eye shade ×0.45, no spec).
  - Portrait = ref 1 (32.webp) with the cave removed and the sky gloomy (`gloomy_sky_32`): blue-sky mask + hand masks for the rock and hero, inpainted with a normalised blur, slate-grey regrade, figure ×0.8. → scratch cyc5/portrait_final.png.
  - NEXT: DeadUnit 325/326 + Add_UNITS face 48 + unit slot/stats.
- Portrait v3 (11/07). User: "slightly too detailed" + "grey patches on his body".
  - Sky mask now keeps only candidates CONNECTED TO THE BORDER (geodesic grow), so skin highlights are no longer regraded.
  - Painterly: blur 0.7 → 180x224 → Mode(3) + Median(3) → 103x128 → unsharp(1, 55, 2). Blur 1.2/Mode(5) was too muddy.
- Portrait v4 (11/07). User: "make portrait look more like an oil painting".
  - oil(): Kuwahara r3 then r2 at 370x460; the unfiltered eye is blended back in (centre 175,130, ellipse 34x26, 80%); impasto relief from the luminance gradient + canvas weave.
  - The first try (r4+r2 at 260x324) was blotchy and lost the eye.
- **11/07 INSTALLED** (`patch scripts/install_cyclops_gfx_v1.py`, .bak_cyclops, --revert):
  - DeadUnit.ILB ids 325/326 "D_Cyclops.BMP": type 22 raw RGB565 inside the clip box, troll 100 as template.
  - FACES\Add_UNITS.ILB index 48 "Cyclops.bmp", 103x128.
  - Source art saved in `art import export\cyclops\` (corpse_A/B.png, portrait_final.png, frames\*.png).
  - Verified with the independent aowxlib decoder.
  - NOT yet referenced by any unit (Unitres/Unitgfx). Release zip: --add Images\UNITS\Monsters\CYCLOPS.ILB.
- Portrait v5 (11/07, user: 'too dark/heavily shaded'): figure x0.95 (was 0.80), gamma 0.86 + shadow lift 10 (was gamma 1.12); reinstalled in place (Add_UNITS index 48).
- **v6 eye (11/16)** `render_cyclops_v6.py`. User: "still looks a bit cartoony ... maybe make its eye less bright". The v5 eye was a forced-bright near-white ball (r 0.135, shade floor 0.95) = googly. v6: r 0.115 centred 0.188·hf (smaller r at the old centre gets BURIED in the head — keep the tip near 0.30), sclera (216,204,172), iris (92,50,18) at ca > 0.80, pupil > 0.92, shade floor 0.80, spec 0.30; a carved socket or floor ≤ 0.68 made the eye vanish at 64 px. Portrait/corpses untouched. CYCLOPS.ILB rebuilt (vanilla palette); old file `backup\CYCLOPS.ILB.bak_eye_v6`, old frames `art import export\cyclops\frames_v5\`. Awaiting user verdict.
