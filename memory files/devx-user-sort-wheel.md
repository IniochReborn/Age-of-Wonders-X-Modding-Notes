---
name: devx-user-sort-wheel
description: "2026-11-07 editor Heroes/Items \"U\" sort button (User entries first, then name) + wheel only scrolls the map while the cursor is over it (v1.6: VCL30 LL arrow-key arm redirected in memory); APPLIED, awaiting user test"
metadata:
  node_type: memory
  type: project
  originSessionId: 64f9d834-ce56-42d3-b058-494a867c0e87
  modified: 2026-11-07T22:10:45.500Z
---

**Request 11/07:** U sort button after sort-by-level (Heroes, then also Items); wheel must only scroll the map when the cursor is over the map view.

**AoWEPACK** `patch_devx_hero_sort_user_v1.py` (.bak_herosortu, surgical revert): sort mode byte [grid+0x1EC] (0 name / 1 level|type) → new mode 2 in cave 0x558E1700..0x558E1880 (318 B used). Hero switch @0x55809477 (UpdateHeroes 0x558093E4), item switch @0x55808274 (UpdateItems 0x558081F8). User = [hero+0x90]==-1 / [item+0x24]==-1 (GetLibraryHero/Item). cmp fns get INDICES into [map+0xF8] THeroControl / [map+0xF4] TItemControl, map = [[0x558E9494]]. Ties → original name cmp 0x558092FC / 0x5580807C.
⚠ pefile only lists 10036 AoWEPACK exports — HeroCtrl/ItemCtrl ones are missing; parse the export table manually.

**Editor** (patch_devx_screenshot_v1 v4 + aowxshot_missing v1.5): DFM SortUserBtn (HeroPnl) / SortItemUserBtn (ItemsPnl), purple Arial-28 "U" glyph; the 7 buttons repacked at width 46 (lefts 2,58,104,150,208,254,300; panels are 357 wide). The AoWxShot click handler sets mode 2 and then calls Update* (resolved via GetProcAddress). Grids: hero [form+0x3AC], item [form+0x39C].

**Wheel v1.6 (v1.5 WH_MOUSE filter FAILED, user retest):** ⭐ MEASURED on a live editor: THSMEdit IGNORES WM_MOUSEWHEEL (SendMessage x3 → scrollbar unchanged); it pans ONLY on arrow keys (VK_DOWN +4 each; posted down/up pairs in a burst coalesce to one step). VCL30's WH_MOUSE_LL chord proc plain-wheel arm @0x413A8F60 (`call 0x413A90B2` VK lookup from table 0x413E7170 = 26/28 / `call 0x413A90DD` keybd_event / jmp 0x413A909B pass-through) synthesizes them; key counter [0x413E7168] was 186 after use → **the 8/31 "no keys synthesized" probe was WRONG** (keys go to the FOCUSED window: map pans while hovering panels; clicking the Scanner kills map scrolling).
Fix (AoWxShot Init, editor process only, VCL30 file + game untouched): patch5 that call IN MEMORY → `llwheel` (runs on the LL hook thread; ebx = VCL delta, edx = VK row): VK via the hook's lookup; GetCursorPos (NOT the LL pt — the editor is DPI-virtualised, the main form reports 1365 px wide) → WindowFromPoint → class THSMEdit → PostMessage WM_KEYDOWN/UP(VK) to the map; else nothing; then the pass-through. The WH_MOUSE hook was removed. Tests: `test_aowxshot_wheel_emu.py` ALL OK; live check: [0x413A8F60] = E9 → AoWxShot, 0 exceptions. Awaiting user test.

**v1.7 tilt (user: after clicking the minimap only normal scroll worked, not side scroll):** the TILT arm @0x413A8EF2 (same `call lookup` shape, rows 0x413E7176/79 → Left/Right) is now patched too → `lltilt` = llwheel with exit 0x413A90A5 (swallow tail; the vanilla tilt arm always swallows). Live check: both arms E9 → AoWxShot, 0 exceptions. USER-CONFIRMED v1.6 wheel 11/07; tilt awaiting test.

Next free AoWEPACK cave after this: 0x558E1880. See [[devx-missing-resources]], [[mouse-wheel-scrolling]].

**v1.8 level chord (11/14, user: "add the map level mouse hotkey from the game to the editor"):** game hotkey = Mouse5 + wheel → PgUp/PgDn (VK table rows +2/+5). AoWxShot now also patches the CHORD wheel arm @0x413A8F6F in memory → `llchord`: VK 0x21/0x22 with TMainForm or TScannerFloater in the foreground → PostMessage WM_TIMER (wParam 0x4C56<<16|VK, lParam = `lvl_tp`) → main thread calls LevelUpBtnClick 0x429ED8 / LevelDownBtnClick 0x429D80 (eax = form); other chord VKs take the original path. Init registers a dormant SetTimer(NULL,0,0x7FFFFFFF,lvl_tp) so Windows accepts the posted callback. Emu tests ALL OK; live: site patched, posted WM_TIMER switched Surface→Caverns→Depths→Caverns (by me, background driver). Real mouse chord awaiting user test. Backup backup\AoWxShot.dll.bak_lvlchord.

**v1.9/v1.10 (11/14) more editor hotkeys, all in AoWxShot (aowxshot_missing.py):** (a) hex grid: WH_GETMESSAGE hook on the main thread, removed WM_KEYDOWN F5 → xor byte [[0x43289C]]+0xCA (same flag as the game's F5; plain middle click already synthesizes F5); DrawGrid image cave 0x5581F800 imm patched in memory to the registry "Hex Grid Thickness" (#93/#92/#7). ⚠ WH_KEYBOARD does NOT fire for posted key messages (first attempt untestable) → WH_GETMESSAGE. (b) fog: Mouse4 (X1, state bit0 @VCL 0x413E7150) + wheel → WM_TIMER id MAGIC|1 → FogofWarClick wrapper 0x4E92D7, 250 ms debounce. (c) brush size: Mouse4 + tilt L/R (lltilt) → ids 2/3 → size byte [THSMEdit+0x1AC] 1/2/3/7 cycles with wrap: SetDown 0x402318 + Brush1/2/3BtnClick 0x4296A4/B4/C4 (Brush4 = component after Brush3Btn, handler Brush3BtnClick). Live-verified by me through posted messages (grid draws, fog toggles, brush 3→7→1→2); user 11/14: level/grid/fog "seems to work"; brush awaiting test. Editor exits with code 0 during my tests were the user closing the window, not crashes.
