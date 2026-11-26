#!/usr/bin/env python3
r"""Release\Ability.pfs for Tame Animal v5 (2026-10-19; data only).  In-place upgrade of patch_tame_ability_pfs_v4.py
(v4 must be applied); --revert puts the exact v4 bytes back.

User (v4 live, overhead paw working): "I don't like how it looks - use the new image (art import export\tamed.jpg):
BLACK with a GREEN GLOW, maybe partial transparency, a little smaller.  The paw should be part of the ability GFX like
the Dominate eyeball, then 'stick' if it lands.  Fade in and out smoothly."

How Dominate does it (vanilla Ability.pfs): record 0x1C's slot-0 chain has layer f8 6 = COMBAT.ILB [99, 99, 130 x 8]
at xs -32 / ys -44 (two blank lead-in frames, then the eye); the Dominated status record (0x96) draws the SAME image 130
at the SAME anchor as its overhead overlay - so when the touch lands the status overlay takes over under the cast's eye
and the eye "sticks".  All chain layers of the slot play together (f18 = ticks per frame - 1).
v5 mirrors that with the new traced paw (DualDF 7300..7327, build_dual_sphere_fx_v1.py rows from
_tame7_integration.txt):
  211 (Tame Animal) tag 8, layer f8 6 (the mark): [340, 340, 7242..7249] (v3 rising/fading old paw)
       -> [340, 340, 7320..7323 (fade in: blend 18/38/60/80), 7300..7303 (hold = badge frames, 88),
           7324..7327 (fade out: 66/44/24/8)]  = 14 frames x 2 ticks (28 <= f8 1's 30, so the effect length / the CA
           midpoint where the status is applied are unchanged).  On SUCCESS the Tamed overlay (same sprite, same anchor)
           is already drawn underneath when the mark fades, so the paw stays; on a FAILED roll it simply fades out.
  212 (Tamed overlay) tag 8, layer f8 0: [7260..7271] (v3 solid green paw) -> [7300..7311] (black paw, pulsing glow,
       ALPHA 258/88).  Same xs -32 / ys -44 / f18 / f20.
The other layers of 211 (f8 1/2/5/8: the twinkle with v4's fades) are untouched.

Dry-run default; --apply / --revert; --pfs <copy> = scratch.  Safety copy <game>\backup\Release\Ability.pfs.bak_tame5.
LIFO: revert this BEFORE patch_tame_ability_pfs_v4.py.
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record, replace

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_tame5"
KEY_T, KEY_S = 0xC9 + 10, 0xCA + 10
B = chr(92)
ILB = "EFFECTS" + B + "DUALDF.ILB"
MARK4 = [340, 340] + list(range(7242, 7250))
MARK5 = [340, 340] + list(range(7320, 7324)) + list(range(7300, 7304)) + list(range(7324, 7328))
BADGE4 = list(range(7260, 7272))
BADGE5 = list(range(7300, 7312))
EDITS = {KEY_T: {6: (MARK4, MARK5)}, KEY_S: {0: (BADGE4, BADGE5)}}


def walk(s):
    while s:
        yield s
        s = s.get("chain")


def conv(t8, edits, to5):
    slots = G.seq_parse(t8); assert len(slots) == 1
    hit = set()
    for e in walk(slots[0]):
        if e["name"].upper() != ILB: return None
        if e["f8"] in edits:
            src, dst = edits[e["f8"]] if to5 else edits[e["f8"]][::-1]
            if e["frames"] == src: e["frames"] = list(dst); hit.add(e["f8"])
    return G.seq_build(slots) if hit == set(edits) else None


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw0 = open(PFS, "rb").read()
    states, new = {}, {}
    for key, ed in EDITS.items():
        order, vals = fields(R.rec_of(raw0, key)); t8 = vals[8]
        up, down = conv(t8, ed, True), conv(t8, ed, False)
        states[key] = "v4" if up is not None else "v5" if down is not None else "FOREIGN"
        new[key] = (order, vals, up if not revert else down)
    print("Ability.pfs | 211 Tame Animal mark: %s | 212 Tamed overlay: %s" % (states[KEY_T], states[KEY_S]))
    st = set(states.values())
    if "FOREIGN" in st or len(st) != 1:
        print("ABORT - records 211/212 are not both v4 or both v5 (apply patch_tame_ability_pfs_v4.py first?)"); return 1
    st = st.pop(); want = "v4" if revert else "v5"
    if st == want: print("nothing to revert" if revert else "already applied"); return 0
    raw = raw0
    for key, (order, vals, t8) in new.items():
        nv = dict(vals); nv[8] = t8
        raw = replace(raw, key, build_record(order, nv))
    R.load(raw)
    ks = lambda r: [k for k, _ in R.load(r)[2]] + [k for k, _ in R.load(r)[3]]
    assert ks(raw) == ks(raw0), "key set changed"
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks(raw0) if k not in EDITS and k > 12), "another record changed"
    for key in EDITS:
        a, b = fields(R.rec_of(raw, key)), fields(R.rec_of(raw0, key))
        assert a[0] == b[0] and all(a[1][t] == b[1][t] for t in a[0] if t != 8), "a tag other than 8 changed (%d)" % key
    print("%s: %d -> %d bytes (CRC ok)" % ("revert -> v4" if revert else "apply -> v5", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(bk):
        shutil.copy2(PFS, bk); print("safety copy ->", bk)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
