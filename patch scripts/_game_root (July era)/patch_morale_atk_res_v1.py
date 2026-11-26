#!/usr/bin/env python3
"""
Morale debuffs ATK/RES instead of DEF/RES; Terrible = -3 (v1) - AoWEPACK.dll
============================================================================
Vanilla/AoWx: morale modifies DEFENSE and RESISTANCE via runtime-init tables at
0x558E83E0 (def) / 0x558E83D8 (res), indexed by morale level 0-4
(Terrible/Poor/Okay/Good/High). Effective values were ~[-2,-2,-1,0,0].

This patch (my own static tables, since the vanilla ones are runtime-filled):
- MYMORALE = [-3,-2,-1,0,0]  (Terrible -3, Poor -2, Okay -1, Good/High 0)
- ATTACK  gets MYMORALE (NEW - injected).
- RESIST  gets MYMORALE (was runtime table; Terrible now -3).
- DEFENSE morale removed (repointed to an all-zero table).
Applied to both TUnit and THero, EFFECTIVE getters only (inherent/base untouched,
matching where morale already lived). Levels from MoraleValueToMorale: morale
value <=20 -> L0, 21-40 -> L1, 41-60 -> L2, 61-80 -> L3, >80 -> L4.

Run: python patch_morale_atk_res_v1.py [--apply]   Revert: .bak_morale_atkres
"""
import struct, sys, shutil, os

DLL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK   = DLL + '.bak_morale_atkres'
DELTA = 0x55700C00
ATKWRAP  = 0x5580EFA0
GETMORALE= 0x5577F178

MYMORALE = 0x5580F0A0   # file 0x10E4A0
ZEROTAB  = 0x5580F0A5   # file 0x10E4A5
CAVE_ATK = 0x5580F0B0   # file 0x10E4B0  (unit effective-attack wrapper)
CAVE_HRO = 0x5580F100   # file 0x10E500  (hero attack jmp-hook; relocated for PIC-cave size)

def off(va): return va - DELTA
def rel(src, dst): return struct.pack('<i', dst - (src + 5))
def call(src, dst): return b'\xE8' + rel(src, dst)
def jmp(src, dst):  return b'\xE9' + rel(src, dst)
def d32(v): return struct.pack('<I', v)

# ---- caves (PIC: the MYMORALE lookup MUST be position-independent — a raw
#      absolute disp32 has no .reloc entry and reads garbage when the DLL is
#      rebased at runtime; RES/DEF repoints work because they inherit the
#      original instruction's .reloc). call/pop-delta -> [edx(delta)+eax(level)+MYMORALE] ----
b = bytearray()
b += call(CAVE_ATK+len(b), ATKWRAP)        # call cave_atkwrap -> al = attack
b += b'\x50'                                # push eax
b += b'\x8B\xC3'                            # mov eax,ebx (unit)
b += call(CAVE_ATK+len(b), GETMORALE)       # GetMorale -> eax=level
b += b'\x83\xE0\x7F'                        # and eax,0x7f
b += b'\xE8\x00\x00\x00\x00'                # call $+5
_pv = CAVE_ATK+len(b)
b += b'\x5A'                                # pop edx (runtime addr of this pop)
b += b'\x81\xEA' + d32(_pv)                 # sub edx, pop_link  -> edx = rebase delta
b += b'\x0F\xBE\x94\x02' + d32(MYMORALE)    # movsx edx, byte [edx+eax+MYMORALE_link]
b += b'\x58'                                # pop eax
b += b'\x02\xC2'                            # add al,dl
b += b'\xC3'                                # ret
CAVE_ATK_BYTES = bytes(b)

b = bytearray()
b += b'\x02\xC2'                            # add al,dl  (replayed original hook bytes)
b += b'\x50'                                # push eax
b += b'\x8B\xC5'                            # mov eax,ebp (hero)
b += call(CAVE_HRO+len(b), GETMORALE)       # GetMorale
b += b'\x83\xE0\x7F'                        # and eax,0x7f
b += b'\xE8\x00\x00\x00\x00'                # call $+5
_pv2 = CAVE_HRO+len(b)
b += b'\x5A'                                # pop edx
b += b'\x81\xEA' + d32(_pv2)                # sub edx, pop_link -> delta
b += b'\x0F\xBE\x94\x02' + d32(MYMORALE)    # movsx edx, byte [edx+eax+MYMORALE_link]
b += b'\x58'                                # pop eax
b += b'\x02\xC2'                            # add al,dl
b += b'\x88\x04\x24'                        # mov [esp],al  (store local; esp intact via jmp entry)
b += jmp(CAVE_HRO+len(b), 0x557883B6)       # back to clamp
CAVE_HRO_BYTES = bytes(b)

# ---- patches: (file_off, original, new, desc) ----
P = [
  (off(MYMORALE), b'\x00'*5, b'\xFD\xFE\xFF\x00\x00', 'MYMORALE table -3,-2,-1,0,0'),
  # (ZEROTAB stays 5 zero bytes - already zero, no write needed)
  (off(CAVE_ATK), b'\x00'*len(CAVE_ATK_BYTES), CAVE_ATK_BYTES, 'cave_atkmorale'),
  (off(CAVE_HRO), b'\x00'*len(CAVE_HRO_BYTES), CAVE_HRO_BYTES, 'cave_heroatk'),
  # RES morale table -> MYMORALE
  (off(0x55782AF7), d32(0x558E83D8), d32(MYMORALE), 'unit GetResistance morale -> MYMORALE'),
  (off(0x5578856D), d32(0x558E83D8), d32(MYMORALE), 'hero GetResistance morale -> MYMORALE'),
  # DEF morale table -> ZEROTAB (disable)
  (off(0x55782A6B), d32(0x558E83E0), d32(ZEROTAB), 'unit GetDefense morale -> 0'),
  (off(0x55788449), d32(0x558E83E0), d32(ZEROTAB), 'hero GetDefense morale -> 0'),
  # ATK: effective unit GetAttack call cave_atkwrap -> cave_atkmorale
  (off(0x55782A00), call(0x55782A00, ATKWRAP), call(0x55782A00, CAVE_ATK), 'unit eff GetAttack -> cave_atkmorale'),
  # ATK: hero GetAttack (add al,dl; mov[esp],al) -> jmp cave_heroatk
  (off(0x557883B1), b'\x02\xC2\x88\x04\x24', jmp(0x557883B1, CAVE_HRO), 'hero GetAttack -> cave_heroatk'),
]

def main():
    ap = '--apply' in sys.argv
    d = bytearray(open(DLL,'rb').read()); ok=True
    for o,orig,new,desc in P:
        cur=bytes(d[o:o+len(orig)])
        if cur!=orig:
            print(f'[!] {desc} @{hex(o)}: want {orig.hex()} got {cur.hex()}'); ok=False
        assert len(new)==len(orig), desc
    if not ok: print('ABORT'); sys.exit(1)
    print('verified. caves: atkmorale', len(CAVE_ATK_BYTES),'B, heroatk', len(CAVE_HRO_BYTES),'B')
    if not ap: print('DRY RUN ok'); return
    if not os.path.exists(BAK): shutil.copy2(DLL,BAK); print('backup ->',BAK)
    for o,orig,new,desc in P:
        d[o:o+len(new)]=new; print('  patched',desc)
    open(DLL,'wb').write(d); print('APPLIED')

if __name__=='__main__': main()
