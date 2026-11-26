#!/usr/bin/env python3
r"""
phoenix_art.py - the Phoenix drawn from scratch (2026-10-13, user: "it should almost look like Ho-Oh").

SPRITE: a small 3-D paper-bird rendered with a software projector - crimson body with a cream belly, a long neck,
gold hooked beak, a five-plume golden crest sweeping back, broad wings (crimson inner / gold band / green-tipped
primaries with notched trailing edges) that beat with the frame, and five long tail plumes (gold shaft, green then
white tips) streaming back and down with a travelling wave.  Six direction sets (1 away, 2 away-left, 3 away-right,
4 towards, 5 towards-left, 6 towards-right - the Great Eagle's order) x 12 frames, 64x64, drawn at 3x and
down-sampled, then quantised to a 255-colour palette (index 0 = transparent) by build_phoenix_unit_v1.py.
PORTRAIT: 103x128 head in profile facing right - hooked gold beak, big eye, cream throat, crest plumes sweeping up
and back, neck feathers, a wing mass at the bottom, a golden glow in a dark crimson sky with embers.
"""
import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------- palette (Ho-Oh: crimson, gold, green/white tips)
OUT = (62, 8, 6)
OUT_SHADE, OUT_W = 0.55, 0.7    # 11/01: outline = fill x OUT_SHADE, width OUT_W px (was OUT itself, 0.9 px)
RED0, RED1, RED2 = (150, 20, 10), (205, 44, 16), (236, 82, 24)
ORG, GOLD0, GOLD1, GOLD2 = (226, 104, 22), (184, 96, 26), (204, 118, 36), (218, 140, 54)      # v6: brownish orange ("yellow not dark enough")
WHITE = (222, 146, 58)
GREEN0, GREEN1 = (150, 66, 18), (196, 108, 30)           # v6: dark brown primaries / brown-orange tips
BELLY = (200, 112, 34)
BEAK, BEAK_D = (214, 150, 48), (150, 96, 22)
EYE_D = (24, 10, 8)

# direction sets, settled with the Boar (BOARY.ILB, unambiguous head) 10/13: 1 S (towards the camera), 2 SE, 3 NE,
# 4 N (away), 5 NW, 6 SW - a flat-top hex's six neighbours.  (The eagle sheet misled twice; the old "set 6 =
# front-right" memo was wrong too.)  (dR, dF): dR = screen right, dF = into the screen.
DIRS = {1: (0.0, -1.0), 2: (0.7071, -0.7071), 3: (0.7071, 0.7071), 4: (0.0, 1.0), 5: (-0.7071, 0.7071), 6: (-0.7071, -0.7071)}
EL = math.radians(34.0)          # camera elevation above the horizon
SS = 3                           # supersampling
FW, FH = 64, 64
CX, CY = 31.5, 37.0              # screen position of the bird's body centre (frame coordinates)


def hull(pts):
    """Convex hull (monotone chain) of 2-D points."""
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in pts))
    if len(pts) < 3: return pts
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


class Projector:
    def __init__(self, direction):
        self.dR, self.dF = DIRS[direction]
    def world(self, p):
        f, l, u = p
        R = f * self.dR + l * (-self.dF); F = f * self.dF + l * self.dR
        return R, F, u
    def screen(self, p):
        R, F, u = self.world(p)
        return (CX + R) * SS, (CY - (u * math.cos(EL) + F * math.sin(EL))) * SS
    def depth(self, pts):
        return sum(self.world(p)[1] for p in pts) / len(pts)


def ellipsoid_pts(c, a, n=14):
    """Surface samples of an axis-aligned ellipsoid centre c, semi-axes a (bird frame)."""
    out = []
    for i in range(n):
        th = math.pi * (i + 0.5) / n
        for j in range(n * 2):
            ph = 2 * math.pi * j / (n * 2)
            out.append((c[0] + a[0] * math.sin(th) * math.cos(ph), c[1] + a[1] * math.sin(th) * math.sin(ph), c[2] + a[2] * math.cos(th)))
    return out


# The Great Eagle's own wing motion, measured on its symmetric away-facing set (401..412) on 10/13: per frame the
# wing-TIP height and the MID-SPAN height above the body centre (px) and the horizontal half-span (px).  It is NOT
# one sinusoid over 12 frames: frames 1-8 are one full beat (down at 1, highest at 5, level at 8) and 9-12 a
# second, faster rise - which is why a 12-frame cosine looked like it skipped frames.  The wing is modelled as
# u(s) = A*s + B*s^2 fitted through the two heights, so it bows exactly like the eagle's (concave up at the top of
# the stroke, tips below the body at the bottom).
EAGLE_WING = [  # (tip height, mid-span height, half-span)
    (-14.2, 0.8, 18.6), (-8.1, 2.9, 20.7), (6.2, 9.2, 23.5), (16.0, 16.0, 24.5), (21.5, 9.5, 23.5), (16.4, 6.4, 24.5),
    (9.2, 3.2, 27.2), (0.9, -0.1, 30.3), (-2.3, 3.7, 24.4), (10.8, 11.8, 22.6), (23.2, 20.2, 20.2), (24.1, 12.1, 18.2)]
