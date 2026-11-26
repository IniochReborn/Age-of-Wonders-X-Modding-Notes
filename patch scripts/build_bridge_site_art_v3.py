#!/usr/bin/env python3
r"""
BUILD BRIDGE site art v3 (2026-10-19).  Data only: Images\BORDER.ILB (Str_bldg.ILB stays vanilla).

v3 (user on v2: "underground bridge side image: make it darker (because it's underground)"): the underground strips
202..204 are darkened - per channel x(0.50, 0.53, 0.62) after a 1.15 gamma (keeps the arches readable, cool cave
tint), plus a soft top/bottom vignette.  The surface strips 199..201 are unchanged (byte-identical to v2).  Same ids,
names and record templates as v2, so the look scripts need nothing; --apply rewrites a v2 BORDER.ILB in place,
--revert -> vanilla (as v2).  v2 history follows.

v2 (2026-10-19).

User on v1: "bridge construction GFX is all glitched - just keep the moving builders, get rid of the tower shell and the
new stuff you added.  Side image: I posted two images in the art import folder - one for bridges built on the surface,
the other for underground/depths."

ROOT CAUSE of the glitch (v1): ILB images are looked up BY ID (TCustomImageLibrary.Get = [lib+0x48][id*8], size
[lib+0x44] = max id + 1) and v1 appended its records with id = image INDEX:
  * Str_bldg.ILB vanilla holds 18 images with ids 0..5 + 10..21 (BuidFr00..11 = the construction crane frames the
    STR_BLDG crane sequences use: 10..21).  v1 appended ids 18..26 -> DUPLICATE ids 18..21 = the crane's frames
    BuidFr08..11 -> every construction / rebuild in the game (not only the bridge) flashed bridge-stage art in its
    crane animation.
  * BORDER.ILB vanilla holds 195 images with ids up to 198 (171..174 unused; 193..198 = the wizard-ruin borders).
    v1 appended id 195 = a duplicate of "wiz ruin border3.png".
v2:
  * Str_bldg.ILB -> exactly vanilla again (v1's 9 tail records dropped; nothing of ours added - the map shows only the
    vanilla crane/builders, patch_bridge_site_look_v2.py).
  * BORDER.ILB -> vanilla + 6 Picture16 records with FREE ids 199..204 (the user's two paintings as full 57x330 side
    images, split like every structure's border into top 57x2 / middle 57x50 / bottom 57x278):
        199/200/201 = "B_BridgeS.BMP" top/middle/bottom - surface ("art import export\bridge surface.jpg")
        202/203/204 = "B_BridgeU.BMP" top/middle/bottom - underground ("art import export\bridge underground.jpg")
    Each painting is scaled to 330 px high (Lanczos) and a 57 px column is cut around the bridge (surface: the arch +
    waterfall, x 300/674; underground: the aqueduct arches + the rope bridge, x 245/480).
States: vanilla / v1 (our BrSite_* / B_BridgeSite tails) / v2 (ours, rebuilt in place if the bytes differ) / FOREIGN.
--revert drops every record of ours (v1 or v2) -> byte-identical to the vanilla files (the .bak_bridgesite backups).
Dry-run default; --apply / --revert / --preview DIR / --bldg / --border (copies).
Ship Images\BORDER.ILB (build_release_zip.py --add Images\BORDER.ILB); Str_bldg.ILB is vanilla again (nothing to ship).
"""
import argparse, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file, game_dir
sys.path.insert(0, os.path.join(game_dir(), "modding tools"))
from aowxlib import ilb
from PIL import Image

STR_BLDG = game_file(os.path.join("Images", "Str_bldg.ILB"))
BORDER = game_file(os.path.join("Images", "BORDER.ILB"))
ART = os.path.join(game_dir(), "art import export")
SRC = {"S": ("bridge surface.jpg", 300 / 674), "U": ("bridge underground.jpg", 245 / 480)}
BLDG_VANILLA_N, BORDER_VANILLA_N = 18, 195
V1_BLDG = ["BrSite_a%ds%d.BMP" % (ax, st) for ax in range(3) for st in range(3)]
V1_BORDER = ["B_BridgeSite.BMP"]
ID0 = 199                                            # patch_bridge_site_look_v2.py: 199 + 3*underground + part
PARTS = ((42, 2), (43, 50), (44, 278))               # template image id (B_WatchT top/middle/bottom), height
V2_BORDER = [("B_Bridge%s.BMP" % k, ID0 + 3 * n + p) for n, k in enumerate("SU") for p in range(3)]


