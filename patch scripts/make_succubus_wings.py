"""Succubus icon mask (347) v4 (2026-10-16; user: v3 bat-wing redraw was all messed up - revert to the traced
feathered wings, simply get rid of the lines in the wings and make the BOTTOMS of the wings webbed like a bat).
Input succubus_feather_mask.png (the traced reference, untouched) -> succubus_user_mask.png:
  1. the wings (everything outside the body/hair polygon) get their inner feather slits closed (Max/Min filter) -
     solid wings, same outline;
  2. along each wing's lower edge the bottom is cut into bat-membrane scallops: between evenly spaced 'finger' tips the
     edge sags upward in arcs."""
import math
from PIL import Image, ImageDraw, ImageFilter, ImageChops
base = Image.open("succubus_feather_mask.png").convert("L")
W, H = base.size
Q = lambda pts: [(x * 4, y * 4) for x, y in pts]
bodyp = Image.new("L", base.size, 0)
ImageDraw.Draw(bodyp).polygon(Q([(32, 2), (49, 2), (50, 8), (61, 10), (59, 27), (49, 34), (48, 46), (46, 56), (46, 69), (35, 69), (36, 56), (32, 46), (30, 36), (31, 15), (32, 8)]), fill=255)
wreg = bodyp.point(lambda v: 255 - v)
body = ImageChops.multiply(base, bodyp)
wings = ImageChops.multiply(base, wreg)
pad = Image.new("L", (W + 40, H + 40), 0); pad.paste(wings, (20, 20))
solid = pad.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.MinFilter(13)).crop((20, 20, W + 20, H + 20))
solid = ImageChops.multiply(solid, wreg)
sp = solid.load()
for sg, xa, xb in ((-1, 0, W // 2), (1, W // 2, W)):                           # bat scallops: the lower edge re-cut
    cols = [x for x in range(xa, xb) if any(sp[x, y] for y in range(H))]
    if not cols: continue
    xo = min(cols) if sg < 0 else max(cols)                                    # the outer-most column
    ys = [y for y in range(H) if sp[xo, y]]; ya = sum(ys) / len(ys) + 6          # A: the wing's outer point
    xi = (min(cols) + max(cols)) / 2 + sg * 0.0
    xi = max(cols) if sg < 0 else min(cols)                                    # B: next to the body, at the wing's bottom
    yb = max(y for y in range(H) if any(sp[x, y] for x in range(min(xi, xi - sg * 12), max(xi, xi - sg * 12) + 1)))
    n = 4
    for x in cols:
        t = (x - xo) / (xi - xo)                                               # 0 at A .. 1 at B
        if t < 0 or t > 1: continue
        base_y = ya + (yb - ya) * t
        u = (t * n) % 1.0; sag = math.sin(math.pi * u) * 16
        cut = base_y - sag
        for y in range(int(cut), H): sp[x, y] = 0
solid.paste(0, mask=body.filter(ImageFilter.MaxFilter(7)))                    # a dark gap round the body + hair (their real outline)
out = ImageChops.lighter(solid, body)
out.save("succubus_wings_v4_rejected.png")   # 2026-10-16: user rejected the wing edits - succubus_user_mask.png = the feathered trace again