E_SPAN = 24.5                 # the eagle's reference half-span (tip at s = 24.5 of our 30)
# 11/01 (user: wings "stretch out too much at a certain point ... missing a couple frames? smoother"): a SMOOTH
# 12-frame flap loop rendered as extra frames 12..23 (image ids 13..24): the eagle's 8-frame beat fitted with two
# harmonics (no frame-8 span jump), the span swing scaled by SPAN_K, and every periodic term (tail sway/ripple/beat)
# driven by one phase angle so the loop wraps without a hitch.  The fly/idle sequences point at 13..24.
LOOP_BASE, LOOP_N, SPAN_K = 12, 12, 0.45


def _fit_eagle():
    cols = list(zip(*EAGLE_WING[:8])); out = []
    for c in cols:
        a0 = sum(c) / 8
        h = []
        for k in (1, 2):
            ak = sum(v * math.cos(2 * math.pi * k * i / 8) for i, v in enumerate(c)) * 2 / 8
            bk = sum(v * math.sin(2 * math.pi * k * i / 8) for i, v in enumerate(c)) * 2 / 8
            h.append((k, ak, bk))
        out.append((a0, h))
    return out


_EFIT = None


def wing_params(fv):
    """(tip height, mid-span height, half-span) at continuous eagle-frame position fv (0..8, periodic)"""
    global _EFIT
    if _EFIT is None: _EFIT = _fit_eagle()
    vals = []
    for a0, h in _EFIT:
        vals.append(a0 + sum(ak * math.cos(2 * math.pi * k * fv / 8) + bk * math.sin(2 * math.pi * k * fv / 8) for k, ak, bk in h))
    a0span = _EFIT[2][0]
    vals[2] = a0span + SPAN_K * (vals[2] - a0span)
    return tuple(vals)


def loop_phase(frame):
    """loop frames 12..23 -> phase 0..1, else None"""
    return (frame - LOOP_BASE) / LOOP_N if frame >= LOOP_BASE else None


POSE_SHIFT = 2                # image 1 = eagle frame 3 (wings a little raised, gently bowed) - v14 panel pose; 0 = the eagle's own order (wings down)


def wing_outline(side, phi, frame):
    """v10 (user: "wings very stiff, skip frames, don't curve like the eagle's"): the v5 outline wing (span 30,
    chord 14, flame-tongue trailing edge, band/tip) driven by the EAGLE_WING table - height along the span is the
    quadratic through the eagle's measured mid-span and tip heights, the horizontal reach follows its half-span,
    so the phoenix beats, bows and foreshortens exactly as the eagle does in every one of the 12 frames."""
    root_f, root_l, root_u = 1.0, 3.0 * side, 1.2
    # POSE_SHIFT: which eagle pose lands on image 1 of the 8-frame loops (the unit panel shows image 1): the loop is
    # the same cycle, phase-shifted.  Rotating the sequence lists instead made the engine skip frames (10/13).
    lp = loop_phase(frame)
    if lp is not None:
        tipH, midH, span = wing_params((lp * 8 + POSE_SHIFT) % 8)
    else:
        f = ((frame + POSE_SHIFT) % 8) if frame < 8 else frame
        tipH, midH, span = EAGLE_WING[f]
    B = (tipH - 2 * midH) / (2 * (E_SPAN / 2) ** 2) if False else (tipH - 2 * midH) / 288.0
    A = (midH - 144.0 * B) / 12.0
    kx = span / 26.0                                             # horizontal reach relative to our 30-unit span
    ph = 2 * math.pi * (lp if lp is not None else (frame % 8) / 8)
    sweep = -0.10 * math.cos(ph)
    lead = [(6.0, 0.0), (8.2, 6.0), (8.0, 13.0), (6.0, 21.0), (2.2, 30.0)]
    trail = []
    for sp, tipf, notchf in ((30.0, 2.2, None), (27.4, -7.2, -3.0), (24.0, -10.4, -4.8), (20.0, -12.4, -6.0), (15.8, -13.4, -6.8), (11.5, -13.0, -6.6), (7.2, -11.2, -6.0), (3.0, -8.4, -5.0)):
        if notchf is not None: trail.append((notchf, sp + 1.6))
        trail.append((tipf, sp))
    trail.append((-5.2, 0.0))
    outline = lead + trail
    def to3(cf, sp):
        se = sp * E_SPAN / 30.0                                  # our span -> the eagle's measurement scale
        return (root_f + cf + sweep * sp, root_l + side * sp * kx, root_u + A * se + B * se * se)
    full = [to3(cf, sp) for cf, sp in outline]
    def beyond(s0):
        return [to3(cf, sp) for cf, sp in outline if sp >= s0]
    return full, beyond(14.0), beyond(23.0), to3


