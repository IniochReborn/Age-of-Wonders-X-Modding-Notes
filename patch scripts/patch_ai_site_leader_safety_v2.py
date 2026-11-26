r"""
AI SITE EXPLORING - LEADER SAFETY v2 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of v1 (same zone, same
two hooks).  Layer on build_ai_sitesearch.py v2.

User (after v1): "AI still dies too often at the beginning of the game attempting to clear exploration sites.  In the
latest test an AI leader SEPARATED from his army and attempted it ALONE."

WHY v1 LET IT HAPPEN
  * The search is minted by cave_execai (0x55814780) for WHATEVER army stands on the site hex ([site+4] ->
    GetObjectOfType(0x20217) -> [+0x1C]), judged by that army alone.  v1 still allowed a LONE / token-escort leader
    to search at 3x the roster strength.  Early-game leaders are strong single units (band multiplier), so 3x a small
    roster is easy to reach - but a single unit facing 4-8 defenders in auto-combat dies far more often than a
    strength SUM suggests (every defender gets its strikes in; strength is additive, combat is not).
  * Attraction (cave_msgproc 0x55814A40, msg 0x1200) is judged on the AI GROUP (TAIGroupControl [gc+0xC] = unit
    list that can span several stacks).  A group whose total passes v1's bar walks to the site; stacks move
    separately, the leader's stack arrives first ALONE, and the mint gate then judged a lone leader at 3x
    -> search -> dead leader.  That is the "separated from his army" report.
  * Rosters ([site+0x34]) are rolled once on day 1 (TExplorationSite.NewDay @0x557C20A4, map[+0x174]==1), so the
    defender estimate is exact, not an average - the error is the margins and the lone case, not the estimate.

v2 RULES (only stacks/groups that contain the player's LEADER; everything else = untouched v2 behaviour):
  The leader is judged on the stack he is ACTUALLY in (search: the army on the site; attraction: the leader's own
  army [leader+4], IsClass TArmy 0x557130AC - NOT the whole group), and must pass ALL of:
    1  leader hp >= 60 % of max
    2  at least 2 other units in his stack (never alone / with a single bodyguard)
    3  escorts carry >= 50 % of the stack's strength (no token escort)
    4  his stack has at least as many units as the site roster
    5  stack strength >= k x roster:   search  k = 4.0 before day 15, 2.5 after
                                       attract k = 5.0 before day 15, 3.5 after   (day = map[+0x174])
  Fail -> effective strength 0 (no search / no attraction).  Pass -> search: plain strength; attraction: strength
  scaled by 1.5/k so the v2 ladder starts at priority 15 at the bar (leader groups never out-bid other duties).
  Attraction is judged on the same stack and is always the stricter bar, so an attracted leader can also search on
  arrival (no "parked leader"); a leader stack that splits en route is refused on arrival and simply rejoins (the
  group's other stacks still head for the site, and as non-leader stacks they search under plain v2 rules).
  Undefended sites (roster strength 0) stay free loot for everyone, leader alone included.
  Pure synced game state, no RNG -> identical on all MP peers.
Zone AoWEPACK 0x5581E400..0x5581E800 (v1's; header "ALS2").  Dry-run default; --apply / --revert / --dis / --dll.
  apply : clean or v1 -> v2 (in place);   revert : -> pre-leader-safety (exactly what v1 --revert gives).
LIFO: revert THIS before reverting/re-running build_ai_sitesearch.py.  v1's script refuses a v2 zone.
Backup <game>\backup\AoWEPACK.dll.bak_aileadsafe2.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_leader_safety_v1 as V1

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581E400, 0x5581E800
LIST_STRENGTH = 0x55783300      # TUnitList.GetStrength(eax=list, dl=kind)
UNIT_STRENGTH = 0x5577F8F4      # TAbstractUnit.GetStrength(eax=unit, dl=kind)
GC_STRENGTHMAX = 0x557389D4     # TAIGroupControl.GetStrengthMax(eax=gc, dx=mask)
GETUNIT = 0x5578309C            # TUnitList.GetUnit(eax=list, edx=idx)
ISCLASS = 0x557010C0            # System.@IsClass thunk (eax=obj, edx=class) -> al
CLS_LEADER = 0x557121F8         # TLeader classref cell
CLS_ARMY = 0x557130AC           # TArmy classref cell
MAPCELL = 0x558E9494            # [[cell]] = TAoWHSMap; [map+0x174] = day
HOOK_A, HOOK_B = 0x558147D7, 0x55814ABD
HP_PCT, MIN_ESC, ESC_PCT, EARLY_DAY = 60, 2, 50, 5    # 10/19 user: early-game window 15 -> 5 days (AI too passive)
K_MINT_EARLY, K_MINT, K_ATT_EARLY, K_ATT = 40, 25, 50, 35        # x10
MAGIC = b"ALS2"

SRC = f"""
army_eff:                       ; hook A: eax = army on the site, edx = kind; caller ebx = site, edi = roster S
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    call 0x{LIST_STRENGTH:X}
    mov  edi, eax
    mov  eax, esi
    call find_leader
    test eax, eax
    jz   a_plain
    mov  ebx, eax
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
fin:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret

