#!/usr/bin/env python3
r"""Release\Ability.pfs for Tame Animal v3 (2026-10-19; data only, no engine change).  In-place upgrade of
patch_tame_ability_pfs_v2.py (v2 must be applied); --revert puts the exact v2 bytes back.

User (v3 engine live, taming works): "needs a smoother fade out for its gfx, and needs a gfx that stays above the
unit's head during combat (like the heart for Seduced / eyeball for Dominated) - maybe a green bear-paw print."

  record 211 (Tame Animal 0xC9), tag 8 only - two elements of Dominate's chain get new frame ids (same counts, same
    f8 / f18 / f20 / xs / ys, so the timing is untouched):
      f8 6 (the 'mark' that Dominate shows as its eye pop): [340, 340, 7230..7237] -> [340, 340, 7242..7249]
           = tame_mark: the paw pops in, rises 3 px, swells and FADES OUT over the 8 frames (v2 played the overlay
             loop at full brightness and then cut).
      f8 8 (Dominate re-plays its twinkle-in here: TWINKGR 220..228): [7200..7206, 7208] -> [7219..7226]
           = the dispersal tail of tame_twinkle (frames 19-26, motes/leaves drifting out and fading), which v2 had
             built but never referenced - so this slot no longer ends on a bright gathering frame.
  record 212 (Tamed 0xCA), tag 8 only - the overhead status overlay: frames 7230..7241 (faint additive glow) ->
    7260..7271 (tame_badge: SOLID green bear-paw print, drawMode 256 like the Charmed pendulum), xs/ys -31/-50 ->
    -32/-44 (the exact spot of the Dominated eye, COMBAT.ILB 130).  f8 0 / f18 1 / f20 3 kept (Charmed's loop).

Needs DualDF.ILB ids 7242..7249 + 7260..7271 (build_dual_sphere_fx_v1.py with the _tame5_integration.txt rows).
Dry-run default; --apply / --revert; --pfs <copy> = scratch.  One-time safety copy
<game>\backup\Release\Ability.pfs.bak_tame3.  LIFO: revert this BEFORE patch_tame_ability_pfs_v2.py (and before
patch_channeler_ability_pfs_v1.py's revert is irrelevant - records 211/212 are replaced in place, no key moves).
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record, replace

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_tame3"
KEY_T, KEY_S = 0xC9 + 10, 0xCA + 10
B = chr(92)
ILB = "EFFECTS" + B + "DUALDF.ILB"
V2_MARK, V3_MARK = [340, 340] + list(range(7230, 7238)), [340, 340] + list(range(7242, 7250))
V2_F8, V3_F8 = list(range(7200, 7207)) + [7208], list(range(7219, 7227))
V2_OV, V3_OV = list(range(7230, 7242)), list(range(7260, 7272))
V2_XY, V3_XY = (-31, -50), (-32, -44)


def walk(s):
    while s:
        yield s
        s = s.get("chain")


def conv_211(t8, to3):
    slots = G.seq_parse(t8); assert len(slots) == 1
    src = (V2_MARK, V2_F8) if to3 else (V3_MARK, V3_F8)
    dst = (V3_MARK, V3_F8) if to3 else (V2_MARK, V2_F8)
    hit = 0
    for e in walk(slots[0]):
        assert e["name"].upper() == ILB, "unexpected element library %s" % e["name"]
        if e["f8"] == 6 and e["frames"] == src[0]: e["frames"] = list(dst[0]); hit |= 1
        elif e["f8"] == 8 and e["frames"] == src[1]: e["frames"] = list(dst[1]); hit |= 2
    return G.seq_build(slots) if hit == 3 else None


def conv_212(t8, to3):
    slots = G.seq_parse(t8)
    if len(slots) != 1 or slots[0].get("chain"): return None
    s = slots[0]; fr, xy = (V2_OV, V2_XY) if to3 else (V3_OV, V3_XY)
    if s["name"].upper() != ILB or s["frames"] != fr or (s["xs"], s["ys"]) != xy: return None
    s["frames"] = list(V3_OV if to3 else V2_OV); s["xs"], s["ys"] = V3_XY if to3 else V2_XY
    return G.seq_build(slots)


def state(raw, key, conv):
    order, vals = fields(R.rec_of(raw, key)); t8 = vals[8]
    up, down = conv(t8, True), conv(t8, False)
    if up is not None: return "v2", order, vals, up
    if down is not None: return "v3", order, vals, down
    return "FOREIGN", order, vals, None


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw0 = open(PFS, "rb").read(); raw = raw0
    s1, o1, v1, n1 = state(raw, KEY_T, conv_211)
    s2, o2, v2, n2 = state(raw, KEY_S, conv_212)
    print("Ability.pfs | 211 Tame Animal gfx: %s | 212 Tamed overlay: %s" % (s1, s2))
    if "FOREIGN" in (s1, s2): print("ABORT - record 211/212 tag 8 is neither v2 nor v3 (apply patch_tame_ability_pfs_v2.py first?)"); return 1
    want = "v3" if not revert else "v2"
    if s1 == want and s2 == want: print("already applied" if not revert else "nothing to revert"); return 0
    if s1 != want:
        vals = dict(v1); vals[8] = n1; raw = replace(raw, KEY_T, build_record(o1, vals))
    if s2 != want:
        vals = dict(v2); vals[8] = n2; raw = replace(raw, KEY_S, build_record(o2, vals))
    R.load(raw)
    ks = lambda r: [k for k, _ in R.load(r)[2]] + [k for k, _ in R.load(r)[3]]
    assert ks(raw) == ks(raw0), "key set changed"
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks(raw0) if k not in (KEY_T, KEY_S) and k > 12), "another record changed"
    for k in (KEY_T, KEY_S):
        a, b = fields(R.rec_of(raw, k)), fields(R.rec_of(raw0, k))
        assert a[0] == b[0] and all(a[1][t] == b[1][t] for t in a[0] if t != 8), "a tag other than 8 changed in %d" % k
    print("%s: %d -> %d bytes (CRC ok)" % ("revert -> v2" if revert else "apply -> v3", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
