#!/usr/bin/env python3
r"""
SHOCKWAVE PUSH v2 (2026-10-18): v1 + a SUBTLER hop puff for Shockwave pushes only.  AoWTCPCK.dll only.

User on v1: "Shockwave good but the new white particle effect that plays when a unit is moved is a bit much, make it
more subtle."
The puff = WoF's per-tick swirl loop in the kind-0x2F NewFrame (0x42BFA5..0x42C0E8, reached from Gust's SPN hop path
0x42BF98): every tick it spawns one kind-0x1F swirl particle (5 Random calls each, spell id copied from the carrier ->
212's slot 1 = Shockwave's PARTICLE.ILB orbs) for EVERY path index in [tick-20, tick] that is < the path count.  A hop
carrier has ~25 points (p0 + 14 shake + ~10 arc) and starts at tick 20 -> ~21 particles per tick, hundreds per push.
v2:
  * MARK: Shockwave's hop carriers now get [fx+0x28] = -6 instead of -5 (the cue-1 sound tick; NewFrame only compares
    it with the tick, which never reaches -5 or -6 -> still silent).  Gust / Crashing Wave carriers keep -5 (their own
    zone, untouched) -> they are not affected.
  * SKP 0x42BFD4 (11 B `mov eax,[ebp-8] / mov eax,[eax+0x1c] / call 0x402DFC` = the per-index `idx < count` test,
    reloc-free) -> cave SKP at 0x450C00 (own 0x40-byte zone right after v1's zone): for a marked carrier, the index is
    SKIPPED (jmp 0x42C0DC = next index) unless ((idx + tick) & MASK) == 0 -> 1 particle in 4 (MASK 3), same spread /
    swirl / art / lifetime, just a quarter as dense.  Unmarked carriers run the vanilla test unchanged.
    (Fewer Random calls - the same on every client: the effect loop runs identically on every machine.)
State handling: vanilla -> v2; v1 -> v2 IN PLACE (zone rewritten, SKP added); --revert -> vanilla (site + zone + SKP,
byte-identical to the pre-v1 DLL).  Revert with THIS script: v1's --revert would leave SKP + its cave in place
(harmless: no carrier carries -6 any more -> pure pass-through), and this script's --revert then removes them.
LIFO: revert before patch_tc_gust_v1.py (needs Gust's SPN / LND hop hooks, checked at --apply).
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_swpush (v1's, kept).
"""
import argparse, os, re, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path
from patch_airdeath_fix_v1 import asm_pic, relocs
import patch_tc_shockwave_push_v1 as V1

DLL, V2F, BASE = V1.DLL, V1.V2F, V1.BASE
ZONE, ZONE_END, SITE, SITE_ORIG = V1.ZONE, V1.ZONE_END, V1.SITE, V1.SITE_ORIG
SKP, SKP_ORIG = 0x42BFD4, bytes.fromhex("8b45f88b401ce81d6efdff")      # mov eax,[ebp-8] / mov eax,[eax+0x1c] / call 0x402DFC
SKP_NEXT, SKP_BACK = 0x42C0DC, 0x42BFDF                                # next index / after the count call
SZONE, SZONE_END = 0x450C00, 0x450C40
MARK = -6
MASK = 3                                                               # keep 1 particle in (MASK+1)
OLD_MARK = "mov dword ptr [edi+0x28], -5"


def src_v2():
    s = V1.src()
    assert s.count(OLD_MARK) == 1, "v1 source changed: the cue-1 init is not unique"
    return s.replace(OLD_MARK, "mov dword ptr [edi+0x28], %d" % MARK)


def build_zone():
    blob = asm_pic(re.sub(r"/\*.*?\*/", "", src_v2(), flags=re.S), ZONE)
    assert ZONE + len(blob) <= ZONE_END, hex(ZONE + len(blob))
    return blob


def build_skp():
    s = """
    skp:
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x28], %(mark)d
        jne skp_van
        mov edx, [ebp-0x10]
        add edx, [eax+0x10]
        test dl, %(mask)d
        jz skp_van
        jmp %(nxt)#x
    skp_van:
        mov eax, [eax+0x1c]
        call 0x402DFC
        jmp %(back)#x
    """ % dict(mark=MARK, mask=MASK, nxt=SKP_NEXT, back=SKP_BACK)
    blob = asm_pic(s, SZONE)
    assert SZONE + len(blob) <= SZONE_END
    return blob


