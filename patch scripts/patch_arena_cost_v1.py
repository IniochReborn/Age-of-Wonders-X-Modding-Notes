# -*- coding: utf-8 -*-
# Arena train cost rework (2026-07-27):
#   vanilla: cost = 5 * (nextRankXP - currentXP); heroes & gold-medal units already -1 (ineligible)
#   new:     cost = (nextRankXP - currentXP) * unitLevel * (1 if silver-bound else 2 if gold-bound)
# Hook: TArena.UnitTrainCost @0x557D6755 `lea eax,[esi+esi*4]; jmp short +8` (5 bytes) -> jmp cave.
# Cave @0x5580FF00 (PIC: rel32 calls/jmps only, no absolutes -> rebase-safe).
# esi = xp diff (callee-saved through both getters), ebx = unit.
import shutil, struct, os

FN = 'AoWEPACK.dll'
VA = 0x55700C00
GETRANK = 0x5578294C     # AoWE.TUnit.GetRank   (al = 0/1/2)
GETLVL  = 0x55782B8C     # AoWE.TUnit.GetUnitLevel (al = level; upper eax garbage!)
HOOK = 0x557D6755
BACK = 0x557D6762
CAVE = 0x5580FF00

if not os.path.exists(FN + '.bak_arena'):
    shutil.copyfile(FN, FN + '.bak_arena')
d = bytearray(open(FN, 'rb').read())
def off(va): return va - VA
def rel(src, dst): return struct.pack('<i', dst - (src + 5))

orig = d[off(HOOK):off(HOOK)+5]
assert orig == bytes.fromhex('8d04b6eb08'), 'hook bytes unexpected: ' + orig.hex()
assert all(b == 0 for b in d[off(CAVE):off(CAVE)+48]), 'cave not empty'

cave = bytearray()
cave += bytes.fromhex('89d8')                      # mov eax, ebx
cave += b'\xe8' + rel(CAVE + len(cave), GETRANK)   # call GetRank
cave += bytes.fromhex('0fb6c8')                    # movzx ecx, al
cave += bytes.fromhex('41')                        # inc ecx          ; 1 (silver-bound) / 2 (gold-bound)
cave += bytes.fromhex('89d8')                      # mov eax, ebx
cave += b'\xe8' + rel(CAVE + len(cave), GETLVL)    # call GetUnitLevel
cave += bytes.fromhex('0fb6c0')                    # movzx eax, al    ; unit level
cave += bytes.fromhex('0fafc1')                    # imul eax, ecx    ; level * mult
cave += bytes.fromhex('0fafc6')                    # imul eax, esi    ; * xp-to-next-rank
cave += b'\xe9' + rel(CAVE + len(cave), BACK)      # jmp back (pop esi/pop ebx/ret)

d[off(CAVE):off(CAVE)+len(cave)] = cave
d[off(HOOK):off(HOOK)+5] = b'\xe9' + rel(HOOK, CAVE)
open(FN, 'wb').write(d)
print('applied: cave %d bytes @0x%X, hook @0x%X (orig %s)' % (len(cave), CAVE, HOOK, orig.hex()))
