#!/usr/bin/env python3
r"""
AoWEPACK.dll: TCombatPlayerList.GetPlayers bounds check (2026-10-24, event-log crash follow-up to patch_combatlog_refcount v1.1).

Bug (user 10/24, save 'autosave----Allair 2P'): loading -> event list AV.  VEH: AV read 0 at 0x557288B1 =
TCombatPlayerList.GetPlayers+9 (`mov eax,[[[list+8]+4]+idx*4]`, items array nil = EMPTY list) from
TCombatEventLog.GetTextColor 0x55728F81 ([[ev+0x18]+0x10] = combat data, player idx [data+0x24], list [data+0x38]).
Cause: patch_combatlog_refcount v1.1 replaces a POISONED logbook (save written while the vanilla refcount bug left it
dangling) with a fresh TCombatLogbook.Create - its combat data has EMPTY player lists.  GetText copes (blank text),
but GetTextColor / GetLeftIcon / GetRightIcon / Execute all index the player list -> AV.

Fix: GetPlayers 0x557288A8 (13 B) -> jmp cave 'CPG1' 0x5583C380..0x5583C3E0:
    movsx edx, dl ; list = [eax+8] ; nil or idx >= count (unsigned) -> return a static ZERO record (PIC)
    else -> [[list+4]+idx*4] (vanilla)
The zero record reads as "no player" (byte +8 = 0): the colour / icon getters take their vanilla default branch.
Valid indices behave exactly as before (every combat caller); only the out-of-range case changes (crash -> default).
No relocs (site or zone); PIC via call/pop.  Backup <game>\backup\AoWEPACK.dll.bak_cpguard.
Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_cpguard"
V2F = 0x55700C00
SITE = 0x557288A8
SITE_ORIG = bytes.fromhex("0fbed28b40088b40048b0490c3")
ZONE, ZONE_END = 0x5583C380, 0x5583C3E0
CODE = ZONE + 0x10
DUMMY = ZONE + 0x40                                  # 0x20 zero bytes = the "no player" record


def build_zone():
    c = bytearray()
    c += bytes.fromhex("0fbed2")                     # movsx edx, dl
    c += bytes.fromhex("8b4008")                     # mov eax, [eax+8]
    c += bytes.fromhex("85c0")                       # test eax, eax
    c += bytes.fromhex("740c")                       # jz dummy
    c += bytes.fromhex("3b5008")                     # cmp edx, [eax+8]   (count)
    c += bytes.fromhex("7307")                       # jae dummy          (also catches idx < 0)
    c += bytes.fromhex("8b4004")                     # mov eax, [eax+4]   (items)
    c += bytes.fromhex("8b0490")                     # mov eax, [eax+edx*4]
    c += bytes.fromhex("c3")                         # ret
    assert len(c) == 0x16
    c += bytes.fromhex("e800000000")                 # dummy: call $+5
    c += bytes.fromhex("58")                         # pop eax  (= CODE + 0x1B)
    c += bytes([0x83, 0xC0, DUMMY - (CODE + 0x1B)])  # add eax, DUMMY - here
    c += bytes.fromhex("c3")                         # ret
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = b"CPG1"
    z[0x10:0x10 + len(c)] = c
    assert 0x10 + len(c) <= DUMMY - ZONE
    return bytes(z)


def site_new():
    rel = CODE - (SITE + 5)
    return b"\xe9" + rel.to_bytes(4, "little", signed=True) + b"\x90" * (len(SITE_ORIG) - 5)


def relocs(path, lo, hi):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [hex(ib + e.rva) for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries
            if e.type and lo - 3 <= ib + e.rva < hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: d[va - V2F:va - V2F + n]
    zone, new = build_zone(), site_new()
    site, zl = g(SITE, len(SITE_ORIG)), g(ZONE, ZONE_END - ZONE)
    state = ("vanilla" if site == SITE_ORIG and zl == bytes(len(zl)) else
             "ours" if site == new and zl == zone else "OTHER")
    print("GetPlayers %#x: %s | zone %#x: %s -> %s" % (SITE, site.hex(), ZONE, "zero" if not any(zl) else zl[:4], state))
    if state == "OTHER": print("ABORT (site or zone changed by another patch)"); return 1
    bad = relocs(a.dll, SITE, SITE + len(SITE_ORIG)) + relocs(a.dll, ZONE, ZONE_END)
    if bad: print("ABORT: relocs", bad); return 1
    if state == ("vanilla" if a.revert else "ours"): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not a.apply and not a.revert: print("site 13 B + zone %d B. Dry run OK - rerun with --apply (or --revert)." % len(zone)); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    ws, wz = (SITE_ORIG, bytes(len(zone))) if a.revert else (new, zone)
    with open(a.dll, "r+b") as f:                    # in-place (house rule: "wb" is refused on the live DLLs)
        f.seek(SITE - V2F); f.write(ws)
        f.seek(ZONE - V2F); f.write(wz)
    d2 = open(a.dll, "rb").read()
    assert d2[SITE - V2F:SITE - V2F + len(ws)] == ws and d2[ZONE - V2F:ZONE - V2F + len(wz)] == wz
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
