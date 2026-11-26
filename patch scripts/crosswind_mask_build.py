import sys, os
from PIL import Image, ImageFilter, ImageChops
import numpy as np
from collections import deque
D = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude"
im = Image.open(os.path.join(D, "art import export", "crosswind.jpg")).convert("L")
ink = im.point(lambda v: 255 if v < 128 else 0)
ink = ink.filter(ImageFilter.MaxFilter(int(sys.argv[1]) if len(sys.argv) > 1 else 7))          # thicken lines (default 7)
from PIL import ImageDraw
ImageDraw.Draw(ink).line([(76, 512), (118, 582)], fill=255, width=10)     # close the wrist so the hand outline encloses the palm
a = np.asarray(ink) > 128; H, W = a.shape
# fill enclosed holes (the hand outline -> solid hand): flood the background from the border
bg = np.zeros_like(a); q = deque()
for x in range(W): q.append((0, x)); q.append((H - 1, x))
for y in range(H): q.append((y, 0)); q.append((y, W - 1))
while q:
    y, x = q.popleft()
    if 0 <= y < H and 0 <= x < W and not a[y, x] and not bg[y, x]:
        bg[y, x] = True; q.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
holes = ~bg & ~a                                                    # enclosed regions; fill ONLY the largest (the palm)
hl = np.zeros(a.shape, np.int32); sizes = {}; k = 0
for y in range(H):
    for x in range(W):
        if holes[y, x] and not hl[y, x]:
            k += 1; q = deque([(y, x)]); hl[y, x] = k; c = 0
            while q:
                cy, cx = q.popleft(); c += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = cy + dy, cx + dx
                    if 0 <= yy < H and 0 <= xx < W and holes[yy, xx] and not hl[yy, xx]: hl[yy, xx] = k; q.append((yy, xx))
            sizes[k] = c
big = sorted(sizes, key=sizes.get, reverse=True)[:int(sys.argv[2]) if len(sys.argv) > 2 else 1]
solid = a | np.isin(hl, big)
# drop dust dots / specks: components smaller than 1200 px at source size
lab = np.zeros(a.shape, np.int32); n = 0; keep = np.zeros_like(a)
for y in range(H):
    for x in range(W):
        if solid[y, x] and not lab[y, x]:
            n += 1; q = deque([(y, x)]); lab[y, x] = n; comp = []
            while q:
                cy, cx = q.popleft(); comp.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = cy + dy, cx + dx
                    if 0 <= yy < H and 0 <= xx < W and solid[yy, xx] and not lab[yy, xx]: lab[yy, xx] = n; q.append((yy, xx))
            if len(comp) >= 1200:
                for cy, cx in comp: keep[cy, cx] = True
m = Image.fromarray((keep * 255).astype(np.uint8))
bb = m.getbbox(); m = m.crop(bb)
TW, TH = 320, 280; sc = min(TW * 0.98 / m.width, TH * 0.95 / m.height)
r = m.resize((int(m.width * sc), int(m.height * sc)), Image.LANCZOS)
out = Image.new("L", (TW, TH), 0); out.paste(r, ((TW - r.width) // 2, (TH - r.height) // 2))
out = out.filter(ImageFilter.GaussianBlur(1.2)).point(lambda v: 255 if v >= 128 else 0)
out.save(os.path.join(D, "patch scripts", "crosswind_user_mask.png"))
