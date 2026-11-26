"""
patch_mld_repair.py - repair the language tables MLDEdit corrupted.

MLDEdit's writer (VA 0x468E87) has two bugs: it never writes the `Primary`
field, and it writes `ISODefaultCountry` twice overlapping. The two size errors
cancel out, so the file still parses and the damage is silent and cumulative.
Six of the eight shipped dictionaries have been through it.

Why it matters: picking a language explicitly in AoWSetup is index-based and
works regardless. But "Auto" asks Multilizer to match the Windows locale
against Primary/DefaultSub, which is impossible once those fields are garbage -
so a German player who leaves the setting on Auto gets English.

This does NOT guess. It copies the canonical language table verbatim from the
stock AoW 1.36 dictionaries under `reference files`, which are untouched, and
asserts that every one of the 6683 records is bit-identical afterwards.

    python patch_mld_repair.py            dry run
    python patch_mld_repair.py --apply    repair, after backing up
    python patch_mld_repair.py --revert   restore
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DICT = os.path.join(GAME, "Dict")
STOCK = os.path.join(GAME, "reference files", "AoW 1.36", "Dict")
BACKUP = os.path.join(GAME, "backup", "Dict.bak_langrepair")

for cand in (os.path.join(GAME, "modding tools", "aowxlib"),
             os.path.join(GAME, "old modding tools", "research")):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from mld import MLDFile                                              # noqa: E402

NAMES = ["AoW", "AoWEd", "AoWSetup", "Campaign", "CampMaps",
         "CustMaps", "Release", "ResStr"]
FIELDS = ("Primary", "ISOLanguage", "DefaultSub", "ISODefaultCountry",
          "AllSubs", "ISOAllCountries", "CharacterSet", "CodePage",
          "Options", "EnglishName", "NativeName", "FontName", "FontSize")


def show(v):
    if isinstance(v, (bytes, bytearray)):
        return v.decode("latin-1", "replace")
    return v


def run(apply_it):
    total = 0
    for name in NAMES:
        live_p = os.path.join(DICT, name + ".mld")
        stock_p = os.path.join(STOCK, name + ".mld")
        if not os.path.isfile(stock_p):
            print("  %-10s no stock reference - skipped" % name)
            continue
        live = MLDFile.load(live_p)
        stock = MLDFile.load(stock_p)
        if len(live.languages) != len(stock.languages):
            print("  %-10s language COUNT differs (%d vs %d) - skipped, needs a look"
                  % (name, len(live.languages), len(stock.languages)))
            continue
        diffs = []
        for i, (a, b) in enumerate(zip(live.languages, stock.languages)):
            for f in FIELDS:
                if getattr(a, f, None) != getattr(b, f, None):
                    diffs.append((i, f, show(getattr(a, f, None)), show(getattr(b, f, None))))
        if not diffs:
            print("  %-10s already clean" % name)
            continue
        print("  %-10s %d field(s) to restore" % (name, len(diffs)))
        for i, f, got, want in diffs[:6]:
            print("        lang[%d].%-18s %r -> %r" % (i, f, got, want))
        if len(diffs) > 6:
            print("        ... and %d more" % (len(diffs) - 6))
        total += len(diffs)

        if apply_it:
            before_records = [(r.Original, r.ClassName, r.ComponentName,
                               list(r.translations)) for r in live.records]
            for a, b in zip(live.languages, stock.languages):
                for f in FIELDS:
                    if hasattr(b, f):
                        setattr(a, f, getattr(b, f))
            live.save(live_p)
            after = MLDFile.load(live_p)
            assert len(after.records) == len(before_records), name + ": record count changed"
            for i, r in enumerate(after.records):
                o, c, cm, tr = before_records[i]
                assert r.Original == o and r.ClassName == c and r.ComponentName == cm, \
                    "%s#%d key changed" % (name, i)
                assert list(r.translations) == tr, "%s#%d text changed" % (name, i)
            for a, b in zip(after.languages, stock.languages):
                for f in FIELDS:
                    if hasattr(b, f):
                        assert getattr(a, f) == getattr(b, f), name + ": " + f + " not restored"
            print("        repaired; all %d records verified bit-identical" % len(after.records))
    print("\n%d field(s) %s" % (total, "restored" if apply_it else "would be restored"))


def backup():
    if os.path.isdir(BACKUP):
        print("backup already exists: %s" % BACKUP)
        return
    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    shutil.copytree(DICT, BACKUP)
    print("backed up Dict -> %s" % BACKUP)


def revert():
    if not os.path.isdir(BACKUP):
        sys.exit("no backup at %s" % BACKUP)
    for f in os.listdir(BACKUP):
        shutil.copy2(os.path.join(BACKUP, f), os.path.join(DICT, f))
    print("restored %d file(s)" % len(os.listdir(BACKUP)))


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    elif "--apply" in sys.argv:
        backup()
        run(True)
    else:
        print("DRY RUN - nothing written. Use --apply.\n")
        run(False)
