#!/usr/bin/env python3
r"""Borderless fullscreen: new "Fullscreen (Optimized)" entry in Video settings.

WHY: Windows 8+ removed 16bpp display modes system-wide, so AoW's exclusive-
fullscreen DirectDraw mode enumeration (GFXE.ListDisplayModes, 16bpp) always
comes back EMPTY on Win10/11 -> the resolution list shows only "Desktop
Window". Windowed mode works because DirectDraw color-converts the 16bpp
surface while blitting to the 32bpp desktop.

DESIGN (all AoWx.exe; VA = file + 0x400C00; exe never rebases):
The main window is a plain VCL TMainForm with a TDisplay control, Align =
alClient + doAutoResizeBackSurface: any window resize auto-resizes the back
surfaces and fires TMainForm.DisplayResizeBackSurface -> TGeneral.ResetLayout
(min 640x480, no upper cap). So "borderless fullscreen" = stay on the WORKING
windowed DC (TWindows16DC) and restyle the form: WS_POPUP + screen-sized via
SetWindowLongA/SetWindowPos.

v2 (user request): the game must KEEP its windowed-size layout (same map
viewport / event window) and be STRETCHED to fill the screen. While borderless
we clear doAutoResizeBackSurface (bit0 of [display+0x185]) before resizing, so
the back surface stays at the windowed size; the per-frame present
(ExecuteBltSurfaceEvent, BackSurfaceControlMode=bmBltSurface -> DC BltSurface
vcall+0x84) is a full StretchDIBits(surface -> DC client rect), which scales
the picture automatically. Mouse input is scaled surface/client by the
companion patch build_bfs_mouse_dcpack.py (identity when not stretched).

  - listbox populator 0x40B08C: after "Desktop Window" (object -1) we append
    "FullScreen (Borderless)" with object -2  [site A @0x40B0E4]
  - TVideoDialog.ApplyBtnClick reads the selected object: -2 -> save the form's
    VCL bounds (l,t,w,h @ +0x30..0x3C), set FLAG:=2, restyle, then take the
    normal windowed path (mode 0 + apply 0x40B298(0,0)). -1 while borderless ->
    clear FLAG + restore style/bounds. Real mode index while borderless ->
    clear+restore first.                                  [site B @0x40B68C]
  - selection finder 0x40B5CC: windowed+FLAG -> select object -2 item
                                                          [site C @0x40B5F3]
  - persistence: registry "Video\Display Mode" = 2 (Get/SetDisplayMode do NOT
    clamp - verified in AoWEPACK 0x5570476C). Boot: FormCreate's GetDisplayMode
    call is wrapped: 2 -> FLAG:=2, return 0 (so the mode-2 intro machinery in
    the display controller never sees it)                 [site D @0x4534DA]
    FormShow entry: FLAG -> save VCL bounds (just restored from registry
    MainWindowPosition), restyle                          [site E @0x453A80]
    FormDestroy entry: FLAG -> write saved bounds back into the form's VCL
    l/t/w/h fields BEFORE the layout save runs, so the registry keeps the
    pre-borderless windowed rect (no user32 calls at exit) [site F @0x453910]
    FormDestroy windowed SetDisplayMode(0) call -> SetDisplayMode(FLAG) (FLAG
    is 0 or 2)                                            [site G @0x4539DD]

NEW SECTION ".xbfs" (RVA 0x20D000 = VA 0x60D000, appended raw at EOF,
chars 0xE0000060 CODE|INITDATA|EXEC|READ|WRITE) holds:
  - relocated import descriptor table (old 22 descriptors copied + user32
    descriptor for SetWindowLongA/SetWindowPos/GetSystemMetrics + null);
    DataDirectory[1] repointed. Loader fills our IAT slots at fixed VAs -
    no runtime GetProcAddress, no rebase concerns.
  - FLAG byte (0 or 2), SAVED_RECT (l,t,w,h), the Delphi string constant
    (refcount -1 header), and the seven cave routines.

Known cosmetic edges (accepted): if the window was maximized, borderless keeps
Windows' internal maximized flag (looks identical); un-restyling then shows
normal borders at the saved rect. Exclusive fullscreen (if modes exist, e.g.
Win7) still works; picking it clears borderless first.

Dry-run by default; --apply writes (backup AoWx.exe.bak_borderless), --revert
restores the backup. LAN-safe: pure client-side presentation.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWx.exe")
BAK = EXE + ".bak_borderless"

BASE      = 0x400000
FILE2VA   = 0x400C00                     # CODE section: VA = file + this
SEC_RVA   = 0x20D000
SEC_VA    = BASE + SEC_RVA
SEC_NAME  = b".xbfs\x00\x00\x00"
SEC_CHARS = 0xE0000060
SEC_VSIZE = 0x2000

# fixed exe addresses (verified by disassembly 2026-08-11)
MAINFORM_PP = 0x45A168                   # -> -> TMainForm instance
GH   = 0x40164C                          # thunk VCL30 TWinControl.GetHandle
IOBJ = 0x4014F4                          # thunk VCL30 TStrings.IndexOfObject
GDM  = 0x401F24                          # thunk AoWEPACK GetDisplayMode
SDM  = 0x401F2C                          # thunk AoWEPACK SetDisplayMode
GCW  = 0x4015F4                          # thunk VCL30 TControl.GetClientWidth
GCH  = 0x4015FC                          # thunk VCL30 TControl.GetClientHeight
SBW  = 0x4030BC                          # thunk DCPACK SetBackSurfaceWidth
SBH  = 0x4030C4                          # thunk DCPACK SetBackSurfaceHeight
GRECT = 0x401EEC                         # thunk AoWEPACK GetRectangle
SRECT = 0x401EF4                         # thunk AoWEPACK SetRectangle
REGP  = 0x45DF74                         # -> -> engine; +0x5C = TAoWRegistry
RECT_IDX = 100                           # our slot under General\rectangles

SITES = {  # va: (expected bytes, kind)
    'A': (0x40B0E4, bytes.fromhex("8B868C000000"), 'jmp+nop'),   # populator
    'B': (0x40B68C, bytes.fromhex("83FEFF7444"),   'jmp'),       # apply
    'C': (0x40B5CC, bytes.fromhex("535657558BF0"), 'jmp+nop'),   # finder entry
    'D': (0x4534DA, bytes.fromhex("E845EAFAFF"),   'call'),      # boot read
    'E': (0x452E50, bytes.fromhex("558BEC83C4A0"), 'jmp+nop'),   # UpdateFrame
    'F': (0x453910, bytes.fromhex("5356578BD8"),   'jmp'),       # FormDestroy
    'G': (0x4539DD, bytes.fromhex("E84AE5FAFF"),   'call'),      # save mode
    'H': (0x40B4AF, bytes.fromhex("8A8390000000"), 'jmp+nop'),   # boot no-DC
}
RESUME = {'A': 0x40B0EA, 'B': None, 'C': None, 'D': None,
          'E': 0x452E56, 'F': 0x453915, 'G': None, 'H': 0x40B4B5}
MODEMGR_EXIT = 0x40B5A2                  # mode manager: clear apply-flag & ret
APPLY_FS   = 0x40B691                    # ApplyBtnClick: fullscreen-index path
APPLY_WIN  = 0x40B6D5                    # ApplyBtnClick: windowed path
FINDER_FS  = 0x40B5F5                    # finder: fullscreen-active body
FINDER_OUT = 0x40B654                    # finder common exit (pops + ret)


def parse_pe(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe+4] == b"PE\0\0"
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    sec0 = pe + 24 + optsz
    secs = []
    for i in range(nsec):
        o = sec0 + i * 40
        name = data[o:o+8].rstrip(b"\0")
        vsz, rva, rsz, raw = struct.unpack_from("<IIII", data, o + 8)
        secs.append((name, rva, vsz, raw, rsz, o))
    return pe, nsec, sec0, secs


def rva2off(secs, rva):
    for name, srva, vsz, raw, rsz, _ in secs:
        if srva <= rva < srva + max(vsz, rsz):
            return raw + (rva - srva)
    raise ValueError(f"rva {rva:#x} unmapped")


def check_relocs(data, secs):
    """assert no reloc entry targets any patched byte range"""
    spans = [(va, len(old)) for va, old, _ in SITES.values()]
    rel = next(s for s in secs if s[0] == b".reloc")
    off, size = rel[3], rel[2]
    end = off + size
    hits = []
    p = off
    while p < end:
        page, bsz = struct.unpack_from("<II", data, p)
        if bsz == 0:
            break
        for q in range(p + 8, p + bsz, 2):
            e = struct.unpack_from("<H", data, q)[0]
            if e >> 12 != 3:
                continue
            tva = BASE + page + (e & 0xFFF)
            for sva, ln in spans:
                if sva <= tva < sva + ln or sva <= tva + 3 < sva + ln:
                    hits.append((tva, sva))
        p += bsz
    assert not hits, f"reloc entries overlap patch sites: {hits}"


class Asm:
    def __init__(self, org):
        self.org = org
        self.buf = bytearray()
        self.labels = {}
        self.fix32 = []   # (bufpos, target-or-label, kind) kind: rel|abs
        self.fix8 = []    # (bufpos, label)

    def here(self):
        return self.org + len(self.buf)

    def lab(self, n):
        self.labels[n] = self.here()

    def db(self, *b):
        self.buf.extend(b)

    def dd(self, v):
        self.buf.extend((v & 0xFFFFFFFF).to_bytes(4, "little"))

    def rel32(self, op, target):
        self.buf.extend(op)
        self.fix32.append((len(self.buf), target, "rel"))
        self.dd(0)

    def call(self, t): self.rel32(b"\xE8", t)
    def jmp(self, t):  self.rel32(b"\xE9", t)

    def j8(self, op, label):
        self.db(op)
        self.fix8.append((len(self.buf), label))
        self.db(0)

    def callmem(self, slot_va):   # call [slot]
        self.db(0xFF, 0x15); self.dd(slot_va)

    def pushmem(self, va):        # push dword [va]
        self.db(0xFF, 0x35); self.dd(va)

    def resolve(self):
        for pos, tgt, kind in self.fix32:
            t = self.labels.get(tgt, tgt) if isinstance(tgt, str) else tgt
            struct.pack_into("<i", self.buf, pos, t - (self.org + pos + 4))
        for pos, labl in self.fix8:
            d = self.labels[labl] - (self.org + pos + 1)
            assert -128 <= d < 128, f"j8 out of range to {labl}"
            struct.pack_into("<b", self.buf, pos, d)
        return bytes(self.buf)


def build_section(data, secs, pe):
    # ---- gather old import descriptors ----
    imp_rva = struct.unpack_from("<I", data, pe + 24 + 96 + 8)[0]
    off = rva2off(secs, imp_rva)
    descs = []
    while True:
        d = data[off:off+20]
        if d == b"\0" * 20:
            break
        descs.append(d)
        off += 20
    # Borland: one descriptor per import GROUP (unit), OFT=0 (IAT-only form)
    assert 15 < len(descs) < 400, f"unexpected import descriptor count {len(descs)}"

    blob = bytearray(SEC_VSIZE)
    ndesc = len(descs) + 2                       # + user32 + null
    desc_sz = ndesc * 20
    INT_OFF  = (desc_sz + 15) & ~15
    IAT_OFF  = INT_OFF + 0x10
    NAME_OFF = IAT_OFF + 0x10
    HN_OFF   = NAME_OFF + 0x10

    names = [b"SetWindowLongA", b"SetWindowPos", b"GetSystemMetrics"]
    hn_rvas = []
    p = HN_OFF
    for n in names:
        hn_rvas.append(SEC_RVA + p)
        blob[p:p+2] = b"\0\0"
        blob[p+2:p+2+len(n)+1] = n + b"\0"
        p += 2 + len(n) + 1
        p += p & 1
    DATA_OFF = (p + 15) & ~15
    FLAG_OFF = DATA_OFF
    RECT_OFF = DATA_OFF + 4
    STRH_OFF = DATA_OFF + 0x18
    s = b"Fullscreen (Optimized)"
    struct.pack_into("<ii", blob, STRH_OFF, -1, len(s))
    STR_OFF = STRH_OFF + 8
    blob[STR_OFF:STR_OFF+len(s)+1] = s + b"\0"
    TMP_OFF = (STR_OFF + len(s) + 1 + 3) & ~3     # 16-byte TRect scratch
    CODE_OFF = (TMP_OFF + 16 + 15) & ~15

    FLAG = SEC_VA + FLAG_OFF
    PENDING = FLAG + 1                           # one-shot boot-apply guard
    RECT = SEC_VA + RECT_OFF
    STR  = SEC_VA + STR_OFF
    TMP  = SEC_VA + TMP_OFF                      # TRect scratch for registry
    SLOT_SWL = SEC_VA + IAT_OFF
    SLOT_SWP = SEC_VA + IAT_OFF + 4
    SLOT_GSM = SEC_VA + IAT_OFF + 8

    # descriptors: old ones + user32
    for i, d in enumerate(descs):
        blob[i*20:(i+1)*20] = d
    struct.pack_into("<IIIII", blob, len(descs)*20,
                     SEC_RVA + INT_OFF, 0, 0, SEC_RVA + NAME_OFF,
                     SEC_RVA + IAT_OFF)
    blob[NAME_OFF:NAME_OFF+11] = b"user32.dll\0"
    for i, rva in enumerate(hn_rvas):
        struct.pack_into("<I", blob, INT_OFF + i*4, rva)
        struct.pack_into("<I", blob, IAT_OFF + i*4, rva)

    # ---- code ----
    a = Asm(SEC_VA + CODE_OFF)

    def load_form_eax():
        a.db(0xA1); a.dd(MAINFORM_PP)            # mov eax,[pp]
        a.db(0x8B, 0x00)                         # mov eax,[eax]

    def load_display_eax():
        load_form_eax()
        a.db(0x8B, 0x80); a.dd(0x1DC)            # mov eax,[eax+0x1DC]

    a.lab("RESTYLE")
    a.db(0x53, 0x56, 0x57)                       # push ebx/esi/edi
    # freeze back surface: clear doAutoResizeBackSurface (bit0 of +0x185)
    # BEFORE the resize below, so the game keeps its windowed-size layout and
    # the per-frame BltSurface StretchDIBits scales it to the new client.
    load_display_eax()
    a.db(0x80, 0xA0); a.dd(0x185); a.db(0xFE)    # and byte [eax+0x185],0xFE
    load_form_eax()
    a.call(GH)                                   # eax = form hwnd
    a.db(0x8B, 0xD8)                             # mov ebx,eax
    a.db(0x6A, 0x00); a.callmem(SLOT_GSM)        # GetSystemMetrics(0)
    a.db(0x8B, 0xF0)                             # mov esi,eax
    a.db(0x6A, 0x01); a.callmem(SLOT_GSM)        # GetSystemMetrics(1)
    a.db(0x8B, 0xF8)                             # mov edi,eax
    a.db(0x68); a.dd(0x96000000)                 # WS_POPUP|VISIBLE|CLIPCH|CLIPSIB
    a.db(0x6A, 0xF0)                             # GWL_STYLE (-16)
    a.db(0x53)
    a.callmem(SLOT_SWL)
    a.db(0x6A, 0x24)                             # SWP_NOZORDER|SWP_FRAMECHANGED
    a.db(0x57, 0x56)                             # cy, cx
    a.db(0x6A, 0x00, 0x6A, 0x00, 0x6A, 0x00)     # y, x, insertafter
    a.db(0x53)
    a.callmem(SLOT_SWP)
    a.db(0x5F, 0x5E, 0x5B, 0xC3)

    a.lab("UNRESTYLE")
    a.db(0x53)
    # re-enable doAutoResizeBackSurface before restoring the windowed size
    load_display_eax()
    a.db(0x80, 0x88); a.dd(0x185); a.db(0x01)    # or byte [eax+0x185],1
    load_form_eax()
    a.call(GH)
    a.db(0x8B, 0xD8)
    a.db(0x68); a.dd(0x16CF0000)                 # WS_OVERLAPPEDWINDOW|VIS|CLIP*
    a.db(0x6A, 0xF0)
    a.db(0x53)
    a.callmem(SLOT_SWL)
    a.db(0x6A, 0x24)
    a.pushmem(RECT + 12); a.pushmem(RECT + 8)    # h, w
    a.pushmem(RECT + 4);  a.pushmem(RECT)        # t, l
    a.db(0x6A, 0x00)
    a.db(0x53)
    a.callmem(SLOT_SWP)
    a.db(0x5B, 0xC3)

    a.lab("SAVERECT")
    load_form_eax()
    for i, fo in enumerate((0x30, 0x34, 0x38, 0x3C)):
        a.db(0x8B, 0x50, fo)                     # mov edx,[eax+fo]
        a.db(0x89, 0x15); a.dd(RECT + i*4)       # mov [RECT+i*4],edx
    a.db(0xC3)

    def cmp_flag0():
        a.db(0x80, 0x3D); a.dd(FLAG); a.db(0x00)   # cmp byte [FLAG],0

    def set_flag(v):
        a.db(0xC6, 0x05); a.dd(FLAG); a.db(v)      # mov byte [FLAG],v

    a.lab("CAVE1")                               # populator (esi=ctrl, ebx free)
    a.db(0x8B, 0x46, 0x70)                       # mov eax,[esi+0x70]
    a.db(0x8B, 0x80); a.dd(0x114)                # mov eax,[eax+0x114] (TStrings)
    a.db(0xBA); a.dd(STR)                        # mov edx,STR
    a.db(0xB9); a.dd(0xFFFFFFFE)                 # mov ecx,-2
    a.db(0x8B, 0x18)                             # mov ebx,[eax]
    a.db(0xFF, 0x53, 0x38)                       # call [ebx+0x38]  AddObject
    a.db(0x8B, 0x86); a.dd(0x8C)                 # replay mov eax,[esi+0x8c]
    a.jmp(RESUME['A'])

    a.lab("CAVE2")                               # apply (esi=obj, ebx=dialog)
    a.db(0x83, 0xFE, 0xFF); a.j8(0x74, "c2_m1")  # cmp esi,-1; je
    a.db(0x83, 0xFE, 0xFE); a.j8(0x74, "c2_bf")  # cmp esi,-2; je
    cmp_flag0(); a.j8(0x74, "c2_fs")             # fullscreen picked
    set_flag(0)
    a.call("UNRESTYLE")
    a.lab("c2_fs"); a.jmp(APPLY_FS)
    a.lab("c2_m1")
    cmp_flag0(); a.j8(0x74, "c2_win")
    set_flag(0)
    a.call("UNRESTYLE")
    a.lab("c2_win"); a.jmp(APPLY_WIN)
    a.lab("c2_bf")
    cmp_flag0(); a.j8(0x75, "c2_win")            # already borderless
    a.call("SAVERECT")
    set_flag(2)
    a.call("RESTYLE")
    a.jmp(APPLY_WIN)

    a.lab("CAVE3")                               # finder entry (eax=ctrl)
    a.db(0x53, 0x56, 0x57, 0x55, 0x8B, 0xF0)     # replay prologue+mov esi,eax
    a.db(0xA1); a.dd(MAINFORM_PP)                # mov eax,[pp]
    a.db(0x8B, 0x00)                             # mov eax,[eax]     (form)
    a.db(0x8B, 0x88); a.dd(0x1DC)                # mov ecx,[eax+0x1dc] display
    a.db(0x8B, 0x80); a.dd(0x1E4)                # mov eax,[eax+0x1e4] DXDC ref
    a.db(0x3B, 0x81); a.dd(0x1A8)                # cmp eax,[ecx+0x1a8] active DC
    a.j8(0x74, "c3_fs")                          # equal -> fullscreen body
    cmp_flag0(); a.j8(0x75, "c3_bf")
    a.db(0x31, 0xC0)                             # xor eax,eax (Desktop Window)
    a.jmp(FINDER_OUT)
    a.lab("c3_bf")
    a.db(0x8B, 0x46, 0x70)
    a.db(0x8B, 0x80); a.dd(0x114)
    a.db(0xBA); a.dd(0xFFFFFFFE)                 # edx = -2
    a.call(IOBJ)                                 # IndexOfObject
    a.jmp(FINDER_OUT)
    a.lab("c3_fs")
    a.jmp(FINDER_FS)                             # eax = active DC, as original

    a.lab("CAVE4")                               # FormCreate GetDisplayMode wrap
    a.call(GDM)
    a.db(0x83, 0xF8, 0x02); a.j8(0x75, "c4_d")   # cmp eax,2; jne
    set_flag(2)
    a.db(0x31, 0xC0)
    a.lab("c4_d"); a.db(0xC3)

    a.lab("CAVE5")                               # DisplayUpdateFrame entry
    # BOOT APPLY, deferred to the FIRST FRAME (one-shot). OnShow was too
    # early: the game restores its windowed size as a MAXIMIZED window (only
    # MainWindowState is persisted; MainWindowPosition is never written), and
    # VCL applies the maximize AFTER OnShow - so ClientWidth still read the
    # DFM 640x480 there. By the first OnUpdateFrame the window is shown and
    # maximized and auto-resize has already sized the back surfaces to the
    # true windowed client - the exact same state as the (working) manual
    # toggle. Then: save bounds, pin the surfaces (defensive no-op if already
    # right), freeze auto-resize + restyle.
    a.db(0x55, 0x8B, 0xEC, 0x83, 0xC4, 0xA0)     # replay prologue
    cmp_flag0(); a.j8(0x75, "c5_chk")            # FLAG set -> check pending
    a.lab("c5_x"); a.jmp(RESUME['E'])            # near trampoline out
    a.lab("c5_chk")
    a.db(0x80, 0x3D); a.dd(PENDING); a.db(0x00)  # cmp byte [PENDING],0
    a.j8(0x75, "c5_x")                           # already applied
    a.db(0xC6, 0x05); a.dd(PENDING); a.db(0x01)  # mov byte [PENDING],1
    a.db(0x50, 0x51, 0x52)                       # push eax/ecx/edx (event args)
    a.call("SAVERECT")
    a.db(0x53, 0x57)                             # push ebx, push edi
    # the game never persists its windowed size, so the boot window is the
    # 640x480 default - restore OUR saved render size (rectangles\100),
    # written by CAVE6A on exit-while-borderless. Fallback: current client.
    a.db(0xA1); a.dd(REGP)                       # mov eax,[REGP]
    a.db(0x8B, 0x00)                             # mov eax,[eax]
    a.db(0x8B, 0x40, 0x5C)                       # mov eax,[eax+0x5C] registry
    a.db(0xBA); a.dd(RECT_IDX)                   # mov edx,RECT_IDX
    a.db(0xB9); a.dd(TMP)                        # mov ecx,TMP
    a.call(GRECT)                                # GetRectangle
    a.db(0xA1); a.dd(TMP + 8)                    # mov eax,[TMP.r]
    a.db(0x2B, 0x05); a.dd(TMP)                  # sub eax,[TMP.l]  -> w
    a.db(0x3D); a.dd(0x280)                      # cmp eax,640
    a.j8(0x7C, "c5_fb")                          # jl fallback
    a.db(0x8B, 0xD8)                             # mov ebx,eax      (w)
    a.db(0xA1); a.dd(TMP + 12)                   # mov eax,[TMP.b]
    a.db(0x2B, 0x05); a.dd(TMP + 4)              # sub eax,[TMP.t]  -> h
    a.db(0x3D); a.dd(0x1E0)                      # cmp eax,480
    a.j8(0x7C, "c5_fb")
    a.db(0x8B, 0xF8)                             # mov edi,eax      (h)
    a.j8(0xEB, "c5_set")                         # jmp set
    a.lab("c5_fb")
    load_form_eax()
    a.call(GCW)                                  # eax = form ClientWidth
    a.db(0x8B, 0xD8)                             # mov ebx,eax
    load_form_eax()
    a.call(GCH)                                  # eax = form ClientHeight
    a.db(0x8B, 0xF8)                             # mov edi,eax
    a.lab("c5_set")
    load_display_eax()
    a.db(0x8B, 0xD3)                             # mov edx,ebx
    a.call(SBW)                                  # SetBackSurfaceWidth
    load_display_eax()
    a.db(0x8B, 0xD7)                             # mov edx,edi
    a.call(SBH)                                  # SetBackSurfaceHeight
    a.db(0x5F, 0x5B)                             # pop edi, pop ebx
    a.call("RESTYLE")
    a.db(0x5A, 0x59, 0x58)                       # pop edx/ecx/eax
    a.lab("c5_d"); a.jmp(RESUME['E'])

    a.lab("CAVE6A")                              # FormDestroy entry (ebx=form)
    a.db(0x53, 0x56, 0x57, 0x8B, 0xD8)           # replay
    cmp_flag0(); a.j8(0x74, "c6_d")
    for i, fo in enumerate((0x30, 0x34, 0x38, 0x3C)):
        a.db(0x8B, 0x15); a.dd(RECT + i*4)       # mov edx,[RECT+i*4]
        a.db(0x89, 0x53, fo)                     # mov [ebx+fo],edx
    # persist the render size: rectangles\100 := (0,0,surfW,surfH)
    a.db(0x8B, 0x83); a.dd(0x1DC)                # mov eax,[ebx+0x1DC] display
    a.db(0x8B, 0x90); a.dd(0x18C)                # mov edx,[eax+0x18C]
    a.db(0x89, 0x15); a.dd(TMP + 8)              # mov [TMP.r],edx
    a.db(0x8B, 0x90); a.dd(0x190)                # mov edx,[eax+0x190]
    a.db(0x89, 0x15); a.dd(TMP + 12)             # mov [TMP.b],edx
    a.db(0x31, 0xD2)                             # xor edx,edx
    a.db(0x89, 0x15); a.dd(TMP)                  # mov [TMP.l],0
    a.db(0x89, 0x15); a.dd(TMP + 4)              # mov [TMP.t],0
    a.db(0xA1); a.dd(REGP)                       # mov eax,[REGP]
    a.db(0x8B, 0x00)                             # mov eax,[eax]
    a.db(0x8B, 0x40, 0x5C)                       # mov eax,[eax+0x5C]
    a.db(0xBA); a.dd(RECT_IDX)                   # mov edx,RECT_IDX
    a.db(0xB9); a.dd(TMP)                        # mov ecx,TMP
    a.call(SRECT)                                # SetRectangle
    a.lab("c6_d"); a.jmp(RESUME['F'])

    a.lab("CAVE6B")                              # SetDisplayMode(FLAG) tail
    a.db(0x8A, 0x15); a.dd(FLAG)                 # mov dl,[FLAG]
    a.jmp(SDM)

    a.lab("CAVE7")                               # mode mgr, boot no-DC branch
    # The title scene forces mode 2 at boot; with no DC active yet the mode
    # manager would SetBackSurfaceWidth/Height(640,480) explicitly (bypassing
    # the frozen auto-resize bit) and overwrite the client-size surfaces set
    # at OnShow -> "zoomed" boot. While borderless, skip the whole branch.
    cmp_flag0(); a.j8(0x74, "c7_n")
    a.jmp(MODEMGR_EXIT)                          # just clear apply-flag
    a.lab("c7_n")
    a.db(0x8A, 0x83); a.dd(0x90)                 # replay mov al,[ebx+0x90]
    a.jmp(RESUME['H'])

    code = a.resolve()
    blob[CODE_OFF:CODE_OFF+len(code)] = code
    used = CODE_OFF + len(code)
    assert used <= SEC_VSIZE, f"section overflow: {used:#x}"

    info = dict(FLAG=FLAG, RECT=RECT, STR=STR, labels=a.labels,
                desc_sz=desc_sz, used=used)
    return bytes(blob), info


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--revert":
        if not os.path.exists(BAK):
            sys.exit("no backup to revert")
        shutil.copyfile(BAK, EXE)
        print(f"reverted {EXE} from {BAK}")
        return

    data = bytearray(open(EXE, "rb").read())
    pe, nsec, sec0, secs = parse_pe(data)

    # ---- validations ----
    assert struct.unpack_from("<I", data, pe + 24 + 32)[0] == 0x1000  # SectAlign
    assert struct.unpack_from("<I", data, pe + 24 + 36)[0] == 0x200   # FileAlign
    assert struct.unpack_from("<I", data, pe + 24 + 96 + 11*8)[0] == 0, \
        "bound import dir present"
    names = [s[0] for s in secs]
    assert b".xbfs" not in names, "patch already applied"
    last = secs[-1]
    next_rva = (last[1] + max(last[2], last[4]) + 0xFFF) & ~0xFFF
    assert next_rva == SEC_RVA, f"section RVA drift: {next_rva:#x}"
    hdr_off = sec0 + nsec * 40
    # slot holds a stripped (loader-ignored) ghost header: name+sizes zeroed,
    # stale VA/rawptr/chars left by Borland's debug-strip. Overwriting is safe
    # as long as the name field is empty and the count says 6.
    assert data[hdr_off:hdr_off+8] == b"\0"*8, "no room for section header"
    assert hdr_off + 40 <= struct.unpack_from("<I", data, pe + 24 + 60)[0], \
        "section table would exceed SizeOfHeaders"
    assert len(data) % 0x200 == 0, "file size not aligned"

    for k, (va, old, kind) in SITES.items():
        off = va - FILE2VA
        got = data[off:off+len(old)]
        assert got == old, f"site {k} @ {va:#x}: expected {old.hex()} got {got.hex()}"
    check_relocs(data, secs)

    blob, info = build_section(bytearray(data), secs, pe)
    L = info["labels"]
    print("section .xbfs @ VA %08X  (used 0x%X of 0x%X)"
          % (SEC_VA, info["used"], SEC_VSIZE))
    print("  FLAG=%08X RECT=%08X STR=%08X" % (info["FLAG"], info["RECT"], info["STR"]))
    for n in ("RESTYLE", "UNRESTYLE", "SAVERECT", "CAVE1", "CAVE2", "CAVE3",
              "CAVE4", "CAVE5", "CAVE6A", "CAVE6B"):
        print(f"  {n:9} @ {L[n]:08X}")

    # ---- site patch bytes ----
    def rel(op, src_va, dst_va, ln):
        return op + struct.pack("<i", dst_va - (src_va + len(op) + 4)) + \
               b"\x90" * (ln - len(op) - 4)
    patch = {
        'A': rel(b"\xE9", SITES['A'][0], L["CAVE1"], 6),
        'B': rel(b"\xE9", SITES['B'][0], L["CAVE2"], 5),
        'C': rel(b"\xE9", SITES['C'][0], L["CAVE3"], 6),
        'D': rel(b"\xE8", SITES['D'][0], L["CAVE4"], 5),
        'E': rel(b"\xE9", SITES['E'][0], L["CAVE5"], 6),
        'F': rel(b"\xE9", SITES['F'][0], L["CAVE6A"], 5),
        'G': rel(b"\xE8", SITES['G'][0], L["CAVE6B"], 5),
        'H': rel(b"\xE9", SITES['H'][0], L["CAVE7"], 6),
    }
    for k, b in patch.items():
        print(f"  site {k} @ {SITES[k][0]:08X}: {SITES[k][1].hex()} -> {b.hex()}")

    if mode != "--apply":
        print("dry run OK - rerun with --apply")
        return

    shutil.copyfile(EXE, BAK)
    print(f"backup -> {BAK}")

    raw_off = len(data)
    data += blob + b"\0" * ((-len(blob)) % 0x200)
    # section header
    struct.pack_into("<8sIIIIIIHHI", data, hdr_off, SEC_NAME, SEC_VSIZE, SEC_RVA,
                     (len(blob) + 0x1FF) & ~0x1FF, raw_off, 0, 0, 0, 0, SEC_CHARS)
    struct.pack_into("<H", data, pe + 6, nsec + 1)
    struct.pack_into("<I", data, pe + 24 + 56, SEC_RVA + SEC_VSIZE)  # SizeOfImage
    # import dir -> our descriptor copy
    struct.pack_into("<II", data, pe + 24 + 96 + 8, SEC_RVA, info["desc_sz"])
    for k, b in patch.items():
        off = SITES[k][0] - FILE2VA
        data[off:off+len(b)] = b

    open(EXE, "wb").write(data)
    print("APPLIED. Select 'Fullscreen (Optimized)' in Settings > Video.")


main()
