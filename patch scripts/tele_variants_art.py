#!/usr/bin/env python3
r"""
Teleporter terrain variants art (2026-11-06): ice, lava, floating (sky / chasm).

User: "we added water teleporters but i think we should also add ice teleporters for when the water theyre on gets
frozen.... lets also add lava teleporters. i also want to add teleporters for sky/clear sky/chasm however these
should have different GFX because they would be floating. and maybe slowly rotating/levitating?"

Map frames (all built from STR_TELE.ILB stone ring frame 0 (surface) / 2 (underground), like tele_water_art):
  ice_base(gd, under)       60x65  frosted stones frozen into an ice collar with cracks
  ice_glints(gd, under)     ICE_N frames: a few twinkles wandering over the ice collars / frost caps
  lava_base(gd, under)      60x65  charred stones, heat-lit feet, crust ring + glowing rim
  lava_anim(gd, under)      LAVA_N frames: rim pulse per stone + rising embers
  float_frames(gd, kind)    FLOAT_N frames FW x FH: the ring standing on a floating rock island; the island and the
                            ring turn one full revolution per cycle, the whole thing bobs (2 bobs per revolution);
                            kind 'sky' = grassy island, 'chasm' = black basalt with violet veins.
  float_glow(gd, kind)      FLOAT_N frames FW x FH: the vanilla teal flame (STR_TELE 6) riding on the five stones
                            that carry a glow in vanilla, each pulsing on its own phase (additive, 770 / 45);
                            chasm = violet flames.
Side portraits 57x278 (BORDER.ILB style): portrait_ice / portrait_lava (from the record's own portrait),
portrait_float(kind) (from the surface portrait 41 for sky, underground 131 for chasm).
--preview <dir> writes PNG sheets + GIFs.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eagle_nest_art as V1  # noqa: E402
import tele_water_art as W  # noqa: E402

HOLD = 2
ICE_N, LAVA_N, FLOAT_N = 32, 32, 360
FLOAT_HOLD = 1                               # v6 (user: still jittery, more frames): 360 frames x 1 tick per turn
FW, FH, OX, OY = 80, 124, 10, 48            # floating canvas; vanilla 60x65 canvas origin sits at (OX, OY) in it
LIFT = 10                                    # the ring stands this much higher than on the ground
GLOW_STONES = ((41, 48), (21, 49), (14, 34), (32, 26), (48, 30))   # vanilla glow peaks (base-canvas coords)


def _stone_ring(gd, under):
    lib, by = V1._load(gd, "STR_TELE.ILB")
    a = V1._rgba(lib, by[2 if under else 0].primary)
    m = a[..., 3] > 0
    lab, n = W._components(m)
    comps = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        yb = ys.max()
        foot = ((xs[ys >= yb - 1].min() + xs[ys >= yb - 1].max()) / 2.0, float(yb))
        comps.append(dict(ys=ys, xs=xs, foot=foot, big=len(ys) >= 30, px=a[ys, xs].copy(),
                          xl=xs[ys >= yb - 1].min(), xr=xs[ys >= yb - 1].max(), yb=yb, top=ys.min()))
    return a, m, comps


def _put(out, m, x, y, c, a=255):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < out.shape[1] and 0 <= y < out.shape[0] and (m is None or not m[y, x]):
        out[y, x, :3] = c; out[y, x, 3] = a


def _mix(c1, c2, f):
    return tuple(int(round(a * (1 - f) + b * f)) for a, b in zip(c1, c2))


# ---------------------------------------------------------------------------------------------------------------- ice
# v3 (user: "rework bases effect of ice teleporters, i dont like the dots"): no single pixels anywhere.  The stone
# feet blend into the ice, each foot sits in a low smooth ice skirt (a light row fading out at its ends over a faint
# shadow row), the frost caps are a continuous light rim, and the animation is a soft sheen sliding diagonally across
# each stone's frozen foot once per cycle (staggered per stone).
ICE_COL = {False: (176, 206, 226), True: (128, 160, 178)}


def _ice(gd, under):
    a, m, comps = _stone_ring(gd, under)
    out = a.astype(float)
    tint = np.array((0.90, 0.96, 1.07)) if not under else np.array((0.84, 0.92, 1.0))
    out[m, :3] = np.clip(out[m, :3] * tint, 0, 255)
    ice = np.array(ICE_COL[under], float)
    frost = ice * 0.5 + 255 * 0.5
    feet = []
    for c in comps:
        if not c["big"]:
            continue
        for x in np.unique(c["xs"]):                          # continuous frost rim on top
            t = c["ys"][c["xs"] == x].min()
            out[t, x, :3] = out[t, x, :3] * 0.7 + frost * 0.3
        for k, y in enumerate(range(c["yb"] - 2, c["yb"] + 1)):  # frozen-in foot
            row = c["xs"][c["ys"] == y]
            f = (0.16, 0.30, 0.46)[k]
            out[y, row, :3] = out[y, row, :3] * (1 - f) + ice * f
        feet.append(c)
    res = np.clip(out, 0, 255)
    res[..., 3] = np.where(a[..., 3] > 0, 255, 0)
    light, shadow = ice * 0.55 + 255 * 0.45, ice * 0.80
    skirt = np.zeros(m.shape, bool)
    for c in feet:                                            # smooth ice skirt around the foot
        cx, half, yb = (c["xl"] + c["xr"]) / 2.0, (c["xr"] - c["xl"]) / 2.0, c["yb"]
        for dy, col, k, spread in ((1, light, 0.55, 1.5), (2, shadow, 0.45, 0.0)):
            y = yb + dy
            for x in range(int(cx - half - 2), int(cx + half + 3)):
                pr = 1 - (abs(x - cx) / (half + spread + 0.5)) ** 2
                if pr <= 0.25 or not (0 <= y < m.shape[0] and 0 <= x < m.shape[1]) or m[y, x] or skirt[y, x]:
                    continue
                res[y, x, :3] = ice * (1 - k * pr) + col * k * pr
                res[y, x, 3] = 255
                skirt[y, x] = True
    return res.astype(np.uint8), m, feet, skirt


def ice_base(gd, under=False):
    return _ice(gd, under)[0]


def ice_glints(gd, under=False):
    """ICE_N frames: a soft diagonal sheen slides across each stone's frozen foot + skirt once per cycle"""
    base, m, feet, skirt = _ice(gd, under)
    b = base.astype(float)
    phases = [(i * 11) % ICE_N for i in range(len(feet))]
    SWEEP = 12                                               # frames the sheen takes to cross a stone
    frames = []
    for k in range(ICE_N):
        out = np.zeros(m.shape + (4,), np.uint8)
        for c, ph in zip(feet, phases):
            t = (k - ph) % ICE_N
            if t >= SWEEP:
                continue
            pos = c["xl"] - 3 + (c["xr"] - c["xl"] + 6) * t / (SWEEP - 1)
            fade = math.sin(math.pi * (t + 0.5) / SWEEP)
            for y in range(c["yb"] - 4, c["yb"] + 2):
                for x in range(c["xl"] - 2, c["xr"] + 3):
                    if not (0 <= y < m.shape[0] and 0 <= x < m.shape[1]) or base[y, x, 3] == 0:
                        continue
                    if not (m[y, x] and y >= c["yb"] - 4) and not skirt[y, x]:
                        continue
                    g = 0.34 * fade * math.exp(-(((x - pos) + (c["yb"] - y) * 0.6) / 1.4) ** 2)
                    if g < 0.05:
                        continue
                    out[y, x, :3] = np.clip(b[y, x, :3] * (1 - g) + 255 * g, 0, 255)
                    out[y, x, 3] = 255
        frames.append(out)
    return frames


