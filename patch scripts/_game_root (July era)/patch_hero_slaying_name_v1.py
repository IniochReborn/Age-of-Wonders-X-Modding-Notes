import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

# ── Overview ──────────────────────────────────────────────────────────────────
#
# Problem:
#   TResurrectedAbility (0x80) and TCombatResurrectedAbility (0x82) both load
#   their display name via LoadResString using the SAME resource string pointer
#   at [L558E8FE0] -> ResurrectedRStr (ID 0xFE31, native "Resurrected").
#   TranslateRStr then does a MLD dictionary lookup by string content:
#     "Resurrected" -> "Hero" (EN, as set by user)
#   Both abilities therefore display as "Hero".
#
# Fix (code-cave approach):
#   Patch TCombatResurrectedAbility.Create (file 0xB9DE3) to call a small
#   trampoline cave instead of LoadResString.  The trampoline calls
#   @LStrFromString with a constant ShortString "Hero Slaying", filling the
#   same local AnsiString variable that LoadResString would have filled.
#   TranslateRStr then receives "Hero Slaying" as its lookup key.
#
#   Result:
#     • Ability 0x80 (TResurrectedAbility)         -> name "Hero" (unchanged)
#     • Ability 0x82 (TCombatResurrectedAbility)    -> name "Hero Slaying"
#
# MLD note:
#   TranslateRStr performs a text-key lookup against the loaded MLD dictionary.
#   If "Hero Slaying" is not in the MLD the library typically returns the key
#   unchanged, so the ability shows "Hero Slaying" natively.  For full
#   multi-language support, add a new entry to ResStr.mld:
#     Native:  Hero Slaying
#     English: Hero Slaying
#     (+ other languages as desired)
#   The native slot value is the lookup key.
#
# ── Layout ────────────────────────────────────────────────────────────────────
#
# Patch site (TCombatResurrectedAbility.Create):
#   File 0xB9DE3 (VA 0x557BA9E3) — 10 bytes
#   OLD: A1 E0 8F 8E 55   mov eax,[L558E8FE0]     (5 bytes)
#        E8 23 68 F4 FF   call LoadResString        (5 bytes)
#   NEW: E8 xx xx xx xx   call cave_fn             (5 bytes)
#        90 90 90 90 90   nop * 5
#
# Cave (file 0x10D169, VA 0x5580DD69) — 26 bytes in free zero space:
#   +0  (13 bytes): ShortString: byte(12) + 'Hero Slaying'
#   +13 ( 2 bytes): 89 D0          mov eax, edx     ; edx = &AnsiStr from caller
#   +15 ( 5 bytes): BA [ssva]      mov edx, shortstr_va
#   +20 ( 5 bytes): E8 [rel]       call @LStrFromString
#   +25 ( 1 byte ): C3             ret
#
# Calling convention for @LStrFromString (Delphi 3):
#   EAX = var AnsiString (dest), EDX = @ShortString (source)
#   The caller (constructor) has already done 'lea edx,[ebp-08h]' before our
#   call, so EDX holds the address of the local AnsiString variable.

# ── Constants ─────────────────────────────────────────────────────────────────

PATCH_FILE = 0xB9DE3        # mov eax,[L558E8FE0] in TCombatResurrectedAbility.Create
PATCH_VA   = fva(PATCH_FILE)
PATCH_OLD  = bytes([0xA1, 0xE0, 0x8F, 0x8E, 0x55,   # mov eax,[L558E8FE0]
                    0xE8, 0x23, 0x68, 0xF4, 0xFF])    # call LoadResString

CAVE_FILE  = 0x10D169       # start of free zero area
CAVE_VA    = fva(CAVE_FILE)
CAVE_AVAIL = 213            # bytes free (per MEMORY.md)

# @LStrFromString jmp-stub: stub index 45, each stub 8 bytes, base VA 0x55701000
LSTRFROMSTRING_VA = 0x55701000 + 45 * 8  # 0x55701168

