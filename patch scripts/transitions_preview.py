#!/usr/bin/env python3
r"""
Offline strategic-map renderer for terrain transitions (2026-11-06) - reproduces how AoWEPACK/HSEPack pick and draw
HEXTRANS images, so Sky / Clear Sky / Chasm edge changes can be judged before touching the game.

Engine facts (RE 11/06):
  * Tiles 48x32 (sky_clouds_art.SPANS mask); column x at px = 32x, row y at py = 32y + 16(x&1).  Half-row coords
    Y = 2y + (x&1); neighbours: above (0,-2), upper-left (-1,-1), upper-right (1,-1), lower-left (-1,1), ...
  * TAoWHexagon.UpdateTransition (AoWEPACK 0x5579A9E0, edx = slot bl 0..2 -> HSE dir 6/1/2 = upper-left / above /
    upper-right neighbour): ebp = own terrain, edi = neighbour terrain -> [hex+0x10+bl] = HEXTRANS id (0xFF none),
    plus a 'displaced' bit (bl+3 of [hex+0x13]) = draw the image in the NEIGHBOUR's frame.
  * Ziggurat Sky/Chasm block B (AoWEPACK 0x55850B50) runs first (see transitions_rule()).
  * HSEPack hexagon draw 0x55611FA4: tile at origin, each transition image at origin-(6,9), displaced: bl0 -(32,16),
    bl1 -(0,32), bl2 +(32,-16).
  * Ziggurat block A+0x40 (AoWEPACK 0x55850850, after the normal Show): a Sky/Chasm hex draws cliff faces
    (HEXTRANS 0x100.. + 0x20*((2nx+ny) % 3) [+0x80 chasm]) at its origin-(0,8)... for land neighbours (table below).
render(grid, rule) -> PIL image.  grid = list of rows of terrain codes ('S' Sky, 'C' Clear Sky, 'X' Chasm, digits).
"""
import os, struct, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import sky_clouds_art as SKY  # noqa: E402

GD = os.path.dirname(HERE)
LAND = 0x103E                 # terrains 1-5, 0xC
CLIFF = [((1, -1), [(0x100, [(1, 1)]), (0x106, [])]),
         ((0, -2), [(0x101, []), (0x103, [(1, -1)]), (0x107, [(-1, -1)])]),
         ((-1, -1), [(0x102, [(-1, 1)]), (0x105, [])]),
         ((-1, 1), [(0x104, [(0, 2)])])]
DIRS = [(-1, -1), (0, -2), (1, -1)]       # bl 0, 1, 2
DISP = [(-32, -16), (0, -32), (32, -16)]


def _tiles():
    b = open(H.OURS, "rb").read(); A = H.parse(b)
    out = {}
    for cid, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != 0x20153:
            continue
        try:
            t = H.terr(r)
        except Exception:
            continue
        if len(t) != 2:
            continue
        s, e = H.emb_span(r)
        lib = ilb.read(bytes(r[s:e]))
        rec = lib.images[0].primary
        w, h, rows = ilb.decode_record(lib, rec)
        a = np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)
        clear = (H.u32(r, 1) or 0) >> 16 == 0x5A1B
        key = ("C" if clear else t[0])
        out.setdefault(key, []).append(a)
    return out


_T = None
_HT = None


def tiles():
    global _T
    if _T is None:
        _T = _tiles()
    return _T


def hextrans(path=None):
    global _HT
    if _HT is None or path:
        lib = ilb.read(open(path or os.path.join(GD, "Images", "HEXTRANS.ILB"), "rb").read())
        d = {}
        for im in lib.images:
            w, h, rows = ilb.decode_record(lib, im.primary)
            d[im.id] = np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)
        if path:
            return d
        _HT = d
    return _HT


def code(c):
    return {"S": 0xE, "C": 0xE, "X": 0xB, "W": 0, "I": 6, "L": 9, "A": 0xA, "D": 0xC, "J": 0xD}.get(c, None) \
        if not c.isdigit() else int(c)


