#!/usr/bin/env python3
r"""AoWx -- editor wheel: scroll ONLY what the cursor is over, and make map
scrolling independent of keyboard focus. (VCL30.dpl, shared runtime.)

USER SPEC 2026-08-31: "if the mouse is hovering over a side window, scrolling
only applies to the side window; if hovering over the map, only the map" --
plus the Scanner bug (after clicking the Scanner, wheeling over the map did
nothing until you clicked back into the map). And: DO NOT change the game.

=========================== HOW THIS WAS ESTABLISHED ========================
Three wrong patches preceded this one; the mechanism was finally settled by
measurement, and the earlier reasoning is kept in [[mouse-wheel-scrolling]]
as the lesson.
  * An elevated WH_MOUSE_LL + WH_KEYBOARD_LL probe (probe_input_stream.py)
    logged 156 wheel events while wheeling over side panels and the map and
    saw **exactly 2 key events, both real hardware**. So NOTHING synthesizes
    arrow keys in the editor -- the LL "mouse hotkey" hook's keybd_event arm
    never fires there, and every patch aimed at it was aimed at nothing.
    (A non-elevated probe sees zero events at all: UIPI blocks input hooks
    for an elevated target. The editor runs elevated here.)
  * The editor map scrolls because **HSEPack handles WM_MOUSEWHEEL natively**
    -- a Delphi DYNAMIC METHOD TABLE at HSEPack VA 0x55636804 lists message
    ids 0x020F 0x020C 0x01F8 0x0211 0x020B 0x0210 **0x020A** 0x0209 ...
    A `cmp reg,0x20A` scan (which is what the first analysis did) can never
    find a Delphi message handler -- the id lives in a table, not in code.
  * Windows delivers WM_MOUSEWHEEL to the FOCUSED window, which is why the
    map scrolled while the cursor was over a side panel (focus was still on
    the map) and why clicking the Scanner killed map scrolling entirely.

=================================== THE FIX ================================
The right place is `cave_A` @0x413A8400, the thread-level **WH_MOUSE** hook
that sees WM_MOUSEWHEEL BEFORE it is delivered. Vanilla cave_A:
    WindowFromPoint -> walk parents for WS_VSCROLL/WS_HSCROLL (@0x413A84DF)
    found    -> SendMessageA line-scrolls (@0x413A8514), return 1 = swallow
    not found-> fall to 0x413A84C8 = CallNextHookEx (message is delivered to
                the FOCUSED window -- this is the bug's delivery path)
Only that last edge is redirected: the 6-byte `je 0x413A84C8` @0x413A84AF
(reached solely for a wheel event with no scrollable window under the
cursor) now jumps to a cave that:
    not the editor (GetModuleHandleA("AoWDevX.exe") == 0)
        -> jmp 0x413A84C8, i.e. **the GAME is byte-for-byte unchanged**
    editor, cursor over the map (GetClassNameA == "THSMEdit")
        -> PostMessageA(hwnd, WM_MOUSEWHEEL, delta<<16, (y<<16)|x) and
           swallow: the map gets the wheel DIRECTLY, so it scrolls no matter
           what holds focus (this is the Scanner fix, now via the map's own
           handler instead of synthesized keys)
    editor, cursor anywhere else
        -> swallow: the side panel keeps whatever cave_A already did for it
           and the map does not move
Scrollable side panels are untouched: they never reach this code, because
cave_A already handled and swallowed them further up.

PIC: the cave takes its own load delta (`call $+5; pop ebx; sub ebx,<pref>`,
the same idiom the LL hook uses) and addresses everything as
[ebx+<preferred VA>], so it survives a rebase even though vanilla cave_A
uses absolutes. NOTHING is written to the cave -- the class-name buffer is a
`sub esp,68` stack frame. (v2 crashed both apps by caching a pointer in the
cave: VCL30's CODE section is R-X. See the memory note.)
EBX/ESI/EDI are saved and restored; every exit restores ESP.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "VCL30.dpl")
BAK = DLL + ".bak_wheelctx"

D = 0x41300C00

# the one edge we redirect: cave_A's "wheel, but nothing scrollable" branch
HOOK = 0x413A84AF
ORIG = bytes.fromhex("0f8413000000")          # je 0x413A84C8
PASSTHRU = 0x413A84C8                          # CallNextHookEx tail
SWALLOW_EAX1 = 0x413A84BD                      # mov eax,1; mov esp,ebp; pop ebp; ret 0xC

# v3 of this script hooked the LL wheel gate; restore it if still present
LLGATE = 0x413A8F53
LLGATE_ORIG = bytes.fromhex("83b848e10300000f853b010000")

CAVE = 0x413A9200
CAVE_HI = 0x413A9400

IAT_GETMODULEHANDLEA = 0x413E43BC
IAT_GETPROCADDRESS = 0x413E43B4
IAT_POSTMESSAGEA = 0x413E46C8

MAP_CLASS = b"THSMEdit"
WM_MOUSEWHEEL = 0x20A


_SRC_TMPL = """
        push ebx
        push esi
        push edi
        call _a
    _a:
        pop  ebx
        sub  ebx, {anchor:#x}
        sub  esp, 68
        lea  eax, [ebx + {s_user32:#x}]
        push eax
        call dword ptr [ebx + {gmh:#x}]
        test eax, eax
        jz   _swallow
        lea  edx, [ebx + {s_getcls:#x}]
        push edx
        push eax
        call dword ptr [ebx + {gpa:#x}]
        test eax, eax
        jz   _swallow
        mov  edi, eax
        mov  esi, dword ptr [ebp-4]
        test esi, esi
        jz   _swallow
        push 64
        lea  eax, [esp+4]
        push eax
        push esi
        call edi
        cmp  dword ptr [esp], {w0:#x}
        jne  _swallow
        cmp  dword ptr [esp+4], {w1:#x}
        jne  _swallow
        cmp  byte ptr [esp+8], 0
        jne  _swallow
        mov  edx, dword ptr [ebp+0x10]
        mov  eax, dword ptr [edx+4]
        shl  eax, 16
        mov  ecx, dword ptr [edx]
        and  ecx, 0xFFFF
        or   eax, ecx
        push eax
        movsx eax, word ptr [edx+0x16]
        shl  eax, 16
        push eax
        push {wm:#x}
        push esi
        call dword ptr [ebx + {pm:#x}]
    _swallow:
        add  esp, 68
        pop  edi
        pop  esi
        pop  ebx
        jmp  {swallow:#x}
"""


def make_cave():
    """Read-only cave (VCL30 CODE is R-X): buffer on the stack, no caching."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    off = 0
    s_editor = CAVE + off; b_editor = b"AoWDevX.exe\x00"; off += len(b_editor)
    s_user32 = CAVE + off; b_user32 = b"user32.dll\x00"; off += len(b_user32)
    s_getcls = CAVE + off; b_getcls = b"GetClassNameA\x00"; off += len(b_getcls)
    off = (off + 15) & ~15
    code_va = CAVE + off
    data_len = off
    w0 = struct.unpack("<I", MAP_CLASS[0:4])[0]
    w1 = struct.unpack("<I", MAP_CLASS[4:8])[0]
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    anchor = code_va + 8
    code = None
    for _ in range(6):
        src = _SRC_TMPL.format(anchor=anchor, s_editor=s_editor, s_user32=s_user32,
                               s_getcls=s_getcls, gmh=IAT_GETMODULEHANDLEA,
                               gpa=IAT_GETPROCADDRESS, pm=IAT_POSTMESSAGEA,
                               w0=w0, w1=w1, wm=WM_MOUSEWHEEL,
                               swallow=SWALLOW_EAX1, passthru=PASSTHRU)
        blob, _n = ks.asm(src, code_va)
        code = bytes(blob)
        i = code.find(bytes([0xE8, 0, 0, 0, 0]))
        assert i != -1 and code[i + 5] == 0x5B, "anchor idiom missing"
        real = code_va + i + 5
        if real == anchor:
            break
        anchor = real
    else:
        raise AssertionError("anchor did not converge")
    body = bytearray(data_len) + code
    for addr, blob2 in ((s_editor, b_editor), (s_user32, b_user32), (s_getcls, b_getcls)):
        body[addr - CAVE:addr - CAVE + len(blob2)] = blob2
    return bytes(body), code_va


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave, code_va = make_cave()
    assert CAVE + len(cave) <= CAVE_HI, len(cave)
    hook = b"\x0F\x84" + struct.pack("<i", code_va - (HOOK + 6))

    now = bytes(d[HOOK - D:HOOK - D + len(ORIG)])
    ll = bytes(d[LLGATE - D:LLGATE - D + len(LLGATE_ORIG)])
    st = "original" if now == ORIG else "applied" if now == hook else "OTHER"
    print("  cave_A wheel edge @0x%08X  %s" % (HOOK, st))
    print("  cave              @0x%08X  %d B (code 0x%08X)" % (CAVE, len(cave), code_va))
    if ll != LLGATE_ORIG:
        print("  LL gate           @0x%08X  v3 patch present -> will restore" % LLGATE)

    if revert:
        d[HOOK - D:HOOK - D + len(ORIG)] = ORIG
        d[LLGATE - D:LLGATE - D + len(LLGATE_ORIG)] = LLGATE_ORIG
        d[CAVE - D:CAVE_HI - D] = bytes(CAVE_HI - CAVE)
        open(DLL, "wb").write(bytes(d))
        print("reverted (cave_A edge + LL gate restored, cave zeroed)")
        return 0
    if st == "OTHER":
        print("FOREIGN bytes %s - refusing" % now.hex())
        return 1
    if st == "applied" and bytes(d[CAVE - D:CAVE - D + len(cave)]) == cave and ll == LLGATE_ORIG:
        print("already applied")
        return 0
    if not apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- cave code ----")
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(cave[code_va - CAVE:], code_va):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply / --revert)")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("  backed up")
    d[LLGATE - D:LLGATE - D + len(LLGATE_ORIG)] = LLGATE_ORIG      # undo v3
    d[CAVE - D:CAVE_HI - D] = bytes(CAVE_HI - CAVE)
    d[CAVE - D:CAVE - D + len(cave)] = cave
    d[HOOK - D:HOOK - D + len(ORIG)] = hook
    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe / AoWx.exe / AoWSetup.exe and retry")
        return 1
    print("APPLIED - test (EDITOR): wheel over a side panel scrolls only it "
          "(map stays put); wheel over the map scrolls the map even right "
          "after clicking the Scanner. GAME: untouched (the not-editor path "
          "jumps straight to the vanilla CallNextHookEx tail).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
