#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Hurl Skull (ability 0xCC) AOE hits each unit ONCE, only inside Fire Ball's 7 hexes (2026-10-24).

Bug (user, MP 10/23): the skull damaged a ~5x5 area instead of the previewed 3x3 (Fire Ball's 7 hexes) and did 17 DMG
to a Fire Elemental (DMG 8 per hit -> it was hit several times).

Root cause: HSEngine.TMapField.SendMapFieldMsg 0x55607944 delivers a field message to EVERY object listed on the field
and sets [msg+0x18] = that object's per-field tag byte (0 = the object's own hex, non-zero = a secondary entry on a
neighbouring field).  Fire Ball's unit handler (TCPCK 0x420FCA) skips the message unless [msg+0x18] == 0.  Our HM cave
(patch_bxl_ranged_abilities_v2..v7, 0x4521F0) handles msg 0x31020 WITHOUT that test, so a unit standing next to the
area was hit through its neighbour entries (radius 2) and units inside were hit once per covered entry (the centre
unit up to 7x).

Fix: HM's `je hm_own` (0x4521F9, 74 0B -> 0x452206) is redirected to an 8-byte stub in the unused gap 0x452272:
    cmp dword ptr [eax+0x18], 0     ; eax = msg ([ebp-8])
    jne 0x45226D                    ; hm_out -> 0x421728 (not our home hex: ignore)
    jmp 0x452206                    ; hm_own (unchanged)
Self-relative short jumps only, no relocs.  MP: same on every machine.  Layered on top of v7 (revert this FIRST).
Backup <game>\backup\AoWTCPCK.dll.bak_hskhome.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_hskhome"
V2F = 0x400C00
CTX_VA, CTX = 0x4521F0, bytes.fromhex("8b45f8813820100300")      # mov eax,[ebp-8] / cmp [eax],0x31020
JE_VA, JE_ORIG, JE_NEW = 0x4521F9, bytes.fromhex("740b"), bytes.fromhex("7477")   # je 0x452206 -> je 0x452272
OUT_CTX_VA, OUT_CTX = 0x45226D, bytes.fromhex("e9b6f4fcff")      # hm_out: jmp 0x421728
STUB_VA = 0x452272
STUB_ORIG = bytes(8)
STUB_NEW = bytes.fromhex("83781800" "75f5" "eb8c")               # cmp [eax+0x18],0 / jne 0x45226D / jmp 0x452206


def reloc_hits(path, lo, hi):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type and lo - 3 <= ib + e.rva < hi: out.append(hex(ib + e.rva))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    if g(CTX_VA, len(CTX)) != CTX or g(OUT_CTX_VA, len(OUT_CTX)) != OUT_CTX:
        print("ABORT: Hurl Skull HM cave not found (patch_bxl_ranged_abilities_v7 expected)"); return 1
    je, stub = g(JE_VA, 2), g(STUB_VA, 8)
    state = ("vanilla" if (je, stub) == (JE_ORIG, STUB_ORIG) else
             "ours" if (je, stub) == (JE_NEW, STUB_NEW) else "OTHER")
    print("HM je %#x: %s | stub %#x: %s -> %s" % (JE_VA, je.hex(), STUB_VA, stub.hex(), state))
    if state == "OTHER": print("ABORT"); return 1
    bad = reloc_hits(a.dll, JE_VA, STUB_VA + 8)
    if bad: print("ABORT: relocs in range", bad); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    je_w, st_w = (JE_ORIG, STUB_ORIG) if a.revert else (JE_NEW, STUB_NEW)
    d[JE_VA - V2F:JE_VA - V2F + 2] = je_w
    d[STUB_VA - V2F:STUB_VA - V2F + 8] = st_w
    if not a.apply and not a.revert: print("10 byte change. Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:                    # in-place (house rule: "wb" is refused on the live DLLs)
        for va, b in ((JE_VA, je_w), (STUB_VA, st_w)): f.seek(va - V2F); f.write(b)
    assert open(a.dll, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
