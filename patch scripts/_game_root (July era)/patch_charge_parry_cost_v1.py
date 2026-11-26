#!/usr/bin/env python3
"""
Charge/Parry cost 10 -> 3 per level — AoWEPACK.dll  (applied 2026-07-20)
Retargets both factory calls in RegisterStrikeAbilities from cave_mlcreate
(0x5580E200, costs 10) to the generic cost-3 wrapper cave_mscost (0x5580EB70,
from patch_ability_costs_v1) shared with Monster Slaying.
Requires: charge/parry-leveled + ability-costs patches.
Revert: restore AoWEPACK.dll.bak_chgpar_cost
Run: python patch_charge_parry_cost_v1.py --apply
"""
import struct, sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_chgpar_cost'
MLCREATE, MSCOST = 0x5580E200, 0x5580EB70
def call(src, dst): return b'\xE8' + struct.pack('<i', dst - (src + 5))
PATCHES = [
    (0x6673F, call(0x5576733F, MLCREATE), call(0x5576733F, MSCOST), 'Charge factory -> cost-3 wrapper'),
    (0x667A9, call(0x557673A9, MLCREATE), call(0x557673A9, MSCOST), 'Parry factory -> cost-3 wrapper'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    for off, orig, new, desc in PATCHES:
        cur = bytes(data[off:off+5])
        if cur == new:
            print(f'{desc}: already applied'); continue
        assert cur == orig, f'{desc}: expected {orig.hex()} got {cur.hex()}'
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    for off, orig, new, desc in PATCHES:
        data[off:off+5] = new
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