def vanilla_rule(ebp, edi, bl, rnd=0):
    """vanilla UpdateTransition tail from 0x5579AA97 (ebp own, edi neighbour) -> (id or None, displaced)"""
    if ebp == edi or ebp < 0 or edi < 0 or edi in (8, 7, 0xF) or ebp == 0xF:
        return None, False
    if ebp == 9:
        if edi in (0xA, 0xD):
            return 0xB6 + bl + 3 * rnd, False
        if edi in (8, 7):
            return None, False
        return 0x93 + bl, True
    if edi == 9:
        if ebp in (0xA, 0xD):
            return 0xB6 + bl + 3 * rnd, False
        if ebp in (8, 7):
            return None, False
        return 0x90 + bl, False
    if ebp == 0xD:
        return (0xD0 + bl, False) if edi == 0xA else (0xD9 + bl, True)
    if edi == 0xD:
        return (0xD3 + bl, True) if ebp == 0xA else (0xD6 + bl, False)
    if ebp == 0xA:
        return 0xA3 + bl, True
    if edi == 0xA:
        return 0xA0 + bl, False
    if edi in (0, 6):
        return None, False
    if ebp == 6:
        return (0x60 + bl, False) if edi == 0 else ((edi << 4) + 3 + bl, True)
    if ebp == 0:
        return 3 + bl, True
    return ((ebp << 4) + 6 + bl + 3 * rnd) & 0xFF, False


def zig_rule(ebp, edi, bl, rnd=0):
    """block B (Ziggurat v3) in front of the vanilla rule"""
    sky = (0xE, 0xB)
    if edi in (0, 6):
        if ebp in sky:
            return None, False
    elif ebp == 0xA:
        if edi == 0xE:
            return 0xE0 + bl, True
        if edi == 0xB:
            return 0xB0 + bl, True
    elif edi == 0xA:
        if ebp == 0xE:
            return 0xE3 + bl, True
        if ebp == 0xB:
            return 0xB3 + bl, True
    elif ebp in sky:
        if 0 <= edi <= 0xF and (LAND >> edi) & 1:
            return 0xE9 + bl, True
    elif edi in sky:
        if 0 <= ebp <= 0xF and (LAND >> ebp) & 1:
            return 0xE6 + bl, True
    e2 = 0xA if ebp in sky else ebp
    d2 = 0xA if edi in sky else edi
    return vanilla_rule(e2, d2, bl, rnd)


