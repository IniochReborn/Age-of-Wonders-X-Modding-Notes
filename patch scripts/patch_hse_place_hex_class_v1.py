#!/usr/bin/env python3
r"""
HSEPack.dpl: painting Earth/Rock onto WATER no longer crashes the editor (2026-10-31; port of BXL's Ziggurat fix).

User: with the new cross-level brushes, Earth/Rock painted on surface land works but on water -> "Access violation
at 5579AF2F / 5579AF59 in AoWEPACK.dll" (TAoWWaterHexagon.Show) and the editor closes.  Works in Ziggurat.
Cause (vanilla): IsoHex.TIsometricHexagonResource.PlaceResourceUser (0x55619BF8) finds the hexagon already on the
field and, if there is one, just re-links it to the new resource (VMT+0x110) - whatever its class.  A
TAoWWaterHexagon re-linked to the Earth/Rock wall resource then draws water frames 0x8C+ / shore frames 0x24 out
of the wall's image list -> nil/garbage frame -> AV.  (Grass etc. never get here: they are found by
TMORTerrainControl.GetRndResource with the water class id, miss, and take the replacement path.)
Fix (BXL's, verbatim logic): reuse the existing hexagon only when its ClassID (hexagon VMT+0x24) equals the
resource's hexagon class id (resource VMT+0x58); otherwise take the vanilla "create a new hexagon" path 0x55619C91.
  site 0x55619C30  8B D8 85 DB 74 5B  (mov ebx,eax; test ebx,ebx; je 0x55619C91) -> jmp cave + nop
Cave 0x5561C800..0x5561C840 (zero padding inside CODE, the same spot Ziggurat uses; unclaimed by our scripts).
rel32 only (PIC).  Dry-run default; --apply; --revert.  Backup <game>\backup\HSEPack.dpl.bak_placehexcls.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("HSEPack.dpl")
BASE = 0x55600000
SITE, ORIG = 0x55619C30, bytes.fromhex("8bd885db745b")
REUSE, CREATE = 0x55619C36, 0x55619C91
ZONE, ZONE_END = 0x5561C800, 0x5561C840


def build():
    code = bytearray(bytes.fromhex(
        "8bd8"          # mov ebx, eax
        "85db"          # test ebx, ebx
        "7419"          # je create
        "8bc6"          # mov eax, esi            ; resource
        "8b10"          # mov edx, [eax]
        "ff5258"        # call [edx+0x58]         ; hexagon class id the resource makes
        "50"            # push eax
        "8bc3"          # mov eax, ebx            ; existing hexagon
        "8b10"          # mov edx, [eax]
        "ff5224"        # call [edx+0x24]         ; ClassID
        "5a"            # pop edx
        "3bc2"          # cmp eax, edx
        "7505"          # jne create
        "e900000000"    # jmp REUSE
        "e900000000"))  # create: jmp CREATE
    assert len(code) == 0x24
    struct.pack_into("<i", code, 0x1B, REUSE - (ZONE + 0x1F))
    struct.pack_into("<i", code, 0x20, CREATE - (ZONE + 0x24))
    assert code[0x05] == 0x19 and ZONE + 0x06 + 0x19 == ZONE + 0x1F and code[0x19] == 0x05
    return bytes(code)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    cave = build()
    hook = b"\xe9" + struct.pack("<i", ZONE - (SITE + 5)) + b"\x90"
    P = [(SITE, ORIG, hook), (ZONE, bytes(len(cave)), cave)]
    rl = {BASE + e.rva for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    assert not any(d[off(ZONE) + len(cave):off(ZONE_END)])
    sts = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    print("site %#x %s | cave %#x %s | relocs %s" % (SITE, sts[0], ZONE, sts[1], bad or "none"))
    if "OTHER" in sts or bad or len(set(sts)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_placehexcls")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        for s, o, n in reversed(P):
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
