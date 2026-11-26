#!/usr/bin/env python3
r"""
Cyclops unit sprites v5 (2026-11-07; user on v4: "his back looks too smooth ... his clothes/cloth looks janky" +
"the dead corpse looks too much like T-pose, make it more like the others. and still flatter and more mangled").
v5: shoulder blades + spine groove + bump-mapped skin; loincloth = ragged hide kilt with folds + front/back flaps
(the strand fringe is gone; ALSO FIXED: the skirt SDF overwrote the shared sample array `p` in place, so every
primitive after it was evaluated in a rotated space); crumpled corpses (bent limbs, twisted torso, head turned)
from straight above with flat lighting.
---- v4: Cyclops unit sprites v4 (2026-11-07; user on v3: "corpse gfx are too different from vanilla corpses, which are
flattened" / "still looks a bit off ... how can we make it more vanilla style? ... maybe it should have long straggly
hair and a beard?" + reference art: a human-like bearded giant with one eye, long matted hair, shaggy fringe
loincloth, grimy speckled skin).  v4: hair + beard + unibrow as hanging strands (seeded), no horn / pointed ears,
fringe loincloth (strands round a short skirt), earthier speckled skin ramp, corpses seen from above (ELEV 75) and
splayed flat like the vanilla ones.
---- v3: Cyclops unit sprites v3 (2026-11-07; user on v2: "it looks off. something about the texture/color/style maybe. and its
shape is a bit weird, like too hunched over and blobby" + "it needs a corpse gfx too").  v3: upright, defined anatomy
(tighter blends, smaller belly, pecs/biceps/calves, longer legs, visible neck), shading mapped onto a warm skin RAMP
in the style of the game's own units (dark brown shadow -> tan highlight) instead of multiplied grey-pink, white-noise
grain instead of the sine stripes, and two 62x62 corpses (on its back / face down) for DeadUnit.ILB.
---- v2 notes: Cyclops unit sprites v2 (2026-11-07) - rendered FROM SCRATCH (user on v1, a troll recolour: "it looks terrible, like
a janky recolor with a poorly drawn eye. maybe just restart from scratch").  PREVIEW ONLY: writes PNGs.

AoW unit sprites are pre-rendered 3D, so this is a small CPU ray-marcher (numpy, signed distance fields):
  * model = smooth-unioned primitives on a simple skeleton: short thick legs, barrel belly + broad hunched chest with a
    back hump, long heavy arms with big fists (troll-like reach), small forward-thrust bald head with ONE big eye under
    a heavy brow ridge, a stubby horn, pointed ears, wide jaw; fur loincloth + belt.  No weapon (user: no club).
  * per frame pose from the sheet layout every unit uses (Unitgfx sequences, verified on the troll record):
      frames 1-8 walk cycle, 9 stand, 10-11 attack (wind-up, smash), 12 hit / recoil;  directions 1..6 = facing
      front, front-right, back-right, back, back-left, front-left (60 deg apart).
  * orthographic camera ELEV deg above the ground, key light from the upper left, 4x4 supersampling -> 64x64 RGBA with
    a hard alpha (the game sprites are palette + transparent key), feet anchored like the original sprites (x 32,
    y ~54).
Output dir (argv[1]): frames/<id>.png, sheet_3x.png, dirs_8x.png, compare_3x.png (Giant / Troll / Cyclops).
"""
import math, os, sys
import numpy as np
from PIL import Image

OUT = sys.argv[1] if len(sys.argv) > 1 else "cyclops_v2"
SS = int(os.environ.get("CYC_SS", 4))   # supersampling per axis
N = 64
ELEV = math.radians(38)
PX_PER_UNIT = 18.5           # tuned so the standing figure is about Giant height
FEET = (32.0, 53.0)
LIGHT = np.array([-0.70, 0.62, 0.30]); LIGHT /= np.linalg.norm(LIGHT)

SKIN = np.array([170, 124, 90]) / 255.0
SKIN_RAMP = np.array([(30, 20, 16), (62, 42, 30), (98, 68, 48), (134, 96, 68), (166, 126, 90), (196, 156, 114),
                      (222, 190, 146)], float) / 255.0          # game-style warm ramp: brown shadow -> tan highlight
SKIN_D = np.array([120, 78, 60]) / 255.0
FUR = np.array([92, 72, 50]) / 255.0
BELT = np.array([58, 38, 26]) / 255.0
HORN = np.array([226, 210, 172]) / 255.0
EYEW = np.array([240, 236, 222]) / 255.0
IRIS = np.array([196, 120, 20]) / 255.0
PUPIL = np.array([12, 8, 8]) / 255.0
MOUTH = np.array([70, 30, 28]) / 255.0
NAIL = np.array([210, 190, 160]) / 255.0

M_SKIN, M_FUR, M_BELT, M_HORN, M_EYE, M_MOUTH, M_NAIL, M_HAIR = range(8)
HAIR = np.array([56, 40, 30]) / 255.0
FACE_CUT = [0.02, 0.55, 0.10]          # hair-cap hairline (sprites); the portrait raises it


# ---------------------------------------------------------------------------------------------------- SDF helpers
BUMP_F, BUMP_A = 22.0, 0.42
FLAT = 0.0                     # 0 = normal lighting; corpses use a flatter light (vanilla corpses are nearly unlit)


def vnoise(x):
    """trilinear value noise in [0,1] (x: (n,3))"""
    i = np.floor(x); f = x - i
    f = f * f * (3 - 2 * f)
    def h(o):
        c = i + o
        v = np.sin(c @ np.array([127.1, 311.7, 74.7])) * 43758.5453
        return v - np.floor(v)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * h(np.array([dx, dy, dz], float))
    return out


