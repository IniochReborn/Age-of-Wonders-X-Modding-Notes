#!/usr/bin/env python3
"""
Capped-medal victims grant 2x kill XP (v1) — AoWEPACK.dll  (applied 2026-07-20)
===============================================================================
Killing a unit that reached its HP cap (new medal type) grants twice the XP a
normal (gold-medal) unit of the same tier would.

Mechanism: DoDamage kill tail fetches victim level (combat vmt+0xA0). New cave
cave_victimxp sets bit 7 on the level when the victim is a capped TUnit
(hero/leader excluded via GetUnitType +0x114; cap test via cave_iscap). The
XP-store cave strips the flag early (cave_flag -> DH=1; DH is unused/preserved
through the gain math incl. `inc edx` medal adjust and `mul ah`) and the merge
cave doubles the computed gain (after the min-1 floor, before add to current).

Sites:
- 0x25F7F  (0x55726B7F): call [edx+0xA0]; and eax,0xFF (11B) -> call
  cave_victimxp 0x5580F000 (50B; preserves EBX=killer XP accum) + 6 NOP
- 0x10B619 (0x5580C219): 7B dead slot -> call cave_flag 0x5580EFC0 (10B) + 2 NOP
- 0x10B695 (0x5580C295): old min-1 stub -> jmp cave_merge2 0x5580EFD0 (19B:
  min-1; DH? gain*=2; add al,cl; jmp 0x5580C277)
REQUIRES: xp-min1, hp-cap, capfinetune (cave_iscap 0x5580EF60).
Revert: restore AoWEPACK.dll.bak_capxp2x
Run: python patch_capxp2x_v1.py [--apply]
"""
import struct, sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_capxp2x'
ISCAP, FLAG_VA, MERGE2_VA, VICXP_VA = 0x5580EF60, 0x5580EFC0, 0x5580EFD0, 0x5580F000
def call(src, dst): return b'\xE8' + struct.pack('<i', dst - (src + 5))
def jmp(src, dst): return b'\xE9' + struct.pack('<i', dst - (src + 5))

CAVE_FLAG = bytes.fromhex('84DB790580E37FB601C3')
CAVE_MERGE2 = bytes.fromhex('84C07502FEC084F6740202C000C8') + jmp(MERGE2_VA+14, 0x5580C277)
b = bytearray()
b += bytes.fromhex('8BC68B10FF92A000000025FF000000538B5E4C85DB741950'
                   '8BC38B10FF921401000084C058' '7409')
b += call(VICXP_VA+len(b), ISCAP)
b += bytes.fromhex('72020C805BC3')
CAVE_VICXP = bytes(b)

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read()); size0 = len(data)
    if bytes(data[0x10E400:0x10E400+len(CAVE_VICXP)]) == CAVE_VICXP:
        print('already applied'); return
    assert bytes(data[0x10B619:0x10B620]) == bytes.fromhex('80f914eb029090')
    assert bytes(data[0x10B695:0x10B6A0]) == bytes.fromhex('84c07502fec000c8ebd800')
    assert bytes(data[0x25F7F:0x25F8A]) == bytes.fromhex('ff92a000000025ff000000')
    assert bytes(data[0x10E3C0:0x10E440]) == b'\x00'*0x80
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    data[0x10E3C0:0x10E3C0+len(CAVE_FLAG)] = CAVE_FLAG
    data[0x10E3D0:0x10E3D0+len(CAVE_MERGE2)] = CAVE_MERGE2
    data[0x10E400:0x10E400+len(CAVE_VICXP)] = CAVE_VICXP
    data[0x10B619:0x10B620] = call(0x5580C219, FLAG_VA) + b'\x90'*2
    data[0x10B695:0x10B69A] = jmp(0x5580C295, MERGE2_VA)
    data[0x10B69A:0x10B6A0] = b'\x00'*6
    data[0x25F7F:0x25F8A] = call(0x55726B7F, VICXP_VA) + b'\x90'*6
    assert len(data) == size0
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
