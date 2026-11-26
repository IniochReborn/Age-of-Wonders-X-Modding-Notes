#!/usr/bin/env python3

r"""In-game mouse-wheel scrolling, part 1/2: aowInt.dpl scroll helper.



The in-game map-select / load-save dialog (TFileDlgWindow) is built from the

game's own widget toolkit in aowInt.dpl, not Win32 controls: FileLB/SaveLB/

DateLB are TAOWListBox, with TAOWVScrollBar siblings. So the shared VCL30

WS_VSCROLL wheel hook can't reach them (no HWND scrollbar exists).



This patch adds, inside aowInt.dpl:

  * g_hover  @ 0x5983E100 (DATA slack, writable, zero-filled)

      = the TAOWListBox the cursor is currently inside, or 0.

  * CLR hook @ TAOWWinManager.CheckMouseMove 0x59807094 (steals the 6-byte

      prologue): zeroes g_hover at the start of every mouse-move sweep.

  * SET hook @ TAOWListBox.CheckMouseMove inside-branch 0x598175C5 (steals the

      7-byte `mov [ebx+0x78],-1`): records g_hover = ebx (that listbox). This

      address is only reached when the cursor is INSIDE the list.

  * WheelScroll(delta) @ 0x59822880 â€” stdcall, 1 arg, ret 4, eax=1 if it

      scrolled. Drives the game's own scroll path:

        vs = [listbox+0x118]                 (its TAOWVScrollBar)

        SetFPos(vs, vs.FPos -/+ 3)           @0x5980CA28 (clamps internally)

        TAOWListBox.Update(listbox)          @0x59817138 (repaints from FPos)

      Wheel up (delta>0) => FPos-3, down => FPos+3. 3 lines/notch.



Part 2 (build_wheel_vcl_pump.py) calls WheelScroll from the VCL message pump.

This half is inert on its own (only tracks hover), so it is safe to apply

alone. All caves are position-independent (call/pop delta); intra-module calls

are rel32, so a rebased aowInt still works.



Backup: aowInt.dpl.bak_wheel. Dry-run default; --apply / --revert.

"""

import os, shutil, struct, sys



GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(

    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DPL = os.path.join(GAME, "aowInt.dpl")

BAK = DPL + ".bak_wheel"



CODE_OFF = 0x59800C00          # CODE: file = VA - this

DATA_OFF = 0x59801A00          # DATA: file = VA - this

G_HOVER  = 0x5983E100          # DATA slack (476B of zeros from 0x5983E024)



CLR_CAVE, SET_CAVE, HELP_CAVE = 0x59822800, 0x59822840, 0x59822880

CAVE_END = 0x59823600   # CODE tail zeros run 0x598229B9..0x5983D200 (~107 KB)



H_CLR = 0x59807094             # TAOWWinManager.CheckMouseMove entry

H_CLR_OLD = bytes.fromhex("558bec83c4f4")           # push ebp;mov ebp,esp;add esp,-0xC

H_SET = 0x598175C5             # TAOWListBox.CheckMouseMove, cursor-inside branch
H_SET2 = 0x5981A29A            # TAOWMemo.CheckMouseMove, cursor-inside branch
SET2_CAVE = 0x59823200         # (helper is large; keep well clear of it)

H_SET_OLD = bytes.fromhex("c74378ffffffff")          # mov dword [ebx+0x78],-1



F_SETFPOS = 0x5980CA28         # TAOWScrollBar.SetFPos(eax=self, edx=newpos)

F_UPDATE  = 0x59817138         # TAOWListBox.Update(eax=self)

F_SETLISTOFF = 0x598168F4      # TAOWListBox.SetListOff(eax=self, edx=off) — clamps

LB_LISTOFF = 0x15C             # TAOWListBox current top-item offset
LB_PARENT  = 0x10C             # TAOWControl -> parent component
COMP_CHILDREN = 0xD0           # TAoWComponent children TList (data +4, count +8)
CTRL_LEFT, CTRL_TOP = 0x84, 0x88
CTRL_WIDTH, CTRL_HEIGHT = 0x7C, 0x80
VMT_VSCROLLBAR = 0x5980C594    # AoWVScroll..TAOWVScrollBar class VMT
VMT_LISTBOX = 0x59815F9C       # AoWListBox..TAOWListBox
VMT_MEMO    = 0x5981848C       # AoWMemo..TAOWMemo (unit description tab)
MEMO_VSCROLL = 0x120           # TAOWMemo -> its scrollbar (listbox uses 0x118)
MEMO_LISTOFF = 0x128           # TAOWMemo top-line offset (listbox uses 0x15c)
F_MEMO_UPDATE = 0x59819B18     # TAOWMemo.Update
F_MEMO_SETLISTOFF = 0x59819298 # TAOWMemo.SetListOff
# --- leader-setup portrait cycling ---
G_FACENEXT = 0x5983E104        # FaceNextBtn under the cursor's window (or 0)
G_FACEPREV = 0x5983E108        # FacePrevBtn
H_SET3 = 0x59815882            # TAOWImage.CheckMouseMove, cursor-inside branch
H_SET3_OLD = bytes.fromhex('8a83c0000000')   # mov al,[ebx+0xc0]
SET3_CAVE = 0x59823400
VMT_BUTTON = 0x59810DC0        # AoWButton..TAOWButton
BTN_EVT_CODE, BTN_EVT_HIWD, BTN_EVT_DATA = 0x138, 0x13A, 0x13C
# AoWx.exe is a Delphi 3 image with no .reloc, so it always loads at
# 0x400000 -> these handler addresses identify the buttons reliably.
FACE_NEXT_CLICK = 0x00416D54   # TLeaderSetupWin.FaceNextBtnClick
FACE_PREV_CLICK = 0x00416D0C   # TLeaderSetupWin.FacePrevBtnClick

LB_VSCROLL = 0x118             # TAOWListBox -> its scrollbar

SB_FPOS    = 0x148             # TAOWScrollBar.FPos
SB_EVT_CODE = 0x6C             # TAOWScrollBar.OnChange method ptr: code
SB_EVT_HIWD = 0x6E             # high word of that ptr (0 => unassigned)
SB_EVT_DATA = 0x70             # ...and its Self

LINES = 3

# --diag counters in aowInt DATA slack (476B zeros @0x5983E024)

DIAG = "--diag" in sys.argv

CNT = 0x5983E110      # +0 CLR hits, +4 SET hits, +8 WheelScroll calls,

                      # +0xC scrolled ok, +0x10 last hovered listbox





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
    def jcc32(self, op, n): # near conditional jump to a label (0F 8x rel32)
        self.db(0x0F, op); self.j32.append((len(self.buf), n)); self.dd(0)
    def jmp32(self, n):     # near jmp to a label (for out-of-range targets)
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





def build_clr():

    a = Asm(CLR_CAVE)

    a.db(0x53)                                  # push ebx

    a.delta(3)                                  # ebx = delta

    a.db(0xC7, 0x83); a.dd(G_HOVER); a.dd(0)    # mov dword [ebx+G_HOVER],0
    a.db(0xC7, 0x83); a.dd(G_FACENEXT); a.dd(0)
    a.db(0xC7, 0x83); a.dd(G_FACEPREV); a.dd(0)

    if DIAG:

        a.db(0xFF, 0x83); a.dd(CNT + 0)         # inc [ebx+CNT+0]

    a.db(0x5B)                                  # pop ebx

    a.db(0x55, 0x8B, 0xEC, 0x83, 0xC4, 0xF4)    # displaced prologue

    a.jmp(H_CLR + len(H_CLR_OLD))

    return a.fin()





def build_set():

    a = Asm(SET_CAVE)

    a.db(0x50)                                  # push eax (ebx = listbox, keep it)

    a.delta(0)                                  # eax = delta

    a.db(0x89, 0x98); a.dd(G_HOVER)             # mov [eax+G_HOVER],ebx

    if DIAG:

        a.db(0xFF, 0x80); a.dd(CNT + 4)         # inc [eax+CNT+4]

        a.db(0x89, 0x98); a.dd(CNT + 0x10)      # mov [eax+CNT+0x10],ebx

    a.db(0x58)                                  # pop eax

    a.db(0xC7, 0x43, 0x78); a.dd(0xFFFFFFFF)    # displaced: mov [ebx+0x78],-1

    a.jmp(H_SET + len(H_SET_OLD))

    return a.fin()





def build_set2():
    """Same hover latch as build_set, but for TAOWMemo (unit description tab).

    TAOWMemo.CheckMouseMove has the identical cursor-inside marker
    `mov dword [ebx+0x78],-1` @0x5981A29A with ebx = the memo, so the same
    7-byte steal works.
    """
    a = Asm(SET2_CAVE)
    a.db(0x50)                                  # push eax (ebx = memo, keep it)
    a.delta(0)                                  # eax = delta
    a.db(0x89, 0x98); a.dd(G_HOVER)             # mov [eax+G_HOVER],ebx
    if DIAG:
        a.db(0xFF, 0x80); a.dd(CNT + 4)
        a.db(0x89, 0x98); a.dd(CNT + 0x10)
    a.db(0x58)                                  # pop eax
    a.db(0xC7, 0x43, 0x78); a.dd(0xFFFFFFFF)    # displaced
    a.jmp(H_SET2 + len(H_SET_OLD))
    return a.fin()


def build_set3():
    """Hooked at TAOWImage.CheckMouseMove's cursor-inside branch (ebx = image).

    Leader customization has no scrollable control under the portrait, so there
    is nothing for the wheel to grab. Instead, while the cursor sits on ANY
    image, walk up to 3 parent levels and look for TAOWButtons whose OnClick
    handler is TLeaderSetupWin.FaceNext/FacePrevBtnClick. If found (i.e. this
    image belongs to the leader-setup screen) latch them, and WheelScroll will
    fire the appropriate one. Non-portrait images simply find nothing.

    Only objects whose VMT is TAOWButton are probed at +0x138, so this never
    reads past a smaller object.
    """
    a = Asm(SET3_CAVE)
    a.db(0x60)                                  # pushad (ebx still = image)
    a.delta(5)                                  # ebp = delta
    a.db(0xC7, 0x85); a.dd(G_FACENEXT); a.dd(0)
    a.db(0xC7, 0x85); a.dd(G_FACEPREV); a.dd(0)
    a.db(0x8B, 0xF3)                            # mov esi,ebx (node = image)
    a.db(0xBF); a.dd(3)                         # mov edi,3 (levels to climb)
    a.lab('lvl')
    a.db(0x8B, 0xB6); a.dd(LB_PARENT)           # mov esi,[esi+0x10c] (parent)
    a.db(0x85, 0xF6)
    a.jcc8(0x74, 'done')
    a.db(0x8B, 0x86); a.dd(COMP_CHILDREN)       # mov eax,[esi+0xd0]
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'nextlvl')
    a.db(0x8B, 0x48, 0x08)                      # mov ecx,[eax+8] count
    a.db(0x8B, 0x58, 0x04)                      # mov ebx,[eax+4] data
    a.lab('child')
    a.db(0x49)                                  # dec ecx
    a.jcc8(0x78, 'nextlvl')                     # js -> level exhausted
    a.db(0x8B, 0x04, 0x8B)                      # mov eax,[ebx+ecx*4]
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'child')
    a.db(0x8D, 0x95); a.dd(VMT_BUTTON)          # lea edx,[ebp+VMT_BUTTON]
    a.db(0x39, 0x10)                            # cmp [eax],edx
    a.jcc8(0x75, 'child')                       # not a button -> skip
    a.db(0x8B, 0x90); a.dd(BTN_EVT_CODE)        # mov edx,[eax+0x138] (OnClick)
    a.db(0x81, 0xFA); a.dd(FACE_NEXT_CLICK)
    a.jcc8(0x75, 'notnext')
    a.db(0x89, 0x85); a.dd(G_FACENEXT)
    a.jcc8(0xEB, 'child')
    a.lab('notnext')
    a.db(0x81, 0xFA); a.dd(FACE_PREV_CLICK)
    a.jcc8(0x75, 'child')
    a.db(0x89, 0x85); a.dd(G_FACEPREV)
    a.jcc8(0xEB, 'child')
    a.lab('nextlvl')
    a.db(0x4F)                                  # dec edi
    a.jcc8(0x75, 'lvl')
    a.lab('done')
    a.db(0x61)                                  # popad
    a.buf += H_SET3_OLD                         # displaced: mov al,[ebx+0xc0]
    a.jmp(H_SET3 + len(H_SET3_OLD))
    return a.fin()


