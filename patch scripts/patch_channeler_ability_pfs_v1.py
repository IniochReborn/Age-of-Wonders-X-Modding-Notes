#!/usr/bin/env python3
r"""Release\Ability.pfs record 213 = Channeler I/II/III (ability 0xCB, 2026-10-18; engine = patch_channeler_v1.py).

Shape = Evoker's record 182 (tags 5 / 6 / 7 / 8 / 9): tag 5 new description, tag 6 skill cost 10 (fills
[ability+0x14]; the per-level costs come from the engine's TIntegerList = 10/10/10), tags 7 / 8 copied from 182
(no sound / no gfx), tag 9 offer mask 0x3FE (= Spell Casting's record 62 mask).  Appended as the new largest key
(212 Tamed must be the current largest - Tame's "212 must stay highest" note only guards Tame's own revert; this
script is LIFO on top of it: revert this before patch_tame_ability_pfs_v2.py --revert).
Loads the LIVE file every run (R.load / R.assemble; nothing cached).  --revert removes 213 (must still be the
largest key).  Dry-run default; --pfs <copy> = scratch.  One-time safety copy
<game>\backup\Release\Ability.pfs.bak_channeler.
After applying: LADDER += 0xCB in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py, re-run both
with --apply (bound 0xCB -> 0xCC).
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record
from patch_tame_ability_pfs_v1 import remove

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_channeler"
KEY, DONOR, PREV_MAX = 0xCB + 10, 0xAC + 10, 0xCA + 10          # 213 Channeler, 182 Evoker, 212 Tamed
DESC = ("Increases the Mana the Hero is able to channel each turn. Has no effect without Spell Casting.\r\n"
        "I: Channeling +30%\r\nII: Channeling +50%\r\nIII: Channeling +100%\r\n")
COST, MASK = 10, 0x3FE


def new_rec(raw):
    order, vals = fields(R.rec_of(raw, DONOR))
    assert order == [5, 6, 7, 8, 9], "record %d is not the expected Evoker record (%s)" % (DONOR, order)
    d = DESC.encode("latin-1")
    vals = dict(vals)
    vals[5] = struct.pack("<I", len(d)) + d
    vals[6] = struct.pack("<I", COST)
    vals[9] = struct.pack("<H", MASK)
    return build_record(order, vals)


def keys(raw):
    _p, _pre, smalls, wides, _b = R.load(raw)
    return [i for i, _ in smalls] + [i for i, _ in wides]


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw; ks = keys(raw)
    rec = new_rec(raw)
    st = "absent" if KEY not in ks else "ours" if R.rec_of(raw, KEY) == rec else "FOREIGN"
    print("Ability.pfs: %d records, highest key %d | 213 Channeler: %s" % (len(ks), max(ks), st))
    if st == "FOREIGN": print("ABORT - record 213 exists with other content (editor resave? compare first)"); return 1
    if revert:
        if st == "absent": print("nothing to revert"); return 0
        assert max(ks) == KEY, "record 213 is followed by foreign keys - revert those first (LIFO)"
        raw = remove(raw, KEY)
    else:
        if st == "ours": print("already applied"); return 0
        assert max(ks) == PREV_MAX, "record 212 (Tamed) must be the largest key before 213 is appended (highest %d)" % max(ks)
        payload, pre, smalls, wides, body = R.load(raw)
        raw = R.assemble(raw, payload, pre, smalls, list(wides) + [(KEY, len(body))], body + rec)
        assert R.rec_of(raw, KEY) == rec
    R.load(raw)
    others = [k for k in keys(raw0) if k != KEY and k > 12]
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in others), "another record changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert" if revert else "apply", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
