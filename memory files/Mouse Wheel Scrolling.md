# Mouse Wheel Scrolling

**One-line:** Add mouse-wheel scrolling to Delphi/Win32 scrollbars in both the game (AoWx.exe) and editor (AoWDevX.exe) via a single WH_MOUSE hook installed in the shared Delphi-3 runtime VCL30.dpl, which translates the wheel into WM_VSCROLL / WM_HSCROLL.

**Status:** Editor CONFIRMED WORKING (vertical + horizontal, Shift-aware). In-game custom-UI scrolling was investigated and SHELVED (the WH_MOUSE hook does not fire inside the game process — see Landmines). This doc / patch = the shipped "editor v2" state. Backup: `VCL30.dpl.bak_wheel`.

---

## File patched
- **VCL30.dpl** — ImageBase `0x41300000`, CODE section raw offset `0x400`, RVA `0x1000` → **VA = file_offset + 0x41300C00**. Shared by the game, the editor, and tools (all import & call `Forms.TApplication.Run`). CODE is R+X with a large tail-zero cave from ~VA `0x413A8306`.

## Root cause
Both apps are **Delphi 3**. Delphi 3 predates VCL mouse-wheel support (added in D4): `TControl`/`TWinControl` have zero `WM_MOUSEWHEEL` handling. The wheel therefore only worked where **Windows itself** scrolls (native Win32 listbox / memo / treeview / listview). Delphi-drawn scrolling (TScrollBox, auto-scroll TForm, custom grids) got nothing.

## RE findings
- **Install site — `TApplication.Run` @VA `0x4133BC9C`.** `Run` executes once per process, so no re-entry guard is needed. Its 7-byte prologue `55 8B EC 51 89 45 FC` (`push ebp; mov ebp,esp; push ecx; mov [ebp-4],eax`) is stolen for the detour.
- **The wheel arrives as a thread message** `WM_MOUSEWHEEL` (0x20A) that a thread-level `WH_MOUSE` hook can see, carrying a `MOUSEHOOKSTRUCTEX`: `pt` at `+0x00/+0x04`, `mouseData` at `+0x14` (delta = HIWORD, read via `movsx word [edx+0x16]`).
- **Scrollbar discovery is by window style, walking the parent chain:** `WindowFromPoint(pt)` → then `GetWindowLongA(GWL_STYLE)` tested for `WS_VSCROLL` (0x200000) / `WS_HSCROLL` (0x100000); if absent, `GetParent` and repeat. This uniformly covers Delphi `TScrollingWinControl`/`TScrollBox`/auto-scroll forms **and** native Win32 controls.
- **Scroll is driven via standard messages:** 3× `SendMessageA(hwnd, msg, code, 0)` then `SB_ENDSCROLL` (8), where `msg` = `WM_VSCROLL` (0x115) / `WM_HSCROLL` (0x114) and `code` = `SB_LINEUP/LEFT` (0) when delta>0 else `SB_LINEDOWN/RIGHT` (1). 3 lines per notch. The hook then returns 1 to swallow the message (no double-scroll on native controls).
- **Shift-aware:** `GetKeyState(VK_SHIFT=0x10)`; Shift down → primary axis HORIZONTAL, else VERTICAL; the other axis is the fallback if the primary scroll style isn't found.

**IAT slots used** (all pre-imported by VCL30, so no new imports): GetCurrentThreadId `0x413E43E8`, SetWindowsHookExA `0x413E463C`, WindowFromPoint `0x413E45FC`, GetWindowLongA `0x413E4758`, GetParent `0x413E4784`, SendMessageA `0x413E468C`, CallNextHookEx `0x413E4894`, GetKeyState `0x413E47B4`.

## The patch
Three changes (see byte table below):

1. **HOOK @ `TApplication.Run`** — file `0x3B09C` / VA `0x4133BC9C`. 7-byte prologue `55 8B EC 51 89 45 FC` → `E9 5F CB 06 00 90 90` (`jmp cave_B` + 2 NOP). `E9` rel32 = `0x0006CB5F`; target = `0x4133BCA1 + 0x6CB5F = 0x413A8800` = cave_B.

