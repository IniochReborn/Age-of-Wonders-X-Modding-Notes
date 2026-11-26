#!/usr/bin/env python3
r"""
Title screen: soft black fading outline around the AoWx logo (2026-11-14).

User: "on the title screen, the AoWx logo edges are a bit janky. what if we added a slight black fading outline".

Int\Scenes\title.ilb: image 1 (Sprite16) and image 3 (RLESprite16) are the same 375x175 colour-keyed logo.
TTitleScene's background helper (AoWx.exe 0x419C84) draws image 1 through an alpha table while the logo fades in
(ticks 25..75) / out, and image 3 with the plain draw (vmt+0x84) for the rest of the time.
Image 3 becomes a COMPOSITE (like the company logos 4 / 6 of the same library): N black ring layers
(Sprite16, drawMode 258 = smBlended + bmAlpha, blendValue = opacity %) followed by the untouched logo record.
Ring k holds the pixels whose distance to the logo is in (RINGS[k-1].r, RINGS[k].r].  The rings need PAD px
around the 375x175 box (the logo touches its top and bottom rows) -> the layers are (375+2*PAD) x (175+2*PAD) with
xshift = yshift = -PAD, so the logo itself stays exactly where it was.  No exe change.
Image 1 is left alone: the outline appears when the fade-in ends (the alpha-table draw takes a single sprite).

Backup <game>\backup\Int\Scenes\title.ilb.bak_logohalo.  Dry-run default (writes a preview PNG with --preview <png>);
--apply; --revert.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file
from aowxlib import ilb
import numpy as np
from PIL import Image

ILB = game_file(os.path.join("Int", "Scenes", "title.ilb"))
SUF = ".bak_logohalo"
LOGO_ID = 3
PAD = 6
# (outer radius px, opacity %) from the logo edge outwards
RINGS = [(1.0, 62), (2.0, 46), (3.0, 31), (4.2, 19), (5.7, 9)]


def rgba(lib, rec):
    w, h, px = ilb.decode_record(lib, rec)
    return np.array([p for row in px for p in row], dtype=np.uint8).reshape(h, w, 4)


def dilate(m, r):
    out = np.zeros_like(m)
    k = int(r)
    H, W = m.shape
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            if dx * dx + dy * dy <= r * r + 1e-6:
                ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
                xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
                out[yd, xd] |= m[ys, xs]
    return out


def ring_masks(logo):
    h, w = logo.shape[:2]
    m = np.zeros((h + 2 * PAD, w + 2 * PAD), dtype=bool)
    m[PAD:PAD + h, PAD:PAD + w] = logo[:, :, 3] > 0
    prev = m; rings = []
    for r, op in RINGS:
        d = dilate(m, r)
        rings.append((d & ~prev, op))
        prev = d | prev
    return rings


def build(lib):
    img = [i for i in lib.images if i.id == LOGO_ID][0]
    if img.composite:
        return None, None
    assert len(img.parts) == 1
    base = img.parts[0]
    assert (base["w"], base["h"], base["type"]) == (375, 175, ilb.T_RLESPRITE16), base
    logo = rgba(lib, base)
    rings = ring_masks(logo)
    parts = []
    for k, (mask, op) in enumerate(rings):
        im = np.zeros(mask.shape + (4,), dtype=np.uint8)
        im[mask] = (0, 0, 0, 255)
        r = ilb.new_record(ilb.T_SPRITE16, name=base["name"], info=3)
        r["xs"] = r["ys"] = (-PAD) & 0xFFFFFFFF
        r["sub"] = k + 1
        r["loadMode"] = base["loadMode"]
        r["drawMode"] = 258                      # smBlended | bmAlpha << 8
        r["blendValue"] = op
        ilb.encode_image(lib, r, Image.fromarray(im, "RGBA"))
        assert r["size"] > 0
        parts.append(r)
    img.parts = parts + [base]
    img.composite = True
    return rings, logo


def preview(lib0, rings, logo, out):
    bg = rgba(lib0, [i for i in lib0.images if i.id == 0][0].parts[0])[:, :, :3].astype(np.float32)
    h, w = logo.shape[:2]
    x0, y0 = 300, 40

    def comp(with_halo):
        c = bg[y0 - 20:y0 + h + 20, x0 - 20:x0 + w + 20].copy()
        oy, ox = 20, 20
        if with_halo:
            for mask, op in rings:
                reg = c[oy - PAD:oy + h + PAD, ox - PAD:ox + w + PAD]
                reg[mask] *= (1 - op / 100.0)
        a = logo[:, :, 3:4] > 0
        reg = c[oy:oy + h, ox:ox + w]
        reg[:] = np.where(a, logo[:, :, :3], reg)
        return c
    a, b = comp(False), comp(True)
    both = np.concatenate([a, b], axis=0).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(both, "RGB")
    im = im.resize((im.width * 2, im.height * 2), Image.NEAREST)
    im.save(out)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(ILB, SUF)
    if revert:
        if not os.path.exists(bak):
            print("no backup", bak); return 1
        shutil.copy2(bak, ILB); print("restored", bak); return 0
    lib = ilb.read(ILB)
    rings, logo = build(lib)
    if rings is None:
        print("already applied (image %d is a composite)" % LOGO_ID); return 0
    data = ilb.write(lib)
    chk = ilb.read(data)
    ci = [i for i in chk.images if i.id == LOGO_ID][0]
    assert ci.composite and len(ci.parts) == len(RINGS) + 1
    assert (rgba(chk, ci.parts[-1]) == logo).all()
    print("title.ilb %d -> %d B | image %d = %d ring layers (%s) + logo, pad %d"
          % (os.path.getsize(ILB), len(data), LOGO_ID, len(RINGS),
             ", ".join("r<=%.1f %d%%" % x for x in RINGS), PAD))
    if "--preview" in sys.argv:
        out = sys.argv[sys.argv.index("--preview") + 1]
        preview(ilb.read(ILB), rings, logo, out); print("preview ->", out)
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bak):
        shutil.copy2(ILB, bak); print("backup ->", bak)
    with open(ILB, "wb") as f:
        f.write(data)
    assert open(ILB, "rb").read() == data
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
