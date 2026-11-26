#!/usr/bin/env python3
r"""
Procedural art for the poison-cloud variants (v10, 2026-10-30; 48 frames; seamless loop: every layer moves whole 256-px tiles per loop) [v11 frame-reuse reverted 10/31 at user request].  Used by build_cloud_variants_hss_v1.py --art.

Every frame (10, looping, 320x480, same anchor as PoisnCld.ILB) is a 2-layer COMPOSITE image, drawn in order:
  part 0  multiply  (drawMode 1026, blendValue 100)  tints/darkens the ground   result = ground * M
  part 1  additive  (drawMode  770, blendValue 100)  adds colour/light           result += A
so  ground*M + A  can paint any colour with soft edges (retail precedent: SpellIcn.ILB 770+1026, Magic.ILB
258+770, Combat.ILB 1026+258).  Footprint = soft noisy ellipse on the vanilla cloud's area (centre 157,254,
~206x156 px = the radius-2 hex area).  All motion loops seamlessly over the 10 frames:
  sand / snow  wind DIAGONAL down-right (~28 deg): turbulent body (fbm) scrolling along the wind, motion-blurred
               streaks, fast grains / flakes with short trails (whole wraps per loop).
  holy         warm gold glow, soft light shafts, slow rising motes (fade in/out along a short path) and twinkling
               4-point star glints; bright core.
  death        purple-black body swirling in place (cyclic cross-fade of noise fields + small rotation
               oscillation), glowing violet rim, slow rising violet embers.
render(variant) -> list of (mul_rgba, add_rgba) PIL pairs;  preview(pairs, ground_rgb) -> list of RGB images;
to_ilb(lib, ilb, pairs) turns a PoisnCld-layout library into the composites.
"""
import copy
import math
import numpy as np
from PIL import Image

W, H, N = 320, 480, 48
CX, CY, RX, RY = 157.0, 254.0, 118.0, 86.0
WIND = math.radians(28)                    # down-right
YY, XX = np.mgrid[0:H, 0:W].astype(float)


# ---------------------------------------------------------------- noise ----
def tile_noise(h, w, cy, cx, rng):
    """periodic value noise (period h x w), cubic-smoothstep interpolated, values 0..1"""
    lat = rng.random((cy, cx))
    y = np.arange(h) * cy / h
    x = np.arange(w) * cx / w
    y0 = np.floor(y).astype(int); x0 = np.floor(x).astype(int)
    fy = y - y0; fx = x - x0
    fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
    y1 = (y0 + 1) % cy; x1 = (x0 + 1) % cx
    a = lat[y0][:, x0]; b = lat[y0][:, x1]; c = lat[y1][:, x0]; d = lat[y1][:, x1]
    top = a + (b - a) * fx[None, :]; bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(h, w, rng, base=4, octaves=5, gain=0.55):
    tot = np.zeros((h, w)); amp = 1.0; norm = 0.0; f = base
    for _ in range(octaves):
        tot += amp * tile_noise(h, w, f, f, rng); norm += amp; amp *= gain; f *= 2
    return tot / norm


