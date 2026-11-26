"""Generate the AoWxImg / AoWxInk / AoWxQuest icons.

Each icon is the AoWx.exe MAINICON coiled black dragon (32x32 pixel art,
extracted to assets\\aowx_dragon32.png) kept crisp as the background, with a
shaded tool symbol placed slightly toward the bottom-right corner:
    AoWxImg   -> painter's palette
    AoWxInk   -> feather quill
    AoWxQuest -> globe

Writes assets\\aowximg.ico / aowxink.ico / aowxquest.ico (16..256 multi-size)
plus a 256px .png preview of each. Every ICO frame is composed at its own size
(pixel dragon scaled nearest for integer multiples), so the ICO is written by
hand instead of through Pillow's resample-the-base-image saver.
Run after any art tweak; the tools embed these at build time (build_tools.py)
and load them at runtime for the window icon.
"""
from PIL import Image, ImageDraw, ImageFilter
import math
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
os.makedirs(OUT, exist_ok=True)

DRAGON = Image.open(os.path.join(OUT, "aowx_dragon32.png")).convert("RGBA")
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]
S = 768                   # supersample canvas for the drawn symbols
FG_FRAC = 0.62            # symbol box as a fraction of the icon side
FG_FRAC_TINY = 0.74       # symbols grow a little at 16/24 px to stay readable
FG_CENTER = (0.615, 0.635)  # slightly toward the bottom-right corner


# --------------------------------------------------------------------------
# small drawing helpers (no numpy: gradients from PIL primitives)
# --------------------------------------------------------------------------
def linear_gradient(size, c0, c1, angle_deg):
    """RGBA image blending c0 -> c1 along the given direction."""
    g = Image.linear_gradient("L").rotate(angle_deg, expand=True)
    g = g.resize(size)
    a = Image.new("RGBA", size, c0)
    b = Image.new("RGBA", size, c1)
    return Image.composite(b, a, g)


