#!/usr/bin/env python3
r"""
AoWx auto-updater, STEP 4 - the game side (AoWx.exe title screen) (2026-10-20), v5 (2026-10-31).

v5 (user: "add another typed command to the title screen, similar to update. this one will be repair and it should
prompt the user via a similar pop up message whether they want to repair/redownload the latest update"): typing
R E P A I R (same rolling buffer / conditions as UPDATE, needs AoWxUpdater.exe) -> the same Yes/No dialog with
"Repair AoWx? This downloads and reinstalls the latest version. The game will close."  Yes -> next frame:
AoWxUpdater.exe --repair <pid> (normal window) + the title Quit sequence.  Upgrades UPD4 in place.


Talks to AoWxUpdater.exe (patch scripts\updater) only through the registry
HKCU\Software\Triumph Studios\Age of Wonders X\Updater (Mode Auto|Ask|Off, Status 0 unknown / 1 up to date /
2 available / 3 downloaded - installs on exit, LatestVersion, LastChecked) and by launching it with ShellExecuteA:
  * once per process, on the first title-screen frame:  AoWxUpdater.exe --game-start <pid>   (hidden; skipped when the
    exe is missing or Mode = Off)
  * title status line ABOVE the Version label, right-aligned to it, Version font:
        1 green  "AoWx is up to date!"            2 red    "Update available!"
        3 amber  "Update ready - installs when you quit"   checking: grey "Checking for updates..."
        0 / Mode Off / no AoWxUpdater.exe: nothing
    The registry is re-read once a second (KUSER_SHARED_DATA InterruptTime).  When the text or hover state changes the
    line's area is cleared outside the cloud band for 3 frames (the title only repaints the band - same lesson as the
    title-quote v2 fix) and the three title labels the vanilla draw paints are redrawn.
  * red line: hover (mouse position = TTitleScene +0x70/+0x74, written by WindowMouseMove) -> v2 (2026-10-20, user:
    'change to Download update', 'grow/glow less extreme'): text becomes "Download update", SAME font (no size
    change), slightly brighter red with a very soft dark-red glow on the 4 orthogonal neighbours;
    v3 (2026-10-20, user: 'slight fade in/out when it changes', 'make it pulse', 'hovering anywhere over the version
    number/update text activates it'): every change of the shown line (status change, first appearance, hover
    toggle) fades the old text out (100 ms) and the new one in (150 ms) by scaling its colour toward the black
    background (the line area is cleared every frame while animating); the glow is gone - while hovered, the
    'Download update' text PULSES (brightness 70 %..100 %, triangle wave, 1 s period); the hover / click area is ONE
    rectangle covering the status line, the Version label text and the gap between them; left click (TTitleScene.WindowMouseUp, button = left) ->
    Yes/No in the shared TMessageDlg (YesNoPnl, same machinery as the tutorial confirm): "Update AoWx to <ver> now?
    The game will close."  Yes -> next frame: AoWxUpdater.exe --install <pid> (normal window) + the title Quit
    sequence (same code as the 'ziggurat' egg's Okay).  While OUR dialog is open every title click is swallowed.
  * Mode Ask: once per game session, the first time the title is up with Status 2 and the dialog idle: "AoWx <ver> is
    available. Update now?" Yes/No (Yes = same as clicking the red line).
  * typing U P D A T E on the title (same conditions as the inioch/ziggurat eggs, own rolling buffer) ->
    AoWxUpdater.exe --check (hidden) and "Checking for updates..." until Status or LastChecked changes or 15 s pass.
    Ignored when Mode = Off or the exe is missing.
  * v4 (2026-10-21, user: 'hover over the green text -> pulsing Check for update?, click = same as typing update'):
    with Status 1 the same union hover area turns the green line into "Check for update?" (brighter green, same
    70 %..100 % 1 s pulse and fades as the red line); a left click there runs the typed-UPDATE path directly (no
    dialog).  The amber Status 3 line stays non-interactive; while "Checking..." is shown clicks are ignored.

Hooks (all chained in FRONT of what is there now, previous targets kept in the zone header):
  X  0x41A0BB (7 B `mov eax,esi / mov edx,[eax] / call [edx+0x30]`, the surface unlock right after the label draws and
     after title-quotes v3's cave returns) -> draw the status line, then the 7 bytes, jmp 0x41A0C2.
  K  0x45549C ManagerKeyDown: the 5-byte `jmp <title-quotes v3 cave_key>` -> ours -> previous target.
  U  method-table dword 0x4193DA (WindowUpdate; tutorial-confirm's upd)  -> per-frame logic after the previous handler.
  D  method-table dword 0x419419 (WindowMouseUp, vanilla 0x41AE94)        -> click handling, else previous handler.
  M  method-table dword 0x4193A8 (TitleSceneDestroy; title-quotes v3 cave_dest) -> forget the scene, previous.
Win32 APIs not in AoWx.exe's IAT (RegOpenKeyExA / RegQueryValueExA / RegCloseKey) come from GetProcAddress, which is
found once by walking kernel32's export table (GetModuleHandleA is imported); the pid is read from the TEB
(fs:[0x20]); ShellExecuteA / GetModuleFileNameA / CreateFileA / CloseHandle are imported.

.xtut (must be the LAST section, title-quotes v3 applied, raw 0x1400 / VS 0x2000 / SizeOfImage 0x236000):
  raw 0x1400 -> 0x3200 (file bytes 0x635400..0x636000 stay zero = title-quotes v3's runtime data, unchanged),
  code zone 0x636000..0x637200, runtime data 0x637200..0x637A00 (VS 0x2000 -> 0x4000, SizeOfImage -> 0x238000).
Revert = exact (sites restored from the zone header, file truncated, sizes restored).  Revert THIS first, before
patch_exe_title_quotes_v3 / patch_title_tutorial_confirm_v1.
UI only, no game state -> MP-irrelevant.  Dry-run default; --apply / --revert / --dis; --exe <scratch copy>.
Backup backup\AoWx.exe.bak_updtitle.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_updtitle5"
BASE = 0x400000
SEC_NAME, SEC_VA = b".xtut", 0x634000
RAW_OLD, RAW_NEW = 0x1400, 0x3200
VS_OLD, VS_NEW = 0x2000, 0x4000
ZONE, ZONE_END = 0x636000, 0x637200
DATA, DATA_END = 0x637200, 0x637A00
MAGIC = b"UPD5"
MAGIC_V4 = b"UPD4"
MAGIC_V1 = b"UPD1"                            # v1 / v2 / v3 zones (same header layout) -> upgraded in place
MAGIC_V2 = b"UPD2"
MAGIC_V3 = b"UPD3"
TTQ3_MAGIC_VA = 0x634800                     # title quotes v3 zone magic 'TTQ3'

SITE_X, SITE_X_ORIG = 0x41A0BB, bytes.fromhex("8bc68b10ff5230")
SITE_K = 0x45549C                            # 7 B: E9 rel32 + 90 90 (title quotes v3)
SITE_U = 0x4193DA                            # dword
SITE_D = 0x419419                            # dword
SITE_M = 0x4193A8                            # dword

# zone header
H_ORIG_K = ZONE + 0x04                       # 7 bytes
H_PREV_K = ZONE + 0x0C
H_PREV_U = ZONE + 0x10
H_PREV_D = ZONE + 0x14
H_PREV_M = ZONE + 0x18
VMT = ZONE + 0x80                            # fake message-object VMT (0x40 zero bytes in front)
NSLOTS = 0x24
FAKEOBJ = ZONE + 0x120
LITS = ZONE + 0x130
CODE = ZONE + 0x400

# runtime data
D = lambda o: DATA + o
MYSCENE, LAUNCHED, HASEXE, MODE, STATUS, LASTPOLL, POLLED, CHECKING = (D(4 * i) for i in range(8))
CHKSTART, CHKSTAT, DRAWNID, DIRTY, HOVER, ASKED, GOINSTALL, GPA = (D(0x20 + 4 * i) for i in range(8))
PREGOPEN, PREGQUERY, PREGCLOSE, RESOLVED = (D(0x40 + 4 * i) for i in range(4))
KBUF = D(0x50)                               # 8 bytes
RECT = D(0x58)                               # hit rect x0,y0,x1,y1
HK, TMPTYPE, TMPSIZE, DLGWHICH, GTWFN, TMPDW = (D(0x78 + 4 * i) for i in range(6))
SURFCOPY = D(0x90)                           # 0x3C
LASTCHK = D(0xD0)                            # 32
CHKSNAP = D(0xF0)                            # 32
VERBUF = D(0x110)                            # 32
PARAMS = D(0x150)                            # 64
MSGSTR = D(0x190)                            # 8 header + 120
PATH = D(0x210)                              # 264
GAMEDIR = D(0x318)                           # 264
NEWID, OLDID, TSTART, ANIM = (D(0x430 + 4 * i) for i in range(4))   # v3 fade state (id = state*2 + hover)
assert ANIM + 4 <= DATA_END

FONTMOD_VAR, F_AGE10 = 0x45A210, 0x50
I_GETMODH, I_GETMODFN, I_CREATEFILE, I_CLOSEH, I_SHELLEXEC = 0x45D39C, 0x45D3A0, 0x45D3CC, 0x45D3D4, 0x45EE38
I_SETTEXT, I_SETCOLOR = 0x45D7B8, 0x45D7BC
HKCU, KEY_READ = 0x80000001, 0x20019
SEC1 = 10000000                              # InterruptTime ticks per second (100 ns)
CHK_TIMEOUT = 15 * SEC1
COL_UP, COL_AV, COL_RD, COL_CK = 0x00309A30, 0x003838F0, 0x0000B8FF, 0x00C0C0C0
COL_HOT, COL_GLOW = 0x004848FF, 0x00101048          # v2: subtle hover (v1: 0x006868FF / 0x00000090)
COL_UPHOT = 0x0040C040                       # v4: green hover ('Check for update?'), a touch brighter than COL_UP
CLR_W, CLR_H = 270, 24                       # cleared box left of / above the Version right edge
OUTDUR, INDUR = 1000000, 1500000            # v3 fade-out 100 ms / fade-in 150 ms (InterruptTime, 100 ns)
PULSE_MIN = 179                              # v3 hover pulse: 179/256 = 70 % .. 100 %, 1 s triangle
PULSE_SPAN = 256 - PULSE_MIN

STRS = [  # (name, bytes, ansistring?)
    ("up", b"AoWx is up to date!", True), ("av", b"Update available!", True), ("dl", b"Download update", True), ("cu", b"Check for update?", True),
    ("rd", b"Update ready - installs when you quit", True), ("ck", b"Checking for updates...", True),
    ("title", b"AoWx Update", True),
    ("k32", b"kernel32.dll", False), ("gpa", b"GetProcAddress", False), ("adv", b"advapi32.dll", False),
    ("ll", b"LoadLibraryA", False), ("rok", b"RegOpenKeyExA", False), ("rq", b"RegQueryValueExA", False),
    ("rc", b"RegCloseKey", False), ("sub", b"Software\\Triumph Studios\\Age of Wonders X\\Updater", False),
    ("mode", b"Mode", False), ("status", b"Status", False), ("lv", b"LatestVersion", False),
    ("lc", b"LastChecked", False), ("open", b"open", False), ("exe", b"AoWxUpdater.exe", False),
    ("pgs", b"--game-start ", False), ("pin", b"--install ", False), ("pck", b"--check", False),
    ("prp", b"--repair ", False), ("rtitle", b"AoWx Repair", True),
    ("r1", b"Repair AoWx? This downloads and reinstalls the latest version. The game will close.", False),
    ("m1", b"Update AoWx to ", False), ("m2", b" now? The game will close.", False),
    ("a1", b"AoWx ", False), ("a2", b" is available. Update now?", False), ("nv", b"the new version", False),
]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    src = "\n".join(l.split(";")[0] for l in src.splitlines())
    return bytes(ks.asm(src, va)[0])


def lits():
    out = bytearray(); addr = {}
    for name, s, ans in STRS:
        if ans:
            out += struct.pack("<iI", -1, len(s))
        addr[name] = LITS + len(out)
        out += s + b"\0"
        out += bytes((-len(out)) % 4)
    assert LITS + len(out) <= CODE, "literals overflow"
    return bytes(out), addr


SRC = r"""
    jmp cave_draw
    jmp cave_key
    jmp cave_upd
    jmp cave_mup
    jmp cave_dest
    jmp ret0
    jmp e_yes
    jmp e_close

