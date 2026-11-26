#!/usr/bin/env python3
r"""AoWDevX -- "Theme" option in the Options menu: Classic / Dark.

USER REQUEST 2026-09-01: below "Preview Mode" in the editor's Options menu,
add "Theme" switchable between "Classic" (unchanged) and "Dark" (similar to
the modding tools' dark mode). Setting persists across sessions.

=============================== HOW IT WORKS ===============================
A single 6-byte hook on the frame handler `TMainForm.HSMEditUpdateFrame`
@0x00428D18 (prologue `55 8B EC 83 C4 9C`, reloc-free; eax = the main form)
drives everything from a new RWX section `.xthm` @VA 0x004E4000:

  * FIRST TICK: read the setting (registry named value General\"Editor Theme"
    in the mod's isolated tree, "1" = Dark) and build the menu at runtime:
    a "Theme" TMenuItem appended to OptionsItem ([mainform+0x208]) -- Preview
    Mode is the LAST child of Options (verified in the DFM), so Add() lands
    directly below it -- with radio children "Classic"/"Dark" whose OnClick
    TMethod is {our handler, Data = 0/1} (TMenuItem.FOnClick = +0x60/+0x64;
    VCL passes Data in eax, so the handler receives the theme id directly).
  * EVERY 8th TICK while Dark: re-walk Screen.Forms and recolor anything not
    yet dark -- this also catches dialogs created later (Map Validation etc.)
    within ~a quarter second. TFont.SetColor self-checks (cmp [font+0x14])
    and we compare [ctrl+0x54] (TControl.FColor) before TControl.SetColor,
    so a settled UI costs only reads -- no repaint churn.
  * MENU CLICK: store the id, update the radio checkmarks, write the registry
    (TAoWRegistry.rwString mode 1), and walk immediately -- Dark applies dark
    colors, Classic restores the STANDARD system colors (clBtnFace/clWindow/
    clWindowText). "Classic remains unchanged": with the setting off, the
    walker never touches a single control.

COLORS (from the modding tools' Fusion-dark look): window/panels 0x383838,
edit-like surfaces (TCustomEdit/TCustomMemo descendants, TCustomGrid,
TCustomListBox, TCustomComboBox, TCustomListView, TCustomTreeView) 0x252525,
text 0xE0E0E0. Windows-drawn chrome (title bar, menu bar, scrollbars) is not
themable in Delphi 3 and stays light -- known cosmetic limitation. The map /
scanner / palette art draw themselves and are unaffected.

=========================== VERIFIED RE (9/1) ==============================
AoWDevX gets its VCL from **VCL30.dpl packages**, so nearly everything is an
existing IMPORT (no signature hunting, no statically-linked copies):
  IAT: TMenuItem.Create [0x4324AC] / .Add [0x432490] (eax=parent, edx=item)
       / .SetCaption [0x4324A8] / .SetChecked [0x4324A4] (eax, dl)
       / .SetRadioItem [0x43248C]; Controls.TControl.SetColor [0x43237C]
       (eax, edx=TColor); Forms.Screen [0x432220] (ptr to the global);
       System.@IsClass [0x432128]; Menus..TMenuItem classref [0x4324BC];
       LStrClr thunk 0x004037D0.
  VCL30 non-imports via a runtime delta ([0x432210] - 0x41336300, the
  Forms.TCustomForm.Create anchor proven by build_editor_timerres.py):
       Graphics.TFont.SetColor 0x413294BC (FColor=+0x14, self-checking);
       classrefs Controls..TControl 0x4133FBB0, StdCtrls..TCustomEdit
       0x4134A4A8, Grids..TCustomGrid 0x41380EF4, ComCtrls..TCustomListView
       0x41363178, StdCtrls..TCustomListBox 0x4134A186*, StdCtrls..
       TCustomComboBox*, ComCtrls..TCustomTreeView* (*resolved at build time
       from VCL30's export table -- the script aborts if any is missing).
  Layouts (Delphi 3): TControl.FFont=+0x50, FColor=+0x54; TComponent
       .FComponents TList=+0x10; TScreen forms TList=+0x40; TList data=+0x4,
       count=+0x8; TMenuItem.FOnClick=+0x60 (RTTI).
  Registry via the AoWEPACK delta ([0x432E64] - 0x55704B6C, the
  AoWReg.TAoWRegistry.GetLanguage import): engine global 0x558FA048 ->
  registry [engine+0x5C] -> rwString 0x55703D08 (ret 8; mode 0 read / 1
  write; [@result] then [mode] on the stack) -- the exact machinery proven by
  the campaign-switch v7 stubs, which already rely on the editor's engine
  global being set.

Usage: dry-run default; --apply / --revert. Backup AoWDevX.exe.bak_darktheme.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWDevX.exe")
BAK = EXE + ".bak_darktheme"

IMAGE_BASE = 0x400000
SEC_VA = 0x004E4000            # RVA 0xE4000
SEC_SIZE = 0x800
SEC_NAME = b".xthm\x00\x00\x00"

HOOK = 0x00428D18              # TMainForm.HSMEditUpdateFrame prologue
HOOK_ORIG = bytes.fromhex("558bec83c49c")   # push ebp/mov ebp,esp/add esp,-64h
HOOK_RESUME = 0x00428D1E

# ⚠ v2 (9/1): the tick hook alone was NOT enough -- the Theme menu never
# appeared, implying HSMEditUpdateFrame does not fire at startup (likely only
# once a map is open). Guaranteed startup init: repoint TMainForm's
# METHOD-TABLE entry for 'FormCreate' (table @0x004272EE via [VMT-0x28],
# VMT 0x425D00; entry addr-dword at FILE 0x266F2 -> 0x0042841C) at a wrapper
# that runs the original handler and then our init -- the .xhub OnCreate
# pattern. The dword's reloc stays valid (still an in-image address). The
# tick hook remains as the periodic walker (live re-theming of new dialogs
# whenever the frame loop runs).
MT_FC_FOFF = 0x266F2
ORIG_FORMCREATE = 0x0042841C

# AoWDevX IAT slots
IAT_MI_CREATE = 0x004324AC
IAT_MI_ADD = 0x00432490
IAT_MI_SETCAP = 0x004324A8
IAT_MI_SETCHK = 0x004324A4
IAT_MI_SETRADIO = 0x0043248C
IAT_MI_CLASSREF = 0x004324BC
IAT_SETCOLOR = 0x0043237C
IAT_SCREEN = 0x00432220
IAT_ISCLASS = 0x00432128
IAT_VCL_ANCHOR = 0x00432210    # -> Forms.TCustomForm.Create
VCL_ANCHOR_PREF = 0x41336300
IAT_EP_ANCHOR = 0x00432E64     # -> AoWReg.TAoWRegistry.GetLanguage
EP_ANCHOR_PREF = 0x55704B6C
# ⚠⚠ THE STARTUP CRASH ("oh dear its the end", v3+v4): this constant was
# borrowed from the MOUSE-TAB notes, which target AOWSETUP. In AoWDevX,
# 0x4037D0 is mid-instruction garbage that reads unmapped memory -> AV in
# _readreg the moment the registry read succeeded. NEVER carry a thunk
# address across binaries -- re-derive per exe (IAT slot 0x4320F4 here).
LSTRCLR = 0x004010B0           # AoWDevX thunk -> VCL30 System.@LStrClr

# ⚠ Delphi field-table format is {offset:u32, classidx:u16, name:shortstring}
# -- the offset PRECEDES the name (the exact trap from the AoWSetup xhub
# work). A first cut read the dword AFTER the name and got +0x208 = About1,
# which attached the Theme submenu to Help > About. Proper parse of
# TMainForm's field table (VMT 0x425D00, table 0x425D92, 305 entries):
# HelpItem +0x200, OptionsItem +0x204, About1 +0x208, HSMEdit +0x22C
# (cross-checked against valgoto's proven mainform+0x22C).
OFF_OPTIONSITEM = 0x204        # TMainForm.OptionsItem

# VCL30 preferred VAs (delta-adjusted at runtime)
VCL_FONT_SETCOLOR = 0x413294BC
VCL_CLS_TCONTROL = 0x4133FBB0
# edit-like classrefs resolved from the export table at build time:
EDITLIKE_CLASSES = ["StdCtrls..TCustomEdit", "Grids..TCustomGrid",
                    "ComCtrls..TCustomListView", "StdCtrls..TCustomListBox",
                    "StdCtrls..TCustomComboBox", "ComCtrls..TCustomTreeView"]

# AoWEPACK preferred VAs
EP_ENGINE_GLOBAL = 0x558FA048
EP_RWSTRING = 0x55703D08

# colors (TColor, BGR)
DK_OTHER = 0x00383838
DK_EDIT = 0x00252525
DK_TEXT = 0x00E0E0E0
CL_OTHER = 0x8000000F          # clBtnFace
CL_EDIT = 0x80000005           # clWindow
CL_TEXT = 0x80000008           # clWindowText

# ---- data layout ----
D_THEME, D_CLASSIC, D_DARK = 0x00, 0x20, 0x40
D_GENERAL, D_VALNAME = 0x60, 0x80
D_ONE, D_ZERO = 0xA0, 0xB0
G_INIT, G_DARK, G_TICK, G_ITMC, G_ITMD = 0xC0, 0xC4, 0xC8, 0xCC, 0xD0
G_VCLD, G_EPD, G_WSLOT = 0xD4, 0xD8, 0xDC
G_RWS, G_FSC = 0xE0, 0xE4          # precomputed fn ptrs (rwString, TFont.SetColor)
G_CLSTAB = 0xE8                    # 6 dwords: VCL30 classref preferred VAs
D_CODE = 0x100


def astr(s, block=32):
    b = struct.pack("<iI", -1, len(s)) + s + b"\0"
    assert len(b) <= block, s
    return b + b"\0" * (block - len(b))


SRC = """
_entry:
    pushad
    mov  ebp, esp
    inc  dword ptr [{g_tick:#x}]
    cmp  dword ptr [{g_init:#x}], 0
    je   _doinit
    cmp  dword ptr [{g_dark:#x}], 0
    je   _out
    mov  eax, dword ptr [{g_tick:#x}]
    and  eax, 7
    jnz  _out
    call _walk
    jmp  _out
_doinit:
    call _initcore
_out:
    popad
    push ebp
    mov  ebp, esp
    add  esp, -0x64
    jmp  {resume:#x}

_fcwrap:
    push eax
    push edx
    call {orig_fc:#x}
    pop  edx
    pop  eax
    pushad
    mov  ebp, esp
    cmp  dword ptr [{g_init:#x}], 0
    jne  _fcout
    call _initcore
_fcout:
    popad
    ret

_initcore:
    mov  dword ptr [{g_init:#x}], 1
    mov  eax, dword ptr [{iat_vclanchor:#x}]
    sub  eax, {vcl_anchor_pref:#x}
    mov  dword ptr [{g_vcld:#x}], eax
    mov  eax, dword ptr [{iat_epanchor:#x}]
    sub  eax, {ep_anchor_pref:#x}
    mov  dword ptr [{g_epd:#x}], eax
    add  eax, {ep_rwstring:#x}
    mov  dword ptr [{g_rws:#x}], eax
    mov  eax, dword ptr [{g_vcld:#x}]
    add  eax, {vcl_font_setcolor:#x}
    mov  dword ptr [{g_fsc:#x}], eax
    call _readreg
    mov  eax, dword ptr [ebp + 0x1C]
    call _makemenu
    cmp  dword ptr [{g_dark:#x}], 0
    je   _icout
    call _walk
_icout:
    ret

_makemenu:
    push ebx
    push esi
    push edi
    mov  edi, eax
    mov  ecx, edi
    mov  dl, 1
    mov  eax, dword ptr [{mi_classref:#x}]
    call dword ptr [{mi_create:#x}]
    mov  ebx, eax
    mov  edx, {s_theme:#x}
    call dword ptr [{mi_setcap:#x}]
    mov  edx, ebx
    mov  eax, dword ptr [edi + {opt_item:#x}]
    call dword ptr [{mi_add:#x}]
    mov  ecx, edi
    mov  dl, 1
    mov  eax, dword ptr [{mi_classref:#x}]
    call dword ptr [{mi_create:#x}]
    mov  dword ptr [{g_itmc:#x}], eax
    mov  esi, eax
    mov  edx, {s_classic:#x}
    call dword ptr [{mi_setcap:#x}]
    mov  eax, esi
    mov  dl, 1
    call dword ptr [{mi_setradio:#x}]
    mov  dword ptr [esi + 0x60], _handler
    mov  dword ptr [esi + 0x64], 0
    mov  edx, esi
    mov  eax, ebx
    call dword ptr [{mi_add:#x}]
    mov  ecx, edi
    mov  dl, 1
    mov  eax, dword ptr [{mi_classref:#x}]
    call dword ptr [{mi_create:#x}]
    mov  dword ptr [{g_itmd:#x}], eax
    mov  esi, eax
    mov  edx, {s_dark:#x}
    call dword ptr [{mi_setcap:#x}]
    mov  eax, esi
    mov  dl, 1
    call dword ptr [{mi_setradio:#x}]
    mov  dword ptr [esi + 0x60], _handler
    mov  dword ptr [esi + 0x64], 1
    mov  edx, esi
    mov  eax, ebx
    call dword ptr [{mi_add:#x}]
    call _checks
    pop  edi
    pop  esi
    pop  ebx
    ret

_checks:
    mov  eax, dword ptr [{g_itmc:#x}]
    mov  edx, dword ptr [{g_dark:#x}]
    test edx, edx
    setz dl
    call dword ptr [{mi_setchk:#x}]
    mov  eax, dword ptr [{g_itmd:#x}]
    mov  edx, dword ptr [{g_dark:#x}]
    test edx, edx
    setnz dl
    call dword ptr [{mi_setchk:#x}]
    ret

_handler:
    pushad
    mov  dword ptr [{g_dark:#x}], eax
    call _checks
    call _writereg
    call _walk
    popad
    ret

_readreg:
    xor  eax, eax
    mov  dword ptr [{g_dark:#x}], eax
    mov  eax, dword ptr [{g_epd:#x}]
    mov  eax, dword ptr [eax + {ep_engine:#x}]
    test eax, eax
    jz   _rrout
    mov  eax, dword ptr [eax + 0x5C]
    test eax, eax
    jz   _rrout
    push 0
    mov  edx, esp
    push edx
    push 0
    mov  edx, {s_general:#x}
    mov  ecx, {s_valname:#x}
    call dword ptr [{g_rws:#x}]
    mov  eax, dword ptr [esp]
    test eax, eax
    jz   _rrclr
    cmp  byte ptr [eax], 0x31
    jne  _rrclr
    mov  dword ptr [{g_dark:#x}], 1
_rrclr:
    mov  eax, esp
    call {lstrclr:#x}
    add  esp, 4
_rrout:
    ret

_writereg:
    mov  eax, dword ptr [{g_epd:#x}]
    mov  eax, dword ptr [eax + {ep_engine:#x}]
    test eax, eax
    jz   _wrout
    mov  eax, dword ptr [eax + 0x5C]
    test eax, eax
    jz   _wrout
    mov  edx, {s_one_chars:#x}
    cmp  dword ptr [{g_dark:#x}], 0
    jne  _wr1
    mov  edx, {s_zero_chars:#x}
_wr1:
    mov  dword ptr [{g_wslot:#x}], edx
    push {g_wslot:#x}
    push 1
    mov  edx, {s_general:#x}
    mov  ecx, {s_valname:#x}
    call dword ptr [{g_rws:#x}]
_wrout:
    ret

_walk:
    push ebx
    push esi
    push edi
    mov  eax, dword ptr [{iat_screen:#x}]
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _wdone
    mov  eax, dword ptr [eax + 0x40]
    test eax, eax
    jz   _wdone
    mov  edi, dword ptr [eax + 8]
    mov  ebx, dword ptr [eax + 4]
    test edi, edi
    jz   _wdone
_wform:
    dec  edi
    js   _wdone
    mov  esi, dword ptr [ebx + edi*4]
    mov  eax, esi
    call _recolor
    push  ebx
    push  edi
    mov  eax, dword ptr [esi + 0x10]
    test eax, eax
    jz   _wnext
    mov  edi, dword ptr [eax + 8]
    mov  ebx, dword ptr [eax + 4]
_wcomp:
    dec  edi
    js   _wnext
    mov  eax, dword ptr [ebx + edi*4]
    mov  edx, dword ptr [{g_vcld:#x}]
    add  edx, {cls_tcontrol:#x}
    push eax
    call dword ptr [{iat_isclass:#x}]
    test al, al
    pop  eax
    jz   _wcomp
    call _recolor
    jmp  _wcomp
_wnext:
    pop  edi
    pop  ebx
    jmp  _wform
_wdone:
    pop  edi
    pop  esi
    pop  ebx
    ret

_recolor:
    push ebx
    push esi
    mov  esi, eax
    xor  ebx, ebx
    mov  ecx, 6
_rcls:
    push ecx
    mov  edx, dword ptr [{g_clstab:#x} + ecx*4 - 4]
    add  edx, dword ptr [{g_vcld:#x}]
    mov  eax, esi
    call dword ptr [{iat_isclass:#x}]
    pop  ecx
    test al, al
    jz   _rnc
    mov  ebx, 1
    jmp  _rgot
_rnc:
    loop _rcls
_rgot:
    cmp  dword ptr [{g_dark:#x}], 0
    je   _rclassic
    mov  edx, {dk_other:#x}
    test ebx, ebx
    jz   _rc1
    mov  edx, {dk_edit:#x}
_rc1:
    mov  ecx, {dk_text:#x}
    jmp  _rset
_rclassic:
    mov  edx, {cl_other:#x}
    test ebx, ebx
    jz   _rc2
    mov  edx, {cl_edit:#x}
_rc2:
    mov  ecx, {cl_text:#x}
_rset:
    cmp  dword ptr [esi + 0x54], edx
    je   _rfont
    push ecx
    mov  eax, esi
    call dword ptr [{iat_setcolor:#x}]
    pop  ecx
_rfont:
    mov  eax, dword ptr [esi + 0x50]
    test eax, eax
    jz   _rout
    mov  edx, ecx
    call dword ptr [{g_fsc:#x}]
_rout:
    pop  esi
    pop  ebx
    ret
"""


def build_body():
    """keystone hangs on ';' comments in this project -- source is comment-free."""
    import sys as _s
    _s.path.insert(0, os.path.join(GAME, r"reference files\BXL\re_tools"))
    from aowsyms import get_symbols
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    pe, base, exp, iat = get_symbols("VCL30.dpl")
    lut = {n: v for v, n in exp.items()}
    clstab = []
    for n in EDITLIKE_CLASSES:
        assert n in lut, "VCL30 export missing: %s" % n
        clstab.append(lut[n])

    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    src = SRC.format(
        orig_fc=ORIG_FORMCREATE,
        g_init=SEC_VA + G_INIT, g_dark=SEC_VA + G_DARK, g_tick=SEC_VA + G_TICK,
        g_itmc=SEC_VA + G_ITMC, g_itmd=SEC_VA + G_ITMD,
        g_vcld=SEC_VA + G_VCLD, g_epd=SEC_VA + G_EPD,
        g_wslot=SEC_VA + G_WSLOT, g_clstab=SEC_VA + G_CLSTAB,
        g_rws=SEC_VA + G_RWS, g_fsc=SEC_VA + G_FSC,
        s_theme=SEC_VA + D_THEME + 8, s_classic=SEC_VA + D_CLASSIC + 8,
        s_dark=SEC_VA + D_DARK + 8, s_general=SEC_VA + D_GENERAL + 8,
        s_valname=SEC_VA + D_VALNAME + 8,
        s_one_chars=SEC_VA + D_ONE + 8, s_zero_chars=SEC_VA + D_ZERO + 8,
        iat_vclanchor=IAT_VCL_ANCHOR, vcl_anchor_pref=VCL_ANCHOR_PREF,
        iat_epanchor=IAT_EP_ANCHOR, ep_anchor_pref=EP_ANCHOR_PREF,
        mi_classref=IAT_MI_CLASSREF, mi_create=IAT_MI_CREATE,
        mi_setcap=IAT_MI_SETCAP, mi_add=IAT_MI_ADD,
        mi_setchk=IAT_MI_SETCHK, mi_setradio=IAT_MI_SETRADIO,
        iat_setcolor=IAT_SETCOLOR, iat_screen=IAT_SCREEN,
        iat_isclass=IAT_ISCLASS, lstrclr=LSTRCLR,
        opt_item=OFF_OPTIONSITEM, resume=HOOK_RESUME,
        ep_engine=EP_ENGINE_GLOBAL, ep_rwstring=EP_RWSTRING,
        cls_tcontrol=VCL_CLS_TCONTROL, vcl_font_setcolor=VCL_FONT_SETCOLOR,
        dk_other=DK_OTHER, dk_edit=DK_EDIT, dk_text=DK_TEXT,
        cl_other=CL_OTHER, cl_edit=CL_EDIT, cl_text=CL_TEXT)
    code = bytes(ks.asm(src, SEC_VA + D_CODE)[0])
    body = bytearray(SEC_SIZE)
    body[D_THEME:D_THEME + 32] = astr(b"Theme")
    body[D_CLASSIC:D_CLASSIC + 32] = astr(b"Classic")
    body[D_DARK:D_DARK + 32] = astr(b"Dark")
    body[D_GENERAL:D_GENERAL + 32] = astr(b"General")
    body[D_VALNAME:D_VALNAME + 32] = astr(b"Editor Theme")
    body[D_ONE:D_ONE + 16] = astr(b"1", 16)
    body[D_ZERO:D_ZERO + 16] = astr(b"0", 16)
    for i, v in enumerate(clstab):
        struct.pack_into("<I", body, G_CLSTAB + i * 4, v - 0x41300000)
    # clstab holds PREFERRED-BASE-RELATIVE?  No: store preferred VAs; the code
    # adds the runtime DELTA (actual-preferred), so store the preferred VA.
    for i, v in enumerate(clstab):
        struct.pack_into("<I", body, G_CLSTAB + i * 4, v)
    body[D_CODE:D_CODE + len(code)] = code
    assert D_CODE + len(code) <= SEC_SIZE, len(code)
    # _fcwrap starts right after _entry's tail `add esp,-0x64; jmp resume`
    j = code.find(b"\x83\xc4\x9c\xe9")
    assert j != -1, "entry tail not found"
    fcwrap_va = SEC_VA + D_CODE + j + 8
    assert code[j + 8] == 0x50, "fcwrap must start with push eax"
    return bytes(body), len(code), fcwrap_va


def load_pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    osz = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + osz
    secs = []
    for i in range(n):
        b = tbl + i * 40
        nm = d[b:b + 8].rstrip(b"\0").decode()
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((nm, va, vsz, raw, rsz, b))
    return dict(e=e, n=n, opt=e + 24, tbl=tbl, secs=secs,
                salign=struct.unpack_from("<I", d, e + 24 + 32)[0],
                falign=struct.unpack_from("<I", d, e + 24 + 36)[0],
                hdrsz=struct.unpack_from("<I", d, e + 24 + 84)[0])


def align(x, a):
    return (x + a - 1) // a * a


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(EXE, "rb").read())
    F = load_pe(d)
    body, codelen, fcwrap_va = build_body()
    mt_cur = struct.unpack_from("<I", d, MT_FC_FOFF)[0]
    mt_state = ("original" if mt_cur == ORIG_FORMCREATE else
                "applied" if mt_cur == fcwrap_va else "FOREIGN")
    hook = b"\xE9" + struct.pack("<i", (SEC_VA + D_CODE) - (HOOK + 5)) + b"\x90"

    sect = None
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == SEC_NAME[:5]:
            sect = s
    off = HOOK - 0x400C00
    cur = bytes(d[off:off + 6])
    st = ("original" if cur == HOOK_ORIG else
          "applied" if cur == hook else "FOREIGN")
    print("  hook @0x%08X : %s   section: %s   code %d B"
          % (HOOK, st, "present" if sect else "will append", codelen))
    print("  FormCreate MT   : %s   (dword @file 0x%X, fcwrap %08X)"
          % (mt_state, MT_FC_FOFF, fcwrap_va))
    if st == "FOREIGN" or mt_state == "FOREIGN":
        print("FOREIGN bytes - refusing")
        return 1

    if revert:
        if st == "original" and mt_state == "original" and not sect:
            print("already vanilla")
            return 0
        d[off:off + 6] = HOOK_ORIG
        struct.pack_into("<I", d, MT_FC_FOFF, ORIG_FORMCREATE)
        if sect:
            d[sect[3]:sect[3] + sect[4]] = bytes(sect[4])
            print("  .xthm body zeroed (inert header kept)")
        open(EXE, "wb").write(bytes(d))
        print("reverted: Theme menu gone, editor untouched at startup")
        return 0

    if st == "applied" and mt_state == "applied" and sect and \
            bytes(d[sect[3]:sect[3] + SEC_SIZE]) == body:
        print("already applied")
        return 0
    if not do_apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- code (first 60 instructions) ----")
            for k, i in enumerate(Cs(CS_ARCH_X86, CS_MODE_32).disasm(
                    body[D_CODE:D_CODE + codelen], SEC_VA + D_CODE)):
                if k >= 60:
                    break
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))
    if sect:
        d[sect[3]:sect[3] + sect[4]] = bytes(sect[4])
        d[sect[3]:sect[3] + SEC_SIZE] = body
    else:
        assert F["tbl"] + (F["n"] + 1) * 40 <= F["hdrsz"], "no header room"
        newraw = align(len(d), F["falign"])
        d += bytes(newraw - len(d))
        rawsz = align(SEC_SIZE, F["falign"])
        d += body + bytes(rawsz - SEC_SIZE)
        b = F["tbl"] + F["n"] * 40
        struct.pack_into("<8sIIII", d, b, SEC_NAME, SEC_SIZE,
                         SEC_VA - IMAGE_BASE, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<H", d, F["e"] + 6, F["n"] + 1)
        F2 = load_pe(d)
        soi = align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]),
                    F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xthm appended, SizeOfImage -> 0x%X" % soi)
    d[off:off + 6] = hook
    struct.pack_into("<I", d, MT_FC_FOFF, fcwrap_va)
    try:
        open(EXE, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe and retry")
        return 1
    print("APPLIED - open the editor: Options menu now ends with 'Theme' > "
          "Classic/Dark (radio-checked). Dark recolors the whole UI (windows "
          "chrome stays light - D3 limit) and persists via the registry; "
          "Classic restores standard colors and never touches anything at "
          "startup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
