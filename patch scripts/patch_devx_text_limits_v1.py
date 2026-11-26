#!/usr/bin/env python3
r"""
AoWDevX.exe: longer sign / hero name / hero title text + red overflow characters (2026-10-30).

User: "drastically increase the text character limit" for signs; raise the limit for hero names and titles, and show
every character beyond the original limit in RED (editor only) so the designer knows it may not display in-game.
Decisions (user, 10/30): sign = unlimited; names + titles max 64; red from character 16 on (names were 15; titles
had no limit - the longest built-in title "the Necromancer" is 15).

Storage is not the limit: TSign text = TStrings [sign+0x30] (stream tag 7), THero name/nickname = AnsiStrings
[hero+0x60]/[hero+0x64] (stream tags 0xA/0xB).  The caps were editor controls only:
  1. TSIGNEDITFORM  TMemo SignText  MaxLength 100 -> 0 (= no limit; multiline EDIT 0x7FFFFFFE)  DFM byte @file 0xD41EC
  2. THEROEDITFORM  TEdit NameEdit  MaxLength 15  -> 64                                          DFM byte @file 0x5D819
  3. THEROEDITFORM  TComboBox NicknameEdit (title, csDropDown, no MaxLength) -> CB_LIMITTEXT 64 at FormCreate
Red overflow: THeroEditForm method table 'FormCreate' entry @0x414594 (0x415A58) -> wrap: original FormCreate, then
lazy init (user32/gdi32 resolved with LoadLibraryA/GetProcAddress borrowed from VCL30's IAT - same anchors as
patch_devx_spellcheck_v1), GetHandle(NameEdit [form+0x218]) and the title combo's edit child (GetWindow GW_CHILD of
[form+0x214]) are subclassed (old proc kept in window prop "AoWxRL"; restored on WM_NCDESTROY).
rl_proc: CallWindowProcA(old); WM_PAINT -> if text > 15 chars: GetDC + the control font, chars 15.. (not inside the
selection) re-drawn with TextOutA in RGB(255,0,0) on COLOR_WINDOW at EM_POSFROMCHAR; caret hidden meanwhile.
Typing/paste/selection/focus messages -> InvalidateRect(FALSE) when the text is over 15 (the EDIT control draws typed
text outside WM_PAINT).  Init failure -> vanilla behaviour (limits still raised).

Zone .xprn 0x4EC500..0x4ED000 (zero run 0x4EC49A..0x4ED000, before the relocated TMAINFORM DFM @0x4ED000; nothing
else claims it).  ⚠ patch_devx_prune_unused_v2.py rebuilds .xprn - re-run this after it.
Fixed base (no rebase) -> absolute addresses fine; the method-table entry's reloc stays valid (target in image).
Backup <game>\backup\AoWDevX.exe.bak_textlimits.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWDevX.exe")
BASE = 0x400000
MAGIC = b"RDL1"
SIGN_ML_FO, SIGN_ML_OLD, SIGN_ML_NEW = 0xD41EC, 100, 0
NAME_ML_FO, NAME_ML_OLD, NAME_ML_NEW = 0x5D819, 15, 64
TITLE_MAX = 64
LIMIT = 15
ENTRY_VA, ENTRY_ORIG = 0x414594, 0x415A58
F_NICK, F_NAME = 0x214, 0x218
SLOT_GETHANDLE = 0x4322E0
SLOT_FORMCREATE, VCL_FORMCREATE = 0x432210, 0x41336300
VCL_LOADLIB, VCL_GETPROC = 0x413E4360, 0x413E43B4

ZONE, ZONE_END = 0x4EC500, 0x4ED000
G_INIT = ZONE + 0x10
FP = ZONE + 0x20
FUNCS = [("user32.dll", n) for n in ("SetWindowLongA", "CallWindowProcA", "SendMessageA", "GetDC", "ReleaseDC",
                                       "InvalidateRect", "GetClientRect", "GetWindow", "SetPropA", "GetPropA",
                                       "RemovePropA", "HideCaret", "ShowCaret", "GetSysColor")] + \
        [("gdi32.dll", n) for n in ("SelectObject", "SetTextColor", "SetBkColor", "SetBkMode", "TextOutA")]
F = {n: FP + 4 * i for i, (_, n) in enumerate(FUNCS)}
RT = FP + 4 * len(FUNCS)
STR = RT + 12 * len(FUNCS) + 4
# WM_SETFOCUS KILLFOCUS SIZE SETTEXT KEYDOWN KEYUP CHAR LBUTTONDOWN LBUTTONUP CUT PASTE CLEAR UNDO EM_SETSEL
# EM_REPLACESEL EM_UNDO  (WM_MOUSEMOVE 0x200 handled separately: only while the left button is held)
INVAL_MSGS = [0x0007, 0x0008, 0x0005, 0x000C, 0x0100, 0x0101, 0x0102, 0x0201, 0x0202, 0x0300, 0x0302, 0x0303,
              0x0304, 0x00B1, 0x00C2, 0x00C7]


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<I", z, 4, ENTRY_ORIG)
    p = STR

    def put(bs):
        nonlocal p
        a = p; z[a - ZONE:a - ZONE + len(bs)] = bs; p += len(bs); return a
    strs = {}
    for dll in sorted({d for d, _ in FUNCS}):
        strs[dll] = put(dll.encode() + b"\0")
    for _, fn in FUNCS:
        strs[fn] = put(fn.encode() + b"\0")
    prop = put(b"AoWxRL\0")
    p = (p + 1) & ~1
    mtab = put(b"".join(struct.pack("<H", m) for m in INVAL_MSGS) + bytes(2))
    for i, (dll, fn) in enumerate(FUNCS):
        struct.pack_into("<III", z, RT - ZONE + 12 * i, strs[dll], strs[fn], F[fn])
    code = (p + 0xF) & ~0xF
    H = lambda v: "0x%X" % v  # noqa: E731
    f = lambda n: "dword ptr [%s]" % H(F[n])  # noqa: E731
    src = f"""
