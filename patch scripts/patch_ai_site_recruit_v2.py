r"""
AI SITE RAIDS - GATHER A STRONG ENOUGH FORCE v2 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of
patch_ai_site_recruit_v1.py (same zone 0x5581D000..0x5581D400, same hooks M / T / A, same table 0x5590BD20).

User ("AI too passive"): leaderless stacks head to a site at 1.25x the defenders (was 1.5x); keep the weaker-group
gathering but target 1.25x.
v2 changes (everything else = v1):
  M  weak-group gate: 4 x group >= 5 x roster (1.25x) -> original ladder (ecx = 3 x roster re-loaded for the ladder:
     1.25x..2x -> 15, 2x -> 30, 3x -> 45, 5x -> 75, 10x -> 100); weaker group without the leader -> priority 15 (the
     engine's cooperation / recruitment / production then gathers); weaker group with the leader -> refused.
     Leader groups are judged by ai-site-leader-safety v5 (its grp_eff answers L x 1.25 / 2.0 for a passing leader
     stack, so the 1.25x bar here == the leader's 2.0x bar).
  tag = roster x 1.25 (was x 1.5) -> the selector's required strength = roster x 1.25 x superiority.
Dry-run default; --apply / --revert / --dis / --dll.  apply : vanilla / v1 -> v2;  revert : -> vanilla (== v1 --revert).
v1's script refuses a v2 zone.  LIFO: revert this before build_ai_sitesearch.py.  Backup .bak_aisiterecruit2.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_site_recruit_v1 as R1

DLL = game_file("AoWEPACK.dll")
BASE, V2F = R1.BASE, R1.V2F
ZONE, ZONE_END = R1.ZONE, R1.ZONE_END

V1_BUILD = R1.build()

M_OLD = """    lea  ecx, [ebp+ebp*2]
    lea  edx, [eax+eax]
    cmp  edx, ecx
    jl   weak
    jmp  {STRONG}"""
M_NEW = """    lea  ecx, [ebp+ebp*4]
    lea  edx, [eax*4]
    cmp  edx, ecx
    jl   weak
    lea  ecx, [ebp+ebp*2]
    jmp  {STRONG}"""
T_OLD = """    imul eax, eax, {K}
    cdq
    mov  ecx, 10"""
T_NEW = """    imul eax, eax, {K}
    cdq
    mov  ecx, 100"""


def build():
    saved = {k: getattr(R1, k) for k in ("SRC_M", "SRC_S", "TAGK", "MAGIC")}
    try:
        assert R1.SRC_M.count(M_OLD) == 1 and R1.SRC_S.count(T_OLD) == 1
        R1.SRC_M = R1.SRC_M.replace(M_OLD, M_NEW)
        R1.SRC_S = R1.SRC_S.replace(T_OLD, T_NEW)
        R1.TAGK, R1.MAGIC = 125, b"SRC2"            # tag = roster x 125 / 100
        return R1.build()
    finally:
        for k, v in saved.items(): setattr(R1, k, v)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, sites, hasl = build()
    z1, sites1, _h1 = V1_BUILD
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    def zis(z): return zl[:len(z)] == z and not any(zl[len(z):])
    zstate = "zero" if not any(zl) else "v2" if zis(zone) else "v1" if zis(z1) else "DIFFERS"
    st = {}
    for s, (o, n) in sites.items():
        b = bytes(d[s - V2F:s - V2F + len(o)])
        st[s] = "vanilla" if b == o else "v2" if b == n else "v1" if b == sites1[s][1] else "FOREIGN"
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
    # site bytes of v1 and v2 are identical jumps (same entry points); the zone decides the state
    want_sites = "vanilla" if zstate == "zero" else ("v2" if set(st.values()) <= {"v1", "v2"} else "?")
    if zstate != "zero" and want_sites == "?": print("ABORT (mixed state)"); return 1
    if zstate == "zero" and set(st.values()) != {"vanilla"}: print("ABORT (mixed state)"); return 1
    print("  state:", zstate + (" - upgrading v1 -> v2 in place" if zstate == "v1" and not a.revert else ""))
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
        bak = bak_path(a.dll, ".bak_aisiterecruit2")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
