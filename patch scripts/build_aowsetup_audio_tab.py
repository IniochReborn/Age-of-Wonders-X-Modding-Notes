#!/usr/bin/env python3
r"""AoWSetup -- new "Audio" tab in Settings + AoWSetup's own sounds follow the game's SFX volume (2026-10-24).

User request (a player's complaints): audio settings were only reachable in game; AoWSetup's sounds are too loud and
should follow the game's SFX volume.  The game already keeps the audio settings in the registry
(HKCU\Software\Triumph Studios\Age of Wonders X\Sound, all REG_DWORD, written by AoWReg.TAoWRegistry); this tab reads
and writes exactly those values, so AoWSetup and the game always agree:
    [x] Sound Effects            -> "Sound Effects Enabled" (0/1, default 1)
    Sound Effects Volume: ====   -> "SFX Volume"   (0..100, default 50)
    [x] Music                    -> "Music Enabled"         (0/1, default 1)
    Music Volume: ============   -> "Music Volume" (0..100, default 50)
The volume sliders are native comctl32 trackbars ("msctls_trackbar32", range 0..100, ticks every 10, value tooltip
while dragging) created as child windows of the runtime TTabSheet (AoWSetup's VCL has no TTrackBar).  They are
re-created if the sheet's window was re-created (IsWindow check on every Settings open + a one-shot 350 ms timer, the
updater-settings script's idiom).  v1.1: each trackbar is SUBCLASSED (tbproc): VCL's TTabSheet answers the trackbar's
WM_CTLCOLORSTATIC by forwarding CN_CTLCOLORSTATIC (0xBD38) back to the child, which a native control returns 0 for ->
no background brush -> the thumb smeared copies while dragging; tbproc answers 0xBD38/0x138 with a cached clBtnFace
brush (CreateSolidBrush(GetSysColor(COLOR_BTNFACE))), everything else -> CallWindowProcA(original).  Captions are runtime literals -> English in every language (like the other added
tabs/rows).  Values are re-read on every Settings open, written on OK, Cancel discards.

AoWSetup VOLUME: AoWSetup plays start.wav / startbtn.wav through TMediaPlayer (MCI) - no volume control.  Instead the
process's audio-session volume is set with winmm!waveOutSetVolume(0, v|v<<16), v = SFX Volume * 0xFFFF / 100 (0 when
Sound Effects is off), resolved at run time (GetModuleHandleA("winmm.dll") - winmm is in AoWSetup's import table).
Applied at start-up BEFORE FormCreate (start.wav plays inside FormCreate) and again after OK.

HOOKS (chain heads; previous targets kept in the zone header):
  SettingsBtnClick site 0x4689F4 / SettingsOk site 0x469090 (jmps, today -> build_aowsetup_updater_settings caves)
  OnCreate binding: TLoaderForm method-table dword @file 0x677D2 ("FormCreate"; today -> the Modding wrapper 0x512034)
CHAIN ORDER: devtab -> mouse_tab -> campaign_dropdown -> hexgrid_dropdown -> flavor_checkbox -> updater_settings -> THIS
  (+ modding_button for OnCreate).  !! LIFO: revert THIS first (it grows .xftx again; the updater script's revert would
  cut this zone off).  Re-running an earlier script's --apply re-points the sites to itself -> re-run this one after.
MACHINERY: .xftx (last section, VA 0x515000) grown 0x2000 -> 0x3000; zone VA 0x517000..0x518000 'AUD1'.
Usage: py -3.10 build_aowsetup_audio_tab.py [--apply | --revert] [--exe PATH]   (dry-run default)
Backup: backup\AoWSetup.exe.bak_audiotab.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file
import build_aowsetup_hexgrid_dropdown as HG

IMAGE_BASE = 0x400000
HOST_NAME = b".xftx"
HOST_VA = 0x515000
HOST_OLD, HOST_NEW = 0x2000, 0x3000
ZONE_VA, ZONE_SIZE = 0x517000, 0x1000
MAGIC = b"AUD1"
ONCREATE_FILE = 0x677D2                      # TLoaderForm method table: FormCreate entry dword

SHEET_VMT, SHEET_CTOR, SETPAGECTL = 0x438D18, 0x43A0A8, 0x43A1E8
CHK_VMT, CHK_CTOR, GETCHECKED, SETCHECKED = 0x430368, 0x4345D4, 0x434694, 0x4346B4
LBL_VMT, LBL_CTOR = HG.LBL_VMT, HG.LBL_CTOR
SETTEXT, GETHANDLE = HG.SETTEXT, HG.GETHANDLE
SLOT_SETPARENT, SLOT_SETBOUNDS = 0x3C, 0x4C
OFF_PAGECONTROL = 0x1E8
IAT = dict(sendmsg=HG.IAT_SENDMSG, settimer=HG.IAT_SETTIMER, killtimer=HG.IAT_KILLTIMER,
           regopen=HG.IAT_REGOPEN, regquery=HG.IAT_REGQUERY, regcreate=HG.IAT_REGCREATE, regset=HG.IAT_REGSET,
           regclose=HG.IAT_REGCLOSE, getmodh=0x46C1EC, getproc=0x46C2A0, iswindow=0x46C530, createwin=0x46C654,
           setwinlong=0x46C48C, callwinproc=0x46C66C, getsyscolor=0x46C57C, createbrush=0x46C404)
HKCU = 0x80000001
SBTN_VA, OK_VA, CODE_D = HG.SBTN_VA, HG.OK_VA, HG.CODE_D

# ---- zone layout ----
Z_PREV_SHOW, Z_PREV_OK, Z_PREV_CREATE, Z_OLDVS, Z_OLDRAW = 0x04, 0x08, 0x0C, 0x10, 0x14
G = 0x20                                         # globals
GV = {n: G + 4 * i for i, n in enumerate(
    "sheet chk1 chk2 tb1 tb2 vsfx vmus esfx emus hkey type size buf disp tmp orig brush".split())}
STR = {                                          # (offset, bytes, kind)  kind a = AnsiString (chars at +8), c = C string
    "s_tab":     (0x080, b"Audio", "a"),
    "s_chk1":    (0x0A0, b"Sound Effects", "a"),
    "s_chk2":    (0x0C0, b"Music", "a"),
    "s_lbl1":    (0x0E0, b"Sound Effects Volume:", "a"),
    "s_lbl2":    (0x110, b"Music Volume:", "a"),
    "s_note":    (0x130, b"AoWSetup's own sounds follow the Sound Effects volume.", "a"),
    "s_subkey":  (0x180, b"Software\\Triumph Studios\\Age of Wonders X\\Sound", "c"),
    "v_sfx":     (0x1C0, b"SFX Volume", "c"),
    "v_mus":     (0x1D0, b"Music Volume", "c"),
    "v_esfx":    (0x1E0, b"Sound Effects Enabled", "c"),
    "v_emus":    (0x200, b"Music Enabled", "c"),
    "s_tbclass": (0x210, b"msctls_trackbar32", "c"),
    "s_winmm":   (0x228, b"winmm.dll", "c"),
    "s_wovol":   (0x238, b"waveOutSetVolume", "c"),
}
UNITS = ["timerproc", "show", "ok", "create", "regread", "regwrite", "apply", "mkchk", "mklbl", "ensuretb", "mktb", "tbproc"]
U_OFF = dict(zip(UNITS, [0x300, 0x340, 0x4C0, 0x5C0, 0x5E0, 0x680, 0x700, 0x780, 0x800, 0x880, 0x8E0, 0xA00]))
U_END = 0xA80

# layout (sheet client ~376 x 352)
X0, TB_X, TB_W, TB_H = 16, 10, 350, 30
Y_CHK1, Y_LBL1, Y_TB1 = 18, 50, 68
Y_CHK2, Y_LBL2, Y_TB2 = 122, 154, 172
Y_NOTE = 226
TBS = 0x50010101                                 # WS_CHILD|WS_VISIBLE|WS_TABSTOP|TBS_AUTOTICKS|TBS_TOOLTIPS
TBM_GETPOS, TBM_SETPOS, TBM_SETRANGE, TBM_SETTICFREQ, TBM_SETPAGESIZE = 0x400, 0x405, 0x406, 0x414, 0x415

SRC = {
"timerproc": """
    pushad
    mov  eax, dword ptr [esp + 0x2C]
    push eax
    push 0
    call dword ptr [{killtimer}]
    call {ensuretb}
    popad
    ret  16
