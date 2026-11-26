r"""
AI SITE EXPLORING - ALL-LEVEL-1 ROSTER HALVING v1 (2026-10-20).  AoWEPACK.dll only.  Layer on
patch_ai_site_leader_safety_v6.py (zone 0x5581E400, 'ALS6').

User: "if ALL the defenders of an exploration site are LEVEL 1, its perceived combat strength is HALVED (only for
exploration sites)."

Single source: leader-safety v6's rs_eff (0x5581E5C5) is THE roster-strength function every AI site decision uses:
  * hook RA 0x558147AF (cave_execai search gate)   -> converge v5 gate edi + army_eff/judge (fight decisions)
  * hook RB 0x55814AA7 (cave_msgproc attraction)    -> grp_eff, recruit v3 tag/M gate (ebp), site boost v1 (ebp)
  * xs_gate's internal `call rs_eff`                 -> XS ExecuteSearch leader judge
so redirecting rs_eff itself keeps every consumer consistent (no gate can contradict another).

rs_eff entry (5 B: `push esi / mov esi,eax / call..`) -> jmp RS7 (zone 0x5581DD00..0x5581DE00, header 'L1H1'):
  RS7 = v6 rs_eff semantics (ls_all all-kinds strength; >= 1 while the list holds units; empty -> 0), then if the
  strength is > 0 and EVERY unit in the roster TUnitList ([list+8] TList: +4 items, +8 count) answers level 1 via
  the unit's own GetLevel virtual (VMT+0xA0: TUnit 0x55782B8C = template [+0x40] byte +0x2F; THero overrides) ->
  strength / 2 (min 1).  Mixed levels / nil unit / empty -> unchanged.  Pure synced game state, no RNG.
Only rosters (site defender lists) reach rs_eff, so only exploration sites are affected.

Dry-run default; --apply / --revert / --dis / --dll.  Backup <game>\backup\AoWEPACK.dll.bak_l1half.
LIFO: revert THIS before reverting/re-applying patch_ai_site_leader_safety_v6 (whose dry run reports its zone
DIFFERS while this is applied).  Boost v1 / converge v5 only check the 'ALS6' magic (unchanged) - unaffected.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_site_leader_safety_v6 as V6

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V6.BASE, V6.V2F
ZONE, ZONE_END = 0x5581DD00, 0x5581DE00
MAGIC = b"L1H1"
CODE = ZONE + 4
GETLEVEL_SLOT = 0xA0

ASM = """
rs7:
    push esi
    mov  esi, eax
    call LSALL
    test eax, eax
    jnz  have
    mov  eax, [esi+8]
    test eax, eax
    jz   r0
    cmp  dword ptr [eax+8], 0
    jle  r0
    mov  eax, 1
    jmp  out
r0:
    xor  eax, eax
    jmp  out
have:
    push ebx
    push edi
    push ebp
    mov  ebp, eax
    mov  eax, [esi+8]
    test eax, eax
    jz   keep
    mov  edi, [eax+8]
    test edi, edi
    jle  keep
    xor  ebx, ebx
lp:
    mov  eax, [esi+8]
    mov  eax, [eax+4]
    mov  eax, [eax+ebx*4]
    test eax, eax
    jz   keep
    mov  edx, [eax]
    call dword ptr [edx+SLOT]
    cmp  al, 1
    jne  keep
    inc  ebx
    cmp  ebx, edi
    jl   lp
    shr  ebp, 1
    jnz  keep
    mov  ebp, 1
keep:
    mov  eax, ebp
    pop  ebp
    pop  edi
    pop  ebx
out:
    pop  esi
    ret
"""


def v6_labels():
    return V6.build("leader")


def build():
    z6, L = v6_labels()
    src = ASM.replace("LSALL", "0x%X" % L["ls_all"]).replace("SLOT", "0x%X" % GETLEVEL_SLOT)
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)[0])
    zone = MAGIC + code
    assert len(zone) <= ZONE_END - ZONE
    site = L["rs_eff"]
    orig = z6[site - V6.ZONE:site - V6.ZONE + 5]
    new = b"\xe9" + struct.pack("<i", CODE - (site + 5))
    return zone, site, orig, new, z6


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site, orig, new, z6 = build()
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    if rd(V6.ZONE, 4) != b"ALS6":
        print("ABORT (ai-site-leader-safety v6 not applied)"); return 1
    zl = rd(ZONE, ZONE_END - ZONE)
    zstate = "zero" if not any(zl) else ("ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS")
    sc = rd(site, 5)
    sstate = "vanilla(v6)" if sc == orig else ("ours" if sc == new else "FOREIGN")
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or site - 3 <= r < site + 5]
    print("AoWEPACK rs_eff %#x %s | zone %#x %s (%d B, rs7 %#x) | relocs %s"
          % (site, sstate, ZONE, zstate, len(zone), CODE, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[4:], CODE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (reloc)"); return 1
    if zstate == "DIFFERS" or sstate == "FOREIGN": print("ABORT (zone/site foreign)"); return 1
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    if a.revert:
        n[site - V2F:site - V2F + 5] = orig
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        n[site - V2F:site - V2F + 5] = new
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_l1half")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
