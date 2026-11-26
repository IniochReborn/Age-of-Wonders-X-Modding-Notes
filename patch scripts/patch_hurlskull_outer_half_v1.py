#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Hurl Skull (ability 0xCC) - the 6 OUTER hexes of the AOE deal half damage (2026-11-16).

User: "hurl skull is too powerful. keep its damage and stats for the center hex of the AOE, outside hexes -50% damage".

How the AOE works (patch_bxl_ranged_abilities_v2..v7 + patch_hurlskull_aoe_home_v1): the AOE cave 0x452110 sends
field msg 0x31020 to Fire Ball's 7 hexes (CenterHNtoHX, HN 0 = the impact hex, 1..6 = the ring).  The msg buffer is
the cave's 0x50-byte stack frame and its loop counter lives INSIDE it at +0x48, so every handler sees
[msg+0x48] = HN of the hex being served (SendMapFieldMsg passes the same pointer on).  The unit handler cave HM
(0x4521F0) builds the hit with TRangedAttackAbility.CreateRangedAttackCA, whose Setup (AoWEPACK 0x55729C20) stores
the already ROLLED damage in byte [ca+0x10]; Execute only applies it.

Patch: HM's final `jmp 0x42101C` (0x452268, Fire Ball's tail) -> cave 0x43E800:
    mov edx, [ebp-8]            ; msg
    cmp dword ptr [edx+0x48], 0 ; HN 0 = centre hex: untouched
    je  done
    mov dl, [eax+0x10]          ; rolled damage
    shr dl, 1
    adc dl, 0                   ; half, rounded up (a hit never becomes 0; a miss stays 0)
    mov [eax+0x10], dl
done:
    jmp 0x42101C
ATK / to-hit roll, damage types and the RNG stream are unchanged (same rolls, result halved) -> MP-deterministic as
long as every machine has the patch.  DMG 8 at the centre -> 1..4 on the ring.
Self-relative jumps only, no relocs.  Layered on v7 + aoe_home (revert this FIRST).
Backup <game>\backup\AoWTCPCK.dll.bak_hskhalf.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_hskhalf"
V2F = 0x400C00
CTX_VA, CTX = 0x4521F0, bytes.fromhex("8b45f8813820100300")      # HM: mov eax,[ebp-8] / cmp [eax],0x31020
AOE_VA, AOE = 0x45218F, bytes.fromhex("ff442448837c244807")      # AOE loop: inc [esp+0x48] / cmp [esp+0x48],7
SEND_VA, SEND = 0x452188, bytes.fromhex("89e2")                  # mov edx,esp (msg = frame base)
JMP_VA, TAIL = 0x452268, 0x42101C
CAVE_VA, CAVE_ROOM = 0x43E800, 0x100


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


JMP_ORIG = rel(0xE9, JMP_VA, TAIL)
JMP_NEW = rel(0xE9, JMP_VA, CAVE_VA)
CAVE_NEW = (bytes.fromhex("8b55f8" "837a4800" "740b" "8a5010" "d0ea" "80d200" "885010")
            + rel(0xE9, CAVE_VA + 20, TAIL))
CAVE_ORIG = bytes(len(CAVE_NEW))


def reloc_hits(path, ranges):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type and any(lo - 3 <= ib + e.rva < hi for lo, hi in ranges): out.append(hex(ib + e.rva))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    if g(CTX_VA, len(CTX)) != CTX or g(AOE_VA, len(AOE)) != AOE or g(SEND_VA, len(SEND)) != SEND:
        print("ABORT: Hurl Skull AOE / HM caves not found (patch_bxl_ranged_abilities_v7 expected)"); return 1
    jmp, cave = g(JMP_VA, 5), g(CAVE_VA, len(CAVE_NEW))
    state = ("vanilla" if (jmp, cave) == (JMP_ORIG, CAVE_ORIG) else
             "ours" if (jmp, cave) == (JMP_NEW, CAVE_NEW) else "OTHER")
    print("HM jmp %#x: %s | cave %#x: %s -> %s" % (JMP_VA, jmp.hex(), CAVE_VA, cave.hex(), state))
    if state == "OTHER": print("ABORT"); return 1
    if state == "vanilla" and any(g(CAVE_VA, CAVE_ROOM)): print("ABORT: cave zone not empty"); return 1
    bad = reloc_hits(a.dll, [(JMP_VA, JMP_VA + 5), (CAVE_VA, CAVE_VA + len(CAVE_NEW))])
    if bad: print("ABORT: relocs in range", bad); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    jw, cw = (JMP_ORIG, CAVE_ORIG) if a.revert else (JMP_NEW, CAVE_NEW)
    d[JMP_VA - V2F:JMP_VA - V2F + 5] = jw
    d[CAVE_VA - V2F:CAVE_VA - V2F + len(cw)] = cw
    if not a.apply and not a.revert:
        print("%d byte change. Dry run OK - rerun with --apply (or --revert)." % (5 + len(cw))); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:                    # in-place (house rule: "wb" is refused on the live DLLs)
        for va, b in ((JMP_VA, jw), (CAVE_VA, cw)): f.seek(va - V2F); f.write(b)
    assert open(a.dll, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
