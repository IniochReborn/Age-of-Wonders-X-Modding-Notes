#!/usr/bin/env python3
r"""
BUILD BRIDGE site art (2026-10-18).  Data only: Images\Str_bldg.ILB + Images\BORDER.ILB.

User (Build Bridge v2 works): "during construction, can it NOT say it's a tower - say Bridge instead with custom gfx?
The structure panel would also need a custom side image."  The engine half is patch_bridge_site_look_v1.py; this
script APPENDS the art it draws:

  Images\Str_bldg.ILB (vanilla 18 images: building frames + the BuidFr crane) += 9 RLESprite16 records, ids 18..26 =
      "BrSite_a<axis>s<stage>.BMP": a half-built wooden bridge over the water, per bridge axis (0 = N-S, HN 1/4;
      1 = NE-SW, HN 2/5; 2 = NW-SE, HN 3/6) and build stage (0 = pilings driven + a raft of planks, 1 = stringers +
      the first planks, 2 = deck nearly complete).  64x64 canvas drawn at (-24, -40) from the structure origin (canvas
      (32, 42) = the hex centre (8, 2)); the engine draws it UNDER the vanilla construction crane (STR_BLDG sub-sequence,
      unchanged) - every construction / rebuild in the game shows that crane, so the bridge site keeps it.
  Images\BORDER.ILB (195 images) += 1 Picture16 record, id 195 = "B_BridgeSite.BMP" (57x278): the structure panel's
      bottom border image (the "side image") - the watchtower panel's own sky (#44 rows 0..96 kept verbatim so the
      tower's top/middle strips #42/#43 continue seamlessly) over a river valley with a half-built bridge and a crane.

States: vanilla (counts 18 / 195) -> append; ours (our names at the tail) -> rebuilt in place if the bytes differ, else
"already applied"; anything else -> ABORT.  --revert drops exactly our tail records (byte-identical to the pre-apply
file).  Dry-run default; --apply / --revert / --preview DIR / --bldg / --border (copies).
Backups <game>\backup\Images\<file>.bak_bridgesite.  Ship both ILBs (build_release_zip.py --add Images\Str_bldg.ILB
Images\BORDER.ILB).
"""
import argparse, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file, game_dir
sys.path.insert(0, os.path.join(game_dir(), "modding tools"))
from aowxlib import ilb

# ------------------------------------------------------------------ art (procedural)
import math, random
from PIL import Image, ImageDraw, ImageFilter, ImageChops

SS = 4                      # supersampling
W = H = 64
CX, CY = 32, 42             # hex centre on the canvas
XO, YO = -24, -40
DECK_H = 6                  # deck height above the water (px)

AXES = {0: (0.0, -16.0), 1: (16.0, -8.0), 2: (16.0, 8.0)}   # half-span vector (screen px) per axis

WOOD_D = (58, 38, 20)
WOOD_M = (112, 78, 42)
WOOD_L = (158, 116, 66)
WOOD_H = (196, 154, 98)
PLANK_A = (138, 98, 54)
PLANK_B = (122, 86, 46)
FOAM = (176, 204, 222)


def _unit(v):
    l = math.hypot(*v); return (v[0] / l, v[1] / l)


def _poly(dr, pts, col):
    dr.polygon([(x * SS, y * SS) for x, y in pts], fill=col + (255,))


def _line(dr, a, b, col, w):
    dr.line([(a[0] * SS, a[1] * SS), (b[0] * SS, b[1] * SS)], fill=col + (255,), width=max(1, int(w * SS)))


def _post(dr, x, y, h, bg):
    """A piling at water point (x, y), h px tall, with a ripple ring."""
    dr.ellipse([(x - 2.6) * SS, (y - 1.1) * SS, (x + 2.6) * SS, (y + 1.3) * SS], outline=FOAM + (255,), width=SS)
    _poly(dr, [(x - 1.4, y), (x + 1.4, y), (x + 1.4, y - h), (x - 1.4, y - h)], WOOD_D)
    _poly(dr, [(x - 1.0, y - 0.2), (x + 0.1, y - 0.2), (x + 0.1, y - h + 0.2), (x - 1.0, y - h + 0.2)], WOOD_M)
    _poly(dr, [(x - 1.4, y - h - 0.6), (x + 1.4, y - h - 0.6), (x + 1.4, y - h + 0.8), (x - 1.4, y - h + 0.8)], WOOD_L)


