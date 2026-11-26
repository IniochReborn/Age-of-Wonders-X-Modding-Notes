#!/usr/bin/env python3
r"""
AoWEPACK.dll: Depths of Plenty (spell 217) mine bonus by level, 29-level maps (2026-11-16).

User: "+1 on surface, +2 underground, +3 in depths, +4 in any abyss level".
Before (patch_depthsofplenty_v1 v2, MI cave 0x5586F0C0): bonus = min(level, 2) + 1 with level = [[mine+4]+0x12]
-> Firmament (level index 3) AND every Abyss level (4..28) got +3.
Now: level 0 Surface +1, 1 Caverns +2, 2 Depths +3, 3 Firmament +1 (counts as surface - user rule 10/31),
4..28 Abyss +4.

MI's clamp `cmp edx,2 / jbe +5 / mov edx,2` (0x5586F0F1, 10 B) -> `jmp stub` + 5 nops; stub in the free tail of
the Depths zone (0x5586F7C0):
    cmp edx, 3 / jb back / mov edx, 0 / je back / mov edx, 3 / jmp back      (back = 0x5586F0FB lea eax,[eax+edx+1])
Relative code only, no relocs.  patch_depthsofplenty_v1 will report its zone as changed while this is applied -
revert this FIRST.  Backup .bak_dopabyss.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, V2F, BAK_SUFFIX = game_file("AoWEPACK.dll"), 0x55700C00, ".bak_dopabyss"
SITE, BACK, STUB = 0x5586F0F1, 0x5586F0FB, 0x5586F7C0
SITE_ORIG = bytes.fromhex("83fa02" "7605" "ba02000000")
CTX_VA, CTX = 0x5586F0ED, bytes.fromhex("0fb65212")            # movzx edx, byte ptr [edx+0x12]
TAIL_VA, TAIL = 0x5586F0FB, bytes.fromhex("8d441001")          # lea eax,[eax+edx+1]


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "cmp edx, 3; jb %#x; mov edx, 0; je %#x; mov edx, 3; jmp %#x" % (BACK, BACK, BACK)
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, STUB)[0])


def relocs(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [ib + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    stub = build()
    site_new = rel(0xE9, SITE, STUB) + b"\x90" * 5
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    if g(CTX_VA, 4) != CTX or g(TAIL_VA, 4) != TAIL:
        print("ABORT: Depths of Plenty MI cave not found (patch_depthsofplenty_v1 v2 expected)"); return 1
    cur = (g(SITE, 10), g(STUB, len(stub)))
    state = ("vanilla" if cur == (SITE_ORIG, bytes(len(stub))) else "ours" if cur == (site_new, stub) else "OTHER")
    print("site %#x: %s | stub %#x (%d B): %s -> %s" % (SITE, cur[0].hex(), STUB, len(stub), cur[1].hex(), state))
    if state == "OTHER": print("ABORT"); return 1
    if state == "vanilla" and any(g(STUB - 0x10, 0x40)): print("ABORT: stub zone not empty"); return 1
    bad = [hex(r) for r in relocs(DLL) if SITE - 3 <= r < SITE + 10 or STUB - 3 <= r < STUB + len(stub)]
    if bad: print("ABORT: relocs in range", bad); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    ws = ((SITE, SITE_ORIG), (STUB, bytes(len(stub)))) if a.revert else ((SITE, site_new), (STUB, stub))
    with open(DLL, "r+b") as f:                      # in-place (house rule)
        for va, b in ws:
            d[va - V2F:va - V2F + len(b)] = b; f.seek(va - V2F); f.write(b)
    assert open(DLL, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
