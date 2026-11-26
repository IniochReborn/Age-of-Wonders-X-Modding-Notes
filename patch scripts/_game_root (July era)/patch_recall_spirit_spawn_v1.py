import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

URI_VA = fva(0x4C7C8)   # TUnitResource.UnitResourceIndex(self) -> EAX = unit type ID

# ── Addresses ────────────────────────────────────────────────────────────────
RS_CAVE_FILE_OFF = 0x10CD8D   # Recall Spirit spawn cave
RS_CAVE_AVAIL    = 704        # 0x10D04D - 0x10CD8D

NEW_SUB_FILE_OFF = 0x10D04D   # New upkeep subroutine (replaces old at 0x10C593)
NEW_SUB_SIZE     = 171

JMP_PATCH_OFF = 0xF9526       # BA 82 00 00 00  →  E9 xx xx xx xx
JMP_PATCH_OLD = bytes([0xBA, 0x82, 0x00, 0x00, 0x00])
JMP_RETURN    = fva(0xF952B)  # call AddUnit — return site after cave

CALL1_OFF = 0x10BAFE          # CALL in TRecallSpiritCA summoned cave → old sub
CALL1_OLD = bytes([0xE8, 0x90, 0x0A, 0x00, 0x00])
CALL2_OFF = 0x10BB34          # CALL in TAnimateDeadCA summoned cave → old sub
CALL2_OLD = bytes([0xE8, 0x5A, 0x0A, 0x00, 0x00])

OLD_SUB_FILE_OFF = 0x10C593   # Old upkeep subroutine (103 bytes)
OLD_SUB_SIZE     = 103

# ── Compute 5-byte JMP patch ──────────────────────────────────────────────────
_rel      = (fva(RS_CAVE_FILE_OFF) - fva(JMP_PATCH_OFF + 5)) & 0xFFFFFFFF
JMP_PATCH_NEW = b'\xE9' + struct.pack('<I', _rel)
assert len(JMP_PATCH_NEW) == 5

# ── Compute updated CALL bytes ────────────────────────────────────────────────
def make_call_bytes(from_off, to_off):
    rel = (to_off - from_off - 5) & 0xFFFFFFFF
    return b'\xE8' + struct.pack('<I', rel)

CALL1_NEW = make_call_bytes(CALL1_OFF, NEW_SUB_FILE_OFF)
CALL2_NEW = make_call_bytes(CALL2_OFF, NEW_SUB_FILE_OFF)

# ── Build new upkeep subroutine (171 bytes) ───────────────────────────────────
#
# Same prologue as old sub: derive enchant ptr from [EBX+10h][+10h], call URI
# on [EBX+40h] to get spawned unit type ID, write [enchant+10h] by unit type.
#
# Unit type → mana upkeep:
#   243        → 15  (dragon)
#   133        → 10  (spirit 133)
#   204, 206   → 10  (horror, wraith)
#   216        →  8  (spirit 216)
#   44         →  6  (glow creature)
#   200, 223   →  5  (horse, mummy)
#   241        →  3  (spirit/ghost)
#   else       →  2  (130 spirit, 201 swordsman, 202 hound, 249 …)
#
def build_new_sub():
    sub_va = fva(NEW_SUB_FILE_OFF)
    s      = bytearray()
    labels = {}
    fixups = []

    def here(): return len(s)
    def lbl(n): labels[n] = here()
    def B(*bs): s.extend(bs)
    def I32(v): s.extend(struct.pack('<I', v & 0xFFFFFFFF))
    def JE(n):  B(0x0F, 0x84); fixups.append((here(), n)); I32(0)
    def resolve():
        for off, name in fixups:
            struct.pack_into('<I', s, off, (labels[name] - off - 4) & 0xFFFFFFFF)
    def SET(val):
        B(0xC7, 0x41, 0x10); I32(val)   # mov dword [ecx+10h], val
        B(0xC3)                           # ret

    # Prologue (16 bytes)
    B(0x8B, 0x4B, 0x10)   # mov ecx, [ebx+10h]   TUnitEnchantmentAbilityData
    B(0x8B, 0x49, 0x10)   # mov ecx, [ecx+10h]   TUnitEnchantment
    B(0x51)               # push ecx              save enchant (ECX trashed by call)
    B(0x8B, 0x43, 0x40)   # mov eax, [ebx+40h]   TUnitResource ptr
    B(0xE8); I32((URI_VA - (sub_va + here() + 4)) & 0xFFFFFFFF)  # call URI
    B(0x59)               # pop ecx               restore enchant ptr

    # CMP chains: 9 pairs × 11 bytes = 99 bytes
    B(0x3D); I32(243); JE('set15')
    B(0x3D); I32(133); JE('set10')
    B(0x3D); I32(204); JE('set10')
    B(0x3D); I32(206); JE('set10')
    B(0x3D); I32(216); JE('set8')
    B(0x3D); I32(44);  JE('set6')
    B(0x3D); I32(200); JE('set5')
    B(0x3D); I32(223); JE('set5')
    B(0x3D); I32(241); JE('set3')
    SET(2)      # default: 130 spirit, 201 swordsman, 202 hound, 249 …

    lbl('set15'); SET(15)
    lbl('set10'); SET(10)
    lbl('set8');  SET(8)
    lbl('set6');  SET(6)
    lbl('set5');  SET(5)
    lbl('set3');  SET(3)

    resolve()
    assert len(s) == NEW_SUB_SIZE, f"Sub size mismatch: {len(s)} != {NEW_SUB_SIZE}"
    return bytes(s)

