#!/usr/bin/env python3
r"""
AoWxShot.dll - "Missing resources" part (2026-11-07), assembled into the DLL by build_aowxshot.py.

User: "add a button between validate and screenshot ... an X instead of a checkmark ... sometimes i download a usermade
map that was made with a different mod ... resources (units, structures, etc) missing from the map. sometimes i can just
click through the errors, which removes the missing resources. but i want the X button to display a list of all
resources missing, what theyre called, and where theyre located (right click to center)".

RE (all verified on our files 11/07):
  * a map object whose resource id is not in the loaded HSS raises in HSEngine.TMapObject.ReadWrite (HSEPack 0x55609824):
    EMapObjectResourceMissing("Resource Missing <ClassName>: <ResourceID>"); a unit whose unit type index is unknown
    raises Exception("unit resource missing (<index>)") in AoWE.TUnit.ReadWrite (AoWEPACK 0x55782DB7).
  * the binary object reader Engine.TEReadStorageStream (Enginep) wraps every object in try/except:
      rwCreateEObject 0x55511434: creates the object, [obj+4] = owner (ecx param, kept in ESI), obj.ReadWrite; the
        handler frees the object and calls HandleError 0x55511398(reader, E) at 0x55511586 - prepared by
        `mov edx,ebx / mov eax,[ebp-4]` @0x55511581 (EBX = E, ESI = owner, [ebp-0x10] = class id)
      rwEObject 0x555116B0 (embedded objects): same handler shape @0x55511789 (ESI = the object itself)
    HandleError calls the reader's OnError (the editor's "click through" message); handled -> the object is dropped and
    loading continues.
  * map objects are children of their TMapField (TMapField.ReadWrite reads its HS list with owner = the field), so the
    owner chain [obj+4] of the failing object reaches the field: x [+0x10], y [+0x11], level [+0x12] (GetXYL).
  * every editor map load goes through TMainForm 0x4296D4(form, filename) (OpenBtnClick 0x4298A3 + the other caller
    0x42BF21).
DLL side (no file changes to Enginep / the game): Init(form) (called by the exe's FormCreate stub) wires OnClick of
ScreenshotBtn -> Run and MissingBtn -> the list, and patches IN MEMORY (VirtualProtect, bytes verified first):
    Enginep +0x11581 / +0x11789  `8B D3 8B 45 FC` -> jmp hook_a / hook_b (log, replay, jmp back)
    AoWDevX 0x4296D4           `55 8B EC 33 C9` -> jmp hook_o (clear the log, replay, jmp 0x4296D9)
The list = modeless dialog (CreateDialogIndirectParamA; the editor's Delphi loop dispatches its messages): one line
per dropped object "x, y (level) - <error text>"; right-click (WM_CONTEXTMENU from the list box + LB_ITEMFROMPOINT) or
double-click centres the map: SetMapLevel 0x429C68(form, level) + the editor's centre helper 0x4E9348 (eax = HSMEdit,
edx = x, ecx = y, push level: CenterView + PlayCenterAnimation).
Missing resources keep only their numeric id in a map file - their names live in the other mod's Release.hss - so the
list shows the object type (class) and resource id / unit type index.
"""
import struct

ENG_SITE_A, ENG_SITE_B = 0x1155C, 0x11789          # Enginep RVAs (image base 0x55500000)
ENG_BYTES_A = bytes([0x8B, 0x45, 0xF8, 0x8B, 0x00])  # handler entry: mov eax,[ebp-8] / mov eax,[eax] (object, before Free)
ENG_BYTES = bytes([0x8B, 0xD3, 0x8B, 0x45, 0xFC])
# v1.1 (user: "it says location unknown and doesnt center"): ESI is NOT the owner inside the except handler (Delphi
# handlers only trust frame locals - the unwinder leaves ESI clobbered), so hook A moved to the handler's first
# instruction where the failing object [[ebp-8]] is still alive: its [obj+4] = the owner set before ReadWrite (the
# TMapField for map objects; army -> field for units).  Hook B (embedded objects) logs without a location.
OPEN_SITE, OPEN_BYTES = 0x4296D4, bytes([0x55, 0x8B, 0xEC, 0x33, 0xC9])
# v1.2 (user: "still says location unknown ... units who are defenders inside an exploration site"): the defender army
# [site+0x34] is read EMBEDDED (rwEObject, owner nil) by ExploreS.TExplorationSite.ReadWrite, so a failing unit's
# owner chain dead-ends at the army.  Hook the site's ReadWrite right after its TStructure part (position read):
# AoWEPACK 0x557C1F9C `mov ecx,5` -> g_cursite = site; logit: chain dead-ends at [g_cursite+0x34] -> walk on from the
# site (a field child: [site+4] = its TMapField, like TMapObject.GetLhx).
SITE_RW, SITE_BYTES, SITE_ARMY = 0xC1F9C, bytes([0xB9, 0x05, 0x00, 0x00, 0x00]), 0x34
# v1.3 (user: "add a button to the taskbar to regenerate all units ... with a user confirmation" - Ziggurat maps keep
# Ziggurat-era abilities in every placed unit): RegenBtn -> for every registered unit ([AoWHSMap+0xFC] TUnitControl,
# list [uc+0x10]) whose class is exactly TUnit (heroes / leaders untouched) and that has a unit type [u+0x40]:
#   UnregisterEnchantments(u); SetUnitResource(u, nil) (TAbilityOwner.Clear); SetUnitResource(u, type) (default
#   abilities of every ability owner incl. medal / legendary sets, morale, HP / moves to max); RegisterEnchantments(u);
#   TUnit.Changed(u).  Type, medals, experience, owner kept.  Then: save, close and reopen the map.
REGEN = [("r_pmap", "AoWE.AoWHSMap@6B957A58"), ("r_tunit", "AoWE..TUnit@53822AF1"),
         ("r_setres", "AoWE.TUnit.SetUnitResource@23EDC2EF"), ("r_changed", "AoWE.TUnit.Changed@23EDC2EF"),
         ("r_reg", "AoWE.TAbstractUnit.RegisterEnchantments@23EDC2EF"),
         ("r_unreg", "AoWE.TAbstractUnit.UnregisterEnchantments@23EDC2EF")]
