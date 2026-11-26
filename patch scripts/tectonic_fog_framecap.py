#!/usr/bin/env python3
"""Fast small-region screen capture for the Tectonic black-fog flash (2026-10-17).  Grabs a 640x360 box at the screen
centre as fast as possible, logs mean brightness + the exe shake DX/DY each frame, and keeps the 12 darkest frames
(plus the frame before each) as PNGs in tmp_fogcap\.  Usage: py -3.10 tectonic_fog_framecap.py [seconds=60]"""
import os, sys, time
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P
from PIL import ImageGrab, ImageStat
pid, mods = P.find_game(); mem = P.Mem(pid); exe = mods.get('aowx.exe'); xr = (exe - 0x400000) if exe else 0
here = os.path.dirname(os.path.abspath(__file__)); shots = os.path.join(here, "tmp_fogcap"); os.makedirs(shots, exist_ok=True)
for f in os.listdir(shots): os.remove(os.path.join(shots, f))
W, H = ImageGrab.grab().size; box = (W // 2 - 320, H // 2 - 180, W // 2 + 320, H // 2 + 180)
log = open(os.path.join(here, "tectonic_fog_framecap.log"), "w")
frames = []; prev = None; t0 = time.perf_counter(); n = 0
while time.perf_counter() - t0 < secs:
    img = ImageGrab.grab(bbox=box); t = time.perf_counter() - t0; n += 1
    b = ImageStat.Stat(img.convert("L")).mean[0]
    xv = mem.read(xr + 0x62FD18, 8) or bytes(8)
    dx, dy = int.from_bytes(xv[0:4], 'little', signed=True), int.from_bytes(xv[4:8], 'little', signed=True)
    log.write("%8.3f %6.1f %d %d\n" % (t, b, dx, dy))
    frames.append((b, t, img, prev)); frames.sort(key=lambda r: r[0]); frames = frames[:12]
    prev = img
log.write("done %d frames %.1f fps\n" % (n, n / secs)); log.close()
for k, (b, t, img, pv) in enumerate(frames):
    img.save(os.path.join(shots, "dark%02d_%07.3f_b%03d.png" % (k, t, b)))
    if pv: pv.save(os.path.join(shots, "dark%02d_%07.3f_prev.png" % (k, t)))
print("done %d frames, %.1f fps; darkest %s" % (n, n / secs, [round(r[0], 1) for r in frames]))
