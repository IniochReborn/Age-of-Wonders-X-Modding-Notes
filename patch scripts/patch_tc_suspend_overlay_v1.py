#!/usr/bin/env python3
r"""
Suspend (214): a persistent STATUS OVERLAY for 0xC3 'Suspended' (2026-10-16, user: "a gfx like Entangled - a very
subtle beam of white light with small white particles slowly spinning upwards around it").  AoWTCPCK.dll.

RE (earthdeath-spells.md / patch_rot_overlay_v1.py): TTacticalCombatUnitHS.Show draws the per-ability status overlays
in a loop @0x4227AA..0x4228A2 over an id TABLE (vanilla 0x4675B8, 14 ids; patch_rot_overlay_v1.py moved it to
0x43EC00 with Rot 0xB5 appended = 15 ids): for each id the CU holds (VMT+0xA8), it draws the ABILITY's own graphics =
Ability.pfs record (key id + 10) tag 8, sequence slot 0, frame picked purely from the map tick (no shared stepping),
at x = xs + drawX + 0xF, y = ys + drawY + 0xA, through the image's own drawMode.
Rot's table zone 0x43EC00..0x43EC40 is full after one more id, so this script RELOCATES the table again:
  TABLE  0x444010: the ids found live (decoded from where RD1 points, count = the LOOP byte) + 0xC3
  RD1/RD2  disp32 of `mov edx,[eax*4+table]` @0x4227B6 / 0x4227DC -> 0x444010 (type-3 relocs stay valid)
  BOUND  the `bound` pair @0x422BCC (0, n-1) -> (0, n)
  LOOP   imm8 of `cmp [ebp-0x30],n` @0x4228A1 -> n + 1
Header @0x444000 keeps the values found at apply (RD target, bound pair, loop byte) for an exact --revert.
The graphics themselves = patch_suspend_ability_pfs_v1.py v2 (record 205 tag 8 -> DualDF 3250.. suspend_status).
v2 2026-10-16 (Static Shield 215): the appended ids are now ADD = (0xC3, 0xC4) - 0xC4 'Static Shield' gets its
persistent lightning aura the same way (Ability.pfs record 206 tag 8, patch_staticshield_ability_pfs_v1.py v2).  A live
v1 (only 0xC3 appended) is recognised and upgraded in place (the header still holds the pre-table values, so --revert
stays exact).
v3 2026-10-16 (Crosswind 213): ADD = (0xC3, 0xC4, 0xC2) - 0xC2 'Crosswind' gets a persistent aura (Ability.pfs record 204
tag 8, patch_crosswind_ability_pfs_v1.py v2: xwind_status, short mote spiral).  A live v2 is upgraded in place (header
unchanged -> --revert stays exact).
v4 2026-10-19 (Tame Animal): ADD = (0xC3, 0xC4, 0xC2, 0xCA) - 0xCA 'Tamed' gets its overhead green bear-paw badge
(Ability.pfs record 212 tag 8 = DualDF 7260..7271, patch_tame_ability_pfs_v3.py).  ROOT CAUSE of 'no paw above the tamed
unit': tactical combat never draws through AoWEPACK's TAbstractUnit overlay routine (0x557812EC; patch_tame_animal_v2's
ICO hook @0x5578175B only serves the strategic/autocombat draw) - TTacticalCombatUnitHS.Show uses THIS id table.  A live
v3 is upgraded in place (header unchanged -> --revert stays exact).
Zone AoWTCPCK 0x444000..0x444400 (verified zero, reloc-free).  Dry-run default; --apply / --revert; --dll <copy>.
Backup <game>\backup\AoWTCPCK.dll.bak_suspoverlay.  While applied, patch_rot_overlay_v1.py's dry-run reports its
sites as OTHER (expected) - revert this first to touch it.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_rot_overlay_v1 import relocs

DLL = game_file("AoWTCPCK.dll")
CODE_V2F = 0x400C00
ZONE, ZONE_END = 0x444000, 0x444400
TABLE = ZONE + 0x10
ADD = (0xC3, 0xC4, 0xC2, 0xCA)     # v2: + Static Shield 0xC4; v3: + Crosswind 0xC2; v4: + Tamed 0xCA
RD1, RD2, BOUND, LOOP = 0x4227B6, 0x4227DC, 0x422BCC, 0x4228A1
CONTEXT = {RD1 - 3: bytes.fromhex("8b1485"), RD2 - 3: bytes.fromhex("8b1485"), LOOP - 3: bytes.fromhex("837dd0")}


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DLL); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    u32 = lambda va: struct.unpack_from("<I", d, va - CODE_V2F)[0]
    for va, b in CONTEXT.items(): assert g(va, len(b)) == b, "unexpected code @%#x" % va
    zl = g(ZONE, ZONE_END - ZONE); applied = any(zl)
    rd1, rd2, (b0, b1), loop = u32(RD1), u32(RD2), struct.unpack_from("<ii", d, BOUND - CODE_V2F), g(LOOP, 1)[0]
    if applied:
        prev_tab, prev_b1, prev_loop = struct.unpack_from("<IiB", zl, 0)
    else:
        assert rd1 == rd2 and b0 == 0 and b1 == loop - 1, "overlay sites inconsistent: rd %#x/%#x bound %d,%d loop %d" % (rd1, rd2, b0, b1, loop)
        prev_tab, prev_b1, prev_loop = rd1, b1, loop
    def tab_va_to_off(va):                         # the table may sit in CODE (0x43xxxx) or DATA (0x4675B8 vanilla)
        pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; ns = struct.unpack_from("<H", d, pe + 6)[0]
        for k in range(ns):
            vs, rva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
            if rva <= va - 0x400000 < rva + max(vs, rs): return ro + va - 0x400000 - rva
        raise ValueError(hex(va))
    ids = [struct.unpack_from("<I", d, tab_va_to_off(prev_tab) + 4 * k)[0] for k in range(prev_loop)]   # the table we replaced
    assert not any(x in ids for x in ADD), "an ADD id is already in the pre-existing overlay table"
    new_ids = ids + list(ADD)
    n = len(new_ids)
    zone = struct.pack("<IiB", prev_tab, prev_b1, prev_loop).ljust(0x10, b"\0") + struct.pack("<%dI" % n, *new_ids)
    want = {RD1: struct.pack("<I", TABLE), RD2: struct.pack("<I", TABLE), BOUND: struct.pack("<ii", 0, n - 1), LOOP: bytes([n])}
    st = "ours" if all(g(va, len(b)) == b for va, b in want.items()) else ("vanilla-or-rot" if not applied else
         "ours(old)" if rd1 == TABLE and rd2 == TABLE and b0 == 0 and b1 == loop - 1 else "OTHER")
    zstate = ("zero" if not applied else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else
              "ours(old)" if zl[:0x10] == zone[:0x10] else "DIFFERS")
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END]
    print("overlay ids %s | sites %s (rd %#x, bound %d,%d, loop %d) | zone %s | relocs in zone %s"
          % (" ".join("%X" % i for i in new_ids), st, rd1, b0, b1, loop, zstate, bad or "none"))
    if bad or st == "OTHER" or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if not applied: print("already reverted"); return 0
        struct.pack_into("<I", d, RD1 - CODE_V2F, prev_tab); struct.pack_into("<I", d, RD2 - CODE_V2F, prev_tab)
        struct.pack_into("<ii", d, BOUND - CODE_V2F, 0, prev_b1); d[LOOP - CODE_V2F] = prev_loop
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(d)); print("reverted"); return 0
    if st == "ours" and zstate == "ours": print("already applied"); return 0
    if "old" in st or "old" in zstate: print("older build of this patch found -> upgrading in place")
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, b in want.items(): out[va - CODE_V2F:va - CODE_V2F + len(b)] = b
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_suspoverlay")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