""",
"show": """
    pushad
    mov  ebp, eax
    cmp  dword ptr [{g_sheet}], 0
    jne  have
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {sheet_vmt}
    call {sheet_ctor}
    mov  dword ptr [{g_sheet}], eax
    mov  edx, {s_tab}
    call {settext}
    mov  eax, dword ptr [{g_sheet}]
    mov  edx, dword ptr [ebp + {pagectl}]
    call {setpagectl}
    mov  esi, {s_chk1}
    mov  edi, {y_chk1}
    call {mkchk}
    mov  dword ptr [{g_chk1}], eax
    mov  esi, {s_chk2}
    mov  edi, {y_chk2}
    call {mkchk}
    mov  dword ptr [{g_chk2}], eax
    mov  esi, {s_lbl1}
    mov  edi, {y_lbl1}
    call {mklbl}
    mov  esi, {s_lbl2}
    mov  edi, {y_lbl2}
    call {mklbl}
    mov  esi, {s_note}
    mov  edi, {y_note}
    call {mklbl}
have:
    mov  edx, {v_sfx}
    mov  ecx, 50
    call {regread}
    mov  dword ptr [{g_vsfx}], eax
    mov  edx, {v_mus}
    mov  ecx, 50
    call {regread}
    mov  dword ptr [{g_vmus}], eax
    mov  edx, {v_esfx}
    mov  ecx, 1
    call {regread}
    mov  dword ptr [{g_esfx}], eax
    mov  edx, {v_emus}
    mov  ecx, 1
    call {regread}
    mov  dword ptr [{g_emus}], eax
    xor  edx, edx
    cmp  dword ptr [{g_esfx}], 0
    setne dl
    mov  eax, dword ptr [{g_chk1}]
    call {setchecked}
    xor  edx, edx
    cmp  dword ptr [{g_emus}], 0
    setne dl
    mov  eax, dword ptr [{g_chk2}]
    call {setchecked}
    call {ensuretb}
    push {timerproc}
    push 350
    push 0
    push 0
    call dword ptr [{settimer}]
    popad
    jmp  dword ptr [{prev_show}]
