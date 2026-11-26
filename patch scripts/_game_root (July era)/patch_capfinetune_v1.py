#!/usr/bin/env python3
"""
HP-cap fine-tune: min one level past gold + capped ATK/RES bonus (v1)
=====================================================================
AoWEPACK.dll, applied 2026-07-20. REQUIRES hp-cap + medal-icon patches.

- Effective HP cap = max(base*(7-tier)/2, base+6): every unit needs >=10 XP
  past gold (XP 30) before capping. Examples: base 7 tier4 -> 13 HP,
  base 10 tier4 -> 16 HP.
- Units at the cap get +1 ATK and +2 RES (strategic getters; combat routes
  through them) and show medal icon 8 (medal-icon patch).

Revert: restore AoWEPACK.dll.bak_capfinetune
Run: python patch_capfinetune_v1.py [--apply]
"""
import struct, sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_capfinetune'
ISCAP_VA, ATKW_VA, RESC_VA, D800 = 0x5580EF60, 0x5580EFA0, 0x5580EFB0, 0x5580D800
def call(src, dst): return b'\xE8' + struct.pack('<i', dst - (src + 5))

OLD_MAXHP = bytes.fromhex(
    '5356' '8BD8' '8B5340' '0FB64A2C' '0FB6522F' 'BE07000000' '2BF2'
    '8BC1' '0FAFC6' 'D1E8' '8BF0' '0FB6433C' '33D2' 'BB0A000000' 'F7F3'
    '03C0' '03C1' '3BC6' '7E02' '8BC6' '5E5BC3')          # hp-cap v2 (57B)
NEW_MAXHP = bytes.fromhex(
    '5356' '8BD8' '8B5340' '0FB64A2C' '0FB6522F' 'B807000000' '2BC2'
    '0FAFC1' 'D1E8' '8D5106' '3BC2' '7D02' '8BC2' '8BF0' '0FB6433C'
    '33D2' 'BB0A000000' 'F7F3' '03C0' '03C1' '3BC6' '7E02' '8BC6' '5E5BC3')
OLD_MED = bytes.fromhex('BA05000000EB05BA06000000')       # medal-icon v1 head
MED2 = (b'\xBA\x05\x00\x00\x00\xEB\x05\xBA\x06\x00\x00\x00'
        + call(0x5580EF10+12, ISCAP_VA) + b'\x72\x05\xBA\x08\x00\x00\x00\xC3')
ISCAP = (b'\x50\x51\x52\x8B\x53\x40\x0F\xB6\x4A\x2C\x0F\xB6\x52\x2F'
         b'\xB8\x07\x00\x00\x00\x2B\xC2\x0F\xAF\xC1\xD1\xE8'
         b'\x8D\x51\x06\x3B\xC2\x7D\x02\x8B\xC2\x50\x0F\xB6\x43\x3C'
         b'\x33\xD2\x57\xBF\x0A\x00\x00\x00\xF7\xF7\x5F\x03\xC0\x03\xC1'
         b'\x5A\x3B\xC2\x5A\x59\x58\xC3')
ATKW = call(ATKW_VA, D800) + call(ATKW_VA+5, ISCAP_VA) + b'\x72\x02\xFE\xC0\xC3'
RESC = b'\x02\x02' + call(RESC_VA+2, ISCAP_VA) + b'\x72\x02\x04\x02\x0F\xBE\xD0\xC3'

PATCHES = [
    (0x81DE4, bytes.fromhex('e817ae0800'), call(0x557829E4, ATKW_VA), 'inherent GetAttack -> atkwrap'),
    (0x81E00, bytes.fromhex('e8fbad0800'), call(0x55782A00, ATKW_VA), 'effective GetAttack -> atkwrap'),
    (0x81F18, bytes.fromhex('02020fbed0'), call(0x55782B18, RESC_VA), 'GetResistance tail -> rescap'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read()); size0 = len(data)
    if bytes(data[0x10E360:0x10E360+len(ISCAP)]) == ISCAP:
        print('already applied'); return
    assert bytes(data[0x10B215:0x10B215+len(OLD_MAXHP)]) == OLD_MAXHP
    assert bytes(data[0x10E310:0x10E310+len(OLD_MED)]) == OLD_MED
    assert bytes(data[0x10E35A:0x10E400]) == b'\x00'*(0x10E400-0x10E35A)
    for off, orig, new, desc in PATCHES:
        assert bytes(data[off:off+len(orig)]) == orig, desc
        assert len(new) == len(orig)
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    data[0x10B215:0x10B215+0x6B] = NEW_MAXHP + b'\x00'*(0x6B-len(NEW_MAXHP))
    data[0x10E310:0x10E310+74]   = MED2 + b'\x00'*(74-len(MED2))
    data[0x10E360:0x10E360+len(ISCAP)] = ISCAP
    data[0x10E3A0:0x10E3A0+len(ATKW)]  = ATKW
    data[0x10E3B0:0x10E3B0+len(RESC)]  = RESC
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
    assert len(data) == size0
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