# --------------------------------------------------------------------------------------------------------------- lava
# v2 (user: "make the fire/lava effects near its base more subtle, like the water teleporter"): no crust ring / pool;
# only the lowest stone rows are heat-lit, and the animation is a sparse dotted shimmer just in front of each foot in
# colours close to the lava (like the water foam), plus one short-lived ember per stone per cycle.
LAVA_COL = {False: (190, 66, 20), True: (170, 56, 18)}


def _lava(gd, under):
    a, m, comps = _stone_ring(gd, under)
    out = a.astype(float)
    out[m, :3] = np.clip(out[m, :3] * np.array((0.80, 0.72, 0.68)), 0, 255)   # a little sooty
    heat = np.array((226, 104, 36), float)
    feet = []
    for c in comps:
        if not c["big"]:
            continue
        for k, y in enumerate(range(c["yb"] - 3, c["yb"] + 1)):
            row = c["xs"][c["ys"] == y]
            f = (0.08, 0.16, 0.26, 0.38)[k]
            out[y, row, :3] = out[y, row, :3] * (1 - f) + heat * f
        feet.append((c["xl"], c["xr"], c["yb"]))
    res = out.copy()
    res[..., 3] = np.where(res[..., 3] > 0, 255, 0)
    res = np.clip(res, 0, 255).astype(np.uint8)
    rims = []
    for xl, xr, yb in feet:
        rim = [(x, yb + 1) for x in range(xl - 1, xr + 2)] + [(xl - 1, yb), (xr + 1, yb)]
        rims.append(([(x, y) for x, y in rim if 0 <= y < m.shape[0] and 0 <= x < m.shape[1] and not m[y, x]],
                     ((xl + xr) / 2, yb, (xr - xl) / 2 + 1)))
    return res, m, rims


def lava_base(gd, under=False):
    return _lava(gd, under)[0]


