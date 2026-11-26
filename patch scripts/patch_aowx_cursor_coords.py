#!/usr/bin/env python3
"""
AoWx.exe: the taskbar status line shows the map hex under the cursor as "X,Y,Z" at its right
end ("-,-,-" when the cursor is not over a valid map hex) (2026-09-14).

Facts (410 build, verified):
  * Status text = TAOWEdit TBMessEdit inside TAOWWindow TBWorld of the TTBWindow data module
    (RCDATA TTBWINDOW 35452 B, res data entry @file 0x731a0; VMT 0x456cac, instance 0x144, field
    table @0x456cd4 (60 fields, class table @0x45729d: TAOWLabel = idx 4); global instance var
    0x45b2c8 (found by live scan).  The edit is awBoth LeftOffset 48 / RightOffset 275, font Age10;
    TimeLbl sits awRight RightOffset 225, BottomOffset 4, priority 60.
  * Map mouse: TMWindow.MapWindowMouseMove @0x450EF8 converts the cursor into the map's mouse
    object ([[0x45df7c]] = AoWHSMap, [map+0xC] = THSMapMouse) via its VMT+0x20, then
    @0x450F77 `mov dx,0x270f / mov eax,[ebx+0x44]` (SetCursor).  Hovered hex = HSEPack
    THSMapMouse.GetXhx / GetYhx (0x5560b6b0 / 0x5560b718, eax=self -> eax, -1 = none); level =
    [map+0x88].  Neither getter is imported; runtime addresses come from the exe's IAT slot
    0x45d9d8 (HSEngine.TMapContainer.GetField, link VA 0x55608d84) + link delta -> rebase-safe.
  * TMainForm.DisplayMouseMove @0x4536e8 (published, method table dword @file 0x51bb0) is the
    VCL-level mouse move for the whole display (register args + X,Y on the stack, `ret 8`);
    the aowInt window dispatch it performs is synchronous.

Patch (new RWX section .xcrd @VA 0x612000):
  1. TTBWINDOW DFM with TAOWLabel CoordLbl cloned from TimeLbl (font Age10, RightOffset 280 so it
     sits inside the message box's right end, BottomOffset 6) inserted after TimeLbl; resource
     entry repointed.  Field table +1 (CoordLbl @+0x144, TAOWLabel), instance 0x144 -> 0x148.
  2. Hook @0x450F77 -> cave: flag := 1, read hex X/Y (+ level), format "X,Y,Z" into a static
     AnsiString (refcount -1) and SetGText(CoordLbl) when the value changed; replay; back.
  3. DisplayMouseMove method-table entry -> wrapper: flag := 0, original, then if flag still 0
     (cursor was not over the map area) show "-,-,-".
Dry-run default; --apply; --revert (restores backup).  Backup: AoWx.exe.bak_cursorcoords
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK_SUFFIX = ".bak_cursorcoords"; BASE = 0x400000
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
SEC_NAME, SEC_VA, SEC_VSIZE = b".xcrd", 0x612000, 0xA000
RES_ENTRY_FO, RES_RVA, RES_SIZE = 0x731a0, 0x1cf870, 0x8a7c
VMT, VMT_FT_FO, VMT_SIZE_FO, FT_VA, FT_LEN = 0x456cac, 0x56080, 0x56090, 0x456cd4, 885
OLD_INST, NEW_INST, CLS_LABEL, NEW_FIELD = 0x144, 0x148, 4, 0x144
G_TBWINDOW, G_MAP_IAT, IAT_GETFIELD = 0x45b2c8, 0x45df7c, 0x45d9d8
LINK_GETFIELD, LINK_GETXHX, LINK_GETYHX = 0x55608d84, 0x5560b6b0, 0x5560b718
T_SETGTEXT = 0x403254
HOOK, HOOK_ORIG, HOOK_CONT = 0x450F77, bytes.fromhex("66ba0f27" "8b4344"), 0x450F7E
MT_DMM_FO, DISPLAYMOUSEMOVE = 0x51bb0, 0x4536e8
MAP_MOUSE, MAP_LEVEL = 0x0C, 0x88
# TBMessEdit spans LeftOffset 48 .. RightOffset 275, but the player-indicator frame PInd (75 px wide,
# RightOffset 275, higher priority) covers its right end - the visible text area ends 350 px from the
# right edge.  Border width 5 -> label right edge at 355.
LABEL_RIGHT, LABEL_BOTTOM = 355, 6

def sstr(s): return bytes([len(s)]) + s
def obj_span(d, o):
    def skip_val(p):
        t = d[p]; p += 1
        if t in (0, 8, 9, 13): return p
        if t == 1:
            while d[p] != 0: p = skip_val(p)
            return p + 1
        if t == 2: return p + 1
        if t == 3: return p + 2
        if t == 4: return p + 4
        if t == 5: return p + 10
        if t in (6, 7): return p + 1 + d[p]
        if t == 10: return p + 4 + struct.unpack_from("<I", d, p)[0]
        if t == 11:
            while d[p] != 0: p += 1 + d[p]
            return p + 1
        if t == 12: return p + 4 + struct.unpack_from("<I", d, p)[0]
        raise ValueError(f"vtype {t} @{p:#x}")
    p = o + 1 + d[o]; p += 1 + d[p]
    while d[p] != 0: p += 1 + d[p]; p = skip_val(p)
    p += 1
    while d[p] != 0: p = obj_span(d, p)
    return p + 1
def find_obj(d, name):
    key = sstr(name); i = 0
    while True:
        i = d.find(key, i); assert i >= 0, name
        for cl in range(3, 40):
            s = i - 1 - cl
            if s >= 0 and d[s] == cl and d[s+1:s+2] == b"T": return s, obj_span(d, s)
        i += 1
def build_dfm(dfm):
    s, e = find_obj(dfm, b"TimeLbl"); raw = dfm[s:e]
    cl = raw[0]; body = raw[1+cl+1+raw[1+cl]:]; out = raw[:1+cl] + sstr(b"CoordLbl") + body
    for old, new in ((b"\x07AOWFont\x07" + sstr(b"FontModule.TBarNumber"), b"\x07AOWFont\x07" + sstr(b"FontModule.Age10")),
                     (b"\x15Alignment.RightOffset\x03\xe1\x00", b"\x15Alignment.RightOffset\x03" + struct.pack("<h", LABEL_RIGHT)),
                     (b"\x16Alignment.BottomOffset\x02\x04", b"\x16Alignment.BottomOffset\x02" + bytes([LABEL_BOTTOM]))):
        assert out.count(old) == 1, old; out = out.replace(old, new)
    return dfm[:e] + out + dfm[e:]
def build_field_table(ft):
    out = bytearray(ft); out += struct.pack("<IH", NEW_FIELD, CLS_LABEL) + sstr(b"CoordLbl")
    struct.pack_into("<H", out, 0, struct.unpack_from("<H", ft, 0)[0] + 1); return bytes(out)

class Asm:
    def __init__(self, base): self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []; self.fix32 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def jcc32(self, op, lab): self.db(0x0F, op + 0x10); self.fix32.append((len(self.buf), lab)); self.dd(0)
    def align(self, n):
        while len(self.buf) % n: self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127, lab; self.buf[off] = rel & 0xFF
        for off, lab in self.fix32:
            struct.pack_into("<i", self.buf, off, self.labels[lab]-(self.base+off+4))
        return bytes(self.buf)

def build_code(va):
    a = Asm(va)
    a.label('flag'); a.dd(0)
    a.label('lastX'); a.dd(-2); a.label('lastY'); a.dd(-2); a.label('lastZ'); a.dd(-2)
    # two static AnsiStrings (refcount -1 = constant, length, chars) used alternately, so the label never
    # receives the very pointer it already holds (a same-text short-circuit in SetGText would skip the repaint)
    a.dd(-1); a.dd(5); a.label('buf0'); a.buf += b"-,-,-\0" + bytes(26)
    a.dd(-1); a.dd(5); a.label('buf1'); a.buf += b"-,-,-\0" + bytes(26)
    a.label('bufsel'); a.dd(a.labels['buf0'])                          # buffer to write next
    a.align(16)
    BUF0, BUF1, BSEL = a.labels['buf0'], a.labels['buf1'], a.labels['bufsel']
    LX, LY, LZ, FLAG = a.labels['lastX'], a.labels['lastY'], a.labels['lastZ'], a.labels['flag']
    # itoa: eax = value (>=0), edi = dest; writes digits, advances edi. clobbers ecx, edx
    a.label('itoa')
    a.db(0x53); a.db(0xBB); a.dd(10); a.db(0x33, 0xC9)              # push ebx ; ebx=10 ; ecx=0
    a.label('i1'); a.db(0x33, 0xD2); a.db(0xF7, 0xF3); a.db(0x52); a.db(0x41); a.db(0x85, 0xC0); a.j8(0x75, 'i1')   # div ; push rem ; inc ecx ; loop while eax
    a.label('i2'); a.db(0x58); a.db(0x04, 0x30); a.db(0xAA); a.db(0xE2, 0xFA)   # pop eax ; add al,'0' ; stosb ; loop i2
    a.db(0x5B); a.db(0xC3)                                           # pop ebx ; ret
    # commit: edi = end of text written into buffer [bufsel]; NUL, length, SetGText(CoordLbl), swap buffers
    a.label('commit')
    a.db(0xC6, 0x07, 0x00)                                            # mov byte [edi],0
    a.db(0x8B, 0x15); a.dd(BSEL)                                      # edx = buffer
    a.db(0x8B, 0xC7); a.db(0x2B, 0xC2); a.db(0x89, 0x42, 0xFC)        # [buffer-4] = edi - buffer
    a.db(0xB8); a.dd(BUF0 + BUF1); a.db(0x2B, 0xC2); a.db(0xA3); a.dd(BSEL)   # bufsel = other buffer
    a.db(0xA1); a.dd(G_TBWINDOW); a.db(0x85, 0xC0); a.j8(0x74, 'sl_ret')
    a.db(0x8B, 0x80); a.dd(NEW_FIELD); a.db(0x85, 0xC0); a.j8(0x74, 'sl_ret')
    a.call(T_SETGTEXT)                                                # SetGText(label=eax, text=edx)
    a.label('sl_ret'); a.db(0xC3)
    # blank: "-,-,-" if not already
    a.label('blank')
    a.db(0x83, 0x3D); a.dd(LX); a.db(0xFF); a.j8(0x74, 'bl_ret')   # cmp dword [lastX],-1 ; je
    a.db(0xC7, 0x05); a.dd(LX); a.dd(-1)
    a.db(0x8B, 0x3D); a.dd(BSEL)                                      # edi = buffer
    a.db(0xC7, 0x07); a.buf += b"-,-,"                                # mov dword [edi],'-,-,'
    a.db(0xC6, 0x47, 0x04, 0x2D)                                      # mov byte [edi+4],'-'
    a.db(0x83, 0xC7, 0x05)                                            # add edi,5
    a.call(a.labels['commit'])
    a.label('bl_ret'); a.db(0xC3)
    # update: flag := 1 ; read hex under cursor ; format ; clobbers eax ecx edx esi edi
    a.label('update')
    a.db(0xC7, 0x05); a.dd(FLAG); a.dd(1)
    a.db(0xA1); a.dd(G_MAP_IAT); a.db(0x8B, 0x00); a.db(0x85, 0xC0); a.jcc32(0x74, 'u_blank')   # map
    a.db(0x8B, 0xF0)                                                  # esi = map
    a.db(0x8B, 0x46, MAP_MOUSE); a.db(0x85, 0xC0); a.jcc32(0x74, 'u_blank')   # mouse obj
    a.db(0x8B, 0xF8)                                                  # edi = mouse
    a.db(0x8B, 0x0D); a.dd(IAT_GETFIELD); a.db(0x81, 0xC1); a.dd((LINK_GETXHX - LINK_GETFIELD) & 0xFFFFFFFF)
    a.db(0x8B, 0xC7); a.db(0xFF, 0xD1)                                # GetXhx(mouse)
    a.db(0x83, 0xF8, 0xFF); a.jcc32(0x74, 'u_blank')
    a.db(0x50)                                                        # push X
    a.db(0x8B, 0x0D); a.dd(IAT_GETFIELD); a.db(0x81, 0xC1); a.dd((LINK_GETYHX - LINK_GETFIELD) & 0xFFFFFFFF)
    a.db(0x8B, 0xC7); a.db(0xFF, 0xD1)                                # GetYhx(mouse)
    a.db(0x59)                                                        # ecx = X
    a.db(0x83, 0xF8, 0xFF); a.jcc32(0x74, 'u_blank')
    a.db(0x8B, 0x96); a.dd(MAP_LEVEL)                                 # edx = level
    a.db(0x3B, 0x0D); a.dd(LX); a.j8(0x75, 'u_chg')
    a.db(0x3B, 0x05); a.dd(LY); a.j8(0x75, 'u_chg')
    a.db(0x3B, 0x15); a.dd(LZ); a.j8(0x74, 'u_ret')
    a.label('u_chg')
    a.db(0x89, 0x0D); a.dd(LX); a.db(0xA3); a.dd(LY); a.db(0x89, 0x15); a.dd(LZ)
    a.db(0x52); a.db(0x50)                                            # push Z ; push Y
    a.db(0x8B, 0x3D); a.dd(BSEL); a.db(0x8B, 0xC1); a.call(a.labels['itoa'])    # edi = buffer ; X
    a.db(0xB0, 0x2C); a.db(0xAA)                                      # ','
    a.db(0x58); a.call(a.labels['itoa'])                              # Y
    a.db(0xB0, 0x2C); a.db(0xAA)
    a.db(0x58); a.call(a.labels['itoa'])                              # Z
    a.call(a.labels['commit'])
    a.label('u_ret'); a.db(0xC3)
    a.label('u_blank'); a.call(a.labels['blank']); a.db(0xC3)
    # cave for hook @0x450F77
    a.label('cave_hook')
    a.db(0x56); a.db(0x57); a.call(a.labels['update']); a.db(0x5F); a.db(0x5E)
    a.db(0x66, 0xBA, 0x0F, 0x27); a.db(0x8B, 0x43, 0x44); a.jmp32(HOOK_CONT)   # replay
    # DisplayMouseMove wrapper (eax,edx,cl regs; X,Y on stack; ret 8)
    a.label('dmm_wrap')
    a.db(0xC7, 0x05); a.dd(FLAG); a.dd(0)
    a.db(0xFF, 0x74, 0x24, 0x08); a.db(0xFF, 0x74, 0x24, 0x08)      # push Y ; push X
    a.call(DISPLAYMOUSEMOVE)
    a.db(0x83, 0x3D); a.dd(FLAG); a.db(0x00); a.j8(0x75, 'w_done')
    a.db(0x56); a.db(0x57); a.call(a.labels['blank']); a.db(0x5F); a.db(0x5E)
    a.label('w_done'); a.db(0xC2, 0x08, 0x00)
    return a.done(), a.labels

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    args = ap.parse_args(); exe, bak = args.exe, bak_path(args.exe, BAK_SUFFIX)
    if args.revert:
        if not os.path.exists(bak): print("no backup"); return 1
        shutil.copyfile(bak, exe); print(f"Restored {exe} from {bak}"); return 0
    import pefile
    d = bytearray(open(exe, "rb").read()); pe = pefile.PE(data=bytes(d))
    already = any(s.Name.rstrip(b"\0") == SEC_NAME for s in pe.sections)
    src = bytes(open(bak, "rb").read()) if already and os.path.exists(bak) else bytes(d); pe0 = pefile.PE(data=src)
    dfm = src[pe0.get_offset_from_rva(RES_RVA):pe0.get_offset_from_rva(RES_RVA) + RES_SIZE]; assert dfm[:4] == b"TPF0"
    ft = src[pe0.get_offset_from_rva(FT_VA - BASE):pe0.get_offset_from_rva(FT_VA - BASE) + FT_LEN]; assert struct.unpack_from("<H", ft, 0)[0] == 60
    new_dfm, new_ft = build_dfm(dfm), build_field_table(ft)
    off_ft = (len(new_dfm) + 15) & ~15; off_code = (off_ft + len(new_ft) + 15) & ~15
    code, L = build_code(SEC_VA + off_code)
    blob = bytearray(off_code + len(code)); blob[:len(new_dfm)] = new_dfm; blob[off_ft:off_ft+len(new_ft)] = new_ft; blob[off_code:] = code
    raw_size = (len(blob) + 0x1FF) & ~0x1FF; assert raw_size <= SEC_VSIZE
    print(f"target: {exe}\n{SEC_NAME.decode()} @{SEC_VA:#x}: dfm {len(new_dfm)} B (+{len(new_dfm)-RES_SIZE}), field table @+{off_ft:#x}, code {len(code)} B @{SEC_VA+off_code:#x} (update {L['update']:#x}, hook cave {L['cave_hook']:#x}, wrapper {L['dmm_wrap']:#x})")
    sites = [
        (VMT_FT_FO, struct.pack("<I", FT_VA), struct.pack("<I", SEC_VA + off_ft), "TTBWindow VMT field-table ptr"),
        (VMT_SIZE_FO, struct.pack("<I", OLD_INST), struct.pack("<I", NEW_INST), "TTBWindow instance size 0x144 -> 0x148"),
        (RES_ENTRY_FO, struct.pack("<II", RES_RVA, RES_SIZE), struct.pack("<II", SEC_VA - BASE, len(new_dfm)), "TTBWINDOW resource -> extended DFM"),
        (pe.get_offset_from_rva(HOOK - BASE), HOOK_ORIG, b"\xE9" + struct.pack("<i", L['cave_hook'] - (HOOK + 5)) + b"\x90\x90", "MapWindowMouseMove after mouse update -> cave"),
        (MT_DMM_FO, struct.pack("<I", DISPLAYMOUSEMOVE), struct.pack("<I", L['dmm_wrap']), "method table DisplayMouseMove -> wrapper"),
    ]
    ok = True; applied = 0
    for off, old, new, desc in sites:
        cur = bytes(d[off:off+len(old)])
        if cur == new: applied += 1
        elif cur != old: print(f"MISMATCH @file {off:#x} ({desc}): exp {old.hex()} got {cur.hex()}"); ok = False
    if already and applied == len(sites):
        sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == SEC_NAME)
        if bytes(d[sec.PointerToRawData:sec.PointerToRawData+len(blob)]) == bytes(blob): print("ALL ALREADY PATCHED"); return 0
    if not ok or (applied and applied != len(sites)): print("Aborting."); return 1
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(exe, bak); print(f"Backup: {bak}")
    e = struct.unpack_from("<I", d, 0x3C)[0]; nsec = struct.unpack_from("<H", d, e + 6)[0]; sec0 = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    if not already:
        assert sec0 + 40 * (nsec + 1) <= pe.sections[0].PointerToRawData
        assert pe.OPTIONAL_HEADER.SizeOfImage == SEC_VA - BASE, f"SizeOfImage {pe.OPTIONAL_HEADER.SizeOfImage:#x}"
        pad = (-len(d)) % 0x200; d += bytes(pad); rawoff = len(d); d += blob + bytes(raw_size - len(blob))
        hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC_VSIZE, SEC_VA - BASE, raw_size, rawoff, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<40s", d, sec0 + 40 * nsec, hdr); struct.pack_into("<H", d, e + 6, nsec + 1); struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE + SEC_VSIZE)
        print(f"appended {SEC_NAME.decode()} raw @{rawoff:#x} ({raw_size:#x} B)")
    else:
        sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == SEC_NAME); assert raw_size <= sec.SizeOfRawData
        d[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData] = blob + bytes(sec.SizeOfRawData - len(blob)); print("refreshed section")
    for off, old, new, desc in sites: d[off:off+len(new)] = new; print("Patched:", desc)
    open(exe, "wb").write(d); print("AoWx.exe patched successfully."); return 0

if __name__ == "__main__":
    sys.exit(main())
