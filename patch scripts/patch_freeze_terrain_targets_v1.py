"""
Freeze Terrain: the cast preview glowed over every hex (Sky, Chasm, rock, snow ...) - 2026-11-26.  AoWEPACK.dll.

patch_frost_terrain_v1 widened TFreezeWater's two water-only target gates (ValidTargetMapF @0x5579EBA0, field = ebx,
pass 0x5579EBAF / reject 0x5579EBC0; ValidTargetSelectionMapF @0x5579EBF0, field = esi, pass 0x5579EBFF / reject
0x5579EC10) to `jmp pass`, so every explored hex counted as a valid target.  The gates now accept exactly the
terrains the spell acts on (TFreezeWaterTE.ChangeTerrain + frost cave 0x55816040):
    Water 0, Cave Water 0xA (-> ice), Ice 6, Cave Ice 0xD (melt timer refreshed), Lava 9 (-> wasteland),
    Grass 1, Desert 2, Steppe 4, Wasteland 5 (-> snow), Snow 3 (unchanged, but shown as valid - user).
Earth 7, Rock 8, Chasm 0xB, Dirt 0xC, Sky 0xE are rejected -> dimmed in the preview, like the hexes other
terrain spells cannot change.  Both gates stay identical (as in vanilla, where both were water-only).

Sites: the two `EB 0D` + 13 NOP gates -> 5-byte jmp into cave 0x558BB100 (rel32 only).  Backup .bak_freezetgt.
Dry-run default; --apply; --revert (puts the widened `EB 0D` gates back, zeroes the cave).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_bugfix_1126_v1 import reloc_hits

DLL, V2F, BAK_SUFFIX = game_file("AoWEPACK.dll"), 0x55700C00, ".bak_freezetgt"
CAVE, ROOM = 0x558BB100, 0x40
VALID = (0, 1, 2, 3, 4, 5, 6, 9, 0x0A, 0x0D)   # 3 Snow added (user 11/26: glow on snow too)
MASK = sum(1 << t for t in VALID)
GATE = b"\xEB\x0D" + b"\x90" * 13
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def jmp(at, to): return b"\xe9" + struct.pack("<i", to - (at + 5))


def gate_cave(va, reg, ok, no):
    return bytes(ks.asm("""
        movzx eax, byte ptr [%s+0x14]
        cmp al, 0x10
        jae 0x%x
        mov edi, 0x%x
        bt edi, eax
        jc 0x%x
        jmp 0x%x
    """ % (reg, no, MASK, ok, no), va)[0])


C1 = gate_cave(CAVE, "ebx", 0x5579EBAF, 0x5579EBC0)
C2_VA = CAVE + 0x20
C2 = gate_cave(C2_VA, "esi", 0x5579EBFF, 0x5579EC10)
assert len(C1) <= 0x20 and len(C2) <= 0x20
CAVE_NEW = C1 + bytes(0x20 - len(C1)) + C2 + bytes(0x20 - len(C2))
SITES = [(0x5579EBA0, GATE, jmp(0x5579EBA0, CAVE) + GATE[5:]), (0x5579EBF0, GATE, jmp(0x5579EBF0, C2_VA) + GATE[5:])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = open(DLL, "rb").read()
    g = lambda va, n: d[va - V2F:va - V2F + n]
    st = ["widened" if g(va, 15) == o else "ours" if g(va, 15) == h else "OTHER" for va, o, h in SITES]
    cave = g(CAVE, ROOM); cst = "zero" if not any(cave) else "ours" if cave == CAVE_NEW else "FOREIGN"
    state = "old" if set(st) == {"widened"} and cst == "zero" else "ours" if set(st) == {"ours"} and cst == "ours" else "MIXED"
    print("gates %s | cave %#x %s -> %s" % (st, CAVE, cst, state))
    if state == "MIXED": print("ABORT (patch_frost_terrain_v1 gates expected)"); return 1
    bad = reloc_hits(DLL, [(va, va + 15) for va, _, _ in SITES] + [(CAVE, CAVE + ROOM)])
    if bad: print("ABORT: relocs in range", bad); return 1
    if a.revert: writes = [(va, o) for va, o, _ in SITES] + [(CAVE, bytes(ROOM))] if state == "ours" else []
    else: writes = [(CAVE, CAVE_NEW)] + [(va, h) for va, _, h in SITES] if state == "old" else []
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
