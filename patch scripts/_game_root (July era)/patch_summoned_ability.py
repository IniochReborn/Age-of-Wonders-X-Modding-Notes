import struct

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

# Cave locations (first free space after the 813-byte Animate Dead spawn cave)
CAVE1_FILE_OFF = 0x10B9C2   # for TRecallSpiritCA.Execute
CAVE2_FILE_OFF = 0x10B9D7   # for TAnimateDeadCA.Execute (CAVE1 + 21)

# Patch sites (full 15-byte instruction sequence: BA xx xx xx xx 8B C3 8B 08 FF 91 94 00 00 00)
PATCH1_FILE_OFF = 0xF9549   # TRecallSpiritCA.Execute — opcode BA at this offset
PATCH2_FILE_OFF = 0xF9769   # TAnimateDeadCA.Execute  — opcode BA at this offset

# Return sites (= patch + 15)
RET1_FILE_OFF = PATCH1_FILE_OFF + 15   # 0xF9558
RET2_FILE_OFF = PATCH2_FILE_OFF + 15   # 0xF9778

# ── Build a 21-byte cave ──────────────────────────────────────────────────────
# On entry: EBX = newly created TUnit, EDX = (will be overwritten), EAX = (scratch)
# Goal: call SetAbSet(EAX=unit, EDX=0x9B, CL=1) via vtable[0x50h]
# Strategy mirrors TAbility.Expand: use EBX for vtable so CL=1 is preserved.
#
# BA 9B 00 00 00  mov edx, 0x9B        ; ability ID = Summoned
# 8B C3           mov eax, ebx         ; EAX = unit
# 53              push ebx             ; save unit on stack (EBX will hold vtable)
# 8B 18           mov ebx, [eax]       ; EBX = vtable ([eax] == [ebx] since eax=ebx)
# B1 01           mov cl, 1            ; flag=1 (set ability)  — CL safe, ECX not vtable
# FF 53 50        call [ebx+0x50]      ; SetAbSet(EAX=unit, EDX=0x9B, CL=1)
# 5B              pop ebx              ; restore EBX = unit
# E9 xx xx xx xx  jmp <return site>
# ─────────────────────────────────────────────────────────────────────────────

def build_cave(cave_file_off, ret_file_off):
    code = bytearray()
    code += b'\xBA\x9B\x00\x00\x00'   # mov edx, 0x9B
    code += b'\x8B\xC3'               # mov eax, ebx
    code += b'\x53'                    # push ebx
    code += b'\x8B\x18'               # mov ebx, [eax]
    code += b'\xB1\x01'               # mov cl, 1
    code += b'\xFF\x53\x50'           # call [ebx+0x50]
    code += b'\x5B'                    # pop ebx
    # JMP back: relative from (cave + len(code) + 5) to ret
    jmp_src_va  = fva(cave_file_off + len(code) + 5)   # next IP after JMP
    jmp_dst_va  = fva(ret_file_off)
    rel = (jmp_dst_va - jmp_src_va) & 0xFFFFFFFF
    code += b'\xE9' + struct.pack('<I', rel)
    assert len(code) == 21
    return bytes(code)

cave1 = build_cave(CAVE1_FILE_OFF, RET1_FILE_OFF)
cave2 = build_cave(CAVE2_FILE_OFF, RET2_FILE_OFF)

# ── Build 15-byte patch: JMP to cave + 10 NOPs ───────────────────────────────
def build_jmp_patch(patch_file_off, cave_file_off):
    jmp_next_ip_va = fva(patch_file_off + 5)
    cave_va        = fva(cave_file_off)
    rel = (cave_va - jmp_next_ip_va) & 0xFFFFFFFF
    return b'\xE9' + struct.pack('<I', rel) + b'\x90' * 10

patch1 = build_jmp_patch(PATCH1_FILE_OFF, CAVE1_FILE_OFF)
patch2 = build_jmp_patch(PATCH2_FILE_OFF, CAVE2_FILE_OFF)

assert len(patch1) == 15
assert len(patch2) == 15

# ── Verify existing bytes before patching ─────────────────────────────────────
EXPECTED = bytes([0xBA, 0x9B, 0x00, 0x00, 0x00,
                  0x8B, 0xC3, 0x8B, 0x08,
                  0xFF, 0x91, 0x94, 0x00, 0x00, 0x00])

with open(DLL, 'rb') as f:
    f.seek(PATCH1_FILE_OFF); cur1 = f.read(15)
    f.seek(PATCH2_FILE_OFF); cur2 = f.read(15)
    f.seek(CAVE1_FILE_OFF);  cav1_pre = f.read(21)
    f.seek(CAVE2_FILE_OFF);  cav2_pre = f.read(21)

assert cur1 == EXPECTED, \
    f"Patch1 pre-check failed: {cur1.hex(' ')}"
assert cur2 == EXPECTED, \
    f"Patch2 pre-check failed: {cur2.hex(' ')}"
assert cav1_pre == b'\x00' * 21, \
    f"Cave1 not zero: {cav1_pre.hex(' ')}"
assert cav2_pre == b'\x00' * 21, \
    f"Cave2 not zero: {cav2_pre.hex(' ')}"

print("Pre-checks passed.")
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
    f.seek(CAVE1_FILE_OFF);  assert f.read(21) == cave1
    f.seek(CAVE2_FILE_OFF);  assert f.read(21) == cave2
    f.seek(PATCH1_FILE_OFF); assert f.read(15) == patch1
    f.seek(PATCH2_FILE_OFF); assert f.read(15) == patch2

print("Written and verified OK.")
print()
print(f"  TRecallSpiritCA  : 0x{PATCH1_FILE_OFF:X} -> cave @ 0x{CAVE1_FILE_OFF:X} -> ret 0x{RET1_FILE_OFF:X}")
print(f"  TAnimateDeadCA   : 0x{PATCH2_FILE_OFF:X} -> cave @ 0x{CAVE2_FILE_OFF:X} -> ret 0x{RET2_FILE_OFF:X}")
