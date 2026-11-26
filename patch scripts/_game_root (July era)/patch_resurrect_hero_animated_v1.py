import struct

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"

# ── Patch site ────────────────────────────────────────────────────────────────
#
# TResurrectHero.ExecuteTE  (GlobalSpells unit, VMT slot 20, file 0xEB414)
# vs TAnimateHero.ExecuteTE (same structure,    VMT slot 20, file 0xEB97C)
#
# Both functions are structurally identical.  The only semantic difference is
# one vtable dispatch byte at offset +0x1DC into TResurrectHero.ExecuteTE:
#
#   call [edx+0x1B0]   ->  TUnit.MakeResurrected  (grants ability 0x82)
#   call [edx+0x1B4]   ->  TUnit.MakeAnimated     (grants ability 0x84)
#
# TAnimateHero.ExecuteTE calls vtable[0x1B4] at the same position.
# Changing b0 -> b4 makes TResurrectHero call the same Animated method.
#
PATCH_OFF = 0xEB5F0   # byte 2 of 'ff 92 b0 01 00 00'  (the 0x1B0 low byte)
OLD_BYTE  = 0xB0      # vtable offset 0x1B0 -> MakeResurrected (ability 0x82)
NEW_BYTE  = 0xB4      # vtable offset 0x1B4 -> MakeAnimated     (ability 0x84)

# Full instruction context for pre-check
INSN_OFF  = 0xEB5EE
INSN_OLD  = bytes([0xFF, 0x92, 0xB0, 0x01, 0x00, 0x00])  # call [edx+0x1B0]
INSN_NEW  = bytes([0xFF, 0x92, 0xB4, 0x01, 0x00, 0x00])  # call [edx+0x1B4]

# ── Pre-check ─────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(INSN_OFF)
    cur = f.read(6)

assert cur == INSN_OLD, f"Unexpected bytes at 0x{INSN_OFF:X}: {cur.hex(' ')}"
print("Pre-check passed — original 'call [edx+0x1B0]' confirmed.")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(PATCH_OFF)
    f.write(bytes([NEW_BYTE]))

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(INSN_OFF)
    result = f.read(6)

assert result == INSN_NEW, f"Verify failed: {result.hex(' ')}"
print("Written and verified OK.")
print()
print("  TResurrectHero.ExecuteTE:")
print("    Before: call [edx+0x1B0]  -> MakeResurrected (ability 0x82)")
print("    After:  call [edx+0x1B4]  -> MakeAnimated    (ability 0x84)")
print()
print("  Heroes resurrected by Resurrect Hero now receive the Animated")
print("  ability instead of the Resurrected ability.")
