#!/usr/bin/env python3
"""READ-ONLY live probe (2026-10-17, Smokescreen v3.3 earth-wall hunt): lists the objects of the ACTIVE tactical
combat map so we can see which class draws the underground earth walls / pillars.

Run it while a battle is on screen (ideally an underground battle with earth walls in view):
    py -3.10 combat_objects_probe.py              -> summary: object count per (list, class) + every IL-terrain tile
                                                     whose image is taller than 40 px
    py -3.10 combat_objects_probe.py X Y [R]      -> every object within R (default 2) hexes of combat hex (X, Y)
Nothing is written to the game.  Output also goes to combat_objects_probe.log.
Per object: list (static [map+0x1C] / dynamic [+0x20] / user [+0x28]), address, VMT, Delphi class name (VMT-0x20),
hex (+0x10/+0x11), resource [+8], tile index [+0x14], resource library [+0x20] / sequence list [+0x24], image
size (direct: lib.Get(idx); sequence: first part's library image 0), and the resource's name if it has one."""
import os, sys, struct
args = [int(a) for a in sys.argv[1:]]
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P

pid, mods = P.find_game(); tc = mods.get('aowtcpck.dll'); mem = P.Mem(pid)
if tc is None: sys.exit("AoWTCPCK.dll not in process")
cmap = mem.u32(P.G_COMBATMAP + tc - P.BASE)
if not cmap: sys.exit("no tactical combat map active - start/continue a battle first")
log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "combat_objects_probe.log"), "w")
def out(s): print(s); log.write(s + "\n")

def libimg(lib, idx):
    """TCustomImageLibrary.Get: [lib+0x48] = 8-byte entries indexed by id -> image; TLibraryImage w +0x20 / h +0x24."""
    arr = mem.u32(lib + 0x48) if lib else None
    img = mem.u32(arr + 8 * idx) if arr is not None and 0 <= idx < 4096 else None
    if not img: return None
    return mem.i32(img + 0x20), mem.i32(img + 0x24)

def info(o):
    vmt = mem.u32(o) or 0; cls = mem.classname(o)
    hx, hy = (mem.read(o + 0x10, 2) or b"\xff\xff")
    hx = hx - 256 if hx > 127 else hx; hy = hy - 256 if hy > 127 else hy
    res = mem.u32(o + 8) or 0; idx = mem.i32(o + 0x14)
    lib = seq = size = None; how = ""
    if res and ('Terrain' in cls or 'Obstacle' in cls):
        lib = mem.u32(res + 0x20); seq = mem.u32(res + 0x24)
        if seq:
            n = mem.u32(seq + 8) or 0; items = mem.u32(seq + 4)
            part = mem.u32(items + 4 * idx) if items and idx is not None and 0 <= idx < n else None
            plib = mem.u32(part + 0x10) if part else None
            size = libimg(plib, 0); how = "seq(n=%d part=%s lib=%s)" % (n, hex(part or 0), hex(plib or 0))
        elif lib and idx is not None:
            size = libimg(lib, idx); how = "direct"
    return dict(o=o, vmt=vmt, cls=cls, hx=hx, hy=hy, res=res, idx=idx, lib=lib, seq=seq, size=size, how=how)

def fmt(L, i):
    return "%-7s %08X vmt %08X %-28s hex(%3d,%3d) res %08X idx %-4s lib %-10s seq %-10s size %-10s %s" % (
        L, i['o'], i['vmt'], i['cls'], i['hx'], i['hy'], i['res'], i['idx'], hex(i['lib'] or 0), hex(i['seq'] or 0),
        "%dx%d" % i['size'] if i['size'] else "-", i['how'])

out("AoWx pid %d  AoWTCPCK %#x  combat map %#x  (VMTs below are as loaded; preferred base 0x400000, delta %+#x)" % (pid, tc, cmap, tc - P.BASE))
objs = []
for name, off in (("static", 0x1C), ("dynamic", 0x20), ("user", 0x28)):
    lst = mem.u32(cmap + off)
    if not lst: continue
    n = mem.u32(lst + 0xC) or 0; items = mem.u32(lst + 0x14)
    for k in range(min(n, 20000)):
        o = mem.u32(items + 8 * k + 4) if items else None
        if o: objs.append((name, info(o)))
if len(args) >= 2:
    X, Y = args[0], args[1]; R = args[2] if len(args) > 2 else 2
    out("objects within %d hexes of (%d, %d):" % (R, X, Y))
    for L, i in sorted(objs, key=lambda t: (t[1]['hy'], t[1]['hx'])):
        if abs(i['hx'] - X) <= R and abs(i['hy'] - Y) <= R: out("  " + fmt(L, i))
else:
    from collections import Counter
    c = Counter((L, i['cls'], hex(i['vmt'] - (tc - P.BASE))) for L, i in objs)
    out("object count per (list, class, VMT at preferred base):")
    for (L, cls, v), k in sorted(c.items()): out("  %-7s %-30s %s  x%d" % (L, cls, v, k))
    out("IL-terrain / obstacle objects with an image taller than 40 px:")
    for L, i in objs:
        if i['size'] and i['size'][1] > 40: out("  " + fmt(L, i))
    # v3.4 (Smokescreen earth walls): TCombatHexagon base hexes whose base-hex library image 0 is >= 100 px (H_EARTH 'Wall')
    eh = []
    for L, i in objs:
        if i['cls'] != 'TIsometricCombatHexagon' or not i['res']: continue   # v3.5: the earth walls (live 10/17)
        seq = mem.u32(i['res'] + 0x24); n = mem.u32(seq + 8) if seq else 0
        items = mem.u32(seq + 4) if seq else 0; part = mem.u32(items) if items and n else 0
        lib = mem.u32(part + 0x10) if part else 0; sz = libimg(lib, 0) if lib else None
        fld = mem.u32(i['o'] + 4); fx, fy = (mem.read(fld + 0x10, 2) or b"\xff\xff") if fld else (255, 255)
        base = (mem.read(i['o'] + 0x10, 4) or bytes(4))
        if sz and sz[1] >= 100: eh.append((fy, fx, base.hex(), sz))
    out("earth walls (TIsometricCombatHexagon, seq item-0 library image 0 >= 100 px = what Smokescreen v3.5 lifts out of the smoke): %d" % len(eh))
    for fy, fx, b, sz in sorted(eh)[:60]: out("  field(%3d,%3d) base/overlay bytes %s  lib image0 %dx%d" % (fx, fy, b, sz[0], sz[1]))
    out("(re-run with: py -3.10 combat_objects_probe.py X Y  - X/Y = a hex with an earth wall, see the hex list above)")
log.close()
