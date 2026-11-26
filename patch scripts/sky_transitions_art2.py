#!/usr/bin/env python3
r"""
Sky / Clear Sky / Chasm transition art v2 (2026-11-07).

User: "revert the transitions for solid terrain ... the only thing i dont like about them is the left tip has a
transparent crack, fix that ... i only wanted sky/clear sky/chasm transitions with each other and with water etc to be
improved .. refer to shoreline (when land meets water), except make it ethereal/fading, kind of like smoke or fog with
curves etc".

  pair_fog(low, up, bl)      HEXTRANS 60x50 (lower hex origin - (6, 9)), Sky-family pairs: the edge becomes a
                             curving, lobed shoreline line (smooth lobes + domain-warped wisps) across which the two
                             tile textures cross-fade like fog, with mist strands curling along it.
  shore_fog(kind, k, ...)    Waterhex / IceHex 86x84 shore piece k (0..31) for a Sky ('S'), Clear Sky ('C') or Chasm
                             ('X') neighbour: the SHAPE of the vanilla land shoreline piece k (sand 0x00+k), blurred
                             and warped into fog: the sky texture at the hex edge dissolving into the water / ice.
                             Drawn at the water tile origin - (19, 32); only pixels inside the water hex are drawn.
  fix_black(img)             Ziggurat's cliff faces 0x100..0x1C7 carry a few pure-black pixels at their top-left that
                             show as a dark crack at an island's left tip -> inpainted from their neighbours.
"""
import math, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
import sky_clouds_art as SKY  # noqa: E402

ONE_BASE = 0xEC              # v2.9: one-sided pair fades = ONE_BASE + (BLEND - 0x70) + bl  (0xEC..0xFD, free ids)
BLEND = {("S", "X"): 0x70, ("X", "S"): 0x73, ("C", "X"): 0x76, ("X", "C"): 0x79, ("C", "S"): 0x7C, ("S", "C"): 0x7F}
SHORE_BASE = {"S": 0xA0, "X": 0xC0, "C": 0xE0}            # Waterhex / IceHex shore sets (Ziggurat: 0xA0 / 0xC0)
NEIGH = [(-32, -16), (0, -32), (32, -16)]
CW, CH, OX, OY = 60, 50, 6, 9
MASK = SKY._hexmask()
MIST = {"S": (140, 160, 214), "C": (232, 242, 252), "X": (138, 92, 186)}
_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


# ------------------------------------------------------------------------------------------------------------ helpers
def _noise(seed, n=64, blur=2):
    rng = np.random.default_rng(seed)
    g = rng.random((n, n))
    for _ in range(blur):
        g = (g + np.roll(g, 1, 0) + np.roll(g, 1, 1) + np.roll(g, -1, 0) + np.roll(g, -1, 1)) / 5
    return (g - g.min()) / (g.max() - g.min())


def _nz(g, x, y):
    """bilinear, wrapping"""
    n = g.shape[0]
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    a, b = g[y0 % n, x0 % n], g[y0 % n, (x0 + 1) % n]
    c, d = g[(y0 + 1) % n, x0 % n], g[(y0 + 1) % n, (x0 + 1) % n]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def _blur(a, s):
    r = int(math.ceil(s * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="constant")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, p)
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, p)
    return p[r:-r, r:-r]


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _ign(x, y):
    """interleaved gradient noise: a fine, even (blue-noise-like) dither threshold in [0, 1)"""
    return (52.9829189 * ((0.06711056 * x + 0.00583715 * y) % 1.0)) % 1.0


def _wrap(tx, ty):
    """any screen position (tile-local coords of some hex) -> the same texture position inside the tile mask"""
    for k in (0, -1, 1, -2, 2):
        x, y0 = tx - 32 * k, ty - 16 * k
        if not 0 <= x < 48:
            continue
        for m in (0, -1, 1, -2, 2, -3, 3):
            y = y0 - 32 * m
            if 0 <= y < 32 and MASK[y, x]:
                return x, y
    return None


