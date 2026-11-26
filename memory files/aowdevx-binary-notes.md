---
name: aowdevx-binary-notes
description: "AoWDevX.exe (patched AoWEd editor) — PE layout, title/icon patch sites, cave usage"
metadata: 
  node_type: memory
  type: reference
  originSessionId: b2194c48-2a67-4385-b51c-d26ff2e1f586
  modified: 2026-09-20T17:00:00.000Z
---

AoWDevX.exe (base 0x400000; CODE VA 0x1000 raw 0x400, DATA 0x2f000, .rsrc raw 0x42600, extra section .dlgd @VA 0xE1000 from the earlier About-dialog patch). Delphi 3, Multilizer TIvTranslator with `Dict\AoWEd.mld` (dictionary FILE name — do not rename).

**Identity patch (2026-08-23, `patch scripts\build_aowdevx_identity.py`, backup `.bak_identity`)**:
- TASKBAR text came from `Application.Title := 'AoWEd'` — constant AnsiString literal chars @file 0x2e3e8 / VA 0x42efe8, single code ref operand @file 0x2e25f. New literal "AoWDevX" in the 16 zero bytes at CODE raw tail @file 0x2e3f0 (VA 0x42eff0, chars 0x42eff8); operand repointed; **CODE VirtualSize bumped 0x2dff0→0x2e000**. That cave is now FULL.
- **TITLE-BAR text (TMainForm.Caption) is a DIFFERENT source**: the AoWE unit's Multilizer resourcestring `AoWEdRStr` — value 'AoWEd' lives in **AoWEPACK.dll's RT_STRING** (don't patch there: vanilla AoWEd.exe shares it). AoWDevX imports the ResStringRec as name `AoWE.AoWEdRStr@04ECFCC5` (IAT slot VA 0x432934); 4 CODE sites do `lea edx,[ebp-X]; mov eax,[slot]; call load-helper` into a nil local then TranslateRStr (unknown text passes through). Fixed by a 7-byte cave in .dlgd slack @file 0xdcfe0 / VA 0x4E13E0 (`mov [edx],0x42eff8; ret` — literal store into nil dest, refcount −1 so LStrClr skips it) with all 4 call rel32s retargeted (operand file offs 0x27a65/0x29b31/0x29b8d/0x29bd5 +5); **.dlgd VirtualSize bumped 0x3de→0x400**. Verified all 4 in bytes; ~25 bytes of .dlgd slack remain.
- Diagnostic trick: enumerate top-level windows per PID — TApplication window caption = Application.Title, TMainForm caption = the visible title bar; the two differing is what exposed the second source. AoWDevX runs elevated (RUNASADMIN) — can't Stop-Process from non-elevated shell, but a running exe CAN be renamed aside to unlock the path for writing a patched copy.
- Icons: the INTENDED art is the exe's original MAINICON — black dragon over green hexes (a 32bpp editor remaster; vanilla AoWEd.exe uses red dragon over BLUE hexes, and the old title-bar DFM icon was the plain red game dragon). The script keeps RT_ICON 3/1 (4264 B @file 0x446c4) as that original art (restoring from backup if needed) and writes a 16-color quantized copy of it into MainForm DFM `Icon.Data` (766 B payload @file 0x74c0c). A first build wrongly used a dragon+pencil badge — user corrected it 2026-08-23.
- MainForm DFM Caption is "Age of Wonders Editor" (@0x74b38) but runtime title shows Application.Title. RegistrationDlg still captioned "Age of Wonders" (@0xd2ac4, unshown dialog — left alone).

**How to apply:** future AoWDevX string grows need a new cave (append a section or use .dlgd slack ~0x3de..0x400). Re-cut release zip + installer after any AoWDevX patch. Related: [[aowx-release-process]], [[aowsetup-internals]].

**Item Properties dialog HP/MV rows (2026-09-12, `patch scripts\patch_devx_item_hpmv_ui.py`, backup `.bak_itemui`, new RWX section `.xitm` @VA 0x4E5000 raw 0x400, SizeOfImage 0xE5000→0xE6000; NOT yet UI-tested — AoWDevX runs elevated so it can't be launched from the agent shell):** TItemEditForm VMT 0x412d40 (DFM TITEMEDITFORM @file 0x697a8, 7487 B, PixelsPerInch 120 Scaled False): item [form+0x27C], read-only-library flag +0x280, ClientPnl +0x1DC, StatisticsPnl +0x224 (397x161, rows label x=28/spin x=124, y=24+32*row), stat spinners AttackEdit +0x250 / DefenseEdit +0x254 / ResistanceEdit +0x258 / DamageEdit +0x25C are **VCLADDON.dpl TSpin** (classref IAT 0x43357c = VMT directly — class import symbols ARE the VMT, no extra deref; ctor VMT+0x24 (eax=class, dl=1, ecx=owner); SetValue/GetValue thunks 0x4030e8/0x4030e0; OnChange TMethod +0x128/+0x12C; MinValue +0x130, MaxValue +0x134, EditorEnabled byte +0x140). Published-method table (vmt-40) entry FormCreate dword @file 0x12489 → fc_wrap (zero statics, original 0x413630, then grow form/ClientPnl/StatisticsPnl Height +64 via TControl.SetHeight IAT 0x4323c4 and create 2 TLabel (IAT 0x432654) + 2 TSpin on rows 4/5; HP -20..30, MV -10..10). Update routine 0x41321c (loads controls from item; called after item assignment + ItemTypeBoxChange) prologue hooked → refresh (SetValue from [item+0x4A/+0x4B], SetColor clWindow/clBtnFace by +0x280). The "greyed Use-item stats" was ONLY `cmp [item+0x34],6 / je` @0x4134A0 painting clBtnFace → nop'd. VCL30 TControl fields: +0x30 Left, +0x34 Top, +0x38 Width, +0x3C Height, +0x54 Color; TControl.SetBounds(eax,edx=L,ecx=T, push W, push H). Imports used: SetParent 0x4323ac, SetBounds 0x4323d4, SetText thunk 0x401568, SetColor thunk 0x4015a0. Labels are literal English (not in AoWEd.mld). ⚠ **v1 CRASHED ("Oh dear, it's the end...." = the editor's EAccessViolation handler @0x4281EC, then Terminate) — cause: calling the STATIC `Controls.TControl.SetBounds` import on a TWinControl; it Performs WM_WINDOWPOSCHANGED with a nil WindowPos which TWinControl.WMWindowPosChanged derefs. Always dispatch SetParent (+0x3C) / SetBounds (+0x4C) through the VMT for runtime-created controls.** Diagnosed with the VEH logger on a renamed copy `AoWDevX_dbg.exe` launched by an ELEVATED python (Start-Process -Verb RunAs; the exe quits at once if not elevated — the RUNASADMIN flag is per-path in HKCU AppCompatFlags\Layers, a renamed copy has none); UI must then be driven by the user (UIPI blocks messages from a non-elevated shell). v2 also relocates the form DFM into `.xdfm` @0x4E6000 (see [[aowx-item-hpmv]]).

**⚠ v2 LIVE (2026-09-14, `patch scripts\patch_devx_prune_unused_v2.py`, same backup `.bak_prune` = pristine base it always rebuilds from; v1 superseded):** `.xprn` is now 0x53C00 bytes (SizeOfImage 0x13CC00): +0x0000 caves (~1.6 KB; free ≈ +0x650..+0x1000), **+0x1000 relocated TMainForm FIELD table** (308 entries, VMT−0x2C → 0x4EA000; new fields FogBtn +0x6AC / PruneHeroesBtn +0x6B0 / PruneItemsBtn +0x6B4, class index 30 = Buttons..TSpeedButton; InstanceSize 0x6AC→0x6B8), **+0x2800 relocated published-METHOD table** (VMT−0x28 → 0x4EB800; FogofWarClick → fog wrapper, + PruneHeroesClick/PruneItemsClick), **+0x4000 relocated TMAINFORM DFM** (res data entry @file 0x43550 → RVA 0xED000, 0x4FB1F B; vanilla 0x4AFD5 @file 0x74AFC): 3 TSpeedButtons in Panel2 after PreviewBtn (39x38, x=592/652/692, Enabled=False, NumGlyphs 2, Glyph.Data = dword(len)+BMP 64x32 24bpp, transparent = bottom-left (191,191,191); painted by `make_devx_toolbar_icons.py` → `assets\devx_*_btn.bmp`; toolbar rows: Panel2 buttons 39x38 at x 4,44,96,152,192,232,288,328,388,428,488,552) + menu nodes after RemoveLeadersItem. CODE hooks: 0x42A19C/0x42A4BF (`mov eax,[ebx+0x610]; call SetEnabled` in map-close/open → cave enabling the 3 new fields too), 0x42CD44/0x42CDE0 (`cmp byte [esp],0xFF; je` in GotoItemClick/GoToHeroClick → site-search cave: item container == [site+0x3C] of a TItemExplorationSite (VMT 0x557C23BC) / hero Owner army == [site+0x34] of a TExplorationSite (VMT 0x557C1440); structures = map+0x100 → [sc+8] node → [node+8] TList; site x/y/level via VMT +0x74/+0x78/+0x7C (Engine.TMapObject thunks, return al); class test walks [[VMT−0x18]] parent cells; AoWEPACK delta = [0x43289C] − 0x558FA040), `.vgo` 0x4E30F0 (`call THSMEdit.CenterView` in BXL's valgoto handler → cave adding PlayCenterAnimation thunk 0x401CF8 (eax=map, dl=x, cl=y, push level, ret 4)). Other facts: TMenuItem Checked byte +0x2C; FogofWarClick 0x42BB64 reads the menu via [form+0x390] (Sender-agnostic); TSpeedButton.SetDown thunk 0x402318 (eax,dl), TControl.SetEnabled thunk 0x401550 (eax,dl); PreviewBtnClick = THSMEdit.ShowPreview; Go-to handlers: GetSelected → `[obj+4]==0 → exit` → GetLocation(eax,edx=&x,ecx=&y,push &level) → SetMapLevel 0x429C68(eax=form, edx=level) → THSMEdit.CenterView 0x402E28 → PlayCenterAnimation; site treasure lists (TExplorationSiteItemList) and defender armies are created with Owner=nil, so nothing links back to the site except the site's own fields. Earlier v1 notes follow (technique still valid):

**Developer > Delete Unused Heroes / Delete Unused Items (2026-09-14, `patch scripts\patch_devx_prune_unused_v1.py`, backup `.bak_prune`, APPLIED to the 410 prerelease exe, UNTESTED in the editor — it runs elevated):** new section `.xprn` @VA 0x4E9000 (raw 0x1000, ~2.8 KB free at +0x520 for future small caves; SizeOfImage 0xEA000). ⚠ **The AoWDevX section table is now FULL (13 headers end exactly at file 0x400 = CODE raw)** — future caves must use slack: `.xprn` tail, or the orphan all-zero `.xthm` @0x4E4000 (0x800 B RWX, no owning script found anywhere — probably a reverted patch; don't assume it stays free). Technique (no DFM/method-table relocation, unlike BXL's build_deved_heroprune.py): TMainForm's published-method-table dword for FormCreate (table @0x4272EE, dword @file 0x266F2, was 0x42841C) → wrapper that runs FormCreate then creates a NewLine + two TMenuItems at runtime via the already-imported thunks TMenuItem.Create 0x401818 (eax=class [IAT 0x4324BC], dl=1, ecx=owner) / SetCaption 0x401820 (edx=AnsiString) / Add 0x401850 (eax=parent, edx=item) / NewLine 0x401860; **TMenuItem OnClick TMethod = +0x60 code / +0x64 data**, Enabled +0x2D, Caption +0x24 (VCL30, confirmed by the exe's own recent-files code @0x407B34). TMainForm fields: DeveloperItems +0x358, RemoveLeadersItem +0x560, HSMEdit +0x22C (render pause/resume: guard byte +0x1BC, VMT +0x90/+0x94), ItemControlGrid +0x39C, HeroControlGrid +0x3AC, MainMenu1 +0x1DC. Delphi 3 VMT negative slots here: −0x2C field table, −0x28 method table, −0x20 class name, −0x1C instance size. Our CODE is byte-identical to BXL's AoWDevEd at every template routine (RemoveLeadersMIClick 0x42D598, DeleteHeroBtnClick 0x42AD10, MsgDlg 0x42BBE4 — cl=3 + buttons 11 → Win32 MessageBox path, no LStrAsg on the message). Hero prune = BXL's predicate (Owner [+4]==nil and not TLeader) and per-victim VMT+0x188 Deactivate then +0x2C Release. Item prune: TItemControl = map+0xF4 ([ic+8] TList: +4 array, +8 count); victims = item[+4]==nil; deletion = what ItemCtrl.TItemControlGrid.DeleteItem does: `AoWE.TItemControl.UnRegisterItem` (0x55794F08; TList.Remove, clear flag bit 2, Release, Changed) — NOT imported by the exe, so resolved at run time as [IAT RegisterItem 0x4326E0]+0x8C with a 10-byte prologue check (53 56 8B DA 8B F0 F6 43 1C 02); THSMEdit.DeselectPlaceHS (thunk 0x402DE8) first. Registered pool items have refcount exactly 1 (GenerateItem tests `[item+0x20]==1`). ⚠ **Gameplay semantics:** unplaced roster heroes ARE the hero-join pool (TPlayer.MakeHeroEmerge 0x55752520 picks Owner==nil, not dead, [+0x24]≤0, race-compatible) and unheld registry items ARE the random-treasure pool (TItemControl.GenerateItem 0x55794F40 ← TItemHS.GenerateItems / TItemExplorationSite.Generate); no game code repopulates either from the libraries at load (UpdateLibraryHeroes/Items only refresh existing entries). Item hidden byte +0x44 (grid shows it only in dev mode) is not spared. ⚠ **keystone 0.9.2 gotchas:** bare decimal immediates are parsed as HEX (`push 64` → 6A 64) — emit every number as 0x…; and its `sym_resolver` hook mis-computes PC-relative branches by the displacement width — keep labels in one text and recover addresses with an appended `mov eax, label` probe (see the script). Menu OnClick handlers receive eax = the stored data (the form), edx = Sender.

**Splash rebrand 2026-08-26** ("patch scripts\patch_editor_splash_devx.py", backup EDIMAGES\Splash.BMP.bak_devx): title AoWed->AoWDevX + subtitle ->'Editor for Age of Wonders X' (both Age14G glyphs: title 1.5x black-face/gold-rim synth, subtitle 0.457-squeezed 13px), and Julia's sword arm clone-inpainted out of the bottom-right. Key facts: the splash bottom band is Int\TitleM.ILB image 0 (TitleFull 640x480) pasted at src=1.1225x-39 / 1.1275y+88; the area behind the text is the AUTHOR'S near-black fill (source has a pale stone face there — never refill from source); the BMP is BITMAPV5 32bpp BI_BITFIELDS, pixel offset 138, bottom-up; arm inpaint must run BEFORE new text compositing (its clone sources overlap the title zone).

**Splash rebrand REVERTED by the user 2026-08-26** — they found the generated result looked bad and will paint their own splash instead. Do NOT re-apply or propose regenerating it; the script and its background facts (TitleM source mapping, BMP layout, author dark-fill) stay valid as reference for their manual work.

## Editor responsiveness: timer resolution (BXL adoption, APPLIED 2026-08-31)
`patch scripts/build_editor_timerres.py` (backup AoWDevX.exe.bak_timerres; dry-run/--apply [--sleep N]/--revert surgical). **Root cause of the sluggish editor UI:** the frame loop calls Sleep(1) TWICE per frame — HSEPack `THSMEdit.UpdateFrame+0x09` (call thunk 0x556014FC) and AoWDevX `TMainForm.HSMEditUpdateFrame+0x29` (`push 1` @0x428D3F / call thunk 0x4013C8) — and **no AoW module ever calls timeBeginPeriod**, so at Windows' default 15.625 ms granularity each Sleep(1) is ~15.6 ms ⇒ ~31 ms/frame, and since the render loop paces the whole message pump the editor services input only ~32×/s (BXL profile: 76% of the UI thread inside those two sleeps). This is also why DFM FrameRate tuning stopped helping — **ours was already 60** (byte @0x751A0; the untouched twin AoWEd.dev.exe still reads 15) and FrameRate cannot pace below the Sleep floor.
**Fix:** hook the exe's kernel32 **Sleep import thunk @0x4013C8** (`ff25a0224300` → `jmp cave`+nop) → one-time `timeBeginPeriod(1)` on the first Sleep call, then tail-jmp `[0x4322A0]` with the caller's stack untouched. The exe imports neither LoadLibraryA nor GetProcAddress, so the cave borrows **VCL30's IAT via a delta**: `vcl_delta = [0x432210](exe IAT slot for Forms.TCustomForm.Create) − 0x41336300`, then `LoadLibraryA = [0x413E4360+delta]`, `GetProcAddress = [0x413E43B4+delta]` — all four anchors re-verified exact on our files 8/31. (Never derive from winmm's own export RVAs — they move with Windows updates.)
**Frame budget must be restored by hand:** with a 1 ms timer the loop free-runs (~55% of a core). CPU ≈ work(~4 ms)/period: stock ~31 ms/14% · **Sleep(8) ~13 ms/30% (our default)** · Sleep(1) ~8 ms/55%. So the script also patches the exe's own `push 1` imm8 @0x428D40. ⚠ **`--sleep 1` is only safe once build_editor_rendergate.py is installed** (its skip path paces the loop). Editor self-throttles when not foreground (~1-3%), so the idle cost is foreground-only.
**New PE section `.tres` @rva 0xE2000 (raw 0xDD000, 118 B body: [done flag][winmm.dll][timeBeginPeriod][code @0x4E2020]), R/W/X; sections 7→8, SizeOfImage 0xE2000→0xE3000.** `.dlgd` (rva 0xE1000, raw 0xDCC00) and the identity caption cave inside its slack (file 0xDCFE0) are NOT moved by an append — identity patch verified still applied afterwards. ⚠ SizeOfImage is recomputed from the MAX end over ALL sections; computing it from one's own section is the bug class that silently unmaps a later section (BXL hit exactly that with .hcol vs .syd).
Not yet adopted from the same BXL trio: **build_editor_rendergate.py** (HSEPack `.rgt` section, render every Nth pass: 29%→5% CPU with better latency; hook 0x55614912 verified vanilla on our HSEPack, epilogue 0x55614C2E `595a5e5bc3` ✓, skip MUST jump past the present at 0x55614C29) and **MapDrawSteps 1→8** (byte @0xD3C3D, progressive scanner redraw).

## Editor render gate — the animation-speed fix (APPLIED 2026-08-31, ours, time-based)
`patch scripts/build_editor_rendergate.py` (backup HSEPack.dpl.bak_rendergate; dry-run/--apply [--interval N] [--skip-sleep N] [--present-on-skip]/--revert surgical).
**Why it was needed:** after timerres the user reported "more responsive, but all the animations are sped up." **RE result: THSMEdit.UpdateFrame has NO wall-clock time base.** The only timeGetTime calls near it (0x55613E19/2A/37/4A, 0x55614C4B/65 via thunk **0x55601BE4**) merely write perf counters ([self+0x248/0x250/0x258/0x25C]); nothing gates on them. So **animation advances once per UpdateFrame call**, and since the frame loop paces the message pump, animation speed == pump speed. DFM FrameRate does not throttle it (ours already 60). ⇒ pump and animation cannot be decoupled without a gate.
**Design (BXL's hook site, but wall-clock instead of his every-Nth-pass counter — a pass counter would re-couple animation to pump rate):** hook the 7 bytes @0x55614912 → cave: `now=timeGetTime(); if now-last < interval → Sleep(skip_ms); eax=0; jmp EPILOGUE 0x55614C2E; else last=now; replay cmp; jmp RESUME 0x55614919`. Defaults **interval 31 ms** (= BXL's measured stock pump, so animation returns to vanilla speed) and **skip-sleep 2 ms** (pump ~2 ms on skipped passes).
- ⚠ skip MUST target the epilogue 0x55614C2E, not the early-exit 0x55614C27 — the latter still runs `call TCustomDisplay.UpdateFrame` @0x55614C29 = the present (StretchDIBits); BXL measured only 35%→22.5% when he jumped there. `--present-on-skip` selects that path if a skipped frame ever leaves the window unrepainted.
- ⚠ skipping bypasses the exe's OnUpdateFrame (and hence its Sleep), so the cave must sleep itself or the loop free-runs.
- Return value on skip = 0: verified safe on OUR exe — frame tick @0x42BDC8 does `call [vmt+0xAC]/test al,al/je 0x42BE87`, and **0x42BE87 is `pop ebx; ret`** (skips only status-bar/scanner updates, touches no loop-continuation state). The tick is a published event handler (dword ref in the method table, no direct callers).
- PIC per house rule: `call $+5; pop ebx` RUNTIME anchor, NO sub; state at [ebx−0x16/−0x12/−0xE] = last/interval/skip_ms; all calls/jumps rel32. Flags from the replayed cmp survive to RESUME (cmp is last). Hook range reloc-free (the fixup @0x55614920 belongs to `mov eax,[0x5562E2F4]` @0x5561491F and is not displaced) — re-asserted every run.
- **New section `.rgt` @rva 0x4F000 (raw 0x48800, 88 B), R/W/X; sections 9→10, SizeOfImage 0x4F000→0x50000.** `.dlgd` (rva 0x4E000) untouched. SizeOfImage recomputed from the MAX end over ALL sections.
- Deliberately INDEPENDENT of timerres (it does not touch the exe's Sleep arg), so either can be reverted alone. `--interval` is the live knob: higher = slower animation + less CPU.

**MapDrawSteps 1→8 APPLIED 2026-08-31** (`patch scripts/build_editor_scanner_steps.py`, backup .bak_scannersteps; one DFM byte @file 0xD3C3D, guarded by the `\x0cMapDrawSteps\x02` anchor, --steps N re-tunable). It is a property of the **SCANNER (minimap)** control, not the map view — proven by the surrounding DFM properties (ScanTiles/ScanHiLites/ScanFog/ScanObj/ScannerChangeTileBox/ScanWin). Splits the scanner rebuild across 8 frames; with the 31 ms render gate a full scanner refresh takes ~0.25 s. The FrameRate half of BXL's build_editor_framerate.py is moot for us (ours already 60; FrameRate cannot pace below the Sleep floor).

## Map Validation entries clickable → jump to tile (BXL adoption, APPLIED 2026-08-31)
`patch scripts/build_editor_validation_goto.py` (backup `AoWDevX.exe.bak_valgoto`;
dry-run/--apply/--revert surgical). Double-clicking a line in the Validate dialog
centres the map on that object, switching level if needed; an indented
`  Warning:` line walks UP to its `<Name> at location (x, y, z)` header; lines
with no location above them do nothing. Ported from BXL's `build_validation_goto.py`
(their notes `.../notes/Validation_Dialog_Clickable_Entries.md`) — **every address
re-verified on OUR AoWDevX.exe/VCL30/AoWEPACK before writing**, all matched:
- Hook `TMainForm.ValidateMapBtnClick` @0x0042CEAC, its `call ShowModal` @**0x0042CEE2**
  (`e80144fdff` → thunk 0x004012E8 = `[0x4321B0]` Forms.TCustomForm.ShowModal).
  EAX = the dialog there (`mov eax,ebx` @0x42CEE0). **dialog+0x1DC = the TMemo**,
  proven in the hooked function itself @0x42CEC8 (`mov eax,[ebx+0x1DC]; mov edx,[eax+0x130]`).
- Install cave sets **Memo.FOnDblClick — TMethod Code=+0xAC, Data=+0xB0** (from OUR
  VCL30 `Controls.TControl.DblClick` @0x41342B48; ⚠ its Assigned test only checks the
  **high word** of Code, so the cave must not sit at a VA with a zero high word).
- Handler = TNotifyEvent (EDX = memo). `Perform` via exe IAT **[0x00432354]**
  (`Controls.TControl.Perform` @0x413428D8, EAX=self EDX=msg ECX=wparam push lparam,
  **`ret 4` = callee-cleaned**, and it nil-checks self). EM_LINEFROMCHAR 0xC9 →
  clicked line; EM_GETLINE 0xC4 into a 256 B **stack** buffer (capacity word 0xFE).
- Parse: scan **right-to-left** for `'('` then `int , int , int )`. The `(x, y, z)`
  group is built at runtime by LStrCatN from GetX/GetY/GetLevel (VMT +0x74/+0x78/+0x7C)
  in `AoWE.TStructure.MainValidateMap` @0x5575F4F8, so it is always the LAST paren
  group and survives dictionary translation — that is why nothing matches words.
  (Detail lines get the two-space prefix literal @0x5575F6BC = `20 20 00 00`.)
  Memo is `ScrollBars=ssBoth` ⇒ no word wrap ⇒ visual lines = logical lines.
- Jump: `SetMapLevel` @**0x00429C68**(EAX=form, EDX=level) then `THSMEdit.CenterView`
  thunk **0x00402E28** (EAX=ctrl, EDX=x, ECX=y, push level; **clamps to map edges
  itself**). MainForm = `[[0x0042F0A8]]`, THSMEdit control = **mainform+0x22C**.
  Exact sequence of the editor's own precedent `TPlayerInfoFloater.StructureGridDblClick`
  @0x00425BEC (and GotoItemClick/GoToHeroClick/GoToLeaderClick/ScannerChangeTileBox).
- **New section `.vgo` @rva 0xE3000 (raw 0xDD200, 0x17D B), read+exec** (no writable
  state — the line buffer is a stack frame); sections 8→9, SizeOfImage 0xE3000→0xE4000.
  Editor-only: the game, AoWEPACK and every MP path are untouched, and the feature only
  moves the camera (writes no map data). Every failure mode is a no-op.

⚠ **SECTION-ORDER FOOTGUN FIXED 2026-08-31:** `build_editor_timerres.py`'s re-apply
path rebuilt the file as `d[:raw] + body`, which **destroys any section appended after
`.tres`** (i.e. `.vgo`). It now overwrites `.tres` **in place** when the body fits its
0x200 B raw slot (it is 0x76 B), keeping the truncating path only as a guarded fallback.
Verified: re-running `timerres --apply --sleep 2` leaves `.vgo` intact and the file size
unchanged. Both scripts revert surgically and keep their inert section headers, so
neither renumbers sections — they are order-independent now. Apply this same
in-place rule to any future AoWDevX section.

**⚠ Editor loads aowInt.dpl too** (verified from its import table 8/31) — so the game UI pack's wheel helper `WheelScroll @0x59822880` is live in the EDITOR as well. Helper shape: `[0x5983E100]` = current aowInt widget; if nil it fires the map scroll-up/down objects at `[0x5983E104]/[0x5983E108]` (returns 1=swallow, 0=passthrough); with a widget it dispatches by class — `[0x59815F9C]`→type 0 (scrollbar at [w+0x118]), `[0x5981848C]`→type 1 (at [w+0x120]), else type 2; the memo arm calls **SetListOff 0x59819298** (the function our memo clamp patches) and **always returns 1**, so the memo clamp cannot change the swallow/passthrough decision.

## Editor dark theme (Theme menu, APPLIED 2026-09-01, awaiting test)
`patch scripts/build_editor_dark_theme.py` (backup .bak_darktheme;
dry-run/--apply/--revert). Adds **Options → Theme → Classic/Dark** (radio
items, appended below Preview Mode — it is the LAST child of OptionsItem, so
plain TMenuItem.Add lands right under it). Dark ≈ modding-tools Fusion dark:
panels 0x383838, edit-like surfaces 0x252525, text 0xE0E0E0; Classic restores
clBtnFace/clWindow/clWindowText and, when OFF, the walker never touches a
control. Setting = registry named value **General\"Editor Theme"** ("1"=Dark)
via AoWEPACK rwString (delta from IAT [0x432E64]↔GetLanguage 0x55704B6C;
engine global 0x558FA048 → registry [engine+0x5C] — same machinery the
campaign-switch v7 stubs already prove works in the editor).
**Mechanism v2 (9/1):** init moved to a **FormCreate method-table repoint**
(the .xhub OnCreate pattern): TMainForm method table @0x004272EE ([VMT-0x28],
132 entries), FormCreate entry addr-dword at FILE 0x266F2 (orig 0x0042841C)
-> wrapper in .xthm (calls orig, then one-shot init). The DFM binds
OnCreate=FormCreate BY NAME (dfm +0x47C; zero code refs to 0x42841C), so
the repoint is authoritative. ⚠ The original tick-only design NEVER showed
the menu: **HSMEditUpdateFrame does not fire at startup** (evidently only
once a map is open) — the tick hook remains as the periodic dark-walker.
Plus ONE 6-byte hook on `TMainForm.HSMEditUpdateFrame` prologue
@**0x00428D18** (`55 8B EC 83 C4 9C`, reloc-free; eax=main form; compatible
with timerres — its bytes at 0x428D3F/0x4013C8 untouched) → new RWX section
**`.xthm` @VA 0x004E4000** (0x800; sections 9→10, SizeOfImage 0xE4000→0xE5000).
First tick: read setting, build menu, apply if dark. Every 8th tick while
dark: re-walk Screen.Forms → catches later-created dialogs in ~0.25 s.
**⭐ Editor-patching gold (AoWDevX uses VCL30 PACKAGES — everything is an
import, no signature hunting):** TMenuItem.Create[0x4324AC]/Add[0x432490]
(eax=parent,edx=item)/SetCaption[0x4324A8]/SetChecked[0x4324A4]/SetRadioItem
[0x43248C]; classref Menus..TMenuItem [0x4324BC]; TControl.SetColor
[0x43237C]; Forms.Screen ptr [0x432220]; @IsClass [0x432128]; LStrClr thunk
0x4037D0. VCL30 delta = [0x432210]−0x41336300 for non-imports
(TFont.SetColor 0x413294BC — **TFont.FColor=+0x14, setter self-checks**, no
repaint churn; classrefs TControl 0x4133FBB0 + edit-like table resolved from
exports at build time). D3 layouts: TControl.FFont=+0x50/FColor=+0x54;
TComponent.FComponents TList=+0x10; TScreen forms TList=+0x40; TMenuItem
FOnClick=+0x60 (VCL passes Data in eax → handler gets the theme id directly),
FItems TList=+0x40. TMainForm field table (VMT 0x425D00, table 0x425D92, 305 entries): HelpItem=+0x200, **OptionsItem=+0x204**, About1=+0x208, HSMEdit=+0x22C, PreviewMode640x4801=+0x2D4. ⚠ First cut used +0x208 (read the dword AFTER the name — the field-table offset PRECEDES the name, same trap as the AoWSetup xhub bug) and the Theme submenu landed under Help>About; user-caught 9/1, fixed. ⚠ keystone RESOLVES label immediates
(`mov [esi+0x60], _label` works — no two-pass needed).
Known limits: Windows-drawn chrome (title/menu bar, scrollbars, native
dialogs) stays light; buttons keep light faces with dark text (Win32 classic).

**⚠⚠ 9/1 CRASH LESSON (editor died at splash with "oh dear its the end"):**
a Delphi package export named "Unit..TClassName" **IS the VMT itself**, not a
pointer cell to it (proven live: AoWE..TArmy/..THero VMT slot dumps work
directly on the export address; also explains why an earlier ..TStringList
slot scan through a deref found nothing). Consequently: an IAT slot importing
such a symbol already holds the CLASS POINTER after one load — the theme
patch v2 double-dereferenced it and passed garbage to TMenuItem.Create →
exception in FormCreate. Distinguish from CELLS like [0x557130AC]/[0x55715A54]
(DATA variables that CONTAIN the VMT — those need the one deref). Rule:
"..TName" EXPORT address = VMT; a "ptr->..TName" data cell = deref once.

**9/1 SECOND crash cause (v4 still died): the LStrClr thunk 0x4037D0 was
borrowed from the MOUSE-TAB notes — which target AOWSETUP. In AoWDevX that
address is mid-instruction garbage; _readreg called it whenever the registry
read succeeded → AV at startup in every version (v3 additionally had the VMT
over-deref). AoWDevX @LStrClr thunk = 0x004010B0 (IAT 0x4320F4).
RULE: thunk/helper addresses are PER-BINARY — never carry one across exes;
re-derive from the target IAT every time. Also confirmed from VCL30 disasm:
D3 ctor convention = EAX=class, DL=flag, ECX=AOwner (TMenuItem.Create
passes ECX through untouched to TComponent.Create; the xor edx,edx there is
the inherited-flag=0, not the owner).
**9/1 FINAL: dark theme WORKED but user judged the look BAD -> REVERTED at
their request (hook + FormCreate MT entry restored, .xthm body zeroed, inert
header kept). Script `build_editor_dark_theme.py` stays as reference. Do NOT
re-apply unless asked.** Why it looked bad (for any future attempt): recolor
via TControl.Color/TFont.Color only gets partway in a Win32/D3 app -- the
menu bar, title bar, scrollbars, native dialogs and button FACES all stay
light, so the result is a patchwork rather than the modding tools' uniform
Fusion dark. A convincing editor dark mode would need owner-draw everything
or Windows dark-mode APIs that Delphi 3 predates -- out of proportion for a
1999-exe editor. All the RE in this section (menu creation via VCL30-package
imports, FormCreate MT wrapper, VMT-export rule, per-binary thunk rule, ctor
convention EAX=class/DL=flag/ECX=AOwner, the Screen.Forms/Components walker)
remains valid and reusable.


## Index note (moved verbatim from MEMORY.md 2026-09-21)
- [aowdevx-binary-notes.md](aowdevx-binary-notes.md) — editor title/icon sites, CODE-tail cave (full), .dlgd slack; **9/20 merged laptop notes: Item Properties HP/MV rows (.xitm), Developer prune menu + toolbar (.xprn v2 relocated field/method tables + DFM; section table FULL)**; **🛑 9/1 dark theme built, WORKED, then REVERTED (user: "it looks bad" — D3 chrome stays light ⇒ patchwork; do not re-apply). Kept for its RE gold: VCL30-package menu/ctor recipes, FormCreate MT wrapper, ..T*-export-IS-the-VMT rule, per-binary thunk rule.** **🔨 8/31 valgoto applied awaiting test** (Map Validation entries double-clickable → jump to tile; `.vgo` section; BXL port, all addresses re-verified; ⚠ fixed a timerres section-order footgun that would have destroyed `.vgo`). **🔨 8/31 timerres + render gate applied** (timeBeginPeriod(1) via Sleep-thunk hook/.tres in AoWDevX.exe; wall-clock render gate/.rgt in HSEPack.dpl @31 ms — fixes the sped-up animations timerres caused, since UpdateFrame has NO time base). MapDrawSteps 1→8 applied.


**DIAG (reverted same day; re-apply when an editor AV needs an address): `patch scripts\diag_devx_show_av_details.py` (backup `.bak_avdiag`)** — the editor's Application.OnException handler @0x4281EC shows "Oh dear, it's the end" + Terminate for EAccessViolation ([0x432474] classref) and the standard dialog for everything else; the `je 0x428225` @0x4281FE is now `jmp` so AVs show address/module. **Revert before any release cut.** Context: adding Holy/Unholy Champion or Evoker/Conjurer/Enchanter/Ritualist to a hero in the editor crashes (reported after patch_ml_cost_from_pfs_v1; unknown whether it predates it). Static findings: the hero form's add button (0x413B38) opens the ability-select dialog (class [0x40FFD4], owner = a temp TAbilityOwner at [dialog+0x214], NOT a unit); the dialog calls ability VMT+0xC4 CanExpand(owner) — for ML that is our cave_canexp 0x55812F00 (champions → IsClass TAbstractUnit fails → returns 0 = not offered), then +0x8C GetSourceName, +0x58 GetName(owner), +0xCC ExpandName, +0xC8 ExpandCost; OK → TAbilityOwner.AssignAb 0x5574F1E4 (copies ability DATA nodes, no ReadWrite) → form refresh 0x41321C. ML.GetLevel 0x557651D8 is patched (item-ability-levels cave 0x55812400 → 0x558124A0 is THero/TLeader-guarded, range-checked). TIntegerList.Put grows the list (SetCount), so the mlcost hook cannot index-fault. **RESOLVED:** AV at 0x55816B8E = casterru cave_expandnotify reading the engine global [0x558FA040] (nil in the editor) → patch_caster_research_upkeep_v1 v9 nil-guards the four notify caves (expand/herolist/upgrade/setplayer); applied 9/22, game launch OK, editor add-to-hero awaiting user test. Lesson: **any AoWEPACK cave that dereferences [0x558FA040]/[0x558FA044] must nil-check — the editor loads the same dll without an engine.**

**10/31 Abilities tab re-layout** (user: skill-point cost not visible unless desktop resolution changed): `patch_devx_ability_layout_v1.py` APPLIED (.bak_ablayout) — TMAINFORM Settings>PageControl3>AbilitySheet>Panel3 column: Skill Points box (AbilityLevelPointBox) moved from y512 to top (4), others tightened; column ends y492 (was 565). In-place int edits of the DFM at the tail of .xprn. ⚠ re-run after terrain palette / sky polish rebuilds of TMAINFORM.
**10/31 Spells tab re-layout** (user: combat info cut off): `patch_devx_spell_layout_v1.py` APPLIED (.bak_spelllayout; reuses patch_devx_ability_layout_v1 with SHEET/LAYOUT swapped) — Panel9 column: Description 4/120, Combat Info (SpellInfoGroup) 128/180, Settings 312, SFX+GFX side by side at 500/56 → ends y556 (was 713).
