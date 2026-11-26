r"""
DUAL-SPHERE RESEARCH GATE: a pair spell needs a KNOWN spell of BOTH component spheres (2026-10-20).  AoWEPACK.dll only.

User: Water/Air/Life spheres, started knowing Air/Water/Cosmos spells -> Air/Water pair spells researchable (correct)
but Air/Life pair spells were researchable too (wrong: no Life spell known yet).

ROOT CAUSE - TPlayerMagicControl.ValidResearchSpell 0x5577CFF0 (eax=ctl, edx=spell) only checks
  (1) tier [spell+0x21] <= GetSpherePicks(leader, sphere)  -> patch_dual_sphere_plumbing_v1 H_PICKS makes a pair
      return picks(A)+picks(B)-1, i.e. >= 1 whenever BOTH spheres are PICKED (Air 1 + Life 1 -> 1),
  (2) not already known ([ctl+0x30] IndexOf), and
  (3) the per-sphere tier ladder (count of known spells of THE PAIR sphere per tier; H_LADDER needs 1 for pairs) -
      tier 1 has no prerequisite.
  Nothing ever looked at the component spheres' KNOWN spells, so every tier-1 pair spell of two picked spheres was
  researchable from turn 1.  Air/Water only "looked right" because Air+Water spells happened to be known.

FIX - hook S 0x5577D01B (`mov eax,[esp] / mov edx,[eax+0x10]`, 6 B, right after the picks test passed): for a pair
sphere 9..22 walk the known list [ctl+0x30] (TIntegerList: count [+8], Get 0x55702E94; GetSpell 0x55779AC8 on
[[0x558FA044]+0x84]) and require one known spell whose sphere byte [spell+0x20] == A and one == B (exact compare -
Cosmos 0 / Secret 7 / other pair spells never count).  Missing either -> the vanilla 'not valid' exit 0x5577D0C6.
Single-sphere spells unchanged.  Uses the frame's free ladder slots [esp+4..+0xC] before the ladder zeroes them.
PIC: call/pop delta for the pair table and the engine global (no absolute operands needing relocs).
Zone AoWEPACK 0x5581DE00..0x5581E000 (zero, reloc-free; l1half ends 0x5581DE00, evoker33 at 0x5581E000).
LIFO: independent of patch_no_pair_start_spells_v1 (G1/G2) and the dual-sphere plumbing H_LADDER cave (0x5577D09C,
later in the same function).  Dry-run default; --apply / --revert (exact) / --dis / --dll <copy>.  Backup .bak_pairgate.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581DE00, 0x5581E000
MAGIC = b"PRG1"
CODE = ZONE + 4
SITE, SITE_ORIG, RESUME, FAIL = 0x5577D01B, bytes.fromhex("8b04248b5010"), 0x5577D021, 0x5577D0C6
LIST_GET, GET_SPELL, ENGINE = 0x55702E94, 0x55779AC8, 0x558FA044
PAIRS = [(1, 3), (1, 4), (1, 5), (1, 6), (2, 3), (2, 4), (2, 5), (2, 6),
         (3, 4), (3, 5), (3, 6), (4, 5), (4, 6), (5, 6)]          # sphere ids 9..22 (patch_dual_sphere_plumbing_v1 PAIRS)

ASM = """
cv:
    mov eax, dword ptr [esp]
    movzx ecx, byte ptr [eax+0x20]
    sub ecx, 9
    cmp ecx, 13
    ja ok
    call gp
gp:
    pop ebx
    sub ebx, %(GP)d
    movzx eax, byte ptr [ebx + ecx*2 + %(TAB)d]
    mov dword ptr [esp+4], eax
    movzx eax, byte ptr [ebx + ecx*2 + %(TAB1)d]
    mov dword ptr [esp+8], eax
    mov dword ptr [esp+0xC], 0
    mov eax, dword ptr [edi+0x30]
    mov esi, dword ptr [eax+8]
lp:
    dec esi
    js chk
    mov eax, dword ptr [edi+0x30]
    mov edx, esi
    call %(GET)d
    mov edx, eax
    mov eax, dword ptr [ebx + %(ENG)d]
    mov eax, dword ptr [eax+0x84]
    call %(GSP)d
    test eax, eax
    jz lp
    movzx eax, byte ptr [eax+0x20]
    cmp eax, dword ptr [esp+4]
    jne n1
    or dword ptr [esp+0xC], 1
n1:
    cmp eax, dword ptr [esp+8]
    jne lp
    or dword ptr [esp+0xC], 2
    jmp lp
chk:
    cmp dword ptr [esp+0xC], 3
    jne %(FAIL)d
ok:
    mov eax, dword ptr [esp]
    mov edx, dword ptr [eax+0x10]
    jmp %(RES)d
"""


def build():
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    def asm(tab, gp):
        src = ASM % dict(GP=gp, TAB=tab, TAB1=tab + 1, ENG=ENGINE, GET=LIST_GET, GSP=GET_SPELL, FAIL=FAIL, RES=RESUME)
        return bytes(ks.asm(src, CODE)[0])
    CALLPOP = bytes.fromhex("e8000000005b")   # call +0 / pop ebx
    gp, tab = CODE, CODE + 0x100
    for _ in range(6):                        # gp = the pop after `call +0`; table right after the code
        code = asm(tab, gp)
        k = code.index(CALLPOP)
        ngp, ntab = CODE + k + 5, CODE + len(code)
        if (ngp, ntab) == (gp, tab): break
        gp, tab = ngp, ntab
    code = asm(tab, gp)
    assert CODE + len(code) == tab and code.index(CALLPOP) + CODE + 5 == gp
    table = bytes(b for p in PAIRS for b in p)
    zone = MAGIC + code + table
    assert len(zone) <= ZONE_END - ZONE
    site = b"\xe9" + struct.pack("<i", CODE - (SITE + 5)) + b"\x90"
    assert len(site) == len(SITE_ORIG)
    return zone, site, gp, tab


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, gp, tab = build()
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    sst = "vanilla" if g(SITE, 6) == SITE_ORIG else "ours" if g(SITE, 6) == site else "FOREIGN"
    zl = g(ZONE, ZONE_END - ZONE)
    zst = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + 6]
    print("ValidResearchSpell pair gate site %#x %s | zone %#x %s (%d B, table %#x) | relocs %s"
          % (SITE, sst, ZONE, zst, len(zone), tab, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:tab - ZONE], CODE):
            print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sst == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if zst == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sst == "ours") != (zst == "ours"): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    def put(va, b): n[va - V2F:va - V2F + len(b)] = b
    if a.revert:
        put(SITE, SITE_ORIG); put(ZONE, bytes(ZONE_END - ZONE))
    else:
        put(ZONE, zone); put(SITE, site)
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_pairgate")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