def sample_wrapped(field, u, v):
    """bilinear sample of a periodic field (Hf x Wf) at float coords (u = column, v = row)"""
    hf, wf = field.shape
    u0 = np.floor(u).astype(int); v0 = np.floor(v).astype(int)
    fu = u - u0; fv = v - v0
    u0 %= wf; v0 %= hf; u1 = (u0 + 1) % wf; v1 = (v0 + 1) % hf
    a = field[v0, u0]; b = field[v0, u1]; c = field[v1, u0]; d = field[v1, u1]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def blur_axis1_periodic(arr, k):
    out = np.zeros_like(arr)
    for i in range(-(k // 2), k // 2 + 1):
        out += np.roll(arr, i, axis=1)
    return out / (2 * (k // 2) + 1)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def envelope(edge_noise, grow=1.0, soft=0.45, rough=0.35):
    r = np.sqrt(((XX - CX) / (RX * grow)) ** 2 + ((YY - CY) / (RY * grow)) ** 2)
    r = r + (edge_noise - 0.5) * rough
    return 1 - smooth(1 - soft, 1.0, r)


# ---------------------------------------------------------- particles ----
def stamp(img, x, y, rgb, rad, strength=1.0):
    """additive soft gaussian dot"""
    r = int(math.ceil(rad * 2.2))
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(0, xi - r), min(W, xi + r + 1)
    y0, y1 = max(0, yi - r), min(H, yi + r + 1)
    if x0 >= x1 or y0 >= y1:
        return
    gy, gx = np.mgrid[y0:y1, x0:x1]
    d2 = ((gx - x) ** 2 + (gy - y) ** 2) / (rad * rad)
    k = np.exp(-d2 * 1.6) * strength
    img[y0:y1, x0:x1, :] += k[..., None] * np.asarray(rgb, float)[None, None, :]


def streak(img, x, y, dx, dy, length, rgb, rad, strength=1.0):
    steps = max(2, int(length / max(0.6, rad * 0.8)))
    for i in range(steps):
        t = i / (steps - 1)
        stamp(img, x - dx * length * t, y - dy * length * t, rgb, rad * (1 - 0.35 * t), strength * (1 - t) ** 1.3)


def star(img, x, y, rgb, size, strength):
    stamp(img, x, y, rgb, size * 0.55, strength)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        streak(img, x + dx * size * 2.2, y + dy * size * 2.2, dx, dy, size * 2.2, rgb, size * 0.28, strength * 0.7)
    for dx, dy in ((0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
        streak(img, x + dx * size * 1.1, y + dy * size * 1.1, dx, dy, size * 1.1, rgb, size * 0.2, strength * 0.35)


def _pack(mul, add, thr_m=0.008, thr_a=1.5):
    mul = np.clip(mul, 0, 1)
    add = np.clip(add, 0, 255)
    m_mask = (1 - mul).max(axis=2) > thr_m
    a_mask = add.max(axis=2) > thr_a
    mi = np.dstack([(mul * 255).astype(np.uint8), (m_mask * 255).astype(np.uint8)])
    ai = np.dstack([add.astype(np.uint8), (a_mask * 255).astype(np.uint8)])
    return Image.fromarray(mi, "RGBA"), Image.fromarray(ai, "RGBA")


# --------------------------------------------------------------- render ----
def comp(alpha, col, glow=None):
    """true alpha compositing via the two layers: ground*(1-a) + a*col (+ optional extra additive light)"""
    a = np.clip(alpha, 0, 0.97)[..., None]
    mul = np.repeat(1 - a, 3, axis=2)
    add = a * (col if col.ndim == 3 else col[None, None, :])
    if glow is not None:
        add = add + glow
    return mul, add


def dot(acc_a, acc_c, x, y, rad, col, op):
    """soft opaque particle: accumulate alpha and colour (over-compositing)"""
    r = int(math.ceil(rad * 2.2))
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(0, xi - r), min(W, xi + r + 1)
    y0, y1 = max(0, yi - r), min(H, yi + r + 1)
    if x0 >= x1 or y0 >= y1:
        return
    gy, gx = np.mgrid[y0:y1, x0:x1]
    k = np.exp(-(((gx - x) ** 2 + (gy - y) ** 2) / (rad * rad)) * 1.6) * op
    old = acc_a[y0:y1, x0:x1]
    acc_c[y0:y1, x0:x1, :] = acc_c[y0:y1, x0:x1, :] * (1 - k[..., None]) + k[..., None] * np.asarray(col, float)
    acc_a[y0:y1, x0:x1] = old + k * (1 - old)


def adot(acc_a, x, y, rad, op):
    """soft alpha-only particle (over-accumulated)"""
    r = int(math.ceil(rad * 2.2))
    xi, yi = int(round(x)), int(round(y))
    x0, x1 = max(0, xi - r), min(W, xi + r + 1)
    y0, y1 = max(0, yi - r), min(H, yi + r + 1)
    if x0 >= x1 or y0 >= y1:
        return
    gy, gx = np.mgrid[y0:y1, x0:x1]
    k = np.exp(-(((gx - x) ** 2 + (gy - y) ** 2) / (rad * rad)) * 1.6) * op
    acc_a[y0:y1, x0:x1] = acc_a[y0:y1, x0:x1] + k * (1 - acc_a[y0:y1, x0:x1])


TILE = 256


def _warped(rng, base=4, octaves=6, amt=38.0):
    """periodic domain-warped fbm on a TILE x TILE torus -> billowing cloud texture 0..1"""
    f = fbm(TILE, TILE, rng, base=base, octaves=octaves)
    wx = fbm(TILE, TILE, rng, base=3, octaves=4)
    wy = fbm(TILE, TILE, rng, base=3, octaves=4)
    gy, gx = np.mgrid[0:TILE, 0:TILE].astype(float)
    out = sample_wrapped(f, gx + (wx - 0.5) * amt * 2, gy + (wy - 0.5) * amt * 2)
    return (out - out.min()) / (np.ptp(out) + 1e-9)


def _streaks(rng, step, length, base=24):
    """periodic streak texture: noise smeared along the integer direction `step` (dx, dy) with wrap"""
    f = fbm(TILE, TILE, rng, base=base, octaves=2, gain=0.5)
    acc = np.zeros_like(f)
    for i in range(length):
        acc += np.roll(np.roll(f, i * step[1], axis=0), i * step[0], axis=1)
    acc /= length
    return (acc - acc.min()) / (np.ptp(acc) + 1e-9)


def _tile_layer(field, vx, vy, t, scale=1.0):
    """sample a periodic TILE field translated by (vx, vy)*t (whole tiles per loop -> seamless)"""
    return sample_wrapped(field, (XX - vx * t) / scale, (YY - vy * t) / scale)


def render_wind(variant, rng):
    """v8 'real storm': billowing domain-warped dust/snow bodies lit from the upper-left, three depth layers moving
    at different speeds (far / mid / near), airborne streaks (sand) or a blizzard of flakes (snow), wide faint mist.
    Every layer moves a whole number of 256-px tiles per loop -> seamless with no cross-fade smearing."""
    sand = variant == "sand"
    if sand:
        d = np.array([2.0, 1.0])                     # down-right ~27 deg
        vel = {"far": d * 256, "mid": d * 512, "near": d * 768}
        step = (2, 1)
        shadow = np.array([112, 78, 40], float); base_c = np.array([176, 136, 82], float)
        high = np.array([238, 208, 152], float); mote_c = np.array([246, 224, 172], float)
        mist_a, body_a, streak_a = 0.20, 0.28, 0.07
        counts = {"far": 90, "mid": 50, "near": 18}
        sizes = {"far": 0.45, "mid": 0.65, "near": 0.9}
        mop = {"far": 0.06, "mid": 0.09, "near": 0.12}
        blur = 1.1
    else:
        d = np.array([-1.0, 1.0])                    # down-left 45 deg (blizzard)
        vel = {"far": d * 256, "mid": d * 512, "near": d * 768}
        step = (-1, 1)
        shadow = np.array([168, 182, 208], float); base_c = np.array([222, 230, 244], float)
        high = np.array([255, 255, 255], float); mote_c = np.array([255, 255, 255], float)
        mist_a, body_a, streak_a = 0.22, 0.22, 0.04
        counts = {"far": 90, "mid": 45, "near": 16}
        sizes = {"far": 0.8, "mid": 1.3, "near": 2.1}
        mop = {"far": 0.08, "mid": 0.12, "near": 0.16}
        blur = 0.45
    body_fs = [_warped(rng) for _ in range(2)]
    mist_f = _warped(rng, base=2, octaves=4, amt=24.0)
    strk_f = _streaks(rng, step, 34 if sand else 18)
    edge_f = fbm(H, W, rng, base=5, octaves=4)
    parts = {k: (rng.random(counts[k]) * TILE, rng.random(counts[k]) * TILE, rng.random(counts[k]) * 2 * math.pi)
             for k in counts}
    L = np.array([-1.0, -1.0]) / math.sqrt(2)        # light from upper-left
    out = []
    for f in range(N):
        t = f / N
        ox, oy = 10 * math.cos(2 * math.pi * t), 10 * math.sin(2 * math.pi * t)
        edge = sample_wrapped(edge_f, XX + ox, YY + oy)
        env = envelope(edge, grow=1.08, soft=0.75, rough=0.5)
        env_m = envelope(edge, grow=1.4, soft=0.95, rough=0.4)
        w0 = 0.5 + 0.5 * math.cos(2 * math.pi * t)
        vm = d * TILE                                 # body drift: whole tiles per loop
        b0 = _tile_layer(body_fs[0], vm[0], vm[1], t)
        b1 = _tile_layer(body_fs[1], vm[0], vm[1], t)
        body = b0 * w0 + b1 * (1 - w0)
        b0s = sample_wrapped(body_fs[0], XX - vm[0] * t - L[0] * 4, YY - vm[1] * t - L[1] * 4)
        b1s = sample_wrapped(body_fs[1], XX - vm[0] * t - L[0] * 4, YY - vm[1] * t - L[1] * 4)
        light = np.clip((body - (b0s * w0 + b1s * (1 - w0))) * 6 + 0.5, 0, 1)
        vf = d * TILE * 1.6                            # /1.6 in sampling -> exactly d*TILE per loop
        mist = _tile_layer(mist_f, vf[0], vf[1], t, scale=1.6)
        vn = vel["near"]
        strk = smooth(0.55, 0.85, _tile_layer(strk_f, vn[0], vn[1], t))
        a_mist = env_m * (0.35 + 0.65 * smooth(0.15, 0.8, mist)) * mist_a
        a_body = env * smooth(0.22, 0.75, body) * body_a
        a_strk = env * strk * streak_a
        a_cloud = 1 - (1 - a_mist) * (1 - a_body) * (1 - a_strk)
        tone = (0.35 + 0.65 * light)[..., None]
        col = shadow[None, None, :] * (1 - tone) + base_c[None, None, :] * tone
        col = col + (high - base_c)[None, None, :] * (np.clip(light - 0.65, 0, 1) * 2.5 + strk * 0.6)[..., None]
        pa = np.zeros((H, W))
        x0, x1 = CX - RX * 1.4, CX + RX * 1.4
        y0, y1 = CY - RY * 1.4, CY + RY * 1.4
        for k in ("far", "mid", "near"):
            pu, pv, ph = parts[k]
            v = vel[k]
            sp = math.hypot(*v) / N                                   # px per frame
            dx, dy = v / (np.linalg.norm(v) + 1e-9)
            Ltrail = sp * blur
            for u, w, p in zip(pu, pv, ph):
                bx = (u + v[0] * t) % TILE
                by = (w + v[1] * t) % TILE
                for tx in range(-TILE, W + TILE, TILE):
                    for ty in range(-TILE, H + TILE, TILE):
                        x = bx + tx; y = by + ty
                        if not (x0 < x < x1 and y0 < y < y1):
                            continue
                        if not sand:
                            x += 1.5 * math.sin(p + 2 * math.pi * t * 3)          # flutter
                        n_st = max(2, int(Ltrail / max(0.8, sizes[k])) + 1)
                        for i in range(n_st):
                            q = i / (n_st - 1)
                            adot(pa, x - dx * Ltrail * q, y - dy * Ltrail * q, sizes[k] * (1.25 - 0.4 * q),
                                 mop[k] * (1 - q) ** 1.5)
        pa = pa * np.clip(env_m * 1.5, 0, 1)
        a_tot = a_cloud + pa * (1 - a_cloud)
        col_tot = (col * (a_cloud * (1 - pa))[..., None] + mote_c[None, None, :] * pa[..., None]) / np.maximum(a_tot, 1e-6)[..., None]
        mul, add = comp(np.clip(a_tot, 0, 0.5), col_tot)
        out.append(_pack(mul, add))
    return out


def render_holy(rng):
    edge_f = fbm(H, W, rng, base=4, octaves=4)
    HCY = CY + 14                                     # sit lower: cover the bottom-centre hex
    glow_fs = [fbm(H, W, rng, base=3, octaves=4) for _ in range(3)]
    n_mote, n_star, n_ray = 190, 30, 7
    mx = CX + (rng.random(n_mote) - 0.5) * 2 * RX * 0.62
    my = HCY + (rng.random(n_mote) - 0.5) * 2 * RY * 0.8
    mph = rng.random(n_mote); mrise = rng.uniform(18, 42, n_mote); msz = rng.uniform(0.8, 1.6, n_mote)
    sx = CX + (rng.random(n_star) - 0.5) * 2 * RX * 0.62
    sy = HCY + (rng.random(n_star) - 0.5) * 2 * RY * 0.7 - 6
    sph = rng.random(n_star); ssz = rng.uniform(2.0, 3.4, n_star)
    rx = CX + (rng.random(n_ray) - 0.5) * RX * 0.6; rph = rng.random(n_ray); rw = rng.uniform(6, 13, n_ray)
    tintc = np.array([255, 236, 175], float); gold = np.array([255, 200, 100], float)
    white = np.array([255, 248, 222], float)
    r = np.sqrt(((XX - CX) / (RX * 0.74 * (1 - 0.28 * np.clip((YY - HCY) / RY, 0, 1)))) ** 2 + ((YY - HCY) / (RY * 0.95)) ** 2)
    core = np.exp(-r * r * 2.6) * 0.85
    out = []
    for f in range(N):
        t = f / N
        w = [0.5 + 0.5 * math.cos(2 * math.pi * (t - k / 3)) for k in range(3)]
        glow = smooth(0.25, 0.8, sum(glow_fs[k] * w[k] for k in range(3)) / sum(w))
        edge = sample_wrapped(edge_f, XX, YY - t * 40)
        rxf = RX * 0.8 * (1 - 0.28 * np.clip((YY - HCY) / RY, 0, 1))
        env = 1 - smooth(0.3, 1.0, np.sqrt(((XX - CX) / rxf) ** 2 + ((YY - HCY) / (RY * 0.98)) ** 2) + (edge - 0.5) * 0.3)
        alpha = (env * (0.06 + 0.06 * glow) + core * 0.06)
        light = (env * (0.07 + 0.13 * glow) + core * 0.20)[..., None] * gold[None, None, :] * 0.5
        rays = np.zeros((H, W))
        for x0, ph, ww in zip(rx, rph, rw):
            pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2 * math.pi * (ph + t)))
            lean = (YY - CY) * -0.08
            rays += np.exp(-((XX - x0 - lean) / ww) ** 2) * pulse
        rays *= smooth(HCY + RY * 0.4, HCY - RY * 0.3, YY) * smooth(HCY - RY * 2.2, HCY - RY * 0.6, YY) * 0.3
        light = light + rays[..., None] * gold[None, None, :] * 0.4
        p = np.zeros((H, W, 3))
        for x, y, ph, ri, sz in zip(mx, my, mph, mrise, msz):
            q = (ph + t) % 1.0
            stamp(p, x, y - ri * q, white, sz, 0.9 * math.sin(math.pi * q) ** 1.5)
        for x, y, ph, sz in zip(sx, sy, sph, ssz):
            tw = max(0.0, math.sin(2 * math.pi * (ph + t))) ** 2
            if tw > 0.02:
                star(p, x, y, white, sz, 1.15 * tw)
        mul, add = comp(alpha, tintc, light + p)
        out.append(_pack(mul, add))
    return out


def render_death(rng):
    edge_f = fbm(H, W, rng, base=5, octaves=5)
    fields = [fbm(H, W, rng, base=4, octaves=6) for _ in range(3)]
    n = 110
    ex = CX + (rng.random(n) - 0.5) * 2 * RX * 1.1
    ey = CY + (rng.random(n) - 0.5) * 2 * RY * 1.0
    eph = rng.random(n); erise = rng.uniform(14, 34, n); esz = rng.uniform(0.7, 1.4, n)
    smoke_d = np.array([62, 12, 105], float); smoke_l = np.array([150, 60, 225], float)
    violet = np.array([150, 55, 220], float); ember = np.array([205, 130, 255], float)
    out = []
    for f in range(N):
        t = f / N
        ang = 0.07 * math.sin(2 * math.pi * t)
        ca, sa = math.cos(ang), math.sin(ang)
        Xr = CX + (XX - CX) * ca - (YY - CY) * sa
        Yr = CY + (XX - CX) * sa + (YY - CY) * ca
        w = [0.5 + 0.5 * math.cos(2 * math.pi * (t - k / 3)) for k in range(3)]
        body = sum(sample_wrapped(fields[k], Xr, Yr) * w[k] for k in range(3)) / sum(w)
        edge = sample_wrapped(edge_f, Xr, Yr)
        env = envelope(edge, grow=1.25, soft=0.75)
        dens = smooth(0.18, 0.75, env * (0.35 + 0.95 * body)) * 0.30
        shade = smooth(0.35, 0.85, body)[..., None]
        col = smoke_d[None, None, :] * (1 - shade) + smoke_l[None, None, :] * shade
        wisp = smooth(0.62, 0.9, body) * env
        glow = wisp[..., None] * violet[None, None, :] * 0.65 + dens[..., None] * violet[None, None, :] * 0.45
        p = np.zeros((H, W, 3))
        for x, y, ph, ri, sz in zip(ex, ey, eph, erise, esz):
            q = (ph + t) % 1.0
            stamp(p, x + 3 * math.sin(2 * math.pi * (ph + q)), y - ri * q, ember, sz, 0.75 * math.sin(math.pi * q) ** 1.6)
        mul, add = comp(dens, col, glow + p)
        out.append(_pack(mul, add))
    return out


def render(variant, seed=11):
    rng = np.random.default_rng(seed + sum(map(ord, variant)))
    if variant in ("sand", "snow"):
        return render_wind(variant, rng)
    if variant == "holy":
        return render_holy(rng)
    return render_death(rng)


def preview(pairs, ground=(70, 110, 45)):
    g = np.array(ground, float)
    outs = []
    for mi, ai in pairs:
        m = np.array(mi).astype(float); a = np.array(ai).astype(float)
        mm = np.where(m[..., 3:4] > 0, m[..., :3] / 255, 1.0)
        aa = np.where(a[..., 3:4] > 0, a[..., :3], 0.0)
        res = np.clip(g[None, None, :] * mm + aa, 0, 255)
        outs.append(Image.fromarray(res.astype(np.uint8), "RGB"))
    return outs


def to_ilb(lib, ilb, pairs):
    """every image of a PoisnCld-layout library -> 2-part composite (multiply 1026/100, additive 770/100)"""
    for img, (mi, ai) in zip(lib.images, pairs):
        base = img.primary
        parts = []
        for im, dm in ((mi, 1026), (ai, 770)):
            r = ilb.Record(copy.deepcopy(dict(base)))
            r["newdata"] = None
            ilb.encode_image(lib, r, im)
            r["drawMode"] = dm
            r["blendValue"] = 100
            parts.append(r)
        img.parts = parts
        img.composite = True
