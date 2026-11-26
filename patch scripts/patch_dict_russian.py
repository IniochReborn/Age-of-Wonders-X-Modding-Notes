"""
patch_dict_russian.py - add a Russian language column to all eight dictionaries.

Adds a 7th TLanguageData entry (index 6: Primary 0x19, ISO ru/RU, CodePage 1251
= the aowx-ru byte mapping, charset RUSSIAN_CHARSET) to every Dict\\*.mld and
appends an empty translation cell to each record. Empty cells fall back to the
Original English text at runtime, so selecting Russian before any translation
exists simply shows English - the correct staging behavior.

Modeled field-for-field on the stock entries; written with aowxlib.mld, which
rewrites offsets and the language table correctly (unlike MLDEdit).

This must be applied BEFORE patch_language_russian.py's binaries are exercised:
the game's new case calls TIvDictionary.SetLanguage(6), which needs language
index 6 to exist. (Columns without the binary patch are harmless.)

    python patch_dict_russian.py            dry run
    python patch_dict_russian.py --apply    back up Dict, add the columns
    python patch_dict_russian.py --revert   restore the backup
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DICT = os.path.join(GAME, "Dict")
BACKUP = os.path.join(GAME, "backup", "Dict.bak_ru7")

for cand in (os.path.join(GAME, "modding tools"),):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from aowxlib.mld import MLDFile, Language                            # noqa: E402

NAMES = ["AoW", "AoWEd", "AoWSetup", "Campaign", "CampMaps",
         "CustMaps", "Release", "ResStr"]
RUSSIAN_CHARSET = 204


def make_russian(model):
    """Build the Russian entry, copying structural fields from `model`
    (the German entry) so wstr shapes match the stock convention."""
    return Language(
        Primary=0x19, ISOLanguage=b"ru", DefaultSub=1, ISODefaultCountry=b"RU",
        AllSubs=model.AllSubs, ISOAllCountries=model.ISOAllCountries,
        CharacterSet=RUSSIAN_CHARSET, CodePage=1251, Options=model.Options,
        EnglishName=b"Russian", NativeName=b"Russian",
        FontName=model.FontName, FontSize=model.FontSize)


def run(apply_it):
    total = 0
    for name in NAMES:
        path = os.path.join(DICT, name + ".mld")
        m = MLDFile.load(path)
        isos = [l.ISOLanguage for l in m.languages]
        if b"ru" in isos:
            print("  %-10s already has Russian (%d languages)"
                  % (name, len(m.languages)))
            continue
        if len(m.languages) != 6:
            print("  %-10s unexpected language count %d - skipped, needs a look"
                  % (name, len(m.languages)))
            continue
        german = m.languages[2]
        print("  %-10s add Russian as language 6 (%d records get a new cell)"
              % (name, len(m.records)))
        total += 1
        if apply_it:
            m.languages.append(make_russian(german))
            for r in m.records:
                r.translations.append(b"")
            os.makedirs(BACKUP, exist_ok=True)
            dst = os.path.join(BACKUP, name + ".mld")
            if not os.path.isfile(dst):
                shutil.copy2(path, dst)
            m.save(path)
            chk = MLDFile.load(path)             # prove it still parses
            assert len(chk.languages) == 7 and chk.languages[6].ISOLanguage == b"ru"
            assert all(len(r.translations) == 6 for r in chk.records)
    if not apply_it and total:
        print("\nDry run - nothing written. Use --apply.")
    elif apply_it:
        print("\nDone. Backups in %s" % BACKUP)


def revert():
    if not os.path.isdir(BACKUP):
        print("No backup at %s" % BACKUP)
        sys.exit(1)
    for fn in os.listdir(BACKUP):
        shutil.copy2(os.path.join(BACKUP, fn), os.path.join(DICT, fn))
        print("  restored %s" % fn)


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
