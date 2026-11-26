#!/usr/bin/env python3
r"""Release\Ability.pfs record 214 (Hurl Skull, ability 0xCC): point cost (tag 6) 12 -> 15 (user 2026-10-24).

Only tag 6 changes; every other tag of the live record is kept byte-for-byte.  Backup
<game>\backup\Release\Ability.pfs.bak_hskcost.  Dry run by default; --apply / --revert (writes the old cost back).
Note: patch_bxl_ranged_ability_pfs_v7.py rebuilds record 214 from its pre-v7 copy - re-running it would undo this.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record, replace

PFS = game_file(os.path.join("Release", "Ability.pfs"))
KEY, OLD, NEW = 214, 12, 15


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    raw = open(PFS, "rb").read()
    rec = R.rec_of(raw, KEY)
    order, vals = fields(rec)
    assert vals[5][4:4 + 11] == b"Hurls a sku", "record 214 is not Hurl Skull"
    cur = struct.unpack("<I", vals[6])[0]
    want = OLD if revert else NEW
    print("Ability.pfs record %d (Hurl Skull) cost: %d -> %d" % (KEY, cur, want))
    if cur == want: print("already %s" % ("reverted" if revert else "applied")); return 0
    if cur not in (OLD, NEW): print("ABORT - unexpected cost %d" % cur); return 1
    vals = dict(vals); vals[6] = struct.pack("<I", want)
    new = replace(raw, KEY, build_record(order, vals))
    if not apply and not revert: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(PFS, ".bak_hskcost")
    if not os.path.exists(bak): shutil.copy2(PFS, bak); print("backup ->", bak)
    with open(PFS, "r+b") as f:                      # in-place (house rule)
        f.write(new); f.truncate()
    assert open(PFS, "rb").read() == new
    print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
