r"""
AI SITE EXPLORING - LEADER SAFETY v4 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of v1/v2/v3 (same zone,
same five hooks A / B / RA / RB / XS).  Layer on build_ai_sitesearch.py v2.

User (after v3, day-5 tuning): "(A) an AI leader fought a Syron (very strong) in a dungeon with only two Fire Sprites
on turn 3 - a very risky fight.  (B) other AIs are being PASSIVE, not attempting easy exploration sites they used to
clear in early games before."

ROOT CAUSE (both reports) - THE STRENGTH METRIC WAS THE FIRE-DAMAGE BAND
  Every strength the site AI uses (build_ai_sitesearch v2 + leader-safety v1..v3) asks the engine for KIND 0:
  TUnitList.GetStrength(list, dl = 0) 0x55783300 / TAbstractUnit.GetStrength(unit, dl = 0) 0x5577F8F4 /
  TAIGroupControl.GetStrengthMax(gc, dx = 1 = bit 0) 0x557389D4.  A unit's strength for kind k is
  (band[k] + 10) * [unit+0x34]  (band[k] = 0 -> strength 0), where [unit+0x34] = (ATK + 10 + DEF) * (HP + 10) and the
  10 bands [unit+0x28..0x31] are the DAMAGE TYPES its attacks deal (TAbstractUnit strength update 0x5577F75C: for every
  ability, VMT+0xE0 -> value + damage-type mask; TStrikeAbility mask 0x55766DE4: physical bit 7 (0x80) always, plus
  bit 0 for ability 0x0E FIRE STRIKE / 0xA3, bit 1 for 0x0F cold, bit 2 for 0x10 lightning, bit 4 for 0x11 poison, ...).
  So "kind 0" = FIRE damage: only the ~12 unit types with Fire Strike (Fire Sprite, Salamander, Hell Hound, Fire
  Elemental, Red Dragon, Phoenix, ...) have any kind-0 strength; everything else - the Syron (ATK 15, physical only)
  included - counts 0.
  (A) Syron roster -> 0 (v3 rs_eff floors it to 1); the leader (no fire) -> 0; the two Fire Sprites -> 2 x 5525.
      v2 judge: HP ok, 2 escorts, 3 units >= 1, escorts 100 % of 11050 >= 50 %, 11050 >= 4.0 x 1 -> PASS -> search.
      With the real (all-damage-types) metric: Syron 79050 vs leader + sprites ~40000 -> 0.5x -> refused everywhere.
  (B) Most rosters AND most AI groups/stacks are 0.  Before v3 a 0-strength roster was "undefended = free loot,
      priority 100, search unconditionally" (the early-game suicides).  v3's rs_eff floor (>= 1 while the roster holds
      units) turned those sites into "group strength 0 < 1.5 x 1 -> no attraction" for every group without fire units,
      and every leader stack (0 strength) fails the judge (0 >= k x 1 false) -> whole leader groups zeroed -> passive.
  Dungeons are NOT a separate path: TDungeon's ExecuteTE (0x557C61A0) calls the base one (0x557C1D28 -> VMT+0x1FC
  ExecuteSearch -> XS gate) and its defenders are [site+0x34] like every site ([+0x38] is its prisoner list).

v4 CHANGES
  1  ALL-DAMAGE-TYPE METRIC everywhere in the site AI: army / roster / leader / stack strengths use
     TUnitList.GetStrength(mask) 0x55783338 and TAbstractUnit.GetStrength(mask) 0x5577F924 with mask 0xFFFF (the
     engine's own "all kinds" value, [0x558E8044] = 0xFFFF -> (best attack value + 10) * [unit+0x34]); the group
     aggregate uses GetStrengthMax(gc, 0xFFFF) (best per-damage-type group sum).  For a physical attacker this equals
     its physical-band strength, so every comparison is now "real fighting strength vs real fighting strength".
     rs_eff keeps the floor (>= 1 while the roster holds units; empty roster = undefended).
  2  Group attraction no longer zeroes the WHOLE group when the leader's stack fails the judge: the group answers with
     the strength of its OTHER stacks (group - leader stack), judged by the plain v2 ladder (1.5x ...); if the leader
     stack passes, the answer is max(leader-stack bar value, other stacks).  The leader stack itself still cannot
     search unless it passes (hook A + XS), so a group may walk to a site with its leader in tow and let an escort
     stack do the search - the leader then just rejoins.
  3  Judge tuned for the real metric: escorts must carry >= 25 % of the stack (was 50 %: with real numbers a level-1
     leader ~30000 vs ~5500 per level-1 escort needed 6 escorts); HP >= 60 %, >= 2 escorts, units >= roster units,
     search k = 4.0 before day EARLY_DAY (5) / 2.5 after, attraction k = 5.0 / 3.5 (unchanged).
  PROTECT  "leader" (TLeader only, the user's choice) / "heroes" (every THero) as v3; --protect selects.
  Pure synced game state, no RNG -> identical on all MP peers.

Zone AoWEPACK 0x5581E400..0x5581E800 (header "ALS4").  Dry-run default; --apply / --revert / --dis / --dll.
  apply : zero / v1 / v2 / v3 (either protect) / v4 (other protect) -> v4;  revert : -> pre-leader-safety (== v3/v2/v1
  --revert).  v1/v2/v3 scripts refuse a v4 zone.  LIFO: revert THIS (and patch_ai_site_converge_*, whose gate sits in
  cave_execai) before reverting/re-running build_ai_sitesearch.py.  Backup <game>\backup\AoWEPACK.dll.bak_aileadsafe4.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_leader_safety_v1 as V1
import patch_ai_site_leader_safety_v2 as V2
import patch_ai_site_leader_safety_v3 as V3

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = V2.ZONE, V2.ZONE_END
LIST_STRENGTH, GC_STRENGTHMAX = V2.LIST_STRENGTH, V2.GC_STRENGTHMAX
LIST_STRENGTH_M = 0x55783338     # TUnitList.GetStrength(eax = list, dx = damage-type mask)
UNIT_STRENGTH_M = 0x5577F924     # TAbstractUnit.GetStrength(eax = unit, dx = mask)
ALL_KINDS = 0xFFFF               # = [0x558E8044], the engine's "all damage types" mask
GETUNIT, ISCLASS, GETPLAYERS = V2.GETUNIT, V2.ISCLASS, V3.GETPLAYERS
CLS_LEADER, CLS_HERO, CLS_ARMY, MAPCELL, GAME_CELL = V2.CLS_LEADER, V3.CLS_HERO, V2.CLS_ARMY, V2.MAPCELL, V3.GAME_CELL
HOOK_A, HOOK_B, HOOK_RA, HOOK_RB, HOOK_XS = V3.HOOK_A, V3.HOOK_B, V3.HOOK_RA, V3.HOOK_RB, V3.HOOK_XS
XS_BACK, XS_REFUSE = V3.XS_BACK, V3.XS_REFUSE
HP_PCT, MIN_ESC, ESC_PCT, EARLY_DAY = 60, 2, 25, 0    # 10/19 user: early-game window removed (was V2.EARLY_DAY = 5)
K_MINT_EARLY, K_MINT, K_ATT_EARLY, K_ATT = 40, 25, 50, 35        # x10
MAGIC = b"ALS4"

SRC = """
army_eff:                       ; hook A: eax = army on the site; caller ebx = site, edi = roster S (rs_eff)
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, eax
    call ls_all
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