UNITCTRL = 0xFC
# v1.4 (user: "the new icons should be greyed out when a map isnt open"): the editor's map open / close paths call the
# prune patch's enable cave 0x4E92FD (ebx = form, dl = enabled; sites 0x42A19C close / 0x42A4BF open).  Init disables
# our 3 buttons and patches that cave's first 10 bytes (push edx / mov edx,[esp] / mov eax,[ebx+0x610]) IN MEMORY ->
# hook_e: SetEnabled(button, dl) for ScreenshotBtn / MissingBtn / RegenBtn (exe thunk 0x401550), replay, jmp 0x4E9307.
ENABLE_CAVE, ENABLE_RESUME = 0x4E92FD, 0x4E9307
ENABLE_BYTES = bytes([0x52, 0x8B, 0x14, 0x24, 0x8B, 0x83, 0x10, 0x06, 0x00, 0x00])
SET_ENABLED = 0x401550
SET_MAP_LEVEL, CENTER_HELPER = 0x429C68, 0x4E9348
# v1.5 (user: "add another sorting button (after sort by level) ... 'U' icon ... sort heroes by whether they are 'User' or
# not (and also sort alphabetically)"): SortUserBtn (Heroes tab, DFM by patch_devx_screenshot_v1) -> grid [form+0x3AC]
# (HeroCtrl.THeroControlGrid): sort mode byte [grid+0x1EC] := 2, UpdateHeroes.  Mode 2 is implemented in AoWEPACK by
# patch_devx_hero_sort_user_v1 (user heroes first, then by name); without it mode 2 simply lists unsorted.
HERO_GRID, HERO_SORTMODE = 0x3AC, 0x1EC
# + (user: "also add that 'User' sorting for items"): SortItemUserBtn -> item grid [form+0x39C] (ItemCtrl.TItemControlGrid,
# same sort-mode byte +0x1EC) + UpdateItems.
ITEM_GRID = 0x39C
# v1.6 wheel (user: "the mousewheel scrolls the map view no matter where the cursor is ... only ... while the cursor is
# within the boundaries of the map view" / v1.5 retest: "still scrolls the map no matter where cursor is ... if i click
# the minimap, the map no longer scrolls ... hover over sidepanels and scroll then both map and side panel scroll"):
# MEASURED 11/07 on a live editor: the map IGNORES WM_MOUSEWHEEL (SendMessage x3 -> scrollbars unchanged) and pans only
# on arrow keys (VK_DOWN x3 -> +12); VCL30's WH_MOUSE_LL chord proc synthesizes them - plain-wheel arm @0x413A8F60
# `call 0x413A90B2 (VK from table 0x413E7170: up 0x26 / down 0x28) / call 0x413A90DD (keybd_event down+up) / jmp
# 0x413A909B (pass through)` (key counter [0x413E7168] = 186 after use) - and keybd_event types into the FOCUSED window.
# (The 8/31 "no keys are synthesized" probe was wrong, and v1.5's WH_MOUSE filter on WM_MOUSEWHEEL therefore did nothing.)
# Fix, editor process only (VCL30.dpl file and the game untouched): Init patches that `call` IN MEMORY (bytes verified)
# -> llwheel (runs on the LL hook's own thread; ebx = VCL30 delta, edx = VK row): VK = the hook's own lookup; cursor
# (GetCursorPos - DPI-virtualised like WindowFromPoint; the LL struct pt is physical) over THSMEdit -> PostMessage
# WM_KEYDOWN/WM_KEYUP(VK) to the map (focus no longer matters); elsewhere nothing; then the original pass-through
# 0x413A909B, so side windows keep their own wheel scrolling.
VCL_LLARM, VCL_LOOKUP, VCL_BAIL = 0xA8F60, 0xA90B2, 0xA909B        # RVAs (VCL30 image base 0x41300000)
VCL_LLARM_BYTES = bytes([0xE8, 0x4D, 0x01, 0x00, 0x00])
# v1.7 (user: "if i click minimap, only the 'normal' scroll works on map and not the side scroll"): the TILT arm
# (WM_MOUSEHWHEEL) @0x413A8EF2 has the same `call lookup / call keybd_event` shape (rows tiltL 0x413E7176 / tiltR
# 0x413E7179 -> Left/Right arrows) but exits through the SWALLOW tail 0x413A90A5 -> lltilt = llwheel with that exit.
VCL_TILTARM, VCL_SWALLOW = 0xA8EF2, 0xA90A5
VCL_TILTARM_BYTES = bytes([0xE8, 0xBB, 0x01, 0x00, 0x00])
# v1.8 (user 11/14: "add the map level mouse hotkey from the game to the editor as well"): in the game Mouse5 + wheel
# sends PgUp / PgDn = map level up / down (VK table rows +2 / +5).  The CHORD wheel arm @0x413A8F6F (same `call lookup /
# call keybd_event / jmp swallow` shape) is patched in memory too -> llchord: VK 0x21 / 0x22 while the editor main form
# (or the Scanner floater) is the foreground window -> the level step must run on the MAIN thread (this is the LL hook
# thread), so a WM_TIMER carrying the callback lvl_tp is posted to that window (Windows only calls a posted timer
# callback that belongs to a live timer of the process -> Init registers a dormant SetTimer(NULL, 0, 0x7FFFFFFF,
# lvl_tp)); lvl_tp -> TMainForm.LevelUpBtnClick 0x429ED8 / LevelDownBtnClick 0x429D80 (eax = form; both test "map
# open" themselves and step in display order over the visible levels).  Every other chord VK (Mouse4 + wheel = P / N)
# takes the original path (lookup re-run with the return address 0x413A8F74).  The wheel event is swallowed as before.
VCL_CHORDARM, VCL_CHORDRET = 0xA8F6F, 0xA8F74
VCL_CHORDARM_BYTES = bytes([0xE8, 0x3E, 0x01, 0x00, 0x00])
ED_LEVELUP, ED_LEVELDOWN = 0x429ED8, 0x429D80
LVL_MAGIC = 0x4C56
# v1.9 (user 11/14: "add the F5/mousewheel click togglable hex grid to the editor" + "a mouse hotkey (mouse back +
# mousewheel) for toggling visibility fog button"):
#  * grid: the game's F5 flips byte [map+0xCA]; TAoWHSMap's draw (AoWEPACK 0x55778A78, shared with the editor) then calls
#    DrawGrid.  Init installs a WH_GETMESSAGE hook on the main thread: a removed WM_KEYDOWN F5 (no repeat) on the editor's main thread
#    with a map open -> xor byte [[0x43289C]]+0xCA.  Plain middle click already synthesizes F5 (VK table +12).
#    DrawGrid's image pick (cave 0x5581F800 `push eax / mov edx,7`, host-gated to AoWx.exe) is patched in memory to the
#    player's "Hex Grid Thickness" registry setting (3 -> #93, 1 -> #7, else #92), bounds/nil fallbacks kept.
#  * fog: chord wheel arm with Mouse4 (X1, state bit0 @VCL 0x413E7150) held -> WM_TIMER id MAGIC|1 -> main thread calls
#    the FogofWarClick wrapper 0x4E92D7 (eax = form; menu check + map + button), at most once per 250 ms.
#  * v1.10 brush size (user: "mouse hotkey for cycling between terrain size buttons ... Mouse Back + Mousewheel Tilt
#    Left/Right"): lltilt with Mouse4 held -> WM_TIMER id MAGIC|2 (tilt left = smaller) / MAGIC|3 (right = bigger) ->
#    main thread: size byte [THSMEdit+0x1AC] (1/2/3/7) -> index 0..3, +-1 wrapping, SetDown(button) + its OnClick
#    (Brush1/2/3BtnClick 0x4296A4/B4/C4; Brush4 = the component after Brush3Btn in Form.Components, handler =
#    Brush3BtnClick with Sender = Brush4 -> 7); at most one step per 200 ms (a held tilt repeats).
ED_BRUSH1CLICK, ED_SETDOWN, F_BRUSH1, HSM_BRUSH = 0x4296A4, 0x402318, 0x5F0, 0x1AC
ED_FOGCLICK, ED_PMAP, MAP_GRID = 0x4E92D7, 0x43289C, 0xCA
VCL_STATE = 0x413E7150
EPACK_HGCAVE_RVA = 0x11F800
REG_KEY, REG_VAL = "Software\\Triumph Studios\\Age of Wonders X\\General", "Hex Grid Thickness"
MAP_CLASS = b"THSMEdit"
FIELD_VMT_EXPORT = "HSEngine..TMapField@41E74B90"
MAXE, ESZ, MSGMAX = 600, 0x90, 0x80
ID_HDR, ID_LIST = 201, 202

