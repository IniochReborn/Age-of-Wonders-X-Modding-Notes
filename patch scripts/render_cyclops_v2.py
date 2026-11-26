#!/usr/bin/env python3
r"""
Cyclops unit sprites v2 (2026-11-07) - rendered FROM SCRATCH (user on v1, a troll recolour: "it looks terrible, like
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
PX_PER_UNIT = 16.5           # tuned so the standing figure is about Giant height
FEET = (32.0, 53.0)
LIGHT = np.array([-0.70, 0.62, 0.30]); LIGHT /= np.linalg.norm(LIGHT)

SKIN = np.array([170, 124, 90]) / 255.0
SKIN_D = np.array([120, 78, 60]) / 255.0
FUR = np.array([104, 78, 52]) / 255.0
BELT = np.array([58, 38, 26]) / 255.0
HORN = np.array([226, 210, 172]) / 255.0
EYEW = np.array([240, 236, 222]) / 255.0
IRIS = np.array([196, 120, 20]) / 255.0
PUPIL = np.array([12, 8, 8]) / 255.0
MOUTH = np.array([70, 30, 28]) / 255.0
NAIL = np.array([210, 190, 160]) / 255.0

M_SKIN, M_FUR, M_BELT, M_HORN, M_EYE, M_MOUTH, M_NAIL = range(7)


# ---------------------------------------------------------------------------------------------------- SDF helpers
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
    P = np.array([0.0, 1.02 + g("bob"), 0.0])
    lean = g("lean", 0.35)
    twist = g("twist")
    Rsp = rot_y(twist) @ rot_x(lean)                    # spine frame (lean = pitch forward about +x)
    up = Rsp @ np.array([0, 1.0, 0]); fw = Rsp @ np.array([0, 0, 1.0]); lf = Rsp @ np.array([1.0, 0, 0])
    prims = []   # (kind, args, material, blend_group)

    # legs
    for s, side in ((1, "L"), (-1, "R")):
        hip = P + np.array([s * 0.24, -0.04, 0.0])
        a, b = g("hip" + side, 0.0), g("knee" + side, 0.15)
        th = np.array([0.0, -math.cos(a), math.sin(a)])
        knee = hip + 0.48 * th
        sh = np.array([0.0, -math.cos(a - b), math.sin(a - b)])
        ankle = knee + 0.46 * sh
        ankle[1] = max(ankle[1], 0.09) if g("grounded" + side, 1.0) else ankle[1]
        toe = ankle + np.array([s * 0.03, -0.04, 0.24])
        prims += [("rc", (hip, knee, 0.20, 0.15), M_SKIN, 0),
                  ("rc", (knee, ankle, 0.15, 0.12), M_SKIN, 0),
                  ("rc", (ankle, toe, 0.11, 0.09), M_SKIN, 0)]
        for t in (-1, 0, 1):
            prims.append(("sp", (toe + np.array([t * 0.06, -0.02, 0.06]), 0.035), M_NAIL, 1))

    # torso
    belly = P + 0.26 * up + 0.10 * fw
    chest = P + 0.62 * up + 0.02 * fw
    hump = P + 0.80 * up - 0.16 * fw
    neck = P + 0.86 * up + 0.10 * fw
    prims += [("el", (belly, np.array([0.40, 0.36, 0.38]), Rsp), M_SKIN, 0),
              ("el", (chest, np.array([0.54, 0.34, 0.34]), Rsp), M_SKIN, 0),
              ("sp", (hump, 0.30), M_SKIN, 0),
              ("rc", (P + 0.10 * up, P + 0.50 * up, 0.33, 0.36), M_SKIN, 0)]
    # pecs
    for s in (1, -1):
        prims.append(("sp", (chest + 0.20 * s * lf + 0.20 * fw + 0.04 * up, 0.17), M_SKIN, 0))

    # arms (shoulder pitch p forward, abduction q outward, elbow e forward)
    fists = {}
    for s, side in ((1, "L"), (-1, "R")):
        sh = chest + s * 0.50 * lf + 0.12 * up - 0.02 * fw
        p_, q_, e_ = g("sp" + side, 0.15), g("sa" + side, 0.25), g("el" + side, 0.35)
        dloc = np.array([s * math.sin(q_), -math.cos(q_) * math.cos(p_), math.cos(q_) * math.sin(p_)])
        d1 = Rsp @ dloc if g("armspine", 0.0) else dloc
        elbow = sh + 0.50 * d1
        p2 = p_ + e_
        dloc2 = np.array([s * math.sin(q_) * 0.6, -math.cos(p2), math.sin(p2)])
        d2 = dloc2 / np.linalg.norm(dloc2)
        wrist = elbow + 0.48 * d2
        fist = wrist + 0.10 * d2
        fists[side] = fist
        prims += [("sp", (sh, 0.17), M_SKIN, 0),
                  ("rc", (sh, elbow, 0.18, 0.14), M_SKIN, 0),
                  ("rc", (elbow, wrist, 0.15, 0.13), M_SKIN, 0),
                  ("sp", (fist, 0.16), M_SKIN, 0)]
        for t in (-1, 0, 1):
            prims.append(("sp", (fist + 0.12 * d2 + t * 0.06 * np.cross(d2, [0, 1, 0]) / max(1e-6, np.linalg.norm(np.cross(d2, [0, 1, 0]))), 0.04), M_NAIL, 1))

    # head (thrust forward and low)
    hp = g("headp", 0.0)
    Rh = Rsp @ rot_x(-lean * 0.9 + hp)                  # head stays roughly upright
    hu = Rh @ np.array([0, 1.0, 0]); hf = Rh @ np.array([0, 0, 1.0]); hl = Rh @ np.array([1.0, 0, 0])
    head = neck + 0.30 * up + 0.16 * fw
    prims += [("rc", (neck, head, 0.20, 0.16), M_SKIN, 0),
              ("el", (head, np.array([0.25, 0.26, 0.24]), Rh), M_SKIN, 0),
              ("el", (head - 0.14 * hu + 0.07 * hf, np.array([0.23, 0.12, 0.19]), Rh), M_SKIN, 0)]   # jaw
    brow = head + 0.13 * hu + 0.18 * hf
    prims.append(("rc", (brow - 0.15 * hl, brow + 0.15 * hl, 0.065, 0.065), M_SKIN, 2))
    for s in (1, -1):                                   # ears
        prims.append(("rc", (head + s * 0.22 * hl, head + s * 0.36 * hl + 0.10 * hu - 0.05 * hf, 0.055, 0.012), M_SKIN, 2))
    horn0 = head + 0.24 * hu + 0.07 * hf
    prims.append(("rc", (horn0, horn0 + 0.14 * hu + 0.07 * hf, 0.05, 0.01), M_HORN, 1))
    mouth = head - 0.14 * hu + 0.24 * hf
    prims.append(("rc", (mouth - 0.11 * hl, mouth + 0.11 * hl, 0.025, 0.025), M_MOUTH, 3))
    eye_c = head + 0.04 * hu + 0.175 * hf
    prims.append(("eye", (eye_c, 0.135, hf), M_EYE, 1))

    # loincloth + belt
    waist = P + 0.04 * up
    prims += [("tor", (waist + np.array([0, 0.02, 0.04]), 0.36, 0.05), M_BELT, 1),
              ("skirt", (waist, P - np.array([0, 0.42, -0.02]), 0.35, 0.42), M_FUR, 1)]
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
            d = sd_torus_y(p, *args)
        elif kind == "skirt":                            # hollow-ish flared cone with a ragged hem
            a, b, ra, rb = args
            q = p - a
            ang = np.arctan2(q[..., 0], q[..., 2])
            hem = 0.06 * np.abs(np.sin(ang * 5.0)) + 0.03 * np.sin(ang * 13.0)
            bb = b + np.array([0.0, 0.0, 0.0])
            d = sd_roundcone(p, a, bb, ra, rb)
            d = np.maximum(d, (bb[1] + hem) - p[..., 1])     # cut the bottom raggedly
            d = np.maximum(d, -sd_roundcone(p, a + np.array([0, -0.05, 0]), bb - np.array([0, 0.2, 0]), ra - 0.06, rb - 0.05))
        elif kind == "eye":
            c, r, f = args
            d = sd_sphere(p, c, r)
            eye_info = (c, r, f)
        if grp == 0:
            d_body = smin(d_body, d, 0.10)
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
def render(pose, yaw):
    prims = build(pose)
    R = rot_y(yaw)
    world = []
    for kind, args, m, grp in prims:              # rotate the character into world space
        if kind == "sp":
            args = (R @ args[0], args[1])
        elif kind == "el":
            args = (R @ args[0], args[1], R @ args[2])
        elif kind == "rc":
            args = (R @ args[0], R @ args[1], args[2], args[3])
        elif kind == "tor":
            args = (R @ args[0], args[1], args[2])
        elif kind == "skirt":
            args = (R @ args[0], R @ args[1], args[2], args[3])
        elif kind == "eye":
            args = (R @ args[0], args[1], R @ args[2])
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
        _d, mat, eye = eval_sdf(p, world, need_mat=True)
        base = np.tile(SKIN, (len(hi), 1))
        # skin: darker underside / shadowed back, mild mottling
        mott = 0.5 + 0.5 * np.sin(p[:, 0] * 23.0 + np.sin(p[:, 1] * 17.0) * 2.0) * np.sin(p[:, 2] * 19.0 + p[:, 1] * 7.0)
        grain = (np.sin(p[:, 0] * 97.0 + p[:, 1] * 41.0) * np.sin(p[:, 2] * 89.0 - p[:, 1] * 53.0)
                 + 0.5 * np.sin(p[:, 0] * 151.0 - p[:, 2] * 137.0))
        base = base * (0.88 + 0.14 * mott[:, None] + 0.07 * grain[:, None])
        for m, c in ((M_FUR, FUR), (M_BELT, BELT), (M_HORN, HORN), (M_MOUTH, MOUTH), (M_NAIL, NAIL)):
            base[mat == m] = c
        fur = mat == M_FUR
        angf = np.arctan2(p[fur, 0], p[fur, 2])
        base[fur] *= (0.78 + 0.32 * (0.5 + 0.5 * np.sin(angf * 40.0 + np.sin(p[fur, 1] * 12.0))))[:, None]
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
        shade = shade * (0.80 + 0.25 * np.clip(p[:, 1] / 1.6, 0, 1))      # lower body a little darker
        h = LIGHT - fwd; h /= np.linalg.norm(h)
        sp = np.clip(n @ h, 0, 1) ** 24
        if eye is not None:
            shade = np.where(mat == M_EYE, np.maximum(shade, 0.95), shade)   # the eye always reads
        col[hi] = np.clip(base * shade[:, None] + (0.05 + 0.6 * spec)[:, None] * sp[:, None], 0, 1)
        rim = np.clip(1.0 - np.abs(n @ fwd), 0, 1) ** 3
        col[hi] *= (1.0 - 0.35 * rim)[:, None]           # darker silhouette edge (reads like the game's outline)
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
        return dict(bob=0.0, lean=0.35, spL=0.10, spR=0.10, elL=0.30, elR=0.30, kneeL=0.18, kneeR=0.18)
    if 1 <= frame <= 8:                                   # walk
        ph = (frame - 1) / 8.0 * 2 * math.pi
        sw = math.sin(ph)
        return dict(bob=-0.04 * abs(math.cos(ph)), lean=0.42, twist=0.10 * sw,
                    hipL=0.42 * sw, hipR=-0.42 * sw,
                    kneeL=0.15 + 0.55 * max(0.0, -math.cos(ph)), kneeR=0.15 + 0.55 * max(0.0, math.cos(ph)),
                    spL=-0.45 * sw, spR=0.45 * sw, elL=0.35 + 0.2 * max(0, -sw), elR=0.35 + 0.2 * max(0, sw))
    if frame == 10:                                       # wind-up: both fists raised high
        return dict(lean=0.05, bob=0.02, spL=2.6, spR=2.6, saL=0.35, saR=0.35, elL=0.6, elR=0.6,
                    kneeL=0.25, kneeR=0.25, hipL=0.15, hipR=-0.10, headp=-0.15)
    if frame == 11:                                       # smash: double-fist slam forward and down
        return dict(lean=0.75, bob=-0.10, spL=1.25, spR=1.25, saL=0.12, saR=0.12, elL=0.1, elR=0.1,
                    kneeL=0.55, kneeR=0.45, hipL=0.45, hipR=-0.05, headp=0.2)
    if frame == 12:                                       # hit recoil
        return dict(lean=-0.15, bob=-0.02, spL=0.6, spR=0.9, saL=0.9, saR=0.9, elL=0.8, elR=0.6,
                    kneeL=0.35, kneeR=0.20, hipL=-0.20, hipR=0.25, headp=-0.35, twist=0.25)
    raise ValueError(frame)


YAW = {1: 0.0, 2: 60.0, 3: 120.0, 4: 180.0, 5: 240.0, 6: 300.0}


def main():
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
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
