#!/usr/bin/env python3
r"""AoWSetup -- "Campaigns" dropdown on the Developer tab.

Adds a TLabel "Campaigns:" + a real TComboBox (csDropDownList) to the
Developer tab with two entries:
    0  AoWx campaigns          (default)
    1  Original campaigns
The selection is loaded from / saved to the registry named value
    HKCU\Software\Triumph Studios\Age of Wonders X\General\"Vanilla Campaigns"
("1" = vanilla) -- exactly what the game-side patch build_campaign_switch.py
reads at startup. Saved on Settings OK; Cancel changes nothing (the combo is
re-loaded from the registry on every Settings open).

================================ MACHINERY =================================
Same runtime-VCL patterns as the devtab/mouse-tab patches ([[aowsetup-
internals]]): controls created lazily on first Settings open; new appended
RWX section `.xcmp` @VA 0x513000 (exe is fixed-base, absolutes safe).

HOOK CHAIN: the SettingsBtnClick (0x4689F4) and SettingsOk (0x469090) site
jmps -- currently pointing at the MOUSE-TAB caves (0x510000/0x510062), which
tail-jmp into the devtab caves -- are re-pointed to our caves, which do the
campaign work and tail-jmp to WHATEVER the sites pointed at before (read at
apply time, stored in data slots, jumped through indirectly -- so revert can
restore them and a mouse-tab re-apply can be chained again by re-running this
script). The Cancel site is NOT touched: nothing to undo on cancel.
⚠ CHAIN ORDER: devtab -> mouse_tab -> THIS. Re-running an earlier script
re-points the sites to itself -- re-run this one afterwards.

VERIFIED ADDRESSES (this session):
  TComboBox VMT 0x0042F594, ctor [VMT+0x24] = 0x004333C0 (classname-
    shortstring -> vmt-0x20 recipe).
  TComboBox RTTI: Style Set = **virtual [vmt+0x88]** (PropInfo 0xFE000088),
    value 2 = csDropDownList; Items = field +0x118 (unused -- see below).
  TLabel VMT 0x0042DD08 ctor 0x00431CEC; TControl.SetText 0x0041CA24 (edx =
    AnsiString CHARS ptr -- needs the -1/len header before it);
    SetParent slot [vmt+0x3C]; SetBounds slot [vmt+0x4C]
    (push W, push H, ecx=Top, edx=Left).
  TWinControl.GetHandle @0x00420714 (found by byte shape
    `53 8b d8 8b c3 e8 ? 8b 83 cc 00 00 00 5b c3`; creates the OS handle on
    demand, parents included; FHandle = +0xCC, matching VCL30's layout).
    With a real handle the combo is driven with plain combobox messages via
    user32 SendMessageA [0x0046C4C0] -- CB_ADDSTRING 0x143 / CB_GETCURSEL
    0x147 / CB_RESETCONTENT 0x14B / CB_SETCURSEL 0x14E -- which sidesteps the
    whole TComboBoxStrings/TStrings.Add VMT question. Items are RESET and
    re-added on every Settings open, so a VCL window re-creation can never
    leave the combo empty, and the selection always mirrors the registry.
    ⚠ The CB_SETCURSEL is issued TWICE: once synchronously and once via
    PostMessageA [0x0046C4F4]. User report (8/31): with only the synchronous
    set, the combo opened BLANK -- something later in the original
    SettingsBtnClick flow (which runs after the whole hook chain) clears the
    selection made during the click. The posted duplicate is processed on the
    next message-pump cycle, after that flow has finished, so the current
    setting is visible as soon as the tab appears. (Default = index 0 "AoWx":
    _readreg returns 0 on ANY failure -- missing value, missing key, or a
    value that is not "1".)
  advapi32 IAT: RegOpenKeyExA [0x0046C200], RegQueryValueExA [0x0046C1FC],
    RegCreateKeyExA [0x0046C208], RegSetValueExA [0x0046C1F8],
    RegCloseKey [0x0046C20C].
  DeveloperSheet = [form+0x224]; its DFM children end at y=232+17 (AutoSaveBox) and the devtab patch's runtime 'Cheat Mode' checkbox sits at (112,264,141,17) -- ⚠ v1 collided with it -- so the new row sits at y=296 (sheet client ~376x352).

Known cosmetic limitation (same as the Mouse tab): runtime-created controls
do not localise -- the label/items stay English in all languages.

Usage: dry-run default; --apply / --revert. Backup AoWSetup.exe.bak_campdrop.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_campdrop"

IMAGE_BASE = 0x400000
SEC_VA = 0x513000            # RVA 0x113000
SEC_SIZE = 0x600
SEC_NAME = b".xcmp\x00\x00\x00"

# verified constants
CBO_VMT, CBO_CTOR = 0x0042F594, 0x004333C0
LBL_VMT, LBL_CTOR = 0x0042DD08, 0x00431CEC
SETTEXT = 0x0041CA24
GETHANDLE = 0x00420714
SLOT_SETPARENT, SLOT_SETBOUNDS, SLOT_SETSTYLE = 0x3C, 0x4C, 0x88
OFF_DEVSHEET = 0x224
IAT_SENDMSG = 0x0046C4C0
IAT_POSTMSG = 0x0046C4F4
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
VALNAME = b"Vanilla Campaigns"
S_LABEL = b"Campaigns:"
S_ITEM0 = b"AoWx"
S_ITEM1 = b"Vanilla"

# ---- data layout (offsets from SEC_VA) ----
D_LABEL, D_ITEM0, D_ITEM1 = 0x00, 0x20, 0x40
D_SUBKEY = 0x60              # 64 B block
D_VALNAME = 0xA0
D_GCOMBO = 0xC0
D_HKEY = 0xC4
D_TYPE = 0xC8
D_SIZE = 0xCC
D_BUF = 0xD0                 # 8 B
D_VAL = 0xD8                 # 2 B ('0'/'1' + NUL)
D_TAIL_SHOW = 0xDC
D_TAIL_OK = 0xE0
D_CODE = 0xF0


def astr(s, block):
    b = struct.pack("<iI", -1, len(s)) + s + b"\0"
    assert len(b) <= block, s
    return b + b"\0" * (block - len(b))


SRC = """
cs_show:
    pushad
    mov  ebp, eax
    cmp  dword ptr [{g_combo:#x}], 0
    jne  _have
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {lbl_vmt:#x}
    call {lbl_ctor:#x}
    mov  ebx, eax
    mov  edx, dword ptr [ebp + {devsheet:#x}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent:#x}]
    push 88
    push 16
    mov  ecx, 300
    mov  edx, 16
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
    mov  edx, dword ptr [ebp + {devsheet:#x}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent:#x}]
    push 180
    push 21
    mov  ecx, 296
    mov  edx, 112
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
    call _readreg
    mov  edi, eax
    push 0
    push edi
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

cs_ok:
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
    cmp  eax, 0
    jl   _okout
    mov  cl, 0x30
    cmp  eax, 1
    jne  _w
    mov  cl, 0x31
_w:
    mov  byte ptr [{g_val:#x}], cl
    mov  byte ptr [{g_val1:#x}], 0
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
    push 2
    push {g_val:#x}
    push 1
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
    push {g_size:#x}
    push {g_buf:#x}
    push {g_type:#x}
    push 0
    push {s_valname:#x}
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regquery:#x}]
    mov  dword ptr [{g_type:#x}], eax
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
    cmp  dword ptr [{g_type:#x}], 0
    jne  _rrdef
    cmp  byte ptr [{g_buf:#x}], 0x31
    jne  _rrdef
    mov  eax, 1
    ret
_rrdef:
    xor  eax, eax
    ret
"""


def build_code():
    """keystone hangs on ';' comments in this project -- source is comment-free.

    Two-pass: _timerproc's ABSOLUTE address (the SetTimer callback) is found
    by locating it after assembly (right after the tail_show jmp) and
    re-assembling until it converges.
    """
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
    # cs_ok starts right after _timerproc's `ret 16` (C2 10 00)
    j = code.find(b"\xC2\x10\x00", i)
    assert j != -1, "timerproc ret16 not found"
    return code, SEC_VA + D_CODE, SEC_VA + D_CODE + j + 3


def _asm_once(ks, timerproc_va):
    src = SRC.format(
        timerproc=timerproc_va,
        settimer=IAT_SETTIMER, killtimer=IAT_KILLTIMER,
        g_combo=SEC_VA + D_GCOMBO, g_hkey=SEC_VA + D_HKEY,
        g_type=SEC_VA + D_TYPE, g_size=SEC_VA + D_SIZE,
        g_buf=SEC_VA + D_BUF, g_val=SEC_VA + D_VAL, g_val1=SEC_VA + D_VAL + 1,
        tail_show=SEC_VA + D_TAIL_SHOW, tail_ok=SEC_VA + D_TAIL_OK,
        s_label=SEC_VA + D_LABEL + 8, s_item0=SEC_VA + D_ITEM0 + 8,
        s_item1=SEC_VA + D_ITEM1 + 8, s_subkey=SEC_VA + D_SUBKEY + 8,
        s_valname=SEC_VA + D_VALNAME + 8,
        lbl_vmt=LBL_VMT, lbl_ctor=LBL_CTOR, cbo_vmt=CBO_VMT, cbo_ctor=CBO_CTOR,
        settext=SETTEXT, gethandle=GETHANDLE, devsheet=OFF_DEVSHEET,
        setparent=SLOT_SETPARENT, setbounds=SLOT_SETBOUNDS,
        setstyle=SLOT_SETSTYLE, sendmsg=IAT_SENDMSG, postmsg=IAT_POSTMSG,
        regopen=IAT_REGOPEN, regquery=IAT_REGQUERY, regcreate=IAT_REGCREATE,
        regset=IAT_REGSET, regclose=IAT_REGCLOSE, hkcu=HKCU,
        cb_add=CB_ADDSTRING, cb_getsel=CB_GETCURSEL,
        cb_reset=CB_RESETCONTENT, cb_setsel=CB_SETCURSEL)
    return bytes(ks.asm(src, SEC_VA + D_CODE)[0])


def build_body(tail_show, tail_ok):
    code, va_show, va_ok = build_code()
    body = bytearray(SEC_SIZE)
    body[D_LABEL:D_LABEL + 32] = astr(S_LABEL, 32)
    body[D_ITEM0:D_ITEM0 + 32] = astr(S_ITEM0, 32)
    body[D_ITEM1:D_ITEM1 + 32] = astr(S_ITEM1, 32)
    body[D_SUBKEY:D_SUBKEY + 64] = astr(SUBKEY, 64)
    body[D_VALNAME:D_VALNAME + 32] = astr(VALNAME, 32)
    struct.pack_into("<I", body, D_TAIL_SHOW, tail_show)
    struct.pack_into("<I", body, D_TAIL_OK, tail_ok)
    body[D_CODE:D_CODE + len(code)] = code
    assert D_CODE + len(code) <= SEC_SIZE, len(code)
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
                hdrsz=struct.unpack_from("<I", d, e + 24 + 84)[0])


def align(x, a):
    return (x + a - 1) // a * a


def site_target(d, off):
    assert d[off] == 0xE9, "site @%#x is not a jmp (%02X)" % (off, d[off])
    return off + 5 + struct.unpack_from("<i", d, off + 1)[0]


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(EXE, "rb").read())
    F = load_pe(d)
    sect = None
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == SEC_NAME[:5]:
            sect = s

    sb_off, ok_off = SBTN_VA - CODE_D, OK_VA - CODE_D
    sb_t = site_target(d, sb_off) + CODE_D
    ok_t = site_target(d, ok_off) + CODE_D
    mine = lambda va: SEC_VA <= va < SEC_VA + 0x1000
    print("  SettingsBtn site -> %08X  (%s)" % (sb_t, "OURS" if mine(sb_t) else "prev owner"))
    print("  SettingsOk  site -> %08X  (%s)" % (ok_t, "OURS" if mine(ok_t) else "prev owner"))
    print("  section .xcmp: %s" % ("present" if sect else "will be appended"))

    if revert:
        if not sect or not (mine(sb_t) or mine(ok_t)):
            print("nothing of ours is hooked; nothing to do")
            return 0
        raw = sect[3]
        old_show = struct.unpack_from("<I", d, raw + D_TAIL_SHOW)[0]
        old_ok = struct.unpack_from("<I", d, raw + D_TAIL_OK)[0]
        if mine(sb_t):
            struct.pack_into("<i", d, sb_off + 1, old_show - (SBTN_VA + 5))
        if mine(ok_t):
            struct.pack_into("<i", d, ok_off + 1, old_ok - (OK_VA + 5))
        d[raw:raw + sect[4]] = bytes(sect[4])
        open(EXE, "wb").write(bytes(d))
        print("reverted: sites -> %08X / %08X, .xcmp body zeroed (header kept)"
              % (old_show, old_ok))
        return 0

    tails = (sb_t, ok_t)
    if mine(sb_t) and sect:
        # already ours: keep the stored tails (do NOT read our own cave as tail)
        raw = sect[3]
        tails = (struct.unpack_from("<I", d, raw + D_TAIL_SHOW)[0],
                 struct.unpack_from("<I", d, raw + D_TAIL_OK)[0])
    body, va_show, va_ok = build_body(*tails)
    print("  cs_show @%08X, cs_ok @%08X, tails %08X / %08X"
          % (va_show, va_ok, tails[0], tails[1]))

    if sect and mine(sb_t) and mine(ok_t) and \
            bytes(d[sect[3]:sect[3] + SEC_SIZE]) == body:
        print("already applied")
        return 0
    if not do_apply:
        print("dry run (--apply / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))

    if sect:
        raw = sect[3]
        d[raw:raw + sect[4]] = bytes(sect[4])
        d[raw:raw + SEC_SIZE] = body
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
        soi = align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xcmp appended, SizeOfImage -> 0x%X" % soi)
    struct.pack_into("<i", d, sb_off + 1, va_show - (SBTN_VA + 5))
    struct.pack_into("<i", d, ok_off + 1, va_ok - (OK_VA + 5))
    try:
        open(EXE, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWSetup.exe and retry")
        return 1
    print("APPLIED - open AoWSetup -> Settings -> Developer tab: a "
          "'Campaigns:' dropdown (AoWx / Vanilla) sits "
          "below the Cheat Mode checkbox. Pick one, OK, then start the game - it "
          "reads the same registry value at startup. Cancel discards the "
          "choice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
