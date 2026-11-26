#!/usr/bin/env python3
r"""Release\Ability.pfs for Tame Animal v4 (2026-10-19; data only).  In-place upgrade of patch_tame_ability_pfs_v3.py
(v3 must be applied); --revert puts the exact v3 bytes back.

User (v3 live): "Tame Animal HIT gfx ends too abruptly - have it fade out."
Record 211 (Tame Animal 0xC9) tag 8, three elements of Dominate's chain whose last frame was still bright:
  f8 2 and f8 5 (the 10-frame peak loop on the unit, Dominate's TWINKGR 232..236 x2): [7212..7216, 7212..7216]
       -> DualDF 7280..7289 = tame_hitfade (same frames, the second pass fading 1 -> .07)
  f8 1 (15 frames, ended on the gathering frame 8 at ~70 %): [340 x7, 7200..7206, 7208]
       -> [340 x7, 7200..7203, 7290..7293] = tame_castfade (twinkle 5-8 fading .75 -> .10)
Same frame counts / f8 / f18 / f20 / xs / ys -> the timing is untouched.  f8 6 (tame_mark) and f8 8 (tail) already
fade (v3).  Record 212 (Tamed overlay) unchanged here - the overhead badge needed an ENGINE fix (TCPCK overlay id
table, patch_tc_suspend_overlay_v1.py v4 adds 0xCA).

Needs DualDF.ILB ids 7280..7293 (build_dual_sphere_fx_v1.py with the _tame6_integration.txt rows).
Dry-run default; --apply / --revert; --pfs <copy> = scratch.  Safety copy <game>\backup\Release\Ability.pfs.bak_tame4.
LIFO: revert this BEFORE patch_tame_ability_pfs_v3.py.
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record, replace

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_tame4"
KEY_T = 0xC9 + 10
B = chr(92)
ILB = "EFFECTS" + B + "DUALDF.ILB"
LOOP3 = list(range(7212, 7217)) * 2
LOOP4 = list(range(7280, 7290))
CAST3 = [340] * 7 + list(range(7200, 7207)) + [7208]
CAST4 = [340] * 7 + list(range(7200, 7204)) + list(range(7290, 7294))
MAP = {1: (CAST3, CAST4), 2: (LOOP3, LOOP4), 5: (LOOP3, LOOP4)}


def walk(s):
    while s:
        yield s
        s = s.get("chain")


def conv(t8, to4):
    slots = G.seq_parse(t8); assert len(slots) == 1
    hit = set()
    for e in walk(slots[0]):
        if e["name"].upper() != ILB: return None
        if e["f8"] in MAP:
            src, dst = MAP[e["f8"]] if to4 else MAP[e["f8"]][::-1]
            if e["frames"] == src: e["frames"] = list(dst); hit.add(e["f8"])
    return G.seq_build(slots) if hit == set(MAP) else None


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw0 = open(PFS, "rb").read()
    order, vals = fields(R.rec_of(raw0, KEY_T)); t8 = vals[8]
    up, down = conv(t8, True), conv(t8, False)
    st = "v3" if up is not None else "v4" if down is not None else "FOREIGN"
    print("Ability.pfs | 211 Tame Animal gfx: %s" % st)
    if st == "FOREIGN": print("ABORT - record 211 tag 8 is neither v3 nor v4 (apply patch_tame_ability_pfs_v3.py first?)"); return 1
    want = "v3" if revert else "v4"
    if st == want: print("nothing to revert" if revert else "already applied"); return 0
    nv = dict(vals); nv[8] = up if not revert else down
    raw = replace(raw0, KEY_T, build_record(order, nv))
    R.load(raw)
    ks = lambda r: [k for k, _ in R.load(r)[2]] + [k for k, _ in R.load(r)[3]]
    assert ks(raw) == ks(raw0), "key set changed"
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks(raw0) if k != KEY_T and k > 12), "another record changed"
    a, b = fields(R.rec_of(raw, KEY_T)), fields(R.rec_of(raw0, KEY_T))
    assert a[0] == b[0] and all(a[1][t] == b[1][t] for t in a[0] if t != 8), "a tag other than 8 changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert -> v3" if revert else "apply -> v4", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(bk):
        shutil.copy2(PFS, bk); print("safety copy ->", bk)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
