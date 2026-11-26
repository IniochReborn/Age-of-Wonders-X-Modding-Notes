#!/usr/bin/env python3
r"""
Water teleporters v3 (2026-10-31) - animated water art, on top of patch_teleport_water_v1/v2.

User: "the white lines that you added should be animated and more subtle (like waves breaking against the
teleporter). and the swirl thing you added in the middle should be more subtle and animated too".
  1. Images\STR_TELW.ILB rebuilt (tele_water_art v3): 0 / 1 = static bases (tinted stones + wet band, no foam, no
     swirl); 10..25 / 50..65 = breaking-wave foam frames (surface / underground; each stone foot on its own phase,
     the crest pushes out, breaks into dots and fades into the water colour); 30..41 / 70..81 = faint dotted two-arm
     swirl turning one step per frame.  All 60x65 at the base offset, 1-bit alpha.
  2. Release.hss records 201 / 218, slots 0 / 10: two layers chained after the five glow layers (a2..a6):
     a7 = foam frames, a8 = swirl frames (copies of the a6 layer's mode-4 sequence, frame phase 0).
     (Chains of up to 9 layers already exist in the hss, rec 156/158.)
v3.1 (user: "janky ... needs to be slower and center animation too"): 32 foam / 24 swirl frames (half the motion per
frame), each listed HOLD=2 times -> 4x slower; swirl dots no longer cycle (flickered); ids foam 10-41 / 100-131,
swirl 50-73 / 150-173.  Re-running rebuilds the a7/a8 layers.
v3.2 (user: waves must follow the water flow up-left, subtler; centre subtler): foam = swell from the lower right breaking on
each stone and washing round it up-left (tele_water_art v3.2); swirl sparser + closer to the water colour.
Backups .bak_telewater3 (Release.hss, STR_TELW.ILB).  Re-running patch_teleport_water_v1 afterwards would rewrite
STR_TELW.ILB with the v1 static art - don't (its dry-run reports "write" once v3 is on; harmless).
Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import patch_teleport_water_v1 as V1  # noqa: E402
import tele_water_art as ART  # noqa: E402

TAG = ".bak_telewater3"
HSS, TELW = V1.HSS, V1.TELW
IDS = {False: (0, 10, 50), True: (1, 100, 150)}    # under: (base, first foam, first swirl)  (v3.1 ids)


def build_telw(gd):
    from PIL import Image
    raw = open(os.path.join(gd, "Images", "STR_TELE.ILB"), "rb").read()
    tpl = {im.id: im for im in ilb.read(raw).images}[0].primary
    lib = ilb.read(raw); lib.images = []

    def add(iid, arr):
        rec = copy.deepcopy(tpl); rec["name"] = "str_telw%d.BMP" % iid
        ilb.encode_image(lib, rec, Image.fromarray(arr, "RGBA"))
        lib.images.append(ilb.Image(iid, parts=[rec]))
    for under, (b, f0, s0) in IDS.items():
        add(b, ART.base_frame(gd, under))
        for k, fr in enumerate(ART.foam_frames(gd, under)):
            add(f0 + k, fr)
        for k, fr in enumerate(ART.swirl_frames(gd, under)):
            add(s0 + k, fr)
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def chain(s):
    out = []
    while s:
        out.append(s); s = s["sub"]
    return out


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c in V1.RECS:
        r = bytes(A["recs"][c])
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        new = copy.deepcopy(lst)
        for slot, under in ((0, False), (10, True)):
            ch = chain(new[slot])
            assert ch[0]["name"] == "STR_TELW.ILB", (c, slot)
            ch = ch[:6]                                   # v3.1: rebuild our a7/a8 layers
            assert ch[-1]["a"] == 6 and ch[-1]["mode"] == 4
            _, f0, s0 = IDS[under]
            prev = ch[-1]; prev["sub"] = None
            for a, first, n in ((7, f0, ART.FOAM_N), (8, s0, ART.SWIRL_N)):
                s = copy.deepcopy(ch[-1]); s["sub"] = None
                s.update(name="STR_TELW.ILB", a=a, b=0, frame=0, x=ch[0]["x"], y=ch[0]["y"],
                         frames=[f for f in range(first, first + n) for _ in range(ART.HOLD)])
                prev["sub"] = s; prev = s
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
    return nb


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        for f in (HSS, TELW):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    gd = os.path.dirname(HERE)
    nh = hss_build(open(HSS, "rb").read())
    nt = build_telw(gd)
    if open(TELW, "rb").read() == nt:
        nt = None
    for f, data in ((HSS, nh), (TELW, nt)):
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    if nh is None and nt is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, data in ((HSS, nh), (TELW, nt)):
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