def map_stage(axis, stage, seed=1):
    rnd = random.Random(seed * 31 + axis * 7 + stage)
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    hx, hy = AXES[axis]
    ux, uy = _unit((hx, hy))
    px, py = -uy, ux                    # perpendicular
    if py < 0 or (abs(py) < 1e-6 and px < 0):
        px, py = -px, -py               # perpendicular points "down/right" (front side)
    half_w = 7.0 if axis == 0 else 5.0
    # squash the perpendicular a little (oblique view)
    pxs, pys = px * half_w, py * half_w * 0.75 if abs(py) > 0.3 else py * half_w
    def P(t, side, lift=0.0):           # point along the axis t in [-1,1], side -1/+1, lifted up by `lift`
        return (CX + hx * t + pxs * side, CY + hy * t + pys * side - lift)

    ts = (-0.8, 0.0, 0.8) if axis == 0 else (-0.86, -0.3, 0.3, 0.86)
    posts = [(t, s) for t in ts for s in (-1, 1)]
    posts.sort(key=lambda ts_: P(*ts_)[1])          # back to front
    # stage 0: a small raft with a plank stack beside the pilings
    if stage == 0:
        rx, ry = CX - pxs * 2.4 + hx * 0.15, CY - pys * 2.4 + hy * 0.15 + 3
        _poly(dr, [(rx - 7, ry), (rx + 6, ry - 3), (rx + 9, ry + 1), (rx - 4, ry + 4)], WOOD_D)
        for k in range(3):
            o = -1.3 * k
            _poly(dr, [(rx - 6, ry + o - 0.3), (rx + 6, ry + o - 3.2), (rx + 7.5, ry + o - 1.6), (rx - 4.5, ry + o + 1.3)],
                  (PLANK_A if k % 2 == 0 else PLANK_B))
    for t, s in posts:
        x, y = P(t, s)
        _post(dr, x, y, DECK_H + (2 if stage == 0 else 0), None)
    if stage >= 1:
        # stringers (two beams along the deck edges)
        for s in (-1, 1):
            a, b = P(-0.98, s, DECK_H), P(0.98, s, DECK_H)
            _line(dr, a, b, WOOD_D, 2.2)
            _line(dr, (a[0], a[1] - 0.6), (b[0], b[1] - 0.6), WOOD_M, 1.2)
        # cross planks
        frac = 0.42 if stage == 1 else 0.88
        n = 15
        for k in range(n):
            t0 = -0.98 + 1.96 * k / n
            if (t0 + 0.98) / 1.96 > frac:
                break
            if stage == 2 and k == n - 4:
                continue                                   # one plank still missing
            t1 = t0 + 1.96 / n * 0.72
            q = [P(t0, -1.15, DECK_H + 0.8), P(t1, -1.15, DECK_H + 0.8), P(t1, 1.15, DECK_H + 0.8), P(t0, 1.15, DECK_H + 0.8)]
            col = PLANK_A if (k + rnd.randint(0, 1)) % 2 == 0 else PLANK_B
            _poly(dr, q, col)
            _line(dr, q[0], q[3], WOOD_H, 0.5)
        if stage == 2:
            # a loose plank lying across the last gap + a small plank stack on the deck end
            a, b = P(0.70, -0.4, DECK_H + 1.6), P(0.95, 0.9, DECK_H + 1.6)
            _line(dr, a, b, WOOD_L, 1.6)
    # downsample + hard alpha + dark 1-px outline (AoW sprite look)
    sm = im.resize((W, H), Image.LANCZOS)
    a = sm.split()[3].point(lambda v: 255 if v >= 110 else 0)
    rgb = Image.new("RGB", (W, H), (0, 0, 0)); rgb.paste(sm.convert("RGB"), mask=sm.split()[3])
    # un-premultiply-ish: boost edge pixels toward their colour
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(rgb, (0, 0), a)
    grown = a.filter(ImageFilter.MaxFilter(3))
    ring = ImageChops.subtract(grown, a)
    outline = Image.new("RGBA", (W, H), (34, 22, 12, 255))
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0)); base.paste(outline, (0, 0), ring)
    base.alpha_composite(out)
    # sharpen-ish: keep colours crisp
    return base


def _blob(dr, cx, cy, rx, ry, col):
    dr.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)


