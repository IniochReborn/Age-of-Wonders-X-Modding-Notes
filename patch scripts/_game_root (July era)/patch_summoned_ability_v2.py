import struct

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

# Cave locations — same cave1 base as v1, cave2 shifts to cave1+27 due to larger cave size
CAVE1_FILE_OFF = 0x10B9C2   # for TRecallSpiritCA.Execute  (same as v1)
CAVE2_FILE_OFF = 0x10B9C2 + 27   # 0x10B9DD — for TAnimateDeadCA.Execute

# Patch sites (full 15-byte sequences, BA at these offsets)
PATCH1_FILE_OFF = 0xF9549   # TRecallSpiritCA.Execute
PATCH2_FILE_OFF = 0xF9769   # TAnimateDeadCA.Execute

# Return sites (= patch + 15)
RET1_FILE_OFF = PATCH1_FILE_OFF + 15   # 0xF9558
RET2_FILE_OFF = PATCH2_FILE_OFF + 15   # 0xF9778

# ── Cave code (27 bytes) ──────────────────────────────────────────────────────
# Root cause: TUnitEnchantmentAbility.Expand asserts [unit+18h] > 0.
# TAnimateDeadCA creates the unit but never calls Place(), so [unit+18h] = 0
# → Assert fires → EAssertionFailed → caught as "Error during Token Execute".
#
# Fix: set [unit+18h] = 1 before calling ExpandAbility, so the assertion passes.
# This also creates TUnitEnchantmentAbilityData properly, preventing a secondary
# crash in GetSourceName which dereferences [data+10h] without a nil check.
#
# C7 43 18 01 00 00 00   mov dword ptr [ebx+18h], 1   ; pass assertion [unit+18h]>0
# BA 9B 00 00 00          mov edx, 0x9B               ; ability ID = Summoned
# 8B C3                   mov eax, ebx                ; EAX = unit (self)
# 8B 08                   mov ecx, [eax]              ; ECX = vtable
# FF 91 94 00 00 00       call [ecx+94h]              ; ExpandAbility(unit,0x9B)
# E9 xx xx xx xx          jmp <return site>
# ─────────────────────────────────────────────────────────────────────────────

def build_cave(cave_file_off, ret_file_off):
    code = bytearray()
    code += b'\xC7\x43\x18\x01\x00\x00\x00'  # mov dword ptr [ebx+18h], 1
    code += b'\xBA\x9B\x00\x00\x00'           # mov edx, 0x9B
    code += b'\x8B\xC3'                        # mov eax, ebx
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x94\x00\x00\x00'       # call [ecx+94h]
    # JMP back
    jmp_src_va = fva(cave_file_off + len(code) + 5)
    jmp_dst_va = fva(ret_file_off)
    rel = (jmp_dst_va - jmp_src_va) & 0xFFFFFFFF
    code += b'\xE9' + struct.pack('<I', rel)
    assert len(code) == 27
    return bytes(code)

cave1 = build_cave(CAVE1_FILE_OFF, RET1_FILE_OFF)
cave2 = build_cave(CAVE2_FILE_OFF, RET2_FILE_OFF)

# ── Build 15-byte JMP patches ─────────────────────────────────────────────────
def build_jmp_patch(patch_file_off, cave_file_off):
    jmp_next_ip_va = fva(patch_file_off + 5)
    cave_va        = fva(cave_file_off)
    rel = (cave_va - jmp_next_ip_va) & 0xFFFFFFFF
    return b'\xE9' + struct.pack('<I', rel) + b'\x90' * 10

patch1 = build_jmp_patch(PATCH1_FILE_OFF, CAVE1_FILE_OFF)
patch2 = build_jmp_patch(PATCH2_FILE_OFF, CAVE2_FILE_OFF)

assert len(patch1) == 15
assert len(patch2) == 15

# ── Pre-checks (verify v1 state) ─────────────────────────────────────────────
V1_CAVE1 = bytes([0xBA,0x9B,0x00,0x00,0x00,0x8B,0xC3,0x53,0x8B,0x18,
                  0xB1,0x01,0xFF,0x53,0x50,0x5B,0xE9])  # first 17 bytes of v1 cave

with open(DLL, 'rb') as f:
    f.seek(PATCH1_FILE_OFF); cur_p1 = f.read(1)
    f.seek(PATCH2_FILE_OFF); cur_p2 = f.read(1)
    f.seek(CAVE1_FILE_OFF);  cur_c1 = f.read(17)
    # cave2 (old) started at 0x10B9D7
    f.seek(0x10B9D7);        cur_c2 = f.read(17)
    # verify both caves free from 0x10B9EE onward (beyond v1 cave2 end)
    f.seek(0x10B9EE);        tail = f.read(18)

assert cur_p1 == b'\xE9', f"Patch1 not JMP: {cur_p1.hex()}"
assert cur_p2 == b'\xE9', f"Patch2 not JMP: {cur_p2.hex()}"
assert cur_c1[:17] == V1_CAVE1, f"Cave1 unexpected: {cur_c1.hex(' ')}"
assert cur_c2[:17] == V1_CAVE1, f"Cave2 unexpected: {cur_c2.hex(' ')}"
assert tail == b'\x00' * 18, f"Tail not zero: {tail.hex(' ')}"

print("Pre-checks passed (v1 caves confirmed).")
print(f"Cave1 @ 0x{CAVE1_FILE_OFF:X}  (VA 0x{fva(CAVE1_FILE_OFF):08X}): {cave1.hex(' ')}")
print(f"Cave2 @ 0x{CAVE2_FILE_OFF:X}  (VA 0x{fva(CAVE2_FILE_OFF):08X}): {cave2.hex(' ')}")
print(f"Patch1 @ 0x{PATCH1_FILE_OFF:X}: {patch1.hex(' ')}")
print(f"Patch2 @ 0x{PATCH2_FILE_OFF:X}: {patch2.hex(' ')}")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(CAVE1_FILE_OFF);  f.write(cave1)
    f.seek(CAVE2_FILE_OFF);  f.write(cave2)
    f.seek(PATCH1_FILE_OFF); f.write(patch1)
    f.seek(PATCH2_FILE_OFF); f.write(patch2)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(CAVE1_FILE_OFF);  assert f.read(27) == cave1
    f.seek(CAVE2_FILE_OFF);  assert f.read(27) == cave2
    f.seek(PATCH1_FILE_OFF); assert f.read(15) == patch1
    f.seek(PATCH2_FILE_OFF); assert f.read(15) == patch2

print("Written and verified OK.")
print()
print(f"  TRecallSpiritCA : 0x{PATCH1_FILE_OFF:X} -> cave @ 0x{CAVE1_FILE_OFF:X} -> ret 0x{RET1_FILE_OFF:X}")
print(f"  TAnimateDeadCA  : 0x{PATCH2_FILE_OFF:X} -> cave @ 0x{CAVE2_FILE_OFF:X} -> ret 0x{RET2_FILE_OFF:X}")
print()
print("  Cave: [ebx+18h]=1 to pass TUnitEnchantmentAbility.Expand assertion,")
print("        then ExpandAbility(0x9B) = Summoned via vtable[0x94h].")
