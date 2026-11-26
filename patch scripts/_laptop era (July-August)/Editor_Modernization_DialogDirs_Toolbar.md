# Editor Modernization — Per-Dialog Directory Memory + Menu Toolbar + Maximized

**Status: APPLIED + AUTOMATED-DRIVEN-TEST PASS (2026-07-09). Awaiting user in-game confirmation
before marking CONFIRMED WORKING.**

Three independent AoWDevEd.exe / AoWEd.exe usability patches, requested for a 4K screen where the
editor's tiny centered window and menu-buried file dialogs are painful. Built as two build scripts:

| Feature | Script | Binaries touched | Backup suffix |
|---|---|---|---|
| Per-dialog-type directory memory | `build_dlgdirs.py` | `AoWDevEd.exe`, `HSEPack.dpl` | `.pre-dlgdirs` |
| Menu→toolbar rows + start maximized | `build_editor_toolbar.py` | `AoWDevEd.exe` (DFM only) | `.pre-modtoolbar` |

Apply order was **dlgdirs first, then modtoolbar** (both add a PE section to AoWDevEd.exe).
Revert in **reverse order**: `.pre-modtoolbar` restores the dlgdirs-only exe; `.pre-dlgdirs`
restores the pristine (pre-both) exe. HSEPack has only `.pre-dlgdirs` (its `.pre-mapcursor` sits
underneath — reverting dlgdirs via `.pre-dlgdirs` keeps the mapcursor fix, since that backup was
taken *after* mapcursor was applied).

---

## Feature 1 — Per-dialog-type directory memory (`build_dlgdirs.py`)

### Problem
Every file dialog in the editor opens in the same "last folder". None of the editor's Open dialogs
seed `FileName`/`InitialDir`, so Windows falls back to a single per-application MRU folder shared by
all of them. Scenario maps (`*.hsm`, under `1Scenario\…`) and mapsets/rulesets (`*.hss`, e.g.
`Release\Release.hss`) live in different trees, so the user constantly re-navigates between them.

### Solution
Each dialog **type** gets its own remembered full path, persisted across sessions in
`<gamedir>\AoWEd_LastDirs.ini`, section `[LastDirs]`:

```
[LastDirs]
Map=…\1Scenario\…\111MPv1.hsm      ; File>Open (map) + THSMEdit.Load/SaveAs
Set=…\Release\Release.hss          ; Developer>Open Mapset + THSSEdit.Load/SaveAs
Text=…\something.txt               ; Export/Import Text + Export Ability Info (exe)
```

- **Open dialogs**: before `Execute`, the cave reads the INI key and sets `FFileName` (+0x6C) to the
  remembered full path and `FInitialDir` (+0x60) to its directory part → the dialog opens in that
  folder with the last file preselected. After a successful pick, the chosen path is written back.
