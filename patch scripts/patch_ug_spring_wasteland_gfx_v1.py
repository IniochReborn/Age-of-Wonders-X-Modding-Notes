#!/usr/bin/env python3
r"""
Underground Spring of Life: dead-spring picture on wasteland (2026-11-14).

User: "we had modified spring of life so that it changed in wasteland ... it doesnt change on wasteland underground".
Structure image slot = terrain id.  Surface record (Release.hss child 207, page 21) has slot 5 (Wasteland) = the dead
spring (STR_SOL image 11, no water layer) and slot 3 (Snow) = the frozen one (image 10).  The underground record
(child 226, page 23) has the frozen slot 3 but its slot 5 is a copy of the normal flowing spring - painted
wasteland underground is terrain 5 too (palette page 10), so the spring kept flowing there.
Fix: every TSpringOfLife resource (class 0x20101) whose slot 5 still shows the flowing spring gets the surface
record's slot 5.  (The wasteland behaviour - build_spring_wasteland cave 0x55810000 - tests the terrain byte only,
so it is level independent.)
Backup Release.hss.bak_ugspring (first apply only).  Dry-run default; --apply; --revert (in place: slot 5 := slot 1).
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402

TAG = ".bak_ugspring"
HSS = H.OURS
CLS, SRC, WASTE, DEAD = 0x20101, 207, 5, 11


def chain(s):
    out = []
    while s:
        out.append(s); s = s["sub"]
    return out


def sig(s):
    return [(x["name"].upper(), x.get("frames")) for x in chain(s)]


def build(b, revert):
    A = H.parse(b)

    def lst_of(c):
        r = bytes(A["recs"][c]); fo, td = H.fields(r)
        return r, Q.parse_list(r, td + fo[9])[0]

    _, src = lst_of(SRC)
    assert sig(src[WASTE]) == [("STR_SOL.ILB", [DEAD])], "surface spring slot 5 is not the dead spring: %r" % sig(src[WASTE])
    changed = {}
    for c, rec in A["recs"].items():
        if struct.unpack_from("<I", rec, 0)[0] != CLS or c == SRC:
            continue
        r, lst = lst_of(c)
        if len(lst) <= WASTE or lst[WASTE] is None or lst[1] is None:
            print("  child %d (page %s): no slot 1/5 - skipped" % (c, H.u32(r, 2))); continue
        dead = sig(lst[WASTE]) == sig(src[WASTE])
        flowing = sig(lst[WASTE]) == sig(lst[1])
        print("  child %d (page %s): slot 5 = %s" % (c, H.u32(r, 2), "dead spring" if dead else "flowing" if flowing else "OTHER %r" % sig(lst[WASTE])))
        new = copy.deepcopy(lst)
        if not revert and flowing:
            new[WASTE] = copy.deepcopy(src[WASTE])
            new[WASTE]["x"], new[WASTE]["y"] = lst[1]["x"], lst[1]["y"]
        elif revert and dead:
            new[WASTE] = copy.deepcopy(lst[1])
        if new != lst:
            changed[c] = R.rec_with_list(r, new)
    if not changed:
        return None
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    print("  records changed:", sorted(changed))
    return nb


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    nb = build(open(HSS, "rb").read(), revert)
    if nb is None:
        print("nothing to do (%s)" % ("already vanilla" if revert else "already applied")); return 0
    if not (apply or revert):
        print("Dry run OK (%d B) - rerun with --apply (or --revert)." % len(nb)); return 0
    bk = bak_path(HSS, TAG)
    if not os.path.exists(bk):
        shutil.copy2(HSS, bk)
    with open(HSS, "r+b") as fh:
        fh.write(nb); fh.truncate()
    assert open(HSS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