new_sub = build_new_sub()

# ── Build Recall Spirit spawn cave ───────────────────────────────────────────
#
# Replaces the 5-byte `mov edx, 130` at 0xF9526.
# On entry: EBX = new TUnit, ESI = dead body TCombatUnit, EAX = [eax+5Ch] (caller)
# On exit (JMP to 0xF952B): EDX = chosen spawn unit ID; EBX and EAX restored.
#
# Groups (table index → handler):
#   0 default     everything else   80% 130 / 20% 241
#   1 greater     major undead      80% 241 / 20% 130
#   2 g241_self   241 corpse        50% 241 / 50% 130
#   3 glow_mix    37,41,43,289      10% 44  / 20% 130 / 70% 241
#   4 unit42      42                40% 44  / 20% 130 / 40% 241
#   5 glow        44,224-227,282    20% 44  / 20% 130 / 60% 241
#   6 spirit133   133,203           80% 241 / 20% 133
#   7 spirit216   216,292           90% 241 / 10% 216
#
CAVE_VA = fva(RS_CAVE_FILE_OFF)

code   = bytearray()
labels = {}
fixups = []

def here():     return len(code)
def lbl(n):     labels[n] = here()
def B(*bs):     code.extend(bs)
def I32(v):     code.extend(struct.pack('<I', v & 0xFFFFFFFF))
def CALL(va):   B(0xE8); I32((va - (CAVE_VA + here() + 4)) & 0xFFFFFFFF)
def JMP_VA(va): B(0xE9); I32((va - (CAVE_VA + here() + 4)) & 0xFFFFFFFF)
def JMP(n):     B(0xE9);       fixups.append((here(), n, 'r32')); I32(0)
def JE(n):      B(0x0F, 0x84); fixups.append((here(), n, 'r32')); I32(0)
def JZ(n):      JE(n)
def JA(n):      B(0x0F, 0x87); fixups.append((here(), n, 'r32')); I32(0)
def JB(n):      B(0x0F, 0x82); fixups.append((here(), n, 'r32')); I32(0)
def PICREL(base_lbl, target_lbl):
    B(0x81, 0xC1); fixups.append((here(), (base_lbl, target_lbl), 'picrel')); I32(0)

def resolve():
    for off, name, typ in fixups:
        if typ == 'r32':
            t = labels[name]
            struct.pack_into('<I', code, off, (t - off - 4) & 0xFFFFFFFF)
        elif typ == 'picrel':
            base_lbl, tgt_lbl = name
            val = (labels[tgt_lbl] - labels[base_lbl]) & 0xFFFFFFFF
            struct.pack_into('<I', code, off, val)

