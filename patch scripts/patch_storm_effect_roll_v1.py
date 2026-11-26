#!/usr/bin/env python3
r"""
Strategic-map storm / Poison Plant debuffs roll against Resistance (AoWEPACK.dll, 2026-09-15).
Port of BXL's Ziggurat build_stormeffectroll.py (2026-07-30, untested by him) to the 410 dll.

Vanilla: TArmy.IncommingStorm 0x557904B4 -> per unit TAbstractUnit.ExecuteStormDamage 0x55780668:
  1. typed base damage via ExecuteDamageRole (immunity -> 0, protection -> half);
  2. if damage > 0: TAbstractUnit.ExecuteDamageEffects(eax=unit, dx=mask) @0x55781E28 applies the
     storm's status OUTRIGHT: Pestilence 0x10 -> Poisoned (0x60), Death Storm 0x20 -> Cursed (0x5D),
     Divine Storm 0x40 -> Vertigo (0x62).  Only immunity is stripped (`mask &= ~GetImmunityTypes`);
     Resistance and partial protections are never consulted.  PoisonP.TPoisonPlant.TriggerArmyDamage
     @0x557C41D2 is the only other caller (mask 0x10).  Holy/Unholy Ground never call it.
Tactical combat instead uses TAbstractUnit.ExecuteDamageEffectsRole(eax=unit, dx=mask) -> AX
@0x55781BA4, which per bit skips the immunity ability, adds the protection bonus to RES (+3 in this
build, see 0x55781CD0) and rolls through our roll cave @0x5580FC00 (poison str 3, death 4, holy 3;
the vanilla HitRole chance is clamp(50 + 10*(str - RES), 10, 90)); machines never get Vertigo
(GetUnitType == 2 gate @0x55781DA0).  It returns the surviving bits with the SAME bit values as its
input mask and applies nothing.

Fix (BXL's shape): hook the entry of ExecuteDamageEffects (8 B prologue `53 56 57 51 66 89 14 24`
-> `E9 rel32 90 90 90`) into a 27-byte position-independent cave:
    and  dx, 0x70                    ; only poison/death/holy can reach the strategic map
    push eax
    call ExecuteDamageEffectsRole    ; AX = bits that passed the RES roll
    mov  dx, ax
    pop  eax
    push ebx / esi / edi / ecx ; mov [esp], dx     ; replayed prologue
    jmp  0x55781E30
so the original body applies only the survivors.  No recursion (the Role function never calls
ExecuteDamageEffects); tactical combat is untouched (it reaches the Role function via combat VMT+0x118).
rel32 only, no data refs -> safe under DLL rebasing; no .reloc entries in the hook or cave range.

Behaviour change: Pestilence / Death Storm / Divine Storm / Poison Plant debuffs are now probabilistic
(RES 5 -> 50%, RES 7 -> 30%, RES >= 9 -> 10%, RES <= 4 -> 90%), matching protection gives +3 RES,
machines never get Vertigo.  Damage and immunity behaviour unchanged.

Cave 0x55816180 (0x40 reserved, verified zero 2026-09-15).  Backup AoWEPACK.dll.bak_stormroll.
Dry-run default; --apply; --revert (restores the backup by same-size in-place write).
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_stormroll"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x55700000

HOOK_VA = 0x55781E28
HOOK_ORIG = bytes.fromhex("5356575166891424")      # push ebx/esi/edi/ecx; mov [esp],dx
RESUME_VA = 0x55781E30
FN_ROLE = 0x55781BA4                                # ExecuteDamageEffectsRole(eax=self, dx=mask) -> AX
ROLE_HEAD = bytes.fromhex("535657558 3c4f866891424".replace(" ", ""))   # its prologue, asserted
CAVE_VA, CAVE_LIMIT = 0x55816180, 0x40
KEEP_MASK = 0x0070


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def build_cave(va):
    c = b""
    c += bytes.fromhex("6683e270")                          # and dx, 0x70
    c += b"\x50"                                            # push eax
    c += b"\xE8" + rel32(va + len(c), FN_ROLE)              # call ExecuteDamageEffectsRole
    c += bytes.fromhex("668bd0")                            # mov dx, ax
    c += b"\x58"                                            # pop eax
    c += bytes.fromhex("53565751")                          # push ebx; push esi; push edi; push ecx
    c += bytes.fromhex("66891424")                          # mov [esp], dx
    c += b"\xE9" + rel32(va + len(c), RESUME_VA)            # jmp resume
    assert len(c) == 27, len(c)
    return c


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        vs, va0, rs, ra = struct.unpack_from("<IIII", s, 8)
        if va0 <= va - BASE < va0 + max(vs, rs):
            return ra + (va - BASE - va0)
    raise ValueError(hex(va))


def relocs_in(d, lo, hi):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    hits = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        if s[:6] != b".reloc":
            continue
        rs, ra = struct.unpack_from("<II", s, 16)
        p, end = ra, ra + rs
        while p + 8 <= end:
            pr, sz = struct.unpack_from("<II", d, p)
            if sz == 0:
                break
            for q in range(p + 8, p + sz, 2):
                w = struct.unpack_from("<H", d, q)[0]
                if w >> 12 == 3:
                    va = BASE + pr + (w & 0xFFF)
                    if lo <= va < hi:
                        hits.append(va)
            p += sz
    return hits


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data)


def main():
    ap = argparse.ArgumentParser(description="storm/poison-plant debuffs roll vs Resistance")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        bak = open(bak_path(dll, BAK), "rb").read()
        assert len(bak) == os.path.getsize(dll), "size differs from backup; refusing"
        write_inplace(dll, bak); print("restored AoWEPACK.dll from" + BAK); return 0

    d = bytearray(open(dll, "rb").read())
    ho, co, ro = va2off(d, HOOK_VA), va2off(d, CAVE_VA), va2off(d, FN_ROLE)
    cave = build_cave(CAVE_VA)
    hook = b"\xE9" + rel32(HOOK_VA, CAVE_VA) + b"\x90" * 3
    cur = bytes(d[ho:ho + 8])
    assert bytes(d[ro:ro + len(ROLE_HEAD)]) == ROLE_HEAD, "ExecuteDamageEffectsRole prologue changed; refusing"
    print("hook  %#x: %s" % (HOOK_VA, cur.hex()))
    print("cave  %#x: %d B  %s" % (CAVE_VA, len(cave), cave.hex()))
    if cur == hook and bytes(d[co:co + len(cave)]) == cave:
        print("ALL ALREADY PATCHED"); return 0
    assert cur == HOOK_ORIG, "hook site is neither vanilla nor ours: " + cur.hex()
    zone = bytes(d[co:co + CAVE_LIMIT])
    assert zone == b"\0" * CAVE_LIMIT, "cave zone %#x is not zero - someone else owns it" % CAVE_VA
    r = relocs_in(d, HOOK_VA, HOOK_VA + 8) + relocs_in(d, CAVE_VA, CAVE_VA + CAVE_LIMIT)
    assert not r, "reloc entries intersect: " + ", ".join(hex(x) for x in r)
    print("checks OK: vanilla prologue, zero cave, no relocs")
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWEPACK.dll" + BAK)
    d[ho:ho + 8] = hook
    d[co:co + len(cave)] = cave
    write_inplace(dll, bytes(d))
    back = open(dll, "rb").read()
    assert back[ho:ho + 8] == hook and back[co:co + len(cave)] == cave, "read-back failed"
    print("applied.  Test: cast Pestilence / Death Storm / Divine Storm (or park a stack on a Poison Plant)"
          " on a high-RES stack - some units now take damage without the debuff; immune units unchanged;"
          " machines never get Vertigo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
