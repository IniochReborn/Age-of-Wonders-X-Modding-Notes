#!/usr/bin/env python3
r"""Native mouse-chord hotkeys (Scroll of Slickness replacement), VCL30.dpl.

Replaces the AutoHotkey companion ("AoWx - Scroll of Slickness.exe" + the
launcher) with an in-engine chord layer. Chords (defaults = SoS parity):

              plain        Mouse4 (X1) held    Mouse5 (X2) held
  wheel up    Up           p (prev unit)       PgUp
  wheel down  Down         n (next unit)       PgDn
  tilt left   Left         d                   d
  tilt right  Right        d                   d
  middle      F5           c                   c
  left-click  (normal)     l                   (with R held) Ctrl+E
  right-click (normal)     Esc                 (with L held) Ctrl+E
  Mouse4+Mouse5 together   F4
  (SoS's F8/F9 Alt+Enter fullscreen hack is dropped - native borderless
   fullscreen already exists.)

ARCHITECTURE: the mouse-wheel patch (build_wheel_vcl_pump.py) already runs a
WH_MOUSE_LL hook on a dedicated thread inside the game process - the same
vantage point AutoHotkey used. This patch chains a chord proc in FRONT of the
existing wheel proc: SetWindowsHookExA's lpfn (the `lea eax,[ebx+LLCAVE]`
dword @0x413A8C3E inside the hook-owner threadproc) is repointed to
cave_chproc; whatever the chord layer does not consume falls through with a
tail-jmp into the original LLCAVE @0x413A8B00 (wheel-over-list scrolling and
CallNextHookEx live there, untouched).

cave_chproc @0x413A8D00 (CODE-tail zeros):
  - no-ops unless nCode>=0 AND aowInt.dpl is loaded (G_AOWBASE, set by the
    wheel machinery - so the editor/tools never chord).
  - BUTTON-UP events (X/L/R) always update held-state, even unfocused, so no
    modifier ever sticks after alt-tab.
  - DOWN/wheel/tilt events additionally require the foreground window to
    belong to this process (AHK #IfWinActive equivalent), via
    GetForegroundWindow/GetWindowThreadProcessId/GetCurrentProcessId.
  - keybd_event + the three gate functions are resolved ONCE via the existing
    GetModuleHandleA/GetProcAddress IAT slots and cached; resolution failure
    poisons the feature off (never crashes).
  - key synthesis = keybd_event down/up pairs (what AHK's SendInput does),
    with KEYEVENTF_EXTENDEDKEY for VK 0x21..0x28 (PgUp..Down) so arrows do
    not turn into numpad keys, and a real Ctrl wrap for Ctrl+E.
  - swallowing matches SoS: chorded wheel / tilt / middle are consumed;
    clicks and X-buttons always pass through. PLAIN wheel sends the arrow key
    AND passes through, so every native wheel consumer (hovered-list scroll,
    leader portrait, power slider, and any future WheelScroll client) still
    receives the event - exactly the SoS-era combined behaviour. (v1 of this
    patch swallowed plain wheel outside of known consumers, which silently
    disabled the power-slider wheel - reinstated 2026-08-21.)

VK TABLE @0x413E7170 (20 bytes, file-backed zeros in .idata tail, WRITABLE at
runtime): the engine only reads VKs from here, so the future AoWSetup "Mouse"
tab can rewrite these 20 bytes (file for persistence, live for instant apply)
without touching code. A zero VK disables that chord. Layout:
  +0..2  wheelup   plain/X1/X2      +12..14 middle  plain/X1/X2
  +3..5  wheeldn   plain/X1/X2      +15 L-click+X1   +16 R-click+X1
  +6..8  tiltleft  plain/X1/X2      +17 X1+X2        +18 L+R+X2 (Ctrl+vk)
  +9..11 tiltright plain/X1/X2      +19 reserved
Runtime state @0x413E7150..0x413E716C (.idata zeros, after the wheel patch's
G_PENDING trio): held flags, 4 cached fn ptrs, 2 diag counters.

PIC throughout (call/pop load delta; IAT and globals addressed via delta;
intra-module transfers rel32). Requires the wheel pump patch (asserted).
Backup: VCL30.dpl.bak_chords. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DPL = os.path.join(GAME, "VCL30.dpl")
BAK = DPL + ".bak_chords"

CODE_V2F  = 0x41300C00
IDATA_V2F = 0x41302A00          # .idata: va 0x413E4000 raw 0xE1600

LLCAVE   = 0x413A8B00           # existing wheel LL proc (chain target)
THCAVE   = 0x413A8C00           # hook-owner threadproc (holds lpfn lea)
LPFN_VA  = 0x413A8C3E           # dword of `lea eax,[ebx+LLCAVE]` @0x413A8C3C
CHPROC   = 0x413A8D00
CHPROC_END = 0x413A9200

IAT_GETMODULEHANDLEA = 0x413E43BC
IAT_GETPROCADDRESS   = 0x413E43B4
G_AOWBASE = 0x413E27FC          # cached aowInt base (wheel patch, DATA slack)
AOWINT_HOVER_RVA    = 0x3E100
AOWINT_FACENEXT_RVA = 0x3E104

G2_STATE = 0x413E7150           # bit0 X1, bit1 X2, bit2 L, bit3 R
G2_KEYBD = 0x413E7154           # 0=unresolved, 1=poisoned, else keybd_event
G2_GETFG = 0x413E7158
G2_GWTPID= 0x413E715C
G2_GCPID = 0x413E7160
G2_EVT   = 0x413E7164           # diag: gated chord messages seen
G2_SND   = 0x413E7168           # diag: keys synthesized
G2_TAB   = 0x413E7170           # 20-byte VK table (file-baked defaults)
G2_TAB_END = 0x413E7184

VK = dict(UP=0x26, DOWN=0x28, LEFT=0x25, RIGHT=0x27, PRIOR=0x21, NEXT=0x22,
          F4=0x73, F5=0x74, ESC=0x1B)
DEFAULT_TAB = bytes([
    VK['UP'],   ord('P'), VK['PRIOR'],     # wheel up
    VK['DOWN'], ord('N'), VK['NEXT'],      # wheel down
    VK['LEFT'], ord('D'), ord('D'),        # tilt left
    VK['RIGHT'],ord('D'), ord('D'),        # tilt right
    VK['F5'],   ord('C'), ord('C'),        # middle
    ord('L'),                              # +15 L-click with X1
    VK['ESC'],                             # +16 R-click with X1
    VK['F4'],                              # +17 X1+X2
    ord('E'),                              # +18 L+R with X2 (Ctrl+vk)
    0,                                     # +19 reserved
])
assert len(DEFAULT_TAB) == 20


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.rel = []
        self.labels = {}; self.j32 = []; self.fix = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call_rel(self, t): self.db(0xE8); self.rel.append((len(self.buf), t)); self.dd(0)
    def call_lab(self, n): self.db(0xE8); self.j32.append((len(self.buf), n)); self.dd(0)
    def jmp_lab(self, n): self.db(0xE9); self.j32.append((len(self.buf), n)); self.dd(0)
    def jcc(self, cc8, n):
        # 32-bit Jcc to a label: short opcode 0x7X -> 0F 8X rel32
        self.db(0x0F, cc8 + 0x10); self.j32.append((len(self.buf), n)); self.dd(0)
    def lab(self, n): self.labels[n] = len(self.buf)
    def lea_lab(self, modrm, n):        # lea r32,[ebx+<label VA>]
        self.db(0x8D, modrm); self.fix.append((len(self.buf), n)); self.dd(0)
    def fin(self, limit):
        for off, t in self.rel:
            self.buf[off:off+4] = (t - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, n in self.j32:
            t = self.base + self.labels[n]
            self.buf[off:off+4] = (t - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, n in self.fix:
            self.buf[off:off+4] = ((self.base + self.labels[n]) & 0xFFFFFFFF).to_bytes(4, 'little')
        assert self.base + len(self.buf) <= limit, hex(self.base + len(self.buf))
        return bytes(self.buf)


def build_chproc():
    a = Asm(CHPROC)
    # stdcall(nCode=[ebp+8], wParam/message=[ebp+0xC], lParam/MSLL*=[ebp+0x10])
    a.db(0x55, 0x8B, 0xEC)                  # push ebp; mov ebp,esp
    a.db(0x83, 0xEC, 0x04)                  # sub esp,4  ([ebp-4] = fg pid)
    a.db(0x53, 0x56)                        # push ebx; push esi
    a.call_rel(a.here() + 5)                # ebx = load delta
    popva = a.here()
    a.db(0x5B)
    a.db(0x81, 0xEB); a.dd(popva)
    a.db(0x8B, 0x45, 0x08)                  # nCode
    a.db(0x85, 0xC0)
    a.jcc(0x78, 'chain')                    # js -> pass
    a.db(0x83, 0xBB); a.dd(G_AOWBASE); a.db(0x00)
    a.jcc(0x74, 'chain')                    # not the game -> pass
    a.db(0x8B, 0x4D, 0x0C)                  # ecx = message
    # ---- button-up events: always maintain state, never gated ----
    a.db(0x81, 0xF9); a.dd(0x20C)           # WM_XBUTTONUP
    a.jcc(0x74, 'xup')
    a.db(0x81, 0xF9); a.dd(0x202)           # WM_LBUTTONUP
    a.jcc(0x74, 'lup')
    a.db(0x81, 0xF9); a.dd(0x205)           # WM_RBUTTONUP
    a.jcc(0x74, 'rup')
    # ---- interesting down/wheel messages only ----
    a.db(0x81, 0xF9); a.dd(0x201); a.jcc(0x74, 'need')    # LBUTTONDOWN
    a.db(0x81, 0xF9); a.dd(0x204); a.jcc(0x74, 'need')    # RBUTTONDOWN
    a.db(0x81, 0xF9); a.dd(0x207); a.jcc(0x74, 'need')    # MBUTTONDOWN
    a.db(0x81, 0xF9); a.dd(0x20A); a.jcc(0x74, 'need')    # MOUSEWHEEL
    a.db(0x81, 0xF9); a.dd(0x20B); a.jcc(0x74, 'need')    # XBUTTONDOWN
    a.db(0x81, 0xF9); a.dd(0x20E); a.jcc(0x74, 'need')    # MOUSEHWHEEL
    a.jmp_lab('chain')

    a.lab('need')
    # ---- one-time function resolution ----
    a.db(0x83, 0xBB); a.dd(G2_KEYBD); a.db(0x00)
    a.jcc(0x75, 'resolved')
    a.lea_lab(0x83, 's_user32')             # lea eax,[ebx+"user32.dll"]
    a.db(0x50)
    a.db(0xFF, 0x93); a.dd(IAT_GETMODULEHANDLEA)
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'poison')
    a.db(0x8B, 0xF0)                        # esi = hUser32
    a.lea_lab(0x83, 's_keybd')
    a.db(0x50); a.db(0x56)
    a.db(0xFF, 0x93); a.dd(IAT_GETPROCADDRESS)
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'poison')
    a.db(0x89, 0x83); a.dd(G2_KEYBD)
    a.lea_lab(0x83, 's_getfg')
    a.db(0x50); a.db(0x56)
    a.db(0xFF, 0x93); a.dd(IAT_GETPROCADDRESS)
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'poison')
    a.db(0x89, 0x83); a.dd(G2_GETFG)
    a.lea_lab(0x83, 's_gwtpid')
    a.db(0x50); a.db(0x56)
    a.db(0xFF, 0x93); a.dd(IAT_GETPROCADDRESS)
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'poison')
    a.db(0x89, 0x83); a.dd(G2_GWTPID)
    a.lea_lab(0x83, 's_k32')
    a.db(0x50)
    a.db(0xFF, 0x93); a.dd(IAT_GETMODULEHANDLEA)
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'poison')
    a.lea_lab(0x8B, 's_gcpid')              # lea ecx,[ebx+...]
    a.db(0x51); a.db(0x50)
    a.db(0xFF, 0x93); a.dd(IAT_GETPROCADDRESS)
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'poison')
    a.db(0x89, 0x83); a.dd(G2_GCPID)
    a.jmp_lab('resolved')
    a.lab('poison')
    a.db(0xC7, 0x83); a.dd(G2_KEYBD); a.dd(1)
    a.jmp_lab('chain')
    a.lab('resolved')
    a.db(0x83, 0xBB); a.dd(G2_KEYBD); a.db(0x01)
    a.jcc(0x76, 'chain')                    # jbe: 0/1 -> disabled
    # ---- foreground gate: window must belong to this process ----
    a.db(0xFF, 0x93); a.dd(G2_GETFG)        # GetForegroundWindow()
    a.db(0x85, 0xC0)
    a.jcc(0x74, 'chain')
    a.db(0x8D, 0x55, 0xFC)                  # lea edx,[ebp-4]
    a.db(0x52); a.db(0x50)                  # push &pid; push hwnd
    a.db(0xFF, 0x93); a.dd(G2_GWTPID)
    a.db(0xFF, 0x93); a.dd(G2_GCPID)        # eax = our pid
    a.db(0x3B, 0x45, 0xFC)                  # cmp eax,[ebp-4]
    a.jcc(0x75, 'chain')
    a.db(0xFF, 0x83); a.dd(G2_EVT)          # diag
    # ---- dispatch (ecx=message, esi=MSLLHOOKSTRUCT*) ----
    a.db(0x8B, 0x4D, 0x0C)                  # reload message
    a.db(0x8B, 0x75, 0x10)                  # esi = MSLLHOOKSTRUCT*
    a.db(0x81, 0xF9); a.dd(0x20B); a.jcc(0x74, 'xdown')
    a.db(0x81, 0xF9); a.dd(0x201); a.jcc(0x74, 'ldown')
    a.db(0x81, 0xF9); a.dd(0x204); a.jcc(0x74, 'rdown')
    a.db(0x81, 0xF9); a.dd(0x207); a.jcc(0x74, 'mdown')
    a.db(0x81, 0xF9); a.dd(0x20A); a.jcc(0x74, 'wheel')
    # fallthrough: 0x20E tilt
    a.db(0x8B, 0x46, 0x08)                  # mouseData
    a.db(0xC1, 0xF8, 0x10)                  # sar eax,16 (signed delta)
    a.db(0x85, 0xC0)
    a.db(0xBA); a.dd(G2_TAB + 9)            # right row
    a.jcc(0x7F, 'tilt_go')                  # jg: positive = right
    a.db(0xBA); a.dd(G2_TAB + 6)            # left row
    a.lab('tilt_go')
    a.call_lab('chord3')
    a.call_lab('send1')
    a.jmp_lab('eat')

    a.lab('wheel')
    a.db(0x8B, 0x46, 0x08)
    a.db(0xC1, 0xF8, 0x10)                  # signed wheel delta
    a.db(0x85, 0xC0)
    a.db(0xBA); a.dd(G2_TAB + 0)            # up row
    a.jcc(0x7F, 'wheel_row')
    a.db(0xBA); a.dd(G2_TAB + 3)            # down row
    a.lab('wheel_row')
    a.db(0xF6, 0x83); a.dd(G2_STATE); a.db(0x03)   # test state, X1|X2
    a.jcc(0x75, 'wheel_go')
    # PLAIN wheel: send the arrow ONLY when the native wheel machinery is not
    # armed (its LL proc consumes armed wheels), then always pass through so
    # it makes its own call. Armed = any of the four aowInt globals the
    # CURRENT wheel LL proc checks (hover list 0x3E100, portrait 0x3E104,
    # slider/extras 0x3E10C, 0x3E148). ⚠ If a future wheel patch adds an
    # armed global, add it HERE too, or wheel-over-that-widget will also
    # move the map/selection (the v2 double-action complaint).
    a.db(0x8B, 0x83); a.dd(G_AOWBASE)              # eax = aowInt base
    a.db(0x83, 0xB8); a.dd(0x3E100); a.db(0x00)
    a.jcc(0x75, 'chain')
    a.db(0x83, 0xB8); a.dd(0x3E104); a.db(0x00)
    a.jcc(0x75, 'chain')
    a.db(0x83, 0xB8); a.dd(0x3E10C); a.db(0x00)
    a.jcc(0x75, 'chain')
    a.db(0x83, 0xB8); a.dd(0x3E148); a.db(0x00)
    a.jcc(0x75, 'chain')
    a.call_lab('chord3')
    a.call_lab('send1')
    a.jmp_lab('chain')
    a.lab('wheel_go')
    a.call_lab('chord3')                    # chorded: consume, like SoS
    a.call_lab('send1')
    a.jmp_lab('eat')

    a.lab('mdown')
    a.db(0xBA); a.dd(G2_TAB + 12)
    a.call_lab('chord3')
    a.call_lab('send1')
    a.jmp_lab('eat')

    a.lab('xdown')
    a.db(0x8B, 0x46, 0x08)                  # mouseData
    a.db(0xC1, 0xE8, 0x10)                  # shr eax,16
    a.db(0x83, 0xF8, 0x02)
    a.jcc(0x74, 'x2d')
    a.db(0x83, 0xF8, 0x01)
    a.jcc(0x75, 'chain')
    a.db(0x80, 0x8B); a.dd(G2_STATE); a.db(0x01)   # or state,1 (X1)
    a.jmp_lab('xboth')
    a.lab('x2d')
    a.db(0x80, 0x8B); a.dd(G2_STATE); a.db(0x02)   # or state,2 (X2)
    a.lab('xboth')
    a.db(0x8A, 0x83); a.dd(G2_STATE)
    a.db(0x24, 0x03)                        # and al,3
    a.db(0x3C, 0x03)                        # cmp al,3
    a.jcc(0x75, 'chain')
    a.db(0x0F, 0xB6, 0x83); a.dd(G2_TAB + 17)      # X1+X2 -> F4
    a.call_lab('send1')
    a.jmp_lab('chain')                      # X buttons always pass through

    a.lab('ldown')
    a.db(0x80, 0x8B); a.dd(G2_STATE); a.db(0x04)   # or state,4 (L)
    a.db(0xF6, 0x83); a.dd(G2_STATE); a.db(0x01)   # X1?
    a.jcc(0x74, 'l_x2')
    a.db(0x0F, 0xB6, 0x83); a.dd(G2_TAB + 15)      # 'l'
    a.call_lab('send1')
    a.jmp_lab('chain')
    a.lab('l_x2')
    a.db(0x8A, 0x83); a.dd(G2_STATE)
    a.db(0x24, 0x0A)                        # X2|R
    a.db(0x3C, 0x0A)
    a.jcc(0x75, 'chain')
    a.jmp_lab('ctrl_e')

    a.lab('rdown')
    a.db(0x80, 0x8B); a.dd(G2_STATE); a.db(0x08)   # or state,8 (R)
    a.db(0xF6, 0x83); a.dd(G2_STATE); a.db(0x01)   # X1?
    a.jcc(0x74, 'r_x2')
    a.db(0x0F, 0xB6, 0x83); a.dd(G2_TAB + 16)      # Esc
    a.call_lab('send1')
    a.jmp_lab('chain')
    a.lab('r_x2')
    a.db(0x8A, 0x83); a.dd(G2_STATE)
    a.db(0x24, 0x06)                        # X2|L
    a.db(0x3C, 0x06)
    a.jcc(0x75, 'chain')
    a.lab('ctrl_e')
    a.db(0x0F, 0xB6, 0x83); a.dd(G2_TAB + 18)
    a.call_lab('sendctrl')
    a.jmp_lab('chain')

    a.lab('xup')
    a.db(0x8B, 0x75, 0x10)                  # esi = MSLL*
    a.db(0x8B, 0x46, 0x08)
    a.db(0xC1, 0xE8, 0x10)
    a.db(0x83, 0xF8, 0x01)
    a.jcc(0x75, 'x2u')
    a.db(0x80, 0xA3); a.dd(G2_STATE); a.db(0xFE)   # and state,~1
    a.jmp_lab('chain')
    a.lab('x2u')
    a.db(0x80, 0xA3); a.dd(G2_STATE); a.db(0xFD)   # and state,~2
    a.jmp_lab('chain')
    a.lab('lup')
    a.db(0x80, 0xA3); a.dd(G2_STATE); a.db(0xFB)   # and state,~4
    a.jmp_lab('chain')
    a.lab('rup')
    a.db(0x80, 0xA3); a.dd(G2_STATE); a.db(0xF7)   # and state,~8
    # fallthrough to chain
    a.lab('chain')
    a.db(0x5E, 0x5B)                        # pop esi; pop ebx
    a.db(0x8B, 0xE5, 0x5D)                  # mov esp,ebp; pop ebp
    a.db(0xE9); a.rel.append((len(a.buf), LLCAVE)); a.dd(0)   # jmp LLCAVE
    a.lab('eat')
    a.db(0xB8); a.dd(1)                     # eax = 1 (swallow)
    a.db(0x5E, 0x5B)
    a.db(0x8B, 0xE5, 0x5D)
    a.db(0xC2, 0x0C, 0x00)                  # ret 0xC

    # ---- chord3: edx = row VA (plain/X1/X2 columns) -> eax = vk ----
    a.lab('chord3')
    a.db(0xF6, 0x83); a.dd(G2_STATE); a.db(0x01)
    a.jcc(0x75, 'c3_1')
    a.db(0xF6, 0x83); a.dd(G2_STATE); a.db(0x02)
    a.jcc(0x75, 'c3_2')
    a.db(0x0F, 0xB6, 0x04, 0x13)            # movzx eax, byte [ebx+edx]
    a.db(0xC3)
    a.lab('c3_1')
    a.db(0x0F, 0xB6, 0x44, 0x13, 0x01)      # movzx eax, byte [ebx+edx+1]
    a.db(0xC3)
    a.lab('c3_2')
    a.db(0x0F, 0xB6, 0x44, 0x13, 0x02)      # movzx eax, byte [ebx+edx+2]
    a.db(0xC3)

    # ---- send1: eax = vk (0 -> no-op). down+up via keybd_event ----
    # extended-key flag for VK 0x21..0x28 (PgUp/PgDn/End/Home/arrows)
    a.lab('send1')
    a.db(0x85, 0xC0)
    a.jcc(0x75, 's1go')
    a.db(0xC3)
    a.lab('s1go')
    a.db(0x33, 0xC9)                        # ecx = base flags 0
    a.db(0x8D, 0x50, 0xDF)                  # lea edx,[eax-0x21]
    a.db(0x83, 0xFA, 0x07)
    a.jcc(0x77, 's1ne')                     # ja: not extended
    a.db(0x41)                              # ecx = 1 (EXTENDEDKEY)
    a.lab('s1ne')
    a.db(0x50)                              # save vk
    a.db(0x51)                              # save flags
    a.db(0x6A, 0x00)                        # extra
    a.db(0x51)                              # flags (down)
    a.db(0x6A, 0x00)                        # scan
    a.db(0x50)                              # vk
    a.db(0xFF, 0x93); a.dd(G2_KEYBD)        # keybd_event down (pops own args)
    a.db(0x59)                              # ecx = flags
    a.db(0x58)                              # eax = vk
    a.db(0x83, 0xC9, 0x02)                  # or ecx,2 (KEYUP)
    a.db(0x6A, 0x00)                        # extra
    a.db(0x51)                              # flags (up)
    a.db(0x6A, 0x00)                        # scan
    a.db(0x50)                              # vk
    a.db(0xFF, 0x93); a.dd(G2_KEYBD)        # keybd_event up
    a.db(0xFF, 0x83); a.dd(G2_SND)          # diag
    a.db(0xC3)

    # ---- sendctrl: eax = vk; Ctrl+vk press ----
    a.lab('sendctrl')
    a.db(0x85, 0xC0)
    a.jcc(0x75, 'scgo')
    a.db(0xC3)
    a.lab('scgo')
    a.db(0x50)                              # save vk
    a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x6A, 0x11)
    a.db(0xFF, 0x93); a.dd(G2_KEYBD)        # Ctrl down
    a.db(0x8B, 0x04, 0x24)                  # vk
    a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x50)
    a.db(0xFF, 0x93); a.dd(G2_KEYBD)        # vk down
    a.db(0x8B, 0x04, 0x24)
    a.db(0x6A, 0x00); a.db(0x6A, 0x02); a.db(0x6A, 0x00); a.db(0x50)
    a.db(0xFF, 0x93); a.dd(G2_KEYBD)        # vk up
    a.db(0x6A, 0x00); a.db(0x6A, 0x02); a.db(0x6A, 0x00); a.db(0x6A, 0x11)
    a.db(0xFF, 0x93); a.dd(G2_KEYBD)        # Ctrl up
    a.db(0x58)                              # drop saved vk
    a.db(0xFF, 0x83); a.dd(G2_SND)
    a.db(0xC3)

    a.lab('s_user32'); a.buf += b"user32.dll\0"
    a.lab('s_keybd');  a.buf += b"keybd_event\0"
    a.lab('s_getfg');  a.buf += b"GetForegroundWindow\0"
    a.lab('s_gwtpid'); a.buf += b"GetWindowThreadProcessId\0"
    a.lab('s_k32');    a.buf += b"kernel32.dll\0"
    a.lab('s_gcpid');  a.buf += b"GetCurrentProcessId\0"
    return a.fin(CHPROC_END)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5 * 8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs):
                return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from('<H', data, off + 8 + i * 2)[0]
            if w >> 12 == 0:
                continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None:
                continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi:
                    hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DPL); print("restored VCL30.dpl"); return 0
        print("no backup"); return 1

    d = bytearray(open(DPL, "rb").read())
    ch = build_chproc()

    c_off = CHPROC - CODE_V2F
    lp_off = LPFN_VA - CODE_V2F
    tab_off = G2_TAB - IDATA_V2F

    # prerequisites: wheel pump patch present (threadproc + lea LLCAVE dword)
    assert d[THCAVE - CODE_V2F: THCAVE - CODE_V2F + 3] == b"\x55\x8b\xec", \
        "wheel pump patch not applied (build_wheel_vcl_pump.py first)"
    assert d[lp_off - 2: lp_off] == b"\x8d\x83", "lpfn lea not found"
    cur_lpfn = struct.unpack_from("<I", d, lp_off)[0]

    hits = reloc_hits(bytes(d), [(c_off, c_off + len(ch)),
                                 (lp_off, lp_off + 4),
                                 (tab_off, tab_off + 20)])
    assert not hits, [hex(x) for x in hits]

    cur_c = bytes(d[c_off:c_off + len(ch)])
    cur_t = bytes(d[tab_off:tab_off + 20])

    if cur_c == ch and cur_lpfn == CHPROC and cur_t == DEFAULT_TAB:
        print("ALL ALREADY PATCHED"); return 0
    ok = True
    # accept our own earlier build in the cave (upgrade in place)
    if cur_c != bytes(len(ch)) and cur_c != ch and cur_c[:3] != b"\x55\x8b\xec":
        print("MISMATCH: chord cave region not zero/ours"); ok = False
    if cur_lpfn not in (LLCAVE, CHPROC):
        print("MISMATCH: lpfn dword holds %#x" % cur_lpfn); ok = False
    if cur_t != bytes(20) and cur_t != DEFAULT_TAB:
        print("MISMATCH: VK table region not zero"); ok = False
    if not ok:
        print("Aborting."); return 1

    print("cave_chproc @%#x %dB; lpfn %#x -> chproc; VK table @%#x (20B)"
          % (CHPROC, len(ch), cur_lpfn, G2_TAB))
    print("Native mouse chords (Scroll of Slickness parity) via the LL hook.")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(DPL, BAK); print("Backup ->", os.path.basename(BAK))
    d[c_off:CHPROC_END - CODE_V2F] = bytes(CHPROC_END - CHPROC)  # clear old build
    d[c_off:c_off + len(ch)] = ch
    struct.pack_into("<I", d, lp_off, CHPROC)
    d[tab_off:tab_off + 20] = DEFAULT_TAB
    open(DPL, "wb").write(d)
    print("VCL30.dpl patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