""",
"ok": """
    pushad
    cmp  dword ptr [{g_sheet}], 0
    je   out
    mov  eax, dword ptr [{g_chk1}]
    call {getchecked}
    movzx ecx, al
    mov  edx, {v_esfx}
    call {regwrite}
    mov  eax, dword ptr [{g_chk2}]
    call {getchecked}
    movzx ecx, al
    mov  edx, {v_emus}
    call {regwrite}
    mov  esi, dword ptr [{g_tb1}]
    mov  edi, {g_vsfx}
    mov  ebx, {v_sfx}
    call rdtb
    mov  esi, dword ptr [{g_tb2}]
    mov  edi, {g_vmus}
    mov  ebx, {v_mus}
    call rdtb
    call {apply}
out:
    popad
    jmp  dword ptr [{prev_ok}]
rdtb:
    test esi, esi
    jz   rdkeep
    push esi
    call dword ptr [{iswindow}]
    test eax, eax
    jz   rdkeep
    push 0
    push 0
    push {tbm_getpos}
    push esi
    call dword ptr [{sendmsg}]
    cmp  eax, 100
    ja   rdkeep
    mov  dword ptr [edi], eax
rdkeep:
    mov  ecx, dword ptr [edi]
    mov  edx, ebx
    call {regwrite}
    ret
