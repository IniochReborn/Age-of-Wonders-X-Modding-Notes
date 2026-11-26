# Raise Terrain v2 (run with the game/DevEd CLOSED):
# - blocked-terrain mask 0x2541 -> 0x25C1: adds Earth(7) so an already-raised
#   Earth hex can't be raised again (raised mountain is guarded via its painted
#   terrain 0).
# - NOP the [field+15h] != 0 overlay checks in both validity functions. Lava and
#   underground floor tiles carry overlay 0, which is what blocked them. Restore
#   is already safe for overlay-0 hexes: they have no decor object to rebuild,
#   and TRaisedMountain.RestoreTerrain skips PlaceTerrain for saved <= 0.
import shutil, sys

DLL = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"
BAK = DLL + ".bak_raise_terrain_v2"

with open(DLL, "rb") as f:
    data = bytearray(f.read())

if data[0xA29D0] == 0xC1 and data[0xA29DE] == 0x90:
    print("Already patched."); sys.exit(0)

assert bytes(data[0xA29CB:0xA29CB+19]) == bytes.fromhex("0FB64314B9412500000FA3C1721D9090909090")
assert bytes(data[0xA2A23:0xA2A23+19]) == bytes.fromhex("0FB64614B9412500000FA3C1721D9090909090")
assert bytes(data[0xA29DE:0xA29DE+7]) == bytes.fromhex("8A431584C07411")
assert bytes(data[0xA2A36:0xA2A36+7]) == bytes.fromhex("8A461584C07411")

shutil.copyfile(DLL, BAK)
data[0xA29D0] = 0xC1
data[0xA2A28] = 0xC1
data[0xA29DE:0xA29DE+7] = b"\x90" * 7
data[0xA2A36:0xA2A36+7] = b"\x90" * 7
with open(DLL, "wb") as f:
    f.write(data)
print(f"Patched. Backup: {BAK}")
