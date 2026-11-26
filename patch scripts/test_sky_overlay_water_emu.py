#!/usr/bin/env python3
r"""
Unicorn cross-check of the AoWEPACK sky overlay (sky_clouds_overlay_asm) against sky_clouds_art.model_pixel.
Fake TAoWHSMap / draw context / level / cell grid; GetMapLevel thunk and timeGetTime stubbed.  WATER build: + sky-shored
water hexes (fake TAoWWaterHexagon in the field HS array, shore base 0xE0 = Clear) holding a smooth water/Clear fog
blend; checks the fog path (cloud delta of the matching Clear tile pixel scaled by the projected sky share).
"""
import random, struct, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UcError
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX
import sky_clouds_art as A
import sky_clouds_overlay_asm as S
import sky_overlay_ext_asm as EXTM

MAP, DC, LVL, CELLS, SCR, SURF = 0x600000, 0x601000, 0x602000, 0x610000, 0x700000, 0x900000


GD = os.path.dirname(HERE := os.path.dirname(os.path.abspath(__file__)))
BLOB = S.blob(GD, True)
PIXEL, PIXNEXT = S.labels_va(True)
EXT = EXTM.build(PIXEL, PIXNEXT)
CHS = A.chasm_tiles(GD)
import sky_transitions_art2 as T2
_w = np.zeros((32, 48, 4), np.uint8); _w[..., 0] = 22; _w[..., 1] = 58; _w[..., 2] = 86; _w[..., 3] = 255
_cl = A.clear_tiles()[0].astype(float)
_rr = np.random.default_rng(3)
WATERFOG = _w.copy()
for _r in range(32):
    for _x in range(48):
        _a = max(0.0, min(1.0, 1.3 - _r / 12.0 - _x / 90.0))
        c = _w[_r, _x, :3] * (1 - _a) + _cl[_r, _x, :3] * _a + _rr.normal(0, 3, 3)
        WATERFOG[_r, _x, :3] = np.clip(c, 0, 255)