def build_helper():
    """WheelScroll(delta) - stdcall(1 arg), ret 4, eax=1 if it scrolled.

    Scrolls the TAOWListBox under the cursor (g_hover). Three cases, in order:

    1. The list owns a scrollbar ([lb+0x118], e.g. the map-select list) - move
       its FPos and fire OnChange, exactly like clicking a scroll arrow.

    2. The list has NO scrollbar, but a TAOWVScrollBar SIBLING governs it.
       That is the hero level-up / leader-setup shape: the form hangs several
       parallel lists (abilities + their cost column) off ONE scrollbar, and
       THeroUpgradeDlg.AvailableAbilitiesSBChange @0x00447030 pushes SB.FPos
       into every list via SetListOff. Driving the list directly moves only the
       hovered column and leaves the cost list and the thumb behind, so find
       that scrollbar and drive IT - the form's own handler syncs the rest.
       Search: walk the list's parent's children ([parent+0xD0] TList) for an
       object whose VMT is TAOWVScrollBar, require its vertical span to overlap
       the list's, and take the nearest one at/right of the list's left edge
       (so the correct group's bar wins when a dialog has several).

    3. Neither - fall back to moving the list's own offset (SetListOff).
    """
    a = Asm(HELP_CAVE)
    a.db(0x55, 0x8B, 0xEC)                      # push ebp; mov ebp,esp
    a.db(0x83, 0xEC, 0x18)                      # sub esp,0x18 (locals; -0x14 = kind)
    a.db(0x53, 0x56, 0x57)                      # push ebx; push esi; push edi
    a.delta(3)                                  # ebx = load delta
    if DIAG:
        a.db(0xFF, 0x83); a.dd(CNT + 8)
    a.db(0x8B, 0xB3); a.dd(G_HOVER)             # mov esi,[ebx+G_HOVER]
    a.db(0x85, 0xF6)
    a.jcc32(0x85, 'havehover')
    if DIAG:
        a.db(0xFF, 0x83); a.dd(CNT + 0x18)
    # nothing scrollable under the cursor: leader-setup portrait cycling.
    # wheel up = previous face, wheel down = next face.
    a.db(0x8B, 0x4D, 0x08)                      # mov ecx,[ebp+8] (delta)
    a.db(0x85, 0xC9)
    a.jcc8(0x7E, 'facedown')
    a.db(0x8B, 0xBB); a.dd(G_FACEPREV)          # mov edi,[ebx+G_FACEPREV]
    a.jcc8(0xEB, 'facego')
    a.lab('facedown')
    a.db(0x8B, 0xBB); a.dd(G_FACENEXT)          # mov edi,[ebx+G_FACENEXT]
    a.lab('facego')
    a.db(0x85, 0xFF)
    a.jcc32(0x84, 'fail')
    a.db(0x66, 0x83, 0xBF); a.dd(BTN_EVT_HIWD); a.db(0x00)   # OnClick assigned?
    a.jcc32(0x84, 'fail')
    a.db(0x8B, 0xD7)                            # mov edx,edi (Sender)
    a.db(0x8B, 0x87); a.dd(BTN_EVT_DATA)        # mov eax,[edi+0x13c] (Self)
    a.db(0xFF, 0x97); a.dd(BTN_EVT_CODE)        # call [edi+0x138] (OnClick)
    a.jmp32('okexit')
    a.lab('havehover')
    # classify the hovered control: 0 = listbox, 1 = memo, 2 = other
    a.db(0x8B, 0x06)                            # mov eax,[esi] (its VMT)
    a.db(0x8D, 0x8B); a.dd(VMT_LISTBOX)         # lea ecx,[ebx+VMT_LISTBOX]
    a.db(0x3B, 0xC1)
    a.jcc8(0x75, 'notlb')
    a.db(0xC7, 0x45, 0xEC); a.dd(0)             # kind = 0
    a.db(0x8B, 0xBE); a.dd(LB_VSCROLL)          # edi = [esi+0x118]
    a.jcc8(0xEB, 'gotkind')
    a.lab('notlb')
    a.db(0x8D, 0x8B); a.dd(VMT_MEMO)            # lea ecx,[ebx+VMT_MEMO]
    a.db(0x3B, 0xC1)
    a.jcc8(0x75, 'notmemo')
    a.db(0xC7, 0x45, 0xEC); a.dd(1)             # kind = 1
    a.db(0x8B, 0xBE); a.dd(MEMO_VSCROLL)        # edi = [esi+0x120]
    a.jcc8(0xEB, 'gotkind')
    a.lab('notmemo')
    a.db(0xC7, 0x45, 0xEC); a.dd(2)             # kind = 2 (unknown class)
    a.db(0x33, 0xFF)                            # edi = 0
    a.lab('gotkind')
    a.db(0x85, 0xFF)
    a.jcc32(0x85, 'havesb')                     # already has a scrollbar
    # ---- case 2: hunt for the governing sibling scrollbar ----
    a.db(0x8B, 0x86); a.dd(LB_PARENT)           # mov eax,[esi+0x10c] (parent)
    a.db(0x85, 0xC0)
    a.jcc32(0x84, 'fallback')
    a.db(0x8B, 0x80); a.dd(COMP_CHILDREN)       # mov eax,[eax+0xd0] (children)
    a.db(0x85, 0xC0)
    a.jcc32(0x84, 'fallback')
    a.db(0x8B, 0x48, 0x08)                      # mov ecx,[eax+8] count
    a.db(0x89, 0x4D, 0xF4)                      # mov [ebp-0xC],ecx
    a.db(0x8B, 0x40, 0x04)                      # mov eax,[eax+4] data
    a.db(0x89, 0x45, 0xF8)                      # mov [ebp-8],eax
    a.db(0xC7, 0x45, 0xFC); a.dd(0)             # index = 0
    a.db(0xC7, 0x45, 0xF0); a.dd(0x7FFFFFFF)    # best dx = INT_MAX
    a.lab('scan')
    a.db(0x8B, 0x4D, 0xFC)                      # mov ecx,[ebp-4]
    a.db(0x3B, 0x4D, 0xF4)                      # cmp ecx,[ebp-0xC]
    a.jcc8(0x7D, 'scandone')
    a.db(0x8B, 0x45, 0xF8)                      # mov eax,[ebp-8]
    a.db(0x8B, 0x04, 0x88)                      # mov eax,[eax+ecx*4] (child)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'next')
    a.db(0x8B, 0x10)                            # mov edx,[eax] (child VMT)
    a.db(0x8D, 0x8B); a.dd(VMT_VSCROLLBAR)      # lea ecx,[ebx+VMT] (PIC)
    a.db(0x3B, 0xD1)                            # cmp edx,ecx
    a.jcc8(0x75, 'next')
    a.db(0x8B, 0x90); a.dd(CTRL_TOP)            # mov edx,[eax+0x88] ch.top
    a.db(0x8B, 0x8E); a.dd(CTRL_TOP)            # mov ecx,[esi+0x88] lb.top
    a.db(0x03, 0x8E); a.dd(CTRL_HEIGHT)         # add ecx,[esi+0x80] lb.bottom
    a.db(0x3B, 0xD1)
    a.jcc8(0x7D, 'next')                        # ch.top >= lb.bottom -> no overlap
    a.db(0x03, 0x90); a.dd(CTRL_HEIGHT)         # add edx,[eax+0x80] ch.bottom
    a.db(0x3B, 0x96); a.dd(CTRL_TOP)            # cmp edx,[esi+0x88]
    a.jcc8(0x7E, 'next')                        # ch.bottom <= lb.top -> no overlap
    a.db(0x8B, 0x90); a.dd(CTRL_LEFT)           # mov edx,[eax+0x84]
    a.db(0x2B, 0x96); a.dd(CTRL_LEFT)           # sub edx,[esi+0x84]
    a.jcc8(0x78, 'next')                        # left of the list -> skip
    a.db(0x3B, 0x55, 0xF0)                      # cmp edx,[ebp-0x10]
    a.jcc8(0x7D, 'next')
    a.db(0x89, 0x55, 0xF0)                      # best dx = dx
    a.db(0x8B, 0xF8)                            # mov edi,eax (best)
    a.lab('next')
    a.db(0xFF, 0x45, 0xFC)                      # inc index
    a.jcc8(0xEB, 'scan')
    a.lab('scandone')
    a.db(0x85, 0xFF)
    a.jcc32(0x84, 'fallback')
    if DIAG:
        a.db(0xFF, 0x83); a.dd(CNT + 0x20)      # sibling scrollbar found
    # ---- scrollbar path (cases 1 & 2) ----
    a.lab('havesb')
    a.db(0x8B, 0x97); a.dd(SB_FPOS)             # mov edx,[edi+0x148] FPos
    a.db(0x8B, 0x4D, 0x08)                      # mov ecx,[ebp+8] delta
    a.db(0x85, 0xC9)
    a.jcc8(0x7E, 'down')
    a.db(0x83, 0xEA, LINES)                     # wheel up -> FPos-3
    a.jcc8(0xEB, 'doit')
    a.lab('down')
    a.db(0x83, 0xC2, LINES)                     # wheel down -> FPos+3
    a.lab('doit')
    a.db(0x8B, 0xC7)                            # mov eax,edi
    a.call(F_SETFPOS)
    a.db(0x66, 0x83, 0xBF); a.dd(SB_EVT_HIWD); a.db(0x00)
    a.jcc8(0x74, 'noevt')
    if DIAG:
        a.db(0xFF, 0x83); a.dd(CNT + 0x1C)      # OnChange fired
    a.db(0x8B, 0xD7)                            # mov edx,edi (Sender)
    a.db(0x8B, 0x87); a.dd(SB_EVT_DATA)         # mov eax,[edi+0x70] (Self)
    a.db(0xFF, 0x97); a.dd(SB_EVT_CODE)         # call [edi+0x6c] OnChange
    a.lab('noevt')
    a.db(0x83, 0x7D, 0xEC, 0x01)                # cmp dword [ebp-0x14],1
    a.jcc8(0x74, 'upmemo')
    a.jcc8(0x7F, 'okexit')                      # kind 2: nothing to refresh
    a.db(0x8B, 0xC6)
    a.call(F_UPDATE)                            # TAOWListBox.Update
    a.jcc8(0xEB, 'okexit')
    a.lab('upmemo')
    a.db(0x8B, 0xC6)
    a.call(F_MEMO_UPDATE)                       # TAOWMemo.Update
    a.jcc8(0xEB, 'okexit')
    # ---- case 3 ----
    a.lab('fallback')
    if DIAG:
        a.db(0xFF, 0x83); a.dd(CNT + 0x14)
    a.db(0x83, 0x7D, 0xEC, 0x01)                # cmp kind,1
    a.jcc8(0x74, 'fmemo')
    a.jcc32(0x8F, 'fail')                       # kind 2: cannot scroll it
    a.db(0x8B, 0x96); a.dd(LB_LISTOFF)          # mov edx,[esi+0x15c]
    a.jcc8(0xEB, 'fcalc')
    a.lab('fmemo')
    a.db(0x8B, 0x96); a.dd(MEMO_LISTOFF)        # mov edx,[esi+0x128]
    a.lab('fcalc')
    a.db(0x8B, 0x4D, 0x08)                      # mov ecx,[ebp+8]
    a.db(0x85, 0xC9)
    a.jcc8(0x7E, 'fdown')
    a.db(0x83, 0xEA, LINES)
    a.jcc8(0xEB, 'fdo')
    a.lab('fdown')
    a.db(0x83, 0xC2, LINES)
    a.lab('fdo')
    a.db(0x8B, 0xC6)                            # mov eax,esi
    a.db(0x83, 0x7D, 0xEC, 0x01)                # cmp kind,1
    a.jcc8(0x74, 'fsetmemo')
    a.call(F_SETLISTOFF)
    a.jcc8(0xEB, 'okexit')
    a.lab('fsetmemo')
    a.call(F_MEMO_SETLISTOFF)
    a.lab('okexit')
    if DIAG:
        a.db(0xFF, 0x83); a.dd(CNT + 0xC)
    a.db(0xB8); a.dd(1)                         # mov eax,1
    a.jcc8(0xEB, 'exit')
    a.lab('fail')
    a.db(0x33, 0xC0)                            # xor eax,eax
    a.lab('exit')
    a.db(0x5F, 0x5E, 0x5B)                      # pop edi; pop esi; pop ebx
    a.db(0x8B, 0xE5, 0x5D)                      # mov esp,ebp; pop ebp
    a.db(0xC2, 0x04, 0x00)                      # ret 4
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

            shutil.copy2(BAK, DPL); print("restored aowInt.dpl"); return 0

        print("no backup"); return 1

    d = bytearray(open(DPL, 'rb').read())

    clr, st, hp, st2 = build_clr(), build_set(), build_helper(), build_set2()
    st3 = build_set3()

    parts = [(CLR_CAVE, clr), (SET_CAVE, st), (HELP_CAVE, hp), (SET2_CAVE, st2),
             (SET3_CAVE, st3)]

    for va, blob in parts:

        assert va + len(blob) <= CAVE_END, (hex(va), len(blob))

    hc, hs, hs2 = H_CLR - CODE_OFF, H_SET - CODE_OFF, H_SET2 - CODE_OFF
    hs3 = H_SET3 - CODE_OFF

    rngs = [(hc, hc+len(H_CLR_OLD)), (hs, hs+len(H_SET_OLD)), (hs2, hs2+len(H_SET_OLD)),
            (hs3, hs3+len(H_SET3_OLD))]

    rngs += [(va - CODE_OFF, va - CODE_OFF + len(b)) for va, b in parts]

    rngs.append((G_HOVER - DATA_OFF, G_HOVER - DATA_OFF + 4))

    hits = reloc_hits(bytes(d), rngs)

    assert not hits, [hex(x) for x in hits]

    # hook sites

    cur = bytes(d[hc:hc+len(H_CLR_OLD)])

    assert cur == H_CLR_OLD or cur[0] == 0xE9, cur.hex()

    cur = bytes(d[hs:hs+len(H_SET_OLD)])

    assert cur == H_SET_OLD or cur[0] == 0xE9, cur.hex()

    # caves must be free (or already ours)

    for va, blob in parts:

        o = va - CODE_OFF

        seg = bytes(d[o:o+len(blob)])

        assert seg == bytes(len(blob)) or seg[:1] in (b'\x53', b'\x50', b'\x55', b'\x60'), seg[:8].hex()

    g = G_HOVER - DATA_OFF

    assert bytes(d[g:g+4]) == b'\0\0\0\0', "g_hover slot not free"

    for va, blob in parts:

        o = va - CODE_OFF

        d[o:o+len(blob)] = blob

    d[hc:hc+len(H_CLR_OLD)] = bytes([0xE9]) + (CLR_CAVE - (H_CLR+5)).to_bytes(4, 'little', signed=True) + b'\x90'

    d[hs:hs+len(H_SET_OLD)] = bytes([0xE9]) + (SET_CAVE - (H_SET+5)).to_bytes(4, 'little', signed=True) + b'\x90\x90'
    d[hs2:hs2+len(H_SET_OLD)] = bytes([0xE9]) + (SET2_CAVE - (H_SET2+5)).to_bytes(4, 'little', signed=True) + b'\x90\x90'
    d[hs3:hs3+len(H_SET3_OLD)] = bytes([0xE9]) + (SET3_CAVE - (H_SET3+5)).to_bytes(4, 'little', signed=True) + b'\x90'

    print("aowInt: CLR %dB @0x%X, SET %dB @0x%X, WheelScroll %dB @0x%X; g_hover @0x%X"

          % (len(clr), CLR_CAVE, len(st), SET_CAVE, len(hp), HELP_CAVE, G_HOVER))

    if not apply:

        print("Dry run OK â€” rerun with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):

        shutil.copy2(DPL, BAK); print("Backup ->", os.path.basename(BAK))

    open(DPL, 'wb').write(d)

    print("Written.")

    return 0





if __name__ == "__main__":

    sys.exit(main())

