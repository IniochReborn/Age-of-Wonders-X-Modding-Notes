#!/usr/bin/env python3
"""
Capture XP cap: seduce/charm/dominate captures grant only 1 XP (v1) — AoWEPACK.dll
==================================================================================
Applied & confirmed working in-game 2026-07-20 (units AND heroes, tactical + autocombat).

MP anti-exploit: previously, capturing a unit via seduce/charm/dominate granted the
captor the SAME XP as a kill, so players farmed XP by capturing -> disbanding ->
recapturing the same unit. This caps every capture to +1 XP regardless of the
captured unit/hero level. Normal kills are untouched.

WHY IT WAS HARD (recorded so nobody re-treads it):
- Kills and captures use DIFFERENT XP code paths. Kills go through the two
  "defeat handler" sites (tactical 0x55726b7f, autocombat 0x5572a00c) that call
  cave_victimxp directly. CAPTURES instead go through a THIRD, battle-log result
  path: two callers (0x557f8473, 0x5576fcb8) -> thunk 0x5580f050 -> cave_victimxp.
- The capture is identified by the captured unit's OWNER byte [+0x1c] now matching
  the captor's (a seduce/charm/dominate makes the enemy join your side; a normal
  kill leaves them enemy). [+0x1c] is the owner/player index on the battle unit
  (NOT [+0x24], which is a shared/constant field — an early wrong guess).
- XP write is GET-MODIFY-SET: ebx = GetXP([killer+0x98]) ; add cave return ;
  edx = ebx ; SetXP([killer+0x9c], edx). So the cave's return value is the GAIN
  added to current XP. THE HERO TRAP: THero SetXP -> hero cave 0x5580BE80 computes
  delta = edx - currentXP[+0x48]; if delta <= 0 it DIRECT-STORES edx as the new
  absolute XP. An earlier attempt forced the gain to (4 - ebx) which, for a
  high-XP hero, is a huge NEGATIVE -> corrupted a L4 hero to ~ -6000 XP / level 1.
  FIX: return a small POSITIVE CONSTANT (+1). total = currentXP + 1, delta = 1,
  hero cave adds exactly 1. Impossible to go negative -> hero-safe.

The two caves differ only in where the killer sits on the stack when the cave is
entered (caller A stored killer at its [esp] -> [esp+4] after our call; caller B
at [esp+4] -> [esp+8]).

Layout in the AoWEPACK cave block:
  cave_p3a @ 0x5580F160 (file 0x10E560) — for caller 0x557f8473 (killer @ [esp+4])
  cave_p3b @ 0x5580F190 (file 0x10E590) — for caller 0x5576fcb8 (killer @ [esp+8])
Each: mov ecx,[esp+disp]; mov al,[edi+0x1c]; cmp al,[ecx+0x1c];
      jne .normal; xor eax,eax; inc eax; ret          ; CAPTURE -> gain +1
      .normal: push esi; mov esi,edi; call cave_victimxp(0x5580F060); pop esi; ret

Revert: restore AoWEPACK.dll.bak_capturexp  (clean pre-feature state)
Run: python patch_capture_xp_cap_v1.py [--apply]
"""
import sys, os, struct

DLL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
DELTA = 0x55700C00
VICXP = 0x5580F060
THUNK = 0x5580F050
P3A, P3B = 0x5580F160, 0x5580F190
CALLERS = [(0x557F8473, P3A, 0x04), (0x5576FCB8, P3B, 0x08)]

def foff(va): return va - DELTA
def rel(src, dst): return struct.pack('<i', dst - (src + 5))

def build(addr, disp):
    b = bytearray()
    b += bytes((0x8B, 0x4C, 0x24, disp))    # mov ecx,[esp+disp]   killer
    b += b'\x8A\x47\x1C\x3A\x41\x1C'        # mov al,[edi+0x1c]; cmp al,[ecx+0x1c]
    b += b'\x75\x04'                        # jne .normal
    b += b'\x31\xC0\x40\xC3'                # CAPTURE: xor eax,eax; inc eax; ret  (gain +1)
    b += b'\x56\x8B\xF7'                    # .normal: push esi; mov esi,edi
    b += b'\xE8' + rel(addr + len(b), VICXP)# call cave_victimxp
    b += b'\x5E\xC3'                        # pop esi; ret
    return bytes(b)

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    assert len(data) == 2785792, len(data)
    # detect already-applied
    o = foff(CALLERS[0][0])
    already = ((CALLERS[0][0] + 5) + struct.unpack('<i', data[o+1:o+5])[0]) == P3A
    print('status:', 'ALREADY APPLIED' if already else 'not applied')
    if already:
        return
    # callers must currently point at the thunk (clean state)
    for site, dst, disp in CALLERS:
        o = foff(site); assert data[o] == 0xE8, hex(site)
        cur = (site + 5) + struct.unpack('<i', data[o+1:o+5])[0]
        assert cur == THUNK, f'{hex(site)} -> {hex(cur)} (expected thunk); wrong base state'
    if not apply:
        print('DRY RUN ok — pass --apply to write'); return
    for addr, disp in ((P3A, 0x04), (P3B, 0x08)):
        c = build(addr, disp)
        assert data[foff(addr):foff(addr)+len(c)] == b'\x00'*len(c), f'{hex(addr)} not free'
        data[foff(addr):foff(addr)+len(c)] = c
    for site, dst, disp in CALLERS:
        o = foff(site); data[o+1:o+5] = rel(site, dst)
    assert len(data) == 2785792
    open(DLL, 'wb').write(data)
    print('APPLIED: captures (owner [+0x1c] match) -> +1 XP; kills untouched')

if __name__ == '__main__':
    main()
