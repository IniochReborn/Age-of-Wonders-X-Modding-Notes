r"""
AI SITE SEARCH - STACK GATE v5 (2026-10-20).  AoWEPACK.dll only.  In-place upgrade of patch_ai_site_converge_v4
(same gate site 0x558147DC, same zone 0x55817000..0x55817400, same tables).  ONE change (user: "leader stacks at >= 3x
... priority increases for moving towards exploration sites ... and ATTEMPTING them"):
   LEADER stack "search now" bar 4.0x -> 3.0x  (v4: 1.5x..4.0x with a friend within 6 hexes waited one turn, so a 3x
   leader stack that the new site boost (patch_ai_site_boost_v1) sends to a site would still stall a turn).
   Everything else is exactly v4: leaderless <1.0x hold, 1.0..2.0x friend-wait 1 turn, >=2.0x search; leader cooldown,
   give-up, 0.75..1.5x 2-turn wait, 1.5..3.0x 1-turn wait, then >= 2.0x search else give up.
Dry-run default; --apply / --revert / --dis / --dll.  apply : v4 -> v5 (also vanilla/v1..v3 -> v5);  revert : ->
original gate bytes, all zones zero (== v4 --revert).  v4's script refuses a v5 zone (DIFFERS).  LIFO: revert this
FIRST (before leader-safety v6).  Backup .bak_aiconverge5.
NOTE: patch_ai_site_leader_safety_v6.py's revert guard checks for b"CNV4" only; with v5 applied revert converge v5
first (the patched copy of the v6 script delivered alongside also recognises b"CNV5").
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_site_converge_v1 as C1
import patch_ai_site_converge_v2 as C2
import patch_ai_site_converge_v3 as C3
import patch_ai_site_converge_v4 as C4

DLL = game_file("AoWEPACK.dll")
OLD = "lead:\n    lea  ecx, [edi*4]\n    cmp  eax, ecx\n    jge  do_mint\n"
NEW = "lead:\n    lea  ecx, [edi+edi*2]\n    cmp  eax, ecx\n    jge  do_mint\n"
MAGIC = b"CNV5"


def build_v4():
    return C4.build()


def build():
    saved = (C4.ASM, C4.MAGIC)
    try:
        assert C4.ASM.count(OLD) == 1
        C4.ASM = C4.ASM.replace(OLD, NEW); C4.MAGIC = MAGIC
        return C4.build()
    finally:
        C4.ASM, C4.MAGIC = saved


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, gate = build(); z4, s4, _g4 = build_v4()
    z1, s1, _ = C1.build(); z2, s2, _ = C2.build(); z3, s3, _ = C3.build()
    V2F, ZONE, ZONE_END, SITE, SITE_LEN, ORIG = C4.V2F, C4.ZONE, C4.ZONE_END, C4.SITE, C4.SITE_LEN, C4.ORIG
    rd = lambda lo, hi: bytes(d[lo - V2F:hi - V2F])
    zl, zl3, zl2, zl1 = rd(ZONE, ZONE_END), rd(C3.ZONE, C3.ZONE_END), rd(C2.ZONE, C2.ZONE_END), rd(C1.ZONE, C1.ZONE_END)
    sb = rd(SITE, SITE + SITE_LEN)
    sstate = ("vanilla" if sb == ORIG else "v5" if sb == site and zl[:len(zone)] == zone else
              "v4" if sb == s4 else "v3" if sb == s3 else "v2" if sb == s2 else "v1" if sb == s1 else "FOREIGN")
    def zst(b, z, nm): return nm if b[:len(z)] == z and not any(b[len(z):]) else None
    z5s = "zero" if not any(zl) else (zst(zl, zone, "v5") or zst(zl, z4, "v4") or "DIFFERS")
    z3s = "zero" if not any(zl3) else (zst(zl3, z3, "v3") or "DIFFERS")
    z2s = "zero" if not any(zl2) else (zst(zl2, z2, "v2") or "DIFFERS")
    z1s = "zero" if not any(zl1) else (zst(zl1, z1, "v1") or "DIFFERS")
    ls = rd(C4.LS_ZONE, C4.LS_ZONE + 4)
    bad = [hex(r) for r in relocs(bytes(d), C4.BASE)
           if any(lo - 3 <= r < hi for lo, hi in ((ZONE, ZONE_END), (C3.ZONE, C3.ZONE_END), (C2.ZONE, C2.ZONE_END),
                                                    (C1.ZONE, C1.ZONE_END), (SITE, SITE + SITE_LEN)))]
    print("AoWEPACK site-search gate %#x %s | zone %#x %s (v5 %d B, gate %#x) | v3 %s v2 %s v1 %s | leader-safety %s | relocs %s"
          % (SITE, sstate, ZONE, z5s, len(zone), gate, z3s, z2s, z1s, ls, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], C4.CODE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if "DIFFERS" in (z5s, z3s, z2s, z1s): print("ABORT (zone not free / foreign)"); return 1
    ok = {("vanilla", "zero", "zero", "zero", "zero"), ("v1", "zero", "zero", "zero", "v1"),
          ("v2", "zero", "zero", "v2", "zero"), ("v3", "zero", "v3", "zero", "zero"),
          ("v4", "v4", "zero", "zero", "zero"), ("v5", "v5", "zero", "zero", "zero")}
    if (sstate, z5s, z3s, z2s, z1s) not in ok: print("ABORT (mixed state)"); return 1
    if not a.revert and ls != C4.LS_MAGIC:
        print("ABORT (ai-site-leader-safety v6 not applied)"); return 1
    print("  state:", sstate + (" - upgrading %s -> v5 in place" % sstate if sstate not in ("vanilla", "v5") and not a.revert else ""))
    n = bytearray(d)
    for lo, hi in ((ZONE, ZONE_END), (C3.ZONE, C3.ZONE_END), (C2.ZONE, C2.ZONE_END), (C1.ZONE, C1.ZONE_END)):
        n[lo - V2F:hi - V2F] = bytes(hi - lo)
    if a.revert:
        n[SITE - V2F:SITE - V2F + SITE_LEN] = ORIG
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[SITE - V2F:SITE - V2F + SITE_LEN] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiconverge5")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