def run(fmt, level, T, view, clip, cols=14, rows=10, seed=1, mode=0, cclear=0):
    rng = random.Random(seed)
    z, tex_b, web_b, ents = BLOB
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(S.ZONE, (S.END - S.ZONE + 0xFFF) & ~0xFFF); mu.mem_write(S.ZONE, z)
    mu.mem_map(S.TEX, 0x20000); mu.mem_write(S.TEX, tex_b); mu.mem_write(S.WEB, web_b)
    mu.mem_map(EXTM.EXTRA, 0x1000); mu.mem_write(EXTM.EXTRA, EXT)
    mu.mem_map(0x55778000, 0x1000); mu.mem_write(S.RESUME, b"\xf4")           # hlt = stop marker
    mu.mem_map(0x55702000, 0x1000); mu.mem_write(S.GETLEVEL, b"\xb8" + struct.pack("<I", LVL) + b"\xc3")
    mu.mem_map(0x558FA000, 0x2000)
    mu.mem_write(S.GLOBAL_MAP, struct.pack("<I", MAP))
    mu.mem_write(S.IAT_HSE_GETMAPLEVEL, struct.pack("<I", S.HSE_GETMAPLEVEL))
    mu.mem_map(0x55630000, 0x1000); mu.mem_write(S.HSE_IAT_TIMEGETTIME, struct.pack("<I", 0x55631000 - 0x1000 + 0x800))
    mu.mem_write(0x55630800, b"\xb8" + struct.pack("<I", T) + b"\xc3")
    mu.mem_map(0x600000, 0x10000); mu.mem_map(CELLS, 0x10000); mu.mem_map(SCR, 0x200000); mu.mem_map(SURF, 0x100000)
    mu.mem_map(0xB00000, 0x10000)
    Wp, Hp = 420, 300
    pitch = Wp * 2
    vx, vy = view
    struct_w = lambda a, v: mu.mem_write(a, struct.pack("<i", v))  # noqa: E731
    struct_w(MAP + 0x80, vx); struct_w(MAP + 0x84, vy); struct_w(MAP + 0x88, level)
    struct_w(MAP + 0x94, -1); struct_w(MAP + 0x98, -1); struct_w(MAP + 0x9C, cols + 2); struct_w(MAP + 0xA0, rows + 2)
    struct_w(DC + 0x28, 0x56509310 if fmt == 0 else 0x55509310)
    struct_w(DC + 0x0C, pitch); struct_w(DC + 0x20, SCR)
    for k, v in zip((0x10, 0x14, 0x18, 0x1C), clip):
        struct_w(DC + k, v)
    struct_w(LVL + 0x0C, cols); struct_w(LVL + 0x10, rows)
    struct_w(LVL + 0x74, LVL + 0x100); struct_w(LVL + 0x78, LVL + 0x400)
    for x in range(cols):
        struct_w(LVL + 0x100 + 4 * x, x * 0x800)
    for y in range(rows):
        struct_w(LVL + 0x400 + 4 * y, CELLS + y * 0x20)
    sky, clr = A.sky_tiles(), A.clear_tiles()
    other = np.zeros((32, 48, 4), np.uint8); other[..., 0] = 90; other[..., 1] = 140; other[..., 2] = 60
    other[..., 3] = 255
    kinds = {}
    scr = np.zeros((Hp, Wp), np.int64)
    for x in range(cols):
        for y in range(rows):
            t = rng.random()
            kind = 0 if t < 0.3 else 1 if t < 0.5 else 2 if t < 0.65 else 'w' if t < 0.9 else None
            terr = {0: 0xE, 1: 0xE, 2: 0xB, 'w': 0}.get(kind, 1)
            cell = CELLS + x * 0x800 + y * 0x20
            mu.mem_write(cell + 0x14, bytes([terr]))
            if kind == 1:
                hsa = 0xB08000 + (x * 16 + y) * 0x40
                mu.mem_write(cell + 0x8, struct.pack("<I", hsa)); mu.mem_write(cell + 0xD, bytes([1]))
                mu.mem_write(hsa, struct.pack("<I", hsa + 0x10))
                mu.mem_write(hsa + 0x18, struct.pack("<I", hsa + 0x20))
                mu.mem_write(hsa + 0x2C, struct.pack("<I", 0x5A1B0002))
            if kind == 'w':
                hsa = 0xB00000 + (x * 16 + y) * 0x40
                hexo = hsa + 0x10
                mu.mem_write(cell + 0x8, struct.pack("<I", hsa)); mu.mem_write(cell + 0xD, bytes([2]))
                mu.mem_write(hsa, struct.pack("<II", 0xB0F000, hexo))
                mu.mem_write(hexo, struct.pack("<I", S.WATER_VMT))
                mu.mem_write(hexo + 0x14, bytes([0x21]))
                mu.mem_write(hexo + 0x1a, bytes([0xE0, 0, 0, 0, 0, 0xA0]))
            tile = (sky[rng.randrange(8)] if kind == 0 else clr[rng.randrange(4)] if kind == 1 else
                    CHS[rng.randrange(15)] if kind == 2 else WATERFOG if kind == 'w' else other)
            if kind in (0, 1, 2) and rng.random() < 0.5:          # pair cross-fade in the upper rows
                own = (sky[0], clr[0], CHS[0])[kind].astype(float)
                oth = (sky[0], clr[0], CHS[0])[(kind + 1 + rng.randrange(2)) % 3].astype(float)
                tile = tile.copy()
                for rr in range(14):
                    w_ = max(0.0, 0.9 - rr / 14.0)
                    tile[rr, :, :3] = np.clip(np.round(own[rr, :, :3] * (1 - w_) + oth[rr, :, :3] * w_), 0, 255)
            kinds[(x, y)] = kind
            px, py = x * 32 - vx, y * 32 + (x & 1) * 16 - vy
            for r, (s, e) in enumerate(A.SPANS):
                for xx in range(s, e):
                    X, Y = px + xx, py + r
                    if 0 <= X < Wp and 0 <= Y < Hp:
                        q = tile[r, xx]
                        scr[Y, X] = ((int(q[0]) >> 3) << 11) | ((int(q[1]) >> 2) << 5) | (int(q[2]) >> 3)
    # foreign pixels (a 'unit' drawn over the sky)
    for _ in range(300):
        scr[rng.randrange(Hp), rng.randrange(Wp)] = 0x1234
    to_fmt = (lambda p: p) if fmt == 0 else (lambda p: ((p >> 1) & 0x7FE0) | (p & 0x1F))
    from_fmt = (lambda p: p) if fmt == 0 else (lambda p: ((p & 0x7FE0) << 1) | (p & 0x1F))
    raw = np.vectorize(to_fmt)(scr).astype(np.uint16)
    mu.mem_write(SCR, raw.tobytes())
    surf = None
    if level == 3:
        SW, SH = 333, 211
        srng = np.random.default_rng(seed)
        surf = srng.integers(0, 0x10000, (SH, SW)).astype(np.uint16)
        surf[srng.random((SH, SW)) < 0.05] = 0
        if fmt == 1:
            surf &= 0x7FFF
        mu.mem_write(SURF, surf.tobytes())
        mu.mem_write(S.BSS_BUF, struct.pack("<IIIIII", SURF, SW, SH, 1, MAP, 0x56509310 if fmt == 0 else 0x55509310))
    mu.mem_write(0xB0FF00, struct.pack("<I", 0xDEAD0000))
    mu.reg_write(UC_X86_REG_ESP, 0xB0FF00); mu.reg_write(UC_X86_REG_EAX, MAP); mu.reg_write(UC_X86_REG_EDX, DC)
    if mode == 1:
        mu.mem_write(S.GLOBAL_MAP, struct.pack("<I", 0x12345678))
    mu.mem_write(S.CCLEAR, bytes([cclear]))
    try:
        if mode == 0:
            mu.emu_start(ents["main"], S.RESUME, count=200_000_000)
        else:
            mu.reg_write(UC_X86_REG_ESP, 0xB0FF00 - 4); mu.mem_write(0xB0FF00 - 4, struct.pack("<I", 0xDEAD0000))
            mu.mem_map(0xDEAD0000, 0x1000)
            mu.emu_start(ents["combat"], 0xDEAD0000, count=200_000_000)
    except UcError as e:
        print("emu error", e, hex(mu.reg_read(0x1A)) if False else "")
        raise
    got = np.frombuffer(bytes(mu.mem_read(SCR, Wp * Hp * 2)), np.uint16).reshape(Hp, Wp)
    assert mu.reg_read(UC_X86_REG_ESP) == 0xB0FF00 - (8 if mode == 0 else 0), hex(mu.reg_read(UC_X86_REG_ESP))
    if mode == 0:                                   # second, water-only pass (after the dynamic scene)
        mu.mem_map(0xDEAD0000, 0x1000)
        sp_ = 0xB0F000
        mu.mem_write(sp_, struct.pack("<II", 0xDEAD0000, 2))
        mu.reg_write(UC_X86_REG_ESP, sp_); mu.reg_write(UC_X86_REG_EAX, MAP); mu.reg_write(UC_X86_REG_EDX, DC)
        mu.emu_start(S.core_va(True), 0xDEAD0000, count=200_000_000)
        assert mu.reg_read(UC_X86_REG_ESP) == sp_ + 8, hex(mu.reg_read(UC_X86_REG_ESP))
    got = np.frombuffer(bytes(mu.mem_read(SCR, Wp * Hp * 2)), np.uint16).reshape(Hp, Wp)
    # expected
    exp = raw.astype(np.int64).copy()
    L = A.luts(); tex = A.cloud_tex(); web = A.web_tex()
    A_mp = lambda key_, kind_, sp_, wx_, wy_: A.model_pixel(key_, kind_, sp_, wx_, wy_, T, tex, L, web)  # noqa: E731
    pk = [A.packed(t) for t in sky + clr + CHS]
    ET = EXTM.edge_table()
    mask = 0xFFFF if fmt == 0 else 0xFFDF
    cl, ct, cr, cb = clip
    order = [(x, y) for x in range(-1, cols + 1) for y in range(-1, rows + 1) if kinds.get((x, y)) not in (None, 'w')]
    if mode == 0:
        order += [(x, y) for x in range(-1, cols + 1) for y in range(-1, rows + 1) if kinds.get((x, y)) == 'w']
    for (x, y) in order:
        if True:
            water = kinds[(x, y)] == 'w'
            wx0, wy0 = x * 32, y * 32 + (x & 1) * 16
            sx, sy = wx0 - vx, wy0 - vy
            k = 0
            for r, (s, e) in enumerate(A.SPANS):
                for xx in range(s, e):
                    X, Y = sx + xx, sy + r
                    if ct <= Y < cb and cl <= X < cr:
                        key = from_fmt(int(exp[Y, X]))
                        kind = None
                        rng_v = range(0) if water else range(12) if kinds[(x, y)] < 2 else range(12, 27)
                        for v in rng_v:
                            if (pk[v][k] & mask) == key:
                                kind = 0 if v < 8 else 1 if v < 12 else 2
                                break
                        if kind == 0 and mode == 1 and cclear:
                            key = pk[8 + ((x * 3 + y) & 3)][k]; kind = 1
                        if kind is not None:
                            sp = 0
                            if surf is not None and mode == 0:
                                px = (vx - (vx >> 2)); py = (vy - (vy >> 2))
                                bx = (wx0 - px) % surf.shape[1]; by = (wy0 - py) % surf.shape[0]
                                sp = from_fmt(int(surf[(by + r) % surf.shape[0], (bx + xx) % surf.shape[1]]))
                            out = A.model_pixel(key, kind, sp, wx0 + xx, wy0 + r, T, tex, L, web)
                            exp[Y, X] = to_fmt(out)
                        elif not water and kinds[(x, y)] in (0, 1, 2) and ET[k] & sum(
                                1 << e for e, n_ in enumerate(((x - 1, y - 1 + (x & 1)), (x, y - 1), (x + 1, y - 1 + (x & 1)),
                                                                (x + 1, y + (x & 1)), (x, y + 1), (x - 1, y + (x & 1))))
                                if kinds.get(n_) in (0, 1, 2) and kinds.get(n_) != kinds[(x, y)]):
                            own = kinds[(x, y)]
                            cc = lambda p: ((p >> 11) * 4, ((p >> 5) & 63) * 4, (p & 31) * 4)  # noqa: E731
                            Ap = pk[(0, 8, 12)[own]][k]
                            best = None
                            for oth in range(3):
                                if oth == own:
                                    continue
                                Bp = pk[(0, 8, 12)[oth]][k]
                                vs = [b_ - a_ for a_, b_ in zip(cc(Ap), cc(Bp))]
                                vp = [p_ - a_ for a_, p_ in zip(cc(Ap), cc(key))]
                                den = sum(v * v for v in vs); num = sum(a_ * b_ for a_, b_ in zip(vs, vp))
                                if den < S.FOG_MINDEN or num <= 0:
                                    continue
                                t_ = (num << 8) // den
                                if t_ > 0x110:
                                    continue
                                t_ = min(t_, 256)
                                if t_ < 16:
                                    continue
                                res = sum((((vs[c_] * t_) >> 8) - vp[c_]) ** 2 for c_ in range(3))
                                if best is None or res < best[0]:
                                    best = (res, t_, Bp, oth)
                            hang = any(n_ in kinds and kinds[n_] is None for n_ in (
                                (x - 1, y - 1 + (x & 1)), (x, y - 1), (x + 1, y - 1 + (x & 1)), (x - 1, y + (x & 1))))
                            if best is not None and hang and best[1] > EXTM.HANG_TMAX:
                                best = None
                            if best is not None and best[0] <= EXTM.SKYFOG_MAXRES:
                                res, t_, Bp, oth = best
                                sp = 0
                                if surf is not None and mode == 0:
                                    px = (vx - (vx >> 2)); py = (vy - (vy >> 2))
                                    bx = (wx0 - px) % surf.shape[1]; by = (wy0 - py) % surf.shape[0]
                                    sp = from_fmt(int(surf[(by + r) % surf.shape[0], (bx + xx) % surf.shape[1]]))
                                RA = from_fmt(to_fmt(A_mp(Ap, own, sp, wx0 + xx, wy0 + r)))
                                RB = from_fmt(to_fmt(A_mp(Bp, oth, sp, wx0 + xx, wy0 + r)))
                                o = 0
                                for sh, m in ((11, 31), (5, 63), (0, 31)):
                                    acc = (((RA >> sh) & m) - ((Ap >> sh) & m)) * (256 - t_) + (((RB >> sh) & m) - ((Bp >> sh) & m)) * t_
                                    v_ = ((key >> sh) & m) + (acc >> 8)
                                    o |= max(0, min(m, v_)) << sh
                                exp[Y, X] = to_fmt(o)
                        elif water and mode == 0:
                            W4 = (20, 58, 44)
                            cc = lambda p: ((p >> 11) * 4, ((p >> 5) & 63) * 4, (p & 31) * 4)  # noqa: E731
                            best = None
                            for kk in range(3):
                                cs = pk[(0, 8, 12)[kk]][k]
                                vs = [a_ - b_ for a_, b_ in zip(cc(cs), W4)]
                                vp = [a_ - b_ for a_, b_ in zip(cc(key), W4)]
                                den = sum(v * v for v in vs); num = sum(a_ * b_ for a_, b_ in zip(vp, vs))
                                if den < S.FOG_MINDEN or num <= 0:
                                    continue
                                al = (num << 8) // den
                                if al > 0x110:
                                    continue
                                al = min(al, 256)
                                if al < 16:
                                    continue
                                res = sum((((vs[c_] * al) >> 8) - vp[c_]) ** 2 for c_ in range(3))
                                if best is None or res < best[0]:
                                    best = (res, al, cs, kk)
                            if best is not None and best[0] <= S.FOG_MAXRES:
                                res, al, cs, kk = best
                                sp = 0
                                if surf is not None and mode == 0:
                                    px = (vx - (vx >> 2)); py = (vy - (vy >> 2))
                                    bx = (wx0 - px) % surf.shape[1]; by = (wy0 - py) % surf.shape[0]
                                    sp = from_fmt(int(surf[(by + r) % surf.shape[0], (bx + xx) % surf.shape[1]]))
                                R = from_fmt(to_fmt(A.model_pixel(cs, kk, sp, wx0 + xx, wy0 + r, T, tex, L, web)))
                                o = 0
                                for sh, m in ((11, 31), (5, 63), (0, 31)):
                                    v = ((key >> sh) & m) + (((((R >> sh) & m) - ((cs >> sh) & m)) * al) >> 8)
                                    o |= max(0, min(m, v)) << sh
                                exp[Y, X] = to_fmt(o)
                    k += 1
    diff = int((got != exp).sum())
    changed = int((got != raw).sum())
    return diff, changed