""",
"create": """
    pushad
    call {apply}
    popad
    jmp  dword ptr [{prev_create}]
""",
"regread": """
    push ecx
    push edx
    push {g_hkey}
    push 1
    push 0
    push {s_subkey}
    push {hkcu}
    call dword ptr [{regopen}]
    pop  edx
    pop  ecx
    test eax, eax
    jnz  dflt
    push ecx
    mov  dword ptr [{g_size}], 4
    mov  dword ptr [{g_type}], 0
    mov  dword ptr [{g_buf}], 0
    push {g_size}
    push {g_buf}
    push {g_type}
    push 0
    push edx
    push dword ptr [{g_hkey}]
    call dword ptr [{regquery}]
    push eax
    push dword ptr [{g_hkey}]
    call dword ptr [{regclose}]
    pop  eax
    pop  ecx
    test eax, eax
    jnz  dflt
    cmp  dword ptr [{g_type}], 4
    jne  dflt
    mov  eax, dword ptr [{g_buf}]
    ret
dflt:
    mov  eax, ecx
    ret
""",
"regwrite": """
    mov  dword ptr [{g_tmp}], ecx
    push edx
    push {g_disp}
    push {g_hkey}
    push 0
    push 2
    push 0
    push 0
    push 0
    push {s_subkey}
    push {hkcu}
    call dword ptr [{regcreate}]
    pop  edx
    test eax, eax
    jnz  wout
    push 4
    push {g_tmp}
    push 4
    push 0
    push edx
    push dword ptr [{g_hkey}]
    call dword ptr [{regset}]
    push dword ptr [{g_hkey}]
    call dword ptr [{regclose}]
wout:
    ret
""",
"apply": """
    push ebx
    mov  edx, {v_esfx}
    mov  ecx, 1
    call {regread}
    xor  ebx, ebx
    test eax, eax
    jz   haveval
    mov  edx, {v_sfx}
    mov  ecx, 50
    call {regread}
    cmp  eax, 100
    jbe  inrange
    mov  eax, 100
inrange:
    imul eax, eax, 0xFFFF
    xor  edx, edx
    mov  ecx, 100
    div  ecx
    mov  ebx, eax
haveval:
    mov  eax, ebx
    shl  eax, 16
    or   ebx, eax
    push {s_winmm}
    call dword ptr [{getmodh}]
    test eax, eax
    jz   aout
    push {s_wovol}
    push eax
    call dword ptr [{getproc}]
    test eax, eax
    jz   aout
    push ebx
    push 0
    call eax
aout:
    pop  ebx
    ret
""",
"mkchk": """
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {chk_vmt}
    call {chk_ctor}
    mov  ebx, eax
    mov  edx, dword ptr [{g_sheet}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent}]
    push 220
    push 17
    mov  eax, dword ptr [ebx]
    mov  eax, dword ptr [eax + {setbounds}]
    mov  dword ptr [{g_tmp}], eax
    mov  ecx, edi
    mov  edx, {x0}
    mov  eax, ebx
    call dword ptr [{g_tmp}]
    mov  edx, esi
    mov  eax, ebx
    call {settext}
    mov  eax, ebx
    ret
""",
"mklbl": """
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {lbl_vmt}
    call {lbl_ctor}
    mov  ebx, eax
    mov  edx, dword ptr [{g_sheet}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent}]
    push 340
    push 16
    mov  eax, dword ptr [ebx]
    mov  eax, dword ptr [eax + {setbounds}]
    mov  dword ptr [{g_tmp}], eax
    mov  ecx, edi
    mov  edx, {x0}
    mov  eax, ebx
    call dword ptr [{g_tmp}]
    mov  edx, esi
    mov  eax, ebx
    call {settext}
    mov  eax, ebx
    ret
