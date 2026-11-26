#!/usr/bin/env python3
r"""
Underground structures on surface terrain (2026-10-31).

User (community suggestion + follow-up): "If structures where placed on dungeon level and if there is terrain like
snow, the structures should become snow structures of their kind" / "double check structures, some dont have correct
surface terrain variant underground (mines, some nodes, dungeon, monster lair, builders guild, possibly others)".
A structure's image slot = its hex terrain (TStructure.TerrainChanged -> GetTerrainTypeImage): 1..5 = the surface
terrains, 10..13 = the underground ones.  The underground Release.hss records (the palette's underground versions)
only carry 11/12 art, so on underground grass / snow / ... (slots 1..5) they draw nothing or the wrong frame.
Fix (Release.hss data only): every record that has underground slots (10..13) but misses any of 1..5 gets the
missing slots copied (whole sequence incl. animation layers + offsets) from the same-class record that has all
five, preferring one drawn with the same ILB (e.g. the Machinereum art), then the same description text.  Skipped: SKIP (custom slot layouts).
Backup .bak_ugterrain (Release.hss).  Dry-run default (prints every pairing); --apply; --revert.
"""
import copy, os, re, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402

TAG = ".bak_ugterrain"
HSS = H.OURS
SKIP = {229, 238}          # Magic Sanctuary (razed/rebuild slot layout), Water Node (rock + whirl special slots)
UG, SURF = (10, 11, 12, 13), (1, 2, 3, 4, 5)


def texts(r):
    return {s for s in re.findall(rb"[ -~]{12,}", r) if b".ILB" not in s.upper() and b".WAV" not in s.upper()}


def survey(A):
    info = {}
    for c, r in A["recs"].items():
        r = bytes(r)
        try:
            fo, td = H.fields(r)
            if 9 not in fo or fo.get(10) != fo[9]:
                continue
            lst = Q.parse_list(r, td + fo[9])[0]
        except Exception:
            continue
        if len(lst) < 14:
            continue
        info[c] = (struct.unpack_from("<I", r, 0)[0], lst, texts(r))
    return info


def plan(A):
    info = survey(A)
    out = []
    for c, (cls, lst, tx) in sorted(info.items()):
        if c in SKIP or not any(lst[i] for i in UG) or all(lst[i] for i in SURF):
            continue
        art = {lst[i]["name"].upper() for i in UG if lst[i]}
        twins = [(int(any(l2[i]["name"].upper() in art for i in SURF)) * 1000 + len(tx & t2), d)
                 for d, (k2, l2, t2) in info.items()
                 if d != c and k2 == cls and all(l2[i] for i in SURF)]
        if not twins:
            out.append((c, None, []))
            continue
        twins.sort(key=lambda z: (-z[0], z[1]))
        d = twins[0][1]
        out.append((c, d, [i for i in SURF if not lst[i]]))
    return info, out


def hss_build(b, verbose=False):
    A = H.parse(b)
    info, pl = plan(A)
    changed = {}
    for c, d, miss in pl:
        if verbose:
            desc = sorted(info[c][2], key=len)[-1][:50] if info[c][2] else b""
            print("  %4d cls %s %-52s <- %s slots %s" % (c, hex(info[c][0]), desc, d, miss))
        if d is None or not miss:
            continue
        new = copy.deepcopy(info[c][1])
        for i in miss:
            new[i] = copy.deepcopy(info[d][1][i])
        changed[c] = R.rec_with_list(bytes(A["recs"][c]), new)
    if not changed:
        return None, []
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb, sorted(changed)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        bk = bak_path(HSS, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, HSS); print("restored", bk)
        return 0
    b = open(HSS, "rb").read()
    nb, ch = hss_build(b, verbose=True)
    print("Release.hss", "already applied" if nb is None else "%d records" % len(ch))
    if nb is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
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
