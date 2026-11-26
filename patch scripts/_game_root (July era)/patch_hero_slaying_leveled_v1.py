#!/usr/bin/env python3
"""
Hero Slaying I/II/III - new 3-level ability (id 0x38): +1/+1, +2/+2, +3/+3
ATK/DMG vs hero/leader targets in melee (AoWEPACK.dll, 2026-07-20).
Concept from BXL's Assassin; rebuilt leveled on TMultiLevelAbility.
REQUIRES patch_lifesteal_leveled_v1.py (its cave_lsnames @0x5580E2A0 provides
" I/II/III" names generically for any plain-ML instance via VMT+0x10C).

 A. REGISTRATION - hook the RegisterAbility call @0x55767313 (right after our
    lifesteal mlcreate call in RegisterStrikeAbilities) -> cave_hsreg: performs
    the original registration, then constructs a second TMultiLevelAbility
    (id 0x38, name "Hero Slaying" from an embedded refcnt=-1 AnsiString
    constant, icon word 0x209 = the strike-ability group's, cap 3,
    cost 10/level) and registers it. Id 0x38 verified free (RegisterAbility
    raises loudly at startup if not).
 B. MELEE BONUS - the two parallel slayer tables (per BXL; the autocombat DV
    copy and CalculateUnitStrikes are deliberately NOT hooked - same scope as
    his confirmed-working Assassin):
    - global CreateStrikeCA Monster block @0x557666A1 (EBP=attacker,
      ESI=target, BL=atk acc, [ESP+3]=dmg acc) -> cave_hsmelee
    - TMeleeRound.CalculateStrikes block @0x55767C5C (ESI=attacker,
      EDI=target, [EBX]=atk dword, [EBX+4]=dmg dword) -> cave_hsmelee2
    Both: attacker GetAbilityEnabled(0x38) [null-safe] -> target strategic
    unit != nil && IsClass(THero) [covers TLeader] -> level = GetAbilityLevel
    (min 1 for bare-bit) -> add level to atk+dmg. Displaced instruction
    `mov edx,0x70` replayed; vanilla Monster Slaying block runs unchanged.

Register-truth note: disasm shows 0x70 checked on the ATTACKER and 0x3F on the
TARGET in both blocks (0x70 = Monster Slaying ability, 0x3F = Dragon marker -
our old MEMORY notes had these swapped; BXL's naming is correct).

PIC throughout (call/pop delta for classrefs/name constant). Caves @0x5580E300+
(file 0x10D700+, zeros verified). Dry-run default; --apply.
Backup: AoWEPACK.dll.bak_hero_slaying_lvl
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_hero_slaying_lvl"
FILE_DELTA = 0x55700C00

HS_ABIL   = 0x38
MAX_LEVEL = 3
COST_EACH = 10
ICON_WORD = 0x209

REG_CALL   = 0x55767313          # call RegisterAbility (after lifesteal mlcreate)
REGISTER   = 0x55750238          # TAbilityControl.RegisterAbility (EAX=ctl, EDX=ability)
ML_OBJENTRY= 0x5571DF90          # TMultiLevelAbility.Object_Entry
ML_CREATE  = 0x55765168
LSTRASG    = 0x55701150
PUT_FN     = 0x55702EB4
ISCLASS    = 0x557010C0
THERO_REF  = 0x55711FAC          # global -> THero VMT (verified by class name)

MELEE1_INJ = 0x557666A1; MELEE1_CONT = 0x557666A6   # CreateStrikeCA
MELEE2_INJ = 0x55767C5C; MELEE2_CONT = 0x55767C61   # TMeleeRound.CalculateStrikes
BLOCK_ORIG = bytes.fromhex("ba70000000")             # mov edx,0x70

CAVE_HSREG   = 0x5580E300        # file 0x10D700
NAME_TAB     = 0x5580E390        # AnsiString constant block
CAVE_MELEE1  = 0x5580E3B0
CAVE_MELEE2  = 0x5580E410
CAVE_LIMIT   = 0x5580E470        # file 0x10D870 — still inside verified-zero run (0x10D840 was conservative; re-check below)

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

# ---- name constant: refcnt -1, len 12, "Hero Slaying\0" ---------------------
name_blob = struct.pack("<i", -1) + struct.pack("<I", 12) + b"Hero Slaying\x00"
NAME_CHARS = NAME_TAB + 8        # link-time VA of char data

# ---- cave_hsreg: displaced RegisterAbility call + create/register 0x38 ------
a = Asm(CAVE_HSREG)
a.call(REGISTER)                    # original: register lifesteal ability
a.db(0x56)                          # push esi (caller doesn't save esi/edi)
a.db(0x57)                          # push edi
a.call(a.here()+5)                  # PIC anchor
_pop = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_pop)              # sub eax, link  ; eax = load delta
a.db(0x8B, 0xF0)                    # mov esi, eax   ; esi = delta
a.db(0x8B, 0x86); a.dd(ML_OBJENTRY) # mov eax, [esi+ObjEntry] ; ML VMT ptr
a.db(0x33, 0xC9)                    # xor ecx, ecx
a.db(0xB2, 0x01)                    # mov dl, 1
a.call(ML_CREATE)                   # -> eax = obj
a.db(0x8B, 0xF8)                    # mov edi, eax
a.db(0x66, 0xC7, 0x47, 0x20); a.db(ICON_WORD & 0xFF, ICON_WORD >> 8)  # mov word [edi+0x20], icon
a.db(0xC7, 0x47, 0x0C); a.dd(HS_ABIL)     # mov dword [edi+0x0C], 0x38
a.db(0x8D, 0x96); a.dd(NAME_CHARS)  # lea edx, [esi+NAME_CHARS] ; runtime const addr
a.db(0x8D, 0x47, 0x08)              # lea eax, [edi+8]
a.call(LSTRASG)                     # name := "Hero Slaying"
a.db(0xC7, 0x47, 0x28); a.dd(MAX_LEVEL)   # cap = 3
for lvl in range(1, MAX_LEVEL+1):
    a.db(0x8B, 0x47, 0x2C)          # mov eax, [edi+0x2C]
    a.db(0xBA); a.dd(lvl)           # mov edx, lvl
    a.db(0xB9); a.dd(COST_EACH)     # mov ecx, cost
    a.call(PUT_FN)
a.db(0x8B, 0xD7)                    # mov edx, edi   ; ability
a.db(0x8B, 0xC3)                    # mov eax, ebx   ; control (ebx live from caller)
a.call(REGISTER)                    # RegisterAbility(control, hero-slaying)
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0xC3)                          # ret
cave_hsreg = a.done()
assert CAVE_HSREG + len(cave_hsreg) <= NAME_TAB, f"hsreg {len(cave_hsreg)}B"
assert NAME_TAB + len(name_blob) <= CAVE_MELEE1

def build_melee(base, atk_dmg_writer, cont):
    """Shared cave shape; atk_dmg_writer(a) emits the add-level code (AL=level)."""
    a = Asm(base)
    a.db(0xBA, HS_ABIL,0,0,0)        # mov edx, 0x38
    a.db(0x8B, 0xC5) if base == CAVE_MELEE1 else a.db(0x8B, 0xC6)  # attacker: ebp / esi
    a.db(0x8B, 0x08)                 # mov ecx, [eax]
    a.db(0xFF, 0x91, 0xA8,0,0,0)     # call [ecx+0xA8]  ; enabled? (null-safe)
    a.db(0x84, 0xC0)                 # test al, al
    a.j8(0x74, 'out')                # jz out
    a.call(a.here()+5)               # PIC anchor
    _pop = a.here()
    a.db(0x5A)                       # pop edx
    a.db(0x81, 0xEA); a.dd(_pop)     # sub edx, link   ; edx = delta
    a.db(0x8B, 0x92); a.dd(THERO_REF)# mov edx, [edx+THeroRef] ; THero class
    # target strategic unit
    a.db(0x8B, 0x46, 0x4C) if base == CAVE_MELEE1 else a.db(0x8B, 0x47, 0x4C)  # mov eax,[tgt+0x4C]
    a.db(0x85, 0xC0)                 # test eax, eax
    a.j8(0x74, 'out')                # jz out
    a.call(ISCLASS)                  # al = is THero (covers TLeader)
    a.db(0x84, 0xC0)                 # test al, al
    a.j8(0x74, 'out')                # jz out
    a.db(0xBA, HS_ABIL,0,0,0)        # mov edx, 0x38
    a.db(0x8B, 0xC5) if base == CAVE_MELEE1 else a.db(0x8B, 0xC6)  # attacker again
    a.db(0x8B, 0x08)                 # mov ecx, [eax]
    a.db(0xFF, 0x91, 0xB0,0,0,0)     # call [ecx+0xB0]  ; GetAbilityLevel (safe: enabled passed)
    a.db(0x85, 0xC0)                 # test eax, eax
    a.j8(0x75, 'have')               # jnz have
    a.db(0x40)                       # inc eax          ; bare-bit -> level 1
    a.label('have')
    atk_dmg_writer(a)                # add level to atk/dmg accumulators
    a.label('out')
    a.db(0xBA, 0x70,0,0,0)           # replay: mov edx, 0x70
    a.jmp32(cont)
    return a.done()

def w1(a):  # CreateStrikeCA: BL=atk acc, byte [esp+3]=dmg acc (no pushes outstanding)
    a.db(0x02, 0xD8)                 # add bl, al
    a.db(0x00, 0x44, 0x24, 0x03)     # add [esp+3], al
def w2(a):  # CalculateStrikes: [ebx]=atk dword, [ebx+4]=dmg dword
    a.db(0x01, 0x03)                 # add [ebx], eax
    a.db(0x01, 0x43, 0x04)           # add [ebx+4], eax

cave_m1 = build_melee(CAVE_MELEE1, w1, MELEE1_CONT)
cave_m2 = build_melee(CAVE_MELEE2, w2, MELEE2_CONT)
assert CAVE_MELEE1 + len(cave_m1) <= CAVE_MELEE2, f"m1 {len(cave_m1)}B"
assert CAVE_MELEE2 + len(cave_m2) <= CAVE_LIMIT, f"m2 {len(cave_m2)}B"

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE_HSREG, bytes(len(cave_hsreg)), cave_hsreg,
     f"cave_hsreg @0x{CAVE_HSREG:X} ({len(cave_hsreg)}B: create+register HS 0x38, cap 3, cost {COST_EACH})"),
    (NAME_TAB, bytes(len(name_blob)), name_blob, 'AnsiString constant "Hero Slaying"'),
    (CAVE_MELEE1, bytes(len(cave_m1)), cave_m1,
     f"cave_hsmelee @0x{CAVE_MELEE1:X} ({len(cave_m1)}B: CreateStrikeCA +lvl/+lvl vs heroes)"),
    (CAVE_MELEE2, bytes(len(cave_m2)), cave_m2,
     f"cave_hsmelee2 @0x{CAVE_MELEE2:X} ({len(cave_m2)}B: CalculateStrikes +lvl/+lvl vs heroes)"),
    (REG_CALL, b"\xE8"+rel32(REG_CALL, REGISTER), b"\xE8"+rel32(REG_CALL, CAVE_HSREG),
     "RegisterStrikeAbilities: RegisterAbility -> cave_hsreg"),
    (MELEE1_INJ, BLOCK_ORIG, b"\xE9"+rel32(MELEE1_INJ, CAVE_MELEE1),
     "CreateStrikeCA Monster block -> cave_hsmelee"),
    (MELEE2_INJ, BLOCK_ORIG, b"\xE9"+rel32(MELEE2_INJ, CAVE_MELEE2),
     "CalculateStrikes Monster block -> cave_hsmelee2"),
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
    print(f"Hero Slaying I/II/III: +1/+1, +2/+2, +3/+3 ATK/DMG vs heroes; cost {COST_EACH}/level")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
