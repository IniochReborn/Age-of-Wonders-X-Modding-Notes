#!/usr/bin/env python3
r"""
Int\Fonts\Age15WhGr.ILB (FontModule.AoW15WhiteGrey): CONDENSED digits for the unit window's "100/100" (2026-10-18).

Channeler III gives a Spell Casting V hero 100 casting points; "100/100" in AoW15WhiteGrey is 59 px but the unit
window's Mana label sits in a 51 px panel.  v1 switched that label to Age10s (looked janky - a different font).
This script adds a condensed copy of the font's own digits + slash, so the label keeps the same font, colour,
height and shadow, just a little narrower:

    glyph   ids      source   width   columns removed (both layers)
    0..9    0x10..0x19   '0'..'9'   see DEL   interior blank columns ('0', '8') or the near-empty side-bearing column
    /       0x1A     '/'      7 -> 6  the top tip column

    "100/100": 59 px -> 48 px;  "99/100" 49 -> 41;  "50/50" unchanged (43, normal glyphs).

The glyph art is copied pixel for pixel (raw 565, lossless) - only whole columns are dropped, never resampled - so
the strokes stay crisp; each image keeps the template's two layers (part 0 = the bmShadow layer, drawMode 1026,
key 0xFFFF; part 1 = the glyph, drawMode 770 / blend 60, key 0), name, flags and 18 px cell.
Ids 0x10..0x1A are control bytes: never in game text, not special-cased by ImageLib.ParseFontText (only 0x0A / 0x0D /
0x20) nor by TAOWLabel.SetGText/Draw, and TImageLibraryFont's width = [image+0x20] (= w) + CharacterDistance (0),
so a label holding these bytes centres on the condensed width.  Only patch_exe_channeler_label_v2.py writes them.

ORDER: apply this BEFORE patch_exe_channeler_label_v2.py (that script refuses without these glyphs; without them the
bytes would draw as 5 px blanks).  Revert it AFTER reverting the label script.
Usage:  py -3.10 patch_font_age15_condensed_digits_v1.py [--apply | --revert] [--ilb PATH]   (dry-run by default)
Backup: backup\Int\Fonts\Age15WhGr.ILB.bak_cdigits  (--revert rebuilds without ids 0x10..0x1A and checks it equals the
backup byte for byte).  Ship Int\Fonts\Age15WhGr.ILB (release zip: --add it, it is a newly modified file).
"""
import argparse, copy, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_dir

FIRST_ID = 0x10
CHARS = "0123456789/"
IDS = {c: FIRST_ID + i for i, c in enumerate(CHARS)}          # '0'..'9' -> 0x10..0x19, '/' -> 0x1A
DEL = {'0': (4, 5), '1': (5,), '2': (0, 8), '3': (7,), '4': (0, 8), '5': (7,), '6': (7,), '7': (0, 8),
       '8': (3,), '9': (0,), '/': (6,)}
SRC_W = {'0': 10, '1': 6, '2': 9, '3': 8, '4': 9, '5': 8, '6': 8, '7': 9, '8': 7, '9': 8, '/': 7}
BAK = ".bak_cdigits"


def lib_mod():
    sys.path.insert(0, os.path.join(game_dir(), "modding tools"))
    from aowxlib import ilb
    return ilb


