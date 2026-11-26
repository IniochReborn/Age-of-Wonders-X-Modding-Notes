#!/usr/bin/env python3
"""
Leadership rework for AoWEPACK.dll (port of BXL's leadership4 + leadership_fix,
extended to FIVE levels, 2026-07-19).

Feature A - 5-level Leadership (cut content restored, custom curve):
    I  +1/+0   II +1/+1   III +2/+1   IV +2/+2   V +3/+3   (attack/defense)
    Cost: 10 skill points per level (flat). NOTE: rebalances level 1 downward
    (vanilla level 1 was +2/+1, now level III); existing leaders get weaker.
  1. cap imm32 @0x55766187 (`mov [esi+0x28],1`) -> 5
  2. ctor's `call TIntegerList.Put` @0x557661A2 -> cave_lscosts (Put cost[1..5]=10)
  3. GetAttack/GetDefense table disp32s @0x55766207/@0x5576621B -> relocated
     6-byte tables in cave data (both disp32s carry .reloc entries - verified -
     so the value repoint stays rebase-safe)
  4. TLeadershipAbility VMT+0x10C @0x55722114 (GetLevelName, only xref) ->
     cave_lsname: call original ("Leadership") then LStrCat3 a suffix.
     Suffixes reuse the game's own literals: " I".." IV" (Marksmanship's
     @0x557BBF18/24/30/40) + " V" @0x5576DE04 (multi-level framework's, found
     2026-07-19; header verified refcnt=-1 len=2).

Feature B - Leadership disable bug fix (grant masked by aura + GC eats record):
  TAbilityOwner.UpdateDefaultAbilities compares EFFECTIVE levels (own | aura-
  borrowed) at two sites, so a unit ranking up inside a leader's aura never gets
  its own inherent record; leaving the aura then deletes bit+record for good.
  Fix: repoint both 8-byte sites @0x5574F54D/@0x5574F55B (mov ecx,[eax];
  call [ecx+0x84] GetAbLevel) -> cave_abinherent, which resolves the ability
  flyweight via the registry and dispatches ability VMT+0x94 GetInherentLevel
  instead. No-op for non-multi-level abilities (both getters return 0).

All caves position-independent (call/pop load-delta for globals/data; rel32
calls). Cave block relocated to OUR free space 0x5580DFF0+ (file 0x10D3F0,
zeros verified 2026-07-19). MP: both peers need the patched DLL.
Dry-run by default; --apply to write. Backup: AoWEPACK.dll.bak_leadership5
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_leadership5"

FILE_DELTA = 0x55700C00

# ---- vanilla addresses (all byte-verified on our DLL 2026-07-19) ----
CAP_SITE   = 0x55766187          # mov dword [esi+0x28], 1  (C7 46 28 01 00 00 00)
PUT_CALL   = 0x557661A2          # call TIntegerList.Put
PUT_FN     = 0x55702EB4          # TIntegerList.Put (EAX=list, EDX=idx, ECX=val)
ATK_DISP   = 0x55766207          # disp32 in GetAttack  `mov al,[eax+0x558E83E7]`
DEF_DISP   = 0x5576621B          # disp32 in GetDefense `mov al,[eax+0x558E83EB]`
ATK_VAN    = 0x558E83E7
DEF_VAN    = 0x558E83EB
VMT_SLOT   = 0x55722114          # TLeadershipAbility VMT+0x10C (GetLevelName)
ORIG_NAME  = 0x557663D0          # TLeadershipAbility.GetLevelName
LSTRCAT3   = 0x55701190          # System.@LStrCat3 (EAX=dest, EDX=s1, ECX=s2)
LSTRASG    = 0x55701150          # System.@LStrAsg  (EAX=&dest, EDX=src)
LSTRCLR    = 0x55701140          # System.@LStrClr  (EAX=&str)
AOWHSSET   = 0x558FA044          # AoWE.AoWHSSet (ability registry at +0x80)
GETABILITY = 0x557501C0          # TAbilityControl.GetAbility (EAX=ctl, EDX=id)
SITE1      = 0x5574F54D          # UpdateDefaultAbilities: template level call
SITE2      = 0x5574F55B          # UpdateDefaultAbilities: unit level call
SITE_ORIG  = bytes.fromhex("8b08ff9184000000")           # mov ecx,[eax]; call [ecx+0x84]
# suffix literals (char-data VAs; refcnt=-1 constants, verified)
SUFFIX_VAS = (0x557BBF18, 0x557BBF24, 0x557BBF30, 0x557BBF40, 0x5576DE04)  # " I".." V"

# ---- our cave block (file 0x10D3F0+, zeros verified to 0x10D600) ----
CAVE_COSTS = 0x5580DFF0
CAVE_NAME  = 0x5580E020
DATA_TAB   = 0x5580E0C0
ATK_TAB    = DATA_TAB + 0x00     # 6 bytes, index = level 0..5
DEF_TAB    = DATA_TAB + 0x08
SUF_TAB    = DATA_TAB + 0x10     # 5 dwords, link-time VAs of suffix literals
CAVE_FIX   = DATA_TAB + 0x28     # cave_abinherent
CAVE_END_LIMIT = 0x5580E200      # file 0x10D600, end of verified-zero region

# ---- user-chosen curve / cost ----
ATK_BONUS = (0, 1, 1, 2, 2, 3)   # index = level (0 unused; getters early-return)
DEF_BONUS = (0, 0, 1, 1, 2, 3)
MAX_LEVEL = 5
COST_EACH = 10

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, name): self.labels[name] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self._rel32(t)
    def _rel32(self, t):
        if isinstance(t, str):
            self.fix32.append((len(self.buf), t)); self.buf += b'\0\0\0\0'
        else:
            self.buf += (t - (self.here()+4)).to_bytes(4, 'little', signed=True)
    def j8(self, op, lab):
        self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab]-(self.base+off+4)).to_bytes(4,'little',signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1)
            assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
    def done(self): self.resolve(); return bytes(self.buf)

# ---- cave_lscosts: EAX = cost TIntegerList; Put(list, 1..5, 10) --------------
a = Asm(CAVE_COSTS)
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x8B, 0xD8)                    # mov ebx, eax
a.db(0xBE, 0x01,0,0,0)              # mov esi, 1
a.label('c_loop')
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.db(0x8B, 0xD6)                    # mov edx, esi
a.db(0xB9); a.dd(COST_EACH)         # mov ecx, COST_EACH
a.call(PUT_FN)
a.db(0x46)                          # inc esi
a.db(0x83, 0xFE, MAX_LEVEL)         # cmp esi, MAX_LEVEL
a.j8(0x7E, 'c_loop')                # jle
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0xC3)                          # ret
cave_costs = a.done()

# ---- cave_lsname: GetLevelName(EAX=self, EDX=level, ECX=out PAnsiString) -----
# tmp := original(self, level); out := (1<=level<=5) ? tmp + suffix[level-1] : tmp
a = Asm(CAVE_NAME)
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x55)                          # push ebp
a.db(0x8B, 0xF9)                    # mov edi, ecx           ; out ptr
a.db(0x8B, 0xF2)                    # mov esi, edx           ; level
a.db(0x8B, 0xD8)                    # mov ebx, eax           ; self
a.call(a.here()+5)                  # call $+5 (push runtime addr of pop)
_pop_va = a.here()
a.db(0x5D)                          # pop ebp                ; runtime addr
a.db(0x81, 0xED); a.dd(_pop_va)     # sub ebp, link addr     ; ebp = load delta
a.db(0x6A, 0x00)                    # push 0                 ; tmp AnsiString slot
a.db(0x8B, 0xCC)                    # mov ecx, esp           ; &tmp
a.db(0x8B, 0xD6)                    # mov edx, esi
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.call(ORIG_NAME)                   # tmp := "Leadership"
a.db(0x83, 0xFE, 0x01)              # cmp esi, 1
a.j8(0x7C, 'n_plain')               # jl plain
a.db(0x83, 0xFE, MAX_LEVEL)         # cmp esi, MAX_LEVEL
a.j8(0x7F, 'n_plain')               # jg plain
a.db(0x8D, 0x56, 0xFF)              # lea edx, [esi-1]
a.db(0x8B, 0x8C, 0x95); a.dd(SUF_TAB)  # mov ecx, [ebp + edx*4 + SUF_TAB]
a.db(0x03, 0xCD)                    # add ecx, ebp           ; suffix (delta-fixed)
a.db(0x8B, 0x14, 0x24)              # mov edx, [esp]         ; tmp
a.db(0x8B, 0xC7)                    # mov eax, edi           ; dest
a.call(LSTRCAT3)                    # out := tmp + suffix
a.j8(0xEB, 'n_done')
a.label('n_plain')
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x14, 0x24)              # mov edx, [esp]
a.call(LSTRASG)                     # out := tmp
a.label('n_done')
a.db(0x8B, 0xC4)                    # mov eax, esp
a.call(LSTRCLR)                     # release tmp
a.db(0x83, 0xC4, 0x04)              # add esp, 4
a.db(0x5D)                          # pop ebp
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0xC3)                          # ret
cave_name = a.done()
assert CAVE_NAME + len(cave_name) <= DATA_TAB, f"cave_lsname overruns DATA_TAB ({len(cave_name)}B)"

# ---- data tables -------------------------------------------------------------
tab = bytes(ATK_BONUS) + b"\x00"*(8-len(ATK_BONUS)) \
    + bytes(DEF_BONUS) + b"\x00"*(8-len(DEF_BONUS)) \
    + b"".join(struct.pack("<I", v) for v in SUFFIX_VAS) \
    + b"\x00"*4                     # pad to CAVE_FIX (0x10+0x14+4 = 0x28)
assert len(tab) == CAVE_FIX - DATA_TAB

# ---- cave_abinherent: in EAX=owner, EDX=id; out EAX=inherent level -----------
a = Asm(CAVE_FIX)
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x8B, 0xF2)                    # mov esi, edx           ; id
a.db(0x8B, 0xD8)                    # mov ebx, eax           ; owner
a.call(a.here()+5)                  # call $+5
_pop_va = a.here()
a.db(0x58)                          # pop eax
a.db(0x2D); a.dd(_pop_va)           # sub eax, link addr     ; eax = load delta
a.db(0x8B, 0x80); a.dd(AOWHSSET)    # mov eax, [eax+AoWHSSet]
a.db(0x8B, 0x80, 0x80,0,0,0)        # mov eax, [eax+0x80]    ; ability registry
a.db(0x8B, 0xD6)                    # mov edx, esi
a.call(GETABILITY)                  # -> eax = ability flyweight
a.db(0x8B, 0xD3)                    # mov edx, ebx           ; owner
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0x94,0,0,0)        # call [ecx+0x94]        ; GetInherentLevel
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0xC3)                          # ret
cave_fix = a.done()
assert CAVE_FIX + len(cave_fix) <= CAVE_END_LIMIT

def rel32(src, dst): return struct.pack("<i", dst-(src+5))

patches = [
    (CAVE_COSTS, bytes(len(cave_costs)), cave_costs, f"cave_lscosts (cost[1..{MAX_LEVEL}]={COST_EACH})"),
    (CAVE_NAME,  bytes(len(cave_name)),  cave_name,  "cave_lsname (append ' I'..' V')"),
    (DATA_TAB,   bytes(len(tab)),        tab,        "atk/def tables + suffix ptrs"),
    (CAVE_FIX,   bytes(len(cave_fix)),   cave_fix,   "cave_abinherent (GetAbLevel -> GetInherentLevel)"),
    (CAP_SITE, bytes.fromhex("c7462801000000"), bytes.fromhex("c74628")+bytes([MAX_LEVEL])+b"\0\0\0",
               f"cap: [esi+0x28] = 1 -> {MAX_LEVEL}"),
    (PUT_CALL, b"\xE8"+rel32(PUT_CALL, PUT_FN), b"\xE8"+rel32(PUT_CALL, CAVE_COSTS),
               "ctor: call TIntegerList.Put -> cave_lscosts"),
    (ATK_DISP, struct.pack("<I", ATK_VAN), struct.pack("<I", ATK_TAB),
               f"GetAttack disp32 -> table {tuple(ATK_BONUS[1:])}"),
    (DEF_DISP, struct.pack("<I", DEF_VAN), struct.pack("<I", DEF_TAB),
               f"GetDefense disp32 -> table {tuple(DEF_BONUS[1:])}"),
    (VMT_SLOT, struct.pack("<I", ORIG_NAME), struct.pack("<I", CAVE_NAME),
               "VMT+0x10C: GetLevelName -> cave_lsname"),
    (SITE1, SITE_ORIG, b"\xE8"+rel32(SITE1, CAVE_FIX)+b"\x90\x90\x90",
               "UpdateDefaultAbilities site1: template level -> inherent"),
    (SITE2, SITE_ORIG, b"\xE8"+rel32(SITE2, CAVE_FIX)+b"\x90\x90\x90",
               "UpdateDefaultAbilities site2: unit level -> inherent"),
]

print(f"curve: I +{ATK_BONUS[1]}/+{DEF_BONUS[1]}  II +{ATK_BONUS[2]}/+{DEF_BONUS[2]}  "
      f"III +{ATK_BONUS[3]}/+{DEF_BONUS[3]}  IV +{ATK_BONUS[4]}/+{DEF_BONUS[4]}  V +{ATK_BONUS[5]}/+{DEF_BONUS[5]}")
print(f"cost: {COST_EACH}/level ({COST_EACH*MAX_LEVEL} total to V)")
print(f"caves: costs@{CAVE_COSTS:08X}({len(cave_costs)}B) name@{CAVE_NAME:08X}({len(cave_name)}B) "
      f"data@{DATA_TAB:08X}({len(tab)}B) fix@{CAVE_FIX:08X}({len(cave_fix)}B)")

data = bytearray(open(DLL, 'rb').read())
ok = True; applied = 0
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    cur = bytes(data[off:off+len(orig)])
    if cur == new:
        applied += 1
    elif cur != orig:
        print(f"MISMATCH @0x{va:X} ({desc}):\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}")
        ok = False
if applied == len(patches):
    print("ALL ALREADY PATCHED"); sys.exit(0)
if not ok:
    print("Aborting - original bytes did not match."); sys.exit(1)
if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