""",
"ensuretb": """
    pushad
    mov  eax, dword ptr [{g_sheet}]
    test eax, eax
    jz   eout
    mov  esi, {g_tb1}
    mov  edi, {y_tb1}
    mov  ebx, dword ptr [{g_vsfx}]
    call {mktb}
    mov  esi, {g_tb2}
    mov  edi, {y_tb2}
    mov  ebx, dword ptr [{g_vmus}]
    call {mktb}
eout:
    popad
    ret
""",
"tbproc": """
    mov  eax, dword ptr [esp + 8]
    cmp  eax, 0xBD38
    je   brush
    cmp  eax, 0x138
    je   brush
    pop  ecx
    push dword ptr [{g_orig}]
    push ecx
    jmp  dword ptr [{callwinproc}]
brush:
    mov  eax, dword ptr [{g_brush}]
    test eax, eax
    jnz  bret
    push 15
    call dword ptr [{getsyscolor}]
    push eax
    call dword ptr [{createbrush}]
    mov  dword ptr [{g_brush}], eax
bret:
    ret  16
""",
"mktb": """
    mov  eax, dword ptr [esi]
    test eax, eax
    jz   create
    push eax
    call dword ptr [{iswindow}]
    test eax, eax
    jnz  setpos
create:
    mov  eax, dword ptr [{g_sheet}]
    call {gethandle}
    test eax, eax
    jz   tbout
    push 0
    push 0
    push 0
    push eax
    push {tb_h}
    push {tb_w}
    push edi
    push {tb_x}
    push {tbs}
    push 0
    push {s_tbclass}
    push 0
    call dword ptr [{createwin}]
    mov  dword ptr [esi], eax
    test eax, eax
    jz   tbout
    push {tbproc}
    push -4
    push eax
    call dword ptr [{setwinlong}]
    test eax, eax
    jz   tbout
    mov  dword ptr [{g_orig}], eax
    push 0x00640000
    push 1
    push {tbm_setrange}
    push dword ptr [esi]
    call dword ptr [{sendmsg}]
    push 0
    push 10
    push {tbm_setticfreq}
    push dword ptr [esi]
    call dword ptr [{sendmsg}]
    push 10
    push 0
    push {tbm_setpagesize}
    push dword ptr [esi]
    call dword ptr [{sendmsg}]
setpos:
    push ebx
    push 1
    push {tbm_setpos}
    push dword ptr [esi]
    call dword ptr [{sendmsg}]
tbout:
    ret
