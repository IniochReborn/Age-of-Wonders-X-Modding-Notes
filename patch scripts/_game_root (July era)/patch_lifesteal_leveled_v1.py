#!/usr/bin/env python3
"""
Life Stealing becomes a 3-level ability (I/II/III = +1/+2/+3 HP per hit),
built on the engine's TMultiLevelAbility framework like Leadership (AoWEPACK.dll,
2026-07-20). REQUIRES patch_lifesteal_round_v1.py applied first (rewrites its
heal cave in place; Generate cave/hooks unchanged).

Three parts:
 A. FLYWEIGHT CONVERSION - RegisterStrikeAbilities creates the 0x76 ability via
    SUB_0x5576727C (TStrikeEnhancementAbility factory). Repoint that one call
    @0x5576730A -> cave_mlcreate: constructs TMultiLevelAbility instead (same
    id 0x76 / translated name / icon word), then cap[+0x28]=3 and
    cost[1..3]=10 skill points (TIntegerList.Put). CanExpand/Expand/ExpandCost/
    ExpandName/save-data (TMultiLevelAbilityData) all come free from the class.
 B. LEVEL NAMES - base TMultiLevelAbility.GetLevelName renders "Unknown N", so
    repoint TMultiLevelAbility's OWN VMT slot +0x10C (@0x5571E0DC) ->
    cave_lsnames ("Life Stealing" + " I/II/III", reusing Marksmanship's
    refcount=-1 suffix literals). Safe: no vanilla instance uses the plain ML
    VMT (verified: Object_Entry referenced only as parent/class-registry),
    and subclass VMTs are static copies - unaffected.
 C. HEAL BY LEVEL - rewrite cave_lsround @0x5580E160: heal = GetAbilityLevel
    (combat VMT+0xB0 -> strategic +0x144), so +1/+2/+3. Level 0 (legacy
    bit-only possessors: unit data authored before this patch has no level
    record) heals as level I. NOTE: that is a change from the pre-patch flat
    +2 - re-author units in DevEd with Life Stealing II to restore, or heroes
    buy levels at level-up (10 pts each, like Leadership).

PIC: classref + suffix-table reads via call/pop delta. Caves in verified-zero
space 0x5580E200+ (file 0x10D600+). Dry-run default; --apply.
Backup: AoWEPACK.dll.bak_lifesteal_leveled
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_lifesteal_leveled"
FILE_DELTA = 0x55700C00

MAX_LEVEL  = 3
COST_EACH  = 10
LS_ABIL    = 0x76
LS_FLAG    = 0x08

CREATE_CALL = 0x5576730A         # call SUB_5576727C inside RegisterStrikeAbilities
OLD_FACTORY = 0x5576727C
ML_OBJENTRY = 0x5571DF90         # TMultiLevelAbility.Object_Entry (dword = VMT ptr, relocated)
ML_CREATE   = 0x55765168         # TMultiLevelAbility.Create
ML_VMT_GLN  = 0x5571DFD0 + 0x10C # VMT slot +0x10C (GetLevelName) = 0x5571E0DC
GLN_ORIG    = 0x55765230         # base TMultiLevelAbility.GetLevelName ("Unknown N")
LSTRASG     = 0x55701150
LSTRCAT3    = 0x55701190
PUT_FN      = 0x55702EB4         # TIntegerList.Put (EAX=list, EDX=idx, ECX=val)
SUFFIX_VAS  = (0x557BBF18, 0x557BBF24, 0x557BBF30)   # " I", " II", " III"
EXEC_CONT   = 0x557667CF

CAVE_HEAL   = 0x5580E160         # existing cave_lsround slot (rewrite in place, 64B budget)
CAVE_HEAL_LIMIT = 0x5580E1A0
CAVE_MLCREATE = 0x5580E200       # file 0x10D600
CAVE_LSNAMES  = 0x5580E2A0
SUF_TAB       = 0x5580E2F0
CAVE_LIMIT    = 0x5580E380       # end of verified-zero region (file 0x10D780)

# v1 heal cave bytes (what we expect to replace)
V1_HEAL = bytes.fromhex(
    "f6431808" "7419" "8bc7" "8b10" "ff9288000000" "83c002" "8bd0" "8bc7"
    "8b08" "ff918c000000" "e94b86f5ff")

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

# ---- cave_mlcreate: (EAX=id, EDX=name, CX=icon) -> EAX = new ML ability -----
a = Asm(CAVE_MLCREATE)
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x51)                          # push ecx
a.db(0x66, 0x89, 0x0C, 0x24)        # mov [esp], cx          ; icon word
a.db(0x8B, 0xFA)                    # mov edi, edx           ; name
a.db(0x8B, 0xF0)                    # mov esi, eax           ; id
a.call(a.here()+5)                  # call $+5 (PIC anchor)
_pop = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_pop)              # sub eax, link addr     ; eax = load delta
a.db(0x8B, 0x80); a.dd(ML_OBJENTRY) # mov eax, [eax+ObjEntry]; VMT ptr (relocated slot)
a.db(0x33, 0xC9)                    # xor ecx, ecx
a.db(0xB2, 0x01)                    # mov dl, 1
a.call(ML_CREATE)                   # TMultiLevelAbility.Create -> eax = obj
a.db(0x8B, 0xD8)                    # mov ebx, eax
a.db(0x66, 0x8B, 0x04, 0x24)        # mov ax, [esp]
a.db(0x66, 0x89, 0x43, 0x20)        # mov [ebx+0x20], ax     ; icon word
a.db(0x89, 0x73, 0x0C)              # mov [ebx+0x0C], esi    ; ability id
a.db(0x8D, 0x43, 0x08)              # lea eax, [ebx+8]
a.db(0x8B, 0xD7)                    # mov edx, edi
a.call(LSTRASG)                     # name := translated "Life Stealing"
a.db(0xC7, 0x43, 0x28); a.dd(MAX_LEVEL)  # mov dword [ebx+0x28], 3 ; cap
for lvl in range(1, MAX_LEVEL+1):
    a.db(0x8B, 0x43, 0x2C)          # mov eax, [ebx+0x2C]    ; cost list
    a.db(0xBA); a.dd(lvl)           # mov edx, lvl
    a.db(0xB9); a.dd(COST_EACH)     # mov ecx, COST_EACH
    a.call(PUT_FN)                  # Put(list, lvl, cost)
a.db(0x8B, 0xC3)                    # mov eax, ebx           ; return obj
a.db(0x5A)                          # pop edx (balance icon push)
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0xC3)                          # ret
cave_mlcreate = a.done()
assert CAVE_MLCREATE + len(cave_mlcreate) <= CAVE_LSNAMES

# ---- cave_lsnames: GetLevelName(EAX=self, EDX=level, ECX=out PAnsiString) ---
a = Asm(CAVE_LSNAMES)
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x8B, 0xF9)                    # mov edi, ecx           ; out
a.db(0x8B, 0xF2)                    # mov esi, edx           ; level
a.db(0x8B, 0xD8)                    # mov ebx, eax           ; self
a.db(0x83, 0xFE, 0x01)              # cmp esi, 1
a.j8(0x7C, 'plain')                 # jl plain
a.db(0x83, 0xFE, MAX_LEVEL)         # cmp esi, MAX_LEVEL
a.j8(0x7F, 'plain')                 # jg plain
a.call(a.here()+5)                  # call $+5 (PIC anchor)
_pop = a.here()
a.db(0x5A)                          # pop edx
a.db(0x81, 0xEA); a.dd(_pop)        # sub edx, link addr     ; edx = delta
a.db(0x8B, 0x8C, 0xB2); a.dd(SUF_TAB - 4)  # mov ecx, [edx+esi*4+SUF_TAB-4]
a.db(0x03, 0xCA)                    # add ecx, edx           ; suffix (delta-fixed)
a.db(0x8B, 0xC7)                    # mov eax, edi           ; dest
a.db(0x8B, 0x53, 0x08)              # mov edx, [ebx+8]       ; base name
a.call(LSTRCAT3)                    # out := name + suffix
a.j8(0xEB, 'done')
a.label('plain')
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x53, 0x08)              # mov edx, [ebx+8]
a.call(LSTRASG)                     # out := name
a.label('done')
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0xC3)                          # ret
cave_lsnames = a.done()
assert CAVE_LSNAMES + len(cave_lsnames) <= SUF_TAB

suf_tab = b"".join(struct.pack("<I", v) for v in SUFFIX_VAS)
assert SUF_TAB + len(suf_tab) <= CAVE_LIMIT

# ---- cave_lsround v2: heal by ability level (EBX=CA, EDI=attacker) ----------
a = Asm(CAVE_HEAL)
a.db(0xF6, 0x43, 0x18, LS_FLAG)     # test byte [ebx+0x18], LS_FLAG
a.j8(0x74, 'done')                  # jz done
a.db(0xBA, LS_ABIL,0,0,0)           # mov edx, 0x76
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xB0,0,0,0)        # call [ecx+0xB0]        ; GetAbilityLevel 0..3
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x75, 'have')                  # jnz have
a.db(0x40)                          # inc eax                ; legacy bit-only -> I
a.label('have')
a.db(0x50)                          # push eax               ; save level
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x92, 0x88,0,0,0)        # call [edx+0x88]        ; GetHitPoints
a.db(0x5A)                          # pop edx                ; level
a.db(0x03, 0xC2)                    # add eax, edx           ; HP += level
a.db(0x8B, 0xD0)                    # mov edx, eax
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0x8C,0,0,0)        # call [ecx+0x8C]        ; SetHitPoints (clamps)
a.label('done')
a.jmp32(EXEC_CONT)
cave_heal = a.done()
assert CAVE_HEAL + len(cave_heal) <= CAVE_HEAL_LIMIT
# pad to cover all of v1's 36 bytes if v2 is shorter
if len(cave_heal) < len(V1_HEAL):
    cave_heal += b"\x00" * (len(V1_HEAL) - len(cave_heal))
V1_PAD = V1_HEAL + b"\x00" * max(0, len(cave_heal) - len(V1_HEAL))

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE_MLCREATE, bytes(len(cave_mlcreate)), cave_mlcreate,
     f"cave_mlcreate @0x{CAVE_MLCREATE:X} ({len(cave_mlcreate)}B: ML ctor, cap={MAX_LEVEL}, cost={COST_EACH}/lvl)"),
    (CAVE_LSNAMES, bytes(len(cave_lsnames)), cave_lsnames,
     f"cave_lsnames @0x{CAVE_LSNAMES:X} ({len(cave_lsnames)}B: name + ' I/II/III')"),
    (SUF_TAB, bytes(len(suf_tab)), suf_tab, "suffix ptr table"),
    (CAVE_HEAL, V1_PAD, cave_heal,
     f"cave_lsround v2 @0x{CAVE_HEAL:X} ({len(cave_heal)}B: heal = ability level, min 1)"),
    (CREATE_CALL, b"\xE8"+rel32(CREATE_CALL, OLD_FACTORY), b"\xE8"+rel32(CREATE_CALL, CAVE_MLCREATE),
     "RegisterStrikeAbilities: 0x76 factory -> cave_mlcreate"),
    (ML_VMT_GLN, struct.pack("<I", GLN_ORIG), struct.pack("<I", CAVE_LSNAMES),
     "TMultiLevelAbility VMT+0x10C: GetLevelName -> cave_lsnames"),
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
    print(f"levels: I +1 HP, II +2 HP, III +3 HP; cost {COST_EACH}/level")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