- **Save As dialogs** (map + set): their `SetInitialDir(GetCurrentDir)` call is rerouted — if the INI
  has a remembered path for that type, its directory part replaces the CWD; else original behaviour.
  (When a map/set already has a full path from load, the VCL puts it in `lpstrFile`, which wins over
  InitialDir anyway — so Save As on an already-loaded file opens at that file's own folder. Verified
  live: Save As on loaded `Release.hss` opened in `Release\` with `Release.hss` preselected.)
- **First run / missing key** → exactly vanilla behaviour. No INI is created until a dialog is accepted.

### Hooked sites (all `call <import-thunk>` → `call <cave-wrapper>`, 5 bytes, 1:1)
Cave = one new PE section `.dlgd` per module (chars `0xE0000060`: code+data, X/R/**W** — the INI read
buffer lives in-section). 16 sites total, each byte-verified against the shipped binary before write.

**AoWDevEd.exe** (fixed base 0x400000, absolute refs fine):
- seed (Create thunk 0x4019C8): `0x429840` OpenBtnClick=Map, `0x42B9AC` ImportText=Text,
  `0x42B8AC` ExportText=Text, `0x42D436` ExportAbilityInfo=Text
- persist (GetFileName thunk 0x4019D0, first call after Execute): `0x429899`, `0x42B9DF`, `0x42B8EC`, `0x42D488`

**HSEPack.dpl** (preferred 0x55600000, **REBASES** → cave is position-independent):
- seed (Create 0x55601A54): `0x55615267` THSMEdit.Load=Map, `0x55615E96` THSSEdit.Load=Set
- dirseed (SetInitialDir 0x55601A64): `0x55614D7E` THSMEdit.SaveAs=Map, `0x55615C5A` THSSEdit.SaveAs=Set
- persist (GetFileName 0x55601A5C): `0x556152BD` (Load Map), `0x55614E65` (SaveAs Map, post-save),
  `0x55615EE5` (Load Set), `0x55615C8E` (SaveAs Set)

### Key technique — calling kernel32 profile APIs from a module that doesn't import them
Neither AoWDevEd.exe nor HSEPack.dpl imports `GetPrivateProfileStringA`/`WritePrivateProfileStringA`.
But **VCL30.dpl** (the shared runtime, always loaded) does — its IniFiles unit pulls them in. Both
patched modules import `VCL30!Dialogs.TOpenDialog.Create`, so at runtime the cave recovers VCL30's
runtime base:

```
vcl_delta = [own IAT slot for TOpenDialog.Create]  -  0x4137AFB0   ; Create's preferred VA in VCL30
GetPrivateProfileStringA   = [ 0x413E43B8 + vcl_delta ]            ; a VCL30 IAT slot
WritePrivateProfileStringA = [ 0x413E42F8 + vcl_delta ]
```

Constants (verified against the game's VCL30.dpl):
`TOpenDialog.Create` preferred VA `0x4137AFB0`; VCL30 IAT slots GPPS `0x413E43B8`, WPPS `0x413E42F8`;
own Create IAT slot AoWDevEd `0x432598`, HSEPack `0x556308DC`.

### Rebasing handling (HSEPack)
Every data reference in the HSEPack cave is `[reg+disp32]` corrected by an `ebx` module-delta computed
by a 4-instruction `call/pop` helper (`getdelta`: `runtime_here - preferred_here`), and every call is
rel32. No `.reloc` entries needed. In the exe the same code works with delta = 0.

### String handoff
The INI read buffer (0x108 bytes) doubles as a Delphi 3 static AnsiString: `[buf-8]` = refcount −1
(immutable, never freed), `[buf-4]` = length (set to the API's return after each read). `@LStrAsg`
copies when the source refcount < 0 (verified in the VCL30 disasm), so assigning the buffer into
`FFileName`/`FInitialDir` is safe; `SetInitialDir` copies too. Register ABI: caves push/pop
ebx/esi/edi and only carry eax across the original thunks; kernel32 APIs are stdcall (callee-clean).

### Why patching HSEPack is safe for the game
HSEPack.dpl is also loaded by AoW.exe / AoWCompat.exe / AoWEd.exe. The patched functions
(`THSMEdit.Load/SaveAs`, `THSSEdit.Load/SaveAs`) are **editor-only** entry points — the game never
calls them — and the cave is host-agnostic (no absolute exe addresses). Riding along in other
processes is inert. **Bonus:** AoWEd.exe gets the map/mapset dialog fix for free via HSEPack (its own
in-exe File>Open would need a separate exe patch — not done, low value).

### Live automated test (2026-07-09, driven via clicker/menucmd, screenshots captured)
1. Open Mapset → picked `Release\Release.hss` → INI got `Set=…Release.hss`. ✓
2. File>Open (map) → picked `1Scenario\…\111MPv1.hsm` → INI got `Map=…111MPv1.hsm`, `Set` untouched. ✓
3. Reopen Open Mapset → dialog **preselected `Release.hss` in `Release\`** (seed cave), NOT the map
   folder → the two memories are genuinely independent. ✓
4. Save As with mapset loaded → dialog opened cleanly (no crash), `Release.hss` preselected. ✓

### Failed approach avoided
Do **not** try to add the profile-API imports to the exe/DLL import table (fragile table surgery) or
hardcode a rebasing cross-DLL call target. The `VCL30 IAT via own-IAT-delta` trick sidesteps both.

---

## Feature 2 — Menu options as always-visible toolbar rows + start maximized (`build_editor_toolbar.py`)

### Revision 2026-07-09-b (user-requested tweaks — APPLIED + AUTOMATED-TESTED)
Re-applied via `copy AoWDevEd.exe.pre-modtoolbar AoWDevEd.exe` then
`python build_scripts/build_editor_toolbar.py --apply` (the `.mtb` marker made the first `--apply`
a no-op until the revert; note: use `Copy-Item … -Force` in PowerShell, not `copy /Y`).
1. **Removed the `Close` button** (`MBClose`) from the File group (misclick risk, like Exit).
   Verified: Row 1 File group is now `New Open Save "Save As"`.
2. **Underlined the six category labels** (File/Edit/Options/Preview/Developer/Help): each `TLabel`
   now carries an explicit underlined copy of the form font (`Font.Style=[fsUnderline]`,
   `ParentFont=False`, Height −10/MS Sans Serif to keep size) so they read as section headers.
   Verified in a zoomed screenshot: all six labels underlined, command buttons not.
3. **Ctrl+S saves**: added `ShortCut = 16467` (=0x4053 = scCtrl|'S') to the `SaveItem` menu item
   (it had none). The build script now locates `SaveItem` via a recursive DFM node search and splices
   the property in; because the menu streams *after* Panel2, the three insert points are spliced
   highest-offset-first (SaveItem → Panel2 tail → root) so offsets stay valid. `KeyPreview=True` on the
   form means Ctrl+S fires from anywhere, routing to `SaveBtnClick` (same as the Save button/menu).
   Verified: the File menu now renders `&Save⇥Ctrl+S` (VCL draws that accelerator straight from the
   ShortCut property, which is also what its dispatcher matches), and a synthesized Ctrl+S keystroke
   ran the Save path without fault (early-outs with no map loaded, exactly like the Save button).

### What
Two captioned toolbar rows are injected under the existing icon toolbar (Panel2), exposing (nearly)
every menu sub-option as a flat `TSpeedButton`, **grouped and labelled by its parent menu**
(category names are UNDERLINED labels). `Close` is intentionally omitted (see revision note above):

- **Row 1 (Top=50):** `File |` New Open Save "Save As" · `Edit |` Cut Copy Paste Delete ·
  `Options |` "Map Settings" "Player Info" Scanner "Remove Level" "Add Level" ·
  `Preview |` 640 800 1024 1280
- **Row 2 (Top=82):** `Developer |` "New Combat Map" "New Mapset" "Open Mapset" "Game Settings"
  "Mapset Settings" "Edit Map Text" "Export Text" "Import Text" Multilizer "Debug Mode" "Fog of War"
  "Export Abilities" "Remove Leaders" · `Help |` About

Also sets `WindowState=wsMaximized` on the main form (opt out with `--no-maximize`), so it fills a 4K
screen instead of the 916×696 centered default.

**Deliberately skipped:** File>Exit (misclick risk), the runtime-built per-map Players menu, and the
Debug/Fog/Scanner/Preview *check-mark* state (buttons fire the same handlers; the checkmarks still
show in the menus, which stay fully functional).

### How — DFM resource edit, ZERO new code
Delphi forms are serialized component trees in the `RCDATA "TMAINFORM"` resource. **DFM event
handlers are resolved by name against the form's published method table at load time**, so a brand-new
`TSpeedButton` can be wired to an *existing* handler (e.g. `OnClick=OpenBtnClick`) with no code added.
All 32 handler names were verified present in TMainForm's published method table, and each exposed
handler either self-guards (checked in disasm) or is exactly as reachable as its always-enabled menu
item is today. The injected classes (TPanel/TSpeedButton/TLabel) are all in TMainForm's streaming
class table, so `TReader` can instantiate them.

The enlarged DFM (0x4AFD5 → 0x4C393 bytes) can't fit in place, so the patch:
- appends the rebuilt blob to a new PE section `.mtb`,
- **repoints the `IMAGE_RESOURCE_DATA_ENTRY` for TMAINFORM** (found by walking `.rsrc`) to the new
  section (OffsetToData + Size). The old blob stays in `.rsrc` as dead data.

Layout: new panels are `alTop` with Top=50/82 so the VCL stacks them under Panel2 (Top=0); Panel1 is
`alClient` and reflows automatically. The build script re-parses the modified DFM (offset-tracking
parser incl. `vaCollection`) and asserts it round-trips to the same shape with `MBRowA`/`MBRowB`
present after `Panel2`, before writing.

### Live automated test (2026-07-09)
- Editor launches, does not crash, opens **maximized** (window −8,−8..2568,1400 on a 2560 screen). ✓
- Both toolbar rows render with all captions grouped/labelled (screenshot). ✓
- Clicked **About** button → About dialog opened. ✓  Clicked **Open Mapset** button → Open dialog. ✓
  File>Open handler (via row) → map dialog. ✓ (buttons are correctly wired to the real handlers)

### Note on TSpeedButton clicks in automation
`TSpeedButton` is a `TGraphicControl` (no HWND); it receives mouse via the parent panel's WM_MOUSE*,
dispatched by coordinate. So automation posts `WM_LBUTTONDOWN/UP` to the **panel** hwnd at the
button's client coords (that's how the live test drove them). Menu items were driven via
`menucmd.py exec <id>` (WM_COMMAND).

---

## Rebuild / revert quick reference

```
# rebuild (dry-run prints cave disasm / layout; --apply writes; both idempotent)
python build_scripts/build_dlgdirs.py            # then --apply
python build_scripts/build_editor_toolbar.py     # then --apply   (apply AFTER dlgdirs)

# revert (close AoW/AoWCompat/AoWDevEd/AoWEd first — they lock the files)
copy AoWDevEd.exe.pre-modtoolbar  AoWDevEd.exe    # undo toolbar (keeps dlgdirs)
copy AoWDevEd.exe.pre-dlgdirs     AoWDevEd.exe    # undo BOTH exe patches
copy HSEPack.dpl.pre-dlgdirs      HSEPack.dpl     # undo dlgdirs in the DLL (keeps mapcursor)
```

`AoWEd_LastDirs.ini` is created lazily and is harmless to delete (resets to vanilla behaviour).

### v2 (2026-07-31) — INI path now RUNTIME-DERIVED; feature is install-location-independent
v1 baked the absolute INI path (a build-machine constant) into the `.dlgd` caves, which silently
disabled the whole feature on any other machine/folder (reads empty → vanilla shared-MRU fallback,
write-backs fail — no error). Discovered after the home-PC→laptop transfer; briefly hotfixed by
editing the string in place (`.bak_inipath` backups, now-obsolete intermediates), then fixed properly:
`build_dlgdirs.py` v2 adds a lazy `getini` cave helper — `GetModuleFileNameA(NULL, buf, 0x104)`
(via VCL30 IAT slot `0x413E43C0`, same borrow trick as the profile APIs) → truncate after last `\` →
append `AoWEd_LastDirs.ini`. NULL = host exe, so HSEPack riding in AoW.exe/AoWEd.exe resolves the
game dir too. Built once per process (buffer byte 0 doubles as the done-flag); on failure the buffer
stays empty and both profile APIs no-op → vanilla. Rebuilt 2026-07-31 from the `.pre-dlgdirs`
backups (module renamed AoWDevEd.exe → AoWDevX.exe in the script; all 16 sites re-verified; cave
now 990/1141 bytes). **Shipped binaries are now safe to distribute — the feature works for any
player at any install path.** The INI's *stored* paths still go stale on a move (dead paths → MRU
fallback for that entry until the next successful pick, which overwrites it); deleting the INI is
always safe.
