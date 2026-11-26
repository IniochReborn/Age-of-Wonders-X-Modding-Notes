#!/usr/bin/env python3
r"""
Unicorn cross-check of the AoWEPACK sky overlay (sky_clouds_overlay_asm) against sky_clouds_art.model_pixel.
Fake TAoWHSMap / draw context / level / cell grid; GetMapLevel thunk and timeGetTime stubbed.  Cases: 565 + 555,
plain level and Firmament (fake cached surface), clipping, view offsets, foreign pixels, non-sky hexes.
"""
import random, struct, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UcError
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX
import sky_clouds_art as A
import sky_clouds_overlay_asm as S

MAP, DC, LVL, CELLS, SCR, SURF = 0x600000, 0x601000, 0x602000, 0x610000, 0x700000, 0x900000


GD = os.path.dirname(HERE := os.path.dirname(os.path.abspath(__file__)))
BLOB = S.blob(GD)
CHS = A.chasm_tiles(GD)


def run(fmt, level, T, view, clip, cols=14, rows=10, seed=1, mode=0, cclear=0):
    rng = random.Random(seed)
    z, tex_b, web_b, ents = BLOB
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(S.ZONE, (S.END - S.ZONE + 0xFFF) & ~0xFFF); mu.mem_write(S.ZONE, z)
    mu.mem_map(S.TEX, 0x20000); mu.mem_write(S.TEX, tex_b); mu.mem_write(S.WEB, web_b)
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
            kind = 0 if t < 0.35 else 1 if t < 0.6 else 2 if t < 0.88 else None
            terr = {0: 0xE, 1: 0xE, 2: 0xB}.get(kind, 1)
            mu.mem_write(CELLS + x * 0x800 + y * 0x20 + 0x14, bytes([terr]))
            tile = (sky[rng.randrange(8)] if kind == 0 else clr[rng.randrange(4)] if kind == 1 else
                    CHS[rng.randrange(15)] if kind == 2 else other)
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
    # expected
    exp = raw.astype(np.int64).copy()
    L = A.luts(); tex = A.cloud_tex(); web = A.web_tex()
    pk = [A.packed(t) for t in sky + clr + CHS]
    mask = 0xFFFF if fmt == 0 else 0xFFDF
    cl, ct, cr, cb = clip
    for x in range(-1, cols + 1):
        for y in range(-1, rows + 1):
            if kinds.get((x, y)) is None:
                continue
            wx0, wy0 = x * 32, y * 32 + (x & 1) * 16
            sx, sy = wx0 - vx, wy0 - vy
            k = 0
            for r, (s, e) in enumerate(A.SPANS):
                for xx in range(s, e):
                    X, Y = sx + xx, sy + r
                    if ct <= Y < cb and cl <= X < cr:
                        key = from_fmt(int(exp[Y, X]))
                        kind = None
                        rng_v = range(12) if kinds[(x, y)] < 2 else range(12, 27)
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
                    k += 1
    diff = int((got != exp).sum())
    changed = int((got != raw).sum())
    return diff, changed


if __name__ == "__main__":
    bad = 0
    for case in [dict(fmt=0, level=0, T=123456, view=(10, 7), clip=(0, 0, 420, 300)),
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
