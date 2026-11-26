---
name: mouse-wheel-scrolling
description: "Mouse-wheel scrolling, COMPLETE 2026-08-11: editor Win32 scrollbars + every in-game aowInt list/memo, leader-portrait cycling, and swallowing so an AHK wheel-to-arrows remap cannot also scroll the map. Game never gets WM_MOUSEWHEEL (render window is never focused) so it needs WH_MOUSE_LL owned by a DEDICATED THREAD (on the render thread it cost frame rate + cursor ghosting)."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-09-01T00:07:01.262Z
---

## ★★ IN-GAME WHEEL — COMPLETE & USER-CONFIRMED 2026-08-11.
Works everywhere asked for: map-select/load list, hero level-up + leader-setup
parallel lists (abilities + cost column + thumb in sync), unit-window
description tab (TAOWMemo), magic window lists, events log; leader-setup
PORTRAIT CYCLING via the wheel; and handled wheels are SWALLOWED so the user's
AutoHotkey wheel->arrow remap no longer scrolls the map underneath a list.
Frame rate/cursor lag resolved (round 4). Clean (non-diag) build
applied to both files. Backups: aowInt.dpl.bak_wheel, VCL30.dpl.bak_wheelpump.
**MEASURED FACTS that decided the design** (via `patch scripts/wheel_probe.py`,
which reads live counters out of the running AoWx.exe — rebuild with `--diag`
on both scripts to re-enable them):
  pump hits 346 | **wheel msgs 0** | move sweeps 144 | inside-listbox 75
→ the pump hook and hover tracking work perfectly, but **the app NEVER receives
WM_MOUSEWHEEL**: Windows routes wheel to the FOCUSED window and this game's
render window never becomes focused (it does get WM_MOUSEMOVE). So any
queue/WndProc-based approach is impossible — this also explains the 2026-07-22
"WH_MOUSE never fires" dead end. Only a **WH_MOUSE_LL** hook sees the wheel.
**⚠ PERF TRAP (cost two rounds of user-reported regressions):** a global
WH_MOUSE_LL fires for EVERY system mouse event **on the installing thread** —
~1000 callbacks/sec from a gaming mouse ⇒ FPS drop + cursor ghosting.
Round-1 mitigation (install only while hovering, Unhook on leave) helped in
gameplay but still dipped inside menus. **SUPERSEDED by round 4: own the hook
on a dedicated thread** — that removes the cost entirely, so the hover gating
was dropped and the hook is now permanent. See ROUND 4 below.
**⚠⚠ CROSS-FILE COUPLING — bit me once, cost a whole test round:** VCL30's pump
AND its LL proc both gate on a **signature byte = WheelScroll's FIRST byte**
(`cmp byte [aowbase+0x22880], SIG`) so a reverted/absent aowInt half can never
be called into. Rewriting the helper's prologue (push ebx → **push ebp**)
changed that byte 0x53→0x55 and **silently killed wheel scrolling everywhere**
(no crash, just nothing). `HELPER_SIG` in build_wheel_vcl_pump.py must track
build_wheel_aowint.py's prologue — BOTH files must be re-applied together.

**ROUND 4 (8/11) ✅ USER-CONFIRMED: "frame rate is fixed, everything works" — PERF: hook moved to its own thread.**
Root of the remaining FPS dip: **WH_MOUSE_LL callbacks run on the thread that
INSTALLED the hook**, and a gaming mouse reports ~1000 events/s, so the game's
render thread was servicing 1000 callbacks/s AND all system mouse input waited
on it (that is the cursor ghosting — input is delayed until the owning thread
gets round to its message pump). ⚠ NOTE: *we* never poll; the report rate is
the MOUSE's. Lowering the mouse to 500 Hz in its driver halves the callbacks
and genuinely helps, but it is a system-wide setting, so fix it in code:
- **New dedicated hook-owner thread** (cave 0x413A8C00, created once from the
  pump via CreateThread IAT 0x413E41E8): installs WH_MOUSE_LL and then does
  nothing but `WaitMessage` + drain `PeekMessageA` forever. Idle CPU ≈ 0, and
  it answers callbacks instantly, so the render thread is out of the input path.
- **LL proc now does almost nothing** (and must not touch UI — wrong thread):
  if armed (g_hover || g_facenext) it adds the notch to **G_PENDING 0x413E7140**
  and `PostMessageA(G_HWND, WM_NULL)` to wake the game thread, then swallows.
