#!/usr/bin/env python3
"""Read-only live probe for Bountiful Harvest (325) income (2026-10-15).  Nothing is written to the game.

Attaches to the running AoWx.exe (AoWEPACK rebase-safe) and, every 0.5 s, prints whatever CHANGED:
  per player   : index, gold [p+0xC4], per-turn income total [p+0xD0] (= [p+0xB0] + sum of income sources),
                 whether that player owns an ACTIVE 325 enchantment (the same test the hva cave does);
  per source   : every TPlayerStructureIncomeSource in [p+0x64] -> its structure ([src+8]): class, owner [+0x30],
                 cached income byte [+0x3C] (what the turn payout really pays), flags [+0xC] (0x20 = income enabled).
Also checks once that patch_harvest_v1's hooks (F / C / NT) are live in memory.

Usage: start the game, load the save, then in a console:
    py -3.10 harvest_probe.py            (Ctrl+C to stop; output also appended to harvest_probe.txt)
Cast Bountiful Harvest, end your turn, play to your next turn and watch: a city/farm line should show its income
byte double its crop part (city = crops + size bonus) once the hooks fire.  Paste harvest_probe.txt back.
"""
import sys, time, os
sys.argv = sys.argv[:1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P

PREF = 0x55700000
MAP_GLOBAL = 0x558FA040
SITES = {"F": (0x557A6253, 0xE8), "C": (0x557ABBC4, 0xE8), "NT": (0x557A620F, 0xE8), "P1": (0x557ABA49, 0xE8)}
SPELL = 325
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvest_probe.txt")


def log(s):
    line = time.strftime("%H:%M:%S ") + s
    print(line)
    with open(OUT, "a", encoding="utf-8") as f: f.write(line + "\n")


def tlist(mem, obj):
    """Delphi TList at [obj+8]: items [l+4], count [l+8]."""
    l = mem.u32(obj + 8) if obj else None
    if not l: return []
    n = mem.u32(l + 8) or 0; it = mem.u32(l + 4)
    if n > 5000 or not it: return []
    return [mem.u32(it + 4 * k) for k in range(n)]


def main():
    pid, mods = P.find_game(); mem = P.Mem(pid)
    ep = mods.get("aowepack.dll")
    if not ep: sys.exit("AoWEPACK.dll not loaded")
    dlt = ep - PREF
    log("attached pid %d, AoWEPACK at %#x (delta %#x)" % (pid, ep, dlt))
    for nm, (va, op) in SITES.items():
        b = mem.read(va + dlt, 5)
        tgt = (va + 5 + int.from_bytes(b[1:5], "little", signed=True)) if b and b[0] == 0xE8 else None
        log("hook %-3s @%#x: %s" % (nm, va, ("call -> %#x" % (tgt - dlt)) if tgt else ("NOT HOOKED (%s)" % (b.hex() if b else "?"))))
    last = {}
    while True:
        try:
            g = mem.u32(MAP_GLOBAL + dlt)
            if not g: time.sleep(0.5); continue
            # active Bountiful Harvest owners (= the hva test: marker 325, active bit, caster byte +0x19)
            owners = set()
            gm = mem.u32(g + 0x188)
            for e in tlist(mem, mem.u32(gm + 0x14) if gm else 0):
                if e and mem.u32(e + 0x14) == SPELL:
                    act = mem.u8(e + 0x10) & 1; who = mem.u8(e + 0x19)
                    key = ("ench", e)
                    val = "Bountiful Harvest ench %#x: active=%d caster=%d flags10=%#x" % (e, act, who, mem.u8(e + 0x10))
                    if last.get(key) != val: log(val); last[key] = val
                    if act: owners.add(who if who < 0x80 else who - 0x100)
            for idx, p in enumerate(tlist(mem, mem.u32(g + 0x140))):
                if not p: continue
                val = "player %d: gold %d  income/turn [D0] %d  base [B0] %d  harvest active %s" % (
                    idx, mem.i32(p + 0xC4), mem.i32(p + 0xD0), mem.i32(p + 0xB0), idx in owners)
                if last.get(("p", idx)) != val: log(val); last[("p", idx)] = val
                for src in tlist(mem, mem.u32(p + 0x64)):
                    st = mem.u32(src + 8) if src else None
                    if not st: continue
                    cn = mem.classname(st)
                    val = "   p%d source %#x -> %s %#x owner %d income[3C] %d flags[C] %#x" % (
                        idx, src, cn, st, mem.u8(st + 0x30), mem.u8(st + 0x3C), mem.u8(st + 0xC))
                    if last.get(("s", st)) != val: log(val); last[("s", st)] = val
            time.sleep(0.5)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
