#!/usr/bin/env python3
r"""
Sky / Clear Sky / Chasm transition art (2026-11-06), new HEXTRANS.ILB images.

User: "improve the transitions between sky/clear sky/chasm with other terrains (without changing any existing
transitions between vanilla terrains). and improve the transition between each other too".

HEXTRANS images are 60x50, drawn at the LOWER hex's tile origin - (6, 9); slot bl 0/1/2 = its upper-left / top /
upper-right edge (the neighbour sits at (-32,-16) / (0,-32) / (+32,-16)).  Each edge is evaluated once (by the lower
hex), so a blend image covers BOTH sides of the edge: on the lower side it scatters the upper terrain's pixels, on the
upper side the lower terrain's, in organic clumps whose density falls off with the distance from the edge.
  blend(low, up, bl)   low/up in 'S' Sky, 'C' Clear Sky, 'X' Chasm    -> ids BLEND[(low, up)] + bl
  chasm lips           0xE6/0xE9 (Ziggurat's land lips) re-tinted to dark basalt -> 0x82 / 0x85 + bl
  chasm cliffs         the existing Chasm cliff faces 0x180.. (only Chasm uses +0x80) get the same basalt tint
Ids are bytes ([hex+0x10+bl]), so only free ids below 0x100 are used (0x66..0x8F is free in HEXTRANS).
"""
import math, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sky_clouds_art as SKY  # noqa: E402

BLEND = {("S", "X"): 0x70, ("X", "S"): 0x73, ("C", "X"): 0x76, ("X", "C"): 0x79, ("C", "S"): 0x7C, ("S", "C"): 0x7F}
CHASM_LIP_LOW_LAND, CHASM_LIP_LOW_CHASM = 0x82, 0x85        # + bl (copies of 0xE6 / 0xE9)
NEIGH = [(-32, -16), (0, -32), (32, -16)]
CW, CH, OX, OY = 60, 50, 6, 9
MASK = SKY._hexmask()


def _noise(seed, n=64, blur=2):
    rng = np.random.default_rng(seed)
    g = rng.random((n, n))
    for _ in range(blur):
        g = (g + np.roll(g, 1, 0) + np.roll(g, 1, 1) + np.roll(g, -1, 0) + np.roll(g, -1, 1)) / 5
    g = (g - g.min()) / (g.max() - g.min())
    return g


def _in_hex(tx, ty):
    return 0 <= ty < 32 and 0 <= tx < 48 and MASK[ty, tx]


def _edge(bl):
    """edge segment in canvas coords (the boundary between the lower hex and the neighbour in slot bl)"""
    if bl == 0:
        return (OX + 0.0, OY + 15.5), (OX + 15.0, OY - 0.5)
    if bl == 1:
        return (OX + 15.0, OY - 0.5), (OX + 33.0, OY - 0.5)
    return (OX + 33.0, OY - 0.5), (OX + 48.0, OY + 15.5)


def _dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    vx, vy = bx - ax, by - ay
    t = ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)
    tc = min(1.0, max(0.0, t))
    cx, cy = ax + tc * vx, ay + tc * vy
    return math.hypot(px - cx, py - cy), t


def _pick(tile, x, y):
    """a pixel of the terrain's tile texture near (x, y) (wrapped into the hex)"""
    for k in range(48):
        tx, ty = (x * 3 + k * 7) % 48, (y * 5 + k * 3) % 32
        if MASK[ty, tx]:
            return tile[ty, tx, :3]
    return tile[16, 24, :3]


def _sources(game_dir):
    sky = SKY.sky_tiles()[0]
    clear = SKY.clear_tiles()[0]
    chasm = SKY.chasm_tiles(game_dir)[0]
    return {"S": sky, "C": clear, "X": chasm}


# v2 (user: "the transitions aren't great, make them more ethereal, like a fading into each other kind of"): no more
# pixel clumps.  Each pixel near the edge is a smooth colour cross-fade of the two terrains' own tile textures, both
# sampled continuously across the edge (the hex lattice is periodic, so the neighbour's texture is read at the same
# screen position), with the fade line warped by soft noise into wisps, plus a faint mist glow along the seam.
# Pixels where the other terrain's share drops below ~3 % stay transparent (native tile + cloud animation there).
FADE_W = 7.0                                    # px each side of the edge over which the fade runs
MIST = {"S": (150, 170, 220), "C": (226, 238, 252), "X": (128, 84, 176)}
_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


