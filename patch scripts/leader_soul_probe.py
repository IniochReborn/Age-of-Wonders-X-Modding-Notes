r"""
leader_soul_probe.py - READ-ONLY dump of the Leader's Soul v4 runtime diag block (2026-10-22).

  py -3.10 leader_soul_probe.py        one line per running AoWx.exe

AoWEPACK .idata slack (runtime-only, zero at load): 0x5590B3C0 FOUND, +4 PICK, then the v4 diag counters:
  +0x08 TLeader+0x180 refusals (the setup-leader Compare said no)   +0x0C refusals v4 overrode (picked / revived leader)
  +0x10 placer-nil clean aborts                                      +0x14 placement-location fallbacks used
  v5: +0x18 STAGE (1 leader picked, 2 coin tails, 3 join attempt, 4 joined soul army, 5 join refused -> placer,
      6 placer returned, 7 oj entered, 8 oj left, 9 placer nil -> abort), +0x1C hero, +0x20 soul army, +0x24 AddChild
  v6: STAGE 10 caster-stack join try, 11 joined caster stack, 12 ring search, 13 new army placed next to caster,
      14 ring search found no hex (then 9); +0x20 = the army the leader went to; +0x28 hexes tried
Run it right after casting Resurrect/Animate Hero on the dead leader.  Elevated prompt if OpenProcess fails.
"""
from presence_probe import module_base, Proc
from autoclaim_probe import all_pids
import struct

PREF, BASE_VA = 0x55700000, 0x5590B3C0


def main():
    pids = all_pids()
    if not pids: print("AoWx not running"); return
    for pid in pids:
        base = module_base(pid)
        if not base: print("pid %d: AoWEPACK.dll not found" % pid); continue
        b = Proc(pid).rd(base + BASE_VA - PREF, 0x2C)
        if len(b) < 0x2C: print("pid %d: read failed" % pid); continue
        found, pick, rf, ov, nil, lc, stage, hero, sarmy, join, tries = struct.unpack("<11I", b)
        print("pid %d: FOUND %08X PICK %08X | leader+0x180 refused %d, overridden %d | placer-nil aborts %d | "
              "location fallbacks %d | STAGE %d hero %08X army %08X AddChild %d hexes tried %d"
              % (pid, found, pick, rf, ov, nil, lc, stage, hero, sarmy, join, tries))


if __name__ == "__main__":
    main()
