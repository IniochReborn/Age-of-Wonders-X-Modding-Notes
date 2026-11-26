#!/usr/bin/env python3
r"""patch_hexgrid_option_v1.py - in-game Settings -> Display "Hex Grid Thickness (F5)" dropdown (2026-10-18).

User: "make the F5 hex grid an in-game option: Settings -> Display, move the existing stuff up and respace to make room
for a dropdown styled like Settings -> Gameplay's, called 'Hex Grid Thickness (F5)' with Extra / Default / Vanilla."
    Extra   = 3-px lines  -> Flags.ilb #93      registry value 3
    Default = 2-px lines  -> Flags.ilb #92      registry value 2   (also when the value is missing / out of range)
    Vanilla = 1-px lines  -> Flags.ilb #7       registry value 1
Setting = HKCU\Software\Triumph Studios\Age of Wonders X\General\"Hex Grid Thickness" REG_DWORD (1/2/3) - the same
value AoWSetup's dropdown writes (build_aowsetup_hexgrid_dropdown.py).  Applied immediately on change; visual only, so
MP-safe (each client draws its own grid).

============================ VERIFIED RE FACTS =============================
Settings menu (TControlWin SettingsMenu: Display / Sound / Gameplay / Reset Layout / Email) -> "Display" = TVideoDialog
(title "Video Settings"): RCDATA TVIDEODIALOG rva 0x1FF230 size 0x290F, data entry @file 0x73250; VMT 0x40ADE0
(Delphi 3: field table ptr @VMT-0x38 = 0x40ADA8 -> 0x40ADFC, instance size @VMT-0x28 = 0x40ADB8 = 0xA4; 18 fields,
class table 0x40AFA7 = 10 import-slot class refs); method table 0x40AF08: ResCBChange 0x40B6EC (addr dword @0x40AF6B),
DlgShow 0x40B758 (addr dword @0x40AF8E; it reads the instance from global 0x45B07C).  Dlg = TAOWWindow 340x280.
Gameplay dropdown style (TGamePlayDlg): TAOWPanel MovPnl (frame 105, 270x22) + TAOWPanel MovFr (frame 113, 100x21) with
TAOWLabel Movelbl inside (7,5; Age10, colour 9415072) + TAOWComboBox MovementSpeedCB (W 170, Age10, colour 11002593,
ItemHeight 17, frame 113 / edit 27).  TAOWComboBox class ref = import slot 0x45ED98; SetSelected = virtual [vmt+0xB8]
(edx = index); Selected = [cb+0x138] (-1 none); OnChange = TNotifyEvent (eax = form, edx = sender).
Registry: TAoWRegistry object = [[0x45DF74]+0x5C]; AoWEPACK TAoWRegistry.rwInteger 0x55703B28 (eax = self,
edx = subkey 'General' appended to '\Software\Triumph Studios\Age of Wonders X\', ecx = value name, push @value,
push mode (0 = read if the value exists, 1 = write), ret 8) - reached through the exe's GetString IAT slot 0x45DAE8
(link 0x55704424) + link delta, so AoWEPACK's rebase is harmless.
DrawGrid AoWEPACK 0x55772DA8: `mov edx,7 / call 0x55702934` @0x55772E7C (10 B, no reloc) = TCustomImageLibrary.Get
(Ilpack 0x5521A8B8: [lib+0x48][id*8], NO bounds check - count = [lib+0x44]) of [[0x558FA044]+0x78]+0x10 (Flags.ilb).

================================ THE PATCH ================================
AoWx.exe (never rebases): new RWX section .xhgr @VA 0x630000 (RVA 0x230000 = old SizeOfImage, 0x4000):
  +0x000 signature 'HGR1' (AoWEPACK's host gate) / +0x004 G_PX (0 = not loaded yet) / +0x005 G_BUSY
  +0x010 / +0x030 AnsiString literals 'General' / 'Hex Grid Thickness'
  +0x060 code: hg_getid (-> eax = ILB id, all other regs kept) / hg_ensure (lazy registry read) / hg_save /
         hg_show (DlgShow wrapper: original, then SetSelected(3 - px) under G_BUSY) /
         hg_change (ResCBChange wrapper: sender == HexGridCB -> px = 3 - Selected, save; else the original)
  +0x300 field table (18 + HexGridCB @+0xA4, TAOWComboBox) / +0x500 class table (10 + 0x45ED98)
  +0x600 TVIDEODIALOG DFM, rebuilt: Dlg 280 -> 290 high; VideoLbl 70 -> 50; mode list 90 -> 68 (same 108 height);
         'Allow Resolution Switches' 212/214 -> 186/188; new row @212: HexPnl (30, 280x22) + HexFr (31, 150x21) +
         HexLbl "Hex Grid Thickness (F5)" + HexGridCB (180, w130, items Extra/Default/Vanilla, PriorityOpened 5000,
         OnChange -> ResCBChange); buttons stay bottom-anchored (now y 253).
  sites: VMT field-table ptr, instance size 0xA4 -> 0xA8, the two method-table addresses, the resource data entry.
AoWEPACK.dll: site 0x55772E7C (10 B) -> `call hg_epack` + 5-B nop.  Cave 0x5581F800 (PIC: rel32 calls + absolutes into
  the fixed exe only): host gate (e_lfanew sane, exe SizeOfImage >= 0x234000, 'HGR1' @0x630000 - so AoWDevX and any
  other host get #7), id = hg_getid(), bounds-checked against [lib+0x44], Get(); a nil image (Flags.ilb without #92/#93)
  falls back to #7.  The `push eax` before the site stays the vcall's argument.

LIFO / chains: nothing else hooks these sites (verified vanilla bytes).  WARNING: scripts that revert by copying a
whole-file backup (patch_aowx_cursor_coords.py --revert, ...) would also drop this patch - revert this one first.
Revert removes .xhgr only while it is the LAST section (else its body is zeroed and the header kept).
Pair with patch_hexgrid_option_ilb_v1.py (Flags.ilb #92/#93) and build_aowsetup_hexgrid_dropdown.py (AoWSetup).

Usage: py -3.10 patch_hexgrid_option_v1.py [--apply | --revert] [--exe PATH] [--epack PATH]   (dry-run default)
Backups: backup\AoWx.exe.bak_hexgridopt, backup\AoWEPACK.dll.bak_hexgridopt
"""
import os, sys, struct, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file
import dfm_edit as D

