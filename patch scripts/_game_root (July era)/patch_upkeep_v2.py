import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

URI_VA = fva(0x4C7C8)

SUB_FILE_OFF = 0x10D04D   # shared upkeep subroutine (v1: 171 bytes)
SUB_V1_SIZE  = 171        # bytes currently occupied

# ── Build new upkeep subroutine (v2, 155 bytes) ───────────────────────────────
#
# Changes vs v1:
#   243  : 15 -> 8   (AD dragon)
#   204  : 10 -> 6   (AD horror)
#   206  : 10 -> 6   (AD wraith)
#   200  :  5 -> 3   (AD horse)
#   223  :  5 -> 3   (AD mummy)
#
# Unchanged:
#   133  : 10        (RS spirit133)
#   216  :  8        (RS spirit216)
#   44   :  6        (RS glow)
#   241  :  3        (RS ghost)
#   else :  2        (201 swordsman, 202 hound, 249 ram-sub, 130 spirit …)
#
def build_sub():
    sub_va = fva(SUB_FILE_OFF)
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

    # Prologue (16 bytes) — identical to v1
    B(0x8B, 0x4B, 0x10)   # mov ecx, [ebx+10h]   TUnitEnchantmentAbilityData
    B(0x8B, 0x49, 0x10)   # mov ecx, [ecx+10h]   TUnitEnchantment
    B(0x51)               # push ecx
    B(0x8B, 0x43, 0x40)   # mov eax, [ebx+40h]   TUnitResource ptr
    B(0xE8); I32((URI_VA - (sub_va + here() + 4)) & 0xFFFFFFFF)  # call URI
    B(0x59)               # pop ecx

    # CMP chains: 9 pairs × 11 bytes = 99 bytes
    B(0x3D); I32(133); JE('set10')   # RS spirit133 (unchanged)
    B(0x3D); I32(243); JE('set8')    # AD dragon    (15 -> 8)
    B(0x3D); I32(216); JE('set8')    # RS spirit216 (unchanged)
    B(0x3D); I32(204); JE('set6')    # AD horror    (10 -> 6)
    B(0x3D); I32(206); JE('set6')    # AD wraith    (10 -> 6)
    B(0x3D); I32(44);  JE('set6')    # RS glow      (unchanged)
    B(0x3D); I32(200); JE('set3')    # AD horse     (5 -> 3)
    B(0x3D); I32(223); JE('set3')    # AD mummy     (5 -> 3)
    B(0x3D); I32(241); JE('set3')    # RS ghost     (unchanged)
    SET(2)   # default: 201/202/249 (AD) and 130 (RS)

    lbl('set10'); SET(10)
    lbl('set8');  SET(8)
    lbl('set6');  SET(6)
    lbl('set3');  SET(3)

    resolve()
    return bytes(s)

new_sub = build_sub()
print(f"New sub: {len(new_sub)} bytes  (was {SUB_V1_SIZE})")
print(f"  {new_sub.hex(' ')}")

# The 16 trailing bytes of the old slot become zeros (after the last RET, unreachable)
full_block = new_sub + b'\x00' * (SUB_V1_SIZE - len(new_sub))
assert len(full_block) == SUB_V1_SIZE

# ── Pre-checks ────────────────────────────────────────────────────────────────
PROLOGUE_SIG = bytes([0x8B, 0x4B, 0x10, 0x8B, 0x49, 0x10, 0x51, 0x8B])  # first 8 bytes

with open(DLL, 'rb') as f:
    f.seek(SUB_FILE_OFF)
    cur = f.read(SUB_V1_SIZE)

assert cur[:8] == PROLOGUE_SIG, f"Sub prologue mismatch: {cur[:8].hex(' ')}"
assert cur != b'\x00' * SUB_V1_SIZE, "Sub already zeroed!"
assert cur != full_block, "v2 already applied!"
print("Pre-checks passed.")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(SUB_FILE_OFF)
    f.write(full_block)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(SUB_FILE_OFF)
    assert f.read(SUB_V1_SIZE) == full_block

print("Written and verified OK.")
print()
print("  Upkeep changes:")
print("    243 (dragon) : 15 -> 8")
print("    204 (horror) : 10 -> 6")
print("    206 (wraith) : 10 -> 6")
print("    200 (horse)  :  5 -> 3")
print("    223 (mummy)  :  5 -> 3")
print()
print("  Unchanged:")
print("    133 -> 10, 216 -> 8, 44 -> 6, 241 -> 3, else -> 2")