def cliff_draws(terr, x, Y, getT, land=LAND):
    """block A+0x40: (id) list a Sky/Chasm hex at (x, Y) draws over itself"""
    t = terr
    if t not in (0xB, 0xE):
        return []
    base = 0x80 if t == 0xB else 0
    out = []
    for (dx, dy), subs in CLIFF:
        n = getT(x + dx, Y + dy)
        if n is None or not (0 <= n <= 0xF and (land >> n) & 1):
            continue
        var = ((2 * (x + dx) + (Y + dy) // 2) % 3) * 0x20
        for wid, req in subs:
            ok = all(getT(x + rx, Y + ry) in (0xB, 0xE) for rx, ry in req)
            if ok:
                out.append(wid + base + var)
    return out


def render(grid, rule=zig_rule, ht=None, cliffs=True, extra=None, scale=3, land=LAND):
    """grid: list of strings (rows), each char a terrain; returns PIL image (sky overlay not simulated)"""
    from PIL import Image
    ht = ht or hextrans()
    T = tiles()
    rows, cols = len(grid), len(grid[0])
    Wp, Hp = cols * 32 + 32, rows * 32 + 48
    img = Image.new("RGBA", (Wp, Hp), (0, 0, 0, 255))
    ox, oy = 8, 16

    def cell(x, Y):
        if x < 0 or x >= cols or Y < 0 or (Y - (x & 1)) % 2:
            return None
        y = (Y - (x & 1)) // 2
        if y >= rows:
            return None
        return grid[y][x]

    def getT(x, Y):
        c = cell(x, Y)
        return None if c is None else code(c)

    def org(x, Y):
        return ox + 32 * x, oy + 16 * Y
    for y in range(rows):
        for x in range(cols):
            c = grid[y][x]
            key = c if c == "C" else code(c)
            lst = T.get(key)
            if not lst:
                continue
            a = lst[(x * 7 + y * 3) % len(lst)]
            img.alpha_composite(Image.fromarray(a, "RGBA"), org(x, 2 * y + (x & 1)))
    draws = []
    for y in range(rows):
        for x in range(cols):
            Y = 2 * y + (x & 1)
            me = code(grid[y][x])
            for bl, (dx, dy) in enumerate(DIRS):
                n = getT(x + dx, Y + dy)
                if n is None:
                    continue
                cme, cn = grid[y][x], cell(x + dx, Y + dy)
                tid, disp = rule(me, n, bl, (x + y) % 3) if extra is None else extra(cme, cn, me, n, bl, (x + y) % 3, rule)
                if tid is None or tid not in ht:
                    continue
                px, py = org(x, Y)
                px, py = px - 6, py - 9
                if disp:
                    px, py = px + DISP[bl][0], py + DISP[bl][1]
                draws.append((Y, x, 0, tid, px, py))
            if cliffs:
                for tid in cliff_draws(me, x, Y, getT, land):
                    if tid in ht:
                        px, py = org(x, Y)
                        draws.append((Y, x, 1, tid, px, py))
    for Y, x, k, tid, px, py in sorted(draws):
        img.alpha_composite(Image.fromarray(ht[tid], "RGBA"), (max(0, px), max(0, py)) if px >= 0 and py >= 0 else (0, 0)) \
            if px >= 0 and py >= 0 else _paste_clip(img, ht[tid], px, py)
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def _paste_clip(img, a, px, py):
    from PIL import Image
    h, w = a.shape[:2]
    x0, y0 = max(0, -px), max(0, -py)
    if x0 >= w or y0 >= h:
        return
    img.alpha_composite(Image.fromarray(np.ascontiguousarray(a[y0:, x0:]), "RGBA"), (px + x0, py + y0))


SAMPLE = [
    "SSSSSSSSSSSS",
    "SS111SSXXXSS",
    "S11111SXXXXS",
    "SS1111SXX5XS",
    "SSS11SSXXXXS",
    "SSSSSSSSSSSS",
    "CCCCSSSLLLSS",
    "CC33CSSLLLSS",
    "CCCCSSXX44XS",
    "SSSSSWWWSSSS",
]



# ---- proposed rule (2026-11-06) -----------------------------------------------------------------------------------
LAND2 = 0x33BE                # + earth 7, rock 8, lava 9, cave ice 0xD count as 'land' next to Sky/Chasm


def new_rule(cme, cn, me, n, bl, rnd, base_rule=zig_rule):
    import sky_transitions_art as ST
    skyf = (0xE, 0xB)
    island = lambda t: 0 <= t <= 0xF and (LAND2 >> t) & 1
    if me in skyf and n in skyf:
        a = "X" if me == 0xB else ("C" if cme == "C" else "S")
        b = "X" if n == 0xB else ("C" if cn == "C" else "S")
        return (ST.BLEND[(a, b)] + bl, False) if a != b else (None, False)
    if me == 0xB and island(n):
        return ST.CHASM_LIP_LOW_CHASM + bl, True
    if n == 0xB and island(me):
        return ST.CHASM_LIP_LOW_LAND + bl, True
    if me == 0xE and island(n):
        return 0xE9 + bl, True
    if n == 0xE and island(me):
        return 0xE6 + bl, True
    return base_rule(me, n, bl, rnd)


def preview_new(out):
    import sky_transitions_art as ST
    ht = dict(hextrans())
    ht.update(ST.all_images(GD, ht))
    ht.update(ST.chasm_cliffs({i: a for i, a in hextrans().items() if 0x180 <= i <= 0x1C7}))
    render(SAMPLE).save(os.path.join(out, "trans_current.png"))
    render(SAMPLE, ht=ht, extra=new_rule, land=LAND2).save(os.path.join(out, "trans_new.png"))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    preview_new(out)
    print("written")