BASE = 0x400000
SEC_NAME, SEC_VA, SEC_VSIZE = b".xhgr", 0x630000, 0x4000
SIG = 0x31524748                                   # 'HGR1'
O_PX, O_BUSY, O_SGEN, O_SVAL, O_CODE, O_FT, O_CT, O_DFM = 0x4, 0x5, 0x10, 0x30, 0x60, 0x300, 0x500, 0x600
RES_ENTRY_FO, RES_RVA, RES_SIZE = 0x73250, 0x1FF230, 0x290F
VMT_FT_VA, FT_VA, VMT_INST_VA, OLD_INST, NEW_INST, NEW_FIELD = 0x40ADA8, 0x40ADFC, 0x40ADB8, 0xA4, 0xA8, 0xA4
CT_VA, CLS_COMBO_SLOT = 0x40AFA7, 0x45ED98
MT_CHANGE_VA, ORIG_CHANGE = 0x40AF6B, 0x40B6EC
MT_SHOW_VA, ORIG_SHOW = 0x40AF8E, 0x40B758
G_VIDEODLG, G_ENGINE, IAT_GETSTRING = 0x45B07C, 0x45DF74, 0x45DAE8
LINK_GETSTRING, LINK_RWINTEGER = 0x55704424, 0x55703B28
SLOT_SETSELECTED, OFF_SELECTED = 0xB8, 0x138
EP_BASE = 0x55700000
EP_SITE, EP_SITE_ORIG, EP_GET = 0x55772E7C, bytes.fromhex("ba07000000e8aefaf8ff"), 0x55702934
EP_CAVE, EP_CAVE_MAX = 0x5581F800, 0x80
GAMEPLAY_RES = "TGAMEPLAYDLG"
ROW_TOP = 212

