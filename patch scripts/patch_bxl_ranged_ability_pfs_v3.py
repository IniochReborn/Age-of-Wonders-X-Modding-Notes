#!/usr/bin/env python3
r"""Release\Ability.pfs record 215 v3 = Shoot Black Javelin (0xCD) art - 2026-10-19 (user: "revise shoot black javelin
gfx to have a slight black glow/tail").  Record 214 (Hurl Skull) is untouched (pfs v2).

  215 tag 8 slots 0..23 (the kind-1 per-direction projectile images, frame k = 15*k deg clockwise from north):
        vanilla  TCOMBAT\OBJECTS\ARROW.ILB 300+k   (kind 0 single image, xs -32 / ys -32)
        v3       EFFECTS\DUALDF.ILB        7430+k  (same kind / anchor / flags - only name + image id change)
      7430-7453 = build_dual_sphere_fx_v1.black_javelin(): the vanilla sprite on top of a soft near-black halo and a
      short smoky tail streaming back from the fletching (same 64x64 canvas).  Slot 40 (panel icon) unchanged.
States: vanilla art -> applied in place (same key/position); v3 -> 'already applied'; --revert rebuilds the ARROW.ILB
entries (exact: every other field of each slot is kept).  Needs the DualDF frames (run build_dual_sphere_fx_v1.py
--apply first).  LIFO: revert this before re-running / reverting patch_bxl_ranged_ability_pfs_v1.py (its record-215
check expects the vanilla art).  Dry-run default; --pfs <copy> = scratch.  Safety copy .bak_bxlranged3.
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
import spellgfx as G
from patch_seekerbolts_pfs_v1 import fields, build_record, replace
import patch_bxl_ranged_ability_pfs_v1 as V1

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_bxlranged3"
K_JAV = V1.K_JAV                                           # 215
B = chr(92)
VAN_NAME, NEW_NAME = "TCOMBAT" + B + "OBJECTS" + B + "ARROW.ILB", "EFFECTS" + B + "DUALDF.ILB"
VAN0, NEW0, N = 300, 7430, 24


def rebuild(rec, name, base):
    order, vals = fields(rec)
    slots = list(G.seq_parse(vals[8]))
    for k in range(N):
        e = dict(slots[k]); e["name"] = name; e["f20"] = base + k; slots[k] = e
    vals = dict(vals); vals[8] = G.seq_build(slots)
    return build_record(order, vals)


def state(rec):
    slots = G.seq_parse(fields(rec)[1][8])
    if all(s and s["kind"] == 0 and s["name"].upper() == VAN_NAME and s["f20"] == VAN0 + k for k, s in enumerate(slots[:N])):
        return "vanilla"
    if all(s and s["kind"] == 0 and s["name"].upper() == NEW_NAME and s["f20"] == NEW0 + k for k, s in enumerate(slots[:N])):
        return "v3"
    return "FOREIGN"


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw
    ks = V1.keys(raw)
    if K_JAV not in ks: print("record 215 absent - apply patch_bxl_ranged_ability_pfs_v1.py first"); return 1
    cur = R.rec_of(raw, K_JAV); st = state(cur)
    print("Ability.pfs record 215 (Shoot Black Javelin): %s (v3 slots 0-23 = DualDF %d-%d)" % (st, NEW0, NEW0 + N - 1))
    if st == "FOREIGN": print("ABORT - record 215 slots are neither vanilla ARROW.ILB nor ours"); return 1
    if revert:
        if st == "vanilla": print("not applied"); return 0
        new = rebuild(cur, VAN_NAME, VAN0)
    else:
        if st == "v3": print("already applied"); return 0
        new = rebuild(cur, NEW_NAME, NEW0)
        assert rebuild(new, VAN_NAME, VAN0) == cur, "revert would not be exact"
    raw = replace(raw, K_JAV, new)
    R.load(raw)
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks if k != K_JAV and k > 12), "another record changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert" if revert else "apply", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    with open(PFS, "r+b") as f:
        f.seek(0); f.write(raw); f.truncate(len(raw))
    print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