# ── Prologue ──
B(0x50); B(0x53)           # push eax; push ebx  (save caller's EAX and new TUnit)
B(0x8B, 0x46, 0x4C)        # mov eax, [esi+4Ch]  dead body TCombatUnit -> TUnit ptr
B(0x8B, 0x40, 0x40)        # mov eax, [eax+40h]  TUnit -> TUnitResource ptr
CALL(URI_VA)               # EAX = unit type ID of the dead body

# Get RNG before bounds check so group-0 handler can use it
B(0x50)                    # push eax            save unit type ID
B(0x0F, 0x31)              # rdtsc
B(0x31, 0xD2)              # xor edx, edx
B(0xB9); I32(100)          # mov ecx, 100
B(0xF7, 0xF1)              # div ecx             EDX = remainder (0-99)
B(0x89, 0xD1)              # mov ecx, edx        ECX = RNG [0,99]
B(0x58)                    # pop eax             restore unit type ID

# Bounds check: if ID > 292 the table has no entry → treat as group 0
B(0x3D); I32(292); JA('default')

# PIC table lookup (position-independent: CALL/POP trick)
B(0x51)                    # push ecx            save RNG
B(0xE8, 0, 0, 0, 0)        # CALL +0  → pushes VA of pic_next onto stack
lbl('pic_next')
B(0x59)                    # pop ecx             ECX = runtime VA of pic_next
PICREL('pic_next', 'table') # add ecx, (table - pic_next)
B(0x0F, 0xB6, 0x14, 0x01)  # movzx edx, byte [ecx+eax]  EDX = group index
B(0x59)                    # pop ecx             restore RNG

# ── Dispatch ──
B(0x85, 0xD2); JZ('default')       # group 0
B(0x83, 0xFA, 1); JE('greater')
B(0x83, 0xFA, 2); JE('g241_self')
B(0x83, 0xFA, 3); JE('glow_mix')
B(0x83, 0xFA, 4); JE('unit42')
B(0x83, 0xFA, 5); JE('glow')
B(0x83, 0xFA, 6); JE('spirit133')
# group 7 falls through to spirit216

# ── Handlers ──
# spirit216 (corpses 216, 292): 90% -> 241, 10% -> 216
lbl('spirit216'); B(0x83, 0xF9, 90); JB('ghost_prim'); JMP('s216_prim')

# default (group 0, or ID > 292): 80% -> 130, 20% -> 241
lbl('default');   B(0x83, 0xF9, 80); JB('rs_prim');    JMP('ghost_prim')

# greater (major undead): 80% -> 241, 20% -> 130
lbl('greater');   B(0x83, 0xF9, 80); JB('ghost_prim'); JMP('rs_prim')

# g241_self (241 corpse): 50% -> 241, 50% -> 130
lbl('g241_self'); B(0x83, 0xF9, 50); JB('ghost_prim'); JMP('rs_prim')

# glow_mix (37,41,43,289): 10% -> 44, 20% -> 130, 70% -> 241
lbl('glow_mix'); B(0x83, 0xF9, 10); JB('glow_prim'); B(0x83, 0xF9, 30); JB('rs_prim'); JMP('ghost_prim')

# unit42 (42): 40% -> 44, 20% -> 130, 40% -> 241
lbl('unit42');   B(0x83, 0xF9, 40); JB('glow_prim'); B(0x83, 0xF9, 60); JB('rs_prim'); JMP('ghost_prim')

# glow (44, 224-227, 282): 20% -> 44, 20% -> 130, 60% -> 241
lbl('glow');     B(0x83, 0xF9, 20); JB('glow_prim'); B(0x83, 0xF9, 40); JB('rs_prim'); JMP('ghost_prim')

# spirit133 (corpses 133, 203): 80% -> 241, 20% -> 133
lbl('spirit133'); B(0x83, 0xF9, 80); JB('ghost_prim'); JMP('s133_prim')

