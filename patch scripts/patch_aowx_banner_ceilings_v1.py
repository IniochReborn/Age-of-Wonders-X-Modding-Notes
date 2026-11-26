#!/usr/bin/env python3
r"""
AoWx.exe banner popups: raise the two ability-id ceilings so the new abilities are listed (2026-09-15).

Symptom: right-click a unit in the unit panel (or hover it) and the unit banner popup lists its
abilities -- but never Magic Sight (0xAA), Evoker (0xAC), Conjurer (0xAD), Enchanter (0xAE) or
Ritualist (0xAF), although the full Unit dialog shows them.  The item banner popup has the same hole
for items granting those abilities.

Same vanilla idiom as patch_tcablist_ceiling_v1.py (AoWTCPCK.dll) and BXL's build_abilityid_ceilings.py
(Ziggurat, sites A4/A5 of his ID_Ceilings.md audit): "for id := lo to 0xA9: if enabled(id) then add",
compiled as `inc reg; cmp reg,0xAA; jne body`.  0xAA = highest vanilla id + 1, so everything minted
above 0xA9 is silently skipped.  Two sites in AoWx.exe (fixed base 0x400000, no .reloc, immediates
carry nothing):

    0x00455DE1  81 fb aa 00 00 00   cmp ebx,0xAA   unit banner popup (loop ids 0..0xA9, `xor ebx,ebx`
                                                   @0x455D43; body asks unit VMT+0x148 per id, then
                                                   ability VMT+0x98 GetControlType to pick the list)
    0x00406DEF  81 fe aa 00 00 00   cmp esi,0xAA   TItemBanner popup (loop ids 1..0xA9, `mov esi,1`
                                                   @0x406DA6; body asks item VMT+0x88 per id)

Over-iterating is harmless (TAbilityControl.GetAbility returns nil past the count and the bitset
readers fail closed), but the bound is kept at exactly "highest id in Release\Ability.pfs + 1" so a
dry run doubles as the drift check: when a new ability id is minted, re-run this AND
patch_tcablist_ceiling_v1.py.  Not touched: the four TCAI.EvalBattle scans in AoWTCPCK.dll (need
BXL's AbilTypes relocation first).

Backup AoWx.exe.bak_bannerceil.  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_GAME = game_dir()
BAK = ".bak_bannerceil"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
LADDER = (0xAA, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE)                 # values accepted as a base: vanilla, the 410 Ritualist ceiling (append ours as they ship)

# (VA of the cmp, opcode prefix before the imm32, description)
SITES = [
    (0x00455DE1, bytes.fromhex("81fb"), "unit banner popup (right-click / hover in the unit panel)"),
    (0x00406DEF, bytes.fromhex("81fe"), "TItemBanner popup"),
]
# loop initialisers the docstring relies on -- asserted unchanged, never written
INITS = [
    (0x00455D43, bytes.fromhex("33db"),       "unit banner loop starts at id 0"),
    (0x00406DA6, bytes.fromhex("be01000000"), "item banner loop starts at id 1"),
]


def va2off(d, va, base=0x400000):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
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
    ap = argparse.ArgumentParser(description="raise the AoWx.exe banner popup ability-id ceilings")
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    exe = os.path.join(a.game, "AoWx.exe")
    if a.revert:
        if not os.path.exists(bak_path(exe, BAK)):
            print("no backup"); return 1
        bak = open(bak_path(exe, BAK), "rb").read()
        assert os.path.getsize(exe) == len(bak), "size differs from backup - not a same-size revert; refusing"
        with open(exe, "r+b") as f:
            f.seek(0); f.write(bak)
        print("restored AoWx.exe from" + BAK); return 0

    d = bytearray(open(exe, "rb").read())
    for va, want, desc in INITS:
        o = va2off(d, va)
        assert bytes(d[o:o + len(want)]) == want, "%s changed @%#x - refusing" % (desc, va)

    hi = highest_ability_id(os.path.join(a.game, "Release", "Ability.pfs"))
    target = hi + 1
    print("Ability.pfs highest id 0x%02X -> bound target 0x%02X" % (hi, target))
    todo = []
    for va, prefix, desc in SITES:
        o = va2off(d, va)
        assert bytes(d[o:o + len(prefix)]) == prefix, "%s: not the expected cmp reg,imm32 @%#x" % (desc, va)
        cur = struct.unpack_from("<I", d, o + len(prefix))[0]
        state = "patched" if cur == target else ("vanilla" if cur == LADDER[0] else "UNKNOWN")
        print("  %#010x  bound 0x%02X (%s)  %s" % (va, cur, state, desc))
        if cur == target:
            continue
        if cur not in LADDER and cur < target:
            print("    bound 0x%02X is neither vanilla nor a value this script wrote - inspect first" % cur); return 1
        todo.append((o + len(prefix), cur))
    if not todo:
        print("ALL ALREADY PATCHED"); return 0
    hidden = [i for i in range(min(c for _, c in todo), target)]
    print("currently hidden from the popups: " + ", ".join("0x%02X" % i for i in hidden))
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(exe, BAK)):
        shutil.copyfile(exe, bak_path(exe, BAK)); print("backup: AoWx.exe" + BAK)
    for o, _ in todo:
        struct.pack_into("<I", d, o, target)
    with open(exe, "r+b") as f:                      # same-size in-place write (see project notes)
        f.seek(0); f.write(d)
    back = open(exe, "rb").read()
    for o, _ in todo:
        assert struct.unpack_from("<I", back, o)[0] == target, "read-back failed @file %#x" % o
    print("applied: %d site(s) -> 0x%02X.  Test: right-click a hero with Evoker/Conjurer/Enchanter/Ritualist"
          " in the unit panel - the banner lists them; an item granting one of them shows it in the item popup."
          % (len(todo), target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
