r"""
AI SITE SEARCH - STACK GATE v4 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of patch_ai_site_converge_v1/v2/v3
(same gate site 0x558147DC inside build_ai_sitesearch's cave_execai).  The cave MOVES to 0x55817000..0x55817400
(v3's zone 0x5581F530..0x5581F800 was too small; v1/v2/v3 zones are zeroed on upgrade).
REQUIRES ai-site-leader-safety v6 ('ALS6'): its army_eff (hook A, the instruction right before this gate) returns
eax = strength of the stack on the site and edx = 0x4C454144 when that stack holds the leader (HP >= 75 %).

Gate input: S = stack on the site, R = exact site roster (both all-damage-type strength), ebx = site, esi = player.

LEADERLESS stacks (user, final):
   S <  1.0R                           -> never fights (holds; its group keeps the site as target, recruit gathers)
   S >= 2.0R                           -> search now
   1.0R .. 2.0R, own army (not in a city) within 6 hexes -> wait ONE turn (table A), then search
   1.0R .. 2.0R, no friend nearby      -> search now
LEADER stacks (fight still needs 2.0R; the XS choke gate in leader-safety v6 enforces it too):
   S >= 4.0R                           -> search now
   leader gave this site up < 3 days ago (table B state 2) -> search only if S >= 2.0R, else skip (no restamp)
   no own army within 6 hexes          -> S >= 2.0R search, else GIVE UP
   friend within 6 hexes:  S < 0.75R   -> GIVE UP
                           0.75R..1.5R -> wait up to TWO turns (table B state 1), then S >= 2.0R search else GIVE UP
                           1.5R..4.0R  -> wait up to ONE turn, then S >= 2.0R search else GIVE UP
   GIVE UP = table B slot := {site | 2<<24, today} and skip; leader-safety v6's grp_eff then answers 0 for that site
   for the leader's group for 3 days (no parking), after which it may be re-attracted (1.75x).
Wait tables (16 slots, {key = x | y<<8 | level<<16 | state<<24, day}, slot = (x + 3y + 5*level) & 15):
   A = 0x5590BC80..0x5590BD00 (leaderless, as v3)  B = 0x5590B510..0x5590B590 (leader; shared with leader-safety v6)
   Wait rule (N turns): same key and 0 <= day - stamp < N -> hold; = N -> decide; anything else -> stamp today, hold.
   AoWEPACK .idata page slack beyond raw data -> zero at load; only synced game state + day -> MP-identical; a reload
   mid-wait restarts that wait.
Field scan as v1/v3 (grid 0x557020EC, field 0x557020DC, army HS 0x55771EB0, owner [[hs+0x1C]+0x12], city 0x20108).

Zone AoWEPACK 0x55817000..0x55817400 (header 'CNV4' + the 10 original gate bytes).
Dry-run default; --apply / --revert / --dis / --dll.  apply : vanilla / v1 / v2 / v3 -> v4 (refuses unless
leader-safety v6 is applied);  revert : -> original gate bytes, all zones zero (== v1/v2/v3 --revert).
LIFO: revert this FIRST (before leader-safety v6 / build_ai_sitesearch).  v1..v3 scripts refuse a v4 install.
Backup <game>\backup\AoWEPACK.dll.bak_aiconverge4.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_converge_v1 as C1
import patch_ai_site_converge_v2 as C2
import patch_ai_site_converge_v3 as C3

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55817000, 0x55817400   # free run (ml_cost cave ends 0x55817000)
CODE = ZONE + 0x10
SITE, SITE_LEN, ORIG = C1.SITE, C1.SITE_LEN, C1.ORIG
SKIP, MINT, MAPHOLD = C1.SKIP, C1.MINT, C1.MAPHOLD
TABLE_A, TABLE_B = 0x5590BC80, 0x5590B510
R = 6
COOL = 3
LEAD_MAGIC = 0x4C454144
LS_ZONE, LS_MAGIC = 0x5581E400, b"ALS6"
MAGIC = b"CNV4"

ASM = """
maph:
    call p1
p1: pop eax
    add eax, 0x11111111
    mov eax, [eax]
    ret
tbla:
    call p2
p2: pop eax
    add eax, 0x22222222
    ret
tblb:
    call p3
p3: pop eax
    add eax, 0x33333333
    ret
gate:
    push ebp
    sub  esp, 0x20
    mov  [esp+0x10], eax
    mov  [esp+0x18], edx
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movzx eax, al
    mov  [esp], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movzx eax, al
    mov  [esp+4], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movzx eax, al
    mov  [esp+8], eax
    shl  eax, 16
    mov  edx, [esp+4]
    shl  edx, 8
    or   eax, edx
    or   eax, [esp]
    mov  [esp+0xC], eax
    mov  eax, [esp+0x10]
    cmp  dword ptr [esp+0x18], LEADM
    je   lead
    cmp  eax, edi
    jl   do_skip
    lea  ecx, [edi+edi]
    cmp  eax, ecx
    jge  do_mint
    mov  eax, esp
    call friend
    test eax, eax
    jz   do_mint
    mov  eax, [esp+0xC]
    or   eax, 0x1000000
    mov  [esp+0x14], eax
    call tbla
    mov  ecx, eax
    mov  eax, esp
    mov  edx, 1
    call waitn
    test eax, eax
    jz   do_skip
    jmp  do_mint