- **Pump (game thread)** captures a real HWND from msg.hwnd into G_HWND
  0x413E7144, starts the thread once (G_THREADED 0x413E7148), and drains
  G_PENDING by calling WheelScroll — so all UI work still happens on the game
  thread. The wake-up post is what makes scrolling work when the mouse is
  perfectly still (a wheel alone posts no message).
- Hook is now installed permanently (cheap, since it is off-thread), so the old
  install/uninstall-on-hover gating is gone. New VCL30 globals live in **.idata
  tail slack 0x413E713C (196B zeros)** because DATA's 44B slack is full.

**ROUND 3 (8/11) ✅ USER-CONFIRMED — memo + portrait + swallow:**
- **Unit-window DESCRIPTION tab** = `T2Memo : TAOWMemo`. Memos mirror listboxes
  with DIFFERENT offsets: scrollbar `[memo+0x120]` (list 0x118), top-line
  `[memo+0x128]` (list 0x15c), Update @0x59819B18, SetListOff @0x59819298.
  WheelScroll now CLASSIFIES the hovered control by VMT (listbox 0x59815F9C /
  memo 0x5981848C / other) and uses the right offsets + Update/SetListOff.
  2nd hover latch hooked at **TAOWMemo.CheckMouseMove @0x5981A29A** (same
  7-byte `mov [ebx+0x78],-1` marker as the listbox).
- **LEADER PORTRAIT CYCLING**: no scrollable control sits under the portrait,
  so a 3rd latch hooks **TAOWImage.CheckMouseMove inside-branch @0x59815882**
  (steals 6B `mov al,[ebx+0xc0]`): it climbs ≤3 parent levels and scans
  children for TAOWButtons (VMT 0x59810DC0) whose **OnClick code ptr
  `[btn+0x138]`** equals `TLeaderSetupWin.FaceNextBtnClick 0x00416D54` /
  `FacePrevBtnClick 0x00416D0C` (⚠ CORRECTION 8/31: AoWx.exe **does** have a
  .reloc with 11911 entries — but `DllCharacteristics = 0`, no ASLR, ImageBase
  0x400000, so it never rebases and the fixed-address assumption still holds;
  see [[unitwindow-party-arrows]]), latching them in g_facenext/g_faceprev
  (0x5983E104/8, cleared each sweep by the CLR hook). With nothing scrollable
  hovered, WheelScroll fires that button's OnClick (edx=Sender, eax=[btn+0x13C],
  call [btn+0x138]; assigned iff word[btn+0x13A]!=0). Wheel up = prev face.
  The pump arms the LL hook on `g_hover || g_facenext`. **Button OnClick lives
  at +0x138/+0x13A/+0x13C — different from the scrollbar's +0x6C/+0x6E/+0x70.**
  ⚠ Only probes +0x138 after a VMT match, so it never reads past a small object.
- **SWALLOW when handled**: the LL proc now returns 1 instead of chaining if
  WheelScroll scrolled/acted. This stops the user's AutoHotkey "wheel = arrow
  keys" remap from ALSO scrolling the map while the cursor is over the events
  window or any list. Unhandled wheels still chain normally.
- aowInt caves relocated into the big CODE tail-zero run **0x598229B9..0x5983D200
  (~107 KB)**: helper 0x59822880 (480B), SET2 0x59823200, SET3 0x59823400,
  CAVE_END 0x59823600.

**LEVEL-UP / PARALLEL-LIST FIX (8/11, user-confirmed working):** RE'd the exact
wiring — **THeroUpgradeDlg.AvailableAbilitiesSBChange @0x00447030** does
`SetListOff([form+0x80] abilities, [ [form+0x84] SB +0x148 ].FPos)` then the
same for `[form+0x98]` (the COST column). So those lists have **no linked
scrollbar** ([lb+0x118]==0); the SB drives them through the form's OnChange.
WheelScroll now has 3 cases: (1) list owns a scrollbar → drive it; (2) **no
scrollbar → find the governing TAOWVScrollBar SIBLING** and drive that, so the
form's handler syncs every column + the thumb; (3) neither → SetListOff.
Sibling search: parent `[lb+0x10C]` → children TList `[parent+0xD0]` (data +4,
count +8); a child is a scrollbar iff `[child] == VMT 0x5980C594`
(`AoWVScroll..TAOWVScrollBar`, verified: its +0x84 slot = TAOWVScrollBar.
CheckMouseDown); require vertical overlap and pick the nearest one at/right of
the list's left edge (dialogs have several bars). Control geometry:
left/top = [+0x84]/[+0x88], w/h = [+0x7C]/[+0x80]. Component children list is
created in TAoWComponent.Create @0x59802318 (three TLists: +0xD0 children,
+0xDC, +0xE0). Helper is now 314B (cave limit 0x59822A00).