def _tex(tile, tx, ty):
    p = _wrap(int(tx), int(ty))
    return tile[p[1], p[0], :3].astype(float) if p else tile[16, 24, :3].astype(float)


def sources(game_dir):
    return {"S": SKY.sky_tiles()[0], "C": SKY.clear_tiles()[0], "X": SKY.chasm_tiles(game_dir)[0]}


# --------------------------------------------------------------------------------------------- sky-family pair blends
def _edge(bl):
    if bl == 0:
        return (OX + 0.0, OY + 15.5), (OX + 15.0, OY - 0.5)
    if bl == 1:
        return (OX + 15.0, OY - 0.5), (OX + 33.0, OY - 0.5)
    return (OX + 33.0, OY - 0.5), (OX + 48.0, OY + 15.5)


def _in_hex(tx, ty):
    return 0 <= ty < 32 and 0 <= tx < 48 and MASK[ty, tx]


def pair_fog(game_dir, low, up, bl, src=None, one_sided=False):
    src = src or sources(game_dir)
    (ax, ay), (bx, by) = _edge(bl)
    ex, ey = bx - ax, by - ay
    L = math.hypot(ex, ey)
    ux, uy = ex / L, ey / L
    nxv, nyv = uy, -ux                                       # normal pointing into the upper hex
    nx, ny = NEIGH[bl]
    seed = 0x5F00 + 31 * bl + 7 * ord(low) + ord(up)
    w1, w2, w3 = _noise(seed, blur=3), _noise(seed + 1, blur=3), _noise(seed + 2, blur=1)
    rng = np.random.default_rng(seed)
    ph1, ph2 = rng.uniform(0, 2 * math.pi, 2)
    mist = np.array(MIST[up], float) * 0.5 + np.array(MIST[low], float) * 0.5
    W = 5.5 if one_sided else 7.5
    out = np.zeros((CH, CW, 4), np.uint8)
    for y in range(CH):
        for x in range(CW):
            tx, ty = x - OX, y - OY
            lower, upper = _in_hex(tx, ty), _in_hex(tx - nx, ty - ny)
            if not (lower or upper):
                continue
            # domain warp -> smoky curls
            px = x + 0.5 + 2.4 * (_nz(w1, x * 0.17, y * 0.17) - 0.5) * 2
            py = y + 0.5 + 2.4 * (_nz(w2, x * 0.17, y * 0.17) - 0.5) * 2
            t = ((px - ax) * ux + (py - ay) * uy) / L
            s = (px - ax) * nxv + (py - ay) * nyv               # + = into the upper hex
            env = math.sin(math.pi * min(1.0, max(0.0, t))) ** 0.8
            lobe = env * (-1.2 + 2.2 * math.sin(2 * math.pi * 0.95 * t + ph1) + 1.0 * math.sin(2 * math.pi * 2.2 * t + ph2))
            # v2.9 (user: "the dirt hex between two bridges has a big transparent crack"): the fade spilled across
            # the edge into the UPPER hex, which is drawn first - and the upper sky hex had already drawn its cliff
            # face there (under its land neighbour) -> the spill painted sky over the cliff.  ONE-SIDED now: the
            # whole fade lies inside the lower hex (upper terrain 100 % at the edge), the upper hex is never touched
            # (the one-sided set is only picked by the rule cave where the upper hex hangs cliff faces; elsewhere the
            # symmetric fade stays - one-sided everywhere zig-zags along diagonal boundaries)
            if one_sided:
                if not lower:
                    continue
                d = s - (-W - 2.5 + 0.6 * (lobe - 2.0))
                if d < -W - 2:
                    continue
            else:
                d = s - lobe
                if abs(d) > W + 2:
                    continue
            wu = float(_smooth(-W, W, d))                        # share of the upper terrain
            other = wu if lower else 1 - wu
            if t < 0 or t > 1:                                   # fade out at the corners (three hexes meet)
                other *= max(0.0, 1 - abs(t - (0 if t < 0 else 1)) / 0.3)
            # v2.8 (user: "sky/clear sky transition needs the same cloud fix"): a PURE cross-fade of the two tile
            # pixels (no mist / strands) - the overlay's sky fog path recovers t from exactly this mix and blends
            # both kinds' clouds across the band
            if other < 0.05:
                continue
            if other < 0.18 and other / 0.18 <= _BAYER[y % 4, x % 4]:
                continue
            cl = _tex(src[low], tx, ty)
            cu = _tex(src[up], tx - nx, ty - ny)
            col = np.round(cl * (1 - other) + cu * other) if one_sided else np.round(cl * (1 - wu) + cu * wu)
            out[y, x, :3] = np.clip(col, 0, 255).astype(np.uint8)
            out[y, x, 3] = 255
    return out


