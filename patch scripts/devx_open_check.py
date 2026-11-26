#!/usr/bin/env python3
r"""Open a map in AoWDevX (minimised, no focus steal) and report whether it loaded (2026-11-13).
The TMainForm caption becomes 'AoWDevX [<path>]' once a map is open.  Also lists the process's visible windows
(error dialogs) and CPU use.  Usage: py -3.10 devx_open_check.py "<map path>" [wait seconds=15] [--keep]"""
import ctypes as C, os, subprocess, sys, time
from ctypes import wintypes as W
import psutil
from bakpath import game_dir

u = C.WinDLL("user32")
CB = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def windows(pid):
    out = []
    def cb(h, l):
        q = W.DWORD(); u.GetWindowThreadProcessId(h, C.byref(q))
        if q.value == pid:
            t = C.create_unicode_buffer(300); c = C.create_unicode_buffer(100)
            u.GetWindowTextW(h, t, 300); u.GetClassNameW(h, c, 100)
            out.append((c.value, t.value, bool(u.IsWindowVisible(h))))
        return True
    u.EnumWindows(CB(cb), 0)
    return out


def main():
    mp = os.path.abspath(sys.argv[1]); wait = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 15
    si = subprocess.STARTUPINFO(); si.dwFlags = 1; si.wShowWindow = 7          # SW_SHOWMINNOACTIVE
    p = subprocess.Popen([os.path.join(game_dir(), "AoWDevX.exe"), mp], cwd=game_dir(), startupinfo=si)
    time.sleep(wait)
    if p.poll() is not None:
        print("EXITED code", p.returncode); return
    ps = psutil.Process(p.pid); c0 = ps.cpu_times().user; time.sleep(2); c1 = ps.cpu_times().user
    ws = windows(p.pid)
    main_ = [t for c, t, v in ws if c == "TMainForm"]
    print("main form:", main_, "| loaded" if main_ and "[" in main_[0] else "| NOT loaded", "| cpu %.2fs/2s" % (c1 - c0))
    for c, t, v in ws:
        if v and c not in ("TMainForm", "TApplication"):
            print("  visible window:", c, repr(t))
    if "--keep" not in sys.argv:
        p.kill()


if __name__ == "__main__":
    main()