EXE_SRC = """
hg_getid:
    push ecx
    push edx
    call hg_ensure
    movzx ecx, byte ptr [{g_px:#x}]
    mov  eax, 7
    cmp  ecx, 2
    jne  _g3
    mov  eax, 92
_g3:
    cmp  ecx, 3
    jne  _gout
    mov  eax, 93
_gout:
    pop  edx
    pop  ecx
    ret
hg_ensure:
    cmp  byte ptr [{g_px:#x}], 0
    jne  _eret
    pushad
    mov  eax, dword ptr [{g_engine:#x}]
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _edone
    mov  eax, dword ptr [eax + 0x5c]
    test eax, eax
    jz   _edone
    mov  byte ptr [{g_px:#x}], 2
    push 2
    mov  ebx, dword ptr [{iat_getstring:#x}]
    add  ebx, {delta:#x}
    mov  edx, {s_gen:#x}
    mov  ecx, {s_val:#x}
    push esp
    push 0
    call ebx
    pop  eax
    cmp  eax, 1
    jl   _edone
    cmp  eax, 3
    jg   _edone
    mov  byte ptr [{g_px:#x}], al
_edone:
    popad
_eret:
    ret
hg_save:
    pushad
    movzx eax, al
    mov  byte ptr [{g_px:#x}], al
    mov  ecx, dword ptr [{g_engine:#x}]
    mov  ecx, dword ptr [ecx]
    test ecx, ecx
    jz   _sdone
    mov  ecx, dword ptr [ecx + 0x5c]
    test ecx, ecx
    jz   _sdone
    push eax
    mov  ebx, dword ptr [{iat_getstring:#x}]
    add  ebx, {delta:#x}
    mov  eax, ecx
    mov  edx, {s_gen:#x}
    mov  ecx, {s_val:#x}
    push esp
    push 1
    call ebx
    pop  eax
_sdone:
    popad
    ret
hg_show:
    push eax
    push edx
    call {orig_show:#x}
    call hg_ensure
    mov  eax, dword ptr [{g_dlg:#x}]
    test eax, eax
    jz   _shout
    mov  eax, dword ptr [eax + {fld:#x}]
    test eax, eax
    jz   _shout
    movzx edx, byte ptr [{g_px:#x}]
    test edx, edx
    jnz  _sh1
    mov  edx, 2
_sh1:
    neg  edx
    add  edx, 3
    mov  byte ptr [{g_busy:#x}], 1
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {slot_setsel:#x}]
    mov  byte ptr [{g_busy:#x}], 0
_shout:
    pop  edx
    pop  eax
    ret
hg_change:
    mov  ecx, dword ptr [eax + {fld:#x}]
    test ecx, ecx
    jz   _orig
    cmp  edx, ecx
    jne  _orig
    cmp  byte ptr [{g_busy:#x}], 0
    jne  _cret
    mov  eax, dword ptr [ecx + {off_sel:#x}]
    cmp  eax, 2
    ja   _cret
    mov  edx, 3
    sub  edx, eax
    mov  eax, edx
    call hg_save
_cret:
    ret
_orig:
    jmp  {orig_change:#x}
"""

