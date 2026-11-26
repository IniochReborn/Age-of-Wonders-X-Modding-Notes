#!/usr/bin/env python3
"""
Wall Crushing preview fix (v1b) — AoWEPACK.dll  (applied 2026-07-20)
====================================================================
The tactical-combat preview showed ATK 6 / DMG 6 regardless of level.
Source: TWallCrushingAbility.GetCombatInfo (VMT+0x104 @0x557688A8) hardcodes
the record: [out+1]=ATK byte, [out+2]=DMG byte, [out+3]=types word,
[out+5]=range, [out]=flags — and ignores its EDX=unit param.

Fix: VMT+0x104 -> cave_wcinfo 0x5580EEF0 (32B): ATK 6 kept, DMG = 5*level via
cave_wclvl5s. Also levels the third combat estimator (+0xEC @0x55768832
`mov edx,6` -> call cave_wcestdmg — same frame layout as +0xE4).
REQUIRES: wallcrush-leveled patch. Revert: AoWEPACK.dll.bak_wallcrush_preview
Run: python patch_wallcrush_preview_v1.py --apply
"""
import struct, sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_wallcrush_preview'
DELTA = 0x55700C00
WCLVL5S, WCESTDMG = 0x5580EBC0, 0x5580EED0
INFO_OFF = 0x10E2F0
INFO_VA = INFO_OFF + DELTA
def call(src, dst): return b'\xE8' + struct.pack('<i', dst - (src + 5))

b = bytearray()
b += b'\x53\x8B\xD9\x8B\xC2'
b += call(INFO_VA+len(b), WCLVL5S)
b += b'\xC6\x43\x01\x06'            # ATK 6
b += b'\x88\x43\x02'                # DMG = 5*level
b += b'\x66\xC7\x43\x03\x00\x01'    # types 0x100
b += b'\xC6\x43\x05\x01'            # range 1
b += b'\xC6\x03\x00'                # flags 0
b += b'\x5B\xC3'
CAVE = bytes(b); assert len(CAVE) == 32

PATCHES = [
    (0x20818, struct.pack('<I',0x557688A8), struct.pack('<I',INFO_VA), 'VMT+0x104 -> cave_wcinfo'),
    (0x67C32, b'\xBA\x06\x00\x00\x00', call(0x55768832, WCESTDMG), '+0xEC est DMG -> 5*level'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    cave_cur = bytes(data[INFO_OFF:INFO_OFF+len(CAVE)])
    if cave_cur == CAVE and all(bytes(data[o:o+len(n)]) == n for o,_,n,_ in PATCHES):
        print('already applied'); return
    assert cave_cur == b'\x00'*len(CAVE)
    for off, orig, new, desc in PATCHES:
        assert bytes(data[off:off+len(orig)]) == orig, desc
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    data[INFO_OFF:INFO_OFF+len(CAVE)] = CAVE
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
