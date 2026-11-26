#!/usr/bin/env python3
r"""
AoWEPACK.dll: Angel Wings (ability 0xBD) gets the "fly up / down a level" button too (2026-11-16).

User: "units can travel between sky levels with flying ... they should be able to do this with angel wings
spell/ability too".

patch_fly_levels_v1 puts the level-flight action on the FLYING ability object only: TMovementAbility VMT slots
+0x98 GetControlType / +0xB4 Activate -> block handlers 0x558CA7E0 / 0x558CA650, each starting with
`cmp [ability+0xC],1 / jne <vanilla>`.  The party test inside (0x558CA47A) uses unit GetAbilityEnabled(1)
(VMT+0x148), which Angel Wings already satisfies (implied Flying) - but an Angel Wings unit has no Flying ability
icon, so there was nothing to click.

Angel Wings 0xBD is an instance of TWaterWalkingEnchantment (VMT 0x557B8CF0, shared with Water Walking and
Swampwalk; both slots hold the same vanilla defaults 0x5574E730 / 0x5574EF68 as TMovementAbility did).
  VMT+0x98 (0x557B8D88) -> ctl: cmp [eax+0xC],0xBD / jne 0x5574E730 / jmp 0x558CA7EA   (handler body, past its id test)
  VMT+0xB4 (0x557B8DA4) -> act: cmp [eax+0xC],0xBD / jne 0x5574EF68 / jmp 0x558CA65A
Caves 0x558CAE80.. in the fly zone tail (zero).  Same rules as for flyers: every selected unit must be able to fly,
4 movement points, standing on Sky/Chasm.  The two slots carry relocs (kept: we store un-rebased VAs); caves are
rel32 only.  Needs patch_fly_levels_v1 + patch_angelwings_v1.  Backup .bak_flyangel.  Dry run; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, V2F, BAK_SUFFIX = game_file("AoWEPACK.dll"), 0x55700C00, ".bak_flyangel"
ABIL = 0xBD
CAVE = 0x558CAE80
# slot VA, vanilla value, fly handler, handler body (after `cmp [eax+0xC],1 / jne rel32` = 10 B)
SLOTS = [(0x557B8D88, 0x5574E730, 0x558CA7E0), (0x557B8DA4, 0x5574EF68, 0x558CA650)]
MOVE_SLOTS = [(0x557B7374, 0x558CA7E0), (0x557B7390, 0x558CA650)]     # must already point at the fly handlers


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    out, where = b"", []
    for _slot, vanilla, handler in SLOTS:
        va = CAVE + len(out); where.append(va)
        out += bytes(ks.asm("cmp dword ptr [eax+0xc], %#x; jne %#x; jmp %#x" % (ABIL, vanilla, handler + 10), va)[0])
        out += b"\x00" * (-len(out) % 16)
    return out, where


def relocs(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return set(ib + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    code, where = build()
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    u = lambda va: struct.unpack_from("<I", d, va - V2F)[0]
    for slot, h in MOVE_SLOTS:
        if u(slot) != h: print("ABORT: patch_fly_levels_v1 not applied (slot %#x = %#x)" % (slot, u(slot))); return 1
    for _s, vanilla, h in SLOTS:
        want = b"\x83\x78\x0c\x01\x0f\x85" + struct.pack("<i", vanilla - (h + 10))
        if g(h, 10) != want: print("ABORT: fly handler %#x does not start with the expected id test" % h); return 1
    cur_slots, cur_code = [u(s) for s, _v, _h in SLOTS], g(CAVE, len(code))
    state = ("vanilla" if cur_slots == [v for _s, v, _h in SLOTS] and not any(cur_code) else
             "ours" if cur_slots == where and cur_code == code else "OTHER")
    print("slots %s | cave %#x (%d B) -> %s" % ([hex(x) for x in cur_slots], CAVE, len(code), state))
    if state == "OTHER": print("ABORT"); return 1
    if state == "vanilla" and any(g(CAVE - 0x10, 0x60)): print("ABORT: cave zone not empty"); return 1
    rl = relocs(DLL)
    if any(s not in rl for s, _v, _h in SLOTS): print("ABORT: a VMT slot has no reloc"); return 1
    if any(CAVE - 3 <= r < CAVE + len(code) for r in rl): print("ABORT: relocs in the cave"); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    ws = [(CAVE, bytes(len(code)) if a.revert else code)]
    ws += [(s, struct.pack("<I", v if a.revert else w)) for (s, v, _h), w in zip(SLOTS, where)]
    with open(DLL, "r+b") as f:                      # in-place (house rule)
        for va, b in ws:
            d[va - V2F:va - V2F + len(b)] = b; f.seek(va - V2F); f.write(b)
    assert open(DLL, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
