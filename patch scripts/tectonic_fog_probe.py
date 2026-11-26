#!/usr/bin/env python3
"""Read-only live probe for the Tectonic Shift (219) 'fog turns black' flicker (2026-10-17).

Start it, switch to the game, cast Tectonic Shift (or end the turn it completes on) and watch the fog.
Nothing is written to the game process.  Every sample (as fast as the screen grab allows, ~20-30/s):
  * screen: mean brightness of the whole primary screen + of its darkest 10 % (the fog shows up there),
  * map  [[0x558E9494]] (AoWEPACK, rebased): +0x30 static-dirty, +0x31 dynamic-dirty, +0x80/+0x84 origin,
          +0x88 viewed level, +0xA5 viewing player, +0xC8/+0xC9 fog flags, user-sprite count [+0x28].count,
  * the live 219 map-wide animation (user sprite whose OnShow Data [+0x28] is a spell with id 219): its tick,
  * the exe shake vars (.xedt 0x62FD00: request, start, packed amp/len, DX, DY).
A line is printed whenever any state value changes or the dark-10 % brightness jumps by > 25 %; frames whose
brightness falls > 35 % below the running median are saved as PNGs in tmp_fogprobe\ (max 12) for proof.
Usage: py -3.10 tectonic_fog_probe.py [seconds=90]   (log also written to tectonic_fog_probe.log)
"""
import os, sys, time, statistics
sys.argv, secs = [sys.argv[0]], float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P
from PIL import ImageGrab, ImageStat

EPACK_BASE, MAP_CELL, XV = 0x55700000, 0x558E9494, 0x62FD00
pid, mods = P.find_game(); mem = P.Mem(pid)
ep = mods.get('aowepack.dll'); exe = mods.get('aowx.exe')
reb = (ep - EPACK_BASE) if ep else 0
here = os.path.dirname(os.path.abspath(__file__)); shots = os.path.join(here, "tmp_fogprobe"); os.makedirs(shots, exist_ok=True)
log = open(os.path.join(here, "tectonic_fog_probe.log"), "w")


def out(s):
    print(s); log.write(s + "\n"); log.flush()


def state():
    cell = mem.u32(MAP_CELL + reb); m = mem.u32(cell) if cell else None
    if not m: return None
    us = mem.u32(m + 0x28); n = mem.u32(us + 0xC) if us else 0; items = mem.u32(us + 0x14) if us else 0   # HSE list: count +0xC, items +0x14 (8-byte entries, object at +4)
    anim = None
    for i in range(min(n or 0, 64)):
        a = mem.u32(items + 8 * i + 4) if items else None
        sp = mem.u32(a + 0x28) if a else None
        if sp and mem.u32(sp + 0x10) == 219: anim = mem.u32(a + 0x10)
    xv = mem.read((exe - 0x400000 if exe else 0) + XV, 0x20) or bytes(0x20)
    return (mem.u8(m + 0x30), mem.u8(m + 0x31), mem.i32(m + 0x80), mem.i32(m + 0x84), mem.i32(m + 0x88),
            mem.u8(m + 0xA5), mem.u8(m + 0xC8), mem.u8(m + 0xC9), n, anim,
            tuple(int.from_bytes(xv[k:k + 4], 'little', signed=True) for k in (0, 8, 0x18, 0x1C)))


out("pid %d  AoWEPACK %s  exe %s  -- columns: t  bright  dark10  [static,dyn dirty | origin | level | viewer | c8,c9 | "
    "usersprites | tect tick | shake(req,len,DX,DY)]" % (pid, hex(ep or 0), hex(exe or 0)))
t0 = time.time(); last = None; hist = []; saved = 0; lastdark = None
while time.time() - t0 < secs:
    img = ImageGrab.grab(); g = img.convert("L").resize((320, 180))
    px = sorted(g.getdata()); bright = sum(px) / len(px); dark = sum(px[:len(px) // 10]) / (len(px) // 10)
    st = state(); t = time.time() - t0
    hist.append(bright); hist = hist[-60:]; med = statistics.median(hist)
    jump = lastdark is not None and lastdark > 1 and abs(dark - lastdark) / lastdark > 0.25
    if st != last or jump:
        s = st and ("%d,%d | %d,%d | lvl %d | pl %d | %d,%d | us %d | tect %s | %s" % (st[0], st[1], st[2], st[3], st[4], st[5],
                    st[6], st[7], st[8], st[9], st[10]))
        out("%7.3f  %6.1f %6.1f  %s" % (t, bright, dark, s))
        last = st
    if len(hist) > 10 and bright < 0.65 * med and saved < 12:
        fn = os.path.join(shots, "dip_%02d_%07.3f.png" % (saved, t)); img.save(fn); saved += 1
        out("        ^ brightness dip (%.1f vs median %.1f) saved %s" % (bright, med, fn))
    lastdark = dark
out("done (%d dip frames saved)" % saved)
