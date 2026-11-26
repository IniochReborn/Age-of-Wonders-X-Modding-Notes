#!/usr/bin/env python3
r"""
AoO-awareness fix: type 5 = WALK to a firing spot, not "fire from position" (AoWTCPCK.dll, 2026-09-20).

build_ai_aoo_awareness.py (v5, Aug 2026) classified move type 5 as a safe ranged attack and type 3 as a
move.  The 2026-09-18 RE of the phase-5 executor table (0x41A4E8) established the opposite: type 3 =
shoot now (AbRangedTC), type 5 = walk to a firing spot (same executor as type 0).  Result observed
2026-09-20: an AI leader adjacent to a Cavalier walked one hex (type 5) to line up a next-turn shot and
ate the attack of opportunity, because the walk carried no AoO penalty and the shot-now got no boost.

Fix (one byte in the live AoO cave): the classifier's `cmp eax, 5` (safe-attack test) becomes
`cmp eax, 3`.  Type 3 then takes the safe-attack branch; type 5 falls through to the distance check with
threshold 0 (moves), i.e. provoked when it leaves the hex, skipped when stationary -- exactly the type-0
rules.  Located by byte pattern inside the AoO cave zone 0x438660..0x438B00 (unique match).
Backup AoWTCPCK.dll.bak_aootype (in <game>\backup\).  Dry-run; --apply; --revert.
"""
import argparse, os, re, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_aootype"
BASE = 0x400000
ZONE = (0x438660, 0x438B00)
PAT_VANILLA = bytes.fromhex("0fb6470483f80575")   # movzx eax,[edi+4]; cmp eax,5; jne
PAT_FIXED = bytes.fromhex("0fb6470483f80375")     # ... cmp eax,3; jne


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
    lo, hi = va2off(data, ZONE[0]), va2off(data, ZONE[1])
    zone = bytes(data[lo:hi])
    van = [m.start() for m in re.finditer(re.escape(PAT_VANILLA), zone)]
    fix = [m.start() for m in re.finditer(re.escape(PAT_FIXED), zone)]
    print(f"target: {dll}\n  AoO cave classifier: {'PATCHED' if fix and not van else 'vanilla(AoO v5)' if van and not fix else 'NOT FOUND / ambiguous'}"
          f"  (vanilla hits {[hex(ZONE[0] + o) for o in van]}, fixed hits {[hex(ZONE[0] + o) for o in fix]})")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if fix and not van:
        print("already applied"); return
    if len(van) != 1:
        sys.exit("expected exactly one vanilla match - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    off = lo + van[0] + 6
    assert data[off] == 0x05
    data[off] = 0x03
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
