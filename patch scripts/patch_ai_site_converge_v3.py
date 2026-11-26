r"""
AI SITE SEARCH - LEADERLESS STACK RULES v3 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of
patch_ai_site_converge_v1 / v2 (same gate site 0x558147DC; the cave MOVES to 0x5581F530).

User ("AI too passive about attempting exploration sites"): leaderless stacks head to a site AND start the fight at
1.25x the defenders; between 1.0x and 1.5x with a friendly army within 4 hexes wait one turn for it to merge; between
0.5x and 1.0x with a friendly army within 6 hexes wait two turns (keep the gathering, target 1.25x).

GATE (S_army = army standing ON the site through leader-safety's wrapper - 0 for a leader stack that fails the
leader rules; S_def = exact roster):
   4*S_army <  5*S_def   (< 1.25x)     -> skip.  The stack never starts a fight below 1.25x, so the "wait" bands
                                          0.5x..1.0x (friend <= 6 hexes) and 1.0x..1.25x (friend <= 4) are holds by
                                          construction: the stack does not search and its group keeps the site as its
                                          target (attraction >= 1.25x, recruit tags 1.25x), so friends converge and
                                          merge; once the merged stack reaches 1.25x the rules below apply.
   2*S_army >= 3*S_def   (>= 1.5x)     -> search now.
   1.25x .. 1.5x: an own army (not inside a city) within |dx|,|dy| <= 4 on the site's level -> WAIT ONE TURN, then
                  search; no friend -> search now.
WAIT CAP (deterministic, replaces v2's day parity): a 16-slot table {key = x | y<<8 | level<<16 | 1<<24, first-wait
  day} at AoWEPACK .idata page slack 0x5590BC80..0x5590BD00 (beyond raw data -> zero at load; smokescreen's band buffer
  ends 0x5590BC80, essence starts 0x5590BD00), slot = (x + 3y + 5*level) & 15.  Same key and same day -> wait; same key
  and day = first + 1 -> search; anything else (new site, collision, stale stamp) -> stamp today, wait.  Day =
  [[0x558E9494]]+0x174.  Only synced game state feeds it and every peer starts with an empty table (new game / load)
  -> MP-identical; a reload mid-wait merely restarts that one-turn wait.
Field scan exactly as v1 (grid 0x557020EC, field 0x557020DC, army HS 0x55771EB0, owner byte [[hs+0x1C]+0x12],
city test GetObjectOfType 0x20108).

Zone AoWEPACK 0x5581F530..0x5581F800 (header 'CNV3' + the 10 original gate bytes); v2's zone 0x5581C6C0..0x5581C800 and
v1's 0x5581C100..0x5581C220 are zeroed on upgrade.  Dry-run default; --apply / --revert / --dis / --dll.
  apply : vanilla / v1 / v2 -> v3;  revert : -> original gate bytes, all three zones zero (== v1/v2 --revert).
LIFO: revert this before ai-site-leader-safety / build_ai_sitesearch (its gate site sits in their cave).
v1/v2 scripts refuse a v3 install (gate points elsewhere -> FOREIGN).  Backup <game>\backup\AoWEPACK.dll.bak_aiconverge3.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_converge_v1 as C1
import patch_ai_site_converge_v2 as C2

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581F530, 0x5581F800
CODE = ZONE + 0x10
SITE, SITE_LEN, ORIG = C1.SITE, C1.SITE_LEN, C1.ORIG
SKIP, MINT, MAPHOLD = C1.SKIP, C1.MINT, C1.MAPHOLD
TABLE, NSLOT = 0x5590BC80, 16
R = 6    # 10/19 user: wait radius 4 -> 6 hexes
MAGIC = b"CNV3"

ASM = """
    call p1
p1: pop eax
    add eax, %(K)d
    mov eax, [eax]
    ret
tbl:
    call p2
p2: pop eax
    add eax, %(KT)d
    ret
gate:
    lea ecx, [eax*4]
    lea edx, [edi+edi*4]
    cmp ecx, edx
    jl  skip
    lea ecx, [eax+eax]
    lea edx, [edi+edi*2]
    cmp ecx, edx
    jge mint
    push ebp
    sub esp, 0x18
    mov eax, ebx
    mov edx, [eax]
    call dword ptr [edx+0x74]
    movzx eax, al
    mov [esp], eax
    mov eax, ebx
    mov edx, [eax]
    call dword ptr [edx+0x78]
    movzx eax, al
    mov [esp+4], eax
    mov eax, ebx
    mov edx, [eax]
    call dword ptr [edx+0x7c]
    movzx eax, al
    mov [esp+8], eax
    call %(CODE)d
    mov eax, [eax]
    test eax, eax
    jz nofriend
    mov eax, [eax+0x10]
    mov edx, [esp+8]
    call 0x557020EC
    test eax, eax
    jz nofriend
    mov [esp+0xc], eax
    mov edi, -%(R)d
