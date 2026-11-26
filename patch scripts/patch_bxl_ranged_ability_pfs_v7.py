#!/usr/bin/env python3
r"""Release\Ability.pfs record 214 v7 = Hurl Skull (0xCC) - explosion 20 % smaller - 2026-10-19.  User on v6/art v7:
"make the explosion about 20 % smaller".  Only tag 8 slot 2 (the impact helper 0xCC01) changes:

  v6 slot 2:  CHAIN  DUALDF 7680-7709 skull_death_burst (MULTIPLY, 274x258 at -131/-142)
                  -> EXPLBIG.ILB 0-29 (Self Destruct's own frames, record 75 slot 0: mode / timing / anchor -131/-142)
  v7 slot 2:  CHAIN  DUALDF 7710-7739 skull_death_burst80 (the same death layer scaled to 80 %: 219x206)
                  -> DUALDF 7740-7769 explbig80 (Self Destruct's ExplBig 0-29 COPIED and scaled to 80 %, drawMode 514
                     and the vanilla per-frame blends 100 x21 / 95..20 kept by the fx-builder rows)
              both at -105/-113 (= the vanilla impact point 131/142 x 0.8), with vanilla EXPLBIG's kind / f8 / f18 / f20
              (same 30-frame lifetime and timing).  ExplBig.ILB itself is NOT touched (Self Destruct keeps its blast).
States: v6 (slot 2 = burst 7680.. + EXPLBIG) -> v7; --revert = the exact pre-v7 record, kept in
<game>\backup\Release\Ability.pfs.rec214_pre_v7 at apply.  Needs the DualDF frames 7710-7769 (fx builder v8 rows,
build_dual_sphere_fx_v1.py --apply).  LIFO: revert this before pfs v6 (v6 sees v7 as FOREIGN and refuses).
Dry-run default; --pfs <copy> = scratch.  One-time safety copy .bak_bxlranged7.
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
import spellgfx as G
from patch_seekerbolts_pfs_v1 import fields, build_record, replace
import patch_bxl_ranged_ability_pfs_v1 as V1
import patch_bxl_ranged_ability_pfs_v6 as V6

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_bxlranged7"
K_SKULL = V1.K_SKULL
DF = V6.DF
BURST80, EXPL80 = list(range(7710, 7740)), list(range(7740, 7770))
XS80, YS80 = -105, -113                      # vanilla impact anchor -131/-142 scaled by 0.8 (219x206 canvas)


def v7_rec(raw, prev):
    order, vals = fields(prev)
    assert order == [5, 6, 7, 8, 9]
    slots = list(G.seq_parse(vals[8]))
    assert len(slots) == 41 and slots[2] and slots[2]["frames"] == V6.BURST, "record 214 slot 2 is not the v6 burst chain"
    ex = V6.explosion_vanilla(raw)
    burst = G.seq_entry(DF, BURST80, XS80, YS80, kind=ex["kind"], f8=ex["f8"], f18=ex["f18"], f20=ex["f20"])
    expl = G.seq_entry(DF, EXPL80, XS80, YS80, kind=ex["kind"], f8=ex["f8"], f18=ex["f18"], f20=ex["f20"])
    slots[2] = V6.chain(burst, expl)
    vals = dict(vals)
    vals[8] = G.seq_build(slots); assert G.seq_parse(vals[8]) == slots
    return build_record(order, vals)


def is_v7(rec):
    s = G.seq_parse(fields(rec)[1][8])
    return len(s) > 3 and s[2] and s[2]["frames"] == BURST80 and s[2].get("chain") and s[2]["chain"]["frames"] == EXPL80


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw
    ks = V1.keys(raw)
    if K_SKULL not in ks: print("record 214 absent - apply patch_bxl_ranged_ability_pfs_v1.py first"); return 1
    cur = R.rec_of(raw, K_SKULL)
    live = os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs")))
    side = bak_path(PFS, ".rec214_pre_v7") if live else PFS + ".rec214_pre_v7"
    if is_v7(cur):
        if not os.path.exists(side): print("ABORT - v7 record present but no pre-v7 copy %s" % side); return 1
        prev = open(side, "rb").read(); want = v7_rec(raw, prev); st = "v7" if cur == want else "FOREIGN"
    elif V6.is_v6(cur):
        prev = cur; want = v7_rec(raw, cur); st = "v6"
    else:
        print("ABORT - record 214 is neither v6 nor v7 (apply patch_bxl_ranged_ability_pfs_v6.py first)"); return 1
    print("Ability.pfs record 214: %s (v7: slot 2 = death burst DualDF %d.. + 80 %% ExplBig DualDF %d.. at %d/%d)"
          % (st, BURST80[0], EXPL80[0], XS80, YS80))
    if st == "FOREIGN": print("ABORT - record 214 differs from the v7 build of its saved pre-v7 copy"); return 1
    if revert:
        if st != "v7": print("not applied"); return 0
        raw = replace(raw, K_SKULL, prev)
    else:
        if st == "v7": print("already applied"); return 0
        raw = replace(raw, K_SKULL, want)
    R.load(raw)
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks if k != K_SKULL and k > 12), "another record changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert" if revert else "apply", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if live and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    if not revert:
        with open(side, "wb") as f: f.write(prev)
    with open(PFS, "r+b") as f:
        f.seek(0); f.write(raw); f.truncate(len(raw))
    print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
