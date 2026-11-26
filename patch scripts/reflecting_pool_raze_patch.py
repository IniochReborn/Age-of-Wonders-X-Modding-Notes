#!/usr/bin/env python3
"""
reflecting_pool_raze_patch.py  --  Age of Wonders 1  (AoWEPACK.dll)
====================================================================
Applies the complete "Reflecting Pool Raze" feature to AoWEPACK.dll:
raze + rebuild + rebuild animation + full pool-vision handling.

The bytes below were extracted by diffing the pre-feature backup
(AoWEPACK.dll.bak_reflecting_pool_raze) against the live, fully-patched
AoWEPACK.dll, then keeping ONLY the ranges that belong to the pool
feature (later, unrelated mod features that share the cave zone were
excluded). See "Reflecting Pool Raze.md" for the full RE writeup.

ImageBase 0x55700000, CODE VA = file_offset + 0x55700C00.

Usage:
    py reflecting_pool_raze_patch.py [path	o\AoWEPACK.dll]

Each patch is (file_offset, OLD_bytes, NEW_bytes):
 - if the file already holds NEW  -> that patch is skipped (idempotent)
 - if the file holds OLD          -> it is rewritten to NEW
 - anything else                  -> the script aborts (wrong/again-modified file)
A .bak_prepoolraze backup is written before the first change.
"""
import sys, os, shutil

PATCHES = [
    (0x5DAA0, bytes.fromhex('53568bf28bd8'), bytes.fromhex('e9ebdc0a0090')),  # GetTerrainTypeImage entry hook -> rebuild-gfx cave
    (0xD3CE0, bytes.fromhex('404d7d'), bytes.fromhex('d8c280')),  # TReflectingPool VMT +0x18 ReadWrite hook
    (0xD3E14, bytes.fromhex('e8ed7555e4ed75'), bytes.fromhex('00c38055a0c280')),  # TReflectingPool VMT +0x14C SetRazed & +0x150 GetRazed hooks
    (0xD4630, bytes.fromhex('535651881424'), bytes.fromhex('e90b71030090')),  # PoolVisionPlayer entry hook -> razed-guard cave
    (0xD464F, bytes.fromhex('8b10ff5254'), bytes.fromhex('e800710300')),  # PoolVisionPlayer own-list count -> rebuild-count helper
    (0xD468B, bytes.fromhex('8b10ff5254'), bytes.fromhex('e8c4700300')),  # PoolVisionPlayer ally-list count -> rebuild-count helper
    (0xD47E5, bytes.fromhex('4401c6464500c6466400c6465800'), bytes.fromhex('4500c6466400c6465801c6465b01')),  # TReflectingPoolResource.Create inline rewrite (razeable=1, rebuild=1 turn)
    (0x10B6A0, bytes.fromhex('0000000000000000'), bytes.fromhex('f64039010f95c0c3')),  # cave: GetRazed (test byte[eax+39h],1)
    (0x10B6D8, bytes.fromhex('0000000000000000000000000000000000000000000000000000000000'), bytes.fromhex('53568bf28bd8e8614cf5ff8d5339b9700000008bc68b30ff56305e5bc3')),  # cave: ReadWrite (stream byte +39h, field id 0x70)
    (0x10B700, bytes.fromhex('000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'), bytes.fromhex('538bd884d27476b2ff8bc38b08ff91f0010000804b39018bc38b08ff9104020000eb04806339fe0fbe53188bc38b08ff912c0100008943145bc3000000000000f6403901750b535651881424e9e58efcff33c0c356578bf08b16ff52548bf88b76088b76044f78108b04bef640390175f4b801000000eb0233c05f5ec3806339fe8bc3e8fc8cfcffe99affffff000000807824ff741cb81900000083fa037506b81a000000c383fa057506b81b000000c3c353568bf28bd8e9e922f5ff')),  # cave: SetRazed v2 + PoolVisionPlayer guard + rebuild-count helper + unraze-ext + rebuild-gfx
]

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "AoWEPACK.dll"
    if not os.path.isfile(path):
        sys.exit(f"file not found: {path}")
    data = bytearray(open(path, "rb").read())

    # pre-flight: every range must be either OLD or already NEW
    todo = []
    for off, old, new in PATCHES:
        cur = bytes(data[off:off+len(new)])
        if cur == new:
            continue
        if cur == old:
            todo.append((off, old, new))
        else:
            sys.exit(f"ABORT @0x{off:X}: unexpected bytes {cur.hex()} "
                     f"(expected OLD {old.hex()} or NEW {new.hex()})")

    if not todo:
        print("Already fully patched -- nothing to do.")
        return

    bak = path + ".bak_prepoolraze"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"backup -> {bak}")

    for off, old, new in todo:
        data[off:off+len(new)] = new
        print(f"  patched 0x{off:X}  ({len(new)} bytes)")

    open(path, "wb").write(data)
    print(f"done: {len(todo)} range(s) written to {path}")

if __name__ == "__main__":
    main()
