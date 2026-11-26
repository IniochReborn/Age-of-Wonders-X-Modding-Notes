# Reflecting Pool: set rebuild time to 2 turns (like watch towers)
# TReflectingPoolResource.Create @ file 0xD47E3 writes 4 byte fields.
# The +44h=01 write is redundant (TStructureResource.Create already sets it),
# so repurpose that slot to write rebuild-days [res+5Bh]=02 inline.
import shutil, sys

DLL = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"
BAK = DLL + ".bak_pool_rebuild_days"

OFF = 0xD47E3
OLD = bytes.fromhex("C6464401" "C6464500" "C6466400" "C6465801")
NEW = bytes.fromhex("C6464500" "C6466400" "C6465801" "C6465B02")

with open(DLL, "rb") as f:
    data = bytearray(f.read())

cur = bytes(data[OFF:OFF+len(OLD)])
if cur == NEW:
    print("Already patched.")
    sys.exit(0)
if cur != OLD:
    print(f"UNEXPECTED BYTES at {OFF:#x}: {cur.hex(' ')}")
    sys.exit(1)

shutil.copyfile(DLL, BAK)
data[OFF:OFF+len(NEW)] = NEW
with open(DLL, "wb") as f:
    f.write(data)
print(f"Patched {OFF:#x}: rebuild days = 2. Backup: {BAK}")
