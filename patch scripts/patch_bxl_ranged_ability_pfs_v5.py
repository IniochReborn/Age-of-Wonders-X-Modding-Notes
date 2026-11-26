#!/usr/bin/env python3
r"""v5 (2026-10-19, user: 'the explosion looks bad - polish it to the quality of the original'): the dark impact is
rebuilt at FULL size (274x258, vanilla's own canvas - Implosion's 280x280 DualDF sprite runs live, so the >=256-px
worry does not hold) as a crimson brighten FLASH (frames 0-3) + a MULTIPLY dark-crimson blast turning to soot (4-29)
(build_dual_sphere_fx_v1.dark_explosion2(), same ids 7460-7489) -> slot 2's anchor goes back to vanilla's -131/-142.
States: v2/v3 (EXPLBIG) or v4 (-115/-124) -> v5; --revert = back to the v4 slot (then v4's --revert -> EXPLBIG).
One-time safety copy .bak_bxlranged5.

Release\Ability.pfs record 214 v4 = Hurl Skull (0xCC) DARK impact - 2026-10-19 (user: "the gfx/sfx as a whole should
be evil, dark, gritty").  Only tag 8 slot 2 changes (the impact explosion drawn by the engine's kind-0x26 helper):

        v2/v3    EFFECTS\EXPLBIG.ILB 0-29  (Self Destruct's explosion, 274x258, bmBrighten 514), xs -131 / ys -142
        v4       EFFECTS\DUALDF.ILB  7460-7489  (build_dual_sphere_fx_v1.dark_explosion(): the same 30 frames
                 re-graded to black smoke + crimson fire, drawn bmAlpha 258, scaled to 240x226 because DualDF sprites
                 >= ~256 px wide crashed the game before), xs -115 / ys -124 (the anchor scaled by 240/274)
        every other field of the slot (kind 4, f8, f18, f20 timing, ft10) is kept -> 30 frames, same one-shot timing,
        so patch_bxl_ranged_abilities_v3's helper / skip logic is untouched.
Slot 0 (the projectile) keeps DualDF 7410-7421 - the v4 art (hurl_skull3) is rebuilt under the SAME ids by the fx
builder, so it needs no pfs change; record 215 (Shoot Black Javelin) likewise keeps 7430-7453 (black_javelin2 is
rebuilt there in drawMode 1026).  Sounds: SKULL_HIT.WAV / SKULL_SCREAM.WAV keep their names (rebuilt by the sfx builder).
States: v2/v3 (EXPLBIG) -> applied in place; v4 -> 'already applied'; --revert puts the EXPLBIG slot back (exact).
Needs the DualDF frames (build_dual_sphere_fx_v1.py --apply first).  LIFO: revert this before reverting
patch_bxl_ranged_ability_pfs_v2.py (its v2 state check expects the EXPLBIG slot).  Dry-run default; --pfs <copy> =
scratch.  One-time safety copy .bak_bxlranged4.
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
import spellgfx as G
from patch_seekerbolts_pfs_v1 import fields, build_record, replace
import patch_bxl_ranged_ability_pfs_v1 as V1

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_bxlranged5"
K_SKULL = V1.K_SKULL                                     # 214
B = chr(92)
VAN = ("EFFECTS" + B + "EXPLBIG.ILB", list(range(30)), -131, -142)
V4 = ("EFFECTS" + B + "DUALDF.ILB", list(range(7460, 7490)), -115, -124)
NEW = ("EFFECTS" + B + "DUALDF.ILB", list(range(7460, 7490)), -131, -142)


def rebuild(rec, spec):
    order, vals = fields(rec)
    slots = list(G.seq_parse(vals[8]))
    e = dict(slots[2]); e["name"], e["frames"], e["xs"], e["ys"] = spec[0], list(spec[1]), spec[2], spec[3]
    slots[2] = e
    vals = dict(vals); vals[8] = G.seq_build(slots)
    return build_record(order, vals)


def state(rec):
    s = G.seq_parse(fields(rec)[1][8])
    e = s[2] if len(s) > 2 else None
    if not e: return "FOREIGN"
    for nm, spec in (("v2/v3", VAN), ("v4", V4), ("v5", NEW)):
        if e["name"].upper() == spec[0].upper() and e["frames"] == spec[1] and (e["xs"], e["ys"]) == (spec[2], spec[3]):
            return nm
    return "FOREIGN"


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw
    ks = V1.keys(raw)
    if K_SKULL not in ks: print("record 214 absent - apply patch_bxl_ranged_ability_pfs_v1.py first"); return 1
    cur = R.rec_of(raw, K_SKULL); st = state(cur)
    print("Ability.pfs record 214 (Hurl Skull) slot 2: %s (v5 = DualDF %d-%d at %d/%d)" % (st, NEW[1][0], NEW[1][-1], NEW[2], NEW[3]))
    if st == "FOREIGN": print("ABORT - record 214 slot 2 is neither EXPLBIG 0-29 nor ours"); return 1
    if revert:
        if st != "v5": print("not applied"); return 0
        new = rebuild(cur, V4)
    else:
        if st == "v5": print("already applied"); return 0
        new = rebuild(cur, NEW)
        assert rebuild(new, V4 if st == "v4" else VAN) == cur, "revert would not be exact"
    raw = replace(raw, K_SKULL, new)
    R.load(raw)
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks if k != K_SKULL and k > 12), "another record changed"
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
