#!/usr/bin/env python3
r"""build_citynames_vanilla.py  [--apply]

Compiles every city name of the vanilla (AoW 1.36) custom + campaign scenarios into  Dict\xCityNamesV.mld  - the
"Vanilla AoW" list of the editor's random city-name generator (user 2026-11-22).

Source: <game>\reference files\AoW 1.36\Scenario\{Custom,Campaign}\*.hsm / *.csm  (CFS + zlib maps).
City = hex child class 0x20108; tag 0x0C = name (ShortString), tag 0x0D = race (signed byte; tag absent = 0):
  0 Human 1 Azrac 2 Lizardman 3 Frostling 4 Elf 5 Halfling 6 Dwarf 7 Highman 8 Dark Elf 9 Orc 10 Goblin 11 Undead,
  negative = a random-race city (-1 plain random; -2..-4 the campaign's other random kinds) -> category "Random".
Left out: the placeholder "noname" (any case), "Catacombs" and empty names.  Duplicates inside a category are merged.

The file is an ordinary Multilizer dictionary (same header + language table as the stock Dict files, so MLDEdit /
AoWxInk open it):  one record per name,  Original = the name,  ClassName = the category ("Human" ... "Undead",
"Random"),  ComponentName empty, every translation column empty.  Records are sorted by category (race order, Random
last), then by name.  The editor reads Original + ClassName only.

Dry run prints the census; --apply writes the file (an existing one is backed up to backup\Dict\).
"""
import collections, glob, os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file
from aowxlib import mld as MLD

GAME = os.path.dirname(HERE)
SRC = os.path.join(GAME, "reference files", "AoW 1.36", "Scenario")
OUT = game_file(os.path.join("Dict", "xCityNamesV.mld"))
TEMPLATE = game_file(os.path.join("Dict", "CustMaps.mld"))
RACES = ["Human", "Azrac", "Lizardman", "Frostling", "Elf", "Halfling", "Dwarf", "Highman", "Dark Elf", "Orc", "Goblin", "Undead"]
CATS = RACES + ["Random"]
INFO_NAME = "City Names - Vanilla AoW"
CITY = 0x20108
EXCLUDE = {"noname", "catacombs"}      # placeholder; "Catacombs" = 40 cities of one map (Desolate Maugogom), removed at the user's request 11/22


def tbl(d, p):
    b = d[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from("<I", d, p)[0]; p += 4
    f = []
    for _ in range(b & 0x7F):
        f.append((d[p], d[p + 1])); p += 2
    for _ in range(nd):
        f.append(struct.unpack_from("<II", d, p)); p += 8
    return f, p


def fields(d, p, end):
    f, base = tbl(d, p)
    srt = sorted(f, key=lambda kv: kv[1])
    return {t: (base + o, base + srt[j + 1][1] if j + 1 < len(srt) else end) for j, (t, o) in enumerate(srt)}


def cities(path):
    raw = open(path, "rb").read()
    i = raw.find(b"CFS\x00")
    d = zlib.decompress(raw[i + 5:])
    root = fields(d, 0x13, len(d))
    cs, ce = sorted(fields(d, *root[1]).values())[0]
    cf = fields(d, cs + 4, ce)
    W, H = d[cf[3][0]], d[cf[4][0]]
    for ls, le in sorted(fields(d, *cf[1]).values()):
        lf = fields(d, ls + 4, le)
        q = lf[6][0] if 6 in lf else lf[1][0] + 2          # saves / newer maps keep the hex stream in tag 6
        for _ in range(W * H):
            L = struct.unpack_from("<I", d, q)[0]; s, e = q + 4, q + 4 + L; q = e
            try:
                kids = fields(d, s, e)
            except Exception:
                continue
            for t, (a, b) in kids.items():
                if b - a < 8 or struct.unpack_from("<I", d, a)[0] != CITY:
                    continue
                f = fields(d, a + 4, b)
                if 0xC not in f:
                    continue
                name = d[f[0xC][0] + 1:f[0xC][0] + 1 + d[f[0xC][0]]].decode("latin1")
                race = struct.unpack_from("b", d, f[0xD][0])[0] if 0xD in f else 0
                yield name, race


def collect():
    by = collections.OrderedDict((c, set()) for c in CATS)
    maps = total = skipped = 0
    for sub in ("Custom", "Campaign"):
        for p in sorted(glob.glob(os.path.join(SRC, sub, "*"))):
            if p.rsplit(".", 1)[-1].lower() not in ("hsm", "csm"):
                continue
            maps += 1
            for name, race in cities(p):
                total += 1
                nm = name.strip()
                if not nm or nm.lower() in EXCLUDE:
                    skipped += 1; continue
                assert race < len(RACES), (p, name, race)
                by["Random" if race < 0 else RACES[race]].add(nm)
    return by, maps, total, skipped


def build(by):
    tpl = MLD.MLDFile.load(TEMPLATE)
    out = MLD.MLDFile()
    out.Version, out.ByteOrder, out.CharacterSet, out.Context = tpl.Version, tpl.ByteOrder, tpl.CharacterSet, 1
    out.reserved1, out.reserved2 = tpl.reserved1, tpl.reserved2
    out.languages = tpl.languages
    nl = len(tpl.languages) - 1
    for cat in CATS:
        for nm in sorted(by[cat], key=lambda s: (s.lower(), s)):
            out.records.append(MLD.Record(nm.encode("cp1252"), cat.encode("cp1252"), b"", [b""] * nl))
    # Info block (MLDEdit never reads it): wstr Name, two empty wstr, date d/m/yyyy + time h:m:s
    w = MLD.BinWriter(); w.wstr(INFO_NAME.encode("cp1252")); w.wstr(b""); w.wstr(b"")
    w.u8(22); w.u8(11); w.u16(2026); w.u8(0); w.u8(0); w.u8(0)
    out.info = bytes(w.b)
    blob = out.dump()
    chk = MLD.MLDFile.parse(blob)                              # must read back identically
    assert [(x.Original, x.ClassName) for x in chk.records] == [(x.Original, x.ClassName) for x in out.records]
    assert not chk.stale_info_header and chk.dump() == blob
    return blob, out


def main():
    by, maps, total, skipped = collect()
    blob, out = build(by)
    print("%d maps, %d cities, %d skipped (excluded / empty) -> %d names" % (maps, total, skipped, len(out.records)))
    for c in CATS:
        print("  %-10s %4d" % (c, len(by[c])))
    print("languages:", out.lang_names(), "| file %d B" % len(blob))
    if "--apply" not in sys.argv:
        print("Dry run - rerun with --apply to write", OUT); return 0
    if os.path.exists(OUT):
        if open(OUT, "rb").read() == blob:
            print("already up to date"); return 0
        b = bak_path(OUT, ".bak_citynames")
        os.makedirs(os.path.dirname(b), exist_ok=True); shutil.copy2(OUT, b); print("backup ->", b)
    open(OUT, "wb").write(blob)
    print("written", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
