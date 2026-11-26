r"""
AI SITE SEARCH - WAIT FOR NEARBY FRIENDS v2 (2026-10-19).  AoWEPACK.dll only.  In-place upgrade of
patch_ai_site_converge_v1.py (same gate site 0x558147DC; the cave MOVES to a larger zone).

User (after converge v1 + leader-safety v3): "other AIs are being passive, not attempting easy exploration sites".
v1 risk: a marginal stack (2/3x .. 1.5x the roster) WAITS every pass while ANY own army stands within 2 hexes - a
garrison, a mine guard or a stack that never merges keeps it waiting forever.

v2 = v1's rule with a deterministic one-turn cap: the "wait for a friend" branch only waits on days where
(day + site x + site y) is EVEN; on odd days it searches (exactly as with no friend nearby).  So a marginal stack
waits at most one turn in a row for its group to converge, then goes in.  Day = [[0x558E9494]]+0x174 (synced),
x/y = the site's own VMT +0x74/+0x78 - no RNG, MP-identical.  Everything else unchanged from v1:
   3*S_army <  2*S_def -> skip;  2*S_army >= 3*S_def -> search;  in between: own army within |dx|,|dy| <= 2 (not in a
   city) -> wait (even days only), else search.
S_army / S_def come from ai-site-leader-safety's wrappers (v4: real all-damage-type strengths).

Zone AoWEPACK 0x5581C6C0..0x5581C800 (header 'CNV2' + the 10 original gate bytes); v1's zone 0x5581C100..0x5581C220
is zeroed on upgrade.  Dry-run default; --apply / --revert / --dis / --dll.
  apply : vanilla gate / v1 -> v2;   revert : -> original gate bytes, both zones zero (== v1 --revert).
LIFO: revert this before build_ai_sitesearch.py / ai-site-leader-safety (its gate site sits in their cave).
v1's script refuses a v2 install (its zone check sees the gate pointing elsewhere -> FOREIGN).
Backup <game>\backup\AoWEPACK.dll.bak_aiconverge2.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_ai_site_converge_v1 as C1

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581C6C0, 0x5581C800
CODE = ZONE + 0x10
SITE, SITE_LEN, ORIG = C1.SITE, C1.SITE_LEN, C1.ORIG
SKIP, MINT, MAPHOLD, R = C1.SKIP, C1.MINT, C1.MAPHOLD, C1.R
MAGIC = b"CNV2"

WAIT_OLD = """wait:
    add esp, 0x18
    pop ebp
skip:"""
WAIT_NEW = """wait:
    call %(CODE)d
    mov eax, [eax]
    test eax, eax
    jz w_hold
    mov eax, [eax+0x174]
    add eax, [esp]
    add eax, [esp+4]
    test al, 1
    jnz nofriend
w_hold:
    add esp, 0x18
    pop ebp
skip:"""


def build():
    assert C1.ASM.count(WAIT_OLD) == 1
    asm = C1.ASM.replace(WAIT_OLD, WAIT_NEW)
    src = asm % dict(K=MAPHOLD - (CODE + 5), CODE=CODE, R=R, MINT=MINT, SKIP=SKIP)
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)[0])
    import capstone
    gate = None
    for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, CODE):
        if i.mnemonic == "lea" and i.op_str.startswith("ecx, [eax + eax*2]"): gate = i.address; break
    assert gate
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
    z1, s1, g1 = C1.build()
    rd = lambda lo, hi: bytes(d[lo - V2F:hi - V2F])
    zl, zl1 = rd(ZONE, ZONE_END), rd(C1.ZONE, C1.ZONE_END)
    sb = rd(SITE, SITE + SITE_LEN)
    sstate = "vanilla" if sb == ORIG else "v2" if sb == site else "v1" if sb == s1 else "FOREIGN"
    zstate = "zero" if not any(zl) else "v2" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    z1state = "zero" if not any(zl1) else "v1" if zl1[:len(z1)] == z1 and not any(zl1[len(z1):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE)
           if ZONE - 3 <= r < ZONE_END or C1.ZONE - 3 <= r < C1.ZONE_END or SITE - 3 <= r < SITE + SITE_LEN]
    print("AoWEPACK site-search gate %#x %s | v2 zone %#x %s (%d B, gate cave %#x) | v1 zone %#x %s | relocs %s"
          % (SITE, sstate, ZONE, zstate, len(zone), gate, C1.ZONE, z1state, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], CODE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if "DIFFERS" in (zstate, z1state): print("ABORT (zone not free / foreign)"); return 1
    ok = {("vanilla", "zero", "zero"), ("v1", "zero", "v1"), ("v2", "v2", "zero")}
    if (sstate, zstate, z1state) not in ok: print("ABORT (mixed state)"); return 1
    print("  state:", sstate + (" - upgrading v1 -> v2 in place" if sstate == "v1" and not a.revert else ""))
    n = bytearray(d)
    n[C1.ZONE - V2F:C1.ZONE_END - V2F] = bytes(C1.ZONE_END - C1.ZONE)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    if a.revert:
        n[SITE - V2F:SITE - V2F + SITE_LEN] = ORIG
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[SITE - V2F:SITE - V2F + SITE_LEN] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiconverge2")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
