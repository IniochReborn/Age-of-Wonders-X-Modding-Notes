"""The user's reference (art import export/lionheart idea.jpg: a tribal black-on-white lion head, front view) -> 40x35 ink
mask (black = ink).  Crop to the lion, threshold, fit, light blur so the thin mane strands survive the downsample."""
from PIL import Image, ImageFilter, ImageOps
import numpy as np
SRC = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\art import export\lionheart idea.jpg"
OUT = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts\lion_user_mask.png"
PREV = r"C:\Users\<user>\.claude\jobs\47241cad\tmp\lion_user_prev.png"
im = Image.open(SRC).convert("L")
a = np.array(im); H, W = a.shape
# the lion occupies roughly rows 130..880 of 1136; find the exact bbox of dark pixels inside that band
band = a[120:890, :]; dark = band < 110
ys, xs = np.where(dark); y0, y1, x0, x1 = ys.min() + 120, ys.max() + 120, xs.min(), xs.max(); print("bbox", x0, y0, x1, y1)
crop = im.crop((x0, y0, x1 + 1, y1 + 1))
ink = ImageOps.invert(crop).point(lambda v: 255 if v > 140 else 0)      # ink = 255 where the drawing is black
Wt, Ht = 40, 35; sc = min(Wt / ink.width, Ht / ink.height); nw, nh = int(round(ink.width * sc)), int(round(ink.height * sc))
small = ink.filter(ImageFilter.GaussianBlur(0.9)).resize((nw, nh), Image.LANCZOS).point(lambda v: 255 if v > 118 else (0 if v < 60 else v))   # crisp: binarise the middle greys
out = Image.new("L", (Wt, Ht), 0); out.paste(small, ((Wt - nw) // 2, (Ht - nh) // 2))
out.save(OUT); print("mask ->", OUT, "size", (nw, nh))
prev = Image.new("L", (Wt * 8 + 20 + 300, max(Ht * 8, 300)), 128)
prev.paste(out.resize((Wt * 8, Ht * 8), Image.NEAREST), (0, 0)); prev.paste(ink.resize((300, int(300 * ink.height / ink.width))), (Wt * 8 + 20, 0)); prev.save(PREV); print("preview ->", PREV)
