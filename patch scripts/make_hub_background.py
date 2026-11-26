"""Compose modding tools/assets/aowxhub_bg.png - the AoWxHub window background.

Built from AoWSetup.exe's own 398x450 home-screen BMP (TLoaderForm DFM,
file offset 0x7eda3). Canvas = 398x449, the home window's TRUE runtime
client size (FormCreate ends with SetClientWidth(398)/SetClientHeight(449)
@0x468DC7 - the DFM's 420x525 is only the install-mode layout), so the hub
window is pixel-for-pixel the size of the screen it replaces:

  - frame top + the Age of Wonders X logo art (BMP rows 0..156, cut just
    above Julia's head) at (0,0)
  - the greek-key divider line (BMP rows 404..415)
  - SEVEN full-width stone-slab bars, synthesised seamlessly from one home
    slab's texture: six 36px tool bars (name + description drawn by the app)
    and one 22px Exit bar
  - the BMP's bottom frame, with its side borders tiled down the flanks

Button rects for AoWxHub.py (window coords):
  tools: x=14 w=370 h=36 at y = 171 + i*39 (i = 0..5)
  exit : x=14 w=370 h=22 at y = 407
"""
import io
import os
import struct

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
OUT = os.path.join(GAME, "modding tools", "assets", "aowxhub_bg.png")

BMP_OFF = 0x7EDA3
W, H = 398, 449              # the home window's true runtime client size
FILL = (10, 7, 6)

data = open(os.path.join(GAME, "AoWSetup.exe"), "rb").read()
assert data[BMP_OFF:BMP_OFF + 2] == b"BM"
size = struct.unpack_from("<I", data, BMP_OFF + 2)[0]
bg = Image.open(io.BytesIO(data[BMP_OFF:BMP_OFF + size])).convert("RGB")
assert bg.size == (398, 450), bg.size


# the home screen's FOUR slabs (92x21 each, bevels included). v2: the first
# version tiled slab #1's 84px face ~4.4x per bar, so every dark blotch
# repeated constantly and the button text was hard to read over the noise.
SLABS = [(14, 415, 106, 436), (107, 415, 199, 436),
         (200, 415, 292, 436), (293, 415, 385, 436)]
EDGE = 4


def slab_bar(w, h):
    """A seamless full-width slab with NO repeating pattern: all four home
    slabs' faces concatenated (336px of unique texture) and gently stretched
    to the bar's inner width; taller bars stretch the face rows smoothly
    (LANCZOS softens the mottling rather than duplicating it)."""
    import numpy as np
    slabs = [bg.crop(r) for r in SLABS]
    left = slabs[0].crop((0, 0, EDGE, 21))
    right = slabs[3].crop((92 - EDGE, 0, 92, 21))
    faces = [s.crop((EDGE, 0, 92 - EDGE, 21)) for s in slabs]
    # concatenate with a 12px cross-fade at each join (butt joins leave a
    # visible texture discontinuity even after the gradient flattening)
    import numpy as np
    OV = 12
    arrs = [np.asarray(f, dtype=np.float64) for f in faces]
    ramp = np.linspace(0.0, 1.0, OV)[None, :, None]
    acc = arrs[0]
    for nxt in arrs[1:]:
        blend = acc[:, -OV:] * (1 - ramp) + nxt[:, :OV] * ramp
        acc = np.concatenate([acc[:, :-OV], blend, nxt[:, OV:]], axis=1)
    wide = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8))
    # each slab is lit with its own left->right gradient, so plain
    # concatenation shows sawtooth luminance seams at the joins. Flatten the
    # strip's smoothed per-column brightness profile, then re-apply ONE
    # gentle global gradient (sampled from slab #1's own profile shape).
    a = np.asarray(wide, dtype=np.float64)
    k = 15                                           # smoothing window
    kern = np.ones(2 * k + 1) / (2 * k + 1)
    for c in range(3):                               # per channel: kills hue
        col = a[:, :, c].mean(axis=0)                # drift between slabs too
        smooth = np.convolve(np.pad(col, k, mode="edge"), kern, "valid")
        target = np.linspace(smooth[:20].mean(), smooth[-20:].mean(), len(col))
        target *= smooth.mean() / target.mean()      # keep the slabs' brightness
        a[:, :, c] *= target / smooth
    wide = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    inner = wide.resize((w - 2 * EDGE, 21), Image.LANCZOS)   # 336 -> 362
    bar = Image.new("RGB", (w, 21))
    bar.paste(left, (0, 0))
    bar.paste(inner, (EDGE, 0))
    bar.paste(right, (w - EDGE, 0))
    if h == 21:
        return bar
    # taller bars: keep the 4px bevels crisp, stretch only the face rows
    top = bar.crop((0, 0, w, 4))
    mid = bar.crop((0, 4, w, 17))
    bot = bar.crop((0, 17, w, 21))
    out = Image.new("RGB", (w, h))
    out.paste(top, (0, 0))
    out.paste(mid.resize((w, h - 8), Image.LANCZOS), (0, 4))
    out.paste(bot, (0, h - 4))
    return out


canvas = Image.new("RGB", (W, H), FILL)

# frame top + logo art, cut just above Julia's head (hair top = BMP row ~162)
art = bg.crop((0, 0, 398, 156))
canvas.paste(art, (0, 0))                            # 0..156
divider = bg.crop((0, 404, 398, 415))
canvas.paste(divider, (0, 156))                      # 156..167

# side borders down the button zone (167..437)
lb = bg.crop((0, 300, 14, 340))
rb = bg.crop((384, 300, 398, 340))
y = 167
while y < 437:
    hseg = min(40, 437 - y)
    canvas.paste(lb.crop((0, 0, 14, hseg)), (0, y))
    canvas.paste(rb.crop((0, 0, 14, hseg)), (W - 14, y))
    y += hseg

tool_bar = slab_bar(370, 36)
for i in range(6):
    canvas.paste(tool_bar, (14, 171 + i * 39))       # 171..402
canvas.paste(slab_bar(370, 22), (14, 407))           # Exit 407..429

bottom = bg.crop((0, 438, 398, 450))
canvas.paste(bottom, (0, 437))                       # 437..449

canvas.save(OUT)
print("saved %s (%dx%d)" % (OUT, W, H))
