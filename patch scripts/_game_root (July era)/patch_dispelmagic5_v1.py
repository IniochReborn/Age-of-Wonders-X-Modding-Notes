#!/usr/bin/env python3
"""
Dispel Magic IV + V (AoWEPACK.dll, 2026-07-20). Vanilla cap is 3 (I-III), so
this adds TWO levels. No value ladders exist to patch: the level's entire
effect flows through GetDispelMana = level*10+20, which is both the casting
mana cost AND the dispel strength fed to TEnchantment.DispelChance (rolled vs
Random(100)) in ALL THREE paths (fcExecuteCombatCommand, CreateCA, strategic
TE - verified all call GetDispelMana). So:
  I 30   II 40   III 50   IV 60   V 70   (strength = mana cost)
ExpandCost is a flat 1 skill point (no cap logic) -> IV/V cost 1 each.
REQUIRES patch_inherent_level_fix_v1.py (DM VMT+0x94 -> own GetLevel), or
level purchases would be silently discarded by UpdateDefaultAbilities.

Patches:
 1. CanExpand `cmp eax,3` imm @0x5576D163 -> 5
 2. Expand `cmp byte [data+0xD],3` imm @0x5576D1D0 -> 5 (allows increment to 5)
 3. GetLevelName: the dec-chain's default path is ALREADY a 5-byte near jmp
    @0x5576CF61 (level>3 -> bare-name epilogue 0x5576CFF8) -> retarget to
    cave_dm5name. At that point EDX = level-3, EBX = out PAnsiString, frame
    locals [ebp-8]/[ebp-4] zeroed, SEH active. Cave: level 4 -> " IV"
    (Marksmanship literal 0x557BBF40), level 5 -> " V" (0x5576DE04), via
    LoadResString(DispelMagicRStr 0x55709AEC, PIC) + TranslateRStr + LStrCat3;
    else default.

Notes: level lives at TDispelMagicAbilityData+0xD (+0xC is the per-turn
enabled toggle); bare-record/no-record reads as level 1. DM id 0x3C.
Cave @0x5580E680 (file 0x10DA80, zeros verified). Dry-run default; --apply.
Backup: AoWEPACK.dll.bak_dispelmagic5
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_dispelmagic5"
FILE_DELTA = 0x55700C00

NEW_MAX  = 5
JMP_SITE = 0x5576CF61            # E9 92 00 00 00 (jmp 0x5576CFF8, default path)
NAME_DEF = 0x5576CFF8
DM_RSTR  = 0x55709AEC
LOADRES  = 0x55701210
TRANSL   = 0x557249FC
LSTRCAT3 = 0x55701190
LIT_IV   = 0x557BBF40
LIT_V    = 0x5576DE04

CAVE     = 0x5580E680            # file 0x10DA80
CAVE_LIMIT = 0x5580E740

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4,'little',signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4,'little',signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)

# cave_dm5name: EDX=level-3 (>=1), EBX=out, EBP frame; EAX/ECX free
a = Asm(CAVE)
a.db(0x4A)                          # dec edx            ; level-4
a.j8(0x74, 'fourth')                # jz fourth
a.db(0x4A)                          # dec edx            ; level-5
a.j8(0x74, 'fifth')                 # jz fifth
a.jmp32(NAME_DEF)                   # level > 5: bare name
a.label('fourth')
a.call(a.here()+5)                  # PIC anchor
_p = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_p)                # sub eax, link      ; delta
a.db(0x8D, 0x88); a.dd(LIT_IV)      # lea ecx, [eax+LIT_IV]
a.j8(0xEB, 'body')                  # jmp body
a.label('fifth')
a.call(a.here()+5)                  # PIC anchor
_p = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_p)                # sub eax, link
a.db(0x8D, 0x88); a.dd(LIT_V)       # lea ecx, [eax+LIT_V]
a.label('body')
a.db(0x51)                          # push ecx           ; literal runtime addr
a.db(0x05); a.dd(DM_RSTR)           # add eax, DM_RSTR   ; RStr runtime addr
a.db(0x8D, 0x55, 0xF8)              # lea edx, [ebp-8]
a.call(LOADRES)                     # LoadResString -> [ebp-8]
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]
a.db(0x8D, 0x55, 0xFC)              # lea edx, [ebp-4]
a.call(TRANSL)                      # TranslateRStr -> [ebp-4]
a.db(0x59)                          # pop ecx            ; literal
a.db(0x8B, 0x55, 0xFC)              # mov edx, [ebp-4]
a.db(0x8B, 0xC3)                    # mov eax, ebx       ; out
a.call(LSTRCAT3)                    # out := name + suffix
a.jmp32(NAME_DEF)                   # rejoin epilogue (finally clears locals)
cave = a.done()
assert CAVE + len(cave) <= CAVE_LIMIT, f"{len(cave)}B"

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE, bytes(len(cave)), cave, f"cave_dm5name @0x{CAVE:X} ({len(cave)}B)"),
    (0x5576D163, b"\x03", bytes([NEW_MAX]), "CanExpand cap 3 -> 5"),
    (0x5576D1D0, b"\x03", bytes([NEW_MAX]), "Expand increment cap 3 -> 5"),
    (JMP_SITE, b"\xE9"+rel32(JMP_SITE, NAME_DEF), b"\xE9"+rel32(JMP_SITE, CAVE),
     "GetLevelName default jmp -> cave_dm5name"),
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
    print("Dispel Magic I-V: strength/mana 30/40/50/60/70; cost 1 skill point/level")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
