#!/usr/bin/env python3
r"""
Great Eagle's Nest v8 (2026-10-31) - on top of patch_eagle_nest_v7.

User: "extend the crops to the entire empty area in the combat map (units spawn on crops)".
TCMaps\Nest0000.hsm = v7's map (NodeE000 + rock/crop swaps) + a crop/hay decor child on EVERY empty playable hex
(hex records whose base child is the combat hexagon 0x220500 and that hold no decor 0x220166, structure 0x22051C
or flee object 0x220528), except the ring right around the centre structure (its image already is a crop patch).
New child = <u32 0x220166><03 01 00 03 04 04 05><crop guid><x><y> under the hex's next free child tag; the level's
stream is rebuilt with hsm_grid (mapgen's offset fix-ups).  Crop resources = ZGR_CROP 133/131/132, picked per hex.
Backup .bak_eagle8 (Nest0000.hsm).  Dry-run default; --apply; --revert.
"""
import os, random, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v7 as V7  # noqa: E402
import hsm_grid as G  # noqa: E402

TAG = ".bak_eagle8"
NESTMAP = V2.NESTMAP
CENTRE, SKIP_R = (32, 28), 1
HEX, DECOR, STRUCT, FLEE = 0x220500, 0x220166, 0x22051C, 0x220528


def cls(c):
    return struct.unpack_from("<I", c, 0)[0] if len(c) >= 4 else None


def build_nestmap():
    raw, _ = V7.build_nestmap()
    g = G.loads(raw)
    rnd = random.Random(0xEA8)
    n = 0
    for i, rec in enumerate(g.recs):
        x, y = i % g.W, i // g.W
        kids = G.children(rec)
        cl = [cls(c) for t, c in kids]
        if HEX not in cl or DECOR in cl or STRUCT in cl or FLEE in cl:
            continue
        if abs(x - CENTRE[0]) <= SKIP_R and abs(y - CENTRE[1]) <= SKIP_R:
            continue
        tag = max(t for t, c in kids if t >= 0x32) + 1
        child = struct.pack("<I", DECOR) + bytes.fromhex("03010003040405") + \
            struct.pack("<I", rnd.choice(V7.CROPS)) + bytes([x, y])
        g.recs[i] = G.build(kids + [(tag, child)])
        n += 1
    out = G.dumps(g)
    chk = G.loads(out)
    assert len(chk.recs) == g.W * g.H and chk.recs == g.recs
    return out, n


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        bk = bak_path(NESTMAP, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, NESTMAP); print("restored", bk)
        return 0
    nm, n = build_nestmap()
    if open(NESTMAP, "rb").read() == nm:
        print("Nest0000.hsm already applied"); return 0
    print("Nest0000.hsm write (+%d crop hexes, %d B)" % (n, len(nm)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(NESTMAP, TAG)
    if not os.path.exists(bk):
        shutil.copy2(NESTMAP, bk)
    with open(NESTMAP, "r+b") as fh:
        fh.write(nm); fh.truncate()
    assert open(NESTMAP, "rb").read() == nm
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
