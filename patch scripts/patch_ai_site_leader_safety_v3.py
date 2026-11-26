r"""
AI SITE EXPLORING - LEADER SAFETY v3 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of v1/v2 (same zone; v1/v2's
two hooks + three new ones).  Layer on build_ai_sitesearch.py v2.

User (after v2): "the AI are still exploring exploration sites with their LEADERS ALONE in the first few turns.
Sometimes they have other leaderless stacks explore them, which is good, but why do they keep attempting them alone?"

WHAT v2 DID NOT COVER (static audit 10/19; confirm with diag_ai_site_probe.py)
  The ONLY code that mints an AI site search is cave_execai (0x55814780; the vanilla Search 0x557C1E5C is called only
  by AoWx.exe's human UI 0x442445, and every other CreateTE caller builds TEs with [te+0x18] != 0, which the site
  ExecuteTE 0x557C1D28 never turns into a search).  v2 gates cave_execai and cave_msgproc - but with two holes:
   1  cave_execai mints UNCONDITIONALLY when the roster's engine strength is 0 (`test edi,edi / je mint` @0x558147B6,
      the "undefended" shortcut), and cave_msgproc then advertises priority 100 (city tier!) to EVERY group, lone
      leader included (@0x55814AB0 -> 0x55814B0E).  A roster that holds units but sums to 0 strength (units without a
      kind-0 band: TAbstractUnit.GetStrength 0x5577F8F4 returns 0 when [unit+0x28] == 0) therefore looks like free
      loot, draws the leader at top priority and fights him with no gate at all.  ExecuteSearch 0x557C1A20 fights
      whatever [site+0x34] holds (count > 0), so "0 strength" is NOT "undefended".
   2  v1/v2 only protect the TLeader.  Heroes (THero, the player's other irreplaceable units - and what a player sees
      as "their leader" in a scenario whose leader is a hero) were judged as ordinary units -> a lone hero at 1.5x.
  The v2 judge itself is correct for a TLeader that reaches it (emulated v2 + here again).

v3 CHANGES (only stacks/groups that contain a PROTECTED unit; everything else = untouched v2 behaviour)
  RA/RB  both roster-strength calls (cave_execai 0x558147AF, cave_msgproc 0x55814AA7: call TUnitList.GetStrength)
         -> rs_eff: the engine strength, but at least 1 while the roster holds units.  An empty roster stays 0 =
         undefended = free loot for everyone (unchanged).  For unprotected stacks this changes nothing (they already
         minted / got 100 at 0, and 1 is passed by any army).  Protected stacks now go through the v2 judge, whose
         count rules (>= 2 escorts carrying >= 50 %, stack units >= roster units) refuse a lone leader/hero.
  XS     a CHOKE gate in TExplorationSite.ExecuteSearch itself (0x557C1A6F, right after CanSearch passed; 6 bytes
         `mov eax,[esi+0x1C] / mov al,[eax+0x12]` -> jmp xs_gate + nop): if the searching army is owned by an AI
         player ([player+0xA7] != 0), the roster holds units, and the army contains a protected unit that fails the
         v2 judge (mode 0 = search margins), the search is refused (-> 0x557C1CF2, ExecuteSearch's own "cannot search"
         exit; the TE completes as done, nothing else happens).  Human searches are never touched.  This catches any
         origin, present or future (a TE minted before the escort walked off, another mint path, ...).
  PROTECT  "heroes" (default) = every THero incl. the TLeader (THero classref cell 0x55711FAC; TLeader's parent);
         "leader" = TLeader only (v2 behaviour).  Switch with --protect leader|heroes (re-apply converts in place).
  Pure synced game state, no RNG -> identical on all MP peers.

Zone AoWEPACK 0x5581E400..0x5581E800 (v1/v2's; header "ALS3").  Dry-run default; --apply / --revert / --dis / --dll.
  apply : clean / v1 / v2 / v3(other variant) -> v3;   revert : -> pre-leader-safety (exactly what v2/v1 --revert give).
LIFO: revert THIS before reverting/re-running build_ai_sitesearch.py (its caves carry RA/RB/A/B) ; v1/v2 refuse a v3 zone.
Backup <game>\backup\AoWEPACK.dll.bak_aileadsafe3.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_leader_safety_v1 as V1
import patch_ai_site_leader_safety_v2 as V2

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = V2.ZONE, V2.ZONE_END
LIST_STRENGTH, GC_STRENGTHMAX = V2.LIST_STRENGTH, V2.GC_STRENGTHMAX
HOOK_A, HOOK_B = V2.HOOK_A, V2.HOOK_B
HOOK_RA, HOOK_RB = 0x558147AF, 0x55814AA7          # cave_execai / cave_msgproc: call TUnitList.GetStrength (roster)
HOOK_XS, XS_BACK, XS_REFUSE = 0x557C1A6F, 0x557C1A75, 0x557C1CF2
XS_ORIG = bytes.fromhex("8b461c8a4012")             # mov eax,[esi+0x1C] / mov al,[eax+0x12]
GETPLAYERS = 0x557544D0                             # TPlayers.Get(eax=list [[0x558FA040]+0x140], edx=idx) -> player
GAME_CELL = 0x558FA040
CLS_HERO, CLS_LEADER = 0x55711FAC, V2.CLS_LEADER
MAGIC = b"ALS3"

NEW_SRC = """
rs_eff:                         ; eax = roster TUnitList, dl = kind -> engine strength, >= 1 while the list holds units
    push esi
    mov  esi, eax
    call 0x{LS:X}
    test eax, eax
    jnz  rs_out
    mov  eax, [esi+8]
    test eax, eax
    jz   rs_out
    cmp  dword ptr [eax+8], 0
    jle  rs_zero
    mov  eax, 1
    jmp  rs_out
