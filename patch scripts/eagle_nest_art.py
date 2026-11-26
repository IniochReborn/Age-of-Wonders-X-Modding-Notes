#!/usr/bin/env python3
r"""
Great Eagle's Nest art (2026-10-31).

User: "great eagles nest ... its GFX is bad, rework it, maybe add small bird circling it. and it needs a side
image (currently reuses teleporter)".
  map_frames(game_dir) -> 5 RGBA 60x65 sprites (terrain variants of the vanilla, otherwise unused PRO_DRGN.ILB
      spire 0..4): purple shadows -> cool grey-brown stone, the purple egg cluster -> a woven twig nest with an
      eagle perched on it (white head, yellow beak);
  bird_frames() -> 24 RGBA 64x40 frames: a small bird circling the nest (flapping, smaller/lighter on the far side);
  side_images() -> (top 57x2, middle 57x50, bottom 57x278) side-window portrait in the B_* style: dusk sky with
      soft clouds, distant ridges, a tall crag topped by the nest, an eagle with spread wings above it.
--preview <dir> writes sheets.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import ilb  # noqa: E402

TWIG_DARK, TWIG_MID, TWIG_LIGHT = (58, 40, 22), (104, 74, 42), (150, 116, 72)
EAGLE_BODY, EAGLE_LIGHT = (72, 46, 26), (118, 82, 48)
WHITE, BEAK = (238, 236, 226), (232, 182, 46)


def _load(game_dir, name):
    lib = ilb.read(open(os.path.join(game_dir, "Images", name), "rb").read())
    return lib, {im.id: im for im in lib.images}


def _rgba(lib, rec):
    w, h, rows = ilb.decode_record(lib, rec)
    return np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)


def _hsv(a):
    import colorsys
    return np.array([[colorsys.rgb_to_hsv(*(p[:3] / 255.0)) for p in row] for row in a.astype(float)])


def _put(a, x, y, col, alpha=255):
    h, w = a.shape[:2]
    if 0 <= x < w and 0 <= y < h:
        a[y, x, :3] = col; a[y, x, 3] = alpha


def _nest(a, cx, cy, rx, ry, rng):
    """woven twig bowl centred at (cx, cy)"""
    for _ in range(int(rx * ry * 5)):
        t = rng.uniform(0, 2 * math.pi); r = math.sqrt(rng.uniform(0.15, 1.0))
        x0, y0 = cx + math.cos(t) * rx * r, cy + math.sin(t) * ry * r + 1
        ang = rng.uniform(-0.5, 0.5) + (0 if rng.random() < 0.7 else math.pi / 2)
        ln = rng.uniform(2, 5)
        col = (TWIG_DARK, TWIG_MID, TWIG_LIGHT)[min(2, int((math.sin(t) * 0.5 + 0.5) * 2.2 + rng.uniform(0, 0.8)))]
        for s in np.linspace(0, ln, int(ln * 2) + 1):
            _put(a, int(round(x0 + math.cos(ang) * s)), int(round(y0 + math.sin(ang) * s * 0.5)), col)
    # dark hollow on top
    for y in range(int(cy - ry), int(cy + 1)):
        for x in range(int(cx - rx * 0.6), int(cx + rx * 0.6) + 1):
            if ((x - cx) / (rx * 0.62)) ** 2 + ((y - cy + ry * 0.35) / (ry * 0.55)) ** 2 <= 1:
                _put(a, x, y, (38, 26, 16))
    # a few sticks poking out
    for k in range(7):
        t = math.pi + k / 6 * math.pi + rng.uniform(-0.2, 0.2)
        x0, y0 = cx + math.cos(t) * rx * 0.9, cy + math.sin(t) * ry * 0.9
        for s in range(3):
            _put(a, int(round(x0 + math.cos(t) * s)), int(round(y0 + math.sin(t) * s * 0.5)), TWIG_LIGHT)


def _perched_eagle(a, cx, cy):
    """~7x10 px eagle sitting in the nest, facing right"""
    for y in range(-4, 5):
        for x in range(-3, 4):
            if (x / 3.2) ** 2 + (y / 4.6) ** 2 <= 1:
                _put(a, cx + x, cy + y, EAGLE_LIGHT if x < -1 else EAGLE_BODY)
    for x, y in ((-3, 2), (-3, 3), (-2, 4), (3, 3)):
        _put(a, cx + x, cy + y, (52, 34, 20))
    for y in range(-3, 0):
        for x in range(-1, 3):
            if (x - 0.5) ** 2 / 3.2 + (y + 1.5) ** 2 / 2.2 <= 1:
                _put(a, cx + x, cy - 4 + y, WHITE)
    _put(a, cx + 3, cy - 6, BEAK); _put(a, cx + 3, cy - 5, (196, 140, 30))
    _put(a, cx + 1, cy - 6, (20, 16, 12))


def map_frames(game_dir):
    lib, by = _load(game_dir, "PRO_DRGN.ILB")
    rng = np.random.default_rng(0xEA61)
    out = []
    for k in range(5):
        a = _rgba(lib, by[k].primary).copy()
        hsv = _hsv(a)
        m = a[..., 3] > 0
        purple = m & (hsv[..., 0] > 0.62) & (hsv[..., 0] < 0.97) & (hsv[..., 1] > 0.10)
        lum = a[..., :3].astype(float) @ np.array([0.299, 0.587, 0.114])
        for c, t in enumerate((1.02, 0.97, 0.90)):
            a[..., c] = np.where(purple, np.clip(lum * t * 1.05, 0, 255), a[..., c])
        # clear the egg cluster (everything above the spire neck)
        top = 25
        neck = [x for x in range(a.shape[1]) if a[top, x, 3]]
        a[:top, :, 3] = 0
        a[:top, :, :3] = 0
        nx = (min(neck) + max(neck)) // 2 if neck else 31
        _nest(a, nx, 20, 12.5, 4.6, np.random.default_rng(0xEA61 + 1))
        _perched_eagle(a, nx + 1, 14)
        out.append(a)
    return out


def bird_frames(n=24):
    frames = []
    for i in range(n):
        a = np.zeros((40, 64, 4), np.uint8)
        t = i / n * 2 * math.pi
        x = 32 + 22 * math.cos(t); y = 20 + 8 * math.sin(t)
        far = math.sin(t) < 0                      # upper half of the loop = far side
        col = (92, 80, 70) if far else (44, 34, 26)
        span = 2 if far else 3
        flap = (i // 2) % 2
        dx = -math.sin(t); facing = 1 if dx >= 0 else -1
        cx, cy = int(round(x)), int(round(y))
        _put(a, cx, cy, col)
        for s in range(1, span + 1):
            wy = cy - (1 if flap else 0) * (1 if s < span else 0) - (s - 1 if flap else 0) * 0
            _put(a, cx - s, cy - (s if flap else (1 if s == span else 0)), col)
            _put(a, cx + s, cy - (s if flap else (1 if s == span else 0)), col)
        _put(a, cx + facing, cy + 1, col)
        frames.append(a)
    return frames


def side_images():
    """57 x 278 portrait + 2 px top + 50 px filler (B_* layout)"""
    S = 4
    W, H = 57 * S, 278 * S
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    top, mid, hor = np.array([46, 70, 110]), np.array([118, 140, 170]), np.array([226, 196, 150])
    t = yy / (H * 0.78)
    sky = np.where((t < 0.6)[..., None], top + (mid - top) * (t / 0.6)[..., None],
                   mid + (hor - mid) * np.clip((t - 0.6) / 0.4, 0, 1)[..., None])
    rng = np.random.default_rng(0xEA62)

    def noise(f):
        g = rng.random((f + 1, f + 1)); g[-1] = g[0]; g[:, -1] = g[:, 0]
        ys = (yy / W * f * 0.45) % f; xs = (xx / W * f * 0.6) % f
        y0, x0 = np.floor(ys).astype(int) % f, np.floor(xs).astype(int) % f
        ty = (1 - np.cos((ys - np.floor(ys)) * math.pi)) / 2; tx = (1 - np.cos((xs - np.floor(xs)) * math.pi)) / 2
        return (g[y0, x0] * (1 - tx) + g[y0, x0 + 1] * tx) * (1 - ty) + (g[y0 + 1, x0] * (1 - tx) + g[y0 + 1, x0 + 1] * tx) * ty
    cl = noise(6) * 0.6 + noise(14) * 0.4
    ca = np.clip((cl - 0.5) * 2.4, 0, 1) * np.clip(1 - yy / (H * 0.75), 0, 1) * 0.55
    img = sky * (1 - ca[..., None]) + np.array([236, 232, 240]) * ca[..., None]
    # distant ridges
    for k, (base, amp, col) in enumerate(((0.80, 0.05, (104, 112, 140)), (0.86, 0.04, (82, 88, 110)))):
        ridge = H * (base - amp * (0.5 + 0.5 * np.sin(xx / W * (5 + 3 * k) + k * 2.1)) - 0.03 * noise(9))
        img = np.where((yy > ridge)[..., None], np.array(col), img)
    # crag: a jagged spire rising from the bottom to about y 0.42
    peak_y = H * 0.42
    jag = (noise(30) - 0.5) * W * 0.10
    half = np.clip((yy - peak_y) / (H - peak_y), 0, 1) ** 0.75 * W * 0.46 + W * 0.07
    cxs = W * 0.52 + np.sin(yy / H * 7) * W * 0.03
    rock = (np.abs(xx - cxs - jag * 0.4) < half) & (yy > peak_y)
    side = (xx - cxs) / np.maximum(half, 1)
    shade = np.clip(0.58 - side * 0.42 + (noise(40) - 0.5) * 0.35, 0.15, 1.0)
    rockcol = np.array([158, 146, 128])[None, None, :] * shade[..., None]
    crack = (np.abs(np.sin(xx / W * 23 + yy / H * 9 + noise(18) * 4)) < 0.05) & rock
    rockcol = np.where(crack[..., None], rockcol * 0.55, rockcol)
    img = np.where(rock[..., None], rockcol, img)
    img = np.clip(img, 0, 255)
    small = np.array([img[y::S, x::S] for y in range(S) for x in range(S)]).mean(0).astype(np.uint8)
    a = np.zeros((278, 57, 4), np.uint8); a[..., :3] = small; a[..., 3] = 255
    # nest on the peak + eagle with spread wings above (drawn at 1x for crisp pixel art)
    py = int(peak_y / S)
    _nest(a, 29, py + 1, 15, 5.5, np.random.default_rng(0xEA63))
    _perched_eagle(a, 33, py - 5)
    ex, ey = 26, py - 52
    for side_ in (-1, 1):
        for s in range(0, 22):
            yv = ey - int(round(5 * math.sin(s / 22 * math.pi) + s * 0.18))
            thick = max(1, int(round(4 - s * 0.14)))
            for d in range(thick):
                _put(a, ex + side_ * s, yv + d, EAGLE_BODY if d < thick - 1 else EAGLE_LIGHT)
            if s > 15 and s % 2 == 0:
                _put(a, ex + side_ * s, yv + thick, (40, 26, 14))
    for y in range(-2, 5):
        for x in range(-2, 3):
            if (x / 2.2) ** 2 + ((y - 1) / 3.6) ** 2 <= 1:
                _put(a, ex + x, ey + y, EAGLE_BODY)
    for x in range(-1, 2):
        for y in range(5, 8):
            _put(a, ex + x, ey + y, WHITE)
    for x, y in ((-1, -4), (0, -4), (1, -4), (-1, -3), (0, -3), (1, -3), (0, -5)):
        _put(a, ex + x, ey + y, WHITE)
    _put(a, ex, ey - 6, BEAK)
    for bx, by in ((12, 40), (44, 64), (16, 90)):
        for d in (-1, 0, 1):
            _put(a, bx + d, by - abs(d), (60, 64, 84))
    topc = a[0, :, :3].astype(int).mean(0).astype(np.uint8)
    t2 = np.zeros((2, 57, 4), np.uint8); t2[..., :3] = topc; t2[..., 3] = 255
    m50 = np.zeros((50, 57, 4), np.uint8); m50[..., :3] = topc; m50[..., 3] = 255
    return t2, m50, a


def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out_dir, exist_ok=True)
    mf = map_frames(gd); bf = bird_frames()
    s = Image.new("RGBA", (5 * 64, 70), (88, 120, 60, 255))
    for i, f in enumerate(mf):
        s.alpha_composite(Image.fromarray(f, "RGBA"), (i * 64, 2))
        s.alpha_composite(Image.fromarray(bf[i * 5 % 24], "RGBA"), (i * 64 - 1, -13))
    s.resize((s.width * 4, s.height * 4), Image.NEAREST).save(os.path.join(out_dir, "eagle_map.png"))
    t, m, b = side_images()
    p = Image.fromarray(b, "RGBA")
    p.resize((57 * 3, 278 * 3), Image.NEAREST).save(os.path.join(out_dir, "eagle_side.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
