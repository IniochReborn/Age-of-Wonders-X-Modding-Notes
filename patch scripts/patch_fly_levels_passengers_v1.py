#!/usr/bin/env python3
r"""
AoWEPACK.dll: flying between levels only drains the TRANSPORT's movement, not its passengers' (2026-11-16).

User: "when a transport carrying units crosses sky levels, only the transport's movement should be set to 0. not
all the units it is carrying".

TArmy.MovedTo (0x5578DE24): with a transporter in the army it calls transporter.MovedTo(cost) and every passenger's
MovedTo with cost 0.  The fly block's TAbstractUnit.MovedTo hook (0x558CA960, from 0x55780343) forces the spent
points to 0x7F (= everything) for ANY unit whose move changed level over Sky/Chasm - passengers included.
Fix: `mov edi,0x7F` (0x558CA9A6, 5 B) -> jmp stub 0x558CAEE0:
    cmp dword ptr [ebp+8], 0 / je back / mov edi, 0x7F / back: jmp 0x558CA9AB
A carried unit (cost argument 0) keeps its movement; flyers moving on their own (cost 4) and the transport itself
are drained as before.  Rel32 only.  Needs patch_fly_levels_v1 (its dry run sees a changed block while this is
applied - revert this first).  Backup .bak_flypass.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, V2F, BAK_SUFFIX = game_file("AoWEPACK.dll"), 0x55700C00, ".bak_flypass"
SITE, BACK, STUB = 0x558CA9A6, 0x558CA9AB, 0x558CAEE0
SITE_ORIG = bytes.fromhex("bf7f000000")
CTX_VA, CTX = 0x558CA9A1, bytes.fromhex("80fa0e7505")          # cmp dl,0xE / jne +5


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(
        "cmp dword ptr [ebp+8], 0; je %#x; mov edi, 0x7f; jmp %#x" % (BACK, BACK), STUB)[0])


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
    stub, site_new = build(), rel(0xE9, SITE, STUB)
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    if g(CTX_VA, 5) != CTX or g(BACK, 1) != b"\xe9":
        print("ABORT: fly block MovedTo hook not found (patch_fly_levels_v1 expected)"); return 1
    cur = (g(SITE, 5), g(STUB, len(stub)))
    state = "vanilla" if cur == (SITE_ORIG, bytes(len(stub))) else "ours" if cur == (site_new, stub) else "OTHER"
    print("site %#x: %s | stub %#x (%d B) -> %s" % (SITE, cur[0].hex(), STUB, len(stub), state))
    if state == "OTHER": print("ABORT"); return 1
    if state == "vanilla" and any(g(STUB - 0x10, 0x40)): print("ABORT: stub zone not empty"); return 1
    bad = [hex(r) for r in relocs(DLL) if SITE - 3 <= r < SITE + 5 or STUB - 3 <= r < STUB + len(stub)]
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
