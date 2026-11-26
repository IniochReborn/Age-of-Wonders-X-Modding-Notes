#!/usr/bin/env python3
r"""
DEV helper for testing the title-screen updater line (patch_exe_updater_title_v1.py) in game without a real update
(2026-10-20).  Writes fake values into HKCU\Software\Triumph Studios\Age of Wonders X\Updater - the same values
AoWxUpdater.exe writes - and can drop a do-nothing stand-in AoWxUpdater.exe into the game folder (the game only shows
the line / launches anything when <game>\AoWxUpdater.exe exists; the stand-in ignores every argument, so it never
overwrites the fake values and never downloads anything).

  py -3.10 dev_updater_title_test.py --status 1                         green "AoWx is up to date!"
  py -3.10 dev_updater_title_test.py --status 2 --version 1.37.425      red "Update available!" (hover / click)
  py -3.10 dev_updater_title_test.py --status 2 --mode Ask              + the Ask popup at the title
  py -3.10 dev_updater_title_test.py --status 3                         amber "Update ready - installs when you quit"
  py -3.10 dev_updater_title_test.py --mode Off                         nothing shown
  py -3.10 dev_updater_title_test.py --dummy-exe                        install the stand-in AoWxUpdater.exe
  py -3.10 dev_updater_title_test.py --show                             print the current values
  py -3.10 dev_updater_title_test.py --clear                            delete the fake values (+ remove the stand-in)
Typing UPDATE on the title with the stand-in shows "Checking for updates..." for ~15 s (the stand-in never answers).
⚠ Do not leave the stand-in in place when testing the real updater; --clear removes it (only if it is the stand-in).
"""
import argparse, os, subprocess, sys, tempfile, winreg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import game_dir

KEY = r"Software\Triumph Studios\Age of Wonders X\Updater"
MARK = "AoWxUpdater.exe.devdummy"
CSC = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
VALUES = ("Mode", "Status", "LatestVersion", "LastChecked", "Notes")


def show():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            for n in VALUES + ("Frequency", "Channel", "ReadyVersion", "LastError"):
                try:
                    print("  %-14s %r" % (n, winreg.QueryValueEx(k, n)[0]))
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        print("  (no Updater key)")
    gd = game_dir()
    exe = os.path.join(gd, "AoWxUpdater.exe")
    print("  AoWxUpdater.exe in game folder: %s%s" % (os.path.exists(exe),
                                                       " (dev stand-in)" if os.path.exists(os.path.join(gd, MARK)) else ""))


def dummy_exe():
    gd = game_dir(); exe = os.path.join(gd, "AoWxUpdater.exe")
    if os.path.exists(exe) and not os.path.exists(os.path.join(gd, MARK)):
        print("a REAL AoWxUpdater.exe is already in the game folder - not replacing it"); return 1
    src = os.path.join(tempfile.gettempdir(), "aowx_updater_devdummy.cs")
    open(src, "w").write("class P { static void Main(string[] a) { } }\n")
    r = subprocess.run([CSC, "/nologo", "/target:winexe", "/out:" + exe, src], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr); return 1
    open(os.path.join(gd, MARK), "w").write("dev stand-in written by dev_updater_title_test.py\n")
    print("stand-in written: " + exe); return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", type=int, choices=(0, 1, 2, 3))
    ap.add_argument("--version")
    ap.add_argument("--mode", choices=("Auto", "Ask", "Off"))
    ap.add_argument("--checked", help="LastChecked text (default: now)")
    ap.add_argument("--dummy-exe", action="store_true")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    if a.clear:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
                for n in VALUES:
                    try: winreg.DeleteValue(k, n)
                    except FileNotFoundError: pass
        except FileNotFoundError:
            pass
        gd = game_dir()
        if os.path.exists(os.path.join(gd, MARK)):
            for f in ("AoWxUpdater.exe", MARK):
                try: os.remove(os.path.join(gd, f))
                except FileNotFoundError: pass
            print("stand-in removed")
        print("cleared"); show(); return 0
    if a.dummy_exe:
        rc = dummy_exe()
        if rc: return rc
    if a.status is not None or a.version or a.mode or a.checked:
        import datetime
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            if a.status is not None: winreg.SetValueEx(k, "Status", 0, winreg.REG_DWORD, a.status)
            if a.version: winreg.SetValueEx(k, "LatestVersion", 0, winreg.REG_SZ, a.version)
            if a.mode: winreg.SetValueEx(k, "Mode", 0, winreg.REG_SZ, a.mode)
            winreg.SetValueEx(k, "LastChecked", 0, winreg.REG_SZ,
                              a.checked or datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    show(); return 0


if __name__ == "__main__":
    sys.exit(main())
