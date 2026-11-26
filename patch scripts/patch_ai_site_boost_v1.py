r"""
AI SITE EXPLORING - STRONG-GROUP BOOST v1 (2026-10-20).  AoWEPACK.dll only.  Layer on build_ai_sitesearch v2 +
ai-site-leader-safety v6 + ai-site-recruit v3 (+ ai-itemloot reach v1 for the travel refund).

User: "most AI made good decisions, but a couple of times a group much stronger than a nearby site (within 3 turns)
didn't go.  Leave everything as is, but ADD: leaderless stacks at >= 2.5x combat strength and leader stacks at >= 3x
get a priority increase for moving towards exploration sites within 12 hexes and attempting them."

WHY STRONG GROUPS IGNORED NEAR SITES (static RE):
  * The site answer (cave_msgproc ladder) is only 30 (2x..3x), 45 (3x..5x), 75 (5x..10x), 100 (>= 10x).
  * TAIGroupTargetSelector.Score 0x5573C57C: score = priority - 25 * ((pathcost-1) div groupMP) + 75 for the group's
    CURRENT (committed) target, -50 if another own group already heads there.  So a 3x group 2-3 turns from a site
    scores 45 - 50 = -5, and any committed target (even a weak one at 15 + 75 = 90) keeps the group locked.
    reach_v1 refunds the per-turn penalty only for ITEM answers.
FIX (answers only - every existing rule/threshold is untouched):
  hook H 0x55814B13 = cave_msgproc's _comb (6 B `cmp [ebx],eax / jge / mov [ebx],eax`; every site answer - ladder,
  recruit-15, undefended-100 - converges here; ebx = answer rec, esi = site, edi = msg, ebp = roster strength) ->
  cave BST: if the site has a defender roster (ebp > 0) and
     LEADERLESS group (no leader in [gc+0xC]):  group strength G (GC.GetStrengthMax, all kinds) >= 2.5 x roster AND
        some unit of the group stands within 12 hexes of the site (same level, engine hex distance), or
     LEADER group: leader stack L (his TArmy, else the leader alone; all kinds) >= 3.0 x roster AND leader HP >= 75 %
        (leader-safety v6 judge, mode 2) AND the leader is within 12 hexes,
  -> answer = max(answer, BOOST = 125), and the answer is marked in reach_v1's G slot (0x5590BFE0 = {rec, prio, group})
     so reach_v1's RC refunds the selector's -25/turn travel penalty for 1..3 turns.
  BOOST 125 = beats a committed mid target (<= 45 + 75 = 120) and the undefended-site draw (100), stays below a
     committed undefended site (175) and enemy-city attack answers (300).
  The leader-group test uses the leader STACK (a group whose leader stack fails is not boosted; leader-safety v6's
  give-up cooldown already answers 0 before this point, so a given-up site stays at 0 - max() never lifts a refusal
  because the cave only runs on the answer path).
SEARCH side: leaderless >= 2.5x is above converge v4's wait band (>= 2.0x searches at once).  Leader >= 3x was inside
the 1.5..4.0x one-turn wait band -> patch_ai_site_converge_v5.py lowers the leader "search now" bar 4.0x -> 3.0x.

Zone AoWEPACK 0x5581C800..0x5581D000 (header 'SBB1' + the 6 original bytes), verified zero / reloc-free.  PIC: call/pop
deltas for G and the TArmy class cell; rel32 calls into leader-safety v6 (find_leader / ls_all / judge - the script
checks the ALS6 zone and resolves the labels from patch_ai_site_leader_safety_v6.build).  Pure synced game state,
no RNG -> identical on all MP peers.
Dry-run default; --apply / --revert / --dis / --dll.  Backup .bak_aisiteboost.  LIFO: revert this BEFORE
leader-safety v6 / recruit v3 / reach v1 / build_ai_sitesearch.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_leader_safety_v2 as V2
import patch_ai_site_leader_safety_v6 as V6

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581C800, 0x5581D000
CODE = ZONE + 0x10
MAGIC = b"SBB1"
HOOK, HOOK_LEN, HOOK_ORIG, HOOK_BACK = 0x55814B13, 6, bytes.fromhex("39037d028903"), 0x55814B19
G_SLOT = 0x5590BFE0
GC_STRENGTHMAX = 0x557389D4
UNIT_STRENGTH_M = 0x5577F924
ALL_KINDS = 0xFFFF
GETUNIT, ISCLASS, CLS_ARMY = V2.GETUNIT, V2.ISCLASS, V2.CLS_ARMY
GETLOC, HXRAD = 0x5577ED94, 0x5570266C
BOOST = 125
RADIUS = 12
K_LEADERLESS2 = 5        # 2 x G >= 5 x R   (2.5x)
K_LEADER = 3             # L >= 3 x R       (3.0x)

ASM = """
bst:
    push 0
    pushad
    sub  esp, 0x10
    mov  esi, [esp+0x14]
    mov  edi, [esp+0x10]
    mov  eax, [esi+0x34]
    test eax, eax
    jz   b_out
    cmp  dword ptr [esp+0x18], 0
    jle  b_out
    mov  ebx, [edi+0x10]
    test ebx, ebx
    jz   b_out
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movzx eax, al
    mov  [esp], eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movzx eax, al
    mov  [esp+4], eax
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movzx eax, al
    mov  [esp+8], eax
    mov  eax, [ebx+0xC]
    test eax, eax
    jz   b_out
    mov  ebp, eax
    call FINDL
    test eax, eax
    jnz  b_lead
    mov  eax, ebx
    mov  dx, AKV
    call GCSM
    add  eax, eax
    mov  ecx, [esp+0x18]
    imul ecx, ecx, KLL
    cmp  eax, ecx
    jl   b_out
    mov  eax, ebp
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  edi, eax
    xor  esi, esi
