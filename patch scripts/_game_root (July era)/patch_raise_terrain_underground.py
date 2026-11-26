# Raise Terrain (spell 0x13) overhaul:
# 1) Block list: vanilla ValidTargetMapF/ValidTargetSelectionMapF reject terrain
#    types {0,6,10,13} (Water, Ice, Water2, Ice2) via a sub/jz chain. Replace with
#    bitmask test also blocking Rock(8): mask 0x2541 = bits {0,6,8,10,13}.
#    Lava(9), Earth(7), Dirt(12) etc. remain castable -> underground + lava OK.
# 2) Spawn selection: TRaiseTerrainTE.RaiseTerrain scans resources for
#    ClassID==0x2016B && UsedTerrain==1 and spawns the first hit (vanilla small
#    mountain). New cave selects by cast level ([TE+22h]): underground wants the
#    resource whose painted terrain (TTerrainList.GetTerrain(list,0)) == 7
#    (Earth), surface wants != 7 (the vanilla mountain resource).
#    Requires a second Raised-Mountain-class resource painted Earth (made in
#    AoWDevEd); until it exists, underground casts spawn nothing.
import shutil, sys

DLL = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"
BAK = DLL + ".bak_raise_terrain_ug"
VA = 0x55700C00

USED_TERRAIN = 0x55701CA4   # jmp_HSEPack TTerrainList.UsedTerrain thunk
GET_TERRAIN  = 0x55701C8C   # jmp_HSEPack TTerrainList.GetTerrain thunk

def rel(target, next_va):
    return (target - next_va) & 0xFFFFFFFF

# --- 1) validity filters (19 bytes each) ---
OLD1 = bytes.fromhex("8A431484C074242C0674202C04741C2C037418")  # [ebx+14h] chain
OLD2 = bytes.fromhex("8A461484C074242C0674202C04741C2C037418")  # [esi+14h] chain
NEW1 = bytes.fromhex("0FB64314" "B941250000" "0FA3C1" "721D" "9090909090")
NEW2 = bytes.fromhex("0FB64614" "B941250000" "0FA3C1" "721D" "9090909090")
F1_OFF, F2_OFF = 0xA29CB, 0xA2A23

# --- 2) spawn-selection cave ---
CAVE_OFF = 0x10B7C0
CAVE_VA  = VA + CAVE_OFF
cave = bytearray()
cave += bytes.fromhex("8B4328")                                   # mov eax,[ebx+28h]
cave += b"\xE8" + rel(USED_TERRAIN, CAVE_VA + len(cave) + 5).to_bytes(4, "little")
cave += bytes.fromhex("48" "7525")                                # dec eax; jnz .no
cave += bytes.fromhex("33D2" "8B4328")                            # xor edx,edx; mov eax,[ebx+28h]
cave += b"\xE8" + rel(GET_TERRAIN, CAVE_VA + len(cave) + 5).to_bytes(4, "little")
cave += bytes.fromhex("8B4C2404")                                 # mov ecx,[esp+04h]  ; TE self
cave += bytes.fromhex("80792200")                                 # cmp byte [ecx+22h],0 ; level
cave += bytes.fromhex("740A")                                     # jz .surface
cave += bytes.fromhex("3C07" "750D" "B001" "C3")                  # UG: ==7 ? al=1:ret : .no
cave += bytes.fromhex("909090")
cave += bytes.fromhex("3C07" "7403" "B001" "C3")                  # .surface: ==7 -> .no
cave += bytes.fromhex("33C0" "C3")                                # .no: xor eax,eax; ret
assert len(cave) == 0x33, hex(len(cave))

# --- TE scan redirect (11 bytes at 0xA2758) ---
SCAN_OFF = 0xA2758
OLD_SCAN = bytes.fromhex("8B4328" "E844E9F5FF" "48" "7404")
NEW_SCAN = (b"\xE8" + rel(CAVE_VA, VA + SCAN_OFF + 5).to_bytes(4, "little")
            + bytes.fromhex("84C0" "7506" "9090"))
assert len(NEW_SCAN) == 11

with open(DLL, "rb") as f:
    data = bytearray(f.read())

if bytes(data[F1_OFF:F1_OFF+19]) == NEW1:
    print("Already patched."); sys.exit(0)

for off, old, what in [(F1_OFF, OLD1, "filter1"), (F2_OFF, OLD2, "filter2"),
                       (SCAN_OFF, OLD_SCAN, "scan")]:
    if bytes(data[off:off+len(old)]) != old:
        print(f"UNEXPECTED {what} at {off:#x}: {data[off:off+len(old)].hex(' ')}"); sys.exit(1)
if bytes(data[CAVE_OFF:CAVE_OFF+len(cave)]) != b"\x00" * len(cave):
    print("Cave not empty"); sys.exit(1)

shutil.copyfile(DLL, BAK)
data[F1_OFF:F1_OFF+19] = NEW1
data[F2_OFF:F2_OFF+19] = NEW2
data[SCAN_OFF:SCAN_OFF+11] = NEW_SCAN
data[CAVE_OFF:CAVE_OFF+len(cave)] = cave
with open(DLL, "wb") as f:
    f.write(data)
print(f"Patched: filters {F1_OFF:#x}/{F2_OFF:#x}, scan {SCAN_OFF:#x}, "
      f"cave {CAVE_OFF:#x} ({len(cave)}B). Backup: {BAK}")
