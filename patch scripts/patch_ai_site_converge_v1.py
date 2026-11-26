r"""
AI SITE SEARCH - WAIT FOR NEARBY FRIENDS (2026-10-19).  AoWEPACK.dll only.

User (after ai-site-leader-safety v3): "they are still taking some risk and making odd decisions (attempting with a
4-unit party with other units nearby)."

RE - the only AI site-search mint is cave_execai @0x55814780 (build_ai_sitesearch v2).  After CanSearch it compares
the army standing ON the site (S_army, through ai-site-leader-safety's wrapper 0x5581E404) with the exact defender
roster [site+0x34] (S_def, rolled once on day 1) and mints the search when 3*S_army >= 2*S_def - deliberately loose
because AI groups split while walking.  That is the "4-unit party attacks while the rest of its group is 1-2 hexes
away" case.
  gate bytes @0x558147DC (10 B, inside our own cave, reloc-free):
     8D 0C 40   lea ecx,[eax+eax*2]
     8D 14 3F   lea edx,[edi+edi]
     39 D1      cmp ecx,edx
     7C 4F      jl  0x55814835        (skip)
  regs there: eax = S_army, edi = S_def, ebx = site, esi = player index (dl of ExecuteAI).

FIX - the gate jumps to a cave:
   3*S_army <  2*S_def           -> skip (vanilla v2 rule, unchanged)
   2*S_army >= 3*S_def (>=1.5x)  -> mint (clearly strong alone: stay aggressive)
   otherwise (between 2/3x and 1.5x): scan the square |dx|,|dy| <= R (=2) around the site on its level; if any OTHER
   army of the same player stands there and is not inside a city (field GetObjectOfType 0x20108 TCity == nil), the
   stack WAITS this pass (no mint) so the group can converge / merge; with no friend nearby it searches as before.
Field access exactly as the engine's own finder 0x557CC7D0: grid = HSE 0x557020EC(eax=[map+0x10], edx=level),
field = 0x557020DC(eax=grid, edx=x, ecx=y) with 0 <= x < [grid+0xC], 0 <= y < [grid+0x10]; army HS = 0x55771EB0
(field) (= GetObjectOfType 0x20217); owner = byte [[hs+0x1C]+0x12].  Site x/y/level = VMT +0x74/+0x78/+0x7C (al).
Map holder [0x558E9494] reached PIC (call/pop).  Only synced game state, no RNG -> MP-identical.
Leader stacks are additionally judged by ai-site-leader-safety v3 (its wrapper zeroes S_army; its XS choke gate in
ExecuteSearch stays in force).  Attraction (cave_msgproc) is unchanged.

Zone AoWEPACK 0x5581C100..0x5581C800 (header 'CNV1' + the 10 original gate bytes; bridge look v3 owns 0x5581C000-100).
LIFO: revert this before build_ai_sitesearch.py / ai-site-leader-safety (its gate site sits in their cave).
Dry-run default; --apply / --revert / --dis / --dll <scratch>.  Backup <game>\backup\AoWEPACK.dll.bak_aiconverge.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581C100, 0x5581C220   # 10/19: 0x5581C220+ = patch_ai_itemloot_use_v1 / reach_v1
CODE = ZONE + 0x10
SITE, SITE_LEN = 0x558147DC, 10
ORIG = bytes.fromhex("8d0c408d143f39d17c4f")
SKIP, MINT = 0x55814835, 0x558147E6
MAPHOLD = 0x558E9494
R = 2

# pic helper first: call p1 / p1: pop eax / add eax, K / mov eax,[eax] / ret   (p1 = CODE+5)
ASM = """
    call p1
p1: pop eax
    add eax, %(K)d
    mov eax, [eax]
    ret
gate:
    lea ecx, [eax+eax*2]
    lea edx, [edi+edi]
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
    movsx eax, al
    mov [esp], eax
    mov eax, ebx
    mov edx, [eax]
    call dword ptr [edx+0x78]
    movsx eax, al
    mov [esp+4], eax
    mov eax, ebx
    mov edx, [eax]
    call dword ptr [edx+0x7c]
    movsx eax, al
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
    add esp, 0x18
    pop ebp
skip:
    jmp %(SKIP)d
"""


def build():
    src = ASM % dict(K=MAPHOLD - (CODE + 5), CODE=CODE, R=R, MINT=MINT, SKIP=SKIP)
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)[0])
    import capstone
    gate = None
    for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, CODE):
        if i.mnemonic == "lea" and i.op_str.startswith("ecx, [eax + eax*2]"): gate = i.address; break
    assert gate
    zone = b"CNV1" + bytes(12)
    zone = zone[:4] + ORIG + zone[4 + len(ORIG):]
    zone = zone[:0x10] + code
    assert len(zone) <= ZONE_END - ZONE
    site = b"\xe9" + struct.pack("<i", gate - (SITE + 5)) + b"\x90" * 5
    assert len(site) == SITE_LEN
    return zone, site, gate


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, gate = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F]); sb = bytes(d[SITE - V2F:SITE - V2F + SITE_LEN])
    sstate = "vanilla" if sb == ORIG else "ours" if sb == site else "FOREIGN"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + SITE_LEN]
    print("AoWEPACK site-search gate %#x %s | zone %#x %s (%d B, gate cave %#x) | relocs %s"
          % (SITE, sstate, ZONE, zstate, len(zone), gate, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], CODE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate == "ours"): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        n[SITE - V2F:SITE - V2F + SITE_LEN] = ORIG; n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[SITE - V2F:SITE - V2F + SITE_LEN] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiconverge")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
