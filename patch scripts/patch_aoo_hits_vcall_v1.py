#!/usr/bin/env python3
r"""
Fix the AoO-awareness cave's out-of-bounds HP reads (AoWTCPCK.dll, 2026-10-04).

Symptom: "Error - TCAI / Error during Add Group Bonuses" repeating every AI cycle (soft-lock).  VEH capture
(veh_attach_log.txt 17:26, 332 identical records): AV read at AoWTCPCK+0x38754 = VA 0x438754, data = unit+0x84.

Cause: build_ai_aoo_awareness.py's frailty term reads the self unit's max/current hit points as FIELDS
    0x438754  mov ecx, [eax+0x84]      ; "maxhits"
    0x43875A  mov eax, [eax+0x88]      ; "hits"
but TCombatUnit (live class TTacticalCombatUnit, instance size 0x68) has no such fields: +0x84 / +0x88 are the
VMT slots GetHits (max) / GetHitPoints (cur), byte results.  The reads land in whatever follows the object on
the heap - garbage normally (so f100 was random all along), an access violation when the object sits at the
end of a mapped page.  Same bug class the healing and melee AI scripts fixed on 2026-09-17.

Patch: the 12 bytes become `call SUB` + 7 nop; SUB (0x43C200, CODE zero tail right after the relocated
SpellTypes table) does the two virtual calls and returns with ecx = max, eax = cur, exactly what the
following `test ecx,ecx / imul eax,eax,100 / idiv ecx` expects.  eax/ecx/edx are the only registers the
cave has live there (eax = unit object); ebx/esi/edi survive the Delphi calls.  Rel32 only - rebase-proof.

Backup <game>\backup\AoWTCPCK.dll.bak_aoo_vcall (first apply).  --revert is surgical (restores the 12 bytes,
zeroes SUB) so it stays independent of patches layered on later.  Dry-run default; --apply; --revert; --dll.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_aoo_vcall"
CODE_V2F = 0x400C00

SITE = 0x438754
SITE_ORIG = bytes.fromhex("8b8884000000" "8b8088000000")      # mov ecx,[eax+0x84] ; mov eax,[eax+0x88]
SUB = 0x43C200

SUB_CODE = bytes.fromhex(
    "50"            # push eax              ; unit object
    "8b10"          # mov edx, [eax]
    "ff9284000000"  # call [edx+0x84]       ; GetHits (max) -> al
    "0fbec8"        # movsx ecx, al
    "58"            # pop eax
    "51"            # push ecx
    "8b10"          # mov edx, [eax]
    "ff9288000000"  # call [edx+0x88]       ; GetHitPoints (cur) -> al
    "0fbec0"        # movsx eax, al
    "59"            # pop ecx
    "c3")           # ret


def hook_bytes():
    rel = SUB - (SITE + 5)
    return b"\xe8" + struct.pack("<i", rel) + b"\x90" * (len(SITE_ORIG) - 5)


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs):
                return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8:
            break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3:
                out.add(0x400000 + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def show(d, lo, n, mark=None):
    try:
        import capstone
    except ImportError:
        return
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for i in md.disasm(d[lo - CODE_V2F:lo - CODE_V2F + n], lo):
        print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    d = open(dll, "rb").read()
    site = d[SITE - CODE_V2F:SITE - CODE_V2F + len(SITE_ORIG)]
    sub = d[SUB - CODE_V2F:SUB - CODE_V2F + len(SUB_CODE)]
    relocs = reloc_set(d)
    bad = [r for r in relocs if SITE <= r < SITE + len(SITE_ORIG) or SUB <= r < SUB + len(SUB_CODE)]
    if bad:
        print("ABORT: reloc entries in patched ranges:", ["0x%X" % r for r in bad]); return 1

    if a.revert:
        if site != hook_bytes() or sub != SUB_CODE:
            print("not applied (site %s, sub %s) - nothing to revert" % (site.hex(), sub.hex())); return 1
        out = bytearray(d)
        out[SITE - CODE_V2F:SITE - CODE_V2F + len(SITE_ORIG)] = SITE_ORIG
        out[SUB - CODE_V2F:SUB - CODE_V2F + len(SUB_CODE)] = bytes(len(SUB_CODE))
        write_inplace(dll, bytes(out)); print("reverted (site restored, SUB zeroed)"); return 0

    if site == hook_bytes() and sub == SUB_CODE:
        print("already applied"); show(d, SITE - 5, 24); show(d, SUB, len(SUB_CODE)); return 0
    if site != SITE_ORIG:
        print("ABORT: site bytes %s unexpected (AoO cave not at the known layout?)" % site.hex()); return 1
    if any(sub):
        print("ABORT: SUB region not zero:", sub.hex()); return 1
    out = bytearray(d)
    out[SITE - CODE_V2F:SITE - CODE_V2F + len(SITE_ORIG)] = hook_bytes()
    out[SUB - CODE_V2F:SUB - CODE_V2F + len(SUB_CODE)] = SUB_CODE
    print("site 0x%X: %s -> %s ; SUB @0x%X (%d B)" % (SITE, site.hex(), hook_bytes().hex(), SUB, len(SUB_CODE)))
    show(bytes(out), SITE - 5, 24); show(bytes(out), SUB, len(SUB_CODE))
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(dll, BAK_SUFFIX)
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print("backup ->", bak)
    write_inplace(dll, bytes(out))
    assert open(dll, "rb").read() == bytes(out)
    print("Written and verified:", dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