wrap:
    push ebx
    mov  ebx, eax
    call {H(ENTRY_ORIG)}
    pushad
    cmp  dword ptr [{H(G_INIT)}], 0
    jne  w_ini
    call init
w_ini:
    cmp  dword ptr [{H(G_INIT)}], 1
    jne  w_out
    mov  eax, dword ptr [ebx + {H(F_NAME)}]
    test eax, eax
    jz   w_nick
    call dword ptr [{H(SLOT_GETHANDLE)}]
    test eax, eax
    jz   w_nick
    call hook
w_nick:
    mov  eax, dword ptr [ebx + {H(F_NICK)}]
    test eax, eax
    jz   w_out
    call dword ptr [{H(SLOT_GETHANDLE)}]
    test eax, eax
    jz   w_out
    mov  esi, eax
    push 0
    push {TITLE_MAX}
    push 0x141
    push esi
    call {f('SendMessageA')}
    push 5
    push esi
    call {f('GetWindow')}
    test eax, eax
    jz   w_out
    call hook
w_out:
    popad
    pop  ebx
    ret

hook:
    push esi
    mov  esi, eax
    push {H(prop)}
    push esi
    call {f('GetPropA')}
    test eax, eax
    jnz  h_out
    push {{RLP}}
    push -4
    push esi
    call {f('SetWindowLongA')}
    test eax, eax
    jz   h_out
    push eax
    push {H(prop)}
    push esi
    call {f('SetPropA')}
h_out:
    pop  esi
    ret

init:
    pushad
    mov  dword ptr [{H(G_INIT)}], 2
    mov  eax, dword ptr [{H(SLOT_FORMCREATE)}]
    sub  eax, {H(VCL_FORMCREATE)}
    mov  ebx, dword ptr [eax + {H(VCL_LOADLIB)}]
    mov  edi, dword ptr [eax + {H(VCL_GETPROC)}]
    mov  esi, {H(RT)}
i_loop:
    mov  eax, dword ptr [esi]
    test eax, eax
    jz   i_ok
    push eax
    call ebx
    test eax, eax
    jz   i_out
    push dword ptr [esi + 4]
    push eax
    call edi
    test eax, eax
    jz   i_out
    mov  ecx, dword ptr [esi + 8]
    mov  dword ptr [ecx], eax
    add  esi, 12
    jmp  i_loop
