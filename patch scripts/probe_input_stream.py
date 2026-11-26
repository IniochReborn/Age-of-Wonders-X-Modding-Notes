#!/usr/bin/env python3
r"""Probe: watch the RAW input stream while the wheel is used in AoWDevX.

Answers the one question static analysis cannot: when the map scrolls while
the cursor is over a side panel, IS anything synthesizing arrow keys, and if
so is it injected (software) or real?

Installs its own WH_MOUSE_LL + WH_KEYBOARD_LL hooks (global, so they see
events for every process) and logs, per event:
    WHEEL  delta, and the class of the window under the cursor
    KEY    vk, and whether LLKHF_INJECTED (0x10) is set
A wheel notch followed by injected VK_UP/VK_DOWN (0x26/0x28) means keys are
being synthesized -- by our VCL30 hook or by anything else. A wheel notch
with NO key event means the map is moving by some other route entirely.

Usage:  py -3.10 "patch scripts\probe_input_stream.py" [seconds]
Writes patch scripts\input_probe.txt (flushed per line).
"""
import ctypes
import ctypes.wintypes as wt
import io
import os
import sys
import time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x020A, 0x020E
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
LLKHF_INJECTED = 0x10
VK = {0x25: "LEFT", 0x26: "UP", 0x27: "RIGHT", 0x28: "DOWN",
      0x21: "PGUP", 0x22: "PGDN", 0x24: "HOME", 0x23: "END"}

LOG = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "input_probe.txt"), "w", encoding="utf-8")


def emit(msg):
    print(msg)
    LOG.write(msg)
    LOG.write(chr(10))
    LOG.flush()


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class KBD(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("extra", ctypes.POINTER(ctypes.c_ulong))]


class MSLL(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("extra", ctypes.POINTER(ctypes.c_ulong))]


def cls_at(pt):
    h = u32.WindowFromPoint(pt)
    if not h:
        return "-", 0
    b = ctypes.create_string_buffer(128)
    u32.GetClassNameA(h, b, 128)
    return b.value.decode(errors="replace"), h


CB = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wt.WPARAM, wt.LPARAM)
t0 = time.time()


def on_mouse(code, wparam, lparam):
    if code == 0 and wparam in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
        m = ctypes.cast(lparam, ctypes.POINTER(MSLL)).contents
        delta = ctypes.c_short((m.mouseData >> 16) & 0xFFFF).value
        c, h = cls_at(m.pt)
        emit("%7.2fs WHEEL  delta=%-5d over=%-20s hwnd=%08X%s"
             % (time.time() - t0, delta, c, h, "  [INJECTED]" if m.flags & 1 else ""))
    return u32.CallNextHookEx(None, code, wparam, lparam)


def on_key(code, wparam, lparam):
    if code == 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
        k = ctypes.cast(lparam, ctypes.POINTER(KBD)).contents
        name = VK.get(k.vkCode, "vk%02X" % k.vkCode)
        inj = "INJECTED(software)" if k.flags & LLKHF_INJECTED else "real hardware"
        emit("%7.2fs KEY    %-6s %s" % (time.time() - t0, name, inj))
    return u32.CallNextHookEx(None, code, wparam, lparam)


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    mcb, kcb = CB(on_mouse), CB(on_key)
    hm = u32.SetWindowsHookExW(WH_MOUSE_LL, mcb, None, 0)
    hk = u32.SetWindowsHookExW(WH_KEYBOARD_LL, kcb, None, 0)
    emit("watching input for %ds -- wheel over a SIDE PANEL, then over the MAP" % secs)
    emit("-" * 70)
    msg = wt.MSG()
    end = time.time() + secs
    while time.time() < end:
        if u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.005)
    u32.UnhookWindowsHookEx(hm)
    u32.UnhookWindowsHookEx(hk)
    emit("done")


if __name__ == "__main__":
    main()
