#!/usr/bin/env python3
r"""
Release\easteregg.pfs builder / dumper (2026-10-19).  User: "show random flavour text on the title screen, bottom-left,
same font as the game version; display one of those texts at random, including the quotation marks" + "store them as
normal PFS string records in Release\easteregg.pfs, extensible for other easter-egg data later".

Source : <game>\reference files\title screen fflavor text.txt  (UTF-8, quotes separated by blank lines)
Output : <game>\Release\easteregg.pfs  - game .pfs framing + CRC; one record per quote, key = (1 << 16) | n,
         type 1 = title quote, text in tag 2.  Layout + CLI: modding tools\aowxlib\eastereggpfs.py.
         Read by AoWx.exe (patch_exe_title_quotes_v1.py) on every entry to the title screen.

Character mapping (the Age8s glyph font has printable ASCII except ` } ~ plus a few accented letters):
  BOM removed; line breaks inside a quote -> one space; curly double quotes -> straight ";  when a quote already starts
  with a straight " a NESTED curly pair becomes single quotes '...'; curly single quotes -> '; en/em dash -> -;
  ellipsis char -> ...; anything else non-ASCII -> its ASCII base letter (NFKD) or dropped.  > 480 chars -> cut.

Dry-run default (prints the quotes); --apply writes the pfs (an existing file is backed up once to
backup\Release\easteregg.pfs.bak); --dump [out.txt] prints/writes the live file back as text.
Other easter-egg types are preserved: --apply only replaces the type-1 records.
"""
import argparse, os, shutil, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import game_dir, bak_path

GAME = game_dir()
SRC = os.path.join(GAME, "reference files", "title screen fflavor text.txt")
DST = os.path.join(GAME, "Release", "easteregg.pfs")
sys.path.insert(0, os.environ.get("AOWX_MODTOOLS") or os.path.join(GAME, "modding tools"))
MAXQ = 480
BAD = set("`}~")


def norm(block):
    s = block.replace("﻿", "").replace("\r", "")
    s = " ".join(l.strip() for l in s.split("\n") if l.strip())
    outer_straight = s.startswith('"')
    out = []
    for c in s:
        if c in "“”„«»":
            out.append("'" if outer_straight else '"')
        elif c in "‘’‚′":
            out.append("'")
        elif c in "–—−":
            out.append("-")
        elif c == "…":
            out.append("...")
        elif ord(c) < 128:
            out.append(c if c not in BAD else "")
        else:
            b = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode()
            out.append(b)
    s = "".join(out)
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()[:MAXQ]


def build(src=SRC):
    t = open(src, encoding="utf-8-sig").read().replace("\r\n", "\n")
    blocks = [b for b in t.split("\n\n") if b.strip()]
    return [q for q in (norm(b) for b in blocks) if q]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--dst", default=DST)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dump", nargs="?", const="-")
    a = ap.parse_args()
    from aowxlib import eastereggpfs as E
    if a.dump:
        txt = E.dump_text(E.read(open(a.dst, "rb").read()))
        if a.dump == "-": sys.stdout.write(txt)
        else: open(a.dump, "w", encoding="latin-1", newline="").write(txt); print("dumped ->", a.dump)
        return 0
    qs = build(a.src)
    for i, q in enumerate(qs):
        print("%2d (%3d) %s" % (i, len(q), q))
    others = []
    if os.path.exists(a.dst):
        others = [(t, x) for t, _i, x in E.read(open(a.dst, "rb").read()) if t != E.T_TITLE_QUOTE]
    data = E.write([(E.T_TITLE_QUOTE, q) for q in qs] + others)
    assert [x for t, _i, x in E.read(data) if t == E.T_TITLE_QUOTE] == qs
    print("%d quotes (+%d other records), longest %d chars, %d bytes -> %s"
          % (len(qs), len(others), max(map(len, qs)), len(data), a.dst))
    if not a.apply:
        print("Dry run - rerun with --apply to write."); return 0
    if os.path.exists(a.dst):
        if open(a.dst, "rb").read() == data:
            print("already up to date"); return 0
        if os.path.abspath(a.dst) == os.path.abspath(DST):
            b = bak_path(a.dst, ".bak")
            if not os.path.exists(b):
                os.makedirs(os.path.dirname(b), exist_ok=True); shutil.copy2(a.dst, b); print("backup ->", b)
    open(a.dst, "wb").write(data)
    print("written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
