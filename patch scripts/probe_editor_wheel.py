#!/usr/bin/env python3
r"""Probe: what window is under the cursor in AoWDevX, and does it scroll?

Read-only diagnostic for the editor wheel work (no patching). Run it with
the editor open, then hover -- for ~6 seconds each -- over:
    1. the MAP view
    2. the SIDE WINDOW that wrongly pans the map while scrolling
    3. the MAP SCANNER (minimap)
It samples twice a second and prints one line per distinct window, with the
facts the wheel gate needs:
    class name, WS_VSCROLL/WS_HSCROLL on the window AND on every ancestor
    (that is exactly what our WH_MOUSE hook walks), the focused window, and
    the parent chain.

Usage:  py -3.10 "patch scripts\probe_editor_wheel.py" [seconds]
"""
import ctypes
import ctypes.wintypes as wt
import io
import os
import sys
import time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

WS_VSCROLL = 0x00200000
WS_HSCROLL = 0x00100000
GWL_STYLE = -16


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cls(h):
    b = ctypes.create_string_buffer(256)
    u32.GetClassNameA(h, b, 256)
    return b.value.decode(errors="replace")


def text(h):
    b = ctypes.create_string_buffer(128)
    u32.GetWindowTextA(h, b, 128)
    return b.value.decode(errors="replace")


def style(h):
    return u32.GetWindowLongA(h, GWL_STYLE) & 0xFFFFFFFF


def pid_of(h):
    p = wt.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


def chain(h):
    out = []
    seen = 0
    while h and seen < 12:
        s = style(h)
        flags = ("V" if s & WS_VSCROLL else "-") + ("H" if s & WS_HSCROLL else "-")
        out.append("%s[%s]%s" % (cls(h), flags, ("'" + text(h) + "'") if text(h) else ""))
        h = u32.GetParent(h)
        seen += 1
    return " <- ".join(out)


def pname(pid):
    import subprocess
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"], text=True,
            stderr=subprocess.DEVNULL)
        return out.split('","')[0].strip('"') if '","' in out else ""
    except Exception:
        return ""


LOG = None


def emit(msg):
    print(msg)
    if LOG:
        LOG.write(msg)
        LOG.write(chr(10))
        LOG.flush()


def main():
    global LOG
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    LOG = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "wheel_probe3.txt"), "w", encoding="utf-8")
    print("Hover the MAP, then the SIDE WINDOW, then the SCANNER (~6s each).")
    print("-" * 78)
    last = None
    t0 = time.time()
    while time.time() - t0 < secs:
        p = POINT()
        u32.GetCursorPos(ctypes.byref(p))
        h = u32.WindowFromPoint(p)
        if h and pname(pid_of(h)).lower() == "aowdevx.exe":
            key = (h, u32.GetFocus())
            if key != last:
                last = key
                s = style(h)
                scroll_here = bool(s & (WS_VSCROLL | WS_HSCROLL))
                # what our WH_MOUSE hook would find by walking parents
                w, found = h, None
                for _ in range(12):
                    if not w:
                        break
                    if style(w) & (WS_VSCROLL | WS_HSCROLL):
                        found = w
                        break
                    w = u32.GetParent(w)
                fg = u32.GetForegroundWindow()
                foc = u32.GetFocus()          # only valid for our own thread; may be 0
                emit("under cursor : %-22s hwnd=%08X pid=%d" % (cls(h), h, pid_of(h)))
                emit("  scrollable : self=%s   hook-would-scroll=%s"
                      % (scroll_here, ("%s hwnd=%08X" % (cls(found), found)) if found else "NO"))
                emit("  chain      : %s" % chain(h))
                emit("  foreground : %-22s focus(this thread)=%08X" % (cls(fg) if fg else "-", foc or 0))
                verdict = ("MAP -> keys posted here" if cls(h) == "THSMEdit"
                           else "NOT map -> patch must SUPPRESS map scrolling")
                emit("  PATCH SAYS : class=%r  =>  %s" % (cls(h), verdict))
                emit("-" * 78)
        time.sleep(0.5)
    print("done")


if __name__ == "__main__":
    main()