def _wrap(tx, ty):
    """(tx, ty) in any hex of the lattice -> the same texture position inside the tile mask (lattice (32,16),(0,32))"""
    for k in (0, -1, 1, -2, 2):
        x = tx - 32 * k
        y0 = ty - 16 * k
        if not 0 <= x < 48:
            continue
        for m in (0, -1, 1, -2, 2, -3, 3):
            y = y0 - 32 * m
            if 0 <= y < 32 and MASK[y, x]:
                return x, y
    return None


def _tex(tile, tx, ty):
    p = _wrap(tx, ty)
    return tile[p[1], p[0], :3].astype(float) if p else tile[16, 24, :3].astype(float)


def _smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def blend(game_dir, low, up, bl, src=None):
    """60x50 RGBA covering both sides of the edge between the lower hex ('low') and its slot-bl neighbour ('up')"""
    src = src or _sources(game_dir)
    a, b = _edge(bl)
    nx, ny = NEIGH[bl]
    warp = _noise(0x5E00 + 17 * bl + 3 * ord(low) + ord(up), blur=3)
    wisp = _noise(0x7A11 + bl + ord(low), blur=1)
    mist = np.array(MIST[up], float) * 0.5 + np.array(MIST[low], float) * 0.5
    out = np.zeros((CH, CW, 4), np.uint8)
    for y in range(CH):
        for x in range(CW):
            tx, ty = x - OX, y - OY
            lower = _in_hex(tx, ty)
            upper = _in_hex(tx - nx, ty - ny)
            if not (lower or upper):
                continue
            d, t = _dist((x + 0.5, y + 0.5), a, b)
            if d > FADE_W + 3 or t < -0.25 or t > 1.25:
                continue
            u = t * 2.3                                          # warp the fade line along the edge (wisps)
            n = warp[int(u * 9 + 3) % 64, (int(d * 2) + 7 * bl) % 64] - 0.5
            s = (d if upper else -d) + 4.2 * n                   # signed distance, + = into the upper hex
            wu = _smooth(-FADE_W, FADE_W, s)                     # share of the upper terrain
            other = wu if lower else 1 - wu
            if t < 0 or t > 1:                                   # fade out where three hexes meet
                other *= max(0.0, 1 - abs(t - (0 if t < 0 else 1)) / 0.25)
            if other < 0.03:
                continue
            if other < 0.14 and other / 0.14 <= _BAYER[y % 4, x % 4]:   # dithered tail: no hard rim
                continue
            cl = _tex(src[low], tx, ty)
            cu = _tex(src[up], tx - nx, ty - ny)
            col = cl * (1 - wu) + cu * wu
            h = 0.20 * math.exp(-(s / 3.0) ** 2) * (0.55 + 0.45 * wisp[y % 64, (x * 2) % 64])
            col = col * (1 - h) + mist * h
            out[y, x, :3] = np.clip(col, 0, 255).astype(np.uint8)
            out[y, x, 3] = 255
    return out


BASALT = np.array((0.62, 0.56, 0.74))


def basalt(img):
    """re-tint brown cliff/lip art to the Chasm's dark violet basalt (keeps shading)"""
    out = img.copy()
    m = out[..., 3] > 0
    rgb = out[..., :3].astype(float)
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    tgt = np.stack([lum * 0.78, lum * 0.70, lum * 0.95], -1)
    rgb = rgb * 0.35 + tgt * 0.65
    out[..., :3] = np.where(m[..., None], np.clip(rgb * 0.92, 0, 255), out[..., :3]).astype(np.uint8)
    return out


def all_images(game_dir, ht):
    """{id: rgba} of every new/changed HEXTRANS image; ht = current decoded HEXTRANS {id: rgba}"""
    src = _sources(game_dir)
    out = {}
    for (low, up), base in BLEND.items():
        for bl in range(3):
            out[base + bl] = blend(game_dir, low, up, bl, src)
    for bl in range(3):
        out[CHASM_LIP_LOW_LAND + bl] = basalt(ht[0xE6 + bl])
        out[CHASM_LIP_LOW_CHASM + bl] = basalt(ht[0xE9 + bl])
    return out


def chasm_cliffs(ht_vanilla_zig):
    """the Chasm cliff faces 0x180..0x1C7 re-tinted from their (Ziggurat) originals"""
    return {i: basalt(a) for i, a in ht_vanilla_zig.items() if 0x180 <= i <= 0x1C7}
