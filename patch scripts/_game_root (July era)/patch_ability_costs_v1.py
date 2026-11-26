#!/usr/bin/env python3
"""
Ability cost retune (v1) — AoWEPACK.dll
=======================================
- Hero Slaying (0x38): 10 -> 5 /level   (imms in our cave_hsreg)
- Monster Slaying (0x70): 10 -> 3 /level (new wrapper cave_mscost; cave_mlcreate
  is SHARED with Life Stealing/Charge/Parry which stay 10 — wrapper re-Puts 3s)
- Leadership: 10 -> 5 /level             (imm in our cave_lscosts loop)
- Turn Undead (0x26): 5 -> 3 /level      (vanilla ExpandCost imm AND
  GetSkillPoints x5 -> x3 — charge is the skillpoints DELTA, must match display)

ML abilities (HS/MS/Leadership) need no skillpoints change: ML GetSkillPoints
derives from the same cost list.

Run: python patch_ability_costs_v1.py [--apply]
Revert: restore AoWEPACK.dll.bak_ability_costs
"""
import struct, sys, shutil, os

DLL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK   = DLL + '.bak_ability_costs'
DELTA = 0x55700C00
MLCREATE = 0x5580E200
PUT      = 0x55702EB4
MSCOST_OFF = 0x10DF70          # new cave (zeros verified region)
MSCOST_VA  = MSCOST_OFF + DELTA

def rel32(src, dst): return struct.pack('<i', dst - (src + 5))
def call(src, dst): return b'\xE8' + rel32(src, dst)

# cave_mscost: passthrough to cave_mlcreate, then Put(list,1..3, 3)
b = bytearray()
b += call(MSCOST_VA + len(b), MLCREATE)
b += b'\x56\x8B\xF0'                      # push esi; mov esi,eax
for idx in (1, 2, 3):
    b += b'\x8B\x46\x2C'                  # mov eax,[esi+0x2C]
    b += b'\xBA' + struct.pack('<I', idx) # mov edx,idx
    b += b'\xB9\x03\x00\x00\x00'          # mov ecx,3
    b += call(MSCOST_VA + len(b), PUT)
b += b'\x8B\xC6\x5E\xC3'                  # mov eax,esi; pop esi; ret
CAVE_MSCOST = bytes(b)
assert len(CAVE_MSCOST) == 66, len(CAVE_MSCOST)

PATCHES = [
    # Leadership: cave_lscosts Put value (mov ecx,0xA imm @0x5580DFFD+1)
    (0x10D3FE, b'\x0a\x00\x00\x00', b'\x05\x00\x00\x00', 'Leadership cost 10->5'),
    # Hero Slaying: cave_hsreg three Puts (mov ecx,0xA imms)
    (0x10D750, b'\x0a\x00\x00\x00', b'\x05\x00\x00\x00', 'HS cost lvl1 10->5'),
    (0x10D762, b'\x0a\x00\x00\x00', b'\x05\x00\x00\x00', 'HS cost lvl2 10->5'),
    (0x10D774, b'\x0a\x00\x00\x00', b'\x05\x00\x00\x00', 'HS cost lvl3 10->5'),
    # Turn Undead: ExpandCost mov eax,5 imm @0x5576B0E6+1 ; GetSkillPoints x5->x3
    (0x6A4E7,  b'\x05\x00\x00\x00', b'\x03\x00\x00\x00', 'TU ExpandCost 5->3'),
    (0x6A531,  b'\x8d\x04\x80',     b'\x8d\x04\x40',     'TU GetSkillPoints x5->x3'),
    # Monster Slaying: retarget factory call to wrapper
    (0x66774, call(0x55767374, MLCREATE), call(0x55767374, MSCOST_VA),
     'MS 0x70 factory -> cave_mscost'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    ok = True
    if bytes(data[MSCOST_OFF:MSCOST_OFF+len(CAVE_MSCOST)]) != b'\x00'*len(CAVE_MSCOST):
        print('[!] cave_mscost region not zero'); ok = False
    for off, orig, new, desc in PATCHES:
        cur = bytes(data[off:off+len(orig)])
        if cur != orig:
            print(f'[!] {desc} @ {hex(off)}: expected {orig.hex()} got {cur.hex()}'); ok = False
        assert len(new) == len(orig)
    if not ok:
        print('ABORT'); sys.exit(1)
    print(f'Verified. cave_mscost @ file {hex(MSCOST_OFF)} VA {hex(MSCOST_VA)} len {len(CAVE_MSCOST)}')
    if not apply:
        print('DRY RUN ok — rerun with --apply'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print('backup ->', BAK)
    data[MSCOST_OFF:MSCOST_OFF+len(CAVE_MSCOST)] = CAVE_MSCOST
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
        print(f'  patched {desc} @ {hex(off)}')
    open(DLL, 'wb').write(data)
    print('APPLIED.')

if __name__ == '__main__':
    main()