**(superseded) earlier limitation:** hero level-up / abilities screens hang SEVERAL
parallel lists (abilities + cost column) off ONE scrollbar, synced only inside
the scrollbar's OnChange handler. The hovered list scrolls but the cost column
and thumb stay put. Helper already replicates the arrow-click sequence
(TAOWVScrollBar.CheckMouseDown @0x5980D8BC: FPos-=FSmall, redraw flag
[sb+0xa4]=0, then **OnChange via method ptr code@[sb+0x6c]/data@[sb+0x70],
assigned iff word[sb+0x6e]!=0**) — still didn't sync, so those lists likely
have **no linked scrollbar** ([lb+0x118]==0, we take the SetListOff fallback)
and the governing TAOWVScrollBar must be found another way (walk the parent's
children for a TAOWVScrollBar sibling, then drive IT). NEXT STEP if revisited:
run the --diag probe on that screen and read `no-scrollbar fb` vs the
event-fired counter to confirm before writing the sibling search.

## (build detail) IN-GAME WHEEL REBUILT 2026-08-11
User asked for wheel scrolling in the **map-select / load-game window**. That
dialog = `TFileDlgWindow` (AoWx.exe DFM @file 0xD67CC) whose list is
**`FileLB : TAOWListBox`** (+ SaveLB/DateLB, and TAOWVScrollBar SSBar/NSBar) —
i.e. the aowInt custom toolkit, confirming the shelved analysis below.
**ROOT-CAUSE FIX for the old blocker:** stop relying on the WH_MOUSE hook
(proven never to fire in-game). Instead tap the VCL message pump the game
demonstrably runs (AoWx.exe imports Forms.TApplication.Run):
- **`Forms.TApplication.ProcessMessage` @0x4133BA48** (private; called by
  HandleMessage 0x4133BB08) does PeekMessageA then `cmp dword [esp+8],0x12`
  (WM_QUIT) @**0x4133BA6D — exactly 5 bytes** → replaced with `call cave`.
  TMsg @[esp+4]: .message=[esp+8], .wParam=[esp+0xC]; inside the cave after
  `pushad` those are [esp+0x2C]/[esp+0x30]; after `popad` the displaced cmp
  must use **[esp+0xC]** (return address on top). `ret` preserves flags for the
  caller's `je`. Cave @0x413A8A00 (81B), PIC; `GetModuleHandleA("aowInt.dpl")`
  (IAT 0x413E43BC) → base+0x22880, guarded by a **signature byte check
  (0x53)** so a reverted aowInt half can't be called. No-op in editor/tools.
  Message is NOT swallowed (nothing in D3 handles it; DefWindowProc is inert).
- **aowInt.dpl** (`build_wheel_aowint.py`, bak aowInt.dpl.bak_wheel): rebuilt
  the shelved design — g_hover @0x5983E100 (DATA slack; **file = VA−0x59801A00**,
  CODE file = VA−0x59800C00 — different section deltas!), CLR hook @0x59807094
  (steal 6B prologue), SET hook @0x598175C5 (steal 7B `mov[ebx+0x78],-1`,
  ebx=listbox, cursor-inside branch), **WheelScroll(delta) @0x59822880**
  (stdcall ret 4 → eax=1): SetFPos(vs=[lb+0x118], FPos∓3) @0x5980CA28 +
  TAOWListBox.Update @0x59817138. All PIC (call/pop delta), intra-module rel32.
- Old WH_MOUSE caves (0x413A8400/0x413A8800) left INTACT for editor Win32
  scrollbars; if that hook ever swallows a wheel first, the pump hook simply
  doesn't see it → no double-scroll. Backups: VCL30.dpl.bak_wheelpump (new,
  distinct from .bak_wheel), aowInt.dpl.bak_wheel.
- SCOPE: TAOWListBox only (any in-game list: map select, load/save, and likely
  level-up/unit lists). TAOWComboBox/TAOWMemo would need their own SET hooks.