rs_zero:
    xor  eax, eax
rs_out:
    pop  esi
    ret

xs_gate:                        ; ExecuteSearch after CanSearch: ebx = site, esi = TArmyHS on the site (frame live)
    pushad
    mov  edi, [esi+0x1C]
    test edi, edi
    jz   xs_pass
    movsx edx, byte ptr [edi+0x12]
    test edx, edx
    jl   xs_pass
    call xs_p
xs_p:
    pop  eax
    mov  eax, dword ptr [eax + 0x44444444]
    test eax, eax
    jz   xs_pass
    mov  eax, [eax+0x140]
    test eax, eax
    jz   xs_pass
    call 0x{GP:X}
    test eax, eax
    jz   xs_pass
    cmp  byte ptr [eax+0xA7], 0
    je   xs_pass
    mov  eax, [esp+0x10]
    mov  eax, [eax+0x34]
    test eax, eax
    jz   xs_pass
    xor  edx, edx
    call rs_eff
    test eax, eax
    jz   xs_pass
    mov  ebp, eax
    mov  eax, edi
    call 0x{FL:X}
    test eax, eax
    jz   xs_pass
    mov  ebx, eax
    mov  eax, edi
    xor  edx, edx
    call 0x{LS:X}
    mov  esi, edi
    mov  edi, eax
    mov  ecx, [esp+0x10]
    mov  edx, ebp
    xor  eax, eax
    call 0x{JG:X}
    test eax, eax
    jz   xs_refuse
xs_pass:
    popad
    mov  eax, [esi+0x1C]
    mov  al, byte ptr [eax+0x12]
    jmp  0x{XB:X}
xs_refuse:
    popad
    jmp  0x{XR:X}
