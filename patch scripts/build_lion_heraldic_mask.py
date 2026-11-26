"""Trace the heraldic lion head (Wikimedia Commons 'Meuble heraldique Tete (lion).svg', outline art) into a 40x35 ink
mask: fill the interior of the outer contour, cut out the eye and the open mouth, crop, fit and save."""
import os, sys
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
from collections import deque
SRC = r"C:\Users\<user>\.claude\jobs\47241cad\tmp\lion_her.png"
OUT = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts\lion_heraldic_mask.png"
PREV = r"C:\Users\<user>\.claude\jobs\47241cad\tmp\lion_trace_prev.png"
im = Image.open(SRC).convert("RGBA")
bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.paste(im, (0, 0), im); rgb = np.array(bg.convert("RGB")).astype(int)
line = (rgb.sum(2) < 200)                                  # the black outline
blue = (rgb[:, :, 2] > 150) & (rgb[:, :, 0] < 120)         # the tongue
H, W = line.shape
# exterior = white connected to the border (through non-line pixels)
ext = np.zeros((H, W), bool); q = deque()
for x in range(W):
    for y in (0, H - 1):
        if not line[y, x] and not ext[y, x]: ext[y, x] = True; q.append((y, x))
for y in range(H):
    for x in (0, W - 1):
        if not line[y, x] and not ext[y, x]: ext[y, x] = True; q.append((y, x))
while q:
    y, x = q.popleft()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < H and 0 <= nx < W and not ext[ny, nx] and not line[ny, nx]: ext[ny, nx] = True; q.append((ny, nx))
ink = ~ext                                                 # everything inside the outer contour (lines included)
# cut-outs: the enclosed regions that contain the tongue (mouth) and the eye.  Enclosed regions = non-line, non-exterior
lab = np.zeros((H, W), int); nlab = 0; sizes = {}; has_blue = {}; cy_of = {}; cx_of = {}
for y in range(H):
    for x in range(W):
        if line[y, x] or ext[y, x] or lab[y, x]: continue
        nlab += 1; q.append((y, x)); lab[y, x] = nlab; n = 0; b = 0; sy = 0; sx = 0
        while q:
            yy, xx = q.popleft(); n += 1; sy += yy; sx += xx; b += blue[yy, xx]
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = yy + dy, xx + dx
                if 0 <= ny < H and 0 <= nx < W and not lab[ny, nx] and not line[ny, nx] and not ext[ny, nx]: lab[ny, nx] = nlab; q.append((ny, nx))
        sizes[nlab] = n; has_blue[nlab] = b; cy_of[nlab] = sy / n; cx_of[nlab] = sx / n
regions = sorted(sizes, key=lambda k: -sizes[k])
print("regions (size, blue px, centre):", [(sizes[k], has_blue[k], int(cx_of[k]), int(cy_of[k])) for k in regions[:12]])
cut = np.zeros((H, W), bool)
for k in regions:
    if has_blue[k] > 50 or (1500 < sizes[k] < 4000 and 280 < cx_of[k] < 330 and 230 < cy_of[k] < 290): cut |= (lab == k); print("mouth region", k, sizes[k])
# the eye: a small enclosed region in the upper-left part of the head (x 230..330, y 80..130 in the 600x700 render)
for k in regions:
    if 20 < sizes[k] < 4000 and 220 < cx_of[k] < 340 and 70 < cy_of[k] < 140 and has_blue[k] == 0: cut |= (lab == k); print("eye region", k, sizes[k], int(cx_of[k]), int(cy_of[k]))
mask = ink & ~cut
mask[575:, :] = False                                      # drop the lowest mane flames: a bigger head in the icon
ys, xs = np.where(mask); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max(); print("bbox", x0, y0, x1, y1)
m = Image.fromarray((mask[y0:y1 + 1, x0:x1 + 1] * 255).astype(np.uint8), "L")
# fit into 40x35 keeping aspect, centred; a little blur before the downsample so thin outline parts survive
Wt, Ht = 40, 35; sc = min(Wt / m.width, Ht / m.height); nw, nh = max(1, int(round(m.width * sc))), max(1, int(round(m.height * sc)))
small = m.filter(ImageFilter.GaussianBlur(1.2)).resize((nw, nh), Image.LANCZOS)
out = Image.new("L", (Wt, Ht), 0); out.paste(small, ((Wt - nw) // 2, (Ht - nh) // 2))
out.save(OUT); print("mask ->", OUT)
# preview: 8x nearest + the full-size trace
prev = Image.new("L", (Wt * 8 + 20 + (x1 - x0 + 1) // 2, max(Ht * 8, (y1 - y0 + 1) // 2)), 128)
prev.paste(out.resize((Wt * 8, Ht * 8), Image.NEAREST), (0, 0)); prev.paste(m.resize(((x1 - x0 + 1) // 2, (y1 - y0 + 1) // 2)), (Wt * 8 + 20, 0)); prev.save(PREV); print("preview ->", PREV)
