"""
patch_replace_italian_russian.py - make the Italian language slot into Russian.

The engine hard-caps at 6 language columns (Native/English/German/French/
Italian/Spanish); a true 7th slot corrupts the heap (see the 7th-language
investigation). So Russian REPLACES Italian, which lives at dictionary column 4
and is reached by AoWSetup dropdown index 5 -> SetLanguage(4). Index 4 is inside
the engine's 6-slot range, exactly like every shipped language, so it cannot
trigger the overflow. No language-count binary patches are needed.

What this does:
  * AoWSetup.exe   - rename the LanguageCB dropdown item "Italian" -> "Russian"
                     (same length, in place); and neutralise the Multilizer
                     locale/codepage validation raises (4 sites) so declaring
                     the slot CodePage 1251 does not pop an error dialog.
  * Localize.dpl   - the same 4 validation raises in the copy the game/engine
                     use via the IvDictio imports.
  * Dict\\*.mld     - retag language[4]: EnglishName "Russian", NativeName
                     "Русский" (aowx-ru bytes), ISO ru/RU, Primary 0x19,
                     CodePage 1251 (so AoWxInk edits it as Cyrillic). Empty the
                     old Italian cells (they fall back to English until
                     translated), and seed the main-menu strings.

Cyrillic renders because the Int\\Fonts glyphs were painted at the aowx-ru byte
values; the CodePage only steers Multilizer's locale check (silenced) and
AoWxInk's editor codec. The game keeps strings as raw AnsiString bytes, so the
aowx-ru bytes reach the bitmap-font renderer unchanged.

    python patch_replace_italian_russian.py            dry run
    python patch_replace_italian_russian.py --apply    back up, then patch
    python patch_replace_italian_russian.py --revert    restore the backups
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DICT = os.path.join(GAME, "Dict")
BK_BIN = {"AoWSetup.exe": "AoWSetup.exe.bak_ruit",
          "Localize.dpl": "Localize.dpl.bak_ruit"}
BK_DICT = os.path.join(GAME, "backup", "Dict.bak_ruit")

for cand in (os.path.join(GAME, "modding tools"),):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from aowxlib.mld import MLDFile                                      # noqa: E402
from aowxlib.cyrillic import encode, AOWX_RU_CODEC                  # noqa: E402

ITALIAN_COL = 4                 # dictionary language index
ITALIAN_TR = ITALIAN_COL - 1    # translations[] index (skips Native)

# --- binary edits: (file, offset, expected_old, new) ------------------------
BIN_PATCHES = {
    "AoWSetup.exe": [
        (0x1092B1, b"Italian", b"Russian"),      # dropdown item (same length)
        (0x04B17E, b"\x75", b"\xEB"),            # validation raise A/system
        (0x04B1B5, b"\x75", b"\xEB"),            # A/codepage
        (0x04B315, b"\x0F\x85", b"\x90\xE9"),    # B/system (near jne -> nop;jmp)
        (0x04B36F, b"\x75", b"\xEB"),            # B/codepage
    ],
    "Localize.dpl": [
        (0x006A1A, b"\x75", b"\xEB"),
        (0x006A51, b"\x75", b"\xEB"),
        (0x006BB1, b"\x0F\x85", b"\x90\xE9"),
        (0x006C0B, b"\x75", b"\xEB"),
    ],
}

SEED = {
    b"Tutorial": "Обучение",
    b"Options": "Опции",
    b"Exit": "Выход",
    b"Continue": "Продолжить",
    b"Load Game": "Загрузить игру",
}


def patch_binaries(apply_it):
    ok = True
    for name, patches in BIN_PATCHES.items():
        path = os.path.join(GAME, name)
        d = bytearray(open(path, "rb").read())
        pending = done = 0
        for off, old, new in patches:
            cur = bytes(d[off:off + len(new)])
            if cur == new:
                done += 1
            elif cur == old:
                d[off:off + len(new)] = new
                pending += 1
            else:
                print("  %-13s 0x%06X MISMATCH: found %s (want %s/%s)"
                      % (name, off, cur.hex(), old.hex(), new.hex()))
                ok = False
        print("  %-13s %d edit(s) to write, %d already done" % (name, pending, done))
        if apply_it and ok and pending:
            bak = os.path.join(GAME, BK_BIN[name])
            if not os.path.isfile(bak):
                shutil.copy2(path, bak)
            with open(path, "wb") as fh:
                fh.write(d)
            print("      written (backup %s)" % BK_BIN[name])
    return ok


def patch_dicts(apply_it):
    if apply_it:
        os.makedirs(BK_DICT, exist_ok=True)
    ru_native = encode("Русский", AOWX_RU_CODEC)
    for f in sorted(os.listdir(DICT)):
        if not f.endswith(".mld"):
            continue
        path = os.path.join(DICT, f)
        m = MLDFile.load(path)
        if len(m.languages) != 6:
            print("  %-14s has %d languages (want 6) - skipped"
                  % (f, len(m.languages)))
            continue
        lang = m.languages[ITALIAN_COL]
        already = lang.EnglishName == b"Russian"
        cleared = sum(1 for r in m.records if r.translations[ITALIAN_TR])
        print("  %-14s retag Italian->Russian, clear %d cell(s)%s"
              % (f, cleared, " [already Russian]" if already else ""))
        if not apply_it:
            continue
        bak = os.path.join(BK_DICT, f)
        if not os.path.isfile(bak):
            shutil.copy2(path, bak)
        lang.EnglishName = b"Russian"
        lang.NativeName = ru_native
        lang.ISOLanguage = b"ru"
        lang.ISODefaultCountry = b"RU"
        lang.Primary = 0x19
        lang.DefaultSub = 1
        lang.CodePage = 1251
        for r in m.records:
            r.translations[ITALIAN_TR] = b""
        if f == "ResStr.mld":
            for r in m.records:
                if r.Original in SEED and r.ClassName == b"" and r.ComponentName == b"":
                    r.translations[ITALIAN_TR] = encode(SEED[r.Original], AOWX_RU_CODEC)
        m.save(path)
        chk = MLDFile.load(path)
        assert chk.languages[ITALIAN_COL].EnglishName == b"Russian"
        assert chk.languages[ITALIAN_COL].CodePage == 1251


def run(apply_it):
    print("Binaries:")
    ok = patch_binaries(apply_it)
    if not ok:
        print("\nBinary mismatch - not applying. Are they already patched by "
              "the 7th-language script? Revert that first.")
        return
    print("Dictionaries:")
    patch_dicts(apply_it)
    if not apply_it:
        print("\nDry run - use --apply.")
    else:
        print("\nDone. In AoWSetup pick 'Russian' (was Italian). It maps to the "
              "safe column 4, so no crash. Translate the rest in AoWxInk.")


def revert():
    for name, bak in BK_BIN.items():
        bp = os.path.join(GAME, bak)
        if os.path.isfile(bp):
            shutil.copy2(bp, os.path.join(GAME, name))
            print("  restored %s" % name)
    if os.path.isdir(BK_DICT):
        for f in os.listdir(BK_DICT):
            shutil.copy2(os.path.join(BK_DICT, f), os.path.join(DICT, f))
            print("  restored %s" % f)


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
