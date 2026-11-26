#!/usr/bin/env python3
"""
Turn Undead V (AoWEPACK.dll, 2026-07-20). Levels I-IV unchanged; new level V.
Actual curve in our build (verified vanilla, dll==dpl):
  I 6/4   II 7/5   III 8/6   IV 9/7   V 10/10   (touch ATK / DMG; V dmg re-tuned 8->10 2026-07-20)
Cost: flat 5 skill points/level (vanilla ExpandCost returns 5; GetSkillPoints =
5*level) - level V costs 5 automatically.

Turn Undead is NOT TMultiLevelAbility-based (TTurnUndeadAbility : TTouchAbility
: TAbility) - it implements its own level machinery with hardcoded 4s, so the
cap raise is three one-byte immediates:
 1. ExpandCost  `cmp eax,4`        imm @0x5576B0E3 -> 5
 2. CanExpand   `cmp eax,4`        imm @0x5576B11B -> 5
 3. Expand      `cmp [data+0xC],4` imm @0x5576B18C -> 5 (allows increment to 5)
 4. ATK ladder  GetTouchAttack @0x5576B1F4 (29B, EDX=level, dec-edx chain
    6/7/8/9 else 4) -> rewritten in place: level 1..5 -> level+5, else 4.
 5. DMG ladder  GetTurnUndeadDamage @0x5576B214 (29B, 4/5/6/7 else 0)
    -> rewritten: level 1..4 -> level+3, level 5 -> 10, else 0.
 6. NAME - GetLevelName jump table (levels 0-4) guarded by `cmp edx,4; ja
    default` @0x5576AF57 -> retargeted to cave_tu5name: level==5 renders
    "Turn Undead V" (LoadResString(TurnUndeadRStr @0x557078D4, PIC immediate)
    -> TranslateRStr -> LStrCat3 " V" @0x5576DE04) using the fn frame's
    locals; else jmp default @0x5576B036. Same shape as Marksmanship V's cave.

Info card / AI estimators call the two getters with the level -> consistent
automatically. No legacy-level concern: TU data records are TMultiLevelAbility-
Data and vanilla units already carry proper levels.

Cave @0x5580E640 (file 0x10DA40, zeros verified). Dry-run default; --apply.
Backup: AoWEPACK.dll.bak_turnundead5
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_turnundead5"
FILE_DELTA = 0x55700C00

NEW_MAX  = 5
JA_SITE  = 0x5576AF57            # 0F 87 rel32 at +3 after cmp edx,4
JA_DEF   = 0x5576B036
TU_RSTR  = 0x557078D4            # RStr record address (immediate w/ reloc in vanilla)
LOADRES  = 0x55701210
TRANSL   = 0x557249FC
LSTRCAT3 = 0x55701190
LIT_V    = 0x5576DE04

ATK_SITE = 0x5576B1F4
ATK_ORIG = bytes.fromhex("4a740b4a740b4a740b4a740beb0cb006c3b007c3b008c3b009c3b004c3")
DMG_SITE = 0x5576B214
DMG_ORIG = bytes.fromhex("4a740b4a740b4a740b4a740beb0cb004c3b005c3b006c3b007c333c0c3")

CAVE     = 0x5580E640            # file 0x10DA40
CAVE_LIMIT = 0x5580E700

def ladder(base_add, default_bytes):
    # test edx,edx; jle def; cmp edx,5; jg def; mov al,dl; add al,N; ret; def: ...; ret
    b = bytearray()
    b += bytes.fromhex("85d2")          # test edx,edx
    b += bytes([0x7E, 0])               # jle def (patched)
    b += bytes([0x83, 0xFA, NEW_MAX])   # cmp edx,5
    b += bytes([0x7F, 0])               # jg def (patched)
    b += bytes.fromhex("8ac2")          # mov al,dl
    b += bytes([0x04, base_add])        # add al,N
    b += b"\xC3"                        # ret
    deflt = len(b)
    b += default_bytes + b"\xC3"
    b[3] = deflt - 4                    # jle rel
    b[8] = deflt - 9                    # jg rel
    b += b"\x00" * (len(ATK_ORIG) - len(b))
    return bytes(b)

atk_new = ladder(5, bytes.fromhex("b004"))      # default: mov al,4
# DMG (v2, user re-tune 2026-07-20): I-IV = level+3 (4/5/6/7), V = 10 special-cased
dmg_new = bytes.fromhex("85d27e0f83fa057f0a74058ac20403c3b00ac333c0c3") + b"\x00"*7
# test edx,edx; jle def; cmp edx,5; jg def; jz five; mov al,dl; add al,3; ret
# five: mov al,10; ret;  def: xor eax,eax; ret
assert len(atk_new) == len(ATK_ORIG) and len(dmg_new) == len(DMG_ORIG)

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

# cave_tu5name: EDX=level(>4), EBX=out, EBP=fn frame (locals zeroed, SEH active)
a = Asm(CAVE)
a.db(0x83, 0xFA, NEW_MAX)           # cmp edx, 5
a.j8(0x75, 'def')                   # jnz default
a.call(a.here()+5)                  # PIC anchor
_pop = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_pop)              # sub eax, link      ; eax = load delta
a.db(0x50)                          # push eax           ; save delta
a.db(0x05); a.dd(TU_RSTR)           # add eax, TU_RSTR   ; runtime RStr record addr
a.db(0x8D, 0x55, 0xF8)              # lea edx, [ebp-8]
a.call(LOADRES)                     # LoadResString -> [ebp-8]
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]
a.db(0x8D, 0x55, 0xFC)              # lea edx, [ebp-4]
a.call(TRANSL)                      # TranslateRStr -> [ebp-4] = "Turn Undead"
a.db(0x59)                          # pop ecx            ; delta
a.db(0x81, 0xC1); a.dd(LIT_V)       # add ecx, LIT_V     ; " V" literal addr
a.db(0x8B, 0x55, 0xFC)              # mov edx, [ebp-4]
a.db(0x8B, 0xC3)                    # mov eax, ebx       ; out
a.call(LSTRCAT3)                    # out := name + " V"
a.label('def')
a.jmp32(JA_DEF)                     # rejoin epilogue (finally clears locals)
cave = a.done()
assert CAVE + len(cave) <= CAVE_LIMIT

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE, bytes(len(cave)), cave, f"cave_tu5name @0x{CAVE:X} ({len(cave)}B)"),
    (0x5576B0E3, b"\x04", bytes([NEW_MAX]), "ExpandCost cap 4 -> 5"),
    (0x5576B11B, b"\x04", bytes([NEW_MAX]), "CanExpand cap 4 -> 5"),
    (0x5576B18C, b"\x04", bytes([NEW_MAX]), "Expand increment cap 4 -> 5"),
    (ATK_SITE, ATK_ORIG, atk_new, "GetTouchAttack: ladder -> level+5 (V=10 ATK)"),
    (DMG_SITE, DMG_ORIG, dmg_new, "GetTurnUndeadDamage: ladder -> level+3, V=10 DMG"),
    (JA_SITE, bytes.fromhex("0f87")+struct.pack("<i", JA_DEF-(JA_SITE+6)),
              bytes.fromhex("0f87")+struct.pack("<i", CAVE-(JA_SITE+6)),
     "GetLevelName ja(>4) -> cave_tu5name"),
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
    print("Turn Undead V: I 6/4, II 7/5, III 8/6, IV 9/7, V 10/10; cost 5/level")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
