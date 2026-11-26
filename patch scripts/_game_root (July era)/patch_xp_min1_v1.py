#!/usr/bin/env python3
"""
Minimum 1 XP per kill (v1) — AoWEPACK.dll  (applied 2026-07-20)
===============================================================
AoWx's pre-Claude XP cave (0x5580C200, called from TUnit.SetExperience
0x557828B4) gives 0 XP when the victim's level is 3+ below the killer's
effective level (unit tier +1 at 10 XP/silver, +2 at 20 XP/gold) AND the
victim is level 1. Fix: at the gain/curXP merge point, floor the computed
gain to 1 (only reachable with a positive kill delta).

Patch: `add al,cl` @0x5580C275 (00 C8) -> jmp 0x5580C295; 10-byte stub in the
11-byte free gap after the cave: test al,al; jnz+; inc al; add al,cl; jmp back.
Revert: restore AoWEPACK.dll.bak_xp_min1
Run: python patch_xp_min1_v1.py --apply
"""
import sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_xp_min1'
STUB = bytes.fromhex('84C0' '7502' 'FEC0' '00C8' 'EBD8')

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    if bytes(data[0x10B675:0x10B677]) == b'\xEB\x1E' and bytes(data[0x10B695:0x10B695+len(STUB)]) == STUB:
        print('already applied'); return
    assert bytes(data[0x10B675:0x10B677]) == b'\x00\xC8'
    assert bytes(data[0x10B695:0x10B6A0]) == b'\x00'*11
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    data[0x10B675:0x10B677] = b'\xEB\x1E'
    data[0x10B695:0x10B695+len(STUB)] = STUB
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