def radial_gradient(size, c_center, c_edge, center=(0.5, 0.5), radius=0.5):
    g = Image.radial_gradient("L").resize((size[0] * 2, size[1] * 2))
    cx = int(size[0] * center[0]) - size[0]
    cy = int(size[1] * center[1]) - size[1]
    # radial_gradient is black centre -> white edge over its own half-size
    sc = max(0.05, radius / 0.5)
    g = g.resize((int(g.size[0] * sc), int(g.size[1] * sc)))
    mask = Image.new("L", size, 255)
    mask.paste(g, (cx + (g.size[0] - size[0] * 2) // -2 + cx - cx,
                   cy + (g.size[1] - size[1] * 2) // -2 + cy - cy))
    # simpler: recompute paste position so gradient centre lands on `center`
    mask = Image.new("L", size, 255)
    px = int(size[0] * center[0] - g.size[0] / 2)
    py = int(size[1] * center[1] - g.size[1] / 2)
    mask.paste(g, (px, py))
    a = Image.new("RGBA", size, c_center)
    b = Image.new("RGBA", size, c_edge)
    return Image.composite(b, a, mask)


def clip(img, mask):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def outline_of(mask, width, color):
    """Dark outline ring around a silhouette mask."""
    grown = mask.filter(ImageFilter.MaxFilter(width * 2 + 1))
    ring = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    ring.paste(Image.new("RGBA", mask.size, color), (0, 0), grown)
    hole = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    ring = Image.composite(hole, ring, mask.point(lambda v: 255 if v > 0 else 0))
    return ring, grown


def rot(p, c, deg):
    a = math.radians(deg)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(a) - y * math.sin(a),
            c[1] + x * math.sin(a) + y * math.cos(a))


# --------------------------------------------------------------------------
# the three tool symbols, each drawn on an S x S canvas
# --------------------------------------------------------------------------
def draw_palette():
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx, cy, R = S * 0.5, S * 0.5, S * 0.44

    # kidney shape: big ellipse minus a bite on the upper right, minus thumb hole
    mask = Image.new("L", (S, S), 0)
    dm = ImageDraw.Draw(mask)
    dm.ellipse([cx - R, cy - R * 0.82, cx + R, cy + R * 0.82], fill=255)
    dm.ellipse([cx + R * 0.28, cy - R * 0.95, cx + R * 1.05, cy - R * 0.18], fill=0)
    dm.ellipse([cx + R * 0.30, cy - R * 0.10, cx + R * 0.66, cy + R * 0.26], fill=0)
    mask = mask.rotate(-14, center=(cx, cy), resample=Image.BICUBIC)

    wood = linear_gradient((S, S), (196, 148, 92, 255), (120, 82, 46, 255), -30)
    c.alpha_composite(clip(wood, mask))
    ring, _ = outline_of(mask, 7, (74, 46, 24, 255))
    c.alpha_composite(ring)
    # soft inner highlight along the top-left rim
    hi = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dh = ImageDraw.Draw(hi)
    dh.arc([cx - R * 0.93, cy - R * 0.76, cx + R * 0.93, cy + R * 0.76],
           150, 285, fill=(255, 226, 180, 130), width=14)
    c.alpha_composite(clip(hi.rotate(-14, center=(cx, cy), resample=Image.BICUBIC), mask))

    # paint blobs with darker rim + specular dot
    blobs = [((-0.52, -0.42), (208, 58, 48)), ((-0.02, -0.55), (238, 178, 44)),
             ((0.42, -0.50), (72, 148, 66)), ((-0.72, 0.02), (58, 104, 196)),
             ((-0.52, 0.44), (146, 66, 168)), ((-0.02, 0.52), (238, 238, 230))]
    d = ImageDraw.Draw(c)
    for (fx, fy), col in blobs:
        bx, by = rot((cx + R * fx, cy + R * fy), (cx, cy), -14)
        rr = R * 0.145
        dark = tuple(max(0, v - 70) for v in col)
        d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=col + (255,),
                  outline=dark + (255,), width=6)
        d.ellipse([bx - rr * 0.45, by - rr * 0.55, bx - rr * 0.05, by - rr * 0.15],
                  fill=tuple(min(255, v + 55) for v in col) + (220,))

    # brush lying across the lower part
    bx0, by0 = cx - R * 1.02, cy + R * 0.88
    bx1, by1 = cx + R * 0.95, cy + R * 0.10
    ang = math.atan2(by1 - by0, bx1 - bx0)
    nx, ny = -math.sin(ang), math.cos(ang)
    w = R * 0.055

    def seg(t0, t1, col, ww):
        p0 = (bx0 + (bx1 - bx0) * t0, by0 + (by1 - by0) * t0)
        p1 = (bx0 + (bx1 - bx0) * t1, by0 + (by1 - by0) * t1)
        d.polygon([(p0[0] + nx * ww, p0[1] + ny * ww), (p1[0] + nx * ww, p1[1] + ny * ww),
                   (p1[0] - nx * ww, p1[1] - ny * ww), (p0[0] - nx * ww, p0[1] - ny * ww)],
                  fill=col)
    seg(0.00, 0.62, (58, 36, 22, 255), w + 6)          # outline
    seg(0.62, 0.78, (40, 40, 46, 255), w + 8)
    seg(0.78, 1.00, (30, 28, 30, 255), w + 4)
    seg(0.00, 0.62, (172, 118, 62, 255), w)            # handle
    seg(0.62, 0.78, (188, 190, 200, 255), w + 2)       # ferrule
    seg(0.78, 0.97, (52, 48, 54, 255), w - 2)          # bristles
    # red paint on the tip
    tipx, tipy = bx0 + (bx1 - bx0) * 0.985, by0 + (by1 - by0) * 0.985
    d.ellipse([tipx - w * 1.2, tipy - w * 1.2, tipx + w * 1.2, tipy + w * 1.2],
              fill=(208, 58, 48, 255))
    return c