**GOAL:** Scroll wheel didn't work over many editor scrollbars (and game scrollbars). ROOT CAUSE: the apps are **Delphi 3** (VCL30.dpl) — Delphi 3 predates VCL mouse-wheel support (added in D4). Confirmed VCL30 has zero `WM_MOUSEWHEEL` handling in TControl/TWinControl. So the wheel only worked where **Windows itself** scrolls (native Win32 listbox/memo/treeview/listview) — that was the "sometimes it works." Delphi-drawn scrolling (TScrollBox, auto-scroll TForm, custom grids) got nothing.

**FIX (VCL30.dpl, shared by game+editor+tools; backup `VCL30.dpl.bak_wheel`).** Install a thread-local **WH_MOUSE hook** at startup whose callback translates the wheel into `WM_VSCROLL` on the scrollable window under the cursor. One patch fixes BOTH AoWx.exe (game) and AoWDevX.exe (editor) — both import & call `Forms.TApplication.Run`. VCL30 imagebase 0x41300000, VA = file + 0x41300C00. CODE section is R+X with ~231KB tail-zero cave space from ~VA 0x413A8306.

- **Install hook @ TApplication.Run (VA 0x4133BC9C):** stole 7-byte prologue `55 8bec 51 8945fc` (push ebp;mov ebp,esp;push ecx;mov[ebp-4],eax) -> `e9 <rel> 90 90` = jmp installer cave. Run runs once per process => no re-entry guard needed.
- **Installer cave_B @0x413A8500 (36B):** `pushad; call [GetCurrentThreadId]; push eax(tid); push 0(hMod); push 0x413A8400(lpfn); push 7(WH_MOUSE); call [SetWindowsHookExA]; popad;` then stolen prologue; `jmp 0x4133BCA3` (Run+7). hMod=0 legal because proc is in-process & tid is current thread. Return value (hhook) ignored.
- **Hook callback cave_A @0x413A8400 (v2, 348B)** — stdcall `MouseProc(nCode,wParam,lParam)`, ret 0xC. Uses only eax/ecx/edx + ebp-frame locals (sub esp,0x40), so ebx/esi/edi auto-preserved. If `nCode!=0`(HC_ACTION) or `nCode<0` or `wParam!=0x20A`(WM_MOUSEWHEEL) -> `CallNextHookEx(0,...)` passthrough. Else lParam=MOUSEHOOKSTRUCTEX: delta=`movsx word[edx+0x16]` (mouseData@+20 HIWORD), pt@+0/+4. `WindowFromPoint(pt)`=starthwnd. **Shift-aware (v2):** `GetKeyState(VK_SHIFT=0x10)`; if Shift down -> primary axis = HORIZONTAL, else primary = VERTICAL; the other axis is the fallback. Internal subroutine `FIND(mask)` walks starthwnd's parent chain (`GetWindowLongA(GWL_STYLE=-16)` test mask; else `GetParent`) for a window with WS_VSCROLL(0x200000)/WS_HSCROLL(0x100000). Try primary mask; if none, try secondary; if still none -> passthrough. Found -> `DOSCROLL`: 3x `SendMessageA(hwnd, msg, code, 0)` + SB_ENDSCROLL(8), where msg=WM_VSCROLL(0x115)/WM_HSCROLL(0x114) and code = delta>0 ? 0(SB_LINEUP/LEFT) : 1(SB_LINEDOWN/RIGHT); return 1 (swallow). Net: plain wheel scrolls vertical (or horizontal if only-horizontal), Shift+wheel scrolls horizontal (or vertical if only-vertical). 3 lines/notch.

IATs used (all pre-imported by VCL30): GetCurrentThreadId 0x413E43E8, SetWindowsHookExA 0x413E463C, WindowFromPoint 0x413E45FC, GetWindowLongA 0x413E4758, GetParent 0x413E4784, SendMessageA 0x413E468C, CallNextHookEx 0x413E4894, GetKeyState 0x413E47B4. cave_B installer moved to 0x413A8800 (v2, was 0x413A8500) to give cave_A room.

**LIMITATION (confirmed by user test 2026-07-22):** works for editor Delphi/native scrollbars (vertical AND now horizontal). Does NOT work for the **in-game screens** (scenario selection, leader skill-points, load/save, hero level-up abilities, unit-abilities view) NOR the **editor map view** — these are **custom engine-drawn UI, not real HWND scrollbars** (WindowFromPoint returns the single game render window, no WS_*SCROLL style, so nothing to send WM_VSCROLL to). Fixing those needs engine-level RE of the game's own mouse/UI input. INVESTIGATED 2026-07-22 (below) — feasible, mechanism fully mapped, not yet built.

