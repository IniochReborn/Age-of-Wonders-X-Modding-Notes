#!/usr/bin/env python3
"""
Marksmanship V (AoWEPACK.dll, 2026-07-20). Levels I-IV unchanged; new level V.
Effective curve (attack from pre-Claude AoWx rework, damage vanilla):
  I +1/+0   II +2/+1   III +3/+1   IV +4/+2   V +5/+2   (ATK/DMG)
Cost: vanilla 3 skill points/level, level 5 also 3.

Five patches:
 1. CAP - TMarksmanshipAbility.Create `mov dword [esi+0x28],4` @0x557BBD60 -> 5.
 2. COST - ctor's 4th TIntegerList.Put call @0x557BBDAA -> cave_mk5cost:
    Put(4,3) then tail-jmp Put(5,3). (ESI=self in ctor.)
 3. ATTACK - rewrite pre-Claude marksmanship cave @0x5580BF70 (in GetAttackRA,
    EAX=level, BL=attack acc): 4-rung ladder (+1..+4, else +0) -> `if level>0:
    add bl,level` - identical for I-IV, V gets +5.
 4. DAMAGE - GetDamageRA ladder's final `jz` @0x5576E64A (tests level-4==0)
    -> `jge`: level>=4 gets +2 (IV unchanged, V +2). I-III untouched. VANILLA
    fn (verified dll==dpl).
 5. NAME - GetLevelName is a 5-entry jump table guarded by `cmp edx,4; ja
    default` @0x557BBE07. Retarget the ja -> cave_mk5name: if level==5,
    replicate the case-body pattern (LoadResString(RStr @0x558E9498) ->
    TranslateRStr -> LStrCat3 with the " V" literal @0x5576DE04, using the
    frame's [ebp-8]/[ebp-4] locals which the fn's finally clears); else jmp
    default @0x557BBEE6. EAX is dead at the ja (SEH setup zeroed it) - that is
    why the cave cannot read the name from self and must re-load the RStr.

PIC (call/pop delta for the RStr global slot + " V" literal). Caves @0x5580E5B0
(file 0x10D9B0, zeros verified). ExpandName(level+1) routes through the same
GetLevelName -> the buy-V dialog entry works too.
Dry-run default; --apply. Backup: AoWEPACK.dll.bak_marksmanship5
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_marksmanship5"
FILE_DELTA = 0x55700C00

CAP_SITE  = 0x557BBD60           # mov dword [esi+0x28], 4
PUT_CALL  = 0x557BBDAA           # 4th Put call in ctor
PUT_FN    = 0x55702EB4
JA_SITE   = 0x557BBE07           # 0F 87 rel32 -> 0x557BBEE6
JA_DEF    = 0x557BBEE6
ATK_CAVE  = 0x5580BF70           # pre-Claude cave in GetAttackRA (rewrite in place)
ATK_ORIG  = bytes.fromhex("48740b48740d48740f487411eb1280c301eb0d80c302eb0880c303eb0380c304c3")
DMG_JZ    = 0x5576E64A           # 74 08 -> 7D 08
RSTR_GLOB = 0x558E9498           # Marksmanship RStr ptr global (relocated slot)
LOADRES   = 0x55701210
TRANSL    = 0x557249FC
LSTRCAT3  = 0x55701190
LIT_V     = 0x5576DE04           # " V" refcnt=-1 literal (verified)
NEW_MAX   = 5
COST      = 3

CAVE_COST = 0x5580E5B0           # file 0x10D9B0
CAVE_NAME = 0x5580E5D0
CAVE_LIMIT= 0x5580E640           # file 0x10DA40 (zeros verified)

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

# ---- cave_mk5cost: displaced Put(4,3), then Put(5,3) (ESI=self) -------------
a = Asm(CAVE_COST)
a.call(PUT_FN)                      # original Put(list,4,3) (args preset by ctor)
a.db(0x8B, 0x46, 0x2C)              # mov eax, [esi+0x2C]
a.db(0xBA, NEW_MAX,0,0,0)           # mov edx, 5
a.db(0xB9, COST,0,0,0)              # mov ecx, 3
a.jmp32(PUT_FN)                     # tail-call Put(list,5,3); its ret returns to ctor
cave_cost = a.done()
assert CAVE_COST + len(cave_cost) <= CAVE_NAME

# ---- cave_mk5name: level>4 path of GetLevelName -----------------------------
# in: EDX=level, EBX=out PAnsiString, EBP=fn frame (locals [ebp-8]/[ebp-4]=0, SEH active)
a = Asm(CAVE_NAME)
a.db(0x83, 0xFA, NEW_MAX)           # cmp edx, 5
a.j8(0x75, 'def')                   # jnz default
a.call(a.here()+5)                  # PIC anchor
_pop = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_pop)              # sub eax, link      ; eax = load delta
a.db(0x8B, 0x88); a.dd(LIT_V)       # mov ecx, [eax+LIT_V-?]... placeholder (patched below)
# NOTE: LIT_V is a literal ADDRESS (char data), not a pointer slot - need lea not mov.
cave_name = None  # rebuilt below with correct code
a = Asm(CAVE_NAME)
a.db(0x83, 0xFA, NEW_MAX)           # cmp edx, 5
a.j8(0x75, 'def')                   # jnz default
a.call(a.here()+5)                  # PIC anchor
_pop = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_pop)              # sub eax, link      ; eax = load delta
a.db(0x50)                          # push eax           ; save delta
a.db(0x8B, 0x80); a.dd(RSTR_GLOB)   # mov eax, [eax+RStrGlob] ; RStr ptr (relocated slot)
a.db(0x8D, 0x55, 0xF8)              # lea edx, [ebp-8]
a.call(LOADRES)                     # LoadResString -> [ebp-8]
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]
a.db(0x8D, 0x55, 0xFC)              # lea edx, [ebp-4]
a.call(TRANSL)                      # TranslateRStr -> [ebp-4] = "Marksmanship"
a.db(0x59)                          # pop ecx            ; delta
a.db(0x81, 0xC1); a.dd(LIT_V)       # add ecx, LIT_V     ; runtime " V" literal addr
a.db(0x8B, 0x55, 0xFC)              # mov edx, [ebp-4]
a.db(0x8B, 0xC3)                    # mov eax, ebx       ; out
a.call(LSTRCAT3)                    # out := name + " V"
a.label('def')
a.jmp32(JA_DEF)                     # rejoin epilogue (finally clears locals)
cave_name = a.done()
assert CAVE_NAME + len(cave_name) <= CAVE_LIMIT, f"name cave {len(cave_name)}B"

# ---- attack cave rewrite ----------------------------------------------------
atk_new = bytes.fromhex("85c0" "7e02" "02d8" "c3")     # test eax,eax; jle ret; add bl,al; ret
atk_new += b"\x00" * (len(ATK_ORIG) - len(atk_new))

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE_COST, bytes(len(cave_cost)), cave_cost, f"cave_mk5cost @0x{CAVE_COST:X} ({len(cave_cost)}B)"),
    (CAVE_NAME, bytes(len(cave_name)), cave_name, f"cave_mk5name @0x{CAVE_NAME:X} ({len(cave_name)}B)"),
    (CAP_SITE, bytes.fromhex("c7462804000000"), bytes.fromhex("c7462805000000"),
     "ctor cap: 4 -> 5"),
    (PUT_CALL, b"\xE8"+rel32(PUT_CALL, PUT_FN), b"\xE8"+rel32(PUT_CALL, CAVE_COST),
     "ctor 4th Put -> cave_mk5cost (adds cost[5]=3)"),
    (ATK_CAVE, ATK_ORIG, atk_new,
     "attack cave rewrite: ladder -> add bl,level (V=+5)"),
    (DMG_JZ, bytes.fromhex("7408"), bytes.fromhex("7d08"),
     "GetDamageRA: jz -> jge (level>=4 gets +2; V=+2)"),
    (JA_SITE, bytes.fromhex("0f87")+rel32(JA_SITE+1, JA_DEF)[0:4], # 0F 87 rel32 (rel from JA_SITE+6)
     bytes.fromhex("0f87")+struct.pack("<i", CAVE_NAME-(JA_SITE+6)),
     "GetLevelName ja(>4) -> cave_mk5name"),
]
# fix expected orig rel32 for the ja (6-byte instruction: rel from JA_SITE+6)
patches[6] = (JA_SITE,
    bytes.fromhex("0f87")+struct.pack("<i", JA_DEF-(JA_SITE+6)),
    bytes.fromhex("0f87")+struct.pack("<i", CAVE_NAME-(JA_SITE+6)),
    "GetLevelName ja(>4) -> cave_mk5name")

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
    print("Marksmanship V: I +1/0, II +2/+1, III +3/+1, IV +4/+2, V +5/+2; cost 3/level")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
