"""
ROT (ability 0xB5) - a status overlay on combat units, like Cursed's (2026-10-14).  AoWTCPCK.dll.

RE: TTacticalCombatUnitHS.Show draws the per-ability status overlays in a loop @0x4227AA..0x4228A2:
  for i in 0..13: id = OverlayIds[i] (table 0x4675B8, 14 dwords: 95 96 30 5C 5D(Cursed) 5E 5F 60(Poisoned) 61(Webbed)
  62(Vertigo) 6B A3 7F(Burning) 22; range-checked by `bound eax,[0x422BCC]` = (0, 13)); if CU VMT+0xA8 (has ability
  edx) -> ability = GetAbility(id) (0x402704 on [[0x46E8D0]]+0x80); seq = TImageSequenceList [ability+0x1C] slot 0
  (0x4016E4) and its chain (+0xC); frame = 0x4016D4(seq, tick [[0x46E8D4]]+0x40, phase (hs>>2)&0xFFFF) - a PURE pick, no
  shared stepping; image = 0x4016F4([seq+0x10], frame); Draw VMT+0x84 at x = [seq+0x24] + drawX + 0xF,
  y = [seq+0x28] + drawY + 0xA + [ebp-0x38].
  So an overlay is just the ability's OWN graphics: Ability.pfs record (key = id + 10) tag 8, same sequence format as a
  spell's tag 0xC.  Cursed (key 103) = TCOMBAT\\OBJECTS\\SEFFECT.ILB 50-65 (64x64, drawMode 1026 blend 50 - a darkening
  multiply), kind 4, f18 1, f20 13, xs -31 ys -35.  Burning (key 137) = EFFECTS\\FIRESM2.ILB, kind 1.
Patch = relocate the id table with 0xB5 appended (15 entries) - no code cave:
  TABLE  0x43EC00: the 14 vanilla ids + 0xB5 (read-only data in the CODE cave area)
  RD1/RD2  disp32 of `mov edx,[eax*4+0x4675B8]` @0x4227B6 / 0x4227DC -> 0x43EC00 (both carry a type-3 reloc, which
           stays valid: the field is still an absolute in-image address)
  BOUND  the range pair @0x422BCC (0, 13) -> (0, 14) (only the two `bound` @0x4227AD / 0x4227D3 read it)
  LOOP   `cmp dword [ebp-0x30],0x0E` @0x42289E -> 0x0F
Rot's own graphics come from Ability.pfs record 191 tag 8 (empty today) - patch_rot_ability_pfs_v1.py must write it
(see the report); until then the loop finds an empty list for 0xB5 and draws nothing (safe).
Dry-run default; --apply / --revert (in place) / --dis.  Backup <game>\\backup\\AoWTCPCK.dll.bak_rotoverlay.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWTCPCK.dll")
BASE, CODE_V2F = 0x400000, 0x400C00
OLD_TABLE, NEW_TABLE, N_OLD = 0x4675B8, 0x43EC00, 14
ZONE, ZONE_END = 0x43EC00, 0x43EC40
ROT_ID = 0xB5
SITES = {   # name: (va, vanilla bytes, patched bytes)
    "RD1":   (0x4227B6, struct.pack("<I", OLD_TABLE), struct.pack("<I", NEW_TABLE)),
    "RD2":   (0x4227DC, struct.pack("<I", OLD_TABLE), struct.pack("<I", NEW_TABLE)),
    "BOUND": (0x422BCC, struct.pack("<ii", 0, 13), struct.pack("<ii", 0, 14)),
    "LOOP":  (0x4228A1, bytes([0x0E]), bytes([0x0F])),
}
CONTEXT = {"RD1": (0x4227B3, bytes.fromhex("8b1485")), "RD2": (0x4227D9, bytes.fromhex("8b1485")), "LOOP": (0x42289E, bytes.fromhex("837dd0"))}


def data_va_to_off(d, va):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    for k in range(nsec):
        vs, rva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if rva <= va - BASE < rva + max(vs, rs): return ro + va - BASE - rva
    raise ValueError(hex(va))


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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    old = [struct.unpack_from("<I", d, data_va_to_off(d, OLD_TABLE) + 4 * k)[0] for k in range(N_OLD)]
    table = struct.pack("<%dI" % (N_OLD + 1), *(old + [ROT_ID]))
    assert ZONE + len(table) <= ZONE_END
    for name, (cva, cb) in CONTEXT.items():
        assert bytes(d[cva - CODE_V2F:cva - CODE_V2F + len(cb)]) == cb, "unexpected code around %s" % name
    states = {}
    for name, (va, van, ours) in SITES.items():
        live = bytes(d[va - CODE_V2F:va - CODE_V2F + len(van)])
        states[name] = "vanilla" if live == van else "ours" if live == ours else "OTHER"
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(table)] == table and not any(zl[len(table):]) else "DIFFERS"
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or 0x422BCC <= r < 0x422BD4 or 0x4228A1 == r]
    print("ids %s + 0x%X | sites %s | table zone %s (%d B @%#x) | relocs %s | RD relocs kept %s" % (
        " ".join("%X" % x for x in old), ROT_ID, states, zstate, len(table), ZONE, bad or "none",
        all((va in rl) for va in (0x4227B6, 0x4227DC))))
    if a.dis: print("   table:", " ".join("%02X" % x for x in old + [ROT_ID]))
    if bad or "OTHER" in states.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        for name, (va, van, ours) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(van)] = van
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(table)] = table
    for name, (va, van, ours) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(van)] = ours
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_rotoverlay")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