grp_eff:                        ; hook B: eax = TAIGroupControl; caller esi = site, ebp = roster S (rs_eff)
    push ebx
    push esi
    push edi
    push ebp
    sub  esp, 8                 ; [esp] = G (group), [esp+4] = L (leader stack); saved ebp(roster) at [esp+8], esi(site) [esp+0x10]
    mov  esi, eax
    mov  dx, 0x{AK:X}
    call 0x{GC:X}
    mov  [esp], eax
    mov  eax, [esi+0xC]
    test eax, eax
    jz   g_plain
    call find_leader
    test eax, eax
    jz   g_plain
    mov  ebx, eax
    mov  eax, [ebx+4]
    test eax, eax
    jz   g_loose
    push eax
    call g_pic
g_pic:
    pop  edx
    mov  edx, dword ptr [edx + 0x33333333]
    call 0x{IC:X}
    pop  esi
    test al, al
    jz   g_loose
    mov  eax, esi
    call ls_all
    mov  [esp+4], eax
    mov  edi, eax
    mov  ecx, [esp+0x10]
    mov  edx, [esp+8]
    mov  eax, 1
    call judge
    test eax, eax
    jz   g_rest
    mov  eax, [esp+4]
    imul eax, eax, 15
    xor  edx, edx
    div  ecx
    mov  ecx, eax               ; leader-stack bar value
    call g_other
    cmp  eax, ecx
    jge  g_out
    mov  eax, ecx
    jmp  g_out
