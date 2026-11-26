#!/usr/bin/env python3
r"""
Images\Effects\DualDF.ILB: tactical/cast effect sprites for the Death/Fire spells (2026-10-06).

A brand-new v4.0 image library (written through old modding tools\research\ilbcodec.py; every image is a raw
Sprite16 (type 22) with a transparent key) - nothing in the vanilla ILBs is touched.  Image ids:
   0-5    Bloodbath sparkles: PARTICLE.ILB 3-5 / 21-23 re-coloured deep crimson (19x19, additive 770/50)
  40-47   Hellfire projectiles: Hurl Boulder's BALLS.ILB 3-6 stones (darker, ember flecks) with a ~90 px flame tail,
          thick at the stone and thinning behind it - 64x128 opaque 256/0, stone at hail's anchor (ys = -97)
  50-57   Hellfire impact: small expanding fiery flash with embers, 64x64 additive 770/50 (hail's impact is 29x29)
  60-99   Hellfire hell portal: 40-frame swirling dark disc 96x56 (alpha 258/88), spawned 300 px above the target
          by patch_tc_hellfire_portal_v1.py as a kind-0x26 effect reading spell slot 3 (3 ticks/frame = 120 ticks)
 100-199  Bloodbath shadow sword: 100 frames 64x150 (alpha 258/75, 1 tick/frame, spawned at tick 0 by
          patch_tc_bloodbath_aura_v1.py): fade in while still (0-11), hold (12-19), descend (20-59), then the
          engine's BIG blood-hit gush (BHBIG1.ILB 0-15, full speed) + ground pool (GNDBLOOD.ILB) from tick 60
Referenced from Spells.pfs by patch_dual_sphere_spells_v1.py (gfx slots).  --preview renders dualdf_preview.png.
Dry run by default; --apply writes the ILB (new file; --revert deletes it).
"""
import argparse, math, os, random, struct, sys
import numpy as np
import sys as _sys; _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import game_dir, game_file   # 2026-10-11: de-baked
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "old modding tools", "research"))
import ilbcodec

GAME = game_dir()   # 2026-10-11: de-baked (AOW_GAME_DIR or parent of patch scripts)
OUT = os.path.join(GAME, "Images", "Effects", "DualDF.ILB")
PARTICLE = os.path.join(GAME, "Images", "Effects", "Particle.ILB")
BALLS = os.path.join(GAME, "Images", "TCombat", "Objects", "Balls.ILB")
BHBIG = os.path.join(GAME, "Images", "TCombat", "Objects", "BHBig1.ILB")
GNDBLOOD = os.path.join(GAME, "Images", "TCombat", "Objects", "GndBlood.ILB")
KEY = 0xF81F                       # magenta key for opaque / alpha sprites (never produced by the painters)
# ⚠ blendValue is a PERCENT 0..100: GFXEPACK keeps a TLookupBlendTableCollection100 and BlendColorKey555 indexes it by
# the value - 120 (Ashes v1-v3, 2026-10-13) read a garbage table pointer -> AV in GFXEPACK+0xB306, the game closed silently.
PIXFMT = 0x56509310
random.seed(20261006)


def c565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def raw_pixels(lib, img_id):
    """Decode a raw 16-bit (type 16/22) image into an RGBA PIL image (key colour -> transparent)."""
    img = next(i for i in lib["images"] if i["id"] == img_id); r = img["parts"][0]
    assert r["type"] in (16, 22) and r["size"] == r.get("cw", r["w"]) * r.get("ch", r["h"]) * 2, "not a raw image"
    cw, ch, cx, cy = r.get("cw", r["w"]), r.get("ch", r["h"]), r.get("cx", 0), r.get("cy", 0)
    im = Image.new("RGBA", (r["w"], r["h"]), (0, 0, 0, 0)); px = im.load(); base = lib["pixeldata"]; o = r["off"]
    key = r.get("transp")
    for y in range(ch):
        for x in range(cw):
            v = struct.unpack_from("<H", base, o)[0]; o += 2
            if r["type"] == 22 and key is not None and v == (key & 0xFFFF): continue
            px[cx + x, cy + y] = c565(*[]) if False else c565(v) + (255,)
    return im, r


# ------------------------------------------------------------------ painters (RGBA, alpha 0 = transparent)
def particles():
    lib = ilbcodec.read(PARTICLE); out = []
    for k, src in enumerate((3, 4, 5, 21, 22, 23)):
        im, r = raw_pixels(lib, src); px = im.load()
        res = Image.new("RGBA", im.size, (0, 0, 0, 0)); rp = res.load()
        for y in range(im.height):
            for x in range(im.width):
                cr, cg, cb, ca = px[x, y]
                lum = (0.3 * cr + 0.59 * cg + 0.11 * cb) / 255.0
                if lum < 0.03: continue
                # v2 (2026-10-11, user: "deeper/darker red, like the blood splatter"): blood red - lower intensity
                # (additive draw adds less light), pure red, no purple, no pink highlights
                pr = min(255, int(185 * lum ** 0.9)); pg = int(5 * lum); pb = int(7 * lum)
                rp[x, y] = (pr, pg, pb, 255)
        out.append(res)
    return out


N_SWORD = 100                # frames at 1 tick each (f18 = 0): the sparkle phase is 100 ticks
FADE_IN, HOLD, DESCENT = 12, 8, 40
DESCENT_END = FADE_IN + HOLD + DESCENT          # tick 60: the tip reaches the unit, blood gushes from here


def sword_frames():
    """v4 (1 tick per frame so the blood can run at full speed): the small fuzzy black sword fades in while hanging
    still above the unit (ticks 0-11), waits (12-19), then descends at a steady pace (20-59); at tick 60 the engine's
    BIG blood-hit gush (BHBIG1 0-15, one frame per tick) sprays from the wound and a ground pool (GNDBLOOD) spreads
    at the feet and stays; the sword fades out over ticks 62-80."""
    W, H = 64, 150; frames = []
    FEET = 130                                  # the entry anchor (ys = -130) = the unit's hex centre
    tip_start, tip_end = 44, FEET - 30          # blade tip: above the head -> chest height
    for i in range(N_SWORD):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        if i < FADE_IN + HOLD: t = 0.0
        else: t = min(1.0, (i - FADE_IN - HOLD) / float(DESCENT))
        t = t * t * (3 - 2 * t)                                 # ease in/out
        tip = tip_start + (tip_end - tip_start) * t
        fade_in = min(1.0, (i + 1) / float(FADE_IN))
        fade_out = 1.0 if i < 62 else max(0.0, 1.0 - (i - 61) / 19.0)
        a = int(235 * fade_in * fade_out)
        cx = 32
        core, edge = (6, 4, 10, a), (26, 20, 32, int(a * 0.85))
        L = 34; bw = 2
        dr.polygon([(cx - bw, tip - L + 7), (cx + bw, tip - L + 7), (cx + bw, tip - 8), (cx, tip), (cx - bw, tip - 8)], fill=edge)
        dr.polygon([(cx - 1, tip - L + 7), (cx + 1, tip - L + 7), (cx + 1, tip - 8), (cx, tip - 1), (cx - 1, tip - 8)], fill=core)
        gy = tip - L + 7
        dr.rectangle([cx - 6, gy - 2, cx + 6, gy], fill=core)                      # crossguard
        dr.rectangle([cx - 1, gy - 9, cx + 1, gy - 2], fill=core)                  # grip
        dr.ellipse([cx - 2, gy - 12, cx + 2, gy - 8], fill=core)                   # pommel
        im = im.filter(ImageFilter.GaussianBlur(1.6))                             # fuzzy / ghostly
        # keep the core dark after the blur: re-stamp a thin dark spine
        dr = ImageDraw.Draw(im)
        dr.line([(cx, tip - L + 7), (cx, tip - 2)], fill=(4, 2, 8, int(a * 0.9)), width=1)
        if i >= DESCENT_END:
            splash(im, cx, tip_end, FEET, i - DESCENT_END)       # baked BHBIG1 gush (+ pool) as in v4 - the user liked it
        frames.append(im)
    return frames


_BH = {}
def splash(im, cx, cy, feet, k):
    r"""Bake the engine's own blood: the BIG blood-hit gush (TCOMBAT\OBJECTS\BHBIG1.ILB 0-15, what a powerful melee
    hit sprays) centred on the wound at (cx, cy), one gush frame per effect frame (k), and a ground pool
    (GNDBLOOD.ILB, frames 0-7 cycling then holding the biggest) spreading at the feet from k >= 2."""
    for key, path in (("big", BHBIG), ("gnd", GNDBLOOD)):
        if key not in _BH: _BH[key] = ilbcodec.read(path)
    if k < 16:                                                   # the full 16-frame gush, one frame per tick
        src, r = raw_pixels(_BH["big"], k)
        im.alpha_composite(src, (cx - 32, cy - 33))             # BHBIG1 anchor xs -28/ys -33 ~ centre of the burst
    if k >= 3:
        pool = (0, 1, 2, 5, 7)[min(k - 3, 4)]                    # pool grows over 5 ticks then holds the biggest
        src, r = raw_pixels(_BH["gnd"], pool)
        im.alpha_composite(src, (cx - 31, feet - 47))           # GNDBLOOD anchor xs -31 / ys -47 (pool sits at the feet)


def splash_procedural(im, cx, cy, k):
    """(unused fallback) procedural blood splash at (cx, cy): k = 0..6, droplets flying out then falling, pool below."""
    dr = ImageDraw.Draw(im)
    rnd = random.Random(99)
    n = 14
    for j in range(n):
        ang = rnd.uniform(math.pi * 1.05, math.pi * 1.95)          # upward half-circle
        spd = rnd.uniform(2.2, 5.0); g = 0.9
        tt = k + 0.5
        x = cx + math.cos(ang) * spd * tt
        y = cy + math.sin(ang) * spd * tt + g * tt * tt * 0.5
        r = max(1, int(2.6 - k * 0.3))
        col = (150 + rnd.randint(0, 50), 8, 12, 255) if k < 6 else (120, 6, 10, 180)
        dr.ellipse([x - r, y - r, x + r, y + r], fill=col)
    # central burst + pool
    br = 7 + k * 2
    dr.ellipse([cx - br, cy - br // 2, cx + br, cy + br // 3], fill=(140 + min(k * 10, 60), 6, 10, 255 if k < 5 else 170))
    dr.ellipse([cx - br // 2, cy - br // 4, cx + br // 2, cy + br // 6], fill=(200, 20, 24, 255 if k < 5 else 170))


def boulders():
    """v2: Hurl Boulder's own dark stones (BALLS 3-6, as the user asked) with a few ember pixels, trailing a LONG
    flame tail (~44 px) that fades out towards its end (colour -> dark red and alpha -> 0, dithered by rec_for)."""
    """v5: back on hail's 64x64 canvas/anchor; the stone carries only a short (~22 px) flame cap - the long tail is
    now the slot-1 TRAIL (trail_frames) that the engine draws along the path behind the projectile."""
    lib = ilbcodec.read(BALLS); frames = []
    srcs = [3, 4, 5, 6, 3, 4, 5, 6]
    W, H = 64, 64
    for i, sid in enumerate(srcs):
        src, r = raw_pixels(lib, sid)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sp = src.load()
        rock = [(x, y) for y in range(64) for x in range(64) if sp[x, y][3]]
        xs = [p[0] for p in rock]; ys = [p[1] for p in rock]
        rx0, rx1, ry0, ry1 = min(xs), max(xs), min(ys), max(ys); rcx = (rx0 + rx1) / 2 + 0.5
        shift = 0
        tail = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        rnd = random.Random(11 + i)
        root_y = ry0 + shift + 3
        Lt = 0                                                  # v7: no flame cap at all - plain Hurl Boulder stone
        tp = tail.load()
        def plot(x, y, col, a):
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W and 0 <= yi < H:
                pr, pg, pb, pa = tp[xi, yi]
                if a > pa: tp[xi, yi] = col + (a,)
        def grad(t):                                            # v6: no white/yellow - dark orange -> red -> ember
            if t < 0.3: c0, c1, u = (235, 130, 30), (200, 60, 10), t / 0.3
            else: c0, c1, u = (200, 60, 10), (70, 10, 6), (t - 0.3) / 0.7
            return tuple(int(c0[k] + (c1[k] - c0[k]) * u) for k in range(3))
        # 1) solid wedge: half-width 7 px at the stone -> 0 at ~55% of the length, edges wavering (Lt = 0: none)
        for s in range(0, int(Lt * 0.6)):
            t = s / float(Lt)
            y = root_y - s
            hw = 7.0 * (1 - t / 0.6) ** 1.1
            wob = 0.9 * math.sin(s * 0.45 + i * 0.9)
            for k in range(-int(hw + 1), int(hw + 2)):
                xx = rcx + k + wob
                edge = abs(k) / (hw + 0.5) if hw > 0.5 else 1.0
                a = int(255 * (1 - t / 0.6) ** 0.7 * (1 - 0.35 * edge))
                plot(xx, y, grad(min(1.0, t * 0.9 + 0.25 * edge)), a)
        # 2) strands continuing to the tip, thinning and fading (none when Lt = 0)
        strands = [(rnd.uniform(-4.0, 4.0), rnd.uniform(0.75, 1.0), rnd.uniform(0, 6.28), rnd.uniform(2.0, 4.0)) for _ in range(8 if Lt else 0)]
        for x0, length, phase, amp in strands:
            steps = int(Lt * length * 2)
            for s in range(int(steps * 0.3), steps):
                t = s / float(steps)
                y = root_y - Lt * length * t
                x = rcx + x0 * (0.4 + 1.6 * t) + amp * math.sin(t * 6.5 + phase + i * 0.7) * t
                a = int(235 * (1 - t) ** 1.7)
                plot(x, y, grad(t), a)
        # 3) drifting sparks (none when Lt = 0)
        for _ in range(10 if Lt else 0):
            t = rnd.uniform(0.3, 1.0); plot(rcx + rnd.uniform(-10, 10) * t, root_y - Lt * t * rnd.uniform(0.6, 1.05), (255, 215, 100), int(230 * (1 - t)))
        im.alpha_composite(tail)
        px = im.load()
        for (x, y) in rock:
            cr, cg, cb, _a = sp[x, y]
            col = (int(cr * 0.5), int(cg * 0.45), int(cb * 0.45), 255)                 # v9: much darker stone
            if rnd.random() < 0.06 and (cr + cg + cb) < 200:
                col = (240, 120 + rnd.randint(0, 60), 25, 255)                            # ember flecks
            px[x, y + shift] = col
        frames.append(im)
    return frames


def impacts():
    frames = []
    for i in range(8):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        t = i / 7.0; cx, cy = 32, 33
        r = 4 + 13 * t; a = int(255 * (1 - t) ** 1.2)
        dr.ellipse([cx - r, cy - r * 0.55, cx + r, cy + r * 0.55], fill=(220, 70, 15, a))
        r2 = r * 0.55
        dr.ellipse([cx - r2, cy - r2 * 0.55, cx + r2, cy + r2 * 0.55], fill=(255, 200, 80, a))
        rnd = random.Random(31 + i)
        for j in range(10):
            ang = rnd.uniform(0, 2 * math.pi); d = (6 + 16 * t) * rnd.uniform(0.6, 1.0)
            x = cx + math.cos(ang) * d; y = cy + math.sin(ang) * d * 0.6 - 8 * t
            dr.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(255, 140 + rnd.randint(0, 80), 30, a))
        im = im.filter(ImageFilter.GaussianBlur(0.6))
        frames.append(im)
    return frames


# ------------------------------------------------------------------ ILB assembly
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def keep(px, x, y):
    """Per-pixel alpha -> keyed sprite via ordered (Bayer 4x4) dithering: partially transparent pixels survive in
    proportion to their alpha, which reads as a soft / fading edge at game scale."""
    return px[x, y][3] > BAYER[y % 4][x % 4] * 16 + 8


def rec_for(im, name, draw, blend, key, sub, ptype=22):
    """Trim to the kept-pixel bbox (clip box), encode raw RGB565, key colour outside (alpha dithered, see keep).
    ptype 16 = Picture16 (no key, whole image raw) - used for the PARTICLE copies so they match the originals."""
    W, H = im.size; px = im.load()
    if ptype == 16:
        data = b"".join(struct.pack("<H", rgb565(*px[x, y][:3])) for y in range(H) for x in range(W))
        return ilbcodec.Rec(type=16, info=3, name=name.encode(), w=W, h=H, xs=0, ys=0, sub=sub, unkA=1, size=len(data), off=0,
                            totw=W, toth=H, drawMode=draw, blendValue=blend, pixFmt=PIXFMT), data
    pts = [(x, y) for y in range(H) for x in range(W) if keep(px, x, y)]
    if pts:
        cx, cy = min(p[0] for p in pts), min(p[1] for p in pts); cw = max(p[0] for p in pts) - cx + 1; ch = max(p[1] for p in pts) - cy + 1
    else:
        cx, cy, cw, ch = 0, 0, 1, 1
    data = bytearray()
    for y in range(cy, cy + ch):
        for x in range(cx, cx + cw):
            r, g, b, a = px[x, y]
            if not keep(px, x, y): v = key
            else:
                v = rgb565(r, g, b)
                if v == key: v ^= 0x0020                        # never emit the key colour as art
            data += struct.pack("<H", v)
    r = ilbcodec.Rec(type=22, info=3, name=name.encode(), w=W, h=H, xs=0, ys=0, sub=sub, unkA=1, size=len(data), off=0,
                     totw=W, toth=H, drawMode=draw, blendValue=blend, pixFmt=PIXFMT, cw=cw, ch=ch, cx=cx, cy=cy, transp=key)
    return r, bytes(data)


N_PORTAL = 50                # driver frames: 50 x (f18=3 -> 4 ticks) = 200 ticks, longer than the rain


def sparkles():
    """Exact copies of PARTICLE.ILB 15-17 (the white sparkle Mind Decay whirls in its dark draw mode) for Hellfire's
    slot 4, so the whirl uses the very same sprite."""
    lib = ilbcodec.read(PARTICLE); out = []
    for src in (15, 16, 17):
        im, r = raw_pixels(lib, src); out.append(im)
    return out


def portal_frames():
    """Hell portal above the drop area, in the style of Mind Decay's portal - which the engine builds out of many
    small sparkle effects whirling along arcs 200 px above the target (TfxHS.NewFrame kind 0x2A spawns kind-0x1F
    sparkles on arc paths every other tick): a 160x72 isometric vortex of small ember/crimson/purple sparks on
    three spiral arms spinning inward over a faint smoky dark disc, with a smouldering core.  40 frames = one
    revolution; alpha fades in over 4 frames and out over the last 6 (dithered by rec_for)."""
    # v3: the visible portal is now the engine's own sparkle whirl (patch_tc_hellfire_portal_v1.py spawns kind-0x1F
    # sparkles on arcs, drawn dark like Mind Decay's); these driver frames are therefore fully transparent 1x1 keys
    # whose only job is to keep the driver effect alive for N_PORTAL*(f18+1) ticks.
    return [Image.new("RGBA", (2, 2), (0, 0, 0, 0)) for _ in range(N_PORTAL)]
    W, H = 160, 72; rx, ry = 78.0, 33.0; cx, cy = 80.0, 36.0; frames = []     # (old painted portal, unreachable)
    rnd = random.Random(1234)
    # Mind Decay's whirl is made of ~19 px soft sparkle blobs drawn dark, orbiting on arcs: model it as 14 big soft
    # black blobs orbiting the flat ellipse at different phases/radii, each dragging a short fading wake, plus a
    # few smaller dark-purple ones; no disc, no rim.  Soft edges come from the alpha falloff (dithered by rec_for).
    blobs = [(rnd.random(), rnd.uniform(0.55, 1.0), rnd.uniform(7.0, 10.0), rnd.random() < 0.25) for _ in range(14)]
    for i in range(N_PORTAL):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); px = im.load()
        rot = 2 * math.pi * i / N_PORTAL
        fade = min(1.0, (i + 1) / 4.0) * (1.0 if i < N_PORTAL - 6 else max(0.0, (N_PORTAL - i) / 6.0))
        for ph, rr, rad, purple in blobs:
            for k in range(5, -1, -1):                                       # k = 0 head, 1..5 wake (older, fainter)
                th = 2 * math.pi * ph + rot * 1.6 - k * 0.12
                bx = cx + math.cos(th) * rx * rr; by = cy + math.sin(th) * ry * rr
                r = rad * (1 - 0.12 * k)
                base_a = fade * (1.0 if k == 0 else 0.55 * (1 - k / 6.0))
                col = (36, 8, 48) if purple else (4, 1, 6)
                for yy in range(int(by - r), int(by + r) + 2):
                    for xx in range(int(bx - r * 1.4), int(bx + r * 1.4) + 2):
                        if not (0 <= xx < W and 0 <= yy < H): continue
                        d2 = ((xx + 0.5 - bx) / (r * 1.4)) ** 2 + ((yy + 0.5 - by) / r) ** 2
                        if d2 > 1.0: continue
                        a = int(255 * base_a * (1 - d2) ** 0.9)
                        pr, pg, pb, pa = px[xx, yy]
                        if a > pa: px[xx, yy] = col + (a,)
        frames.append(im)
    return frames


def trail_frames():
    """Hellfire trail (slot 1): the hail strike renderer draws the slot-1 sequence at the ~9 previous path points,
    frame 0 nearest the projectile, so these 10 additive frames go from a big bright yellow-white flame puff to a
    small dark-red ember - a tail that thins and cools with distance, ~90 px long at 10 px per path step."""
    frames = []
    for i in range(10):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        t = i / 9.0
        r = 5.5 * (1 - t) + 2.0                                              # v8: 5.5 px -> 2 px so the stone stays visible
        # the soft dark-orange look of the game's own fire bolt (BOLTS 70-77): no white/yellow core
        head = 0.55 + 0.45 * min(1.0, t * 3)                                 # the two frames nearest the stone are dimmer
        col_out = (int((150 - 90 * t) * head), int((30 - 22 * t) * head), 4)
        col_mid = (int((215 - 70 * t) * head), int((95 - 60 * t) * head), int(14 - 8 * t))
        col_in = (int((245 - 60 * t) * head), int((150 - 80 * t) * head), int(40 - 25 * t))
        for rr, col in ((r, col_out), (r * 0.7, col_mid), (r * 0.4, col_in)):
            pts = []
            for k in range(20):
                a = 2 * math.pi * k / 20; wob = 1 + 0.15 * math.sin(k * 2.3 + i)
                pts.append((32 + math.cos(a) * rr * wob, 33 + math.sin(a) * rr * wob * (0.9 + 0.2 * t)))
            dr.polygon(pts, fill=col + (255,))
        frames.append(im.filter(ImageFilter.GaussianBlur(1.4 + 0.5 * t)))
    return frames


# ------------------------------------------------------------------ Repent (Life T2, 2026-10-12): beam from the sky
# Spell 206 is a hail-class strike (patch_tc_repent_harvest_v1.py: 1 strike, vertical path from 300 px above the
# target hex, no scatter).  Slot 0 = the path head: a 64x128 shaft of holy light whose bright tip sits at the anchor
# (ys = -112) and which fades upward - as the head descends the shaft above it IS the beam.  Slot 1 = trail: soft
# glow at the previous path points (fattens the column).  Slot 2 = impact: a flash, a ground ring and the last of the
# pillar dissolving (96x104, ys = -52).
def _gold(inten):
    v = min(1.0, inten)
    return (int(255 * min(1.0, v * 1.05)), int(250 * v), int(165 * v ** 0.8), int(255 * min(1.0, v * 1.6)))


def beam_head():
    frames = []
    for i in range(6):
        im = Image.new("RGBA", (64, 128), (0, 0, 0, 0)); px = im.load(); ph = 2 * math.pi * i / 6
        for y in range(128):
            v = min(1.0, y / 112.0)
            fade = 0.18 + 0.82 * v ** 1.5
            if y > 112: fade *= max(0.0, 1 - (y - 112) / 12.0)
            shimmer = 1 + 0.10 * math.sin(y * 0.22 + ph)
            for x in range(64):
                d = abs(x - 31.5)
                inten = (math.exp(-(d / 4.6) ** 2) * 1.0 + math.exp(-(d / 12.0) ** 2) * 0.42) * fade * shimmer
                if inten > 0.03: px[x, y] = _gold(inten)
        frames.append(im)
    return frames


def beam_trail():
    frames = []
    for i in range(10):
        t = i / 9.0
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); px = im.load()
        rx, ry, amp = 13.0 - 5.0 * t, 16.0, 0.50 * (1 - t) + 0.10
        for y in range(64):
            for x in range(64):
                d = math.hypot((x - 31.5) / rx, (y - 31.5) / ry)
                inten = amp * math.exp(-(d * 1.4) ** 2)
                if inten > 0.03: px[x, y] = _gold(inten)
        frames.append(im)
    return frames


def beam_impact():
    frames = []
    for i in range(10):
        t = i / 9.0
        im = Image.new("RGBA", (96, 104), (0, 0, 0, 0)); px = im.load(); cx, cy = 47.5, 52.0
        R = 8 + 36 * t; ring_w = 5.0 + 3.0 * t; ring_a = (1 - t) ** 1.1
        burst_r = 16.0 * (1 - t) + 3.0; burst_a = (1 - t) ** 0.8
        pil_w = 9.0 * (1 - t) + 1.5; pil_a = (1 - t) ** 1.4
        for y in range(104):
            for x in range(96):
                dx, dy = x - cx, y - cy
                e = math.hypot(dx, dy / 0.5)                                       # ground ellipse distance
                inten = ring_a * 0.9 * math.exp(-((e - R) / ring_w) ** 2)
                inten += burst_a * math.exp(-(math.hypot(dx, dy * 1.3) / burst_r) ** 2)
                if y <= cy:
                    rise = 1 - (cy - y) / 52.0
                    inten += pil_a * (0.25 + 0.75 * rise) * math.exp(-(dx / pil_w) ** 2)
                if inten > 0.03: px[x, y] = _gold(inten)
        frames.append(im)
    return frames


# ------------------------------------------------------------------ Harvest Souls (Death T2, 2026-10-12): soul wisps
# The Animate Dead corpse effect (0x31008) spawns 18 kind-0x1F sparkles of the spell's slot 0 around each corpse;
# Harvest's sprite is a pale sickly-green ghost flame with a wavering tail (24x28, anchor -12/-14) instead of Animate
# Dead's white twinkle, so the swirl reads as souls leaving the body.
def souls():
    frames = []
    for i in range(4):
        im = Image.new("RGBA", (24, 28), (0, 0, 0, 0)); px = im.load(); ph = 2 * math.pi * i / 4
        hr = 5.6 + 0.6 * math.sin(ph)
        for y in range(28):
            for x in range(24):
                # head: ellipse around (12, 10); tail: a thinning column swaying below it
                hd = math.hypot((x - 12) / hr, (y - 10) / (hr * 1.05))
                inten = math.exp(-(hd * 1.5) ** 2)
                if y > 10:
                    v = (y - 10) / 17.0
                    sway = 2.2 * math.sin(v * 3.2 + ph) * v
                    tw = hr * 0.75 * (1 - v) + 0.6
                    inten = max(inten, (1 - v) ** 1.2 * math.exp(-((x - 12 - sway) / tw) ** 2) * 0.9)
                if inten > 0.04:
                    v = min(1.0, inten)
                    px[x, y] = (int(120 * v + 110 * v ** 3), int(255 * v), int(150 * v + 70 * v ** 3), int(255 * min(1.0, v * 1.5)))
        frames.append(im)
    return frames


# ------------------------------------------------------------------ Repent v3 (2026-10-12 evening): static UFO beam
# patch_tc_repent_harvest_v1.py spawns a kind-0x26 driver effect at the target hex (frame top-left at hex centre
# -40/-280) that plays spell slot 1 = beam_frames() at 3 ticks per frame (f18 = 2): N_SPARK frames of slow holy
# sparkles round the unit (additive), then the beam - a semi-transparent (258 alpha) column from the top of the
# 80x300 frame down to a pool at the unit's feet (y 280) - growing from narrow to BEAM_WMAX over N_GROW frames,
# holding N_HOLD frames (the strike lands at the start of the hold: slot 2 flash + sound 1), then fading N_FADE
# frames.  Slot 0 (the strike's falling head) is a transparent 1x1 sprite; the trail is skipped by the "show" hook.
BEAM_W, BEAM_H, BEAM_FOOT, BEAM_WMAX = 80, 300, 280, 46
N_SPARK, N_GROW, N_HOLD, N_FADE = 14, 14, 3, 8          # v5: 39 frames; the strike lands at frame N_SPARK+N_GROW (full width)


def _gold_rgba(inten, core):
    """Additive white-gold: white where `core` is high, gold at the edges; alpha carries the dither threshold."""
    i = np.clip(inten, 0, 1)
    r = 255 * i; g = (252 - 34 * (1 - core)) * i; b = (232 - 120 * (1 - core)) * i
    a = np.where(i > 0.025, 255, 0)
    return np.dstack([r, g, b, a]).astype(np.uint8)


def _star_layer(stars, i, life=10):
    """Soft 4-point stars with a glow halo (numpy field): each star = (x, y, birth frame, size, drift)."""
    yy, xx = np.mgrid[0:BEAM_H, 0:BEAM_W].astype(np.float32)
    f = np.zeros((BEAM_H, BEAM_W), np.float32); core = np.zeros_like(f)
    for x, y, born, sz, drift in stars:
        age = i - born
        if age < 0 or age > life: continue
        a = math.sin(math.pi * age / life) ** 0.8; y = y - drift * age; r = sz * (0.55 + 0.45 * a)
        dx, dy = xx - x, yy - y
        # a 4-point star: product of two thin gaussians along the axes, plus a soft round halo and a hot core
        arm = np.exp(-(dx / (r * 2.4)) ** 2 - (dy / (r * 0.38)) ** 2) + np.exp(-(dx / (r * 0.38)) ** 2 - (dy / (r * 2.9)) ** 2)
        halo = np.exp(-(dx * dx + dy * dy) / (r * r * 2.2)) * 0.55
        hot = np.exp(-(dx * dx + dy * dy) / (r * r * 0.22))
        f += a * (0.9 * arm + halo + 0.9 * hot); core += a * hot
    return f, np.clip(core, 0, 1)


def beam_frames():
    frames = []
    rnd = random.Random(2061)
    # v5: "much more subtle and small" - tiny faint motes, few at a time, no anticipation shaft
    # v7: TIGHT round the unit, born over the first frames and then PERSISTING (twinkling, slowly falling) through the
    # whole sparkle phase; they only fade out while the beam widens (see the grow frames below)
    stars = [(rnd.uniform(27, 53), rnd.uniform(224, 272), rnd.uniform(-2, 6), rnd.uniform(0.8, 1.4), rnd.uniform(-0.55, -0.2), rnd.uniform(0, 6.28)) for _ in range(16)]
    yy, xx = np.mgrid[0:BEAM_H, 0:BEAM_W].astype(np.float32)
    dxc = xx - 39.5
    def motes(i, fade):
        f = np.zeros((BEAM_H, BEAM_W), np.float32); core = np.zeros_like(f)
        for x, y, born, sz, drift, ph in stars:
            age = i - born
            if age < 0: continue
            a = min(1.0, age / 3.0) * (0.55 + 0.45 * math.sin(age * 1.1 + ph)) * fade      # ramp in, twinkle, global fade
            y = y - drift * age; r = sz
            dx, dy = xx - x, yy - y
            arm = np.exp(-(dx / (r * 2.4)) ** 2 - (dy / (r * 0.38)) ** 2) + np.exp(-(dx / (r * 0.38)) ** 2 - (dy / (r * 2.9)) ** 2)
            hot = np.exp(-(dx * dx + dy * dy) / (r * r * 0.22))
            f += a * (0.9 * arm + 0.45 * np.exp(-(dx * dx + dy * dy) / (r * r * 2.2)) + 0.9 * hot); core += a * hot
        return f * 0.75, np.clip(core * 0.8, 0, 1)
    # v8 (2026-10-13): a small glowing yellow cross hovers above the unit during the sparkle phase (fades in over the
    # first frames, floats gently) and fades away as the beam begins
    def cross_layer(k, fade):
        cx, cy = 39.5, 226.0 + 1.5 * math.sin(k * 0.45)                     # v9: lower - just above where the Turn Undead status cross sits
        dv = np.hypot(np.maximum(np.abs(xx - cx) - 1.2, 0), np.maximum(np.abs(yy - cy) - 8.5, 0))          # upright bar 2.4 x 17
        dh = np.hypot(np.maximum(np.abs(xx - cx) - 5.5, 0), np.maximum(np.abs(yy - (cy - 3.2)) - 1.2, 0))  # crossbar 11 x 2.4
        dm = np.minimum(dv, dh)
        return (np.exp(-(dm / 0.8) ** 2) + 0.55 * np.exp(-(dm / 3.0) ** 2) + 0.15 * np.exp(-(dm / 7.0) ** 2)) * fade * 0.95
    for i in range(N_SPARK):
        f, core = motes(i, 1.0)
        f = f + cross_layer(i, min(1.0, max(0.0, (i - 1) / 4.0)) * (1 + 0.07 * math.sin(i * 1.3)))
        frames.append(Image.fromarray(_gold_rgba(f, core), "RGBA"))
    for i in range(N_GROW + N_HOLD + N_FADE):                                  # the beam (additive, ~half strength)
        if i < N_GROW:
            # v5: starts as a thread of light, then brightens and widens (ease-in, most of the growth late)
            t = (i + 1) / N_GROW; w = 2.5 + (BEAM_WMAX - 2.5) * (t ** 1.8); bright = 0.3 + 0.7 * (t ** 1.3)
        elif i < N_GROW + N_HOLD:
            k = i - N_GROW; w = BEAM_WMAX + 1.5 * math.sin(k * 1.3); bright = 1.0
        else:
            t = (i - N_GROW - N_HOLD + 1) / N_FADE; w = BEAM_WMAX * (1 - 0.35 * t); bright = (1 - t) ** 1.4
        hw = w / 2; d = np.abs(dxc) / hw
        core = np.exp(-(d / 0.42) ** 2)
        body = np.exp(-(d / 0.95) ** 4) * 0.55 + core * 0.5 + np.exp(-(d / 1.45) ** 2) * 0.16
        # vertical light rays: brighter lines drifting slowly across the column, plus a slow shimmer along it
        rays = 1 + 0.22 * np.sin(xx * 0.95 + i * 0.6) * np.sin(xx * 0.37 - i * 0.25) + 0.12 * np.sin(xx * 2.1 + i * 0.9)
        shimmer = 1 + 0.07 * np.sin(yy * 0.11 + i * 0.8)
        top = 1 - 0.55 * np.clip((90 - yy) / 90.0, 0, 1)                      # fades into the sky
        col = body * rays * shimmer * top
        # pool of light at the feet: a bright-rimmed ellipse, the column cut off below its centre
        ey = (yy - BEAM_FOOT) / 11.0; ex = dxc / (hw * 1.5)
        pool = np.exp(-(np.sqrt(ex * ex + ey * ey) - 0.85) ** 2 / 0.06) * 0.42 + np.exp(-(ex * ex + ey * ey) * 1.6) * 0.3
        col = np.where(yy > BEAM_FOOT, 0.0, col) + np.where(np.abs(ey) < 1.4, pool, 0.0)
        if i < N_GROW:                                                         # v7: the motes linger and fade as the beam widens
            mf, mc = motes(N_SPARK + i, (1 - (i + 1) / N_GROW) ** 1.4)
            col = col * bright * 0.6 + mf + cross_layer(N_SPARK + i, max(0.0, 1 - (i + 1) / 5.0)); core = np.maximum(core, mc)
            frames.append(Image.fromarray(_gold_rgba(col, core), "RGBA")); continue
        frames.append(Image.fromarray(_gold_rgba(col * bright * 0.6, core), "RGBA"))
    return frames


def beam_flash():
    """Repent slot 2: the landing flash at the hex (64x64 additive, 6 frames) while the beam holds."""
    frames = []
    for i in range(6):
        t = i / 5.0
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); px = im.load()
        r0 = 10 + 18 * t; amp = (1 - t) ** 0.9
        for y in range(64):
            for x in range(64):
                d = math.hypot(x - 31.5, (y - 40) * 1.6) / r0
                inten = amp * math.exp(-(d * 1.3) ** 2)
                if inten > 0.03: px[x, y] = _gold(inten)
        frames.append(im)
    return frames


def blank():
    return [Image.new("RGBA", (4, 4), (0, 0, 0, 0))]


def purple_sparkles():
    """Harvest Souls slot 0 (v3, 2026-10-12): Animate Dead's own PARTICLE.ILB 15-17 twinkle, re-coloured purple.
    The originals are Picture16 records in draw mode 1026 (multiply/"dark"): a DARK star on a WHITE field, which is
    how Animate Dead's black sparkles work.  Spell 207 is not on the engine's dark-draw id list, so the copy is
    inverted (star bright, field black) and tinted violet for the additive (770) mode: same shape, motion and
    timing, glowing purple instead of black."""
    lib = ilbcodec.read(PARTICLE); out = []
    for src in (15, 16, 17):
        im, r = raw_pixels(lib, src); im = im.convert("RGBA")
        im = im.resize((im.width * 2, im.height * 2), Image.BICUBIC)           # v4: 2x (19 -> 38 px; user: "particles too small")
        p = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r_, g_, b_, a_ = p[x, y]; v = 1.0 - max(r_, g_, b_) / 255.0
                p[x, y] = (int(255 * min(1.0, 0.70 * v + 0.2 * v ** 3)), int(255 * 0.12 * v), int(255 * min(1.0, 1.0 * v)), 255)
        out.append(im)
    return out


MAGIC = os.path.join(GAME, "Images", "Effects", "Magic.ILB")
def purple_summon():
    """Harvest Souls slot 1 (v4, 2026-10-12): the vanilla summon dome (MAGIC.ILB 89-109, the green glow that rises
    and collapses when a creature is summoned) tinted purple - played at the CASTER by a kind-0x26 effect when the
    corpses pop (patch_tc_repent_harvest_v1.py), 21 frames at 2 ticks (f18 = 1)."""
    lib = ilbcodec.read(MAGIC); out = []
    for src in range(89, 110):
        im, r = raw_pixels(lib, src); im = im.convert("RGBA"); a = np.array(im).astype(np.float32)
        g = a[:, :, 1]; rr = a[:, :, 0]; b = a[:, :, 2]
        a[:, :, 0] = np.clip(0.48 * g + 0.26 * rr, 0, 255)                   # violet rather than pink
        a[:, :, 1] = np.clip(0.15 * g, 0, 255)
        a[:, :, 2] = np.clip(np.maximum(b, 1.0 * g), 0, 255)
        out.append(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


# ------------------------------------------------------------------ Life/Fire spells (2026-10-13)
def _fire_rgba(inten, heat):
    """Additive fire: deep red at the edges -> orange -> white-gold where `heat` (core fraction) is high."""
    i = np.clip(inten, 0, 1); h = np.clip(heat, 0, 1)
    r = 255 * i; g = (110 + 140 * h) * i; b = (15 + 215 * h * h) * i
    a = np.where(i > 0.025, 255, 0)
    return np.dstack([r, g, b, a]).astype(np.uint8)


def martyr_motes():
    """Martyr slot 0 (16 frames 64x64 additive, 2 ticks each): a crowd of small flame motes born low around the unit
    and rising while they flicker, plus a soft gold halo over the head that brightens and fades with them."""
    rnd = random.Random(360); frames = []
    motes = [(rnd.uniform(14, 50), rnd.uniform(36, 60), rnd.uniform(0, 5), rnd.uniform(1.0, 1.9), rnd.uniform(1.3, 2.5), rnd.uniform(0, 6.28)) for _ in range(24)]
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    for i in range(16):
        f = np.zeros((64, 64), np.float32); heat = np.zeros_like(f)
        glob = math.sin(math.pi * i / 15) ** 0.7
        for x, y0, born, sz, speed, ph in motes:
            age = i - born
            if age < 0: continue
            y = y0 - speed * age; a = min(1.0, age / 2.0) * (0.6 + 0.4 * math.sin(age * 1.3 + ph)) * glob
            x2 = x + 1.5 * math.sin(age * 0.8 + ph)
            d2 = (xx - x2) ** 2 + (yy - y) ** 2
            core = np.exp(-d2 / (sz * sz * 0.5)); halo = np.exp(-d2 / (sz * sz * 3.0)) * 0.45
            f += a * (core + halo); heat += a * core
        ring = np.exp(-((np.hypot(xx - 31.5, (yy - 12.0) * 2.2) - 9.0) ** 2) / 6.0) * glob * 0.8
        f += ring; heat += ring * 0.9
        frames.append(Image.fromarray(_fire_rgba(f, heat / np.maximum(f, 1e-3)), "RGBA"))
    return frames


def cleanse_burst():
    """Cleansing Flame slot 0 (16 frames 64x72 additive): a white-gold flash at the unit's chest, a ring of fire
    racing out over the ground and flame tongues licking up round the unit, all dying away by the last frame."""
    frames = []; rnd = random.Random(361)
    yy, xx = np.mgrid[0:72, 0:64].astype(np.float32)
    tongues = [(rnd.uniform(14, 50), rnd.uniform(0.9, 1.7), rnd.uniform(0, 6.28)) for _ in range(9)]
    for i in range(16):
        t = i / 15.0; f = np.zeros((72, 64), np.float32); heat = np.zeros_like(f); cx, cy = 31.5, 58.0
        R = 4 + 26 * t
        ring = (1 - t) ** 1.2 * np.exp(-((np.hypot(xx - cx, (yy - cy) * 2.0) - R) ** 2) / (2 * (3 + 3 * t) ** 2))
        f += 0.9 * ring; heat += 0.5 * ring
        fl = (1 - t) ** 2.2 * np.exp(-((xx - cx) ** 2 + ((yy - 36) * 1.1) ** 2) / (2 * (3.5 + 7 * t) ** 2))   # smaller flash (v1 preview: a moon)
        f += 0.7 * fl; heat += 0.7 * fl
        h = 10 + 30 * math.sin(math.pi * min(1.0, t * 1.3)); a = (1 - t) ** 0.8; top = cy - h
        vert = np.clip((yy - top) / max(1.0, cy - top), 0, 1) * (yy <= cy + 2)
        for x, w, ph in tongues:
            col = np.exp(-((xx - x - 2 * np.sin(yy * 0.3 + ph + i * 0.6)) ** 2) / (2 * (w * (1 + (cy - yy) / 40)) ** 2))
            tongue = col * vert ** 1.5 * a
            f += tongue; heat += 0.6 * tongue * vert
        frames.append(Image.fromarray(_fire_rgba(f, heat / np.maximum(f, 1e-3)), "RGBA"))
    return frames


def phoenix_summon():
    """Summon Phoenix slot 0: the Mermaid's summon glow (MAGIC.ILB 20-31, the blue-white rising column) tinted
    gold/orange, 12 frames at 2 ticks."""
    lib = ilbcodec.read(MAGIC); out = []
    for src in range(20, 32):
        im, r = raw_pixels(lib, src); a = np.array(im.convert("RGBA")).astype(np.float32)
        lum = np.max(a[:, :, :3], axis=2)
        a[:, :, 0] = np.clip(lum * 1.05, 0, 255); a[:, :, 1] = np.clip(lum * 0.62, 0, 255); a[:, :, 2] = np.clip(lum * 0.12, 0, 255)
        out.append(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


def ed_summon():
    """Earth/Death summons (332 Dire Wolf / 334 Werewolf) slot 0: the Mermaid's summon glow (MAGIC.ILB 20-31, the
    rising column) tinted a sickly green-grey (Earth -> Death), 12 frames - the Phoenix recipe."""
    lib = ilbcodec.read(MAGIC); out = []
    for src in range(20, 32):
        im, r = raw_pixels(lib, src); a = np.array(im.convert("RGBA")).astype(np.float32)
        lum = np.max(a[:, :, :3], axis=2)
        a[:, :, 0] = np.clip(lum * 0.62, 0, 255); a[:, :, 1] = np.clip(lum * 0.86, 0, 255); a[:, :, 2] = np.clip(lum * 0.48, 0, 255)
        out.append(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


def silk_tuft(n=6):
    """Thousand Threads (335) hail slot 0 = the falling projectile: a small glowing tuft of silk - a bright knot with
    four wiggling threads streaming up behind it.  24x24 additive."""
    frames = []; yy, xx = np.mgrid[0:24, 0:24].astype(np.float32)
    for i in range(n):
        I = np.exp(-((xx - 12) ** 2 + (yy - 15) ** 2) / (2 * 1.9 ** 2)) * 1.1
        for k in range(4):
            off = (k - 1.5) * 1.6
            for m in range(14):
                t = m / 13.0; x = 12 + off * (0.4 + t) + 1.2 * math.sin(t * 7 + i * 1.3 + k); y = 15 - 13 * t
                I = np.maximum(I, np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 0.55 ** 2)) * (1 - 0.7 * t))
        v = np.clip(I, 0, 1)
        frames.append(Image.fromarray(np.dstack([235 * v, 238 * v, 245 * v, 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def silk_trail(n=10):
    """Thousand Threads (335) hail slot 1 = the trail drawn at the previous path points (frame 0 nearest the head):
    a thin wavering thread wisp fading out.  24x24 additive."""
    frames = []; yy, xx = np.mgrid[0:24, 0:24].astype(np.float32)
    for i in range(n):
        t = i / (n - 1.0); I = np.zeros((24, 24), np.float32)
        for m in range(16):
            u = m / 15.0; x = 12 + 2.2 * math.sin(u * 6.3 + i); y = 2 + 20 * u
            I = np.maximum(I, np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 0.6 ** 2)))
        v = np.clip(I * (1 - t) ** 1.2 * 0.8, 0, 1)
        frames.append(Image.fromarray(np.dstack([225 * v, 228 * v, 240 * v, 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def web_burst(n=10):
    """Thousand Threads (335) hail slot 2 = the impact on the hex: a radial spider web flashing open over the hex
    (flattened to the battlefield angle) - eight radial threads and three sagging rings growing out, then fading.
    64x48 additive."""
    frames = []; W_, H_ = 64, 48
    for i in range(n):
        t = i / (n - 1.0); grow = min(1.0, (i + 1) / 4.0); a_ = 1.0 if i < 6 else 1 - (i - 5) / 4.5
        im = Image.new("L", (W_ * 4, H_ * 4), 0); dr = ImageDraw.Draw(im); cx, cy = W_ * 2, H_ * 2 + 4
        R = 28 * 4 * grow
        angs = [math.radians(k * 45 + 10) for k in range(8)]
        for a in angs:
            dr.line([(cx, cy), (cx + R * math.cos(a), cy + R * 0.55 * math.sin(a))], fill=255, width=4)
        for ring in (0.35, 0.65, 0.95):
            r = R * ring
            for k in range(8):
                a0, a1 = angs[k], angs[(k + 1) % 8] + (2 * math.pi if k == 7 else 0)
                p0 = (cx + r * math.cos(a0), cy + r * 0.55 * math.sin(a0)); p1 = (cx + r * math.cos(a1), cy + r * 0.55 * math.sin(a1))
                mid = ((p0[0] + p1[0]) / 2 * 0.92 + cx * 0.08, (p0[1] + p1[1]) / 2 * 0.92 + cy * 0.08)
                pts = [((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * mid[0] + u * u * p1[0], (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * mid[1] + u * u * p1[1]) for u in [m / 6.0 for m in range(7)]]
                dr.line(pts, fill=255, width=3)
        v = np.array(im.resize((W_, H_), Image.LANCZOS)).astype(np.float32) / 255.0 * a_
        yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32)
        flash = np.exp(-((xx - W_ / 2) ** 2 + ((yy - H_ / 2 - 1) * 1.8) ** 2) / (2 * 6.0 ** 2)) * max(0.0, 1 - i / 3.0)
        v = np.clip(np.maximum(v * 1.3, flash), 0, 1)
        frames.append(Image.fromarray(np.dstack([235 * v, 238 * v, 248 * v, 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def _rot_rgba(v, w):
    """Rot colouring: sickly green-brown body (v), a paler bile-green highlight (w); additive."""
    v = np.clip(v, 0, 1); w = np.clip(w, 0, 1)
    rgb = np.dstack([120 * v + 90 * w, 150 * v + 95 * w, 40 * v + 30 * w])
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (np.maximum(v, w) > 0.04)]).astype(np.uint8), "RGBA")


def rot_glob(n=6):
    """Rot Away (333) hail slot 0 = the falling projectile: a wobbling glob of rot (green-brown, a bile-green core) with
    two drips hanging off it.  24x24 additive."""
    frames = []; yy, xx = np.mgrid[0:24, 0:24].astype(np.float32)
    for i in range(n):
        wob = 0.8 * math.sin(i * 1.1)
        body = np.exp(-(((xx - 12) / (4.2 + wob * 0.3)) ** 2 + ((yy - 13) / (3.8 - wob * 0.3)) ** 2))
        drips = sum(np.exp(-((xx - x) ** 2) / 1.0 - ((yy - (17 + 2.5 * k + 0.6 * (i % 3))) ** 2) / 3.0) * 0.7 for k, x in ((0, 10.4), (1, 13.6)))
        core = np.exp(-(((xx - 11) / 2.0) ** 2 + ((yy - 12) / 1.7) ** 2))
        frames.append(_rot_rgba(np.maximum(body * 1.1, drips), core * 0.8))
    return frames


def rot_trail(n=10):
    """Rot Away (333) hail slot 1 = the trail (frame 0 nearest the head): dripping slime motes and spores, fading."""
    frames = []; yy, xx = np.mgrid[0:24, 0:24].astype(np.float32); rnd = random.Random(333)
    for i in range(n):
        t = i / (n - 1.0); v = np.zeros((24, 24), np.float32)
        for k in range(4):
            x = 12 + rnd.uniform(-4, 4) * (0.4 + t); y = 12 + rnd.uniform(-4, 4); r = rnd.uniform(0.9, 1.6) * (1 - 0.5 * t)
            v = np.maximum(v, np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r)))
        frames.append(_rot_rgba(v * (1 - t) ** 1.2 * 0.9, v * 0.2 * (1 - t)))
    return frames


def rot_burst(n=12):
    """Rot Away (333) hail slot 2 = the impact on the hex: a rot splatter - a green-brown splash flattened on the
    hex with slime drops flung out, then a cloud of spores drifting up and fading.  48x48 additive."""
    frames = []; yy, xx = np.mgrid[0:48, 0:48].astype(np.float32); rnd = random.Random(3331)
    drops = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(9, 18), rnd.uniform(1.0, 1.8)) for _ in range(9)]
    spores = [(rnd.uniform(14, 34), rnd.uniform(26, 36), rnd.uniform(0.7, 1.3), rnd.uniform(0, 1)) for _ in range(14)]
    for i in range(n):
        t = i / (n - 1.0); grow = min(1.0, (i + 1) / 3.0); fade = 1.0 if i < 5 else 1 - (i - 4) / 8.0
        splash = np.exp(-(((xx - 24) / (6 + 8 * grow)) ** 2 + ((yy - 34) / (2.6 + 3.4 * grow)) ** 2)) * fade
        v = splash.copy()
        for a, d, r in drops:
            x = 24 + d * grow * math.cos(a); y = 34 + d * grow * 0.5 * math.sin(a) - 6 * grow * (1 - grow)
            v = np.maximum(v, np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r)) * fade)
        w = np.zeros_like(v)
        for x, y0, r, ph in spores:
            if t < 0.25: continue
            y = y0 - 22 * (t - 0.25) * (0.8 + 0.4 * ph); x2 = x + 3 * math.sin(t * 6 + ph * 6)
            w = np.maximum(w, np.exp(-((xx - x2) ** 2 + (yy - y) ** 2) / (2 * r * r)) * (1 - t) * 1.1)
        frames.append(_rot_rgba(v * 1.1, w))
    return frames


def rot_boil_seq():
    """Rot Away (333) v2 slot 2 (user: make the gfx similar to Blood Boil but GREEN bubbles): Blood Boil's 16-frame
    boil (bubbles swelling, rising and popping + steam from Vaporize's SMOKE) recoloured a sickly green, played as the
    hail impact on every hex of the area (nothing visibly falls: slots 0/1 blank)."""
    out = []
    for f in bloodboil_seq():
        a = np.array(f).astype(np.float32); r, g, b, al = a[:, :, 0], a[:, :, 1], a[:, :, 2], a[:, :, 3]
        nr = np.clip(g * 0.85 + r * 0.22, 0, 255); ng = np.clip(r * 0.95 + g * 0.1, 0, 255); nb = np.clip(b * 0.45, 0, 255)
        out.append(Image.fromarray(np.dstack([nr, ng, nb, al]).astype(np.uint8), "RGBA"))
    return out


def silk_spin(n=14):
    """Thousand Threads (335) v3 slot 2 (user: v2 too cartoony/bright - more realistic / gritty): a whirl of FINE silk
    round each hex - a dozen thin, uneven, slightly jittering strands on flattened orbits spinning fast (each a broken
    run of fibres, dull off-white/grey, varying in brightness), loose fibres trailing and dust motes caught in the
    whirl; dim (about half v2's brightness).  96x64 additive."""
    frames = []; CW, CH = 96, 64; rnd = random.Random(3356)
    strands = [(rnd.uniform(10, 42), rnd.uniform(0, 2 * math.pi), rnd.uniform(0.6, 1.0), rnd.choice((1, 1, 1, -1)), rnd.uniform(70, 160)) for _ in range(12)]
    dust = [(rnd.uniform(8, 40), rnd.uniform(0, 2 * math.pi), rnd.uniform(0.5, 1.0)) for _ in range(22)]
    for i in range(n):
        a_ = min(1.0, (i + 1) / 2.0) * (1.0 if i < n - 4 else (n - i) / 4.0)
        im = Image.new("L", (CW * 4, CH * 4), 0); dr = ImageDraw.Draw(im); cx, cy = CW * 2, CH * 2 + 8
        rr = random.Random(i * 31 + 7)
        for r, ph, br, sd, sweep in strands:
            a0 = ph + sd * i * math.radians(52); m = 18
            pts = []
            for k in range(m + 1):
                t = k / m; a = a0 + sd * math.radians(sweep) * t; rj = r + rr.uniform(-0.7, 0.7)
                pts.append((cx + rj * 4 * math.cos(a), cy + rj * 4 * 0.45 * math.sin(a) + rr.uniform(-1.5, 1.5)))
            for k in range(m):
                if rr.random() < 0.18: continue                                                            # broken fibre
                dr.line([pts[k], pts[k + 1]], fill=int(255 * br * (0.3 + 0.7 * k / (m - 1))), width=rr.choice((1, 2, 2, 3)))
        for r, ph, br in dust:                                                                              # dust motes in the whirl
            a = ph + i * math.radians(40); x = cx + r * 4 * math.cos(a); y = cy + r * 4 * 0.45 * math.sin(a)
            dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=int(200 * br))
        v = np.array(im.resize((CW, CH), Image.LANCZOS)).astype(np.float32) / 255.0 * a_ * 1.3
        v = np.clip(v, 0, 1)
        frames.append(Image.fromarray(np.dstack([200 * v, 196 * v, 182 * v, 255 * (v > 0.03)]).astype(np.uint8), "RGBA"))
    return frames


def silk_spin_v1(n=14):
    """Thousand Threads (335) v2 slot 2 (user: silk rapidly spinning around the AOE): played at every landing hex - a
    whirl of silk threads spinning fast round the hex: five glowing thread arcs on flattened orbits (y 0.45) of
    different radii, each sweeping ~130 deg and turning ~55 deg per frame, with a few loose strands flicking out;
    fades in over 2 frames and out over the last 4.  96x64 additive."""
    frames = []; CW, CH = 96, 64; rnd = random.Random(3355)
    arcs = [(rnd.uniform(14, 42), rnd.uniform(0, 2 * math.pi), rnd.uniform(1.6, 2.4), rnd.choice((1, 1, -1))) for _ in range(5)]
    for i in range(n):
        a_ = min(1.0, (i + 1) / 2.0) * (1.0 if i < n - 4 else (n - i) / 4.0)
        im = Image.new("L", (CW * 4, CH * 4), 0); dr = ImageDraw.Draw(im); cx, cy = CW * 2, CH * 2 + 8
        for r, ph, w, sd in arcs:
            a0 = ph + sd * i * math.radians(55)
            pts = [(cx + r * 4 * math.cos(a0 + sd * math.radians(130) * t), cy + r * 4 * 0.45 * math.sin(a0 + sd * math.radians(130) * t)) for t in [k / 20.0 for k in range(21)]]
            for k in range(20):
                dr.line([pts[k], pts[k + 1]], fill=int(255 * (0.35 + 0.65 * k / 19.0)), width=max(2, int(w * 4 * (0.4 + 0.6 * k / 19.0))))
        for k in range(4):                                                                                 # loose strands flicking out
            a = rnd.uniform(0, 2 * math.pi); r0 = rnd.uniform(10, 30); r1 = r0 + rnd.uniform(6, 12)
            dr.line([(cx + r0 * 4 * math.cos(a), cy + r0 * 1.8 * math.sin(a)), (cx + r1 * 4 * math.cos(a + 0.3), cy + r1 * 1.8 * math.sin(a + 0.3))], fill=150, width=3)
        v = np.array(im.resize((CW, CH), Image.LANCZOS)).astype(np.float32) / 255.0 * a_ * 1.25
        v = np.clip(v, 0, 1)
        frames.append(Image.fromarray(np.dstack([235 * v, 238 * v, 248 * v, 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def rot_status():
    """Rot (ability 0xB5) combat status overlay (user: a dark green variant of the Cursed gfx): Cursed's SEffect.ILB
    50-65 (16 frames, 64x64, drawn as a darkening MULTIPLY, drawMode 1026) tinted toward green - light greys become a
    sickly green haze, the dark core a deep rot green.  Played via Ability.pfs record 191 tag 8 (xs -31 / ys -35)."""
    lib = ilbcodec.read(open(os.path.join(GAME, "Images", "TCombat", "Objects", "SEffect.ILB"), "rb").read()); out = []
    for k in range(50, 66):
        im, r = raw_pixels(lib, k); a = np.array(im.convert("RGBA")).astype(np.float32)
        v = 255 - (255 - a[:, :, :3].mean(2)) * 0.5                                                  # v2 (user: too apparent): half the darkening
        a[:, :, 0] = np.clip(v * 0.80, 0, 255); a[:, :, 1] = np.clip(v * 0.97, 0, 255); a[:, :, 2] = np.clip(v * 0.76, 0, 255)
        out.append(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


def gold_motes():
    """Golden Age (302) slot 0: the map-wide particle of Earth Mastery's world effect (drawn by the TWorldFXHS
    particles, Drought's pattern) - a bright GOLD twinkle: a hot white-gold core with four thin rays, 3 frames
    (bright / brighter / soft).  20x20 additive."""
    frames = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32)
    for k, (g, rl) in enumerate(((0.8, 5.0), (1.1, 7.0), (0.6, 4.0))):
        d2 = (xx - 9.5) ** 2 + (yy - 9.5) ** 2
        core = np.exp(-d2 / (2 * 1.6 ** 2)) * g
        rays = (np.exp(-((yy - 9.5) ** 2) / 0.5 - ((xx - 9.5) ** 2) / (2 * rl ** 2)) + np.exp(-((xx - 9.5) ** 2) / 0.5 - ((yy - 9.5) ** 2) / (2 * rl ** 2))) * 0.6 * g
        halo = np.exp(-d2 / (2 * 3.5 ** 2)) * 0.35 * g
        v = np.clip(np.maximum(np.maximum(core, rays), halo), 0, 1); w = np.clip(core * 1.2 - 0.3, 0, 1)
        rgb = np.dstack([255 * v, (175 + 70 * w) * v, (40 + 190 * w) * v])
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def spirit_rise(n=16):
    """Awaken Spirit (300) per-unit aura: pale green-gold spirit wisps spiralling up round the unit - four soft comets
    with bright cores circling and rising, a faint glow at the feet.  48x64 additive."""
    frames = []; yy, xx = np.mgrid[0:64, 0:48].astype(np.float32)
    for i in range(n):
        t = i / (n - 1.0); a_ = min(1.0, (i + 1) / 3.0) * (1.0 if i < n - 4 else (n - i) / 4.0); I = np.zeros((64, 48), np.float32); C = np.zeros_like(I)
        for k in range(4):
            for g in range(6):                                                                             # comet: head + 5 ghosts
                tt = t - g * 0.025; ph = k * math.pi / 2 + tt * 2 * math.pi * 1.4
                x = 24 + 13 * math.cos(ph); y = 56 - 44 * tt - 3 * math.sin(ph)
                r = 2.6 - 0.3 * g; f = (1.0 - g * 0.17)
                blob = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r)) * f
                I = np.maximum(I, blob); C = np.maximum(C, blob if g == 0 else 0 * blob)
        I = np.maximum(I, np.exp(-(((xx - 24) / 12.0) ** 2 + ((yy - 58) / 3.0) ** 2)) * 0.5 * (1 - t))
        v = np.clip(I * a_, 0, 1); w = np.clip(C * a_ * 1.2 - 0.3, 0, 1)
        rgb = np.dstack([(170 + 85 * w) * v, (235 + 20 * w) * v, (120 + 135 * w) * v])
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def leaf_fall(n=16):
    """Blessing of the Forest (301) per-unit aura: green oak leaves drifting and spinning down round the unit, with a
    faint golden-green shimmer that settles on it.  48x64 additive."""
    frames = []; rnd = random.Random(301); yy, xx = np.mgrid[0:64, 0:48].astype(np.float32)
    leaves = [(rnd.uniform(6, 42), rnd.uniform(-4, 30), rnd.uniform(0, 2 * math.pi), rnd.uniform(0.8, 1.2)) for _ in range(9)]
    for i in range(n):
        t = i / (n - 1.0); a_ = min(1.0, (i + 1) / 3.0) * (1.0 if i < n - 4 else (n - i) / 4.0)
        im = Image.new("L", (48 * 4, 64 * 4), 0); dr = ImageDraw.Draw(im)
        for x0, y0, ph, sz in leaves:
            x = x0 + 4 * math.sin(t * 6 + ph); y = y0 + 34 * t; ang = ph + t * 7
            if not (-4 < y < 66): continue
            ca, sa = math.cos(ang), math.sin(ang); L = 5.5 * sz; pts = []
            for k in range(13):
                u = k / 12.0; w = 2.2 * sz * math.sin(math.pi * u) * (0.6 + 0.4 * abs(math.cos(t * 9 + ph)))   # flutter = the leaf turning
                pts.append(((x + ca * (u - 0.5) * L - sa * w) * 4, (y + sa * (u - 0.5) * L + ca * w) * 4))
            for k in range(12, -1, -1):
                u = k / 12.0; w = 2.2 * sz * math.sin(math.pi * u) * (0.6 + 0.4 * abs(math.cos(t * 9 + ph)))
                pts.append(((x + ca * (u - 0.5) * L + sa * w) * 4, (y + sa * (u - 0.5) * L - ca * w) * 4))
            dr.polygon(pts, fill=230)
        v = np.array(im.resize((48, 64), Image.LANCZOS)).astype(np.float32) / 255.0
        sh = np.exp(-(((xx - 24) / 14.0) ** 2 + ((yy - 40) / 16.0) ** 2)) * 0.35 * math.sin(math.pi * t)
        v = np.clip(np.maximum(v, sh) * a_, 0, 1)
        rgb = np.dstack([(70 + 120 * sh) * v / np.maximum(v, 1e-3) * v, 200 * v, (60 + 40 * sh) * v])
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def spirit_mote():
    """Awaken Spirit (300) slot 0: High Prayer's rising per-unit particle - a small pale green-gold spirit wisp with a
    bright core and a short tail.  16x16 additive, 4 frames (a gentle pulse)."""
    frames = []; yy, xx = np.mgrid[0:16, 0:16].astype(np.float32)
    for k, g in enumerate((0.8, 1.0, 0.9, 0.7)):
        core = np.exp(-((xx - 7.5) ** 2 + (yy - 6.5) ** 2) / (2 * 1.3 ** 2)) * g
        tail = np.exp(-((xx - 7.5) ** 2) / 1.2 - ((yy - 10.5) ** 2) / 8.0) * 0.5 * g
        v = np.clip(np.maximum(core, tail), 0, 1); w = np.clip(core * 1.3 - 0.4, 0, 1)
        rgb = np.dstack([(170 + 85 * w) * v, (235 + 20 * w) * v, (120 + 135 * w) * v])
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def leaf_mote():
    """Blessing of the Forest (301) slot 0: a small green leaf tumbling as it rises, 4 frames.  16x16 additive."""
    frames = []
    for k in range(4):
        im = Image.new("L", (64, 64), 0); dr = ImageDraw.Draw(im); ang = k * math.pi / 4; ca, sa = math.cos(ang), math.sin(ang); pts = []
        for m in range(11):
            u = m / 10.0; w = 9 * math.sin(math.pi * u) * (0.5 + 0.5 * abs(math.cos(k * 0.9)))
            pts.append((32 + ca * (u - 0.5) * 40 - sa * w, 32 + sa * (u - 0.5) * 40 + ca * w))
        for m in range(10, -1, -1):
            u = m / 10.0; w = 9 * math.sin(math.pi * u) * (0.5 + 0.5 * abs(math.cos(k * 0.9)))
            pts.append((32 + ca * (u - 0.5) * 40 + sa * w, 32 + sa * (u - 0.5) * 40 - ca * w))
        dr.polygon(pts, fill=220)
        v = np.array(im.resize((16, 16), Image.LANCZOS)).astype(np.float32) / 255.0
        frames.append(Image.fromarray(np.dstack([70 * v, 200 * v, 60 * v, 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def starfire_head():
    """Holy Starfire slot 0 (8 frames 64x64 additive): the falling star - a hot white core, four long gold arms
    turning slowly, a soft halo."""
    frames = []; yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    for i in range(8):
        ang = i * math.pi / 16; dx, dy = xx - 31.5, yy - 31.5
        u = dx * math.cos(ang) + dy * math.sin(ang); v = -dx * math.sin(ang) + dy * math.cos(ang); r = 7.0
        arm = np.exp(-(u / (r * 2.6)) ** 2 - (v / (r * 0.3)) ** 2) + np.exp(-(u / (r * 0.3)) ** 2 - (v / (r * 2.6)) ** 2)
        halo = np.exp(-(dx * dx + dy * dy) / (r * r * 2.5)) * 0.7
        hot = np.exp(-(dx * dx + dy * dy) / (r * r * 0.35))
        frames.append(Image.fromarray(_gold_rgba(0.8 * arm + halo + 1.2 * hot, np.clip(hot * 1.5, 0, 1)), "RGBA"))
    return frames


def starfire_trail():
    """Holy Starfire slot 1 (10 frames, frame 0 nearest the head): a fading gold glow with scattered sparks."""
    frames = []; rnd = random.Random(363); yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    for i in range(10):
        t = i / 9.0
        glow = (1 - t) ** 1.3 * np.exp(-((xx - 31.5) ** 2 + (yy - 31.5) ** 2) / (2 * (5 + 4 * t) ** 2))
        f = glow.copy()
        for k in range(6):
            x = 31.5 + rnd.uniform(-8, 8) * (0.5 + t); y = 31.5 + rnd.uniform(-8, 8) * (0.5 + t); sz = rnd.uniform(0.8, 1.6)
            f += (1 - t) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sz * sz))
        frames.append(Image.fromarray(_gold_rgba(f, np.clip(glow, 0, 1)), "RGBA"))
    return frames


def starfire_impact():
    """Holy Starfire slot 2 (8 frames 64x64 additive): a white-gold flash, an expanding ring and fire sparks."""
    frames = []; yy, xx = np.mgrid[0:64, 0:64].astype(np.float32); rnd = random.Random(3631)
    for i in range(8):
        t = i / 7.0; cx, cy = 31.5, 36.0
        flash = (1 - t) ** 2 * np.exp(-((xx - cx) ** 2 + ((yy - cy) * 1.4) ** 2) / (2 * (5 + 12 * t) ** 2))
        R = 3 + 24 * t
        ring = (1 - t) ** 1.1 * np.exp(-((np.hypot(xx - cx, (yy - cy) * 1.8) - R) ** 2) / (2 * (2.5 + 2 * t) ** 2))
        f = 1.3 * flash + 0.9 * ring; heat = 1.3 * flash + 0.3 * ring
        for k in range(7):
            ang = rnd.uniform(0, 6.28); dd = (4 + 18 * t) * rnd.uniform(0.5, 1.0)
            x = cx + math.cos(ang) * dd; y = cy + math.sin(ang) * dd * 0.6 - 10 * t
            sp = (1 - t) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 2.5); f += sp; heat += 0.3 * sp
        frames.append(Image.fromarray(_fire_rgba(f, heat / np.maximum(f, 1e-3)), "RGBA"))
    return frames


def corpse_fire():
    """Ashes to Ashes slot 1 (20 frames 64x64, ALPHA 258): fire bursting up from a corpse hex with an evil twist -
    orange flames licking up from the ground, a column of black smoke and black ash particles rising and drifting,
    everything dying to embers by the last frame."""
    frames = []; rnd = random.Random(353)
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32)
    tongues = [(rnd.uniform(20, 44), rnd.uniform(1.0, 2.0), rnd.uniform(0, 6.28)) for _ in range(7)]
    motes = [(rnd.uniform(18, 46), rnd.uniform(38, 50), rnd.uniform(0, 4), rnd.uniform(1.0, 2.2), rnd.uniform(0.8, 1.8)) for _ in range(18)]
    for i in range(20):
        t = i / 19.0
        fire = np.zeros((64, 64), np.float32); heat = np.zeros_like(fire); smoke = np.zeros((64, 64), np.float32)
        h = 10 + 26 * math.sin(math.pi * min(1.0, t * 1.4)); a = (1 - t) ** 0.9; cy = 46.0; top = cy - h
        vert = np.clip((yy - top) / max(1.0, cy - top), 0, 1) * (yy <= cy + 3)
        for x, w, ph in tongues:
            col = np.exp(-((xx - x - 2.5 * np.sin(yy * 0.28 + ph + i * 0.7)) ** 2) / (2 * (w * (1 + (cy - yy) / 30)) ** 2))
            tongue = col * vert ** 1.4 * a; fire += tongue; heat += 0.7 * tongue * vert
        base = (1 - t) * np.exp(-((xx - 32) ** 2 / 2 / 11.0 ** 2 + ((yy - cy) * 1.8) ** 2 / 2 / 5.0 ** 2)); fire += base; heat += 0.5 * base
        # black smoke column rising and widening, plus ash motes
        sy = cy - 8 - 30 * t
        smoke += 0.8 * min(1.0, t * 2.0) * (1 - t) ** 0.6 * np.exp(-((xx - 32 - 3 * math.sin(i * 0.6)) ** 2) / (2 * (5 + 12 * t) ** 2) - ((yy - sy) ** 2) / (2 * (7 + 9 * t) ** 2))
        for x, y0, born, sz, sp in motes:
            age = i - born
            if age < 0: continue
            y = y0 - sp * age; x2 = x + 1.6 * math.sin(age * 0.9 + x)
            smoke += 0.9 * (1 - t) * np.exp(-((xx - x2) ** 2 + (yy - y) ** 2) / (sz * sz))
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (110 + 140 * hh) * f; b = (15 + 215 * hh * hh) * f
        # smoke darkens: blend towards black where smoke dominates
        alpha = np.clip(f + s_ * 0.85, 0, 1)
        r = r * (1 - s_) ; g = g * (1 - s_); b = b * (1 - s_)
        rgba = np.dstack([r, g, b, 255 * alpha]).astype(np.uint8)
        frames.append(Image.fromarray(rgba, "RGBA"))
    return frames


def ashes_hit():
    """Ashes to Ashes slot 0 (16 frames 96x96, ALPHA 258): the hit at the target - the ashes of the burned corpses
    arrive as a black swirl, fire erupts up the unit's body, a column of flame with black ash spiralling through it,
    then the fire dies and a dark ash cloud spreads and thins, embers dropping."""
    frames = []; rnd = random.Random(3532)
    yy, xx = np.mgrid[0:96, 0:96].astype(np.float32); cx, cy = 48.0, 50.0
    tongues = [(rnd.uniform(30, 66), rnd.uniform(2.0, 3.6), rnd.uniform(0, 6.28)) for _ in range(9)]
    ash = [(rnd.uniform(0, 6.28), rnd.uniform(10, 34), rnd.uniform(1.2, 2.6), rnd.uniform(0.25, 0.6)) for _ in range(40)]
    embers = [(rnd.uniform(24, 72), rnd.uniform(1.0, 1.6), rnd.uniform(0, 1)) for _ in range(14)]
    N = 16
    for i in range(N):
        t = i / (N - 1.0)
        fire = np.zeros((96, 96), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
        # fire column: grows fast (frames 0-5), holds, dies after frame 9
        grow = min(1.0, (i + 1) / 5.0); life = 1.0 if i <= 8 else max(0.0, 1 - (i - 8) / 6.0)
        h = 70 * grow; top = cy + 20 - h
        vert = np.clip((yy - top) / max(1.0, (cy + 20) - top), 0, 1) * (yy <= cy + 24)
        for x, w, ph in tongues:
            sway = 3.5 * np.sin(yy * 0.16 + ph + i * 0.9)
            col = np.exp(-((xx - x - sway) ** 2) / (2 * (w * (0.6 + 0.8 * (1 - vert))) ** 2))
            tongue = col * vert ** 1.2 * life; fire += tongue; heat += 0.75 * tongue * vert
        base = life * np.exp(-((xx - cx) ** 2 / 2 / 16.0 ** 2 + ((yy - (cy + 16)) * 1.6) ** 2 / 2 / 7.0 ** 2)); fire += base; heat += 0.5 * base
        # black ash swirl: particles spiralling up around the column, then drifting out as the fire dies
        spread = 1.0 + 1.6 * max(0.0, t - 0.5)
        for a0, r0, sz, spd in ash:
            ang = a0 + i * spd; r = (r0 * (0.5 + 0.5 * min(1.0, i / 6.0))) * spread
            x = cx + r * math.cos(ang); y = cy + 10 - i * 3.2 * (1 - 0.5 * t) + 0.35 * r * math.sin(ang)
            smoke += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * (1 - 0.55 * t)
        # ash cloud body: appears as the fire dies
        cloud = max(0.0, (i - 6) / 9.0)
        smoke += 0.7 * cloud * (1 - 0.6 * t) * np.exp(-((xx - cx) ** 2) / (2 * (14 + 22 * cloud) ** 2) - ((yy - (cy - 18 - 10 * cloud)) ** 2) / (2 * (16 + 10 * cloud) ** 2))
        # falling embers near the end
        if i >= 9:
            for x, sz, ph in embers:
                y = cy - 30 + (i - 9) * 7 + 20 * ph
                fire += 0.9 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); heat += 0.3 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (90 + 150 * hh) * f; b = (10 + 200 * hh * hh) * f
        alpha = np.clip(f + s_ * 0.9, 0, 1)
        r = r * (1 - s_) + 28 * s_ * (1 - f); g = g * (1 - s_) + 22 * s_ * (1 - f); b = b * (1 - s_) + 26 * s_ * (1 - f)
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def ashes_hit_v2():
    """Ashes to Ashes slot 0 v2 (22 frames 128x128, ALPHA 258/90): the EPIC hit - the ashes slam into the target as a
    black vortex, a pillar of fire erupts to the top of the frame, a ring-shaped shockwave of ash and embers bursts
    outward along the ground, embers spray up and rain down, then the pillar collapses into a towering ash cloud
    that thins out."""
    frames = []; rnd = random.Random(3533); N = 22; SZ = 128
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, cy = 64.0, 78.0      # cy = the unit's feet-ish
    tongues = [(rnd.uniform(40, 88), rnd.uniform(2.5, 5.0), rnd.uniform(0, 6.28), rnd.uniform(0.8, 1.2)) for _ in range(12)]
    ash = [(rnd.uniform(0, 6.28), rnd.uniform(14, 44), rnd.uniform(1.6, 3.4), rnd.uniform(0.2, 0.55)) for _ in range(60)]
    sparks = [(rnd.uniform(0, 6.28), rnd.uniform(1.8, 4.2), rnd.uniform(0.9, 1.6), rnd.uniform(0, 0.4)) for _ in range(40)]
    for i in range(N):
        t = i / (N - 1.0)
        fire = np.zeros((SZ, SZ), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
        # 1. impact flash + black vortex (frames 0-3): a bright white-orange core with dark arms spinning in
        if i <= 4:
            fl = (1 - i / 4.0); fire += 1.4 * fl * np.exp(-((xx - cx) ** 2 + (yy - cy + 12) ** 2) / (2 * (10 + 8 * i) ** 2)); heat += 1.2 * fl * np.exp(-((xx - cx) ** 2 + (yy - cy + 12) ** 2) / (2 * (8 + 6 * i) ** 2))
            ang = np.arctan2(yy - cy + 12, xx - cx); r = np.sqrt((xx - cx) ** 2 + (yy - cy + 12) ** 2)
            arms = 0.5 * (1 + np.sin(3 * ang + r * 0.25 - i * 1.5)) * np.exp(-((r - 22 + 4 * i) ** 2) / 90.0)
            smoke += 0.9 * arms
        # 2. pillar of fire: rises frames 1-7, holds to 11, dies 12-18
        grow = min(1.0, (i + 1) / 6.0); life = 1.0 if i <= 11 else max(0.0, 1 - (i - 11) / 7.0)
        h = 100 * grow; top = cy + 16 - h
        vert = np.clip((yy - top) / max(1.0, (cy + 16) - top), 0, 1) * (yy <= cy + 20)
        for x, w, ph, sp in tongues:
            sway = 5 * np.sin(yy * 0.12 + ph + i * sp)
            col = np.exp(-((xx - x - sway) ** 2) / (2 * (w * (0.5 + 1.0 * (1 - vert))) ** 2))
            tongue = col * vert ** 1.1 * life; fire += tongue; heat += 0.8 * tongue * vert
        core = life * np.exp(-((xx - cx) ** 2) / (2 * 9.0 ** 2)) * np.clip((yy - top) / 40.0, 0, 1) * (yy <= cy + 16) * (1 - 0.6 * (yy - top) / max(1.0, h))
        fire += 0.9 * core; heat += 0.9 * core
        base = life * np.exp(-((xx - cx) ** 2 / 2 / 24.0 ** 2 + ((yy - (cy + 12)) * 1.5) ** 2 / 2 / 9.0 ** 2)); fire += base; heat += 0.5 * base
        # 3. ground shockwave ring of ash + embers (frames 2-12): an ellipse expanding outward, fading
        if 2 <= i <= 14:
            R = 8 + (i - 2) * 6.5; ring = np.exp(-((np.sqrt(((xx - cx) ** 2) + ((yy - (cy + 8)) * 2.6) ** 2) - R) ** 2) / (2 * 4.0 ** 2)) * (1 - (i - 2) / 13.0)
            smoke += 0.9 * ring
            fire += 0.5 * ring * (1 - (i - 2) / 8.0 if i < 10 else 0.0); heat += 0.3 * ring
        # 4. embers spraying up and out, then raining down
        for a0, v, sz, ph in sparks:
            age = i - 1 - ph * 3
            if age < 0: continue
            x = cx + math.cos(a0) * v * 4.5 * age; y = cy - 6 - abs(math.sin(a0)) * v * 9 * age + 0.9 * age * age
            if 0 <= x < SZ and 0 <= y < SZ:
                g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); fire += 1.0 * g; heat += 0.5 * g
        # 5. black ash swirl round the pillar, then the towering ash cloud as the fire dies
        spread = 1.0 + 1.8 * max(0.0, t - 0.5)
        for a0, r0, sz, spd in ash:
            ang = a0 + i * spd; r = r0 * (0.4 + 0.6 * min(1.0, i / 6.0)) * spread
            x = cx + r * math.cos(ang); y = cy + 6 - i * 3.8 * (1 - 0.4 * t) + 0.3 * r * math.sin(ang)
            smoke += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * (1 - 0.5 * t)
        cloud = max(0.0, (i - 8) / 10.0)
        smoke += 0.85 * cloud * (1 - 0.55 * t) * np.exp(-((xx - cx) ** 2) / (2 * (18 + 30 * cloud) ** 2) - ((yy - (cy - 30 - 24 * cloud)) ** 2) / (2 * (22 + 16 * cloud) ** 2))
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (80 + 165 * hh) * f; b = (10 + 230 * hh * hh) * f
        alpha = np.clip(f + s_ * 0.92, 0, 1)
        r = r * (1 - s_) + 24 * s_ * (1 - f); g = g * (1 - s_) + 18 * s_ * (1 - f); b = b * (1 - s_) + 22 * s_ * (1 - f)
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def ashes_mote():
    """Ashes to Ashes slot 2 (6 frames 22x22 additive 770): a red-orange ember twinkle - a soft glowing core with a
    4-point star flare that pulses, drawn by the kind-0x1F sparkles that stream from each burning corpse to the caster
    (patch_tc_ashes_v1.py v5)."""
    frames = []; yy, xx = np.mgrid[0:22, 0:22].astype(np.float32); cx = cy = 10.5
    for i in range(6):
        p = 0.5 + 0.5 * math.sin(i / 6.0 * 2 * math.pi)
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        core = np.exp(-d2 / (2 * (2.2 + 0.8 * p) ** 2)); halo = 0.45 * np.exp(-d2 / (2 * (4.5 + 1.5 * p) ** 2))
        star = (np.exp(-((xx - cx) ** 2) / 1.2) * np.exp(-np.abs(yy - cy) / (4.5 + 3 * p)) + np.exp(-((yy - cy) ** 2) / 1.2) * np.exp(-np.abs(xx - cx) / (4.5 + 3 * p))) * (0.45 + 0.4 * p)
        f = np.clip(core + halo + star, 0, 1)
        r = 255 * f; g = (70 + 120 * core) * f; b = (10 + 60 * core * core) * f
        frames.append(Image.fromarray(np.dstack([r, g, b, np.where(f > 0.03, 255, 0)]).astype(np.uint8), "RGBA"))
    return frames


def ashes_hit_v3():
    """Ashes to Ashes slot 0 v3 (20 frames 96x96, ALPHA 258/90) - "like Vaporize but death/fire": a dark ash cloud
    boils up around the unit, lit from inside by a red-orange ember glow, with small embers and a faint sickly
    death-green tinge in the smoke, rising and thinning away like Vaporize's SMOKE cloud.  No flash, no pillar."""
    frames = []; rnd = random.Random(3534); N = 20; SZ = 96
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, cy = 48.0, 62.0
    puffs = [(rnd.uniform(-16, 16), rnd.uniform(-6, 10), rnd.uniform(7, 13), rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.3)) for _ in range(14)]
    embers = [(rnd.uniform(-18, 18), rnd.uniform(0, 1), rnd.uniform(1.0, 1.7), rnd.uniform(0.7, 1.4)) for _ in range(22)]
    for i in range(N):
        t = i / (N - 1.0)
        smoke = np.zeros((SZ, SZ), np.float32); glow = np.zeros_like(smoke); fire = np.zeros_like(smoke)
        grow = min(1.0, (i + 1) / 7.0); life = 1.0 if i <= 12 else max(0.0, 1 - (i - 12) / 7.0)
        rise = 24 * t
        for dx, dy, r, ph, sp in puffs:
            x = cx + dx * (0.4 + 0.6 * grow) + 2.5 * math.sin(ph + i * 0.5 * sp); y = cy + dy - rise * sp - 10 * grow
            rr = r * (0.3 + 0.7 * grow) * (1 + 0.6 * t)
            smoke += life * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * rr * rr))
        # inner ember glow: red-orange, strongest mid-cloud, flickering
        g = life * (1.0 + 0.4 * math.sin(i * 1.3)) * np.exp(-((xx - cx) ** 2) / (2 * (7 + 6 * grow) ** 2) - ((yy - (cy - 8 - rise * 0.5)) ** 2) / (2 * (9 + 5 * grow) ** 2))   # v3c: tighter so the cloud's edges stay black
        glow += g
        fire += 0.55 * life * np.exp(-((xx - cx) ** 2) / (2 * (6 + 5 * grow) ** 2) - ((yy - (cy - 6 - rise * 0.5)) ** 2) / (2 * (8 + 4 * grow) ** 2)) * (0.7 + 0.3 * math.sin(i * 2.1))   # a bright ember heart
        for dx, ph, sz, sp in embers:
            age = i - ph * 4
            if age < 0: continue
            x = cx + dx + 3 * math.sin(age * 0.8 + ph * 6); y = cy + 4 - age * 2.2 * sp
            fire += life * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
        s_ = np.clip(smoke, 0, 1); gl = np.clip(glow, 0, 1); f = np.clip(fire, 0, 1)
        # smoke colour: near-black ash with a faint death-green tinge, lit red-orange by the glow where thick
        gl = gl * gl * np.clip(s_ * 1.5, 0, 1)                                                                        # the glow only shows through thick ash, concentrated at the heart
        r = (24 + 215 * gl) * s_; g_ = (20 + 90 * gl) * s_; b = (22 + 6 * gl) * s_                                  # near-black ash lit red-orange from inside (v3b: the green tinge was too strong)
        r = r * (1 - f) + 255 * f; g_ = g_ * (1 - f) + 140 * f; b = b * (1 - f) + 30 * f
        alpha = np.clip(s_ * 0.95 + f, 0, 1)
        frames.append(Image.fromarray(np.dstack([r, g_, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def ashes_swirl():
    """Ashes to Ashes slot 0 v5 (20 frames 96x128, ALPHA 258/90) - user: "a fast tight swirl of particles (the same
    ember motes) spinning around the unit in a tight pillar-like radius, with a smoky effect / black particles":
    ~28 ember motes orbit a vertical axis at radius 9..15 px (ellipse 1:0.35 for perspective, back ones dimmer),
    about three revolutions over the sequence while drifting upward, with ~34 black ash flecks on wider orbits
    trailing short smears and a faint dark smoke column in the middle; the swirl gathers over the first frames
    and flies apart / thins out over the last five."""
    frames = []; rnd = random.Random(3535); N = 20; Wd, Ht = 96, 128
    yy, xx = np.mgrid[0:Ht, 0:Wd].astype(np.float32); cx, base = 48.0, 112.0
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(4, 92), rnd.uniform(9, 15), rnd.uniform(0.8, 1.05), rnd.uniform(1.0, 1.8)) for _ in range(30)]
    flecks = [(rnd.uniform(0, 6.28), rnd.uniform(0, 96), rnd.uniform(13, 21), rnd.uniform(0.7, 1.0), rnd.uniform(0.9, 1.7)) for _ in range(40)]   # v5b: smaller, more numerous flecks
    OMEGA = 0.95                                                     # rad per frame -> ~3 turns in 20 frames
    for i in range(N):
        t = i / (N - 1.0)
        gather = min(1.0, (i + 1) / 4.0); scatter = max(0.0, (i - 14) / 5.0); life = 1.0 - scatter
        fire = np.zeros((Ht, Wd), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
        for ph, h, r, w, sz in motes:
            a = ph + OMEGA * w * i; rr = r * (0.4 + 0.6 * gather) * (1 + 3.0 * scatter)
            x = cx + rr * math.cos(a); y = base - h - 1.2 * i + 0.35 * rr * math.sin(a)
            depth = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(a))        # front (sin>0) bright, back dim
            if not (0 <= x < Wd and 0 <= y < Ht): continue
            d2 = (xx - x) ** 2 + (yy - y) ** 2
            core = np.exp(-d2 / (2 * (sz * 0.9) ** 2)); star = (np.exp(-((xx - x) ** 2) / 0.8) * np.exp(-np.abs(yy - y) / 3.2) + np.exp(-((yy - y) ** 2) / 0.8) * np.exp(-np.abs(xx - x) / 3.2)) * 0.5
            fire += life * depth * (core + star); heat += life * depth * 0.9 * core
        for ph, h, r, w, sz in flecks:
            a = ph + OMEGA * w * i; rr = r * (0.4 + 0.6 * gather) * (1 + 2.0 * scatter)
            x = cx + rr * math.cos(a); y = base - h - 1.0 * i + 0.35 * rr * math.sin(a)
            for k in range(3):                                      # short smear behind the fleck
                a2 = a - 0.18 * k; x2 = cx + rr * math.cos(a2); y2 = base - h - 1.0 * i + 0.35 * rr * math.sin(a2)
                if 0 <= x2 < Wd and 0 <= y2 < Ht: smoke += life * (1 - 0.3 * k) * np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (sz * sz))
        # the smoke column: a faint dark pillar in the middle, widening a little at the top
        col = life * gather * 0.45 * np.exp(-((xx - cx) ** 2) / (2 * (6 + 4 * (base - yy) / 100.0) ** 2)) * np.clip((base + 6 - yy) / 12.0, 0, 1) * np.clip((yy - 8) / 10.0, 0, 1)
        smoke += col
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (70 + 150 * hh) * f; b = (10 + 90 * hh * hh) * f
        alpha = np.clip(f + s_ * 0.8, 0, 1)
        r = r * (1 - s_ * (1 - f)) + 18 * s_ * (1 - f); g = g * (1 - s_ * (1 - f)) + 16 * s_ * (1 - f); b = b * (1 - s_ * (1 - f)) + 18 * s_ * (1 - f)
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def ashes_swirl_seg(loop=6, fade=7):
    """Ashes to Ashes slot 3 (v6): ONE swirl segment per hit, spawned by the gate on every strike pass (kind-0x26
    driver with [fx+0x24]=1).  `loop` frames of the full pillar swirl (= GAP ticks, so consecutive hits chain into
    one continuous swirl) then `fade` frames where the motes spiral outward and dim and the smoke thins - the last
    hit's segment is the fade the user asked for.  96x128, ALPHA 258/90.  Polish vs v5: a warm core glow up the
    axis, mote trails, finer flecks."""
    frames = []; rnd = random.Random(3536); N = loop + fade; Wd, Ht = 96, 128
    yy, xx = np.mgrid[0:Ht, 0:Wd].astype(np.float32); cx, base = 48.0, 112.0
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(4, 92), rnd.uniform(9, 15), rnd.uniform(0.85, 1.05), rnd.uniform(1.1, 1.9)) for _ in range(32)]
    flecks = [(rnd.uniform(0, 6.28), rnd.uniform(0, 96), rnd.uniform(13, 21), rnd.uniform(0.7, 1.0), rnd.uniform(0.8, 1.5)) for _ in range(44)]
    OMEGA = 1.0
    for i in range(N):
        k = max(0.0, (i - loop + 1) / float(fade))                   # 0 during the loop .. 1 at the end of the fade
        life = 1.0 - k
        fire = np.zeros((Ht, Wd), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
        for ph, h, r, w, sz in motes:
            a = ph + OMEGA * w * i; rr = r * (1 + 2.6 * k * k)
            yb = base - h - 1.4 * i - 10 * k
            for tr in range(3):                                         # trail: two dimmer ghosts behind each mote
                a2 = a - 0.22 * tr; x = cx + rr * math.cos(a2); y = yb + 0.35 * rr * math.sin(a2)
                if not (0 <= x < Wd and 0 <= y < Ht): continue
                depth = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(a2)); amp = life * depth * (1.0 if tr == 0 else 0.35 / tr)
                d2 = (xx - x) ** 2 + (yy - y) ** 2
                core = np.exp(-d2 / (2 * (sz * 0.9) ** 2))
                star = (np.exp(-((xx - x) ** 2) / 0.8) * np.exp(-np.abs(yy - y) / 3.4) + np.exp(-((yy - y) ** 2) / 0.8) * np.exp(-np.abs(xx - x) / 3.4)) * 0.5 if tr == 0 else 0.0
                fire += amp * (core + star); heat += amp * 0.9 * core
        for ph, h, r, w, sz in flecks:
            a = ph + OMEGA * w * i; rr = r * (1 + 1.8 * k)
            for q in range(3):
                a2 = a - 0.18 * q; x2 = cx + rr * math.cos(a2); y2 = base - h - 1.0 * i - 6 * k + 0.35 * rr * math.sin(a2)
                if 0 <= x2 < Wd and 0 <= y2 < Ht: smoke += life * (1 - 0.3 * q) * np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (sz * sz))
        col = life * 0.5 * np.exp(-((xx - cx) ** 2) / (2 * (6 + 4 * (base - yy) / 100.0) ** 2)) * np.clip((base + 6 - yy) / 12.0, 0, 1) * np.clip((yy - 8) / 10.0, 0, 1)
        smoke += col
        glow = life * 0.55 * np.exp(-((xx - cx) ** 2) / (2 * 5.0 ** 2)) * np.clip((base + 2 - yy) / 10.0, 0, 1) * np.clip((yy - 14) / 14.0, 0, 1) * (0.8 + 0.2 * math.sin(i * 1.7))
        fire += glow; heat += 0.6 * glow
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (70 + 150 * hh) * f; b = (10 + 90 * hh * hh) * f
        alpha = np.clip(f + s_ * 0.8, 0, 1)
        r = r * (1 - s_ * (1 - f)) + 18 * s_ * (1 - f); g = g * (1 - s_ * (1 - f)) + 16 * s_ * (1 - f); b = b * (1 - s_ * (1 - f)) + 18 * s_ * (1 - f)
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def ashes_pulse():
    """Ashes to Ashes slot 0 (v6): the strike effect itself, now just a 4-frame (1 tick each) impact pulse - a ring of
    ember sparks snapping inward on the unit's chest with a flash - so the hit lands and damages within a few ticks
    (a class-7 effect lands only when its sequence reaches the last frame).  64x64 additive 770."""
    frames = []; rnd = random.Random(3537); yy, xx = np.mgrid[0:64, 0:64].astype(np.float32); cx = cy = 32.0
    sparks = [(rnd.uniform(0, 6.28), rnd.uniform(1.0, 1.6)) for _ in range(16)]
    for i in range(4):
        t = i / 3.0; f = np.zeros((64, 64), np.float32); heat = np.zeros_like(f)
        flash = (1 - t) * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (6 + 10 * t) ** 2)); f += flash; heat += 0.9 * flash
        R = 22 * (1 - t) + 4
        for a, sz in sparks:
            x = cx + R * math.cos(a); y = cy + R * 0.6 * math.sin(a)
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); f += g; heat += 0.5 * g
        f = np.clip(f, 0, 1); hh = np.clip(heat / np.maximum(f, 1e-3), 0, 1)
        frames.append(Image.fromarray(np.dstack([255 * f, (90 + 150 * hh) * f, (20 + 180 * hh * hh) * f, np.where(f > 0.03, 255, 0)]).astype(np.uint8), "RGBA"))
    return frames


def _swirl_frame(i, k, rnd_state, Wd=96, Ht=96, base=84.0, hmax=62.0, period=24):
    """One frame of the unit-height pillar swirl (v8).  i = continuous frame index (orbit phase), k = scatter 0..1
    (0 = steady loop, 1 = fully scattered/faded).  Pillar ~hmax px above the feet = a bit more than a unit."""
    motes, flecks = rnd_state
    yy, xx = np.mgrid[0:Ht, 0:Wd].astype(np.float32); cx = Wd / 2.0
    life = 1.0 - k
    fire = np.zeros((Ht, Wd), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
    # v9: SEAMLESS over `period` frames - every mote makes an integer number of turns (w = turns) and climbs an integer
    # number of pillar heights (vs = climbs) per period, so frame `period` == frame 0 and the 6-frame slices the gate
    # chains hit after hit join without a jump.  Motes = the caster-stream ember look: small bright core + star flare.
    for ph, h, r, w, sz, vs in motes:
        a = ph + 2 * math.pi * w * i / period; rr = r * (1 + 2.6 * k * k)
        yb = base - ((h + vs * hmax * i / period) % hmax) - 10 * k
        for tr in range(2):
            a2 = a - 0.25 * tr; x = cx + rr * math.cos(a2); y = yb + 0.35 * rr * math.sin(a2)
            if not (0 <= x < Wd and 0 <= y < Ht): continue
            depth = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(a2)); amp = life * depth * (2.2 if tr == 0 else 0.35)      # v11: brighter, white-hot centres
            d2 = (xx - x) ** 2 + (yy - y) ** 2
            core = np.exp(-d2 / (2 * (sz * 0.8) ** 2))
            star = (np.exp(-((xx - x) ** 2) / 0.5) * np.exp(-np.abs(yy - y) / 2.2) + np.exp(-((yy - y) ** 2) / 0.5) * np.exp(-np.abs(xx - x) / 2.2)) * 0.5 if tr == 0 else 0.0
            fire += amp * (core + star); heat += amp * 1.2 * core
    for ph, h, r, w, sz, vs in flecks:
        a = ph + 2 * math.pi * w * i / period; rr = r * (1 + 1.8 * k)
        yb = base - ((h + vs * (hmax + 6) * i / period) % (hmax + 6)) - 6 * k
        for q in range(2):
            a2 = a - 0.2 * q; x2 = cx + rr * math.cos(a2); y2 = yb + 0.35 * rr * math.sin(a2)
            if 0 <= x2 < Wd and 0 <= y2 < Ht: smoke += 0.55 * life * (1 - 0.4 * q) * np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (sz * sz))
    col = life * 0.5 * np.exp(-((xx - cx) ** 2) / (2 * (6 + 3 * (base - yy) / hmax) ** 2)) * np.clip((base + 6 - yy) / 12.0, 0, 1) * np.clip((yy - (base - hmax - 4)) / 10.0, 0, 1)
    smoke += col
    glow = life * 0.55 * np.exp(-((xx - cx) ** 2) / (2 * 5.0 ** 2)) * np.clip((base + 2 - yy) / 10.0, 0, 1) * np.clip((yy - (base - hmax + 2)) / 14.0, 0, 1) * (0.8 + 0.2 * math.sin(i * 1.7))
    fire += glow; heat += 0.6 * glow
    f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
    r = 255 * f; g = (70 + 150 * hh) * f; b = (10 + 90 * hh * hh) * f
    alpha = np.clip(f + s_ * 0.8, 0, 1)
    r = r * (1 - s_ * (1 - f)) + 18 * s_ * (1 - f); g = g * (1 - s_ * (1 - f)) + 16 * s_ * (1 - f); b = b * (1 - s_ * (1 - f)) + 18 * s_ * (1 - f)
    return Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA")


def _swirl_particles():
    rnd = random.Random(3539)
    # (phase, height, radius, turns per period, size, climbs per period) - turns/climbs integer for a seamless loop
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0, 62), rnd.uniform(9, 15), rnd.choice((3, 4)), rnd.uniform(0.55, 0.85), rnd.choice((1, 2))) for _ in range(46)]   # v11: smaller + more (fire-damage / Swarm sparks)
    flecks = [(rnd.uniform(0, 6.28), rnd.uniform(0, 68), rnd.uniform(13, 20), rnd.choice((2, 3)), rnd.uniform(0.7, 1.1), rnd.choice((1, 1, 2))) for _ in range(26)]
    return motes, flecks


def ashes_swirl_loop(n=24):
    """Ashes to Ashes slots 3..6 (v9): a SEAMLESS 24-frame pillar swirl cut into four 6-frame slices (12 ticks each);
    every hit spawns the next slice (marker = strike index mod 4 + 1), so the spin carries straight across the hits
    and simply stops after the last one - no fade (user).  Unit-height pillar, 96x96."""
    st = _swirl_particles()
    return [_swirl_frame(i, 0.0, st, period=n) for i in range(n)]


def ashes_swirl_fade(n=8, start=40):
    """Ashes to Ashes slot 4 (v8): the scatter/fade the gate spawns on the LAST hit while it kills the loop driver -
    motes spiral outward and dim, smoke thins, from a mid-orbit state."""
    st = _swirl_particles()
    return [_swirl_frame(start + i, (i + 1) / float(n), st) for i in range(n)]


def oil_splash():
    """Oil Spring slot 0 (12 frames 96x96, ALPHA 258/90): a burst of black-brown oil at the target hex spreading over
    the surrounding hexes - a central spout that collapses into rings of thick dark liquid with glossy highlights and
    flying drops, ending as a dark glistening pool with a few flame licks where it catches."""
    frames = []; rnd = random.Random(372); N = 12; SZ = 96
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, cy = 48.0, 58.0
    drops = [(rnd.uniform(0, 6.28), rnd.uniform(2.0, 4.5), rnd.uniform(1.2, 2.2)) for _ in range(22)]
    for i in range(N):
        t = i / (N - 1.0)
        oil = np.zeros((SZ, SZ), np.float32); gloss = np.zeros_like(oil); fire = np.zeros_like(oil)
        R = 10 + 34 * min(1.0, t * 1.3)                                       # the pool spreading (ellipse 1:0.5)
        pool = np.exp(-((((xx - cx) / R) ** 2 + ((yy - cy) / (R * 0.5)) ** 2) ** 2.0) * 1.2)
        oil += pool * (0.75 + 0.25 * (1 - t))
        if i < 7:                                                             # spout
            h = 30 * math.sin(math.pi * i / 7.0)
            col = np.exp(-((xx - cx) ** 2) / (2 * (4.5 + 2 * i / 7.0) ** 2)) * np.clip((yy - (cy - h)) / 6.0, 0, 1) * (yy <= cy)
            oil += col; gloss += 0.5 * col * np.exp(-((xx - cx + 2) ** 2) / 6.0)
        for a, v, sz in drops:                                                # drops flying out and falling back
            age = i - 1
            if age < 0: continue
            x = cx + math.cos(a) * v * 3.0 * age; y = cy - 6 - abs(math.sin(a)) * v * 5 * age + 1.1 * age * age
            if 0 <= x < SZ and 0 <= y < SZ and y < cy + 4: oil += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
        gloss += 0.35 * pool * np.exp(-(((xx - cx + 8) / (R * 0.55)) ** 2 + ((yy - cy + 3) / (R * 0.2)) ** 2) * 2.5)   # sheen
        if i >= 8:                                                            # small flames catching on the pool
            for k in range(5):
                fx_ = cx + (k - 2) * 11 + 3 * math.sin(i + k); fy = cy - 2 + 2 * math.sin(k * 2.0)
                fire += (i - 7) / 5.0 * np.exp(-((xx - fx_) ** 2) / 4.0 - ((yy - fy + 4 * (i - 7)) ** 2) / 24.0) * (yy < fy + 2)
        o = np.clip(oil, 0, 1); g = np.clip(gloss, 0, 1); f = np.clip(fire, 0, 1)
        r = (18 + 90 * g) * o; gg = (10 + 60 * g) * o; b = (6 + 30 * g) * o
        r = r * (1 - f) + 255 * f; gg = gg * (1 - f) + 150 * f; b = b * (1 - f) + 30 * f
        alpha = np.clip(o * 0.92 + f, 0, 1)
        frames.append(Image.fromarray(np.dstack([r, gg, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def lionheart_glow():
    """Lionheart slot 0 (10 frames 40x40 additive): a golden-red burst on the unit - a heart-shaped core flaring up
    with a ring of tawny mane-like rays, then sparkling out."""
    frames = []; rnd = random.Random(373); SZ = 40; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, cy = 20.0, 19.0
    sparks = [(rnd.uniform(0, 6.28), rnd.uniform(0.8, 1.4), rnd.uniform(0.9, 1.4)) for _ in range(14)]
    for i in range(10):
        t = i / 9.0; f = np.zeros((SZ, SZ), np.float32); heat = np.zeros_like(f)
        # heart: two lobes + a point, as a soft field
        hx, hy = (xx - cx) / 7.0, (yy - cy + 2) / 7.0
        heart = np.clip(1.6 - ((hx ** 2 + hy ** 2 - 1) ** 3 - hx ** 2 * hy ** 3), 0, 1) * np.exp(-(hx ** 2 + hy ** 2) / 3.0)
        pulse = 0.5 + 0.5 * math.sin(t * 6.28 * 1.5) if i < 7 else (9 - i) / 3.0
        f += 0.9 * pulse * heart; heat += 0.5 * pulse * heart
        rays = 0.5 * pulse * np.clip(0.5 + 0.5 * np.sin(8 * np.arctan2(yy - cy, xx - cx) + i * 0.6), 0, 1) * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) - 110) ** 2 / 2600.0)
        f += rays; heat += 0.2 * rays
        for a, v, sz in sparks:
            x = cx + math.cos(a) * v * 2.4 * i; y = cy + math.sin(a) * v * 2.0 * i - 0.4 * i
            if 0 <= x < SZ and 0 <= y < SZ: g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); f += (1 - t) * g; heat += 0.6 * (1 - t) * g
        f = np.clip(f, 0, 1); hh = np.clip(heat / np.maximum(f, 1e-3), 0, 1)
        frames.append(Image.fromarray(np.dstack([255 * f, (60 + 180 * hh) * f, (10 + 70 * hh * hh) * f, np.where(f > 0.03, 255, 0)]).astype(np.uint8), "RGBA"))
    return frames


def forge_sparks():
    """Forge Blast (14 frames 128x96, ALPHA 258/90): a hammer-blow burst over the city - a white-orange flash, a
    fountain of sparks and molten chips spraying up and out, dark smoke rolling up, embers raining."""
    frames = []; rnd = random.Random(374); N = 14; W_, H_ = 128, 96
    yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32); cx, cy = 64.0, 70.0
    sparks = [(rnd.uniform(0, 6.28), rnd.uniform(2.0, 5.0), rnd.uniform(0.8, 1.5), rnd.uniform(0, 0.4)) for _ in range(70)]
    for i in range(N):
        t = i / (N - 1.0); fire = np.zeros((H_, W_), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
        if i <= 3: fl = 1 - i / 3.0; fire += 1.3 * fl * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (8 + 10 * i) ** 2)); heat += 1.2 * fl * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (6 + 8 * i) ** 2))
        for a, v, sz, ph in sparks:
            age = i - ph * 3
            if age < 0: continue
            x = cx + math.cos(a) * v * 4.0 * age; y = cy - abs(math.sin(a)) * v * 7 * age + 0.75 * age * age
            if 0 <= x < W_ and 0 <= y < H_:
                g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); fire += (1 - 0.6 * t) * g; heat += 0.6 * g
        cloud = max(0.0, (i - 2) / 8.0)
        smoke += 0.7 * cloud * (1 - 0.6 * t) * np.exp(-((xx - cx) ** 2) / (2 * (12 + 22 * cloud) ** 2) - ((yy - (cy - 20 - 22 * cloud)) ** 2) / (2 * (10 + 10 * cloud) ** 2))
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (90 + 160 * hh) * f; b = (20 + 200 * hh * hh) * f
        alpha = np.clip(f + s_ * 0.85, 0, 1)
        r = r * (1 - s_ * (1 - f)) + 30 * s_ * (1 - f); g = g * (1 - s_ * (1 - f)) + 26 * s_ * (1 - f); b = b * (1 - s_ * (1 - f)) + 26 * s_ * (1 - f)
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def arms_race_glow():
    """Arms Race slot 0 (15 frames 48x48 additive): a forge-glow twinkle over the city - an orange-gold pulse with a
    turning cog of light (eight spokes) and rising sparks."""
    frames = []; rnd = random.Random(375); SZ = 48; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx = cy = 24.0
    sparks = [(rnd.uniform(14, 34), rnd.uniform(0, 1), rnd.uniform(0.8, 1.3)) for _ in range(12)]
    for i in range(15):
        t = i / 14.0; f = np.zeros((SZ, SZ), np.float32); heat = np.zeros_like(f)
        env = math.sin(math.pi * t) ** 0.6
        ang = np.arctan2(yy - cy, xx - cx); r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        ring = np.exp(-((r - 11) ** 2) / 8.0) * (0.55 + 0.45 * np.cos(8 * ang - i * 0.5)); f += env * ring; heat += 0.3 * env * ring
        core = np.exp(-r ** 2 / 30.0) * (0.8 + 0.2 * math.sin(i * 1.9)); f += env * core; heat += 0.8 * env * core
        for x, ph, sz in sparks:
            y = 40 - (i + ph * 6) * 2.6
            if 0 <= y < SZ: g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); f += env * g; heat += 0.5 * env * g
        f = np.clip(f, 0, 1); hh = np.clip(heat / np.maximum(f, 1e-3), 0, 1)
        frames.append(Image.fromarray(np.dstack([255 * f, (110 + 130 * hh) * f, (20 + 120 * hh * hh) * f, np.where(f > 0.03, 255, 0)]).astype(np.uint8), "RGBA"))
    return frames


def oil_gush_v2():
    """Oil Spring v2 gfx (18 frames 128x128, ALPHA 258/90): a geyser of black oil - a column shoots up from the centre of
    the area, widens and sheds drops at the top which arc outward and rain down; the column collapses and a dark pool
    spreads at the base."""
    frames = []; rnd = random.Random(1372); N = 18; SZ = 128
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, base = 64.0, 112.0
    drops = [(rnd.uniform(-1, 1), rnd.uniform(1.5, 3.5), rnd.uniform(1.4, 2.6), rnd.uniform(0, 0.5)) for _ in range(60)]
    for i in range(N):
        t = i / (N - 1.0)
        oil = np.zeros((SZ, SZ), np.float32); gloss = np.zeros_like(oil)
        h = 96 * math.sin(math.pi * min(1.0, i / 11.0)) if i < 11 else 96 * max(0.0, 1 - (i - 10) / 6.0) ** 1.5
        if h > 2:
            top = base - h
            col = np.exp(-((xx - cx + 3 * np.sin(yy * 0.1 + i * 0.8)) ** 2) / (2 * (5 + 7 * np.clip((yy - top) / max(1.0, h), 0, 1) ** 0.5 * (1 - 0.6 * (yy - top) / max(1.0, h))) ** 2)) * np.clip((yy - top) / 5.0, 0, 1) * (yy <= base)
            oil += col; gloss += 0.4 * col * np.exp(-((xx - cx + 3) ** 2) / 8.0)
            crown = np.exp(-((xx - cx) ** 2) / (2 * 9.0 ** 2) - ((yy - top) ** 2) / (2 * 5.0 ** 2)); oil += crown
        for a, v, sz, ph in drops:                                                                         # drops leaving the crown, arcing out and down
            age = i - 3 - ph * 4
            if age < 0: continue
            ty0 = base - 96 * math.sin(math.pi * min(1.0, max(0, i - age) / 11.0))
            x = cx + a * v * 6.0 * age; y = ty0 - v * 5 * age + 1.3 * age * age
            if 0 <= x < SZ and 0 <= y < base + 6: oil += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
        R = 8 + 52 * min(1.0, t * 1.2)
        pool = np.exp(-((((xx - cx) / R) ** 2 + ((yy - base + 4) / (R * 0.42)) ** 2) ** 2.0) * 1.2); oil += pool * (0.6 + 0.4 * t)
        gloss += 0.3 * pool * np.exp(-(((xx - cx + 10) / (R * 0.5)) ** 2 + ((yy - base + 6) / (R * 0.18)) ** 2) * 2.5)
        o = np.clip(oil, 0, 1); g = np.clip(gloss, 0, 1)
        r = (16 + 95 * g) * o; gg = (10 + 60 * g) * o; b = (6 + 30 * g) * o
        frames.append(Image.fromarray(np.dstack([r, gg, b, 255 * np.clip(o * 0.94, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def _oil_gush_oneshot():
    """Oil Spring v4 gush (user 2026-10-14: 'particle based - lots of black particles, so many it looks almost solid,
    flowing out of the ground upwards before mushrooming at the top'): 18 frames 128x128, a fountain of ~900 black
    droplets emitted from the fissure at the hex centre (base (64,112)) with an upward velocity, a slight sideways
    spread that grows with height so the column mushrooms at the top, then the particles arc out and fall back; the
    pool at the base grows as they land.  Each particle is a small glossy black dot; density makes the column read
    as near-solid.  Opaque ink, soft edge only."""
    frames = []; N = 18; SZ = 128; rnd = random.Random(1484)
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, base = 64.0, 112.0
    parts = []
    for p in range(1400):
        t0 = rnd.uniform(0, 11.0)                                       # emission frame (continuous stream)
        vy = rnd.uniform(14.0, 20.5) * (1.0 if t0 < 9 else 0.6)         # upward speed px/frame (weaker at the end)
        vx = rnd.gauss(0, 1.9)                                          # initial sideways speed (a fatter column)
        sz = rnd.uniform(1.2, 2.6); g = rnd.uniform(0.0, 1.0)
        parts.append((t0, vy, vx, sz, g))
    for i in range(N):
        ink = np.zeros((SZ, SZ), np.float32); gloss = np.zeros_like(ink); landed = 0.0
        for t0, vy, vx, sz, g in parts:
            age = i - t0
            if age < 0: continue
            y = base - vy * age + 1.05 * age * age                                   # rise, then fall under gravity
            apex_age = vy / 2.1; h = max(0.0, base - y)
            spread = vx * age + math.copysign(1, vx) * 0.9 * max(0.0, age - apex_age * 0.75) ** 1.6   # mushroom: strong lateral drift past the apex
            x = cx + spread
            if y > base + 2:
                landed += 1; continue
            if 0 <= x < SZ and 0 <= y < SZ:
                d = (xx - x) ** 2 + (yy - y) ** 2
                dot = np.exp(-d / (sz * sz)); ink = np.maximum(ink, dot)
                if g > 0.6: gloss = np.maximum(gloss, np.exp(-((xx - x + sz * 0.5) ** 2 + (yy - y + sz * 0.5) ** 2) / (sz * sz * 0.35)) * 0.7)
        R = 6 + min(52.0, landed * 0.11)
        pool = np.exp(-((((xx - cx) / R) ** 2 + ((yy - base + 3) / (R * 0.40)) ** 2) ** 2.2) * 1.1) * min(1.0, 0.45 + landed * 0.004)
        ink = np.maximum(ink, pool); gloss = np.maximum(gloss, 0.35 * pool * np.exp(-(((xx - cx + 12) / (R * 0.45)) ** 2 + ((yy - base + 5) / (R * 0.16)) ** 2) * 2.2))
        o = np.clip(ink, 0, 1); gl = np.clip(gloss, 0, 1)
        r = (12 + 110 * gl) * o; gg = (9 + 70 * gl) * o; b = (6 + 36 * gl) * o
        frames.append(Image.fromarray(np.dstack([r, gg, b, 255 * np.clip(o * 1.8, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


PULSE = 0.42                         # fountain height pulse amplitude (user 2026-10-14: 'rises, drops a bit, rises again'); one pulse per loop cycle (10 frames x 3 ticks)
_BALLS = None
def _oil_balls():
    """Particle stamps = small BLACK OIL BALLS lit from the upper left (user 2026-10-14: the flat dots / pure-black
    motes read as 2-D): an opaque black disc with a 1-px soft rim and a grey highlight crescent toward the light, at
    radii 2.2 / 3.0 / 4.0 px.  Each stamp = (alpha, grey) arrays; composited painter's-order so the highlights of the
    nearer balls stay visible and overlapping balls read as a lumpy mass with volume."""
    global _BALLS
    if _BALLS is None:
        out = []
        for r in (1.5, 2.1, 2.9):
            n = int(math.ceil(r)) * 2 + 3; c = n / 2.0
            yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
            d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
            alpha = np.clip(r + 0.5 - d, 0, 1)
            hl = np.sqrt((xx - c + 0.42 * r) ** 2 + (yy - c + 0.42 * r) ** 2)
            grey = 150 * np.clip(1 - hl / (0.80 * r), 0, 1) ** 1.2 * (d <= r + 0.5)
            out.append((alpha.astype(np.float32), grey.astype(np.float32)))
        _BALLS = out
    return _BALLS


def _stamp(ink, grey, stamp, x, y):
    """Painter's-order composite of a (alpha, grey) stamp centred at (x, y): where the stamp is opaque it overwrites."""
    sa, sg = stamp; h, w = sa.shape; x0 = int(round(x - w / 2)); y0 = int(round(y - h / 2))
    sx0, sy0 = max(0, -x0), max(0, -y0); ex, ey = min(w, ink.shape[1] - x0), min(h, ink.shape[0] - y0)
    if ex <= sx0 or ey <= sy0: return
    sub_a = ink[y0 + sy0:y0 + ey, x0 + sx0:x0 + ex]; sub_g = grey[y0 + sy0:y0 + ey, x0 + sx0:x0 + ex]
    a = sa[sy0:ey, sx0:ex]; g = sg[sy0:ey, sx0:ex]
    solid = a >= 0.75
    sub_g[solid] = g[solid]
    np.maximum(sub_a, a, out=sub_a)


def _oil_fountain_frame(parts, i, P, cutoff=0.0, pool_R=30.0, rise=False, ceil=None):
    """One fountain frame of lit black oil balls, dense enough at the column to read as a solid stream (with glints) and
    thinning out as they mushroom.  rise: only particles emitted so far (age = i - t0, first generation); otherwise
    steady state: every particle re-emitted every P frames, three generations in flight; only ages >= cutoff drawn
    (cutoff > 0 = the emission has stopped, the column empties from the bottom up)."""
    SZ = 160; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, base = 80.0, 140.0   # v12: 160-px frame so the spray never touches the edges (128 clipped it square)
    ink = np.zeros((SZ, SZ), np.float32); grey = np.zeros((SZ, SZ), np.float32); balls = _oil_balls()
    # the pool first (behind everything): a black ellipse with a sheen band
    R = max(pool_R, 0.5)
    pool = np.exp(-((((xx - cx) / R) ** 2 + ((yy - base + 3) / (R * 0.40)) ** 2) ** 2.2) * 1.1) * 0.95 * (1.0 if pool_R >= 2.0 else 0.0)
    sheen = 110 * np.exp(-(((xx - cx + 0.25 * R) / (R * 0.45)) ** 2 + ((yy - base + 5) / (R * 0.14)) ** 2) * 2.0)
    ink = np.maximum(ink, pool); grey = np.where(pool > 0.5, sheen, grey)
    drawn = []
    for t0, vy0, vx, sz, spr in parts:
        for k in range(1 if rise else 3):
            age = (i - t0) if rise else (i - t0) % P + k * P
            if age < cutoff or age < 0: continue
            vy = vy0 * (1.0 + PULSE * math.sin(2 * math.pi * (i - age) / (P / 2.0 if rise else P)))   # v11: the emission speed pulses with the emission time -> rises, sags, rises each loop cycle (seamless: period = P); v15: the RISE pulses twice as fast = one extra pulse in the first half (user 2026-10-14)
            y = base - vy * age + 1.05 * age * age
            if y > base + 2: continue
            if ceil is not None and y < base - ceil: continue                         # 2026-10-17: the rising ceiling (gush grows out of the ground)
            apex_age = vy / 2.1
            past = max(0.0, age - apex_age * 0.7)
            spread = vx * age + math.copysign(1, vx) * (0.5 + 4.6 * spr) * (math.sqrt(past + 2.0) - math.sqrt(2.0))   # v14: dome flare that starts with a finite slope (no gap on the centre line = no seam) and a wide random strength so some droplets stay near the middle
            x = cx + spread
            if 4 <= x < SZ - 4 and 4 <= y < SZ - 4: drawn.append((y, x, int(sz * 3) % 3))
    drawn.sort(key=lambda t: -t[0])                                                     # far (higher) first, near (lower) on top
    for y, x, b in drawn: _stamp(ink, grey, balls[b], x, y)
    o = np.clip(ink, 0, 1)
    rgb = (6 + grey) * o
    return Image.fromarray(np.dstack([rgb, rgb * 0.92, rgb * 0.8, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA")


def _oil_fountain_parts(P=10, n=1200):
    rnd = random.Random(1485)
    return [(rnd.uniform(0, P), rnd.uniform(12.5, 17.5), rnd.gauss(0, 1.0), rnd.uniform(0.0, 0.999), rnd.uniform(0, 1)) for _ in range(n)]   # 4th value = the mote stamp pick (0..1 -> 9 stamps)


def oil_gush():
    """v6: the RISE (slot 4) = the stream starting up, rendered by the same particle fountain (frames 0..9, first
    generation only) so the hand-over to the loop is seamless."""
    parts = _oil_fountain_parts(); P = 10
    def ceil_(i):                                                                    # 2026-10-17 (user: it suddenly appears - make it RISE out of the
        u = min(1.0, (i + 1) / float(P)); return 4 + 140 * (u * u * (3 - 2 * u))       #   ground): a ceiling climbing smoothly to full height by the last
    return [_oil_fountain_frame(parts, i, P, rise=True, pool_R=4 + 2.6 * i, ceil=ceil_(i)) for i in range(P)]   #   rise frame (= the loop's first frame, seamless)


def oil_gush_loop(P=10):
    """The steady-state fountain (slot 5): a continuous stream - every particle is re-emitted every P frames, so the
    column, the mushroom head and the falling spray are all present in every frame and the 10 frames cycle seamlessly.
    The gate keeps this driver alive until the last glob is launched."""
    parts = _oil_fountain_parts(P)
    return [_oil_fountain_frame(parts, i, P) for i in range(P)]


def oil_gush_end(delay=9, P=10, n_end=8):
    """The collapse (slot 6): `delay` blank frames first (the loop driver still shows the fountain while the last glob
    falls), then the emission stops: the column empties from the bottom up while the spray that is already in the air
    keeps falling (cutoff grows 2.4 frames per frame), the pool staying put."""
    parts = _oil_fountain_parts(P)
    return [Image.new("RGBA", (4, 4), (0, 0, 0, 0)) for _ in range(delay)] + [_oil_fountain_frame(parts, P + j, P, cutoff=2.4 * (j + 1), pool_R=30.0 * max(0.0, 1.0 - max(0, j - 1) / (n_end - 1.5)) ** 1.1) for j in range(n_end)]   # v16: the pool shrinks away over the collapse (user: the last puddle vanished too abruptly)


def sand_puff(n=10):
    """Sandstorm (388) slot 0 (2026-10-14; replaces Swarm's SWARM.ILB 0-9 flying sprite, anchor -8/-8 -> we use -16/-16):
    32x32, a swirling tan dust devil that lands as a stinging puff - a spinning streaky cloud of ochre grains that
    tightens, then bursts outward with grit flying."""
    frames = []; rnd = random.Random(1388); yy, xx = np.mgrid[0:32, 0:32].astype(np.float32); cx, cy = 16.0, 16.0
    grains = [(rnd.uniform(0, 6.28), rnd.uniform(0.3, 1.0), rnd.uniform(0.6, 1.2)) for _ in range(40)]
    for i in range(n):
        t = i / (n - 1.0); a = np.zeros((32, 32), np.float32); lit = np.zeros_like(a)
        R = 11 - 5 * min(1.0, i / 6.0) + 9 * max(0.0, (i - 6) / 3.0)                                   # tightens then bursts
        ang = np.arctan2(yy - cy, xx - cx); rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        swirl = 0.5 + 0.5 * np.sin(3 * ang + rr * 0.55 - i * 1.1)                                       # rotating streaks
        body = np.exp(-(rr / R) ** 2 * 1.6) * (0.45 + 0.55 * swirl) * (1.0 if i < 8 else 1 - (i - 7) / 3.0)
        a += body; lit += 0.5 * body * np.exp(-((xx - cx + 3) ** 2 + (yy - cy + 3) ** 2) / 40.0)
        for g0, v, sz in grains:
            r_ = (0.3 + 0.7 * v) * R * (1.15 if i > 6 else 1.0); x = cx + r_ * math.cos(g0 + i * 0.5); y = cy + r_ * math.sin(g0 + i * 0.5)
            a += 0.9 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
        o = np.clip(a, 0, 1); l = np.clip(lit, 0, 1)
        r = (178 + 60 * l) * o; g = (140 + 50 * l) * o; b = (82 + 35 * l) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.6, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def implosion_fx(n=14):
    """Implosion (389) impact slot 2 (2026-10-14): 96x96 at the landing hex - a ring of fiery debris shards is sucked
    inward and spins faster as it collapses to a point, then a white-hot flash bursts and fades; frames 258/90."""
    frames = []; rnd = random.Random(1389); yy, xx = np.mgrid[0:96, 0:96].astype(np.float32); cx, cy = 48.0, 48.0
    shards = [(rnd.uniform(0, 6.28), rnd.uniform(0.7, 1.0), rnd.uniform(1.6, 3.2)) for _ in range(60)]
    for i in range(n):
        a = np.zeros((96, 96), np.float32); heat = np.zeros_like(a)
        if i < 9:                                                                                       # the suck: ring radius 40 -> 4 (accelerating), shards spin faster
            t = i / 8.0; R = 40 * (1 - t) ** 1.7 + 3
            for a0, v, sz in shards:
                ang = a0 + 2.2 * t * t + 0.6 * t; r_ = R * (0.75 + 0.5 * v)
                x = cx + r_ * math.cos(ang); y = cy + r_ * math.sin(ang) * 0.85
                tail = np.exp(-(((xx - x) * math.cos(ang + 1.57) + (yy - y) * math.sin(ang + 1.57)) ** 2) / (sz * sz * 0.5) - (((xx - x) * math.cos(ang) + (yy - y) * math.sin(ang)) ** 2) / (sz * sz * 3.0))
                a += 0.9 * tail; heat += 0.35 * tail
            ring = np.exp(-(np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.85) ** 2) - R) ** 2 / 9.0) * (0.35 + 0.4 * t); a += ring; heat += 0.5 * ring * t
            core = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (2 + 10 * t) ** 2)) * t; a += core; heat += core
        else:                                                                                           # the burst: a white-hot flash expanding and fading
            t = (i - 9) / 4.0; R = 14 + 40 * t
            flash = np.exp(-(((xx - cx) ** 2 + ((yy - cy) / 0.9) ** 2) / (2 * R * R)) ** 1.4) * (1 - t) ** 0.5 * 1.4
            a += flash; heat += flash * (1.2 - t)
            for a0, v, sz in shards[:28]:
                x = cx + (6 + 46 * t) * v * math.cos(a0); y = cy + (6 + 46 * t) * v * math.sin(a0) * 0.85
                sp = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * (1 - t); a += sp; heat += 0.6 * sp
        o = np.clip(a, 0, 1); h = np.clip(heat / np.maximum(a, 1e-3), 0, 1)
        r = (200 + 55 * h) * o; g = (70 + 170 * h) * o; b = (20 + 200 * h * h) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def rage_flare(n=8):
    """Frenzied Charge (390) slot 0 (High Prayer's PARTICLE 12-14 per-unit twinkle slot): 24x24, a red-orange flare on
    each unit - three flame tongues tapering to their tips leap from a hot core, swell, then fade."""
    frames = []; yy, xx = np.mgrid[0:24, 0:24].astype(np.float32); cx, cy = 12.0, 17.0
    for i in range(n):
        t = i / (n - 1.0); a = np.zeros((24, 24), np.float32); heat = np.zeros_like(a)
        env = math.sin(math.pi * min(1.0, 0.15 + t)) ** 0.7
        core = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 2.6 ** 2)) * env; a += core; heat += core
        for k, (dx, h, ph) in enumerate(((-4.5, 10.0, 0.0), (0.0, 14.0, 0.5), (4.5, 9.0, 1.0))):
            hh = h * (0.55 + 0.45 * math.sin(2.2 * t * math.pi + ph)) * env
            if hh < 1: continue
            u = np.clip((cy - yy) / hh, 0, 1)                                      # 0 at the base, 1 at the tip
            w = 2.4 * (1 - u) + 0.5; lean = dx * (0.3 + 0.7 * u) + 1.2 * math.sin(3 * t * math.pi + ph) * u
            tongue = np.exp(-((xx - cx - lean) ** 2) / (2 * w * w)) * (u < 1) * (yy <= cy + 1) * (1 - 0.35 * u)
            a += tongue; heat += tongue * (1 - u) * 0.9
        o = np.clip(a, 0, 1); h = np.clip(heat / np.maximum(a, 1e-3), 0, 1)
        r = (225 + 30 * h) * o; g = (50 + 170 * h) * o; b = (10 + 70 * h * h) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def rage_whirl(n=21):
    """Frenzied Charge (390) slot 1 (High Prayer's MAGIC.ILB 89-109 caster pillar slot): 96x96 at the caster - a cone of
    fire streaks spiralling up and outward (a rising whirl), 21 frames like the donor's: fades in over 4, holds, fades
    out over the last 6."""
    frames = []; yy, xx = np.mgrid[0:96, 0:96].astype(np.float32); cx, cy = 48.0, 78.0
    for i in range(n):
        a = np.zeros((96, 96), np.float32); heat = np.zeros_like(a)
        life = min(1.0, i / 4.0) * (1.0 if i < 15 else max(0.0, 1 - (i - 14) / 6.0))
        for k in range(56):                                                                      # streaks on a rising spiral
            h = (i * 3.3 + k * 6.1) % 66; ang = k * 0.9 + i * 0.5 + h * 0.06
            r_ = 5 + 0.48 * h; x = cx + r_ * math.cos(ang); y = cy - h + 3 * math.sin(ang)
            if not (2 < x < 94 and 2 < y < 94): continue
            dxs, dys = math.cos(ang + 1.3), -0.9                                                  # streak direction: up and round
            u = (xx - x) * dxs + (yy - y) * dys; v = -(xx - x) * dys + (yy - y) * dxs
            st = np.exp(-(u * u) / (2 * 4.5 ** 2) - (v * v) / (2 * 1.4 ** 2)) * life * (1 - 0.5 * h / 66.0)
            a += st; heat += st * (1 - h / 66.0) * 0.8
        core = np.exp(-(((xx - cx) ** 2) / (2 * 6.0 ** 2) + ((yy - cy + 12) ** 2) / (2 * 14.0 ** 2))) * life; a += core; heat += core
        o = np.clip(a, 0, 1); h = np.clip(heat / np.maximum(a, 1e-3), 0, 1)
        r = (215 + 40 * h) * o; g = (60 + 165 * h) * o; b = (12 + 80 * h * h) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def heat_flare(n=4):
    """Drought (391) slot 0 (Water Mastery's PARTICLE 0-2 caster twinkle slot, -10/-10): 24x24, a hot orange sun flare
    - a bright core with eight rays that pulse over 4 frames."""
    frames = []; yy, xx = np.mgrid[0:24, 0:24].astype(np.float32); cx, cy = 12.0, 12.0
    for i in range(n):
        ph = [0.0, 0.6, 1.0, 0.6][i]; a = np.zeros((24, 24), np.float32)
        a += np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (2.2 + 1.2 * ph) ** 2))
        ang = np.arctan2(yy - cy, xx - cx); rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        rays = np.clip(np.cos(4 * ang + ph * 0.8), 0, 1) ** 6 * np.exp(-rr / (5.0 + 4.0 * ph)) * (rr > 1.5); a += 0.9 * rays
        o = np.clip(a, 0, 1); w = np.clip(o * 1.3, 0, 1)
        r = (235 + 20 * w) * o; g = (120 + 120 * w) * o; b = (20 + 120 * w * w) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


_MOTES = None
def _oil_motes():
    """Mind Decay's motes (PARTICLE.ILB 15/16/17, dark shaded dots on white) as alpha stamps at three scales."""
    global _MOTES
    if _MOTES is None:
        lib = ilbcodec.read(PARTICLE); out = []
        for src in (15, 16, 17):
            im, r = raw_pixels(lib, src); a_ = np.array(im.convert("RGB")).astype(np.float32)
            v = np.clip((1.0 - a_.max(2) / 255.0 - 0.08) / 0.92, 0, 1)
            base = Image.fromarray((v * 255).astype(np.uint8), "L")
            for sc in (0.9, 1.3, 1.8):
                w = max(3, int(round(base.width * sc))); h = max(3, int(round(base.height * sc)))
                out.append(np.array(base.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255.0)
        _MOTES = out
    return _MOTES


def implosion_ring(n=14):
    """Implosion (389) slot 3 (2026-10-14; user: 'like Animate Dead's circle but reversed and red'): 128x128, a ring of
    red-orange sparkle motes (the PARTICLE.ILB twinkle stamps tinted red) around the target that shrinks into it over
    14 frames, spinning faster and brightening as it closes."""
    frames = []; rnd = random.Random(3891); motes = _oil_motes(); yy, xx = np.mgrid[0:128, 0:128].astype(np.float32); cx, cy = 64.0, 64.0
    pts = [(rnd.uniform(0, 6.28), rnd.uniform(0.85, 1.15), rnd.randrange(9)) for _ in range(70)]
    for i in range(n):
        t = i / (n - 1.0); R = 54 * (1 - t) ** 1.25 + 2; ink = np.zeros((128, 128), np.float32)
        for a0, v, m in pts:
            a = a0 + 0.35 * i + 1.2 * t * t; x = cx + R * v * math.cos(a); y = cy + 0.9 * R * v * math.sin(a)
            _stamp_alpha(ink, motes[m], x, y)
        glow = np.exp(-(np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.9) ** 2) - R) ** 2 / (2 * 5.0 ** 2)) * (0.25 + 0.5 * t)
        core = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (3 + 12 * t) ** 2)) * t * t
        o = np.clip(ink + glow + core, 0, 1); w = np.clip(core * 1.5 + ink * 0.3, 0, 1)
        r = (225 + 30 * w) * o; g = (30 + 170 * w) * o; b = (20 + 120 * w * w) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def _stamp_alpha(ink, stamp, x, y):
    h, w = stamp.shape; x0 = int(round(x - w / 2)); y0 = int(round(y - h / 2))
    sx0, sy0 = max(0, -x0), max(0, -y0); ex, ey = min(w, ink.shape[1] - x0), min(h, ink.shape[0] - y0)
    if ex <= sx0 or ey <= sy0: return
    sub = ink[y0 + sy0:y0 + ey, x0 + sx0:x0 + ex]; np.maximum(sub, stamp[sy0:ey, sx0:ex], out=sub)


def drought_particles():
    """Drought (391) cast slot (user: red particles instead of Water Mastery's blue ones): the vanilla PARTICLE.ILB 0-2
    twinkle lifted and re-coloured red-orange (same shapes, motion and timing as the blue originals)."""
    lib = ilbcodec.read(PARTICLE); out = []
    for src in (0, 1, 2):
        im, r = raw_pixels(lib, src); im = im.convert("RGBA"); a = np.array(im).astype(np.float32)
        lum = a[:, :, :3].max(2) / 255.0; alpha = a[:, :, 3] / 255.0 if a.shape[2] > 3 else np.ones_like(lum)
        o = lum * alpha
        rgb = np.dstack([255 * o, (60 + 150 * lum ** 1.5) * o, (10 + 50 * lum ** 3) * o])     # v2: bright orange core fading to deep red (drawn ADDITIVE like the vanilla twinkle)
        out.append(Image.fromarray(np.dstack([rgb, 255 * (o > 0.04)]).astype(np.uint8), "RGBA"))
    return out


def sand_streak(n=4):
    """Sandstorm v2 (388) hail slot 0 (the falling head; Great Hail's BALLS-style ~32 px): 32x32, a diagonal lash of
    ochre sand grains streaking down-left, 4 frames of flicker."""
    frames = []; rnd = random.Random(1392); yy, xx = np.mgrid[0:32, 0:32].astype(np.float32)
    grains = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0.6, 1.3)) for _ in range(28)]
    for i in range(n):
        a = np.zeros((32, 32), np.float32); lit = np.zeros_like(a)
        u = (xx - 16) * 0.7071 + (yy - 16) * 0.7071; v = -(xx - 16) * 0.7071 + (yy - 16) * 0.7071         # along / across the streak
        streak = np.exp(-(v * v) / (2 * 2.2 ** 2) - (u * u) / (2 * 11.0 ** 2)) * (0.8 + 0.2 * math.sin(i * 1.6)); a += streak; lit += 0.4 * streak * np.exp(-(v + 1.5) ** 2 / 3.0)
        for gx, gy, sz in grains:
            x = 16 + gx * 11 + 2.0 * math.sin(i + gx * 5); y = 16 + gx * 11 + gy * 3.5 + 1.5 * math.cos(i + gy * 4)
            a += 0.9 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
        o = np.clip(a, 0, 1); l = np.clip(lit, 0, 1)
        r = (178 + 60 * l) * o; g = (140 + 50 * l) * o; b = (82 + 35 * l) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.6, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def sand_trail():
    """Sandstorm v2 (388) hail slot 1 (the trail, 1 frame): a faint scatter of grains behind the lash."""
    rnd = random.Random(1393); yy, xx = np.mgrid[0:32, 0:32].astype(np.float32); a = np.zeros((32, 32), np.float32)
    for _ in range(18):
        x, y = rnd.uniform(6, 26), rnd.uniform(6, 26); sz = rnd.uniform(0.5, 1.0); a += 0.7 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
    o = np.clip(a, 0, 1)
    return [Image.fromarray(np.dstack([178 * o, 140 * o, 82 * o, 255 * np.clip(o * 1.6, 0, 1)]).astype(np.uint8), "RGBA")]


def sand_clump(n=4):
    """Sandstorm v3 hail slot 0 (the falling head): 24x24, a dense round clump of ochre grains that tumbles."""
    frames = []; rnd = random.Random(1395); yy, xx = np.mgrid[0:24, 0:24].astype(np.float32)
    grains = [(rnd.uniform(0, 6.28), rnd.uniform(0, 1) ** 0.6 * 7.0, rnd.uniform(0.7, 1.4)) for _ in range(46)]
    for i in range(n):
        a = np.zeros((24, 24), np.float32); lit = np.zeros_like(a)
        for g0, r_, sz in grains:
            x = 12 + r_ * math.cos(g0 + i * 0.6); y = 12 + r_ * 0.9 * math.sin(g0 + i * 0.6)
            d = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); a += d; lit += 0.5 * d * max(0.0, 1 - r_ / 7.0) * (0.5 + 0.5 * math.cos(g0 + i * 0.6 - 2.3))
        o = np.clip(a, 0, 1); l = np.clip(lit, 0, 1)
        r = (170 + 65 * l) * o; g = (132 + 55 * l) * o; b = (76 + 40 * l) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.6, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def sand_burst(n=8):
    """Sandstorm v3 hail slot 2 (impact at the hex): 48x48, a flat burst of dust rolling outward from the landing point
    with grit flung up and out, settling as it thins."""
    frames = []; rnd = random.Random(1396); yy, xx = np.mgrid[0:48, 0:48].astype(np.float32); cx, cy = 24.0, 30.0
    grit = [(rnd.uniform(0, 6.28), rnd.uniform(0.5, 1.0), rnd.uniform(0.6, 1.2)) for _ in range(40)]
    for i in range(n):
        t = i / (n - 1.0); a = np.zeros((48, 48), np.float32); lit = np.zeros_like(a)
        R = 5 + 17 * (1 - (1 - t) ** 2.2)
        ang = np.arctan2((yy - cy) / 0.55, xx - cx); rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.55) ** 2)
        lobes = 0.6 + 0.4 * np.sin(5 * ang + i * 0.7)
        cloud = np.exp(-(rr / R) ** 2 * 1.5) * lobes * (1.0 if i < 5 else 1 - (i - 4) / 4.0); a += cloud; lit += 0.35 * cloud * np.clip(-(yy - cy) / R, 0, 1)
        for g0, v, sz in grit:
            r_ = R * v * 1.25; x = cx + r_ * math.cos(g0); y = cy - 4 - 10 * v * t + 0.5 * r_ * math.sin(g0) + 9 * t * t
            if 0 <= x < 48 and 0 <= y < 48: a += 0.9 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * (1 - 0.5 * t)
        o = np.clip(a, 0, 1); l = np.clip(lit, 0, 1)
        r = (176 + 60 * l) * o; g = (138 + 52 * l) * o; b = (80 + 36 * l) * o
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * np.clip(o * 1.6, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def crossed_swords(n=23):
    """Frenzied Charge v6 (390) slot 0 (user: swords less distinct - glowy / wispy - less dramatic, not as high, fewer
    swords and shorter; swords FALL in different orientations, then the crossed swords appear and stay longest, with
    Fury's fire sound as they appear): 40x40 additive red glow (drawn at 4x, blurred into a soft core + wide halo, with
    a slow flicker so it reads as wisps, not metal).  Frames: sword 1 falls tilted -35 deg (0-2), sword 2 falls tilted
    +40 deg (3-5), crossed swords fade in with a soft flare (6-7), hold (8-13), fade (14-16).  2 ticks/frame (f18=1)
    -> the crossed swords appear ~0.48 s in (DUALFA_FRENZY.WAV puts FireStrt there)."""
    from PIL import ImageFilter
    U = 4; CW = CH = 40; frames = []; rnd = random.Random(3906)
    def sword_mask(ang_deg, ox, oy, L=11.0):
        im = Image.new("L", (CW * U, CH * U), 0); dr = ImageDraw.Draw(im)
        a = math.radians(ang_deg - 90); ca, sa = math.cos(a), math.sin(a)          # 0 deg = point up
        def P(u, v): return ((CW / 2 + ox + u * ca - v * sa) * U, (CH / 2 + oy + u * sa + v * ca) * U)
        dr.polygon([P(-3.5, -1.3), P(L - 3, -1.3), P(L, 0), P(L - 3, 1.3), P(-3.5, 1.3)], fill=255)   # blade
        dr.polygon([P(-4.3, -4.2), P(-3.3, -4.2), P(-3.3, 4.2), P(-4.3, 4.2)], fill=200)               # guard
        dr.polygon([P(-8.5, -0.7), P(-4.3, -0.7), P(-4.3, 0.7), P(-8.5, 0.7)], fill=170)               # grip
        return im
    def glow(mask, k, a):
        core = np.array(mask.filter(ImageFilter.GaussianBlur(0.55 * U)).resize((CW, CH), Image.LANCZOS)).astype(np.float32) / 255
        halo = np.array(mask.filter(ImageFilter.GaussianBlur(2.2 * U)).resize((CW, CH), Image.LANCZOS)).astype(np.float32) / 255
        yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
        wisp = 0.75 + 0.25 * np.sin(xx * 0.55 + yy * 0.35 + k * 1.7) * np.sin(yy * 0.4 - k * 1.1)             # slow flicker = wisps
        return (core * 1.25 + halo * 0.75) * wisp * a, core * wisp * a
    seq = []                                                                                                   # v7: three falling swords at clearly different angles / spots
    for ang, x0 in ((-65, -5), (20, 4), (70, -1)):
        for k in range(4): seq.append([(ang, x0, -9 + 4.5 * k, (0.5, 0.9, 0.85, 0.45)[k], 1)])        # v8: 4 frames per sword (a bit slower)
    cross_a = [0.5, 1.0, 0.95, 0.9, 0.9, 0.85, 0.85, 0.8, 0.55, 0.32, 0.14]
    for k, a in enumerate(cross_a): seq.append([(-45, 0, 0, a, 0), (45, 0, 0, a, 0)])
    for k, parts in enumerate(seq):
        I = np.zeros((CH, CW), np.float32); H = np.zeros((CH, CW), np.float32)
        for ang, ox, oy, a, falling in parts:
            m = sword_mask(ang, ox, oy)
            if falling:                                                                                        # motion streak upward
                for st, f in ((3, 0.45), (6, 0.2)): m = Image.fromarray(np.maximum(np.array(m), (np.array(sword_mask(ang, ox, oy - st)) * f).astype(np.uint8)))
            g, c = glow(m, k, a); I = np.maximum(I, g); H = np.maximum(H, c)
        if k == 12:                                                                                            # soft flare as the cross appears
            yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32); I = np.maximum(I, np.exp(-((xx - 20) ** 2 + (yy - 20) ** 2) / (2 * 4.0 ** 2)) * 0.35)
        o = np.clip(I, 0, 1); w = np.clip(H * 1.2 - 0.35, 0, 1)
        r = (200 + 55 * w) * o; g_ = (30 + 120 * w) * o; b = (20 + 70 * w) * o
        frames.append(Image.fromarray(np.dstack([r, g_, b, 255 * (o > 0.03)]).astype(np.uint8), "RGBA"))
    return frames


def fireball_small(size=112):
    """Implosion v3 (389) hail impact slot 2 (2026-10-14): FIREBALL's own explosion (EFFECTS\EXPLBIG.ILB 0-29, 274x258,
    keyed, drawMode 514) scaled down to fit `size` px.  The full-size sequence as a HAIL impact crashed the game: a
    ~260-px impact sprite spans many map fields and leaves a dangling entry in a field's sprite list (HSEPack draw loop
    0x5560D68F)."""
    lib = ilbcodec.read(open(os.path.join(GAME, "Images", "Effects", "EXPLBIG.ILB"), "rb").read()); out = []
    for k in range(30):
        im, r = raw_pixels(lib, k); sc = size / max(im.size)
        sm = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
        a = np.array(sm).astype(np.float32); a[:, :, 3] = np.where(a[:, :, 3] > 110, 255, 0)
        out.append(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


def _sand_swirl_parts(seed=1406, n=260):
    rnd = random.Random(seed)
    return [(rnd.uniform(14, 92), rnd.uniform(0, 6.283), rnd.choice((3, 3, 4)), rnd.random(), rnd.uniform(1.0, 1.9)) for _ in range(n)]   # v5: 3-4 turns per loop = rapid spin


def _sand_swirl_frame(parts, i, P, keep=1.0, rscale=1.0):
    """Sandstorm swirl frame (224x160): sand grains + Swarm-like streak motes orbiting the area centre on flattened
    ellipses (y x 0.55); m whole turns per P frames -> seamless loop."""
    W_, H_ = 224, 160; cx, cy = 112.0, 92.0; yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32)
    a = np.zeros((H_, W_), np.float32); lit = np.zeros_like(a)
    for r, a0, m, sel, sz in parts:
        if sel > keep: continue
        ang = a0 + 2 * math.pi * m * i / P; rr = r * rscale
        x = cx + rr * math.cos(ang); y = cy + 0.55 * rr * math.sin(ang) - 10 * (1 - rr / 92.0)
        if not (3 < x < W_ - 3 and 3 < y < H_ - 3): continue
        tx, ty = -math.sin(ang), 0.55 * math.cos(ang)                                      # v5: every mote = a short glowing comet along the orbit (Swarm-like)
        u = (xx - x) * tx + (yy - y) * ty; v = (xx - x) * (-ty) + (yy - y) * tx
        core = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (sz * 0.7) ** 2))
        tail = np.exp(-(u * u) / (2 * np.where(u <= 0, 6.0, 0.8) ** 2) - (v * v) / (2 * 0.8 ** 2)) * 0.55
        g = np.maximum(core, tail)
        a = np.maximum(a, g); lit = np.maximum(lit, core)
    o = np.clip(a, 0, 1); l = np.clip(lit, 0, 1)
    r_ = (150 + 105 * l) * o; g_ = (98 + 92 * l) * o; b_ = (44 + 70 * l) * o                # glowing brown -> hot sand-white at the cores
    return Image.fromarray(np.dstack([r_, g_, b_, 255 * (o > 0.05)]).astype(np.uint8), "RGBA")


def sand_swirl_rise(n=8, P=12):
    parts = _sand_swirl_parts(); return [_sand_swirl_frame(parts, i, P, keep=(i + 1) / n, rscale=0.5 + 0.5 * (i + 1) / n) for i in range(n)]


def sand_swirl_loop(P=12):
    parts = _sand_swirl_parts(); return [_sand_swirl_frame(parts, i, P) for i in range(P)]


def sand_swirl_end(delay=11, n=8, P=12):
    parts = _sand_swirl_parts()
    return [Image.new("RGBA", (4, 4), (0, 0, 0, 0)) for _ in range(delay)] + [_sand_swirl_frame(parts, P + j, P, keep=1.0 - (j + 1) / (n + 0.5), rscale=1.0 + 0.25 * (j + 1) / n) for j in range(n)]


def implosion_seq():
    """Implosion v6 (389) driver slot 3 (user: ring not angled right, more dramatic / orange / brighter, explosion right
    after the ring with no orb, and Fireball's BIG explosion): ONE sequence on a 240x256 canvas (content kept under 256 px
    wide - every crash so far came from sprites 274-280 px wide; 224 wide and 300 tall both work).
      14 ring frames: 36 glowing orange comets (white-hot cores, tails trailing along the spin) on a ring flattened to
         the battlefield's angle (y 0.48), spinning faster as they rush in from R 108 to 10, with a hot core glow
         swelling at the centre;
      29 explosion frames: Fireball's EXPLBIG 1-29 at 0.87x (frame 0 is the small orb - skipped, so the ring collapses
         straight into the big flash), the outer glow faded out before the canvas edge so nothing looks clipped."""
    CW, CH = 240, 256; cx, cy = 120, 128; frames = []
    yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    def ring_pos(t, k):
        R = 98 * (1 - t) ** 1.3 + 10; ang = 2 * math.pi * k / 36 + 1.6 * t * t
        return cx + R * math.cos(ang), cy + 0.48 * R * math.sin(ang)
    for i in range(14):
        t = i / 13.0
        I = np.exp(-(((xx - cx) / (8 + 14 * t)) ** 2 + ((yy - cy) / (5 + 8 * t)) ** 2)) * (0.2 + 0.9 * t ** 1.5)      # the core swelling
        for k in range(36):
            x, y = ring_pos(t, k); sz = 3.2 + 1.2 * t
            I = np.maximum(I, np.exp(-((xx - x) ** 2 + ((yy - y) / 0.8) ** 2) / (2 * sz * sz)) * 1.15)
            for gh, f in ((0.03, 0.55), (0.06, 0.35), (0.10, 0.18)):                                          # the comet tail
                if t - gh < 0: continue
                gx, gy = ring_pos(t - gh, k)
                I = np.maximum(I, np.exp(-((xx - gx) ** 2 + ((yy - gy) / 0.8) ** 2) / (2 * (sz * 0.8) ** 2)) * f)
        I = np.clip(I, 0, 1.2)
        w = np.clip((I - 0.55) / 0.6, 0, 1)                                                                    # white-hot above ~0.55
        r = 255 * np.ones_like(I); g = 120 + 135 * w; b = 30 + 200 * w ** 1.5
        a = 255 * np.clip(I * 1.4, 0, 1)
        frames.append(Image.fromarray(np.dstack([r, g, b, a]).astype(np.uint8), "RGBA"))
    edge = np.clip((118 - np.sqrt((xx - cx) ** 2 + ((yy - cy) * 0.94) ** 2)) / 22.0, 0, 1)                    # soft falloff before the canvas edge
    xl = ilbcodec.read(open(os.path.join(GAME, "Images", "Effects", "EXPLBIG.ILB"), "rb").read())
    for k in range(1, 30):
        im, r = raw_pixels(xl, k); im = im.resize((int(im.width * 0.87), int(im.height * 0.87)), Image.LANCZOS); can = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        can.paste(im, (int(cx - im.width / 2), int(cy - im.height * 0.55)), im)
        arr = np.array(can).astype(np.float32); arr[:, :, 3] *= edge; frames.append(Image.fromarray(arr.astype(np.uint8), "RGBA"))
    return frames


def steam_puff(n=10):
    """Steam Power (406) slot 0 v2 (user: the gfx is too subtle): the map-wide cast animation (Fire Mastery's, drawn on
    random visible hexes): a BIG bright steam plume - 48x64, seven billows bursting from a vent, rising, swelling and
    curling, bright white cores, then thinning out.  Additive, blend 100."""
    frames = []; yy, xx = np.mgrid[0:64, 0:48].astype(np.float32); rnd = random.Random(406)
    blobs = [(rnd.uniform(-5, 5), rnd.uniform(0, 1), rnd.uniform(0.75, 1.25)) for _ in range(7)]
    for i in range(n):
        t = i / (n - 1.0); I = np.zeros((64, 48), np.float32)
        for dx, ph, sz in blobs:
            tt = min(1.0, t * 1.1 + 0.18 * ph)
            cy = 58 - 46 * tt; cx = 24 + dx * (0.4 + tt) + 3.5 * math.sin(tt * 5 + ph * 6)
            r = (4.0 + 10.0 * tt) * sz
            I = np.maximum(I, np.exp(-(((xx - cx) / r) ** 2 + ((yy - cy) / (r * 0.85)) ** 2)) * (1 - tt ** 2.2) * 1.15)
        vent = np.exp(-(((xx - 24) / 5.0) ** 2 + ((yy - 59) / 2.5) ** 2)) * (1 - t) * 0.9
        v = np.clip(np.maximum(I, vent), 0, 1)
        rgb = np.dstack([230 * v + 25 * v * v, 236 * v + 19 * v * v, 250 * v + 5 * v * v])
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.03)]).astype(np.uint8), "RGBA"))
    return frames


def bloodboil_seq(n=16):
    """Blood Boil (404) slot 0: 16 frames on Vaporize's 100x120 canvas (anchor -37/-71 = on the unit's body):
    dark-red bubbles swell, rise and pop across the unit's body (each with a bright rim + highlight), while crimson
    steam (Vaporize's SMOKE 40-49 tinted blood-red) boils up from frame 5 on.  Additive 770.  The class-7 hit lands as
    the sequence ends = at the height of the boil."""
    sm = ilbcodec.read(open(os.path.join(GAME, "Images", "SMOKE.ILB"), "rb").read())
    CW, CH = 100, 120; frames = []; yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32)
    rnd = random.Random(404)
    bubbles = [(rnd.uniform(28, 72), rnd.uniform(48, 92), rnd.uniform(4.5, 8.5), rnd.randint(0, 9), rnd.uniform(1.5, 3.0)) for _ in range(14)]
    for i in range(n):
        R = np.zeros((CH, CW), np.float32); G = np.zeros_like(R)
        for bx, by, br, t0, rise in bubbles:                                                               # bubbles: grow, rise, pop
            age = i - t0
            if age < 0 or age > 6: continue
            r = br * min(1.0, (age + 1) / 3.0) * (1.25 if age == 6 else 1.0); y = by - rise * age
            d = np.sqrt((xx - bx) ** 2 + (yy - y) ** 2)
            if age == 6:                                                                                   # pop = a bright broken ring
                ring = np.exp(-((d - r) ** 2) / 1.2) * 0.9; R = np.maximum(R, ring); G = np.maximum(G, ring * 0.35)
                continue
            body = np.clip(1 - d / r, 0, 1) ** 0.6 * 0.55
            rim = np.exp(-((d - r * 0.9) ** 2) / 0.9) * 0.9
            hi = np.exp(-(((xx - bx + r * 0.35) ** 2 + (yy - y + r * 0.35) ** 2) / (0.25 * r * r + 0.5))) * 0.9
            R = np.maximum(R, np.maximum(body, rim)); G = np.maximum(G, np.maximum(rim * 0.25, hi * 0.8))
        if i >= 5:                                                                                         # crimson steam boiling up
            k = 40 + min(9, i - 5); im, r = raw_pixels(sm, k)
            a = np.array(im.resize((CW, CH)).convert("RGBA")).astype(np.float32)
            v = np.clip(a[:, :, :3].max(2) / 255.0 * (a[:, :, 3] / 255.0) * (2.7 if i < 13 else 2.7 * (1 - (i - 12) / 4.0)), 0, 1)
            R = np.maximum(R, v * 0.95); G = np.maximum(G, v * 0.1)
        R = np.clip(R, 0, 1); G = np.clip(G, 0, 1)
        rgb = np.clip(np.dstack([235 * R + 255 * G, 30 * R + 190 * G, 25 * R + 170 * G]), 0, 255)
        o = np.maximum(R, G)
        frames.append(Image.fromarray(np.dstack([rgb, 255 * (o > 0.03)]).astype(np.uint8), "RGBA"))
    return frames


def scald_seq():
    """Scald (405) slot 0 (user: like Geyser but way smaller, it doesn't lift the unit - it douses it in steam coming
    from the ground; a hybrid of Geyser and Vaporize): 14 frames on Vaporize's own 100x120 canvas (anchor -37/-71, so
    it sits on the unit exactly like Vaporize): frames 0-3 = Geyser's ground burst (Storm1 1-4) shrunk to ~0.3 and
    whitened, at the unit's feet; frames 4-13 = Vaporize's smoke (SMOKE 40-49) turned to white-blue STEAM billowing up
    round the unit while the burst fades.  Additive (770): black is transparent.  A class-7 hit lands when this
    sequence reaches its last frame."""
    st = ilbcodec.read(open(os.path.join(GAME, "Images", "Effects", "Storm1.ILB"), "rb").read())
    sm = ilbcodec.read(open(os.path.join(GAME, "Images", "SMOKE.ILB"), "rb").read())
    CW, CH = 100, 120; base = (50, 104); frames = []
    def steamify(im, gain):
        a = np.array(im.convert("RGBA")).astype(np.float32)
        lum = a[:, :, :3].max(2) / 255.0 * (a[:, :, 3] / 255.0)
        v = np.clip(lum * gain, 0, 1)
        rgb = np.dstack([215 * v + 30 * v * v, 225 * v + 30 * v * v, 245 * v + 10 * v * v])
        return Image.fromarray(np.dstack([rgb, 255 * (v > 0.03)]).astype(np.uint8), "RGBA")
    bursts = []
    for k in (1, 2, 3, 4):
        im, r = raw_pixels(st, k); bb = im.getbbox(); c = im.crop(bb); sc = 0.3
        c = c.resize((max(1, int(c.width * sc)), max(1, int(c.height * sc))), Image.LANCZOS)
        bursts.append(steamify(c, 1.3))
    yy, xx = np.mgrid[0:CH, 0:CW].astype(np.float32); rnd = np.random.RandomState(405)
    noise = rnd.rand(CH // 4 + 2, CW // 4 + 2).astype(np.float32)
    for i in range(14):
        # a turbulent steam JET shooting up from the ground (frames 0-6), spreading into Vaporize's smoke as steam
        jet = np.zeros((CH, CW), np.float32)
        if i < 8:
            hgt = min(1.0, (i + 1) / 4.0) * 78; fade = 1.0 if i < 5 else 1 - (i - 4) / 4.0
            up = np.clip((base[1] - yy) / max(1.0, hgt), 0, 1.2) * (yy <= base[1])
            width = 5.0 + 11.0 * up
            wob = 3.0 * np.sin(yy * 0.21 + i * 1.3) * up
            nz = np.array(Image.fromarray((noise * 255).astype(np.uint8)).resize((CW, CH), Image.BICUBIC).transform((CW, CH), Image.AFFINE, (1, 0, 0, 0, 1, (i * 9) % CH))) / 255.0
            jet = np.exp(-((xx - base[0] - wob) / width) ** 2) * np.clip((1.0 - up) * 3.5, 0, 1) * (yy <= base[1]) * (0.55 + 0.6 * nz) * fade
            jet *= np.clip((base[1] + 2 - yy) / 6.0, 0, 1)
            pool = np.exp(-(((xx - base[0]) / 16.0) ** 2 + ((yy - base[1]) / 4.0) ** 2)) * fade * 0.8   # the hot spot on the ground
            jet = np.maximum(jet, pool)
        st_l = np.zeros((CH, CW), np.float32)
        if i >= 3:
            k = 40 + min(9, i - 3); im, r = raw_pixels(sm, k)
            a = np.array(im.resize((CW, CH)).convert("RGBA")).astype(np.float32)
            st_l = a[:, :, :3].max(2) / 255.0 * (a[:, :, 3] / 255.0) * (2.4 if i < 11 else 2.4 * (1 - (i - 10) / 4.0))
        v = np.clip(np.maximum(jet, st_l), 0, 1)
        rgb = np.dstack([205 * v + 45 * v * v, 220 * v + 35 * v * v, 245 * v + 10 * v * v])
        frames.append(Image.fromarray(np.dstack([rgb, 255 * (v > 0.03)]).astype(np.uint8), "RGBA"))
    return frames


def drought_glow(n=12):
    """Drought (391) slot 1 (2026-10-14): the SUBTLE glow on desertified hexes (drawn per marker by patch_drought_glow_v1.py
    with a pure frame pick, additive 770): 32x24, a faint orange haze shaped like the hex top that breathes slowly,
    with two tiny embers drifting up and fading.  Dim on purpose - additive light, no alpha dithering."""
    frames = []; yy, xx = np.mgrid[0:24, 0:32].astype(np.float32); cx, cy = 16.0, 12.0
    for i in range(n):
        t = i / float(n); b = 0.55 + 0.45 * math.sin(2 * math.pi * t)
        haze = np.exp(-(((xx - cx) / 11.0) ** 2 + ((yy - cy) / 6.0) ** 2) * 1.6) * (0.30 + 0.11 * b)   # v3 (user: slightly more subtle than v2); v1 0.16 was invisible
        a = haze.copy()
        for k, (ex, ph) in enumerate(((10.0, 0.0), (21.0, 0.5))):
            u = (t + ph) % 1.0; ey = 18 - 14 * u; amp = math.sin(math.pi * u) * 0.8
            a += amp * np.exp(-((xx - ex) ** 2 + (yy - ey) ** 2) / (2 * 0.8 ** 2))
        a = np.clip(a, 0, 1)
        r = 255 * a; g = (110 + 60 * a) * a; bl = 25 * a
        frames.append(Image.fromarray(np.dstack([r, g, bl, 255 * (a > 0.015)]).astype(np.uint8), "RGBA"))
    return frames


def city_sparkle(n=12):
    """City enchantment glow (2026-10-14; patch_city_enchant_ui_v1.py v3 draws it on every pad hex of a Fountain of Life
    city): 12 frames 48x48, ALPHA 258/90 - a slow soft blue-white shimmer: four small stars that brighten and fade in
    turn around a faint central glow (one full cycle per 12 frames; the cave steps it slowly)."""
    frames = []; yy, xx = np.mgrid[0:48, 0:48].astype(np.float32); cx, cy = 24.0, 26.0
    stars = [(cx - 9, cy - 8), (cx + 10, cy - 3), (cx - 4, cy + 9), (cx + 6, cy + 11), (cx + 1, cy - 12)]
    for i in range(n):
        t = i / float(n); a = np.zeros((48, 48), np.float32); w = np.zeros_like(a)
        glow = np.exp(-(((xx - cx) ** 2 + ((yy - cy) * 1.3) ** 2) / (2 * 11.0 ** 2))) * (0.42 + 0.12 * math.sin(2 * math.pi * t)); a += glow   # v2: a stronger, wider blue glow like the unit enchantment halo
        for k, (sx, sy) in enumerate(stars):
            ph = (t * 2 * math.pi + k * 2 * math.pi / len(stars)); b = max(0.0, math.sin(ph)) ** 2
            core = np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * 1.1 ** 2)); ray = (np.exp(-((xx - sx) ** 2) / 1.2) * np.exp(-((yy - sy) ** 2) / 30.0) + np.exp(-((yy - sy) ** 2) / 1.2) * np.exp(-((xx - sx) ** 2) / 30.0))
            a += b * (core + 0.55 * ray); w += b * core
        a = np.clip(a, 0, 1); w = np.clip(w, 0, 1)
        r = (40 + 120 * w) * a; g = (110 + 110 * w) * a; bl = 255 * a                                                  # v2 (user): bluer, less white; the glow carries more of the alpha
        frames.append(Image.fromarray(np.dstack([r, g, bl, 255 * a]).astype(np.uint8), "RGBA"))
    return frames


def forge_explosion():
    """Forge Blast v2 gfx (16 frames 128x128, ALPHA 258/90): a proper explosion over the city - a white-hot core, an
    expanding orange fireball with dark rolling smoke, debris and embers flung outward, then the smoke thins."""
    frames = []; rnd = random.Random(1374); N = 16; SZ = 128
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, cy = 64.0, 72.0
    debris = [(rnd.uniform(0, 6.28), rnd.uniform(2.5, 6.0), rnd.uniform(1.0, 2.0)) for _ in range(44)]
    puffs = [(rnd.uniform(0, 6.28), rnd.uniform(0.5, 1.0), rnd.uniform(9, 16)) for _ in range(12)]
    for i in range(N):
        t = i / (N - 1.0); fire = np.zeros((SZ, SZ), np.float32); heat = np.zeros_like(fire); smoke = np.zeros_like(fire)
        R = 10 + 40 * min(1.0, i / 6.0); life = 1.0 if i <= 7 else max(0.0, 1 - (i - 7) / 7.0)
        ball = np.exp(-(((xx - cx) ** 2 + ((yy - cy + 6 * t) * 1.15) ** 2) / (2 * R * R)) ** 1.3)
        fire += life * ball; heat += life * ball * (0.75 - 0.55 * t) * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2)) / (2 * (R * 0.45) ** 2))   # white-hot only at the core, orange outside
        if i <= 2: fl = 1 - i / 2.0; fire += 1.5 * fl * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 14 ** 2)); heat += 1.5 * fl
        for a, v, sz in debris:
            x = cx + math.cos(a) * v * 3.2 * i; y = cy - abs(math.sin(a)) * v * 5.0 * i + 0.8 * i * i
            if 0 <= x < SZ and 0 <= y < SZ: g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)); fire += (1 - 0.5 * t) * g; heat += 0.4 * g
        for a, v, sz in puffs:
            r = (R + 8) * v * (1 + 0.6 * t); x = cx + r * math.cos(a); y = cy - 10 - 26 * t + 0.5 * r * math.sin(a)
            smoke += (0.35 + 0.65 * min(1.0, i / 5.0)) * (1 - 0.6 * t) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (sz * (1 + t)) ** 2))
        f = np.clip(fire, 0, 1); hh = np.clip(heat / np.maximum(fire, 1e-3), 0, 1); s_ = np.clip(smoke, 0, 1)
        r = 255 * f; g = (70 + 175 * hh) * f; b = (10 + 230 * hh * hh) * f
        alpha = np.clip(f + s_ * 0.85, 0, 1)
        r = r * (1 - s_ * (1 - f)) + 34 * s_ * (1 - f); g = g * (1 - s_ * (1 - f)) + 28 * s_ * (1 - f); b = b * (1 - s_ * (1 - f)) + 26 * s_ * (1 - f)
        frames.append(Image.fromarray(np.dstack([r, g, b, 255 * alpha]).astype(np.uint8), "RGBA"))
    return frames


def oil_tile_v1(n=5):
    """(v3 solid pool, kept for reference)"""
    return []


def oil_tile(n=5):
    """Oil Spring v5 tiles (user 2026-10-14: 'heavily splattered over the terrain with some base terrain showing through,
    each hex different'): 5 variants, 75x91 like the Ooze mud tiles (hex blob area 11..62 / 48..87, image top-left at
    HXtoHP - (16,48)).  Each variant = a dense cluster of irregular black splats (big central blobs, mid-size blobs,
    droplets) with gaps between them, confined to the hex, glossy highlights on the bigger ones; fully opaque ink."""
    frames = []; W_, H_ = 75, 91
    yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32); cx, cy = 36.5, 67.5
    for k in range(n):
        rnd = random.Random(2200 + 37 * k)
        hexmask = (((xx - cx) / 25.5) ** 2 + ((yy - cy) / 19.5) ** 2) <= 1.0
        ink = np.zeros((H_, W_), np.float32); gloss = np.zeros_like(ink)
        blobs = []
        for _ in range(3):   blobs.append((rnd.uniform(-16, 16), rnd.uniform(-11, 11), rnd.uniform(7.0, 10.0), rnd.uniform(0.55, 0.8)))   # big pools, spread out so terrain shows between them
        for _ in range(11):  blobs.append((rnd.uniform(-22, 22), rnd.uniform(-16, 16), rnd.uniform(3.0, 5.5), rnd.uniform(0.5, 0.9)))  # mid splats
        for _ in range(34):  blobs.append((rnd.uniform(-24, 24), rnd.uniform(-18, 18), rnd.uniform(1.0, 2.8), rnd.uniform(0.6, 1.0)))  # droplets
        for bx, by, rad, sq in blobs:
            a0 = rnd.uniform(0, 6.28); w1, w2 = rnd.uniform(0.08, 0.2), rnd.uniform(0.05, 0.12)
            dx, dy = xx - (cx + bx), yy - (cy + by)
            ang = np.arctan2(dy / sq, dx); rr = np.sqrt(dx * dx + (dy / sq) ** 2)
            edge = rad * (1 + w1 * np.sin(3 * ang + a0) + w2 * np.sin(7 * ang + 2 * a0))
            b = np.clip((edge - rr) / 1.2, 0, 1); ink = np.maximum(ink, b)
            if rad > 6: gloss = np.maximum(gloss, b * np.exp(-((dx + rad * 0.35) ** 2 / (rad * 0.9) ** 2 + (dy + rad * 0.3) ** 2 / (rad * 0.35) ** 2)) * 0.6)
        ink *= hexmask; gloss *= hexmask
        rr = (12 + 115 * gloss) * ink; gg = (9 + 75 * gloss) * ink; bb = (6 + 40 * gloss) * ink
        frames.append(Image.fromarray(np.dstack([rr, gg, bb, 255 * np.clip(ink * 1.8, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def oil_glob():
    """Oil Spring v3 slot 0 (6 frames 32x32, alpha 258/90): the falling oil glob - a wobbling black drop with a glint
    (replaces Ooze's BALLS 23-28 projectile)."""
    frames = []; yy, xx = np.mgrid[0:32, 0:32].astype(np.float32)
    for i in range(6):
        p = i / 6.0 * 6.28; a = 1 + 0.18 * math.sin(p); b = 1 / a
        body = np.clip((1.0 - np.sqrt(((xx - 16) / (7.5 * a)) ** 2 + ((yy - 17) / (9.0 * b)) ** 2)) / 0.12, 0, 1)
        tail = np.clip((1.0 - np.sqrt(((xx - 16) / 2.2) ** 2 + ((yy - 7) / 7.0) ** 2)) / 0.2, 0, 1) * (yy < 14)
        o = np.clip(body + tail, 0, 1); glint = np.exp(-(((xx - 13) / 2.0) ** 2 + ((yy - 13) / 1.6) ** 2)) * 0.8
        frames.append(Image.fromarray(np.dstack([(16 + 120 * glint) * o, (12 + 80 * glint) * o, (8 + 45 * glint) * o, 255 * np.clip(o * 1.8, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def oil_trail():
    """Oil Spring v3 slot 1 (1 frame 32x32): the drip trail behind the glob."""
    yy, xx = np.mgrid[0:32, 0:32].astype(np.float32)
    o = np.zeros((32, 32), np.float32)
    for y0, sz in ((8, 1.6), (14, 2.0), (21, 2.4), (27, 1.4)):
        o += np.exp(-(((xx - 16) / sz) ** 2 + ((yy - y0) / (sz * 1.6)) ** 2))
    o = np.clip(o, 0, 1)
    return [Image.fromarray(np.dstack([18 * o, 13 * o, 9 * o, 255 * np.clip(o * 1.6, 0, 1)]).astype(np.uint8), "RGBA")]


def oil_hit():
    """Oil Spring v3 slot 2 (5 frames 64x64): the splash where a glob lands - a dark crown of droplets flying up and out,
    collapsing into a spreading smear."""
    frames = []; rnd = random.Random(1140); yy, xx = np.mgrid[0:64, 0:64].astype(np.float32); cx, cy = 32.0, 36.0
    drops = [(rnd.uniform(0, 6.28), rnd.uniform(2.0, 4.0), rnd.uniform(1.2, 2.2)) for _ in range(16)]
    for i in range(5):
        t = i / 4.0; o = np.zeros((64, 64), np.float32); g = np.zeros_like(o)
        R = 6 + 16 * t
        pool = np.exp(-((((xx - cx) / R) ** 2 + ((yy - cy) / (R * 0.5)) ** 2) ** 2.0) * 1.2) * (0.5 + 0.5 * t); o += pool
        g += 0.3 * pool * np.exp(-(((xx - cx + 4) / (R * 0.5)) ** 2 + ((yy - cy - 1) / (R * 0.2)) ** 2) * 2.5)
        for a, v, sz in drops:
            x = cx + math.cos(a) * v * 3.5 * i; y = cy - 2 - abs(math.sin(a)) * v * 4.5 * i + 1.6 * i * i
            if 0 <= x < 64 and 0 <= y < 64 and y < cy + 4: o += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * (1 - 0.3 * t)
        o = np.clip(o, 0, 1); g = np.clip(g, 0, 1)
        frames.append(Image.fromarray(np.dstack([(16 + 100 * g) * o, (11 + 65 * g) * o, (7 + 35 * g) * o, 255 * np.clip(o * 1.8, 0, 1)]).astype(np.uint8), "RGBA"))
    return frames


def ember_ray():
    """Ashes to Ashes slot 0 (4 frames 32x32 additive): the ray head - a smouldering ember ball, dark red core with
    orange flicker and sparks."""
    frames = []; yy, xx = np.mgrid[0:32, 0:32].astype(np.float32); rnd = random.Random(3531)
    for i in range(4):
        d2 = (xx - 15.5) ** 2 + (yy - 15.5) ** 2
        core = np.exp(-d2 / 18.0) * (0.85 + 0.15 * math.sin(i * 1.6)); halo = np.exp(-d2 / 90.0) * 0.5
        f = np.clip(core + halo, 0, 1)
        for k in range(6):
            x = 15.5 + rnd.uniform(-9, 9); y = 15.5 + rnd.uniform(-9, 9); f += 0.8 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.6)
        f = np.clip(f, 0, 1)
        rgba = np.dstack([255 * f, (40 + 90 * core) * f, 8 * f, np.where(f > 0.03, 255, 0)]).astype(np.uint8)
        frames.append(Image.fromarray(rgba, "RGBA"))
    return frames


def big_boulder(n=4, R=11.0):
    """Hurl Boulder (365) hail slot 0: a lumpy grey-brown boulder (64x64, ~22 px across), lit from the upper left,
    with dark cracks; the 4 frames rotate it a quarter turn each so it tumbles in flight."""
    rnd = random.Random(3650); lumps = [R * rnd.uniform(0.82, 1.08) for _ in range(11)]
    cracks = [(rnd.uniform(0, 6.28), rnd.uniform(0.3, 0.9)) for _ in range(4)]
    yy, xx = np.mgrid[0:64, 0:64].astype(np.float32); out = []
    for f in range(n):
        rot = f * math.pi / 2 / n * 4 / 4 * 1.0 + f * 0.5
        dx, dy = xx - 32, yy - 32; ang = np.arctan2(dy, dx) - rot; rr = np.hypot(dx, dy)
        idx = (ang % (2 * math.pi)) / (2 * math.pi) * 11; i0 = np.floor(idx).astype(int) % 11; fr = idx - np.floor(idx)
        L = np.array(lumps, np.float32); edge = L[i0] * (1 - fr) + L[(i0 + 1) % 11] * fr
        inside = rr <= edge
        nz = np.clip(1 - rr / edge, 0, 1); shade = 0.55 + 0.45 * np.clip((-dx - dy) / (edge * 1.4) + 0.4 * nz, -0.6, 1)
        grain = np.array([[rnd.uniform(-0.08, 0.08) for _ in range(64)] for _ in range(64)], np.float32)
        v = np.clip(shade + grain, 0.2, 1.1)
        r, g, b = 128 * v, 116 * v, 100 * v
        a = np.where(inside, 255, 0).astype(np.float32)
        im = Image.fromarray(np.dstack([r * inside, g * inside, b * inside, a]).astype(np.uint8), "RGBA"); dr = ImageDraw.Draw(im)
        for c0, l in cracks:
            c = c0 + rot; x0, y0 = 32 + 2 * math.cos(c), 32 + 2 * math.sin(c); x1, y1 = 32 + R * l * math.cos(c + 0.3), 32 + R * l * math.sin(c + 0.3)
            dr.line([(x0, y0), (x1, y1)], fill=(52, 44, 38, 255), width=1)
        out.append(im)
    return out


def boulder_dust(n=3):
    """Hurl Boulder (365) hail slot 1: the trail behind the flying stone - a soft grey-brown dust puff (32x32)."""
    frames = []; yy, xx = np.mgrid[0:32, 0:32].astype(np.float32); rnd = random.Random(3651)
    for i in range(n):
        a = np.zeros((32, 32), np.float32)
        for _ in range(6):
            x, y, r = 16 + rnd.uniform(-5, 5), 16 + rnd.uniform(-4, 4), rnd.uniform(2.5, 5.0)
            a += 0.45 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r))
        o = np.clip(a, 0, 1)
        frames.append(Image.fromarray(np.dstack([150 * o, 132 * o, 110 * o, 200 * o]).astype(np.uint8), "RGBA"))
    return frames


def rock_impact(n=10):
    """Hurl Boulder (365) hail slot 2: the stone shatters on the hex (64x64) - a grey-brown dust burst rolling out and
    dark rock chunks flung up and out, falling back as the dust thins."""
    frames = []; rnd = random.Random(3652); yy, xx = np.mgrid[0:64, 0:64].astype(np.float32); cx, cy = 32.0, 42.0
    chunks = [(rnd.uniform(-2.9, -0.25), rnd.uniform(0.5, 1.0), rnd.uniform(1.8, 3.2)) for _ in range(12)]
    for i in range(n):
        t = i / (n - 1.0); a = np.zeros((64, 64), np.float32); lit = np.zeros_like(a)
        R = 6 + 20 * (1 - (1 - t) ** 2.0)
        rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.55) ** 2); ang = np.arctan2((yy - cy) / 0.55, xx - cx)
        cloud = np.exp(-(rr / R) ** 2 * 1.4) * (0.65 + 0.35 * np.sin(6 * ang + i)) * (1.0 if i < 6 else 1 - (i - 5) / 5.0)
        a += cloud; lit += 0.3 * cloud * np.clip(-(yy - cy) / R, 0, 1)
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        o = np.clip(a, 0, 1); l = np.clip(lit, 0, 1)
        dust = Image.fromarray(np.dstack([(140 + 60 * l) * o, (126 + 52 * l) * o, (104 + 40 * l) * o, 255 * np.clip(o * 1.5, 0, 1)]).astype(np.uint8), "RGBA")
        im.alpha_composite(dust); dr = ImageDraw.Draw(im)
        for ang0, v, sz in chunks:                                                    # rock chunks on ballistic arcs
            d = 26 * v * t; x = cx + d * math.cos(ang0); y = cy + d * math.sin(ang0) * 0.9 + 30 * t * t
            if t < 0.95 and 0 <= x < 64 and 0 <= y < 64:
                k = sz * (1 - 0.3 * t)
                dr.polygon([(x - k, y), (x - 0.2 * k, y - k), (x + k, y - 0.3 * k), (x + 0.4 * k, y + k)], fill=(96, 86, 74, 255), outline=(40, 34, 30, 255))
        frames.append(im)
    return frames


def gravity_well(n=16):
    """Gravity Well (366) hail slot 2: a well of crushing force on each hex (80x64) - dark violet-brown rings
    contracting inward on the ground, dust and grit pulled into the centre, a dark core pulsing then fading."""
    frames = []; W, H = 80, 64; rnd = random.Random(3661); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); cx, cy = 40.0, 40.0
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.5) ** 2)
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.0), rnd.uniform(0, 1)) for _ in range(36)]
    for i in range(n):
        t = i / (n - 1.0); life = min(1.0, i / 2.0) * (1.0 if i < n - 4 else (n - 1 - i) / 3.0)
        a = np.zeros((H, W), np.float32); glow = np.zeros_like(a)
        for k in range(3):                                                            # three rings contracting inward
            ph = ((t * 2.2 + k / 3.0) % 1.0); R = 34 * (1 - ph)
            ring = np.exp(-((rr - R) / 2.0) ** 2) * (ph ** 0.5) * (1 - ph * 0.3)
            a += 0.9 * ring; glow += 0.5 * ring * ph
        a += 1.1 * np.exp(-(rr / 7.0) ** 2) * (0.75 + 0.25 * math.sin(i * 1.3))      # the dark core
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        o = np.clip(a * life, 0, 1); g = np.clip(glow, 0, 1)
        im.alpha_composite(Image.fromarray(np.dstack([(60 + 90 * g) * o, (40 + 50 * g) * o, (70 + 110 * g) * o, 235 * o]).astype(np.uint8), "RGBA"))
        dr = ImageDraw.Draw(im)
        for ang0, v, ph0 in motes:                                                    # grit spiralling into the centre
            ph = (t * 1.6 + ph0) % 1.0; R = 36 * v * (1 - ph); ang = ang0 + 2.4 * ph
            x = cx + R * math.cos(ang); y = cy + 0.5 * R * math.sin(ang) - 6 * (1 - ph) * v
            if life > 0.2: dr.rectangle([x - 0.6, y - 0.6, x + 0.6, y + 0.6], fill=(176, 150, 120, int(255 * life)))
        frames.append(im)
    return frames


def gravity_field(n=12):
    """Gravity Well (366) slot 3 (v2 10/15): the lingering well on each field hex, a SEAMLESS 12-frame loop (64x40,
    centre (32, 20)) - a faint dark-violet ground ellipse, two rings sliding inward and grit spiralling in, low alpha
    so the units on it stay readable."""
    frames = []; W, H = 64, 40; rnd = random.Random(3667); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); cx, cy = 32.0, 20.0
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.5) ** 2)
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0.5, 1.0), rnd.uniform(0, 1)) for _ in range(18)]
    for i in range(n):
        t = i / float(n)
        a = 0.35 * np.exp(-(rr / 22.0) ** 4); glow = np.zeros_like(a)
        for k in range(2):
            ph = (t + k / 2.0) % 1.0; R = 28 * (1 - ph)
            ring = np.exp(-((rr - R) / 1.8) ** 2) * min(1.0, ph * 4) * min(1.0, (1 - ph) * 3)
            a += 0.55 * ring; glow += 0.6 * ring
        a += 0.45 * np.exp(-(rr / 5.0) ** 2)
        o = np.clip(a, 0, 1); g = np.clip(glow, 0, 1)
        im = Image.fromarray(np.dstack([(50 + 90 * g) * o, (30 + 50 * g) * o, (70 + 120 * g) * o, 200 * o]).astype(np.uint8), "RGBA")
        dr = ImageDraw.Draw(im)
        for ang0, v, ph0 in motes:
            ph = (t + ph0) % 1.0; R = 28 * v * (1 - ph); ang = ang0 + 3.0 * ph
            x = cx + R * math.cos(ang); y = cy + 0.5 * R * math.sin(ang)
            al = int(220 * min(1.0, ph * 4) * min(1.0, (1 - ph) * 4))
            dr.rectangle([x - 0.5, y - 0.5, x + 0.5, y + 0.5], fill=(170, 150, 190, al))
        frames.append(im)
    return frames


def gravity_well_v2(n=20):
    """Gravity Well (366) slot 2 v2 (10/15; user: the initial swirl should be more magical - epic glowing purple
    particles): ADDITIVE (draw 770) 96x80, centre (48, 52).  ~70 glowing violet/magenta motes spiral inward from a
    wide ring, each with a short comet tail; three glowing rings contract on the ground; a violet core builds and
    peaks in a bright white-violet flash at frame 13, then the light collapses into the ground and fades."""
    W, H = 96, 80; cx, cy = 48.0, 52.0; rnd = random.Random(3668); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.5) ** 2)
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0.7, 1.15), rnd.uniform(-0.15, 0.25), rnd.uniform(0.7, 1.3), rnd.uniform(-18, 2)) for _ in range(70)]
    frames = []
    def glow(acc, x, y, r, amp, col):
        g = amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r))
        for c in range(3): acc[..., c] += g * col[c]
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        fade = 1.0 if i < 15 else max(0.0, 1 - (i - 14) / 5.0)
        for k in range(3):                                                            # glowing rings contracting on the ground
            ph = min(1.0, max(0.0, t * 1.5 - k * 0.18)); R = 40 * (1 - ph)
            if 0 < ph < 1:
                ring = np.exp(-((rr - R) / 1.6) ** 2) * math.sin(ph * math.pi) * fade
                acc[..., 0] += ring * 150; acc[..., 1] += ring * 60; acc[..., 2] += ring * 230
        for a0, v, d0, sp, h0 in motes:                                               # spiralling motes with comet tails
            for tail in range(4):
                tt = t - tail * 0.025
                ph = min(1.0, max(0.0, tt * 1.35 * sp + d0))
                if ph <= 0 or ph >= 1: continue
                R = 42 * v * (1 - ph) ** 1.2; ang = a0 + 5.0 * ph
                x = cx + R * math.cos(ang); y = cy + 0.5 * R * math.sin(ang) + h0 * (1 - ph)
                amp = (1.0 if tail == 0 else 0.55 / tail) * math.sin(min(1.0, ph * 3) * math.pi / 2) * fade
                glow(acc, x, y, 1.1 if tail == 0 else 0.9, amp, (210, 110, 255) if tail == 0 else (150, 60, 220))
        core = (t / 0.65) ** 2 if t < 0.65 else max(0.0, 1 - (t - 0.65) / 0.35) ** 1.5      # the core builds, flashes, collapses
        glow(acc, cx, cy, 4 + 6 * core, 1.4 * core, (220, 150, 255))
        if 0.6 < t < 0.8: glow(acc, cx, cy, 14, 0.9 * math.sin((t - 0.6) / 0.2 * math.pi), (255, 220, 255))
        frames.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return frames


def boulder_glow(n=12):
    """Hurl Boulder (365) slot 1 (10/15; user: a brief magical gfx before the boulder is thrown): ADDITIVE 64x64,
    centre (32, 32) = the caster's chest.  Amber-brown earth motes and a few sky-blue air sparks spiral IN over
    frames 0-7, a pale sky-blue flare peaks at frames 8-9 (the throw leaves at tick 18) and fades over 10-11."""
    W = H = 64; cx = cy = 32.0; rnd = random.Random(3653); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.0), rnd.random() < 0.3) for _ in range(34)]
    frames = []
    def glow(acc, x, y, r, amp, col):
        g = amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r))
        for c in range(3): acc[..., c] += g * col[c]
    for i in range(n):
        acc = np.zeros((H, W, 3), np.float32); t = min(1.0, i / 8.0)
        if i < 10:
            for a0, v, air in motes:
                R = 28 * v * (1 - t) ** 1.3; ang = a0 + 3.2 * t
                x = cx + R * math.cos(ang); y = cy + R * math.sin(ang) * 0.8
                glow(acc, x, y, 1.2, 0.9 * min(1.0, 0.3 + i / 3.0), (150, 200, 255) if air else (255, 170, 80))
        core = [0.05, 0.1, 0.15, 0.22, 0.3, 0.4, 0.5, 0.65, 1.0, 0.9, 0.45, 0.15][i]
        glow(acc, cx, cy, 3 + 7 * core, 1.2 * core, (190, 225, 255))
        if i in (8, 9): glow(acc, cx, cy, 15, 0.6 if i == 8 else 0.35, (150, 200, 255))
        frames.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return frames


def boulder_rise(n=18):
    """Hurl Boulder (365) slot 1 v2 (10/15; user: the glow is lame - magic ON the caster and a boulder SHAKING and RISING
    from the ground in front of the caster, then thrown with the existing animation): 96x96, the hex centre at
    (48, 72).  Frames 0-5: earthy-amber + sky-blue motes swirl up round the caster, the ground cracks in front of
    the caster's feet (48, 80) and the boulder's top shows, jittering; frames 6-12: the boulder (the ability's own
    BALLS 7-14 rock, same size as the thrown one) wrenches free and rises, shaking, shedding dirt, to the throw
    point (48, 58); frames 13-14 it hovers there; frame 15 on (= the launch at tick 30) the rock is gone, the magic
    and the dust fade."""
    W = H = 96; gx, gy = 48, 80; ty = 58; rnd = random.Random(3654)
    lib = ilbcodec.read(open(BALLS, "rb").read())
    rocks = []
    for sid in range(7, 15):
        im, r = raw_pixels(lib, sid); rocks.append(im.crop((22, 25, 42, 43)))                     # 20x18 around the rock (centre ~ (9, 8))
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(9, 15), rnd.uniform(0, 1), rnd.random() < 0.35) for _ in range(30)]
    debris = [(rnd.uniform(-6, 6), rnd.uniform(-2.5, -0.5), rnd.uniform(0.6, 1.2)) for _ in range(14)]
    frames = []
    for i in range(n):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        mag = min(1.0, (i + 1) / 4.0) * (1.0 if i < 15 else max(0.0, (17 - i) / 3.0))
        for k, (a0, R, ph0, air) in enumerate(motes):                                            # magic swirling up round the caster
            ph = (i / 12.0 + ph0) % 1.0; a = a0 + 4.0 * ph
            x = 48 + R * math.cos(a); y = 72 - 46 * ph + 0.35 * R * math.sin(a)
            al = int(255 * mag * math.sin(ph * math.pi))
            if al > 10:
                col = (150, 205, 255) if air else (255, 180, 90)
                dr.ellipse([x - 1.6, y - 1.6, x + 1.6, y + 1.6], fill=col[:3] + (al // 3,))
                dr.rectangle([x - 0.5, y - 0.5, x + 0.5, y + 0.5], fill=(255, 245, 220, al))
        crack = min(1.0, (i + 1) / 3.0) * (1.0 if i < 14 else max(0.0, (17 - i) / 3.0))      # the cracked ground / pit in front
        if crack > 0:
            dr.ellipse([gx - 9, gy - 3, gx + 9, gy + 3], fill=(58, 46, 34, int(220 * crack)))
            for a in (0.3, 1.4, 2.5, 3.5, 4.6, 5.6):
                dr.line([(gx + 8 * math.cos(a), gy + 2.7 * math.sin(a)), (gx + 13 * math.cos(a + 0.15), gy + 4.4 * math.sin(a + 0.15))], fill=(48, 38, 28, int(200 * crack)), width=1)
        if i < 15:                                                                                 # the boulder
            if i < 6: cy = gy + 5 - i * 0.6                                                        # top showing, jittering
            elif i < 13: u = (i - 5) / 7.0; cy = (gy + 1.4) + (ty - gy - 1.4) * (1 - (1 - u) ** 2)
            else: cy = ty
            jx = (-1, 1, 0, 1, -1, 0)[i % 6] * (1 if i < 13 else 0); jy = (0, -1, 1, 0)[i % 4] * (1 if i < 13 else 0)
            rk = rocks[i % 8]; ox, oy = int(round(gx + jx - 9)), int(round(cy + jy - 8))
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); layer.alpha_composite(rk, (ox, oy))
            if i < 13:                                                                             # below the ground line it is still buried
                la = layer.load()
                for yy in range(gy + 1, H):
                    for xx in range(W): la[xx, yy] = (0, 0, 0, 0)
            im.alpha_composite(layer)
            if 4 <= i < 14:                                                                        # dirt shed as it rises
                for dx, vy, sz in debris:
                    t = (i - 4) / 3.0
                    x = gx + dx * (1 + 0.3 * t); y = cy + 6 + vy * t * 3 + 2.0 * t * t
                    if y < gy + 3: dr.rectangle([x - sz / 2, y - sz / 2, x + sz / 2, y + sz / 2], fill=(92, 74, 56, 230))
        if 5 <= i < 12:                                                                            # dust puff at the pit as it breaks free
            r = 4 + (i - 5) * 2.2; al = int(130 * (1 - (i - 5) / 7.0))
            dr.ellipse([gx - r * 1.5, gy - r * 0.6, gx + r * 1.5, gy + r * 0.4], fill=(150, 130, 105, al))
        frames.append(im)
    return frames


def leaf_drift(n=3):
    """Overgrowth (383) slots 0-2 (10/15): three single-frame sprites for the donor Air Mastery's map-wide drift
    animation (like Air's MAGIC 160-162, ~200x116, ADDITIVE at low blend) - a loose swirling stream of green leaves,
    a few yellow-green ones, and pale pollen specks along a wide S-curve."""
    W, H = 200, 116; out = []
    for v in range(n):
        rnd = random.Random(3840 + v); im = Image.new("RGBA", (W, H), (0, 0, 0, 255)); dr = ImageDraw.Draw(im)
        ph = v * 1.7
        for k in range(46):                                                                           # leaves along the swirl
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 34 * math.sin(t * 2 * math.pi * 1.2 + ph) + rnd.uniform(-14, 14)
            L = rnd.uniform(4, 8); a = rnd.uniform(0, 6.28); ux, uy = math.cos(a), math.sin(a); px, py = -uy, ux
            g = rnd.choice([(70, 200, 60), (110, 220, 70), (160, 220, 60), (60, 170, 70)])
            br = rnd.uniform(0.55, 1.0); col = tuple(int(c * br) for c in g)
            pts = [(x - ux * L / 2, y - uy * L / 2), (x + px * L * 0.3, y + py * L * 0.3), (x + ux * L / 2, y + uy * L / 2), (x - px * L * 0.3, y - py * L * 0.3)]
            dr.polygon(pts, fill=col + (255,))
            dr.line([pts[0], pts[2]], fill=tuple(int(c * 0.5) for c in col) + (255,))
        for k in range(70):                                                                           # pollen specks
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 34 * math.sin(t * 2 * math.pi * 1.2 + ph) + rnd.uniform(-22, 22)
            c = int(rnd.uniform(120, 230)); dr.point((x, y), fill=(c, c, int(c * 0.6), 255))
        out.append(im)
    return out


def overgrowth_glow(n=12):
    """Overgrowth (383) slot 3 (10/15; user: like Drought, a subtle green hex glow): drawn per marker by
    patch_drought_glow_v1.py v2 (pure frame pick, additive 770) - Drought's drought_glow recoloured: 32x24, a faint
    green haze shaped like the hex top that breathes slowly, with two pale yellow-green pollen glints drifting up."""
    frames = []; yy, xx = np.mgrid[0:24, 0:32].astype(np.float32); cx, cy = 16.0, 12.0
    for i in range(n):
        t = i / float(n); b = 0.55 + 0.45 * math.sin(2 * math.pi * t)
        a = np.exp(-(((xx - cx) / 11.0) ** 2 + ((yy - cy) / 6.0) ** 2) * 1.6) * (0.42 + 0.12 * b)   # v2 (green on grass reads weaker than Drought's orange)
        glint = np.zeros_like(a)
        for ex, ph in ((11.0, 0.25), (20.0, 0.75)):
            u = (t + ph) % 1.0; ey = 18 - 14 * u; amp = math.sin(math.pi * u) * 0.75
            glint += amp * np.exp(-((xx - ex) ** 2 + (yy - ey) ** 2) / (2 * 0.8 ** 2))
        a = np.clip(a, 0, 1); glint = np.clip(glint, 0, 1); tot = np.clip(a + glint, 0, 1)
        r = 60 * a + 200 * glint; g = 200 * a + 235 * glint; bl = 50 * a + 90 * glint
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(bl, 0, 255), 255 * (tot > 0.015)]).astype(np.uint8), "RGBA"))
    return frames


def grass_drift(n=3):
    """World Healer (327) slots 0-2 (10/15): three single-frame sprites for Air Mastery's map-wide drift animation
    (200x116, ADDITIVE at low blend) - a soft stream of green grass blades along a wide S-curve, dew-light motes,
    a few white-gold (Life) and blue droplet (Water) glints."""
    W, H = 200, 116; out = []
    for v in range(n):
        rnd = random.Random(3940 + v); im = Image.new("RGBA", (W, H), (0, 0, 0, 255)); dr = ImageDraw.Draw(im); ph = v * 1.9
        for k in range(55):                                                                           # grass blades
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 30 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-14, 14)
            L = rnd.uniform(5, 10); a = rnd.uniform(-2.4, -0.7); bend = rnd.uniform(-0.5, 0.5)
            g = rnd.choice([(80, 210, 70), (120, 230, 80), (60, 180, 60)]); br = rnd.uniform(0.55, 1.0)
            col = tuple(int(c * br) for c in g) + (255,)
            pts = [(x + L * t2 * math.cos(a + bend * t2), y + L * t2 * math.sin(a + bend * t2)) for t2 in (0, 0.35, 0.7, 1.0)]
            dr.line(pts, fill=col, width=2 if k % 3 == 0 else 1)
        for k in range(26):                                                                           # glints
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 30 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-22, 22)
            col = rnd.choice([(255, 240, 180), (150, 200, 255), (220, 255, 220)])
            dr.ellipse([x - 1, y - 1, x + 1, y + 1], fill=col + (255,))
        out.append(im)
    return out


def dew_veil(n=3):
    """Blessed Dew (326) slots 0-2 (10/15): three single images for Death Mastery's map-wide drift (kind 0, ~200x100,
    centred near (99, 51), ADDITIVE at low blend) - a soft veil of pale blue-white mist with glittering dew drops and
    a few small 4-point sparkles."""
    W, H = 200, 100; out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for v in range(n):
        rnd = random.Random(3920 + v); acc = np.zeros((H, W, 3), np.float32)
        for k in range(14):                                                                           # mist puffs
            x, y, r = rnd.uniform(20, 180), rnd.uniform(25, 75), rnd.uniform(14, 26)
            g = 0.32 * np.exp(-((xx - x) ** 2 + ((yy - y) / 0.6) ** 2) / (r * r))
            for c, cv in enumerate((150, 190, 235)): acc[..., c] += g * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for k in range(40):                                                                           # dew drops
            x, y = rnd.uniform(15, 185), rnd.uniform(18, 82); c = int(rnd.uniform(170, 255))
            dr.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(c, c, 255, 255))
        for k in range(7):                                                                            # sparkles
            x, y = rnd.uniform(25, 175), rnd.uniform(20, 80)
            dr.line([(x - 3, y), (x + 3, y)], fill=(255, 255, 255, 255)); dr.line([(x, y - 3), (x, y + 3)], fill=(255, 255, 255, 255))
        out.append(im)
    return out


def harvest_twinkle(n=9):
    """Bountiful Harvest (325) slot 0 (10/15): the world FX at the caster's capital (Life Mastery's TWINKGR 30-38 role,
    ~54x48, anchor -27/-48 = bottom centre): golden grain motes and a few wheat ears rising and twinkling, green leaf
    glints, fading at the top - additive."""
    W, H = 54, 48; rnd = random.Random(3900); out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    motes = [(rnd.uniform(6, 48), rnd.uniform(0, 1), rnd.uniform(0.7, 1.3), rnd.random() < 0.2) for _ in range(26)]
    for i in range(n):
        t = i / float(n); acc = np.zeros((H, W, 3), np.float32)
        for x0, ph, sp, leaf in motes:
            u = (t * sp + ph) % 1.0; x = x0 + 3 * math.sin(u * 6 + ph * 10); y = 44 - 38 * u
            amp = math.sin(math.pi * u) * (1.0 if (i + int(ph * 9)) % 3 else 1.5)
            g = amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3)
            col = (90, 230, 80) if leaf else (255, 205, 70)
            for c in range(3): acc[..., c] += g * col[c]
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for k in range(3):                                                                            # rising wheat ears
            u = (t + k / 3.0) % 1.0; x = 14 + k * 13; y = 42 - 34 * u; a = int(255 * math.sin(math.pi * u))
            col = (int(230 * a / 255), int(180 * a / 255), int(60 * a / 255), 255)
            dr.line([(x, y + 6), (x, y)], fill=col)
            for g in range(3): dr.point((x - 1, y + g * 2), fill=col); dr.point((x + 1, y + g * 2), fill=col)
        out.append(im)
    return out


def holy_spray(n=8):
    """Holy Water (324) slot 0 (10/15): the per-strike puff drawn along the breath fan (Cold Breath's BOLTS 90-97 role,
    64x64, centre (32, 33), ADDITIVE): a pale blue-white water spray burst - droplets flung outward - with a few
    gold-white holy glints, shrinking and fading over the 8 frames."""
    W = H = 64; cx, cy = 32.0, 33.0; rnd = random.Random(3880); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    drops = [(rnd.uniform(0, 6.28), rnd.uniform(0.4, 1.0), rnd.random() < 0.5) for _ in range(38)]   # v2 (user): half the drops gold
    out = []
    for i in range(n):
        t = i / (n - 1.0); fade = (1 - t) ** 1.2; acc = np.zeros((H, W, 3), np.float32)
        core = 0.9 * fade * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (5 + 6 * t) ** 2))
        for c, cv in enumerate((215, 215, 200)): acc[..., c] += core * cv   # v2: pale gold-white core
        for a, v, holy in drops:
            R = (5 + 20 * t) * v; x = cx + R * math.cos(a); y = cy + R * math.sin(a) * 0.8 + 4 * t * t
            g = fade * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (1.4 if holy else 1.0))
            col = (255, 205, 90) if holy else (180, 220, 255)
            for c in range(3): acc[..., c] += g * col[c] * (1.3 if holy else 1.0)
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def harvest_drift(n=3):
    """Bountiful Harvest (325) slots 0-2 (10/15; user: drift across the whole map like the others): three single
    frames for Death Mastery's map-wide drift (200x116, ADDITIVE at low blend) - a loose S-curved stream of golden
    grain motes, small wheat ears and a few gold coin glints."""
    W, H = 200, 116; out = []
    for v in range(n):
        rnd = random.Random(3960 + v); im = Image.new("RGBA", (W, H), (0, 0, 0, 255)); dr = ImageDraw.Draw(im); ph = v * 2.1
        def path(t): return 10 + 180 * t, 58 + 30 * math.sin(t * 2 * math.pi * 1.1 + ph)
        for k in range(14):                                                                           # wheat ears
            t = rnd.random(); x, y = path(t); y += rnd.uniform(-14, 14); a = rnd.uniform(-2.6, -0.5)
            col = tuple(int(c * rnd.uniform(0.6, 1.0)) for c in rnd.choice(((230, 180, 60), (110, 210, 70)))) + (255,)   # v2: gold or green
            ux, uy = math.cos(a), math.sin(a); dr.line([(x, y), (x + 9 * ux, y + 9 * uy)], fill=col)
            for g in range(3):
                gx, gy = x + (5 + g * 1.6) * ux, y + (5 + g * 1.6) * uy
                dr.ellipse([gx - 1.2, gy - 1.2, gx + 1.2, gy + 1.2], fill=col)
        for k in range(46):                                                                           # grain motes
            t = rnd.random(); x, y = path(t); y += rnd.uniform(-20, 20); c = rnd.uniform(0.55, 1.0)
            gc = (255, 200, 70) if k % 2 else (120, 225, 80)
            dr.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(int(gc[0] * c), int(gc[1] * c), int(gc[2] * c), 255))
        for k in range(7):                                                                            # coin glints
            t = rnd.random(); x, y = path(t); y += rnd.uniform(-16, 16)
            dr.ellipse([x - 2.2, y - 1.4, x + 2.2, y + 1.4], fill=(255, 220, 90, 255)); dr.point((x - 1, y - 0.5), fill=(255, 255, 220, 255))
        out.append(im)
    return out


def harvest_glow(n=24):
    """Bountiful Harvest (325) slot 3 v9 (10/15; user: a bit more subtle and SMOOTHER - it was janky): the vanilla
    PARTICLE.ILB glow dots (green 6-8 / gold 12-14) at a third of the unit size, 24 frames (was 12) so each particle
    rises ~1 px per frame, placed with sub-pixel (bilinear) positioning so it glides, and ~30 % dimmer.  Drawn per frame
    by patch_harvest_v1.py v8 (dx cave on the map's dynamic scene)."""
    lib = ilbcodec.read(PARTICLE); dots = {}
    for sid in (6, 7, 8, 12, 13, 14):
        im, r = raw_pixels(lib, sid); a = np.array(im.convert("RGBA")).astype(np.float32)
        pm = Image.fromarray(np.clip(a[:, :, :3] * (a[:, :, 3:4] / 255.0), 0, 255).astype(np.uint8))
        pm = pm.resize((max(3, pm.width // 3), max(3, pm.height // 3)), Image.LANCZOS)
        dots[sid] = np.array(pm).astype(np.float32) * 0.6
    rnd = random.Random(3986); W, H = 32, 24
    xs_ = [5.0 + k * 22.0 / 10.0 for k in range(11)]; rnd.shuffle(xs_)
    parts = [(xs_[k], k * n / 11.0, k % 2) for k in range(11)]                                       # x, birth frame, gold?
    def splat(acc, d, fx, fy):                                                                       # bilinear sub-pixel placement
        h, w = d.shape[:2]; ix, iy = int(math.floor(fx)), int(math.floor(fy)); ax, ay = fx - ix, fy - iy
        for ox, oy, wt in ((0, 0, (1 - ax) * (1 - ay)), (1, 0, ax * (1 - ay)), (0, 1, (1 - ax) * ay), (1, 1, ax * ay)):
            x0, y0 = ix + ox, iy + oy
            sx0, sy0 = max(0, -x0), max(0, -y0); dx0, dy0 = max(0, x0), max(0, y0)
            ww, hh = min(w - sx0, W - dx0), min(h - sy0, H - dy0)
            if ww > 0 and hh > 0: acc[dy0:dy0 + hh, dx0:dx0 + ww] += d[sy0:sy0 + hh, sx0:sx0 + ww] * wt
    frames = []
    for i in range(n):
        acc = np.zeros((H, W, 3), np.float32)
        for x, birth, gold in parts:
            age = (i - birth) % n; life = 12.0
            if age >= life: continue
            u = age / life; y = 19.0 - 13.0 * u; xx = x + 1.0 * math.sin(u * 5.0 + x)
            sid = (12 if gold else 6) + min(2, int(u * 3))
            d = dots[sid] * (math.sin(math.pi * min(1.0, u * 1.3)) ** 0.8)
            splat(acc, d, xx - d.shape[1] / 2.0, y - d.shape[0] / 2.0)
        acc = np.clip(acc, 0, 255); a = acc.max(axis=2) / 255.0
        frames.append(Image.fromarray(np.dstack([acc[..., 0], acc[..., 1], acc[..., 2], 255 * (a > 0.02)]).astype(np.uint8), "RGBA"))
    return frames


def soul_siphon(n=12):
    """Soul Siphon (340) slot 0 (10/15): drawn at the target, 64x64 additive, anchor -32/-48 (centre (32, 40) = the
    unit's chest): a violet vortex tightening over the target while pale soul wisps are pulled OUT of it, spiralling
    up and away to the top of the frame and fading."""
    W = H = 64; cx, cy = 32.0, 40.0; rnd = random.Random(3400); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    wisps = [(rnd.uniform(0, 6.28), rnd.uniform(0, 1), rnd.uniform(0.8, 1.2)) for _ in range(9)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32); fade = min(1.0, (n - 1 - i) / 3.0 + 0.0) if i > n - 4 else 1.0
        rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.55) ** 2); ang = np.arctan2((yy - cy) / 0.55, xx - cx)
        vort = np.exp(-((rr - (14 - 8 * t)) / 2.2) ** 2) * (0.6 + 0.4 * np.sin(3 * ang + 10 * t)) * 0.7 * fade   # tightening vortex
        for c, cv in enumerate((150, 60, 210)): acc[..., c] += vort * cv
        for a0, ph, sp in wisps:                                                                    # wisps drawn up and out
            for tail in range(5):
                u = ((t * sp + ph) - tail * 0.04) % 1.0
                a = a0 + 4.0 * u; r = 10 * (1 - u) + 3
                x = cx + r * math.cos(a) * 0.8; y = cy - 34 * u + 0.5 * r * math.sin(a)
                amp = math.sin(math.pi * u) * (1.0 if tail == 0 else 0.5 / tail) * fade
                g = amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (1.6 if tail == 0 else 1.1))
                for c, cv in enumerate((220, 200, 255)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def black_droplets(n=3):
    """Black Tide (342) slot 0 (10/15): Earth Mastery's map-wide particle twinkle (as Golden Age's gold_motes, ~20x20,
    3 frames): an ink-dark teal droplet with a faint sickly green rim, swelling and shrinking - additive, so the
    'dark' reads as deep teal glow."""
    out = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32); cx, cy = 10.0, 10.0
    for k, sc in enumerate((0.75, 1.0, 0.85)):
        rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 0.85) ** 2) / sc
        core = np.exp(-(rr / 3.2) ** 2); rim = np.exp(-((rr - 4.4) / 1.0) ** 2) * 0.8
        r = 20 * core + 60 * rim; g = 90 * core + 160 * rim; b = 100 * core + 70 * rim
        a = np.clip(core + rim, 0, 1)
        out.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255), 255 * (a > 0.04)]).astype(np.uint8), "RGBA"))
    return out


def plague_miasma(n=3):
    """Plague (341) slots 0-2 (10/15): three single images for Death Mastery's map-wide drift (kind 0, ~200x100,
    additive): a sickly yellow-green miasma with drifting spore specks and a few black-bodied flies (drawn as dim
    green specks with pale wings - additive can't draw black)."""
    W, H = 200, 100; out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for v in range(n):
        rnd = random.Random(4030 + v); acc = np.zeros((H, W, 3), np.float32)
        for k in range(14):
            x, y, r = rnd.uniform(20, 180), rnd.uniform(25, 75), rnd.uniform(14, 26)
            g = 0.30 * np.exp(-((xx - x) ** 2 + ((yy - y) / 0.6) ** 2) / (r * r))
            for c, cv in enumerate((120, 170, 40)): acc[..., c] += g * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for k in range(45):
            x, y = rnd.uniform(15, 185), rnd.uniform(18, 82); c = rnd.uniform(0.5, 1.0)
            dr.point((x, y), fill=(int(170 * c), int(220 * c), int(60 * c), 255))
        for k in range(8):
            x, y = rnd.uniform(25, 175), rnd.uniform(20, 80)
            dr.ellipse([x - 1, y - 0.6, x + 1, y + 0.6], fill=(60, 90, 30, 255))
            dr.line([(x - 2, y - 1.2), (x - 0.4, y - 0.4)], fill=(190, 210, 190, 255)); dr.line([(x + 2, y - 1.2), (x + 0.4, y - 0.4)], fill=(190, 210, 190, 255))
        out.append(im)
    return out


def soul_linger(n=30):
    """Soul Siphon (340) slot 1 (10/15; user: the hit should LINGER): the kind-0x26 driver's sequence at the target,
    64x64 additive, centre (32, 40), 30 frames x 2 ticks (~2 s): a violet vortex turning slowly over the target with
    pale wisps rising out of it, fading over the last 6 frames."""
    W = H = 64; cx, cy = 32.0, 40.0; rnd = random.Random(3401); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    wisps = [(rnd.uniform(0, 6.28), rnd.uniform(0, 1), rnd.uniform(0.7, 1.2)) for _ in range(8)]
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.55) ** 2); ang = np.arctan2((yy - cy) / 0.55, xx - cx)
    out = []
    for i in range(n):
        t = i / float(n); fade = min(1.0, (n - 1 - i) / 6.0) * min(1.0, (i + 1) / 3.0)
        acc = np.zeros((H, W, 3), np.float32)
        vort = np.exp(-((rr - 10.0) / 2.6) ** 2) * (0.55 + 0.45 * np.sin(3 * ang - 6.28 * t * 2)) * 0.65 * fade
        vort += np.exp(-(rr / 4.0) ** 2) * 0.35 * fade
        for c, cv in enumerate((150, 60, 210)): acc[..., c] += vort * cv
        for a0, ph, sp in wisps:
            u = (t * 2.0 * sp + ph) % 1.0; a = a0 + 3.0 * u; r = 8 * (1 - u) + 2
            x = cx + r * math.cos(a) * 0.8; y = cy - 26 * u + 0.5 * r * math.sin(a)
            g = math.sin(math.pi * u) * fade * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.5)
            for c, cv in enumerate((215, 200, 255)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def soul_mote(n=6):
    """Soul Siphon (340) slot 2 (10/15): the kind-0x1F mote flying target -> caster, 22x22 additive, looping: a pale
    lilac-white soul wisp with a soft violet core and a short flickering tail."""
    W = H = 22; cx, cy = 11.0, 11.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for i in range(n):
        t = i / float(n); acc = np.zeros((H, W, 3), np.float32)
        core = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / 3.0) * (0.85 + 0.15 * math.sin(6.28 * t))
        halo = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / 14.0) * 0.45
        for c, (cv, hv) in enumerate(((235, 150), (225, 70), (255, 220))): acc[..., c] += core * cv + halo * hv
        for k in range(3):                                                                           # flickering tail
            tx = cx + 2.0 + k * 2.2 + 0.6 * math.sin(6.28 * t + k); ty = cy + 1.4 * math.sin(6.28 * t * 2 + k)
            g = np.exp(-((xx - tx) ** 2 + (yy - ty) ** 2) / 1.6) * (0.5 - k * 0.12)
            for c, cv in enumerate((190, 120, 255)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def silver_motes(n=3):
    """Nimue's Favour (398) slot 0 v2 (user: more blue, more of a water effect): Earth Mastery's map-wide particle
    (20x20, 3 frames, additive) is now a falling water droplet hitting a lake - frame 0 a bright blue teardrop, frame 1
    the drop landing in a small ripple ring with a splash fleck, frame 2 a wider, fainter double ripple."""
    out = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32); cx, cy = 10.0, 12.0
    for k in range(n):
        acc = np.zeros((20, 20), np.float32); hi = np.zeros((20, 20), np.float32)
        if k == 0:                                                         # teardrop: round bottom + pointed top
            d = np.sqrt((xx - cx) ** 2 + ((yy - 11.0) / 1.0) ** 2); acc += np.exp(-(d / 2.4) ** 2)
            acc += np.exp(-((xx - cx) ** 2) / 0.8) * np.clip(1 - np.abs(yy - 7.5) / 3.2, 0, 1) * (yy < 11) * 0.8
            hi += np.exp(-((xx - 9.0) ** 2 + (yy - 10.2) ** 2) / 0.6)
        else:
            for R, w, a in (((2.6, 0.9, 1.0),) if k == 1 else ((5.0, 1.0, 0.8), (2.6, 0.8, 0.5))):
                d = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.5) ** 2); acc += a * np.exp(-((d - R) / w) ** 2)
            if k == 1:
                acc += np.exp(-((xx - cx) ** 2 + (yy - (cy - 3.0)) ** 2) / 1.2) * 0.9; hi += np.exp(-((xx - cx) ** 2 + (yy - (cy - 3.0)) ** 2) / 0.5)
        r = 40 * acc + 200 * hi; g = 130 * acc + 230 * hi; b = 255 * acc + 255 * hi; a = np.clip(acc + hi, 0, 1)
        out.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255), 255 * (a > 0.05)]).astype(np.uint8), "RGBA"))
    return out


def snow_drift(n=3):
    """Ice Age (399) slots 0-2 (10/15): three single frames for Air Mastery's map-wide drift (200x116, additive at
    low blend): a stream of six-armed snowflakes (small crosses with diagonals) of several sizes, frost glints and a
    faint pale-blue haze along a wide S-curve."""
    W, H = 200, 116; out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for v in range(n):
        rnd = random.Random(4150 + v); ph = v * 2.3
        acc = np.zeros((H, W, 3), np.float32)
        for k in range(10):
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 30 * math.sin(t * 2 * math.pi * 1.1 + ph)
            g = 0.18 * np.exp(-((xx - x) ** 2 + ((yy - y) / 0.6) ** 2) / 300.0)
            for c, cv in enumerate((150, 190, 240)): acc[..., c] += g * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for k in range(34):
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 30 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-20, 20)
            r = rnd.choice((1.5, 2.0, 3.0)); c = int(rnd.uniform(190, 255)); col = (c, c, 255, 255)
            for a in range(3):
                ang = math.radians(a * 60 + rnd.uniform(0, 30)); dx, dy = r * math.cos(ang), r * math.sin(ang)
                dr.line([(x - dx, y - dy), (x + dx, y + dy)], fill=col)
        for k in range(20):
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 30 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-24, 24)
            dr.point((x, y), fill=(220, 240, 255, 255))
        out.append(im)
    return out


def mist_swirl(n=12):
    """Misty Step (396) slot 0 v2 (2026-10-15; user: more blue, more of a splash, blue glowing particles): Void Step's
    cast-fx canvas (64x64, centre (31, 34)), played at the origin AND the destination, additive: a burst of water - a
    bright blue flash at the feet, a splash crown ring spreading over the ground, and ~34 glowing blue droplets (white
    hot cores in a blue halo) flung up and out on ballistic arcs that fall back, fading as they land."""
    W = H = 64; cx, cy = 31.0, 40.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3962)
    drops = [(rnd.uniform(-1, 1) * 1.6, rnd.uniform(1.4, 3.0), rnd.uniform(0.8, 1.6), rnd.uniform(0.0, 0.15)) for _ in range(34)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)
        flash = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.6) ** 2) / (20.0 + 80 * t)) * max(0.0, 1 - t * 2.5)
        acc += 0.9 * flash; hot += 0.6 * flash
        R = 4 + 22 * t ** 0.7; ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.4) ** 2) - R) / 1.6) ** 2) * (1 - t) * 0.8
        acc += ring
        for vx, vy, r, d in drops:
            tt = max(0.0, t - d) * 1.25
            if tt <= 0 or tt > 1.0: continue
            x = cx + vx * 14 * tt; y = cy - vy * 16 * tt + 26 * tt * tt
            if y > cy + 4: continue
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r * 2.2)) * (1 - 0.6 * tt)
            acc += g; hot += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r * 0.5)) * (1 - 0.6 * tt)
        rr = np.clip(40 * acc + 230 * hot, 0, 255); gg = np.clip(140 * acc + 240 * hot, 0, 255); bb = np.clip(255 * acc + 255 * hot, 0, 255)
        out.append(Image.fromarray(np.dstack([rr, gg, bb]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def frost_burst(n=8):
    """Flashfreeze (397) slot 0 v2 (2026-10-15; user: the hit gfx and sfx are out of sync): the hit and its cue-1 sound
    land on the LAST frame of this sequence (TCPCK 0x42D3AE/0x42D3E5), so the burst is now timed to END on the impact:
    on Vaporize's canvas (74x80, hit point (37, 64)), additive, the white / pale-cyan ice shards spike up and out from
    the hit point over frames 0-11 (frost crystals gathering), then the frost flares and the shards shatter into
    glittering fragments on frames 12-15 with the brightest flash on the final frame."""
    W, H = 74, 80; cx, cy = 37.0, 64.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3970)
    shards = [(rnd.uniform(-3.0, -0.1), rnd.uniform(0.6, 1.0)) for _ in range(14)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        grow = min(1.0, t / 0.72) ** 0.7; shatter = max(0.0, (t - 0.72) / 0.28)
        glow = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (30.0 + 60 * grow)) * (0.15 + 0.25 * grow)
        flash = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 1.2) ** 2) / (60.0 + 260 * shatter)) * shatter ** 1.5
        for c, cv in enumerate((230, 250, 255)): acc[..., c] += (glow + 1.1 * flash) * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for a, v in shards:
            L = 6 + 22 * v * grow; ux, uy = math.cos(a), math.sin(a); px, py = -uy * 1.6, ux * 1.6
            col = (210, 240, 255, 255)
            if shatter <= 0:
                x1, y1 = cx + L * ux, cy + L * uy * 0.9
                dr.polygon([(cx + ux * L * 0.5 + px, cy + uy * L * 0.5 + py), (x1, y1), (cx + ux * L * 0.5 - px, cy + uy * L * 0.5 - py), (cx + ux * L * 0.35, cy + uy * L * 0.35)], fill=col)
            else:
                for f in (0.45, 0.7, 0.95):                                    # fragments flying apart
                    d = L * f * (1 + 0.35 * shatter); fx, fy = cx + d * ux + rnd.uniform(-1, 1) * shatter * 3, cy + d * uy * 0.9 + rnd.uniform(-1, 1) * shatter * 3
                    r = 1.6 * (1 - 0.5 * shatter); dr.polygon([(fx + ux * r * 1.8, fy + uy * r * 1.8), (fx + px * r * 0.6, fy + py * r * 0.6), (fx - ux * r, fy - uy * r), (fx - px * r * 0.6, fy - py * r * 0.6)], fill=col)
        if t > 0.45:                                                           # v3 (user: add a blue particle splash): glowing blue
            sp = (t - 0.45) / 0.55; ov = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)   # droplets erupting from the hit, widest on the hit frame
            prnd = random.Random(3972)
            for q in range(26):
                a2 = prnd.uniform(-3.05, -0.09); v2 = prnd.uniform(0.5, 1.0); r2 = prnd.uniform(1.0, 1.8)
                d2 = 30 * v2 * sp ** 0.8; x2 = cx + d2 * math.cos(a2); y2 = cy + d2 * math.sin(a2) * 0.85 + 10 * sp * sp * v2
                ov += np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (r2 * r2 * 2.0)); hot += np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (r2 * r2 * 0.45))
            ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.4) ** 2) - (4 + 20 * sp)) / 1.5) ** 2) * 0.7
            base = np.asarray(im).astype(np.float32)
            base[..., 0] += 40 * (ov + ring) + 220 * hot; base[..., 1] += 140 * (ov + ring) + 235 * hot; base[..., 2] += 255 * (ov + ring) + 255 * hot
            im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGBA"); dr = ImageDraw.Draw(im)
        for k in range(int(4 + 18 * shatter)):
            x = cx + rnd.uniform(-26, 26); y = cy + rnd.uniform(-36, 6)
            dr.point((x, y), fill=(220, 245, 255, 255))
        out.append(im)
    return out


def frost_ring(n=24):
    """Flashfreeze (397) slot 1 (10/15; user: 'similar to implosion with a shrinking circle, fewer particles, jagged
    and bluish white'): the kind-0x26 driver's sequence at the target (patch_tc_flashfreeze_v1.py), 160x96 additive,
    centre (80, 52) = the hex centre, 16 frames x 2 ticks: 14 jagged ice shards (irregular 5-point crystals, white
    cores, pale-cyan edges) on a ring flattened to the battlefield angle (y 0.48), spinning and tumbling as they rush
    in from R 64 to 4 while a faint cold halo traces the ring and a frost core swells at the centre; the last frame is
    the collapse flash the first frost burst starts from."""
    W, H = 160, 96; cx, cy = 80.0, 52.0; rnd = random.Random(3971); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    shards = []
    for k in range(14):
        a0 = 2 * math.pi * k / 14 + rnd.uniform(-0.15, 0.15); v = rnd.uniform(0.88, 1.08); L = rnd.uniform(4.5, 7.0)
        prof = [(1.0, 0.0), (0.35, 0.45 * rnd.uniform(0.7, 1.2)), (-0.55, 0.3 * rnd.uniform(0.7, 1.3)),
                (-0.8, -0.25 * rnd.uniform(0.7, 1.3)), (0.3, -0.5 * rnd.uniform(0.7, 1.2))]   # jagged 5-point crystal
        shards.append((a0, v, L, prof, rnd.uniform(0, 6.28), rnd.uniform(-0.5, 0.5)))
    out = []
    for i in range(n):
        t = i / (n - 1.0); R = 60 * (1 - t) ** 1.3 + 4; spin = 1.4 * t * t
        acc = np.zeros((H, W, 3), np.float32)
        rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.48) ** 2)
        halo = np.exp(-((rr - R) / 4.0) ** 2) * (0.12 + 0.18 * t)                                   # faint cold ring
        core = np.exp(-(((xx - cx) / (3 + 9 * t)) ** 2 + ((yy - cy) / (2 + 5 * t)) ** 2)) * (0.1 + 0.9 * t ** 2)
        for c, cv in enumerate((150, 210, 255)): acc[..., c] += halo * cv
        for c, cv in enumerate((220, 240, 255)): acc[..., c] += core * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB"); dr = ImageDraw.Draw(im)
        for a0, v, L, prof, rot0, rs in shards:
            a = a0 + spin; x = cx + R * v * math.cos(a); y = cy + 0.48 * R * v * math.sin(a)
            r = rot0 + rs * i + a; s = L * (1.0 + 0.25 * t); ca, sa = math.cos(r), math.sin(r)
            pts = [(x + s * (u * ca - w * sa), y + 0.8 * s * (u * sa + w * ca)) for u, w in prof]
            dr.polygon(pts, fill=(120, 190, 235))                                                    # pale-cyan body
            inner = [(x + 0.55 * (px - x), y + 0.55 * (py - y)) for px, py in pts]
            dr.polygon(inner, fill=(235, 248, 255))                                                  # white-hot core
            for d in (0.03, 0.07):                                                                   # a short frost trail
                ta = a - d * (1 + 3 * t); tR = R + 6 * d / 0.07 * (1 - t)
                tx, ty = cx + tR * v * math.cos(ta), cy + 0.48 * tR * v * math.sin(ta)
                g = int(120 * (1 - d / 0.1)); dr.point((tx, ty), fill=(g, g + 30, min(255, g + 80)))
        out.append(im.convert("RGBA"))
    return out


def ice_sparkle():
    """Ice Age (399) slot 3 (10/15; user: the same hex glow as Freeze Water, slightly more subtle): drawn per marker by
    patch_drought_glow_v1.py v3 (pure frame pick).  EXACT copies of the vanilla sparkle every Freeze Water ice hex
    shows (general-FX slot 0x46 in Release.hss = EFFECTS\\SWARM.ILB 20..31, 64x64, additive 770 / blend 100, anchor
    (-33, -39)); the subtlety comes from the lower blend in the table entry."""
    lib = ilbcodec.read(os.path.join(GAME, "Images", "Effects", "Swarm.ILB")); out = []
    for src in range(20, 32):
        im, r = raw_pixels(lib, src); out.append(im)
    return out


def drought_sparkle():
    """Drought (391) slot 1 v3 (2026-10-15; user: make the drought gfx more like Ice Age's, but red/orange): Ice Age's
    hex glow (the vanilla Freeze Water sparkle, EFFECTS\SWARM.ILB 20..31, 64x64, anchor (-33, -39)) recoloured to a
    heat shimmer - each pixel's brightness mapped onto deep red -> orange -> pale yellow."""
    lib = ilbcodec.read(os.path.join(GAME, "Images", "Effects", "Swarm.ILB")); out = []
    for src in range(20, 32):
        im, r = raw_pixels(lib, src); a = np.asarray(im.convert("RGBA")).astype(np.float32)
        lum = a[..., :3].max(axis=2) / 255.0
        rgb = np.dstack([255 * np.clip(lum * 1.25, 0, 1), 255 * np.clip(lum ** 1.4 * 0.75, 0, 1), 255 * np.clip((lum - 0.75) * 2.4, 0, 1) * 0.7])
        out.append(Image.fromarray(np.dstack([rgb, a[..., 3]]).astype(np.uint8), "RGBA"))
    return out


def heat_drift(n=3):
    """Drought (391) slots 0-2 v3 (2026-10-15; user: make the cast gfx cover the map like Overgrowth's): three single
    frames for Air Mastery's map-wide drift (patch_drought_worldfx_v1.py v3 replays it for 391; 200x116, additive at
    low blend, drawn 5-20x per frame so kept sparse): a wide S-curve of hot red/orange haze with drifting embers, dust
    motes and short wavering heat streaks."""
    W, H = 200, 116; out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for v in range(n):
        rnd = random.Random(3910 + v); ph = v * 2.1
        acc = np.zeros((H, W, 3), np.float32)
        for k in range(10):
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph)
            g = 0.2 * np.exp(-((xx - x) ** 2 + ((yy - y) / 0.6) ** 2) / 320.0)
            for c, cv in enumerate((240, 110, 30)): acc[..., c] += g * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for k in range(12):                                                    # heat streaks
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-18, 18)
            pts = [(x + j * 2.0, y + 1.2 * math.sin(j * 1.3 + k)) for j in range(6)]
            dr.line(pts, fill=(200, 90, 20, 255))
        for k in range(30):                                                    # embers + dust
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-22, 22)
            c = rnd.choice(((255, 170, 60), (255, 110, 30), (230, 70, 20), (255, 210, 120)))
            if rnd.random() < 0.4: dr.ellipse([x - 1, y - 1, x + 1, y + 1], fill=c + (255,))
            else: dr.point((x, y), fill=c + (255,))
        out.append(im)
    return out


def frost_fade(n=12):
    """Flashfreeze (397) slot 2 (2026-10-15; user: the hit gfx needs a longer, smoother fade-out, the hits slightly
    overlapping): spawned at the landing tick by patch_tc_flashfreeze_v1.py v3 (the burst object is deleted right after
    the hit), same canvas as frost_burst (74x80, hit point (37, 64)), additive: continues from the burst's final flash -
    the flash dies away, the ice fragments keep flying out and tumble down, the glowing blue droplets arc and fall, the
    splash ring spreads and thins, frost glitter lingers; everything dims smoothly to nothing."""
    W, H = 74, 80; cx, cy = 37.0, 64.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    srnd = random.Random(3970); shards = [(srnd.uniform(-3.0, -0.1), srnd.uniform(0.6, 1.0)) for _ in range(14)]
    prnd = random.Random(3972); drops = [(prnd.uniform(-3.05, -0.09), prnd.uniform(0.5, 1.0), prnd.uniform(1.0, 1.8)) for _ in range(26)]
    grnd = random.Random(3973); glit = [(grnd.uniform(-28, 28), grnd.uniform(-38, 4), grnd.uniform(0, 1)) for _ in range(30)]
    out = []
    for i in range(n):
        u = (i + 1) / float(n); fade = (1 - u) ** 1.6; acc = np.zeros((H, W, 3), np.float32)
        flash = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 1.2) ** 2) / (320.0 + 200 * u)) * (1 - u) ** 3
        for c, cv in enumerate((230, 250, 255)): acc[..., c] += 1.1 * flash * cv
        ov = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)
        for a2, v2, r2 in drops:                                               # droplets keep flying, then fall
            sp = 1 + 0.9 * u; d2 = 30 * v2 * sp ** 0.8
            x2 = cx + d2 * math.cos(a2); y2 = cy + d2 * math.sin(a2) * 0.85 + 10 * sp * sp * v2 + 18 * u * u
            ov += np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (r2 * r2 * 2.0)) * fade; hot += np.exp(-((xx - x2) ** 2 + (yy - y2) ** 2) / (r2 * r2 * 0.45)) * fade
        ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.4) ** 2) - (24 + 10 * u)) / (1.5 + 2 * u)) ** 2) * 0.7 * (1 - u) ** 2
        acc[..., 0] += 40 * (ov + ring) + 220 * hot; acc[..., 1] += 140 * (ov + ring) + 235 * hot; acc[..., 2] += 255 * (ov + ring) + 255 * hot
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        col = (int(210 * fade), int(240 * fade), int(255 * fade), 255)
        for a, v in shards:                                                    # fragments tumbling out and down
            L = 28 * v; ux, uy = math.cos(a), math.sin(a); px, py = -uy * 1.6, ux * 1.6
            for f in (0.45, 0.7, 0.95):
                d = L * f * (1.35 + 0.5 * u); fx, fy = cx + d * ux, cy + d * uy * 0.9 + 14 * u * u
                r = 0.8 * (1 - 0.4 * u); dr.polygon([(fx + ux * r * 1.8, fy + uy * r * 1.8), (fx + px * r * 0.6, fy + py * r * 0.6), (fx - ux * r, fy - uy * r), (fx - px * r * 0.6, fy - py * r * 0.6)], fill=col)
        for gx, gy, ph in glit:                                                # lingering frost glitter
            if (ph + u * 2.3) % 1.0 < 0.5 * fade + 0.1 * (1 - u):
                g = int(235 * fade); dr.point((cx + gx, cy + gy + 6 * u), fill=(g, min(255, g + 15), 255, 255))
        out.append(im)
    return out


def suffocate_coil(n=16):
    """Suffocate (345) slot 0 v4 (2026-10-16; user: the particles/animation need more work): one per strike (8 frames x 2
    ticks; the 5 strikes overlap into one stream), Vaporize's canvas (74x80), additive: ~18 pale blue-white motes of
    breath start INSIDE the target's body (an ellipse round (37, 46)), are pulled out with growing speed up and away on
    curling paths, each trailing a short fading streak; a faint pale mist leaves the chest with them."""
    W, H = 96, 96; cx, cy = 48.0, 62.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3452); out = []   # v5: 96x96 (motes travel ~60 px), 16 frames x 3 ticks
    motes = []
    for k in range(18):
        a = rnd.uniform(0, 2 * math.pi); rr = rnd.uniform(0.2, 1.0); sx, sy = cx + 6 * rr * math.cos(a), cy + 10 * rr * math.sin(a)
        da = rnd.uniform(-2.5, -0.6); sp = rnd.uniform(48, 66); d0 = rnd.uniform(0, 0.35); r = rnd.uniform(0.9, 1.5); cu = rnd.uniform(-0.8, 0.8)
        motes.append((sx, sy, da, sp, d0, r, cu))
    def pos(m, u):
        sx, sy, da, sp, d0, r, cu = m; d = sp * u ** 1.4; a = da + cu * u
        return sx + d * math.cos(a), sy + d * math.sin(a)
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)
        acc += np.exp(-((xx - cx) ** 2 + ((yy - cy + 6 * t) / 1.4) ** 2) / 40.0) * 0.18 * math.sin(math.pi * t)   # the leaving mist
        for m in motes:
            u = max(0.0, t - m[4]) / (1 - m[4])
            if u <= 0: continue
            f = math.sin(math.pi * min(1.0, u * 1.1)); r = m[5]
            for q in range(5):                                                 # head + fading tail
                uq = max(0.0, u - q * 0.06); x, y = pos(m, uq); w = (1 - q / 5.0) * f
                acc += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r * 2.0)) * w * 0.8
                if q == 0: hot += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r * 0.4)) * f
        rgb = np.dstack([110 * acc + 210 * hot, 150 * acc + 230 * hot, 210 * acc + 255 * hot])
        out.append(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def borrow_hourglass(n=20):
    """Borrow Time (346) slot 0 v2 (2026-10-15; user: an hourglass like the icon, the sand going from the BOTTOM into
    the TOP): Martyr's canvas (64x64, anchor -32/-50), additive, 16 frames x 3 ticks: the icon's hourglass (solid
    caps, side posts, the glass) in pale violet light fades in over the unit; the golden sand pile in the bottom bulb
    shrinks while grains stream UP through the neck and pile into the top bulb (time running backwards); it then fades."""
    W = H = 64; cx, cy = 32.0, 30.0; rnd = random.Random(3461); out = []
    grains = [(rnd.uniform(-0.8, 0.8), rnd.uniform(0, 1)) for _ in range(16)]
    for i in range(n):
        t = i / (n - 1.0); vis = min(1.0, t / 0.2) * (1.0 if t < 0.78 else max(0.0, 1 - (t - 0.78) / 0.22))
        im = Image.new("RGBA", (W, H), (0, 0, 0, 255)); dr = ImageDraw.Draw(im)
        fr = (int(210 * vis), int(180 * vis), int(255 * vis), 255); sd = (int(255 * vis), int(215 * vis), int(120 * vis), 255)
        dr.rectangle([cx - 13, cy - 21, cx + 13, cy - 18], fill=fr); dr.rectangle([cx - 13, cy + 18, cx + 13, cy + 21], fill=fr)   # caps
        for x in (cx - 11.5, cx + 11.5): dr.rectangle([x - 1, cy - 18, x + 1, cy + 18], fill=fr)              # posts
        for sg in (-1, 1):                                                     # the glass
            dr.line([(cx + sg * 8.5, cy - 17), (cx + sg * 8.5, cy - 13), (cx + sg * 1.5, cy - 2), (cx + sg * 1.5, cy + 2), (cx + sg * 8.5, cy + 13), (cx + sg * 8.5, cy + 17)], fill=fr, width=1)
        p = min(1.0, t / 0.85)                                                 # sand: bottom empties, top fills (from the top cap DOWN)
        hb = 9.0 * (1 - p); ht = 9.0 * p
        if hb > 0.5: dr.polygon([(cx - 8, cy + 17), (cx + 8, cy + 17), (cx + 8 - hb * 0.4, cy + 17 - hb), (cx - 8 + hb * 0.4, cy + 17 - hb)], fill=sd)
        if ht > 0.5: dr.polygon([(cx - 8, cy - 17), (cx + 8, cy - 17), (cx + 8 - ht * 0.4, cy - 17 + ht), (cx - 8 + ht * 0.4, cy - 17 + ht)], fill=sd)
        if 0.05 < t < 0.9:                                                     # grains rising through the neck
            for gx, ph in grains:
                y = cy + 15 - ((ph + t * 3.0) % 1.0) * (30 - ht)
                dr.point((cx + gx * (abs(y - cy) / 6.0 + 0.4), y), fill=sd)
        out.append(im)
    return out


def banshee_wisp(n=3):
    """Banshee Gale (344) slot 0 (2026-10-15): the particle Winds of Fury's engine leaves all along each thrown unit's
    path (20x20, anchor -9/-10, additive, 3 frames): a pale grey-violet ghostly wisp - a soft glowing smear with a
    darker hollow pair of eyes and a stretched wailing mouth, trailing off to one side."""
    out = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32)
    for k, (sc, dx) in enumerate(((0.8, 0.0), (1.0, 0.8), (0.9, -0.6))):
        cx, cy = 9.0 + dx, 9.0
        body = np.exp(-(((xx - cx) / (4.2 * sc)) ** 2 + ((yy - cy) / (5.0 * sc)) ** 2))
        tail = np.exp(-(((xx - cx - 5 * sc) / (4.5 * sc)) ** 2 + ((yy - cy - 3) / (2.2 * sc)) ** 2)) * 0.5
        holes = np.zeros_like(body)
        for ex in (-1.6, 1.6): holes += np.exp(-(((xx - cx - ex * sc) ** 2) + (yy - cy + 1.6 * sc) ** 2) / (0.9 * sc))
        holes += np.exp(-(((xx - cx) / (0.9 * sc)) ** 2 + ((yy - cy - 2.2 * sc) / (1.6 * sc)) ** 2))
        v = np.clip(body + tail - 0.9 * holes, 0, 1)
        r = 170 * v; g = 160 * v; b = 220 * v
        out.append(Image.fromarray(np.dstack([r, g, b, 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return out


def banshee_vortex():
    """Banshee Gale (344) slot 1 v4 (2026-10-16; user: more particles, with the same 'black glow' as Mind Decay): drawn
    the way Mind Decay's own particle is - MULTIPLY / dark mode 1026 on a WHITE field (white = no change), stamping
    the vanilla Mind Decay particle sprites (EFFECTS\PARTICLE.ILB 15-17: a dark core in a soft dark halo) ~650 times
    per frame, a few tinted dark purple.  224x160 (hex centre (112, 92)), 44 frames x 3 ticks (v5) = rise 0-7 / seamless
    revolution 8-19 / 8-19 again / the 12 phases thinning out 32-43; Sandstorm's swirl: flattened ellipses, 75 %% of
    the particles on 3 spiral arms, one spin speed (2 turns per 12-frame cycle) so the loop is seamless."""
    W, H = 224, 160; cx, cy = 112.0, 84.0; rnd = random.Random(3445)
    plib = ilbcodec.read(os.path.join(GAME, "Images", "Effects", "PARTICLE.ILB"))
    stamps = [(np.asarray(raw_pixels(plib, k)[0].convert("RGB")).astype(np.float32) / 255.0) ** 1.35 for k in (15, 16, 17)]   # v5: DARKER (gamma 1.35)
    parts = []
    for _ in range(77):                                                         # v10: 3-FOLD SYMMETRIC (each particle x3 at 120 deg) so the
        r = 98 * math.sqrt(rnd.random()) + 6                                    #   image repeats every third of a turn (smooth fade entry)
        a0 = (-r / 20.0 + rnd.gauss(0, 0.30)) if rnd.random() < 0.75 else rnd.uniform(0, 2 * math.pi / 3)
        dy = rnd.uniform(-24, 20) * (1 - r / 140.0); st = rnd.randrange(3); pu = rnd.random() < 0.08; q = rnd.random()
        for k3 in range(3): parts.append((r, a0 + k3 * 2 * math.pi / 3, dy, st, pu, q))
    def frame(ph, keep, grow, dark=1.0):
        f = np.ones((H, W, 3), np.float32)
        for r0, a0, dy, st, purple, q in parts:
            if q > keep: continue
            r = r0 * grow
            for tl in range(5):                                                # v5: the particle + a 4-step afterglow tail behind it
                a = a0 + 2 * math.pi * ph - tl * 0.07                          # v5: ONE full turn per 12-frame cycle (30 deg/frame) = visible orbit
                x = int(round(cx + r * math.cos(a))) - 9; y = int(round(cy + 0.42 * r * math.sin(a) + dy * grow * 0.5)) - 9
                if x < 0 or y < 0 or x + 19 > W or y + 19 > H: continue
                sp = stamps[st]
                if purple: sp = 1 - (1 - sp) * np.array([0.75, 1.0, 0.55], np.float32)
                if tl: sp = 1 - (1 - sp) * (0.55 * (1 - tl / 5.0))
                if dark < 1.0: sp = 1 - (1 - sp) * dark                         # v12: fading transparency
                f[y:y + 19, x:x + 19] *= sp
        return Image.fromarray((np.clip(f, 0, 1) * 255).astype(np.uint8), "RGB").convert("RGBA")
    R, C = 36, 24                                                               # v12 (user: after full size, spin up even faster; a smoother, more
    w0, w1 = 1.0 / C, 2.0 / C                                                   #   transparent fade): rise 36 = 12 growing at 1 turn/24 frames + 24
    phs = []; p = 0.0                                                           #   ACCELERATING to 2 turns/24 frames; loop + fade at the fast speed;
    for f in range(R):                                                          #   phase tracked continuously (seamless into the loop)
        w = w0 if f < 12 else w0 + (w1 - w0) * (f - 11) / 24.0
        p += w; phs.append(p)
    out = []
    for f in range(R):
        u = min(1.0, (f + 1) / 12.0); out.append(frame(phs[f], u, 0.12 + 0.88 * u ** 0.8))
    loop = [frame(phs[-1] + w1 * (k + 1), 1.0, 1.0) for k in range(C)]
    out += loop + loop
    def single(a, grow):                                                       # the last particle alone, paling away
        f = np.ones((H, W, 3), np.float32); sp = stamps[1]
        x = int(round(cx + 6 * grow)) - 9; y = int(round(cy)) - 9
        f[y:y + 19, x:x + 19] *= 1 - (1 - sp) * a
        return Image.fromarray((np.clip(f, 0, 1) * 255).astype(np.uint8), "RGB").convert("RGBA")
    for k in range(C):                                                         # FADE: 8 frames at FULL strength (the gate enters there at the
        ph = phs[-1] + w1 * (k + 1)                                            #   matching image), then it shrinks into its centre, thins out and
        if k < C // 3: out.append(frame(ph, 1.0, 1.0)); continue              #   grows ever more transparent; the last 3 frames = one paling particle
        v = 1 - (k - C // 3 + 1) / float(C - C // 3)
        if k >= C - 3: out.append(single((0.7, 0.4, 0.18)[k - (C - 3)], v)); continue
        out.append(frame(ph, max(0.004, v ** 2.6), 0.06 + 0.94 * v ** 1.1, dark=0.25 + 0.75 * v ** 0.9))
    return out


def suffocate_puff(n=16):
    """Suffocate (345) slot 0 v6 (2026-10-16): the per-HIT effect (8 frames x 2 ticks; the hit lands on the last frame),
    Vaporize's canvas (74x80, chest (37, 46)), additive: a small gasp of pale breath torn out of the chest - a soft
    glow tightening, then on the last frames a handful of motes jerked out sideways."""
    W, H = 74, 80; cx, cy = 37.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3453); out = []
    motes = [(rnd.choice((-1, 1)) * rnd.uniform(0.6, 1.0), rnd.uniform(-0.35, 0.15), rnd.uniform(0.8, 1.3)) for _ in range(6)]
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)
        acc += np.exp(-((xx - cx) ** 2 + ((yy - cy) / 1.3) ** 2) / (30.0 - 18 * t)) * (0.2 + 0.4 * t)
        if t > 0.55:
            u = (t - 0.55) / 0.45
            for dx, dy, r in motes:
                x = cx + dx * 14 * u; y = cy + dy * 14 * u
                acc += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r * 2.0)) * 0.9; hot += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r * 0.4))
        rgb = np.dstack([110 * acc + 210 * hot, 150 * acc + 230 * hot, 210 * acc + 255 * hot])
        out.append(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def suffocate_drain(n=48):
    """Suffocate (345) slot 1 v2 (2026-10-16; user: a bit more glow; start at the unit's FEET, rise to about head level,
    then move outward in a CURVE (not a 90-degree turn)): patch_tc_suffocate_v1.py's whole-cast driver (32 frames x 3
    ticks), 160x120 with the hex centre at (80, 70) (feet ~ y 68, head ~ y 24), additive: a sparse trickle of pale
    breath motes, each lifting off near the feet, rising up the body to head height and bending smoothly outward to
    one side on a cubic curve, with a soft wide glow, a bright core and a short fading tail; a faint haze at the chest."""
    W, H = 160, 120; cx = 80.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3455); out = []
    def cub(p0, p1, p2, p3, u):
        a, b, c, d = (1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u * u, u ** 3
        return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])
    motes = []
    for k in range(24):
        born = k * (n - 18) / 24.0 + rnd.uniform(-0.6, 0.6); life = rnd.uniform(17, 22); sd = rnd.choice((-1, 1))   # v3: 48 frames x 2 ticks (smoother)
        x0 = cx + rnd.uniform(-7, 7); hy = rnd.uniform(20, 28)
        P = ((x0, 68 + rnd.uniform(-2, 2)), (x0 + sd * rnd.uniform(-1, 2), hy + 10), (x0 + sd * 8, hy - 3), (x0 + sd * rnd.uniform(52, 66), hy - rnd.uniform(0, 8)))
        motes.append((born, life, P, rnd.uniform(0.9, 1.3)))
    for i in range(n):
        acc = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)
        env = min(1.0, i / 4.0) * min(1.0, (n - 1 - i) / 6.0)
        acc += np.exp(-((xx - cx) ** 2 + ((yy - 46) / 1.6) ** 2) / 60.0) * 0.12 * env
        for born, life, P, r in motes:
            u = (i - born) / life
            if u < 0 or u > 1: continue
            f = math.sin(math.pi * u) ** 0.7
            for q in range(4):
                uq = max(0.0, u - q * 0.045); x, y = cub(P[0], P[1], P[2], P[3], uq); w = (1 - q / 4.0) * f
                d2 = (xx - x) ** 2 + (yy - y) ** 2
                acc += np.exp(-d2 / (r * r * 2.0)) * w * 0.8
                if q == 0:
                    hot += np.exp(-d2 / (r * r * 0.4)) * f
                    acc += np.exp(-d2 / (r * r * 9.0)) * f * 0.35          # v2: a soft wide glow
        rgb = np.dstack([110 * acc + 210 * hot, 150 * acc + 230 * hot, 210 * acc + 255 * hot])
        out.append(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def chorus_spark(n=4):
    """Heavenly Chorus (308) slot 0 (2026-10-16): High Prayer's rising per-unit particle (16x16, additive, 4 frames):
    a small golden-white four-point sparkle with a soft warm glow, twinkling."""
    out = []; yy, xx = np.mgrid[0:16, 0:16].astype(np.float32); c = 7.5
    for k, sc in enumerate((0.8, 1.0, 0.9, 0.7)):
        rr = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / sc
        core = np.exp(-(rr / 1.4) ** 2); glow = np.exp(-(rr / 4.0) ** 2) * 0.45
        arms = (np.exp(-((yy - c) ** 2) / 0.25) * np.clip(1 - np.abs(xx - c) / (6 * sc), 0, 1) + np.exp(-((xx - c) ** 2) / 0.25) * np.clip(1 - np.abs(yy - c) / (6 * sc), 0, 1)) * 0.7
        v = core + glow + arms
        out.append(Image.fromarray(np.clip(np.dstack([255 * v, 225 * v, 150 * v + 60 * core]), 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def chorus_aura(n=30):
    """Heavenly Chorus (308) slot 1 v4 (2026-10-16; user: the halo should appear sooner, drop slowly, come to rest LOWER,
    and its glow should swell once it has landed before it fades): 48x64, additive, 24 frames x 2 ticks, anchor -24/-62:
    the golden halo ring appears almost at once high above, sinks slowly (eased) to rest just over the head (y 21),
    then brightens with a soft warm bloom round the ring, and fades away."""
    W, H = 48, 64; cx = 24.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for i in range(n):
        t = i / (n - 1.0)
        fin = min(1.0, t / 0.08)
        hy = 2 + 19 * (1 - (1 - min(1.0, t / 0.55)) ** 2.2)                    # a slow ease down from y 2 to y 21 (v5: lands at 55 %)
        swell = 0.0 if t < 0.53 else min(1.0, (t - 0.53) / 0.12)              # once landed: the glow swells ...
        u_ = 0.0 if t < 0.66 else min(1.0, (t - 0.66) / 0.34); fout = 1 - u_ * u_ * (3 - 2 * u_)   # ... then a slow, smooth (smoothstep) fade - v5
        ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - hy) / 0.35) ** 2) - 8) / (1.2 + 0.8 * swell)) ** 2) * (1 + 0.6 * swell)
        bloom = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - hy) / 0.35) ** 2) - 8) / 4.5) ** 2) * 0.45 * swell
        v = (ring + bloom) * fin * fout
        out.append(Image.fromarray(np.clip(np.dstack([255 * v, 225 * v, 140 * v]), 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def inspire_burst(n=16):
    """Inspiration (309) slot 2 v3 (2026-10-16; user: try something different): the per-hex landing (96x80, additive,
    16 frames x 2 ticks, anchor -48/-40 = hex centre (48, 40)): a slender golden pillar of light rises from the hex
    and a four-pointed star flares at its top, motes of light spiral up round the pillar and a soft ring spreads over
    the ground; all fade together."""
    W, H = 96, 80; cx, cy = 48.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3092)
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0, 0.35), rnd.uniform(5, 10)) for _ in range(10)]
    for i in range(n):
        t = i / (n - 1.0); env = math.sin(math.pi * min(1.0, t * 1.05)) ** 0.7
        top = cy - 6 - 34 * min(1.0, t / 0.4)
        pillar = np.exp(-((xx - cx) / 3.2) ** 2) * ((yy <= cy) & (yy >= top)) * (0.35 + 0.65 * np.clip((yy - top) / 30.0, 0, 1)) * 0.7
        sr = np.sqrt((xx - cx) ** 2 + (yy - top) ** 2)
        star = (np.exp(-((yy - top) ** 2) / 0.8) * np.clip(1 - np.abs(xx - cx) / 12, 0, 1) + np.exp(-((xx - cx) ** 2) / 0.8) * np.clip(1 - np.abs(yy - top) / 12, 0, 1)) * min(1.0, t / 0.4) + np.exp(-(sr / 3.0) ** 2)
        ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.4) ** 2) - (6 + 26 * t)) / 3.0) ** 2) * (1 - t) * 0.5
        v = (pillar + 0.9 * star + ring) * env
        for a0, d0, r0 in motes:
            u = (t - d0) / 0.6
            if 0 <= u <= 1:
                a = a0 + 7 * u; x = cx + r0 * math.cos(a); y = cy - 2 - 36 * u
                v = v + np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.6) * math.sin(math.pi * u) * env
        out.append(Image.fromarray(np.clip(np.dstack([255 * v, 220 * v, 130 * v]), 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def secondwind_swirl(n=40):
    """Second Wind (310) slot 0 v3 (2026-10-16; user: v2 looked janky/rough - refine it): 96x96, feet at (48, 86)
    (anchor -48/-86), additive, 20 frames x 2 ticks: three smooth ribbons of pale-blue wind spiralling up round the
    unit - drawn as anti-aliased strokes at 2x and softened, each ribbon fading toward its ends - carrying green-gold
    motes, then a clean flash at the chest and a soft shockwave ring over the ground."""
    W = H = 96; SS = 2; cx = 48.0; rnd = random.Random(3103); out = []
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(0.0, 0.45), rnd.uniform(10, 19)) for _ in range(16)]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for i in range(n):
        t = i / (n - 1.0); env = math.sin(math.pi * min(1.0, t * 1.08)) ** 0.6
        big = Image.new("L", (W * SS, H * SS), 0); d = ImageDraw.Draw(big)
        for k in range(3):
            pts = []
            for j in range(80):
                u = j / 79.0; y = 86 - 78 * u; a = 2 * math.pi * (1.5 * u + t * 1.6) + k * 2.094; r = 20 - 9 * u
                pts.append(((cx + r * math.cos(a)) * SS, y * SS, u, a))
            for j in range(len(pts) - 1):                                   # front strokes brighter than the back ones
                x0, y0, u, a = pts[j]; x1, y1, _, _ = pts[j + 1]
                lvl = int(255 * env * math.sin(math.pi * u) * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(a))))
                d.line([(x0, y0), (x1, y1)], fill=lvl, width=int(3.2 * SS))
        wind = np.asarray(big.filter(ImageFilter.GaussianBlur(2.2)).resize((W, H), Image.LANCZOS)).astype(np.float32) / 255.0
        acc = np.zeros((H, W, 3), np.float32)
        gold = np.clip((86 - yy) / 78.0, 0, 1)                                 # v4 (user: a bit more gold): the wind turns gold as it rises
        for c, (cb, cg) in enumerate(((170, 255), (210, 215), (255, 120))): acc[..., c] += wind * (cb + (cg - cb) * gold) * 0.8
        for a0, d0, r0 in motes:
            u = (t - d0) / 0.5
            if 0 <= u <= 1:
                y = 84 - 76 * u; a = a0 + 6 * u; x = cx + r0 * (1 - 0.45 * u) * math.cos(a)
                g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 3.0) * math.sin(math.pi * u)
                for c, cv in enumerate((255, 220, 110) if a0 > 3.14 else (190, 255, 120)): acc[..., c] += g * cv   # gold + green motes
        if t > 0.55:
            u = (t - 0.55) / 0.45
            fl = np.exp(-((xx - cx) ** 2 + ((yy - 52) / 1.5) ** 2) / (40 + 120 * u)) * (1 - u) ** 1.5
            sh = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - 86) / 0.35) ** 2) - (6 + 40 * u)) / 3.0) ** 2) * (1 - u) * 0.8
            for c, cv in enumerate((255, 230, 150)): acc[..., c] += (fl + sh) * cv   # a golden flash + ring
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def angelwings_flash(n=16):
    """Angel Wings (311) slot 0 (2026-10-16): Water Walking's enchant canvas (64x64, anchor -31/-32), additive, 16
    frames x 3 ticks: a golden halo ring flashing open above the unit, a soft white glow behind it in the shape of two
    spread wings, and a few white feathers drifting down and fading."""
    W = H = 64; cx, cy = 32.0, 30.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3111); out = []
    feathers = [(rnd.uniform(10, 54), rnd.uniform(4, 20), rnd.uniform(0, 0.4), rnd.uniform(-0.6, 0.6)) for _ in range(7)]
    for i in range(n):
        t = i / (n - 1.0); env = math.sin(math.pi * min(1.0, t * 1.1)) ** 0.7
        acc = np.zeros((H, W, 3), np.float32)
        ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - 10) / 0.35) ** 2) - (5 + 5 * min(1.0, t * 2))) / 1.2) ** 2) * env
        for c, cv in enumerate((255, 220, 120)): acc[..., c] += ring * cv
        for sg in (-1, 1):                                                     # the wing-shaped glow
            wx = cx + sg * 14; wing = np.exp(-(((xx - wx) / 11) ** 2 + ((yy - cy + 4 - 0.35 * sg * (xx - cx) * 0) / 9) ** 2)) * 0.45 * env
            wing *= np.clip(1 - np.abs(yy - (cy - 6 + 0.25 * np.abs(xx - cx))) / 12.0, 0, 1)
            for c, cv in enumerate((235, 240, 255)): acc[..., c] += wing * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for fx0, fy0, d0, sw in feathers:                                      # drifting feathers
            u = (t - d0) / 0.6
            if 0 <= u <= 1:
                x = fx0 + 4 * math.sin(u * 5 + sw * 3); y = fy0 + 30 * u; g = int(255 * math.sin(math.pi * u))
                a = sw + 0.6 * math.sin(u * 6); dx, dy = 3 * math.cos(a), 3 * math.sin(a)
                dr.line([(x - dx, y - dy), (x + dx, y + dy)], fill=(g, g, g, 255), width=2)
        out.append(im)
    return out


def angelwings_emblem():
    """Angel Wings (311) unit-enchantment EMBLEM (2026-10-16; user: unit enchantments show their ICON glowing, like the
    others): vanilla does this with ENCHANT.ILB frames (Water Walking 45-49 = its icon glyph at 5 strengths, played
    45..49, 49 x6, 49..45 in the twinkle chain).  Ours: the Angel Wings icon glyph (build_dual_sphere_icons_v1
    .glyph_angelwings, 40x35) centred on 64x64, a white core in a soft warm glow, at 5 strengths (additive)."""
    return _icon_emblem("glyph_angelwings")


def _icon_emblem(glyph_name, tint=(255, 245, 210)):
    """2026-10-16: a unit-enchantment cast EMBLEM from a dual-sphere icon glyph (the vanilla ENCHANT.ILB idea): the glyph
    at 40x35 centred on 64x64, a white core in a soft warm glow, at 5 strengths (additive)."""
    import build_dual_sphere_icons_v1 as _ic
    g = getattr(_ic, glyph_name)().resize((40, 35), Image.BOX)
    m = Image.new("L", (64, 64), 0); m.paste(g, (12, 14))
    a = np.asarray(m).astype(np.float32) / 255.0
    glow = np.asarray(m.filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255.0
    out = []
    for lv in (0.2, 0.4, 0.6, 0.8, 1.0):
        v = (a + 1.2 * glow) * lv
        out.append(Image.fromarray(np.clip(np.dstack([tint[0] * v, tint[1] * v, tint[2] * v]), 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def _icon_emblem_levels(glyph_name, n=12, gamma=1.35, tint=(255, 245, 210)):
    """2026-10-18 (Lucky v3, user: smoother fade-out): _icon_emblem with N strengths instead of 5 - level k = (k/N)^gamma
    so equal steps LOOK equal; the pipeline's _emblem_slot_seq timeline eases through them."""
    import build_dual_sphere_icons_v1 as _ic
    g = getattr(_ic, glyph_name)().resize((40, 35), Image.BOX)
    m = Image.new("L", (64, 64), 0); m.paste(g, (12, 14))
    a = np.asarray(m).astype(np.float32) / 255.0
    glow = np.asarray(m.filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255.0
    out = []
    for k in range(1, n + 1):
        v = (a + 1.2 * glow) * (k / float(n)) ** gamma
        out.append(Image.fromarray(np.clip(np.dstack([tint[0] * v, tint[1] * v, tint[2] * v]), 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def sanctify_strike(n=16):
    """Sanctify (208) slot 2 (2026-10-16): the per-hex landing (96x80, additive, 16 frames x 2 ticks, anchor -48/-40 =
    hex centre (48, 46)): a narrow shaft of white-gold light falls onto the hex, flares, and a flat golden RING of
    light spreads over the ground with a few motes rising from it; all fade together."""
    W, H = 96, 80; cx, cy = 48.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(2081)
    motes = [(rnd.uniform(-20, 20), rnd.uniform(-5, 5), rnd.uniform(0.25, 0.55)) for _ in range(12)]
    hexr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.45) ** 2)                       # ground ellipse radius (hex-sized, not hex-shaped: grid-agnostic)
    for i in range(n):
        t = i / (n - 1.0); env = math.sin(math.pi * min(1.0, t * 1.04)) ** 0.6
        bot = cy - 44 + 44 * min(1.0, t / 0.3)                                     # the shaft reaches the ground at t = 0.3
        shaft = np.exp(-((xx - cx) / (2.4 + 3 * t)) ** 2) * ((yy <= bot) & (yy >= 0)) * np.clip((yy + 4) / 50.0, 0, 1) * (1 - t) ** 0.8
        flare = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.6) ** 2) / (10 + 60 * t)) * max(0.0, 1 - abs(t - 0.32) / 0.3)
        R = 4 + 24 * min(1.0, max(0.0, t - 0.25) / 0.6)
        ring = np.exp(-((hexr - R) / 1.6) ** 2) * (t > 0.25) * (1 - t) * 0.9
        fill = np.exp(-(hexr / (R + 2)) ** 6) * (t > 0.25) * 0.25 * (1 - t)
        v = (0.8 * shaft + 1.1 * flare + ring + fill) * env
        acc = np.zeros((H, W, 3), np.float32)
        for c, cv in enumerate((255, 235, 165)): acc[..., c] += v * cv
        for dx, dy, d0 in motes:
            u = (t - d0) / 0.45
            if 0 <= u <= 1:
                g = np.exp(-((xx - cx - dx) ** 2 + (yy - (cy + dy - 30 * u)) ** 2) / 1.5) * math.sin(math.pi * u)
                for c, cv in enumerate((255, 245, 200)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def sanctify_field(n=12):
    """Sanctify (208) slot 3 (2026-10-16): the consecrated hex, a SEAMLESS 12-frame loop (64x40, centre (32, 20), drawn
    by patch_tc_sanctify_field_v1.py at HXtoHP + (-12, 0) like Gravity Well's field), additive: a faint golden ring
    on the ground with a softly breathing inner glow and six glints running round its rim; low level so the units on
    it stay readable."""
    frames = []; W, H = 64, 40; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); cx, cy = 32.0, 20.0
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.5) ** 2)
    hexr = rr                                                                         # ground ellipse (grid-agnostic)
    for i in range(n):
        t = i / float(n); br = 0.75 + 0.25 * math.cos(2 * math.pi * t)
        rim = np.exp(-((hexr - 21) / 1.3) ** 2) * 0.55
        inner = np.exp(-(hexr / 17.0) ** 4) * 0.22 * br
        glints = np.zeros_like(rr)
        for k in range(6):
            a = 2 * math.pi * (k / 6.0 + t / 6.0)
            gx, gy = cx + 21 * math.cos(a), cy + 10.5 * math.sin(a)
            glints += np.exp(-((xx - gx) ** 2 + ((yy - gy) / 0.7) ** 2) / 2.5)
        v = rim + inner + 0.8 * glints
        acc = np.dstack([v * 255, v * 225, v * 140])
        frames.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return frames


def miracle_sparkles():
    """Miracle (209) slot 0 v3 (2026-10-16, user: v2 crosses messy/janky - more gold-ish but still bright, more glow /
    translucence): 4 frames on Harvest's 38x38 canvas (centre (17, 18)), additive: a SOFT Latin cross drawn at 4x and
    box-downsampled (anti-aliased edges), a warm gold body with a pale-gold core line, wrapped in a wide gold glow; the
    whole thing at ~80 %% so it reads as translucent light; shrinks and dims frame by frame."""
    from PIL import ImageFilter
    out = []; W = H = 38; U = 4; cx, cy = 17.0, 18.0
    for k, sc in enumerate((1.0, 0.76, 0.54, 0.34)):
        big = Image.new("L", (W * U, H * U), 0); d = ImageDraw.Draw(big)
        hw, up, down, arm = (1.25 * sc + 0.35), 9.0 * sc, 14.0 * sc, 7.0 * sc; ay = cy - 3.0 * sc
        d.rectangle([(cx - hw) * U, (cy - up) * U, (cx + hw) * U, (cy + down) * U], fill=255)
        d.rectangle([(cx - arm) * U, (ay - hw) * U, (cx + arm) * U, (ay + hw) * U], fill=255)
        body = np.asarray(big.filter(ImageFilter.GaussianBlur(0.6 * U)).resize((W, H), Image.BOX), np.float32) / 255.0
        thin = Image.new("L", (W * U, H * U), 0); t = ImageDraw.Draw(thin); cw = max(0.25, 0.45 * sc)
        t.rectangle([(cx - cw) * U, (cy - up + 1) * U, (cx + cw) * U, (cy + down - 1) * U], fill=255)
        t.rectangle([(cx - arm + 1) * U, (ay - cw) * U, (cx + arm - 1) * U, (ay + cw) * U], fill=255)
        core = np.asarray(thin.filter(ImageFilter.GaussianBlur(0.5 * U)).resize((W, H), Image.BOX), np.float32) / 255.0
        glow = np.asarray(Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.6 * sc + 1.2)), np.float32) / 255.0
        lvl = 0.82 * (1.0 - 0.15 * k)
        r = (body * 245 + core * 10 + glow * 230) * lvl
        g = (body * 175 + core * 70 + glow * 150) * lvl
        b = (body * 55 + core * 120 + glow * 40) * lvl
        rgb = np.clip(np.dstack([r, g, b]), 0, 255)
        a = 255 * (rgb.max(axis=2) > 6)
        out.append(Image.fromarray(np.dstack([rgb, a]).astype(np.uint8), "RGBA"))
    return out


def deadcall_sparkles():
    """Call of the Dead (211) slot 0 v2 (2026-10-16, user: the particles should start out shaped like ONE BIG SKULL
    before shrinking): 4 frames on the 38x38 canvas (centre (17, 18)), additive: an anti-aliased skull (cranium, cheek
    and jaw, black eye sockets / nose / teeth line) in sickly grave-green with a soft glow, shrinking and dimming."""
    from PIL import ImageFilter
    out = []; W = H = 38; U = 4; cx, cy = 17.0, 18.0
    for k, sc in enumerate((1.04, 0.8, 0.58, 0.38)):
        big = Image.new("L", (W * U, H * U), 0); d = ImageDraw.Draw(big)
        def E(x0, y0, x1, y1, f): d.ellipse([(cx + x0 * sc) * U, (cy + y0 * sc) * U, (cx + x1 * sc) * U, (cy + y1 * sc) * U], fill=f)
        def R(x0, y0, x1, y1, f): d.rectangle([(cx + x0 * sc) * U, (cy + y0 * sc) * U, (cx + x1 * sc) * U, (cy + y1 * sc) * U], fill=f)
        E(-12, -15, 12, 7, 255)                                        # cranium
        R(-7.5, 2, 7.5, 12, 255)                                       # jaw
        E(-9.5, -5, -2, 3, 0); E(2, -5, 9.5, 3, 0)                     # eye sockets
        d.polygon([((cx - 1.6 * sc) * U, (cy + 6.5 * sc) * U), ((cx + 1.6 * sc) * U, (cy + 6.5 * sc) * U), (cx * U, (cy + 3.2 * sc) * U)], fill=0)   # nose
        for xx in (-4.5, -1.5, 1.5, 4.5): R(xx - 0.45, 8.5, xx + 0.45, 12, 0)   # teeth gaps
        body = np.asarray(big.filter(ImageFilter.GaussianBlur(0.5 * U)).resize((W, H), Image.BOX), np.float32) / 255.0
        glow = np.asarray(Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.2 * sc + 1.0)), np.float32) / 255.0
        # v3 (user: brown / black / purple): ALPHA mode (258) with OPAQUE pixels only (soft alpha dithers there): a
        # near-black bone skull shaded brown toward its top, inside a purple glow rim; sockets stay see-through
        yy = np.mgrid[0:H, 0:W][0].astype(np.float32); shade = np.clip(1.0 - (yy - (cy - 15 * sc)) / (27 * sc + 1e-6), 0, 1)
        # v4 (user: hard to tell apart; brown/black with a SOFT purple glow): skull 15 %% bigger (scale below), the rim now a
        # 2-step opaque gradient - a light lavender-purple edge fading to a deep purple outer ring - instead of a flat band
        skull = body > 0.5; inner = (glow > 0.30) & ~skull; outer = (glow > 0.12) & ~skull & ~inner
        r = np.where(skull, 28 + 62 * shade, np.where(inner, 110, 60)); g = np.where(skull, 18 + 34 * shade, np.where(inner, 55, 22))
        b = np.where(skull, 14 + 16 * shade, np.where(inner, 150, 85))   # v5: darker purple rim (user)
        a = 255 * (skull | inner | outer)
        out.append(Image.fromarray(np.dstack([r, g, b, a]).astype(np.uint8), "RGBA"))
    return out


def _dead_skull(sc):
    """One Call of the Dead skull sprite (RGBA, opaque pixels only, for ALPHA 258): near-black bone shaded brown toward
    the crown, a 2-step purple rim (lavender inner incl. the eye sockets, deep purple outer).  sc = 1 is ~27 px tall."""
    from PIL import ImageFilter
    S_ = max(8, int(40 * sc) + 8); U = 4; cx = cy = S_ / 2.0
    big = Image.new("L", (S_ * U, S_ * U), 0); d = ImageDraw.Draw(big)
    def E(x0, y0, x1, y1, f): d.ellipse([(cx + x0 * sc) * U, (cy + y0 * sc) * U, (cx + x1 * sc) * U, (cy + y1 * sc) * U], fill=f)
    def R(x0, y0, x1, y1, f): d.rectangle([(cx + x0 * sc) * U, (cy + y0 * sc) * U, (cx + x1 * sc) * U, (cy + y1 * sc) * U], fill=f)
    E(-12, -15, 12, 7, 255); R(-7.5, 2, 7.5, 12, 255); E(-9.5, -5, -2, 3, 0); E(2, -5, 9.5, 3, 0)
    d.polygon([((cx - 1.6 * sc) * U, (cy + 6.5 * sc) * U), ((cx + 1.6 * sc) * U, (cy + 6.5 * sc) * U), (cx * U, (cy + 3.2 * sc) * U)], fill=0)
    for xx in (-4.5, -1.5, 1.5, 4.5): R(xx - 0.45, 8.5, xx + 0.45, 12, 0)
    body = np.asarray(big.filter(ImageFilter.GaussianBlur(0.5 * U)).resize((S_, S_), Image.BOX), np.float32) / 255.0
    glow = np.asarray(Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.0 * sc + 0.8)), np.float32) / 255.0
    yy = np.mgrid[0:S_, 0:S_][0].astype(np.float32); shade = np.clip(1.0 - (yy - (cy - 15 * sc)) / (27 * sc + 1e-6), 0, 1)
    skull = body > 0.5; inner = (glow > 0.30) & ~skull; outer = (glow > 0.12) & ~skull & ~inner
    r = np.where(skull, 28 + 62 * shade, np.where(inner, 110, 60)); g = np.where(skull, 18 + 34 * shade, np.where(inner, 55, 22))
    b = np.where(skull, 14 + 16 * shade, np.where(inner, 150, 85)); a = 255 * (skull | inner | outer)   # = the burst (slot 0 v5) colours
    return Image.fromarray(np.dstack([r, g, b, a]).astype(np.uint8), "RGBA")


def _white_skull(sc):
    """A glowing WHITE skull sprite for additive (770) drawing, like the raise burst's skulls in game: bone-white body,
    dark (= transparent in additive) eye sockets / nose / teeth, a soft pale glow round it."""
    from PIL import ImageFilter
    S_ = max(8, int(44 * sc) + 10); U = 4; cx = cy = S_ / 2.0
    big = Image.new("L", (S_ * U, S_ * U), 0); d = ImageDraw.Draw(big)
    def E(x0, y0, x1, y1, f): d.ellipse([(cx + x0 * sc) * U, (cy + y0 * sc) * U, (cx + x1 * sc) * U, (cy + y1 * sc) * U], fill=f)
    def R(x0, y0, x1, y1, f): d.rectangle([(cx + x0 * sc) * U, (cy + y0 * sc) * U, (cx + x1 * sc) * U, (cy + y1 * sc) * U], fill=f)
    E(-12, -15, 12, 7, 255); R(-7.5, 2, 7.5, 12, 255); E(-9.5, -5, -2, 3, 0); E(2, -5, 9.5, 3, 0)
    d.polygon([((cx - 1.6 * sc) * U, (cy + 6.5 * sc) * U), ((cx + 1.6 * sc) * U, (cy + 6.5 * sc) * U), (cx * U, (cy + 3.2 * sc) * U)], fill=0)
    for xx in (-4.5, -1.5, 1.5, 4.5): R(xx - 0.45, 8.5, xx + 0.45, 12, 0)
    body = np.asarray(big.filter(ImageFilter.GaussianBlur(0.5 * U)).resize((S_, S_), Image.BOX), np.float32) / 255.0
    glow = np.asarray(Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.4 * sc + 0.8)), np.float32) / 255.0
    # v3 (user: like the burst skulls, a bit more translucent, a DARKER purple glow): body pale bone at ~75 %%, glow deep purple
    b = body * 0.75; gl = np.clip(glow - body * 0.6, 0, 1) * 0.9
    return np.dstack([b * 240 + gl * 95, b * 235 + gl * 30, b * 245 + gl * 135]), np.dstack([glow * 95, glow * 30, glow * 135])


def deadcall_spiral(n=30):
    """Call of the Dead (211) slot 1 v4 (2026-10-16, user: the movement is good but the skulls must look EXACTLY like the
    raise-burst skulls; the burst ones unchanged).  RE: the burst = kind-0x1F sparkles drawn through GFXE's INTENSITY blend
    table at L ~ 80-100 - the same table drawMode 770 picks with blendValue = L - so the burst's 'white skull + smooth
    purple glow' is just the slot-0 DARK pixels (_dead_skull colours) ADDED onto the ground (out = d + 1.75*f*s^2/(s+d)).
    So: identical _dead_skull pixels on pure black, drawMode 770 blend 95; the trail = past positions holding only the
    purple RIM pixels at half strength (intensity adds ~s^2, so it fades softly).  Motion as v2/v3: grow in on R 44,
    accelerating spin (2 turns x t^2.2), spiral in, shrink at the end; 96x96, -48/-48, 30 frames x 3 ticks."""
    out = []; W = H = 96; cx, cy = 48.0, 50.0; dt = 1.0 / (n - 1.0)
    for i in range(n):
        t = i / (n - 1.0)
        R = 44.0 * (1 - t ** 1.7); rot = 2 * math.pi * 2.0 * t ** 2.2
        grow = min(1.0, t / 0.25); fade = 1.0 if t < 0.75 else max(0.0, 1 - (t - 0.75) / 0.25)
        sc = 0.78 * grow * (0.3 + 0.7 * fade)
        acc = np.zeros((H, W, 3), np.float32)
        if sc > 0.08:
            sp = np.asarray(_dead_skull(sc)).astype(np.float32); h_, w_ = sp.shape[:2]
            body = sp[..., 3] > 0; rgb = sp[..., :3] * body[..., None]
            rim = rgb * ((rgb[..., 2] > rgb[..., 0]) & (rgb[..., 2] > 70))[..., None]     # the purple rim pixels only
            from PIL import ImageFilter as _IF                                              # blurred -> a smooth smear, not ring copies
            rim = np.dstack([np.asarray(Image.fromarray(rim[..., c].astype(np.uint8)).filter(_IF.GaussianBlur(1.6)), np.float32) * 1.6 for c in range(3)])
            def put(img, a, R_, mode):
                x = int(round(cx + R_ * math.cos(a) - w_ / 2)); y = int(round(cy + 0.55 * R_ * math.sin(a) - h_ / 2))
                x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + w_), min(H, y + h_)
                if x1 <= x0 or y1 <= y0: return
                src = img[y0 - y:y1 - y, x0 - x:x1 - x]
                if mode == "over":
                    m_ = body[y0 - y:y1 - y, x0 - x:x1 - x][..., None]; acc[y0:y1, x0:x1] = np.where(m_, src, acc[y0:y1, x0:x1])
                else:
                    acc[y0:y1, x0:x1] = np.maximum(acc[y0:y1, x0:x1], src)
            for k in range(5):
                for j in range(6, 0, -1):                                       # purple trail along the skull's past path
                    tp = max(0.0, t - j * dt * 0.5)
                    put(rim * (0.55 * (1 - j / 7.0)), 2 * math.pi * 2.0 * tp ** 2.2 + 2 * math.pi * k / 5, 44.0 * (1 - tp ** 1.7), "max")
            for k in range(5):
                put(rgb, rot + 2 * math.pi * k / 5, R, "over")
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out




def gust_wisp(n=8):
    """Gust (212) slot 0 v2 (2026-10-16, user: the v1 wisps suck - make it more like Winds of Fury's particles): Winds of
    Fury's own PARTICLE.ILB 18-20 (soft blue-white glow orbs, additive) at 2x (38x38) and brighter, each smeared a little
    sideways (a gust-blown streak) - played like WoF's [18, 19, 20, 19] cycle along the breath fan."""
    from PIL import ImageFilter
    lib = ilbcodec.read(PARTICLE); out = []
    for src in (18, 19, 20):
        im, r = raw_pixels(lib, src); a = np.asarray(im.convert("RGB")).astype(np.float32)
        big = np.asarray(Image.fromarray(a.astype(np.uint8)).resize((38, 38), Image.BICUBIC)).astype(np.float32)
        smear = np.zeros_like(big)
        for dx in range(-6, 7):                                    # sideways wind smear (decaying copies)
            w = math.exp(-abs(dx) / 3.0) * (0.55 if dx else 1.0)
            smear = np.maximum(smear, np.roll(big, dx, axis=1) * w)
        out.append(Image.fromarray(np.clip(smear * 1.35, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def crosswind_motes():
    """Crosswind (213) slot 0 (2026-10-16): High Prayer's per-unit particle twinkle (PARTICLE 12-14, 16x16 at -8/-8)
    re-done as WIND: 3 frames of a small pale blue-white air streak - a curved dash with a curl at its head - drifting
    and fading (additive 770)."""
    out = []; W = H = 16
    for k in range(3):
        acc = np.zeros((H, W, 3), np.float32); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        lvl = (1.0, 0.75, 0.45)[k]; x0 = 2 + 2 * k
        for t in np.linspace(0, 1, 40):
            x = x0 + 9 * t; y = 9 - 2.5 * math.sin(t * math.pi * 0.9)
            if t > 0.75:                                                          # the curl at the head
                u = (t - 0.75) / 0.25; a = u * math.pi * 1.4
                x = x0 + 9 * 0.75 + 2.6 * math.sin(a); y = 7.0 - 2.6 * (1 - math.cos(a))
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 0.9) * (0.35 + 0.65 * t)
            for c, cv in enumerate((215, 230, 255)): acc[..., c] = np.maximum(acc[..., c], g * cv * lvl)
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def crosswind_gust(n=24):
    """Crosswind (213) slot 1 (2026-10-16): replaces High Prayer's per-unit dome (MAGIC 89-109 at -41/-61) with a GUST
    sweeping across the unit (82x72, additive 770, 24 frames x 2 ticks): five wind streaks at spread heights, each one
    path = a gentle S across the canvas ending in a tightening spiral curl (the reference art's swirls); a moving
    window of the path is drawn bright at its head and fading to the tail, plus a few dust motes; fade over the last
    third."""
    W, H = 82, 72; rnd = random.Random(2131); out = []
    rows = [16, 27, 38, 49, 60]
    streaks = [(y0, 0.06 * k + rnd.uniform(0, 0.05), rnd.uniform(0.85, 1.05), (-1) ** k) for k, y0 in enumerate(rows)]
    motes = [(rnd.uniform(10, 62), rnd.uniform(0.0, 0.5), rnd.uniform(0.6, 1.1)) for _ in range(10)]
    def path(y0, sgn, m=90):
        pts = []
        for k in range(m):                                                  # 0..0.7: the S sweep, 0.7..1: the curl
            s_ = k / (m - 1.0)
            if s_ <= 0.7:
                x = -8 + 66 * s_ / 0.7; y = y0 + sgn * 3.5 * math.sin(s_ / 0.7 * math.pi)
            else:
                u = (s_ - 0.7) / 0.3; a = u * math.pi * 1.7; r = 7.0 * (1 - 0.55 * u)
                cx, cy = 58.0, y0 - sgn * 7.0
                x = cx + r * math.sin(a); y = cy + sgn * r * math.cos(a)
            pts.append((x, y))
        return pts
    for i in range(n):
        t = i / (n - 1.0); fade = 1.0 if t < 0.66 else max(0.0, 1 - (t - 0.66) / 0.34)
        im = Image.new("RGB", (W, H), (0, 0, 0)); d = ImageDraw.Draw(im)
        for y0, delay, spd, sgn in streaks:
            u = max(0.0, min(1.0, (t - delay) * 1.9 * spd))
            if u <= 0: continue
            P = path(y0, sgn); m = len(P); hi = int(u * (m - 1)); lo = max(0, hi - 45)
            for k in range(lo, hi):
                w = (k - lo) / max(1.0, hi - lo); c = int(240 * fade * (0.12 + 0.88 * w))
                d.line([P[k], P[k + 1]], fill=(int(c * 0.86), int(c * 0.93), c), width=2 if w > 0.55 else 1)
        for x0, delay, spd in motes:
            u = (t - delay) * spd
            if 0 < u < 1:
                x = 4 + 74 * u; y = x0 * 0.9 - 6 * math.sin(u * math.pi); c = int(200 * fade * math.sin(u * math.pi))
                d.ellipse([x - 0.8, y - 0.8, x + 0.8, y + 0.8], fill=(c, c, c))
        out.append(im.filter(ImageFilter.GaussianBlur(0.6)).convert("RGBA"))
    return out


def suspend_lift(n=96, OVY=22):
    """Suspend (214) slot 0 v2 (2026-10-16, user: pretty good but more GLOWY / translucent, and WIDEN at the top instead
    of narrowing): 96x96 additive, anchor -48/-86 (unit feet ~y 86): three helical wind ribbons rising round the unit,
    their radius OPENING from 10 px at the ground to 26 px at the top (a funnel), drawn soft (blurred glow + a thin
    core at ~60 %%) over an updraft glow that also widens upward; rising motes; fades out over the last third."""
    from PIL import ImageFilter
    W, H = 96, 128; cx = 48.0; OY = 18; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2140)   # v3: canvas 128 tall (anchor -48/-104), old content +18 px
    status = suspend_status()
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(8, 20), rnd.uniform(0, 1)) for _ in range(26)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); fade = 1.0 if t < 0.55 else max(0.0, 1 - (t - 0.55) / 0.45) ** 1.4   # v7 (user): longer (96 fr), rises slower, spins faster,
        dis = 0.0 if t < 0.55 else (t - 0.55) / 0.45                                     #   and GROWS + dissipates as it fades out
        gu = min(1.0, t / 0.55); grow = gu * gu * (3 - 2 * gu)
        acc = np.zeros((H, W, 3), np.float32)
        half = 8.0 + 18.0 * np.clip((88 + OY - yy) / 70.0, 0, 1)                       # glow column widening upward
        glow = np.exp(-((xx - cx) / half) ** 2) * np.clip((yy - 14 - OY) / 72.0, 0, 1) * 0.20 * grow * fade
        for c, cv in enumerate((150, 210, 255)): acc[..., c] += glow * cv
        rib = Image.new("RGB", (W, H)); dr = ImageDraw.Draw(rib)
        ring_lv = fade * max(0.0, 1.0 - grow * 1.6)                                    # v4 (user): it starts as ONE ring at the bottom...
        if ring_lv > 0: dr.ellipse([cx - 11, 88 + OY - 3.2, cx + 11, 88 + OY + 3.2], outline=(int(170 * ring_lv), int(225 * ring_lv), int(255 * ring_lv)), width=3)
        for k in range(3):
            pts = []
            for s_ in range(48):
                u = s_ / 47.0; y = 88 + OY - u * 72 * grow * (1 + 0.12 * dis); ph = 6.28 * (u * 1.5 + t * 3.5) + k * 2.09
                r = (10 + 16 * u) * (1 + 0.55 * dis); x = cx + r * math.cos(ph); y += 0.25 * r * math.sin(ph)
                pts.append((x, y, math.sin(ph)))
            for a, b in zip(pts, pts[1:]):
                lv = (0.5 + 0.5 * (a[2] > 0)) * fade
                dr.line([a[:2], b[:2]], fill=(int(170 * lv), int(225 * lv), int(255 * lv)), width=3)
        soft = np.asarray(rib.filter(ImageFilter.GaussianBlur(2.2 + 3.0 * dis)), np.float32) * 1.6     # the glow round each ribbon (blurs out as it dissipates)
        core = np.asarray(rib, np.float32) * 0.45 * (1 - dis)                                          # a thin translucent core
        acc += soft + core
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB"); dr = ImageDraw.Draw(im)
        for a0, r, ph in motes:
            u = (t * 1.3 + ph) % 1.0; y = 88 + OY - u * 76; x = cx + r * (1 + 0.5 * u) * math.cos(a0 + 6 * u)
            lv = fade * math.sin(math.pi * u) * 0.8
            dr.point((x, y), fill=(int(220 * lv), int(245 * lv), int(255 * lv)))
        fin = min(1.0, max(0.0, (t - 0.35) / 0.35)) * (1.0 - 0.65 * min(1.0, max(0.0, (t - 0.85) / 0.15)))   # v8 (RE): in 35-70 %, dip to 0.35 over the last 15 % (meets the overlay's fade-in at 12/60)
        if fin > 0:                                                                 #   (same pixels + position as the status overlay: x + 25)
            st = np.asarray(status[i % len(status)].convert("RGB"), np.float32) * fin
            a_ = np.asarray(im, np.float32); a_[:H - OVY, 24:24 + 48] = np.maximum(a_[:H - OVY, 24:24 + 48], st[OVY:] * 0.75)   # (RE) overlay = cast + (24, -22) once the unit is Flying
            im = Image.fromarray(np.clip(a_, 0, 255).astype(np.uint8), "RGB")
        out.append(im.convert("RGBA"))
    return out


def _ss_dome_glow(xx, yy, cx, cy, rx, ry):
    """Fire Halo's dome SHAPE as a soft glow (no ring): brightest just inside the outline, fading inward, and OPEN at
    the bottom (it fades out below the dome's middle, like Fire Halo's dome round the figure's legs)."""
    e = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    shell = np.where(e < 1.0, e ** 3, np.exp(-((e - 1.0) / 0.06) ** 2))
    return shell * np.clip((cy + 0.45 * ry - yy) / (0.55 * ry), 0, 1)


def _ss_dome_arcs(dr, cx, cy, rx, ry, rnd, lv, n_arcs, jit, inner, ew=3, blue=0.0, n_skinny=0):
    """Lightning-Altar-style crackle on a Fire-Halo-shaped dome (shared by the cast aura and the status loop): n_arcs
    short zig-zag arcs (blue-violet edge, white core) running along the dome outline, angles -25..205 deg (the bottom
    left open like Fire Halo's dome), plus `inner` small sparks/forks inside the dome.  lv = brightness 0..1."""
    def mix(c0, c1): return tuple(int((a + (b - a) * blue) * lv) for a, b in zip(c0, c1))       # v6: white -> blue (~60 %% of Chain Lightning's)
    edge = mix((120, 120, 235), (70, 110, 255)); core = mix((235, 235, 255), (160, 195, 255))
    for k in range(n_arcs):
        a0 = rnd.uniform(-10, 190); span = rnd.uniform(28, 58) * (1 if rnd.random() < 0.5 else -1)
        segs = rnd.randint(4, 6); pts = []
        for s_ in range(segs + 1):
            a = math.radians(a0 + span * s_ / segs); j = 1.0 + (rnd.uniform(-jit, jit) if 0 < s_ < segs else 0.0)
            pts.append((cx + rx * j * math.cos(a), cy - ry * j * math.sin(a)))
        dr.line(pts, fill=edge, width=ew); dr.line(pts, fill=core, width=1)
    for k in range(inner):                                                  # small forks inside, like the Altar's sparks
        a = math.radians(rnd.uniform(20, 160)); r_ = rnd.uniform(0.35, 0.8)
        x0, y0 = cx + rx * r_ * math.cos(a), cy - ry * r_ * math.sin(a); pts = [(x0, y0)]
        for s_ in range(3):
            x0 += rnd.uniform(-0.18, 0.18) * rx; y0 += rnd.uniform(-0.18, 0.18) * ry; pts.append((x0, y0))
        dr.line(pts, fill=edge, width=2); dr.line(pts, fill=core, width=1)
    for k in range(n_skinny):                                               # v6 (user): more INTERIOR arcs, very skinny
        a = math.radians(rnd.uniform(25, 155)); r0 = rnd.uniform(0.25, 0.75)
        x0, y0 = cx + rx * r0 * math.cos(a), cy - ry * r0 * math.sin(a); pts = [(x0, y0)]
        for s_ in range(4):
            x0 += rnd.uniform(-0.16, 0.16) * rx; y0 += rnd.uniform(-0.13, 0.13) * ry; pts.append((x0, y0))
        dr.line(pts, fill=core, width=1)


def staticshield_aura(n=30):
    """Static Shield (215) slot 0 v4 (2026-10-16, user: the lightning should last longer (it can overlap the orb, the
    orb starting later); the orb must hand over SMOOTHLY to the status aura - v3 ended larger than the aura and sat
    ~20 px higher - and the static should be thinner).  96x128 additive (anchor -48/-86 = unit origin at (48, 86); the
    canvas now extends below the origin so the dome fits).  Frames 0-11: the vanilla storm bolt (Lightn.ILB 0/5/8)
    flickers on the unit, fading over 8-11; frames 5-23: the Altar-style dome (thin arcs) grows in and SHRINKS from 2x
    to the status aura's exact dome (rx 20.5, ry 19.5, centred like the overlay: unit origin + (0, 1.5)); frames 24-29
    ARE the status overlay's frames 0-5 pasted at its own offset (-22/-21 from the unit origin) = a seamless hand-off."""
    from PIL import ImageFilter
    W, H = 96, 128; cx, oy = 48.0, 86.0; out = []
    status = staticshield_status()
    lib = ilbcodec.read(open(os.path.join(GAME, "Images", "Effects", "Lightn.ILB"), "rb").read())
    bolts = []
    for src in (0, 5, 8):
        im, r = raw_pixels(lib, src); bb = im.getbbox(); im = im.crop(bb)
        sc = 100.0 / im.height; bolts.append(im.resize((max(1, int(im.width * sc)), 100), Image.LANCZOS))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    SX, SY = 25, 51                                                          # v6 (RE): overlay pixel (px, py) = cast pixel (px + 25, py + 51) for a ground unit
    rx1, ry1, cy1 = 20.5, 19.5, SY + 22.5                                  # = staticshield_status's dome in cast coords
    for i in range(n):
        rnd = random.Random(2150 + 7 * i); acc = np.zeros((H, W, 3), np.float32)
        if i < 12:                                                          # the strike, flickering, longer
            lv = (1.0 if i < 8 else 1.0 - (i - 7) / 5.0) * (0.75 if i % 3 == 2 else 1.0)
            b = bolts[[0, 1, 2, 1, 0, 2, 1, 0, 2, 0, 1, 2][i]]; lay = Image.new("RGB", (W, H)); bx = int(cx - b.width / 2)
            lay.paste(b.convert("RGB"), (bx, int(cy1 + ry1 - b.height)), mask=b.split()[3])
            acc += np.asarray(lay, np.float32) * np.array([0.85, 1.0, 1.45], np.float32) * 1.15 * lv   # v5: bluer, like Chain Lightning
            flash = np.exp(-((xx - cx) ** 2 + ((yy - (cy1 + ry1 - 6)) / 0.7) ** 2) / (90 + 40 * min(i, 6))) * lv * (1.2 if i < 2 else 0.6)
            for c, cv in enumerate((120, 160, 255)): acc[..., c] += flash * cv
        if 5 <= i < 24:                                                     # the dome: grows in at 2x, shrinks to the aura
            u = (i - 5) / 18.0; s_ = 2.0 - (1 - (1 - u) ** 2); lv = min(1.0, (i - 4) / 4.0)
            rx, ry = rx1 * s_, ry1 * s_; cy = cy1 + ry1 - ry                # bottom stays on the aura's bottom
            glowd = _ss_dome_glow(xx, yy, cx, cy, rx, ry) * 0.26 * lv
            bl = u                                                          # v6 (user): white -> blue during the shrink
            for c, cv in enumerate((90 - 30 * bl, 100 - 5 * bl, 230 + 10 * bl)): acc[..., c] += glowd * cv
            lay = Image.new("RGB", (W, H)); dr = ImageDraw.Draw(lay)
            _ss_dome_arcs(dr, cx, cy, rx, ry, rnd, 0.85 * lv, n_arcs=int(4 + 2 * (s_ - 1)), jit=0.10, inner=0, ew=2 if s_ > 1.4 else 1, blue=bl, n_skinny=3)
            arc = np.asarray(lay, np.float32); soft = np.asarray(lay.filter(ImageFilter.GaussianBlur(1.0 + 0.6 * (s_ - 1))), np.float32)
            acc += arc * 0.8 + soft * 1.0
        if i >= 24:                                                         # = the status overlay itself
            st = np.asarray(status[(i - 24) % len(status)].convert("RGB"), np.float32)
            x0, y0 = SX, SY; acc[y0:y0 + 42, x0:x0 + 44] = np.maximum(acc[y0:y0 + 42, x0:x0 + 44], st)
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def staticshield_status(n=96):
    """Static Shield (215) 0xC4 STATUS OVERLAY v4 (2026-10-16, user: slower with MORE frames; the outer shell should look
    'skippy/jumpy', with inner arcs that appear SUDDENLY then slowly fade away): Fire Halo's canvas (44x42, -22/-21),
    additive, blue.  48-frame seamless loop: the outer dome crackle is re-drawn only every 6 frames (held, then jumps to a
    new shape); 8 skinny interior arcs are born at staggered frames at full brightness and fade over 14 frames each."""
    from PIL import ImageFilter
    W, H = 44, 42; cx, feet = 22.0, 41.0; rx, ry = 20.5, 19.5; cy = feet - ry * 0.95; out = []
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    inner = []                                                              # (birth frame, seeded shape)
    rnd0 = random.Random(2217)
    for k in range(11):                                                     # v6 (user): every inner arc STARTS ON the outer shell and
        birth = k * 9 + rnd0.randint(0, 3)                                  #   runs inward; it only appears where the shell is (a shell
        a = (168, 22, 128, 62, 196, -12, 146, 38, 100, 182, 8)[k] + rnd0.uniform(-5, 5)   # v7 (user): spread + alternating sides (no two close on one side)
        x0, y0 = cx + rx * math.cos(math.radians(a)), cy - ry * math.sin(math.radians(a))   #   arc 10 = the lower-right one
        y0 = min(y0, feet - 2); pts = [(x0, y0)]
        nseg = rnd0.choice((3, 4, 4, 5, 6)); tx, ty = cx - x0, (cy + 2) - y0; L_ = math.hypot(tx, ty) or 1.0
        dang = math.atan2(ty, tx); bend = rnd0.choice((-1, 1)) * rnd0.uniform(0.25, 0.45)   # v8 (user: some too straight): each arc BENDS
        for s_ in range(nseg):                                                   #   (heading turns every step) + a zig-zag kink
            dang += bend * (0.6 + 0.8 * rnd0.random()); zz = (0.07 if s_ % 2 else -0.07)
            x0 += math.cos(dang) * rx * 0.10 + (-math.sin(dang)) * zz * rx + rnd0.uniform(-0.03, 0.03) * rx
            y0 += math.sin(dang) * ry * 0.10 + math.cos(dang) * zz * ry + rnd0.uniform(-0.03, 0.03) * ry
            x0 = min(W - 2, max(1, x0)); y0 = min(feet - 2, max(1, y0)); pts.append((x0, y0))
        inner.append((birth, pts, a))
    for i in range(n):
        acc = np.zeros((H, W, 3), np.float32)
        glowd = _ss_dome_glow(xx, yy, cx, cy, rx, ry) * 0.24
        for c, cv in enumerate((60, 95, 240)): acc[..., c] += glowd * cv
        lay = Image.new("RGB", (W, H)); dr = ImageDraw.Draw(lay)
        rnd = random.Random(2190 + 11 * (i // 2))                            # v5: outer shell jumps every 2 frames (6 ticks) - faster, jumpier
        _ss_dome_arcs(dr, cx, cy, rx, ry, rnd, 0.85, n_arcs=4, jit=0.10, inner=0, ew=1, blue=1.0, n_skinny=0)
        for birth, pts, a in inner:                                          # inner arcs: sudden, then a slow fade (cyclic)
            age = (i - birth) % n
            if age < 23:
                lv = (1 - age / 23.0) ** 1.3
                dr.line(pts, fill=(int(160 * lv), int(195 * lv), int(255 * lv)), width=1)
            if age < 4:                                                      # the shell crackles through the arc's root as it fires
                sp = []; rs = random.Random(int(a * 10) + age)
                for s_ in range(6):
                    aa = math.radians(a - 18 + 36 * s_ / 5.0); jj = 1.0 + (rs.uniform(-0.08, 0.08) if 0 < s_ < 5 else 0)
                    sp.append((cx + rx * jj * math.cos(aa), min(feet - 1, cy - ry * jj * math.sin(aa))))
                dr.line(sp, fill=(160, 195, 255), width=1)
        arc = np.asarray(lay, np.float32); soft = np.asarray(lay.filter(ImageFilter.GaussianBlur(1.0)), np.float32)
        acc += arc * 0.8 + soft * 1.0
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def xwind_cloud(src=160, n=30):
    """Crosswind (213) map-wide wash, slots 2 / 4 (2026-10-16, user: like the level-4 globals - Air Mastery's clouds
    washing across the map): ONE of Air Mastery's own cloud images (Magic.ILB 160 / 162, 201x118 streaky clouds,
    colour-keyed) drifting left -> right across a 300x160 canvas (hex centre at (150, 80), entry -150/-80), fading
    in over the first quarter and out over the last third.  Additive 770 (= GFXE Intensity, like Air Mastery's own
    770/30), stored on black.  One driver per grid point of the battlefield (patch_tc_crosswind_fx_v1.py), so the whole
    field fills with clouds drifting the same way = a wash."""
    lib = ilbcodec.read(MAGIC); im, r = raw_pixels(lib, src)
    cl = np.asarray(im).astype(np.float32); a = (cl[..., 3:4] > 0).astype(np.float32); rgb = cl[..., :3] * a
    H_, W_ = rgb.shape[:2]; W, H = 300, 160; out = []
    for i in range(n):
        t = i / (n - 1.0)
        lvl = min(1.0, t / 0.25) * min(1.0, (1 - t) / 0.33)
        x0 = int(round(5 + 90 * t)); y0 = int(round((H - H_) / 2 + 6 * math.sin(t * math.pi)))
        acc = np.zeros((H, W, 3), np.float32)
        xs0, ys0 = max(0, x0), max(0, y0); xs1, ys1 = min(W, x0 + W_), min(H, y0 + H_)
        acc[ys0:ys1, xs0:xs1] = rgb[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0] * lvl
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def xwind_motes(n=30):
    """Crosswind (213) map-wide wash, slot 3 (2026-10-16, user: white glowing particles like Winds of Fury washing across
    the map): 18 white glowing motes (a bright core in a soft pale-blue halo, each with a short fading trail of 4 ghost
    dots) blown left -> right across a 300x160 canvas (entry -150/-80) with a gentle wave, each fading in and out on
    its own phase.  Additive 770 on black.  Deterministic (seeded)."""
    W, H = 300, 160; rnd = random.Random(2130); yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    motes = [(rnd.uniform(-60, 120), rnd.uniform(15, H - 15), rnd.uniform(150, 230), rnd.uniform(0, 6.28),
              rnd.uniform(0.0, 0.35), rnd.uniform(0.75, 1.25)) for _ in range(18)]
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W), np.float32)
        for x0, y0, dist, ph, t0, sz in motes:
            u = (t - t0) / 0.65
            if not 0 <= u <= 1: continue
            lvl = math.sin(math.pi * u) ** 0.7
            for k in range(12):                                     # the mote + an 11-step fading streak
                uk = max(0.0, u - k * 0.012)
                x = x0 + dist * uk; y = y0 + 7 * math.sin(ph + uk * 5.0)
                rr = (xx - x) ** 2 + (yy - y) ** 2
                g = lvl * (1.0 - k / 12.0) ** 1.8
                acc += g * (0.8 * np.exp(-rr / (2.0 * sz)) + 0.25 * np.exp(-rr / (14.0 * sz)))
        acc = np.clip(acc, 0, 1.4)
        rgb = np.dstack([acc * 225, acc * 235, acc * 255])
        out.append(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out



def suspend_status(n=100):
    """Suspend (214) STATUS OVERLAY (2026-10-16, user: like Entangled - a very subtle beam of WHITE light, like Repent's
    but white and very very subtle, with small white particles slowly spinning upwards around it).  Ability.pfs record
    205 tag 8 (patch_suspend_ability_pfs_v1.py v2) -> drawn every frame by TTacticalCombatUnitHS.Show's overlay loop
    (patch_tc_suspend_overlay_v1.py) at xs -23 / ys -104.  48x128, ADDITIVE 770 (GFXE Intensity: out = d + 1.75*f*s^2/
    (s+d), black = invisible - so the beam is stored DIM and adds only a faint glow), 24 frames x 2 ticks, seamless
    loop: a narrow soft white column fading out at both ends with a slow shimmer, and 6 small white motes on a helix
    (radius 10, flattened) each rising once per loop while turning one full turn - brighter in front, dimmer behind."""
    W, H = 48, 128; cx = 24.0; y_top, y_bot = 34.0, 118.0      # v2 (user 10/16): beam shorter (top 6 -> 34), 40 frames (slower, smoother), tighter coil
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    vert = np.clip((yy - y_top) / 22.0, 0, 1) * np.clip((y_bot - yy) / 16.0, 0, 1)
    for i in range(n):
        t = i / float(n)
        shim = 0.85 + 0.15 * np.sin(2 * math.pi * (t * 2 + yy / 40.0))
        beam = (np.exp(-((xx - cx) / 2.2) ** 2) * 0.45 + np.exp(-((xx - cx) / 6.0) ** 2) * 0.18) * vert * shim
        acc = beam * 120.0
        for k in range(6):
            u = (t + k / 6.0) % 1.0
            a = 2 * math.pi * (t + k / 6.0) + u * 2 * math.pi * 1.0
            x = cx + 7.0 * math.cos(a); y = y_bot - 4 - u * (y_bot - y_top - 12); z = math.sin(a)
            fade = min(1.0, u / 0.15) * min(1.0, (1 - u) / 0.2)
            lvl = (0.55 + 0.45 * z) * fade
            acc = acc + np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * 210.0 * lvl
        rp = t                                                                     # v4 (user): a subtle white RING below the unit rising very slowly
        for off_, lv_ in ((0.0, 1.0), (0.09, 0.7)):                                 # v8 (user): a DOUBLE ring (a 2nd follows close behind), subtler,
            rp = (t * 5.0 - off_) % 1.0                                               #   5 per loop (reappears sooner), shorter fade-out
            ry_c = 125.0 - rp * 32.0; rr = 14.0 + 7.0 * rp
            rfade = min(1.0, rp / 0.2) ** 1.5 * (1.0 if rp < 0.7 else (1 - rp) / 0.3)
            ell = np.sqrt(((xx - cx) / rr) ** 2 + ((yy - ry_c) / (rr * 0.28)) ** 2)
            acc = acc + np.exp(-((ell - 1.0) / 0.12) ** 2) * 95.0 * rfade * lv_
        v = np.clip(acc, 0, 255)
        out.append(Image.fromarray(np.dstack([v, v, np.clip(v * 1.04, 0, 255)]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def gust_shock():
    """Gust (212) slot 1 v3 (2026-10-16, user: make it like SHOCKWAVE's particles but only going forward): vanilla
    Shockwave's own particle sprite (PARTICLE.ILB 0-2, the 19x19 blue-white glow orbs its kind-0x1F swarm draws) with
    most of the blue drained into a pale silver-white wind mote (a breath of cyan kept).  Drawn by kind-0x1F particles
    through GFXE's intensity table (the image's drawMode is ignored there), fading over each particle's path."""
    lib = ilbcodec.read(PARTICLE); out = []
    for src in (0, 1, 2):
        im, r = raw_pixels(lib, src); a = np.asarray(im.convert("RGB")).astype(np.float32)
        g = a.max(axis=2, keepdims=True)                                   # v4 (user): WHITER, less blue
        a = a * 0.08 + g * 0.92
        a = a * np.array([1.0, 1.0, 1.02], np.float32)
        out.append(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out



def xwind_cloudset():
    """Crosswind (213) v3 field wash: Air Mastery's OWN cloud images (MAGIC.ILB 160 / 161 / 162 'Cloud01-03', 201x118)
    copied 1:1.  The group table stores this set five times at intensity 6 / 12 / 18 / 24 / 30 (Air Mastery draws them at
    770 / 30) so a 30-frame driver sequence can fade each cloud in and out while patch_tc_crosswind_fx_v1 v3 drifts it
    across the field with the Winds of Fury particles."""
    lib = ilbcodec.read(MAGIC); out = []
    for src in (160, 161, 162):
        im, r = raw_pixels(lib, src); out.append(im.convert("RGBA"))
    return out


def xwind_swirl(n=32):
    """Crosswind (213) v3 per-ENEMY swirl (user: no 'bubbles' over the targets - a very subtle animation like Suspend's
    spinning motes, going round them, gone when the spell's gfx is over): 64x80, additive 770, centre (32, 46) = 16 px
    above the hex centre (driver at hex centre, anchor -32/-62).  Five small white motes circle the unit on a flattened
    ring (rx 20, ry 7) with a short fading trail and a gentle bob, the back half dimmer (behind the unit); seamless
    32-frame loop (one turn).  Stored dim - additive at 70 (and a 30 copy for the fade in / out)."""
    W, H = 64, 80; cx, cy = 32.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for i in range(n):
        t = i / float(n); acc = np.zeros((H, W), np.float32)
        for k in range(5):
            for j in range(4):                                         # the mote + 3 trailing ghosts
                a = 2 * math.pi * (t + k / 5.0) - j * 0.16
                x = cx + 20.0 * math.cos(a); y = cy + 7.0 * math.sin(a) - 2.5 * math.sin(2 * math.pi * (2 * t + k / 5.0))
                front = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(a))
                lv = front * (1.0, 0.45, 0.25, 0.12)[j]
                acc += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (1.2 if j == 0 else 1.6)) * 225.0 * lv
        v = np.clip(acc, 0, 255)
        out.append(Image.fromarray(np.dstack([v, v, np.clip(v * 1.05, 0, 255)]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def xwind_swirl2(n=60):
    """Crosswind (213) v4 per-ENEMY swirl (user: the swirl is nice but looks like it skips frames): ONE non-looping
    60-frame pass (213 slot 5, f18=1 -> 2 ticks/frame = 120 ticks; the swirl driver's end also carries the 0xC2 grant -
    patch_tc_crosswind_fx_v1.py v4): five small white motes circling the unit on a flattened ring (rx 20, ry 7, centre
    (32, 46) on the 64x80 canvas, anchor -32/-62) through 1.5 turns = 9 deg per frame (v3: 11.25 deg per frame and a
    jump between a 30- and a 70-level copy for the fade), each with 5 close trailing ghosts (smooth motion blur), a gentle
    bob, the back half dimmer; the fade in (first 12 frames) / out (last 16) is BAKED into every frame on a smooth
    sin^2 curve.  Additive 770 at blend 70 (GFXE Intensity), stored on black."""
    W, H = 64, 80; cx, cy = 32.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for i in range(n):
        t = i / float(n - 1); turn = 1.5 * t
        env = math.sin(0.5 * math.pi * min(1.0, i / 12.0)) ** 2 * math.sin(0.5 * math.pi * min(1.0, (n - 1 - i) / 16.0)) ** 2
        acc = np.zeros((H, W), np.float32)
        for k in range(5):
            for j in range(6):                                       # the mote + 5 close trailing ghosts
                a = 2 * math.pi * (turn + k / 5.0) - j * 0.075
                x = cx + 20.0 * math.cos(a); y = cy + 7.0 * math.sin(a) - 2.5 * math.sin(2 * math.pi * (2 * turn + k / 5.0))
                front = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(a))
                lv = front * (1.0, 0.55, 0.36, 0.22, 0.12, 0.06)[j]
                acc += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (1.2 if j == 0 else 1.5)) * 225.0 * lv
        v = np.clip(acc * env, 0, 255)
        out.append(Image.fromarray(np.dstack([v, v, np.clip(v * 1.05, 0, 255)]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def xwind_status(n=48):
    """Crosswind (213) 0xC2 'Crosswind' STATUS OVERLAY (2026-10-16, user: an enchantment aura on units with Crosswind,
    like Suspended's spinning particles but SHORTER).  Ability.pfs record 204 tag 8 (patch_crosswind_ability_pfs_v1.py
    v2) -> drawn by TTacticalCombatUnitHS.Show's overlay loop (patch_tc_suspend_overlay_v1.py v3 table) at xs -23 /
    ys -56 (overlay origin = canvas (23, 56); the feet ~ origin + 21 = y 77, Suspend's rule).  48x80, ADDITIVE 770
    (GFXE Intensity: out = d + 1.75*f*s^2/(s+d), black = invisible), seamless loop of n frames: no beam - only a very
    faint pale-cyan air tint round the lower body, and 5 small white motes (each with a 3-dot fading trail) on a
    flattened helix of radius 9 that rise from the feet to about HALF the unit's height while turning 1.25 turns -
    brighter in front, dimmer behind, fading in at the bottom and out at the top."""
    W, H = 48, 80; cx = 24.0; y_bot, y_top = 74.0, 40.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    tint = np.exp(-((xx - cx) / 11.0) ** 2 - ((yy - 62.0) / 13.0) ** 2) * 22.0
    for i in range(n):
        t = i / float(n)
        acc = tint * (0.85 + 0.15 * math.cos(2 * math.pi * t))
        for k in range(5):
            for g, gl in ((0.0, 1.0), (0.018, 0.55), (0.036, 0.3), (0.054, 0.15)):   # the mote + its trail
                u = (t + k / 5.0 - g) % 1.0
                a = 2 * math.pi * (u * 1.25 + k / 5.0)
                x = cx + 9.0 * math.cos(a); y = y_bot - u * (y_bot - y_top) + 2.2 * math.sin(a); z = math.sin(a)
                fade = min(1.0, u / 0.18) * min(1.0, (1 - u) / 0.25)
                lvl = (0.5 + 0.5 * z) * fade * gl
                if lvl > 0.01: acc = acc + np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.1) * 200.0 * lvl
        v = np.clip(acc, 0, 255)
        out.append(Image.fromarray(np.dstack([np.clip(v * 0.92, 0, 255), np.clip(v * 0.98, 0, 255), v]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def xwind_dust():
    """Crosswind (213) slot 0 v7 (2026-10-16, user: the 0.6x WoF orbs read as BUBBLES - smaller, not bubbly): a tiny
    soft white wind speck (no ring/halo edge): a 1.6 px gaussian core smeared ~4 px sideways into a short streak, at 3
    strengths; 11x11 on black, same anchor (-5/-5) and Intensity-table drawing as before."""
    out = []; yy, xx = np.mgrid[0:11, 0:11].astype(np.float32)
    for lv in (1.0, 0.8, 0.6):
        v = np.zeros((11, 11), np.float32)
        for dx in np.linspace(-2.2, 2.2, 9):
            v = np.maximum(v, np.exp(-((xx - 5 - dx) ** 2 + ((yy - 5) / 0.8) ** 2) / 1.3) * (1 - abs(dx) / 3.2))
        v = v * 235 * lv
        out.append(Image.fromarray(np.dstack([v, v, np.clip(v * 1.05, 0, 255)]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def oil_gush_smooth(K=3, P=10):
    """Oil Spring gush RISE v2 (2026-10-17, user: janky - smoothen, more frames): the same particle fountain rendered at
    K x the time resolution (1 frame per tick instead of 1 per 3): frame j = fountain time j/K (in the old frame units,
    so the physics, the rising ceiling and the pool growth are unchanged), K*P = 30 frames, slot 4 at f18 = 0."""
    parts = _oil_fountain_parts(P); out = []
    for j in range(K * P):
        t = j / float(K); u = min(1.0, (j + 1) / float(K * P))
        out.append(_oil_fountain_frame(parts, t, P, rise=True, pool_R=4 + 2.6 * t, ceil=4 + 140 * (u * u * (3 - 2 * u))))
    return out


def oil_gush_loop_smooth(K=3, P=10):
    """Oil Spring gush LOOP v2: the steady-state fountain at K x time resolution (30 frames = one seamless cycle).  The
    slot plays the cycle TWICE (60 entries) - patch_tc_oilgush_smooth_v1 keeps it alive by wrapping its tick by 30."""
    parts = _oil_fountain_parts(P)
    return [_oil_fountain_frame(parts, j / float(K), P) for j in range(K * P)]


def oil_gush_end_smooth(K=3, P=10, n_end=8):
    """Oil Spring gush END v2: ONE blank image (the slot lists it 27 times = the old 9 blank frames x 3 ticks) + the
    collapse at K x resolution (24 frames): fountain time P + c (c = j/K) continues from loop phase 0, the cutoff grows
    smoothly from 0 (2.4 per old frame) and the pool shrinks as before."""
    parts = _oil_fountain_parts(P); out = [Image.new("RGBA", (4, 4), (0, 0, 0, 0))]
    for j in range(K * n_end):
        c = j / float(K)
        out.append(_oil_fountain_frame(parts, P + c, P, cutoff=2.4 * c + 0.3,
                                       pool_R=30.0 * max(0.0, 1.0 - max(0.0, c - 1) / (n_end - 1.5)) ** 1.1))
    return out


def mend_stone(n=8):
    """Mend Walls (216) slot 0 (2026-10-17): the falling projectile of each of the 19 Ooze strikes (Ooze BALLS canvas
    64x66, anchor (-31,-33), opaque keyed like boulders): a tumbling dressed stone block (lit top, shaded side, mortar
    crumbs clinging to it) wrapped in a faint earthy halo of grit, turning a quarter per 2 frames."""
    W, H = 64, 66; cx, cy = 31.0, 33.0; out = []; rnd = random.Random(3954)
    grit = [(rnd.uniform(0, 6.28), rnd.uniform(9, 14), rnd.choice((1, 1, 2))) for _ in range(9)]
    for i in range(n):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        a = i * math.pi / 4 / 2 + 0.3; ca, sa = math.cos(a), math.sin(a)
        rot = lambda dx, dy: (cx + dx * ca - dy * sa, cy + dx * sa * 0.75 + dy * ca * 0.75)
        w2, h2, d = 8.0, 5.5, 4.0
        face = [rot(-w2, -h2), rot(w2, -h2), rot(w2, h2), rot(-w2, h2)]
        side = [rot(w2, -h2), (rot(w2, -h2)[0] + d * 0.6, rot(w2, -h2)[1] + d), (rot(w2, h2)[0] + d * 0.6, rot(w2, h2)[1] + d), rot(w2, h2)]
        bottom = [rot(-w2, h2), rot(w2, h2), (rot(w2, h2)[0] + d * 0.6, rot(w2, h2)[1] + d), (rot(-w2, h2)[0] + d * 0.6, rot(-w2, h2)[1] + d)]
        dr.polygon(bottom, fill=(92, 78, 62, 255)); dr.polygon(side, fill=(110, 94, 74, 255))
        dr.polygon(face, fill=(168, 150, 120, 255))
        dr.line([face[0], face[1]], fill=(205, 190, 158, 255)); dr.line([face[0], face[3]], fill=(190, 174, 142, 255))
        for k in range(5):                                                                                       # pitting / crumbs
            u, v = rnd.uniform(-0.8, 0.8), rnd.uniform(-0.7, 0.7); px, py = rot(u * w2, v * h2)
            dr.point((px, py), fill=(120, 104, 84, 255))
        for g0, r, s in grit:                                                                                   # grit orbiting with it
            ang = g0 + i * 0.5; x, y = cx + r * math.cos(ang), cy + r * 0.75 * math.sin(ang)
            dr.rectangle([x, y, x + s - 1, y + s - 1], fill=(140, 116, 80, 255))
        out.append(im)
    return out


def mend_trail(n=4):
    """Mend Walls (216) slot 1: the trail (Ooze BOLTS canvas, anchor (-32,-33)), additive: a short smear of warm amber
    earth-dust motes."""
    W, H = 64, 66; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3962)
    for i in range(n):
        acc = np.zeros((H, W, 3), np.float32)
        for k in range(6):
            x = cx + rnd.uniform(-5, 5); y = cy + rnd.uniform(-10, 4); r = rnd.uniform(1.2, 2.4)
            g = 0.55 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (r * r))
            for c, cv in enumerate((200, 150, 80)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def mend_impact(n=24):
    """Mend Walls (216) slot 2: the landing on every hex of the area (Ooze MISC canvas grown to 96x72, hit at (48, 44)),
    additive: a burst of brown-amber dust ringing out flat along the ground (frames 0-7), chips of stone kicked up and
    falling back, and a warm golden earth-glow that swells over the hex and settles (the mortar setting) - longer and
    softer than Ooze's 5-frame splash so a mended segment visibly glows as its stones lock in."""
    W, H = 96, 72; cx, cy = 48.0, 44.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(3966)
    puffs = [(k * 6.2832 / 16 + rnd.uniform(-0.15, 0.15), rnd.uniform(0.75, 1.1), rnd.uniform(3.0, 5.0)) for k in range(16)]
    chips = [(rnd.uniform(-2.9, -0.25), rnd.uniform(0.5, 1.0)) for _ in range(10)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        R = 4 + 26 * (1 - (1 - min(1.0, t / 0.4)) ** 2); dfade = max(0.0, 1 - t / 0.75) * min(1.0, 0.35 + t * 6)
        for a, v, r in puffs:                                                                                   # the dust ring, squashed flat (hex perspective)
            x = cx + R * v * math.cos(a); y = cy + 0.45 * R * v * math.sin(a) - 3 * t
            g = 0.42 * dfade * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / ((r + 4 * t) ** 2))
            for c, cv in enumerate((150, 115, 70)): acc[..., c] += g * cv
        gl = math.sin(math.pi * min(1.0, max(0.0, (t - 0.1) / 0.85)))                                          # the settling glow
        glow = np.exp(-((xx - cx) ** 2 + ((yy - cy + 4) / 0.55) ** 2) / 260.0) * 0.75 * gl
        for c, cv in enumerate((255, 200, 90)): acc[..., c] += glow * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for a, v in chips:                                                                                      # stone chips: up and back down
            s = min(1.0, t / 0.55); x = cx + 22 * v * math.cos(a) * s; y = cy + 30 * v * math.sin(a) * s * (1 - s) * 2.2 - 2
            if t < 0.6:
                c = int(200 * (1 - t / 0.6)) + 40; dr.rectangle([x, y, x + 1, y + 1], fill=(c, int(c * 0.85), int(c * 0.6), 255))
        out.append(im)
    return out




def steadfast_ward(n=16):
    """Steadfast (218) slot 2 (2026-10-17): the per-hex landing (96x80, additive, 16 frames x 2 ticks, anchor -51/-40
    like Sanctify = hex centre (48, 46)): the ground answers - a low ring of amber-brown dust and stone chips kicks up
    around the hex, then a ring of earthen bronze light rises a short way up the unit (a 'rooted' wall of light) and
    settles back into the ground; all fade together.  Earthy, no white flare."""
    W, H = 96, 80; cx, cy = 48.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(2181)
    hexr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.45) ** 2)
    chips = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(16, 24), rnd.uniform(0.0, 0.25), rnd.uniform(8, 16)) for _ in range(14)]
    for i in range(n):
        t = i / (n - 1.0); env = math.sin(math.pi * min(1.0, t * 1.04)) ** 0.6
        R = 10 + 14 * min(1.0, t / 0.35)
        dust = np.exp(-((hexr - R) / 3.2) ** 2) * max(0.0, 1 - t / 0.7) * 0.55
        h = 22 * math.sin(math.pi * min(1.0, max(0.0, t - 0.15) / 0.8))           # the wall of light: rises then sinks
        side = np.exp(-((np.sqrt((xx - cx) ** 2) - 22) / 2.2) ** 2)
        wall = np.clip(1 - (cy + 4 - yy) / max(h, 0.5), 0, 1) * (yy <= cy + 4) * (yy >= cy + 4 - h)
        rim = np.exp(-((hexr - 22) / 1.8) ** 2) * (t > 0.12) * 0.8
        v_wall = (0.55 * wall * np.exp(-((xx - cx) / 24) ** 6) + 0.9 * side * wall + 0.7 * rim) * env
        acc = np.zeros((H, W, 3), np.float32)
        for c, cv in enumerate((205, 160, 90)): acc[..., c] += dust * cv * env
        for c, cv in enumerate((215, 150, 70)): acc[..., c] += v_wall * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for a, r0, d0, up in chips:
            u = (t - d0) / 0.55
            if 0 <= u <= 1:
                x = cx + (r0 + 4 * u) * math.cos(a); y = cy + 0.45 * (r0 + 4 * u) * math.sin(a) - up * math.sin(math.pi * u)
                k = int(150 * (1 - u)) + 40
                dr.rectangle([x - 1, y - 1, x, y], fill=(k, int(k * 0.75), int(k * 0.45), 255))
        out.append(im)
    return out


_BALLS3 = None
def _oil_balls3():
    """v3 'classic' stamps (2026-10-17, user: slightly too modern, not as dated as v2): bigger, more distinct oil blobs
    with a hard dark outline and POSTERIZED shading - 3 tones (outline black / body near-black brown / one hard
    highlight) instead of soft gradients; radii 2.6 / 3.4 / 4.4 px."""
    global _BALLS3
    if _BALLS3 is None:
        out = []
        for r in (2.6, 3.4, 4.4):
            n = int(math.ceil(r)) * 2 + 3; c = n / 2.0
            yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
            d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
            alpha = (d <= r).astype(np.float32)                               # hard edge
            body = (d <= r - 1.0)                                             # 1-px black outline ring outside the body
            hl = np.sqrt((xx - c + 0.38 * r) ** 2 + (yy - c + 0.38 * r) ** 2)
            grey = np.where(body, 34.0, 0.0)                                  # tone 2: dark brown body
            grey = np.where(body & (hl < 0.42 * r), 150.0, grey)              # tone 3: a hard highlight blob
            out.append((alpha, grey.astype(np.float32)))
        _BALLS3 = out
    return _BALLS3


def _stamp_hard(ink, grey, stamp, x, y):
    a, g = stamp; h, w = a.shape; x0, y0 = int(round(x - w / 2.0)), int(round(y - h / 2.0))
    H, W = ink.shape; xs0, ys0 = max(0, x0), max(0, y0); xs1, ys1 = min(W, x0 + w), min(H, y0 + h)
    if xs1 <= xs0 or ys1 <= ys0: return
    aa = a[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]; gg = g[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
    m = aa > 0
    ink[ys0:ys1, xs0:xs1] = np.where(m, 1.0, ink[ys0:ys1, xs0:xs1])
    grey[ys0:ys1, xs0:xs1] = np.where(m, gg, grey[ys0:ys1, xs0:xs1])        # painter's order: nearer ball overwrites


def oil_frame3(parts, T, P, transient, cutoff=0.0, pool_R=30.0, ceil=None):
    """One gush frame at fountain time T (old frame units).  transient=True: only emissions e = t0 + kP with 0 <= e <= T
    exist (the fountain STARTED at T=0 - no spray from earlier cycles, the cause of the v2 hand-over pop); False: the
    periodic steady state (identical to the transient once T >= 24 = the oldest visible age).  The emission speed
    pulses with sin(2 pi e / P) in BOTH, so the two agree particle for particle.  Classic style: posterized blobs."""
    SZ = 160; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, base = 80.0, 140.0
    ink = np.zeros((SZ, SZ), np.float32); grey = np.zeros((SZ, SZ), np.float32); balls = _oil_balls3()
    R = max(pool_R, 0.5)
    if pool_R >= 2.0:                                                         # pool: hard-edged black ellipse + one flat sheen band
        e = ((xx - cx) / R) ** 2 + ((yy - base + 3) / (R * 0.40)) ** 2
        pool = e <= 1.0; ink = np.where(pool, 1.0, ink)
        sheen = (((xx - cx + 0.25 * R) / (R * 0.45)) ** 2 + ((yy - base + 5) / (R * 0.14)) ** 2) <= 1.0
        grey = np.where(pool, np.where(sheen, 70.0, 14.0), grey)
    drawn = []
    for t0, vy0, vx, sz, spr in parts:
        ems = []
        if transient:
            k = 0
            while t0 + k * P <= T: ems.append(t0 + k * P); k += 1
        else:
            for k in range(3): ems.append(T - (((T - t0) % P) + k * P))
        for e in ems:
            age = T - e
            if age < cutoff or age < 0: continue
            vy = vy0 * (1.0 + PULSE * math.sin(2 * math.pi * e / P))
            y = base - vy * age + 1.05 * age * age
            if y > base + 2: continue
            if ceil is not None and y < base - ceil: continue
            apex_age = vy / 2.1; past = max(0.0, age - apex_age * 0.7)
            x = cx + vx * age + math.copysign(1, vx) * (0.5 + 4.6 * spr) * (math.sqrt(past + 2.0) - math.sqrt(2.0))
            if 6 <= x < SZ - 6 and 6 <= y < SZ - 6: drawn.append((y, x, int(sz * 3) % 3))
    drawn.sort(key=lambda t: -t[0])
    for y, x, b in drawn: _stamp_hard(ink, grey, balls[b], x, y)
    o = np.clip(ink, 0, 1); rgb = (6 + grey) * o
    return Image.fromarray(np.dstack([rgb, rgb * 0.9, rgb * 0.76, 255 * (o > 0.5)]).astype(np.uint8), "RGBA")


N3 = 520                                                                      # fewer, bigger blobs (v2: 1200 small ones)

def oil_gush_rise3(K=3, P=10, n=66, warp=48):
    """RISE v3: the fountain from its very start (transient), on a time-warped clock - T = j/3 + 8(1 - (1 - j/48)^2)
    for the first 48 ticks (an eager 2x-speed burst easing into normal speed) and j/3 + 8 after - so T reaches 24 (the
    oldest visible particle age = fully developed = pixel-identical to the steady loop) at tick 48; the gate spawns the
    loop at tick 48 with loop tick 12 (= (3 * 24) % 30) and the rise's last 18 frames equal the loop's frames 12-29.
    The column climbs out of the ground under a ceiling that is full by T 8."""
    parts = _oil_fountain_parts(P, N3); out = []
    for j in range(n):
        T = j / float(K) + (K * P * 8.0 / 30.0) * (1.0 - (1.0 - j / float(warp)) ** 2) if j < warp else j / float(K) + 8.0
        u = min(1.0, T / 8.0)
        out.append(oil_frame3(parts, T, P, True, pool_R=min(30.0, 4 + 2.6 * T), ceil=4 + 140 * (u * u * (3 - 2 * u))))
    return out


def oil_gush_loop3(K=3, P=10):
    parts = _oil_fountain_parts(P, N3)
    return [oil_frame3(parts, 30.0 + j / float(K), P, False) for j in range(K * P)]   # T = 30.. (phase j/K), = steady


def oil_gush_end3(K=3, P=10, n_end=8):
    parts = _oil_fountain_parts(P, N3); out = [Image.new("RGBA", (4, 4), (0, 0, 0, 0))]
    for j in range(K * n_end):
        c = j / float(K)
        out.append(oil_frame3(parts, 40.0 + c, P, False, cutoff=2.4 * c, pool_R=30.0 * max(0.0, 1.0 - max(0.0, c - 1) / (n_end - 1.5)) ** 1.1))
    while len(out) > 2 and out[-1].getbbox() is None: out.pop()                   # drop the empty tail (nothing left to draw)
    return out


def ore_glints():
    """Depths of Plenty (217) slot 0: Earth Mastery's map-wide particle (as Golden Age's gold_motes, 20x20 additive,
    played [4200, 4201, 4202, 4203, 4202, 4201]): a deep-amber gold-ore glint - a warm nugget-coloured core under a
    diagonal X-flare (Golden Age's twinkle is a +), an earthy bronze halo and two specks of dust drifting down."""
    frames = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32)
    for k, (g, rl, dy) in enumerate(((0.6, 3.5, 0.0), (0.9, 5.5, 1.0), (1.15, 7.0, 2.0), (0.7, 4.5, 3.0))):
        d2 = (xx - 9.5) ** 2 + (yy - 9.5) ** 2
        u, v_ = (xx - 9.5 + yy - 9.5) / 1.4142, (xx - 9.5 - (yy - 9.5)) / 1.4142
        core = np.exp(-d2 / (2 * 1.5 ** 2)) * g
        rays = (np.exp(-(u ** 2) / 0.45 - (v_ ** 2) / (2 * rl ** 2)) + np.exp(-(v_ ** 2) / 0.45 - (u ** 2) / (2 * rl ** 2))) * 0.55 * g
        halo = np.exp(-d2 / (2 * 4.0 ** 2)) * 0.30 * g
        dust = sum(np.exp(-((xx - x0) ** 2 + (yy - (y0 + dy)) ** 2) / 0.6) * 0.5 * g for x0, y0 in ((6.0, 12.0), (13.5, 11.0)))
        v = np.clip(np.maximum(np.maximum(core, rays), np.maximum(halo, dust)), 0, 1); w = np.clip(core * 1.2 - 0.35, 0, 1)
        rgb = np.dstack([(212 + 28 * w) * v, (166 + 44 * w) * v, (20 + 66 * w) * v])   # v2 10/17 (user: more golden / dark yellow, less orange, not holy-bright): hue ~46 deg, core only to (240,210,86)
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def tectonic_dust(n=3):
    """Tectonic Shift (219) slots 0-2 (v2 2026-10-17, user: particles green): three single frames for Air Mastery's
    map-wide drift (200x116, additive at low blend, as Ice Age's snow_drift): a faint green earth-magic haze along a
    wide S-curve, a jagged glowing green fissure (forked crack line with a soft glow) running through it, and pale
    green grit / pebble specks thrown up beside the crack."""
    W, H = 200, 116; out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for v in range(n):
        rnd = random.Random(2190 + v); ph = v * 2.1
        acc = np.zeros((H, W, 3), np.float32)
        for k in range(12):                                                      # dust haze puffs
            t = rnd.random(); x = 10 + 180 * t; y = 60 + 26 * math.sin(t * 2 * math.pi * 0.9 + ph) + rnd.uniform(-6, 6)
            g = 0.16 * np.exp(-((xx - x) ** 2 + ((yy - y) / 0.55) ** 2) / 260.0)
            for c, cv in enumerate((80, 190, 100)): acc[..., c] += g * cv
        pts = []; x = 14.0; y = 60 + 26 * math.sin(ph) + rnd.uniform(-4, 4)       # the fissure: a jagged walk along the curve
        while x < 186:
            pts.append((x, y)); x += rnd.uniform(6, 11)
            y = 60 + 26 * math.sin((x - 10) / 180.0 * 2 * math.pi * 0.9 + ph) + rnd.uniform(-5, 5)
        glow = Image.new("L", (W, H), 0); gd = ImageDraw.Draw(glow)
        gd.line(pts, fill=255, width=5)
        for k in range(4):                                                       # side forks
            i = rnd.randrange(1, len(pts) - 1); fx, fy = pts[i]; ang = rnd.uniform(-2.6, -0.5) if k % 2 else rnd.uniform(0.5, 2.6)
            fork = [(fx, fy)]
            for s in range(3):
                fx += 7 * math.cos(ang) + rnd.uniform(-2, 2); fy += 7 * math.sin(ang) * 0.6 + rnd.uniform(-2, 2); fork.append((fx, fy))
            gd.line(fork, fill=170, width=3)
        g = np.asarray(glow.filter(ImageFilter.GaussianBlur(3.0)), np.float32) / 255.0 * 0.55
        for c, cv in enumerate((90, 255, 120)): acc[..., c] += g * cv
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        dr.line(pts, fill=(185, 255, 175, 255), width=1)                         # the bright crack core
        for k in range(40):                                                      # grit and pebbles thrown up
            t = rnd.random(); x = 10 + 180 * t; y = 60 + 26 * math.sin(t * 2 * math.pi * 0.9 + ph) + rnd.uniform(-22, 22)
            c = int(rnd.uniform(150, 230)); col = (int(c * 0.55), c, int(c * 0.62), 255)
            r = rnd.choice((0.6, 1.0, 1.4))
            if r < 1: dr.point((x, y), fill=col)
            else: dr.polygon([(x - r, y), (x, y - r), (x + r, y + 0.4), (x + 0.3, y + r)], fill=col)
        out.append(im)
    return out


def mend_glow(n=24):
    """Mend Walls (216) v2 slot 1 (2026-10-17, user: "it should simply make walls within the AOE glow green or have some
    kind of magical effect"): one kind-0x26 effect per MENDED wall hex (patch_tc_mendwalls_v2.py), 64x96, additive,
    the hex centre at (32, 80) (entry xs/ys -32/-80): a soft green aura wrapping the wall segment (rises, holds with a
    slow shimmer, fades), three bright 'knitting' seams sweeping up through it like mortar re-setting, green-white
    motes drifting upward and a faint flat glow where the wall meets the ground."""
    W, H = 64, 96; cx, base = 32.0, 84.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2160)
    motes = [(rnd.uniform(14, 50), rnd.uniform(0.0, 1.0), rnd.uniform(0.55, 1.0), rnd.uniform(0, 6.28)) for _ in range(20)]
    colx = np.exp(-((xx - cx) ** 2) / (2 * 12.5 ** 2))
    top = 20.0
    coly = np.clip((base + 4 - yy) / 10.0, 0, 1) * np.clip((yy - top + 14) / 22.0, 0, 1)
    out = []
    for i in range(n):
        t = i / (n - 1.0)
        env = min(1.0, t / 0.22) if t < 0.22 else 1.0 if t < 0.68 else max(0.0, 1.0 - (t - 0.68) / 0.32)
        env = env * env * (3 - 2 * env)
        acc = np.zeros((H, W, 3), np.float32)
        shim = 0.82 + 0.18 * np.sin(yy * 0.35 - t * 14.0 + xx * 0.12)
        aura = colx * coly * shim * 0.55 * env
        for c, cv in enumerate((40, 210, 95)): acc[..., c] += aura * cv
        for k in range(3):
            u = t * 1.45 - k * 0.26
            if 0.0 <= u <= 1.0:
                by = base - u * (base - top)
                band = np.exp(-((yy - by) ** 2) / (2 * 1.6 ** 2)) * np.exp(-((xx - cx) ** 2) / (2 * 11.0 ** 2)) * math.sin(math.pi * u) * 0.75 * max(env, 0.35)
                for c, cv in enumerate((150, 255, 175)): acc[..., c] += band * cv
        floor = np.exp(-((xx - cx) ** 2) / (2 * 15.0 ** 2) - ((yy - base) ** 2) / (2 * 2.4 ** 2)) * 0.45 * env
        for c, cv in enumerate((60, 230, 110)): acc[..., c] += floor * cv
        for x0, ph, sp, tw in motes:
            u = (ph + t * sp * 1.3) % 1.0
            y = base - 4 - u * (base - top + 6); x = x0 + 2.5 * math.sin(tw + u * 7.0)
            a = math.sin(math.pi * u) * (0.65 + 0.35 * math.sin(tw + t * 25.0)) * env
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * a
            for c, cv in enumerate((190, 255, 205)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def _sf2_shield(S=4):
    """A round hoplite shield (aspis) seen slightly from below/front: a 22x26 px ellipse with a thick rim, an inner
    raised ring, a central boss and a chevron (lambda-like) blazon.  Returned as a float32 intensity mask at S x."""
    w, h = 24 * S, 28 * S
    im = Image.new("L", (w, h), 0); d = ImageDraw.Draw(im)
    d.ellipse([1 * S, 1 * S, 23 * S, 27 * S], fill=95)                              # face
    d.ellipse([1 * S, 1 * S, 23 * S, 27 * S], outline=255, width=int(2.2 * S))      # thick rim
    d.ellipse([5.5 * S, 6 * S, 18.5 * S, 22 * S], outline=215, width=int(1.0 * S))  # inner ring
    d.line([(7.5 * S, 19.5 * S), (12 * S, 9 * S), (16.5 * S, 19.5 * S)], fill=255, width=int(1.6 * S))   # chevron blazon
    d.ellipse([10.2 * S, 12.4 * S, 13.8 * S, 16.4 * S], fill=255)                     # boss
    return np.asarray(im, np.float32) / 255.0


def _sf3_heater(S=4):
    """A HEATER shield (user 2026-10-17: 'heater shields, triangular-ish') seen from the front: flat top with softly
    rounded corners, straight sides for the upper 40 %, then two convex curves meeting in a point at the bottom.
    Thick bright rim, a darker face, an inner border line and a chief band along the top over an
    upward chevron (a mountain peak - Earth; no cross, which read as Life).  22x28 px; float32 mask at S x."""
    w, h = 24 * S, 30 * S
    def outline(inset):
        x0, x1, y0 = (1.0 + inset) * S, (23.0 - inset) * S, (1.0 + inset) * S
        ys = (12.0) * S                                                   # end of the straight sides
        tip = (29.0 - inset * 1.6) * S
        pts = [(x0 + 1.2 * S, y0), (x1 - 1.2 * S, y0), (x1, y0 + 1.2 * S), (x1, ys)]
        for k in range(1, 17):                                            # right flank: convex curve to the tip
            u = k / 16.0
            pts.append((x1 - (x1 - w / 2.0) * (u ** 1.6), ys + (tip - ys) * math.sin(u * math.pi / 2)))
        for k in range(15, -1, -1):                                       # left flank (mirror)
            u = k / 16.0
            pts.append((x0 + (w / 2.0 - x0) * (u ** 1.6), ys + (tip - ys) * math.sin(u * math.pi / 2)))
        pts += [(x0, ys), (x0, y0 + 1.2 * S)]
        return pts
    im = Image.new("L", (w, h), 0); d = ImageDraw.Draw(im)
    d.polygon(outline(0.0), fill=255)                                     # rim
    d.polygon(outline(2.2), fill=90)                                      # face
    d.line(outline(3.6) + [outline(3.6)[0]], fill=200, width=max(1, int(0.8 * S)))   # inner border
    d.rectangle([4.4 * S, 4.4 * S, 19.6 * S, 7.0 * S], fill=225)          # a 'chief' band along the top
    d.line([(6.0 * S, 19.0 * S), (12.0 * S, 10.6 * S), (18.0 * S, 19.0 * S)], fill=240, width=int(2.0 * S))   # chevron = a mountain peak (Earth)
    return np.asarray(im, np.float32) / 255.0


def steadfast_shield(n=26, mask=None):
    """Steadfast (218) v2 slot 3 (2026-10-17, user: green not yellow; shields above each unit in the AOE that float down
    onto them, maybe a very subtle green pillar; no ground circles - something unique): ONE kind-0x26 driver per
    FRIENDLY non-machine unit on the pattern (patch_tc_steadfast_fx_v1.py, marker 3 -> slot 3), at the unit's hex
    centre (HXtoHP + 16), 96x128 canvas, anchor -48/-112 -> the hex-centre point = canvas (48, 112).
      * SHIELD: a round green hoplite shield (rim, inner ring, boss, chevron blazon) appears high above the unit, glides
        down on an ease-out curve with a short motion trail and a slight sway, settles at chest height (y 72) with a
        bright pulse, then sinks a little into the unit while it fades - the ward 'taken up'.
      * PILLAR: a very faint green column of light (soft gaussian, 18 px wide) from the sky to the ground, fading in with
        the shield and out after it, with slow upward glints.
      * GROUND: SIX small angular rune-stones (no rings/circles) at the corners of a flattened hexagon around the
        unit's feet: as the shield lands they push up out of the earth, glow, shed a few rising green motes and sink.
    Additive 770 (stored on black), anti-aliased at 4x.  26 frames x 2 ticks (f18=1) = 52 ticks (~1.5 s)."""
    S = 4; W, H = 96, 128; cx, gy = 48.0, 104.0                       # gy = ground point of the unit's feet (centre-8)
    Wb, Hb = W * S, H * S
    yy, xx = np.mgrid[0:Hb, 0:Wb].astype(np.float32) / S
    sh = (mask or _sf2_shield)(S); shh, shw = sh.shape
    rnd = random.Random(2182)
    stones = []
    for k in range(6):
        a = math.radians(30 + 60 * k)
        stones.append((cx + 26.0 * math.cos(a), gy + 10.0 * math.sin(a), 0.75 + 0.25 * math.sin(a)))   # back stones dimmer
    motes = [(rnd.randrange(6), rnd.uniform(-2.5, 2.5), rnd.uniform(0.0, 0.25), rnd.uniform(14, 26)) for _ in range(16)]
    glints = [(rnd.uniform(-5, 5), rnd.uniform(0, 1), rnd.uniform(0.5, 1.0)) for _ in range(6)]
    T_LAND = 0.52
    out = []
    for i in range(n):
        t = i / (n - 1.0)
        acc = np.zeros((Hb, Wb), np.float32); core = np.zeros((Hb, Wb), np.float32)
        # ---- pillar (very subtle)
        pil = 0.10 * math.sin(math.pi * min(1.0, t / 0.9)) ** 1.2
        if pil > 0:
            col = np.exp(-((xx - cx) / 7.5) ** 2) * np.clip((yy - 4) / 30.0, 0, 1) * np.clip((gy + 4 - yy) / 6.0, 0, 1)
            acc += col * pil
            for gx, ph, lv in glints:
                y0 = gy - ((t * 1.6 + ph) % 1.0) * (gy - 10)
                acc += np.exp(-((xx - cx - gx) / 0.9) ** 2 - ((yy - y0) / 4.0) ** 2) * 0.22 * lv * min(1.0, pil * 12)
        # ---- shield
        if t <= T_LAND:
            u = t / T_LAND; e = 1 - (1 - u) ** 2.2
            sy = 14.0 + (72.0 - 14.0) * e; sl = min(1.0, u / 0.25) * 0.72
            sxo = 2.0 * math.sin(u * math.pi * 1.5) * (1 - u)
            trail = [(sy - (72.0 - 14.0) * (e - (1 - (1 - max(0.0, u - dd)) ** 2.2)), f) for dd, f in ((0.05, 0.35), (0.10, 0.18), (0.16, 0.08))]
            pulse = 0.0
        else:
            u = (t - T_LAND) / (1 - T_LAND)
            sy = 72.0 + 6.0 * u ** 1.5; sxo = 0.0
            sl = (1 - u) ** 1.4 * 0.72; trail = []
            pulse = math.exp(-((u - 0.06) / 0.10) ** 2)
        def stamp(cy_, lev, scale=1.0):
            if lev <= 0.004: return
            m = sh if scale == 1.0 else np.asarray(Image.fromarray((sh * 255).astype(np.uint8)).resize((max(1, int(shw * scale)), max(1, int(shh * scale))), Image.BILINEAR), np.float32) / 255.0
            mh, mw = m.shape
            x0 = int(round((cx + sxo) * S - mw / 2)); y0 = int(round(cy_ * S - mh / 2))
            xa, ya = max(0, x0), max(0, y0); xb, yb = min(Wb, x0 + mw), min(Hb, y0 + mh)
            if xa >= xb or ya >= yb: return
            acc[ya:yb, xa:xb] += m[ya - y0:yb - y0, xa - x0:xb - x0] * lev
        for ty, f in trail: stamp(ty, sl * f)
        stamp(sy, sl, 1.0 + 0.08 * pulse)
        if pulse > 0.01:
            halo = np.exp(-(((xx - cx) / 16.0) ** 2 + ((yy - sy) / 18.0) ** 2)) * 0.40 * pulse
            acc += halo; core += halo * 0.6
        # ---- six rune-stones at the hexagon corners
        sv = math.sin(math.pi * min(1.0, max(0.0, (t - T_LAND + 0.12) / 0.55))) if t > T_LAND - 0.12 else 0.0
        if sv > 0:
            rise = 5.0 * sv
            for x0, y0, dep in stones:
                ytop = y0 - rise
                # a small upright diamond shard: 3 px wide, 4..6 px tall
                pts = [((x0 - 0.4) * S, (ytop - 3.6) * S), ((x0 + 2.2) * S, (ytop - 0.6) * S), ((x0 + 1.4) * S, (y0 + 1.0) * S), ((x0 - 1.6) * S, (y0 + 1.0) * S), ((x0 - 2.2) * S, (ytop - 0.2) * S)]
                m = Image.new("L", (Wb, Hb), 0); ImageDraw.Draw(m).polygon(pts, fill=255)
                sm = np.asarray(m, np.float32) / 255.0
                acc += sm * 0.85 * sv * dep
                core += sm * 0.5 * sv * dep
                acc += np.exp(-(((xx - x0) / 3.5) ** 2 + ((yy - ytop) / 3.0) ** 2)) * 0.30 * sv * dep
            for k, dx, ph, hgt in motes:
                lt = (t - T_LAND - ph) / 0.42
                if 0 < lt < 1:
                    x0, y0, dep = stones[k]
                    my = y0 - 4 - hgt * lt; mx = x0 + dx * lt
                    acc += np.exp(-(((xx - mx) / 0.9) ** 2 + ((yy - my) / 0.9) ** 2)) * 0.8 * (1 - lt) * dep
        # ---- colour (emerald): body green, hot spots toward pale mint
        v = np.clip(acc, 0, 1.6); hot = np.clip(core * 0.7 + np.clip(acc - 0.9, 0, 1), 0, 1)
        r = 40 * v + 150 * hot; g = 205 * v + 50 * hot; b = 85 * v + 90 * hot
        rgb = np.dstack([r, g, b]).clip(0, 255).astype(np.uint8)
        im = Image.fromarray(rgb, "RGB").resize((W, H), Image.BOX)
        out.append(im.convert("RGBA"))
    return out


MEND3_ARRIVE = [28, 31, 34, 37, 40, 43]                    # ticks: rock k reaches the wall (shared by both variants + the glow)
MEND3_TARGETS = [(-12, -44), (10, -48), (-3, -31), (14, -25), (-14, -18), (5, -12)]   # px from the hex centre: on the wall body
MEND3_RW, MEND3_RH, MEND3_RAX, MEND3_RAY = 224, 212, 112, 120   # rock canvas + anchor (= the hex-centre point)
_MEND3_BAY = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def _mend3_sources(variant):
    """6 ground points 2-3 hexes from the wall (combat HXtoHP lattice: columns 32 px apart, rows 32 px, odd columns
    16 px lower), spread round the compass, |dy| <= 80; variant 1 is rotated half a step against variant 0."""
    cand = []
    for i in range(-3, 4):
        for j in range(-4, 5):
            q, r = i, j - (i - (i & 1)) // 2
            dist = (abs(q) + abs(r) + abs(q + r)) // 2
            dx, dy = 32 * i, 32 * j + 16 * (i & 1)
            if dist in (2, 3) and abs(dy) <= 80: cand.append((math.atan2(dy, dx), dist, dx, dy))
    rnd = random.Random(2163 + variant); out = []
    for k in range(6):
        a0 = -math.pi + (k + 0.5 * variant) * math.pi / 3 + 0.25
        want = 2 if (k + variant) % 2 else 3
        best = min(cand, key=lambda c: (abs(math.atan2(math.sin(c[0] - a0), math.cos(c[0] - a0))) + (0 if c[1] == want else 0.6)))
        cand.remove(best)
        out.append((best[2] + rnd.uniform(-6, 6), best[3] + rnd.uniform(-5, 5)))
    order = list(range(6)); rnd.shuffle(order)                 # which source feeds which target (arrival order)
    return [out[o] for o in order]


def _mend3_poly(rnd, r, n=7):
    return [(a, r * rnd.uniform(0.72, 1.08)) for a in sorted(rnd.uniform(0, 2 * math.pi) for _ in range(n))]


def _mend3_stamp(dr, S, pts, x, y, rot, sc, fam):
    """One rock: hard 3-tone (dark rim, body, one highlight facet), drawn at S x."""
    rim, body, lit = (((36, 31, 28), (110, 104, 96), (166, 158, 146)), ((42, 30, 21), (124, 96, 66), (178, 148, 110)))[fam]
    r0 = sum(rr for _a, rr in pts) / len(pts)
    def P(grow, shx=0.0, shy=0.0, k=1.0):
        return [((x + shx + math.cos(a + rot) * (rr * sc * k + grow)) * S, (y + shy + math.sin(a + rot) * (rr * sc * k + grow) * 0.9) * S) for a, rr in pts]
    dr.polygon(P(1.0), fill=rim + (255,))
    dr.polygon(P(0.0), fill=body + (255,))
    dr.polygon(P(0.0, -0.3 * r0 * sc, -0.35 * r0 * sc, 0.5), fill=lit + (255,))


def _mend3_bez(p0, p1, p2, u):
    return ((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0], (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1])


def mend3_rocks(variant, n=26):
    """Mend Walls (216) v3 slots 3/4 (2026-10-17, user: "a bunch of debris/rocks etc being pulled from the ground fairly
    nearby (within 2 or 3 hexes) and pulled into the wall ... green glow particles as they reach the wall"): one
    kind-0x26 effect per MENDED wall hex (patch_tc_mendwalls_v2.py v3), ALPHA (258), 224x212, the hex centre at
    (112, 120) (entry xs/ys -112/-120), 26 frames x 2 ticks.  Six rocks (grey stone / brown earth, hard 3-tone like
    Oil Spring v3) crack out of the ground 2-3 hexes away (dark hole + a pebble spurt), rise with a green magic
    shimmer, hover, then are pulled along an arc into the wall body (shadow sliding along the ground, a green speck
    trail, a trailing pebble) and vanish into it at MEND3_ARRIVE - where the shared glow layer (mend3_glow) flashes.
    Variants 0/1 differ only in the source layout (the wall's (x + y) parity picks one)."""
    S = 4; W, H, AX, AY = MEND3_RW, MEND3_RH, MEND3_RAX, MEND3_RAY; bay = _MEND3_BAY
    src = _mend3_sources(variant); rnd = random.Random(2170 + variant)
    rocks = []
    for k in range(6):
        sx, sy = src[k]; tx, ty = MEND3_TARGETS[k]; arr = MEND3_ARRIVE[k]
        pop = arr - 26; launch = pop + 14
        ctrl = ((sx + tx) / 2.0 + rnd.uniform(-10, 10), min(sy - 14, ty) - rnd.uniform(26, 40))
        rocks.append(dict(sx=sx, sy=sy, tx=tx, ty=ty, pop=pop, launch=launch, arr=arr, ctrl=ctrl, fam=k % 2,
                          pts=_mend3_poly(rnd, rnd.uniform(5.2, 7.0)), spin=rnd.choice((-1, 1)) * rnd.uniform(5.0, 9.0),
                          peb=_mend3_poly(rnd, 2.0, 5), pebo=(rnd.uniform(-4, 4), rnd.uniform(1, 4)),
                          spurt=[(rnd.uniform(-1, 1), rnd.uniform(5, 10), _mend3_poly(rnd, 1.5, 5)) for _ in range(3)],
                          motes=[(rnd.uniform(0, 6.28), rnd.uniform(5, 9), rnd.uniform(0.25, 0.45)) for _ in range(5)],
                          jit=[(rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5)) for _ in range(3 * n)]))
    out = []
    for i in range(n):
        t = 2.0 * i
        big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); dr = ImageDraw.Draw(big)
        shade = Image.new("L", (W, H), 0); sd = ImageDraw.Draw(shade)          # dithered layers (holes, shadows)
        hole = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(hole)
        specks = []
        for R in rocks:
            gx, gy = AX + R["sx"], AY + R["sy"]
            if R["pop"] <= t < R["launch"] + 12:                             # the torn ground: open, then healing over
                a = 1.0 if t < R["launch"] + 2 else max(0.0, 1.0 - (t - R["launch"] - 2) / 10.0)
                hd.ellipse([gx - 5.5, gy - 2.2, gx + 5.5, gy + 2.6], fill=int(255 * a))
            if R["pop"] <= t < R["pop"] + 9:                                   # pebble spurt
                u = (t - R["pop"]) / 9.0
                for vx, vy, pp in R["spurt"]:
                    px_ = gx + vx * 7 * u; py_ = gy - vy * 4 * u * (1 - u) * 1.6
                    _mend3_stamp(dr, S, pp, px_, py_, u * 6, 1.0, R["fam"])
            if R["pop"] <= t < R["launch"]:                                    # emerging + hovering
                u = min(1.0, (t - R["pop"]) / 10.0); e = u * u * (3 - 2 * u)
                hov = 0.0 if u < 1 else math.sin((t - R["pop"] - 10) * 0.9) * 1.2
                x, y = gx + math.sin(t * 0.7 + R["spin"]) * 0.6 * e, gy - 2 - 13 * e + hov
                sd.ellipse([gx - 6 * e - 1, gy - 1.5, gx + 6 * e + 1, gy + 1.8], fill=int(120 * e))
                _mend3_stamp(dr, S, R["pts"], x, y, 0.2 * math.sin(t * 0.5), 0.55 + 0.45 * e, R["fam"])
                for ph, rr, sp in R["motes"]:                                     # the green pull swirling round it
                    a = ph + t * sp; specks.append((x + math.cos(a) * rr, y + math.sin(a) * rr * 0.55 + 2, 0.55 + 0.45 * e))
            elif R["launch"] <= t < R["arr"]:                                    # pulled into the wall
                u = (t - R["launch"]) / float(R["arr"] - R["launch"]); e = u * u * (3 - 2 * u) * 0.35 + u * 0.65
                p0 = (gx, gy - 15); p2 = (AX + R["tx"], AY + R["ty"]); p1 = (AX + R["ctrl"][0], AY + R["ctrl"][1])
                x, y = _mend3_bez(p0, p1, p2, e)
                shx, shy = gx + (AX + R["tx"] - gx) * e, gy + (AY - gy) * e        # its shadow slides to the wall foot
                sd.ellipse([shx - 5, shy - 1.5, shx + 5, shy + 1.8], fill=int(110 * (1 - u)))
                _mend3_stamp(dr, S, R["pts"], x, y, R["spin"] * u, 1.0 - 0.2 * u, R["fam"])
                for q, b in enumerate((0.06, 0.12, 0.19)):                       # green speck trail
                    if e - b > 0:
                        bx, by = _mend3_bez(p0, p1, p2, e - b); jx, jy = R["jit"][3 * i + q]
                        specks.append((bx + jx, by + jy, 1.0 - b * 3))
            if R["launch"] + 3 <= t < R["arr"] + 3:                              # the trailing pebble
                u = (t - R["launch"] - 3) / float(R["arr"] - R["launch"])
                p0 = (gx + 3, gy - 12); p2 = (AX + R["tx"] + R["pebo"][0], AY + R["ty"] + R["pebo"][1])
                p1 = (AX + R["ctrl"][0] + 6, AY + R["ctrl"][1] + 8)
                x, y = _mend3_bez(p0, p1, p2, u)
                _mend3_stamp(dr, S, R["peb"], x, y, R["spin"] * u * 1.3, 1.0, 1 - R["fam"])
        im = big.resize((W, H), Image.BOX); a = np.array(im); hp = np.array(hole); sp_ = np.array(shade)
        thr = np.tile(np.array(bay, np.int32) * 16 + 8, (H // 4 + 1, W // 4 + 1))[:H, :W]
        solid = a[..., 3] >= 120
        a[~solid] = 0; a[solid, 3] = 255
        hm = (~solid) & (hp > thr) & (hp > 40); a[hm] = (30, 22, 16, 255)
        sm = (~solid) & (~hm) & (sp_ > thr); a[sm] = (16, 14, 12, 255)
        for x, y, s in specks:                                               # green motes: 1-2 px, dithered by strength
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W - 1 and 0 <= yi < H and s * 255 > thr[yi, xi]:
                a[yi, xi] = (150, 255, 160, 255)
                if s > 0.7: a[yi, xi + 1] = (70, 220, 110, 255)
        out.append(Image.fromarray(a, "RGBA"))
    return out


_MEND3_GLOW = []


def mend3_glow(n=24):
    """Mend Walls (216) v3 slot 1 (shared by both rock variants): ADDITIVE (770), 96x112, the hex centre at (48, 92)
    (entry xs/ys -48/-92), 24 frames x 3 ticks: a green flash + a ring of sparks + a short glowing seam where each
    rock sinks into the wall (MEND3_TARGETS at MEND3_ARRIVE), then a soft green aura wraps the mended wall, one bright
    band sweeps up through it and green-white motes drift off as it fades.  Cached (two builder rows slice it)."""
    if _MEND3_GLOW: return _MEND3_GLOW
    W, H, AX, AY = 96, 112, 48, 92
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2180)
    sparks = [[(rnd.uniform(0, 6.28), rnd.uniform(9, 16), rnd.uniform(-0.3, 0.1)) for _ in range(8)] for _ in range(6)]
    motes = [(rnd.uniform(-16, 16), rnd.uniform(0, 1), rnd.uniform(0.6, 1.0), rnd.uniform(0, 6.28)) for _ in range(16)]
    colx = np.exp(-((xx - AX) ** 2) / (2 * 13.0 ** 2)); coly = np.clip((AY + 6 - yy) / 8.0, 0, 1) * np.clip((yy - (AY - 66)) / 14.0, 0, 1)
    for i in range(n):
        t = 3.0 * i; acc = np.zeros((H, W, 3), np.float32)
        def add(g, col):
            for c, cv in enumerate(col): acc[..., c] += g * cv
        for k, (tx, ty) in enumerate(MEND3_TARGETS):
            d = t - MEND3_ARRIVE[k]
            if 0 <= d < 15:
                x, y = AX + tx, AY + ty; f = math.exp(-d / 4.0)
                add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (2.5 + d * 0.35) ** 2)) * f * 1.1, (170, 255, 185))
                add(np.exp(-((yy - y) ** 2) / 1.2 - ((xx - x) ** 2) / (2 * (3 + d * 0.8) ** 2)) * f * 0.7, (90, 240, 130))
                for a, r, vy in sparks[k]:
                    u = d / 15.0; sx = x + math.cos(a) * r * (1 - (1 - u) ** 2); sy = y + math.sin(a) * r * 0.7 * (1 - (1 - u) ** 2) + vy * d * 3
                    add(np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / 1.1) * (1 - u) * 0.95, (190, 255, 200))
        ramp = 0.0 if t < MEND3_ARRIVE[0] else min(1.0, (t - MEND3_ARRIVE[0]) / 18.0)
        fade = 1.0 if t < 54 else max(0.0, 1.0 - (t - 54) / 16.0)
        env = ramp * fade; env = env * env * (3 - 2 * env)
        add(colx * coly * (0.82 + 0.18 * np.sin(yy * 0.35 - t * 0.45 + xx * 0.12)) * 0.42 * env, (40, 210, 95))
        u = (t - 44) / 16.0
        if 0 <= u <= 1:
            by = AY + 4 - u * 70
            add(np.exp(-((yy - by) ** 2) / (2 * 1.6 ** 2)) * np.exp(-((xx - AX) ** 2) / (2 * 12.0 ** 2)) * math.sin(math.pi * u) * 0.7, (150, 255, 175))
        add(np.exp(-((xx - AX) ** 2) / (2 * 16.0 ** 2) - ((yy - AY - 2) ** 2) / (2 * 2.4 ** 2)) * 0.4 * env, (60, 230, 110))
        for x0, ph, sp, tw in motes:
            if t < 34: continue
            v = (ph + (t - 34) / 38.0 * sp * 1.3) % 1.0
            y = AY - 2 - v * 72; x = AX + x0 + 2.5 * math.sin(tw + v * 7.0)
            a = math.sin(math.pi * v) * (0.65 + 0.35 * math.sin(tw + t * 0.8)) * fade
            add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * a, (190, 255, 205))
        _MEND3_GLOW.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return _MEND3_GLOW


def tectonic_motes(n=3):
    """Tectonic Shift (219) v3 slots 0-2 (bright) + 11-13 (dim twins) (2026-10-17, user: particles hover map-wide, then split
    diagonally and drift apart like a fissure opening): six 96x64 additive clusters of 5-7 hovering green earth-magic
    motes (white-green core, green halo, a fleck of grit), drawn by 219's own map-wide callback (patch_tectonic_shake_v1.py
    v2), which bobs them, twinkles them (bright <-> dim twin) and pushes each half away from the opening fissure."""
    W, H = 96, 64; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); bright = []
    for v in range(n):
        rnd = random.Random(21930 + v); acc = np.zeros((H, W, 3), np.float32)
        for k in range(rnd.randint(5, 7)):
            x, y = rnd.uniform(10, W - 10), rnd.uniform(9, H - 9); r = rnd.choice((1.2, 1.5, 1.9, 2.4))
            d2 = (xx - x) ** 2 + (yy - y) ** 2
            core = np.exp(-d2 / (2 * (0.55 * r) ** 2)); halo = np.exp(-d2 / (2 * (2.3 * r) ** 2)) * 0.42
            for c, (cv, hv) in enumerate(((215, 40), (255, 210), (200, 70))): acc[..., c] += core * cv + halo * hv
        for k in range(rnd.randint(2, 4)):                                       # specks of grit lifted with them
            x, y = rnd.uniform(6, W - 6), rnd.uniform(6, H - 6)
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 0.5) * 0.7
            for c, cv in enumerate((120, 200, 110)): acc[..., c] += g * cv
        bright.append(np.clip(acc, 0, 255))
    out = [Image.fromarray(a.astype(np.uint8), "RGB").convert("RGBA") for a in bright]
    out += [Image.fromarray((a * 0.42).astype(np.uint8), "RGB").convert("RGBA") for a in bright]   # dim twins (twinkle / fade)
    return out


def _crack_pts(v, W, H, jit):
    """A jagged crack SEGMENT whose ends sit exactly at the canvas centre -+(18, -9) - the callback lays segments
    every (36, -18) px along the diagonal, so neighbours join end to end."""
    rnd = random.Random(21940 + v); cx, cy = W / 2.0, H / 2.0
    p0, p1 = (cx - 18, cy + 9), (cx + 18, cy - 9); nx, ny = 9 / 20.12, 18 / 20.12   # unit normal of (36, -18)
    pts = [p0]
    for f in (0.22, 0.45, 0.63, 0.82):
        j = rnd.uniform(-jit, jit); pts.append((p0[0] + 36 * f + nx * j, p0[1] - 18 * f + ny * j))
    pts.append(p1)
    return pts, rnd


def tectonic_crack(n=3):
    """219 v3 slots 4-6: the thin fissure line (64x48, additive): a bright 1-px green-white jagged core with a tight green
    glow; laid along the screen diagonal it grows out from the centre, then (after the split) its two copies are the
    fissure's EDGES moving apart with the two halves."""
    W, H = 64, 48; out = []
    for v in range(n):
        pts, rnd = _crack_pts(v, W, H, 2.6)
        m = Image.new("L", (W * 4, H * 4), 0); ImageDraw.Draw(m).line([(x * 4, y * 4) for x, y in pts], fill=255, width=6)
        m = m.resize((W, H), Image.LANCZOS)
        a = np.asarray(m, np.float32) / 255.0
        g1 = np.asarray(m.filter(ImageFilter.GaussianBlur(1.6)), np.float32) / 255.0
        g2 = np.asarray(m.filter(ImageFilter.GaussianBlur(4.0)), np.float32) / 255.0
        acc = np.zeros((H, W, 3), np.float32)
        for c, (cv, v1, v2) in enumerate(((150, 40, 20), (255, 230, 150), (150, 70, 40))):
            acc[..., c] = a * cv + g1 * v1 * 1.1 + g2 * v2 * 0.9
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        for k in range(2):                                                       # a spark of grit on the line
            q = pts[rnd.randrange(1, len(pts) - 1)]; dr.point((q[0] + rnd.uniform(-2, 2), q[1] - rnd.uniform(1, 4)), fill=(170, 255, 170, 255))
        out.append(im)
    return out + [_tect_dim(im) for im in out]                                         # + dim twins (slots 14-16: fading out)


def _tect_dim(im, k=0.45):
    return Image.fromarray((np.asarray(im.convert("RGB"), np.float32) * k).astype(np.uint8), "RGB").convert("RGBA")


def tectonic_gap(n=3):
    """219 v3 slots 7-9: the OPEN fissure (80x56, additive): a broad green glow welling up along the crack line with a
    brighter seam and a few motes rising out of it - drawn on the line between the parting edges."""
    W, H = 80, 56; out = []
    for v in range(n):
        pts, rnd = _crack_pts(v + 7, W, H, 3.2)
        m = Image.new("L", (W * 4, H * 4), 0); ImageDraw.Draw(m).line([(x * 4, y * 4) for x, y in pts], fill=255, width=34)
        m = m.resize((W, H), Image.LANCZOS)
        g1 = np.asarray(m.filter(ImageFilter.GaussianBlur(3.0)), np.float32) / 255.0
        g2 = np.asarray(m.filter(ImageFilter.GaussianBlur(8.5)), np.float32) / 255.0
        s = Image.new("L", (W * 4, H * 4), 0); ImageDraw.Draw(s).line([(x * 4, y * 4) for x, y in pts], fill=255, width=6)
        s = np.asarray(s.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255.0
        acc = np.zeros((H, W, 3), np.float32)
        for c, (sv, v1, v2) in enumerate(((190, 40, 18), (255, 200, 120), (190, 70, 40))):
            acc[..., c] = s * sv + g1 * v1 + g2 * v2
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        for k in range(4):                                                       # motes welling up out of the gap
            q = pts[rnd.randrange(1, len(pts) - 1)]; x, y = q[0] + rnd.uniform(-3, 3), q[1] - rnd.uniform(4, 11)
            gg = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.6)
            for c, cv in enumerate((190, 255, 190)): acc[..., c] += gg * cv * 0.8
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out + [_tect_dim(im) for im in out]                                         # + dim twins (slots 17-19: fading out)


def tectonic_glow(n=12):
    """Tectonic Shift (219) slot 3 (2026-10-17; user: a very subtle green hex glow on every spawned terrain change,
    similar to but different from the others): drawn per TFrozenWaterHS marker by patch_tectonic_v1.py v3's glow cave
    (pure frame pick, 4 ticks/frame, additive 770).  32x24 like the Overgrowth / Drought glows, but instead of their
    breathing haze it is a faint emerald HEX RIM (a flattened hexagon traced just inside the hex) with a dim inner
    wash, and one brighter spark that runs once round the rim per cycle - like a seam of earth-magic settling - plus a
    single tiny grit speck rising from the middle."""
    W, H = 32, 24; cx, cy, rx, ry = 16.0, 12.5, 12.5, 7.5
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    verts = [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    def seg_d(px, py, a, b):
        ax, ay = a; bx, by = b; vx, vy = bx - ax, by - ay
        t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        return np.hypot(px - (ax + t * vx), py - (ay + t * vy))
    rim_d = np.min([seg_d(xx, yy, verts[k], verts[(k + 1) % 6]) for k in range(6)], axis=0)
    rim = np.exp(-(rim_d / 0.9) ** 2)
    wash = np.exp(-(((xx - cx) / 10.0) ** 2 + ((yy - cy) / 5.5) ** 2) * 1.4)
    perim = [(verts[k], verts[(k + 1) % 6]) for k in range(6)]
    frames = []
    for i in range(n):
        t = i / float(n); b = 0.5 + 0.5 * math.sin(2 * math.pi * t)
        k = int(t * 6) % 6; u = t * 6 - int(t * 6)
        (ax, ay), (bx, by) = perim[k]; sx, sy = ax + (bx - ax) * u, ay + (by - ay) * u
        spark = np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * 1.1 ** 2)) * 0.55
        uu = t; gy = cy + 3 - 9 * uu; grit = np.exp(-((xx - cx - 1) ** 2 + (yy - gy) ** 2) / (2 * 0.6 ** 2)) * math.sin(math.pi * uu) * 0.5
        a = np.clip(rim * (0.26 + 0.08 * b) + wash * (0.10 + 0.04 * b) + spark + grit, 0, 1)
        hot = np.clip(spark * 1.4 + grit, 0, 1)
        r = 40 * a + 150 * hot; g = 215 * a + 40 * hot; bl = 90 * a + 70 * hot
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(bl, 0, 255),
                                                 255 * (a > 0.015)]).astype(np.uint8), "RGBA"))
    return frames


def mend4_rocks(variant, n=50):
    """Mend Walls (216) v4 slots 3/4 (2026-10-17 round 4, user: "gfx is pretty good but janky or missing frames - smooth
    it out"): mend3_rocks re-rendered at ONE tick per frame (50 frames, f18 0; v3 was 26 x 2 ticks, so a rock pulled
    into the wall jumped ~10 px per frame) with every hand-over made continuous: rocks GROW out of the ground from 15 %
    (v3 popped in at 55 %), the torn ground opens over 3 ticks, the arc starts at the exact hover position / angle (v3
    snapped to a fixed launch point), and each rock shrinks into the wall over its last 3 ticks instead of vanishing.
    Same sources / targets / arrival ticks (MEND3_*) and the same hard 3-tone look, ALPHA 258, 224x212, hex centre at
    (112, 120)."""
    S = 4; W, H, AX, AY = MEND3_RW, MEND3_RH, MEND3_RAX, MEND3_RAY; bay = _MEND3_BAY
    src = _mend3_sources(variant); rnd = random.Random(2170 + variant)
    rocks = []
    for k in range(6):
        sx, sy = src[k]; tx, ty = MEND3_TARGETS[k]; arr = MEND3_ARRIVE[k]
        pop = arr - 26; launch = pop + 14
        ctrl = ((sx + tx) / 2.0 + rnd.uniform(-10, 10), min(sy - 14, ty) - rnd.uniform(26, 40))
        rocks.append(dict(sx=sx, sy=sy, tx=tx, ty=ty, pop=pop, launch=launch, arr=arr, ctrl=ctrl, fam=k % 2,
                          pts=_mend3_poly(rnd, rnd.uniform(5.2, 7.0)), spin=rnd.choice((-1, 1)) * rnd.uniform(5.0, 9.0),
                          peb=_mend3_poly(rnd, 2.0, 5), pebo=(rnd.uniform(-4, 4), rnd.uniform(1, 4)),
                          spurt=[(rnd.uniform(-1, 1), rnd.uniform(5, 10), _mend3_poly(rnd, 1.5, 5)) for _ in range(3)],
                          motes=[(rnd.uniform(0, 6.28), rnd.uniform(5, 9), rnd.uniform(0.25, 0.45)) for _ in range(5)],
                          jit=[(rnd.uniform(-1.5, 1.5), rnd.uniform(-1.5, 1.5)) for _ in range(3 * 26)]))

    def hover(R, t):
        gx, gy = AX + R["sx"], AY + R["sy"]
        u = min(1.0, max(0.0, (t - R["pop"]) / 10.0)); e = u * u * (3 - 2 * u)
        hov = math.sin(max(0.0, t - R["pop"] - 6) * 0.45) * 1.2 * min(1.0, max(0.0, (t - R["pop"] - 6) / 4.0))
        x, y = gx + math.sin(t * 0.35 + R["spin"]) * 0.6 * e, gy - 2 - 13 * e + hov
        return x, y, 0.2 * math.sin(t * 0.25), e
    out = []
    for i in range(n):
        t = float(i)
        big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); dr = ImageDraw.Draw(big)
        shade = Image.new("L", (W, H), 0); sd = ImageDraw.Draw(shade)
        hole = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(hole)
        specks = []
        for R in rocks:
            gx, gy = AX + R["sx"], AY + R["sy"]
            if R["pop"] <= t < R["launch"] + 12:                             # the torn ground: opens over 3 ticks, heals over 10
                o = min(1.0, (t - R["pop"] + 1) / 3.0)
                a = 1.0 if t < R["launch"] + 2 else max(0.0, 1.0 - (t - R["launch"] - 2) / 10.0)
                hd.ellipse([gx - 5.5 * o, gy - 2.2 * o, gx + 5.5 * o, gy + 2.6 * o], fill=int(255 * a))
            if R["pop"] <= t < R["pop"] + 9:                                   # pebble spurt
                u = (t - R["pop"]) / 9.0
                for vx, vy, pp in R["spurt"]:
                    px_ = gx + vx * 7 * u; py_ = gy - vy * 4 * u * (1 - u) * 1.6
                    _mend3_stamp(dr, S, pp, px_, py_, u * 6, 0.6 + 0.4 * min(1.0, u * 4), R["fam"])
            if R["pop"] <= t < R["launch"]:                                    # growing out of the ground + hovering
                x, y, rot, e = hover(R, t)
                sd.ellipse([gx - 6 * e - 1, gy - 1.5, gx + 6 * e + 1, gy + 1.8], fill=int(120 * e))
                _mend3_stamp(dr, S, R["pts"], x, y, rot, 0.15 + 0.85 * e, R["fam"])
                for ph, rr, sp in R["motes"]:
                    a = ph + t * sp; specks.append((x + math.cos(a) * rr, y + math.sin(a) * rr * 0.55 + 2, 0.25 + 0.75 * e))
            elif R["launch"] <= t < R["arr"]:                                  # pulled into the wall, continuous from the hover
                x0, y0, rot0, _e = hover(R, R["launch"])
                u = (t - R["launch"]) / float(R["arr"] - R["launch"]); e = u * u * (3 - 2 * u) * 0.35 + u * 0.65
                p0 = (x0, y0); p2 = (AX + R["tx"], AY + R["ty"]); p1 = (AX + R["ctrl"][0], AY + R["ctrl"][1])
                x, y = _mend3_bez(p0, p1, p2, e)
                shx, shy = gx + (AX + R["tx"] - gx) * e, gy + (AY - gy) * e
                sd.ellipse([shx - 5, shy - 1.5, shx + 5, shy + 1.8], fill=int(110 * (1 - u)))
                left = R["arr"] - t; sc = (1.0 - 0.2 * u) * (1.0 if left > 3 else 0.55 + 0.15 * left)
                _mend3_stamp(dr, S, R["pts"], x, y, rot0 + R["spin"] * u * 0.5, sc, R["fam"])
                j = int(t - R["launch"])
                for q, b in enumerate((0.05, 0.10, 0.15)):
                    if e - b > 0:
                        bx, by = _mend3_bez(p0, p1, p2, e - b); jx, jy = R["jit"][3 * (j // 2) + q]
                        specks.append((bx + jx, by + jy, 1.0 - b * 3))
            if R["launch"] + 3 <= t < R["arr"] + 3:                              # the trailing pebble (shrinks in too)
                u = (t - R["launch"] - 3) / float(R["arr"] - R["launch"])
                x0, y0, _r, _e = hover(R, R["launch"])
                p0 = (x0 + 3, y0 + 3); p2 = (AX + R["tx"] + R["pebo"][0], AY + R["ty"] + R["pebo"][1])
                p1 = (AX + R["ctrl"][0] + 6, AY + R["ctrl"][1] + 8)
                x, y = _mend3_bez(p0, p1, p2, u)
                left = R["arr"] + 3 - t
                _mend3_stamp(dr, S, R["peb"], x, y, R["spin"] * u * 0.65, 1.0 if left > 2 else 0.6 + 0.2 * left, 1 - R["fam"])
        im = big.resize((W, H), Image.BOX); a = np.array(im); hp = np.array(hole); sp_ = np.array(shade)
        thr = np.tile(np.array(bay, np.int32) * 16 + 8, (H // 4 + 1, W // 4 + 1))[:H, :W]
        solid = a[..., 3] >= 120
        a[~solid] = 0; a[solid, 3] = 255
        hm = (~solid) & (hp > thr) & (hp > 40); a[hm] = (30, 22, 16, 255)
        sm = (~solid) & (~hm) & (sp_ > thr); a[sm] = (16, 14, 12, 255)
        for x, y, s in specks:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W - 1 and 0 <= yi < H and s * 255 > thr[yi, xi]:
                a[yi, xi] = (150, 255, 160, 255)
                if s > 0.7: a[yi, xi + 1] = (70, 220, 110, 255)
        out.append(Image.fromarray(a, "RGBA"))
    return out


_MEND4_GLOW = []
MEND4_GLOW_T0 = 28                                          # first arrival: the glow is blank before it (one blank frame, repeated)


def mend4_glow(t_end=72):
    """Mend Walls (216) v4 slot 1: mend3_glow's art at ONE tick per frame (v3: 24 x 3 ticks - the arrival flashes,
    which decay over ~4 ticks, showed as 1-2 hard steps).  Frame 0 = blank (the slot's sequence repeats it for ticks
    0..27, before the first rock lands), frames 1..44 = ticks 28..71; the same 72-tick life as v3, ADDITIVE 770, 96x112,
    hex centre (48, 92).  The arrival flash now swells in over 2 ticks and decays a little slower (tau 5)."""
    if _MEND4_GLOW: return _MEND4_GLOW
    W, H, AX, AY = 96, 112, 48, 92
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2180)
    sparks = [[(rnd.uniform(0, 6.28), rnd.uniform(9, 16), rnd.uniform(-0.3, 0.1)) for _ in range(8)] for _ in range(6)]
    motes = [(rnd.uniform(-16, 16), rnd.uniform(0, 1), rnd.uniform(0.6, 1.0), rnd.uniform(0, 6.28)) for _ in range(16)]
    colx = np.exp(-((xx - AX) ** 2) / (2 * 13.0 ** 2)); coly = np.clip((AY + 6 - yy) / 8.0, 0, 1) * np.clip((yy - (AY - 66)) / 14.0, 0, 1)
    _MEND4_GLOW.append(Image.new("RGB", (W, H), (0, 0, 0)).convert("RGBA"))
    for ti in range(MEND4_GLOW_T0, t_end):
        t = float(ti); acc = np.zeros((H, W, 3), np.float32)

        def add(g, col):
            for c, cv in enumerate(col): acc[..., c] += g * cv
        for k, (tx, ty) in enumerate(MEND3_TARGETS):
            d = t - MEND3_ARRIVE[k] + 1
            if 0 <= d < 18:
                x, y = AX + tx, AY + ty; f = min(1.0, (d + 1) / 2.0) * math.exp(-d / 5.0)
                add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (2.5 + d * 0.3) ** 2)) * f * 1.1, (170, 255, 185))
                add(np.exp(-((yy - y) ** 2) / 1.2 - ((xx - x) ** 2) / (2 * (3 + d * 0.7) ** 2)) * f * 0.7, (90, 240, 130))
                for a, r, vy in sparks[k]:
                    u = d / 18.0; sx = x + math.cos(a) * r * (1 - (1 - u) ** 2); sy = y + math.sin(a) * r * 0.7 * (1 - (1 - u) ** 2) + vy * d * 2.5
                    add(np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / 1.1) * (1 - u) * 0.95, (190, 255, 200))
        ramp = min(1.0, max(0.0, (t - MEND3_ARRIVE[0] + 1) / 18.0))
        fade = 1.0 if t < 52 else max(0.0, 1.0 - (t - 52) / 19.0)
        env = ramp * fade; env = env * env * (3 - 2 * env)
        add(colx * coly * (0.82 + 0.18 * np.sin(yy * 0.35 - t * 0.45 + xx * 0.12)) * 0.42 * env, (40, 210, 95))
        u = (t - 44) / 16.0
        if 0 <= u <= 1:
            by = AY + 4 - u * 70
            add(np.exp(-((yy - by) ** 2) / (2 * 1.6 ** 2)) * np.exp(-((xx - AX) ** 2) / (2 * 12.0 ** 2)) * math.sin(math.pi * u) * 0.7, (150, 255, 175))
        add(np.exp(-((xx - AX) ** 2) / (2 * 16.0 ** 2) - ((yy - AY - 2) ** 2) / (2 * 2.4 ** 2)) * 0.4 * env, (60, 230, 110))
        for x0, ph, sp, tw in motes:
            if t < 34: continue
            v = (ph + (t - 34) / 38.0 * sp * 1.3) % 1.0
            y = AY - 2 - v * 72; x = AX + x0 + 2.5 * math.sin(tw + v * 7.0)
            a = math.sin(math.pi * v) * (0.65 + 0.35 * math.sin(tw + t * 0.8)) * fade * min(1.0, (t - 34) / 4.0)
            add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * a, (190, 255, 205))
        _MEND4_GLOW.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return _MEND4_GLOW


TECT_K = 10                                   # brightness levels per Tectonic fissure image (patch_tectonic_shake_v1.py v3 K)


def _tect_levels(frames, K=TECT_K, gamma=0.85):
    """Tectonic Shift (219) v4 (2026-10-17, user: "give it a smoother fade out"): every fissure / mote image as K
    brightness LEVELS (level k = (1 - k/K)^0.85 of the full image, variant-major: v0 L0..L9, v1 L0..L9, ...).  219's own
    map-wide callback (patch_tectonic_shake_v1.py v3) picks the level per draw through TImageSequenceList.Show's time
    argument (kind 4, f18 0 -> frame = time), easing every element out (and the motes in) instead of the v3 bright ->
    dim-twin -> gone steps; each element is dithered in time so the levels never step all at once."""
    out = []
    for im in frames:
        a = np.asarray(im.convert("RGB"), np.float32)
        for k in range(K):
            out.append(Image.fromarray(np.clip(a * (1.0 - k / float(K)) ** gamma, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def tectonic_motes_lv():
    return _tect_levels(tectonic_motes()[:3])          # slots 0-2: the three hovering mote clusters x K levels


def tectonic_crack_lv():
    return _tect_levels(tectonic_crack()[:3])          # slots 4-6: the fissure line / its parting edges x K levels


def tectonic_gap_lv():
    return _tect_levels(tectonic_gap()[:3])            # slots 7-9: the open glowing gap x K levels


def tectonic_glow2(n=48):
    """Tectonic Shift (219) slot 3 v2 (2026-10-17, user: "the hex glow is bad - colour is fine but more subtle; instead of
    circling particles have particles moving up and fading as they reach their peak; they look like they're missing
    frames - make sure they're smooth, and subtle"): the v1 glow was 12 frames at 4 ticks each with a spark jumping ~5 px
    per frame round the rim.  v2 = 48 frames x 2 ticks (patch_tectonic_v1.py v3.1 GLOW_PERIOD 2; a 2.8 s seamless loop):
    a much fainter emerald hex rim + wash breathing once per loop, and four soft green motes rising out of the hex at
    staggered phases - each fades in, rises ~13 px with an ease-out (slowing as it nears its peak) and fades to nothing
    at the top; sub-pixel gaussian motes moving < 0.3 px per frame, so nothing steps.  32x40 additive, the hex centre at
    canvas (16, 29.5) -> anchor (-16, -31): the same spot as v1 (-16, -14 on its 32x24)."""
    W, H = 32, 40; cx, cy, rx, ry = 16.0, 29.5, 12.5, 7.5
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    verts = [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    def seg_d(px, py, a, b):
        ax, ay = a; bx, by = b; vx, vy = bx - ax, by - ay
        t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        return np.hypot(px - (ax + t * vx), py - (ay + t * vy))
    rim = np.exp(-(np.min([seg_d(xx, yy, verts[k], verts[(k + 1) % 6]) for k in range(6)], axis=0) / 0.9) ** 2)
    wash = np.exp(-(((xx - cx) / 10.0) ** 2 + ((yy - cy) / 5.5) ** 2) * 1.4)
    #        x0     y0    rise  sway  sway-ph  sigma  phase
    motes = [(12.0, 32.5, 13.0, 0.8, 0.10, 0.95, 0.00),
             (19.5, 29.5, 12.0, 0.7, 0.55, 0.85, 0.25),
             (15.0, 34.0, 14.5, 0.9, 0.30, 0.90, 0.50),
             (21.5, 33.0, 11.5, 0.6, 0.80, 0.80, 0.75)]
    peak = (0.82 ** 1.6)
    frames = []
    for i in range(n):
        t = i / float(n); b = 0.5 + 0.5 * math.cos(2 * math.pi * t)
        a = rim * (0.12 + 0.03 * b) + wash * (0.04 + 0.015 * b); hot = np.zeros_like(a)
        for x0, y0, rise, sway, sph, sig, ph in motes:
            u = (t + ph) % 1.0
            y = y0 - rise * (1.0 - (1.0 - u) ** 2)                          # ease-out: slows as it nears the peak
            x = x0 + sway * math.sin(2 * math.pi * (u + sph))
            br = min(1.0, u / 0.18) ** 1.5 * (1.0 - u) ** 1.6 / peak          # fades in fast, fades out toward the top
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sig * sig)) * br * 0.55
            a = a + g; hot = hot + g * 0.55
        a = np.clip(a, 0, 1); hot = np.clip(hot, 0, 1)
        r = 40 * a + 120 * hot; g_ = 215 * a + 40 * hot; bl = 90 * a + 60 * hot
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g_, 0, 255), np.clip(bl, 0, 255),
                                                 255 * (a > 0.012)]).astype(np.uint8), "RGBA"))
    return frames


def tectonic_glow3(n=48):
    """Tectonic Shift (219) slot 3 v3 (2026-10-17, user: "the hex glow is too subtle, I can't see it"): tectonic_glow2's
    design and timing unchanged (48 frames x 2 ticks, 2.8 s seamless loop; an emerald hex rim + wash breathing once per
    loop and four green motes rising out of the hex, easing out and fading at their peak) - only the strengths go up:
    rim 0.12 -> 0.46 (+0.08 breathing), wash 0.04 -> 0.13, motes 0.55 -> 0.95 with a whiter core, played at blend 70
    (v2: 45).  Under GFXE Intensity that is ~+10..20 % light on grass / desert / dirt, a clear green tint on dark cave
    dirt and still visible on snow; the motes read as small bright sparks.  32x40 additive, anchor (-16, -31)."""
    W, H = 32, 40; cx, cy, rx, ry = 16.0, 29.5, 12.5, 7.5
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    verts = [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    def seg_d(px, py, a, b):
        ax, ay = a; bx, by = b; vx, vy = bx - ax, by - ay
        t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
        return np.hypot(px - (ax + t * vx), py - (ay + t * vy))
    rim = np.exp(-(np.min([seg_d(xx, yy, verts[k], verts[(k + 1) % 6]) for k in range(6)], axis=0) / 1.0) ** 2)
    wash = np.exp(-(((xx - cx) / 10.0) ** 2 + ((yy - cy) / 5.5) ** 2) * 1.4)
    #        x0     y0    rise  sway  sway-ph  sigma  phase
    motes = [(12.0, 32.5, 13.0, 0.8, 0.10, 1.00, 0.00),
             (19.5, 29.5, 12.0, 0.7, 0.55, 0.90, 0.25),
             (15.0, 34.0, 14.5, 0.9, 0.30, 0.95, 0.50),
             (21.5, 33.0, 11.5, 0.6, 0.80, 0.85, 0.75)]
    peak = (0.82 ** 1.6)
    frames = []
    for i in range(n):
        t = i / float(n); b = 0.5 + 0.5 * math.cos(2 * math.pi * t)
        a = rim * (0.46 + 0.08 * b) + wash * (0.13 + 0.03 * b); hot = np.zeros_like(a)
        for x0, y0, rise, sway, sph, sig, ph in motes:
            u = (t + ph) % 1.0
            y = y0 - rise * (1.0 - (1.0 - u) ** 2)                          # ease-out: slows as it nears the peak
            x = x0 + sway * math.sin(2 * math.pi * (u + sph))
            br = min(1.0, u / 0.18) ** 1.5 * (1.0 - u) ** 1.6 / peak          # fades in fast, fades out toward the top
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sig * sig)) * br * 0.95
            a = a + g; hot = hot + g * 0.75
        a = np.clip(a, 0, 1); hot = np.clip(hot, 0, 1)
        r = 40 * a + 130 * hot; g_ = 215 * a + 40 * hot; bl = 90 * a + 80 * hot
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g_, 0, 255), np.clip(bl, 0, 255),
                                                 255 * (a > 0.012)]).astype(np.uint8), "RGBA"))
    return frames


MEND5_POP = [0, 2, 4, 6, 8, 10]                              # ticks: debris k grows out of the ground
MEND5_FLY = 5                                               # v6: ticks of flight (was 8): launch = MEND6_ARRIVE[k] - 5 (flung, quick)
MEND6_ARRIVE = [21, 26, 31, 36, 41, 46]                     # v6 10/17 (user: staggered, not all at once): ONE piece flung every 5 ticks
                                                            # (launches 16/21/26/31/36/41; v5 28..43 every 3 with 8-tick flights = 3 in the air)
MEND5_STICK = (1, 4)                                        # debris 1 and 4 are brown sticks, the rest grey rocks


def _mend5_paths(variant):
    """Shared debris motion for mend5_rocks (alpha) and mend5_halo (additive): per debris k a function t -> (x, y, rot,
    scale, phase) or None, on the 224x212 canvas (hex centre MEND3_RAX/RAY); phase 1 growing / 2 shaking / 3 flying.
    Sources = _mend3_sources (2-3 hexes out), targets = MEND3_TARGETS, arrivals = MEND3_ARRIVE (28..43, shared with
    the wall glow).  grow 6 ticks (15 % -> full, lifting 3 px) -> shake in place (jitter 0.5 -> 1.5 px, lifted 3 -> 6 px;
    a deterministic per-tick jitter = the charging tremble) -> flung: a shallow arc on an accelerating ease (u^1.7),
    shrinking into the wall over the last 2 ticks."""
    AX, AY = MEND3_RAX, MEND3_RAY
    src = _mend3_sources(variant); rnd = random.Random(2190 + variant); paths = []
    for k in range(6):
        sx, sy = AX + src[k][0], AY + src[k][1]; tx, ty = AX + MEND3_TARGETS[k][0], AY + MEND3_TARGETS[k][1]
        pop = MEND5_POP[k]; arr = MEND6_ARRIVE[k]; launch = arr - MEND5_FLY
        jit = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)) for _ in range(64)]
        rot0 = rnd.uniform(-0.6, 0.6); spin = rnd.choice((-1, 1)) * rnd.uniform(2.5, 4.5)
        arc = rnd.uniform(14, 22)

        def f(t, sx=sx, sy=sy, tx=tx, ty=ty, pop=pop, arr=arr, launch=launch, jit=jit, rot0=rot0, spin=spin, arc=arc):
            if t < pop or t >= arr: return None
            if t < pop + 6:
                u = (t - pop + 1) / 6.0; e = u * u * (3 - 2 * u)
                return sx, sy - 3 * e, rot0, 0.15 + 0.85 * e, 1
            if t < launch:
                u = min(1.0, (t - pop - 6) / 6.0); amp = 0.5 + 1.0 * u
                jx, jy, jr = jit[int(t) % 64]
                lift = 3 + 3 * (u * u * (3 - 2 * u))
                return sx + jx * amp, sy - lift + jy * amp * 0.6, rot0 + jr * 0.10 * amp, 1.0, 2
            u = (t - launch + 1) / float(MEND5_FLY); e = u ** 1.7
            x0, y0 = sx, sy - 6
            x = x0 + (tx - x0) * e; y = y0 + (ty - y0) * e - arc * 4 * e * (1 - e)
            left = arr - t; sc = 1.0 if left > 2 else 0.55 + 0.2 * left
            return x, y, rot0 + spin * e, sc, 3
        f.ground = (sx, sy)
        paths.append(f)
    return paths


def _mend5_stick(dr, S, x, y, rot, sc, L=13.0, w=2.0):
    """A brown stick: a slightly bent bar with a dark rim, a lit edge and one short twig."""
    c, s_ = math.cos(rot), math.sin(rot)

    def P(pts): return [((x + (px * c - py * s_) * sc) * S, (y + (px * s_ + py * c) * sc) * S) for px, py in pts]
    h = L / 2
    bar = [(-h, -w / 2), (0, -w / 2 - 0.6), (h, -w / 2), (h, w / 2), (0, w / 2 - 0.6), (-h, w / 2)]
    twig = [(1.0, -0.6), (3.6, -3.4), (4.4, -3.0), (2.2, 0.0)]
    rim = [(px + (0.7 if px > 0 else -0.7), py + (0.7 if py > 0 else -0.7)) for px, py in bar]
    dr.polygon(P(rim), fill=(38, 24, 12, 255))
    dr.polygon(P([(px + 0.6, py - 0.6) for px, py in twig]), fill=(38, 24, 12, 255))
    dr.polygon(P(bar), fill=(112, 74, 38, 255))
    dr.polygon(P(twig), fill=(104, 70, 36, 255))
    dr.polygon(P([(-h + 1, -w / 2 + 0.1), (h - 1, -w / 2 + 0.1), (h - 1, -w / 2 + 0.7), (-h + 1, -w / 2 + 0.7)]), fill=(158, 114, 66, 255))


def mend5_rocks(variant, n=50):
    """Mend Walls (216) v5 slots 3/4 (2026-10-17 round 5, user: debris should look more like grey rocks and brown
    sticks; it should shake in place when first spawned with the green glow, then levitate to the walls fairly quickly,
    almost like getting flung at the walls): four GREY rocks (hard 3-tone, two shades) + two BROWN sticks grow out of
    torn ground 2-3 hexes away (a small grey pebble spurt), tremble in place lifted a few px, then are flung along a
    shallow accelerating arc into the wall body (_mend5_paths), shrinking in over the last 2 ticks.  No green in this
    layer (the glow is mend5_halo, additive).  ALPHA 258, 224x212, hex centre (112, 120), 1 tick per frame."""
    S = 4; W, H = MEND3_RW, MEND3_RH; bay = _MEND3_BAY
    paths = _mend5_paths(variant); rnd = random.Random(2195 + variant)
    shapes = [_mend3_poly(rnd, rnd.uniform(5.0, 6.6)) for _ in range(6)]
    sticks = [rnd.uniform(11.5, 14.5) for _ in range(6)]
    spurts = [[(rnd.uniform(-1, 1), rnd.uniform(5, 9), _mend3_poly(rnd, 1.3, 5)) for _ in range(3)] for _ in range(6)]
    tones = (((34, 33, 32), (112, 110, 106), (170, 168, 162)), ((28, 28, 30), (88, 88, 92), (140, 140, 146)))
    out = []
    for i in range(n):
        t = float(i)
        big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); dr = ImageDraw.Draw(big)
        shade = Image.new("L", (W, H), 0); sd = ImageDraw.Draw(shade)
        hole = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(hole)
        for k, f in enumerate(paths):
            pop = MEND5_POP[k]; launch = MEND6_ARRIVE[k] - MEND5_FLY; gx, gy = f.ground
            if pop <= t < launch + 8:
                o = min(1.0, (t - pop + 1) / 3.0); a = 1.0 if t < launch else max(0.0, 1.0 - (t - launch) / 8.0)
                hd.ellipse([gx - 5.0 * o, gy - 2.0 * o, gx + 5.0 * o, gy + 2.4 * o], fill=int(255 * a))
            if pop <= t < pop + 8:                                                  # grey pebble spurt
                u = (t - pop) / 8.0
                for vx, vy, pp in spurts[k]:
                    _mend3_stamp(dr, S, pp, gx + vx * 6 * u, gy - vy * 4 * u * (1 - u) * 1.6, u * 6, 0.6 + 0.4 * min(1.0, u * 4), 0)
            p = f(t)
            if p is None: continue
            x, y, rot, sc, ph = p
            if ph in (1, 2):
                e = sc if ph == 1 else 1.0
                sd.ellipse([gx - 5.5 * e - 1, gy - 1.4, gx + 5.5 * e + 1, gy + 1.7], fill=int(110 * e))
            else:
                u = (t - launch + 1) / float(MEND5_FLY); shy = gy + (MEND3_RAY - gy) * u
                sd.ellipse([x - 4.5, shy - 1.3, x + 4.5, shy + 1.6], fill=int(100 * (1 - u)))
            if k in MEND5_STICK:
                _mend5_stick(dr, S, x, y, rot, sc, sticks[k])
            else:
                pts = shapes[k]; rim, body, lit = tones[k % 2]
                r0 = sum(rr for _a, rr in pts) / len(pts)

                def P(grow_, shx_=0.0, shy_=0.0, kk=1.0):
                    return [((x + shx_ + math.cos(a + rot) * (rr * sc * kk + grow_)) * S, (y + shy_ + math.sin(a + rot) * (rr * sc * kk + grow_) * 0.9) * S) for a, rr in pts]
                dr.polygon(P(1.0), fill=rim + (255,)); dr.polygon(P(0.0), fill=body + (255,))
                dr.polygon(P(0.0, -0.3 * r0 * sc, -0.35 * r0 * sc, 0.5), fill=lit + (255,))
        im = big.resize((W, H), Image.BOX); a = np.array(im); hp = np.array(hole); sp_ = np.array(shade)
        thr = np.tile(np.array(bay, np.int32) * 16 + 8, (H // 4 + 1, W // 4 + 1))[:H, :W]
        solid = a[..., 3] >= 120
        a[~solid] = 0; a[solid, 3] = 255
        hm = (~solid) & (hp > thr) & (hp > 40); a[hm] = (30, 26, 22, 255)
        sm = (~solid) & (~hm) & (sp_ > thr); a[sm] = (16, 14, 12, 255)
        out.append(Image.fromarray(a, "RGBA"))
    return out


def mend5_halo(variant, n=50):
    """Mend Walls (216) v5 slots 5/6: the SUBTLE green glow on the debris of mend5_rocks (same _mend5_paths), ADDITIVE
    770, 224x212, hex centre (112, 120), 1 tick per frame: a faint emerald halo swells in as each piece starts to
    tremble (flickering with the shake), a few tiny motes drift up off it, and in flight a short fading streak trails
    it; the glow ends where the piece sinks into the wall (the wall glow's arrival burst takes over there)."""
    W, H = MEND3_RW, MEND3_RH; paths = _mend5_paths(variant); rnd = random.Random(2197 + variant)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    motes = [[(rnd.uniform(-5, 5), rnd.uniform(0, 1), rnd.uniform(0.04, 0.07)) for _ in range(3)] for _ in range(6)]
    out = []
    for i in range(n):
        t = float(i); acc = np.zeros((H, W), np.float32)

        def g(x, y, s, a):
            x0, x1 = max(0, int(x - 3 * s - 1)), min(W, int(x + 3 * s + 2)); y0, y1 = max(0, int(y - 3 * s - 1)), min(H, int(y + 3 * s + 2))
            if x0 < x1 and y0 < y1:
                acc[y0:y1, x0:x1] += a * np.exp(-((xx[y0:y1, x0:x1] - x) ** 2 + (yy[y0:y1, x0:x1] - y) ** 2) / (2 * s * s))
        for k, f in enumerate(paths):
            p = f(t)
            if p is None: continue
            x, y, rot, sc, ph = p; pop = MEND5_POP[k]
            if ph == 1:
                lv = 0.06 * sc
            elif ph == 2:
                u = min(1.0, (t - pop - 6) / 5.0); lv = 0.06 + 0.16 * u * u * (3 - 2 * u)
                lv *= 0.88 + 0.12 * math.sin(t * 2.3 + k)
            else:
                lv = 0.22
            g(x, y, 5.5 * max(0.5, sc), lv)
            g(x, y, 2.6 * max(0.5, sc), lv * 0.6)
            if ph == 3:
                for q, b in enumerate((1.0, 2.0, 3.0)):
                    pb = f(t - b)
                    if pb is not None and pb[4] == 3: g(pb[0], pb[1], 3.0, lv * (0.5 - 0.14 * q))
            if ph >= 2:
                for mx, ph0, sp in motes[k]:
                    v = (ph0 + (t - pop - 6) * sp) % 1.0
                    a = math.sin(math.pi * v) * 0.3 * min(1.0, (t - pop - 6) / 4.0) * (1.0 if ph == 2 else 0.4)
                    g(x + mx, y - 2 - v * 12, 0.9, a)
        rgb = np.dstack([acc * 70, acc * 235, acc * 120]).clip(0, 255).astype(np.uint8)
        out.append(Image.fromarray(rgb, "RGB").convert("RGBA"))
    return out


_MEND5_GLOW = []


def mend5_glow(t_end=72):
    """Mend Walls (216) v5 slot 1: mend4_glow UNCHANGED (green aura / rising band / ground ellipse / motes on the wall
    hex - user: the existing wall hex green circle thing unchanged) except the per-rock ARRIVAL, now a SMALL, SUBTLE
    green particle burst (user round 5): a soft flash at ~40 % of v4 and six fine sparks spraying 5-10 px and fading
    (v4: a bright 1.1 flash + a horizontal flare + 8 sparks to 16 px).  Same ids / sequence / 72-tick life as v4."""
    if _MEND5_GLOW: return _MEND5_GLOW
    W, H, AX, AY = 96, 112, 48, 92
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2180)
    _sparks4 = [[(rnd.uniform(0, 6.28), rnd.uniform(9, 16), rnd.uniform(-0.3, 0.1)) for _ in range(8)] for _ in range(6)]   # (v4's draws, kept so the motes match v4)
    motes = [(rnd.uniform(-16, 16), rnd.uniform(0, 1), rnd.uniform(0.6, 1.0), rnd.uniform(0, 6.28)) for _ in range(16)]
    rnd5 = random.Random(2185)
    sparks5 = [[(rnd5.uniform(0, 6.28), rnd5.uniform(5, 10), rnd5.uniform(-0.25, 0.05)) for _ in range(6)] for _ in range(6)]
    colx = np.exp(-((xx - AX) ** 2) / (2 * 13.0 ** 2)); coly = np.clip((AY + 6 - yy) / 8.0, 0, 1) * np.clip((yy - (AY - 66)) / 14.0, 0, 1)
    _MEND5_GLOW.append(Image.new("RGB", (W, H), (0, 0, 0)).convert("RGBA"))
    for ti in range(MEND4_GLOW_T0, t_end):
        t = float(ti); acc = np.zeros((H, W, 3), np.float32)

        def add(g, col):
            for c, cv in enumerate(col): acc[..., c] += g * cv
        for k, (tx, ty) in enumerate(MEND3_TARGETS):
            d = t - MEND3_ARRIVE[k] + 1
            if 0 <= d < 14:
                x, y = AX + tx, AY + ty; f = min(1.0, (d + 1) / 2.0) * math.exp(-d / 4.0)
                add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (2.0 + d * 0.25) ** 2)) * f * 0.42, (150, 255, 175))
                for a, r, vy in sparks5[k]:
                    u = d / 14.0; sx = x + math.cos(a) * r * (1 - (1 - u) ** 2); sy = y + math.sin(a) * r * 0.7 * (1 - (1 - u) ** 2) + vy * d * 2.0
                    add(np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / 0.8) * (1 - u) ** 1.3 * 0.55, (170, 255, 190))
        ramp = min(1.0, max(0.0, (t - MEND3_ARRIVE[0] + 1) / 18.0))
        fade = 1.0 if t < 52 else max(0.0, 1.0 - (t - 52) / 19.0)
        env = ramp * fade; env = env * env * (3 - 2 * env)
        add(colx * coly * (0.82 + 0.18 * np.sin(yy * 0.35 - t * 0.45 + xx * 0.12)) * 0.42 * env, (40, 210, 95))
        u = (t - 44) / 16.0
        if 0 <= u <= 1:
            by = AY + 4 - u * 70
            add(np.exp(-((yy - by) ** 2) / (2 * 1.6 ** 2)) * np.exp(-((xx - AX) ** 2) / (2 * 12.0 ** 2)) * math.sin(math.pi * u) * 0.7, (150, 255, 175))
        add(np.exp(-((xx - AX) ** 2) / (2 * 16.0 ** 2) - ((yy - AY - 2) ** 2) / (2 * 2.4 ** 2)) * 0.4 * env, (60, 230, 110))
        for x0, ph, sp, tw in motes:
            if t < 34: continue
            v = (ph + (t - 34) / 38.0 * sp * 1.3) % 1.0
            y = AY - 2 - v * 72; x = AX + x0 + 2.5 * math.sin(tw + v * 7.0)
            a = math.sin(math.pi * v) * (0.65 + 0.35 * math.sin(tw + t * 0.8)) * fade * min(1.0, (t - 34) / 4.0)
            add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * a, (190, 255, 205))
        _MEND5_GLOW.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return _MEND5_GLOW


_MEND6_GLOW = []


def mend6_glow(t_end=72):
    """Mend Walls (216) v6 slot 1 (2026-10-17, user: debris flung in a staggered order): mend5_glow re-timed to the
    staggered arrivals MEND6_ARRIVE (21/26/31/36/41/46) - one small subtle burst per piece as it lands, the aura ramping
    in from the FIRST arrival (tick 21, v5 28) and the rising band moved to ticks 48-64 so it sweeps up after the LAST
    piece (v5 44-60); the look (aura, band, ground ellipse, motes, fade 52-71) is unchanged.  72-tick life as before:
    one blank frame + 51 frames (ticks 21..71) -> NEW ids 4900-4951 (v5 4700-4744 had a 28-tick blank prefix)."""
    if _MEND6_GLOW: return _MEND6_GLOW
    W, H, AX, AY = 96, 112, 48, 92
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2180)
    _sparks4 = [[(rnd.uniform(0, 6.28), rnd.uniform(9, 16), rnd.uniform(-0.3, 0.1)) for _ in range(8)] for _ in range(6)]   # (v4's draws, kept so the motes match v4/v5)
    motes = [(rnd.uniform(-16, 16), rnd.uniform(0, 1), rnd.uniform(0.6, 1.0), rnd.uniform(0, 6.28)) for _ in range(16)]
    rnd5 = random.Random(2185)
    sparks5 = [[(rnd5.uniform(0, 6.28), rnd5.uniform(5, 10), rnd5.uniform(-0.25, 0.05)) for _ in range(6)] for _ in range(6)]
    colx = np.exp(-((xx - AX) ** 2) / (2 * 13.0 ** 2)); coly = np.clip((AY + 6 - yy) / 8.0, 0, 1) * np.clip((yy - (AY - 66)) / 14.0, 0, 1)
    _MEND6_GLOW.append(Image.new("RGB", (W, H), (0, 0, 0)).convert("RGBA"))
    for ti in range(MEND6_ARRIVE[0], t_end):
        t = float(ti); acc = np.zeros((H, W, 3), np.float32)

        def add(g, col):
            for c, cv in enumerate(col): acc[..., c] += g * cv
        for k, (tx, ty) in enumerate(MEND3_TARGETS):
            d = t - MEND6_ARRIVE[k] + 1
            if 0 <= d < 14:
                x, y = AX + tx, AY + ty; f = min(1.0, (d + 1) / 2.0) * math.exp(-d / 4.0)
                add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (2.0 + d * 0.25) ** 2)) * f * 0.42, (150, 255, 175))
                for a, r, vy in sparks5[k]:
                    u = d / 14.0; sx = x + math.cos(a) * r * (1 - (1 - u) ** 2); sy = y + math.sin(a) * r * 0.7 * (1 - (1 - u) ** 2) + vy * d * 2.0
                    add(np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / 0.8) * (1 - u) ** 1.3 * 0.55, (170, 255, 190))
        ramp = min(1.0, max(0.0, (t - MEND6_ARRIVE[0] + 1) / 18.0))
        fade = 1.0 if t < 52 else max(0.0, 1.0 - (t - 52) / 19.0)
        env = ramp * fade; env = env * env * (3 - 2 * env)
        add(colx * coly * (0.82 + 0.18 * np.sin(yy * 0.35 - t * 0.45 + xx * 0.12)) * 0.42 * env, (40, 210, 95))
        u = (t - 48) / 16.0
        if 0 <= u <= 1:
            by = AY + 4 - u * 70
            add(np.exp(-((yy - by) ** 2) / (2 * 1.6 ** 2)) * np.exp(-((xx - AX) ** 2) / (2 * 12.0 ** 2)) * math.sin(math.pi * u) * 0.7, (150, 255, 175))
        add(np.exp(-((xx - AX) ** 2) / (2 * 16.0 ** 2) - ((yy - AY - 2) ** 2) / (2 * 2.4 ** 2)) * 0.4 * env, (60, 230, 110))
        for x0, ph, sp, tw in motes:
            if t < 34: continue
            v = (ph + (t - 34) / 38.0 * sp * 1.3) % 1.0
            y = AY - 2 - v * 72; x = AX + x0 + 2.5 * math.sin(tw + v * 7.0)
            a = math.sin(math.pi * v) * (0.65 + 0.35 * math.sin(tw + t * 0.8)) * fade * min(1.0, (t - 34) / 4.0)
            add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * a, (190, 255, 205))
        _MEND6_GLOW.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return _MEND6_GLOW


def tectonic_glow4(n=48):
    """Tectonic Shift (219) slot 3 v4 (2026-10-17, user: "the hex glows have weird green hexagons, get rid of those, and
    make the particles slightly more subtle"): glow3's hex RIM is gone; what is left is a very soft round ground wash
    (breathing once per loop) under four green motes rising out of the hex, easing out and fading at their peak - motes
    ~10 % dimmer than glow3 (0.95 -> 0.86, whiter core 0.75 -> 0.65).  Same canvas / anchor / timing as glow2-3 (32x40,
    anchor (-16, -31), 48 frames x 2 ticks = 2.8 s seamless loop; same ids 4750-4797), additive, played at blend 65."""
    W, H = 32, 40; cx, cy = 16.0, 30.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    wash = np.exp(-(((xx - cx) / 8.5) ** 2 + ((yy - cy) / 4.6) ** 2) * 1.6)      # round, soft, no edge
    #        x0     y0    rise  sway  sway-ph  sigma  phase
    motes = [(12.0, 32.5, 13.0, 0.8, 0.10, 1.00, 0.00),
             (19.5, 29.5, 12.0, 0.7, 0.55, 0.90, 0.25),
             (15.0, 34.0, 14.5, 0.9, 0.30, 0.95, 0.50),
             (21.5, 33.0, 11.5, 0.6, 0.80, 0.85, 0.75)]
    peak = (0.82 ** 1.6)
    frames = []
    for i in range(n):
        t = i / float(n); b = 0.5 + 0.5 * math.cos(2 * math.pi * t)
        a = wash * (0.10 + 0.03 * b); hot = np.zeros_like(a)
        for x0, y0, rise, sway, sph, sig, ph in motes:
            u = (t + ph) % 1.0
            y = y0 - rise * (1.0 - (1.0 - u) ** 2)                          # ease-out: slows as it nears the peak
            x = x0 + sway * math.sin(2 * math.pi * (u + sph))
            br = min(1.0, u / 0.18) ** 1.5 * (1.0 - u) ** 1.6 / peak          # fades in fast, fades out toward the top
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sig * sig)) * br * 0.86
            a = a + g; hot = hot + g * 0.65
        a = np.clip(a, 0, 1); hot = np.clip(hot, 0, 1)
        r = 40 * a + 130 * hot; g_ = 215 * a + 40 * hot; bl = 90 * a + 80 * hot
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g_, 0, 255), np.clip(bl, 0, 255),
                                                 255 * (a > 0.012)]).astype(np.uint8), "RGBA"))
    return frames


MEND7_POP, MEND7_TREM, MEND7_POST, MEND7_FLY = 8, 12, 15, 5     # = patch_tc_mendwalls_v2.py v7 POP / TREM / POST / FLY
MEND7_E = [0, 19, 59, 113, 179, 256]                            # = the engine's flight ease ETAB (x256)
MEND7_W, MEND7_H, MEND7_AX, MEND7_AY = 48, 56, 24, 40           # piece canvas; anchor = the engine's point (rock centre at rest)


def _mend7_pose(i):
    """Piece pose for frame i of a v7 piece sequence (0 = blank): -> None or (dx, dy, rot, scale, phase) relative to the
    anchor.  Phase 1 grow (8 frames: 15 % -> full, lifting to 6 px, the tremble fading in over the last 3), 2 tremble
    (12-frame LOOP, seamless: integer harmonics of the loop, bobbing 6 +- 0.8 px), 3 flight (5 frames: the engine moves
    the point on its accelerating arc; the lift eases 6 -> 0 with the same ease so the piece lands exactly on the
    target, spinning), 4 = sinking into the wall (2 frames, 0.7 / 0.4 scale), then blank."""
    def jit(q):
        a = 2 * math.pi * q / MEND7_TREM
        return 1.1 * math.sin(3 * a) + 0.5 * math.sin(5 * a + 1.0), 0.6 * math.sin(4 * a + 0.5), 0.08 * math.sin(2 * a)
    if i <= 0: return None
    i -= 1
    if i < MEND7_POP:
        e = min(1.0, (i + 1) / 6.0); e = e * e * (3 - 2 * e)
        lu = (i + 1) / float(MEND7_POP); lift = 6.0 * lu * lu * (3 - 2 * lu)
        amp = max(0.0, (i - 4) / 4.0); jx, jy, jr = jit(i - MEND7_POP)
        return jx * amp, -lift + jy * amp, jr * amp, 0.15 + 0.85 * e, 1
    i -= MEND7_POP
    if i < MEND7_TREM:
        jx, jy, jr = jit(i)
        return jx, -(6.0 + 0.8 * math.sin(2 * math.pi * i / MEND7_TREM)) + jy, jr, 1.0, 2
    i -= MEND7_TREM
    if i < MEND7_FLY:
        e = MEND7_E[i] / 256.0
        return 0.0, -6.0 * (1 - e), 3.6 * e, 1.0, 3
    if i < MEND7_FLY + 2:
        return 0.0, 0.0, 3.6, (0.7, 0.4)[i - MEND7_FLY], 4
    return None


def mend7_rocks(stick=False):
    """Mend Walls (216) v7 slots 3 (grey rock) / 4 (brown stick) (2026-10-17 round 7, user: "only one debris at a time
    from any hex, they should ALL launch one after the other, and only one debris from each source hex"): ONE piece per
    sequence - the engine (patch_tc_mendwalls_v2.py v7) gives every piece its own source hex and launch time and moves
    the drawn point itself, so this art only has to draw the piece about its anchor: blank + 8 grow + 12 tremble (looped
    by the engine until the launch) + 15 post (5 flight, 2 sinking into the wall, blank).  The v5 look: hard 3-tone grey
    rock / brown stick with a twig, a dithered ground shadow while it hovers.  ALPHA 258, 48x56, anchor (24, 40)."""
    S = 4; W, H = MEND7_W, MEND7_H; rnd = random.Random(2270 + int(stick))
    pts = _mend3_poly(rnd, 5.8); L_ = 13.0
    rim, body, lit = (34, 33, 32), (112, 110, 106), (170, 168, 162)
    out = [Image.new("RGBA", (W, H), (0, 0, 0, 0))]
    n = 1 + MEND7_POP + MEND7_TREM + MEND7_POST
    for i in range(1, n):
        p = _mend7_pose(i)
        if p is None: out.append(Image.new("RGBA", (W, H), (0, 0, 0, 0))); continue
        dx, dy, rot, sc, ph = p; x, y = MEND7_AX + dx, MEND7_AY + dy
        big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); dr = ImageDraw.Draw(big)
        shade = Image.new("L", (W, H), 0)
        if ph in (1, 2):
            e = sc if ph == 1 else 1.0
            ImageDraw.Draw(shade).ellipse([MEND7_AX - 5.5 * e - 1, MEND7_AY + 5 - 1.4, MEND7_AX + 5.5 * e + 1, MEND7_AY + 5 + 1.7], fill=int(110 * e))
        if stick:
            _mend5_stick(dr, S, x, y, rot - 0.3, sc, L_)
        else:
            r0 = sum(rr for _a, rr in pts) / len(pts)

            def P(grow_, shx_=0.0, shy_=0.0, kk=1.0):
                return [((x + shx_ + math.cos(a + rot) * (rr * sc * kk + grow_)) * S, (y + shy_ + math.sin(a + rot) * (rr * sc * kk + grow_) * 0.9) * S) for a, rr in pts]
            dr.polygon(P(1.0), fill=rim + (255,)); dr.polygon(P(0.0), fill=body + (255,))
            dr.polygon(P(0.0, -0.3 * r0 * sc, -0.35 * r0 * sc, 0.5), fill=lit + (255,))
        a = np.array(big.resize((W, H), Image.BOX)); sp_ = np.array(shade)
        thr = np.tile(np.array(_MEND3_BAY, np.int32) * 16 + 8, (H // 4 + 1, W // 4 + 1))[:H, :W]
        solid = a[..., 3] >= 120; a[~solid] = 0; a[solid, 3] = 255
        sm = (~solid) & (sp_ > thr); a[sm] = (16, 14, 12, 255)
        out.append(Image.fromarray(a, "RGBA"))
    return out


def mend7_halo():
    """Mend Walls (216) v7 slot 5: the subtle green glow riding on each piece (same pose as mend7_rocks, ADDITIVE 770,
    48x56, anchor (24, 40)): a faint emerald halo fading in as the piece grows, swelling and flickering with the tremble
    (seamless 12-frame loop) with three tiny motes drifting up off it, held while it is flung; then the ARRIVAL = a small
    subtle green burst on the wall (a soft flash + six fine sparks spraying 5-10 px, as v6's wall-glow bursts)."""
    W, H = MEND7_W, MEND7_H; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2275)
    motes = [(rnd.uniform(-4, 4), rnd.uniform(0, 1)) for _ in range(3)]
    sparks = [(rnd.uniform(0, 6.28), rnd.uniform(5, 10), rnd.uniform(-0.25, 0.05)) for _ in range(6)]
    out = [Image.new("RGB", (W, H), (0, 0, 0)).convert("RGBA")]
    n = 1 + MEND7_POP + MEND7_TREM + MEND7_POST

    def g(acc, x, y, s, a): acc += a * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s))
    for i in range(1, n):
        acc = np.zeros((H, W), np.float32); burst = np.zeros((H, W), np.float32)
        p = _mend7_pose(i); k = i - 1
        if p is not None and p[4] != 4:
            dx, dy, rot, sc, ph = p; x, y = MEND7_AX + dx, MEND7_AY + dy
            if ph == 1: lv = 0.20 * (k + 1) / MEND7_POP
            elif ph == 2:
                q = k - MEND7_POP; lv = 0.20 * (0.9 + 0.1 * math.sin(2 * math.pi * 2 * q / MEND7_TREM))
            else: lv = 0.22
            g(acc, x, y, 5.0 * max(0.5, sc), lv); g(acc, x, y, 2.4 * max(0.5, sc), lv * 0.6)
            if ph == 2 or (ph == 1 and k >= 5):
                q = (k - MEND7_POP) % MEND7_TREM; amp = 1.0 if ph == 2 else (k - 4) / 4.0
                for mx, ph0 in motes:
                    v = (ph0 + q / float(MEND7_TREM)) % 1.0
                    g(acc, x + mx, y - 2 - v * 12, 0.9, math.sin(math.pi * v) * 0.3 * amp)
        d = k - MEND7_POP - MEND7_TREM - MEND7_FLY                # ticks since the arrival
        if 0 <= d < MEND7_POST - MEND7_FLY:
            x, y = MEND7_AX, MEND7_AY; f = min(1.0, (d + 1) / 2.0) * math.exp(-d / 3.5)
            g(burst, x, y, 2.0 + d * 0.25, f * 0.42)
            for a, r, vy in sparks:
                u = d / float(MEND7_POST - MEND7_FLY); e = 1 - (1 - u) ** 2
                g(burst, x + math.cos(a) * r * e, y + math.sin(a) * r * 0.7 * e + vy * d * 2.0, 0.65, (1 - u) ** 1.3 * 0.55)
        rgb = np.dstack([acc * 70 + burst * 150, acc * 235 + burst * 255, acc * 120 + burst * 175]).clip(0, 255).astype(np.uint8)
        out.append(Image.fromarray(rgb, "RGB").convert("RGBA"))
    return out


def mend7_hole():
    """Mend Walls (216) v7 slot 7: the torn ground at each piece's SOURCE hex (stationary, ALPHA 258, 48x56, anchor =
    the piece's rest point): the hole opens over 3 frames under a small grey pebble spurt as the piece grows out, stays
    open while it trembles (the tremble frames are identical - a seamless loop), then closes over 8 frames once the
    piece is flung; blank after."""
    S = 4; W, H = MEND7_W, MEND7_H; rnd = random.Random(2278)
    spurt = [(rnd.uniform(-1, 1), rnd.uniform(5, 9), _mend3_poly(rnd, 1.3, 5)) for _ in range(3)]
    gx, gy = MEND7_AX, MEND7_AY + 5
    thr = np.tile(np.array(_MEND3_BAY, np.int32) * 16 + 8, (H // 4 + 1, W // 4 + 1))[:H, :W]
    out = [Image.new("RGBA", (W, H), (0, 0, 0, 0))]
    n = 1 + MEND7_POP + MEND7_TREM + MEND7_POST
    for i in range(1, n):
        k = i - 1; big = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); dr = ImageDraw.Draw(big)
        hole = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(hole)
        if k < MEND7_POP + MEND7_TREM: o = min(1.0, (k + 1) / 3.0); a = 1.0
        else: o = 1.0; a = max(0.0, 1.0 - (k - MEND7_POP - MEND7_TREM + 1) / 8.0)
        if a > 0: hd.ellipse([gx - 5.0 * o, gy - 2.0 * o, gx + 5.0 * o, gy + 2.4 * o], fill=int(255 * a))
        if k < 8:
            u = k / 8.0
            for vx, vy, pp in spurt:
                _mend3_stamp(dr, S, pp, gx + vx * 6 * u, gy - vy * 4 * u * (1 - u) * 1.6, u * 6, 0.6 + 0.4 * min(1.0, u * 4), 0)
        arr = np.array(big.resize((W, H), Image.BOX)); hp = np.array(hole)
        solid = arr[..., 3] >= 120; arr[~solid] = 0; arr[solid, 3] = 255
        hm = (~solid) & (hp > thr) & (hp > 40); arr[hm] = (30, 26, 22, 255)
        out.append(Image.fromarray(arr, "RGBA"))
    return out


_MEND7_GLOW = []


def mend7_glow(t_end=72):
    """Mend Walls (216) v7 slot 1: the wall hex green circle thing UNCHANGED (mend6_glow's aura / rising band / ground
    ellipse / motes, same timing from the wall's first impact) MINUS the six baked arrival bursts - each piece now brings
    its own burst on its real impact point (mend7_halo).  The engine starts it at the wall's first impact (frame 1 =
    that tick; byte 3 of the marker), so: one blank frame + 51 frames, 96x112, anchor (48, 92), additive."""
    if _MEND7_GLOW: return _MEND7_GLOW
    W, H, AX, AY = 96, 112, 48, 92
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2180)
    _sparks4 = [[(rnd.uniform(0, 6.28), rnd.uniform(9, 16), rnd.uniform(-0.3, 0.1)) for _ in range(8)] for _ in range(6)]   # (v4's draws, kept so the motes match v4-v6)
    motes = [(rnd.uniform(-16, 16), rnd.uniform(0, 1), rnd.uniform(0.6, 1.0), rnd.uniform(0, 6.28)) for _ in range(16)]
    colx = np.exp(-((xx - AX) ** 2) / (2 * 13.0 ** 2)); coly = np.clip((AY + 6 - yy) / 8.0, 0, 1) * np.clip((yy - (AY - 66)) / 14.0, 0, 1)
    _MEND7_GLOW.append(Image.new("RGB", (W, H), (0, 0, 0)).convert("RGBA"))
    T0 = 21
    for ti in range(T0, t_end):
        t = float(ti); acc = np.zeros((H, W, 3), np.float32)

        def add(g, col):
            for c, cv in enumerate(col): acc[..., c] += g * cv
        ramp = min(1.0, max(0.0, (t - T0 + 1) / 18.0))
        fade = 1.0 if t < 52 else max(0.0, 1.0 - (t - 52) / 19.0)
        env = ramp * fade; env = env * env * (3 - 2 * env)
        add(colx * coly * (0.82 + 0.18 * np.sin(yy * 0.35 - t * 0.45 + xx * 0.12)) * 0.42 * env, (40, 210, 95))
        u = (t - 48) / 16.0
        if 0 <= u <= 1:
            by = AY + 4 - u * 70
            add(np.exp(-((yy - by) ** 2) / (2 * 1.6 ** 2)) * np.exp(-((xx - AX) ** 2) / (2 * 12.0 ** 2)) * math.sin(math.pi * u) * 0.7, (150, 255, 175))
        add(np.exp(-((xx - AX) ** 2) / (2 * 16.0 ** 2) - ((yy - AY - 2) ** 2) / (2 * 2.4 ** 2)) * 0.4 * env, (60, 230, 110))
        for x0, ph, sp, tw in motes:
            if t < 34: continue
            v = (ph + (t - 34) / 38.0 * sp * 1.3) % 1.0
            y = AY - 2 - v * 72; x = AX + x0 + 2.5 * math.sin(tw + v * 7.0)
            a = math.sin(math.pi * v) * (0.65 + 0.35 * math.sin(tw + t * 0.8)) * fade * min(1.0, (t - 34) / 4.0)
            add(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.3) * a, (190, 255, 205))
        _MEND7_GLOW.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return _MEND7_GLOW


def sea_rite_motes():
    """Rite of the Seas (221) slot 0 (2026-10-17): Earth Mastery's map-wide particle (20x20, additive, played
    [5300, 5301, 5302, 5303, 5302, 5301] like Depths of Plenty's glints): a small curling sea crest - a deep-blue
    swell arc whose white-cyan foam lip curls over and throws two spray flecks, with a silver four-point glint at the
    crest (the medal) that brightens as the wave breaks.  Distinct from Nimue's droplet/ripple and Black Tide's black
    drops."""
    frames = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32)
    for k, (h, curl, spray, gl) in enumerate(((0.55, 0.0, 0.0, 0.35), (0.8, 0.45, 0.25, 0.6), (1.0, 0.9, 0.7, 1.0), (0.85, 1.0, 1.0, 0.7))):
        cx, cy, R = 9.5, 15.5, 5.2 + 1.2 * h
        ang = np.arctan2(yy - cy, xx - cx); d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        arc = np.exp(-((d - R) / 1.15) ** 2) * ((ang < -0.15) & (ang > -np.pi + 0.25 - 0.9 * curl))   # the swell's back + crest
        body = np.exp(-((d - R + 1.6) / 1.4) ** 2) * ((ang < -0.4) & (ang > -np.pi + 0.5)) * 0.45
        lx, ly = cx + R * np.cos(-0.35 - 0.6 * curl), cy + R * np.sin(-0.35 - 0.6 * curl) + 1.6 * curl  # the foam lip
        lip = np.exp(-((xx - lx) ** 2 + (yy - ly) ** 2) / (1.1 + 0.6 * curl))
        fl = sum(np.exp(-((xx - (lx + dx * spray)) ** 2 + (yy - (ly - dy * spray)) ** 2) / 0.45) * spray
                 for dx, dy in ((3.2, 3.0), (1.0, 4.6)))
        gx, gy = cx - 0.5, cy - R - 0.2
        glint = (np.exp(-((yy - gy) ** 2) / 0.25) * np.clip(1 - np.abs(xx - gx) / 3.4, 0, 1)
                 + np.exp(-((xx - gx) ** 2) / 0.25) * np.clip(1 - np.abs(yy - gy) / 3.4, 0, 1)) * 0.7 * gl \
            + np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / 0.6) * gl
        blue = np.clip(arc + body, 0, 1) * (0.55 + 0.45 * h); white = np.clip(lip * (0.6 + 0.4 * curl) + fl, 0, 1)
        sil = np.clip(glint, 0, 1)
        r = 20 * blue + 200 * white + 225 * sil; g = 95 * blue + 235 * white + 230 * sil; b = 225 * blue + 255 * white + 240 * sil
        a = np.clip(blue + white + sil, 0, 1)
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255), 255 * (a > 0.05)]).astype(np.uint8), "RGBA"))
    return frames


def crashwave_spray():
    """Crashing Wave (220) slot 1 (2026-10-17, user: like Gust but blue water particles): the sprite of every kind-0x1F
    spray particle Gust v7's SPR throws along each breath strike (drawn through GFXE's intensity table, fading over the
    particle's path; played [5200, 5201, 5202, 5203]).  Vanilla Shockwave's own glow orbs (PARTICLE.ILB 0-2, as Gust's
    gust_shock) re-tinted to sea water - a deep-blue rim, a cyan-teal body and a white foam core - plus a 4th frame of
    torn spray: three small foam droplets round a cyan blob, so the stream reads as flung water, not light."""
    lib = ilbcodec.read(PARTICLE); out = []
    for src in (0, 1, 2):
        im, r = raw_pixels(lib, src); a = np.asarray(im.convert("RGB")).astype(np.float32)
        g = a.max(axis=2) / 255.0                                               # 0..1 glow strength
        core = np.clip((g - 0.62) / 0.38, 0, 1) ** 1.4                           # white foam only in the hottest centre
        body = np.dstack([25 * g, 125 * g, 255 * g])                             # sea blue / cyan
        body = body * (1 - core[..., None]) + np.dstack([235 * g, 250 * g, 255 * g]) * core[..., None]
        out.append(Image.fromarray(np.clip(body, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    W_, H_ = out[0].size
    yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32); cx, cy = (W_ - 1) / 2.0, (H_ - 1) / 2.0
    acc = np.zeros((H_, W_, 3), np.float32)
    def blob(x0, y0, r, col, k=1.0):
        g = np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * r * r)) * k
        for c in range(3): acc[..., c] += g * col[c]
    blob(cx, cy + 1, 3.2, (45, 150, 255), 0.95)                                  # cyan blob
    blob(cx, cy + 1, 1.4, (200, 240, 255), 0.7)
    for dx, dy, r in ((-4.5, -3.0, 1.1), (4.0, -4.0, 1.0), (5.0, 3.0, 0.9)):    # torn foam droplets
        blob(cx + dx, cy + dy, r, (225, 245, 255), 0.95)
    out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def flood_particles():
    """Flash Flood (223) slot 0 (2026-10-17): the three kind-0x1F flood particles (frame = particle address mod 3), drawn
    through GFXE's intensity table (additive; black = invisible), 56x24, centre (28, 12), flowing RIGHT:
      0 a breaking crest - a long low deep-blue swell whose top carries a foam line brightening towards the front,
        where it curls over into a bright cyan-white lip, with spindrift flecks thrown ahead;
      1 a rolling swell - a broader, lower swell with two foam streaks combed back along its back;
      2 spray - a spread of white-cyan droplets over a faint blue wash and a short foam streak."""
    W, H = 56, 24; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []

    def blob(cx, cy, rx, ry, a=1.0):
        return a * np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2))

    def line(y0, k, x0, x1, w, a, xc):
        yc = y0 + k * (xx - xc) ** 2
        ramp = np.clip((xx - x0) / max(1.0, x1 - x0), 0, 1) * (xx <= x1)
        return a * np.exp(-((yy - yc) / w) ** 2) * ramp

    def to_img(body, foam):
        body = np.clip(body, 0, 1); foam = np.clip(foam, 0, 1)
        r = 18 * body + 205 * foam; g = 66 * body + 228 * foam; b = 150 * body + 242 * foam
        return Image.fromarray(np.clip(np.dstack([r, g, b]), 0, 255).astype(np.uint8), "RGB").convert("RGBA")

    # 0 breaking crest
    body = blob(26, 15.5, 22, 5.5, 0.85) * np.clip(xx / 18.0, 0.25, 1) + blob(40, 12.5, 6, 4.5, 0.55)
    ang = np.arctan2(yy - 12.0, xx - 41.0); rad = np.hypot((xx - 41.0) / 1.3, yy - 12.0)
    lip = np.exp(-((rad - 4.6) / 1.1) ** 2) * np.clip(np.cos(ang + 1.6) * 1.5, 0, 1)
    foam = line(9.5, 0.006, 6, 40, 0.95, 0.85, 40) + lip + blob(48, 8.5, 1.5, 1.3, 0.9) + blob(51.5, 11.5, 1.1, 1.0, 0.75)         + blob(46, 5.5, 1.0, 0.9, 0.6)
    out.append(to_img(body, foam))
    # 1 rolling swell
    body = blob(28, 15.5, 24, 5.0, 0.7)
    foam = line(11.5, 0.004, 8, 44, 0.85, 0.75, 44) + line(14.0, 0.003, 14, 38, 0.75, 0.45, 38)
    out.append(to_img(body, foam))
    # 2 spray
    body = blob(26, 15, 16, 4.0, 0.35)
    foam = (blob(18, 13, 1.6, 1.3) + blob(24, 10, 1.3, 1.2, 0.95) + blob(30, 12, 1.5, 1.3, 0.9) + blob(36, 8.5, 1.0, 1.0, 0.8)
            + blob(27, 6.5, 0.9, 0.9, 0.7) + blob(41, 12, 0.9, 0.9, 0.7) + blob(45, 9, 0.8, 0.8, 0.6)
            + line(14.0, 0.0, 12, 30, 0.8, 0.7, 30))
    out.append(to_img(body, foam))
    return out


def sea_summon():
    """Summon Sea Serpent (222) slot 0: the Mermaid's summon glow (MAGIC.ILB 20-31, the rising column) tinted deep
    sea-teal with white foam at its brightest - the Phoenix / Earth-Death summon recipe, 12 frames."""
    lib = ilbcodec.read(MAGIC); out = []
    for src in range(20, 32):
        im, r = raw_pixels(lib, src); a = np.array(im.convert("RGBA")).astype(np.float32)
        lum = np.max(a[:, :, :3], axis=2); foam = np.clip((lum - 170.0) / 85.0, 0, 1)
        a[:, :, 0] = np.clip(lum * 0.30 + 200 * foam, 0, 255); a[:, :, 1] = np.clip(lum * 0.78 + 60 * foam, 0, 255)
        a[:, :, 2] = np.clip(lum * 1.00 + 20 * foam, 0, 255)
        out.append(Image.fromarray(a.astype(np.uint8), "RGBA"))
    return out


def walloflames_ignite(n=18):
    """Wall of Flames (226) slot 2 (2026-10-17): the per-hex landing (96x80, additive, 18 frames x 2 ticks, anchor
    -51/-40 = Sanctify's per-hex canvas, hex centre (48, 46)): a hot white-orange flash on the ground, a ring of
    fire licking outward over the hex, a column of flame tongues bursting up and collapsing, and embers rising
    out of it - the vanilla burning-hex fire (TCombatFire) takes over on the ring hexes as it fades."""
    W, H = 96, 80; cx, cy = 48.0, 46.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(2260)
    hexr = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.45) ** 2)
    tongues = [(rnd.uniform(-13, 13), rnd.uniform(0.6, 1.0), rnd.uniform(0, 6.28), rnd.uniform(2.4, 3.6)) for _ in range(9)]
    embers = [(rnd.uniform(-14, 14), rnd.uniform(-3, 3), rnd.uniform(0.15, 0.55), rnd.uniform(-6, 6)) for _ in range(16)]
    for i in range(n):
        t = i / (n - 1.0)
        acc = np.zeros((H, W), np.float32); hot = np.zeros((H, W), np.float32)
        flash = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.5) ** 2) / (12 + 140 * t)) * max(0.0, 1 - t / 0.35)
        hot += 1.3 * flash
        R = 3 + 22 * min(1.0, t / 0.55)
        ring = np.exp(-((hexr - R) / (1.6 + 2.2 * t)) ** 2) * (1 - t) ** 1.2 * 0.9
        acc += ring
        grow = min(1.0, t / 0.25); fall = max(0.0, (t - 0.45) / 0.55)
        for dx, hs, ph, wd in tongues:
            hgt = 34 * hs * grow * (1 - fall ** 1.4)
            if hgt < 1: continue
            x0 = cx + dx * (0.6 + 0.4 * t); sway = 2.2 * math.sin(ph + 9 * t)
            u = np.clip((cy - yy) / hgt, 0, 1); inside = (yy <= cy + 2) & (yy >= cy - hgt)
            half = wd * (1 - u) ** 0.8 + 0.3
            g = np.exp(-((xx - x0 - sway * u * u) / half) ** 2) * inside * (1 - u ** 3)
            acc += 0.75 * g; hot += 0.5 * g * (1 - u) ** 2
        for ex, ey, d0, drift in embers:
            u = (t - d0) / 0.45
            if 0 <= u <= 1:
                px = cx + ex + drift * u; py = cy + ey - 40 * u
                acc += np.exp(-((xx - px) ** 2 + (yy - py) ** 2) / 1.2) * math.sin(math.pi * u) * 0.9
        v = np.clip(acc, 0, 1.4); hv = np.clip(hot, 0, 1.2)
        r = 255 * np.clip(v * 1.0 + hv, 0, 1); g = 255 * np.clip(v * 0.48 + hv * 0.85, 0, 1); b = 255 * np.clip(v * 0.08 + hv * 0.55, 0, 1)
        out.append(Image.fromarray(np.dstack([r, g, b]).astype(np.uint8), "RGB").convert("RGBA"))
    return out


# ---- Smokescreen (225) art: functions destined for build_dual_sphere_fx_v1.py (they use its raw_pixels / GAME / ilbcodec)
SMOKE_ILB = os.path.join(GAME, "Images", "SMOKE.ILB")
_SMK_SRC = None


def _smoke_sources():
    """The vanilla smoke plume (SMOKE.ILB 61-70 = the raw-16 twins of the Cloud-of-Ashes plume 21-30, 254x126): per
    frame a DENSITY map (where the plume has pixels) and its LUMA, cropped to the plume - the material for the
    smokescreen billows (blurred so the dithered source fringe becomes a soft density)."""
    global _SMK_SRC
    if _SMK_SRC is None:
        lib = ilbcodec.read(SMOKE_ILB); _SMK_SRC = []
        for k in range(10):
            im, r = raw_pixels(lib, 61 + k)
            a = np.asarray(im).astype(np.float32)
            dens = (a[..., 3] > 0).astype(np.float32)
            luma = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]) / 255.0
            ys, xs = np.nonzero(dens)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            d = Image.fromarray((dens[y0:y1, x0:x1] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.2))
            l = Image.fromarray((luma[y0:y1, x0:x1] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
            _SMK_SRC.append((d, l))
    return _SMK_SRC


def _smoke_canvas(W, H, puffs, t, n, grow=1.0, alpha=1.0, rise=0.0):
    """Composite the billows for time t of an n-frame loop -> RGBA (ash-grey smoke, soft alpha - rec_for dithers it).
    puff = (cx, cy, size, k, ang0, orbit_r, phase, mirror); each billow plays the plume's own 10-frame billow once per
    loop (frame (3k + 10t/n) mod 10) while circling a small orbit -> seamless."""
    acc = np.zeros((H, W), np.float32); lum = np.zeros((H, W), np.float32)
    src = _smoke_sources()
    for cx, cy, size, k, ang0, orb, ph, mir in puffs:
        f = (k * 3 + (t * 10) // n) % 10
        d, l = src[f]
        w = max(4, int(size * grow)); h = max(3, int(size * grow * d.height / float(d.width)))
        dd, ll = d.resize((w, h), Image.LANCZOS), l.resize((w, h), Image.LANCZOS)
        if mir: dd, ll = dd.transpose(Image.FLIP_LEFT_RIGHT), ll.transpose(Image.FLIP_LEFT_RIGHT)
        a = 2 * math.pi * (t / float(n)) + ph
        x = cx + orb * math.cos(a) - w / 2.0; y = cy + 0.45 * orb * math.sin(a) - h / 2.0 - rise
        xi, yi = int(round(x)), int(round(y))
        D = np.asarray(dd).astype(np.float32) / 255.0; L = np.asarray(ll).astype(np.float32) / 255.0
        sx0, sy0 = max(0, -xi), max(0, -yi); sx1, sy1 = min(w, W - xi), min(h, H - yi)
        if sx1 <= sx0 or sy1 <= sy0: continue
        dst = (slice(yi + sy0, yi + sy1), slice(xi + sx0, xi + sx1)); s = (slice(sy0, sy1), slice(sx0, sx1))
        m = D[s] > acc[dst]
        lum[dst] = np.where(m, L[s], lum[dst]); acc[dst] = np.maximum(acc[dst], D[s])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = 150 + 70 * lum                                                     # ash grey: 150 (shade) .. 220 (lit billow)
    warm = np.clip((yy - H * 0.55) / (H * 0.45), 0, 1)                     # a faint ember warmth low down (Fire sphere)
    r = g + 14 * warm; gg = g + 4 * warm; b = g - 12 * warm
    al = np.clip((acc - 0.12) / 0.38, 0, 1); al = al * al * (3 - 2 * al) * alpha   # SOLID core, dithered only at the fringe
                                                                       # (translucency comes from drawMode 769, not the dither:
                                                                       #  a moving dither grid shimmers under DPI scaling)
    rgba = np.dstack([np.clip(r, 0, 255), np.clip(gg, 0, 255), np.clip(b, 0, 255), np.clip(al * 255, 0, 255)])
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


SMK_FW, SMK_FH, SMK_FCX, SMK_FCY, SMK_FN = 76, 54, 38, 36, 60


def _smoke_field_puffs():
    rnd = random.Random(2250); out = []
    for k in range(6):                                                     # a ring of churning billows filling the hex
        a = 2 * math.pi * k / 6 + rnd.uniform(-0.3, 0.3)
        out.append((SMK_FCX + 15 * math.cos(a), SMK_FCY + 6 * math.sin(a) - 3, rnd.uniform(32, 38), k, a,
                    rnd.uniform(2.5, 4.5), rnd.uniform(0, 6.28), k % 2 == 0))
    out.append((SMK_FCX, SMK_FCY - 6, 42, 7, 0.0, 2.0, 1.1, False))
    return out


def smoke_field():
    """Smokescreen (225) slot 3 (2026-10-17): the lingering smoke on each screened hex, drawn by
    patch_tc_smokescreen_v1.py's field HS (frame by tick, per-hex phase).  A SEAMLESS 60-frame loop (2 ticks each =
    ~3.5 s), 76x54, hex centre (38, 36): billows cut from the vanilla smoke plume (SMOKE.ILB 61-70) churning slowly in
    place on small orbits while their own billow animation plays; ash grey with a faint ember warmth at the ground,
    translucent (drawMode 769 = the plume's own blend mode) and dithered at the edges so neighbouring hexes merge into
    one bank."""
    puffs = _smoke_field_puffs(); out = []
    yy, xx = np.mgrid[0:SMK_FH, 0:SMK_FW].astype(np.float32)
    rn = np.sqrt(((xx - SMK_FCX) / 35.0) ** 2 + ((yy - (SMK_FCY - 5)) / 20.0) ** 2)
    env = np.clip((1.05 - rn) / 0.3, 0, 1)                               # solid bank, only the outer rim fades (dithered)
    for t in range(SMK_FN):
        im = _smoke_canvas(SMK_FW, SMK_FH, puffs, t, SMK_FN, alpha=1.0)
        a = np.asarray(im).copy(); a[..., 3] = (a[..., 3].astype(np.float32) * env).astype(np.uint8)
        out.append(Image.fromarray(a, "RGBA"))
    return out


SMK_PW, SMK_PH, SMK_PCX, SMK_PCY, SMK_PN = 80, 72, 40, 56, 20


def smoke_burst():
    """Smokescreen (225) slot 1 (2026-10-17): the cast on each hex (kind-0x26 effect at the hex centre, spawned by
    patch_tc_smokescreen_v1.py's gate; 20 frames x 2 ticks): a dense puff BURSTS up out of the ground with an ember
    flicker at its root, swells outward and rolls over, then settles and thins into the field haze."""
    puffs = _smoke_field_puffs(); out = []
    for i in range(SMK_PN):
        u = i / float(SMK_PN - 1)
        grow = 0.35 + 0.85 * (1 - (1 - u) ** 2.2)                          # quick swell, easing out
        rise = 10 * math.sin(math.pi * min(1.0, u * 1.4)) * (1 - u)         # lifts as it bursts, settles back
        al = min(1.0, 0.25 + u * 4.0) * (1.0 if u < 0.85 else 1.0 - (u - 0.85) / 0.15 * 0.6)   # solid; only the last frames thin (the field HS is already under it)
        pf = [(SMK_PCX + (cx - SMK_FCX) * (0.4 + 0.6 * u), SMK_PCY + (cy - SMK_FCY) * (0.4 + 0.6 * u), s, k, a0, o, ph, m)
              for cx, cy, s, k, a0, o, ph, m in puffs]
        im = _smoke_canvas(SMK_PW, SMK_PH, pf, i, SMK_PN, grow=grow, alpha=al, rise=rise)
        if u < 0.35:                                                        # ember flicker at the root
            dr = ImageDraw.Draw(im); e = 1 - u / 0.35; rr = 4 + 8 * u
            for j in range(9):
                ang = j * 0.7 + i; dx = math.cos(ang) * rr; dy = math.sin(ang) * rr * 0.4
                dr.ellipse([SMK_PCX + dx - 1.5, SMK_PCY + dy - 1, SMK_PCX + dx + 1.5, SMK_PCY + dy + 1],
                           fill=(255, int(120 + 80 * e), 40, int(230 * e)))
        out.append(im)
    return out


def pyro_ash_drift(n=3):
    """Pyroclasm (227) slots 0-2 (2026-10-17): three single frames for Air Mastery's map-wide drift (200x116, additive at
    low blend, as Ice Age's snow_drift): an EMBER-AND-ASH rain along a wide S-curve - glowing embers (hot yellow-white
    cores in orange-red halos, each with a short fading trail slanting down-left), cooler red sparks, pale ash flecks and
    a faint smoky red haze."""
    W, H = 200, 116; out = []; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for v in range(n):
        rnd = random.Random(5850 + v); ph = v * 2.1
        acc = np.zeros((H, W, 3), np.float32)
        for k in range(9):                                                   # faint smoky red haze
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph)
            g = 0.16 * np.exp(-((xx - x) ** 2 + ((yy - y) / 0.6) ** 2) / 320.0)
            for c, cv in enumerate((170, 60, 25)): acc[..., c] += g * cv
        for k in range(26):                                                  # embers with trails
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-22, 22)
            s = rnd.uniform(0.6, 1.1); L = rnd.uniform(4.0, 8.0)
            for j in range(6):                                               # the trail: up-right of the ember, fading
                f = j / 5.0; tx, ty = x + 0.7 * L * f, y - L * f
                g = np.exp(-((xx - tx) ** 2 + (yy - ty) ** 2) / (2 * (0.55 * s) ** 2)) * (1 - f) * 0.35
                for c, cv in enumerate((255, 110, 30)): acc[..., c] += g * cv
            core = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (0.6 * s) ** 2))
            halo = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * (1.6 * s) ** 2)) * 0.45
            for c, cv in enumerate((255, 235, 150)): acc[..., c] += core * cv * 0.95
            for c, cv in enumerate((255, 95, 20)): acc[..., c] += halo * cv
        for k in range(18):                                                  # cooler red sparks
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-26, 26)
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 0.9) * 0.8
            for c, cv in enumerate((220, 60, 20)): acc[..., c] += g * cv
        for k in range(22):                                                  # pale ash flecks
            t = rnd.random(); x = 10 + 180 * t; y = 58 + 28 * math.sin(t * 2 * math.pi * 1.1 + ph) + rnd.uniform(-26, 26)
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 0.6) * 0.35
            for c, cv in enumerate((150, 140, 130)): acc[..., c] += g * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def pyro_glow(n=48):
    """Pyroclasm (227) slot 3 (2026-10-17): the per-hex glow on every volcano anchor / lava hex Pyroclasm made - the
    Tectonic glow4 recipe in fire colours (32x40, anchor (-16, -31), 48 frames x 2 ticks = 2.8 s seamless loop,
    additive): a very soft round ember-red ground wash breathing once per loop under four small embers rising out of
    the hex, easing out and fading at their peak (yellow-white cores in orange halos).  Subtle by design (blend 65)."""
    W, H = 32, 40; cx, cy = 16.0, 30.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    wash = np.exp(-(((xx - cx) / 8.5) ** 2 + ((yy - cy) / 4.6) ** 2) * 1.6)
    #        x0     y0    rise  sway  sway-ph  sigma  phase
    motes = [(11.5, 32.5, 14.0, 0.9, 0.10, 0.85, 0.00),
             (20.0, 29.5, 12.5, 0.7, 0.55, 0.80, 0.25),
             (15.5, 34.0, 15.5, 1.0, 0.30, 0.90, 0.50),
             (21.5, 33.0, 12.0, 0.6, 0.80, 0.75, 0.75)]
    peak = (0.82 ** 1.6)
    frames = []
    for i in range(n):
        t = i / float(n); b = 0.5 + 0.5 * math.cos(2 * math.pi * t)
        a = wash * (0.09 + 0.03 * b); hot = np.zeros_like(a)
        for x0, y0, rise, sway, sph, sig, ph in motes:
            u = (t + ph) % 1.0
            y = y0 - rise * (1.0 - (1.0 - u) ** 2)
            x = x0 + sway * math.sin(2 * math.pi * (u + sph))
            br = min(1.0, u / 0.15) ** 1.5 * (1.0 - u) ** 1.7 / peak
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sig * sig)) * br * 0.85
            a = a + g; hot = hot + g * 0.7
        a = np.clip(a, 0, 1); hot = np.clip(hot, 0, 1)
        r = 215 * a + 40 * hot; g_ = 70 * a + 150 * hot; bl = 20 * a + 60 * hot
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g_, 0, 255), np.clip(bl, 0, 255),
                                                 255 * (a > 0.012)]).astype(np.uint8), "RGBA"))
    return frames


# ---- Smokescreen (225) v2 art (2026-10-17, user: "gfx looks meh - I wanted a variant of the CLOUD OF ASHES smoke"):
# built from the vanilla Cloud of Ashes image itself (Misc_Obj.ILB 40 'CloudofAshes.BMP', 195x155, drawMode 1026 =
# MULTIPLY on white) and drawn the vanilla way (1026: white = no change, grey = darken).  Like vanilla, ONE cloud
# covers the whole area: patch_tc_smokescreen_v1.py v2 draws slot 3 only from the CENTRE hex's smoke HS.
ASH_ILB = os.path.join(GAME, "Images", "Misc_Obj.ILB")
_ASH = None
SMK2_BW, SMK2_BH, SMK2_BCX, SMK2_BCY, SMK2_BN = 272, 208, 136, 104, 48     # bank canvas / hex-centre point / frames
SMK2_PW, SMK2_PH, SMK2_PCX, SMK2_PCY, SMK2_PN = 72, 72, 36, 52, 20         # burst canvas / hex-centre point / frames


def _ash():
    """(grain, envelope) from the vanilla Cloud of Ashes: grain = its darkness WITH the key-colour dither holes (the
    vanilla ash speckle), mirrored 2x2 into a seamless tile normalised to mean 1; envelope = its darkness with the
    holes filled (blur), 0..1 - the billowy outline."""
    global _ASH
    if _ASH is None:
        lib = ilbcodec.read(open(ASH_ILB, "rb").read())
        im, r = raw_pixels(lib, 40)
        a = np.asarray(im).astype(np.float32)
        dark = 1.0 - a[..., :3].mean(2) / 255.0
        cov = (a[..., 3] > 0).astype(np.float32)
        core = (dark * cov)[30:125, 35:160]
        core = core / core.mean()
        grain = np.vstack([np.hstack([core, core[:, ::-1]]), np.hstack([core[::-1, :], core[::-1, ::-1]])])
        bl = lambda x, s: np.asarray(Image.fromarray(np.clip(x * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(s))).astype(np.float32) / 255.0
        env = bl(dark * cov, 3.0) / np.maximum(bl(cov, 3.0), 0.08) * bl(cov, 2.0)
        _ASH = (grain, np.clip(env / env.max(), 0, 1))
    return _ASH


def _sample(tex, x, y):
    """Bilinear, wrapping sample of tex at float coordinate arrays."""
    H, W = tex.shape
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); fx = x - x0; fy = y - y0
    x0 %= W; y0 %= H; x1 = (x0 + 1) % W; y1 = (y0 + 1) % H
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy) + tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)


def _smk2_rgb(dens):
    """MULTIPLY image from a darkness density: m = exp(-dens), soot-grey tint (blue darkened a touch more than red)."""
    m = np.exp(-np.maximum(dens, 0))
    rgb = np.dstack([m ** 0.96, m, m ** 1.07]) * 255.0
    return Image.fromarray(np.dstack([rgb, np.full(m.shape, 255.0)]).clip(0, 255).astype(np.uint8), "RGBA")


def smoke_bank(n=SMK2_BN):
    """Smokescreen (225) slot 3 v2: the smoke bank over all 19 hexes - the Cloud of Ashes, scaled from its 7-hex size to
    the 2-ring area (x1.35), lighter than the vanilla ash (core multiply ~0.3, a smoke grey): its billowy outline
    breathes on a slow closed loop (a gentle low-frequency warp) while the ash speckle drifts across it in WHOLE-pixel
    steps (the grain moves as one sheet - no shimmering dither).  48 frames x 3 ticks (seamless, ~4.2 s); 1026
    multiply, 272x208, the centre hex at (136, 104)."""
    grain, env = _ash(); W, H, CX, CY = SMK2_BW, SMK2_BH, SMK2_BCX, SMK2_BCY
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    eh, ew = env.shape; sc = 1.35
    out = []
    for t in range(n):
        a = 2 * math.pi * t / n
        wx = 3.0 * np.sin(yy / 23.0 + a) + 2.0 * np.sin(xx / 31.0 - a)        # the outline breathes (closed loop)
        wy = 2.5 * np.sin(xx / 27.0 + a + 1.1) + 1.5 * np.sin(yy / 19.0 - a)
        ex = (xx - CX + wx) / sc + ew / 2.0; ey = (yy - CY + wy) / sc + eh / 2.0 + 4
        inside = (ex >= 0) & (ex < ew - 1) & (ey >= 0) & (ey < eh - 1)
        E = np.where(inside, _sample(env, np.clip(ex, 0, ew - 1.001), np.clip(ey, 0, eh - 1.001)), 0.0)
        ox, oy = int(round(10 * math.cos(a))), int(round(7 * math.sin(a)))  # whole-pixel grain drift
        G = _sample(grain, xx + 37 + ox, yy + 21 + oy)
        out.append(_smk2_rgb(1.25 * E ** 1.2 * (0.35 + 0.65 * G)))
    return out


def smoke_burst2(n=SMK2_PN):
    """Smokescreen (225) slot 1 v2: the cast on each hex (kind-0x26 effect at the hex centre, 20 frames x 2 ticks):
    a dark puff of the same ash speckle belches up out of the ground, swells and rises a little, then thins into the
    bank already lying over it.  1026 multiply, 72x72, hex centre (36, 52)."""
    grain, env = _ash(); W, H, CX, CY = SMK2_PW, SMK2_PH, SMK2_PCX, SMK2_PCY
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for i in range(n):
        u = i / float(n - 1)
        sig = 4 + 11 * (1 - (1 - u) ** 2.0)
        lift = 18 * (1 - (1 - u) ** 1.6)
        amp = min(1.0, u * 4.0) * (1.0 - max(0.0, (u - 0.35) / 0.65)) ** 1.3
        g = np.exp(-((xx - CX) ** 2 + ((yy - (CY - lift)) / 0.8) ** 2) / (2 * sig ** 2))
        G = _sample(grain, xx + 60, yy + 40 - i)                               # the speckle rising with the puff
        out.append(_smk2_rgb(1.6 * amp * g * (0.35 + 0.65 * G)))
    return out


PYRO_K = 8


def _pyro_levels(img, K=PYRO_K, gamma=1.2):
    """Pyroclasm (227) v3 fx: one particle image as K brightness levels (level k = (1 - k/K)^1.2, k = K-1 a faint
    ghost) - patch_pyroclasm_fx_v1.py picks the level per draw through Show's time argument (kind 4, f18 0)."""
    a = np.asarray(img.convert("RGB"), np.float32)
    return [Image.fromarray(np.clip(a * (1.0 - k / float(K)) ** gamma, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
            for k in range(K)]


def _pyro_blob(W, H, cx, cy, sx, sy, cols, core=0.0):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d2 = ((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2
    g = np.exp(-d2 * 1.6); c = np.exp(-d2 * 6.0) * core
    rgb = np.zeros((H, W, 3), np.float32)
    for k in range(3): rgb[..., k] = g * cols[0][k] + c * cols[1][k]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def pyro_particles():
    """Pyroclasm (227) v3 (2026-10-17, user: "pyroclasm gfx: add more particles, and add a shake"): the four particle
    types of 227's own map-wide callback, each a PYRO_K-level ladder (additive, black = invisible):
      slot 4 ember  (11x11, anchor -5/-5): a glowing orange ember with a yellow-white core;
      slot 5 ash    ( 9x9, anchor -4/-4): a pale, warm-grey ash fleck (kept dim - additive grey only lightens);
      slot 6 spark  (13x13, anchor -6/-6): a hot yellow-white lava spark with an orange halo;
      slot 7 haze   (72x44, anchor -36/-22): a big dim red-orange lava-light glow (pulsed by the callback)."""
    ember = _pyro_blob(11, 11, 5.0, 5.0, 4.0, 4.0, ((235, 110, 25), (255, 225, 140)), core=1.0)
    ash = _pyro_blob(9, 9, 4.0, 4.0, 3.0, 2.6, ((125, 112, 100), (50, 45, 40)), core=0.6)
    spark = _pyro_blob(13, 13, 6.0, 6.0, 4.4, 4.4, ((255, 120, 20), (255, 245, 190)), core=1.3)
    haze = _pyro_blob(72, 44, 36.0, 22.0, 30.0, 16.0, ((92, 30, 8), (40, 18, 4)), core=0.5)
    out = []
    for im in (ember, ash, spark, haze): out += _pyro_levels(im)
    return out


SMK3_IN = 20                                                                # v3 intro frames (x 3 ticks, ~1.8 s)


def _smk3_dens(t, n=SMK2_BN):
    """smoke_bank's darkness density of loop frame t (identical maths) - shared by the v3 intro."""
    grain, env = _ash(); W, H, CX, CY = SMK2_BW, SMK2_BH, SMK2_BCX, SMK2_BCY
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    eh, ew = env.shape; sc = 1.35
    a = 2 * math.pi * t / n
    wx = 3.0 * np.sin(yy / 23.0 + a) + 2.0 * np.sin(xx / 31.0 - a)
    wy = 2.5 * np.sin(xx / 27.0 + a + 1.1) + 1.5 * np.sin(yy / 19.0 - a)
    ex = (xx - CX + wx) / sc + ew / 2.0; ey = (yy - CY + wy) / sc + eh / 2.0 + 4
    inside = (ex >= 0) & (ex < ew - 1) & (ey >= 0) & (ey < eh - 1)
    E = np.where(inside, _sample(env, np.clip(ex, 0, ew - 1.001), np.clip(ey, 0, eh - 1.001)), 0.0)
    ox, oy = int(round(10 * math.cos(a))), int(round(7 * math.sin(a)))
    G = _sample(grain, xx + 37 + ox, yy + 21 + oy)
    return 1.25 * E ** 1.2 * (0.35 + 0.65 * G)


def smoke_bank_intro(n=SMK3_IN):
    """Smokescreen (225) slot 4 v3 (user: "a distinct hex-shaped gfx at the beginning looks janky" = the 19 per-hex
    cast puffs, which summed into a hard hexagon - they are gone): the bank GROWS IN instead.  Frame t = loop frame t's
    density under a round, wobbly mask that swells out from the centre hex (lobed radius, soft 30-px edge, the lobes
    turning so it billows rather than scales) and an overall density ramp; over the last quarter the mask relaxes to 1,
    so frame n-1 == loop frame n-1 and the patch's hand-over to slot 3 frame n is seamless.  1026 multiply, 272x208, the
    centre hex at (136, 104), drawn only by patch_tc_smokescreen_v1.py v3's frame picker (k < n -> this, else slot 3)."""
    W, H, CX, CY = SMK2_BW, SMK2_BH, SMK2_BCX, SMK2_BCY
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx, dy = xx - CX, (yy - CY) / 0.72
    r = np.sqrt(dx * dx + dy * dy); th = np.arctan2(dy, dx)
    out = []
    for t in range(n):
        u = (t + 1) / float(n)
        e = 1 - (1 - u) ** 2.2                                                  # ease-out growth
        R = 10 + 210 * e
        lobes = 1 + 0.16 * np.sin(3 * th + 1.3 + 2.0 * u) + 0.10 * np.sin(5 * th - 0.4 - 3.0 * u) + 0.06 * np.sin(8 * th + 2.0 + 4.0 * u)
        m = np.clip((R * lobes - r) / 30.0, 0, 1); m = m * m * (3 - 2 * m)     # soft, smoothstepped edge
        relax = min(1.0, max(0.0, (u - 0.75) / 0.25)) ** 2                     # -> 1 over the last quarter
        m = 1 - (1 - m) * (1 - relax)
        amp = min(1.0, 0.25 + 0.75 * u ** 0.7)
        out.append(_smk2_rgb(_smk3_dens(t) * m * amp))
    return out


def mmissile_head(n=8):
    """Magic Missile (228) slot 0: the flying bolt HEAD (class-6 projectile; TCPCK 0x42e5fc draws slot 0 looped at the
    current path point, frame = map frame counter + self>>2).  64x64, centre (32, 33) = vanilla BOLTS/TWINKGR anchor
    -32/-33; additive (770): a white-hot arcane core in a violet glow with four flickering star rays turning a little
    each frame (8-frame seamless loop)."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for k in range(n):
        a0 = k * (math.pi / 2) / n; fl = 0.85 + 0.15 * math.cos(2 * math.pi * k / n)
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        core = np.exp(-d2 / (2 * 2.2 ** 2)) * 1.25
        glow = np.exp(-d2 / (2 * 7.0 ** 2)) * 0.55 * fl
        rays = np.zeros_like(xx)
        for j in range(4):
            a = a0 + j * math.pi / 2; ux, uy = math.cos(a), math.sin(a)
            u = (xx - cx) * ux + (yy - cy) * uy; v = -(xx - cx) * uy + (yy - cy) * ux
            L = (11.0 if j % 2 == 0 else 7.5) * fl
            rays = np.maximum(rays, np.exp(-(v ** 2) / 0.9) * np.clip(1 - np.abs(u) / L, 0, 1) * 0.8)
        hot = np.clip(core + 0.6 * rays, 0, 1.4); v_ = np.clip(glow + rays * 0.5 + core, 0, 1.6)
        r = 150 * v_ + 110 * hot; g = 80 * v_ + 150 * hot; b = 255 * np.clip(v_, 0, 1) + 40 * hot
        a = np.clip(v_, 0, 1)
        out.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(g, 0, 255), np.clip(b, 0, 255), 255 * (a > 0.03)]).astype(np.uint8), "RGBA"))
    return out


def mmissile_trail(n=8):
    """Magic Missile (228) slot 1: the TRAIL (TCPCK 0x42e85c draws slot-1 frame j at path point pos-4+(7-j)/2: frame 0 =
    right behind the head, frame 7 = the oldest).  64x64, centre (32, 33); additive: a violet arcane puff shrinking and
    cooling to indigo with age, plus two drifting white sparks that wink out."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(2280)
    sp = [(rnd.uniform(-5, 5), rnd.uniform(-5, 5)) for _ in range(2)]
    for k in range(n):
        u = k / (n - 1.0); rad = 6.5 * (1 - 0.7 * u) + 1.0; br = (1 - u) ** 1.3
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        puff = np.exp(-d2 / (2 * rad ** 2)) * 0.75 * br
        acc = np.zeros((H, W, 3), np.float32)
        col = (170 * (1 - u) + 70 * u, 90 * (1 - u) + 40 * u, 255 * (1 - u) + 170 * u)
        for c in range(3): acc[..., c] += puff * col[c]
        for (sx, sy) in sp:
            x, y = cx + sx * (1 + u), cy + sy * (1 + u) - 2 * u
            s = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 0.8) * max(0.0, 1 - 1.4 * u)
            for c, cv in enumerate((255, 245, 255)): acc[..., c] += s * cv
        v = acc.max(axis=2) / 255.0
        out.append(Image.fromarray(np.dstack([np.clip(acc, 0, 255), 255 * (v > 0.03)]).astype(np.uint8), "RGBA"))
    return out


def royal_motes():
    """Royal Ambition (230) slot 0 (2026-10-17): Earth Mastery's map-wide particle (as Depths of Plenty's ore_glints,
    20x20, played [6150, 6151, 6152, 6153, 6152, 6151], additive): a regal golden FIVE-POINTED STAR glint - a warm
    white-gold core, star rays that grow and shrink as it twinkles, and a soft royal-gold halo."""
    frames = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32)
    dx, dy = xx - 9.5, yy - 9.5; r = np.sqrt(dx * dx + dy * dy); ang = np.arctan2(dy, dx)
    for g, rl in ((0.55, 3.2), (0.85, 5.2), (1.1, 6.8), (0.7, 4.2)):
        lobe = 0.38 + 0.62 * np.abs(np.cos(2.5 * (ang + np.pi / 2))) ** 3      # five sharp points, one pointing up
        star = np.clip(1.0 - r / (rl * lobe + 1e-3), 0, 1) * 0.85 * g
        core = np.exp(-r * r / (2 * 1.3 ** 2)) * g
        halo = np.exp(-r * r / (2 * 4.5 ** 2)) * 0.25 * g
        v = np.clip(np.maximum(np.maximum(core, star), halo), 0, 1); w = np.clip(core * 1.3 - 0.3, 0, 1)
        rgb = np.dstack([(225 + 30 * w) * v, (170 + 75 * w) * v, (40 + 150 * w) * v])
        frames.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * (v > 0.04)]).astype(np.uint8), "RGBA"))
    return frames


def cityspy_eye(n=12):
    """City Spy (229) slot 1 (2026-10-17; patch_cityspy_v1.py draws it ONLY for the spy's own player, above the
    enchanted city, frame = map tick / 4): 12 frames 40x28, ALPHA 258/80 - a small watchful cosmic eye: a violet
    almond outline that half-closes once per cycle, a glowing magenta iris with a dark pupil and a white glint, and
    three tiny stars twinkling around it.  Hard alpha (no dither), smooth per-frame changes."""
    frames = []; Wd, Hd = 40, 28; cx, cy = 20.0, 14.0
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    stars = [(5.0, 6.0, 0.0), (35.0, 8.0, 2.1), (31.0, 24.0, 4.2)]
    for i in range(n):
        t = i / float(n)
        lid = 0.62 + 0.38 * (0.5 + 0.5 * math.cos(2 * math.pi * t)) ** 0.5            # 1 = open, ~0.62 = half-closed (once per cycle)
        a = 12.0; b = 6.8 * lid
        u = (xx - cx) / a; v = (yy - cy) / max(b, 1e-3)
        inside = (np.abs(v) <= (1 - np.clip(np.abs(u), 0, 1) ** 2) ** 1.2) & (np.abs(u) <= 1)
        edge = np.abs(np.abs(v) - (1 - np.clip(np.abs(u), 0, 1) ** 2) ** 1.2) < 0.22
        outline = edge & (np.abs(u) <= 1.04)
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        iris = inside & (r <= 4.2); pupil = inside & (r <= 1.7)
        glint = ((xx - (cx - 1.6)) ** 2 + (yy - (cy - 1.8)) ** 2) <= 1.1
        glow = np.exp(-((xx - cx) ** 2 / (2 * 9.0 ** 2) + (yy - cy) ** 2 / (2 * 5.0 ** 2))) * 0.55
        R = np.zeros((Hd, Wd), np.float32); G = np.zeros_like(R); Bc = np.zeros_like(R); A = np.zeros_like(R)
        halo = (glow > 0.18) & ~inside
        R[halo], G[halo], Bc[halo], A[halo] = 90, 40, 150, 1
        R[inside], G[inside], Bc[inside], A[inside] = 225, 210, 245, 1
        R[iris], G[iris], Bc[iris] = 200, 60, 220
        R[pupil], G[pupil], Bc[pupil] = 30, 8, 50
        R[outline], G[outline], Bc[outline], A[outline] = 120, 50, 190, 1
        R[glint & inside], G[glint & inside], Bc[glint & inside] = 255, 255, 255
        for sx, sy, ph in stars:
            k = max(0.0, math.sin(2 * math.pi * t + ph)) ** 2
            if k < 0.15: continue
            st = ((np.abs(xx - sx) <= 0.6) & (np.abs(yy - sy) <= 1.6 * k + 0.4)) | ((np.abs(yy - sy) <= 0.6) & (np.abs(xx - sx) <= 1.6 * k + 0.4))
            R[st], G[st], Bc[st], A[st] = 230, 200, 255, 1
        frames.append(Image.fromarray(np.dstack([R, G, Bc, 255 * A]).astype(np.uint8), "RGBA"))
    return frames


def cityspy_cast(n=16):
    """City Spy (229) slot 0 (played by PlayDefaultCityEffects at the city on the cast): 16 frames 72x72, additive
    770 - a scrying swirl: violet motes spiral inward to a point, an eye-shaped flash opens there and fades."""
    frames = []; SZ = 72; cx, cy = 36.0, 40.0; rnd = random.Random(2290)
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32)
    motes = [(rnd.uniform(0, 6.283), rnd.uniform(0.7, 1.0), rnd.uniform(1.0, 1.6)) for _ in range(18)]
    for i in range(n):
        t = i / (n - 1.0); f = np.zeros((SZ, SZ), np.float32); w = np.zeros_like(f)
        rr = 30.0 * (1 - min(1.0, t / 0.6)) ** 1.2
        fade = 1.0 if t < 0.7 else max(0.0, 1 - (t - 0.7) / 0.3)
        for a0, s, sz in motes:
            ang = a0 + 5.0 * t; x = cx + rr * s * math.cos(ang); y = cy + 0.6 * rr * s * math.sin(ang)
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * 0.9 * fade; f += g; w += 0.4 * g
        if t >= 0.5:
            k = min(1.0, (t - 0.5) / 0.15) * fade
            eye = np.exp(-(((xx - cx) / 14.0) ** 2 + ((yy - cy) / (5.5 * k + 0.5)) ** 2) * 2.0) * k
            core = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / 6.0) * k
            f += 0.8 * eye + core; w += core + 0.3 * eye
        f = np.clip(f, 0, 1); w = np.clip(w, 0, 1)
        frames.append(Image.fromarray(np.dstack([(150 + 105 * w) * f, (60 + 170 * w) * f, 255 * f, 255 * (f > 0.03)]).astype(np.uint8), "RGBA"))
    return frames


def essence_swirl(n=28):
    """Essence Shift (231) slot 0 (2026-10-17): the cast effect at the target node (96x96, additive, 28 x 2 ticks).
    Six motes in the six elemental colours (Life gold-white, Death violet, Earth amber, Air pale cyan, Fire orange,
    Water blue) spiral inward around a faint cosmic halo, each trailing a soft streak, converge into a bright
    white-violet core (frame ~15), which bursts as a thin ring of starlight and fades; a few cosmic sparkles twinkle
    throughout.  Smooth: every element's position is continuous in t, no popping."""
    W = H = 96; cx, cy = 48.0, 52.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cols = ((255, 240, 190), (190, 120, 255), (235, 170, 80), (170, 235, 255), (255, 140, 50), (80, 150, 255))
    rnd = random.Random(2310); sparks = [(rnd.uniform(0, 6.283), rnd.uniform(10, 40), rnd.uniform(0, 1)) for _ in range(14)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        tc = min(1.0, t / 0.55)                                     # converge phase 0..1
        ring_r = 34 * (1 - tc) ** 1.3 + 2
        halo = math.sin(math.pi * min(1.0, t / 0.8)) * 0.35
        g = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.8) ** 2) / (2 * 18.0 ** 2)) * halo
        acc += g[..., None] * np.array((150, 110, 230), np.float32)
        if t < 0.6:
            for k, c in enumerate(cols):
                for tail in range(6):
                    tt = max(0.0, tc - tail * 0.025)
                    r = 34 * (1 - tt) ** 1.3 + 2
                    a = k * math.pi / 3 + 5.0 * tt
                    x = cx + r * math.cos(a); y = cy + 0.7 * r * math.sin(a)
                    s = (2.6 - tail * 0.3)
                    amp = (1.0 - tail / 6.0) * (0.9 if t < 0.52 else 0.9 * (0.6 - t) / 0.08)
                    gg = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s)) * max(0.0, amp)
                    acc += gg[..., None] * np.array(c, np.float32)
        core = math.exp(-((t - 0.55) / 0.09) ** 2)
        gc = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.85) ** 2) / (2 * 6.5 ** 2)) * core * 1.6
        acc += gc[..., None] * np.array((240, 225, 255), np.float32)
        if t > 0.5:
            u = (t - 0.5) / 0.5; rr = 4 + 40 * u ** 0.7
            d = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.7) ** 2)
            ring = np.exp(-((d - rr) / 2.2) ** 2) * (1 - u) ** 1.4 * 0.9
            acc += ring[..., None] * np.array((205, 190, 255), np.float32)
        for a0, r0, ph in sparks:
            tw = max(0.0, math.sin(2 * math.pi * (t * 1.5 + ph))) ** 3 * math.sin(math.pi * t)
            x = cx + r0 * math.cos(a0); y = cy + 0.7 * r0 * math.sin(a0)
            sp = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.2) * tw * 0.9
            acc += sp[..., None] * np.array((235, 225, 255), np.float32)
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


_CSPY_EYE2 = None


def _cityspy_eye2_frames():
    """City Spy (229) v2 slot 1 art (2026-10-18, user: the eye fades in, slowly looks left, holds, slowly looks right,
    holds, back to centre, fades out, pauses, repeats; visible for everyone): 15 UNIQUE 40x28 frames, ADDITIVE 770 (black
    = invisible, so the fade is a plain brightness ramp - no dither, no hard alpha edge):
      0 blank | 1..6 centre gaze at 1/6..6/6 brightness (6 = the full open eye) | 7..10 gaze LEFT 1..4 | 11..14 gaze
      RIGHT 1..4 (iris + pupil + glint slide 1.5 px per step, the lids stay put).
    A glowing violet almond (soft halo, pale lavender white, brighter rim), a magenta iris ring around a dark pupil
    (dark = the city shows through under additive) and a white glint.  The TIMELINE lives in the pipeline's slot list
    (patch_cityspy_v1.py v2 picks entry = real-time 0.1 s steps mod the list length)."""
    global _CSPY_EYE2
    if _CSPY_EYE2 is not None: return _CSPY_EYE2
    Wd, Hd = 40, 28; cx, cy = 20.0, 14.0; S = 4
    yy, xx = np.mgrid[0:Hd * S, 0:Wd * S].astype(np.float32); xx = (xx + 0.5) / S; yy = (yy + 0.5) / S

    def eye(gaze, level):
        a, b = 12.5, 6.6
        u = (xx - cx) / a; v = (yy - cy) / b
        lidf = np.clip(1 - np.clip(np.abs(u), 0, 1) ** 2, 0, 1) ** 1.15
        inside = (np.abs(v) <= lidf) & (np.abs(u) <= 1)
        rim = np.exp(-((np.abs(v) - lidf) * b) ** 2 / (2 * 0.55 ** 2)) * (np.abs(u) <= 1.06)
        gx = cx + 1.6 * gaze
        r = np.sqrt((xx - gx) ** 2 + (yy - cy) ** 2)
        iris = np.clip(4.6 - r, 0, 1) * inside
        pupil = np.clip(2.1 - r, 0, 1) * inside
        ring = np.exp(-(r - 3.9) ** 2 / (2 * 0.6 ** 2)) * inside
        glint = np.clip(1.0 - np.sqrt((xx - (gx - 1.5)) ** 2 + (yy - (cy - 1.6)) ** 2), 0, 1) * inside
        halo = np.exp(-((xx - cx) ** 2 / (2 * 10.0 ** 2) + (yy - cy) ** 2 / (2 * 5.5 ** 2)))
        R = 45 * halo + 55 * inside + 120 * rim
        G = 15 * halo + 40 * inside + 40 * rim
        B = 80 * halo + 95 * inside + 200 * rim
        # iris: magenta, brighter ring; pupil: dark; glint: white
        R = R * (1 - iris) + iris * (150 + 80 * ring); G = G * (1 - iris) + iris * (20 + 40 * ring); B = B * (1 - iris) + iris * (170 + 60 * ring)
        R *= (1 - 0.92 * pupil); G *= (1 - 0.92 * pupil); B *= (1 - 0.92 * pupil)
        R = R * (1 - glint) + 255 * glint; G = G * (1 - glint) + 255 * glint; B = B * (1 - glint) + 255 * glint
        k = (level / 6.0) ** 1.4
        rgb = np.dstack([R, G, B]) * k
        img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").resize((Wd, Hd), Image.BOX)
        return img.convert("RGBA")

    frames = [Image.new("RGBA", (Wd, Hd), (0, 0, 0, 255))]
    frames += [eye(0, L) for L in range(1, 7)]
    frames += [eye(-p, 6) for p in range(1, 5)]
    frames += [eye(p, 6) for p in range(1, 5)]
    _CSPY_EYE2 = frames
    return frames


def cityspy_eye2_a():
    """City Spy (229) v2 eye frames 0..11 -> DualDF 6100..6111 (see _cityspy_eye2_frames)."""
    return _cityspy_eye2_frames()[:12]


def cityspy_eye2_b():
    """City Spy (229) v2 eye frames 12..14 (gaze right 2..4) -> DualDF 6128..6130 (6112..6127 = the cast swirl)."""
    return _cityspy_eye2_frames()[12:]


# ---- City Spy v3 eye (2026-10-18): v1 look (opaque almond, white sclera, magenta iris, violet outline + halo, three
# static star glints) drawn ALPHA 258 like v1; the fade uses the SAME image at stepped blendValue (258 = colour-key
# alpha, blendValue = opacity %: v1 = 80).  Gaze = iris/pupil/glint slide, supersampled 4x so 0.25 px steps glide.
CSPY3_N_GAZE = 33                 # gaze -4.0 .. +4.0 px in 0.25 px steps (index 16 = centre)
CSPY3_FADE = [8, 16, 24, 32, 40, 48, 56, 64, 72]   # fade blend levels (the open eye itself = 80, v1's value)
CSPY3_FULL = 80
_CSPY3 = None


def _cspy3_eye(gaze):
    Wd, Hd, S = 40, 28, 4; cx, cy = 20.0, 14.0
    # alpha mask from v1's exact (non-supersampled) shapes so the outline stays crisp and IDENTICAL for every gaze
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    a, b = 12.0, 6.8
    u = (xx - cx) / a; v = (yy - cy) / b
    lid = (1 - np.clip(np.abs(u), 0, 1) ** 2) ** 1.2
    inside = (np.abs(v) <= lid) & (np.abs(u) <= 1)
    outline = (np.abs(np.abs(v) - lid) < 0.22) & (np.abs(u) <= 1.04)
    glow = np.exp(-((xx - cx) ** 2 / (2 * 9.0 ** 2) + (yy - cy) ** 2 / (2 * 5.0 ** 2))) * 0.55
    halo = (glow > 0.18) & ~inside & ~outline
    stars = [(5.0, 6.0), (35.0, 8.0), (31.0, 24.0)]
    st = np.zeros_like(inside)
    for sx, sy in stars:
        st |= ((np.abs(xx - sx) <= 0.6) & (np.abs(yy - sy) <= 1.4)) | ((np.abs(yy - sy) <= 0.6) & (np.abs(xx - sx) <= 1.4))
    # interior colours supersampled (iris slides smoothly)
    Y, X = np.mgrid[0:Hd * S, 0:Wd * S].astype(np.float32); X = (X + 0.5) / S; Y = (Y + 0.5) / S
    gx = cx + gaze
    r = np.sqrt((X - gx) ** 2 + (Y - cy) ** 2)
    iris = np.clip(4.2 - r + 0.5, 0, 1); pupil = np.clip(1.7 - r + 0.5, 0, 1)
    gl = np.clip(1.6 - np.sqrt((X - (gx - 1.6)) ** 2 + (Y - (cy - 1.8)) ** 2) * 1.5, 0, 1)
    R = 225 * (1 - iris) + 200 * iris; G = 210 * (1 - iris) + 60 * iris; B = 245 * (1 - iris) + 220 * iris
    R = R * (1 - pupil) + 30 * pupil; G = G * (1 - pupil) + 8 * pupil; B = B * (1 - pupil) + 50 * pupil
    R = R * (1 - gl) + 255 * gl; G = G * (1 - gl) + 255 * gl; B = B * (1 - gl) + 255 * gl
    rgb = Image.fromarray(np.dstack([R, G, B]).clip(0, 255).astype(np.uint8), "RGB").resize((Wd, Hd), Image.BOX)
    arr = np.asarray(rgb).astype(np.float32)
    out = np.zeros((Hd, Wd, 4), np.float32)
    out[..., :3][halo] = (90, 40, 150); out[..., 3][halo] = 255
    out[..., :3][inside] = arr[inside]; out[..., 3][inside] = 255
    out[..., :3][outline] = (120, 50, 190); out[..., 3][outline] = 255
    out[..., :3][st] = (230, 200, 255); out[..., 3][st] = 255
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def _cspy3_frames():
    global _CSPY3
    if _CSPY3 is None:
        _CSPY3 = [_cspy3_eye(-4.0 + 0.25 * k) for k in range(CSPY3_N_GAZE)]
    return _CSPY3


def cityspy_eye3_blank():
    """City Spy (229) v3: one invisible frame (all colour key) for the hidden pause."""
    return [Image.new("RGBA", (40, 28), (0, 0, 0, 0))]


def cityspy_eye3_gaze():
    """City Spy (229) v3: 33 open-eye frames, gaze -4..+4 px in 0.25 px steps (index 16 = centre), ALPHA 258 / 80."""
    return list(_cspy3_frames())


def cityspy_eye3_centre():
    """City Spy (229) v3: the centre-gaze eye alone (one fade row per blend level)."""
    return [_cspy3_frames()[16]]


def _ease(t):
    return t * t * (3 - 2 * t)


def cityspy_eye3_timeline(base):
    """City Spy (229) v3 slot-1 list for patch_cityspy_v1.py v3 (35 ms per entry = real time mod len):
    fade in 0.32 s / hold 0.39 / look left 0.6 / hold 0.6 / sweep right 0.8 / hold 0.6 / back to centre 0.5 / hold 0.32 /
    fade out 0.32 / hidden 2.0 s  ->  183 entries = 6.4 s.  base = first DualDF id: +0 blank, +1..+33 gaze, +34..+42 fade."""
    BL, G0, F0 = base, base + 1, base + 34
    def gz(px): return G0 + int(round((px + 4.0) / 0.25))
    seq = []
    seq += [F0 + k for k in range(9)]                                   # fade in (8..72 %)
    seq += [gz(0)] * 11
    seq += [gz(-4.0 * _ease((i + 1) / 17)) for i in range(17)]           # look left
    seq += [gz(-4.0)] * 17
    seq += [gz(-4.0 + 8.0 * _ease((i + 1) / 23)) for i in range(23)]      # sweep right
    seq += [gz(4.0)] * 17
    seq += [gz(4.0 - 4.0 * _ease((i + 1) / 14)) for i in range(14)]      # back to centre
    seq += [gz(0)] * 9
    seq += [F0 + 8 - k for k in range(9)]                               # fade out (72..8 %)
    seq += [BL] * 57                                                    # 2 s hidden
    return seq


def essence_swirl2(n=44):
    """Essence Shift (231) slot 0 v3 (2026-10-18, user: "really good but needs a smooth fade out, it ends abruptly").
    essence_swirl's first 28 frames unchanged in look and speed (t = i / 27: six elemental motes spiral in, the
    white-violet core flashes at t 0.55, the starlight ring bursts), then 16 more frames of tail: the ring keeps
    EXPANDING while it fades on a smoothstep (no retract), the cosmic halo and a soft afterglow ease out, the sparkles
    dim with them; every term reaches exactly 0 with zero slope at the last frame (96x96, additive, 44 x 2 ticks)."""
    def sst(a, b, x):
        u = min(1.0, max(0.0, (x - a) / (b - a))); return u * u * (3 - 2 * u)
    W = H = 96; cx, cy = 48.0, 52.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cols = ((255, 240, 190), (190, 120, 255), (235, 170, 80), (170, 235, 255), (255, 140, 50), (80, 150, 255))
    rnd = random.Random(2310); sparks = [(rnd.uniform(0, 6.283), rnd.uniform(10, 40), rnd.uniform(0, 1)) for _ in range(14)]
    T_END = (n - 1) / 27.0
    out = []
    for i in range(n):
        t = i / 27.0; acc = np.zeros((H, W, 3), np.float32)
        tc = min(1.0, t / 0.55)
        halo = 0.35 * (math.sin(math.pi * min(1.0, t / 0.8)) if t < 0.4 else 1.0 - sst(0.4, T_END, t))
        g = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.8) ** 2) / (2 * 18.0 ** 2)) * halo
        acc += g[..., None] * np.array((150, 110, 230), np.float32)
        if t < 0.6:
            for k, c in enumerate(cols):
                for tail in range(6):
                    tt = max(0.0, tc - tail * 0.025)
                    r = 34 * (1 - tt) ** 1.3 + 2
                    a = k * math.pi / 3 + 5.0 * tt
                    x = cx + r * math.cos(a); y = cy + 0.7 * r * math.sin(a)
                    s = (2.6 - tail * 0.3)
                    amp = (1.0 - tail / 6.0) * (0.9 if t < 0.52 else 0.9 * (0.6 - t) / 0.08)
                    gg = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s * s)) * max(0.0, amp)
                    acc += gg[..., None] * np.array(c, np.float32)
        core = math.exp(-((t - 0.55) / 0.09) ** 2)
        gc = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.85) ** 2) / (2 * 6.5 ** 2)) * core * 1.6
        acc += gc[..., None] * np.array((240, 225, 255), np.float32)
        glow = sst(0.5, 0.65, t) * (1.0 - sst(0.65, T_END, t)) * 0.45                 # soft afterglow easing out
        gg2 = np.exp(-((xx - cx) ** 2 + ((yy - cy) / 0.85) ** 2) / (2 * 11.0 ** 2)) * glow
        acc += gg2[..., None] * np.array((200, 180, 255), np.float32)
        if t > 0.5:
            u = (t - 0.5) / (T_END - 0.5); rr = 4 + 40 * u ** 0.7                       # keeps expanding to the end (stays inside the 96 px canvas)
            d = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.7) ** 2)
            ring = np.exp(-((d - rr) / 2.2) ** 2) * (1 - u) ** 1.2 * (1.0 - sst(0.45, 1.0, u)) * 0.9
            acc += ring[..., None] * np.array((205, 190, 255), np.float32)
        fs = math.sin(math.pi * min(t, 0.5)) * (1.0 - sst(0.7, T_END, t))
        for a0, r0, ph in sparks:
            tw = max(0.0, math.sin(2 * math.pi * (t * 1.5 + ph))) ** 3 * fs
            x = cx + r0 * math.cos(a0); y = cy + 0.7 * r0 * math.sin(a0)
            sp = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.2) * tw * 0.9
            acc += sp[..., None] * np.array((235, 225, 255), np.float32)
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


# ---- City Spy v4 eye (2026-10-18; user: fade in/out slower + smoother, more translucent/subtle, iris becomes an OVAL
# toward the sides so it reads 3D).  Same v1-look almond, drawn ALPHA 258 like v3 but the open eye at blendValue 52
# (v3: 80) with a softer, dimmer halo/outline; the fades use 20 rows of the centre eye at blend 2.6 .. 52 (v3: 9 rows,
# 0.32 s) eased over 0.9 s each.  Gaze = a sphere model: the iris/pupil are discs on a 5.4 px eyeball, so at gaze g
# the angle th = asin(g / 5.4) and the iris is foreshortened horizontally by cos(th) (oval at the sides), the
# highlight drifts with it.  Supersampled 4x; the almond outline is IDENTICAL for every frame (no edge flicker).
CSPY4_N_GAZE = 33                 # gaze -4.0 .. +4.0 px in 0.25 px steps (index 16 = centre)
CSPY4_FULL = 52                   # open-eye opacity (blendValue %, mode 258)
CSPY4_NFADE = 20                  # fade rows: blend = FULL * k / 20, k = 1..20 (row 20 == the open eye's own value)
CSPY4_BALL = 5.4                  # eyeball radius (px) for the foreshortening
_CSPY4 = None


def _cspy4_eye(gaze):
    Wd, Hd, S = 40, 28, 4; cx, cy = 20.0, 14.0
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    a, b = 12.0, 6.8
    u = (xx - cx) / a; v = (yy - cy) / b
    lid = (1 - np.clip(np.abs(u), 0, 1) ** 2) ** 1.2
    inside = (np.abs(v) <= lid) & (np.abs(u) <= 1)
    outline = (np.abs(np.abs(v) - lid) < 0.22) & (np.abs(u) <= 1.04)
    glow = np.exp(-((xx - cx) ** 2 / (2 * 9.0 ** 2) + (yy - cy) ** 2 / (2 * 5.0 ** 2))) * 0.55
    halo = (glow > 0.22) & ~inside & ~outline                        # a touch tighter than v3 (0.18): subtler
    stars = [(5.0, 6.0), (35.0, 8.0), (31.0, 24.0)]
    st = np.zeros_like(inside)
    for sx, sy in stars:
        st |= ((np.abs(xx - sx) <= 0.6) & (np.abs(yy - sy) <= 1.4)) | ((np.abs(yy - sy) <= 0.6) & (np.abs(xx - sx) <= 1.4))
    Y, X = np.mgrid[0:Hd * S, 0:Wd * S].astype(np.float32); X = (X + 0.5) / S; Y = (Y + 0.5) / S
    th = math.asin(max(-0.98, min(0.98, gaze / CSPY4_BALL))); c = math.cos(th)
    gx = cx + gaze
    ri, rp = 4.2, 1.7
    re = np.sqrt(((X - gx) / c) ** 2 + (Y - cy) ** 2)                 # elliptical distance: horizontally squashed by cos(th)
    iris = np.clip(ri - re + 0.5, 0, 1); pupil = np.clip(rp - re + 0.5, 0, 1)
    hx = gx - 1.6 * c + 0.6 * math.sin(th); hy = cy - 1.8              # highlight rides the curved surface
    gl = np.clip(1.6 - np.sqrt(((X - hx) / max(c, 0.55)) ** 2 + (Y - hy) ** 2) * 1.5, 0, 1)
    rim = np.clip(1.0 - np.abs(re - ri) * 1.6, 0, 1) * 0.35           # a soft darker limbal ring sells the roundness
    R = 225 * (1 - iris) + 200 * iris; G = 210 * (1 - iris) + 60 * iris; B = 245 * (1 - iris) + 220 * iris
    R = R * (1 - rim) + 110 * rim; G = G * (1 - rim) + 30 * rim; B = B * (1 - rim) + 150 * rim
    R = R * (1 - pupil) + 30 * pupil; G = G * (1 - pupil) + 8 * pupil; B = B * (1 - pupil) + 50 * pupil
    R = R * (1 - gl) + 255 * gl; G = G * (1 - gl) + 255 * gl; B = B * (1 - gl) + 255 * gl
    rgb = Image.fromarray(np.dstack([R, G, B]).clip(0, 255).astype(np.uint8), "RGB").resize((Wd, Hd), Image.BOX)
    arr = np.asarray(rgb).astype(np.float32)
    out = np.zeros((Hd, Wd, 4), np.float32)
    out[..., :3][halo] = (70, 34, 120); out[..., 3][halo] = 255      # dimmer halo than v3 (90, 40, 150)
    out[..., :3][inside] = arr[inside]; out[..., 3][inside] = 255
    out[..., :3][outline] = (110, 50, 175); out[..., 3][outline] = 255
    out[..., :3][st] = (215, 190, 245); out[..., 3][st] = 255
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def _cspy4_frames():
    global _CSPY4
    if _CSPY4 is None:
        _CSPY4 = [_cspy4_eye(-4.0 + 0.25 * k) for k in range(CSPY4_N_GAZE)]
    return _CSPY4


def cityspy_eye4_blank():
    """City Spy (229) v4: one invisible frame (all colour key) for the hidden pause."""
    return [Image.new("RGBA", (40, 28), (0, 0, 0, 0))]


def cityspy_eye4_gaze():
    """City Spy (229) v4: 33 open-eye frames, gaze -4..+4 px in 0.25 px steps (index 16 = centre), oval iris at the sides."""
    return list(_cspy4_frames())


def cityspy_eye4_centre():
    """City Spy (229) v4: the centre-gaze eye alone (one fade row per blend level)."""
    return [_cspy4_frames()[16]]


def _ease4(t):
    return t * t * (3 - 2 * t)


def cityspy_eye4_timeline(base):
    """City Spy (229) v4 slot-1 list for patch_cityspy_v1.py v3 (35 ms per entry = real time mod len; no engine change):
    fade in 0.91 s (26 entries over 20 eased levels) / hold 0.39 / look left 0.6 / hold 0.6 / sweep right 0.8 /
    hold 0.6 / back to centre 0.5 / hold 0.32 / fade out 0.91 / hidden 2.0 s -> 217 entries = 7.6 s.
    base = first DualDF id: +0 blank, +1..+33 gaze, +34..+53 fade rows 1..20 (row 20 = blend 52 = the open eye)."""
    BL, G0, F0 = base, base + 1, base + 34
    def gz(px): return G0 + int(round((px + 4.0) / 0.25))
    def fd(t): return F0 + max(0, min(CSPY4_NFADE - 1, int(round(_ease4(t) * CSPY4_NFADE)) - 1))
    NF = 26
    seq = []
    seq += [fd((i + 1) / NF) for i in range(NF)]                        # fade in (eased, 20 levels)
    seq += [gz(0)] * 11
    seq += [gz(-4.0 * _ease4((i + 1) / 17)) for i in range(17)]         # look left
    seq += [gz(-4.0)] * 17
    seq += [gz(-4.0 + 8.0 * _ease4((i + 1) / 23)) for i in range(23)]    # sweep right
    seq += [gz(4.0)] * 17
    seq += [gz(4.0 - 4.0 * _ease4((i + 1) / 14)) for i in range(14)]    # back to centre
    seq += [gz(0)] * 9
    seq += [fd(1 - (i + 1) / NF) if i < NF - 1 else BL for i in range(NF)]   # fade out (eased) -> blank
    seq += [BL] * 57                                                   # 2 s hidden
    return seq


# ---- City Spy v5 eye (2026-10-18; user: "make the fade in/out the eye OPENING / CLOSING").  The v4 eye (sphere iris,
# alpha 258 @ blend 52) unchanged while open; the fades are replaced by EYELIDS: the closed eye is a thin curved lid
# line (lids meet a little below centre), it fades in faintly (3 blend rows of the closed frame), the lids part over
# CSPY5_NOPEN aperture frames (eased; upper lid rises, lower lid drops, the iris is revealed through the slit, the halo
# and the star glints grow with the aperture), then the v4 look-around; at the end the lids close the same way and the
# lid line fades out.  The fully open aperture frame is pixel-identical to the v4 centre-gaze frame (asserted).
CSPY5_NOPEN = 16                  # aperture frames o = k / 15, k = 0..15 (k = 15 == the v4 centre eye)
CSPY5_LINE = (13, 26, 39)         # faint lid-line rows (blendValue %) before the lids part / after they close


def _cspy5_eye(o):
    Wd, Hd, S = 40, 28, 4; cx, cy = 20.0, 14.0
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    a, b = 12.0, 6.8
    u = (xx - cx) / a; v = (yy - cy) / b
    lid = (1 - np.clip(np.abs(u), 0, 1) ** 2) ** 1.2
    if o >= 1.0:
        inside = (np.abs(v) <= lid) & (np.abs(u) <= 1)
        outline = (np.abs(np.abs(v) - lid) < 0.22) & (np.abs(u) <= 1.04)
    else:
        mid = 0.2 * lid * (1 - o)                                    # where the lids meet (a touch below centre)
        vu, vl = -lid * o + mid, lid * o + mid                         # upper / lower lid edge
        inside = (v >= vu) & (v <= vl) & (np.abs(u) <= 1)
        tol = 0.11 + 0.11 * o                                          # thin lid line when (nearly) closed
        outline = ((np.abs(v - vu) < tol) | (np.abs(v - vl) < tol)) & (np.abs(u) <= 1.04) & (lid > 0.02)
    glow = np.exp(-((xx - cx) ** 2 / (2 * 9.0 ** 2) + (yy - cy) ** 2 / (2 * 5.0 ** 2))) * 0.55
    halo = (glow > 0.22 + 0.33 * (1 - o)) & ~inside & ~outline if o > 0.15 else np.zeros_like(inside)
    stars = [(5.0, 6.0), (35.0, 8.0), (31.0, 24.0)]
    st = np.zeros_like(inside)
    if o >= 0.6:
        for sx, sy in stars:
            st |= ((np.abs(xx - sx) <= 0.6) & (np.abs(yy - sy) <= 1.4)) | ((np.abs(yy - sy) <= 0.6) & (np.abs(xx - sx) <= 1.4))
    Y, X = np.mgrid[0:Hd * S, 0:Wd * S].astype(np.float32); X = (X + 0.5) / S; Y = (Y + 0.5) / S
    gx = cx; c = 1.0; th = 0.0
    ri, rp = 4.2, 1.7
    re = np.sqrt(((X - gx) / c) ** 2 + (Y - cy) ** 2)
    iris = np.clip(ri - re + 0.5, 0, 1); pupil = np.clip(rp - re + 0.5, 0, 1)
    hx = gx - 1.6 * c + 0.6 * math.sin(th); hy = cy - 1.8
    gl = np.clip(1.6 - np.sqrt(((X - hx) / max(c, 0.55)) ** 2 + (Y - hy) ** 2) * 1.5, 0, 1)
    rim = np.clip(1.0 - np.abs(re - ri) * 1.6, 0, 1) * 0.35
    R = 225 * (1 - iris) + 200 * iris; G = 210 * (1 - iris) + 60 * iris; B = 245 * (1 - iris) + 220 * iris
    R = R * (1 - rim) + 110 * rim; G = G * (1 - rim) + 30 * rim; B = B * (1 - rim) + 150 * rim
    R = R * (1 - pupil) + 30 * pupil; G = G * (1 - pupil) + 8 * pupil; B = B * (1 - pupil) + 50 * pupil
    R = R * (1 - gl) + 255 * gl; G = G * (1 - gl) + 255 * gl; B = B * (1 - gl) + 255 * gl
    rgb = Image.fromarray(np.dstack([R, G, B]).clip(0, 255).astype(np.uint8), "RGB").resize((Wd, Hd), Image.BOX)
    arr = np.asarray(rgb).astype(np.float32)
    out = np.zeros((Hd, Wd, 4), np.float32)
    out[..., :3][halo] = (70, 34, 120); out[..., 3][halo] = 255
    out[..., :3][inside] = arr[inside]; out[..., 3][inside] = 255
    out[..., :3][outline] = (110, 50, 175); out[..., 3][outline] = 255
    out[..., :3][st] = (215, 190, 245); out[..., 3][st] = 255
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def cityspy_eye5_open():
    """City Spy (229) v5: 16 aperture frames, closed lid line (k = 0) .. fully open centre eye (k = 15 == v4 gaze 16)."""
    fr = [_cspy5_eye(k / (CSPY5_NOPEN - 1.0)) for k in range(CSPY5_NOPEN)]
    assert np.array_equal(np.asarray(fr[-1]), np.asarray(_cspy4_frames()[16])), "open frame != v4 centre eye"
    return fr


def cityspy_eye5_line():
    """City Spy (229) v5: the closed lid line alone (one faint row per CSPY5_LINE blend level)."""
    return [_cspy5_eye(0.0)]


def cityspy_eye5_timeline(base, v4base):
    """City Spy (229) v5 slot-1 list for patch_cityspy_v1.py (35 ms per entry, real time mod len):
    lid line fades in 0.21 s (3 faint rows x 2) / lids open 0.77 s (22 entries over 16 eased apertures) / hold 0.39 /
    look left 0.6 / hold 0.6 / sweep right 0.8 / hold 0.6 / back 0.5 / hold 0.32 / lids close 0.77 / lid line fades out
    0.21 / hidden 2.0 s.  base = v5 first id: +0..+15 apertures, +16..+18 faint lid-line rows; v4base = the v4 ids
    (+0 blank, +1..+33 gaze)."""
    BL, G0 = v4base, v4base + 1
    def gz(px): return G0 + int(round((px + 4.0) / 0.25))
    def ap(t): return base + max(0, min(CSPY5_NOPEN - 1, int(round(_ease4(t) * (CSPY5_NOPEN - 1)))))
    NO = 22
    seq = []
    seq += [base + 16] * 2 + [base + 17] * 2 + [base + 18] * 2                 # faint lid line appears
    seq += [ap(i / (NO - 1)) for i in range(NO)]                              # lids part (k 0 .. 15)
    seq += [gz(0)] * 11
    seq += [gz(-4.0 * _ease4((i + 1) / 17)) for i in range(17)]
    seq += [gz(-4.0)] * 17
    seq += [gz(-4.0 + 8.0 * _ease4((i + 1) / 23)) for i in range(23)]
    seq += [gz(4.0)] * 17
    seq += [gz(4.0 - 4.0 * _ease4((i + 1) / 14)) for i in range(14)]
    seq += [gz(0)] * 9
    seq += [ap(1 - i / (NO - 1)) for i in range(NO)]                          # lids close (k 15 .. 0)
    seq += [base + 18] * 2 + [base + 17] * 2 + [base + 16] * 2                 # lid line fades away
    seq += [BL] * 57                                                          # 2 s hidden
    return seq


# ---- City Spy v6 eye (2026-10-18; user: "have the iris start moving left right BEFORE the eye has fully opened, and
# have the eye start to shut as soon as the eye reaches centre (from the right)").  Lids and gaze now OVERLAP, so the
# frames are combined (aperture o x gaze g): _cspy6_eye(o, g) = the v5 eyelid model with the v4 sphere iris at gaze g
# (o = 1 is pixel-identical to the v4 gaze frame, g = 0 to the v5 aperture frame - both asserted).  Timeline: the
# look-left begins halfway through the opening; the return from the right runs straight into the closing (no centre
# hold).  Only the (o < 1, g != 0) combinations are new images (DualDF 6420+); o = 1 reuses the v4 gaze ids and
# (o < 1, g = 0) the v5 apertures.
CSPY6_NO = 22                     # entries for a full open / close (35 ms each = 0.77 s)
CSPY6_LEFT_AT = 11                # opening entry at which the iris starts sliding left (halfway open)
CSPY6_CLOSE_AT = 8                # return-to-centre entry (of 14) at which the lids start to close
_CSPY6 = None


def _cspy6_eye(o, gaze):
    Wd, Hd, S = 40, 28, 4; cx, cy = 20.0, 14.0
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    a, b = 12.0, 6.8
    u = (xx - cx) / a; v = (yy - cy) / b
    lid = (1 - np.clip(np.abs(u), 0, 1) ** 2) ** 1.2
    if o >= 1.0:
        inside = (np.abs(v) <= lid) & (np.abs(u) <= 1)
        outline = (np.abs(np.abs(v) - lid) < 0.22) & (np.abs(u) <= 1.04)
    else:
        mid = 0.2 * lid * (1 - o)
        vu, vl = -lid * o + mid, lid * o + mid
        inside = (v >= vu) & (v <= vl) & (np.abs(u) <= 1)
        tol = 0.11 + 0.11 * o
        outline = ((np.abs(v - vu) < tol) | (np.abs(v - vl) < tol)) & (np.abs(u) <= 1.04) & (lid > 0.02)
    glow = np.exp(-((xx - cx) ** 2 / (2 * 9.0 ** 2) + (yy - cy) ** 2 / (2 * 5.0 ** 2))) * 0.55
    halo = (glow > 0.22 + 0.33 * (1 - o)) & ~inside & ~outline if o > 0.15 else np.zeros_like(inside)
    stars = [(5.0, 6.0), (35.0, 8.0), (31.0, 24.0)]
    st = np.zeros_like(inside)
    if o >= 0.6:
        for sx, sy in stars:
            st |= ((np.abs(xx - sx) <= 0.6) & (np.abs(yy - sy) <= 1.4)) | ((np.abs(yy - sy) <= 0.6) & (np.abs(xx - sx) <= 1.4))
    Y, X = np.mgrid[0:Hd * S, 0:Wd * S].astype(np.float32); X = (X + 0.5) / S; Y = (Y + 0.5) / S
    th = math.asin(max(-0.98, min(0.98, gaze / CSPY4_BALL))); c = math.cos(th)
    gx = cx + gaze
    ri, rp = 4.2, 1.7
    re = np.sqrt(((X - gx) / c) ** 2 + (Y - cy) ** 2)
    iris = np.clip(ri - re + 0.5, 0, 1); pupil = np.clip(rp - re + 0.5, 0, 1)
    hx = gx - 1.6 * c + 0.6 * math.sin(th); hy = cy - 1.8
    gl = np.clip(1.6 - np.sqrt(((X - hx) / max(c, 0.55)) ** 2 + (Y - hy) ** 2) * 1.5, 0, 1)
    rim = np.clip(1.0 - np.abs(re - ri) * 1.6, 0, 1) * 0.35
    R = 225 * (1 - iris) + 200 * iris; G = 210 * (1 - iris) + 60 * iris; B = 245 * (1 - iris) + 220 * iris
    R = R * (1 - rim) + 110 * rim; G = G * (1 - rim) + 30 * rim; B = B * (1 - rim) + 150 * rim
    R = R * (1 - pupil) + 30 * pupil; G = G * (1 - pupil) + 8 * pupil; B = B * (1 - pupil) + 50 * pupil
    R = R * (1 - gl) + 255 * gl; G = G * (1 - gl) + 255 * gl; B = B * (1 - gl) + 255 * gl
    rgb = Image.fromarray(np.dstack([R, G, B]).clip(0, 255).astype(np.uint8), "RGB").resize((Wd, Hd), Image.BOX)
    arr = np.asarray(rgb).astype(np.float32)
    out = np.zeros((Hd, Wd, 4), np.float32)
    out[..., :3][halo] = (70, 34, 120); out[..., 3][halo] = 255
    out[..., :3][inside] = arr[inside]; out[..., 3][inside] = 255
    out[..., :3][outline] = (110, 50, 175); out[..., 3][outline] = 255
    out[..., :3][st] = (215, 190, 245); out[..., 3][st] = 255
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def _cspy6_plan():
    """The v6 slot-1 timeline as (kind, a, g): ('L', row, 0) faint lid-line row 0..2 / ('B', 0, 0) blank /
    ('E', k, gi) eye at aperture index k (0..15, 15 = open) and gaze index gi (0..32, 16 = centre)."""
    def ap(t): return max(0, min(CSPY5_NOPEN - 1, int(round(_ease4(min(1.0, max(0.0, t))) * (CSPY5_NOPEN - 1)))))
    def gi(px): return int(round((px + 4.0) / 0.25))
    NO, NL = CSPY6_NO, 17
    seq = []
    seq += [('L', 0, 0)] * 2 + [('L', 1, 0)] * 2 + [('L', 2, 0)] * 2           # faint lid line appears
    left = [-4.0 * _ease4((i + 1) / NL) for i in range(NL)]                   # the look-left curve
    for i in range(NO):                                                       # lids part; the iris starts left halfway
        g = left[i - CSPY6_LEFT_AT] if i >= CSPY6_LEFT_AT else 0.0
        seq.append(('E', ap(i / (NO - 1)), gi(g)))
    seq += [('E', 15, gi(px)) for px in left[NO - CSPY6_LEFT_AT:]]             # rest of the look-left, fully open
    seq += [('E', 15, gi(-4.0))] * 17                                         # hold left
    seq += [('E', 15, gi(-4.0 + 8.0 * _ease4((i + 1) / 23))) for i in range(23)]   # sweep right
    seq += [('E', 15, gi(4.0))] * 17                                          # hold right
    back = [4.0 - 4.0 * _ease4((i + 1) / 14) for i in range(14)]               # back towards centre ...
    seq += [('E', 15, gi(px)) for px in back[:CSPY6_CLOSE_AT]]
    rest = back[CSPY6_CLOSE_AT:]                                              # ... while the lids already close
    for i in range(NO):
        g = rest[i] if i < len(rest) else 0.0
        seq.append(('E', ap(1 - (i + 1) / NO), gi(g)))
    seq += [('L', 2, 0)] * 2 + [('L', 1, 0)] * 2 + [('L', 0, 0)] * 2           # lid line fades away
    seq += [('B', 0, 0)] * 57                                                 # 2 s hidden
    return seq


def _cspy6_combos():
    """The (aperture k < 15, gaze gi != 16) pairs the timeline needs, in first-use order (= the new images)."""
    out = []
    for kind, k, g in _cspy6_plan():
        if kind == 'E' and k < CSPY5_NOPEN - 1 and g != 16 and (k, g) not in out:
            out.append((k, g))
    return out


def cityspy_eye6_mixed():
    """City Spy (229) v6: the new lid x gaze frames (aperture < 1 with the iris off centre), DualDF 6420+."""
    global _CSPY6
    if _CSPY6 is None:
        assert np.array_equal(np.asarray(_cspy6_eye(1.0, -2.5)), np.asarray(_cspy4_frames()[6])), "o=1 != v4 gaze"
        assert np.array_equal(np.asarray(_cspy6_eye(0.4, 0.0)), np.asarray(_cspy5_eye(0.4))), "g=0 != v5 aperture"
        _CSPY6 = [_cspy6_eye(k / (CSPY5_NOPEN - 1.0), -4.0 + 0.25 * g) for k, g in _cspy6_combos()]
    return list(_CSPY6)


def cityspy_eye6_timeline(base, v5base, v4base):
    """City Spy (229) v6 slot-1 list (35 ms per entry, real time mod len; patch_cityspy_v1.py unchanged).
    base = v6 first id (mixed frames), v5base = v5 apertures (+0..+15) / lid-line rows (+16..+18),
    v4base = v4 blank (+0) / gaze (+1..+33)."""
    combos = _cspy6_combos(); ids = []
    for kind, k, g in _cspy6_plan():
        if kind == 'L': ids.append(v5base + 16 + k)
        elif kind == 'B': ids.append(v4base)
        elif k == CSPY5_NOPEN - 1: ids.append(v4base + 1 + g)
        elif g == 16: ids.append(v5base + k)
        else: ids.append(base + combos.index((k, g)))
    return ids


def reversal_swirl(n=36):
    """Reversal (234) slot 0 (2026-10-18): Second Wind's canvas (96x96, feet at (48, 86), anchor -48/-86), additive,
    36 frames x 2 ticks: two ribbons circle the unit in OPPOSITE directions on a tilted orbit round its chest - a warm
    ember-red one (attack) and a cool steel-blue one (defense) - and as they cross behind the unit at the half-way
    point their colours INVERT (warm turns cool, cool turns warm) with a thin white mirror-flash splitting the unit
    down the middle and a soft ring; paired red/blue motes swap sides; smooth fade in and out."""
    W = H = 96; SS = 2; cx, cy = 48.0, 52.0; rnd = random.Random(2340); out = []
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    motes = [(rnd.uniform(0, 6.28), rnd.uniform(14, 22), rnd.uniform(-14, 14)) for _ in range(12)]
    WARM, COOL = np.array((255, 105, 45), np.float32), np.array((70, 165, 255), np.float32)
    for i in range(n):
        t = i / (n - 1.0)
        env = min(1.0, t / 0.15) ** 0.8 * (1.0 if t < 0.78 else max(0.0, 1 - (t - 0.78) / 0.22) ** 1.4)
        mix = min(1.0, max(0.0, (t - 0.38) / 0.24)); mix = mix * mix * (3 - 2 * mix)      # smoothstep colour inversion
        acc = np.zeros((H, W, 3), np.float32)
        for k, (sgn, c0, c1) in enumerate(((1, WARM, COOL), (-1, COOL, WARM))):
            big = Image.new("L", (W * SS, H * SS), 0); d = ImageDraw.Draw(big)
            head = sgn * 2 * math.pi * 1.35 * t + k * math.pi
            pts = []
            for j in range(48):
                u = j / 47.0; a = head - sgn * 2.4 * u                              # a 2.4 rad trailing arc
                r = 22 - 3 * k; x = cx + r * math.cos(a); y = cy + 9 * math.sin(a) - 6 * math.cos(a) * (1 if k == 0 else -1) * 0.3
                pts.append((x * SS, y * SS, u, a))
            for j in range(len(pts) - 1):
                x0, y0, u, a = pts[j]; x1, y1, _, _ = pts[j + 1]
                front = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(a))                        # the near side brighter
                lvl = int(255 * env * (1 - u) ** 1.3 * front)
                d.line([(x0, y0), (x1, y1)], fill=lvl, width=int(3.0 * SS))
            rib = np.asarray(big.filter(ImageFilter.GaussianBlur(2.0)).resize((W, H), Image.LANCZOS)).astype(np.float32) / 255.0
            col = c0 * (1 - mix) + c1 * mix
            for c in range(3): acc[..., c] += rib * col[c] * 0.95
        for m, (a0, r0, dy) in enumerate(motes):                                    # paired motes trading sides
            side = 1 if m % 2 == 0 else -1
            a = a0 + side * 3.0 * t; x = cx + r0 * math.cos(a); y = cy + dy * 0.6 + 6 * math.sin(a)
            g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 2.2) * env * (0.55 + 0.45 * math.sin(7 * t + m))
            col = (WARM if side > 0 else COOL) * (1 - mix) + (COOL if side > 0 else WARM) * mix
            for c in range(3): acc[..., c] += g * col[c]
        u = (t - 0.42) / 0.30                                                       # the mirror flash at the crossing
        if 0 <= u <= 1:
            f = math.sin(math.pi * u) ** 1.5
            line = np.exp(-((xx - cx) / 1.3) ** 2) * np.exp(-((yy - 50) / 30.0) ** 2) * f
            ring = np.exp(-((np.sqrt((xx - cx) ** 2 + ((yy - 86) / 0.35) ** 2) - (5 + 34 * u)) / 2.6) ** 2) * (1 - u) * 0.6
            for c, cv in enumerate((245, 235, 255)): acc[..., c] += (line * 1.1 + ring) * cv
        out.append(Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"))
    return out


def lucky_glow():
    """Lucky (232) slot 0 (16 frames 40x40 additive, Dark Gift's twinkle slot like Lionheart): a soft green four-leaf
    clover blooms on the unit (four heart-lobed leaves, rotating slowly), golden lucky sparkles spiral up around it,
    then the clover fades out in a gold-green glint."""
    frames = []; rnd = random.Random(232); SZ = 40; N = 16
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); cx, cy = 20.0, 20.0
    sparks = [(rnd.uniform(0, 6.28), rnd.uniform(0.7, 1.2), rnd.uniform(0.8, 1.3), rnd.uniform(0, 0.35)) for _ in range(12)]
    for i in range(N):
        t = i / (N - 1.0)
        grow = min(1.0, t / 0.35); fade = 1.0 if t < 0.6 else max(0.0, 1.0 - (t - 0.6) / 0.4)
        amp = grow * fade
        rot = 0.6 * t
        a = np.arctan2(yy - cy, xx - cx) - rot; r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        # four heart-lobed leaves: r < R * (0.55 + 0.45 |cos 2a|) with a notch
        R = 9.5 * (0.35 + 0.65 * grow)
        leaf = np.clip((R * (0.45 + 0.55 * np.abs(np.cos(2 * a))) - r) / 2.0, 0, 1)
        vein = np.exp(-((np.sin(2 * a)) ** 2) / 0.01) * np.clip(1 - r / (R + 1e-3), 0, 1)     # the 4 midribs, a touch brighter
        core = np.exp(-r * r / 6.0)
        g = amp * (0.75 * leaf + 0.35 * vein * leaf + 0.6 * core)
        gold = amp * 0.9 * core
        for a0, v, sz, ph in sparks:
            age = t - ph
            if age < 0 or age > 0.65: continue
            ang = a0 + 5.0 * age; rad = 4 + 14 * age * v
            x = cx + math.cos(ang) * rad; y = cy + math.sin(ang) * rad * 0.8 - 10 * age
            if 0 <= x < SZ and 0 <= y < SZ:
                tw = (1 - age / 0.65) * (0.6 + 0.4 * math.sin(age * 40 + a0))
                s = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz)) * tw
                gold += 1.1 * s; g += 0.25 * s
        g = np.clip(g, 0, 1); gold = np.clip(gold, 0, 1)
        rr = 255 * np.clip(0.25 * g + 1.0 * gold, 0, 1)
        gg = 255 * np.clip(0.95 * g + 0.85 * gold, 0, 1)
        bb = 255 * np.clip(0.30 * g + 0.25 * gold, 0, 1)
        lum = np.maximum(np.maximum(rr, gg), bb) / 255.0
        frames.append(Image.fromarray(np.dstack([rr, gg, bb, np.where(lum > 0.03, 255, 0)]).astype(np.uint8), "RGBA"))
    return frames


def transmute_motes(n=4):
    """Transmutation (235, Secret L4, 2026-10-18) slot 0: Earth Mastery's map-wide particle (as Golden Age's gold_motes,
    20x20 additive): a molten GOLD drop with an alchemical GREEN glint orbiting it and four thin gold rays that turn
    45 deg over the 4 frames (the base metal turning to gold) - swell, peak, settle, soft."""
    frames = []; yy, xx = np.mgrid[0:20, 0:20].astype(np.float32); cx = cy = 9.5
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    for k, g in enumerate((0.75, 1.1, 0.9, 0.6)):
        a = math.pi / 4 * k / 4.0; u = (xx - cx) * math.cos(a) + (yy - cy) * math.sin(a); v = -(xx - cx) * math.sin(a) + (yy - cy) * math.cos(a)
        core = np.exp(-d2 / (2 * 1.7 ** 2)) * g
        rays = (np.exp(-(v ** 2) / 0.45 - (u ** 2) / (2 * 5.5 ** 2)) + np.exp(-(u ** 2) / 0.45 - (v ** 2) / (2 * 5.5 ** 2))) * 0.5 * g
        halo = np.exp(-d2 / (2 * 3.8 ** 2)) * 0.30 * g
        ga = 2 * math.pi * k / n; gx, gy = cx + 4.2 * math.cos(ga), cy + 3.0 * math.sin(ga)
        glint = np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * 0.9 ** 2)) * 0.9
        gold = np.clip(np.maximum(np.maximum(core, rays), halo), 0, 1); w = np.clip(core * 1.2 - 0.3, 0, 1)
        r = 255 * gold + 70 * glint; gch = (170 + 75 * w) * gold + 235 * glint; b = (30 + 170 * w) * gold + 90 * glint
        al = 255 * ((gold + glint) > 0.04)
        frames.append(Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(gch, 0, 255), np.clip(b, 0, 255), al]).astype(np.uint8), "RGBA"))
    return frames


def mimic_shimmer(n=20):
    """Mimic (233) slot 1 (2026-10-18): the kind-0x26 driver at the CASTER's hex (patch_tc_mimic_v1.py), additive,
    64x96 (hex centre at (32, 76)): a tall oval pane of silvery-violet light forms around the caster (frames 0-5), a
    bright sheen sweeps across it left -> right and is answered by its mirror image sweeping back right -> left
    (6-13), then the pane breaks into glints that drift up and fade (14-19)."""
    W, H = 64, 96; cx, cy, A, B = 32.0, 50.0, 17.0, 30.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rnd = random.Random(2330)
    e = np.sqrt(((xx - cx) / A) ** 2 + ((yy - cy) / B) ** 2)
    glints = [(rnd.uniform(0, 6.283), rnd.uniform(0.6, 1.05), rnd.uniform(0.6, 1.4)) for _ in range(22)]
    out = []
    for i in range(n):
        t = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        form = min(1.0, i / 5.0); fade = 1.0 if i < 14 else max(0.0, 1.0 - (i - 13) / 6.0)
        rim = 0.85 * np.exp(-((e - 1.0) / 0.07) ** 2) * form * fade
        pane = np.clip(1.0 - e, 0, 1) ** 0.6 * 0.22 * form * fade
        sheen = np.zeros_like(xx)
        if 6 <= i <= 13:
            k = (i - 6) / 7.0
            for pos, w in ((-1.0 + 2.0 * k, 0.9), (1.0 - 2.0 * k, 0.6)):                  # the sweep and its mirror
                u = (xx - cx) / A + 0.35 * (yy - cy) / B * (1 if w > 0.7 else -1)
                sheen += w * np.exp(-((u - pos) / 0.16) ** 2)
            sheen *= (e < 1.0)
        for c, (rc, pc, sc) in enumerate(((150, 105, 235), (170, 140, 235), (235, 220, 255))):
            acc[..., c] += rim * rc + pane * pc + sheen * sc * fade
        im = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB").convert("RGBA"); dr = ImageDraw.Draw(im)
        if i >= 12:
            g = (i - 12) / 7.0
            for a, v, s in glints:
                x = cx + A * v * math.cos(a); y = cy + B * v * math.sin(a) - 22 * g * s
                lum = int(255 * max(0.0, 1.0 - g) ** 0.7)
                if lum < 20: continue
                col = (lum, int(lum * 0.9), 255 if lum > 0 else 0, 255); r = 1.6 if s > 1.0 else 1.0
                dr.line([(x - r, y), (x + r, y)], fill=col); dr.line([(x, y - r), (x, y + r)], fill=col)
        out.append(im)
    return out


SB_GOLD = (255, 196, 70); SB_WGOLD = (255, 240, 190); SB_BLUE = (70, 140, 255); SB_EBLUE = (150, 215, 255)


def _sb_rgba(acc, thr=0.03, edge=7.0):
    H, W = acc.shape[:2]; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    e = np.minimum(np.minimum(xx, W - 1 - xx), np.minimum(yy, H - 1 - yy))   # fade every glow out before the canvas edge
    acc = acc * np.clip(e / edge, 0, 1)[..., None] ** 1.5
    a = acc.max(axis=2) / 255.0
    return Image.fromarray(np.dstack([np.clip(acc, 0, 255), 255 * (a > thr)]).astype(np.uint8), "RGBA")


def _sb_blob(acc, xx, yy, x, y, r, col, k=1.0):
    g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r)) * k
    for c in range(3): acc[..., c] += g * col[c]


def seeker_head(n=8):
    """Seeker Bolts (ability 0x3A) slot 0: the flying bolt HEAD (kind-6 projectile, drawn looped at the path point;
    frame = map clock + self>>2).  64x64, centre (32, 33) = the vanilla BOLTS anchor -32/-33; additive (770): a
    white-gold core in a gold glow wrapped in a crackling blue corona, two small motes (one gold, one blue) circling
    the core once per loop (the orbs it was born from).  8-frame seamless loop."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    for k in range(n):
        t = k / n; fl = 0.88 + 0.12 * math.cos(2 * math.pi * t * 2)
        acc = np.zeros((H, W, 3), np.float32)
        _sb_blob(acc, xx, yy, cx, cy, 10.0 * fl, SB_BLUE, 0.6)                     # blue corona
        _sb_blob(acc, xx, yy, cx, cy, 4.2, SB_GOLD, 0.75)                          # gold glow
        _sb_blob(acc, xx, yy, cx, cy, 1.6, SB_WGOLD, 0.55)                         # white-hot core
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
        crackle = (0.5 + 0.5 * np.cos(5 * ang + 2 * math.pi * t * 3 + 1.3 * np.sin(3 * ang - 2 * math.pi * t))) ** 6
        ring = np.exp(-((d - 7.5 * fl) ** 2) / 2.2) * crackle * 0.9         # flickering blue arcs on the corona edge
        for c in range(3): acc[..., c] += ring * (0.5 * SB_EBLUE[c] + 0.5 * SB_BLUE[c])
        for j, col in enumerate((SB_GOLD, SB_EBLUE)):
            a = 2 * math.pi * (t + j * 0.5); mx = cx + 8.5 * math.cos(a); my = cy + 4.0 * math.sin(a)
            _sb_blob(acc, xx, yy, mx, my, 1.4, col, 1.1); _sb_blob(acc, xx, yy, mx, my, 3.0, col, 0.35)
        out.append(_sb_rgba(acc))
    return out


def seeker_trail(n=8):
    """Seeker Bolts (0x3A) slot 1: the TRAIL (TCPCK 0x42e85c draws slot-1 frame j at path point pos-4+(7-j)/2: frame 0
    = right behind the head, frame 7 = the oldest).  64x64, centre (32, 33); additive: a gold puff that cools to blue
    and shrinks with age, plus a few gold/blue sparks that scatter and wink out."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3708)
    sp = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), j % 2) for j in range(4)]
    for k in range(n):
        u = k / (n - 1.0); rad = 5.5 * (1 - 0.65 * u) + 1.0; br = (1 - u) ** 1.2
        acc = np.zeros((H, W, 3), np.float32)
        col = tuple(SB_GOLD[c] * (1 - u) ** 1.5 + SB_BLUE[c] * (1 - (1 - u) ** 1.5) for c in range(3))
        _sb_blob(acc, xx, yy, cx, cy, rad, col, 0.8 * br)
        _sb_blob(acc, xx, yy, cx, cy, rad * 0.45, SB_WGOLD, 0.6 * (1 - u) ** 2)
        for sx, sy, j in sp:
            x, y = cx + sx * (3 + 9 * u), cy + sy * (3 + 9 * u) - 2 * u
            _sb_blob(acc, xx, yy, x, y, 0.9, (SB_GOLD if j == 0 else SB_EBLUE), 1.2 * max(0.0, 1 - 1.3 * u))
        out.append(_sb_rgba(acc))
    return out


def seeker_spin(n=30):
    """Seeker Bolts (0x3A) slot 2: the START-UP in front of the caster (a kind-0x26 helper the engine script spawns at
    the bolt's path point ~20 px toward the target while it holds the bolt; 1 tick per frame = n ticks).  72x72,
    centre (36, 36); additive: three small orbs (gold, blue, gold) fade in on a tilted ring and SPIN, accelerating;
    the ring tightens, the orbs brighten and streak, blue arcs flicker between them while a gold-white core swells in
    the middle; the orbs collapse into the core and it flashes (the launch)."""
    W = H = 72; cx, cy = 36.0, 36.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    cols = (SB_GOLD, SB_EBLUE, SB_GOLD)
    ang = [0.0]                                                              # an accelerating spin, 0.035 -> 0.16 rev/frame
    for i in range(1, n): ang.append(ang[-1] + 2 * math.pi * (0.035 + 0.125 * (i / (n - 1)) ** 1.6))
    for i in range(n):
        u = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        fade_in = min(1.0, (i + 1) / 5.0)
        collapse = max(0.0, (u - 0.78) / 0.22)                               # 0 .. 1 over the last ~7 frames
        R = (16.0 - 5.0 * u) * (1 - collapse) ** 1.3                          # the ring tightens, then collapses
        bright = (0.75 + 0.45 * u) * fade_in
        osz = (1.9 + 0.7 * u) * (0.5 + 0.5 * fade_in)
        for j in range(3):
            for s in range(5):                                               # a short streak back along the orbit
                a = ang[i] + j * 2 * math.pi / 3 - s * (0.05 + 0.3 * u); w = (1 - s / 5.0) ** 1.5
                x = cx + R * math.cos(a); y = cy + 0.45 * R * math.sin(a)
                _sb_blob(acc, xx, yy, x, y, osz + 2.2, cols[j], 0.4 * bright * w)
                if s == 0:
                    _sb_blob(acc, xx, yy, x, y, osz, cols[j], 1.0 * bright)
                    _sb_blob(acc, xx, yy, x, y, osz * 0.5, SB_WGOLD, 0.7 * bright)
        if 0.45 < u < 0.97 and i % 2 == 0:                                   # blue arcs between the orbs while powering up
            rnd = random.Random(3720 + i)
            pts = [(cx + R * math.cos(ang[i] + j * 2 * math.pi / 3), cy + 0.45 * R * math.sin(ang[i] + j * 2 * math.pi / 3)) for j in range(3)]
            for j in range(3):
                (x0, y0), (x1, y1) = pts[j], pts[(j + 1) % 3]
                nx, ny = -(y1 - y0), (x1 - x0); L = math.hypot(nx, ny) or 1.0
                for s in range(12):
                    f = s / 11.0; jit = rnd.uniform(-1.6, 1.6) * math.sin(math.pi * f)
                    _sb_blob(acc, xx, yy, x0 + (x1 - x0) * f + jit * nx / L, y0 + (y1 - y0) * f + jit * ny / L, 0.8, SB_EBLUE, 0.55 * (u - 0.45) / 0.5)
        core = max(0.0, (u - 0.3) / 0.7) ** 1.5                              # the core swelling in the middle
        _sb_blob(acc, xx, yy, cx, cy, 3.0 + 6.0 * core, SB_BLUE, 0.5 * core)
        _sb_blob(acc, xx, yy, cx, cy, 1.5 + 2.5 * core, SB_GOLD, 0.9 * core)
        _sb_blob(acc, xx, yy, cx, cy, 1.0 + 1.2 * core, SB_WGOLD, 1.0 * core)
        if collapse > 0:                                                     # the launch flash
            fl = math.sin(math.pi * min(1.0, collapse * 1.15)) if collapse < 0.87 else 1.0 - (collapse - 0.87) / 0.13 * 0.5
            _sb_blob(acc, xx, yy, cx, cy, 4.0 + 5.0 * collapse, SB_WGOLD, 0.55 * fl)
            _sb_blob(acc, xx, yy, cx, cy, 7.0 + 6.0 * collapse, SB_GOLD, 0.5 * fl)
            _sb_blob(acc, xx, yy, cx, cy, 11.0 + 5.0 * collapse, SB_BLUE, 0.4 * fl)
            d = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.6) ** 2)
            ring = np.exp(-((d - (6 + 22 * collapse)) ** 2) / 3.0) * 0.7 * (1 - collapse * 0.6)
            for c in range(3): acc[..., c] += ring * SB_EBLUE[c]
        out.append(_sb_rgba(acc))
    return out


def seeker_impact(n=16):
    """Seeker Bolts (0x3A) slot 3: the IMPACT BURST (a kind-0x26 helper the engine script spawns at the bolt's last path
    point on arrival; 1 tick per frame).  96x96, centre (48, 48); additive: a white-gold flash, an expanding blue
    shock ring (flattened 0.6 for the isometric ground), gold sparks flung outward on falling arcs and blue motes that
    linger and fade."""
    W = H = 96; cx, cy = 48.0, 48.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    rnd = random.Random(3740)
    sparks = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.6, 1.0), j % 3) for j in range(16)]
    motes = [(rnd.uniform(-18, 18), rnd.uniform(-14, 8), rnd.uniform(0.4, 1.0)) for _ in range(8)]
    for i in range(n):
        u = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        flash = max(0.0, 1 - u / 0.35) ** 1.4
        _sb_blob(acc, xx, yy, cx, cy, 4 + 6 * u, SB_WGOLD, 0.9 * flash)
        _sb_blob(acc, xx, yy, cx, cy, 8 + 8 * u, SB_GOLD, 0.75 * flash)
        _sb_blob(acc, xx, yy, cx, cy, 13 + 6 * u, SB_BLUE, 0.45 * max(0.0, 1 - u / 0.6))
        d = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.6) ** 2)
        ring = np.exp(-((d - (4 + 40 * u ** 0.7)) ** 2) / (2.0 + 6 * u)) * (1 - u) ** 1.2
        for c in range(3): acc[..., c] += ring * (0.15 * SB_WGOLD[c] + 0.75 * SB_EBLUE[c])
        for a, v, j in sparks:
            L = 34 * v * (1 - (1 - u) ** 2); x = cx + L * math.cos(a); y = cy + 0.75 * L * math.sin(a) + 14 * u * u
            b = max(0.0, 1 - u * 1.15); col = SB_GOLD if j else SB_EBLUE
            _sb_blob(acc, xx, yy, x, y, 1.0, col, 1.3 * b)
            xt, yt = cx + 0.7 * L * math.cos(a), cy + 0.75 * 0.7 * L * math.sin(a) + 10 * u * u
            _sb_blob(acc, xx, yy, xt, yt, 0.9, col, 0.5 * b)
        for mx, my, v in motes:
            b = math.sin(math.pi * min(1.0, u * 1.1)) * v
            _sb_blob(acc, xx, yy, cx + mx * (0.5 + u), cy + my * (0.5 + u) - 8 * u, 1.3, SB_EBLUE, 0.8 * b)
        out.append(_sb_rgba(acc))
    return out


def seeker_head2(n=8):
    """Seeker Bolts (0x3A) slot 0 v2 (2026-10-18, user: "has the bolt actually changed? I don't see any blue"): a SOLID
    sprite (ALPHA 258/95, opaque pixels only, so the colours survive on bright terrain instead of washing out to white
    like the additive v1): a gold orb (shaded, with a white-hot glint) inside a ring of saturated blue arcane fire, four
    jagged electric-blue lightning spurs crackling off the ring (they rotate through the 8-frame loop) and two small motes
    (gold + pale blue) orbiting it.  64x64, centre (32, 33) = anchor -32/-33."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
    rnd = random.Random(3758)
    for k in range(n):
        t = k / n
        rgb = np.zeros((H, W, 3), np.float32); a = np.zeros((H, W), bool)
        # blue fire ring: radius wobbles with a flickering flame edge
        edge = 8.2 + 1.3 * np.sin(6 * ang + 2 * math.pi * t * 2) * np.cos(3 * ang - 2 * math.pi * t) + 0.6 * np.sin(11 * ang - 2 * math.pi * t * 3)
        ring = d <= edge
        shade = np.clip((d - 5.0) / np.maximum(edge - 5.0, 0.1), 0, 1)               # 0 inner .. 1 outer edge
        for c, (ci, co) in enumerate(zip((90, 170, 255), (25, 70, 215))):
            rgb[..., c] = np.where(ring, ci * (1 - shade) + co * shade, rgb[..., c])
        a |= ring
        # lightning spurs: 4 jagged polylines from the ring outwards
        sp = np.zeros((H, W), bool)
        for j in range(4):
            a0 = 2 * math.pi * (j / 4 + t / 4) + 0.35 * math.sin(2 * math.pi * (t + j * 0.3))
            x, y = cx + 7.5 * math.cos(a0), cy + 7.5 * math.sin(a0) * 0.85
            L = 5 + 4 * (0.5 + 0.5 * math.sin(2 * math.pi * (t * 2 + j * 0.37)))
            rr = random.Random(9000 + 31 * j + k)
            for s in range(int(L)):
                aa = a0 + rr.uniform(-0.9, 0.9)
                x += math.cos(aa); y += math.sin(aa) * 0.85
                ix, iy = int(round(x)), int(round(y))
                if 1 <= ix < W - 1 and 1 <= iy < H - 1: sp[iy, ix] = True
        rgb[sp] = (160, 225, 255); a |= sp
        # gold orb: radius 5 with a lit top-left and a darker bottom-right rim, white-hot glint
        orb = d <= 5.0
        lx, ly = -0.6, -0.8; nrm = np.clip(((xx - cx) * lx + (yy - cy) * ly) / 5.0, -1, 1)
        lit = 0.5 + 0.5 * nrm
        for c, (dk, br) in enumerate(zip((205, 120, 15), (255, 222, 110))):
            rgb[..., c] = np.where(orb, dk * (1 - lit) + br * lit, rgb[..., c])
        gl = (xx - (cx - 1.6)) ** 2 + (yy - (cy - 1.8)) ** 2 <= 2.3
        rgb[gl] = (255, 252, 230)
        # orbiting motes
        for j, col in enumerate(((255, 205, 60), (190, 235, 255))):
            aa = 2 * math.pi * (t + j * 0.5); mx = cx + 11.0 * math.cos(aa); my = cy + 4.5 * math.sin(aa)
            m = (xx - mx) ** 2 + (yy - my) ** 2 <= 1.8
            rgb[m] = col; a |= m
        out.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * a]).astype(np.uint8), "RGBA"))
    return out


def seeker_trail2(n=8):
    """Seeker Bolts (0x3A) slot 1 v2: the TRAIL, drawn AFTER the head (TCPCK 0x42e85c, frame j at path point
    pos-4+(7-j)/2: frame 0 sits on the head, 7 is the oldest).  Additive (770), 64x64, centre (32, 33).  Frame 0 is a
    HOLLOW blue halo round the head (no white blob over the orb, so the solid head keeps its colours); the older frames
    are saturated blue wisps shrinking behind it with gold and blue sparks that scatter and wink out."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3709)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    sp = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), j % 2) for j in range(6)]
    blue = (40, 110, 255)
    for k in range(n):
        u = k / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        if k <= 1:
            halo = np.exp(-((d - 11.0) ** 2) / 10.0) * (0.5 if k == 0 else 0.3)
            for c in range(3): acc[..., c] += halo * blue[c]
        else:
            rad = 3.6 * (1 - 0.5 * u) + 1.0; br = (1 - u) ** 1.1
            _sb_blob(acc, xx, yy, cx, cy, rad, blue, 0.75 * br)
            _sb_blob(acc, xx, yy, cx, cy, rad * 0.4, (90, 170, 255), 0.5 * br)
        for sx, sy, j in sp:
            x, y = cx + sx * (4 + 10 * u), cy + sy * (4 + 10 * u) - 2 * u
            _sb_blob(acc, xx, yy, x, y, 0.85, ((255, 190, 50) if j == 0 else (120, 200, 255)), 1.3 * max(0.0, 1 - 1.2 * u) * (k > 0))
        out.append(_sb_rgba(acc))
    return out


SB_PBLUE = (175, 225, 255); SB_SKY = (110, 185, 255)


def seeker_head3(n=8):
    """Seeker Bolts (0x3A) slot 0 v3 (2026-10-18, user: v2 'awesome' but make the bolt look more like the start-up -
    less solid, more glow, lighter blue): the spin-up's collapsed core in flight, drawn as concentric opaque bands so it
    READS as a glow while staying visible on bright terrain (ALPHA 258 at blend 75 - the terrain shows through a little;
    opaque pixels only, soft per-pixel alpha dithers in 258): a white-hot centre, a gold core (r 3.8), a pale sky-blue
    inner glow (r ~5.3) and a lighter-blue flickering outer glow (r ~7.4), and the spin's THREE orbs (gold, pale blue,
    gold) still circling it on a tilted ring.  64x64, centre (32, 33) = anchor -32/-33; 8-frame loop."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
    for k in range(n):
        t = k / n
        rgb = np.zeros((H, W, 3), np.float32); a = np.zeros((H, W), bool)
        e2 = 7.0 + 0.9 * np.sin(5 * ang + 2 * math.pi * t * 2) + 0.5 * np.sin(9 * ang - 2 * math.pi * t * 3)
        outer = d <= e2; rgb[outer] = SB_SKY; a |= outer
        e1 = 5.1 + 0.4 * np.sin(4 * ang - 2 * math.pi * t * 2)
        inner = d <= e1; rgb[inner] = SB_PBLUE
        core = d <= 3.8
        u = np.clip(d / 3.8, 0, 1)
        for c, (ci, co) in enumerate(zip(SB_WGOLD, SB_GOLD)):
            rgb[..., c] = np.where(core, ci * (1 - u ** 1.5) + co * u ** 1.5, rgb[..., c])
        rgb[d <= 1.3] = (255, 253, 240)
        for j, col in enumerate((SB_GOLD, SB_PBLUE, SB_GOLD)):
            aa = 2 * math.pi * (t + j / 3.0); mx = cx + 10.5 * math.cos(aa); my = cy + 0.45 * 10.5 * math.sin(aa)
            m = (xx - mx) ** 2 + (yy - my) ** 2 <= 1.8
            rgb[m] = col; a |= m
            rgb[(xx - mx) ** 2 + (yy - my) ** 2 <= 0.45] = (255, 252, 235)
        out.append(Image.fromarray(np.dstack([np.clip(rgb, 0, 255), 255 * a]).astype(np.uint8), "RGBA"))
    return out


def seeker_trail3(n=8):
    """Seeker Bolts (0x3A) slot 1 v3: the GLOW + trail, additive (770), drawn AFTER the head (TCPCK 0x42e85c: frame j at
    path point pos-4+(7-j)/2, frame 0 = on the head, 7 = oldest).  64x64, centre (32, 33).  Frames 0-1 = the spin orb's
    soft halo round the head - a wide blue glow (blue-weighted so it stays BLUE on sand instead of washing to white),
    hollow over the head so the core keeps its colours, with crackling pale-blue arcs on its edge; frames 2-7 = soft
    light-blue wisps shrinking behind it with gold / pale-blue sparks that scatter and wink out."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3711)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
    hole = 1 - np.exp(-(d / 6.5) ** 4)
    glow = (40, 110, 230)
    sp = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), j % 2) for j in range(6)]
    for k in range(n):
        u = k / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        if k <= 1:
            s = 1.0 if k == 0 else 0.55
            g = np.exp(-(d / 11.5) ** 2) * hole * 0.6 * s
            for c in range(3): acc[..., c] += g * glow[c]
            crackle = (0.5 + 0.5 * np.cos(5 * ang + 1.7 * k + 1.3 * np.sin(3 * ang))) ** 6
            ring = np.exp(-((d - 9.5) ** 2) / 2.0) * crackle * 0.55 * s
            for c in range(3): acc[..., c] += ring * SB_PBLUE[c]
        else:
            rad = 4.0 * (1 - 0.5 * u) + 1.2; br = (1 - u) ** 1.1
            _sb_blob(acc, xx, yy, cx, cy, rad, glow, 0.6 * br)
            _sb_blob(acc, xx, yy, cx, cy, rad * 0.45, SB_SKY, 0.35 * br)
        for sx, sy, j in sp:
            x, y = cx + sx * (4 + 10 * u), cy + sy * (4 + 10 * u) - 2 * u
            _sb_blob(acc, xx, yy, x, y, 0.85, (SB_GOLD if j == 0 else SB_PBLUE), 1.1 * max(0.0, 1 - 1.2 * u) * (k > 0))
        out.append(_sb_rgba(acc))
    return out


SB_GGLOW = (255, 150, 20)


def seeker_head4(n=8):
    """Seeker Bolts (0x3A) slot 0 v4 (2026-10-18, user on v3: 'make the projectile MORE like the startup animation -
    gold/blue GLOW, it still looks too solid'): no opaque disc any more - drawn exactly like the spin-up (seeker_spin,
    additive 770 at blend 90): the spin's collapsed core in flight = a gold glow with a white-hot centre inside a soft
    blue halo, the spin's THREE orbs (gold, light blue, gold) still circling it on the tilted ring with short streaks,
    and flickering blue arcs on the halo edge.  Readable on light terrain through saturated blue/gold, not opacity.
    64x64, centre (32, 33) = anchor -32/-33; 8-frame loop."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
    cols = (SB_GOLD, SB_EBLUE, SB_GOLD)
    for k in range(n):
        t = k / n; fl = 0.9 + 0.1 * math.cos(2 * math.pi * t * 2)
        acc = np.zeros((H, W, 3), np.float32)
        _sb_blob(acc, xx, yy, cx, cy, 9.0 * fl, SB_BLUE, 0.42)                    # the spin's blue halo
        _sb_blob(acc, xx, yy, cx, cy, 5.0, SB_SKY, 0.12)
        _sb_blob(acc, xx, yy, cx, cy, 3.3, SB_GGLOW, 0.62)                        # gold glow
        _sb_blob(acc, xx, yy, cx, cy, 1.4, SB_WGOLD, 0.6)                        # white-hot centre
        crackle = (0.5 + 0.5 * np.cos(5 * ang + 2 * math.pi * t * 3 + 1.3 * np.sin(3 * ang - 2 * math.pi * t))) ** 6
        ring = np.exp(-((d - 8.0 * fl) ** 2) / 2.0) * crackle * 0.55
        for c in range(3): acc[..., c] += ring * SB_EBLUE[c]
        R = 12.5
        for j in range(3):
            for s in range(4):                                                   # orb + a short streak back along the orbit
                a = 2 * math.pi * (t + j / 3.0) - s * 0.22; w = (1 - s / 4.0) ** 1.5
                x = cx + R * math.cos(a); y = cy + 0.45 * R * math.sin(a)
                _sb_blob(acc, xx, yy, x, y, 3.0, cols[j], 0.22 * w)
                if s == 0:
                    _sb_blob(acc, xx, yy, x, y, 1.6, cols[j], 0.85)
                    _sb_blob(acc, xx, yy, x, y, 0.7, SB_WGOLD, 0.5)
        out.append(_sb_rgba(acc))
    return out


def seeker_trail4(n=8):
    """Seeker Bolts (0x3A) slot 1 v4: additive (770), drawn AFTER the head (frame j at path point pos-4+(7-j)/2, frame 0 =
    on the head).  64x64, centre (32, 33).  Frames 0-1 = a wide soft blue glow round the head (only a small hollow now -
    the head is a glow itself), its edge crackling with light-blue arcs and a faint gold rim; frames 2-7 = blue glow
    wisps shrinking behind it with gold / light-blue sparks that scatter and wink out (gold-weighted, the spin's
    colours)."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3712)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx)
    hole = 1 - np.exp(-(d / 4.0) ** 4)
    glow = (40, 110, 235)
    sp = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), j % 3) for j in range(8)]
    for k in range(n):
        u = k / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        if k <= 1:
            s = 1.0 if k == 0 else 0.55
            g = np.exp(-(d / 13.0) ** 2) * hole * 0.32 * s
            for c in range(3): acc[..., c] += g * glow[c]
            crackle = (0.5 + 0.5 * np.cos(5 * ang + 1.7 * k + 1.3 * np.sin(3 * ang))) ** 6
            ring = np.exp(-((d - 11.0) ** 2) / 2.0) * crackle * 0.5 * s
            for c in range(3): acc[..., c] += ring * SB_EBLUE[c]
            rim = np.exp(-((d - 6.5) ** 2) / 1.5) * 0.18 * s
            for c in range(3): acc[..., c] += rim * SB_GOLD[c]
        else:
            rad = 4.5 * (1 - 0.5 * u) + 1.2; br = (1 - u) ** 1.1
            _sb_blob(acc, xx, yy, cx, cy, rad, glow, 0.55 * br)
            _sb_blob(acc, xx, yy, cx, cy, rad * 0.45, SB_GGLOW, 0.30 * br * (1 - u))
        for sx, sy, j in sp:
            x, y = cx + sx * (4 + 11 * u), cy + sy * (4 + 11 * u) - 2 * u
            _sb_blob(acc, xx, yy, x, y, 0.9, (SB_EBLUE if j == 0 else SB_GOLD), 1.15 * max(0.0, 1 - 1.2 * u) * (k > 0))
        out.append(_sb_rgba(acc))
    return out


def seeker_impact2(n=16):
    """Seeker Bolts (0x3A) slot 3 v2 (2026-10-18, user: 'I want the hit gfx to have some GOLD too'): seeker_impact with
    gold worked through it - a saturated GOLD flash core (white-hot only at the very centre), a GOLD shock ring
    following just inside the blue one, gold sparks bigger and with longer streaks, and the lingering motes alternating
    gold / light blue.  96x96, centre (48, 48); additive, 1 tick per frame."""
    W = H = 96; cx, cy = 48.0, 48.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    rnd = random.Random(3740)
    sparks = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.6, 1.0), j % 3) for j in range(18)]
    motes = [(rnd.uniform(-18, 18), rnd.uniform(-14, 8), rnd.uniform(0.4, 1.0), j % 2) for j in range(10)]
    d = np.sqrt((xx - cx) ** 2 + ((yy - cy) / 0.6) ** 2)
    for i in range(n):
        u = i / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        flash = max(0.0, 1 - u / 0.35) ** 1.4
        _sb_blob(acc, xx, yy, cx, cy, 2 + 3 * u, SB_WGOLD, 0.55 * flash)
        _sb_blob(acc, xx, yy, cx, cy, 8 + 8 * u, SB_GGLOW, 0.75 * flash)
        _sb_blob(acc, xx, yy, cx, cy, 13 + 6 * u, SB_BLUE, 0.30 * max(0.0, 1 - u / 0.6))
        rb = 4 + 40 * u ** 0.7
        ring = np.exp(-((d - rb) ** 2) / (2.0 + 6 * u)) * (1 - u) ** 1.2
        for c in range(3): acc[..., c] += ring * (0.1 * SB_WGOLD[c] + 0.8 * SB_EBLUE[c])
        ug = max(0.0, u - 0.06) / 0.94                                           # the gold ring, a step behind the blue one
        rg = np.exp(-((d - (3 + 30 * ug ** 0.7)) ** 2) / (1.6 + 5 * ug)) * (1 - ug) ** 1.4 * (i > 0)
        for c in range(3): acc[..., c] += rg * 0.85 * SB_GGLOW[c]
        for a, v, j in sparks:
            L = 36 * v * (1 - (1 - u) ** 2); x = cx + L * math.cos(a); y = cy + 0.75 * L * math.sin(a) + 14 * u * u
            b = max(0.0, 1 - u * 1.1); col = SB_GOLD if j else SB_EBLUE
            _sb_blob(acc, xx, yy, x, y, 1.2 if j else 1.0, col, 1.35 * b)
            for f in (0.75, 0.55):
                xt, yt = cx + f * L * math.cos(a), cy + 0.75 * f * L * math.sin(a) + 14 * f * u * u
                _sb_blob(acc, xx, yy, xt, yt, 0.9, col, 0.45 * b * f)
        for mx, my, v, j in motes:
            b = math.sin(math.pi * min(1.0, u * 1.1)) * v
            _sb_blob(acc, xx, yy, cx + mx * (0.5 + u), cy + my * (0.5 + u) - 8 * u, 1.3, (SB_GOLD if j else SB_EBLUE), 0.8 * b)
        out.append(_sb_rgba(acc))
    return out


SB_WBLUE = (215, 240, 255); SB_DBLUE = (30, 95, 255)


def seeker_head5(n=8):
    """Seeker Bolts (0x3A) slot 0 v5 (2026-10-18, user on v4: 'reverse the colours - blue becomes gold and gold becomes
    blue; make it a bit TIGHTER - don't change the tail length but slightly less wide/fat'): seeker_head4 with the
    roles swapped - a saturated BLUE glow with a white-blue centre inside a soft GOLD halo, crackling gold arcs on the
    halo edge, the three orbs now light blue / gold / light blue - and every radius x0.78 (head ~22 % slimmer).
    Additive 770 at blend 90; 64x64, centre (32, 33) = anchor -32/-33; 8-frame loop."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx); S5 = 0.78
    cols = (SB_SKY, SB_GOLD, SB_SKY)
    for k in range(n):
        t = k / n; fl = 0.9 + 0.1 * math.cos(2 * math.pi * t * 2)
        acc = np.zeros((H, W, 3), np.float32)
        hole = 1 - np.exp(-(d / (3.4 * S5)) ** 2)                                  # halo kept off the core so the blue stays blue
        g = np.exp(-(d ** 2) / (2 * (9.0 * fl * S5) ** 2)) * 0.46 * hole
        for c in range(3): acc[..., c] += g * SB_GGLOW[c]                          # gold halo (was blue)
        _sb_blob(acc, xx, yy, cx, cy, 3.6 * S5, SB_DBLUE, 1.00)                    # saturated blue glow core (was gold)
        _sb_blob(acc, xx, yy, cx, cy, 1.2 * S5, SB_WBLUE, 0.35)                    # small white-blue centre
        crackle = (0.5 + 0.5 * np.cos(5 * ang + 2 * math.pi * t * 3 + 1.3 * np.sin(3 * ang - 2 * math.pi * t))) ** 6
        ring = np.exp(-((d - 8.0 * fl * S5) ** 2) / 1.6) * crackle * 0.55
        for c in range(3): acc[..., c] += ring * SB_GOLD[c]                       # gold arcs (were light blue)
        R = 12.5 * S5
        for j in range(3):
            for s in range(4):
                a = 2 * math.pi * (t + j / 3.0) - s * 0.22; w = (1 - s / 4.0) ** 1.5
                x = cx + R * math.cos(a); y = cy + 0.45 * R * math.sin(a)
                _sb_blob(acc, xx, yy, x, y, 3.0 * S5, cols[j], 0.22 * w)
                if s == 0:
                    _sb_blob(acc, xx, yy, x, y, 1.6 * S5, cols[j], 0.85)
                    _sb_blob(acc, xx, yy, x, y, 0.6, SB_WBLUE, 0.3)
        out.append(_sb_rgba(acc))
    return out


def seeker_trail5(n=8):
    """Seeker Bolts (0x3A) slot 1 v5: seeker_trail4 with gold <-> blue swapped (a soft GOLD glow round the head with
    crackling gold arcs and a faint blue rim, then gold wisps with blue-weighted sparks) and every LATERAL size x0.78
    (glow radii, arc ring, spark scatter).  The tail LENGTH is unchanged - it comes from the engine placing frame j at
    path point pos-4+(7-j)/2, not from the art.  Additive 770; 64x64, centre (32, 33)."""
    W = H = 64; cx, cy = 32.0, 33.0; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); out = []; rnd = random.Random(3712)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2); ang = np.arctan2(yy - cy, xx - cx); S5 = 0.78
    hole = 1 - np.exp(-(d / (4.0 * S5)) ** 4)
    glow = (235, 140, 25)
    sp = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), j % 3) for j in range(8)]
    for k in range(n):
        u = k / (n - 1.0); acc = np.zeros((H, W, 3), np.float32)
        if k <= 1:
            s = 1.0 if k == 0 else 0.55
            g = np.exp(-(d / (13.0 * S5)) ** 2) * hole * 0.30 * s
            for c in range(3): acc[..., c] += g * glow[c]
            crackle = (0.5 + 0.5 * np.cos(5 * ang + 1.7 * k + 1.3 * np.sin(3 * ang))) ** 6
            ring = np.exp(-((d - 11.0 * S5) ** 2) / 1.6) * crackle * 0.5 * s
            for c in range(3): acc[..., c] += ring * SB_GOLD[c]
            rim = np.exp(-((d - 6.5 * S5) ** 2) / 1.2) * 0.22 * s
            for c in range(3): acc[..., c] += rim * SB_EBLUE[c]
        else:
            rad = (4.5 * (1 - 0.5 * u) + 1.2) * S5; br = (1 - u) ** 1.1
            _sb_blob(acc, xx, yy, cx, cy, rad, glow, 0.50 * br)
            _sb_blob(acc, xx, yy, cx, cy, rad * 0.45, SB_DBLUE, 0.6 * br * (1 - u))
        for sx, sy, j in sp:
            x, y = cx + sx * (4 + 11 * u) * S5, cy + sy * (4 + 11 * u) * S5 - 2 * u
            _sb_blob(acc, xx, yy, x, y, 0.9, (SB_GOLD if j == 0 else SB_SKY), 1.15 * max(0.0, 1 - 1.2 * u) * (k > 0))
        out.append(_sb_rgba(acc))
    return out


def _tame_paw_field(xx, yy, cx, cy, s):
    """soft paw-print field (0..1): a rounded heel pad + four oval toes in an arc above it; s = scale (1.0 ~ 16 px)."""
    f = np.zeros_like(xx)
    pad = (((xx - cx) / (4.6 * s)) ** 2 + ((yy - (cy + 3.2 * s)) / (3.6 * s)) ** 2)
    f = np.maximum(f, np.clip(1.4 - pad, 0, 1))
    for dx, dy, rx, ry in ((-5.2, -1.6, 1.7, 2.1), (-2.0, -4.6, 1.8, 2.3), (2.0, -4.6, 1.8, 2.3), (5.2, -1.6, 1.7, 2.1)):
        toe = (((xx - (cx + dx * s)) / (rx * s)) ** 2 + ((yy - (cy + dy * s)) / (ry * s)) ** 2)
        f = np.maximum(f, np.clip(1.4 - toe, 0, 1))
    return np.clip(f, 0, 1)


def _tame_leaf(dr, x, y, ang, L, col):
    """a small pointed leaf (two arcs) of length L at (x, y), pointing along ang."""
    ux, uy = math.cos(ang), math.sin(ang); px, py = -uy, ux; w = 0.32 * L
    pts = [(x - ux * L / 2, y - uy * L / 2), (x + px * w, y + py * w), (x + ux * L / 2, y + uy * L / 2), (x - px * w, y - py * w)]
    dr.polygon(pts, fill=col)


def tame_twinkle(n=27):
    """Tame Animal (ability 0xC9) v2 cast twinkle (2026-10-18; user: own gfx, beast-calming): Dominate's TwinkRed
    timing (27 frames 64x64, additive 770/80, id k <-> TWINKGR 220+k) in a nature palette - leaf-green motes and
    small green leaves spiralling IN (0-11), a soft paw print glowing up in the middle with amber glints (12-16 =
    the loop frames), then the leaves drifting up and out as the glow settles (17-26)."""
    SZ = 64; cx, cy = 32.0, 34.0; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); rnd = random.Random(2010)
    motes = [(rnd.uniform(0, 6.283), rnd.uniform(14, 26), rnd.uniform(0.9, 1.6), rnd.random() < 0.3) for _ in range(16)]
    leaves = [(rnd.uniform(0, 6.283), rnd.uniform(12, 22), rnd.uniform(5.0, 7.5)) for _ in range(6)]
    out = []
    for i in range(n):
        g = np.zeros((SZ, SZ), np.float32); amb = np.zeros_like(g)
        if i < 12:   u = i / 11.0; R = 1.0 - 0.75 * u; spin = 2.2 * u; paw = 0.6 * u * u; fade = 0.35 + 0.65 * u
        elif i < 17: u = (i - 12) / 4.0; R = 0.25; spin = 2.2 + 0.6 * u; paw = 0.75 + 0.25 * math.sin(u * math.pi); fade = 1.0
        else:        u = (i - 17) / 9.0; R = 0.25 + 0.9 * u; spin = 2.8 + 0.8 * u; paw = 0.9 * (1 - u) ** 1.5; fade = (1 - u) ** 1.2
        pf = _tame_paw_field(xx, yy, cx, cy - 2, 1.0)
        g += paw * (0.85 * pf + 0.35 * np.exp(-((xx - cx) ** 2 + (yy - cy + 2) ** 2) / 90.0))
        amb += paw * 0.5 * pf
        for a0, r0, sz, isamb in motes:
            a = a0 + spin; r = r0 * R; x = cx + r * math.cos(a); y = cy + 0.7 * r * math.sin(a) - (6 * u if i >= 17 else 0)
            m = fade * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (sz * sz))
            g += 0.9 * m
            if isamb: amb += 0.9 * m
        f = np.clip(g, 0, 1); a_ = np.clip(amb / np.maximum(g, 1e-3), 0, 1)
        r = (90 + 165 * a_) * f; gg = (210 + 30 * a_) * f; b = (80 - 50 * a_) * f
        im = Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(gg, 0, 255), np.clip(b, 0, 255), np.where(f > 0.03, 255, 0)]).astype(np.uint8), "RGBA")
        dr = ImageDraw.Draw(im)
        for a0, r0, L in leaves:
            a = a0 - 1.6 * spin; r = r0 * R; x = cx + r * math.cos(a); y = cy + 0.7 * r * math.sin(a) - (8 * u if i >= 17 else 0)
            k = fade * 0.9; _tame_leaf(dr, x, y, a + 1.2, L * (0.7 + 0.3 * fade), (int(60 * k), int(200 * k), int(50 * k), 255))
        out.append(im)
    return out


def tame_paw(n=12):
    """Tamed (status 0xCA) overlay + Tame Animal success mark (2026-10-18): Charmed's layout (64x64, glyph above the
    unit's head at xs -31 / ys -50, 12-frame loop) - a small glowing green paw print with an amber rim that gently
    bobs and pulses, two tiny leaves circling it.  Additive 770/80."""
    SZ = 64; cx, cy = 30.0, 32.0; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); out = []
    for i in range(n):
        t = i / float(n); bob = 1.2 * math.sin(2 * math.pi * t); pulse = 0.78 + 0.22 * math.sin(2 * math.pi * t + 0.8)
        pf = _tame_paw_field(xx, yy, cx, cy + bob, 0.70)
        rim = np.clip(_tame_paw_field(xx, yy, cx, cy + bob, 0.83) - pf, 0, 1)
        halo = 0.28 * np.exp(-((xx - cx) ** 2 + (yy - cy - bob) ** 2) / 60.0)
        g = np.clip(pulse * (0.95 * pf + 0.7 * rim + halo), 0, 1); amb = np.clip(rim * 1.4, 0, 1)
        r = (80 + 175 * amb) * g; gg = (215 - 20 * amb) * g; b = (70 - 40 * amb) * g
        im = Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(gg, 0, 255), np.clip(b, 0, 255), np.where(g > 0.04, 255, 0)]).astype(np.uint8), "RGBA")
        dr = ImageDraw.Draw(im)
        for k in range(2):
            a = 2 * math.pi * (t + 0.5 * k); x = cx + 11.0 * math.cos(a); y = cy + bob + 4.5 * math.sin(a)
            _tame_leaf(dr, x, y, a + 1.57, 4.2, (50, 185, 45, 255))
        out.append(im)
    return out


def tame_mark(n=8):
    """Tame Animal (0xC9) v3 success mark (2026-10-19; user: 'needs a smoother fade out'): replaces the v2 mark, which
    re-used the overlay loop at FULL brightness for all 8 frames of Dominate's 'mark' slot (f8 6) and then vanished.
    Same canvas / anchor as the overlay (64x64, paw centred at (32, 32), xs -32 / ys -44 = Dominate's eye spot):
    the glowing green paw pops in, then rises 3 px, swells a little and fades out smoothly over the 8 frames while
    its two leaves drift outward and fade.  Additive 770/80."""
    SZ = 64; yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32); out = []
    env = [0.60, 1.00, 0.92, 0.76, 0.56, 0.36, 0.19, 0.07]
    for i in range(n):
        t = i / float(n - 1); e = env[i] if i < len(env) else 0.0
        cx, cy = 32.0, 32.0 - 3.0 * t; sc = 0.70 + 0.12 * t
        pf = _tame_paw_field(xx, yy, cx, cy, sc)
        rim = np.clip(_tame_paw_field(xx, yy, cx, cy, sc + 0.13) - pf, 0, 1)
        halo = (0.30 + 0.25 * t) * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (60.0 + 90.0 * t))
        g = np.clip(e * (0.95 * pf + 0.7 * rim + halo), 0, 1); amb = np.clip(rim * 1.4, 0, 1)
        r = (80 + 175 * amb) * g; gg = (215 - 20 * amb) * g; b = (70 - 40 * amb) * g
        im = Image.fromarray(np.dstack([np.clip(r, 0, 255), np.clip(gg, 0, 255), np.clip(b, 0, 255), np.where(g > 0.03, 255, 0)]).astype(np.uint8), "RGBA")
        dr = ImageDraw.Draw(im)
        for k in range(2):
            a = 2 * math.pi * (0.15 * i / n + 0.5 * k) + 0.4; R = 11.0 + 9.0 * t
            x = cx + R * math.cos(a); y = cy + 0.45 * R * math.sin(a) - 4.0 * t; c = e * 1.05
            if c > 0.06: _tame_leaf(dr, x, y, a + 1.57, 4.2, (int(50 * c), int(185 * c), int(45 * c), 255))
        out.append(im)
    return out


def tame_badge(n=12):
    """Tamed (status 0xCA) v3 overhead badge (2026-10-19; user: 'needs a gfx that stays above the unit's head during
    combat, like the Charmed pendulum / Dominated eye - maybe a green bear-paw print'): a SOLID green bear paw (the
    v2 overlay was a faint additive glow that washed out on grass and sand).  Drawn like COMBAT.ILB 130 (the
    Dominated eye): 64x64 canvas, glyph centred at (32, 32) -> record 212 xs -32 / ys -44 puts it where the eye sits.
    Opaque keyed sprite (256): a broad main pad and five separate toes with small claw points, each element with its
    own 1-px dark-green outline (so the toes read as separate), top-left light / bottom-right shade; the 12-frame
    loop pulses the highlight and sends a small glint across the pad - no positional jitter.  Hard alpha."""
    S = 8; SZ = 64; out = []
    def mask(draw):
        m = Image.new("L", (SZ * S, SZ * S), 0); draw(ImageDraw.Draw(m), lambda x, y: ((32 + x) * S, (32 + y) * S))
        return np.asarray(m.resize((SZ, SZ), Image.BOX), np.float32) / 255.0 > 0.5
    def dil(m):
        o = m.copy(); o[1:, :] |= m[:-1, :]; o[:-1, :] |= m[1:, :]; o[:, 1:] |= m[:, :-1]; o[:, :-1] |= m[:, 1:]
        o[1:, 1:] |= m[:-1, :-1]; o[:-1, :-1] |= m[1:, 1:]; o[1:, :-1] |= m[:-1, 1:]; o[:-1, 1:] |= m[1:, :-1]
        return o
    def pad(d, P):
        d.ellipse([P(-8.0, -1.5), P(8.0, 9.5)], fill=255)
        d.ellipse([P(-2.2, 7.4), P(2.2, 11.0)], fill=0)                                           # heel dimple
    elems = [mask(pad)]
    TOES = ((-9.6, -4.0, 2.4, 2.7), (-5.4, -8.6, 2.6, 2.9), (0.0, -10.2, 2.7, 3.0), (5.4, -8.6, 2.6, 2.9), (9.6, -4.0, 2.4, 2.7))
    claws = []
    for dx, dy, rx, ry in TOES:
        elems.append(mask(lambda d, P, dx=dx, dy=dy, rx=rx, ry=ry: d.ellipse([P(dx - rx, dy - ry), P(dx + rx, dy + ry)], fill=255)))
        L = math.hypot(dx, dy - 2.0); ux, uy = dx / L, (dy - 2.0) / L
        claws.append((int(round(32 + dx + ux * (ry + 1.2))), int(round(32 + dy + uy * (ry + 1.2)))))
    fill = np.zeros((SZ, SZ), bool)
    for m in elems: fill |= m
    edge = np.zeros((SZ, SZ), bool)
    for m in elems: edge |= dil(m) & ~m
    for k, a in enumerate(elems):                       # touching elements: keep a dark seam between them
        for b in elems[k + 1:]: edge |= dil(a) & b
    fill &= ~edge
    yy, xx = np.mgrid[0:SZ, 0:SZ].astype(np.float32)
    light = np.clip(0.5 + ((32 - xx) * 0.6 + (28 - yy) * 0.8) / 16.0, 0, 1)
    base = np.array([60, 176, 52], np.float32); hi = np.array([160, 240, 118], np.float32); lo = np.array([26, 108, 28], np.float32)
    pady = [(int(x), int(y)) for y, x in zip(*np.nonzero(elems[0] & fill)) if 31 <= y <= 34]
    pady.sort()
    for i in range(n):
        t = i / float(n); pulse = 0.5 + 0.5 * math.sin(2 * math.pi * t)
        L = np.clip(light * (0.80 + 0.30 * pulse), 0, 1)[..., None]
        col = np.where(L > 0.5, base + (hi - base) * (L - 0.5) * 2, lo + (base - lo) * L * 2)
        rgb = np.zeros((SZ, SZ, 3), np.uint8); a = np.zeros((SZ, SZ), np.uint8)
        rgb[fill] = np.clip(col[fill], 0, 255).astype(np.uint8); a[fill] = 255
        rgb[edge] = (14, 52, 16); a[edge] = 255
        for cx_, cy_ in claws:
            if 0 <= cx_ < SZ and 0 <= cy_ < SZ: rgb[cy_, cx_] = (14, 52, 16); a[cy_, cx_] = 255
        if pady:
            gx, gy = pady[int(t * len(pady)) % len(pady)]
            for ox, oy, c in ((0, 0, 255), (1, 0, 210), (-1, 0, 210), (0, 1, 210), (0, -1, 210)):
                X, Y = gx + ox, gy + oy
                if 0 <= X < SZ and 0 <= Y < SZ and fill[Y, X]: rgb[Y, X] = (c, 255, c)
        out.append(Image.fromarray(np.dstack([rgb, a]), "RGBA"))
    return out


def _tame_dim(im, k):
    """Scale an additive RGBA frame's colour by k (alpha re-keyed on what is still visible)."""
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    rgb = a[..., :3] * k
    vis = (rgb.max(axis=2) > 6) & (a[..., 3] > 0)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.where(vis, 255, 0)]).astype(np.uint8), "RGBA")


def tame_hitfade(n=10):
    """Tame Animal (0xC9) v4 hit loop (2026-10-19; user: 'the hit gfx ends too abruptly - have it fade out'): the
    record-211 slots f8 2 / f8 5 played the twinkle's peak loop (frames 12-16) twice at full strength and then cut.
    Same 10 frames (timing kept), the second pass fading out: envelope 1,1,1,1,1, .80,.58,.38,.20,.07.  770/80."""
    tw = tame_twinkle(); env = [1, 1, 1, 1, 1, 0.80, 0.58, 0.38, 0.20, 0.07]
    return [_tame_dim(tw[12 + (i % 5)], env[i]) for i in range(n)]


def tame_castfade(n=4):
    """Tame Animal (0xC9) v4: the cast slot f8 1 ended on the gathering frame 8 at ~70 % strength; its last four
    frames are now twinkle frames 5-8 fading out (.75, .50, .28, .10)."""
    tw = tame_twinkle(); env = [0.75, 0.50, 0.28, 0.10]
    return [_tame_dim(tw[5 + i], env[i]) for i in range(n)]


TAME_PAW_MASK = "tamed_paw_user_mask.png"      # art import export/tamed.jpg traced (ink < 128 -> white), 214x320


def _tame_paw7(glow=1.0, BH=20.0):
    """Tame Animal v5 paw (2026-10-19; user: 'use the new image I uploaded (art import export/tamed.jpg); BLACK with a
    GREEN GLOW around it, maybe partial transparency; a little smaller than the current one'): the user's bear-paw
    print TRACED (TAME_PAW_MASK) at BH px tall x ~14 px wide (the v3 badge was ~27 x 24 px), centred at (32, 32) of a
    64x64 canvas - the Dominated eye's anchor (xs -32 / ys -44).  Near-black body; the gaps between the toes / claw
    marks / pad stay SEE-THROUGH (the glow only hugs the paw's outer outline = the shape closed by ~2 px, so the print
    reads); outside it a soft green glow ring, bright leaf green at the edge fading to deep green, alpha falling off
    (dithered at game scale).  Drawn ALPHA 258 with blendValue < 100 = the whole sprite partly see-through.
    glow scales the ring (the overhead pulse)."""
    from PIL import ImageFilter
    SS = 8; SZ = 64
    m = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), TAME_PAW_MASK)).convert("L")
    h = int(round(BH * SS)); w = int(round(m.width * h / m.height))
    big = Image.new("L", (SZ * SS, SZ * SS), 0)
    big.paste(m.resize((w, h), Image.LANCZOS), (int(32 * SS - w / 2), int(32 * SS - h / 2)))
    hull = big.filter(ImageFilter.MaxFilter(2 * 2 * SS + 1)).filter(ImageFilter.MinFilter(2 * 2 * SS + 1))
    cov = np.asarray(big.resize((SZ, SZ), Image.BOX), np.float32) / 255.0
    hcov = np.asarray(hull.resize((SZ, SZ), Image.BOX), np.float32) / 255.0
    body = cov >= 0.5; inside = hcov >= 0.5
    sil = Image.fromarray((hcov * 255).astype(np.uint8), "L")
    g1 = np.asarray(sil.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0
    g2 = np.asarray(sil.filter(ImageFilter.GaussianBlur(2.7)), np.float32) / 255.0
    gl = np.clip((0.8 * g1 + 0.8 * g2) * 2.1 * glow, 0, 1)
    ring = ~inside & (gl > 0.05)
    t = np.clip(gl, 0, 1) ** 0.8
    lo = np.array([24, 110, 30], np.float32); hi = np.array([125, 252, 105], np.float32)
    col = lo + (hi - lo) * t[..., None]
    rgb = np.zeros((SZ, SZ, 3), np.float32); a = np.zeros((SZ, SZ), np.float32)
    al = np.clip(gl * 1.7, 0, 1); al[al < 0.22] = 0                 # no lone speckles far out
    rgb[ring] = col[ring]; a[ring] = al[ring]
    rgb[body] = np.array([8, 16, 10], np.float32); a[body] = 1.0
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(a * 255, 0, 255)]).astype(np.uint8), "RGBA")


def tame_badge7(n=12):
    """Tamed (0xCA) v5 overhead badge (record 212): the traced black paw, its green glow gently pulsing (0.82..1.0)
    over the 12-frame loop; ALPHA 258/88 (partly transparent).  Frame 0 = the mean glow (also the cast mark's hold)."""
    return [_tame_paw7(0.91 + 0.09 * math.cos(2 * math.pi * i / n)) for i in range(n)]


def tame_mark7():
    """Tame Animal (0xC9) v5 cast mark (record 211 f8 6, like Dominate's eye in COMBAT.ILB 130): the SAME paw sprite
    as the overhead badge at the same anchor, so on success the Tamed overlay continues it seamlessly ('sticks').
    One frame (the badge's mean glow); the fade in / out is done with per-record blend values (separate rows), so
    the colours stay identical and only the opacity ramps."""
    return [_tame_paw7(0.91)]


def flaming_skull(n=8):
    """Hurl Flaming Skull (ability 0xCC, 2026-10-19) slot 0: the flying projectile for the kind-2 (Hurl Boulder) arc.
    Source art = the vanilla flaming-skull hit icon COMBAT.ILB #116 ('HitIcon.BMP', 46x45, the Undead skull used by
    the Skull Thrower) centred on Hurl Boulder's 64x64 BALLS canvas (anchor -31/-33).  8-frame loop: the skull stays
    put, its flame tongue flickers (fire pixels brightness 0.78..1.12 with a phase that runs up the flame) and a few
    ember sparks drift off the tail.  Solid keyed sprite (256/0, like the Death/Fire stones)."""
    import sys as _s
    _s.path.insert(0, os.path.join(HERE, "..", "modding tools"))
    from aowxlib import ilb as _ilb
    lib = _ilb.read(os.path.join(GAME, "Images", "Combat.ILB"))
    img = next(i for i in lib.images if i.id == 116)
    w, h, rows = _ilb.decode_record(lib, img.parts[0])
    src = Image.new("RGBA", (w, h), (0, 0, 0, 0)); src.putdata([p for row in rows for p in row])
    W = H = 64; ox, oy = (W - w) // 2, (H - h) // 2
    sp = src.load(); out = []
    rnd = random.Random(4120)
    sparks = [(rnd.uniform(0.55, 0.95), rnd.uniform(0.05, 0.45), rnd.random()) for _ in range(6)]
    for i in range(n):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); px = im.load()
        ph = 2 * math.pi * i / n
        for y in range(h):
            for x in range(w):
                r, g, b, a = sp[x, y]
                if not a: continue
                fire = r > 150 and r > g + 25 and b < 140          # orange / yellow / red flame pixels
                if fire:
                    f = 0.95 + 0.17 * math.sin(ph + (h - y) * 0.35 + x * 0.12)
                    r, g, b = min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f))
                px[ox + x, oy + y] = (r, g, b, a)
        dr = ImageDraw.Draw(im)
        for (fx, fy, p0) in sparks:                                # embers drifting up-right off the flame tail
            t = (i / n + p0) % 1.0
            x = ox + fx * w + 6 * t; y = oy + fy * h - 8 * t
            if 0 <= x < W and 0 <= y < H and t < 0.85:
                c = (255, int(200 - 120 * t), int(60 - 50 * t), 255)
                dr.point((x, y), fill=c)
        out.append(im)
    return out


def hurl_skull(n=12):
    """Hurl Skull (ability 0xCC) v2 slot 0 (2026-10-19, user: 'the gfx is really bad - start fresh'): a fresh painted
    flaming skull for Hurl Boulder's kind-2 lob (64x64 BALLS canvas, anchor -31/-33).  12-frame loop: the skull TUMBLES
    (one full turn per loop, rotated in the picture plane) inside a mane of fire that always streams UP (flames rise
    whatever the flight direction) and flickers, with embers flaking off.  Skull ~17 px: bone with a warm top light and
    a dark rim, black sockets lit by ember-red pupils, a nasal notch and a toothed jaw.  Painted at 6x, shrunk with a
    hard alpha cut -> solid keyed sprite (256/0, like the other solid projectiles)."""
    S = 6; W = H = 64; cx, cy = 31.0, 34.0
    rnd = random.Random(4720)
    embers = [(rnd.uniform(-5, 5), rnd.uniform(0, 1), rnd.uniform(0.6, 1.4)) for _ in range(9)]
    tongues = [(rnd.uniform(-6.5, 6.5), rnd.uniform(13, 21), rnd.uniform(0, 6.28), rnd.uniform(2.4, 3.8)) for _ in range(8)]

    def skull_layer(ang):
        L = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
        k = S
        def E(x0, y0, x1, y1, c): d.ellipse([(cx + x0) * k, (cy + y0) * k, (cx + x1) * k, (cy + y1) * k], fill=c)
        def P(pts, c): d.polygon([((cx + x) * k, (cy + y) * k) for x, y in pts], fill=c)
        rim, bone, lit, shade = (38, 22, 16, 255), (214, 200, 168, 255), (246, 238, 214, 255), (164, 146, 116, 255)
        E(-8.6, -9.4, 8.6, 6.0, rim)                     # cranium outline
        P([(-6.4, 2.0), (6.4, 2.0), (5.0, 8.6), (-5.0, 8.6)], rim)      # jaw outline
        E(-7.6, -8.4, 7.6, 5.0, bone)
        P([(-5.4, 2.4), (5.4, 2.4), (4.2, 7.6), (-4.2, 7.6)], bone)
        E(-6.6, -8.0, 3.6, -1.6, lit)                    # top-left light
        E(-1.5, -8.6, 2.2, -5.0, (255, 250, 236, 255))
        E(2.6, -3.0, 7.4, 4.6, shade)                    # right-cheek shade
        E(-6.0, -2.4, -0.9, 2.6, rim); E(0.9, -2.4, 6.0, 2.6, rim)      # sockets
        E(-4.4, -1.2, -2.6, 0.8, (255, 70, 20, 255)); E(2.6, -1.2, 4.4, 0.8, (255, 70, 20, 255))  # ember pupils
        E(-3.9, -0.8, -3.1, 0.2, (255, 220, 120, 255)); E(3.1, -0.8, 3.9, 0.2, (255, 220, 120, 255))
        P([(0, 2.2), (-1.2, 4.4), (1.2, 4.4)], rim)       # nose
        d.rectangle([(cx - 4.0) * k, (cy + 5.0) * k, (cx + 4.0) * k, (cy + 5.6) * k], fill=rim)   # teeth line
        for t in range(-3, 4):
            x = cx + t * 1.15
            d.line([(x * k, (cy + 5.0) * k), (x * k, (cy + 7.4) * k)], fill=rim, width=max(1, int(0.45 * k)))
        return L.rotate(ang, resample=Image.BICUBIC, center=(cx * k, cy * k))

    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        F = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(F); k = S
        for layer, (col, sc) in enumerate((((150, 18, 8), 1.0), ((235, 80, 16), 0.78), ((255, 170, 40), 0.56), ((255, 236, 150), 0.32))):
            for (ox, ln, p0, wd) in tongues:
                fl = 0.75 + 0.25 * math.sin(ph * 2 + p0)
                L = ln * sc * fl + 3.0; w = wd * (0.9 + 0.5 * sc)
                sway = 1.6 * math.sin(ph + p0)
                base = (cx + ox * (0.55 + 0.45 * sc), cy - 1.0)
                tip = (cx + ox * 0.35 + sway, cy - 1.0 - L)
                pts = [(base[0] - w, base[1] + 2.0), (base[0] + w, base[1] + 2.0),
                       (base[0] + w * 0.6 + sway * 0.4, base[1] - L * 0.5), (tip[0], tip[1]),
                       (base[0] - w * 0.6 + sway * 0.4, base[1] - L * 0.5)]
                d.polygon([(x * k, y * k) for x, y in pts], fill=col + (255,))
            d.ellipse([(cx - 9.5 * sc - 1) * k, (cy - 7.5 * sc - 2) * k, (cx + 9.5 * sc + 1) * k, (cy + 6.5 * sc + 1) * k], fill=col + (255,))
        im = Image.alpha_composite(F, skull_layer(-360.0 * i / n))
        small = im.resize((W, H), Image.LANCZOS)
        px = small.load()
        for y in range(H):
            for x in range(W):
                r, g, b, a = px[x, y]
                px[x, y] = (r, g, b, 255) if a >= 110 else (0, 0, 0, 0)
        dr = ImageDraw.Draw(small)
        for (ex, e0, sp) in embers:
            t = (i / n * sp + e0) % 1.0
            x = cx + ex + 2.0 * math.sin(ph + e0 * 6); y = cy - 12 - 16 * t
            if t < 0.8:
                dr.point((round(x), round(y)), fill=(255, int(230 - 150 * t), int(90 - 80 * t), 255))
        out.append(small)
    return out


def black_javelin(n=24):
    """Shoot Black Javelin (ability 0xCD) v3 (2026-10-19, user: 'add a slight black glow/tail'): the VANILLA black
    javelin sprites (TCOMBAT\OBJECTS\ARROW.ILB 300-323, 64x64, frame k flies 15*k deg clockwise from north = the
    engine's kind-1 direction index) kept pixel-for-pixel on top of (1) a soft near-black halo hugging the javelin
    (2 px, alpha 215 -> 95, dithered by rec_for) and (2) a short smoky tail (~17 px) streaming back from the
    fletching, tapering and fading out with a few drifting soot specks.  Same 64x64 canvas / anchor (-32 / -32) as
    vanilla, so record 215's 24 direction slots only change their image ids.  Solid keyed sprite (256/0)."""
    import sys as _s
    _s.path.insert(0, os.path.join(HERE, "..", "modding tools"))
    from aowxlib import ilb as _ilb
    lib = _ilb.read(os.path.join(GAME, "Images", "TCombat", "Objects", "Arrow.ILB"))
    src = {}
    for img in lib.images:
        if 300 <= img.id < 300 + n:
            w, h, rows = _ilb.decode_record(lib, img.parts[0])
            s = Image.new("RGBA", (w, h), (0, 0, 0, 0)); s.putdata([p for row in rows for p in row]); src[img.id] = s
    out = []
    SMOKE = (16, 10, 22)
    for k in range(n):
        s = src[300 + k]; W, H = s.size; sp = s.load()
        th = math.radians(15 * k); dx, dy = math.sin(th), -math.cos(th)      # flight direction (screen, y down)
        pts = [(x, y) for y in range(H) for x in range(W) if sp[x, y][3]]
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        back = min(pts, key=lambda p: (p[0] - cx) * dx + (p[1] - cy) * dy)  # fletching end
        bproj = (back[0] - cx) * dx + (back[1] - cy) * dy
        acc = [[0.0] * W for _ in range(H)]
        mask = set(pts)
        for (x, y) in pts:                                                  # halo: distance-weighted dark glow
            for oy in range(-2, 3):
                for ox in range(-2, 3):
                    X, Y = x + ox, y + oy
                    if 0 <= X < W and 0 <= Y < H and (X, Y) not in mask:
                        d = math.hypot(ox, oy)
                        if d <= 2.3:
                            acc[Y][X] = max(acc[Y][X], 215 if d <= 1.0 else 160 if d <= 1.5 else 95)
        rnd = random.Random(5300 + k)
        L = 17.0
        for step in range(int(L * 3)):                                       # tail: tapering smoky ribbon
            t = step / (L * 3.0)
            px_, py_ = cx + dx * (bproj - t * L), cy + dy * (bproj - t * L)
            wob = math.sin(t * 7.0 + k) * 1.2 * t
            px_ += -dy * wob; py_ += dx * wob
            rad = 1.8 + 1.6 * t
            a0 = 235 * (1.0 - t) ** 1.1
            for oy in range(-3, 4):
                for ox in range(-3, 4):
                    X, Y = int(round(px_ + ox)), int(round(py_ + oy))
                    if 0 <= X < W and 0 <= Y < H and (X, Y) not in mask:
                        d = math.hypot(X - px_, Y - py_)
                        if d <= rad:
                            acc[Y][X] = max(acc[Y][X], a0 * (1.0 - 0.55 * d / rad))
        for _ in range(4):                                                   # soot specks drifting off the tail
            t = rnd.uniform(0.45, 1.05)
            X = int(round(cx + dx * (bproj - t * L) + rnd.uniform(-3, 3))); Y = int(round(cy + dy * (bproj - t * L) + rnd.uniform(-3, 3)))
            if 0 <= X < W and 0 <= Y < H and (X, Y) not in mask: acc[Y][X] = max(acc[Y][X], 110 * (1.1 - t))
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); px = im.load()
        for Y in range(H):
            for X in range(W):
                if acc[Y][X] > 8: px[X, Y] = SMOKE + (int(min(255, acc[Y][X])),)
        im.alpha_composite(s)
        out.append(im)
    return out



def _aowx_ilb_frames(rel, ids):
    """Decode vanilla ILB images (RGBA, key -> alpha 0) with the modding-tools reader."""
    import sys as _s
    p = os.path.join(HERE, "..", "modding tools")
    if p not in _s.path: _s.path.insert(0, p)
    from aowxlib import ilb as _ilb
    lib = _ilb.read(os.path.join(GAME, "Images", rel)); out = {}
    for img in lib.images:
        if img.id in ids:
            w, h, rows = _ilb.decode_record(lib, img.parts[0])
            s = Image.new("RGBA", (w, h), (0, 0, 0, 0)); s.putdata([q for row in rows for q in row]); out[img.id] = s
    return [out[i] for i in ids]


def black_javelin2(n=24):
    """Shoot Black Javelin (0xCD) v4 (2026-10-19, user: 'did the projectile change colour? I thought it was black
    before'): yes - vanilla ARROW.ILB 300-323 are drawn in MULTIPLY mode (drawMode 0x402 = 1026, blend 100, white
    key): the sprite DARKENS the ground, so its black core reads as a black javelin and its light-grey shading almost
    vanishes.  v3 re-encoded the frames as SOLID (256), so the light greys painted over the ground -> a 'plain' grey
    javelin.  v4 = the vanilla pixels unchanged, drawn 1026 like vanilla, plus the dark glow / smoky tail expressed as
    multiply greys (white = no change, grey = darken): a 2-px halo and a ~17 px tapering soot tail behind the fletching
    with drifting specks.  Same 64x64 canvas / anchor / ids (DualDF 7430-7453) -> no pfs change."""
    src = _aowx_ilb_frames(os.path.join("TCombat", "Objects", "Arrow.ILB"), list(range(300, 300 + n)))
    out = []
    for k in range(n):
        s = src[k]; W, H = s.size; sp = s.load()
        th = math.radians(15 * k); dx, dy = math.sin(th), -math.cos(th)
        pts = [(x, y) for y in range(H) for x in range(W) if sp[x, y][3]]
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        back = min(pts, key=lambda p: (p[0] - cx) * dx + (p[1] - cy) * dy)
        bproj = (back[0] - cx) * dx + (back[1] - cy) * dy
        dark = [[0.0] * W for _ in range(H)]                       # 0..1 darkening amount
        mask = set(pts)
        for (x, y) in pts:
            for oy in range(-2, 3):
                for ox in range(-2, 3):
                    X, Y = x + ox, y + oy
                    if 0 <= X < W and 0 <= Y < H and (X, Y) not in mask:
                        d = math.hypot(ox, oy)
                        if d <= 2.3: dark[Y][X] = max(dark[Y][X], 0.40 if d <= 1.0 else 0.26 if d <= 1.5 else 0.13)
        rnd = random.Random(5300 + k); L = 17.0
        for step in range(int(L * 3)):
            t = step / (L * 3.0)
            px_, py_ = cx + dx * (bproj - t * L), cy + dy * (bproj - t * L)
            wob = math.sin(t * 7.0 + k) * 1.2 * t
            px_ += -dy * wob; py_ += dx * wob
            rad = 1.8 + 1.6 * t; a0 = 0.62 * (1.0 - t) ** 1.1
            for oy in range(-3, 4):
                for ox in range(-3, 4):
                    X, Y = int(round(px_ + ox)), int(round(py_ + oy))
                    if 0 <= X < W and 0 <= Y < H and (X, Y) not in mask:
                        d = math.hypot(X - px_, Y - py_)
                        if d <= rad: dark[Y][X] = max(dark[Y][X], a0 * (1.0 - 0.55 * d / rad))
        for _ in range(5):
            t = rnd.uniform(0.45, 1.05)
            X = int(round(cx + dx * (bproj - t * L) + rnd.uniform(-3, 3))); Y = int(round(cy + dy * (bproj - t * L) + rnd.uniform(-3, 3)))
            if 0 <= X < W and 0 <= Y < H and (X, Y) not in mask: dark[Y][X] = max(dark[Y][X], 0.4 * (1.1 - t))
        for (x, y) in pts:                                         # the sprite's own light rim sits INSIDE the glow:
            nb = [dark[y + oy][x + ox] for oy in (-1, 0, 1) for ox in (-1, 0, 1)   # multiply it by the neighbouring
                  if 0 <= x + ox < W and 0 <= y + oy < H]                         # darkening so no bright ring shows
            dark[y][x] = max(nb) * 0.9
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); px = im.load()
        for Y in range(H):
            for X in range(W):
                f = 1.0 - dark[Y][X]
                if (X, Y) in mask:
                    r, g, b, a = sp[X, Y]
                    px[X, Y] = (int(r * f), int(g * f), int(b * f), 255)
                elif dark[Y][X] > 0.04:
                    v = int(round(255 * f))
                    px[X, Y] = (v, v, min(255, v + 6), 255)          # multiply grey (faint cold tint)
        out.append(im)
    return out


def hurl_skull3(n=12):
    """Hurl Skull (0xCC) v3 slot 0 (2026-10-19, user: 'not gritty enough; smaller = the Hurl Boulder projectile size;
    whitish-grey skull, black eyes/mouth, black and red fire glow; evil, dark, gritty'): Hurl Boulder's BALLS.ILB
    projectile is ~10 x 9 px on its 64x64 canvas (centre 31/33), so the skull is ~9 px wide / 11 px tall incl. the jaw,
    same canvas / anchor / ids (DualDF 7410-7421).  12-frame loop: the skull TUMBLES (one turn per loop); cracked,
    pitted grey-white bone with grime, pitch-black sockets / nasal hole / teeth gaps; around it a ragged fire of BLACK
    smoke tongues and CRIMSON / blood-red flame streaming up, smouldering dark-red embers.  Solid keyed sprite (256):
    the skull opaque, smoke / flame edges alpha-dithered by rec_for (gritty, broken edges)."""
    S = 8; W = H = 64; cx, cy = 31.0, 33.0
    rnd = random.Random(4721)
    tongues = [(rnd.uniform(-3.4, 3.4), rnd.uniform(7.0, 12.0), rnd.uniform(0, 6.28), rnd.uniform(1.3, 2.1)) for _ in range(9)]
    smoke = [(rnd.uniform(-4.5, 4.5), rnd.uniform(9.0, 15.0), rnd.uniform(0, 6.28), rnd.uniform(1.6, 2.6)) for _ in range(7)]
    embers = [(rnd.uniform(-4, 4), rnd.uniform(0, 1), rnd.uniform(0.6, 1.3)) for _ in range(7)]
    grime = np.random.RandomState(4722).rand(H, W)

    def skull(ang):
        L = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(L); k = S
        def E(x0, y0, x1, y1, c): d.ellipse([(cx + x0) * k, (cy + y0) * k, (cx + x1) * k, (cy + y1) * k], fill=c)
        def P(pts, c): d.polygon([((cx + x) * k, (cy + y) * k) for x, y in pts], fill=c)
        def Ln(pts, c, w): d.line([((cx + x) * k, (cy + y) * k) for x, y in pts], fill=c, width=max(1, int(w * k)))
        rim, bone, lit, shade, blk = (14, 10, 10, 255), (196, 192, 184, 255), (232, 230, 222, 255), (128, 122, 116, 255), (6, 4, 4, 255)
        E(-5.4, -6.6, 5.4, 3.4, rim)                                         # cranium + rim
        P([(-3.9, 1.2), (3.9, 1.2), (3.1, 6.2), (-3.1, 6.2)], rim)           # jaw + rim
        E(-4.8, -6.0, 4.8, 2.8, bone)
        P([(-3.3, 1.6), (3.3, 1.6), (2.6, 5.6), (-2.6, 5.6)], bone)
        E(-3.8, -5.0, 1.6, -1.6, lit)                                        # top-left light
        E(1.4, -2.4, 4.2, 2.6, shade); P([(0.6, 3.0), (3.0, 1.8), (2.3, 4.8), (0.4, 4.8)], shade)
        E(-4.0, -2.2, -0.4, 1.5, blk); E(0.4, -2.2, 4.0, 1.5, blk)             # deep black sockets
        P([(-3.6, -2.1), (-0.3, -1.5), (-0.6, -1.0), (-3.6, -1.3)], rim); P([(3.6, -2.1), (0.3, -1.5), (0.6, -1.0), (3.6, -1.3)], rim)   # brow ridge
        P([(0, 1.6), (-1.0, 3.2), (1.0, 3.2)], blk)                           # nasal hole
        d.rectangle([(cx - 2.8) * k, (cy + 3.7) * k, (cx + 2.8) * k, (cy + 4.4) * k], fill=blk)   # mouth slit
        for t in (-1.8, -0.6, 0.6, 1.8):
            Ln([(t, 3.7), (t, 5.4)], blk, 0.42)                               # teeth gaps
        Ln([(-1.2, -5.2), (-0.4, -3.6), (-1.0, -2.6)], rim, 0.32)             # cracks
        Ln([(2.0, -4.6), (1.2, -3.4), (1.9, -2.5)], rim, 0.28)
        return L.rotate(ang, resample=Image.BICUBIC, center=(cx * k, cy * k))

    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        F = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(F); k = S
        def tongue(ox, ln, p0, wd, col, sc, a):
            fl = 0.72 + 0.28 * math.sin(ph * 2 + p0)
            L = ln * sc * fl + 2.0; w = wd * (0.85 + 0.4 * sc)
            sway = 1.3 * math.sin(ph + p0)
            base = (cx + ox * (0.6 + 0.4 * sc), cy - 0.5)
            tip = (cx + ox * 0.35 + sway, cy - 0.5 - L)
            pts = [(base[0] - w, base[1] + 2.4), (base[0] + w, base[1] + 2.4),
                   (base[0] + w * 0.55 + sway * 0.4, base[1] - L * 0.5), tip, (base[0] - w * 0.55 + sway * 0.4, base[1] - L * 0.5)]
            d.polygon([(x * k, y * k) for x, y in pts], fill=col + (a,))
        for (ox, ln, p0, wd) in smoke:                                        # black smoke, outermost, ragged
            tongue(ox, ln, p0, wd, (12, 8, 8), 1.0, 175)
        d.ellipse([(cx - 6.6) * k, (cy - 6.4) * k, (cx + 6.6) * k, (cy + 5.6) * k], fill=(18, 6, 6, 190))
        for col, sc, a in (((92, 6, 6), 0.95, 235), ((150, 12, 10), 0.75, 250), ((196, 24, 14), 0.52, 255)):
            for (ox, ln, p0, wd) in tongues:
                tongue(ox, ln, p0, wd, col, sc, a)
            d.ellipse([(cx - 5.8 * sc - 0.4) * k, (cy - 5.6 * sc - 0.6) * k, (cx + 5.8 * sc + 0.4) * k, (cy + 4.6 * sc + 0.4) * k], fill=col + (a,))
        F = F.filter(ImageFilter.GaussianBlur(S * 0.35))
        sk = skull(26.0 * math.sin(ph) + 8.0 * math.sin(2 * ph))              # v3b: a rocking tumble keeps the face legible
        glow = Image.new("RGBA", F.size, (0, 0, 0, 0)); glow.paste((170, 14, 8, 255), mask=sk.split()[3].filter(ImageFilter.MaxFilter(2 * S + 1)))
        F = Image.alpha_composite(F, glow.filter(ImageFilter.GaussianBlur(S * 0.6)))   # crimson rim glow hugging the skull
        im = Image.alpha_composite(F, sk)
        small = np.array(im.resize((W, H), Image.LANCZOS)).astype(np.float32)
        a = small[:, :, 3]
        opaque = a > 200
        lum = small[:, :, :3].mean(2)
        bonepx = opaque & (lum > 95)
        g = (grime - 0.5) * 30.0                                              # gritty grime on the bone
        for c in range(3): small[:, :, c] = np.where(bonepx, small[:, :, c] + g, small[:, :, c])
        pit = bonepx & (grime > 0.93)                                         # pits / specks
        for c in range(3): small[:, :, c] = np.where(pit, small[:, :, c] * 0.45, small[:, :, c])
        small[:, :, 3] = np.where(opaque, 255, np.clip(a * 1.15, 0, 255))
        img = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), "RGBA")
        dr = ImageDraw.Draw(img)
        for (ex, e0, sp) in embers:                                           # smouldering embers rising
            t = (i / n * sp + e0) % 1.0
            x = cx + ex + 1.6 * math.sin(ph + e0 * 6); y = cy - 7 - 11 * t
            if t < 0.85:
                dr.point((round(x), round(y)), fill=(int(225 - 90 * t), int(30 - 20 * t), 10, 255))
        out.append(img)
    return out


_DARK_EXPL = []
EXPL_SCALE = 240.0 / 274.0                     # DualDF sprites >= ~256 px wide crashed before (implosion notes): 274x258 -> 240x226
EXPL_BLEND = [90] * 21 + [86, 81, 72, 63, 54, 45, 36, 27, 18]   # vanilla's 100,...,95..20 fade, scaled to a 90 % peak


def dark_explosion():
    """Hurl Skull (0xCC) v3 impact (slot 2): Self Destruct's EXPLBIG.ILB 0-29 re-graded EVIL.  Vanilla draws it in
    bmBrighten (514: dark pixels add nothing), which can never show black - so v3 draws in bmAlpha (258, blend = the
    vanilla per-frame fade x0.9) and builds the colour + coverage from the vanilla luminance: the hot core = crimson /
    blood red (no orange or yellow, the hottest stops at a dark red-orange), the mid body = deep blood red into
    charcoal, the outer glow = a ragged black-smoke haze (coverage fades with luminance -> Bayer-dithered by rec_for:
    gritty, broken edges).  Scaled to 240x226 (the >=256-px-wide crash) - record 214 slot 2's anchor scales with it."""
    if _DARK_EXPL: return _DARK_EXPL
    src = _aowx_ilb_frames(os.path.join("Effects", "ExplBig.ILB"), list(range(30)))
    xs = np.array([0, 25, 60, 110, 170, 230, 255], np.float32)
    R = np.array([6, 14, 40, 105, 165, 205, 220], np.float32)
    G = np.array([4, 8, 8, 10, 18, 40, 62], np.float32)
    B = np.array([4, 8, 8, 9, 12, 24, 36], np.float32)
    AL = np.array([0, 60, 150, 230, 255, 255, 255], np.float32)
    grit = np.random.RandomState(4790).rand(258, 274).astype(np.float32)
    for s in src:
        a = np.array(s).astype(np.float32)
        lum = a[:, :, 0] * 0.35 + a[:, :, 1] * 0.5 + a[:, :, 2] * 0.15
        lum = lum * (0.85 + 0.3 * grit)                                       # grain
        o = np.zeros_like(a)
        o[:, :, 0] = np.interp(lum, xs, R); o[:, :, 1] = np.interp(lum, xs, G); o[:, :, 2] = np.interp(lum, xs, B)
        o[:, :, 3] = np.interp(lum, xs, AL) * (a[:, :, 3] > 0)
        im = Image.fromarray(np.clip(o, 0, 255).astype(np.uint8), "RGBA")
        im = im.resize((int(round(274 * EXPL_SCALE)), int(round(258 * EXPL_SCALE))), Image.LANCZOS)
        _DARK_EXPL.append(im)
    return _DARK_EXPL


def hurl_skull4(n=12):
    """Hurl Skull (0xCC) v4 slot 0 (2026-10-19, user: 'make the skull SPIN like the boulder - the face does not need to
    stay in front; needs more glow / tail'): Hurl Boulder's BALLS.ILB 7-14 turn a full revolution in 8 frames at
    f20 5 (40 ticks); this skull turns 30 deg per frame = one revolution per 12-frame loop at the live f20 3 (36 ticks,
    ~ the boulder's speed) - same ids 7410-7421, same 64x64 canvas centre 31/33, size ~ the boulder (~10x12 px).
    Gritty bone-grey skull (grime, pits, cracks, pitch-black sockets / nose / teeth gaps), a wider CRIMSON glow halo
    hugging it, a ragged BLACK smoke aura, and a rising PLUME (black smoke + blood-red flame tongues + dark-red embers,
    ~22 px up) that reads as a fire trail behind the lob (the kind-2 arc has no direction / trail slot, so the trail
    is baked as rising smoke).  Solid keyed sprite (256): edges alpha-dithered by rec_for = gritty broken edges."""
    S = 8; W = H = 64; cx, cy = 31.0, 33.0
    rnd = random.Random(5410)
    tongues = [(rnd.uniform(-3.0, 3.0), rnd.uniform(9.0, 15.0), rnd.uniform(0, 6.28), rnd.uniform(1.3, 2.2)) for _ in range(10)]
    puffs = [(rnd.uniform(-5.0, 5.0), rnd.uniform(0, 1), rnd.uniform(2.0, 3.6), rnd.uniform(0, 6.28)) for _ in range(9)]
    embers = [(rnd.uniform(-4.5, 4.5), rnd.uniform(0, 1), rnd.uniform(0.7, 1.4)) for _ in range(10)]
    grime = np.random.RandomState(5411).rand(H, W)

    def skull(ang):
        L = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(L); k = S
        def E(x0, y0, x1, y1, c): d.ellipse([(cx + x0) * k, (cy + y0) * k, (cx + x1) * k, (cy + y1) * k], fill=c)
        def P(pts, c): d.polygon([((cx + x) * k, (cy + y) * k) for x, y in pts], fill=c)
        def Ln(pts, c, w): d.line([((cx + x) * k, (cy + y) * k) for x, y in pts], fill=c, width=max(1, int(w * k)))
        rim, bone, lit, shade, blk = (14, 8, 8, 255), (200, 196, 186, 255), (236, 233, 224, 255), (124, 116, 110, 255), (4, 2, 2, 255)
        E(-5.4, -6.6, 5.4, 3.4, rim)
        P([(-3.9, 1.2), (3.9, 1.2), (3.1, 6.2), (-3.1, 6.2)], rim)
        E(-4.8, -6.0, 4.8, 2.8, bone)
        P([(-3.3, 1.6), (3.3, 1.6), (2.6, 5.6), (-2.6, 5.6)], bone)
        E(-3.8, -5.0, 1.6, -1.6, lit)
        E(1.4, -2.4, 4.2, 2.6, shade); P([(0.6, 3.0), (3.0, 1.8), (2.3, 4.8), (0.4, 4.8)], shade)
        E(-4.0, -2.2, -0.4, 1.5, blk); E(0.4, -2.2, 4.0, 1.5, blk)
        P([(-3.6, -2.1), (-0.3, -1.5), (-0.6, -1.0), (-3.6, -1.3)], rim); P([(3.6, -2.1), (0.3, -1.5), (0.6, -1.0), (3.6, -1.3)], rim)
        P([(0, 1.6), (-1.0, 3.2), (1.0, 3.2)], blk)
        d.rectangle([(cx - 2.8) * k, (cy + 3.7) * k, (cx + 2.8) * k, (cy + 4.4) * k], fill=blk)
        for t in (-1.8, -0.6, 0.6, 1.8): Ln([(t, 3.7), (t, 5.4)], blk, 0.42)
        Ln([(-1.2, -5.2), (-0.4, -3.6), (-1.0, -2.6)], rim, 0.32)
        Ln([(2.0, -4.6), (1.2, -3.4), (1.9, -2.5)], rim, 0.28)
        return L.rotate(ang, resample=Image.BICUBIC, center=(cx * k, cy * k))

    out = []
    for i in range(n):
        ph = 2 * math.pi * i / n
        F = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0)); d = ImageDraw.Draw(F); k = S
        for (ox, t0, r, p0) in puffs:                                         # rising black smoke plume (the 'tail')
            t = (i / n + t0) % 1.0
            x = cx + ox * (0.5 + 0.6 * t) + 1.4 * math.sin(ph + p0); y = cy - 4 - 20 * t
            rr = r * (0.7 + 0.9 * t) * (1.0 - 0.45 * t); a = int(255 * (1 - t) ** 0.6)
            d.ellipse([(x - rr) * k, (y - rr) * k, (x + rr) * k, (y + rr) * k], fill=(10, 6, 6, a))

        def tongue(ox, ln, p0, wd, col, sc, a):
            fl = 0.7 + 0.3 * math.sin(ph * 2 + p0)
            Lg = ln * sc * fl + 2.0; w = wd * (0.85 + 0.4 * sc); sway = 1.4 * math.sin(ph + p0)
            base = (cx + ox * (0.6 + 0.4 * sc), cy - 0.5); tip = (cx + ox * 0.35 + sway, cy - 0.5 - Lg)
            pts = [(base[0] - w, base[1] + 2.6), (base[0] + w, base[1] + 2.6), (base[0] + w * 0.55 + sway * 0.4, base[1] - Lg * 0.5),
                   tip, (base[0] - w * 0.55 + sway * 0.4, base[1] - Lg * 0.5)]
            d.polygon([(x * k, y * k) for x, y in pts], fill=col + (a,))
        d.ellipse([(cx - 8.0) * k, (cy - 7.8) * k, (cx + 8.0) * k, (cy + 7.2) * k], fill=(14, 4, 4, 200))      # black smoke aura
        for col, sc, a in (((80, 4, 4), 1.0, 230), ((140, 10, 8), 0.8, 245), ((200, 22, 12), 0.56, 255)):
            for (ox, ln, p0, wd) in tongues: tongue(ox, ln, p0, wd, col, sc, a)
        F = F.filter(ImageFilter.GaussianBlur(S * 0.4))
        sk = skull(-30.0 * i)                                                  # full spin: 30 deg / frame
        m = sk.split()[3]
        for col, rad, bl in (((120, 6, 6, 255), 3, 1.0), ((210, 26, 14, 255), 1, 0.5)):   # wide dark-crimson glow + hot rim
            g = Image.new("RGBA", F.size, (0, 0, 0, 0)); g.paste(col, mask=m.filter(ImageFilter.MaxFilter(2 * rad * S + 1)))
            F = Image.alpha_composite(F, g.filter(ImageFilter.GaussianBlur(S * bl)))
        im = Image.alpha_composite(F, sk)
        small = np.array(im.resize((W, H), Image.LANCZOS)).astype(np.float32)
        a = small[:, :, 3]; opaque = a > 200; lum = small[:, :, :3].mean(2); bonepx = opaque & (lum > 95)
        g = (grime - 0.5) * 32.0
        for c in range(3): small[:, :, c] = np.where(bonepx, small[:, :, c] + g, small[:, :, c])
        pit = bonepx & (grime > 0.92)
        for c in range(3): small[:, :, c] = np.where(pit, small[:, :, c] * 0.45, small[:, :, c])
        small[:, :, 3] = np.where(a > 120, 255, 0)                             # v4: hard edge (no checkerboard dither) - chunky gritty smoke
        smoke = (small[:, :, 3] > 0) & (lum < 40)                              # sooty smoke pixels: vary the greys for texture
        tex = (grime[::-1, :] - 0.5) * 34.0
        for c in range(3): small[:, :, c] = np.where(smoke, np.clip(small[:, :, c] + 14 + tex, 4, 70), small[:, :, c])
        img = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), "RGBA"); dr = ImageDraw.Draw(img)
        for (ex, e0, sp) in embers:
            t = (i / n * sp + e0) % 1.0
            x = cx + ex + 1.8 * math.sin(ph + e0 * 6); y = cy - 7 - 16 * t
            if t < 0.9: dr.point((round(x), round(y)), fill=(int(230 - 100 * t), int(34 - 24 * t), 10, 255))
        out.append(img)
    return out


_DARK_EXPL2 = []
EXPL2_MODE = [514] * 4 + [1026] * 26             # a short crimson FLASH (brighten), then the blast drawn as MULTIPLY (darkening)


def dark_explosion2():
    """Hurl Skull (0xCC) v4 impact (slot 2) (2026-10-19, user: 'cool idea but looks bad - polish it to the quality of the
    original explosion'): v3's alpha version had to DITHER its soft coverage (a keyed sprite has no per-pixel alpha) -
    hence the blocky, speckled look.  v4 keeps Self Destruct's EXPLBIG.ILB 0-29 at FULL size (274x258, vanilla's own
    canvas; Implosion's 280x280 DualDF sprite runs live) and every gradient smooth by using the two modes that take
    per-pixel strength from the colour itself:
      frames 0-3   BRIGHTEN (514, like vanilla): the ignition flash re-graded onto a crimson ramp (blood-red glow ->
                   hot red-orange core, never yellow / white).
      frames 4-29  MULTIPLY (1026, white = no change): the fireball darkens the ground - each pixel's darkening
                   follows vanilla's own luminance, tinted deep crimson in the burning body (the hottest parts nearly
                   black-red) and turning to sooty grey-black smoke from frame 16 as the fire dies, thinning out by 29.
    Same 30 frames / timing as vanilla; record 214 slot 2 anchor = vanilla's -131/-142 (pfs v5)."""
    if _DARK_EXPL2: return _DARK_EXPL2
    src = _aowx_ilb_frames(os.path.join("Effects", "ExplBig.ILB"), list(range(30)))
    xs = np.array([0, 20, 60, 120, 180, 230, 255], np.float32)            # flash ramp: luminance -> added light
    R = np.array([0, 50, 120, 175, 215, 240, 255], np.float32)
    Gc = np.array([0, 0, 3, 8, 22, 50, 80], np.float32)
    Bc = np.array([0, 0, 3, 6, 14, 30, 50], np.float32)
    FIRE = np.array([175, 18, 12], np.float32)                             # multiply tint of the burning body
    CORE = np.array([95, 4, 4], np.float32)                                # the hottest parts: near black-red
    SOOT = np.array([70, 62, 60], np.float32)                              # dying smoke
    for i, s in enumerate(src):
        a = np.array(s).astype(np.float32)
        lum = np.maximum(a[:, :, 0] * 0.4 + a[:, :, 1] * 0.45 + a[:, :, 2] * 0.15, a[:, :, :3].max(2) * 0.85)
        o = np.zeros_like(a)
        if EXPL2_MODE[i] == 514:
            o[:, :, 0] = np.interp(lum, xs, R); o[:, :, 1] = np.interp(lum, xs, Gc); o[:, :, 2] = np.interp(lum, xs, Bc)
            o[:, :, 3] = np.where(o[:, :, :3].max(2) >= 4, 255, 0)
        else:
            k = max(0.0, (i - 15) / 14.0)                                    # 0 = fire .. 1 = last smoke frame
            fade = (1.0 - k) ** 1.1 * (min(1.0, (i - 3) / 3.0))              # ramps in over 4-6, thins out by 29
            d = np.clip(lum / 230.0, 0, 1) ** 0.7                            # 0..1 per-pixel strength from vanilla
            hot = np.clip((lum - 170) / 85.0, 0, 1)
            body = FIRE[None, None, :] * (1 - hot[:, :, None]) + CORE[None, None, :] * hot[:, :, None]
            tint = body * (1 - min(1.0, k * 1.6)) + SOOT[None, None, :] * min(1.0, k * 1.6)   # fire -> soot
            amt = (d * fade)[:, :, None]
            o[:, :, :3] = 255.0 * (1 - amt) + tint * amt
            o[:, :, 3] = np.where(amt[:, :, 0] > 0.02, 255, 0)
        _DARK_EXPL2.append(Image.fromarray(np.clip(o, 0, 255).astype(np.uint8), "RGBA"))
    return _DARK_EXPL2


SK5_DEATH = np.array([34, 22, 44], np.float32)    # vanilla-death multiply tint: near-black with a cold violet cast
SK5_FIRE = [(0.00, (255, 246, 190)), (0.25, (255, 210, 90)), (0.50, (255, 150, 35)), (0.75, (225, 80, 12)), (1.00, (120, 28, 4))]


def _sk5_firecol(t):
    """Vanilla-style fire ramp (Fire Bolt / Fire Ball palette): 0 = white-yellow core .. 1 = deep red-brown edge."""
    t = min(1.0, max(0.0, t))
    for (a, ca), (b, cb) in zip(SK5_FIRE, SK5_FIRE[1:]):
        if t <= b:
            u = (t - a) / (b - a)
            return tuple(ca[c] + (cb[c] - ca[c]) * u for c in range(3))
    return SK5_FIRE[-1][1]


def _sk5_mul(dark, tint=SK5_DEATH):
    """darkening amount 0..1 (HxW) -> a MULTIPLY sprite (drawMode 1026): white = no change; kept where > 1.5 %."""
    a = np.clip(dark, 0, 1)[:, :, None]
    rgb = 255.0 * (1 - a) + tint[None, None, :] * a
    al = np.where(a[:, :, 0] > 0.015, 255, 0)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), al]).astype(np.uint8), "RGBA")


def _sk5_add(rgb):
    """additive light (HxWx3, 0..255) -> an ADDITIVE sprite (drawMode 770, black key = nothing added)."""
    rgb = np.clip(rgb, 0, 255)
    al = np.where(rgb.max(2) >= 4, 255, 0)
    return Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA")


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


def skull_death_burst(n=30):
    """Hurl Skull slot 2 layer 1 (drawn BEFORE Self Destruct's vanilla EXPLBIG 0-29) - v7 (user: 'the death ring is
    excessive'): NO shock ring; a lighter violet-black pall under the blast (60 % max, r 26 -> 100 px), ~55 black
    shards with soot streaks on low arcs and two thin smoke wisps rising late - all subtle, the vanilla fireball stays the star.
    MULTIPLY (1026), vanilla 274x258 canvas / anchor (impact at 131/142), 30 frames (sets the helper lifetime)."""
    W, H = 274, 258; cx, cy = 131.0, 142.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 1.3) ** 2)
    rnd = random.Random(5740)
    parts = []
    for _ in range(55):
        a = rnd.uniform(0, 2 * math.pi); v = rnd.uniform(2.4, 5.4); up = rnd.uniform(0.8, 2.8)
        parts.append((math.cos(a) * v, math.sin(a) * v * 0.55 - up, rnd.uniform(1.4, 2.8), rnd.uniform(0, 3)))
    cols = [(rnd.uniform(-18, 18), rnd.uniform(0, 4), rnd.uniform(7, 10)) for _ in range(2)]
    noise = np.array(Image.fromarray((np.random.RandomState(5741).rand(26, 28) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)).astype(np.float32) / 255
    out = []
    for i in range(n):
        t = i / (n - 1.0)
        R = 26 + 74 * t ** 0.6
        dark = (0.60 * (1 - t) ** 1.3) * np.exp(-(rr / R) ** 2 * 1.5) * (0.85 + 0.3 * noise) * min(1.0, (i + 1) / 3.0)
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
        if i >= 14:
            u = (i - 14) / 15.0
            for (ox, d0, wd) in cols:
                for k in range(5):
                    v = u - k * 0.06
                    if v <= 0: continue
                    px_ = cx + ox + 3 * math.sin(k + i * 0.3); py_ = cy - 8 - 55 * v
                    w = wd * (0.7 + 0.6 * v)
                    dark = np.maximum(dark, 0.45 * (1 - u) ** 0.9 * (1 - 0.12 * k) * np.exp(-((xx - px_) ** 2 + (yy - py_) ** 2) / (w * w)))
        out.append(_sk5_mul(dark))
    return out


SK8_SCALE = 0.8
SK8_EXPL_BLEND = [100] * 21 + [95, 90, 80, 70, 60, 50, 40, 30, 20]   # vanilla ExplBig 0-29 blend values (all drawMode 514)
_SK8_EXPL, _SK8_BURST = [], []


def _sk8_size():
    return int(round(274 * SK8_SCALE)), int(round(258 * SK8_SCALE))   # 219 x 206; impact 131/142 -> 105/113


def explbig80():
    """Hurl Skull v8 impact (record 214 slot 2, pfs v7) - user: 'make the explosion about 20 % smaller'.  Self
    Destruct's own ExplBig.ILB 0-29, untouched in ExplBig.ILB (shared with Self Destruct), COPIED here scaled to 80 %
    (274x258 -> 219x206): each frame composited onto black (its BRIGHTEN mode 514 adds light, so black = nothing),
    Lanczos-downscaled in linear-ish space, re-keyed where the light drops below 4/255.  drawMode 514 and the vanilla
    per-frame blend values (100 x21, then 95..20) are kept by the rows."""
    if _SK8_EXPL: return _SK8_EXPL
    src = _aowx_ilb_frames(os.path.join("Effects", "ExplBig.ILB"), list(range(30)))
    W, H = _sk8_size()
    for s in src:
        a = np.array(s).astype(np.float32)
        rgb = a[:, :, :3] * (a[:, :, 3:4] / 255.0)
        lin = (rgb / 255.0) ** 2.2
        ch = []
        for c in range(3):
            plane = Image.fromarray((lin[:, :, c] * 65535).astype(np.float32), "F").resize((W, H), Image.LANCZOS)
            ch.append(np.clip(np.array(plane) / 65535.0, 0, 1) ** (1 / 2.2) * 255)
        o = np.dstack(ch)
        al = np.where(o.max(2) >= 4, 255, 0)
        _SK8_EXPL.append(Image.fromarray(np.dstack([np.clip(o, 0, 255), al]).astype(np.uint8), "RGBA"))
    return _SK8_EXPL


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


def build():
    groups = [(0, particles(), "DFspark%02d.BMP", 770, 50, 0x0000),
              (40, boulders(), "DFrock%02d.BMP", 256, 0, KEY),
              (50, impacts(), "DFhit%02d.BMP", 770, 50, 0x0000),
              (60, portal_frames(), "DFportal%02d.BMP", 258, 88, KEY),
              (80, trail_frames(), "DFtrail%02d.BMP", 770, 55, 0x0000),
              (100, sword_frames(), "DFsword%03d.BMP", 258, 75, KEY),
              (200, sparkles(), "DFspark1%d.BMP", 770, 50, 0x0000),
              (300, beam_head(), "DFbeam%02d.BMP", 770, 55, 0x0000),          # Repent slot 0 (2026-10-12)
              (310, beam_trail(), "DFbeamt%02d.BMP", 770, 55, 0x0000),        # Repent slot 1
              (320, beam_impact(), "DFbeamh%02d.BMP", 770, 55, 0x0000),       # Repent slot 2
              (330, souls(), "DFsoul%02d.BMP", 770, 50, 0x0000),              # (v2 Harvest wisps, unused since v3)
              (334, purple_sparkles(), "DFpsoul%d.BMP", 770, 50, 0x0000),     # Harvest Souls slot 0 (v3)
              (3000, deadcall_sparkles(), "DEcall%d.BMP", 258, 85, 0x0000),   # v3: alpha (brown/black skull, purple rim)   # Call of the Dead (211) slot 0: grave-green corpse twinkle (3 frames, 38x38)
              (3004, deadcall_spiral(), "DEcspir%02d.BMP", 770, 95, 0x0000),   # Call of the Dead (211) slot 1: five skulls spiralling in (96x96, per-corpse kind-0x26 driver)
              (3300, xwind_cloudset(), "AIxc06_%d.BMP", 770, 6, 0x0000),   # Crosswind (213) Air Mastery clouds 160/161/162 at intensity 6
              (3303, xwind_cloudset(), "AIxc12_%d.BMP", 770, 12, 0x0000),   # Crosswind (213) Air Mastery clouds 160/161/162 at intensity 12
              (3306, xwind_cloudset(), "AIxc18_%d.BMP", 770, 18, 0x0000),   # Crosswind (213) Air Mastery clouds 160/161/162 at intensity 18
              (3309, xwind_cloudset(), "AIxc24_%d.BMP", 770, 24, 0x0000),   # Crosswind (213) Air Mastery clouds 160/161/162 at intensity 24
              (3312, xwind_cloudset(), "AIxc30_%d.BMP", 770, 30, 0x0000),   # Crosswind (213) Air Mastery clouds 160/161/162 at intensity 30
              (3320, xwind_swirl(), "AIxsw%02d.BMP", 770, 70, 0x0000),          # Crosswind (213) per-enemy mote swirl (64x80, loop)
              (3352, xwind_swirl(), "AIxswf%02d.BMP", 770, 30, 0x0000),         # ... the same frames dimmer (fade in / out)
              (3390, xwind_swirl2(), "AIxsw2_%02d.BMP", 770, 70, 0x0000),       # Crosswind (213) v4 per-enemy swirl: 60 frames, fade baked in (3390-3449)
              (3550, xwind_status(), "AIxwst%02d.BMP", 770, 81, 0x0000),   # r7: 10 % more subtle      # Crosswind (213) 0xC2 status overlay: short white mote spiral (48x80, loop, Ability.pfs 204 tag 8)
              (3600, xwind_dust(), "AIxwdst%d.BMP", 770, 50, 0x0000),   # Crosswind (213) v6 slot 0: small (0.6x) Winds of Fury orbs for the wash particles
              (3450, suspend_status(), "AIsust%03d.BMP", 770, 60, 0x0000),   # v3: 100 frames (smooth) - 3250-3289 unused since   # Suspend (214) 0xC3 status overlay: faint white beam + rising motes (48x128, loop)
              (3034, gust_wisp(), "AIgust%d.BMP", 770, 70, 0x0000),          # Gust (212) slot 0: per-strike wind wisp along the breath fan (64x64, Cold Breath's role)
              (3042, gust_shock(), "AIgshk%d.BMP", 770, 50, 0x0000),           # Gust (212) slot 1 v3: pale Shockwave particle (19x19, kind-0x1F spray)
              (5200, crashwave_spray(), "WTcwav%d.BMP", 770, 50, 0x0000),       # Crashing Wave (220) slot 1: sea-blue spray particle (19x19, kind-0x1F, Gust v7 SPR)
              (3100, crosswind_motes(), "AIxwmote%d.BMP", 770, 60, 0x0000),    # Crosswind (213) slot 0: small air curl (16x16)
              (3103, crosswind_gust(), "AIxwgust%02d.BMP", 770, 90, 0x0000),   # Crosswind (213) slot 1: gust sweep (82x72, 24 frames)
              (3714, suspend_lift(), "AIsusm%02d.BMP", 770, 90, 0x0000),   # v7: 96 frames (3714-3809); 3650-3713 unused since   # v6: 64 frames x 1 tick (smoother; same length) - 3150-3181 unused since   # Suspend (214) slot 0: rising wind helix (96x96, additive)
              (3200, staticshield_aura(), "AIsshld%02d.BMP", 770, 100, 0x0000),   # Static Shield (215) slot 0: crackling static shell (96x96, additive)
              (3858, staticshield_status(), "AIssstat%02d.BMP", 770, 70, 0x0000),   # Static Shield (215) 0xC4 status overlay: Fire-Halo-sized lightning aura loop (44x42, 16 frames)   # v4: 48 frames (3810-3857); 3230-3245 unused since
              (2960, miracle_sparkles(), "LImirac%d.BMP", 770, 50, 0x0000),   # Miracle (209) slot 0: gold PARTICLE twinkle (3 frames, 38x38)
              (340, blank(), "DFnone%d.BMP", 770, 50, 0x0000),                # Repent slot 0: invisible strike head
              (350, beam_flash(), "DFbflash%d.BMP", 770, 55, 0x0000),         # Repent slot 2: landing flash
              (400, beam_frames()[:N_SPARK], "DFbspark%02d.BMP", 770, 55, 0x0000),            # Repent slot 1 part 1: sparkles (additive)
              (400 + N_SPARK, beam_frames()[N_SPARK:], "DFbeam%02d.BMP", 770, 55, 0x0000),   # Repent slot 1 part 2: the beam (ADDITIVE: every vanilla 258-alpha sprite is <= 64x64, 770 goes to 320x480; the 258 80x300 build crashed at cast)
              (460, purple_summon(), "DFpsumm%02d.BMP", 770, 50, 0x0000),       # Harvest Souls slot 1: purple summon dome at the caster (v4)
              (500, martyr_motes(), "DFmartyr%02d.BMP", 770, 55, 0x0000),       # Martyr slot 0 (2026-10-13, Life/Fire)
              (520, cleanse_burst(), "DFcleanse%02d.BMP", 770, 55, 0x0000),     # Cleansing Flame slot 0
              (540, phoenix_summon(), "DFphnx%02d.BMP", 770, 50, 0x0000),       # Summon Phoenix slot 0
              (560, starfire_head(), "DFstar%02d.BMP", 770, 55, 0x0000),        # Holy Starfire slot 0 (path head)
              (570, starfire_trail(), "DFstart%02d.BMP", 770, 55, 0x0000),      # Holy Starfire slot 1 (trail)
              (580, starfire_impact(), "DFstarh%02d.BMP", 770, 55, 0x0000),     # Holy Starfire slot 2 (impact)
              (600, corpse_fire(), "DFashes%02d.BMP", 258, 90, KEY),           # Ashes to Ashes slot 1: burning corpse (alpha: black smoke + fire)
              (620, ember_ray(), "DFashray%d.BMP", 770, 55, 0x0000),           # (v1 ember ray head - unused since v2, kept so later ids stay put)
              (640, ashes_hit(), "DFashhit%02d.BMP", 258, 90, KEY),           # Ashes to Ashes slot 0 (v2, unused since v3): the hit - fire column + black ash swirl at the target
              (660, ashes_hit_v2(), "DFashbig%02d.BMP", 258, 90, KEY),         # Ashes to Ashes slot 0 (v3 epic, unused since v4 - user: "too explodey")
              (690, ashes_mote(), "DFashmote%d.BMP", 770, 55, 0x0000),          # Ashes to Ashes slot 2: red-orange ember mote (kind-0x1F sparkles corpse -> caster)
              (700, ashes_hit_v3(), "DFashvap%02d.BMP", 258, 90, KEY),         # Ashes to Ashes slot 0 (v4, unused since v5 - user: "bad")
              (720, ashes_swirl(), "DFashswl%02d.BMP", 258, 90, KEY),          # Ashes to Ashes slot 0 (v5, unused since v6): one 40-tick swirl per hit
              (740, ashes_swirl_seg(), "DFashseg%02d.BMP", 258, 90, KEY),      # Ashes to Ashes slot 3 (v6): per-hit swirl segment (6 loop + 7 fade frames), the kind-0x26 driver the gate spawns each strike
              (760, ashes_pulse(), "DFashpls%d.BMP", 770, 55, 0x0000),          # Ashes to Ashes slot 0 (v6): 4-frame impact pulse = the strike effect (lands fast -> damage fast)
              (780, ashes_swirl_seg(60, 8), "DFashlp%02d.BMP", 258, 90, KEY),   # (v7, unused since v8: too tall; the drawn frame comes from the sequence's own counter so a tick jump cannot reach the fade)
              (860, ashes_swirl_loop(), "DFashloop%02d.BMP", 258, 90, KEY),     # Ashes to Ashes slot 3 (v8): unit-height continuous pillar swirl, 90 frames (one driver per cast)
              (950, ashes_swirl_fade(), "DFashfade%d.BMP", 258, 90, KEY),       # Ashes to Ashes slot 4 (v8, unused since v9): the scatter/fade
              # ---- Earth/Fire (2026-10-13)
              (1000, oil_splash(), "EFoil%02d.BMP", 258, 90, KEY),               # Oil Spring slot 0: oil burst spreading over the area, flames catching (96x96)
              (1020, lionheart_glow(), "EFlion%02d.BMP", 770, 55, 0x0000),       # Lionheart slot 0: golden-red heart burst on the unit (40x40)
              (1040, forge_sparks(), "EFforge%02d.BMP", 258, 90, KEY),           # Forge Blast slot 0: hammer-blow spark fountain + smoke over the city (128x96)
              (1060, arms_race_glow(), "EFarms%02d.BMP", 770, 55, 0x0000),       # Arms Race slot 0: forge-glow cog twinkle over the city (48x48)
              (1080, oil_gush(), "EFgush%02d.BMP", 258, 90, KEY),                # Oil Spring v5: the gush RISE (10 frames 128x128) = slot 4
              (1170, oil_gush_loop(), "EFgushl%02d.BMP", 258, 90, KEY),          # Oil Spring v5: the steady fountain LOOP (10 frames) = slot 5
              (1180, oil_gush_end(), "EFgushe%02d.BMP", 258, 90, KEY),           # Oil Spring v5: 9 blank frames + the collapse (8) = slot 6                # Oil Spring v2: the oil geyser rising from the centre of the area and raining down (128x128)
              (4000, oil_gush_smooth(), "EFgsr%02d.BMP", 258, 90, KEY),        # Oil Spring gush RISE v2: 30 frames x 1 tick
              (4030, oil_gush_loop_smooth(), "EFgsl%02d.BMP", 258, 90, KEY),   # Oil Spring gush LOOP v2: 30 frames (slot plays it twice)
              (4060, oil_gush_end_smooth(), "EFgse%02d.BMP", 258, 90, KEY),    # Oil Spring gush END v2: 1 blank + 24 collapse frames
              (4100, oil_gush_rise3(), "EFgr3%02d.BMP", 258, 90, KEY),       # Oil Spring gush RISE v3: 66 frames x 1 tick (transient; == loop from 48)
              (4166, oil_gush_loop3(), "EFgl3%02d.BMP", 258, 90, KEY),       # Oil Spring gush LOOP v3: 30 frames (slot plays it twice)
              (4196, oil_gush_end3(), "EFge3%02d.BMP", 258, 90, KEY),        # Oil Spring gush END v3: 1 blank + 21 collapse frames
              (4220, ore_glints(), "ERdepth%d.BMP", 770, 50, KEY),                   # Depths of Plenty (217) slot 0: Earth Mastery map-wide particle = amber ore glints (20x20, 4 frames)
              (5300, sea_rite_motes(), "WTrite%d.BMP", 770, 55, 0x0000),              # Rite of the Seas (221) slot 0: Earth Mastery map-wide particle = curling sea crest + silver glint (20x20, 4 frames)
              (6150, royal_motes(), "COroyal%d.BMP", 770, 50, 0x0000),            # Royal Ambition (230) slot 0: Earth Mastery map-wide particle = golden 5-point star glints (20x20, 4 frames)
              (6200, essence_swirl2(), "COess%02d.BMP", 770, 90, 0x0000),      # Essence Shift (231) v3 slot 0: cast swirl + smooth fade-out tail (96x96, additive, 44 x 2 ticks; DualDF 6200-6243)
              (6100, cityspy_eye2_a(), "COspye%02d.BMP", 770, 90, 0x0000),      # City Spy (229) v2 slot 1: eye frames 0-11 (blank / fade 1-6 / gaze left 1-4 / right 1), 40x28, ADDITIVE
              (6128, cityspy_eye2_b(), "COspyf%02d.BMP", 770, 90, 0x0000),      # City Spy (229) v2 slot 1: eye frames 12-14 (gaze right 2-4)
              (6300, cityspy_eye3_blank(), "COspy3z%d.BMP", 258, 80, KEY),        # City Spy (229) v3: invisible frame (hidden pause)
              (6301, cityspy_eye3_gaze(), "COspy3g%02d.BMP", 258, 80, KEY),       # City Spy (229) v3: v1-look open eye, gaze -4..+4 px in 0.25 px steps (33 frames, ALPHA 80 = v1)
              (6334, cityspy_eye3_centre(), "COspy3f0_%d.BMP", 258, 8, KEY),      # City Spy (229) v3: fade level 1/9 = the centre eye at blend 8
              (6335, cityspy_eye3_centre(), "COspy3f1_%d.BMP", 258, 16, KEY),      # City Spy (229) v3: fade level 2/9 = the centre eye at blend 16
              (6336, cityspy_eye3_centre(), "COspy3f2_%d.BMP", 258, 24, KEY),      # City Spy (229) v3: fade level 3/9 = the centre eye at blend 24
              (6337, cityspy_eye3_centre(), "COspy3f3_%d.BMP", 258, 32, KEY),      # City Spy (229) v3: fade level 4/9 = the centre eye at blend 32
              (6338, cityspy_eye3_centre(), "COspy3f4_%d.BMP", 258, 40, KEY),      # City Spy (229) v3: fade level 5/9 = the centre eye at blend 40
              (6339, cityspy_eye3_centre(), "COspy3f5_%d.BMP", 258, 48, KEY),      # City Spy (229) v3: fade level 6/9 = the centre eye at blend 48
              (6340, cityspy_eye3_centre(), "COspy3f6_%d.BMP", 258, 56, KEY),      # City Spy (229) v3: fade level 7/9 = the centre eye at blend 56
              (6341, cityspy_eye3_centre(), "COspy3f7_%d.BMP", 258, 64, KEY),      # City Spy (229) v3: fade level 8/9 = the centre eye at blend 64
              (6342, cityspy_eye3_centre(), "COspy3f8_%d.BMP", 258, 72, KEY),      # City Spy (229) v3: fade level 9/9 = the centre eye at blend 72
              (6343, cityspy_eye4_blank(), "COspy4z%d.BMP", 258, 52, KEY),        # City Spy (229) v4: invisible frame (hidden pause)
              (6344, cityspy_eye4_gaze(), "COspy4g%02d.BMP", 258, 52, KEY),       # City Spy (229) v4: open eye at blend 52, gaze -4..+4 px in 0.25 px steps (33), oval iris at the sides
              (6377, cityspy_eye4_centre(), "COspy4f00_%d.BMP", 258, 3, KEY),     # City Spy (229) v4: fade level 1/20 = the centre eye at blend 3
              (6378, cityspy_eye4_centre(), "COspy4f01_%d.BMP", 258, 5, KEY),     # City Spy (229) v4: fade level 2/20 = the centre eye at blend 5
              (6379, cityspy_eye4_centre(), "COspy4f02_%d.BMP", 258, 8, KEY),     # City Spy (229) v4: fade level 3/20 = the centre eye at blend 8
              (6380, cityspy_eye4_centre(), "COspy4f03_%d.BMP", 258, 10, KEY),     # City Spy (229) v4: fade level 4/20 = the centre eye at blend 10
              (6381, cityspy_eye4_centre(), "COspy4f04_%d.BMP", 258, 13, KEY),     # City Spy (229) v4: fade level 5/20 = the centre eye at blend 13
              (6382, cityspy_eye4_centre(), "COspy4f05_%d.BMP", 258, 16, KEY),     # City Spy (229) v4: fade level 6/20 = the centre eye at blend 16
              (6383, cityspy_eye4_centre(), "COspy4f06_%d.BMP", 258, 18, KEY),     # City Spy (229) v4: fade level 7/20 = the centre eye at blend 18
              (6384, cityspy_eye4_centre(), "COspy4f07_%d.BMP", 258, 21, KEY),     # City Spy (229) v4: fade level 8/20 = the centre eye at blend 21
              (6385, cityspy_eye4_centre(), "COspy4f08_%d.BMP", 258, 23, KEY),     # City Spy (229) v4: fade level 9/20 = the centre eye at blend 23
              (6386, cityspy_eye4_centre(), "COspy4f09_%d.BMP", 258, 26, KEY),     # City Spy (229) v4: fade level 10/20 = the centre eye at blend 26
              (6387, cityspy_eye4_centre(), "COspy4f10_%d.BMP", 258, 29, KEY),     # City Spy (229) v4: fade level 11/20 = the centre eye at blend 29
              (6388, cityspy_eye4_centre(), "COspy4f11_%d.BMP", 258, 31, KEY),     # City Spy (229) v4: fade level 12/20 = the centre eye at blend 31
              (6389, cityspy_eye4_centre(), "COspy4f12_%d.BMP", 258, 34, KEY),     # City Spy (229) v4: fade level 13/20 = the centre eye at blend 34
              (6390, cityspy_eye4_centre(), "COspy4f13_%d.BMP", 258, 36, KEY),     # City Spy (229) v4: fade level 14/20 = the centre eye at blend 36
              (6391, cityspy_eye4_centre(), "COspy4f14_%d.BMP", 258, 39, KEY),     # City Spy (229) v4: fade level 15/20 = the centre eye at blend 39
              (6392, cityspy_eye4_centre(), "COspy4f15_%d.BMP", 258, 42, KEY),     # City Spy (229) v4: fade level 16/20 = the centre eye at blend 42
              (6393, cityspy_eye4_centre(), "COspy4f16_%d.BMP", 258, 44, KEY),     # City Spy (229) v4: fade level 17/20 = the centre eye at blend 44
              (6394, cityspy_eye4_centre(), "COspy4f17_%d.BMP", 258, 47, KEY),     # City Spy (229) v4: fade level 18/20 = the centre eye at blend 47
              (6395, cityspy_eye4_centre(), "COspy4f18_%d.BMP", 258, 49, KEY),     # City Spy (229) v4: fade level 19/20 = the centre eye at blend 49
              (6396, cityspy_eye4_centre(), "COspy4f19_%d.BMP", 258, 52, KEY),     # City Spy (229) v4: fade level 20/20 = the centre eye at blend 52
              (6400, cityspy_eye5_open(), "COspy5o%02d.BMP", 258, 52, KEY),        # City Spy (229) v5: eyelids, closed lid line (k 0) .. fully open (k 15 == v4 centre eye 6360)
              (6416, cityspy_eye5_line(), "COspy5l0_%d.BMP", 258, 13, KEY),       # City Spy (229) v5: faint closed lid line, blend 13
              (6417, cityspy_eye5_line(), "COspy5l1_%d.BMP", 258, 26, KEY),       # City Spy (229) v5: faint closed lid line, blend 26
              (6418, cityspy_eye5_line(), "COspy5l2_%d.BMP", 258, 39, KEY),       # City Spy (229) v5: faint closed lid line, blend 39
              (6420, cityspy_eye6_mixed(), "COspy6m%02d.BMP", 258, 52, KEY),     # City Spy (229) v6: lid x gaze combined frames (aperture < 1 with the iris off centre; 9 frames 6420-6428)
              (6600, mimic_shimmer(), "SEmimic%02d.BMP", 770, 85, 0x0000),       # Mimic (233) slot 1: mirror pane forms around the caster, sheen + its mirrored sweep, breaks into glints (64x96, kind-0x26 driver)
              (6700, reversal_swirl(), "SErevs%02d.BMP", 770, 85, 0x0000),       # Reversal (234) slot 0: counter-rotating ribbons that invert colour + mirror flash (96x96, 36 x 2 ticks)
              (6500, lucky_glow(), "SElucky%02d.BMP", 770, 55, 0x0000),       # Lucky (232) slot 0: green four-leaf clover bloom + golden sparkles (40x40, 16 frames, additive)
              (6520, _icon_emblem("glyph_lucky"), "SElukemb%d.BMP", 770, 100, 0x0000),   # Lucky (232) v2 EMBLEM: its own (smaller) clover icon glowing white x5 strengths (replaces the twinkle chain's ENCHANT.ILB emblem)
              (6525, _icon_emblem_levels("glyph_lucky"), "SElukem2_%02d.BMP", 770, 100, 0x0000),   # Lucky (232) v3 EMBLEM: 12 strengths (gamma 1.35) for a smooth eased fade
              (6800, transmute_motes(), "SEtrans%d.BMP", 770, 55, 0x0000),       # Transmutation (235) slot 0: Earth Mastery map-wide particle = gold drop + orbiting green alchemical glint (20x20, 4 frames)
              (7000, seeker_head5(), "SBhead%d.BMP", 770, 90, 0x0000),           # Seeker Bolts slot 0 v5: colours swapped (blue core, gold halo/arcs) + 22 % slimmer (64x64, 8-frame loop)
              (7008, seeker_trail5(), "SBtrail%d.BMP", 770, 80, 0x0000),         # Seeker Bolts slot 1 v5: gold halo/wisps with a blue heart, 22 % narrower (same length)
              (7016, seeker_spin(), "SBspin%02d.BMP", 770, 90, 0x0000),          # Seeker Bolts slot 2: 3 gold/blue orbs spin up + launch flash (72x72, 30 x 1 tick, patch_tc_seekerbolts_v1.py helper)
              (7046, seeker_impact2(), "SBhit%02d.BMP", 770, 90, 0x0000),        # Seeker Bolts slot 3 v2: impact burst with GOLD flash core + gold ring inside the blue ring + gold sparks (96x96, 16 x 1 tick)
              (7200, tame_twinkle(), "TAtwink%02d.BMP", 770, 80, 0x0000),       # Tame Animal (0xC9) v2: Ability.pfs 211 chain (Dominate's TwinkRed timing, 27 frames 64x64)
              (7230, tame_paw(), "TApaw%02d.BMP", 770, 80, 0x0000),             # Tamed (0xCA) overlay + Tame success mark: green paw loop (12 frames 64x64)
              (7242, tame_mark(), "TAmark%d.BMP", 770, 80, 0x0000),             # Tame Animal (0xC9) v3: success mark = paw that rises + fades out smoothly (8 frames 64x64; Ability.pfs 211 slot f8 6)
              (7260, tame_badge(), "TAbadge%02d.BMP", 256, 0, KEY),              # Tamed (0xCA) v3: SOLID green bear-paw overhead badge (12-frame loop 64x64, Dominated-eye spot; Ability.pfs 212)
              (7280, tame_hitfade(), "TAhitf%d.BMP", 770, 80, 0x0000),           # Tame Animal (0xC9) v4: record 211 f8 2/5 peak loop, second pass fades out (10 frames 64x64)
              (7290, tame_castfade(), "TAcastf%d.BMP", 770, 80, 0x0000),         # Tame Animal (0xC9) v4: record 211 f8 1 tail - twinkle 5-8 fading (4 frames 64x64)
              (7300, tame_badge7(), "TAbdg7_%02d.BMP", 258, 88, KEY),          # Tamed (0xCA) v5 overhead badge: user-traced BLACK paw + pulsing green glow (12-frame loop 64x64, ALPHA 258/88; Ability.pfs 212)
              (7400, flaming_skull(), "FSkull%d.BMP", 256, 0, KEY),          # Hurl Flaming Skull (0xCC) slot 0: flying flaming skull, flame flicker loop (64x64 BALLS canvas, Ability.pfs 214)
              (7410, hurl_skull4(), "HSkull%02d.BMP", 256, 0, KEY),          # Hurl Skull (0xCC) v4 slot 0: full 30-deg/frame SPIN like the boulder, wider crimson glow + black aura + rising smoke/ember plume (12 frames, 64x64 BALLS canvas)
              (7430, black_javelin2(), "BJav%02d.BMP", 1026, 100, KEY),     # Shoot Black Javelin (0xCD) v4 slots 0-23: vanilla javelin in MULTIPLY like vanilla (black) + dark glow / soot tail
              (7460, dark_explosion2()[:4], "SKexp%02d.BMP", 514, 100, KEY),  # Hurl Skull v4 slot 2 (pfs v5): crimson ignition FLASH (brighten, 274x258 = vanilla canvas)
              (7464, dark_explosion2()[4:], "SKexq%02d.BMP", 1026, 100, KEY), # Hurl Skull v4 slot 2: MULTIPLY dark-crimson blast -> soot (frames 4-29, smooth per-pixel)
              (7612, hurl_skull5(), "HSbone%02d.BMP", 256, 0, KEY),              # Hurl Skull v5 slot 0 layer 2: the bone skull alone (full spin), solid
              (7624, skull_death_aura(), "HSdaur%02d.BMP", 1026, 100, KEY),      # Hurl Skull v5 slot 0 layer 1: smooth black death aura, MULTIPLY
              (7636, skull_fire_aura(), "HSfaur%02d.BMP", 770, 100, 0x0000),     # Hurl Skull v5 slot 0 layer 3: vanilla-colour flames round it, ADDITIVE
              (7648, deathfire_puff_smoke(), "HSpsmk%02d.BMP", 1026, 100, KEY),  # Hurl Skull v5 slot 3 layer 1: trail puff black smoke, MULTIPLY (48x48)
              (7664, deathfire_puff_fire(), "HSpfir%02d.BMP", 770, 90, 0x0000),  # Hurl Skull v5 slot 3 layer 2: trail puff fire core + sparks, ADDITIVE
              (7680, skull_death_burst(), "HSburst%02d.BMP", 1026, 100, KEY),    # Hurl Skull v5 slot 2 layer 1: death pall / shock ring / black shards under EXPLBIG (274x258)
              (7710, skull_death_burst80(), "HSbu8%02d.BMP", 1026, 100, KEY),      # Hurl Skull v8 slot 2 layer 1 (pfs v7): v7 death layer at 80 % (219x206)
              (7740, explbig80()[:21], "HSx8%02d.BMP", 514, 100, KEY),              # Hurl Skull v8 slot 2 layer 2 (pfs v7): Self Destruct ExplBig 0-20 at 80 %, vanilla mode/blend
              (7761, explbig80()[21:22], "HSx8_21_%d.BMP", 514, 95, KEY),
              (7762, explbig80()[22:23], "HSx8_22_%d.BMP", 514, 90, KEY),
              (7763, explbig80()[23:24], "HSx8_23_%d.BMP", 514, 80, KEY),
              (7764, explbig80()[24:25], "HSx8_24_%d.BMP", 514, 70, KEY),
              (7765, explbig80()[25:26], "HSx8_25_%d.BMP", 514, 60, KEY),
              (7766, explbig80()[26:27], "HSx8_26_%d.BMP", 514, 50, KEY),
              (7767, explbig80()[27:28], "HSx8_27_%d.BMP", 514, 40, KEY),
              (7768, explbig80()[28:29], "HSx8_28_%d.BMP", 514, 30, KEY),
              (7769, explbig80()[29:30], "HSx8_29_%d.BMP", 514, 20, KEY),
              (7320, tame_mark7(), "TApf7a%d.BMP", 258, 18, KEY),              # Tame Animal (0xC9) v5 cast mark fade-in: the badge sprite at blend 18 (record 211 f8 6 fade-in)
              (7321, tame_mark7(), "TApf7b%d.BMP", 258, 38, KEY),              # Tame Animal (0xC9) v5 cast mark fade-in: the badge sprite at blend 38 (record 211 f8 6 fade-in)
              (7322, tame_mark7(), "TApf7c%d.BMP", 258, 60, KEY),              # Tame Animal (0xC9) v5 cast mark fade-in: the badge sprite at blend 60 (record 211 f8 6 fade-in)
              (7323, tame_mark7(), "TApf7d%d.BMP", 258, 80, KEY),              # Tame Animal (0xC9) v5 cast mark fade-in: the badge sprite at blend 80 (record 211 f8 6 fade-in)
              (7324, tame_mark7(), "TApf7e%d.BMP", 258, 66, KEY),              # Tame Animal (0xC9) v5 cast mark fade-out: the badge sprite at blend 66 (record 211 f8 6 fade-out)
              (7325, tame_mark7(), "TApf7f%d.BMP", 258, 44, KEY),              # Tame Animal (0xC9) v5 cast mark fade-out: the badge sprite at blend 44 (record 211 f8 6 fade-out)
              (7326, tame_mark7(), "TApf7g%d.BMP", 258, 24, KEY),              # Tame Animal (0xC9) v5 cast mark fade-out: the badge sprite at blend 24 (record 211 f8 6 fade-out)
              (7327, tame_mark7(), "TApf7h%d.BMP", 258, 8, KEY),               # Tame Animal (0xC9) v5 cast mark fade-out: the badge sprite at blend 8 (record 211 f8 6 fade-out)
              (6112, cityspy_cast(), "COspyc%02d.BMP", 770, 85, 0x0000),         # City Spy (229) slot 0: scrying swirl at the city on the cast (72x72, 16 frames, additive)
              (5400, flood_particles(), "WTflod%d.BMP", 770, 80, 0x0000),       # Flash Flood (223) slot 0: kind-0x1F flood particles (56x24; crest / swell / spray)
              (5750, walloflames_ignite(), "FIwall%02d.BMP", 770, 85, 0x0000),  # Wall of Flames (226) slot 2: per-hex ignition burst (96x80, additive, 18 x 2 ticks)
              (5850, pyro_ash_drift(), "FRpyroD%d.BMP", 770, 40, 0x0000),          # Pyroclasm (227) slots 0-2: Air Mastery map-wide drift = embers + ash (200x116)
              (5853, pyro_glow(), "FRpyroG%02d.BMP", 770, 65, 0x0000),             # Pyroclasm (227) slot 3: per-hex volcano / lava glow, rising embers (32x40, 48 frames; 5853-5900)
              (5950, pyro_particles(), "FRpyroP%02d.BMP", 770, 80, 0x0000),       # Pyroclasm (227) v3 slots 4-7: ember / ash / spark / haze x 8 brightness levels (5950-5981)
              (6000, mmissile_head(), "COmmh%d.BMP", 770, 85, 0x0000),           # Magic Missile (228) slot 0: kind-6 bolt HEAD (64x64, 8-frame loop, additive)
              (6008, mmissile_trail(), "COmmt%d.BMP", 770, 80, 0x0000),          # Magic Missile (228) slot 1: kind-6 TRAIL (frame 0 newest .. 7 oldest)
              (5600, sea_summon(), "WTserp%02d.BMP", 770, 50, 0x0000),          # Summon Sea Serpent (222) slot 0: summon glow tinted sea-teal + foam (12 frames)
              (5650, smoke_burst2(), "FRsmkb%02d.BMP", 1026, 100, KEY),           # Smokescreen (225) v2 slot 1: per-hex ash puff at the cast (72x72, 20 x 2 ticks, MULTIPLY like Cloud of Ashes)
              (5670, smoke_bank(), "FRsmkk%02d.BMP", 1026, 100, KEY),             # Smokescreen (225) v2 slot 3: the whole-area Cloud-of-Ashes bank (272x208, 48 x 3 ticks, drawn by the centre hex only)
              (5718, smoke_bank_intro(), "FRsmki%02d.BMP", 1026, 100, KEY),       # Smokescreen (225) v3 slot 4: the bank GROWS IN (272x208, 20 frames; frame 19 == loop frame 19)
              (4350, mend5_rocks(1), "ERmrkB%02d.BMP", 258, 90, KEY),       # Mend Walls (216) v5 slot 4: debris layout B (50 x 1 tick)
              (4500, mend5_rocks(0), "ERmrkA%02d.BMP", 258, 90, KEY),       # Mend Walls (216) v5 slot 3: grey rocks + brown sticks, tremble then flung (224x212 alpha, 50 x 1 tick)
              (4900, mend6_glow(), "ERmgl6%02d.BMP", 770, 90, 0x0000),      # Mend Walls (216) v6 slot 1: wall glow re-timed to the staggered hits (blank + 51 frames, 4900-4951)
              (4800, mend5_halo(0), "ERmhlA%02d.BMP", 770, 60, 0x0000),     # Mend Walls (216) v5 slot 5: subtle green glow on debris layout A (additive, 50 x 1 tick)
              (4850, mend5_halo(1), "ERmhlB%02d.BMP", 770, 60, 0x0000),     # Mend Walls (216) v5 slot 6: ... layout B
              (5000, mend7_rocks(False), "ERm7r%02d.BMP", 258, 90, KEY),    # Mend Walls (216) v7 slot 3: ONE grey rock (blank + 8 grow + 12 tremble loop + 15 post; 48x56, engine-moved)
              (5036, mend7_rocks(True), "ERm7s%02d.BMP", 258, 90, KEY),     # Mend Walls (216) v7 slot 4: ONE brown stick (same timeline)
              (5072, mend7_halo(), "ERm7h%02d.BMP", 770, 60, 0x0000),       # Mend Walls (216) v7 slot 5: its subtle green halo + the small arrival burst (additive)
              (5108, mend7_hole(), "ERm7g%02d.BMP", 258, 90, KEY),          # Mend Walls (216) v7 slot 7: the torn ground at the source hex (stationary)
              (5144, mend7_glow(), "ERm7w%02d.BMP", 770, 90, 0x0000),       # Mend Walls (216) v7 slot 1: wall glow without baked bursts (blank + 51; 96x112)
              (4400, steadfast_shield(mask=_sf3_heater), "ERsfsh%02d.BMP", 770, 80, 0x0000),    # Steadfast (218) v3 slot 3: per-unit HEATER shield driver (96x128, 26 frames)
              (4300, tectonic_dust(), "ERtect%d.BMP", 770, 40, 0x0000),            # Tectonic Shift (219) slots 0-2: Air Mastery map-wide drift = ochre dust, glowing fissure, grit (200x116)
              (4600, tectonic_motes_lv(), "ERtml%02d.BMP", 770, 70, 0x0000),     # Tectonic Shift (219) v4 slots 0-2: mote clusters x 10 brightness levels (4600-4629)
              (4630, tectonic_crack_lv(), "ERtcl%02d.BMP", 770, 90, 0x0000),     # 219 v4 slots 4-6: fissure line / parting edges x 10 levels (4630-4659)
              (4660, tectonic_gap_lv(), "ERtgp%02d.BMP", 770, 85, 0x0000),       # 219 v4 slots 7-9: the open glowing gap x 10 levels (4660-4689)
              (4750, tectonic_glow4(), "ERtgv%02d.BMP", 770, 65, 0x0000),        # 219 slot 3 v4: per-hex glow, NO hex rim (soft round wash + rising motes, ~10 % dimmer than v3; 32x40, 48 x 2 ticks)
              (3954, mend_stone(), "ERmstone%d.BMP", 256, 0, KEY),          # Mend Walls (216) slot 0: tumbling stone block projectile (64x66, opaque keyed like boulders)
              (3962, mend_trail(), "ERmtrail%d.BMP", 770, 50, 0x0000),      # Mend Walls (216) slot 1: amber grit trail (64x66)
              (3966, mend_impact(), "ERmend%02d.BMP", 770, 80, 0x0000),     # Mend Walls (216) slot 2: dust ring + settling earth-glow per landed hex (96x72, hit at (48,44))
              (4250, steadfast_ward(), "ERstead%02d.BMP", 770, 85, 0x0000),      # Steadfast (218) slot 2: per-hex landing (96x80, additive)
              (1100, forge_explosion(), "EFboom%02d.BMP", 258, 90, KEY),         # Forge Blast v2: explosion over the city (128x128)
              (1120, oil_tile(), "EFoiltile%d.BMP", 258, 95, KEY),               # Oil Spring v3 slot 3: the oil hex tile (5 variants, 75x91 like Ooze's mud tiles)
              (1130, oil_glob(), "EFoilglob%d.BMP", 258, 90, KEY),               # Oil Spring v3 slot 0: falling oil glob (32x32)
              (1136, oil_trail(), "EFoiltrail%d.BMP", 258, 85, KEY),             # Oil Spring v3 slot 1: drip trail (32x32)
              (1140, oil_hit(), "EFoilhit%d.BMP", 258, 90, KEY),                 # Oil Spring v3 slot 2: splash where a glob lands (64x64)
              (1150, city_sparkle(), "EFcityench%02d.BMP", 258, 90, KEY),         # city enchantment shimmer (48x48, 12 frames) = spell 375 gfx slot 1
              (1200, sand_puff(), "FAsand%02d.BMP", 258, 90, KEY),                # Sandstorm (388) slot 0: the stinging dust devil per strike (32x32, 10 frames)
              (1210, implosion_fx(), "FAimplo%02d.BMP", 258, 90, KEY),            # Implosion (389) slot 2: debris sucked in, then the flash (96x96, 14 frames)
              (1230, rage_flare(), "FArage%02d.BMP", 258, 90, KEY),               # Frenzied Charge (390) slot 0: per-unit rage flare (24x24, 8 frames)
              (1240, rage_whirl(), "FAwhirl%02d.BMP", 258, 90, KEY),              # Frenzied Charge (390) slot 1: the caster's fire whirl (96x96, 21 frames)
              (1270, heat_flare(), "FAheat%d.BMP", 258, 90, KEY),                 # Drought (391): sun flare twinkle (24x24, 4 frames; unused since v2)
              (1274, drought_particles(), "FAdrop%d.BMP", 770, 50, KEY),
              (1450, drought_glow(), "FAdglow%02d.BMP", 770, 70, KEY),
              (1470, scald_seq(), "FWscald%02d.BMP", 770, 100, KEY),
              (1490, bloodboil_seq(), "FWboil%02d.BMP", 770, 100, KEY),
              (1510, steam_puff(), "FWpuff%02d.BMP", 770, 100, KEY),
              (1520, ed_summon(), "EDsumm%02d.BMP", 770, 50, 0x0000),
              (1540, silk_tuft(), "EDtuft%d.BMP", 770, 100, KEY),               # Thousand Threads (335) hail slot 0: silk tuft projectile
              (1550, silk_trail(), "EDtrail%d.BMP", 770, 90, KEY),              # Thousand Threads (335) hail slot 1: thread trail
              (1560, web_burst(), "EDweb%d.BMP", 770, 100, KEY),
              (1570, rot_glob(), "EDrot%d.BMP", 770, 100, KEY),                 # Rot Away (333) hail slot 0: rot glob projectile
              (1580, rot_trail(), "EDrott%d.BMP", 770, 90, KEY),               # Rot Away (333) hail slot 1: dripping trail
              (1590, rot_burst(), "EDrotb%02d.BMP", 770, 100, KEY),
              (1610, rot_boil_seq(), "EDboil%02d.BMP", 770, 100, KEY),          # Rot Away (333) v2 slot 2: green boil (Blood Boil recoloured)
              (1630, silk_spin(), "EDspin%02d.BMP", 770, 100, KEY),
              (1650, rot_status(), "EDrots%02d.BMP", 1026, 35, KEY),
              (1670, gold_motes(), "ELgold%d.BMP", 770, 50, KEY),
              (1680, spirit_rise(), "ELspir%02d.BMP", 770, 100, KEY),           # Awaken Spirit (300) per-unit aura: rising spirit wisps
              (1700, leaf_fall(), "ELleaf%02d.BMP", 770, 100, KEY),
              (1720, spirit_mote(), "ELsmot%d.BMP", 770, 100, KEY),             # Awaken Spirit (300) slot 0: rising spirit mote
              (1724, leaf_mote(), "ELlmot%d.BMP", 770, 100, KEY),
              (1726, big_boulder(), "EAbould%d.BMP", 258, 100, KEY),            # Hurl Boulder (365) hail slot 0: the big stone (64x64, 4 frames)
              (1730, boulder_dust(), "EAdust%d.BMP", 258, 70, KEY),             # Hurl Boulder (365) hail slot 1: dust trail behind the stone
              (1734, rock_impact(), "EArock%02d.BMP", 258, 95, KEY),            # Hurl Boulder (365) hail slot 2: the stone shatters (64x64, 10 frames)
              (1750, gravity_well(), "EAgrav%02d.BMP", 258, 95, KEY),
              (1766, gravity_field(), "EAfield%02d.BMP", 258, 70, KEY),
              (1778, boulder_glow(), "EAbglow%02d.BMP", 770, 100, 0x0000),
              (1820, boulder_rise(), "EArise%02d.BMP", 258, 100, KEY),
              (1840, leaf_drift(), "EWleaf%d.BMP", 770, 35, 0x0000),
              (1860, overgrowth_glow(), "EWglow%02d.BMP", 770, 70, KEY),
              (1940, grass_drift(), "LWgrass%d.BMP", 770, 35, 0x0000),
              (1920, dew_veil(), "LWdew%d.BMP", 770, 45, 0x0000),
              (1900, harvest_twinkle(), "LWharv%d.BMP", 770, 60, 0x0000),
              (1960, harvest_drift(), "LWhdrift%d.BMP", 770, 35, 0x0000),
              (1980, harvest_glow(), "LWcropglow%02d.BMP", 770, 100, KEY),
              (2010, soul_siphon(), "WDsiphon%02d.BMP", 770, 100, 0x0000),
              (2022, soul_mote(), "WDmote%d.BMP", 770, 55, 0x0000),                # Soul Siphon (340) slot 2: soul mote flying target -> caster (22x22, kind 0x1F)
              (2060, soul_linger(), "WDlinger%02d.BMP", 770, 90, 0x0000),
              (2090, rot_status(), "WDplagueglow%02d.BMP", 1026, 80, KEY),        # Plague (341) slot 3: the Rot overlay frames at a STRONGER blend (80 vs Rot's 35; user: too subtle) on plagued city hexes          # Soul Siphon (340) slot 1: lingering vortex at the target (64x64, 30 frames, kind-0x26 driver)
              (2050, black_droplets(), "WDtide%d.BMP", 770, 60, 0x0000),
              (2130, silver_motes(), "WAnimue%d.BMP", 770, 90, 0x0000),   # Nimue v2: blue water drop + ripples
              (2150, snow_drift(), "WAsnow%d.BMP", 770, 40, 0x0000),
              (2885, sanctify_strike(), "LSsanct%02d.BMP", 770, 85, 0x0000),    # Sanctify (208) slot 2: per-hex landing (96x80, additive)
              (2901, sanctify_field(), "LSfield%02d.BMP", 770, 60, 0x0000),     # Sanctify (208) slot 3: consecrated-hex loop (64x40, additive)
              (2210, ice_sparkle(), "WAiceg%02d.BMP", 770, 55, KEY),
              (2222, drought_sparkle(), "FAdspark%02d.BMP", 770, 22, KEY),
              (2234, heat_drift(), "FAheat%d.BMP", 770, 40, 0x0000),   # Drought (391) slots 0-2 v3: Air Mastery map-wide drift = red/orange heat haze + embers (200x116)   # Drought (391) slot 1 v3: Ice Age's sparkle in red/orange on desertified hexes (64x64)               # Ice Age (399) slot 3: Freeze Water's sparkle (SWARM 20-31) at blend 55 on frozen hexes (64x64)
              (2110, mist_swirl(), "WAmist%02d.BMP", 770, 90, 0x0000),           # Misty Step (396) slot 0: mist swirl at origin + destination (64x64, Void Step canvas)
              (2170, frost_burst(), "WAfrost%02d.BMP", 770, 100, 0x0000),
              (2252, frost_ring(), "WAfring%02d.BMP", 770, 90, 0x0000),
              (2555, suffocate_puff(), "ADspuff%02d.BMP", 770, 90, 0x0000),   # v2: 16 frames x 1 tick -> 2555-2570 (2383-2390 unused)   # Suffocate (345) slot 0 v6: per-hit gasp of breath (74x80, hit on the last frame)
              (2507, suffocate_drain(), "ADsdrain%02d.BMP", 770, 90, 0x0000),   # v3: 48 frames -> 2507-2554 (2391-2422 unused)   # Suffocate (345) slot 1: whole-cast drain, sparse motes drawn outward (160x120, patch_tc_suffocate_v1.py)   # v5: 16 frames 96x96 -> 2367-2382 (2276-2283 unused)
              (2303, borrow_hourglass(), "ADborrow%02d.BMP", 770, 90, 0x0000),
              (2571, banshee_vortex(), "ADvortex%03d.BMP", 1026, 90, KEY),
              (2679, chorus_spark(), "LAspark%d.BMP", 770, 80, 0x0000),   # Heavenly Chorus (308) slot 0: rising golden sparkle (16x16)
              (2815, chorus_aura(), "LAaura%02d.BMP", 770, 85, 0x0000),   # v5: 30 frames -> 2815-2844 (2791-2814 unused)   # v4: 24 frames -> 2791-2814 (2683-2698 unused)   # Heavenly Chorus (308) slot 1: per-unit golden aura + halo + notes (48x64)
              (2770, inspire_burst(), "LAinsp%02d.BMP", 770, 85, 0x0000),   # v3: 16 frames -> 2770-2785 (2699-2712 unused)
              (2845, secondwind_swirl(), "LAsw%02d.BMP", 770, 90, 0x0000),   # v5: 40 frames (~2.7 s = the sound) -> 2845-2884 (2745-2764 unused)   # v2: 20 frames 96x96 -> 2745-2764 (2713-2728 unused)   # Second Wind (310) slot 0: air swirl + heal motes (64x64)
              (2765, angelwings_emblem(), "LAawemb%d.BMP", 770, 100, 0x0000),
              (2964, _icon_emblem("glyph_undying", (235, 235, 235)), "DEundemb%d.BMP", 770, 100, 0x0000),   # Undying (210) emblem: its icon glowing x5 strengths (replaces Water Walking's ENCHANT emblem)
              (2786, _icon_emblem("glyph_swampwalk"), "EWswemb%d.BMP", 770, 100, 0x0000),   # Swampwalk (382) emblem: its icon glowing (replaces Water Walking's ENCHANT emblem)   # Angel Wings (311): glowing icon emblem x5 strengths (replaces Water Walking's ENCHANT 45-49 in the donor chain; 2729-2744 unused)   # Angel Wings (311) slot 0: halo flash + wing glow + feathers (64x64)   # Inspiration (309) slot 2: per-hex golden ray burst (96x80)   # v6: 84 frames -> 2423-2506 (2323-2366 unused)   # v4: MULTIPLY/dark like Mind Decay's particle   # Banshee Gale (344) slot 1: the spinning gale, 44 frames rise/loop/loop/fade (224x160, patch_tc_banshee_vortex_v1.py)   # v3: 20 frames (slower) -> 2303-2322 (2284-2299 unused since)
              (2300, banshee_wisp(), "ADwisp%d.BMP", 770, 70, 0x0000),   # Banshee Gale (344) slot 0: ghost wisp left along each thrown unit's path (20x20)   # Borrow Time (346) slot 0: ghost hourglass, sand running up, clock hand, wisps (64x64, Martyr canvas)   # Suffocate (345) slot 0: choking coil per strike, peaks on the hit frame (74x80, Vaporize canvas)   # v3 2026-10-15: 24 frames (slower) -> moved to 2252-2275 (2190-2209 unused since)
              (2240, frost_fade(), "WAffade%02d.BMP", 770, 100, 0x0000),   # Flashfreeze (397) slot 2: fade-out after each hit (74x80, burst canvas; patch_tc_flashfreeze_v1.py v3 spawns it at landing)   # Flashfreeze (397) slot 1: shrinking ice-shard ring at the target (160x96, kind-0x26 driver, patch_tc_flashfreeze_v1.py)         # Flashfreeze (397) slot 0: ice-shard burst per strike (74x80, Vaporize canvas)               # Ice Age (399) slots 0-2: Air Mastery map-wide drift = snowflakes + frost (200x116)            # Nimue's Favour (398) slot 0: Earth Mastery map-wide particles = blue-silver water motes (20x20)
              (2030, plague_miasma(), "WDplague%d.BMP", 770, 45, 0x0000),          # Plague (341) slots 0-2: Death Mastery map-wide drift = sickly miasma, spores, flies (200x100)          # Black Tide (342) slot 0: Earth Mastery map-wide particles = dark teal droplets (20x20)         # Soul Siphon (340) slot 0: violet vortex + soul wisps pulled up out of the target (64x64)         # Bountiful Harvest (325) slot 3: green/gold glow on crop fields (32x24, 12 frames, patch_harvest_v1.py v6)          # Bountiful Harvest (325) slots 0-2 v2: map-wide golden drift (Death Mastery drift; 200x116 additive)
              (1880, holy_spray(), "LWholy%d.BMP", 770, 40, 0x0000),              # Holy Water (324) slot 0: per-strike holy water spray along the breath fan (64x64, additive)          # Bountiful Harvest (325) slot 0: golden grain twinkle at the capital (54x48, additive)                 # Blessed Dew (326) slots 0-2: drifting dew veil for Death Mastery's map-wide animation (200x100, additive)            # World Healer (327) slots 0-2: drifting grass for Air Mastery's map-wide animation (200x116, additive)         # Overgrowth (383) slot 3: subtle green glow on overgrown hexes (32x24, 12 frames, patch_drought_glow_v1.py v2)              # Overgrowth (383) slots 0-2: drifting leaves for Air Mastery's map-wide animation (200x116, additive)          # Hurl Boulder (365) slot 1 v2: caster magic + the boulder shaking and rising from the ground (96x96, 18 frames); 1778-1789 unused since      # Hurl Boulder (365) slot 1: pre-throw glow at the caster (64x64, 12 frames, patch_hurlboulder_glow_v1.py)
              (1800, gravity_well_v2(), "EAgrv2%02d.BMP", 770, 100, 0x0000),    # Gravity Well (366) slot 2 v2: additive glowing purple motes spiralling in + core flash (96x80, 20 frames); 1750-1765 unused since         # Gravity Well (366) v2 slot 3: the lingering well, seamless loop (64x40, 12 frames)           # Gravity Well (366) hail slot 2: contracting rings + grit pulled in (80x64, 16 frames)               # Blessing of the Forest (301) slot 0: rising leaf             # Blessing of the Forest (301) per-unit aura: falling leaves               # Golden Age (302) slot 0: map-wide gold twinkles (Earth Mastery world effect)            # Rot 0xB5 status overlay: Cursed (SEffect 50-65) tinted dark green, multiply             # Thousand Threads (335) v2 slot 2: silk spinning round each hex            # Rot Away (333) hail slot 2: rot splatter + spores                # Thousand Threads (335) hail slot 2: web burst on the hex          # Earth/Death summons slot 0: green-grey summon glow (MAGIC 20-31 tinted)              # Steam Power (406) slot 0: map-wide steam puffs (Fire Mastery's animation)          # Blood Boil (404) slot 0: boiling bubbles + crimson steam, 16 frames on Vaporize's canvas             # Scald (405) slot 0: ground burst -> steam (Geyser x Vaporize), 14 frames on Vaporize's canvas            # Drought (391) slot 1: the subtle glow on desertified hexes (32x24, 12 frames)         # Drought (391) cast slot: PARTICLE 0-2 re-coloured red (v2)
              (1280, implosion_ring(), "FAring%02d.BMP", 258, 90, KEY),           # Implosion (389) slot 3: the red particle ring shrinking into the target (128x128, 14 frames)
              (1294, sand_streak(), "FAsandh%d.BMP", 258, 90, KEY),               # Sandstorm v2 (388) slot 0: the falling sand lash (32x32, 4 frames)
              (1298, sand_trail(), "FAsandt%d.BMP", 258, 85, KEY),                # Sandstorm v2 (388) slot 1: trail (1 frame)
              (1300, sand_clump(), "FAsandc%d.BMP", 258, 90, KEY),                # Sandstorm v3 (388) slot 0: the falling sand clump (24x24, 4 frames)
              (1304, sand_burst(), "FAsandb%d.BMP", 258, 90, KEY),                # Sandstorm v3 (388) slot 2: the dust burst at the hex (48x48, 8 frames)
              (1312, crossed_swords(), "FAswords%02d.BMP", 770, 90, KEY),         # Frenzied Charge v3 (390) slot 0: two red swords crossing above the unit (48x48, 12 frames)
              (1360, implosion_seq(), "FAimp%02d.BMP", 514, 100, KEY),            # Implosion v4 (389) slot 3: red twinkle ring contracting + Fireball's full explosion (280x280, 44 frames)
              (1410, sand_swirl_rise(), "FAswr%d.BMP", 770, 80, KEY),             # Sandstorm v4 (388) slot 4: the swirl rising (224x160, 8 frames)
              (1418, sand_swirl_loop(), "FAswl%02d.BMP", 770, 80, KEY),           # Sandstorm v4 (388) slot 5: the swirl loop (12 frames)
              (1430, sand_swirl_end(), "FAswe%02d.BMP", 770, 80, KEY)]            # Sandstorm v4 (388) slot 6: 11 blank + 8 fade frames
    pix = bytearray(); images = []
    for base, frames, nm, draw, blend, key in groups:
        for i, im in enumerate(frames):
            r, data = rec_for(im, nm % i, draw, blend, key, i, ptype=16 if base in (200, 334) else 22)
            r["off"] = len(pix); pix += data
            images.append({"id": base + i, "composite": False, "parts": [r], "empty": False})
    lib = {"someId": 0x0040F000, "version": 4.0, "hdrLength": 24, "palettes": [], "images": images, "pixeldata": bytes(pix)}
    out = ilbcodec.write(lib)
    chk = ilbcodec.read(out); assert [i["id"] for i in chk["images"]] == [i["id"] for i in images]
    return out, groups


def preview(groups, path):
    cols = 30
    rows = []
    for base, frames, nm, draw, blend, key in groups:
        W = max(f.width for f in frames); H = max(f.height for f in frames)
        strip = Image.new("RGB", (min(len(frames), cols) * (W + 2), H + 12), (70, 70, 70)); dr = ImageDraw.Draw(strip)
        for i, f in enumerate(frames[:cols]):
            strip.paste(f, (i * (W + 2), 12), f); dr.text((i * (W + 2), 0), str(base + i), fill=(255, 255, 0))
        rows.append(strip)
    Wt = max(r.width for r in rows); Ht = sum(r.height + 4 for r in rows)
    S = Image.new("RGB", (Wt, Ht), (70, 70, 70)); y = 0
    for r in rows: S.paste(r, (0, y)); y += r.height + 4
    S = S.resize((S.width * 2, S.height * 2), Image.NEAREST); S.save(path); print("preview ->", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    if a.revert:
        if os.path.exists(OUT): os.remove(OUT); print("deleted", OUT)
        return 0
    out, groups = build()
    if a.preview:
        preview(groups, os.path.join(HERE, "dualdf_preview.png")); return 0
    cur = open(OUT, "rb").read() if os.path.exists(OUT) else None
    print("DualDF.ILB: %d bytes, %d images%s" % (len(out), sum(len(g[1]) for g in groups), " (unchanged)" if cur == out else ""))
    if cur == out: print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    open(OUT, "wb").write(out); print("written", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
