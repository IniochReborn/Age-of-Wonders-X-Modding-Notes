#!/usr/bin/env python3
"""
Victim medals count toward kill XP (units AND heroes) (v1) — AoWEPACK.dll
=========================================================================
Applied 2026-07-20. REQUIRES capxp2x (+its chain).

- cave_victimxp v2 (0x5580F000, 66B): victim effective level = tier + rank
  (GetRank 0x5578294C on the strategic victim; TUnit victims only — heroes/
  leaders keep raw level), then |0x80 if capped. Single source feeding BOTH
  unit-killer XP (XP cave) and hero-killer XP (THero.SetExperience).
  Unit examples (plain lvl-3 killer vs lvl-4 victim): silver 15, gold 20,
  capped 40 = (tier+rank+1-killer)*5, x2 when capped.
- Hero XP tier cave REWRITTEN (0x5580BE80, 93B in 112B region): keeps
  delta<=0 direct-store + dh==0xFF raw-add escape; strips capped flag
  (delta>=0x80 -> -0x80, remember); tier ladder by effective level
  1->1, 2->5, 3->15, 4->25, >=5->50; capped -> value x2.
  (So heroes: silver-1 kill +5, gold-1 +15, capped-1 +30, capped-4 +100.)

Revert: restore AoWEPACK.dll.bak_medal_killxp
This script records the change set; applied interactively with size checks.
Re-apply: restore backup then rerun session steps (bytes in active-patches.md).
"""
import sys, os
DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
VICXP2_HEAD = bytes.fromhex('8bc68b10ff92a000000025ff000000538b5e4c85db7429')
HERO2_HEAD  = bytes.fromhex('528bf08b4648' '29c2' '85d2' '7705' '5a895648c3' '80feff7507')

def main():
    data = open(DLL, 'rb').read()
    ok1 = data[0x10E400:0x10E400+len(VICXP2_HEAD)] == VICXP2_HEAD
    ok2 = data[0x10B280:0x10B280+len(HERO2_HEAD)] == HERO2_HEAD
    print('victimxp v2:', 'applied' if ok1 else 'NOT APPLIED')
    print('hero cave v2:', 'applied' if ok2 else 'NOT APPLIED')

if __name__ == '__main__':
    main()