grp_eff:                        ; hook B: eax = TAIGroupControl, dx = mask; caller esi = site, ebp = roster S
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    call 0x{GC_STRENGTHMAX:X}
    mov  edi, eax
    mov  eax, [esi+0xC]
    test eax, eax
    jz   g_plain
    call find_leader
    test eax, eax
    jz   g_plain
    mov  ebx, eax
    mov  eax, [ebx+4]
    test eax, eax
    jz   ret_zero
    push eax
    call g_pic
g_pic:
    pop  edx
    mov  edx, dword ptr [edx + 0x33333333]
    call 0x{ISCLASS:X}
    pop  esi
    test al, al
    jz   ret_zero
    mov  eax, esi
    xor  edx, edx
    call 0x{LIST_STRENGTH:X}
    mov  edi, eax
    mov  ecx, [esp+8]
    mov  edx, [esp]
    mov  eax, 1
    call judge
    test eax, eax
    jz   ret_zero
    mov  eax, edi
    imul eax, eax, 15
    xor  edx, edx
    div  ecx
    jmp  fin
g_plain:
    mov  eax, edi
    jmp  fin

judge:                          ; ebx = leader, esi = stack, edi = stack S, ecx = site, edx = roster S, eax = mode
    push ebp                    ;   -> eax = 1 pass / 0 fail, ecx = k (x10)
    push ecx
    push edx
    push eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0xE0]
    movsx ebp, al
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0xD0]
    movsx eax, al
    imul eax, eax, {HP_PCT}
    imul ebp, ebp, 100
    cmp  ebp, eax
    jl   j_fail
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  ebp, eax
    cmp  ebp, {MIN_ESC + 1}
    jl   j_fail
    mov  eax, [esp+8]
    mov  eax, [eax+0x34]
    test eax, eax
    jz   j_cnt
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    cmp  ebp, eax
    jl   j_fail
j_cnt:
    mov  eax, ebx
    xor  edx, edx
    call 0x{UNIT_STRENGTH:X}
    mov  edx, edi
    sub  edx, eax
    jge  j_e1
    xor  edx, edx
j_e1:
    imul edx, edx, 100
    imul eax, edi, {ESC_PCT}
    cmp  edx, eax
    jl   j_fail
    mov  eax, [esp]
    test eax, eax
    jnz  j_att
    mov  ecx, {K_MINT}
    mov  edx, {K_MINT_EARLY}
    jmp  j_day
j_att:
    mov  ecx, {K_ATT}
    mov  edx, {K_ATT_EARLY}
j_day:
    call j_pic
j_pic:
    pop  ebp
    mov  ebp, dword ptr [ebp + 0x22222222]
    test ebp, ebp
    jz   j_k
    mov  ebp, [ebp]
    test ebp, ebp
    jz   j_k
    cmp  dword ptr [ebp+0x174], {EARLY_DAY}
    jge  j_k
    mov  ecx, edx
j_k:
    mov  eax, edi
    imul eax, eax, 10
    mov  edx, [esp+4]
    imul edx, ecx
    cmp  eax, edx
    jl   j_fail
    mov  eax, 1
    jmp  j_out
j_fail:
    xor  eax, eax
j_out:
    add  esp, 0xC
    pop  ebp
    ret

find_leader:                    ; eax = TUnitList -> eax = first TLeader in it, or 0.  saves ebx/esi/edi/ebp
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    test esi, esi
    jz   fl_none
    call fl_a
