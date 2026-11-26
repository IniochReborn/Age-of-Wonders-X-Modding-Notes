"""Call of the Dead (211) icon mask builder (2026-10-16): traces the user's art import export/call of the dead.jpg
(5 zombie hands from grass) -> callofdead_user_mask.png.  Steps: binarise, erase the magnifier badge, a 9 px opening
drops the grass blades, solid mound; the odd 2nd hand -> the 1st hand mirrored x1.1 on a forearm; the far-left hand
-> the MIDDLE arm mirrored, standing slightly lower than it (user 10/16); flatter mound so every arm stands on it;
smooth + despeckle."""
from PIL import Image, ImageFilter, ImageDraw, ImageOps, ImageChops
import numpy as np, os
from collections import deque
HERE = os.path.dirname(os.path.abspath(__file__))
im = Image.open(os.path.join(HERE, "..", "art import export", "call of the dead.jpg")).convert("L"); W0, H0 = im.size
ink = im.point(lambda v: 255 if v < 128 else 0); d = ImageDraw.Draw(ink); d.rectangle([940, 770, W0, H0], fill=0)
op = ink.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.MaxFilter(9))
d = ImageDraw.Draw(op); d.rectangle([0, 740, W0, H0], fill=255)
mask = Image.new("L", op.size, 255); md = ImageDraw.Draw(mask); md.rectangle([0, 700, W0, H0], fill=0); md.ellipse([-120, 700, W0 + 120, H0 + 260], fill=255)
op = Image.composite(op, Image.new("L", op.size, 0), mask)
bb = op.getbbox(); op = op.crop((bb[0], bb[1], bb[2], H0 - 40))
TW, TH = 320, 280; sc = min(TW * 0.98 / op.width, TH * 0.98 / op.height)
r = op.resize((int(op.width * sc), int(op.height * sc)), Image.LANCZOS)
m = Image.new("L", (TW, TH), 0); m.paste(r, ((TW - r.width) // 2, TH - r.height))
m = m.filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: 255 if v >= 128 else 0)
a = np.asarray(m) > 128
# the middle arm = the ink in columns 150..214 above y 214 (its own columns only, so nothing else is caught)
mid = np.zeros_like(a); mid[40:140, 150:215] = a[40:140, 150:215]; mid[140:214, 150:204] = a[140:214, 150:204]   # below y 140 the 4th hand starts at x ~205
ys, xs = np.where(mid); arm = Image.fromarray((mid * 255).astype(np.uint8)).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
arm = ImageOps.mirror(arm)
hand = m.crop((10, 140, 64, 226))                                           # 1st hand (for the 2nd-hand swap)
d = ImageDraw.Draw(m); d.rectangle([0, 40, 153, 236], fill=0)               # clear hands 1 + 2
h2 = ImageOps.mirror(hand); h2 = h2.resize((int(h2.width * 1.1), int(h2.height * 1.1)), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
bx, by = 78, 214 - h2.height
lay = Image.new("L", m.size, 0); lay.paste(h2, (bx, by))
ha = np.asarray(h2) > 128; cols = np.where(ha[-3:].any(axis=0))[0]; wx0, wx1 = bx + cols.min(), bx + cols.max()
ImageDraw.Draw(lay).polygon([(wx0, 212), (wx1, 212), (wx1 + 4, 240), (wx0 - 4, 240)], fill=255)
m = ImageChops.lighter(m, lay)
LEFT_X, DROP = 4, 16                                                        # far-left arm: mirrored middle arm, 16 px lower
lay = Image.new("L", m.size, 0); lay.paste(arm, (LEFT_X, ys.min() + DROP))
aw = np.asarray(arm) > 128; cols = np.where(aw[-3:].any(axis=0))[0]; ax0, ax1 = LEFT_X + cols.min(), LEFT_X + cols.max(); abot = ys.min() + DROP + arm.height
ImageDraw.Draw(lay).polygon([(ax0, abot - 2), (ax1, abot - 2), (ax1 + 3, 242), (ax0 - 3, 242)], fill=255)
m = ImageChops.lighter(m, lay)
d = ImageDraw.Draw(m); d.ellipse([-80, 220, 400, 344], fill=255)
m = m.filter(ImageFilter.GaussianBlur(0.8)).point(lambda v: 255 if v >= 128 else 0)
arr = np.asarray(m) > 128; seen = np.zeros_like(arr); out = arr.copy()
for y in range(arr.shape[0]):
    for x in range(arr.shape[1]):
        if arr[y, x] and not seen[y, x]:
            q = deque([(y, x)]); seen[y, x] = True; comp = []
            while q:
                cy, cx = q.popleft(); comp.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = cy + dy, cx + dx
                    if 0 <= yy < arr.shape[0] and 0 <= xx < arr.shape[1] and arr[yy, xx] and not seen[yy, xx]: seen[yy, xx] = True; q.append((yy, xx))
            if len(comp) < 30:
                for cy, cx in comp: out[cy, cx] = False
Image.fromarray((out * 255).astype(np.uint8)).save(os.path.join(HERE, "callofdead_user_mask.png"))
