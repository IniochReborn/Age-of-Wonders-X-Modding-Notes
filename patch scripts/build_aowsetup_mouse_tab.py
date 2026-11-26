#!/usr/bin/env python3
r"""AoWSetup "Mouse" tab, stage 2a: DISPLAY the mouse-chord bindings + RESET.

Adds a new 'Mouse' page to AoWSetup's Settings (next to the Developer tab):
  - shows the current chord->key bindings, read live from the 20-byte VK
    table that build_mouse_chords.py keeps in VCL30.dpl (.idata, file offset
    0xE4770) - the game reads the same bytes at startup, so this file IS the
    configuration store;
  - a 'Reset bindings to default' checkbox: if ticked when Settings is
    closed with OK, the default table is written back into VCL30.dpl
    (guarded: only when the table is present, i.e. the chords patch is
    applied and the file is not locked by a running game);
  - a note that changes apply on the next game launch.
(Stage 2b - editing individual bindings - builds on the same plumbing.)

MACHINERY (all patterns proven by build_aowsetup_installcheck_devtab.py):
  - controls are created AT RUNTIME, lazily, on first Settings open;
  - a whole new TTabSheet is constructed (ctor [VMT+0x24], Owner=form),
    parented to MainPageControl (form+0x1E8) via TControl.SetParent
    ([vmt+0x3C] - TTabSheet's override inserts it as a page), captioned via
    TControl.SetText 0x41CA24;
  - children (TLabels + the TCheckBox) come from a DATA-DRIVEN layout table
    walked by one creation loop;
  - tab visibility follows the Developer tab: the three settings hooks
    (SettingsBtnClick/OK/Cancel sites, currently jmp'ing to the devtab
    caves SHOW/HIDEOK/HIDECAN) are re-pointed to our caves, which do the
    Mouse work and tail-jump into the devtab caves (which replay the
    displaced bytes and resume) - both patches stay independent;
  - VCL30.dpl is located next to AoWSetup.exe via GetModuleFileNameA.

Verified addresses (TCheckBox ctor re-derived = devtab's constant, method
validated): TTabSheet VMT 0x438D18 ctor 0x43A0A8, TLabel VMT 0x42DD08 ctor
0x431CEC, TCheckBox VMT 0x430368 ctor 0x4345D4, SetText 0x41CA24,
SetTabVisible 0x43A32C, Get/SetChecked 0x434694/0x4346B4, SetParent slot
+0x3C, SetBounds slot +0x4C, MainPageControl @form+0x1E8. kernel32 IAT:
GetModuleFileNameA [0x46C158], CreateFileA [0x46C194], ReadFile [0x46C180],
WriteFile [0x46C170], SetFilePointer [0x46C174], CloseHandle [0x46C198].

All code/data/vars live in a NEW appended section '.xmou' @VA 0x510000
(0x2000, RWX; the exe is fixed-base with no DYNAMIC_BASE, so absolute
addresses are safe - same rationale as the devtab patch).

Usage: dry-run default; --apply / --revert. Backup: AoWSetup.exe.bak_mousetab
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_mousetab"

SEC_VA = 0x510000
SEC_SIZE = 0x2000
SEC_NAME = b".xmou\x00\x00\x00"

# ---- engine/VCL constants (see docstring) ----
SHEET_VMT, SHEET_CTOR = 0x438D18, 0x43A0A8
LBL_VMT, LBL_CTOR = 0x42DD08, 0x431CEC
EDIT_VMT, EDIT_CTOR = 0x42E384, 0x43224C
BTN_VMT, BTN_CTOR = 0x42FCEC, 0x434314
PNL_VMT, PNL_CTOR = 0x436254, 0x4373D0     # 2px-high TPanel = divider line
SETTEXT = 0x41CA24
GETTEXT = 0x41C9F4          # (eax=ctrl, edx=@AnsiString out)
LSTRCLR = 0x4037D0          # (eax=@AnsiString)
SETTABVIS = 0x43A32C
SETACTIVEPAGE = 0x43A774    # TPageControl.SetActivePage (eax=pc, edx=sheet;
                            # from ActivePage PropInfo RTTI @file 0x385d9)
SETPAGECTL = 0x43A1E8       # TTabSheet.SetPageControl (SetParent + InsertPage)
OFF_ONCLICK = 0xA4          # TControl FOnClick TMethod {Code, +4 Data} (RTTI)
SLOT_SETPARENT, SLOT_SETBOUNDS = 0x3C, 0x4C
OFF_PAGECONTROL = 0x1E8

IAT_GMFN = 0x46C158
IAT_CREATEFILE = 0x46C194
IAT_READFILE = 0x46C180
IAT_WRITEFILE = 0x46C170
IAT_SETFP = 0x46C174
IAT_CLOSE = 0x46C198

# devtab caves we chain into + the three hook sites we re-point
DT_SHOW, DT_HIDEOK, DT_HIDECAN = 0x46AF40, 0x46AF80, 0x469990
SBTN_VA, OK_VA, CAN_VA = 0x4689F4, 0x469090, 0x469344
CODE_D = 0x400C00

# VCL30 chord table (see build_mouse_chords.py)
VCL30_TAB_FOFF = 0xE4770
DEFAULT_TAB = bytes([
    0x26, ord('P'), 0x21,  0x28, ord('N'), 0x22,
    0x25, ord('D'), ord('D'),  0x27, ord('D'), ord('D'),
    0x74, ord('C'), ord('C'),
    ord('L'), 0x1B, 0x73, ord('E'), 0])

VK_NAMES = {0: '-', 0x08: 'Bksp', 0x09: 'Tab', 0x0D: 'Enter', 0x1B: 'Esc',
            0x20: 'Space', 0x21: 'PgUp', 0x22: 'PgDn', 0x23: 'End',
            0x24: 'Home', 0x25: 'Left', 0x26: 'Up', 0x27: 'Right',
            0x28: 'Down', 0x2D: 'Ins', 0x2E: 'Del', 0x11: 'Ctrl'}
for _c in range(26):
    VK_NAMES[0x41 + _c] = chr(ord('A') + _c)
for _c in range(10):
    VK_NAMES[0x30 + _c] = chr(ord('0') + _c)
for _c in range(12):
    VK_NAMES[0x70 + _c] = 'F%d' % (_c + 1)

# layout: (text, left, top, width, kind, tabidx)
# kind 0=label, 1=EDIT (editable binding), 2=Reset BUTTON, 3=divider (TPanel)
# MainPageControl is 384x382 (DFM) -> sheet client ~376x352: keep every
# control's right edge <= 370 and bottom <= 352.
ROWS = ['Wheel up', 'Wheel down', 'Tilt left', 'Tilt right', 'Middle click']
COMBOS = ['Mouse4 (Back) + Left click', 'Mouse4 (Back) + Right click',
          'Mouse4 (Back) + Mouse5 (Fwd)', 'Mouse5 (Fwd) + L+R  (Ctrl+key)']
COLX = (120, 205, 290)
LAYOUT = [('Plain', COLX[0], 8, 60, 0, 0),
          ('Mouse4 (Back)', COLX[1], 8, 84, 0, 0),
          ('Mouse5 (Fwd)', COLX[2], 8, 80, 0, 0)]
for i, r in enumerate(ROWS):
    y = 30 + 22 * i
    LAYOUT.append((r, 6, y, 110, 0, 0))
    for c in range(3):
        LAYOUT.append(('?', COLX[c], y, 80, 1, i * 3 + c))
LAYOUT.append((' ', 6, 142, 358, 3, 0))           # ---- divider ----
for j, r in enumerate(COMBOS):
    y = 150 + 24 * j
    LAYOUT.append((r, 6, y, 196, 0, 0))
    LAYOUT.append(('?', COLX[2], y, 80, 1, 15 + j))
LAYOUT.append((' ', 6, 248, 358, 3, 0))           # ---- divider ----
LAYOUT.append(('Key meanings: see the Hotkeys tab.', 6, 256, 220, 0, 0))
LAYOUT.append(('Changes apply on the next game launch.', 6, 274, 235, 0, 0))
LAYOUT.append(('Reset to defaults', 250, 260, 115, 2, 0))

# ---- second tab: vanilla hotkey reference (user-supplied list) ----
HK1 = ['Arrows - scroll the map',
       'PgUp / PgDn - map level up / down',
       'N or . - select next unit / army',
       'P or , - select prev. unit / army',
       'H - select next hero',
       'L - select leader',
       'C - center on selected unit / army',
       'D - party done for the current turn',
       'G - guard on / off',
       'M - move selected unit(s)']
HK2 = ['Ctrl+Enter or Ctrl+E - end turn',
       'Esc - quits most screens',
       'F3 or Ctrl+O - open / load game',
       'F4 or Ctrl+S - save game',
       'F5 - toggle hex grid on / off',
       'F1 - recall last tutorial tip',
       'O - observe enemy movement on / off',
       'Shift - select multiple parties / units',
       'Alt+Enter - full screen / windowed',
       '"-" in a binding disables that chord']
LAYOUT2 = [('Vanilla game hotkeys:', 6, 8, 200, 0, 0)]
for k in range(10):
    y = 32 + 17 * k
    LAYOUT2.append((HK1[k], 6, y, 180, 0, 0))
    LAYOUT2.append((HK2[k], 192, y, 176, 0, 0))


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.j32 = []; self.fix = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF)
    def dw(self, v): self.buf += struct.pack("<H", v & 0xFFFF)
    def call_abs(self, t):     # direct rel32 to a fixed exe address
        self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4))
    def call_lab(self, n): self.db(0xE8); self.j32.append((len(self.buf), n)); self.dd(0)
    def jmp_abs(self, t):
        self.db(0xE9); self.buf += struct.pack("<i", t - (self.here() + 4))
    def jmp_lab(self, n): self.db(0xE9); self.j32.append((len(self.buf), n)); self.dd(0)
    def jcc(self, cc8, n):
        self.db(0x0F, cc8 + 0x10); self.j32.append((len(self.buf), n)); self.dd(0)
    def lab(self, n):
        assert n not in self.labels, n
        self.labels[n] = len(self.buf)
    def ref(self, n):          # absolute dword of a label (fixed up later)
        self.fix.append((len(self.buf), n)); self.dd(0)
    def align(self, k):
        while len(self.buf) % k:
            self.db(0)
    def la(self, n): return None  # placeholder
    def fin(self, limit):
        for off, n in self.j32:
            t = self.base + self.labels[n]
            self.buf[off:off+4] = struct.pack("<i", t - (self.base + off + 4))
        for off, n in self.fix:
            self.buf[off:off+4] = struct.pack("<I", self.base + self.labels[n])
        assert len(self.buf) <= limit, hex(len(self.buf))
        return bytes(self.buf)


def build_section():
    a = Asm(SEC_VA)

    # ================= my_show: from SettingsBtnClick site =================
    # site regs: eax = form (site original code preserved by devtab SHOW cave)
    a.lab('my_show')
    a.db(0x50, 0x52, 0x53)                  # push eax/edx/ebx
    a.call_lab('ensure')                    # eax=form (creates once)
    a.call_lab('refresh')
    a.db(0xA1); a.ref('g_sheet')            # mov eax,[g_sheet]
    a.db(0x85, 0xC0); a.jcc(0x74, 'ms_no')
    a.db(0xB2, 0x01)                        # dl = 1 (visible)
    a.call_abs(SETTABVIS)
    a.db(0xA1); a.ref('g_sheet2')
    a.db(0x85, 0xC0); a.jcc(0x74, 'ms_no')
    a.db(0xB2, 0x01)
    a.call_abs(SETTABVIS)
    a.lab('ms_no')
    # force the Settings sheet active: creating/showing our pages can leave
    # 'Mouse' selected, and the selection persists on the live form between
    # opens — the user expects Settings each time (fix 2026-08-23)
    a.db(0x8B, 0x44, 0x24, 0x08)            # mov eax,[esp+8] (form, saved)
    a.db(0x8B, 0x90); a.dd(0x1EC)           # mov edx,[eax+0x1EC] SettingsSheet
    a.db(0x8B, 0x80); a.dd(OFF_PAGECONTROL) # mov eax,[eax+0x1E8] MainPageControl
    a.db(0x85, 0xD2); a.jcc(0x74, 'ms_pop')
    a.db(0x85, 0xC0); a.jcc(0x74, 'ms_pop')
    a.call_abs(SETACTIVEPAGE)
    a.lab('ms_pop')
    a.db(0x5B, 0x5A, 0x58)                  # pop ebx/edx/eax
    a.jmp_abs(DT_SHOW)                      # devtab: show its tabs + replay

    # ================= my_hideok: from SettingsOk site =====================
    a.lab('my_hideok')
    a.db(0x50, 0x52, 0x53)
    a.call_lab('apply_edits')               # parse edit boxes -> write file
    a.db(0xA1); a.ref('g_sheet')
    a.db(0x85, 0xC0); a.jcc(0x74, 'mo_no')
    a.db(0x32, 0xD2)                        # dl = 0 (hide tab)
    a.call_abs(SETTABVIS)
    a.db(0xA1); a.ref('g_sheet2')
    a.db(0x85, 0xC0); a.jcc(0x74, 'mo_no')
    a.db(0x32, 0xD2)
    a.call_abs(SETTABVIS)
    a.lab('mo_no')
    a.db(0x5B, 0x5A, 0x58)
    a.jmp_abs(DT_HIDEOK)

    # ================= my_hidecan: from SettingsCancel site ================
    a.lab('my_hidecan')
    a.db(0x50, 0x52)
    a.db(0xA1); a.ref('g_sheet')
    a.db(0x85, 0xC0); a.jcc(0x74, 'mc_no')
    a.db(0x32, 0xD2)
    a.call_abs(SETTABVIS)
    a.db(0xA1); a.ref('g_sheet2')
    a.db(0x85, 0xC0); a.jcc(0x74, 'mc_no')
    a.db(0x32, 0xD2)
    a.call_abs(SETTABVIS)
    a.lab('mc_no')
    a.db(0x5A, 0x58)
    a.jmp_abs(DT_HIDECAN)

    # ================= ensure(eax=form): create sheets + controls once =====
    a.lab('ensure')
    a.db(0x83, 0x3D); a.ref('g_sheet'); a.db(0x00)   # cmp [g_sheet],0
    a.jcc(0x75, 'en_done')
    a.db(0x53, 0x56, 0x57, 0x55)            # push ebx/esi/edi/ebp
    a.db(0x8B, 0xE8)                        # mov ebp,eax (form)
    # ---- sheet 1: Mouse ----
    a.db(0x8B, 0xCD)                        # mov ecx,ebp (Owner)
    a.db(0xB2, 0x01)                        # mov dl,1
    a.db(0xB8); a.dd(SHEET_VMT)
    a.call_abs(SHEET_CTOR)                  # -> eax = sheet
    a.db(0xA3); a.ref('g_sheet')
    a.db(0xA3); a.ref('g_cursheet')
    a.db(0xBA); a.ref('s_mouse')
    a.call_abs(SETTEXT)                     # caption (eax=sheet from ctor)
    # attach to MainPageControl. ⚠ NOT plain SetParent: in this VCL,
    # TTabSheet.SetPageControl @0x43A1E8 (eax=sheet, edx=pagecontrol) does
    # SetParent AND TPageControl.InsertPage @0x43A648 - only then does the
    # page join FPages/the tab strip (found 2026-08-21: SetParent-only left
    # a fully-built but tab-less sheet).
    a.db(0xA1); a.ref('g_sheet')
    a.db(0x8B, 0x95); a.dd(OFF_PAGECONTROL)  # mov edx,[ebp+0x1E8]
    a.call_abs(0x43A1E8)                    # TTabSheet.SetPageControl
    a.db(0xBE); a.ref('layout')             # mov esi, layout
    a.call_lab('en_loop')
    # ---- sheet 2: Hotkeys reference ----
    a.db(0x8B, 0xCD)
    a.db(0xB2, 0x01)
    a.db(0xB8); a.dd(SHEET_VMT)
    a.call_abs(SHEET_CTOR)
    a.db(0xA3); a.ref('g_sheet2')
    a.db(0xA3); a.ref('g_cursheet')
    a.db(0xBA); a.ref('s_hotkeys')
    a.call_abs(SETTEXT)
    a.db(0xA1); a.ref('g_sheet2')
    a.db(0x8B, 0x95); a.dd(OFF_PAGECONTROL)
    a.call_abs(0x43A1E8)
    a.db(0xBE); a.ref('layout2')
    a.call_lab('en_loop')
    a.db(0x5D, 0x5F, 0x5E, 0x5B)            # pop ebp/edi/esi/ebx
    a.lab('en_done')
    a.db(0xC3)

    # ---- creation loop subroutine: esi=layout table, parent=[g_cursheet] ---
    a.lab('en_loop')
    a.db(0x8B, 0x06)                        # mov eax,[esi] (text)
    a.db(0x85, 0xC0); a.jcc(0x74, 'en_fin')
    # class select by kind: 0 label / 1 edit / 2 button / 3 divider panel
    a.db(0x8A, 0x4E, 0x0A)                  # mov cl, [esi+0xA] (kind)
    a.db(0x80, 0xF9, 0x01); a.jcc(0x74, 'en_ed')
    a.db(0x80, 0xF9, 0x02); a.jcc(0x74, 'en_bt')
    a.db(0x80, 0xF9, 0x03); a.jcc(0x74, 'en_pn')
    a.db(0xB8); a.dd(LBL_VMT)
    a.db(0xBB); a.dd(LBL_CTOR)
    a.db(0xB1, 0x11)                        # mov cl,17 (height)
    a.jmp_lab('en_mk')
    a.lab('en_ed')
    a.db(0xB8); a.dd(EDIT_VMT)
    a.db(0xBB); a.dd(EDIT_CTOR)
    a.db(0xB1, 0x15)                        # 21
    a.jmp_lab('en_mk')
    a.lab('en_bt')
    a.db(0xB8); a.dd(BTN_VMT)
    a.db(0xBB); a.dd(BTN_CTOR)
    a.db(0xB1, 0x14)                        # 20
    a.jmp_lab('en_mk')
    a.lab('en_pn')
    a.db(0xB8); a.dd(PNL_VMT)
    a.db(0xBB); a.dd(PNL_CTOR)
    a.db(0xB1, 0x02)                        # 2 (divider line)
    a.lab('en_mk')
    a.db(0x88, 0x0D); a.ref('hgt')          # mov [hgt],cl
    a.db(0x8B, 0xCD)                        # mov ecx,ebp (Owner=form)
    a.db(0xB2, 0x01)                        # dl = 1
    a.db(0xFF, 0xD3)                        # call ebx (ctor) -> eax
    a.db(0x8B, 0xD8)                        # mov ebx,eax (inst)
    # SetParent(current sheet)
    a.db(0x8B, 0x15); a.ref('g_cursheet')   # mov edx,[g_cursheet]
    a.db(0x8B, 0x08)                        # mov ecx,[eax]
    a.db(0xFF, 0x51, SLOT_SETPARENT)
    # SetBounds(left, top, w, h)
    a.db(0x0F, 0xB7, 0x46, 0x08)            # movzx eax, word [esi+8] (w)
    a.db(0x50)                              # push w
    a.db(0x0F, 0xB6, 0x05); a.ref('hgt')    # movzx eax, byte [hgt]
    a.db(0x50)                              # push h
    a.db(0x0F, 0xB7, 0x4E, 0x06)            # movzx ecx, word [esi+6] (top)
    a.db(0x0F, 0xB7, 0x56, 0x04)            # movzx edx, word [esi+4] (left)
    a.db(0x8B, 0xC3)                        # mov eax,ebx
    a.db(0x8B, 0x38)                        # mov edi,[eax]
    a.db(0xFF, 0x57, SLOT_SETBOUNDS)        # call [edi+0x4C]
    # SetText(text)
    a.db(0x8B, 0x16)                        # mov edx,[esi]
    a.db(0x8B, 0xC3)                        # mov eax,ebx
    a.call_abs(SETTEXT)
    # kind dispatch: 1 -> edit slot; 2 -> reset button + OnClick wiring
    a.db(0x8A, 0x46, 0x0A)                  # mov al, [esi+0xA] (kind)
    a.db(0x3C, 0x01); a.jcc(0x75, 'en_k2')
    a.db(0x0F, 0xB6, 0x46, 0x0B)            # movzx eax, byte [esi+0xB] (tabidx)
    a.db(0x89, 0x1C, 0x85); a.ref('g_vallab')  # mov [g_vallab+eax*4],ebx
    a.jmp_lab('en_next')
    a.lab('en_k2')
    a.db(0x3C, 0x02); a.jcc(0x75, 'en_next')
    a.db(0x89, 0x1D); a.ref('g_resetcb')    # mov [g_resetcb],ebx (button)
    # FOnClick := (reset_handler, button)
    a.db(0xC7, 0x83); a.dd(OFF_ONCLICK); a.ref('reset_handler')  # [ebx+A4]=Code
    a.db(0x89, 0x9B); a.dd(OFF_ONCLICK + 4)                       # [ebx+A8]=Data
    a.lab('en_next')
    a.db(0x83, 0xC6, 0x0C)                  # add esi,12
    a.jmp_lab('en_loop')
    a.lab('en_fin')
    a.db(0xC3)                              # subroutine return

    # ================= reset_handler: TNotifyEvent(Data=btn, Sender) =======
    a.lab('reset_handler')
    a.call_lab('read_table')                # guard: table readable?
    a.db(0x84, 0xC0); a.jcc(0x74, 'rh_out')
    a.db(0xB8); a.ref('defaults')           # mov eax, defaults
    a.call_lab('write_buf')
    a.call_lab('refresh')
    a.lab('rh_out')
    a.db(0xC3)

    # ================= apply_edits: parse the 19 edit boxes, write =========
    a.lab('apply_edits')
    a.db(0x53, 0x56, 0x57)                  # push ebx/esi/edi
    a.call_lab('read_table')
    a.db(0x84, 0xC0); a.jcc(0x74, 'ae_out')
    a.db(0x33, 0xF6)                        # xor esi,esi (i)
    a.lab('ae_loop')
    a.db(0x83, 0xFE, 0x13); a.jcc(0x7D, 'ae_write')
    a.db(0x8B, 0x1C, 0xB5); a.ref('g_vallab')   # mov ebx,[g_vallab+esi*4]
    a.db(0x85, 0xDB); a.jcc(0x74, 'ae_next')
    a.db(0xC7, 0x05); a.ref('strvar'); a.dd(0)  # [strvar] := nil
    a.db(0xBA); a.ref('strvar')             # mov edx, @strvar
    a.db(0x8B, 0xC3)                        # mov eax,ebx
    a.call_abs(GETTEXT)
    a.db(0xA1); a.ref('strvar')             # mov eax,[strvar]
    a.db(0x85, 0xC0); a.jcc(0x74, 'ae_next')
    a.call_lab('parse_vk')                  # eax=chars -> eax=vk | -1
    a.db(0x83, 0xF8, 0xFF); a.jcc(0x74, 'ae_clr')
    a.db(0x88, 0x86); a.ref('tabbuf')       # mov [tabbuf+esi], al
    a.lab('ae_clr')
    a.db(0xB8); a.ref('strvar')             # mov eax, @strvar
    a.call_abs(LSTRCLR)
    a.lab('ae_next')
    a.db(0x46)                              # inc esi
    a.jmp_lab('ae_loop')
    a.lab('ae_write')
    a.db(0xB8); a.ref('tabbuf')
    a.call_lab('write_buf')
    a.lab('ae_out')
    a.db(0x5F, 0x5E, 0x5B, 0xC3)

    # ================= parse_vk: eax=chars -> eax = vk | -1 ================
    # case-insensitive match against the vknames table; '?' entries skipped
    a.lab('parse_vk')
    a.db(0x53, 0x56, 0x57, 0x55)            # push ebx/esi/edi/ebp
    a.db(0x8B, 0xE8)                        # mov ebp,eax (input)
    a.db(0x33, 0xDB)                        # xor ebx,ebx (vk)
    a.lab('pv_loop')
    a.db(0x81, 0xFB); a.dd(256); a.jcc(0x7D, 'pv_fail')
    a.db(0x8B, 0x3C, 0x9D); a.ref('vknames')    # mov edi,[vknames+ebx*4]
    a.db(0x80, 0x3F, 0x3F); a.jcc(0x74, 'pv_nx')  # skip '?' entries
    a.db(0x8B, 0xF5)                        # mov esi,ebp (input)
    a.lab('pv_cmp')
    a.db(0x8A, 0x06)                        # mov al,[esi]
    a.db(0x8A, 0x17)                        # mov dl,[edi]
    a.db(0x3C, 0x61); a.jcc(0x72, 'pv_u1')  # al < 'a'?
    a.db(0x3C, 0x7A); a.jcc(0x77, 'pv_u1')
    a.db(0x2C, 0x20)                        # sub al,0x20
    a.lab('pv_u1')
    a.db(0x80, 0xFA, 0x61); a.jcc(0x72, 'pv_u2')
    a.db(0x80, 0xFA, 0x7A); a.jcc(0x77, 'pv_u2')
    a.db(0x80, 0xEA, 0x20)                  # sub dl,0x20
    a.lab('pv_u2')
    a.db(0x3A, 0xC2); a.jcc(0x75, 'pv_nx')  # mismatch
    a.db(0x84, 0xC0); a.jcc(0x74, 'pv_hit') # both NUL -> match
    a.db(0x46, 0x47)                        # inc esi; inc edi
    a.jmp_lab('pv_cmp')
    a.lab('pv_nx')
    a.db(0x43)                              # inc ebx
    a.jmp_lab('pv_loop')
    a.lab('pv_hit')
    a.db(0x8B, 0xC3)                        # mov eax,ebx
    a.jmp_lab('pv_done')
    a.lab('pv_fail')
    a.db(0x83, 0xC8, 0xFF)                  # or eax,-1
    a.lab('pv_done')
    a.db(0x5D, 0x5F, 0x5E, 0x5B, 0xC3)

    # ================= refresh: read table file, update value labels =======
    a.lab('refresh')
    a.db(0x53, 0x56, 0x57)                  # push ebx/esi/edi
    a.call_lab('read_table')                # al=1 ok (tabbuf filled)
    a.db(0x84, 0xC0); a.jcc(0x74, 'rf_out')
    a.db(0x33, 0xF6)                        # xor esi,esi
    a.lab('rf_loop')
    a.db(0x83, 0xFE, 0x13); a.jcc(0x7D, 'rf_out')   # 19 slots (0..18)
    a.db(0x8B, 0x1C, 0xB5); a.ref('g_vallab')       # mov ebx,[g_vallab+esi*4]
    a.db(0x85, 0xDB); a.jcc(0x74, 'rf_next')
    a.db(0x0F, 0xB6, 0x86); a.ref('tabbuf')         # movzx eax, byte [tabbuf+esi]
    a.db(0x8B, 0x14, 0x85); a.ref('vknames')        # mov edx,[vknames+eax*4]
    a.db(0x8B, 0xC3)                        # mov eax,ebx
    a.call_abs(SETTEXT)
    a.lab('rf_next')
    a.db(0x46)                              # inc esi
    a.jmp_lab('rf_loop')
    a.lab('rf_out')
    a.db(0x5F, 0x5E, 0x5B, 0xC3)

    # ================= path builder (once) =================================
    a.lab('mkpath')
    a.db(0x80, 0x3D); a.ref('pathbuf'); a.db(0x00)  # cmp byte [pathbuf],0
    a.jcc(0x75, 'mp_done')
    a.db(0x57, 0x56)                        # push edi/esi
    a.db(0x68); a.dd(240)                   # push nSize
    a.db(0x68); a.ref('pathbuf')            # push buf
    a.db(0x6A, 0x00)                        # push 0 (self)
    a.db(0xFF, 0x15); a.dd(IAT_GMFN)        # GetModuleFileNameA -> eax=len
    a.db(0xBF); a.ref('pathbuf')            # mov edi, pathbuf
    a.db(0x03, 0xF8)                        # add edi,eax (points at NUL)
    a.lab('mp_scan')
    a.db(0x4F)                              # dec edi
    a.db(0x80, 0x3F, 0x5C)                  # cmp byte [edi],'\'
    a.jcc(0x75, 'mp_scan')
    a.db(0x47)                              # inc edi (past the backslash)
    a.db(0xBE); a.ref('s_vcl30')            # mov esi, "VCL30.dpl"
    a.db(0xB9); a.dd(10)                    # mov ecx,10 (incl NUL)
    a.db(0xF3, 0xA4)                        # rep movsb
    a.db(0x5E, 0x5F)                        # pop esi/edi
    a.lab('mp_done')
    a.db(0xC3)

    # ================= read_table -> al=1 ok ===============================
    a.lab('read_table')
    a.call_lab('mkpath')
    a.db(0x6A, 0x00)                        # hTemplate
    a.db(0x6A, 0x00)                        # flags
    a.db(0x6A, 0x03)                        # OPEN_EXISTING
    a.db(0x6A, 0x00)                        # security
    a.db(0x6A, 0x03)                        # share rw
    a.db(0x68); a.dd(0x80000000)            # GENERIC_READ
    a.db(0x68); a.ref('pathbuf')
    a.db(0xFF, 0x15); a.dd(IAT_CREATEFILE)
    a.db(0x83, 0xF8, 0xFF); a.jcc(0x74, 'rt_fail')
    a.db(0x50)                              # save handle (also arg use below)
    a.db(0x6A, 0x00)                        # FILE_BEGIN
    a.db(0x6A, 0x00)                        # lpDistHigh
    a.db(0x68); a.dd(VCL30_TAB_FOFF)        # offset
    a.db(0xFF, 0x74, 0x24, 0x0C)            # push handle
    a.db(0xFF, 0x15); a.dd(IAT_SETFP)
    a.db(0x6A, 0x00)                        # overlapped
    a.db(0x68); a.ref('gotbuf')             # &bytesRead
    a.db(0x6A, 0x14)                        # 20
    a.db(0x68); a.ref('tabbuf')
    a.db(0xFF, 0x74, 0x24, 0x10)            # push handle
    a.db(0xFF, 0x15); a.dd(IAT_READFILE)
    a.db(0xFF, 0x15 - 0x15)                 # (placeholder removed below)
    a.buf.pop(); a.buf.pop()                # undo placeholder bytes
    a.db(0xFF, 0x34, 0x24)                  # push handle (still on stack top)
    a.db(0xFF, 0x15); a.dd(IAT_CLOSE)       # CloseHandle
    a.db(0x58)                              # pop saved handle copy
    a.db(0xA1); a.ref('gotbuf')
    a.db(0x83, 0xF8, 0x14)                  # cmp eax,20
    a.jcc(0x75, 'rt_fail')
    a.db(0xB0, 0x01, 0xC3)                  # mov al,1; ret
    a.lab('rt_fail')
    a.db(0x32, 0xC0, 0xC3)                  # xor al,al; ret

    # ================= write_buf (eax = 20-byte source) ====================
    # ⚠ pure writer: callers guard with read_table FIRST (a guard-read here
    # would clobber tabbuf when apply_edits passes it as the source).
    a.lab('write_buf')
    a.db(0xA3); a.ref('wsrc')               # mov [wsrc], eax
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x03)                        # OPEN_EXISTING
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x00)                        # no sharing
    a.db(0x68); a.dd(0xC0000000)            # GENERIC_READ|WRITE
    a.db(0x68); a.ref('pathbuf')
    a.db(0xFF, 0x15); a.dd(IAT_CREATEFILE)
    a.db(0x83, 0xF8, 0xFF); a.jcc(0x74, 'wd_out')
    a.db(0x50)                              # save handle
    a.db(0x6A, 0x00)
    a.db(0x6A, 0x00)
    a.db(0x68); a.dd(VCL30_TAB_FOFF)
    a.db(0xFF, 0x74, 0x24, 0x0C)
    a.db(0xFF, 0x15); a.dd(IAT_SETFP)
    a.db(0x6A, 0x00)
    a.db(0x68); a.ref('gotbuf')
    a.db(0x6A, 0x14)
    a.db(0xFF, 0x35); a.ref('wsrc')         # push dword [wsrc]
    a.db(0xFF, 0x74, 0x24, 0x10)
    a.db(0xFF, 0x15); a.dd(IAT_WRITEFILE)
    a.db(0xFF, 0x34, 0x24)
    a.db(0xFF, 0x15); a.dd(IAT_CLOSE)
    a.db(0x58)
    a.lab('wd_out')
    a.db(0xC3)

    # ================= data ================================================
    a.align(4)

    def astr(name, s):
        a.align(4)
        a.dd(0xFFFFFFFF)                    # refcount -1 (constant)
        a.dd(len(s))
        a.lab(name)                         # label points at the CHARS
        a.buf += s.encode('latin1') + b'\x00'

    astr('s_mouse', 'Mouse')
    astr('s_hotkeys', 'Hotkeys')
    a.align(4)
    a.lab('s_vcl30')
    a.buf += b'VCL30.dpl\x00'

    # layout entries reference their text labels; emit strings first
    texts = []
    for idx, (text, left, top, w, kind, ti) in enumerate(LAYOUT):
        nm = 'lt%d' % idx
        astr(nm, text)
        texts.append(nm)
    texts2 = []
    for idx, (text, left, top, w, kind, ti) in enumerate(LAYOUT2):
        nm = 'lt2_%d' % idx
        astr(nm, text)
        texts2.append(nm)

    # vk name strings (unique)
    uniq = {}
    for vk in range(256):
        nm = VK_NAMES.get(vk, '?')
        if nm not in uniq:
            key = 'vk_%d' % len(uniq)
            uniq[nm] = key
            astr(key, nm)

    a.align(4)
    a.lab('layout')
    for idx, (text, left, top, w, kind, ti) in enumerate(LAYOUT):
        a.ref(texts[idx])                   # +0 text (char ptr)
        a.dw(left); a.dw(top); a.dw(w)      # +4 left, +6 top, +8 width
        a.db(kind, ti)                      # +0xA kind, +0xB tabidx
    a.dd(0)                                 # terminator

    a.align(4)
    a.lab('layout2')
    for idx, (text, left, top, w, kind, ti) in enumerate(LAYOUT2):
        a.ref(texts2[idx])
        a.dw(left); a.dw(top); a.dw(w)
        a.db(kind, ti)
    a.dd(0)

    a.align(4)
    a.lab('vknames')
    for vk in range(256):
        a.fix.append((len(a.buf), uniq[VK_NAMES.get(vk, '?')]))
        a.dd(0)

    a.align(4)
    a.lab('defaults')
    a.buf += DEFAULT_TAB

    # ---- zero-initialized vars ----
    a.align(4)
    a.lab('g_sheet'); a.dd(0)
    a.lab('g_sheet2'); a.dd(0)
    a.lab('g_cursheet'); a.dd(0)
    a.lab('g_resetcb'); a.dd(0)
    a.lab('gotbuf'); a.dd(0)
    a.lab('wsrc'); a.dd(0)
    a.lab('strvar'); a.dd(0)
    a.lab('hgt'); a.dd(0)
    a.lab('g_vallab'); a.buf += bytes(4 * 19)
    a.lab('tabbuf'); a.buf += bytes(20)
    a.lab('pathbuf'); a.buf += bytes(260)

    return a.fin(SEC_SIZE)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE); print("restored AoWSetup.exe"); return 0
        print("no backup"); return 1

    d = bytearray(open(EXE, "rb").read())
    blob = build_section()

    # PE surgery: append section
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sec0 = e + 24 + optsz
    already = any(d[sec0 + 40*i: sec0 + 40*i + 8].rstrip(b"\x00") == b".xmou"
                  for i in range(nsec))

    # hook site re-points (5-byte jmps)
    def jmp5(src, dst):
        return b"\xE9" + struct.pack("<i", dst - (src + 5))
    lab = {}
    # recover label VAs from a fresh assembly (labels dict)
    a2 = Asm(SEC_VA)
    # rebuild to get labels (build_section returns bytes; rebuild for labels)
    # simpler: find offsets by rebuilding with the same function
    # (build_section is deterministic)
    # -- extract label positions via a re-run:
    import types
    # cheap: rerun and capture labels by monkeypatching fin
    holder = {}
    orig_fin = Asm.fin
    def capture_fin(self, limit):
        holder['labels'] = dict(self.labels)
        return orig_fin(self, limit)
    Asm.fin = capture_fin
    blob = build_section()
    Asm.fin = orig_fin
    L = holder['labels']
    MY_SHOW = SEC_VA + L['my_show']
    MY_HIDEOK = SEC_VA + L['my_hideok']
    MY_HIDECAN = SEC_VA + L['my_hidecan']

    sites = [
        (SBTN_VA, jmp5(SBTN_VA, DT_SHOW), jmp5(SBTN_VA, MY_SHOW), "SettingsBtn -> my_show"),
        (OK_VA, jmp5(OK_VA, DT_HIDEOK), jmp5(OK_VA, MY_HIDEOK), "SettingsOk -> my_hideok"),
        (CAN_VA, jmp5(CAN_VA, DT_HIDECAN), jmp5(CAN_VA, MY_HIDECAN), "SettingsCancel -> my_hidecan"),
    ]

    ok = True; applied = 0
    for va, old, new, desc in sites:
        off = va - CODE_D
        cur = bytes(d[off:off+5])
        cur_tgt = va + 5 + struct.unpack_from("<i", cur, 1)[0] if cur[0] == 0xE9 else 0
        if cur == new:
            applied += 1
        elif cur == old or SEC_VA <= cur_tgt < SEC_VA + SEC_SIZE:
            pass                            # devtab jmp, or an older build of ours
        else:
            print("MISMATCH %s @%#x: %s (expected devtab jmp %s)" % (desc, va, cur.hex(' '), old.hex(' ')))
            ok = False
    content_current = False
    if already:
        for i in range(nsec):
            if d[sec0 + 40*i: sec0 + 40*i + 8].rstrip(b"\x00") == b".xmou":
                praw = struct.unpack_from("<I", d, sec0 + 40*i + 20)[0]
                content_current = bytes(d[praw:praw + len(blob)]) == blob
    if already and applied == len(sites) and content_current:
        print("ALL ALREADY PATCHED"); return 0
    if not ok:
        print("Aborting (apply the devtab patch first)."); return 1

    print("section .xmou @%#x: %d bytes (code+data), %d layout controls"
          % (SEC_VA, len(blob), len(LAYOUT)))
    print("my_show=%#x my_hideok=%#x my_hidecan=%#x" % (MY_SHOW, MY_HIDEOK, MY_HIDECAN))
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK); print("Backup ->", os.path.basename(BAK))

    if not already:
        # append the section
        filealign = struct.unpack_from("<I", d, e + 24 + 36)[0]
        sizeofimage_off = e + 24 + 56
        rawoff = len(d)
        pad = (-rawoff) % max(filealign, 0x200)
        d += bytes(pad)
        rawoff = len(d)
        d += blob + bytes(SEC_SIZE - len(blob))
        hdr = SEC_NAME + struct.pack("<IIIIIIHHI",
                                     SEC_SIZE, SEC_VA - 0x400000, SEC_SIZE, rawoff,
                                     0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<40s", d, sec0 + 40 * nsec, hdr)
        struct.pack_into("<H", d, e + 6, nsec + 1)
        newimg = (SEC_VA - 0x400000 + SEC_SIZE)
        struct.pack_into("<I", d, sizeofimage_off, newimg)
        print("appended .xmou raw @%#x, SizeOfImage -> %#x" % (rawoff, newimg))
    else:
        # refresh section content in place
        for i in range(struct.unpack_from('<H', d, e + 6)[0]):
            name = d[sec0 + 40*i: sec0 + 40*i + 8].rstrip(b"\x00")
            if name == b".xmou":
                praw = struct.unpack_from("<I", d, sec0 + 40*i + 20)[0]
                d[praw:praw + SEC_SIZE] = blob + bytes(SEC_SIZE - len(blob))
                print("refreshed .xmou content in place")

    for va, old, new, desc in sites:
        off = va - CODE_D
        d[off:off+5] = new
        print("Re-pointed:", desc)
    open(EXE, "wb").write(d)
    print("AoWSetup.exe patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
