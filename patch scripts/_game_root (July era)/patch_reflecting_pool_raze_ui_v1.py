"""
Reflecting Pool Raze patch v1 - UI part (AoWx.exe).

The side info window (TIWindow) picks a per-class handler when a structure is
selected. Handlers for TMine/TPowerNode/TFarm/TTower/TAltar each show RazePnl
(form field +0x10C); every other owned TPlayerStructure (incl. TReflectingPool)
falls through to a generic handler that never shows it - that's why the engine
patch alone gave no raze button.

Patch: redirect the generic fallthrough's 'jmp end' (file 0x43511) into a cave
that sets RazePnl.Visible = structure.GetRazeable (vtable +0x154), then jumps
back. Works for any structure whose resource razeable flag is set, so it is
driven by the AoWEPACK.dll data patch.

Cave lives in .idata tail slack (file 0x6BF80, VA 0x46E380); .idata section
gets the EXECUTE characteristic so DEP-enabled systems still run it.

Registers at patch point: ebx = structure, esi = TIWindow instance (both
callee-saved across the generic handler call). [vmt+0x6C] = SetVisible(dl).
"""
import shutil, struct, sys

EXE = "AoWx.exe"
BAK = "AoWx.exe.bak_reflecting_pool_raze_ui"
FILE2VA = 0x400C00  # CODE: VA = file offset + this

SITE_JMP   = 0x43511         # e9 e7 00 00 00 -> end 0x435FD
SITE_EXPECT = bytes.fromhex("8BD38BC6E833FEFFFF" "E9E7000000")  # from 0x43508
END_VA     = 0x435FD + FILE2VA          # 0x4441FD
CAVE_FILE  = 0x6BF80
CAVE_VA    = 0x46E380                   # RVA 0x6E380 (.idata)

data = bytearray(open(EXE, "rb").read())

# --- validate ---
if data[0x43508:0x43508 + len(SITE_EXPECT)] != SITE_EXPECT:
    sys.exit("FAIL: dispatcher fallthrough bytes mismatch - wrong exe version?")
if any(data[CAVE_FILE:CAVE_FILE + 0x40]):
    sys.exit("FAIL: cave area not empty")

# .idata section header: verify and add EXECUTE
pe = struct.unpack_from("<I", data, 0x3C)[0]
off = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
idata_hdr = None
for i in range(struct.unpack_from("<H", data, pe + 6)[0]):
    if data[off:off + 8].rstrip(b"\x00") == b".idata":
        idata_hdr = off
    off += 40
if idata_hdr is None:
    sys.exit("FAIL: .idata header not found")
chars = struct.unpack_from("<I", data, idata_hdr + 36)[0]
assert chars == 0xC0000040, f".idata characteristics unexpected: {chars:08X}"

# sanity: RVA math for the cave
vsz, va = struct.unpack_from("<II", data, idata_hdr + 8)
ro = struct.unpack_from("<I", data, idata_hdr + 20)[0]
assert CAVE_FILE - ro + va + 0x400000 == CAVE_VA, "cave VA mismatch"
assert CAVE_FILE >= ro + vsz, "cave overlaps used .idata"

print("validated - applying")
shutil.copyfile(EXE, BAK)
print(f"  backup -> {BAK}")

# --- cave ---
#   mov eax,ebx; mov ecx,[eax]; call [ecx+154h]   ; al = GetRazeable
#   mov dl,al
#   mov eax,[esi+10Ch]                            ; RazePnl
#   mov ecx,[eax]; call [ecx+6Ch]                 ; SetVisible(dl)
#   jmp end
cave = bytes.fromhex("8BC38B08FF91540100008AD08B860C0100008B08FF516C") \
    + b"\xE9" + struct.pack("<i", END_VA - (CAVE_VA + 23 + 5))
assert len(cave) == 28
data[CAVE_FILE:CAVE_FILE + len(cave)] = cave

# --- redirect site jmp into cave ---
data[SITE_JMP:SITE_JMP + 5] = b"\xE9" + struct.pack(
    "<i", CAVE_VA - (SITE_JMP + FILE2VA + 5))

# --- .idata += EXECUTE ---
struct.pack_into("<I", data, idata_hdr + 36, 0xE0000040)

open(EXE, "wb").write(data)
print("done:")
print(f"  jmp @ 0x{SITE_JMP:X} -> cave VA 0x{CAVE_VA:X} (file 0x{CAVE_FILE:X})")
print(f"  cave: {cave.hex(' ')}")
print(f"  .idata characteristics C0000040 -> E0000040")
