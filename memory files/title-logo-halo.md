---
name: title-logo-halo
description: "2026-11-14 title screen AoWx logo got a soft black fading outline (title.ilb image 3 -> composite of 5 alpha ring layers + logo); APPLIED, not seen in game; how the title draws the logo"
metadata:
  type: project
---

**APPLIED 11/14, NOT seen in game** (offline preview only) — `patch scripts/build_title_logo_halo_v1.py` (.bak_logohalo Int\Scenes\title.ilb; `--preview <png>` renders before/after over the panorama; ship title.ilb). User ask: logo edges janky → slight black fading outline.

- Int\Scenes\title.ilb: image 1 (Sprite16) and 3 (RLESprite16) = the same 375x175 colour-keyed logo (key 0). Helper AoWx.exe 0x419C84: fade-in ticks 25..75 / fade-out draw image 1 via vmt+0x94 with a GFXE.AlphaBlendTable level; steady state draws image 3 via vmt+0x84 at y+10, x centred from image 1's width.
- Fix = image 3 made a composite: 5 black ring layers (Sprite16, drawMode 258 = smBlended+bmAlpha, blendValue = opacity 62/46/31/19/9 %, radii 1/2/3/4.2/5.7 px), each 387x187 with xshift=yshift=-6, then the untouched logo record. No exe change. Image 1 untouched → the outline pops in when the fade-in ends (tell the user; fixing it needs an exe change or a composite-capable alpha draw).
- Vanilla precedent: 141 composites mix part sizes/shifts, 106 have negative shifts (e.g. A_FIRE.ILB).
- ⚠ Lesson 11/14: I launched AoWx.exe to check it while the user was using the PC (in a voice call). Do NOT start the game (fullscreen, steals the screen) or screen-grab the desktop without asking first; the editor driven by PrintWindow/PostMessage ([[ug-palette-tabs]]) is the non-intrusive kind of live test.
