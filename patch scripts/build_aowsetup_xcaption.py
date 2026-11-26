#!/usr/bin/env python3
r"""AoWSetup.exe: retitle the Settings window to "Age of Wonders X".

The Settings UI lives inside TLoaderForm (the main borderless splash form) —
opening Settings shows a captioned window whose title comes from LoaderForm's
DFM Caption property, still "Age of Wonders". DFM strings are inline
length-prefixed, so growing the caption by 2 bytes ("Age of Wonders" ->
"Age of Wonders X") would shift the whole resource. To keep the RCDATA
resource size (and everything outside it, notably the background BMP at
0x7eda3 used by build_aowsetup_logo.py) byte-identical, the dead CD-check
message a few hundred bytes later in the SAME form is shortened by the same
2 bytes:

  0x7e7f1: Caption len 0x0e "Age of Wonders"      -> 0x10 "Age of Wonders X"
  0x7ec68: Caption len 0x24 "Please insert the Age of Wonders CD."
                                                  -> 0x22 "Insert the Age of Wonders game CD."

Only the bytes BETWEEN the two edits shift (+2); total file size is unchanged
and nothing at or after 0x7ec8d moves.

Usage:
    python build_aowsetup_xcaption.py            # dry run
    python build_aowsetup_xcaption.py --apply    # back up + patch
    python build_aowsetup_xcaption.py --revert   # restore backup
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_xcaption"

CAP_LEN_OFF = 0x7e7f1          # length byte of LoaderForm.Caption
OLD_CAP = b"Age of Wonders"
NEW_CAP = b"Age of Wonders X"

CD_LEN_OFF = 0x7ec68           # length byte of the CD-check message caption
OLD_CD = b"Please insert the Age of Wonders CD."
NEW_CD = b"Insert the Age of Wonders game CD."


def build(d):
    assert d[CAP_LEN_OFF - 1] == 0x06, "vaString marker missing before caption"
    assert d[CAP_LEN_OFF] == len(OLD_CAP), "caption length byte mismatch"
    cap_txt = CAP_LEN_OFF + 1
    assert d[cap_txt:cap_txt + len(OLD_CAP)] == OLD_CAP, "caption text mismatch"

    assert d[CD_LEN_OFF - 1] == 0x06, "vaString marker missing before CD msg"
    assert d[CD_LEN_OFF] == len(OLD_CD), "CD message length byte mismatch"
    cd_txt = CD_LEN_OFF + 1
    assert d[cd_txt:cd_txt + len(OLD_CD)] == OLD_CD, "CD message text mismatch"

    grow = len(NEW_CAP) - len(OLD_CAP)
    assert grow == len(OLD_CD) - len(NEW_CD), "edits do not compensate"

    new = (d[:CAP_LEN_OFF]
           + bytes([len(NEW_CAP)]) + NEW_CAP
           + d[cap_txt + len(OLD_CAP):CD_LEN_OFF]
           + bytes([len(NEW_CD)]) + NEW_CD
           + d[cd_txt + len(OLD_CD):])
    assert len(new) == len(d), "size changed"
    return new


def main():
    mode = "--apply" if "--apply" in sys.argv else "--revert" if "--revert" in sys.argv else "dry"

    if mode == "--revert":
        if not os.path.isfile(BAK):
            print(f"!! no backup at {BAK}")
            return 1
        shutil.copy2(BAK, EXE)
        print(f"REVERTED {EXE} from {os.path.basename(BAK)}")
        return 0

    d = open(EXE, "rb").read()
    if bytes([len(NEW_CAP)]) + NEW_CAP == d[CAP_LEN_OFF:CAP_LEN_OFF + 1 + len(NEW_CAP)]:
        print("already patched — Settings window caption is 'Age of Wonders X'")
        return 0

    new = build(d)
    print(f"caption  @{hex(CAP_LEN_OFF)}: '{OLD_CAP.decode()}' -> '{NEW_CAP.decode()}'")
    print(f"CD  msg  @{hex(CD_LEN_OFF)}: '{OLD_CD.decode()}' -> '{NEW_CD.decode()}'")
    print(f"shifted region: {hex(CAP_LEN_OFF + 1 + len(NEW_CAP))}..{hex(CD_LEN_OFF)} (+2 bytes), file size unchanged")

    if mode == "dry":
        print("\nDRY RUN — rerun with --apply to patch")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print(f"backed up -> {os.path.basename(BAK)}")
    open(EXE, "wb").write(new)
    print(f"WROTE {EXE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
