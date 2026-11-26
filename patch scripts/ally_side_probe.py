#!/usr/bin/env python3
"""READ-ONLY live probe (2026-10-18, ally enchant hunt).  Run during a battle that has an ALLIED army on your side:
    py -3.10 ally_side_probe.py            -> combat players (index -> player / side) + every unit's combat player,
                                              player and side, as the tactical code sees them (GetPlayer / GetSide)
Nothing is written to the game.  Output also goes to ally_side_probe.log next to this script."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = sys.argv[:1]
import ai_state_probe as P

pid, mods = P.find_game(); tc = mods.get('aowtcpck.dll'); mem = P.Mem(pid)
if tc is None: sys.exit("AoWTCPCK.dll not in process")
cmap = mem.u32(P.G_COMBATMAP + tc - P.BASE)
if not cmap: sys.exit("no tactical combat map active")
log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ally_side_probe.log"), "w")
def out(s): print(s); log.write(s + "\n"); log.flush()

combat = mem.u32(cmap + 0xE4); data = mem.u32(combat + 0xC) if combat else 0
out(f"cmap {cmap:#x}  [+0xEC] turn cplayer {mem.u8(cmap + 0xEC)}  [+0xED] {mem.u8(cmap + 0xED)}  "
    f"[+0xA4] {mem.u8(cmap + 0xA4)}  [+0xA5] local player {mem.u8(cmap + 0xA5)}  combat {combat:#x} data {data:#x}")
cps = {}
pc = mem.u32(data + 0x38) if data else 0; lst = mem.u32(pc + 8) if pc else 0
if lst:
    items, cnt = mem.u32(lst + 4), mem.u32(lst + 8)
    for i in range(cnt or 0):
        cp = mem.u32(items + 4 * i)
        if cp:
            cps[i] = (mem.u8(cp + 8), mem.u8(cp + 0xA))
            out(f"  combat player {i}: {cp:#x} {mem.classname(cp)}  player {cps[i][0]}  side {cps[i][1]}")
cai = mem.u32(cmap + 0x118)
for name, off in (("[cai+8]", 8), ("[cai+C]", 0xC), ("[cai+10]", 0x10)):
    l = mem.u32(cai + off) if cai else 0
    if not l: continue
    items, cnt = mem.u32(l + 4), mem.u32(l + 8)
    out(f"  TCAI list {name}: {cnt}")
    for i in range(cnt or 0):
        o = mem.u32(items + 4 * i)
        if not o: continue
        cpi = mem.u8(o + 0x45); unit = mem.u32(o + 0x4C); res = mem.u32(unit + 0x40) if unit else 0
        nm = mem.ansistr(mem.u32(res + 0x24)) if res else ''
        pl, sd = cps.get(cpi, (None, 2 if cpi == 0xFF else None))
        out(f"    {o:#x} '{nm}' cplayer {cpi} -> player {pl} side {sd}  flags {mem.u8(o + 0x47):#04x}")
