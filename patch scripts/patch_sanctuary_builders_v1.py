#!/usr/bin/env python3
r"""
Magic Sanctuary rebuild cranes: re-position + a mirrored pair (2026-10-31).  After patch_sanctuary_rebuild_gfx_v1.

User: "move them slightly up and left... then add a mirrored pair above pointing down that is more to the right".
  * Images\STR_BLDG.ILB: ids 30..41 = horizontally mirrored copies of the crane frames 10..21 (ids 10..21 and
    everything else untouched - other structures keep using them);
  * Release.hss, both Sanctuary records, rebuild slots 13..18 and 0x19..0x1D: the two STR_BLDG crane layers move
    by SHIFT (left/up); two more layers (a 5 / a 7) = the mirrored frames (frame list + 20), placed above and to the
    right of the first pair (MIRROR_POS), their arms swinging down-left over the floor.
Backups .bak_sanctcranes (Release.hss, STR_BLDG.ILB).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402

HSS = R.HSS
BLDG = game_file(os.path.join("Images", "STR_BLDG.ILB"))
SLOTS = list(range(13, 19)) + list(range(0x19, 0x1E))
ORIG_POS = [(-29, -17), (-5, -11)]
SHIFT = (-6, -4)
MIRROR_POS = [(10, -40), (-14, -46)]          # mirrored crane 1 / 2 (above, further right)
MIRROR_LAYERS = (5, 7)
FLIP = 20                                    # mirrored id = original id + 20


def ilb_build(raw):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    if 30 in by:
        return None
    for i in range(10, 22):
        rec = copy.deepcopy(by[i].primary)
        w, h, rows = ilb.decode_record(lib, by[i].primary)
        img = Image.new("RGBA", (w, h)); img.putdata([q or (0, 0, 0, 0) for row in rows for q in row])
        ilb.encode_image(lib, rec, img.transpose(Image.FLIP_LEFT_RIGHT))
        rec["name"] = "BuidFrM%02d.BMP" % (i - 10)
        lib.images.append(ilb.Image(i + FLIP, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    chk = {im.id for im in ilb.read(out).images}
    assert set(range(30, 42)) <= chk and set(range(10, 22)) <= chk
    return out


def fix_slot(s):
    """base -> crane a1 -> crane a3  ==>  shifted cranes + mirrored pair"""
    s = copy.deepcopy(s)
    c1 = s["sub"]; c2 = c1["sub"] if c1 else None
    assert c1 and c2 and c1["name"].upper() == "STR_BLDG.ILB" and c2["name"].upper() == "STR_BLDG.ILB"
    if c2.get("sub"):
        return None
    assert [(c1["x"], c1["y"]), (c2["x"], c2["y"])] == ORIG_POS, ((c1["x"], c1["y"]), (c2["x"], c2["y"]))
    for c in (c1, c2):
        c["x"] += SHIFT[0]; c["y"] += SHIFT[1]
    m = []
    for k, (src, (x, y), layer) in enumerate(zip((c1, c2), MIRROR_POS, MIRROR_LAYERS)):
        mm = copy.deepcopy(src)
        mm["sub"] = None
        mm["a"] = layer
        mm["x"], mm["y"] = x, y
        mm["frames"] = [f + FLIP for f in src["frames"]]
        mm["frame"] = (src["frame"] + 17 + 23 * k) % len(mm["frames"])   # out of phase with the first pair
        m.append(mm)
    c2["sub"] = m[0]
    m[0]["sub"] = m[1]
    return s


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != R.SANCT_CLS:
            continue
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        assert lst[0x19] is not None, "patch_sanctuary_rebuild_gfx_v1 not applied"
        new = list(lst)
        hit = False
        for i in SLOTS:
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
            bk = bak_path(f, ".bak_sanctcranes")
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    b = open(HSS, "rb").read(); nb = hss_build(b)
    ni = ilb_build(open(BLDG, "rb").read())
    print("Release.hss", "already applied" if nb is None else "%d -> %d B" % (len(b), len(nb)),
          "| STR_BLDG.ILB", "already applied" if ni is None else "+12 mirrored crane frames (ids 30..41)")
    if nb is None and ni is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    for f, data in ((HSS, nb), (BLDG, ni)):
        if data is None:
            continue
        bk = bak_path(f, ".bak_sanctcranes")
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