EP_SRC = """
    push eax
    mov  edx, 7
    mov  ecx, dword ptr [0x40003c]
    cmp  ecx, 0x400
    ja   _plain
    cmp  dword ptr [ecx + 0x400050], {soi_min:#x}
    jb   _plain
    cmp  dword ptr [{sig_va:#x}], {sig:#x}
    jne  _plain
    mov  ecx, {getid:#x}
    call ecx
    mov  edx, eax
_plain:
    mov  eax, dword ptr [esp]
    cmp  edx, dword ptr [eax + 0x44]
    jl   _get
    mov  edx, 7
_get:
    call {get:#x}
    test eax, eax
    jnz  _ok
    mov  eax, dword ptr [esp]
    mov  edx, 7
    call {get:#x}
_ok:
    add  esp, 4
    ret
"""
LABELS = ("hg_getid", "hg_ensure", "hg_save", "hg_show", "hg_change")


def asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


def exe_src():
    return EXE_SRC.format(g_px=SEC_VA + O_PX, g_busy=SEC_VA + O_BUSY, g_engine=G_ENGINE, iat_getstring=IAT_GETSTRING,
                          delta=(LINK_RWINTEGER - LINK_GETSTRING) & 0xFFFFFFFF, s_gen=SEC_VA + O_SGEN + 8,
                          s_val=SEC_VA + O_SVAL + 8, orig_show=ORIG_SHOW, g_dlg=G_VIDEODLG, fld=NEW_FIELD,
                          slot_setsel=SLOT_SETSELECTED, off_sel=OFF_SELECTED, orig_change=ORIG_CHANGE)


def build_exe_code():
    """Entry addresses: each label is located by re-assembling the source with a 5 x int3 marker right after it; the
    marked build must be exactly 5 bytes longer (no instruction changed size - only rel32 calls cross function
    labels), so the marker's offset is the label's offset in the real build."""
    va = SEC_VA + O_CODE
    src = exe_src()
    code = asm(src, va)
    assert b"\xCC" not in code
    labels = {}
    for lab in LABELS:
        marked = src.replace(lab + ":\n", lab + ":\n    int3\n    int3\n    int3\n    int3\n    int3\n", 1)
        mc = asm(marked, va)
        i = mc.find(b"\xCC" * 5)
        assert i >= 0 and len(mc) == len(code) + 5, lab
        labels[lab] = va + i
    return code, labels


def build_ep_cave(getid):
    code = asm(EP_SRC.format(soi_min=(SEC_VA - BASE) + SEC_VSIZE, sig_va=SEC_VA, sig=SIG, getid=getid, get=EP_GET),
               EP_CAVE)
    assert len(code) <= EP_CAVE_MAX, len(code)
    return code


# ---------------------------------------------------------------- DFM
def enc_int(v):
    if -128 <= v <= 127: return bytes([D.I8]) + struct.pack("<b", v)
    if -32768 <= v <= 32767: return bytes([D.I16]) + struct.pack("<h", v)
    return bytes([D.I32]) + struct.pack("<i", v)


def enc_ident(s): return bytes([D.IDENT]) + bytes([len(s)]) + s
def enc_str(s): return bytes([D.STR]) + bytes([len(s)]) + s
def sstr(s): return bytes([len(s)]) + s


def edit(dfm, edits):
    """edits: {(path_suffix, prop): encoded value bytes} -> new dfm (span replacement, back to front)."""
    w = D.walk(dfm)
    assert w.consumed == len(dfm), "DFM walk desync"
    reps = []
    for (suffix, prop), val in edits.items():
        hits = [p for p in w.props if p[0].endswith(suffix) and p[1] == prop]
        if len(hits) > 1:                            # a vaList also records each item under the same name
            hits = [p for p in hits if p[2] == D.LIST]
        assert len(hits) == 1, (suffix, prop, len(hits))
        _, nm, _, a, b, _ = hits[0]
        reps.append((a, b, D.shortstr(prop) + val))
    out = bytearray(dfm)
    for a, b, new in sorted(reps, reverse=True):
        out[a:b] = new
    return bytes(out)


