# 1) Rebuild graphics: TStructure.GetTerrainTypeImage checks GetRazed BEFORE
#    GetBuilding, so a razed structure under rebuild keeps the razed image
#    (idx 22-24 / 0x16-0x18) instead of the rebuild images (idx 25-27 / 0x19-0x1B).
#    Hook the entry: if building ([self+24h] != FF) return 0x19/0x1A/0x1B by
#    terrain type (3->0x1A, 5->0x1B, else 0x19), else resume original flow.
#    Affects all TStructure classes that don't override slot +12Ch.
#
# 2) Unraze refresh: SetRazed(false) cave path now also calls
#    TReflectingPool.UpdateReflectingPoolsExploration so pool vision updates
#    on the rebuild-completion turn (bit must be cleared first).
import shutil, sys

BASE = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude"
DLL = BASE + r"\AoWEPACK.dll"
BAK = DLL + ".bak_rebuild_gfx"
VA = 0x55700C00  # VA = file offset + VA

def rel32(target_va, next_instr_va):
    return (target_va - next_instr_va) & 0xFFFFFFFF

# --- addresses ---
GTTI_ENTRY   = 0x5DAA0            # TStructure.GetTerrainTypeImage
GTTI_RESUME  = VA + GTTI_ENTRY + 6
UPDATE_RPE   = VA + 0xD4484       # TReflectingPool.UpdateReflectingPoolsExploration
SETRAZED_JZ  = 0x10B705           # jz in SetRazed v2 cave (74 1C -> 74 76)
CAVE_COMMON  = VA + 0x10B727      # SetRazed cave common: image recompute + ret

EXT_OFF = 0x10B77D                # unraze extension cave
EXT_VA  = VA + EXT_OFF
GFX_OFF = 0x10B790                # building-image cave
GFX_VA  = VA + GFX_OFF

# --- ext cave: and byte[ebx+39h],0FEh; mov eax,ebx; call UpdateRPE; jmp common ---
ext = bytearray()
ext += bytes.fromhex("80633 9FE".replace(" ", ""))   # and byte [ebx+39h],0xFE
ext += bytes.fromhex("8BC3")                          # mov eax,ebx
ext += b"\xE8" + rel32(UPDATE_RPE, EXT_VA + len(ext) + 5).to_bytes(4, "little")
ext += b"\xE9" + rel32(CAVE_COMMON, EXT_VA + len(ext) + 5).to_bytes(4, "little")
assert len(ext) == 0x10, len(ext)

# --- gfx cave ---
gfx = bytearray()
gfx += bytes.fromhex("807824FF")      # cmp byte [eax+24h],0xFF  (GetBuilding inline)
gfx += bytes.fromhex("741C")          # jz  +0x22 (orig)
gfx += bytes.fromhex("B819000000")    # mov eax,0x19
gfx += bytes.fromhex("83FA03")        # cmp edx,3
gfx += bytes.fromhex("7506")          # jnz +0x16
gfx += bytes.fromhex("B81A000000")    # mov eax,0x1A
gfx += bytes.fromhex("C3")            # ret
gfx += bytes.fromhex("83FA05")        # cmp edx,5
gfx += bytes.fromhex("7506")          # jnz +0x21
gfx += bytes.fromhex("B81B000000")    # mov eax,0x1B
gfx += bytes.fromhex("C3")            # ret
gfx += bytes.fromhex("C3")            # ret (eax=0x19)
assert len(gfx) == 0x22, len(gfx)
gfx += bytes.fromhex("53568BF28BD8")  # replicated entry: push ebx/esi; mov esi,edx; mov ebx,eax
gfx += b"\xE9" + rel32(GTTI_RESUME, GFX_VA + len(gfx) + 5).to_bytes(4, "little")
assert len(gfx) == 0x2D, len(gfx)

# --- entry hook ---
hook = b"\xE9" + rel32(GFX_VA, VA + GTTI_ENTRY + 5).to_bytes(4, "little") + b"\x90"

with open(DLL, "rb") as f:
    data = bytearray(f.read())

if bytes(data[GTTI_ENTRY:GTTI_ENTRY+6]) == hook:
    print("Already patched."); sys.exit(0)

# preflight
if bytes(data[GTTI_ENTRY:GTTI_ENTRY+6]) != bytes.fromhex("53568BF28BD8"):
    print("GTTI entry unexpected:", data[GTTI_ENTRY:GTTI_ENTRY+6].hex(" ")); sys.exit(1)
if bytes(data[SETRAZED_JZ:SETRAZED_JZ+2]) != bytes.fromhex("741C"):
    print("SetRazed jz unexpected:", data[SETRAZED_JZ:SETRAZED_JZ+2].hex(" ")); sys.exit(1)
if bytes(data[EXT_OFF:GFX_OFF+len(gfx)]) != b"\x00" * (GFX_OFF + len(gfx) - EXT_OFF):
    print("Cave space not empty"); sys.exit(1)
if bytes(data[0xD4484:0xD4487]) != bytes.fromhex("535657"):
    print("UpdateRPE entry unexpected"); sys.exit(1)

shutil.copyfile(DLL, BAK)
data[EXT_OFF:EXT_OFF+len(ext)] = ext
data[GFX_OFF:GFX_OFF+len(gfx)] = gfx
data[GTTI_ENTRY:GTTI_ENTRY+6] = hook
data[SETRAZED_JZ+1] = 0x76        # jz -> ext cave (0x10B77D)
with open(DLL, "wb") as f:
    f.write(data)
print(f"Patched. ext@{EXT_OFF:#x}({len(ext)}B) gfx@{GFX_OFF:#x}({len(gfx)}B) "
      f"hook@{GTTI_ENTRY:#x} jz@{SETRAZED_JZ:#x}. Backup: {BAK}")
