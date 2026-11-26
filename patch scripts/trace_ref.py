"""trace_ref.py <src image> <out mask.png> [fill 0.96] [thicken px at 320x280]  -- trace a black-on-white reference into a
320x280 icon mask (white = ink): binarise, crop to the ink, fit centred (bottom-aligned when it touches the floor),
smooth edges (blur + threshold), optional thickening.  2026-10-16."""
import sys
from PIL import Image, ImageFilter, ImageOps
src, out = sys.argv[1], sys.argv[2]; fill = float(sys.argv[3]) if len(sys.argv) > 3 else 0.96; thick = int(sys.argv[4]) if len(sys.argv) > 4 else 0
im = Image.open(src).convert("L"); ink = im.point(lambda v: 255 if v < 128 else 0); ink = ink.crop(ink.getbbox())
TW, TH = 320, 280; sc = min(TW * fill / ink.width, TH * fill / ink.height)
r = ink.resize((max(1, int(ink.width * sc)), max(1, int(ink.height * sc))), Image.LANCZOS)
m = Image.new("L", (TW, TH), 0); m.paste(r, ((TW - r.width) // 2, (TH - r.height) // 2))
m = m.filter(ImageFilter.GaussianBlur(1.2)).point(lambda v: 255 if v >= 128 else 0)
if thick: m = m.filter(ImageFilter.MaxFilter(thick * 2 + 1))
m.save(out)
