#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registry_isolation_patch.py

Registry Isolation for the AoWx mod (Age of Wonders 1, 1999, Delphi).
Redirects the mod's entire per-user settings tree from the shared vanilla key
    HKCU\\Software\\Triumph Studios\\Age of Wonders\\
to its own isolated key
    HKCU\\Software\\Triumph Studios\\Age of Wonders X\\
so it no longer collides with vanilla or other AoW mods.

Target : AoWEPACK.dll  (ImageBase 0x55700000 ; VA = file_offset + 0x55700C00)
Backup : AoWEPACK.dll.bak_regiso
Method : 12 pure in-place byte edits (no caves, no hooks). Each of the 6 copies
         of the Delphi path constant is lengthened in place: bump the length
         dword low byte by +2 and rewrite the trailing "\\"+pad as " X\\".
Applied: 2026-07-22, CONFIRMED clean.

POST-STEP (NOT a binary patch): one-time settings migration so an existing
install keeps its current settings (non-destructive; run once at a shell):
    reg copy "HKCU\\Software\\Triumph Studios\\Age of Wonders" \\
             "HKCU\\Software\\Triumph Studios\\Age of Wonders X" /s /f
For distribution this can be skipped (the game creates the new key with defaults
on first run) or shipped as a .reg.

Usage:
    py registry_isolation_patch.py [path-to-AoWEPACK.dll]
    py registry_isolation_patch.py --verify   # self-test against the .bak
Idempotent: re-running on an already-patched file is a no-op.
"""
import sys, shutil, os

VA_BASE = 0x55700C00  # VA = file_offset + VA_BASE

# (file_offset, old_bytes, new_bytes)  -- old bytes verified against .bak_regiso
PATCHES = [
    # 5 bare-path copies: "\Software\Triumph Studios\Age of Wonders\" (len 41->43)
    (0x002FE8, bytes.fromhex("29"),               bytes.fromhex("2b")),                # len 0x29->0x2B  VA 0x55703BE8
    (0x003014, bytes.fromhex("5c0000"),           bytes.fromhex("20585c")),            # "\"+pad -> " X\"  VA 0x55703C14
    (0x0030D8, bytes.fromhex("29"),               bytes.fromhex("2b")),                # VA 0x55703CD8
    (0x003104, bytes.fromhex("5c0000"),           bytes.fromhex("20585c")),            # VA 0x55703D04
    (0x0031D0, bytes.fromhex("29"),               bytes.fromhex("2b")),                # VA 0x55703DD0
    (0x0031FC, bytes.fromhex("5c0000"),           bytes.fromhex("20585c")),            # VA 0x55703DFC
    (0x0032C4, bytes.fromhex("29"),               bytes.fromhex("2b")),                # VA 0x55703EC4
    (0x0032F0, bytes.fromhex("5c0000"),           bytes.fromhex("20585c")),            # VA 0x55703EF0
    (0x0035B8, bytes.fromhex("29"),               bytes.fromhex("2b")),                # VA 0x557041B8
    (0x0035E4, bytes.fromhex("5c0000"),           bytes.fromhex("20585c")),            # VA 0x557041E4
    # 6th copy: "...Age of Wonders\General" (len 48->50)
    (0x003AB8, bytes.fromhex("30"),               bytes.fromhex("32")),                # len 0x30->0x32  VA 0x557046B8
    (0x003AE4, bytes.fromhex("5c47656e6572616c0000"), bytes.fromhex("20585c47656e6572616c")),  # "\General"+pad -> " X\General"  VA 0x557046E4
]

REG_COPY_CMD = ('reg copy "HKCU\\Software\\Triumph Studios\\Age of Wonders" '
                '"HKCU\\Software\\Triumph Studios\\Age of Wonders X" /s /f')


def apply(buf: bytearray) -> int:
    """Apply patches in place. Returns count actually written (0 if all already applied)."""
    written = 0
    for off, old, new in PATCHES:
        assert len(old) == len(new), f"length mismatch at 0x{off:X}"
        cur = bytes(buf[off:off + len(old)])
        if cur == new:
            continue  # already patched
        assert cur == old, (
            f"unexpected bytes at file 0x{off:06X} (VA 0x{off+VA_BASE:08X}): "
            f"got {cur.hex()}, expected old {old.hex()} or new {new.hex()}")
        buf[off:off + len(new)] = new
        written += 1
    return written


def patch_file(path: str):
    with open(path, "rb") as f:
        buf = bytearray(f.read())
    n = apply(buf)
    if n == 0:
        print(f"[=] {path}: already patched (no changes).")
        return
    bak = path + ".bak_regiso"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"[+] backup -> {bak}")
    with open(path, "wb") as f:
        f.write(buf)
    print(f"[+] {path}: applied {n} edits. Registry tree now 'Age of Wonders X'.")
    print(f"[i] POST-STEP (optional, one-time settings migration):\n    {REG_COPY_CMD}")


def verify():
    """Reproduce the live bytes: apply to a copy of the .bak and compare patched
    offsets to the live AoWEPACK.dll."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)  # game root (this script lives in "share to discord")
    bak  = os.path.join(root, "AoWEPACK.dll.bak_regiso")
    live = os.path.join(root, "AoWEPACK.dll")
    with open(bak, "rb") as f:  b = bytearray(f.read())
    with open(live, "rb") as f: L = f.read()
    apply(b)
    ok = all(bytes(b[off:off+len(new)]) == L[off:off+len(new)] == new
             for off, _old, new in PATCHES)
    print("VERIFY:", "PASS - patched .bak reproduces live bytes at all offsets" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        sys.exit(0 if verify() else 1)
    patch_file(sys.argv[1] if len(sys.argv) > 1 else "AoWEPACK.dll")
