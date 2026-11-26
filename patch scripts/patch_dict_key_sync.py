"""patch_dict_key_sync.py - repair the two stale lookup keys in Release.mld.

The Dict records have no ID: the game looks up the runtime string against each
record's Original. AoWx renames things by filling the ENGLISH column and
leaving Original as the vanilla key - that is correct wherever the binary
still emits the vanilla string (verified 2026-08-26 for 31 of the 33
overrides: e.g. 'Dragon Slaying' is still AoWEPACK.dll's resourcestring).

Two Release.mld rows are the exception: their runtime text lives in
Release\\Ability.pfs / Spells.pfs, which AoWx EDITED, so the game emits the
new wording and the stale keys never match - the English override and the
refreshed foreign translations on those rows are unreachable:

  row 248  'Enhanced attack ability against dragonkind.'
        -> 'Enhanced attack ability against monstrous units.'   (pfs wording)
  row 352  \"Halves the target's mobility for the duration of combat.\"
        -> 'The target is marked as prey, making them easier to strike '
           '(-1 DEF, -1 RES).'                                  (pfs wording)

Only Original changes; all translation columns stay byte-identical.

Usage:  py patch_dict_key_sync.py            (dry run)
        py patch_dict_key_sync.py --apply
        py patch_dict_key_sync.py --revert
Backup: Dict\\Release.mld.bak_keysync
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
TARGET = os.path.join(GAME, "Dict", "Release.mld")
BACKUP = TARGET + ".bak_keysync"
sys.path.insert(0, os.path.join(GAME, "modding tools"))
from aowxlib.mld import MLDFile  # noqa: E402

FIXES = [
    (b"Enhanced attack ability against dragonkind.",
     b"Enhanced attack ability against monstrous units."),
    (b"Halves the target's mobility for the duration of combat.",
     b"The target is marked as prey, making them easier to strike "
     b"(-1 DEF, -1 RES)."),
]


def main():
    apply_ = "--apply" in sys.argv
    if "--revert" in sys.argv:
        if not os.path.exists(BACKUP):
            print("no backup found -", BACKUP)
            return 1
        open(TARGET, "wb").write(open(BACKUP, "rb").read())
        print("reverted from", BACKUP)
        return 0

    f = MLDFile.load(TARGET)
    hit = 0
    for r in f.records:
        for old, new in FIXES:
            if r.Original == old:
                assert not any(x.Original == new for x in f.records), \
                    "a record keyed %r already exists" % new
                print("%s row: %r\n%s        -> %r"
                      % ("would fix" if not apply_ else "fixing   ",
                         old.decode("cp1252"), "" , new.decode("cp1252")))
                r.Original = new
                hit += 1
    assert hit == len(FIXES), "expected %d rows, matched %d (already applied?)" \
        % (len(FIXES), hit)

    if not apply_:
        print("dry run - re-run with --apply")
        return 0
    if not os.path.exists(BACKUP):
        open(BACKUP, "wb").write(open(TARGET, "rb").read())
        print("backup ->", BACKUP)
    f.save(TARGET)
    # prove the write: reload and check both new keys resolve
    g = MLDFile.load(TARGET)
    for _, new in FIXES:
        assert any(r.Original == new for r in g.records), "post-check failed"
    assert not any(r.Original == old for r in g.records for old, _ in FIXES)
    print("applied + re-parse verified ->", TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