# ---------------------------------------------------------------------------------------------- water / ice shores
SW, SH, SOX, SOY = 86, 84, 19, 32                             # shore piece canvas, tile origin inside it
_HEX_EDGES = [((0.0, 15.5), (15.0, -0.5)), ((15.0, -0.5), (33.0, -0.5)), ((33.0, -0.5), (48.0, 15.5)),
              ((48.0, 15.5), (33.0, 31.5)), ((33.0, 31.5), (15.0, 31.5)), ((15.0, 31.5), (0.0, 15.5))]


def shore_fog(kind, k, shape, own_tile, src, seed=0):
    """shape = vanilla shoreline piece k (RGBA 84x86), own_tile = the water / ice tile (32x48)"""
    M = (shape[..., 3] > 0)
    # v6 (user: "you readded the thin tails"): morphological opening (erode 2 / dilate 2) drops the thin strips the
    # vanilla sand pieces trail along the hex edges, so only the rounded shoreline bodies make fog
    def _er(m):
        return m & np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1)

    def _di(m):
        return m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    M = _di(_di(_er(_er(M)))).astype(float)
    if M.sum() == 0:
        return np.zeros((SH, SW, 4), np.uint8)
    n1, n2, n3 = _noise(0x7100 + k + seed, blur=3), _noise(0x7200 + k + seed, blur=3), _noise(0x7300 + k + seed, blur=1)
    yy, xx = np.mgrid[0:SH, 0:SW]
    wx = np.vectorize(lambda x, y: _nz(n1, x * 0.22, y * 0.22))(xx, yy) - 0.5
    wy = np.vectorize(lambda x, y: _nz(n2, x * 0.22, y * 0.22))(xx, yy) - 0.5
    sx = np.clip(np.round(xx + 4.0 * wx), 0, SW - 1).astype(int)
    sy = np.clip(np.round(yy + 4.0 * wy), 0, SH - 1).astype(int)
    Mw = np.maximum(M, M[sy, sx])
    # v3 (user: "long skinny tails" + a hex-shaped band where the clouds stop): no curl wisps, blob-like body; the
    # fog never reaches a flat 100 % sky band and is tinted toward the CLOUDED sky (the overlay only draws clouds
    # inside the sky hex, so a cloud reaching the edge now continues into a similar whitish fog instead of bare tile)
    # v8 (user: thin tails): most vanilla sand pieces lie on the LAND side of the edge, so only a sliver of them falls
    # inside the water hex -> thin tapering strips.  Take the in-hex part and grow it ~4 px (inside the hex only)
    # before the blur: slivers become soft rounded bands, big curved bodies keep their shape.
    hexm = np.zeros((SH, SW), bool)
    hexm[SOY:SOY + 32, SOX:SOX + 48] = MASK
    H = (Mw > 0) & hexm
    for _ in range(4):
        H = (H | np.roll(H, 1, 0) | np.roll(H, -1, 0) | np.roll(H, 1, 1) | np.roll(H, -1, 1)) & hexm
    Mw = np.maximum(Mw, H.astype(float))
    a = _smooth(0.03, 0.9, _blur(Mw, 3.6))
    sky = src[kind]
    mist = np.array(MIST[kind], float)
    cloud_k = {"S": 0.12, "C": 0.32, "X": 0.0}[kind]
    cloud = np.array({"S": (196, 200, 238), "C": (246, 248, 252), "X": (0, 0, 0)}[kind], float)
    curl = np.ones((SH, SW))
    out = np.zeros((SH, SW, 4), np.uint8)
    for y in range(SH):
        for x in range(SW):
            tx, ty = x - SOX, y - SOY
            if not _in_hex(tx, ty):
                continue
            av = float(a[y, x])
            # v5 (user: "too grainy now, make it smooth like before ... the clouds should be shown in the water hex
            # too"): smooth blend of THIS position's water and sky tile pixels (no tint / mist) - the overlay's water
            # mode (patch_sky_overlay_water_v1) recovers the sky share of each pixel from exactly this mix and adds
            # the cloud of the matching sky pixel scaled by it, so the clouds fade into the water with the fog
            if av < 0.08:
                continue
            cw = own_tile[ty, tx, :3].astype(float)
            cs = src[kind][ty, tx, :3].astype(float)
            out[y, x, :3] = np.clip(np.round(cw * (1 - av) + cs * av), 0, 255).astype(np.uint8)
            out[y, x, 3] = 255
    return out


