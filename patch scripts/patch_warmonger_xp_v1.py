# -*- coding: utf-8 -*-
# Warmonger XP fix (2026-07-27, requires patch_arena_xp_v1 — reuses cave_arenaxp @0x5580FF20):
# Vanilla: CreateUnitProduction (city flag [city+0x5C] bit3 = Warmonger) -> SetRank(unit,1)
# -> SetExperience(10); modded SetExperience scales the delta (fresh unit got ~27 XP: too much).
# Fix: dl=1 -> dl=0x14 and SetRank call -> cave_warmonger: cave_arenaxp (direct xp write to 20,
# clamps, grants Silver+Gold medal abilities) then TUnit.Changed via vtbl+0x90 (SetExperience
# used to do this). Produced units now spawn at exactly 20 XP = Gold. PIC (rel32 only).
import shutil, struct, os

FN = 'AoWEPACK.dll'
VA = 0x55700C00
CAVE_ARENAXP = 0x5580FF20
MOVDL = 0x557A8DBA            # b2 01        mov dl,1
CALLR = 0x557A8DBE            # e8 ...       call TUnit.SetRank (0x55782978)
CAVE = 0x5580FF60

if not os.path.exists(FN + '.bak_warmonger'):
    shutil.copyfile(FN, FN + '.bak_warmonger')
d = bytearray(open(FN, 'rb').read())
def off(va): return va - VA
def rel(src, dst): return struct.pack('<i', dst - (src + 5))

assert d[off(MOVDL):off(MOVDL)+2] == bytes.fromhex('b201'), 'mov dl,1 not found'
assert d[off(CALLR):off(CALLR)+5] == b'\xe8' + rel(CALLR, 0x55782978), 'SetRank call not found'
assert all(b == 0 for b in d[off(CAVE):off(CAVE)+24]), 'cave not empty'

c = bytearray()
c += b'\xe8' + rel(CAVE + len(c), CAVE_ARENAXP)  # call cave_arenaxp (eax=unit, dl=0x14; preserves esi)
c += bytes.fromhex('89f0')                       # mov eax, esi     ; unit (caller's esi)
c += bytes.fromhex('8b10')                       # mov edx, [eax]
c += bytes.fromhex('ff9290000000')               # call [edx+0x90]  ; TUnit.Changed
c += bytes.fromhex('c3')                         # ret

d[off(CAVE):off(CAVE)+len(c)] = c
d[off(MOVDL)+1] = 0x14                           # mov dl, 0x14 (target 20 XP)
d[off(CALLR):off(CALLR)+5] = b'\xe8' + rel(CALLR, CAVE)
open(FN, 'wb').write(d)
print('applied: cave %d bytes @0x%X; Warmonger units now spawn at 20 XP (Gold)' % (len(c), CAVE))
