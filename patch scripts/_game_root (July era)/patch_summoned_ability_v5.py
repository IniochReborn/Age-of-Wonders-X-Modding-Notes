import struct

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

URI_VA = fva(0x4C7C8)   # TUnitResource.UnitResourceIndex(self) -> EAX = unit type ID

# New cave locations (v5 — 54 bytes each)
CAVE1_FILE_OFF = 0x10BAD2    # TRecallSpiritCA.Execute
CAVE2_FILE_OFF = 0x10BB08    # TAnimateDeadCA.Execute  (CAVE1 + 54)

# Shared upkeep subroutine — placed in the 109 remaining bytes after the
# Animate Dead cave (0x10C20D + 902 = 0x10C593, 109 bytes to end of zero block)
SUB_FILE_OFF   = 0x10C593

# Patch sites
PATCH1_FILE_OFF = 0xF9549
PATCH2_FILE_OFF = 0xF9769

# Return sites (= patch + 15)
RET1_FILE_OFF = PATCH1_FILE_OFF + 15   # 0xF9558
RET2_FILE_OFF = PATCH2_FILE_OFF + 15   # 0xF9778

# Old v4 caves to clear
OLD_CAVE1_FILE_OFF = 0x10BA70
OLD_CAVE2_FILE_OFF = 0x10BAA1
OLD_CAVE_SIZE      = 49

# ── Build upkeep subroutine (103 bytes) ──────────────────────────────────────
# Called after SetSource. EBX = unit ptr (callee-preserved, still valid).
# Re-derives enchant ptr from [EBX+10h][+10h], gets unit type ID via
# UnitResourceIndex([EBX+40h]), writes the correct upkeep to [enchant+10h]:
#   243        -> 15 mana  (dragon)
#   204, 206   -> 10 mana  (horror, wraith)
#   200, 223   ->  5 mana  (horse, mummy)
#   else       ->  2 mana  (swordsman 201, hound 202, ram/horror-sub 249)
# ─────────────────────────────────────────────────────────────────────────────
def build_subroutine(sub_file_off):
    sub_va = fva(sub_file_off)
    s = bytearray()
    labels = {}
    fixups = []

    def here(): return len(s)
    def lbl(n): labels[n] = here()
    def B(*bs): s.extend(bs)
    def I32(v): s.extend(struct.pack('<I', v & 0xFFFFFFFF))
    def JE(n): B(0x0F, 0x84); fixups.append((here(), n)); I32(0)
    def resolve():
        for off, name in fixups:
            struct.pack_into('<I', s, off, (labels[name] - off - 4) & 0xFFFFFFFF)
    def SET(val):
        B(0xC7, 0x41, 0x10); I32(val)   # mov dword [ecx+10h], val
        B(0xC3)                           # ret

    B(0x8B, 0x4B, 0x10)   # mov ecx, [ebx+10h]  TUnitEnchantmentAbilityData
    B(0x8B, 0x49, 0x10)   # mov ecx, [ecx+10h]  TUnitEnchantment
    B(0x51)               # push ecx            save enchant (ECX trashed by call)
    B(0x8B, 0x43, 0x40)   # mov eax, [ebx+40h]  TUnitResource ptr
    B(0xE8); I32((URI_VA - (sub_va + here() + 4)) & 0xFFFFFFFF)  # call UnitResourceIndex
    B(0x59)               # pop ecx             restore enchant ptr

    B(0x3D); I32(243); JE('set15')
    B(0x3D); I32(204); JE('set10')
    B(0x3D); I32(206); JE('set10')
    B(0x3D); I32(200); JE('set5')
    B(0x3D); I32(223); JE('set5')
    SET(2)   # default: 201, 202, 249

    lbl('set15'); SET(15)
    lbl('set10'); SET(10)
    lbl('set5');  SET(5)

    resolve()
    assert len(s) == 103, f"Subroutine size mismatch: {len(s)}"
    return bytes(s)