g_loose:                        ; leader not in a TArmy (garrison / transit): his own strength is the "leader stack"
    mov  eax, ebx
    mov  dx, 0x{AK:X}
    call 0x{US:X}
    mov  [esp+4], eax
g_rest:
    call g_other
    jmp  g_out
g_plain:
    mov  eax, [esp]
g_out:
    add  esp, 8
    jmp  fin
g_other:                        ; eax = max(0, G - L)   (frame: [esp+4] = G, [esp+8] = L after the call)
    mov  eax, [esp+4]
    sub  eax, [esp+8]
    jge  go_ok
    xor  eax, eax
go_ok:
    ret

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
    imul eax, eax, {HP}
    imul ebp, ebp, 100
    cmp  ebp, eax
    jl   j_fail
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  ebp, eax
    cmp  ebp, {ME1}
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
    mov  dx, 0x{AK:X}
    call 0x{US:X}
    mov  edx, edi
    sub  edx, eax
    jge  j_e1
    xor  edx, edx
j_e1:
    imul edx, edx, 100
    imul eax, edi, {EP}
    cmp  edx, eax
    jl   j_fail
    mov  eax, [esp]
    test eax, eax
    jnz  j_att
    mov  ecx, {KM}
    mov  edx, {KME}
    jmp  j_day
j_att:
    mov  ecx, {KA}
    mov  edx, {KAE}
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
    cmp  dword ptr [ebp+0x174], {ED}
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

find_leader:                    ; eax = TUnitList -> eax = first protected unit in it, or 0.  saves ebx/esi/edi/ebp
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
    call 0x{GU:X}
    test eax, eax
    jz   fl_nx
    push eax
    mov  edx, ebp
    call 0x{IC:X}
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

ls_all:                         ; eax = TUnitList -> real fighting strength (best damage type per unit, summed)
    mov  dx, 0x{AK:X}
    jmp  0x{LM:X}

rs_eff:                         ; hooks RA/RB: eax = roster TUnitList -> ls_all, but >= 1 while the list holds units
    push esi
    mov  esi, eax
    call ls_all
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
    call rs_eff
    test eax, eax
    jz   xs_pass
    mov  ebp, eax
    mov  eax, edi
    call find_leader
    test eax, eax
    jz   xs_pass
    mov  ebx, eax
    mov  eax, edi
    call ls_all
    mov  esi, edi
    mov  edi, eax
    mov  ecx, [esp+0x10]
    mov  edx, ebp
    xor  eax, eax
    call judge
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

PH = {0x11111111: (None, 0x5D), 0x22222222: (MAPCELL, 0x5D), 0x33333333: (CLS_ARMY, 0x5A), 0x44444444: (GAME_CELL, 0x58)}


