"""Banshee Gale (344) icon mask v11 (2026-10-16; user: start fresh with the new art import export/banshee.jpg - a
long-haired banshee crawling out of a swirl of grey shroud): the WHOLE figure (grey shroud + black hair/body) as ink,
with a thin clear line cut where the black hair/body meets the grey shroud so the two still read apart at 40x35;
only the main connected figure is kept (the drifting flower bits and the signature drop out)."""
from PIL import Image, ImageFilter, ImageChops, ImageDraw
src = Image.open("../art import export/banshee.jpg").convert("L")
sil = src.point(lambda v: 255 if v < 205 else 0)
black = src.point(lambda v: 255 if v < 70 else 0)
blackm = black.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.MinFilter(15))           # hair strands merged into masses
ring = ImageChops.subtract(blackm.filter(ImageFilter.MaxFilter(11)), blackm)                     # one outline round each mass
cut = ImageChops.multiply(ring, sil)
mask = ImageChops.subtract(sil, cut)
SEED = next((x, y) for y in range(300, 420) for x in range(300, 420) if src.getpixel((x, y)) < 60)
keep = sil.copy(); ImageDraw.floodfill(keep, SEED, 128)                     # the main figure only
keep = keep.point(lambda v: 255 if v == 128 else 0)
mask = ImageChops.multiply(mask, keep)
bb = keep.getbbox(); mask = mask.crop(bb)
W, H = 320, 280
sc = min(W / mask.width, H / mask.height) * 0.99; w, h = round(mask.width * sc), round(mask.height * sc)
out = Image.new("L", (W, H), 0); out.paste(mask.resize((w, h), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0), ((W - w) // 2, (H - h) // 2))
out.save("banshee4_user_mask.png"); print(src.size, bb, (w, h))
