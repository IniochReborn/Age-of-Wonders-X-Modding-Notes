import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

VTABLE_HAS_ABILITY = 0x148

# Ability IDs
ID_MONSTER_SLAYING = 0x3F   # attacker — TCombatUnit runtime flag
ID_MONSTER         = 0x70   # target  — TCombatUnit runtime flag
ID_HERO_SLAYING    = 0x82   # attacker — TCombatResurrectedAbility, TUnit static
ID_HERO            = 0x80   # target  — TResurrectedAbility,        TUnit static

# Layout (unchanged from v1/v2)
JMP_PATCH_OFF = 0x66D04
NOP_OFF       = 0x66D09
NOP_SIZE      = 40
RETURN_OFF    = 0x66D31
CAVE_OFF      = 0x10D0F8
CAVE_AVAIL    = 325

JMP_PATCH_EXPECTED = b'\xe9\xef\x63\x0a\x00'

# ── Build cave v3 ─────────────────────────────────────────────────────────────
#
# Monster Slaying (0x3F):  attacker (EDI) TCombatUnit runtime flag
#   vs Monster (0x70):     target  (ESI) TCombatUnit runtime flag  → +2/+2
#
# Hero Slaying (0x82):     attacker (EDI) TUnit static ability via [EDI+4Ch]
#   vs Hero (0x80):        target  (ESI) TUnit static ability via [ESI+4Ch]  → +2/+2
#
CAVE_VA = fva(CAVE_OFF)
code    = bytearray()
labels  = {}
fixups  = []

def here():     return len(code)
def lbl(n):     labels[n] = here()
def B(*bs):     code.extend(bs)
def I32(v):     code.extend(struct.pack('<I', v & 0xFFFFFFFF))
def JZ(n):      B(0x0F, 0x84); fixups.append((here(), n)); I32(0)
def JMP_VA(va): B(0xE9); I32((va - (CAVE_VA + here() + 4)) & 0xFFFFFFFF)

def HASCALL_REG(reg, ability_id):
    """HasAbility on TCombatUnit directly (runtime flags). 15 bytes."""
    B(0xBA); I32(ability_id)
    if   reg == 'esi': B(0x8B, 0xC6)
    elif reg == 'edi': B(0x8B, 0xC7)
    B(0x8B, 0x08)
    B(0xFF, 0x91); I32(VTABLE_HAS_ABILITY)

def HASCALL_DEREF(reg, offset, ability_id):
    """HasAbility on [reg+offset] (TUnit static abilities). 16 bytes."""
    B(0xBA); I32(ability_id)
    if   reg == 'esi': B(0x8B, 0x46, offset)
    elif reg == 'edi': B(0x8B, 0x47, offset)
    B(0x8B, 0x08)
    B(0xFF, 0x91); I32(VTABLE_HAS_ABILITY)

def resolve():
    for off, name in fixups:
        struct.pack_into('<I', code, off, (labels[name] - off - 4) & 0xFFFFFFFF)

# ── Monster Slaying ───────────────────────────────────────────────────────────
HASCALL_REG('edi', ID_MONSTER_SLAYING)      # attacker has Monster Slaying?
B(0x84, 0xC0); JZ('skip_ms')               # no → skip
HASCALL_REG('esi', ID_MONSTER)              # target has Monster?
B(0x84, 0xC0); JZ('skip_ms')               # no → skip
B(0x83, 0x03, 0x02)                         # add [ebx],   2
B(0x83, 0x43, 0x04, 0x02)                   # add [ebx+4], 2

lbl('skip_ms')

# ── Hero Slaying ──────────────────────────────────────────────────────────────
HASCALL_DEREF('edi', 0x4C, ID_HERO_SLAYING) # attacker has Hero Slaying? (TUnit)
B(0x84, 0xC0); JZ('exit')                   # no → exit
HASCALL_DEREF('esi', 0x4C, ID_HERO)         # target has Hero? (TUnit)
B(0x84, 0xC0); JZ('exit')                   # no → exit
B(0x83, 0x03, 0x02)                         # add [ebx],   2
B(0x83, 0x43, 0x04, 0x02)                   # add [ebx+4], 2

lbl('exit')
JMP_VA(fva(RETURN_OFF))

resolve()

print(f"Cave v3: {len(code)} bytes / {CAVE_AVAIL} available")
assert len(code) <= CAVE_AVAIL, f"Cave overflow: {len(code)}"

# ── Pre-checks ────────────────────────────────────────────────────────────────
# v1/v2 caves both start with ba 3f 00 00 00 (Monster Slaying HasAbility)
V2_CAVE_SIG = bytes([0xBA, ID_MONSTER_SLAYING, 0x00, 0x00, 0x00])

with open(DLL, 'rb') as f:
    f.seek(JMP_PATCH_OFF); cur_jmp  = f.read(5)
    f.seek(CAVE_OFF);      cur_cave = f.read(5)
    f.seek(NOP_OFF);       cur_nop  = f.read(5)

assert cur_jmp  == JMP_PATCH_EXPECTED, f"JMP not v1: {cur_jmp.hex(' ')}"
assert cur_cave == V2_CAVE_SIG,        f"Cave not v1/v2: {cur_cave.hex(' ')}"
assert cur_nop  == b'\x90' * 5,        f"NOP range not NOPs: {cur_nop.hex(' ')}"

print("Pre-checks passed (v1/v2 state confirmed).")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(CAVE_OFF); f.write(b'\x00' * CAVE_AVAIL)
    f.seek(CAVE_OFF); f.write(code)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(CAVE_OFF); assert f.read(len(code)) == bytes(code)

print("Written and verified OK.")
print()
print("  Monster Slaying (0x3F):")
print("    vs Monster (0x70) : +2 damage, +2 attack")
print("    vs other          : no bonus")
print()
print("  Hero Slaying (0x82):")
print("    vs Hero (0x80)    : +2 damage, +2 attack")
print("    vs other          : no bonus")
print()
print("  (Hero Slaying checked via [EDI+4Ch] TUnit — static editor ability)")
print("  (Hero        checked via [ESI+4Ch] TUnit — static editor ability)")
