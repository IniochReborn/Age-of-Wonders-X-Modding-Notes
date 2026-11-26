r"""
AI SITE EXPLORING - LEADER SAFETY v6 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of v1..v5 (same zone
0x5581E400..0x5581E800, same five hooks A / B / RA / RB / XS).  Layer on build_ai_sitesearch.py v2.

User (final spec): leader stacks HEAD to a site at 1.75x the defenders, FIGHT only at >= 2.0x, leader HP >= 75 %.
The leader "wait for reinforcements" bands live in patch_ai_site_converge_v4 (search gate), which must know that the
stack on the site holds the leader - v6 provides that contract:
  army_eff (hook A): leader stack, HP >= 75 %  -> eax = its real strength, edx = 0x4C454144 ("LEAD");
                     leader stack, HP <  75 %  -> eax = 0, edx = 0 (gate skips; heal first);
                     leaderless stack          -> eax = strength, edx = 0.
                     (v5 returned 0 for a leader stack below 2.0x; the gate now runs the band rules.)
  judge  : mode 0 search K = 2.0x, mode 1 attraction K = 1.75x, mode 2 HP only (K = 0).  S*20 >= R*K (K x20).
  grp_eff: a passing leader stack answers L x 20 / 35 (>= roster  <=>  L >= 1.75 x roster; recruit v3's attraction
           bar is 1.0x).  NEW: if the leader GAVE UP this site (converge v4 table B entry {site | 2<<24, day}) less
           than COOL (3) days ago, the whole leader group answers 0 for the site (stops being attracted, no parking).
  XS choke gate: judge mode 0 (HP >= 75 % and >= 2.0x) - every leader search still needs 2.0x.
Table B (shared with converge v4): 16 x {key, day} at AoWEPACK .idata page slack 0x5590B510..0x5590B590 (zero at
load; free between armyhooks 0x5590B500/B504 and smokescreen W 0x5590B600).  Slot = (x + 3y + 5*level) & 15.
Pure synced game state + day, no RNG -> identical on all MP peers.

Dry-run default; --apply / --revert / --dis / --dll / --protect.
  apply : zero / v1..v5 (either protect) / v6 (other protect) -> v6;  revert : -> pre-leader-safety (== v5/../v1
  --revert).  v1..v5 scripts refuse a v6 zone.  LIFO: revert patch_ai_site_converge_* first, then this, before
  build_ai_sitesearch.py.  Backup <game>\backup\AoWEPACK.dll.bak_aileadsafe6.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_site_leader_safety_v1 as V1
import patch_ai_site_leader_safety_v2 as V2
import patch_ai_site_leader_safety_v3 as V3
import patch_ai_site_leader_safety_v4 as V4
import patch_ai_site_leader_safety_v5 as V5

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V4.BASE, V4.V2F
ZONE, ZONE_END = V4.ZONE, V4.ZONE_END
HOOK_A, HOOK_B, HOOK_RA, HOOK_RB, HOOK_XS = V4.HOOK_A, V4.HOOK_B, V4.HOOK_RA, V4.HOOK_RB, V4.HOOK_XS
HP_PCT = 75
K_SEARCH, K_ATT = 40, 35                         # x20: 2.0x / 1.75x
COOL = 3                                         # days a given-up site is ignored by the leader's group
TABLE_B = 0x5590B510
LEAD_MAGIC = 0x4C454144
MAGIC = b"ALS6"

V5_BUILDS = {p: V5.build(p) for p in ("leader", "heroes")}

A_OLD = """    mov  ebx, eax
    mov  ecx, [esp+0xC]
    mov  edx, [esp+4]
    xor  eax, eax
    call judge
    test eax, eax
    jz   ret_zero
a_plain:
    mov  eax, edi
    jmp  fin
ret_zero:
    xor  eax, eax
fin:"""
A_NEW = """    mov  ebx, eax
    mov  ecx, [esp+0xC]
    mov  edx, [esp+4]
    mov  eax, 2
    call judge
    test eax, eax
    jz   ret_zero
    mov  eax, edi
    mov  edx, 0x%X
    jmp  fin
a_plain:
    mov  eax, edi
    xor  edx, edx
    jmp  fin
ret_zero:
    xor  eax, eax
    xor  edx, edx
fin:""" % LEAD_MAGIC

J_OLD_HEAD = "    mov  eax, [esp]\n    test eax, eax\n    jnz  j_att\n"
J_OLD_TAIL = "    mov  edx, [esp+4]\n    imul edx, ecx\n"
J_NEW = """    mov  eax, [esp]
    mov  ecx, %d
    test eax, eax
    jz   j_k
    mov  ecx, %d
    cmp  eax, 1
    je   j_k
    xor  ecx, ecx
j_k:
    mov  eax, edi
    imul eax, eax, 20
    mov  edx, [esp+4]
    imul edx, ecx
""" % (K_SEARCH, K_ATT)

S_OLD = """    mov  eax, [esp+4]
    imul eax, eax, 125
    lea  ecx, [ecx+ecx*4]
    add  ecx, ecx
    xor  edx, edx
    div  ecx
"""
S_NEW = """    mov  eax, [esp+4]
    imul eax, eax, 20
    xor  edx, edx
    div  ecx
