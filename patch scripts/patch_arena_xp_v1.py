# -*- coding: utf-8 -*-
# Arena XP fix (2026-07-27, follows patch_arena_cost_v1):
# TArena.ExecuteTrainUnit called SetExperience(nextRankXP), but our modded SetExperience
# (cave 0x5580C200) turns absolute sets into level-scaled diminishing GAINS -> arena granted
# wrong XP amounts. Fix: unit branch now calls cave_arenaxp instead of [vtbl+0x160]:
#   xp = min(target, 20) written DIRECTLY to [unit+0x3C], then the SetExperience rank-up
#   loop is replicated (TAbilityOwner.UpdateDefaultAbilities per crossed rank, owner =
#   [resource + rank*4 + 0x38]). Caller's vtbl+0x90 Changed call still refreshes the unit.
# Hero branch untouched (heroes ineligible anyway). PIC: rel32 only.
import shutil, struct, os

FN = 'AoWEPACK.dll'
VA = 0x55700C00
GETRANK = 0x5578294C          # AoWE.TUnit.GetRank
UPDDEF  = 0x5574F518          # AoWE.TAbilityOwner.UpdateDefaultAbilities
HOOK = 0x557D67C5             # unit branch: call dword ptr [ecx+0x160]  (ff 91 60 01 00 00)
CAVE = 0x5580FF20

if not os.path.exists(FN + '.bak_arenaxp'):
    shutil.copyfile(FN, FN + '.bak_arenaxp')
d = bytearray(open(FN, 'rb').read())
def off(va): return va - VA
def rel(src, dst): return struct.pack('<i', dst - (src + 5))

orig = d[off(HOOK):off(HOOK)+6]
assert orig == bytes.fromhex('ff9160010000'), 'hook bytes unexpected: ' + orig.hex()
assert all(b == 0 for b in d[off(CAVE):off(CAVE)+64]), 'cave not empty'

c = bytearray()
c += bytes.fromhex('53')            # push ebx
c += bytes.fromhex('56')            # push esi
c += bytes.fromhex('89c6')          # mov esi, eax
c += bytes.fromhex('80fa14')        # cmp dl, 0x14
c += bytes.fromhex('7602')          # jbe +2
c += bytes.fromhex('b214')          # mov dl, 0x14        ; clamp target to 20 XP
c += bytes.fromhex('88d7')          # mov bh, dl          ; bh = target xp
c += bytes.fromhex('89f0')          # mov eax, esi
c += b'\xe8' + rel(CAVE + len(c), GETRANK)   # call GetRank ; al = old rank
c += bytes.fromhex('88c3')          # mov bl, al
c += bytes.fromhex('887e3c')        # mov [esi+0x3c], bh  ; xp = target (direct, unscaled)
c += bytes.fromhex('89f0')          # mov eax, esi
c += b'\xe8' + rel(CAVE + len(c), GETRANK)   # call GetRank ; al = new rank
c += bytes.fromhex('88c7')          # mov bh, al
L2 = len(c)
c += bytes.fromhex('38fb')          # cmp bl, bh
JAE = len(c)
c += bytes.fromhex('7300')          # jae done (patched below)
c += bytes.fromhex('fec3')          # inc bl
c += bytes.fromhex('0fb6c3')        # movzx eax, bl
c += bytes.fromhex('8b5640')        # mov edx, [esi+0x40]  ; unit resource
c += bytes.fromhex('8b548238')      # mov edx, [edx+eax*4+0x38] ; rank ability owner
c += bytes.fromhex('89f0')          # mov eax, esi
c += b'\xe8' + rel(CAVE + len(c), UPDDEF)    # call UpdateDefaultAbilities
JB = len(c)
c += bytes.fromhex('eb00')          # jmp L2 (patched below)
DONE = len(c)
c += bytes.fromhex('5e')            # pop esi
c += bytes.fromhex('5b')            # pop ebx
c += bytes.fromhex('c3')            # ret
c[JAE+1] = DONE - (JAE + 2)
c[JB+1] = (L2 - (JB + 2)) & 0xFF

d[off(CAVE):off(CAVE)+len(c)] = c
d[off(HOOK):off(HOOK)+6] = b'\xe8' + rel(HOOK, CAVE) + b'\x90'
open(FN, 'wb').write(d)
print('applied: cave %d bytes @0x%X, hook @0x%X (orig %s)' % (len(c), CAVE, HOOK, orig.hex()))
