#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp_default_race_cpu_emperor_patch.py

MP Default Race: CPU Emperor (Age of Wonders 1, 1999, Delphi; AoWx mod).
In the LAN multiplayer lobby, unassigned races default to CPU Emperor (type 7)
instead of Free (type 5). A player's Preferred Race still claims/overrides it;
host-Forced / map-assigned races still win. Claim logic keys off owner-id
(rec[0xC]==0) and the flags word, never the owner-type enum, so only the default
value changes.

Target : AoWEPACK.dll  unit "AoWSetup"  (CODE VA = file_offset + 0x55700C00)
Backup : AoWEPACK.dll.bak_mprace
Method : 3 MP-only byte edits (no caves). Ghidra-verified data model.
Applied: 2026-07-23, CONFIRMED working in-game.

Owner-type enum: 0=Human 1=CPU-Warrior 2=Knight 3=Lord 4=Independent
                 5=Free 6=CPU-King 7=CPU-Emperor
pid globals @0x558E8E58 stride 8: pidFree={5}@..E58, pidCPU5/Emperor={7}@..E88

Usage:
    py mp_default_race_cpu_emperor_patch.py [path-to-AoWEPACK.dll]
    py mp_default_race_cpu_emperor_patch.py --verify
Idempotent.
"""
import sys, shutil, os

VA_BASE = 0x55700C00

# (file_offset, old_bytes, new_bytes, note)
PATCHES = [
    # 1) race-record builder @0x557E2398: MP default owner   Free(5) -> Emperor(7)
    (0x0E1798, bytes.fromhex("c6400805"), bytes.fromhex("c6400807"),
     "mov byte[eax+8],5 -> 7   (MP default owner)"),
    # 2) race-record builder @0x557E239F: MP default fallback Free(5) -> Emperor(7)
    (0x0E179F, bytes.fromhex("c6401005"), bytes.fromhex("c6401007"),
     "mov byte[eax+0x10],5 -> 7 (MP default fallback)"),
    # 3) ResetPlayerSettings remote @0x557E1406: read pidCPU5(7)@0x558E8E88 not pidFree(5)@0x558E8E58
    #    only the operand low byte (file 0x0E0808) changes: 0x58 -> 0x88; base-reloc @0x557E1408 intact
    (0x0E0806, bytes.fromhex("8b15588e8e55"), bytes.fromhex("8b15888e8e55"),
     "mov edx,[0x558E8E58] -> [0x558E8E88] (released race reverts to Emperor)"),
]


def apply(buf: bytearray) -> int:
    written = 0
    for off, old, new, _note in PATCHES:
        assert len(old) == len(new), f"length mismatch at 0x{off:X}"
        cur = bytes(buf[off:off + len(old)])
        if cur == new:
            continue
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
    bak = path + ".bak_mprace"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"[+] backup -> {bak}")
    with open(path, "wb") as f:
        f.write(buf)
    print(f"[+] {path}: applied {n} edits. MP default race = CPU Emperor.")


def verify():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    bak  = os.path.join(root, "AoWEPACK.dll.bak_mprace")
    live = os.path.join(root, "AoWEPACK.dll")
    with open(bak, "rb") as f:  b = bytearray(f.read())
    with open(live, "rb") as f: L = f.read()
    apply(b)
    ok = all(bytes(b[off:off+len(new)]) == L[off:off+len(new)] == new
             for off, _old, new, _n in PATCHES)
    print("VERIFY:", "PASS - patched .bak reproduces live bytes at all offsets" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        sys.exit(0 if verify() else 1)
    patch_file(sys.argv[1] if len(sys.argv) > 1 else "AoWEPACK.dll")
