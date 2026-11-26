#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hero_levelup_event_fixed_location_patch.py

Hero Level-Up Event: Fixed Location (Age of Wonders 1, 1999, Delphi; AoWx mod).
Right-clicking a hero level-up entry in the event log now centers on the ORIGINAL
level-up hex (stored when the event is created) instead of following the hero's
current position (which let players track enemy heroes).

Target : AoWEPACK.dll  (ImageBase 0x55700000 ; VA = file_offset + 0x55700C00)
Backup : AoWEPACK.dll.bak_heroevt
Method : 1 hook (AddEvent) + 1 VMT-slot repoint + 2 PIC-safe caves.
Applied: 2026-07-23, CONFIRMED working in-game. Save/MP-safe (uses the already-
         serialized event field [+0x20]).

cave_evtcap @0x5580F600 hooks TEventLogbook.AddEvent @0x557FDB9D: on a
THeroUpgradeEventLog (VMT 0x55711B88, compared PIC-style so it survives rebase),
it latches the hero's current location into event[+0x20..0x22] and sets the valid
flag [+0x23], then replays the stolen call and returns.
cave_vloc @0x5580F6C0 is the new VMT+0x74 (ViewLocation) target: if the flag is
set it centers on the stored location; otherwise it jumps to the original
follow-hero ViewLocation @0x557857E0.

Usage:
    py hero_levelup_event_fixed_location_patch.py [path-to-AoWEPACK.dll]
    py hero_levelup_event_fixed_location_patch.py --verify
Idempotent.
"""
import sys, shutil, os

VA_BASE = 0x55700C00

CAVE_EVTCAP = (
    "50e8000000005981e906f680558d81881b715539060f85500000008b8140a08f558b80fc00"
    "00008b5618e819f3f6ff85c00f843400000083ec048d542402528d4c24058d542404e848f7"
    "f6ff8a04243cff74158846208a4424018846218a442402884622c646230183c40458e8975f"
    "f6ffe92ce5feff"
)
CAVE_VLOC = (
    "807823000f8505000000e91161f7ff538bd80fb64322508a4b218a53208bc3e810dffeff5bc3"
)

# (file_offset, old_bytes, new_bytes, note)
PATCHES = [
    # Hook: TEventLogbook.AddEvent @0x557FDB9D  call 0x55775608 -> jmp cave_evtcap 0x5580F600
    (0x0FCF9D, bytes.fromhex("e8667af7ff"), bytes.fromhex("e95e1a0100"),
     "AddEvent: steal call -> jmp cave_evtcap"),
    # VMT ViewLocation slot @0x55711BFC (THeroUpgradeEventLog VMT+0x74): 0x557857E0 -> cave_vloc 0x5580F6C0
    (0x010FFC, bytes.fromhex("e05778"), bytes.fromhex("c0f680"),
     "VMT+0x74 ViewLocation -> cave_vloc"),
    # cave_evtcap @0x5580F600 (was zero-filled free space), 118 bytes
    (0x10EA00, bytes(118), bytes.fromhex(CAVE_EVTCAP),
     "cave_evtcap (capture original location)"),
    # cave_vloc @0x5580F6C0 (was zero-filled free space), 38 bytes
    (0x10EAC0, bytes(38), bytes.fromhex(CAVE_VLOC),
     "cave_vloc (center on stored location)"),
]
# sanity: cave lengths
assert len(bytes.fromhex(CAVE_EVTCAP)) == 118
assert len(bytes.fromhex(CAVE_VLOC)) == 38


def apply(buf: bytearray) -> int:
    written = 0
    for off, old, new, _note in PATCHES:
        assert len(old) == len(new), f"length mismatch at 0x{off:X} ({len(old)} vs {len(new)})"
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
    bak = path + ".bak_heroevt"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"[+] backup -> {bak}")
    with open(path, "wb") as f:
        f.write(buf)
    print(f"[+] {path}: applied {n} edits (hook + VMT repoint + 2 caves).")


def verify():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    bak  = os.path.join(root, "AoWEPACK.dll.bak_heroevt")
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
