#!/usr/bin/env python3
r"""
CALL OF THE DEAD (211) FEWER CORPSE PARTICLES (2026-10-16).  AoWTCPCK.dll only.

User: the skull particles are too dense to make out - fewer per corpse.
RE: TCCorpseHS.MapFieldMsgProc (0x423BC4), msg 0x31008 (FX phase, spell id = [[ebp-8]+0xC]) spawns its kind-0x1F
sparkles (spell gfx slot 0) in two nested loops: OUTER ring [ebp-0x1C] = 1..3 (`inc [ebp-0x1C] / cmp [ebp-0x1C],4`
@0x423E37, jne 0x423C9C; ring r jitters the spawn by Random(20) + 30*r) x INNER [ebp-0x14] = 0..0x11 (`inc [ebp-0x14] /
cmp [ebp-0x14],0x12` @0x423E2A, jne 0x423CF0) = 54 sparkles per corpse.  (The Repent/Harvest cave 0x43CBB0 sits at the
loop START 0x423C95 and is untouched.)
Fix: both 7-byte `inc / cmp` pairs -> `call cave` + 2 NOP; the caves replay the inc and compare against N_PER_RING /
N_RINGS + 1 when the msg's spell is 211, else the vanilla 0x12 / 4 (flags from the cmp survive the ret into the vanilla
jne).  211 -> N_RINGS rings of N_PER_RING (default 1 x 6 = N_SKULLS 6, innermost ring, the vanilla random jitter kept).
Zone AoWTCPCK 0x442480..0x442500 (verified zero, reloc-free).  Sites were vanilla (no chain).
Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_cotdfx.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x442480, 0x442500
SPELL = 211
N_SKULLS = 6                      # particles per corpse for 211 (= N_RINGS * N_PER_RING)
N_RINGS = 1                       # how many jitter rings (vanilla 3; ring 1 = the tightest)
N_PER_RING = N_SKULLS // N_RINGS
SITES = [("inner", 0x423E2A, bytes.fromhex("ff45ec837dec12")),     # inc [ebp-0x14] / cmp [ebp-0x14],0x12
         ("outer", 0x423E37, bytes.fromhex("ff45e4837de404"))]     # inc [ebp-0x1C] / cmp [ebp-0x1C],4


def build():
    srcs = [
        ("inner", """
            inc dword ptr [ebp-0x14]
            push eax
            mov eax, [ebp-8]
            cmp dword ptr [eax+0xc], %(spell)d
            pop eax
            jne i_van
            cmp dword ptr [ebp-0x14], %(n)d
            ret
        i_van:
            cmp dword ptr [ebp-0x14], 0x12
            ret
        """ % dict(spell=SPELL, n=N_PER_RING)),
        ("outer", """
            inc dword ptr [ebp-0x1c]
            push eax
            mov eax, [ebp-8]
            cmp dword ptr [eax+0xc], %(spell)d
            pop eax
            jne o_van
            cmp dword ptr [ebp-0x1c], %(n)d
            ret
        o_van:
            cmp dword ptr [ebp-0x1c], 4
            ret
        """ % dict(spell=SPELL, n=N_RINGS + 1)),
    ]
    out = bytearray(); where = {}
    for name, src in srcs:
        va = ZONE + len(out); where[name] = va
        out += asm_pic(src, va); out += b"\x00" * ((-len(out)) % 16)
    assert ZONE + len(out) <= ZONE_END
    return bytes(out), where


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zone, where = build()
    states = {}
    for tag, site, van in SITES:
        cur = bytes(d[site - V2F:site - V2F + 7])
        want = b"\xe8" + struct.pack("<i", where[tag] - (site + 5)) + b"\x90\x90"
        states[tag] = "vanilla" if cur == van else "ours" if cur == want else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + 7 for _, s, _ in SITES)]
    print("AoWTCPCK sites %s | zone %s (%d B: %s) | N %d ring(s) x %d | relocs %s" % (states, zstate, len(zone),
          ", ".join("%s @%#x" % kv for kv in where.items()), N_RINGS, N_PER_RING, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in states.values(): print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS" and "ours" not in states.values(): print("ABORT (zone not free)"); return 1
    n = bytearray(d)
    if a.revert:
        for tag, site, van in SITES: n[site - V2F:site - V2F + 7] = van
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for tag, site, _ in SITES: n[site - V2F:site - V2F + 7] = b"\xe8" + struct.pack("<i", where[tag] - (site + 5)) + b"\x90\x90"
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_cotdfx")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
