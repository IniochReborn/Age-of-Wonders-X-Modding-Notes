#!/usr/bin/env python3
r"""
AoW.exe launcher: drop the obsolete "Scroll of Slickness" helper (2026-09-21).

AoW.exe in the game root is NOT the game: it is a compiled AutoHotkey v1.1.37 launcher (710656 B) whose script
(RCDATA ">AUTOHOTKEY SCRIPT<", 204 B, stored in plain text @file 0xACEF8) ran the old mouse-hotkey helper
"AoWx - Scroll of Slickness.exe" and then AoWx.exe, waited for the game and killed the helper.  The helper was
retired when wheel scrolling went native (mouse-wheel-scrolling), so AutoHotkey's Run now fails ("Failed attempt
to launch program") and AoW.exe looks like a crash.  AoWSetup's install check / Start button still target aow.exe,
so the file must stay and must launch the game.
Patch: rewrite the script in place (same length, space-padded) to just `Run AoWx.exe` from the launcher's folder
and exit.  Backup AoW.exe.bak_launcher (in <game>\backup\).  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, sys
from bakpath import game_dir, game_file, bak_path

DEFAULT_EXE = game_file(r"AoW.exe")
BAK = ".bak_launcher"
RES_OFF, RES_SIZE = 0xACEF8, 204
ORIG = (b'; <COMPILER: v1.1.37.02>\nRun, "%A_ScriptDir%\\AoWx - Scroll of Slickness.exe",, , ahkScriptPID\n'
        b'Run, "%A_ScriptDir%\\AoWx.exe",, , gamePID\nProcess, WaitClose, %gamePID%\nProcess, Close, %ahkScriptPID%\nExitApp')
NEW_SCRIPT = b'; <COMPILER: v1.1.37.02>\nRun, "%A_ScriptDir%\\AoWx.exe", %A_ScriptDir%\nExitApp\n'
assert len(ORIG) == RES_SIZE
NEW = NEW_SCRIPT + b"; " + b" " * (RES_SIZE - len(NEW_SCRIPT) - 2)
assert len(NEW) == RES_SIZE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    exe = a.exe; bak = bak_path(exe, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, exe); print(f"reverted {exe} from {bak}"); return
    data = bytearray(open(exe, "rb").read())
    cur = bytes(data[RES_OFF:RES_OFF + RES_SIZE])
    st = "vanilla (Slickness launcher)" if cur == ORIG else "ALREADY PATCHED" if cur == NEW else "UNKNOWN"
    print(f"target: {exe} ({len(data)} B)\n  script @{RES_OFF:#x}: {st}\n  current: {cur!r}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if st == "UNKNOWN":
        sys.exit("refusing: unexpected script bytes")
    if st == "ALREADY PATCHED":
        print("already applied"); return
    if not os.path.exists(bak):
        shutil.copy2(exe, bak); print(f"  backup -> {bak}")
    data[RES_OFF:RES_OFF + RES_SIZE] = NEW
    with open(exe, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied: AoW.exe now just launches AoWx.exe.")


if __name__ == "__main__":
    main()
