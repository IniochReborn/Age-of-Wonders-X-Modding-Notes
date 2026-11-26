#!/usr/bin/env python3
r"""
SECOND WIND (310) TACTICAL TARGETING (2026-10-16).  AoWTCPCK.dll only.

User: "didn't work when cast twice on the same unit but it still let me do it - I should not have been able to target
it twice."  patch_secondwind_v1.py v3 makes TRemedy.ValidTarget refuse a unit holding 0xBF 'Second Wind', but the
tactical screen never asks the AoWEPACK ValidTarget: the hover cursor (UpdateMoveCursor 0x41F6E8) only tests the TC
spell's side mask ([ebp-0x15] bits 1/2, + TC VMT+0x11C for kind-2 spells) and the click goes through
CalculateRangedPath (an empty path list = the click casts nothing).  So the re-cast was issued, spent, and then
refused inside ExecuteSpell.  Same two sites patch_airdeath_fix_v1.py uses for 345 Suffocate, chained in FRONT:
  RP  0x41DCF0  CalculateRangedPath (call -> airdeath rp cave 0x43F670):  selected HS [ebp-0xC] doing action 0x34
      with spell [+0x38] == 310, and the unit on the hovered field ([ebp-5] x / [ebp-6] y, FindOwnedChild 0x220104)
      holds 0xBF (TUnit VMT+0x148) -> drop the return, jmp 0x41DFCD (no path = click does nothing); else jmp prev.
  CU  0x41FA1C  UpdateMoveCursor exit (call -> airdeath cu cave 0x43F6E0):  call prev (replays the 7 vanilla bytes
      + Suffocate's test), then 310 + hovered HS [ebp-0x14] holds 0xBF and the cursor [ctl+0x2C] is a VALID-cast
      cursor (0x50..0x53 side-mask / 0x69..0x6B kind-2) -> cursor := 0x59 (invalid).  Self-cast included (the
      caster's own 0xBF also refuses, as ValidTarget does).
0xBF is a combat-only TDurationAbility (CombatDone removes it) -> the refusal lasts exactly one battle.
Zone AoWTCPCK 0x440800..0x440900 (zero, reloc-free); first 8 bytes = the chained sites' previous targets (data) for
--revert.  PIC call/pop delta for the G_GAME read (the DLL rebases).  Dry-run default; --apply / --revert / --dis /
--dll <scratch copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_swtarget.  APPLY AFTER patch_airdeath_fix_v1.py;
revert this before it (with this applied, airdeath's dry run reports a mixed-state ABORT - expected).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs, call_target

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x440800, 0x440900
SPELL, AB_SW = 310, 0xBF
G_GAME, GETMAPLEVEL, GETFIELD, NOPATH = 0x46C064, 0x401E64, 0x401E54, 0x41DFCD
HOOKS = [("RP", 0x41DCF0, "rp"), ("CU", 0x41FA1C, "cu")]
TABLE = 8


def caves(prev):
    return [
        # holds(eax = unit HS) -> al = 1 if its TUnit holds 0xBF.  Saves ecx/edx.
        ("holds", """
            test eax, eax
            jz h_no
            mov eax, [eax+0x1c]
            test eax, eax
            jz h_no
            mov eax, [eax+0x4c]
            test eax, eax
            jz h_no
            push ecx
            push edx
            mov edx, %(ab)d
            mov ecx, [eax]
            call dword ptr [ecx+0x148]
            pop edx
            pop ecx
            ret
        h_no:
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
            mov edx, 0x220104
            mov ecx, [eax]
            call dword ptr [ecx+0x80]
            call holds
            test al, al
            jz rp_ok
            popal
            add esp, 4
            jmp %(nopath)#x
        rp_ok:
            popal
        rp_prev:
            jmp %(prev_rp)#x
        """),
        # cu: UpdateMoveCursor exit ([ebp-4] control: +0x2C cursor word; [ebp-0x10] selected HS, [ebp-0x14] hovered HS)
        ("cu", """
            call %(prev_cu)#x
            push eax
            push edx
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
            cmp edx, 0x53
            jbe cu_chk
            cmp edx, 0x69
            jb cu_out
            cmp edx, 0x6b
            ja cu_out
        cu_chk:
            mov eax, [ebp-0x14]
            call holds
            test al, al
            jz cu_out
            mov eax, [ebp-4]
            mov word ptr [eax+0x2c], 0x59
        cu_out:
            pop edx
            pop eax
            ret
        """),
    ], dict(ab=AB_SW, spell=SPELL, game=G_GAME, getmaplevel=GETMAPLEVEL, getfield=GETFIELD, nopath=NOPATH,
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
        bak = bak_path(a.dll, ".bak_swtarget")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
