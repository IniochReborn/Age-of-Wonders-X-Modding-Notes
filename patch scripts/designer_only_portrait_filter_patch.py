#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# Designer-Only Portrait Filter  --  AoWEPACK.dll apply-script
# =============================================================================
# Restores vanilla behaviour where hero/leader portraits flagged "Designer
# Only" / "Reserved" in the editor do NOT appear in in-game leader
# customization. AoW+ (our base) had disabled the filter by forcing
# AoWReg.TAoWRegistry.GetDeveloper() to return TRUE, which made
# TFaceResourceList.NextFace / PrevFace stop skipping reserved faces.
#
# This surgical fix leaves GetDeveloper = true (so the AoW+ dev keyboard
# still works) and instead NOPs the `jne <accept>` after `test al,al` in
# both NextFace and PrevFace, so the reserved-flag check ALWAYS runs.
#
# File patched : AoWEPACK.dll   (ImageBase 0x55700000, CODE roff 0x400 rva 0x1000)
# Baseline     : AoWEPACK.dll.bak_predevfix   (AoW+ original, filter disabled)
# Two byte edits only:
#   PrevFace jne  file 0x4CA4D  VA 0x5574D64D   75 0F -> 90 90
#   NextFace jne  file 0x4CA90  VA 0x5574D690   75 0F -> 90 90
#
# Verified: diff bak_predevfix -> bak_regiso (the next-feature snapshot) shows
# EXACTLY these two 2-byte ranges; both are still 90 90 in the current live
# AoWEPACK.dll (no later patch touched them).
#
# Usage:  py designer_only_portrait_filter_patch.py [path-to-AoWEPACK.dll]
#         (defaults to ./AoWEPACK.dll ; writes in place, makes a .bak_portrait)
# =============================================================================
import sys, os, shutil

# (file_offset, expected_old_bytes, new_bytes, description)
PATCHES = [
    (0x4CA4D, bytes.fromhex("750f"), bytes.fromhex("9090"), "PrevFace jne->nop (VA 0x5574D64D)"),
    (0x4CA90, bytes.fromhex("750f"), bytes.fromhex("9090"), "NextFace jne->nop (VA 0x5574D690)"),
]

def apply(buf: bytearray):
    for off, old, new, desc in PATCHES:
        cur = bytes(buf[off:off+len(old)])
        if cur == new:
            print(f"  [skip] 0x{off:X} already patched ({desc})")
            continue
        assert cur == old, (f"OLD-BYTE MISMATCH at 0x{off:X}: expected {old.hex()} "
                            f"got {cur.hex()} ({desc}). Wrong/already-modified file.")
        buf[off:off+len(new)] = new
        print(f"  [ok]   0x{off:X} {old.hex()} -> {new.hex()} ({desc})")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "AoWEPACK.dll"
    if not os.path.isfile(target):
        sys.exit(f"target not found: {target}")
    buf = bytearray(open(target, "rb").read())
    bak = target + ".bak_portrait"
    if not os.path.exists(bak):
        shutil.copyfile(target, bak); print(f"backup -> {bak}")
    apply(buf)
    open(target, "wb").write(buf)
    print(f"written: {target}")

if __name__ == "__main__":
    main()