lead:
    lea  ecx, [edi*4]
    cmp  eax, ecx
    jge  do_mint
    mov  eax, esp
    call incool
    test eax, eax
    jnz  l_cool
    mov  eax, esp
    call friend
    test eax, eax
    jz   l_decide
    mov  eax, [esp+0x10]
    lea  ecx, [eax*4]
    lea  edx, [edi+edi*2]
    cmp  ecx, edx
    jl   l_give
    lea  ecx, [eax+eax]
    cmp  ecx, edx
    jl   l_band2
    mov  edx, 1
    jmp  l_wait
l_band2:
    mov  edx, 2
l_wait:
    push edx
    mov  eax, [esp+0x10]
    or   eax, 0x1000000
    mov  [esp+0x18], eax
    call tblb
    mov  ecx, eax
    pop  edx
    mov  eax, esp
    call waitn
    test eax, eax
    jz   do_skip
l_decide:
    mov  eax, [esp+0x10]
    lea  ecx, [edi+edi]
    cmp  eax, ecx
    jge  do_mint
l_give:
    mov  eax, esp
    call giveup
    jmp  do_skip
l_cool:
    mov  eax, [esp+0x10]
    lea  ecx, [edi+edi]
    cmp  eax, ecx
    jge  do_mint
do_skip:
    add  esp, 0x20
    pop  ebp
    jmp  SKIPA
do_mint:
    add  esp, 0x20
    pop  ebp
    jmp  MINTA

slot:
    mov  ecx, [eax+4]
    lea  ecx, [ecx+ecx*2]
    add  ecx, [eax]
    mov  edx, [eax+8]
    lea  edx, [edx+edx*4]
    add  ecx, edx
    and  ecx, 15
    ret

waitn:
    push ebx
    push esi
    push ebp
    mov  ebx, eax
    mov  esi, ecx
    mov  ebp, edx
    call slot
    lea  esi, [esi+ecx*8]
    call maph
    mov  eax, [eax]
    test eax, eax
    jz   w_hold
    mov  edx, [eax+0x174]
    mov  eax, [ebx+0x14]
    cmp  [esi], eax
    jne  w_new
    mov  eax, edx
    sub  eax, [esi+4]
    jl   w_new
    cmp  eax, ebp
    jl   w_hold
    je   w_dec
w_new:
    mov  eax, [ebx+0x14]
    mov  [esi], eax
    mov  [esi+4], edx
w_hold:
    xor  eax, eax
    jmp  w_out
w_dec:
    mov  eax, 1
w_out:
    pop  ebp
    pop  esi
    pop  ebx
    ret

giveup:
    push ebx
    push esi
    mov  ebx, eax
    call slot
    push ecx
    call tblb
    pop  ecx
    lea  esi, [eax+ecx*8]
    call maph
    mov  eax, [eax]
    test eax, eax
    jz   gu_out
    mov  edx, [eax+0x174]
    mov  eax, [ebx+0xC]
    or   eax, 0x2000000
    mov  [esi], eax
    mov  [esi+4], edx
gu_out:
    pop  esi
    pop  ebx
    ret

incool:
    push ebx
    push esi
    mov  ebx, eax
    call slot
    push ecx
    call tblb
    pop  ecx
    lea  esi, [eax+ecx*8]
    mov  eax, [ebx+0xC]
    or   eax, 0x2000000
    cmp  [esi], eax
    jne  ic_no
    call maph
    mov  eax, [eax]
    test eax, eax
    jz   ic_no
    mov  eax, [eax+0x174]
    sub  eax, [esi+4]
    jl   ic_no
    cmp  eax, COOLN
    jge  ic_no
    mov  eax, 1
    jmp  ic_out
ic_no:
    xor  eax, eax
ic_out:
    pop  esi
    pop  ebx
    ret

friend:
    push ebx
    push edi
    push ebp
    sub  esp, 8
    mov  ebx, eax
    call maph
    mov  eax, [eax]
    test eax, eax
    jz   f_no
    mov  eax, [eax+0x10]
    mov  edx, [ebx+8]
    call 0x557020EC
    test eax, eax
    jz   f_no
    mov  [esp], eax
    mov  edi, -RR
fy: mov  ebp, -RR
fx: mov  eax, ebp
    or   eax, edi
    jz   fnx
    mov  edx, [ebx]
    add  edx, ebp
    js   fnx
    mov  ecx, [esp]
    cmp  edx, [ecx+0xc]
    jge  fnx
    mov  ecx, [ebx+4]
    add  ecx, edi
    js   fnx
    mov  eax, [esp]
    cmp  ecx, [eax+0x10]
    jge  fnx
    call 0x557020DC
    test eax, eax
    jz   fnx
    mov  [esp+4], eax
    call 0x55771EB0
    test eax, eax
    jz   fnx
    mov  eax, [eax+0x1c]
    test eax, eax
    jz   fnx
    mov  ecx, esi
    cmp  byte ptr [eax+0x12], cl
    jne  fnx
    mov  eax, [esp+4]
    mov  edx, 0x20108
    mov  ecx, [eax]
    call dword ptr [ecx+0x80]
    test eax, eax
    jz   f_yes
