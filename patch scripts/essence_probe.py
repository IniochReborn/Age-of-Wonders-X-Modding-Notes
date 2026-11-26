#!/usr/bin/env python3
"""essence_probe.py - READ-ONLY live probe for Essence Shift (spell 231, patch_essenceshift_v1.py v5), 2026-10-18.

Run it while AoWx is running (after a cast, or any time):  py -3.10 essence_probe.py
Prints:
  * the v5 diag dwords (AoWEPACK .idata slack 0x5590BD10, rebase-aware):
      +0x00 stage: 1 started, 2 events off / retiring, 3 old node retired (unowned, shadow gone, off the map, listeners
            notified), 4 new node placed (+ owned), 5 done, 9 done + synchronise ended;
            bit 0x80 = an exception was raised inside the transform and CAUGHT (no dialog),
            bit 0x20 = the recovery re-placed the OLD node type, bit 0x40 = the recovery raised too
      +0x04 casts that reached the transform, +0x08 path (3 = retire + place), +0x0C chosen sphere,
      +0x10 candidate sphere mask (bit n = sphere n), +0x14 exception object pointer (0 = none),
      +0x18 ClassID of the node that was targeted, +0x1C caster player index (TE byte +0x18)
  * every player's leader sphere picks (TPlayer [+0xD4] -> TLeader [+0xA0] list: items +4 bytes, count +8) and the
    per-sphere counts, so the chosen sphere can be checked against the spec (highest count, random tie-break).
Nothing is written to the game process.
"""
import os, sys
sys.argv = sys.argv[:1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P

EPACK_BASE, DIAG, GAMEVAR = 0x55700000, 0x5590BD10, 0x558FA040
SPH = {0: "Cosmos", 1: "Life", 2: "Death", 3: "Earth", 4: "Air", 5: "Fire", 6: "Water"}
CIDS = {0x2019A: "Power node", 0x20371: "Life node", 0x204AE: "Death node", 0x204CE: "Earth node", 0x2094E: "Air node",
        0x203DE: "Fire node", 0x204B3: "Water node", 0x20822: "Random node"}

pid, mods = P.find_game(); mem = P.Mem(pid)
ep = mods.get('aowepack.dll')
if not ep: sys.exit("AoWEPACK.dll not loaded")
reb = ep - EPACK_BASE
d = [mem.u32(DIAG + reb + 4 * k) or 0 for k in range(8)]
st = d[0]
flags = []
if st & 0x80: flags.append("EXCEPTION caught")
if st & 0x20: flags.append("old node re-placed by recovery")
if st & 0x40: flags.append("recovery raised too")
stage = {0: "never ran", 1: "started", 2: "retiring old node", 3: "old node retired", 4: "new node placed", 5: "done",
         9: "done (sync ended)"}.get(st & 0x1F, "?")
print("AoWx pid %d  AoWEPACK %#x" % (pid, ep))
print("diag: stage %#x = %s%s" % (st, stage, (" | " + ", ".join(flags)) if flags else ""))
print("      casts %d, path %d, chosen sphere %d (%s), candidate mask %#x %s" % (
    d[1], d[2], d[3], SPH.get(d[3], "?"), d[4], [SPH[s] for s in range(7) if d[4] >> s & 1]))
print("      exception object %#x, targeted node %#x (%s), caster index %d" % (d[5], d[6], CIDS.get(d[6], "?"), d[7]))
game = mem.u32(GAMEVAR + reb)
pl = mem.u32(game + 0x140) if game else None
lst = mem.u32(pl + 8) if pl else None
n = mem.u32(lst + 8) if lst else 0
items = mem.u32(lst + 4) if lst else None
for i in range(min(n or 0, 16)):
    p = mem.u32(items + 4 * i) if items else None
    if not p: continue
    ld = mem.u32(p + 0xD4)
    sl = mem.u32(ld + 0xA0) if ld else None
    cnt = mem.u32(sl + 8) if sl else 0
    it = mem.u32(sl + 4) if sl else None
    picks = list(mem.read(it, cnt) or b"") if it and cnt and cnt < 64 else []
    counts = {SPH.get(s, str(s)): picks.count(s) for s in sorted(set(picks))}
    print("player %d @%#x: leader picks %s -> %s" % (i, p, picks, counts))
