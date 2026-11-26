#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sphere Combining  -  allow opposing element spheres (Fire/Water, Earth/Air)

Wizard sphere selection: Life/Death stay mutually exclusive, but Fire/Water and
Earth/Air can now be combined, each opposing-element pair capped at 4 combined picks.
This rewrites TLeader.CanAddSphere (VA 0x5578B1F8) in place (no cave).

Target: AoWEPACK.dll  (Age of Wonders 1 engine package; ImageBase 0x55700000)
VA math: VA = file_offset + 0x55700C00   (file_offset = VA - 0x55700C00)

Usage:
    py sphere_combining_patch.py [path-to-AoWEPACK.dll]
If no path is given it patches ./AoWEPACK.dll in the current directory.
A timestamped .bak_preXXXX backup is written before any bytes are changed.
Pass  --force  to skip the original-byte assertions (patch anyway).

Each record below is (file_offset, expected_original_hex, new_hex). The script
verifies the expected_original bytes are present (so it refuses to double-apply
or patch the wrong build), then writes the new bytes. All offsets are FILE
offsets into AoWEPACK.dll.

"""
import sys, os, shutil, datetime

IMG = 0x55700C00

# (file_offset, expected_original_hex, new_hex)
PATCHES = [
    (0x08A657, "057511b206", "017511b202"),
    (0x08A66D, "067511b2058bc6e803ffffff84c0740433c0eb5f80fb017511b2028bc6e8edfeffff84c0740433c0eb4980fb027511b2018bc6e8d7feffff84c0740433c0eb3380fb037511b2048bc6e8c1feffff84c0740433c0eb1d80fb047511b2038bc6e8abfeffff84c0740433c0eb07", "027511b2018bc6e803ffffff84c0745c33c0eb5f80fb03740580fb04751cb2038bc6e8e8feffff50b2048bc6e8defeffff5900c83c047234eb3780fb05740580fb067528b2058bc6e8c2feffff50b2068bc6e8b8feffff5900c83c04720eeb11909090909090909090909090"),
]

TAG = "spheres"

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
