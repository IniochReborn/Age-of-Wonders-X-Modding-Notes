#!/usr/bin/env python3
"""
Post-gold HP cap + XP overflow fix (v1) — AoWEPACK.dll  (applied 2026-07-20)
============================================================================
Fixes runaway HP/medal-loss bug (e.g. "80/25 HP") and caps leveling HP.

Root cause chain (pre-Claude AoWx XP system):
- TUnit.GetMaxHP cave 0x5580BE15: MaxHP = baseHP + 2*(XP/10), uncapped.
- TUnit.SetExperience (0x557828B4) clamps its PROPOSED total to 100, but the
  XP-store cave (0x5580C200) recomputes gains and stores beyond 100; once
  stored XP > 100 the byte delta (proposed-current) wraps to garbage "victim
  levels" -> runaway XP -> XP byte wraps at 256 -> medals + MaxHP collapse
  while current HP stays high.

Fixes (all exact-length writes):
1. GetMaxHP cave REWRITTEN (57B into the 0x6B-byte region 0x10B215-0x10B27F):
   MaxHP = min(baseHP + 2*(XP/10), baseHP*(7-tier)/2)
   -> cap x3.0 / x2.5 / x2.0 / x1.5 for unit tiers 1/2/3/4.
2. SetExperience 100-clamp REMOVED (13 NOPs @0x81CC5: cmp edi,0x64/jle/mov):
   delta math now exact for any stored XP.
3. XP cave wrap-guard in the 6-byte dead slot @0x10B686 (was cmp al,0x14 + dead
   jmp): cmp al,cl; jae store; mov al,0xFA  -> new XP < old XP == overflow,
   pin at 250. XP is monotonic; MaxHP monotonic; medals never lost.

REQUIRES: xp-min1 patch (stub at 0x10B695 does the add al,cl).
Revert: restore AoWEPACK.dll.bak_hp_cap
Run: python patch_hp_cap_v1.py --apply
"""
import sys, shutil, os

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK = DLL + '.bak_hp_cap'

OLD_MAXHP = bytes.fromhex('538bd88bc3e82d6bf7ff83e07f8b53406bc00002422c5089d8'
                          'e8796af7ff31d2b90a000000f7f1d1e089c35801d85bc3')
NEW_MAXHP = bytes.fromhex(
    '5356' '8BD8' '8B5340' '0FB64A2C' '0FB6522F' 'BE07000000' '2BF2'
    '8BC1' '0FAFC6' 'D1E8' '8BF0' '0FB6433C' '33D2' 'BB0A000000' 'F7F3'
    '03C0' '03C1' '3BC6' '7E02' '8BC6' '5E5BC3')
REGION = 0x6B
CLAMP_OLD = bytes.fromhex('81ff640000007e05bf64000000')
SLOT_OLD = bytes.fromhex('3c14eb029090')
SLOT_NEW = bytes.fromhex('38C87302B0FA')

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    size0 = len(data)
    if bytes(data[0x10B215:0x10B215+len(NEW_MAXHP)]) == NEW_MAXHP:
        print('already applied'); return
    assert bytes(data[0x10B215:0x10B215+len(OLD_MAXHP)]) == OLD_MAXHP
    assert bytes(data[0x10B245:0x10B280]) == b'\x00'*0x3B
    assert bytes(data[0x81CC5:0x81CC5+13]) == CLAMP_OLD
    assert bytes(data[0x10B686:0x10B68C]) == SLOT_OLD
    if not apply:
        print('DRY RUN ok'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    blob = NEW_MAXHP + b'\x00'*(REGION - len(NEW_MAXHP))
    assert len(blob) == REGION
    data[0x10B215:0x10B215+REGION] = blob
    data[0x81CC5:0x81CC5+13] = b'\x90'*13
    data[0x10B686:0x10B68C] = SLOT_NEW
    assert len(data) == size0, 'file size changed — slice bug!'
    open(DLL, 'wb').write(data)
    print('APPLIED')

if __name__ == '__main__':
    main()
