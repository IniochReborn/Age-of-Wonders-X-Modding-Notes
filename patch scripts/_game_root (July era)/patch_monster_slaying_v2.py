import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

VTABLE_HAS_ABILITY = 0x148

ID_MONSTER = 0x70
ID_SLAYING = 0x3F
ID_HERO    = 0x82

JMP_PATCH_OFF = 0x66D04
NOP_OFF       = 0x66D09
NOP_SIZE      = 40
RETURN_OFF    = 0x66D31
CAVE_OFF      = 0x10D0F8
CAVE_AVAIL    = 325

# v1 JMP patch (unchanged — cave starts at same address)
JMP_PATCH_EXPECTED = b'\xe9\xef\x63\x0a\x00'

# ── Build cave v2 ─────────────────────────────────────────────────────────────
#
# Fix: Hero ability (0x82) is a static editor-assigned TUnit ability, not a
# TCombatUnit runtime flag.  Must check [ESI+4Ch] (TUnit) rather than ESI
# (TCombatUnit) — same pattern used by the game itself at 0x24159:
#   8B 46 4C  mov eax, [esi+4Ch]   ← was: 8B C6  mov eax, esi
#
# Monster (0x70) is a TCombatUnit runtime flag → still checked on ESI directly.
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
def JNZ(n):     B(0x0F, 0x85); fixups.append((here(), n)); I32(0)
def JMP(n):     B(0xE9);       fixups.append((here(), n)); I32(0)
def JMP_VA(va): B(0xE9); I32((va - (CAVE_VA + here() + 4)) & 0xFFFFFFFF)

def HASCALL_REG(reg, ability_id):
    """Check ability on a register directly (TCombatUnit runtime flags). 15 bytes."""
    B(0xBA); I32(ability_id)
    if   reg == 'esi': B(0x8B, 0xC6)
    elif reg == 'edi': B(0x8B, 0xC7)
    B(0x8B, 0x08)
    B(0xFF, 0x91); I32(VTABLE_HAS_ABILITY)

def HASCALL_DEREF(reg, offset, ability_id):
    """Check ability on [reg+offset] (TUnit static abilities). 16 bytes for offset<=0x7F."""
    B(0xBA); I32(ability_id)
    # mov eax, [reg+offset]
    if   reg == 'esi': B(0x8B, 0x46, offset)
    elif reg == 'edi': B(0x8B, 0x47, offset)
    B(0x8B, 0x08)
    B(0xFF, 0x91); I32(VTABLE_HAS_ABILITY)

def resolve():
    for off, name in fixups:
        struct.pack_into('<I', code, off, (labels[name] - off - 4) & 0xFFFFFFFF)

# Step 1: Does attacker (EDI) have Monster Slaying (0x3F)?
HASCALL_REG('edi', ID_SLAYING)   # 15 bytes — TCombatUnit runtime flag
B(0x84, 0xC0); JZ('exit')

# Step 2: Does target (ESI) have Monster (0x70)?
HASCALL_REG('esi', ID_MONSTER)   # 15 bytes — TCombatUnit runtime flag
B(0x50)                           # push eax (save monster_flag)

# Step 3: Does target (ESI) have Hero (0x82)?
# Use [esi+4Ch] (TUnit) — editor-assigned static abilities live at TUnit level,
# not in the TCombatUnit runtime flags.  Pattern from game code at 0x24159.
HASCALL_DEREF('esi', 0x4C, ID_HERO)  # 16 bytes
B(0x59)                               # pop ecx (ecx = monster_flag)

# Dispatch
B(0x84, 0xC0); JNZ('has_hero')
B(0x84, 0xC9); JZ('exit')
# Monster only → +2
B(0x83, 0x03, 0x02); B(0x83, 0x43, 0x04, 0x02); JMP('exit')

lbl('has_hero')
B(0x84, 0xC9); JZ('hero_only')
# Both → +3
B(0x83, 0x03, 0x03); B(0x83, 0x43, 0x04, 0x03); JMP('exit')

lbl('hero_only')
# Hero only → +2
B(0x83, 0x03, 0x02); B(0x83, 0x43, 0x04, 0x02)

lbl('exit')
JMP_VA(fva(RETURN_OFF))

resolve()

print(f"Cave v2: {len(code)} bytes / {CAVE_AVAIL} available")
assert len(code) <= CAVE_AVAIL, f"Cave overflow: {len(code)}"

# ── Pre-checks ────────────────────────────────────────────────────────────────
# v1 cave first 5 bytes: BA 3F 00 00 00 (mov edx, ID_SLAYING)
V1_CAVE_SIG = bytes([0xBA, ID_SLAYING, 0x00, 0x00, 0x00])

with open(DLL, 'rb') as f:
    f.seek(JMP_PATCH_OFF);  cur_jmp  = f.read(5)
    f.seek(CAVE_OFF);       cur_cave = f.read(5)
    f.seek(NOP_OFF);        cur_nop  = f.read(5)

assert cur_jmp  == JMP_PATCH_EXPECTED, f"JMP not v1: {cur_jmp.hex(' ')}"
assert cur_cave == V1_CAVE_SIG,        f"Cave not v1: {cur_cave.hex(' ')}"
assert cur_nop  == b'\x90' * 5,        f"NOP range not NOPs: {cur_nop.hex(' ')}"

print("Pre-checks passed (v1 state confirmed).")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    # Zero old cave then write new (in case new is smaller, though it's larger)
    f.seek(CAVE_OFF); f.write(b'\x00' * CAVE_AVAIL)
    f.seek(CAVE_OFF); f.write(code)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(CAVE_OFF); assert f.read(len(code)) == bytes(code)

print("Written and verified OK.")
print()
print("  Fix: Hero check now uses [ESI+4Ch] (TUnit) instead of ESI (TCombatUnit)")
print("  Monster check unchanged — TCombatUnit runtime flag (ESI direct)")
print()
print("  Monster Slaying (0x3F):")
print("    vs Monster only   : +2 damage, +2 attack")
print("    vs Hero only      : +2 damage, +2 attack")
print("    vs Monster + Hero : +3 damage, +3 attack")
