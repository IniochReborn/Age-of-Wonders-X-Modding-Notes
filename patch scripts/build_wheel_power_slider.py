#!/usr/bin/env python3
r"""Mouse-wheel support: Power Distribution slider + unit-window party cycling.

v3 adds UNIT CYCLING: in the unit window (TUnitWindow), the PNext/PPrev
arrow buttons cycle through the units of the party. When the cursor is
within the unit-preview area (the zone spanned by those two arrows,
extended upward over the preview graphic), wheel up = previous unit,
wheel down = next unit.

  * The buttons identify themselves: a hook at TAOWButton.CheckMouseMove
    entry @0x59811808 (5-byte prologue steal) latches g_unext/g_uprev when
    a button's OnClick is TUnitWindow.PNextClick @0x40AC9C / PPrevClick
    @0x40ABF0. Buttons only receive CheckMouseMove while their window is
    open and input-eligible, so open/close/modality come for free.
  * When the second button of the pair latches (same sweep - the manager
    entry hook zeroes the latches at sweep start), the hook computes the
    preview zone from the buttons' own rects (assumes PPrev left of PNext,
    one parent level of coordinates, zone extended UNIT_GAP_UP px above)
    and tests the sweep's cursor X (ecx at entry) / Y ([esp+4]): result in
    g_uarmed. All game-object pointer chasing stays on the game thread.
  * WheelUnit(delta) @0x598238C0 - stdcall(1 arg), ret 4, eax=1 if it fired
    a button OnClick (hover targets keep priority). Chained third in the
    VCL pump; the LL hook also arms on g_uarmed (a static flag - safe to
    read from the hook thread).
  * Separate globals (not g_facenext/g_faceprev) because the leader-setup
    image hook zeroes those whenever the cursor sits on any TAOWImage.

v2 (Power Distribution slider):

While the power-distribution window is open, the wheel moves the
research/mana slider: wheel up = +5 toward research, wheel down = -5 toward
mana (FPos 0..100; PAResDraw scales FPos, PAManaDraw scales 100-FPos).

Builds on the existing wheel plumbing (build_wheel_aowint.py +
build_wheel_vcl_pump.py, both must already be applied).

HOW THE SLIDER IS FOUND (v2 - the v1 window-VMT scan was wrong): TPowerDlg
in AoWx.exe is NOT the window the TAOWWinManager dispatches to - it is a
small controller object (instance size 0xAC, ~10 virtual slots). The actual
window is a generic aowInt object built from the 'AoWPowerDlg' resource,
with the controller's published methods bound to control events by name.
So no window in the manager's children ever carries the TPowerDlg VMT.

What IS unambiguous is the slider control itself: a TAOWHScrollBar whose
OnChange handler is TPowerDlg.PowerSliderChange @0x42BF40 (AoWx.exe is
Delphi 3 with no .reloc -> exe addresses are constants). Every mouse-move
sweep, each control in every OPEN, input-eligible window has its
CheckMouseMove called (the control does its own bounds test), so:

aowInt.dpl side
  * g_pslider @ 0x5983E10C (DATA slack) = the power slider, or 0.
  * CLR2 cave @ 0x59823600 replaces the old CLR cave as the target of the
    TAOWWinManager.CheckMouseMove entry hook @0x59807094: zeroes all four
    latches at the start of every sweep (old cave at 0x59822800 left dead).
  * SLD hook @ TAOWHScrollBar.CheckMouseMove entry 0x5981FA5C (steals the
    5-byte prologue 55 8B EC 51 53): if this scrollbar's OnChange code ptr
    (+0x6C) == PowerSliderChange, latch g_pslider = self. Runs only while
    the window is open and receiving sweeps, so open/close, modality and
    z-order are all handled by the game's own dispatch.
  * WheelPower(delta) @ 0x59823700 - stdcall(1 arg), ret 4, eax=1 if it
    moved the slider. Only acts when g_pslider is set and g_hover is clear.
    Drives the game's own path:
      TAOWScrollBar.SetFPos(slider, FPos +/- 5)   @0x5980CA28 (clamps 0..100)
      fire slider.OnChange (+0x6C/6E/70)          -> PowerSliderChange
    OnChange recalcs the Mana/Research/Power labels, exactly like dragging.
    First byte is 0x55 (push ebp) - the VCL side's call-safety signature.

VCL30.dpl side (pump + LL caves REBUILT in place, extended)
  * pump cave @0x413A8A00: after WheelScroll(delta) returns 0 (nothing
    hovered), chain-call WheelPower(delta) at aowInt RVA 0x23700 (sig-checked).
  * LL cave @0x413A8B00: also arm (queue the notch + swallow the event) when
    g_pslider (aowInt RVA 0x3E10C) is set, so the wheel works anywhere on
    screen while the window is open - and the AutoHotkey wheel->arrow remap
    (Scroll of Slickness) never sees the event while armed.
  * hook-owner thread cave @0x413A8C00 untouched.

Requires both prior wheel patches applied; asserts their exact footprints
before touching anything. Backups: aowInt.dpl.bak_pwrslider,
VCL30.dpl.bak_pwrslider. Dry-run default; --apply / --revert (restores both).
Diagnose live with probe_pwrslider.py.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
INT = os.path.join(GAME, "aowInt.dpl")
VCL = os.path.join(GAME, "VCL30.dpl")
INT_BAK = INT + ".bak_pwrslider"
VCL_BAK = VCL + ".bak_pwrslider"

STEP = 5                       # slider notches per wheel click (range is 0..100)
UNIT_GAP_UP   = 110            # px above the arrows counted as preview zone
UNIT_GAP_DOWN = 8              # px below
UNIT_GAP_SIDE = 8              # px left/right of the arrow pair

# ---- aowInt.dpl map (matches build_wheel_aowint.py) ----
CODE_OFF = 0x59800C00          # CODE: file = VA - this
DATA_OFF = 0x59801A00          # DATA: file = VA - this
G_HOVER    = 0x5983E100
G_FACENEXT = 0x5983E104
G_FACEPREV = 0x5983E108
G_PSLIDER  = 0x5983E10C        # NEW latch (diag counters start at 0x...110)
G_UNEXT    = 0x5983E140        # unit-window PNext button (past the diag area)
G_UPREV    = 0x5983E144        # unit-window PPrev button
G_UARMED   = 0x5983E148        # 1 = cursor inside the preview zone this sweep
CLR_CAVE   = 0x59822800        # old CLR cave (becomes dead code)
CLR2_CAVE  = 0x59823600        # new CheckMouseMove-entry cave
SLD_CAVE   = 0x59823680        # H-scrollbar CheckMouseMove entry cave
WPOWER_CAVE = 0x59823700       # WheelPower helper
BTN_CAVE   = 0x59823800        # TAOWButton CheckMouseMove entry cave
WUNIT_CAVE = 0x59823900        # WheelUnit helper
CAVE_END   = 0x59823A00        # CODE tail zeros run 0x598229B9..0x5983D200
H_CLR      = 0x59807094        # TAOWWinManager.CheckMouseMove entry (hooked)
H_CLR_OLDLEN = 6               # jmp rel32 + nop
H_SLD      = 0x5981FA5C        # TAOWHScrollBar.CheckMouseMove entry
H_SLD_OLD  = bytes.fromhex("558bec5153")  # push ebp;mov ebp,esp;push ecx;push ebx
H_BTN      = 0x59811808        # TAOWButton.CheckMouseMove entry (same prologue)
H_BTN_OLD  = bytes.fromhex("558bec5153")
F_SETFPOS  = 0x5980CA28        # TAOWScrollBar.SetFPos(eax=self, edx=newpos)
SB_FPOS, SB_EVT_CODE, SB_EVT_HIWD, SB_EVT_DATA = 0x148, 0x6C, 0x6E, 0x70
CTRL_LEFT, CTRL_TOP = 0x84, 0x88
CTRL_WIDTH, CTRL_HEIGHT = 0x7C, 0x80
CTRL_PARENT = 0x10C
BTN_EVT_CODE, BTN_EVT_HIWD, BTN_EVT_DATA = 0x138, 0x13A, 0x13C
# AoWx.exe (Delphi 3, no .reloc, always at 0x400000)
PWRSLIDERCHANGE = 0x42BF40     # TPowerDlg.PowerSliderChange (published table)
PNEXT_CLICK = 0x40AC9C         # TUnitWindow.PNextClick (published table)
PPREV_CLICK = 0x40ABF0         # TUnitWindow.PPrevClick

# ---- VCL30.dpl map (matches build_wheel_vcl_pump.py) ----
VA2FILE = 0x41300C00
CAVE,  CAVE_HI  = 0x413A8A00, 0x413A8B00   # pump cave (rebuilt)
LLCAVE, LL_HI   = 0x413A8B00, 0x413A8C00   # LL hook cave (rebuilt)
THCAVE          = 0x413A8C00               # hook-owner thread (untouched)
H_SITE = 0x4133BA6D
IAT_CREATETHREAD  = 0x413E41E8
IAT_POSTMESSAGEA  = 0x413E46C8
IAT_CALLNEXTHOOKEX = 0x413E4894
G_PENDING, G_HWND, G_THREADED = 0x413E7140, 0x413E7144, 0x413E7148
G_AOWBASE = 0x413E27FC
WM_MOUSEWHEEL = 0x20A
RVA_WHEELSCROLL = 0x22880      # aowInt WheelScroll
RVA_WHEELPOWER  = 0x23700      # aowInt WheelPower (this patch)
RVA_WHEELUNIT   = 0x23900      # aowInt WheelUnit (this patch)
RVA_HOVER, RVA_FACENEXT, RVA_PSLIDER = 0x3E100, 0x3E104, 0x3E10C
RVA_UARMED = 0x3E148
HELPER_SIG = 0x55              # push ebp - shared call-safety signature


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.rel = []
        self.labels = {}; self.j8 = []; self.j32 = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.rel.append((len(self.buf), t)); self.dd(0)
    def jmp(self, t): self.db(0xE9); self.rel.append((len(self.buf), t)); self.dd(0)
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def jcc32(self, op, n):  # near conditional jump to a label (0F 8x rel32)
        self.db(0x0F, op); self.j32.append((len(self.buf), n)); self.dd(0)
    def jmp32(self, n):      # near jmp to a label
        self.db(0xE9); self.j32.append((len(self.buf), n)); self.dd(0)
    def delta(self, reg):
        """reg = load delta (runtime base - preferred base)."""
        self.call(self.here() + 5)
        popva = self.here()
        self.db(0x58 + reg)                       # pop reg
        self.db(0x81, 0xE8 + reg); self.dd(popva) # sub reg, popva
    def fin(self):
        for off, t in self.rel:
            self.buf[off:off+4] = (t - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, n in self.j8:
            d = self.labels[n] - (off + 1)
            assert -128 <= d <= 127, (n, d)
            self.buf[off] = d & 0xFF
        for off, n in self.j32:
            self.buf[off:off+4] = (self.labels[n] - (off + 4)).to_bytes(4, 'little', signed=True)
        return bytes(self.buf)


def build_clr2():
    """CheckMouseMove-entry cave: zero all latches every sweep."""
    a = Asm(CLR2_CAVE)
    a.db(0x53)                                  # push ebx
    a.delta(3)                                  # ebx = load delta
    for g in (G_HOVER, G_FACENEXT, G_FACEPREV, G_PSLIDER,
              G_UNEXT, G_UPREV, G_UARMED):
        a.db(0xC7, 0x83); a.dd(g); a.dd(0)      # mov dword [ebx+g],0
    a.db(0x5B)                                  # pop ebx
    a.db(0x55, 0x8B, 0xEC, 0x83, 0xC4, 0xF4)    # displaced prologue
    a.jmp(H_CLR + H_CLR_OLDLEN)
    return a.fin()


def build_btn():
    """TAOWButton.CheckMouseMove entry: latch the unit-window arrows and
    evaluate the preview zone.

    Entry: eax = the button, ecx = sweep cursor X, dl = flag, [esp+4] = Y.
    When both arrows have latched (the second one lands here in the same
    sweep, since the manager entry zeroes the latches at sweep start),
    build the zone from the buttons' rects - one parent level of offsets,
    matching TAOWControl's own hit test - and set g_uarmed from the cursor.
    Assumes PPrev sits left of PNext; if a layout ever mirrors them the
    zone collapses and the wheel simply stays inactive there.
    """
    a = Asm(BTN_CAVE)
    a.db(0x53, 0x56, 0x57)                      # push ebx; push esi; push edi
    a.delta(3)                                  # ebx = load delta
    a.db(0x81, 0xB8); a.dd(BTN_EVT_CODE); a.dd(PNEXT_CLICK)
    a.jcc8(0x75, 'notnext')                     # cmp [eax+0x138],PNextClick
    a.db(0x89, 0x83); a.dd(G_UNEXT)             # mov [ebx+G_UNEXT],eax
    a.db(0x83, 0xBB); a.dd(G_UPREV); a.db(0x00) # cmp dword [ebx+G_UPREV],0
    a.jcc8(0x75, 'eval')
    a.jmp32('out')
    a.lab('notnext')
    a.db(0x81, 0xB8); a.dd(BTN_EVT_CODE); a.dd(PPREV_CLICK)
    a.jcc32(0x85, 'out')
    a.db(0x89, 0x83); a.dd(G_UPREV)             # mov [ebx+G_UPREV],eax
    a.db(0x83, 0xBB); a.dd(G_UNEXT); a.db(0x00)
    a.jcc32(0x84, 'out')
    a.lab('eval')
    a.db(0x50, 0x51, 0x52)                      # push eax; push ecx; push edx
    a.db(0x8B, 0xB3); a.dd(G_UPREV)             # esi = PPrev
    a.db(0x8B, 0xBB); a.dd(G_UNEXT)             # edi = PNext
    a.db(0x8B, 0x96); a.dd(CTRL_PARENT)         # edx = [esi+0x10C] parent
    # ---- X: L = parX + prev.left - GAP <= ecx <= parX + next.left+width + GAP
    a.db(0x8B, 0x82); a.dd(CTRL_LEFT)           # eax = parent.left
    a.db(0x03, 0x86); a.dd(CTRL_LEFT)           # + prev.left
    a.db(0x83, 0xE8, UNIT_GAP_SIDE)             # - gap
    a.db(0x3B, 0xC8)                            # cmp ecx,eax
    a.jcc8(0x7C, 'miss')
    a.db(0x8B, 0x82); a.dd(CTRL_LEFT)
    a.db(0x03, 0x87); a.dd(CTRL_LEFT)           # + next.left
    a.db(0x03, 0x87); a.dd(CTRL_WIDTH)          # + next.width
    a.db(0x83, 0xC0, UNIT_GAP_SIDE)             # + gap
    a.db(0x3B, 0xC8)
    a.jcc8(0x7F, 'miss')
    # ---- Y: T = parY + prev.top - GAP_UP <= Y <= parY + prev.top+height + GAP_DN
    a.db(0x8B, 0x4C, 0x24, 0x1C)                # mov ecx,[esp+0x1C] = Y
    a.db(0x8B, 0x82); a.dd(CTRL_TOP)            # eax = parent.top
    a.db(0x03, 0x86); a.dd(CTRL_TOP)            # + prev.top
    a.db(0x83, 0xE8, UNIT_GAP_UP)               # - gap up
    a.db(0x3B, 0xC8)
    a.jcc8(0x7C, 'miss')
    a.db(0x8B, 0x82); a.dd(CTRL_TOP)
    a.db(0x03, 0x86); a.dd(CTRL_TOP)
    a.db(0x03, 0x86); a.dd(CTRL_HEIGHT)         # + prev.height
    a.db(0x83, 0xC0, UNIT_GAP_DOWN)             # + gap down
    a.db(0x3B, 0xC8)
    a.jcc8(0x7F, 'miss')
    a.db(0xC7, 0x83); a.dd(G_UARMED); a.dd(1)
    a.jcc8(0xEB, 'evald')
    a.lab('miss')
    a.db(0xC7, 0x83); a.dd(G_UARMED); a.dd(0)
    a.lab('evald')
    a.db(0x5A, 0x59, 0x58)                      # pop edx; pop ecx; pop eax
    a.lab('out')
    a.db(0x5F, 0x5E, 0x5B)                      # pop edi; pop esi; pop ebx
    a.buf += H_BTN_OLD                          # displaced prologue
    a.jmp(H_BTN + len(H_BTN_OLD))
    return a.fin()


def build_wheelunit():
    """WheelUnit(delta) - stdcall(1 arg), ret 4, eax=1 if it cycled a unit.
    Wheel up = PPrev (previous unit), wheel down = PNext."""
    a = Asm(WUNIT_CAVE)
    a.db(0x55, 0x8B, 0xEC)                      # push ebp; mov ebp,esp (sig 0x55)
    a.db(0x53, 0x56)                            # push ebx; push esi
    a.delta(3)                                  # ebx = load delta
    a.db(0x83, 0xBB); a.dd(G_UARMED); a.db(0x00)
    a.jcc8(0x74, 'fail')                        # cursor not in the preview zone
    a.db(0x8B, 0x83); a.dd(G_HOVER)             # hover targets keep priority
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'fail')
    a.db(0x8B, 0x4D, 0x08)                      # mov ecx,[ebp+8] delta
    a.db(0x85, 0xC9)
    a.jcc8(0x7E, 'down')
    a.db(0x8B, 0xB3); a.dd(G_UPREV)             # wheel up -> previous unit
    a.jcc8(0xEB, 'go')
    a.lab('down')
    a.db(0x8B, 0xB3); a.dd(G_UNEXT)             # wheel down -> next unit
    a.lab('go')
    a.db(0x85, 0xF6)
    a.jcc8(0x74, 'fail')
    a.db(0x66, 0x83, 0xBE); a.dd(BTN_EVT_HIWD); a.db(0x00)  # OnClick assigned?
    a.jcc8(0x74, 'fail')
    a.db(0x8B, 0xD6)                            # mov edx,esi (Sender)
    a.db(0x8B, 0x86); a.dd(BTN_EVT_DATA)        # mov eax,[esi+0x13C] (Self)
    a.db(0xFF, 0x96); a.dd(BTN_EVT_CODE)        # call [esi+0x138] OnClick
    a.db(0xB8); a.dd(1)                         # mov eax,1
    a.jcc8(0xEB, 'exit')
    a.lab('fail')
    a.db(0x33, 0xC0)                            # xor eax,eax
    a.lab('exit')
    a.db(0x5E, 0x5B, 0x5D)                      # pop esi; pop ebx; pop ebp
    a.db(0xC2, 0x04, 0x00)                      # ret 4
    return a.fin()


def build_sld():
    """TAOWHScrollBar.CheckMouseMove entry: latch the power slider.

    eax = the scrollbar. Called every sweep for every H-scrollbar inside an
    open, input-eligible window (each control hit-tests itself), so this is
    live exactly while the power window can take input. The power slider is
    the only scrollbar whose OnChange code ptr is PowerSliderChange.
    """
    a = Asm(SLD_CAVE)
    a.db(0x53)                                  # push ebx
    a.delta(3)                                  # ebx = load delta
    a.db(0x81, 0xB8); a.dd(SB_EVT_CODE); a.dd(PWRSLIDERCHANGE)
    a.jcc8(0x75, 'skip')                        # cmp [eax+0x6C],imm ; jne
    a.db(0x89, 0x83); a.dd(G_PSLIDER)           # mov [ebx+G_PSLIDER],eax
    a.lab('skip')
    a.db(0x5B)                                  # pop ebx
    a.buf += H_SLD_OLD                          # displaced prologue
    a.jmp(H_SLD + len(H_SLD_OLD))
    return a.fin()


def build_wheelpower():
    """WheelPower(delta) - stdcall(1 arg), ret 4, eax=1 if it moved the slider."""
    a = Asm(WPOWER_CAVE)
    a.db(0x55, 0x8B, 0xEC)                      # push ebp; mov ebp,esp (sig 0x55)
    a.db(0x53, 0x56, 0x57)                      # push ebx; push esi; push edi
    a.delta(3)                                  # ebx = load delta
    a.db(0x8B, 0xBB); a.dd(G_PSLIDER)           # mov edi,[ebx+G_PSLIDER]
    a.db(0x85, 0xFF)
    a.jcc8(0x74, 'fail')
    a.db(0x8B, 0x83); a.dd(G_HOVER)             # hover targets keep priority
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'fail')
    a.db(0x8B, 0x97); a.dd(SB_FPOS)             # mov edx,[edi+0x148]
    a.db(0x8B, 0x4D, 0x08)                      # mov ecx,[ebp+8] delta
    a.db(0x85, 0xC9)
    a.jcc8(0x7E, 'down')
    a.db(0x83, 0xC2, STEP)                      # wheel up -> toward research
    a.jcc8(0xEB, 'doit')
    a.lab('down')
    a.db(0x83, 0xEA, STEP)                      # wheel down -> toward mana
    a.lab('doit')
    a.db(0x8B, 0xC7)                            # mov eax,edi
    a.call(F_SETFPOS)                           # clamps to 0..100 internally
    a.db(0x66, 0x83, 0xBF); a.dd(SB_EVT_HIWD); a.db(0x00)   # OnChange assigned?
    a.jcc8(0x74, 'ok')
    a.db(0x8B, 0xD7)                            # mov edx,edi (Sender)
    a.db(0x8B, 0x87); a.dd(SB_EVT_DATA)         # mov eax,[edi+0x70] (Self)
    a.db(0xFF, 0x97); a.dd(SB_EVT_CODE)         # call [edi+0x6C] OnChange
    a.lab('ok')
    a.db(0xB8); a.dd(1)                         # mov eax,1
    a.jcc8(0xEB, 'exit')
    a.lab('fail')
    a.db(0x33, 0xC0)                            # xor eax,eax
    a.lab('exit')
    a.db(0x5F, 0x5E, 0x5B, 0x5D)                # pop edi;esi;ebx;ebp
    a.db(0xC2, 0x04, 0x00)                      # ret 4
    return a.fin()


def build_pump():
    """Pump cave, extended: WheelScroll first; if it returns 0, WheelPower.
    Same entry/exit contract as build_wheel_vcl_pump.py's cave."""
    a = Asm(CAVE)
    a.db(0x60)                                   # pushad
    a.call(a.here() + 5)                         # edx = load delta
    popva = a.here()
    a.db(0x5A)
    a.db(0x81, 0xEA); a.dd(popva)
    # ---- remember a real window handle for the wake-up post ----
    a.db(0x83, 0xBA); a.dd(G_HWND); a.db(0x00)
    a.jcc8(0x75, 'havehwnd')
    a.db(0x8B, 0x44, 0x24, 0x28)                 # mov eax,[esp+0x28] msg.hwnd
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'havehwnd')
    a.db(0x89, 0x82); a.dd(G_HWND)
    a.lab('havehwnd')
    # ---- start the hook owner thread once ----
    a.db(0x83, 0xBA); a.dd(G_THREADED); a.db(0x00)
    a.jcc8(0x75, 'threaded')
    a.db(0xC7, 0x82); a.dd(G_THREADED); a.dd(1)
    a.db(0x52)                                   # push edx
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x00)
    a.db(0x8D, 0x82); a.dd(THCAVE)               # lpStartAddress
    a.db(0x50)
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x00)
    a.db(0xFF, 0x92); a.dd(IAT_CREATETHREAD)
    a.db(0x5A)                                   # pop edx
    a.lab('threaded')
    # ---- apply queued notches ----
    a.db(0x8B, 0x82); a.dd(G_PENDING)            # mov eax,[edx+G_PENDING]
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'done')
    a.db(0xC7, 0x82); a.dd(G_PENDING); a.dd(0)   # consume
    a.db(0x8B, 0xF0)                             # mov esi,eax (delta)
    a.db(0x8B, 0xBA); a.dd(G_AOWBASE)            # mov edi, aowInt base
    a.db(0x85, 0xFF)
    a.jcc8(0x74, 'done')
    a.db(0x80, 0xBF); a.dd(RVA_WHEELSCROLL); a.db(HELPER_SIG)
    a.jcc8(0x75, 'trypwr')
    a.db(0x56)                                   # push esi (delta)
    a.db(0x8D, 0x87); a.dd(RVA_WHEELSCROLL)      # lea eax,[edi+RVA]
    a.db(0xFF, 0xD0)                             # WheelScroll(delta) (ret 4)
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'done')                         # scrolled -> done
    a.lab('trypwr')
    a.db(0x80, 0xBF); a.dd(RVA_WHEELPOWER); a.db(HELPER_SIG)
    a.jcc8(0x75, 'tryunit')
    a.db(0x56)                                   # push esi (delta)
    a.db(0x8D, 0x87); a.dd(RVA_WHEELPOWER)
    a.db(0xFF, 0xD0)                             # WheelPower(delta) (ret 4)
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'done')                         # handled -> done
    a.lab('tryunit')
    a.db(0x80, 0xBF); a.dd(RVA_WHEELUNIT); a.db(HELPER_SIG)
    a.jcc8(0x75, 'done')
    a.db(0x56)                                   # push esi (delta)
    a.db(0x8D, 0x87); a.dd(RVA_WHEELUNIT)
    a.db(0xFF, 0xD0)                             # WheelUnit(delta) (ret 4)
    a.lab('done')
    a.db(0x61)                                   # popad
    a.db(0x83, 0x7C, 0x24, 0x0C, 0x12)           # displaced cmp (shifted)
    a.db(0xC3)                                   # ret (flags preserved)
    return a.fin()


