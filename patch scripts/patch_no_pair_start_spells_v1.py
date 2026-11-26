r"""
NO DUAL-SPHERE SPELLS FROM AUTOMATIC STARTING-SPELL GRANTS (2026-10-19).  AoWEPACK.dll only.

User: started a new game already knowing Misty Step (396, Water/Air pair sphere 21, tier 1).  Pair spells must only
come from research (ValidResearchSpell ladder, aowx-dual-sphere-spells).

RE - the two automatic grants that pick spells by sphere through GetSpherePicks 0x5578B17C (pair sphere ->
picks(A)+picks(B), > 0 when both are picked, so pair spells qualify):
  G1  TResearch day-1 starting spells (fn 0x5577CC2C; entry hooked by drought -> 0x55864060 and back): on day 1
      ([game+0x174]==1) for a non-independent player, unless [game+0x11A]==1 and the known list [res+0x30] is already
      non-empty (map-defined spells), for each book category 0..2 ([spell+0x22]) collect every unknown spell with
      tier [spell+0x21]==1 whose sphere [spell+0x20] is 0 (no sphere) or has picks > 0, then add ONE random pick
      (0x5577827C) to the known list.  -> Misty Step / other tier-1 pair spells could be drawn.
      Site 0x5577CCD6 `cmp byte [ebx+0x20],0 / je 0x5577CCF1` (6 B).
  G2  TAoWCampaign scenario-setup catch-up (VMT slot @0x55723EAC -> 0x5573217C): every player except the human
      gets all spells with tier <= completed/4+1 and picks(sphere) >= tier.  -> pair spells for campaign AIs.
      Site 0x55732244 `xor eax,eax / mov al,[ebp+0x21] / cmp eax,[esp+4]` (9 B), next `jg 0x557322B9` (skip).
  Not grants: CanAddSphere 0x5578B21x (setup sphere rules), node bonuses 0x557BD/BE (node sphere ids <= 6),
  ValidResearchSpell (research gate - untouched, pair spells stay researchable).
  Map-maker spells: stored in the player's research known list [res+0x30] from the map; G1 never removes entries,
  only adds one random pick (and is skipped entirely in map-defined mode), G2 only adds -> nothing is stripped.
FIX - both sites skip a candidate whose sphere byte is a PAIR sphere 9..22 (single spheres 0..8 incl. Cosmos 0 /
Secret 7 and our single-sphere custom ids unchanged).  Caves PIC (rel32 jumps only).
Zone AoWEPACK 0x5581F100..0x5581F200 (zero, reloc-free; item prio 0x5581F000-0x5581F0F9, hex grid 0x5581F800).
Dry-run default; --apply / --revert (exact vanilla bytes) / --dis / --dll <copy>.  Backup .bak_nopairstart.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581F100, 0x5581F200
PAIR_LO, PAIR_N = 9, 14                       # spheres 9..22
S1, S1_ORIG = 0x5577CCD6, bytes.fromhex("807b20007415")
S2, S2_ORIG = 0x55732244, bytes.fromhex("33c08a45213b442404")

CAVE = """
c1:
    mov al, byte ptr [ebx+0x20]
    sub al, %(LO)d
    cmp al, %(N1)d
    jbe 0x5577CD02
    cmp byte ptr [ebx+0x20], 0
    je 0x5577CCF1
    jmp 0x5577CCDC
c2:
    mov al, byte ptr [ebp+0x20]
    sub al, %(LO)d
    cmp al, %(N1)d
    jbe 0x557322B9
    xor eax, eax
    mov al, byte ptr [ebp+0x21]
    cmp eax, dword ptr [esp+4]
    jmp 0x5573224D
""" % dict(LO=PAIR_LO, N1=PAIR_N - 1)


def build():
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    zone = bytes(ks.asm(CAVE, ZONE)[0])
    # locate c2: assemble c1 alone
    c1 = bytes(ks.asm(CAVE.split("c2:")[0], ZONE)[0]); c2 = ZONE + len(c1)
    assert len(zone) <= ZONE_END - ZONE - 0x10
    s1 = b"\xe9" + struct.pack("<i", ZONE - (S1 + 5)) + b"\x90"
    s2 = b"\xe9" + struct.pack("<i", c2 - (S2 + 5)) + b"\x90" * 4
    assert len(s1) == len(S1_ORIG) and len(s2) == len(S2_ORIG)
    return zone, s1, s2, c2


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, s1, s2, c2 = build()
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    st = lambda va, orig, new: "vanilla" if g(va, len(orig)) == orig else "ours" if g(va, len(new)) == new else "FOREIGN"
    st1, st2 = st(S1, S1_ORIG, s1), st(S2, S2_ORIG, s2)
    zl = g(ZONE, ZONE_END - ZONE)
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or S1 - 3 <= r < S1 + 6 or S2 - 3 <= r < S2 + 9]
    print("G1 day-1 start spells %#x %s | G2 campaign catch-up %#x %s | zone %#x %s (%d B, c2 %#x) | relocs %s"
          % (S1, st1, S2, st2, ZONE, zstate, len(zone), c2, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "FOREIGN" in (st1, st2): print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if len({st1 == "ours", st2 == "ours", zstate == "ours"}) != 1: print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    def put(va, b): n[va - V2F:va - V2F + len(b)] = b
    if a.revert:
        put(S1, S1_ORIG); put(S2, S2_ORIG); put(ZONE, bytes(ZONE_END - ZONE))
    else:
        put(ZONE, zone); put(S1, s1); put(S2, s2)
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_nopairstart")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
