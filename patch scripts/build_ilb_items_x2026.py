#!/usr/bin/env python3
"""build_ilb_items_x2026.py - generate Images\\Items\\I_x2026.ilb

A fresh item-graphic library with 12 procedurally painted icons for each of
the six hero-inventory slots (head, body, weapon, shield, ring, use), 72
icons total.  The library is data only - no game items reference it.

The ILB mirrors the layout of I_x2025.ilb exactly: v4.0, no palettes,
every image a 41x42 RLESprite16 (type 17, InfoByte 3, drawMode 256,
blend 0, RGB565, transparent colour 0x4D2B = 19755, clip_x 0).

Icons are painted at 4x resolution with gradient/rim shading, downsampled
(premultiplied Lanczos) and given a 1-px dark outline, then RLE-encoded
with the same encoder that round-trips the game's own data bit-for-bit.

usage:
  py build_ilb_items_x2026.py                 write Images\\Items\\I_x2026.ilb (+ preview png)
  py build_ilb_items_x2026.py --out X.ilb     write elsewhere
  py build_ilb_items_x2026.py --preview P.png write the 3x contact sheet here
  py build_ilb_items_x2026.py --force         overwrite an existing output
"""
import os, sys, math, struct, argparse
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "old modding tools", "research"))
import ilbcodec  # noqa: E402  (lossless reader/writer, 689/689 game ILBs round-trip)

S = 4                       # supersampling factor
BW, BH = 41, 42             # every AoW1 item icon is 41x42
W, H = BW * S, BH * S
TRANSP = 19755              # 0x4D2B - the transparent RGB565 value used by all item ILBs
PIXFMT = 0x56509310         # RGB565
SOMEID = 0x0040F000

# ----------------------------------------------------------------------------
# palettes  (light, mid, dark)
STEEL   = ((238, 242, 250), (158, 166, 182), (62, 68, 86))
SILVER  = ((252, 252, 255), (196, 200, 214), (92, 96, 118))
IRON    = ((150, 150, 164), (86, 86, 100), (28, 28, 38))
BLACK   = ((112, 108, 128), (52, 50, 66), (12, 11, 18))
GOLD    = ((255, 244, 160), (218, 168, 52), (118, 74, 14))
BRONZE  = ((232, 178, 112), (166, 106, 50), (78, 44, 14))
BRASS   = ((250, 225, 140), (195, 150, 60), (95, 65, 18))
WOOD    = ((196, 146, 90), (128, 82, 42), (58, 34, 14))
DARKWOOD= ((150, 100, 60), (90, 54, 26), (38, 20, 8))
LEATHER = ((170, 118, 72), (112, 70, 36), (50, 28, 12))
BONE    = ((248, 244, 222), (204, 194, 162), (112, 102, 70))
ICE     = ((242, 252, 255), (150, 206, 242), (52, 112, 176))
RUBY    = (215, 30, 45)
SAPPH   = (40, 80, 230)
EMER    = (40, 190, 90)
AMET    = (170, 60, 220)
TOPAZ   = (255, 170, 40)
DIAM    = (235, 245, 255)
DARK_EYE= (16, 12, 18)


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def rgba(c):
    return tuple(c) + (255,) if len(c) == 3 else tuple(c)


def star_pts(cx, cy, r, n=5, inner=0.45, rot=-90):
    pts = []
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + i * 180.0 / n)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def leaf_pts(cx, cy, length, width, angle_deg, n=14):
    """Pointed-ellipse leaf centred at (cx,cy), long axis along angle."""
    a = math.radians(angle_deg); ca, sa = math.cos(a), math.sin(a)
    top, bot = [], []
    for i in range(n + 1):
        u = i / n
        x = (u - 0.5) * length
        y = -width / 2 * math.sin(math.pi * u)
        top.append((x, y)); bot.append((x, -y))
    pts = top + bot[::-1]
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]


def rot(pts, deg, cx=20.5, cy=21.0):
    """Rotate base-grid points about (cx,cy); positive = clockwise on screen."""
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def local(pts, deg, cx=20.5, cy=21.0):
    """Points given relative to the icon centre, then rotated."""
    return rot([(cx + x, cy + y) for x, y in pts], deg, cx, cy)


def lin_grad(bb, angle):
    """Canvas-size L image: 0 -> 255 across bbox bb along screen angle (0=L->R, 90=T->B)."""
    x0, y0, x1, y1 = bb
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    n = int(math.hypot(bw, bh) * 1.02) + 6
    g = Image.linear_gradient('L').rotate(90).resize((n, n), Image.BILINEAR)
    g = g.rotate(-angle, resample=Image.BILINEAR)
    ox, oy = (n - bw) // 2, (n - bh) // 2
    g = g.crop((ox, oy, ox + bw, oy + bh))
    out = Image.new('L', (W, H), 0)
    out.paste(g, (x0, y0))
    return out


def rad_grad(cx, cy, r):
    """Canvas-size L image: 0 at (cx,cy) -> 255 at radius r (and beyond)."""
    d = max(2, int(2 * r))
    g = Image.radial_gradient('L').resize((d, d), Image.BILINEAR)
    out = Image.new('L', (W, H), 255)
    out.paste(g, (int(cx - r), int(cy - r)))
    return out


def shift(m, dx, dy):
    out = Image.new('L', (W, H), 0)
    out.paste(m, (int(round(dx)), int(round(dy))))
    return out


