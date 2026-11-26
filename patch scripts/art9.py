# ---- code begin
def hurl_skull5(n=12):
    """Hurl Skull (0xCC) slot 0 layer 2 of 3 - v9 (2026-10-19, user: 'the skull looks too big ... it's perfectly ROUND
    instead of skull-shaped - change the shape, it can be a bit misshapen like a skull'): a real skull SILHOUETTE - a
    lopsided cranium dome, brow ridge over two angular sockets, cheekbones that jut out, a narrower maxilla and a
    jagged tooth row with a gap, a nasal notch and a couple of cracks; dark bone rim, lit upper-left / shaded lower-right,
    grime and pits.  ~9 x 11 px (the v4-v8 skull was a ~10 x 12 px ball).  Full spin like the boulder (30 deg / frame,
    12 frames).  64x64 canvas, centre 31/33 (unchanged), solid keyed (256)."""
    S = 8; W = H = 64; cx, cy = 31.0, 33.0; SC = 0.9
    grime = np.random.RandomState(5911).rand(H, W)

    def skull(ang):
        L = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(L); k = S * SC
        def E(x0, y0, x1, y1, c): d.ellipse([cx * S + x0 * k, cy * S + y0 * k, cx * S + x1 * k, cy * S + y1 * k], fill=c)
        def P(pts, c): d.polygon([(cx * S + x * k, cy * S + y * k) for x, y in pts], fill=c)
        def Ln(pts, c, w): d.line([(cx * S + x * k, cy * S + y * k) for x, y in pts], fill=c, width=max(1, int(w * k)))
        rim, bone, lit, shade, blk = (16, 10, 8, 255), (205, 199, 186, 255), (238, 234, 222, 255), (126, 117, 108, 255), (5, 3, 3, 255)
        # silhouette (rim first, 0.6 px wider): lopsided dome, cheekbones, narrower jaw
        cran = [(-4.9, -1.0), (-5.2, -3.4), (-4.4, -5.6), (-2.6, -6.9), (-0.2, -7.3), (2.4, -6.9), (4.2, -5.5), (5.0, -3.2),
                (4.7, -0.8)]
        face = [(4.7, -0.8), (5.4, 0.5), (4.6, 1.5), (3.0, 1.9), (2.6, 3.6), (2.0, 5.3), (0.8, 5.9), (-0.8, 5.9), (-2.1, 5.2),
                (-2.7, 3.6), (-3.1, 1.9), (-4.8, 1.5), (-5.6, 0.4), (-4.9, -1.0)]
        outline = cran + face[1:]
        cxm = sum(x for x, _ in outline) / len(outline); cym = sum(y for _, y in outline) / len(outline)
        grow = lambda pts, g: [(x + (x - cxm) / max(1e-6, math.hypot(x - cxm, y - cym)) * g,
                                y + (y - cym) / max(1e-6, math.hypot(x - cxm, y - cym)) * g) for x, y in pts]
        P(grow(outline, 0.6), rim)
        P(outline, bone)
        P([(-4.3, -1.4), (-4.6, -3.4), (-3.7, -5.4), (-1.9, -6.4), (0.3, -6.6), (1.2, -5.6), (-1.2, -4.6), (-2.8, -3.0)], lit)  # lit dome
        P([(4.7, -0.8), (5.4, 0.5), (4.6, 1.5), (3.0, 1.9), (2.6, 3.6), (2.0, 5.3), (0.8, 5.9), (1.2, 3.6), (2.4, 1.0), (3.6, -1.6),
           (4.4, -3.4), (5.0, -3.2)], shade)                                                                          # shaded right
        # brow ridge + angular sockets (left a touch larger)
        P([(-4.1, -1.9), (-0.7, -2.3), (-0.5, -1.7), (-4.2, -1.3)], rim); P([(4.0, -1.9), (0.7, -2.3), (0.5, -1.7), (4.1, -1.3)], rim)
        P([(-3.9, -1.5), (-0.8, -1.9), (-0.6, 0.2), (-1.5, 1.2), (-3.1, 1.0), (-4.0, 0.0)], blk)
        P([(3.8, -1.5), (0.8, -1.9), (0.7, 0.1), (1.5, 1.0), (2.9, 0.9), (3.7, -0.1)], blk)
        P([(0.0, 1.0), (-0.9, 2.7), (0.0, 2.4), (0.9, 2.7)], blk)                                                    # nasal notch
        # tooth row: dark band, light teeth, one missing
        d.polygon([(cx * S - 2.3 * k, cy * S + 3.6 * k), (cx * S + 2.3 * k, cy * S + 3.6 * k), (cx * S + 1.9 * k, cy * S + 4.9 * k),
                   (cx * S - 2.0 * k, cy * S + 4.9 * k)], fill=blk)
        for i_, tx in enumerate((-1.7, -0.85, 0.0, 0.85, 1.65)):
            if i_ == 2: continue
            P([(tx - 0.3, 3.75), (tx + 0.3, 3.75), (tx + 0.24, 4.55), (tx - 0.24, 4.55)], bone)
        # cracks
        Ln([(-1.6, -6.4), (-0.9, -5.0), (-1.5, -4.0), (-1.0, -3.0)], rim, 0.34)
        Ln([(2.6, -5.9), (2.0, -4.6), (2.7, -3.6)], rim, 0.3)
        Ln([(3.2, 2.2), (2.6, 3.0)], rim, 0.28)
        return L.rotate(ang, resample=Image.BICUBIC, center=(cx * S, cy * S))

    out = []
    for i in range(n):
        sk = skull(-30.0 * i)
        small = np.array(sk.resize((W, H), Image.LANCZOS)).astype(np.float32)
        a = small[:, :, 3]; opaque = a > 120; lum = small[:, :, :3].mean(2); bonepx = opaque & (lum > 95)
        g = (grime - 0.5) * 18.0
        for c in range(3): small[:, :, c] = np.where(bonepx, small[:, :, c] + g, small[:, :, c])
        pit = bonepx & (grime > 0.96)
        for c in range(3): small[:, :, c] = np.where(pit, small[:, :, c] * 0.5, small[:, :, c])
        small[:, :, 3] = np.where(opaque, 255, 0)
        out.append(Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), "RGBA"))
    return out


