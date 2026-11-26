#!/usr/bin/env python3
r"""
CALL OF THE DEAD (211) INSTANT CAST (2026-10-16).  AoWTCPCK.dll only.

User: "Call of the Dead should just start when cast - currently it makes me select a hex to target."
RE: picking a spell in the combat spell book calls the unit HS's SetSpell 0x423270 (VMT method; eax = HS, edx = spell id
-> [hs+0x38]).  At 0x4233B0 it reads SpellTypes[id] and, for the vanilla INSTANT classes 9 / 0x17 / 0x1D / 0x25 (High
Prayer) / 0x2C, fires at once: `AbRangedTC(hs, 0, 0)` 0x423860 (= the same routine the human click 0x41EAC1 and the AI
0x41AEA2 use: builds the TCAbRangedTE via 0x40F4B0 and posts it), then [ebp-0xC] := -1 and hs.VMT+0x100 (deselect)
@0x4233E0.  Every other class falls through to targeting.  211 is class 0x27 (corpse spell, needed by the Execute
dispatch and patch_tc_callofdead_v1's sweep) so it takes the targeting path.
Fix: call-hook 0x4233A2 (`call 0x402DDC`, rel32, no reloc) -> cave IN: replay the call; if [ebp-8] == 211 -> AbRangedTC
(hs, x, y) with x/y = the caster's own hex (hs VMT+0x74 / +0x78, the calls 0x40F4B0 uses for the caster) so the TE has a
sane centre (the BC sweep raises every corpse on the field regardless), drop the return and resume at 0x4233E0 (vanilla
instant tail: deselect + UI refresh).  Mana/turn handling = the TE's normal execution, as for High Prayer.  AI (own
target via AbRangedTC) and fast combat (patch_callofdead_v1 v2) are untouched.
Zone AoWTCPCK 0x442400..0x442480 (verified zero, reloc-free); first 4 bytes = the site's previous call target (data)
for --revert.  Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.  Backup <game>\backup\
AoWTCPCK.dll.bak_cotdinstant.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs, call_target

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x442400, 0x442480
SPELL = 211
ABRANGED, INSTANT_TAIL = 0x423860, 0x4233E0
HOOKS = [("IN", 0x4233A2, "in")]
TABLE = 4


def caves(prev):
    return [
        # in: SetSpell 0x423270 frame ([ebp-4] HS, [ebp-8] spell id); replaces `call 0x402DDC` @0x4233A2
        ("in", """
            call %(prev_in)#x
            mov eax, [ebp-8]
            cmp eax, %(spell)d
            jne in_out
            mov eax, [ebp-4]
            mov edx, [eax]
            call dword ptr [edx+0x78]
            movsx ecx, al
            push ecx
            mov eax, [ebp-4]
            mov edx, [eax]
            call dword ptr [edx+0x74]
            movsx edx, al
            pop ecx
            mov eax, [ebp-4]
            call %(abranged)#x
            add esp, 4
            jmp %(tail)#x
        in_out:
            ret
        """),
    ], dict(spell=SPELL, abranged=ABRANGED, tail=INSTANT_TAIL, prev_in=prev.get("IN", 0))


def build(prev):
    srcs, fmt = caves(prev); out = bytearray(); where = {}
    for name, src in srcs:
        va = ZONE + TABLE + len(out); where[name] = va
        out += asm_pic(src % fmt, va); out += b"\x00" * ((-len(out)) % 16)
    table = b"".join(struct.pack("<I", prev.get(t, 0)) for t, _, _ in HOOKS)
    return table + bytes(out), where


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zprev = {t: struct.unpack_from("<I", zl, 4 * i)[0] for i, (t, _, _) in enumerate(HOOKS)}
    states, prev = {}, {}
    for tag, site, _ in HOOKS:
        tgt, op = call_target(d, site, V2F)
        if op != 0xE8: states[tag] = "NOT-A-CALL"; continue
        if ZONE <= tgt < ZONE_END: states[tag] = "ours"; prev[tag] = zprev[tag]
        else: states[tag] = "chain-ready"; prev[tag] = tgt
    zone, where = build(prev)
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + 5 for _, s, _ in HOOKS)]
    print("AoWTCPCK sites %s | prev %s | zone %s (%d B: %s) | relocs %s" % (states, {k: hex(v) for k, v in prev.items()},
          zstate, len(zone), ", ".join("%s @%#x" % kv for kv in where.items()), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[TABLE:], ZONE + TABLE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "NOT-A-CALL" in states.values(): print("ABORT (site/reloc)"); return 1
    if any(v == 0 for v in prev.values()): print("ABORT (previous target unknown)"); return 1
    ours = [t for t, s in states.items() if s == "ours"]
    if zstate == "DIFFERS" and not ours: print("ABORT (zone not free)"); return 1
    n = bytearray(d)
    if a.revert:
        for tag, site, _ in HOOKS:
            if states[tag] == "ours": n[site - V2F:site - V2F + 5] = b"\xe8" + struct.pack("<i", prev[tag] - (site + 5))
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for tag, site, cave in HOOKS: n[site - V2F:site - V2F + 5] = b"\xe8" + struct.pack("<i", where[cave] - (site + 5))
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_cotdinstant")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
