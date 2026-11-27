"""
Sky / Chasm follow-ups from the 2026-11-26 terrain-spell audit.  AoWEPACK.dll, three same-size in-place edits inside
existing caves (no hooks, no new cave, no relocs).

1. DROUGHT `waterok` (patch_drought_v1.py; live @0x55864409, 24 B): "does this water hex touch land?" was a blacklist
   (not land = 0, 6, 0xA, 0xD, 0xF), so Sky 0xE / Chasm 0xB / Earth 7 / Rock 8 / Lava 9 neighbours counted as land and
   water beside the void was desert-filled like a coast.  Now a land whitelist {1,2,3,4,5,0xC} (bit mask 0x103E).
2. `t_open` connectivity test of TECTONIC SHIFT (patch_tectonic_v1.py; live @0x55874FD2) and PYROCLASM
   (patch_pyroclasm_v1.py; live @0x5587C8A8), 14 B each: closed terrains were {0, 7..0xA}; Sky and Chasm counted as
   walkable, so a new mountain / lava hex could cut off an area whose only other link ran across the void.  Now closed
   = {0, 7, 8, 9, 0xA, 0xB, 0xE} (bit mask 0x4F81).
Shape of both: `push mask / bt [esp],edx / pop edx / jc|jnc <the old reject label> / nops` (edx = the terrain byte the
routine had just loaded and does not use again).

⚠ The owning scripts' SOURCES are unchanged (drought's zone already reports an older build; pyroclasm / tectonic are
chained).  Re-syncing any of their zones restores the old checks -> re-run this script afterwards (it then sees the
original bytes again).  Backup .bak_skyvoid.  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_bugfix_1126_v1 import reloc_hits

DLL, V2F, BAK_SUFFIX = game_file("AoWEPACK.dll"), 0x55700C00, ".bak_skyvoid"
LAND = sum(1 << t for t in (1, 2, 3, 4, 5, 0x0C))
CLOSED = sum(1 << t for t in (0, 7, 8, 9, 0x0A, 0x0B, 0x0E))


def bt(mask, jcc, rel_from_start, size):
    b = b"\x68" + mask.to_bytes(4, "little") + bytes.fromhex("0fa31424") + b"\x5a" + bytes([jcc, rel_from_start - 12])
    return b + b"\x90" * (size - len(b))


T_OPEN_OLD = bytes.fromhex("85d2741683fa07720583fa0a760c")                       # reject label at +0x1A
WATEROK_OLD = bytes.fromhex("85d2743683fa06743183fa0a742c83fa0d742783fa0f7422")   # wo_n at +0x3A
SITES = [(0x55864409, WATEROK_OLD, bt(LAND, 0x73, 0x3A, 24), "Drought waterok: land whitelist"),
         (0x55874FD2, T_OPEN_OLD, bt(CLOSED, 0x72, 0x1A, 14), "Tectonic t_open: Sky/Chasm closed"),
         (0x5587C8A8, T_OPEN_OLD, bt(CLOSED, 0x72, 0x1A, 14), "Pyroclasm t_open: Sky/Chasm closed")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = open(DLL, "rb").read()
    writes = []
    for va, old, new, what in SITES:
        assert len(old) == len(new)
        cur = d[va - V2F:va - V2F + len(old)]
        st = "old" if cur == old else "ours" if cur == new else "OTHER"
        print("%#x %-36s %s" % (va, what, st))
        if st == "OTHER": print("ABORT"); return 1
        if a.revert and st == "ours": writes.append((va, old))
        if not a.revert and st == "old": writes.append((va, new))
    bad = reloc_hits(DLL, [(va, va + len(o)) for va, o, _, _ in SITES])
    if bad: print("ABORT: relocs in range", bad); return 1
    if not a.apply and not a.revert: print("Dry run OK (%d writes) - rerun with --apply (or --revert)." % len(writes)); return 0
    if not writes: print("nothing to do"); return 0
    bak = bak_path(DLL, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        for va, b in writes: f.seek(va - V2F); f.write(b)
    print("reverted" if a.revert else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
