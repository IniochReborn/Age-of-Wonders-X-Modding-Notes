#!/usr/bin/env python3
"""Read-only live probe for Wall of Flames v2 (patch_tc_walloflames_v1.py v2, 2026-10-17).

Prints the diagnostic counters the patch keeps in AoWEPACK's .idata page slack (DIAG_EP, rebased with the DLL) every
time one changes: flames placed / turn-start scans / turn-start burns / move-in burns / burns completed.
"burns completed" < turn-start + move-in burns => the hit threw inside the unit's breath-hit handler.
Usage: py -3.10 wof_probe.py [seconds=180]   (nothing is written to the game process)
"""
import os, sys, time
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
sys.argv = [sys.argv[0]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_state_probe as P

EPACK_BASE, DIAG_EP = 0x55700000, 0x5590B400
pid, mods = P.find_game(); mem = P.Mem(pid)
ep = mods.get('aowepack.dll'); reb = (ep - EPACK_BASE) if ep else 0
NAMES = ("flames placed", "turn-start scans", "turn-start burns", "move-in burns", "burns completed")
print("pid %d  AoWEPACK %#x  counters @%#x" % (pid, ep or 0, DIAG_EP + reb))
t0 = time.time(); last = None
while time.time() - t0 < secs:
    b = mem.read(DIAG_EP + reb, 20)
    if b is None: print("read failed (game closed?)"); break
    v = tuple(int.from_bytes(b[4 * k:4 * k + 4], "little") for k in range(5))
    if v != last:
        print("%7.2f  " % (time.time() - t0) + "  ".join("%s %d" % kv for kv in zip(NAMES, v))); last = v
    time.sleep(0.05)
print("done")
