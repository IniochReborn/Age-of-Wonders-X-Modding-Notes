#!/usr/bin/env python3
r"""
In-combat unit panel: raise the ability-id ceiling so the new abilities are listed (2026-09-14).

AoWTC.TTacticalCombatUnitHS.CreateTCAbList @0x00423430 (AoWTCPCK.dll, the file AoWx.exe imports;
the .dpl beside it is a different build and is not loaded) builds the panel's ability list with a
counted loop `for id := 1 to BOUND-1: if GetAbilityEnabled(id) then add`.  There is NO relevance
filter: the `test al,2` on GetControlType only decides Insert-at-front (selectable abilities)
versus Add-at-end.  The loop bound is a vanilla immediate 0xAA = "highest vanilla id + 1", so
every ability minted above 0xA9 -- Magic Sight 0xAA, Evoker 0xAC, Conjurer 0xAD, Enchanter 0xAE,
Ritualist 0xAF -- was silently absent from the panel while the full Unit dialog (which uses
GetCount) showed them.  Diagnosis and script shape after BXL's build_tcablist_ceiling.py.

This script sets the bound to (highest record id in Release\Ability.pfs - 10) + 1 = 0xB0 and
refuses to write a bound the live data has outgrown.  Walking (id 0) stays hidden because the
loop STARTS at 1 (`mov dword [ebp-8],1` @0x00423489 is asserted unchanged).  All ids listed
here are non-selectable (base GetControlType = 0: enhancement/enchantment abilities), so the
`bound eax,{0,169}` AbilTypes guard that selectable ids >169 would trip on a map click is not
reached (BXL's build_abiltypes_relocate.py lesson).  The immediate carries no relocation.

Not touched: the four TCAI.EvalBattle scans and the AoWx.exe banner/hover popups that BXL's
build_abilityid_ceilings.py raises (those also stop at 0xAA); raise them separately if wanted.

Backup AoWTCPCK.dll.bak_tcablist.  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_GAME = game_dir()
BAK = ".bak_tcablist"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BOUND_VA, BOUND_PREFIX = 0x0042354A, bytes.fromhex("817df8")      # cmp dword [ebp-8], imm32
INIT_VA, INIT_BYTES = 0x00423489, bytes.fromhex("c745f801000000")  # mov dword [ebp-8], 1
LADDER = (0xAA, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE)                                               # values this script accepts as a base (vanilla, the 410 Ritualist ceiling)


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    base = struct.unpack_from("<I", d, e + 24 + 28)[0]
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        vs, va0, rs, ra = struct.unpack_from("<IIII", s, 8)
        if va0 <= va - base < va0 + max(vs, rs):
            return ra + (va - base - va0)
    raise ValueError(hex(va))


def highest_ability_id(pfs_path):
    d = open(pfs_path, "rb").read()
    b = d[7]; p = 8
    nb, nd = b & 0x7F, 0
    if b & 0x80:
        nd = struct.unpack_from("<I", d, p)[0]; p += 4
    ids = []
    for _ in range(nb):
        ids.append(d[p]); p += 2
    for _ in range(nd):
        ids.append(struct.unpack_from("<I", d, p)[0]); p += 8
    return max(ids) - 10                             # record id = ability id + 10


def main():
    ap = argparse.ArgumentParser(description="raise the in-combat ability panel id ceiling")
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    dll = os.path.join(a.game, "AoWTCPCK.dll")
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        shutil.copyfile(bak_path(dll, BAK), dll); print("restored AoWTCPCK.dll"); return 0

    d = bytearray(open(dll, "rb").read())
    io_, bo = va2off(d, INIT_VA), va2off(d, BOUND_VA)
    assert bytes(d[io_:io_ + 7]) == INIT_BYTES, "loop init changed - Walking's exclusion depends on it; refusing"
    assert bytes(d[bo:bo + 3]) == BOUND_PREFIX, "bound site is not `cmp dword [ebp-8], imm32`"
    cur = struct.unpack_from("<I", d, bo + 3)[0]
    hi = highest_ability_id(os.path.join(a.game, "Release", "Ability.pfs"))
    target = hi + 1
    print("CreateTCAbList bound @%#x: current 0x%02X (lists ids 1..0x%02X); Ability.pfs highest id 0x%02X -> target 0x%02X"
          % (BOUND_VA, cur, cur - 1, hi, target))
    if cur == target:
        print("ALL ALREADY PATCHED"); return 0
    if cur not in LADDER and cur < target:
        print("bound 0x%02X is neither vanilla nor a value this script wrote - inspect first" % cur); return 1
    hidden = [i for i in range(cur, target)]
    print("currently hidden from the combat panel: " + ", ".join("0x%02X" % i for i in hidden))
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWTCPCK.dll" + BAK)
    struct.pack_into("<I", d, bo + 3, target)
    with open(dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied: bound 0x%02X -> 0x%02X.  Test: a hero with Evoker/Conjurer/Enchanter/Ritualist shows them in the"
          " in-combat unit panel; Walking still absent; Strike still first." % (cur, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