class C:
    """A 4x supersampled RGBA canvas with painterly helpers (coords in 41x42 units)."""

    def __init__(self):
        self.im = Image.new('RGBA', (W, H), (0, 0, 0, 0))

    # --- masks ---------------------------------------------------------
    def mpoly(self, pts):
        m = Image.new('L', (W, H), 0)
        ImageDraw.Draw(m).polygon([(x * S, y * S) for x, y in pts], fill=255)
        return m

    def mell(self, x0, y0, x1, y1):
        m = Image.new('L', (W, H), 0)
        ImageDraw.Draw(m).ellipse((x0 * S, y0 * S, x1 * S, y1 * S), fill=255)
        return m

    def mrect(self, x0, y0, x1, y1):
        return self.mpoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    def mline(self, pts, w):
        m = Image.new('L', (W, H), 0)
        ImageDraw.Draw(m).line([(x * S, y * S) for x, y in pts], fill=255,
                               width=max(1, int(w * S)), joint='curve')
        return m

    @staticmethod
    def union(*ms):
        out = ms[0]
        for m in ms[1:]:
            out = ImageChops.lighter(out, m)
        return out

    @staticmethod
    def sub(a, b):
        return ImageChops.subtract(a, b)

    @staticmethod
    def inter(a, b):
        return ImageChops.multiply(a, b)

    # --- fills ---------------------------------------------------------
    def fill(self, m, col):
        self.im.paste(rgba(col), (0, 0, W, H), m)

    def gfill(self, m, c1, c2, angle=45, mid=None):
        bb = m.getbbox()
        if not bb:
            return
        g = lin_grad(bb, angle)
        self.im.paste(ImageOps.colorize(g, black=c1, white=c2, mid=mid), (0, 0), m)

    def rfill(self, m, c_center, c_edge, cx, cy, r, mid=None):
        g = rad_grad(cx * S, cy * S, r * S)
        self.im.paste(ImageOps.colorize(g, black=c_center, white=c_edge, mid=mid), (0, 0), m)

    def edge(self, m, dx, dy, col, strength=120, blur=0.5):
        """Tint the part of m not covered by m shifted by (dx,dy) - a directional rim."""
        band = self.sub(m, shift(m, dx * S, dy * S))
        if blur:
            band = band.filter(ImageFilter.GaussianBlur(blur * S))
        band = self.inter(band, m).point(lambda v: v * strength // 255)
        self.im.paste(rgba(col), (0, 0, W, H), band)

    def rim(self, m, col=(0, 0, 0), strength=100, width=1.0, blur=0.5):
        k = int(width * S) * 2 + 1
        band = self.sub(m, m.filter(ImageFilter.MinFilter(k)))
        if blur:
            band = band.filter(ImageFilter.GaussianBlur(blur * S))
        band = self.inter(band, m).point(lambda v: v * strength // 255)
        self.im.paste(rgba(col), (0, 0, W, H), band)

    def shade(self, m, ls=110, ds=130, w=1.3):
        self.edge(m, w, w, (255, 255, 255), ls)
        self.edge(m, -w, -w, (0, 0, 0), ds)

    def form(self, m, pal, angle=45, ls=110, ds=130, rimst=60, w=1.3):
        """Standard 'painted solid': 3-stop gradient + directional shading + soft rim."""
        self.gfill(m, pal[0], pal[2], angle, mid=pal[1])
        self.shade(m, ls, ds, w)
        if rimst:
            self.rim(m, (0, 0, 0), rimst, 0.8)

    # --- strokes / dots --------------------------------------------------
    def stroke(self, pts, col, w, closed=False):
        p = [(x * S, y * S) for x, y in pts]
        if closed:
            p.append(p[0])
        ImageDraw.Draw(self.im).line(p, fill=rgba(col), width=max(1, int(w * S)), joint='curve')

    def dot(self, x, y, r, col):
        ImageDraw.Draw(self.im).ellipse((int((x - r) * S), int((y - r) * S), int((x + r) * S), int((y + r) * S)),
                                        fill=rgba(col))

    def gem(self, x, y, r, col, ry=None, sparkle=True):
        ry = ry or r
        m = self.mell(x - r, y - ry, x + r, y + ry)
        light = mix(col, (255, 255, 255), 0.55)
        dark = mix(col, (0, 0, 0), 0.6)
        self.rfill(m, light, dark, x - r * 0.35, y - ry * 0.35, max(r, ry) * 1.7, mid=col)
        self.rim(m, (0, 0, 0), 110, 0.5, 0.3)
        if sparkle:
            self.dot(x - r * 0.38, y - ry * 0.4, max(0.45, r * 0.22), (255, 255, 255))

    def bezel(self, x, y, r, pal, ry=None, w=0.9):
        ry = ry or r
        ring = self.sub(self.mell(x - r - w, y - ry - w, x + r + w, y + ry + w),
                        self.mell(x - r, y - ry, x + r, y + ry))
        self.form(ring, pal, 45, 90, 110, 40, 0.6)

    def layer(self):
        return C()

    def paste_layer(self, lay, m):
        a = self.inter(lay.im.split()[3], m)
        self.im.paste(lay.im, (0, 0), a)

    def glow(self, m, col, radius=1.5, strength=140):
        g = m.filter(ImageFilter.GaussianBlur(radius * S)).point(lambda v: v * strength // 255)
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        lay.paste(rgba(col), (0, 0, W, H), g)
        self.im = Image.alpha_composite(lay, self.im)


# ----------------------------------------------------------------------------
# shared part-drawers

def torso_mask(c, top=9, bot=35, shoulder=7, waist=10, neck=5.0, hip=9):
    pts = [(shoulder, top + 2), (shoulder + 3, top), (41 - shoulder - 3, top), (41 - shoulder, top + 2),
           (41 - shoulder - 1, top + 9), (41 - waist, top + 16), (41 - hip, bot),
           (hip, bot), (waist, top + 16), (shoulder + 1, top + 9)]
    m = c.mpoly(pts)
    neckm = c.mell(20.5 - neck, top - 4, 20.5 + neck, top + 4)
    return c.sub(m, neckm)


def arm_holes(c, m, top=9):
    """Darken the shoulder/arm openings a little so the torso reads as a vest."""
    for x in (7.5, 33.5):
        hole = c.mell(x - 2.5, top + 1, x + 2.5, top + 9)
        c.fill(c.inter(hole, m), (0, 0, 0, 90))


def skull(c, cx, cy, s, eye=DARK_EYE):
    cr = c.mell(cx - 5.5 * s, cy - 7 * s, cx + 5.5 * s, cy + 4 * s)
    jaw = c.mpoly([(cx - 3.8 * s, cy + 1 * s), (cx + 3.8 * s, cy + 1 * s), (cx + 3.0 * s, cy + 6.5 * s),
                   (cx + 1.5 * s, cy + 7.5 * s), (cx - 1.5 * s, cy + 7.5 * s), (cx - 3.0 * s, cy + 6.5 * s)])
    m = c.union(cr, jaw)
    c.form(m, BONE, 55, 110, 120, 50)
    for ex in (-2.4, 2.4):
        e = c.mell(cx + ex * s - 1.7 * s, cy - 3.2 * s, cx + ex * s + 1.7 * s, cy + 0.2 * s)
        c.fill(e, eye)
        c.rim(e, (0, 0, 0), 120, 0.3, 0.2)
    c.fill(c.mpoly([(cx - 0.9 * s, cy + 1.2 * s), (cx + 0.9 * s, cy + 1.2 * s), (cx, cy + 3.2 * s)]), eye)
    for i in range(-2, 3):
        c.stroke([(cx + i * 1.3 * s, cy + 4.6 * s), (cx + i * 1.3 * s, cy + 7.2 * s)], (90, 80, 55), 0.35 * s)
    c.stroke([(cx - 3.2 * s, cy + 4.6 * s), (cx + 3.2 * s, cy + 4.6 * s)], (90, 80, 55), 0.35 * s)
    return m


def flame(c, base_x, base_y, h, w, lean=0.0, cols=((255, 245, 150), (255, 150, 30), (200, 40, 10))):
    """A tongue of fire rising from (base_x, base_y)."""
    pts = [(base_x - w / 2, base_y), (base_x - w * 0.55, base_y - h * 0.35), (base_x - w * 0.15 + lean * 0.5, base_y - h * 0.7),
           (base_x + lean, base_y - h), (base_x + w * 0.35 + lean * 0.5, base_y - h * 0.6), (base_x + w * 0.55, base_y - h * 0.3),
           (base_x + w / 2, base_y)]
    m = c.mpoly(pts)
    c.gfill(m, cols[0], cols[2], 90, mid=cols[1])
    c.rim(m, cols[2], 80, 0.5, 0.3)
    inner = c.mpoly([(base_x - w * 0.22, base_y), (base_x - w * 0.1 + lean * 0.4, base_y - h * 0.45),
                     (base_x + lean * 0.7, base_y - h * 0.68), (base_x + w * 0.18 + lean * 0.4, base_y - h * 0.4),
                     (base_x + w * 0.22, base_y)])
    c.gfill(inner, (255, 255, 220), cols[0], 90)
    return m


def scales(c, m, pal, step_x=3.0, step_y=2.2, r=1.7, x0=6, y0=8, x1=36, y1=38):
    lay = c.layer()
    row = 0
    y = y0
    while y < y1:
        x = x0 + (step_x / 2 if row % 2 else 0)
        while x < x1:
            sm = lay.mell(x - r, y - r * 0.8, x + r, y + r * 1.1)
            lay.gfill(sm, pal[0], pal[2], 80, mid=pal[1])
            lay.rim(sm, pal[2], 140, 0.45, 0.25)
            x += step_x
        y += step_y; row += 1
    c.paste_layer(lay, m)


def chain(c, m, light, dark, step=2.0, r=0.85, x0=6, y0=8, x1=36, y1=38):
    lay = c.layer()
    row = 0
    y = y0
    while y < y1:
        x = x0 + (step / 2 if row % 2 else 0)
        while x < x1:
            ring = lay.sub(lay.mell(x - r, y - r, x + r, y + r), lay.mell(x - r * 0.45, y - r * 0.45, x + r * 0.45, y + r * 0.45))
            lay.fill(ring, dark)
            lay.edge(ring, 0.4, 0.4, light, 200, 0.15)
            x += step
        y += step * 0.85; row += 1
    c.paste_layer(lay, m)


def blade(c, pts_local, deg, pal, angle_off=-90):
    m = c.mpoly(local(pts_local, deg))
    c.gfill(m, pal[0], pal[2], deg + angle_off, mid=pal[1])
    c.shade(m, 90, 120, 0.7)
    c.rim(m, (0, 0, 0), 70, 0.5)
    return m


def shaft(c, y0, y1, hw, deg, pal, angle_off=-90):
    m = c.mpoly(local([(-hw, y0), (hw, y0), (hw, y1), (-hw, y1)], deg))
    c.gfill(m, pal[0], pal[2], deg + angle_off, mid=pal[1])
    c.rim(m, (0, 0, 0), 70, 0.5)
    return m


def grip_wrap(c, y0, y1, hw, deg, col, n=5):
    for i in range(n):
        y = y0 + (y1 - y0) * (i + 0.5) / n
        c.stroke(local([(-hw, y - 0.6), (hw, y + 0.6)], deg), col, 0.55)


def ring_band(c, cx, cy, rx, ry, th, pal, angle=60):
    outer = c.mell(cx - rx, cy - ry, cx + rx, cy + ry)
    inner = c.mell(cx - rx + th, cy - ry + th * 0.8, cx + rx - th, cy + ry - th * 1.2)
    band = c.sub(outer, inner)
    c.form(band, pal, angle, 120, 140, 50, 0.9)
    return band


def flask_glass(c, m, liquid_m, lcol, gcol=(200, 230, 245)):
    c.fill(m, mix(gcol, (60, 80, 100), 0.35))
    c.gfill(liquid_m, mix(lcol, (255, 255, 255), 0.35), mix(lcol, (0, 0, 0), 0.55), 30, mid=lcol)
    c.edge(m, 1.2, 1.2, (255, 255, 255), 150, 0.4)
    c.edge(m, -1.0, -1.0, (0, 0, 0), 120, 0.4)
    c.rim(m, (0, 0, 0), 70, 0.6)


# ----------------------------------------------------------------------------
# HEAD ------------------------------------------------------------------------

def head_greathelm(c):
    m = c.union(c.mell(11, 6, 30, 26), c.mrect(11, 16, 30, 36))
    c.form(m, STEEL, 15)
    c.stroke([(20.5, 7), (20.5, 19)], (255, 255, 255, 110), 1.0)
    slit = c.union(c.mrect(13, 20, 28, 23.5), c.mrect(19, 20, 22, 33))
    c.fill(slit, DARK_EYE)
    c.edge(slit, 0, -0.8, (0, 0, 0), 160, 0.2)
    for x in (13.5, 27.5):
        for y in (27, 30.5):
            c.dot(x, y, 0.75, (70, 72, 85)); c.dot(x - 0.25, y - 0.25, 0.35, (210, 215, 225))
    c.stroke([(11.5, 16.5), (29.5, 16.5)], (60, 62, 78, 150), 0.6)


def head_crown(c):
    pts = [(8, 24), (11, 13), (14.5, 22), (20.5, 9), (26.5, 22), (30, 13), (33, 24), (33, 35), (8, 35)]
    m = c.mpoly(pts)
    c.form(m, GOLD, 60)
    band = c.mrect(8.5, 28, 32.5, 34.5)
    c.gfill(band, (240, 200, 90), (140, 90, 20), 90)
    c.stroke([(8.5, 28), (32.5, 28)], (255, 250, 200), 0.6)
    c.stroke([(8.5, 34.5), (32.5, 34.5)], (110, 65, 10), 0.7)
    c.gem(20.5, 31.2, 2.4, RUBY)
    c.gem(13.5, 31.2, 1.6, SAPPH); c.gem(27.5, 31.2, 1.6, SAPPH)
    for x, y in ((11, 13), (20.5, 9.2), (30, 13)):
        c.gem(x, y + 1.5, 1.2, RUBY, sparkle=False)
    for x in (14.5, 26.5):
        c.dot(x, 22.5, 0.9, (250, 230, 130))


def head_horned(c):
    for sx in (1, -1):
        horn = [(12.5, 21), (9, 18.5), (6, 14), (4.6, 7.5), (6.5, 7), (9.5, 12.5), (13.5, 17.5)]
        if sx < 0:
            horn = [(41 - x, y) for x, y in horn]
        hm = c.mpoly(horn)
        c.form(hm, BONE, 45 if sx > 0 else -45, 110, 120, 60, 0.9)
    helm = c.union(c.mell(11, 11, 30, 31), c.mrect(11, 21, 30, 31.5))
    c.form(helm, BRONZE, 30)
    brim = c.mrect(11, 20.5, 30, 23.5)
    c.gfill(brim, (200, 140, 80), (110, 65, 25), 90)
    c.edge(brim, 0, 0.7, (255, 235, 200), 130, 0.2)
    for x in (13, 17, 24, 28):
        c.dot(x, 22, 0.6, (90, 50, 20))
    nasal = c.mrect(19.5, 21, 21.5, 33)
    c.gfill(nasal, (190, 130, 70), (90, 50, 20), 0)
    c.rim(nasal, (0, 0, 0), 90, 0.4)
    c.stroke([(20.5, 12), (20.5, 20)], (255, 230, 190, 110), 0.9)


def head_wizard_hat(c):
    brim = c.mell(5.5, 25.5, 35.5, 34.5)
    c.form(brim, ((120, 130, 235), (50, 55, 170), (18, 18, 80)), 60)
    cone = c.mpoly([(25, 4), (28.5, 8), (28, 28.5), (13, 28.5), (16.5, 14)])
    c.form(cone, ((115, 125, 240), (58, 62, 190), (22, 22, 95)), 30)
    c.stroke([(19, 27), (23.5, 13)], (150, 160, 255, 100), 1.0)
    band = c.mpoly([(13.5, 25), (28, 25), (28, 28.5), (13, 28.5)])
    c.gfill(band, (240, 200, 90), (130, 85, 20), 90)
    c.dot(20.5, 26.7, 0.8, (255, 240, 170))
    st = c.mpoly(star_pts(21.5, 18, 3.4))
    c.gfill(st, (255, 250, 180), (210, 150, 40), 90)
    c.dot(15.5, 11.5, 0.7, (255, 245, 200)); c.dot(26, 22, 0.6, (255, 245, 200))


def head_hood(c):
    hood = c.mpoly([(20.5, 4), (26, 6), (30, 10), (33, 20), (32.5, 35), (8.5, 35), (8, 20), (11, 10), (15, 6)])
    c.form(hood, ((100, 135, 78), (48, 78, 38), (16, 30, 12)), 40)
    face = c.mell(13, 13, 28, 34)
    c.rfill(face, (58, 48, 58), (8, 6, 10), 20.5, 30, 14)
    c.rim(face, (0, 0, 0), 150, 0.9)
    c.edge(hood, 0, 1.6, (200, 230, 170), 70, 0.4)
    c.stroke([(13, 12.5), (10.5, 20), (10, 30)], (30, 50, 22, 160), 0.9)
    c.stroke([(28, 12.5), (30.5, 20), (31, 30)], (30, 50, 22, 160), 0.9)
    c.dot(17.5, 22, 0.6, (200, 210, 190)); c.dot(23.5, 22, 0.6, (200, 210, 190))


def head_circlet(c):
    band = ring_band(c, 20.5, 22, 14.5, 9.5, 3.8, SILVER, 60)
    c.stroke([(8.5, 20), (13.5, 15.4), (20.5, 14.2), (27.5, 15.4), (32.5, 20)], (255, 255, 255, 150), 0.9)
    c.stroke([(9, 26), (14, 29.8), (20.5, 30.6), (27, 29.8), (32, 26)], (0, 0, 0, 80), 0.8)
    c.bezel(20.5, 30.2, 3.4, SILVER, 2.9, 1.1)
    c.gem(20.5, 30.2, 3.4, SAPPH, 2.9)
    for x in (12, 29):
        c.bezel(x, 28.2, 1.5, SILVER, 1.5, 0.6)
        c.gem(x, 28.2, 1.5, SAPPH, sparkle=False)
    for x, y in ((8.8, 23.5), (32.2, 23.5), (16, 29.6), (25, 29.6)):
        c.dot(x, y, 0.6, (255, 255, 255))


def head_skull(c):
    skull(c, 20.5, 19, 2.0)
    c.stroke([(15, 10), (17.5, 14), (16.5, 17)], (120, 110, 80), 0.5)
    c.stroke([(25.5, 9.5), (24.5, 13)], (120, 110, 80), 0.5)
    for ex in (15.7, 25.3):
        c.dot(ex, 15.5, 0.8, (200, 40, 40, 160))


def head_feathered_cap(c):
    plume = [(26, 23), (29, 18), (32, 12), (35, 6.5)]
    c.stroke(plume, (200, 45, 45), 2.6)
    c.stroke([(27, 21), (30.5, 15), (33.5, 9), (35.5, 6)], (255, 120, 110), 1.0)
    c.stroke(plume, (250, 210, 130), 0.5)
    brim = c.mell(5, 24.5, 36, 31)
    c.form(brim, ((90, 130, 60), (45, 75, 30), (16, 32, 10)), 60)
    cap = c.inter(c.mell(9, 11, 32, 31), c.mrect(0, 0, 41, 27.5))
    c.form(cap, ((130, 180, 90), (60, 105, 40), (22, 45, 14)), 30)
    band = c.inter(cap, c.mrect(0, 22.5, 41, 26))
    c.gfill(band, (110, 70, 35), (45, 25, 10), 90)
    c.stroke([(9.5, 22.7), (31.5, 22.7)], (150, 100, 55), 0.5)
    c.dot(25.5, 24.2, 0.9, (220, 175, 60))


def head_winged(c):
    for sx in (1, -1):
        wing = [(13, 17.5), (7, 12), (2.5, 13.5), (3.5, 18), (1.5, 22.5), (5.5, 23.5), (8.5, 27), (13, 25.5)]
        if sx < 0:
            wing = [(41 - x, y) for x, y in wing]
        wm = c.mpoly(wing)
        c.form(wm, ((255, 255, 255), (205, 208, 220), (100, 104, 125)), 45 if sx > 0 else 135, 90, 110, 50, 0.8)
        for (a, b) in (((12, 19), (4, 14.5)), ((12, 21.5), (3.5, 19)), ((12, 24), (6, 23.5))):
            if sx < 0:
                a = (41 - a[0], a[1]); b = (41 - b[0], b[1])
            c.stroke([a, b], (120, 125, 150), 0.45)
    helm = c.union(c.mell(12, 8, 29, 28), c.mrect(12, 18, 29, 31))
    c.form(helm, GOLD, 25)
    c.stroke([(20.5, 9), (20.5, 18)], (255, 255, 230, 120), 1.0)
    vis = c.mrect(14, 22, 27, 25.5)
    c.fill(vis, DARK_EYE)
    nasal = c.mrect(19.6, 22, 21.4, 30.5)
    c.gfill(nasal, (240, 200, 90), (130, 85, 20), 0)
    c.stroke([(12.5, 21), (28.5, 21)], (120, 80, 20, 170), 0.6)


def head_spiked(c):
    for pts in ([(20.5, 2), (17.2, 12), (23.8, 12)], [(7, 9), (12.5, 16), (10.5, 20.5)], [(34, 9), (28.5, 16), (30.5, 20.5)],
                [(11.5, 5.5), (15, 13), (12, 15)], [(29.5, 5.5), (26, 13), (29, 15)]):
        sm = c.mpoly(pts)
        c.form(sm, BLACK, 60, 90, 120, 60, 0.7)
    helm = c.union(c.mell(11, 8, 30, 28), c.mrect(11, 18, 30, 34))
    c.form(helm, BLACK, 20)
    vis = c.mrect(12.5, 21, 28.5, 24.5)
    c.fill(vis, (8, 6, 10))
    for ex in (16.5, 24.5):
        gm = c.mell(ex - 1.8, 21.6, ex + 1.8, 24.0)
        c.rfill(gm, (255, 230, 150), (170, 20, 10), ex, 22.8, 2.2, mid=(255, 90, 40))
    c.stroke([(20.5, 24.5), (20.5, 33)], (18, 16, 24), 1.6)
    for x in (13.5, 27.5):
        c.dot(x, 29, 0.7, (80, 78, 95))


def head_tiara(c):
    crys = [((20.5, 6), (15.8, 27), (25.2, 27)), ((12.5, 12), (8.8, 26.5), (16.2, 26.5)),
            ((28.5, 12), (24.8, 26.5), (32.2, 26.5)), ((6.5, 19), (5, 26), (10.5, 26)), ((34.5, 19), (30.5, 26), (36, 26))]
    for tip, a, b in crys:
        m = c.mpoly([tip, a, b])
        c.gfill(m, (245, 255, 255), (70, 150, 210), 90, mid=(160, 215, 245))
        half = c.mpoly([tip, ((a[0] + b[0]) / 2, a[1]), b])
        c.fill(half, (50, 120, 190, 90))
        c.rim(m, (30, 90, 150), 120, 0.5, 0.3)
        c.stroke([tip, ((tip[0] + a[0]) / 2, (tip[1] + a[1]) / 2 + 2)], (255, 255, 255, 170), 0.6)
    band = ring_band(c, 20.5, 27, 14.5, 7.5, 3.6, ICE, 60)
    c.stroke([(8.5, 25), (14, 21), (20.5, 20), (27, 21), (32.5, 25)], (255, 255, 255, 150), 0.8)
    c.bezel(20.5, 33.2, 2.8, ICE, 2.3, 1.0)
    c.gem(20.5, 33.2, 2.8, (140, 220, 255), 2.3)
    for x in (12.5, 28.5):
        c.gem(x, 32, 1.2, (140, 220, 255), sparkle=False)


def head_laurel(c):
    ring_band(c, 20.5, 22, 13, 9.5, 3.4, GOLD, 60)
    n = 14
    for i in range(n):
        t = 2 * math.pi * (i + 0.5) / n
        x = 20.5 + 13 * math.cos(t); y = 22 + 9.5 * math.sin(t)
        ang = math.degrees(math.atan2(9.5 * math.cos(t), -13 * math.sin(t))) + (25 if math.cos(t) < 0 else -25)
        pal = ((160, 210, 90), (78, 138, 48), (25, 62, 18)) if i % 2 else ((135, 190, 78), (60, 118, 38), (18, 50, 14))
        lm = c.mpoly(leaf_pts(x, y, 8.5, 4.6, ang))
        c.gfill(lm, pal[0], pal[2], ang + 90, mid=pal[1])
        c.rim(lm, (10, 30, 8), 130, 0.5, 0.3)
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        c.stroke([(x - 3.4 * ca, y - 3.4 * sa), (x + 3.4 * ca, y + 3.4 * sa)], (210, 240, 150), 0.5)
    for (x, y) in ((20.5, 32.2), (10, 28.5), (31, 28.5), (14.5, 12.5), (26.5, 12.5)):
        c.dot(x, y, 1.2, (200, 40, 40)); c.dot(x - 0.4, y - 0.4, 0.45, (255, 170, 170))


# ----------------------------------------------------------------------------
# BODY ------------------------------------------------------------------------

def body_plate(c):
    m = torso_mask(c)
    c.form(m, STEEL, 40)
    for x in (15.5, 25.5):
        pec = c.mell(x - 4.5, 13, x + 4.5, 22)
        c.edge(c.inter(pec, m), 1.0, 1.0, (255, 255, 255), 110, 0.6)
    c.stroke([(20.5, 12), (20.5, 26)], (70, 76, 95, 190), 0.8)
    for y in (27.5, 30.5, 33.5):
        c.stroke([(10, y), (31, y)], (55, 60, 78, 200), 0.7)
        c.stroke([(10, y - 0.8), (31, y - 0.8)], (230, 235, 245, 120), 0.5)
    c.stroke([(9.5, 26.2), (31.5, 26.2)], (255, 255, 255, 120), 0.6)
    arm_holes(c, m)
    for x in (12.5, 28.5):
        c.dot(x, 11.5, 0.6, (60, 64, 80))


def body_chain(c):
    m = torso_mask(c)
    c.fill(m, (98, 100, 115))
    chain(c, m, (190, 194, 210), (48, 50, 62))
    c.shade(m, 90, 150, 1.4)
    c.rim(m, (0, 0, 0), 80, 0.9)
    coll = c.sub(c.mell(14, 4.5, 27, 14.5), c.mell(15.5, 5, 25.5, 13))
    c.form(c.inter(coll, m), LEATHER, 60, 80, 100, 40, 0.5)
    arm_holes(c, m)


def body_leather(c):
    m = torso_mask(c)
    c.form(m, LEATHER, 35)
    for x in (13, 28):
        pts = [(x, 12 + i * 1.6) for i in range(9)]
        for i in range(0, len(pts) - 1, 2):
            c.stroke([pts[i], pts[i + 1]], (60, 35, 15), 0.45)
    for i in range(4):
        y = 13.5 + i * 3
        c.stroke([(17.5, y), (23.5, y + 2)], (230, 200, 150), 0.5)
        c.stroke([(23.5, y), (17.5, y + 2)], (230, 200, 150), 0.5)
    for x in (17.5, 23.5):
        for i in range(5):
            c.dot(x, 13.5 + i * 3, 0.5, (40, 22, 8))
    belt = c.inter(c.mrect(8, 26, 33, 29.5), m)
    c.gfill(belt, (90, 55, 25), (35, 18, 6), 90)
    buck = c.mrect(18.5, 25.3, 22.5, 30.2)
    c.form(buck, BRASS, 45, 90, 100, 40, 0.5)
    c.fill(c.mrect(19.6, 26.4, 21.4, 29.1), (60, 38, 15))
    arm_holes(c, m)


def body_robe(c):
    m = torso_mask(c, top=8, bot=38, shoulder=5, waist=9, neck=4.5, hip=7)
    c.form(m, ((175, 115, 225), (95, 42, 160), (36, 10, 72)), 35)
    for x, y in ((12, 14), (29, 14), (16, 22), (25, 22), (13, 30), (28, 30)):
        c.stroke([(x, y), (x + 0.5, y + 6)], (60, 20, 110, 150), 0.9)
    trim = ((255, 240, 170), (215, 165, 50), (120, 75, 15))
    hem = c.inter(c.mrect(0, 35.5, 41, 38), m)
    c.gfill(hem, trim[0], trim[2], 90, mid=trim[1])
    coll = c.inter(c.sub(c.mell(14.5, 3.5, 26.5, 13.5), c.mell(16, 4, 25, 12)), m)
    c.gfill(coll, trim[0], trim[2], 60, mid=trim[1])
    for x in (5.5, 35.5):
        cuff = c.inter(c.mrect(x - 2.5, 14, x + 2.5, 17), m)
        c.gfill(cuff, trim[0], trim[2], 90, mid=trim[1])
    st = c.mpoly(star_pts(20.5, 23, 4.2))
    c.gfill(st, trim[0], trim[2], 90, mid=trim[1])
    c.gem(20.5, 23, 1.3, AMET, sparkle=False)


def body_scale(c):
    m = torso_mask(c)
    c.fill(m, (40, 70, 35))
    scales(c, m, ((150, 200, 100), (60, 120, 50), (18, 50, 20)))
    c.shade(m, 80, 150, 1.4)
    c.rim(m, (0, 0, 0), 80, 0.9)
    coll = c.inter(c.sub(c.mell(14, 4.5, 27, 14.5), c.mell(15.5, 5, 25.5, 13)), m)
    c.form(coll, BRONZE, 60, 80, 100, 40, 0.5)
    for x in (8, 33):
        pad = c.inter(c.mell(x - 3.5, 9, x + 3.5, 16), m)
        c.form(pad, BRONZE, 45, 80, 100, 40, 0.5)


def body_gold(c):
    m = torso_mask(c)
    c.form(m, GOLD, 40)
    sun = c.mell(15.5, 14.5, 25.5, 24.5)
    c.rfill(sun, (255, 250, 200), (190, 130, 30), 20.5, 19.5, 5.5)
    for i in range(12):
        a = math.radians(i * 30)
        c.stroke([(20.5 + 5.2 * math.cos(a), 19.5 + 5.2 * math.sin(a)), (20.5 + 7.6 * math.cos(a), 19.5 + 7.6 * math.sin(a))],
                 (255, 245, 180), 0.8)
    c.gem(20.5, 19.5, 2.2, RUBY)
    for y in (28, 31, 34):
        c.stroke([(10, y), (31, y)], (120, 75, 15, 200), 0.6)
    c.stroke([(9.5, 26.5), (31.5, 26.5)], (255, 255, 230, 140), 0.6)
    arm_holes(c, m)


def body_bone(c):
    m = torso_mask(c)
    c.form(m, ((88, 66, 62), (46, 32, 30), (14, 8, 8)), 40)
    for i in range(5):
        y = 14 + i * 4.2
        for sx in (1, -1):
            pts = [(20.5, y), (20.5 + sx * 4, y + 0.6), (20.5 + sx * 8, y + 1.8), (20.5 + sx * 10.5, y + 3.6)]
            rm = c.mline(pts, 1.6)
            c.gfill(c.inter(rm, m), BONE[0], BONE[2], 90, mid=BONE[1])
            c.rim(c.inter(rm, m), (0, 0, 0), 80, 0.3, 0.2)
    sp = c.inter(c.mrect(19.3, 12, 21.7, 34), m)
    c.gfill(sp, BONE[0], BONE[2], 0, mid=BONE[1])
    c.rim(sp, (0, 0, 0), 80, 0.3, 0.2)
    for x in (8.5, 32.5):
        sk = c.inter(c.mell(x - 3.5, 9, x + 3.5, 16), m)
        c.form(sk, BONE, 45, 90, 100, 50, 0.5)
    arm_holes(c, m)


def body_fire(c):
    m = torso_mask(c)
    c.form(m, ((255, 130, 70), (185, 45, 22), (72, 10, 5)), 40)
    for y in (27.5, 31, 34.5):
        c.stroke([(10, y), (31, y)], (60, 8, 4, 200), 0.6)
    for x, sx in ((8.5, -1), (32.5, 1)):
        for k, (dx, h, w) in enumerate(((0, 9, 4), (sx * 2.2, 6, 3), (-sx * 2.0, 5.5, 2.6))):
            flame(c, x + dx, 13.5, h, w, sx * 0.8)
    for k in range(3):
        flame(c, 14 + k * 6.5, 26, 6 - abs(k - 1) * 1.5, 3, (k - 1) * 0.8)
    gm = c.mell(18.2, 16.5, 22.8, 21.5)
    c.rfill(gm, (255, 255, 200), (200, 60, 10), 20.5, 19, 2.5, mid=(255, 170, 40))
    c.rim(gm, (80, 10, 0), 120, 0.4, 0.2)
    arm_holes(c, m)


def body_ice(c):
    m = torso_mask(c)
    c.form(m, ((190, 230, 252), (95, 165, 222), (28, 80, 140)), 40)
    facets = [([(20.5, 13), (9, 25), (20.5, 27)], (150, 210, 245, 110)), ([(20.5, 13), (32, 25), (20.5, 27)], (30, 95, 160, 120)),
              ([(8, 35), (20.5, 27), (20.5, 35)], (45, 115, 180, 110)), ([(33, 35), (20.5, 27), (20.5, 35)], (165, 220, 250, 110)),
              ([(6, 9), (20.5, 13), (9, 25), (6, 20)], (175, 225, 250, 110)), ([(35, 9), (20.5, 13), (32, 25), (35, 20)], (22, 80, 140, 120))]
    for pts_f, col in facets:
        c.fill(c.inter(c.mpoly(pts_f), m), col)
    for a, b in (((20.5, 13), (20.5, 35)), ((9, 25), (32, 25)), ((20.5, 13), (9, 25)), ((20.5, 13), (32, 25)),
                 ((20.5, 27), (8, 35)), ((20.5, 27), (33, 35))):
        c.stroke([a, b], (255, 255, 255, 150), 0.6)
    for x, sx in ((9, -1), (32, 1)):
        for tip, a, b in (((x + sx * 1.0, 4.5), (x - 3, 14), (x + 3, 14)), ((x + sx * 5.5, 8), (x + sx * 0.5, 14), (x + sx * 5, 15))):
            sm = c.mpoly([tip, a, b])
            c.gfill(sm, (245, 255, 255), (60, 140, 200), 90, mid=(150, 210, 245))
            c.rim(sm, (30, 90, 150), 110, 0.4, 0.25)
            c.stroke([tip, ((tip[0] + a[0]) / 2, (tip[1] + a[1]) / 2)], (255, 255, 255, 180), 0.5)
        pad = c.inter(c.mell(x - 4.5, 9, x + 4.5, 17), m)
        c.gfill(pad, (235, 250, 255), (90, 160, 215), 60)
        c.rim(pad, (30, 90, 150), 90, 0.5, 0.3)
    c.rim(m, (30, 90, 150), 90, 0.8)
    c.gem(20.5, 20, 2.2, (140, 220, 255))


def body_cloak(c):
    m = c.sub(c.mpoly([(20.5, 5), (26, 7.5), (30, 12), (33, 22), (35.5, 37.5), (5.5, 37.5), (8, 22), (11, 12), (15, 7.5)]),
              c.mell(16.5, 2, 24.5, 9.5))
    c.form(m, ((88, 88, 108), (40, 40, 52), (10, 10, 16)), 40)
    for x0, x1 in ((13, 10), (17, 16), (24, 25), (28, 31)):
        c.stroke([(x0, 12), (x1, 36)], (14, 14, 20, 170), 1.0)
        c.stroke([(x0 - 1.2, 12), (x1 - 1.2, 36)], (120, 120, 145, 70), 0.7)
    coll = c.inter(c.sub(c.mell(13.5, 3, 27.5, 13), c.mell(16.5, 2, 24.5, 9.5)), m)
    c.form(coll, ((110, 110, 132), (55, 55, 70), (18, 18, 26)), 60, 90, 110, 40, 0.5)
    c.bezel(20.5, 12.5, 1.9, GOLD, 1.9, 0.9)
    c.gem(20.5, 12.5, 1.9, RUBY)
    c.edge(m, 0, 1.5, (0, 0, 0), 150, 0.5)


def body_dragon(c):
    m = torso_mask(c)
    c.fill(m, (70, 15, 12))
    scales(c, m, ((240, 90, 60), (165, 30, 22), (60, 8, 6)), 3.6, 2.6, 2.1)
    c.shade(m, 80, 150, 1.4)
    c.rim(m, (0, 0, 0), 80, 0.9)
    for x, sx in ((8, -1), (33, 1)):
        pad = c.inter(c.mell(x - 3.8, 9, x + 3.8, 16.5), m)
        c.form(pad, ((150, 40, 30), (90, 18, 12), (30, 4, 2)), 45, 80, 100, 40, 0.5)
        for tip, a, b in (((x + sx * 3, 4.5), (x - 1.5, 10.5), (x + 2, 10.5)), ((x + sx * 6, 8), (x + sx * 1.5, 11), (x + sx * 4.5, 12.5))):
            sm = c.mpoly([tip, a, b])
            c.form(sm, BONE, 90, 90, 100, 60, 0.5)
    coll = c.inter(c.sub(c.mell(14, 4.5, 27, 14.5), c.mell(15.5, 5, 25.5, 13)), m)
    c.form(coll, ((150, 40, 30), (90, 18, 12), (30, 4, 2)), 60, 80, 100, 40, 0.5)


def body_mithril(c):
    m = torso_mask(c)
    c.form(m, ((255, 255, 255), (208, 214, 232), (110, 118, 150)), 40, 90, 110)
    lm = c.mpoly(leaf_pts(20.5, 21, 12, 6, 90))
    c.gfill(lm, (150, 200, 120), (40, 95, 60), 90, mid=(90, 150, 90))
    c.rim(lm, (30, 70, 40), 110, 0.4, 0.3)
    c.stroke([(20.5, 15.5), (20.5, 26.5)], (200, 240, 180), 0.45)
    for i in range(3):
        y = 17.5 + i * 3
        c.stroke([(20.5, y), (17.5, y + 2)], (200, 240, 180), 0.35)
        c.stroke([(20.5, y), (23.5, y + 2)], (200, 240, 180), 0.35)
    for (a, b) in (((10, 13), (16, 26)), ((31, 13), (25, 26)), ((10.5, 32), (16.5, 28)), ((30.5, 32), (24.5, 28))):
        c.stroke([a, b], (140, 150, 185, 150), 0.5)
    c.stroke([(9.5, 27), (31.5, 27)], (140, 150, 185, 150), 0.5)
    coll = c.inter(c.sub(c.mell(14.5, 4.5, 26.5, 14), c.mell(15.5, 5, 25.5, 13)), m)
    c.form(coll, SILVER, 60, 90, 110, 40, 0.5)
    arm_holes(c, m)


# ----------------------------------------------------------------------------
# WEAPON ----------------------------------------------------------------------

def weapon_longsword(c):
    d = -45
    shaft(c, 5.5, 13.5, 1.3, d, DARKWOOD)
    grip_wrap(c, 6, 13, 1.3, d, (40, 22, 8), 5)
    pm = c.mpoly(local([(-2.2, 13.5), (2.2, 13.5), (2.2, 16.5), (-2.2, 16.5)], d))
    c.form(pm, GOLD, d + 45, 90, 110, 50, 0.6)
    bm = blade(c, [(0, -19.5), (2.0, -16), (2.0, 3.2), (-2.0, 3.2), (-2.0, -16)], d, STEEL)
    c.stroke(local([(0, -15), (0, 1.5)], d), (95, 100, 120, 200), 0.7)
    c.stroke(local([(-1.4, -15), (-1.4, 1.5)], d), (255, 255, 255, 140), 0.5)
    gm = c.mpoly(local([(-6.5, 3.2), (6.5, 3.2), (6.5, 5.6), (-6.5, 5.6)], d))
    c.form(gm, GOLD, d + 45, 90, 110, 50, 0.6)
    c.gem(*local([(0, 4.4)], d)[0], 1.0, RUBY, sparkle=False)


def weapon_axe(c):
    d = -35
    shaft(c, -15, 17, 1.1, d, WOOD)
    grip_wrap(c, 9, 16, 1.1, d, (60, 36, 16), 4)
    for sx in (1, -1):
        pts = [(sx * 1.5, -13.5), (sx * 10.5, -16.5), (sx * 13.5, -8.5), (sx * 10.5, -0.5), (sx * 1.5, -3.5)]
        m = blade(c, pts, d, STEEL, -90 if sx > 0 else 90)
        c.stroke(local([(sx * 11, -14.5), (sx * 13, -8.5), (sx * 11, -2)], d), (255, 255, 255, 170), 0.6)
    sp = c.mpoly(local([(0, -21), (1.6, -15.5), (-1.6, -15.5)], d))
    c.form(sp, STEEL, d, 90, 110, 50, 0.5)
    band = c.mpoly(local([(-2.2, -3), (2.2, -3), (2.2, 0), (-2.2, 0)], d))
    c.form(band, IRON, d + 45, 90, 110, 50, 0.4)


def weapon_mace(c):
    d = -40
    shaft(c, -4, 17, 1.2, d, IRON)
    grip_wrap(c, 8, 16, 1.2, d, (40, 22, 8), 4)
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        tip = (7.8 * math.cos(a), -9 + 7.8 * math.sin(a))
        b1 = (4.2 * math.cos(a + 0.28), -9 + 4.2 * math.sin(a + 0.28))
        b2 = (4.2 * math.cos(a - 0.28), -9 + 4.2 * math.sin(a - 0.28))
        sm = c.mpoly(local([tip, b1, b2], d))
        c.form(sm, IRON, 45, 90, 110, 50, 0.4)
    cx, cy = local([(0, -9)], d)[0]
    ball = c.mell(cx - 5.2, cy - 5.2, cx + 5.2, cy + 5.2)
    c.rfill(ball, IRON[0], IRON[2], cx - 1.8, cy - 1.8, 6.5, mid=IRON[1])
    c.rim(ball, (0, 0, 0), 90, 0.6)
    band = c.mpoly(local([(-2.0, -3.5), (2.0, -3.5), (2.0, -1.5), (-2.0, -1.5)], d))
    c.form(band, BRASS, d + 45, 90, 110, 50, 0.4)


def weapon_spear(c):
    d = -45
    shaft(c, -9, 20, 0.9, d, WOOD)
    hm = blade(c, [(0, -21), (2.8, -14), (1.4, -8), (-1.4, -8), (-2.8, -14)], d, STEEL)
    c.stroke(local([(0, -19), (0, -9)], d), (90, 96, 115, 200), 0.6)
    c.stroke(local([(-0.9, -18), (-0.9, -9.5)], d), (255, 255, 255, 150), 0.45)
    band = c.mpoly(local([(-1.8, -8.5), (1.8, -8.5), (1.8, -5.5), (-1.8, -5.5)], d))
    c.form(band, BRASS, d + 45, 90, 110, 50, 0.4)
    for y in (-4, 1, 6):
        c.stroke(local([(-1.0, y), (1.0, y + 0.8)], d), (200, 40, 40), 0.6)


def weapon_bow(c):
    d = -35
    # string first (behind everything), then the arrow, then the limbs on top
    c.stroke(local([(-4, -20.5), (-4, 20.5)], d), (240, 238, 225), 0.8)
    c.stroke(local([(-4, 0.5), (-19, 0.5)], d), (165, 112, 60), 1.3)
    c.stroke(local([(-19, 0.5), (-23, 0.5)], d), (200, 205, 220), 2.0)
    for sy in (-1, 1):
        fm = c.mpoly(local([(-5, 0.5), (-10, 0.5), (-9, 0.5 + sy * 2.6), (-5.5, 0.5 + sy * 2.6)], d))
        c.form(fm, ((240, 90, 90), (200, 40, 40), (90, 10, 10)), d, 80, 100, 40, 0.3)
    arc = [(-4, -21), (1.5, -17), (5.5, -10), (7, 0), (5.5, 10), (1.5, 17), (-4, 21)]
    bm = c.mline(local(arc, d), 3.0)
    c.gfill(bm, WOOD[0], WOOD[2], d + 90, mid=WOOD[1])
    c.edge(bm, 0.7, 0.7, (255, 240, 200), 130, 0.3)
    c.rim(bm, (0, 0, 0), 90, 0.6)
    for y in (-14, 14):
        c.stroke(local([(-1.5, y - 1), (2.5, y + 1)], d), (60, 36, 16), 0.6)
    grip = c.mline(local([(6.5, -3.5), (6.5, 3.5)], d), 3.6)
    c.form(grip, LEATHER, d + 90, 80, 100, 50, 0.4)
    for y in (-1.8, 0.4, 2.6):
        c.stroke(local([(4.8, y), (8.2, y + 0.6)], d), (50, 28, 12), 0.5)


def weapon_dagger(c):
    d = -45
    shaft(c, 3.5, 11.5, 1.2, d, ((70, 60, 80), (38, 30, 46), (12, 8, 16)))
    grip_wrap(c, 4, 11, 1.2, d, (110, 90, 120), 4)
    pts = [(4.5, -15.5), (5.5, -10), (4.5, -5), (2.2, 0), (0.5, 3.2), (-1.5, 3.2), (-1.2, -2), (-0.4, -8), (1.5, -12.5)]
    blade(c, pts, d, STEEL)
    c.stroke(local([(1.5, -11), (0.6, -7), (0.8, -1)], d), (255, 255, 255, 170), 0.55)
    gm = c.mpoly(local([(-4, 3.2), (4, 3.2), (3, 5.3), (-3, 5.3)], d))
    c.form(gm, GOLD, d + 45, 90, 110, 50, 0.5)
    px, py = local([(0, 12.8)], d)[0]
    c.bezel(px, py, 1.4, GOLD, 1.4, 0.6)
    c.gem(px, py, 1.4, RUBY)


def weapon_hammer(c):
    d = -40
    shaft(c, -8, 18, 1.2, d, WOOD)
    grip_wrap(c, 10, 17, 1.2, d, (60, 36, 16), 4)
    for y in (-6.5, 0):
        band = c.mpoly(local([(-1.9, y), (1.9, y), (1.9, y + 2.2), (-1.9, y + 2.2)], d))
        c.form(band, IRON, d + 45, 80, 100, 50, 0.4)
    hm = c.mpoly(local([(-9, -16), (9, -16), (9, -8.5), (-9, -8.5)], d))
    c.form(hm, STEEL, d + 90, 100, 130, 60, 0.8)
    for sx in (1, -1):
        face = c.mpoly(local([(sx * 9, -16), (sx * 11.5, -14.5), (sx * 11.5, -10), (sx * 9, -8.5)], d))
        c.form(face, STEEL, d + 90 + sx * 30, 80, 130, 60, 0.5)
    c.stroke(local([(-8, -15), (8, -15)], d), (255, 255, 255, 150), 0.6)
    for x in (-5, 0, 5):
        px, py = local([(x, -12.2)], d)[0]
        c.dot(px, py, 0.7, (60, 64, 80)); c.dot(px - 0.25, py - 0.25, 0.3, (220, 225, 235))


def weapon_flaming(c):
    d = -45
    shaft(c, 5.5, 13.5, 1.3, d, BLACK)
    grip_wrap(c, 6, 13, 1.3, d, (120, 30, 10), 5)
    pm = c.mpoly(local([(-2.2, 13.5), (2.2, 13.5), (2.2, 16.5), (-2.2, 16.5)], d))
    c.form(pm, BRONZE, d + 45, 90, 110, 50, 0.6)
    fl = ((255, 235, 130), (235, 110, 25), (130, 25, 5))
    for k, (y, h, w) in enumerate(((-14, 6, 3.6), (-9, 7, 4), (-4, 6, 3.4), (1, 5, 3))):
        for sx in (1, -1):
            lay = c.layer()
            pts = [(sx * 1.5, y + 2), (sx * (1.5 + w * 0.8), y + 1), (sx * (2 + w), y - h * 0.6), (sx * (1.2 + w * 0.5), y - h),
                   (sx * 1.5, y - 2.5)]
            fm = lay.mpoly(local(pts, d))
            lay.gfill(fm, fl[0], fl[2], d + (-90 if sx > 0 else 90), mid=fl[1])
            c.im = Image.alpha_composite(c.im, lay.im)
    bm = blade(c, [(0, -19.5), (2.0, -16), (2.0, 3.2), (-2.0, 3.2), (-2.0, -16)], d, ((255, 225, 140), (225, 100, 30), (110, 20, 5)))
    c.stroke(local([(0, -15), (0, 1.5)], d), (255, 250, 200, 220), 0.8)
    gm = c.mpoly(local([(-6.5, 3.2), (6.5, 3.2), (6.5, 5.6), (-6.5, 5.6)], d))
    c.form(gm, BRONZE, d + 45, 90, 110, 50, 0.6)
    c.gem(*local([(0, 4.4)], d)[0], 1.0, TOPAZ, sparkle=False)


def weapon_frost(c):
    d = -45
    shaft(c, 5.5, 13.5, 1.3, d, ((90, 110, 150), (48, 60, 95), (14, 20, 40)))
    grip_wrap(c, 6, 13, 1.3, d, (190, 220, 245), 5)
    pm = c.mpoly(local([(-2.2, 13.5), (2.2, 13.5), (2.2, 16.5), (-2.2, 16.5)], d))
    c.form(pm, SILVER, d + 45, 90, 110, 50, 0.6)
    pts = [(0, -20), (2.6, -15), (1.6, -11), (2.8, -6), (1.8, -1), (2.2, 3.2), (-2.2, 3.2), (-1.8, -3), (-2.8, -8), (-1.6, -13), (-2.4, -16)]
    bm = blade(c, pts, d, ICE)
    c.stroke(local([(0, -17), (0, 1.5)], d), (255, 255, 255, 220), 0.7)
    for y in (-13, -8, -3):
        c.stroke(local([(-1.5, y + 2), (1.5, y - 2)], d), (255, 255, 255, 150), 0.4)
    for (x, y) in ((-3.5, -11), (3.6, -4), (-3.8, -1)):
        px, py = local([(x, y)], d)[0]
        c.dot(px, py, 0.55, (240, 252, 255))
    gm = c.mpoly(local([(-6, 3.2), (6, 3.2), (5, 5.6), (-5, 5.6)], d))
    c.form(gm, SILVER, d + 45, 90, 110, 50, 0.6)
    c.gem(*local([(0, 4.4)], d)[0], 1.0, (140, 220, 255), sparkle=False)


def weapon_staff(c):
    d = -40
    pts = [(-1.2, -9), (1.2, -9), (1.6, 0), (1.0, 9), (1.4, 19), (-1.4, 19), (-1.0, 9), (-1.6, 0)]
    sm = c.mpoly(local(pts, d))
    c.gfill(sm, WOOD[0], WOOD[2], d - 90, mid=WOOD[1])
    c.rim(sm, (0, 0, 0), 80, 0.5)
    for y in (2, 8, 14):
        c.stroke(local([(-0.6, y), (0.6, y + 2.5)], d), (60, 36, 16, 160), 0.4)
    for sx in (1, -1):
        prong = c.mpoly(local([(sx * 0.8, -9), (sx * 4.8, -13), (sx * 4.0, -19), (sx * 2.5, -18), (sx * 2.2, -13.5), (-sx * 0.5, -10.5)], d))
        c.form(prong, DARKWOOD, d + 45 * sx, 90, 110, 50, 0.4)
    px, py = local([(0, -15)], d)[0]
    c.gem(px, py, 4.2, AMET)
    c.dot(px + 1.4, py + 1.2, 0.6, (255, 230, 255))
    for sx in (1, -1):
        prong = c.mpoly(local([(sx * 0.8, -9), (sx * 4.8, -13), (sx * 3.5, -12.5), (sx * 1.2, -10.5)], d))
        c.form(prong, DARKWOOD, d + 45 * sx, 90, 110, 50, 0.4)


def weapon_scythe(c):
    d = -30
    o = 3.0        # everything sits a little low so the blade tip clears the top edge
    shaft(c, -15 + o, 18 + o, 1.2, d, DARKWOOD)
    for y in (-1, 9):
        peg = c.mpoly(local([(0.5, y + o), (5.5, y - 1.2 + o), (5.5, y + 1.0 + o), (0.5, y + 2.2 + o)], d))
        c.form(peg, DARKWOOD, d, 80, 100, 50, 0.3)
    pts = [(-1, -16), (5, -19.5), (12, -19), (17.5, -15), (20.5, -8.5), (20, -1), (18, 3.5),
           (18.2, -3), (16.5, -9), (13, -13.5), (8, -15), (3, -14.5), (-1, -12.5)]
    pts = [(x, y + o) for x, y in pts]
    bm = blade(c, pts, d, STEEL, 0)
    c.stroke(local([(3, -17.3 + o), (11, -17.3 + o), (16.5, -13.2 + o), (19.2, -6.5 + o), (18.8, o)], d), (255, 255, 255, 190), 0.8)
    c.stroke(local([(2, -13.6 + o), (9, -14.2 + o), (14.5, -11.5 + o), (17, -6 + o)], d), (60, 66, 84, 170), 0.6)
    band = c.mpoly(local([(-2.2, -16.5 + o), (2.2, -16.5 + o), (2.2, -12 + o), (-2.2, -12 + o)], d))
    c.form(band, IRON, d + 45, 80, 100, 50, 0.4)


def weapon_crossbow(c):
    d = -40
    st = c.mpoly(local([(-2.6, -12), (2.6, -12), (3.2, 9), (4.2, 17), (-1.2, 17), (-2.2, 9)], d))
    c.gfill(st, WOOD[0], WOOD[2], d - 90, mid=WOOD[1])
    c.rim(st, (0, 0, 0), 90, 0.6)
    c.stroke(local([(-1.4, -10), (-0.8, 8)], d), (220, 175, 120, 120), 0.6)
    prod = c.mline(local([(-17, -3), (-10, -8.5), (0, -10.5), (10, -8.5), (17, -3)], d), 2.8)
    c.gfill(prod, STEEL[0], STEEL[2], d + 90, mid=STEEL[1])
    c.edge(prod, 0.6, 0.6, (255, 255, 255), 130, 0.3)
    c.rim(prod, (0, 0, 0), 90, 0.55)
    c.stroke(local([(-17, -3), (17, -3)], d), (240, 238, 225), 0.8)
    box = c.mpoly(local([(-3.8, -11), (3.8, -11), (3.8, -6), (-3.8, -6)], d))
    c.form(box, IRON, d + 45, 80, 100, 50, 0.4)
    c.stroke(local([(0, -3), (0, -14)], d), (170, 115, 60), 1.2)
    c.stroke(local([(0, -14), (0, -17.5)], d), (205, 210, 225), 1.8)
    trig = c.mpoly(local([(2.5, 4), (6.5, 5.5), (6.5, 8), (2.5, 8.5)], d))
    c.form(trig, IRON, d, 80, 100, 50, 0.3)
    for y in (1, 7, 12):
        c.stroke(local([(-2.4, y), (3.0, y + 0.8)], d), (60, 36, 16, 170), 0.6)


# ----------------------------------------------------------------------------
# SHIELD ----------------------------------------------------------------------

def shield_round_wood(c):
    m = c.mell(6, 6, 35, 36)
    c.form(m, WOOD, 45)
    for x in (12, 17, 24, 29):
        c.stroke([(x, 7), (x, 35)], (55, 32, 12, 170), 0.6)
        c.stroke([(x - 0.8, 7), (x - 0.8, 35)], (215, 170, 110, 80), 0.5)
    rim = c.inter(m, c.sub(m, c.mell(8.5, 8.5, 32.5, 33.5)))
    c.form(rim, IRON, 45, 100, 120, 50, 0.5)
    for i in range(10):
        a = math.radians(i * 36 + 18)
        c.dot(20.5 + 13.5 * math.cos(a), 21 + 13.7 * math.sin(a), 0.55, (170, 172, 185))
    boss = c.mell(15.5, 16, 25.5, 26)
    c.rfill(boss, STEEL[0], STEEL[2], 19, 19.5, 6, mid=STEEL[1])
    c.rim(boss, (0, 0, 0), 100, 0.7)


def shield_kite(c):
    m = c.mpoly([(20.5, 4), (30, 7.5), (33.5, 15), (31.5, 27), (20.5, 38.5), (9.5, 27), (7.5, 15), (11, 7.5)])
    c.form(m, ((125, 155, 255), (52, 72, 205), (14, 20, 90)), 40)
    cross = c.inter(c.union(c.mrect(18, 5, 23, 37), c.mrect(9, 15, 32, 20)), m)
    c.gfill(cross, (255, 255, 255), (185, 190, 215), 45)
    c.rim(cross, (60, 70, 140), 80, 0.4, 0.2)
    rim = c.sub(m, c.mpoly([(20.5, 6), (28.8, 9), (31.7, 15.5), (29.8, 26.2), (20.5, 36), (11.2, 26.2), (9.3, 15.5), (12.2, 9)]))
    c.form(rim, SILVER, 45, 90, 110, 40, 0.4)
    c.dot(20.5, 17.5, 1.3, (60, 64, 80)); c.dot(20.1, 17.1, 0.6, (230, 235, 245))


def shield_tower(c):
    m = c.union(c.mrect(10, 10, 31, 38), c.mell(10, 3.5, 31, 16.5))
    c.form(m, STEEL, 35)
    for y in (16, 27):
        band = c.inter(c.mrect(10, y, 31, y + 2.5), m)
        c.gfill(band, IRON[0], IRON[2], 90, mid=IRON[1])
        c.rim(band, (0, 0, 0), 80, 0.3, 0.2)
        for x in (12.5, 20.5, 28.5):
            c.dot(x, y + 1.25, 0.6, (200, 204, 215))
    vb = c.inter(c.mrect(19.3, 5, 21.7, 38), m)
    c.gfill(vb, IRON[0], IRON[2], 0, mid=IRON[1])
    c.rim(vb, (0, 0, 0), 80, 0.3, 0.2)
    rim = c.sub(m, c.union(c.mrect(11.6, 10, 29.4, 36.4), c.mell(11.6, 5.1, 29.4, 16.5)))
    c.form(rim, IRON, 45, 90, 110, 40, 0.4)
    c.stroke([(12.5, 12), (12.5, 35)], (255, 255, 255, 110), 0.7)


def shield_heater_red(c):
    m = c.mpoly([(8, 6), (33, 6), (33, 20), (30, 29), (20.5, 38), (11, 29), (8, 20)])
    c.form(m, ((255, 115, 95), (192, 32, 32), (80, 5, 10)), 40)
    st = c.mpoly(star_pts(20.5, 19.5, 7.2))
    c.form(st, GOLD, 60, 90, 110, 50, 0.5)
    rim = c.sub(m, c.mpoly([(10, 8), (31, 8), (31, 19.5), (28.3, 28), (20.5, 35.4), (12.7, 28), (10, 19.5)]))
    c.form(rim, GOLD, 45, 90, 110, 40, 0.4)
    c.stroke([(10.5, 9), (10.5, 19), (13, 27)], (255, 200, 190, 110), 0.7)


def shield_buckler(c):
    m = c.mell(9, 9.5, 32, 32.5)
    c.form(m, BRASS, 45)
    ring = c.sub(c.mell(12, 12.5, 29, 29.5), c.mell(13.5, 14, 27.5, 28))
    c.gfill(ring, (110, 70, 20), (60, 35, 8), 45)
    c.edge(ring, 0.4, 0.4, (255, 240, 180), 130, 0.2)
    for i in range(8):
        a = math.radians(i * 45)
        x, y = 20.5 + 9.8 * math.cos(a), 21 + 9.8 * math.sin(a)
        c.dot(x, y, 0.95, (90, 60, 20)); c.dot(x - 0.3, y - 0.3, 0.45, (255, 240, 190))
    boss = c.mell(16, 16.5, 25, 25.5)
    c.rfill(boss, (255, 235, 170), (110, 70, 20), 19, 19.5, 5.5, mid=(210, 160, 60))
    c.rim(boss, (0, 0, 0), 100, 0.6)


def shield_bone(c):
    m = c.mell(7, 5.5, 34, 37)
    c.form(m, ((175, 165, 150), (95, 88, 78), (35, 30, 25)), 45)
    for i in range(12):
        a = math.radians(i * 30 + 15)
        x, y = 20.5 + 12 * math.cos(a), 21.2 + 14 * math.sin(a)
        c.dot(x, y, 0.8, (60, 52, 45)); c.dot(x - 0.3, y - 0.3, 0.4, (200, 190, 175))
    rim = c.sub(m, c.mell(9.2, 7.8, 31.8, 34.7))
    c.form(rim, BONE, 45, 90, 110, 40, 0.5)
    skull(c, 20.5, 20.5, 1.55, (28, 12, 14))
    for sx in (1, -1):
        b = c.mline([(20.5 + sx * 4, 33.5), (20.5 + sx * 9, 29.5)], 1.6)
        c.gfill(c.inter(b, m), BONE[0], BONE[2], 90, mid=BONE[1])
        c.rim(c.inter(b, m), (0, 0, 0), 80, 0.3, 0.2)


def shield_dragon_green(c):
    m = c.mpoly([(8, 6), (33, 6), (33, 20), (30, 29), (20.5, 38), (11, 29), (8, 20)])
    c.fill(m, (25, 60, 30))
    scales(c, m, ((150, 210, 110), (55, 130, 55), (15, 50, 20)), 3.6, 2.6, 2.1, 6, 6, 36, 38)
    c.shade(m, 90, 150, 1.3)
    rim = c.sub(m, c.mpoly([(10, 8), (31, 8), (31, 19.5), (28.3, 28), (20.5, 35.4), (12.7, 28), (10, 19.5)]))
    c.form(rim, BRONZE, 45, 90, 110, 40, 0.4)
    c.bezel(20.5, 19, 2.6, BRONZE, 2.6, 1.0)
    c.gem(20.5, 19, 2.6, EMER)


def shield_ice(c):
    m = c.mpoly([(20.5, 3.5), (34, 12), (34, 29), (20.5, 38.5), (7, 29), (7, 12)])
    c.form(m, ICE, 40)
    corners = [(20.5, 3.5), (34, 12), (34, 29), (20.5, 38.5), (7, 29), (7, 12)]
    tints = [(255, 255, 255, 110), (60, 140, 205, 90), (30, 100, 170, 110), (90, 165, 220, 90), (200, 240, 255, 100), (150, 215, 250, 90)]
    for i in range(6):
        tri = c.mpoly([(20.5, 21), corners[i], corners[(i + 1) % 6]])
        c.fill(c.inter(tri, m), tints[i])
    for i in range(6):
        c.stroke([(20.5, 21), corners[i]], (255, 255, 255, 130), 0.6)
    for i in range(6):
        a = math.radians(i * 60 + 30)
        p1 = (20.5, 21); p2 = (20.5 + 8 * math.cos(a), 21 + 8 * math.sin(a))
        c.stroke([p1, p2], (255, 255, 255), 0.9)
        px, py = 20.5 + 5.2 * math.cos(a), 21 + 5.2 * math.sin(a)
        for da in (0.7, -0.7):
            c.stroke([(px, py), (px + 2.4 * math.cos(a + da), py + 2.4 * math.sin(a + da))], (255, 255, 255), 0.7)
    rim = c.sub(m, c.mpoly([(20.5, 6), (31.8, 13.2), (31.8, 27.8), (20.5, 36), (9.2, 27.8), (9.2, 13.2)]))
    c.form(rim, ((240, 250, 255), (150, 200, 235), (50, 110, 170)), 45, 90, 110, 40, 0.4)
    c.dot(20.5, 21, 1.3, (255, 255, 255))


def shield_fire(c):
    m = c.mpoly([(8, 6), (33, 6), (33, 20), (30, 29), (20.5, 38), (11, 29), (8, 20)])
    c.form(m, ((255, 205, 90), (222, 82, 22), (92, 20, 5)), 40)
    lay = c.layer()
    for (x, h, w, lean) in ((20.5, 21, 8, 0), (14.5, 14, 5, -1.2), (26.5, 15, 5, 1.2)):
        flame(lay, x, 33, h, w, lean)
    c.paste_layer(lay, m)
    rim = c.sub(m, c.mpoly([(10, 8), (31, 8), (31, 19.5), (28.3, 28), (20.5, 35.4), (12.7, 28), (10, 19.5)]))
    c.form(rim, BLACK, 45, 90, 110, 40, 0.4)
    for x, y in ((12.5, 9.5), (28.5, 9.5), (12.5, 22), (28.5, 22)):
        c.dot(x, y, 0.6, (120, 118, 135))


def shield_gold_ornate(c):
    m = c.mpoly([(20.5, 4), (30, 7.5), (33.5, 15), (31.5, 27), (20.5, 38.5), (9.5, 27), (7.5, 15), (11, 7.5)])
    c.form(m, GOLD, 40)
    for sx in (1, -1):
        pts = [(20.5 + sx * 2, 9), (20.5 + sx * 7, 11), (20.5 + sx * 9.5, 16), (20.5 + sx * 8, 22), (20.5 + sx * 5, 27), (20.5 + sx * 2, 33)]
        c.stroke(pts, (120, 75, 15), 0.8)
        c.stroke([(x - 0.4, y - 0.4) for x, y in pts], (255, 250, 200), 0.4)
        c.stroke([(20.5 + sx * 3, 12.5), (20.5 + sx * 6, 15), (20.5 + sx * 4, 19)], (120, 75, 15), 0.6)
    rim = c.sub(m, c.mpoly([(20.5, 6), (28.8, 9), (31.7, 15.5), (29.8, 26.2), (20.5, 36), (11.2, 26.2), (9.3, 15.5), (12.2, 9)]))
    c.form(rim, ((255, 250, 200), (190, 140, 40), (95, 55, 10)), 45, 90, 110, 40, 0.4)
    c.bezel(20.5, 19.5, 3.2, GOLD, 3.2, 1.1)
    c.gem(20.5, 19.5, 3.2, RUBY)
    for x, y in ((14, 10.5), (27, 10.5), (20.5, 31.5)):
        c.gem(x, y, 1.0, SAPPH, sparkle=False)


def shield_spiked(c):
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        tip = (20.5 + 17.5 * math.cos(a), 21 + 18.5 * math.sin(a))
        b1 = (20.5 + 11.5 * math.cos(a + 0.28), 21 + 12 * math.sin(a + 0.28))
        b2 = (20.5 + 11.5 * math.cos(a - 0.28), 21 + 12 * math.sin(a - 0.28))
        sm = c.mpoly([tip, b1, b2])
        c.form(sm, IRON, 45, 90, 120, 50, 0.4)
    m = c.mell(8, 8, 33, 34)
    c.form(m, BLACK, 45)
    ring = c.sub(c.mell(11, 11, 30, 31), c.mell(12.5, 12.5, 28.5, 29.5))
    c.form(ring, IRON, 45, 90, 110, 40, 0.3)
    for i in range(8):
        a = math.radians(i * 45)
        x, y = 20.5 + 10.8 * math.cos(a), 21 + 11.3 * math.sin(a)
        c.dot(x, y, 0.7, (25, 25, 32)); c.dot(x - 0.25, y - 0.25, 0.35, (150, 150, 165))
    cone = c.mell(15.5, 16, 25.5, 26)
    c.rfill(cone, (200, 200, 215), (20, 20, 28), 19.5, 19.8, 5.5, mid=(90, 90, 105))
    c.rim(cone, (0, 0, 0), 100, 0.6)
    c.dot(20.5, 21, 1.1, (230, 232, 240))


def shield_leaf(c):
    m = c.mpoly(leaf_pts(20.5, 21, 36, 25, 90, 20))
    c.form(m, ((195, 235, 125), (82, 152, 52), (20, 62, 15)), 40)
    c.stroke([(20.5, 5), (20.5, 37)], (240, 210, 90), 0.9)
    for i in range(5):
        y = 10 + i * 5
        c.stroke([(20.5, y), (12 + i * 0.6, y + 4.5)], (240, 210, 90), 0.5)
        c.stroke([(20.5, y), (29 - i * 0.6, y + 4.5)], (240, 210, 90), 0.5)
    rim = c.sub(m, c.mpoly(leaf_pts(20.5, 21, 32.5, 21.5, 90, 20)))
    c.form(rim, SILVER, 45, 90, 110, 40, 0.4)
    c.bezel(20.5, 20, 2.0, SILVER, 2.0, 0.8)
    c.gem(20.5, 20, 2.0, EMER)


# ----------------------------------------------------------------------------
# RING ------------------------------------------------------------------------

RX, RY, RTH, RCY = 11.5, 8.8, 4.4, 25.0


def _ring(c, pal, gem=None, gem_r=4.0, bezel=True, cx=20.5, cy=RCY, rx=RX, ry=RY, th=RTH, angle=60):
    band = ring_band(c, cx, cy, rx, ry, th, pal, angle)
    c.stroke([(cx - rx + 2.2, cy - 1), (cx - rx * 0.55, cy - ry + 2.2), (cx, cy - ry + 1.8)], (255, 255, 255, 140), 0.8)
    c.stroke([(cx + rx * 0.3, cy + ry - 2.0), (cx + rx * 0.7, cy + ry * 0.55)], (0, 0, 0, 90), 0.8)
    if gem is not None:
        gx, gy = cx, cy - ry - 0.6
        if bezel:
            c.bezel(gx, gy, gem_r, pal, gem_r * 0.85, 1.2)
        c.gem(gx, gy, gem_r, gem, gem_r * 0.85)
    return band


def _band_pt(t, inset=0.0, cx=20.5, cy=RCY, rx=RX, ry=RY):
    """Point on the ring's outer ellipse at parameter t (0..1 around), moved inwards by inset."""
    a = 2 * math.pi * t
    return (cx + (rx - inset) * math.cos(a), cy + (ry - inset * 0.9) * math.sin(a))


def ring_gold_plain(c):
    _ring(c, GOLD)
    for t in (0.55, 0.62, 0.69, 0.76, 0.83, 0.9):
        a, b = _band_pt(t, 0.6), _band_pt(t + 0.02, 3.6)
        c.stroke([a, b], (120, 75, 15, 200), 0.6)
    c.stroke([_band_pt(0.32, 2.2), _band_pt(0.18, 2.2)], (255, 250, 210), 0.7)


def ring_silver_ruby(c):
    _ring(c, SILVER, RUBY)


def ring_gold_sapphire(c):
    _ring(c, GOLD, SAPPH)


def ring_silver_emerald(c):
    _ring(c, SILVER, EMER, 3.6)
    for x in (15.2, 25.8):
        c.bezel(x, 17.8, 1.4, SILVER, 1.4, 0.6)
        c.gem(x, 17.8, 1.4, EMER, sparkle=False)


def ring_gold_amethyst(c):
    _ring(c, GOLD, AMET, 4.3)
    for x in (14.5, 26.5):
        c.dot(x, 18.6, 0.8, (255, 250, 210))


def ring_iron_skull(c):
    _ring(c, BLACK)
    skull(c, 20.5, 14.8, 1.05, (150, 20, 20))


def ring_twisted(c):
    band = _ring(c, GOLD)
    for i in range(14):
        t = 0.5 + i * 0.5 / 14
        a, b = _band_pt(t, 0.4), _band_pt(t + 0.03, 4.2)
        c.stroke([a, b], (110, 65, 10, 220), 0.8)
        c.stroke([(a[0] - 0.5, a[1] - 0.5), (b[0] - 0.5, b[1] - 0.5)], (255, 250, 200, 170), 0.55)
    c.bezel(20.5, 15.8, 2.4, GOLD, 2.0, 1.0)
    c.gem(20.5, 15.8, 2.4, TOPAZ, 2.0)


def ring_diamond(c):
    _ring(c, ((255, 255, 255), (214, 220, 235), (110, 118, 150)), DIAM, 4.2)
    for (x, y, r) in ((15.4, 13.4, 0.7), (25.8, 13.8, 0.55), (20.5, 9.4, 0.75)):
        c.dot(x, y, r, (255, 255, 255))
    for a in (0, 90):
        rad = math.radians(a)
        c.stroke([(20.5 - 3 * math.cos(rad), 9.4 - 3 * math.sin(rad)), (20.5 + 3 * math.cos(rad), 9.4 + 3 * math.sin(rad))], (255, 255, 255), 0.5)


def ring_bone(c):
    _ring(c, BONE, th=5.0)
    for t in (0.55, 0.64, 0.73, 0.82, 0.9):
        a, b = _band_pt(t, 0.8), _band_pt(t + 0.025, 4.0)
        c.stroke([a, b], (100, 90, 60, 220), 0.6)
    skull(c, 20.5, 15.4, 0.9, (120, 20, 20))


def ring_fire(c):
    _ring(c, GOLD, TOPAZ, 3.4)
    lay = c.layer()
    for (x, h, w, lean) in ((20.5, 9.5, 4.6, 0), (16.6, 6.5, 3.0, -1.2), (24.4, 6.8, 3.0, 1.2)):
        flame(lay, x, 14.2, h, w, lean)
    c.im = Image.alpha_composite(c.im, lay.im)
    c.gem(20.5, 15.6, 3.4, TOPAZ, 2.9)


def ring_ice(c):
    _ring(c, ((240, 250, 255), (170, 210, 240), (60, 110, 165)), (150, 225, 255), 3.8)
    for tip, a, b in (((13.5, 9.5), (15.2, 17.6), (18.6, 16.6)), ((27.5, 9.5), (25.8, 17.6), (22.4, 16.6))):
        sm = c.mpoly([tip, a, b])
        c.gfill(sm, (245, 255, 255), (70, 150, 210), 90, mid=(160, 215, 245))
        c.rim(sm, (30, 90, 150), 110, 0.4, 0.25)
    c.dot(13.9, 12, 0.5, (255, 255, 255)); c.dot(27.1, 12, 0.5, (255, 255, 255))


def ring_signet(c):
    _ring(c, GOLD)
    top = c.mell(14, 11.5, 27, 19.5)
    c.form(top, GOLD, 60, 90, 110, 50, 0.7)
    face = c.mell(15.6, 12.8, 25.4, 18.4)
    c.gfill(face, (175, 30, 40), (70, 5, 12), 60)
    c.rim(face, (0, 0, 0), 110, 0.4, 0.2)
    st = c.mpoly(star_pts(20.5, 15.6, 2.2))
    c.fill(st, (255, 240, 170))


# ----------------------------------------------------------------------------
# USE -------------------------------------------------------------------------

def use_potion_red(c):
    neck = c.mrect(17.8, 8, 23.2, 17)
    bulb = c.mell(10.5, 14, 30.5, 36)
    m = c.union(neck, bulb)
    liq = c.inter(m, c.mrect(0, 21, 41, 41))
    flask_glass(c, m, liq, (205, 25, 40))
    bub = c.mell(13.5, 23.5, 19.5, 31)
    c.fill(bub, (255, 130, 140, 60))
    c.stroke([(13.5, 20), (13, 27), (15, 32)], (255, 255, 255, 170), 0.9)
    for (x, y, r) in ((23, 27, 0.6), (19, 31, 0.45), (25.5, 32.5, 0.4)):
        c.dot(x, y, r, (255, 170, 175))
    cork = c.mrect(16.8, 5, 24.2, 9.5)
    c.form(cork, ((200, 150, 95), (140, 95, 50), (60, 35, 15)), 30, 90, 110, 50, 0.5)
    lip = c.mrect(16.5, 9.2, 24.5, 11.2)
    c.fill(lip, (170, 200, 220, 220)); c.rim(lip, (0, 0, 0), 90, 0.3, 0.2)


def use_potion_blue(c):
    m = c.mpoly([(17, 9), (24, 9), (24, 17), (32.5, 34), (31, 36.5), (10, 36.5), (8.5, 34), (17, 17)])
    liq = c.inter(m, c.mrect(0, 24, 41, 41))
    flask_glass(c, m, liq, (35, 90, 230))
    c.stroke([(17.5, 19), (12.5, 30)], (255, 255, 255, 170), 0.9)
    for (x, y, r) in ((24, 28, 0.55), (19, 33, 0.45), (27.5, 32.5, 0.4)):
        c.dot(x, y, r, (170, 210, 255))
    cork = c.mrect(16.5, 5, 24.5, 10)
    c.form(cork, ((200, 150, 95), (140, 95, 50), (60, 35, 15)), 30, 90, 110, 50, 0.5)
    lip = c.mrect(16, 9.5, 25, 11.5)
    c.fill(lip, (170, 200, 220, 220)); c.rim(lip, (0, 0, 0), 90, 0.3, 0.2)
    tag = c.mpoly([(26, 10.5), (32, 16), (30, 18), (24, 12.5)])
    c.gfill(tag, (250, 240, 200), (200, 175, 120), 45)
    c.rim(tag, (0, 0, 0), 90, 0.3, 0.2)
    c.stroke([(25.5, 10), (24.5, 11.5)], (200, 200, 190), 0.4)


def use_scroll(c):
    body = c.mrect(10.5, 10, 30.5, 32)
    c.form(body, ((252, 244, 210), (222, 198, 150), (130, 100, 60)), 20, 80, 110, 50, 0.7)
    for i in range(5):
        y = 14.5 + i * 3.2
        c.stroke([(13.5, y), (27 - (i % 2) * 5, y)], (110, 80, 50), 0.55)
    for y0, y1 in ((7.5, 13.5), (29, 35)):
        roll = c.mell(8, y0, 33, y1)
        c.form(roll, ((252, 246, 220), (215, 190, 140), (120, 92, 52)), 90, 100, 130, 60, 0.7)
        for x in (9.3, 31.7):
            c.dot(x, (y0 + y1) / 2, 1.2, (150, 120, 75)); c.dot(x, (y0 + y1) / 2, 0.5, (90, 65, 35))
    c.stroke([(21, 30), (25, 34.5), (24, 38)], (200, 40, 40), 1.4)
    c.stroke([(21, 30), (17.5, 35), (18, 38)], (200, 40, 40), 1.4)
    seal = c.mell(18, 26.5, 24, 32.5)
    c.rfill(seal, (255, 100, 100), (110, 5, 10), 20, 28.5, 3.5, mid=(200, 30, 40))
    c.rim(seal, (0, 0, 0), 100, 0.4, 0.2)
    c.dot(21, 29.5, 1.0, (150, 20, 30))


def use_spellbook(c):
    pages = c.mrect(11.5, 8.5, 33, 36.5)
    c.form(pages, ((250, 245, 225), (215, 200, 165), (120, 100, 70)), 60, 60, 100, 40, 0.5)
    for y in (10, 12, 14):
        c.stroke([(31.5, y), (31.5, 36)], (150, 130, 95, 150), 0.5)
    cover = c.mrect(9, 6.5, 30.5, 34.5)
    c.form(cover, ((160, 62, 66), (102, 26, 32), (40, 6, 10)), 40)
    c.rim(cover, (0, 0, 0), 90, 0.7)
    spine = c.mrect(9, 6.5, 12.5, 34.5)
    c.gfill(spine, (120, 40, 45), (45, 8, 12), 0)
    for y in (9, 32):
        c.stroke([(9.5, y), (30, y)], (230, 190, 90), 0.6)
    inner = c.sub(c.mrect(14.5, 9.5, 28, 31.5), c.mrect(15.5, 10.5, 27, 30.5))
    c.fill(inner, (230, 190, 90, 200))
    eye = c.mpoly(leaf_pts(21.2, 20.5, 9, 5, 0))
    c.gfill(eye, (240, 200, 100), (140, 85, 20), 90)
    c.gem(21.2, 20.5, 1.7, AMET)
    clasp = c.mrect(28, 18, 32.5, 23)
    c.form(clasp, BRASS, 45, 90, 110, 50, 0.4)


def use_orb(c):
    stand = c.mpoly([(12.5, 28), (28.5, 28), (26, 34.5), (15, 34.5)])
    c.form(stand, BRONZE, 60, 90, 120, 60, 0.6)
    base = c.mell(11, 32.5, 30, 37.5)
    c.form(base, BRONZE, 60, 90, 120, 60, 0.6)
    for sx in (1, -1):
        claw = c.mpoly([(20.5 + sx * 3, 28.5), (20.5 + sx * 9.5, 24), (20.5 + sx * 10.5, 20), (20.5 + sx * 8.5, 22), (20.5 + sx * 7, 27)])
        c.form(claw, BRONZE, 45, 90, 110, 50, 0.4)
    c.gem(20.5, 17.5, 9.5, (150, 90, 230), 9.5)
    swirl = c.mline([(13.5, 20), (16, 15), (21, 13), (26, 15.5), (27.5, 21), (23, 24.5)], 1.2)
    c.fill(c.inter(swirl, c.mell(11, 8, 30, 27)), (240, 200, 255, 110))
    c.dot(16.5, 13, 1.3, (255, 255, 255))
    c.dot(24.5, 22, 0.6, (255, 240, 255))


def tube_pts(center, widths):
    """Polygon around a polyline `center` with per-vertex half-widths."""
    left, right = [], []
    n = len(center)
    for i, (x, y) in enumerate(center):
        x0, y0 = center[max(0, i - 1)]; x1, y1 = center[min(n - 1, i + 1)]
        dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        left.append((x + nx * widths[i], y + ny * widths[i])); right.append((x - nx * widths[i], y - ny * widths[i]))
    return left + right[::-1]


def use_horn(c):
    center = [(30.5, 9), (30, 14), (27, 20), (22, 26), (16, 31), (10, 34.5)]
    widths = [6.0, 5.4, 4.6, 3.6, 2.4, 1.2]
    m = c.mpoly(tube_pts(center, widths))
    c.form(m, ((242, 228, 195), (188, 152, 108), (86, 60, 30)), 40, 110, 130, 60, 1.1)
    for i in range(1, 5):
        x, y = center[i]; w = widths[i]
        x0, y0 = center[i - 1]; x1, y1 = center[i + 1]
        dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        c.stroke([(x + nx * w * 0.9, y + ny * w * 0.9), (x - nx * w * 0.9, y - ny * w * 0.9)], (120, 90, 50, 150), 0.6)
    mouth = c.mell(24.5, 4.5, 36.5, 13.5)
    c.form(mouth, GOLD, 45, 90, 110, 50, 0.6)
    inner = c.mell(26.3, 6.2, 34.7, 11.8)
    c.rfill(inner, (150, 110, 70), (45, 25, 10), 29, 8.2, 4.5)
    c.rim(inner, (0, 0, 0), 110, 0.5, 0.2)
    band = c.inter(c.mline([(24.5, 17), (30.5, 21)], 2.6), m)
    c.form(band, GOLD, 45, 90, 110, 50, 0.4)
    c.stroke([(27.5, 14.5), (23.5, 22), (17, 28.5)], (255, 250, 235, 150), 1.0)
    c.stroke([(12, 33), (13, 30.5)], (255, 250, 235, 150), 0.6)


def use_amulet(c):
    pts = []
    for i in range(21):
        t = i / 20
        a = math.pi * (1.0 + t)
        pts.append((20.5 + 12.5 * math.cos(a), 12 + 8 * math.sin(a)))
    pts = [(8, 20)] + pts + [(33, 20)]
    for i in range(len(pts) - 1):
        col = (240, 215, 120) if i % 2 == 0 else (150, 105, 30)
        c.stroke([pts[i], pts[i + 1]], col, 1.1)
    c.stroke([(8, 20), (13, 27.5)], (200, 160, 60), 1.0)
    c.stroke([(33, 20), (28, 27.5)], (200, 160, 60), 1.0)
    pend = c.mpoly([(20.5, 20), (27, 26), (27.5, 31), (24, 36.5), (17, 36.5), (13.5, 31), (14, 26)])
    c.form(pend, GOLD, 50, 110, 130, 60, 0.8)
    c.bezel(20.5, 30, 3.6, GOLD, 3.6, 1.1)
    c.gem(20.5, 30, 3.6, SAPPH)
    loop = c.sub(c.mell(18.5, 19, 22.5, 23), c.mell(19.6, 20.1, 21.4, 21.9))
    c.form(loop, GOLD, 45, 90, 110, 40, 0.3)


def use_boots(c):
    for (x0, dy) in ((8, 0), (20.5, 3)):
        shaftm = c.mrect(x0 + 1, 6 + dy, x0 + 10.5, 24 + dy)
        foot = c.union(c.mpoly([(x0 + 1, 22 + dy), (x0 + 10.5, 22 + dy), (x0 + 12, 29 + dy), (x0 + 12.5, 33 + dy), (x0 + 1, 33 + dy)]),
                       c.mell(x0 + 5, 25 + dy, x0 + 13, 33 + dy))
        m = c.union(shaftm, foot)
        c.form(m, LEATHER, 35, 110, 130, 60, 1.0)
        sole = c.inter(c.mrect(x0, 31 + dy, x0 + 13, 34 + dy), c.union(m, c.mrect(x0 + 1, 31 + dy, x0 + 12.5, 34 + dy)))
        c.gfill(sole, (70, 45, 25), (25, 12, 5), 90)
        c.rim(sole, (0, 0, 0), 80, 0.3, 0.2)
        cuff = c.mrect(x0 + 0.5, 5.5 + dy, x0 + 11, 9.5 + dy)
        c.form(cuff, ((200, 150, 100), (130, 85, 45), (55, 30, 12)), 90, 90, 110, 50, 0.5)
        for i in range(3):
            y = 12 + dy + i * 3.5
            c.stroke([(x0 + 3.5, y), (x0 + 8, y + 1.6)], (60, 35, 15), 0.45)
            c.stroke([(x0 + 8, y), (x0 + 3.5, y + 1.6)], (60, 35, 15), 0.45)
        c.stroke([(x0 + 2.5, 10 + dy), (x0 + 2.5, 22 + dy)], (215, 165, 110, 120), 0.7)


def use_gauntlet(c):
    cuff = c.mpoly([(12, 6), (29, 6), (27.5, 15), (13.5, 15)])
    c.form(cuff, STEEL, 40, 100, 130, 60, 0.8)
    for y in (9, 12):
        c.stroke([(13, y), (28.5, y)], (60, 66, 84, 170), 0.6)
        c.stroke([(13, y - 0.7), (28.5, y - 0.7)], (255, 255, 255, 120), 0.45)
    palm = c.mpoly([(13.5, 15), (27.5, 15), (28, 27), (14, 27)])
    c.form(palm, STEEL, 40, 100, 130, 60, 0.8)
    for i, x in enumerate((15.0, 18.7, 22.4, 26.1)):
        top = 27; ln = (10, 11, 10.5, 8.5)[i]
        f = c.union(c.mrect(x - 1.55, top - 1, x + 1.55, top + ln - 1.5), c.mell(x - 1.55, top + ln - 3.2, x + 1.55, top + ln))
        c.form(f, STEEL, 30, 100, 130, 70, 0.6)
        for k in range(1, 3):
            y = top + ln * k / 3
            c.stroke([(x - 1.5, y), (x + 1.5, y)], (40, 44, 58, 220), 0.6)
        if i:
            c.stroke([(x - 1.85, 27), (x - 1.85, top + ln - 1)], (25, 28, 38, 230), 0.5)
    th = c.mpoly([(14, 17), (9.5, 21.5), (9, 27), (12, 29), (15, 25)])
    c.form(th, STEEL, 30, 100, 130, 70, 0.6)
    c.stroke([(11.5, 22.5), (12.5, 26)], (40, 44, 58, 220), 0.6)
    c.stroke([(14.2, 17.5), (14.5, 26)], (25, 28, 38, 200), 0.5)
    for x in (16.8, 20.5, 24.2):
        c.dot(x, 24.5, 0.8, (50, 54, 70)); c.dot(x - 0.3, 24.2, 0.35, (225, 230, 240))


def use_wand(c):
    st = c.mline([(9, 35), (30, 11)], 2.0)
    c.gfill(st, DARKWOOD[0], DARKWOOD[2], 45, mid=DARKWOOD[1])
    c.rim(st, (0, 0, 0), 90, 0.5)
    c.stroke([(9.5, 34), (29.5, 11.5)], (200, 150, 100, 110), 0.5)
    hm = c.mline([(9, 35), (16, 27)], 2.6)
    c.form(hm, LEATHER, 45, 80, 100, 50, 0.4)
    band = c.mline([(28.5, 12.5), (30.5, 10.5)], 2.6)
    c.form(band, GOLD, 45, 90, 110, 50, 0.3)
    st2 = c.mpoly(star_pts(31.5, 9.5, 4.5))
    c.gfill(st2, (255, 255, 210), (225, 170, 40), 90)
    c.rim(st2, (120, 75, 15), 90, 0.3, 0.2)
    for (x, y, r) in ((25, 8, 0.7), (35, 15, 0.6), (27, 16.5, 0.5), (34, 5.5, 0.5)):
        c.dot(x, y, r, (255, 250, 200))
    c.stroke([(19, 25), (16, 30)], (200, 40, 40), 0.9)
    c.stroke([(19, 25), (21, 30)], (200, 40, 40), 0.9)


def use_key(c):
    bow = c.sub(c.mell(6.5, 24, 17.5, 35), c.mell(9.5, 27, 14.5, 32))
    c.form(bow, GOLD, 45, 110, 130, 60, 0.8)
    st = c.mline([(15.5, 27.5), (31.5, 11.5)], 2.6)
    c.gfill(st, GOLD[0], GOLD[2], 135, mid=GOLD[1])
    c.rim(st, (0, 0, 0), 90, 0.5)
    c.stroke([(16.5, 26), (31, 11.5)], (255, 250, 200, 150), 0.6)
    for (x, y) in ((27.5, 14.5), (30.5, 11.5)):
        t = c.mpoly([(x - 1.2, y + 1.2), (x + 1.2, y - 1.2), (x + 4.5, y + 2.2), (x + 2, y + 4.5)])
        c.form(t, GOLD, 45, 90, 110, 50, 0.4)
    c.dot(12, 29.5, 0.9, (120, 75, 15))
    c.gem(12, 29.5, 0.9, RUBY, sparkle=False)
    c.stroke([(8.5, 26.5), (10.5, 25)], (255, 255, 230, 180), 0.7)


def use_lantern(c):
    handle = c.sub(c.mell(13.5, 3.5, 27.5, 13), c.mell(15.5, 5.5, 25.5, 12))
    handle = c.inter(handle, c.mrect(0, 0, 41, 9.5))
    c.form(handle, IRON, 45, 90, 110, 50, 0.5)
    glass = c.mrect(13.5, 11, 27.5, 31)
    c.rfill(glass, (255, 255, 210), (200, 90, 20), 20.5, 22, 11, mid=(255, 190, 60))
    fl = flame(c, 20.5, 26, 8, 4)
    c.dot(20.5, 21.5, 1.0, (255, 255, 240))
    frame = c.sub(c.mrect(12, 9.5, 29, 32.5), c.mrect(13.5, 11, 27.5, 31))
    frame = c.union(frame, c.mrect(19.7, 11, 21.3, 31), c.mrect(13.5, 20.3, 27.5, 21.7))
    c.form(frame, BLACK, 45, 90, 110, 50, 0.4)
    top = c.mpoly([(12, 9.5), (29, 9.5), (25.5, 6.5), (15.5, 6.5)])
    c.form(top, BLACK, 60, 90, 110, 50, 0.4)
    base = c.mrect(11, 32.5, 30, 36)
    c.form(base, BLACK, 60, 90, 110, 50, 0.4)
    c.dot(20.5, 5.8, 1.1, (60, 60, 72))


# ----------------------------------------------------------------------------
ICONS = [
    ("head", [head_greathelm, head_crown, head_horned, head_wizard_hat, head_hood, head_circlet,
              head_skull, head_feathered_cap, head_winged, head_spiked, head_tiara, head_laurel]),
    ("armor", [body_plate, body_chain, body_leather, body_robe, body_scale, body_gold,
               body_bone, body_fire, body_ice, body_cloak, body_dragon, body_mithril]),
    ("weapon", [weapon_longsword, weapon_axe, weapon_mace, weapon_spear, weapon_bow, weapon_dagger,
                weapon_hammer, weapon_flaming, weapon_frost, weapon_staff, weapon_scythe, weapon_crossbow]),
    ("shield", [shield_round_wood, shield_kite, shield_tower, shield_heater_red, shield_buckler, shield_bone,
                shield_dragon_green, shield_ice, shield_fire, shield_gold_ornate, shield_spiked, shield_leaf]),
    ("ring", [ring_gold_plain, ring_silver_ruby, ring_gold_sapphire, ring_silver_emerald, ring_gold_amethyst, ring_iron_skull,
              ring_twisted, ring_diamond, ring_bone, ring_fire, ring_ice, ring_signet]),
    ("use", [use_potion_red, use_potion_blue, use_scroll, use_spellbook, use_orb, use_horn,
             use_amulet, use_boots, use_gauntlet, use_wand, use_key, use_lantern]),
]


def finish(c, alpha_cut=110, outline=0.42):
    """Downsample the 4x canvas to 41x42 (premultiplied), binarise alpha, add a dark outline."""
    im = c.im.convert('RGBa').resize((BW, BH), Image.LANCZOS).convert('RGBA')
    px = im.load()
    for y in range(BH):
        for x in range(BW):
            r, g, b, a = px[x, y]
            px[x, y] = (r, g, b, 255) if a >= alpha_cut else (0, 0, 0, 0)
    out = im.copy(); po = out.load()
    for y in range(BH):
        for x in range(BW):
            if px[x, y][3] == 0:
                continue
            edge = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < BW and 0 <= ny < BH and px[nx, ny][3] == 0:
                    edge = True; break
            if edge:
                r, g, b, _ = px[x, y]
                po[x, y] = (int(r * outline), int(g * outline), int(b * outline), 255)
    return out


def to565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def rle16(rows, back):
    """Game-identical RLESprite16 encoder (see rle_test.py: 4161/4161 images re-encode bit-exact)."""
    out = bytearray()
    for row in rows:
        line = bytearray(); run = 0
        for v in row:
            if v == back:
                run += 1
            else:
                if run:
                    line += struct.pack('<HH', back, 2 * run); run = 0
                line += struct.pack('<H', v)
        if run:
            line += struct.pack('<HH', back, 2 * run)
        nvals = len(line) // 2
        out += struct.pack('<I', 2 * nvals + 4) + line
        if nvals % 2:
            out += struct.pack('<H', back)
    return bytes(out)


def encode_icon(im):
    """Return (rle bytes, (cw, ch, cx, cy)) for a finished 41x42 RGBA icon."""
    px = im.load()
    bb = im.split()[3].getbbox()
    if not bb:
        raise ValueError("empty icon")
    x0, y0, x1, y1 = bb
    rows = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a == 0:
                row.append(TRANSP)
            else:
                v = to565(r, g, b)
                if v == TRANSP:
                    v ^= 1           # never let an opaque pixel collide with the key colour
                row.append(v)
        rows.append(row)
    return rle16(rows, TRANSP), (x1 - x0, y1 - y0, x0, y0)


def build(preview_path=None):
    icons = []            # (name, finished RGBA)
    for slot, fns in ICONS:
        for i, fn in enumerate(fns, 1):
            c = C()
            fn(c)
            icons.append(("%s%02d.bmp" % (slot, i), finish(c)))
    images = []; blob = bytearray()
    for idx, (name, im) in enumerate(icons):
        data, (cw, ch, cx, cy) = encode_icon(im)
        if cx == 0 or cy == 0 or cx + cw == BW or cy + ch == BH:
            print("  note: %s touches the canvas edge (clip %dx%d at %d,%d)" % (name, cw, ch, cx, cy))
        rec = ilbcodec.Rec(type=17, info=3, name=name.encode('latin1'), w=BW, h=BH, xs=0, ys=0, sub=0,
                           unkA=1, size=len(data), off=len(blob), totw=BW, toth=BH,
                           drawMode=256, blendValue=0, pixFmt=PIXFMT,
                           cw=cw, ch=ch, cx=cx, cy=cy, transp=TRANSP, clip_x=0)
        images.append({'id': idx, 'composite': False, 'parts': [rec], 'empty': False})
        blob += data
    lib = {'someId': SOMEID, 'version': 4.0, 'hdrLength': 24, 'palettes': [], 'images': images, 'pixeldata': bytes(blob)}
    raw = ilbcodec.write(lib)
    if preview_path:
        cols, sc = 12, 3
        TW, TH = BW * sc, BH * sc + 12
        rows = (len(icons) + cols - 1) // cols
        sheet = Image.new('RGBA', (cols * TW, rows * TH), (58, 58, 58, 255))
        dr = ImageDraw.Draw(sheet)
        for i, (name, im) in enumerate(icons):
            x, y = (i % cols) * TW, (i // cols) * TH
            sheet.alpha_composite(im.resize((BW * sc, BH * sc), Image.NEAREST), (x, y))
            dr.text((x + 2, y + BH * sc), "%d %s" % (i, name[:-4]), fill=(255, 255, 0, 255))
        sheet.save(preview_path)
    return raw, icons


def verify(raw, icons):
    """Re-read the ILB with the reference reader and decode every image back to pixels."""
    lib = ilbcodec.read(raw)
    assert ilbcodec.write(lib) == raw, "codec round-trip mismatch"
    base = lib['imgDirectory']
    for img, (name, im) in zip(lib['images'], icons):
        r = img['parts'][0]
        assert r['name'] == name.encode('latin1')
        data = raw[base + r['off']: base + r['off'] + r['size']]
        px = im.load(); q = 0
        for yy in range(r['ch']):
            ln = struct.unpack_from('<I', data, q)[0]; q += 4
            n = (ln - 4) // 2; pad = n % 2; x = r['cx']; y = r['cy'] + yy
            while n > 0:
                v = struct.unpack_from('<H', data, q)[0]; q += 2; n -= 1
                if v == TRANSP:
                    cnt = struct.unpack_from('<H', data, q)[0]; q += 2; n -= 1
                    for k in range(cnt // 2):
                        assert px[x + k, y][3] == 0, "%s: opaque pixel decoded as transparent at %d,%d" % (name, x + k, y)
                    x += cnt // 2
                else:
                    rr, gg, bb, a = px[x, y]
                    assert a == 255, "%s: transparent pixel decoded as opaque at %d,%d" % (name, x, y)
                    want = to565(rr, gg, bb)
                    if want == TRANSP:
                        want ^= 1
                    assert v == want, "%s: pixel mismatch at %d,%d" % (name, x, y)
                    x += 1
            if pad:
                q += 2
            assert x == r['cx'] + r['cw'], "%s: row %d width mismatch" % (name, y)
        assert q == len(data), "%s: trailing bytes" % name
        # every opaque pixel must lie inside the clip box
        for y in range(BH):
            for x in range(BW):
                if px[x, y][3] and not (r['cx'] <= x < r['cx'] + r['cw'] and r['cy'] <= y < r['cy'] + r['ch']):
                    raise AssertionError("%s: opaque pixel outside clip box" % name)
    return len(lib['images'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'Images', 'Items', 'I_x2026.ilb'))
    ap.add_argument('--preview', default=None, help='contact-sheet png (default: next to the script, I_x2026_preview.png)')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    preview = a.preview or os.path.join(HERE, 'I_x2026_preview.png')
    if os.path.exists(a.out) and not a.force:
        print("refusing to overwrite %s (use --force)" % a.out); return 1
    raw, icons = build(preview)
    n = verify(raw, icons)
    with open(a.out, 'wb') as f:
        f.write(raw)
    print("wrote %s  (%d bytes, %d images, verified decode)" % (a.out, len(raw), n))
    print("preview: %s" % preview)
    return 0


if __name__ == '__main__':
    sys.exit(main())