def build_llproc():
    """LL hook cave, extended: also armed when g_pslider is set."""
    a = Asm(LLCAVE)
    a.db(0x55, 0x8B, 0xEC)                       # push ebp; mov ebp,esp
    a.db(0x53, 0x56)                             # push ebx; push esi
    a.call(a.here() + 5)
    popva = a.here()
    a.db(0x5B)
    a.db(0x81, 0xEB); a.dd(popva)
    a.db(0x8B, 0x45, 0x08)                       # nCode
    a.db(0x85, 0xC0)
    a.jcc8(0x7C, 'tail')
    a.db(0x81, 0x7D, 0x0C); a.dd(WM_MOUSEWHEEL)
    a.jcc8(0x75, 'tail')
    a.db(0x8B, 0x83); a.dd(G_AOWBASE)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'tail')
    a.db(0x8B, 0x90); a.dd(RVA_HOVER)            # cursor inside a list/memo?
    a.db(0x85, 0xD2)
    a.jcc8(0x75, 'armed')
    a.db(0x8B, 0x90); a.dd(RVA_FACENEXT)         # leader portrait?
    a.db(0x85, 0xD2)
    a.jcc8(0x75, 'armed')
    a.db(0x8B, 0x90); a.dd(RVA_PSLIDER)          # power-distribution dlg open?
    a.db(0x85, 0xD2)
    a.jcc8(0x75, 'armed')
    a.db(0x8B, 0x90); a.dd(RVA_UARMED)           # cursor in the unit preview?
    a.db(0x85, 0xD2)
    a.jcc8(0x74, 'tail')
    a.lab('armed')
    a.db(0x8B, 0x45, 0x10)                       # MSLLHOOKSTRUCT*
    a.db(0x8B, 0x70, 0x08)                       # mouseData
    a.db(0xC1, 0xFE, 0x10)                       # sar esi,16 -> signed delta
    a.db(0x01, 0xB3); a.dd(G_PENDING)            # add [ebx+G_PENDING],esi
    a.db(0x8B, 0x83); a.dd(G_HWND)               # wake the game thread
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'swallow')
    a.db(0x6A, 0x00); a.db(0x6A, 0x00); a.db(0x6A, 0x00)
    a.db(0x50)
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


