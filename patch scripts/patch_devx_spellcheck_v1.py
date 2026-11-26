#!/usr/bin/env python3
r"""
AoWDevX.exe: red spell-check squiggles in the Spell / Ability description editor (2026-10-19).
User: "add a spellcheck red underline to text boxes in the editor - no suggestions, just the underline - specifically
for spell and ability descriptions."

Where: Spells tab 'Spell Description: Edit' (EditSpellTextClick 0x42C8DC) and Abilities tab 'Ability Description:
Edit' (EditAbilityTextClick 0x42C724) are the ONLY users of TTextEditDlg ("Text Editor", VMT 0x421644, classref cell
0x421604): `mov eax,[0x421604] / call 0x401228` (create, eax=dialog), then SetText on its TMemo at [dlg+0x1E4],
ShowModal, read the text back.  The memo is a plain Windows EDIT control.

Why not RichEdit: RICHEDIT50W + EM_SETLANGOPTIONS(IMF_SPELLCHECKING) (+ SES_USECTF/SES_CTFALLOWPROOFING) was
prototyped on this Win10 machine from an ANSI process and drew NO squiggles in any flag combination, while the
Windows spell checker itself works (ISpellChecker flags "tset"/"teh").  So the memo stays an EDIT control (zero
change to TMemo semantics) and the underline is drawn by us:

  site S1 0x42C93B / S2 0x42C783: `call 0x401228` (create the dialog) -> `call wrap`
  wrap   : call 0x401228 (original), then [lazy init], hwnd = TWinControl.GetHandle(memo) (VCL30 import slot
           0x4322E0), old = SetWindowLongA(hwnd, GWL_WNDPROC, sc_proc).  Returns the dialog in eax unchanged.
  sc_proc: r = CallWindowProcA(old, ...);  WM_PAINT -> squiggles;  edit/scroll/selection/focus messages ->
           InvalidateRect(hwnd, NULL, TRUE) (the EDIT control draws typed text outside WM_PAINT);
           WM_NCDESTROY -> restore the old proc first.  Returns r.
  squiggles: GetWindowTextA -> MultiByteToWideChar(CP_ACP) -> ISpellChecker::Check -> for each ISpellingError:
           EM_POSFROMCHAR(start) for x/y, GetTextExtentPoint32A(word) with the memo font (WM_GETFONT) for the
           width, tmHeight for the baseline -> red 1-px zigzag (CreatePen PS_SOLID 1 RGB(255,0,0), MoveToEx/LineTo)
           in a GetDC(hwnd) DC.  Rows outside the client rect are skipped.
  init   : LoadLibraryA / GetProcAddress borrowed from VCL30's IAT (vcl_delta = [0x432210] - 0x41336300;
           [0x413E4360+delta], [0x413E43B4+delta] - anchors re-verified on our files 2026-10-19), resolves the
           user32/gdi32/kernel32/ole32 functions below, LocalAlloc's an 8 KB ANSI + 16 KB wide buffer,
           CoInitialize(NULL), CoCreateInstance(SpellCheckerFactory) -> CreateSpellChecker(user default locale
           name if IsSupported, else "en-US").  Any failure -> g_init = 2 and the editor behaves exactly as vanilla.
No suggestions / context menu (the EDIT control's own context menu is untouched).  Language = the Windows user
locale (en-CA here).  Editor only (AoWDevX.exe); the game is not touched.

Zone: .xprn tail 0x4E9700..0x4EA000 (RWX; patch_devx_editor_flags_v1 owns 0x4E9650..0x4E9700, zero-verified;
⚠ patch_devx_prune_unused_v2.py rebuilds .xprn from its pristine backup - re-run this script after it).
The exe never rebases (fixed base 0x400000, DllCharacteristics 0) - absolute addresses are fine; no reloc lies on
the sites or the zone.  Backup <game>\backup\AoWDevX.exe.bak_spellchk.  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys, uuid
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWDevX.exe")
BAK = ".bak_spellchk"
BASE = 0x400000
SITES = [(0x42C93B, bytes.fromhex("e8e848fdff")), (0x42C783, bytes.fromhex("e8a04afdff"))]
T_CREATE = 0x401228
SLOT_GETHANDLE = 0x4322E0           # VCL30 Controls.TWinControl.GetHandle
SLOT_FORMCREATE, VCL_FORMCREATE = 0x432210, 0x41336300
VCL_LOADLIB, VCL_GETPROC = 0x413E4360, 0x413E43B4
MEMO_OFF = 0x1E4

ZONE, ZONE_END = 0x4E9700, 0x4EA000
MAGIC = b"SPK1"
V = ZONE + 0x10                     # variables
G_INIT, G_OLD, G_HWND, G_CHECK, G_BUF, G_WBUF, G_FACT, G_TMP = (V + 4 * i for i in range(8))
FP = ZONE + 0x30                    # resolved function pointers
FUNCS = [("kernel32.dll", "LocalAlloc"), ("kernel32.dll", "MultiByteToWideChar"),
         ("kernel32.dll", "GetUserDefaultLocaleName"),
         ("user32.dll", "SetWindowLongA"), ("user32.dll", "CallWindowProcA"), ("user32.dll", "GetWindowTextA"),
         ("user32.dll", "SendMessageA"), ("user32.dll", "GetDC"), ("user32.dll", "ReleaseDC"),
         ("user32.dll", "InvalidateRect"), ("user32.dll", "GetClientRect"),
         ("gdi32.dll", "CreatePen"), ("gdi32.dll", "SelectObject"), ("gdi32.dll", "DeleteObject"),
         ("gdi32.dll", "MoveToEx"), ("gdi32.dll", "LineTo"), ("gdi32.dll", "GetTextExtentPoint32A"),
         ("gdi32.dll", "GetTextMetricsA"),
         ("ole32.dll", "CoInitialize"), ("ole32.dll", "CoCreateInstance")]
F = {name: FP + 4 * i for i, (_, name) in enumerate(FUNCS)}
RT = FP + 4 * len(FUNCS)            # resolve table: (dll ptr, name ptr, slot) * n, 0-terminated
STR = RT + 12 * len(FUNCS) + 4
CLSID_FACT = "7AB36653-1796-484B-BDFA-E74F1DB7C1DC"
IID_FACT = "8E018A9D-2415-4677-BF08-794EA61F94BB"
BUF_N, WBUF_N = 0x2000, 0x2000      # chars

# messages that make the EDIT control redraw text outside WM_PAINT -> force a full repaint
INVAL_MSGS = [0x0007, 0x0008, 0x000C, 0x0100, 0x0102, 0x0115, 0x0114, 0x020A, 0x0202, 0x0300, 0x0302, 0x0303,
              0x0304, 0x00C2, 0x00C7, 0x00B1, 0x0005]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    src = chr(10).join(l.split(';')[0] for l in src.splitlines())
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def build():
    """-> (zone bytes, {label: va})"""
    data = bytearray(ZONE_END - ZONE)
    data[0:4] = MAGIC
    for i, (_, orig) in enumerate(SITES):
        data[4 + 5 * i:9 + 5 * i] = orig
    # strings
    p = STR
    strs = {}
    def put(b):
        nonlocal p
        a = p; data[a - ZONE:a - ZONE + len(b)] = b; p += len(b)
        return a
    for dll in sorted({d for d, _ in FUNCS}):
        strs[dll] = put(dll.encode() + b"\0")
    for _, fn in FUNCS:
        strs[fn] = put(fn.encode() + b"\0")
    p = (p + 3) & ~3
    clsid = put(uuid.UUID(CLSID_FACT).bytes_le)
    iid = put(uuid.UUID(IID_FACT).bytes_le)
    enus = put("en-US\0".encode("utf-16-le"))
    p = (p + 3) & ~3
    mtab = put(b"".join(struct.pack("<H", m) for m in INVAL_MSGS) + bytes(2))
    p = (p + 3) & ~3
    tm = put(bytes(0x40))           # TEXTMETRICA (56 B)
    rc = put(bytes(0x10))           # RECT
    sz = put(bytes(0x8))            # SIZE
    loc = put(bytes(4 * 6))         # enum, err, start, len, isSupported, spare
    L_ENUM, L_ERR, L_ST, L_LEN, L_BOOL = loc, loc + 4, loc + 8, loc + 12, loc + 16
    for i, (dll, fn) in enumerate(FUNCS):
        struct.pack_into("<III", data, RT - ZONE + 12 * i, strs[dll], strs[fn], F[fn])
    code_va = (p + 0xF) & ~0xF
    src = f"""
    wrap:
        call {T_CREATE:#x}
        pushad
        mov ebx, eax
        test ebx, ebx
        jz w_out
        cmp dword ptr [{G_INIT:#x}], 0
        jne w_inited
        call init
    w_inited:
        cmp dword ptr [{G_INIT:#x}], 1
        jne w_out
        mov eax, [ebx + {MEMO_OFF:#x}]
        test eax, eax
        jz w_out
        call dword ptr [{SLOT_GETHANDLE:#x}]
        test eax, eax
        jz w_out
        mov [{G_HWND:#x}], eax
        mov ecx, sc_proc_addr
        push ecx
        push -4
        push eax
        call dword ptr [{F['SetWindowLongA']:#x}]
        mov [{G_OLD:#x}], eax
    w_out:
        popad
        ret

    init:
        pushad
        mov dword ptr [{G_INIT:#x}], 2
        mov eax, [{SLOT_FORMCREATE:#x}]
        sub eax, {VCL_FORMCREATE:#x}
        mov ebx, [eax + {VCL_LOADLIB:#x}]
        mov edi, [eax + {VCL_GETPROC:#x}]
        mov esi, {RT:#x}
    i_loop:
        mov eax, [esi]
        test eax, eax
        jz i_res
        push eax
        call ebx
        test eax, eax
        jz i_fail
        push dword ptr [esi + 4]
        push eax
        call edi
        test eax, eax
        jz i_fail
        mov ecx, [esi + 8]
        mov [ecx], eax
        add esi, 0xC
        jmp i_loop
    i_res:
        push {BUF_N + 0x10:#x}
        push 0
        call dword ptr [{F['LocalAlloc']:#x}]
        test eax, eax
        jz i_fail
        mov [{G_BUF:#x}], eax
        push {2 * WBUF_N + 0x10:#x}
        push 0
        call dword ptr [{F['LocalAlloc']:#x}]
        test eax, eax
        jz i_fail
        mov [{G_WBUF:#x}], eax
        push 0
        call dword ptr [{F['CoInitialize']:#x}]
        push {G_FACT:#x}
        push {iid:#x}
        push 5
        push 0
        push {clsid:#x}
        call dword ptr [{F['CoCreateInstance']:#x}]
        test eax, eax
        jnz i_fail
        mov eax, [{G_FACT:#x}]
        test eax, eax
        jz i_fail
        mov esi, {enus:#x}
        push 0x55
        push dword ptr [{G_WBUF:#x}]
        call dword ptr [{F['GetUserDefaultLocaleName']:#x}]
        test eax, eax
        jz i_lang
        mov dword ptr [{L_BOOL:#x}], 0
        push {L_BOOL:#x}
        push dword ptr [{G_WBUF:#x}]
        mov eax, [{G_FACT:#x}]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x10]
        test eax, eax
        jnz i_lang
        cmp dword ptr [{L_BOOL:#x}], 0
        je i_lang
        mov esi, [{G_WBUF:#x}]
    i_lang:
        push {G_CHECK:#x}
        push esi
        mov eax, [{G_FACT:#x}]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x14]
        mov esi, eax
        mov eax, [{G_FACT:#x}]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x8]
        test esi, esi
        jnz i_fail
        cmp dword ptr [{G_CHECK:#x}], 0
        je i_fail
        mov dword ptr [{G_INIT:#x}], 1
    i_fail:
        popad
        ret

    sc_proc:
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        mov eax, [ebp + 0xC]
        cmp eax, 0x82
        jne sc_call
        push dword ptr [{G_OLD:#x}]
        push -4
        push dword ptr [ebp + 0x8]
        call dword ptr [{F['SetWindowLongA']:#x}]
        mov dword ptr [{G_HWND:#x}], 0
    sc_call:
        push dword ptr [ebp + 0x14]
        push dword ptr [ebp + 0x10]
        push dword ptr [ebp + 0xC]
        push dword ptr [ebp + 0x8]
        push dword ptr [{G_OLD:#x}]
        call dword ptr [{F['CallWindowProcA']:#x}]
        mov esi, eax
        mov eax, [ebp + 0xC]
        cmp eax, 0xF
        jne sc_chk
        push dword ptr [ebp + 0x8]
        call squig
        jmp sc_done
    sc_chk:
        cmp eax, 0x200
        jne sc_chk2
        test dword ptr [ebp + 0x10], 1
        jnz sc_inval
        jmp sc_done
    sc_chk2:
        mov edx, {mtab:#x}
    sc_tab:
        movzx ecx, word ptr [edx]
        test ecx, ecx
        jz sc_done
        add edx, 0x2
        cmp eax, ecx
        jne sc_tab
    sc_inval:
        push 1
        push 0
        push dword ptr [ebp + 0x8]
        call dword ptr [{F['InvalidateRect']:#x}]
    sc_done:
        mov eax, esi
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10

    squig:
        push ebp
        mov ebp, esp
        sub esp, 0x20
        pushad
        cmp dword ptr [{G_INIT:#x}], 1
        jne q_out
        mov ebx, [ebp + 0x8]
        push {BUF_N - 1:#x}
        push dword ptr [{G_BUF:#x}]
        push ebx
        call dword ptr [{F['GetWindowTextA']:#x}]
        test eax, eax
        jle q_out
        mov edi, eax
        push {WBUF_N - 1:#x}
        push dword ptr [{G_WBUF:#x}]
        push edi
        push dword ptr [{G_BUF:#x}]
        push 0
        push 0
        call dword ptr [{F['MultiByteToWideChar']:#x}]
        test eax, eax
        jle q_out
        mov ecx, [{G_WBUF:#x}]
        mov word ptr [ecx + eax*2], 0
        mov dword ptr [{L_ENUM:#x}], 0
        push {L_ENUM:#x}
        push dword ptr [{G_WBUF:#x}]
        mov eax, [{G_CHECK:#x}]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x10]
        test eax, eax
        jnz q_out
        cmp dword ptr [{L_ENUM:#x}], 0
        je q_out
        push ebx
        call dword ptr [{F['GetDC']:#x}]
        test eax, eax
        jz q_rel_enum
        mov [ebp - 0x4], eax
        push 0
        push 0
        push 0x31
        push ebx
        call dword ptr [{F['SendMessageA']:#x}]
        mov dword ptr [ebp - 0x8], 0
        test eax, eax
        jz q_nofont
        push eax
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['SelectObject']:#x}]
        mov [ebp - 0x8], eax
    q_nofont:
        mov dword ptr [{tm:#x}], 0
        push {tm:#x}
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['GetTextMetricsA']:#x}]
        push {rc:#x}
        push ebx
        call dword ptr [{F['GetClientRect']:#x}]
        push 0xFF
        push 1
        push 0
        call dword ptr [{F['CreatePen']:#x}]
        mov [ebp - 0xC], eax
        push eax
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['SelectObject']:#x}]
        mov [ebp - 0x10], eax
    q_loop:
        mov dword ptr [{L_ERR:#x}], 0
        push {L_ERR:#x}
        mov eax, [{L_ENUM:#x}]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0xC]
        test eax, eax
        jnz q_done
        mov esi, [{L_ERR:#x}]
        test esi, esi
        jz q_done
        mov dword ptr [{L_ST:#x}], 0
        mov dword ptr [{L_LEN:#x}], 0
        push {L_ST:#x}
        push esi
        mov eax, [esi]
        call dword ptr [eax + 0xC]
        push {L_LEN:#x}
        push esi
        mov eax, [esi]
        call dword ptr [eax + 0x10]
        push esi
        mov eax, [esi]
        call dword ptr [eax + 0x8]
        mov eax, [{L_LEN:#x}]
        test eax, eax
        jle q_loop
        mov ecx, [{L_ST:#x}]
        cmp ecx, edi
        jae q_loop
        add eax, ecx
        cmp eax, edi
        jbe q_lenok
        mov eax, edi
        sub eax, ecx
        mov [{L_LEN:#x}], eax
    q_lenok:
        push 0
        push ecx
        push 0xD6
        push ebx
        call dword ptr [{F['SendMessageA']:#x}]
        cmp eax, -1
        je q_loop
        movsx edx, ax
        mov [ebp - 0x14], edx
        sar eax, 0x10
        mov [ebp - 0x18], eax
        test eax, eax
        js q_loop
        add eax, [{tm:#x}]
        sub eax, 0x2
        mov [ebp - 0x1C], eax
        add eax, 0x2
        cmp eax, [{rc + 0xC:#x}]
        jg q_loop
        mov dword ptr [{sz:#x}], 0
        push {sz:#x}
        push dword ptr [{L_LEN:#x}]
        mov eax, [{G_BUF:#x}]
        add eax, [{L_ST:#x}]
        push eax
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['GetTextExtentPoint32A']:#x}]
        mov eax, [ebp - 0x14]
        add eax, [{sz:#x}]
        mov [ebp - 0x20], eax
        push 0
        mov eax, [ebp - 0x1C]
        add eax, 0x2
        push eax
        push dword ptr [ebp - 0x14]
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['MoveToEx']:#x}]
        xor esi, esi
    q_zig:
        mov eax, [ebp - 0x14]
        add eax, 0x2
        mov [ebp - 0x14], eax
        cmp eax, [ebp - 0x20]
        jg q_loop
        xor esi, 1
        mov ecx, [ebp - 0x1C]
        test esi, esi
        jnz q_up
        add ecx, 0x2
    q_up:
        push ecx
        push eax
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['LineTo']:#x}]
        jmp q_zig
    q_done:
        push dword ptr [ebp - 0x10]
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['SelectObject']:#x}]
        push dword ptr [ebp - 0xC]
        call dword ptr [{F['DeleteObject']:#x}]
        mov eax, [ebp - 0x8]
        test eax, eax
        jz q_rdc
        push eax
        push dword ptr [ebp - 0x4]
        call dword ptr [{F['SelectObject']:#x}]
    q_rdc:
        push dword ptr [ebp - 0x4]
        push ebx
        call dword ptr [{F['ReleaseDC']:#x}]
    q_rel_enum:
        mov eax, [{L_ENUM:#x}]
        push eax
        mov eax, [eax]
        call dword ptr [eax + 0x8]
    q_out:
        popad
        leave
        ret 4
    """
    # two passes: first to learn sc_proc's address, then with it baked into the `mov ecx, imm32`
    probe = src.replace("sc_proc_addr", "0x11111111")
    b1 = asm(probe + "\n    lbl_probe:\n        mov eax, sc_proc\n        mov eax, squig\n", code_va)
    sc_proc = struct.unpack_from("<I", b1, len(b1) - 10 + 1)[0]
    squig = struct.unpack_from("<I", b1, len(b1) - 5 + 1)[0]
    code = asm(src.replace("sc_proc_addr", f"{sc_proc:#x}"), code_va)
    assert asm(src.replace("sc_proc_addr", f"{sc_proc:#x}") + "\n    mov eax, sc_proc\n", code_va)[-4:] == struct.pack("<I", sc_proc)
    off = code_va - ZONE
    assert off + len(code) <= len(data), hex(off + len(code))
    data[off:off + len(code)] = code
    labels = dict(wrap=code_va, sc_proc=sc_proc, squig=squig, code_end=code_va + len(code), tm=tm, rc=rc, sz=sz,
                  L_ENUM=L_ENUM, L_ERR=L_ERR, L_ST=L_ST, L_LEN=L_LEN, L_BOOL=L_BOOL, clsid=clsid, iid=iid, enus=enus)
    return bytes(data), labels


def va2off(pe, va):
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    n = struct.unpack_from("<H", pe, e + 6)[0]
    opt = struct.unpack_from("<H", pe, e + 20)[0]
    sec = e + 24 + opt
    for i in range(n):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def reloc_entries(pe, ranges):
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    rva, sz = struct.unpack_from("<II", pe, e + 24 + 0x88)
    if not sz:
        return []
    off = va2off(pe, BASE + rva); end = off + sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            ent = struct.unpack_from("<H", pe, off + 8 + 2 * i)[0]
            va = BASE + page + (ent & 0xFFF)
            if ent >> 12 and any(lo <= va < hi for lo, hi in ranges):
                hits.append(va)
        off += bsz
    return hits


def call_bytes(src, dst):
    return b"\xe8" + struct.pack("<i", dst - (src + 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    exe = a.exe
    data = bytearray(open(exe, "rb").read())
    zone, lab = build()
    zo = va2off(data, ZONE)
    cur_zone = bytes(data[zo:zo + len(zone)])
    zstate = "zero" if not any(cur_zone) else ("ours" if cur_zone == zone else
                                                ("ours-other" if cur_zone[:4] == MAGIC else "FOREIGN"))
    sstates = []
    for va, orig in SITES:
        so = va2off(data, va); cur = bytes(data[so:so + 5])
        sstates.append("vanilla" if cur == orig else ("ours" if cur == call_bytes(va, lab["wrap"]) else "FOREIGN"))
    rl = reloc_entries(data, [(va, va + 5) for va, _ in SITES] + [(ZONE, ZONE_END)])
    # anchors
    def rd(va): return struct.unpack_from("<I", data, va2off(data, va))[0]
    print(f"AoWDevX spell-check underline: sites {', '.join(f'{va:#x} {s}' for (va, _), s in zip(SITES, sstates))} | "
          f"zone {ZONE:#x}..{ZONE_END:#x} {zstate} (code {lab['wrap']:#x}..{lab['code_end']:#x}, "
          f"{lab['code_end'] - ZONE} B used) | relocs {[hex(v) for v in rl] or 'none'}")
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        off = lab["wrap"] - ZONE
        for i in md.disasm(zone[off:lab["code_end"] - ZONE], lab["wrap"]):
            print(f"  {i.address:08x}  {i.mnemonic} {i.op_str}")
    applied = zstate == "ours" and all(s == "ours" for s in sstates)
    if a.revert:
        if zstate == "zero" and all(s == "vanilla" for s in sstates):
            print("not applied"); return 0
        if zstate not in ("ours", "ours-other") or any(s == "FOREIGN" for s in sstates):
            print("ABORT: unexpected state"); return 1
        hdr = cur_zone
        for i, (va, orig) in enumerate(SITES):
            saved = hdr[4 + 5 * i:9 + 5 * i]
            assert saved == orig, "saved site bytes differ from the expected vanilla bytes"
            so = va2off(data, va); data[so:so + 5] = saved
        data[zo:zo + len(zone)] = bytes(len(zone))
        with open(exe, "r+b") as f:
            f.seek(0); f.write(data)
        print("reverted (sites restored, zone zeroed)"); return 0
    if applied:
        print("already applied"); return 0
    if rl:
        print("ABORT: reloc entries on a site/zone"); return 1
    if zstate == "FOREIGN" or any(s == "FOREIGN" for s in sstates):
        print("ABORT: zone or site not free"); return 1
    if not a.apply:
        print("dry run OK - nothing written (use --apply)"); return 0
    bak = bak_path(exe, BAK)
    if not os.path.exists(bak):
        shutil.copyfile(exe, bak); print("backup ->", bak)
    data[zo:zo + len(zone)] = zone
    for va, _ in SITES:
        so = va2off(data, va); data[so:so + 5] = call_bytes(va, lab["wrap"])
    with open(exe, "r+b") as f:
        f.seek(0); f.write(data)
    back = open(exe, "rb").read()
    assert back[zo:zo + len(zone)] == zone
    print("written and verified: Spell/Ability description editor underlines misspelled words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
