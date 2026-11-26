#!/usr/bin/env python3
"""
AoWx.exe: the in-game item popup (TItemBanner, unit AoWItemBanner) shows the
item's Hit points and Movement bonuses next to ATK/DEF/DMG/RES (2026-09-13).
Companion of patch_item_hpmv_use_v1.py (TItem +0x4A HP / +0x4B MV).

Vanilla facts (AoWx.exe, fixed base 0x400000, DllCharacteristics 0):
  * TItemBanner is a DFM data module (RCDATA TITEMBANNER, 7411 B, resource
    data entry @file 0x72f70): TAOWImage AttackIcon/DefenseIcon/DamageIcon/
    ResistanceIcon (ImageLib IntGfxMod.UnitIcons, CurrentImage 0..3, 15x17)
    + TAOWLabel Attack/Defense/Damage/Resistance, all inside IBannerPopup.
    Fields (field table @0x406978, VMT 0x406950, instance size 0x78):
    +0x4C..+0x58 icons, +0x5C..+0x68 labels, +0x6C DrawBox, +0x70 AbLB.
  * IBannerPopupShow @0x406AE8 (published; OnShow) hides the 8 controls, then
    for each non-zero stat: label := IntToStr(v), show icon+label, place icon
    at (esi+10, top) and label at (esi+30, top+5), esi += 50 wrapping at 130
    into a new row (top += 20); finally the ability list top := top+10.
    The unit banner shows Hits as UnitIcons #4 and Moves as
    IntGfxMod.MoveIcons #16 (32x17).

Patch (new RWX section .xibn @VA 0x60F000):
 1. Extended DFM: HitsIcon (UnitIcons #4), MovesIcon (MoveIcons #16, 32 wide),
    labels Hits/Moves - cloned from AttackIcon/Attack - inserted before
    DrawBox; resource data entry repointed (RVA + size) into the section.
 2. Field table copied + 4 entries (HitsIcon +0x78, MovesIcon +0x7C,
    Hits +0x80, Moves +0x84); VMT-44 -> new table, VMT-28 size 0x78 -> 0x88.
    The DFM reader assigns the new components to those fields by name.
 3. Hook @0x406D7D (`cmp esi,0x1e ; je`) -> cave: hide the 4 new controls,
    then HP and MV blocks identical in shape to the vanilla ones (reading
    [item+0x4A]/[+0x4B]), then replay the compare and jump back.

Dry-run default; --apply; --revert (restores the backup copy).
Backup: AoWx.exe.bak_itembanner
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK_SUFFIX = ".bak_itembanner"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x400000
SEC_NAME, SEC_VA, SEC_VSIZE = b".xibn", 0x60F000, 0x3000

RES_ENTRY_FO = 0x72f70            # IMAGE_RESOURCE_DATA_ENTRY of TITEMBANNER
RES_RVA, RES_SIZE = 0x102278, 0x1cf3
VMT = 0x406950
VMT_FT_FO, VMT_SIZE_FO = 0x5d24, 0x5d34
FT_VA, FT_LEN = 0x406978, 210
OLD_INST, NEW_INST = 0x78, 0x88
CLS_LABEL, CLS_IMAGE = 0, 2       # class table indices (TAOWLabel, TAOWImage)
HOOK, HOOK_ORIG = 0x406D7D, bytes.fromhex("83fe1e7404")   # cmp esi,0x1e ; je +4
CONT_EQ, CONT_NE = 0x406D86, 0x406D82
T_INTTOSTR, T_SETGTEXT = 0x4013ac, 0x403254
F_ITEM_LOCAL, F_STR_LOCAL, F_TOP_LOCAL = -4, -0xC, -8      # [ebp-4] item, [ebp-0xC] temp str, [ebp-8] top
NEW = [  # (icon field, label field, item byte, icon name, label name, imagelib ident or None, current image, winwidth or None)
    (0x78, 0x80, 0x4A, b"HitsIcon",  b"Hits",  None,                   4,  None),
    (0x7C, 0x84, 0x4B, b"MovesIcon", b"Moves", b"IntGfxMod.MoveIcons", 0, 32),   # IconMove.ILB #0 = plain foot (16 = all-terrain variant)
]
# Layout: vanilla = 2 columns per row (esi 30 -> 80, pitch 50, wrap at 130). Six stats would need a
# third row, and the ability list then draws below the popup's surface (allocated once at creation;
# SetHeight later does NOT grow it) -> AV on scroll. So: THREE columns per row, pitch 40, wrap at 150
# (icons at 40/80/120 +15, labels at 60/100/140 - fits the 160-wide popup), max two rows for six stats.
# Chosen per item at layout start: <=4 stats keep the vanilla grid exactly; 5-6 stats use the
# compact grid centred in the popup (start 12: icons 22/62/102, labels 42/82/122).
LAYOUT_VANILLA = (30, 50, 130)   # start, pitch, wrap
LAYOUT_COMPACT = (12, 40, 132)
START_HOOK, START_ORIG = 0x406B89, bytes.fromhex("be1e000000")          # mov esi,0x1e
ADV_SITES = (0x406BFB, 0x406C75, 0x406CEF, 0x406D69)                    # 20-byte column-advance sequences
ADV_ORIG = bytes.fromhex("83c632" "81fe82000000" "7509" "be1e000000" "8345f814")
MOVES_ICON_SHIFT = -6   # IconMove #0 draws the foot from x=8 of its 32-wide frame; UnitIcons art starts at x=2
# Popup height: IBannerPopupShow ends with  h = statsTop + 50 + 10*abilities ; if h > 200 then h := 200
# (0x406E24 cmp imm / 0x406E30 mov imm).  With two stat rows that cap leaves the ability list
# (ahBoth, bottom offset 24) only 26 px -> a scrolled repaint AVs in ILPACK TRLESprite16.GrabImage
# (wheel over the abilities crashed to desktop).  Raise the cap so any list that must scroll is >= 66 px.
# Instead of a taller popup (user disliked it), tighten vertical spacing so two stat rows still
# leave the list ~50 px at the vanilla 200 cap:
#   stats top 100 -> 94 (name label ends ~91), row pitch 20 -> 18 (icons are 17 tall),
#   list top = statsBottom + 10 -> +4, list bottom offset 24 -> 16 (DFM AbLB Alignment.BottomOffset),
#   popup height base 50 -> 36 keeps list = 16 + 10*abilities when uncapped (as vanilla).
STATS_TOP_OLD, STATS_TOP_NEW = 0x64, 0x5E          # mov dword [ebp-8],imm @0x406B8E (imm @+3)
ROW_H = 18                                         # row pitch used by adv (vanilla 20)
LIST_GAP_OLD, LIST_GAP_NEW = 0x0A, 0x04            # add eax,imm8 @0x406D97
POPUP_BASE_OLD, POPUP_BASE_NEW = 0x32, 0x24        # add eax,imm8 @0x406E14
LIST_BOTTOM_OLD, LIST_BOTTOM_NEW = 24, 16          # AbLB Alignment.BottomOffset (DFM)
SPACING_SITES = ((0x406B91, bytes([STATS_TOP_OLD]), bytes([STATS_TOP_NEW]), "stats top 100 -> 94"),
                 (0x406D99, bytes([LIST_GAP_OLD]), bytes([LIST_GAP_NEW]), "list gap 10 -> 4"),
                 (0x406E16, bytes([POPUP_BASE_OLD]), bytes([POPUP_BASE_NEW]), "popup height base 50 -> 36"))
def fo_of(pe, rva): return pe.get_offset_from_rva(rva)

# ---------------------------------------------------------------- DFM edit
def sstr(s): return bytes([len(s)]) + s
def read_obj_span(dfm, o):
    """Return end offset of the object starting at o (binary DFM, no collections)."""
    def skip_val(p):
        t = dfm[p]; p += 1
        if t in (0, 8, 9, 13): return p
        if t == 1:
            while dfm[p] != 0: p = skip_val(p)
            return p + 1
        if t == 2: return p + 1
        if t == 3: return p + 2
        if t == 4: return p + 4
        if t == 5: return p + 10
        if t in (6, 7): return p + 1 + dfm[p]
        if t == 10: return p + 4 + struct.unpack_from("<I", dfm, p)[0]
        if t == 11:
            while dfm[p] != 0: p += 1 + dfm[p]
            return p + 1
        if t == 12: return p + 4 + struct.unpack_from("<I", dfm, p)[0]
        raise ValueError(f"vtype {t} @{p:#x}")
    p = o + 1 + dfm[o]; p += 1 + dfm[p]          # class, name
    while dfm[p] != 0:
        p += 1 + dfm[p]; p = skip_val(p)         # prop name, value
    p += 1
    while dfm[p] != 0: p = read_obj_span(dfm, p)
    return p + 1
def find_obj(dfm, name):
    key = sstr(name); i = 0
    while True:
        i = dfm.find(key, i)
        if i < 0: raise KeyError(name)
        # preceded by a class shortstring: byte at i-1-len(cls) == len(cls); check class name is 'T...'
        for cl in range(3, 40):
            s = i - 1 - cl
            if s >= 0 and dfm[s] == cl and dfm[s+1:s+2] == b"T": return s, read_obj_span(dfm, s)
        i += 1
def clone(dfm, src, newname, patches):
    s, e = find_obj(dfm, src); raw = dfm[s:e]
    cl = raw[0]; body = raw[1+cl+1+raw[1+cl]:]     # after class + name
    out = raw[:1+cl] + sstr(newname) + body
    for old, new in patches:
        assert out.count(old) == 1, (src, old); out = out.replace(old, new)
    return out
def build_dfm(dfm):
    ins = b""
    for icon_f, lbl_f, byte, iname, lname, lib, cur, ww in NEW:
        pats = [(b"\x0cCurrentImage\x02\x00", b"\x0cCurrentImage\x02" + bytes([cur]))]
        if lib: pats.append((b"\x08ImageLib\x07" + sstr(b"IntGfxMod.UnitIcons"), b"\x08ImageLib\x07" + sstr(lib)))
        if ww:
            pats.append((b"\x08WinWidth\x02\x0f", b"\x08WinWidth\x02" + bytes([ww])))
            pats.append((b"\x06Masked\x08", b"\x06Masked\x09"))     # the foot frame is half transparent: colour-key it
        ins += clone(dfm, b"AttackIcon", iname, pats)
        ins += clone(dfm, b"Attack", lname, [])
    s, e = find_obj(dfm, b"DrawBox")
    out = dfm[:s] + ins + dfm[s:]
    old = b"\x16Alignment.BottomOffset\x02" + bytes([LIST_BOTTOM_OLD]); new = b"\x16Alignment.BottomOffset\x02" + bytes([LIST_BOTTOM_NEW])
    assert out.count(old) == 1, out.count(old)          # only AbLB carries a non-zero bottom offset
    return out.replace(old, new)

def build_field_table(ft):
    cnt = struct.unpack_from("<H", ft, 0)[0]; out = bytearray(ft)
    for icon_f, lbl_f, byte, iname, lname, lib, cur, ww in NEW:
        out += struct.pack("<IH", icon_f, CLS_IMAGE) + sstr(iname)
        out += struct.pack("<IH", lbl_f, CLS_LABEL) + sstr(lname)
    struct.pack_into("<H", out, 0, cnt + 2 * len(NEW))
    return bytes(out)

# ---------------------------------------------------------------- cave
class Asm:
    def __init__(self, base): self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def jcc32(self, op2, lab): self.db(0x0F, op2); self.fix32.append((len(self.buf), lab)); self.dd(0)
    fix32 = None
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127; self.buf[off] = rel & 0xFF
        for off, lab in (self.fix32 or []):
            self.buf[off:off+4] = (self.labels[lab]-(self.base+off+4)).to_bytes(4, 'little', signed=True)
        return bytes(self.buf)
def vcall(a, field, slot):                 # mov eax,[ebx+field] ; mov ecx,[eax] ; call [ecx+slot]
    a.db(0x8B, 0x83); a.dd(field); a.db(0x8B, 0x08); a.db(0xFF, 0x51, slot)
def build_cave(va):
    a = Asm(va); a.fix32 = []
    # ---- statics: start / pitch / wrap (RWX section) ----
    a.label('lay_start'); a.dd(0); a.label('lay_pitch'); a.dd(0); a.label('lay_wrap'); a.dd(0)
    # ---- setup (called from 0x406B89 in place of `mov esi,0x1e`): pick layout, esi := start ----
    a.label('setup')
    a.db(0x51); a.db(0x52)                               # push ecx ; push edx
    a.db(0x8B, 0x45, F_ITEM_LOCAL & 0xFF)                # eax = item
    a.db(0x33, 0xC9)                                     # ecx = 0 (non-zero stat count)
    for off in (0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B):
        a.db(0x80, 0x78, off, 0x00); a.db(0x0F, 0x95, 0xC2); a.db(0x0F, 0xB6, 0xD2); a.db(0x03, 0xCA)   # cmp ; setne dl ; movzx ; add ecx,edx
    a.db(0x83, 0xF9, 0x04); a.j8(0x7F, 'compact')        # cmp ecx,4 ; jg compact
    for lab, val in zip(('lay_start', 'lay_pitch', 'lay_wrap'), LAYOUT_VANILLA):
        a.db(0xC7, 0x05); a.dd(a.labels[lab]); a.dd(val)
    a.j8(0xEB, 'setup_done')
    a.label('compact')
    for lab, val in zip(('lay_start', 'lay_pitch', 'lay_wrap'), LAYOUT_COMPACT):
        a.db(0xC7, 0x05); a.dd(a.labels[lab]); a.dd(val)
    a.label('setup_done')
    a.db(0x8B, 0x35); a.dd(a.labels['lay_start'])        # esi = start
    a.db(0x5A); a.db(0x59); a.db(0xC3)                   # pop edx ; pop ecx ; ret
    # ---- adv: esi += pitch ; wrap -> esi = start, top += 20  (caller's ebp frame) ----
    a.label('adv')
    a.db(0x03, 0x35); a.dd(a.labels['lay_pitch'])        # add esi,[pitch]
    a.db(0x3B, 0x35); a.dd(a.labels['lay_wrap'])         # cmp esi,[wrap]
    a.j8(0x75, 'adv_ret')
    a.db(0x8B, 0x35); a.dd(a.labels['lay_start'])        # mov esi,[start]
    a.db(0x83, 0x45, F_TOP_LOCAL & 0xFF, ROW_H)          # add dword [ebp-8],ROW_H
    a.label('adv_ret'); a.db(0xC3)
    a.label('cave')
    for icon_f, lbl_f, *_ in NEW:          # hide our 4 controls first
        a.db(0x33, 0xD2); vcall(a, icon_f, 0x6C)
        a.db(0x33, 0xD2); vcall(a, lbl_f, 0x6C)
    for icon_f, lbl_f, byte, iname, *_ in NEW:
        skip = b"skip_" + iname
        a.db(0x8B, 0x45, F_ITEM_LOCAL & 0xFF)            # mov eax,[ebp-4]
        a.db(0x80, 0x78, byte, 0x00); a.jcc32(0x84, skip)   # cmp byte [eax+byte],0 ; je (near)
        a.db(0x8D, 0x55, F_STR_LOCAL & 0xFF)             # lea edx,[ebp-0xC]
        a.db(0x8B, 0x45, F_ITEM_LOCAL & 0xFF)
        a.db(0x0F, 0xBE, 0x40, byte)                     # movsx eax, byte [eax+byte]
        a.call(T_INTTOSTR)
        a.db(0x8B, 0x55, F_STR_LOCAL & 0xFF)             # mov edx,[ebp-0xC]
        a.db(0x8B, 0x83); a.dd(lbl_f); a.call(T_SETGTEXT)
        a.db(0xB2, 0x01); vcall(a, lbl_f, 0x6C)          # show label
        a.db(0xB2, 0x01); vcall(a, icon_f, 0x6C)         # show icon
        shift = MOVES_ICON_SHIFT if iname == b"MovesIcon" else 0
        a.db(0x8D, 0x56, (0x0A + shift) & 0xFF); vcall(a, icon_f, 0x58)   # icon.Left = esi+10 (+shift)
        a.db(0x8D, 0x56, 0x1E); vcall(a, lbl_f, 0x58)    # label.Left = esi+30
        a.db(0x8B, 0x55, F_TOP_LOCAL & 0xFF); vcall(a, icon_f, 0x5C)                     # icon.Top = top
        a.db(0x8B, 0x55, F_TOP_LOCAL & 0xFF); a.db(0x83, 0xC2, 0x05); vcall(a, lbl_f, 0x5C)  # label.Top = top+5
        a.call(a.labels['adv'])                          # next column / row
        a.label(skip)
    # ---- tail: finish the row like vanilla, then size the popup so the ability list (aligned
    # ahBoth: top = stats bottom + 10, bottom offset 24) keeps >= LIST_MIN px; the AbVSB scrollbar
    # (ahNone, DFM top 110) is moved/sized to match.  Vanilla's 184 px popup left a 10 px list for
    # 4-stat items -> unreadable abilities and an AV in TRLESprite16.GrabImage on wheel repaint.
    a.db(0x3B, 0x35); a.dd(a.labels['lay_start']); a.j8(0x74, 'rows_done')   # cmp esi,[start] ; je
    a.db(0x83, 0x45, F_TOP_LOCAL & 0xFF, ROW_H)          # add dword [ebp-8],ROW_H (partial row)
    a.label('rows_done')
    a.jmp32(CONT_EQ)                                     # continue past the vanilla partial-row add
    # (vanilla then sets popup height = top + 50 + 10*abilities, clamped - see POPUP_CAP sites -
    #  and the list/scrollbar follow by alignment)
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
    src = bytes(open(bak, "rb").read()) if already and os.path.exists(bak) else bytes(d)
    pe0 = pefile.PE(data=src)
    dfm = src[pe0.get_offset_from_rva(RES_RVA):pe0.get_offset_from_rva(RES_RVA) + RES_SIZE]
    assert dfm[:4] == b"TPF0" and len(dfm) == RES_SIZE
    ft = src[pe0.get_offset_from_rva(FT_VA - BASE):pe0.get_offset_from_rva(FT_VA - BASE) + FT_LEN]
    assert struct.unpack_from("<H", ft, 0)[0] == 13
    new_dfm = build_dfm(dfm); new_ft = build_field_table(ft)
    # section layout: [dfm][pad16][field table][pad16][cave]
    off_dfm = 0; off_ft = (len(new_dfm) + 15) & ~15; off_cave = (off_ft + len(new_ft) + 15) & ~15
    cave, CL = build_cave(SEC_VA + off_cave)
    blob = bytearray(off_cave + len(cave)); blob[0:len(new_dfm)] = new_dfm; blob[off_ft:off_ft+len(new_ft)] = new_ft; blob[off_cave:] = cave
    raw_size = (len(blob) + 0x1FF) & ~0x1FF; assert raw_size <= SEC_VSIZE
    print(f"target: {exe}\n{SEC_NAME.decode()} @{SEC_VA:#x}: dfm {len(new_dfm)} B (+{len(new_dfm)-RES_SIZE}), field table {len(new_ft)} B @+{off_ft:#x}, cave {len(cave)} B @{SEC_VA+off_cave:#x} (setup {CL['setup']:#x}, adv {CL['adv']:#x}, cave {CL['cave']:#x})")
    sites = [
        (VMT_FT_FO, struct.pack("<I", FT_VA), struct.pack("<I", SEC_VA + off_ft), "VMT field-table ptr -> extended table"),
        (VMT_SIZE_FO, struct.pack("<I", OLD_INST), struct.pack("<I", NEW_INST), "TItemBanner instance size 0x78 -> 0x88"),
        (RES_ENTRY_FO, struct.pack("<II", RES_RVA, RES_SIZE), struct.pack("<II", SEC_VA - BASE, len(new_dfm)), "TITEMBANNER resource -> extended DFM"),
        (pe.get_offset_from_rva(HOOK - BASE), HOOK_ORIG, b"\xE9" + struct.pack("<i", CL['cave'] - (HOOK + 5)), "IBannerPopupShow tail -> cave"),
        (pe.get_offset_from_rva(START_HOOK - BASE), START_ORIG, b"\xE8" + struct.pack("<i", CL['setup'] - (START_HOOK + 5)), "layout start -> setup (pick grid by stat count)"),
    ]
    for va in ADV_SITES:
        sites.append((pe.get_offset_from_rva(va - BASE), ADV_ORIG, b"\xE8" + struct.pack("<i", CL['adv'] - (va + 5)) + b"\x90" * 15, f"column advance -> adv @{va:#x}"))
    for va, old, new, desc in SPACING_SITES:
        sites.append((pe.get_offset_from_rva(va - BASE), old, new, f"{desc} @{va:#x}"))
    ok = True; applied = 0
    for off, old, new, desc in sites:
        cur = bytes(d[off:off+len(old)])
        if cur == new: applied += 1
        elif cur != old: print(f"MISMATCH @file {off:#x} ({desc}): exp {old.hex()} got {cur.hex()}"); ok = False
    if already and applied == len(sites):
        sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == SEC_NAME)
        if bytes(d[sec.PointerToRawData:sec.PointerToRawData+len(blob)]) == bytes(blob): print("ALL ALREADY PATCHED"); return 0
    if not ok or (applied and applied != len(sites)): print("Aborting (partial/mismatch)."); return 1
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(exe, bak); print(f"Backup: {bak}")
    e = struct.unpack_from("<I", d, 0x3C)[0]; nsec = struct.unpack_from("<H", d, e + 6)[0]
    sec0 = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    if not already:
        assert sec0 + 40 * (nsec + 1) <= pe.sections[0].PointerToRawData, "no room for a section header"
        assert pe.OPTIONAL_HEADER.SizeOfImage == SEC_VA - BASE, f"SizeOfImage {pe.OPTIONAL_HEADER.SizeOfImage:#x}"
        pad = (-len(d)) % 0x200; d += bytes(pad); rawoff = len(d); d += blob + bytes(raw_size - len(blob))
        hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC_VSIZE, SEC_VA - BASE, raw_size, rawoff, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<40s", d, sec0 + 40 * nsec, hdr); struct.pack_into("<H", d, e + 6, nsec + 1)
        struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE + SEC_VSIZE)
        print(f"appended {SEC_NAME.decode()} raw @{rawoff:#x} ({raw_size:#x} B), SizeOfImage -> {SEC_VA - BASE + SEC_VSIZE:#x}")
    else:
        sec = next(s for s in pe.sections if s.Name.rstrip(b"\0") == SEC_NAME)
        assert raw_size <= sec.SizeOfRawData; d[sec.PointerToRawData:sec.PointerToRawData + sec.SizeOfRawData] = blob + bytes(sec.SizeOfRawData - len(blob)); print("refreshed section in place")
    for off, old, new, desc in sites: d[off:off+len(new)] = new; print("Patched:", desc)
    open(exe, "wb").write(d); print("AoWx.exe patched successfully."); return 0

if __name__ == "__main__":
    sys.exit(main())