""",
}


def fmt():
    Z = ZONE_VA
    f = {k: hex(v) for k, v in IAT.items()}
    f.update({("g_" + n): hex(Z + o) for n, o in GV.items()})
    f.update({n: hex(Z + o + (8 if kind == "a" else 0)) for n, (o, _s, kind) in STR.items()})
    f.update({u: hex(Z + U_OFF[u]) for u in UNITS})
    f.update(prev_show=hex(Z + Z_PREV_SHOW), prev_ok=hex(Z + Z_PREV_OK), prev_create=hex(Z + Z_PREV_CREATE),
             sheet_vmt=hex(SHEET_VMT), sheet_ctor=hex(SHEET_CTOR), setpagectl=hex(SETPAGECTL),
             chk_vmt=hex(CHK_VMT), chk_ctor=hex(CHK_CTOR), getchecked=hex(GETCHECKED), setchecked=hex(SETCHECKED),
             lbl_vmt=hex(LBL_VMT), lbl_ctor=hex(LBL_CTOR), settext=hex(SETTEXT), gethandle=hex(GETHANDLE),
             setparent=hex(SLOT_SETPARENT), setbounds=hex(SLOT_SETBOUNDS), pagectl=hex(OFF_PAGECONTROL),
             hkcu=hex(HKCU), x0=X0, tb_x=TB_X, tb_w=TB_W, tb_h=TB_H, tbs=hex(TBS),
             y_chk1=Y_CHK1, y_chk2=Y_CHK2, y_lbl1=Y_LBL1, y_lbl2=Y_LBL2, y_tb1=Y_TB1, y_tb2=Y_TB2, y_note=Y_NOTE,
             tbm_getpos=hex(TBM_GETPOS), tbm_setpos=hex(TBM_SETPOS), tbm_setrange=hex(TBM_SETRANGE),
             tbm_setticfreq=hex(TBM_SETTICFREQ), tbm_setpagesize=hex(TBM_SETPAGESIZE))
    return f


def build_zone(prev_show, prev_ok, prev_create, old_vs, old_raw):
    """keystone hangs on ';' comments in this project -> sources are comment-free.  Every routine is assembled on its
    own at a fixed zone offset, so cross-references are plain absolute addresses."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    z = bytearray(ZONE_SIZE)
    z[0:4] = MAGIC
    struct.pack_into("<IIIII", z, Z_PREV_SHOW, prev_show, prev_ok, prev_create, old_vs, old_raw)
    for n, (o, s, kind) in STR.items():
        b = HG.astr(s, 0x100) if kind == "a" else s + b"\0"
        b = b.rstrip(b"\0") + b"\0"
        z[o:o + len(b)] = b
    offs = sorted([o for o, _s, _k in STR.values()] + [0x300])
    for n, (o, s, kind) in STR.items():
        nxt = min(x for x in offs if x > o)
        assert o + (len(s) + 9 if kind == "a" else len(s) + 1) <= nxt, "string %s overflows" % n
    F = fmt()
    ends = sorted(U_OFF.values()) + [U_END]
    for u in UNITS:
        va = ZONE_VA + U_OFF[u]
        code = bytes(ks.asm(SRC[u].format(**F), va)[0])
        lim = min(x for x in ends if x > U_OFF[u])
        assert U_OFF[u] + len(code) <= lim, "unit %s too big (%d B, room %d)" % (u, len(code), lim - U_OFF[u])
        z[U_OFF[u]:U_OFF[u] + len(code)] = code
    return bytes(z)


def host(d, F):
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == HOST_NAME:
            return s
    return None


