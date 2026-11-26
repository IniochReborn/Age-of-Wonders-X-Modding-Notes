#!/usr/bin/env python3
r"""
Great Eagle's Nest v5 (2026-10-31) - on top of patch_eagle_nest_v4.

User: "combat map center should be city combat crop/hay tiles ,,, i think the problem is the mountains are too
similar to vanilla. make original ones with a more realistic shape, the nest is still too wide compared to top of
mountain... side image is okay thematically but the art style looks bad".
  1. Images\PRO_EAGL.ILB ids 0..4 = eagle_nest_art_v3: an original butte (no PRO_DRGN pixels) painted with
     crag_paint.facet_rock, top 34 px wide vs a ~14 px nest; bird frames 10..33 unchanged (v2).
  2. BORDER 205..207 + CityWin 69 = eagle_nest_side_v5 (v4 composition, faceted rock, crisper).
  3. Combat centre (comb_res child 581 image list): the v4 shrubs -> a patch of the crop/hay clumps used on farm /
     city outskirts (TCOMBAT\GR\ZGR_CROP.ILB frames 0..2, records 131..133), chained mode-0 layers, back to front,
     staggered ~one clump per hex over the node footprint.
Backups .bak_eagle5 (PRO_EAGL.ILB, BORDER.ILB, CityWin.ILB, comb_res.pfs).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import build_sky_chasm_combat_v1 as SC  # noqa: E402
import patch_eagle_nest_gfx_v1 as G1  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v3 as V3  # noqa: E402
import eagle_nest_art_v2 as BIRDS  # noqa: E402
import eagle_nest_art_v3 as MAP  # noqa: E402
import eagle_nest_side_v5 as SIDE  # noqa: E402

TAG = ".bak_eagle5"
EAGL, BORDER, CITYWIN, PFS = G1.EAGL, G1.BORDER, V2.CITYWIN, SC.PFS
CROP = "TCOMBAT\\GR\\ZGR_CROP.ILB"
# visual clump centres (structure-anchor px; the node pit's centre is ~(16, 31)), staggered rows ~one per hex
CENTRES = [(1, 6), (31, 6), (-14, 23), (16, 23), (46, 23), (1, 40), (31, 40), (-14, 57), (16, 57), (46, 57)]
CLUMP_C = (31, 25)          # visual centre inside the 62x51 clump sprite


def crop_slot():
    s = None
    for k, (cx, cy) in reversed(list(enumerate(CENTRES))):
        s = dict(name=CROP, a=0, b=0, mode=0, frame=k % 3, x=cx - CLUMP_C[0], y=cy - CLUMP_C[1], sub=s)
    return s


def build_eagl(gd):
    from PIL import Image
    raw = open(os.path.join(gd, "Images", "PRO_DRGN.ILB"), "rb").read()
    tpl = {im.id: im for im in ilb.read(raw).images}
    lib = ilb.read(raw); lib.images = []
    import copy
    for k, a in enumerate(MAP.map_frames(gd)):
        rec = copy.deepcopy(tpl[k].primary); rec["name"] = "str_eagl.BMP"
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(k, parts=[rec]))
    for i, a in zip(G1.BIRD_IDS, BIRDS.bird_frames(len(G1.BIRD_IDS))):
        rec = ilb.new_record(name="eagl_bird%02d.BMP" % (i - 10))
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    return ilb.write(lib)


def build_pfs(b):
    ce, cbase, recs = SC.pfs_records(b)
    s, t = recs[V3.NEW_CHILD]
    assert t == len(b) - 4, "child 581 must be the last record"
    r = b[s:t]
    fo, td = H.fields(r)
    assert struct.unpack_from("<I", r, td + fo[1])[0] == V3.NEW_RID
    lst = Q.parse_list(r, td + fo[9])[0]
    new = [None if x is None else crop_slot() for x in lst]
    if new == lst:
        return None
    out = bytearray(b[:s]) + R.rec_with_list(r, new)
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    ce2, cb2, recs2 = SC.pfs_records(bytes(out))
    for c, (s0, t0) in recs.items():
        if c != V3.NEW_CHILD:
            assert out[recs2[c][0]:recs2[c][1]] == b[s0:t0], c
    return bytes(out)


def build_border(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    for i, a in zip(G1.BORDER_IDS, SIDE.side_images(gd)):
        ilb.encode_image(lib, by[i].primary, Image.fromarray(a, "RGBA"))
    out = ilb.write(lib)
    return None if out == raw else out


def build_citywin(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    rec = {im.id: im for im in lib.images}[V2.ICON_ID].primary
    a = SIDE.window_icon(gd)
    assert (rec["w"], rec["h"]) == (a.shape[1], a.shape[0])
    ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
    out = ilb.write(lib)
    return None if out == raw else out


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        for f in (EAGL, BORDER, CITYWIN, PFS):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    gd = game_dir()
    ne = build_eagl(gd); ne = None if open(EAGL, "rb").read() == ne else ne
    files = [(EAGL, ne), (BORDER, build_border(open(BORDER, "rb").read(), gd)),
             (CITYWIN, build_citywin(open(CITYWIN, "rb").read(), gd)), (PFS, build_pfs(open(PFS, "rb").read()))]
    for f, data in files:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    if all(d is None for _, d in files):
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, data in files:
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
