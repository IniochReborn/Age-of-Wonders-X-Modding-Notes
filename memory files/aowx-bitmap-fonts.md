---
name: aowx-bitmap-fonts
description: "Structure of the 13 Int\\Fonts glyph ILBs - shadow rule, accent-reuse chains, compacted-id quirk, per-font indices/palettes, usage counts - and the applied Cyrillic patch"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 7caffbff-32ec-402f-944f-c6ef4032cc30
  modified: 2026-08-25T22:01:26.426Z
---

The game renders ALL text from glyph ILBs in `Int\Fonts\`; a text byte is the
image id (id lookup, NOT frame position - proven by the ` 0x60 gap: positional
lookup would misalign everything above backtick). Facts established 2026-08-25:

**Families and derivation chains** (what feeds what):
- `Age8` (11px cell, baseline row 7, caps r0-7, x-height r2-7) → `Age8s`
- `Age10` (12px cell, baseline row 8, caps r0-8, x-height r3-8, rounded Є-style
  E/C) → `Age10s`; its glyphs are ALSO retail's accent art for `Age10tb` and
  `Age10LB` (mask-identical, palette 1)
- `Age10b` (bold, 2px strokes) → `Age10bs`; bs glyphs are retail's accent art
  for `Age16s` (mask-identical, pal 1, 12px tall next to 28px Latin - retail
  itself shipped small accents there)
- `Age15WhIn` == `Age15WhGr` part1 exactly; WhGr part0 (bmShadow layer) =
  part1 color-INVERTED (254-v) shifted down 1 row; `Age15BlBr` = recolor of the
  same letterforms. One 18px grayscale art set covers the whole trio.
- `Age14G` = 22px gold beveled title font, ids 33..124 only, RLESprite16.

**Shadow rule** for the "s" fonts: shadow = glyph shifted DOWN 1 row, drawn
where no glyph pixel sits (verified on I L o .; retail hand-tweaked a few
complex glyphs like A, imperceptible). Indices: Age8 g=1; Age8s g=1 s=0
transp=2; Age10/tb/LB g=1 transp=0; Age10s g=2 s=1; Age10b g=1; Age10bs g=2
s=0 transp=1; Age16s accents g=2 s=0 transp=1 pal=1. 8-bit palettes are tiny
standard sets: (48,32,32) (160,0,0) red glyph, (160,160,240), (240,240,240),
black - the engine recolors at runtime.

**Compacted-id quirk**: Age10tb, Age10LB, Age16s store their 64 accent glyphs
at CONTIGUOUS ids 0xA1..0xE0 instead of Latin-1 ids - so real accent bytes
(0xC4 etc.) fetch the WRONG glyph in those three fonts. Retail bug, ships that
way; irrelevant for Cyrillic since we claim only never-used bytes.

**Usage — count FontModule references, not filename strings.** AoWx.exe has a
`TFontModule` DFM (file ~0xDF288) defining named modules -> ILBs: Age8/8s/10/
10s/10b/10bs/10LB/16s plus `Sessis14G`->Age14G, `AoW15WhiteGrey`->Age15WhGr,
`AoW15BlackBrown`->Age15BlBr (Age10tb is defined privately inside TGamePlayDlg's
DFM). Counting `FontModule.<name>` usages: **AoW15WhiteGrey 132 usages across
nearly every window** (MultiWindow 21, WorldMap 12, CityScreen 10 ...),
AoW15BlackBrown 23 (SpellBook 10, HelpWindow, TutorialWindow), Sessis14G 1
(TArmyEventDlg), Age16s 1 (TTitleScene copyright label). The filename-string
counts (Age10 386 / Age8 300 / Age10s 156 / Age8s 117 ...) are SetGText-style
code references. Age15WhIn has no module - reachable only as art.

**Main menu**: TTitleWindow draws its items in CODE (owner-draw
TitleWinDrawSurface panels, DFM has no labels), labels come from ResStr
resourcestrings (Tutorial/Options/Load Game/Continue/Exit). A byte with no
glyph in the drawing font renders as NOTHING (confirmed in-game: Cyrillic
test label showed a blank Tutorial button while only the 8-bit fonts were
patched - the menu draws with an Age15 font).

**Applied 2026-08-25**: `patch scripts\patch_fonts_cyrillic.py` (dry-run /
--apply / --revert, backup `backup\Fonts.bak_cyrillic`) paints the 66 Cyrillic
glyphs at the [[mld-localisation]] aowx-ru byte ids (А=0x80 .. я=0xE3) into
the nine text fonts: hand-drawn art for Age8/Age10/Age10b (~44 originals per
family embedded as text grids in the script), copies (А=A, Ё=Ë, ё=ë...) and
mirrors (И←N, Я←R) taken from each font's own retail glyphs, shadows derived
by the rule above, tb/LB/16s fed the same art retail used for their accents.
Replaces the never-referenced accent frames (15 in first-group fonts, 36 in
compacted ones), adds the rest, keeps images sorted by id; post-write verify
decodes every glyph back and asserts untouched frames identical.
**Age15 trio also covered (same script, second pass same day)**: one 18px set
COMPOSED in code from Age15WhIn's own antialiased Latin art - copies/mirrors
plus piece surgery (Ж=X+I stem, Ч=H minus lower-left stem, Ь=B minus top
bowl, Л=vflip(V), П=vflip(U), Д=Λ+z-bar+feet, б='6', п='n', д='g'
italic-form, ь=b minus ascender stub, я=mirror(p)+x-leg, breve=vflipped Û
hat...). WhIn gets it raw, BlBr recolored via a majority-vote color map
learned from retail WhIn/BlBr pairs, WhGr as composite shadow (254-v
inverted, down 1 row) + glyph. Encoded as raw Sprite16 with 565 quantization
and transp-key nudge. The composer only reads Latin donors, so the whole
script is idempotent on patched files. **Still pending: Age14G** (1 usage,
TArmyEventDlg) - gold beveled 22px, own composition pass someday.
Known soft spots to revisit at 18px: lowercase д = italic g-form,
и = mirror(u), в = ь+waist-bar - readable but improvable.

`patch scripts\test_cyrillic_ingame.py` toggles main-menu labels
(ResStr.mld English column: Options→Опции, Tutorial→Абвгдеёжз) to smoke-test
the engine actually drawing the new byte values; backup
`backup\Dict.bak_cyrtest`. Note "Options" is NOT on the main menu - only the
Tutorial label shows there. Proof renders in the session scratchpad
(`font_out\proof_from_disk.png`, `age15_proof.png`).

**STATUS 2026-08-26: Cyrillic glyphs reverted back out of the fonts** (verified: Age10.ILB has no glyphs at 0x80 / 0xAB-0xB2) as part of removing Russian from the game. The structure facts (shadow rule, accent-reuse chains, compacted-id quirk) remain valid; Age15/Age14G Cyrillic work is cancelled, not pending.