def obj_span(d, o):
    def skip_val(p):
        t = d[p]; p += 1
        if t in (0, 8, 9, 13): return p
        if t == 1:
            while d[p] != 0: p = skip_val(p)
            return p + 1
        if t == 2: return p + 1
        if t == 3: return p + 2
        if t == 4: return p + 4
        if t == 5: return p + 10
        if t in (6, 7): return p + 1 + d[p]
        if t == 10: return p + 4 + struct.unpack_from("<I", d, p)[0]
        if t == 11:
            while d[p] != 0: p += 1 + d[p]
            return p + 1
        if t == 12: return p + 4 + struct.unpack_from("<I", d, p)[0]
        raise ValueError(f"vtype {t} @{p:#x}")
    p = o + 1 + d[o]; p += 1 + d[p]
    while d[p] != 0: p += 1 + d[p]; p = skip_val(p)
    p += 1
    while d[p] != 0: p = obj_span(d, p)
    return p + 1


def find_obj(d, cls, name):
    key = sstr(cls) + sstr(name)
    i = d.find(key)
    assert i > 0 and d.find(key, i + 1) == -1, name
    return i, obj_span(d, i)


def clone(gp, cls, src_name, new_name, edits, extra=b""):
    s, e = find_obj(gp, cls, src_name)
    raw = gp[s:e]
    raw = raw[:1 + len(cls)] + sstr(new_name) + raw[1 + len(cls) + 1 + len(src_name):]
    assert raw.endswith(b"\x00\x00"), "expected a leaf object"
    raw = raw[:-2] + extra + b"\x00\x00"
    wrapped = edit(b"TPF0" + raw, {("/" + new_name.decode(), k): v for k, v in edits.items()})
    return wrapped[4:]


def build_dfm(video, gameplay):
    v = edit(video, {
        ("/Dlg", "WinHeight"): enc_int(290),
        ("/VideoLbl", "WinTop"): enc_int(50), ("/VideoLbl", "Alignment.TopOffset"): enc_int(50),
        ("/T3LBPnl", "WinTop"): enc_int(68), ("/T3LBPnl", "Alignment.TopOffset"): enc_int(68),
        ("/T3LBPnl", "Alignment.BottomOffset"): enc_int(114),
        ("/ResCB", "WinTop"): enc_int(186), ("/ResCB", "Alignment.BottomOffset"): enc_int(92),
        ("/ResSwLbl", "WinTop"): enc_int(188), ("/ResSwLbl", "Alignment.BottomOffset"): enc_int(90),
    })
    pnl = clone(gameplay, b"TAOWPanel", b"MovPnl", b"HexPnl", {
        "WinLeft": enc_int(30), "WinTop": enc_int(ROW_TOP), "WinWidth": enc_int(280),
        "Alignment.LeftOffset": enc_int(30), "Alignment.RightOffset": enc_int(30),
        "Alignment.TopOffset": enc_int(ROW_TOP), "AOWWindow": enc_ident(b"Dlg")})
    fr = clone(gameplay, b"TAOWPanel", b"MovFr", b"HexFr", {
        "WinLeft": enc_int(31), "WinTop": enc_int(ROW_TOP), "WinWidth": enc_int(150),
        "Alignment.LeftOffset": enc_int(31), "Alignment.TopOffset": enc_int(ROW_TOP), "AOWWindow": enc_ident(b"Dlg")})
    lbl = clone(gameplay, b"TAOWLabel", b"Movelbl", b"HexLbl", {
        "AOWWindow": enc_ident(b"HexFr"), "Text": enc_str(b"Hex Grid Thickness (F5)")})
    cb = clone(gameplay, b"TAOWComboBox", b"MovementSpeedCB", b"HexGridCB", {
        "WinLeft": enc_int(180), "WinTop": enc_int(ROW_TOP), "WinWidth": enc_int(130), "AOWWindow": enc_ident(b"Dlg"),
        "Alignment.LeftOffset": enc_int(180), "Alignment.RightOffset": enc_int(30),
        "Alignment.TopOffset": enc_int(ROW_TOP),
        "Items.Strings": bytes([D.LIST]) + D.string_list(["Extra", "Default", "Vanilla"]),
        "PriorityOpened": enc_int(5000)},
        extra=sstr(b"OnChange") + enc_ident(b"ResCBChange"))
    s, _ = find_obj(v, b"TIvTranslator", b"Translator")
    out = v[:s] + pnl + fr + lbl + cb + v[s:]
    w = D.walk(out)
    assert w.consumed == len(out), "rebuilt DFM does not walk"
    return out


