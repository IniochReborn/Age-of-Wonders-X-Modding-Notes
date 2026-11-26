#!/usr/bin/env python3
r"""
AoWDevX.exe: cross-level terrain brushes + Sky / Chasm brushes in the Tiles palette (2026-10-31).

User: copy BXL's Ziggurat editor "cross level" terrain.  Ziggurat's TMAINFORM terrain panels are byte-identical to
ours apart from Height 76 -> 152 plus 8 appended TSpeedButtons each (verified by this script):
  Surface tab  (ToolbarPnl): + SkyBtn, XuWaterBtn, XDirtBtn, XLavaBtn, XuIceBtn, XEarthBtn, XRockBtn, ChasmBtn
  Underground  (Panel10)   : + uChasmBtn, uSkyBtn, XWaterBtn, XGrassBtn, XSteppeBtn, XDesertBtn, XWastelandBtn,
                               XSnowBtn, XIceBtn
The X* clones point at the existing handlers by name (OnClick resolves at form load); glyphs travel with the DFM.
SkyBtnClick (terrain 0xE) / ChasmBtnClick (0xB) are new: copies of TMainForm.uWaterBtnClick 0x42B594 (dl=0xA)
with the immediate changed, at .xprn 0x4EB5A0 / 0x4EB5D0 (zero run 0x4EB592..0x4EB800), and two entries appended
in place to the relocated published-method table (0x4EB800, count 134 -> 136, end 0x4EC49A -> 0x4EC4C0; free up to
0x4EC500 = patch_devx_text_limits_v1 zone).  An unresolved OnClick raises EReadError at startup, so a launch that
shows the form proves the names resolved.
The live TMAINFORM DFM sits at the end of .xprn (the last section): the DFM is rebuilt with the two panels swapped
for Ziggurat's, .xprn raw/virtual size + SizeOfImage grow, resource entry size updated (as patch_devx_sphere_items_v1).

Until the engine half (Sky/Chasm terrain patch) is applied, Sky paints Coast (engine turns it into water) and Chasm
paints uWasteland.
⚠ Layered on the live exe: patch_devx_prune_unused_v2 (rebuilds .xprn + method table) / patch_devx_sphere_items_v1
re-runs would drop this -> re-run this after them.  File length changes -> --revert restores the backup copy.
Backup <game>\backup\AoWDevX.exe.bak_terrainpal.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWDevX.exe")
ZIG = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\AoWzEd.exe"
BASE = 0x400000
RES_ENTRY_FO = 0x43550
VMT = 0x425D00
TEMPLATE, TPL_LEN, TPL_ID = 0x42B594, 0x2C, 0x0A
STUBS = [("SkyBtnClick", 0x4EB5A0, 0x0E), ("ChasmBtnClick", 0x4EB5D0, 0x0B)]
STUB_ZONE = (0x4EB592, 0x4EB800)
MT_VA, MT_END_OLD, MT_LIMIT, MT_N_OLD = 0x4EB800, 0x4EC49A, 0x4EC500, 134
PANELS = ["ToolbarPnl", "Panel10"]
ALIGN = 0x200


# ---- minimal Delphi DFM (TPF0) reader: component spans -------------------------------------------------------
class DFM:
    def __init__(self, raw):
        self.raw = raw; self.comps = []; self.p = 4
        assert raw[:4] == b"TPF0"
        self.comp(None)

    def rs(self):
        n = self.raw[self.p]; v = self.raw[self.p + 1:self.p + 1 + n]; self.p += 1 + n; return v

    def val(self):
        r = self.raw; t = r[self.p]; self.p += 1
        if t in (0, 8, 9, 13):
            return
        if t == 1:
            while r[self.p]:
                self.val()
            self.p += 1; return
        if t in (2, 3, 4):
            self.p += {2: 1, 3: 2, 4: 4}[t]; return
        if t == 5:
            self.p += 10; return
        if t in (6, 7):
            self.rs(); return
        if t in (10, 12):
            self.p += 4 + struct.unpack_from("<I", r, self.p)[0]; return
        if t == 11:
            while r[self.p]:
                self.rs()
            self.p += 1; return
        if t == 14:
            while r[self.p]:
                if r[self.p] in (2, 3, 4):
                    self.val()
                assert r[self.p] == 1; self.p += 1
                while r[self.p]:
                    self.rs(); self.val()
                self.p += 1
            self.p += 1; return
        raise ValueError("DFM value type %d at %#x" % (t, self.p - 1))

    def comp(self, parent):
        st = self.p
        if self.raw[self.p] & 0xF0 == 0xF0:
            self.p += 1
        cls = self.rs(); name = self.rs()
        while self.raw[self.p]:
            self.rs(); self.val()
        self.p += 1
        c = dict(cls=cls, name=name.decode("latin1"), start=st, parent=parent, kids=[])
        ks = self.p
        while self.raw[self.p]:
            c["kids"].append(self.comp(c["name"]))
        self.p += 1
        c["kids_start"] = ks; c["end"] = self.p
        self.comps.append(c)
        return c

    def get(self, name):
        m = [c for c in self.comps if c["name"] == name]
        assert len(m) == 1, (name, len(m))
        return m[0]


def mainform_dfm(pe):
    for e in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if e.id == 10:
            for n in e.directory.entries:
                if str(n.name) == "TMAINFORM":
                    de = n.directory.entries[0].data.struct
                    return de.OffsetToData, pe.get_data(de.OffsetToData, de.Size)
    raise KeyError("TMAINFORM")


def new_dfm(ours, zig):
    a = DFM(ours); z = DFM(zig)
    out = bytearray(); pos = 0
    spans = []
    for pn in PANELS:
        ca, cz = a.get(pn), z.get(pn)
        ka, kz = ca["kids"], cz["kids"]
        assert len(kz) > len(ka)
        for x, y in zip(ka, kz):                       # our buttons == the first ones of his panel
            assert ours[x["start"]:x["end"]] == zig[y["start"]:y["end"]], (pn, x["name"])
        ha = ours[ca["start"]:ca["kids_start"]]; hz = zig[cz["start"]:cz["kids_start"]]
        assert ha.replace(b"\x06Height\x02\x4c", b"\x06Height\x03\x98\x00") == hz, pn
        spans.append((ca["start"], ca["end"], zig[cz["start"]:cz["end"]]))
    for s, e, blob in sorted(spans):
        out += ours[pos:s] + blob; pos = e
    out += ours[pos:]
    DFM(bytes(out))                                    # re-parse check
    return bytes(out)


def stub_bytes(tpl, va, tid):
    b = bytearray(tpl)
    assert b[0x10] == TPL_ID and b[0x1E] == TPL_ID and b[0x17] == 0xE8 and b[0x25] == 0xE8
    b[0x10] = b[0x1E] = tid
    for at in (0x17, 0x25):
        tgt = TEMPLATE + at + 5 + struct.unpack_from("<i", tpl, at + 1)[0]
        struct.pack_into("<i", b, at + 1, tgt - (va + at + 5))
    return bytes(b)


def running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWDevX.exe"], capture_output=True, text=True).stdout
    return "AoWDevX.exe" in r


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(EXE, ".bak_terrainpal")
    if revert:
        if not os.path.exists(bak):
            print("no backup", bak); return 1
        if running():
            print("AoWDevX.exe is running - close the editor first"); return 1
        shutil.copy2(bak, EXE); print("restored", bak); return 0
    d = open(EXE, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    rva, dfm = mainform_dfm(pe)
    if b"\x06SkyBtn" in dfm:
        print("already applied (TMAINFORM has SkyBtn)"); return 0
    zpe = pefile.PE(ZIG)
    _, zdfm = mainform_dfm(zpe)
    nd = new_dfm(dfm, zdfm)
    # code stubs + method table
    tpl = d[off(TEMPLATE):off(TEMPLATE) + TPL_LEN]
    assert not any(d[off(STUB_ZONE[0]):off(STUB_ZONE[1])]), "stub zone not zero"
    n = struct.unpack_from("<H", d, off(MT_VA))[0]
    assert struct.unpack_from("<I", d, off(VMT - 0x28))[0] == MT_VA and n == MT_N_OLD, (n,)
    assert not any(d[off(MT_END_OLD):off(MT_LIMIT)]), "method-table tail not zero"
    ents = b""
    for nm, va, tid in STUBS:
        ents += struct.pack("<HI", 7 + len(nm), va) + bytes([len(nm)]) + nm.encode()
    assert MT_END_OLD + len(ents) <= MT_LIMIT
    # section growth
    secs = pe.sections
    last = max(secs, key=lambda s: s.PointerToRawData)
    assert last.Name.rstrip(b"\0") == b".xprn" and last.PointerToRawData + last.SizeOfRawData == len(d)
    assert max(secs, key=lambda s: s.VirtualAddress) is last
    dfm_fo = pe.get_offset_from_rva(rva)
    assert not any(d[dfm_fo + len(dfm):]), "data after the DFM in .xprn"
    end = dfm_fo + len(nd)
    new_raw = ((end - last.PointerToRawData) + ALIGN - 1) // ALIGN * ALIGN
    new_vs = max(new_raw, last.Misc_VirtualSize)
    sa = pe.OPTIONAL_HEADER.SectionAlignment
    soi = (last.VirtualAddress + new_vs + sa - 1) // sa * sa
    print("DFM %d -> %d B (+%d) | .xprn raw %#x -> %#x | SizeOfImage %#x -> %#x | stubs %s | method table %d -> %d"
          % (len(dfm), len(nd), len(nd) - len(dfm), last.SizeOfRawData, new_raw, pe.OPTIONAL_HEADER.SizeOfImage,
             soi, ", ".join("%s@%#x" % (s[0], s[1]) for s in STUBS), n, n + len(STUBS)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if running():
        print("AoWDevX.exe is running - close the editor first"); return 1
    if not os.path.exists(bak):
        shutil.copy2(EXE, bak); print("backup ->", bak)
    out = bytearray(d[:dfm_fo]) + nd
    out += bytes(last.PointerToRawData + new_raw - len(out))
    sh = last.get_file_offset()
    struct.pack_into("<I", out, sh + 8, new_vs)
    struct.pack_into("<I", out, sh + 16, new_raw)
    struct.pack_into("<I", out, pe.OPTIONAL_HEADER.get_file_offset() + 56, soi)
    struct.pack_into("<I", out, RES_ENTRY_FO + 4, len(nd))
    assert struct.unpack_from("<I", out, RES_ENTRY_FO)[0] == rva
    for nm, va, tid in STUBS:
        out[off(va):off(va) + TPL_LEN] = stub_bytes(tpl, va, tid)
    out[off(MT_END_OLD):off(MT_END_OLD) + len(ents)] = ents
    struct.pack_into("<H", out, off(MT_VA), n + len(STUBS))
    try:
        with open(EXE, "r+b") as f:
            f.write(out); f.truncate()
    except PermissionError:
        print("LOCKED - close the editor and retry"); return 1
    pe2 = pefile.PE(EXE)
    _, chk = mainform_dfm(pe2)
    assert chk == nd
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