fl_a:
    pop  ebp
    mov  ebp, dword ptr [ebp + 0x11111111]
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  edi, eax
    xor  ebx, ebx
fl_lp:
    cmp  ebx, edi
    jge  fl_none
    mov  edx, ebx
    mov  eax, esi
    call 0x{GETUNIT:X}
    test eax, eax
    jz   fl_nx
    push eax
    mov  edx, ebp
    call 0x{ISCLASS:X}
    test al, al
    pop  eax
    jnz  fl_out
fl_nx:
    inc  ebx
    jmp  fl_lp
fl_none:
    xor  eax, eax
fl_out:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""


def build():
    src = "\n".join(ln.split(";")[0] for ln in SRC.splitlines())
    org = ZONE + 4
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, org)
    code = bytearray(code)
    for ph, tgt, popreg in ((0x11111111, CLS_LEADER, 0x5D), (0x22222222, MAPCELL, 0x5D), (0x33333333, CLS_ARMY, 0x5A)):
        p = struct.pack("<I", ph)
        j = code.find(p); assert j > 0 and code.count(p) == 1, hex(ph)
        k = code.rfind(b"\xe8\x00\x00\x00\x00" + bytes([popreg]), 0, j); assert 0 <= k and j - k < 12, hex(ph)
        code[j:j + 4] = struct.pack("<i", tgt - (org + k + 5))
    labs = {}
    for k in range(len(code) - 11):
        if bytes(code[k:k + 7]) == b"\x53\x56\x57\x55\x89\xc6\xe8":
            tgt = org + k + 11 + struct.unpack_from("<i", code, k + 7)[0]
            nm = {LIST_STRENGTH: "army_eff", GC_STRENGTHMAX: "grp_eff"}.get(tgt)
            if nm: labs[nm] = org + k
    assert set(labs) == {"army_eff", "grp_eff"}, labs
    code = MAGIC + bytes(code)
    assert len(code) <= ZONE_END - ZONE
    return code, labs


def call_to(site, tgt):
    return b"\xe8" + struct.pack("<i", tgt - (site + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, labs = build()
    z1, l1 = V1.build()
    hooks = [(HOOK_A, LIST_STRENGTH, "army_eff", "cave_execai army strength"),
             (HOOK_B, GC_STRENGTHMAX, "grp_eff", "cave_msgproc group strength")]
    states = []
    for va, orig, lab, nm in hooks:
        c = bytes(d[va - V2F:va - V2F + 5])
        st = ("site" if c == call_to(va, orig) else "v1" if c == call_to(va, l1[lab])
              else "ours" if c == call_to(va, labs[lab]) else "FOREIGN")
        states.append(st); print("  %-30s @%#x  %s" % (nm, va, st))
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = ("zero" if not any(zl) else "v1" if zl[:len(z1)] == z1 and not any(zl[len(z1):])
              else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS")
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 5 for va, *_ in hooks)]
    print("  zone %#x..%#x %s (%d B; army_eff %#x, grp_eff %#x) | relocs %s" % (ZONE, ZONE_END, zstate, len(zone), labs["army_eff"], labs["grp_eff"], bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:], ZONE + 4):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "FOREIGN" in states: print("ABORT (site/reloc) - is build_ai_sitesearch.py v2 applied?"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    want = {"zero": ("clean", lambda va, orig, lab: call_to(va, orig)),     # army_eff sits at the same VA in v1 and
            "v1": ("v1", lambda va, orig, lab: call_to(va, l1[lab])),        # v2, so the zone decides which labels
            "ours": ("v2", lambda va, orig, lab: call_to(va, labs[lab]))}.get(zstate)   # the hooks must match
    cur = want[0] if want and all(bytes(d[va - V2F:va - V2F + 5]) == want[1](va, orig, lab) for va, orig, lab, _ in hooks) else None
    if not cur: print("ABORT (mixed state)"); return 1
    print("  state:", cur + (" - upgrading v1 -> v2 in place" if cur == "v1" and not a.revert else ""))
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    if a.revert:
        for va, orig, lab, _ in hooks: n[va - V2F:va - V2F + 5] = call_to(va, orig)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for va, orig, lab, _ in hooks: n[va - V2F:va - V2F + 5] = call_to(va, labs[lab])
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aileadsafe2")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
