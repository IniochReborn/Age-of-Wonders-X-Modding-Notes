#!/usr/bin/env python3
r"""
Great Eagle's Nest v4 (2026-10-31) - on top of patch_eagle_nest_v3.

User: "the nest should not be extending past the mountain like that. widen the mountain at the top or something.
side image still sucks, so does structure UI... the stuff you added to combat map sucks, remove it and leave it
mostly empty, maybe some light vegetation (no trees)".
  1. Images\PRO_EAGL.ILB ids 0..4 re-made: eagle_nest_art_v2 now flares the top 12 rows of the cut spire out to a
     30-px mesa cap (_flare) and keeps the nest inside it (bird frames unchanged).
  2. BORDER 205..207 + CityWin 69 = eagle_nest_side_v4 (cliff running off the right edge, nest on a flat ledge,
     rock textured with vanilla BORDER brushwork, small bird silhouettes).
  3. Combat: comb_res child 581 (the Nest's centre structure, v3) image list -> three vanilla shrubs chained
     (TCOMBAT\GR\ZGR_SHRB.ILB frames SHRUBS) - no mound, no birds; Images\TCOMBAT\STRUCT\ZS_NEST.ILB deleted
     (nothing references it any more).  The structure keeps the node's footprint mask.
Backups .bak_eagle4 (PRO_EAGL.ILB, BORDER.ILB, CityWin.ILB, comb_res.pfs, ZS_NEST.ILB - restored by --revert).
Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys, zlib

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
import eagle_nest_side_v4 as SIDE  # noqa: E402

TAG = ".bak_eagle4"
EAGL, BORDER, CITYWIN, PFS, ZSNEST = G1.EAGL, G1.BORDER, V2.CITYWIN, SC.PFS, V3.ZSNEST
SHRB = "TCOMBAT\\GR\\ZGR_SHRB.ILB"
SHRUBS = [(1, -12, -14), (3, 24, 4), (4, -2, 28)]       # (frame, x, y) relative to the structure anchor


def shrub_slot():
    s = None
    for f, x, y in reversed(SHRUBS):
        s = dict(name=SHRB, a=0, b=0, mode=0, frame=f, x=x, y=y, sub=s)
    return s


def build_pfs(b):
    ce, cbase, recs = SC.pfs_records(b)
    s, t = recs[V3.NEW_CHILD]
    assert t == len(b) - 4, "child 581 must be the last record"
    r = b[s:t]
    fo, td = H.fields(r)
    assert struct.unpack_from("<I", r, td + fo[1])[0] == V3.NEW_RID
    lst = Q.parse_list(r, td + fo[9])[0]
    new = [None if x is None else shrub_slot() for x in lst]
    if new == lst:
        return None
    nr = R.rec_with_list(r, new)
    out = bytearray(b[:s]) + nr
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
        for f in (EAGL, BORDER, CITYWIN, PFS, ZSNEST):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    gd = game_dir()
    ne = V2.build_eagl(gd); ne = None if open(EAGL, "rb").read() == ne else ne
    files = [(EAGL, ne), (BORDER, build_border(open(BORDER, "rb").read(), gd)),
             (CITYWIN, build_citywin(open(CITYWIN, "rb").read(), gd)), (PFS, build_pfs(open(PFS, "rb").read()))]
    for f, data in files:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    zs = os.path.exists(ZSNEST)
    print("ZS_NEST.ILB", "delete" if zs else "already removed")
    if all(d is None for _, d in files) and not zs:
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
    if zs:
        bk = bak_path(ZSNEST, TAG)
        if not os.path.exists(bk):
            shutil.copy2(ZSNEST, bk)
        os.remove(ZSNEST)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
