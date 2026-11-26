#!/usr/bin/env python3
"""
AoWDevX.exe: Item Properties dialog gets "Hit points:" and "Movement:" spinners
with icons (TItem +0x4A / +0x4B, see patch_item_hpmv_use_v1.py), and the four
stat spinners are no longer greyed for "Use" items (2026-09-12/13, v2).

TItemEditForm (VMT 0x412d40, DFM TITEMEDITFORM @file 0x697a8, 7487 B, resource
data entry @file 0x434e0): item at [form+0x27C], read-only-library flag at
[form+0x280], StatisticsPnl at [form+0x224], ClientPnl +0x1DC; AttackEdit/
DefenseEdit/ResistanceEdit/DamageEdit (+0x250/+0x254/+0x258/+0x25C) are VCLADDON
TSpin controls (classref IAT 0x43357c = VMT; ctor = VMT+0x24 (eax=class, dl=1,
ecx=owner); Value via TSpin.SetValue/GetValue thunks 0x4030e8/0x4030e0;
OnChange TMethod +0x128/+0x12C, MinValue +0x130, MaxValue +0x134,
EditorEnabled byte +0x140).  Rows: icon x=4 / label x=28 / spin x=124,
y = 24+32*row (icon and label +4).  Update routine 0x41321c (called after the
item is assigned and from ItemTypeBoxChange) loads the spinners and paints
them clBtnFace when [item+0x34]==6 (Use) - that `je` @0x4134A0 is the whole
"greyed out" effect.

v1 crashed (AV in TWinControl.WMWindowPosChanged): the runtime controls were
positioned through the static TControl.SetBounds import, bypassing the
TWinControl.SetBounds override; SetParent/SetBounds go through the VMT now.

Patch (fixed-base exe, no reloc needed):
 1. section .xitm @0x4E5000 (code+statics): published-method-table entry
    FormCreate (dword @file 0x12489) -> wrapper: zero statics, original
    FormCreate, grow form/ClientPnl/StatisticsPnl by 64 px, create two TLabels
    + two TSpins (parent StatisticsPnl, rows 4 and 5, HP -20..30, MV -10..10,
    EditorEnabled=False, OnChange -> handlers writing [item+0x4A]/[+0x4B]).
 2. update routine prologue 0x41321c (5B) -> cave: refresh our spinners
    (Value from the item, colour clBtnFace/clWindow by the read-only flag).
 3. `je 0x4134e4` @0x4134A0 -> nop nop: Use items keep clWindow.
 4. section .xdfm @0x4E6000: the TITEMEDITFORM DFM with two extra TImage
    components (heart / boot bitmaps from the hero editor form, assets\
    item_hp_icon.bmp + item_mv_icon.bmp) in StatisticsPnl; the resource data
    entry is repointed there (RVA + size).  The boot is 32 px wide, so the
    Movement label sits at x=38.

Dry-run default; --apply; --revert (restores the backup copy).
Backup: AoWDevX.exe.bak_itemui
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXE = game_file(r"AoWDevX.exe")
BAK_SUFFIX  = ".bak_itemui"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE        = 0x400000
SEC_CODE = (b".xitm", 0x4E5000, 0x1000, 0x400)      # name, VA, virtual size, raw size
SEC_DFM  = (b".xdfm", 0x4E6000, 0x3000, None)       # raw size computed
RES_ENTRY_FO, RES_RVA, RES_SIZE = 0x434e0, 0x6d1a8, 0x1d3f
ASSETS = {"hp": os.path.join(HERE, "assets", "item_hp_icon.bmp"), "mv": os.path.join(HERE, "assets", "item_mv_icon.bmp")}

# --- exe facts ---
FORMCREATE       = 0x413630
MT_FORMCREATE_FO = 0x12489
UPD_HOOK, UPD_CONT = 0x41321c, 0x413221
UPD_ORIG = bytes.fromhex("558bec33c9")
USEGREY_VA, USEGREY_ORIG = 0x4134A0, bytes.fromhex("7442")
T_SETVALUE, T_GETVALUE = 0x4030e8, 0x4030e0
T_SETTEXT, T_SETCOLOR  = 0x401568, 0x4015a0
IAT_SETHEIGHT = 0x4323c4                          # TControl.SetHeight (dispatches SetBounds virtually inside)
VMT_SETPARENT, VMT_SETBOUNDS = 0x3C, 0x4C          # TControl virtual slots (never the static TControl.SetBounds import on a TWinControl)
IAT_TLABEL, IAT_TSPIN = 0x432654, 0x43357c        # class import slots = VMT
F_ITEM, F_ROFLAG, F_CLIENTPNL, F_STATPNL = 0x27C, 0x280, 0x1DC, 0x224
CTRL_HEIGHT = 0x3C
SPIN_ONCHANGE, SPIN_MIN, SPIN_MAX, SPIN_EDITOR = 0x128, 0x130, 0x134, 0x140
CL_WINDOW, CL_BTNFACE = 0x80000005, 0x8000000F
GROW = 64
ROWS = [  # (label text, item field, min, max, row index, label left)
    ("Hit points:", 0x4A, -20, 30, 4, 28),
    ("Movement:",   0x4B, -10, 10, 5, 28),
]
ICONS = [  # (component name, asset key, left, top) - inserted into StatisticsPnl after Image6
    (b"ImageHP", "hp", 4, 24 + 32*4 + 4),     # heart from the hero editor form (16x16)
    (b"ImageMV", "mv", 4, 24 + 32*5 + 4),     # plain foot, IconMove.ILB #0 cropped onto the 16x16 grey tile
]

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def call_iat(self, slot): self.db(0xFF, 0x15); self.dd(slot)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def align(self, n):
        while len(self.buf) % n: self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127, (lab, rel)
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)

def build_code_section():
    a = Asm(SEC_CODE[1])
    a.label('spin_ptrs'); a.dd(0); a.dd(0)
    for text, *_ in ROWS:
        a.align(4); a.dd(-1); a.dd(len(text)); a.label('txt_' + text); a.buf += text.encode('latin1') + b'\0'
    a.align(16)
    # mk_label(eax=left, edx=text, ecx=top); ebx=form
    a.label('mk_label')
    a.db(0x56); a.db(0x57); a.db(0x50)                  # push esi/edi ; push eax (left)
    a.db(0x8B, 0xF2); a.db(0x8B, 0xF9)                  # esi=text edi=top
    a.db(0xA1); a.dd(IAT_TLABEL); a.db(0xB2, 0x01); a.db(0x8B, 0xCB); a.db(0xFF, 0x50, 0x24)   # TLabel.Create(form)
    a.db(0x50)                                          # push label
    a.db(0x8B, 0x93); a.dd(F_STATPNL); a.db(0x8B, 0x08); a.db(0xFF, 0x51, VMT_SETPARENT)
    a.db(0x8B, 0x04, 0x24)                              # eax = label
    a.db(0x6A, 80); a.db(0x6A, 16)                      # W, H
    a.db(0x8B, 0xCF); a.db(0x8B, 0x54, 0x24, 0x0C)      # ecx=top ; edx=left ([esp+0xC]: label, H, W above it)
    a.db(0x8B, 0x38); a.db(0xFF, 0x57, VMT_SETBOUNDS)
    a.db(0x58); a.db(0x8B, 0xD6); a.call(T_SETTEXT)     # SetText(label, text)
    a.db(0x59); a.db(0x5F); a.db(0x5E); a.db(0xC3)      # pop left ; pop edi/esi
    # mk_spin(ecx=top, edx=slot ptr, [ebp+8]=min, [ebp+12]=max, [ebp+16]=handler); ebx=form
    a.label('mk_spin')
    a.db(0x55); a.db(0x8B, 0xEC); a.db(0x56); a.db(0x57)
    a.db(0x8B, 0xF2); a.db(0x8B, 0xF9)
    a.db(0xA1); a.dd(IAT_TSPIN); a.db(0xB2, 0x01); a.db(0x8B, 0xCB); a.db(0xFF, 0x50, 0x24)    # TSpin.Create(form)
    a.db(0x89, 0x06); a.db(0x50)                        # [slot]=spin ; push spin
    a.db(0x8B, 0x93); a.dd(F_STATPNL); a.db(0x8B, 0x08); a.db(0xFF, 0x51, VMT_SETPARENT)
    a.db(0x8B, 0x04, 0x24); a.db(0x6A, 50); a.db(0x6A, 26); a.db(0x8B, 0xCF); a.db(0xBA); a.dd(124)
    a.db(0x8B, 0x38); a.db(0xFF, 0x57, VMT_SETBOUNDS)
    a.db(0x58)
    a.db(0x8B, 0x55, 0x08); a.db(0x89, 0x90); a.dd(SPIN_MIN)
    a.db(0x8B, 0x55, 0x0C); a.db(0x89, 0x90); a.dd(SPIN_MAX)
    a.db(0xC6, 0x80); a.dd(SPIN_EDITOR); a.db(0x00)
    a.db(0x8B, 0x55, 0x10); a.db(0x89, 0x90); a.dd(SPIN_ONCHANGE); a.db(0x89, 0x98); a.dd(SPIN_ONCHANGE + 4)
    a.db(0x5F); a.db(0x5E); a.db(0x5D); a.db(0xC2, 0x0C, 0x00)
    for text, fld, lo, hi, row, left in ROWS:            # OnChange handlers (eax=form, edx=sender)
        a.label('chg_' + text)
        a.db(0x53); a.db(0x8B, 0xD8); a.db(0x8B, 0xC2); a.call(T_GETVALUE)
        a.db(0x8B, 0x93); a.dd(F_ITEM); a.db(0x85, 0xD2); a.j8(0x74, 'chg_out_' + text)
        a.db(0x88, 0x42, fld)
        a.label('chg_out_' + text); a.db(0x5B); a.db(0xC3)
    a.label('create')                                    # create_controls(eax=form)
    a.db(0x53); a.db(0x8B, 0xD8)
    for getctrl in (None, F_CLIENTPNL, F_STATPNL):
        if getctrl is None: a.db(0x8B, 0xC3)
        else: a.db(0x8B, 0x83); a.dd(getctrl)
        a.db(0x8B, 0x50, CTRL_HEIGHT); a.db(0x83, 0xC2, GROW); a.call_iat(IAT_SETHEIGHT)
    for k, (text, fld, lo, hi, row, left) in enumerate(ROWS):
        a.db(0xB9); a.dd(24 + 32*row + 4); a.db(0xBA); a.dd(a.labels['txt_' + text]); a.db(0xB8); a.dd(left)
        a.call(a.labels['mk_label'])
        a.db(0x68); a.dd(a.labels['chg_' + text]); a.db(0x68); a.dd(hi); a.db(0x68); a.dd(lo)
        a.db(0xBA); a.dd(a.labels['spin_ptrs'] + 4*k); a.db(0xB9); a.dd(24 + 32*row)
        a.call(a.labels['mk_spin'])
    a.db(0x5B); a.db(0xC3)
    a.label('fc_wrap')                                   # FormCreate wrapper (eax=form, edx=sender)
    a.db(0x53); a.db(0x8B, 0xD8); a.db(0x33, 0xC9)
    a.db(0x89, 0x0D); a.dd(a.labels['spin_ptrs']); a.db(0x89, 0x0D); a.dd(a.labels['spin_ptrs'] + 4)
    a.call(FORMCREATE); a.db(0x8B, 0xC3); a.call(a.labels['create']); a.db(0x5B); a.db(0xC3)
    a.label('refresh')                                   # refresh(eax=form)
    a.db(0x53); a.db(0x56); a.db(0x57); a.db(0x8B, 0xD8)
    a.db(0x8B, 0xB3); a.dd(F_ITEM); a.db(0x85, 0xF6); a.j8(0x74, 'rf_out')
    a.db(0xBF); a.dd(CL_WINDOW); a.db(0x80, 0xBB); a.dd(F_ROFLAG); a.db(0x00); a.j8(0x74, 'rf_col'); a.db(0xBF); a.dd(CL_BTNFACE)
    a.label('rf_col')
    for k, (text, fld, *_) in enumerate(ROWS):
        a.db(0xA1); a.dd(a.labels['spin_ptrs'] + 4*k); a.db(0x85, 0xC0); a.j8(0x74, 'rf_skip_' + text)
        a.db(0x50); a.db(0x0F, 0xBE, 0x56, fld); a.call(T_SETVALUE); a.db(0x58); a.db(0x8B, 0xD7); a.call(T_SETCOLOR)
        a.label('rf_skip_' + text)
    a.label('rf_out'); a.db(0x5F); a.db(0x5E); a.db(0x5B); a.db(0xC3)
    a.label('upd_hook')
    a.db(0x50); a.call(a.labels['refresh']); a.db(0x58); a.db(0x55); a.db(0x8B, 0xEC); a.db(0x33, 0xC9); a.jmp32(UPD_CONT)
    blob = a.done(); assert len(blob) <= SEC_CODE[3]
    return blob, a.labels

# ---------------------------------------------------------------- DFM (form) extension
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
        if t == 14:
            while d[p] != 0:
                if d[p] == 1: p += 1
                while d[p] != 0: p += 1 + d[p]; p = skip_val(p)
                p += 1
            return p + 1
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
def vint(v):
    return b"\x02" + struct.pack("<b", v) if -128 <= v <= 127 else b"\x03" + struct.pack("<h", v)
def timage(name, bmp, left, top):
    w, h = struct.unpack_from("<ii", bmp, 18)
    pic = sstr(b"TBitmap") + struct.pack("<I", len(bmp)) + bmp
    return (sstr(b"TImage") + sstr(name) + sstr(b"Left") + vint(left) + sstr(b"Top") + vint(top) +
            sstr(b"Width") + vint(w) + sstr(b"Height") + vint(h) +
            sstr(b"Picture.Data") + b"\x0a" + struct.pack("<I", len(pic)) + pic + b"\x00\x00")
def build_dfm(dfm):
    s, e = find_obj(dfm, b"Image6")          # last TImage in StatisticsPnl; insert after it
    ins = b"".join(timage(nm, open(ASSETS[key], "rb").read(), l, t) for nm, key, l, t in ICONS)
    return dfm[:e] + ins + dfm[e:]

def jmp5(src, dst): return b"\xE9" + struct.pack("<i", dst - (src + 5))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    args = ap.parse_args(); exe, bak = args.exe, bak_path(args.exe, BAK_SUFFIX)
    if args.revert:
        if not os.path.exists(bak): print("no backup - nothing to revert"); return 1
        shutil.copyfile(bak, exe); print(f"Restored {exe} from {bak}"); return 0
    import pefile
    d = bytearray(open(exe, "rb").read()); pe = pefile.PE(data=bytes(d))
    secs = {s.Name.rstrip(b"\0"): s for s in pe.sections}
    src = bytes(open(bak, "rb").read()) if (SEC_DFM[0] in secs and os.path.exists(bak)) else bytes(d)
    pe0 = pefile.PE(data=src); dfm = src[pe0.get_offset_from_rva(RES_RVA):pe0.get_offset_from_rva(RES_RVA)+RES_SIZE]
    assert dfm[:4] == b"TPF0" and len(dfm) == RES_SIZE
    code_blob, L = build_code_section(); dfm_blob = build_dfm(dfm)
    dfm_raw = (len(dfm_blob) + 0x1FF) & ~0x1FF; assert dfm_raw <= SEC_DFM[2]
    print(f"target: {exe}\n{SEC_CODE[0].decode()} @{SEC_CODE[1]:#x}: {len(code_blob)} B; {SEC_DFM[0].decode()} @{SEC_DFM[1]:#x}: DFM {len(dfm_blob)} B (+{len(dfm_blob)-RES_SIZE})")
    print("labels: " + ", ".join(f"{k}={v:#x}" for k, v in L.items() if not k.startswith(('txt_', 'chg_out', 'rf_'))))
    def fo(va): return pe.get_offset_from_rva(va - BASE)
    sites = [
        (MT_FORMCREATE_FO, struct.pack("<I", FORMCREATE), struct.pack("<I", L['fc_wrap']), "method table FormCreate -> fc_wrap"),
        (fo(UPD_HOOK), UPD_ORIG, jmp5(UPD_HOOK, L['upd_hook']), "update routine prologue -> upd_hook"),
        (fo(USEGREY_VA), USEGREY_ORIG, b"\x90\x90", "Use-item grey branch -> nop"),
        (RES_ENTRY_FO, struct.pack("<II", RES_RVA, RES_SIZE), struct.pack("<II", SEC_DFM[1] - BASE, len(dfm_blob)), "TITEMEDITFORM resource -> extended DFM"),
    ]
    plan = [(SEC_CODE[0], SEC_CODE[1], SEC_CODE[2], SEC_CODE[3], code_blob), (SEC_DFM[0], SEC_DFM[1], SEC_DFM[2], dfm_raw, dfm_blob)]
    ok = True; applied = 0
    for off, old, new, desc in sites:
        cur = bytes(d[off:off+len(old)])
        if cur == new: applied += 1
        elif cur != old: print(f"MISMATCH @file {off:#x} ({desc}): exp {old.hex()} got {cur.hex()}"); ok = False
    content_ok = all(n in secs and bytes(d[secs[n].PointerToRawData:secs[n].PointerToRawData+len(blob)]) == blob for n, va, vs, rs, blob in plan)
    if applied == len(sites) and content_ok: print("ALL ALREADY PATCHED"); return 0
    if not ok or (applied and applied != len(sites) and not any(n in secs for n, *_ in plan)): print("Aborting (mismatch)."); return 1
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(exe, bak); print(f"Backup: {bak}")
    e = struct.unpack_from("<I", d, 0x3C)[0]; sec0 = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    for name, va, vsize, raw_size, blob in plan:
        nsec = struct.unpack_from("<H", d, e + 6)[0]
        if name in secs:
            s = secs[name]; assert len(blob) <= s.SizeOfRawData
            d[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData] = blob + bytes(s.SizeOfRawData - len(blob)); print(f"refreshed {name.decode()} in place"); continue
        assert sec0 + 40 * (nsec + 1) <= pe.sections[0].PointerToRawData, "no room for a section header"
        assert struct.unpack_from("<I", d, e + 24 + 56)[0] == va - BASE, f"SizeOfImage != {va:#x}"
        pad = (-len(d)) % 0x200; d += bytes(pad); rawoff = len(d); d += blob + bytes(raw_size - len(blob))
        hdr = name.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", vsize, va - BASE, raw_size, rawoff, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<40s", d, sec0 + 40 * nsec, hdr); struct.pack_into("<H", d, e + 6, nsec + 1)
        struct.pack_into("<I", d, e + 24 + 56, va - BASE + vsize)
        print(f"appended {name.decode()} raw @{rawoff:#x} ({raw_size:#x} B), SizeOfImage -> {va - BASE + vsize:#x}")
    for off, old, new, desc in sites: d[off:off+len(new)] = new; print("Patched:", desc)
    open(exe, "wb").write(d); print("AoWDevX.exe patched successfully."); return 0

if __name__ == "__main__":
    sys.exit(main())