def jmp_to(src, dst, n):
    return b"\xE9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)


def f(va): return va - V2F


def zstate(z, blob):
    if z == bytes(len(z)): return "zero"
    if z[:len(blob)] == blob and z[len(blob):] == bytes(len(z) - len(blob)): return "match"
    return "used"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    path = a.dll; d = bytearray(open(path, "rb").read())
    R = relocs(d, BASE)
    bad = [hex(r) for r in R if (ZONE - 3 <= r < ZONE_END) or (SZONE - 3 <= r < SZONE_END) or (SITE - 3 <= r < SITE + 5)
           or (SKP - 3 <= r < SKP + len(SKP_ORIG))]
    zb, sb, v1b = build_zone(), build_skp(), V1.build()
    zone = bytes(d[f(ZONE):f(ZONE_END)]); szone = bytes(d[f(SZONE):f(SZONE_END)])
    st = V1.site_state(d)
    skp_now = bytes(d[f(SKP):f(SKP) + len(SKP_ORIG)]); skp_ours = jmp_to(SKP, SZONE, len(SKP_ORIG))
    sk = "vanilla" if skp_now == SKP_ORIG else ("ours" if skp_now == skp_ours else "OTHER")
    zs = "v2" if zstate(zone, zb) == "match" else ("v1" if zstate(zone, v1b) == "match" else zstate(zone, zb))
    ss = zstate(szone, sb)
    print("AoWTCPCK shockwave site %#x %s | zone %#x %s | SKP %#x %s | skp zone %#x %s | gust hop hooks %s | relocs %s" % (
        SITE, st, ZONE, zs, SKP, sk, SZONE, ss, "ok" if V1.gust_ok(d) else "MISSING", bad or "none"))
    if bad: print("ABORT: relocations in the zones / under the sites"); return 1
    if st == "OTHER" or sk == "OTHER": print("ABORT: a site holds unknown code"); return 1
    if ss == "used": print("ABORT: the SKP zone holds foreign bytes"); return 1
    if a.revert:
        if st == "vanilla" and sk == "vanilla" and zs == "zero" and ss == "zero": print("already reverted"); return 0
        if st == "vanilla" and zs != "zero": print("ABORT: site vanilla but the zone is not zero"); return 1
        if st == "ours" and zs not in ("v1", "v2"): print("ABORT: unknown shockwave build in the zone"); return 1
        d[f(SITE):f(SITE) + 5] = SITE_ORIG; d[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        d[f(SKP):f(SKP) + len(SKP_ORIG)] = SKP_ORIG; d[f(SZONE):f(SZONE_END)] = bytes(SZONE_END - SZONE)
        open(path, "r+b").write(d); print("reverted", path); return 0
    if st == "ours" and zs == "v2" and sk == "ours" and ss == "match":
        if a.dis: dis(d)
        print("already applied"); return 0
    if st == "vanilla" and zs != "zero": print("ABORT: zone not free"); return 1
    if st == "ours" and zs not in ("v1", "v2"): print("ABORT: the zone holds an unknown shockwave build - revert it first"); return 1
    if not V1.gust_ok(d): print("ABORT: patch_tc_gust_v1.py (v3+ SPN / LND hop hooks) is not applied"); return 1
    print("fresh apply" if st == "vanilla" else "upgrading %s -> v2 in place" % zs)
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(path) == os.path.abspath(DLL):
        bak = bak_path(DLL, ".bak_swpush")
        if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    d[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE); d[f(ZONE):f(ZONE) + len(zb)] = zb
    d[f(SZONE):f(SZONE_END)] = bytes(SZONE_END - SZONE); d[f(SZONE):f(SZONE) + len(sb)] = sb
    d[f(SITE):f(SITE) + 5] = b"\xE9" + struct.pack("<i", ZONE - (SITE + 5))
    d[f(SKP):f(SKP) + len(SKP_ORIG)] = skp_ours
    open(path, "r+b").write(d); print("written", path)
    if a.dis: dis(d)
    return 0


def dis(d):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for i in md.disasm(bytes(d[f(SZONE):f(SZONE_END)]), SZONE):
        if i.bytes == b"\x00\x00": break
        print("%08X  %-8s %s" % (i.address, i.mnemonic, i.op_str))


if __name__ == "__main__":
    sys.exit(main())
