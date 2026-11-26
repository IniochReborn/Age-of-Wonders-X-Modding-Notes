#!/usr/bin/env python3
r"""
Strategic map, multi-party move: a party that cannot reach the shared target THIS turn moves as far as it can
instead of being dropped (AoWEPACK.dll, 2026-09-21).

Vanilla: TSelectedArmy.CalculateMovePath 0x55792900 computes the party's path; in multi-select mode
([sel+0x18] == 1) it then compares the path's total cost [ms+0xC] with the party's movement points [ms+0x14]
(0x55792A66) and, when the path costs more, CLEARS the path and flashes "Not enough move points" (resstring
65018) -> that party gets no move order at all, while a single selected party keeps its path and walks a
partial route (multi-turn move).  The click-time setup (SetupMultiArmyMove 0x5574AC68 -> CalculateMovePositions
0x55763A5C, reach index [ms+0x24], settle callback 0x5574AAA4) already supports partial paths: it builds the
reachable prefix and creates the move TE ("Moving to: x,y,z"), so nothing else needs to change.

Patch: 0x55792A6C `jge 0x55792AA3` (7D 35) -> `jmp` (EB 35): skip the discard branch, keep the road-cost message
branch that follows.  In place, 1 byte; the two .reloc entries inside the skipped block (0x55792A7A, 0x55792A92)
are untouched.  The path still travels inside the token -> multiplayer-safe.
Backup AoWEPACK.dll.bak_stratpartial (in <game>\backup\).  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_stratpartial"
BASE = 0x55700000
SITE = 0x55792A6C
ORIG, NEW = bytes.fromhex("7d35"), bytes.fromhex("eb35")
CTX_BEFORE = bytes.fromhex("8b47143b470c")   # mov eax,[edi+0x14] ; cmp eax,[edi+0xC]


def va2off(pe_bytes, va):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe_bytes, e_lfanew + 6)[0]
    opt = struct.unpack_from("<H", pe_bytes, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt
    for i in range(nsec):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe_bytes, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll); print(f"reverted {dll} from {bak}"); return
    data = bytearray(open(dll, "rb").read())
    o = va2off(data, SITE); cur = bytes(data[o:o + 2])
    if bytes(data[o - 6:o]) != CTX_BEFORE:
        sys.exit(f"unexpected context bytes {bytes(data[o-6:o]).hex()} - refusing")
    state = "vanilla" if cur == ORIG else "ALREADY PATCHED" if cur == NEW else f"UNKNOWN {cur.hex()}"
    print(f"target: {dll}\n  site 0x{SITE:x}: {state}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if cur == NEW:
        print("already applied"); return
    if cur != ORIG:
        sys.exit("refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    data[o:o + 2] = NEW
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied: multi-party moves keep partial paths.")


if __name__ == "__main__":
    main()