sub = build_subroutine(SUB_FILE_OFF)

# ── Build cave (54 bytes each) ────────────────────────────────────────────────
# Identical to v4 with one addition: `call set_upkeep_sub` before the jmp back.
#
# C7 43 18 01 00 00 00   mov [ebx+18h], 1          ; pass assertion
# BA 9B 00 00 00         mov edx, 0x9B              ; Summoned ability ID
# 8B C3                  mov eax, ebx
# 8B 08                  mov ecx, [eax]
# FF 91 94 00 00 00      call [ecx+94h]             ; ExpandAbility
# 8B 43 10               mov eax, [ebx+10h]         ; TUnitEnchantmentAbilityData
# 8B 40 10               mov eax, [eax+10h]         ; TUnitEnchantment
# 31 D2                  xor edx, edx
# 89 50 18               mov [eax+18h], edx         ; clear source unit ID
# 8A 53 24               mov dl, [ebx+24h]          ; player
# 8B 08                  mov ecx, [eax]
# FF 91 58 00 00 00      call [ecx+58h]             ; SetSource -> RegisterEnchantment
# E8 xx xx xx xx         call set_upkeep_sub        ; set [enchant+10h] by unit type
# E9 xx xx xx xx         jmp <return site>
# ─────────────────────────────────────────────────────────────────────────────
def build_cave(cave_file_off, ret_file_off):
    cave_va = fva(cave_file_off)
    sub_va  = fva(SUB_FILE_OFF)
    code = bytearray()

    code += b'\xC7\x43\x18\x01\x00\x00\x00'  # mov dword [ebx+18h], 1
    code += b'\xBA\x9B\x00\x00\x00'           # mov edx, 0x9B
    code += b'\x8B\xC3'                        # mov eax, ebx
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x94\x00\x00\x00'       # call [ecx+94h]  ExpandAbility
    code += b'\x8B\x43\x10'                    # mov eax, [ebx+10h]
    code += b'\x8B\x40\x10'                    # mov eax, [eax+10h]
    code += b'\x31\xD2'                        # xor edx, edx
    code += b'\x89\x50\x18'                    # mov [eax+18h], edx
    code += b'\x8A\x53\x24'                    # mov dl, [ebx+24h]
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x58\x00\x00\x00'       # call [ecx+58h]  SetSource

    # call set_upkeep_sub
    next_ip = cave_va + len(code) + 5
    code += b'\xE8' + struct.pack('<I', (sub_va - next_ip) & 0xFFFFFFFF)

    # jmp back
    next_ip = cave_va + len(code) + 5
    code += b'\xE9' + struct.pack('<I', (fva(ret_file_off) - next_ip) & 0xFFFFFFFF)

    assert len(code) == 54
    return bytes(code)

cave1 = build_cave(CAVE1_FILE_OFF, RET1_FILE_OFF)
cave2 = build_cave(CAVE2_FILE_OFF, RET2_FILE_OFF)

# ── Build 15-byte JMP patches ─────────────────────────────────────────────────
def build_jmp_patch(patch_file_off, cave_file_off):
    rel = (fva(cave_file_off) - fva(patch_file_off + 5)) & 0xFFFFFFFF
    return b'\xE9' + struct.pack('<I', rel) + b'\x90' * 10

patch1 = build_jmp_patch(PATCH1_FILE_OFF, CAVE1_FILE_OFF)
patch2 = build_jmp_patch(PATCH2_FILE_OFF, CAVE2_FILE_OFF)
assert len(patch1) == 15 and len(patch2) == 15

# ── Pre-checks (verify v4 state) ─────────────────────────────────────────────
V4_SIG = bytes([0xC7, 0x43, 0x18, 0x01, 0x00, 0x00, 0x00])

