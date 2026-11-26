AoWx Modding Tools
==================
Five standalone Windows programs, no install and no Python needed:

    dist\AoWxImg.exe     image library (.ILB) editor   - replaces ILB Maker
    dist\AoWxQuest.exe   campaign (.CAM) editor        - replaces AoWCGE
    dist\AoWxInk.exe     localisation (.MLD) editor    - replaces MLDEdit
    dist\AoWxBard.exe    music converter (WAV/MP3->IT) - GUI for wav2it
    dist\AoWxGen.exe     random map generator          - GUI for the v6.5 engine

Single-file PyInstaller builds (34-41 MB). Run any of them with "--selftest"
to verify the build without opening a window; the report is written to
%TEMP%\aowx_selftest_{img,quest,ink,bard,gen}.txt. AoWxGen additionally
accepts "--selftest --selftest-gen" to prove a full generation round-trip.

AoWxGen: same three modes as the old console tool - Random Map Batch (two
maps of each size), Custom RNG Map (size / levels / players / terrain
inversion / landmass / up to 3 combinable terrain styles + strength), and
Image to Map (drop a picture on the window; one map per size). The engine is
the unchanged generate_map_v4 (bundled with its data and the four template
maps); finished maps are validated and land in Scenario\Custom with the seed
in the file name.

AoWxBard: drop WAV/MP3 files on the window (or click to browse). Each queued
row shows a pregenerated in-game name (the IT module title, max 25 chars) and
an 8.3-style output file name - both editable before converting. The two
AoW-tuned mastering steps are on by default and toggleable: "Volume balancer"
(-12 dB RMS soft-limited, matches the vanilla soundtrack) and "AoW EQ"
(+6 dB bass shelf below ~120 Hz). Output goes to the game's Songs folder
(auto-detected, changeable). 16-bit PCM WAV needs nothing; MP3 and other WAV
flavours are decoded through ffmpeg if it is installed.

Nothing here is derived from the GPL code of ILB Maker or AoWCGE. The file
formats were re-implemented from the published ILB specification plus our own
analysis of the retail data, so the licensing stays open.


-------------------------------------------------------------------------
DO I STILL NEED TO "RESIZE" AN ILB BEFORE SAVING?
-------------------------------------------------------------------------
No. That was an ILB Maker workflow: its "Create ilb" button stayed greyed out
until you pressed "Make", because Make was what actually generated the resized
bitmaps and quantised the 8-bit images. Any parameter change re-greyed it.

AoWxImg has no Make step. Pictures are encoded the moment you add or re-import
them, and images you have not touched keep their original bytes untouched. So
you open, edit, save, and it works.

Two things do still need care:
  * If you change an image's TYPE, the pixels already stored are still in the
    old encoding. Use "Re-import" on that slot to re-encode it. The program
    tells you this when you change a type.
  * 8-bit images are matched onto the library's existing palette. Adding art
    whose colours are far outside that palette will approximate.

Because untouched records are copied verbatim, opening any of the 689 retail
libraries and saving it straight back produces a byte-for-byte identical file.


-------------------------------------------------------------------------
AoWxImg - image library editor
-------------------------------------------------------------------------
* Every image parameter is shown in the grid AND editable in the panel:
  type, sub type, load mode, show/blend mode, blend value, clip_x, instance
  number, X/Y shift, palette index and transparent colour.
* The preview shows the image at IN-GAME SIZE (1:1) by default, so you see what
  the game will draw. Ctrl+Space (or the toolbar button) toggles an enlarged
  view, scaled by whole numbers with nearest-neighbour so no pixel is invented.
  The caption under the preview always says which mode you are in.
* Adding images is one click. "Add images" defaults to "Match this library",
  which copies the parameter set the library already uses - 74.5% of the retail
  ILBs use exactly one setting for every image, so this is almost always right,
  and it beats a fixed preset where libraries genuinely differ (retail face
  libraries use bmAlpha, the AoWx-added ones use bmUser).
* Ten named presets, mined from the retail data, for building a library from
  scratch: unit sprite, portrait/face, item icon, structure/map object,
  tactical-combat object, spell effect, race set, mountain, scene backdrop,
  UI element.
* Three SEPARATE remembered folders, kept in
  %APPDATA%\AoWxTools\aowximg.json:
      - where you open and save libraries
      - where you import pictures from
      - where you export pictures to
  Exporting to the desktop no longer drags the "open library" dialog out of the
  game folder.
* Export (Ctrl+E): with ONE image selected you get a Save As dialog, so you can
  name the file. With several selected you pick a folder once and they are
  written using their own names.
* "Check" lists any image whose settings differ from the rest of its library.
* "Re-import" replaces a slot's picture while keeping all its parameters.
* Composite (layered) images appear as child rows.

Known limits:
  - No animation preview yet, and no drag-to-reorder in the grid.
  - No palette re-quantisation pass for 8-bit imports (see above).


-------------------------------------------------------------------------
AoWxQuest - campaign editor
-------------------------------------------------------------------------
* Drag nodes on the map. X/Y update live; no more typing coordinates. Mouse
  wheel zooms and the window resizes (AoWCGE was locked to 640x480).
* Markers can show the record's ID number, and the name label beside them can
  be switched off - both are tick boxes under "Show on map". With 139 nodes on
  one backdrop, IDs-only is far more readable than names.
* Branch tree on the left. A straight run of scenarios stays at ONE indent
  level; only real branch points indent, so a long campaign no longer marches
  off the right edge. Loops back to an earlier scenario are marked
  "[loops back]" instead of recursing forever.
* Counter actions now appear IN the tree, as a child of the scenario they
  belong to. Previously only unlinked ones were listed, which is why they
  vanished when "Only ticked branches" was on.