def render_frame(direction, frame, layers=("body", "head", "wing", "tail")):
    """-> RGBA 64x64 image (alpha 0 = transparent).  `layers` selects which tagged parts are drawn (v8: the
    builder composites the Great Eagle's own wings between the "body"/"tail" and the "head" layers)."""
    P = Projector(direction)
    prims = []                                       # (depth, kind, data, tag)
    TAG = ["body"]
    def poly(pts3, color, outline=OUT, bias=0.0):
        sp = [P.screen(p) for p in pts3]
        prims.append((P.depth(pts3) + bias, "poly", (sp, color, outline), TAG[0]))
    def hullpoly(pts3, color, outline=OUT, bias=0.0):
        sp = hull([P.screen(p) for p in pts3])
        prims.append((P.depth(pts3) + bias, "poly", (sp, color, outline), TAG[0]))
    def seg(p0, p1, width, color, bias=0.0):
        prims.append((P.depth([p0, p1]) + bias, "line", (P.screen(p0), P.screen(p1), width, color), TAG[0]))
    phi = math.radians(-34.0 * math.cos(2 * math.pi * frame / 12) + 4.0)      # frame 0 = wings DOWN (the unit panel shows frame 1); gentler than v7
    # body + belly
    hullpoly(ellipsoid_pts((0.0, 0.0, 0.0), (9.5, 5.2, 5.0)), RED1)
    hullpoly(ellipsoid_pts((2.5, 0.0, -2.4), (6.2, 4.0, 2.6)), BELLY, outline=None, bias=-0.5)
    # neck + head + beak
    # v4: neck/head/beak/eyes/crest carry a large "nearer" bias so the head is never hidden behind the near wing in
    # the three-quarter views; the head sits higher and is a little bigger
    HB = -14.0
    TAG[0] = "head"
    # attack frames 9-11 (indices 8..10): the head SWOOPS - neck and head pitch down and reach forward about the
    # shoulder, most at frame 10; the hit frame 12 (index 11) keeps the normal pose
    dip = {8: 0.5, 9: 1.0, 10: 0.7}.get(frame, 0.0)
    ang = -0.7 * dip; ca, sa = math.cos(ang), math.sin(ang); pf, pu = 6.0, 2.0
    def hd(pts):
        if not dip: return pts
        out = []
        for f_, l_, u_ in pts:
            df, du = f_ - pf, u_ - pu
            out.append((pf + df * ca - du * sa + 2.5 * dip, l_, pu + df * sa + du * ca))
        return out
    hullpoly(hd([(6.5, l, 2.0 + u) for l in (-2.2, 2.2) for u in (-1.5, 1.5)] + [(10.5, l, 5.8 + u) for l in (-2.0, 2.0) for u in (-1.6, 1.6)]), RED2, bias=HB)
    hullpoly(hd(ellipsoid_pts((11.4, 0.0, 6.4), (4.1, 3.6, 3.7))), RED2, bias=HB - 1)
    hullpoly(hd([(14.2, -1.4, 7.4), (14.2, 1.4, 7.4), (14.2, -1.4, 4.9), (14.2, 1.4, 4.9), (19.4, 0.0, 6.0), (17.6, 0.0, 4.1)]), BEAK, outline=BEAK_D, bias=HB - 2)
    for side in (-1, 1):
        n_f = side * P.dR                            # eye normal's depth component
        if -n_f > -0.2:
            e = hd([(12.8, side * 3.5, 7.3)])[0]
            prims.append((P.depth([e]) + HB - 3, "dot", (P.screen(e), EYE_D), "head"))
    # crest: five plumes from the crown sweeping back
    for k in (-1.0, -0.5, 0.0, 0.5, 1.0):
        _lp = loop_phase(frame)
        sway = 0.7 * math.sin((2 * math.pi * _lp if _lp is not None else frame * 0.55) + k * 1.7)
        pts = hd([(10.8, k * 0.8, 9.4), (8.4, k * 1.8, 12.2 + sway * 0.4), (5.4, k * 2.8, 14.4 + sway), (2.0, k * 3.6, 15.6 + sway * 1.4)])
        for i in range(len(pts) - 1):
            seg(pts[i], pts[i + 1], 2.0 if i < 2 else 1.4, ORG if i < 1 else GOLD1 if i < 2 else WHITE, bias=HB)
    # wings
    TAG[0] = "wing"
    for side in (-1, 1):
        full, band, tip, to3 = wing_outline(side, phi, frame)
        bias = 0.8                                    # wings sit on the body's back
        poly(full, RED1, bias=bias); poly(band, GOLD0, outline=None, bias=bias - 0.01); poly(tip, GREEN1, outline=None, bias=bias - 0.02)
        for sp in (9.0, 13.5, 18.0, 22.5, 26.5):          # feather lines on the band
            seg(to3(3.0, sp), to3(-6.0, sp + 0.8), 0.8, RED2, bias=bias - 0.03)
    # tail: five long plumes streaming back and down with a travelling wave
    TAG[0] = "tail"
    for k in (-1.0, -0.5, 0.0, 0.5, 1.0):
        prev = None
        n = 9
        for i in range(n + 1):
            t = i / n
            f = -8.5 - 20.0 * t
            toward = P.dF < -0.1
            l = k * (1.4 + (14.0 if toward else 8.0) * t)         # facing the camera: fan the tail wide so it shows beside the body
            droop = 3.0 if toward else 1.0                 # facing the camera: the tail is behind = higher on screen, so it must hang well below the body
            # v15: the tail MOVES - a stronger travelling ripple plus a whole-tail swing that follows the wing-beat
            _lp = loop_phase(frame)
            if _lp is not None:
                beat = math.sin(2 * math.pi * (_lp + POSE_SHIFT / 8)); rip = 2 * math.pi * _lp
            else:
                beat = math.sin(2 * math.pi * ((frame + POSE_SHIFT) % 8) / 8) if frame < 8 else 0.0; rip = frame * 0.8
            u = 0.6 - (2.0 * t + 5.5 * t * t) * droop + 2.4 * t * math.sin(3.2 * t + rip + k * 1.1) + 2.0 * t * beat
            p = (f, l, u)
            if prev is not None:
                col = ORG if t < 0.3 else GOLD0 if t < 0.6 else GOLD1 if t < 0.82 else WHITE
                seg(prev, p, 2.2 if t < 0.55 else 1.6, col, bias=1.2)
            prev = p
    # legs tucked under the belly
    TAG[0] = "body"
    for side in (-1, 1):
        seg((1.5, side * 2.0, -4.2), (3.0, side * 2.4, -7.6), 1.2, GOLD0, bias=-0.6)
    # draw, far first
    im = Image.new("RGBA", (FW * SS, FH * SS), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    for depth, kind, data, tag in sorted(prims, key=lambda t: -t[0]):
        if tag not in layers: continue
        if kind == "poly":
            sp, color, outline = data
            if len(sp) >= 3:
                if outline == OUT:                       # 11/01 (user: black outline not as subtle as vanilla units):
                    outline = tuple(int(c * OUT_SHADE) for c in color)   # edge = the fill darkened, like vanilla sprites
                dr.polygon(sp, fill=color + (255,), outline=(outline + (255,)) if outline else None)
                if outline:
                    dr.line(sp + [sp[0]], fill=outline + (255,), width=max(1, int(OUT_W * SS)))
        elif kind == "line":
            a, b, w, color = data
            dr.line([a, b], fill=color + (255,), width=max(1, int(w * SS)))
        else:
            (x, y), color = data
            r = 0.75 * SS; dr.ellipse([x - r, y - r, x + r, y + r], fill=color + (255,))
    small = im.resize((FW, FH), Image.LANCZOS)
    a = np.array(small); a[:, :, 3] = np.where(a[:, :, 3] >= 110, 255, 0)
    return Image.fromarray(a, "RGBA")


def frames():
    """{image id: RGBA} for the 72 sprite frames in the eagle's id scheme (d*100 + f + 1)."""
    out = {}
    for d in range(1, 7):
        for f in range(LOOP_BASE + LOOP_N):
            out[d * 100 + f + 1] = render_frame(d, f)
    return out


# ---------------------------------------------------------------- the portrait v3 (103x128): the eagle painting re-forged
def fire_ramp_np(v):
    stops = [(0.00, (70, 6, 4)), (0.25, (170, 28, 8)), (0.50, (240, 110, 15)), (0.75, (255, 200, 70)), (1.00, (255, 248, 210))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if v <= t1:
            k = (v - t0) / (t1 - t0)
            return [c0[i] + (c1[i] - c0[i]) * k for i in range(3)]
    return list(stops[-1][1])


def portrait_v3(eagle, fires):
    """eagle = the vanilla Great Eagle portrait (PIL RGB 103x128, the game's own painted style); fires = list of RGBA
    vanilla FireLg frames.  The bird is re-coloured to fire while KEEPING its painted feather texture, the sky becomes
    a dark ember vignette with a glow round the head, and real flames (the game's own fire art) rise as a crest from
    the crown, stream back from the nape as a mane and lick up from the wing at the bottom; gold beak, glowing eye."""
    W, H = eagle.size
    a = np.array(eagle).astype(np.float32); r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    lum = (0.3 * r + 0.59 * g + 0.11 * b) / 255.0
    sky = (b > r + 18) & (b > g + 6)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ramp = np.array([[fire_ramp_np(v) for v in row] for row in lum ** 0.85], np.float32)
    tex = lum[:, :, None] * 255.0
    out = 0.72 * ramp + 0.28 * tex                                                 # fire colour, painted texture kept
    glow = np.exp(-((xx - 66) ** 2 + (yy - 60) ** 2) / (2 * 30.0 ** 2))
    skycol = np.stack([38 + 60 * (1 - yy / H), 6 + 10 * (1 - yy / H), 8 + 4 * (1 - yy / H)], axis=2)
    skycol = skycol + glow[:, :, None] * np.array([255, 120, 25], np.float32) * 0.6
    out[sky] = skycol[sky]
    beak = (~sky) & (xx > 78) & (xx < 100) & (yy > 50) & (yy < 74) & (lum > 0.45)
    out[beak] = 0.55 * np.array([255, 205, 70], np.float32) + 0.45 * out[beak]
    eye = np.exp(-((xx - 72) ** 2 + (yy - 53) ** 2) / 6.0)
    out = out + eye[:, :, None] * np.array([255, 225, 120], np.float32)
    def flame(idx, sw, sh, cx, base_y, strength, flip=False):
        fr = fires[idx % len(fires)].resize((sw, sh), Image.LANCZOS)
        if flip: fr = fr.transpose(Image.FLIP_LEFT_RIGHT)
        f = np.array(fr).astype(np.float32); fa = f[:, :, 3] / 255.0 * strength
        fade = np.clip((np.arange(sh)[:, None] - sh * 0.62) / (sh * 0.38), 0, 1)
        fa = fa * (1 - fade)
        x0 = int(cx - sw / 2); y0 = int(base_y - sh)
        for j in range(sh):
            Y = y0 + j
            if Y < 0 or Y >= H: continue
            for i in range(sw):
                X = x0 + i
                if X < 0 or X >= W: continue
                k = fa[j, i]
                if k <= 0.01: continue
                out[Y, X] = out[Y, X] + k * f[j, i, :3] * (1 - out[Y, X] / 320.0)
    flame(2, 52, 70, 62, 52, 1.0)                    # crest from the crown
    flame(5, 40, 56, 50, 56, 0.9, flip=True)         # second crest tongue, leaning back
    flame(9, 48, 64, 30, 82, 0.85, flip=True)        # mane from the nape / back
    flame(12, 70, 60, 20, 128, 0.9)                  # flames off the wing, bottom left
    flame(15, 60, 52, 80, 128, 0.8, flip=True)       # flames off the wing, bottom right
    rnd = random.Random(2711)
    for _ in range(120):
        x, y = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
        if not sky[y, x]: continue
        c = np.array(rnd.choice([(255, 220, 120), (255, 150, 40), (255, 90, 20)]), np.float32); k = rnd.uniform(0.5, 1.0)
        out[y, x] = out[y, x] * (1 - k) + c * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def _noise(w, h, seed, scales=(4, 9, 20)):
    """Multi-scale value noise in [-1, 1] (random fields blurred at several radii, summed)."""
    rnd = np.random.RandomState(seed); acc = np.zeros((h, w), np.float32)
    for k, sc in enumerate(scales):
        f = Image.fromarray((rnd.rand(h, w) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(sc))
        a = np.array(f).astype(np.float32); a = (a - a.mean()) / max(1e-3, a.std()); acc += a / (k + 1)
    return acc / np.abs(acc).max()


def portrait_v4(fires):
    """From scratch, painterly (vanilla portrait style): a phoenix head in profile facing right - a raptor head with
    a big hooked gold beak, a fierce eye, a crest of long flame plumes sweeping up and back, layered neck feathers in
    reds and golds, a dark wing mass below - lit from the upper left, with feather-grain noise, soft shading and a
    dark ember sky with a glow and embers; the game's own fire frames burn at the crown and off the wing."""
    W, H, S = 103, 128, 3
    Wn, Hn = W * S, H * S
    yy, xx = np.mgrid[0:Hn, 0:Wn].astype(np.float32) / S
    out = np.zeros((Hn, Wn, 3), np.float32)
    # sky
    for c, (t, b) in enumerate(((66, 20), (10, 4), (12, 6))): out[:, :, c] = t + (b - t) * (yy / H)
    glow = np.exp(-((xx - 60) ** 2 + (yy - 62) ** 2) / (2 * 34.0 ** 2))
    out += glow[:, :, None] * np.array([255, 130, 30], np.float32) * 0.55
    smoke = _noise(Wn, Hn, 7, (12, 30, 60)); out += (smoke[:, :, None] * 18.0) * np.array([1.0, 0.5, 0.3], np.float32)
    grain = _noise(Wn, Hn, 11, (2, 5, 11))
    def shade(mask, nx, ny, base, hi, lo, tex=0.12):
        """Paint `base` into out where mask, lit along (nx, ny) (unit fake normals), with highlight/shadow tints."""
        l = np.clip(-0.62 * nx - 0.78 * ny, -1, 1)
        col = np.zeros_like(out)
        for c in range(3):
            col[:, :, c] = base[c] + np.where(l > 0, l * (hi[c] - base[c]), -l * (lo[c] - base[c]))
        col *= (1 + tex * grain)[:, :, None]
        out[mask] = col[mask]
    def ell(cx, cy, rx, ry):
        nx, ny = (xx - cx) / rx, (yy - cy) / ry
        return (nx ** 2 + ny ** 2) <= 1.0, nx, ny
    # wing / body mass at the bottom
    m, nx, ny = ell(30, 150, 80, 52); shade(m, nx, ny, (150, 24, 10), (214, 70, 20), (70, 8, 6))
    m, nx, ny = ell(92, 160, 60, 60); shade(m, nx, ny, (160, 30, 12), (220, 80, 24), (70, 8, 6))
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"); dr = ImageDraw.Draw(im)
    def L(pts, fill, w): dr.line([(x * S, y * S) for x, y in pts], fill=fill, width=max(1, int(w * S)), joint="curve")
    def P(pts, fill, outline=None, w=1.0):
        dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
        if outline: dr.line([(x * S, y * S) for x, y in pts] + [(pts[0][0] * S, pts[0][1] * S)], fill=outline, width=max(1, int(w * S)))
    def curve(ctrl, n=20):
        pts = []
        for i in range(len(ctrl) - 1):
            p0 = ctrl[max(i - 1, 0)]; p1 = ctrl[i]; p2 = ctrl[i + 1]; p3 = ctrl[min(i + 2, len(ctrl) - 1)]
            for k in range(n):
                t = k / n; t2 = t * t; t3 = t2 * t
                pts.append((0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                            0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
        pts.append(ctrl[-1]); return pts
    # feather scallops on the wing mass
    for row in range(6):
        y0 = 100 + row * 5
        for i in range(-1, 12):
            x0 = i * 10 + (5 if row % 2 else 0)
            arc = [(x0 + 5 * math.cos(math.pi * (1 - t)), y0 + 6 + 5 * math.sin(math.pi * (1 - t)) * 0.7) for t in [k / 10 for k in range(11)]]
            L(arc, (232 - row * 10, 120 - row * 10, 30), 0.9)
    out = np.array(im).astype(np.float32)
    # crest plumes (long, back-swept) BEHIND the head
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"); dr = ImageDraw.Draw(im)
    plumes = ((52, 44, 36, 24, 18, 6), (57, 42, 44, 16, 30, 0), (62, 41, 54, 14, 44, -2), (67, 41, 64, 16, 60, 2), (71, 43, 74, 24, 78, 12), (47, 48, 26, 36, 6, 24))
    for (x1, y1, x2, y2, x3, y3) in plumes:
        pts = curve([(x1 + 3, y1 + 6), (x1, y1), (x2, y2), (x3, y3)]); n = len(pts)
        for i in range(n - 1):
            t = i / (n - 1); w = 5.0 * (1 - t) + 1.2
            col = (236, 112, 22) if t < 0.3 else (226, 160, 36) if t < 0.62 else (236, 184, 58) if t < 0.85 else (246, 206, 96)
            L([pts[i], pts[i + 1]], (70, 8, 6), w + 1.8); L([pts[i], pts[i + 1]], col, w)
            if t > 0.1: L([pts[i], pts[i + 1]], (250, 220, 120), max(0.6, w * 0.3))
    out = np.array(im).astype(np.float32)
    # neck (shaded cylinder) and head (shaded ellipse), feather grain
    neck = (yy > 74) & (yy < 130) & (xx > 38 + (yy - 74) * -0.18) & (xx < 74 + (yy - 74) * 0.22)
    nx = ((xx - (56 + (yy - 74) * 0.02)) / 18.0); ny = np.zeros_like(nx) + 0.15
    shade(neck, nx, ny, (214, 60, 18), (240, 120, 36), (110, 16, 8), tex=0.16)
    m, nx, ny = ell(61, 64, 25, 22); shade(m, nx, ny, (228, 74, 22), (246, 140, 40), (120, 18, 8), tex=0.14)
    m2, nx2, ny2 = ell(70, 76, 13, 10); shade(m2 & m, nx2, ny2, (232, 150, 44), (246, 190, 80), (170, 70, 20), tex=0.1)
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"); dr = ImageDraw.Draw(im)
    # neck feather scallops (layered)
    for row in range(8):
        y0 = 84 + row * 6
        for i in range(0, 8):
            x0 = 38 + i * 6 + (3 if row % 2 else 0) - row * 0.6
            arc = [(x0 + 3.2 * math.cos(math.pi * (1 - t)), y0 + 3.2 * math.sin(math.pi * (1 - t)) * 0.8) for t in [k / 8 for k in range(9)]]
            L(arc, (120, 20, 8), 0.8); L([(x, y - 0.8) for x, y in arc], (244, 150, 44), 0.6)
    # head outline / brow
    L(curve([(40, 70), (42, 52), (56, 42), (74, 44), (84, 52)]), (90, 12, 6), 1.2)
    # beak: hooked, gold, dark seam and tip
    P([(82, 50), (96, 54), (103, 62), (101, 70), (94, 74), (86, 70), (82, 62)], (236, 184, 58), (120, 70, 14), 1.1)
    P([(84, 52), (95, 56), (100, 61), (90, 60), (84, 58)], (246, 206, 96))                     # top light
    P([(83, 64), (94, 69), (98, 73), (88, 74), (82, 70)], (186, 120, 24), (100, 50, 10), 0.8)   # lower mandible
    L([(84, 61), (97, 64)], (120, 70, 14), 0.9)
    dr.ellipse([86 * S, 56 * S, 88.5 * S, 58 * S], fill=(120, 60, 10))                          # nostril
    # eye: fierce, under a dark brow
    P([(66, 56), (74, 53), (80, 57), (74, 61)], (40, 10, 6))
    dr.ellipse([68 * S, 54 * S, 78 * S, 60.5 * S], fill=(236, 150, 40))
    dr.ellipse([71 * S, 55 * S, 76.5 * S, 60 * S], fill=(20, 8, 6))
    dr.ellipse([72 * S, 55.5 * S, 74 * S, 57.5 * S], fill=(255, 240, 200))
    L(curve([(64, 55), (72, 50), (82, 54)]), (60, 10, 6), 1.6)
    out = np.array(im).astype(np.float32)
    # the game's fire: crest base and wing flames
    def flame(idx, sw, sh, cx, base_y, strength, flip=False):
        fr = fires[idx % len(fires)].resize((sw * S, sh * S), Image.LANCZOS)
        if flip: fr = fr.transpose(Image.FLIP_LEFT_RIGHT)
        f = np.array(fr).astype(np.float32); fa = f[:, :, 3] / 255.0 * strength
        fade = np.clip((np.arange(sh * S)[:, None] - sh * S * 0.6) / (sh * S * 0.4), 0, 1); fa = fa * (1 - fade)
        x0 = int((cx - sw / 2) * S); y0 = int((base_y - sh) * S)
        ys0, ys1 = max(0, y0), min(Hn, y0 + sh * S); xs0, xs1 = max(0, x0), min(Wn, x0 + sw * S)
        sub = out[ys0:ys1, xs0:xs1]; k = fa[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0][:, :, None]; src = f[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0, :3]
        out[ys0:ys1, xs0:xs1] = sub + k * src * (1 - sub / 330.0)
    flame(3, 44, 60, 58, 50, 0.75)
    flame(8, 36, 50, 42, 60, 0.6, flip=True)
    flame(12, 70, 58, 22, 128, 0.85)
    flame(15, 60, 50, 84, 128, 0.8, flip=True)
    rnd = random.Random(2712)
    for _ in range(90):
        x, y = rnd.randint(0, Wn - 1), rnd.randint(0, Hn - 1)
        if (xx[y, x] - 61) ** 2 / 26 ** 2 + (yy[y, x] - 64) ** 2 / 23 ** 2 < 1 or yy[y, x] > 96: continue
        c = np.array(rnd.choice([(255, 220, 120), (255, 150, 40), (255, 90, 20)]), np.float32); k = rnd.uniform(0.5, 1.0)
        out[y:y + 3, x:x + 3] = out[y:y + 3, x:x + 3] * (1 - k) + c * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.LANCZOS)


def portrait():
    W, H = 103, 128; S = 3
    im = Image.new("RGB", (W * S, H * S)); dr = ImageDraw.Draw(im)
    # sky: dark crimson, a golden radial glow behind the head, embers
    yy, xx = np.mgrid[0:H * S, 0:W * S].astype(np.float32) / S
    glow = np.exp(-((xx - 58) ** 2 + (yy - 62) ** 2) / (2 * 34.0 ** 2))
    sky = np.zeros((H * S, W * S, 3), np.float32)
    base_top, base_bot = np.array([54, 6, 10]), np.array([22, 4, 8])
    for c in range(3): sky[:, :, c] = base_top[c] + (base_bot[c] - base_top[c]) * (yy / H)
    gl = np.array([255, 150, 40])
    for c in range(3): sky[:, :, c] += gl[c] * 0.55 * glow
    im = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8), "RGB"); dr = ImageDraw.Draw(im)
    rnd = random.Random(271)
    for _ in range(140):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H); r = rnd.uniform(0.3, 1.1)
        c = rnd.choice([(255, 220, 120), (255, 160, 50), (255, 100, 30)])
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=c)
    def P(pts, fill, outline=None, w=1.0):
        dr.polygon([(x * S, y * S) for x, y in pts], fill=fill, outline=outline)
        if outline: dr.line([(x * S, y * S) for x, y in pts] + [(pts[0][0] * S, pts[0][1] * S)], fill=outline, width=int(w * S))
    def E(box, fill, outline=None, w=1.0):
        dr.ellipse([box[0] * S, box[1] * S, box[2] * S, box[3] * S], fill=fill, outline=outline, width=int(w * S) if outline else 1)
    def Ln(pts, fill, w):
        dr.line([(x * S, y * S) for x, y in pts], fill=fill, width=max(1, int(w * S)), joint="curve")
    def curve(ctrl, n=24):
        pts = []
        for i in range(len(ctrl) - 1):
            p0 = ctrl[max(i - 1, 0)]; p1 = ctrl[i]; p2 = ctrl[i + 1]; p3 = ctrl[min(i + 2, len(ctrl) - 1)]
            for k in range(n):
                t = k / n; t2 = t * t; t3 = t2 * t
                pts.append((0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                            0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
        pts.append(ctrl[-1]); return pts
    # wing mass at the bottom left + body behind the neck
    P([(0, 128), (0, 92), (18, 86), (40, 92), (62, 104), (84, 118), (103, 122), (103, 128)], RED0)
    for i in range(8):
        x0 = 4 + i * 11
        Ln(curve([(x0, 128), (x0 + 6, 112 - i), (x0 + 16, 100 - i * 0.6)]), GOLD0 if i % 2 else RED2, 1.6)
    # crest plumes from the crown sweeping up and back (drawn before the head so they emerge from behind it)
    for k, (x1, y1, x2, y2, x3, y3) in enumerate(((50, 40, 34, 22, 14, 6), (54, 38, 40, 16, 24, 2), (58, 37, 48, 14, 36, 1), (62, 37, 56, 15, 48, 3), (66, 38, 64, 18, 60, 6), (46, 44, 28, 30, 8, 18))):
        pts = curve([(x1 + 4, y1 + 6), (x1, y1), (x2, y2), (x3, y3)])
        n = len(pts)
        for i in range(n - 1):
            t = i / (n - 1); w = 4.4 * (1 - t) + 1.2
            col = GOLD0 if t < 0.45 else GOLD1 if t < 0.62 else GREEN1 if t < 0.85 else WHITE
            Ln([pts[i], pts[i + 1]], OUT, w + 1.6); Ln([pts[i], pts[i + 1]], col, w)
    # neck + head
    P(curve([(40, 118), (44, 96), (50, 78), (58, 66), (72, 62), (80, 70), (78, 86), (70, 104), (64, 128)], 10), RED1, OUT, 1.2)
    E((38, 42, 86, 84), RED2, OUT, 1.2)                                           # skull
    E((50, 60, 86, 90), BELLY, None)                                              # cream cheek/throat
    E((44, 44, 78, 70), RED2, None)                                               # crown over the cheek
    # throat feathers (cream streaks) and neck feathers (red/gold streaks)
    for i in range(7):
        Ln(curve([(52 + i * 3, 84 + i), (50 + i * 3, 96 + i * 2), (46 + i * 3, 108 + i * 2)]), BELLY if i < 4 else GOLD0, 1.4)
    # beak: hooked, gold, with a dark edge
    P([(78, 52), (94, 55), (101, 62), (99, 69), (92, 72), (84, 66), (78, 62)], BEAK, BEAK_D, 1.1)
    P([(79, 64), (90, 68), (94, 72), (86, 73), (78, 70)], BEAK_D, OUT, 0.8)
    Ln([(80, 58), (94, 61)], BEAK_D, 0.8)
    # eye
    E((62, 52, 74, 62), WHITE, OUT, 1.0)
    E((65, 53, 73, 61), (210, 60, 20), None)
    E((67, 55, 72, 60), EYE_D, None)
    E((67.5, 55.5, 69.5, 57.5), WHITE, None)
    Ln(curve([(60, 50), (68, 48), (76, 52)]), OUT, 1.4)                             # brow
    # a few flame licks round the head
    for (x, y, h) in ((30, 60, 10), (34, 76, 8), (90, 44, 9), (96, 80, 7)):
        pts = curve([(x, y + h), (x + 2, y + h * 0.5), (x - 1, y)])
        Ln(pts, ORG, 2.2); Ln(pts[len(pts) // 2:], GOLD1, 1.2)
    out = im.resize((W, H), Image.LANCZOS)
    return out


if __name__ == "__main__":
    import sys
    fr = frames(); S = 3
    sheet = Image.new("RGB", (12 * 64 * S + 103 * 3 + 20, 6 * 64 * S), (28, 28, 48))
    for d in range(6):
        for f in range(12):
            im = fr[(d + 1) * 100 + f + 1].resize((64 * S, 64 * S), Image.NEAREST); sheet.paste(im, (f * 64 * S, d * 64 * S), im)
    sheet.paste(portrait().resize((309, 384)), (12 * 64 * S + 10, 0))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else "phoenix_art_preview.png"); print("ok")
