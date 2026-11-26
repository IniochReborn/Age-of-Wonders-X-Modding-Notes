#!/usr/bin/env python3
"""
HP-cap medal icon (v1) — AoWEPACK.dll  (applied 2026-07-20)
===========================================================
Shows Combat.ilb index 8 (user-added) instead of the silver(5)/gold(6) medal
icon when a unit's max HP has reached the cap (base*(7-tier)/2, from the
hp-cap patch). The single shared unit-card painter draws medals for all
displays: TUnit.GetRank branch at 0x557826F5 -> silver draw (mov edx,5
@0x55782712) / gold draw (mov edx,6 @0x5578273B), image list [0x558FA044]+0x50,
GetImage 0x55702934. EBX=unit (TUnit) at both sites.

Cave 0x5580EF10 (74B): entry5/entry6 set default icon, common computes
capped = (base + 2*(XP/10)) >= base*(7-tier)>>1 -> icon 8.
REQUIRES: hp-cap patch (same cap formula); user's Combat.ilb with index 8.
Revert: restore AoWEPACK.dll.bak_medal_icon
Run: python patch_medal_icon_v1.py --apply
"""
import struct, sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_medal_icon'
DELTA = 0x55700C00
CAVE_OFF = 0x10E310
CAVE_VA = CAVE_OFF + DELTA

CAVE = bytes.fromhex(
    'BA05000000' 'EB05' 'BA06000000'
    '505156' '8B4340' '0FB6482C' '0FB6702F' 'B807000000' '2BC6' '0FAFC1'
    'D1E8' '8BF0' '0FB6433C' '52' '33D2' '57BF0A000000' 'F7F7' '5F'
    '03C0' '03C1' '5A' '3BC6' '7C05' 'BA08000000' '5E5958' 'C3')

def call(src, dst): return b'\xE8' + struct.pack('<i', dst - (src + 5))
PATCHES = [
    (0x81B12, b'\xBA\x05\x00\x00\x00', call(0x55782712, CAVE_VA),     'silver icon site'),
    (0x81B3B, b'\xBA\x06\x00\x00\x00', call(0x5578273B, CAVE_VA + 7), 'gold icon site'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    if bytes(data[CAVE_OFF:CAVE_OFF+len(CAVE)]) == CAVE:
        print('already applied'); return
    assert bytes(data[CAVE_OFF:CAVE_OFF+len(CAVE)]) == b'\x00'*len(CAVE)
    for off, orig, new, desc in PATCHES:
        assert bytes(data[off:off+len(orig)]) == orig, desc
        assert len(new) == len(orig)
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    size0 = len(data)
    data[CAVE_OFF:CAVE_OFF+len(CAVE)] = CAVE
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
    assert len(data) == size0
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
