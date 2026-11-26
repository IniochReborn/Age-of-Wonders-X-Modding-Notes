#!/usr/bin/env python3
r"""
Tame Animal v3 (2026-10-19): the actual reason Tame Animal (0xC9) never converted - a LAYER on top of
patch_tame_animal_v2.py (v2 must be applied; v2's files/zones are not touched).

Root cause.  The tactical touch TE in AoWTCPCK.dll picks the touch effect with a SWITCH ON THE ABILITY ID
([te+0x3C]) at 0x40A5F1:
      0x28 Web -> 0x40A654        0x1B -> 0x40A6D3          0x1C Dominate / 0x1D Seduce / 0x94 Charm -> 0x40A752
      0x21 -> 0x40A855            0x24 -> 0x40A7D4          0x2F -> 0x40A8D4   0x3C -> 0x40A94B   0x6A/0x6B -> 0x40A9D1
      anything else -> 0x40AAED (does nothing)
0x40A752 is the command-ability case: GetAbility(id) -> ability VMT +0x128 (TCommandAbility 0x55770358: the
roll +0x110, TCommandCA) -> [te+0x54] / [te+0x61] = success -> the CA queue (Execute -> Apply grants [+0x28]).
Tame Animal (0xC9) fell into the default, so no roll, no CA, nothing - for the player AND the tactical AI (its
touch moves run through the same TE).  v1/v2 only patched the AoWEPACK side and the TCAI scan.  (The live probe
saw nothing for Tame for the same reason; its Dominate 'error' was the probe forwarding its own hardware
single-step - see diag_tame_probe.py v2.)

Fix.  Hook SW @0x40A5F4 (`mov eax,[eax+0x3c] / cmp eax,0x28`, 6 B) -> cave: id 0xC9 -> 0x40A752 (Dominate's
case); otherwise the original `cmp eax,0x28` and back to 0x40A5FA (the `jg`, flags intact).

Zone AoWTCPCK 0x450E00..0x450E40 (verified zero + reloc-free at apply; kept OUTSIDE v2's 0x450D00..0x450E00 because
v2's dry run treats any extra bytes there as foreign and its --revert zeroes that range).  Header +0 'TAM3',
+4 SW original (6 B); cave @+0x10.  PIC: rel32 only (TCPCK is rebased at load).  MP: deterministic.
States: v2 present + vanilla site -> apply; ours -> already applied.  --revert restores the site + zeroes the
zone (back to plain v2).  LIFO: revert this BEFORE patch_tame_animal_v2.py.
Dry-run default; --apply / --revert / --dis; --tcdll / --dll <scratch copies>.  Backup (first apply):
<game>\backup\AoWTCPCK.dll.bak_tame3.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
DEFAULT_TC = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_tame3"
TCBASE, CODE_V2F = 0x400000, 0x55700C00
V2_ZONE, V2_MAGIC = 0x55818100, b"TAM2"
ZONE, ZONE_END, MAGIC = 0x450E00, 0x450E40, b"TAM3"
SW_SITE, SW_BYTES, SW_BACK = 0x40A5F4, bytes.fromhex("8b403c83f828"), 0x40A5FA
CMD_CASE, AB = 0x40A752, 0xC9
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    return [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(n)], pe


def va2off(d, va, base):
    for vs, sva, rs, ro in sections(d)[0]:
        if sva <= va - base < sva + max(vs, rs): return ro + va - base - sva
    raise ValueError(hex(va))


def reloc_set(d, base):
    secs, pe = sections(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def build():
    cave = ZONE + 0x10
    code = bytes(ks.asm("""
        mov eax, dword ptr [eax + 0x3c]
        cmp eax, %d
        je %#x
        cmp eax, 0x28
        jmp %#x
    """ % (AB, CMD_CASE, SW_BACK), cave)[0])
    zone = bytearray(ZONE_END - ZONE)
    zone[0:4] = MAGIC; zone[4:10] = SW_BYTES; zone[0x10:0x10 + len(code)] = code
    hook = b"\xE9" + struct.pack("<i", cave - (SW_SITE + 5)) + b"\x90"
    return bytes(zone), hook, cave


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--tcdll", default=DEFAULT_TC)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read(); t = open(a.tcdll, "rb").read()
    v2 = d[V2_ZONE - CODE_V2F:V2_ZONE - CODE_V2F + 4] == V2_MAGIC
    so, zo = va2off(t, SW_SITE, TCBASE), va2off(t, ZONE, TCBASE)
    cur_site, cur_zone = t[so:so + 6], t[zo:zo + ZONE_END - ZONE]
    zone, hook, cave = build()
    site = "ours" if cur_site == hook else "vanilla" if cur_site == SW_BYTES else "OTHER"
    zst = "zero" if not any(cur_zone) else "ours" if cur_zone == zone else "DIFFERS"
    rl = reloc_set(t, TCBASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or SW_SITE - 3 <= r < SW_SITE + 6]
    print("v2 %s | SW site %#x %s | zone %#x %s | relocs %s | cave %#x" % (
        "applied" if v2 else "MISSING", SW_SITE, site, ZONE, zst, bad or "none", cave))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:].rstrip(b"\0"), cave):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if site == "OTHER" or zst == "DIFFERS" or bad:
        print("ABORT"); return 1
    out = bytearray(t)
    if a.revert:
        if site == "vanilla" and zst == "zero": print("already reverted"); return 0
        assert cur_zone[4:10] == SW_BYTES, "zone header lost the site original"
        out[so:so + 6] = cur_zone[4:10]; out[zo:zo + len(zone)] = bytes(len(zone))
        write_inplace(a.tcdll, bytes(out)); print("reverted (SW site restored, zone zeroed)"); return 0
    if site == "ours" and zst == "ours": print("already applied"); return 0
    if not v2: print("ABORT: patch_tame_animal_v2.py is not applied"); return 1
    if site != "vanilla" or zst != "zero": print("ABORT: half-applied state (site %s, zone %s)" % (site, zst)); return 1
    out[zo:zo + len(zone)] = zone; out[so:so + 6] = hook
    print("%d AoWTCPCK bytes change" % sum(1 for x, y in zip(t, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.tcdll) == os.path.abspath(DEFAULT_TC):
        bak = bak_path(a.tcdll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.tcdll, bak); print("backup ->", bak)
    write_inplace(a.tcdll, bytes(out))
    assert open(a.tcdll, "rb").read() == bytes(out)
    print("Written and verified.  Test: cast Tame Animal on a level-1 creature a few times - it should convert and get 'Tamed'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