def lava_anim(gd, under=False):
    _, m, rims = _lava(gd, under)
    rng = np.random.default_rng(0x1A7A)
    lava = np.array(LAVA_COL[under], float)
    hot = np.array((236, 132, 44), float)
    em = [np.array(c, float) for c in ((240, 150, 60), (210, 100, 36), (160, 64, 26))]
    phases = rng.integers(0, LAVA_N, len(rims))
    frames = []
    for k in range(LAVA_N):
        out = np.zeros(m.shape + (4,), np.uint8)
        for i, ((rim, (cx, yb, rx)), ph) in enumerate(zip(rims, phases)):
            t = ((k + ph) % LAVA_N) / LAVA_N
            g = 0.25 + 0.35 * (0.5 + 0.5 * math.sin(2 * math.pi * t))        # gentle swell
            for j, (x, y) in enumerate(rim):
                if (j + k // 2 + i) % 3:                                      # sparse, slowly travelling dots
                    continue
                _put(out, m, x, y, tuple((lava * (1 - g) + hot * g).astype(int)))
            e = (k + ph) % LAVA_N                                             # one ember per stone per cycle
            if e < 6:
                x = cx + (((i * 5) % 3) - 1) * rx * 0.6
                _put(out, m, x, yb - 1 - e * 1.5, tuple(em[min(2, e // 2)].astype(int)))
        frames.append(out)
    return frames


# ----------------------------------------------------------------------------------------------------------- floating
def _noise(seed, n=48):
    rng = np.random.default_rng(seed)
    g = rng.random((n, n))
    for _ in range(2):
        g = (g + np.roll(g, 1, 0) + np.roll(g, 1, 1) + np.roll(g, -1, 0) + np.roll(g, -1, 1)) / 5
    g = (g - g.min()) / (g.max() - g.min())
    return g


def _bil(g, u, v):
    n = g.shape[0]
    x, y = (u * 0.5 + 0.5) * (n - 2), (v * 0.5 + 0.5) * (n - 2)
    x0, y0 = int(x), int(y)
    fx, fy = x - x0, y - y0
    x0, y0 = min(max(x0, 0), n - 2), min(max(y0, 0), n - 2)
    return (g[y0, x0] * (1 - fx) * (1 - fy) + g[y0, x0 + 1] * fx * (1 - fy) + g[y0 + 1, x0] * (1 - fx) * fy
            + g[y0 + 1, x0 + 1] * fx * fy)


PAL = {
    "sky": dict(top=(84, 116, 60), top2=(118, 146, 74), rim=(96, 74, 48), soil=(104, 78, 50),
                rock=(116, 106, 96), rock2=(82, 74, 68), deep=(58, 52, 50), vein=None, peb=(120, 110, 100)),
    "chasm": dict(top=(52, 46, 60), top2=(70, 62, 80), rim=(40, 34, 46), soil=(44, 38, 52),
                  rock=(62, 56, 72), rock2=(40, 36, 48), deep=(24, 20, 30), vein=(176, 96, 236), peb=(70, 62, 82)),
}


def _ring_geom(comps):
    big = [c for c in comps if c["big"]]
    cx = np.mean([c["foot"][0] for c in big]); cy = np.mean([c["foot"][1] for c in big])
    rx = max(abs(c["foot"][0] - cx) for c in big); ry = max(abs(c["foot"][1] - cy) for c in big)
    return cx, cy, rx, ry


def _float_scene(gd, kind):
    a, m, comps = _stone_ring(gd, False)
    cx, cy, rx, ry = _ring_geom(comps)
    P = PAL[kind]
    ntop, nrock, nvein = _noise(0x5C1 if kind == "sky" else 0xC4A5), _noise(0x2B0C), _noise(0x7E1)
    IRX, IRY = rx + 4.5, ry + 3.5                 # island top ellipse
    DEPTH = 30                                     # underside depth below the top plane
    stones = []
    for c in comps:
        dx, dy = c["foot"][0] - cx, (c["foot"][1] - cy) * rx / ry
        stones.append(dict(c=c, r=math.hypot(dx, dy), th=math.atan2(dy, dx), ph=(len(stones) * 0.37) % 1.0, yoff=0))
    # v3 (user: "make the smaller pieces more centered vertically with the middles of the larger pieces since theyre
    # floating"): a small piece's centre goes to the mean centre height of the big stones (incl. their undersides)
    bigH = np.mean([c["yb"] - c["top"] + 1 for c in comps if c["big"]])
    for st in stones:
        c = st["c"]
        if not c["big"]:
            h = c["yb"] - c["top"] + 1
            st["yoff"] = -int(round(bigH * (0.5 - 0.18) - h / 2.0))
    glows = []
    for gx, gy in GLOW_STONES:                    # attach every vanilla glow to its stone
        best = min((s for s in stones if s["c"]["big"]),
                   key=lambda s: (s["c"]["foot"][0] - gx) ** 2 + (s["c"]["foot"][1] - gy) ** 2)
        glows.append((best, gx - best["c"]["foot"][0], gy - best["c"]["foot"][1]))
    return dict(a=a, comps=comps, cx=cx, cy=cy, rx=rx, ry=ry, P=P, ntop=ntop, nrock=nrock, nvein=nvein,
                IRX=IRX, IRY=IRY, DEPTH=DEPTH, stones=stones, glows=glows, kind=kind)


def _bob(k, s=None):
    """global float (2 per revolution) + a small per-stone drift (4 per revolution, own phase) -> seamless loop"""
    b = 1.6 * math.sin(4 * math.pi * k / FLOAT_N)
    if s is not None:
        b += 0.6 * math.sin(2 * math.pi * (2 * k / FLOAT_N + s["ph"]))     # v4: gentler, less 1-px flicker
    return b


def _pos(S, s, rot, k):
    """screen foot position (float canvas coords) of stone record s at rotation rot / frame k"""
    th = s["th"] + rot
    x = S["cx"] + math.cos(th) * s["r"]
    y = S["cy"] + math.sin(th) * s["r"] * S["ry"] / S["rx"]
    return x + OX, y + OY - LIFT + _bob(k, s)


def _shifts(S):
    """v5 (user: "floating teleporters are jittery"): every stone's integer shift per frame with HYSTERESIS - a stone
    only moves once its float position is 0.7 px past the pixel it sits on, so bob + drift hovering around a rounding
    boundary no longer flicks it back and forth.  Two passes round the cycle -> seamless loop."""
    out = {}
    for s in S["stones"]:
        fx0, fy0 = s["c"]["foot"]
        # ring position only (no bob); the shared bob is added below as ONE integer offset for all stones, so the
        # whole ring rises / sinks together on the same frame instead of each stone stepping on its own
        f = [(lambda p, k: (p[0] - fx0, p[1] - fy0 - _bob(k, s)))(_pos(S, s, 2 * math.pi * k / FLOAT_N, k), k)
             for k in range(FLOAT_N)]
        qx, qy = round(f[-1][0]), round(f[-1][1])
        for _ in range(2):
            res = []
            for fx, fy in f:
                if abs(fx - qx) > 0.7:
                    qx = round(fx)
                if abs(fy - qy) > 0.7:
                    qy = round(fy)
                res.append((int(qx), int(qy) + int(round(_bob(len(res))))))
        out[id(s)] = res
    return out


def _ring_y(S, s, rot):
    return S["cy"] + math.sin(s["th"] + rot) * s["r"] * S["ry"] / S["rx"]


def _extend(c):
    """v2 (user: "extend the pillar bottoms, they should not look cut off ... natural like the tops"): the ground-
    shadow pixels at the foot are trimmed to the stone's body width, then a rounded, slightly pointed underside grows
    below, following the stone's lean, textured from the rows above (mirrored) and shaded darker towards the point."""
    ys, xs, px = c["ys"], c["xs"], c["px"].astype(float)
    top, yb = int(ys.min()), int(ys.max())
    H = yb - top + 1
    if not c["big"] or H < 6:
        return ys, xs, px
    rows = {y: (xs[ys == y].min(), xs[ys == y].max()) for y in range(top, yb + 1) if (ys == y).any()}
    body = [y for y in rows if top + 0.3 * H <= y <= yb - 3]
    W = float(np.median([rows[y][1] - rows[y][0] + 1 for y in body]))
    yy = np.array(body); cc = np.array([(rows[y][0] + rows[y][1]) / 2 for y in body])
    k, b0 = np.polyfit(yy, cc, 1) if len(yy) > 2 else (0.0, cc.mean())
    cline = lambda y: k * y + b0
    keep = [i for i, (y, x) in enumerate(zip(ys, xs)) if y < yb - 2 or abs(x - cline(y)) <= W / 2 + 0.01]
    ys, xs, px = ys[keep], xs[keep], px[keep]
    look = {(y, x): p for y, x, p in zip(ys, xs, px)}
    rows = {y: (xs[ys == y].min(), xs[ys == y].max()) for y in range(top, yb + 1) if (ys == y).any()}
    E = max(3, int(round(H * 0.36)))
    nys, nxs, npx = list(ys), list(xs), list(px)
    for d in range(1, E + 1):
        y = yb + d
        w = max(1.0, W * (1 - (d / (E + 0.6)) ** 2) ** 0.7)
        cx = cline(y)
        x0, x1 = int(round(cx - (w - 1) / 2)), int(round(cx + (w - 1) / 2))
        src_y = max(top, yb - 2 - E + d)                         # v3: continue the texture (shifted), not mirrored
        while src_y not in rows:
            src_y -= 1
        sx0, sx1 = rows[src_y]
        shade = 0.82 - 0.38 * d / E
        for x in range(x0, x1 + 1):
            u = (x - x0) / max(1, x1 - x0)
            p = look.get((src_y, int(round(sx0 + u * (sx1 - sx0)))))
            if p is None:
                continue
            q = p.copy(); q[:3] = q[:3] * shade
            nys.append(y); nxs.append(x); npx.append(q)
    for y in range(yb - 2, yb + 1):                              # fill gaps the trim left inside the body
        cx = cline(y); x0, x1 = int(round(cx - (W - 1) / 2)), int(round(cx + (W - 1) / 2))
        src_y = yb - 3
        while src_y not in rows:
            src_y -= 1
        sx0, sx1 = rows[src_y]
        for x in range(x0, x1 + 1):
            if (y, x) in look:
                continue
            u = (x - x0) / max(1, x1 - x0)
            p = look.get((src_y, int(round(sx0 + u * (sx1 - sx0)))))
            if p is not None:
                q = p.copy(); q[:3] = q[:3] * 0.85
                nys.append(y); nxs.append(x); npx.append(q)
    return np.array(nys), np.array(nxs), np.array(npx)


def float_frames(gd, kind="sky"):
    """v2 (user: "get rid of the island below them"): just the ring of stones floating, every stone with a natural
    tapered underside, the ring turning once per cycle, the stones bobbing (shared float + own small drift)"""
    S = _float_scene(gd, kind)
    for st in S["stones"]:
        st["ext"] = _extend(st["c"])
    sh = _shifts(S)
    frames = []
    for k in range(FLOAT_N):
        rot = 2 * math.pi * k / FLOAT_N
        out = np.zeros((FH, FW, 4), np.uint8)
        order = sorted(S["stones"], key=lambda s: _ring_y(S, s, rot))     # back to front, no bob -> no popping
        for s in order:
            ox, oy = sh[id(s)][k]
            oy += s["yoff"]
            ys, xs, px = s["ext"]
            px = px.copy()
            if S["kind"] == "chasm":
                px[:, :3] *= np.array((0.78, 0.74, 0.92))
            for y, x, p in zip(ys, xs, px):
                if 0 <= y + oy < FH and 0 <= x + ox < FW:
                    out[y + oy, x + ox, :3] = np.clip(p[:3], 0, 255); out[y + oy, x + ox, 3] = 255
        frames.append(out)
    return frames


def _glow_sprite(gd, kind):
    lib, by = V1._load(gd, "STR_TELE.ILB")
    g = V1._rgba(lib, by[6].primary).astype(float)
    L = g[..., :3].sum(-1)
    py, px = np.unravel_index(L.argmax(), L.shape)
    if kind == "chasm":                                        # teal -> violet
        r, gg, b = g[..., 0].copy(), g[..., 1].copy(), g[..., 2].copy()
        g[..., 0], g[..., 1], g[..., 2] = gg * 0.95, r * 0.6 + gg * 0.25, np.maximum(b, gg) * 1.05
    return g, px, py


GLOW_PERIOD = 18                                                 # FLOAT_N / GLOW_PERIOD must be an integer


def float_glow(gd, kind="sky"):
    S = _float_scene(gd, kind)
    g, gpx, gpy = _glow_sprite(gd, kind)
    gh, gw = g.shape[:2]
    phases = (0.0, 0.31, 0.62, 0.17, 0.83)
    sh = _shifts(S)
    stones = [f[..., 3] > 0 for f in float_frames(gd, kind)]
    frames = []
    for k in range(FLOAT_N):
        rot = 2 * math.pi * k / FLOAT_N
        acc = np.zeros((FH, FW, 3), float)
        for (s, dx, dy), ph in zip(S["glows"], phases):
            inten = 0.11 + 0.89 * (0.5 + 0.5 * math.cos(2 * math.pi * (k / GLOW_PERIOD + ph)))  # 5..45 of 45
            ox, oy = sh[id(s)][k]                                                                # = the stone's shift
            x0 = ox + int(round(s["c"]["foot"][0] + dx)) - gpx
            y0 = oy + int(round(s["c"]["foot"][1] + dy)) - gpy
            ys0, xs0 = max(0, -y0), max(0, -x0)
            ys1, xs1 = min(gh, FH - y0), min(gw, FW - x0)
            acc[y0 + ys0:y0 + ys1, x0 + xs0:x0 + xs1] += g[ys0:ys1, xs0:xs1, :3] * inten
        out = np.zeros((FH, FW, 4), np.uint8)
        out[..., :3] = np.clip(acc, 0, 255)
        # v5: only pixels the additive layer visibly brightens.  The near-invisible fringe still changed the sky
        # pixels, so the cloud overlay (which only animates pixels equal to the tile) left a bare patch under the ring.
        # v6: a pixel the additive glow touches is no longer a tile pixel, so the cloud overlay skips it (bare tile
        # = darker dots on Clear Sky).  Keep glow only ON the stones (no sky there anyway) or where clearly bright.
        on = stones[k]
        near = on | np.roll(on, 1, 0) | np.roll(on, -1, 0) | np.roll(on, 1, 1) | np.roll(on, -1, 1)
        out[..., 3] = np.where((near & (acc.max(-1) >= 10)) | (acc.max(-1) >= 70), 255, 0)
        out[out[..., 3] == 0, :3] = 0
        frames.append(out)
    return frames


# ---------------------------------------------------------------------------------------------------------- portraits
def _portrait_src(gd, src_id):
    lib, by = V1._load(gd, "BORDER.ILB")
    return V1._rgba(lib, by[src_id].primary).astype(float)


# v3 portraits (user: "for side images, the water/ice/lava is too flat and abrupt. sky is okay but looks like a mirror
# effect instead of full pillar, polish it ... chasm get rid of cave background, all purple chasm").
# The three stones of B_Telep (41) / BU_Telep (131, same layout) are masked by hand-checked extents; the ground behind
# and between them is replaced by a surface in perspective from a horizon at HZ (ripples / cracks / crust grow towards
# the viewer), every stone stands IN it (reflection, frozen / heat-lit foot, contact rim) instead of on a flat strip.
P_STONES = (dict(xr=(0, 22), yext=228, yb=252, bot=(2, 20), padr=1),     # left (back)
            dict(xr=(22, 53), yext=212, yb=263, bot=(25, 50), padr=0),   # big middle
            dict(xr=(53, 57), yext=233, yb=277, bot=(47, 56), padr=0))   # right edge (front)
HZ = 234


def _pstones(gd):
    a = _portrait_src(gd, 41)
    m = (a[..., 2] - a[..., 0]) < 20
    out = []
    for st in P_STONES:
        x0, x1 = st["xr"]
        ext = {}
        for y in range(150, st["yext"] + 1):
            xs = np.nonzero(m[y, x0:x1])[0]
            if len(xs) >= 2:
                ext[y] = [x0 + int(xs.min()), x0 + int(xs.max()) + st["padr"]]
        l0, r0 = ext[st["yext"]]
        bl, br = st["bot"]
        for y in range(st["yext"] + 1, st["yb"] + 1):
            t = (y - st["yext"]) / (st["yb"] - st["yext"])
            ext[y] = [int(round(l0 + (bl - l0) * t)), int(round(r0 + (br - r0) * t))]
        mm = np.zeros(m.shape, bool)
        for y, (l, r) in ext.items():
            mm[y, max(0, l):min(56, r) + 1] = True
        out.append(dict(m=mm, yb=st["yb"], ext=ext, top=min(ext)))
    return out


def _inpaint(a, mask):
    """row-wise linear fill of the masked pixels from their unmasked neighbours (smooth skies)"""
    out = a.copy()
    h, w = mask.shape
    for y in range(h):
        free = np.nonzero(~mask[y])[0]
        if len(free) == 0:
            out[y] = out[y - 1]
            continue
        if mask[y].any():
            for c in range(3):
                out[y, mask[y], c] = np.interp(np.nonzero(mask[y])[0], free, a[y, free, c])
    return out


def _wnoise(g, X, Y):
    """bilinear, wrapping"""
    n = g.shape[0]
    x0, y0 = math.floor(X), math.floor(Y)
    fx, fy = X - x0, Y - y0
    x0 %= n; y0 %= n; x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    return (g[y0, x0] * (1 - fx) * (1 - fy) + g[y0, x1] * fx * (1 - fy) + g[y1, x0] * (1 - fx) * fy
            + g[y1, x1] * fx * fy)


def _smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


_WPTS = {}


def _worley(X, Y, seed, n=16):
    """cellular noise on a wrapping n x n grid -> (F1, F2, cell id)"""
    if seed not in _WPTS:
        _WPTS[seed] = np.random.default_rng(seed).random((n, n, 2))
    P = _WPTS[seed]
    cx, cy = math.floor(X), math.floor(Y)
    best = [(9.0, 0), (9.0, 0)]
    for j in (-1, 0, 1):
        for i in (-1, 0, 1):
            gx, gy = cx + i, cy + j
            px, py = P[gy % n, gx % n]
            d = math.hypot(gx + px - X, gy + py - Y)
            if d < best[0][0]:
                best = [(d, (gy % n) * n + gx % n), best[0]]
            elif d < best[1][0]:
                best[1] = (d, 0)
    return best[0][0], best[1][0], best[0][1]


def _lum(c):
    return float(np.dot(c, (0.299, 0.587, 0.114)))


def _ground(gd, src_id, kind, under):
    """v4 (user: "side images for water/ice/lava got worse, improve them"): keep the painting's own ground - its
    perspective, stone shadows, pebbles and the stones' real bases - and RE-COLOUR it by brightness into water / ice /
    lava, with a soft graded horizon (the far hills tinted to match) instead of a pasted strip.
      water: deep -> light teal ramp, horizontal ripple glints that widen towards the viewer, rippled stone reflections
      ice:   smoothed (blurred) brightness on a white-blue ramp, faint blurred reflections, frost on the stone feet
      lava:  dark crust ramp; the painting's dark spots / shadow seams become glowing lava, warm haze at the horizon"""
    a = _portrait_src(gd, src_id)
    h, w = a.shape[:2]
    S = _pstones(gd)
    allm = S[0]["m"] | S[1]["m"] | S[2]["m"]
    G0, G1 = 226, 236                                           # far hills band -> ground fully re-coloured below G1
    out = a.copy()
    lumf = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    gnd = np.zeros((h, w), bool)
    gnd[G0:] = True
    gnd &= ~allm
    lo, hi = np.percentile(lumf[gnd], 4), np.percentile(lumf[gnd], 96)
    l = np.clip((lumf - lo) / max(1.0, hi - lo), 0, 1)
    if kind == "ice":                                           # smooth the grass texture into ice
        l = 0.55 * _blur2(l, 1.6) + 0.45 * l
    rng = np.random.default_rng(0x5EA + len(kind))
    if kind == "water":
        dark, light = ((np.array((16, 46, 66)), np.array((116, 168, 186))) if not under
                       else (np.array((10, 32, 36)), np.array((74, 120, 118))))
    elif kind == "ice":
        dark, light = ((np.array((132, 168, 196)), np.array((238, 247, 252))) if not under
                       else (np.array((76, 102, 118)), np.array((170, 194, 206))))
    else:
        dark, light = np.array((34, 20, 16)), np.array((112, 66, 46))
    if kind == "lava":                                          # warm smoky sky, stones lit orange from below
        for y in range(G0):
            f = (y / G0) ** 2.2
            sky = ~allm[y]
            out[y, sky, :3] = out[y, sky, :3] * np.array((1.0, 0.86, 0.74)) * (1 - 0.35 * f) + np.array((150, 52, 18)) * 0.35 * f
        for st in S:
            for y in range(st["top"], st["yb"] + 1):
                xs = np.nonzero(st["m"][y])[0]
                p = out[y, xs, :3] * np.array((0.86, 0.76, 0.70))
                f = (max(0.0, (y - 196) / (st["yb"] - 196))) ** 2 * 0.55
                lv = p @ np.array([0.299, 0.587, 0.114])
                out[y, xs, :3] = p * (1 - f) + np.outer(lv / 110.0, (240, 110, 30)) * f
    elif kind == "ice":
        out[:G0, :, :3] = np.clip(out[:G0, :, :3] * np.array((0.95, 0.99, 1.05)), 0, 255)
    for y in range(G0, h):
        g = min(1.0, (y - G0) / float(G1 - G0))                 # 0 at the far hills -> 1 on the ground
        t = max(0.0, (y - G1) / float(h - G1))                  # depth: 0 far .. 1 near
        for x in range(w):
            if allm[y, x]:
                continue
            lv = float(l[y, x])
            if kind == "water":
                c = dark + (light - dark) * lv ** 1.15
                ph = max(0, y - G1) ** 0.62 * 3.1 + 0.9 * math.sin(x * (0.55 - 0.35 * t) + y)
                rip = math.sin(ph)
                if y >= G1 and rip > 0.78:                       # glints: thin far, broader near
                    c = c + (np.array((214, 236, 242)) - c) * (0.22 + 0.2 * t) * (rip - 0.78) / 0.22
                xs = int(round(min(w - 1, max(0, x + (0.4 + 1.8 * t) * math.sin(ph * 1.7)))))
                for st in reversed(S):                           # rippled reflections of the stones
                    sy = 2 * st["yb"] - y
                    if y > st["yb"] and sy >= st["top"] and st["m"][sy, xs]:
                        k = 0.34 * max(0.0, 1 - (y - st["yb"]) / 34.0)
                        c = c * (1 - k) + a[sy, xs, :3] * 0.7 * k
                        break
            elif kind == "ice":
                c = dark + (light - dark) * lv ** 0.9
                for st in reversed(S):
                    sy = 2 * st["yb"] - y
                    if y > st["yb"] and sy >= st["top"] and st["m"][sy, x]:
                        k = 0.14 * max(0.0, 1 - (y - st["yb"]) / 22.0)
                        c = c * (1 - k) + a[sy, x, :3] * 0.8 * k
                        break
            else:
                c = dark + (light - dark) * lv
                glow = float(_smooth(0.30, 0.06, lv))          # the painting's dark seams glow
                if glow > 0:
                    hot = np.array((236, 92, 22)) + (np.array((255, 196, 76)) - np.array((236, 92, 22))) * glow ** 2
                    c = c + (hot - c) * glow
                c = c + (np.array((170, 70, 30)) - c) * 0.45 * math.exp(-(y - G1 + 2) / 6.0) if y >= G1 - 2 else c
                if under:
                    c = c * 0.92
            orig = out[y, x, :3]
            if kind == "lava" and g < 1:
                orig = orig * np.array((0.9, 0.62, 0.5)) + np.array((40, 8, 0))
            elif kind == "ice" and g < 1:
                orig = orig + (np.array((214, 230, 240)) - orig) * 0.35
            elif kind == "water" and g < 1:
                orig = orig * 0.9 + np.array((0, 8, 14))
            gg = g * g * (3 - 2 * g)
            out[y, x, :3] = orig * (1 - gg) + c * gg
    # stone feet: wet / frosted / heat-lit, following each stone's own lowest rows
    for i, st in enumerate(S):
        front = S[i + 1:]
        hcol = 2.5 + 4.0 * rng.random(w)
        for y in range(st["yb"] - 7, st["yb"] + 1):
            for x in range(w):
                if not st["m"][y, x] or any(o["m"][y, x] for o in front):
                    continue
                p = out[y, x, :3]
                up = st["yb"] - y
                if kind == "water":
                    out[y, x, :3] = p * (1 - 0.25 * max(0.0, 1 - up / 4.0) ** 2) + np.array((0, 6, 10)) * max(0.0, 1 - up / 4.0)
                elif kind == "ice":
                    f = 0.40 * max(0.0, 1 - up / hcol[x]) ** 1.3
                    out[y, x, :3] = p + (np.array((226, 240, 250)) - p) * f
                else:
                    f = 0.35 * max(0.0, 1 - up / 5.0) ** 1.5
                    out[y, x, :3] = p + (np.array((255, 140, 40)) - p) * f
    out[..., 3] = 255
    return np.clip(out, 0, 255).astype(np.uint8)


def _blur2(a, s):
    r = int(math.ceil(s * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, p)
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, p)
    return p[r:-r, r:-r]


def portrait_water(gd, under=False):
    return _ground(gd, 131 if under else 41, "water", under)


def portrait_ice(gd, src_id, under=False):
    return _ground(gd, src_id, "ice", under)


def portrait_lava(gd, src_id, under=False):
    return _ground(gd, src_id, "lava", under)


def portrait_float(gd, kind="sky"):
    """v3: full floating pillars.  The three stones are cut out (ground rows trimmed), the background is the sky with
    the stones and the hills removed and continued down into misty depth (chasm: the same streaky sky re-coloured to an
    all-purple void), and every stone is lifted and grows a long tapered underside that CONTINUES its texture (a
    shifted copy of the rows above, narrowed and darkened towards the point; lit left side kept) - no mirror line."""
    a41 = _portrait_src(gd, 41)
    src = a41 if kind == "sky" else _portrait_src(gd, 131)
    h, w = a41.shape[:2]
    S = _pstones(gd)
    allm = S[0]["m"] | S[1]["m"] | S[2]["m"]
    bg = _inpaint(a41, allm)
    CUT = 220                                                   # sky rows below this (hills / grass) are replaced
    nz = _noise(0xC10D, 48)
    out = np.zeros_like(a41)
    for y in range(h):
        for x in range(w):
            if y < CUT:
                c = bg[y, x, :3]
            else:
                t = (y - CUT) / (h - 1 - CUT)
                c = bg[CUT - 1, x, :3] * (1 - t) + np.array((214, 232, 240)) * t
                wisp = _wnoise(nz, x * 0.18 + 3, y * 0.07)
                c = c + (np.array((236, 244, 248)) - c) * 0.35 * t * _smooth(0.5, 0.75, wisp)
            out[y, x, :3] = c
    if kind == "chasm":                                         # all-purple void: re-colour by luminance
        L = (out[..., :3] @ np.array([0.299, 0.587, 0.114])) / 255.0
        yy = (np.arange(h) / h)[:, None]
        dark, mid, hi = np.array((14, 8, 26)), np.array((70, 34, 110)), np.array((172, 120, 226))
        k = np.clip((L - 0.25) / 0.6, 0, 1)[..., None]
        col = dark + (mid - dark) * np.clip(L * 1.6, 0, 1)[..., None] + (hi - mid) * k ** 1.6
        depth = np.clip((yy - 0.55) / 0.45, 0, 1)[..., None]                  # down into the abyss: darker
        col = col * (1 - 0.55 * depth) + np.array((40, 14, 64)) * 0.55 * depth
        out[..., :3] = col
    LIFT = (30, 24, 16)
    for i, (st, lift) in enumerate(zip(S, LIFT)):
        yc = st["yb"] - 10 if i < 2 else st["yb"] - 6           # the taper starts above the grass-touching rows
        rows = {y: st["ext"][y] for y in st["ext"] if y <= yc}
        l_b, r_b = rows[yc]
        W = r_b - l_b + 1
        E = int(round(min(40, max(10, W * 0.62)))) if i < 2 else 14
        orig = {}
        for y, (l, r) in st["ext"].items():
            if y > (st["yb"] - 3 if i < 2 else st["yb"]):
                continue
            for x in range(max(0, l), min(w - 1, r) + 1):
                if st["m"][y, x]:
                    c = src[y, x, :3].astype(float)
                    if kind == "chasm":
                        c = c * np.array((0.80, 0.72, 0.98)) + np.array((6, 0, 14))
                    orig[(y, x)] = c
        px = {k: v for k, v in orig.items() if k[0] <= yc}
        cx = (l_b + r_b) / 2.0
        for d in range(1, E + 1):
            y = yc + d
            ww = W * max(0.0, 1 - (d / (E + 0.7)) ** 1.7) ** 0.85
            if ww < 0.8:
                break
            lx, rx = cx - (ww - 1) / 2, cx + (ww - 1) / 2
            sy = yc - E + d - 1
            while sy not in rows:
                sy += 1
            sl, sr = rows[sy]
            for x in range(int(math.floor(lx)), int(math.ceil(rx)) + 1):
                if not 0 <= x < w:
                    continue
                u = (x - lx) / max(1.0, rx - lx)
                sx = int(round(sl + min(1.0, max(0.0, u)) * (sr - sl)))
                c = px.get((sy, sx))
                if c is None:
                    continue
                shade = (1.0 - 0.50 * (d / E) ** 1.3) * (1 - 0.22 * u ** 2 * min(1.0, d / 4.0))
                c = c * shade
                o = orig.get((y, x))                            # first rows: crossfade from the real stone
                if o is not None and d <= 4:
                    c = o * (1 - d / 5.0) + c * (d / 5.0)
                px[(y, x)] = c
        for (y, x), c in px.items():
            yy = y - lift
            if 0 <= yy < h:
                out[yy, x, :3] = c
    out[..., 3] = 255
    return np.clip(out, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------------------------------------------------ preview
def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ice = {u: (ice_base(gd, u), ice_glints(gd, u)) for u in (False, True)}
    lava = {u: (lava_base(gd, u), lava_anim(gd, u)) for u in (False, True)}
    fl = {k: (float_frames(gd, k), float_glow(gd, k)) for k in ("sky", "chasm")}
    BG = {"ice": (182, 214, 232), "lava": (150, 50, 20), "sky": (120, 170, 200), "chasm": (28, 18, 40)}

    def glow_add(img, gl):
        arr = np.array(img).astype(float)
        g = gl.astype(float)[..., :3] * 45 / 100.0
        return Image.fromarray(np.clip(arr + np.dstack([g, np.zeros(g.shape[:2])]), 0, 255).astype(np.uint8), "RGBA")

    ims = []
    n = FLOAT_N * FLOAT_HOLD
    for t in range(0, n, 2):
        s = Image.new("RGBA", (4 * 84, 2 * 128), (0, 0, 0, 255))
        for col, (name, u) in enumerate((("ice", False), ("ice", True), ("lava", False), ("lava", True))):
            tile = Image.new("RGBA", (84, 128), BG[name] + (255,))
            b, an = (ice if name == "ice" else lava)[u]
            nn = ICE_N if name == "ice" else LAVA_N
            tile.alpha_composite(Image.fromarray(b, "RGBA"), (12, 40))
            tile.alpha_composite(Image.fromarray(an[(t // HOLD) % nn], "RGBA"), (12, 40))
            s.paste(tile, (col * 84, 0))
        for col, kind in enumerate(("sky", "chasm")):
            tile = Image.new("RGBA", (84, 128), BG[kind] + (255,))
            fr, gl = fl[kind]
            tile.alpha_composite(Image.fromarray(fr[(t // FLOAT_HOLD) % FLOAT_N], "RGBA"), (2, 2))
            tile = glow_add(tile, np.pad(gl[(t // FLOAT_HOLD) % FLOAT_N], ((2, 2), (2, 2), (0, 0)))[:128, :84])
            s.paste(tile, (col * 84, 128))
        ims.append(s.resize((s.width * 3, s.height * 3), Image.NEAREST))
    ims[0].save(os.path.join(out_dir, "tele_variants.gif"), save_all=True, append_images=ims[1:], duration=180, loop=0)
    for i in (0, 30, 60):
        ims[i].save(os.path.join(out_dir, "tele_variants_%d.png" % i))
    c = Image.new("RGBA", (8 * 60, 278), (0, 0, 0, 255))
    for i, a in enumerate((portrait_water(gd), portrait_water(gd, True), portrait_ice(gd, 41),
                           portrait_ice(gd, 131, True), portrait_lava(gd, 41),
                           portrait_lava(gd, 131, True), portrait_float(gd, "sky"), portrait_float(gd, "chasm"))):
        c.alpha_composite(Image.fromarray(a, "RGBA"), (i * 60, 0))
    c.resize((c.width * 2, c.height * 2), Image.NEAREST).save(os.path.join(out_dir, "tele_variants_side.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
