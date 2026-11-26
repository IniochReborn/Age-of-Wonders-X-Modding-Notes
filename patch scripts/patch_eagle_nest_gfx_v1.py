#!/usr/bin/env python3
r"""
Great Eagle's Nest graphics + side image, and Sanctuary cranes 5 px higher (2026-10-31).

User: "move them up a bit .... there's a structure called great eagles nest that is a builders guild clone that
produces great eagles and has a custom GFX. its GFX is bad, rework it, maybe add small bird circling it. and it
needs a side image (currently reuses teleporter)".

Great Eagle's Nest = Release.hss child 282 (TBuildersGuildResource 0x2092F, page 43 cell 14).  Its map art was the
vanilla, otherwise unused PRO_DRGN.ILB (purple dragon-egg spire) + a SMOKE layer; the side window builds its
picture from the structure's border slots 0x1E..0x20 (AoWx 0x44275C -> vmt+0x138/0x13C/0x140), which pointed at the
Teleport's BORDER.ILB 39..41.
  * Images\PRO_EAGL.ILB (NEW file): ids 0..4 = eagle_nest_art.map_frames (terrain variants), ids 10..33 = the
    circling-bird animation;  PRO_DRGN.ILB is left untouched;
  * Images\BORDER.ILB: ids 205/206/207 = the Nest's side picture (top 57x2 / filler 57x50 / portrait 57x278,
    cloned from the B_Telep records);
  * Release.hss child 282: slots 1..5 base -> PRO_EAGL.ILB (same frame ids), the SMOKE layer -> the bird layer
    (PRO_EAGL a1, delay 2, frames 10..33, at (-16,-49)); slots 0x1E..0x20 -> BORDER 205..207;
  * Release.hss Sanctuary rebuild slots (13..18, 0x19..0x1D): crane layers 5 px higher.
Backups .bak_eaglegfx (Release.hss, BORDER.ILB); PRO_EAGL.ILB is removed by --revert.
⚠ PRO_EAGL.ILB is a NEW file -> release --add.  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import patch_sanctuary_builders_v1 as B1  # noqa: E402
import eagle_nest_art as ART  # noqa: E402

TAG = ".bak_eaglegfx"
HSS = H.OURS
BORDER = game_file(os.path.join("Images", "BORDER.ILB"))
EAGL = game_file(os.path.join("Images", "PRO_EAGL.ILB"))
NEST_CHILD, NEST_CLS = 282, 0x2092F
BIRD_IDS = list(range(10, 34))
BORDER_IDS = (205, 206, 207)
BIRD_POS = (-16, -49)
CRANE_Y = [-21, -15]
CRANE_UP = 5


def build_eagl(gd):
    from PIL import Image
    src = ilb.read(open(os.path.join(gd, "Images", "PRO_DRGN.ILB"), "rb").read())
    by = {im.id: im for im in src.images}
    lib = ilb.read(open(os.path.join(gd, "Images", "PRO_DRGN.ILB"), "rb").read())
    lib.images = []
    for k, a in enumerate(ART.map_frames(gd)):
        rec = copy.deepcopy(by[k].primary)
        rec["name"] = "str_eagl.BMP"
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(k, parts=[rec]))
    for i, a in zip(BIRD_IDS, ART.bird_frames(len(BIRD_IDS))):
        rec = ilb.new_record(name="eagl_bird%02d.BMP" % (i - 10))
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    out = ilb.write(lib)
    assert {im.id for im in ilb.read(out).images} == set(range(5)) | set(BIRD_IDS)
    return out


def build_border(raw):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    if BORDER_IDS[0] in by:
        return None
    assert not any(i in by for i in BORDER_IDS)
    for i, src, a in zip(BORDER_IDS, (39, 40, 41), ART.side_images()):
        rec = copy.deepcopy(by[src].primary)
        rec["name"] = "B_Eagle.BMP"
        assert (rec["w"], rec["h"]) == (a.shape[1], a.shape[0]), (src, rec["w"], rec["h"], a.shape)
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    assert set(BORDER_IDS) <= {im.id for im in ilb.read(out).images}
    return out


def nest_list(lst):
    lst = copy.deepcopy(lst)
    if lst[1]["name"].upper() == "PRO_EAGL.ILB":
        return None
    for i in range(1, 6):
        s = lst[i]
        assert s["name"].upper() == "PRO_DRGN.ILB" and s["sub"]["name"].upper() == "SMOKE.ILB", i
        s["name"] = "PRO_EAGL.ILB"
        s["sub"] = dict(name="PRO_EAGL.ILB", a=1, b=2, mode=4, frame=(i * 5) % len(BIRD_IDS),
                        x=BIRD_POS[0], y=BIRD_POS[1], z=0, frames=list(BIRD_IDS), sub=None)
    for slot, fid in zip((0x1E, 0x1F, 0x20), BORDER_IDS):
        assert lst[slot]["name"].upper() == "BORDER.ILB"
        lst[slot]["frame"] = fid
    return lst


def sanct_list(lst):
    lst = copy.deepcopy(lst); hit = False
    for i in B1.SLOTS:
        c1 = lst[i]["sub"]; c2 = c1["sub"]
        if [c1["y"], c2["y"]] == CRANE_Y:
            c1["y"] -= CRANE_UP; c2["y"] -= CRANE_UP; hit = True
        else:
            assert [c1["y"], c2["y"]] == [y - CRANE_UP for y in CRANE_Y], (i, c1["y"], c2["y"])
    return lst if hit else None


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, r in A["recs"].items():
        cls = struct.unpack_from("<I", r, 0)[0]
        if cls == R.SANCT_CLS or (c == NEST_CHILD and cls == NEST_CLS and b"Great Eagle" in bytes(r)):
            fo, td = H.fields(r)
            lst = Q.parse_list(r, td + fo[9])[0]
            new = sanct_list(lst) if cls == R.SANCT_CLS else nest_list(lst)
            if new is not None:
                changed[c] = R.rec_with_list(r, new)
    if not changed:
        return None
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    N = H.parse(nb)
    old = H.parse(b)["recs"]
    for c, v in N["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb, sorted(changed)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if SP.busy():
            print("game/editor running - close it first"); return 1
        for f in (HSS, BORDER):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        if os.path.exists(EAGL):
            os.remove(EAGL); print("removed", EAGL)
        return 0
    gd = game_dir()
    b = open(HSS, "rb").read(); hb = hss_build(b)
    nbd = build_border(open(BORDER, "rb").read())
    ne = build_eagl(gd)
    same_e = os.path.exists(EAGL) and open(EAGL, "rb").read() == ne
    print("Release.hss", "already applied" if hb is None else "children %s (%d -> %d B)" % (hb[1], len(b), len(hb[0])),
          "| BORDER.ILB", "already applied" if nbd is None else "+3 (205..207)",
          "| PRO_EAGL.ILB", "already applied" if same_e else "write (%d B)" % len(ne))
    if hb is None and nbd is None and same_e:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    for f, data in ((HSS, hb[0] if hb else None), (BORDER, nbd)):
        if data is None:
            continue
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    if not same_e:
        with open(EAGL, "wb") as fh:
            fh.write(ne)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
