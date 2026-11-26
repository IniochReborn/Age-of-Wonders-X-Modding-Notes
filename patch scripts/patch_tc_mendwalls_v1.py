#!/usr/bin/env python3
r"""
MEND WALLS (216, Earth L1 combat, 2026-10-17).  AoWTCPCK.dll only.

Spell: TOoze clone (pipeline, pfs donor 134, tc_type 0x0A) aliased 216 -> 0x7C (patch_tc_spell_alias_v1) = 19 Ooze
strikes, one per hex of the radius-2 area, Ooze 19-hex preview, range 0xFF.  This script gives the strikes their effect:
  LND  Ooze landing path 0x40C922 (`jmp 0x43AC40` = patch_ooze_extinguish_v1, chained; the previous target is decoded at
       apply time and kept in the zone table for an exact revert): when [[ebp-0x20]+0x18] == 216, the strike's own hex
       ([ebp-0x28] x / [ebp-0x2C] y) is looked up (GetMapLevel 0x401E64 / GetField 0x401E54), its TCityWall HS found
       (field VMT+0x80 FindOwnedChild ClassID 0x220504) and TCityWall.SetHP 0x405AE4(hs, max) called, max = dword
       [[0x4693D0] + (material-1)*4] (material byte [hs+0x2D] in 1..2, the vanilla bound).  SetHP's heal branch stores
       HP, recomputes the image state and sets dirty.  v2 (2026-10-17, user's full spec: "repair all walls in AOE by a
       RANDOM amount, each hex rolls individually, no repair if fully broken"): a DESTROYED segment (HP <= 0) is left
       alone; a damaged one gains max/4 + RandInt(max/2 + 1) (= 25..75 % of max, capped at max) - RandInt = System.@
       RandInt thunk 0x401020, the combat RNG stream (seeded from synced state at combat start; the stream the strike
       landings / breath block rolls use), never map.Random.  After a repair, when EVERY wall in [[[0x469420]]+0x120] has
       HP > 0 the breach flag
       [[[map]+0xE4]+0xC]+0x4D is cleared again (set by SetHP at HP 0; read by the AI ram focus).  Then -> 0x40CAF2
       (the strike's end: no Ooze mud, no extinguish).  Other spells -> the previous target unchanged.
  TGT  NextStrike hail target call 0x40E35D (`call 0x43D890` = Oil Spring 'tgt' cave, chained): 216 returns ZF=1 (the
       Ooze nil-target branch) so no TOoze combat action targets a unit (the Oil Spring v3.1 AV); others -> previous.
Not touched: AoWEPACK TCombatWall (AI / auto-combat wall objects) - the tactical AI's wall values stay as they were.
Zone AoWTCPCK 0x447400..0x447800 (verified zero, reloc-free): +0 prev LND, +4 prev TGT (script data), caves from +0x10.
Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_mendwalls.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x447400, 0x447800
SPELL = 216
END_STRIKE = 0x40CAF2
SITES = [("lnd", 0x40C922, 0xE9),           # jmp prev (Ooze landing path)
         ("tgt", 0x40E35D, 0xE8)]           # call prev (NextStrike target routing)

LND = """
    push eax
    mov eax, [ebp-0x20]
    cmp dword ptr [eax+0x18], %(spell)d
    pop eax
    jne %(prev_lnd)#x
    pushal
    call $D
    pop ebx
    sub ebx, $D
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    mov eax, [eax+0x10]
    xor edx, edx
    call 0x401e64
    test eax, eax
    je done
    mov edx, [ebp-0x28]
    mov ecx, [ebp-0x2c]
    call 0x401e54
    test eax, eax
    je done
    mov esi, eax
    mov edx, 0x220504
    mov ecx, [eax]
    call dword ptr [ecx+0x80]
    test eax, eax
    je done
    mov edi, eax
    movzx eax, byte ptr [edi+0x2d]
    dec eax
    cmp eax, 1
    ja done
    mov edx, [ebx+0x4693d0]
    test edx, edx
    je done
    mov esi, [edx+eax*4]
    mov eax, [edi+0x20]
    test eax, eax
    jle done
    cmp eax, esi
    jge done
    mov eax, esi
    shr eax, 1
    inc eax
    call 0x401020
    mov edx, esi
    shr edx, 2
    add eax, edx
    add eax, [edi+0x20]
    cmp eax, esi
    jle capped
    mov eax, esi
capped:
    mov edx, eax
    mov eax, edi
    call 0x405ae4
    mov eax, [ebx+0x469420]
    mov eax, [eax]
    test eax, eax
    je done
    mov esi, [eax+0xe4]
    test esi, esi
    je done
    mov esi, [esi+0xc]
    test esi, esi
    je done
    mov eax, [eax+0x120]
    test eax, eax
    je done
    mov ecx, [eax+8]
    mov edx, [eax+4]
lp:
    dec ecx
    js clear
    mov eax, [edx+ecx*4]
    test eax, eax
    je lp
    cmp dword ptr [eax+0x20], 0
    jle done
    jmp lp
clear:
    mov byte ptr [esi+0x4d], 0
done:
    popal
    jmp %(end)#x
"""
TGT = """
    cmp dword ptr [eax+0x18], %(spell)d
    jne %(prev_tgt)#x
    xor eax, eax
    ret
"""


def build(prev):
    out = bytearray(struct.pack("<II", prev["lnd"], prev["tgt"]) + bytes(8)); where = {}
    for tag, src in (("lnd", LND), ("tgt", TGT)):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[tag] = va
        out += asm_pic(src % dict(spell=SPELL, end=END_STRIKE, prev_lnd=prev["lnd"], prev_tgt=prev["tgt"]), va)
    assert ZONE + len(out) <= ZONE_END
    return bytes(out), where


def target(d, site, op):
    b = d[site - V2F:site - V2F + 5]
    return site + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == op else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    cur = {tag: target(d, site, op) for tag, site, op in SITES}
    # applied (or a stale layout): the previous targets live in the zone table; else they are the sites' current targets
    prev = dict(zip(("lnd", "tgt"), struct.unpack_from("<II", zl, 0))) if any(zl) else dict(cur)
    zone, where = build(prev)
    states = {}
    for tag, site, op in SITES:
        c = cur[tag]
        states[tag] = "ours" if c == where[tag] else "ours(old)" if c is not None and ZONE <= c < ZONE_END and any(zl) \
            else "OTHER" if c is None or ZONE <= c < ZONE_END \
            else "chain(%#x)" % c if c == prev[tag] else "MOVED(%#x, table %#x)" % (c, prev[tag])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "older build (upgrade)" \
        if all(v.startswith("ours") for v in states.values()) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + 5 for _, s, _ in SITES)]
    print("AoWTCPCK sites %s | zone %s (%d B: %s) | prev lnd %#x tgt %#x | relocs %s" % (states, zstate, len(zone),
          ", ".join("%s @%#x" % kv for kv in where.items()), prev["lnd"], prev["tgt"], bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[16:], ZONE + 16):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or any(v.startswith(("OTHER", "MOVED")) for v in states.values()): print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    n = bytearray(d)
    if a.revert:
        for tag, site, op in SITES: n[site - V2F + 1:site - V2F + 5] = struct.pack("<i", prev[tag] - (site + 5))
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for tag, site, op in SITES: n[site - V2F + 1:site - V2F + 5] = struct.pack("<i", where[tag] - (site + 5))
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_mendwalls")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