# ── Primaries ──
lbl('s216_prim');  B(0xBA); I32(216); JMP('exit')
lbl('s133_prim');  B(0xBA); I32(133); JMP('exit')
lbl('rs_prim');    B(0xBA); I32(130); JMP('exit')
lbl('ghost_prim'); B(0xBA); I32(241); JMP('exit')
lbl('glow_prim');  B(0xBA); I32(44);  JMP('exit')
lbl('exit');       B(0x5B); B(0x58); JMP_VA(JMP_RETURN)

# ── Table (293 bytes, index = dead body unit type ID, value = group 0–7) ──
lbl('table')
tbl = [0] * 293   # default = 0

# Group 1: major undead / "greater" units → 80% ghost (241), 20% spirit (130)
for u in [1,5,6,19,22,24,25,55,58,65,73,76,78,79,80,91,95,96,97,98,
          109,115,127,131,132,134,145,149,150,152,163,166,170,181,
          187,189,199,205,206,217,221,223,229,234,238,240,243,244,
          252,264,288,290,291]:
    tbl[u] = 1

# Group 2: ghost (241) corpse → 50/50
tbl[241] = 2

# Group 3: glow-adjacent units → 10% glow (44), 20% spirit (130), 70% ghost (241)
for u in [37, 41, 43, 289]:
    tbl[u] = 3

# Group 4: unit 42 → 40% glow (44), 20% spirit (130), 40% ghost (241)
tbl[42] = 4

# Group 5: glow creatures → 20% glow (44), 20% spirit (130), 60% ghost (241)
for u in [44, 224, 225, 226, 227, 282]:
    tbl[u] = 5

# Group 6: spirit 133 / related → 80% ghost (241), 20% spirit 133
for u in [133, 203]:
    tbl[u] = 6

# Group 7: spirit 216 / related → 90% ghost (241), 10% spirit 216
for u in [216, 292]:
    tbl[u] = 7

code.extend(tbl)

resolve()

code_sz = labels['table']
print(f"Cave code: {code_sz} bytes  Table: 293  Total: {len(code)} / {RS_CAVE_AVAIL}")
assert len(code) <= RS_CAVE_AVAIL, f"Cave overflow: {len(code)} > {RS_CAVE_AVAIL}"

delta = labels['table'] - labels['pic_next']
print(f"PICREL delta: {delta} (0x{delta:X})")

# Verify JMP back address
exit_off    = labels['exit']
jmp_e9_off  = exit_off + 2          # skip pop ebx (1) + pop eax (1)
next_ip_off = jmp_e9_off + 1 + 4   # skip E9 opcode + 4-byte operand
jmp_target  = (CAVE_VA + next_ip_off + struct.unpack_from('<i', code, jmp_e9_off + 1)[0]) & 0xFFFFFFFF
print(f"JMP back: 0x{jmp_target:08X}  expected: 0x{JMP_RETURN:08X}  {'OK' if jmp_target == JMP_RETURN else 'FAIL'}")
print(f"JMP patch (0xF9526): {JMP_PATCH_NEW.hex(' ')}")
print(f"CALL1 new (0x10BAFE): {CALL1_NEW.hex(' ')}")
print(f"CALL2 new (0x10BB34): {CALL2_NEW.hex(' ')}")
print(f"New sub   (0x{NEW_SUB_FILE_OFF:X}): {new_sub.hex(' ')}")

# ── Pre-checks ────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(JMP_PATCH_OFF);    cur_jmp    = f.read(5)
    f.seek(RS_CAVE_FILE_OFF); cur_cave   = f.read(len(code))
    f.seek(NEW_SUB_FILE_OFF); cur_sub    = f.read(NEW_SUB_SIZE)
    f.seek(CALL1_OFF);        cur_call1  = f.read(5)
    f.seek(CALL2_OFF);        cur_call2  = f.read(5)
    f.seek(OLD_SUB_FILE_OFF); cur_oldsub = f.read(OLD_SUB_SIZE)

