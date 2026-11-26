#!/usr/bin/env python3
r"""
AoWDevX.exe: list the dual-sphere pairs (ids 9..22) in the spell editor's Sphere drop-down (2026-10-04).

The spell page of TMainForm has `SphereEdit`, a csDropDownList TComboBox whose Items.Strings are hard-coded in
the form's DFM: Cosmos, Life, Death, Earth, Air, Fire, Water, Unknown (8 entries).  The index IS the sphere id:
  load  @0x42C094   movzx edx, byte [spell+0x20] ; mov eax,[form+0x51C] ; call TCustomComboBox.SetItemIndex
  save  @0x42CA4E   TMainForm.SphereEditChange: [spell+0x20] := SphereEdit.ItemIndex (byte store @0x42CA54)
so a pair sphere (9..22, see patch_dual_sphere_plumbing_v1.py) showed an empty box and could not be chosen.
Fix = rewrite that one Items.Strings list: index 7 'Unknown' -> 'Secret', 8 'None' (the engine's msNone), then
the 14 pair names in id order.  Nothing else in the editor names spheres (the only other copy of the list is the
dead vanilla TMAINFORM resource left behind by the prune patch).

The LIVE TMAINFORM DFM is the relocated copy in `.xprn` (+0x4000, resource data entry @file 0x43550 -> RVA 0xED000,
0x4FB1F bytes), written by patch_devx_prune_unused_v2.py, whose .bak_prune base is not present in the uploaded
410 folder - so this is a LAYERED patch on the live exe: the list grows the DFM by ~190 B, which overflows the
0xE7 B of slack at the end of `.xprn` (the last section), so the section's raw/virtual size and SizeOfImage grow
by one 0x200 block and the resource entry's size is updated.  No code, no relocs, no addresses involved.
⚠ If patch_devx_prune_unused_v2.py is ever re-run from a .bak_prune base, re-run this script afterwards.

Backup <game>\backup\AoWDevX.exe.bak_sphereitems (file length changes, so --revert restores the backup copy).
Dry-run default; --apply; --revert; --exe <path>.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_EXE = game_file("AoWDevX.exe")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_sphereitems"
BASE = 0x400000
RES_ENTRY_FO = 0x43550                      # TMAINFORM resource data entry: [rva][size][cp][res]
SEC_NAME = b".xprn"
OLD_ITEMS = ["Cosmos", "Life", "Death", "Earth", "Air", "Fire", "Water", "Unknown"]
NEW_ITEMS = ["Cosmos", "Life", "Death", "Earth", "Air", "Fire", "Water", "Secret", "None",
             "Life/Earth", "Life/Air", "Life/Fire", "Life/Water",
             "Death/Earth", "Death/Air", "Death/Fire", "Death/Water",
             "Earth/Air", "Earth/Fire", "Earth/Water",
             "Air/Fire", "Air/Water",
             "Fire/Water"]
assert len(NEW_ITEMS) == 23


# ---- minimal Delphi DFM walker (same grammar as patch_devx_prune_unused_v2.DfmParser) ---------------
class Dfm(object):
    def __init__(self, data):
        self.d = data

    def rstr(self, o):
        n = self.d[o]
        return self.d[o + 1:o + 1 + n].decode("latin1"), o + 1 + n

    def value(self, o):
        d = self.d
        vt = d[o]; o += 1
        if vt == 0: return o
        if vt == 2: return o + 1
        if vt == 3: return o + 2
        if vt == 4: return o + 4
        if vt == 5: return o + 10
        if vt in (6, 7): return self.rstr(o)[1]
        if vt in (8, 9, 13): return o
        if vt in (10, 12): return o + 4 + struct.unpack_from("<I", d, o)[0]
        if vt == 11:
            while True:
                s, o = self.rstr(o)
                if s == "": return o
        if vt == 1:
            while d[o] != 0:
                o = self.value(o)
            return o + 1
        if vt == 15: return o + 4
        if vt in (16, 17): return o + 8
        if vt == 18: return o + 4 + 2 * struct.unpack_from("<I", d, o)[0]
        if vt == 14:
            while d[o] != 0:
                if d[o] in (2, 3, 4): o = self.value(o)
                assert d[o] == 1; o += 1
                while d[o] != 0:
                    _s, o = self.rstr(o); o = self.value(o)
                o += 1
            return o + 1
        raise ValueError("valuetype %d @ %#x" % (vt, o - 1))

    def obj(self, o):
        d = self.d; start = o
        if (d[o] & 0xF0) == 0xF0:
            o += 1
            if d[start] & 0x02: o = self.value(o)
        cls, o = self.rstr(o); name, o = self.rstr(o)
        props = {}
        while True:
            pn, o2 = self.rstr(o)
            if pn == "": o = o2; break
            vs = o2; o = self.value(o2); props[pn] = (vs, o)
        kids = []
        while d[o] != 0:
            c = self.obj(o); kids.append(c); o = c["end"]
        return dict(cls=cls, name=name, start=start, props=props, children=kids, end=o + 1)


def find_node(node, name):
    if node["name"] == name: return node
    for c in node["children"]:
        r = find_node(c, name)
        if r: return r
    return None


def str_list(data, vs, ve):
    assert data[vs] == 1, "Items.Strings is not a vaList"
    out, o = [], vs + 1
    while data[o] != 0:
        assert data[o] == 6; n = data[o + 1]; out.append(data[o + 2:o + 2 + n].decode("latin1")); o += 2 + n
    assert o + 1 == ve
    return out


def enc_list(items):
    b = b"\x01"
    for s in items:
        e = s.encode("latin1"); assert len(e) < 256; b += b"\x06" + bytes([len(e)]) + e
    return b + b"\x00"


def pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]; opt = struct.unpack_from("<H", d, e + 20)[0]
    secs = []
    for k in range(nsec):
        s = e + 24 + opt + 40 * k
        vs, va, rs, ro = struct.unpack_from("<IIII", d, s + 8)
        secs.append(dict(name=d[s:s + 8].rstrip(b"\0"), vs=vs, va=va, rs=rs, ro=ro, hdr=s))
    return dict(e=e, nsec=nsec, soi_off=e + 24 + 56, secs=secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    exe = a.exe
    bak = bak_path(exe, BAK_SUFFIX, create=a.apply)
    if a.revert:
        if not os.path.exists(bak): print("no backup at", bak); return 1
        shutil.copy2(bak, exe); print("restored", exe, "from", bak); return 0

    d = open(exe, "rb").read()
    P = pe(d)
    last = P["secs"][-1]
    assert last["name"] == SEC_NAME, "last section is %r, not .xprn" % last["name"]
    assert last["ro"] + last["rs"] == len(d), "file has data after .xprn"
    assert struct.unpack_from("<I", d, P["soi_off"])[0] == last["va"] + last["vs"], "SizeOfImage != end of .xprn"
    dfm_rva, dfm_size = struct.unpack_from("<II", d, RES_ENTRY_FO)
    assert last["va"] <= dfm_rva < last["va"] + last["vs"], "TMAINFORM resource is not in .xprn"
    dfm_off = last["ro"] + (dfm_rva - last["va"])
    assert dfm_off + dfm_size <= len(d)
    dfm = d[dfm_off:dfm_off + dfm_size]
    root = Dfm(dfm).obj(4)
    assert root["end"] == dfm_size, "DFM walk does not consume the whole resource"
    node = find_node(root, "SphereEdit")
    assert node and node["cls"] == "TComboBox", "SphereEdit not found"
    vs, ve = node["props"]["Items.Strings"]
    items = str_list(dfm, vs, ve)
    print("live SphereEdit items (%d): %s" % (len(items), items))
    if items == NEW_ITEMS:
        print("already applied"); return 0
    assert items == OLD_ITEMS, "unexpected item list"
    new_dfm = dfm[:vs] + enc_list(NEW_ITEMS) + dfm[ve:]
    root2 = Dfm(new_dfm).obj(4)
    assert root2["end"] == len(new_dfm)
    n2 = find_node(root2, "SphereEdit")
    assert str_list(new_dfm, *n2["props"]["Items.Strings"]) == NEW_ITEMS
    grow = len(new_dfm) - dfm_size
    tail_after = d[dfm_off + dfm_size:]                    # bytes after the DFM inside .xprn (slack, must be zero)
    assert not any(tail_after), "bytes after the DFM in .xprn are not zero"
    need = (dfm_rva - last["va"]) + len(new_dfm)
    new_size = (need + 0x1FF) & ~0x1FF
    assert new_size >= last["rs"]
    out = bytearray(d[:dfm_off]) + new_dfm
    out += bytes(last["ro"] + new_size - len(out))
    struct.pack_into("<I", out, last["hdr"] + 8, new_size)       # VirtualSize
    struct.pack_into("<I", out, last["hdr"] + 16, new_size)      # SizeOfRawData
    struct.pack_into("<I", out, P["soi_off"], last["va"] + new_size)
    struct.pack_into("<I", out, RES_ENTRY_FO + 4, len(new_dfm))
    print("DFM %d -> %d B (+%d) | .xprn size %#x -> %#x | SizeOfImage %#x -> %#x | file %#x -> %#x"
          % (dfm_size, len(new_dfm), grow, last["rs"], new_size, last["va"] + last["vs"], last["va"] + new_size, len(d), len(out)))
    # post-check on the image
    P2 = pe(bytes(out)); l2 = P2["secs"][-1]
    r2, s2 = struct.unpack_from("<II", out, RES_ENTRY_FO)
    chk = bytes(out[l2["ro"] + (r2 - l2["va"]):l2["ro"] + (r2 - l2["va"]) + s2])
    assert chk == new_dfm and l2["ro"] + l2["rs"] == len(out)
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bak):
        shutil.copy2(exe, bak); print("backup ->", bak)
    with open(exe, "wb") as f:
        f.write(bytes(out))
    assert open(exe, "rb").read() == bytes(out)
    print("Written and verified:", exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
