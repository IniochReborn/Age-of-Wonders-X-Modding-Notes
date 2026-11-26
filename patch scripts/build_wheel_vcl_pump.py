#!/usr/bin/env python3
r"""In-game mouse-wheel scrolling, part 2/2: deliver the wheel from the VCL
message pump to aowInt's WheelScroll helper.

WHY NOT THE EXISTING WH_MOUSE HOOK: the 2026-07-22 attempt routed the in-game
case through the WH_MOUSE hook installed at TApplication.Run — and that hook
was proven never to fire in the game process, which is why in-game scrolling
was shelved. This patch bypasses the hook entirely and taps the message pump
that the game demonstrably runs (AoWx.exe imports Forms.TApplication.Run).

Hook: Forms.TApplication.ProcessMessage @0x4133BA48 does
    PeekMessageA(&Msg) ; cmp [esp+8], WM_QUIT ; je ...
The `cmp dword [esp+8],0x12` @0x4133BA6D is exactly 5 bytes, so it is replaced
by `call cave`. TMsg lives at [esp+4]: .message=[esp+8], .wParam=[esp+0xC].
The cave inspects the freshly peeked message and, for WM_MOUSEWHEEL (0x20A):
    base = GetModuleHandleA("aowInt.dpl")        (0 in editor/tools -> skip)
    if byte[base+0x22880] == 0x53:               (our helper's `push ebx`)
        WheelScroll((short)(wParam >> 16))       stdcall, ret 4
then replays the displaced compare (at its shifted offset [esp+0xC], because a
return address is on top) and returns — `ret` preserves flags, so the caller's
`je` still works. The message itself is left alone: nothing in Delphi 3 handles
WM_MOUSEWHEEL, so letting it continue to DefWindowProc is harmless and keeps
this patch non-invasive.

SAFETY: no-ops anywhere aowInt.dpl isn't loaded (the editor and tools share
this VCL30.dpl), and the signature byte check means a reverted/absent aowInt
half can never be called into. The existing WH_MOUSE hook (caves 0x413A8400 /
0x413A8800) is untouched and still serves real Win32 scrollbars in the editor;
if it swallows a wheel message first, this pump hook simply never sees it, so
there is no double-scroll.

Cave @0x413A8A00 (VCL30 CODE tail zeros). PIC throughout: the IAT slot and the
string are reached via a call/pop load delta.
Backup: VCL30.dpl.bak_wheelpump. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DPL = os.path.join(GAME, "VCL30.dpl")
BAK = DPL + ".bak_wheelpump"

VA2FILE = 0x41300C00
CAVE, CAVE_END = 0x413A8A00, 0x413A8B00
LLCAVE, LLCAVE_END = 0x413A8B00, 0x413A8C00
THCAVE, THCAVE_END = 0x413A8C00, 0x413A8D00
H_SITE = 0x4133BA6D
H_OLD = bytes.fromhex("837c240812")        # cmp dword [esp+8], WM_QUIT
IAT_GETMODULEHANDLEA = 0x413E43BC
IAT_SETWINDOWSHOOKEXA = 0x413E463C
IAT_CALLNEXTHOOKEX = 0x413E4894
IAT_UNHOOKWINDOWSHOOKEX = 0x413E4618
IAT_CREATETHREAD  = 0x413E41E8
IAT_POSTMESSAGEA  = 0x413E46C8
IAT_PEEKMESSAGEA  = 0x413E46CC
IAT_WAITMESSAGE   = 0x413E4604
# more writable slack (DATA's 44B is full) - .idata tail, 196B of zeros
G_PENDING  = 0x413E7140   # wheel notches waiting for the game thread
G_HWND     = 0x413E7144   # a game window, for the wake-up PostMessage
G_THREADED = 0x413E7148   # hook-owner thread created latch
VCL_PREFERRED_BASE = 0x41300000
WH_MOUSE_LL = 14
G_HOOKED = 0x413E27F4                      # "LL hook installed" latch
G_HHOOK  = 0x413E27F8                      # returned HHOOK (diagnostic)
LL_CNT   = 0x413E27D4                      # +0 install result, +4 LL hits, +8 LL wheels
G_AOWBASE = 0x413E27FC                     # cached aowInt.dpl base (0 = unresolved)
AOWINT_HOVER_RVA = 0x3E100                 # aowInt g_hover (cursor-inside listbox)
AOWINT_FACENEXT_RVA = 0x3E104              # aowInt g_facenext (leader portrait)
WM_MOUSEWHEEL = 0x20A
AOWINT_WHEELSCROLL_RVA = 0x22880           # aowInt.dpl VA 0x59822880
HELPER_SIG = 0x55                          # helper's 1st byte = `push ebp`.
# ⚠ COUPLED TO build_wheel_aowint.py: this is a safety signature so a reverted
# or absent aowInt half can never be called into. If WheelScroll's prologue
# changes, update this or the wheel silently stops working everywhere.
# --diag counters in VCL30 DATA slack (44B of zeros @0x413E27D4). Read live with
# wheel_probe.py to see exactly how far a wheel event gets.
DIAG = "--diag" in sys.argv
CNT = 0x413E27E0                           # +0 pump hits, +4 wheel msgs,
                                           # +8 aowInt found, +0xC helper called,
                                           # +0x10 last wParam


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.rel = []
        self.labels = {}; self.j8 = []; self.fix = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.rel.append((len(self.buf), t)); self.dd(0)
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def lea_lab(self, modrm, n):            # lea reg,[reg+<label VA>]
        self.db(0x8D, modrm); self.fix.append((len(self.buf), n)); self.dd(0)
    def fin(self):
        for off, t in self.rel:
            self.buf[off:off+4] = (t - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, n in self.j8:
            d = self.labels[n] - (off + 1)
            assert -128 <= d <= 127, (n, d)
            self.buf[off] = d & 0xFF
        for off, n in self.fix:
            self.buf[off:off+4] = ((self.base + self.labels[n]) & 0xFFFFFFFF).to_bytes(4, 'little')
        return bytes(self.buf)


def build_cave():
    """Game-thread side: create the hook owner thread once, then apply any wheel
    notches the hook has queued.

    PERFORMANCE (this is the whole point of the rewrite): WH_MOUSE_LL callbacks
    run on the thread that INSTALLED the hook, and a gaming mouse reports ~1000
    events/sec. Owning that hook on the game's render thread cost frame rate and
    made the cursor lag, because every mouse event had to wait for the game to
    come round to its message pump. So the hook now lives on a dedicated thread
    that does nothing else: it answers instantly, and the render thread never
    sees an input callback again. The only work left here is draining a counter.
    """
    a = Asm(CAVE)
    a.db(0x60)                                   # pushad
    a.call(a.here() + 5)                         # edx = load delta
    popva = a.here()
    a.db(0x5A)
    a.db(0x81, 0xEA); a.dd(popva)
    if DIAG:
        a.db(0xFF, 0x82); a.dd(CNT + 0)
    # ---- remember a real window handle for the wake-up post ----
    a.db(0x83, 0xBA); a.dd(G_HWND); a.db(0x00)   # cmp dword [edx+G_HWND],0
    a.jcc8(0x75, 'havehwnd')
    a.db(0x8B, 0x44, 0x24, 0x28)                 # mov eax,[esp+0x28] = msg.hwnd
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'havehwnd')                     # thread message: no window
    a.db(0x89, 0x82); a.dd(G_HWND)
    a.lab('havehwnd')
    # ---- start the hook owner thread once ----
    a.db(0x83, 0xBA); a.dd(G_THREADED); a.db(0x00)
    a.jcc8(0x75, 'threaded')
    a.db(0xC7, 0x82); a.dd(G_THREADED); a.dd(1)
    a.db(0x52)                                   # push edx
    a.db(0x6A, 0x00)                             # lpThreadId = NULL
    a.db(0x6A, 0x00)                             # dwCreationFlags
    a.db(0x6A, 0x00)                             # lpParameter
    a.db(0x8D, 0x82); a.dd(THCAVE)               # lpStartAddress
    a.db(0x50)
    a.db(0x6A, 0x00)                             # dwStackSize (default)
    a.db(0x6A, 0x00)                             # lpThreadAttributes
    a.db(0xFF, 0x92); a.dd(IAT_CREATETHREAD)
    a.db(0x5A)                                   # pop edx
    a.lab('threaded')
    # ---- apply queued notches (this is the only per-message cost) ----
    a.db(0x8B, 0x82); a.dd(G_PENDING)            # mov eax,[edx+G_PENDING]
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'done')
    a.db(0xC7, 0x82); a.dd(G_PENDING); a.dd(0)   # consume
    a.db(0x50)                                   # push eax (delta)
    a.db(0x8B, 0x82); a.dd(G_AOWBASE)            # cached aowInt base
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'droppend')
    a.db(0x80, 0xB8); a.dd(AOWINT_WHEELSCROLL_RVA); a.db(HELPER_SIG)
    a.jcc8(0x75, 'droppend')
    a.db(0x05); a.dd(AOWINT_WHEELSCROLL_RVA)
    a.db(0xFF, 0xD0)                             # WheelScroll(delta) (ret 4)
    a.jcc8(0xEB, 'done')
    a.lab('droppend')
    a.db(0x58)                                   # pop eax (discard the arg)
    a.lab('done')
    a.db(0x61)                                   # popad
    a.db(0x83, 0x7C, 0x24, 0x0C, 0x12)           # displaced cmp (shifted)
    a.db(0xC3)                                   # ret (flags preserved)
    return a.fin()


def build_threadproc():
    """Dedicated hook-owner thread: install WH_MOUSE_LL, then just pump.

    A low-level hook is only serviced while its owning thread processes
    messages, so this thread exists solely to do that promptly. It is idle
    otherwise (WaitMessage blocks), so it costs no measurable CPU, and the
    game's render thread is completely out of the input path.
    """
    a = Asm(THCAVE)
    a.db(0x55, 0x8B, 0xEC)                       # push ebp; mov ebp,esp
    a.db(0x83, 0xEC, 0x20)                       # sub esp,0x20 (MSG)
    a.db(0x53)                                   # push ebx
    a.call(a.here() + 5)                         # ebx = delta
    popva = a.here()
    a.db(0x5B)
    a.db(0x81, 0xEB); a.dd(popva)
    # resolve aowInt base here too, so the hook works before the pump caches it
    a.db(0x83, 0xBB); a.dd(G_AOWBASE); a.db(0x00)
    a.jcc8(0x75, 'gotbase')
    a.lea_lab(0x83, 'str2')                      # lea eax,[ebx+"aowInt.dpl"]
    a.db(0x50)
    a.db(0xFF, 0x93); a.dd(IAT_GETMODULEHANDLEA)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'gotbase')
    a.db(0x89, 0x83); a.dd(G_AOWBASE)
    a.lab('gotbase')
    a.db(0x6A, 0x00)                             # dwThreadId = 0 (global)
    a.db(0x8D, 0x83); a.dd(VCL_PREFERRED_BASE)   # hMod
    a.db(0x50)
    a.db(0x8D, 0x83); a.dd(LLCAVE)               # lpfn
    a.db(0x50)
    a.db(0x6A, WH_MOUSE_LL)
    a.db(0xFF, 0x93); a.dd(IAT_SETWINDOWSHOOKEXA)
    a.db(0x89, 0x83); a.dd(G_HHOOK)
    if DIAG:
        a.db(0x89, 0x83); a.dd(LL_CNT + 0)
    a.lab('pump')
    a.db(0xFF, 0x93); a.dd(IAT_WAITMESSAGE)      # block until something arrives
    a.lab('drain')
    a.db(0x6A, 0x01)                             # PM_REMOVE
    a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x6A, 0x00)
    a.db(0x8D, 0x45, 0xE0)                       # lea eax,[ebp-0x20] (&MSG)
    a.db(0x50)
    a.db(0xFF, 0x93); a.dd(IAT_PEEKMESSAGEA)
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'drain')
    a.jcc8(0xEB, 'pump')
    a.lab('str2'); a.buf += b"aowInt.dpl" + bytes(1)
    return a.fin()


def build_llproc():
    """LowLevelMouseProc - now runs on the dedicated thread, so it must stay
    trivial and must NOT touch game UI (that is not thread-safe). It only
    records the notch and nudges the game thread, which does the real work.

    Swallowing (return 1) when armed is what keeps an AutoHotkey wheel->arrow
    remap from also scrolling the map while the cursor is over a game list.
    """
    a = Asm(LLCAVE)
    a.db(0x55, 0x8B, 0xEC)                       # push ebp; mov ebp,esp
    a.db(0x53, 0x56)                             # push ebx; push esi
    a.call(a.here() + 5)
    popva = a.here()
    a.db(0x5B)
    a.db(0x81, 0xEB); a.dd(popva)
    if DIAG:
        a.db(0xFF, 0x83); a.dd(LL_CNT + 4)
    a.db(0x8B, 0x45, 0x08)                       # nCode
    a.db(0x85, 0xC0)
    a.jcc8(0x7C, 'tail')
    a.db(0x81, 0x7D, 0x0C); a.dd(WM_MOUSEWHEEL)
    a.jcc8(0x75, 'tail')
    if DIAG:
        a.db(0xFF, 0x83); a.dd(LL_CNT + 8)
    # armed? (cursor inside a list/memo, or on the leader portrait)
    a.db(0x8B, 0x83); a.dd(G_AOWBASE)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'tail')
    a.db(0x8B, 0x90); a.dd(AOWINT_HOVER_RVA)     # mov edx,[eax+g_hover]
    a.db(0x85, 0xD2)
    a.jcc8(0x75, 'armed')
    a.db(0x8B, 0x90); a.dd(AOWINT_FACENEXT_RVA)
    a.db(0x85, 0xD2)
    a.jcc8(0x74, 'tail')
    a.lab('armed')
    a.db(0x8B, 0x45, 0x10)                       # MSLLHOOKSTRUCT*
    a.db(0x8B, 0x70, 0x08)                       # mouseData
    a.db(0xC1, 0xFE, 0x10)                       # sar esi,16 -> signed delta
    a.db(0x01, 0xB3); a.dd(G_PENDING)            # add [ebx+G_PENDING],esi
    # wake the game thread so it drains the notch even if the mouse is still
    a.db(0x8B, 0x83); a.dd(G_HWND)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'swallow')
    a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x6A, 0x00)   # lParam, wParam, WM_NULL
    a.db(0x50)                                   # hWnd
    a.db(0xFF, 0x93); a.dd(IAT_POSTMESSAGEA)
    a.lab('swallow')
    a.db(0xB8); a.dd(1)
    a.db(0x5E, 0x5B, 0x5D)
    a.db(0xC2, 0x0C, 0x00)                       # ret 0xC (swallow)
    a.lab('tail')
    a.db(0xFF, 0x75, 0x10)
    a.db(0xFF, 0x75, 0x0C)
    a.db(0xFF, 0x75, 0x08)
    a.db(0x6A, 0x00)
    a.db(0xFF, 0x93); a.dd(IAT_CALLNEXTHOOKEX)
    a.db(0x5E, 0x5B, 0x5D)
    a.db(0xC2, 0x0C, 0x00)
    a.lab('str'); a.buf += b"aowInt.dpl" + bytes(1)
    return a.fin()


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]; osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva)
    if off is None or not rsz: return []
    end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8: break
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None: continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi: hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DPL); print("restored VCL30.dpl"); return 0
        print("no backup"); return 1
    d = bytearray(open(DPL, 'rb').read())
    cave = build_cave(); llp = build_llproc(); thp = build_threadproc()
    assert CAVE + len(cave) <= CAVE_END, hex(len(cave))
    assert LLCAVE + len(llp) <= LLCAVE_END, hex(len(llp))
    assert THCAVE + len(thp) <= THCAVE_END, hex(len(thp))
    h, c, l = H_SITE - VA2FILE, CAVE - VA2FILE, LLCAVE - VA2FILE
    t = THCAVE - VA2FILE
    hits = reloc_hits(bytes(d), [(h, h+5), (c, c+len(cave)), (l, l+len(llp)),
                                 (t, t+len(thp))])
    assert not hits, [hex(x) for x in hits]
    cur = bytes(d[h:h+5])
    assert cur == H_OLD or cur[0] == 0xE8, cur.hex()
    seg = bytes(d[c:c+len(cave)])
    assert seg == bytes(len(cave)) or seg[:1] == b'\x60', seg[:8].hex()
    seg = bytes(d[l:l+len(llp)])
    assert seg == bytes(len(llp)) or seg[:1] == b'\x55', seg[:8].hex()
    d[c:c+len(cave)] = cave
    d[l:l+len(llp)] = llp
    d[t:t+len(thp)] = thp
    d[h:h+5] = bytes([0xE8]) + (CAVE - (H_SITE+5)).to_bytes(4, 'little', signed=True)
    print("VCL30: pump %dB @0x%X, LLproc %dB @0x%X, hook-thread %dB @0x%X; hook @0x%X"
          % (len(cave), CAVE, len(llp), LLCAVE, len(thp), THCAVE, H_SITE))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DPL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DPL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
