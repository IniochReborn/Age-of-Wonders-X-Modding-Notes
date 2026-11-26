#!/usr/bin/env python3
r"""
Title screen flavour quote + two title-screen easter eggs (2026-10-19).  AoWx.exe only; UI only (no game state, no game
RNG -> MP-irrelevant).

User: "flavor text on the title screen, bottom-left, same font as the game version, randomly one of the texts in
'title screen flavor text' (incl. quotation marks)" -> stored as type-1 string records in Release\easteregg.pfs
(build_easteregg_pfs.py / modding tools\aowxlib\eastereggpfs.py).  Easter eggs (ONLY while the title main menu has the
input - no modal window/dialog above it): typing  I N I O C H  -> the quote changes to another one (shuffle bag);
typing  Z I G G U R A T  -> a fake error dialog "Oh dear..." / "It's not a bug, it's a feature!" / [Okay] - Okay quits
the game through the title Quit button's own sequence.

RE (AoWx.exe):
  * TTitleScene (DFM @file 0x1E1794): +0x48 Window (TAoWUserWindow), +0x5C Version (TAOWLabel, Age8s, clGray,
    awRight/ahBottom).  TitleSceneCreate 0x41A310 sets Version via `call TAOWLabel.SetGText` @0x41A397.
    TitleSceneDestroy 0x41ADD0 is reached through its published-method-table dword @0x4193A8 (reloc'd absolute).
  * the scene draw routine paints Version via label VMT+0x80 @0x41A0AD (8B435C 8D55C4 8B08 FF9180000000; ebx =
    scene, [ebp-3C] = surface descriptor).  TAOWLabel.Draw = SetColor(font [lbl+8C], [lbl+24]); SetText(font,
    x [win+84]+[lbl+84], y [win+88]+[lbl+88], push text, push &surf), win = [lbl+10C]; +7C/+80 = width/height.
    SetText / SetColor = imports 0x45D7B8 / 0x45D7BC (Ilpack); GetTextWidth (not imported) = [0x45D7B8] - 0x160,
    accepted only if its prologue matches (55 8B EC 6A 00 53 56 8B F2), else 5 px/char.
  * Release\easteregg.pfs is read with VCL30's TMemoryStream (VMT / LoadFromFile reached via the TStringList VMT
    import 0x45D4E4 + fixed deltas, validated by the VMT self pointer); TMemoryStream +4 Memory / +8 Size.
  * keys: TGeneral.ManagerKeyDown 0x45549C (Manager.OnKeyDown = keys no window claimed; eax self, edx manager, ecx
    &VK word, ret 4).  Title has the input when Window+0x75 visible and manager+0x10C (overlay priority) <=
    Window+0xA0, and the shared TMessageDlg ([0x45A1A0], +0xB8 = active message object) is idle.
  * fake error = the shared TMessageDlg (same window the mid-game save prompt / tutorial confirm use): Reset
    0x40E7E4, +0x48 TitleLbl (SetGText 0x403254), +0x80 MessageMemo (+0x118 Lines: SetTextStr +0x2C, Insert +0x54),
    +0x68 OKBtn (text [btn+0x90], TAOWBaseButton.SetGText 0x40323C; saved + restored on close), +0x6C OKPnl,
    +0x44 Dlg; OKBtnClick calls [obj]+0x78, DlgHide calls [obj]+0x2C.  Okay = the title Quit button's code
    (0x41AFF4: hide title window, [[0x45A420]] 0x455DFC(0), [[0x45DF74]+0x6E] ? [[0x45A28C]] 0x429C14 :
    Application([[0x45A168]]).Terminate 0x40171C).

Patch:
  DRAW  0x41A0AD (14 B) -> jmp: original Version draw, then the quote word-wrapped (greedy, spaces) to
        max(120, 40 % window width) px with the Version label's font, re-wrapped when the window width changes,
        LEFT-aligned with the Version label's right margin (clamped 2..48), last line on the Version row, others
        stacked above (line height = Version height), Version colour.  Max 14 lines.
  INIT  0x41A397 (5 B) `call SetGText` -> call: SetGText, remember the scene, pick a quote.
  KEY   0x45549C (7 B, ManagerKeyDown prologue) -> jmp: title-only rolling 8-letter buffer, then the original.
  DEST  method-table dword 0x4193A8 (TitleSceneDestroy 0x41ADD0) -> wrapper: forget the scene, then the original.
  pick = load the pfs, count type-1 records (<= 512), shuffle bag (bitmap; every quote once before any repeat, no
  immediate repeat, also across refills: if the pick equals the previous quote the next unused one is taken), RDTSC random, tag-2 text (<= 480 chars), all bounds-checked; missing file =
  no quote.
.xtut: code 0x634800..0x635400 (raw 0x800 -> 0x1400), runtime data 0x635400..0x635900 (VirtualSize 0x1000 ->
0x2000, SizeOfImage 0x235000 -> 0x236000).  .xtut must be the LAST section (channeler label +0x400..+0x800,
tutorial confirm +0..+0x400).  Revert = exact (all sites, zone zeroed, raw/VS/SizeOfImage restored).  Revert this
BEFORE patch_exe_channeler_label_v2 / patch_title_tutorial_confirm_v1.
Dry-run default; --apply / --revert / --dis; --exe <scratch copy>.  Backup backup\AoWx.exe.bak_titlequotes.
Ship: AoWx.exe + Release\easteregg.pfs (build_release_zip --add Release/easteregg.pfs).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_titlequotes"
BASE = 0x400000
SEC_NAME, SEC_VA = b".xtut", 0x634000
VS_OLD, VS_NEW = 0x1000, 0x2000
ZONE, ZONE_END = 0x634800, 0x635400          # file-backed code
DATA = 0x635400                              # runtime zero data (VirtualSize tail)
MAGIC = b"TTQ1"
SITE_D, SITE_D_ORIG = 0x41A0AD, bytes.fromhex("8b435c8d55c48b08ff9180000000")
SITE_I, SITE_I_ORIG = 0x41A397, bytes.fromhex("e8b88efeff")
SITE_K, SITE_K_ORIG = 0x45549C, bytes.fromhex("558bec6a006a00")
SITE_M, SITE_M_ORIG = 0x4193A8, struct.pack("<I", 0x41ADD0)
FNAME = b"Release\\easteregg.pfs"
PFS_MAGIC, QTYPE, TAG_TEXT = 0x2144DF1C, 1, 2
VCL_TSL, VCL_TMS, VCL_TMS_LOAD = 0x4131BC98, 0x4131BFA8, 0x41320A6C   # TStringList VMT, TMemoryStream VMT, .LoadFromFile
T_TITLE, T_MSG, T_OKAY = b"Oh dear...", b"It's not a bug, it's a feature!", b"Okay"
MAXQ, MAXL, PCT, MINW, MAXLINE, MAXK = 480, 14, 40, 120, 250, 512

D = lambda o: DATA + o
QLEN, CACHEW, NL, FONT, LAST, GTW, MAXW, DELTA, PEND, WPTR, WCNT, BODY, SCENE, KPREV, UCNT, SAVEDLG, SAVEBTN = \
    (D(4 * i) for i in range(17))
KBUF = D(0x48)
USED = D(0x60)                               # MAXK bits
LINES = D(0xC0)
SURF = D(0x140)
TMPSTR = D(0x180)
QBUF = D(0x2A0)
FAKEOBJ = D(0x4A0)
assert USED + MAXK // 8 <= LINES and LINES + 8 * MAXL <= SURF and QBUF + MAXQ <= FAKEOBJ
VMT = ZONE + 0x60                            # fake message-object VMT (0x40 zero bytes in front = no parent etc.)
NSLOTS = 0x24
CODE = ZONE + 0x100
LITS = ZONE_END - 0xA0                       # literal AnsiStrings (refcount -1)

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    src = "\n".join(l.split(";")[0] for l in src.splitlines())   # keystone can hang on ';' comments
    return bytes(ks.asm(src, va)[0])


def lits():
    out = b""; addr = {}
    for name, s in (("fname", FNAME), ("title", T_TITLE), ("msg", T_MSG), ("okay", T_OKAY)):
        addr[name] = LITS + len(out) + 8
        out += struct.pack("<iI", -1, len(s)) + s + b"\0"
        out += bytes((-len(out)) % 4)
    assert LITS + len(out) <= ZONE_END
    return out, addr


SRC = r"""
    jmp cave_draw
    jmp cave_init
    jmp cave_key
    jmp cave_dest
    jmp ret0
    jmp e_release
    jmp e_ok