i_ok:
    mov  dword ptr [{H(G_INIT)}], 1
i_out:
    popad
    ret

    int3
    int3
    int3
    int3
rl_proc:
    push ebp
    mov  ebp, esp
    sub  esp, 0x140
    push ebx
    push esi
    push edi
    push {H(prop)}
    push dword ptr [ebp + 8]
    call {f('GetPropA')}
    mov  edi, eax
    test edi, edi
    jz   p_zero
    cmp  dword ptr [ebp + 0xC], 0x82
    jne  p_call
    push edi
    push -4
    push dword ptr [ebp + 8]
    call {f('SetWindowLongA')}
    push {H(prop)}
    push dword ptr [ebp + 8]
    call {f('RemovePropA')}
p_call:
    push dword ptr [ebp + 0x14]
    push dword ptr [ebp + 0x10]
    push dword ptr [ebp + 0xC]
    push dword ptr [ebp + 8]
    push edi
    call {f('CallWindowProcA')}
    mov  ebx, eax
    mov  eax, dword ptr [ebp + 0xC]
    cmp  eax, 0xF
    je   o_paint
    cmp  eax, 0x200
    jne  p_list
    test dword ptr [ebp + 0x10], 1
    jnz  p_do
    jmp  p_ret
p_list:
    mov  esi, {H(mtab)}
p_l:
    movzx ecx, word ptr [esi]
    test ecx, ecx
    jz   p_ret
    cmp  ecx, eax
    je   p_do
    add  esi, 2
    jmp  p_l
p_do:
    push 0
    push 0
    push 0xE
    push dword ptr [ebp + 8]
    call {f('SendMessageA')}
    cmp  eax, {LIMIT}
    jle  p_ret
    push 0
    push 0
    push dword ptr [ebp + 8]
    call {f('InvalidateRect')}
    jmp  p_ret

o_paint:
    lea  eax, [ebp - 0x110]
    push eax
    push 0x100
    push 0xD
    push dword ptr [ebp + 8]
    call {f('SendMessageA')}
    mov  dword ptr [ebp - 0xC], eax
    cmp  eax, {LIMIT}
    jle  p_ret
    mov  dword ptr [ebp - 0x130], 0
    mov  dword ptr [ebp - 0x12C], 0
    mov  dword ptr [ebp - 8], 0
    lea  eax, [ebp - 0x12C]
    push eax
    lea  eax, [ebp - 0x130]
    push eax
    push 0xB0
    push dword ptr [ebp + 8]
    call {f('SendMessageA')}
    lea  eax, [ebp - 0x140]
    push eax
    push dword ptr [ebp + 8]
    call {f('GetClientRect')}
    push 0
    push 0
    push 0x31
    push dword ptr [ebp + 8]
    call {f('SendMessageA')}
    mov  dword ptr [ebp - 0x124], eax
    push dword ptr [ebp + 8]
    call {f('HideCaret')}
    push dword ptr [ebp + 8]
    call {f('GetDC')}
    mov  dword ptr [ebp - 0x128], eax
    test eax, eax
    jz   o_caret
    mov  eax, dword ptr [ebp - 0x124]
    test eax, eax
    jz   o_nf
    push eax
    push dword ptr [ebp - 0x128]
    call {f('SelectObject')}
    mov  dword ptr [ebp - 8], eax
o_nf:
    push 0xFF
    push dword ptr [ebp - 0x128]
    call {f('SetTextColor')}
    push 5
    call {f('GetSysColor')}
    push eax
    push dword ptr [ebp - 0x128]
    call {f('SetBkColor')}
    push 2
    push dword ptr [ebp - 0x128]
    call {f('SetBkMode')}
    mov  esi, {LIMIT}
o_loop:
    cmp  esi, dword ptr [ebp - 0xC]
    jge  o_done
    cmp  esi, dword ptr [ebp - 0x130]
    jl   o_draw
    cmp  esi, dword ptr [ebp - 0x12C]
    jl   o_next
