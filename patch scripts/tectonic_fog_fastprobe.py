#!/usr/bin/env python3
"""Fast read-only probe for the Tectonic Shift black-fog flash (2026-10-17).  No screenshots: reads map state in a
tight loop (thousands of samples/s) and logs every change of the fog-relevant fields with a timestamp.
Usage: py -3.10 tectonic_fog_fastprobe.py [seconds=120]   -> tectonic_fog_fastprobe.log"""
import os, sys, time
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P
EPACK_BASE, MAP_CELL, XV = 0x55700000, 0x558E9494, 0x62FD00
pid, mods = P.find_game(); mem = P.Mem(pid)
ep = mods.get('aowepack.dll'); exe = mods.get('aowx.exe')
reb = (ep - EPACK_BASE) if ep else 0; xr = (exe - 0x400000) if exe else 0
here = os.path.dirname(os.path.abspath(__file__)); log = open(os.path.join(here, "tectonic_fog_fastprobe.log"), "w")
def out(s): print(s); log.write(s + "\n"); log.flush()
out("pid %d AoWEPACK %#x exe %#x  fields: viewer(+A5) level(+88) dirty(+30,+31) fog(+C8,+C9) origin(+80,+84) | shake DX,DY" % (pid, ep or 0, exe or 0))
t0 = time.perf_counter(); last = None; n = 0; m = 0
while time.perf_counter() - t0 < secs:
    if n % 2000 == 0:
        cell = mem.u32(MAP_CELL + reb); m = mem.u32(cell) if cell else 0
    n += 1
    if not m: continue
    xv = mem.read(xr + XV + 0x18, 8) or bytes(8)
    st = (mem.u8(m + 0xA5), mem.i32(m + 0x88), mem.u8(m + 0x30), mem.u8(m + 0x31), mem.u8(m + 0xC8), mem.u8(m + 0xC9),
          mem.i32(m + 0x80), mem.i32(m + 0x84), int.from_bytes(xv[0:4], 'little', signed=True), int.from_bytes(xv[4:8], 'little', signed=True))
    key = st[:6]
    if key != last:
        out("%9.4f  viewer %3d  lvl %d  dirty %d,%d  fog %d,%d  origin %d,%d  DX,DY %d,%d" % ((time.perf_counter() - t0,) + st))
        last = key
out("done: %d samples in %.1f s (%.0f/s)" % (n, time.perf_counter() - t0, n / max(1e-6, time.perf_counter() - t0)))
