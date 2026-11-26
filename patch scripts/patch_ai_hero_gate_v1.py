#!/usr/bin/env python3
r"""
Tactical AI: heroes/leaders are evaluated every decision cycle (AoWTCPCK.dll, 2026-09-20).

Vanilla TCAI counts attack proposals per cycle in [cai+0x2C] and, when it is non-zero, skips for every
THero (heroes and leaders):
  * the ENEMY loop of phase 1 (melee / ranged / gaze / touch attacks)   @0x418E8D `jne 0x418EE5`
  * the SPELL objective loop of phase 2 (leader spell casting)          @0x4198D2 `jne 0x419944`
  * the friendly loop (heals) @0x4191AE -- already removed by patch_heal_ai_tcpck_v1 (hook G)
  * the phase-4 regroup/safety pass @0x419F45 -- LEFT AS IS (regroup only when nobody attacks)
Because phase 5 executes only the single best move per cycle and re-evaluates, this made heroes act
only after every regular unit had exhausted every attack option, however poor (user: "that doesn't
seem like we want that", 2026-09-20).  With the two jumps NOP'd, hero/leader moves compete on value
like everyone else's; the hero-specific brakes (self value x4 in the retaliation term, UnitSafe-gated
approaches, escort/bold-streak rules) are untouched.  Memory: aowx-ai-hero-idle.
In-place, no cave.  Backup AoWTCPCK.dll.bak_herogate (in <game>\backup\).  Dry-run; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_herogate"
BASE = 0x400000
SITES = [  # (name, VA, vanilla bytes, patched bytes)
    ("enemy-loop gate", 0x418E8D, bytes.fromhex("7556"), b"\x90\x90"),
    ("spell-objective gate", 0x4198D2, bytes.fromhex("7570"), b"\x90\x90"),
]


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
    state = []
    print(f"target: {dll}")
    for name, va, orig, new in SITES:
        cur = bytes(data[va2off(data, va):va2off(data, va) + 2])
        st = "vanilla" if cur == orig else "PATCHED" if cur == new else f"UNKNOWN {cur.hex()}"
        state.append(st); print(f"  {name:22} {va:#x}: {st}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if all(s == "PATCHED" for s in state):
        print("already applied"); return
    if any(s.startswith("UNKNOWN") for s in state):
        sys.exit("unexpected bytes - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for name, va, orig, new in SITES:
        o = va2off(data, va); data[o:o + 2] = new
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