def skull_death_aura(n=12):
    """Hurl Skull slot 0 layer 1 of 3 (under the bone) - v9 (user: 'make its immediate glow less SOLID; its immediate
    glow and tail should be similar effects'): the same soft Gaussian darkness as the trail puffs - no hard core / edge
    any more: ~55 % dark at the centre falling off smoothly (R ~6.3 px, gone by ~11 px), the centre wobbling slightly and
    the radius breathing, with two faint wisps curling up like the puffs' smoke.  MULTIPLY (1026), 64x64, centre 31/33,
    12 frames."""
    W = H = 64; cx, cy = 31.0, 33.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        ox, oy = 0.5 * math.sin(ph), 0.4 * math.cos(ph * 2)
        R = 6.3 + 0.5 * math.sin(ph * 2 + 1.0)
        r2 = (xx - cx - ox) ** 2 + ((yy - cy - oy) * 1.05) ** 2
        amt = 0.70 * np.exp(-r2 / (R * R))
        for k, (dx, sp) in enumerate(((-2.2, 1.0), (2.4, 1.4))):
            t = ((i / n) * sp + k / 2.0) % 1.0
            wx = cx + dx + 1.0 * math.sin(ph + k * 2.1); wy = cy - 5 - 6 * t; wr = 2.2 + 1.6 * t
            amt = 1 - (1 - amt) * (1 - 0.22 * (1 - t) * np.exp(-((xx - wx) ** 2 + (yy - wy) ** 2) / (wr * wr)))
        out.append(_sk5_mul(amt))
    return out


def skull_fire_aura(n=12):
    """Hurl Skull slot 0 layer 3 of 3 (over the bone) - v9 (user: 'less solid; the immediate glow and the tail should be
    similar effects'): no ring and no hard tongues any more - the same soft Gaussian fire glow as the trail puffs'
    fire core: a flickering halo peaking ~5 px out (hollow inside ~3.5 px so the bone keeps its white), brighter on a
    slowly turning side, with three small soft flame licks rising off it; vanilla fire ramp (hot orange near the skull
    -> deep red at the edge), gone by ~11 px.  ADDITIVE (770), 64x64, centre 31/33, 12 frames."""
    W = H = 64; cx, cy = 31.0, 33.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rnd = random.Random(5912)
    licks = [(rnd.uniform(-3.5, 3.5), rnd.uniform(0, 1), rnd.uniform(0.8, 1.3)) for _ in range(3)]
    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
        side = 0.80 + 0.20 * np.cos(ang - ph) + 0.08 * math.sin(ph * 3)
        heat = 0.40 * np.exp(-(np.maximum(r - 6.6, 0) / 3.6) ** 2) * side
        heat = heat * np.clip((r - 5.2) / 2.0, 0, 1)
        for (lx, l0, sz) in licks:
            t = ((i / n) + l0) % 1.0
            px_, py_ = cx + lx + 0.8 * math.sin(ph + l0 * 6), cy - 7.0 - 6.0 * t
            w = (1.8 + 0.8 * (1 - t)) * sz
            heat = 1 - (1 - heat) * (1 - 0.30 * (1 - t) ** 1.2 * np.exp(-((xx - px_) ** 2 + (yy - py_) ** 2) / (w * w)))
        hn = np.clip(heat / 0.5, 0, 1)
        rgb = np.zeros((H, W, 3), np.float32)
        for c in range(3):
            stops = np.array([s[0] for s in SK5_FIRE], np.float32); vals = np.array([s[1][c] for s in SK5_FIRE], np.float32)
            rgb[:, :, c] = np.interp(np.clip(0.95 - 0.7 * hn, 0, 1), stops, vals) * np.clip(heat * 1.6, 0, 1)
        out.append(_sk5_add(rgb))
    return out


