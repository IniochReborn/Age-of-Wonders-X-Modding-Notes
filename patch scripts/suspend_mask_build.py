"""Suspend (214) icon mask builder (2026-10-16): traces the user's art import export/suspend.jpg (a figure arched backward,
floating) -> suspend_user_mask.png (320x280 = 40x35 icon at 8x, white = ink): the figure fitted across the upper part,
with two narrow elongated rings beneath it (v2; v1 had three wind streaks) (a dark gap keeps them clear of the body)."""
import os, math
from PIL import Image, ImageDraw, ImageFilter, ImageChops
HERE = os.path.dirname(os.path.abspath(__file__))
im = Image.open(os.path.join(HERE, "..", "art import export", "suspend.jpg")).convert("L")
ink = im.point(lambda v: 255 if v < 128 else 0)
fig = ink.crop(ink.getbbox())
TW, TH = 320, 280
sc = min(300 / fig.width, 165 / fig.height)
fig = fig.resize((int(fig.width * sc), int(fig.height * sc)), Image.LANCZOS)
m = Image.new("L", (TW, TH), 0); fx, fy = (TW - fig.width) // 2, 22
m.paste(fig, (fx, fy))
m = m.filter(ImageFilter.GaussianBlur(1.2)).point(lambda v: 255 if v >= 128 else 0)
wind = Image.new("L", (TW, TH), 0); d = ImageDraw.Draw(wind)
# v2 (user 10/16: replace the wind lines with two narrow elongated RINGS, the top one widest, a smaller one below it)
d.ellipse([160 - 128, 214 - 15, 160 + 128, 214 + 15], outline=255, width=10)
d.ellipse([160 - 84, 250 - 11, 160 + 84, 250 + 11], outline=255, width=9)
gap = m.filter(ImageFilter.MaxFilter(17))
wind = ImageChops.subtract(wind, gap)
out = ImageChops.lighter(m, wind)
out.save(os.path.join(HERE, "suspend_user_mask.png")); print("written suspend_user_mask.png")
