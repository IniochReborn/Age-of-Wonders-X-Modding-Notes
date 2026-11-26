"""Static Shield (215) icon SHELL builder (2026-10-16, user: use the outer shell of art import export/static shield
general inspiration.png, reshaped slightly to follow Stone Skin's outer-shell silhouette; the man stays unchanged):
binarise the reference, drop the man (the biggest blob), fit the remaining lightning shell into Stone Skin's aura box
(icon px x 5..36, y 3..33) -> staticshield_shell_mask.png (320x280, white = ink)."""
import os
import numpy as np
from collections import deque
from PIL import Image, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
im = Image.open(os.path.join(HERE, "..", "art import export", "static shield general inspiration.png")).convert("L")
a = np.asarray(im) < 128; H, W = a.shape
lab = np.zeros(a.shape, np.int32); n = 0; sizes = {}
for y in range(H):
    for x in range(W):
        if a[y, x] and not lab[y, x]:
            n += 1; q = deque([(y, x)]); lab[y, x] = n; c = 0
            while q:
                cy, cx = q.popleft(); c += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = cy + dy, cx + dx
                    if 0 <= yy < H and 0 <= xx < W and a[yy, xx] and not lab[yy, xx]: lab[yy, xx] = n; q.append((yy, xx))
            sizes[n] = c
man = max(sizes, key=sizes.get)
keep = [k for k, c in sizes.items() if k != man and c >= 20000]          # v2 (user): the OUTER shell only (top/left/right), inner bolts dropped
shell = (a & np.isin(lab, keep)).astype(np.uint8) * 255
sh = Image.fromarray(shell); bb = sh.getbbox(); sh = sh.crop(bb)
S = 8; X0, Y0, X1, Y1 = 5 * S, 3 * S, 36 * S, 33 * S                     # Stone Skin's aura box
sh = sh.resize((X1 - X0, Y1 - Y0), Image.LANCZOS)
m = Image.new("L", (40 * S, 35 * S), 0); m.paste(sh, (X0, Y0))
m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.0)).point(lambda v: 255 if v >= 110 else 0)
from PIL import ImageDraw                                                  # v3 (user: no gap on the RIGHT of the shell): a jagged
ImageDraw.Draw(m).line([(236, 100), (252, 104), (246, 112), (262, 116), (266, 126)], fill=255, width=11, joint="curve")   # bridge
m.save(os.path.join(HERE, "staticshield_shell_mask.png")); print("man blob", sizes[man], "shell bbox", bb)