def astr(s, block):
    b = struct.pack("<iI", -1, len(s)) + s + b"\0"
    assert len(b) <= block
    return b + bytes(block - len(b))


# ---------------------------------------------------------------- PE helpers
def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    tbl = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    out = []
    for i in range(n):
        b = tbl + 40 * i
        nm = bytes(d[b:b + 8]).rstrip(b"\0")
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        out.append(dict(name=nm, vsz=vsz, va=va, rsz=rsz, raw=raw, hdr=b))
    return e, n, tbl, out


def fo(secs, rva):
    for s in secs:
        if s["va"] <= rva < s["va"] + max(s["vsz"], s["rsz"]):
            return s["raw"] + rva - s["va"]
    raise ValueError(hex(rva))


def res_bytes(d, secs, name):
    import pefile
    pe = pefile.PE(data=bytes(d))
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id == 10:
            for e in t.directory.entries:
                if str(e.name) == name:
                    s = e.directory.entries[0].data.struct
                    o = fo(secs, s.OffsetToData)
                    return bytes(d[o:o + s.Size])
    raise KeyError(name)


def build_section(d, secs):
    o = fo(secs, RES_RVA)
    video = bytes(d[o:o + RES_SIZE])
    assert video[:4] == b"TPF0"
    gameplay = res_bytes(d, secs, GAMEPLAY_RES)
    dfm = build_dfm(video, gameplay)
    ft_o = fo(secs, FT_VA - BASE)
    n, ct = struct.unpack_from("<HI", d, ft_o)
    assert (n, ct) == (18, CT_VA), (n, hex(ct))
    p = ft_o + 6
    for _ in range(n): p += 7 + d[p + 6]
    ft_body = bytes(d[ft_o + 6:p])
    ct_o = fo(secs, CT_VA - BASE)
    nc = struct.unpack_from("<H", d, ct_o)[0]
    assert nc == 10
    ct_new = struct.pack("<H", nc + 1) + bytes(d[ct_o + 2:ct_o + 2 + 4 * nc]) + struct.pack("<I", CLS_COMBO_SLOT)
    ft_new = struct.pack("<HI", n + 1, SEC_VA + O_CT) + ft_body + struct.pack("<IH", NEW_FIELD, nc) + sstr(b"HexGridCB")
    code, L = build_exe_code()
    blob = bytearray(O_DFM + len(dfm))
    struct.pack_into("<I", blob, 0, SIG)
    blob[O_SGEN:O_SGEN + 32] = astr(b"General", 32)
    blob[O_SVAL:O_SVAL + 32] = astr(b"Hex Grid Thickness", 32)
    assert O_CODE + len(code) <= O_FT, len(code)
    blob[O_CODE:O_CODE + len(code)] = code
    assert O_FT + len(ft_new) <= O_CT and O_CT + len(ct_new) <= O_DFM
    blob[O_FT:O_FT + len(ft_new)] = ft_new
    blob[O_CT:O_CT + len(ct_new)] = ct_new
    blob[O_DFM:] = dfm
    assert len(blob) <= SEC_VSIZE
    return bytes(blob), L, len(dfm)


