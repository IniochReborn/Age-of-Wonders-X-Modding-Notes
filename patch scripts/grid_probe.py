#!/usr/bin/env python3
"""Read-only: dump the tactical pathfinder's leftover cost grid (TCombatMoveControlSettings [sel+4]:
+0x20 level grids, +0x1c row offsets, 4 B/cell, 0xFFFFFF = unvisited) of the LAST computed path, the
bound [mc+0x2c] (= straight-line estimate when the line is free, else the 4095 max), src/dst, and the
group selection's stored paths.  Usage: grid_probe.py [x0 x1 y0 y1]"""
import sys
args = [int(a) for a in sys.argv[1:]]
sys.argv = ['x']; sys.path.insert(0, '.')
import ai_state_probe as P
pid, mods = P.find_game(); tc = mods['aowtcpck.dll']; mem = P.Mem(pid)
cmap = mem.u32(P.G_COMBATMAP + tc - P.BASE)
if not cmap: sys.exit("no combat map")
sel = mem.u32(cmap + 0x100); st = mem.u32(sel + 4); mc = mem.u32(cmap + 0xFC)
src = (mem.u32(st + 0x7c), mem.u32(st + 0x80)); dst = (mem.u32(st + 0x88), mem.u32(st + 0x8c))
print(f"last computation: src {src} dst {dst} bound(mc+0x2c) {mem.u32(mc+0x2c)} phase {mem.u8(st+0x65)} max {mem.u32(st+0x98)}")
lv = mem.u32(mem.u32(st + 0x20) + 4 * mem.u32(st + 0x84)); rows = mem.u32(st + 0x1c)
def cell(x, y): return mem.u32(lv + mem.u32(rows + 4 * y) + 4 * x)
x0, x1, y0, y1 = args if len(args) == 4 else (min(src[0], dst[0]) - 3, max(src[0], dst[0]) + 3, min(src[1], dst[1]) - 3, max(src[1], dst[1]) + 3)
print(f"cost grid x={x0}..{x1} (columns), y={y0}..{y1} ('.' = unvisited):")
print("        " + " ".join(f"{x:>4}" for x in range(x0, x1 + 1)))
for y in range(y0, y1 + 1):
    print(f"  y={y:2}: " + " ".join((f"{cell(x,y):>4}" if cell(x, y) != 0xffffff else "   .") for x in range(x0, x1 + 1)))
wrap = mem.u32(sel + 8); lst = mem.u32(wrap + 8); items = mem.u32(lst + 4); n = mem.u32(lst + 8)
print(f"\nselection: {n} unit(s)")
for i in range(n):
    ms = mem.u32(items + 4 * i); hs = mem.u32(ms + 0x10); ho = mem.u32(hs + 4)
    path = mem.u32(ms + 8); pc = mem.u32(path + 8); pi = mem.u32(path + 4)
    nodes = [(v & 0xFF, (v >> 8) & 0xFF, v >> 24) for v in (mem.u32(pi + 4 * k) for k in range(pc))]
    print(f"  [{i}] origin {(mem.u8(ho+0x10), mem.u8(ho+0x11))} path(dest-first) {[(x, y) for x, y, c in nodes]} costs {[c for x, y, c in nodes]}")