# ── Build cave ────────────────────────────────────────────────────────────────

shortstr_va = CAVE_VA + 0          # address of ShortString in memory
cave_fn_va  = CAVE_VA + 13         # address of trampoline function

cave = bytearray()

# ShortString "Hero Slaying" (12 chars)
cave.append(12)                    # length byte
cave.extend(b'Hero Slaying')       # 12 bytes
assert len(cave) == 13

# Trampoline function
cave.extend([0x89, 0xD0])          # mov eax, edx   (edx = &AnsiStr from caller)
cave.extend([0xBA])                # mov edx, imm32
cave.extend(struct.pack('<I', shortstr_va))          # addr of ShortString
# call @LStrFromString (relative from next instruction)
call_instr_va = cave_fn_va + 2 + 5
next_instr_va = call_instr_va + 5
rel_call = (LSTRFROMSTRING_VA - next_instr_va) & 0xFFFFFFFF
cave.extend([0xE8])
cave.extend(struct.pack('<I', rel_call))
cave.append(0xC3)                  # ret

assert len(cave) == 26, f"Cave size wrong: {len(cave)}"
assert len(cave) <= CAVE_AVAIL

# ── Build patch ───────────────────────────────────────────────────────────────

# call cave_fn (relative from next instruction)
next_after_call = PATCH_VA + 5
rel_patch = (cave_fn_va - next_after_call) & 0xFFFFFFFF
patch_new = bytearray([0xE8]) + bytearray(struct.pack('<I', rel_patch))
patch_new += bytearray([0x90] * 5)   # NOPs for the remaining 5 bytes

assert len(patch_new) == 10

# ── Pre-checks ────────────────────────────────────────────────────────────────

with open(DLL, 'rb') as f:
    f.seek(PATCH_FILE); cur_patch = f.read(10)
    f.seek(CAVE_FILE);  cur_cave  = f.read(CAVE_AVAIL)

assert cur_patch == PATCH_OLD, \
    f"Patch site mismatch at 0x{PATCH_FILE:X}: {cur_patch.hex(' ')}"
assert cur_cave == b'\x00' * CAVE_AVAIL, \
    f"Cave not zero at 0x{CAVE_FILE:X}: {cur_cave[:16].hex(' ')}..."

print("Pre-checks passed.")
print(f"  Patch: {PATCH_OLD.hex(' ')} -> {bytes(patch_new).hex(' ')}")
print(f"  Cave:  {len(cave)} bytes at file 0x{CAVE_FILE:X} (VA 0x{CAVE_VA:X})")

# ── Apply ─────────────────────────────────────────────────────────────────────

with open(DLL, 'r+b') as f:
    f.seek(CAVE_FILE);  f.write(cave)
    f.seek(PATCH_FILE); f.write(patch_new)

# ── Verify ────────────────────────────────────────────────────────────────────

with open(DLL, 'rb') as f:
    f.seek(CAVE_FILE);  assert f.read(len(cave))    == bytes(cave)
    f.seek(PATCH_FILE); assert f.read(len(patch_new)) == bytes(patch_new)

print("Written and verified OK.")
print()
print("  TCombatResurrectedAbility (0x82) now loads 'Hero Slaying' as its")
print("  display name key, bypassing the shared ResurrectedRStr resource string.")
print()
print("  TResurrectedAbility (0x80) is unchanged -> still translates via")
print("  ResurrectedRStr -> MLD 'Resurrected' -> 'Hero' (EN).")
print()
print("  ACTION REQUIRED: add a new entry to ResStr.mld (via MLDEdit.exe):")
print("    Native:  Hero Slaying")
print("    English: Hero Slaying")
print("    (+ DE/FR/IT/ES translations as desired)")
print("  The native text is the MLD lookup key.  If the entry is absent,")
print("  the game falls back to displaying 'Hero Slaying' natively.")