2. **cave_A (MouseProc callback)** — file `0xA7800` / VA `0x413A8400`, **348 bytes**. `stdcall MouseProc(nCode, wParam, lParam)`, `ret 0xC`. Uses only eax/ecx/edx + an ebp frame (`sub esp,0x40`), so ebx/esi/edi are auto-preserved. If `nCode != 0` (HC_ACTION) or `nCode < 0` or `wParam != 0x20A` → `CallNextHookEx(0,…)` passthrough. Otherwise: read delta + point, `GetKeyState(VK_SHIFT)` to pick primary axis, run an internal `FIND(mask)` that walks the parent chain for `WS_VSCROLL`/`WS_HSCROLL`; try primary mask, then secondary; if none → passthrough; if found → `DOSCROLL` (3× SendMessage + ENDSCROLL) and return 1 (swallow).

3. **cave_B (installer)** — file `0xA7C00` / VA `0x413A8800`, **36 bytes**. `pushad; call [GetCurrentThreadId]; push eax (tid); push 0 (hMod); push 0x413A8400 (lpfn=cave_A); push 7 (WH_MOUSE); call [SetWindowsHookExA]; popad;` then the stolen prologue `55 8B EC 51 89 45 FC`; then `jmp 0x4133BCA3` (Run+7). `hMod = 0` is legal because the proc is in-process and `tid` is the current thread. Return value (hhook) is ignored; if `SetWindowsHookEx` fails it is a silent no-op.

### Byte / cave table
| # | File offset | VA | Size | Old | New |
|---|---|---|---|---|---|
| 1 HOOK | `0x3B09C` | `0x4133BC9C` | 7 | `55 8B EC 51 89 45 FC` | `E9 5F CB 06 00 90 90` |
| 2 cave_A | `0xA7800` | `0x413A8400` | 348 | `00…00` (zero-fill) | MouseProc (see patch .py) |
| 3 cave_B | `0xA7C00` | `0x413A8800` | 36 | `00…00` (zero-fill) | installer (see patch .py) |

cave_B full bytes: `60 FF15 E8433E41 50 6A00 68 00843A41 6A07 FF15 3C463E41 61 55 8BEC 51 8945FC E9 7F34F9FF`.

**Binary verification:** diffing `VCL30.dpl.bak_wheel` → live `vcl30.dpl` yields exactly these three ranges; the accompanying apply-script reproduces the live file byte-for-byte.

## Mechanism (summary)
`Run` detours once into cave_B, which installs a thread-local `WH_MOUSE` hook (cave_A) and then continues normally. Every subsequent `WM_MOUSEWHEEL` on the pumping thread enters cave_A, which finds the scrollable HWND under the cursor and drives it with standard scroll messages, swallowing the original.

## Landmines & notes
- **Editor v2 = shipped state.** cave_A is 348 B and cave_B is 36 B at `0x413A8400` / `0x413A8800`. (Earlier drafts placed the installer at `0x413A8500`; it was moved to `0x413A8800` to give cave_A room. Do not assume the older address.)
- **In-game scrolling does NOT work and was reverted out.** Diagnostic MessageBoxes proved the `WH_MOUSE` hook *never fires* in the game (AoWx.exe) process, while it fires fine in the editor. Root cause is upstream: the game likely reads mouse via a path a thread-level `WH_MOUSE` hook doesn't see (DirectInput / a render surface that never gets `WM_MOUSEWHEEL`), or installs the hook on a non-pumping thread. If revisited, **fix hook delivery first** (verify Run runs & installs on the pumping thread in-game; try `WH_MOUSE_LL` or hooking the game's real WndProc / message pump) before touching any in-game scroll code. The in-game (`aowInt.dpl`) scroll helper that was prototyped is fully reverted — `aowInt.dpl` is clean.
- Only affects real HWND scrollbars. Fully custom engine-drawn "scroll" widgets that aren't HWNDs (in-game screens, editor map view) are unaffected.
- Terminates safely: the parent walk ends at top-level (`GetParent` → 0), no cycles. `ret 0xC` balances the stdcall stack; registers preserved.

## Revert
Restore `VCL30.dpl.bak_wheel` (single file).