def sd_sphere(p, c, r):
    return np.linalg.norm(p - c, axis=-1) - r


def sd_ellipsoid(p, c, rad, R=None):
    q = p - c
    if R is not None:
        q = q @ R
    k0 = np.linalg.norm(q / rad, axis=-1)
    k1 = np.linalg.norm(q / (rad * rad), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def sd_roundcone(p, a, b, ra, rb):
    """capsule with radius ra at a, rb at b (approximate, fine for ray-marching)"""
    ba = b - a
    pa = p - a
    L2 = float(ba @ ba)
    h = np.clip((pa @ ba) / L2, 0.0, 1.0)
    r = ra + (rb - ra) * h
    return np.linalg.norm(pa - h[..., None] * ba, axis=-1) - r


def sd_torus_y(p, c, R, r):
    q = p - c
    xz = np.sqrt(q[..., 0] ** 2 + q[..., 2] ** 2) - R
    return np.sqrt(xz ** 2 + q[..., 1] ** 2) - r


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# ---------------------------------------------------------------------------------------------------- skeleton
def build(pose):
    """-> list of primitives in the character's local space (facing +z, up +y, own left = +x)"""
    g = lambda k, d=0.0: pose.get(k, d)  # noqa: E731
    P = np.array([0.0, 1.08 + g("bob"), 0.0])
    lean = g("lean", 0.12)
    twist = g("twist")
    Rsp = rot_y(twist) @ rot_x(lean)                    # spine frame (lean = pitch forward about +x)
    up = Rsp @ np.array([0, 1.0, 0]); fw = Rsp @ np.array([0, 0, 1.0]); lf = Rsp @ np.array([1.0, 0, 0])
    prims = []   # (kind, args, material, blend_group)

    # legs (longer, muscular: thigh bulge, knee, calf, big flat feet)
    for s_, side in ((1, "L"), (-1, "R")):
        hip = P + np.array([s_ * 0.22, -0.02, 0.0])
        a, b = g("hip" + side, 0.0), g("knee" + side, 0.12)
        spl = g("legsplay", 0.0)
        th = np.array([s_ * math.sin(spl), -math.cos(a) * math.cos(spl), math.sin(a) * math.cos(spl)])
        knee = hip + 0.50 * th
        sh = np.array([0.0, -math.cos(a - b), math.sin(a - b)])
        ankle = knee + 0.48 * sh
        toe = ankle + np.array([s_ * 0.04, -0.06, 0.26])
        prims += [("rc", (hip, knee, 0.19, 0.12), M_SKIN, 0),
                  ("el", (hip + 0.22 * th + np.array([0, 0, 0.03]), np.array([0.15, 0.20, 0.15]), None), M_SKIN, 0),
                  ("rc", (knee, ankle, 0.12, 0.085), M_SKIN, 0),
                  ("el", (knee + 0.16 * sh - 0.05 * np.array([0, -sh[2], sh[1]]), np.array([0.115, 0.17, 0.12]), None), M_SKIN, 0),
                  ("rc", (ankle, toe, 0.10, 0.08), M_SKIN, 0),
                  ("el", (ankle + np.array([0, -0.05, 0.10]), np.array([0.13, 0.06, 0.20]), None), M_SKIN, 0)]
        for t in (-1, 0, 1):
            prims.append(("sp", (toe + np.array([t * 0.055, -0.01, 0.05]), 0.03), M_NAIL, 1))

    # torso: upright, broad chest, pecs, modest belly, short thick neck, small trapezius hump
    belly = P + 0.20 * up + 0.08 * fw
    chest = P + 0.58 * up + 0.02 * fw
    neck = P + 0.88 * up + 0.04 * fw
    prims += [("el", (belly, np.array([0.33, 0.30, 0.29]), Rsp), M_SKIN, 4),
              ("el", (chest, np.array([0.50, 0.32, 0.28]), Rsp), M_SKIN, 4),
              ("el", (P + 0.38 * up, np.array([0.38, 0.30, 0.27]), Rsp), M_SKIN, 4),
              ("el", (chest + 0.18 * up - 0.06 * fw, np.array([0.40, 0.16, 0.20]), Rsp), M_SKIN, 4)]     # traps
    for s_ in (1, -1):
        prims.append(("el", (chest + 0.19 * s_ * lf + 0.15 * fw + 0.02 * up, np.array([0.18, 0.13, 0.10]), Rsp), M_SKIN, 5))
        prims.append(("el", (chest + 0.20 * s_ * lf - 0.20 * fw + 0.06 * up, np.array([0.15, 0.17, 0.08]), Rsp), M_SKIN, 5))  # scapula
        prims.append(("el", (P + 0.42 * up - 0.12 * fw + 0.13 * s_ * lf, np.array([0.11, 0.24, 0.08]), Rsp), M_SKIN, 5))    # lats
    prims.append(("rc", (P + 0.22 * up - 0.285 * fw, P + 0.74 * up - 0.315 * fw, 0.018, 0.018), M_SKIN, 6))    # spine groove (subtle)

    # arms: deltoid, biceps bulge, thick forearm, big fist
    fists = {}
    for s_, side in ((1, "L"), (-1, "R")):
        shd = chest + s_ * 0.46 * lf + 0.14 * up - 0.02 * fw
        p_, q_, e_ = g("sp" + side, 0.15), g("sa" + side, 0.22), g("el" + side, 0.30)
        d1 = np.array([s_ * math.sin(q_), -math.cos(q_) * math.cos(p_), math.cos(q_) * math.sin(p_)])
        elbow = shd + 0.48 * d1
        p2 = p_ + e_
        dloc2 = np.array([s_ * math.sin(q_) * 0.6, -math.cos(p2), math.sin(p2)])
        d2 = dloc2 / np.linalg.norm(dloc2)
        wrist = elbow + 0.44 * d2
        fist = wrist + 0.09 * d2
        fists[side] = fist
        prims += [("sp", (shd, 0.16), M_SKIN, 0),
                  ("rc", (shd, elbow, 0.14, 0.10), M_SKIN, 0),
                  ("sp", (shd + 0.22 * d1 + 0.03 * np.array([0, 0, 1.0]), 0.12), M_SKIN, 5),        # biceps
                  ("rc", (elbow, wrist, 0.135, 0.09), M_SKIN, 0),
                  ("sp", (elbow + 0.13 * d2, 0.115), M_SKIN, 5),                                    # forearm
                  ("el", (fist, np.array([0.12, 0.12, 0.13]), None), M_SKIN, 0)]
        side_v = np.cross(d2, [0, 1, 0]); nv = np.linalg.norm(side_v)
        side_v = side_v / nv if nv > 1e-6 else np.array([1.0, 0, 0])
        for t in (-1, 0, 1):
            prims.append(("sp", (fist + 0.10 * d2 + t * 0.05 * side_v, 0.03), M_NAIL, 1))

    # head (thrust forward and low)
    hp = g("headp", 0.0)
    Rh = Rsp @ rot_x(-lean * 0.8 + hp)                  # head stays roughly upright
    hu = Rh @ np.array([0, 1.0, 0]); hf = Rh @ np.array([0, 0, 1.0]); hl = Rh @ np.array([1.0, 0, 0])
    head = neck + 0.22 * up + 0.10 * fw
    prims += [("rc", (neck - 0.10 * up, head, 0.19, 0.15), M_SKIN, 0),
              ("el", (head, np.array([0.25, 0.26, 0.24]), Rh), M_SKIN, 0),
              ("el", (head - 0.14 * hu + 0.07 * hf, np.array([0.23, 0.12, 0.19]), Rh), M_SKIN, 0)]   # jaw
    brow = head + 0.13 * hu + 0.18 * hf
    prims.append(("rc", (brow - 0.15 * hl, brow + 0.15 * hl, 0.065, 0.065), M_SKIN, 2))
    if not g("portrait", 0):
        prims.append(("rc", (brow - 0.14 * hl + 0.03 * hu + 0.03 * hf, brow + 0.14 * hl + 0.03 * hu + 0.03 * hf,
                             0.04, 0.04), M_HAIR, 1))                                  # heavy unibrow
    else:
        rb = np.random.RandomState(21); eb = []
        for i in range(22):                              # bushy eyebrow tufts along the ridge
            t = rb.uniform(-1, 1)
            a = brow + t * 0.15 * hl + 0.05 * hu + 0.04 * hf
            eb.append((a, a + 0.06 * hf + rb.uniform(-0.02, 0.05) * hu + t * 0.05 * hl + rb.normal(0, 0.01, 3), 0.018, 0.006))
        prims.append(("strands", (eb, brow, 0.4), M_HAIR, 1))
    down = np.array([0.0, -1.0, 0.0])
    rng = np.random.RandomState(7)
    segs = []
    for i in range(48):                                 # long straggly hair: crown, sides and back (face kept clear)
        az = rng.uniform(-2.35, 2.35)                   # 0 = straight back
        el = rng.uniform(0.0, 1.0)
        dv = (-hf * math.cos(az) + hl * math.sin(az)) * math.cos(el * 1.25) + hu * math.sin(el * 1.25)
        dv /= np.linalg.norm(dv)
        a = head + 0.24 * dv
        L = rng.uniform(0.38, 0.66) * (0.75 if abs(az) > 1.7 else 1.0)
        out = dv * np.array([1.0, 0.0, 1.0]); out = out / (np.linalg.norm(out) + 1e-6)
        mid = a + 0.07 * out + down * L * 0.5 + rng.normal(0, 0.03, 3)
        end = mid + down * L * 0.5 + 0.06 * out + rng.normal(0, 0.04, 3)
        r0 = rng.uniform(0.035, 0.05)
        segs += [(a, mid, r0, r0 * 0.8), (mid, end, r0 * 0.8, 0.012)]
    jaw = head - (0.20 if g("portrait", 0) else 0.14) * hu + 0.07 * hf
    for i in range(34):                                 # full beard down onto the chest
        az = rng.uniform(-1.45, 1.45)
        dv = hf * math.cos(az) + hl * math.sin(az)
        a = jaw + 0.18 * dv + hu * (rng.uniform(-0.04, 0.10) * (1 if abs(az) > 0.9 else 0.4)
                                     if not g("portrait", 0) else rng.uniform(-0.10, -0.02) + (0.10 if abs(az) > 1.0 else 0))
        L = rng.uniform(0.22, 0.44) * (1.0 - 0.25 * abs(az))
        mid = a + 0.05 * dv + down * L * 0.5 + rng.normal(0, 0.025, 3)
        end = mid + down * L * 0.5 + 0.03 * fw + rng.normal(0, 0.035, 3)
        segs += [(a, mid, 0.05, 0.04), (mid, end, 0.04, 0.012)]
    prims.append(("strands", (segs, head - 0.15 * hu, 1.05), M_HAIR, 1))
    prims.append(("cap", (head + 0.01 * hu - 0.01 * hf, np.array([0.29, 0.30, 0.285]), Rh, hu, hf, head), M_HAIR, 1))
    mouth = head - 0.14 * hu + 0.24 * hf
    if not g("portrait", 0):
        prims.append(("rc", (mouth - 0.11 * hl, mouth + 0.11 * hl, 0.025, 0.025), M_MOUTH, 3))
        eye_c = head + 0.04 * hu + 0.175 * hf
        prims.append(("eye", (eye_c, 0.135, hf), M_EYE, 1))
    else:                                               # close-up face detail (portrait only)
        eye_c = head + 0.05 * hu + 0.19 * hf
        prims.append(("sp", (eye_c + 0.02 * hf, 0.115), M_SKIN, 3))                   # eye socket (carved)
        prims.append(("eye", (eye_c, 0.085, hf), M_EYE, 1))
        prims.append(("rc", (eye_c - 0.08 * hu + 0.07 * hf, eye_c - 0.19 * hu + 0.13 * hf, 0.04, 0.055), M_SKIN, 2))  # nose
        for s2 in (1, -1):
            prims.append(("sp", (eye_c - 0.20 * hu + 0.11 * hf + s2 * 0.045 * hl, 0.045), M_SKIN, 2))          # nostrils
            prims.append(("sp", (eye_c - 0.11 * hu + 0.02 * hf + s2 * 0.13 * hl, 0.075), M_SKIN, 2))           # cheeks
        mo = head - 0.17 * hu + 0.235 * hf
        prims.append(("el", (mo, np.array([0.085, 0.035, 0.05]), Rh), M_MOUTH, 3))                         # open snarl
        for t in (-1.5, -0.5, 0.5, 1.5):
            prims.append(("sp", (mo + 0.015 * hu + t * 0.032 * hl - 0.01 * hf, 0.016), M_NAIL, 1))           # teeth

    # loincloth: ragged hide kilt with folds, front and back flaps, belt
    waist = P + 0.02 * up
    prims += [("tor", (waist + np.array([0, 0.02, 0.03]), 0.335, 0.045), M_BELT, 1),
              ("kilt", (waist + 0.01 * up, waist - 0.40 * up, 0.34, 0.42, Rsp), M_FUR, 1),
              ("el", (waist + 0.33 * fw - 0.22 * up, np.array([0.17, 0.26, 0.035]), Rsp @ rot_x(0.12)), M_FUR, 1),
              ("el", (waist - 0.31 * fw - 0.24 * up, np.array([0.20, 0.27, 0.035]), Rsp @ rot_x(-0.10)), M_FUR, 1)]
    return prims


def eval_sdf(p, prims, need_mat=False):
    d_body = np.full(p.shape[:-1], 1e9)
    d_other = np.full(p.shape[:-1], 1e9)
    mat = np.full(p.shape[:-1], -1, np.int16) if need_mat else None
    eye_info = None
    for kind, args, m, grp in prims:
        if kind == "sp":
            d = sd_sphere(p, *args)
        elif kind == "el":
            c, rad, R = args
            d = sd_ellipsoid(p, c, rad, R)
        elif kind == "rc":
            d = sd_roundcone(p, *args)
        elif kind == "tor":
            c, R0, r0 = args[0], args[1], args[2]
            Rm = args[3] if len(args) > 3 else np.eye(3)
            d = sd_torus_y((p - c) @ Rm + c, c, R0, r0)
        elif kind == "skirt":                            # hollow-ish flared cone with a ragged hem
            a, b, ra, rb = args[:4]
            Rm = args[4] if len(args) > 4 else np.eye(3)
            b = a + (b - a) @ Rm                              # back into the skirt's own (upright) frame
            pl = (p - a) @ Rm + a                             # (v5: local copy - never overwrite p)
            q = pl - a
            ang = np.arctan2(q[..., 0], q[..., 2])
            hem = 0.06 * np.abs(np.sin(ang * 5.0)) + 0.03 * np.sin(ang * 13.0)
            bb = b + np.array([0.0, 0.0, 0.0])
            d = sd_roundcone(pl, a, bb, ra, rb)
            d = np.maximum(d, (bb[1] + hem) - pl[..., 1])     # cut the bottom raggedly
            d = np.maximum(d, -sd_roundcone(pl, a + np.array([0, -0.05, 0]), bb - np.array([0, 0.2, 0]), ra - 0.06, rb - 0.05))
        elif kind == "kilt":                             # hide kilt: fold ridges, torn uneven hem, open inside
            a, b, ra, rb, Rk = args
            pl = (p - a) @ Rk                                 # kilt-local: y along the body axis
            ang = np.arctan2(pl[..., 0], pl[..., 2])
            L = float(np.linalg.norm(b - a))
            h = np.clip(-pl[..., 1] / L, 0.0, 1.0)
            r = ra + (rb - ra) * h + 0.022 * np.sin(ang * 9.0 + 0.7) * h + 0.012 * np.sin(ang * 17.0) * h
            rad = np.sqrt(pl[..., 0] ** 2 + pl[..., 2] ** 2)
            shell = np.abs(rad - r) - 0.028
            hem = (0.07 * np.abs(np.sin(ang * 3.3 + 1.1)) + 0.04 * np.abs(np.sin(ang * 7.9 + 0.3))
                   + 0.025 * np.sin(ang * 19.0))
            d = np.maximum(shell, -(pl[..., 1] + L - hem))
            d = np.maximum(d, pl[..., 1] - 0.02)
        elif kind == "eye":
            c, r, f = args
            d = sd_sphere(p, c, r)
            eye_info = (c, r, f)
        elif kind == "cap":                              # hair shell over crown / back / sides, face left clear
            c, rad, Rm, hu_, hf_, hc = args
            d = sd_ellipsoid(p, c, rad, Rm)
            rel = p - hc
            face = (rel @ hf_) - FACE_CUT[0] - FACE_CUT[1] * np.maximum(rel @ hu_ - FACE_CUT[2], 0.0)  # hairline
            d = np.maximum(d, face)
            d = np.maximum(d, -(rel @ hu_) - 0.06)
        elif kind == "strands":
            segs, bc, br = args
            db = np.linalg.norm(p - bc, axis=-1)
            d = db - br                                  # outside the bound: conservative distance
            inside = np.nonzero(db < br + 0.05)[0]
            if len(inside):
                q = p[inside]
                dm = np.full(len(inside), 1e9)
                for a_, b_, ra_, rb_ in segs:
                    dm = np.minimum(dm, sd_roundcone(q, a_, b_, ra_, rb_))
                d = d.copy()
                d[inside] = np.maximum(dm, d[inside])
        if grp == 0:
            d_body = smin(d_body, d, 0.05)
        elif grp == 6:                                   # smooth carve (spine groove)
            k = 0.07
            hh = np.clip(0.5 - 0.5 * (d_body + d) / k, 0.0, 1.0)
            d_body = d_body + (-d - d_body) * hh + k * hh * (1.0 - hh)
            continue
        elif grp == 4:                                   # torso: soft blend, no ridges between the masses
            d_body = smin(d_body, d, 0.16)
        elif grp == 5:                                   # muscle bulges
            d_body = smin(d_body, d, 0.09)
        elif grp == 2:
            d_body = smin(d_body, d, 0.04)
        elif grp == 3:                                   # carved (mouth groove)
            d_body = np.maximum(d_body, -d)
            if need_mat:
                mat = np.where(d < 0.012, M_MOUTH, mat)
            continue
        else:
            if need_mat:
                mat = np.where(d < d_other, m, mat)
            d_other = np.minimum(d_other, d)
    d = np.minimum(d_body, d_other)
    if need_mat:
        mat = np.where((d_body <= d_other) & (mat != M_MOUTH), M_SKIN, np.where(d_body <= d_other, mat, mat))
        mat = np.where(d_other < d_body, mat, np.where(mat == M_MOUTH, M_MOUTH, M_SKIN))
    return d, mat, eye_info


# ---------------------------------------------------------------------------------------------------- camera / render
def render(pose, yaw, n_px=None, feet=None, body_rx=0.0, lift=0.0, elev=None):
    global N, FEET, ELEV
    n_save, f_save, e_save = N, FEET, ELEV
    if elev is not None:
        ELEV = math.radians(elev)
    if n_px:
        N = n_px
    if feet:
        FEET = feet
    try:
        return _render(pose, yaw, body_rx, lift)
    finally:
        N, FEET, ELEV = n_save, f_save, e_save


def _render(pose, yaw, body_rx, lift):
    prims = build(pose)
    R = rot_y(yaw) @ rot_x(body_rx)
    T = np.array([0.0, lift, 0.0])
    world = []
    for kind, args, m, grp in prims:              # rotate the character into world space
        if kind == "sp":
            args = (R @ args[0] + T, args[1])
        elif kind == "el":
            args = (R @ args[0] + T, args[1], R @ (args[2] if args[2] is not None else np.eye(3)))
        elif kind == "rc":
            args = (R @ args[0] + T, R @ args[1] + T, args[2], args[3])
        elif kind == "tor":
            args = (R @ args[0] + T, args[1], args[2], R)
        elif kind == "skirt":
            args = (R @ args[0] + T, R @ args[1] + T, args[2], args[3], R)
        elif kind == "eye":
            args = (R @ args[0] + T, args[1], R @ args[2])
        elif kind == "cap":
            args = (R @ args[0] + T, args[1], R @ args[2], R @ args[3], R @ args[4], R @ args[5] + T)
        elif kind == "kilt":
            args = (R @ args[0] + T, R @ args[1] + T, args[2], args[3], R @ args[4])
        elif kind == "strands":
            args = ([(R @ a_ + T, R @ b_ + T, ra_, rb_) for a_, b_, ra_, rb_ in args[0]], R @ args[1] + T, args[2])
        world.append((kind, args, m, grp))
    W = N * SS
    fwd = np.array([0.0, -math.sin(ELEV), -math.cos(ELEV)])
    upv = np.array([0.0, math.cos(ELEV), -math.sin(ELEV)])
    rgt = np.array([1.0, 0.0, 0.0])
    s = PX_PER_UNIT * SS
    ys, xs = np.mgrid[0:W, 0:W]
    u = (xs + 0.5 - FEET[0] * SS) / s
    v = -(ys + 0.5 - FEET[1] * SS) / s
    org = (u[..., None] * rgt + v[..., None] * upv) - 6.0 * fwd
    org = org.reshape(-1, 3)
    t = np.zeros(len(org))
    alive = np.ones(len(org), bool)
    hit = np.zeros(len(org), bool)
    for _ in range(90):
        idx = np.nonzero(alive)[0]
        if not len(idx):
            break
        p = org[idx] + t[idx, None] * fwd
        d, _m, _e = eval_sdf(p, world)
        t[idx] += d
        h = d < 0.002
        hit[idx[h]] = True
        alive[idx[h]] = False
        alive[idx[t[idx] > 12.0]] = False
    col = np.zeros((len(org), 3)); alpha = hit.astype(float)
    hi = np.nonzero(hit)[0]
    if len(hi):
        p = org[hi] + t[hi, None] * fwd
        e = 0.003
        nx = eval_sdf(p + [e, 0, 0], world)[0] - eval_sdf(p - [e, 0, 0], world)[0]
        ny = eval_sdf(p + [0, e, 0], world)[0] - eval_sdf(p - [0, e, 0], world)[0]
        nz = eval_sdf(p + [0, 0, e], world)[0] - eval_sdf(p - [0, 0, e], world)[0]
        n = np.stack([nx, ny, nz], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
        n0 = n.copy()
        _d, mat, eye = eval_sdf(p, world, need_mat=True)
        sk_m = mat == M_SKIN
        if sk_m.any():
            bump = np.stack([vnoise(p[sk_m] * BUMP_F + o) for o in (0.0, 17.3, 41.7)], -1) - 0.5
            nb = n[sk_m] + BUMP_A * bump
            n[sk_m] = nb / (np.linalg.norm(nb, axis=-1, keepdims=True) + 1e-9)
        fm = (mat == M_FUR)
        if fm.any():                                     # hide: coarse creases
            bump = np.stack([vnoise(p[fm] * np.array([30.0, 6.0, 30.0]) + o) for o in (3.1, 9.7, 27.2)], -1) - 0.5
            nb = n[fm] + 0.9 * bump
            n[fm] = nb / (np.linalg.norm(nb, axis=-1, keepdims=True) + 1e-9)
        base = np.tile(SKIN, (len(hi), 1))
        # skin: darker underside / shadowed back, mild mottling
        cell = np.floor(p * 120.0)
        hsh = np.sin(cell @ np.array([12.9898, 78.233, 37.719])) * 43758.5453
        grain = (hsh - np.floor(hsh)) - 0.5                 # white noise per small 3D cell (no stripes)
        cell2 = np.floor(p * 85.0)
        h2 = np.sin(cell2 @ np.array([39.346, 11.135, 83.155])) * 24634.6345
        speck = (h2 - np.floor(h2)) > 0.92                  # dark grime speckles on the skin
        for m, c in ((M_FUR, FUR), (M_BELT, BELT), (M_HORN, HORN), (M_MOUTH, MOUTH), (M_NAIL, NAIL), (M_HAIR, HAIR)):
            base[mat == m] = c
        mm = mat == M_HAIR
        base[mm] *= (0.75 + 0.55 * (grain[mm] + 0.5))[:, None]
        mm = mat == M_FUR                                 # hide: blotchy leather/fur tone
        base[mm] *= (0.70 + 0.50 * vnoise(p[mm] * np.array([9.0, 3.0, 9.0])))[:, None]
        spec = np.zeros(len(hi))
        if eye is not None:
            ec, er, ef = eye
            em = mat == M_EYE
            q = p[em] - ec; q /= np.linalg.norm(q, axis=-1, keepdims=True)
            ca = q @ (ef / np.linalg.norm(ef))
            c = np.tile(EYEW, (em.sum(), 1))
            c[ca > 0.86] = IRIS
            c[ca > 0.95] = PUPIL
            base[em] = c
            spec[em] = 1.0
        lam = np.clip(n @ LIGHT, 0.0, 1.0)
        hemi = 0.5 + 0.5 * n[:, 1]
        ao = np.ones(len(hi))
        for k, dist in enumerate((0.04, 0.09, 0.16)):
            dd = eval_sdf(p + n * dist, world)[0]
            ao -= (dist - np.clip(dd, 0, dist)) / dist * (0.35 / (k + 1))
        ao = np.clip(ao, 0.25, 1.0)
        shade = (0.10 + 1.00 * lam + 0.12 * hemi) * (0.40 + 0.60 * ao)
        shade = shade * (1 - FLAT) + (0.55 + 0.25 * lam) * (0.55 + 0.45 * ao) * FLAT
        shade = shade * (0.80 + 0.25 * np.clip(p[:, 1] / 1.6, 0, 1))      # lower body a little darker
        h = LIGHT - fwd; h /= np.linalg.norm(h)
        sp = np.clip(n @ h, 0, 1) ** 24
        if eye is not None and not FLAT:
            shade = np.where(mat == M_EYE, np.maximum(shade, 0.95), shade)   # the eye always reads (not on corpses)
        if FLAT:
            shade = np.where(mat == M_EYE, shade * 0.45, shade)              # dead: dull, clouded eye
            spec = spec * 0.0
        col[hi] = np.clip(base * shade[:, None] + (0.05 + 0.6 * spec)[:, None] * sp[:, None], 0, 1)
        sk = mat == M_SKIN
        tt = np.clip(shade[sk] * 0.78 + 0.035 * grain[sk] + 0.20 * sp[sk] - 0.09 * speck[sk], 0, 0.999) * (len(SKIN_RAMP) - 1)
        i0 = np.floor(tt).astype(int); fr = (tt - i0)[:, None]
        col[hi[sk]] = SKIN_RAMP[i0] * (1 - fr) + SKIN_RAMP[np.minimum(i0 + 1, len(SKIN_RAMP) - 1)] * fr
        rim = np.clip(1.0 - np.abs(n @ fwd), 0, 1) ** 3
        col[hi] *= (1.0 - 0.30 * rim)[:, None]           # darker silhouette edge (reads like the game's outline)
    col = col.reshape(W, W, 3); alpha = alpha.reshape(W, W)
    if os.environ.get("CYC_HIRES"):
        big = np.zeros((W, W, 4), np.uint8)
        big[..., :3] = np.clip(col * 255, 0, 255).astype(np.uint8); big[..., 3] = (alpha > 0) * 255
        render.hires = Image.fromarray(big, "RGBA")
    # downsample: colour = mean over covered samples, alpha = coverage >= 40%
    cs = (col * alpha[..., None]).reshape(N, SS, N, SS, 3).sum((1, 3))
    cov = alpha.reshape(N, SS, N, SS).sum((1, 3))
    rgb = np.where(cov[..., None] > 0, cs / np.maximum(cov, 1)[..., None], 0)
    a = (cov / (SS * SS) >= 0.4)
    img = np.zeros((N, N, 4), np.uint8)
    img[..., :3] = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    img[..., 3] = a * 255
    # 1-px darker silhouette edge, like the game's pre-rendered sprites
    edge = a & ~(np.roll(a, 1, 0) & np.roll(a, -1, 0) & np.roll(a, 1, 1) & np.roll(a, -1, 1))
    img[edge, :3] = (img[edge, :3] * 0.62).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


# ---------------------------------------------------------------------------------------------------- poses
def pose_for(frame):
    if frame == 9:                                        # stand
        return dict(bob=0.0, lean=0.12, spL=0.08, spR=0.08, elL=0.30, elR=0.30, kneeL=0.10, kneeR=0.10)
    if 1 <= frame <= 8:                                   # walk
        ph = (frame - 1) / 8.0 * 2 * math.pi
        sw = math.sin(ph)
        return dict(bob=-0.04 * abs(math.cos(ph)), lean=0.20, twist=0.10 * sw,
                    hipL=0.42 * sw, hipR=-0.42 * sw,
                    kneeL=0.15 + 0.55 * max(0.0, -math.cos(ph)), kneeR=0.15 + 0.55 * max(0.0, math.cos(ph)),
                    spL=-0.45 * sw, spR=0.45 * sw, elL=0.35 + 0.2 * max(0, -sw), elR=0.35 + 0.2 * max(0, sw))
    if frame == 10:                                       # wind-up: both fists raised high
        return dict(lean=0.05, bob=0.02, spL=2.6, spR=2.6, saL=0.35, saR=0.35, elL=0.6, elR=0.6,
                    kneeL=0.25, kneeR=0.25, hipL=0.15, hipR=-0.10, headp=-0.15)
    if frame == 11:                                       # smash: double-fist slam forward and down
        return dict(lean=0.55, bob=-0.10, spL=1.25, spR=1.25, saL=0.12, saR=0.12, elL=0.1, elR=0.1,
                    kneeL=0.55, kneeR=0.45, hipL=0.45, hipR=-0.05, headp=0.2)
    if frame == 12:                                       # hit recoil
        return dict(lean=-0.15, bob=-0.02, spL=0.6, spR=0.9, saL=0.9, saR=0.9, elL=0.8, elR=0.6,
                    kneeL=0.35, kneeR=0.20, hipL=-0.20, hipR=0.25, headp=-0.35, twist=0.25)
    raise ValueError(frame)


YAW = {1: 0.0, 2: 60.0, 3: 120.0, 4: 180.0, 5: 240.0, 6: 300.0}


CORPSES = {  # id: (pose, yaw deg, body_rx, lift) - crumpled like the vanilla corpses, seen from above
    "A": (dict(lean=0.0, twist=0.55, spL=2.1, saL=0.5, elL=1.7, spR=-0.5, saR=1.1, elR=1.3,
               hipL=1.0, kneeL=1.5, hipR=-0.35, kneeR=0.7, legsplay=0.25, headp=0.5, bob=0.0), 30.0, -math.pi / 2, 0.30),
    "B": (dict(lean=0.0, twist=-0.6, spL=0.9, saL=1.2, elL=1.4, spR=2.4, saR=0.3, elR=0.6,
               hipL=-0.4, kneeL=1.2, hipR=0.8, kneeR=1.6, legsplay=0.30, headp=-0.4, bob=0.0), -55.0, math.pi / 2, 0.30),
}
CORPSE_ELEV = 86.0
CORPSE_SCALE = 0.80


def render_corpses():
    global PX_PER_UNIT, FLAT
    px_save = PX_PER_UNIT
    PX_PER_UNIT, FLAT = px_save * CORPSE_SCALE, 0.65
    try:
        return _render_corpses()
    finally:
        PX_PER_UNIT, FLAT = px_save, 0.0


def render_portrait():
    """103x128 portrait for FACES\Add_UNITS.ILB: head + shoulders near eye level, one hand reaching at the viewer,
    dark cave background with a warm key light, then a light painterly pass (mode filter + canvas grain)"""
    global PX_PER_UNIT, LIGHT, SS
    from PIL import ImageFilter
    saves = (PX_PER_UNIT, LIGHT, SS)
    PX_PER_UNIT, SS = 92.0, 3
    LIGHT = np.array([-0.85, 0.40, 0.40]); LIGHT = LIGHT / np.linalg.norm(LIGHT)
    try:
        pose = dict(lean=0.25, bob=0.0, spL=0.30, saL=0.30, elL=0.40, spR=0.30, saR=0.30, elR=0.40, headp=0.15,
                    portrait=1)
        FACE_CUT[:] = [-0.06, 0.20, 0.20]
        os.environ["CYC_HIRES"] = "1"
        render(pose, math.radians(-20.0), n_px=128, feet=(64.0, 236.0), elev=10.0)
        big = render.hires                                   # 384x384 RGBA
    finally:
        PX_PER_UNIT, LIGHT, SS = saves
        FACE_CUT[:] = [0.02, 0.55, 0.10]
    W, H = big.size
    yy, xx = np.mgrid[0:H, 0:W]
    # background: dark cave, warm glow from the upper left
    g = np.clip(1.0 - np.hypot((xx - 0.15 * W) / W, (yy - 0.20 * H) / H) * 1.25, 0, 1)
    bgc = (np.array([22, 18, 14])[None, None] + g[..., None] * np.array([92, 70, 44])[None, None])
    rng = np.random.RandomState(3)
    bgc = bgc * (0.85 + 0.30 * rng.rand(H, W, 1))
    bg = Image.fromarray(np.clip(bgc, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(3))
    bg.paste(big, (0, 0), big)
    img = bg.filter(ImageFilter.ModeFilter(3)).filter(ImageFilter.SMOOTH)
    img = img.resize((128, 128), Image.LANCZOS)
    img = img.crop((12, 0, 12 + 103, 128))
    a = np.asarray(img).astype(float)
    a = a * (0.94 + 0.12 * np.random.RandomState(5).rand(128, 103, 1))     # canvas grain
    vign = np.clip(1.15 - np.hypot((np.mgrid[0:128, 0:103][1] - 51) / 70.0, (np.mgrid[0:128, 0:103][0] - 60) / 85.0), 0.55, 1)
    a = a * vign[..., None]
    a = 255.0 * (np.clip(a / 255.0, 0, 1) ** 1.25)                         # moodier, like the vanilla portraits
    m = a.mean(axis=2, keepdims=True); a = m + (a - m) * 1.15
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    out.save(os.path.join(OUT, "portrait.png"))
    out.resize((309, 384), Image.NEAREST).save(os.path.join(OUT, "portrait_3x.png"))
    return out


def _render_corpses():
    out = {}
    for k, (pose, yaw, rx, lift) in CORPSES.items():
        # lying body: the pelvis sits at height P.y; rotate about the origin, then drop it onto the ground
        big = render(pose, math.radians(yaw), n_px=110, feet=(55.0, 55.0), body_rx=rx, lift=lift - 1.08,
                     elev=CORPSE_ELEV)
        x0, y0, x1, y1 = big.getbbox()
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2        # centre the body like the troll's corpse (bbox centre ~ 28,39)
        im = big.crop((cx - 29, cy - 38, cx - 29 + 62, cy - 38 + 62))
        assert im.getbbox() and (x1 - x0) <= 62 and (y1 - y0) <= 62, ("corpse too big", x1 - x0, y1 - y0)
        out[k] = im
        im.save(os.path.join(OUT, "corpse_%s.png" % k))
    C = Image.new("RGB", (2 * 62 * 4, 62 * 4), (78, 96, 52))
    for i, k in enumerate(sorted(out)):
        b = out[k].resize((248, 248), Image.NEAREST)
        C.paste(b, (i * 248, 0), b)
    C.save(os.path.join(OUT, "corpses_4x.png"))


def main():
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
    if os.environ.get("CYC_PORTRAIT"):
        render_portrait()
        return
    if os.environ.get("CYC_CORPSE"):
        render_corpses()
        if os.environ.get("CYC_CORPSE") == "only":
            return
    only = None if len(sys.argv) < 3 else [int(x) for x in sys.argv[2].split(",")]
    frames = {}
    for d in range(1, 7):
        for f in range(1, 13):
            fid = d * 100 + f
            if only and fid not in only:
                continue
            im = render(pose_for(f), math.radians(YAW[d]))
            im.save(os.path.join(OUT, "frames", "%d.png" % fid))
            if os.environ.get("CYC_HIRES"):
                render.hires.save(os.path.join(OUT, "hires_%d.png" % fid))
            frames[fid] = im
            print(fid, end=" ", flush=True)
    print()
    bg = (78, 96, 52)
    ids = sorted(frames)
    S = Image.new("RGB", (12 * 64 * 3, 6 * 64 * 3), bg)
    for fid in ids:
        d, f = fid // 100 - 1, fid % 100 - 1
        im = frames[fid].resize((192, 192), Image.NEAREST)
        S.paste(im, (f * 192, d * 192), im)
    S.save(os.path.join(OUT, "sheet_3x.png"))
    Z = Image.new("RGB", (6 * 64 * 6, 64 * 6), bg)
    for k, d in enumerate(range(1, 7)):
        fid = d * 100 + 9
        if fid in frames:
            im = frames[fid].resize((384, 384), Image.NEAREST)
            Z.paste(im, (k * 384, 0), im)
    Z.save(os.path.join(OUT, "dirs_6x.png"))
    if len(frames) == 72:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
        from aowxlib import ilb
        game = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        def load(rel, fid):
            lib = ilb.read(open(os.path.join(game, rel), "rb").read())
            im = [i for i in lib.images if i.id == fid][0]
            w, h, rows = ilb.decode_record(lib, im.primary)
            q = Image.new("RGBA", (w, h), (0, 0, 0, 0)); px = q.load()
            for y in range(h):
                for x in range(w):
                    c = rows[y][x]
                    if c and c[3]:
                        px[x, y] = tuple(c[:3]) + (255,)
            return q
        C = Image.new("RGB", (6 * 192, 3 * 192), bg)
        for k, d in enumerate(range(1, 7)):
            for r, im in enumerate((load(os.path.join("Images", "UNITS", "Dwr", "giant.ILB"), d * 100 + 9),
                                    load(os.path.join("Images", "UNITS", "Gbn", "troll.ILB"), d * 100 + 9),
                                    frames[d * 100 + 9])):
                im = im.resize((192, 192), Image.NEAREST)
                C.paste(im, (k * 192, r * 192), im)
        C.save(os.path.join(OUT, "compare_3x.png"))


if __name__ == "__main__":
    main()