def jmp5(src, dst):
    return bytes([0xE9]) + (dst - (src + 5)).to_bytes(4, 'little', signed=True)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        ok = True
        for f, b in ((INT, INT_BAK), (VCL, VCL_BAK)):
            if os.path.exists(b):
                shutil.copy2(b, f); print("restored", os.path.basename(f))
            else:
                print("no backup for", os.path.basename(f)); ok = False
        return 0 if ok else 1

    di = bytearray(open(INT, 'rb').read())
    dv = bytearray(open(VCL, 'rb').read())

    # ---- aowInt: prerequisite + target state checks ----
    hc = H_CLR - CODE_OFF
    cur = bytes(di[hc:hc+H_CLR_OLDLEN])
    want_old = jmp5(H_CLR, CLR_CAVE) + b'\x90'    # wheel patch applied
    want_new = jmp5(H_CLR, CLR2_CAVE) + b'\x90'   # this patch applied
    assert cur in (want_old, want_new), "unexpected H_CLR bytes: " + cur.hex()
    hs = H_SLD - CODE_OFF
    curs = bytes(di[hs:hs+len(H_SLD_OLD)])
    slds_new = jmp5(H_SLD, SLD_CAVE)
    assert curs in (H_SLD_OLD, slds_new), "unexpected H_SLD bytes: " + curs.hex()
    hb = H_BTN - CODE_OFF
    curb = bytes(di[hb:hb+len(H_BTN_OLD)])
    btn_new = jmp5(H_BTN, BTN_CAVE)
    assert curb in (H_BTN_OLD, btn_new), "unexpected H_BTN bytes: " + curb.hex()

    clr2, sld, wpow = build_clr2(), build_sld(), build_wheelpower()
    btn, wunit = build_btn(), build_wheelunit()
    assert CLR2_CAVE + len(clr2) <= SLD_CAVE, len(clr2)
    assert SLD_CAVE + len(sld) <= WPOWER_CAVE, len(sld)
    assert WPOWER_CAVE + len(wpow) <= BTN_CAVE, len(wpow)
    assert BTN_CAVE + len(btn) <= WUNIT_CAVE, len(btn)
    assert WUNIT_CAVE + len(wunit) <= CAVE_END, len(wunit)
    caves = ((CLR2_CAVE, clr2, 0x53), (SLD_CAVE, sld, 0x53),
             (WPOWER_CAVE, wpow, 0x55), (BTN_CAVE, btn, 0x53),
             (WUNIT_CAVE, wunit, 0x55))
    for va, blob, sig in caves:
        o = va - CODE_OFF
        seg = bytes(di[o:o+len(blob)])
        assert seg == bytes(len(blob)) or seg[0] == sig, seg[:8].hex()
    for gva in (G_PSLIDER, G_UNEXT, G_UPREV, G_UARMED):
        g = gva - DATA_OFF
        assert bytes(di[g:g+4]) == b'\0\0\0\0', "latch slot 0x%X not free" % gva
    g = G_PSLIDER - DATA_OFF
    rngs = [(hc, hc + H_CLR_OLDLEN), (hs, hs + len(H_SLD_OLD)),
            (hb, hb + len(H_BTN_OLD)), (g, g + 4),
            (G_UNEXT - DATA_OFF, G_UARMED - DATA_OFF + 4)]
    rngs += [(va - CODE_OFF, va - CODE_OFF + len(b)) for va, b, _ in caves]
    hits = reloc_hits(bytes(di), rngs)
    assert not hits, [hex(x) for x in hits]

    # ---- VCL30: prerequisite + target state checks ----
    pump, llp = build_pump(), build_llproc()
    assert CAVE + len(pump) <= CAVE_HI, len(pump)
    assert LLCAVE + len(llp) <= LL_HI, len(llp)
    c, l, t, h = (CAVE - VA2FILE, LLCAVE - VA2FILE, THCAVE - VA2FILE,
                  H_SITE - VA2FILE)
    assert dv[h] == 0xE8, "pump hook missing - apply build_wheel_vcl_pump first"
    assert dv[c] == 0x60, "pump cave missing (%02x)" % dv[c]
    assert dv[l] == 0x55, "LL cave missing (%02x)" % dv[l]
    assert dv[t] == 0x55, "hook-thread cave missing (%02x)" % dv[t]
    hits = reloc_hits(bytes(dv), [(c, c+len(pump)), (l, l+len(llp))])
    assert not hits, [hex(x) for x in hits]

    # ---- write ----
    for va, blob, _ in caves:
        o = va - CODE_OFF
        di[o:o+len(blob)] = blob
    di[hc:hc+H_CLR_OLDLEN] = want_new
    di[hs:hs+len(H_SLD_OLD)] = slds_new
    di[hb:hb+len(H_BTN_OLD)] = btn_new
    dv[c:c+len(pump)] = pump
    dv[l:l+len(llp)] = llp
    print("aowInt: CLR2 %dB @0x%X, SLD %dB @0x%X, WheelPower %dB @0x%X"
          % (len(clr2), CLR2_CAVE, len(sld), SLD_CAVE, len(wpow), WPOWER_CAVE))
    print("        BTN %dB @0x%X, WheelUnit %dB @0x%X; latches @0x%X/0x%X-0x%X"
          % (len(btn), BTN_CAVE, len(wunit), WUNIT_CAVE, G_PSLIDER, G_UNEXT, G_UARMED))
    print("VCL30:  pump %dB @0x%X, LLproc %dB @0x%X (rebuilt in place)"
          % (len(pump), CAVE, len(llp), LLCAVE))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, b in ((INT, INT_BAK), (VCL, VCL_BAK)):
        if not os.path.exists(b):
            shutil.copy2(f, b); print("Backup ->", os.path.basename(b))
    open(INT, 'wb').write(di)
    open(VCL, 'wb').write(dv)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
