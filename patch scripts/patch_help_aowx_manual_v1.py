#!/usr/bin/env python3
r"""
Help menu: "www.ageofwonders.com" -> "AoWx Manual", opening https://aowx.org/ (2026-10-19).

User: "the in-game help section of the menu has a subsection called ageofwonders.com ... I want it to instead
say 'AoWx Manual', and launch the browser and navigate to https://aowx.org/".

Where things live (AoWx.exe, fixed base 0x400000):
  * Click handler 0x4278D0 (index-based - the menu item is never compared by text): ... push 5 / push 0 / push 0 /
    push 0x42790C (URL) / push 0x427928 ('open') / push hwnd / call ShellExecute thunk 0x421F8C.
    URL literal "http://www.ageofwonders.com\0" at VA 0x42790C (file 0x26D0C, 28 bytes incl. NUL), 'open' follows at
    0x427928.  "https://aowx.org/" (17 + NUL) is written in place, the rest NUL-padded; the push immediate (relocated)
    is untouched.
  * Label: RCDATA TPOPUPWINDOWS (file 0x149A6C, size 0x2CD3, data entry @file 0x73070) - TAOWMenu HelpMenu and
    TCHelpMenu (strategic + tactical) Items.Strings = ['General Interface','Map Interface','www.ageofwonders.com'].
    The third item becomes 'AoWx Manual' in both (DFM shrinks by 2 x 9 bytes; the tail is moved down, the freed
    bytes zeroed and the data entry Size lowered - nothing after it moves).
  * Dict\AoW.mld + Dict\AoWVan.MLD rows keyed ('www.ageofwonders.com', TPopupWindows, HelpMenu|TCHelpMenu): the
    English/German/French/Italian/Spanish columns are set to 'AoWx Manual' (German was 'www.take2.de/aow').  The
    Original key is left alone (mld-localisation rule: never edit Original); with the DFM text changed the lookup
    simply misses and the DFM text shows - the columns are filled as well so either path reads 'AoWx Manual'.

Byte-level revert (only our ranges / cells).  Backups <game>\backup\*.bak_helplink.
Dry-run default; --apply / --revert; --game DIR (scratch copies).
"""
import argparse, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
import dfm_edit
from bakpath import bak_path, game_dir
from aowxlib import mld

SUF = ".bak_helplink"
URL_OFF, URL_LEN = 0x26D0C, 28                       # "http://www.ageofwonders.com\0"
OLD_URL = b"http://www.ageofwonders.com\x00"
NEW_URL = b"https://aowx.org/".ljust(URL_LEN, b"\x00")
DFM_OFF, DFM_SIZE, ENTRY_OFF = 0x149A6C, 0x2CD3, 0x73070
OLD_ITEM = b"\x06\x14www.ageofwonders.com"
NEW_ITEM = b"\x06\x0bAoWx Manual"
MENUS = ("/PopupWindows/HelpMenu", "/PopupWindows/TCHelpMenu")
LABEL = b"AoWx Manual"
MLDS = ("Dict/AoW.mld", "Dict/AoWVan.MLD")
KEY = b"www.ageofwonders.com"
OLD_COLS = [b"", b"www.take2.de/aow", KEY, KEY, KEY]   # English, German, French, Italian, Spanish (stock)


def exe_state(d):
    url = d[URL_OFF:URL_OFF + URL_LEN]
    size = struct.unpack_from("<I", d, ENTRY_OFF + 4)[0]
    us = "vanilla" if url == OLD_URL else "ours" if url == NEW_URL else "UNKNOWN"
    if size == DFM_SIZE and d[DFM_OFF:DFM_OFF + size].count(OLD_ITEM) == 2:
        ds = "vanilla"
    elif size == DFM_SIZE - 18 and d[DFM_OFF:DFM_OFF + size].count(NEW_ITEM) == 2 \
            and not any(d[DFM_OFF + size:DFM_OFF + DFM_SIZE]):
        ds = "ours"
    else:
        ds = "UNKNOWN"
    return us, ds, size