ly: mov ebp, -%(R)d
lx: mov eax, ebp
    or eax, edi
    jz nx
    mov edx, [esp]
    add edx, ebp
    js nx
    mov ecx, [esp+0xc]
    cmp edx, [ecx+0xc]
    jge nx
    mov ecx, [esp+4]
    add ecx, edi
    js nx
    mov eax, [esp+0xc]
    cmp ecx, [eax+0x10]
    jge nx
    call 0x557020DC
    test eax, eax
    jz nx
    mov [esp+0x10], eax
    call 0x55771EB0
    test eax, eax
    jz nx
    mov eax, [eax+0x1c]
    test eax, eax
    jz nx
    mov ecx, esi
    cmp byte ptr [eax+0x12], cl
    jne nx
    mov eax, [esp+0x10]
    mov edx, 0x20108
    mov ecx, [eax]
    call dword ptr [ecx+0x80]
    test eax, eax
    jz wait
nx: inc ebp
    cmp ebp, %(R)d
    jle lx
    inc edi
    cmp edi, %(R)d
    jle ly
nofriend:
    add esp, 0x18
    pop ebp
mint:
    jmp %(MINT)d
wait:
    mov eax, [esp+8]
    shl eax, 16
    mov edx, [esp+4]
    shl edx, 8
    or eax, edx
    or eax, [esp]
    or eax, 0x1000000
    mov [esp+0x14], eax
    mov ecx, [esp+4]
    lea ecx, [ecx+ecx*2]
    add ecx, [esp]
    mov edx, [esp+8]
    lea edx, [edx+edx*4]
    add ecx, edx
    and ecx, %(NM)d
    call %(CODE)d
    mov eax, [eax]
    test eax, eax
    jz w_hold
    mov edx, [eax+0x174]
    call tbl
    lea ecx, [eax+ecx*8]
    mov eax, [esp+0x14]
    cmp [ecx], eax
    jne w_new
    mov eax, edx
    sub eax, [ecx+4]
    jz w_hold
    cmp eax, 1
    je nofriend
w_new:
    mov eax, [esp+0x14]
    mov [ecx], eax
    mov [ecx+4], edx
w_hold:
    add esp, 0x18
    pop ebp
skip:
    jmp %(SKIP)d
"""


def build():
    p2 = CODE + 14 + 5                                 # map helper (14 B: call/pop/add eax,imm32/mov/ret) then "tbl: call p2"
    src = ASM % dict(K=MAPHOLD - (CODE + 5), KT=TABLE - p2, CODE=CODE, R=R, NM=NSLOT - 1, MINT=MINT, SKIP=SKIP)
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)[0])
    import capstone
    ins = list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, CODE))
    assert ins[5].address == CODE + 14 and ins[5].mnemonic == "call" and ins[6].address == p2, "tbl helper misplaced"
    gate = next(i.address for i in ins if i.mnemonic == "lea" and i.op_str.startswith("ecx, [eax*4]"))
    zone = MAGIC + ORIG + bytes(0x10 - 4 - len(ORIG)) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    site = b"\xe9" + struct.pack("<i", gate - (SITE + 5)) + b"\x90" * 5
    assert len(site) == SITE_LEN
    return zone, site, gate


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, gate = build()
    z1, s1, _g1 = C1.build(); z2, s2, _g2 = C2.build()
    rd = lambda lo, hi: bytes(d[lo - V2F:hi - V2F])
    zl, zl2, zl1 = rd(ZONE, ZONE_END), rd(C2.ZONE, C2.ZONE_END), rd(C1.ZONE, C1.ZONE_END)
    sb = rd(SITE, SITE + SITE_LEN)
    sstate = ("vanilla" if sb == ORIG else "v3" if sb == site else "v2" if sb == s2 else "v1" if sb == s1 else "FOREIGN")
    def zst(b, z, nm): return "zero" if not any(b) else nm if b[:len(z)] == z and not any(b[len(z):]) else "DIFFERS"
    z3s, z2s, z1s = zst(zl, zone, "v3"), zst(zl2, z2, "v2"), zst(zl1, z1, "v1")
    bad = [hex(r) for r in relocs(bytes(d), BASE)
           if any(lo - 3 <= r < hi for lo, hi in ((ZONE, ZONE_END), (C2.ZONE, C2.ZONE_END), (C1.ZONE, C1.ZONE_END),
                                                    (SITE, SITE + SITE_LEN)))]
    print("AoWEPACK site-search gate %#x %s | v3 zone %#x %s (%d B, gate cave %#x) | v2 zone %s | v1 zone %s | "
          "table %#x x%d | relocs %s" % (SITE, sstate, ZONE, z3s, len(zone), gate, z2s, z1s, TABLE, NSLOT, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], CODE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if "DIFFERS" in (z3s, z2s, z1s): print("ABORT (zone not free / foreign)"); return 1
    ok = {("vanilla", "zero", "zero", "zero"), ("v1", "zero", "zero", "v1"), ("v2", "zero", "v2", "zero"),
          ("v3", "v3", "zero", "zero")}
    if (sstate, z3s, z2s, z1s) not in ok: print("ABORT (mixed state)"); return 1
    print("  state:", sstate + (" - upgrading %s -> v3 in place" % sstate if sstate in ("v1", "v2") and not a.revert else ""))
    n = bytearray(d)
    for lo, hi in ((ZONE, ZONE_END), (C2.ZONE, C2.ZONE_END), (C1.ZONE, C1.ZONE_END)):
        n[lo - V2F:hi - V2F] = bytes(hi - lo)
    if a.revert:
        n[SITE - V2F:SITE - V2F + SITE_LEN] = ORIG
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[SITE - V2F:SITE - V2F + SITE_LEN] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiconverge3")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
