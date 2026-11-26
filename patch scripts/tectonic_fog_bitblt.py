#!/usr/bin/env python3
"""High-rate capture of the AoWx window via GDI BitBlt (2026-10-17, black-fog hunt).  Grabs the game window's client
area as fast as possible, logs mean brightness per grab + the shake DX/DY, saves dips (and the frame before) to
tmp_fogblt\.  Usage: py -3.10 tectonic_fog_bitblt.py [seconds=60]"""
import os, sys, time, ctypes, ctypes.wintypes as W, statistics
import numpy as np
from PIL import Image
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P
u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
u32.SetProcessDPIAware()
pid, mods = P.find_game(); mem = P.Mem(pid); exe = mods.get('aowx.exe'); xr = (exe - 0x400000) if exe else 0
found = []
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
here = os.path.dirname(os.path.abspath(__file__)); shots = os.path.join(here, "tmp_fogblt"); os.makedirs(shots, exist_ok=True)
for f in os.listdir(shots): os.remove(os.path.join(shots, f))
hdc = u32.GetDC(hwnd); mdc = g32.CreateCompatibleDC(hdc)
class BMI(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                ("biCompression", W.DWORD), ("biSizeImage", W.DWORD), ("a", W.LONG), ("b", W.LONG), ("c", W.DWORD), ("d", W.DWORD)]
bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0); bits = ctypes.c_void_p()
hbm = g32.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0); g32.SelectObject(mdc, hbm)
buf = (ctypes.c_ubyte * (w * h * 4)).from_address(bits.value)
log = open(os.path.join(here, "tectonic_fog_bitblt.log"), "w")
t0 = time.perf_counter(); n = 0; hist = []; prev = None; saved = 0
while time.perf_counter() - t0 < secs:
    g32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
    a = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
    small = a[::4, ::4, :3].astype(np.float32); b = float(small.mean()); t = time.perf_counter() - t0; n += 1
    xv = mem.read(xr + 0x62FD18, 8) or bytes(8)
    dx, dy = int.from_bytes(xv[0:4], 'little', signed=True), int.from_bytes(xv[4:8], 'little', signed=True)
    log.write("%8.4f %6.2f %d %d\n" % (t, b, dx, dy))
    hist.append(b); hist = hist[-90:]
    if len(hist) > 30 and (b < 0.8 * statistics.median(hist) or b > 1.4 * statistics.median(hist)) and saved < 8:
        Image.fromarray(a[:, :, 2::-1].copy()).save(os.path.join(shots, "dip%02d_%08.4f_b%05.1f.png" % (saved, t, b)))
        if prev is not None: Image.fromarray(prev[:, :, 2::-1]).save(os.path.join(shots, "dip%02d_%08.4f_prev.png" % (saved, t)))
        saved += 1
    prev = a.copy() if saved < 8 else None
log.write("done %d grabs %.1f/s, %d dips\n" % (n, n / secs, saved)); log.close()
print("done %d grabs %.1f/s, %d dips saved, window %dx%d" % (n, n / secs, saved, w, h))
