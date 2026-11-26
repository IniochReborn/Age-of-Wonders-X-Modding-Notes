#!/usr/bin/env python3
"""Read-only live probe for the Tectonic Shift present-level shake (patch_tectonic_shake_v1.py v5, 2026-10-17).
Prints, every 0.25 s, the exe-var counters the Gfxepack present cave keeps (XV+0x2C presents seen in AoWx,
+0x30 presents from a DC BltSurface/FlipSurface, +0x34 presents drawn shifted) plus the shake state (packed len,
DX, DY).  'seen' and 'dc' should climb every frame; 'shifted' only while a shake runs.
Usage: py -3.10 tectonic_shake_probe.py [seconds=60]   (log also written to tectonic_shake_probe.log)"""
import os, sys, time
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P

XV = 0x62FD00
pid, mods = P.find_game(); mem = P.Mem(pid)
xr = (mods.get('aowx.exe') or 0x400000) - 0x400000
here = os.path.dirname(os.path.abspath(__file__)); log = open(os.path.join(here, "tectonic_shake_probe.log"), "w")


def out(s):
    print(s); log.write(s + "\n"); log.flush()


v = mem.read(xr + XV, 0x40)
out("pid %d  magic %r  Gfxepack %#x" % (pid, v[0xC:0x10] if v else None, mods.get('gfxepack.dpl') or 0))
t0 = time.time(); last = None
while time.time() - t0 < secs:
    v = mem.read(xr + XV, 0x40)
    if v:
        i = lambda o: int.from_bytes(v[o:o + 4], 'little', signed=True)
        st = (i(0x2C), i(0x30), i(0x34), i(8) & 0xFFFF, i(0x18), i(0x1C))
        if st != last:
            out("%7.2f  seen %8d  dc %8d  shifted %6d  | len %4d ms  DX %2d  DY %2d" % ((time.time() - t0,) + st))
            last = st
    time.sleep(0.25)
out("done")