cave_draw:
    pushad
    lea eax, [ebp-0x3c]
    mov edx, ebx
    call sdraw
    popad
    mov eax, esi
    mov edx, dword ptr [eax]
    call dword ptr [edx+0x30]
    jmp 0x41a0c2

cave_key:
    pushad
    mov eax, edx
    movzx ecx, word ptr [ecx]
    call ukey
    popad
    jmp dword ptr [{H_PREV_K:#x}]

cave_dest:
    mov dword ptr [{MYSCENE:#x}], 0
    jmp dword ptr [{H_PREV_M:#x}]

cave_upd:
    push eax
    push edx
    push ecx
    call dword ptr [{H_PREV_U:#x}]
    pop ecx
    pop edx
    pop eax
    pushad
    mov dword ptr [{MYSCENE:#x}], eax
    mov ebx, eax
    call frame
    popad
    ret

cave_mup:
    pushad
    mov edx, dword ptr [0x45a1a0]
    mov edx, dword ptr [edx]
    test edx, edx
    jz mu_1
    cmp dword ptr [edx+0xb8], {FAKEOBJ:#x}
    je mu_swallow
mu_1:
    test cl, cl
    jnz mu_pass
    test edx, edx
    jz mu_pass
    cmp dword ptr [edx+0xb8], 0
    jne mu_pass
    call state
    mov ebp, eax
    cmp eax, 2
    je mu_hit
    cmp eax, 1
    jne mu_pass
mu_hit:
    mov eax, dword ptr [esp+0x28]
    mov ecx, dword ptr [esp+0x24]
    cmp eax, dword ptr [{RECT:#x}]
    jl mu_pass
    cmp eax, dword ptr [{RECT:#x}+8]
    jg mu_pass
    cmp ecx, dword ptr [{RECT:#x}+4]
    jl mu_pass
    cmp ecx, dword ptr [{RECT:#x}+12]
    jg mu_pass
    cmp ebp, 1
    jne mu_dlg
    call startchk
    jmp mu_swallow
mu_dlg:
    mov dword ptr [{DLGWHICH:#x}], 0
    mov esi, edx
    call showdlg
mu_swallow:
    popad
    ret 0xc
mu_pass:
    popad
    jmp dword ptr [{H_PREV_D:#x}]

ret0:
    xor eax, eax
    ret
e_yes:
    mov dword ptr [{GOINSTALL:#x}], 1
    cmp dword ptr [{DLGWHICH:#x}], 2
    jne e_close
    mov dword ptr [{GOINSTALL:#x}], 2
e_close:
    mov al, 1
    ret

now:
    mov eax, dword ptr [0x7ffe0008]
    ret

state:
    xor eax, eax
    cmp dword ptr [{HASEXE:#x}], 1
    jne st_out
    cmp dword ptr [{MODE:#x}], 2
    je st_out
    mov eax, 4
    cmp dword ptr [{CHECKING:#x}], 0
    jne st_out
    mov eax, dword ptr [{STATUS:#x}]
    cmp eax, 3
    jbe st_out
    xor eax, eax
st_out:
    ret

frame:
    cmp dword ptr [{LAUNCHED:#x}], 0
    jne fr_1
    mov dword ptr [{LAUNCHED:#x}], 1
    call init_paths
    call resolve
    call poll
    call now
    mov dword ptr [{LASTPOLL:#x}], eax
    cmp dword ptr [{HASEXE:#x}], 1
    jne fr_1
    cmp dword ptr [{MODE:#x}], 2
    je fr_1
    mov esi, {L_pgs:#x}
    mov edi, 0
    mov ecx, 1
    call launch
fr_1:
    mov eax, dword ptr [{GOINSTALL:#x}]
    test eax, eax
    je fr_2
    mov dword ptr [{GOINSTALL:#x}], 0
    cmp dword ptr [{HASEXE:#x}], 1
    jne fr_2
    mov esi, {L_pin:#x}
    cmp eax, 2
    jne fr_inst
    mov esi, {L_prp:#x}
fr_inst:
    mov edi, 1
    mov ecx, 1
    call launch
    call doquit
    ret
fr_2:
    call now
    mov edx, eax
    sub edx, dword ptr [{LASTPOLL:#x}]
    cmp edx, {SEC1}
    jb fr_3
    mov dword ptr [{LASTPOLL:#x}], eax
    call poll
    cmp dword ptr [{CHECKING:#x}], 0
    je fr_3
    mov eax, dword ptr [{STATUS:#x}]
    cmp eax, dword ptr [{CHKSTAT:#x}]
    jne fr_ckdone
    push esi
    push edi
    push ecx
    mov esi, {LASTCHK:#x}
    mov edi, {CHKSNAP:#x}
    mov ecx, 32
    repe cmpsb byte ptr [esi], byte ptr es:[edi]
    pop ecx
    pop edi
    pop esi
    jne fr_ckdone
    call now
    sub eax, dword ptr [{CHKSTART:#x}]
    cmp eax, {CHK_TIMEOUT}
    jb fr_3
fr_ckdone:
    mov dword ptr [{CHECKING:#x}], 0
fr_3:
    cmp dword ptr [{MODE:#x}], 1
    jne fr_out
    cmp dword ptr [{ASKED:#x}], 0
    jne fr_out
    call state
    cmp eax, 2
    jne fr_out
    mov eax, dword ptr [ebx+0x48]
    test eax, eax
    jz fr_out
    cmp byte ptr [eax+0x75], 0
    je fr_out
    mov esi, dword ptr [0x45a1a0]
    mov esi, dword ptr [esi]
    test esi, esi
    jz fr_out
    cmp dword ptr [esi+0xb8], 0
    jne fr_out
    mov dword ptr [{ASKED:#x}], 1
    mov dword ptr [{DLGWHICH:#x}], 1
    call showdlg
fr_out:
    ret

doquit:
    mov eax, dword ptr [ebx+0x48]
    test eax, eax
    jz dq_x
    xor edx, edx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
dq_x:
    mov eax, dword ptr [0x45a420]
    mov eax, dword ptr [eax]
    xor edx, edx
    call 0x455dfc
    mov eax, dword ptr [0x45df74]
    mov eax, dword ptr [eax]
    cmp byte ptr [eax+0x6e], 0
    je dq_term
    mov eax, dword ptr [0x45a28c]
    mov eax, dword ptr [eax]
    call 0x429c14
    ret
dq_term:
    mov eax, dword ptr [0x45a168]
    mov eax, dword ptr [eax]
    call 0x40171c
    ret

init_paths:
    mov dword ptr [{HASEXE:#x}], 0
    push 260
    push {PATH:#x}
    push 0
    call dword ptr [{I_GETMODFN:#x}]
    test eax, eax
    jz ip_out
    cmp eax, 260
    jae ip_out
    mov ecx, eax
ip_find:
    dec ecx
    js ip_out
    cmp byte ptr [{PATH:#x}+ecx], 0x5c
    jne ip_find
    lea eax, [ecx+20]
    cmp eax, 260
    jae ip_out
    push ecx
    mov esi, {PATH:#x}
    mov edi, {GAMEDIR:#x}
    rep movsb byte ptr es:[edi], byte ptr [esi]
    mov byte ptr [edi], 0
    pop ecx
    lea edi, [{PATH:#x}+ecx+1]
    mov esi, {L_exe:#x}
    mov ecx, 16
    rep movsb byte ptr es:[edi], byte ptr [esi]
    push 0
    push 0x80
    push 3
    push 0
    push 1
    push 0x80000000
    push {PATH:#x}
    call dword ptr [{I_CREATEFILE:#x}]
    cmp eax, 0xffffffff
    je ip_out
    push eax
    call dword ptr [{I_CLOSEH:#x}]
    mov dword ptr [{HASEXE:#x}], 1
ip_out:
    ret

resolve:
    push ebx
    push ebp
    push esi
    push edi
    cmp dword ptr [{RESOLVED:#x}], 0
    jne rs_out
    mov dword ptr [{RESOLVED:#x}], 0xffffffff
    push {L_k32:#x}
    call dword ptr [{I_GETMODH:#x}]
    test eax, eax
    jz rs_out
    mov ebx, eax
    cmp word ptr [ebx], 0x5a4d
    jne rs_out
    mov eax, dword ptr [ebx+0x3c]
    mov eax, dword ptr [ebx+eax+0x78]
    test eax, eax
    jz rs_out
    lea ebp, [ebx+eax]
    mov edx, dword ptr [ebp+0x20]
    add edx, ebx
    xor edi, edi
rs_loop:
    cmp edi, dword ptr [ebp+0x18]
    jae rs_out
    mov esi, dword ptr [edx+edi*4]
    add esi, ebx
    push edi
    mov edi, {L_gpa:#x}
    mov ecx, 15
    repe cmpsb byte ptr [esi], byte ptr es:[edi]
    pop edi
    je rs_found
    inc edi
    jmp rs_loop
rs_found:
    mov eax, dword ptr [ebp+0x24]
    add eax, ebx
    movzx eax, word ptr [eax+edi*2]
    mov ecx, dword ptr [ebp+0x1c]
    add ecx, ebx
    mov eax, dword ptr [ecx+eax*4]
    add eax, ebx
    mov dword ptr [{GPA:#x}], eax
    push {L_adv:#x}
    call dword ptr [{I_GETMODH:#x}]
    test eax, eax
    jnz rs_adv
    push {L_ll:#x}
    push ebx
    call dword ptr [{GPA:#x}]
    test eax, eax
    jz rs_out
    push {L_adv:#x}
    call eax
    test eax, eax
    jz rs_out
rs_adv:
    mov esi, eax
    push {L_rok:#x}
    push esi
    call dword ptr [{GPA:#x}]
    mov dword ptr [{PREGOPEN:#x}], eax
    test eax, eax
    jz rs_out
    push {L_rq:#x}
    push esi
    call dword ptr [{GPA:#x}]
    mov dword ptr [{PREGQUERY:#x}], eax
    test eax, eax
    jz rs_out
    push {L_rc:#x}
    push esi
    call dword ptr [{GPA:#x}]
    mov dword ptr [{PREGCLOSE:#x}], eax
    test eax, eax
    jz rs_out
    mov dword ptr [{RESOLVED:#x}], 1
rs_out:
    pop edi
    pop esi
    pop ebp
    pop ebx
    ret

poll:
    mov dword ptr [{POLLED:#x}], 1
    mov dword ptr [{MODE:#x}], 0
    mov dword ptr [{STATUS:#x}], 0
    mov byte ptr [{VERBUF:#x}], 0
    mov byte ptr [{LASTCHK:#x}], 0
    cmp dword ptr [{RESOLVED:#x}], 1
    jne pl_out
    push {HK:#x}
    push {KEY_READ:#x}
    push 0
    push {L_sub:#x}
    push {HKCU:#x}
    call dword ptr [{PREGOPEN:#x}]
    test eax, eax
    jnz pl_out
    mov eax, {L_mode:#x}
    mov edx, {VERBUF:#x}
    call qstr
    mov al, byte ptr [{VERBUF:#x}]
    or al, 0x20
    cmp al, 0x6f
    jne pl_m1
    mov dword ptr [{MODE:#x}], 2
    jmp pl_m2
pl_m1:
    cmp al, 0x61
    jne pl_m2
    mov al, byte ptr [{VERBUF:#x}+1]
    or al, 0x20
    cmp al, 0x73
    jne pl_m2
    mov dword ptr [{MODE:#x}], 1
pl_m2:
    mov dword ptr [{TMPSIZE:#x}], 4
    mov dword ptr [{TMPDW:#x}], 0
    push {TMPSIZE:#x}
    push {TMPDW:#x}
    push {TMPTYPE:#x}
    push 0
    push {L_status:#x}
    push dword ptr [{HK:#x}]
    call dword ptr [{PREGQUERY:#x}]
    test eax, eax
    jnz pl_s
    cmp dword ptr [{TMPTYPE:#x}], 4
    jne pl_s
    mov eax, dword ptr [{TMPDW:#x}]
    mov dword ptr [{STATUS:#x}], eax
pl_s:
    mov eax, {L_lv:#x}
    mov edx, {VERBUF:#x}
    call qstr
    mov eax, {L_lc:#x}
    mov edx, {LASTCHK:#x}
    call qstr
    push dword ptr [{HK:#x}]
    call dword ptr [{PREGCLOSE:#x}]
pl_out:
    ret

qstr:
    push ebx
    mov ebx, edx
    mov byte ptr [ebx], 0
    mov byte ptr [ebx+31], 0
    mov dword ptr [{TMPSIZE:#x}], 31
    push {TMPSIZE:#x}
    push ebx
    push {TMPTYPE:#x}
    push 0
    push eax
    push dword ptr [{HK:#x}]
    call dword ptr [{PREGQUERY:#x}]
    test eax, eax
    jnz qs_bad
    cmp dword ptr [{TMPTYPE:#x}], 1
    jne qs_bad
    mov eax, dword ptr [{TMPSIZE:#x}]
    cmp eax, 31
    jae qs_ok
    mov byte ptr [ebx+eax], 0
    jmp qs_ok
qs_bad:
    mov byte ptr [ebx], 0
qs_ok:
    mov byte ptr [ebx+31], 0
    pop ebx
    ret

launch:
    push ebp
    mov ebp, edi
    push ebx
    mov ebx, ecx
    mov edi, {PARAMS:#x}
la_cp:
    lodsb byte ptr [esi]
    stosb byte ptr es:[edi], al
    test al, al
    jnz la_cp
    dec edi
    test ebx, ebx
    jz la_go
    mov eax, dword ptr fs:[0x20]
    mov ecx, 10
    xor ebx, ebx
la_dig:
    xor edx, edx
    div ecx
    add dl, 0x30
    push edx
    inc ebx
    test eax, eax
    jnz la_dig
la_put:
    pop eax
    stosb byte ptr es:[edi], al
    dec ebx
    jnz la_put
    mov byte ptr [edi], 0
la_go:
    push ebp
    push {GAMEDIR:#x}
    push {PARAMS:#x}
    push {PATH:#x}
    push {L_open:#x}
    push 0
    call dword ptr [{I_SHELLEXEC:#x}]
    pop ebx
    pop ebp
    ret
"""

SRC += r"""
ukey:
    mov edx, dword ptr [{MYSCENE:#x}]
    test edx, edx
    jz uk_ret
    mov edx, dword ptr [edx+0x48]
    test edx, edx
    jz uk_ret
    cmp byte ptr [edx+0x75], 0
    je uk_ret
    mov edx, dword ptr [edx+0xa0]
    cmp dword ptr [eax+0x10c], edx
    jg uk_ret
    mov edx, dword ptr [0x45a1a0]
    mov edx, dword ptr [edx]
    test edx, edx
    jz uk_1
    cmp dword ptr [edx+0xb8], 0
    jne uk_ret
uk_1:
    cmp ecx, 0x41
    jb uk_clear
    cmp ecx, 0x5a
    ja uk_clear
    mov edx, dword ptr [{KBUF:#x}]
    mov eax, dword ptr [{KBUF:#x}+4]
    shrd edx, eax, 8
    shr eax, 8
    shl ecx, 24
    or eax, ecx
    mov dword ptr [{KBUF:#x}], edx
    mov dword ptr [{KBUF:#x}+4], eax
    cmp eax, 0x52494150
    je uk_rep
    cmp eax, 0x45544144
    jne uk_ret
    shr edx, 16
    cmp edx, 0x5055
    jne uk_ret
    mov dword ptr [{KBUF:#x}], 0
    mov dword ptr [{KBUF:#x}+4], 0
    jmp startchk
uk_rep:
    shr edx, 16
    cmp edx, 0x4552
    jne uk_ret
    mov dword ptr [{KBUF:#x}], 0
    mov dword ptr [{KBUF:#x}+4], 0
    cmp dword ptr [{HASEXE:#x}], 1
    jne uk_ret
    mov esi, dword ptr [0x45a1a0]
    mov esi, dword ptr [esi]
    test esi, esi
    jz uk_ret
    mov dword ptr [{DLGWHICH:#x}], 2
    jmp showdlg
uk_clear:
    mov dword ptr [{KBUF:#x}], 0
    mov dword ptr [{KBUF:#x}+4], 0
uk_ret:
    ret

startchk:
    cmp dword ptr [{HASEXE:#x}], 1
    jne sk_ret
    cmp dword ptr [{MODE:#x}], 2
    je sk_ret
    cmp dword ptr [{CHECKING:#x}], 0
    jne sk_ret
    mov dword ptr [{CHECKING:#x}], 1
    call now
    mov dword ptr [{CHKSTART:#x}], eax
    mov eax, dword ptr [{STATUS:#x}]
    mov dword ptr [{CHKSTAT:#x}], eax
    mov esi, {LASTCHK:#x}
    mov edi, {CHKSNAP:#x}
    mov ecx, 8
    rep movsd dword ptr es:[edi], dword ptr [esi]
    mov esi, {L_pck:#x}
    mov edi, 0
    xor ecx, ecx
    call launch
sk_ret:
    ret

showdlg:
    mov eax, {MSGSTR:#x}+8
    mov edi, eax
    cmp dword ptr [{DLGWHICH:#x}], 2
    jne sd_upd
    mov eax, {L_r1:#x}
    call scat
    jmp sd_txt
sd_upd:
    cmp dword ptr [{DLGWHICH:#x}], 0
    jne sd_ask
    mov eax, {L_m1:#x}
    call scat
    call scatver
    mov eax, {L_m2:#x}
    call scat
    jmp sd_txt
sd_ask:
    mov eax, {L_a1:#x}
    call scat
    call scatver
    mov eax, {L_a2:#x}
    call scat
sd_txt:
    mov byte ptr [edi], 0
    mov eax, edi
    sub eax, {MSGSTR:#x}+8
    mov dword ptr [{MSGSTR:#x}+4], eax
    mov dword ptr [{MSGSTR:#x}], 0xffffffff
    mov eax, esi
    call 0x40e7e4
    mov edx, {L_title:#x}
    cmp dword ptr [{DLGWHICH:#x}], 2
    jne sd_ttl
    mov edx, {L_rtitle:#x}
sd_ttl:
    mov eax, dword ptr [esi+0x48]
    call 0x403254
    mov eax, dword ptr [esi+0x80]
    mov eax, dword ptr [eax+0x118]
    mov edx, {MSGSTR:#x}+8
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x2c]
    mov eax, dword ptr [esi+0x80]
    mov eax, dword ptr [eax+0x118]
    mov ecx, dword ptr [eax]
    push dword ptr [ecx+0x54]
    xor ecx, ecx
    xor edx, edx
    call dword ptr [esp]
    pop ecx
    mov dl, 1
    mov eax, dword ptr [esi+0x4c]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
    xor eax, eax
    mov dword ptr [esi+0xb0], eax
    mov dword ptr [esi+0xb4], eax
    mov dword ptr [esi+0xb8], {FAKEOBJ:#x}
    mov dl, 1
    mov eax, dword ptr [esi+0x44]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
    ret

scat:
    push esi
    mov esi, eax
cat_l:
    lodsb byte ptr [esi]
    test al, al
    jz cat_e
    mov edx, edi
    sub edx, {MSGSTR:#x}+8
    cmp edx, 116
    jae cat_e
    stosb byte ptr es:[edi], al
    jmp cat_l
cat_e:
    pop esi
    ret

scatver:
    mov eax, {VERBUF:#x}
    cmp byte ptr [eax], 0
    jne scat
    mov eax, {L_nv:#x}
    jmp scat

sdraw:
    push ebp
    mov ebp, esp
    sub esp, 0x80
    mov dword ptr [ebp-4], eax
    mov dword ptr [ebp-8], edx
    test edx, edx
    jz sw_out
    mov ecx, dword ptr [edx+0x5c]
    test ecx, ecx
    jz sw_out
    mov dword ptr [ebp-0xc], ecx
    mov eax, dword ptr [ecx+0x10c]
    test eax, eax
    jz sw_out
    mov dword ptr [ebp-0x10], eax
    mov eax, dword ptr [ecx+0x84]
    add eax, dword ptr [ecx+0x7c]
    mov edx, dword ptr [ebp-0x10]
    add eax, dword ptr [edx+0x84]
    mov dword ptr [ebp-0x14], eax
    mov eax, dword ptr [ecx+0x88]
    add eax, dword ptr [edx+0x88]
    mov dword ptr [ebp-0x18], eax
    mov eax, dword ptr [ecx+0x80]
    cmp eax, 4
    jge sw_h
    mov eax, 10
sw_h:
    mov dword ptr [ebp-0x1c], eax
    mov eax, dword ptr [ecx+0x8c]
    test eax, eax
    jz sw_out
    mov dword ptr [ebp-0x2c], eax
    call gtw_init
    mov edx, dword ptr [ebp-0x18]
    sub edx, dword ptr [ebp-0x1c]
    sub edx, 2
    mov dword ptr [ebp-0x34], edx
    call state
    mov dword ptr [ebp-0x20], eax
    mov edx, {L_up:#x}
    cmp eax, 1
    je sw_rect
    cmp eax, 2
    jne sw_norect
    ; union hit rect: status line (its normal text width) + Version label text + the gap between them
    mov edx, {L_av:#x}
sw_rect:
    mov eax, dword ptr [ebp-0x2c]
    call twidth
    mov ecx, dword ptr [ebp-0x14]
    sub ecx, eax
    mov dword ptr [ebp-0x60], ecx
    mov eax, dword ptr [ebp-0xc]
    mov edx, dword ptr [ebp-0x10]
    mov ecx, dword ptr [edx+0x84]
    add ecx, dword ptr [eax+0x84]
    mov dword ptr [ebp-0x64], ecx
    mov edx, dword ptr [eax+0x90]
    test edx, edx
    jz sw_nov
    mov eax, dword ptr [ebp-0x2c]
    call twidth
    add eax, dword ptr [ebp-0x64]
    jmp sw_vx
sw_nov:
    mov eax, dword ptr [ebp-0x64]
sw_vx:
    mov dword ptr [ebp-0x68], eax
    mov eax, dword ptr [ebp-0x60]
    cmp eax, dword ptr [ebp-0x64]
    jle sw_r1
    mov eax, dword ptr [ebp-0x64]
sw_r1:
    sub eax, 3
    mov dword ptr [{RECT:#x}], eax
    mov eax, dword ptr [ebp-0x34]
    sub eax, 3
    mov dword ptr [{RECT:#x}+4], eax
    mov eax, dword ptr [ebp-0x14]
    cmp eax, dword ptr [ebp-0x68]
    jge sw_r2
    mov eax, dword ptr [ebp-0x68]
sw_r2:
    add eax, 3
    mov dword ptr [{RECT:#x}+8], eax
    mov eax, dword ptr [ebp-0x18]
    add eax, dword ptr [ebp-0x1c]
    add eax, 2
    mov dword ptr [{RECT:#x}+12], eax
sw_norect:
    xor edx, edx
    mov eax, dword ptr [ebp-0x20]
    cmp eax, 1
    je sw_hv
    cmp eax, 2
    jne sw_hov
sw_hv:
    mov ecx, dword ptr [0x45a1a0]
    mov ecx, dword ptr [ecx]
    test ecx, ecx
    jz sw_hov
    cmp dword ptr [ecx+0xb8], 0
    jne sw_hov
    mov ecx, dword ptr [ebp-8]
    mov eax, dword ptr [ecx+0x70]
    cmp eax, dword ptr [{RECT:#x}]
    jl sw_hov
    cmp eax, dword ptr [{RECT:#x}+8]
    jg sw_hov
    mov eax, dword ptr [ecx+0x74]
    cmp eax, dword ptr [{RECT:#x}+4]
    jl sw_hov
    cmp eax, dword ptr [{RECT:#x}+12]
    jg sw_hov
    mov edx, 1
sw_hov:
    mov dword ptr [{HOVER:#x}], edx
    mov eax, dword ptr [ebp-0x20]
    lea eax, [eax*2+edx]
    mov dword ptr [ebp-0x54], eax
    call now
    mov dword ptr [ebp-0x58], eax
    mov eax, dword ptr [ebp-0x54]
    cmp eax, dword ptr [{NEWID:#x}]
    je sw_noch
    mov ecx, dword ptr [{NEWID:#x}]
    mov dword ptr [{OLDID:#x}], ecx
    mov dword ptr [{NEWID:#x}], eax
    mov eax, dword ptr [ebp-0x58]
    mov dword ptr [{TSTART:#x}], eax
    mov dword ptr [{ANIM:#x}], 1
    cmp ecx, 2
    jae sw_noch
    sub dword ptr [{TSTART:#x}], {OUTDUR}
sw_noch:
    mov eax, dword ptr [{NEWID:#x}]
    mov dword ptr [ebp-0x70], eax
    mov dword ptr [ebp-0x74], 256
    cmp dword ptr [{ANIM:#x}], 0
    je sw_static
    mov eax, dword ptr [ebp-0x58]
    sub eax, dword ptr [{TSTART:#x}]
    cmp eax, {OUTDUR}
    jae sw_in
    mov ecx, dword ptr [{OLDID:#x}]
    mov dword ptr [ebp-0x70], ecx
    shl eax, 8
    xor edx, edx
    mov ecx, {OUTDUR}
    div ecx
    mov ecx, 256
    sub ecx, eax
    mov dword ptr [ebp-0x74], ecx
    jmp sw_clr
sw_in:
    sub eax, {OUTDUR}
    cmp eax, {INDUR}
    jae sw_done
    shl eax, 8
    xor edx, edx
    mov ecx, {INDUR}
    div ecx
    mov dword ptr [ebp-0x74], eax
    jmp sw_clr
sw_done:
    mov dword ptr [{ANIM:#x}], 0
    mov dword ptr [{DIRTY:#x}], 3
sw_static:
    cmp dword ptr [ebp-0x70], 5
    je sw_clr
    cmp dword ptr [ebp-0x70], 3
    je sw_clr
    cmp dword ptr [{DIRTY:#x}], 0
    jle sw_draw
    dec dword ptr [{DIRTY:#x}]
sw_clr:
    call sclear
sw_draw:
    cmp dword ptr [ebp-0x70], 5
    je sw_pul
    cmp dword ptr [ebp-0x70], 3
    jne sw_pd
sw_pul:
    call now
    xor edx, edx
    mov ecx, 10000
    div ecx
    xor edx, edx
    mov ecx, 1000
    div ecx
    mov eax, edx
    sub eax, 500
    cdq
    xor eax, edx
    sub eax, edx
    imul eax, eax, {PULSE_SPAN}
    xor edx, edx
    mov ecx, 500
    div ecx
    add eax, {PULSE_MIN}
    imul eax, dword ptr [ebp-0x74]
    shr eax, 8
    mov dword ptr [ebp-0x74], eax
sw_pd:
    mov eax, dword ptr [ebp-0x70]
    shr eax, 1
    test eax, eax
    jz sw_out
    mov edx, {L_up:#x}
    mov ecx, {COL_UP:#x}
    cmp eax, 1
    jne sw_p2
    test dword ptr [ebp-0x70], 1
    jz sw_pick
    mov edx, {L_cu:#x}
    mov ecx, {COL_UPHOT:#x}
    jmp sw_pick
sw_p2:
    mov edx, {L_av:#x}
    mov ecx, {COL_AV:#x}
    cmp eax, 2
    jne sw_p3
    test dword ptr [ebp-0x70], 1
    jz sw_pick
    mov edx, {L_dl:#x}
    mov ecx, {COL_HOT:#x}
    jmp sw_pick
sw_p3:
    mov edx, {L_rd:#x}
    mov ecx, {COL_RD:#x}
    cmp eax, 3
    je sw_pick
    mov edx, {L_ck:#x}
    mov ecx, {COL_CK:#x}
sw_pick:
    mov dword ptr [ebp-0x24], edx
    mov dword ptr [ebp-0x28], ecx
    ; colour * f / 256 per channel (fade toward the black background)
    xor ecx, ecx
    mov dword ptr [ebp-0x78], 0
sw_ch:
    mov eax, dword ptr [ebp-0x28]
    shr eax, cl
    and eax, 0xff
    imul eax, dword ptr [ebp-0x74]
    shr eax, 8
    cmp eax, 0xff
    jbe sw_ch1
    mov eax, 0xff
sw_ch1:
    shl eax, cl
    or dword ptr [ebp-0x78], eax
    add ecx, 8
    cmp ecx, 24
    jb sw_ch
    push esi
    push edi
    mov esi, dword ptr [ebp-4]
    mov edi, {SURFCOPY:#x}
    mov ecx, 15
    rep movsd dword ptr es:[edi], dword ptr [esi]
    pop edi
    pop esi
    mov edx, dword ptr [ebp-0x24]
    mov eax, dword ptr [ebp-0x2c]
    call twidth
    mov ecx, dword ptr [ebp-0x14]
    sub ecx, eax
    mov dword ptr [ebp-0x30], ecx
    mov edx, dword ptr [ebp-0x78]
    mov eax, dword ptr [ebp-0x2c]
    call dword ptr [{I_SETCOLOR:#x}]
    push dword ptr [ebp-0x24]
    push {SURFCOPY:#x}
    mov edx, dword ptr [ebp-0x30]
    mov ecx, dword ptr [ebp-0x34]
    mov eax, dword ptr [ebp-0x2c]
    call dword ptr [{I_SETTEXT:#x}]
sw_out:
    mov esp, ebp
    pop ebp
    ret

sclear:
    mov ebx, dword ptr [ebp-8]
    mov esi, dword ptr [ebp-4]
    mov eax, dword ptr [ebp-0x14]
    add eax, 2
    mov dword ptr [ebp-0x48], eax
    sub eax, {CLR_W}
    mov dword ptr [ebp-0x50], eax
    mov eax, dword ptr [ebp-0x18]
    mov dword ptr [ebp-0x44], eax
    sub eax, {CLR_H}
    mov dword ptr [ebp-0x4c], eax
    cmp dword ptr [ebp-0x50], 0
    jge sc_c1
    mov dword ptr [ebp-0x50], 0
sc_c1:
    cmp dword ptr [ebp-0x4c], 0
    jge sc_c2
    mov dword ptr [ebp-0x4c], 0
sc_c2:
    mov eax, dword ptr [esi]
    cmp dword ptr [ebp-0x48], eax
    jle sc_c3
    mov dword ptr [ebp-0x48], eax
sc_c3:
    mov eax, dword ptr [esi+4]
    cmp dword ptr [ebp-0x44], eax
    jle sc_c4
    mov dword ptr [ebp-0x44], eax
sc_c4:
    mov eax, dword ptr [ebp-0x48]
    cmp eax, dword ptr [ebp-0x50]
    jle sc_out
    mov eax, dword ptr [ebx+0x88]
    cmp eax, dword ptr [ebp-0x44]
    jle sc_a1
    mov eax, dword ptr [ebp-0x44]
sc_a1:
    cmp eax, dword ptr [ebp-0x4c]
    jle sc_b
    mov edx, dword ptr [ebp-0x4c]
    call sc_fill
sc_b:
    mov edx, dword ptr [ebx+0x90]
    cmp edx, dword ptr [ebp-0x4c]
    jge sc_b1
    mov edx, dword ptr [ebp-0x4c]
sc_b1:
    mov eax, dword ptr [ebp-0x44]
    cmp edx, eax
    jge sc_lbl
    call sc_fill
sc_lbl:
    mov eax, dword ptr [0x45df74]
    mov eax, dword ptr [eax]
    call 0x402894
    test al, al
    jz sc_out
    cmp byte ptr [ebx+0x95], 0
    jne sc_out
    mov edi, 0x4c
sc_l:
    mov eax, dword ptr [ebx+edi]
    test eax, eax
    jz sc_ln
    mov edx, esi
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x80]
sc_ln:
    add edi, 4
    cmp edi, 0x58
    jb sc_l
sc_out:
    ret
sc_fill:
    sub esp, 0x10
    mov ecx, dword ptr [ebp-0x50]
    mov dword ptr [esp], ecx
    mov dword ptr [esp+4], edx
    mov ecx, dword ptr [ebp-0x48]
    mov dword ptr [esp+8], ecx
    mov dword ptr [esp+12], eax
    mov eax, esp
    xor edx, edx
    mov ecx, esi
    call 0x4018cc
    add esp, 0x10
    ret

gtw_init:
    mov dword ptr [{GTWFN:#x}], 0
    mov eax, dword ptr [{I_SETTEXT:#x}]
    test eax, eax
    jz gi_out
    sub eax, 0x160
    cmp dword ptr [eax], 0x6aec8b55
    jne gi_out
    cmp dword ptr [eax+4], 0x8b565300
    jne gi_out
    cmp byte ptr [eax+8], 0xf2
    jne gi_out
    mov dword ptr [{GTWFN:#x}], eax
gi_out:
    ret

twidth:
    cmp dword ptr [{GTWFN:#x}], 0
    je tw_est
    call dword ptr [{GTWFN:#x}]
    ret
tw_est:
    mov eax, dword ptr [edx-4]
    lea eax, [eax+eax*4]
    ret
"""


def build(prev_k, prev_u, prev_d, prev_m, orig_k):
    lit, la = lits()
    fmt = {k: v for k, v in globals().items() if k.isupper() and isinstance(v, int)}
    fmt.update({"L_" + k: v for k, v in la.items()})
    src = SRC.format(**fmt)
    code = asm(src, CODE)
    assert CODE + len(code) <= ZONE_END, "code too big (%d B, room %d)" % (len(code), ZONE_END - CODE)
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    names = ["cave_draw", "cave_key", "cave_upd", "cave_mup", "cave_dest", "ret0", "e_yes", "e_close"]
    labels = {}
    for name, ins in zip(names, md.disasm(code, CODE)):
        assert ins.mnemonic == "jmp", ins
        labels[name] = int(ins.op_str, 16)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[H_ORIG_K - ZONE:H_ORIG_K - ZONE + 7] = orig_k
    struct.pack_into("<IIII", z, H_PREV_K - ZONE, prev_k, prev_u, prev_d, prev_m)
    vmt = bytearray()
    for k in range(NSLOTS):
        t = labels["ret0"]
        if k * 4 in (0x78, 0x7C, 0x84): t = labels["e_close"]
        if k * 4 == 0x80: t = labels["e_yes"]
        vmt += struct.pack("<I", t)
    assert VMT - ZONE >= 0x40 + 0x1C and VMT + len(vmt) <= FAKEOBJ
    z[VMT - ZONE:VMT - ZONE + len(vmt)] = vmt
    struct.pack_into("<I", z, FAKEOBJ - ZONE, VMT)
    z[LITS - ZONE:LITS - ZONE + len(lit)] = lit
    z[CODE - ZONE:CODE - ZONE + len(code)] = code
    return bytes(z), labels, len(code), la


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]; opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt; secs = []
    for i in range(n):
        h = tbl + 40 * i
        vs, va, rs, ro = struct.unpack_from("<IIII", d, h + 8)
        secs.append(dict(name=d[h:h + 8].rstrip(b"\0"), vs=vs, va=va, rsz=rs, raw=ro, hdr=h))
    return e, secs


def off(secs, va):
    for s in secs:
        if s["va"] <= va - BASE < s["va"] + s["rsz"]:
            return s["raw"] + va - BASE - s["va"]
    raise ValueError(hex(va))


def relocs(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    out = set()
    for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for en in b.entries:
            if en.type: out.add(en.rva + BASE)
    return out


def jmp_target(b, va):
    assert b[0] == 0xE9
    return (va + 5 + struct.unpack_from("<i", b, 1)[0]) & 0xFFFFFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    e, secs = sections(d)
    sec = next((s for s in secs if s["name"] == SEC_NAME), None)
    if sec is None or secs[-1]["name"] != SEC_NAME:
        print("ABORT: .xtut must exist and be the last section"); return 1
    soi_off = e + 24 + 56
    soi = struct.unpack_from("<I", d, soi_off)[0]
    o_x, o_k = off(secs, SITE_X), off(secs, SITE_K)
    o_u, o_d, o_m = off(secs, SITE_U), off(secs, SITE_D), off(secs, SITE_M)
    cur_x, cur_k = bytes(d[o_x:o_x + 7]), bytes(d[o_k:o_k + 7])
    cur_u, cur_d, cur_m = (struct.unpack_from("<I", d, o)[0] for o in (o_u, o_d, o_m))
    zmagic = bytes(d[sec["raw"] + ZONE - SEC_VA:sec["raw"] + ZONE - SEC_VA + 4]) \
        if sec["rsz"] >= ZONE_END - BASE - sec["va"] else b""
    applied = zmagic == MAGIC
    v1 = zmagic in (MAGIC_V1, MAGIC_V2, MAGIC_V3, MAGIC_V4)
    if applied or v1:
        zo = sec["raw"] + ZONE - SEC_VA
        zone = bytes(d[zo:zo + (ZONE_END - ZONE)])
        orig_k = zone[H_ORIG_K - ZONE:H_ORIG_K - ZONE + 7]
        prev_k, prev_u, prev_d, prev_m = struct.unpack_from("<IIII", zone, H_PREV_K - ZONE)
    else:
        if sec["rsz"] != RAW_OLD or sec["vs"] != VS_OLD or soi != SEC_VA - BASE + VS_OLD \
                or len(d) != sec["raw"] + sec["rsz"]:
            print("ABORT: expected .xtut raw %#x / VS %#x / SizeOfImage %#x and no overlay (got raw %#x VS %#x SOI %#x)"
                  % (RAW_OLD, VS_OLD, SEC_VA - BASE + VS_OLD, sec["rsz"], sec["vs"], soi)); return 1
        if bytes(d[off(secs, TTQ3_MAGIC_VA):off(secs, TTQ3_MAGIC_VA) + 4]) != b"TTQ3":
            print("ABORT: title quotes v3 (TTQ3) must be applied first"); return 1
        if cur_x != SITE_X_ORIG:
            print("ABORT: draw site %#x is not vanilla (%s)" % (SITE_X, cur_x.hex())); return 1
        if cur_k[0] != 0xE9 or cur_k[5:] != b"\x90\x90":
            print("ABORT: key site %#x is not title-quotes' jmp (%s)" % (SITE_K, cur_k.hex())); return 1
        orig_k = cur_k
        prev_k, prev_u, prev_d, prev_m = jmp_target(cur_k, SITE_K), cur_u, cur_d, cur_m
    blob, lab, clen, la = build(prev_k, prev_u, prev_d, prev_m, orig_k)
    new_x = b"\xE9" + struct.pack("<i", lab["cave_draw"] - (SITE_X + 5)) + b"\x90\x90"
    new_k = b"\xE9" + struct.pack("<i", lab["cave_key"] - (SITE_K + 5)) + b"\x90\x90"
    rl = relocs(d)
    bad_rel = [hex(r) for va, n in ((SITE_X, 7), (SITE_K, 7)) for r in rl if va - 3 <= r < va + n]
    ptr_rel = all(va in rl for va in (SITE_U, SITE_D, SITE_M))
    st = "applied" if applied else ("%s (upgrading in place)" % zmagic.decode() if v1 else "vanilla")
    print("%s\n  state: %s | .xtut raw %#x VS %#x SOI %#x | X %s K %s U %#x D %#x M %#x | prev K %#x U %#x D %#x M %#x"
          % (a.exe, st, sec["rsz"], sec["vs"], soi, cur_x.hex(), cur_k.hex(), cur_u, cur_d, cur_m,
             prev_k, prev_u, prev_d, prev_m))
    print("  code %d B @%#x (room %d) | relocs under code sites: %s | method-ptr relocs present: %s"
          % (clen, CODE, ZONE_END - CODE - clen, bad_rel or "none", ptr_rel))
    print("  entries: " + ", ".join("%s %#x" % kv for kv in lab.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(blob[CODE - ZONE:CODE - ZONE + clen], CODE):
            print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad_rel:
        print("ABORT: relocation under a code site"); return 1
    if applied:
        ok = cur_x == new_x and cur_k == new_k and (cur_u, cur_d, cur_m) == (lab["cave_upd"], lab["cave_mup"],
                                                                            lab["cave_dest"])
        zo = sec["raw"] + ZONE - SEC_VA
        same_zone = bytes(d[zo:zo + (ZONE_END - ZONE)]) == blob
        if a.revert:
            if not ok:
                print("ABORT: sites no longer point at this patch (something chained in front?) - refusing"); return 1
            d[o_x:o_x + 7] = SITE_X_ORIG
            d[o_k:o_k + 7] = orig_k
            struct.pack_into("<I", d, o_u, prev_u)
            struct.pack_into("<I", d, o_d, prev_d)
            struct.pack_into("<I", d, o_m, prev_m)
            del d[sec["raw"] + RAW_OLD:]
            struct.pack_into("<I", d, sec["hdr"] + 16, RAW_OLD)
            struct.pack_into("<I", d, sec["hdr"] + 8, VS_OLD)
            struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_OLD)
            with open(a.exe, "wb") as f: f.write(d)
            print("reverted (raw %#x, VS %#x, SizeOfImage %#x)" % (RAW_OLD, VS_OLD, SEC_VA - BASE + VS_OLD)); return 0
        if ok and same_zone:
            print("already applied"); return 0
        # v5.1 (11/01, user: "repair command broken" - AV 0x40E80E reading [nil+0x88]): the REPAIR path passed the
        # title scene to showdlg instead of the dialog object [[0x45A1A0]] the other two paths use.  The entry labels
        # are unchanged, so a code-only update of the zone is safe when every hook still points at our labels.
        # (cave_upd/mup/dest pointers may have later patches chained in front - compare them against the labels OR
        # accept a foreign target, exactly as the v4->v5 upgrade does.)
        sites_ok = cur_x == new_x and cur_k == new_k
        if sites_ok and same_zone:
            print("already applied (v5.1)"); return 0
        if sites_ok and len(blob) == ZONE_END - ZONE:
            print("  zone code update (v5.1 REPAIR fix)")
            if not a.apply:
                print("Dry run OK - rerun with --apply."); return 0
            if os.path.abspath(a.exe) == os.path.abspath(DEFAULT_EXE):
                bak = bak_path(a.exe, ".bak_updtitle51")
                if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
            d[zo:zo + len(blob)] = blob
            with open(a.exe, "wb") as f: f.write(d)
            assert open(a.exe, "rb").read() == bytes(d)
            print("Written and verified (v5.1)."); return 0
        print("ABORT: partially applied / zone differs - revert first"); return 1
    if v1:
        ok1 = cur_x[0] == 0xE9 and cur_k[0] == 0xE9 and ZONE <= jmp_target(cur_x, SITE_X) < ZONE_END \
            and ZONE <= jmp_target(cur_k, SITE_K) < ZONE_END
        # v5: later patches may have chained in FRONT of our U / D / M handlers (their prev = our v4 labels) ->
        # leave those pointers alone, but only if the v5 labels they lead to are unchanged from v4
        import patch_exe_updater_title_v4 as V4
        _b4, lab4, _c4, _l4 = V4.build(prev_k, prev_u, prev_d, prev_m, orig_k)
        for kk in ("cave_upd", "cave_mup", "cave_dest"):
            assert lab4[kk] == lab[kk], (kk, hex(lab4[kk]), hex(lab[kk]))
        keep = {o: not (ZONE <= v < ZONE_END) for o, v in ((o_u, cur_u), (o_d, cur_d), (o_m, cur_m))}
        if not ok1:
            print("ABORT: v1/v2/v3 zone present but sites don't point into it - revert with that script first"); return 1
        if a.revert:
            print("an older version (%s) is applied - revert it with its own script (or apply v4 first)" % zmagic.decode()); return 1
        zo = sec["raw"] + ZONE - SEC_VA
        d[zo:zo + len(blob)] = blob
        d[o_x:o_x + 7] = new_x
        d[o_k:o_k + 7] = new_k
        for o, kk in ((o_u, "cave_upd"), (o_d, "cave_mup"), (o_m, "cave_dest")):
            if not keep[o]:
                struct.pack_into("<I", d, o, lab[kk])
        print("  kept chained pointers:", [hex(o) for o, k in keep.items() if k])
        if not a.apply:
            print("Dry run OK - %s -> v5 in place; rerun with --apply." % zmagic.decode()); return 0
        if os.path.abspath(a.exe) == os.path.abspath(DEFAULT_EXE):
            bak = bak_path(a.exe, BAK_SUFFIX)
            if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
        with open(a.exe, "wb") as f: f.write(d)
        assert open(a.exe, "rb").read() == bytes(d)
        print("Written and verified (%s -> v5): typed REPAIR -> Yes/No -> AoWxUpdater --repair." % zmagic.decode()); return 0
    if a.revert:
        print("nothing to revert"); return 0
    # apply
    d += bytes(RAW_NEW - RAW_OLD)
    struct.pack_into("<I", d, sec["hdr"] + 16, RAW_NEW)
    struct.pack_into("<I", d, sec["hdr"] + 8, VS_NEW)
    struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_NEW)
    zo = sec["raw"] + ZONE - SEC_VA
    d[zo:zo + len(blob)] = blob
    d[o_x:o_x + 7] = new_x
    d[o_k:o_k + 7] = new_k
    struct.pack_into("<I", d, o_u, lab["cave_upd"])
    struct.pack_into("<I", d, o_d, lab["cave_mup"])
    struct.pack_into("<I", d, o_m, lab["cave_dest"])
    print("  .xtut raw %#x -> %#x, VS %#x -> %#x, SizeOfImage -> %#x" % (RAW_OLD, RAW_NEW, VS_OLD, VS_NEW,
                                                                        SEC_VA - BASE + VS_NEW))
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.exe) == os.path.abspath(DEFAULT_EXE):
        bak = bak_path(a.exe, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "wb") as f: f.write(d)
    assert open(a.exe, "rb").read() == bytes(d)
    print("Written and verified (v4): title update status line / click-to-update / click-to-check / Ask popup / 'update' check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
