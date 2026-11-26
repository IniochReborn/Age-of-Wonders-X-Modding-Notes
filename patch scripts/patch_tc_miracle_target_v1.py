#!/usr/bin/env python3
r"""
MIRACLE (209) TACTICAL TARGETING (2026-10-16).  AoWTCPCK.dll only.

User: "I don't want to be able to target living units with it."  209 is a corpse spell (TRecallSpirit clone, single-hex
highlight - keep it).  Like Second Wind (patch_tc_secondwind_target_v1.py) the tactical screen never asks AoWEPACK:
the hover cursor (UpdateMoveCursor 0x41F6E8) only tests the side mask, and the click goes through CalculateRangedPath
(empty path list = nothing cast, no mana spent).  So, chained in FRONT of the Second Wind target caves at the same two
sites:
  RP  0x41DCF0  CalculateRangedPath (call -> prev):  selected HS [ebp-0xC] doing action 0x34 with spell [+0x38] == 209
      and the hovered field ([ebp-5] x / [ebp-6] y) NOT a valid Miracle target -> drop the return, jmp 0x41DFCD (no path,
      the click does nothing); else jmp prev.
  CU  0x41FA1C  UpdateMoveCursor exit (call -> prev):  call prev, then 209 + a cast cursor (0x50..0x53 unit / 0x55..0x58
      ground / 0x69..0x6B kind-2) over a field that is NOT a valid target ([ebp-8] = hovered field) -> cursor := 0x59.
Valid target field = no living unit HS on it (FindOwnedChild 0x220104 == nil, so never a living unit - the caster
included) AND a TCCorpseHS (ClassID 0x220108) whose combat unit (+0xC; nil = machine wreck) is on the CASTER'S side
([cu+0x45] == [[casterHS+0x1C]+0x45]) and still carries its TUnit ([cu+0x4C]).  FindOwnedChild returns the first corpse
on the field - the corpse the raise (patch_tc_miracle_v1.py T2) meets first is the same one.
Zone AoWTCPCK 0x440E00..0x441000 (zero, reloc-free; between patch_tc_miracle_v1 0x440C00-0x440D33 and Sanctify's
0x441400); first 8 bytes = the chained sites' previous targets for --revert.  PIC call/pop delta for G_GAME.
Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_mirtarget.
APPLY AFTER patch_tc_secondwind_target_v1.py; revert this before it (with this applied, its dry run reports a
mixed-state ABORT - expected, same as airdeath under Second Wind).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs, call_target

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x440E00, 0x441000
SPELL = 209
G_GAME, GETMAPLEVEL, GETFIELD, NOPATH = 0x46C064, 0x401E64, 0x401E54, 0x41DFCD
HOOKS = [("RP", 0x41DCF0, "rp"), ("CU", 0x41FA1C, "cu")]
TABLE = 8


def caves(prev):
    return [
        # valid(eax = field, edx = caster HS) -> al = 1 if the field is a valid Miracle target.  pushal-safe (clobbers all).
        ("valid", """
            test eax, eax
            jz v_no
            test edx, edx
            jz v_no
            mov edx, [edx+0x1c]
            test edx, edx
            jz v_no
            push esi
            push edi
            mov esi, eax
            movzx edi, byte ptr [edx+0x45]
            mov edx, 0x220104
            mov ecx, [esi]
            call dword ptr [ecx+0x80]
            test eax, eax
            jnz v_no2
            mov eax, esi
            mov edx, 0x220108
            mov ecx, [esi]
            call dword ptr [ecx+0x80]
            test eax, eax
            jz v_no2
            mov eax, [eax+0xc]
            test eax, eax
            jz v_no2
            cmp dword ptr [eax+0x4c], 0
            je v_no2
            movzx eax, byte ptr [eax+0x45]
            cmp eax, edi
            jne v_no2
            pop edi
            pop esi
            mov al, 1
            ret
        v_no2:
            pop edi
            pop esi
        v_no:
            xor eax, eax
            ret
        """),
        # rp: CalculateRangedPath ([ebp-0xC] selected unit HS: +0x34 action, +0x38 spell; [ebp-5]/[ebp-6] hovered x/y)
        ("rp", """
            mov eax, [ebp-0xc]
            test eax, eax
            jz rp_prev
            cmp dword ptr [eax+0x34], 0x34
            jne rp_prev
            cmp dword ptr [eax+0x38], %(spell)d
            jne rp_prev
            pushal
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebx+%(game)#x]
            mov eax, [eax+0x10]
            xor edx, edx
            call %(getmaplevel)#x
            test eax, eax
            jz rp_ok
            movsx edx, byte ptr [ebp-5]
            movsx ecx, byte ptr [ebp-6]
            call %(getfield)#x
            test eax, eax
            jz rp_ok
            mov edx, [ebp-0xc]
            call valid
            test al, al
            jnz rp_ok
            popal
            add esp, 4
            jmp %(nopath)#x
        rp_ok:
            popal
        rp_prev:
            jmp %(prev_rp)#x
        """),
        # cu: UpdateMoveCursor exit ([ebp-4] control: +0x2C cursor word; [ebp-8] hovered field; [ebp-0x10] selected HS)
        ("cu", """
            call %(prev_cu)#x
            pushal
            mov eax, [ebp-0x10]
            test eax, eax
            jz cu_out
            cmp dword ptr [eax+0x34], 0x34
            jne cu_out
            cmp dword ptr [eax+0x38], %(spell)d
            jne cu_out
            mov edx, [ebp-4]
            movzx edx, word ptr [edx+0x2c]
            cmp edx, 0x50
            jb cu_out
            cmp edx, 0x58
            jbe cu_chk
            cmp edx, 0x69
            jb cu_out
            cmp edx, 0x6b
            ja cu_out
        cu_chk:
            cmp edx, 0x54
            je cu_out
            mov eax, [ebp-8]
            mov edx, [ebp-0x10]
            call valid
            test al, al
            jnz cu_out
            mov eax, [ebp-4]
            mov word ptr [eax+0x2c], 0x59
        cu_out:
            popal
            ret
        """),
    ], dict(spell=SPELL, game=G_GAME, getmaplevel=GETMAPLEVEL, getfield=GETFIELD, nopath=NOPATH,
            prev_rp=prev.get("RP", 0), prev_cu=prev.get("CU", 0))


def build(prev):
    srcs, fmt = caves(prev); where = {n: 0 for n, _ in srcs}
    for _ in range(3):
        out = bytearray(); new = {}
        for name, src in srcs:
            va = ZONE + TABLE + len(out); new[name] = va
            s = src % fmt
            for nm in where: s = s.replace("call %s\n" % nm, "call %#x\n" % where[nm])
            out += asm_pic(s, va); out += b"\x00" * ((-len(out)) % 16)
        if new == where: break
        where = new
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
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
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
    if ours and len(ours) != len(HOOKS): print("ABORT (mixed state: something chained in front of one of our sites)"); return 1
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
        bak = bak_path(a.dll, ".bak_mirtarget")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
