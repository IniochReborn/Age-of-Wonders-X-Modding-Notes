import struct

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

# New cave locations (v4 — two 49-byte caves)
CAVE1_FILE_OFF = 0x10BA70          # TRecallSpiritCA.Execute
CAVE2_FILE_OFF = 0x10BA70 + 49     # 0x10BAA1 — TAnimateDeadCA.Execute

# Patch sites (BA opcode)
PATCH1_FILE_OFF = 0xF9549
PATCH2_FILE_OFF = 0xF9769

# Return sites (= patch + 15)
RET1_FILE_OFF = PATCH1_FILE_OFF + 15   # 0xF9558
RET2_FILE_OFF = PATCH2_FILE_OFF + 15   # 0xF9778

# Old v3 caves to clear
OLD_CAVE1_FILE_OFF = 0x10BA18
OLD_CAVE2_FILE_OFF = 0x10BA44
OLD_CAVE_SIZE      = 44

# ── Cave code (49 bytes each) ─────────────────────────────────────────────────
# Root issue: ExpandAbility.Expand copies [unit+18h] into [enchant+18h] as the
# source unit ID. Our dummy value of 1 hits another player's unit in FindUnit(1),
# causing GetSourceName to attribute the display to that player's name.
#
# Fix: after ExpandAbility, zero [enchant+18h] before calling SetSource.
# This makes FindUnit(0) return nil -> GetSourceName falls straight to the path
# that reads [enchant+0Ch] (the correct player) for the display string.
#
# C7 43 18 01 00 00 00   mov dword ptr [ebx+18h], 1    ; pass assertion [unit+18h]>0
# BA 9B 00 00 00         mov edx, 0x9B                  ; ability ID = Summoned
# 8B C3                  mov eax, ebx                   ; EAX = unit
# 8B 08                  mov ecx, [eax]                 ; ECX = vtable
# FF 91 94 00 00 00      call [ecx+94h]                 ; ExpandAbility(unit, 0x9B)
# 8B 43 10               mov eax, [ebx+10h]             ; TUnitEnchantmentAbilityData
# 8B 40 10               mov eax, [eax+10h]             ; TUnitEnchantment
# 31 D2                  xor edx, edx                   ; EDX = 0
# 89 50 18               mov [eax+18h], edx             ; clear source unit ID -> FindUnit(0)=nil
# 8A 53 24               mov dl, [ebx+24h]              ; DL = unit's player (low byte only)
# 8B 08                  mov ecx, [eax]                 ; ECX = TUnitEnchantment vtable
# FF 91 58 00 00 00      call [ecx+58h]                 ; SetSource(enchant, player)
# E9 xx xx xx xx         jmp <return site>
# ─────────────────────────────────────────────────────────────────────────────

def build_cave(cave_file_off, ret_file_off):
    code = bytearray()
    code += b'\xC7\x43\x18\x01\x00\x00\x00'  # mov dword ptr [ebx+18h], 1
    code += b'\xBA\x9B\x00\x00\x00'           # mov edx, 0x9B
    code += b'\x8B\xC3'                        # mov eax, ebx
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x94\x00\x00\x00'       # call [ecx+94h]  ExpandAbility
    code += b'\x8B\x43\x10'                    # mov eax, [ebx+10h]
    code += b'\x8B\x40\x10'                    # mov eax, [eax+10h]
    code += b'\x31\xD2'                        # xor edx, edx
    code += b'\x89\x50\x18'                    # mov [eax+18h], edx  (zero source unit ID)
    code += b'\x8A\x53\x24'                    # mov dl, [ebx+24h]   (player byte)
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x58\x00\x00\x00'       # call [ecx+58h]  SetSource
    # JMP back
    jmp_src_va = fva(cave_file_off + len(code) + 5)
    jmp_dst_va = fva(ret_file_off)
    rel = (jmp_dst_va - jmp_src_va) & 0xFFFFFFFF
    code += b'\xE9' + struct.pack('<I', rel)
    assert len(code) == 49
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

