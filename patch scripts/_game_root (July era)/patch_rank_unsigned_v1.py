#!/usr/bin/env python3
"""
GetRank unsigned-compare fix (v1) — AoWEPACK.dll  (applied 2026-07-20)
======================================================================
Pre-Claude TUnit.GetRank (0x5578294C) used SIGNED `jl` on the XP byte:
XP >= 128 read as negative -> rank 0 -> medal icon vanished (incl. our capped
icon 8, which lives in the rank branches) and silver/gold rank stat-table
bonuses were lost. Cap-based logic (movzx/unsigned) was unaffected.
Fix: both `jl` -> `jb` (0x7C -> 0x72) at 0x55782955 / 0x5578295A.
Revert: restore AoWEPACK.dll.bak_rank_unsigned
Run: python patch_rank_unsigned_v1.py [--apply]
"""
import sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_rank_unsigned'

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    region = bytes(data[0x81D52:0x81D5E])
    if region == bytes.fromhex('80fa0a720d80fa147204b002'):
        print('already applied'); return
    assert region == bytes.fromhex('80fa0a7c0d80fa147c04b002'), region.hex()
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    data[0x81D55] = 0x72
    data[0x81D5A] = 0x72
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