# ------------------------------------------------------------------------------------------------------ crack fix
def grow_top(img):
    """v2.6 (user: "for solid terrains, the left point of the hex has a small transparent crack, fix that by filling it
    in"): the 1-px diagonal gap between an island's edge lip and the cliff face below it at the hex's left point ->
    every cliff face grows one pixel upward at its top edge (copy of the pixel below)"""
    out = img.copy()
    op = img[..., 3] > 0
    for x in range(img.shape[1]):
        ys = np.nonzero(op[:, x])[0]
        if len(ys) and ys[0] > 0:
            out[ys[0] - 1, x] = img[ys[0], x]
    return out


def fill_gaps(img):
    """v2.8 (user: "some solid terrains (like dirt) still have transparent cracks"): the Ziggurat lips and cliff faces
    have 1-2 px see-through slits INSIDE the shape -> fill every transparent run of <= 2 px that has opaque pixels
    on both sides (rows, then single-pixel holes in columns), colour interpolated from the two sides"""
    out = img.copy()
    for _ in range(2):
        op = out[..., 3] > 0
        h, w = op.shape
        for y in range(h):
            x = 0
            while x < w:
                if op[y, x]:
                    x += 1
                    continue
                x0 = x
                while x < w and not op[y, x]:
                    x += 1
                if x0 > 0 and x < w and x - x0 <= 2:
                    a, b = out[y, x0 - 1, :3].astype(float), out[y, x, :3].astype(float)
                    for i, xx in enumerate(range(x0, x)):
                        f = (i + 1) / (x - x0 + 1)
                        out[y, xx, :3] = (a * (1 - f) + b * f).astype(np.uint8)
                        out[y, xx, 3] = 255
        op = out[..., 3] > 0
        for x in range(w):
            for y in range(1, h - 1):
                if not op[y, x] and op[y - 1, x] and op[y + 1, x]:
                    out[y, x, :3] = ((out[y - 1, x, :3].astype(int) + out[y + 1, x, :3].astype(int)) // 2).astype(np.uint8)
                    out[y, x, 3] = 255
    return out


def ice_teeth(k, zig_piece, water_teeth, ice_teeth_up, ice_tile=None):
    """v2.8 (user: "ice on sky etc looks bad. it should look similar to ice on water"): ice shore piece k for a
    Sky-family neighbour = the ice/water edge art on every hex edge piece k is for (edges read from the Ziggurat
    piece k): upper edges -> IceHex 0x23/0x24/0x25 (what an ice hex draws under water) at the tile origin -(6,9);
    lower edges -> Waterhex 0x23/0x24/0x25 (the ice teeth a water hex draws under ice) in the lower neighbour frame"""
    out = np.zeros((SH, SW, 4), np.uint8)
    op = zig_piece[..., 3] > 0
    pys, pxs = np.nonzero(op)
    hexm = np.zeros((SH, SW), bool)
    hexm[SOY:SOY + 32, SOX:SOX + 48] = MASK
    if len(pys):
        inside = hexm[pys, pxs]
        pys, pxs = pys[inside], pxs[inside]
    if not len(pys):
        return out
    place = {0: (ice_teeth_up[0x23], (SOX - 6, SOY - 9)), 1: (ice_teeth_up[0x24], (SOX - 6, SOY - 9)),
             2: (ice_teeth_up[0x25], (SOX - 6, SOY - 9)), 3: (water_teeth[0x23], (SOX - 6 + 32, SOY - 9 + 16)),
             4: (water_teeth[0x24], (SOX - 6, SOY - 9 + 32)), 5: (water_teeth[0x25], (SOX - 6 - 32, SOY - 9 + 16))}
    drawn = []
    for ei, ((x0, y0), (x1, y1)) in enumerate(_HEX_EDGES):
        ax0, ay0, ex, ey = x0 + SOX, y0 + SOY, x1 - x0, y1 - y0
        tt = np.clip(((pxs - ax0) * ex + (pys - ay0) * ey) / (ex * ex + ey * ey), 0, 1)
        dd = np.hypot(pxs - (ax0 + tt * ex), pys - (ay0 + tt * ey))
        if (dd <= 2.5).sum() < 40:     # v2.9: real edge = 50 (diagonals) .. 68 px, corner spill <= 20 (60 dropped UR/top/LR/bottom)
            continue
        drawn.append(ei)
        img, (ox, oy) = place[ei]
        h, w = img.shape[:2]
        for yy in range(h):
            for xx in range(w):
                if img[yy, xx, 3] and 0 <= ox + xx < SW and 0 <= oy + yy < SH:
                    out[oy + yy, ox + xx] = img[yy, xx]
    if ice_tile is not None:
        out = ice_thickness(out, [e for e in drawn if e >= 3], ice_tile, seed=k)
    return out


def fill_tip_holes(ht, rounds=6, log=None):
    """v2.9 (user: "that left tip of hex still has small transparent crack"): compose the COVERAGE of every land/sky
    layout around a land hex (center land + each of its 6 neighbours land or sky = 64 configs, both column parities x
    the 3 cliff variants, Sky and Chasm backgrounds) exactly as the engine places the pieces (tile at origin; lips
    0xE6+bl (land hex) / 0xE9+bl (sky hex under land) at origin-(6,9) displaced into the neighbour frame; Ziggurat
    cliff faces 0x100.. at the sky hex origin, transitions_preview.cliff_draws) and fill every see-through pixel
    that sits between covered pixels (row run <= 2 or a 1-px column hole) INTO an adjacent cliff face (lips are
    shared by every land type, cliffs only hang under islands).  ht: id -> RGBA array, modified in place.
    Returns the set of ids changed."""
    import transitions_preview as TP
    changed = set()
    pos = [(2, 2), (2, 3), (4, 3), (3, 2), (3, 3), (5, 3)]
    COLS, ROWS = 8, 6
    nbr = [(-1, -1), (0, -2), (1, -1), (1, 1), (0, 2), (-1, 1)]
    for rnd in range(rounds):
        fixes = 0
        for bg in ("S", "X", "M1", "M2", "M3", "M4", "M5", "M6"):      # v2.9c: + mixed Sky/Chasm backgrounds
            for cx, cy in pos:
                Y0 = 2 * cy + (cx & 1)
                for cfg in range(64):
                    land = {(cx, Y0)}
                    for i, (dx, dy) in enumerate(nbr):
                        if cfg >> i & 1:
                            land.add((cx + dx, Y0 + dy))

                    def getT(x, Y):
                        if not (0 <= x < COLS) or (Y - (x & 1)) % 2 or not (0 <= (Y - (x & 1)) // 2 < ROWS):
                            return None
                        if (x, Y) in land:
                            return 1
                        if bg[0] == "M":                          # Chasm hexes draw the +0x80 cliff set
                            h = ((x * 73856093) ^ (Y * 19349663) ^ (int(bg[1:]) * 83492791)) & 0xFFFFFFFF
                            return TP.code("X" if (h >> 7) & 1 else "S")
                        return TP.code(bg)
                    Wp, Hp = COLS * 32 + 64, ROWS * 32 + 96
                    OXc, OYc = 32, 48
                    cov = np.zeros((Hp, Wp), bool)
                    draws = []                                   # (id, px, py)
                    # engine order: hex by hex (rows of half-row Y, then x): tile, its transitions, its cliff faces.
                    # Tiles overlap 1 px on the diagonals -> a later SKY tile un-covers the land tip pixel
                    for Y in range(2 * ROWS + 1):
                        for x in range(COLS):
                            me = getT(x, Y)
                            if me is None:
                                continue
                            ox_, oy_ = OXc + 32 * x, OYc + 16 * Y
                            if (x, Y) in land:
                                cov[oy_:oy_ + 32, ox_:ox_ + 48] |= MASK
                            else:
                                cov[oy_:oy_ + 32, ox_:ox_ + 48] &= ~MASK
                            mine = []
                            for bl, (dx, dy) in enumerate(TP.DIRS):
                                n = getT(x + dx, Y + dy)
                                if n is None:
                                    continue
                                if (x, Y) in land and n in (0xB, 0xE):
                                    tid = 0xE6 + bl
                                elif me in (0xB, 0xE) and (x + dx, Y + dy) in land:
                                    tid = 0xE9 + bl
                                else:
                                    continue
                                mine.append((tid, ox_ - 6 + TP.DISP[bl][0], oy_ - 9 + TP.DISP[bl][1]))
                            for tid in TP.cliff_draws(me, x, Y, getT):
                                mine.append((tid, ox_, oy_))
                            for tid, px, py in mine:
                                a = ht.get(tid)
                                if a is None:
                                    continue
                                h, w = a.shape[:2]
                                cov[py:py + h, px:px + w] |= a[..., 3] > 0
                            draws += mine
                    # holes near the center hex only (other layouts cover the rest)
                    ox0, oy0 = OXc + 32 * cx, OYc + 16 * Y0
                    for yy in range(oy0 - 24, oy0 + 72):
                        for xx in range(ox0 - 40, ox0 + 88):
                            if cov[yy, xx]:
                                continue
                            hole = (cov[yy - 1, xx] and cov[yy + 1, xx]) or \
                                   (any(cov[yy, xx - d] for d in (1, 2)) and any(cov[yy, xx + d] for d in (1, 2))
                                    and (cov[yy, xx - 1] or cov[yy, xx + 1]))
                            if not hole:
                                continue
                            for tid, px, py in sorted(draws, key=lambda d: d[0] < 0x100):
                                a = ht.get(tid)
                                if a is None or tid < 0x100:
                                    continue
                                lx, ly = xx - px, yy - py
                                h, w = a.shape[:2]
                                if not (0 <= lx < w and 0 <= ly < h) or a[ly, lx, 3]:
                                    continue
                                nb = [a[ly + j, lx + i, :3].astype(int) for j in (-1, 0, 1) for i in (-1, 0, 1)
                                      if (i or j) and 0 <= ly + j < h and 0 <= lx + i < w and a[ly + j, lx + i, 3]]
                                if len(nb) < 2:
                                    continue
                                a[ly, lx, :3] = np.mean(nb, 0).astype(np.uint8)
                                a[ly, lx, 3] = 255
                                cov[yy, xx] = True
                                changed.add(tid)
                                fixes += 1
                                if log is not None:
                                    log.append((rnd, bg, cx, cy, cfg, hex(tid), lx, ly))
                                break
        if not fixes:
            break
    return changed


ICE_T = 11                                                     # ice face depth (px)

# ---- v2.9b per-edge water fog wedges (user: "the highlighted water/clear sky transition looks janky") -----------------
# The engine draws water shores as COMBINATION pieces (one image covers 2-3 edges, colour set = ONE side's base), so a
# water hex with Chasm on top and Clear Sky upper-right got Clear fog across the Chasm edge.  Now a cave in ShowDynamic
# draws, for a water hex with any sky side, one wedge per sky side in that side's own kind (+ the engine's single-edge
# sand pieces for sand sides).  Wedge = the hex pixels nearest to that edge; density from the distance to the edge +
# a noise field shared by all wedges (continuous across the bisector to a sky neighbour), tapered toward a non-sky
# neighbour edge, colour cross-faded toward a different-kind neighbour edge.
WEDGE_BASE = 0x100                    # id = WEDGE_BASE + side*48 + (kind-1)*16 + prev*4 + next   (0x100..0x21F)
ENG2HEX = [1, 2, 3, 4, 5, 0]          # engine side (top, UR, LR, bottom, LL, UL) -> _HEX_EDGES index
STATE_KIND = {1: "S", 2: "X", 3: "C"}
WEDGE_D = 16.0
_WD = None


def _wedge_geom():
    global _WD
    if _WD is None:
        ys, xs = np.mgrid[0:32, 0:48]
        px, py = xs + 0.5, ys + 0.5
        d = []
        for (x0, y0), (x1, y1) in _HEX_EDGES:
            ex, ey = x1 - x0, y1 - y0
            t = np.clip(((px - x0) * ex + (py - y0) * ey) / (ex * ex + ey * ey), 0, 1)
            d.append(np.hypot(px - (x0 + t * ex), py - (y0 + t * ey)))
        d = np.array(d)
        g = _noise(0x3ED6E, blur=3)
        n = np.array([[2.8 * (_nz(g, x * 0.23, y * 0.23) - 0.5) * 2 for x in range(48)] for y in range(32)])
        _WD = (d, np.argmin(d, 0), n)
    return _WD


def wedge_fog(side, st, prev, nxt, water, src):
    """RGBA shore-canvas image (SH x SW, tile at SOX,SOY) of the fog wedge of engine side `side` (kind state st 1..3),
    neighbour side states prev/nxt (0 none, 1 Sky, 2 Chasm, 3 Clear)"""
    d, owner, n = _wedge_geom()
    e = ENG2HEX[side]
    ep, en = ENG2HEX[(side + 5) % 6], ENG2HEX[(side + 1) % 6]
    K = STATE_KIND[st]
    out = np.zeros((SH, SW, 4), np.uint8)
    for y in range(32):
        for x in range(48):
            if not MASK[y, x] or owner[y, x] != e:
                continue
            a = 1.0 - float(_smooth(0.0, WEDGE_D, d[e, y, x] + n[y, x]))
            sky = src[K][y, x, :3].astype(float)
            for ns, en_ in ((prev, ep), (nxt, en)):
                gap = d[en_, y, x] - d[e, y, x]                  # 0 on the bisector, grows into this wedge
                if ns == 0:
                    a *= float(_smooth(0.0, 9.0, gap))
                elif ns != st:
                    w = 0.5 * (1.0 - float(_smooth(0.0, 9.0, gap)))
                    sky = sky * (1 - w) + src[STATE_KIND[ns]][y, x, :3].astype(float) * w
            if a < 0.06:
                continue
            col = water[y, x, :3].astype(float) * (1 - a) + sky * a
            out[SOY + y, SOX + x, :3] = np.clip(np.round(col), 0, 255).astype(np.uint8)
            out[SOY + y, SOX + x, 3] = 255
    return out




def ice_thickness(out, lower, ice_tile, seed=0):
    """v2.9b (user: "make ice thicker when its on sky/clear sky/chasm"): an ice cliff face under every LOWER edge that
    faces sky (3 LR / 4 bottom / 5 LL): per column, below the lowest ice pixel (hex body + the jagged chunks) a face of
    ~ICE_T px - lit lip, darkening downward, ragged icicle bottom, vertical streaks; tapers where the run of sky
    edges ends.  Drawn UNDER the chunks' outline only (never over ice)."""
    if not lower:
        return out
    out = out.copy()
    rng = np.random.default_rng(0x1CE0 + seed)
    body = np.zeros((SH, SW), bool)
    body[SOY:SOY + 32, SOX:SOX + 48] = MASK
    body |= out[..., 3] > 0
    tile = ice_tile[..., :3].astype(float)
    base = tile[MASK].mean(0)
    span = {3: (33, 48), 4: (15, 33), 5: (0, 15)}
    cols = np.zeros(SW, bool)
    for e in lower:
        x0, x1 = span[e]
        cols[SOX + x0 - 3:SOX + x1 + 3] = True
    # taper toward the ends of each run of face columns
    xs = np.nonzero(cols)[0]
    runs, cur = [], [xs[0]]
    for x in xs[1:]:
        if x == cur[-1] + 1:
            cur.append(x)
        else:
            runs.append(cur); cur = [x]
    runs.append(cur)
    depth = np.zeros(SW)
    jag = np.convolve(rng.uniform(-1, 1, SW + 4), np.ones(3) / 3, "same")[2:-2]
    streak = np.convolve(rng.uniform(-1, 1, SW + 2), [0.25, 0.5, 0.25], "same")[1:-1]
    for r in runs:
        n = len(r)
        for i, x in enumerate(r):
            end = min(i, n - 1 - i)
            depth[x] = ICE_T * min(1.0, (end + 1) / 6.0) + 2.2 * jag[x] + (1.5 if (x * 7 + seed) % 5 == 0 else 0)
    for x in xs:
        ys = np.nonzero(body[:, x])[0]
        ys = ys[ys >= SOY + 8]
        if not len(ys):
            continue
        yb = ys.max()
        d = int(round(depth[x]))
        for j in range(1, d + 1):
            y = yb + j
            if y >= SH or body[y, x]:
                break
            f = j / max(1, d)
            shade = (1.18 if j == 1 else 0.86 - 0.42 * f) * (1 + 0.10 * streak[x])
            tint = np.array([0.92, 0.98, 1.10])
            ty, tx = (y - SOY) % 32, (x - SOX) % 48
            tex = tile[ty, tx] if MASK[ty, tx] else base
            col = (base * 0.6 + tex * 0.4) * shade * tint
            if j == d:
                col = col * 0.7
            out[y, x, :3] = np.clip(col, 0, 255).astype(np.uint8)
            out[y, x, 3] = 255
    return out


def fix_black(img):
    """pure-black opaque pixels (dark crack at the island's left tip) -> mean of their opaque, non-black neighbours"""
    out = img.copy()
    h, w = img.shape[:2]
    blk = (img[..., 3] > 0) & (img[..., :3].astype(int).sum(-1) == 0)
    for _ in range(3):
        if not blk.any():
            break
        nb = blk.copy()
        for y, x in zip(*np.nonzero(blk)):
            acc = [out[j, i, :3].astype(float) for j in range(max(0, y - 1), min(h, y + 2))
                   for i in range(max(0, x - 1), min(w, x + 2))
                   if out[j, i, 3] > 0 and not blk[j, i]]
            if acc:
                out[y, x, :3] = np.mean(acc, 0).astype(np.uint8)
                nb[y, x] = False
        blk = nb
    out[blk, :3] = (40, 30, 24)
    return out
