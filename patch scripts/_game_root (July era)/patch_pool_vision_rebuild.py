# Reflecting Pool: rebuilding (still-razed) pool must not grant pool-network vision.
# PoolVisionPlayer decides "player owns >=1 pool" via [player+68h].Count != 0.
# ExecuteRebuild -> SetPlayer(builder) enlists the razed pool, so the count check
# passes as soon as rebuild starts. Replace both count fetches with a helper that
# counts only pools whose razed bit ([pool+39h] & 1) is clear.
#
# Helper cave @ file 0x10B754 (VA 0x5580C354), 41 bytes:
#   in EAX = TPlayerStructureList; out EAX = 1 if >=1 non-razed pool else 0
# Call sites (each "mov edx,[eax]; call [edx+54h]" -> "call cave"):
#   0xD464F (VA 0x557D524F): asking player's own list
#   0xD468B (VA 0x557D528B): ally-loop over other players' lists
import shutil, sys

DLL = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"
BAK = DLL + ".bak_pool_vision_rebuild"

CAVE_OFF = 0x10B754
CAVE = bytes.fromhex(
    "56"            # push esi
    "57"            # push edi
    "8BF0"          # mov  esi,eax          ; list
    "8B16"          # mov  edx,[esi]
    "FF5254"        # call [edx+54h]        ; eax = Count
    "8BF8"          # mov  edi,eax
    "8B7608"        # mov  esi,[esi+08h]    ; inlined GetStructure base
    "8B7604"        # mov  esi,[esi+04h]    ; items array
    # loop:
    "4F"            # dec  edi
    "7810"          # js   none
    "8B04BE"        # mov  eax,[esi+edi*4]  ; pool
    "F6403901"      # test byte [eax+39h],1 ; razed bit
    "75F4"          # jnz  loop
    "B801000000"    # mov  eax,1            ; found non-razed pool
    "EB02"          # jmp  out
    # none:
    "33C0"          # xor  eax,eax
    # out:
    "5F"            # pop  edi
    "5E"            # pop  esi
    "C3"            # ret
)

OLD_SITE = bytes.fromhex("8B10FF5254")          # mov edx,[eax]; call [edx+54h]
SITES = [
    (0xD464F, bytes.fromhex("E800710300")),      # call 0x5580C354
    (0xD468B, bytes.fromhex("E8C4700300")),      # call 0x5580C354
]

with open(DLL, "rb") as f:
    data = bytearray(f.read())

if bytes(data[SITES[0][0]:SITES[0][0]+5]) == SITES[0][1]:
    print("Already patched.")
    sys.exit(0)

if bytes(data[CAVE_OFF:CAVE_OFF+len(CAVE)]) != b"\x00" * len(CAVE):
    print("CAVE NOT EMPTY"); sys.exit(1)
for off, _ in SITES:
    if bytes(data[off:off+5]) != OLD_SITE:
        print(f"UNEXPECTED BYTES at {off:#x}: {data[off:off+5].hex(' ')}"); sys.exit(1)

shutil.copyfile(DLL, BAK)
data[CAVE_OFF:CAVE_OFF+len(CAVE)] = CAVE
for off, new in SITES:
    data[off:off+5] = new
with open(DLL, "wb") as f:
    f.write(data)
print(f"Patched. Cave {CAVE_OFF:#x} ({len(CAVE)}B), sites 0xD464F/0xD468B. Backup: {BAK}")
