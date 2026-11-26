r"""
AI SITE EXPLORING - LEADER SAFETY v5 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of v1..v4 (same zone
0x5581E400..0x5581E800, same five hooks A / B / RA / RB / XS).  Layer on build_ai_sitesearch.py v2.

User ("AI too passive about attempting exploration sites"):
  leader stacks: 2.0x the defenders for BOTH heading to the site and starting the fight; leader HP >= 75 % (was 60);
  NO escort requirement (v4: >= 2 escorts carrying >= 25 %); NO "at least as many units as the defenders" rule.
  Leaderless stacks: 1.25x (attraction gate = patch_ai_site_recruit_v2 hook M; search gate = converge v3).

v5 = v4 with:
  judge   : HP >= HP_PCT (75 %) and stack S >= K x roster, K = 2.0 for search (army_eff / XS) AND attraction (grp_eff);
            the escort-count, escort-share and unit-count checks are gone; no early-game window (EARLY_DAY 0).
  grp_eff : a passing leader stack answers L x 1.25 / K (was L x 1.5 / K) so recruit v2's 1.25x attraction bar sits
            exactly at the leader bar (L >= 2.0 x roster  <=>  answer >= 1.25 x roster) and the ladder starts at 15.
            A failing leader stack still lets the group's OTHER stacks answer (group - leader stack), as v4.
  Everything else (all-damage-type metric, rs_eff floor, find_leader, XS choke gate, --protect) unchanged.
Pure synced game state, no RNG -> identical on all MP peers.

Dry-run default; --apply / --revert / --dis / --dll / --protect.
  apply : zero / v1 / v2 / v3 / v4 (either protect) / v5 (other protect) -> v5;  revert : -> pre-leader-safety
  (== v4/v3/v2/v1 --revert).  v1..v4 scripts refuse a v5 zone.  LIFO: revert patch_ai_site_converge_* first, then
  this, before build_ai_sitesearch.py.  Backup <game>\backup\AoWEPACK.dll.bak_aileadsafe5.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_site_leader_safety_v1 as V1
import patch_ai_site_leader_safety_v2 as V2
import patch_ai_site_leader_safety_v3 as V3
import patch_ai_site_leader_safety_v4 as V4

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V4.BASE, V4.V2F
ZONE, ZONE_END = V4.ZONE, V4.ZONE_END
HOOK_A, HOOK_B, HOOK_RA, HOOK_RB, HOOK_XS = V4.HOOK_A, V4.HOOK_B, V4.HOOK_RA, V4.HOOK_RB, V4.HOOK_XS
HP_PCT, K_LEADER = 75, 20                       # %, x10 (both search and attraction)

# v4's builds (for state detection) - taken before V4's module globals are retuned below
V4_BUILDS = {p: V4.build(p) for p in ("leader", "heroes")}

SCALE_OLD = """    mov  eax, [esp+4]
    imul eax, eax, 15
    xor  edx, edx
    div  ecx
"""
SCALE_NEW = """    mov  eax, [esp+4]
    imul eax, eax, 125
    lea  ecx, [ecx+ecx*4]
    add  ecx, ecx
    xor  edx, edx
    div  ecx
"""
J_LO = """    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  ebp, eax
    cmp  ebp, {ME1}"""
J_HI = """    mov  eax, [esp]
    test eax, eax
    jnz  j_att"""


def v5_src():
    s = V4.SRC
    assert s.count(SCALE_OLD) == 1 and s.count(J_LO) == 1 and s.count(J_HI) == 1
    s = s.replace(SCALE_OLD, SCALE_NEW)
    i, j = s.index(J_LO), s.index(J_HI)
    return s[:i] + s[j:]                           # drop the unit-count / roster-count / escort-share checks


def build(protect="leader"):
    saved = {k: getattr(V4, k) for k in ("SRC", "HP_PCT", "MIN_ESC", "ESC_PCT", "EARLY_DAY",
                                         "K_MINT_EARLY", "K_MINT", "K_ATT_EARLY", "K_ATT", "MAGIC")}
    try:
        V4.SRC = v5_src()
        V4.HP_PCT, V4.MIN_ESC, V4.ESC_PCT, V4.EARLY_DAY = HP_PCT, 0, 0, 0
        V4.K_MINT_EARLY = V4.K_MINT = V4.K_ATT_EARLY = V4.K_ATT = K_LEADER
        V4.MAGIC = b"ALS5"
        return V4.build(protect)
    finally:
        for k, v in saved.items(): setattr(V4, k, v)


site_bytes, call_to = V4.site_bytes, V4.call_to


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    ap.add_argument("--protect", choices=("heroes", "leader"), default="leader"); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    other = "heroes" if a.protect == "leader" else "leader"
    zone, labs = build(a.protect); ozone, olabs = build(other)
    z1, l1 = V1.build(); z2, l2 = V2.build()
    z3l, l3l = V3.build("leader"); z3h, l3h = V3.build("heroes")
    (z4l, l4l), (z4h, l4h) = V4_BUILDS["leader"], V4_BUILDS["heroes"]
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zl = rd(ZONE, ZONE_END - ZONE)
    def zis(z): return zl[:len(z)] == z and not any(zl[len(z):])
    vanilla = V3.site_bytes()
    states = {"zero": (None, vanilla),
              "v1": (z1, {**vanilla, HOOK_A: call_to(HOOK_A, l1["army_eff"]), HOOK_B: call_to(HOOK_B, l1["grp_eff"])}),
              "v2": (z2, {**vanilla, HOOK_A: call_to(HOOK_A, l2["army_eff"]), HOOK_B: call_to(HOOK_B, l2["grp_eff"])}),
              "v3-leader": (z3l, V3.site_bytes(l3l)), "v3-heroes": (z3h, V3.site_bytes(l3h)),
              "v4-leader": (z4l, site_bytes(l4l)), "v4-heroes": (z4h, site_bytes(l4h)),
              "v5": (zone, site_bytes(labs)), "v5-other": (ozone, site_bytes(olabs))}
    zstate = "zero" if not any(zl) else next((s for s, (z, _w) in states.items() if z and zis(z)), "DIFFERS")
    names = {HOOK_A: "A cave_execai army strength", HOOK_B: "B cave_msgproc group strength",
             HOOK_RA: "RA cave_execai roster strength", HOOK_RB: "RB cave_msgproc roster strength",
             HOOK_XS: "XS ExecuteSearch choke gate"}
    for va, nm in names.items():
        c = rd(va, len(vanilla[va]))
        st = [s for s, (_z, w) in states.items() if w[va] == c]
        print("  %-34s @%#x  %s" % (nm, va, "/".join(st) if st else "FOREIGN"))
    allh = list(names)
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 6 for va in allh)]
    print("  zone %#x..%#x %s (v5 %d B, protect=%s; %s) | relocs %s"
          % (ZONE, ZONE_END, zstate, len(zone), a.protect, " ".join("%s %#x" % kv for kv in labs.items()), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:], ZONE + 4):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (reloc under a site or the zone)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free / foreign)"); return 1
    w = states[zstate][1]
    if any(rd(va, len(w[va])) != w[va] for va in allh):
        print("ABORT (mixed/foreign hook state for zone state %s - is build_ai_sitesearch.py v2 applied?)" % zstate); return 1
    print("  state:", zstate + ("" if a.revert or zstate == "v5" else " - upgrading %s -> v5 in place" % zstate))
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    tgt = vanilla if a.revert else site_bytes(labs)
    if not a.revert: n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    for va in allh: n[va - V2F:va - V2F + len(tgt[va])] = tgt[va]
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aileadsafe5")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