def side(key, W=57, H=330):
    fn, cxf = SRC[key]
    im = Image.open(os.path.join(ART, fn)).convert("RGB")
    s = H / im.height
    im = im.resize((round(im.width * s), H), Image.LANCZOS)
    cx = round(cxf * im.width); x0 = max(0, min(im.width - W, cx - W // 2))
    return im.crop((x0, 0, x0 + W, H))


DARK = (0.50, 0.53, 0.62)                            # v3: underground per-channel gain (cool tint)
GAMMA = 1.15


def darken(im):
    """v3: the underground painting darkened (gamma, cool per-channel gain, soft vertical vignette)."""
    W, H = im.size
    px = im.load()
    for y in range(H):
        v = 1.0 - 0.25 * (abs(y - H * 0.55) / (H * 0.55)) ** 2           # a little darker towards top / bottom
        for x in range(W):
            c = px[x, y]
            px[x, y] = tuple(max(0, min(255, round(255 * ((c[k] / 255.0) ** GAMMA) * DARK[k] * v))) for k in range(3))
    return im


def strips(key):
    im, out, y = side(key), [], 0
    if key == "U":
        im = darken(im)
    for _, h in PARTS:
        out.append(im.crop((0, y, 57, y + h))); y += h
    return out


def _rec_from(template, name):
    r = ilb.Record({k: v for k, v in template.items() if k not in ("newdata", "inline")})
    r["name"] = name
    return r


def by_id(lib, i):
    return [im for im in lib.images if im.id == i][0]


def bldg_state(lib):
    n = len(lib.images)
    if n == BLDG_VANILLA_N: return "vanilla"
    if n == BLDG_VANILLA_N + len(V1_BLDG) and [lib.images[BLDG_VANILLA_N + k].primary.get("name") for k in range(len(V1_BLDG))] == V1_BLDG:
        return "v1"
    return "FOREIGN(%d images)" % n


def border_state(lib):
    n = len(lib.images)
    tail = [(im.primary.get("name"), im.id) for im in lib.images[BORDER_VANILLA_N:]]
    if n == BORDER_VANILLA_N: return "vanilla"
    if tail == [(V1_BORDER[0], 195)]: return "v1"
    if tail == V2_BORDER: return "ours (v2/v3 tail)"
    return "FOREIGN(%d images)" % n


def build_border(raw):
    lib = ilb.read(raw)
    del lib.images[BORDER_VANILLA_N:]
    used = {im.id for im in lib.images}
    assert not used & {i for _, i in V2_BORDER}, "ids 199..204 are taken in vanilla BORDER.ILB?"
    for n, key in enumerate("SU"):
        for p, img in enumerate(strips(key)):
            nm, iid = V2_BORDER[3 * n + p]
            r = _rec_from(by_id(lib, PARTS[p][0]).primary, nm)
            ilb.encode_image(lib, r, img.convert("RGBA"))
            lib.images.append(ilb.Image(iid, parts=[r]))
    return ilb.write(lib)


def strip(raw, vanilla_n):
    lib = ilb.read(raw); del lib.images[vanilla_n:]; return ilb.write(lib)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--preview", default=None); ap.add_argument("--bldg", default=STR_BLDG); ap.add_argument("--border", default=BORDER)
    a = ap.parse_args()
    raw_b, raw_r = open(a.bldg, "rb").read(), open(a.border, "rb").read()
    lb, lr = ilb.read(raw_b), ilb.read(raw_r)
    assert ilb.write(lb) == raw_b and ilb.write(lr) == raw_r, "codec round-trip failed - refusing"
    sb, sr = bldg_state(lb), border_state(lr)
    print("Str_bldg.ILB: %s (%d images) | BORDER.ILB: %s (%d images)" % (sb, len(lb.images), sr, len(lr.images)))
    if "FOREIGN" in sb or "FOREIGN" in sr: print("ABORT (unexpected image count / names)"); return 1
    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
        sheet = Image.new("RGB", (57 * 2 + 10, 330), (0, 0, 0))
        sheet.paste(side("S"), (0, 0)); sheet.paste(darken(side("U")), (67, 0))
        sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST).save(os.path.join(a.preview, "bridgesite_side_v3.png"))
        print("previews ->", a.preview)
    nb = strip(raw_b, BLDG_VANILLA_N) if sb != "vanilla" else raw_b          # v2: Str_bldg is always vanilla
    nr = strip(raw_r, BORDER_VANILLA_N) if a.revert else build_border(raw_r)
    todo = [(p, raw, new, st) for p, raw, new, st in ((a.bldg, raw_b, nb, sb), (a.border, raw_r, nr, sr)) if new != raw]
    if not todo: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    for p, raw, new, st in todo:
        print("  %s: %s, %d -> %d bytes" % (os.path.basename(p), st, len(raw), len(new)))
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for p, raw, new, st in todo:
        bak = bak_path(p, ".bak_bridgesite")                                # shared with v1: the vanilla file
        if st == "vanilla" and not os.path.exists(bak):
            shutil.copy2(p, bak); print("backup ->", bak)
        with open(p, "r+b" if len(new) == len(raw) else "wb") as f:
            f.write(new); f.truncate()
        assert open(p, "rb").read() == new
        print("written", p)
        if os.path.exists(bak) and new == strip(new, BLDG_VANILLA_N if p == a.bldg else BORDER_VANILLA_N):
            print("  matches vanilla backup: %s" % (open(bak, "rb").read() == new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
