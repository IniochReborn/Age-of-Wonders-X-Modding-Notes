"""
test_cyrillic_ingame.py - temporary in-game smoke test for the Cyrillic glyphs.

patch_fonts_cyrillic.py painted 66 Cyrillic glyphs into the Int\\Fonts ILBs at
the aowx-ru byte assignments. The one thing static verification cannot prove is
the engine actually drawing those byte values. This script borrows the exact
mechanism AoWx uses for renames - the English override column in the
dictionaries - to relabel two main-menu items:

    Options   ->  "Опции"       (bytes 0x90 0xBE 0xCE 0xB3 0xB3)
    Tutorial  ->  "Абвгдеёжз"   (bytes 0x80 0xAB..0xB2 - the low range)

Launch the game with language = English and look at the main menu. If both
labels show Cyrillic, the whole pipeline works: byte -> glyph id -> new frame.
If they show blanks or garbage, note which letters fail (low range vs high).

    python test_cyrillic_ingame.py            dry run
    python test_cyrillic_ingame.py --apply    back up ResStr.mld, set the labels
    python test_cyrillic_ingame.py --revert   restore the backup

Remember to --revert afterwards - this is a diagnostic, not a feature.
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DICT = os.path.join(GAME, "Dict")
BACKUP = os.path.join(GAME, "backup", "Dict.bak_cyrtest")

for cand in (os.path.join(GAME, "modding tools"),):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from aowxlib.mld import MLDFile                                      # noqa: E402
from aowxlib.cyrillic import encode, AOWX_RU_CODEC                   # noqa: E402

TESTS = {
    b"Options": "Опции",
    b"Tutorial": "Абвгдеёжз",
}


def run(apply_it):
    path = os.path.join(DICT, "ResStr.mld")
    m = MLDFile.load(path)
    hits = 0
    for r in m.records:
        if r.Original in TESTS and r.ClassName == b"" and r.ComponentName == b"":
            text = TESTS[r.Original]
            data = encode(text, AOWX_RU_CODEC)
            print("  %-10s English col %r -> %s  (%s)"
                  % (r.Original.decode(), r.translations[0], text,
                     " ".join("%02X" % b for b in data)))
            if apply_it:
                r.translations[0] = data
            hits += 1
    if hits != len(TESTS):
        print("Expected %d records, matched %d - aborting." % (len(TESTS), hits))
        sys.exit(1)
    if not apply_it:
        print("Dry run - nothing written. Use --apply to set the test labels.")
        return
    os.makedirs(BACKUP, exist_ok=True)
    dst = os.path.join(BACKUP, "ResStr.mld")
    if not os.path.isfile(dst):
        shutil.copy2(path, dst)
    m.save(path)
    MLDFile.load(path)                       # prove it still parses
    print("Applied. Launch the game (language: English) and check the main menu.")
    print("Then run  python test_cyrillic_ingame.py --revert")


def revert():
    src = os.path.join(BACKUP, "ResStr.mld")
    if not os.path.isfile(src):
        print("No backup at %s - nothing to revert." % src)
        sys.exit(1)
    shutil.copy2(src, os.path.join(DICT, "ResStr.mld"))
    print("ResStr.mld restored.")


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