def main():
    a = sys.argv[1:]
    do_apply, revert = "--apply" in a, "--revert" in a
    exe = a[a.index("--exe") + 1] if "--exe" in a else game_file("AoWSetup.exe")
    bak = bak_path(exe, ".bak_audiotab", create=do_apply)
    d = bytearray(open(exe, "rb").read())
    F = HG.load_pe(d)
    hs = host(d, F)
    assert hs is not None and hs[1] + IMAGE_BASE == HOST_VA, ".xftx not found"
    is_last = F["secs"][-1][5] == hs[5]
    sb_off, ok_off = SBTN_VA - CODE_D, OK_VA - CODE_D
    sb_t = HG.site_target(d, sb_off) + CODE_D
    ok_t = HG.site_target(d, ok_off) + CODE_D
    oc_t = struct.unpack_from("<I", d, ONCREATE_FILE)[0]
    assert d[ONCREATE_FILE + 4:ONCREATE_FILE + 15] == b"\x0aFormCreate", "OnCreate method-table entry moved"
    mine = lambda va: ZONE_VA <= va < ZONE_VA + ZONE_SIZE
    zraw = hs[3] + (ZONE_VA - HOST_VA)
    present = hs[2] >= HOST_NEW and hs[4] >= HOST_NEW and bytes(d[zraw:zraw + 4]) == MAGIC
    print("target %s\n  .xftx VS %#x raw %#x (last: %s); zone %s" % (exe, hs[2], hs[4], is_last,
                                                                    "PRESENT" if present else "absent"))
    print("  SettingsBtn -> %08X  SettingsOk -> %08X  OnCreate -> %08X  (%s)" % (
        sb_t, ok_t, oc_t, "OURS" if mine(sb_t) and mine(ok_t) and mine(oc_t) else "prev owners"))

    if revert:
        if not present:
            print("ALREADY VANILLA"); return 0
        p_show, p_ok, p_create, old_vs, old_raw = struct.unpack_from("<IIIII", d, zraw + Z_PREV_SHOW)
        if mine(sb_t): struct.pack_into("<i", d, sb_off + 1, p_show - (SBTN_VA + 5))
        if mine(ok_t): struct.pack_into("<i", d, ok_off + 1, p_ok - (OK_VA + 5))
        if mine(oc_t): struct.pack_into("<I", d, ONCREATE_FILE, p_create)
        assert is_last, ".xftx is no longer the last section"
        del d[hs[3] + old_raw:]
        struct.pack_into("<I", d, hs[5] + 8, old_vs)
        struct.pack_into("<I", d, hs[5] + 16, old_raw)
        F2 = HG.load_pe(d)
        struct.pack_into("<I", d, F2["opt"] + 56, HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"]))
        try:
            with open(exe, "r+b") as f:
                f.seek(0); f.write(bytes(d)); f.truncate()
        except PermissionError:
            print("LOCKED - close AoWSetup.exe and retry"); return 1
        if os.path.exists(bak):
            print("  %s backup" % ("EQUALS" if open(exe, "rb").read() == open(bak, "rb").read() else "DIFFERS FROM"))
        print("REVERTED"); return 0

    if present:
        p_show, p_ok, p_create, old_vs, old_raw = struct.unpack_from("<IIIII", d, zraw + Z_PREV_SHOW)
        if not (mine(sb_t) and mine(ok_t) and mine(oc_t)):
            print("  !! zone present but a site points elsewhere - re-chaining from the current targets")
            p_show = sb_t if not mine(sb_t) else p_show
            p_ok = ok_t if not mine(ok_t) else p_ok
            p_create = oc_t if not mine(oc_t) else p_create
    else:
        p_show, p_ok, p_create, old_vs, old_raw = sb_t, ok_t, oc_t, hs[2], hs[4]
    assert not (mine(p_show) or mine(p_ok) or mine(p_create))
    zone = build_zone(p_show, p_ok, p_create, old_vs, old_raw)
    show_va, ok_va, create_va = (ZONE_VA + U_OFF[u] for u in ("show", "ok", "create"))
    print("  au_show %08X  au_ok %08X  au_create %08X; tails %08X / %08X / %08X" % (
        show_va, ok_va, create_va, p_show, p_ok, p_create))
    if present and mine(sb_t) and mine(ok_t) and mine(oc_t) and bytes(d[zraw:zraw + ZONE_SIZE]) == zone:
        print("ALREADY APPLIED"); return 0
    if not present:
        assert is_last, ".xftx must be the last section"
        assert len(d) == hs[3] + hs[4], "file has an overlay - refusing"
        assert hs[2] == HOST_OLD and hs[4] == HOST_OLD, ".xftx size unexpected (updater settings applied?)"
    if not do_apply:
        print("dry run OK (--apply / --revert)"); return 0
    if not os.path.isfile(bak):
        shutil.copy2(exe, bak); print("  backup -> %s" % bak)
    if not present:
        d += bytes(hs[3] + HOST_NEW - len(d))
        struct.pack_into("<I", d, hs[5] + 8, HOST_NEW)
        struct.pack_into("<I", d, hs[5] + 16, HOST_NEW)
        F2 = HG.load_pe(d)
        soi = HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xftx grown to %#x (SizeOfImage %#x)" % (HOST_NEW, soi))
    zraw = hs[3] + (ZONE_VA - HOST_VA)
    d[zraw:zraw + ZONE_SIZE] = zone
    struct.pack_into("<i", d, sb_off + 1, show_va - (SBTN_VA + 5))
    struct.pack_into("<i", d, ok_off + 1, ok_va - (OK_VA + 5))
    struct.pack_into("<I", d, ONCREATE_FILE, create_va)
    try:
        with open(exe, "r+b") as f:
            f.seek(0); f.write(bytes(d)); f.truncate()
    except PermissionError:
        print("LOCKED - close AoWSetup.exe and retry"); return 1
    print("APPLIED - AoWSetup -> Settings -> Audio tab; AoWSetup's sounds follow the SFX volume.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
