---
name: borderless-fullscreen-feature
description: "APPLIED 2026-08-11, awaiting user test — \"FullScreen (Borderless)\" entry in Video settings (WS_POPUP windowed at desktop res). Full RE of TVideoDialog/TMainForm/DisplayC + the new-PE-section + private-import-table technique for AoWx.exe."
metadata: 
  node_type: memory
  type: project
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-11T08:10:46.559Z
---

**STATUS: ✅ v2 USER-CONFIRMED WORKING 2026-08-11 ("perfect"). List entry
renamed to "Fullscreen (Optimized)" at user request.** v1 re-laid-out the game
at desktop res; user wanted the picture IDENTICAL to windowed (same map
viewport/event window) stretched to fill → v2 = render at windowed size +
stretch + mouse scaling. Still untested: Win11 laptop at 300% DPI.
Scripts: `patch scripts/build_borderless_fullscreen.py` (AoWx.exe, backup
`AoWx.exe.bak_borderless`) + companion `patch scripts/build_bfs_mouse_dcpack.py`
(Dcpack.dpl, backup `Dcpack.dpl.bak_bfsmouse`). Both dry-run default,
`--apply`/`--revert`. Smoke-tested: v2 launches and runs.

**v2 STRETCH DESIGN:** while borderless, RESTYLE clears doAutoResizeBackSurface
(bit0 of [display+0x185]) before the resize → back surface stays at windowed
size → game keeps windowed layout. Per-frame present = ExecuteBltSurfaceEvent
(0x55105340; DFM BackSurfaceControlMode=bmBltSurface → DC vcall+0x84
BltSurface(edx=[disp+0x194] surface idx)) → DIB surface blt (VMT+0x24 =
0x55106200) = full **StretchDIBits(surface → DC rect+0x30)** → auto-scales.
(Dirty-block path BltInvalidatedSurface VMT+0x88 blits 1:1 — NOT used in our
config; would need scaling if BackSurfaceControlMode ever changes.)
UNRESTYLE sets the bit back before restoring the saved rect.
**Mouse** (Dcpack.dpl caves @0x55108400, PIC, identity when surf==client):
S1 TCustomDisplay.WndProc 0x551051DC entry (bytes 55 8B EC 51 53) — scales
WM_MOUSE* (0x200-0x209) lParam by surf/client (surf=[ctl+0x18C/0x190],
client=[ctl+0x38/0x3C] TControl FWidth/FHeight); S2 TDisplayCtrl.GetMousePos
0x55103FC0 entry (53 56 57 55 83 C4 D8) — wrap+scale out-params (ctl =
[DC+0x2C]). DC VMT slots: +0x84 BltSurface, +0x88 BltInvalidatedSurface,
+0x98 GetMousePos. GetMouseAboveSurface is screen-space (GetWindowRect) —
unaffected. Dcpack CODE tail has ~24KB zeros from 0x551083FB (cave space);
Dcpack VA = file + 0x55100C00.

**ROOT CAUSE (corrects earlier 300%-DPI theory):** NOT DPI-specific — every
Windows 8+ machine. Windows dropped 16bpp display modes system-wide; AoW is a
16bpp game, so exclusive fullscreen's DirectDraw enumeration (16bpp filter) is
always empty on Win10/11 → resolution list shows only "Desktop Window".
Windowed works because DirectDraw color-converts 16bpp→32bpp during the blit.
The "Reduced color mode (16-bit)" compat checkbox does NOT restore enumeration
(tested __COMPAT_LAYER=16BITCOLOR). Diag script: scratchpad ddraw_diag.py.

**ARCHITECTURE (all names from aowsyms VMT scan — see [[bxl-reference]] re_tools):**
- Main window = VCL `TMainForm` (DFM in AoWx.exe RCDATA; dumped w/ scratchpad
  dfm_dump.py). Child `Display: TDisplay` (Dcpack.dpl DisplayC unit, base
  0x55100000) with **Align=alClient + doAutoResizeBackSurface**: any window
  resize → TCustomDisplay.Resize → ResizeBackSurfaces + OnResizeBackSurface →
  TMainForm.DisplayResizeBackSurface (0x45385C, min 640x480, NO upper cap) →
  TGeneral.ResetLayout. Windowed pipeline natively supports ANY size; window
  is user-resizable (WM_SIZING min-size handler @0x4537A8).