def draw_quill():
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    # spine: quadratic bezier from nib (bottom-left) to plume tip (top-right)
    p0 = (S * 0.14, S * 0.90)
    p1 = (S * 0.34, S * 0.42)
    p2 = (S * 0.88, S * 0.10)

    def bez(t):
        mt = 1 - t
        return (mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
                mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1])

    def tangent(t):
        mt = 1 - t
        tx = 2 * mt * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
        ty = 2 * mt * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
        ln = math.hypot(tx, ty)
        return tx / ln, ty / ln

    # vane silhouette: barbs on both sides of the spine, longest mid-feather
    left, right = [], []
    N = 60
    for i in range(N + 1):
        t = i / N
        x, y = bez(t)
        tx, ty = tangent(t)
        nx, ny = -ty, tx
        if t < 0.22:
            span = 0.0
        else:
            u = (t - 0.22) / 0.78
            span = S * 0.135 * math.sin(min(1.0, u * 1.25) * math.pi * 0.92) + S * 0.012
        sweep = 0.30           # barbs sweep back toward the nib
        bxl = x + (nx - tx * sweep) * span * 1.12
        byl = y + (ny - ty * sweep) * span * 1.12
        bxr = x - (nx + tx * sweep) * span * 0.88
        byr = y - (ny + ty * sweep) * span * 0.88
        left.append((bxl, byl))
        right.append((bxr, byr))
    silhouette = left + right[::-1]

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon(silhouette, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2)).point(lambda v: 255 if v > 90 else 0)

    ring, _ = outline_of(mask, 6, (60, 52, 44, 255))
    c.alpha_composite(ring)
    body = linear_gradient((S, S), (246, 243, 232, 255), (196, 190, 172, 255), -40)
    c.alpha_composite(clip(body, mask))

    # shade the underside of the vane and draw barb lines
    for i in range(6, N, 2):
        t = i / N
        x, y = bez(t)
        tx, ty = tangent(t)
        nx, ny = -ty, tx
        if t < 0.24:
            continue
        u = (t - 0.22) / 0.78
        span = S * 0.135 * math.sin(min(1.0, u * 1.25) * math.pi * 0.92) + S * 0.012
        sweep = 0.30
        exl = x + (nx - tx * sweep) * span * 1.08
        eyl = y + (ny - ty * sweep) * span * 1.08
        exr = x - (nx + tx * sweep) * span * 0.84
        eyr = y - (ny + ty * sweep) * span * 0.84
        d.line([x, y, exl, eyl], fill=(214, 208, 190, 255), width=3)
        d.line([x, y, exr, eyr], fill=(178, 170, 152, 255), width=3)
    # a few notches so it reads as a feather
    for t, side in [(0.42, 1), (0.58, 1), (0.72, 1), (0.50, -1), (0.66, -1)]:
        x, y = bez(t)
        tx, ty = tangent(t)
        nx, ny = -ty, tx
        u = (t - 0.22) / 0.78
        span = S * 0.135 * math.sin(min(1.0, u * 1.25) * math.pi * 0.92) + S * 0.012
        f = 1.12 if side > 0 else -0.88
        ex = x + (nx - tx * 0.30) * span * f
        ey = y + (ny - ty * 0.30) * span * f
        d.line([ex, ey, ex - (ex - x) * 0.5 + tx * 14, ey - (ey - y) * 0.5 + ty * 14],
               fill=(0, 0, 0, 0), width=10)

    # spine (rachis) over the vane
    pts = [bez(i / N) for i in range(N + 1)]
    d.line(pts, fill=(206, 186, 140, 255), width=9)
    d.line([bez(i / N) for i in range(0, int(N * 0.3))], fill=(196, 168, 116, 255), width=11)

    # nib: darkened tip with a slit, plus a tapered ink stroke below it
    nx0, ny0 = bez(0.0)
    tx, ty = tangent(0.0)
    d.line([nx0 + tx * S * 0.005, ny0 + ty * S * 0.005, nx0 + tx * S * 0.09,
            ny0 + ty * S * 0.09], fill=(120, 96, 56, 255), width=13)
    d.line([nx0, ny0, nx0 + tx * S * 0.045, ny0 + ty * S * 0.045],
           fill=(52, 40, 26, 255), width=9)
    # ink: a swoosh written by the nib, tapering off to the right
    i0 = (nx0 - S * 0.010, ny0 + S * 0.030)
    i1 = (nx0 + S * 0.085, ny0 + S * 0.075)
    i2 = (nx0 + S * 0.200, ny0 + S * 0.020)
    for i in range(41):
        t = i / 40
        mt = 1 - t
        ix = mt * mt * i0[0] + 2 * mt * t * i1[0] + t * t * i2[0]
        iy = mt * mt * i0[1] + 2 * mt * t * i1[1] + t * t * i2[1]
        r = S * 0.008 * (1 - t * 0.85)
        d.ellipse([ix - r, iy - r, ix + r, iy + r], fill=(26, 28, 44, 255))
    return c


