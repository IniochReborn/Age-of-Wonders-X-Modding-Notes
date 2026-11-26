#!/usr/bin/env python3
r"""AoWSetup -- "Hex Grid Thickness (F5):" dropdown on the Settings tab (2026-10-18).

User: "we also need to add the hex grid setting to AoWSetup - add a dropdown in settings."  Same three choices and the
SAME registry value as the in-game Settings -> Display dropdown (patch_hexgrid_option_v1.py):
    0  Extra    -> REG_DWORD 3  (3-px lines)
    1  Default  -> REG_DWORD 2  (2-px lines; also shown when the value is missing / not a DWORD / out of range)
    2  Vanilla  -> REG_DWORD 1  (vanilla 1-px lines)
    HKCU\Software\Triumph Studios\Age of Wonders X\General\"Hex Grid Thickness"
Saved on Settings OK; Cancel changes nothing (the combo is reloaded from the registry on every Settings open).

LAYOUT (Settings tab, styled like its two existing dropdown rows "Startup Video Mode:" / "Language:" = TLabel at x 8
(text 4 px below the combo top) + TComboBox at (184, y, 185x24)): the new row goes right under Language at y 72, and
everything below moves down / tightens so the tab still ends where it did (Email group bottom 361 -> 359):
    Sound Quality / Detail Level groups   top 72 -> 104, height 109 -> 90
    Skip Intro / Use Direct Sound         top 188 -> 200
    Allow Resolution Switches             top 216 -> 226
    Email group                           top 240 -> 250, height 121 -> 109
      its rows (edit / label tops)        20/24 -> 18/22, 52/56 -> 46/50, 84/87 -> 74/78
These are IN-PLACE DFM integer edits in TLoaderForm (same value encoding -> same length; offsets found by walking the
DFM at run time and every old value is checked).  The label + combo are runtime VCL controls (like the Campaigns
dropdown) -> they stay English in other languages (known limitation of runtime controls, see aowsetup-internals).

MACHINERY = build_aowsetup_campaign_dropdown.py's, re-used verbatim: new RWX section .xhgd @VA 0x514000 (RVA 0x114000 =
the current SizeOfImage); TLabel VMT 0x42DD08 / ctor 0x431CEC, TComboBox VMT 0x42F594 / ctor 0x4333C0, Style setter
[vmt+0x88] = 2 (csDropDownList) BEFORE parenting, SetParent [vmt+0x3C], SetBounds [vmt+0x4C], TControl.SetText
0x41CA24, TWinControl.GetHandle 0x420714, SendMessageA [0x46C4C0] CB_RESETCONTENT / CB_ADDSTRING / CB_SETCURSEL /
CB_GETCURSEL, SetTimer [0x46C490] / KillTimer [0x46C520] re-select 350 ms later (the original Settings flow clears a
selection made during the click), advapi32 RegOpenKeyExA / RegQueryValueExA / RegCreateKeyExA / RegSetValueExA /
RegCloseKey.  SettingsSheet = [form+0x1EC].

HOOK CHAIN: the SettingsBtnClick (0x4689F4) and SettingsOk (0x469090) site jmps currently point at the Campaigns
dropdown's caves (.xcmp 0x5130F0 / 0x51322C, which tail into mouse-tab -> devtab); they are re-pointed to our caves,
which tail-jmp (indirectly, through stored slots) to whatever the sites pointed at before.  Cancel is untouched.
CHAIN ORDER: devtab -> mouse_tab -> campaign_dropdown -> THIS.  Re-running an earlier script re-points the sites to
itself -> re-run this one afterwards; revert THIS one first (LIFO).

Usage: py -3.10 build_aowsetup_hexgrid_dropdown.py [--apply | --revert] [--exe PATH]   (dry-run default)
Backup: backup\AoWSetup.exe.bak_hexgriddrop.  --revert restores the two site jmps + the DFM values and removes .xhgd
while it is the last section (else zeroes its body) -> byte-identical to the pre-apply file.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file
import dfm_edit as D

IMAGE_BASE = 0x400000
SEC_VA = 0x514000            # RVA 0x114000
SEC_SIZE = 0x600
SEC_NAME = b".xhgd\x00\x00\x00"

CBO_VMT, CBO_CTOR = 0x0042F594, 0x004333C0
LBL_VMT, LBL_CTOR = 0x0042DD08, 0x00431CEC
SETTEXT = 0x0041CA24
GETHANDLE = 0x00420714
SLOT_SETPARENT, SLOT_SETBOUNDS, SLOT_SETSTYLE = 0x3C, 0x4C, 0x88
OFF_SETTINGSSHEET = 0x1EC
IAT_SENDMSG = 0x0046C4C0
IAT_SETTIMER = 0x0046C490
IAT_KILLTIMER = 0x0046C520
IAT_REGOPEN = 0x0046C200
IAT_REGQUERY = 0x0046C1FC
IAT_REGCREATE = 0x0046C208
IAT_REGSET = 0x0046C1F8
IAT_REGCLOSE = 0x0046C20C
HKCU = 0x80000001
CB_ADDSTRING, CB_GETCURSEL, CB_RESETCONTENT, CB_SETCURSEL = 0x143, 0x147, 0x14B, 0x14E

SBTN_VA, OK_VA = 0x004689F4, 0x00469090
CODE_D = 0x400C00            # CODE: VA = file + this

SUBKEY = b"Software\\Triumph Studios\\Age of Wonders X\\General"
VALNAME = b"Hex Grid Thickness"
S_LABEL = b"Hex Grid Thickness (F5):"
ITEMS = (b"Extra", b"Default", b"Vanilla")
LBL_X, LBL_Y, LBL_W, LBL_H = 8, 76, 170, 16
CBO_X, CBO_Y, CBO_W, CBO_H = 184, 72, 185, 24

# (control path suffix, property, old, new) - TLoaderForm DFM, Settings tab
DFM_EDITS = [
    ("/SettingsSheet/SoundQualityGroup", "Top", 72, 104), ("/SettingsSheet/SoundQualityGroup", "Height", 109, 90),
    ("/SettingsSheet/DetailLevelGroup", "Top", 72, 104), ("/SettingsSheet/DetailLevelGroup", "Height", 109, 90),
    ("/SettingsSheet/SkipIntroBox", "Top", 188, 200), ("/SettingsSheet/UseDSound", "Top", 188, 200),
    ("/SettingsSheet/AllowResolutionSwitchesCB", "Top", 216, 226),
    ("/SettingsSheet/EmailSettingsBox", "Top", 240, 250), ("/SettingsSheet/EmailSettingsBox", "Height", 121, 109),
    ("/EmailSettingsBox/LocalEmailAddressEdit", "Top", 20, 18), ("/EmailSettingsBox/LocalEmailAddressLbl", "Top", 24, 22),
    ("/EmailSettingsBox/SMTPServerEdit", "Top", 52, 46), ("/EmailSettingsBox/SMTPServerLbl", "Top", 56, 50),
    ("/EmailSettingsBox/AttachmentDirectoryEdit", "Top", 84, 74),
    ("/EmailSettingsBox/AttachmentDirectoryLbl", "Top", 87, 78),
]

# ---- data layout (offsets from SEC_VA) ----
D_LABEL, D_ITEM0, D_ITEM1, D_ITEM2 = 0x00, 0x30, 0x50, 0x70
D_SUBKEY = 0x90              # 64 B block
D_VALNAME = 0xD0
D_GCOMBO = 0xF0
D_HKEY = 0xF4
D_TYPE = 0xF8
D_SIZE = 0xFC
D_BUF = 0x100                # 8 B
D_VAL = 0x108                # dword to write
D_TAIL_SHOW = 0x10C
D_TAIL_OK = 0x110
D_CODE = 0x120


def astr(s, block):
    b = struct.pack("<iI", -1, len(s)) + s + b"\0"
    assert len(b) <= block, s
    return b + b"\0" * (block - len(b))


SRC = """
hg_show:
    pushad
    mov  ebp, eax
    cmp  dword ptr [{g_combo:#x}], 0
    jne  _have
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {lbl_vmt:#x}
    call {lbl_ctor:#x}
    mov  ebx, eax
    mov  edx, dword ptr [ebp + {sheet:#x}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent:#x}]
    push {lbl_w}
    push {lbl_h}
    mov  ecx, {lbl_y}
    mov  edx, {lbl_x}
    mov  eax, ebx
    mov  edi, dword ptr [eax]
    call dword ptr [edi + {setbounds:#x}]
    mov  edx, {s_label:#x}
    mov  eax, ebx
    call {settext:#x}
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {cbo_vmt:#x}
    call {cbo_ctor:#x}
    mov  dword ptr [{g_combo:#x}], eax
    mov  ebx, eax
    mov  edx, 2
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setstyle:#x}]
    mov  eax, ebx
    mov  edx, dword ptr [ebp + {sheet:#x}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent:#x}]
    push {cbo_w}
    push {cbo_h}
    mov  ecx, {cbo_y}
    mov  edx, {cbo_x}
    mov  eax, ebx
    mov  edi, dword ptr [eax]
    call dword ptr [edi + {setbounds:#x}]
_have:
    mov  eax, dword ptr [{g_combo:#x}]
    call {gethandle:#x}
    mov  esi, eax
    push 0
    push 0
    push {cb_reset:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_item0:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_item1:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_item2:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    call _readreg
    push 0
    push eax
    push {cb_setsel:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {timerproc:#x}
    push 350
    push 0
    push 0
    call dword ptr [{settimer:#x}]
    popad
    jmp  dword ptr [{tail_show:#x}]

_timerproc:
    pushad
    mov  eax, dword ptr [esp + 0x2C]
    push eax
    push 0
    call dword ptr [{killtimer:#x}]
    mov  eax, dword ptr [{g_combo:#x}]
    test eax, eax
    jz   _tpout
    call {gethandle:#x}
    mov  esi, eax
    call _readreg
    push 0
    push eax
    push {cb_setsel:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
_tpout:
    popad
    ret  16

hg_ok:
    pushad
    cmp  dword ptr [{g_combo:#x}], 0
    je   _okout
    mov  eax, dword ptr [{g_combo:#x}]
    call {gethandle:#x}
    push 0
    push 0
    push {cb_getsel:#x}
    push eax
    call dword ptr [{sendmsg:#x}]
    cmp  eax, 2
    ja   _okout
    mov  ecx, 3
    sub  ecx, eax
    mov  dword ptr [{g_val:#x}], ecx
    push {g_type:#x}
    push {g_hkey:#x}
    push 0
    push 2
    push 0
    push 0
    push 0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regcreate:#x}]
    test eax, eax
    jnz  _okout
    push 4
    push {g_val:#x}
    push 4
    push 0
    push {s_valname:#x}
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regset:#x}]
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
_okout:
    popad
    jmp  dword ptr [{tail_ok:#x}]

_readreg:
    push {g_hkey:#x}
    push 1
    push 0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regopen:#x}]
    test eax, eax
    jnz  _rrdef
    mov  dword ptr [{g_size:#x}], 8
    mov  dword ptr [{g_type:#x}], 0
    push {g_size:#x}
    push {g_buf:#x}
    push {g_type:#x}
    push 0
    push {s_valname:#x}
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regquery:#x}]
    push eax
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
    pop  eax
    test eax, eax
    jnz  _rrdef
    cmp  dword ptr [{g_type:#x}], 4
    jne  _rrdef
    mov  eax, dword ptr [{g_buf:#x}]
    cmp  eax, 1
    jb   _rrdef
    cmp  eax, 3
    ja   _rrdef
    neg  eax
    add  eax, 3
    ret
_rrdef:
    mov  eax, 1
    ret
"""


def _asm_once(ks, timerproc_va):
    src = SRC.format(
        timerproc=timerproc_va, settimer=IAT_SETTIMER, killtimer=IAT_KILLTIMER,
        g_combo=SEC_VA + D_GCOMBO, g_hkey=SEC_VA + D_HKEY, g_type=SEC_VA + D_TYPE, g_size=SEC_VA + D_SIZE,
        g_buf=SEC_VA + D_BUF, g_val=SEC_VA + D_VAL,
        tail_show=SEC_VA + D_TAIL_SHOW, tail_ok=SEC_VA + D_TAIL_OK,
        s_label=SEC_VA + D_LABEL + 8, s_item0=SEC_VA + D_ITEM0 + 8, s_item1=SEC_VA + D_ITEM1 + 8,
        s_item2=SEC_VA + D_ITEM2 + 8, s_subkey=SEC_VA + D_SUBKEY + 8, s_valname=SEC_VA + D_VALNAME + 8,
        lbl_vmt=LBL_VMT, lbl_ctor=LBL_CTOR, cbo_vmt=CBO_VMT, cbo_ctor=CBO_CTOR,
        settext=SETTEXT, gethandle=GETHANDLE, sheet=OFF_SETTINGSSHEET,
        setparent=SLOT_SETPARENT, setbounds=SLOT_SETBOUNDS, setstyle=SLOT_SETSTYLE, sendmsg=IAT_SENDMSG,
        regopen=IAT_REGOPEN, regquery=IAT_REGQUERY, regcreate=IAT_REGCREATE, regset=IAT_REGSET,
        regclose=IAT_REGCLOSE, hkcu=HKCU,
        cb_add=CB_ADDSTRING, cb_getsel=CB_GETCURSEL, cb_reset=CB_RESETCONTENT, cb_setsel=CB_SETCURSEL,
        lbl_x=LBL_X, lbl_y=LBL_Y, lbl_w=LBL_W, lbl_h=LBL_H, cbo_x=CBO_X, cbo_y=CBO_Y, cbo_w=CBO_W, cbo_h=CBO_H)
    return bytes(ks.asm(src, SEC_VA + D_CODE)[0])


def build_code():
    """keystone hangs on ';' comments in this project -- source is comment-free.  Two-pass: _timerproc's ABSOLUTE
    address (the SetTimer callback) is found after assembly (right after the tail_show jmp) and re-assembled until it
    converges; hg_ok starts right after _timerproc's `ret 16`."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    tp_va = SEC_VA + D_CODE
    marker = b"\xFF\x25" + struct.pack("<I", SEC_VA + D_TAIL_SHOW)
    for _ in range(6):
        code = _asm_once(ks, tp_va)
        i = code.find(marker)
        assert i != -1, "tail_show jmp not found"
        real = SEC_VA + D_CODE + i + 6
        if real == tp_va:
            break
        tp_va = real
    else:
        raise AssertionError("timerproc address did not converge")
    j = code.find(b"\xC2\x10\x00", i)
    assert j != -1, "timerproc ret16 not found"
    return code, SEC_VA + D_CODE, SEC_VA + D_CODE + j + 3


def build_body(tail_show, tail_ok):
    code, va_show, va_ok = build_code()
    body = bytearray(SEC_SIZE)
    body[D_LABEL:D_LABEL + 0x30] = astr(S_LABEL, 0x30)
    for off, s in zip((D_ITEM0, D_ITEM1, D_ITEM2), ITEMS):
        body[off:off + 32] = astr(s, 32)
    body[D_SUBKEY:D_SUBKEY + 64] = astr(SUBKEY, 64)
    body[D_VALNAME:D_VALNAME + 32] = astr(VALNAME, 32)
    struct.pack_into("<I", body, D_TAIL_SHOW, tail_show)
    struct.pack_into("<I", body, D_TAIL_OK, tail_ok)
    assert D_CODE + len(code) <= SEC_SIZE, len(code)
    body[D_CODE:D_CODE + len(code)] = code
    return bytes(body), va_show, va_ok


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
                hdrsz=struct.unpack_from("<I", d, e + 24 + 84)[0],
                soi=struct.unpack_from("<I", d, e + 24 + 56)[0])


def align(x, a):
    return (x + a - 1) // a * a


def site_target(d, off):
    assert d[off] == 0xE9, "site @%#x is not a jmp (%02X)" % (off, d[off])
    return off + 5 + struct.unpack_from("<i", d, off + 1)[0]


def dfm_sites(d):
    """-> [(file offset of the value bytes, old bytes, new bytes, desc)] for DFM_EDITS (same encoding = same length)."""
    import pefile
    pe = pefile.PE(data=bytes(d))
    ent = None
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id == 10:
            for x in t.directory.entries:
                if str(x.name) == "TLOADERFORM":
                    ent = x.directory.entries[0].data.struct
    assert ent is not None
    base = pe.get_offset_from_rva(ent.OffsetToData)
    dfm = bytes(d[base:base + ent.Size])
    w = D.walk(dfm)
    out = []
    for suffix, prop, old, new in DFM_EDITS:
        hits = [p for p in w.props if p[0].endswith(suffix) and p[1] == prop]
        assert len(hits) == 1, (suffix, prop, len(hits))
        _, _, t, a, b, val = hits[0]
        vstart = a + 1 + len(prop)
        assert t in (D.I8, D.I16), (suffix, prop, t)
        fmt = "<b" if t == D.I8 else "<h"
        lo, hi = (-128, 127) if t == D.I8 else (-32768, 32767)
        assert lo <= new <= hi, (suffix, prop, new)
        ob = bytes([t]) + struct.pack(fmt, old)
        nb = bytes([t]) + struct.pack(fmt, new)
        cur = dfm[vstart:b]
        assert cur in (ob, nb), "%s.%s: unexpected value %r" % (suffix, prop, val)
        out.append((base + vstart, ob, nb, "%s.%s %d -> %d" % (suffix.split("/")[-1], prop, old, new)))
    return out


def main():
    a = sys.argv[1:]
    do_apply, revert = "--apply" in a, "--revert" in a
    exe = a[a.index("--exe") + 1] if "--exe" in a else game_file("AoWSetup.exe")
    bak = bak_path(exe, ".bak_hexgriddrop", create=do_apply)
    d = bytearray(open(exe, "rb").read())
    F = load_pe(d)
    sect = None
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == SEC_NAME[:5]:
            sect = s
    sb_off, ok_off = SBTN_VA - CODE_D, OK_VA - CODE_D
    sb_t = site_target(d, sb_off) + CODE_D
    ok_t = site_target(d, ok_off) + CODE_D
    mine = lambda va: SEC_VA <= va < SEC_VA + 0x1000
    dsites = dfm_sites(d)
    dnew = sum(bytes(d[o:o + len(ob)]) == nb for o, ob, nb, _ in dsites)
    print("target %s" % exe)
    print("  SettingsBtn site -> %08X  (%s)" % (sb_t, "OURS" if mine(sb_t) else "prev owner"))
    print("  SettingsOk  site -> %08X  (%s)" % (ok_t, "OURS" if mine(ok_t) else "prev owner"))
    print("  section .xhgd: %s;  Settings-tab DFM values: %d/%d moved" % (
        "present" if sect else "absent", dnew, len(dsites)))

    if revert:
        if not sect and not dnew:
            print("ALREADY VANILLA")
            return 0
        if sect:
            raw = sect[3]
            old_show = struct.unpack_from("<I", d, raw + D_TAIL_SHOW)[0]
            old_ok = struct.unpack_from("<I", d, raw + D_TAIL_OK)[0]
            if mine(sb_t):
                struct.pack_into("<i", d, sb_off + 1, old_show - (SBTN_VA + 5))
            if mine(ok_t):
                struct.pack_into("<i", d, ok_off + 1, old_ok - (OK_VA + 5))
            print("  sites -> %08X / %08X" % (old_show, old_ok))
        for o, ob, nb, desc in dsites:
            d[o:o + len(ob)] = ob
        if sect:
            if F["secs"][-1][0] == ".xhgd":
                del d[sect[3]:]
                d[sect[5]:sect[5] + 40] = bytes(40)
                struct.pack_into("<H", d, F["e"] + 6, F["n"] - 1)
                struct.pack_into("<I", d, F["opt"] + 56, SEC_VA - IMAGE_BASE)
                print("  removed .xhgd (last section)")
            else:
                d[sect[3]:sect[3] + sect[4]] = bytes(sect[4])
                print("  .xhgd is not the last section - body zeroed, header kept")
        try:
            open(exe, "wb").write(bytes(d))
        except PermissionError:
            print("LOCKED - close AoWSetup.exe and retry")
            return 1
        if os.path.exists(bak):
            print("  %s backup" % ("EQUALS" if open(exe, "rb").read() == open(bak, "rb").read() else "DIFFERS FROM"))
        print("REVERTED")
        return 0

    tails = (sb_t, ok_t)
    if sect and mine(sb_t):
        raw = sect[3]
        tails = (struct.unpack_from("<I", d, raw + D_TAIL_SHOW)[0], struct.unpack_from("<I", d, raw + D_TAIL_OK)[0])
    assert not mine(tails[0]) and not mine(tails[1]), "tail points into our own section"
    body, va_show, va_ok = build_body(*tails)
    print("  hg_show @%08X, hg_ok @%08X, tails %08X / %08X" % (va_show, va_ok, tails[0], tails[1]))

    if sect and mine(sb_t) and mine(ok_t) and bytes(d[sect[3]:sect[3] + SEC_SIZE]) == body and dnew == len(dsites):
        print("ALREADY APPLIED")
        return 0
    if not do_apply:
        print("dry run OK (--apply / --revert)")
        return 0

    if not os.path.isfile(bak):
        shutil.copy2(exe, bak)
        print("  backup -> %s" % bak)
    if sect:
        raw = sect[3]
        d[raw:raw + sect[4]] = bytes(sect[4])
        d[raw:raw + SEC_SIZE] = body
    else:
        assert F["tbl"] + (F["n"] + 1) * 40 <= F["hdrsz"], "no header room"
        assert F["soi"] == SEC_VA - IMAGE_BASE, "SizeOfImage %#x != %#x" % (F["soi"], SEC_VA - IMAGE_BASE)
        last = F["secs"][-1]
        assert len(d) == last[3] + last[4], "file has an overlay - refusing"
        newraw = align(len(d), F["falign"])
        d += bytes(newraw - len(d))
        rawsz = align(SEC_SIZE, F["falign"])
        d += body + bytes(rawsz - SEC_SIZE)
        b = F["tbl"] + F["n"] * 40
        struct.pack_into("<8sIIII", d, b, SEC_NAME, SEC_SIZE, SEC_VA - IMAGE_BASE, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<H", d, F["e"] + 6, F["n"] + 1)
        F2 = load_pe(d)
        soi = align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xhgd appended, SizeOfImage -> 0x%X" % soi)
    struct.pack_into("<i", d, sb_off + 1, va_show - (SBTN_VA + 5))
    struct.pack_into("<i", d, ok_off + 1, va_ok - (OK_VA + 5))
    for o, ob, nb, desc in dsites:
        d[o:o + len(nb)] = nb
    try:
        open(exe, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWSetup.exe and retry")
        return 1
    print("APPLIED - AoWSetup -> Settings: 'Hex Grid Thickness (F5):' dropdown (Extra / Default / Vanilla) under "
          "Language; OK saves it, the game reads it when it first draws the grid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
