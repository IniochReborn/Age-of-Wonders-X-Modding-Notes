r"""
CITY REBUILD = 1 TURN PER CITY HEX (2026-10-18).  AoWEPACK.dll only.

User: "I want rebuilding cities to take 1 turn per hex instead of always 5 turns."

RE - TCity.GetRebuildInfo 0x557AB50C (TCity VMT slot +0x1DC; eax = city, edx = &cost, ecx = &days):
  vanilla 1.36:  cost = GetSize*25 (lea x5 twice), days = GetSize + 1   (GetSize 0x557AA938 = byte [[city+8]+0x78], 1..4)
  live AoWx:     cost = cave 0x5580CC40 (size 1/2/3/4 -> 25/50/100/250), days = `mov eax,ebx / mov eax,5 / nop`
                 @0x557AB524 (8 B, an old in-place AoWx edit, no script on record) -> always 5.
  Every consumer goes through this slot:
    TStructure.ExecuteRebuild         : [struct+0x25] (days left) := days, then NewTurn decrements it and
                                            BuildingDone fires at 0 (days 1 = done at the next turn).
    TStructure.CanRebuild               : gold check only (cost).
    TRebuildConstructionControl (UI)    : "Rebuild" line shows cost + days from the same call -> the UI follows.
  No other "5" exists for city rebuilds (AI and exe read the slot / [struct+0x25]).
City footprint: TCity is a TMultiHexMO; HSEngine.TMultiHexMO.UpdateMapFields (HSEPack 0x5560AF6C) walks the spiral
  indices 0..Count-1 of the resource's TTerrainList [[city+8]+0x28] (Count = [list+4], data = [list+8], 2 bytes per
  index: terrain, overlay) and marks index i as a city hex when TStructure.GetTerrain(i) (VMT +0x4C, = TTerrainList.
  GetTerrain >= 0) or GetOverlay(i) (+0x58, same list) is >= 0 - i.e. when the signed terrain byte data[2i] >= 0
  (0xFE = not part).  Release.hss: size 1 = 1 hex, 2 = 2, 3 = 3, 4 = 4 (cf. patch_city_enchant_ui_v1.py FOOT).
FIX - site 0x557AB524 (8 B `8B C3 B8 05 00 00 00 90`, reloc-free) -> `mov eax,ebx / call cave / nop`; the cave
  counts the city's hexes exactly like UpdateMapFields (signed terrain byte >= 0), min 1, returns eax = days.
  Pure function of the resource data -> deterministic on every MP client; cost unchanged.
Zone AoWEPACK 0x55863F80..0x55864000 (zero, reloc-free; drought owns 0x55864000+).  PIC (rel32 call only).
Dry-run default; --apply / --revert (restores the live 5-day bytes) / --dis / --dll <scratch copy>.
Backup <game>\backup\AoWEPACK.dll.bak_rebuildhex.  No other hook on this site.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55863F80, 0x55864000
SITE, SITE_LEN = 0x557AB524, 8
LIVE5 = bytes.fromhex("8bc3b80500000090")          # days = 5 (pre-patch live state)

CAVE = """
    mov eax, [eax+8]
    mov eax, [eax+0x28]
    test eax, eax
    jz one
    push ecx
    push edx
    push esi
    mov ecx, [eax+4]
    mov esi, [eax+8]
    xor edx, edx
    test esi, esi
    jz done
    test ecx, ecx
    jle done
lp:
    cmp byte ptr [esi], 0
    jl skip
    inc edx
skip:
    add esi, 2
    dec ecx
    jnz lp
done:
    mov eax, edx
    pop esi
    pop edx
    pop ecx
    test eax, eax
    jnz out
one:
    mov eax, 1
out:
    ret
"""


def build():
    zone = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(CAVE, ZONE)[0])
    assert len(zone) <= ZONE_END - ZONE
    site = b"\x8b\xc3\xe8" + struct.pack("<i", ZONE - (SITE + 7)) + b"\x90"
    assert len(site) == SITE_LEN
    return zone, site


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F]); sb = bytes(d[SITE - V2F:SITE - V2F + SITE_LEN])
    sstate = "5-day" if sb == LIVE5 else "ours" if sb == site else "FOREIGN"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + SITE_LEN]
    print("AoWEPACK GetRebuildInfo days %#x %s | zone %#x %s (%d B) | relocs %s" % (SITE, sstate, ZONE, zstate, len(zone), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate == "ours"): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        n[SITE - V2F:SITE - V2F + SITE_LEN] = LIVE5; n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[SITE - V2F:SITE - V2F + SITE_LEN] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_rebuildhex")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
