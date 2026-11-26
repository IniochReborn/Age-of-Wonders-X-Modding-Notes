r"""
AI SITE RAIDS - GATHER A STRONG ENOUGH FORCE v3 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of
patch_ai_site_recruit_v1 / v2 (same zone 0x5581D000..0x5581D400, same hooks M / T / A, same table 0x5590BD20).

User (final spec): leaderless stacks HEAD to a site at 1.0x the defenders (was 1.25x); gathering targets 1.0x.
v3 changes (everything else = v1/v2):
  M  weak-group gate: group >= roster (1.0x) -> original ladder (ecx = 3 x roster re-loaded for the ladder);
     weaker group without the leader -> priority 15 (engine cooperation / recruitment / production gathers);
     weaker group with the leader -> refused.  Leader groups are judged by ai-site-leader-safety v6 (its grp_eff
     answers L x 20 / 35 for a passing leader stack, so this 1.0x bar == the leader's 1.75x attraction bar).
  tag = roster x 1.0 -> the selector's required strength = roster x superiority.
Dry-run default; --apply / --revert / --dis / --dll.  apply : vanilla / v1 / v2 -> v3;  revert : -> vanilla
(== v1/v2 --revert).  v1/v2 scripts refuse a v3 zone.  LIFO: revert this before build_ai_sitesearch.py.
Backup .bak_aisiterecruit3.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_site_recruit_v1 as R1
import patch_ai_site_recruit_v2 as R2

DLL = game_file("AoWEPACK.dll")
BASE, V2F = R1.BASE, R1.V2F
ZONE, ZONE_END = R1.ZONE, R1.ZONE_END

V1_BUILD = R2.V1_BUILD
V2_BUILD = R2.build()

M_NEW3 = """    cmp  eax, ebp
    jl   weak
    lea  ecx, [ebp+ebp*2]
    jmp  {STRONG}"""


def build():
    saved = {k: getattr(R1, k) for k in ("SRC_M", "SRC_S", "TAGK", "MAGIC")}
    try:
        assert R1.SRC_M.count(R2.M_OLD) == 1 and R1.SRC_S.count(R2.T_OLD) == 1
        R1.SRC_M = R1.SRC_M.replace(R2.M_OLD, M_NEW3)
        R1.SRC_S = R1.SRC_S.replace(R2.T_OLD, R2.T_NEW)
        R1.TAGK, R1.MAGIC = 100, b"SRC3"            # tag = roster x 100 / 100
        return R1.build()
    finally:
        for k, v in saved.items(): setattr(R1, k, v)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, sites, hasl = build()
    z1, sites1, _h1 = V1_BUILD
    z2, sites2, _h2 = V2_BUILD
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    def zis(z): return zl[:len(z)] == z and not any(zl[len(z):])
    zstate = "zero" if not any(zl) else "v3" if zis(zone) else "v2" if zis(z2) else "v1" if zis(z1) else "DIFFERS"
    st = {}
    for s, (o, n) in sites.items():
        b = bytes(d[s - V2F:s - V2F + len(o)])
        st[s] = ("vanilla" if b == o else "v3" if b == n else "v2" if b == sites2[s][1] else
                 "v1" if b == sites1[s][1] else "FOREIGN")
        print("  site %#x %s" % (s, st[s]))
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END
           or any(s - 3 <= r < s + len(o) for s, (o, n) in sites.items())]
    print("  zone %#x..%#x %s (%d B; hasl %#x) | relocs %s" % (ZONE, ZONE_END, zstate, len(zone), hasl, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[R1.M_ENTRY - ZONE:R1.T_ENTRY - ZONE].rstrip(b"\0"), R1.M_ENTRY):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "FOREIGN" in st.values(): print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if zstate == "zero" and set(st.values()) != {"vanilla"}: print("ABORT (mixed state)"); return 1
    if zstate != "zero" and not set(st.values()) <= {"v1", "v2", "v3"}: print("ABORT (mixed state)"); return 1
    print("  state:", zstate + (" - upgrading %s -> v3 in place" % zstate if zstate in ("v1", "v2") and not a.revert else ""))
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    if a.revert:
        for s, (o, _) in sites.items(): n[s - V2F:s - V2F + len(o)] = o
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for s, (_, p) in sites.items(): n[s - V2F:s - V2F + len(p)] = p
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aisiterecruit3")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