cave_draw:
    mov eax, dword ptr [ebx+0x5c]
    lea edx, [ebp-0x3c]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x80]
    pushad
    lea eax, [ebp-0x3c]
    mov edx, dword ptr [ebx+0x5c]
    call qdraw
    popad
    jmp 0x41a0bb
cave_init:
    mov dword ptr [{SCENE:#x}], esi
    call 0x403254
    pushad
    mov dword ptr [{KBUF:#x}], 0
    mov dword ptr [{KBUF:#x}+4], 0
    call qpick
    popad
    ret
cave_key:
    pushad
    mov eax, edx
    movzx ecx, word ptr [ecx]
    call qkey
    popad
    push ebp
    mov ebp, esp
    push 0
    push 0
    jmp 0x4554a3
cave_dest:
    mov dword ptr [{SCENE:#x}], 0
    jmp 0x41add0
ret0:
    xor eax, eax
    ret

qdraw:
    push ebp
    mov ebp, esp
    sub esp, 0x20
    mov dword ptr [ebp-4], eax
    mov dword ptr [ebp-8], edx
    cmp dword ptr [{QLEN:#x}], 0
    jle qd_out
    test edx, edx
    jz qd_out
    mov ecx, dword ptr [edx+0x10c]
    test ecx, ecx
    jz qd_out
    mov dword ptr [ebp-0xc], ecx
    mov eax, dword ptr [edx+0x8c]
    test eax, eax
    jz qd_out
    mov dword ptr [{FONT:#x}], eax
    mov eax, dword ptr [ecx+0x7c]
    cmp eax, dword ptr [{CACHEW:#x}]
    je qd_wrapped
    mov dword ptr [{CACHEW:#x}], eax
    call qwrap
qd_wrapped:
    cmp dword ptr [{NL:#x}], 0
    jle qd_out
    mov edx, dword ptr [ebp-8]
    mov ecx, dword ptr [ebp-0xc]
    mov eax, dword ptr [ecx+0x7c]
    sub eax, dword ptr [edx+0x84]
    sub eax, dword ptr [edx+0x7c]
    cmp eax, 2
    jge qd_m1
    mov eax, 2
qd_m1:
    cmp eax, 48
    jle qd_m2
    mov eax, 48
qd_m2:
    add eax, dword ptr [ecx+0x84]
    mov dword ptr [ebp-0x10], eax
    mov eax, dword ptr [ecx+0x88]
    add eax, dword ptr [edx+0x88]
    mov dword ptr [ebp-0x14], eax
    mov eax, dword ptr [edx+0x80]
    cmp eax, 4
    jge qd_h
    mov eax, 10
qd_h:
    mov dword ptr [ebp-0x18], eax
    mov edx, dword ptr [edx+0x24]
    mov eax, dword ptr [{FONT:#x}]
    call dword ptr [0x45d7bc]
    push esi
    push edi
    mov esi, dword ptr [ebp-4]
    mov edi, {SURF:#x}
    mov ecx, 15
    rep movsd dword ptr es:[edi], dword ptr [esi]
    pop edi
    pop esi
    mov dword ptr [ebp-0x1c], 0
qd_loop:
    mov eax, dword ptr [ebp-0x1c]
    cmp eax, dword ptr [{NL:#x}]
    jge qd_out
    mov edx, dword ptr [{LINES:#x}+eax*8+4]
    mov eax, dword ptr [{LINES:#x}+eax*8]
    call mksub
    mov ecx, dword ptr [{NL:#x}]
    dec ecx
    sub ecx, dword ptr [ebp-0x1c]
    imul ecx, dword ptr [ebp-0x18]
    neg ecx
    add ecx, dword ptr [ebp-0x14]
    push eax
    push {SURF:#x}
    mov edx, dword ptr [ebp-0x10]
    mov eax, dword ptr [{FONT:#x}]
    call dword ptr [0x45d7b8]
    inc dword ptr [ebp-0x1c]
    jmp qd_loop
qd_out:
    mov esp, ebp
    pop ebp
    ret

mksub:
    push esi
    push edi
    cmp edx, {MAXLINE}
    jbe ms_1
    mov edx, {MAXLINE}
ms_1:
    test edx, edx
    jge ms_2
    xor edx, edx
ms_2:
    mov dword ptr [{TMPSTR:#x}], 0xffffffff
    mov dword ptr [{TMPSTR:#x}+4], edx
    lea esi, [{QBUF:#x}+eax]
    mov edi, {TMPSTR:#x}+8
    mov ecx, edx
    rep movsb byte ptr es:[edi], byte ptr [esi]
    mov byte ptr [edi], 0
    mov eax, {TMPSTR:#x}+8
    pop edi
    pop esi
    ret

qwidth:
    cmp dword ptr [{GTW:#x}], 0
    jne qw_real
    lea eax, [edx+edx*4]
    ret
qw_real:
    call mksub
    mov edx, eax
    mov eax, dword ptr [{FONT:#x}]
    call dword ptr [{GTW:#x}]
    ret

qwrap:
    push ebp
    mov ebp, esp
    sub esp, 0x10
    push ebx
    push esi
    push edi
    mov eax, dword ptr [{CACHEW:#x}]
    imul eax, eax, {PCT}
    mov ecx, 100
    cdq
    idiv ecx
    cmp eax, {MINW}
    jge qr_w
    mov eax, {MINW}
qr_w:
    mov dword ptr [{MAXW:#x}], eax
    mov dword ptr [{GTW:#x}], 0
    mov eax, dword ptr [0x45d7b8]
    test eax, eax
    jz qr_g
    sub eax, 0x160
    cmp dword ptr [eax], 0x6aec8b55
    jne qr_g
    cmp dword ptr [eax+4], 0x8b565300
    jne qr_g
    cmp byte ptr [eax+8], 0xf2
    jne qr_g
    mov dword ptr [{GTW:#x}], eax
qr_g:
    mov dword ptr [{NL:#x}], 0
    xor esi, esi
wr_line:
    cmp dword ptr [{NL:#x}], {MAXL}
    jge wr_done
wr_skip:
    cmp esi, dword ptr [{QLEN:#x}]
    jge wr_done
    cmp byte ptr [{QBUF:#x}+esi], 0x20
    jne wr_start
    inc esi
    jmp wr_skip
wr_start:
    mov dword ptr [ebp-4], esi
    mov dword ptr [ebp-8], 0xffffffff
    mov edi, esi
wr_word:
    mov ebx, edi
wr_find:
    cmp ebx, dword ptr [{QLEN:#x}]
    jge wr_found
    cmp byte ptr [{QBUF:#x}+ebx], 0x20
    je wr_found
    inc ebx
    jmp wr_find
wr_found:
    mov eax, dword ptr [ebp-4]
    mov edx, ebx
    sub edx, eax
    call qwidth
    cmp eax, dword ptr [{MAXW:#x}]
    jg wr_over
    mov dword ptr [ebp-8], ebx
    cmp ebx, dword ptr [{QLEN:#x}]
    jge wr_emit
    lea edi, [ebx+1]
    jmp wr_word
wr_over:
    cmp dword ptr [ebp-8], 0xffffffff
    jne wr_emit
    mov dword ptr [ebp-8], ebx
wr_emit:
    mov eax, dword ptr [{NL:#x}]
    mov edx, dword ptr [ebp-4]
    mov dword ptr [{LINES:#x}+eax*8], edx
    mov ecx, dword ptr [ebp-8]
    sub ecx, edx
    mov dword ptr [{LINES:#x}+eax*8+4], ecx
    inc dword ptr [{NL:#x}]
    mov esi, dword ptr [ebp-8]
    jmp wr_line
wr_done:
    pop edi
    pop esi
    pop ebx
    mov esp, ebp
    pop ebp
    ret

qpick:
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    xor eax, eax
    mov dword ptr [{QLEN:#x}], eax
    mov dword ptr [{NL:#x}], eax
    mov dword ptr [{CACHEW:#x}], 0xffffffff
    push 0
    push 0x80
    push 3
    push 0
    push 1
    push 0x80000000
    push {L_fname:#x}
    call dword ptr [0x45d3cc]
    cmp eax, 0xffffffff
    je qp_out
    push eax
    call dword ptr [0x45d3d4]
    mov eax, dword ptr [0x45d4e4]
    sub eax, {VCL_TSL:#x}
    mov dword ptr [{DELTA:#x}], eax
    lea ecx, [eax+{VCL_TMS:#x}]
    cmp dword ptr [ecx-0x40], ecx
    jne qp_out
    mov dl, 1
    mov eax, ecx
    call 0x401058
    mov ebx, eax
    test ebx, ebx
    jz qp_out
    mov edx, {L_fname:#x}
    mov eax, ebx
    mov ecx, dword ptr [{DELTA:#x}]
    add ecx, {VCL_TMS_LOAD:#x}
    call ecx
    mov esi, dword ptr [ebx+4]
    mov edi, dword ptr [ebx+8]
    test esi, esi
    jz qp_free
    cmp edi, 16
    jl qp_free
    add edi, esi
    mov dword ptr [{PEND:#x}], edi
    cmp dword ptr [esi], {PFS_MAGIC:#x}
    jne qp_free
    movzx eax, byte ptr [esi+7]
    lea ecx, [esi+8]
    xor edx, edx
    test al, 0x80
    jz qp_nw
    mov edx, dword ptr [ecx]
    add ecx, 4
qp_nw:
    and eax, 0x7f
    lea ecx, [ecx+eax*2]
    mov dword ptr [{WPTR:#x}], ecx
    cmp edx, 0x4000
    ja qp_free
    lea eax, [ecx+edx*8]
    cmp eax, edi
    ja qp_free
    mov dword ptr [{BODY:#x}], eax
    mov dword ptr [{WCNT:#x}], edx
    xor eax, eax
    xor ecx, ecx
    mov edi, dword ptr [{WPTR:#x}]
qp_cnt:
    cmp ecx, edx
    jge qp_cnt_done
    cmp word ptr [edi+ecx*8+2], {QTYPE}
    jne qp_cnt_n
    inc eax
qp_cnt_n:
    inc ecx
    jmp qp_cnt
qp_cnt_done:
    cmp eax, {MAXK}
    jbe qp_k
    mov eax, {MAXK}
qp_k:
    mov esi, eax
    test esi, esi
    jle qp_free
    cmp esi, dword ptr [{KPREV:#x}]
    je qp_same
    mov dword ptr [{KPREV:#x}], esi
    call bag_clear
qp_same:
    cmp dword ptr [{UCNT:#x}], esi
    jb qp_have
    call bag_clear
qp_have:
    mov ecx, esi
    sub ecx, dword ptr [{UCNT:#x}]
    jle qp_free
    rdtsc
    xor eax, edx
    rol eax, 13
    xor edx, edx
    div ecx
    xor edi, edi
qp_walk:
    cmp edi, esi
    jae qp_free
    bt dword ptr [{USED:#x}], edi
    jc qp_walk_n
    test edx, edx
    jz qp_chosen
    dec edx
qp_walk_n:
    inc edi
    jmp qp_walk
qp_chosen:
    mov eax, dword ptr [{LAST:#x}]
    dec eax
    cmp eax, edi
    jne qp_mark
    cmp ecx, 1
    jle qp_mark
qp_next:
    inc edi
    cmp edi, esi
    jb qp_nn
    xor edi, edi
qp_nn:
    bt dword ptr [{USED:#x}], edi
    jc qp_next
qp_mark:
    bts dword ptr [{USED:#x}], edi
    inc dword ptr [{UCNT:#x}]
    lea eax, [edi+1]
    mov dword ptr [{LAST:#x}], eax
    xor ecx, ecx
    mov esi, dword ptr [{WPTR:#x}]
qp_find:
    cmp ecx, dword ptr [{WCNT:#x}]
    jge qp_free
    cmp word ptr [esi+ecx*8+2], {QTYPE}
    jne qp_find_n
    test edi, edi
    jz qp_found
    dec edi
qp_find_n:
    inc ecx
    jmp qp_find
qp_found:
    mov esi, dword ptr [esi+ecx*8+4]
    add esi, dword ptr [{BODY:#x}]
    jc qp_free
    mov edi, dword ptr [{PEND:#x}]
    lea eax, [esi+1]
    cmp eax, edi
    ja qp_free
    movzx ecx, byte ptr [esi]
    and ecx, 0x7f
    lea eax, [esi+ecx*2+1]
    cmp eax, edi
    ja qp_free
    xor edx, edx
qp_tag:
    cmp edx, ecx
    jge qp_free
    cmp byte ptr [esi+edx*2+1], {TAG_TEXT}
    je qp_tagok
    inc edx
    jmp qp_tag
qp_tagok:
    movzx edx, byte ptr [esi+edx*2+2]
    add eax, edx
    lea edx, [eax+4]
    cmp edx, edi
    ja qp_free
    mov ecx, dword ptr [eax]
    add edx, ecx
    jc qp_free
    cmp edx, edi
    ja qp_free
    test ecx, ecx
    jle qp_free
    cmp ecx, {MAXQ}
    jbe qp_len
    mov ecx, {MAXQ}
qp_len:
    mov dword ptr [{QLEN:#x}], ecx
    lea esi, [eax+4]
    mov edi, {QBUF:#x}
    rep movsb byte ptr es:[edi], byte ptr [esi]
qp_free:
    mov eax, ebx
    mov dl, 1
    mov ecx, dword ptr [eax]
    call dword ptr [ecx-4]
qp_out:
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret

bag_clear:
    push edi
    push ecx
    push eax
    mov edi, {USED:#x}
    mov ecx, {USEDDW}
    xor eax, eax
    rep stosd dword ptr es:[edi], eax
    mov dword ptr [{UCNT:#x}], 0
    pop eax
    pop ecx
    pop edi
    ret

qkey:
    mov edx, dword ptr [{SCENE:#x}]
    test edx, edx
    jz k_ret
    mov edx, dword ptr [edx+0x48]
    test edx, edx
    jz k_ret
    cmp byte ptr [edx+0x75], 0
    je k_ret
    mov edx, dword ptr [edx+0xa0]
    cmp dword ptr [eax+0x10c], edx
    jg k_ret
    mov edx, dword ptr [0x45a1a0]
    mov edx, dword ptr [edx]
    test edx, edx
    jz k_1
    cmp dword ptr [edx+0xb8], 0
    jne k_ret
k_1:
    cmp ecx, 0x41
    jb k_reset
    cmp ecx, 0x5a
    ja k_reset
    mov edx, dword ptr [{KBUF:#x}]
    mov eax, dword ptr [{KBUF:#x}+4]
    shrd edx, eax, 8
    shr eax, 8
    shl ecx, 24
    or eax, ecx
    mov dword ptr [{KBUF:#x}], edx
    mov dword ptr [{KBUF:#x}+4], eax
    cmp edx, 0x4747495a
    jne k_2
    cmp eax, 0x54415255
    jne k_2
    call k_clear
    jmp qerr
k_2:
    cmp eax, 0x48434f49
    jne k_ret
    shr edx, 16
    cmp edx, 0x4e49
    jne k_ret
    call k_clear
    jmp qpick
k_reset:
k_clear:
    mov dword ptr [{KBUF:#x}], 0
    mov dword ptr [{KBUF:#x}+4], 0
k_ret:
    ret

qerr:
    push esi
    push ebx
    mov esi, dword ptr [0x45a1a0]
    mov esi, dword ptr [esi]
    test esi, esi
    jz qe_out
    cmp dword ptr [esi+0xb8], 0
    jne qe_out
    mov eax, esi
    call 0x40e7e4
    mov edx, {L_title:#x}
    mov eax, dword ptr [esi+0x48]
    call 0x403254
    mov eax, dword ptr [esi+0x80]
    mov eax, dword ptr [eax+0x118]
    mov edx, {L_msg:#x}
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
    mov ebx, dword ptr [esi+0x68]
    test ebx, ebx
    jz qe_nobtn
    mov eax, {SAVEBTN:#x}
    mov edx, dword ptr [ebx+0x90]
    call dword ptr [0x45d318]
    mov dword ptr [{SAVEDLG:#x}], esi
    mov edx, {L_okay:#x}
    mov eax, ebx
    call 0x40323c
qe_nobtn:
    mov dl, 1
    mov eax, dword ptr [esi+0x6c]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
    mov dword ptr [{FAKEOBJ:#x}], {VMT:#x}
    xor eax, eax
    mov dword ptr [esi+0xb0], eax
    mov dword ptr [esi+0xb4], eax
    mov dword ptr [esi+0xb8], {FAKEOBJ:#x}
    mov dl, 1
    mov eax, dword ptr [esi+0x44]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
qe_out:
    pop ebx
    pop esi
    ret

e_release:
    mov eax, dword ptr [{SAVEDLG:#x}]
    test eax, eax
    jz er_out
    mov dword ptr [{SAVEDLG:#x}], 0
    mov eax, dword ptr [eax+0x68]
    test eax, eax
    jz er_clr
    mov edx, dword ptr [{SAVEBTN:#x}]
    call 0x40323c
er_clr:
    mov eax, {SAVEBTN:#x}
    call dword ptr [0x45d320]
er_out:
    xor eax, eax
    ret

e_ok:
    push ebx
    mov ebx, dword ptr [{SCENE:#x}]
    test ebx, ebx
    jz eo_term
    mov eax, dword ptr [ebx+0x48]
    test eax, eax
    jz eo_x
    xor edx, edx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx+0x6c]
eo_x:
    mov eax, dword ptr [0x45a420]
    mov eax, dword ptr [eax]
    xor edx, edx
    call 0x455dfc
    mov eax, dword ptr [0x45df74]
    mov eax, dword ptr [eax]
    cmp byte ptr [eax+0x6e], 0
    je eo_term
    mov eax, dword ptr [0x45a28c]
    mov eax, dword ptr [eax]
    call 0x429c14
    jmp eo_done
eo_term:
    mov eax, dword ptr [0x45a168]
    mov eax, dword ptr [eax]
    call 0x40171c
eo_done:
    pop ebx
    mov al, 1
    ret
"""

def build():
    lit, la = lits()
    fmt = dict(SCENE=SCENE, KBUF=KBUF, QLEN=QLEN, CACHEW=CACHEW, NL=NL, FONT=FONT, LAST=LAST, GTW=GTW, MAXW=MAXW,
               DELTA=DELTA, PEND=PEND, WPTR=WPTR, WCNT=WCNT, BODY=BODY, KPREV=KPREV, UCNT=UCNT, SAVEDLG=SAVEDLG,
               SAVEBTN=SAVEBTN, USED=USED, USEDDW=MAXK // 32, LINES=LINES, SURF=SURF, TMPSTR=TMPSTR, QBUF=QBUF,
               FAKEOBJ=FAKEOBJ, VMT=VMT, MAXQ=MAXQ, MAXL=MAXL, PCT=PCT, MINW=MINW, MAXLINE=MAXLINE, MAXK=MAXK,
               PFS_MAGIC=PFS_MAGIC, QTYPE=QTYPE, TAG_TEXT=TAG_TEXT, VCL_TSL=VCL_TSL, VCL_TMS=VCL_TMS,
               VCL_TMS_LOAD=VCL_TMS_LOAD, L_fname=la["fname"], L_title=la["title"], L_msg=la["msg"],
               L_okay=la["okay"])
    src = SRC.format(**fmt)
    code = asm(src, CODE)
    assert CODE + len(code) <= LITS, "code too big (%d B, room %d)" % (len(code), LITS - CODE)
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    labels = {}
    names = ["cave_draw", "cave_init", "cave_key", "cave_dest", "ret0", "e_release", "e_ok"]
    for name, ins in zip(names, md.disasm(code, CODE)):
        assert ins.mnemonic == "jmp", ins
        labels[name] = int(ins.op_str, 16)
    vmt = bytearray()
    for k in range(NSLOTS):
        tgt = labels["ret0"]
        if k * 4 == 0x78: tgt = labels["e_ok"]
        if k * 4 == 0x2C: tgt = labels["e_release"]
        vmt += struct.pack("<I", tgt)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[0x04:0x04 + 14] = SITE_D_ORIG
    z[0x12:0x12 + 5] = SITE_I_ORIG
    z[0x17:0x17 + 7] = SITE_K_ORIG
    z[0x1E:0x1E + 2] = b"\x00\x00"
    assert VMT - ZONE >= 0x60 and VMT + len(vmt) <= CODE
    z[VMT - ZONE:VMT - ZONE + len(vmt)] = vmt
    z[CODE - ZONE:CODE - ZONE + len(code)] = code
    z[LITS - ZONE:LITS - ZONE + len(lit)] = lit
    return bytes(z), labels, len(code)


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
    if sec is None:
        print("ABORT: no .xtut section (patch_title_tutorial_confirm_v1.py first)"); return 1
    last = secs[-1]["name"] == SEC_NAME
    assert sec["va"] == SEC_VA - BASE
    soi_off = e + 24 + 56
    soi = struct.unpack_from("<I", d, soi_off)[0]
    blob, lab, clen = build()
    sites = [(SITE_D, SITE_D_ORIG, b"\xE9" + struct.pack("<i", lab["cave_draw"] - (SITE_D + 5)) + b"\x90" * 9),
             (SITE_I, SITE_I_ORIG, b"\xE8" + struct.pack("<i", lab["cave_init"] - (SITE_I + 5))),
             (SITE_K, SITE_K_ORIG, b"\xE9" + struct.pack("<i", lab["cave_key"] - (SITE_K + 5)) + b"\x90" * 2),
             (SITE_M, SITE_M_ORIG, struct.pack("<I", lab["cave_dest"]))]
    st = []
    for va, orig, new in sites:
        o = off(secs, va); cur = bytes(d[o:o + len(orig)])
        st.append("ours" if cur == new else "orig" if cur == orig else "OTHER")
    have = max(0, min(sec["rsz"] - (ZONE - SEC_VA), ZONE_END - ZONE))
    zo = sec["raw"] + (ZONE - SEC_VA)
    zl = bytes(d[zo:zo + have]) + bytes((ZONE_END - ZONE) - have)
    zstate = "zero" if not any(zl) else "v1" if zl == blob else "DIFFERS"
    rl = relocs(d)
    bad_rel = [hex(r) for va, orig, _n in sites[:3] for r in rl if va - 3 <= r < va + len(orig)]
    print("%s\n  sites draw/init/key/destroy-ptr: %s | .xtut raw %#x VS %#x (last: %s) SizeOfImage %#x | zone %#x: %s "
          "(code %d B) | relocs under code sites: %s | method ptr reloc: %s"
          % (a.exe, "/".join(st), sec["rsz"], sec["vs"], last, soi, ZONE, zstate, clen, bad_rel or "none",
             SITE_M in rl))
    print("  entries: " + ", ".join("%s %#x" % kv for kv in lab.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        c = blob[CODE - ZONE:CODE - ZONE + clen]
        for i in md.disasm(c, CODE): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad_rel or "OTHER" in st or zstate == "DIFFERS" or len(set(st)) != 1 or (st[0] == "orig") != (zstate == "zero"):
        print("ABORT: unexpected site/zone combination"); return 1
    if a.revert:
        if st[0] == "orig": print("nothing to revert"); return 0
        for va, orig, _n in sites:
            o = off(secs, va); d[o:o + len(orig)] = orig
        if have: d[zo:zo + have] = bytes(have)
        if last and sec["vs"] == VS_NEW and soi == SEC_VA - BASE + VS_NEW:
            struct.pack_into("<I", d, sec["hdr"] + 8, VS_OLD)
            struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_OLD)
            print("  .xtut VS %#x -> %#x, SizeOfImage -> %#x" % (VS_NEW, VS_OLD, SEC_VA - BASE + VS_OLD))
        orig_rsz = ZONE - SEC_VA
        if last and sec["rsz"] > orig_rsz and len(d) == sec["raw"] + sec["rsz"] \
                and not any(d[sec["raw"] + orig_rsz:]):
            del d[sec["raw"] + orig_rsz:]
            struct.pack_into("<I", d, sec["hdr"] + 16, orig_rsz)
            print("  .xtut raw shrunk back to %#x" % orig_rsz)
        open(a.exe, "wb").write(d); print("reverted"); return 0
    if zstate == "v1": print("already applied"); return 0
    if not last or len(d) != sec["raw"] + sec["rsz"]:
        print("ABORT: .xtut must be the last section with no overlay"); return 1
    if sec["rsz"] != ZONE - SEC_VA or sec["vs"] != VS_OLD or soi != SEC_VA - BASE + VS_OLD:
        print("ABORT: expected .xtut raw %#x / VS %#x / SizeOfImage %#x (channeler label applied, nothing after it)"
              % (ZONE - SEC_VA, VS_OLD, SEC_VA - BASE + VS_OLD)); return 1
    d += bytes(ZONE_END - ZONE)
    struct.pack_into("<I", d, sec["hdr"] + 16, ZONE_END - SEC_VA)
    struct.pack_into("<I", d, sec["hdr"] + 8, VS_NEW)
    struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_NEW)
    print("  .xtut raw %#x -> %#x, VS %#x -> %#x, SizeOfImage -> %#x"
          % (sec["rsz"], ZONE_END - SEC_VA, VS_OLD, VS_NEW, SEC_VA - BASE + VS_NEW))
    d[zo:zo + (ZONE_END - ZONE)] = blob
    for va, _orig, new in sites:
        o = off(secs, va) if va < SEC_VA else None
        d[o:o + len(new)] = new
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.exe) == os.path.abspath(DEFAULT_EXE):
        bak = bak_path(a.exe, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    open(a.exe, "wb").write(d)
    assert open(a.exe, "rb").read() == bytes(d)
    print("Written and verified: title quote (Release\\easteregg.pfs) + 'inioch' / 'ziggurat' easter eggs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