def new_dfm(old):
    w = dfm_edit.walk(old)
    assert w.consumed == len(old)
    spans = []
    for m in MENUS:
        hits = [p for p in w.props if p[0] == m and p[1] == "Items.Strings" and p[2] == dfm_edit.LIST]
        assert len(hits) == 1 and hits[0][5][2] == "www.ageofwonders.com", (m, hits)
        seg = old[hits[0][3]:hits[0][4]]
        i = seg.index(OLD_ITEM)
        spans.append(hits[0][3] + i)
    out = bytearray(old)
    for s in sorted(spans, reverse=True):
        out[s:s + len(OLD_ITEM)] = NEW_ITEM
    out = bytes(out)
    w2 = dfm_edit.walk(out)
    assert w2.consumed == len(out)
    for m in MENUS:
        v = [p for p in w2.props if p[0] == m and p[1] == "Items.Strings" and p[2] == dfm_edit.LIST][0][5]
        assert v == ["General Interface", "Map Interface", "AoWx Manual"], v
    return out


def mld_rows(m):
    return [r for r in m.records if r.Original == KEY and r.ClassName == b"TPopupWindows"
            and r.ComponentName in (b"HelpMenu", b"TCHelpMenu")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--game", default=game_dir())
    a = ap.parse_args()
    exe = os.path.join(a.game, "AoWx.exe")
    d = bytearray(open(exe, "rb").read())
    us, ds, size = exe_state(d)
    print("AoWx.exe  URL @file 0x%X: %s | TPOPUPWINDOWS DFM (size 0x%X): %s" % (URL_OFF, us, size, ds))
    assert "UNKNOWN" not in (us, ds), "unexpected AoWx.exe state - refusing"
    mstates = []
    for rel in MLDS:
        p = os.path.join(a.game, rel)
        m = mld.MLDFile.load(p)
        rows = mld_rows(m)
        assert len(rows) == 2, (rel, len(rows))
        cols = [list(r.translations) for r in rows]
        st = "vanilla" if all(c == OLD_COLS for c in cols) else \
             "ours" if all(c == [LABEL] * 5 for c in cols) else "UNKNOWN"
        print("%-16s rows HelpMenu/TCHelpMenu: %s" % (rel, st))
        assert st != "UNKNOWN", "unexpected %s cells - refusing" % rel
        mstates.append((p, m, rows, st))

    if a.revert:
        if us == "ours":
            d[URL_OFF:URL_OFF + URL_LEN] = OLD_URL
        if ds == "ours":
            bak = bak_path(exe, SUF, create=False)
            b = open(bak, "rb").read()
            assert exe_state(b)[1] == "vanilla", "backup DFM not vanilla"
            d[DFM_OFF:DFM_OFF + DFM_SIZE] = b[DFM_OFF:DFM_OFF + DFM_SIZE]
            struct.pack_into("<I", d, ENTRY_OFF + 4, DFM_SIZE)
        with open(exe, "r+b") as f:
            f.seek(0); f.write(d)
        for p, m, rows, st in mstates:
            if st == "ours":
                for r in rows:
                    r.translations = list(OLD_COLS)
                with open(p, "r+b") as f:
                    f.seek(0); f.write(m.dump()); f.truncate()
        print("reverted"); return 0

    if us == "ours" and ds == "ours" and all(s[3] == "ours" for s in mstates):
        print("already applied"); return 0
    nd = new_dfm(bytes(d[DFM_OFF:DFM_OFF + size])) if ds == "vanilla" else None
    if not a.apply:
        print("dry run OK (DFM 0x%X -> 0x%X bytes) - rerun with --apply" % (DFM_SIZE, DFM_SIZE - 18)); return 0

    if not os.path.exists(bak_path(exe, SUF, create=False)):
        shutil.copyfile(exe, bak_path(exe, SUF)); print("backup ->", bak_path(exe, SUF))
    if us == "vanilla":
        d[URL_OFF:URL_OFF + URL_LEN] = NEW_URL
    if nd is not None:
        d[DFM_OFF:DFM_OFF + DFM_SIZE] = nd + b"\x00" * (DFM_SIZE - len(nd))
        struct.pack_into("<I", d, ENTRY_OFF + 4, len(nd))
    with open(exe, "r+b") as f:
        f.seek(0); f.write(d)
    assert exe_state(open(exe, "rb").read())[:2] == ("ours", "ours")
    for p, m, rows, st in mstates:
        if st == "vanilla":
            if not os.path.exists(bak_path(p, SUF, create=False)):
                shutil.copyfile(p, bak_path(p, SUF))
            for r in rows:
                r.translations = [LABEL] * 5
            with open(p, "r+b") as f:
                f.seek(0); f.write(m.dump()); f.truncate()
    print("applied: Help menu item -> 'AoWx Manual', opens https://aowx.org/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
