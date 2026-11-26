#!/usr/bin/env python3
"""
Hero Slaying + Monster Slaying apply to SHORT and MEDIUM range projectile
attacks, NOT long range (AoWEPACK.dll, 2026-07-20).
REQUIRES patch_hero_slaying_leveled_v1.py + patch_monster_slaying_leveled_v1.py.

Single hook (BXL's proven ranged-slayer site): the damage `push eax` inside
TRangedAttackAbility.CreateRangedAttackCA @0x5576EAE4 - the one builder every
projectile/breath shot goes through (called per shot from
TRangedAttackAbility.fcExecuteCombatCommand and TBreathAbility's). At the hook
@0x5576EB34: EAX=damage, EBX=ability, ESI=shooter (TCombatUnit),
[EBP-4]=target (TCombatUnit), [ESP]=already-pushed attack value.

Range gate: ability byte +0x28 (TRangedAttackAbility.GetRangeRA, shared by all
4 ranged VMTs - verified no overrides): 1=short, 2=medium, 3=long (mapped to
combat modes 3/4/5 by CombatRangeToCombatMode). Bonus only when +0x28 < 3.

Bonuses (attacker level each, min 1 for bare-bit; added to BOTH the pushed
attack and the damage):
  - Monster Slaying: shooter enabled(0x70) && target enabled(0x3F)
  - Hero Slaying:    shooter enabled(0x38) && target strategic IsClass(THero)
Note: breath attacks route through the same builder and are short/medium range,
so they get the bonus too. Autocombat DV estimators not hooked (same scope as
the melee patches).

PIC (THero classref via call/pop delta). Cave @0x5580E500 (file 0x10D900,
zeros verified). Dry-run default; --apply.
Backup: AoWEPACK.dll.bak_slayers_ranged
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_slayers_ranged"
FILE_DELTA = 0x55700C00

HS_ABIL = 0x38; MS_ABIL = 0x70; MARKER = 0x3F
RANGE_LONG = 3                    # +0x28 >= 3 -> no bonus

HOOK      = 0x5576EB34            # push eax (damage) in CreateRangedAttackCA
HOOK_ORIG = bytes.fromhex("508bc68b10")   # push eax; mov eax,esi; mov edx,[eax]
HOOK_CONT = 0x5576EB39
ISCLASS   = 0x557010C0
THERO_REF = 0x55711FAC

CAVE      = 0x5580E500            # file 0x10D900
CAVE_LIMIT= 0x5580E640            # file 0x10DA40

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []; self.fix32 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4,'little',signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4,'little',signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def jcc32(self, op2, lab):        # near jcc: 0F <op2> rel32 to label
        self.db(0x0F, op2); self.fix32.append((len(self.buf), lab)); self.buf += b'\0\0\0\0'
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab]-(self.base+off+4)).to_bytes(4,'little',signed=True)
        return bytes(self.buf)

a = Asm(CAVE)
a.db(0x80, 0x7B, 0x28, RANGE_LONG)  # cmp byte [ebx+0x28], 3   ; range
a.jcc32(0x8D, 'out')                # jge out (near; long range: no bonus)
a.db(0x57)                          # push edi
a.db(0x8B, 0xF8)                    # mov edi, eax             ; edi = damage
# ---- Monster Slaying: shooter 0x70 + target 0x3F --------------------------
a.db(0xBA, MS_ABIL,0,0,0)           # mov edx, 0x70
a.db(0x8B, 0xC6)                    # mov eax, esi             ; shooter
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xA8,0,0,0)        # call [ecx+0xA8]
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'hs')                    # jz hs
a.db(0xBA, MARKER,0,0,0)            # mov edx, 0x3F
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]         ; target
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xA8,0,0,0)        # call [ecx+0xA8]
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'hs')                    # jz hs
a.db(0xBA, MS_ABIL,0,0,0)           # mov edx, 0x70
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xB0,0,0,0)        # call [ecx+0xB0]          ; level (post-gate safe)
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x75, 'ms_have')               # jnz
a.db(0x40)                          # inc eax                  ; min 1
a.label('ms_have')
a.db(0x03, 0xF8)                    # add edi, eax             ; damage += lvl
a.db(0x01, 0x44, 0x24, 0x04)        # add [esp+4], eax         ; attack += lvl (+4: pushed edi)
# ---- Hero Slaying: shooter 0x38 + target strategic THero -------------------
a.label('hs')
a.db(0xBA, HS_ABIL,0,0,0)           # mov edx, 0x38
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xA8,0,0,0)        # call [ecx+0xA8]
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'done')                  # jz done
a.call(a.here()+5)                  # PIC anchor
_pop = a.here()
a.db(0x5A)                          # pop edx
a.db(0x81, 0xEA); a.dd(_pop)        # sub edx, link
a.db(0x8B, 0x92); a.dd(THERO_REF)   # mov edx, [edx+THeroRef]
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]         ; target
a.db(0x8B, 0x40, 0x4C)              # mov eax, [eax+0x4C]      ; strategic unit
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'done')                  # jz done
a.call(ISCLASS)                     # al = is THero (covers TLeader)
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'done')                  # jz done
a.db(0xBA, HS_ABIL,0,0,0)           # mov edx, 0x38
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xB0,0,0,0)        # call [ecx+0xB0]
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x75, 'hs_have')               # jnz
a.db(0x40)                          # inc eax
a.label('hs_have')
a.db(0x03, 0xF8)                    # add edi, eax
a.db(0x01, 0x44, 0x24, 0x04)        # add [esp+4], eax
a.label('done')
a.db(0x8B, 0xC7)                    # mov eax, edi             ; modified damage
a.db(0x5F)                          # pop edi
a.label('out')
a.db(0x50)                          # replay: push eax (damage)
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.jmp32(HOOK_CONT)
cave = a.done()
assert CAVE + len(cave) <= CAVE_LIMIT, f"cave {len(cave)}B"

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE, bytes(len(cave)), cave, f"cave_rngslay @0x{CAVE:X} ({len(cave)}B)"),
    (HOOK, HOOK_ORIG, b"\xE9"+rel32(HOOK, CAVE),
     "CreateRangedAttackCA damage-push -> cave_rngslay"),
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
    print("Slayer bonuses on short/medium-range shots (ability byte +0x28 < 3); long range excluded")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
