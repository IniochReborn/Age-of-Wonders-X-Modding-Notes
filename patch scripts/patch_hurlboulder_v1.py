"""
HURL BOULDER (365) - thrown like the Hurl Boulder ABILITY (2026-10-15).  AoWTCPCK.dll.

User: "hurl boulder should have the same trajectory and animation as the hurl boulder ability ... same sfx but with an
added magical sound at start-up. hit sfx should be the same."

How the ability does it (RE 2026-10-15):
  * Hurl Boulder = ability 0x18, AbilTypes[0x18] = 2 = TfxType fxComet (the same class as Fire Ball's spell kind 2).
    TCAbRangedTE.NextStrike's default case -> MakeAbilPath 0x4271EC(edx = [te+0x14] ability, ecx = [te+0x18] id):
    abilities 0x16/0x18/0x19 -> 0x427298 = MakeRangedPath(dx 0x32, cx 0x64 = the HIGH lob arc); a SPELL (0x34) of
    kind 2 with an id outside 0x64..0x77 -> 0x4275B6 = MakeRangedPath(0x32, 0x32) = Fire Ball's flatter arc.
    fxComet NewFrame steps one path point per frame for both; TfxHS.Show case 2 (0x42FAF2) draws gfx SLOT 0 only
    (GetSeq: spells read [spell+0x2C], abilities [ab+0x1C]) - no trail, no impact sprite.  At the landing it plays
    sound cue 1 of the spell's / ability's own library.
  * Ability.pfs record 34 (0x18): gfx slot 0 = TCOMBAT\\OBJECTS\\BALLS.ILB frames 7..14, f18 1, f20 6, xs -31, ys -33;
    sounds [SFX\\ATTACK\\CATAPULT.WAV, [SFX\\ATTACK\\A_PUNCH2.WAV]] (cue 0 throw, cue 1 hit).
  * Impact (TCAbRangedTE.Execute phase 1): a strike that hit a living unit gets the CA from GetSpell(id).CreateCA
    (damage + blood, same as the ability).  Otherwise the ability sends map msg 0x31001 (walls/terrain) while a
    spell falls into the class switch @0x40C856 on [fx+0x34], where kind 2 does NOTHING -> a spell boulder that
    lands on (or is stopped by) a wall would not hurt it.

With SpellTypes[365] = 2 (pipeline tc_type=2, NO alias) the spell already flies caster -> target as an fxComet with
the spell's slot 0, and the unit hit/damage/blood is the generic path.  This script adds the two missing pieces:
  PATH   @0x42737D (7 B `movsx eax,word [ebp-6] / add eax,-0x64`, MakeAbilPath's spell-id switch) -> jmp cave:
         id 365 -> 0x427298 (the ability's own lob: dx 0x32, cx 0x64), everything else replays and returns.
  WALL   @0x40C856 (6 B `mov eax,[ebp-0x20] / mov al,[eax+0x34]`, the spell impact class switch) -> jmp cave:
         id 365 with no unit target ([fx+0x2C] == 0) -> 0x40C8E2, the hail impact sender: msg 0x31006 with the
         spell id in msg+0xC (patch_tc_hail_msg_spell_v1.py) -> walls / gates / structures / terrain at the landing
         hex take Hurl Boulder's own ATK/DMG (the handlers call GetSpell(365)).  Else replays and returns.
Only relative jumps (TCPCK rebases); no RNG, no state -> MP-deterministic like every other strike.
Zone 0x43B100..0x43B180 (zero, reloc-free).  Dry-run default; --apply / --revert / --dis.
Backup <game>\\backup\\AoWTCPCK.dll.bak_hurlboulder (one-time safety copy; --revert is surgical).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWTCPCK.dll")
BASE, CODE_V2F = 0x400000, 0x400C00
SPELL_ID = 365
PATH_SITE, PATH_ORIG = 0x42737D, bytes.fromhex("0fbf45fa83c09c")
WALL_SITE, WALL_ORIG = 0x40C856, bytes.fromhex("8b45e08a4034")
LOB_CASE, PATH_BACK = 0x427298, 0x427384          # ability 0x18's MakeRangedPath(0x32, 0x64); after the replayed add
HAIL_SEND, WALL_BACK = 0x40C8E2, 0x40C85C         # msg 0x31006 sender; after the replayed mov al
ZONE, ZONE_END = 0x43B100, 0x43B180

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    path = asm("""
        movsx eax, word ptr [ebp-6]
        cmp eax, %(id)d
        je %(lob)#x
        add eax, -0x64
        jmp %(back)#x
    """ % {"id": SPELL_ID, "lob": LOB_CASE, "back": PATH_BACK}, ZONE)
    wall_va = ZONE + ((len(path) + 15) & ~15)
    # 10/15: the kind-2 check skips the pre-throw glow (a kind-0x26 effect carrying id 365, patch_hurlboulder_glow_v1.py)
    wall = asm("""
        mov eax, dword ptr [ebp-0x20]
        cmp dword ptr [eax+0x18], %(id)d
        jne rp
        cmp byte ptr [eax+0x34], 2
        jne rp
        cmp dword ptr [eax+0x2c], 0
        jne rp
        jmp %(send)#x
    rp:
        mov al, byte ptr [eax+0x34]
        jmp %(back)#x
    """ % {"id": SPELL_ID, "send": HAIL_SEND, "back": WALL_BACK}, wall_va)
    z = bytearray(path); z += bytes(wall_va - ZONE - len(path)); z += wall
    return bytes(z), {"path": ZONE, "wall": wall_va}


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def code_section(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    vs, va, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 8)
    return BASE + va, BASE + va + min(vs, rs)


def branches_into(d, lo, hi):
    """VAs of jmp/jcc/call instructions (linear capstone sweep of CODE) whose direct target lies strictly inside (lo, hi)."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); md.skipdata = True
    s, e = code_section(d); hits = []
    for i in md.disasm(bytes(d[s - CODE_V2F:e - CODE_V2F]), s):
        if i.mnemonic.startswith("j") or i.mnemonic == "call":
            try: t = int(i.op_str, 16)
            except ValueError: continue
            if lo < t < hi: hits.append(hex(i.address))
    return hits


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    zone, where = build(); assert ZONE + len(zone) <= ZONE_END
    sites = [(PATH_SITE, PATH_ORIG, where["path"]), (WALL_SITE, WALL_ORIG, where["wall"])]
    hooks = {va: b"\xe9" + struct.pack("<i", cave - (va + 5)) + b"\x90" * (len(orig) - 5) for va, orig, cave in sites}
    st = {}
    for va, orig, cave in sites:
        live = bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)])
        st[hex(va)] = "vanilla" if live == orig else "ours" if live == hooks[va] else "OTHER"
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + len(o) for va, o, _ in sites)]
    into = [] if a.revert else sum((branches_into(d, va, va + len(o)) for va, o, _ in sites), [])
    print("sites %s | zone %s (%d B: path=%#x wall=%#x) | relocs %s | branches into sites %s"
          % (st, zstate, len(zone.rstrip(b"\0")), where["path"], where["wall"], bad or "none", into or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or into or "OTHER" in st.values(): print("ABORT"); return 1
    if a.revert:
        for va, orig, _ in sites: d[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and not all(v == "ours" for v in st.values()): print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, _ in sites: d[va - CODE_V2F:va - CODE_V2F + len(orig)] = hooks[va]
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_hurlboulder")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
