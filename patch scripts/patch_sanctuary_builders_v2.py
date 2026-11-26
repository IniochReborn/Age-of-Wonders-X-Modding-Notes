#!/usr/bin/env python3
r"""
Magic Sanctuary rebuild cranes v2 (2026-10-31) - on top of patch_sanctuary_builders_v1.

User: "changed my mind, get rid of the top ones. and the builders, for sanctuary only, need more contrast, they
blend in too much".
  * Release.hss, both Sanctuary records, rebuild slots 13..18 + 0x19..0x1D: the mirrored crane layers (a 5 / a 7)
    are dropped; the two cranes keep v1's shifted positions but use frames + 20;
  * Images\STR_BLDG.ILB ids 30..41 (v1's mirrored frames) become high-contrast copies of the crane frames 10..21:
    luminance stretched around mid-grey (x CONTRAST), a little brighter overall, and a 1-px dark outline around the
    sprite so it separates from the grey stone floor.  Ids 10..21 stay -> every other structure is unchanged.
Backups .bak_sanctcranes2 (Release.hss, STR_BLDG.ILB).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import patch_sanctuary_builders_v1 as B1  # noqa: E402

HSS, BLDG = B1.HSS, B1.BLDG
CONTRAST, LIFT = 1.7, 18
OUTLINE = (24, 18, 12)
TAG = ".bak_sanctcranes2"


def contrasted(rgba):
    a = rgba.astype(float)
    m = rgba[..., 3] > 0
    lum = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    for c in range(3):
        a[..., c] = (a[..., c] - lum) * 1.25 + ((lum - 110) * CONTRAST + 110 + LIFT)
    out = np.clip(a, 0, 255).astype(np.uint8)
    edge = np.zeros_like(m)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        edge |= np.roll(np.roll(m, dy, 0), dx, 1)
    edge &= ~m
    out[edge, 0], out[edge, 1], out[edge, 2] = OUTLINE
    out[..., 3] = np.where(m | edge, 255, 0)
    return out


def ilb_build(raw):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    want = {}
    for i in range(10, 22):
        w, h, rows = ilb.decode_record(lib, by[i].primary)
        a = np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)
        want[i + B1.FLIP] = contrasted(a)
    done = True
    for j, img in want.items():
        if j not in by:
            done = False; break
        w, h, rows = ilb.decode_record(lib, by[j].primary)
        cur = [[ilb.to_rgb565(*q[:3]) if q and q[3] else None for q in row] for row in rows]
        exp = [[ilb.to_rgb565(*(int(v) for v in img[y, x, :3])) if img[y, x, 3] else None for x in range(w)]
               for y in range(h)]
        if cur != exp:
            done = False; break
    if done:
        return None
    lib.images = [im for im in lib.images if im.id not in want]
    for j, img in want.items():
        rec = copy.deepcopy(by[j - B1.FLIP].primary)
        rec["name"] = "BuidFrC%02d.BMP" % (j - 30)
        ilb.encode_image(lib, rec, Image.fromarray(img, "RGBA"))
        lib.images.append(ilb.Image(j, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def fix_slot(s):
    s = copy.deepcopy(s)
    c1 = s["sub"]; c2 = c1["sub"]
    assert c1["name"].upper() == "STR_BLDG.ILB" and c2["name"].upper() == "STR_BLDG.ILB"
    if c2.get("sub") is None and min(c1["frames"]) >= 30 and min(c2["frames"]) >= 30:
        return None
    c2["sub"] = None
    for c in (c1, c2):
        if min(c["frames"]) < 30:
            c["frames"] = [f + B1.FLIP for f in c["frames"]]
    return s


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != R.SANCT_CLS:
            continue
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        new = list(lst); hit = False
        for i in B1.SLOTS:
            f = fix_slot(lst[i])
            if f is not None:
                new[i] = f; hit = True
        if hit:
            changed[c] = R.rec_with_list(r, new)
    if not changed:
        return None
    assert len(changed) == 2
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    N = H.parse(nb)
    old = H.parse(b)["recs"]
    for c, v in N["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if SP.busy():
            print("game/editor running - close it first"); return 1
        for f in (HSS, BLDG):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    b = open(HSS, "rb").read(); nb = hss_build(b)
    ni = ilb_build(open(BLDG, "rb").read())
    print("Release.hss", "already applied" if nb is None else "%d -> %d B" % (len(b), len(nb)),
          "| STR_BLDG.ILB", "already applied" if ni is None else "ids 30..41 -> high-contrast cranes")
    if nb is None and ni is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    for f, data in ((HSS, nb), (BLDG, ni)):
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