fnx:
    inc  ebp
    cmp  ebp, RR
    jle  fx
    inc  edi
    cmp  edi, RR
    jle  fy
f_no:
    xor  eax, eax
    jmp  f_out
f_yes:
    mov  eax, 1
f_out:
    add  esp, 8
    pop  ebp
    pop  edi
    pop  ebx
    ret
"""

LBL = ("p1", "p2", "p3", "gate")


def _asm(src):
    full = src + "\n" + "\n".join("    .long " + n for n in LBL)
    code = bytearray(Ks(KS_ARCH_X86, KS_MODE_32).asm(full, CODE)[0])
    tab = code[-4 * len(LBL):]; del code[-4 * len(LBL):]
    return code, {n: struct.unpack_from("<I", tab, 4 * k)[0] for k, n in enumerate(LBL)}


def build():
    src = (ASM.replace("LEADM", "0x%X" % LEAD_MAGIC).replace("SKIPA", "0x%X" % SKIP).replace("MINTA", "0x%X" % MINT)
           .replace("COOLN", str(COOL)).replace("RR", str(R)))
    code, labs = _asm(src)
    for ph, tgt, lab in ((0x11111111, MAPHOLD, "p1"), (0x22222222, TABLE_A, "p2"), (0x33333333, TABLE_B, "p3")):
        p = struct.pack("<I", ph); j = code.find(p); assert j > 0 and code.count(p) == 1, hex(ph)
        code[j:j + 4] = struct.pack("<i", tgt - labs[lab])
    zone = MAGIC + ORIG + bytes(0x10 - 4 - len(ORIG)) + bytes(code)
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    gate = labs["gate"]
    site = b"\xe9" + struct.pack("<i", gate - (SITE + 5)) + b"\x90" * 5
    assert len(site) == SITE_LEN
    return zone, site, gate


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, gate = build()
    z1, s1, _g1 = C1.build(); z2, s2, _g2 = C2.build(); z3, s3, _g3 = C3.build()
    rd = lambda lo, hi: bytes(d[lo - V2F:hi - V2F])
    zl, zl3, zl2, zl1 = rd(ZONE, ZONE_END), rd(C3.ZONE, C3.ZONE_END), rd(C2.ZONE, C2.ZONE_END), rd(C1.ZONE, C1.ZONE_END)
    sb = rd(SITE, SITE + SITE_LEN)
    sstate = ("vanilla" if sb == ORIG else "v4" if sb == site else "v3" if sb == s3 else "v2" if sb == s2
              else "v1" if sb == s1 else "FOREIGN")
    def zst(b, z, nm): return nm if b[:len(z)] == z and not any(b[len(z):]) else None
    z4s = "zero" if not any(zl) else (zst(zl, zone, "v4") or "DIFFERS")
    z3s = "zero" if not any(zl3) else (zst(zl3, z3, "v3") or "DIFFERS")
    z2s = "zero" if not any(zl2) else (zst(zl2, z2, "v2") or "DIFFERS")
    z1s = "zero" if not any(zl1) else (zst(zl1, z1, "v1") or "DIFFERS")
    ls = rd(LS_ZONE, LS_ZONE + 4)
    bad = [hex(r) for r in relocs(bytes(d), BASE)
           if any(lo - 3 <= r < hi for lo, hi in ((ZONE, ZONE_END), (C3.ZONE, C3.ZONE_END), (C2.ZONE, C2.ZONE_END),
                                                    (C1.ZONE, C1.ZONE_END), (SITE, SITE + SITE_LEN)))]
    print("AoWEPACK site-search gate %#x %s | zone %#x %s (v4 %d B, gate %#x) | v2 zone %s | v1 zone %s | "
          "v3 zone %s | tables A %#x B %#x | leader-safety %s | relocs %s"
          % (SITE, sstate, ZONE, z4s, len(zone), gate, z2s, z1s, z3s, TABLE_A, TABLE_B, ls, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], CODE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if "DIFFERS" in (z4s, z3s, z2s, z1s): print("ABORT (zone not free / foreign)"); return 1
    ok = {("vanilla", "zero", "zero", "zero", "zero"), ("v1", "zero", "zero", "zero", "v1"),
          ("v2", "zero", "zero", "v2", "zero"), ("v3", "zero", "v3", "zero", "zero"), ("v4", "v4", "zero", "zero", "zero")}
    if (sstate, z4s, z3s, z2s, z1s) not in ok: print("ABORT (mixed state)"); return 1
    if not a.revert and ls != LS_MAGIC:
        print("ABORT (ai-site-leader-safety v6 not applied - apply patch_ai_site_leader_safety_v6.py first)"); return 1
    print("  state:", sstate + (" - upgrading %s -> v4 in place" % sstate if sstate in ("v1", "v2", "v3") and not a.revert else ""))
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
        bak = bak_path(a.dll, ".bak_aiconverge4")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
