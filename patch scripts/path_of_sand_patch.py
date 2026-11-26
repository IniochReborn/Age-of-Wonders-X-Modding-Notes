#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Path of Sand  -  new terraform ability (id 0x9F), Desert instead of Grass

A faithful clone of vanilla Path of Life (radius 1, surface-only, suppressed on
transports) that converts terrain to Desert (2) instead of Grass (1). Registered as
a new TEnhancementAbility id 0x9F in free cave space; PIC (rebase-safe).

Target: AoWEPACK.dll  (Age of Wonders 1 engine package; ImageBase 0x55700000)
VA math: VA = file_offset + 0x55700C00   (file_offset = VA - 0x55700C00)

Usage:
    py path_of_sand_patch.py [path-to-AoWEPACK.dll]
If no path is given it patches ./AoWEPACK.dll in the current directory.
A timestamped .bak_preXXXX backup is written before any bytes are changed.
Pass  --force  to skip the original-byte assertions (patch anyway).

Each record below is (file_offset, expected_original_hex, new_hex). The script
verifies the expected_original bytes are present (so it refuses to double-apply
or patch the wrong build), then writes the new bytes. All offsets are FILE
offsets into AoWEPACK.dll.

This is the STANDALONE Path of Sand (registration cave returns straight to the game).
In the shipping mod the same registration cave tail-jump is re-pointed to chain the
Weakness-abilities registration; apply path_of_sand_patch.py FIRST, then the weakness
patch, to reproduce the live binary exactly.
"""
import sys, os, shutil, datetime

IMG = 0x55700C00

# (file_offset, expected_original_hex, new_hex)
PATCHES = [
    (0x07F8B7, "ba6d0000", "e944ef08"),
    (0x0BBDE9, "e84a38f9ff", "e9922a0500"),
    (0x10E7A0, "00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000", "ffffffff0c00000050617468206f662053616e64000000000000000000000000558bec0fbe016683f806740e6685c07409807a12007503c601025dc204"),
    (0x10E800, "00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000", "e8000000005f81ef05f48055ba9f0000008bc38b08ff914801000084c074358b45fc0fbe4011508b45fc0fbe4012506a01538d87c0f38055506a006a008b45fc0fbe481033d28b8740a08f558b30ff96d4000000ba6d000000e95e10f7ff"),
    (0x10E880, "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000", "e8b30df4ffe800000000582d8af480558d90a8f38055668b88c0cf7b55b89f000000e8756bf5ff8bd08bc3e8880df4ffe939d5faff"),
]

TAG = "pathsand"

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv[1:]
    path = args[0] if args else "AoWEPACK.dll"
    if not os.path.isfile(path):
        print("ERROR: file not found:", path); return 1
    with open(path, "rb") as f:
        buf = bytearray(f.read())

    # verify originals
    problems = []
    for off, oldh, newh in PATCHES:
        old = bytes.fromhex(oldh)
        cur = bytes(buf[off:off+len(old)])
        if cur == bytes.fromhex(newh):
            print("  already patched at 0x%06X (VA 0x%08X)" % (off, off+IMG))
        elif cur != old:
            problems.append((off, cur.hex(), oldh))
    if problems and not force:
        print("ERROR: original bytes did not match at:")
        for off, cur, exp in problems:
            print("   0x%06X (VA 0x%08X): found %s expected %s" % (off, off+IMG, cur, exp))
        print("Refusing to patch. Wrong build, or a prerequisite patch is missing.")
        print("(Use --force to override.)")
        return 2

    # backup
    bak = path + ".bak_pre" + TAG
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print("backup ->", bak)

    # write
    n = 0
    for off, oldh, newh in PATCHES:
        new = bytes.fromhex(newh)
        if bytes(buf[off:off+len(new)]) != new:
            buf[off:off+len(new)] = new
            n += 1
    with open(path, "wb") as f:
        f.write(buf)
    print("applied %d/%d ranges. Done: %s" % (n, len(PATCHES), path))
    return 0

if __name__ == "__main__":
    sys.exit(main())
