#!/usr/bin/env python3
"""
Monster Slaying (0x70) becomes a 3-level ability: I/II/III = +1/+1, +2/+2,
+3/+3 ATK/DMG vs monster-marked (0x3F) targets (AoWEPACK.dll, 2026-07-20).
REQUIRES patch_lifesteal_leveled_v1.py (reuses its generic cave_mlcreate
@0x5580E200 for the ML construction and cave_lsnames for " I/II/III" names)
and patch_hero_slaying_leveled_v1.py context (its caves sit at the same two
melee blocks' heads; this patch touches only the blocks' add-tails - disjoint).

 A. FLYWEIGHT - repoint 0x70's factory call @0x55767374 (RegisterStrikeAbilities,
    `mov eax,0x70; call SUB_5576727C`) -> cave_mlcreate: TMultiLevelAbility,
    cap 3, cost 10/level; translated name + icon word 0x209 pass through.
 B. LEVELED BONUS - both melee Monster blocks end in flat +3/+3 adds; replace
    with call-caves that add the attacker's ability level instead:
    - CreateStrikeCA tail @0x557666C7 (8B: add bl,3 / add byte [esp+3],3)
      -> call cave_msmelee + 3 NOP  (EBP=attacker; dmg acc at [esp+7] inside
      the call because of the pushed return address)
    - CalculateStrikes tail @0x55767C82 (7B: add [ebx],3 / add [ebx+4],3)
      -> call cave_msmelee2 + 2 NOP (ESI=attacker)
    GetAbilityLevel (+0xB0) is safe here: the block's own +0xA8 enabled gate
    already passed => [attacker+0x4C] non-null. Level 0 (bare-bit legacy
    data) => min 1.

BALANCE NOTE: vanilla flat +3/+3 becomes +1/+1 for every legacy possessor
(bare enabled bit, no level record) until units are re-authored in DevEd with
Monster Slaying III. The autocombat/DV slayer copy (fcGetDamageValue fn) is
NOT hooked (same scope as Hero Slaying) - fast combat still values it flat +3.
Known side effect (verified inert): TStrikeAbility.Remove's sweep of
strike-enhancements on melee loss no longer matches the converted ability.

Dry-run default; --apply. Backup: AoWEPACK.dll.bak_monster_slaying_lvl
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_monster_slaying_lvl"
FILE_DELTA = 0x55700C00

MS_ABIL   = 0x70
CAVE_MLCREATE = 0x5580E200       # from lifesteal-leveled patch (cap 3, cost 10)
OLD_FACTORY   = 0x5576727C
FACT_CALL     = 0x55767374       # call factory for 0x70 (verified)

ADDS1_INJ  = 0x557666C7          # CreateStrikeCA: add bl,3 / add [esp+3],3
ADDS1_ORIG = bytes.fromhex("80c30380442403 03".replace(" ",""))
ADDS2_INJ  = 0x55767C82          # CalculateStrikes: add [ebx],3 / add [ebx+4],3
ADDS2_ORIG = bytes.fromhex("83030383430403")

CAVE_MS1 = 0x5580E470            # file 0x10D870 (zeros verified)
CAVE_MS2 = 0x5580E4A0
CAVE_LIMIT = 0x5580E500          # file 0x10D900

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)

# cave_msmelee (called from CreateStrikeCA tail; EBP=attacker, BL=atk acc,
# dmg acc at [esp+7] = [esp+3] displaced by the 4-byte return address)
a = Asm(CAVE_MS1)
a.db(0xBA, MS_ABIL,0,0,0)           # mov edx, 0x70
a.db(0x8B, 0xC5)                    # mov eax, ebp
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xB0,0,0,0)        # call [ecx+0xB0]  ; GetAbilityLevel
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x75, 'have')                  # jnz have
a.db(0x40)                          # inc eax          ; bare-bit -> level 1
a.label('have')
a.db(0x02, 0xD8)                    # add bl, al
a.db(0x00, 0x44, 0x24, 0x07)        # add [esp+7], al  ; dmg acc (+4 ret addr)
a.db(0xC3)                          # ret
cave_ms1 = a.done()
assert CAVE_MS1 + len(cave_ms1) <= CAVE_MS2

# cave_msmelee2 (called from CalculateStrikes tail; ESI=attacker, EBX=record)
a = Asm(CAVE_MS2)
a.db(0xBA, MS_ABIL,0,0,0)           # mov edx, 0x70
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xB0,0,0,0)        # call [ecx+0xB0]
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x75, 'have')                  # jnz have
a.db(0x40)                          # inc eax
a.label('have')
a.db(0x01, 0x03)                    # add [ebx], eax
a.db(0x01, 0x43, 0x04)              # add [ebx+4], eax
a.db(0xC3)                          # ret
cave_ms2 = a.done()
assert CAVE_MS2 + len(cave_ms2) <= CAVE_LIMIT

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE_MS1, bytes(len(cave_ms1)), cave_ms1, f"cave_msmelee @0x{CAVE_MS1:X} ({len(cave_ms1)}B)"),
    (CAVE_MS2, bytes(len(cave_ms2)), cave_ms2, f"cave_msmelee2 @0x{CAVE_MS2:X} ({len(cave_ms2)}B)"),
    (FACT_CALL, b"\xE8"+rel32(FACT_CALL, OLD_FACTORY), b"\xE8"+rel32(FACT_CALL, CAVE_MLCREATE),
     "0x70 factory -> cave_mlcreate (ML, cap 3, cost 10/lvl)"),
    (ADDS1_INJ, ADDS1_ORIG, b"\xE8"+rel32(ADDS1_INJ, CAVE_MS1)+b"\x90"*3,
     "CreateStrikeCA +3/+3 tail -> call cave_msmelee (+lvl/+lvl)"),
    (ADDS2_INJ, ADDS2_ORIG, b"\xE8"+rel32(ADDS2_INJ, CAVE_MS2)+b"\x90"*2,
     "CalculateStrikes +3/+3 tail -> call cave_msmelee2 (+lvl/+lvl)"),
]

data = bytearray(open(DLL, 'rb').read())
ok = True; applied = 0
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    cur = bytes(data[off:off+len(orig)])
    if cur == new: applied += 1
    elif cur != orig:
        print(f"MISMATCH @0x{va:X} ({desc}):\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok = False
if applied == len(patches):
    print("ALL ALREADY PATCHED"); sys.exit(0)
if not ok:
    print("Aborting."); sys.exit(1)
if '--apply' not in sys.argv:
    print("Monster Slaying I/II/III: +1/+1, +2/+2, +3/+3 vs monsters; cost 10/level")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