b_ul:
    cmp  esi, edi
    jge  b_out
    mov  edx, esi
    mov  eax, ebp
    call GETU
    inc  esi
    test eax, eax
    jz   b_ul
    call near
    test eax, eax
    jz   b_ul
    jmp  b_yes
b_lead:
    mov  ebx, eax
    mov  eax, [ebx+4]
    test eax, eax
    jz   b_loose
    mov  esi, eax
    call b_pa
b_pa:
    pop  edx
    mov  edx, dword ptr [edx + 0x33333333]
    call ISC
    test al, al
    jz   b_loose
    mov  eax, esi
    call LSALL
    jmp  b_l2
b_loose:
    mov  esi, ebx
    mov  eax, ebx
    mov  dx, AKV
    call USM
b_l2:
    mov  edi, eax
    mov  ecx, [esp+0x18]
    imul ecx, ecx, KLD
    cmp  edi, ecx
    jl   b_out
    mov  ecx, [esp+0x14]
    mov  edx, [esp+0x18]
    mov  eax, 2
    call JUDGE
    test eax, eax
    jz   b_out
    mov  eax, ebx
    call near
    test eax, eax
    jz   b_out
b_yes:
    cmp  dword ptr [esp+0x2C], BOOSTV
    jge  b_flag
    mov  dword ptr [esp+0x2C], BOOSTV
b_flag:
    mov  dword ptr [esp+0x30], 1
b_out:
    add  esp, 0x10
    popad
    pop  ecx
    cmp  dword ptr [ebx], eax
    jge  b_done
    mov  dword ptr [ebx], eax
    test ecx, ecx
    jz   b_done
    push edx
    call b_pg
b_pg:
    pop  edx
    add  edx, 0x11111111
    mov  [edx], ebx
    mov  [edx+4], eax
    mov  ecx, [edi+0x10]
    mov  ecx, [ecx+0xC]
    mov  [edx+8], ecx
    pop  edx
b_done:
    jmp  BACK