**IN-GAME CUSTOM UI — RE FINDINGS (aowInt.dpl, the game's UI pack; imagebase 0x59800000; the GAME AoWx.exe imports aowInt.dpl, NOT AoWInterface.dpl which is a stale copy @IB 0x400000).** The in-game screens use a custom widget toolkit, NOT HWND controls:
- Hierarchy: **TAOWWinManager** (root mouse dispatcher; singleton) -> **TAOWWindow** (screen/form) -> controls (**TAOWListBox**, TAOWButton, **TAOWVScrollBar**, etc.). Mouse routing is virtual: WinManager.CheckMouseDown @0x59806F10 iterates its window list [self+0xd0] (TList, .Get @0x598013E4), and for the window under (x,y) calls its virtual CheckMouseDown at **vtable slot +0x84** (cl,dl=buttons; stack: x=[ebp+8], y=[ebp+0xc]). No wheel method exists anywhere (Wheel=0 hits).
- **TAOWScrollBar/TAOWVScrollBar** field layout (aowInt): FPos @[+0x148], FMin @[+0x138], FMax @[+0x13c], FSmall @[+0x140], FNum @[+0x158], redraw-flag byte @[+0xA4]. Control base: pos @[+0x84]/[+0x88], size @[+0x7c]/[+0x80], parent @[+0x10c], visible byte @[+0x75]. **SetFPos @0x5980CA28** (eax=self, edx=newpos) clamps to [0, FMax-FMin-FNum+1] and sets redraw flag. Arrow-click scroll (in CheckMouseDown @0x5980D788): up-arrow does `FPos -= FSmall` (@0x5980D8C2), plus a notify call @0x598018D4 — i.e. changing FPos alone is NOT enough, the owning list must be notified/updated.
- **TAOWListBox** (the thing usually under the cursor): SetVScroll @0x59816938 (links its scrollbar), SetListOff @0x598168F4 (scroll offset), Update @0x59817138, CheckMouseDown @0x598171C4, CheckKeyPress @0x59817660 (list may respond to arrow/page keys).
- **PLAN (if built):** extend the existing VCL30 WH_MOUSE hook — when it finds NO HWND WS_VSCROLL under the cursor (the in-game case = the single game render window), call a NEW helper in aowInt that finds the scrollable control under (x,y) and scrolls it. Cleanest way to "find control under cursor" without re-walking the whole tree: hook the controls'/window's CheckMouseMove to stash a **g_lastHoveredScrollable global** (listbox/scrollbar the mouse is currently inside), then the wheel handler just scrolls that. Scroll = drive the existing arrow-click path (reuse notify) or SetFPos + the list's Update. Touches shared aowInt.dpl; requires in-game test iterations (only the user can test). STATUS: mapped, not yet implemented — awaiting decision on the build.

**IN-GAME SCROLL — SHELVED 2026-07-22. REVERTED: aowInt.dpl restored to clean; VCL30.dpl kept at working editor-scroll v2 (NO in-game path, NO diag). The aowInt implementation below was fully backed out.**

**CRUCIAL FINDING (why in-game never worked) — the WH_MOUSE hook does NOT fire in the GAME (AoWx.exe) process at all.** MessageBox-diagnostic test (boxes 0=wheel-reached-hook, A=in-game-path, B=aowInt-helper-called, C=list-found): in the EDITOR a single wheel produced boxes **0, A, B** (hook fires, reaches helper; no C = editor has no TAOWListBox, expected). IN THE GAME: **NO boxes at all** — so the VCL30 WH_MOUSE hook never fires in-game. Root cause is upstream of everything I built: either the game doesn't install the hook (TApplication.Run not the active loop / hook installed on a different thread than the one pumping in-game), or the game window never receives WM_MOUSEWHEEL through a path a thread-level WH_MOUSE hook sees (e.g. the game reads mouse via DirectInput and/or its in-game loop uses a surface that doesn't get wheel WM_). NOTE: user plays WINDOWED (so it's not fullscreen-exclusive suppression). **If revisited: FIRST fix hook delivery in-game** (verify TApplication.Run runs in the game & installs the hook on the pumping thread; try a WH_MOUSE_LL low-level hook or hooking the game's actual WndProc / message pump instead of relying on WH_MOUSE at Run) BEFORE touching the aowInt scroll code — the aowInt side (below) was verified correct in isolation and only failed because it was never reached. The editor path proves the aowInt helper chain (GetModuleHandle->helper) works when the hook fires.

