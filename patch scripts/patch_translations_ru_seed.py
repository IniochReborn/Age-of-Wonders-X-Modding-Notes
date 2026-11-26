"""
patch_translations_ru_seed.py - first Russian strings for the main menu.

Seeds the new Russian column (added by patch_dict_russian.py) with a handful
of high-visibility resourcestrings so switching to Russian shows Cyrillic
immediately. Everything else falls back to English until translated (the
long-tail translation work belongs to AoWxInk).

Text is stored in the aowx-ru byte mapping - the same bytes the font glyphs
were painted at.

    python patch_translations_ru_seed.py            dry run
    python patch_translations_ru_seed.py --apply    back up ResStr.mld, seed
    python patch_translations_ru_seed.py --revert   restore the backup
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DICT = os.path.join(GAME, "Dict")
BACKUP = os.path.join(GAME, "backup", "Dict.bak_ruseed")

for cand in (os.path.join(GAME, "modding tools"),):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from aowxlib.mld import MLDFile                                      # noqa: E402
from aowxlib.cyrillic import encode, AOWX_RU_CODEC                   # noqa: E402

SEED = {
    b"Tutorial": "Обучение",
    b"Options": "Опции",
    b"Exit": "Выход",
    b"Continue": "Продолжить",
    b"Load Game": "Загрузить игру",
}


def run(apply_it):
    path = os.path.join(DICT, "ResStr.mld")
    m = MLDFile.load(path)
    isos = [l.ISOLanguage for l in m.languages]
    if b"ru" not in isos:
        print("ResStr.mld has no Russian column - run patch_dict_russian.py first.")
        sys.exit(1)
    ru = isos.index(b"ru") - 1                   # translations[] skips Native
    hits = 0
    for r in m.records:
        if r.Original in SEED and r.ClassName == b"" and r.ComponentName == b"":
            text = SEED[r.Original]
            data = encode(text, AOWX_RU_CODEC)
            state = "set" if not r.translations[ru] else "OVERWRITE"
            print("  %-12s ru col %s -> %s (%s)"
                  % (r.Original.decode(), state, text,
                     " ".join("%02X" % b for b in data)))
            if apply_it:
                r.translations[ru] = data
            hits += 1
    print("%d of %d strings matched." % (hits, len(SEED)))
    if not apply_it:
        print("Dry run - use --apply.")
        return
    os.makedirs(BACKUP, exist_ok=True)
    dst = os.path.join(BACKUP, "ResStr.mld")
    if not os.path.isfile(dst):
        shutil.copy2(path, dst)
    m.save(path)
    MLDFile.load(path)
    print("Applied.")


def revert():
    src = os.path.join(BACKUP, "ResStr.mld")
    if not os.path.isfile(src):
        print("No backup at %s" % src)
        sys.exit(1)
    shutil.copy2(src, os.path.join(DICT, "ResStr.mld"))
    print("ResStr.mld restored.")


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