with open(DLL, 'rb') as f:
    f.seek(PATCH1_FILE_OFF);    cur_p1     = f.read(1)
    f.seek(PATCH2_FILE_OFF);    cur_p2     = f.read(1)
    f.seek(OLD_CAVE1_FILE_OFF); old_c1_sig = f.read(7)
    f.seek(OLD_CAVE2_FILE_OFF); old_c2_sig = f.read(7)
    f.seek(CAVE1_FILE_OFF);     sp1        = f.read(54)
    f.seek(CAVE2_FILE_OFF);     sp2        = f.read(54)
    f.seek(SUB_FILE_OFF);       sp_sub     = f.read(len(sub))

assert cur_p1     == b'\xE9',  f"Patch1 not JMP: {cur_p1.hex()}"
assert cur_p2     == b'\xE9',  f"Patch2 not JMP: {cur_p2.hex()}"
assert old_c1_sig == V4_SIG,   f"Old cave1 sig mismatch: {old_c1_sig.hex(' ')}"
assert old_c2_sig == V4_SIG,   f"Old cave2 sig mismatch: {old_c2_sig.hex(' ')}"
assert sp1        == b'\x00' * 54,       f"Cave1 space not zero at 0x{CAVE1_FILE_OFF:X}"
assert sp2        == b'\x00' * 54,       f"Cave2 space not zero at 0x{CAVE2_FILE_OFF:X}"
assert sp_sub     == b'\x00' * len(sub), f"Sub space not zero at 0x{SUB_FILE_OFF:X}"

print("Pre-checks passed (v4 state confirmed).")
print(f"Sub  @ 0x{SUB_FILE_OFF:X}  ({len(sub)} bytes): {sub.hex(' ')}")
print(f"Cave1@ 0x{CAVE1_FILE_OFF:X} ({len(cave1)} bytes): {cave1.hex(' ')}")
print(f"Cave2@ 0x{CAVE2_FILE_OFF:X} ({len(cave2)} bytes): {cave2.hex(' ')}")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(SUB_FILE_OFF);       f.write(sub)
    f.seek(CAVE1_FILE_OFF);     f.write(cave1)
    f.seek(CAVE2_FILE_OFF);     f.write(cave2)
    f.seek(PATCH1_FILE_OFF);    f.write(patch1)
    f.seek(PATCH2_FILE_OFF);    f.write(patch2)
    f.seek(OLD_CAVE1_FILE_OFF); f.write(b'\x00' * OLD_CAVE_SIZE)
    f.seek(OLD_CAVE2_FILE_OFF); f.write(b'\x00' * OLD_CAVE_SIZE)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(SUB_FILE_OFF);       assert f.read(len(sub)) == sub
    f.seek(CAVE1_FILE_OFF);     assert f.read(54) == cave1
    f.seek(CAVE2_FILE_OFF);     assert f.read(54) == cave2
    f.seek(PATCH1_FILE_OFF);    assert f.read(15) == patch1
    f.seek(PATCH2_FILE_OFF);    assert f.read(15) == patch2
    f.seek(OLD_CAVE1_FILE_OFF); assert f.read(OLD_CAVE_SIZE) == b'\x00' * OLD_CAVE_SIZE
    f.seek(OLD_CAVE2_FILE_OFF); assert f.read(OLD_CAVE_SIZE) == b'\x00' * OLD_CAVE_SIZE

print("Written and verified OK.")
print()
print(f"  TRecallSpiritCA : 0x{PATCH1_FILE_OFF:X} -> cave @ 0x{CAVE1_FILE_OFF:X} -> ret 0x{RET1_FILE_OFF:X}")
print(f"  TAnimateDeadCA  : 0x{PATCH2_FILE_OFF:X} -> cave @ 0x{CAVE2_FILE_OFF:X} -> ret 0x{RET2_FILE_OFF:X}")
print(f"  Upkeep sub      : 0x{SUB_FILE_OFF:X}  unit->upkeep: 243->15, 204/206->10, 200/223->5, else->2")