"""


def build(protect="heroes"):
    V2.CLS_LEADER = CLS_HERO if protect == "heroes" else CLS_LEADER      # find_leader's class (v2 build reads the global)
    try:
        z2, labs = V2.build()
    finally:
        V2.CLS_LEADER = CLS_LEADER
    blob1 = z2[4:]
    org1 = ZONE + 4
    sig_j = bytes.fromhex("5551525089d88b10ff92e0000000")                 # judge: push ebp/ecx/edx/eax; mov eax,ebx; [vmt+0xE0]
    sig_f = bytes.fromhex("5356575589c685f6")                             # find_leader: push x4; mov esi,eax; test esi,esi
    assert blob1.count(sig_j) == 1 and blob1.count(sig_f) == 1
    judge, find_leader = org1 + blob1.find(sig_j), org1 + blob1.find(sig_f)
    org2 = (org1 + len(blob1) + 15) & ~15
    src = NEW_SRC.format(LS=LIST_STRENGTH, GP=GETPLAYERS, FL=find_leader, JG=judge, XB=XS_BACK, XR=XS_REFUSE)
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    blob2 = bytearray(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, org2)[0])
    p = struct.pack("<I", 0x44444444); j = blob2.find(p); assert j > 0 and blob2.count(p) == 1
    k = blob2.rfind(b"\xe8\x00\x00\x00\x00\x58", 0, j); assert 0 <= k and j - k < 12
    blob2[j:j + 4] = struct.pack("<i", GAME_CELL - (org2 + k + 5))
    labs = dict(labs, rs_eff=org2, judge=judge, find_leader=find_leader)
    labs["xs_gate"] = org2 + blob2.find(b"\x60\x8b\x7e\x1c")               # pushad; mov edi,[esi+0x1C]
    assert labs["xs_gate"] > org2
    zone = MAGIC + blob1 + bytes(org2 - org1 - len(blob1)) + bytes(blob2)
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, labs


def call_to(site, tgt):
    return b"\xe8" + struct.pack("<i", tgt - (site + 5))


def jmp_to(site, tgt, n):
    return b"\xe9" + struct.pack("<i", tgt - (site + 5)) + b"\x90" * (n - 5)


def site_bytes(labs=None):
    """hook VA -> bytes for the vanilla/build_ai_sitesearch state (labs None) or for a v3 build."""
    if labs is None:
        return {HOOK_A: call_to(HOOK_A, LIST_STRENGTH), HOOK_B: call_to(HOOK_B, GC_STRENGTHMAX),
                HOOK_RA: call_to(HOOK_RA, LIST_STRENGTH), HOOK_RB: call_to(HOOK_RB, LIST_STRENGTH), HOOK_XS: XS_ORIG}
    return {HOOK_A: call_to(HOOK_A, labs["army_eff"]), HOOK_B: call_to(HOOK_B, labs["grp_eff"]),
            HOOK_RA: call_to(HOOK_RA, labs["rs_eff"]), HOOK_RB: call_to(HOOK_RB, labs["rs_eff"]),
            HOOK_XS: jmp_to(HOOK_XS, labs["xs_gate"], 6)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    ap.add_argument("--protect", choices=("heroes", "leader"), default="heroes"); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, labs = build(a.protect)
    other_zone, other_labs = build("leader" if a.protect == "heroes" else "heroes")
    z1, l1 = V1.build(); z2, l2 = V2.build()
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zl = rd(ZONE, ZONE_END - ZONE)
    def zis(z): return zl[:len(z)] == z and not any(zl[len(z):])
    zstate = ("zero" if not any(zl) else "v1" if zis(z1) else "v2" if zis(z2) else "v3" if zis(zone)
              else "v3-other" if zis(other_zone) else "DIFFERS")
    vanilla = site_bytes()
    want_by_state = {"zero": vanilla, "v3": site_bytes(labs), "v3-other": site_bytes(other_labs),
                     "v1": {**vanilla, HOOK_A: call_to(HOOK_A, l1["army_eff"]), HOOK_B: call_to(HOOK_B, l1["grp_eff"])},
                     "v2": {**vanilla, HOOK_A: call_to(HOOK_A, l2["army_eff"]), HOOK_B: call_to(HOOK_B, l2["grp_eff"])}}
    names = {HOOK_A: "A cave_execai army strength", HOOK_B: "B cave_msgproc group strength",
             HOOK_RA: "RA cave_execai roster strength", HOOK_RB: "RB cave_msgproc roster strength",
             HOOK_XS: "XS ExecuteSearch choke gate"}
    for va, nm in names.items():
        c = rd(va, len(vanilla[va]))
        st = [s for s, w in want_by_state.items() if w[va] == c]
        print("  %-34s @%#x  %s" % (nm, va, "/".join(st) if st else "FOREIGN"))
    allh = list(names)
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 6 for va in allh)]
    print("  zone %#x..%#x %s (v3 %d B, protect=%s; rs_eff %#x xs_gate %#x judge %#x find_leader %#x) | relocs %s"
          % (ZONE, ZONE_END, zstate, len(zone), a.protect, labs["rs_eff"], labs["xs_gate"], labs["judge"], labs["find_leader"], bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:], ZONE + 4):
            if i.address >= labs["rs_eff"]: print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (reloc under a site or the zone)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free / foreign)"); return 1
    w = want_by_state[zstate]
    if any(rd(va, len(w[va])) != w[va] for va in allh):
        print("ABORT (mixed/foreign hook state for zone state %s - is build_ai_sitesearch.py v2 applied?)" % zstate); return 1
    print("  state:", zstate + ("" if a.revert or zstate == "v3" else " - upgrading %s -> v3 in place" % zstate))
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    tgt = vanilla if a.revert else site_bytes(labs)
    if not a.revert: n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    for va in allh: n[va - V2F:va - V2F + len(tgt[va])] = tgt[va]
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aileadsafe3")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