"""
G_OLD = "    jz   g_plain\n    mov  ebx, eax\n"
G_NEW = """    jz   g_plain
    mov  ebx, eax
    mov  eax, [esp+0x10]
    call cool
    test eax, eax
    jz   g_nc
    xor  eax, eax
    jmp  g_out
g_nc:
"""
COOL_SRC = """
cool:
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movzx edi, al
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movzx ebx, al
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movzx esi, al
    lea  ecx, [ebx+ebx*2]
    add  ecx, edi
    lea  edx, [esi+esi*4]
    add  ecx, edx
    and  ecx, 15
    shl  esi, 16
    shl  ebx, 8
    or   edi, ebx
    or   edi, esi
    or   edi, 0x2000000
    call c_pic
c_pic:
    pop  ebp
    lea  ebp, [ebp + 0x55555555]
    cmp  [ebp+ecx*8], edi
    jne  c_no
    call c_pic2
c_pic2:
    pop  eax
    mov  eax, dword ptr [eax + 0x22222222]
    test eax, eax
    jz   c_no
    mov  eax, [eax]
    test eax, eax
    jz   c_no
    mov  eax, [eax+0x174]
    sub  eax, [ebp+ecx*8+4]
    jl   c_no
    cmp  eax, %d
    jge  c_no
    mov  eax, 1
    jmp  c_out
c_no:
    xor  eax, eax
c_out:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
""" % COOL


def v6_src():
    s = V5.v5_src()
    assert s.count(A_OLD) == 1 and s.count(J_OLD_HEAD) == 1 and s.count(J_OLD_TAIL) == 1
    assert s.count(S_OLD) == 1 and s.count(G_OLD) == 1
    s = s.replace(A_OLD, A_NEW).replace(S_OLD, S_NEW).replace(G_OLD, G_NEW)
    i = s.index(J_OLD_HEAD); j = s.index(J_OLD_TAIL) + len(J_OLD_TAIL)
    s = s[:i] + J_NEW + s[j:]
    assert "0x22222222" not in s
    return s + COOL_SRC


def build(protect="leader"):
    saved = {k: getattr(V4, k) for k in ("SRC", "HP_PCT", "MIN_ESC", "ESC_PCT", "EARLY_DAY",
                                         "K_MINT_EARLY", "K_MINT", "K_ATT_EARLY", "K_ATT", "MAGIC", "PH")}
    try:
        V4.SRC = v6_src()
        V4.HP_PCT, V4.MIN_ESC, V4.ESC_PCT, V4.EARLY_DAY = HP_PCT, 0, 0, 0
        V4.K_MINT_EARLY = V4.K_MINT = V4.K_ATT_EARLY = V4.K_ATT = 0
        V4.MAGIC = MAGIC
        ph = dict(saved["PH"]); ph[0x22222222] = (V4.MAPCELL, 0x58); ph[0x55555555] = (TABLE_B, 0x5D)
        V4.PH = ph
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
    (z4l, l4l), (z4h, l4h) = V5.V4_BUILDS["leader"], V5.V4_BUILDS["heroes"]
    (z5l, l5l), (z5h, l5h) = V5_BUILDS["leader"], V5_BUILDS["heroes"]
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zl = rd(ZONE, ZONE_END - ZONE)
    def zis(z): return zl[:len(z)] == z and not any(zl[len(z):])
    vanilla = V3.site_bytes()
    states = {"zero": (None, vanilla),
              "v1": (z1, {**vanilla, HOOK_A: call_to(HOOK_A, l1["army_eff"]), HOOK_B: call_to(HOOK_B, l1["grp_eff"])}),
              "v2": (z2, {**vanilla, HOOK_A: call_to(HOOK_A, l2["army_eff"]), HOOK_B: call_to(HOOK_B, l2["grp_eff"])}),
              "v3-leader": (z3l, V3.site_bytes(l3l)), "v3-heroes": (z3h, V3.site_bytes(l3h)),
              "v4-leader": (z4l, site_bytes(l4l)), "v4-heroes": (z4h, site_bytes(l4h)),
              "v5-leader": (z5l, site_bytes(l5l)), "v5-heroes": (z5h, site_bytes(l5h)),
              "v6": (zone, site_bytes(labs)), "v6-other": (ozone, site_bytes(olabs))}
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
    print("  zone %#x..%#x %s (v6 %d B, protect=%s; %s) | table B %#x | relocs %s"
          % (ZONE, ZONE_END, zstate, len(zone), a.protect, " ".join("%s %#x" % kv for kv in labs.items()), TABLE_B, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:], ZONE + 4):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert and rd(0x55817000, 4) in (b"CNV4", b"CNV5"):
        print("ABORT (patch_ai_site_converge_v4/v5 is applied and relies on v6's army_eff contract - revert it first)"); return 1
    if bad: print("ABORT (reloc under a site or the zone)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free / foreign)"); return 1
    w = states[zstate][1]
    if any(rd(va, len(w[va])) != w[va] for va in allh):
        print("ABORT (mixed/foreign hook state for zone state %s - is build_ai_sitesearch.py v2 applied?)" % zstate); return 1
    print("  state:", zstate + ("" if a.revert or zstate == "v6" else " - upgrading %s -> v6 in place" % zstate))
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    tgt = vanilla if a.revert else site_bytes(labs)
    if not a.revert: n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    for va in allh: n[va - V2F:va - V2F + len(tgt[va])] = tgt[va]
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aileadsafe6")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
