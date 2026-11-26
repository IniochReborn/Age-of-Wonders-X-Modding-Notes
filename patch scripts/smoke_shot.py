#!/usr/bin/env python3
"""Read-only screenshot helper (2026-10-17, Smokescreen earth-wall test): copies the AoWx game window (GDI BitBlt of its
client area, cropped to the drawn picture) to patch scripts\tmp_smokeshot\shot_NN.png.  Nothing is written to the game.
Usage: py -3.10 smoke_shot.py [count=1] [interval_s=2]   e.g. `py -3.10 smoke_shot.py 5 2` = 5 shots, 2 s apart."""
import os, sys, time, ctypes, ctypes.wintypes as W
import numpy as np
from PIL import Image
cnt = int(sys.argv[1]) if len(sys.argv) > 1 else 1; gap = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
sys.argv = [sys.argv[0]]
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import ai_state_probe as P
u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
u32.SetProcessDPIAware()
pid, mods = P.find_game(); found = []
@ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
def cb(h, l):
    p = W.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    if p.value == pid and u32.IsWindowVisible(h):
        r = W.RECT(); u32.GetClientRect(h, ctypes.byref(r))
        if r.right * r.bottom > 300000: found.append((r.right * r.bottom, h, r.right, r.bottom))
    return True
u32.EnumWindows(cb, 0)
if not found: sys.exit("game window not found")
_, hwnd, w, h = max(found)
class BMI(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("w", W.LONG), ("h", W.LONG), ("p", W.WORD), ("b", W.WORD), ("c", W.DWORD), ("s", W.DWORD),
                ("x", W.LONG), ("y", W.LONG), ("u", W.DWORD), ("i", W.DWORD)]
hdc = u32.GetDC(hwnd); mdc = g32.CreateCompatibleDC(hdc)
bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0); bits = ctypes.c_void_p()
hbm = g32.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0); g32.SelectObject(mdc, hbm)
buf = (ctypes.c_ubyte * (w * h * 4)).from_address(bits.value)
out = os.path.join(here, "tmp_smokeshot"); os.makedirs(out, exist_ok=True)
start = len([f for f in os.listdir(out) if f.startswith("shot_")])
for k in range(cnt):
    g32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
    a = np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, 2::-1].copy()
    nz = np.argwhere(a.sum(2) > 0)
    if len(nz): y1, x1 = nz.max(0); a = a[:y1 + 1, :x1 + 1]
    fn = os.path.join(out, "shot_%02d.png" % (start + k)); Image.fromarray(a).save(fn); print("saved", fn, a.shape[1], "x", a.shape[0])
    if k + 1 < cnt: time.sleep(gap)
