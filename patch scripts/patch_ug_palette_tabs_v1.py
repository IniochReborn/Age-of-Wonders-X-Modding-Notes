#!/usr/bin/env python3
r"""
Underground Tiles palette gets the surface's terrain tabs (2026-11-14).

User: "update the underground tabs to be the same as surface tabs ... without messing up existing maps and
structure/terrain/object IDs ... the surface terrains etc are dispersed throughout inaccurately described tabs as a
temporary workaround".

Before: Underground = Places | Objects | Dirt | Developer.  The underground twins of the surface decorations (their
own ResourceIDs, used by maps) were parked in row blocks of two pages:
  page 22 (EResourceGrid1 "Objects"):  cells 32.. Grass, 180.. Steppe, 304.. Desert
  page 10 (DirtMOR "Dirt")          :  cells 76.. Snow,  200.. Wasteland
(each block = the surface page's layout shifted by that many cells).
After:  Underground = Places | Objects | Dirt | Grass | Steppe | Desert | Snow | Wasteland | Developer.

Release.hss: ONLY fields 2 (EditID = palette page) and 3 (EditIndex = cell) of those records change, in place
(u32 writes, no size change, CRC redone).  ResourceIDs, classes, art, order are untouched -> maps are unaffected.
Pages: the editor maps a grid to its page through TEResourceEditSettings.GetEditID(grid component NAME) (Enginep
0x5551B32C: name list stored in Release.hss; an unknown name would get a run-time "first free" id).  The stored list
still has names of grids that no longer exist, with ids no record uses - the new grids simply take those names, so
the ids are fixed and the list needs no edit:
  Grass  -> grid "uCitiesMOR" (8)          Steppe    -> "uSpeedBarMOR" (1)       Desert -> "FastSelectMOR" (2)
  Snow   -> "UnderGroundSpeedBar" (18)     Wasteland -> "CitiesMOR" (12)
(uWastelandMOR / page 9 is the old hidden tab with 3 chasm records - left alone.)

AoWDevX.exe: TMAINFORM gets 5 TTabSheet+TEResourceGrid clones of DirtSheet/DirtMOR (renamed, re-captioned) inserted
after DirtSheet in UndergroundMORPage; the DFM is the tail of .xprn (last section) -> section raw/virtual size,
SizeOfImage and the resource entry size grow (same recipe as patch_devx_terrain_palette_v1).  The grids have no
published fields (not needed: no event handlers besides OnLinkToResourceList = LinkToMORList, which is in the clone).

Backups: <game>\backup\AoWDevX.exe.bak_ugtabs, <game>\backup\Release\Release.hss.bak_ugtabs.
⚠ Layered: a --revert of an older Release.hss / AoWDevX backup drops this -> re-run.  Ship BOTH files together (a new
exe with an old hss shows empty tabs; an old exe with a new hss hides the moved decorations).
Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_devx_terrain_palette_v1 as T
import build_rndhex_previews_hss_v1 as H

EXE = T.EXE
HSS = H.OURS
SUF = ".bak_ugtabs"
# (caption, sheet name, grid name, page id, source page, first cell, end cell (excl), expected lead terrain)
TABS = [
    ("Grass", "uGrassSheet", "uCitiesMOR", 8, 22, 32, 180, 1),
    ("Steppe", "uSteppeSheet", "uSpeedBarMOR", 1, 22, 180, 304, 4),
    ("Desert", "uDesertSheet", "FastSelectMOR", 2, 22, 304, 1 << 30, 2),
    ("Snow", "uSnowSheet", "UnderGroundSpeedBar", 18, 10, 76, 200, 3),
    ("Wasteland", "uWastelandSheet2", "CitiesMOR", 12, 10, 200, 1 << 30, 5),
]
TPL_SHEET, TPL_GRID, TPL_CAP = "DirtSheet", "DirtMOR", "Dirt"
NAME_LIST_IDS = {"uCitiesMOR": 8, "uSpeedBarMOR": 1, "FastSelectMOR": 2, "UnderGroundSpeedBar": 18, "CitiesMOR": 12}


def ps(s):
    return bytes([len(s)]) + s.encode("latin1")


# ---------------------------------------------------------------------------------------------- Release.hss
def name_ids(b):
    """the grid-name -> EditID list (CRLF name block followed by the u32 ids)"""
    k = b.index(b"uSpeedBarMOR\r\nFastSelectMOR\r\n")
    n = struct.unpack_from("<I", b, k - 4)[0]
    names = b[k:k + n].decode("latin1").split("\r\n")[:-1]
    ids = struct.unpack_from("<%dI" % len(names), b, k + n)
    return dict(zip(names, ids))


def build_hss(b):
    A = H.parse(b)
    ni = name_ids(b)
    for nm, i in NAME_LIST_IDS.items():
        assert ni.get(nm) == i, ("name list", nm, ni.get(nm))
    recs = A["recs"]
    # absolute offset of every record
    order = sorted(A["ce"], key=lambda e: e[1])
    pos = {e[0]: A["cbase"] + e[1] for e in order}
    page = {cn: H.u32(r, 2) for cn, r in recs.items()}
    cell = {cn: (H.u32(r, 3) or 0) for cn, r in recs.items()}
    used = {}
    for cn in recs:
        used.setdefault(page[cn], set()).add(cell[cn])
    new_pages = {t[3] for t in TABS}
    done = [bool(used.get(p)) for p in new_pages]
    if all(done):
        return None, []
    assert not any(done), "half applied?"
    out = bytearray(b); log = []
    for cap, _sn, _gn, pid, src, c0, c1, terr in TABS:
        assert c0 % 4 == 0
        mv = sorted((cell[cn], cn) for cn in recs if page[cn] == src and c0 <= cell[cn] < c1)
        lead = sum(1 for _c, cn in mv if H.terr(recs[cn])[0] == terr)
        assert len(mv) > 30 and lead >= len(mv) - 2, (cap, len(mv), lead)      # the block really is that terrain
        seen = set()
        for c, cn in mv:
            r = recs[cn]; fo, td = H.fields(r)
            assert 2 in fo and 3 in fo, (cap, cn)
            nc = c - c0
            assert nc not in seen; seen.add(nc)
            a = pos[cn] + td
            assert struct.unpack_from("<I", out, a + fo[2])[0] == src and struct.unpack_from("<I", out, a + fo[3])[0] == c
            struct.pack_into("<I", out, a + fo[2], pid)
            struct.pack_into("<I", out, a + fo[3], nc)
        log.append("  %-9s page %2d  <- page %d cells %d..%d : %d records (rows 0..%d)"
                   % (cap, pid, src, mv[0][0], mv[-1][0], len(mv), (mv[-1][0] - c0) // 4))
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[:-4])) & 0xFFFFFFFF)
    # verify: same records, same RIDs, only fields 2/3 differ
    B = H.parse(bytes(out))
    assert B["order"] == A["order"]
    for cn, r in recs.items():
        r2 = B["recs"][cn]
        assert len(r) == len(r2)
        fo, td = H.fields(r)
        x = bytearray(r); y = bytearray(r2)
        for f in (2, 3):
            if f in fo:
                x[td + fo[f]:td + fo[f] + 4] = y[td + fo[f]:td + fo[f] + 4] = b"\0\0\0\0"
        assert x == y, cn
    return bytes(out), log


# ---------------------------------------------------------------------------------------------- AoWDevX.exe
def build_dfm(dfm):
    D = T.DFM(dfm)
    names = {c["name"] for c in D.comps}
    have = [t[1] in names for t in TABS]
    if all(have):
        return None
    assert not any(have)
    for t in TABS:
        assert t[2] not in names, t[2]
    sh = D.get(TPL_SHEET)
    assert sh["parent"] == "UndergroundMORPage" and len(sh["kids"]) == 1 and sh["kids"][0]["name"] == TPL_GRID
    tpl = dfm[sh["start"]:sh["end"]]
    head = b"\x09TTabSheet" + ps(TPL_SHEET) + b"\x07Caption\x06" + ps(TPL_CAP) + b"\x00"
    ghead = b"\x0eTEResourceGrid" + ps(TPL_GRID)
    assert tpl.startswith(head + ghead) and tpl.count(ps(TPL_GRID)) == 1
    rest = tpl[len(head) + len(ghead):]
    ins = b""
    for cap, sn, gn, _pid, _src, _c0, _c1, _t in TABS:
        ins += b"\x09TTabSheet" + ps(sn) + b"\x07Caption\x06" + ps(cap) + b"\x00" + b"\x0eTEResourceGrid" + ps(gn) + rest
    nd = dfm[:sh["end"]] + ins + dfm[sh["end"]:]
    D2 = T.DFM(nd)
    pc = D2.get("UndergroundMORPage")
    print("  underground tabs:", " | ".join(k["name"] for k in pc["kids"]))
    return nd


def running():
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    return "AoWx.exe" in r or "AoWDevX.exe" in r


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak_e, bak_h = bak_path(EXE, SUF), bak_path(HSS, SUF)
    if revert:
        if running():
            print("game/editor running - close it first"); return 1
        for bak, tgt in ((bak_e, EXE), (bak_h, HSS)):
            if os.path.exists(bak):
                shutil.copy2(bak, tgt); print("restored", bak)
            else:
                print("no backup", bak)
        return 0
    # ---- hss
    b = open(HSS, "rb").read()
    nb, log = build_hss(b)
    print("Release.hss:", "already applied" if nb is None else "")
    print("\n".join(log))
    # ---- exe
    d = open(EXE, "rb").read()
    pe = pefile.PE(data=d)
    rva, dfm = T.mainform_dfm(pe)
    print("AoWDevX.exe:")
    nd = build_dfm(dfm)
    out = None
    if nd is None:
        print("  already applied")
    else:
        secs = pe.sections
        last = max(secs, key=lambda s: s.PointerToRawData)
        assert last.Name.rstrip(b"\0") == b".xprn" and last.PointerToRawData + last.SizeOfRawData == len(d)
        assert max(secs, key=lambda s: s.VirtualAddress) is last
        dfm_fo = pe.get_offset_from_rva(rva)
        assert not any(d[dfm_fo + len(dfm):]), "data after the DFM in .xprn"
        assert struct.unpack_from("<II", d, T.RES_ENTRY_FO) == (rva, len(dfm))
        end = dfm_fo + len(nd)
        new_raw = ((end - last.PointerToRawData) + T.ALIGN - 1) // T.ALIGN * T.ALIGN
        new_vs = max(new_raw, last.Misc_VirtualSize)
        sa = pe.OPTIONAL_HEADER.SectionAlignment
        soi = (last.VirtualAddress + new_vs + sa - 1) // sa * sa
        print("  DFM %d -> %d B (+%d) | .xprn raw %#x -> %#x | SizeOfImage %#x -> %#x"
              % (len(dfm), len(nd), len(nd) - len(dfm), last.SizeOfRawData, new_raw,
                 pe.OPTIONAL_HEADER.SizeOfImage, soi))
        out = bytearray(d[:dfm_fo]) + nd
        out += bytes(last.PointerToRawData + new_raw - len(out))
        sh = last.get_file_offset()
        struct.pack_into("<I", out, sh + 8, new_vs)
        struct.pack_into("<I", out, sh + 16, new_raw)
        struct.pack_into("<I", out, pe.OPTIONAL_HEADER.get_file_offset() + 56, soi)
        struct.pack_into("<I", out, T.RES_ENTRY_FO + 4, len(nd))
        _, chk = T.mainform_dfm(pefile.PE(data=bytes(out)))
        assert chk == nd
    if nb is None and out is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if running():
        print("game/editor running - close it first"); return 1
    for tgt, bak, data in ((HSS, bak_h, nb), (EXE, bak_e, out)):
        if data is None:
            continue
        if not os.path.exists(bak):
            shutil.copy2(tgt, bak); print("backup ->", bak)
        with open(tgt, "r+b") as f:
            f.write(data); f.truncate()
        assert open(tgt, "rb").read() == bytes(data)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
