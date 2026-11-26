#!/usr/bin/env python3
r"""
AoWxShot.dll - AoWDevX map screenshot exporter (2026-11-07), pure x86 assembly (keystone) wrapped in a hand-built PE.

User: "add a new button to AoWDevX tool bar ... after validate map button ... icon a camera. when pressed, it should
bring up a window for screenshot options: Export minimap as PNG (exclude the white box that shows current view
location); Export map as PNG (export current map view or export entire map level); option for only current map level
or all levels (for both); option to add frame around PNG (similar to in-game map view frame)".

The editor side (patch_devx_screenshot_v1.py) adds the camera button and a click stub that LoadLibrary's this DLL
and calls its only export  Run(form) stdcall.  Everything else is here:
  * options dialog = DialogBoxIndirectParamA on an in-memory DLGTEMPLATE (radio: minimap / map current view / map
    entire level, radio: current level / all levels, check: frame), choices remembered while the editor runs;
  * Save As (comdlg32 GetSaveFileNameA), default "<map name>_<MiniMap|MapView|Map>_View<n>_<level name>.png"
    (2026-11-14: n = display order 1 Firmament, 2 Surface, 3 Caverns, 4 Depths, 5 Abyss, 6 AbyssII ...; without a
    Firmament - fewer than 4 levels or hidden bit 3 of the TAoWHSMap mask +0x41C - everything moves up one, Surface
    = 1; two digits when the map has 10+ shown levels; hidden levels are not exported); all levels -> one file per level, "_View<n>_<level name>" inserted before the
    extension of the chosen name (default "<map name>_<MiniMap|Map>.png");
  * MAP render = Ziggurat's offscreen recipe (AoWEPACK 0x558C0900, the Firmament cache builder): per 512x512 chunk
    set the THSMap viewport fields (+0x80 x, +0x84 y, +0x88 level, +0x94..+0xA0 visible field range), Reset the
    visible static/dynamic lists, TMapField.CopyStatic/DynamicVisibleHS for every field in range, sort (list VMT
    +0x90) and draw every HS (VMT+0xA8 eax=hs edx=viewX ecx=viewY push desc) into our own surface descriptor (a copy
    of a locked display surface's, re-pointed at our buffer); TAoWBorderHexagon skipped, ARMIES INCLUDED; the
    viewport is restored and UpdateStaticScene/UpdateDynamicScene (VMT +0xD8/+0xDC) rebuild the editor's lists;
  * MINIMAP = the scanner of TScannerFloater ([[0x42F064]] +0x1EC): Scanner.SetLevel(level) + DrawMap(0,0,999,999) +
    DrawObjects, then terrain surface +0x174 with the object surface +0x178 on top (key 0xFF00) - the white view box
    is drawn only at blit time (TInterfaceIL.DrawILF in TScanner.Draw), so it is never in these surfaces; the
    floater's own refresh (0x421244) restores the current level afterwards;
  * FRAME = the in-game map window frame Int\ScanWin.ilb 0..7 (torn parchment; corners 34x28, edges tiled 146 / 140,
    right side = mirrored left so it is symmetric), outer torn edge transparent -> PNG with alpha;
  * PNG = GDI+ (gdiplus.dll, always present): GdipCreateBitmapFromScan0 32bpp ARGB + GdipSaveImageToFile (PNG CLSID).
Engine functions are resolved at run time by name (GetModuleHandleA + GetProcAddress on the Delphi packages), so a
missing export only produces a message.  Code is PIC (ebp = load delta, from get_delta), the DLL still carries a
(no-op) .reloc so the loader can rebase it.

  py -3.10 build_aowxshot.py            -> writes <game>\AoWxShot.dll (dry run: --check only builds + validates)
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import game_file  # noqa: E402
import aowxshot_missing as MS  # noqa: E402   (v2: Init export + Missing Resources list)
import aowxshot_banlist as BL  # noqa: E402   (2026-11-20: Map Settings -> Ban List tab, wired by Init -> baninit)
import aowxshot_citynames as CN  # noqa: E402   (2026-11-22: random city names + Map Settings -> City Names tab)
import aowxshot_fogplayer as FP  # noqa: E402   (2026-11-22: editor Fog of War follows the Players pick, wired by Init -> fpinit)
import aowxshot_levelvision as LV  # noqa: E402   (2026-11-22: Map Settings -> Map Level Vision tab, called from the Ban List hooks)

OUT = game_file("AoWxShot.dll")
BASE = 0x6A400000
SEC_RVA = 0x1000
CHUNK = 0x200                 # 512 x 512 render chunks
# AoWEPACK sky overlay entries for offscreen renders (patch_sky_below_v2: header magic, +0x10 begin(eax map, edx
# desc) / +0x15 pass(eax, edx, ecx mode) / +0x1A end); skipped when the magic is absent
SKB_RVA, SKB_MAGIC = 0x558E1900 - 0x55700000, 0x32424B53

# ---------------------------------------------------------------------------------------------------- imports
IMPORTS = [
    ("kernel32.dll", ["GetModuleHandleA", "GetProcAddress", "LoadLibraryA", "VirtualAlloc", "VirtualFree",
                      "MultiByteToWideChar"]),
    ("user32.dll", ["DialogBoxIndirectParamA", "EndDialog", "CheckRadioButton", "CheckDlgButton",
                    "IsDlgButtonChecked", "MessageBoxA", "GetActiveWindow", "SetCursor", "LoadCursorA"]),
    ("comdlg32.dll", ["GetSaveFileNameA"]),
    ("advapi32.dll", []),
    ("gdiplus.dll", ["GdiplusStartup", "GdipCreateBitmapFromScan0", "GdipSaveImageToFile", "GdipDisposeImage"]),
]
IMPORTS = [(dll, funcs + MS.IMPORTS.get(dll, []) + BL.IMPORTS.get(dll, []) + CN.IMPORTS.get(dll, [])) for dll, funcs in IMPORTS]
ENGINE = [  # (global, module, export)
    ("f_getlevel", "HSEPack.dpl", "HSEngine.TMapContainer.GetMapLevel@23EDC2EF"),
    ("f_getfield", "HSEPack.dpl", "HSEngine.TMapLevel.GetField@23EDC2EF"),
    ("f_rvs", "HSEPack.dpl", "HSEngine.THSMap.ResetVisibleStaticHS@23EDC2EF"),
    ("f_rvd", "HSEPack.dpl", "HSEngine.THSMap.ResetVisibleDynamicHS@23EDC2EF"),
    ("f_csv", "HSEPack.dpl", "HSEngine.TMapField.CopyStaticVisibleHS@23EDC2EF"),
    ("f_cdv", "HSEPack.dpl", "HSEngine.TMapField.CopyDynamicVisibleHS@23EDC2EF"),
    ("f_scnlevel", "AOWTools.dpl", "Scanner.TScanner.SetLevel@23EDC2EF"),
    ("f_scnmap", "AOWTools.dpl", "Scanner.TScanner.DrawMap@23EDC2EF"),
    ("f_scnobj", "AOWTools.dpl", "Scanner.TScanner.DrawObjects@23EDC2EF"),
    ("f_border", "AoWEPACK.dll", "AoWHex..TAoWBorderHexagon@07D9D903"),
    ("f_pmap", "AoWEPACK.dll", "AoWE.AoWHSMap@6B957A58"),
]
# editor (fixed-base exe) facts
EXE_FLOATER_VAR = 0x42F064    # ScannerFloater: TScannerFloater (pointer to the var)
EXE_SCN_REFRESH = 0x421244    # TScannerFloater refresh (eax = floater)
ID_MINI, ID_VIEW, ID_FULL, ID_CUR, ID_ALL, ID_FRAME = 101, 102, 103, 111, 112, 121
FRAME_L, FRAME_T = 34, 28


# ---------------------------------------------------------------------------------------------------- data
class Data(object):
    def __init__(self, va):
        self.va, self.b, self.sym = va, bytearray(), {}

    def align(self, n):
        while len(self.b) % n:
            self.b.append(0)

    def add(self, name, blob, align=4):
        self.align(align)
        self.sym[name] = self.va + len(self.b)
        self.b += blob
        return self.sym[name]

    def var(self, name, size=4):
        return self.add(name, bytes(size))

    def s(self, name, text):
        return self.add(name, text.encode("latin1") + b"\0", 1)


def dlg_template():
    """DLGTEMPLATE (DS_SETFONT) with 9 items; dialog units"""
    def w(s):
        return s.encode("utf-16-le") + b"\0\0"

    WS_CHILD, WS_VISIBLE, WS_GROUP, WS_TABSTOP = 0x40000000, 0x10000000, 0x20000, 0x10000
    items = [
        (0x0007 | WS_CHILD | WS_VISIBLE, 7, 6, 196, 52, 0xFFFF, "Export"),
        (0x0009 | WS_CHILD | WS_VISIBLE | WS_GROUP | WS_TABSTOP, 16, 18, 180, 10, ID_MINI,
         "Minimap as PNG"),
        (0x0009 | WS_CHILD | WS_VISIBLE, 16, 30, 180, 10, ID_VIEW, "Map as PNG - current map view"),
        (0x0009 | WS_CHILD | WS_VISIBLE, 16, 42, 180, 10, ID_FULL, "Map as PNG - entire map level"),
        (0x0007 | WS_CHILD | WS_VISIBLE, 7, 62, 196, 40, 0xFFFF, "Levels"),
        (0x0009 | WS_CHILD | WS_VISIBLE | WS_GROUP | WS_TABSTOP, 16, 74, 180, 10, ID_CUR, "Current map level only"),
        (0x0009 | WS_CHILD | WS_VISIBLE, 16, 86, 180, 10, ID_ALL, "All map levels (one PNG per level)"),
        (0x0003 | WS_CHILD | WS_VISIBLE | WS_GROUP | WS_TABSTOP, 9, 108, 194, 10, ID_FRAME,
         "Add frame (in-game map border)"),
        (0x0001 | WS_CHILD | WS_VISIBLE | WS_GROUP | WS_TABSTOP, 95, 126, 52, 14, 1, "Export..."),
        (0x0000 | WS_CHILD | WS_VISIBLE | WS_TABSTOP, 151, 126, 52, 14, 2, "Cancel"),
    ]
    style = 0x80000000 | 0x00C00000 | 0x00080000 | 0x80 | 0x40 | 0x0800   # POPUP|CAPTION|SYSMENU|MODALFRAME|SETFONT|CENTER
    b = struct.pack("<IIHhhhh", style, 0, len(items), 0, 0, 210, 146)
    b += b"\0\0" + b"\0\0" + w("Map Screenshot") + struct.pack("<H", 8) + w("MS Shell Dlg")
    for st, x, y, cx, cy, iid, text in items:
        while len(b) % 4:
            b += b"\0"
        b += struct.pack("<IIhhhhH", st, 0, x, y, cx, cy, iid & 0xFFFF)
        b += b"\xff\xff\x80\x00" + w(text) + b"\0\0"
    return b


def _ilb_bgra(game_dir, rel, ids):
    from aowxlib import ilb
    import numpy as np
    lib = ilb.read(open(os.path.join(game_dir, rel), "rb").read())
    by = {im.id: im for im in lib.images}
    out = {}
    for iid in ids:
        w, h, rows = ilb.decode_record(lib, by[iid].primary)
        a = np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)
        bgra = np.zeros((h, w, 4), np.uint8)
        bgra[..., 0], bgra[..., 1], bgra[..., 2] = a[..., 2], a[..., 1], a[..., 0]
        bgra[..., 3] = np.where(a[..., 3] > 0, 255, 0)
        out[iid] = bgra
    return out


def frame_sets(game_dir):
    """{set: (cw, ch, tw, lh, {piece: bgra})}, pieces TL T TR L R BL B BR.
    'scan' = the in-game minimap frame Int ScanWin.ilb 0/1/3/5/6 (right side mirrored from the left -> symmetric);
    'map'  = the in-game map view border Int GenericF.ILB 8..15 (greek key, 12 px)"""
    import numpy as np
    sw = _ilb_bgra(game_dir, os.path.join("Int", "ScanWin.ilb"), (0, 1, 3, 5, 6))
    scan = dict(TL=sw[0], T=sw[1], TR=np.ascontiguousarray(sw[0][:, ::-1]), L=sw[3],
                R=np.ascontiguousarray(sw[3][:, ::-1]), BL=sw[5], B=sw[6], BR=np.ascontiguousarray(sw[5][:, ::-1]))
    gf = _ilb_bgra(game_dir, os.path.join("Int", "GenericF.ILB"), range(8, 16))
    gmap = dict(TL=gf[8], T=gf[9], TR=gf[10], L=gf[11], R=gf[12], BL=gf[13], B=gf[14], BR=gf[15])
    out = {}
    for name, P in (("scan", scan), ("map", gmap)):
        ch, cw = P["TL"].shape[:2]
        tw, lh = P["T"].shape[1], P["L"].shape[0]
        for k in ("TR", "BL", "BR"):
            assert P[k].shape[:2] == (ch, cw), (name, k)
        assert P["B"].shape[:2] == (ch, tw) and P["T"].shape[0] == ch and P["L"].shape[1] == cw
        assert P["R"].shape[:2] == (lh, cw)
        out[name] = (cw, ch, tw, lh, P)
    return out


def build_data(va, game_dir):
    D = Data(va)
    for n in ("g_inited", "g_form", "g_hsm", "g_map", "g_hwnd", "g_mode", "g_all", "g_frame", "g_token",
              "g_img", "g_w", "g_h", "g_fimg", "g_fw", "g_fh", "g_chunk", "g_lv", "g_lvidx", "g_cols", "g_rows",
              "g_x0", "g_y0", "g_x1", "g_y1", "g_cx", "g_cy", "g_c0", "g_c1", "g_r0", "g_r1", "g_565", "g_bmp",
              "g_nlev", "g_saved", "g_scn", "g_floater", "g_err", "g_tmp", "g_tmp2", "g_mods", "g_cw", "g_ch",
              "g_pimg", "g_pw", "g_ph", "g_bx", "g_by", "g_bw", "g_bh", "g_bsrc", "g_bsw", "g_bmir", "g_curlv", "g_fs", "g_key", "g_fsc", "g_bstr", "g_pimg2", "g_sw", "g_sh", "g_tw", "g_th", "g_skb"):
        D.var(n)
    for g, _m, _e in ENGINE:
        D.var(g)
    D.var("g_save", 0x20)
    D.var("g_sfs", 0x30)
    D.var("g_desc", 0x40)
    D.var("g_d1", 0x40)
    D.var("g_d2", 0x40)
    D.var("g_path", 0x110)
    D.var("g_pathl", 0x130)
    D.var("g_wpath", 0x260)
    D.var("g_msg", 0x200)
    D.var("g_ofn", 0x50)
    D.add("g_gdiin", struct.pack("<IIII", 1, 0, 0, 0))
    D.add("g_clsid", struct.pack("<IHH", 0x557CF406, 0x1A04, 0x11D3) + bytes([0x9A, 0x73, 0, 0, 0xF8, 0x1E, 0xF3, 0x2E]))
    D.add("g_dlg", dlg_template())
    D.add("s_filter", b"PNG image (*.png)\0*.png\0\0", 1)
    D.s("s_defext", "png")
    D.s("s_title", "Map Screenshot")
    D.s("s_noinit", "Map Screenshot: an editor package export was not found (HSEPack / AOWTools / AoWEPACK).")
    D.s("s_nomap", "Open a map first.")
    D.s("s_noscan", "Map Screenshot: the Scanner (minimap) is not available - open the Scanner window first.")
    D.s("s_nomem", "Map Screenshot: not enough memory for an image this large.")
    D.s("s_nogdi", "Map Screenshot: GDI+ could not be started.")
    D.s("s_nosave", "Map Screenshot: could not write the PNG file:\r\n")
    D.s("s_saved1", "Saved ")
    D.s("s_saved2", " PNG file(s). Last one:\r\n")
    D.s("s_sfx0", "_MiniMap")
    D.s("s_sfx1", "_MapView")
    D.s("s_sfx2", "_Map")
    D.s("s_png", ".png")
    # level names for the file suffix "_View<n>_<name>" (16-byte entries by stored level index; 29 = fallback)
    lvn = ["Surface", "Caverns", "Depths", "Firmament", "Abyss"] + \
          ["Abyss" + r for r in ("II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX "
                                 "XXI XXII XXIII XXIV XXV").split()] + ["Level"]
    assert len(lvn) == 30
    D.add("s_lvnames", b"".join(n.encode("latin1").ljust(16, b"\0") for n in lvn))
    D.s("s_map", "map")
    D.s("s_hse", "HSEPack.dpl")
    D.s("s_aowt", "AOWTools.dpl")
    D.s("s_aowt2", "AOWTools.dll")
    D.s("s_aowe", "AoWEPACK.dll")
    for g, _m, e in ENGINE:
        D.s("n_" + g, e)
    MS.data(D)
    BL.data(D)
    LV.data(D)
    FP.data(D)
    CN.data(D)
    fp = frame_sets(game_dir)
    for name, (cw, ch, tw, lh, P) in fp.items():
        ptrs = {}
        for k in ("TL", "T", "TR", "L", "R", "BL", "B", "BR"):
            ptrs[k] = D.add("fr_%s_%s" % (name, k), P[k].tobytes(), 4)
        D.add("fs_" + name, struct.pack("<4I", cw, ch, tw, lh) + b"".join(
            struct.pack("<I", ptrs[k]) for k in ("TL", "T", "TR", "L", "R", "BL", "B", "BR")))
    return D, fp


# ---------------------------------------------------------------------------------------------------- code
def asm_text(D, I, code_va):
    v = lambda n: "dword ptr [ebp + %#x]" % D.sym[n]      # noqa: E731
    a = lambda n: "%#x" % D.sym[n]                          # noqa: E731
    imp = lambda n: "dword ptr [ebp + %#x]" % I[n]          # noqa: E731
    GD = code_va + 0x10
    resolve = []
    for g, mod, _e in ENGINE:
        hm = {"HSEPack.dpl": "g_tmp", "AOWTools.dpl": "g_tmp2", "AoWEPACK.dll": "g_mods"}[mod]
        resolve.append(f"""
        lea eax, [ebp + {a('n_' + g)}]
        push eax
        push {v(hm)}
        call {imp('GetProcAddress')}
        test eax, eax
        jz ini_fail
        mov {v(g)}, eax""")
    resolve = "\n".join(resolve)
    return f"""
    run:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov eax, dword ptr [esp + 0x14]
        mov {v('g_form')}, eax
        call {imp('GetActiveWindow')}
        mov {v('g_hwnd')}, eax
        call init
        test eax, eax
        jz run_out
        mov eax, {v('g_form')}
        mov eax, dword ptr [eax + 0x22c]
        mov {v('g_hsm')}, eax
        test eax, eax
        jz run_nomap
        cmp byte ptr [eax + 0x1bc], 0
        je run_nomap
        mov eax, {v('f_pmap')}
        mov eax, dword ptr [eax]
        test eax, eax
        jz run_nomap
        mov {v('g_map')}, eax
        push 0x0
        lea eax, [ebp + dlgproc]
        push eax
        push {v('g_hwnd')}
        lea eax, [ebp + {a('g_dlg')}]
        push eax
        push 0x0
        call {imp('GetModuleHandleA')}
        push eax
        call {imp('DialogBoxIndirectParamA')}
        cmp eax, 0x1
        jne run_out
        call askname
        test eax, eax
        jz run_out
        call doexport
        jmp run_out
    run_nomap:
        lea eax, [ebp + {a('s_nomap')}]
        call msg
    run_out:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x4

    msg:
        push 0x40
        lea edx, [ebp + {a('s_title')}]
        push edx
        push eax
        push {v('g_hwnd')}
        call {imp('MessageBoxA')}
        ret

    init:
        cmp {v('g_inited')}, 0x0
        jne ini_ok
        lea eax, [ebp + {a('s_hse')}]
        push eax
        call {imp('GetModuleHandleA')}
        mov {v('g_tmp')}, eax
        test eax, eax
        jz ini_fail
        lea eax, [ebp + {a('s_aowt')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jnz ini_t
        lea eax, [ebp + {a('s_aowt2')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz ini_fail
    ini_t:
        mov {v('g_tmp2')}, eax
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        mov {v('g_mods')}, eax
        test eax, eax
        jz ini_fail
{resolve}
        push 0x0
        lea eax, [ebp + {a('g_gdiin')}]
        push eax
        lea eax, [ebp + {a('g_token')}]
        push eax
        call {imp('GdiplusStartup')}
        test eax, eax
        jnz ini_gdi
        mov {v('g_inited')}, 0x1
    ini_ok:
        mov eax, 0x1
        ret
    ini_gdi:
        lea eax, [ebp + {a('s_nogdi')}]
        call msg
        xor eax, eax
        ret
    ini_fail:
        lea eax, [ebp + {a('s_noinit')}]
        call msg
        xor eax, eax
        ret

    dlgproc:
        push ebp
        push ebx
        push esi
        push edi
        call {GD:#x}
        mov ebx, dword ptr [esp + 0x14]
        mov eax, dword ptr [esp + 0x18]
        cmp eax, 0x110
        je dp_init
        cmp eax, 0x111
        je dp_cmd
        xor eax, eax
        jmp dp_ret
    dp_init:
        mov eax, {v('g_mode')}
        add eax, {ID_MINI:#x}
        push eax
        push {ID_FULL:#x}
        push {ID_MINI:#x}
        push ebx
        call {imp('CheckRadioButton')}
        mov eax, {v('g_all')}
        add eax, {ID_CUR:#x}
        push eax
        push {ID_ALL:#x}
        push {ID_CUR:#x}
        push ebx
        call {imp('CheckRadioButton')}
        push {v('g_frame')}
        push {ID_FRAME:#x}
        push ebx
        call {imp('CheckDlgButton')}
        mov eax, 0x1
        jmp dp_ret
    dp_cmd:
        movzx eax, word ptr [esp + 0x1c]
        cmp eax, 0x1
        je dp_ok
        cmp eax, 0x2
        jne dp_zero
        push 0x0
        push ebx
        call {imp('EndDialog')}
        mov eax, 0x1
        jmp dp_ret
    dp_ok:
        mov {v('g_mode')}, 0x0
        push {ID_VIEW:#x}
        push ebx
        call {imp('IsDlgButtonChecked')}
        cmp eax, 0x1
        jne dp_o2
        mov {v('g_mode')}, 0x1
    dp_o2:
        push {ID_FULL:#x}
        push ebx
        call {imp('IsDlgButtonChecked')}
        cmp eax, 0x1
        jne dp_o3
        mov {v('g_mode')}, 0x2
    dp_o3:
        push {ID_ALL:#x}
        push ebx
        call {imp('IsDlgButtonChecked')}
        and eax, 0x1
        mov {v('g_all')}, eax
        push {ID_FRAME:#x}
        push ebx
        call {imp('IsDlgButtonChecked')}
        and eax, 0x1
        mov {v('g_frame')}, eax
        push 0x1
        push ebx
        call {imp('EndDialog')}
        mov eax, 0x1
        jmp dp_ret
    dp_zero:
        xor eax, eax
    dp_ret:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10

    askname:
        lea edi, [ebp + {a('g_path')}]
        mov esi, {v('g_hsm')}
        mov esi, dword ptr [esi + 0x1e4]
        test esi, esi
        jz an_def
        mov ecx, esi
        mov edx, esi
    an_s1:
        mov al, byte ptr [ecx]
        test al, al
        jz an_s2
        cmp al, 0x5c
        jne an_s1n
        lea edx, [ecx + 0x1]
    an_s1n:
        inc ecx
        jmp an_s1
    an_s2:
        mov esi, edx
        xor ecx, ecx
    an_cp:
        mov al, byte ptr [esi + ecx]
        test al, al
        jz an_cpe
        cmp al, 0x2e
        je an_cpe
        cmp ecx, 0xc0
        jae an_cpe
        mov byte ptr [edi + ecx], al
        inc ecx
        jmp an_cp
    an_cpe:
        test ecx, ecx
        jnz an_sfx
    an_def:
        lea esi, [ebp + {a('s_map')}]
        xor ecx, ecx
    an_d1:
        mov al, byte ptr [esi + ecx]
        mov byte ptr [edi + ecx], al
        inc ecx
        test al, al
        jnz an_d1
        dec ecx
    an_sfx:
        add edi, ecx
        lea esi, [ebp + {a('s_sfx0')}]
        cmp {v('g_mode')}, 0x1
        jne an_x2
        lea esi, [ebp + {a('s_sfx1')}]
    an_x2:
        cmp {v('g_mode')}, 0x2
        jne an_x3
        lea esi, [ebp + {a('s_sfx2')}]
    an_x3:
        call scat
        cmp {v('g_all')}, 0x0
        jne an_x4
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x88]
        mov {v('g_lvidx')}, eax
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x10]
        mov eax, dword ptr [eax + 0x8]
        mov eax, dword ptr [eax + 0x8]
        mov {v('g_nlev')}, eax
        call lvsfx
    an_x4:
        lea esi, [ebp + {a('s_png')}]
        call scat
        mov byte ptr [edi], 0x0
        lea edi, [ebp + {a('g_ofn')}]
        xor eax, eax
        mov ecx, 0x14
        rep stosd dword ptr es:[edi], eax
        lea edi, [ebp + {a('g_ofn')}]
        mov dword ptr [edi], 0x4c
        mov eax, {v('g_hwnd')}
        mov dword ptr [edi + 0x4], eax
        lea eax, [ebp + {a('s_filter')}]
        mov dword ptr [edi + 0xc], eax
        mov dword ptr [edi + 0x18], 0x1
        lea eax, [ebp + {a('g_path')}]
        mov dword ptr [edi + 0x1c], eax
        mov dword ptr [edi + 0x20], 0x104
        mov dword ptr [edi + 0x34], 0x80e
        lea eax, [ebp + {a('s_defext')}]
        mov dword ptr [edi + 0x3c], eax
        push edi
        call {imp('GetSaveFileNameA')}
        ret

    getsurf:
        mov eax, {v('g_hsm')}
        mov eax, dword ptr [eax + 0x1a8]
        mov edx, 0x2
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x40]
        ret

    alloc:
        push 0x4
        push 0x3000
        push eax
        push 0x0
        call {imp('VirtualAlloc')}
        ret

    free:
        test eax, eax
        jz fr_r
        push 0x8000
        push 0x0
        push eax
        call {imp('VirtualFree')}
    fr_r:
        ret

    doexport:
        mov {v('g_saved')}, 0x0
        mov {v('g_err')}, 0x0
        push 0x7f02
        push 0x0
        call {imp('LoadCursorA')}
        push eax
        call {imp('SetCursor')}
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x88]
        mov {v('g_curlv')}, eax
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x10]
        mov eax, dword ptr [eax + 0x8]
        mov eax, dword ptr [eax + 0x8]
        mov {v('g_nlev')}, eax
        cmp {v('g_all')}, 0x0
        jne de_all
        mov eax, {v('g_curlv')}
        mov {v('g_lvidx')}, eax
        lea eax, [ebp + {a('g_path')}]
        call onelevel
        jmp de_end
    de_all:
        mov {v('g_lvidx')}, 0x0
    de_al:
        mov eax, {v('g_lvidx')}
        cmp eax, {v('g_nlev')}
        jge de_end
        cmp {v('g_err')}, 0x0
        jne de_end
        cmp {v('g_nlev')}, 0x4
        jl de_vis
        mov ecx, {v('g_map')}
        mov ecx, dword ptr [ecx + 0x41c]
        bt ecx, eax
        jc de_an
    de_vis:
        mov edx, eax
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x10]
        call {v('f_getlevel')}
        test eax, eax
        jz de_an
        call lpath
        lea eax, [ebp + {a('g_pathl')}]
        call onelevel
    de_an:
        inc {v('g_lvidx')}
        jmp de_al
    de_end:
        cmp {v('g_mode')}, 0x0
        jne de_nomini
        mov eax, {EXE_FLOATER_VAR:#x}
        mov eax, dword ptr [eax]
        test eax, eax
        jz de_nomini
        mov eax, dword ptr [eax]
        test eax, eax
        jz de_nomini
        mov edx, {EXE_SCN_REFRESH:#x}
        call edx
    de_nomini:
        cmp {v('g_err')}, 0x0
        jne de_r
        cmp {v('g_saved')}, 0x0
        je de_r
        lea edi, [ebp + {a('g_msg')}]
        lea esi, [ebp + {a('s_saved1')}]
        call scat
        mov eax, {v('g_saved')}
        call sint
        lea esi, [ebp + {a('s_saved2')}]
        call scat
        lea esi, [ebp + {a('g_path')}]
        cmp {v('g_all')}, 0x0
        je de_m1
        lea esi, [ebp + {a('g_pathl')}]
    de_m1:
        call scat
        mov byte ptr [edi], 0x0
        lea eax, [ebp + {a('g_msg')}]
        call msg
    de_r:
        ret

    scat:
        mov al, byte ptr [esi]
        test al, al
        jz sc_r
        mov byte ptr [edi], al
        inc esi
        inc edi
        jmp scat
    sc_r:
        ret

    sint:
        mov ecx, 0xa
        xor ebx, ebx
    si_d:
        xor edx, edx
        div ecx
        add dl, 0x30
        push edx
        inc ebx
        test eax, eax
        jnz si_d
    si_p:
        pop eax
        mov byte ptr [edi], al
        inc edi
        dec ebx
        jnz si_p
        ret

    lpath:
        lea esi, [ebp + {a('g_path')}]
        xor edx, edx
        xor ecx, ecx
    lp_f:
        mov al, byte ptr [esi + ecx]
        test al, al
        jz lp_fe
        cmp al, 0x5c
        jne lp_f1
        xor edx, edx
    lp_f1:
        cmp al, 0x2e
        jne lp_f2
        mov edx, ecx
    lp_f2:
        inc ecx
        jmp lp_f
    lp_fe:
        test edx, edx
        jnz lp_go
        mov edx, ecx
    lp_go:
        lea edi, [ebp + {a('g_pathl')}]
        xor ecx, ecx
    lp_c1:
        cmp ecx, edx
        jge lp_c1e
        mov al, byte ptr [esi + ecx]
        mov byte ptr [edi + ecx], al
        inc ecx
        jmp lp_c1
    lp_c1e:
        add edi, ecx
        add esi, ecx
        push esi
        call lvsfx
        pop esi
    lp_c2:
        mov al, byte ptr [esi]
        mov byte ptr [edi], al
        inc esi
        inc edi
        test al, al
        jnz lp_c2
        ret

    lvsfx:
        push ebx
        mov dword ptr [edi], 0x6569565f
        mov byte ptr [edi + 0x4], 0x77
        add edi, 0x5
        mov eax, {v('g_lvidx')}
        cmp eax, 0x3
        jne lv_a
        mov eax, 0x1
        jmp lv_n
    lv_a:
        jb lv_b
        inc eax
        jmp lv_n
    lv_b:
        add eax, 0x2
    lv_n:
        xor ecx, ecx
        cmp {v('g_nlev')}, 0x4
        jl lv_abs
        mov edx, {v('g_map')}
        test byte ptr [edx + 0x41c], 0x8
        jz lv_pres
    lv_abs:
        inc ecx
    lv_pres:
        sub eax, ecx
        mov edx, {v('g_nlev')}
        sub edx, ecx
        cmp edx, 0xa
        jl lv_np
        cmp eax, 0xa
        jae lv_np
        mov byte ptr [edi], 0x30
        inc edi
    lv_np:
        call sint
        mov byte ptr [edi], 0x5f
        inc edi
        mov eax, {v('g_lvidx')}
        cmp eax, 0x1c
        jbe lv_ok
        mov eax, 0x1d
    lv_ok:
        shl eax, 0x4
        lea esi, [ebp + eax + {a('s_lvnames')}]
        call scat
        pop ebx
        ret

    onelevel:
        mov {v('g_pimg')}, eax
        mov {v('g_img')}, 0x0
        mov {v('g_fimg')}, 0x0
        cmp {v('g_mode')}, 0x0
        jne ol_map
        call minimap
        jmp ol_got
    ol_map:
        call render
    ol_got:
        test eax, eax
        jz ol_fail
        mov eax, {v('g_img')}
        mov {v('g_bsrc')}, eax
        cmp {v('g_frame')}, 0x0
        je ol_save
        lea eax, [ebp + {a('fs_map')}]
        cmp {v('g_mode')}, 0x0
        jne ol_fs
        lea eax, [ebp + {a('fs_scan')}]
    ol_fs:
        mov {v('g_fs')}, eax
        mov {v('g_fsc')}, 0x1
        cmp {v('g_mode')}, 0x0
        je ol_sc
        mov eax, {v('g_w')}
        cmp eax, {v('g_h')}
        jle ol_mn
        mov eax, {v('g_h')}
    ol_mn:
        xor edx, edx
        mov ecx, 0x12c
        div ecx
        cmp eax, 0x2
        jge ol_s2
        mov eax, 0x2
    ol_s2:
        cmp eax, 0x8
        jle ol_s3
        mov eax, 0x8
    ol_s3:
        mov {v('g_fsc')}, eax
    ol_sc:
        call addframe
        test eax, eax
        jz ol_fail
    ol_save:
        cmp {v('g_mode')}, 0x0
        jne ol_sv2
        cmp {v('g_fimg')}, 0x0
        je ol_up
        mov eax, {v('g_img')}
        call free
        mov eax, {v('g_fimg')}
        mov {v('g_img')}, eax
        mov {v('g_fimg')}, 0x0
    ol_up:
        call upscale
        mov eax, {v('g_img')}
        mov {v('g_bsrc')}, eax
    ol_sv2:
        call savepng
        test eax, eax
        jz ol_fail
        inc {v('g_saved')}
        jmp ol_free
    ol_fail:
        mov {v('g_err')}, 0x1
    ol_free:
        mov eax, {v('g_img')}
        call free
        mov eax, {v('g_fimg')}
        call free
        mov {v('g_img')}, 0x0
        mov {v('g_fimg')}, 0x0
        ret

    newimg:
        mov {v('g_w')}, eax
        mov {v('g_h')}, edx
        imul eax, edx
        shl eax, 0x2
        call alloc
        mov {v('g_img')}, eax
        test eax, eax
        jnz ni_r
        lea eax, [ebp + {a('s_nomem')}]
        call msg
        xor eax, eax
    ni_r:
        ret

    px16:
        cmp {v('g_565')}, 0x0
        je px_555
        mov edx, eax
        shr edx, 0xb
        and edx, 0x1f
        shl edx, 0x13
        mov ecx, eax
        shr ecx, 0x5
        and ecx, 0x3f
        shl ecx, 0xa
        or edx, ecx
        and eax, 0x1f
        shl eax, 0x3
        or eax, edx
        jmp px_fin
    px_555:
        mov edx, eax
        shr edx, 0xa
        and edx, 0x1f
        shl edx, 0x13
        mov ecx, eax
        shr ecx, 0x5
        and ecx, 0x1f
        shl ecx, 0xb
        or edx, ecx
        and eax, 0x1f
        shl eax, 0x3
        or eax, edx
    px_fin:
        mov edx, eax
        and edx, 0xe0e0e0
        shr edx, 0x5
        or eax, edx
        or eax, 0xff000000
        ret

    minimap:
        mov eax, {EXE_FLOATER_VAR:#x}
        mov eax, dword ptr [eax]
        test eax, eax
        jz mm_noscan
        mov eax, dword ptr [eax]
        test eax, eax
        jz mm_noscan
        mov {v('g_floater')}, eax
        mov eax, dword ptr [eax + 0x1ec]
        test eax, eax
        jz mm_noscan
        mov {v('g_scn')}, eax
        cmp dword ptr [eax + 0x174], 0x0
        je mm_noscan
        cmp dword ptr [eax + 0x178], 0x0
        je mm_noscan
        mov edx, {v('g_lvidx')}
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x10]
        call {v('f_getlevel')}
        test eax, eax
        jz mm_noscan
        mov edx, eax
        mov eax, {v('g_scn')}
        call {v('f_scnlevel')}
        mov eax, {v('g_scn')}
        mov dword ptr [eax + 0x164], 0x0
        mov byte ptr [eax + 0x180], 0x0
        mov dword ptr [eax + 0x17c], 0xffffffff
        push 0x3e7
        push 0x3e7
        xor ecx, ecx
        xor edx, edx
        call {v('f_scnmap')}
        mov eax, {v('g_scn')}
        call {v('f_scnobj')}
        mov ebx, {v('g_scn')}
        mov eax, dword ptr [ebx + 0x7c]
        mov edx, dword ptr [ebx + 0x80]
        call newimg
        test eax, eax
        jz mm_r0
        mov eax, dword ptr [ebx + 0x174]
        lea edx, [ebp + {a('g_d1')}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x2c]
        test eax, eax
        jl mm_r0
        mov eax, dword ptr [ebx + 0x178]
        lea edx, [ebp + {a('g_d2')}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x2c]
        test eax, eax
        jl mm_un1
        mov {v('g_565')}, 0x1
        mov {v('g_key')}, 0x7e0
        mov eax, dword ptr [ebp + {D.sym['g_d1'] + 0x28:#x}]
        cmp eax, 0x55509310
        jne mm_fmt
        mov {v('g_565')}, 0x0
        mov {v('g_key')}, 0x3e0
    mm_fmt:
        xor esi, esi
    mm_y:
        cmp esi, {v('g_h')}
        jge mm_done
        xor edi, edi
    mm_x:
        cmp edi, {v('g_w')}
        jge mm_yn
        mov eax, esi
        imul eax, dword ptr [ebp + {D.sym['g_d2'] + 0xc:#x}]
        add eax, dword ptr [ebp + {D.sym['g_d2'] + 0x20:#x}]
        movzx eax, word ptr [eax + edi*2]
        cmp eax, {v('g_key')}
        jne mm_pix
        mov eax, esi
        imul eax, dword ptr [ebp + {D.sym['g_d1'] + 0xc:#x}]
        add eax, dword ptr [ebp + {D.sym['g_d1'] + 0x20:#x}]
        movzx eax, word ptr [eax + edi*2]
    mm_pix:
        call px16
        mov edx, esi
        imul edx, {v('g_w')}
        add edx, edi
        shl edx, 0x2
        add edx, {v('g_img')}
        mov dword ptr [edx], eax
        inc edi
        jmp mm_x
    mm_yn:
        inc esi
        jmp mm_y
    mm_done:
        mov eax, dword ptr [ebx + 0x178]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x30]
    mm_un1:
        mov eax, dword ptr [ebx + 0x174]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x30]
        mov eax, 0x1
        ret
    mm_r0:
        xor eax, eax
        ret
    mm_noscan:
        lea eax, [ebp + {a('s_noscan')}]
        call msg
        xor eax, eax
        ret

    upscale:
        mov eax, {v('g_img')}
        mov {v('g_pimg2')}, eax
        mov eax, {v('g_w')}
        mov {v('g_sw')}, eax
        mov ecx, {v('g_h')}
        mov {v('g_sh')}, ecx
        cmp eax, ecx
        jl us_tall
        mov eax, 0x3e8
        mov {v('g_tw')}, eax
        mov eax, ecx
        imul eax, eax, 0x3e8
        xor edx, edx
        div {v('g_sw')}
        mov {v('g_th')}, eax
        jmp us_go
    us_tall:
        mov {v('g_th')}, 0x3e8
        imul eax, eax, 0x3e8
        xor edx, edx
        div {v('g_sh')}
        mov {v('g_tw')}, eax
    us_go:
        mov eax, {v('g_tw')}
        mov edx, {v('g_th')}
        call newimg
        test eax, eax
        jz us_fail
        xor esi, esi
    us_y:
        cmp esi, {v('g_th')}
        jge us_done
        mov eax, esi
        imul eax, {v('g_sh')}
        xor edx, edx
        div {v('g_th')}
        imul eax, {v('g_sw')}
        mov ebx, eax
        xor edi, edi
    us_x:
        cmp edi, {v('g_tw')}
        jge us_yn
        mov eax, edi
        imul eax, {v('g_sw')}
        xor edx, edx
        div {v('g_tw')}
        add eax, ebx
        shl eax, 0x2
        add eax, {v('g_pimg2')}
        mov ecx, dword ptr [eax]
        mov eax, esi
        imul eax, {v('g_tw')}
        add eax, edi
        shl eax, 0x2
        add eax, {v('g_img')}
        mov dword ptr [eax], ecx
        inc edi
        jmp us_x
    us_yn:
        inc esi
        jmp us_y
    us_done:
        mov eax, {v('g_pimg2')}
        call free
        mov eax, 0x1
        ret
    us_fail:
        mov eax, {v('g_pimg2')}
        mov {v('g_img')}, eax
        mov eax, {v('g_sw')}
        mov {v('g_w')}, eax
        mov eax, {v('g_sh')}
        mov {v('g_h')}, eax
        mov eax, 0x1
        ret

    render:
        mov edx, {v('g_lvidx')}
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x10]
        call {v('f_getlevel')}
        test eax, eax
        jz rd_r0
        mov {v('g_lv')}, eax
        mov ecx, dword ptr [eax + 0xc]
        mov {v('g_cols')}, ecx
        mov ecx, dword ptr [eax + 0x10]
        mov {v('g_rows')}, ecx
        mov ebx, {v('g_map')}
        cmp {v('g_mode')}, 0x1
        jne rd_full
        mov eax, dword ptr [ebx + 0x80]
        mov {v('g_x0')}, eax
        mov eax, dword ptr [ebx + 0x84]
        mov {v('g_y0')}, eax
        mov eax, dword ptr [ebx + 0x8c]
        mov edx, dword ptr [ebx + 0x90]
        jmp rd_sz
    rd_full:
        call bbox
    rd_sz:
        test eax, eax
        jle rd_r0
        test edx, edx
        jle rd_r0
        call newimg
        test eax, eax
        jz rd_r0
        mov eax, {v('g_x0')}
        add eax, {v('g_w')}
        mov {v('g_x1')}, eax
        mov eax, {v('g_y0')}
        add eax, {v('g_h')}
        mov {v('g_y1')}, eax
        call getsurf
        lea edx, [ebp + {a('g_d1')}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x2c]
        test eax, eax
        jl rd_r0
        call getsurf
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x30]
        lea esi, [ebp + {a('g_d1')}]
        lea edi, [ebp + {a('g_desc')}]
        mov ecx, 0xf
        rep movsd dword ptr es:[edi], dword ptr [esi]
        mov {v('g_565')}, 0x1
        mov eax, dword ptr [ebp + {D.sym['g_desc'] + 0x28:#x}]
        cmp eax, 0x55509310
        jne rd_fmt
        mov {v('g_565')}, 0x0
    rd_fmt:
        mov eax, {CHUNK * CHUNK * 2:#x}
        call alloc
        mov {v('g_chunk')}, eax
        test eax, eax
        jz rd_nomem
        lea edi, [ebp + {a('g_desc')}]
        mov dword ptr [edi], {CHUNK:#x}
        mov dword ptr [edi + 0x4], {CHUNK:#x}
        mov dword ptr [edi + 0x8], 0x10
        mov dword ptr [edi + 0xc], {CHUNK * 2:#x}
        mov dword ptr [edi + 0x10], 0x0
        mov dword ptr [edi + 0x14], 0x0
        mov dword ptr [edi + 0x18], {CHUNK:#x}
        mov dword ptr [edi + 0x1c], {CHUNK:#x}
        mov dword ptr [edi + 0x20], eax
        mov ebx, {v('g_map')}
        lea edi, [ebp + {a('g_save')}]
        mov eax, dword ptr [ebx + 0x80]
        mov dword ptr [edi], eax
        mov eax, dword ptr [ebx + 0x84]
        mov dword ptr [edi + 0x4], eax
        mov eax, dword ptr [ebx + 0x88]
        mov dword ptr [edi + 0x8], eax
        mov eax, dword ptr [ebx + 0x94]
        mov dword ptr [edi + 0xc], eax
        mov eax, dword ptr [ebx + 0x98]
        mov dword ptr [edi + 0x10], eax
        mov eax, dword ptr [ebx + 0x9c]
        mov dword ptr [edi + 0x14], eax
        mov eax, dword ptr [ebx + 0xa0]
        mov dword ptr [edi + 0x18], eax
        mov {v('g_skb')}, 0x0
        lea eax, [ebp + {a('s_aowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz rd_nosky
        add eax, {SKB_RVA:#x}
        cmp dword ptr [eax], {SKB_MAGIC:#x}
        jne rd_nosky
        mov {v('g_skb')}, eax
        mov ebx, {v('g_map')}
        mov ecx, {v('g_lvidx')}
        mov dword ptr [ebx + 0x88], ecx
        lea ecx, [eax + 0x10]
        mov eax, ebx
        lea edx, [ebp + {a('g_desc')}]
        call ecx
    rd_nosky:
        mov eax, {v('g_y0')}
        mov {v('g_cy')}, eax
    rd_cy:
        mov eax, {v('g_cy')}
        cmp eax, {v('g_y1')}
        jge rd_end
        mov eax, {v('g_x0')}
        mov {v('g_cx')}, eax
    rd_cx:
        mov eax, {v('g_cx')}
        cmp eax, {v('g_x1')}
        jge rd_cyn
        call chunk
        add {v('g_cx')}, {CHUNK:#x}
        jmp rd_cx
    rd_cyn:
        add {v('g_cy')}, {CHUNK:#x}
        jmp rd_cy
    rd_end:
        mov eax, {v('g_skb')}
        test eax, eax
        jz rd_e2
        add eax, 0x1a
        call eax
    rd_e2:
        mov ebx, {v('g_map')}
        lea edi, [ebp + {a('g_save')}]
        mov eax, dword ptr [edi]
        mov dword ptr [ebx + 0x80], eax
        mov eax, dword ptr [edi + 0x4]
        mov dword ptr [ebx + 0x84], eax
        mov eax, dword ptr [edi + 0x8]
        mov dword ptr [ebx + 0x88], eax
        mov eax, dword ptr [edi + 0xc]
        mov dword ptr [ebx + 0x94], eax
        mov eax, dword ptr [edi + 0x10]
        mov dword ptr [ebx + 0x98], eax
        mov eax, dword ptr [edi + 0x14]
        mov dword ptr [ebx + 0x9c], eax
        mov eax, dword ptr [edi + 0x18]
        mov dword ptr [ebx + 0xa0], eax
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xd8]
        mov eax, {v('g_map')}
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xdc]
        mov eax, {v('g_chunk')}
        call free
        mov {v('g_chunk')}, 0x0
        mov eax, 0x1
        ret
    rd_nomem:
        lea eax, [ebp + {a('s_nomem')}]
        call msg
    rd_r0:
        xor eax, eax
        ret

    bbox:
        mov {v('g_c0')}, 0x7fffffff
        mov {v('g_c1')}, 0xffffffff
        mov {v('g_r0')}, 0x7fffffff
        mov {v('g_r1')}, 0xffffffff
        xor esi, esi
    bb_c:
        cmp esi, {v('g_cols')}
        jge bb_done
        xor edi, edi
    bb_r:
        cmp edi, {v('g_rows')}
        jge bb_cn
        mov ecx, edi
        mov edx, esi
        mov eax, {v('g_lv')}
        call {v('f_getfield')}
        test eax, eax
        jz bb_rn
        movzx ecx, byte ptr [eax + 0xd]
        test ecx, ecx
        jz bb_rn
        mov ebx, dword ptr [eax + 0x8]
    bb_h:
        dec ecx
        js bb_in
        mov edx, dword ptr [ebx + ecx*4]
        test edx, edx
        jz bb_h
        mov edx, dword ptr [edx]
        cmp edx, {v('f_border')}
        je bb_rn
        jmp bb_h
    bb_in:
        cmp esi, {v('g_c0')}
        jge bb1
        mov {v('g_c0')}, esi
    bb1:
        cmp esi, {v('g_c1')}
        jle bb2
        mov {v('g_c1')}, esi
    bb2:
        cmp edi, {v('g_r0')}
        jge bb3
        mov {v('g_r0')}, edi
    bb3:
        cmp edi, {v('g_r1')}
        jle bb_rn
        mov {v('g_r1')}, edi
    bb_rn:
        inc edi
        jmp bb_r
    bb_cn:
        inc esi
        jmp bb_c
    bb_done:
        cmp {v('g_c1')}, 0x0
        jl bb_all
        mov eax, {v('g_c0')}
        dec eax
        jge bb_d1
        xor eax, eax
    bb_d1:
        mov {v('g_c0')}, eax
        mov eax, {v('g_r0')}
        dec eax
        jge bb_d2
        xor eax, eax
    bb_d2:
        mov {v('g_r0')}, eax
        mov eax, {v('g_c1')}
        inc eax
        mov edx, {v('g_cols')}
        dec edx
        cmp eax, edx
        jle bb_d3
        mov eax, edx
    bb_d3:
        mov {v('g_c1')}, eax
        mov eax, {v('g_r1')}
        inc eax
        mov edx, {v('g_rows')}
        dec edx
        cmp eax, edx
        jle bb_d4
        mov eax, edx
    bb_d4:
        mov {v('g_r1')}, eax
        mov eax, {v('g_c0')}
        shl eax, 0x5
        mov {v('g_x0')}, eax
        mov eax, {v('g_r0')}
        shl eax, 0x5
        mov {v('g_y0')}, eax
        mov eax, {v('g_c1')}
        sub eax, {v('g_c0')}
        inc eax
        shl eax, 0x5
        add eax, 0x10
        mov edx, {v('g_r1')}
        sub edx, {v('g_r0')}
        inc edx
        shl edx, 0x5
        add edx, 0x10
        ret
    bb_all:
        mov {v('g_x0')}, 0x0
        mov {v('g_y0')}, 0x0
        mov eax, {v('g_cols')}
        shl eax, 0x5
        add eax, 0x10
        mov edx, {v('g_rows')}
        shl edx, 0x5
        add edx, 0x10
        ret

    chunk:
        mov edi, {v('g_chunk')}
        xor eax, eax
        mov ecx, {CHUNK * CHUNK // 2:#x}
        rep stosd dword ptr es:[edi], eax
        mov ebx, {v('g_map')}
        mov eax, {v('g_lvidx')}
        mov dword ptr [ebx + 0x88], eax
        mov eax, {v('g_cx')}
        mov dword ptr [ebx + 0x80], eax
        mov eax, {v('g_cy')}
        mov dword ptr [ebx + 0x84], eax
        mov eax, {v('g_cx')}
        sar eax, 0x5
        sub eax, 0x2
        jge ch_c0
        xor eax, eax
    ch_c0:
        mov {v('g_c0')}, eax
        mov eax, {v('g_cx')}
        add eax, {CHUNK:#x}
        sar eax, 0x5
        add eax, 0x3
        cmp eax, {v('g_cols')}
        jle ch_c1
        mov eax, {v('g_cols')}
    ch_c1:
        mov {v('g_c1')}, eax
        mov eax, {v('g_cy')}
        sar eax, 0x5
        sub eax, 0x2
        jge ch_r0
        xor eax, eax
    ch_r0:
        mov {v('g_r0')}, eax
        mov eax, {v('g_cy')}
        add eax, {CHUNK:#x}
        sar eax, 0x5
        add eax, 0x6
        cmp eax, {v('g_rows')}
        jle ch_r1
        mov eax, {v('g_rows')}
    ch_r1:
        mov {v('g_r1')}, eax
        mov eax, {v('g_c0')}
        mov dword ptr [ebx + 0x94], eax
        mov eax, {v('g_c1')}
        sub eax, {v('g_c0')}
        jle ch_copy
        mov dword ptr [ebx + 0x9c], eax
        mov eax, {v('g_r0')}
        mov dword ptr [ebx + 0x98], eax
        mov eax, {v('g_r1')}
        sub eax, {v('g_r0')}
        jle ch_copy
        mov dword ptr [ebx + 0xa0], eax
        mov eax, ebx
        call {v('f_rvs')}
        mov eax, {v('g_map')}
        call {v('f_rvd')}
        mov esi, {v('g_c0')}
    ch_fc:
        cmp esi, {v('g_c1')}
        jge ch_draw
        mov edi, {v('g_r0')}
    ch_fr:
        cmp edi, {v('g_r1')}
        jge ch_fcn
        mov ecx, edi
        mov edx, esi
        mov eax, {v('g_lv')}
        call {v('f_getfield')}
        test eax, eax
        jz ch_frn
        mov ebx, eax
        mov edx, {v('g_map')}
        mov edx, dword ptr [edx + 0x1c]
        call {v('f_csv')}
        mov eax, ebx
        mov edx, {v('g_map')}
        mov edx, dword ptr [edx + 0x20]
        call {v('f_cdv')}
    ch_frn:
        inc edi
        jmp ch_fr
    ch_fcn:
        inc esi
        jmp ch_fc
    ch_draw:
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x1c]
        call drawlist
        xor ecx, ecx
        call skypass
        mov eax, {v('g_map')}
        mov eax, dword ptr [eax + 0x20]
        call drawlist
        mov ecx, 0x2
        call skypass
    ch_copy:
        xor esi, esi
    cc_y:
        cmp esi, {CHUNK:#x}
        jge cc_r
        mov eax, {v('g_cy')}
        add eax, esi
        cmp eax, {v('g_y1')}
        jge cc_r
        sub eax, {v('g_y0')}
        imul eax, {v('g_w')}
        mov {v('g_tmp')}, eax
        xor edi, edi
    cc_x:
        cmp edi, {CHUNK:#x}
        jge cc_yn
        mov eax, {v('g_cx')}
        add eax, edi
        cmp eax, {v('g_x1')}
        jge cc_yn
        sub eax, {v('g_x0')}
        add eax, {v('g_tmp')}
        shl eax, 0x2
        add eax, {v('g_img')}
        mov {v('g_tmp2')}, eax
        mov eax, esi
        shl eax, {(CHUNK * 2).bit_length() - 1:#x}
        add eax, {v('g_chunk')}
        movzx eax, word ptr [eax + edi*2]
        call px16
        mov edx, {v('g_tmp2')}
        mov dword ptr [edx], eax
        inc edi
        jmp cc_x
    cc_yn:
        inc esi
        jmp cc_y
    cc_r:
        ret

    skypass:
        mov esi, {v('g_skb')}
        test esi, esi
        jz sp_r
        add esi, 0x15
        mov eax, {v('g_map')}
        lea edx, [ebp + {a('g_desc')}]
        call esi
    sp_r:
        ret

    drawlist:
        push ebx
        push esi
        push edi
        mov ebx, eax
        test ebx, ebx
        jz dl_r
        mov edx, dword ptr [ebx]
        call dword ptr [edx + 0x90]
        mov esi, dword ptr [ebx + 0xc]
    dl_l:
        dec esi
        js dl_r
        mov eax, dword ptr [ebx + 0x14]
        mov edi, dword ptr [eax + esi*8 + 0x4]
        test edi, edi
        jz dl_l
        lea eax, [ebp + {a('g_desc')}]
        push eax
        mov eax, {v('g_map')}
        mov ecx, dword ptr [eax + 0x84]
        mov edx, dword ptr [eax + 0x80]
        mov eax, edi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0xa8]
        jmp dl_l
    dl_r:
        pop edi
        pop esi
        pop ebx
        ret

    addframe:
        mov ebx, {v('g_fs')}
        lea edi, [ebp + {a('g_sfs')}]
        mov ecx, 0x4
    af_sc:
        mov eax, dword ptr [ebx]
        imul eax, {v('g_fsc')}
        mov dword ptr [edi], eax
        add ebx, 0x4
        add edi, 0x4
        dec ecx
        jnz af_sc
        mov ecx, 0x8
    af_sp:
        mov eax, dword ptr [ebx]
        mov dword ptr [edi], eax
        add ebx, 0x4
        add edi, 0x4
        dec ecx
        jnz af_sp
        lea ebx, [ebp + {a('g_sfs')}]
        mov {v('g_fs')}, ebx
        mov eax, dword ptr [ebx]
        shl eax, 0x1
        add eax, {v('g_w')}
        mov {v('g_fw')}, eax
        mov edx, dword ptr [ebx + 0x4]
        shl edx, 0x1
        add edx, {v('g_h')}
        mov {v('g_fh')}, edx
        imul eax, edx
        shl eax, 0x2
        call alloc
        mov {v('g_fimg')}, eax
        test eax, eax
        jnz af_go
        lea eax, [ebp + {a('s_nomem')}]
        call msg
        xor eax, eax
        ret
    af_go:
        xor esi, esi
    af_cy:
        cmp esi, {v('g_h')}
        jge af_pieces
        mov eax, esi
        imul eax, {v('g_w')}
        shl eax, 0x2
        add eax, {v('g_img')}
        push esi
        mov edx, esi
        mov ecx, {v('g_fs')}
        add edx, dword ptr [ecx + 0x4]
        imul edx, {v('g_fw')}
        add edx, dword ptr [ecx]
        shl edx, 0x2
        add edx, {v('g_fimg')}
        mov esi, eax
        mov edi, edx
        mov ecx, {v('g_w')}
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop esi
        inc esi
        jmp af_cy
    af_pieces:
        mov ebx, {v('g_fs')}
        mov esi, dword ptr [ebx]
    af_tb:
        mov eax, {v('g_fw')}
        sub eax, dword ptr [ebx]
        cmp esi, eax
        jge af_lr
        sub eax, esi
        cmp eax, dword ptr [ebx + 0x8]
        jle af_tbw
        mov eax, dword ptr [ebx + 0x8]
    af_tbw:
        mov {v('g_bw')}, eax
        mov eax, dword ptr [ebx + 0x4]
        mov {v('g_bh')}, eax
        mov eax, dword ptr [ebx + 0x8]
        mov {v('g_bsw')}, eax
        mov {v('g_bx')}, esi
        mov {v('g_by')}, 0x0
        mov eax, dword ptr [ebx + 0x14]
        mov {v('g_bsrc')}, eax
        call blit
        mov eax, {v('g_fh')}
        sub eax, dword ptr [ebx + 0x4]
        mov {v('g_by')}, eax
        mov eax, dword ptr [ebx + 0x28]
        mov {v('g_bsrc')}, eax
        call blit
        add esi, dword ptr [ebx + 0x8]
        jmp af_tb
    af_lr:
        mov esi, dword ptr [ebx + 0x4]
    af_lr2:
        mov eax, {v('g_fh')}
        sub eax, dword ptr [ebx + 0x4]
        cmp esi, eax
        jge af_corn
        sub eax, esi
        cmp eax, dword ptr [ebx + 0xc]
        jle af_lrh
        mov eax, dword ptr [ebx + 0xc]
    af_lrh:
        mov {v('g_bh')}, eax
        mov eax, dword ptr [ebx]
        mov {v('g_bw')}, eax
        mov {v('g_bsw')}, eax
        mov {v('g_by')}, esi
        mov {v('g_bx')}, 0x0
        mov eax, dword ptr [ebx + 0x1c]
        mov {v('g_bsrc')}, eax
        call blit
        mov eax, {v('g_fw')}
        sub eax, dword ptr [ebx]
        mov {v('g_bx')}, eax
        mov eax, dword ptr [ebx + 0x20]
        mov {v('g_bsrc')}, eax
        call blit
        add esi, dword ptr [ebx + 0xc]
        jmp af_lr2
    af_corn:
        mov eax, dword ptr [ebx]
        mov {v('g_bw')}, eax
        mov {v('g_bsw')}, eax
        mov eax, dword ptr [ebx + 0x4]
        mov {v('g_bh')}, eax
        mov {v('g_bx')}, 0x0
        mov {v('g_by')}, 0x0
        mov eax, dword ptr [ebx + 0x10]
        mov {v('g_bsrc')}, eax
        call blit
        mov eax, {v('g_fw')}
        sub eax, dword ptr [ebx]
        mov {v('g_bx')}, eax
        mov eax, dword ptr [ebx + 0x18]
        mov {v('g_bsrc')}, eax
        call blit
        mov eax, {v('g_fh')}
        sub eax, dword ptr [ebx + 0x4]
        mov {v('g_by')}, eax
        mov eax, dword ptr [ebx + 0x2c]
        mov {v('g_bsrc')}, eax
        call blit
        mov {v('g_bx')}, 0x0
        mov eax, dword ptr [ebx + 0x24]
        mov {v('g_bsrc')}, eax
        call blit
        mov eax, {v('g_fimg')}
        mov {v('g_bsrc')}, eax
        mov eax, {v('g_fw')}
        mov {v('g_w')}, eax
        mov eax, {v('g_fh')}
        mov {v('g_h')}, eax
        mov eax, 0x1
        ret

    blit:
        push ebx
        push esi
        push edi
        mov eax, {v('g_bsw')}
        xor edx, edx
        div {v('g_fsc')}
        mov {v('g_bstr')}, eax
        xor esi, esi
    bl_y:
        cmp esi, {v('g_bh')}
        jge bl_r
        xor edi, edi
    bl_x:
        cmp edi, {v('g_bw')}
        jge bl_yn
        mov eax, esi
        xor edx, edx
        div {v('g_fsc')}
        imul eax, {v('g_bstr')}
        mov ebx, eax
        mov eax, edi
        xor edx, edx
        div {v('g_fsc')}
        add eax, ebx
        shl eax, 0x2
        add eax, {v('g_bsrc')}
        mov eax, dword ptr [eax]
        test eax, 0xff000000
        jz bl_xn
        mov edx, esi
        add edx, {v('g_by')}
        imul edx, {v('g_fw')}
        add edx, edi
        add edx, {v('g_bx')}
        shl edx, 0x2
        add edx, {v('g_fimg')}
        mov dword ptr [edx], eax
    bl_xn:
        inc edi
        jmp bl_x
    bl_yn:
        inc esi
        jmp bl_y
    bl_r:
        pop edi
        pop esi
        pop ebx
        ret

    savepng:
        push 0x130
        lea eax, [ebp + {a('g_wpath')}]
        push eax
        push 0xffffffff
        push {v('g_pimg')}
        push 0x0
        push 0x0
        call {imp('MultiByteToWideChar')}
        test eax, eax
        jz sp_fail
        mov {v('g_bmp')}, 0x0
        lea eax, [ebp + {a('g_bmp')}]
        push eax
        push {v('g_bsrc')}
        push 0x26200a
        mov eax, {v('g_w')}
        shl eax, 0x2
        push eax
        push {v('g_h')}
        push {v('g_w')}
        call {imp('GdipCreateBitmapFromScan0')}
        test eax, eax
        jnz sp_fail
        push 0x0
        lea eax, [ebp + {a('g_clsid')}]
        push eax
        lea eax, [ebp + {a('g_wpath')}]
        push eax
        push {v('g_bmp')}
        call {imp('GdipSaveImageToFile')}
        mov ebx, eax
        push {v('g_bmp')}
        call {imp('GdipDisposeImage')}
        test ebx, ebx
        jnz sp_fail
        mov eax, 0x1
        ret
    sp_fail:
        lea edi, [ebp + {a('g_msg')}]
        lea esi, [ebp + {a('s_nosave')}]
        call scat
        mov esi, {v('g_pimg')}
        call scat
        mov byte ptr [edi], 0x0
        lea eax, [ebp + {a('g_msg')}]
        call msg
        xor eax, eax
        ret

""" + MS.asm(v, a, imp, GD) + BL.asm(v, a, imp, GD) + LV.asm(v, a, imp, GD) + FP.asm(v, a, imp, GD) + CN.asm(v, a, imp, GD) + """
    probe_end:
        mov eax, run
        mov eax, dlgproc
        mov eax, initx
    """


def build_imports(rva):
    """-> (bytes, {name: IAT VA}, import dir rva, size, iat rva, iat size)"""
    nd = len(IMPORTS)
    desc_sz = 20 * (nd + 1)
    # layout: descriptors | ILTs | IATs | names
    ilt_off = desc_sz
    sizes = [4 * (len(f) + 1) for _d, f in IMPORTS]
    iat_off = ilt_off + sum(sizes)
    names_off = iat_off + sum(sizes)
    names = bytearray()
    name_rva = {}
    for dll, funcs in IMPORTS:
        name_rva[dll] = rva + names_off + len(names); names += dll.encode() + b"\0"
        if len(names) % 2: names += b"\0"
        for f in funcs:
            name_rva[(dll, f)] = rva + names_off + len(names)
            names += struct.pack("<H", 0) + f.encode() + b"\0"
            if len(names) % 2: names += b"\0"
    b = bytearray(names_off) + names
    iat_va = {}
    o_ilt, o_iat = ilt_off, iat_off
    for i, (dll, funcs) in enumerate(IMPORTS):
        struct.pack_into("<IIIII", b, 20 * i, rva + o_ilt, 0, 0, name_rva[dll], rva + o_iat)
        for j, f in enumerate(funcs):
            struct.pack_into("<I", b, o_ilt + 4 * j, name_rva[(dll, f)])
            struct.pack_into("<I", b, o_iat + 4 * j, name_rva[(dll, f)])
            iat_va[f] = BASE + rva + o_iat + 4 * j
        o_ilt += 4 * (len(funcs) + 1); o_iat += 4 * (len(funcs) + 1)
    return bytes(b), iat_va, rva, desc_sz, rva + iat_off, sum(sizes)


def build_exports(rva, funcs):
    """funcs = [(name, rva)] -> export directory (names sorted, ordinals = list order)"""
    funcs = sorted(funcs)
    n = len(funcs)
    name = b"AoWxShot.dll\0"
    o_funcs = 40; o_names = o_funcs + 4 * n; o_ords = o_names + 4 * n; o_dll = o_ords + 2 * n
    strs = bytearray(name)
    name_off = []
    for fn, _r in funcs:
        name_off.append(o_dll + len(strs)); strs += fn.encode() + b"\0"
    b = bytearray(o_dll) + strs
    struct.pack_into("<IIHHIIIIIII", b, 0, 0, 0, 0, 0, rva + o_dll, 1, n, n, rva + o_funcs, rva + o_names, rva + o_ords)
    for i, (fn, fr) in enumerate(funcs):
        struct.pack_into("<I", b, o_funcs + 4 * i, fr)
        struct.pack_into("<I", b, o_names + 4 * i, rva + name_off[i])
        struct.pack_into("<H", b, o_ords + 2 * i, i)
    return bytes(b)


def assemble(src, at):
    import sky_clouds_overlay_asm as OV
    return OV.asm(src, at)


def build(game_dir):
    D, fp = build_data(BASE + SEC_RVA, game_dir)
    D.align(16)
    imp_rva = SEC_RVA + len(D.b)
    ib, IAT, idir, isz, iat_rva, iat_sz = build_imports(imp_rva)
    body = bytearray(D.b) + ib
    while len(body) % 16:
        body.append(0)
    code_rva = SEC_RVA + len(body)
    code_va = BASE + code_rva
    gd = code_va + 0x10
    prolog = bytearray(0x20)
    prolog[0:8] = bytes.fromhex("b801000000c20c00")                       # DllMain: mov eax,1 ; ret 0xC
    prolog[0x10:0x1C] = b"\xe8\x00\x00\x00\x00\x5d\x81\xed" + struct.pack("<I", gd + 5)   # call $+5 ; pop ebp ; sub ebp,
    prolog[0x1C] = 0xC3                                                      # ret
    src = asm_text(D, IAT, code_va)
    code = assemble(src, code_va + 0x20)
    # recover label addresses from the probe (mov eax, run / mov eax, dlgproc at the very end)
    tail = code[-15:]
    assert tail[0] == 0xB8 and tail[5] == 0xB8 and tail[10] == 0xB8, tail.hex()
    run_va, dlg_va, init_va = (struct.unpack_from("<I", tail, i)[0] for i in (1, 6, 11))
    code = code[:-15]
    assert run_va == code_va + 0x20, hex(run_va)
    # the dlgproc label is used as [ebp + dlgproc] (VA + delta) -> keystone resolved it to its preferred VA: good
    body += prolog + code
    while len(body) % 16:
        body.append(0)
    exp_rva = SEC_RVA + len(body)
    eb = build_exports(exp_rva, [("Run", run_va - BASE), ("Init", init_va - BASE)])
    body += eb
    sec_vs = len(body)
    raw_sz = (sec_vs + 0x1FF) & ~0x1FF
    reloc_rva = (SEC_RVA + sec_vs + 0xFFF) & ~0xFFF
    reloc = struct.pack("<IIHH", SEC_RVA, 12, 0, 0)
    size_of_image = reloc_rva + 0x1000
    # headers
    h = bytearray(0x400)
    h[0:2] = b"MZ"; struct.pack_into("<I", h, 0x3C, 0x40)
    h[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", h, 0x44, 0x14C, 2, 0, 0, 0, 0xE0, 0x2102)
    o = 0x58
    struct.pack_into("<HBBIIIIII", h, o, 0x10B, 6, 0, raw_sz, 0x200, 0, code_rva, SEC_RVA, SEC_RVA)
    struct.pack_into("<IIIHHHHHHIIIIHHIIIIII", h, o + 28, BASE, 0x1000, 0x200, 4, 0, 0, 0, 4, 0, 0,
                     size_of_image, 0x400, 0, 2, 0, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    dd = o + 96
    struct.pack_into("<II", h, dd + 0 * 8, exp_rva, len(eb))
    struct.pack_into("<II", h, dd + 1 * 8, idir, isz)
    struct.pack_into("<II", h, dd + 5 * 8, reloc_rva, len(reloc))
    struct.pack_into("<II", h, dd + 12 * 8, iat_rva, iat_sz)
    so = o + 0xE0
    h[so:so + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", h, so + 8, sec_vs, SEC_RVA, raw_sz, 0x400, 0, 0, 0, 0, 0xE0000060)
    h[so + 40:so + 48] = b".reloc\0\0"
    struct.pack_into("<IIIIIIHHI", h, so + 48, len(reloc), reloc_rva, 0x200, 0x400 + raw_sz, 0, 0, 0, 0, 0x42000040)
    img = bytes(h) + bytes(body) + bytes(raw_sz - len(body)) + reloc + bytes(0x200 - len(reloc))
    info = dict(code_va=code_va, run_va=run_va, dlg_va=dlg_va, init_va=init_va, code_len=len(code), data_len=len(D.b), size=len(img))
    return img, info


def main():
    gd = os.path.dirname(HERE)
    img, info = build(gd)
    import pefile
    pe = pefile.PE(data=img)
    exps = [(e.name, hex(pe.OPTIONAL_HEADER.ImageBase + e.address)) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols]
    imps = [(i.dll, len(i.imports)) for i in pe.DIRECTORY_ENTRY_IMPORT]
    print("AoWxShot.dll %d B | code %#x (%d B) | data %d B | exports %s | imports %s"
          % (info["size"], info["code_va"], info["code_len"], info["data_len"], exps, imps))
    if "--check" in sys.argv:
        return 0
    cur = open(OUT, "rb").read() if os.path.exists(OUT) else None
    if cur == img:
        print("already up to date:", OUT); return 0
    with open(OUT, "wb") as fh:
        fh.write(img)
    assert open(OUT, "rb").read() == img
    print("written", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
