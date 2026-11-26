---
name: modding-tools-plan
description: "Goal and design constraints for the AoWx modding-tool suite — a Modding launcher replacing AoWSetup's Editor button, plus modernized ILB and campaign editors"
metadata: 
  node_type: memory
  type: project
  originSessionId: 66c54916-064a-4d90-b1cc-a7e1edb96f02
  modified: 2026-08-28T03:38:35.917Z
---

Stated 2026-08-24. End goal: **loosely combine** AoWDevX, AoWxBard, AoWxGen and modernized
replacements for AoWCGE and ILBMaker. They stay **separate programs**; the **"Editor" button in
AoWSetup is replaced with "Modding"**, which launches a hub with buttons for every modding tool.
Not one merged app.

**Why:** the user does not want a monolith — separate tools are easier to evolve, and the
launcher gives one discoverable entry point from the game's own setup program. The AoWSetup
button swap is well-understood territory (see [[aowsetup-internals]] for the VCL runtime-UI
machinery used for the Mouse tab).

**How to apply:** treat the ILB editor and campaign editor as independent deliverables sharing
only file-format libraries. Format work is already done and validated —
[[ilb-image-format]] and [[cam-campaign-format]], with working lossless codecs in
`old modding tools\research\` (`ilbcodec.py`, `camcodec.py`).

**Hard UX requirement for the ILB editor** (the user's main pain point with ILBMaker):
adding an image must NOT mean hand-setting a pile of parameters to match the other images of
that type. It needs one-click correct defaults. Design settled from evidence:
1. **"Match library" is the default.** New images inherit the dominant parameter set of the
   library being edited. Measured: **74.5% of the game's 689 ILBs use exactly one parameter set
   for every image**, and 85% are >=90% dominant — so inheriting is provably right almost always.
   This also beats a global preset where libraries legitimately differ: retail face libraries
   (H_Faces, L_Faces, R_Faces, UNITS) use blendMode **bmAlpha**, while the AoWx-added ones
   (x2022-x2025, Add_UNITS) use **bmUser** — same image type, different libraries.
2. **Named presets** for creating a library from scratch, mined from the retail data and stored
   in `old modding tools\research\ilb_presets.json` (unit_sprite, portrait_face, item_icon,
   structure_map, tactical_combat, spell_effect, race_set, mountain, scene_backdrop, ui_element)
   — each with the exact type/subtype/loadMode/drawMode/blendValue/clip_x plus canvas size.
3. **Escape hatches**: "copy settings from image #N", per-image override, and a warning when an
   image's settings differ from the rest of its library (the ~15% heterogeneous libraries such as
   General.ilb, Str_node.ILB and MSparks.ILB genuinely need per-image control).

**ILB editor also must** keep showing every parameter for every image and allow editing them —
the preset/match-library work is about making *adding* images painless, not about hiding the
parameters. Full manual control stays.

**Campaign editor requirements** (stated 2026-08-24, all driven by concrete AoWCGE pain):
- **Drag-and-drop node placement on the map.** AoWCGE only lets you retype X/Y by hand.
- **Visibility filters.** AoWCGE draws all nodes at once. Measured on the user's own
  `X\Campaign\Keepers.cam` (139 nodes on a fixed 640×480 backdrop): at a 32px icon **96% of
  nodes overlap another**, at 24px 83%, at 16px 65% — and overlapped nodes cannot be clicked,
  which is exactly the reported bug. No two nodes share an exact pixel, so the overlap is
  proximity; drag-and-drop plus filtering genuinely fixes it.
- **A branch/hierarchy tree panel** beside the map, also hosting the visibility toggles.
  Derivable from link field 0x15, but **it is a cyclic graph, not a tree**: their campaign has
  1 root, 0 leaves, 15 branch points, 2 merge points (scenario id 3 has 9 parents) and
  **8 cycles** (branch endings loop back to Keeper1). The view must be a tree *projection* with
  re-entry markers and cycle guards, not naive recursion.
- **Spellcheck with red underline** on scenario story text. Validated with `pyspellchecker`
  (pip, 160k words) over their 19,754-word campaign: 140 words flagged, dropping to ~67 after
  seeding a domain dictionary from campaign titles + recurring proper nouns. It found ~45 real
  typos. Two lessons: the default dictionary is **en-US** and the user writes **en-GB**
  (favour/honour/rumoured/realisation ⇒ needs en-GB or an accept-British option), and
  capitalisation is not a safe "it's a name" signal (Gabrirel, Huamans, Regrettaly, Swordmen
  were all real typos). Ship an "add to campaign dictionary" action.

**WHERE WE LEFT OFF (2026-08-25, second session).** All three tools build and self-test clean:
`dist\AoWxImg.exe` 40.9 MB, `dist\AoWxQuest.exe` 41.3 MB, `dist\AoWxInk.exe` 34.3 MB
(`python build_tools.py` builds all three). The 112-cell translation refresh and the
138-field language-table repair are both **applied** to the live `Dict\`, each with its own
backup and `--revert`. **Russian font glyphs are now painted and applied** for the nine text
fonts (~99% of game text) via `patch scripts\patch_fonts_cyrillic.py` — see
[[aowx-bitmap-fonts]] for the structure facts and derivation chains. Next up:
1. ~~In-game smoke test~~ **PASSED 2026-08-25**: user confirmed Cyrillic renders on the
   main menu (Tutorial → "Абвгдеёжз", covering byte 0x80 and the 0xAB-0xB2 range). The
   whole pipeline — aowx-ru bytes → glyph id → painted frame — works in the live game.
   Test label reverted; ResStr.mld back to normal.
2. ~~7th-language patch~~ **REMOVED 2026-08-26**: the user decided to drop Russian from
   the game entirely — all ru7 patches reverted, ru Dict columns removed, Cyrillic glyphs
   reverted out of the fonts (see [[mld-localisation]], [[aowx-7th-language-crash]]).
3. ~~Age14G Cyrillic~~ — cancelled with the Russian removal.
4. ~~Russian translation content~~ — cancelled with the Russian removal.
5. **The Modding launcher** replacing AoWSetup's Editor button (the original end goal).
Deferred niceties: ILB animation preview + drag-to-reorder + palette re-quantisation for
8-bit imports; an ILB picture picker shared with AoWxQuest; undo inside AoWxQuest text boxes.

**Translation policy (user decision, 2026-08-25) — do NOT bulk-overwrite.** For the non-English,
non-auto languages: if an existing translation is present but poor, **leave it alone**. Only
two things get touched:
1. **Gaps** — entries that are empty or still identical to English.
2. **Strings AoWx changed from vanilla.** The mod renamed things (e.g. "Dragon Slaying" ->
   "Monster Slaying"), so the foreign text still says the vanilla wording and is now simply
   wrong. Find these by diffing the current English against a vanilla baseline —
   `reference files\AoW 1.36` is stock, with `AoW+ 1.45` and `AoW Ziggurat` as further
   comparison points — then re-translate only those entries.
This keeps the diff small and reviewable instead of churning thousands of strings.

**Toolchain — decided and built (2026-08-24): Python 3.12 + PySide6 + PyInstaller.**
Source lives in `modding tools\`; `python build_tools.py` produces
`modding tools\dist\AoWxIlb.exe` and `AoWxCampaign.exe` (~41 MB each, onefile, windowed).
Both accept `--selftest`, which writes a pass/fail report to
`%TEMP%\aowx_selftest_{ilb,campaign}.txt` — use that to verify a frozen build, since
`--windowed` swallows stdout. Shared codecs are `modding tools\aowxlib\{ilb,cam,presets}.py`.
Licensing stays clean: both old tools are GPL and IlbMaker's IPLab dependency is
non-commercial-only, so everything was written from the format specs, not ported.

**AoWxBard GUI built 2026-08-26** (`modding tools\AoWxBard.py` + `aowxlib\wav2it.py`, built
via `build_tools.py bard`, deployed to X\Modding replacing the old console drop-target exe):
drag-drop/browse WAV/MP3 → .IT queue table with editable pregenerated in-game name (IT title,
25-char cap) and 8.3 file name; toggleable default-on "Volume balancer" (-12 dB RMS maximize)
and "AoW EQ" (+6 dB bass shelf) from the proven root wav2it.py engine (engine copied into
aowxlib with explicit-name convert_file(); root CLI script left untouched); conversion in a
QThread; Songs folder auto-detected by walking up to AoWx.exe; QSettings("AoWx","AoWxBard")
remembers output + browse dirs; decoration (four user iterations, final = themed backdrop): 1) leprechaun watermark —
OUT; 2) Inn.ILB celtic green/gold frame — disliked, OUT; 3) dark cracked stone wall
(Int\Scenes\LSetup.ILB image 0 LSBackg, border cropped → assets\bard_stone.png) — user
liked it but it wasn't the one they meant; 4) FINAL: "Background" combo in the TOOLBAR (top-right,
user moved it out of the export-options row), Moss/Stone, persisted (QSettings bg_theme,
default moss). Moss = what the user meant: **Int\GenericT.ilb image 0, TextBackGround.BMP
200x216** — the long flat green stones / cobblestone wall of the game's text windows,
seamless, TILED @25%; Stone = LSBackg scaled-to-cover @22%. Plus the carved celtic emblem
panel **Int\FCWin.ILB image 34 (FC-Party.BMP 179x101 — the game's own single-panel
crop, gold outline at the edge; don't hand-crop FC_MainT)** → assets\bard_emblem.png,
centred on the drop area under both themes, drop hint beneath it. Draw = **BLACK cutout fill of the panel
rect first, then the emblem at 55%** (user's spec: background must never show through
the panel; it stays subtle by fading toward black, not toward the window colour).
Layout rules from user: the export-options/output row sits ABOVE the textured area as
plain UI chrome (MossBack wraps only the table, attr Main.mossw); the Background combo
lives in the toolbar right after "Open Songs folder"; table columns are all
Interactive/draggable and **persisted** (QSettings col_widths saved on close; the user's
last widths ARE the default), first-run fallback proportions: Source = 50% of window,
In-game-name+File-name = ~75% of the rest (40%/35%), Status = remainder (stretch).
Window title is plain "AoWxBard". **Icon: the LEGACY black-dragon+CD bard_icon.ico
(reference files\bard_icon.ico copied verbatim to assets\aowxbard.ico) — the new-style
lyre icon was rejected; make_tool_icons.py must never regenerate aowxbard.ico.**
(FC_MainT as full backdrop was rejected — "not the right moss" — but its panel design
was liked.)
UI-art hunting notes: game window chrome pieces = Inn.ILB 72-79 (corners+strips) + 88
(gold triskele); ornate arch = CityWin GlassFr; triskele stone carvings = CityWin
I-Idle/Is-Upgrade; main-menu orbs = Int\Scenes\title.ilb; game-menu panels = Int\TitleM
GameMenuTop/Bott;
matching lyre icon added to make_tool_icons.py (assets\aowxbard.ico). MP3 needs ffmpeg
(PATH/ImageMagick — NOT bundled, and absent on the dev machine); WAV 16-bit works standalone.
audioop dependency = Python ≤3.12 only.

**AoWxGen GUI built 2026-08-26** (`modding tools\AoWxGen.py` + `aowxlib\mapgen.py`, built via
`build_tools.py gen`, deployed to X\Modding replacing the old console exe): Bard-style window —
left = the series of selections on plain chrome (mode combo: Random Map Batch / Custom RNG
Map / Image to Map; custom page = size/levels/players/inversion/landmass combos + 9 terrain
style checkboxes with the console's combine rules (classic exclusive, max 3, strength slider
1-9 enabled only when non-classic) ), right = monospace log pane on the MossBack backdrop with
the celtic emblem + hint when empty (custom mode shows the generator's ASCII preview; batch/
image suppress it like the console did). Engine = generate_map_v4.py UNCHANGED, bundled as
data with 9 pkls into `_MEIPASS\mapgen` + 4 template .hsm into `_MEIPASS\templates`
(aowxlib\mapgen.py = console launcher v6.5 plumbing minus console-isms; same seeds, env knobs
AOW_LEVELS/XLEVEL/LANDMASS/TPRESET/TSTRENGTH, xGen6/xImg6 naming, validation). Game root =
walk-up for Release\Release.hss, persisted (QSettings AoWx/AoWxGen), dialog fallback.
⚠ frozen-build gotchas: hidden-import "heapq" (v4 ships as DATA — PyInstaller never analyses
it) and GenLog must fill from QApplication.palette() (widget palette nulled by its transparent
stylesheet). `--selftest --selftest-gen` does a full S-map generation round-trip (works frozen,
S map ≈0.5 s). MossBack/emblem now shared in `aowxlib\gui.py` (Bard imports it too). Icon =
legacy aowxgen.ico (dragon+map) copied to assets, like Bard's.

**Tools are named AoWxImg (ILB editor, renamed from AoWxArt on 2026-08-25) and AoWxQuest
(campaign editor)** — `modding tools\AoWxImg.py` / `AoWxQuest.py`, built to
`dist\AoWxImg.exe` / `AoWxQuest.exe` (`python build_tools.py img|quest`). A third tool **AoWxInk** (localisation editor, replacing MLDEdit) was built 2026-08-25 —
`AoWxInk.py` + `aowxlib\mld.py` + `aowxlib\cyrillic.py`, built with `build_tools.py ink`.
It opens the whole Dict folder at once (all 8 dictionaries share a translation memory),
grid-edits every language column, has undo/redo, regex search, Untranslated/Empty filters,
TSV import-export, coverage stats, an Add-language dialog with a Russian preset, and
**repairs MLDEdit's damage on load**. 2026-08-26: gained a Quest-style **"Find typos" dock**
(Ctrl+T) — scans **the selected dictionary + selected language only** (user's laptop froze on
an all-books scan; the real culprit was `SpellChecker.candidates()` at seconds per word ×
~3300 flagged words — the raw scan is 0.12 s — so **suggestions are computed lazily on word
click**, never during the scan; keep it that way), markup stripping, Likely-typos vs
Probable-names split (capitalised 3+ occurrences, or word in the English source column of any
book = untranslated game term; that seed set is cached per folder), click-to-navigate,
Add-word persisting to `Dict\aowxink_accepted_words.json`; English accepts British spellings
via a suffix transform. Only languages present in the files AND with a bundled dictionary are
offered. Also 2026-08-26: QSettings("AoWx","AoWxInk") remembers the last opened Dict folder
(folder picker starts there) and the last TSV import/export directory. Saving is atomic: write temp, re-parse to prove it
loads, then replace, keeping a one-time `.bak_aowxink`. Filter defaults changed 2026-08-26 on user request: the "Show" filter (and every other
filter combo) now defaults to **Source (Native)**, NOT the first real language — the old
"default to German" behaviour read as a bug to the user. All filter choices (Show language,
search column, typo language, hidden columns) now **persist while navigating between
dictionaries** until manually changed; only cb_mode already did. (Historical note: English as
a completeness-filter target reports nothing since that column is near-empty by design —
users pick a real language themselves now.)
Icons (remade AGAIN 2026-08-26, user request — the 08-25 flat-disc versions "looked weird"):
background is the AoWx.exe MAINICON 32px pixel dragon (extracted to `assets\aowx_dragon32.png`
+ `aowx_dragon.ico`), kept crisp (NEAREST at 32/64/128/256, LANCZOS at 16/24/48), with a
shaded high-res tool symbol placed slightly toward the BOTTOM-RIGHT (center 0.615,0.635 of
canvas, ~62% side, ~74% at ≤24px): AoWxImg=wooden palette+brush, AoWxInk=feather quill with
ink stroke, AoWxQuest=shaded globe. `make_tool_icons.py` now writes the ICO **by hand**
(per-size composed frames: BMP 32bpp+AND mask ≤128px, PNG at 256 — Pillow's ICO saver can't
do per-size frames) plus `assets\icons_preview.png`. Older icons kept as `*.ico.bak_cartoon`
(procedural) and `*.ico.bak_flatdisc` (08-25 versions). Rebuild exes to embed.

**Suite-wide theming pass 2026-08-27** (all five tools rebuilt + deployed to X\Modding):
`aowxlib\gui.py` now owns `draw_backdrop(p,w,h,theme,opacity)` (moss tiled 0.25 / stone
cover 0.22), `FAINT=0.10` ("barely visible" behind populated panes), `draw_hint_under`,
and `play_icon()` — a gold gradient triangle replacing SP_MediaPlay, which is near-invisible
on the user's dark theme (used by Bard Convert-all, Gen Generate, Quest Set-as-start).
House pattern: empty pane = backdrop at theme opacity + celtic emblem + hint; populated =
palette-base fill + FAINT backdrop. Applied to: Img library tree (translucent
AlternateBase rgba(128,128,128,30) keeps row striping) + preview pane; Ink grid; Quest
branch tree + prologue/epilogue SpellTextEdit; Gen's log is now fully transparent over its
MossBack when populated (Bard-style) and the Image-to-Map colour-legend text was removed.
Img/Ink/Quest gained the persisted toolbar "Background:" Moss/Stone combo (Img stores it in
its aowximg.json via get_opt/set_opt; Ink/Quest via QSettings bg_theme; Quest reads it
through the module-global BG dict since SpellTextEdit has no Main ref).
⚠ **Two Qt lessons**: (1) a stylesheet `background: transparent` on an item view/text edit
switches it to QStyleSheetStyle and the native scrollbar grooves render BLACK — use
palette transparency instead (Base=QColor(0,0,0,0), viewport autoFillBackground False);
(2) with a transparent Base, inline cell editors inherit it — Ink's InkTable installs an
_OpaqueEditors delegate that resets editor palettes. Bard/Gen's older stylesheet
transparency is left alone (user-approved, rarely scrolls).
Also 2026-08-27: **AoWxInk auto-opens the last Dict folder** at launch (QSettings
last_folder, argv dir still wins); **Quest bugfix** — the typo dock's checkbox had
overwritten `self.chk_names`, silently breaking the map's "Names beside markers" toggle;
dock checkbox renamed chk_typonames. build_tools.py now bundles
bard_moss/bard_stone/bard_emblem into img/quest/ink (they import aowxlib.gui).
**Second 2026-08-27 pass (user request): windows-chrome texture + theme pinning.**
(1) gui.py gained `pin_dark(app)` — `app.styleHints().setColorScheme(Qt.ColorScheme.Dark)`
right after QApplication in ALL FIVE tools' main(): the user's Windows theme is dark and
they want the tools to NEVER restyle when the OS theme flips (explicit setColorScheme
overrides platform changes; verified it keeps the exact current #1e1e1e dark palette).
(2) gui.py `paint_chrome(w,theme)` (window-fill + FAINT backdrop), `ChromeDialog`
(QDialog subclass, theme auto-found via parent chain's bg_theme attr) and `ChromePage`
(tab page that re-lays the FAINT texture OVER the style's opaque tab-pane fill — tab
panes otherwise mask the window texture; it deliberately does NOT fill, preserving the
pane shade). Applied to Ink (Main.paintEvent, PropagateDialog, AddLanguageDialog,
report()) and Quest (Main.paintEvent + `bg_theme` @property mirroring BG["theme"] so
ChromeDialog's parent-chain lookup works, ImagePicker, full-picture + campaign-check
dialogs, ChromePage for the General/Prologue/Epilogue tabs, tracked in
self._chrome_pages for theme-change repaints). Bard/Gen/Img only got pin_dark — their
backgrounds were not to be touched.
(3) **Title-bar red pinned** (user liked the tint their wallpaper's Mica blend gave the
caption): gui.py CAPTION_COLOR = COLORREF 0x001C1B2A (sampled #2a1b1c off a live window);
pin_dark also installs a `_CaptionPinner` app event filter that DwmSetWindowAttribute's
DWMWA_CAPTION_COLOR(35) onto every top-level Qt window on Show (native file dialogs stay
stock). ⚠ ctypes gotcha: pass the HWND as `wintypes.HWND`, not a bare int — bare ints go
as c_int and the 64-bit handle truncates, silently pinning nothing (HRESULT was never
checked in-app; verified S_OK + pixels in a test script instead).
(4) **Img's celtic emblem = click-to-open** (Bard's pattern): LibTree.mouseReleaseEvent
→ main.open() while lib is None; hint text now "Click to open an .ILB image library".
⚠ When probing a live tool window (screenshots/synthetic clicks): the user may be USING
the laptop — a run captured their browser and another caught a context menu they opened;
keep probes to the window rect, and prefer HRESULT/in-process checks over desktop grabs.
**Third 2026-08-27 pass: gradient caption + splashes + version label (all five tools).**
(1) Flat pinned caption replaced by a CUSTOM title bar: gui.py `GradientTitleBar`
(CAPTION_H=34; CAPTION_GRADIENT black #0d0d0d edges → red #3b1f21 middle — the Mica
look; painted icon+elided title, QToolButton min/max/close with drawn glyphs, dims when
inactive) on `CaptionedMainWindow(QMainWindow)`, installed via setMenuWidget. Native
frame eaten with WM_NCCALCSIZE (styles kept → drag/snap/dbl-click-max/shadow survive;
maximized inset = SM_CXSIZEFRAME+SM_CXPADDEDBORDER) + WM_NCHITTEST (borders, HTCAPTION
on the bar, HTCLIENT over its buttons via childAt) + DwmExtendFrameIntoClientArea 1px
top in showEvent for the shadow. All five Mains now subclass CaptionedMainWindow.
Dialogs still use the flat DWMWA_CAPTION_COLOR pin. CAPTION_COLOR/CAPTION_GRADIENT are
the knobs. **The laptop screen is 1920x1080 @150% (logical 1280x720)** — main windows
are bigger than the work area and get clamped at creation; harmless.
(2) **Splashes — REDONE same day (user: "no delays")**: now PyInstaller BOOTLOADER
splashes (`--splash`), NOT Qt splashes. build_tools.py bakes EDIMAGES\Splash_x*.BMP
per target at build time (**native 320x276 pixel size — the user rejected a 1.5x DPI
upscale, "original size like AoWDevX"**; missing file = built without splash, just a
note) — so **splash-art changes need a rebuild now**. Splash appears ~0.3 s after double-click (during onefile
extraction, before Python) and gui.close_splash() (pyi_splash.close(), no-op unframed)
dismisses it right before showMaximized() — measured: splash 0.3 s, maximized window
1.5 s (warm cache), zero gap. The earlier 2 s Qt-splash hold + show_splash/finish_splash/
_find_splash are REMOVED. Heavy loads (Ink's Dict auto-open, Img/Quest argv file) run
BEFORE close_splash so the window opens populated. All five tools now START MAXIMIZED
(showMaximized; CaptionedMainWindow's NCCALCSIZE maximized inset verified visually).
The Tcl/Tk splash adds ~2 MB per exe; `--exclude-module tkinter` coexists fine.
**Splash_xQuest.BMP added by user late 2026-08-27** (all five exist now);
Splash_xGen.BMP fixed by user same day ("Map Generator"), gen rebuilt with it.
New splash BMPs are NOT yet in the installer/release packaging.
**VERSION bumped to 1.01.0002** (gui.VERSION) 2026-08-27.

**THE MODDING LAUNCHER IS DONE (2026-08-27) — the original end goal.**
`modding tools\AoWxHub.py` (build_tools.py target "hub", in the default build list,
no splash, icon assets\aowx_dragon.ico, deployed X\Modding\AoWxHub.exe 34.7 MB):
borderless **398x449** window — ⚠ AoWSetup home's TRUE runtime size: FormCreate ends
with SetClientWidth(398)/SetClientHeight(449) @VA 0x468DC7 (the DFM's 420x525 is the
INSTALL-mode layout; a 420x525 hub read as "wrong size" to the user). Hub runs
**DPI-UNAWARE with the GDI font engine** (`QT_QPA_PLATFORM=windows:dpiawareness=0:
fontengine=gdi`, options are COLON-separated — comma errors out) so Windows
bitmap-stretches it exactly like DPI-unaware AoWSetup (both 597x674 physical @150%)
and the genuine bitmap "MS Sans Serif" renders like the home buttons. Hub also
FindWindowW("TLoaderForm") at startup and moves itself to AoWSetup's position
(AoWSetup lingers 4 s after launching it). Button order: AoWDevX first, then the
AoWx tools ALPHABETICAL (Bard/Gen/Img/Ink/Quest — user request). v4 layout: art rows
0..156 at (0,0), divider 156..167, six 36px tool bars x=14 w=370 y=171+i*39 (name
10pt bold + desc 8pt bold MS Sans Serif), Exit 22px @407, bottom frame 437..449.
Background
assets\aowxhub_bg.png composed by `patch scripts\make_hub_background.py` from
AoWSetup.exe's own home BMP (DFM @file 0x7eda3, 398x450): art cut JUST ABOVE
JULIA'S HEAD (hair top = BMP row ~162, cut at 156 — user request), then SEVEN
FULL-WIDTH stone bars synthesised seamlessly from one home slab's texture
(slab_bar(): bevel ends + mirrored face tiling, face rows MIRROR-TILED
vertically for taller bars — stretching smears). SlabButton = custom-painted:
BOLD TOOL NAME + the tool's SPLASH-IMAGE DESCRIPTION under it, both bold like
the home buttons ("Editor/Music Tool/Map Generator/Image Tool/Text Editor/
Campaign Editor for Age of Wonders X"). Design history: v1 8-small-slab grid
rejected ("full width + descriptions"); v2 hard to read; v3 (420x525) wrong
size; v4 sizing = current. Bottom bar = **"Back"** (v5, replaced Exit):
go_back() relaunches AoWSetup via ShellExecuteW "open" (NOT Popen — AoWSetup
needs elevation, Popen dies WinError 740; the UAC prompt shows) and closes the
hub only when ret>32 (stays open if the user cancels the prompt). Version
label REMOVED on user request (Esc still quick-closes the hub). game_root() walks up to
AoWSetup.exe; tools launched from <root>\X\Modding, AoWDevX from root. Draggable,
Esc closes; hub STAYS OPEN after launching a tool (deliberate — multi-launch),
while AoWSetup still closes after opening the hub (kept its Sleep+Close).
AoWSetup side: `patch scripts\build_aowsetup_modding_button.py` (applied,
.bak_xhub) — see [[aowsetup-internals]] for the .xhub section details.
Installer TODO: ship AoWxHub.exe with the other X\Modding tools + patched
AoWSetup.exe + Dict\AoWSetup.mld ("Editor" row translations → "Modding",
.bak_xhub backup; Original text must stay "Editor" — it's the Multilizer key).
⚠ A QSplashScreen's NATIVE window title = applicationName ("AoWxImg") — window-hunting
scripts must filter it out (check WS_THICKFRAME) or they grab the splash and see it
"destroyed" 2 s later (this masqueraded as a window-recreation bug for a while).
⚠ And the mirror trap: watcher scripts that stop at first "main seen" get fooled by
ORPHANED tool windows left over from earlier probe kills — one "frozen splash never
shows" scare was entirely that (in-process tracing proved find→load→show all fine;
onefile extraction delays the splash to ~4-5 s after launch). Kill orphan AoWx* exes
before probing. AoWxImg --selftest now also reports the resolved splash path + load.
(3) **"Version 1.01.0001"** QLabel (color #888) after each tool's Background combo;
gui.VERSION is the single source.
(4) Latent AoWxGen bug fixed: style_toggled fired by the ctor's setChecked(True) before
sl_str existed → traceback on every launch (invisible in windowed exe); now guarded.

**Installer** (`patch scripts\installer\AoWxInstaller.iss`, 2026-08-25): now deletes stale
modding-tool copies from the MAIN folder on update — the old dot-prefixed `.AoWxGen.exe`/
`.AoWxBard.exe` (shipped through 1.37.406) and any unprefixed `AoWx{Gen,Bard,Img,Ink,Quest}.exe`
— so only the `X\Modding\` copies remain (same DeleteFile block as the retired launcher/scroll).

**No "resize"/Make step exists in AoWxArt** — unlike ILB Maker, whose Create-ilb button stayed
greyed until Make ran. Pictures encode at import time and untouched records keep their original
bytes, so open→edit→save works and an untouched library saves byte-identically. Only caveat:
changing an image's *type* leaves the old pixel encoding, so that slot needs Re-import.

**The user's campaign uses 8 "counter action" records as branch ENDINGS.** They carry no music
field (so the format's type rule classifies them as counter actions) and no scenario names them
as its counter action, but 8 scenarios point their *next mission* at them — they are where each
storyline stops. Labelling them "unlinked counter actions" was wrong and confused the user.
Also genuinely broken in that campaign: scenarios **#65 → CA #66** and **#79 → CA #80** are
dangling references, 8 scenarios have no counter action, and CA **#81** is truly unreferenced.

**Campaign editor v2 additions (2026-08-24):** book-page picture preview + visual
thumbnail picker (book art lives in `<root>\Int\Scenes`, auto-detected from the .cam path);
"Find typos" dock listing every suspect word with click-to-navigate (selects the record,
opens the chapter tab and page, highlights the word); snapshot-based undo/redo (Ctrl+Z/Y,
60 steps, typing coalesced into one step via a burst key + 1.2 s timer).
Typo list splits **"Likely typos"** from **"Probably names"** — a capitalised word used 3+
times is a character/place name, which drops the user's campaign from 82 undifferentiated
flags to 67 likely typos with 15 names set aside.

**Gotchas hit while building, worth not rediscovering:**
- Story text is stored **CRLF** but a QTextEdit works in **LF**. Regex offsets computed on the
  raw string land off-by-one-per-line-break when used as document positions — normalise before
  computing, and convert back to CRLF on save.
- `QImage` must be imported explicitly in each module; a missing import inside a `try/except`
  silently yielded "no picture" instead of an error.
- Per-pixel `QImage.setPixelColor` is far too slow for 272×372 book art — build a raw RGBA
  `bytearray` and use `QImage(buf, w, h, w*4, Format_RGBA8888).copy()`.
- Campaign book pages reference pictures by **image id**, which is usually but not always the
  position in the ILB — match on id first, fall back to position.
- Qt's `offscreen` platform has no fonts — screenshots render text as empty boxes unless
  `QT_QPA_FONTDIR=C:\Windows\Fonts` is set. Not an app bug.
- In a PyInstaller bundle, assets are under `sys._MEIPASS`, not `__file__`'s directory.
- `pyspellchecker` needs `--collect-data spellchecker` or its dictionary is missing at runtime.