near:
    push ebx
    sub  esp, 4
    mov  dword ptr [esp], 0
    lea  edx, [esp+2]
    push edx
    lea  ecx, [esp+5]
    lea  edx, [esp+4]
    call GLOC
    movsx eax, byte ptr [esp+2]
    cmp  eax, [esp+0x14]
    jne  n_no
    movsx eax, byte ptr [esp+1]
    push eax
    movsx ecx, byte ptr [esp+4]
    mov  edx, [esp+0x14]
    mov  eax, [esp+0x10]
    call HXR
    cmp  eax, RADV
    jg   n_no
    mov  eax, 1
    jmp  n_out
n_no:
    xor  eax, eax
n_out:
    add  esp, 4
    pop  ebx
    ret
"""
LBL = ("bst", "b_pa", "b_pg", "near")


def ls6_labels():
    return V6.build("leader")[1]


def build():
    L = ls6_labels()
    src = ASM
    for k, v in (("FINDL", L["find_leader"]), ("LSALL", L["ls_all"]), ("JUDGE", L["judge"]), ("GCSM", GC_STRENGTHMAX),
                 ("USM", UNIT_STRENGTH_M), ("GETU", GETUNIT), ("ISC", ISCLASS), ("GLOC", GETLOC), ("HXR", HXRAD),
                 ("BACK", HOOK_BACK)):
        src = src.replace(k, "0x%X" % v)
    src = (src.replace("AKV", "0x%X" % ALL_KINDS).replace("BOOSTV", str(BOOST)).replace("RADV", str(RADIUS))
           .replace("KLL", str(K_LEADERLESS2)).replace("KLD", str(K_LEADER)))
    full = src + "\n" + "\n".join("    .long " + n for n in LBL)
    code = bytearray(Ks(KS_ARCH_X86, KS_MODE_32).asm(full, CODE)[0])
    tab = code[-4 * len(LBL):]; del code[-4 * len(LBL):]
    labs = {n: struct.unpack_from("<I", tab, 4 * k)[0] for k, n in enumerate(LBL)}
    for ph, tgt, lab, kind in ((0x33333333, CLS_ARMY, "b_pa", "mov"), (0x11111111, G_SLOT, "b_pg", "add")):
        p = struct.pack("<I", ph); j = code.find(p); assert j > 0 and code.count(p) == 1, hex(ph)
        code[j:j + 4] = struct.pack("<i", tgt - labs[lab])
    zone = MAGIC + HOOK_ORIG + bytes(0x10 - 4 - len(HOOK_ORIG)) + bytes(code)
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    site = b"\xe9" + struct.pack("<i", labs["bst"] - (HOOK + 5)) + b"\x90"
    assert len(site) == HOOK_LEN
    return zone, site, labs


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, labs = build()
    rd = lambda lo, n: bytes(d[lo - V2F:lo - V2F + n])
    zl = rd(ZONE, ZONE_END - ZONE)
    zst = "zero" if not any(zl) else ("v1" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS")
    hb = rd(HOOK, HOOK_LEN)
    hst = "original" if hb == HOOK_ORIG else "v1" if hb == site else "FOREIGN"
    ls = rd(V6.ZONE, 4)
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or HOOK - 3 <= r < HOOK + HOOK_LEN]
    print("AoWEPACK site-answer hook %#x %s | zone %#x %s (%d B, bst %#x near %#x) | leader-safety %s | relocs %s"
          % (HOOK, hst, ZONE, zst, len(zone), labs["bst"], labs["near"], ls, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], CODE):
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (reloc under the hook or the zone)"); return 1
    if hst == "FOREIGN" or zst == "DIFFERS": print("ABORT (hook/zone foreign)"); return 1
    if (hst, zst) not in (("original", "zero"), ("v1", "v1")): print("ABORT (mixed state)"); return 1
    if not a.revert and ls != b"ALS6":
        print("ABORT (ai-site-leader-safety v6 not applied - its find_leader/ls_all/judge are called)"); return 1
    n = bytearray(d)
    if a.revert:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); n[HOOK - V2F:HOOK - V2F + HOOK_LEN] = HOOK_ORIG
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[HOOK - V2F:HOOK - V2F + HOOK_LEN] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aisiteboost")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