def exe_sites(L, dfm_len):
    return [
        (VMT_FT_VA, struct.pack("<I", FT_VA), struct.pack("<I", SEC_VA + O_FT), "TVideoDialog VMT field-table ptr"),
        (VMT_INST_VA, struct.pack("<I", OLD_INST), struct.pack("<I", NEW_INST), "TVideoDialog instance size 0xA4 -> 0xA8"),
        (MT_CHANGE_VA, struct.pack("<I", ORIG_CHANGE), struct.pack("<I", L["hg_change"]), "method ResCBChange -> hg_change"),
        (MT_SHOW_VA, struct.pack("<I", ORIG_SHOW), struct.pack("<I", L["hg_show"]), "method DlgShow -> hg_show"),
        ("RES", struct.pack("<II", RES_RVA, RES_SIZE), struct.pack("<II", SEC_VA - BASE + O_DFM, dfm_len),
         "TVIDEODIALOG resource -> rebuilt DFM"),
    ]


def site_off(secs, va):
    return RES_ENTRY_FO if va == "RES" else fo(secs, va - BASE)


def main():
    a = sys.argv[1:]
    mode = "apply" if "--apply" in a else "revert" if "--revert" in a else "dry"
    exe = a[a.index("--exe") + 1] if "--exe" in a else game_file("AoWx.exe")
    ep = a[a.index("--epack") + 1] if "--epack" in a else game_file("AoWEPACK.dll")
    d = bytearray(open(exe, "rb").read())
    g = bytearray(open(ep, "rb").read())
    e, n, tbl, secs = sections(d)
    mine = [s for s in secs if s["name"] == SEC_NAME]
    sec = mine[0] if mine else None
    blob, L, dfm_len = build_section(d, secs)
    sites = exe_sites(L, dfm_len)
    print("target %s\n.xhgr @%#x: %s; code @%#x (getid %#x, show %#x, change %#x); DFM %d B (%+d)" % (
        exe, SEC_VA, "present" if sec else "absent", SEC_VA + O_CODE, L["hg_getid"], L["hg_show"], L["hg_change"],
        dfm_len, dfm_len - RES_SIZE))
    st = {"old": 0, "new": 0}
    for va, old, new, desc in sites:
        o = site_off(secs, va)
        cur = bytes(d[o:o + len(old)])
        k = "new" if cur == new else "old" if cur == old else None
        if k is None:
            print("  MISMATCH %s @file %#x: %s" % (desc, o, cur.hex()))
            return 1
        st[k] += 1
    import pefile
    pg = pefile.PE(data=bytes(g), fast_load=True)
    so = pg.get_offset_from_rva(EP_SITE - EP_BASE)
    co = pg.get_offset_from_rva(EP_CAVE - EP_BASE)
    cave = build_ep_cave(L["hg_getid"])
    site_new = b"\xE8" + struct.pack("<i", EP_CAVE - (EP_SITE + 5)) + bytes.fromhex("0f1f440000")
    ep_site, ep_cave = bytes(g[so:so + 10]), bytes(g[co:co + EP_CAVE_MAX])
    ep_state = ("new" if ep_site == site_new and ep_cave == cave + bytes(EP_CAVE_MAX - len(cave)) else
                "old" if ep_site == EP_SITE_ORIG and ep_cave == bytes(EP_CAVE_MAX) else None)
    pg.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    rel = {EP_BASE + x.rva for b in pg.DIRECTORY_ENTRY_BASERELOC for x in b.entries if x.type}
    assert not any(EP_SITE <= r < EP_SITE + 10 or EP_CAVE <= r < EP_CAVE + EP_CAVE_MAX for r in rel), \
        "reloc under a patched byte"
    print("  exe sites: %d vanilla / %d patched; AoWEPACK site+cave: %s (cave %d B @%#x, no relocs)" % (
        st["old"], st["new"], ep_state, len(cave), EP_CAVE))
    if ep_state is None:
        print("  AoWEPACK MISMATCH: site %s / cave not zero" % ep_site.hex())
        return 1
    sec_ok = sec is not None and bytes(d[sec["raw"]:sec["raw"] + len(blob)]) == blob
    applied = st["new"] == len(sites) and sec_ok and ep_state == "new"
    vanilla = st["old"] == len(sites) and ep_state == "old" and (
        sec is None or bytes(d[sec["raw"]:sec["raw"] + sec["rsz"]]) == bytes(sec["rsz"]))
    if mode == "dry":
        print("ALREADY APPLIED" if applied else "dry-run OK (vanilla) - run with --apply" if vanilla else "PARTIAL state")
        return 0
    bx, bg = bak_path(exe, ".bak_hexgridopt"), bak_path(ep, ".bak_hexgridopt")
    if mode == "apply":
        if applied:
            print("ALREADY APPLIED")
            return 0
        if not os.path.exists(bx): shutil.copy2(exe, bx); print("backup ->", bx)
        if not os.path.exists(bg): shutil.copy2(ep, bg); print("backup ->", bg)
        raw_size = (len(blob) + 0x1FF) & ~0x1FF
        if sec is None:
            assert tbl + 40 * (n + 1) <= secs[0]["raw"], "no room for another section header"
            soi = struct.unpack_from("<I", d, e + 24 + 56)[0]
            assert soi == SEC_VA - BASE, "SizeOfImage %#x != %#x (another section was appended?)" % (soi, SEC_VA - BASE)
            assert len(d) == secs[-1]["raw"] + secs[-1]["rsz"], "file has an overlay - refusing"
            d += bytes((-len(d)) % 0x200)
            raw = len(d)
            d += blob + bytes(raw_size - len(blob))
            hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC_VSIZE, SEC_VA - BASE, raw_size, raw,
                                                         0, 0, 0, 0, 0xE0000060)
            d[tbl + 40 * n:tbl + 40 * n + 40] = hdr
            struct.pack_into("<H", d, e + 6, n + 1)
            struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE + SEC_VSIZE)
            secs = sections(d)[3]
            print("appended .xhgr raw @%#x (%#x B)" % (raw, raw_size))
        else:
            assert raw_size <= sec["rsz"]
            d[sec["raw"]:sec["raw"] + sec["rsz"]] = blob + bytes(sec["rsz"] - len(blob))
            print("refreshed .xhgr")
        for va, old, new, desc in sites:
            o = site_off(secs, va)
            d[o:o + len(new)] = new
            print("  patched:", desc)
        g[so:so + 10] = site_new
        g[co:co + len(cave)] = cave
        open(exe, "wb").write(d)
        open(ep, "wb").write(g)
        print("APPLIED (AoWx.exe + AoWEPACK.dll)")
        return 0
    if vanilla:
        print("ALREADY VANILLA")
        return 0
    for va, old, new, desc in sites:
        o = site_off(secs, va)
        d[o:o + len(old)] = old
    if sec is not None:
        if secs[-1]["name"] == SEC_NAME:
            del d[sec["raw"]:]
            d[sec["hdr"]:sec["hdr"] + 40] = bytes(40)
            struct.pack_into("<H", d, e + 6, n - 1)
            struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE)
            print("removed .xhgr (last section)")
        else:
            d[sec["raw"]:sec["raw"] + sec["rsz"]] = bytes(sec["rsz"])
            print(".xhgr is not the last section - body zeroed, header kept")
    g[so:so + 10] = EP_SITE_ORIG
    g[co:co + EP_CAVE_MAX] = bytes(EP_CAVE_MAX)
    open(exe, "wb").write(d)
    open(ep, "wb").write(g)
    for f, b in ((exe, bx), (ep, bg)):
        if os.path.exists(b):
            same = open(f, "rb").read() == open(b, "rb").read()
            print("  %s %s backup" % (os.path.basename(f), "EQUALS" if same else "DIFFERS FROM"))
    print("REVERTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