def build(protect="leader"):
    src = SRC.format(AK=ALL_KINDS, GC=GC_STRENGTHMAX, IC=ISCLASS, US=UNIT_STRENGTH_M, LM=LIST_STRENGTH_M, GU=GETUNIT,
                     GP=GETPLAYERS, XB=XS_BACK, XR=XS_REFUSE, HP=HP_PCT, ME1=MIN_ESC + 1, EP=ESC_PCT,
                     KM=K_MINT, KME=K_MINT_EARLY, KA=K_ATT, KAE=K_ATT_EARLY, ED=EARLY_DAY)
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    org = ZONE + 4
    LBL = ("army_eff", "grp_eff", "judge", "find_leader", "ls_all", "rs_eff", "xs_gate")
    full = src + "\n" + "\n".join("    .long " + n for n in LBL)     # label table appended, then stripped
    code = bytearray(Ks(KS_ARCH_X86, KS_MODE_32).asm(full, org)[0])
    tab = code[-4 * len(LBL):]; del code[-4 * len(LBL):]
    labs = {n: struct.unpack_from("<I", tab, 4 * k)[0] for k, n in enumerate(LBL)}
    cls = CLS_HERO if protect == "heroes" else CLS_LEADER
    for ph, (tgt, popreg) in PH.items():
        tgt = cls if tgt is None else tgt
        p = struct.pack("<I", ph)
        j = code.find(p); assert j > 0 and code.count(p) == 1, hex(ph)
        k = code.rfind(b"\xe8\x00\x00\x00\x00" + bytes([popreg]), 0, j); assert 0 <= k and j - k < 12, hex(ph)
        code[j:j + 4] = struct.pack("<i", tgt - (org + k + 5))
    zone = MAGIC + bytes(code)
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, labs


def call_to(site, tgt):
    return b"\xe8" + struct.pack("<i", tgt - (site + 5))


def jmp_to(site, tgt, n):
    return b"\xe9" + struct.pack("<i", tgt - (site + 5)) + b"\x90" * (n - 5)


def site_bytes(labs):
    return {HOOK_A: call_to(HOOK_A, labs["army_eff"]), HOOK_B: call_to(HOOK_B, labs["grp_eff"]),
            HOOK_RA: call_to(HOOK_RA, labs["rs_eff"]), HOOK_RB: call_to(HOOK_RB, labs["rs_eff"]),
            HOOK_XS: jmp_to(HOOK_XS, labs["xs_gate"], 6)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    ap.add_argument("--protect", choices=("heroes", "leader"), default="leader"); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    other = "heroes" if a.protect == "leader" else "leader"
    zone, labs = build(a.protect); ozone, olabs = build(other)
    z1, l1 = V1.build(); z2, l2 = V2.build()
    z3l, l3l = V3.build("leader"); z3h, l3h = V3.build("heroes")
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zl = rd(ZONE, ZONE_END - ZONE)
    def zis(z): return zl[:len(z)] == z and not any(zl[len(z):])
    vanilla = V3.site_bytes()
    states = {"zero": (None, vanilla),
              "v1": (z1, {**vanilla, HOOK_A: call_to(HOOK_A, l1["army_eff"]), HOOK_B: call_to(HOOK_B, l1["grp_eff"])}),
              "v2": (z2, {**vanilla, HOOK_A: call_to(HOOK_A, l2["army_eff"]), HOOK_B: call_to(HOOK_B, l2["grp_eff"])}),
              "v3-leader": (z3l, V3.site_bytes(l3l)), "v3-heroes": (z3h, V3.site_bytes(l3h)),
              "v4": (zone, site_bytes(labs)), "v4-other": (ozone, site_bytes(olabs))}
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
    print("  zone %#x..%#x %s (v4 %d B, protect=%s; %s) | relocs %s"
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
    print("  state:", zstate + ("" if a.revert or zstate == "v4" else " - upgrading %s -> v4 in place" % zstate))
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    tgt = vanilla if a.revert else site_bytes(labs)
    if not a.revert: n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    for va in allh: n[va - V2F:va - V2F + len(tgt[va])] = tgt[va]
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aileadsafe4")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