def deathfire_puff_smoke(n=16):
    """Hurl Skull slot 3 layer 1 (the TRAIL) - v9: engine v7 now lays ~4-6 puffs per tick along the last ~16-px path
    step (one every ~4 px, the newest right behind the skull), so each puff is fainter and smaller: ~22 % dark at birth,
    r 4.8 -> 2.6 px, gone by frame 13 of 16 - overlapping, they read as one smooth violet-black streak, the same soft
    Gaussian as the head's death glow.  MULTIPLY (1026), 48x48, centre 23/23 (unchanged canvas/anchor/ids)."""
    W = H = 48; cx, cy = 23.0, 23.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr2 = (xx - cx) ** 2 + (yy - cy) ** 2
    out = []
    for i in range(n):
        life = max(0.0, 1.0 - i / 13.0)
        R = 2.6 + 2.2 * life
        out.append(_sk5_mul(0.30 * life ** 1.1 * np.exp(-rr2 / (R * R))))
    return out


def deathfire_puff_fire(n=16):
    """Hurl Skull slot 3 layer 2 (the TRAIL) - v9: the streak's fire core in the head glow's language, fainter per puff
    because the puffs now overlap (v7 engine): ~18 % at birth, r 5 -> 2.5 px, cooling orange -> deep red, gone by frame
    10.  ADDITIVE (770), 48x48."""
    W = H = 48; cx, cy = 23.0, 23.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr2 = (xx - cx) ** 2 + (yy - cy) ** 2
    out = []
    for i in range(n):
        life = max(0.0, 1.0 - i / 10.0)
        rgb = np.zeros((H, W, 3), np.float32)
        if life > 0:
            R = 2.5 + 2.5 * life
            heat = 0.15 * life ** 1.15 * np.exp(-rr2 / (R * R))
            col = np.array(_sk5_firecol(0.30 + 0.60 * (1 - life)), np.float32)
            rgb = heat[:, :, None] * col[None, None, :] * 1.6
        out.append(_sk5_add(rgb))
    return out