* Records a scenario points to as its next mission but which hold no scenario
  file are labelled "[ending]" - these are where a storyline stops. They are no
  longer mislabelled as unlinked counter actions.
* Counter action linking is a DROPDOWN listing every counter action by id and
  title, plus a "New" button that creates one and links it to the current
  scenario in a single step. A reference to a counter action that no longer
  exists shows as "#n <MISSING>" rather than silently looking fine.
* "Check campaign" reports broken links: duplicate IDs, references to missing
  counter actions, scenarios with no counter action, next-mission links
  pointing nowhere, branch endings, unused counter actions, and scenarios
  unreachable from the start.
* Story text is spell-checked with red underlining. Right-click a flagged word
  for suggestions or to add it to the campaign dictionary, saved next to the
  .cam as <name>.dict.json. British spellings are accepted and names used in
  scenario titles are learned automatically.
* "Find typos" (Ctrl+T) opens a dockable list grouped into "Likely typos" and
  "Probably names" - a capitalised word used 3+ times is treated as a character
  or place name and set aside. Click any occurrence to jump to it: the record
  is selected, the chapter tab and page open, and the word is highlighted.
* Undo / Redo (Ctrl+Z / Ctrl+Y) covers node drags, field edits, story text,
  adding and deleting records, and setting the start scenario. Typing is
  coalesced so a burst of keystrokes is one step.
* Book-page pictures preview under the story text, and "Full size" opens them
  at their real resolution (272x372 for book art). The game folder is
  auto-detected from the .cam location; "Pick..." opens a thumbnail browser of
  every picture in a library.
* "Set as start" fixes AoWCGE's headline bug. The .cam format has no
  start-scenario field - the game uses the FIRST record - so this reorders the
  list, which AoWCGE never let you do.
* Green = scenario, yellow = start, red = counter action. Green curves are
  next-mission links, dashed blue are counter-action links.

Known limits:
  - Undo is snapshot-based (whole campaign per step, 60 steps). Inside a text
    box Ctrl+Z is the app's undo, not the editor's.
  - Deleting a record clears references to it but does not renumber anything.
  - Story text is stored with CRLF as the game writes it; the editor shows LF
    and converts back on save.


-------------------------------------------------------------------------
Building from source
-------------------------------------------------------------------------
    pip install PySide6-Essentials pyinstaller pyspellchecker Pillow
    python build_tools.py            (or: build_tools.py img | quest | ink)

Layout:
    aowxlib\ilb.py     ILB codec  - 689/689 retail libraries round-trip
                       byte-identically; RLE re-encoding reproduces the
                       original byte stream exactly
    aowxlib\cam.py     .CAM codec - all 12 campaign files round-trip
                       byte-identically
    aowxlib\presets.py preset table + "match library" logic
    assets\            world maps extracted from AoWCGE, preset JSON, icons
    AoWxImg.py         image library editor
    AoWxQuest.py       campaign editor
    build_tools.py     PyInstaller build script

Both codecs preserve fields they do not understand, so saving never silently
drops data - including the three clip_x values ILB Maker rewrites to zero.


-------------------------------------------------------------------------
AoWxInk - localisation editor
-------------------------------------------------------------------------
Opens the game's whole Dict folder at once - all 8 Multilizer dictionaries,
6683 records - because the languages live side by side in one file per module,
and translation memory works across them.

* Editable grid: Source (Native) plus one column per language, with per-column
  visibility tick boxes. Untranslated cells (text present but identical to the
  source) are drawn amber; empty cells grey. A roomy text box under the grid
  handles the long story strings.
* Find with substring or regular expression, in any column or one column.
  "Show" filters to All / Untranslated / Empty / Translated for a chosen
  language. It defaults to the first REAL language, not English - the English
  column is deliberately near-empty because Multilizer falls back to the
  source text.
* Undo / Redo (Ctrl+Z / Ctrl+Y) over every edit, jumping back to the cell and
  the file the change was in.
* Propagate (Ctrl+P): choose the source language, then fill other languages
  from a translation memory built out of every dictionary - the same string is
  often already translated elsewhere. It can also flag every cell that still
  reads exactly like the source, which is the real to-do list, and optionally
  seed empty cells with the source text (off by default; it looks finished
  when it is not).
* Add language: adds a column to all 8 dictionaries at once, with presets for
  Russian, Polish, Dutch and Portuguese. Existing text is untouched, verified.
* TSV export / import for translating outside the tool. Import never writes
  the Source column - that is the game's lookup key.
* Stats: per-file, per-language coverage, counting a cell as done only if it
  differs from the source.
* Repairs on load. MLDEdit's writer never wrote the `Primary` field and wrote
  `ISODefaultCountry` twice overlapping, silently corrupting six of the eight
  shipped dictionaries; AoWxInk restores the canonical values and always
  recomputes header offsets. Saving is atomic (write temp, re-parse to prove
  it loads, then replace) and keeps a one-time .bak_aowxink beside each file.

Russian
-------
The game draws text from bitmap glyph strips in Int\Fonts\*.ILB, where the
byte value IS the glyph's image id. A census of every high byte in real text
found 57 in use and 71 never used at all - and Cyrillic needs 66. So Russian
goes into free slots and NOTHING that German, French, Italian or Spanish rely
on is disturbed. aowxlib\cyrillic.py holds that mapping and its codec.

The dictionary side is finished and proven: adding Russian as a 7th language
writes correctly, the Cyrillic survives a save/reload, and all five existing
languages stay byte-identical. Two things remain before it shows up in-game:
the 66 glyphs must be painted into the font libraries, and the two `cmp eax,5`
language-index checks (AoWx.exe ~0x0532CB, AoWEPACK.dll ~0x096A60) plus their
6-entry jump tables need extending to accept a 7th language.

