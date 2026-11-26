# ---- code begin
def _df_blend(i, tm=2.5):
    """v10 puff age ramp: 1.0 at birth (head-glow look) -> 0.0 by frame tm (v9 tail look), smoothstep."""
    u = min(1.0, max(0.0, i / tm))
    return 1.0 - u * u * (3 - 2 * u)


def skull_fire_aura(n=12):
    """Hurl Skull slot 0 layer 3 of 3 (over the bone) - v10 (user: 'the transition from skull glow to tail needs
    improvement - have the skull glow FADE INTO the tail'): v9's soft hollow fire halo (peak ~6.6 px out, hollow inside
    ~5 px so the bone keeps its white, three soft licks) with its OUTER falloff widened (3.6 -> 4.4 px) and warmed so its
    rim matches the youngest trail puffs (same orange 'hn' ramp, same softness) - the head's edge and the first puffs
    read as one glow.  ADDITIVE (770), 64x64, centre 31/33, 12 frames."""
    W = H = 64; cx, cy = 31.0, 33.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rnd = random.Random(5912)
    licks = [(rnd.uniform(-3.5, 3.5), rnd.uniform(0, 1), rnd.uniform(0.8, 1.3)) for _ in range(3)]
    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
        side = 0.80 + 0.20 * np.cos(ang - ph) + 0.08 * math.sin(ph * 3)
        heat = 0.40 * np.exp(-(np.maximum(r - 6.6, 0) / 4.4) ** 2) * side
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
            rgb[:, :, c] = np.interp(np.clip(0.92 - 0.62 * hn, 0, 1), stops, vals) * np.clip(heat * 1.6, 0, 1)
        out.append(_sk5_add(rgb))
    return out


def deathfire_puff_smoke(n=16):
    """Hurl Skull slot 3 layer 1 (the TRAIL) - v10: the first frames now look like the HEAD's glow and morph into v9's
    tail.  Age 0: barely any darkness (8 %, wide r 6.5 px - like the head's death glow only under the skull, the head's
    rim is fire, not smoke); the smoke grows in over frames 0..2.5 (smoothstep) to v9's value (~22 % dark, r 4.8 -> 2.6,
    gone by frame 13).  MULTIPLY (1026), 48x48, centre 23/23 (unchanged canvas/anchor/ids)."""
    W = H = 48; cx, cy = 23.0, 23.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr2 = (xx - cx) ** 2 + (yy - cy) ** 2
    out = []
    for i in range(n):
        b = _df_blend(i)
        life = max(0.0, 1.0 - i / 13.0)
        R_t, a_t = 2.6 + 2.2 * life, 0.30 * life ** 1.1           # v9 tail
        R_h, a_h = 6.0, 0.13                                          # head-glow look
        R = R_t + (R_h - R_t) * b; a = a_t + (a_h - a_t) * b
        out.append(_sk5_mul(a * np.exp(-rr2 / (R * R))))
    return out


def deathfire_puff_fire(n=16):
    """Hurl Skull slot 3 layer 2 (the TRAIL) - v10: born as the HEAD's fire glow - wide (r 7 px), warm orange on the
    same 'hn' ramp as skull_fire_aura's rim, a little brighter - then cooling and narrowing over frames 0..2.5 into v9's
    tail fire core (r 5 -> 2.5, orange -> deep red, gone by frame 10).  ADDITIVE (770), 48x48."""
    W = H = 48; cx, cy = 23.0, 23.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr2 = (xx - cx) ** 2 + (yy - cy) ** 2
    out = []
    for i in range(n):
        b = _df_blend(i)
        life = max(0.0, 1.0 - i / 10.0)
        rgb = np.zeros((H, W, 3), np.float32)
        # v9 tail values
        R_t = 2.5 + 2.5 * life; h_t = 0.15 * life ** 1.15; c_t = 0.30 + 0.60 * (1 - life)
        # head-rim values (skull_fire_aura at r ~7..9: heat ~0.3, colour t ~0.5)
        R_h, h_h, c_h = 6.5, 0.12, 0.55
        R = R_t + (R_h - R_t) * b; h = h_t + (h_h - h_t) * b; ct = c_t + (c_h - c_t) * b
        if h > 0.004:
            heat = h * np.exp(-rr2 / (R * R))
            col = np.array(_sk5_firecol(ct), np.float32)
            rgb = heat[:, :, None] * col[None, None, :] * 1.6
        out.append(_sk5_add(rgb))
    return out
# ---- code end
