#!/usr/bin/env python3
r"""
Water teleporter art (2026-10-31): the standing-stone ring standing in water.
  map_frame(gd, under)   -> RGBA 60x65 from STR_TELE.ILB frame 0 (surface) / 2 (underground): foam rings at every
                            stone foot, wet dark band on the stones' lowest pixels, a faint glowing swirl in the ring
                            (blue on the surface, teal underground), 1-bit alpha.
  portrait(gd, src_id)   -> RGBA 57x278 from a BORDER.ILB portrait (41 = B_Telep, 131 = BU_Telep): the ground under
                            the stones becomes water with rippled, darkened reflections of the stones.
--preview <dir>.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eagle_nest_art as V1  # noqa: E402


def _components(mask):
    h, w = mask.shape
    lab = np.zeros((h, w), int); n = 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not lab[y, x]:
                n += 1; st = [(y, x)]; lab[y, x] = n
                while st:
                    cy, cx = st.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = cy + dy, cx + dx
                        if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                            lab[yy, xx] = n; st.append((yy, xx))
    return lab, n


def map_frame(gd, under=False):
    lib, by = V1._load(gd, "STR_TELE.ILB")
    a = V1._rgba(lib, by[2 if under else 0].primary).astype(float)
    m = a[..., 3] > 0
    lab, n = _components(m)
    out = a.copy()
    tint = np.array((0.80, 0.92, 1.10)) if not under else np.array((0.70, 0.88, 0.95))
    out[m, :3] = np.clip(out[m, :3] * tint, 0, 255)
    foam = (176, 214, 232) if not under else (120, 186, 180)
    glow = (120, 190, 255) if not under else (80, 220, 200)
    feet = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(ys) < 6:
            continue
        yb = ys.max(); xl, xr = xs[ys >= yb - 1].min(), xs[ys >= yb - 1].max()
        feet.append((xl, xr, yb))
        for y in range(yb - 1, yb + 1):                               # wet band
            row = xs[ys == y]
            out[y, row, :3] = out[y, row, :3] * 0.62
    for xl, xr, yb in feet:                                           # foam rings round each foot
        cx, rx = (xl + xr) / 2, (xr - xl) / 2 + 2.2
        for t in np.linspace(0, 2 * math.pi, 48):
            x = int(round(cx + math.cos(t) * rx)); y = int(round(yb + 0.6 + math.sin(t) * 1.4))
            if math.sin(t) > -0.2 and 0 <= x < 60 and 0 <= y < 65 and not m[y, x]:
                out[y, x, :3] = foam; out[y, x, 3] = 255
    if feet:                                                          # swirl in the middle of the ring
        cx = np.mean([(f[0] + f[1]) / 2 for f in feet]); cy = np.mean([f[2] for f in feet]) - 2
        for t in np.linspace(0, 4 * math.pi, 70):
            r = 1.0 + t * 0.85
            x = int(round(cx + math.cos(t) * r * 1.6)); y = int(round(cy + math.sin(t) * r * 0.7))
            if 0 <= x < 60 and 0 <= y < 65 and not m[y, x]:
                f = 0.45 + 0.55 * (1 - t / (4 * math.pi))
                out[y, x, :3] = [g * f + 40 * (1 - f) for g in glow]; out[y, x, 3] = 255
    out[..., 3] = np.where(out[..., 3] > 0, 255, 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def portrait(gd, src_id, under=False):
    lib, by = V1._load(gd, "BORDER.ILB")
    a = V1._rgba(lib, by[src_id].primary).astype(float)
    h, w = a.shape[:2]
    lum = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    # waterline = just under the stones' feet: lowest row where the bright sky no longer reaches the bottom band
    wl = int(h * 0.885)
    rng = np.random.default_rng(0x7E1E)
    deep = np.array((22, 58, 78)) if not under else np.array((14, 40, 44))
    shal = np.array((58, 112, 132)) if not under else np.array((34, 84, 84))
    out = a.copy()
    for y in range(wl, h):
        t = (y - wl) / max(1, h - wl - 1)
        base = shal + (deep - shal) * t
        my = 2 * wl - y - 1
        for x in range(w):
            xo = int(round(x + 1.6 * math.sin(y * 1.3 + x * 0.25)))
            xo = min(w - 1, max(0, xo))
            refl = a[max(0, my), xo, :3] if my >= 0 else base
            c = base * 0.55 + refl * 0.45 * (0.75 - 0.35 * t)
            out[y, x, :3] = c
        if rng.random() < 0.55:                                       # glints
            x0 = rng.integers(0, w - 6); ln = rng.integers(3, 9)
            out[y, x0:x0 + ln, :3] = np.minimum(255, out[y, x0:x0 + ln, :3] + 40)
    out[wl - 1:wl + 1, :, :3] = out[wl - 1:wl + 1, :, :3] * 0.5 + np.array((200, 225, 235)) * 0.5   # foam line
    out[..., 3] = 255
    return np.clip(out, 0, 255).astype(np.uint8)


def preview(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    s = Image.new("RGBA", (150, 80), (40, 90, 140, 255))
    s.alpha_composite(Image.fromarray(map_frame(gd), "RGBA"), (5, 5))
    s.alpha_composite(Image.fromarray(map_frame(gd, True), "RGBA"), (80, 5))
    s.resize((600, 320), Image.NEAREST).save(os.path.join(out_dir, "tele_water_map.png"))
    c = Image.new("RGBA", (120, 278), (30, 30, 30, 255))
    c.alpha_composite(Image.fromarray(portrait(gd, 41), "RGBA"), (0, 0))
    c.alpha_composite(Image.fromarray(portrait(gd, 131, True), "RGBA"), (62, 0))
    c.resize((360, 834), Image.NEAREST).save(os.path.join(out_dir, "tele_water_side.png"))


# ---- v3 (2026-10-31): static base + animated overlay layers ----------------------------------------------------
# user: "the white lines ... should be animated and more subtle (like waves breaking against the teleporter). and the
# swirl thing ... should be more subtle and animated too".  All frames 60x65 at the base frame's offset, 1-bit alpha.
FOAM_N, SWIRL_N = 32, 24           # v3.1: user 'needs to be slower' - twice the frames, each shown HOLD ticks
HOLD = 2


def _base(gd, under):
    lib, by = V1._load(gd, "STR_TELE.ILB")
    a = V1._rgba(lib, by[2 if under else 0].primary).astype(float)
    m = a[..., 3] > 0
    lab, n = _components(m)
    out = a.copy()
    tint = np.array((0.80, 0.92, 1.10)) if not under else np.array((0.70, 0.88, 0.95))
    out[m, :3] = np.clip(out[m, :3] * tint, 0, 255)
    feet = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(ys) < 6:
            continue
        yb = ys.max(); xl, xr = xs[ys >= yb - 1].min(), xs[ys >= yb - 1].max()
        feet.append((xl, xr, yb))
        for y in range(yb - 1, yb + 1):
            row = xs[ys == y]
            out[y, row, :3] = out[y, row, :3] * 0.62
    out[..., 3] = np.where(out[..., 3] > 0, 255, 0)
    return np.clip(out, 0, 255).astype(np.uint8), m, feet


def base_frame(gd, under=False):
    return _base(gd, under)[0]


def _put(out, m, x, y, c):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < out.shape[1] and 0 <= y < out.shape[0] and not m[y, x]:
        out[y, x, :3] = c; out[y, x, 3] = 255


def foam_frames(gd, under=False):
    """v3.2 (user: "water base terrain is animated moving up/left diagonally. make the wave break animations oriented
    the same way, and more subtle"): per stone a low swell arrives from the lower right (travelling up-left like the
    water texture), breaks on the stone's lower-right face, and its foam washes round both sides towards the upper
    left while fading.  Few pixels, colours only a little lighter than the water.  Each stone on its own phase."""
    _, m, feet = _base(gd, under)
    crest = np.array((128, 168, 192) if not under else (92, 146, 142), float)
    water = np.array((66, 108, 140) if not under else (48, 88, 90), float)
    vx, vy = -0.86, -0.51                                         # water flow direction on screen (up-left)
    px_, py_ = -vy, vx                                            # along the wave front
    rng = np.random.default_rng(0xF0A3)
    phases = rng.permutation(FOAM_N)[:len(feet)] if len(feet) <= FOAM_N else rng.integers(0, FOAM_N, len(feet))
    frames = []
    for k in range(FOAM_N):
        out = np.zeros(m.shape + (4,), np.uint8)
        for (xl, xr, yb), ph in zip(feet, phases):
            t = ((k + ph) % FOAM_N) / FOAM_N
            cx, rx = (xl + xr) / 2, (xr - xl) / 2 + 1.0
            if t < 0.4:                                           # swell approaching from the lower right
                u = t / 0.4
                d = 7.0 - 6.0 * u                                 # distance from the stone's face
                f = 0.75 - 0.35 * u                               # faint far away, a bit brighter just before it hits
                c = crest * (1 - f) + water * f
                ox, oy = cx - vx * (rx + d), yb + 0.4 - vy * (rx + d) * 0.5
                half = 1.5 + 1.5 * u
                for j in np.arange(-half, half + 0.01, 1.0):
                    if (int(j * 2) + k) % 3 == 0:                 # broken, dotted crest
                        continue
                    _put(out, m, ox + px_ * j, oy + py_ * j * 0.5, c)
            elif t < 0.85:                                        # break + wash round the sides, fading
                u = (t - 0.4) / 0.45
                f = 0.35 + 0.6 * u
                c = crest * (1 - f) + water * f
                spread = 0.35 + 1.9 * u                           # radians round each side from the impact point
                a0 = math.atan2(-vy * 0.5, -vx)                   # impact direction (lower right), flattened ellipse
                r = rx + 0.6 + 1.2 * u
                n = 4 + int(6 * u)
                for i in range(n):
                    if (i + k) % (2 + int(2 * u)):
                        continue
                    for sgn in (-1, 1):
                        a = a0 + sgn * spread * (i + 0.5) / n
                        _put(out, m, cx + math.cos(a) * r, yb + 0.5 + math.sin(a) * r * 0.45, c)
        frames.append(out)
    return frames


def swirl_frames(gd, under=False):
    """v3.2 (user: "center animation should be more subtle too"): faint two-arm spiral, sparse dots barely lighter
    than the water, turning half a turn per cycle (two arms -> seamless)"""
    _, m, feet = _base(gd, under)
    if not feet:
        return [np.zeros(m.shape + (4,), np.uint8)] * SWIRL_N
    cx = np.mean([(f[0] + f[1]) / 2 for f in feet]); cy = np.mean([f[2] for f in feet]) - 2
    inner = np.array((96, 146, 186) if not under else (70, 148, 140), float)
    water = np.array((68, 112, 146) if not under else (50, 94, 96), float)
    frames = []
    for k in range(SWIRL_N):
        out = np.zeros(m.shape + (4,), np.uint8)
        rot = math.pi * k / SWIRL_N
        for arm in (0, math.pi):
            for i, t in enumerate(np.linspace(0.8, 3.0 * math.pi, 16)):
                if i % 2:
                    continue
                r = 0.8 + t * 0.55
                f = 0.25 + 0.75 * t / (3.0 * math.pi)
                c = inner * (1 - f) + water * f
                a = t + rot + arm
                _put(out, m, cx + math.cos(a) * r * 1.6, cy + math.sin(a) * r * 0.7, c)
        frames.append(out)
    return frames


def preview_anim(out_dir):
    from PIL import Image
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ims = []
    F = {u: (base_frame(gd, u), foam_frames(gd, u), swirl_frames(gd, u)) for u in (False, True)}
    for k in range(FOAM_N * SWIRL_N // 4):
        s = Image.new("RGBA", (150, 80), (52, 96, 128, 255))
        s.paste((38, 74, 78, 255), (75, 0, 150, 80))
        for u, x0 in ((False, 5), (True, 80)):
            b, fo, sw = F[u]
            s.alpha_composite(Image.fromarray(b, "RGBA"), (x0, 5))
            s.alpha_composite(Image.fromarray(fo[(k // HOLD) % FOAM_N], "RGBA"), (x0, 5))
            s.alpha_composite(Image.fromarray(sw[(k // HOLD) % SWIRL_N], "RGBA"), (x0, 5))
        ims.append(s.resize((600, 320), Image.NEAREST))
    ims[0].save(os.path.join(out_dir, "tele_water_anim.gif"), save_all=True, append_images=ims[1:], duration=110, loop=0)
    ims[0].save(os.path.join(out_dir, "tele_water_anim0.png")); ims[5].save(os.path.join(out_dir, "tele_water_anim5.png"))


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
    if "--anim" in sys.argv:
        preview_anim(sys.argv[sys.argv.index("--anim") + 1])
