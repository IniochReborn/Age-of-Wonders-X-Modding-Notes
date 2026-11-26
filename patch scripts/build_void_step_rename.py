#!/usr/bin/env python3
r"""Rename spell 0xCA "Warp Self" -> "Void Step" (same 9-char length).

The name is a Delphi string literal inside the stage-1 registration cave in
AoWEPACK.dll (@VA 0x55810A60, [refcnt -1][len 9][bytes][NUL]); equal length =
in-place byte swap. The pfs record has no name field (description is
user-managed in the editor).

Backup: AoWEPACK.dll.bak_voidstep. Dry-run default; --apply / --revert.
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_voidstep"
OLD, NEW = b"Warp Self", b"Void Step"


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1
    d = bytearray(open(DLL, 'rb').read())
    if d.count(NEW) == 1 and d.count(OLD) == 0:
        print("already applied"); return 0
    assert d.count(OLD) == 1, d.count(OLD)
    off = d.find(OLD)
    assert len(OLD) == len(NEW)
    d[off:off+len(OLD)] = NEW
    print("renamed at file 0x%X (VA 0x%X)" % (off, off + 0x55700C00))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