# ── Pre-checks (verify v3 state) ─────────────────────────────────────────────
V3_SIG = bytes([0xC7, 0x43, 0x18, 0x01, 0x00, 0x00, 0x00])

with open(DLL, 'rb') as f:
    f.seek(PATCH1_FILE_OFF);    cur_p1      = f.read(1)
    f.seek(PATCH2_FILE_OFF);    cur_p2      = f.read(1)
    f.seek(OLD_CAVE1_FILE_OFF); old_c1_sig  = f.read(7)
    f.seek(OLD_CAVE2_FILE_OFF); old_c2_sig  = f.read(7)
    f.seek(CAVE1_FILE_OFF);     new_space   = f.read(100)

assert cur_p1     == b'\xE9',  f"Patch1 not JMP: {cur_p1.hex()}"
assert cur_p2     == b'\xE9',  f"Patch2 not JMP: {cur_p2.hex()}"
assert old_c1_sig == V3_SIG,   f"Old cave1 unexpected: {old_c1_sig.hex(' ')}"
assert old_c2_sig == V3_SIG,   f"Old cave2 unexpected: {old_c2_sig.hex(' ')}"
assert new_space  == b'\x00' * 100, \
    f"New cave space not zero at 0x{CAVE1_FILE_OFF:X}: {new_space[:16].hex(' ')}..."

print("Pre-checks passed (v3 state confirmed).")
print(f"Cave1 @ 0x{CAVE1_FILE_OFF:X}  (VA 0x{fva(CAVE1_FILE_OFF):08X}): {cave1.hex(' ')}")
print(f"Cave2 @ 0x{CAVE2_FILE_OFF:X}  (VA 0x{fva(CAVE2_FILE_OFF):08X}): {cave2.hex(' ')}")
print(f"Patch1 @ 0x{PATCH1_FILE_OFF:X}: {patch1.hex(' ')}")
print(f"Patch2 @ 0x{PATCH2_FILE_OFF:X}: {patch2.hex(' ')}")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(CAVE1_FILE_OFF);       f.write(cave1)
    f.seek(CAVE2_FILE_OFF);       f.write(cave2)
    f.seek(PATCH1_FILE_OFF);      f.write(patch1)
    f.seek(PATCH2_FILE_OFF);      f.write(patch2)
    f.seek(OLD_CAVE1_FILE_OFF);   f.write(b'\x00' * OLD_CAVE_SIZE)
    f.seek(OLD_CAVE2_FILE_OFF);   f.write(b'\x00' * OLD_CAVE_SIZE)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(CAVE1_FILE_OFF);     assert f.read(49) == cave1
    f.seek(CAVE2_FILE_OFF);     assert f.read(49) == cave2
    f.seek(PATCH1_FILE_OFF);    assert f.read(15) == patch1
    f.seek(PATCH2_FILE_OFF);    assert f.read(15) == patch2
    f.seek(OLD_CAVE1_FILE_OFF); assert f.read(OLD_CAVE_SIZE) == b'\x00' * OLD_CAVE_SIZE
    f.seek(OLD_CAVE2_FILE_OFF); assert f.read(OLD_CAVE_SIZE) == b'\x00' * OLD_CAVE_SIZE

print("Written and verified OK.")
print()
print(f"  TRecallSpiritCA : 0x{PATCH1_FILE_OFF:X} -> cave @ 0x{CAVE1_FILE_OFF:X} -> ret 0x{RET1_FILE_OFF:X}")
print(f"  TAnimateDeadCA  : 0x{PATCH2_FILE_OFF:X} -> cave @ 0x{CAVE2_FILE_OFF:X} -> ret 0x{RET2_FILE_OFF:X}")
print()
print("  Cave: [ebx+18h]=1, ExpandAbility(0x9B), zero [enchant+18h], SetSource(enchant,player)")
print("        [enchant+18h]=0 -> FindUnit(0)=nil -> GetSourceName shows correct player name")
