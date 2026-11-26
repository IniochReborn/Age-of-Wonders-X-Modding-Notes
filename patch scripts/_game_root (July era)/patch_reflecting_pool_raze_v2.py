"""
Reflecting Pool Raze v2 (AoWEPACK.dll) - fixes from in-game test:
1. Appearance didn't change until save/reload: SetRazed now recomputes the
   cached terrain-type image [self+0x14] = GetTerrainTypeImage([self+0x18])
   (vtable +0x12C), exactly like Teleport.SetRazed does. On load this happens
   automatically, which is why reload showed the razed look.
2. Cross-pool vision: razing now goes through SetPlayer(-1) (vtable +0x1F0)
   instead of manual Deactivate+owner clear. SetPlayer delists from the owner,
   updates self unfog/exploration, and calls UpdateReflectingPoolsExploration
   (re-evaluates every OWNED pool's vision). After the razed bit is set we
   call UpdateUnfog (vtable +0x204) once more so the pool re-fogs even when
   the current player still owns other pools.
3. PoolVisionPlayer gets a razed-guard trampoline: a razed pool answers "no
   vision" to everyone - it drops out of the pool reflection network for
   both cached unfog evaluation and live 0x110A visibility queries.

Old SetRazed cave (0x10B6B0, 30B) is zeroed; v2 lives at 0x10B700.
"""
import shutil, struct, sys

DLL = "AoWEPACK.dll"
BAK = "AoWEPACK.dll.bak_pool_raze_v2"
F2V = 0x55700C00

VMT              = 0xD3CC8
OLD_SETRAZED     = 0x10B6B0          # 30 bytes, zero out
CAVE_SETRAZED_V2 = 0x10B700          # 58 bytes
CAVE_PVP_GUARD   = 0x10B740          # 20 bytes
PVP_ENTRY        = 0xD4630           # PoolVisionPlayer, VA 0x557D5230

data = bytearray(open(DLL, "rb").read())
va = lambda o: o + F2V

# --- validate current state ---
assert data[OLD_SETRAZED:OLD_SETRAZED + 30] == bytes.fromhex(
    "538BD884D274118BC3E8C28AFCFFC64330FF804B39015BC3806339FE5BC3"), \
    "old SetRazed cave mismatch"
assert struct.unpack_from("<I", data, VMT + 0x14C)[0] == va(OLD_SETRAZED), \
    "VMT+0x14C does not point at old cave"
assert data[PVP_ENTRY:PVP_ENTRY + 6] == bytes.fromhex("535651881424"), \
    "PoolVisionPlayer entry bytes mismatch"
assert not any(data[CAVE_SETRAZED_V2:CAVE_PVP_GUARD + 0x20]), "cave space not free"

# cross-check VMT slots used
for off, want in [(0x1F0, "SetPlayer"), (0x204, "UpdateUnfog"), (0x12C, "GetTerrainTypeImage")]:
    v = struct.unpack_from("<I", data, VMT + off)[0]
    assert 0x55700C00 < v < 0x55900000, f"slot {off:#x} implausible"

print("validated - applying")
shutil.copyfile(DLL, BAK)
print(f"  backup -> {BAK}")

# --- SetRazed v2 cave ---
#  0: push ebx
#  1: mov ebx,eax
#  3: test dl,dl
#  5: jz  +0x1C (clear @35)
#  7: mov dl,0FFh
#  9: mov eax,ebx ; mov ecx,[eax]
# 13: call [ecx+1F0h]        SetPlayer(-1): delist, self unfog, pools refresh
# 19: or  byte [ebx+39h],01  razed bit
# 23: mov eax,ebx ; mov ecx,[eax]
# 27: call [ecx+204h]        UpdateUnfog: now guarded -> refog self
# 33: jmp +4 (recompute @39)
# 35: and byte [ebx+39h],0FEh  (clear branch)
# 39: movsx edx,byte [ebx+18h]
# 43: mov eax,ebx ; mov ecx,[eax]
# 47: call [ecx+12Ch]        GetTerrainTypeImage(terraintype)
# 53: mov [ebx+14h],eax
# 56: pop ebx ; ret
setrazed = bytes.fromhex(
    "53" "8BD8" "84D2" "741C"
    "B2FF" "8BC3" "8B08" "FF91F0010000"
    "804B3901"
    "8BC3" "8B08" "FF9104020000"
    "EB04"
    "806339FE"
    "0FBE5318" "8BC3" "8B08" "FF912C010000"
    "894314" "5B" "C3")
assert len(setrazed) == 58
data[CAVE_SETRAZED_V2:CAVE_SETRAZED_V2 + 58] = setrazed

# --- PoolVisionPlayer razed-guard trampoline ---
#  0: test byte [eax+39h],01
#  4: jnz +0x0B (razed @17)
#  6: push ebx; push esi; push ecx; mov [esp],dl   (stolen entry bytes)
# 12: jmp PVP_ENTRY+6
# 17: xor eax,eax ; ret
back = va(PVP_ENTRY) + 6
guard = bytes.fromhex("F6403901" "750B" "535651881424") \
    + b"\xE9" + struct.pack("<i", back - (va(CAVE_PVP_GUARD) + 12 + 5)) \
    + bytes.fromhex("33C0C3")
assert len(guard) == 20
data[CAVE_PVP_GUARD:CAVE_PVP_GUARD + 20] = guard

# entry hook: jmp cave + nop
data[PVP_ENTRY:PVP_ENTRY + 6] = b"\xE9" + struct.pack(
    "<i", va(CAVE_PVP_GUARD) - (va(PVP_ENTRY) + 5)) + b"\x90"

# repoint VMT SetRazed, zero old cave
struct.pack_into("<I", data, VMT + 0x14C, va(CAVE_SETRAZED_V2))
data[OLD_SETRAZED:OLD_SETRAZED + 30] = bytes(30)

open(DLL, "wb").write(data)
print("done:")
print(f"  SetRazed v2 cave @ 0x{CAVE_SETRAZED_V2:X} (VA 0x{va(CAVE_SETRAZED_V2):08X}), VMT+0x14C repointed")
print(f"  PoolVisionPlayer guard @ 0x{CAVE_PVP_GUARD:X}, entry hook @ 0x{PVP_ENTRY:X}")
print(f"  old cave 0x{OLD_SETRAZED:X} zeroed")
