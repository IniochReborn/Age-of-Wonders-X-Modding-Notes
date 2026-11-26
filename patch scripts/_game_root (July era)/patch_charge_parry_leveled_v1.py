#!/usr/bin/env python3
"""
Charge I/II/III (+2/+3/+4 DMG) & Parry I/II/III (-2/-3/-4 ATK) — AoWEPACK.dll
=============================================================================
Charge = ability 0x6F (initiating side's first melee strike, damage bonus).
Parry  = ability 0x71 (defender of each side's first strike, attack malus).
Vanilla values: tactical combat +2/-2, fast combat +3/-3 (inconsistent!).
This patch: both paths become level+1 (I=2, II=3, III=4). Legacy bare-bit
units = level I (+2/-2): unchanged in tactical, fast combat 3->2.

Conversion: factory swap to cave_mlcreate (0x5580E200, lifesteal-leveled
patch REQUIRED) -> TMultiLevelAbility, cap 3, cost 10/level, names
"Charge I/II/III" automatic via ML VMT+0x10C -> cave_lsnames. ML ExpandCost
and GetSkillPoints are consistent for flat cost lists (display == charge).

Run: python patch_charge_parry_leveled_v1.py [--apply]   (dry-run default)
Revert: restore AoWEPACK.dll.bak_charge_parry
"""
import struct, sys, shutil, os

DLL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK   = DLL + '.bak_charge_parry'
DELTA = 0x55700C00
MLCREATE = 0x5580E200

CAVES = {
    'chgmel': 0x10DEF0,   # tactical charge (combat units, +0xB0)
    'parmel': 0x10DF10,   # tactical parry
    'chgfast': 0x10DF30,  # fast-combat charge (strategic units, +0x144)
    'parfast': 0x10DF50,  # fast-combat parry
}
def VA(n): return CAVES[n] + DELTA
def rel32(src, dst): return struct.pack('<i', dst - (src + 5))
def call(src, dst): return b'\xE8' + rel32(src, dst)

def bonus_cave(aid, unit_reg, lvl_off, apply_bytes):
    """AL=HasAbility result in; if set, bonus = clamp(level,1..)+1 applied."""
    b = bytearray()
    b += b'\x84\xC0'                          # test al,al
    b += bytes([0x74, 24 + len(apply_bytes) - 3])  # jz .r (over the rest)
    b += b'\xBA' + struct.pack('<I', aid)     # mov edx,id
    b += unit_reg                             # mov eax,<esi|edi>
    b += b'\x8B\x08'                          # mov ecx,[eax]
    b += b'\xFF\x91' + struct.pack('<I', lvl_off)  # call [ecx+GetAbilityLevel]
    b += b'\x85\xC0\x75\x01\x40'              # test eax,eax; jnz+1; inc eax (min 1)
    b += b'\x40'                              # inc eax  (bonus = level+1)
    b += apply_bytes                          # add [ebx+4],eax / sub [ebx],eax
    b += b'\xC3'                              # .r: ret
    return bytes(b)

caves = {
    #                 id    unit reg (eax<-)  level slot   apply
    'chgmel':  bonus_cave(0x6F, b'\x8B\xC6', 0xB0,  b'\x01\x43\x04'),  # add [ebx+4],eax
    'parmel':  bonus_cave(0x71, b'\x8B\xC7', 0xB0,  b'\x29\x03'),      # sub [ebx],eax
    'chgfast': bonus_cave(0x6F, b'\x8B\xC6', 0x144, b'\x01\x43\x04'),
    'parfast': bonus_cave(0x71, b'\x8B\xC7', 0x144, b'\x29\x03'),
}
assert len(caves['chgmel']) == 29 and len(caves['parmel']) == 28

PATCHES = [
    # factory swaps in RegisterStrikeAbilities: TStrikeEnhancementAbility -> ML
    (0x6673F, call(0x5576733F, 0x5576727C), call(0x5576733F, MLCREATE),
     'Charge 0x6F factory -> cave_mlcreate'),
    (0x667A9, call(0x557673A9, 0x5576727C), call(0x557673A9, MLCREATE),
     'Parry 0x71 factory -> cave_mlcreate'),
    # tactical combat: TMeleeRound.CalculateStrikes
    (0x66FC6, bytes.fromhex('84c0740483430402'),
     call(0x55767BC6, VA('chgmel')) + b'\x90'*3, 'tactical charge +2 -> +lvl+1'),
    (0x66FDD, bytes.fromhex('84c07403832b02'),
     call(0x55767BDD, VA('parmel')) + b'\x90'*2, 'tactical parry -2 -> -lvl-1'),
    # fast combat: CalculateUnitStrikes
    (0x66C6E, bytes.fromhex('84c0740483430403'),
     call(0x5576786E, VA('chgfast')) + b'\x90'*3, 'fast charge +3 -> +lvl+1'),
    (0x66C85, bytes.fromhex('84c07403832b03'),
     call(0x55767885, VA('parfast')) + b'\x90'*2, 'fast parry -3 -> -lvl-1'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    ok = True
    for name, off in CAVES.items():
        blob = caves[name]
        if bytes(data[off:off+len(blob)]) != b'\x00'*len(blob):
            print(f'[!] cave {name} region not zero @ {hex(off)}'); ok = False
    for off, orig, new, desc in PATCHES:
        cur = bytes(data[off:off+len(orig)])
        if cur != orig:
            print(f'[!] {desc} @ {hex(off)}: expected {orig.hex()} got {cur.hex()}'); ok = False
        assert len(new) == len(orig), desc
    if not ok:
        print('ABORT'); sys.exit(1)
    print('All original bytes + cave zeros verified.')
    for n, off in sorted(CAVES.items(), key=lambda kv: kv[1]):
        print(f'  cave {n:8s} file {hex(off)} VA {hex(off+DELTA)} len {len(caves[n])}')
    if not apply:
        print('DRY RUN ok — rerun with --apply'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print('backup ->', BAK)
    for n, off in CAVES.items():
        data[off:off+len(caves[n])] = caves[n]
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
        print(f'  patched {desc} @ {hex(off)}')
    open(DLL, 'wb').write(data)
    print('APPLIED.')

if __name__ == '__main__':
    main()
