#!/usr/bin/env python3
r"""
Great Eagle's Nest v10 (2026-10-31) - supersedes v8's crop fill.

User (screenshot: crops everywhere OUTSIDE the rock ring, bare grass inside): "why are the crops outside the rocks?
i just want the empty space inside the rocks (ie: the nest) to be full of crops. none outside the rocks. there should
not be base terrain visible, every hex inside the rocks should be crops".
Findings: the interior hexes already held crop decor, but decor within ~2-3 hexes of the battle's structure is not
shown (the structure clears its surroundings), so only the far-out crops were visible.
  1. TCMaps\Nest0000.hsm = v7's map (no v8 fill); interior = playable hexes not reachable from the map edge
     through rock-free hexes (flood fill, combat hex adjacency = mapgen hexn: even x also borders (x+-1, y-1));
     every crop decor OUTSIDE the interior becomes a small rock again (ring stays closed, no crops outside).
  2. comb_res child 581 (the Nest's centre structure) image list = one ZGR_CROP clump per interior hex (+ its own
     hex), drawn as structure layers so nothing clears them: offset = hex delta * (32, 32) + 16 px down for odd
     columns relative to the structure's (even) column, + the decor anchor (-17, -17); back-to-front order.
Backups .bak_eagle10 (Nest0000.hsm, comb_res.pfs).  Dry-run default; --apply; --revert.
"""
import collections, os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import build_sky_chasm_combat_v1 as SC  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v3 as V3  # noqa: E402
import patch_eagle_nest_v7 as V7  # noqa: E402
import hsm_grid as G  # noqa: E402

TAG = ".bak_eagle10"
NESTMAP, PFS = V2.NESTMAP, SC.PFS
CROPS = set(V7.CROPS)
ROCK = 0x0E7A7B7                     # ZGR_SRK small rock
CROP_ILB = "TCOMBAT\\GR\\ZGR_CROP.ILB"
PITCH_X, PITCH_Y, ANCHOR = 32, 32, (-17, -17)
DECOR, STRUCT, HEXC = 0x220166, 0x22051C, 0x220500


def cls(c):
    return struct.unpack_from("<I", c, 0)[0] if len(c) >= 4 else None


def nbrs(x, y, W, H):
    out = [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]
    out += [(x - 1, y - 1), (x + 1, y - 1)] if x % 2 == 0 else [(x - 1, y + 1), (x + 1, y + 1)]
    return [(a, b) for a, b in out if 0 <= a < W and 0 <= b < H]


def analyse(g):
    W, H = g.W, g.H
    info = {}
    for i, r in enumerate(g.recs):
        kids = G.children(r)
        play = any(cls(c) == HEXC for t, c in kids)
        rock = any(cls(c) == DECOR and struct.unpack_from("<I", c, 11)[0] not in CROPS for t, c in kids)
        st = any(cls(c) == STRUCT for t, c in kids)
        info[(i % W, i // W)] = (play, rock, st)
    seen, q = set(), collections.deque()
    for (x, y), (p, r, s) in info.items():
        if p and not r and not s and any(not info[n][0] for n in nbrs(x, y, W, H)):
            seen.add((x, y)); q.append((x, y))
    while q:
        c = q.popleft()
        for n in nbrs(*c, W, H):
            p, r, s = info[n]
            if p and not r and not s and n not in seen:
                seen.add(n); q.append(n)
    inside = {k for k, (p, r, s) in info.items() if p and not r and k not in seen}   # incl. the structure hex
    centre = [k for k, v in info.items() if v[2]][0]
    return inside, centre


def build_nestmap():
    raw, _ = V7.build_nestmap()
    g = G.loads(raw)
    inside, centre = analyse(g)
    assert 20 <= len(inside) <= 80, len(inside)
    n = 0
    for i, rec in enumerate(g.recs):
        xy = (i % g.W, i // g.W)
        if xy in inside:
            continue
        kids = G.children(rec)
        ch = False
        for j, (t, c) in enumerate(kids):
            if cls(c) == DECOR and struct.unpack_from("<I", c, 11)[0] in CROPS:
                c = bytearray(c); struct.pack_into("<I", c, 11, ROCK); kids[j] = (t, bytes(c)); ch = True; n += 1
        if ch:
            g.recs[i] = G.build(kids)
    out = G.dumps(g)
    assert G.loads(out).recs == g.recs
    return out, n, inside, centre


def crop_layers(inside, centre):
    cx, cy = centre
    pts = []
    for (x, y) in inside:
        dx = (x - cx) * PITCH_X
        dy = (y - cy) * PITCH_Y + (16 if x % 2 else 0) - (16 if cx % 2 else 0)
        pts.append((dy, dx, (x * 7 + y * 3) % 3))
    pts.sort()
    s = None
    for dy, dx, f in reversed(pts):
        s = dict(name=CROP_ILB, a=0, b=0, mode=0, frame=f, x=dx + ANCHOR[0], y=dy + ANCHOR[1], sub=s)
    return s


def build_pfs(b, inside, centre):
    ce, cbase, recs = SC.pfs_records(b)
    s, t = recs[V3.NEW_CHILD]
    assert t == len(b) - 4
    r = b[s:t]
    fo, td = H.fields(r)
    assert struct.unpack_from("<I", r, td + fo[1])[0] == V3.NEW_RID
    lst = Q.parse_list(r, td + fo[9])[0]
    lay = crop_layers(inside, centre)
    new = [None if x is None else lay for x in lst]
    if new == lst:
        return None
    out = bytearray(b[:s]) + R.rec_with_list(r, new)
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    ce2, cb2, recs2 = SC.pfs_records(bytes(out))
    for c, (s0, t0) in recs.items():
        if c != V3.NEW_CHILD:
            assert out[recs2[c][0]:recs2[c][1]] == b[s0:t0], c
    return bytes(out)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        for f in (NESTMAP, PFS):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    nm, n, inside, centre = build_nestmap()
    npf = build_pfs(open(PFS, "rb").read(), inside, centre)
    nm = None if open(NESTMAP, "rb").read() == nm else nm
    print("interior %d hexes around %s; %d outside crops -> rocks" % (len(inside), centre, n))
    print("Nest0000.hsm", "already applied" if nm is None else "write", "| comb_res.pfs",
          "already applied" if npf is None else "write (%d crop layers)" % len(inside))
    if nm is None and npf is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, data in ((NESTMAP, nm), (PFS, npf)):
        if data is None:
            continue
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