if __name__ == "__main__":
    bad = 0
    for case in [dict(fmt=0, level=0, T=123456, view=(10, 7), clip=(0, 0, 420, 300)),
                 dict(fmt=0, level=0, T=4242, view=(0, 0), clip=(0, 0, 420, 300), seed=11),
                 dict(fmt=1, level=0, T=8888, view=(7, 3), clip=(0, 0, 420, 300), seed=12),
                 dict(fmt=1, level=0, T=987654, view=(-20, 5), clip=(13, 9, 400, 290)),
                 dict(fmt=0, level=3, T=5555555, view=(64, 40), clip=(0, 0, 420, 300)),
                 dict(fmt=1, level=3, T=77, view=(3, 100), clip=(30, 20, 380, 250)),
                 dict(fmt=0, level=3, T=4000000000, view=(-50, -30), clip=(0, 0, 420, 300)),
                 dict(fmt=0, level=3, T=31337, view=(40, 20), clip=(0, 0, 420, 300), mode=1),
                 dict(fmt=1, level=0, T=2222222, view=(0, 0), clip=(5, 5, 410, 295), mode=1, seed=4),
                 dict(fmt=0, level=0, T=7777, view=(16, 8), clip=(0, 0, 420, 300), mode=1, seed=5, cclear=1),
                 dict(fmt=1, level=0, T=99999, view=(0, 0), clip=(0, 0, 420, 300), mode=0, seed=6, cclear=1)]:
        d, c = run(**case)
        print(case, "mismatch", d, "changed", c)
        bad += d
    print("TOTAL mismatches", bad)
