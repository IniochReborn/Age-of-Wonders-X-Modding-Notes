#!/usr/bin/env python3
r"""Borderless-stretch mouse scaling (Dcpack.dpl) - companion to
build_borderless_fullscreen.py v2.

In stretched borderless mode the back surface (game space) is FROZEN at the
windowed size while the window client covers the screen; the per-frame present
(TCustomDisplay.ExecuteBltSurfaceEvent, BackSurfaceControlMode=bmBltSurface ->
DC vcall+0x84 BltSurface) is a full StretchDIBits(surface -> DC rect), so
video scales automatically. Mouse input does NOT: WM_MOUSE* lParam and
GetCursorPos-based polling deliver window-CLIENT pixels while the game wants
SURFACE pixels. This patch scales both at their choke points:

  S1 TCustomDisplay.WndProc @0x551051DC (entry detour, 5 bytes):
     for WM_MOUSEFIRST(0x200)..WM_MBUTTONDBLCLK(0x209) rewrite
     lParam.x *= BackSurfW/ClientW, lParam.y *= BackSurfH/ClientH.
     Fields on the control (self=eax): +0x18C/+0x190 back surface W/H,
     +0x38/+0x3C TControl FWidth/FHeight (Align=alClient => client size).
     (WM_MOUSEWHEEL 0x20A excluded: SCREEN coords + handled by wheel hook.)
  S2 TDisplayCtrl.GetMousePos @0x55103FC0 (entry wrap, 7 bytes):
     run original (returns client coords or (-1,-1)), then scale the two
     out-params. Control object = [DC self + 0x2C].

Both are EXACT IDENTITY when surface == client (x*W/W = x), i.e. whenever
borderless-stretch is off - so normal windowed/fullscreen play, the editor,
and LAN are untouched. Division guarded against 0 (minimized).

Caves at 0x55108400 (CODE tail zeros, ~24KB free from 0x551083FB). Fully PIC:
field offsets + rel32 branches only, no absolute VAs (Dcpack could rebase).
No reloc entries in patched ranges (asserted). VA = file + 0x55100C00.
Backup: Dcpack.dpl.bak_bfsmouse. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "Dcpack.dpl")
BAK = DLL + ".bak_bfsmouse"

BASE    = 0x55100000
VA2FILE = 0x55100C00
CAVE    = 0x55108400
CAVE_END = 0x55108500

S1_VA, S1_OLD, S1_RESUME = 0x551051DC, bytes.fromhex("558BEC5153"), 0x551051E1
S2_VA, S2_OLD, S2_RESUME = 0x55103FC0, bytes.fromhex("53565755" "83C4D8"), 0x55103FC7

SURF_W, SURF_H = 0x18C, 0x190            # control: back surface size
CLI_W, CLI_H   = 0x38, 0x3C              # control: TControl FWidth/FHeight
DC_CTL         = 0x2C                    # TDisplayCtrl: -> control


class Asm:
    def __init__(self, org):
        self.org, self.buf, self.labels = org, bytearray(), {}
        self.f32, self.f8 = [], []

    def here(self): return self.org + len(self.buf)
    def lab(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf.extend(b)
    def dd(self, v): self.buf.extend((v & 0xFFFFFFFF).to_bytes(4, "little"))

    def rel32(self, op, t):
        self.buf.extend(op); self.f32.append((len(self.buf), t)); self.dd(0)

    def jmp(self, t): self.rel32(b"\xE9", t)
    def call(self, t): self.rel32(b"\xE8", t)

    def j8(self, op, lbl):
        self.db(op); self.f8.append((len(self.buf), lbl)); self.db(0)

    def resolve(self):
        for pos, t in self.f32:
            t = self.labels.get(t, t) if isinstance(t, str) else t
            struct.pack_into("<i", self.buf, pos, t - (self.org + pos + 4))
        for pos, lbl in self.f8:
            d = self.labels[lbl] - (self.org + pos + 1)
            assert -128 <= d < 128, f"j8 range to {lbl}"
            struct.pack_into("<b", self.buf, pos, d)
        return bytes(self.buf)


def build_caves():
    a = Asm(CAVE)

    # ---- S1: WndProc mouse lParam scaling (eax=self ctl, edx=@TMessage) ----
    a.lab("WNDPROC")
    a.db(0x55, 0x8B, 0xEC, 0x51, 0x53)           # replay: push ebp;mov ebp,esp;
    #                                              push ecx; push ebx
    a.db(0x8B, 0xD8)                             # mov ebx,eax   (self)
    a.db(0x56, 0x57)                             # push esi/edi (ours)
    a.db(0x8B, 0xF2)                             # mov esi,edx   (@msg)
    a.db(0x8B, 0x0E)                             # mov ecx,[esi] (Msg)
    a.db(0x81, 0xE9); a.dd(0x200)                # sub ecx,0x200
    a.db(0x83, 0xF9, 0x09)                       # cmp ecx,9
    a.j8(0x77, "w_done")                         # ja  -> not a mouse msg
    a.db(0x8B, 0x4B, CLI_W)                      # mov ecx,[ebx+0x38] cw
    a.db(0x85, 0xC9)                             # test ecx,ecx
    a.j8(0x7E, "w_done")                         # jle
    a.db(0x3B, 0x8B); a.dd(SURF_W)               # cmp ecx,[ebx+0x18C]
    a.j8(0x75, "w_go")
    a.db(0x8B, 0x4B, CLI_H)                      # mov ecx,[ebx+0x3C]
    a.db(0x3B, 0x8B); a.dd(SURF_H)               # cmp ecx,[ebx+0x190]
    a.j8(0x74, "w_done")                         # identity -> skip
    a.db(0x8B, 0x4B, CLI_W)                      # mov ecx,[ebx+0x38]
    a.lab("w_go")
    a.db(0x0F, 0xBF, 0x46, 0x08)                 # movsx eax,word [esi+8]  x
    a.db(0xF7, 0xAB); a.dd(SURF_W)               # imul dword [ebx+0x18C]
    a.db(0xF7, 0xF9)                             # idiv ecx
    a.db(0x8B, 0xF8)                             # mov edi,eax  (x')
    a.db(0x8B, 0x4B, CLI_H)                      # mov ecx,[ebx+0x3C] ch
    a.db(0x85, 0xC9)                             # test ecx,ecx
    a.j8(0x7E, "w_done")
    a.db(0x0F, 0xBF, 0x46, 0x0A)                 # movsx eax,word [esi+0xA] y
    a.db(0xF7, 0xAB); a.dd(SURF_H)               # imul dword [ebx+0x190]
    a.db(0xF7, 0xF9)                             # idiv ecx
    a.db(0xC1, 0xE0, 0x10)                       # shl eax,16
    a.db(0x81, 0xE7); a.dd(0xFFFF)               # and edi,0xFFFF
    a.db(0x0B, 0xC7)                             # or eax,edi
    a.db(0x89, 0x46, 0x08)                       # mov [esi+8],eax (lParam)
    a.lab("w_done")
    a.db(0x8B, 0xD6)                             # mov edx,esi (restore @msg)
    a.db(0x8B, 0xC3)                             # mov eax,ebx (restore self)
    a.db(0x5F, 0x5E)                             # pop edi/esi
    a.jmp(S1_RESUME)

    # ---- S2: GetMousePos wrap (eax=DC, edx=pX, ecx=pY) ----
    a.lab("MOUSEPOS")
    a.db(0x53, 0x56, 0x57)                       # push ebx/esi/edi
    a.db(0x8B, 0xF2)                             # mov esi,edx (pX)
    a.db(0x8B, 0xF9)                             # mov edi,ecx (pY)
    a.db(0x8B, 0x58, DC_CTL)                     # mov ebx,[eax+0x2C] (control)
    a.call("INNER")                              # original GetMousePos
    a.db(0x8B, 0x06)                             # mov eax,[esi]
    a.db(0x83, 0xF8, 0xFF)                       # cmp eax,-1
    a.j8(0x74, "m_done")
    a.db(0x8B, 0x4B, CLI_W)                      # mov ecx,[ebx+0x38]
    a.db(0x85, 0xC9)
    a.j8(0x7E, "m_done")
    a.db(0xF7, 0xAB); a.dd(SURF_W)               # imul dword [ebx+0x18C]
    a.db(0xF7, 0xF9)                             # idiv ecx
    a.db(0x89, 0x06)                             # mov [esi],eax
    a.db(0x8B, 0x4B, CLI_H)                      # mov ecx,[ebx+0x3C]
    a.db(0x85, 0xC9)
    a.j8(0x7E, "m_done")
    a.db(0x8B, 0x07)                             # mov eax,[edi]
    a.db(0xF7, 0xAB); a.dd(SURF_H)               # imul dword [ebx+0x190]
    a.db(0xF7, 0xF9)                             # idiv ecx
    a.db(0x89, 0x07)                             # mov [edi],eax
    a.lab("m_done")
    a.db(0x5F, 0x5E, 0x5B)                       # pop edi/esi/ebx
    a.db(0xC3)                                   # ret
    a.lab("INNER")
    a.db(*S2_OLD)                                # replay prologue
    a.jmp(S2_RESUME)

    return a.resolve(), a.labels


def check_relocs(data, spans):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    sec0 = pe + 24 + optsz
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    rel_raw = rel_size = None
    for i in range(nsec):
        o = sec0 + i * 40
        if data[o:o+8].rstrip(b"\0") == b".reloc":
            rel_size, _, _, rel_raw = struct.unpack_from("<IIII", data, o + 8)
    assert rel_raw, "no .reloc"
    hits, p = [], rel_raw
    while p < rel_raw + rel_size:
        page, bsz = struct.unpack_from("<II", data, p)
        if bsz == 0:
            break
        for q in range(p + 8, p + bsz, 2):
            e = struct.unpack_from("<H", data, q)[0]
            if e >> 12 != 3:
                continue
            tva = BASE + page + (e & 0xFFF)
            for sva, ln in spans:
                if sva - 3 <= tva < sva + ln:
                    hits.append(hex(tva))
        p += bsz
    assert not hits, f"reloc overlap: {hits}"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--revert":
        if not os.path.exists(BAK):
            sys.exit("no backup")
        shutil.copyfile(BAK, DLL)
        print(f"reverted {DLL}")
        return

    data = bytearray(open(DLL, "rb").read())
    for va, old, what in ((S1_VA, S1_OLD, "WndProc"), (S2_VA, S2_OLD, "GetMousePos")):
        got = data[va - VA2FILE: va - VA2FILE + len(old)]
        assert got == old, f"{what} @ {va:#x}: expected {old.hex()} got {got.hex()}"
    cave_bytes = data[CAVE - VA2FILE: CAVE_END - VA2FILE]
    assert not any(cave_bytes), "cave not empty"
    check_relocs(data, [(S1_VA, len(S1_OLD)), (S2_VA, len(S2_OLD)),
                        (CAVE, CAVE_END - CAVE)])

    code, labels = build_caves()
    assert len(code) <= CAVE_END - CAVE, f"cave overflow {len(code):#x}"
    print(f"caves @ {CAVE:08X} len={len(code):#x}: " +
          " ".join(f"{n}={v:08X}" for n, v in labels.items() if n.isupper()))

    def site(va, target, ln):
        return b"\xE9" + struct.pack("<i", target - (va + 5)) + b"\x90" * (ln - 5)
    p1 = site(S1_VA, labels["WNDPROC"], 5)
    p2 = site(S2_VA, labels["MOUSEPOS"], 7)
    print(f"  S1 @ {S1_VA:08X}: {S1_OLD.hex()} -> {p1.hex()}")
    print(f"  S2 @ {S2_VA:08X}: {S2_OLD.hex()} -> {p2.hex()}")

    if mode != "--apply":
        print("dry run OK - rerun with --apply")
        return

    shutil.copyfile(DLL, BAK)
    print(f"backup -> {BAK}")
    data[CAVE - VA2FILE: CAVE - VA2FILE + len(code)] = code
    data[S1_VA - VA2FILE: S1_VA - VA2FILE + len(p1)] = p1
    data[S2_VA - VA2FILE: S2_VA - VA2FILE + len(p2)] = p2
    open(DLL, "wb").write(data)
    print("APPLIED (mouse scaling active only when surface != client)")


main()
