#!/usr/bin/env python3
r"""
Cyclops sprite library (2026-11-07): Images\UNITS\Monsters\CYCLOPS.ILB from render_cyclops_v2.py frames.

Template = Images\UNITS\Gbn\troll.ILB (same 72 record ids d*100+f, record types / flags / offsets kept); the palette is
rebuilt from the cyclops frames (index of the troll's transparent key kept, the other 255 entries = a median-cut
quantisation of all 72 frames together), every frame re-encoded with aowxlib.ilb.encode_image, then decoded back and
compared to the source frame (max colour error after quantisation printed).  The file is NOT referenced by any unit
yet (Unitgfx untouched).  Usage: build_cyclops_ilb_v1.py <frames dir>  (default: render dir in %TEMP%).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(GAME, "modding tools"))
from aowxlib import ilb  # noqa: E402
from PIL import Image  # noqa: E402

FR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["TEMP"], "cyc2", "frames")
TROLL = os.path.join(GAME, "Images", "UNITS", "Gbn", "troll.ILB")
OUT = os.environ.get("CYC_OUT") or os.path.join(GAME, "Images", "UNITS", "Monsters", "CYCLOPS.ILB")


def main():
    lib = ilb.read(open(TROLL, "rb").read())
    recs = {im.id: im.primary for im in lib.images}
    frames = {fid: Image.open(os.path.join(FR, "%d.png" % fid)).convert("RGBA") for fid in recs}
    t0 = recs[min(recs)]
    print("record type", t0["type"], "pal", t0.get("pal"), "transp", t0.get("transp"))
    key = t0.get("transp", 0)
    # palette from all frames (opaque pixels only)
    W = 64 * 12
    mosaic = Image.new("RGB", (W, 64 * 6), (0, 0, 0))
    mask = Image.new("L", mosaic.size, 0)
    for fid, im in frames.items():
        x, y = (fid % 100 - 1) * 64, (fid // 100 - 1) * 64
        mosaic.paste(im.convert("RGB"), (x, y)); mask.paste(im.split()[3], (x, y))
    px, mk = mosaic.load(), mask.load()
    opaque = [px[x, y] for y in range(mosaic.height) for x in range(W) if mk[x, y]]
    # two-stage palette: 200 colours for the bulk, then 55 for whatever the bulk palette matches badly (the eye white,
    # iris, pupil, horn, nails - a handful of pixels that a single median cut would merge into skin)
    import numpy as np
    def mcut(pxl, n):
        st = Image.new("RGB", (len(pxl), 1)); st.putdata([tuple(map(int, c)) for c in pxl])
        g = st.quantize(colors=n, method=Image.Quantize.MEDIANCUT).getpalette()[:n * 3]
        return np.array(g, float).reshape(-1, 3)
    O = np.array(opaque, float)
    P1 = mcut(O, 200)
    err = np.sqrt(((O[:, None, :] - P1[None]) ** 2).sum(-1)).min(1)
    bad = O[err > 10]
    P2 = mcut(bad, 55) if len(bad) else np.zeros((0, 3))
    cols = [tuple(int(v) for v in c) for c in np.vstack([P1, P2])]
    print("palette: 200 bulk + %d detail colours (from %d poorly matched pixels)" % (len(P2), len(bad)))
    old = lib.palette_rgb(t0.get("pal", 0))
    pal, it = [], iter(cols)
    for i in range(256):
        if i == key:
            pal.append(tuple(old[i]))
        else:
            pal.append(next(it, (0, 0, 0)))
    if os.environ.get("CYC_PAL") == "vanilla":     # keep the troll's (= the vanilla unit) palette, nearest-colour map
        pal = old
        print("palette: vanilla unit palette kept")
    lib.set_palette_rgb(pal, t0.get("pal", 0))
    worst = 0
    for fid, rec in recs.items():
        im = frames[fid]
        bg = Image.new("RGBA", im.size, tuple(old[key]) + (0,))
        ilb.encode_image(lib, rec, Image.alpha_composite(bg, im), transparent_rgb=tuple(old[key]))
    data = ilb.write(lib)
    lib2 = ilb.read(data)
    for im2 in lib2.images:
        w, h, rows = ilb.decode_record(lib2, im2.primary)
        src = frames[im2.id].load()
        for y in range(h):
            for x in range(w):
                a = src[x, y][3] > 0; c = rows[y][x]
                b = bool(c and c[3])
                assert a == b, (im2.id, x, y, a, b)
                if a:
                    worst = max(worst, max(abs(c[i] - src[x, y][i]) for i in range(3)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "wb").write(data)
    print("wrote", OUT, len(data), "bytes;", len(lib2.images), "images; worst palette error", worst)


if __name__ == "__main__":
    main()