**(SHELVED design, was fully built+reverted) — wheel scrolling for in-game TAOWListBox screens:** Design = hover-tracking global + reuse the game's own scroll path:
- **Scroll action** (the key discovery): `TAOWListBox.Update` @0x59817138 reads `VScroll.FPos` (=`[[listbox+0x118]+0x148]`) into the listbox display-offset [listbox+0x15c] and redraws. So scroll = `SetFPos(vscroll, FPos +/- 3)` (@0x5980CA28, clamps) then `listbox.Update()` (redraws). Listbox VScroll ptr @[listbox+0x118]. (TAOWListBox.CheckKeyPress is a stub — list doesn't do keys.)
- **g_hoverList global @ aowInt DATA slack VA 0x5983E100** (DATA is R+W, VSz 0x24, slack to 0x200; file 0x3C700).
- **aowInt caves (CODE @0x598227D6+ zeros; VA=file+0x59800C00... actually file=VA-0x59800000-0x1000+0x400):**
  - CLR @0x59822800 (21B): `g_hoverList=0` + stolen prologue + jmp back. Hooked from **WinManager.CheckMouseMove @0x59807094** (stole 6B `558bec83c4f4` -> jmp). Clears every mouse-move sweep.
  - SET @0x59822840 (18B): `g_hoverList=ebx(listbox)` + stolen `mov[ebx+0x78],-1` + jmp back. Hooked from **TAOWListBox.CheckMouseMove inside-branch @0x598175C5** (the point reached only when cursor is INSIDE the listbox; stole 7B `c74378ffffffff` -> jmp). So after each move, g_hoverList = listbox under cursor (or 0).
  - HELPER `WheelScroll(delta)` @0x59822880 (71B, stdcall ret 4, returns eax=1 if scrolled): read g_hoverList; if listbox && [listbox+0x118] vscroll: newpos = FPos + (delta>0?-3:+3); `SetFPos`; `listbox.Update`; ret 1. Else ret 0. Intra-module calls are rel32 (rebase-safe); g_hoverList ref is absolute (fixed-base assumption, like rest of project).
- **VCL30 hook cave_A v3 (401B @0x413A8400):** the no-HWND-scrollbar path (both V+H FIND fail) now, before passthrough, does `GetModuleHandleA("aowInt.dpl")` (@IAT 0x413E43BC); if loaded, `call [base+0x22880](delta)` (=WheelScroll); if it returns 1 -> swallow, else passthrough. **Safety: if aowInt not loaded (tools w/o it) GetModuleHandle=0 -> passthrough, helper never called** (emulation-verified). Editor unaffected (its VCL forms hit the HWND path; if it has no TAOWListBox, helper returns 0). aowInt base+RVA call is rebase-safe for the entry.
- **VERIFIED:** unicorn-emulated HELPER (down->FPos+3+SetFPos+Update+ret1; up->FPos-3; null/no-vscroll->ret0; ebx preserved) and VCL30 v3 all paths (HWND regression intact; aowInt-loaded+scroll->swallow; aowInt-loaded+decline->passthrough; aowInt-absent->safe passthrough; non-wheel->passthrough). Disasm-verified all hooks.
- **SCOPE/UNKNOWNS:** targets TAOWListBox only. Screens using TAOWMemo/TAOWHTMLMemo/TAOWComboBox or fully custom lists won't scroll yet (their VScroll field offset may differ from 0x118 — would need per-class SET hooks + helper branches). If a reported screen (scenario select, load/save, level-up abilities, unit abilities) is NOT a TAOWListBox, extend. Editor map view still separate (not a listbox). Requires in-game test; revert = restore both .bak_wheel.

**VERIFICATION:** unicorn-emulated both caves, all paths: wheel-down -> 3xWM_VSCROLL/SB_LINEDOWN+ENDSCROLL & swallow(ret1); wheel-up -> SB_LINEUP; non-wheel & no-scrollable-target -> CallNextHookEx passthrough; regs preserved, ret 0xC balances stack; installer hooks (7,cave_A,0,tid) & preserves Self(eax). Disasm-verified after apply. Walk terminates via OS window-tree (no cycles); GetParent hits 0 at top-level.

**SCOPE/CAVEATS:** Works for any window with WS_VSCROLL (Delphi TScrollingWinControl/TScrollBox/auto-scroll forms AND native Win32 listbox/memo/treeview — now uniformly via WM_VSCROLL, no double-scroll since original is swallowed). Does NOT help fully custom game-engine-drawn scroll widgets that aren't real HWNDs (if any exist in-game). If SetWindowsHookEx fails it's a silent no-op (no crash). To REVERT: restore `VCL30.dpl.bak_wheel` (single file).

Related: this is the shared VCL runtime — see [[active-patches.md]]. Other AoWDevX.exe work: [[editor-about-dialog.md]], [[editor-dialog-dir-memory.md]].


## Index blurb archived 2026-08-30 (compacted out of MEMORY.md; was current as of ~8/15)

- ✅ [mouse-wheel-scrolling.md](mouse-wheel-scrolling.md) — Wheel scrolling COMPLETE (editor scrollbars + ALL in-game lists, memos, leader portrait cycling; swallows handled wheels so an AHK wheel→arrows remap can't also scroll the map). ⚠ Game never receives WM_MOUSEWHEEL (render window never focused) ⇒ WH_MOUSE_LL, owned by a **dedicated thread** (on the render thread it cost FPS + cursor ghosting at ~1000 Hz mouse reports). ⚠ VCL30↔aowInt coupled by a signature byte.

## 2026-08-31 — EDITOR wheel made context-aware (`build_wheel_editor_context.py`, VCL30.dpl.bak_wheelctx)
**Symptom (user):** in AoWDevX the wheel scrolled a sidebar panel AND panned the map simultaneously. Surfaced right after the editor perf work (a ~2 ms pump makes the synthesized key stream obvious), but the cause is structural, not new.
**RE — TWO independent wheel hooks in VCL30 that don't know about each other:**
1. `cave_A @0x413A8400` = thread-level **WH_MOUSE** (our editor-scroll v2, absolute-IAT style): on 0x20A it does WindowFromPoint → parent-walk for WS_VSCROLL/WS_HSCROLL (finder @0x413A84DF, GetWindowLongA [0x413E4758]/GetParent [0x413E4784]) → SendMessageA WM_V/HSCROLL ×3 + SB_ENDSCROLL (sender @0x413A8514) → returns 1 = swallow. Shift swaps V/H priority. Installer stub @0x413A8800.
2. `@0x413A8D00` = **WH_MOUSE_LL** proc (the 402 mouse-hotkey/chord engine, PIC via call/pop ebx delta). Lazily resolves keybd_event/GetForegroundWindow/GetWindowThreadProcessId/GetCurrentProcessId into [ebx+0x413E7154/58/5C/60] (names @0x413A9169+), gates on foreground-window-is-our-process, counts events at +0x413E7164. Wheel arm @0x413A8F01: picks a VK from the **runtime table 0x413E7170** (up +0 / down +3; modifier bits at [0x413E7150] select +1/+2), `0x413A90B2` = VK lookup (edx = table VA), `0x413A90DD` = keybd_event down/up. Bail = 0x413A909B (passthrough), swallow = 0x413A90A5.
**A WH_MOUSE_LL hook runs at raw-input time, BEFORE the message is queued — so hook 1 swallowing the wheel cannot stop hook 2.** Hook 2's existing context gate @0x413A8F19..0x413A8F5A only consults **aowInt globals** ([ebx+0x413E27FC] = aowInt base; +0x3E100 current widget, +0x3E104, +0x3E10C, +0x3E148) — the 402 "context-aware" behaviour. ⚠ **The editor DOES load aowInt.dpl** but never activates game UI, so all four are nil, the gate always passes, and the map is panned on every notch.
**⚠ v1 OF THIS FIX USED THE WRONG DISCRIMINATOR (kept as the lesson).** v1 gated on "is there a WS_V/HSCROLL window under the cursor" — but scrollbar styles say nothing about where the synthesized keys LAND. A read-only runtime probe (`patch scripts/probe_editor_wheel.py`: class/styles/parent-chain/focus under the cursor) settled it 8/31:
  map = **`THSMEdit`** ← TPanel ← TMainForm — **no scrollbars anywhere in its chain**
  palette = `TEResourceGrid` (WS_VSCROLL) ← TTabSheet 'Places' ← TPageControl ← … ← TMainForm
  scanner = `TDisplay` ← **`TScannerFloater`** (a separate TOP-LEVEL window)
Plus: **neither HSEPack.dpl nor AoWDevX.exe contains ANY WM_MOUSEWHEEL (0x20A) handler** (both scanned) ⇒ the synthesized arrow keys are the ONLY editor map-scroll path, and **keybd_event delivers to the FOCUSED window**. The map pans via `HSMEdit.OnKeyDown = HSMEditKeyDown` (DFM; MainForm KeyPreview=True). That one fact explains both symptoms: hovering a side panel never moves focus → keys still reach THSMEdit → map pans while the panel scrolls (both at once); clicking the Scanner moves focus to TScannerFloater → keys go there → map dead until you click back into it.

**🛑 v2 CRASHED BOTH APPS INSTANTLY (user-hit, no dialog, straight to desktop) — THE LESSON: `VCL30.dpl` CODE IS `R-X`, NOT WRITABLE** (section chars 0x60000020, verified; DATA 0x413E1000 / BSS / .idata 0x413E4000 are the RW ones, chars 0xC000004x). v2 cached the resolved GetClassNameA pointer and scratch dwords **inside the code cave**, so the first wheel event stored into read-only memory → AV inside a WH_MOUSE_LL proc → process death with no exception dialog. v1 never crashed only because it was read-only by accident. **RULE: a VCL30/other R-X code cave may hold CODE AND CONSTANTS ONLY. Mutable state must go in a writable section (VCL30: DATA slack ~0x413E27D4+, .idata slack 0x413E7184+ — the engine's own LL-hook globals live at 0x413E7150-0x413E7180) or, better, on the STACK.**

**v3 (APPLIED 8/31, read-only cave, 267 B @0x413A9200, code @0x413A9230):** same decision logic as v2 but with ZERO writes — the 64-byte class-name buffer and the hwnd slot live in a `sub esp,68` stack frame, and GetClassNameA is resolved per event (GetModuleHandleA+GetProcAddress ≈ nothing next to a wheel notch) instead of cached. Frame: esp+0..63 buffer, +64 hwnd, +68 saved edi, +72 saved edx(VK table ptr); every exit path does `add esp,68 / pop edi / pop edx` so EDX (needed by the original send at 0x413A8F60) and EDI are restored on all paths, and the pre-push `_bail_early` exit jumps straight to 0x413A909B. IAT slots re-verified by name: WindowFromPoint 0x413E45FC, PostMessageA 0x413E46C8, GetModuleHandleA 0x413E43BC, GetProcAddress 0x413E43B4.

**v2 FIX (APPLIED 8/31):** displace the 13 bytes @0x413A8F53 (last aowInt check + `jne bail`) → cave @0x413A9200 (335 B: data cache/hwnd/vk + strings at +0, code @0x413A9260): replay the check, then decide **BY WHAT IS UNDER THE CURSOR** — `hwnd = WindowFromPoint(pt)`; if `GetClassNameA(hwnd) == "THSMEdit"` → VK via the hook's own lookup 0x413A90B2 → **PostMessageA WM_KEYDOWN/WM_KEYUP directly to that hwnd** (pans regardless of focus → fixes the Scanner symptom) → bail; elif `GetModuleHandleA("AoWDevX.exe")` → bail (editor, not the map ⇒ the side window scrolls alone); else → fall through to the original keybd_event send (**the GAME, unchanged**). GetClassNameA is NOT in VCL30's imports → resolved once via GetModuleHandleA("user32.dll")+GetProcAddress, cached in the cave; any resolve failure falls through to the original send (never worse than before). Chord arm @0x413A8F6F deliberately untouched (Mouse4/5+wheel are explicit bindings and must always fire). PIC ([ebx+VA] operands only); EDX (VK table ptr) preserved on every path, ESI (MSLLHOOKSTRUCT: pt.x +0, pt.y +4, wheel delta +8) and EDI never touched; displaced range reloc-free (asserted each run).


**⚠ 2026-11-07 CORRECTION:** the editor map DOES pan via the LL proc's synthesized arrow keys (counter [0x413E7168] = 186 on a live editor), and THSMEdit ignores WM_MOUSEWHEEL. The 8/31 "no keys" probe and the cave_A design built on it were wrong. Current fix: [[devx-user-sort-wheel]] (AoWxShot redirects the 0x413A8F60 arm in memory, editor only).