def skull_death_burst2(n=30):
    """Hurl Skull v9 slot 2 layer 1 source (user: 'the explosion is good - just add a bit more death / black particle
    effects'): v7's death layer (no ring) with MORE of it - a dark violet-black glow under the blast's core for the first
    frames, ~95 black shards with soot streaks (was 55; a mix of small and a few large chunks thrown higher), a ring of
    fine black specks that drift out and fade, and four black wisps rising late (was two thin ones).  Still subtle
    under the vanilla fireball.  MULTIPLY, vanilla 274x258 canvas (impact 131/142), 30 frames; scaled to 80 % by
    skull_death_burst80."""
    W, H = 274, 258; cx, cy = 131.0, 142.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 1.3) ** 2)
    rnd = random.Random(5940)
    parts = []
    for j in range(95):
        a = rnd.uniform(0, 2 * math.pi); big = j < 12
        v = rnd.uniform(2.0, 4.6) if big else rnd.uniform(2.4, 5.8); up = rnd.uniform(1.6, 3.6) if big else rnd.uniform(0.6, 2.8)
        parts.append((math.cos(a) * v, math.sin(a) * v * 0.55 - up, rnd.uniform(2.4, 3.4) if big else rnd.uniform(1.1, 2.4), rnd.uniform(0, 4)))
    specks = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(3.0, 6.5), rnd.uniform(0.8, 1.3)) for _ in range(60)]
    cols = [(rnd.uniform(-26, 26), rnd.uniform(0, 3), rnd.uniform(6, 10)) for _ in range(4)]
    noise = np.array(Image.fromarray((np.random.RandomState(5941).rand(26, 28) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)).astype(np.float32) / 255
    out = []
    for i in range(n):
        t = i / (n - 1.0)
        R = 26 + 74 * t ** 0.6
        dark = (0.62 * (1 - t) ** 1.3) * np.exp(-(rr / R) ** 2 * 1.5) * (0.85 + 0.3 * noise) * min(1.0, (i + 1) / 3.0)
        if i < 12:                                                   # dark glow under the core
            dark = np.maximum(dark, 0.55 * (1 - i / 12.0) * np.exp(-(rr / 22.0) ** 2))
        for (vx, vy, sz, d0) in parts:
            f = i - d0
            if f < 0: continue
            x = cx + vx * f; y = cy + vy * f + 0.11 * f * f
            fade = max(0.0, 1.0 - f / 26.0) ** 0.8
            if fade <= 0: continue
            x0, x1 = int(max(0, x - 20)), int(min(W, x + 20)); y0, y1 = int(max(0, y - 20)), int(min(H, y + 20))
            if x0 >= x1 or y0 >= y1: continue
            sub = dark[y0:y1, x0:x1]; sx_ = xx[y0:y1, x0:x1]; sy_ = yy[y0:y1, x0:x1]
            for k in range(3):
                hx = x - vx * k * 0.8; hy = y - (vy + 0.22 * f) * k * 0.8
                w = sz * (1 - 0.2 * k)
                sub = np.maximum(sub, (0.9 * fade * (1 - 0.2 * k)) * np.exp(-((sx_ - hx) ** 2 + (sy_ - hy) ** 2) / (w * w)))
            dark[y0:y1, x0:x1] = sub
        if 3 <= i < 24:                                              # fine specks drifting out
            u = (i - 3) / 21.0
            for (a, v, sz) in specks:
                x = cx + math.cos(a) * v * (i - 3) * 1.4; y = cy + math.sin(a) * v * (i - 3) * 0.75 - 4 * u
                x0, x1 = int(max(0, x - 4)), int(min(W, x + 5)); y0, y1 = int(max(0, y - 4)), int(min(H, y + 5))
                if x0 >= x1 or y0 >= y1: continue
                dark[y0:y1, x0:x1] = np.maximum(dark[y0:y1, x0:x1], 0.75 * (1 - u) * np.exp(-((xx[y0:y1, x0:x1] - x) ** 2 + (yy[y0:y1, x0:x1] - y) ** 2) / (sz * sz)))
        if i >= 12:
            u = (i - 12) / 17.0
            for (ox, d0, wd) in cols:
                for k in range(6):
                    v = u - k * 0.06
                    if v <= 0: continue
                    px_ = cx + ox + 3 * math.sin(k + i * 0.3 + ox); py_ = cy - 8 - 62 * v
                    w = wd * (0.7 + 0.6 * v)
                    dark = np.maximum(dark, 0.50 * (1 - u) ** 0.9 * (1 - 0.12 * k) * np.exp(-((xx - px_) ** 2 + (yy - py_) ** 2) / (w * w)))
        out.append(_sk5_mul(dark))
    return out


def skull_death_burst80():
    """Hurl Skull slot 2 layer 1 (pfs v7, DualDF 7710-7739) - v9: skull_death_burst2 (more black particles / wisps, dark
    glow) scaled to 80 % with the explosion it sits under (219x206, impact 105/113): composited onto white (multiply's
    no-op), Lanczos-downscaled, re-keyed where it darkens > 1.5 %."""
    if _SK8_BURST: return _SK8_BURST
    W, H = _sk8_size()
    for s in skull_death_burst2():
        a = np.array(s).astype(np.float32)
        k = a[:, :, 3:4] / 255.0
        rgb = a[:, :, :3] * k + 255.0 * (1 - k)
        ch = [np.array(Image.fromarray(rgb[:, :, c], "F").resize((W, H), Image.LANCZOS)) for c in range(3)]
        o = np.clip(np.dstack(ch), 0, 255)
        al = np.where(o.min(2) <= 251, 255, 0)
        _SK8_BURST.append(Image.fromarray(np.dstack([o, al]).astype(np.uint8), "RGBA"))
    return _SK8_BURST
# ---- code end