- PrimaryDC=WinDC (TWindows16DC, works), SecondaryDC=DXDC (TDDrawFullScr16DC,
  dead on Win8+). TMainForm fields: +0x1DC Display, +0x1E0 WinDC, +0x1E4 DXDC.
  Active DC = [Display+0x1A8]; fullscreen ⇔ activeDC==DXDC.
- MainForm global: **[[0x45A168]]** (ptr-to-ptr). TVideoDialog ctrl:
  [[0x45A478]]; fields +0x70 listbox (+0x114 TStrings, +0x120 ItemIndex),
  +0x8C TDisplayModeList, +0x90 mode byte, +0x9C/A0 current res.
- TVideoDialog.ApplyBtnClick 0x40B65C reads selected item's OBJECT: -1 =
  Desktop Window → windowed apply 0x40B298(0,0); else mode index → fullscreen.
  Populator 0x40B08C AddObjects entries (vcall TStrings+0x38). Selection
  finder 0x40B5CC (windowed → 0, fullscreen → IndexOfObject(modeidx)).
- Boot: FormCreate 0x453184 restores MainWindowState + MainWindowPosition
  (windowed size/pos!) + GetDisplayMode (0x401F24 thunk, its ONLY caller);
  registry Get/SetDisplayMode do NOT clamp → value 2 round-trips. FormDestroy
  0x453910 derives saved DisplayMode: fullscreen-active?1:0 (thunk 0x401F2C).

**IMPLEMENTATION (patch = 7 sites + new PE section, all AoWx.exe):**
Borderless = stay on WORKING windowed DC, restyle form WS_POPUP+screen-size
(SetWindowLongA/SetWindowPos; GetSystemMetrics for size). Game re-renders
natively at desktop res (no stretching). Registry: DisplayMode=2.
- **NEW SECTION `.xbfs`** RVA 0x20D000 (VA 0x60D000), raw appended at EOF,
  chars 0xE0000060: relocated import-descriptor table (Borland emits ~239
  descriptors, one per unit, OFT=0; terminator = Name==0) + appended
  **private user32 descriptor** → loader fills OUR IAT slots at fixed VAs:
  SetWindowLongA [0x60E2F0], SetWindowPos [0x60E2F4], GetSystemMetrics
  [0x60E2F8]. DataDirectory[1] repointed. No runtime GetProcAddress.
  Data: FLAG byte 0x60E350 (0 or 2), SAVED_RECT 0x60E354 (VCL l,t,w,h),
  Delphi string const "Fullscreen (Optimized)" @0x60E370 (hdr -1,len).
  Caves 0x60E390-0x60E587; **free .xbfs space from 0x60E590 to 0x60F000** —
  reusable by future AoWx.exe patches (technique reusable for other modules).
  ⚠ AoWx.exe had a GHOST 7th section header slot @file 0x2E8 (stripped debug,
  loader-ignored since NumberOfSections=6) — overwritten by our header.