def condensed_records(ilb, lib, ch):
    """-> list of new Records (one per layer) for the condensed copy of glyph `ch`."""
    src = [i for i in lib.images if i.id == ord(ch)][0]
    assert src.composite and len(src.parts) == 2, "glyph %r: unexpected layer layout" % ch
    dl = set(DEL[ch])
    out = []
    for rec in src.parts:
        assert rec["type"] == 22 and rec["w"] == SRC_W[ch] and rec["h"] == 18, "glyph %r changed - refusing" % ch
        w, h, px = ilb.decode_record(lib, rec)
        rows = [[p for x, p in enumerate(row) if x not in dl] for row in px]
        nw = w - len(dl)
        key = rec["transp"]
        top = left = 10 ** 6; bottom = right = -1
        for y, row in enumerate(rows):
            for x, p in enumerate(row):
                if p[3]:
                    top, bottom, left, right = min(top, y), max(bottom, y), min(left, x), max(right, x)
        assert bottom >= 0, "glyph %r layer empty" % ch
        data = []
        for y in range(top, bottom + 1):
            line = []
            for x in range(left, right + 1):
                p = rows[y][x]
                if not p[3]:
                    line.append(key)
                else:
                    v = ilb.to_rgb565(p[0], p[1], p[2])
                    line.append(v ^ 1 if v == key else v)
            data.append(line)
        r = ilb.Record(copy.deepcopy(dict(rec)))
        r["w"] = r["totw"] = nw
        r["cx"], r["cy"], r["cw"], r["ch"] = left, top, right - left + 1, bottom - top + 1
        r["newdata"] = ilb.encode_raw16(data)
        r["size"] = len(r["newdata"])
        out.append(r)
    return src, out


def exe_v2_applied(exe):
    """True when AoWx.exe's .xtut zone 0x634400 carries the label v2 header 'CHL2'."""
    import struct
    if not os.path.exists(exe):
        return False
    d = open(exe, "rb").read()
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]; opt = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        h = e + 24 + opt + 40 * i
        if d[h:h + 8].rstrip(bytes(1)) == b".xtut":
            vs, va, rs, ro = struct.unpack_from("<IIII", d, h + 8)
            return rs > 0x400 and d[ro + 0x400:ro + 0x404] == b"CHL2"
    return False


def build(raw):
    """-> (state, patched_bytes, stripped_bytes)"""
    ilb = lib_mod()
    lib = ilb.read(raw)
    ours = set(IDS.values())
    base = copy.deepcopy(lib)
    base.images = [i for i in base.images if i.id not in ours]
    full = copy.deepcopy(base)
    for ch in CHARS:
        src, recs = condensed_records(ilb, full, ch)
        full.images.append(ilb.Image(IDS[ch], recs, composite=True))
    full.images.sort(key=lambda im: im.id)
    patched = ilb.write(full)
    stripped = ilb.write(base)
    present = [i.id for i in lib.images if i.id in ours]
    if not present:
        state = "VANILLA"
    elif bytes(raw) == patched:
        state = "APPLIED"
    else:
        state = "FOREIGN (ids %s present but differ)" % ", ".join("0x%02X" % i for i in present)
    return state, patched, stripped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ilb", default=os.path.join(game_dir(), "Int", "Fonts", "Age15WhGr.ILB"))
    ap.add_argument("--exe", default=os.path.join(game_dir(), "AoWx.exe"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    raw = open(a.ilb, "rb").read()
    state, patched, stripped = build(raw)
    print("%s: %s  (%d B; patched %d B)" % (a.ilb, state, len(raw), len(patched)))
    if state.startswith("FOREIGN"):
        print("ABORT"); return 1
    if a.revert:
        if state == "VANILLA":
            print("nothing to revert"); return 0
        if exe_v2_applied(a.exe):
            print("ABORT: %s still has patch_exe_channeler_label_v2 - revert that first" % a.exe); return 1
        bak = bak_path(a.ilb, BAK, create=False)
        if os.path.exists(bak) and open(bak, "rb").read() != stripped:
            print("ABORT: rebuilt file differs from the backup %s" % bak); return 1
        open(a.ilb, "wb").write(stripped)
        assert open(a.ilb, "rb").read() == stripped
        print("reverted (ids 0x%02X..0x%02X removed)" % (FIRST_ID, FIRST_ID + len(CHARS) - 1)); return 0
    if state == "APPLIED":
        print("already applied"); return 0
    assert stripped == bytes(raw), "round-trip without our ids is not byte-identical - refusing"
    if not a.apply:
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.ilb, BAK)
    if not os.path.exists(bak):
        shutil.copy2(a.ilb, bak); print("backup ->", bak)
    open(a.ilb, "wb").write(patched)
    assert open(a.ilb, "rb").read() == patched
    print("applied: condensed 0-9 + '/' at ids 0x%02X..0x%02X" % (FIRST_ID, FIRST_ID + len(CHARS) - 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