IMPORTS = {
    "kernel32.dll": ["VirtualProtect", "IsBadReadPtr", "GetCurrentThreadId", "GetTickCount"],
    "advapi32.dll": ["RegOpenKeyExA", "RegQueryValueExA", "RegCloseKey"],
    "user32.dll": ["CreateDialogIndirectParamA", "DestroyWindow", "ShowWindow", "SendDlgItemMessageA", "SendMessageA",
                   "SetDlgItemTextA", "GetDlgItem", "ScreenToClient", "wsprintfA", "SetForegroundWindow",
                   "WindowFromPoint", "GetClassNameA", "PostMessageA", "GetCursorPos", "GetForegroundWindow",
                   "SetTimer", "SetWindowsHookExA", "CallNextHookEx"],
}


def mdlg_template():
    def w(s):
        return s.encode("utf-16-le") + b"\0\0"
    WS_CHILD, WS_VISIBLE, WS_TABSTOP = 0x40000000, 0x10000000, 0x10000
    items = [  # (class atom, style, x, y, cx, cy, id, text)
        (0x0082, WS_CHILD | WS_VISIBLE, 7, 6, 386, 20, ID_HDR, ""),
        (0x0083, WS_CHILD | WS_VISIBLE | WS_TABSTOP | 0x0001 | 0x0100 | 0x00200000 | 0x00100000 | 0x00800000,
         7, 28, 386, 176, ID_LIST, ""),
        (0x0080, WS_CHILD | WS_VISIBLE | WS_TABSTOP, 341, 210, 52, 14, 2, "Close"),
    ]
    style = 0x80000000 | 0x00C00000 | 0x00080000 | 0x40 | 0x0800        # POPUP|CAPTION|SYSMENU|SETFONT|CENTER
    b = struct.pack("<IIHhhhh", style, 0, len(items), 0, 0, 400, 230)
    b += b"\0\0" + b"\0\0" + w("Missing Resources") + struct.pack("<H", 8) + w("MS Shell Dlg")
    for cls, st, x, y, cx, cy, iid, text in items:
        while len(b) % 4:
            b += b"\0"
        b += struct.pack("<IIhhhhH", st, 0, x, y, cx, cy, iid)
        b += b"\xff\xff" + struct.pack("<H", cls) + w(text) + b"\0\0"
    return b


def data(D):
    for n in ("g_minit", "g_mdlg", "g_ncnt", "g_fieldvmt", "g_old", "g_ptx", "g_pty", "g_mform", "g_cursite",
              "g_try", "g_uc", "g_bshot", "g_bmiss", "g_bregen", "g_vlook", "g_vbail", "g_vswal", "g_vchret", "g_khook", "g_fogt", "g_brt", "g_gridpx", "g_hkey", "g_rsz", "g_hupd", "g_iupd") + tuple(n for n, _e in REGEN):
        D.var(n)
    D.var("g_ents", MAXE * ESZ)
    D.var("g_line", 0x200)
    D.add("x_eng", ENG_BYTES + bytes(3))
    D.add("x_enga", ENG_BYTES_A + bytes(3))
    D.add("x_open", OPEN_BYTES + bytes(3))
    D.add("x_site", SITE_BYTES + bytes(3))
    D.add("x_enab", ENABLE_BYTES + bytes(2))
    D.add("g_mtpl", mdlg_template())
    D.s("s_engp", "Enginep.dpl")
    D.s("s_btnregen", "RegenBtn")
    D.s("s_btnusort", "SortUserBtn")
    D.s("s_vcl", "VCL30.dpl")
    D.add("x_vcl", VCL_LLARM_BYTES + bytes(3))
    D.add("x_vclt", VCL_TILTARM_BYTES + bytes(3))
    D.add("x_vclc", VCL_CHORDARM_BYTES + bytes(3))
    D.s("s_regkey", REG_KEY)
    D.s("s_regval", REG_VAL)
    D.s("s_hupd", "HeroCtrl.THeroControlGrid.UpdateHeroes@23EDC2EF")
    D.s("s_btnisort", "SortItemUserBtn")
    D.s("s_iupd", "ItemCtrl.TItemControlGrid.UpdateItems@23EDC2EF")
    for n, e in REGEN:
        D.s("n_" + n, e)
    D.s("s_rgtitle", "Regenerate Units")
    D.s("s_rgask", "Regenerate all %d units on this map?\r\n\r\nEvery unit's abilities, hit points and moves are "
                   "rebuilt from its AoWx unit type (unit type, medals, experience and owner are kept). Heroes and "
                   "leaders are not changed.\r\n\r\nThis cannot be undone - keep a copy of the map file. Afterwards "
                   "save the map, then close and reopen it.")
    D.s("s_rgdone", "%d units regenerated.\r\n\r\nSave the map, then close and reopen it.")
    D.s("s_rgnone", "This map has no units to regenerate.")
    D.s("s_rgnomap", "Open a map first.")
    D.s("s_rgfail", "Regenerate Units: an AoWEPACK export was not found.")
    D.s("s_btnshot", "ScreenshotBtn")
    D.s("s_btnmiss", "MissingBtn")
    D.s("s_fieldvmt", FIELD_VMT_EXPORT)
    D.s("s_mtitle", "Missing Resources")
    D.s("s_none", "No missing resources were reported while loading the current map.\r\n\r\n"
                  "(The list is filled while a map is opened: every object the editor could not load - "
                  "and dropped after its error message - is recorded here.)")
    D.s("s_hdr", "%d object(s) could not be loaded when this map was opened (their resource is not part of this "
                 "mod) and were dropped. Right-click or double-click an entry to centre the map on it.")
    D.s("s_lxy", "x %3d, y %3d, level %d   -   %s")
    D.s("s_lno", "(location unknown)   -   %s")
    D.s("s_lmax", "... more than %d objects; only the first ones are listed")