def border_bottom(tower_bottom):
    """57x278: the tower border's sky (rows above ~178) kept; a river valley with a half-built bridge painted below."""
    W2, H2 = tower_bottom.size
    S = 4
    big = tower_bottom.convert("RGB").resize((W2 * S, H2 * S), Image.BICUBIC)
    canvas = Image.new("RGB", (W2 * S, H2 * S))
    # sky: the tower art's upper sky (rows 0..118, no tower there) kept; rows 96..124 stretched down to row 206
    canvas.paste(big.crop((0, 0, W2 * S, 118 * S)), (0, 0))
    band = big.crop((0, 96 * S, W2 * S, 124 * S)).resize((W2 * S, 110 * S), Image.BICUBIC).filter(ImageFilter.GaussianBlur(S * 1.5))
    m = Image.new("L", (W2 * S, 110 * S), 255)
    for y in range(0, 22 * S):
        ImageDraw.Draw(m).line([(0, y), (W2 * S, y)], fill=int(255 * y / (22 * S)))
    canvas.paste(band, (0, 96 * S), m)
    dr = ImageDraw.Draw(canvas)
    rnd = random.Random(5)
    HZ = 160                                                             # horizon
    pts = [(0, (HZ + 20) * S)]
    for x in range(0, W2 * S + 8, 8):
        pts.append((x, (HZ + 6 * math.sin(x / (S * 9.0)) + 5 * math.sin(x / (S * 3.7) + 1)) * S))
    pts.append((W2 * S, (HZ + 24) * S)); pts.append((0, (HZ + 24) * S))
    dr.polygon(pts, fill=(96, 106, 120))
    pts = [(0, (HZ + 26) * S)]
    for x in range(0, W2 * S + 8, 8):
        pts.append((x, (HZ + 12 + 5 * math.sin(x / (S * 6.0) + 2) + 3 * math.sin(x / (S * 2.3))) * S))
    pts.append((W2 * S, (HZ + 28) * S)); pts.append((0, (HZ + 28) * S))
    dr.polygon(pts, fill=(62, 78, 64))
    # river
    for y in range((HZ + 22) * S, H2 * S):
        t = (y - (HZ + 22) * S) / ((H2 - HZ - 22) * S)
        c = (int(66 + 34 * t), int(88 + 36 * t), int(108 + 34 * t))
        dr.line([(0, y), (W2 * S, y)], fill=c)
    # far bank (right) and near bank (left/bottom)
    dr.polygon([(36 * S, (HZ + 24) * S), (W2 * S, (HZ + 20) * S), (W2 * S, (HZ + 46) * S), (46 * S, (HZ + 38) * S)], fill=(74, 88, 50))
    dr.polygon([(40 * S, (HZ + 36) * S), (W2 * S, (HZ + 42) * S), (W2 * S, (HZ + 48) * S), (44 * S, (HZ + 41) * S)], fill=(92, 80, 52))
    dr.polygon([(0, 236 * S), (12 * S, 240 * S), (24 * S, 258 * S), (22 * S, H2 * S), (0, H2 * S)], fill=(84, 72, 44))
    dr.polygon([(0, 244 * S), (9 * S, 249 * S), (16 * S, 266 * S), (12 * S, H2 * S), (0, H2 * S)], fill=(60, 78, 42))
    # water highlights
    for _ in range(110):
        x = rnd.uniform(0, W2) * S; y = rnd.uniform(HZ + 24, H2) * S; l = rnd.uniform(2, 8) * S
        dr.line([(x, y), (x + l, y)], fill=(148, 174, 196), width=max(1, S // 2))
    # bridge: deck from the near bank (bottom-left) toward the far bank (upper-right), half built
    deck = lambda t: (8 * S + t * 44 * S, 246 * S - t * 46 * S)        # t 0 near bank .. 1 far bank
    for t in (0.22, 0.44, 0.66, 0.88):                                   # pilings (all driven)
        x, y = deck(t)
        for side in (-1, 1):
            xx = x + side * 5 * S; yy = y + 4 * S + side * 2 * S
            dr.rectangle([xx - 1.6 * S, yy - 9 * S, xx + 1.6 * S, yy + 13 * S], fill=WOOD_D)
            dr.rectangle([xx - 1.1 * S, yy - 9 * S, xx + 0.1 * S, yy + 13 * S], fill=WOOD_M)
            dr.ellipse([xx - 4 * S, yy + 11.5 * S, xx + 4 * S, yy + 14.5 * S], outline=FOAM, width=max(1, S // 2))
    n = 18
    for k in range(n):                                                   # planks up to t = 0.6
        t = 0.6 * k / n
        x, y = deck(t)
        col = PLANK_A if k % 2 == 0 else PLANK_B
        dr.polygon([(x - 6 * S, y - 1.5 * S), (x + 5 * S, y + 2.5 * S), (x + 6.8 * S, y + 0.5 * S), (x - 4.2 * S, y - 3.5 * S)], fill=col)
        dr.line([(x - 6 * S, y - 1.5 * S), (x + 5 * S, y + 2.5 * S)], fill=WOOD_D, width=max(1, S // 3))
    x0, y0 = deck(0.0); x1, y1 = deck(0.6); x2, y2 = deck(0.95)
    for off in ((-5, -1), (5, 3)):                                      # stringers to the far bank
        dr.line([(x1 + off[0] * S, y1 + off[1] * S), (x2 + off[0] * S, y2 + off[1] * S)], fill=WOOD_M, width=int(1.5 * S))
        dr.line([(x0 + off[0] * S, y0 + off[1] * S), (x1 + off[0] * S, y1 + off[1] * S)], fill=WOOD_D, width=int(1.5 * S))
    # A-frame crane on the deck end with a hanging plank
    cx, cy = deck(0.52)
    top = (cx + 2 * S, cy - 40 * S)
    dr.line([(cx - 4 * S, cy), top], fill=WOOD_D, width=int(1.8 * S))
    dr.line([(cx + 5 * S, cy + 2 * S), top], fill=WOOD_M, width=int(1.8 * S))
    arm = (cx + 22 * S, cy - 32 * S)
    dr.line([top, arm], fill=WOOD_D, width=int(1.5 * S))
    dr.line([arm, (arm[0], arm[1] + 16 * S)], fill=(206, 196, 166), width=max(1, S // 2))
    hx_, hy_ = arm[0], arm[1] + 16 * S
    dr.polygon([(hx_ - 7 * S, hy_), (hx_ + 7 * S, hy_ + 2 * S), (hx_ + 7 * S, hy_ + 4 * S), (hx_ - 7 * S, hy_ + 2 * S)], fill=WOOD_L)
    # plank stack + barrel on the near bank
    for k in range(5):
        dr.polygon([(1 * S, (266 - 2.2 * k) * S), (15 * S, (262 - 2.2 * k) * S), (16.5 * S, (264 - 2.2 * k) * S),
                    (2.5 * S, (268 - 2.2 * k) * S)], fill=(PLANK_A if k % 2 == 0 else PLANK_B))
    _blob(dr, 19 * S, 270 * S, 3 * S, 4 * S, (84, 56, 30))
    dr.line([(16.5 * S, 268 * S), (21.5 * S, 268 * S)], fill=(50, 34, 18), width=max(1, S // 2))
    # painterly finish: slight blur + grain
    canvas = canvas.filter(ImageFilter.GaussianBlur(S * 0.35))
    out = canvas.resize((W2, H2), Image.LANCZOS)
    px = out.load(); g = random.Random(9)
    for y in range(96, H2):
        for x in range(W2):
            r, gg, b = px[x, y]; n = g.randint(-5, 5)
            px[x, y] = (max(0, min(255, r + n)), max(0, min(255, gg + n)), max(0, min(255, b + n)))
    # keep the original upper sky untouched (exact pixels) so the panel's middle strip (#43) continues seamlessly
    out.paste(tower_bottom.convert("RGB").crop((0, 0, W2, 96)), (0, 0))
    return out


# ------------------------------------------------------------------ ILB plumbing
STR_BLDG = game_file(os.path.join("Images", "Str_bldg.ILB"))
BORDER = game_file(os.path.join("Images", "BORDER.ILB"))
BLDG_VANILLA_N, BORDER_VANILLA_N = 18, 195
ART_ID0, BORDER_ID = 18, 195                      # patch_bridge_site_look_v1.py uses these ids
BLDG_TEMPLATE, BORDER_TEMPLATE = 6, 171           # BuidFr00 (RLESprite16) / "pan border.png" (Picture16)
BLDG_NAMES = ["BrSite_a%ds%d.BMP" % (ax, st) for ax in range(3) for st in range(3)]
BORDER_NAMES = ["B_BridgeSite.BMP"]


def _decode(lib, i):
    r = lib.images[i].primary; w, h, px = ilb.decode_record(lib, r)
    im = Image.new("RGBA", (w, h)); im.putdata([p for row in px for p in row]); return im


def _rec_from(template, name):
    r = ilb.Record({k: v for k, v in template.items() if k not in ("newdata", "inline")})
    r["name"] = name; r["xs"] = r["ys"] = 0; r["sub"] = 0; r["loadMode"] = 1; r["blendValue"] = 0; r["drawMode"] = 256
    return r


def wanted(raw_bldg, raw_border):
    lb, lr = ilb.read(raw_bldg), ilb.read(raw_border)
    bt = lb.images[BLDG_TEMPLATE].primary
    bl = []
    for k, nm in enumerate(BLDG_NAMES):
        r = _rec_from(bt, nm)
        ilb.encode_image(lb, r, map_stage(k // 3, k % 3), transparent_rgb=(255, 0, 255))
        bl.append((nm, r))
    r = _rec_from(lr.images[BORDER_TEMPLATE].primary, BORDER_NAMES[0])
    ilb.encode_image(lr, r, border_bottom(_decode(lr, 44)).convert("RGBA"))
    return bl, [(BORDER_NAMES[0], r)]


def state(lib, vanilla_n, names):
    n = len(lib.images)
    if n == vanilla_n: return "vanilla"
    if n == vanilla_n + len(names) and [lib.images[vanilla_n + k].primary.get("name") for k in range(len(names))] == names:
        return "ours"
    return "FOREIGN(%d images)" % n


def rebuild(raw, vanilla_n, recs):
    lib = ilb.read(raw)
    del lib.images[vanilla_n:]
    for k, (nm, r) in enumerate(recs):
        lib.images.append(ilb.Image(vanilla_n + k, parts=[r]))
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
    sb = state(lb, BLDG_VANILLA_N, BLDG_NAMES); sr = state(lr, BORDER_VANILLA_N, BORDER_NAMES)
    print("Str_bldg.ILB: %s (%d images) | BORDER.ILB: %s (%d images)" % (sb, len(lb.images), sr, len(lr.images)))
    if "FOREIGN" in sb or "FOREIGN" in sr: print("ABORT (unexpected image count / names)"); return 1
    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
        sheet = Image.new("RGBA", (64 * 9, 64), (46, 74, 120, 255))
        for k in range(9): sheet.alpha_composite(map_stage(k // 3, k % 3), (k * 64, 0))
        sheet.save(os.path.join(a.preview, "bridgesite_map_stages.png"))
        border_bottom(_decode(lr, 44)).save(os.path.join(a.preview, "bridgesite_border.png"))
        print("previews ->", a.preview)
    if a.revert:
        nb = strip(raw_b, BLDG_VANILLA_N) if sb == "ours" else raw_b
        nr = strip(raw_r, BORDER_VANILLA_N) if sr == "ours" else raw_r
    else:
        want_b, want_r = wanted(raw_b, raw_r)
        nb = rebuild(raw_b, BLDG_VANILLA_N, want_b)
        nr = rebuild(raw_r, BORDER_VANILLA_N, want_r)
    todo = [(p, raw, new, st) for p, raw, new, st in ((a.bldg, raw_b, nb, sb), (a.border, raw_r, nr, sr)) if new != raw]
    if not todo: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    for p, raw, new, st in todo:
        print("  %s: %d -> %d bytes%s" % (os.path.basename(p), len(raw), len(new),
              " (our records rebuilt in place)" if (st == "ours" and not a.revert) else ""))
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for p, raw, new, st in todo:
        bak = bak_path(p, ".bak_bridgesite")
        if not a.revert and st == "vanilla" and not os.path.exists(bak):
            shutil.copy2(p, bak); print("backup ->", bak)
        if a.revert and os.path.exists(bak) and open(bak, "rb").read() != new:
            print("  note: %s differs from its pre-apply backup (other edits since?) - writing the stripped file anyway"
                  % os.path.basename(p))
        with open(p, "r+b" if len(new) == len(raw) else "wb") as f:
            f.write(new); f.truncate()
        assert open(p, "rb").read() == new
        print("written", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
