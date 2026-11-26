#!/usr/bin/env python3
r"""
AoWx.exe: turn spell-book pages with the mouse-wheel SIDE TILTS (2026-10-11).

The chord engine in VCL30.dpl (build_mouse_chords.py) already turns a plain tilt into a key press - VK table rows
tiltL/tiltR default to VK_LEFT (0x25) / VK_RIGHT (0x27), sent with keybd_event - so in the game a tilt IS an
arrow key.  The spell book (TSpellBook, VMT 0x42DDA8) binds its TAoWBookWindow `Dlg` (field +0x1C4) OnKeyDown to
TSpellBook.DlgKeyDown @0x43129C, which only handles ESC (hide).  OnKeyDown(Sender, var Key: Word; Shift):
eax = self, edx = Sender (the window), ecx = &Key, Shift on the stack (ret 4).

Hook: the 9-byte prologue `55 8BEC 53 8BD8 66833 91B` (push ebp / mov ebp,esp / push ebx / mov ebx,eax /
cmp word [ecx],0x1B) -> jmp cave.  The cave replays the prologue, then:
  Key == VK_LEFT  -> NextBtnClick(self) @0x430418 if NextBtn ([self+0x138]) is Visible ([btn+0x75] != 0)
  Key == VK_RIGHT -> PrevBtnClick(self) @0x430470 if PrevBtn ([self+0x134]) is Visible
  (v1 had these the other way round; the user found it inverted - tilting LEFT flips to the NEXT page here)
  in both cases Key := 0 and the window claims the key ([Sender+0x78] := -1, which TAOWWinManager's dispatch
  @0x598072FC reads after the window's slot-37 call -> stops iterating, so the map does not scroll), then jumps to
  DlgKeyDown's epilogue @0x4312EA.  Any other key: redo `cmp word [ecx],0x1B` and resume @0x4312A6.
The visibility gate mirrors TSpellBook's own page updater (@0x42F602..: NextBtn.SetVisible(pages left),
PrevBtn.SetVisible(page != 0)), so the page index can never run past the ends.  Keyboard Left/Right do the same
while the book is open (unavoidable and harmless: a tilt is indistinguishable from the key).

Cave @0x60EC40 in `.xbfs` (RWX, the exe never rebases: DllCharacteristics 0, ImageBase 0x400000; relocs are
scanned anyway).  Backup <game>\backup\AoWx.exe.bak_bookpages.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_bookpages"
BASE, CODE_V2F = 0x400000, 0x400C00                 # CODE: VA = file + 0x400C00
XBFS_VA, XBFS_FILE = 0x60D000, 0x208600             # .xbfs section (VA, raw offset)
CAVE, CAVE_END = 0x60EC40, 0x60ECC0
HOOK_VA = 0x43129C
HOOK_ORIG = bytes.fromhex("558bec538bd86683391b")   # 9 B prologue of TSpellBook.DlgKeyDown
RESUME, EPILOGUE = 0x4312A6, 0x4312EA
PREV_CLICK, NEXT_CLICK = 0x430470, 0x430418
PREV_BTN, NEXT_BTN = 0x134, 0x138
VK_LEFT, VK_RIGHT = 0x25, 0x27

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build():
    src = """
        push ebp
        mov ebp, esp
        push ebx
        mov ebx, eax
        movzx eax, word ptr [ecx]
        cmp eax, %(left)d
        je next
        cmp eax, %(right)d
        je prev
        cmp word ptr [ecx], 0x1b
        jmp %(resume)#x
    prev:
        mov eax, [ebx+%(pbtn)#x]
        test eax, eax
        jz consume
        cmp byte ptr [eax+0x75], 0
        je consume
        push ecx
        push edx
        mov eax, ebx
        call %(pclick)#x
        pop edx
        pop ecx
        jmp consume
    next:
        mov eax, [ebx+%(nbtn)#x]
        test eax, eax
        jz consume
        cmp byte ptr [eax+0x75], 0
        je consume
        push ecx
        push edx
        mov eax, ebx
        call %(nclick)#x
        pop edx
        pop ecx
    consume:
        mov word ptr [ecx], 0
        mov dword ptr [edx+0x78], -1
        jmp %(epi)#x
    """ % {"left": VK_LEFT, "right": VK_RIGHT, "resume": RESUME, "pbtn": PREV_BTN, "nbtn": NEXT_BTN,
           "pclick": PREV_CLICK, "nclick": NEXT_CLICK, "epi": EPILOGUE}
    code = bytes(ks.asm(src, CAVE)[0])
    assert len(code) <= CAVE_END - CAVE, len(code)
    return code


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    out = set()
    if not rsz: return out
    p, end = r2f(rrva), r2f(rrva) + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    code = build()
    hf = HOOK_VA - CODE_V2F; cf = XBFS_FILE + (CAVE - XBFS_VA)
    hook = b"\xe9" + struct.pack("<i", CAVE - (HOOK_VA + 5)) + b"\x90" * (len(HOOK_ORIG) - 5)
    live = bytes(d[hf:hf + len(HOOK_ORIG)]); zone = bytes(d[cf:cf + (CAVE_END - CAVE)])
    bad = [hex(r) for r in reloc_set(d) if HOOK_VA <= r < HOOK_VA + len(HOOK_ORIG) or CAVE <= r < CAVE_END]
    state = "vanilla" if live == HOOK_ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zone) else "ours" if zone[:len(code)] == code and not any(zone[len(code):]) else "DIFFERS"
    print("hook %s | cave %s (%d B @%#x) | relocs %s" % (state, zstate, len(code), CAVE, bad or "none"))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        if state != "ours": print("not applied"); return 0
        d[hf:hf + len(HOOK_ORIG)] = HOOK_ORIG; d[cf:cf + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        open(a.exe, "r+b").write(d); print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if state == "vanilla" and zstate not in ("zero", "ours"): print("ABORT: cave not free"); return 1
    d[cf:cf + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE); d[cf:cf + len(code)] = code
    d[hf:hf + len(HOOK_ORIG)] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.exe, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "r+b") as f: f.seek(0); f.write(d)
    assert open(a.exe, "rb").read() == bytes(d); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