def asm(v, a, imp, GD):
    return f"""
    initx:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov eax, dword ptr [esp + 0x14]
        mov {v('g_mform')}, eax
        cmp {v('g_minit')}, 0x0
        jne ix_out
        mov {v('g_minit')}, 0x1
        mov ebx, eax
        lea edx, [ebp + {a('s_btnshot')}]
        lea ecx, [ebp + on_shot]
        call setclick
        mov {v('g_bshot')}, eax
        lea edx, [ebp + {a('s_btnmiss')}]
        lea ecx, [ebp + on_miss]
        call setclick
        mov {v('g_bmiss')}, eax
        lea edx, [ebp + {a('s_btnregen')}]
        lea ecx, [ebp + on_regen]
        call setclick
        mov {v('g_bregen')}, eax
        lea edx, [ebp + {a('s_btnusort')}]
        lea ecx, [ebp + on_usort]
        call setclick
        lea edx, [ebp + {a('s_btnisort')}]
        lea ecx, [ebp + on_isort]
        call setclick
        xor edx, edx
        call setbtns
        lea eax, [ebp + {a('s_vcl')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz ix_novcl
        mov ebx, eax
        lea ecx, [ebx + {VCL_LOOKUP:#x}]
        mov {v('g_vlook')}, ecx
        lea ecx, [ebx + {VCL_BAIL:#x}]
        mov {v('g_vbail')}, ecx
        lea edi, [ebx + {VCL_LLARM:#x}]
        lea esi, [ebp + llwheel]
        lea ecx, [ebp + lw_tramp]
        lea edx, [ebp + {a('x_vcl')}]
        call patch5
        lea ecx, [ebx + {VCL_SWALLOW:#x}]
        mov {v('g_vswal')}, ecx
        lea edi, [ebx + {VCL_TILTARM:#x}]
        lea esi, [ebp + lltilt]
        lea ecx, [ebp + lw_tramp]
        lea edx, [ebp + {a('x_vclt')}]
        call patch5
        lea ecx, [ebx + {VCL_CHORDRET:#x}]
        mov {v('g_vchret')}, ecx
        lea edi, [ebx + {VCL_CHORDARM:#x}]
        lea esi, [ebp + llchord]
        lea ecx, [ebp + lw_tramp]
        lea edx, [ebp + {a('x_vclc')}]
        call patch5
        test eax, eax
        jz ix_novcl
        lea eax, [ebp + lvl_tp]
        push eax
        push 0x7fffffff
        push 0x0
        push 0x0
        call {imp('SetTimer')}
    ix_novcl:
        call gridinit
        call mhooks
        call baninit
        call fpinit
        call cninit
    ix_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x4

    on_shot:
        push eax
        call run
        ret
    on_miss:
        push eax
        call missing
        ret
    on_regen:
        push eax
        call regen
        ret

    on_usort:
        push ebp
        push ebx
        push esi
        push edi
        mov ebx, eax
        call {GD:#x}
        mov esi, {HERO_GRID:#x}
        lea edi, [ebp + {a('g_hupd')}]
        lea edx, [ebp + {a('s_hupd')}]
        call sortu
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret
    on_isort:
        push ebp
        push ebx
        push esi
        push edi
        mov ebx, eax
        call {GD:#x}
        mov esi, {ITEM_GRID:#x}
        lea edi, [ebp + {a('g_iupd')}]
        lea edx, [ebp + {a('s_iupd')}]
        call sortu
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret
    sortu:
        mov eax, dword ptr [edi]
        test eax, eax
        jnz su_have
        push edx
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        pop edx
        test eax, eax
        jz su_out
        push edx
        push eax
        call {imp('GetProcAddress')}
        test eax, eax
        jz su_out
        mov dword ptr [edi], eax
    su_have:
        mov eax, dword ptr [ebx + esi]
        test eax, eax
        jz su_out
        mov byte ptr [eax + {HERO_SORTMODE:#x}], 0x2
        call dword ptr [edi]
    su_out:
        ret

    llwheel:
        pushal
        call {GD:#x}
        mov ecx, {v('g_vbail')}
        jmp lw_go
    lltilt:
        pushal
        call {GD:#x}
        mov ecx, {v('g_vswal')}
        test byte ptr [ebx + {VCL_STATE:#x}], 0x1
        jz lw_go
        mov dword ptr [esp + 0x1c], ecx
        mov edi, 0x2
        cmp dl, 0x79
        jne lt_post
        inc edi
    lt_post:
        call {imp('GetForegroundWindow')}
        mov ebx, eax
        call isedwin
        test eax, eax
        jz lw_out
        lea eax, [ebp + lvl_tp]
        push eax
        or edi, {LVL_MAGIC << 16:#x}
        push edi
        push 0x113
        push ebx
        call {imp('PostMessageA')}
        jmp lw_out
    lw_go:
        mov dword ptr [esp + 0x1c], ecx
        mov eax, {v('g_vlook')}
        call eax
        test eax, eax
        jz lw_out
        mov edi, eax
        sub esp, 0x8
        push esp
        call {imp('GetCursorPos')}
        call {imp('WindowFromPoint')}
        mov ebx, eax
        call ismap
        test eax, eax
        jz lw_out
        push 0x1
        push edi
        push 0x100
        push ebx
        call {imp('PostMessageA')}
        push 0xc0000001
        push edi
        push 0x101
        push ebx
        call {imp('PostMessageA')}
    lw_out:
        popal
        jmp eax
    lw_tramp:
        nop
        nop
        nop
        nop
        nop

    llchord:
        push eax
        push eax
        pushal
        call {GD:#x}
        test byte ptr [ebx + {VCL_STATE:#x}], 0x1
        jz lc_x2
        mov edi, 0x1
        jmp lc_post
    lc_x2:
        mov eax, {v('g_vlook')}
        call eax
        cmp eax, 0x21
        je lc_lvl
        cmp eax, 0x22
        je lc_lvl
        mov eax, {v('g_vlook')}
        mov dword ptr [esp + 0x20], eax
        mov eax, {v('g_vchret')}
        mov dword ptr [esp + 0x24], eax
        popal
        ret
    lc_lvl:
        mov edi, eax
    lc_post:
        call {imp('GetForegroundWindow')}
        mov ebx, eax
        call isedwin
        test eax, eax
        jz lc_sw
        lea eax, [ebp + lvl_tp]
        push eax
        or edi, {LVL_MAGIC << 16:#x}
        push edi
        push 0x113
        push ebx
        call {imp('PostMessageA')}
    lc_sw:
        mov eax, {v('g_vswal')}
        mov dword ptr [esp + 0x20], eax
        popal
        ret 0x4

    isedwin:
        test eax, eax
        jz ie_no
        sub esp, 0x40
        mov edx, esp
        push 0x40
        push edx
        push eax
        call {imp('GetClassNameA')}
        mov eax, dword ptr [esp]
        mov edx, dword ptr [esp + 0x4]
        add esp, 0x40
        cmp eax, 0x69614d54
        jne ie_sc
        cmp edx, 0x726f466e
        je ie_yes
    ie_sc:
        cmp eax, 0x61635354
        jne ie_no
        cmp edx, 0x72656e6e
        jne ie_no
    ie_yes:
        mov eax, 0x1
        ret
    ie_no:
        xor eax, eax
        ret

    lvl_tp:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov ecx, dword ptr [esp + 0x1c]
        mov eax, ecx
        shr eax, 0x10
        cmp eax, {LVL_MAGIC:#x}
        jne lt_out
        mov eax, {v('g_mform')}
        test eax, eax
        jz lt_out
        xor edx, edx
        cmp cl, 0x1
        jne lt_up
        call {imp('GetTickCount')}
        mov ecx, eax
        sub ecx, {v('g_fogt')}
        cmp ecx, 0xfa
        jb lt_out
        mov {v('g_fogt')}, eax
        call mapopen
        test eax, eax
        jz lt_out
        mov eax, {v('g_mform')}
        mov ecx, {ED_FOGCLICK:#x}
        call ecx
        jmp lt_out
    lt_up:
        cmp cl, 0x2
        je lt_br
        cmp cl, 0x3
        je lt_br
        cmp cl, 0x21
        jne lt_dn
        mov ecx, {ED_LEVELUP:#x}
        call ecx
        jmp lt_out
    lt_dn:
        cmp cl, 0x22
        jne lt_out
        mov ecx, {ED_LEVELDOWN:#x}
        call ecx
    lt_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10

    lt_br:
        movzx esi, cl
        lea esi, [esi*2 - 0x5]
        call {imp('GetTickCount')}
        mov ecx, eax
        sub ecx, {v('g_brt')}
        cmp ecx, 0xc8
        jb lt_out
        mov {v('g_brt')}, eax
        call mapopen
        test eax, eax
        jz lt_out
        mov ebx, {v('g_mform')}
        mov eax, dword ptr [ebx + 0x22c]
        movzx eax, byte ptr [eax + {HSM_BRUSH:#x}]
        dec eax
        cmp eax, 0x3
        jb lt_bi
        mov eax, 0x3
    lt_bi:
        add eax, esi
        and eax, 0x3
        cmp eax, 0x3
        je lt_b4
        mov edi, dword ptr [ebx + eax*4 + {F_BRUSH1:#x}]
        shl eax, 0x4
        lea esi, [eax + {ED_BRUSH1CLICK:#x}]
        jmp lt_bgo
    lt_b4:
        xor edi, edi
        mov edx, dword ptr [ebx + 0x10]
        test edx, edx
        jz lt_out
        mov ecx, dword ptr [edx + 0x8]
        mov edx, dword ptr [edx + 0x4]
        mov eax, dword ptr [ebx + {F_BRUSH1 + 8:#x}]
        dec ecx
    lt_b4l:
        dec ecx
        js lt_out
        cmp dword ptr [edx + ecx*4], eax
        jne lt_b4l
        mov edi, dword ptr [edx + ecx*4 + 0x4]
        mov esi, {ED_BRUSH1CLICK + 0x20:#x}
    lt_bgo:
        test edi, edi
        jz lt_out
        mov eax, edi
        mov dl, 0x1
        mov ecx, {ED_SETDOWN:#x}
        call ecx
        mov eax, ebx
        mov edx, edi
        call esi
        jmp lt_out

    mapopen:
        mov eax, {v('g_mform')}
        test eax, eax
        jz mo_no
        mov eax, dword ptr [eax + 0x22c]
        test eax, eax
        jz mo_no
        cmp byte ptr [eax + 0x1bc], 0x0
        je mo_no
        mov eax, dword ptr [{ED_PMAP:#x}]
        mov eax, dword ptr [eax]
        ret
    mo_no:
        xor eax, eax
        ret

    kbproc:
        cmp dword ptr [esp + 0x4], 0x0
        jne kb_next
        test byte ptr [esp + 0x8], 0x1
        jz kb_next
        mov eax, dword ptr [esp + 0xc]
        cmp dword ptr [eax + 0x4], 0x100
        jne kb_next
        cmp dword ptr [eax + 0x8], 0x74
        jne kb_next
        test dword ptr [eax + 0xc], 0x40000000
        jnz kb_next
        pushal
        call {GD:#x}
        call mapopen
        test eax, eax
        jz kb_p
        xor byte ptr [eax + {MAP_GRID:#x}], 0x1
    kb_p:
        popal
    kb_next:
        push ebp
        call {GD:#x}
        push dword ptr [esp + 0x10]
        push dword ptr [esp + 0x10]
        push dword ptr [esp + 0x10]
        push 0x0
        call {imp('CallNextHookEx')}
        pop ebp
        ret 0xc

    gridinit:
        call {imp('GetCurrentThreadId')}
        push eax
        push 0x0
        lea eax, [ebp + kbproc]
        push eax
        push 0x3
        call {imp('SetWindowsHookExA')}
        mov {v('g_khook')}, eax
        lea eax, [ebp + {a('g_hkey')}]
        push eax
        push 0x20019
        push 0x0
        lea eax, [ebp + {a('s_regkey')}]
        push eax
        push 0x80000001
        call {imp('RegOpenKeyExA')}
        test eax, eax
        jnz gi_px
        mov {v('g_rsz')}, 0x4
        lea eax, [ebp + {a('g_rsz')}]
        push eax
        lea eax, [ebp + {a('g_gridpx')}]
        push eax
        push 0x0
        push 0x0
        lea eax, [ebp + {a('s_regval')}]
        push eax
        push {v('g_hkey')}
        call {imp('RegQueryValueExA')}
        test eax, eax
        jz gi_cl
        mov {v('g_gridpx')}, 0x0
    gi_cl:
        push {v('g_hkey')}
        call {imp('RegCloseKey')}
    gi_px:
        mov eax, {v('g_gridpx')}
        mov esi, 0x5c
        cmp eax, 0x3
        jne gi_a
        mov esi, 0x5d
    gi_a:
        cmp eax, 0x1
        je gi_out
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz gi_out
        lea edi, [eax + {EPACK_HGCAVE_RVA:#x}]
        cmp dword ptr [edi], 0x7ba50
        jne gi_out
        cmp dword ptr [edi + 0x4], 0xd8b0000
        jne gi_out
        lea eax, [ebp + {a('g_old')}]
        push eax
        push 0x40
        push 0x8
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz gi_out
        mov dword ptr [edi + 0x2], esi
        lea eax, [ebp + {a('g_old')}]
        push eax
        push {v('g_old')}
        push 0x8
        push edi
        call {imp('VirtualProtect')}
    gi_out:
        ret

    ismap:
        test eax, eax
        jz im_no
        sub esp, 0x40
        mov edx, esp
        push 0x40
        push edx
        push eax
        call {imp('GetClassNameA')}
        cmp dword ptr [esp], 0x4d534854
        jne im_no2
        cmp dword ptr [esp + 0x4], 0x74696445
        jne im_no2
        cmp byte ptr [esp + 0x8], 0x0
        jne im_no2
        add esp, 0x40
        mov eax, 0x1
        ret
    im_no2:
        add esp, 0x40
    im_no:
        xor eax, eax
        ret

    regen:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov eax, dword ptr [esp + 0x14]
        mov {v('g_mform')}, eax
        call {imp('GetActiveWindow')}
        mov {v('g_hwnd')}, eax
        mov eax, {v('g_mform')}
        mov eax, dword ptr [eax + 0x22c]
        test eax, eax
        jz rg_nomap
        cmp byte ptr [eax + 0x1bc], 0x0
        je rg_nomap
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz rg_fail
        mov ebx, eax
        lea edx, [ebp + {a('n_r_pmap')}]
        push edx
        push ebx
        call {imp('GetProcAddress')}
        test eax, eax
        jz rg_fail
        mov {v('r_pmap')}, eax
        lea edx, [ebp + {a('n_r_tunit')}]
        push edx
        push ebx
        call {imp('GetProcAddress')}
        test eax, eax
        jz rg_fail
        mov {v('r_tunit')}, eax
        lea edx, [ebp + {a('n_r_setres')}]
        push edx
        push ebx
        call {imp('GetProcAddress')}
        test eax, eax
        jz rg_fail
        mov {v('r_setres')}, eax
        lea edx, [ebp + {a('n_r_changed')}]
        push edx
        push ebx
        call {imp('GetProcAddress')}
        test eax, eax
        jz rg_fail
        mov {v('r_changed')}, eax
        lea edx, [ebp + {a('n_r_reg')}]
        push edx
        push ebx
        call {imp('GetProcAddress')}
        test eax, eax
        jz rg_fail
        mov {v('r_reg')}, eax
        lea edx, [ebp + {a('n_r_unreg')}]
        push edx
        push ebx
        call {imp('GetProcAddress')}
        test eax, eax
        jz rg_fail
        mov {v('r_unreg')}, eax
        mov eax, {v('r_pmap')}
        mov eax, dword ptr [eax]
        test eax, eax
        jz rg_nomap
        mov eax, dword ptr [eax + {UNITCTRL:#x}]
        test eax, eax
        jz rg_none
        mov {v('g_uc')}, eax
        xor edi, edi
        xor esi, esi
    rg_c:
        mov eax, {v('g_uc')}
        mov eax, dword ptr [eax + 0x10]
        cmp esi, dword ptr [eax + 0x8]
        jge rg_cd
        mov eax, dword ptr [eax + 0x4]
        mov eax, dword ptr [eax + esi*4]
        call rg_isunit
        add edi, eax
        inc esi
        jmp rg_c
    rg_cd:
        test edi, edi
        jz rg_none
        push edi
        lea eax, [ebp + {a('s_rgask')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        push 0x134
        lea eax, [ebp + {a('s_rgtitle')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        push {v('g_hwnd')}
        call {imp('MessageBoxA')}
        cmp eax, 0x6
        jne rg_out
        xor edi, edi
        xor esi, esi
    rg_l:
        mov eax, {v('g_uc')}
        mov eax, dword ptr [eax + 0x10]
        cmp esi, dword ptr [eax + 0x8]
        jge rg_done
        mov eax, dword ptr [eax + 0x4]
        mov ebx, dword ptr [eax + esi*4]
        mov eax, ebx
        call rg_isunit
        test eax, eax
        jz rg_n
        push dword ptr [ebx + 0x40]
        mov eax, ebx
        call {v('r_unreg')}
        mov eax, ebx
        xor edx, edx
        call {v('r_setres')}
        pop edx
        mov eax, ebx
        call {v('r_setres')}
        mov eax, ebx
        call {v('r_reg')}
        mov eax, ebx
        call {v('r_changed')}
        inc edi
    rg_n:
        inc esi
        jmp rg_l
    rg_done:
        push edi
        lea eax, [ebp + {a('s_rgdone')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        lea eax, [ebp + {a('g_line')}]
        mov edx, 0x40
        call rg_msg
        jmp rg_out
    rg_none:
        lea eax, [ebp + {a('s_rgnone')}]
        mov edx, 0x40
        call rg_msg
        jmp rg_out
    rg_nomap:
        lea eax, [ebp + {a('s_rgnomap')}]
        mov edx, 0x40
        call rg_msg
        jmp rg_out
    rg_fail:
        lea eax, [ebp + {a('s_rgfail')}]
        mov edx, 0x10
        call rg_msg
    rg_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x4

    rg_isunit:
        test eax, eax
        jz ru_no
        mov ecx, dword ptr [eax]
        cmp ecx, {v('r_tunit')}
        jne ru_no
        cmp dword ptr [eax + 0x40], 0x0
        je ru_no
        mov eax, 0x1
        ret
    ru_no:
        xor eax, eax
        ret

    rg_msg:
        push edx
        lea ecx, [ebp + {a('s_rgtitle')}]
        push ecx
        push eax
        push {v('g_hwnd')}
        call {imp('MessageBoxA')}
        ret

    setclick:
        push esi
        push edi
        xor eax, eax
        mov esi, dword ptr [ebx + 0x10]
        test esi, esi
        jz sc_o
        mov edi, dword ptr [esi + 0x8]
        mov esi, dword ptr [esi + 0x4]
    sc_l:
        dec edi
        js sc_none
        mov eax, dword ptr [esi + edi*4]
        push eax
        mov eax, dword ptr [eax + 0x8]
        test eax, eax
        jz sc_n
        push edx
        push ecx
        call streq
        pop ecx
        pop edx
        test eax, eax
        jz sc_n
        pop eax
        mov dword ptr [eax + 0xa4], ecx
        mov dword ptr [eax + 0xa8], ebx
        jmp sc_o
    sc_n:
        pop eax
        jmp sc_l
    sc_none:
        xor eax, eax
    sc_o:
        pop edi
        pop esi
        ret

    streq:
        push esi
        push edi
        mov esi, eax
        mov edi, edx
    se_l:
        mov al, byte ptr [esi]
        cmp al, byte ptr [edi]
        jne se_no
        inc esi
        inc edi
        test al, al
        jnz se_l
        mov eax, 0x1
        jmp se_r
    se_no:
        xor eax, eax
    se_r:
        pop edi
        pop esi
        ret

    mhooks:
        lea eax, [ebp + {a('s_hse')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz mh_e
        lea edx, [ebp + {a('s_fieldvmt')}]
        push edx
        push eax
        call {imp('GetProcAddress')}
        mov {v('g_fieldvmt')}, eax
    mh_e:
        lea eax, [ebp + {a('s_engp')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz mh_x
        mov ebx, eax
        lea edi, [ebx + {ENG_SITE_A:#x}]
        lea esi, [ebp + hook_a]
        lea ecx, [ebp + ha_ret]
        lea edx, [ebp + {a('x_enga')}]
        call patch5
        lea edi, [ebx + {ENG_SITE_B:#x}]
        lea esi, [ebp + hook_b]
        lea ecx, [ebp + hb_ret]
        lea edx, [ebp + {a('x_eng')}]
        call patch5
    mh_x:
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz mh_o
        lea edi, [eax + {SITE_RW:#x}]
        lea esi, [ebp + hook_s]
        lea ecx, [ebp + hs_ret]
        lea edx, [ebp + {a('x_site')}]
        call patch5
    mh_o:
        mov edi, {ENABLE_CAVE:#x}
        lea edx, [ebp + {a('x_enab')}]
        mov eax, dword ptr [edx + 0x5]
        cmp eax, dword ptr [edi + 0x5]
        jne mh_e2
        mov ax, word ptr [edx + 0x8]
        cmp ax, word ptr [edi + 0x8]
        jne mh_e2
        lea esi, [ebp + hook_e]
        lea ecx, [ebp + he_ret]
        call patch5
    mh_e2:
        mov edi, {OPEN_SITE:#x}
        lea esi, [ebp + hook_o]
        lea ecx, [ebp + ho_ret]
        lea edx, [ebp + {a('x_open')}]
        call patch5
        ret

    patch5:
        mov eax, dword ptr [edx]
        cmp eax, dword ptr [edi]
        jne p5_no
        mov al, byte ptr [edx + 0x4]
        cmp al, byte ptr [edi + 0x4]
        jne p5_no
        lea eax, [edi + 0x5]
        sub eax, ecx
        sub eax, 0x5
        mov byte ptr [ecx], 0xe9
        mov dword ptr [ecx + 0x1], eax
        lea eax, [ebp + {a('g_old')}]
        push eax
        push 0x40
        push 0x5
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz p5_no
        mov eax, esi
        sub eax, edi
        sub eax, 0x5
        mov byte ptr [edi], 0xe9
        mov dword ptr [edi + 0x1], eax
        lea eax, [ebp + {a('g_old')}]
        push eax
        push {v('g_old')}
        push 0x5
        push edi
        call {imp('VirtualProtect')}
        mov eax, 0x1
        ret
    p5_no:
        xor eax, eax
        ret

    hook_a:
        pushal
        mov ecx, dword ptr [ebp - 0x10]
        mov edx, ebx
        mov eax, dword ptr [ebp - 0x8]
        mov eax, dword ptr [eax]
        call {GD:#x}
        call logit
        popal
        mov eax, dword ptr [ebp - 0x8]
        mov eax, dword ptr [eax]
    ha_ret:
        nop
        nop
        nop
        nop
        nop
    hook_b:
        pushal
        xor eax, eax
        mov edx, ebx
        or ecx, 0xffffffff
        call {GD:#x}
        call logit
        popal
        mov edx, ebx
        mov eax, dword ptr [ebp - 0x4]
    hb_ret:
        nop
        nop
        nop
        nop
        nop
    hook_s:
        pushal
        call {GD:#x}
        mov {v('g_cursite')}, ebx
        popal
        mov ecx, 0x5
    hs_ret:
        nop
        nop
        nop
        nop
        nop
    hook_e:
        pushal
        call {GD:#x}
        call setbtns
        popal
        push edx
        mov edx, dword ptr [esp]
        mov eax, dword ptr [ebx + 0x610]
        push {ENABLE_RESUME:#x}
        ret
    he_ret:
        nop
        nop
        nop
        nop
        nop

    setbtns:
        push esi
        push edi
        mov edi, edx
        mov esi, {v('g_bshot')}
        call sb1
        mov esi, {v('g_bmiss')}
        call sb1
        mov esi, {v('g_bregen')}
        call sb1
        pop edi
        pop esi
        ret
    sb1:
        test esi, esi
        jz sb_r
        mov eax, esi
        mov edx, edi
        mov ecx, {SET_ENABLED:#x}
        call ecx
    sb_r:
        ret

    hook_o:
        pushal
        call {GD:#x}
        mov {v('g_ncnt')}, 0x0
        mov {v('g_cursite')}, 0x0
        popal
        push ebp
        mov ebp, esp
        xor ecx, ecx
    ho_ret:
        nop
        nop
        nop
        nop
        nop

    logit:
        push ebx
        push esi
        push edi
        mov esi, eax
        mov ebx, edx
        mov eax, {v('g_ncnt')}
        cmp eax, {MAXE:#x}
        jae lg_full
        imul edi, eax, {ESZ:#x}
        lea edi, [ebp + edi + {a('g_ents')}]
        mov dword ptr [edi], ecx
        mov dword ptr [edi + 0x4], 0xffffffff
        mov dword ptr [edi + 0x8], 0xffffffff
        mov dword ptr [edi + 0xc], 0xffffffff
        mov {v('g_try')}, 0x0
    lg_restart:
        mov ecx, 0x10
        xor edx, edx
    lg_w:
        test esi, esi
        jz lg_end
        push ecx
        push edx
        push 0x14
        push esi
        call {imp('IsBadReadPtr')}
        pop edx
        pop ecx
        test eax, eax
        jnz lg_end
        mov edx, esi
        push ecx
        push edx
        mov eax, esi
        call isfield
        pop edx
        pop ecx
        test eax, eax
        jnz lg_f
        mov esi, dword ptr [esi + 0x4]
        dec ecx
        jnz lg_w
    lg_end:
        cmp {v('g_try')}, 0x0
        jne lg_m
        mov {v('g_try')}, 0x1
        mov eax, {v('g_cursite')}
        test eax, eax
        jz lg_m
        test edx, edx
        jz lg_m
        cmp dword ptr [eax + {SITE_ARMY:#x}], edx
        jne lg_m
        mov esi, eax
        jmp lg_restart
    lg_f:
        movsx eax, byte ptr [esi + 0x10]
        mov dword ptr [edi + 0x4], eax
        movsx eax, byte ptr [esi + 0x11]
        mov dword ptr [edi + 0x8], eax
        movsx eax, byte ptr [esi + 0x12]
        mov dword ptr [edi + 0xc], eax
    lg_m:
        lea edx, [edi + 0x10]
        mov byte ptr [edx], 0x0
        test ebx, ebx
        jz lg_d
        mov esi, dword ptr [ebx + 0x4]
        test esi, esi
        jz lg_d
        mov ecx, {MSGMAX - 1:#x}
    lg_c:
        mov al, byte ptr [esi]
        test al, al
        jz lg_ce
        cmp al, 0x20
        jae lg_cs
        mov al, 0x20
    lg_cs:
        mov byte ptr [edx], al
        inc esi
        inc edx
        dec ecx
        jnz lg_c
    lg_ce:
        mov byte ptr [edx], 0x0
    lg_d:
        inc {v('g_ncnt')}
        jmp lg_o
    lg_full:
        cmp eax, {MAXE + 1:#x}
        jae lg_o
        inc {v('g_ncnt')}
    lg_o:
        pop edi
        pop esi
        pop ebx
        ret

    isfield:
        mov edx, {v('g_fieldvmt')}
        test edx, edx
        jz if_no
        mov eax, dword ptr [eax]
        mov ecx, 0x20
    if_l:
        test eax, eax
        jz if_no
        cmp eax, edx
        je if_yes
        mov eax, dword ptr [eax - 0x18]
        test eax, eax
        jz if_no
        mov eax, dword ptr [eax]
        dec ecx
        jnz if_l
    if_no:
        xor eax, eax
        ret
    if_yes:
        mov eax, 0x1
        ret

    missing:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov eax, dword ptr [esp + 0x14]
        mov {v('g_mform')}, eax
        call {imp('GetActiveWindow')}
        mov {v('g_hwnd')}, eax
        cmp {v('g_ncnt')}, 0x0
        jne ms_go
        push 0x40
        lea eax, [ebp + {a('s_mtitle')}]
        push eax
        lea eax, [ebp + {a('s_none')}]
        push eax
        push {v('g_hwnd')}
        call {imp('MessageBoxA')}
        jmp ms_out
    ms_go:
        mov eax, {v('g_mdlg')}
        test eax, eax
        jz ms_new
        mov {v('g_mdlg')}, 0x0
        push eax
        call {imp('DestroyWindow')}
    ms_new:
        push 0x0
        lea eax, [ebp + mdlgproc]
        push eax
        push {v('g_hwnd')}
        lea eax, [ebp + {a('g_mtpl')}]
        push eax
        push 0x0
        call {imp('GetModuleHandleA')}
        push eax
        call {imp('CreateDialogIndirectParamA')}
        mov {v('g_mdlg')}, eax
        test eax, eax
        jz ms_out
        push 0x5
        push eax
        call {imp('ShowWindow')}
        push {v('g_mdlg')}
        call {imp('SetForegroundWindow')}
    ms_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x4

    mdlgproc:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov ebx, dword ptr [esp + 0x14]
        mov eax, dword ptr [esp + 0x18]
        cmp eax, 0x110
        je md_init
        cmp eax, 0x111
        je md_cmd
        cmp eax, 0x7b
        je md_ctx
        cmp eax, 0x10
        je md_close
        cmp eax, 0x2
        je md_destroy
        jmp md_zero
    md_init:
        push {v('g_ncnt')}
        lea eax, [ebp + {a('s_hdr')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        lea eax, [ebp + {a('g_line')}]
        push eax
        push {ID_HDR:#x}
        push ebx
        call {imp('SetDlgItemTextA')}
        push 0x0
        push 0x800
        push 0x194
        push {ID_LIST:#x}
        push ebx
        call {imp('SendDlgItemMessageA')}
        xor esi, esi
    md_fl:
        cmp esi, {v('g_ncnt')}
        jae md_fd
        cmp esi, {MAXE:#x}
        jae md_fmax
        imul edi, esi, {ESZ:#x}
        lea edi, [ebp + edi + {a('g_ents')}]
        lea eax, [edi + 0x10]
        push eax
        cmp dword ptr [edi + 0x4], 0x0
        jl md_lno
        push dword ptr [edi + 0xc]
        push dword ptr [edi + 0x8]
        push dword ptr [edi + 0x4]
        lea eax, [ebp + {a('s_lxy')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0x18
        jmp md_add
    md_lno:
        lea eax, [ebp + {a('s_lno')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
    md_add:
        lea eax, [ebp + {a('g_line')}]
        push eax
        push 0x0
        push 0x180
        push {ID_LIST:#x}
        push ebx
        call {imp('SendDlgItemMessageA')}
        inc esi
        jmp md_fl
    md_fmax:
        push {MAXE:#x}
        lea eax, [ebp + {a('s_lmax')}]
        push eax
        lea eax, [ebp + {a('g_line')}]
        push eax
        call {imp('wsprintfA')}
        add esp, 0xc
        lea eax, [ebp + {a('g_line')}]
        push eax
        push 0x0
        push 0x180
        push {ID_LIST:#x}
        push ebx
        call {imp('SendDlgItemMessageA')}
    md_fd:
        mov eax, 0x1
        jmp md_ret
    md_cmd:
        movzx eax, word ptr [esp + 0x1c]
        movzx ecx, word ptr [esp + 0x1e]
        cmp eax, 0x2
        je md_close
        cmp eax, {ID_LIST:#x}
        jne md_zero
        cmp ecx, 0x2
        jne md_zero
        push 0x0
        push 0x0
        push 0x188
        push {ID_LIST:#x}
        push ebx
        call {imp('SendDlgItemMessageA')}
        call center_idx
        jmp md_one
    md_ctx:
        push {ID_LIST:#x}
        push ebx
        call {imp('GetDlgItem')}
        mov esi, eax
        cmp esi, dword ptr [esp + 0x1c]
        jne md_zero
        movsx eax, word ptr [esp + 0x20]
        mov {v('g_ptx')}, eax
        movsx eax, word ptr [esp + 0x22]
        mov {v('g_pty')}, eax
        lea eax, [ebp + {a('g_ptx')}]
        push eax
        push esi
        call {imp('ScreenToClient')}
        mov eax, {v('g_pty')}
        shl eax, 0x10
        mov ecx, {v('g_ptx')}
        and ecx, 0xffff
        or eax, ecx
        push eax
        push 0x0
        push 0x1a9
        push esi
        call {imp('SendMessageA')}
        test eax, 0xffff0000
        jnz md_zero
        and eax, 0xffff
        push eax
        push 0x0
        push eax
        push 0x186
        push esi
        call {imp('SendMessageA')}
        pop eax
        call center_idx
        jmp md_one
    md_close:
        push ebx
        call {imp('DestroyWindow')}
        jmp md_one
    md_destroy:
        mov {v('g_mdlg')}, 0x0
        jmp md_zero
    md_one:
        mov eax, 0x1
        jmp md_ret
    md_zero:
        xor eax, eax
    md_ret:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10

    center_idx:
        test eax, eax
        js ci_r
        cmp eax, {v('g_ncnt')}
        jae ci_r
        cmp eax, {MAXE:#x}
        jae ci_r
        imul edi, eax, {ESZ:#x}
        lea edi, [ebp + edi + {a('g_ents')}]
        cmp dword ptr [edi + 0x4], 0x0
        jl ci_r
        mov eax, {v('g_mform')}
        test eax, eax
        jz ci_r
        mov ecx, dword ptr [eax + 0x22c]
        test ecx, ecx
        jz ci_r
        cmp byte ptr [ecx + 0x1bc], 0x0
        je ci_r
        mov edx, dword ptr [edi + 0xc]
        mov esi, {SET_MAP_LEVEL:#x}
        call esi
        mov eax, {v('g_mform')}
        mov eax, dword ptr [eax + 0x22c]
        push dword ptr [edi + 0xc]
        mov edx, dword ptr [edi + 0x4]
        mov ecx, dword ptr [edi + 0x8]
        mov esi, {CENTER_HELPER:#x}
        call esi
    ci_r:
        ret
"""
