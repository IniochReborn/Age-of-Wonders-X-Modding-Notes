import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

# ── Addresses ────────────────────────────────────────────────────────────────
JMP_PATCH_OFF = 0x66D04    # BA 70 00 00 00  (mov edx, Monster) — branch target of jae above
NOP_OFF       = 0x66D09    # start of bytes to NOP (mov eax, esi onward)
NOP_SIZE      = 40         # 0x66D09 through 0x66D30 inclusive
RETURN_OFF    = 0x66D31    # 8B C7  (next instruction after Dragon Slaying block)

CAVE_OFF      = 0x10D0F8   # free space (~325 bytes available)
CAVE_AVAIL    = 325

# ── Ability IDs ──────────────────────────────────────────────────────────────
ID_MONSTER = 0x70   # 112 — Monster (Dragon) ability — checked on TARGET  (ESI)
ID_SLAYING = 0x3F   # 63  — Monster Slaying ability  — checked on ATTACKER (EDI)
ID_HERO    = 0x82   # 130 — Hero (repurposed Resurrected) — checked on TARGET (ESI)

VTABLE_HAS_ABILITY = 0x148  # call [ecx+0x148] → AL = 0/1

# ── JMP patch bytes ──────────────────────────────────────────────────────────
JMP_PATCH_OLD = bytes([0xBA, 0x70, 0x00, 0x00, 0x00])
_rel = (fva(CAVE_OFF) - fva(JMP_PATCH_OFF + 5)) & 0xFFFFFFFF
JMP_PATCH_NEW = b'\xE9' + struct.pack('<I', _rel)
assert len(JMP_PATCH_NEW) == 5

# ── Build cave ────────────────────────────────────────────────────────────────
#
# On entry (same state as original code at 0x66D04):
#   ESI = target unit,  EDI = attacker unit,  EBX = &{damage, attack} bonus struct
#   EAX/ECX/EDX volatile; EBX/ESI/EDI/EBP preserved
#
# Logic:
#   1. Check attacker (EDI) has Monster Slaying (0x3F)  → if not, skip all
#   2. Check target  (ESI) has Monster (0x70)           → save result
#   3. Check target  (ESI) has Hero    (0x82)           → save result
#   4a. Both Monster + Hero  → +3 damage, +3 attack
#   4b. Monster only         → +2 damage, +2 attack
#   4c. Hero only            → +2 damage, +2 attack
#   4d. Neither              → no bonus
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

def HASCALL(obj_reg, ability_id):
    """Emit: HasAbility(obj_reg, ability_id) -> AL.  15 bytes."""
    B(0xBA); I32(ability_id)              # mov edx, ability_id
    if   obj_reg == 'esi': B(0x8B, 0xC6) # mov eax, esi
    elif obj_reg == 'edi': B(0x8B, 0xC7) # mov eax, edi
    B(0x8B, 0x08)                         # mov ecx, [eax]
    B(0xFF, 0x91); I32(VTABLE_HAS_ABILITY) # call [ecx+0x148]

def resolve():
    for off, name in fixups:
        struct.pack_into('<I', code, off, (labels[name] - off - 4) & 0xFFFFFFFF)

# Step 1: Does attacker have Monster Slaying?
HASCALL('edi', ID_SLAYING)  # 15 bytes
B(0x84, 0xC0); JZ('exit')   # test al, al; jz exit

# Step 2: Does target have Monster?
HASCALL('esi', ID_MONSTER)  # 15 bytes
B(0x50)                     # push eax  (save monster_flag; stack +4)

# Step 3: Does target have Hero?
HASCALL('esi', ID_HERO)     # 15 bytes
B(0x59)                     # pop ecx   (ecx = monster_flag; stack restored)
                             # eax = hero_flag

# Dispatch on (hero_flag, monster_flag)
B(0x84, 0xC0); JNZ('has_hero')   # test al, al; jnz has_hero

# No Hero — check Monster
B(0x84, 0xC9); JZ('exit')        # test cl, cl; jz exit (neither)
# Monster only → +2
B(0x83, 0x03, 0x02)              # add [ebx],   2
B(0x83, 0x43, 0x04, 0x02)        # add [ebx+4], 2
JMP('exit')

lbl('has_hero')
B(0x84, 0xC9); JZ('hero_only')   # test cl, cl; jz hero_only (Hero only)
# Both Monster + Hero → +3
B(0x83, 0x03, 0x03)              # add [ebx],   3
B(0x83, 0x43, 0x04, 0x03)        # add [ebx+4], 3
JMP('exit')

lbl('hero_only')
# Hero only → +2
B(0x83, 0x03, 0x02)              # add [ebx],   2
B(0x83, 0x43, 0x04, 0x02)        # add [ebx+4], 2

lbl('exit')
JMP_VA(fva(RETURN_OFF))          # jmp back to 0x66D31

resolve()

print(f"Cave: {len(code)} bytes / {CAVE_AVAIL} available")
assert len(code) <= CAVE_AVAIL, f"Cave overflow: {len(code)}"

# ── Pre-checks ────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(JMP_PATCH_OFF); cur_jmp  = f.read(5)
    f.seek(CAVE_OFF);      cur_cave = f.read(len(code))

assert cur_jmp  == JMP_PATCH_OLD,        f"Patch site not original: {cur_jmp.hex(' ')}"
assert cur_cave == b'\x00' * len(code),  f"Cave not zero at 0x{CAVE_OFF:X}: {cur_cave[:8].hex(' ')}..."

print("Pre-checks passed.")
print(f"JMP patch: {JMP_PATCH_OLD.hex(' ')} -> {JMP_PATCH_NEW.hex(' ')} @ 0x{JMP_PATCH_OFF:X}")
print(f"NOP: 0x{NOP_OFF:X}–0x{NOP_OFF+NOP_SIZE-1:X} ({NOP_SIZE} bytes)")
print(f"Cave: 0x{CAVE_OFF:X} ({len(code)} bytes)")
print(f"Return: 0x{RETURN_OFF:X}")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(CAVE_OFF);      f.write(code)
    f.seek(JMP_PATCH_OFF); f.write(JMP_PATCH_NEW)
    f.seek(NOP_OFF);       f.write(b'\x90' * NOP_SIZE)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(CAVE_OFF);      assert f.read(len(code))  == bytes(code)
    f.seek(JMP_PATCH_OFF); assert f.read(5)           == JMP_PATCH_NEW
    f.seek(NOP_OFF);       assert f.read(NOP_SIZE)    == b'\x90' * NOP_SIZE

print("Written and verified OK.")
print()
print("  Monster Slaying (0x3F) now:")
print("    vs Monster only         : +2 damage, +2 attack")
print("    vs Hero only            : +2 damage, +2 attack")
print("    vs Monster + Hero       : +3 damage, +3 attack")
print("    vs neither              :  0")
print("  (Monster=0x70, Hero=0x82, checked on target ESI)")
print("  (Slaying=0x3F, checked on attacker EDI)")