def draw_globe():
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx, cy, R = S * 0.5, S * 0.5, S * 0.42

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)

    sea = radial_gradient((S, S), (78, 148, 218, 255), (14, 38, 92, 255),
                          center=(0.40, 0.38), radius=0.62)
    c.alpha_composite(clip(sea, mask))

    # landmasses: hand-placed polygon blobs, darker rim via offset copy
    land = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dl = ImageDraw.Draw(land)
    polys = [
        # big western continent
        [(-0.62, -0.34), (-0.34, -0.56), (-0.06, -0.44), (-0.10, -0.20),
         (-0.32, -0.06), (-0.24, 0.22), (-0.42, 0.46), (-0.62, 0.28), (-0.72, -0.04)],
        # eastern landmass
        [(0.14, -0.24), (0.44, -0.38), (0.72, -0.14), (0.60, 0.16),
         (0.34, 0.24), (0.20, 0.04)],
        # southern island arc
        [(0.06, 0.46), (0.30, 0.40), (0.44, 0.56), (0.22, 0.68), (0.02, 0.62)],
        # northern cap
        [(-0.16, -0.66), (0.12, -0.72), (0.24, -0.56), (0.00, -0.50)],
    ]
    for poly in polys:
        pts = [(cx + R * fx, cy + R * fy) for fx, fy in poly]
        dl.polygon(pts, fill=(84, 156, 60, 255), outline=(40, 88, 34, 255), width=6)
    c.alpha_composite(clip(land, mask))

    # graticule: equator + two meridians, faint parchment-gold like the map icon
    grid = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dg = ImageDraw.Draw(grid)
    col = (235, 226, 190, 72)
    dg.ellipse([cx - R, cy - R * 0.34, cx + R, cy + R * 0.34], outline=col, width=3)
    dg.ellipse([cx - R * 0.42, cy - R, cx + R * 0.42, cy + R], outline=col, width=3)
    dg.ellipse([cx - R * 0.80, cy - R, cx + R * 0.80, cy + R], outline=col, width=3)
    c.alpha_composite(clip(grid, mask))

    # limb shading + specular
    shade = radial_gradient((S, S), (0, 0, 0, 0), (10, 16, 40, 150),
                            center=(0.40, 0.38), radius=0.55)
    c.alpha_composite(clip(shade, mask))
    spec = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(spec).ellipse([cx - R * 0.60, cy - R * 0.68, cx - R * 0.24,
                                  cy - R * 0.36], fill=(255, 255, 255, 42))
    spec = spec.filter(ImageFilter.GaussianBlur(14))
    c.alpha_composite(clip(spec, mask))

    ring, _ = outline_of(mask, 6, (14, 24, 52, 255))
    c.alpha_composite(ring)
    return c


def _unused_draw_lyre():
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    cx, cy, R = S * 0.5, S * 0.52, S * 0.42
    gold = (212, 172, 60, 255)
    gold_hi = (244, 210, 110, 255)
    dark = (92, 66, 20, 255)

    def arm(sign):
        """one S-curved arm: soundbox up to the crossbar, bulging outward"""
        pts = []
        for i in range(41):
            t = i / 40
            # outward bulge that narrows near the top
            bulge = 0.62 + 0.30 * math.sin(t * math.pi) - 0.14 * t
            pts.append((cx + sign * R * bulge, cy + R * (0.55 - 1.35 * t)))
        return pts

    # soundbox: crescent at the bottom joining both arms
    box = [(cx - R * 0.62, cy + R * 0.55)]
    for i in range(21):
        t = i / 20
        a = math.pi * (1 - t)
        box.append((cx + R * 0.62 * math.cos(a), cy + R * 0.55 + R * 0.28 * math.sin(a)))
    for pts, w in [(arm(-1), 30), (arm(1), 30), (box, 34)]:
        d.line(pts, fill=dark, width=w + 14, joint="curve")
    for pts, w in [(arm(-1), 30), (arm(1), 30), (box, 34)]:
        d.line(pts, fill=gold, width=w, joint="curve")
        d.line([(x - 4, y - 4) for x, y in pts], fill=gold_hi, width=w // 3,
               joint="curve")
    # crossbar near the top
    bar_y = cy - R * 0.80
    d.line([cx - R * 0.60, bar_y, cx + R * 0.60, bar_y], fill=dark, width=40)
    d.line([cx - R * 0.58, bar_y, cx + R * 0.58, bar_y], fill=gold, width=26)
    d.line([cx - R * 0.58, bar_y - 5, cx + R * 0.58, bar_y - 5], fill=gold_hi, width=8)
    # strings from crossbar down to the soundbox
    for i in range(5):
        fx = -0.36 + 0.18 * i
        d.line([cx + R * fx, bar_y + 16, cx + R * fx * 0.9, cy + R * 0.50],
               fill=(235, 228, 205, 235), width=6)
    # tuning knobs
    for i in range(5):
        fx = -0.36 + 0.18 * i
        kx, ky = cx + R * fx, bar_y - 20
        d.ellipse([kx - 11, ky - 11, kx + 11, ky + 11], fill=dark)
    return c


