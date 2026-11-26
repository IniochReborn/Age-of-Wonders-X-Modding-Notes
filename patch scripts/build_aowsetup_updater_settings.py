#!/usr/bin/env python3
r"""AoWSetup -- auto-updater settings on the Developer tab (2026-10-20, auto-updater step 3).

Two dropdown rows (runtime TLabel + TComboBox csDropDownList, styled like the Developer tab's "Campaigns:" row):
    "Auto-Updates:"       Automatic (default) / Ask before installing / Off     -> Mode      = Auto | Ask | Off
    "Check for Updates:"  Scheduled (default) / Only when the game runs         -> Frequency = Scheduled | GameOnly
stored as REG_SZ under HKCU\Software\Triumph Studios\Age of Wonders X\Updater -- exactly the names/values
AoWxUpdater.exe reads (Program.cs Mode()/Frequency(): case-insensitive "Ask"/"Off" else Auto; "GameOnly" else
Scheduled).  Missing / non-REG_SZ / unknown values show the defaults.  Re-read on every Settings open, written on OK
(only values whose selection changed), Cancel discards (the combos are reloaded from the registry next time).
When OK changed either value: CreateProcessA("<AoWSetup dir>\AoWxUpdater.exe", "\"...\" --register",
CREATE_NO_WINDOW, SW_HIDE) -- non-blocking, handles closed at once; CreateProcessA is resolved with
GetModuleHandleA("kernel32.dll") + GetProcAddress (not in the IAT); if the exe is missing CreateProcessA just fails ->
silently skipped.  Captions are runtime literals -> English in every language (like the other added rows).

LAYOUT (Developer tab, sheet client ~376x352): DFM StartupDirectoryEdit ends y 69, checkboxes DebugMode 128 /
LogTokenEvents 160 / AutoDebugSave 192 / AutoSaveBox 232, devtab's runtime Cheat Mode 264, campaign row 296.  The two
new rows go right under the Startup Directory edit; two DFM checkboxes move down / tighten (in-place I16 edits):
    "Auto-Updates:"       label (16, 88, 106x16), combo (128, 84, 180x21)
    "Check for Updates:"  label (16, 116, 106x16), combo (128, 112, 180x21)
    DebugMode      Top 128 -> 144      LogTokenEvents Top 160 -> 166      AutoSaveBox Top 232 -> 222
    (AutoDebugSave 192, Cheat Mode 264 and the Campaigns row 296 stay where they are.)

MACHINERY: AoWSetup's section-header table is FULL (CODE raw starts at 0x400), so the LAST section .xftx
(build_aowsetup_flavor_checkbox.py, VA 0x515000, 0x400) is GROWN: VirtualSize/raw 0x400 -> 0x2000, our zone =
VA 0x516000..0x517000 (outside the flavor script's own 0x515000..0x516000 "mine" range), SizeOfImage 0x116000 ->
0x117000.  The original VS/raw sizes are stored in the zone header for an exact revert.
HOOK CHAIN: SettingsBtnClick 0x4689F4 / SettingsOk 0x469090 site jmps (now -> flavor checkbox caves 0x5150C0 /
0x515128) are re-pointed to our caves, which tail-jmp through stored slots to the previous targets.
CHAIN ORDER: devtab -> mouse_tab -> campaign_dropdown -> hexgrid_dropdown -> flavor_checkbox -> THIS.
  !! LIFO: revert THIS first.  Reverting the flavor checkbox while THIS is applied would delete .xftx (it is the last
  section) including this zone while the sites still point here -> AoWSetup would crash on Settings.  Re-running an
  earlier script's --apply re-points the sites to itself -> re-run this one afterwards.

Usage: py -3.10 build_aowsetup_updater_settings.py [--apply | --revert] [--exe PATH]   (dry-run default)
Backup: backup\AoWSetup.exe.bak_updsettings.  --revert restores the site jmps, the DFM tops and the .xftx size ->
byte-identical to the pre-apply file.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = HERE if os.path.isfile(os.path.join(HERE, "bakpath.py")) else \
    r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts"
sys.path.insert(0, PATCH)
from bakpath import bak_path, game_file
import dfm_edit as D
import build_aowsetup_hexgrid_dropdown as HG

IMAGE_BASE = 0x400000
HOST_NAME = b".xftx"
HOST_VA = 0x515000
HOST_NEW = 0x2000            # new VirtualSize == raw size of .xftx
ZONE_VA = 0x516000           # = HOST_VA + 0x1000
ZONE_SIZE = 0x1000
MAGIC = b"UPS1"

CBO_VMT, CBO_CTOR = HG.CBO_VMT, HG.CBO_CTOR
LBL_VMT, LBL_CTOR = HG.LBL_VMT, HG.LBL_CTOR
SETTEXT, GETHANDLE = HG.SETTEXT, HG.GETHANDLE
SLOT_SETPARENT, SLOT_SETBOUNDS, SLOT_SETSTYLE = 0x3C, 0x4C, 0x88
OFF_DEVSHEET = 0x224
IAT_SENDMSG, IAT_SETTIMER, IAT_KILLTIMER = HG.IAT_SENDMSG, HG.IAT_SETTIMER, HG.IAT_KILLTIMER
IAT_REGOPEN, IAT_REGQUERY, IAT_REGCREATE = HG.IAT_REGOPEN, HG.IAT_REGQUERY, HG.IAT_REGCREATE
IAT_REGSET, IAT_REGCLOSE = HG.IAT_REGSET, HG.IAT_REGCLOSE
IAT_LSTRLEN, IAT_LSTRCPY = 0x0046C144, 0x0046C148
IAT_GETMODFN = 0x0046C158
IAT_GETMODH = 0x0046C1EC
IAT_GETPROC = 0x0046C2A0
IAT_CLOSEH = 0x0046C198
HKCU = 0x80000001
CB_ADDSTRING, CB_GETCURSEL, CB_RESETCONTENT, CB_SETCURSEL = 0x143, 0x147, 0x14B, 0x14E
SBTN_VA, OK_VA, CODE_D = HG.SBTN_VA, HG.OK_VA, HG.CODE_D

SUBKEY = b"Software\\Triumph Studios\\Age of Wonders X\\Updater"
LBL1, LBL2 = b"Auto-Updates:", b"Check for Updates:"
MITEMS = (b"Automatic", b"Ask before installing", b"Off")
FITEMS = (b"Scheduled", b"Only when the game runs")
MVALS = (b"Auto", b"Ask", b"Off")
FVALS = (b"Scheduled", b"GameOnly")
ROW1, ROW2 = 84, 112
LBL_X, LBL_W, LBL_H = 16, 106, 16
CBO_X, CBO_W, CBO_H = 128, 180, 21

DFM_EDITS = [("/DeveloperSheet/DebugMode", "Top", 128, 144),
             ("/DeveloperSheet/LogTokenEvents", "Top", 160, 166),
             ("/DeveloperSheet/AutoSaveBox", "Top", 232, 222)]

# ---- zone layout (offsets from ZONE_VA) ----
Z_MAGIC = 0x00               # 'UPS1'
Z_OLDVS = 0x04
Z_OLDRAW = 0x08
Z_TAIL_SHOW = 0x0C
Z_TAIL_OK = 0x10
Z_LBL1, Z_LBL2 = 0x20, 0x40                  # Delphi AnsiStrings (chars at +8)
Z_M0, Z_M1, Z_M2 = 0x70, 0x90, 0xC0
Z_F0, Z_F1 = 0xE0, 0x100
Z_SUBKEY = 0x130                             # C strings from here on
Z_VMODE, Z_VFREQ = 0x170, 0x178
Z_SAUTO, Z_SASK, Z_SOFF, Z_SSCHED, Z_SGAME = 0x188, 0x190, 0x198, 0x1A0, 0x1B0
Z_K32, Z_CREATEP, Z_EXENAME, Z_SUFFIX = 0x1C0, 0x1D0, 0x1E0, 0x1F0
Z_G = 0x200                                  # globals
G_C1, G_C2, G_HKEY, G_TYPE, G_SIZE, G_M0, G_F0, G_CHG = (Z_G + 4 * i for i in range(8))
G_TMP = Z_G + 0x30
G_BUF = Z_G + 0x20                           # 16 B
Z_PATH = 0x240                               # 0x110 B
Z_CMD = 0x360                                # 0x130 B
Z_SI = 0x4A0                                 # STARTUPINFOA 0x44
Z_PI = 0x4F0                                 # PROCESS_INFORMATION 0x10
Z_MTAB = 0x500                               # value-string pointer tables: Mode Auto/Ask/Off, Frequency
Z_FTAB = 0x50C                               #   Scheduled/GameOnly (indexed by the combo selection)
Z_CODE = 0x520


def cstr(s, block):
    assert len(s) + 1 <= block, s
    return s + b"\0" * (block - len(s))


SRC = """
up_show:
    pushad
    mov  ebp, eax
    cmp  dword ptr [{g_c1:#x}], 0
    jne  _have
    mov  esi, {s_lbl1:#x}
    mov  edi, {row1}
    call _mklabel
    mov  edi, {row1}
    call _mkcombo
    mov  dword ptr [{g_c1:#x}], eax
    mov  esi, {s_lbl2:#x}
    mov  edi, {row2}
    call _mklabel
    mov  edi, {row2}
    call _mkcombo
    mov  dword ptr [{g_c2:#x}], eax
_have:
    mov  eax, dword ptr [{g_c1:#x}]
    call {gethandle:#x}
    mov  esi, eax
    push 0
    push 0
    push {cb_reset:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_m0:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_m1:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_m2:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    call _readmode
    mov  dword ptr [{g_m0:#x}], eax
    push 0
    push eax
    push {cb_setsel:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    mov  eax, dword ptr [{g_c2:#x}]
    call {gethandle:#x}
    mov  esi, eax
    push 0
    push 0
    push {cb_reset:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_f0:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    push {s_f1:#x}
    push 0
    push {cb_add:#x}
    push esi
    call dword ptr [{sendmsg:#x}]
    call _readfreq
    mov  dword ptr [{g_f0:#x}], eax
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
    mov  eax, dword ptr [{g_c1:#x}]
    test eax, eax
    jz   _tpout
    call {gethandle:#x}
    push 0
    push dword ptr [{g_m0:#x}]
    push {cb_setsel:#x}
    push eax
    call dword ptr [{sendmsg:#x}]
    mov  eax, dword ptr [{g_c2:#x}]
    test eax, eax
    jz   _tpout
    call {gethandle:#x}
    push 0
    push dword ptr [{g_f0:#x}]
    push {cb_setsel:#x}
    push eax
    call dword ptr [{sendmsg:#x}]
_tpout:
    popad
    ret  16

up_ok:
    pushad
    mov  dword ptr [{g_chg:#x}], 0
    mov  eax, dword ptr [{g_c1:#x}]
    test eax, eax
    jz   _okout
    call {gethandle:#x}
    push 0
    push 0
    push {cb_getsel:#x}
    push eax
    call dword ptr [{sendmsg:#x}]
    cmp  eax, 2
    ja   _okfreq
    cmp  eax, dword ptr [{g_m0:#x}]
    je   _okfreq
    mov  dword ptr [{g_m0:#x}], eax
    mov  edx, dword ptr [{mvals:#x} + eax*4]
    mov  ecx, {v_mode:#x}
    call _writesz
    mov  dword ptr [{g_chg:#x}], 1
_okfreq:
    mov  eax, dword ptr [{g_c2:#x}]
    test eax, eax
    jz   _okreg
    call {gethandle:#x}
    push 0
    push 0
    push {cb_getsel:#x}
    push eax
    call dword ptr [{sendmsg:#x}]
    cmp  eax, 1
    ja   _okreg
    cmp  eax, dword ptr [{g_f0:#x}]
    je   _okreg
    mov  dword ptr [{g_f0:#x}], eax
    mov  edx, dword ptr [{fvals:#x} + eax*4]
    mov  ecx, {v_freq:#x}
    call _writesz
    mov  dword ptr [{g_chg:#x}], 1
_okreg:
    cmp  dword ptr [{g_chg:#x}], 0
    je   _okout
    call _launch
_okout:
    popad
    jmp  dword ptr [{tail_ok:#x}]

_mklabel:
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
    mov  eax, dword ptr [ebx]
    mov  eax, dword ptr [eax + {setbounds:#x}]
    mov  dword ptr [{g_tmp:#x}], eax
    lea  ecx, [edi + 4]
    mov  edx, {lbl_x}
    mov  eax, ebx
    call dword ptr [{g_tmp:#x}]
    mov  edx, esi
    mov  eax, ebx
    call {settext:#x}
    ret

_mkcombo:
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {cbo_vmt:#x}
    call {cbo_ctor:#x}
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
    mov  eax, dword ptr [ebx]
    mov  eax, dword ptr [eax + {setbounds:#x}]
    mov  dword ptr [{g_tmp:#x}], eax
    mov  ecx, edi
    mov  edx, {cbo_x}
    mov  eax, ebx
    call dword ptr [{g_tmp:#x}]
    mov  eax, ebx
    ret

_readmode:
    push ebx
    push esi
    push edi
    mov  edx, {v_mode:#x}
    call _readsz
    test eax, eax
    jnz  _rm0
    mov  edi, {s_ask:#x}
    call _stri
    test eax, eax
    jnz  _rm1
    mov  edi, {s_off:#x}
    call _stri
    test eax, eax
    jnz  _rm2
_rm0:
    xor  eax, eax
    jmp  _rmx
_rm1:
    mov  eax, 1
    jmp  _rmx
_rm2:
    mov  eax, 2
_rmx:
    pop  edi
    pop  esi
    pop  ebx
    ret

_readfreq:
    push ebx
    push esi
    push edi
    mov  edx, {v_freq:#x}
    call _readsz
    test eax, eax
    jnz  _rf0
    mov  edi, {s_game:#x}
    call _stri
    test eax, eax
    jz   _rf0
    mov  eax, 1
    jmp  _rfx
_rf0:
    xor  eax, eax
_rfx:
    pop  edi
    pop  esi
    pop  ebx
    ret

_readsz:
    push edx
    mov  dword ptr [{g_buf:#x}], 0
    mov  dword ptr [{g_buf:#x} + 4], 0
    mov  dword ptr [{g_buf:#x} + 8], 0
    mov  dword ptr [{g_buf:#x} + 12], 0
    push {g_hkey:#x}
    push 1
    push 0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regopen:#x}]
    pop  edx
    test eax, eax
    jnz  _rsfail
    mov  dword ptr [{g_size:#x}], 15
    mov  dword ptr [{g_type:#x}], 0
    push {g_size:#x}
    push {g_buf:#x}
    push {g_type:#x}
    push 0
    push edx
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regquery:#x}]
    push eax
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
    pop  eax
    test eax, eax
    jnz  _rsfail
    cmp  dword ptr [{g_type:#x}], 1
    jne  _rsfail
    mov  byte ptr [{g_buf:#x} + 15], 0
    xor  eax, eax
    ret
_rsfail:
    mov  eax, 1
    ret

_stri:
    mov  esi, {g_buf:#x}
_stl:
    mov  al, byte ptr [esi]
    mov  bl, byte ptr [edi]
    cmp  al, 0x41
    jb   _st1
    cmp  al, 0x5A
    ja   _st1
    or   al, 0x20
_st1:
    cmp  bl, 0x41
    jb   _st2
    cmp  bl, 0x5A
    ja   _st2
    or   bl, 0x20
_st2:
    cmp  al, bl
    jne  _stno
    test al, al
    jz   _styes
    inc  esi
    inc  edi
    jmp  _stl
_styes:
    mov  eax, 1
    ret
_stno:
    xor  eax, eax
    ret

_writesz:
    push edx
    push ecx
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
    pop  ecx
    pop  edx
    test eax, eax
    jnz  _wsout
    push edx
    push ecx
    push edx
    call dword ptr [{lstrlen:#x}]
    pop  ecx
    pop  edx
    inc  eax
    push eax
    push edx
    push 1
    push 0
    push ecx
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regset:#x}]
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
_wsout:
    ret

_launch:
    push 0x104
    push {s_path:#x}
    push 0
    call dword ptr [{getmodfn:#x}]
    test eax, eax
    jz   _lout
    cmp  eax, 0xF0
    ja   _lout
    mov  esi, {s_path:#x}
    mov  edi, esi
_lscan:
    mov  al, byte ptr [esi]
    test al, al
    jz   _lscanned
    inc  esi
    cmp  al, 0x5C
    jne  _lscan
    mov  edi, esi
    jmp  _lscan
_lscanned:
    push {s_exe:#x}
    push edi
    call dword ptr [{lstrcpy:#x}]
    mov  byte ptr [{s_cmd:#x}], 0x22
    push {s_path:#x}
    push {s_cmd1:#x}
    call dword ptr [{lstrcpy:#x}]
    push {s_cmd:#x}
    call dword ptr [{lstrlen:#x}]
    add  eax, {s_cmd:#x}
    push {s_suffix:#x}
    push eax
    call dword ptr [{lstrcpy:#x}]
    push {s_k32:#x}
    call dword ptr [{getmodh:#x}]
    test eax, eax
    jz   _lout
    push {s_createp:#x}
    push eax
    call dword ptr [{getproc:#x}]
    test eax, eax
    jz   _lout
    mov  ebx, eax
    mov  edi, {si_:#x}
    mov  ecx, 0x54
    xor  eax, eax
_lz:
    mov  byte ptr [edi], al
    inc  edi
    dec  ecx
    jnz  _lz
    mov  dword ptr [{si_:#x}], 0x44
    mov  dword ptr [{si_:#x} + 0x2C], 1
    push {pi_:#x}
    push {si_:#x}
    push 0
    push 0
    push 0x08000000
    push 0
    push 0
    push 0
    push {s_cmd:#x}
    push {s_path:#x}
    call ebx
    test eax, eax
    jz   _lout
    push dword ptr [{pi_:#x}]
    call dword ptr [{closeh:#x}]
    push dword ptr [{pi_:#x} + 4]
    call dword ptr [{closeh:#x}]
_lout:
    ret
"""


def _fmt(timerproc_va):
    Z = ZONE_VA
    return dict(
        timerproc=timerproc_va, settimer=IAT_SETTIMER, killtimer=IAT_KILLTIMER,
        g_c1=Z + G_C1, g_c2=Z + G_C2, g_hkey=Z + G_HKEY, g_type=Z + G_TYPE, g_size=Z + G_SIZE,
        g_m0=Z + G_M0, g_f0=Z + G_F0, g_chg=Z + G_CHG, g_buf=Z + G_BUF,
        tail_show=Z + Z_TAIL_SHOW, tail_ok=Z + Z_TAIL_OK,
        s_lbl1=Z + Z_LBL1 + 8, s_lbl2=Z + Z_LBL2 + 8,
        s_m0=Z + Z_M0 + 8, s_m1=Z + Z_M1 + 8, s_m2=Z + Z_M2 + 8, s_f0=Z + Z_F0 + 8, s_f1=Z + Z_F1 + 8,
        s_subkey=Z + Z_SUBKEY, v_mode=Z + Z_VMODE, v_freq=Z + Z_VFREQ,
        s_ask=Z + Z_SASK, s_off=Z + Z_SOFF, s_game=Z + Z_SGAME,
        mvals=Z + Z_MTAB, fvals=Z + Z_FTAB, g_tmp=Z + G_TMP, settext=SETTEXT,
        s_k32=Z + Z_K32, s_createp=Z + Z_CREATEP, s_exe=Z + Z_EXENAME, s_suffix=Z + Z_SUFFIX,
        s_path=Z + Z_PATH, s_cmd=Z + Z_CMD, s_cmd1=Z + Z_CMD + 1, si_=Z + Z_SI, pi_=Z + Z_PI,
        lbl_vmt=LBL_VMT, lbl_ctor=LBL_CTOR, cbo_vmt=CBO_VMT, cbo_ctor=CBO_CTOR,
        gethandle=GETHANDLE, sheet=OFF_DEVSHEET,
        setparent=SLOT_SETPARENT, setbounds=SLOT_SETBOUNDS, setstyle=SLOT_SETSTYLE, sendmsg=IAT_SENDMSG,
        regopen=IAT_REGOPEN, regquery=IAT_REGQUERY, regcreate=IAT_REGCREATE, regset=IAT_REGSET,
        regclose=IAT_REGCLOSE, hkcu=HKCU, lstrlen=IAT_LSTRLEN, lstrcpy=IAT_LSTRCPY, getmodfn=IAT_GETMODFN,
        getmodh=IAT_GETMODH, getproc=IAT_GETPROC, closeh=IAT_CLOSEH,
        cb_add=CB_ADDSTRING, cb_getsel=CB_GETCURSEL, cb_reset=CB_RESETCONTENT, cb_setsel=CB_SETCURSEL,
        row1=ROW1, row2=ROW2, lbl_x=LBL_X, lbl_w=LBL_W, lbl_h=LBL_H, cbo_x=CBO_X, cbo_w=CBO_W, cbo_h=CBO_H)


def build_code():
    """keystone hangs on ';' comments in this project -- source is comment-free.  _timerproc's absolute address (the
    SetTimer callback) is found after assembly (right after the tail_show jmp) and re-assembled until it converges;
    up_ok starts right after _timerproc's `ret 16`."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    base = ZONE_VA + Z_CODE
    tp = base
    marker = b"\xFF\x25" + struct.pack("<I", ZONE_VA + Z_TAIL_SHOW)
    for _ in range(8):
        code = bytes(ks.asm(SRC.format(**_fmt(tp)), base)[0])
        i = code.find(marker)
        assert i != -1, "tail_show jmp not found"
        real = base + i + 6
        if real == tp:
            break
        tp = real
    else:
        raise AssertionError("timerproc did not converge")
    j = code.find(b"\xC2\x10\x00", i)
    assert j != -1
    return code, base, base + j + 3, tp


def build_zone(old_vs, old_raw, tail_show, tail_ok):
    code, va_show, va_ok, va_tp = build_code()
    z = bytearray(ZONE_SIZE)
    z[Z_MAGIC:Z_MAGIC + 4] = MAGIC
    struct.pack_into("<IIII", z, Z_OLDVS, old_vs, old_raw, tail_show, tail_ok)
    z[Z_LBL1:Z_LBL1 + 0x20] = HG.astr(LBL1, 0x20)
    z[Z_LBL2:Z_LBL2 + 0x30] = HG.astr(LBL2, 0x30)
    for off, s, blk in ((Z_M0, MITEMS[0], 0x20), (Z_M1, MITEMS[1], 0x30), (Z_M2, MITEMS[2], 0x20),
                        (Z_F0, FITEMS[0], 0x20), (Z_F1, FITEMS[1], 0x30)):
        z[off:off + blk] = HG.astr(s, blk)
    for i, off in enumerate((Z_SAUTO, Z_SASK, Z_SOFF)):
        struct.pack_into("<I", z, Z_MTAB + 4 * i, ZONE_VA + off)
    for i, off in enumerate((Z_SSCHED, Z_SGAME)):
        struct.pack_into("<I", z, Z_FTAB + 4 * i, ZONE_VA + off)
    z[Z_SUBKEY:Z_SUBKEY + 0x40] = cstr(SUBKEY, 0x40)
    z[Z_VMODE:Z_VMODE + 8] = cstr(b"Mode", 8)
    z[Z_VFREQ:Z_VFREQ + 0x10] = cstr(b"Frequency", 0x10)
    z[Z_SAUTO:Z_SAUTO + 8] = cstr(MVALS[0], 8)
    z[Z_SASK:Z_SASK + 8] = cstr(MVALS[1], 8)
    z[Z_SOFF:Z_SOFF + 8] = cstr(MVALS[2], 8)
    z[Z_SSCHED:Z_SSCHED + 0x10] = cstr(FVALS[0], 0x10)
    z[Z_SGAME:Z_SGAME + 0x10] = cstr(FVALS[1], 0x10)
    z[Z_K32:Z_K32 + 0x10] = cstr(b"kernel32.dll", 0x10)
    z[Z_CREATEP:Z_CREATEP + 0x10] = cstr(b"CreateProcessA", 0x10)
    z[Z_EXENAME:Z_EXENAME + 0x10] = cstr(b"AoWxUpdater.exe", 0x10)
    z[Z_SUFFIX:Z_SUFFIX + 0x10] = cstr(b"\" --register", 0x10)
    assert Z_FTAB + 8 <= Z_CODE and Z_CODE + len(code) <= ZONE_SIZE, len(code)
    z[Z_CODE:Z_CODE + len(code)] = code
    return bytes(z), va_show, va_ok, va_tp


def dfm_sites(d):
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
        ob, nb = bytes([t]) + struct.pack(fmt, old), bytes([t]) + struct.pack(fmt, new)
        assert dfm[vstart:b] in (ob, nb), "%s.%s: unexpected value %r" % (suffix, prop, val)
        out.append((base + vstart, ob, nb))
    return out


def host(d, F):
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == HOST_NAME:
            return s
    return None


def main():
    a = sys.argv[1:]
    do_apply, revert = "--apply" in a, "--revert" in a
    exe = a[a.index("--exe") + 1] if "--exe" in a else game_file("AoWSetup.exe")
    bak = bak_path(exe, ".bak_updsettings", create=do_apply)
    d = bytearray(open(exe, "rb").read())
    F = HG.load_pe(d)
    hs = host(d, F)
    assert hs is not None and hs[1] + IMAGE_BASE == HOST_VA, "flavor checkbox section .xftx not found - apply " \
        "build_aowsetup_flavor_checkbox.py first"
    is_last = F["secs"][-1][5] == hs[5]
    sb_off, ok_off = SBTN_VA - CODE_D, OK_VA - CODE_D
    sb_t = HG.site_target(d, sb_off) + CODE_D
    ok_t = HG.site_target(d, ok_off) + CODE_D
    mine = lambda va: ZONE_VA <= va < ZONE_VA + ZONE_SIZE
    grown = hs[2] >= HOST_NEW and hs[4] >= HOST_NEW
    zraw = hs[3] + (ZONE_VA - HOST_VA)
    present = grown and bytes(d[zraw:zraw + 4]) == MAGIC
    dsites = dfm_sites(d)
    dnew = sum(bytes(d[o:o + len(ob)]) == nb for o, ob, nb in dsites)
    print("target %s" % exe)
    print("  .xftx VS %#x raw %#x (last section: %s); zone %s" % (hs[2], hs[4], is_last,
                                                                    "PRESENT" if present else "absent"))
    print("  SettingsBtn site -> %08X (%s);  SettingsOk site -> %08X (%s)" % (
        sb_t, "OURS" if mine(sb_t) else "prev owner", ok_t, "OURS" if mine(ok_t) else "prev owner"))
    print("  Developer-tab DFM tops moved: %d/%d" % (dnew, len(dsites)))

    audio = lambda va: 0x517000 <= va < 0x518000         # build_aowsetup_audio_tab.py zone (chained in front of us)
    if audio(sb_t) or audio(ok_t):
        print("  audio tab (build_aowsetup_audio_tab.py) is chained in front of this script -> nothing to do; to change "
              "this script revert the audio tab first (LIFO), apply, then re-apply the audio tab")
        return 0
    if revert:
        if not present and not dnew:
            print("ALREADY VANILLA")
            return 0
        if present:
            old_vs, old_raw, old_show, old_ok = struct.unpack_from("<IIII", d, zraw + Z_OLDVS)
            if mine(sb_t):
                struct.pack_into("<i", d, sb_off + 1, old_show - (SBTN_VA + 5))
            if mine(ok_t):
                struct.pack_into("<i", d, ok_off + 1, old_ok - (OK_VA + 5))
            assert is_last, ".xftx is no longer the last section - revert the later section's script first"
            del d[hs[3] + old_raw:]
            struct.pack_into("<I", d, hs[5] + 8, old_vs)
            struct.pack_into("<I", d, hs[5] + 16, old_raw)
            F2 = HG.load_pe(d)
            soi = HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
            struct.pack_into("<I", d, F2["opt"] + 56, soi)
            print("  sites -> %08X / %08X; .xftx -> VS %#x raw %#x; SizeOfImage %#x" % (
                old_show, old_ok, old_vs, old_raw, soi))
        for o, ob, nb in dsites:
            d[o:o + len(ob)] = ob
        try:
            with open(exe, "r+b") as f:
                f.seek(0); f.write(bytes(d)); f.truncate()
        except PermissionError:
            print("LOCKED - close AoWSetup.exe and retry")
            return 1
        if os.path.exists(bak):
            print("  %s backup" % ("EQUALS" if open(exe, "rb").read() == open(bak, "rb").read() else "DIFFERS FROM"))
        print("REVERTED")
        return 0

    if present:
        old_vs, old_raw, t_show, t_ok = struct.unpack_from("<IIII", d, zraw + Z_OLDVS)
    else:
        old_vs, old_raw, t_show, t_ok = hs[2], hs[4], sb_t, ok_t
    if present and not (mine(sb_t) and mine(ok_t)):
        print("  !! zone present but the sites point elsewhere (an earlier script was re-applied) - re-chaining "
              "from the current site targets")
        t_show, t_ok = sb_t, ok_t
    assert not mine(t_show) and not mine(t_ok)
    zone, va_show, va_ok, va_tp = build_zone(old_vs, old_raw, t_show, t_ok)
    print("  up_show @%08X, _timerproc @%08X, up_ok @%08X; tails %08X / %08X" % (va_show, va_tp, va_ok, t_show, t_ok))
    if present and mine(sb_t) and mine(ok_t) and bytes(d[zraw:zraw + ZONE_SIZE]) == zone and dnew == len(dsites):
        print("ALREADY APPLIED")
        return 0
    if not present:
        assert is_last, ".xftx must be the last section"
        assert len(d) == hs[3] + hs[4], "file has an overlay - refusing"
        assert hs[2] <= ZONE_VA - HOST_VA and hs[4] <= ZONE_VA - HOST_VA, ".xftx already larger than expected"
        assert F["soi"] == HG.align(HOST_VA - IMAGE_BASE + max(hs[2], hs[4]), F["salign"]), "SizeOfImage mismatch"
    if not do_apply:
        print("dry run OK (--apply / --revert)")
        return 0

    if not os.path.isfile(bak):
        shutil.copy2(exe, bak)
        print("  backup -> %s" % bak)
    if not present:
        d += bytes(hs[3] + HOST_NEW - len(d))
        struct.pack_into("<I", d, hs[5] + 8, HOST_NEW)
        struct.pack_into("<I", d, hs[5] + 16, HOST_NEW)
        F2 = HG.load_pe(d)
        soi = HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xftx grown to %#x (SizeOfImage %#x)" % (HOST_NEW, soi))
    d[zraw:zraw + ZONE_SIZE] = zone
    struct.pack_into("<i", d, sb_off + 1, va_show - (SBTN_VA + 5))
    struct.pack_into("<i", d, ok_off + 1, va_ok - (OK_VA + 5))
    for o, ob, nb in dsites:
        d[o:o + len(nb)] = nb
    try:
        with open(exe, "r+b") as f:
            f.seek(0); f.write(bytes(d)); f.truncate()
    except PermissionError:
        print("LOCKED - close AoWSetup.exe and retry")
        return 1
    print("APPLIED - AoWSetup -> Developer: 'Auto-Updates:' / 'Check for Updates:' dropdowns (Updater\\Mode / "
          "Frequency); OK runs AoWxUpdater.exe --register when either changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