o_draw:
    push 0
    push esi
    push 0xD6
    push dword ptr [ebp + 8]
    call {f('SendMessageA')}
    cmp  eax, -1
    je   o_next
    movsx ecx, ax
    mov  edx, eax
    sar  edx, 16
    test ecx, ecx
    js   o_next
    cmp  ecx, dword ptr [ebp - 0x138]
    jge  o_next
    lea  eax, [ebp + esi - 0x110]
    push 1
    push eax
    push edx
    push ecx
    push dword ptr [ebp - 0x128]
    call {f('TextOutA')}
o_next:
    inc  esi
    jmp  o_loop
o_done:
    mov  eax, dword ptr [ebp - 8]
    test eax, eax
    jz   o_rel
    push eax
    push dword ptr [ebp - 0x128]
    call {f('SelectObject')}
o_rel:
    push dword ptr [ebp - 0x128]
    push dword ptr [ebp + 8]
    call {f('ReleaseDC')}
o_caret:
    push dword ptr [ebp + 8]
    call {f('ShowCaret')}
p_ret:
    mov  eax, ebx
    pop  edi
    pop  esi
    pop  ebx
    mov  esp, ebp
    pop  ebp
    ret  0x10
p_zero:
    xor  ebx, ebx
    jmp  p_ret
"""
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    tmp = bytes(ks.asm(src.replace("{RLP}", "0x11111111"), code)[0])
    rlp = code + tmp.index(bytes.fromhex("cccccccc")) + 4
    src = src.replace("{RLP}", H(rlp))
    enc = bytes(ks.asm(src, code)[0])
    assert enc[rlp - code:rlp - code + 4] == tmp[rlp - code:rlp - code + 4] and enc[rlp - code] == 0x55, "rl_proc address mismatch"
    assert code + len(enc) <= ZONE_END, hex(code + len(enc))
    z[code - ZONE:code - ZONE + len(enc)] = enc
    return bytes(z), code


def game_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWDevX.exe"], capture_output=True, text=True)
        return "AoWDevX.exe" in r.stdout
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read()
    pe = pefile.PE(data=d, fast_load=True)
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone, code = build()
    eo, zo = off(ENTRY_VA), off(ZONE)
    assert d[SIGN_ML_FO - 11:SIGN_ML_FO - 1] == b"\tMaxLength" and d[SIGN_ML_FO - 1] == 2
    assert d[NAME_ML_FO - 11:NAME_ML_FO - 1] == b"\tMaxLength" and d[NAME_ML_FO - 1] == 2
    assert d[eo + 4:eo + 15] == b"\x0aFormCreate", d[eo:eo + 16]
    cur = (d[SIGN_ML_FO], d[NAME_ML_FO], struct.unpack_from("<I", d, eo)[0], d[zo:zo + len(zone)])
    van = (SIGN_ML_OLD, NAME_ML_OLD, ENTRY_ORIG, bytes(len(zone)))
    ours = (SIGN_ML_NEW, NAME_ML_NEW, code, zone)
    st = "vanilla" if cur == van else "ours" if cur == ours else "OTHER"
    print("sign MaxLength %d | name MaxLength %d | FormCreate entry %#x | zone %#x %s (code %#x, %d B) -> %s"
          % (cur[0], cur[1], cur[2], ZONE, "zero" if not any(cur[3]) else cur[3][:4], code,
             len(zone.rstrip(b"\0")), st))
    if st == "OTHER":
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if game_running():
        print("AoWDevX.exe is running - close the editor first"); return 1
    bak = bak_path(EXE, ".bak_textlimits")
    if not revert and not os.path.exists(bak):
        shutil.copy2(EXE, bak); print("backup ->", bak)
    s, n, e, zz = van if revert else ours
    try:
        with open(EXE, "r+b") as fh:                 # in-place (house rule)
            fh.seek(zo); fh.write(zz)
            fh.seek(SIGN_ML_FO); fh.write(bytes([s]))
            fh.seek(NAME_ML_FO); fh.write(bytes([n]))
            fh.seek(eo); fh.write(struct.pack("<I", e))
    except PermissionError:
        print("LOCKED - close the editor and retry"); return 1
    d2 = open(EXE, "rb").read()
    assert (d2[SIGN_ML_FO], d2[NAME_ML_FO], struct.unpack_from("<I", d2, eo)[0], d2[zo:zo + len(zz)]) == (s, n, e, zz)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