# --------------------------------------------------------------------------
# composition + hand-rolled ICO writer
# --------------------------------------------------------------------------
def compose(symbol, size):
    """One icon frame at `size`: pixel dragon + the symbol toward bottom-right."""
    if size % 32 == 0:
        bg = DRAGON.resize((size, size), Image.NEAREST)
    else:
        bg = DRAGON.resize((size, size), Image.LANCZOS)
    frac = FG_FRAC_TINY if size <= 24 else FG_FRAC
    box = max(8, int(round(size * frac)))
    fg = symbol.resize((box, box), Image.LANCZOS)
    x = int(round(size * FG_CENTER[0] - box / 2))
    y = int(round(size * FG_CENTER[1] - box / 2))
    x = min(max(x, 0), size - box)
    y = min(max(y, 0), size - box)
    out = bg.copy()
    out.alpha_composite(fg, (x, y))
    return out


def frame_bmp(img):
    """32bpp BMP icon frame (BITMAPINFOHEADER + BGRA rows + AND mask)."""
    w, h = img.size
    px = img.load()
    hdr = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b, a = px[x, y]
            row += bytes((b, g, r, a))
        rows.append(bytes(row))
    stride = ((w + 31) // 32) * 4
    mrows = []
    for y in range(h - 1, -1, -1):
        row = bytearray(stride)
        for x in range(w):
            if px[x, y][3] < 128:
                row[x >> 3] |= 0x80 >> (x & 7)
        mrows.append(bytes(row))
    return hdr + b"".join(rows) + b"".join(mrows)


def write_ico(frames, path):
    """frames: list of (size, PIL image) largest first; 256 stored as PNG."""
    entries, blobs = [], []
    off = 6 + 16 * len(frames)
    for size, img in frames:
        if size >= 256:
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
        else:
            data = frame_bmp(img)
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                   1, 32, len(data), off))
        blobs.append(data)
        off += len(data)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(frames)))
        f.write(b"".join(entries))
        f.write(b"".join(blobs))


def build(name, symbol):
    frames = [(s, compose(symbol, s)) for s in ICO_SIZES]
    write_ico(frames, os.path.join(OUT, name + ".ico"))
    frames[0][1].save(os.path.join(OUT, name + ".png"))
    print("  wrote", name + ".ico")
    return frames


def main():
    # AoWxBard keeps its legacy icon (black dragon + CD, copied verbatim from
    # reference files\bard_icon.ico into assets\aowxbard.ico) - user decision
    # 2026-08-26. Never regenerate it here.
    builds = [("aowximg", draw_palette()), ("aowxink", draw_quill()),
              ("aowxquest", draw_globe())]
    all_frames = {}
    for name, sym in builds:
        all_frames[name] = build(name, sym)

    # preview sheet: 256 / 48 / 32 / 16 of each tool
    sheet = Image.new("RGBA", (len(builds) * 266 + 10, 256 + 80), (58, 58, 58, 255))
    for i, (name, _) in enumerate(builds):
        fr = dict((s, im) for s, im in all_frames[name])
        sheet.alpha_composite(fr[256], (8 + i * 266, 8))
        x = 8 + i * 266
        for s in (48, 32, 16):
            sheet.alpha_composite(fr[s], (x, 272))
            x += s + 12
    sheet.save(os.path.join(OUT, "icons_preview.png"))
    print("done ->", OUT)


if __name__ == "__main__":
    main()
