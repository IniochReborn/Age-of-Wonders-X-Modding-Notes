#!/usr/bin/env python3
r"""
CALL OF THE DEAD (211) - one SPIRAL animation per corpse instead of the kind-0x1F sparkles (2026-10-16).  AoWTCPCK only.

User: "it looks like one or two [skulls] to start, which should instead be FIVE skulls that fade in spinning in a large
shrinking circle" + the skulls showed WHITE (kind-0x1F particles ignore the image's ALPHA drawMode 258).
RE: TCCorpseHS.MapFieldMsgProc (0x423BC4), msg 0x31008 (corpse FX; spell = [[ebp-8]+0xC]): HXtoHP(corpse hex) ->
[ebp-0x20] px / [ebp-0x24] py @0x423C90, then @0x423C95 `jmp` into the Repent/Harvest loop-start cave 0x43CBB0 (owned by
patch_tc_repent_harvest_v1), which falls into the 3 x 18 kind-0x1F sparkle loop (0x423C9C..0x423E3E, Random() jitter;
the 211 counts there = patch_tc_callofdead_fx_v1) and leaves through 0x423E44 -> 0x42412D (the proc's exit).
Fix: the 0x423C95 jmp is chained (previous target decoded at apply, kept in the zone header for --revert):
  211 -> spawn ONE kind-0x26 effect (the oil-gush / Ashes driver recipe: AddEffect 0x41C6EC(map [0x46C064], dl 0x26),
         TXYZ (class [0x46EB24]) created + added to [fx+0x1C], xyz = hex centre px+16 / py+16, [fx+0x14] = 0x34,
         [fx+0x18] = 211, [fx+0x24] marker 0, [fx+0x2C] 0) and leave through 0x42412D - no sparkle loop, no Random().
         Kind 0x26 with marker 0 draws spell gfx SLOT 1 (the vanilla `mov edx,1` @0x42A5E9 / `mov eax,1` @0x430059 that
         the oil-gush / Ashes slot caves fall back to for any other id) through the normal sequence path (drawMode
         honoured) and expires when its sequence has played once (30 frames x f20 3 = 90 ticks).
  else -> previous target (the Repent/Harvest cave).
Timing: TCAbRangedTE phase [fx+0x10] 0 sends 0x31008 (spiral starts), 0x63 = 99 sends 0x31009 (raise; patch_tc_callofdead_v1
BC sweep) -> the 90-tick spiral ends 9 ticks before the Draugr rise.  Keep the slot-1 sequence <= ~99 ticks (or raise
the 0x63 compare in patch_tc_callofdead_v1's BC cave).
Zone 0x442500..0x442600 (zero, reloc-free; PIC via call/pop).  Backup <game>\backup\AoWTCPCK.dll.bak_cotdspiral.
Dry-run default; --apply / --revert / --dis / --dll <scratch copy>.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x442500, 0x442600
SPELL, KIND = 211, 0x26
SITE, SITE_LEN = 0x423C95, 5                                   # jmp rel32 (to the Repent/Harvest cave 0x43CBB0)
EXIT = 0x42412D
VANILLA_PREV = 0x43CBB0                                        # what the site jumps to today (for the 'vanilla' label)
MAP_G, TXYZ_IAT = 0x46C064, 0x46EB24
ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ = 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4


def build(prev):
    src = """
        mov eax, [ebp-8]
        cmp dword ptr [eax+0xc], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebx
        push esi
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzadd)#x
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [ebp-0x20]
        add edx, 0x10
        mov [eax+4], edx
        mov edx, [ebp-0x24]
        add edx, 0x10
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(spell)d
        mov dword ptr [esi+0x24], 0
        mov dword ptr [esi+0x2c], 0
        pop esi
        pop ebx
        jmp %(exit)#x
    """ % dict(spell=SPELL, kind=KIND, prev=prev, map=MAP_G, txyz=TXYZ_IAT, add=ADDEFFECT, create=TOBJCREATE,
               xyzadd=XYZADD, getxyz=GETXYZ, exit=EXIT)
    out = bytearray(struct.pack("<I", prev)); out += b"\x00" * 12
    cave = ZONE + len(out); out += asm_pic(src, cave)
    assert ZONE + len(out) <= ZONE_END
    return bytes(out), cave


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    cur = bytes(d[SITE - V2F:SITE - V2F + SITE_LEN]); assert cur[0] == 0xE9, "site is not a jmp rel32: %s" % cur.hex()
    tgt = SITE + 5 + struct.unpack_from("<i", cur, 1)[0]
    ours = ZONE <= tgt < ZONE_END
    prev = struct.unpack_from("<I", zl, 0)[0] if ours else tgt
    zone, cave = build(prev)
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    state = "ours" if ours and tgt == cave else "chain-ready" if not ours else "OTHER(zone, stale cave)"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + SITE_LEN]
    print("AoWTCPCK spiral: site %#x -> %#x (%s) | prev %#x%s | zone %s (%d B, cave %#x) | relocs %s" % (
        SITE, tgt, state, prev, " (vanilla Repent/Harvest cave)" if prev == VANILLA_PREV else "", zstate, len(zone), cave, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[16:], cave):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (relocs)"); return 1
    if not ours and zstate != "zero": print("ABORT (zone not free)"); return 1
    if ours and zl[:4] == bytes(4): print("ABORT (zone header lost)"); return 1
    n = bytearray(d)
    if a.revert:
        if not ours: print("already reverted"); return 0
        n[SITE - V2F:SITE - V2F + 5] = b"\xe9" + struct.pack("<i", prev - (SITE + 5))
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        n[SITE - V2F:SITE - V2F + 5] = b"\xe9" + struct.pack("<i", cave - (SITE + 5))
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_cotdspiral")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