assert cur_jmp   == JMP_PATCH_OLD,       f"0xF9526 not expected RS spawn instr: {cur_jmp.hex(' ')}"
assert cur_cave  == b'\x00' * len(code), f"Cave space not zero at 0x{RS_CAVE_FILE_OFF:X}: {cur_cave[:16].hex(' ')}..."
assert cur_sub   == b'\x00' * NEW_SUB_SIZE, f"New sub space not zero at 0x{NEW_SUB_FILE_OFF:X}"
assert cur_call1 == CALL1_OLD,           f"CALL1 unexpected: {cur_call1.hex(' ')}"
assert cur_call2 == CALL2_OLD,           f"CALL2 unexpected: {cur_call2.hex(' ')}"
assert cur_oldsub != b'\x00' * OLD_SUB_SIZE, "Old sub already zeroed!"

print("Pre-checks passed.")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(RS_CAVE_FILE_OFF); f.write(code)           # write RS spawn cave
    f.seek(NEW_SUB_FILE_OFF); f.write(new_sub)        # write new upkeep sub
    f.seek(JMP_PATCH_OFF);    f.write(JMP_PATCH_NEW)  # patch RS spawn JMP
    f.seek(CALL1_OFF);        f.write(CALL1_NEW)      # update RS summoned cave CALL
    f.seek(CALL2_OFF);        f.write(CALL2_NEW)      # update AD summoned cave CALL
    f.seek(OLD_SUB_FILE_OFF); f.write(b'\x00' * OLD_SUB_SIZE)  # zero old sub

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(RS_CAVE_FILE_OFF); assert f.read(len(code))   == bytes(code)
    f.seek(NEW_SUB_FILE_OFF); assert f.read(NEW_SUB_SIZE) == new_sub
    f.seek(JMP_PATCH_OFF);    assert f.read(5)            == JMP_PATCH_NEW
    f.seek(CALL1_OFF);        assert f.read(5)            == CALL1_NEW
    f.seek(CALL2_OFF);        assert f.read(5)            == CALL2_NEW
    f.seek(OLD_SUB_FILE_OFF); assert f.read(OLD_SUB_SIZE) == b'\x00' * OLD_SUB_SIZE

print("Written and verified OK.")
print()
print(f"  RS spawn JMP : 0x{JMP_PATCH_OFF:X}  {JMP_PATCH_OLD.hex(' ')} -> {JMP_PATCH_NEW.hex(' ')}")
print(f"  RS spawn cave: 0x{RS_CAVE_FILE_OFF:X}  ({len(code)} bytes, returns to 0x{0xF952B:X})")
print(f"  New upkeep   : 0x{NEW_SUB_FILE_OFF:X}  ({NEW_SUB_SIZE} bytes)")
print(f"  CALL1 update : 0x{CALL1_OFF:X}  {CALL1_OLD.hex(' ')} -> {CALL1_NEW.hex(' ')}")
print(f"  CALL2 update : 0x{CALL2_OFF:X}  {CALL2_OLD.hex(' ')} -> {CALL2_NEW.hex(' ')}")
print(f"  Old sub zero : 0x{OLD_SUB_FILE_OFF:X}  ({OLD_SUB_SIZE} bytes)")
print()
print("  RS spawn groups:")
print("    0 default   : 80% spirit(130)  / 20% ghost(241)")
print("    1 greater   : 80% ghost(241)   / 20% spirit(130)")
print("    2 g241_self : 50% ghost(241)   / 50% spirit(130)")
print("    3 glow_mix  : 10% glow(44)     / 20% spirit(130) / 70% ghost(241)")
print("    4 unit42    : 40% glow(44)     / 20% spirit(130) / 40% ghost(241)")
print("    5 glow      : 20% glow(44)     / 20% spirit(130) / 60% ghost(241)")
print("    6 spirit133 : 80% ghost(241)   / 20% spirit133")
print("    7 spirit216 : 90% ghost(241)   / 10% spirit216")
print()
print("  Upkeep by unit type: 243->15, 133->10, 204->10, 206->10, 216->8,")
print("                       44->6, 200->5, 223->5, 241->3, else->2")
