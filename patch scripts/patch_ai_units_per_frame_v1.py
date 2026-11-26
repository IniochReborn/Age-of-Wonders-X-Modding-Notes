#!/usr/bin/env python3
r"""
Tactical AI: evaluate more units per frame (AoWTCPCK.dll, 2026-09-20) -- faster AI turns.

TAoWCombatMap.NewFrame (0x41C440) runs ONE TCAI phase per rendered frame, and phases 1 (move
generation) and 2 (objectives) each stop after `[cai+0x24] >= 1` unit per call:
    0x419289  cmp dword [eax+0x24], 1 ; jl <next unit>      (phase 1)
    0x419B2C  cmp dword [eax+0x24], 1 ; jl <next unit>      (phase 2)
So an AI side with 26 units spends ~52 frames (~2 s at 25-30 fps) per decision cycle before it even
executes a move (live capture 2026-09-20: phase-1 unit index advanced once per ~30 ms).  Raising the
per-call limit lets one frame evaluate UNITS_PER_FRAME units; the per-unit work itself is a few ms.
(Move/shot animations are separate and unchanged.)
In-place immediates (imm8), no cave.  Backup AoWTCPCK.dll.bak_unitsframe (in <game>\backup\).
Dry-run; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_unitsframe"
BASE = 0x400000
UNITS_PER_FRAME = 12       # vanilla 1; 1..127 (imm8)
SITES = [("phase-1 unit limit", 0x41928C), ("phase-2 unit limit", 0x419B2F)]   # the imm8 of `cmp dword [eax+0x24], imm8`
CTX = bytes.fromhex("8b45fc837824")   # mov eax,[ebp-4] ; cmp dword [eax+0x24], ...


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
    assert 1 <= UNITS_PER_FRAME <= 127
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll); print(f"reverted {dll} from {bak}"); return
    data = bytearray(open(dll, "rb").read())
    print(f"target: {dll}")
    vals = []
    for name, va in SITES:
        o = va2off(data, va)
        if bytes(data[o - 6:o]) != CTX:
            sys.exit(f"{name}: unexpected context bytes {bytes(data[o-6:o]).hex()} - refusing")
        vals.append(data[o]); print(f"  {name:20} {va:#x}: current limit {data[o]}")
    if not a.apply:
        print(f"dry run - would set both to {UNITS_PER_FRAME} (use --apply)"); return
    if all(v == UNITS_PER_FRAME for v in vals):
        print("already at that value"); return
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for name, va in SITES:
        data[va2off(data, va)] = UNITS_PER_FRAME
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print(f"applied: {UNITS_PER_FRAME} units per frame in phases 1 and 2.")


if __name__ == "__main__":
    main()