**BOOT-ZOOM FIX (2026-08-11, took 3 iterations — final design verified by
ReadProcessMemory probe + registry round-trip):** root cause chain: the game
NEVER persists its windowed size (MainWindowPosition is read at FormCreate but
no code ever writes it; General\rectangles holds only internal-window rects) —
every boot the window is the 640x480-client default, so any boot-time
"apply borderless" pins 640x480 surfaces → zoom. Toggling worked because it
used the live client size. Fixes, all in AoWx.exe .xbfs:
(1) Boot apply moved from FormShow (too early: VCL applies sizes/maximize
AFTER OnShow) to a ONE-SHOT at **TMainForm.DisplayUpdateFrame entry (site E
0x452E50, bytes 55 8B EC 83 C4 A0, resume 0x452E56)** guarded by PENDING byte
(FLAG+1 = 0x60E351) — first frame = window fully shown, same state as manual
toggle. (2) **Render size persisted in General\rectangles\100** (TRect
l,t,r,b): CAVE6A (FormDestroy) saves (0,0,surfW,surfH) via SetRectangle thunk
0x401EF4 when FLAG set; CAVE5 restores via GetRectangle thunk 0x401EEC
(registry obj = [[0x45DF74]]+0x5C), sanity ≥640x480 else fallback to form
ClientWidth/Height (thunks 0x4015F4/0x4015FC), then
SetBackSurfaceWidth/Height (thunks 0x4030BC/0x4030C4) + RESTYLE. TRect
scratch TMP in .xbfs. (3) Title scene forces mode 2 at boot; mode manager
0x40B390 **no-active-DC branch (0x40B4AF, boot only)** would SetBackSurface
640x480 explicitly (bypasses frozen option bit) → site H (8A 83 90 00 00 00)
→ CAVE7: if FLAG → jmp 0x40B5A2. In-session mode 1/2 with windowed DC active
never touches surfaces — why toggling always worked. VERIFIED: memory probe
(scratchpad probe_bfs.py — ReadProcessMemory of FLAG/surf/client) shows boot
surfaces = registry value; exit-save round-trip confirmed (invalid seed
0,0,100,100 → rejected at boot → exit rewrote real size). Probe tool kept.
- Sites: A 0x40B0E4 populator→CAVE1 (AddObject obj=-2 after Desktop Window);
  B 0x40B68C apply→CAVE2 (-2: SAVERECT+FLAG:=2+RESTYLE→windowed path; -1 or
  real mode while FLAG: clear+UNRESTYLE first); C 0x40B5CC finder entry→CAVE3
  (⚠ the jne there is SHORT 75xx — that's why entry detour, re-implements
  active-DC check; windowed+FLAG → IndexOfObject(-2)); D 0x4534DA FormCreate
  GetDisplayMode call→CAVE4 (2→FLAG:=2, return 0 so controller mode-2 intro
  machinery never sees it); E 0x453A80 FormShow entry→CAVE5 (FLAG →
  SAVERECT+RESTYLE at boot); F 0x453910 FormDestroy entry→CAVE6A (FLAG →
  write SAVED_RECT back into form VCL bounds fields +0x30..0x3C BEFORE the
  layout save, so registry keeps pre-borderless rect; no user32 at exit);
  G 0x4539DD windowed SetDisplayMode(0) call→CAVE6B (SetDisplayMode(FLAG)).
- Styles: borderless 0x96000000 (POPUP|VISIBLE|CLIPCHILDREN|CLIPSIBLINGS);
  restore 0x16CF0000 (OVERLAPPEDWINDOW|VISIBLE|CLIP*). SWP flags 0x24
  (NOZORDER|FRAMECHANGED). Form HWND via TWinControl.GetHandle thunk 0x40164C
  on [[0x45A168]].
- LAN-safe (pure presentation). Known cosmetic edges: window previously
  maximized keeps Windows' internal maximized flag; un-restyle then shows
  normal borders at saved rect.

**TEST CHECKLIST (user):** new entry listed; apply → fills screen, no border;
mouse coords correct; game relayouts to desktop res; toggle back to Desktop
Window restores old window; survives restart (DisplayMode=2); check at 300%
DPI on laptop (GetSystemMetrics returns virtualized size there — DWM scales,
should still fill screen).


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- ✅ [borderless-fullscreen-feature.md](borderless-fullscreen-feature.md) — **"Fullscreen (Optimized)"** user-confirmed 8/11: Video-settings entry, renders at WINDOWED size, StretchDIBits-scaled to fill screen, mouse rescaled in Dcpack.dpl caves (@0x55108400; ~24KB more free there). Root cause: **Win8+ has no 16bpp modes at all** (not DPI). Holds the **new-PE-section + private-import-table recipe** (`.xbfs` @0x60D000; free cave ~0x60E5C0-0x60F000; user32 IAT slots 0x60E2F0/F4/F8). Laptop 300%-DPI test pending.
