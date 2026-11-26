#!/usr/bin/env python3
r"""
SPELLICN.ILB: icons for the dual-sphere (Death/Fire) spells (2026-10-06).

Spell icons are COMPOSITE images keyed by IMAGE ID (not ordinal): frame 0 = the sphere's 40x35 colour cloud
(type 22 Sprite16, drawMode 770 / blend 30, drawn additively as a glow backdrop), frame 1 = black ink glyph on
WHITE (0xFFFF keyed out; drawMode 1026 / blend 100, clip box = the glyph's bounding sub-frame).  Vanilla ids:
0-15 Air, 20-35 Death, 40-55 Earth, 60-75 Fire, 80-95 Life, 100-115 Water, 120-127 Cosmos; 150-156/200 custom.

Dual-sphere cloud = the real Death cloud (image 20, frame 0) blended into the real Fire cloud (image 60, frame 0)
with a smooth left->right fade (smoothstep across the middle 50% of the width, Death on the left, Fire on the
right) - "50/50 Death and Fire colour with a smooth transition".  Glyphs are painted procedurally at 8x and
downsampled to 1-bit ink (same pipeline as build_magic_sight_icon2.py).

New image ids = the spell ids (350 Bloodbath, 351 Summon Hell Hound, 354 Hellfire); records are APPENDED through
old modding tools\research\ilbcodec.py (full lossless rewrite, header offsets recomputed), existing images are
untouched.  patch_dual_sphere_spells_v1.py references them via its SPELLS[...]["icon"] values.

--preview writes dual_icons_preview.png next to this script (cloud / glyph / composite / 4x) and stops.
Backup <game>\backup\SpellIcn.ILB.bak_dualicons.  --revert restores it.  Dry run by default; --apply.
"""
import argparse, random, random, math, os, shutil, struct, sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "old modding tools", "research"))
from bakpath import bak_path, game_dir, game_file
import ilbcodec
import numpy as np

GAME = game_dir()   # 2026-10-11: de-baked (AOW_GAME_DIR or parent of patch scripts)
ILB = os.path.join(GAME, "Images", "SpellIcn.ILB")
BAK_SUFFIX = ".bak_dualicons"
DEATH_ID, FIRE_ID = 20, 60              # cloud donors (frame 0)
W, H = 40, 35
ICONS = {350: "bloodbath", 351: "hellhound", 354: "hellfire", 205: "wither", 204: "rejuvenate", 206: "repent", 207: "harvest",
         360: "martyr", 361: "cleansing", 362: "phoenix", 363: "starfire",          # 360-363 = Life/Fire (2026-10-13)
         353: "ashes",                                                                 # Death/Fire tier 3 (2026-10-13)
         372: "oil_spring", 373: "lionheart", 374: "forge_blast", 375: "arms_race",      # Earth/Fire 1-4 (2026-10-13)
         388: "sandstorm", 389: "implosion", 390: "frenzy", 391: "drought",              # Fire/Air 1-4 (2026-10-14)
         404: "bloodboil", 405: "scald", 406: "steampower",                               # Fire/Water 1-3 (2026-10-14)
         332: "direwolf", 333: "rotaway", 334: "werewolf", 335: "threads",                 # Earth/Death 1-4 (2026-10-14)
         300: "awaken", 301: "forest_blessing", 302: "golden_age", 303: "ent",             # Earth/Life 1-4 (2026-10-14)
         364: "mammoth", 365: "hurl_boulder", 366: "gravity_well",                         # Earth/Air 1-3 (2026-10-14)
         380: "slow", 381: "crocodile", 382: "swampwalk", 383: "overgrowth",                # Earth/Water 1-4 (2026-10-15)
         324: "holywater", 325: "bountiful", 326: "blesseddew", 327: "worldhealer",           # Life/Water 1-4 (2026-10-15)
         340: "soulsiphon", 341: "plague", 342: "blacktide", 343: "hydra",                  # Water/Death 1-4 (2026-10-15)
         396: "mistystep", 397: "flashfreeze", 398: "nimue", 399: "iceage",
         344: "banshee", 345: "suffocate_lungs", 346: "borrowtime", 347: "succubus",
         308: "chorus", 309: "inspire", 310: "secondwind", 311: "angelwings", 208: "sanctify", 209: "miracle", 210: "undying", 211: "callofdead", 212: "gust", 213: "crosswind", 214: "suspend", 215: "staticshield", 216: "mendwalls", 233: "mimic", 232: "lucky", 235: "transmutation", 234: "reversalspell", 231: "essenceshift", 229: "cityspy", 230: "royalambition", 228: "magicmissile", 227: "pyroclasm", 225: "smokescreen", 226: "walloflames", 222: "seaserpent", 223: "flashflood", 220: "crashingwave", 221: "riteseas", 219: "tectonic", 217: "depthsofplenty", 218: "steadfast"}                     # Life/Air 1-4 (2026-10-16)                                                   # Air/Death 2, 4 (2026-10-15)                # Water/Air 1-4 (2026-10-15)
# 2026-10-12: COPIES = icons taken verbatim from another ILB (image id there): 204 = the vanilla 1.36 Rejuvenate icon 88
# (the live image 88 was overdrawn for Summon Mermaid, which keeps it)
VANILLA_ILB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference files", "AoW 1.36", "Images", "SpellIcn.ILB")
COPIES = {"rejuvenate": (VANILLA_ILB, 88)}
# 2026-10-22 (user): 380 Slow keeps the VANILLA glyph (vanilla SpellIcn 52, frame 1) but sits on the Earth->Water cloud
# like the other Earth/Water spells (10/15 it was a verbatim COPIES entry = green Earth cloud only)
GLYPH_COPIES = {"slow": (VANILLA_ILB, 52)}
FRENZY_MASK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frenzy_user_mask.png")   # v16 user reference trace; kept up here (10/15) so glyph swaps "up to the next def" can't swallow it
# 2026-10-12: cloud per icon - "blend" = the Death->Fire blend, an int = that vanilla icon's own frame-0 cloud
CLOUDS = {"bloodbath": "blend", "hellhound": "blend", "hellfire": "blend", "rejuvenate": 80, "wither": 20, "repent": 80, "harvest": 20,
          "martyr": (80, 60), "cleansing": (80, 60), "phoenix": (80, 60), "starfire": (80, 60),   # (a, b) = a's cloud -> b's cloud blend (Life -> Fire)
          "ashes": "blend",
          "oil_spring": (40, 60), "lionheart": (40, 60), "forge_blast": (40, 60), "arms_race": (40, 60),   # Earth (Stone Skin's cloud) -> Fire
          "sandstorm": (0, 60), "implosion": (0, 60), "frenzy": (0, 60), "drought": (0, 60),             # Air (Haste's cloud) -> Fire
          "bloodboil": (60, 100), "scald": (60, 100), "steampower": (60, 100),                         # Fire -> Water (Water ink/cloud 100)
          "direwolf": (40, 20), "rotaway": (40, 20), "werewolf": (40, 20), "threads": (40, 20),         # Earth -> Death
          "awaken": (40, 80), "forest_blessing": (40, 80), "golden_age": (40, 80), "ent": (40, 80),     # Earth -> Life
          "mammoth": (40, 0), "hurl_boulder": (40, 0), "gravity_well": (40, 0),                        # Earth -> Air
          "slow": (40, 100), "crocodile": (40, 100), "swampwalk": (40, 100), "overgrowth": (40, 100),  # Earth -> Water
          "holywater": (80, 100), "bountiful": (80, 100), "blesseddew": (80, 100), "worldhealer": (80, 100),   # Life -> Water
          "soulsiphon": (20, 100), "plague": (20, 100), "blacktide": (20, 100), "hydra": (20, 100),           # Death -> Water
          "mistystep": (0, 100), "flashfreeze": (0, 100), "nimue": (0, 100), "iceage": (0, 100),
          "banshee": (0, 20), "suffocate_lungs": (0, 20), "borrowtime": (0, 20), "succubus": (0, 20),
          "chorus": (80, 0), "inspire": (80, 0), "secondwind": (80, 0), "angelwings": (80, 0), "sanctify": 80, "miracle": 80, "undying": 20, "callofdead": 20, "gust": 0, "crosswind": 0, "suspend": 0, "staticshield": 0, "mendwalls": 40, "mimic": 151, "lucky": 151, "transmutation": 151, "reversalspell": 151, "essenceshift": 120, "cityspy": 120, "royalambition": 120, "magicmissile": 120, "pyroclasm": 60, "smokescreen": 60, "walloflames": 60, "seaserpent": 100, "flashflood": 100, "crashingwave": 100, "riteseas": 100, "tectonic": 40, "depthsofplenty": 40, "steadfast": 40}         # Life -> Air                                                         # Air -> Death              # Air -> Water


# ---------------------------------------------------------------- pixel helpers
def c565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def frame_pixels(lib, img_id, part):
    img = next(i for i in lib["images"] if i["id"] == img_id)
    r = img["parts"][part]
    base = lib["pixeldata"]
    off = r["off"]
    px = [[c565(struct.unpack_from("<H", base, off + (y * r["cw"] + x) * 2)[0]) for x in range(r["cw"])] for y in range(r["ch"])]
    return r, px


def blended_cloud(lib, a_id=DEATH_ID, b_id=FIRE_ID):
    """Death cloud -> Fire cloud (or any a -> b), smoothstep fade over x in [0.25, 0.75] of the width."""
    rd, dpx = frame_pixels(lib, a_id, 0)
    rf, fpx = frame_pixels(lib, b_id, 0)
    assert (rd["cw"], rd["ch"]) == (W, H) == (rf["cw"], rf["ch"])
    out = []
    for y in range(H):
        row = []
        for x in range(W):
            t = (x / (W - 1) - 0.25) / 0.5
            t = 0.0 if t < 0 else 1.0 if t > 1 else t * t * (3 - 2 * t)
            a, b = dpx[y][x], fpx[y][x]
            row.append(tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3)))
        out.append(row)
    return out


# ---------------------------------------------------------------- glyphs (ink = True) painted at 8x on a 40x35 canvas
S = 8


def canvas():
    return Image.new("L", (W * S, H * S), 0)


def teardrop(dr, cx, cy, r, tip_up=True, fill=255):
    """A drop: circle of radius r plus a triangle tip (height ~1.6r) pointing up (tip_up) or down."""
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    k = 0.985
    if tip_up:
        dr.polygon([(cx - r * k, cy - r * 0.15), (cx + r * k, cy - r * 0.15), (cx, cy - r * 2.3)], fill=fill)
    else:
        dr.polygon([(cx - r * k, cy + r * 0.15), (cx + r * k, cy + r * 0.15), (cx, cy + r * 2.3)], fill=fill)


def flame(dr, cx, base_y, h, w, fill=255, lean=0.0):
    """Stylised flame tongue: wavy polygon with a pointed top."""
    pts = []
    n = 14
    for i in range(n + 1):
        t = i / n                                   # 0 bottom-left .. 1 top
        y = base_y - h * t
        x = cx - w * (1 - t) * (0.5 + 0.18 * math.sin(t * 7)) + lean * h * t
        pts.append((x, y))
    for i in range(n, -1, -1):
        t = i / n
        y = base_y - h * t
        x = cx + w * (1 - t) * (0.5 + 0.18 * math.sin(t * 7 + 1.5)) + lean * h * t
        pts.append((x, y))
    dr.polygon(pts, fill=fill)


def glyph_bloodbath():
    """v2 (2026-10-10): three BIG blood drops, no splash pool, and the centre drop is a skull - two slanted eye
    sockets, a nasal hole and a row of teeth cut out of its round body (the drop's round bottom = the jaw)."""
    im = canvas(); dr = ImageDraw.Draw(im)
    teardrop(dr, 20 * S, 21 * S, 8.3 * S, tip_up=True)
    teardrop(dr, 6.6 * S, 17 * S, 4.0 * S, tip_up=True)
    teardrop(dr, 33.6 * S, 14 * S, 3.6 * S, tip_up=True)
    # skull features cut out of the centre drop: angry inward-slanting sockets, nasal triangle, teeth
    dr.polygon([(14.2 * S, 17.2 * S), (19.3 * S, 18.6 * S), (19.1 * S, 21.8 * S), (14.7 * S, 21.1 * S)], fill=0)
    dr.polygon([(25.8 * S, 17.2 * S), (20.7 * S, 18.6 * S), (20.9 * S, 21.8 * S), (25.3 * S, 21.1 * S)], fill=0)
    dr.polygon([(20 * S, 22.5 * S), (18.4 * S, 25.4 * S), (21.6 * S, 25.4 * S)], fill=0)
    dr.rectangle([15.6 * S, 26.2 * S, 24.4 * S, 28.8 * S], fill=0)                 # the mouth band ...
    for x in (16.7, 19.2, 21.7):                                                    # ... with three teeth left standing
        dr.rectangle([x * S, 26.2 * S, (x + 1.4) * S, 28.8 * S], fill=255)
    return im


def glyph_bloodbath_v1_pool():
    """(superseded 2026-10-10) big drop + two satellites over a jagged splash pool - kept for reference."""
    im = canvas(); dr = ImageDraw.Draw(im)
    teardrop(dr, 20 * S, 15.5 * S, 5.2 * S, tip_up=True)
    teardrop(dr, 9.5 * S, 12 * S, 2.2 * S, tip_up=True)
    teardrop(dr, 30.5 * S, 10 * S, 1.9 * S, tip_up=True)
    cx, cy = 20 * S, 27.5 * S
    pts = []
    for i in range(48):
        a = 2 * math.pi * i / 48
        rr = 1.0 + (0.28 if i % 4 == 0 else 0.0)
        pts.append((cx + math.cos(a) * 15 * S * rr, cy + math.sin(a) * 3.6 * S * rr))
    dr.polygon(pts, fill=255)
    dr.ellipse([17.0 * S, 13.2 * S, 18.8 * S, 15.0 * S], fill=0)
    return im


HOUND_STROKE = 1.1                      # None = solid plume; a float = outline width in icon px (user 10/11: outline style)


# hand-drawn cartoon fire jet in jet-local units (u along the jet, v up; both scaled by L): a throat flaring into
# a body with three slender curling tongues (top one curls up, middle longest, bottom one droops) and deep notches.
JET = [(0.00, 0.04), (0.12, 0.12), (0.24, 0.20), (0.34, 0.26),                              # upper body edge
       (0.40, 0.25), (0.46, 0.33), (0.54, 0.43), (0.62, 0.51), (0.67, 0.54),                 # top tongue, curling up
       (0.62, 0.42), (0.56, 0.30), (0.53, 0.20),                                             # its inner edge, down to the notch
       (0.62, 0.23), (0.76, 0.22), (0.89, 0.17), (1.00, 0.10),                               # middle tongue (longest)
       (0.90, 0.02), (0.78, -0.03), (0.66, -0.05),                                           # its lower edge, to the notch
       (0.72, -0.12), (0.79, -0.22), (0.76, -0.33),                                          # bottom tongue, drooping
       (0.65, -0.28), (0.56, -0.20), (0.48, -0.16),                                          # its inner edge back to the body
       (0.40, -0.20), (0.30, -0.22), (0.18, -0.15), (0.08, -0.08), (0.00, -0.04)]            # lower body edge


# v13 (2026-10-11, "draw inspiration from the Fire Halo icon" = SPELLICN 61: a solid figure ringed by OUTLINED flame
# tongues with slender curling pointed tips): the breath as three long tongues leaving the mouth, drawn as a ~1.3 px
# outline (interior clear), jet-local units (u along the jet, v up), scaled by L.
HALO_JET = [(0.00, 0.05), (0.10, 0.11), (0.20, 0.17), (0.28, 0.24), (0.33, 0.33), (0.36, 0.43), (0.42, 0.52),
            (0.52, 0.58), (0.60, 0.60),                                                   # top tongue tip (curls up)
            (0.52, 0.52), (0.46, 0.42), (0.44, 0.30), (0.48, 0.22),                      # inner side down to the notch
            (0.60, 0.22), (0.74, 0.19), (0.88, 0.14), (1.00, 0.08),                      # middle tongue tip (longest)
            (0.88, 0.05), (0.74, 0.03), (0.62, 0.00), (0.54, -0.05),                     # lower side back to the notch
            (0.62, -0.10), (0.72, -0.18), (0.78, -0.30), (0.76, -0.40),                  # bottom tongue tip (curls down)
            (0.68, -0.32), (0.58, -0.24), (0.48, -0.18), (0.38, -0.16),                  # inner side back to the body
            (0.28, -0.17), (0.18, -0.14), (0.08, -0.08), (0.00, -0.05)]


def halo_lines(im, mx, my, ang, L, lines=((0.22, 1.00, 0.26, 1.0, +1), (0.00, 1.00, 0.04, 1.1, -1), (-0.22, 0.90, -0.22, 0.9, +1)),
               width=(0.9, 1.9), fork_at=0.99, fork_len=0.0, fork_bend=0.0):
    # v13 defaults: forks OFF (at 40x35 a forked tip just clutters - tried 0.36..0.55 L); the Halo flavour is kept as the
    # hooked tips (drift 0.26 / -0.22 = the outer strokes curl up / down at the end).  fork_len > 0 re-enables the forks.
    """Fire Halo (SPELLICN 61) style: thin calligraphic strokes that FORK near the tip into two curling points.  Each
    line = (start v offset, length, drift, wave amplitude px, fork side) in jet-local units (u along the jet,
    v up, fractions of L); the main stroke is thin at the ends and width[1] px in the middle; the branch leaves at
    fork_at, is fork_len long and bends away by fork_bend radians, tapering to a point."""
    ca, sa = math.cos(ang), math.sin(ang)

    def M(u, v):
        return ((mx + u * ca - v * sa) * S, (my + u * sa + v * ca) * S)

    dr = ImageDraw.Draw(im)

    def stroke(pts, w0, w1, profile):
        prev = None
        for i, (u, v) in enumerate(pts):
            t = i / (len(pts) - 1); pt = M(u, v)
            if prev is not None:
                w = (w0 + (w1 - w0) * profile(t)) * S
                dr.line([prev, pt], fill=255, width=max(1, int(w)))
                dr.ellipse([pt[0] - w / 2, pt[1] - w / 2, pt[0] + w / 2, pt[1] + w / 2], fill=255)
            prev = pt

    for v0, ln, drift, amp, side in lines:
        spine = []
        for i in range(41):
            t = i / 40
            u = 0.14 * L + ln * L * t
            v = v0 * L * (1.0 + 0.3 * t) + drift * L * t * t + amp * math.sin(2 * math.pi * 0.9 * t) * min(1.0, 2.0 * t)
            spine.append((u, v))
        stroke(spine, width[0], width[1], lambda t: math.sin(math.pi * t) ** 0.7)
        # the fork: a branch from fork_at that bends away and curls, tapering to a point
        i0 = int(fork_at * 40); u0, v0b = spine[i0]
        u1, v1 = spine[i0 + 1]; d = math.atan2(v1 - v0b, u1 - u0)
        branch = []
        for i in range(21):
            t = i / 20; a = d + side * fork_bend * (0.35 + 0.65 * t)
            step = fork_len * L / 20
            if i == 0: branch.append((u0, v0b))
            else:
                pu, pv = branch[-1]; branch.append((pu + step * math.cos(a), pv + step * math.sin(a)))
        if fork_len > 0: stroke(branch, 0.6, width[1] * 0.95, lambda t: (1 - t) ** 0.6)


def halo_breath(im, mx, my, ang, L, stroke=1.3, v_scale=1.0):
    """Fire Halo style breath: the HALO_JET outline (stroke px wide, interior clear) from the mouth along `ang`,
    joined to the lips by a short solid throat."""
    from PIL import ImageChops, ImageFilter
    ca, sa = math.cos(ang), math.sin(ang)

    def M(u, v):
        u, v = u * L, v * L * v_scale
        return ((mx + u * ca - v * sa) * S, (my + u * sa + v * ca) * S)

    mask = Image.new("L", im.size, 0); ImageDraw.Draw(mask).polygon([M(u, v) for u, v in HALO_JET], fill=255)
    k = int(2 * stroke * S) | 1
    ring = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(k)))
    ImageDraw.Draw(ring).polygon([M(u, v) for u, v in HALO_JET[:2] + [(0.10, -0.11)] + HALO_JET[-1:]], fill=255)
    im.paste(255, mask=ring)


def flame_lines(im, mx, my, ang, L, lines=((0.22, 0.92, 0.06, 1.3), (0.00, 1.00, 0.00, 1.4), (-0.22, 0.86, -0.05, 1.2)),
                width=(0.6, 2.4)):
    """Fire as THREE separate wavy strokes leaving the mouth at (mx, my) along `ang` (image coords): each line =
    (start v offset as a fraction of L, length as a fraction of L, drift of the far end as a fraction of L (+ = up),
    wave amplitude px); v12: the stroke is thin at both ends and width[1] px thick in the middle (width[0] = end width)."""
    ca, sa = math.cos(ang), math.sin(ang)

    def M(u, v):                                          # v > 0 = the upper side of the jet
        return ((mx + u * ca - v * sa) * S, (my + u * sa + v * ca) * S)

    dr = ImageDraw.Draw(im)
    for v0, ln, drift, amp in lines:
        n = 40; prev = None
        for i in range(n + 1):
            t = i / n
            u = 0.14 * L + ln * L * t
            v = v0 * L * (1.0 + 0.35 * t) + drift * L * t * t + amp * math.sin(2 * math.pi * 0.95 * t) * min(1.0, 2.0 * t)   # one gentle S per line, near-parallel
            pt = M(u, v)
            if prev is not None:
                w = (width[0] + (width[1] - width[0]) * math.sin(math.pi * t) ** 0.8) * S   # thin -> thick middle -> thin
                dr.line([prev, pt], fill=255, width=int(w))
                dr.ellipse([pt[0] - w / 2, pt[1] - w / 2, pt[0] + w / 2, pt[1] + w / 2], fill=255)
            prev = pt


HOUND_V7 = [(4.0, 13.5), (3.0, 15.0), (3.6, 16.6), (5.0, 17.6), (8.0, 18.4), (12.0, 19.2), (16.0, 20.4), (17.5, 21.5),
            (16.0, 23.2), (12.0, 24.0), (8.0, 23.6), (6.5, 22.6), (7.2, 25.0), (12.0, 26.2), (18.0, 26.6), (22.0, 28.5),
            (24.0, 34.5), (39.5, 34.5), (39.5, 22.0), (35.0, 15.0), (32.5, 10.5), (36.5, 2.5), (29.5, 7.0), (27.5, 6.8),
            (26.0, 1.0), (22.0, 6.0), (19.0, 6.0), (14.0, 8.2), (11.0, 10.5), (7.0, 12.2)]   # v11: two upright ears


HOUND_HEAD = [(4.0, 13.5), (3.0, 15.0), (3.6, 16.6), (5.0, 17.6), (8.0, 18.4), (12.0, 19.2), (16.0, 20.4), (17.5, 21.5),
              (16.0, 23.2), (12.0, 24.0), (8.0, 23.6), (6.5, 22.6), (7.2, 25.0), (12.0, 26.2), (18.0, 26.6), (22.0, 28.5),
              (26.0, 30.5), (32.0, 30.0), (36.5, 26.5), (39.0, 21.0), (35.0, 15.0), (32.5, 10.5), (36.5, 2.5), (29.5, 7.0),
              (27.5, 6.8), (26.0, 1.0), (22.0, 6.0), (19.0, 6.0), (14.0, 8.2), (11.0, 10.5), (7.0, 12.2)]   # v14: neck trimmed


HALO_MODE = "line"      # "line" = one calligraphic flame line around the head (Fire Halo); "band" = solid flame ring


def flame_ring_outer(cx, cy, R, n, tip, lean, phase, steps=22, hook=0.0, short=0.68):
    """Points of a flame-shaped ring boundary: n tongues on a circle of radius R, each rising `tip` px with an
    S-curve that leans by `lean` radians and drops back steeply to the next base."""
    pts = []
    for k in range(n):
        a0 = phase + 2 * math.pi * k / n; da = 2 * math.pi / n
        tk = tip * (1.0 if k % 2 == 0 else short)             # alternate tall / short tongues
        for i in range(steps):
            t = i / steps
            if t < 0.62:                                    # slow rise with a lean
                u = t / 0.62; r = R + tk * u ** 1.4; a = a0 + da * (0.55 * u) + lean * math.sin(math.pi * u) * 0.5 - hook * u ** 3   # hook = the tip curls back
            else:                                           # steep fall to the next base
                u = (t - 0.62) / 0.38; r = R + tk * (1 - u) ** 0.55; a = a0 + da * (0.55 + 0.45 * u) + lean * 0.5 * (1 - u) ** 2 - hook * (1 - u) ** 3
            pts.append(((cx + r * math.cos(a)) * S, (cy + r * math.sin(a)) * S))
    return pts


def halo_ring(im, cx, cy, R, n=7, tip=6.3, lean=0.45, phase=0.0, stroke=1.35, band=2.6, hook=0.0, short=0.68):
    """Fire Halo ring around (cx, cy).  HALO_MODE "line": the flame boundary drawn as one stroke of `stroke` px;
    "band": a solid flame ring `band` px thick (inner edge = a plain circle)."""
    from PIL import ImageChops, ImageFilter
    outer = flame_ring_outer(cx, cy, R, n, tip, lean, phase, hook=hook, short=short)
    if HALO_MODE == "line":
        dr = ImageDraw.Draw(im); w = stroke * S
        dr.line(outer + outer[:1], fill=255, width=int(w), joint="curve")
        for x, y in outer: dr.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    else:
        mask = Image.new("L", im.size, 0); md = ImageDraw.Draw(mask)
        md.polygon(outer, fill=255)
        r = R - band; md.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=0)
        im.paste(255, mask=mask)


SKETCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hound_sketch.png")
SKETCH_LINE, SKETCH_H, SKETCH_DY = 1.25, 34.0, 0.5     # icon line width px, drawn height px, vertical offset px


# v18 (2026-10-11): the sketch's design (front hound face + flaming mane rising behind it) executed Summon-Boar
# style: solid symmetric silhouettes with cut-out features, a white gap separating the head from the mane.
MANE_R = [(20.0, 0.4), (17.4, 8.2), (14.0, 2.4), (12.2, 10.2), (7.6, 5.8), (9.0, 13.2), (3.0, 10.4), (7.2, 17.0),
          (1.4, 17.6), (7.4, 23.0), (3.6, 28.0), (10.8, 28.6)]   # v21: the v18c burst with one lower side tongue fewer (6 per side)        # right half mirrored from the centre top down the LEFT side (x < 20)
MANE_GAP = 1.3          # white separation around the head, px


MANE_BELLY, MANE_INNER, MANE_SWING, MANE_CENTRE = 1.6, -0.8, 12.0, (20.0, 16.0)   # v21 values (v23 = 2.6, -1.4, 16 reverted)
MANE_ALT = -1.0         # -1.0 = all tongues swing the same way (v21); 0.8 = alternating (v23, reverted by the user)
#MANE_ALT_v23 = 0.8          # v23: alternate tongues swing the other way by this fraction (alternating curves)
MANE_SIDE_FROM, MANE_SIDE_SWING, MANE_SIDE_BELLY, MANE_SIDE_INNER, MANE_SIDE_S = 3, 28.0, 2.4, -1.6, 2.6   # v24: tips 3.. (the three side tongues) curl like Fire Halo
MANE_S = 1.1            # v21: S-curve - each tongue side bends outward near the base and back inward near the tip (px)   # v19: outer bulge px, inner concavity px, tip swing deg


def mane_polygon():
    """v19 (2026-10-11, user: "tongues should curve inward slightly, less spiky"): MANE_R alternates tip / notch
    going from the centre-top down the left side.  Each tip is swung MANE_SWING degrees about MANE_CENTRE toward
    the top (the tongues lean/curl inward like rising flames); the tongue's outer side (tip -> lower notch) bulges
    MANE_BELLY px outward and its inner side (upper notch -> tip) is pulled MANE_INNER px (negative = concave), so
    each tongue is a curved, rounded flame instead of a straight spike."""
    cx, cy = MANE_CENTRE
    left = []
    for i, (x, y) in enumerate(MANE_R):
        if i % 2 == 0 and i > 0:                                        # tips except the central one
            a = math.atan2(y - cy, x - cx); r = math.hypot(x - cx, y - cy)
            sw = MANE_SIDE_SWING if i // 2 >= MANE_SIDE_FROM else MANE_SWING          # v24: side tongues sweep further (Fire Halo curls)
            a += math.radians(sw) * (1 if (i // 2) % 2 == 1 else -MANE_ALT)                               # left side: toward the top (-y) = increasing angle
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        left.append((x, y))
    # v24b (2026-10-11, "on the right side some flames are messed up"): curve the LEFT half only, then mirror the
    # finished curve - both sides are identical by construction (the old per-segment right-side mapping was off).
    cx_, cy_ = cx, cy
    curve = []
    for i in range(len(left) - 1):
        (x0, y0), (x1, y1) = left[i], left[i + 1]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        nx, ny = mx - cx_, my - cy_; d = math.hypot(nx, ny) or 1.0
        outer = (i % 2 == 0)                                             # tip -> notch = the tongue's outer side
        tip_i = (i + 1) // 2                                             # tip this segment belongs to (0 = centre)
        side_t = tip_i >= MANE_SIDE_FROM
        belly, inner, S_ = (MANE_SIDE_BELLY, MANE_SIDE_INNER, MANE_SIDE_S) if side_t else (MANE_BELLY, MANE_INNER, MANE_S)
        kb, kt = (belly if outer else inner), -S_
        k1, k2 = (kt, kb) if outer else (kb, kt)                         # outer segment starts at the tip
        c1x, c1y = x0 + (x1 - x0) / 3 + nx / d * k1, y0 + (y1 - y0) / 3 + ny / d * k1
        c2x, c2y = x0 + 2 * (x1 - x0) / 3 + nx / d * k2, y0 + 2 * (y1 - y0) / 3 + ny / d * k2
        for j in range(8):
            t = j / 8; u = 1 - t
            curve.append((u ** 3 * x0 + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t ** 3 * x1,
                          u ** 3 * y0 + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t ** 3 * y1))
    curve.append(left[-1])
    right = [(40.0 - x, y) for x, y in reversed(curve)]
    out = curve + [(13.0, 28.0), (27.0, 28.0)] + right
    return out


# v22 (2026-10-11, user: "side spikes too triangular/spiky - curvier, alternating curves, i.e. flames"): the mane is
# built from individual flame tongues, each a tapering shape swept along an S-curved spine; the bend direction
# alternates from tongue to tongue.  (angle from the top in degrees, length px, base half-width px, bend px, lean)
MANE_TONGUES = [(0, 7.0, 2.6, 1.4, 0.0), (30, 11.0, 2.8, -2.6, 0.25), (58, 13.0, 2.9, 2.6, 0.45),
                (86, 13.5, 2.9, -2.6, 0.55), (114, 12.5, 2.8, 2.6, 0.6), (142, 11.0, 2.6, -2.4, 0.6)]
MANE_BASE = (20.0, 18.0, 9.5, 10.5)       # ellipse the tongues grow from (cx, cy, rx, ry) - just inside the head's footprint
MANE_WAVE = 0.75                          # S-curve: spine offset = bend * sin(2*pi*MANE_WAVE*t) * taper


def mane_mask(size):
    """Solid flame mane behind the head as a mask: every tongue (both mirror sides) swept along an S spine."""
    mask = Image.new("L", size, 0); dr = ImageDraw.Draw(mask)
    cx, cy, rx, ry = MANE_BASE
    for side in (-1, 1):
        for deg, ln, w0, bend, lean in MANE_TONGUES:
            if deg == 0 and side == 1: continue
            a = math.radians(-90 + side * deg)                                  # radial direction from the top
            bx, by = cx + rx * math.cos(a), cy + ry * math.sin(a)               # base on the ellipse
            d = a * (1 - lean) + math.radians(-90) * lean                       # lean the tongue toward "up"
            dx, dy = math.cos(d), math.sin(d); px, py = -dy, dx                 # spine direction and its normal
            spine = []
            for i in range(21):
                t = i / 20
                off = side * bend * math.sin(2 * math.pi * MANE_WAVE * t) * (1 - 0.35 * t)
                spine.append((bx + dx * ln * t + px * off, by + dy * ln * t + py * off, w0 * (1 - t) ** 0.85 + 0.15))
            left = [(x + px * w, y + py * w) for x, y, w in spine]
            right = [(x - px * w, y - py * w) for x, y, w in spine]
            dr.polygon([(x * S, y * S) for x, y in left + right[::-1]], fill=255)
    dr.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)   # base body (behind the head)
    return mask


def head_mask(dr_mask):
    """Solid front hound head (symmetric about x = 20) - ears, skull, jaw - as a filled mask."""
    def P(pts, fill=255): dr_mask.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def E(x0, y0, x1, y1, fill=255): dr_mask.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)
    P([(11.0, 16.0), (11.6, 5.6), (17.6, 12.2)]); P([(29.0, 16.0), (28.4, 5.6), (22.4, 12.2)])   # ears
    E(10.4, 10.0, 29.6, 25.6)                                                                   # skull
    P([(12.4, 21.0), (27.6, 21.0), (26.6, 28.4), (23.2, 31.6), (16.8, 31.6), (13.4, 28.4)])     # jaw to the chin


def head_features(dr):
    """Cut-outs (white) + fangs (black) drawn over the solid head."""
    def P(pts, fill): dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    P([(12.6, 15.0), (18.6, 17.6), (18.6, 19.8), (13.2, 18.0)], 0)                              # eye slits
    P([(27.4, 15.0), (21.4, 17.6), (21.4, 19.8), (26.8, 18.0)], 0)
    P([(17.4, 21.2), (22.6, 21.2), (20.0, 24.2)], 0)                                            # nose
    P([(13.2, 25.6), (26.8, 25.6), (25.8, 29.4), (20.0, 30.8), (14.2, 29.4)], 0)                # open mouth
    for x, h in ((15.4, 2.8), (24.6, 2.8), (19.0, 1.8), (21.0, 1.8)):                           # upper fangs
        P([(x - 0.9, 25.6), (x + 0.9, 25.6), (x, 25.6 + h)], 255)
    for x, h in ((17.2, 2.0), (22.8, 2.0)):                                                     # lower fangs
        P([(x - 0.8, 30.0), (x + 0.8, 30.0), (x, 30.0 - h)], 255)


def glyph_hellhound():
    """v18 (2026-10-11): the user's sketch design (front-facing hound face with a flaming mane rising behind it),
    executed in the polished Summon-Boar manner - solid symmetric silhouettes, white cut-out features, and a thin
    white gap between head and mane.  The raw-sketch raster (v17) is glyph_hellhound_v17_sketch."""
    from PIL import ImageFilter, ImageChops
    im = canvas()
    mane = Image.new("L", im.size, 0); ImageDraw.Draw(mane).polygon([(x * S, y * S) for x, y in mane_polygon()], fill=255)   # v23: outline mane again (mane_mask() = the rejected v22 spine tongues)
    head = Image.new("L", im.size, 0); head_mask(ImageDraw.Draw(head))
    gap = head.filter(ImageFilter.MaxFilter(int(2 * MANE_GAP * S) | 1))
    mane = ImageChops.subtract(mane, gap)
    im.paste(255, mask=mane); im.paste(255, mask=head)
    head_features(ImageDraw.Draw(im))
    return im


def glyph_hellhound_v17_sketch():

    """v17 (2026-10-11): the user's own Paint sketch (hound_sketch.png: front-facing hound face in line art with a
    flaming mane rising behind it) rasterised into the glyph.  The ink is cropped, dilated so the lines come out
    SKETCH_LINE px wide at icon scale, then scaled to SKETCH_H px tall and centred; small details (teeth) merge into
    solid areas at this size, which reads fine.  Previous procedural heads kept below."""
    from PIL import ImageFilter, ImageOps
    src = Image.open(SKETCH).convert("L")
    ink = src.point(lambda v: 255 if v < 128 else 0)
    bb = ink.getbbox(); ink = ink.crop(bb)
    scale = SKETCH_H / ink.height                                  # icon px per sketch px
    rad = max(1, int(round(SKETCH_LINE / scale / 2)))              # dilate so lines are SKETCH_LINE px after scaling
    thick = ink.filter(ImageFilter.MaxFilter(2 * rad + 1))
    w8, h8 = int(round(ink.width * scale * S)), int(round(SKETCH_H * S))
    small = thick.resize((w8, h8), Image.LANCZOS)
    im = canvas()
    im.paste(small, (int((W * S - w8) / 2), int((H * S - h8) / 2 + SKETCH_DY * S)))
    return im


def glyph_hellhound_v16_boar_ring():

    """v15 (2026-10-11, user: "head facing forward inspired by Summon Boar, surrounded by fire similar to Fire
    Halo"): a Summon-Boar-style (SPELLICN 44) front-facing hound head drawn at HEAD_SCALE about the icon centre -
    wide skull, short pointed ears, big cut-out eye slits and nostrils, open gape with fangs - inside the single-line
    Fire-Halo flame ring (halo_ring).  Profile-in-ring version kept as glyph_hellhound_v14_profile_ring."""
    im = canvas(); dr = ImageDraw.Draw(im)
    sc, cx, cy = HEAD_SCALE, HEAD_CX, HEAD_CY

    def T(x, y):                                  # v4 head coordinates (40x35 design) -> icon, scaled about (20, 18)
        return (cx + (x - 20.0) * sc, cy + (y - 18.0) * sc)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in (T(a, b) for a, b in pts)], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        px0, py0 = T(x0, y0); px1, py1 = T(x1, y1)
        dr.ellipse([px0 * S, py0 * S, px1 * S, py1 * S], fill=fill)

    P([(6.5, 15.0), (8.5, 5.0), (16.0, 11.0)])                                         # ears: short, pointed, flared
    P([(33.5, 15.0), (31.5, 5.0), (24.0, 11.0)])
    E(6.0, 8.0, 34.0, 27.0)                                                            # wide skull
    P([(9.5, 20.0), (30.5, 20.0), (29.0, 29.5), (23.5, 34.0), (16.5, 34.0), (11.0, 29.5)])   # muzzle / jaw
    P([(9.0, 12.4), (18.0, 16.2), (18.0, 19.6), (9.6, 16.4)], fill=0)                  # eyes: big mean slits (cut-outs)
    P([(31.0, 12.4), (22.0, 16.2), (22.0, 19.6), (30.4, 16.4)], fill=0)
    E(15.6, 19.6, 19.2, 22.6, fill=0)                                                  # nostrils (big, boar-like)
    E(20.8, 19.6, 24.4, 22.6, fill=0)
    P([(10.5, 24.4), (29.5, 24.4), (27.8, 29.6), (20.0, 31.6), (12.2, 29.6)], fill=0)  # the gape
    for x, h in ((14.0, 3.8), (26.0, 3.8)):                                            # two big upper fangs
        P([(x - 1.3, 24.4), (x + 1.3, 24.4), (x, 24.4 + h)])
    for x, h in ((17.2, 2.4), (22.8, 2.4)):                                            # two lower fangs
        P([(x - 1.0, 30.6), (x + 1.0, 30.6), (x, 30.6 - h)])
    halo_ring(im, 20.0, 18.0, RING_R, n=RING_N, tip=RING_TIP, lean=RING_LEAN, hook=RING_HOOK, short=RING_SHORT, stroke=1.25, phase=math.radians(-85))
    return im


HEAD_SCALE, HEAD_CX, HEAD_CY = 0.76, 20.0, 18.0
RING_R, RING_TIP, RING_N, RING_LEAN, RING_HOOK, RING_SHORT = 11.8, 5.2, 6, 0.75, 0.35, 0.8   # v16: tighter, 6 taller hooked tongues


def glyph_hellhound_v14_profile_ring():

    """v14 (2026-10-11, user: "a dog head surrounded by fire, similar to Fire Halo"): the v7 snarling mastiff head
    (profile, no tilt, 52 %) centred, ringed by six Fire-Halo-style flame strokes (halo_ring).  The breathing-fire
    versions live on in glyph_hellhound_v13_breath."""
    im = canvas(); dr = ImageDraw.Draw(im)
    sc, th = 0.50, math.radians(0)
    px0, py0 = 21.0, 16.0                      # pivot in v7 coordinates (centre of the head mass)
    px1, py1 = 20.5, 17.5
    ct, st = math.cos(th), math.sin(th)

    def T(x, y):
        dx, dy = (x - px0) * sc, (y - py0) * sc
        return (px1 + dx * ct + dy * st, py1 - dx * st + dy * ct)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in (T(a, b) for a, b in pts)], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        P([(cx + rx * math.cos(2 * math.pi * k / 24), cy + ry * math.sin(2 * math.pi * k / 24)) for k in range(24)], fill)

    P(HOUND_HEAD)
    for x, h in ((6.6, 1.7), (9.2, 2.3), (11.8, 2.1), (14.4, 2.4)):
        y0 = 17.6 + (x - 5.0) * 0.31
        P([(x - 0.6, y0), (x + 0.6, y0), (x, y0 + h)])
    for x, h in ((8.2, 1.5), (10.8, 1.9), (13.4, 1.6)):
        y0 = 23.9 - (12.0 - x) * 0.1 if x < 12 else 24.0 - (x - 12.0) * 0.2
        P([(x - 0.6, y0), (x + 0.6, y0), (x, y0 - h)])
    P([(12.6, 12.0), (17.2, 10.6), (17.6, 11.8), (13.2, 13.4)], fill=0)
    E(3.4, 14.2, 4.4, 15.2, fill=0)
    P([(32.9, 9.2), (35.2, 4.4), (35.7, 4.9), (33.6, 9.6)], fill=0)
    halo_ring(im, 20.0, 17.5, 10.8, n=7, phase=math.radians(-80))
    return im


def glyph_hellhound_v13_breath():

    """v8 (2026-10-11): the v7 snarling mastiff head (kept as glyph_hellhound_v7_mastiff) scaled to 50 % and tilted
    34 degrees muzzle-down into the upper right, BREATHING FIRE: the hand-drawn JET silhouette (throat, body, three
    curling tongues) blown down-left across the icon, 14 degrees flatter than the muzzle.  Generated plumes (fans of
    spikes, swept tongues, outlined cones) all read as claws/birds at 40x35 - the explicit silhouette is the one that
    reads as fire.  HOUND_STROKE switches the jet to a vanilla-style outline.  The v7 fire curl is dropped."""
    im = canvas(); dr = ImageDraw.Draw(im)
    sc, th = 0.78, math.radians(27)
    px0, py0 = 15.0, 12.0                      # pivot in v7 coordinates (the eye)
    px1, py1 = 24.0, 16.0                      # where the pivot lands
    ct, st = math.cos(th), math.sin(th)

    def T(x, y):                               # scale about the pivot, rotate muzzle-down (counter-clockwise on screen)
        dx, dy = (x - px0) * sc, (y - py0) * sc
        return (px1 + dx * ct + dy * st, py1 - dx * st + dy * ct)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in (T(a, b) for a, b in pts)], fill=fill)

    def E(x0, y0, x1, y1, fill=255):           # ellipse in v7 coordinates, as a polygon so it transforms
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        P([(cx + rx * math.cos(2 * math.pi * k / 24), cy + ry * math.sin(2 * math.pi * k / 24)) for k in range(24)], fill)

    P(HOUND_V7)
    for x, h in ((6.6, 1.7), (9.2, 2.3), (11.8, 2.1), (14.4, 2.4)):            # upper teeth
        y0 = 17.6 + (x - 5.0) * 0.31
        P([(x - 0.6, y0), (x + 0.6, y0), (x, y0 + h)])
    for x, h in ((8.2, 1.5), (10.8, 1.9), (13.4, 1.6)):                        # lower teeth
        y0 = 23.9 - (12.0 - x) * 0.1 if x < 12 else 24.0 - (x - 12.0) * 0.2
        P([(x - 0.6, y0), (x + 0.6, y0), (x, y0 - h)])
    P([(12.6, 12.0), (17.2, 10.6), (17.6, 11.8), (13.2, 13.4)], fill=0)       # eye slit
    E(3.4, 14.2, 4.4, 15.2, fill=0)                                            # nostril
    P([(32.9, 9.2), (35.2, 4.4), (35.7, 4.9), (33.6, 9.6)], fill=0)           # inner line of the back ear
    # the breath: starts inside the open mouth and follows the tilted muzzle direction (v7 muzzle = -x)
    mx, my = T(2.4, 19.8)
    HALO = True                                # v13 Fire-Halo-style hooked strokes; False = v12 (3 straight-ish S strokes)
    if HALO: halo_lines(im, mx, my, math.atan2(st, -ct) + math.radians(24), L=16.0)
    else: flame_lines(im, mx, my, math.atan2(st, -ct) + math.radians(24), L=15.0)   # v10: three wavy strokes, flatter than the muzzle
    # two detached flecks flying ahead of the jet
    ca, sa = -ct, st
    for u, v, r in ((20.5, 7.0, 0.8),):
        fx, fy = mx + u * ca - v * sa, my + u * sa + v * ca
        dr.ellipse([(fx - r) * S, (fy - r) * S, (fx + r) * S, (fy + r) * S], fill=255)
    return im


def glyph_hellhound_v7_mastiff():
    """v7 (2026-10-10): a SNARLING mastiff-type hound head in profile - heavy skull and jaw, short powerful muzzle
    with the lips drawn back over a full row of teeth, ears pinned flat back, brow ridge over a narrowed eye, thick
    neck, and fire curling out of the mouth.  (v6 shepherd + collar: "don't like it".)"""
    im = canvas(); dr = ImageDraw.Draw(im)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        dr.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)

    # outline, clockwise from the nose: curled upper lip -> mouth corner -> lower jaw -> chin -> throat -> neck ->
    # back of the skull -> pinned-back ear -> skull top -> brow ridge -> stop -> muzzle
    P([(4.0, 13.5), (3.0, 15.0), (3.6, 16.6), (5.0, 17.6), (8.0, 18.4), (12.0, 19.2), (16.0, 20.4), (17.5, 21.5),
       (16.0, 23.2), (12.0, 24.0), (8.0, 23.6), (6.5, 22.6), (7.2, 25.0), (12.0, 26.2), (18.0, 26.6), (22.0, 28.5),
       (24.0, 34.5), (39.5, 34.5), (39.5, 22.0), (35.0, 15.0), (31.0, 11.0), (36.5, 6.5), (28.5, 7.0), (24.0, 5.5),
       (19.0, 6.0), (14.0, 8.2), (11.0, 10.5), (7.0, 12.2)])
    # teeth: upper row hanging from the lip line (y = 17.6 + (x-5)*0.31), lower row rising from the jaw
    for x, h in ((6.6, 1.7), (9.2, 2.3), (11.8, 2.1), (14.4, 2.4)):
        y0 = 17.6 + (x - 5.0) * 0.31
        P([(x - 0.6, y0), (x + 0.6, y0), (x, y0 + h)])
    for x, h in ((8.2, 1.5), (10.8, 1.9), (13.4, 1.6)):
        y0 = 23.9 - (12.0 - x) * 0.1 if x < 12 else 24.0 - (x - 12.0) * 0.2
        P([(x - 0.6, y0), (x + 0.6, y0), (x, y0 - h)])
    # fire pouring from the mouth and curling up in front of the muzzle
    P([(7.0, 20.8), (4.0, 21.2), (1.6, 20.6), (0.4, 18.6), (1.8, 17.4), (0.4, 14.6), (2.0, 15.4), (1.4, 11.8),
       (2.8, 14.2), (3.4, 17.0), (4.6, 19.0), (7.4, 19.4)])
    # eye: narrowed under the brow ridge (cut-out) + nostril + ear fold line
    P([(12.6, 12.0), (17.2, 10.6), (17.6, 11.8), (13.2, 13.4)], fill=0)
    E(3.4, 14.2, 4.4, 15.2, fill=0)
    P([(30.0, 10.6), (35.6, 7.0), (35.9, 7.6), (30.6, 11.3)], fill=0)
    return im


def glyph_hellhound_v6_shepherd():
    """(superseded 2026-10-10) shepherd-style head with a spiked collar - kept for reference."""
    im = canvas(); dr = ImageDraw.Draw(im)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        dr.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)

    # head + neck outline, clockwise from the nose
    P([(6.0, 15.0), (5.6, 16.6), (6.2, 17.8), (7.5, 18.6), (15.0, 20.0),                   # nose, upper lip
       (15.5, 21.6), (8.0, 22.6), (8.8, 24.4), (18.0, 24.0), (21.0, 25.2), (23.0, 27.5),    # deeper lower jaw, chin, throat
       (25.0, 34.5), (39.5, 34.5), (39.5, 24.0), (36.0, 17.0), (32.0, 12.0),                # neck, back of the skull
       (34.0, 3.0), (29.5, 9.5), (28.5, 9.0), (25.5, 0.8), (21.5, 7.5),                     # far ear, notch, near ear
       (18.0, 6.5), (14.5, 7.5), (11.5, 10.5), (8.0, 13.2)])                                # forehead, stop, muzzle
    # mouth: a short cut-out gape at the front of the muzzle with small teeth (v6a: shorter - the long slit read as a bill)
    P([(6.6, 18.2), (14.6, 20.3), (14.9, 21.3), (8.3, 22.2), (7.2, 20.6)], fill=0)
    for x in (9.0, 11.6):
        y0 = 18.2 + (x - 6.6) * 0.26
        P([(x - 0.5, y0), (x + 0.5, y0), (x, y0 + 1.2)])
    P([(12.6, 22.0), (13.6, 22.0), (13.1, 20.9)])
    # fire pouring out of the front of the mouth and curling UP in front of the muzzle (clear of the jaw)
    P([(9.0, 19.6), (5.6, 20.2), (3.0, 20.4), (1.2, 19.0), (2.6, 17.6), (0.8, 15.6), (2.6, 16.4), (2.0, 13.0),
       (3.4, 16.4), (4.4, 18.6), (6.4, 19.0)])
    # spiked collar: a thin pale stripe across the neck + spikes sticking out of the throat and the back
    P([(22.6, 28.0), (39.5, 20.5), (39.5, 21.7), (23.2, 29.3)], fill=0)
    P([(22.5, 27.2), (23.0, 29.8), (19.4, 28.8)])
    P([(36.0, 17.2), (38.2, 20.2), (39.8, 16.2)])
    P([(24.0, 32.0), (25.0, 34.5), (21.4, 33.8)])
    # eye: almond cut-out just behind the stop + nostril
    P([(11.2, 12.4), (15.4, 10.9), (15.8, 12.0), (11.8, 13.6)], fill=0)
    E(5.5, 15.5, 6.5, 16.5, fill=0)
    return im


def glyph_hellhound_v5_profile():
    """(superseded 2026-10-10) wide-gape profile with a flame mane - read as a crocodile/dragon; kept for reference."""
    im = canvas(); dr = ImageDraw.Draw(im)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        dr.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)

    # neck / chest mass to the lower right, with a mane of three separate flame tongues along its back ridge
    P([(23, 12), (33, 15.5), (39.5, 22), (39.5, 34.5), (22, 34.5), (20.5, 24), (27, 21)])
    flame(dr, 32.0 * S, 16.0 * S, 9 * S, 3.6 * S, lean=0.3)
    flame(dr, 36.0 * S, 19.5 * S, 7 * S, 3.0 * S, lean=0.25)
    flame(dr, 38.8 * S, 23.0 * S, 4.5 * S, 2.2 * S, lean=0.1)
    # ear: one tall pointed ear at the top-back of the skull (a second one merged with the mane at this size)
    P([(22.5, 10), (26.5, 0.8), (31, 11.5)])
    # skull (rounded) + brow/stop + long upper muzzle ending in the nose
    E(13, 7, 30.5, 23)
    P([(16, 9.5), (10.5, 12.8), (4.2, 15.2), (2.6, 17.4), (3.4, 19.6), (10, 20.3), (18, 20.0), (25, 18)])
    E(2.2, 15.6, 5.8, 18.9)                                                          # nose bump
    # lower jaw swung wide open, hinged under the back of the skull, chin down-left
    P([(27, 19), (19, 22.5), (12, 26.5), (6, 30), (4.5, 32.5), (8, 33.5), (14, 30), (21.5, 26), (28.5, 22.5)])
    # fangs: upper row hanging from the muzzle, lower row rising from the jaw (jaw top: y = 19 + (27-x)*0.524)
    for x, h in ((6.0, 2.6), (9.6, 3.4), (13.6, 2.4)):
        P([(x - 0.7, 20.1), (x + 0.7, 20.1), (x, 20.1 + h)])
    for x, h in ((9.0, 3.0), (14.0, 2.6)):
        y0 = 19 + (27 - x) * 0.524 + 0.3
        P([(x - 0.7, y0), (x + 0.7, y0), (x, y0 - h)])
    # eye: a mean slit slanting down toward the muzzle (cut-out) + nostril
    P([(12.4, 13.4), (18.0, 11.9), (18.4, 13.1), (12.9, 14.7)], fill=0)
    E(3.0, 16.6, 4.3, 17.9, fill=0)
    return im


def glyph_hellhound_v4_front(tuft=True):
    """(superseded 2026-10-10) Summon-Boar style front-facing head - kept for reference."""
    im = canvas(); dr = ImageDraw.Draw(im)

    def P(pts, fill=255):
        dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        dr.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)

    # flame tuft rising from the top of the skull, between the ears
    if tuft:
        flame(dr, 20 * S, 10.5 * S, 10 * S, 5.5 * S)
        flame(dr, 16.2 * S, 11 * S, 6.5 * S, 3.5 * S, lean=-0.35)
        flame(dr, 23.8 * S, 11 * S, 6.5 * S, 3.5 * S, lean=0.35)
    # ears: tall, pointed, leaning slightly outward
    P([(7.0, 16.0), (9.8, 2.6), (16.5, 11.0)])
    P([(33.0, 16.0), (30.2, 2.6), (23.5, 11.0)])
    # skull (wide, rounded) + muzzle/jaw mass tapering to the chin
    E(7.5, 8.0, 32.5, 27.5)
    P([(10.5, 21.0), (29.5, 21.0), (28.0, 29.5), (23.0, 34.0), (17.0, 34.0), (12.0, 29.5)])
    # eyes: mean slanted slits, inner corners pulled down (cut-outs)
    P([(10.3, 13.2), (17.4, 16.6), (17.4, 18.6), (10.8, 15.6)], fill=0)
    P([(29.7, 13.2), (22.6, 16.6), (22.6, 18.6), (29.2, 15.6)], fill=0)
    # nostrils
    E(17.2, 20.2, 19.0, 21.8, fill=0)
    E(21.0, 20.2, 22.8, 21.8, fill=0)
    # the gape: a wide cut-out band between the jaws
    P([(11.0, 24.0), (29.0, 24.0), (27.4, 29.2), (20.0, 31.0), (12.6, 29.2)], fill=0)
    # fangs: upper row hanging from the top of the gap, lower row rising from the bottom
    for x, y0, h in ((13.4, 24.0, 2.2), (16.4, 24.0, 3.6), (23.6, 24.0, 3.6), (26.6, 24.0, 2.2)):
        P([(x - 0.75, y0), (x + 0.75, y0), (x, y0 + h)])
    for x, y0, h in ((14.6, 29.4, 2.6), (20.0, 31.0, 2.2), (25.4, 29.4, 2.6)):
        P([(x - 0.75, y0), (x + 0.75, y0), (x, y0 - h)])
    return im


def glyph_hellhound_v3_body():
    """(superseded 2026-10-09) full-body stalking silhouette - kept for reference."""
    im = canvas(); dr = ImageDraw.Draw(im)
    OX = 3.0                                                            # room for the fire left of the muzzle

    def P(pts, fill=255):
        dr.polygon([((x + OX) * S, y * S) for x, y in pts], fill=fill)

    def E(x0, y0, x1, y1, fill=255):
        dr.ellipse([(x0 + OX) * S, y0 * S, (x1 + OX) * S, y1 * S], fill=fill)

    # torso: slim, back gently arched, belly well clear of the ground so the legs read
    P([(13, 11.0), (17, 9.4), (22, 9.0), (27, 9.8), (31, 12.0), (32.6, 15.5), (31, 19.5), (25, 20.8), (18, 21.0), (13.5, 20.2), (11.5, 16)])
    # neck, sloping forward-down to the lowered head
    P([(13, 11.0), (10, 11.2), (6.2, 13.8), (7.5, 19.5), (13.5, 20.2), (12, 15.5)])
    # head: skull, long muzzle, lower jaw dropped open
    E(2.6, 10.6, 11.6, 17.8)
    P([(4.4, 12.2), (-0.2, 15.2), (0.4, 17.4), (6.5, 17.9), (9.8, 16.6)])                # upper jaw / snout
    P([(9.0, 17.6), (1.6, 21.2), (3.2, 23.2), (9.9, 20.4), (11.2, 18.0)])                # lower jaw swung open
    P([(1.2, 17.8), (9.0, 17.7), (9.9, 18.6), (3.2, 21.6)], fill=0)                      # the gape (cut-out)
    for x, y0, h in ((2.8, 17.8, 1.4), (4.8, 17.8, 1.8), (6.8, 17.7, 1.4)):             # upper fangs
        P([(x - 0.55, y0), (x + 0.55, y0), (x, y0 + h)])
    for x, y0, h in ((4.2, 21.2, 1.4), (6.4, 20.4, 1.6)):                               # lower fangs
        P([(x - 0.55, y0), (x + 0.55, y0), (x, y0 - h)])
    # ear: upright, pointed
    P([(8.4, 11.8), (10.8, 5.2), (13.4, 11.4)])
    # three short mane spikes over the shoulders
    for x, h, lean in ((15.2, 2.8, -0.6), (18.0, 3.2, -0.4), (20.8, 2.6, -0.2)):
        y0 = 9.8 if x < 17 else 9.4
        P([(x - 1.1, y0 + 0.4), (x + 1.1, y0 + 0.4), (x + lean, y0 - h)])
    # front legs: long and straight, near one stepping forward (thicker than v3a)
    P([(11.2, 15.5), (9.4, 23), (7.6, 31.4), (11.4, 32), (13.0, 24), (15.0, 17.5)])
    P([(15.0, 17.5), (14.6, 24), (14.0, 31.4), (17.6, 32), (18.0, 24), (18.6, 18.5)])
    # hind legs: thigh, bent hock, long shank
    P([(24.0, 17.5), (28.8, 21.0), (27.6, 25.5), (26.8, 31.4), (30.4, 32), (30.6, 26.0), (31.8, 20.5), (29.8, 15.0)])
    P([(29.8, 16.5), (33.8, 21.0), (32.8, 25.5), (32.8, 31.4), (36.4, 32), (36.0, 26.0), (37.0, 20.5), (33.8, 14.0)])
    # tail curling up over the rump
    for i in range(16):
        t = i / 15
        x = 30.5 + 5.8 * math.sin(t * 2.3)
        y = 12.6 - 9.8 * t + 2.0 * (1 - math.cos(t * 3.0))
        r = 1.25 - 0.6 * t
        E(x - r, y - r, x + r, y + r)
    # one big flame tongue pouring forward-down out of the open mouth
    P([(1.6, 17.8), (-0.4, 16.0), (-2.2, 17.8), (-3.0, 20.6), (-1.6, 20.0), (-2.8, 23.8), (-0.6, 21.8),
       (-0.2, 26.0), (1.4, 22.8), (2.8, 25.6), (3.0, 22.2), (3.8, 20.8), (2.6, 19.6)])
    # eye: a mean slit, cut out
    P([(6.0, 13.6), (9.2, 12.6), (9.5, 13.6), (6.4, 14.7)], fill=0)
    return im


def glyph_hellhound_v2_head():
    """(superseded 2026-10-09) three-quarter head only - kept for reference."""
    im = canvas(); dr = ImageDraw.Draw(im)
    # v2: three-quarter view turned a little toward the viewer (wider skull, shorter snout angled down-left), two
    # upright ears (near + far), meaner eyes (slanted down toward the snout), spiky mane behind
    # neck / mane (back-right), spiky
    dr.polygon([(24 * S, 12 * S), (38 * S, 15 * S), (38 * S, 33 * S), (26 * S, 33 * S), (22 * S, 23 * S)], fill=255)
    for x, h in ((32, 6), (36, 4)):                                   # mane spikes moved back so the far ear stands clear
        dr.polygon([((x - 1.6) * S, 14.5 * S), ((x + 1.6) * S, 14.5 * S), (x * S, (14.5 - h) * S)], fill=255)
    # ears: two matching upright pointed ears (same shape, the far one a little shorter and set further back)
    dr.polygon([(9.5 * S, 12.5 * S), (12 * S, 1.5 * S), (19 * S, 10.5 * S)], fill=255)
    dr.polygon([(20.5 * S, 11 * S), (23.5 * S, 2.5 * S), (29 * S, 12.5 * S)], fill=255)
    # skull: wide, rounded
    dr.ellipse([7 * S, 8 * S, 30 * S, 26 * S], fill=255)
    # snout: shorter wedge angled down-left toward the viewer, upper jaw
    dr.polygon([(9 * S, 15 * S), (2 * S, 24 * S), (3.5 * S, 27 * S), (15 * S, 25.5 * S), (22 * S, 21 * S)], fill=255)
    # lower jaw swung open
    dr.polygon([(15 * S, 26 * S), (4 * S, 32 * S), (8 * S, 34.5 * S), (19 * S, 30.5 * S), (23 * S, 25 * S)], fill=255)
    # mouth cut-out (the gape)
    dr.polygon([(4.5 * S, 27.2 * S), (15.5 * S, 26.0 * S), (21.5 * S, 23.5 * S), (21 * S, 26 * S), (16 * S, 29.4 * S), (6 * S, 31.8 * S)], fill=0)
    # fangs in the gap (upper row hanging, lower row rising)
    for x, y0, h in ((6.5, 27.0, 2.3), (9.5, 26.7, 2.9), (12.5, 26.4, 2.5), (16, 25.6, 2.0)):
        dr.polygon([((x - 0.7) * S, y0 * S), ((x + 0.7) * S, y0 * S), (x * S, (y0 + h) * S)], fill=255)
    for x, y0, h in ((7.5, 31.4, 2.2), (10.5, 30.7, 2.7), (13.5, 29.9, 2.2)):
        dr.polygon([((x - 0.7) * S, y0 * S), ((x + 0.7) * S, y0 * S), (x * S, (y0 - h) * S)], fill=255)
    # fire spilling from the mouth corner
    flame(dr, 4 * S, 28.5 * S, 7 * S, 3.5 * S, lean=-0.9)
    # eye (cut-out): a single small slit on the near (right) side, slanting down toward the snout
    dr.polygon([(15.5 * S, 16.6 * S), (19.1 * S, 14.9 * S), (19.6 * S, 16.0 * S), (16.1 * S, 17.9 * S)], fill=0)
    # nostril
    dr.ellipse([2.9 * S, 23.4 * S, 4.7 * S, 25.0 * S], fill=0)
    return im


def glyph_rejuvenate():
    """Rejuvenate (Life, 2026-10-12): a young plant sprouting from the ground - a stem with two broad leaves and a
    bud, over a low mound with grass tufts, solid ink like the vanilla Life glyphs."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def P(pts, fill=255): dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    # ground mound + tufts
    P([(5.0, 30.0), (9.0, 27.6), (15.0, 26.6), (20.0, 26.2), (25.0, 26.6), (31.0, 27.6), (35.0, 30.0), (35.0, 31.6), (5.0, 31.6)])
    for x, h, lean in ((8.5, 4.2, -0.6), (12.0, 5.0, -0.3), (27.5, 5.0, 0.3), (31.0, 4.2, 0.6)):
        P([(x - 0.9, 28.0), (x + 0.9, 28.0), (x + lean * h, 28.0 - h)])
    # stem (slightly curved) and bud
    stem = [(19.2 + 0.9 * math.sin(t * 2.2), 27.0 - 17.0 * t) for t in [i / 12 for i in range(13)]]
    P([(x - 1.1 + 0.5 * i / 12, y) for i, (x, y) in enumerate(stem)] + [(x + 1.1 - 0.5 * i / 12, y) for i, (x, y) in reversed(list(enumerate(stem)))])
    dr.ellipse([(stem[-1][0] - 2.2) * S, (stem[-1][1] - 3.4) * S, (stem[-1][0] + 2.2) * S, (stem[-1][1] + 1.0) * S], fill=255)
    # two broad leaves (teardrop lobes) on the stem, left low, right higher
    def leaf(ax, ay, dx, dy, w):
        pts = []
        for i in range(17):
            t = i / 16; a = math.sin(math.pi * t) * w
            pts.append((ax + dx * t - dy * a, ay + dy * t + dx * a))
        for i in range(16, -1, -1):
            t = i / 16; a = math.sin(math.pi * t) * w * 0.55
            pts.append((ax + dx * t + dy * a, ay + dy * t - dx * a))
        P(pts)
    leaf(19.0, 21.5, -9.0, -5.5, 0.42)
    leaf(20.0, 17.5, 9.5, -4.0, 0.42)
    return im


_VLIB = None
def glyph_martyr():
    """Martyr (2026-10-13): a standing figure with its arms flung wide and a halo over its head, flames rising round
    its feet."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def P(pts, fill=255): dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def E(x0, y0, x1, y1, fill=255): dr.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)
    E(17.2, 6.0, 22.8, 11.6)                                                                   # head
    P([(18.0, 12.0), (22.0, 12.0), (23.4, 18.0), (23.0, 27.0), (17.0, 27.0), (16.6, 18.0)])    # torso
    P([(17.4, 13.0), (18.9, 15.2), (10.6, 10.0), (9.4, 8.4)])                                  # arms raised wide
    P([(22.6, 13.0), (21.1, 15.2), (29.4, 10.0), (30.6, 8.4)])
    P([(17.0, 26.0), (19.6, 26.0), (18.6, 32.6), (15.8, 32.6)])                                # legs
    P([(20.4, 26.0), (23.0, 26.0), (24.2, 32.6), (21.4, 32.6)])
    stroke_ellipse(dr, [14.4 * S, 1.8 * S, 25.6 * S, 5.4 * S], int(0.9 * S))                   # halo
    for cx, h, w, lean in ((7.5, 11.0, 4.4, 0.10), (12.5, 7.5, 3.4, 0.05), (27.5, 8.0, 3.4, -0.05), (32.5, 11.5, 4.4, -0.10)):
        flame(dr, cx * S, 33.4 * S, h * S, w * S, lean=lean)
    return im


def halo_ring(dr, cx, cy, rx, ry, n_side, top=True, bottom=True, stroke=1.5, length=7.5, hook=0.55, phase=0.0):
    """A Fire-Halo-style ring: curling flame tongues set round an ellipse - each tongue is a tapered, bowed stroke
    rising outward from the ellipse and hooking over at its tip (clockwise), `n_side` tongues per side plus
    optional top and bottom ones."""
    angs = []
    for k in range(n_side):
        t = (k + 0.5) / n_side
        angs.append(math.pi * (0.62 + 0.76 * t) + phase)            # left side, from top-left round to bottom-left
        angs.append(math.pi * (0.38 - 0.76 * t) - phase)            # right side (mirror)
    if top: angs.append(-math.pi / 2)
    if bottom: angs.append(math.pi / 2)
    for a in angs:
        bx, by = cx + rx * math.cos(a), cy + ry * math.sin(a)
        nx, ny = math.cos(a), math.sin(a)                          # outward
        tx, ty = -math.sin(a), math.cos(a)                          # tangent (clockwise)
        L = length * (1.25 if abs(math.sin(a)) < 0.3 else 1.0)
        pts = []
        for i in range(9):
            u = i / 8
            d = L * u; curl = hook * L * u * u
            pts.append((bx + nx * d + tx * curl, by + ny * d * 0.92 + ty * curl))
        for i in range(len(pts) - 1):
            w = stroke * (1.0 - 0.75 * i / 8) + 0.5
            dr.line([(pts[i][0] * S, pts[i][1] * S), (pts[i + 1][0] * S, pts[i + 1][1] * S)], fill=255, width=max(1, int(w * S)))
        # a short inner lick at the base, like the halo's double tongues
        pts2 = [(bx - tx * 1.2 + nx * d * 0.5 - tx * 0.2 * d, by - ty * 1.2 + ny * d * 0.5 - ty * 0.2 * d) for d in (0.0, 1.5, 3.0, 4.2)]
        for i in range(len(pts2) - 1):
            dr.line([(pts2[i][0] * S, pts2[i][1] * S), (pts2[i + 1][0] * S, pts2[i + 1][1] * S)], fill=255, width=max(1, int((stroke - 0.4 * i) * S)))


def glyph_cleansing():
    """Cleansing Flame v18 (2026-10-13, user: v17 "janky - revert; different fire, same style/line weight as Fire
    Halo"): the reference praying hands (finger seams kept, 27 px) with the big curling flames of the BURNING-area
    icon (icon 72, its flame cluster x 0..21 / y 0..31, the figure left out) rising on the left and mirrored on the
    right - vanilla ink, so the line weight is the halo's - with a clear halo keeping them off the hands."""
    im = canvas()
    # v19 polish: a clean crop (0,0,19,27) - the figure's arm at x 19..21 and the debris at y 28..31 are out - no
    # vertical stretch (the 1.08 scale jagged the curls), sat a little lower so the flames wrap the hands
    flames = vanilla_ink(72).crop((0, 0, 19, 27))
    fl = flames.resize((19 * S, 27 * S), Image.BICUBIC)
    paste_max(im, fl.transpose(Image.FLIP_LEFT_RIGHT), (int(W * S - fl.width + 0.5 * S), int(4.0 * S)))     # right: the Burning flames (mirrored)
    # v20 (user: "reshape the left side flame"): the left side is FIRE HALO's own left tongues instead (icon 61, figure
    # removed, left half x 0..15 / y 2..32) - same weight, a different shape from the right
    ring = vanilla_ink(61); ring = ImageChops.subtract(ring, ink_component(ring, (20, 22)))
    left = ring.crop((0, 2, 15, 32)).resize((15 * S, 30 * S), Image.BICUBIC)
    paste_max(im, left, (int(0.5 * S), int(2.5 * S)))
    ref = Image.open(os.path.join(IMPORT_DIR, "praying-hands-illustration-black-white-260nw-2628304599.webp")).convert("L").crop((0, 0, 260, 236))
    ink = ref.point(lambda v: 255 if v < 128 else 0)
    bb = ink.getbbox(); ink = ink.crop(bb)
    filled = ink.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    seams = ImageChops.subtract(filled, ink).filter(ImageFilter.MaxFilter(5))
    solid = ImageChops.subtract(filled, seams)
    th = 27.0 * S; sc = th / solid.height
    hands = solid.resize((int(solid.width * sc), int(th)), Image.LANCZOS)
    halo = filled.filter(ImageFilter.MaxFilter(15)).resize(hands.size, Image.LANCZOS)
    x0, y0 = int(20 * S - hands.width / 2), int(19.5 * S - hands.height / 2)
    hp = im.load(); hl = halo.load()
    for y in range(halo.height):
        for x in range(halo.width):
            if hl[x, y] > 100 and 0 <= x0 + x < im.width and 0 <= y0 + y < im.height: hp[x0 + x, y0 + y] = 0
    paste_max(im, hands, (x0, y0))
    return im


def glyph_phoenix():
    """Summon Phoenix (2026-10-13): a firebird rising - wings swept up and out with flame-tipped feathers, a tail of
    three flames hanging below."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def P(pts, fill=255): dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def E(x0, y0, x1, y1, fill=255): dr.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)
    E(16.5, 11.0, 23.5, 24.0)                                                                  # body
    E(17.8, 6.4, 22.2, 11.4)                                                                   # head
    P([(21.6, 8.0), (25.6, 9.4), (21.6, 10.6)])                                                # beak
    P([(17.0, 14.0), (10.0, 6.0), (4.0, 2.6), (2.4, 7.8), (6.0, 13.6), (3.4, 18.8), (9.0, 17.0), (12.0, 20.2), (16.6, 19.0)])     # wings
    P([(23.0, 14.0), (30.0, 6.0), (36.0, 2.6), (37.6, 7.8), (34.0, 13.6), (36.6, 18.8), (31.0, 17.0), (28.0, 20.2), (23.4, 19.0)])
    P([(17.6, 22.0), (22.4, 22.0), (24.2, 33.4), (20.0, 29.4), (15.8, 33.4)])                  # tail
    P([(16.2, 24.0), (12.4, 33.6), (17.0, 29.6)]); P([(23.8, 24.0), (27.6, 33.6), (23.0, 29.6)])
    E(18.6, 8.0, 19.7, 9.1, 0)                                                                 # eye
    return im


def glyph_starfire():
    """Holy Starfire (2026-10-13): three four-point stars streaking down and to the left, trails behind them."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def star(cx, cy, r, trail):
        pts = []
        for k in range(8):
            a = math.pi / 4 * k; rr = r if k % 2 == 0 else r * 0.38
            pts.append(((cx + rr * math.cos(a)) * S, (cy + rr * math.sin(a)) * S))
        dr.polygon(pts, fill=255)
        dr.line([(cx * S, cy * S), ((cx + trail) * S, (cy - trail * 1.25) * S)], fill=255, width=int(1.4 * S))
    star(12.0, 25.5, 6.2, 9.0); star(26.5, 14.5, 4.6, 8.0); star(31.5, 28.0, 3.4, 6.0)
    return im


def pyre_tongue(dr, cx, base_y, h, w, lean=0.0, lick=1):
    """A bulbous flame tongue: round belly (width ~ sqrt(1-t)), wavy edges, pointed leaning tip, plus a short side
    lick curling off the belly on the `lick` side."""
    def edge(sign, ph):
        pts = []
        for i in range(21):
            t = i / 20.0
            ww = w * math.sqrt(max(0.0, 1 - t)) * (0.5 + 0.12 * math.sin(t * 9 + ph)) * (1 - 0.35 * t * t)
            pts.append((cx + sign * ww + lean * h * t * t, base_y - h * t))
        return pts
    left, right = edge(-1, 0.0), edge(+1, 1.7)
    dr.polygon(left + right[::-1], fill=255)
    # side lick: a small tongue growing out of the belly at ~45 % height
    t0 = 0.42; bx = cx + lick * w * math.sqrt(1 - t0) * 0.48 + lean * h * t0 * t0; by = base_y - h * t0
    dr.polygon([(bx - lick * 0.16 * w, by + 0.12 * h), (bx + lick * 0.05 * w, by + 0.02 * h), (bx + lick * 0.34 * w, by - 0.30 * h), (bx + lick * 0.08 * w, by - 0.12 * h)], fill=255)


def glyph_ashes(scale=1.45, split=0.50, fade=0.38, seed=353, ring_scale=(1.12, 1.0), ring_up=0, max_dissolve=0.78, solid_floor=0.0, y_down=7, drift=4, dots=60, y_top=1, torso_holes=16):
    """Ashes to Ashes v16 (user 10/13: "revert the man to the Disease Cloud man, disintegrate from mid-torso
    downwards, forget the arm, keep him centred and surrounded by flame"): the Disease Cloud figure (icon 32, its
    own ink component) enlarged and centred, solid down to `split` of its height, then dissolving into the Disease
    Cloud's own dash/speckle texture (icon 32's cloud, (0,0)-(16,24)) with flakes drifting off the body, inside the
    Fire Halo ring (icon 61, its man cleared, widened a little).  Composed at icon resolution, then x S nearest."""
    rnd = random.Random(seed)
    ring = vanilla_ink(61); rp = ring.load()
    for y in range(8, 33):
        for x in range(10, 28): rp[x, y] = 0
    rw, rh = int(round(W * ring_scale[0])), int(round(H * ring_scale[1]))
    ring = ring.resize((rw, rh), Image.BICUBIC).point(lambda v: 255 if v > 110 else 0)
    ring = ring.crop(((rw - W) // 2, (rh - H) // 2 + ring_up, (rw - W) // 2 + W, (rh - H) // 2 + ring_up + H)); rp = ring.load()
    src = ink_component(vanilla_ink(32), (26, 20), thr=110)
    man = src.crop(src.getbbox())                                            # 15 x 25
    mw, mh = int(round(man.width * scale)), int(round(man.height * scale))
    man = man.resize((mw, mh), Image.BICUBIC).point(lambda v: 255 if v > 120 else 0); mp = man.load()
    halo = man.filter(ImageFilter.MaxFilter(5)); hp = halo.load()          # 2 px black gap around the solid upper body (cuts the ring)
    tex = vanilla_ink(32).crop((0, 0, 16, 24)); tp = tex.load()
    out = Image.new("L", (W, H), 0); op = out.load()
    for y in range(H):
        for x in range(W):
            if rp[x, y] > 100: op[x, y] = 255
    x0, y0 = (W - mw) // 2, (H - mh) // 2 + y_down                          # centred; lowered so the head sits under the ring's top band
    if y_top is not None: y0 = y_top                                          # v19: the big figure starts at the top (torso up fills the icon, the feet run off the bottom)
    def texd(px, py): return tp[(px + 5) % 16, (py + 7) % 24] > 100
    for y in range(mh):
        t = y / float(mh)
        for x in range(mw):
            px, py = x0 + x, y0 + y
            if not (0 <= px < W and 0 <= py < H): continue
            inside = mp[x, y] >= 128
            # v18 (user): the ARMS stay whole - the hanging arm (left 4 columns of the figure, rows 7-18 at 1x) and
            # the bent arm (right 4 columns, rows 6-13) are exempt from the dissolve
            arm = (x < 4 * scale and 6 * scale <= y < 19 * scale) or (x >= mw - 4 * scale and 5 * scale <= y < 14 * scale)
            if t < split or arm:
                if inside: op[px, py] = 255
                elif hp[x, y] >= 128: op[px, py] = 0
                continue
            k = min(1.0, (t - split) / fade)                      # 0 at mid-torso .. 1 fully dissolved
            # v17 (user: "more dramatic"): the body breaks into CHUNKS - a coarse 2x2 cell lattice decides which
            # pieces survive (so the gaps are wide and visible), the surviving pieces shift sideways the further
            # down they are (drifting apart), and the lost ink reappears as flakes blown out to both sides/below
            cell = ((x // 2) * 7919 + (y // 2) * 104729 + seed) % 1000 / 1000.0
            shift = int(round((cell - 0.5) * 2 * drift * k))          # per-chunk sideways drift, up to +-drift px
            if inside:
                # v18: the lower half keeps its SHAPE - at most max_dissolve of it is eaten (holes + the cloud's dash
                # texture), drift is small, so legs/feet stay readable while visibly crumbling
                survive = cell > k * max_dissolve or texd(px, py)
                if survive:
                    qx = px + shift
                    if 0 <= qx < W: op[qx, py] = 255
                if not survive and rnd.random() < 0.35 * k:          # the lost piece blows away as a flake
                    fx_ = px + int(round((rnd.random() - 0.5) * 2 * (drift + 4) * k)); fy = py + rnd.randint(0, 3)
                    if 0 <= fx_ < W and 0 <= fy < H and rp[fx_, fy] < 100: op[fx_, fy] = 255
    # v20 (user: "more disintegration, small white spots in the torso"): single-pixel HOLES punched into the solid
    # torso (between the shoulders and the waist, away from the head/arms), denser towards the waist
    for _ in range(torso_holes):
        hx = x0 + int(mw * (0.25 + 0.5 * rnd.random())); t = 0.22 + (split - 0.22) * rnd.random() ** 0.6
        hy = y0 + int(mh * t)
        if 0 <= hx < W and 0 <= hy < H and 0 <= hx - x0 < mw and 0 <= hy - y0 < mh and mp[hx - x0, hy - y0] >= 128: op[hx, hy] = 0
    # v18: more small dots around him - single-pixel ash specks scattered in a band around the lower body and
    # drifting up past the shoulders, never on the ring or the figure
    for _ in range(dots):
        ang = rnd.random() * 6.2832; r = 6 + rnd.random() * 9
        dx_ = int(round(math.cos(ang) * r)); dy_ = int(round(math.sin(ang) * r * 0.8))
        px = x0 + mw // 2 + dx_; py = y0 + int(mh * (0.35 + 0.65 * rnd.random())) + dy_
        if 0 <= px < W and 0 <= py < H and rp[px, py] < 100 and op[px, py] == 0:
            inside_fig = 0 <= px - x0 < mw and 0 <= py - y0 < mh and mp[px - x0, py - y0] >= 128
            if not inside_fig: op[px, py] = 255
    return out.resize((W * S, H * S), Image.NEAREST)


def glyph_oil_spring_v2():
    """Oil Spring v2 (user): oil gushing up out of a FISSURE in the ground - a thick ground band with a jagged crack
    opening in it, a gush rising from the crack that widens at the top and sheds drops that fall down both sides."""
    im = canvas(); dr = ImageDraw.Draw(im)
    dr.polygon([(0, 27.5 * S), (40 * S, 26.5 * S), (40 * S, 35 * S), (0, 35 * S)], fill=255)          # the ground
    crack = [(13.0, 35), (14.5, 31.5), (17.0, 29.5), (18.5, 27.0), (20.0, 25.5), (21.5, 27.0), (23.0, 29.5), (25.5, 31.5), (27.0, 35)]
    dr.polygon([(x * S, y * S) for x, y in crack], fill=0)                                                # the fissure (cut out)
    dr.line([(6 * S, 31 * S), (13.5 * S, 32.5 * S)], fill=0, width=int(0.9 * S)); dr.line([(26.5 * S, 32.5 * S), (34 * S, 30 * S)], fill=0, width=int(0.9 * S))   # side cracks
    pts = []
    for i in range(15):                                                                                   # the gush: a thin column out of the crack, flaring into a crown at the top
        t = i / 14.0; y = 25.5 - 19 * t; w = 1.6 + 1.2 * t + (4.5 * max(0.0, t - 0.72) / 0.28) ** 1.3
        pts.append(((20 - w + 0.8 * math.sin(t * 9)) * S, y * S))
    pts.append((20 * S, 4.0 * S))
    for i in range(14, -1, -1):
        t = i / 14.0; y = 25.5 - 19 * t; w = 1.6 + 1.2 * t + (4.5 * max(0.0, t - 0.72) / 0.28) ** 1.3
        pts.append(((20 + w + 0.8 * math.sin(t * 9 + 1.4)) * S, y * S))
    dr.polygon(pts, fill=255)
    for cx, cy, r in ((10.5, 7.5, 1.6), (29.5, 7.0, 1.6), (6.5, 13.0, 1.4), (33.5, 12.5, 1.4), (4.0, 19.5, 1.2), (36.0, 19.0, 1.2), (12.5, 15.5, 1.0), (27.5, 15.0, 1.0), (8.0, 24.0, 0.9), (32.0, 24.0, 0.9)):
        teardrop(dr, cx * S, cy * S, r * S, tip_up=False)                                                 # drops arcing out and falling either side
    return im


def glyph_lionheart_v2():
    """Lionheart v2 (user: a lion's head like Summon Boar's head): a solid face with the eyes, nose and mouth cut out,
    round ears, and a full mane of tufts round it separated from the face by a thin gap."""
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy = 20.0, 18.5
    for k in range(16):                                                                                   # mane tufts
        a = math.radians(k * 22.5 + 11); r0, r1 = 11.0, 17.0 + (1.5 if k % 2 else 0.0)
        bx, by = cx + r0 * math.cos(a), cy + r0 * 0.95 * math.sin(a); tx, ty = cx + r1 * math.cos(a), cy + r1 * 0.95 * math.sin(a)
        px, py = -math.sin(a), math.cos(a)
        dr.polygon([((bx + px * 2.6) * S, (by + py * 2.6) * S), ((bx - px * 2.6) * S, (by - py * 2.6) * S), (tx * S, ty * S)], fill=255)
    dr.ellipse([(cx - 11.2) * S, (cy - 10.8) * S, (cx + 11.2) * S, (cy + 10.8) * S], fill=0)              # gap ring
    dr.ellipse([(cx - 10.2) * S, (cy - 9.8) * S, (cx + 10.2) * S, (cy + 9.8) * S], fill=255)              # the face
    for ex in (cx - 7.5, cx + 7.5):                                                                       # ears (over the mane gap)
        dr.ellipse([(ex - 2.6) * S, (cy - 11.5) * S, (ex + 2.6) * S, (cy - 6.8) * S], fill=255); dr.ellipse([(ex - 1.1) * S, (cy - 10.3) * S, (ex + 1.1) * S, (cy - 8.0) * S], fill=0)
    dr.polygon([((cx - 7.2) * S, (cy - 3.2) * S), ((cx - 2.0) * S, (cy - 2.0) * S), ((cx - 2.6) * S, (cy - 0.4) * S), ((cx - 6.8) * S, (cy - 0.8) * S)], fill=0)   # eyes (narrowed)
    dr.polygon([((cx + 7.2) * S, (cy - 3.2) * S), ((cx + 2.0) * S, (cy - 2.0) * S), ((cx + 2.6) * S, (cy - 0.4) * S), ((cx + 6.8) * S, (cy - 0.8) * S)], fill=0)
    dr.polygon([((cx - 2.8) * S, (cy + 2.2) * S), ((cx + 2.8) * S, (cy + 2.2) * S), (cx * S, (cy + 5.0) * S)], fill=0)                                           # nose
    dr.line([(cx * S, (cy + 5.0) * S), (cx * S, (cy + 6.8) * S)], fill=0, width=int(1.0 * S))
    dr.line([((cx - 5.0) * S, (cy + 8.4) * S), (cx * S, (cy + 6.6) * S), ((cx + 5.0) * S, (cy + 8.4) * S)], fill=0, width=int(1.1 * S))                        # mouth
    for mx in (cx - 8.6, cx + 8.6):                                                                       # whisker dots
        for my in (cy + 4.0, cy + 6.2): dr.ellipse([(mx - 0.55) * S, (my - 0.55) * S, (mx + 0.55) * S, (my + 0.55) * S], fill=0)
    return im


def glyph_oil_spring_v3():
    """Oil Spring v3 (user: the ground was inverted - the fissure must be BLACK and the ground OUTLINE art, not a solid
    band): a thin ground line (uneven surface, two short hairline cracks), a solid black jagged fissure opening in it,
    and the oil - one black shape - rising out of the fissure as a column that flares into a rounded crown, with drops
    falling either side."""
    im = canvas(); dr = ImageDraw.Draw(im)
    surf = [(0, 28.6), (5, 28.2), (10, 28.5), (14.5, 28.0), (25.5, 28.0), (30, 28.4), (35, 28.1), (40, 28.5)]          # the ground surface (outline)
    dr.line([(x * S, y * S) for x, y in surf], fill=255, width=int(1.5 * S), joint="curve")
    dr.line([(2 * S, 33.6 * S), (38 * S, 33.6 * S)], fill=255, width=int(0.9 * S))                                    # a faint lower edge: ground thickness
    for a, b in (((6.0, 28.4), (9.5, 31.5)), ((9.5, 31.5), (8.0, 33.4)), ((33.0, 28.3), (30.5, 31.0)), ((30.5, 31.0), (32.5, 33.4))):
        dr.line([(a[0] * S, a[1] * S), (b[0] * S, b[1] * S)], fill=255, width=int(0.9 * S))                           # hairline cracks
    fissure = [(11.5, 27.6), (13.8, 29.6), (13.0, 31.4), (15.6, 32.6), (17.4, 35.0), (22.6, 35.0), (24.6, 32.4), (26.8, 31.2), (26.0, 29.4), (28.5, 27.6)]
    dr.polygon([(x * S, y * S) for x, y in fissure], fill=255)                                                          # the fissure: solid black
    pts = []
    for i in range(17):                                                                                                 # the column: a thin jet out of the fissure mouth, flaring into a splash crown
        t = i / 16.0; y = 28.5 - 20.0 * t; w = 2.1 - 0.7 * t + 3.6 * max(0.0, t - 0.74) ** 1.3 / 0.26 ** 1.3
        pts.append(((20 - w) * S, y * S))
    pts += [((20 - 7.4) * S, 6.0 * S), ((20 - 8.6) * S, 3.4 * S), ((20 - 6.4) * S, 5.6 * S), ((20 - 4.0) * S, 4.4 * S), ((20 - 2.6) * S, 2.2 * S), ((20 - 1.4) * S, 4.6 * S), (20 * S, 4.2 * S),
            ((20 + 1.4) * S, 4.6 * S), ((20 + 2.6) * S, 2.2 * S), ((20 + 4.0) * S, 4.4 * S), ((20 + 6.4) * S, 5.6 * S), ((20 + 8.6) * S, 3.4 * S), ((20 + 7.4) * S, 6.0 * S)]
    for i in range(16, -1, -1):
        t = i / 16.0; y = 28.5 - 20.0 * t; w = 2.1 - 0.7 * t + 3.6 * max(0.0, t - 0.74) ** 1.3 / 0.26 ** 1.3
        pts.append(((20 + w) * S, y * S))
    dr.polygon(pts, fill=255)
    for cx, cy, r in ((11.0, 8.5, 1.5), (29.0, 8.5, 1.5), (7.5, 13.5, 1.3), (32.5, 13.5, 1.3), (5.5, 19.5, 1.1), (34.5, 19.5, 1.1), (10.0, 23.5, 0.9), (30.0, 23.5, 0.9)):
        teardrop(dr, cx * S, cy * S, r * S, tip_up=True)                                                                # drops flung from the crown, falling either side
    return im


def glyph_lionheart_v3(ring=False):
    """Lionheart v3 (user: a STYLIZED lion head, no spiky elements): a heraldic front-facing lion head as one solid
    silhouette - a full mane with soft rounded locks (no spikes), small round ears, and the face read through its
    cut-outs: heavy brows over narrowed eyes, a broad nose, whisker pads and an open roaring mouth with a chin tuft."""
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy = 20.0, 18.0
    mane = []
    for k in range(360):                                                                                                # mane: soft scallops (9 locks), wider than tall, heavier at the bottom
        a = math.radians(k); r = 1.0 + 0.085 * math.cos(9 * a + 0.3) + 0.03 * math.cos(2 * a)
        mane.append(((cx + 16.2 * r * math.cos(a)) * S, (cy + 1.0 + 14.8 * r * math.sin(a)) * S))
    dr.polygon(mane, fill=255)
    for ex in (cx - 9.0, cx + 9.0):                                                                                     # ears: round, sitting on top of the mane
        dr.ellipse([(ex - 3.1) * S, (cy - 15.6) * S, (ex + 3.1) * S, (cy - 9.6) * S], fill=255)
        dr.ellipse([(ex - 1.4) * S, (cy - 14.2) * S, (ex + 1.4) * S, (cy - 11.4) * S], fill=0)
    if ring:                                                                                                            # optional thin gap separating the face from the mane
        dr.ellipse([(cx - 10.6) * S, (cy - 10.4) * S, (cx + 10.6) * S, (cy + 10.6) * S], fill=0)
        dr.ellipse([(cx - 9.7) * S, (cy - 9.5) * S, (cx + 9.7) * S, (cy + 9.7) * S], fill=255)
    # brows + eyes (cut out): a heavy V brow line, narrowed eyes beneath
    dr.polygon([((cx - 8.2) * S, (cy - 5.0) * S), ((cx - 2.2) * S, (cy - 3.2) * S), ((cx - 2.6) * S, (cy - 1.4) * S), ((cx - 7.6) * S, (cy - 2.6) * S)], fill=0)
    dr.polygon([((cx + 8.2) * S, (cy - 5.0) * S), ((cx + 2.2) * S, (cy - 3.2) * S), ((cx + 2.6) * S, (cy - 1.4) * S), ((cx + 7.6) * S, (cy - 2.6) * S)], fill=0)
    dr.polygon([((cx - 3.4) * S, (cy + 0.8) * S), ((cx + 3.4) * S, (cy + 0.8) * S), ((cx + 1.2) * S, (cy + 4.0) * S), ((cx - 1.2) * S, (cy + 4.0) * S)], fill=0)   # nose
    for sx in (-1, 1):                                                                                                  # whisker pads: two cut-out arcs either side of the muzzle
        dr.ellipse([(cx + sx * 5.6 - 2.6) * S, (cy + 3.2) * S, (cx + sx * 5.6 + 2.6) * S, (cy + 7.0) * S], fill=0)
        for wy in (4.2, 5.6):
            dr.ellipse([(cx + sx * 5.6 - 0.5) * S, (wy + cy - 0.5) * S, (cx + sx * 5.6 + 0.5) * S, (wy + cy + 0.5) * S], fill=255)   # whisker dots (ink inside the pad)
    dr.polygon([((cx - 5.4) * S, (cy + 7.4) * S), ((cx + 5.4) * S, (cy + 7.4) * S), ((cx + 3.2) * S, (cy + 12.2) * S), ((cx - 3.2) * S, (cy + 12.2) * S)], fill=0)   # open roaring mouth
    dr.polygon([((cx - 2.6) * S, (cy + 7.4) * S), ((cx - 1.2) * S, (cy + 7.4) * S), ((cx - 1.9) * S, (cy + 9.8) * S)], fill=255)   # fangs
    dr.polygon([((cx + 1.2) * S, (cy + 7.4) * S), ((cx + 2.6) * S, (cy + 7.4) * S), ((cx + 1.9) * S, (cy + 9.8) * S)], fill=255)
    return im


def glyph_lionheart_ring():
    return glyph_lionheart_v3(ring=True)


def _arc_stroke(dr, pts, w):
    """A tapered stroke along a polyline: circles of shrinking radius."""
    n = len(pts)
    for k in range(n - 1):
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        for t in (0.0, 0.25, 0.5, 0.75):
            x = x0 + (x1 - x0) * t; y = y0 + (y1 - y0) * t; r = w[k] + (w[k + 1] - w[k]) * t
            dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)


def glyph_oil_spring_v5():
    """Oil Spring v5 (user: refer to Geyser's icon 109): Geyser's fountain language in thin strokes - a slim central jet
    whose head splits into two short curls, two side jets curving outward from the base, drops at the tips - in OIL:
    the jets rise out of a black fissure in a thin ground line."""
    im = canvas(); dr = ImageDraw.Draw(im)
    dr.line([(0, 30.4 * S), (8, 30.0 * S), (14, 30.3 * S), (26, 30.3 * S), (32, 30.0 * S), (40 * S, 30.4 * S)], fill=255, width=int(1.1 * S), joint="curve")   # ground line
    dr.polygon([(x * S, y * S) for x, y in ((14.5, 30.0), (16.2, 31.8), (15.6, 33.2), (18.0, 35.0), (22.0, 35.0), (24.4, 33.2), (23.8, 31.8), (25.5, 30.0))], fill=255)      # the fissure
    _arc_stroke(dr, [(20.0, 30.0), (20.0, 23.0), (20.0, 15.0), (20.0, 8.5), (20.0, 4.5)], [1.7, 1.4, 1.2, 1.0, 0.9])                                     # central jet
    _arc_stroke(dr, [(20.0, 4.8), (17.2, 3.4), (14.4, 4.4), (12.6, 7.2), (12.2, 10.5)], [0.9, 0.85, 0.8, 0.7, 0.6])                                       # crown curls
    _arc_stroke(dr, [(20.0, 4.8), (22.8, 3.4), (25.6, 4.4), (27.4, 7.2), (27.8, 10.5)], [0.9, 0.85, 0.8, 0.7, 0.6])
    _arc_stroke(dr, [(16.0, 30.0), (14.6, 24.5), (11.8, 18.5), (8.0, 13.5), (4.2, 10.5)], [1.2, 1.05, 0.9, 0.75, 0.6])                                   # side jets
    _arc_stroke(dr, [(24.0, 30.0), (25.4, 24.5), (28.2, 18.5), (32.0, 13.5), (35.8, 10.5)], [1.2, 1.05, 0.9, 0.75, 0.6])
    for cx, cy, r in ((3.0, 7.0, 0.9), (37.0, 7.0, 0.9), (12.0, 13.6, 0.9), (28.0, 13.6, 0.9), (6.5, 15.5, 0.7), (33.5, 15.5, 0.7), (10.0, 24.0, 0.8), (30.0, 24.0, 0.8)):
        teardrop(dr, cx * S, cy * S, r * S, tip_up=True)                                                          # drops leaving the tips
    return im


def glyph_lionheart_v7():
    """Lionheart v7 LINE ART (user: 'restart from scratch, make it a lion head'): a front-facing lion face drawn in
    outline like the thin-stroke vanilla icons (Geyser, Ice Shards): a wavy mane contour with eight big lobes, the
    round face contour inside it, two ears, short hair strokes between the two contours, and the features in solid ink
    - brows + eyes, the broad nose, whisker pads, an open mouth."""
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy = 20.0, 18.0; W_ = int(1.25 * S)
    mane = []
    for k in range(361):                                                                                                # mane contour: 8 big soft lobes
        a = math.radians(k); r = 1.0 + 0.10 * math.cos(8 * a) + 0.045 * math.cos(5 * a + 0.9) + 0.03 * math.cos(13 * a + 2.0)   # irregular lobes: hair, not a flower
        mane.append(((cx + 16.8 * r * math.cos(a)) * S, (cy + 0.5 + 15.0 * r * math.sin(a)) * S))
    dr.line(mane, fill=255, width=W_, joint="curve")
    face = [((cx + 9.6 * math.cos(math.radians(k))) * S, (cy + 0.8 + 9.4 * math.sin(math.radians(k))) * S) for k in range(361)]
    dr.line(face, fill=255, width=int(1.1 * S), joint="curve")                                                           # face contour
    for sx in (-1, 1):                                                                                                  # ears: small arcs on top of the face contour
        ex = cx + sx * 7.2
        dr.arc([(ex - 3.0) * S, (cy - 12.6) * S, (ex + 3.0) * S, (cy - 5.6) * S], 200, 340, fill=255, width=int(1.1 * S))
    for k in range(16):                                                                                                 # hair strokes between the contours
        a = math.radians(k * 22.5 + 11.25 + (6 if k % 2 else -6)); r0, r1 = 10.6, 13.6 + (0.8 if k % 2 else 0)
        dr.line([((cx + r0 * math.cos(a)) * S, (cy + 0.8 + r0 * 0.95 * math.sin(a)) * S), ((cx + r1 * math.cos(a)) * S, (cy + 0.6 + r1 * 0.95 * math.sin(a)) * S)], fill=255, width=int(0.9 * S))
    for sx in (-1, 1):                                                                                                  # brows + eyes (solid)
        dr.polygon([((cx + sx * 7.0) * S, (cy - 3.6) * S), ((cx + sx * 2.2) * S, (cy - 2.2) * S), ((cx + sx * 2.6) * S, (cy - 0.6) * S), ((cx + sx * 6.6) * S, (cy - 1.6) * S)], fill=255)
    dr.polygon([((cx - 2.8) * S, (cy + 1.6) * S), ((cx + 2.8) * S, (cy + 1.6) * S), ((cx + 1.0) * S, (cy + 4.2) * S), ((cx - 1.0) * S, (cy + 4.2) * S)], fill=255)   # nose
    dr.line([(cx * S, (cy + 4.2) * S), (cx * S, (cy + 5.6) * S)], fill=255, width=int(0.9 * S))
    for sx in (-1, 1):                                                                                                  # whisker pads (outline arcs)
        dr.arc([(cx + sx * 3.8 - 3.4) * S, (cy + 3.8) * S, (cx + sx * 3.8 + 3.4) * S, (cy + 8.4) * S], 0, 180, fill=255, width=int(0.9 * S))
    dr.polygon([((cx - 3.2) * S, (cy + 8.2) * S), ((cx + 3.2) * S, (cy + 8.2) * S), ((cx + 1.6) * S, (cy + 10.6) * S), ((cx - 1.6) * S, (cy + 10.6) * S)], fill=255)   # open mouth (solid)
    return im


def glyph_oil_spring_v6():
    """Oil Spring v6 (user: 'refer to geyser'): GEYSER'S OWN GLYPH (vanilla icon 109, the fountain of thin jets) lifted
    1:1 and raised a little, with a black fissure in a thin ground line under it and heavy oil drops falling from the
    jets' tips - the same silhouette the player already knows, in oil."""
    im = canvas()
    gz = vanilla_ink(109)
    paste_max(im, gz.crop((0, 0, 40, 31)).resize((40 * S, 31 * S), Image.BICUBIC), (0, 0))             # the geyser, bottom rows replaced by the ground
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 28.6 * S, 40 * S, 35 * S], fill=0)                                                   # clear the base rows
    dr.line([(0, 30.2 * S), (9, 29.9 * S), (15, 30.2 * S), (25, 30.2 * S), (31, 29.9 * S), (40 * S, 30.2 * S)], fill=255, width=int(1.1 * S), joint="curve")   # ground line
    dr.polygon([(x * S, y * S) for x, y in ((14.0, 29.8), (16.0, 31.6), (15.4, 33.0), (17.8, 35.0), (22.2, 35.0), (24.6, 33.0), (24.0, 31.6), (26.0, 29.8))], fill=255)   # fissure
    dr.polygon([(x * S, y * S) for x, y in ((17.6, 30.6), (20.0, 26.0), (22.4, 30.6))], fill=255)      # the jet rising out of it
    for cx, cy, r in ((6.0, 21.0, 1.1), (34.0, 21.0, 1.1), (3.5, 26.0, 0.9), (36.5, 26.0, 0.9), (12.5, 25.5, 1.0), (27.5, 25.5, 1.0), (16.0, 6.5, 0.9), (24.0, 6.5, 0.9)):
        teardrop(dr, cx * S, cy * S, r * S, tip_up=True)
    return im


def glyph_oil_spring():
    """Oil Spring v7 (user: centre the geyser on the fissure, fissure like TREMORS' icon 54, geyser thicker than Geyser's):
    the Tremors crack (vanilla ink 54, a bold jagged fissure with side branches) rotated to lie along the bottom, and
    Geyser's fountain (vanilla ink 109) thickened by a 3-px max filter, scaled and centred on the crack's middle with
    heavy oil drops falling from its tips."""
    im = canvas()
    crack = vanilla_ink(54).filter(ImageFilter.MaxFilter(3)).rotate(42, resample=Image.BICUBIC, expand=True)   # the Tremors crack, bolder, laid flat
    bb = crack.getbbox(); crack = crack.crop(bb)
    cw, ch = 34, 12; crack = crack.resize((cw * S, ch * S), Image.BICUBIC).point(lambda v: 255 if v > 90 else 0)
    paste_max(im, crack, (3 * S, 23 * S))                                                             # fissure x 3..37, y 23..35
    gw, gh = 30, 26; gz = vanilla_ink(109).crop((5, 0, 35, 29)).resize((gw * S, gh * S), Image.BICUBIC).filter(ImageFilter.MaxFilter(9))   # Geyser's fountain, strokes ~1 px thicker (at 8x), jets kept apart
    paste_max(im, gz, (5 * S, 0))                                                                     # centred on x = 20, feet at y 26 on the crack
    dr = ImageDraw.Draw(im)
    for cx, cy, r in ((4.5, 17.5, 1.2), (35.5, 17.5, 1.2), (9.0, 22.5, 1.0), (31.0, 22.5, 1.0), (14.5, 4.0, 0.9), (25.5, 4.0, 0.9)):
        teardrop(dr, cx * S, cy * S, r * S, tip_up=True)                                              # oil drops
    return im


LION_MASK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lion_user_mask.png")   # v9: the user's reference (art import export/lionheart idea.jpg) traced by tmp\lion_user_trace.py; the heraldic trace lives in lion_heraldic_mask.png


def glyph_lionheart():
    """Lionheart v9 = the USER'S reference image (a tribal black-on-white front-facing lion head) traced to 40x35 (crisp
    binarised downsample; lion_user_mask.png = source of truth, white = ink).  v8 (below in spirit) was a TRACED heraldic lion head - Wikimedia Commons 'Meuble heraldique
    Tete (lion).svg' (outline art of a roaring lion head with its tongue out, mane erased) filled to a silhouette with
    the eye and the open mouth cut out, cropped and fitted to 40x35 (tmp\lion_trace.py -> lion_heraldic_mask.png,
    which is the source of truth; white = ink)."""
    m = Image.open(LION_MASK).convert("L")
    return m.resize((W * S, H * S), Image.BICUBIC)


def glyph_lionheart_front():
    """Lionheart v6 FRONT (the Hell Hound icon's language): a round face with the eyes, nose and open mouth cut out, two
    ears, and a mane of swept flame-like locks all round it (no gap ring)."""
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy = 20.0, 18.5
    for k in range(12):                                                                                                 # mane locks: swept, curved tongues
        a0 = math.radians(k * 30 + 15); a1 = a0 + math.radians(22); am = a0 + math.radians(11)
        r0, r1 = 9.5, 16.5 + (1.5 if k % 2 == 0 else 0.0)
        pts = [(cx + r0 * math.cos(a0), cy + r0 * 0.95 * math.sin(a0)), (cx + (r0 + 3.5) * math.cos(a0 + 0.12), cy + (r0 + 3.5) * 0.95 * math.sin(a0 + 0.12)),
               (cx + r1 * math.cos(am + 0.22), cy + r1 * 0.95 * math.sin(am + 0.22)), (cx + (r0 + 3.5) * math.cos(a1 - 0.05), cy + (r0 + 3.5) * 0.95 * math.sin(a1 - 0.05)),
               (cx + r0 * math.cos(a1), cy + r0 * 0.95 * math.sin(a1))]
        dr.polygon([(x * S, y * S) for x, y in pts], fill=255)
    dr.ellipse([(cx - 10.5) * S, (cy - 10.0) * S, (cx + 10.5) * S, (cy + 10.5) * S], fill=255)                                 # face
    for ex in (cx - 8.0, cx + 8.0):                                                                                      # ears
        dr.ellipse([(ex - 3.0) * S, (cy - 14.0) * S, (ex + 3.0) * S, (cy - 8.0) * S], fill=255); dr.ellipse([(ex - 1.3) * S, (cy - 12.6) * S, (ex + 1.3) * S, (cy - 9.8) * S], fill=0)
    dr.polygon([((cx - 8.0) * S, (cy - 4.6) * S), ((cx - 2.4) * S, (cy - 2.8) * S), ((cx - 3.0) * S, (cy - 0.6) * S), ((cx - 7.6) * S, (cy - 2.0) * S)], fill=0)   # eyes
    dr.polygon([((cx + 8.0) * S, (cy - 4.6) * S), ((cx + 2.4) * S, (cy - 2.8) * S), ((cx + 3.0) * S, (cy - 0.6) * S), ((cx + 7.6) * S, (cy - 2.0) * S)], fill=0)
    dr.polygon([((cx - 3.0) * S, (cy + 1.2) * S), ((cx + 3.0) * S, (cy + 1.2) * S), ((cx + 1.0) * S, (cy + 4.0) * S), ((cx - 1.0) * S, (cy + 4.0) * S)], fill=0)   # nose
    dr.line([(cx * S, (cy + 4.0) * S), (cx * S, (cy + 5.6) * S)], fill=0, width=int(0.9 * S))
    dr.polygon([((cx - 6.0) * S, (cy + 5.8) * S), ((cx + 6.0) * S, (cy + 5.8) * S), ((cx + 3.6) * S, (cy + 10.2) * S), ((cx - 3.6) * S, (cy + 10.2) * S)], fill=0)   # open mouth
    for fx in (cx - 3.2, cx + 1.8):
        dr.polygon([(fx * S, (cy + 5.8) * S), ((fx + 1.4) * S, (cy + 5.8) * S), ((fx + 0.7) * S, (cy + 8.2) * S)], fill=255)
    return im


def glyph_sandstorm_v1():
    """Sandstorm (388): the Air tornado swirl (vanilla ink 10) blown sideways with a spray of sand grains and two gust
    streaks."""
    im = canvas()
    tw = vanilla_ink(10).crop((4, 2, 36, 33)).resize((30 * S, 29 * S), Image.BICUBIC)
    paste_max(im, tw, (6 * S, 3 * S))
    dr = ImageDraw.Draw(im); rnd = random.Random(388)
    for _ in range(26):
        x, y = rnd.uniform(1.5, 38.5), rnd.uniform(3, 32); r = rnd.uniform(0.45, 1.0)
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)
    for y0, x0, x1 in ((9.0, 1.0, 7.0), (23.5, 0.5, 5.5), (30.5, 2.0, 9.0)):
        dr.line([(x0 * S, y0 * S), (x1 * S, (y0 - 1.2) * S)], fill=255, width=int(1.0 * S))
    return im


def glyph_implosion_v1():
    """Implosion (389): a bold ring with six wedges pointing inward and a small dense core."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 17.5
    stroke_ellipse(dr, [(cx - 15.0) * S, (cy - 14.5) * S, (cx + 15.0) * S, (cy + 14.5) * S], int(1.6 * S))
    for k in range(4):                                                                                                  # four arrows pointing INTO the core
        a = math.radians(k * 90 + 45); ux, uy = math.cos(a), math.sin(a); px, py = -uy, ux
        dr.line([((cx + 13.0 * ux) * S, (cy + 12.6 * uy) * S), ((cx + 6.6 * ux) * S, (cy + 6.4 * uy) * S)], fill=255, width=int(1.6 * S))
        tip = (cx + 4.4 * ux, cy + 4.2 * uy); b1 = (cx + 8.2 * ux + 2.4 * px, cy + 8.0 * uy + 2.3 * py); b2 = (cx + 8.2 * ux - 2.4 * px, cy + 8.0 * uy - 2.3 * py)
        dr.polygon([(tip[0] * S, tip[1] * S), (b1[0] * S, b1[1] * S), (b2[0] * S, b2[1] * S)], fill=255)
    dr.ellipse([(cx - 2.6) * S, (cy - 2.5) * S, (cx + 2.6) * S, (cy + 2.5) * S], fill=255)
    for k in range(8):                                                                                                  # debris shards being pulled in between the arrows
        a = math.radians(k * 45 + 22.5 + (8 if k % 2 else -8)); r0 = 9.0 + (k % 3)
        dr.line([((cx + r0 * math.cos(a)) * S, (cy + r0 * 0.97 * math.sin(a)) * S), ((cx + (r0 - 2.4) * math.cos(a)) * S, (cy + (r0 - 2.4) * 0.97 * math.sin(a)) * S)], fill=255, width=int(0.9 * S))
    return im


def glyph_frenzy_v1():
    """Frenzied Charge (390): the Haste runner (vanilla ink 0, speed lines and all) with flames streaming off his
    back."""
    im = canvas()
    paste_max(im, vanilla_ink(0).resize((W * S, H * S), Image.BICUBIC), (0, 0))
    dr = ImageDraw.Draw(im)
    for cx, cy, r in ((9.0, 8.5, 1.9), (6.0, 12.5, 1.6), (11.5, 14.0, 1.4), (4.5, 17.5, 1.2)):
        teardrop(dr, cx * S, cy * S, r * S, tip_up=True)
    return im


def glyph_sandstorm_v2():
    """Sandstorm v2 (user: too close to Tornado; take Tornado + Winds of Fury's arcs minus the man): three sweeping
    wind arcs rushing in from the left and curling down into a squat funnel on the right, grit streaming off them."""
    im = canvas(); dr = ImageDraw.Draw(im); rnd = random.Random(3880)
    for k, (y0, amp, w) in enumerate(((7.0, 4.0, 1.9), (14.0, 5.0, 2.3), (21.5, 4.0, 1.9))):
        pts = []
        for i in range(26):
            t = i / 25.0; x = 1.5 + 30.0 * t; y = y0 + amp * math.sin(t * 3.6 + k * 0.8) + 2.0 * t * t
            pts.append((x * S, y * S))
        dr.line(pts, fill=255, width=int(w * S), joint="curve")
    funnel = [(25.0, 13.0), (37.5, 11.5), (36.0, 16.0), (33.5, 20.5), (31.5, 25.5), (30.5, 31.0), (28.5, 31.0), (27.0, 25.5), (25.5, 20.5), (23.5, 16.0)]   # the funnel on the right
    dr.polygon([(x * S, y * S) for x, y in funnel], fill=255)
    for y0 in (14.5, 19.0, 23.5):
        dr.line([(24.5 * S, y0 * S), (36.5 * S, (y0 - 1.0) * S)], fill=0, width=int(0.8 * S))                        # bands cut into the funnel
    for _ in range(22):
        x, y = rnd.uniform(2, 24), rnd.uniform(4, 32); r = rnd.uniform(0.45, 0.95)
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)
    return im


def glyph_implosion_v2():
    """Implosion v2 (user: a galaxy swirl): three logarithmic spiral arms of dots and strokes winding into a dense
    core, dust specks between them."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 17.5; rnd = random.Random(3890)
    for arm in range(3):
        a0 = arm * 2.094
        for i in range(30):
            t = i / 29.0; r = 1.5 + 15.5 * t; a = a0 + 2.9 * (1 - t) * 1.25
            x = cx + r * math.cos(a); y = cy + 0.9 * r * math.sin(a); d = 2.0 - 1.3 * t
            dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    dr.ellipse([(cx - 3.2) * S, (cy - 3.0) * S, (cx + 3.2) * S, (cy + 3.0) * S], fill=255)
    for _ in range(18):
        r = rnd.uniform(5, 17); a = rnd.uniform(0, 6.28); x = cx + r * math.cos(a); y = cy + 0.9 * r * math.sin(a); d = rnd.uniform(0.4, 0.8)
        dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    return im


def glyph_frenzy_v2():
    """Frenzied Charge v2 (user: a reckless angry face, more exaggerated than Fury's): a wide solid head with slashing
    V brows, mismatched bulging eyes, a huge screaming mouth full of jagged teeth and a wild spiky crest."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 19.0
    dr.ellipse([(cx - 14.0) * S, (cy - 13.0) * S, (cx + 14.0) * S, (cy + 13.5) * S], fill=255)                     # the head
    for k in range(9):                                                                                              # spiky crest
        x = cx - 12 + 3.0 * k; h = 5.5 + 3.5 * math.sin(k * 1.3)
        dr.polygon([((x - 1.6) * S, (cy - 10.0) * S), ((x + 1.6) * S, (cy - 10.0) * S), ((x + 0.6 - 1.2) * S, (cy - 10.0 - h) * S)], fill=255)
    dr.polygon([((cx - 11.0) * S, (cy - 6.5) * S), ((cx - 2.0) * S, (cy - 2.5) * S), ((cx - 2.5) * S, (cy - 1.0) * S), ((cx - 11.5) * S, (cy - 4.2) * S)], fill=0)   # brows (V, cut out)
    dr.polygon([((cx + 11.0) * S, (cy - 6.5) * S), ((cx + 2.0) * S, (cy - 2.5) * S), ((cx + 2.5) * S, (cy - 1.0) * S), ((cx + 11.5) * S, (cy - 4.2) * S)], fill=0)
    dr.ellipse([(cx - 9.2) * S, (cy - 3.0) * S, (cx - 3.4) * S, (cy + 2.2) * S], fill=0)                             # eyes: one bulging, one squinting
    dr.ellipse([(cx - 7.0) * S, (cy - 1.2) * S, (cx - 5.4) * S, (cy + 0.4) * S], fill=255)
    dr.ellipse([(cx + 3.6) * S, (cy - 1.6) * S, (cx + 8.2) * S, (cy + 1.6) * S], fill=0)
    dr.ellipse([(cx + 5.2) * S, (cy - 0.6) * S, (cx + 6.6) * S, (cy + 0.6) * S], fill=255)
    dr.polygon([((cx - 10.5) * S, (cy + 4.0) * S), ((cx + 10.5) * S, (cy + 4.0) * S), ((cx + 8.0) * S, (cy + 11.5) * S), ((cx - 8.0) * S, (cy + 11.5) * S)], fill=0)   # the screaming mouth
    for k in range(6):                                                                                              # jagged teeth top and bottom
        x = cx - 8.5 + 3.4 * k
        dr.polygon([((x - 1.3) * S, (cy + 4.0) * S), ((x + 1.3) * S, (cy + 4.0) * S), (x * S, (cy + 7.2) * S)], fill=255)
        dr.polygon([((x + 0.4) * S, (cy + 11.5) * S), ((x + 3.0) * S, (cy + 11.5) * S), ((x + 1.7) * S, (cy + 8.8) * S)], fill=255)
    return im


def glyph_sandstorm_v3():
    """Sandstorm v3: a towering cone of sand - thousands of grains stippled densely at the core and thinning to the
    edges, bent by the wind, with a few bigger stones flung out of it."""
    im = canvas(); dr = ImageDraw.Draw(im); rnd = random.Random(3883)
    for _ in range(900):
        t = rnd.random() ** 0.8                                                                       # height fraction (0 = base)
        y = 33.0 - 30.0 * t; half = 3.0 + 13.0 * t; x = 20.0 + 4.0 * t * t + rnd.gauss(0, 1) * half * 0.45
        if abs(x - (20.0 + 4.0 * t * t)) > half: continue
        r = rnd.uniform(0.35, 0.8) + 0.35 * (1 - abs(x - (20.0 + 4.0 * t * t)) / half)
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)
    for cx, cy, r in ((5.5, 10.0, 1.3), (34.5, 7.5, 1.4), (3.5, 20.5, 1.0), (36.5, 17.0, 1.1), (9.0, 4.0, 0.9), (31.5, 25.0, 0.9)):
        dr.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=255)
    return im


def glyph_frenzy_v3():
    """Frenzied Charge v3 (user: refer to Fury and Terror): Terror's jagged burst framing Fury's fanged grin - a
    screaming, fanged face with slashing brows inside a ring of ragged flame spikes."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 18.0; rnd = random.Random(3903)
    burst = []
    for k in range(24):                                                                                   # the jagged burst (Terror's frame)
        a = math.radians(k * 15); r = (15.5 if k % 2 == 0 else 11.0) + rnd.uniform(-1.2, 1.2)
        burst.append(((cx + r * math.cos(a)) * S, (cy + 0.95 * r * math.sin(a)) * S))
    dr.polygon(burst, fill=255)
    dr.ellipse([(cx - 9.2) * S, (cy - 8.6) * S, (cx + 9.2) * S, (cy + 9.0) * S], fill=0)                   # the face field (clear) inside the burst
    dr.polygon([((cx - 8.0) * S, (cy - 6.0) * S), ((cx - 1.6) * S, (cy - 2.2) * S), ((cx - 2.0) * S, (cy - 0.4) * S), ((cx - 8.4) * S, (cy - 3.4) * S)], fill=255)   # slashing brows
    dr.polygon([((cx + 8.0) * S, (cy - 6.0) * S), ((cx + 1.6) * S, (cy - 2.2) * S), ((cx + 2.0) * S, (cy - 0.4) * S), ((cx + 8.4) * S, (cy - 3.4) * S)], fill=255)
    dr.ellipse([(cx - 6.6) * S, (cy - 2.4) * S, (cx - 3.0) * S, (cy + 0.6) * S], fill=255)                 # wild eyes
    dr.ellipse([(cx + 3.0) * S, (cy - 2.4) * S, (cx + 6.6) * S, (cy + 0.6) * S], fill=255)
    dr.polygon([((cx - 1.4) * S, (cy + 1.2) * S), ((cx + 1.4) * S, (cy + 1.2) * S), (cx * S, (cy + 3.2) * S)], fill=255)   # nose
    dr.polygon([((cx - 7.4) * S, (cy + 3.6) * S), ((cx + 7.4) * S, (cy + 3.6) * S), ((cx + 5.6) * S, (cy + 8.4) * S), ((cx - 5.6) * S, (cy + 8.4) * S)], fill=255)   # the open mouth (ink)
    for k in range(5):                                                                                    # fangs cut out of the mouth (Fury's grin)
        x = cx - 5.6 + 2.8 * k
        dr.polygon([((x - 0.9) * S, (cy + 3.6) * S), ((x + 0.9) * S, (cy + 3.6) * S), (x * S, (cy + 6.0) * S)], fill=0)
        dr.polygon([((x + 0.5) * S, (cy + 8.4) * S), ((x + 2.3) * S, (cy + 8.4) * S), ((x + 1.4) * S, (cy + 6.4) * S)], fill=0)
    return im


def glyph_frenzy_v4():
    """Frenzied Charge v4 (user: refer to Fury 60 and Terror 33): Fury's face (vanilla ink 60 - the grinning horned
    head) with Terror's jagged rays (vanilla ink 33's burst) bursting out behind it, and two crossed swords below."""
    im = canvas()
    burst = vanilla_ink(33)
    dr0 = ImageDraw.Draw(burst); dr0.ellipse([11, 8, 29, 27], fill=0)                                   # keep only Terror's spiky ring
    paste_max(im, burst.resize((W * S, H * S), Image.BICUBIC), (0, 0))
    face = vanilla_ink(60).crop((6, 3, 34, 30)).resize((22 * S, 21 * S), Image.BICUBIC)
    dr = ImageDraw.Draw(im); dr.ellipse([9 * S, 6 * S, 31 * S, 28 * S], fill=0)
    paste_max(im, face, (9 * S, 6 * S))
    return im


def glyph_sandstorm_v4():
    return glyph_sandstorm()


def glyph_sandstorm_v5():
    """Sandstorm v5 (user: like Great Hail but with sand spinning): Great Hail's falling stones (vanilla ink 114, centred
    at full size) caught in a spinning ring of separate sand grains that grow along two elliptical arcs."""
    im = canvas()
    paste_max(im, vanilla_ink(114).crop((2, 0, 32, 31)).resize((30 * S, 31 * S), Image.BICUBIC), (5 * S, 2 * S))
    dr = ImageDraw.Draw(im); rnd = random.Random(3884)
    for arc in range(2):
        a0 = arc * math.pi + 0.35
        for k in range(17):
            t = k / 16.0; a = a0 + 2.5 * t + rnd.uniform(-0.04, 0.04); r = 18.0 + rnd.uniform(-0.8, 0.8)
            x = 20 + r * math.cos(a); y = 17.5 + 0.42 * r * math.sin(a); d = 0.35 + 0.55 * t
            dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    return im


def glyph_frenzy_v6():
    """Frenzied Charge v6 (user: a frenzied, angry, barbaric face in the art style of the Fury icon): Fury's own grinning
    face (vanilla ink 60, centred and lowered) under a wild mane of hair spikes, with war-paint slashes on the cheeks."""
    im = canvas()
    paste_max(im, vanilla_ink(60).crop((0, 0, 28, 26)).resize((28 * S, 26 * S), Image.BICUBIC), (6 * S, 7 * S))
    dr = ImageDraw.Draw(im); cx, cy = 20.0, 20.0; rnd = random.Random(3905)
    pts_out, pts_in = [], []                                                       # a jagged hair band (spikes outward)
    N = 15
    for k in range(N + 1):
        a = math.radians(-162 + k * 144.0 / N)
        r = 1.0 if k % 2 == 0 else 1.0 + rnd.uniform(0.30, 0.48)
        pts_out.append((cx + 15.0 * r * math.cos(a + (0.06 if k % 2 else 0)), max(0.3, cy - 0.5 + 14.0 * r * math.sin(a + (0.06 if k % 2 else 0)))))
        pts_in.append((cx + 13.2 * math.cos(a), cy + 0.5 + 12.2 * math.sin(a)))
    poly = pts_out + pts_in[::-1]
    dr.polygon([(x * S, y * S) for x, y in poly], fill=255)
    for x0 in (9.5, 11.5, 28.5, 30.5):
        dr.line([(x0 * S, 17.0 * S), ((x0 - 0.7) * S, 20.0 * S)], fill=255, width=int(0.9 * S))
    return im


def _fz_taper(dr, pts, w0, w1, fill=255):
    """A tapered stroke along polyline pts (40x35 coords), width w0 -> w1."""
    n = len(pts) - 1; L = []; R = []
    for i, (x, y) in enumerate(pts):
        a = pts[min(i + 1, n)]; b = pts[max(i - 1, 0)]
        dx, dy = a[0] - b[0], a[1] - b[1]; l = math.hypot(dx, dy) or 1; nx, ny = -dy / l, dx / l
        w = (w0 + (w1 - w0) * i / n) / 2
        L.append(((x + nx * w) * S, (y + ny * w) * S)); R.append(((x - nx * w) * S, (y - ny * w) * S))
    dr.polygon(L + R[::-1], fill=fill)

def _fz_bez(p0, p1, p2, n=14):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in [i / n for i in range(n + 1)]]

def glyph_frenzy_v7():
    """Frenzied Charge v7 (user: a frenzied angry barbaric face, reference art import export/frenzy.webp - a tribal
    black-on-white snarling face): drawn by hand in that style (an auto-trace broke up at 40x35) - tapered side contours,
    forehead wrinkles, a heavy V brow, glaring pupils over lower lids, furrowed nose, cheek lines and an open snarl with
    two rows of teeth cut out."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        _fz_taper(dr, _fz_bez((X(15.0), 6.0), (X(17.0), 17.0), (X(12.0), 29.6)), 0.5, 2.2)              # side jaw strokes (reference: the face's outer contour)
        _fz_taper(dr, _fz_bez((X(12.5), 30.0), (X(9.0), 33.0), (X(4.0), 33.6)), 2.2, 0.6)
        _fz_taper(dr, _fz_bez((X(1.0), 4.2), (X(6.0), 3.0), (X(11.0), 5.6)), 1.6, 0.5)                    # forehead wrinkles
        _fz_taper(dr, _fz_bez((X(2.0), 7.4), (X(6.5), 6.0), (X(10.0), 8.0)), 1.3, 0.4)
        _fz_taper(dr, _fz_bez((X(1.0), 13.0), (X(6.0), 9.2), (X(13.5), 9.6)), 3.4, 0.8)                  # the angry brow: thick at the centre, sweeping up and out
        _fz_taper(dr, _fz_bez((X(13.5), 9.6), (X(15.0), 10.0), (X(15.6), 11.8)), 0.8, 0.4)
        _fz_taper(dr, _fz_bez((X(3.0), 16.0), (X(7.0), 17.6), (X(11.5), 15.4)), 1.0, 1.6)                # the lower lid
        dr.ellipse([(X(6.6) - 1.5) * S, 13.6 * S, (X(6.6) + 1.5) * S, 16.6 * S], fill=255)        # the pupil (glaring)
        _fz_taper(dr, _fz_bez((X(2.0), 19.0), (X(1.0), 21.5), (X(3.2), 23.0)), 1.6, 0.6)                 # the nostril wing
        _fz_taper(dr, _fz_bez((X(4.0), 18.0), (X(8.5), 20.0), (X(9.0), 26.0)), 1.6, 0.6)                 # cheek line nose -> mouth corner
    _fz_taper(dr, [(17.0, 11.0), (18.5, 15.0)], 1.2, 0.4); _fz_taper(dr, [(23.0, 11.0), (21.5, 15.0)], 1.2, 0.4)   # the furrow between the brows
    dr.ellipse([16.5 * S, 21.0 * S, 23.5 * S, 23.6 * S], fill=255)                                # nose base
    mouth = _fz_bez((12.0, 26.4), (20.0, 23.6), (28.0, 26.4)) + _fz_bez((28.0, 26.4), (26.0, 31.6), (20.0, 31.4))[1:] + _fz_bez((20.0, 31.4), (14.0, 31.6), (12.0, 26.4))[1:]
    dr.polygon([(x * S, y * S) for x, y in mouth], fill=255)                                       # the open snarl
    for k in range(5):                                                                             # teeth: upper row + lower row cut out
        x = 14.6 + k * 2.2
        dr.rectangle([x * S, 26.2 * S, (x + 1.5) * S, 27.6 * S], fill=0)
        dr.rectangle([(x + 0.2) * S, 29.0 * S, (x + 1.5) * S, 30.4 * S], fill=0)
    _fz_taper(dr, _fz_bez((16.5, 33.4), (20.0, 34.6), (23.5, 33.4)), 0.6, 0.6)                             # chin
    return im

def glyph_frenzy_v8():
    """Frenzied Charge v8 (user: remove the forehead lines, make the face look CRAZIER): the v7 tribal face (after
    art import export/frenzy.webp) with wild hair spikes where the wrinkles were, bulging eyes - outlined whites with
    pinpoint pupils, the left eye bigger than the right - under a steep V brow, and a wide screaming mouth with jagged
    teeth top and bottom."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im); rnd = random.Random(3907)
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        _fz_taper(dr, _fz_bez((X(15.0), 6.0), (X(17.0), 17.0), (X(12.0), 29.6)), 0.5, 2.2)              # side contours
        _fz_taper(dr, _fz_bez((X(12.5), 30.0), (X(9.0), 33.0), (X(4.0), 33.6)), 2.2, 0.6)
        _fz_taper(dr, _fz_bez((X(1.0), 12.6), (X(6.0), 7.6), (X(13.8), 7.4)), 3.2, 0.7)                  # steep V brow
        _fz_taper(dr, _fz_bez((X(4.0), 18.6), (X(8.5), 22.0), (X(9.4), 25.6)), 1.5, 0.6)                 # cheek line
        _fz_taper(dr, _fz_bez((X(2.0), 18.6), (X(1.0), 20.8), (X(3.0), 22.0)), 1.6, 0.6)                 # nostril wing
    for k in range(11):                                                                                    # wild, uneven hair spikes across the top
        x0 = 5.5 + k * 2.9 + rnd.uniform(-0.6, 0.6); hw = rnd.uniform(0.9, 2.0); base_y = 6.0 + abs(k - 5) * 0.3
        lean = (x0 - 20) * 0.18 + rnd.uniform(-3.0, 3.0); tip = (x0 + lean, rnd.choice((0.0, 0.6, 1.8, 3.0)))
        dr.polygon([((x0 - hw) * S, base_y * S), ((x0 + hw) * S, base_y * S), (tip[0] * S, tip[1] * S)], fill=255)
    for ex, ey, rx, ry, pr in ((13.2, 13.4, 4.6, 3.8, 0.9), (27.0, 13.8, 3.8, 3.1, 0.8)):                  # bulging eyes, uneven
        dr.ellipse([(ex - rx) * S, (ey - ry) * S, (ex + rx) * S, (ey + ry) * S], fill=255)
        dr.ellipse([(ex - rx + 1.0) * S, (ey - ry + 1.0) * S, (ex + rx - 1.0) * S, (ey + ry - 1.0) * S], fill=0)
        dr.ellipse([(ex - pr) * S, (ey - pr) * S, (ex + pr) * S, (ey + pr) * S], fill=255)              # pinpoint pupil
    _fz_taper(dr, [(18.6, 9.6), (19.4, 13.0)], 1.0, 0.4); _fz_taper(dr, [(21.4, 9.6), (20.6, 13.0)], 1.0, 0.4)   # furrow
    dr.ellipse([16.8 * S, 19.6 * S, 23.2 * S, 22.2 * S], fill=255)                                           # nose base
    mouth = _fz_bez((10.6, 24.6), (20.0, 22.4), (29.4, 24.6)) + _fz_bez((29.4, 24.6), (27.0, 33.4), (20.0, 33.2))[1:] + _fz_bez((20.0, 33.2), (13.0, 33.4), (10.6, 24.6))[1:]
    dr.polygon([(x * S, y * S) for x, y in mouth], fill=255)                                                 # the wide screaming mouth
    for k in range(6):                                                                                       # jagged teeth (cut out)
        x = 13.0 + k * 2.4
        dr.polygon([(x * S, 24.4 * S), ((x + 2.0) * S, 24.2 * S), ((x + 1.0) * S, 27.2 * S)], fill=0)
        dr.polygon([((x + 0.2) * S, 32.0 * S), ((x + 2.0) * S, 32.0 * S), ((x + 1.1) * S, 29.4 * S)], fill=0)
    return im


def glyph_sandstorm_v6():
    """Sandstorm v6 (user: v5's particles too big - should read as SAND, not hail chunks): Great Hail's composition
    (particles streaking down from the upper left) made of fine single-pixel grains with short faint streaks, caught in a
    spinning ring of fine grains (two thin elliptical arcs of dots that thicken along the spin)."""
    im = canvas(); dr = ImageDraw.Draw(im); rnd = random.Random(3886)
    def dot(x, y, d): dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    for k in range(70):                                                                       # falling grains, denser toward the centre
        x = rnd.uniform(3, 36); y = rnd.uniform(2, 32)
        if ((x - 20) / 19.0) ** 2 + ((y - 17) / 16.0) ** 2 > 1.0: continue
        d = rnd.choice((0.5, 0.55, 0.7)); dot(x, y, d)
        if rnd.random() < 0.55:
            L = rnd.uniform(1.8, 3.6); dr.line([((x - L * 0.8) * S, (y - L * 0.6) * S), (x * S, y * S)], fill=170, width=max(1, int(0.45 * S)))
    for arc in range(2):                                                                      # the spinning ring
        a0 = arc * math.pi + 0.35
        for k in range(34):
            t = k / 33.0; a = a0 + 2.7 * t + rnd.uniform(-0.03, 0.03); r = 17.5 + rnd.uniform(-1.0, 1.0)
            dot(20 + r * math.cos(a), 17.5 + 0.42 * r * math.sin(a), 0.4 + 0.45 * t)
    return im


def glyph_sandstorm_v7():
    """Sandstorm v7 (user: like Winds of Fury but with more lines, the lines made of sand dots): Winds of Fury's
    buffeted figure (vanilla ink 8, figure blob only, centred) with seven wind arcs sweeping from the top left down
    round it (the original's sweep, centre top-right), every arc a line of separate sand grains thinning toward its
    tail; grains never cross the figure."""
    im = canvas(); rnd = random.Random(3887)
    src = vanilla_ink(8); fig = ink_component(src, (22, 17)); p = fig.load()
    for y in range(H):
        for x in range(16): p[x, y] = 0                                                    # drop the inner arc fused to the figure
    fig = ink_component(fig, (22, 17))
    big = fig.resize((W * S, H * S), Image.BICUBIC)
    paste_max(im, big, (4 * S, 2 * S))
    fm = fig.load()
    def on_fig(x, y):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                fx, fy = int(round(x - 4 + dx)), int(round(y - 2 + dy))
                if 0 <= fx < W and 0 <= fy < H and fm[fx, fy] > 60: return True
        return False
    dr = ImageDraw.Draw(im); cx, cy = 31.0, 0.5
    for n, r in enumerate((10.0, 14.0, 18.0, 22.0, 26.0, 30.0, 34.0)):
        a0, a1 = math.radians(186), math.radians(96 + 2 * n)
        steps = int(abs(a1 - a0) * r / 1.75)
        for k in range(steps + 1):
            t = k / max(1, steps); a = a0 + (a1 - a0) * t + rnd.uniform(-0.015, 0.015)
            x = cx + r * math.cos(a) + rnd.uniform(-0.25, 0.25); y = cy + r * math.sin(a) + rnd.uniform(-0.25, 0.25)
            if not (0 <= x < W and 0 <= y < H) or on_fig(x, y): continue
            if rnd.random() < 0.15 * t: continue
            d = 0.62 - 0.28 * t
            dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    return im


def glyph_sandstorm_v8():
    """Sandstorm v8 (user: remove the man, polish the wind/sand): only the wind - seven smooth arcs of sand grains
    sweeping from the top left down and round to the lower right (Winds of Fury's sweep), each arc a clean run of
    evenly spaced grains that swell through the middle of the stroke and taper at both ends, plus loose grains
    blowing off the arc tails."""
    im = canvas(); rnd = random.Random(3888); dr = ImageDraw.Draw(im)
    def dot(x, y, d): dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    cx, cy = 33.0, -4.0
    for n, r in enumerate((10.0, 14.5, 19.0, 23.5, 28.0, 32.5, 37.0)):
        a0, a1 = math.radians(176 - 2 * n), math.radians(78 + 2 * n)
        steps = int(abs(a1 - a0) * r / 1.9)
        for k in range(steps + 1):
            t = k / max(1, steps); a = a0 + (a1 - a0) * t
            x = cx + r * math.cos(a); y = cy + r * math.sin(a)
            if not (0.5 <= x < W - 0.5 and 0.5 <= y < H - 0.5): continue
            d = 0.28 + 0.5 * math.sin(math.pi * min(1.0, t * 1.1)) ** 0.8
            dot(x, y, d)
        ta = a1                                                                                          # loose grains off the tail
        for g in range(3):
            x = cx + r * math.cos(ta) + 1.6 * (g + 1) + rnd.uniform(-0.4, 0.4); y = cy + r * math.sin(ta) - 0.5 * (g + 1) + rnd.uniform(-0.6, 0.6)
            if 0.5 <= x < W - 0.5 and 0.5 <= y < H - 0.5: dot(x, y, 0.38 - 0.08 * g)
    return im


def glyph_frenzy_v9():
    """Frenzied Charge v9 (user: v8 got way worse - try again; v7 + no forehead lines + crazier): back to v7's tribal
    face (after art import export/frenzy.webp), forehead lines removed; crazier = the glare widened - thin upper lids
    arch above wide-open eyes with tiny pinpoint pupils staring out under the heavy V brow - and the snarl opened wider
    with jagged fangs top and bottom."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        _fz_taper(dr, _fz_bez((X(15.0), 6.0), (X(17.0), 17.0), (X(12.0), 29.6)), 0.5, 2.2)              # side contours
        _fz_taper(dr, _fz_bez((X(12.5), 30.0), (X(9.0), 33.0), (X(4.0), 33.6)), 2.2, 0.6)
        _fz_taper(dr, _fz_bez((X(1.0), 12.4), (X(6.0), 8.0), (X(13.5), 8.4)), 3.4, 0.8)                  # the heavy V brow
        _fz_taper(dr, _fz_bez((X(13.5), 8.4), (X(15.0), 8.8), (X(15.6), 10.6)), 0.8, 0.4)
        _fz_taper(dr, _fz_bez((X(3.0), 16.6), (X(7.0), 18.4), (X(11.5), 16.0)), 1.0, 1.6)                # lower lid
        dr.ellipse([(X(7.0) - 0.75) * S, 14.3 * S, (X(7.0) + 0.75) * S, 15.8 * S], fill=255)            # tiny pinpoint pupil
        _fz_taper(dr, _fz_bez((X(2.0), 19.4), (X(1.0), 21.6), (X(3.2), 22.8)), 1.6, 0.6)                 # nostril wing
        _fz_taper(dr, _fz_bez((X(4.0), 18.8), (X(8.8), 20.6), (X(9.6), 25.4)), 1.6, 0.6)                 # cheek line
    _fz_taper(dr, [(17.0, 10.0), (18.5, 14.0)], 1.2, 0.4); _fz_taper(dr, [(23.0, 10.0), (21.5, 14.0)], 1.2, 0.4)   # furrow
    dr.ellipse([16.5 * S, 20.6 * S, 23.5 * S, 23.2 * S], fill=255)                                           # nose base
    mouth = _fz_bez((11.4, 25.4), (20.0, 23.0), (28.6, 25.4)) + _fz_bez((28.6, 25.4), (26.5, 32.6), (20.0, 32.4))[1:] + _fz_bez((20.0, 32.4), (13.5, 32.6), (11.4, 25.4))[1:]
    dr.polygon([(x * S, y * S) for x, y in mouth], fill=255)                                                 # the wider snarl
    for k in range(6):                                                                                       # jagged fangs (cut out)
        x = 13.3 + k * 2.25
        dr.polygon([(x * S, 25.0 * S), ((x + 1.8) * S, 24.8 * S), ((x + 0.9) * S, 27.6 * S)], fill=0)
        dr.polygon([((x + 0.2) * S, 31.2 * S), ((x + 1.9) * S, 31.2 * S), ((x + 1.0) * S, 28.8 * S)], fill=0)
    _fz_taper(dr, _fz_bez((16.5, 33.6), (20.0, 34.7), (23.5, 33.6)), 0.6, 0.6)                             # chin
    return im


def glyph_sandstorm_v9():
    """Sandstorm v9 (user: v8 almost looks like a shockwave - more curls, polish): stylised gusts - five wind strokes
    sweeping left to right at different heights on gentle waves, each ending in a spiral CURL (alternately curling up
    and down), every stroke a run of sand grains that swell through the stroke and shrink into the curl, plus a few
    loose grains flung off the curls."""
    im = canvas(); rnd = random.Random(3889); dr = ImageDraw.Draw(im)
    def dot(x, y, d):
        if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    strokes = [(1.0, 12.5, 20.0, 1, 4.2), (3.0, 22.0, 24.0, 1, 4.6), (1.0, 31.5, 16.0, 1, 3.4)]
    for x0, y0, L, up, cr in strokes:
        pts = []
        n = int(L / 1.15)
        for k in range(n + 1):                                                                           # the sweep: a gentle wave
            t = k / n; pts.append((x0 + L * t, y0 - 3.2 * math.sin(t * math.pi * 0.5) + 0.8 * math.sin(t * math.pi * 2 + x0) * (1 - t)))
        ex, ey = pts[-1]; ccx, ccy = ex, ey - up * cr                                                     # the curl: a spiral round (ccx, ccy)
        a0 = math.pi / 2 if up > 0 else -math.pi / 2
        for k in range(1, 30):
            t = k / 29.0; a = a0 - up * t * 1.85 * math.pi; r = cr * (1 - 0.68 * t)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
        spacing, acc, last = 1.55, 1e9, None                                                              # grains at an even spacing along the path
        total = len(pts)
        for i, (x, y) in enumerate(pts):
            if last is not None: acc += math.hypot(x - last[0], y - last[1])
            last = (x, y)
            if acc >= spacing:
                acc = 0.0; t = i / (total - 1)
                d = 0.3 + 0.42 * math.sin(math.pi * min(1.0, t * 1.25)) ** 0.7 if t < 0.8 else 0.52 - 0.3 * (t - 0.8) / 0.2
                dot(x + rnd.uniform(-0.12, 0.12), y + rnd.uniform(-0.12, 0.12), max(0.26, d))
        for g in range(2):                                                                                 # grains flung off the curl
            dot(ccx + up * 0 + cr * 1.15 + 1.4 * g, ccy - up * (0.8 + 0.9 * g), 0.34 - 0.06 * g)
    return im


def glyph_frenzy_v10():
    """Frenzied Charge v10 (user: v9 is better - polish it, slight inspiration from Fury and Terror): v9's tribal face
    with a faint Terror-style jagged burst - short irregular spikes radiating from the upper half of the outer
    contours - and Fury's blockier grin: the fangs widened into heavier teeth."""
    im = glyph_frenzy_v9(); dr = ImageDraw.Draw(im); rnd = random.Random(3910)
    for sx in (-1, 1):
        for k in range(3):                                                                                 # Terror-ish burst spikes at the upper corners
            t = 0.02 + k * 0.13
            bx = 20 + sx * (15.0 + 2.0 * math.sin(math.pi * t) - 3.0 * t * t); by = 6.0 + 22.0 * t
            ang = math.radians(-35 + 40 * t + rnd.uniform(-8, 8)); ln = rnd.uniform(1.6, 2.8) * (1.0 - 0.45 * t)
            tx = bx + sx * ln * math.cos(ang); ty = by + ln * math.sin(ang)
            nx, ny = 0.0, 0.85
            dr.polygon([(bx * S, (by - ny) * S), (bx * S, (by + ny) * S), (tx * S, ty * S)], fill=255)
    return im


def glyph_sandstorm_v10():
    """Sandstorm v10 (user: v9 much better - more sand particles, thicker curved wind lines still made of particles):
    v9's three rising gusts, each now a BAND of grains (three staggered rows across the stroke, narrowing to one row
    inside the curl), plus loose grains drifting round the gusts."""
    im = canvas(); rnd = random.Random(3890); dr = ImageDraw.Draw(im)
    def dot(x, y, d):
        if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    strokes = [(1.0, 12.5, 20.0, 1, 4.2), (3.0, 22.0, 24.0, 1, 4.6), (1.0, 31.5, 16.0, 1, 3.4)]
    for x0, y0, L, up, cr in strokes:
        pts = []; n = int(L / 1.15)
        for k in range(n + 1):
            t = k / n; pts.append((x0 + L * t, y0 - 3.2 * math.sin(t * math.pi * 0.5) + 0.8 * math.sin(t * math.pi * 2 + x0) * (1 - t)))
        ex, ey = pts[-1]; ccx, ccy = ex, ey - up * cr
        a0 = math.pi / 2 if up > 0 else -math.pi / 2
        for k in range(1, 30):
            t = k / 29.0; a = a0 - up * t * 1.85 * math.pi; r = cr * (1 - 0.68 * t)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
        # resample the path at even arc length, then lay 2 staggered parallel grain lines (+ a centre line where the band is widest)
        seg = [0.0]
        for k in range(1, len(pts)): seg.append(seg[-1] + math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]))
        Ltot = seg[-1]
        def at(sv):
            k = max(1, min(len(seg) - 1, next((m for m in range(1, len(seg)) if seg[m] >= sv), len(seg) - 1)))
            f = (sv - seg[k - 1]) / max(1e-6, seg[k] - seg[k - 1]); x = pts[k - 1][0] + f * (pts[k][0] - pts[k - 1][0]); y = pts[k - 1][1] + f * (pts[k][1] - pts[k - 1][1])
            tx, ty = pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]; l = math.hypot(tx, ty) or 1
            return x, y, -ty / l, tx / l
        step = 1.3; m = 0
        sv = 0.4
        while sv < Ltot - 0.2:
            t = sv / Ltot; x, y, nx, ny = at(sv)
            width = 1.0 * (min(1.0, t * 5) if t < 0.62 else max(0.0, 1 - (t - 0.62) / 0.3))
            d = 0.36 + 0.12 * math.sin(math.pi * min(1.0, t * 1.2)) - 0.1 * max(0.0, t - 0.75)
            if width > 0.25:
                for side in (-1, 1):
                    xs, ys = x + nx * side * width, y + ny * side * width
                    if side > 0:
                        x2, y2, _, _ = at(min(Ltot, sv + step / 2)); xs, ys = x2 + nx * width, y2 + ny * width
                    dot(xs + rnd.uniform(-0.1, 0.1), ys + rnd.uniform(-0.1, 0.1), d)
                if width > 0.8 and m % 2 == 0: dot(x, y, d * 0.75)
            else:
                dot(x, y, d)
            sv += step; m += 1
    for g in range(12):                                                                                    # loose drifting grains
        x = rnd.uniform(2, 38); y = rnd.uniform(2, 33); dot(x, y, rnd.choice((0.28, 0.32, 0.38)))
    return im


def glyph_frenzy_v11():
    """Frenzied Charge v11 (user: simplify, THICKER line weights - it still looks too different from vanilla icons):
    the same snarling tribal face reduced to a few heavy shapes in the vanilla manner - thick jaw strokes, a heavy V
    brow, solid glaring eyes with a clear pupil, thick flared nostrils and a big snarl with chunky teeth cut out;
    the thin cheek / chin / lid lines and the burst spikes are gone."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        _fz_taper(dr, _fz_bez((X(15.2), 7.0), (X(17.2), 18.0), (X(11.6), 29.8)), 1.4, 3.4)              # thick jaw strokes
        _fz_taper(dr, _fz_bez((X(11.8), 29.8), (X(8.5), 33.0), (X(3.0), 33.8)), 3.2, 1.2)
        _fz_taper(dr, _fz_bez((X(0.6), 13.4), (X(6.0), 8.4), (X(14.4), 8.0)), 4.6, 1.6)                  # heavy V brow
        eye = _fz_bez((X(3.0), 14.6), (X(7.5), 12.6), (X(12.2), 13.2)) + _fz_bez((X(12.2), 13.2), (X(8.0), 18.4), (X(3.0), 14.6))[1:]
        dr.polygon([(x * S, y * S) for x, y in eye], fill=255)                                             # solid glaring eye
        dr.ellipse([(X(7.6) - 1.0) * S, 13.6 * S, (X(7.6) + 1.0) * S, 15.6 * S], fill=0)                 # clear pupil
    _fz_taper(dr, [(18.0, 9.6), (19.2, 14.4)], 2.0, 0.6); _fz_taper(dr, [(22.0, 9.6), (20.8, 14.4)], 2.0, 0.6)   # furrow
    dr.polygon([(19.4 * S, 14.8 * S), (20.6 * S, 14.8 * S), (23.6 * S, 21.4 * S), (22.6 * S, 22.8 * S), (17.4 * S, 22.8 * S), (16.4 * S, 21.4 * S)], fill=255)   # nose: narrow bridge flaring out
    dr.polygon([(17.6 * S, 22.8 * S), (18.8 * S, 21.6 * S), (19.4 * S, 22.8 * S)], fill=0); dr.polygon([(20.6 * S, 22.8 * S), (21.2 * S, 21.6 * S), (22.4 * S, 22.8 * S)], fill=0)   # nostril notches
    mouth = _fz_bez((10.6, 25.4), (20.0, 22.6), (29.4, 25.4)) + _fz_bez((29.4, 25.4), (27.0, 33.0), (20.0, 32.8))[1:] + _fz_bez((20.0, 32.8), (13.0, 33.0), (10.6, 25.4))[1:]
    dr.polygon([(x * S, y * S) for x, y in mouth], fill=255)                                                 # big snarl
    for k in range(5):                                                                                       # chunky teeth (cut out)
        x = 13.4 + k * 2.75
        dr.polygon([(x * S, 25.0 * S), ((x + 2.2) * S, 24.8 * S), ((x + 1.8) * S, 27.6 * S), ((x + 0.4) * S, 27.6 * S)], fill=0)
        dr.polygon([((x + 0.4) * S, 31.2 * S), ((x + 1.9) * S, 31.2 * S), ((x + 2.2) * S, 29.0 * S), ((x + 0.1) * S, 29.0 * S)], fill=0)
    return im


def _sand_band(dot, pts, rnd, wmax=1.0, step=1.3, taper_in=0.12, taper_out=0.3):
    """Lay a band of sand grains along polyline pts: 2 staggered parallel grain lines + a centre line where widest,
    swelling in over the first taper_in and narrowing to one line over the last taper_out of the length."""
    seg = [0.0]
    for k in range(1, len(pts)): seg.append(seg[-1] + math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]))
    Ltot = seg[-1]
    def at(sv):
        k = next((m for m in range(1, len(seg)) if seg[m] >= sv), len(seg) - 1)
        f = (sv - seg[k - 1]) / max(1e-6, seg[k] - seg[k - 1])
        x = pts[k - 1][0] + f * (pts[k][0] - pts[k - 1][0]); y = pts[k - 1][1] + f * (pts[k][1] - pts[k - 1][1])
        tx, ty = pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]; l = math.hypot(tx, ty) or 1
        return x, y, -ty / l, tx / l
    sv, m = 0.3, 0
    while sv < Ltot - 0.2:
        t = sv / Ltot; x, y, nx, ny = at(sv)
        width = wmax * (min(1.0, t / taper_in) if t < 1 - taper_out else max(0.0, (1 - t) / taper_out))
        d = 0.34 + 0.12 * math.sin(math.pi * t)
        if width > 0.25:
            dot(x - nx * width + rnd.uniform(-0.1, 0.1), y - ny * width + rnd.uniform(-0.1, 0.1), d)
            x2, y2, nx2, ny2 = at(min(Ltot, sv + step / 2))
            dot(x2 + nx2 * width + rnd.uniform(-0.1, 0.1), y2 + ny2 * width + rnd.uniform(-0.1, 0.1), d)
            if width > 0.8 and m % 2 == 0: dot(x, y, d * 0.75)
        else:
            dot(x, y, d * 0.9)
        sv += step; m += 1


def glyph_sandstorm_v11():
    """Sandstorm v11 (user: instead of the sideways J, an UPRIGHT HORSESHOE shape): two nested U-shaped bands of sand
    grains (open at the top, like an upright horseshoe) whose upper ends flick outward in small curls, with loose
    grains blowing about - the swirling sand of the earlier gusts bent into a horseshoe."""
    im = canvas(); rnd = random.Random(3891); dr = ImageDraw.Draw(im)
    def dot(x, y, d):
        if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    def horseshoe(cx, rx, ry, top, cur, turns):
        cy = 32.0 - ry; pts = []
        n = 18
        for k in range(n, 0, -1):                                                                          # left curl (spiral end first), outward over the top to the left
            t = k / n; a = -turns * math.pi * t; r = cur * (1 - 0.6 * t)
            pts.append((cx - rx - cur + r * math.cos(a), top + r * math.sin(a)))
        for k in range(0, 9): pts.append((cx - rx, top + (cy - top) * k / 8.0))                           # left arm down
        for k in range(1, 25):
            a = math.pi - math.pi * k / 24.0; pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))  # the bottom of the U
        for k in range(1, 9): pts.append((cx + rx, cy - (cy - top) * k / 8.0))                           # right arm up
        for k in range(1, n + 1):                                                                          # right curl, outward over the top to the right
            t = k / n; a = math.pi + turns * math.pi * t; r = cur * (1 - 0.6 * t)
            pts.append((cx + rx + cur + r * math.cos(a), top + r * math.sin(a)))
        return pts
    _sand_band(dot, horseshoe(20.0, 11.5, 11.5, 9.0, 4.0, 1.6), rnd, wmax=1.35, taper_in=0.16, taper_out=0.16)
    for g in range(12):
        x = rnd.uniform(2, 38); y = rnd.uniform(2, 33); dot(x, y, rnd.choice((0.28, 0.32, 0.38)))
    return im


def glyph_frenzy_v12():
    """Frenzied Charge v12 (user: remove the sides of the face - only the facial features - and polish them): no face
    outline; the features alone, scaled up to fill the icon in heavy vanilla-style shapes: a deep V brow with points
    flaring up at the outer ends, solid glaring eyes tucked under it with clear pupils, twin furrow wedges, a bold
    flared nose, and a wide snarl with chunky teeth and short creases at the corners."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        brow = [(X(0.8), 12.8), (X(7.0), 7.6), (X(14.0), 5.4), (X(19.0), 2.4), (X(17.6), 6.6), (X(13.0), 9.4), (X(7.0), 11.6), (X(1.4), 15.6)]
        dr.polygon([(x * S, y * S) for x, y in brow], fill=255)                                            # heavy V brow, outer point flaring up
        eye = _fz_bez((X(2.6), 14.8), (X(8.5), 11.8), (X(15.0), 11.0)) + _fz_bez((X(15.0), 11.0), (X(10.5), 19.0), (X(2.6), 14.8))[1:]
        dr.polygon([(x * S, y * S) for x, y in eye], fill=255)                                             # solid glaring eye
        dr.ellipse([(X(8.8) - 1.2) * S, 12.9 * S, (X(8.8) + 1.2) * S, 15.3 * S], fill=0)                 # clear pupil
    _fz_taper(dr, [(17.6, 9.0), (19.0, 14.4)], 2.2, 0.6); _fz_taper(dr, [(22.4, 9.0), (21.0, 14.4)], 2.2, 0.6)   # furrow wedges
    dr.polygon([(19.2 * S, 14.4 * S), (20.8 * S, 14.4 * S), (24.6 * S, 21.4 * S), (23.4 * S, 23.0 * S), (16.6 * S, 23.0 * S), (15.4 * S, 21.4 * S)], fill=255)   # bold flared nose
    dr.polygon([(17.2 * S, 23.0 * S), (18.6 * S, 21.4 * S), (19.4 * S, 23.0 * S)], fill=0); dr.polygon([(20.6 * S, 23.0 * S), (21.4 * S, 21.4 * S), (22.8 * S, 23.0 * S)], fill=0)
    mouth = _fz_bez((9.0, 25.6), (20.0, 22.6), (31.0, 25.6)) + _fz_bez((31.0, 25.6), (28.0, 34.4), (20.0, 34.2))[1:] + _fz_bez((20.0, 34.2), (12.0, 34.4), (9.0, 25.6))[1:]
    dr.polygon([(x * S, y * S) for x, y in mouth], fill=255)                                                 # wide snarl
    for k in range(6):                                                                                       # chunky teeth (cut out)
        x = 11.9 + k * 2.75
        dr.polygon([(x * S, 25.0 * S), ((x + 2.2) * S, 24.8 * S), ((x + 1.8) * S, 28.0 * S), ((x + 0.4) * S, 28.0 * S)], fill=0)
        dr.polygon([((x + 0.4) * S, 32.4 * S), ((x + 1.9) * S, 32.4 * S), ((x + 2.2) * S, 29.6 * S), ((x + 0.1) * S, 29.6 * S)], fill=0)
    return im


def _gust(p0, p1, p2, side, cur, turns=1.5, n=26):
    """A wind gust: quadratic bezier p0 -> p2 (control p1) with a slight turbulent wobble, ending in a spiral curl of
    radius cur turning to `side` (+1 / -1) of the travel direction."""
    pts = []
    for k in range(n + 1):
        t = k / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0]); dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
        l = math.hypot(dx, dy) or 1; w = 0.55 * math.sin(t * math.pi * 3.0) * math.sin(t * math.pi)
        pts.append((x - dy / l * w, y + dx / l * w))
    ex, ey = pts[-1]; tx, ty = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]; l = math.hypot(tx, ty) or 1; tx, ty = tx / l, ty / l
    nx, ny = -ty * side, tx * side                                                                         # toward the curl centre
    ccx, ccy = ex + nx * cur, ey + ny * cur; a0 = math.atan2(ey - ccy, ex - ccx)
    for k in range(1, 22):
        t = k / 21.0; a = a0 + side * turns * math.pi * t; r = cur * (1 - 0.62 * t)
        pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def glyph_sandstorm_v12():
    """Sandstorm v12 (user: only VAGUELY a horseshoe, and still 3 main lines - turbulent wind / debris): three wavy gust
    bands of sand grains that together trace a loose upright horseshoe - one sweeping down the left, one swinging
    across the bottom, one rising up the right - each ending in a curl, with debris grains and a few bigger grit
    chunks flung around them."""
    im = canvas(); rnd = random.Random(3892); dr = ImageDraw.Draw(im)
    def dot(x, y, d):
        if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    _sand_band(dot, _gust((4.0, 4.0), (1.5, 18.0), (11.0, 22.0), -1, 3.4), rnd, wmax=1.15, taper_in=0.12, taper_out=0.3)
    _sand_band(dot, _gust((6.0, 29.0), (19.0, 36.0), (27.5, 27.0), -1, 3.2), rnd, wmax=1.15, taper_in=0.12, taper_out=0.3)
    _sand_band(dot, _gust((33.0, 30.5), (38.5, 17.0), (31.0, 6.5), -1, 3.4), rnd, wmax=1.15, taper_in=0.12, taper_out=0.3)
    for g in range(22):                                                                                    # debris
        x = rnd.uniform(2, 38); y = rnd.uniform(2, 33); dot(x, y, rnd.choice((0.28, 0.32, 0.38, 0.38, 0.6)))
    return im


def glyph_frenzy_v13():
    """Frenzied Charge v13 (user: v12's eyebrows look wacky; it should be YELLING / SCREAMING, in a frenzy): features
    only, heavy shapes - thick angry brows (a natural wedge, low at the centre, no flared points), wide crazed eyes
    with pinpoint pupils, furrow wedges, a flared nose, and a tall wide-open screaming mouth with fangs top and bottom."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        brow = _fz_bez((X(1.6), 11.4), (X(8.0), 5.6), (X(15.4), 6.8)) + _fz_bez((X(15.4), 6.8), (X(8.6), 8.6), (X(1.8), 14.4))[1:]
        dr.polygon([(x * S, y * S) for x, y in brow], fill=255)                                            # thick angry brow
        eye = _fz_bez((X(3.4), 13.8), (X(9.0), 9.6), (X(14.4), 11.6)) + _fz_bez((X(14.4), 11.6), (X(10.4), 18.6), (X(3.4), 13.8))[1:]
        dr.polygon([(x * S, y * S) for x, y in eye], fill=255)                                             # wide crazed eye
        dr.ellipse([(X(9.2) - 0.9) * S, 12.6 * S, (X(9.2) + 0.9) * S, 14.4 * S], fill=0)                 # pinpoint pupil
    dr.polygon([(19.3 * S, 13.6 * S), (20.7 * S, 13.6 * S), (23.6 * S, 18.6 * S), (22.6 * S, 19.8 * S), (17.4 * S, 19.8 * S), (16.4 * S, 18.6 * S)], fill=255)   # flared nose
    dr.polygon([(17.6 * S, 19.8 * S), (18.8 * S, 18.6 * S), (19.4 * S, 19.8 * S)], fill=0); dr.polygon([(20.6 * S, 19.8 * S), (21.2 * S, 18.6 * S), (22.4 * S, 19.8 * S)], fill=0)
    mouth = _fz_bez((10.4, 23.0), (20.0, 19.8), (29.6, 23.0)) + _fz_bez((29.6, 23.0), (29.6, 33.6), (20.0, 33.6))[1:] + _fz_bez((20.0, 33.6), (10.4, 33.6), (10.4, 23.0))[1:]
    dr.polygon([(x * S, y * S) for x, y in mouth], fill=255)                                                 # the screaming mouth
    for k in range(5):                                                                                       # upper fangs (cut out), pointing down
        x = 12.2 + k * 3.15; L = 4.4 if k in (0, 4) else 3.2
        dr.polygon([(x * S, 22.6 * S), ((x + 2.8) * S, 22.0 * S), ((x + 1.4) * S, (22.4 + L) * S)], fill=0)
    for k in range(4):                                                                                       # lower fangs, pointing up
        x = 13.4 + k * 3.45; L = 3.8 if k in (0, 3) else 2.8
        dr.polygon([(x * S, 32.4 * S), ((x + 2.6) * S, 32.4 * S), ((x + 1.3) * S, (32.4 - L) * S)], fill=0)
    return im


def glyph_sandstorm_v13():
    """Sandstorm v13 (user: rework - TURBULENT WIND SWIRLS with sand particles): solid tapered wind strokes in the
    vanilla wind-icon manner (Winds of Fury's arcs) curling into three swirls - a big spiral left of centre, two smaller
    curls top-right and bottom-right, joined by the flowing lines - with sand grains streaming along beside the
    strokes and scattered through the gaps."""
    im = canvas(); rnd = random.Random(3893); dr = ImageDraw.Draw(im)
    def dot(x, y, d):
        if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    def spiral(cx, cy, r0, r1, a0, turns, side, n=40):
        return [(cx + (r0 + (r1 - r0) * k / n) * math.cos(a0 + side * turns * 2 * math.pi * k / n),
                 cy + (r0 + (r1 - r0) * k / n) * 0.9 * math.sin(a0 + side * turns * 2 * math.pi * k / n)) for k in range(n + 1)]
    strokes = [
        (spiral(14.0, 17.0, 12.5, 2.2, math.radians(200), 1.15, 1), 2.6, 0.7),        # the big swirl (outer end thick, winding in)
        (spiral(30.0, 8.0, 7.5, 1.6, math.radians(150), 0.95, -1), 2.0, 0.6),         # top-right curl
        (spiral(30.5, 26.0, 7.0, 1.5, math.radians(210), 0.95, 1), 2.0, 0.6),         # bottom-right curl
    ]
    for pts, w0, w1 in strokes:
        _fz_taper(dr, pts, w0, w1)
    flow = []                                                                                              # sand streaming beside the strokes
    for pts, w0, w1 in strokes:
        for k in range(2, len(pts) - 2, 2):
            x, y = pts[k]; tx, ty = pts[k + 1][0] - pts[k - 1][0], pts[k + 1][1] - pts[k - 1][1]; l = math.hypot(tx, ty) or 1
            off = (w0 + (w1 - w0) * k / len(pts)) / 2 + rnd.uniform(1.0, 2.2)
            side = rnd.choice((-1, 1))
            if rnd.random() < 0.6: flow.append((x - ty / l * off * side, y + tx / l * off * side))
    for x, y in flow: dot(x + rnd.uniform(-0.3, 0.3), y + rnd.uniform(-0.3, 0.3), rnd.choice((0.3, 0.36, 0.42)))
    for g in range(18): dot(rnd.uniform(1.5, 38.5), rnd.uniform(1.5, 33.5), rnd.choice((0.3, 0.36, 0.45)))
    return im


def glyph_frenzy_v14():
    """Frenzied Charge v14 (user: inspiration from 'The Desperate Man' - Courbet's self-portrait: a wild-eyed man
    clutching his head, fingers in his hair): a bold vanilla-style SILHOUETTE - solid head and neck with the features
    cut out (wide staring eyes with dark pupils, worried raised brows, an open anguished mouth), a mop of wild hair
    tufts, and both hands raised to the temples gripping the hair, forearms running down to the bottom corners."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    P = lambda pts: [(x * S, y * S) for x, y in pts]
    rnd = random.Random(3914)
    for k in range(13):                                                                                    # wild hair tufts
        a = math.radians(-168 + k * 13 + rnd.uniform(-4, 4)); r1 = rnd.uniform(11.5, 14.0)
        b0 = (20 + 8.6 * math.cos(a - 0.2), 17.5 + 9.6 * math.sin(a - 0.2)); b1 = (20 + 8.6 * math.cos(a + 0.2), 17.5 + 9.6 * math.sin(a + 0.2))
        tip = (20 + r1 * math.cos(a + rnd.uniform(-0.15, 0.15)), 17.5 + (r1 + 0.5) * math.sin(a))
        if tip[1] < 15: dr.polygon(P([b0, b1, (max(0.5, tip[0]), max(0.5, tip[1]))]), fill=255)
    dr.ellipse([12.0 * S, 7.6 * S, 28.0 * S, 28.6 * S], fill=255)                                           # the head
    dr.polygon(P([(16.6, 26.0), (23.4, 26.0), (24.4, 35.0), (15.6, 35.0)]), fill=255)                      # neck
    for sx in (-1, 1):
        X = lambda x: 20 + sx * x
        arm = [(X(10.6), 15.2), (X(12.6), 16.2), (X(16.4), 35.0), (X(13.2), 35.0)]
        hand = [(X(7.0), 12.6), (X(9.4), 8.8), (X(12.4), 9.6), (X(13.8), 14.4), (X(12.4), 17.6), (X(9.6), 17.0)]
        dr.polygon(P(arm), fill=0); dr.polygon(P(hand), fill=0)                                            # a thin gap round arm + hand
        dr.polygon(P([(x + sx * 0.9, y) for x, y in arm]), fill=255)
        dr.polygon(P(hand), fill=255)
        for f in range(4):                                                                                 # fingers gripping into the hair
            fx = X(7.6 + f * 1.45); dr.line(P([(fx, 10.4), (fx - sx * 0.4, 6.6 + f * 0.5)]), fill=255, width=int(1.3 * S))
    for sx in (-1, 1):                                                                                     # features cut out
        X = lambda x: 20 + sx * x
        dr.ellipse([(X(3.6) - 2.5) * S, 14.4 * S, (X(3.6) + 2.5) * S, 18.8 * S], fill=0)                   # wide staring eye
        dr.ellipse([(X(3.6) - 0.9) * S, 15.7 * S, (X(3.6) + 0.9) * S, 17.5 * S], fill=255)                 # dark pupil
        dr.line(P([(X(1.4), 12.4), (X(5.8), 13.4)]), fill=0, width=int(1.1 * S))                         # worried brow, raised inside
    dr.ellipse([17.4 * S, 21.6 * S, 22.6 * S, 26.4 * S], fill=0)                                             # the open, anguished mouth
    return im


def glyph_frenzy_v15():
    """Frenzied Charge v15 (user's new reference art import export/frenzy.jpg: a screaming man in bold black-and-white
    ink - eyes squeezed shut, knotted brow, wild spiky hair, a huge open mouth with teeth top and bottom): a dark
    spiky hair mass framing a clear face; on it a heavy knotted brow, eyes squeezed shut into thick angled slashes,
    a dark nose, deep creases from the nose down round the mouth, and a huge dark screaming mouth with clear rows of
    teeth along the top and bottom."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im); rnd = random.Random(3915)
    P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx, cy = 20.0, 19.0
    dr.ellipse([(cx - 13.0) * S, (cy - 15.0) * S, (cx + 13.0) * S, (cy + 11.0) * S], fill=255)               # hair mass
    for k in range(13):                                                                                     # spikes flaring out of it (top + upper sides)
        a = math.radians(-178 + k * 14.5 + rnd.uniform(-5, 5)); r0 = 11.5; r1 = rnd.uniform(15.0, 19.5)
        p0 = (cx + r0 * math.cos(a - 0.17), cy - 2 + r0 * math.sin(a - 0.17)); p1 = (cx + r0 * math.cos(a + 0.17), cy - 2 + r0 * math.sin(a + 0.17))
        tip = (cx + r1 * math.cos(a + rnd.uniform(-0.12, 0.12)), cy - 2 + r1 * math.sin(a) * 0.95)
        if tip[1] < cy + 6: dr.polygon(P([p0, p1, tip]), fill=255)
    face = _fz_bez((cx - 9.6, 10.0), (cx, 4.4), (cx + 9.6, 10.0)) + _fz_bez((cx + 9.6, 10.0), (cx + 11.6, 30.0), (cx, 35.4))[1:] + _fz_bez((cx, 35.4), (cx - 11.6, 30.0), (cx - 9.6, 10.0))[1:]
    dr.polygon(P(face), fill=0)                                                                              # the clear face
    for sx in (-1, 1):
        X = lambda x: cx + sx * x
        dr.polygon(P([(X(0.6), 13.2), (X(3.0), 9.4), (X(8.8), 9.0), (X(9.4), 10.6), (X(3.6), 12.0), (X(1.2), 15.4)]), fill=255)   # knotted brow
        dr.polygon(P([(X(2.0), 16.6), (X(8.6), 14.0), (X(9.0), 15.4), (X(2.8), 18.0)]), fill=255)       # eye squeezed shut
        _fz_taper(dr, _fz_bez((X(2.6), 19.4), (X(6.4), 20.6), (X(7.4), 26.0)), 1.8, 0.6)                 # crease nose -> round the mouth
    _fz_taper(dr, [(cx - 0.6, 9.0), (cx - 0.3, 13.6)], 1.4, 0.4); _fz_taper(dr, [(cx + 0.8, 9.6), (cx + 0.4, 13.2)], 1.0, 0.4)   # furrow
    dr.polygon(P([(cx - 0.8, 16.4), (cx + 0.8, 16.4), (cx + 2.8, 19.8), (cx + 1.4, 20.6), (cx - 1.4, 20.6), (cx - 2.8, 19.8)]), fill=255)   # dark nose
    mouth = _fz_bez((cx - 6.2, 23.0), (cx, 19.8), (cx + 6.2, 23.0)) + _fz_bez((cx + 6.2, 23.0), (cx + 6.4, 34.0), (cx, 34.4))[1:] + _fz_bez((cx, 34.4), (cx - 6.4, 34.0), (cx - 6.2, 23.0))[1:]
    dr.polygon(P(mouth), fill=255)                                                                           # the huge screaming mouth
    for k in range(5):                                                                                       # upper teeth (clear)
        x = cx - 5.0 + k * 2.05
        dr.polygon(P([(x, 22.4 - 0.5 * math.cos((k - 2) * 0.5)), (x + 1.75, 22.4 - 0.5 * math.cos((k - 2) * 0.5)), (x + 1.55, 24.8), (x + 0.2, 24.8)]), fill=0)
    for k in range(4):                                                                                       # lower teeth
        x = cx - 4.0 + k * 2.05
        dr.polygon(P([(x + 0.2, 31.2), (x + 1.55, 31.2), (x + 1.75, 33.4), (x, 33.4)]), fill=0)
    return im


def glyph_sandstorm_v14():
    """Sandstorm v14 (user: shape inspired by the Carolina Hurricanes logo - the hurricane-warning swirl - still made of
    sand particles): the hurricane symbol - an eye ring at the centre and two broad comma arms spiralling out of it
    (180 deg apart, each sweeping ~200 deg and tapering to a point) - every shape STIPPLED with sand grains on a jittered
    grid, plus loose grains flung off the arm tips."""
    im = canvas(); rnd = random.Random(3894); dr = ImageDraw.Draw(im)
    cx, cy = 20.0, 17.5
    mask = Image.new("L", (W * S, H * S), 0); md = ImageDraw.Draw(mask)
    for arm in range(2):                                                                                   # the two arms
        a0 = math.radians(-60 + 180 * arm); outer, inner = [], []
        for k in range(41):
            t = k / 40.0; a = a0 + math.radians(200) * t
            rm = 5.2 + 11.0 * t ** 0.9; wd = 7.2 * (1 - t) ** 0.6 + 0.3
            outer.append((cx + (rm + wd / 2) * math.cos(a), cy + (rm + wd / 2) * 0.92 * math.sin(a)))
            inner.append((cx + (rm - wd / 2) * math.cos(a), cy + (rm - wd / 2) * 0.92 * math.sin(a)))
        md.polygon([(x * S, y * S) for x, y in outer + inner[::-1]], fill=255)
    md.ellipse([(cx - 5.4) * S, (cy - 5.0) * S, (cx + 5.4) * S, (cy + 5.0) * S], fill=255)                    # eye wall
    md.ellipse([(cx - 2.3) * S, (cy - 2.1) * S, (cx + 2.3) * S, (cy + 2.1) * S], fill=0)                      # the clear eye
    mp = mask.load(); step = 1.18
    y = 0.6
    row = 0
    while y < H:                                                                                           # stipple the mask with grains
        x = 0.6 + (step / 2 if row % 2 else 0)
        while x < W:
            jx, jy = x + rnd.uniform(-0.28, 0.28), y + rnd.uniform(-0.28, 0.28)
            if 0 <= jx < W and 0 <= jy < H and mp[int(jx * S), int(jy * S)]:
                d = rnd.choice((0.36, 0.42, 0.46))
                dr.ellipse([(jx - d) * S, (jy - d) * S, (jx + d) * S, (jy + d) * S], fill=255)
            x += step
        y += step * 0.88; row += 1
    for arm in range(2):                                                                                   # grains flung off the tips
        a = math.radians(-60 + 180 * arm + 200)
        for g in range(5):
            r = 17.5 + 1.2 * g + rnd.uniform(-0.5, 0.5); aa = a + math.radians(8 * g + rnd.uniform(-6, 6))
            x, y = cx + r * math.cos(aa), cy + r * 0.92 * math.sin(aa); d = 0.42 - 0.04 * g
            if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    return im


def glyph_sandstorm():
    """Sandstorm v15 (user: v14 not bad, but SPLIT the connected 'S', THINNER, MORE lines): five separate thin spiral
    arms whirling round a clear eye (hurricane rotation, none touching the centre or each other), each a slim tapering
    crescent stippled with sand grains, plus grains flung off the arm tips."""
    im = canvas(); rnd = random.Random(3895); dr = ImageDraw.Draw(im)
    cx, cy = 20.0, 17.5; N = 5
    mask = Image.new("L", (W * S, H * S), 0); md = ImageDraw.Draw(mask)
    tips = []
    for arm in range(N):
        a0 = math.radians(arm * 360.0 / N + rnd.uniform(-6, 6)); sweep = math.radians(rnd.uniform(105, 125))
        r0 = 4.6 + rnd.uniform(-0.4, 0.4); r1 = 15.6 + rnd.uniform(-0.8, 0.8); outer, inner = [], []
        for k in range(31):
            t = k / 30.0; a = a0 + sweep * t
            rm = r0 + (r1 - r0) * t ** 0.85; wd = 3.0 * math.sin(math.pi * min(1.0, 0.15 + t * 0.95)) ** 0.7 + 0.15
            outer.append((cx + (rm + wd / 2) * math.cos(a), cy + (rm + wd / 2) * 0.9 * math.sin(a)))
            inner.append((cx + (rm - wd / 2) * math.cos(a), cy + (rm - wd / 2) * 0.9 * math.sin(a)))
        md.polygon([(x * S, y * S) for x, y in outer + inner[::-1]], fill=255)
        tips.append((a0 + sweep, r1))
    mp = mask.load(); step = 1.05; y = 0.5; row = 0
    while y < H:
        x = 0.5 + (step / 2 if row % 2 else 0)
        while x < W:
            jx, jy = x + rnd.uniform(-0.22, 0.22), y + rnd.uniform(-0.22, 0.22)
            if 0 <= jx < W and 0 <= jy < H and mp[int(jx * S), int(jy * S)]:
                d = rnd.choice((0.34, 0.38, 0.42))
                dr.ellipse([(jx - d) * S, (jy - d) * S, (jx + d) * S, (jy + d) * S], fill=255)
            x += step
        y += step * 0.88; row += 1
    for a, r in tips:                                                                                      # grains flung off the tips
        for g in range(3):
            aa = a + math.radians(7 * (g + 1) + rnd.uniform(-4, 4)); rr = r + 1.0 * (g + 1)
            x, y = cx + rr * math.cos(aa), cy + rr * 0.9 * math.sin(aa); d = 0.38 - 0.05 * g
            if 0.4 <= x < W - 0.4 and 0.4 <= y < H - 0.4: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    return im


def glyph_implosion_v3():
    """Implosion v3 (user: a new icon that looks like the vacuum circle with an orb in the middle): a solid orb at
    the centre (a clear highlight crescent and a thin clear gap ring round it), a ring of 16 particles rushing inward -
    each a dot with a tapered streak trailing outward behind it - and a smaller inner ring of 8 particles closing on
    the orb, offset between them."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 17.5
    def disc(x, y, r, fill=255): dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)
    for rr, nk, dsz, tail in ((12.8, 14, 0.95, 0.5), (8.8, 9, 0.72, 0.45)):                              # two spinning rings sucked inward
        for k in range(nk):
            a = 2 * math.pi * k / nk + (0.2 if rr < 10 else 0.0)
            pts = []
            for m in range(10, -1, -1):                                                                        # tail: back along a widening spiral
                t = m / 10.0; aa = a - tail * t; r = rr + 3.0 * t
                pts.append((cx + r * math.cos(aa), cy + r * math.sin(aa) * 0.92))
            _fz_taper(dr, pts, 0.12, dsz * 1.1)
            disc(cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.92, dsz)
    disc(cx, cy, 5.6)                                                                                      # the orb
    dr.ellipse([(cx - 5.6) * S, (cy - 5.6) * S, (cx + 5.6) * S, (cy + 5.6) * S], outline=0, width=int(0.7 * S))   # thin clear gap ring
    disc(cx, cy, 4.6)
    dr.ellipse([(cx - 3.2) * S, (cy - 3.4) * S, (cx - 0.6) * S, (cy - 1.4) * S], fill=0)                     # highlight
    return im


def glyph_implosion_v4():
    """Implosion v4 (user: the ring should be ELLIPTICAL / 3D like the GFX circle, the orb HOLLOW): the in-game ring -
    18 comet motes on a flattened ellipse (y 0.42, the battlefield angle) orbiting with short tails along the ellipse -
    in perspective: the back half smaller and drawn first, then a HOLLOW orb (thick outline ring, small highlight),
    then the front half larger and over it; a second, smaller inner ring hints at the contraction."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 18.0
    def ring(rx, ry, n, dmin, dmax, front, phase):
        for k in range(n):
            a = 2 * math.pi * k / n + phase; sa = math.sin(a)
            if (sa > 0) != front: continue
            depth = 0.5 + 0.5 * sa                                                                         # 0 = back, 1 = front
            d = dmin + (dmax - dmin) * depth
            pts = []
            for m in range(8, -1, -1):                                                                      # tail trailing back along the ellipse
                t = m / 8.0; aa = a - 0.42 * t
                pts.append((cx + rx * math.cos(aa), cy + ry * math.sin(aa)))
            _fz_taper(dr, pts, 0.12, d * 1.3)
            x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
            dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    ring(17.6, 8.0, 18, 0.5, 1.3, False, 0.0)                                                           # outer ring, back half
    ring(11.4, 5.2, 12, 0.4, 0.9, False, 0.13)                                                           # inner ring, back half
    R = 7.6; oy = cy - 3.0                                                                                  # the hollow orb
    dr.ellipse([(cx - R - 0.8) * S, (oy - R - 0.8) * S, (cx + R + 0.8) * S, (oy + R + 0.8) * S], fill=0)   # clear margin so the back ring stops at it
    dr.ellipse([(cx - R) * S, (oy - R) * S, (cx + R) * S, (oy + R) * S], outline=255, width=int(2.0 * S))
    dr.ellipse([(cx - 4.4) * S, (oy - 4.8) * S, (cx - 1.8) * S, (oy - 2.4) * S], fill=255)                # highlight
    ring(11.4, 5.2, 12, 0.4, 0.9, True, 0.13)                                                            # inner ring, front half
    ring(17.6, 8.0, 18, 0.5, 1.3, True, 0.0)                                                            # outer ring, front half
    return im


def glyph_implosion_v5():
    """Implosion v5 (user: change the orb to an explosion / MUSHROOM CLOUD): v4's 3D ring of comet motes now circles
    the stem of a mushroom cloud like a shockwave - a billowing cap (overlapping puffs with clear crescent folds), a
    tapering stem with a collar ring, and a low ground cloud at its foot; the ring's back half behind, front half over."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 22.5
    def disc(x, y, r, fill=255): dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)
    def ring(rx, ry, n, dmin, dmax, front, phase):
        for k in range(n):
            a = 2 * math.pi * k / n + phase; sa = math.sin(a)
            if (sa > 0) != front: continue
            d = dmin + (dmax - dmin) * (0.5 + 0.5 * sa)
            pts = [(cx + rx * math.cos(a - 0.42 * m / 8.0), cy + ry * math.sin(a - 0.42 * m / 8.0)) for m in range(8, -1, -1)]
            _fz_taper(dr, pts, 0.12, d * 1.3)
            disc(cx + rx * math.cos(a), cy + ry * math.sin(a), d)
    ring(17.6, 7.4, 18, 0.5, 1.3, False, 0.0)                                                             # back half of the ring
    for x, y, r in ((20.0, 26.6, 3.2), (16.6, 27.4, 2.6), (23.4, 27.4, 2.6), (13.6, 28.4, 1.8), (26.4, 28.4, 1.8)):
        disc(x, y, r + 0.7, 0)
    for x, y, r in ((20.0, 26.6, 3.2), (16.6, 27.4, 2.6), (23.4, 27.4, 2.6), (13.6, 28.4, 1.8), (26.4, 28.4, 1.8)):
        disc(x, y, r)                                                                                          # ground cloud
    stem = [(18.4, 11.6), (21.6, 11.6), (22.6, 18.0), (23.6, 25.4), (16.4, 25.4), (17.4, 18.0)]
    dr.polygon([(x * S, y * S) for x, y in stem], fill=255)                                                    # stem
    dr.ellipse([15.6 * S, 15.6 * S, 24.4 * S, 18.6 * S], fill=255)                                             # collar ring round the stem
    dr.ellipse([16.6 * S, 16.4 * S, 23.4 * S, 17.8 * S], fill=0)
    dr.polygon([(18.6 * S, 16.6 * S), (21.4 * S, 16.6 * S), (21.6 * S, 17.8 * S), (18.4 * S, 17.8 * S)], fill=255)
    puffs = ((20.0, 7.0, 5.0), (14.6, 9.0, 3.6), (25.4, 9.0, 3.6), (11.4, 10.6, 2.4), (28.6, 10.6, 2.4), (17.0, 4.6, 3.0), (23.0, 4.6, 3.0), (20.0, 11.0, 3.4))
    for x, y, r in puffs: disc(x, y, r + 0.6, 0)
    for x, y, r in puffs: disc(x, y, r)                                                                         # the billowing cap
    for x, y, a0, a1 in ((14.6, 9.0, 200, 290), (25.4, 9.0, 250, 340), (20.0, 7.0, 210, 300), (17.0, 4.6, 200, 280)):
        dr.arc([(x - 2.4) * S, (y - 2.4) * S, (x + 2.4) * S, (y + 2.4) * S], a0, a1, fill=0, width=int(0.75 * S))   # clear folds in the cap
    ring(17.6, 7.4, 18, 0.5, 1.3, True, 0.0)                                                              # front half of the ring
    return im


def glyph_frenzy_v20():
    """Frenzied Charge v20 (user: v19 looks weird - refer to the source image art import export/frenzy.jpg, then
    SIMPLIFY it in vanilla icon style): the reference's layout (read off a gridded trace) redrawn as a few bold shapes -
    a spiky dark hair mass over the top and down both sides framing a clear egg-shaped face; a dark brow / squeezed-eye
    band angling down to a narrow clear nose bridge; a dark nose; thick creases from the nostrils down past the mouth;
    a huge dark screaming mouth with clear upper and lower teeth."""
    im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im); rnd = random.Random(3917)
    P = lambda pts: [(x * S, y * S) for x, y in pts]
    hair = []                                                                                               # spiky hair silhouette
    k = 0; t = 0.0
    while t < 1.0:                                                                                           # messy, swept, uneven spikes (not a sunburst)
        a = math.radians(160 + 220 * t)
        if k % 2:
            up = math.radians(-90); sw = 0.45 * math.sin(a - up)                                             # tips swept toward 'up'
            r = 11.8 + rnd.uniform(1.6, 6.0) * (1.25 if 200 < math.degrees(a) < 300 else 0.9); a2 = a - sw
        else:
            r = 11.4 + rnd.uniform(-0.4, 0.8); a2 = a
        hair.append((20.4 + r * math.cos(a2) * 1.05, 16.0 + r * math.sin(a2) * 1.05))
        t += rnd.uniform(0.025, 0.05); k += 1
    hair += [(30.6, 26.0), (27.6, 29.0), (13.2, 29.0), (10.2, 26.0)]
    dr.polygon(P(hair), fill=255)
    face = _fz_bez((11.4, 12.4), (20.4, 3.0), (29.4, 12.4)) + _fz_bez((29.4, 12.4), (30.6, 30.0), (20.4, 35.6))[1:] + _fz_bez((20.4, 35.6), (10.2, 30.0), (11.4, 12.4))[1:]
    dr.polygon(P(face), fill=0)                                                                               # clear face
    for sx in (-1, 1):
        X = lambda x: 20.4 + sx * x
        dr.polygon(P([(X(0.9), 15.8), (X(0.7), 13.2), (X(4.0), 11.8), (X(8.8), 11.6), (X(8.8), 13.0), (X(4.6), 13.8)]), fill=255)   # brow
        dr.polygon(P([(X(2.2), 16.8), (X(7.6), 14.6), (X(8.0), 15.8), (X(3.2), 18.0)]), fill=255)       # squeezed eye
        _fz_taper(dr, _fz_bez((X(3.6), 20.4), (X(6.6), 23.6), (X(7.0), 28.6)), 1.3, 0.5)                 # crease
    dr.polygon(P([(19.4, 16.8), (21.4, 16.8), (23.4, 20.6), (22.2, 21.6), (18.6, 21.6), (17.4, 20.6)]), fill=255)   # nose
    mouth = _fz_bez((15.6, 23.8), (20.4, 21.6), (25.2, 23.8)) + _fz_bez((25.2, 23.8), (25.6, 34.0), (20.4, 34.4))[1:] + _fz_bez((20.4, 34.4), (15.2, 34.0), (15.6, 23.8))[1:]
    dr.polygon(P(mouth), fill=255)                                                                            # screaming mouth
    for k in range(4):                                                                                        # upper teeth (clear)
        x = 16.6 + k * 1.95
        dr.polygon(P([(x, 23.6 - 0.4 * (1 - abs(k - 1.5) / 1.5)), (x + 1.6, 23.6 - 0.4 * (1 - abs(k - 1.5) / 1.5)), (x + 1.4, 25.6), (x + 0.2, 25.6)]), fill=0)
    for k in range(3):                                                                                        # lower teeth
        x = 17.6 + k * 1.95
        dr.polygon(P([(x + 0.2, 31.2), (x + 1.4, 31.2), (x + 1.6, 33.0), (x, 33.0)]), fill=0)
    return im


def glyph_holywater():
    """Holy Water (324) v3 (user: the flask is too round - change its shape): a pilgrim's AMPULLA - a pear-shaped
    flask with a flat base, sloping shoulders, a narrow neck with a collar ring and a pointed stopper - with a bold
    cross on the body centred on the neck axis; drawn upright, tilted 25 degrees as one piece, drops spilling out."""
    big = Image.new("L", (W * S, H * S), 0); d2 = ImageDraw.Draw(big); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx = 20.0
    body = [(cx - 2.2, 11.0), (cx - 4.6, 14.4), (cx - 7.6, 20.0), (cx - 8.6, 25.0), (cx - 8.0, 29.0), (cx - 6.4, 31.6),
            (cx + 6.4, 31.6), (cx + 8.0, 29.0), (cx + 8.6, 25.0), (cx + 7.6, 20.0), (cx + 4.6, 14.4), (cx + 2.2, 11.0)]
    d2.polygon(P(body), fill=255)
    d2.rectangle([(cx - 2.0) * S, 6.4 * S, (cx + 2.0) * S, 11.6 * S], fill=255)                             # neck
    d2.rectangle([(cx - 3.2) * S, 7.0 * S, (cx + 3.2) * S, 8.6 * S], fill=255)                              # collar
    d2.rectangle([(cx - 3.2) * S, 8.5 * S, (cx + 3.2) * S, 9.1 * S], fill=0)
    d2.polygon(P([(cx - 2.4, 6.6), (cx, 1.6), (cx + 2.4, 6.6)]), fill=255)                                   # pointed stopper
    d2.rectangle([(cx - 1.3) * S, 15.6 * S, (cx + 1.3) * S, 28.6 * S], fill=0)                              # the cross on the axis
    d2.rectangle([(cx - 4.6) * S, 19.4 * S, (cx + 4.6) * S, 22.0 * S], fill=0)
    d2.line(P([(cx - 6.6, 22.0), (cx - 6.4, 27.4)]), fill=0, width=int(0.7 * S))                              # a glass highlight cut
    rot = big.rotate(-25, resample=Image.BICUBIC, center=(cx * S, 21.0 * S), translate=(-4 * S, 1 * S))
    im = canvas(); im.paste(rot, (0, 0)); dr = ImageDraw.Draw(im)
    mx, my = (cx - 4) + 17.0 * math.sin(math.radians(25)), 22.0 - 17.0 * math.cos(math.radians(25))     # the mouth after the tilt
    for dx, dy, r in ((4.4, 0.6, 1.9), (8.0, 3.4, 1.6), (5.8, 6.0, 1.4), (11.2, 6.6, 1.2), (9.0, 9.8, 1.0)):
        teardrop(dr, (mx + dx) * S, (my + dy) * S, r * S, tip_up=True)
    return im


def glyph_bountiful():
    """Bountiful Harvest (325) v5 (user: an AoW-stylised version of the Fruit of the Loom logo): a heaped fruit
    cluster - a big apple in front with a stalk and a cut-out highlight, a bunch of grapes behind it to the right,
    a smaller round fruit (a plum) to the left, a cluster of currants peeking out, and broad leaves fanning above -
    every piece black-edged so the shapes stay separate."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    def disc(x, y, r, halo=0.8):
        dr.ellipse([(x - r - halo) * S, (y - r - halo) * S, (x + r + halo) * S, (y + r + halo) * S], fill=0)
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)
    def leaf(x, y, deg, L, W):
        a = math.radians(deg); ux, uy = math.cos(a), -math.sin(a); px, py = -uy, ux
        def sh(wa, la):
            o = []
            for k in range(11):
                t = k / 10.0; w = (W + wa) * math.sin(math.pi * t) ** 0.7; o.append((x + ux * (L + la) * t + px * w, y + uy * (L + la) * t + py * w))
            for k in range(10, -1, -1):
                t = k / 10.0; w = (W + wa) * math.sin(math.pi * t) ** 0.7; o.append((x + ux * (L + la) * t - px * w, y + uy * (L + la) * t - py * w))
            return o
        dr.polygon(P(sh(0.8, 0.8)), fill=0); dr.polygon(P(sh(0, 0)), fill=255)
        dr.line(P([(x + ux * 1.0, y + uy * 1.0), (x + ux * L * 0.85, y + uy * L * 0.85)]), fill=0, width=int(0.5 * S))
    fx, fy, FR = 19.6, 22.0, 15.4                                                                         # v6 (user: lose the leaves - an 'exclamatory' spiky crescent flash)
    for k in range(13):                                                                                   # a crescent of spikes radiating over the cluster
        a = math.radians(30 + k * 10.0); L = 4.6 if k % 2 == 0 else 3.0
        x0, y0 = fx + FR * math.cos(a), fy - FR * math.sin(a); x1, y1 = fx + (FR + L) * math.cos(a), fy - (FR + L) * math.sin(a)
        px, py = -math.sin(a), -math.cos(a)
        dr.polygon(P([(x0 + px * 1.1, y0 + py * 1.1), (x1, y1), (x0 - px * 1.1, y0 - py * 1.1)]), fill=255)
    dr.arc([(fx - FR) * S, (fy - FR) * S, (fx + FR) * S, (fy + FR) * S], 208, 332, fill=255, width=int(1.6 * S))   # the crescent (pillow angles run clockwise, so the top is 208..332)
    for k, (x, y) in enumerate(((26.0, 14.0), (29.4, 14.6), (32.4, 16.6), (27.4, 17.6), (30.8, 19.6), (33.6, 20.6),
                                (28.6, 21.6), (31.8, 23.6), (29.8, 25.8))):                              # grapes, behind on the right
        disc(x, y, 1.9, 0.6)
    disc(9.2, 20.4, 5.4)                                                                                  # plum on the left
    dr.line(P([(9.0, 15.0), (9.6, 13.4)]), fill=255, width=int(0.7 * S))
    for x, y in ((5.6, 26.6), (8.4, 28.2), (4.4, 29.4)):                                                  # currants
        disc(x, y, 1.5, 0.6)
    ax, ay, R = 19.0, 23.0, 8.6                                                                           # the big apple in front
    dr.ellipse([(ax - R - 1.0) * S, (ay - R - 1.0) * S, (ax + R + 1.0) * S, (ay + R + 1.0) * S], fill=0)
    dr.ellipse([(ax - R) * S, (ay - R * 0.95) * S, (ax + R * 0.15) * S, (ay + R) * S], fill=255)
    dr.ellipse([(ax - R * 0.15) * S, (ay - R * 0.95) * S, (ax + R) * S, (ay + R) * S], fill=255)
    dr.polygon(P([(ax - 1.4, ay - R * 0.9), (ax, ay - R * 0.62), (ax + 1.4, ay - R * 0.9)]), fill=0)        # the dimple at the top
    dr.line(P([(ax, ay - R * 0.7), (ax + 1.0, ay - R - 1.8)]), fill=255, width=int(1.1 * S))               # stalk
    dr.arc([(ax - R + 2.0) * S, (ay - R + 2.0) * S, (ax + R - 2.0) * S, (ay + R - 2.0) * S], 200, 245, fill=0, width=int(0.9 * S))   # highlight cut
    return im


def glyph_blesseddew():
    """Blessed Dew (326) v5 (user reference: art import export/dew.jpg - a lush tuft of long pointed grass blades
    curving out from the base): a bold tuft of eleven curved, pointed blades fanning from a ground line - tall ones
    in the middle, outer ones bending out and drooping - each black-edged so they stay separate, with dew drops
    beading on three of them."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    blades = (  # (base x, length, lean (+right), curl, width)                                              v7: ASYMMETRIC (user), middle blade curved over to the right
        (4.0, 13.0, -1.0, 0.9, 3.0), (36.0, 17.0, 1.0, 0.7, 3.0), (8.0, 19.0, -0.9, 0.6, 3.2), (32.0, 23.0, 0.85, 0.5, 3.2),
        (12.0, 25.0, -0.6, 0.35, 3.4), (28.0, 30.0, 0.6, 0.3, 3.4), (16.0, 27.0, -0.35, 1.3, 3.4), (24.4, 26.0, 0.25, 0.2, 3.2),
        (19.0, 36.0, 0.5, 0.75, 3.8), (14.0, 22.0, 0.25, 0.1, 2.8), (27.0, 20.0, -0.45, 1.2, 2.8))
    spines = []
    for x0, L, lean, curl, w in blades:
        pts = []
        for m in range(15):
            t = m / 14.0
            x = x0 + lean * L * 0.55 * t ** 1.4 + lean * curl * L * 0.25 * t ** 3
            y = 33.4 - L * t + curl * L * 0.35 * t ** 2.5
            pts.append((x, y))
        spines.append((pts, w))
    for pts, w in spines:
        left, right = [], []
        for k, (x, y) in enumerate(pts):
            x2, y2 = pts[min(k + 1, 14)]; x1, y1 = pts[max(k - 1, 0)]
            dx, dy = x2 - x1, y2 - y1; n = math.hypot(dx, dy) or 1; px, py = -dy / n, dx / n; ww = w * (1 - k / 14.0) ** 0.85 / 2
            left.append((x + px * ww, y + py * ww)); right.append((x - px * ww, y - py * ww))
        hl = [(x + (x - pts[k][0]) * 0.0, y) for k, (x, y) in enumerate(left)]
        halo_l = []; halo_r = []
        for k, (x, y) in enumerate(pts):
            x2, y2 = pts[min(k + 1, 14)]; x1, y1 = pts[max(k - 1, 0)]
            dx, dy = x2 - x1, y2 - y1; n = math.hypot(dx, dy) or 1; px, py = -dy / n, dx / n; ww = w * (1 - k / 14.0) ** 0.85 / 2 + 0.7
            halo_l.append((x + px * ww, y + py * ww)); halo_r.append((x - px * ww, y - py * ww))
        tx, ty = pts[-1]; x1, y1 = pts[-2]; n = math.hypot(tx - x1, ty - y1) or 1
        dr.polygon(P(halo_l + [(tx + (tx - x1) / n * 0.8, ty + (ty - y1) / n * 0.8)] + list(reversed(halo_r))), fill=0)
        dr.polygon(P(left + list(reversed(right))), fill=255)
    dr.rectangle([1.0 * S, 33.0 * S, 39.0 * S, 34.6 * S], fill=255)                                           # ground line
    def hang(idx, back, r, halo=0.7):                                                                                  # v7.2: a drop hanging from the blade's underside, `back` points short of the tip
        pts, w = spines[idx]; k = 14 - back; tx, ty = pts[k]; ty += w * (1 - k / 14.0) ** 0.85 / 2; cy_ = ty + r * 1.5
        dr.ellipse([(tx - r - halo) * S, (cy_ - r * 0.55) * S, (tx + r + halo) * S, (cy_ + r + halo) * S], fill=0)   # v7.6: outline round the drop's BODY only - never cuts the blade; the drop's tip simply touches the underside                          # v7.4: a black teardrop outline whose POINT is the attachment, so the drop reads distinct but stays connected
        teardrop(dr, tx * S, cy_ * S, r * S, tip_up=True)                                                   # its tip on the blade
    hang(4, 3, 1.5)                                                                                         # left: smaller and lower, its tip on the blade's underside (user)
    hang(8, 2, 1.6, 0.8)                                                                                     # v7.5: the top drop bigger, thicker outline (user: more distinct)                                                                                         # top: smaller and a bit lower on the curved middle blade (user)
    hang(7, 6, 1.6)                                                                                         # new: off the top of the blade right of the middle one (user)
    hang(10, 1, 1.9)
    hang(5, 4, 1.6)                                                                                         # new: on the tall blade at the right (user)
    return im


def glyph_worldhealer():
    """World Healer (327) v7 (user: v6 terrible - revert to the traced hands and make the bottom hand a copy of the
    TOP hand, which was good): the top hand traced from the reference (worldhealer_hands_mask.png = the original
    trace with the globe disc cleared; top hand = rows <= 15 plus the left arm down to row 17), smoothed at drawing
    resolution, and the bottom hand = that top hand turned 180 degrees about the globe centre; the globe drawn clean
    inside (dark sphere, white rim, light continents)."""
    m = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "worldhealer_hands_mask.png")).convert("L")
    px = m.load(); top = Image.new("L", m.size, 0); tp = top.load()
    for y in range(m.size[1]):
        for x in range(m.size[0]):
            if px[x, y] > 127 and (y <= 15 or (x < 12 and y <= 17)): tp[x, y] = 255
    cx, cy, R = 19.0, 16.4, 10.2
    big = top.resize((W * S, H * S), Image.LANCZOS).point(lambda v: 255 if v > 120 else 0)            # smoothed edges
    rot = big.rotate(180, resample=Image.NEAREST, center=(cx * S, cy * S))
    im = canvas(); paste_max(im, big, (0, 0)); paste_max(im, rot, (0, 0))
    dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    dr.ellipse([(cx - R - 1.0) * S, (cy - R - 1.0) * S, (cx + R + 1.0) * S, (cy + R + 1.0) * S], fill=0)      # a clean gap round the globe
    dr.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], outline=255, width=int(1.1 * S))
    rnd = random.Random(3271)                                                                            # v7.3: bigger made-up continents, CLIPPED inside the globe
    land = Image.new("L", im.size, 0); ld = ImageDraw.Draw(land)
    for (lx, ly, lr, nv) in ((14.6, 15.6, 5.4, 18), (24.8, 10.8, 3.2, 13), (24.2, 21.6, 3.0, 12)):          # v7.5: ASYMMETRIC (v7.4 read as a ship's wheel)
        poly = []
        for k in range(nv):
            a = 2 * math.pi * k / nv; rr = lr * (0.66 + 0.5 * rnd.random()) * (1.0 + 0.22 * math.sin(3 * a + lr))
            poly.append(((lx + rr * math.cos(a) * 1.1) * S, (ly + rr * math.sin(a)) * S))
        ld.polygon(poly, fill=255)
    for x, y, r in ((27.8, 16.4, 0.8), (12.2, 23.8, 0.7), (21.4, 8.6, 0.6)):
        ld.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)
    clip = Image.new("L", im.size, 0); ImageDraw.Draw(clip).ellipse([(cx - R + 1.6) * S, (cy - R + 1.6) * S, (cx + R - 1.6) * S, (cy + R - 1.6) * S], fill=255)
    from PIL import ImageChops
    im.paste(255, mask=ImageChops.multiply(land, clip))
    return im


def glyph_soulsiphon():
    """Soul Siphon (340) v8 (user: the drawn v7 lost way too much detail): the line-art reference (art import
    export/soul siphon.jpg - two faces joined by flowing ribbons) traced in GREYSCALE (lines thickened MaxFilter 7,
    LANCZOS downsample, x1.6 gain, no threshold) so the thin lines survive as anti-aliased ink -> soulsiphon_user_mask.png."""
    return _user_mask_glyph("soulsiphon_user_mask.png")


def glyph_plague():
    """Plague (341) v2 (user: a city like the other city enchantments, with a rat over it; reference art import
    export/plague.jpg): Gold Rush's own city silhouette (icon 45, rows 22-35) with the reference rat TRACED
    (plague_rat_mask.png, 40x18) standing over it, a black gap between them."""
    im = canvas()
    city = vanilla_ink(45).crop((0, 21, 40, 35)).point(lambda v: 255 if v > 90 else 0).resize((40 * S, 14 * S), Image.NEAREST)
    paste_max(im, city, (0, 21 * S))
    rat = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plague_rat_mask.png")).convert("L")
    bb_ = rat.getbbox(); rat = rat.crop(bb_)
    rw, rh = rat.size; sc = min(30.0 / rw, 15.0 / rh)                                                   # v2.2: a bit smaller than v2 (34/17); v2.1 lost the resize to a comment
    rat = rat.resize((int(rw * sc * S), int(rh * sc * S)), Image.NEAREST)
    x0 = int((40 * S - rat.width) / 2); y0 = int(20.0 * S - rat.height)
    from PIL import ImageFilter
    layer = Image.new("L", im.size, 0); layer.paste(rat, (x0, y0))
    im.paste(0, mask=layer.filter(ImageFilter.MaxFilter(int(1.2 * S) | 1))); im.paste(255, mask=layer)
    return im


def glyph_blacktide():
    """Black Tide (342) v2 (user reference: art import export/black tide.jpg - a great curling wave with spray):
    the reference TRACED (tmp\\tr3.py variant 1) -> blacktide_user_mask.png."""
    return _user_mask_glyph("blacktide_user_mask.png")


def glyph_hydra():
    """Summon Hydra (343) v3 (user reference: art import export/hydra.jpg - three dragon heads on coiled necks):
    the reference TRACED (tmp\\tr3.py variant 1: median 3, blur 1.5, thr 128) -> hydra_user_mask.png."""
    return _user_mask_glyph("hydra_user_mask.png")


def _ink_png(fname):
    """A 40x35 ink mask (white = ink) saved next to this script, upscaled crisp to the drawing size."""
    return Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)).convert("L").resize((W * S, H * S), Image.NEAREST)


def glyph_mistystep():
    """Misty Step (396) v6 (user: restore the v4 splash; the torso extends down and is cut to the splash shape):
    the v4 splash drawn whole, the figure's torso continued down and clipped 1.6 px clear of the splash.  v5 (user: torso longer, closer to the splash but separate; arms restored): the full figure
    (rows 0-19 incl. arms/hands/legs) with row 12 repeated 4x, the splash cleared 1.6 px around it.  v4 (user: v3 sucked, try again; Void Step's icon with a splash of water for the bottom half):
    Void Step's own icon (voidstep_ink.png) kept at FULL size for the top half (the meditating figure, its rings cut
    away), and in place of the rings a bold water splash the figure rises out of: a broad splash sheet thrown up and
    out on both sides of the body in two big curling wings, a column of water at the centre, big round drops flung
    high, and the disturbed water surface (a wide ellipse rim) underneath."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    from PIL import ImageChops, ImageFilter
    src = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "voidstep_ink.png")).convert("L").point(lambda v: 255 if v > 127 else 0)
    EXT = 0                                                                                                 # v6: arms stay at their own height (v5 stretched 4 rows - the splash cut the arms)
    fig = Image.new("L", (W, 20 + EXT), 0)
    fig.paste(src.crop((0, 0, W, 13)), (0, 0))
    for k in range(EXT): fig.paste(src.crop((0, 12, W, 13)), (0, 13 + k))
    fig.paste(src.crop((0, 13, W, 20)), (0, 13 + EXT))                                                     # shoulders, arms, hands + crossed legs (rows 13-19) intact
    LIFT = 0                                                                                                # v10: back down onto the splash (v8 2 rows up; user v9: torso too far from the splash)
    fig2 = Image.new("L", (W, H), 0); fig2.paste(fig, (0, -LIFT))
    fig = fig2.resize((W * S, H * S), Image.NEAREST)
    figL = Image.new("L", im.size, 0); figL.paste(fig, (0, 0))
    im = Image.new("L", im.size, 0); dr = ImageDraw.Draw(im)                                                # the splash is drawn alone first...
    # v9 (user: new references - the BOTTOM like art import export/splash.jpg, the TOP shaped like splash2.jpg):
    # splash.jpg's flared base + ripple rings (its rows 540..743) along the bottom, splash2.jpg's rounded crown of
    # tongues (with its highlights and wavy inner line) on top, its narrow foot sunk into the base.
    def ref(name):
        r = ImageOps.invert(Image.open(os.path.join(IMPORT_DIR, name)).convert("L")).point(lambda v: 255 if v > 128 else 0)
        return r.crop(r.getbbox())
    base = ref("splash.jpg"); bw = base.width; base = base.crop((0, 540 - 32, bw, base.height))           # (bbox top was y 32)
    BW, BH = 38.0, 10.0
    base = base.resize((int(BW * S), int(BH * S)), Image.LANCZOS).point(lambda v: 255 if v > 110 else 0)
    crown = ref("splash2.jpg")
    CW, CH = 32.0, 12.0
    crown = crown.resize((int(CW * S), int(CH * S)), Image.LANCZOS).point(lambda v: 255 if v > 110 else 0)
    fill_ = Image.new("L", (crown.width + 2, crown.height + 2), 0); fill_.paste(crown, (1, 1))           # fill the crown's inner holes (its wavy line and
    ImageDraw.floodfill(fill_, (0, 0), 128); crown = fill_.crop((1, 1, crown.width + 1, crown.height + 1)).point(lambda v: 0 if v == 128 else 255)   # highlights turn to noise at 40x35)
    im.paste(255, (int((20 - BW / 2) * S), int((H - BH) * S)), base)
    im.paste(255, (int((20 - CW / 2) * S), int(18.6 * S)), crown)
    sp_ = im.load(); fl_ = figL.load(); gap = int(1.2 * S); y_leg = (20 - LIFT) * S                          # v10: the lower body (crossed-legs width) fills each
    top = {x: next((y for y in range(y_leg, H * S) if sp_[x, y]), H * S) for x in range(W * S)}             #   column down to just above the splash's TOP edge,
    k_ = int(0.6 * S)                                                                                       #   smoothed to the highest tongue tip within 2.5 px -
    for x in range(15 * S, 25 * S):                                                                         #   a clean arch hugging the crown's tips (v11: torso width only)
        ys = min(top[q] for q in range(max(0, x - k_), min(W * S, x + k_ + 1)))
        for y in range(y_leg - S, ys - gap): fl_[x, y] = 255
    figL.paste(0, (0, (18 - LIFT) * S, 15 * S, H * S)); figL.paste(0, (25 * S, (18 - LIFT) * S, W * S, H * S))   # v12: below the arms only the torso's own width (x 15-24) - no hand/leg stubs
    figL.paste(0, mask=im.filter(ImageFilter.MaxFilter(int(1.6 * S) | 1)))                                 # v8: the SPLASH takes precedence - the figure gets an
    im.paste(255, mask=figL)                                                                                #   outline cut-out round it (the arms sit above it)
    return im


def glyph_flashfreeze():
    """Flashfreeze (397) v3 (user: v2 bad - reference art import export/flashfreeze.jpg, a sharp six-armed ice star
    with diamond tips): the reference TRACED at drawing resolution (thr 128) -> flashfreeze_user_mask.png."""
    return _user_mask_glyph("flashfreeze_user_mask.png")


def _hands_px(th=27, fz=None, nf=3):
    """Nimue v8 (user: the fingers/thumbs looked janky): Cleansing Flame's reference praying hands rebuilt AT ICON
    RESOLUTION - the filled silhouette box-sampled to th rows, the finger seams placed on the nf 45-degree diagonals
    where the reference's seams are densest (>= 3 apart = clean 2-px fingers, 1-px rim kept), and the thumb/cuff seams
    kept as 1-px row maxima.  The thin source seams turned to a grey checkerboard at 40x35."""
    ref = Image.open(os.path.join(IMPORT_DIR, "praying-hands-illustration-black-white-260nw-2628304599.webp")).convert("L").crop((0, 0, 260, 236))
    ink = ref.point(lambda v: 255 if v < 128 else 0); ink = ink.crop(ink.getbbox())
    filled = ink.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    seam = ImageChops.subtract(filled, ink)
    w = round(filled.width * th / filled.height)
    sil = filled.resize((w, th), Image.BOX).point(lambda v: 255 if v > 110 else 0)
    sd = seam.resize((w, th), Image.BOX); sp = sd.load(); out = sil.copy(); op = out.load()
    fz = fz or int(th * 0.42)
    score = {}
    for y in range(fz):
        for x in range(w):
            if op[x, y]: score[x - y] = score.get(x - y, 0) + sp[x, y]
    picks = []
    for c, v in sorted(score.items(), key=lambda kv: -kv[1]):
        if all(abs(c - q) >= 3 for q in picks): picks.append(c)
        if len(picks) == nf: break
    for c in picks:
        for y in range(fz):
            x = y + c
            if 0 <= x < w and op[x, y]:
                # keep a 1-px ink rim at the silhouette edge so the gap doesn't notch the outline
                if 0 < x < w - 1 and 0 < y and op[x - 1, y] and op[x + 1, y] and op[x, y - 1]: op[x, y] = 0
    for y in range(fz, th):                                                       # thumb / cuff seams: the strong ones only
        for x in range(w):
            if 0 < x < w - 1 and op[x, y] and sp[x, y] >= 40 and sp[x, y] >= sp[x - 1, y] and sp[x, y] >= sp[x + 1, y] and 0 < x < w - 1 and op[x - 1, y] and op[x + 1, y]: op[x, y] = 0
    return out, picks


def glyph_nimue():
    """Nimue's Favour (398) v3 (user: hands bigger and partly hidden by the waves at the wrists; a ring of circular
    PARTICLES, not a solid circle): a halo of separate round motes of varying size (Champion-style particle ring),
    Cleansing Flame's praying hands (glyph_cleansing, flames masked off) large in the middle, and Water Walking's wave
    (vanilla SpellIcn 101) laid OVER the wrists - v6: the wave at FULL detail (only the walker's body + legs erased),
    everything below the crest cleared and a 1-px gap between the hands and the water."""
    from PIL import ImageChops, ImageFilter
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy, R = 20.0, 15.6, 14.4
    for k in range(18):                                                                                     # the particle ring
        a = math.radians(k * 20 + 6); r = (1.25, 0.8, 1.0)[k % 3]
        x, y = cx + R * math.cos(a), cy + R * 0.98 * math.sin(a)
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)
    # v9 (user: v8 pixel hands bad - make them like Cleansing Flame): the hands built EXACTLY as glyph_cleansing builds
    # them (same reference, seams, 27*S LANCZOS, same clear halo) and pasted 1:1 - no second resample (v3-v7 cropped
    # Cleansing's finished glyph and NEAREST-rescaled it, which jagged the fingers).
    ref = Image.open(os.path.join(IMPORT_DIR, "praying-hands-illustration-black-white-260nw-2628304599.webp")).convert("L").crop((0, 0, 260, 236))
    ink = ref.point(lambda v: 255 if v < 128 else 0); full_h = ink.crop(ink.getbbox()).height
    ImageDraw.Draw(ink).polygon([(0, 170), (95, 172), (150, 166), (158, 146), (260, 120), (260, 236), (0, 236)], fill=0)   # v11: no sleeves (cuffs below the wrists)
    ink = ink.crop(ink.getbbox())
    filled = ink.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    seams = ImageChops.subtract(filled, ink).filter(ImageFilter.MaxFilter(5))
    solid = ImageChops.subtract(filled, seams)
    th = 27.0 * S; sc = th / full_h                                                                         # same scale as Cleansing (sleeves or not)
    hands = solid.resize((int(solid.width * sc), int(solid.height * sc)), Image.LANCZOS)
    halo = filled.filter(ImageFilter.MaxFilter(15)).resize(hands.size, Image.LANCZOS)
    import numpy as _np
    ha = _np.asarray(hands, dtype=_np.float32); tot = ha.sum()                                             # v10 (user: centre them better): the hands' INK
    gx = (ha.sum(axis=0) * _np.arange(ha.shape[1])).sum() / tot; gy = (ha.sum(axis=1) * _np.arange(ha.shape[0])).sum() / tot   # centroid on the ring's centre
    x0, y0 = int(20.0 * S - gx), int(17.0 * S - gy)                                                         # (the wave may hide more of the wrists - fine)
    hl_ = Image.new("L", im.size, 0); hl_.paste(halo, (x0, y0)); im.paste(0, mask=hl_.point(lambda v: 255 if v > 100 else 0))
    paste_max(im, hands, (x0, y0))
    wv = vanilla_ink(101).point(lambda v: v if v > 30 else 0)                                               # v6: FULL detail (grey edges kept)
    wd_ = ImageDraw.Draw(wv); wd_.rectangle([0, 0, 39, 11], fill=0); wd_.rectangle([12, 0, 25, 16], fill=0)  # v7: drop ONLY the walker (body, then its legs) -
    wd_.rectangle([15, 0, 19, 19], fill=0); wd_.rectangle([21, 0, 23, 17], fill=0)                          # the crest curling up right of it (rows 14-17) stays
    band = Image.new("L", (W, H), 0); band.paste(wv.crop((0, 12, 40, 25)), (0, 18)); bp = band.load()
    below = Image.new("L", (W, H), 0); bd = ImageDraw.Draw(below)
    for x in range(W):                                                                                      # clear everything from 1 px above the crest down
        ys = [y for y in range(18, H) if bp[x, y] > 30]
        if ys: bd.line([(x, ys[0] - 1), (x, H)], fill=255)
    im.paste(0, mask=below.resize((W * S, H * S), Image.NEAREST))
    paste_max(im, band.resize((W * S, H * S), Image.NEAREST), (0, 0))                                       # the Water Walking wave, intact
    return im


def glyph_iceage():
    """Ice Age (399) v2 (user: the mountain from Level Terrain, and more snowflakes): Level Terrain's mountains (vanilla
    SpellIcn 50, the peaks only - its arrow masked off) along the bottom, and (v4, user: the PLACEMENT was too symmetrical -
    keep the flakes straight) nine regular flakes scattered unevenly, the small ones falling into the valleys."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    mt = vanilla_ink(50).point(lambda v: v if v > 30 else 0)                                               # v5: FULL detail (anti-aliased edges kept, no threshold)
    md = ImageDraw.Draw(mt); md.rectangle([14, 0, 26, 22], fill=0)                                            # drop the arrow (rows 7-22 x 17-25 only)
    MT_DY = 3                                                                                               # the whole icon's mountains, 3 rows lower, unscaled
    mtc = Image.new("L", (W, H), 0); mtc.paste(mt, (0, MT_DY)); mp_ = mtc.load()
    paste_max(im, mtc.resize((W * S, H * S), Image.NEAREST), (0, 0))
    def flake(cx, cy, R):                                                                                   # straight, regular six-armed flakes
        dr.ellipse([(cx - R - 0.9) * S, (cy - R - 0.9) * S, (cx + R + 0.9) * S, (cy + R + 0.9) * S], fill=0)
        for k in range(6):
            a = math.radians(90 + k * 60); ux, uy = math.cos(a), -math.sin(a)
            dr.line(P([(cx, cy), (cx + R * ux, cy + R * uy)]), fill=255, width=max(1, int((0.9 + R * 0.06) * S)))
            if R > 2.6:
                bx, by = cx + R * 0.55 * ux, cy + R * 0.55 * uy
                for d in (-1, 1):
                    b2 = a + d * math.radians(50); dr.line(P([(bx, by), (bx + R * 0.32 * math.cos(b2), by - R * 0.32 * math.sin(b2))]), fill=255, width=max(1, int(0.8 * S)))
    for cx, cy, R in ((15.0, 7.4, 6.0), (4.6, 3.8, 2.6), (31.4, 4.4, 3.4), (34.6, 14.6, 2.4), (25.6, 13.8, 4.2),
                      (8.0, 13.8, 2.8), (19.6, 22.4, 3.6)):              # v4: scattered, not mirrored
        if any(mp_[x, y] for y in range(H) for x in range(W) if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= (R + 1.0) ** 2):   # v6: disc test (its halo)
            continue                                                                                        # v5: no flake may touch the mountains
        flake(cx, cy, R)
    return im


def glyph_suffocate():
    """Suffocate (345) v7 (user: new reference art import export/lungs.jpg - a pair of lungs with windpipe, airways cut
    as white; put a skull on top of it): the lungs TRACED (lungs_ink_full.png, thr 140) at drawing resolution filling
    the lower ~27 rows (its white airways thickened so they read at 40x35), and vanilla SpellIcn 23's skull (crop 10,13-30,31, its own ink) set on top of the windpipe."""
    from PIL import ImageFilter
    im = canvas()
    lg = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lungs_ink_full.png")).convert("L")
    th = 21.0 * S; sc = th / lg.height; lw = int(lg.width * sc)                                            # v7.6 (user: revert to pre-torso = v7.3): lungs 21 rows                                            # v7.2: lungs smaller (26 -> 21 rows)
    pad = Image.new("L", (lg.width + 2, lg.height + 2), 0); pad.paste(lg, (1, 1)); ImageDraw.floodfill(pad, (0, 0), 128)
    sil = pad.crop((1, 1, lg.width + 1, lg.height + 1)).point(lambda v: 0 if v == 128 else 255)          # the lungs' filled silhouette
    veins = ImageChops.subtract(sil, lg).filter(ImageFilter.MaxFilter(5))                                   # v7.1: the white airways thickened (they were
    lg = ImageChops.subtract(sil, veins)                                                                    #   ~0.5 px at icon size -> noise)
    lg = lg.resize((lw, int(th)), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)
    torso = []                                                                                              # v8 (user: keep it, but add a SOLID torso and
    for sg in (-1, 1):                                                                                      #   invert the lungs to be transparent): the torso
        side = [(20 + sg * 3.0, 13.6), (20 + sg * 6.8, 15.0), (20 + sg * 11.4, 16.2), (20 + sg * 14.6, 18.0), (20 + sg * 15.8, 21.0),   # as solid ink,
                (20 + sg * 15.8, 25.0), (20 + sg * 15.2, 29.0), (20 + sg * 15.0, 32.0), (20 + sg * 15.4, 35.2)]                         # the lung tissue cut
        torso.append(side if sg < 0 else side[::-1])                                                        #   out of it (clear), its airways left as ink
    ImageDraw.Draw(im).polygon([(x * S, y * S) for x, y in torso[0] + torso[1]], fill=255)
    ll = Image.new("L", im.size, 0); ll.paste(lg, (int(20 * S - lw / 2), int(H * S - th)))
    im.paste(0, mask=ll)
    sk = vanilla_ink(23).crop((10, 13, 30, 31)); SC = 0.72; sw, sh = int(20 * SC * S), int(18 * SC * S)
    sk = sk.resize((sw, sh), Image.LANCZOS); sx0, sy0 = int(20 * S - sw / 2), int(0.0 * S)
    ny0, ny1 = sy0 + sh - 1.2 * S, H * S - th + 2.0 * S                                                    # v7.3 (user: a thicker neck joining skull and lungs)
    ImageDraw.Draw(im).rectangle([20 * S - 2.6 * S, ny0, 20 * S + 2.6 * S, ny1], fill=255)
    for yy in (ny0 + 1.8 * S, ny0 + 3.6 * S): ImageDraw.Draw(im).line([(20 * S - 2.6 * S, yy), (20 * S + 2.6 * S, yy)], fill=0, width=int(0.5 * S))   # vertebrae
    lay = Image.new("L", im.size, 0); lay.paste(sk, (sx0, sy0))
    im.paste(0, mask=lay.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(int(1.0 * S) | 1))); paste_max(im, sk, (sx0, sy0))
    return im


def glyph_succubus():
    """Summon Succubus (347) v2 (user: v1 sucked - reference art import export/succubus.jpg, a winged woman in black
    silhouette, long hair over great feathered wings): the reference TRACED at drawing resolution (thr 128, x1.32 wider to fill the icon) ->
    succubus_user_mask.png.  v3 (user: wings more demonic/draconic, nothing else changed): make_succubus_wings.py keeps
    the traced body + hair and redraws the wings as bat/dragon wings (arm bone, clawed wrist, 5 finger bones, scalloped
    membrane) -> succubus_user_mask.png (the feathered v2 kept as succubus_feather_mask.png)."""
    return _user_mask_glyph("succubus_user_mask.png")


def glyph_banshee():
    """Banshee Gale (344) v13 (user: add Pestilence's skull, much smaller, in the centre; the swirl slightly skewed and
    enlarged): banshee5_user_mask.png (the traced ink whirlwind) enlarged x1.10 and sheared a little, kept inside the
    inset oval (nothing touches the edges), a clear disc cut at its eye and vanilla SpellIcn 22's skull-in-a-ring
    (Pestilence) shrunk to ~40 % set in it."""
    from PIL import ImageFilter
    base = _user_mask_glyph("banshee5_user_mask.png")
    Wp, Hp = base.size; cx0, cy0 = Wp / 2.0, Hp / 2.0
    k, sh = 1 / 1.10, 0.14                                                                                  # enlarge 10 %, shear x by 0.14 * y
    base = base.transform(base.size, Image.AFFINE, (k, sh * k, cx0 - k * cx0 - sh * k * cy0, 0, k, cy0 - k * cy0), resample=Image.BICUBIC)
    fence = Image.new("L", base.size, 0); ImageDraw.Draw(fence).ellipse([1.6 * S, 1.4 * S, Wp - 1.6 * S, Hp - 1.4 * S], fill=255)
    im = ImageChops.multiply(base.point(lambda v: 255 if v > 128 else 0), fence)
    sk = vanilla_ink(22).crop((2, 2, 38, 33)); SC = 0.40; sw, sh_ = int(36 * SC * S), int(31 * SC * S)
    sk = sk.resize((sw, sh_), Image.LANCZOS).point(lambda v: 255 if v > 90 else 0)
    x0, y0 = int(cx0 - sw / 2), int(cy0 - sh_ / 2)
    dr = ImageDraw.Draw(im); dr.ellipse([x0 - 1.0 * S, y0 - 1.0 * S, x0 + sw + 1.0 * S, y0 + sh_ + 1.0 * S], fill=0)   # clear disc at the eye
    paste_max(im, sk, (x0, y0))
    return im


def glyph_borrowtime():
    """Borrow Time (346, Air/Death tier 3): an hourglass - the last grains running down from the top bulb onto a skull
    lying in the bottom one."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx = 20.0
    dr.rectangle([9.0 * S, 1.0 * S, 31.0 * S, 3.6 * S], fill=255); dr.rectangle([9.0 * S, 31.4 * S, 31.0 * S, 34.0 * S], fill=255)   # caps
    for x in (10.6, 29.4): dr.rectangle([(x - 0.8) * S, 3.6 * S, (x + 0.8) * S, 31.4 * S], fill=255)        # posts
    glass = [(13.0, 4.6), (27.0, 4.6), (27.0, 8.0), (21.2, 16.6), (21.2, 18.4), (27.0, 27.0), (27.0, 30.4), (13.0, 30.4), (13.0, 27.0),
             (18.8, 18.4), (18.8, 16.6), (13.0, 8.0)]
    dr.polygon(P(glass), outline=255, width=int(1.0 * S))
    dr.polygon(P([(15.6, 9.6), (24.4, 9.6), (20.6, 15.4), (19.4, 15.4)]), fill=255)                        # the little sand left on top
    dr.line(P([(20.0, 15.6), (20.0, 22.0)]), fill=255, width=int(0.7 * S))                                  # the falling grains
    sk = (20.0, 25.4)                                                                                       # skull in the bottom bulb
    dr.ellipse([(sk[0] - 4.0) * S, (sk[1] - 3.4) * S, (sk[0] + 4.0) * S, (sk[1] + 2.6) * S], fill=255)
    dr.rectangle([(sk[0] - 2.4) * S, (sk[1] + 1.6) * S, (sk[0] + 2.4) * S, (sk[1] + 4.2) * S], fill=255)
    for ex in (sk[0] - 1.7, sk[0] + 1.7): dr.ellipse([(ex - 1.1) * S, (sk[1] - 1.4) * S, (ex + 1.1) * S, (sk[1] + 0.8) * S], fill=0)
    for tx in (sk[0] - 1.2, sk[0], sk[0] + 1.2): dr.line(P([(tx, sk[1] + 2.6), (tx, sk[1] + 4.2)]), fill=0, width=int(0.4 * S))
    return im


def glyph_chorus():
    """Heavenly Chorus (308, Life/Air tier 1): art import export/heavenly choir.png - an angel in flight sounding a long
    trumpet - TRACED (its black ink, the white highlights left clear) -> chorus_user_mask.png.  v2 (user: a bit smaller,
    the horn bigger): the angel at 85 % (centred), and its trumpet (mask box 15,12-92,50) lifted out and scaled x1.5
    about the mouthpiece (92, 45 in mask px) so it stays at the lips, drawn over a thin dark gap."""
    from PIL import ImageFilter, ImageChops
    m = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chorus_user_mask.png")).convert("L")
    Wm, Hm = m.size; sx, sy = W * S / Wm, H * S / Hm
    A = 0.85
    body = m.resize((int(Wm * A), int(Hm * A)), Image.LANCZOS)
    im = Image.new("L", (Wm, Hm), 0); bx, by = int((Wm - body.width) / 2 + 10), int((Hm - body.height) / 2 + 8)
    im.paste(body, (bx, by))
    mx, my = bx + 92 * A, by + 45 * A                                                                       # the mouthpiece after the 85 % shrink
    d = ImageDraw.Draw(im)
    band = Image.new("L", (Wm, Hm), 0)                                                                      # v4: erase ONLY a band along the old trumpet line
    ImageDraw.Draw(band).line([(bx + 12 * A, by + 18 * A), (bx + 94 * A, by + 46 * A)], fill=255, width=int(20 * A))   #   (the hands survive)
    hands = ImageChops.multiply(im.copy(), Image.eval(band, lambda v: 255 - v))
    hreg = Image.new("L", (Wm, Hm), 0); ImageDraw.Draw(hreg).rectangle([bx + 28 * A, by + 36 * A, bx + 80 * A, by + 80 * A], fill=255)
    hands = ImageChops.multiply(hands, hreg)                                                                # the hands' pixels (kept for re-drawing on top)
    im.paste(0, mask=band)
    ex, ey = mx - 84, my - 36
    L = math.hypot(ex - mx, ey - my); ux, uy = (ex - mx) / L, (ey - my) / L; px, py = -uy, ux
    def outline(grow):
        left, right = [], []
        for q in range(61):
            t = q / 60.0; cx_, cy_ = mx + ux * L * t, my + uy * L * t
            hw = 2.6 + 3.2 * min(1.0, t / 0.12) + (13.0 * ((t - 0.45) / 0.55) ** 2.4 if t > 0.45 else 0.0)   # mouthpiece -> tube -> a gradual bell
            g = grow if t > 0.14 else 0.0                                                                   # (no dark cut where it meets the face)
            left.append((cx_ + px * (hw + g), cy_ + py * (hw + g))); right.append((cx_ - px * (hw + g), cy_ - py * (hw + g)))
        return left + right[::-1]
    d.polygon(outline(4.0), fill=0); d.polygon(outline(0.0), fill=255)
    for t in (0.22, 0.4):                                                                                   # bands round the tube
        cx_, cy_ = mx + ux * L * t, my + uy * L * t; hw = 6.5
        d.line([(cx_ + px * hw, cy_ + py * hw), (cx_ - px * hw, cy_ - py * hw)], fill=0, width=3)
    im.paste(0, mask=hands.point(lambda v: 255 if v > 100 else 0).filter(ImageFilter.MaxFilter(3)))      # the hands back on top, gripping it
    im.paste(255, mask=hands.point(lambda v: 255 if v > 128 else 0))
    return im.resize((W * S, H * S), Image.NEAREST).point(lambda v: 255 if v > 128 else 0)


def glyph_inspire():
    """Inspiration (309) v4 (user: new reference art import export/inspiration.jpg - a rider on a rearing horse raising a
    flag; its modern peaked cap replaced by a plain bare head): traced (cap + brim erased at src 472,374-546,412, a
    rounded crown drawn to join the face profile), x1.12 wide -> inspire2_user_mask.png.  (v3 banner superseded.)"""
    return _user_mask_glyph("inspire2_user_mask.png")


def glyph_secondwind():
    """Second Wind (310, Life/Air tier 3): art import export/second wind.jpg - a weary knight kneeling on one knee, sword
    planted, shield on his arm, arrows in his back - TRACED -> secondwind_user_mask.png.  v2 (user: accurate but out of
    place - fit in with the other icons): simplified toward the vanilla look - a median filter drops the photographic
    speckle, a close/open pass smooths the shapes into bold silhouette masses, and the small inner details are kept
    only where they are thick enough to read at 40x35."""
    from PIL import ImageFilter
    m = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "secondwind_user_mask.png")).convert("L")
    m = m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MedianFilter(5)).point(lambda v: 255 if v > 128 else 0)   # v2.2: thin lines thickened first, then smoothed
    bb = m.getbbox(); k = m.crop(bb); Wm, Hm = m.size
    kw = min(Wm - 8, int(k.width * 1.25)); k = k.resize((kw, k.height), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)   # x1.25 wider: fills the icon
    o = Image.new("L", (Wm, Hm), 0); o.paste(k, ((Wm - kw) // 2, bb[1]))
    # v3 (user: a better-defined sword with a hilt below the hand, the handle above the hand a touch shorter; the shield
    # removed so his whole body shows): edits in an 80x70 grid (x4 = mask px)
    d = ImageDraw.Draw(o); Q = lambda pts: [(x * 4, y * 4) for x, y in pts]
    d.rectangle(Q([(44, 30), (80, 70)]), fill=0)                                                           # the shield gone
    d.polygon(Q([(33, 27), (56, 27), (55, 45), (35, 47)]), fill=255)                                       # lower torso / belt
    d.line(Q([(54, 27), (60, 37), (57, 47)]), fill=255, width=20, joint="curve")                          # his free arm, resting toward the knee
    d.ellipse(Q([(54.5, 45), (59.5, 49.5)]), fill=255)                                                     #   its hand
    d.rectangle(Q([(44.6, 43), (78, 63.4)]), fill=0)                                                       # v6 (user: legs the same thickness; the knee planted,
    d.polygon(Q([(46.8, 43), (55.4, 43), (55.4, 60.0), (53.8, 63.2), (46.8, 63.2), (46.2, 60.0)]), fill=255)   #   v7: the thigh a little thicker, straight down to the knee
    d.polygon(Q([(49.5, 63.2), (52.0, 57.6), (65.8, 54.0), (67.6, 60.6), (54.0, 63.2)]), fill=255)         #   a THICKER shin rising back to the ankle
    d.polygon(Q([(64.6, 54.2), (68.2, 54.0), (68.6, 63.6), (62.0, 63.8), (62.4, 61.4), (65.2, 60.8)]), fill=255)   #   the foot nearly square to the ground, toes turned in
    d.rectangle(Q([(27.5, 48.5), (44.6, 63.4)]), fill=0)                                                   # v5 (user: remove what hangs beneath him): the old rags cleared
    d.polygon(Q([(34, 44), (56, 44), (56, 48.5), (34, 48.5)]), fill=255)                                   #   a clean belt line instead
    d.polygon(Q([(15.6, 64.6), (16.4, 62.0), (21.0, 61.0), (25.6, 60.4), (27.0, 64.6)]), fill=255)         # the front foot: a clear boot, toe forward
    d.rectangle(Q([(0, 65.6), (80, 70)]), fill=0)                                                          # v4: the ground redrawn across the FULL width,
    gl = [(x, 66.6 - 4.4 * math.sin(math.pi * x / 80.0) ** 0.7 - 0.4 * math.sin(x * 1.7)) for x in range(0, 81)]   #   thickest under him and tapering
    gb = [(x, 66.6 + 1.6 * math.sin(math.pi * x / 80.0) + 0.3 * math.sin(x * 2.3)) for x in range(80, -1, -1)]     #   to a thin ragged line at both edges
    d.polygon(Q(gl + gb), fill=255)
    d.rectangle(Q([(17, 6), (24, 18.5)]), fill=0)                                                          # the old pommel + grip above the hand
    d.ellipse(Q([(18.6, 10.2), (22.0, 13.6)]), fill=255)                                                   # pommel (a touch lower = shorter)
    d.rectangle(Q([(19.6, 13.4), (21.0, 19.0)]), fill=255)                                                 # grip down into the hand
    d.rectangle(Q([(14.2, 26.6), (27.4, 29.4)]), fill=0); d.rectangle(Q([(14.8, 27.2), (26.8, 28.8)]), fill=255)   # the CROSSGUARD below the hand
    d.polygon(Q([(18.9, 29.0), (22.3, 29.0), (21.9, 61.0), (20.6, 64.0), (19.3, 61.0)]), fill=0)           # a dark edge so the blade reads over the leg
    d.polygon(Q([(19.5, 29.0), (21.7, 29.0), (21.3, 60.4), (20.6, 62.8), (19.9, 60.4)]), fill=255)         # the blade, tapering to the ground
    return o.resize((W * S, H * S), Image.NEAREST)


def glyph_angelwings():
    """Angel Wings (311, Life/Air tier 4; user: the reference wings with the 'man' from Fire Halo / Liquid Form): the
    traced wing pair (art import export/angel wings.jpg -> angelwings_ink_full.png) spread across the top half, and
    vanilla Fire Halo's figure (SpellIcn 61, the man alone) standing between them, cut free by a dark gap."""
    from PIL import ImageFilter
    im = canvas()
    wg = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "angelwings_ink_full.png")).convert("L")
    ww = 33.0 * S; sc = ww / wg.width; wh = wg.height * sc                                                  # v2 (user: a bit smaller, lower on the man)
    wg = wg.resize((int(ww), int(wh)), Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)
    paste_max(im, wg, (int(20 * S - ww / 2), int(7.0 * S)))
    man = ink_component(vanilla_ink(61), (20, 22)); bb = man.getbbox(); man = man.crop(bb)
    MS = 1.05; mw, mh = int(man.width * MS * S), int(man.height * MS * S)
    man = man.resize((mw, mh), Image.LANCZOS).point(lambda v: 255 if v > 100 else 0)                        # crisp edges
    lay = Image.new("L", im.size, 0); lay.paste(man, (int(20 * S - mw / 2), int(H * S - mh - 0.4 * S)))
    im.paste(0, mask=lay.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(int(1.4 * S) | 1)))
    paste_max(im, man, (int(20 * S - mw / 2), int(H * S - mh - 0.4 * S)))
    return im


def glyph_sanctify():
    """Sanctify (208, Life tier 3, 2026-10-16): consecrated ground - a ring of light on the ground (perspective ellipse,
    a thick rim with six small glints) with a broad beam of light falling into it from above (two converging edges and
    a softer core), and a four-pointed holy star flaring where the beam meets the ground."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx, cy = 20.0, 28.6
    stroke_ellipse(dr, ((cx - 16.5) * S, (cy - 5.2) * S, (cx + 16.5) * S, (cy + 5.2) * S), int(1.6 * S), 255)   # the ring
    for k in range(6):
        a = math.radians(k * 60 + 30); x = cx + 16.5 * math.cos(a); y = cy + 5.2 * math.sin(a)
        dr.ellipse([(x - 1.2) * S, (y - 1.2) * S, (x + 1.2) * S, (y + 1.2) * S], fill=255)
    beam = Image.new("L", (W * S, H * S), 0); bd = ImageDraw.Draw(beam)
    bd.polygon(P([(cx - 3.2, -0.5), (cx + 3.2, -0.5), (cx + 7.5, cy), (cx - 7.5, cy)]), fill=90)         # soft core
    bd.line(P([(cx - 3.2, -0.5), (cx - 7.5, cy - 0.5)]), fill=255, width=int(1.0 * S))                    # edges
    bd.line(P([(cx + 3.2, -0.5), (cx + 7.5, cy - 0.5)]), fill=255, width=int(1.0 * S))
    paste_max(im, beam)
    sy = cy - 7.0                                                                                          # the star
    dr.polygon(P([(cx, sy - 10.0), (cx + 3.4, sy - 3.4), (cx + 10.0, sy), (cx + 3.4, sy + 3.4), (cx, sy + 8.0),
                  (cx - 3.4, sy + 3.4), (cx - 10.0, sy), (cx - 3.4, sy - 3.4)]), fill=0)                  # dark halo
    dr.polygon(P([(cx, sy - 8.5), (cx + 1.6, sy - 1.6), (cx + 8.5, sy), (cx + 1.6, sy + 1.6), (cx, sy + 6.5),
                  (cx - 1.6, sy + 1.6), (cx - 8.5, sy), (cx - 1.6, sy - 1.6)]), fill=255)
    return im


def glyph_miracle():
    """Miracle (209) v4 (2026-10-18, user: lower the star very slightly toward the hands, a small gap under the top
    edge, still not touching the hands): v3's trace (art import export/miracle.jpg via trace_ref.py ->
    miracle_user_mask.png) with the star component moved down 1 icon px -> miracle2_user_mask.png (star top now at
    y 2; nearest star-to-hand gap 1.4 icon px)."""
    return _user_mask_glyph("miracle2_user_mask.png")


def glyph_undying():
    """Undying (210, Death tier 2, 2026-10-16): the user's reference art import export/undying.jpg - a serpent coiled
    into an infinity sign, eating round to its own tail - TRACED (ink < 128, fit 38x33 px, centred, MaxFilter(7) at 8x
    = ~1 px thicker) -> undying_user_mask.png."""
    return _user_mask_glyph("undying_user_mask.png")


def glyph_callofdead():
    """Call of the Dead (211, Death tier 4, 2026-10-16): the user's reference (art import export/call of the dead.jpg -
    a zombie hand clawing up out of a grave mound beside a headstone) TRACED -> callofdead_user_mask.png (binarised,
    thin crease / crack lines closed with an 11 px max/min filter at full size, fitted to 40x35 at 97 %, bottom-aligned)."""
    return _user_mask_glyph("callofdead_user_mask.png")


def _wind_arc(dr, cx, cy, r, a0, a1, w0, w1, ry=None, n=60, grow=0.0):
    """A tapered calligraphic wind arc (Winds of Fury style): centre (cx, cy) icon px, radius r (ry for an ellipse),
    from angle a0 to a1 (degrees, screen y down), width w0 -> w1 icon px."""
    ry = r if ry is None else ry
    for k in range(n + 1):
        u = k / float(n); a = math.radians(a0 + (a1 - a0) * u); w = (w0 + (w1 - w0) * u) / 2.0
        g_ = 1.0 + grow * (u - 0.5)                                     # grow != 0 -> a spiral (radius changes along the arc)
        x, y = cx + r * g_ * math.cos(a), cy + ry * g_ * math.sin(a)
        dr.ellipse([(x - w) * S, (y - w) * S, (x + w) * S, (y + w) * S], fill=255)


def _largest_component(img, thr=80):
    """The biggest connected ink blob of a 40x35 L image (e.g. Spell Ward's hand without its rays)."""
    import numpy as _np
    from collections import deque
    a = _np.asarray(img) > thr; H_, W_ = a.shape; seen = _np.zeros_like(a); best = None
    for y in range(H_):
        for x in range(W_):
            if a[y, x] and not seen[y, x]:
                q = deque([(y, x)]); seen[y, x] = True; comp = []
                while q:
                    cy, cx = q.popleft(); comp.append((cy, cx))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            yy, xx = cy + dy, cx + dx
                            if 0 <= yy < H_ and 0 <= xx < W_ and a[yy, xx] and not seen[yy, xx]: seen[yy, xx] = True; q.append((yy, xx))
                if best is None or len(comp) > len(best): best = comp
    out = Image.new("L", img.size, 0); p = out.load()
    for cy, cx in best: p[cx, cy] = img.getpixel((cx, cy))
    return out


def glyph_gust():
    """Gust (212) v3 (user 10/16: start fresh, Winds of Fury's wind minus the man, much HEAVIER): five heavy tapered
    calligraphic wind arcs in Winds of Fury's sweep (curving from the upper right round to the lower left about a
    centre high on the right), thick at the head (3.4 px) tapering to a point, the inner ones curling tighter."""
    im = canvas(); dr = ImageDraw.Draw(im)
    for k, (r, a0, a1, w0) in enumerate(((30.0, 70, 205, 3.6), (24.0, 66, 210, 3.4), (18.0, 62, 214, 3.2), (12.5, 58, 220, 2.8), (7.5, 55, 230, 2.4))):
        _wind_arc(dr, 33.0, 8.0, r, a0, a1, w0, 0.5, ry=r * 0.92, grow=-0.45, n=90)   # spiralling in toward the tail = a swirling gale
    return im


def glyph_crosswind():
    """Crosswind (213) v16 (user 10/16: follow 'art import export/crosswind general idea.png', a rough draft of the
    shape): three wind lines entering flat at the upper right, flowing left and down in an S-curve and ending in
    curls at the left, nested above a thick arrow that sweeps along the bottom from the lower left and curves up into a
    big head at the right.  Paths are the draft's own strokes (mapped into the 40x35 icon), smoothed (Catmull-Rom) and
    drawn as tapered calligraphic strokes: thin at the right, swelling toward the curls."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def M(p): return (1.0 + (p[0] - 380) * 38.0 / 1110.0, 2.0 + (p[1] - 175) * 31.0 / 665.0)
    def smooth(pts, per=10):
        P = [pts[0]] + pts + [pts[-1]]; out = []
        for k in range(1, len(P) - 2):
            p0, p1, p2, p3 = P[k - 1], P[k], P[k + 1], P[k + 2]
            for t_ in range(per):
                t = t_ / float(per); t2, t3 = t * t, t * t * t
                out.append(tuple(0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2 + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3) for c in (0, 1)))
        out.append(pts[-1]); return out
    def relax(pts, it=6, win=4):                                             # v17 (user: janky lines): heavy smoothing of the
        for _ in range(it):                                                  #   hand-drawn path (moving average, ends pinned)
            q = list(pts)
            for k in range(1, len(pts) - 1):
                lo, hi = max(0, k - win), min(len(pts), k + win + 1)
                q[k] = (sum(p[0] for p in pts[lo:hi]) / (hi - lo), sum(p[1] for p in pts[lo:hi]) / (hi - lo))
            pts = q
        return pts
    def stroke(raw, w0, w1, wend, dy=0.0):
        pts = relax(smooth([(x, y + dy) for x, y in (M(p) for p in raw)], 12))[6:-2]; n = len(pts) - 1   # drop the pinned end stubs
        lay = Image.new("L", im.size, 0); ld = ImageDraw.Draw(lay)
        for k, (x, y) in enumerate(pts):
            u = k / float(n); w = (w0 + (w1 - w0) * min(1.0, u / 0.75)) if u < 0.75 else (w1 + (wend - w1) * (u - 0.75) / 0.25)
            w /= 2.0; ld.ellipse([(x - w) * S, (y - w) * S, (x + w) * S, (y + w) * S], fill=255)
        im.paste(0, mask=lay.filter(ImageFilter.MaxFilter(int(0.9 * S) | 1)))   # a thin dark border: lines never touch
        im.paste(255, mask=lay)
    def windline(xs, ys, xe, ye, R, w0, w1):                                 # v18 (user: still janky): CLEAN parametric lines -
        pts = []                                                             #   a flat start, a smoothstep S-drop to the left,
        for k in range(80):                                                  #   then a spiral curl (radius R -> 0.45R) curling UP
            t = k / 79.0; e = t * t * (3 - 2 * t)
            pts.append((xs - (xs - xe) * t, ys + (ye - ys) * e))
        cx, cy = xe, ye - R
        for k in range(1, 61):
            u = k / 60.0; a = math.radians(90 + 250 * u); r = R * (1 - 0.55 * u)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        lay = Image.new("L", im.size, 0); ld = ImageDraw.Draw(lay); n = len(pts) - 1
        for k, (x, y) in enumerate(pts):
            u = k / float(n); w = (w0 + (w1 - w0) * min(1.0, u / 0.7)) if u < 0.7 else (w1 - (w1 - 0.6) * (u - 0.7) / 0.3)
            w /= 2.0; ld.ellipse([(x - w) * S, (y - w) * S, (x + w) * S, (y + w) * S], fill=255)
        im.paste(0, mask=lay.filter(ImageFilter.MaxFilter(int(0.9 * S) | 1)))   # thin dark border: lines never touch
        im.paste(255, mask=lay)
    windline(29.0, 2.6, 14.0, 7.2, 2.4, 0.8, 1.9)                           # v19: re-jigged to fill the icon round the rotated arrow
    windline(31.0, 6.4, 10.5, 15.0, 2.9, 0.8, 2.1)
    windline(30.0, 10.4, 6.5, 22.8, 3.5, 0.8, 2.4)
    # the arrow: a thick tapered sweep along the bottom (tail fading), curving up into a big solid head at the right
    lay = Image.new("L", im.size, 0); ld = ImageDraw.Draw(lay)
    ROT = math.radians(-12)                                                  # v20 (user meant CLOCKWISE): the arrow rotated slightly clockwise
    pv = M((1030, 640))
    def rot(p):
        x, y = p[0] - pv[0], p[1] - pv[1]
        return (pv[0] - 2.2 + x * math.cos(ROT) + y * math.sin(ROT), pv[1] - 1.2 - x * math.sin(ROT) + y * math.cos(ROT))
    body = smooth([rot(M(p)) for p in [(720, 806), (900, 790), (1130, 720), (1270, 610), (1335, 480)]], 14); n = len(body) - 1
    for k, (x, y) in enumerate(body):
        u = k / float(n); w = (0.5 + 2.0 * u) / 2.0 + 0.4; v = int(255 * min(1.0, 0.25 + u * 1.5))
        ld.ellipse([(x - w) * S, (y - w) * S, (x + w) * S, (y + w) * S], fill=v)
    (tx, ty), bl, br = rot(M((1355, 385))), rot(M((1160, 487))), rot(M((1490, 565)))
    ld.polygon([(tx * S, ty * S), (bl[0] * S, bl[1] * S), (br[0] * S, br[1] * S)], fill=255)
    im.paste(0, mask=lay.point(lambda v: 255 if v > 0 else 0).filter(ImageFilter.MaxFilter(int(1.1 * S) | 1)))
    paste_max(im, lay)
    return im


def glyph_suspend():
    """Suspend (214, Air tier 3, 2026-10-16): the user's reference art import export/suspend.jpg - a figure arched
    backward, floating - traced across the upper icon, three curling wind streaks beneath holding it aloft (dark gap
    round the body) -> suspend_user_mask.png (generator suspend_mask_build.py)."""
    return _user_mask_glyph("suspend_user_mask.png")


def glyph_staticshield():
    """Static Shield (215) v8 (user 10/16: use the outer shell from the new reference 'static shield general
    inspiration.png', reshaped to follow Stone Skin's outer-shell silhouette; the man unchanged): the reference's
    lightning shell (its man removed) fitted into Stone Skin's aura box by staticshield_mask_build.py ->
    staticshield_shell_mask.png, around Stone Skin's figure (ink 40, 1:1) cut free by a dark gap."""
    fig = ink_component(vanilla_ink(61), (20, 22))                          # v10 (user): Fire Halo's man WITH its detail (grey shading kept),
    fig = ImageChops.offset(fig, 3, 1)                                       #   moved to Stone Skin's placement (+3, +1)
    im = _user_mask_glyph("staticshield_shell_mask.png").copy(); dr = ImageDraw.Draw(im)
    BOLT = [(0.62, 0.0), (0.12, 0.56), (0.46, 0.56), (0.30, 1.0), (0.90, 0.40), (0.55, 0.40), (0.80, 0.0)]
    for (x0, y0), (x1, y1) in (((8.6, 15.5), (11.4, 20.0)), ((8.2, 24.0), (11.0, 28.0)),     # v9 (user): clean inner bolts that
                               ((32.4, 15.5), (29.6, 20.0)), ((32.8, 24.0), (30.0, 28.0))):  #   TOUCH the shell but not the man
        dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy); ux, uy = dx / L, dy / L; px, py = -uy, ux; w = 2.6
        dr.polygon([((x0 + ux * L * by + px * w * (bx - 0.5)) * S, (y0 + uy * L * by + py * w * (bx - 0.5)) * S) for bx, by in BOLT], fill=255)
    figm = fig.point(lambda v: 255 if v > 40 else 0).resize((W * S, H * S), Image.NEAREST)
    im.paste(0, mask=figm.filter(ImageFilter.MaxFilter(int(1.4 * S) | 1)))
    im = ImageChops.lighter(im, fig.resize((W * S, H * S), Image.NEAREST))   # the man's own grey detail, unthresholded
    return im


def glyph_depthsofplenty():
    """Depths of Plenty (217, Earth L2, 2026-10-17; no user reference art): a timbered mine mouth (two posts + a lintel
    over a dark adit) set in a hillside, three stepped rock strata descending beneath it (surface / underground /
    depths), and a heap of gold nuggets spilling out of the adit with three sparkles above it."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    dr.polygon(P([(0.0, 22.0), (6.0, 12.0), (13.0, 7.0), (20.0, 5.6), (27.0, 7.0), (34.0, 12.0), (40.0, 22.0)]), fill=255)   # the hill
    dr.rectangle([10.6 * S, 10.4 * S, 29.4 * S, 13.0 * S], fill=0)                                           # lintel gap
    dr.rectangle([11.4 * S, 10.8 * S, 28.6 * S, 12.6 * S], fill=255)                                         # the lintel beam
    for x in (12.0, 25.2):                                                                                   # the posts
        dr.rectangle([(x - 0.8) * S, 12.6 * S, (x + 3.6) * S, 22.0 * S], fill=0)
        dr.rectangle([x * S, 12.6 * S, (x + 2.8) * S, 22.0 * S], fill=255)
    dr.rectangle([15.6 * S, 13.4 * S, 24.4 * S, 22.0 * S], fill=0)                                           # the dark adit
    for k, (y, inset) in enumerate(((24.0, 2.0), (28.0, 6.0), (32.0, 10.0))):                                # strata stepping down
        dr.rectangle([inset * S, y * S, (40.0 - inset) * S, (y + 2.6) * S], fill=255)
        for xx in range(int(inset + 3), int(40 - inset - 1), 5):                                             # cracks in each band
            dr.line(P([(xx, y), (xx + 1.2, y + 2.6)]), fill=0, width=max(1, int(0.6 * S)))
    for cx, cy, r in ((17.4, 20.6, 1.6), (20.2, 20.0, 1.9), (23.0, 20.8, 1.5), (18.8, 18.0, 1.4), (21.6, 17.8, 1.5), (20.2, 15.6, 1.3)):
        dr.ellipse([(cx - r - 0.5) * S, (cy - r - 0.5) * S, (cx + r + 0.5) * S, (cy + r + 0.5) * S], fill=0)
        dr.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=255)                        # gold nuggets in the adit
    for x, y, r in ((6.0, 3.6, 2.4), (33.6, 4.4, 2.0), (20.0, 1.4, 1.4)):                                    # sparkles
        dr.line(P([(x - r, y), (x + r, y)]), fill=255, width=max(1, int(0.7 * S)))
        dr.line(P([(x, y - r), (x, y + r)]), fill=255, width=max(1, int(0.7 * S)))
    return im


def glyph_tectonic():
    """Tectonic Shift (219, Earth tier 4, 2026-10-17): the user's reference art import export/tectonic shift.jpg - a
    round boulder split by a branching crack, chips and grit flying off it - TRACED -> tectonic_user_mask.png
    (ink < 128; inside the disc the ink is eroded 11 px at full size so the white cracks widen enough to survive
    40x35; the flying debris outside the disc is kept and dilated 4 px; fitted to 320x280 at 97 %, centred)."""
    return _user_mask_glyph("tectonic_user_mask.png")


def glyph_riteseas():
    """Rite of the Seas (221, Water L2, 2026-10-17; reference art import export/rite of the seas.jpg - a tribal sailboat
    with spiral-cut sails, a spiral sun with rays and wavelets under the hull).  The 1:1 trace loses every spiral at
    40x35, so it is REDRAWN in the same style with the cut-outs wide enough to survive: a tall curved mainsail and a
    smaller foresail, each carved with a bold spiral; a pennant streaming from the masthead; a crescent hull with a
    curl at the bow; the spiral sun with short rays (upper right); two wavelets below."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    def bez(p0, p1, p2, n=16):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in [k / (n - 1.0) for k in range(n)]]
    def spiral(cx, cy, r0, turns, w, fill=0, a0=0.0, ry=1.0):
        pts = []; n = int(40 * turns)
        for k in range(n + 1):
            t = k / float(n); a = a0 + t * turns * 2 * math.pi; r = r0 * (1 - 0.85 * t)
            pts.append((cx + r * math.cos(a), cy + ry * r * math.sin(a)))
        dr.line(P(pts), fill=fill, width=max(1, int(w * S)), joint="curve")
    # mainsail: mast foot (19.5, 23) -> masthead (18.5, 2.5), belly bulging left, leech curving down to (26, 22)
    main = bez((18.6, 2.6), (8.5, 12.0), (12.6, 23.2)) + [(19.6, 23.2), (26.4, 22.4)] + bez((26.4, 22.4), (24.0, 11.0), (18.6, 2.6))[1:]
    dr.polygon(P(main), fill=255)
    spiral(18.2, 15.2, 4.6, 1.55, 1.25, a0=0.3)
    # foresail (left): small curved triangle
    fore = bez((11.0, 10.0), (4.0, 15.5), (5.0, 22.6)) + [(11.8, 22.6)] + bez((11.8, 22.6), (10.0, 16.0), (11.0, 10.0))[1:]
    dr.polygon(P(fore), fill=255)
    spiral(8.6, 18.6, 2.4, 1.2, 0.9, a0=2.4)
    # pennant streaming right from the masthead
    dr.line(P(bez((18.8, 3.0), (21.5, 0.6), (24.0, 2.4)) + bez((24.0, 2.4), (25.6, 3.4), (27.6, 1.6))[1:]), fill=255, width=int(1.3 * S), joint="curve")
    # hull: a crescent, a gap line under the sails, a curl at the bow
    dr.line(P([(4.5, 23.6), (34.5, 23.6)]), fill=0, width=int(1.0 * S))
    hull = bez((3.0, 24.6), (8.0, 31.0), (20.0, 30.0)) + bez((20.0, 30.0), (30.0, 29.0), (35.5, 24.2))[1:]         + bez((35.5, 24.2), (27.0, 27.0), (19.0, 26.6))[1:] + bez((19.0, 26.6), (10.0, 26.6), (3.0, 24.6))[1:]
    dr.polygon(P(hull), fill=255)
    spiral(7.6, 27.0, 1.6, 1.0, 0.7, a0=3.6)
    # sun: ring with a spiral inside + short rays (upper right)
    scx, scy, sr = 31.0, 9.0, 4.6
    dr.ellipse([(scx - sr) * S, (scy - sr) * S, (scx + sr) * S, (scy + sr) * S], fill=255)
    spiral(scx, scy, 3.3, 1.35, 0.95, a0=4.0)
    for k in range(9):
        a = math.radians(-160 + k * 30)
        if 60 < (k * 30 - 160) % 360 < 200: continue
        x0, y0 = scx + (sr + 1.0) * math.cos(a), scy + (sr + 1.0) * math.sin(a)
        x1, y1 = scx + (sr + 3.0) * math.cos(a), scy + (sr + 3.0) * math.sin(a)
        dr.line(P([(x0, y0), (x1, y1)]), fill=255, width=max(1, int(0.8 * S)))
    # wavelets under the hull
    for y, x0, x1 in ((31.6, 8.0, 31.0), (33.6, 12.0, 27.0)):
        pts = [(x, y + 0.6 * math.sin((x - x0) / 2.2)) for x in [x0 + (x1 - x0) * k / 30.0 for k in range(31)]]
        dr.line(P(pts), fill=255, width=max(1, int(1.0 * S)))
    return im


def glyph_crashingwave():
    """Crashing Wave (220, Water L1, 2026-10-17): the user's reference art import export/crashing wave.jpg (a curling
    breaking wave with spiral foam crests and a long tail) TRACED -> crashingwave_user_mask.png (fill 0.98; the thin
    white bands inside the ink widened: hull = close 7 px, gaps dilated 2 px at 320x280 so they survive 40x35)."""
    return _user_mask_glyph("crashingwave3_user_mask.png")    # v2 10/17: left tail trimmed to a clean tapered point


def glyph_flashflood():
    """Flash Flood (223, Water L4, 2026-10-17): the user's reference art import export/flash flood (...).jpg edited as its
    file name asks (tmp/flood/mk_icon.py): the lighthouse top inside the storm cloud (white tower, lantern, light beam)
    filled into the cloud, the cloud's flat cut-off bottom rounded into puffs, the lower tower shortened and capped with a
    crenellated parapet (corbel band + 4 merlons) - a storm cloud over a sea tower on its rock, struck by a curling wave
    -> TRACED (trace_ref.py fill 0.97, thicken 2) -> flashflood_user_mask.png."""
    return _user_mask_glyph("flashflood3_user_mask.png")    # v2 10/17: bottom half only (tower from its colour change down) + parapet


def glyph_riteseas2():
    """Rite of the Seas (221) v2 (2026-10-17, user: v1 'looks janky'): redrawn clean at 4x supersampling (smooth curves,
    uniform stroke widths, bold cut-outs that survive 40x35) after art import export/rite of the seas.jpg: a tall curved
    mainsail carved with a bold spiral, a small sail either side of it (dark gaps keep all three separate), a pennant
    at the masthead, a deep solid crescent hull, the spiral sun with six rays and two smooth wavelets."""
    import math
    from PIL import Image, ImageDraw
    K = 4; im = Image.new("L", (W * S * K, H * S * K), 0); dr = ImageDraw.Draw(im)
    U = S * K
    P = lambda pts: [(x * U, y * U) for x, y in pts]
    def bez(p0, p1, p2, n=28):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in [i / n for i in range(n + 1)]]
    def spiral(cx, cy, r0, r1, turns, a0=0.0, n=120):
        return [(cx + (r0 + (r1 - r0) * i / n) * math.cos(a0 + 2 * math.pi * turns * i / n),
                 cy + (r0 + (r1 - r0) * i / n) * math.sin(a0 + 2 * math.pi * turns * i / n)) for i in range(n + 1)]
    def stroke(pts, w, fill):
        dr.line(P(pts), fill=fill, width=max(1, int(w * U)), joint="curve")
        for x, y in (pts[0], pts[-1]):
            dr.ellipse([(x - w / 2) * U, (y - w / 2) * U, (x + w / 2) * U, (y + w / 2) * U], fill=fill)
    # tall mainsail: straight mast edge at x 21, convex leading edge
    dr.polygon(P([(21.0, 2.4)] + bez((21.0, 2.4), (12.2, 11.0), (13.6, 21.8)) + [(21.0, 21.8)]), fill=255)
    stroke(spiral(17.8, 15.0, 0.35, 3.3, 1.6, a0=0.9), 1.1, 0)           # bold spiral carved into it
    # small left sail (gap >= 1 unit from the mainsail's leading edge)
    dr.polygon(P([(11.6, 10.0)] + bez((11.6, 10.0), (7.0, 15.0), (6.6, 21.8)) + [(12.4, 21.8)]), fill=255)
    stroke(bez((10.6, 19.6), (9.0, 17.6), (10.6, 15.6)), 0.9, 0)          # a curl cut into it
    # small jib right of the mast
    dr.polygon(P([(22.4, 7.2)] + bez((22.4, 7.2), (27.8, 14.0), (29.4, 21.8)) + [(22.4, 21.8)]), fill=255)
    # pennant streaming left from the masthead
    dr.polygon(P([(21.0, 1.6)] + bez((21.0, 1.6), (17.0, 0.4), (14.0, 2.0)) + bez((14.0, 2.0), (17.6, 2.2), (21.0, 3.6))), fill=255)
    # deep solid crescent hull
    top = bez((5.6, 23.2), (20.0, 25.4), (34.6, 22.6)); bot = bez((34.6, 22.6), (21.0, 33.4), (5.6, 23.2))
    dr.polygon(P(top + bot[1:]), fill=255)
    # spiral sun with six rays
    cx, cy, r = 33.0, 7.4, 4.5
    dr.ellipse([(cx - r) * U, (cy - r) * U, (cx + r) * U, (cy + r) * U], fill=255)
    stroke(spiral(cx, cy, 0.3, 2.8, 1.35, a0=3.4), 0.95, 0)
    for k in range(6):
        a = math.radians(-160 + k * 42); c, s_ = math.cos(a), math.sin(a)
        stroke([(cx + c * (r + 1.2), cy + s_ * (r + 1.2)), (cx + c * (r + 2.7), cy + s_ * (r + 2.7))], 1.0, 255)
    # two wavelets under the hull
    for y0, x0, x1 in ((31.2, 8.0, 32.0), (33.8, 12.0, 28.0)):
        n = 60; pts = [(x0 + (x1 - x0) * i / n, y0 + 0.65 * math.sin(i / n * 3 * math.pi)) for i in range(n + 1)]
        stroke(pts, 1.0, 255)
    return im.resize((W * S, H * S), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)


def glyph_seaserpent():
    """Summon Sea Serpent (222, Water L3, 2026-10-17): the user's reference art import export/sea serpent.jpg (a coiled
    horned serpent rising from two wave lines) TRACED -> seaserpent_user_mask.png (median 3, ink < 128, watermark row
    cropped, fitted 95 %); the two thin source waves redrawn as two clean 15 px sine bands so they survive 40x35."""
    return _user_mask_glyph("seaserpent_user_mask.png")


def glyph_walloflames():
    """Wall of Flames (226, Fire L3, 2026-10-17; no user reference art): a closed RING of flame tongues seen in
    perspective around an empty centre (the hex the wall encloses): tall tongues along the back arc, a burning
    elliptical ground band, and shorter tongues on the near arc drawn over the band (dark-rimmed so each reads)."""
    from PIL import ImageFilter
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy, rx, ry = 20.0, 24.5, 16.0, 6.6
    def tongue(a, h, w, rim):
        s = math.sin(math.radians(a)); c = math.cos(math.radians(a))
        x = cx + rx * c; y = cy + ry * s
        tmp = Image.new("L", im.size, 0); td = ImageDraw.Draw(tmp)
        pyre_tongue(td, x * S, (y + 0.6) * S, h * S, w * S, lean=0.12 * c, lick=1 if c >= 0 else -1)
        if rim: im.paste(0, mask=tmp.filter(ImageFilter.MaxFilter(int(1.0 * S) | 1)))
        im.paste(255, mask=tmp)
    for a, h in ((180, 11.5), (0, 11.5), (210, 13.5), (330, 13.5), (240, 15.5), (300, 15.5), (270, 16.5)):
        tongue(a, h, 7.0, rim=a in (210, 330, 240, 300, 270))
    band = Image.new("L", im.size, 0); bd = ImageDraw.Draw(band)
    bd.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
    bd.ellipse([(cx - rx + 2.8) * S, (cy - ry + 1.8) * S, (cx + rx - 2.8) * S, (cy + ry - 1.8) * S], fill=0)
    im.paste(0, mask=band.filter(ImageFilter.MaxFilter(int(0.8 * S) | 1)))
    im.paste(255, mask=band)
    dr.ellipse([(cx - rx + 3.6) * S, (cy - ry + 2.4) * S, (cx + rx - 3.6) * S, (cy + ry - 2.4) * S], fill=0)
    for a, h in ((150, 9.0), (30, 9.0), (115, 8.0), (65, 8.0), (90, 7.5)):
        tongue(a, h, 6.4, rim=True)
    return im


def glyph_smokescreen():
    """Smokescreen (225, Fire L2, 2026-10-17): the user's reference art import export/smokescreen (middle right,
    shorten left extension to fit).jpg - the MIDDLE-RIGHT cloud of the sheet (big spiral cloud with an arcing band),
    its long left tail cut at 100 px and tapered to a point over 100..145 px (crop 610,420,1190,770 of the jpg), fitted
    to 320x280 at 97 %, the interior white bands widened 3 px inside the cloud's silhouette (closing 31) so the
    spirals survive 40x35 -> smokescreen_user_mask.png (made by tmp/smoke/mk_icon_smokescreen.py)."""
    return _user_mask_glyph("smokescreen_user_mask.png")


def glyph_pyroclasm():
    """Pyroclasm (227, Fire tier 4, 2026-10-17): the user's reference art import export/pyroclasm.jpg - an erupting
    volcano under a billowing ash plume - TRACED (trace_ref.py fill 0.97) -> pyroclasm_user_mask.png; the cone's white
    cracks widened (ink eroded 2 px) and the plume REDRAWN as eleven clean round puffs + stem with five crescent cuts on
    the top row (a 1:1 trace of the plume's tiny crescents was noise at 40x35)."""
    return _user_mask_glyph("pyroclasm_user_mask.png")


def _smooth_tongue(dr, cx, base_y, h, w, lean=0.0):
    """Wall of Flames v2 flame tongue: a round belly and ONE clean taper to a pointed, slightly swaying tip (no wavy
    edges, no side licks); the trailing side a touch fuller."""
    def half(sign):
        pts = []
        for i in range(25):
            t = i / 24.0
            prof = math.sin(math.pi * min(1.0, 0.30 + t * 0.70)) ** 0.7 * (1 - t) ** 0.9
            ww = w * 0.55 * prof * (1.10 if sign * lean < 0 else 0.92)
            sway = 0.10 * h * math.sin(math.pi * t) * (1 if lean >= 0 else -1) * -0.6
            pts.append((cx + sign * ww + lean * h * t ** 2.2 + sway, base_y - h * t))
        return pts
    l, r = half(-1), half(+1)
    dr.polygon(l + r[::-1], fill=255)


def glyph_walloflames2():
    """Wall of Flames v2 (user 10/17: 'pretty good, just polish up the fire a bit'): the same ring composition (tall
    tongues at the back, the burning ground band, short tongues in front, all dark-rimmed) with every tongue redrawn
    as a clean single-taper flame leaning outward from the centre with a slight sway."""
    from PIL import ImageFilter
    im = canvas()
    cx, cy, rx, ry = 20.0, 24.5, 16.0, 6.6
    def tongue(a, h, w, rim=True):
        c = math.cos(math.radians(a)); s = math.sin(math.radians(a))
        x = cx + rx * c; y = cy + ry * s
        tmp = Image.new("L", im.size, 0); td = ImageDraw.Draw(tmp)
        _smooth_tongue(td, x * S, (y + 0.6) * S, h * S, w * S, lean=0.16 * c)
        if rim: im.paste(0, mask=tmp.filter(ImageFilter.MaxFilter(int(1.0 * S) | 1)))
        im.paste(255, mask=tmp)
    for a, h in ((180, 11.0), (0, 11.0), (210, 13.5), (330, 13.5), (240, 15.5), (300, 15.5), (270, 17.0)):
        tongue(a, h, 6.6, rim=a != 180 and a != 0)
    band = Image.new("L", im.size, 0); bd = ImageDraw.Draw(band)
    bd.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
    bd.ellipse([(cx - rx + 2.8) * S, (cy - ry + 1.8) * S, (cx + rx - 2.8) * S, (cy + ry - 1.8) * S], fill=0)
    im.paste(0, mask=band.filter(ImageFilter.MaxFilter(int(0.8 * S) | 1))); im.paste(255, mask=band)
    ImageDraw.Draw(im).ellipse([(cx - rx + 3.6) * S, (cy - ry + 2.4) * S, (cx + rx - 3.6) * S, (cy + ry - 2.4) * S], fill=0)
    for a, h in ((150, 9.0), (30, 9.0), (115, 8.2), (65, 8.2), (90, 7.6)):
        tongue(a, h, 6.0)
    return im


def _flame3(cx, base_y, h, w, lean=0.0, seed=0):
    """Wall of Flames v3 flame (user 10/17: 'the flames don't look enough like flames'): a real fire silhouette - a tall
    S-curved main tongue whose tip curls over, two shorter side licks peeling off its flanks (leaning outward), a round
    belly at the base, and an inner teardrop cut-out (the hot core) so each flame reads as a flickering hollow tongue."""
    im = Image.new("L", (W * S, H * S), 0); d = ImageDraw.Draw(im)
    def tongue(x0, y0, hh, ww, ln, curl, sgn):
        pts_l, pts_r = [], []
        for i in range(33):
            t = i / 32.0
            prof = math.sin(math.pi * min(1.0, 0.22 + t * 0.78)) ** 0.65 * (1 - t) ** 1.15
            hw = ww * 0.5 * prof
            # S-curved spine: sways one way low, the other way high, the tip curls over by `curl`
            sx = x0 + ln * hh * (0.35 * math.sin(math.pi * t) * sgn + t ** 2.4) + curl * hh * max(0.0, t - 0.72) ** 2 * 9.0
            sy = y0 - hh * t
            pts_l.append((sx - hw, sy)); pts_r.append((sx + hw, sy))
        d.polygon(pts_l + pts_r[::-1], fill=255)
    sg = 1 if seed % 2 else -1
    tongue(cx, base_y, h, w, lean, 0.05 * sg, sg)                                   # the main tongue, curling tip
    side = -1 if seed % 2 == 0 else 1                                               # ONE side lick, alternating side
    tongue(cx + side * w * 0.30, base_y - h * 0.08, h * 0.60, w * 0.66, lean + side * 0.34, side * 0.07, side)
    bw = 0.46 if h >= 12.5 * S else 0.36                                            # round belly (slimmer on small flames)
    d.ellipse([cx - w * bw, base_y - w * bw * 1.05, cx + w * bw, base_y + w * 0.16], fill=255)
    if h < 12.5 * S: return im                                                      # small flames: solid (a core would read as a ring)
    core = Image.new("L", im.size, 0); cd = ImageDraw.Draw(core)                    # the hot core: an inner teardrop
    ch, cw = h * 0.40, w * 0.26
    pts_l, pts_r = [], []
    for i in range(25):
        t = i / 24.0
        prof = math.sin(math.pi * min(1.0, 0.25 + t * 0.75)) ** 0.7 * (1 - t) ** 1.2
        sx = cx + lean * ch * t ** 2 * 1.3; sy = base_y - w * 0.10 - ch * t
        pts_l.append((sx - cw * prof, sy)); pts_r.append((sx + cw * prof, sy))
    cd.polygon(pts_l + pts_r[::-1], fill=255)
    return ImageChops.subtract(im, core)


def glyph_walloflames3():
    """Wall of Flames v3 (user 10/17: 'the flames don't look enough like flames. improve them. keep the 3D circle
    idea'): the same perspective ring - tall flames at the back, the burning ground band, short flames in front, all
    dark-rimmed - with every flame redrawn by _flame3 (S-curved main tongue with a curling tip, two side licks peeling
    outward, round belly, hollow hot core), heights and sway varied around the ring so the silhouette flickers."""
    from PIL import ImageFilter
    im = canvas()
    cx, cy, rx, ry = 20.0, 24.5, 16.0, 6.6
    def flame(a, h, w, k, rim=True):
        c = math.cos(math.radians(a)); s = math.sin(math.radians(a))
        x = cx + rx * c; y = cy + ry * s
        m = _flame3(x * S, (y + 0.6) * S, h * S, w * S, lean=0.20 * c, seed=k)
        if rim: im.paste(0, mask=m.filter(ImageFilter.MaxFilter(int(1.0 * S) | 1)))
        im.paste(255, mask=m)
    for k, (a, h) in enumerate(((180, 11.5), (0, 10.5), (212, 14.0), (328, 13.0), (243, 16.0), (297, 15.0), (270, 18.0))):
        flame(a, h, 7.0, k, rim=a not in (180, 0))
    band = Image.new("L", im.size, 0); bd = ImageDraw.Draw(band)
    bd.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=255)
    bd.ellipse([(cx - rx + 2.8) * S, (cy - ry + 1.8) * S, (cx + rx - 2.8) * S, (cy + ry - 1.8) * S], fill=0)
    im.paste(0, mask=band.filter(ImageFilter.MaxFilter(int(0.8 * S) | 1))); im.paste(255, mask=band)
    ImageDraw.Draw(im).ellipse([(cx - rx + 3.6) * S, (cy - ry + 2.4) * S, (cx + rx - 3.6) * S, (cy + ry - 2.4) * S], fill=0)
    for k, (a, h) in enumerate(((150, 10.0), (30, 9.2), (113, 9.4), (67, 10.0), (90, 8.6))):
        flame(a, h, 5.8, k + 7)
    return im


def glyph_magicmissile():
    """Magic Missile (228, Cosmos L1, 2026-10-17): the user's reference art import export/magic missile.jpg (three
    streaking arcane bolts, the middle one largest) TRACED -> magicmissile_user_mask.png (trace_ref.py 0.97 / 2)."""
    return _user_mask_glyph("magicmissile4_user_mask.png")


def glyph_royalambition():
    """Royal Ambition (230, Cosmos L3, 2026-10-17): the user's reference art import export/royal ambition.jpg - the
    comedy and tragedy masks (favour and disfavour, both doubled) - TRACED (median 5, thr 140, 3x3 open, fit 97 %,
    blur 1.4 / thr 120) -> royalambition_user_mask.png."""
    return _user_mask_glyph("royalambition10_user_mask.png")


def glyph_cityspy():
    """City Spy (229, Cosmos L2, 2026-10-17): the user's reference art import export/city spy.jpg (a hooded watcher,
    white on black) TRACED INVERTED -> cityspy_user_mask.png: inside the hood's silhouette the reference's BLACK is the
    ink (the shadowed face + the gaps between the hood folds), the white hood / rim stay the Cosmos cloud - the white
    lines as ink vanished on the dark Cosmos cloud at 40x35 (tmp\cityspy\icon_preview.png: A white-as-ink, B = this)."""
    return _user_mask_glyph("cityspy2_user_mask.png")


def glyph_essenceshift():
    """Essence Shift (231, Cosmos L4, 2026-10-17): the user's reference art import export/essense shift.jpg - a
    four-point star between the four elements (mountain + pines, cloud + wind, wave, flame) - TRACED (trace_ref.py
    fill 0.99, thicken 1) -> essenceshift_user_mask.png."""
    return _user_mask_glyph("essenceshift3_user_mask.png")


def glyph_reversalspell():
    """Reversal (234, Secret L3, 2026-10-18): the user's reference art import export/reversal.png - a sword and a
    half-dark shield inside two swapping arrows - TRACED -> reversal_user_mask.png (frame cropped, 1 px thickening)."""
    return _user_mask_glyph("reversal_user_mask.png")


def glyph_lucky():
    """Lucky (232, Secret L1 2026-10-18): the user's reference art import export/lucky2.jpg (bold four-leaf clover with
    white veins) TRACED -> lucky_user_mask.png: clover body (veins widened so they survive 40x35) + stem; the outer
    outline ring is dropped (noise at icon size)."""
    return _user_mask_glyph("lucky2_user_mask.png")    # v2 10/18 (user: a bit smaller): the v1 clover scaled 0.87 about its centre


def glyph_transmutation():
    """Transmutation (235, Secret L4, 2026-10-18): after the user's reference art import export/transmutation.jpg (a
    transmutation circle), HAND-REDRAWN simplified so it reads at 40x35: outer ring, inverted triangle, double centre
    ring and three small node circles -> transmutation_user_mask.png."""
    return _user_mask_glyph("transmutation_user_mask.png")


def glyph_mimic():
    """Mimic (233, Secret L2): the user's reference mirror frame (art import export/mimic.jpg, ornate oval with scroll
    work) TRACED -> mimic_frame_mask.png; inside the glass a spell star split down a dashed mirror axis - the left
    half solid, the right half its hollow reflection."""
    im = _user_mask_glyph("mimic_frame_mask.png")
    dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx, cy, R, r = 20.0, 17.6, 7.6, 3.1
    star = []
    for k in range(10):
        a = math.radians(90 + 36 * k); rr = R if k % 2 == 0 else r
        star.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
    left = Image.new("L", im.size, 0); ImageDraw.Draw(left).polygon(P(star), fill=255)
    half = Image.new("L", im.size, 0); ImageDraw.Draw(half).rectangle([0, 0, int((cx - 0.55) * S), H * S], fill=255)
    solid = ImageChops.multiply(left, half)
    ring = Image.new("L", im.size, 0); ImageDraw.Draw(ring).polygon(P(star), fill=255)
    inner = ring.filter(ImageFilter.MinFilter(int(1.3 * S) | 1))
    outline = ImageChops.subtract(ring, inner)
    rhalf = Image.new("L", im.size, 0); ImageDraw.Draw(rhalf).rectangle([int((cx + 0.55) * S), 0, W * S, H * S], fill=255)
    outline = ImageChops.multiply(outline, rhalf)
    im.paste(255, mask=solid); im.paste(255, mask=outline)
    for y0 in (7.4, 11.0, 23.2, 26.8):                                                    # the dashed mirror axis
        dr.line(P([(cx, y0), (cx, y0 + 1.8)]), fill=255, width=int(0.8 * S))
    for x, y in ((15.2, 11.0), (25.8, 26.4)):                                              # two glints on the glass
        dr.line(P([(x - 1.2, y), (x + 1.2, y)]), fill=255, width=int(0.6 * S)); dr.line(P([(x, y - 1.2), (x, y + 1.2)]), fill=255, width=int(0.6 * S))
    return im


def glyph_mimic2():
    """Mimic (233) v2 (2026-10-18, user: "a QUESTION MARK instead of a star"): the traced mirror frame
    (mimic_frame_mask.png) with a bold question mark split down the dashed mirror axis - the left half solid ink, the
    right half its hollow reflection (outline only), like v1's split star; two glints on the glass."""
    im = _user_mask_glyph("mimic_frame_mask.png")
    dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx, cy = 20.0, 17.6
    from PIL import ImageFont
    font = None
    for fn in ("ariblk.ttf", "arialbd.ttf", "georgiab.ttf", "timesbd.ttf"):
        try:
            font = ImageFont.truetype(fn, int(19.5 * S)); break
        except OSError:
            pass
    q = Image.new("L", im.size, 0); qd = ImageDraw.Draw(q)
    if font is not None:
        qd.text((cx * S, cy * S), "?", fill=255, font=font, anchor="mm")
    else:                                                                                  # fallback: drawn ?
        qd.arc([(cx - 4.2) * S, (cy - 8.2) * S, (cx + 4.2) * S, (cy + 0.2) * S], 200, 90, fill=255, width=int(2.4 * S))
        qd.line(P([(cx, cy + 0.2), (cx, cy + 3.4)]), fill=255, width=int(2.4 * S))
        qd.ellipse([(cx - 1.5) * S, (cy + 5.2) * S, (cx + 1.5) * S, (cy + 8.2) * S], fill=255)
    bb = q.getbbox()
    if bb:                                                                                 # centre the glyph's ink on (cx, cy)
        dx = int(cx * S - (bb[0] + bb[2]) / 2); dy = int(cy * S - (bb[1] + bb[3]) / 2)
        q = ImageChops.offset(q, dx, dy)
    im.paste(0, mask=q.filter(ImageFilter.MaxFilter(int(1.2 * S) | 1)))                  # clear glass around the mark
    left = Image.new("L", im.size, 0); ImageDraw.Draw(left).rectangle([0, 0, int((cx - 0.45) * S), H * S], fill=255)
    right = Image.new("L", im.size, 0); ImageDraw.Draw(right).rectangle([int((cx + 0.45) * S), 0, W * S, H * S], fill=255)
    solid = ImageChops.multiply(q, left)
    outline = ImageChops.subtract(q, q.filter(ImageFilter.MinFilter(int(1.7 * S) | 1)))
    outline = ImageChops.multiply(outline, right)
    im.paste(255, mask=solid); im.paste(255, mask=outline)
    bb = q.getbbox()
    top, bot = (bb[1] / S, bb[3] / S) if bb else (8.0, 27.0)
    for y0 in (top - 3.4, bot + 1.2):                                                      # the dashed mirror axis, outside the mark
        if 3.0 < y0 < H - 3.0:
            dr.line(P([(cx, y0), (cx, y0 + 1.8)]), fill=255, width=int(0.8 * S))
    for x, y in ((14.4, 11.0), (26.2, 25.6)):                                              # two glints on the glass
        dr.line(P([(x - 1.2, y), (x + 1.2, y)]), fill=255, width=int(0.6 * S)); dr.line(P([(x, y - 1.2), (x, y + 1.2)]), fill=255, width=int(0.6 * S))
    return im


def glyph_mimic3():
    """Mimic (233) v3 (2026-10-18, user: "the question mark should be SOLID but is otherwise good - just fill it in"):
    v2's traced mirror frame and bold question mark, now solid ink in both halves; the dashed mirror axis above and
    below the mark and the two glints on the glass are kept."""
    im = _user_mask_glyph("mimic_frame_mask.png")
    dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx, cy = 20.0, 17.6
    from PIL import ImageFont
    font = None
    for fn in ("ariblk.ttf", "arialbd.ttf", "georgiab.ttf", "timesbd.ttf"):
        try:
            font = ImageFont.truetype(fn, int(19.5 * S)); break
        except OSError:
            pass
    q = Image.new("L", im.size, 0); qd = ImageDraw.Draw(q)
    if font is not None:
        qd.text((cx * S, cy * S), "?", fill=255, font=font, anchor="mm")
    else:                                                                                  # fallback: drawn ?
        qd.arc([(cx - 4.2) * S, (cy - 8.2) * S, (cx + 4.2) * S, (cy + 0.2) * S], 200, 90, fill=255, width=int(2.4 * S))
        qd.line(P([(cx, cy + 0.2), (cx, cy + 3.4)]), fill=255, width=int(2.4 * S))
        qd.ellipse([(cx - 1.5) * S, (cy + 5.2) * S, (cx + 1.5) * S, (cy + 8.2) * S], fill=255)
    bb = q.getbbox()
    if bb:                                                                                 # centre the glyph's ink on (cx, cy)
        dx = int(cx * S - (bb[0] + bb[2]) / 2); dy = int(cy * S - (bb[1] + bb[3]) / 2)
        q = ImageChops.offset(q, dx, dy)
    im.paste(0, mask=q.filter(ImageFilter.MaxFilter(int(1.2 * S) | 1)))                  # clear glass around the mark
    im.paste(255, mask=q)                                                                  # v3: the whole mark solid
    bb = q.getbbox()
    top, bot = (bb[1] / S, bb[3] / S) if bb else (8.0, 27.0)
    for y0 in (top - 3.4, bot + 1.2):                                                      # the dashed mirror axis, outside the mark
        if 3.0 < y0 < H - 3.0:
            dr.line(P([(cx, y0), (cx, y0 + 1.8)]), fill=255, width=int(0.8 * S))
    for x, y in ((14.4, 11.0), (26.2, 25.6)):                                              # two glints on the glass
        dr.line(P([(x - 1.2, y), (x + 1.2, y)]), fill=255, width=int(0.6 * S)); dr.line(P([(x, y - 1.2), (x, y + 1.2)]), fill=255, width=int(0.6 * S))
    return im


def glyph_threads3():
    """Thousand Threads (335) v4 (2026-10-18, user: good, but shorter bottom legs - they touch the bottom edge - and a
    SKULL for the body instead of the eye): v3's trace (thousandthreads_user_mask.png) with everything below icon
    y 27 squashed vertically x0.9 (leg tips now end at y 33, ~1.5 px off the edge, same curve), the abdomen's eye +
    crown-spike cut-outs filled solid and a skull cut out of it instead (cranium 8.8 px wide, sockets / nasal cavity /
    two tooth gaps as ink; the crown spikes are dropped - no room beside the skull at 40x35) ->
    thousandthreads2_user_mask.png (generator: make_masks_miracle2_threads2.py in the job scratch)."""
    return _user_mask_glyph("thousandthreads2_user_mask.png")


def glyph_mendwalls():
    """Mend Walls (216) v2 (2026-10-17, user: "make the wall broken or cracked and get rid of the falling bricks. add a
    symbol above the wall that is a smaller version of the remedy icon"): the crenellated brick wall with a ragged
    breach knocked out of its top-middle, a broken-off merlon stump and jagged cracks running down through the
    courses; above it, floating over the breach, Remedy's cross (vanilla SpellIcn 84, pfs key 45) at ~12 px."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    x0, x1, top, bot = 3.0, 37.0, 21.0, 34.0
    dr.rectangle([x0 * S, top * S, x1 * S, bot * S], fill=255)                                               # the wall body
    for cx, h in ((3.0, 3.6), (10.0, 3.6), (31.0, 3.6)):                                                     # merlons (a breach between 10 and 31)
        dr.rectangle([cx * S, (top - h) * S, (cx + 5.6) * S, top * S], fill=255)
    dr.polygon(P([(24.0, top), (29.6, top), (29.6, top - 1.6), (28.0, top - 2.4), (26.4, top - 1.0), (24.0, top - 1.8)]), fill=255)   # a broken merlon stump
    lw = max(1, int(1.0 * S))
    for k, y in enumerate((25.2, 29.6)):                                                                # mortar courses
        dr.line(P([(x0, y), (x1, y)]), fill=0, width=lw)
        off = 0.0 if k % 2 else 3.4
        for xx in range(int(x0 + off + 3), int(x1), 8):
            y1 = min(y + 4.4, bot)
            dr.line(P([(xx, y), (xx, y1)]), fill=0, width=lw)
    for xx in (7.0, 34.0):                                                                             # top course joints
        dr.line(P([(xx, top), (xx, 25.2)]), fill=0, width=lw)
    breach = [(15.4, top - 0.2), (23.4, top - 0.2), (22.6, 22.6), (21.0, 24.0), (20.6, 26.2), (18.6, 25.0), (17.2, 26.6), (16.4, 23.4)]
    dr.polygon(P(breach), fill=0)                                                                             # the ragged breach
    cw = max(1, int(1.25 * S))
    for pts in (((20.6, 26.0), (21.8, 28.2), (20.4, 30.2), (21.6, 33.0)),                                    # cracks spreading from the breach
                ((17.2, 26.4), (15.6, 28.6), (16.6, 30.0), (14.4, 32.6)),
                ((5.0, top), (6.4, 23.2), (5.4, 25.6), (7.2, 27.4)),
                ((36.0, 26.0), (33.8, 27.6), (34.8, 29.4), (32.6, 31.0))):
        dr.line(P(pts), fill=0, width=cw, joint="curve")
    for bx, by in ((12.0, 34.0), (27.6, 34.0)):                                                              # chips knocked out of the base course
        dr.polygon(P([(bx - 1.6, by + 0.2), (bx - 0.8, by - 1.8), (bx + 1.0, by - 1.4), (bx + 1.8, by + 0.2)]), fill=0)
    cross = vanilla_ink(84).point(lambda v: 255 if v > 100 else 0)                                           # Remedy's cross, smaller
    bb = cross.getbbox(); cross = cross.crop(bb)
    cross = cross.resize((cross.width * S // 2, cross.height * S // 2), Image.NEAREST)               # v4: exactly half size (Remedy's 24x23 -> 12 x 11.5 px)
    cx0 = int(20.0 * S - cross.width / 2); cy0 = int(6.4 * S)                                         # v4: centred on the icon (x 20 = the canvas middle; v3 used 19.4)
    halo = Image.new("L", im.size, 0); halo.paste(cross, (cx0, cy0))
    im.paste(0, mask=halo.filter(ImageFilter.MaxFilter(int(1.4 * S) | 1)))                                    # a clear rim so it reads apart from the merlons
    im.paste(255, mask=halo)
    return im



def glyph_mendwalls_v1():
    """Mend Walls (216, Earth L1, 2026-10-17; no user reference art): a crenellated stretch of city wall in brick courses,
    a breach notch knocked out of its top-middle, and three stone blocks flying back into the gap (motion streaks
    behind them, the lowest already settling in), a few mortar-dust sparks around the notch."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    x0, x1, top, bot = 3.0, 37.0, 17.0, 33.5
    dr.rectangle([x0 * S, top * S, x1 * S, bot * S], fill=255)                                               # the wall body
    for cx in (3.0, 10.0, 24.0, 31.0):                                                                        # merlons (a breach between 10 and 24)
        dr.rectangle([cx * S, (top - 4.0) * S, (cx + 5.6) * S, top * S], fill=255)
    dr.polygon(P([(14.6, top - 0.2), (25.4, top - 0.2), (24.0, 22.4), (21.2, 23.6), (18.4, 21.8), (15.8, 22.8)]), fill=0)   # the breach notch
    lw = max(1, int(0.75 * S))
    for k, y in enumerate((21.2, 25.4, 29.6)):                                                                # mortar courses
        dr.line(P([(x0, y), (x1, y)]), fill=0, width=lw)
        off = 0.0 if k % 2 else 3.4
        for xx in range(int(x0 + off + 2), int(x1), 7):
            y1 = y + 4.2 if y + 4.2 < bot else bot
            dr.line(P([(xx, y), (xx, y1)]), fill=0, width=lw)
    for xx in (5.6, 12.6, 26.6, 33.6):                                                                        # top course joints
        dr.line(P([(xx, top), (xx, 21.2)]), fill=0, width=lw)
    dr.polygon(P([(14.6, top - 0.2), (25.4, top - 0.2), (24.0, 22.4), (21.2, 23.6), (18.4, 21.8), (15.8, 22.8)]), fill=0)   # (re-cut after the joints)
    for bx, by, w_, h_, a in ((17.0, 18.2, 5.2, 3.6, -8), (19.6, 9.0, 4.6, 3.2, 14), (12.2, 3.0, 4.0, 2.8, -20)):   # flying blocks (the lowest settling)
        cxb, cyb = bx + w_ / 2, by + h_ / 2; r = math.radians(a)
        pts = [(cxb + dx * math.cos(r) - dy * math.sin(r), cyb + dx * math.sin(r) + dy * math.cos(r))
               for dx, dy in ((-w_ / 2, -h_ / 2), (w_ / 2, -h_ / 2), (w_ / 2, h_ / 2), (-w_ / 2, h_ / 2))]
        dr.polygon(P([(x + 0.9, y + 0.9) for x, y in pts]), fill=0)                                           # cut a thin gap below it
        dr.polygon(P(pts), fill=255)
    for (ax, ay), (bx2, by2) in (((24.6, 5.0), (29.4, 1.2)), ((25.2, 8.4), (30.6, 5.0)), ((17.0, 0.6), (21.0, 0.2)), ((15.6, 6.8), (19.0, 6.0))):   # motion streaks
        dr.line(P([(ax, ay), (bx2, by2)]), fill=255, width=max(1, int(0.8 * S)))
    for x, y in ((9.0, 9.6), (28.0, 13.2), (6.0, 5.0), (33.4, 8.6)):                                          # dust sparks
        dr.line(P([(x - 1.2, y), (x + 1.2, y)]), fill=255, width=max(1, int(0.6 * S)))
        dr.line(P([(x, y - 1.2), (x, y + 1.2)]), fill=255, width=max(1, int(0.6 * S)))
    return im


def glyph_steadfast():
    """Steadfast (218, Earth tier 3): art import export/steadfast.jpg - a crested hoplite behind his round shield,
    spear levelled - TRACED -> steadfast_user_mask.png (thresholded, cropped, stretched to fill 312x240, lines
    thickened MaxFilter 5 so the spear shaft and shield rims survive at 40x35)."""
    return _user_mask_glyph("steadfast5_user_mask.png")    # v5 10/17: v4 with the helmet top as ONE clean ellipse arc (brow -> back; tmp\stead5\mk_mask5.py 177 73 42 37 73) - v4's separate dome read as lumps



def glyph_frenzy():
    """Frenzied Charge v21 (user: v20's MOUTH is really good, the rest worse - refer again to the source image): the
    traced reference (frenzy_user_mask.png, which the user had called pretty good) for the hair, brows, squeezed eyes,
    nose and creases, CLIPPED to v20's messy swept hair-spike silhouette + face shape (so the hair keeps a spiky edge
    instead of a heavy black block), with v20's hand-drawn screaming mouth and teeth drawn over the traced mouth."""
    P = lambda pts: [(x * S, y * S) for x, y in pts]
    rnd = random.Random(3917); hair = []; k = 0; t = 0.0
    while t < 1.0:                                                                                           # v20's swept hair silhouette
        a = math.radians(160 + 220 * t)
        if k % 2:
            sw = 0.45 * math.sin(a + math.pi / 2); r = 11.8 + rnd.uniform(1.6, 6.0) * (1.25 if 200 < math.degrees(a) < 300 else 0.9); a2 = a - sw
        else:
            r = 11.4 + rnd.uniform(-0.4, 0.8); a2 = a
        hair.append((20.4 + r * math.cos(a2) * 1.05, 16.0 + r * math.sin(a2) * 1.05)); t += rnd.uniform(0.025, 0.05); k += 1
    hair += [(30.6, 26.0), (27.6, 29.0), (13.2, 29.0), (10.2, 26.0)]
    face = _fz_bez((11.4, 12.4), (20.4, 3.0), (29.4, 12.4)) + _fz_bez((29.4, 12.4), (30.6, 30.0), (20.4, 35.6))[1:] + _fz_bez((20.4, 35.6), (10.2, 30.0), (11.4, 12.4))[1:]
    base = Image.open(FRENZY_MASK).convert("L").resize((W * S, H * S), Image.NEAREST)
    clip = Image.new("L", (W * S, H * S), 0); cd = ImageDraw.Draw(clip); cd.polygon(P(hair), fill=255); cd.polygon(P(face), fill=255)
    im = Image.new("L", (W * S, H * S), 0); im.paste(base, (0, 0), clip); dr = ImageDraw.Draw(im)
    # v22 (user: top teeth slightly shorter, raise the bottom of the mouth / teeth - it is open a bit too wide): the
    # traced mouth below the new jaw line is cleared first (it reached lower), then the shorter mouth is drawn
    big_mouth = _fz_bez((15.6, 23.8), (20.4, 21.6), (25.2, 23.8)) + _fz_bez((25.2, 23.8), (25.6, 34.0), (20.4, 34.4))[1:] + _fz_bez((20.4, 34.4), (15.2, 34.0), (15.6, 23.8))[1:]
    dr.polygon(P(big_mouth), fill=0)
    mouth = _fz_bez((15.6, 23.8), (20.4, 21.6), (25.2, 23.8)) + _fz_bez((25.2, 23.8), (25.5, 32.2), (20.4, 32.6))[1:] + _fz_bez((20.4, 32.6), (15.3, 32.2), (15.6, 23.8))[1:]
    dr.polygon(P([(20.4 + (x - 20.4) * 1.05, y + 2.0) for x, y in mouth]), fill=255)                          # v23: a dark border below the mouth
    dr.polygon(P(mouth), fill=255)
    for k in range(4):                                                                                       # upper teeth, shorter
        x = 16.6 + k * 1.95; yy = 23.6 - 0.4 * (1 - abs(k - 1.5) / 1.5)
        dr.polygon(P([(x, yy), (x + 1.6, yy), (x + 1.4, 25.0), (x + 0.2, 25.0)]), fill=0)
    for k in range(3):                                                                                       # lower teeth, raised
        x = 17.6 + k * 1.95
        dr.polygon(P([(x + 0.2, 29.6), (x + 1.4, 29.6), (x + 1.6, 31.3), (x, 31.3)]), fill=0)
    return im


def glyph_implosion():
    """Implosion v6 (user: an EXPLOSION instead of the mushroom cloud, and the circles more like the GFX - particles):
    a jagged explosion burst at the centre (irregular star, a clear inner flash, a solid core) inside the in-game
    vacuum ring - loose particles on flattened ellipses, each its own small mote with a short comet tail, scattered a
    little off the orbit, sized by depth (back half small and behind the burst, front half larger and over it)."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 18.0; rnd = random.Random(3896)
    P = lambda pts: [(x * S, y * S) for x, y in pts]
    def disc(x, y, r, fill=255): dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)
    motes = []
    for rx, ry, n in ((17.2, 8.2, 26), (11.6, 5.4, 16)):
        for k in range(n):
            a = 2 * math.pi * k / n + rnd.uniform(-0.1, 0.1); j = rnd.uniform(-1.3, 1.3)
            if rnd.random() < 0.15: continue
            motes.append((a, rx + j, ry + j * 0.45, rnd.uniform(0.7, 1.3)))
    def draw_motes(front):
        for a, rx, ry, sz in motes:
            sa = math.sin(a)
            if (sa > 0) != front: continue
            depth = 0.5 + 0.5 * sa; d = (0.42 + 0.55 * depth) * sz
            x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
            pts = [(cx + rx * math.cos(a - 0.2 * m / 4.0), cy + ry * math.sin(a - 0.2 * m / 4.0)) for m in range(4, -1, -1)]
            _fz_taper(dr, pts, 0.1, d * 1.2)                                                                 # short comet tail
            disc(x, y, d)
    draw_motes(False)
    def boom(n, rlo, rhi, ilo, ihi, seed):                                                                  # comic 'boom' shape: chunky irregular jags
        rr = random.Random(seed); pts = []; a = -math.pi / 2
        for k in range(n):
            step = 2 * math.pi / n * rr.uniform(0.75, 1.25)
            r = rr.uniform(rlo, rhi); pts.append((cx + r * math.cos(a), cy - 1.0 + r * math.sin(a) * 0.92))
            a += step / 2; r = rr.uniform(ilo, ihi); pts.append((cx + r * math.cos(a), cy - 1.0 + r * math.sin(a) * 0.92))
            a += step / 2
        return pts
    outer = boom(11, 8.4, 10.4, 5.6, 6.8, 71)
    dr.polygon(P([(cx + (x - cx) * 1.14, cy - 1.0 + (y - cy + 1.0) * 1.14) for x, y in outer]), fill=0)  # clear margin
    dr.polygon(P(outer), fill=255)                                                                            # the explosion
    dr.polygon(P(boom(9, 5.0, 6.2, 3.2, 4.0, 72)), fill=0)                                                   # clear inner flash
    dr.polygon(P(boom(7, 2.5, 3.3, 1.5, 2.0, 73)), fill=255)                                                 # solid jagged core
    draw_motes(True)
    return im


def _steam_curl(dr, x, y, r, turns=1.2, w0=1.4, w1=0.4, side=1):
    """A rising steam wisp: a short upward S then a small curl at the top."""
    pts = []
    for k in range(13):
        t = k / 12.0; pts.append((x + side * 1.2 * math.sin(t * math.pi * 1.6), y - 2.6 * r * t))
    ex, ey = pts[-1]
    for k in range(1, 14):
        t = k / 13.0; a = math.pi + side * turns * math.pi * t; rr = r * (1 - 0.55 * t)
        pts.append((ex + r + rr * math.cos(a) - r, ey + rr * math.sin(a) * -1 if False else ey - rr * math.sin(a) * side))
    _fz_taper(dr, pts, w0, w1)


def glyph_bloodboil():
    """Blood Boil (404, Fire/Water tier 1): a big drop of blood BOILING - clear bubbles inside it, more bubbles
    bursting off its top, and two steam wisps curling up from it."""
    im = canvas(); dr = ImageDraw.Draw(im)
    teardrop(dr, 20 * S, 23.0 * S, 9.4 * S, tip_up=True)                                                    # the drop
    for x, y, r in ((16.4, 25.6, 2.0), (22.6, 21.8, 1.6), (21.4, 27.6, 1.3), (17.8, 20.4, 1.1), (24.4, 26.2, 0.9)):
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=0)                         # boiling bubbles (clear)
    for x, y, r in ((12.4, 9.0, 1.5), (27.0, 7.4, 1.8), (30.0, 12.4, 1.0), (9.4, 13.6, 0.9)):
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], outline=255, width=int(0.8 * S))  # bubbles bursting off it
    _fz_taper(dr, [(16.0, 6.6), (14.6, 4.6), (16.2, 2.6), (14.8, 0.8)], 1.3, 0.4)                             # steam wisps
    _fz_taper(dr, [(24.2, 4.8), (25.6, 3.0), (24.2, 1.2)], 1.1, 0.4)
    return im


def glyph_scald_v1():
    """Scald (405, Fire/Water tier 2): a burst of scalding steam erupting from a crack in the ground - a cracked
    ground line, a column of billowing steam puffs widening as it rises (clear folds between them), and hot droplets
    spitting out to the sides."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def disc(x, y, r, fill=255): dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)
    dr.line([(1 * S, 31.0 * S), (14 * S, 31.0 * S)], fill=255, width=int(1.6 * S)); dr.line([(26 * S, 31.0 * S), (39 * S, 31.0 * S)], fill=255, width=int(1.6 * S))   # ground
    dr.polygon([(14 * S, 30.2 * S), (17.0 * S, 33.8 * S), (19.0 * S, 31.6 * S), (21.0 * S, 34.0 * S), (23.4 * S, 31.4 * S), (26 * S, 30.2 * S), (26 * S, 31.8 * S), (14 * S, 31.8 * S)], fill=255)   # the crack
    puffs = ((20.0, 26.0, 3.0), (18.2, 21.6, 3.6), (22.4, 18.4, 4.0), (17.6, 14.0, 4.6), (23.6, 10.4, 5.0), (19.0, 6.2, 5.2))
    for x, y, r in puffs: disc(x, y, r + 0.6, 0)
    for x, y, r in puffs: disc(x, y, r)                                                                    # the steam column
    for x, y, r in puffs[1:]: dr.arc([(x - r * 0.7) * S, (y - r * 0.7) * S, (x + r * 0.7) * S, (y + r * 0.7) * S], 200, 300, fill=0, width=int(0.7 * S))   # folds
    for x, y, r in ((9.6, 22.0, 0.9), (7.0, 17.0, 0.7), (31.0, 21.0, 0.9), (33.6, 15.6, 0.7), (11.6, 27.2, 0.7), (29.0, 27.0, 0.7)):
        disc(x, y, r)                                                                                       # spitting droplets
    return im


def glyph_scald_v2():
    """Scald (405) v2 (user: a really good idea, but the 'bubbles' should look more like STEAM): the cracked ground and
    the spitting droplets of v1, but the column is now steam - three thick wavy wisps rising out of the crack, fanning
    apart as they climb, tapering and curling over at the top (the middle one tallest), with a few thin wisps between."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def disc(x, y, r, fill=255): dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)
    dr.line([(1 * S, 31.0 * S), (14 * S, 31.0 * S)], fill=255, width=int(1.6 * S)); dr.line([(26 * S, 31.0 * S), (39 * S, 31.0 * S)], fill=255, width=int(1.6 * S))
    dr.polygon([(14 * S, 30.2 * S), (17.0 * S, 33.8 * S), (19.0 * S, 31.6 * S), (21.0 * S, 34.0 * S), (23.4 * S, 31.4 * S), (26 * S, 30.2 * S), (26 * S, 31.8 * S), (14 * S, 31.8 * S)], fill=255)
    def wisp(x0, lean, h, amp, curl, w0, w1, ph):
        pts = []
        for k in range(24):
            t = k / 23.0; pts.append((x0 + lean * t * h + amp * math.sin(t * math.pi * 2.2 + ph) * (0.3 + t), 29.6 - h * t))
        ex, ey = pts[-1]; side = 1 if curl > 0 else -1; cr = abs(curl)
        for k in range(1, 12):
            t = k / 11.0; a = math.pi * (1 if side > 0 else 0) - side * 1.3 * math.pi * t; r = cr * (1 - 0.5 * t)
            pts.append((ex + side * cr + r * math.cos(a), ey - r * math.sin(a) * 0.9))
        _fz_taper(dr, pts, w0, w1)
    wisp(20.0, 0.0, 22.0, 3.0, 3.0, 3.0, 0.8, 0.0)                                                         # the tall middle wisp
    wisp(17.6, -0.32, 17.0, 2.4, -2.6, 2.4, 0.7, 1.7)                                                      # left wisp, leaning out
    wisp(22.6, 0.34, 15.0, 2.4, 2.4, 2.3, 0.7, 3.1)                                                        # right wisp, leaning out
    _fz_taper(dr, [(15.6, 26.0), (13.4, 22.0), (14.6, 18.6), (12.8, 15.4)], 1.0, 0.3)                       # thin wisps between
    _fz_taper(dr, [(24.6, 26.4), (26.6, 22.6), (25.4, 19.4), (27.0, 16.6)], 1.0, 0.3)
    for x, y, r in ((7.6, 22.0, 0.9), (5.4, 17.0, 0.7), (32.6, 21.0, 0.9), (35.0, 15.6, 0.7), (10.0, 27.2, 0.7), (30.4, 27.0, 0.7)):
        disc(x, y, r)
    return im


def glyph_scald():
    """Scald (405) v3 (user: v2's wisps look bad - restore the v1 'bubbles' but make them like the DISEASE CLOUD icon:
    particles, not solid): v1's cracked ground, droplets and column of six steam puffs, the puffs now STIPPLED -
    grains on a jittered grid, denser toward each puff's centre and thinning at its rim, so the column reads as a
    particle cloud."""
    im = canvas(); dr = ImageDraw.Draw(im); rnd = random.Random(4052)
    def disc(x, y, r, fill=255): dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill)
    dr.line([(1 * S, 31.0 * S), (14 * S, 31.0 * S)], fill=255, width=int(1.6 * S)); dr.line([(26 * S, 31.0 * S), (39 * S, 31.0 * S)], fill=255, width=int(1.6 * S))
    dr.polygon([(14 * S, 30.2 * S), (17.0 * S, 33.8 * S), (19.0 * S, 31.6 * S), (21.0 * S, 34.0 * S), (23.4 * S, 31.4 * S), (26 * S, 30.2 * S), (26 * S, 31.8 * S), (14 * S, 31.8 * S)], fill=255)
    puffs = ((20.0, 26.0, 3.0), (18.2, 21.6, 3.6), (22.4, 18.4, 4.0), (17.6, 14.0, 4.6), (23.6, 10.4, 5.0), (19.0, 6.2, 5.2))
    step = 0.95; y = 0.6; row = 0
    while y < 29.5:
        x = 0.6 + (step / 2 if row % 2 else 0)
        while x < W:
            jx, jy = x + rnd.uniform(-0.25, 0.25), y + rnd.uniform(-0.25, 0.25)
            dn = min(math.hypot(jx - px, jy - py) / pr for px, py, pr in puffs)                      # 0 = a puff centre, 1 = its rim
            if dn < 1.0 and rnd.random() < 0.28 + 0.8 * dn ** 3:                                        # v3b: rims dense (each billow's outline reads), centres sparse
                d = 0.34 + 0.16 * dn + rnd.uniform(-0.04, 0.04)
                disc(jx, jy, d)
            x += step
        y += step * 0.88; row += 1
    for x, y, sd, L in ((9.4, 22.0, -1, 2.6), (6.8, 16.6, -1, 2.2), (31.2, 21.0, 1, 2.6), (33.8, 15.4, 1, 2.2), (11.4, 27.4, -1, 1.8), (29.2, 27.2, 1, 1.8)):
        # v4 (user: the side particles -> small short CURVED lines): a little rising steam squiggle each
        pts = [(x + sd * 0.7 * math.sin(t * math.pi * 1.4), y - L * t) for t in [k / 6.0 for k in range(7)]]
        _fz_taper(dr, pts, 0.9, 0.35)
    return im


def glyph_steampower():
    """Steam Power (406, Fire/Water tier 3): a big cog (teeth, a clear ring, a solid hub) with a steam pipe at its
    side venting billowing steam puffs up and away."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy, R = 15.5, 21.0, 9.0
    teeth = []
    for k in range(20):
        a = 2 * math.pi * k / 20; r = R + 2.4 if k % 2 == 0 else R
        for da in (-0.13, 0.13): teeth.append((cx + r * math.cos(a + da), cy + r * math.sin(a + da)))
    dr.polygon([(x * S, y * S) for x, y in teeth], fill=255)                                               # the cog
    dr.ellipse([(cx - 5.4) * S, (cy - 5.4) * S, (cx + 5.4) * S, (cy + 5.4) * S], fill=0)
    dr.ellipse([(cx - 3.0) * S, (cy - 3.0) * S, (cx + 3.0) * S, (cy + 3.0) * S], fill=255)                  # hub
    dr.ellipse([(cx - 1.0) * S, (cy - 1.0) * S, (cx + 1.0) * S, (cy + 1.0) * S], fill=0)
    dr.rectangle([27.0 * S, 18.0 * S, 30.6 * S, 33.0 * S], fill=255)                                       # the steam pipe
    dr.rectangle([26.0 * S, 16.6 * S, 31.6 * S, 18.6 * S], fill=255)
    for x, y, r in ((29.0, 13.0, 2.6), (31.4, 8.6, 3.2), (27.6, 4.6, 3.4), (34.6, 4.0, 2.6)):
        dr.ellipse([(x - r - 0.6) * S, (y - r - 0.6) * S, (x + r + 0.6) * S, (y + r + 0.6) * S], fill=0)
    for x, y, r in ((29.0, 13.0, 2.6), (31.4, 8.6, 3.2), (27.6, 4.6, 3.4), (34.6, 4.0, 2.6)):
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)                          # steam puffs
    return im


def glyph_direwolf_v1():
    """Summon Dire Wolf (332, Earth/Death tier 1): a snarling wolf head in profile facing left - pricked ears, a heavy
    brow, a long muzzle with the jaws open on bared fangs, a ruff of fur at the neck; eye and jaw gap cut out."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    head = [(30.0, 33.0), (34.0, 26.0), (35.0, 18.0), (31.6, 8.4), (30.4, 2.4), (27.0, 7.2), (24.6, 4.2), (22.4, 9.4),
            (16.6, 11.4), (10.0, 13.6), (3.4, 15.4), (2.4, 17.0), (4.6, 18.4), (11.0, 18.6), (12.0, 19.6), (5.6, 22.4),
            (4.4, 24.0), (7.4, 24.8), (14.6, 23.2), (18.6, 25.6), (21.4, 30.2), (24.0, 33.0)]
    dr.polygon(P(head), fill=255)
    for k in range(5):                                                                                      # neck ruff tufts
        y = 21.0 + k * 2.6; dr.polygon(P([(33.6, y), (38.4, y + 1.2 + k * 0.2), (33.0, y + 2.4)]), fill=255)
    dr.polygon(P([(18.6, 13.2), (22.6, 13.4), (21.4, 15.0), (18.8, 14.8)]), fill=0)                          # eye
    dr.polygon(P([(6.0, 22.4), (12.0, 19.8), (11.0, 21.4)]), fill=0)                                         # the jaw gap
    dr.line(P([(26.0, 10.0), (28.2, 6.0)]), fill=0, width=int(0.8 * S))                                      # inner ear line
    return im


def glyph_rotaway_v1():
    """Rot Away (333, Earth/Death tier 2): a wooden cartwheel (a machine) rotting apart - rim broken in two places,
    a missing spoke, rot dripping off the bottom in long drops, and three flies buzzing over it."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy, R = 19.0, 15.5, 11.0
    dr.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], outline=255, width=int(2.6 * S))      # rim
    for a0, a1 in ((40, 62), (205, 222)):                                                                    # broken rim gaps
        dr.arc([(cx - R - 1) * S, (cy - R - 1) * S, (cx + R + 1) * S, (cy + R + 1) * S], a0, a1, fill=0, width=int(4.0 * S))
    for k in range(8):                                                                                       # spokes (one missing)
        if k == 2: continue
        a = math.radians(k * 45 + 10)
        dr.line([(cx * S, cy * S), ((cx + R * 0.95 * math.cos(a)) * S, (cy + R * 0.95 * math.sin(a)) * S)], fill=255, width=int(1.5 * S))
    dr.ellipse([(cx - 2.8) * S, (cy - 2.8) * S, (cx + 2.8) * S, (cy + 2.8) * S], fill=255)                   # hub
    dr.ellipse([(cx - 1.0) * S, (cy - 1.0) * S, (cx + 1.0) * S, (cy + 1.0) * S], fill=0)
    for x, L in ((13.0, 5.0), (18.0, 6.6), (23.6, 4.2)):                                                     # rot dripping
        teardrop(dr, x * S, (cy + R + L) * S, 1.1 * S, tip_up=True)
        dr.line([(x * S, (cy + R) * S), (x * S, (cy + R + L - 1) * S)], fill=255, width=int(1.0 * S))
    for x, y in ((31.0, 4.0), (35.4, 7.6), (33.6, 12.0)):                                                    # flies
        dr.ellipse([(x - 0.8) * S, (y - 0.6) * S, (x + 0.8) * S, (y + 0.6) * S], fill=255)
        dr.ellipse([(x - 1.2) * S, (y - 1.6) * S, (x - 0.2) * S, (y - 0.5) * S], outline=255, width=int(0.4 * S))
        dr.ellipse([(x + 0.2) * S, (y - 1.6) * S, (x + 1.2) * S, (y - 0.5) * S], outline=255, width=int(0.4 * S))
    return im


def glyph_werewolf_v1():
    """Summon Werewolf (334, Earth/Death tier 3): a werewolf's head and shoulders in profile HOWLING up at a crescent
    moon - muzzle raised, jaws open, shaggy fur jutting at the back; the moon top-right."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    dr.ellipse([27.0 * S, 1.0 * S, 37.0 * S, 11.0 * S], fill=255); dr.ellipse([24.6 * S, -0.4 * S, 34.2 * S, 9.0 * S], fill=0)   # crescent moon
    body = [(2.0, 35.0), (3.6, 26.0), (6.4, 21.4), (4.0, 19.6), (8.0, 18.4), (6.6, 15.6), (10.6, 15.0), (12.0, 11.6),
            (14.6, 8.6), (13.6, 4.4), (16.4, 7.0), (18.4, 5.8), (21.0, 3.0), (23.4, 2.4), (22.4, 5.6), (24.6, 7.0),
            (21.6, 9.0), (25.4, 10.6), (21.8, 11.6), (20.6, 14.0), (22.4, 17.0), (26.0, 20.4), (29.0, 26.0), (30.0, 35.0)]
    dr.polygon(P(body), fill=255)
    for k in range(4):                                                                                       # shaggy fur at the back
        y = 18.0 + k * 3.2; dr.polygon(P([(5.6 - 0.4 * k, y), (0.6, y + 1.6), (5.0 - 0.4 * k, y + 2.6)]), fill=255)
    dr.polygon(P([(16.0, 9.6), (18.0, 9.8), (17.0, 10.8)]), fill=0)                                           # eye
    dr.polygon(P([(22.4, 5.6), (24.6, 7.0), (21.6, 9.0), (20.4, 7.6)]), fill=0)                               # open jaws (gap)
    return im


def glyph_threads_v1():
    """Thousand Threads (335, Earth/Death tier 4): a spider web spread over the area - eight radial threads and five
    rings of sagging cross-threads round a dark knot - and a small spider on the web."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 17.0; rnd = random.Random(335)
    angs = [math.radians(k * 45 + 8 + rnd.uniform(-6, 6)) for k in range(8)]
    for a in angs:
        L = 16.5 + rnd.uniform(-1.5, 1.5)
        dr.line([(cx * S, cy * S), ((cx + L * math.cos(a)) * S, (cy + L * 0.92 * math.sin(a)) * S)], fill=255, width=int(0.9 * S))
    for ring in range(1, 6):                                                                                 # sagging cross threads
        r = ring * 2.9
        for k in range(8):
            a0 = angs[k]; a1 = angs[(k + 1) % 8] + (2 * math.pi if k == 7 else 0)
            p0 = (cx + r * math.cos(a0), cy + r * 0.92 * math.sin(a0)); p1 = (cx + r * math.cos(a1), cy + r * 0.92 * math.sin(a1))
            mid = ((p0[0] + p1[0]) / 2 * 0.94 + cx * 0.06, (p0[1] + p1[1]) / 2 * 0.94 + cy * 0.06)
            pts = [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * mid[0] + t * t * p1[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * mid[1] + t * t * p1[1]) for t in [m / 6.0 for m in range(7)]]
            dr.line([(x * S, y * S) for x, y in pts], fill=255, width=int(0.75 * S))
    dr.ellipse([(cx - 1.6) * S, (cy - 1.6) * S, (cx + 1.6) * S, (cy + 1.6) * S], fill=255)
    sx, sy = 29.0, 25.6                                                                                      # a small spider on the web
    dr.ellipse([(sx - 1.6) * S, (sy - 1.3) * S, (sx + 1.6) * S, (sy + 1.3) * S], fill=255)
    dr.ellipse([(sx - 0.9) * S, (sy - 2.4) * S, (sx + 0.9) * S, (sy - 0.9) * S], fill=255)
    for side in (-1, 1):
        for k in range(4):
            a = math.radians(-60 + k * 40)
            dr.line([(sx * S, sy * S), ((sx + side * 3.2 * math.cos(a)) * S, (sy + 2.6 * math.sin(a)) * S)], fill=255, width=int(0.6 * S))
    return im


def _user_mask_glyph(fname):
    """A traced user reference (white = ink) at icon resolution, upscaled crisp."""
    m = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)).convert("L")
    return m.resize((W * S, H * S), Image.NEAREST)


def glyph_direwolf():
    """Summon Dire Wolf (332) v2 (user: v1 sucks - new reference art import export/direwolf.jpg, a bold black howling
    wolf head): the reference TRACED -> direwolf_user_mask.png.  (10/15: a darker re-trace was tried and reverted at the
    user's request.)"""
    return _user_mask_glyph("direwolf_user_mask.png")


def glyph_werewolf_v2():
    """Summon Werewolf (334) v2 (user: new reference art import export/werewolf.jpg, a hunched werewolf before a
    cratered full moon): the reference TRACED (median 5 + blur, thr 140) -> werewolf_user_mask.png."""
    return _user_mask_glyph("werewolf_user_mask.png")


def glyph_threads():
    """Thousand Threads (335) v2 (user: pretty good, make it look GRITTIER): v1's web, but every thread is a ragged
    hand-drawn line - wavering, kinked, uneven in thickness, broken in a few places - with grit specks caught on it
    and a scatter of dust, so it reads as an old, sticky, dirty web."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 17.0; rnd = random.Random(3352)
    def rough(p0, p1, w, seg=7, breaks=0.12):
        pts = []
        for k in range(seg + 1):
            t = k / seg; j = 0.0 if k in (0, seg) else rnd.uniform(-0.45, 0.45)
            x = p0[0] + (p1[0] - p0[0]) * t; y = p0[1] + (p1[1] - p0[1]) * t
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]; l = math.hypot(dx, dy) or 1
            pts.append((x - dy / l * j, y + dx / l * j))
        for k in range(seg):
            if rnd.random() < breaks: continue
            ww = w * rnd.uniform(0.65, 1.35)
            dr.line([(pts[k][0] * S, pts[k][1] * S), (pts[k + 1][0] * S, pts[k + 1][1] * S)], fill=255, width=max(1, int(ww * S)))
    angs = [math.radians(k * 45 + 8 + rnd.uniform(-7, 7)) for k in range(8)]
    for a in angs:
        L = 16.5 + rnd.uniform(-1.8, 1.8)
        rough((cx, cy), (cx + L * math.cos(a), cy + L * 0.92 * math.sin(a)), 1.05, seg=9, breaks=0.06)
    for ring in range(1, 6):
        r = ring * 2.9 + rnd.uniform(-0.3, 0.3)
        for k in range(8):
            a0 = angs[k]; a1 = angs[(k + 1) % 8] + (2 * math.pi if k == 7 else 0)
            p0 = (cx + r * math.cos(a0), cy + r * 0.92 * math.sin(a0)); p1 = (cx + r * math.cos(a1), cy + r * 0.92 * math.sin(a1))
            mid = ((p0[0] + p1[0]) / 2 * 0.93 + cx * 0.07, (p0[1] + p1[1]) / 2 * 0.93 + cy * 0.07)
            rough(p0, mid, 0.8, seg=3, breaks=0.15); rough(mid, p1, 0.8, seg=3, breaks=0.15)
    dr.ellipse([(cx - 1.7) * S, (cy - 1.6) * S, (cx + 1.5) * S, (cy + 1.8) * S], fill=255)
    for g in range(40):                                                                                      # grit / dust
        a = rnd.uniform(0, 2 * math.pi); r = rnd.uniform(0, 17); x = cx + r * math.cos(a); y = cy + r * 0.92 * math.sin(a)
        d = rnd.choice((0.35, 0.45, 0.6))
        if 0.5 < x < W - 0.5 and 0.5 < y < H - 0.5: dr.ellipse([(x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S], fill=255)
    sx, sy = 29.0, 25.6
    dr.ellipse([(sx - 1.7) * S, (sy - 1.4) * S, (sx + 1.7) * S, (sy + 1.4) * S], fill=255)
    dr.ellipse([(sx - 1.0) * S, (sy - 2.5) * S, (sx + 1.0) * S, (sy - 0.9) * S], fill=255)
    for side in (-1, 1):
        for k in range(4):
            a = math.radians(-60 + k * 40)
            rough((sx, sy), (sx + side * 3.4 * math.cos(a), sy + 2.8 * math.sin(a)), 0.7, seg=2, breaks=0.0)
    bb_ = im.getbbox()                                                                                   # 10/15 (user: off-centre): centre the drawing in the icon
    if bb_:
        dx = int(round((W * S - (bb_[0] + bb_[2])) / 2)); dy = int(round((H * S - (bb_[1] + bb_[3])) / 2))
        im = Image.Image.transform(im, im.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy))
    return im


def glyph_werewolf():
    """Summon Werewolf (334) v3 (user: v2 not centred and the werewolf is just a blob - make it discernible, bigger
    than the moon if needed): after art import export/werewolf.jpg but DRAWN as a clean silhouette - a hunched
    werewolf (two pointed ears, lowered head, long snout with an open jaw and an eye slit cut out, a shaggy shoulder
    hump with fur tufts, a raised clawed hand) big in the lower left, separated by a clear margin from a smaller
    cratered full moon (outline ring + craters) behind it at the upper right."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    mx, my, mr = 26.5, 11.5, 10.5                                                                           # the moon
    dr.ellipse([(mx - mr) * S, (my - mr) * S, (mx + mr) * S, (my + mr) * S], outline=255, width=int(1.4 * S))
    wolf = [(9.0, 2.6), (12.0, 9.6), (14.6, 9.0), (17.0, 3.0), (18.2, 10.6), (21.4, 12.2), (24.0, 13.0), (25.6, 11.6),
            (26.0, 14.6), (28.6, 14.0), (28.0, 17.2), (30.8, 17.4), (29.6, 20.4), (32.0, 22.4), (30.4, 24.4), (31.4, 28.6),
            (29.6, 31.4), (30.2, 35.0), (13.0, 35.0), (12.0, 32.4), (8.6, 32.4), (5.4, 31.6), (3.8, 28.6), (5.2, 28.4),
            (5.0, 26.0), (6.6, 27.6), (7.2, 25.2), (8.4, 27.4), (9.6, 26.0), (10.6, 28.4), (13.0, 28.6), (14.4, 24.0),
            (12.6, 21.6), (8.6, 21.2), (4.4, 21.6), (1.0, 20.4), (2.0, 19.0), (6.4, 18.6), (2.0, 17.0), (0.8, 15.6),
            (5.6, 13.8), (8.6, 12.6), (9.6, 10.6)]
    dr.polygon(P([(x + (x - 17) * 0.07, y + (y - 20) * 0.07) for x, y in wolf]), fill=0)                    # clear margin round the wolf
    dr.polygon(P(wolf), fill=255)
    dr.polygon(P([(9.4, 13.4), (12.6, 12.6), (12.2, 13.8), (9.6, 14.4)]), fill=0)                             # eye slit
    for x in (3.6, 5.4):                                                                                     # fangs in the open jaw
        dr.polygon(P([(x, 17.6), (x + 1.0, 17.6), (x + 0.5, 18.6)]), fill=0)
    for x0, y0, x1, y1 in ((20.0, 16.0, 24.0, 19.0), (22.6, 21.0, 26.6, 23.6), (19.0, 24.6, 23.4, 27.0), (24.2, 27.6, 27.6, 30.4)):
        dr.line(P([(x0, y0), (x1, y1)]), fill=0, width=int(0.75 * S))                                       # fur strokes
    for x0, y0, x1, y1 in ((18.0, 10.4, 19.6, 8.0), (20.4, 11.4, 22.4, 9.4)):                                # v4 polish: tufts at the back of the head
        dr.polygon(P([(x0 - 0.8, y0 + 0.6), (x1, y1), (x0 + 0.9, y0 + 0.4)]), fill=255)
    from PIL import ImageFilter
    im = im.filter(ImageFilter.GaussianBlur(0.18 * S)).point(lambda v: 255 if v > 128 else 0)                 # soften the jaggies
    bb = im.getbbox()                                                                                          # v4: centre the whole drawing
    if bb:
        dx = (W * S - (bb[0] + bb[2])) // 2; dy = (H * S - (bb[1] + bb[3])) // 2
        out = Image.new("L", im.size, 0); out.paste(im, (dx, dy)); im = out
    return im


def glyph_rotaway():
    """Rot Away (333) v2 (user: get rid of the top-right particles, recentre the wheel, make it a bit more broken):
    the rotting cartwheel centred, no flies; the rim broken in three places with a chunk fallen away, two spokes gone
    and one snapped short, the hub cracked, and rot dripping from the bottom."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy, R = 20.0, 15.5, 11.0
    dr.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], outline=255, width=int(2.6 * S))      # rim
    for a0, a1 in ((30, 58), (145, 160), (205, 226)):                                                        # broken rim gaps (one a missing chunk)
        dr.arc([(cx - R - 1) * S, (cy - R - 1) * S, (cx + R + 1) * S, (cy + R + 1) * S], a0, a1, fill=0, width=int(4.0 * S))
    for k in range(8):                                                                                       # spokes: two missing, one snapped short
        if k in (1, 5): continue
        a = math.radians(k * 45 + 10); L = R * (0.5 if k == 3 else 0.95)
        dr.line([(cx * S, cy * S), ((cx + L * math.cos(a)) * S, (cy + L * math.sin(a)) * S)], fill=255, width=int(1.5 * S))
    dr.ellipse([(cx - 2.8) * S, (cy - 2.8) * S, (cx + 2.8) * S, (cy + 2.8) * S], fill=255)                   # hub
    dr.ellipse([(cx - 1.0) * S, (cy - 1.0) * S, (cx + 1.0) * S, (cy + 1.0) * S], fill=0)
    dr.line([((cx + 0.6) * S, (cy - 2.8) * S), ((cx + 1.6) * S, (cy - 0.6) * S)], fill=0, width=int(0.6 * S))   # crack in the hub
    for x, L in ((14.0, 5.0), (19.0, 6.6), (24.6, 4.2)):                                                     # rot dripping
        teardrop(dr, x * S, (cy + R + L) * S, 1.1 * S, tip_up=True)
        dr.line([(x * S, (cy + R) * S), (x * S, (cy + R + L - 1) * S)], fill=255, width=int(1.0 * S))
    return im


def glyph_awaken_v1():
    """Awaken Spirit (300, Earth/Life tier 1): a spirit wisp - a flame-like teardrop with two clear eyes and a curling
    tail - rising out of an animal's paw print, with small sparkles round it."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    for x, y, r in ((20.0, 30.0, 3.2), (14.6, 26.0, 1.5), (18.0, 24.4, 1.4), (22.0, 24.4, 1.4), (25.4, 26.0, 1.5)):   # paw print
        dr.ellipse([(x - r) * S, (y - r * 0.85) * S, (x + r) * S, (y + r * 0.85) * S], fill=255)
    teardrop(dr, 20 * S, 15.0 * S, 5.6 * S, tip_up=True)                                                    # the wisp: a flame-shaped teardrop
    _fz_taper(dr, [(20.0, 3.4), (21.6, 1.6), (23.4, 1.8), (23.6, 3.4)], 1.4, 0.4)                          # its tip curling over
    for ex in (17.8, 22.2): dr.ellipse([(ex - 1.1) * S, 14.4 * S, (ex + 1.1) * S, 17.0 * S], fill=0)      # eyes
    for x, y, r in ((9.0, 10.0, 1.3), (31.6, 12.0, 1.1), (11.6, 18.6, 0.8), (29.4, 6.0, 0.9)):               # sparkles
        dr.polygon(P([(x, y - r * 2), (x + r * 0.5, y), (x, y + r * 2), (x - r * 0.5, y)]), fill=255)
        dr.polygon(P([(x - r * 2, y), (x, y + r * 0.5), (x + r * 2, y), (x, y - r * 0.5)]), fill=255)
    return im


def glyph_forest_blessing_v1():
    """Blessing of the Forest (301, Earth/Life tier 2): Barkskin - a heater shield made of bark (vertical grooves cut
    out, a knot) crowned by three oak leaves."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    shield = [(9.0, 12.0), (31.0, 12.0), (31.0, 21.0), (27.0, 28.4), (20.0, 33.4), (13.0, 28.4), (9.0, 21.0)]
    dr.polygon(P(shield), fill=255)
    for x in (13.0, 17.4, 22.6, 27.0):                                                                       # bark grooves (clear, wavy)
        pts = [(x + 0.6 * math.sin(t * 5 + x), 13.6 + 16.0 * t * (1 - abs(x - 20) / 16.0)) for t in [k / 10.0 for k in range(11)]]
        _fz_taper(dr, pts, 0.7, 0.4, fill=0)
    dr.ellipse([18.6 * S, 19.6 * S, 21.6 * S, 23.0 * S], fill=0); dr.ellipse([19.4 * S, 20.4 * S, 20.8 * S, 22.2 * S], fill=255)   # knot
    def leaf(cx, cy, ang, L):
        ca, sa = math.cos(ang), math.sin(ang); pts = []
        for k in range(21):
            t = k / 20.0; w = 2.2 * math.sin(math.pi * t) * (1 + 0.3 * math.sin(t * math.pi * 6))      # lobed oak leaf
            pts.append((cx + ca * L * t - sa * w, cy + sa * L * t + ca * w))
        for k in range(20, -1, -1):
            t = k / 20.0; w = 2.2 * math.sin(math.pi * t) * (1 + 0.3 * math.sin(t * math.pi * 6))
            pts.append((cx + ca * L * t + sa * w, cy + sa * L * t - ca * w))
        dr.polygon(P(pts), fill=255)
        dr.line(P([(cx, cy), (cx + ca * L * 0.85, cy + sa * L * 0.85)]), fill=0, width=int(0.5 * S))
    leaf(20.0, 11.4, -math.pi / 2, 10.4); leaf(15.0, 12.0, math.radians(-138), 9.0); leaf(25.0, 12.0, math.radians(-42), 9.0)
    return im


def glyph_golden_age_v1():
    """Golden Age (302, Earth/Life tier 3): a radiant sun rising behind a stack of coins - the sun's rays fanning
    out, the coins stacked with clear rim lines."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 17.0
    for k in range(14):                                                                                      # rays
        a = math.radians(180 + k * (180 / 13.0)); L0, L1 = 9.0, 16.5 if k % 2 == 0 else 13.5
        dr.polygon([((cx + L0 * math.cos(a - 0.08)) * S, (cy + L0 * math.sin(a - 0.08)) * S), ((cx + L1 * math.cos(a)) * S, (cy + L1 * math.sin(a)) * S),
                    ((cx + L0 * math.cos(a + 0.08)) * S, (cy + L0 * math.sin(a + 0.08)) * S)], fill=255)
    dr.pieslice([(cx - 7.6) * S, (cy - 7.6) * S, (cx + 7.6) * S, (cy + 7.6) * S], 180, 360, fill=255)       # the sun's disc (upper half)
    for k, (x, y) in enumerate(((20.0, 31.0), (19.2, 28.4), (20.8, 25.8), (19.6, 23.2), (20.6, 20.6))):     # a slightly offset pile of coins
        dr.rectangle([(x - 8.6) * S, (y - 1.0) * S, (x + 8.6) * S, (y + 1.2) * S], fill=255)                  # coin edge
        dr.ellipse([(x - 8.6) * S, (y + 0.0) * S, (x + 8.6) * S, (y + 2.4) * S], fill=255)
        dr.ellipse([(x - 8.6) * S, (y - 2.2) * S, (x + 8.6) * S, (y + 0.2) * S], fill=255)                    # coin face
        dr.arc([(x - 8.6) * S, (y + 0.0) * S, (x + 8.6) * S, (y + 2.4) * S], 10, 170, fill=0, width=int(0.5 * S))   # edge line (clear)
    x, y = 20.6, 20.6
    dr.ellipse([(x - 6.6) * S, (y - 1.6) * S, (x + 6.6) * S, (y - 0.4) * S], outline=0, width=int(0.45 * S))   # top coin's rim
    return im


def glyph_ent_v1():
    """Summon Ent (303, Earth/Life tier 4): a tree-man - a thick trunk with a face (two clear eyes under a heavy brow,
    a mouth gash), branch arms reaching up to a leafy crown, and roots spreading at its feet."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    for x, y, r in ((20.0, 6.0, 5.4), (13.6, 7.6, 4.2), (26.4, 7.6, 4.2), (9.6, 11.2, 3.2), (30.4, 11.2, 3.2), (16.6, 3.4, 3.4), (23.4, 3.4, 3.4)):
        dr.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=255)                          # leafy crown
    trunk = [(15.6, 12.0), (24.4, 12.0), (25.4, 30.0), (14.6, 30.0)]
    dr.polygon(P(trunk), fill=255)
    _fz_taper(dr, [(15.8, 16.0), (11.0, 14.4), (7.4, 10.6), (5.6, 6.6)], 3.0, 1.0)                           # branch arms
    _fz_taper(dr, [(24.2, 16.0), (29.0, 14.4), (32.6, 10.6), (34.4, 6.6)], 3.0, 1.0)
    for sx in (-1, 1):                                                                                        # roots
        _fz_taper(dr, [(20 + sx * 3.4, 29.0), (20 + sx * 7.0, 31.6), (20 + sx * 11.0, 33.6), (20 + sx * 14.4, 34.2)], 2.6, 0.6)
        _fz_taper(dr, [(20 + sx * 1.6, 29.6), (20 + sx * 3.6, 33.0), (20 + sx * 5.0, 34.6)], 2.0, 0.6)
    dr.polygon(P([(16.4, 16.4), (19.4, 17.8), (19.2, 18.6), (16.4, 17.6)]), fill=0)                          # brow + eyes
    dr.polygon(P([(23.6, 16.4), (20.6, 17.8), (20.8, 18.6), (23.6, 17.6)]), fill=0)
    dr.ellipse([16.8 * S, 18.8 * S, 18.8 * S, 20.6 * S], fill=0); dr.ellipse([21.2 * S, 18.8 * S, 23.2 * S, 20.6 * S], fill=0)
    dr.polygon(P([(17.6, 23.4), (22.4, 23.0), (21.6, 25.0), (18.4, 25.2)]), fill=0)                          # mouth gash
    for x0, y0, y1 in ((16.0, 26.0, 29.4), (24.0, 25.6, 29.6)): dr.line(P([(x0, y0), (x0 + 0.4, y1)]), fill=0, width=int(0.5 * S))   # bark lines
    return im


def _fox_poly(cx, cy, k):
    """A sitting fox in profile (facing left) as a polygon, scaled by k about (cx, cy)."""
    pts = [(-4.6, -7.4), (-3.0, -4.4), (-1.4, -4.6), (-0.6, -8.0), (0.8, -4.2), (1.6, -2.4), (1.4, 0.4), (3.2, 2.0),
           (4.4, 4.6), (4.0, 6.6), (6.4, 5.4), (8.4, 5.8), (8.6, 7.4), (6.0, 8.2), (2.4, 8.2), (-1.8, 8.2), (-2.4, 6.8),
           (-1.6, 6.2), (-1.4, 2.4), (-2.6, 0.2), (-4.0, -1.6), (-7.2, -2.6), (-7.0, -3.6), (-4.8, -4.2)]
    return [(cx + x * k, cy + y * k) for x, y in pts]


def _bear_poly(cx, cy, k):
    """A bear in profile (facing left) as a polygon, scaled by k about (cx, cy)."""
    pts = [(-8.0, -0.4), (-7.4, -1.6), (-6.2, -2.2), (-5.2, -3.2), (-4.6, -4.6), (-3.6, -4.4), (-3.2, -3.6), (-1.0, -4.4),
           (1.6, -4.8), (4.2, -4.4), (6.6, -3.0), (7.8, -1.2), (8.0, 0.8), (7.4, 4.6), (5.6, 4.6), (5.4, 2.0), (3.6, 2.2),
           (3.0, 4.6), (1.2, 4.6), (1.0, 2.2), (-1.8, 2.0), (-2.2, 4.6), (-4.0, 4.6), (-4.4, 1.6), (-6.0, 0.8), (-7.6, 0.6)]
    return [(cx + x * k, cy + y * k) for x, y in pts]


def glyph_awaken():
    """Awaken Spirit (300) v3 (user: a small animal with a LARGER OUTLINE of itself round it, like an aura; v2's fox
    read poorly): a small solid bear in profile at the centre and, round it, the same bear twice as large as a glowing
    OUTLINE (its awakened spirit), with sparks in the space between."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    big = _bear_poly(20.0, 17.8, 2.05)
    dr.line(P(big + [big[0]]), fill=255, width=int(1.3 * S), joint="curve")                                 # the spirit outline
    small = _bear_poly(20.6, 19.4, 0.95)
    dr.polygon(P(small), fill=255)                                                                             # the small bear
    dr.ellipse([(20.6 - 5.2 - 0.45) * S, (19.4 - 2.4 - 0.45) * S, (20.6 - 5.2 + 0.45) * S, (19.4 - 2.4 + 0.45) * S], fill=0)   # eye
    for x, y, r in ((11.0, 14.6, 0.8), (13.4, 24.6, 0.6)):                                       # v5 (user): no spark on the big bear's rump either
        dr.polygon(P([(x, y - r * 2), (x + r * 0.5, y), (x, y + r * 2), (x - r * 0.5, y)]), fill=255)
        dr.polygon(P([(x - r * 2, y), (x, y + r * 0.5), (x + r * 2, y), (x, y - r * 0.5)]), fill=255)
    return im


def glyph_forest_blessing():
    """Blessing of the Forest (301) v4 (user: no circle, fix the roots and leaves): a tree of life - a stout trunk,
    branches curving up and out under a full rounded canopy of leaf clusters (overlapping leaf discs with clear gaps
    between clusters), and seven roots spreading and tapering underneath, curling at their tips."""
    im = canvas(); dr = ImageDraw.Draw(im); cx = 20.0; rnd = random.Random(3011)
    dr.polygon([(18.0 * S, 13.0 * S), (22.0 * S, 13.0 * S), (23.2 * S, 25.0 * S), (16.8 * S, 25.0 * S)], fill=255)   # trunk
    for k in range(5):                                                                                         # branches into the canopy
        a = math.radians(-150 + k * 30); pts = []
        for m in range(9):
            t = m / 8.0; aa = a + (0.3 * t if k < 2 else -0.3 * t if k > 2 else 0)
            pts.append((cx + 9.0 * t * math.cos(aa), 14.0 + 8.0 * t * math.sin(aa)))
        _fz_taper(dr, pts, 2.0, 0.8)
    clusters = []                                                                                              # the canopy: clusters on a dome
    for k in range(11):
        a = math.radians(-180 + k * 18); r = 13.0 if k % 2 == 0 else 10.5
        clusters.append((cx + r * math.cos(a), 11.0 + r * 0.72 * math.sin(a)))
    clusters += [(cx, 7.0), (cx - 5.0, 8.6), (cx + 5.0, 8.6), (cx - 8.6, 11.6), (cx + 8.6, 11.6)]
    for x, y in clusters:
        dr.ellipse([(x - 3.0) * S, (y - 2.6) * S, (x + 3.0) * S, (y + 2.6) * S], fill=0)                      # a clear outline round each cluster
    for x, y in clusters:
        for dx, dy, r in ((0, 0, 2.2), (-1.5, 0.8, 1.4), (1.5, 0.8, 1.4), (0, -1.2, 1.4)):
            dr.ellipse([(x + dx - r) * S, (y + dy - r) * S, (x + dx + r) * S, (y + dy + r) * S], fill=255)
    for side, spread, drop, w, ph in ((0, 0.0, 9.8, 3.0, 0.0), (-1, 6.5, 9.0, 2.6, 0.0), (1, 6.5, 9.0, 2.6, 0.0), (-1, 13.0, 7.4, 2.2, 0.6), (1, 13.0, 7.4, 2.2, 0.6)):
        pts = []                                                                                               # v6: smooth S-curved roots, no hooks
        for m in range(18):
            t = m / 17.0
            x = cx + side * spread * t + (1.6 if side == 0 else 1.3) * math.sin(t * 2 * math.pi + ph) * t * (1 if side >= 0 else -1)
            y = 24.4 + drop * t ** 1.15
            pts.append((x, min(34.6, y)))
        _fz_taper(dr, pts, w, 0.4)
    return im


def glyph_golden_age():
    """Golden Age (302) v2 (user: a CITY like Warmonger's, with the current sunrise above it): Warmonger's own city
    skyline (vanilla ink 71, the lower part) along the bottom, and v1's rising sun - half disc and fanned rays - above."""
    im = canvas(); dr = ImageDraw.Draw(im)
    ink = vanilla_ink(71); bb = ink.point(lambda v: 255 if v > 60 else 0).getbbox()
    city = ink.crop((bb[0], bb[3] - 10, bb[2], bb[3]))                                                       # v3: only the skyline (the bottom 10 rows) - no sword remnants
    cw, ch = city.size
    sc = 1.0; city = city.resize((int(cw * S), int(ch * S)), Image.NEAREST)                                  # v3: native size, crisp (as in Warmonger's icon)
    paste_max(im, city, (int((W * S - city.width) / 2), H * S - city.height - int(0.6 * S)))
    cx, cy = 20.0, 34.6 - ch * sc - 1.6
    for k in range(13):                                                                                        # rays
        a = math.radians(180 + k * 15); L0, L1 = 6.6, 14.5 if k % 2 == 0 else 11.4
        dr.polygon([((cx + L0 * math.cos(a - 0.09)) * S, (cy + L0 * math.sin(a - 0.09)) * S), ((cx + L1 * math.cos(a)) * S, (cy + L1 * math.sin(a)) * S),
                    ((cx + L0 * math.cos(a + 0.09)) * S, (cy + L0 * math.sin(a + 0.09)) * S)], fill=255)
    sun = Image.new("L", im.size, 0); sd = ImageDraw.Draw(sun)                                               # v4: the sun's disc fading into the city
    sd.ellipse([(cx - 5.6) * S, (cy - 5.6) * S, (cx + 5.6) * S, (cy + 5.6) * S], fill=255)
    import numpy as np
    sa = np.array(sun).astype(np.float32); yy = np.arange(sa.shape[0], dtype=np.float32)[:, None] / S
    fade = np.clip(1.0 - (yy - (cy - 1.0)) / 5.2, 0, 1) ** 1.3                                             # full above the horizon, fading below it
    sa *= fade; paste_max(im, Image.fromarray(sa.astype(np.uint8)), (0, 0))
    return im


def glyph_ent():
    """Summon Ent (303) v2 (user: pretty good, but the top/leaves look like a mushroom - make it more of a PARTICLES
    look, like the disease cloud): v1's tree-man (face, branch arms, roots) with the leafy crown STIPPLED - grains
    weighted to each leaf-puff's rim, so it reads as foliage, not a cap."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]; rnd = random.Random(3032)
    puffs = ((20.0, 7.4, 6.2), (12.4, 8.8, 5.0), (27.6, 8.8, 5.0), (7.0, 11.6, 3.8), (33.0, 11.6, 3.8), (15.6, 4.6, 4.0), (24.4, 4.6, 4.0),
             (10.4, 13.0, 3.0), (15.6, 13.6, 3.2), (20.6, 14.0, 3.2), (25.6, 13.6, 3.2), (30.0, 13.0, 3.0))   # v3: the last five = bulbous cloud underside
    step = 0.9; y = 0.3; row = 0
    while y < 18.5:                                                                                            # v3: extends past the puffs and FADES away
        x = 0.3 + (step / 2 if row % 2 else 0)
        while x < W:
            jx, jy = x + rnd.uniform(-0.25, 0.25), y + rnd.uniform(-0.25, 0.25)
            dn = min(math.hypot(jx - px, jy - py) / pr for px, py, pr in puffs)
            if dn < 1.0: p = 0.32 + 0.7 * dn ** 3
            elif dn < 1.7: p = 0.9 * (1 - (dn - 1.0) / 0.7) ** 1.6                                             # the fade-out halo
            else: p = 0.0
            p *= min(1.0, max(0.0, (jy - 0.2) / 4.5)) ** 1.2                                                # v4: fade toward the top edge (no square cut-off)
            if rnd.random() < p:
                d = (0.34 + 0.14 * min(dn, 1.0)) * (1.0 if dn < 1.0 else max(0.55, 1.15 - 0.6 * dn)) + rnd.uniform(-0.04, 0.04)
                dr.ellipse([(jx - d) * S, (jy - d) * S, (jx + d) * S, (jy + d) * S], fill=255)
            x += step
        y += step * 0.88; row += 1
    trunk = [(15.6, 12.0), (24.4, 12.0), (25.4, 30.0), (14.6, 30.0)]
    dr.polygon(P(trunk), fill=255)
    _fz_taper(dr, [(15.8, 16.0), (11.0, 14.4), (7.4, 10.6), (5.6, 6.6)], 3.0, 1.0)
    _fz_taper(dr, [(24.2, 16.0), (29.0, 14.4), (32.6, 10.6), (34.4, 6.6)], 3.0, 1.0)
    for sx in (-1, 1):
        _fz_taper(dr, [(20 + sx * 3.4, 29.0), (20 + sx * 7.0, 31.6), (20 + sx * 11.0, 33.6), (20 + sx * 14.4, 34.2)], 2.6, 0.6)
        _fz_taper(dr, [(20 + sx * 1.6, 29.6), (20 + sx * 3.6, 33.0), (20 + sx * 5.0, 34.6)], 2.0, 0.6)
    dr.polygon(P([(16.4, 16.4), (19.4, 17.8), (19.2, 18.6), (16.4, 17.6)]), fill=0)
    dr.polygon(P([(23.6, 16.4), (20.6, 17.8), (20.8, 18.6), (23.6, 17.6)]), fill=0)
    dr.ellipse([16.8 * S, 18.8 * S, 18.8 * S, 20.6 * S], fill=0); dr.ellipse([21.2 * S, 18.8 * S, 23.2 * S, 20.6 * S], fill=0)
    dr.polygon(P([(17.6, 23.4), (22.4, 23.0), (21.6, 25.0), (18.4, 25.2)]), fill=0)
    for x0, y0, y1 in ((16.0, 26.0, 29.4), (24.0, 25.6, 29.6)): dr.line(P([(x0, y0), (x0 + 0.4, y1)]), fill=0, width=int(0.5 * S))
    return im


def glyph_mammoth():
    """Summon Mammoth (364) v5 (user: smaller ears, bigger tusks, bigger trunk, look hairy): the Summon-Boar-style
    FRONT face - a domed crown and cheeks with a RAGGED hairy outline (shaggy fringe on the crown, long locks hanging
    from the cheeks and chin), small ragged ears tucked to the sides, angry brows and eyes cut out, a THICK trunk
    down the middle curling at the tip, and two HEAVY tusks sweeping out and up past the cheeks (black gap round each)."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]; cx = 20.0
    rnd = random.Random(3645)
    def sym(pts): return pts + [(2 * cx - x, y) for x, y in reversed(pts)]
    for side in (-1, 1):                                                                                       # small ragged ears
        ear = [(cx + side * 7.6, 7.4), (cx + side * 11.6, 6.8), (cx + side * 13.6, 9.4), (cx + side * 13.4, 13.0),
               (cx + side * 14.2, 15.4), (cx + side * 12.8, 17.4), (cx + side * 13.2, 19.6), (cx + side * 11.4, 22.4),
               (cx + side * 9.0, 21.0)]                                                                  # v5.3: ears hang lower (user)
        dr.polygon(P(ear), fill=255)
    head = sym([(cx, 0.8), (cx - 3.8, 1.4), (cx - 6.8, 3.4), (cx - 8.8, 7.2), (cx - 9.4, 11.8), (cx - 8.6, 16.4),
                (cx - 6.4, 20.2), (cx - 3.6, 21.8)])
    dr.polygon(P(head), fill=255)
    for k in range(11):                                                                                        # v5.2: ragged tufts all round the crown (hair; the black fringe read as a headband at 40x35)
        a = math.radians(200 + k * 14.0); x = cx + 8.8 * math.cos(a); y = 9.0 + 8.4 * math.sin(a)
        dr.polygon(P([(x - 1.0, y + 0.6), (x + math.cos(a) * 1.8 - 0.8, y + math.sin(a) * 1.8 + 1.4), (x + 1.0, y + 0.6)]), fill=255)
    for side in (-1, 1):                                                                                       # long locks from cheeks and chin
        for k in range(4):
            x = cx + side * (9.0 - k * 1.6); y = 14.0 + k * 2.2
            dr.polygon(P([(x - side * 1.4, y - 1.0), (x + side * 1.6, y + 0.6), (x + side * 0.2 + rnd.uniform(-0.4, 0.4), y + 4.2)]), fill=255)
    for side in (-1, 1):
        dr.ellipse([(cx + side * 4.4 - 1.0) * S, 10.0 * S, (cx + side * 4.4 + 1.0) * S, 12.0 * S], fill=0)   # eyes
        dr.polygon(P([(cx + side * 1.6, 10.0), (cx + side * 6.8, 7.6), (cx + side * 6.6, 8.8), (cx + side * 1.8, 10.9)]), fill=0)   # angry brow
    trunk = [(cx, 14.0), (cx, 21.0), (cx - 0.2, 26.4), (cx + 0.6, 30.4), (cx + 2.8, 32.6), (cx + 5.0, 31.6), (cx + 5.0, 29.6)]
    _fz_taper(dr, trunk, 7.0, 2.6)                                                                             # THICK trunk
    for k in range(4):
        y = 18.6 + k * 3.0; w = 3.0 - k * 0.45
        dr.line(P([(cx - w, y), (cx + w, y + 0.3)]), fill=0, width=int(0.6 * S))
    for side in (-1, 1):                                                                                       # HEAVY tusks
        tusk = [(cx + side * 3.4, 20.0), (cx + side * 6.4, 26.4), (cx + side * 11.0, 29.4), (cx + side * 15.6, 27.6),
                (cx + side * 17.8, 23.2), (cx + side * 17.4, 18.8)]
        _fz_taper(dr, tusk, 6.4, 3.4, fill=0)
        _fz_taper(dr, tusk, 5.0, 1.8)
    return im


def glyph_hurl_boulder():
    """Hurl Boulder (365, Earth/Air tier 2): a big cracked boulder flying along an arc - three motion lines trailing
    from the upper left, the rock lumpy with clear crack lines, a few chips flying off."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    rock = [(19.6, 9.0), (25.4, 8.2), (30.6, 11.0), (33.4, 16.6), (32.4, 23.0), (27.6, 27.6), (21.0, 28.2), (16.2, 24.8), (14.8, 18.6), (16.0, 12.6)]
    dr.polygon(P(rock), fill=255)
    for pts in (((22.0, 11.0), (24.6, 15.4), (23.4, 19.4)), ((24.6, 15.4), (29.4, 16.6)), ((23.4, 19.4), (19.6, 22.6)), ((23.4, 19.4), (27.0, 24.4))):
        dr.line(P(list(pts)), fill=0, width=int(0.7 * S))                                                  # cracks
    for k, (x0, y0, x1, y1) in enumerate(((2.0, 6.0, 13.0, 12.0), (1.0, 13.4, 13.0, 17.4), (3.0, 21.0, 13.4, 22.6))):
        _fz_taper(dr, [(x0, y0), ((x0 + x1) / 2, (y0 + y1) / 2 - 1.2 + k * 0.6), (x1, y1)], 0.5, 1.6)      # motion lines
    for x, y, r in ((35.6, 8.6, 1.0), (36.8, 13.0, 0.7), (11.6, 28.0, 0.8)):                                 # chips
        dr.polygon(P([(x - r, y), (x, y - r * 1.2), (x + r, y - 0.2), (x + 0.4, y + r)]), fill=255)
    return im


def glyph_gravity_well():
    """Gravity Well (366, Earth/Air tier 3): a well in the ground seen in perspective - five shrinking ellipses
    funnelling down to a dark point - with three arrows pulling down into it and a small bird dragged down above."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]; cx = 20.0
    for k, (rx, ry, y) in enumerate(((16.0, 4.6, 24.0), (12.6, 3.6, 25.6), (9.4, 2.7, 27.0), (6.4, 1.9, 28.2), (3.6, 1.1, 29.2))):
        dr.ellipse([(cx - rx) * S, (y - ry) * S, (cx + rx) * S, (y + ry) * S], outline=255, width=int((1.4 - k * 0.15) * S))
    dr.ellipse([(cx - 1.2) * S, 28.8 * S, (cx + 1.2) * S, 30.2 * S], fill=255)
    for x, y0, y1 in ((9.0, 8.0, 17.0), (31.0, 8.0, 17.0), (20.0, 12.0, 21.0)):                               # arrows pulling down
        dr.line(P([(x, y0), (x, y1)]), fill=255, width=int(1.3 * S))
        dr.polygon(P([(x - 2.0, y1 - 1.0), (x + 2.0, y1 - 1.0), (x, y1 + 2.2)]), fill=255)
    bx, by = 20.0, 5.4                                                                                         # a bird dragged down
    dr.polygon(P([(bx - 5.0, by - 2.6), (bx - 1.6, by + 0.4), (bx, by - 0.4), (bx + 1.6, by + 0.4), (bx + 5.0, by - 2.6), (bx + 1.4, by + 1.8), (bx, by + 2.8), (bx - 1.4, by + 1.8)]), fill=255)
    return im


def glyph_slow():
    """Slow (380, Earth/Water tier 1): a snail creeping left - a big spiral shell (the spiral cut out in black) on a
    long low foot, two eye-stalks with knobbed tips, and dashes trailing behind it (slime/slowness)."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    dr.polygon(P([(3.0, 27.0), (6.0, 23.6), (12.0, 23.0), (30.0, 24.0), (35.6, 26.6), (35.0, 28.6), (5.0, 28.6)]), fill=255)   # foot
    cx, cy, R = 21.0, 15.0, 10.6
    dr.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], fill=255)                            # shell
    pts = []
    for k in range(60):
        t = k / 59.0; a = -math.pi / 2 + t * 2.3 * 2 * math.pi; r = 8.6 * (1 - t) + 0.8
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    dr.line(P(pts), fill=0, width=int(1.0 * S))                                                               # the spiral
    dr.line(P([(cx - R + 0.4, 24.4), (cx + R - 0.4, 24.4)]), fill=0, width=int(0.8 * S))                      # shell rim on the foot
    for x0, y0, x1, y1 in ((7.0, 23.6, 4.6, 14.6), (9.4, 23.4, 9.2, 13.6)):                                 # eye-stalks
        dr.line(P([(x0, y0), (x1, y1)]), fill=255, width=int(1.1 * S))
        dr.ellipse([(x1 - 1.3) * S, (y1 - 1.3) * S, (x1 + 1.3) * S, (y1 + 1.3) * S], fill=255)
    for y, x0, x1 in ((31.4, 25.0, 31.0), (31.4, 33.0, 36.4), (31.4, 15.0, 22.0)):                            # trailing slime dashes
        dr.line(P([(x0, y), (x1, y)]), fill=255, width=int(0.9 * S))
    return im


def glyph_crocodile():
    """Summon Crocodile (381) v8 (user: new reference art import export/croc.jpg - a bold black crocodile in side
    profile, jaws agape, tail curling up behind): the reference TRACED (tmp\\cd_trace.py: text cropped off, median 3
    + blur 1.5, thr 128, fitted to 40x35) -> croc_user_mask.png."""
    return _user_mask_glyph("croc_user_mask.png")


def glyph_swampwalk():
    """Swampwalk (382, Earth/Water tier 3): a bare footprint (sole + five toes) pressed on rippling swamp water,
    flanked by two cattails (reed stems with fat seed heads) and a few reed blades."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]; cx = 20.0
    for rx, ry in ((15.0, 4.4), (10.6, 3.0)):                                                                 # ripples
        dr.ellipse([(cx - rx) * S, (27.6 - ry) * S, (cx + rx) * S, (27.6 + ry) * S], outline=255, width=int(1.0 * S))
    fx = cx                                                                                                   # v8 (user: closer to the reference - toes too small/far): the WHOLE
    ref = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "swampwalk_foot_ref.png"))      # reference traced (sole + 5 toes as separate components),
    fh = 21.5; fw = fh * ref.size[0] / ref.size[1]; fx0, fy0 = fx - fw / 2, 4.6                                # scaled faithfully; each toe gets its own black ring so the
    ra = np.array(ref)                                                                                           # gaps survive at 40x35
    from PIL import ImageFilter
    for k in range(1, int(ra.max()) + 1):
        part = Image.fromarray(((ra == k) * 255).astype(np.uint8)).resize((int(fw * S), int(fh * S)), Image.LANCZOS).point(lambda v: 255 if v > 127 else 0)
        layer = Image.new("L", im.size, 0); layer.paste(part, (int(fx0 * S), int(fy0 * S)))
        im.paste(0, mask=layer.filter(ImageFilter.MaxFilter(int(1.1 * S) | 1))); im.paste(255, mask=layer)
    for x, h, lean in ((6.0, 4.0, -0.10), (34.0, 6.0, 0.08)):                                                   # cattails
        dr.line(P([(x, 30.0), (x + lean * 20, h)]), fill=255, width=int(0.9 * S))
        hx, hy = x + lean * (30.0 - h - 6) * 0.9, h + 6.0
        dr.ellipse([(hx - 1.6) * S, (hy - 4.0) * S, (hx + 1.6) * S, (hy + 4.0) * S], fill=255)
    for x0, x1, y1 in ((9.0, 11.6, 16.0), (31.0, 28.2, 17.4), (3.0, 1.4, 20.0)):                                # reed blades
        _fz_taper(dr, [(x0, 30.0), ((x0 + x1) / 2, (30.0 + y1) / 2), (x1, y1)], 1.4, 0.2)
    for x0, lean, L, w in ((2.0, -0.2, 14.0, 1.6), (4.6, 0.25, 18.0, 1.7), (8.6, -0.35, 13.0, 1.5), (11.4, 0.3, 10.0, 1.3),   # v8.1 (user: more vegetation / long grass)
                           (38.0, 0.2, 13.0, 1.6), (35.6, -0.3, 17.0, 1.7), (31.4, 0.35, 12.0, 1.5), (28.8, -0.25, 9.0, 1.3)):
        pts = [(x0 + lean * L * (m / 8.0) ** 1.6, 33.6 - L * (m / 8.0)) for m in range(9)]
        _fz_taper(dr, pts, w + 1.0, 0.6, fill=0); _fz_taper(dr, pts, w, 0.2)
    return im


def glyph_overgrowth():
    """Overgrowth (383) v8 (user: simpler tower - keep the parapet - and polish the vines/leaves/trees): a plain
    stone tower (no window or door) with its crenellated parapet, a smooth vine winding up it (black-edged) with
    proper pointed leaves on short stems where it passes the edges, between two round-crowned trees."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]; cx = 20.0
    dr.rectangle([0.4 * S, 31.2 * S, 39.6 * S, 34.2 * S], fill=255)                                            # ground
    def tree(x, base, h, r):
        cy = base - h + r
        blobs = ((0, 0, r), (-r * 0.55, r * 0.35, r * 0.7), (r * 0.55, r * 0.35, r * 0.7), (0, -r * 0.35, r * 0.8))
        for dx, dy, rr in blobs:
            k = rr + 0.8; dr.ellipse([(x + dx - k) * S, (cy + dy - k) * S, (x + dx + k) * S, (cy + dy + k) * S], fill=0)
        dr.polygon(P([(x - r * 0.22, base), (x - r * 0.14, cy + r * 0.6), (x + r * 0.14, cy + r * 0.6), (x + r * 0.22, base)]), fill=255)
        for dx, dy, rr in blobs:
            dr.ellipse([(x + dx - rr) * S, (cy + dy - rr) * S, (x + dx + rr) * S, (cy + dy + rr) * S], fill=255)
    tree(6.0, 31.4, 19.0, 5.0); tree(34.0, 31.4, 16.0, 4.4)
    tw = [(16.0, 31.4), (16.6, 12.6), (23.4, 12.6), (24.0, 31.4)]                                        # v8.1: a smaller tower
    dr.polygon(P([(x + (1.0 if x > cx else -1.0), y) for x, y in tw]), fill=0)
    dr.polygon(P(tw), fill=255)                                                                               # a plain tower
    dr.rectangle([(15.0 - 0.9) * S, (9.8 - 0.9) * S, (25.0 + 0.9) * S, 12.9 * S], fill=0)
    dr.rectangle([15.0 * S, 9.8 * S, 25.0 * S, 12.9 * S], fill=255)                                            # parapet
    for x in (15.0, 18.3, 21.6, 23.4):
        dr.rectangle([x * S, 7.8 * S, (x + 1.6) * S, 10.0 * S], fill=255)                                     # merlons
    dr.rectangle([15.0 * S, 12.7 * S, 25.0 * S, 13.3 * S], fill=0)
    pts = []
    for k in range(60):                                                                                       # a smooth vine winding up
        t = k / 59.0; a = t * 1.5 * 2 * math.pi + 0.5
        pts.append((cx + 5.6 * math.sin(a), 31.0 - 17.0 * t + 1.2 * math.cos(a)))
    _fz_taper(dr, pts, 3.2, 2.0, fill=0)
    _fz_taper(dr, pts, 1.9, 1.0)
    def leaf(x, y, deg, L, W):
        a = math.radians(deg); ux, uy = math.cos(a), -math.sin(a); px, py = -uy, ux
        def sh(wa, la):
            o = []
            for k in range(13):
                t = k / 12.0; w = (W + wa) * math.sin(math.pi * t ** 0.8) ** 0.9; o.append((x + ux * (L + la) * t + px * w, y + uy * (L + la) * t + py * w))
            for k in range(12, -1, -1):
                t = k / 12.0; w = (W + wa) * math.sin(math.pi * t ** 0.8) ** 0.9; o.append((x + ux * (L + la) * t - px * w, y + uy * (L + la) * t - py * w))
            return o
        dr.polygon(P(sh(0.8, 0.9)), fill=0); dr.polygon(P(sh(0, 0)), fill=255)
        dr.line(P([(x + ux * 1.2, y + uy * 1.2), (x + ux * L * 0.8, y + uy * L * 0.8)]), fill=0, width=max(1, int(0.4 * S)))
    ext = [k for k in range(1, len(pts) - 1) if abs(pts[k][0] - cx) >= abs(pts[k - 1][0] - cx) and abs(pts[k][0] - cx) > abs(pts[k + 1][0] - cx)]
    for k in ext:
        x, y = pts[k]; side = 1 if x > cx else -1
        leaf(x + side * 0.6, y - 0.2, 30 if side > 0 else 150, 6.6, 2.3)
    return im


def glyph_frenzy_v19():
    """Frenzied Charge v16 (user: v15 looked nothing like the reference art import export/frenzy.jpg): the reference
    itself TRACED - hairline to chin fitted to the icon height (crop x 8-92 %, y 7-70 %), median 9 + blur 6, threshold
    135, then isolated pixels removed: the dark wild hair framing a clear forehead, the knotted brow band, the creases,
    and the dark screaming mouth with its clear rows of teeth.  frenzy_user_mask.png = source of truth (white = ink)."""
    # v19 (user: changed my mind about the small particles - CLEAN IT UP): no grains.  At icon resolution: keep the
    # traced ink inside a head-shaped ellipse (a little wider than the face so the hair forms a clean solid frame),
    # then drop every ink speck / clear pinhole smaller than 4 px (8-connected components) so only clean shapes remain.
    import numpy as np
    m = np.array(Image.open(FRENZY_MASK).convert("L")) > 127
    yy, xx = np.mgrid[0:H, 0:W]
    keep = (((xx + 0.5 - 20.6) / 11.2) ** 2 + ((yy + 0.5 - 20.0) / 16.4) ** 2) <= 1.0
    m &= keep
    def components(a):
        seen = np.zeros_like(a); comps = []
        for y0 in range(H):
            for x0 in range(W):
                if a[y0, x0] and not seen[y0, x0]:
                    st = [(y0, x0)]; seen[y0, x0] = True; c = []
                    while st:
                        y, x = st.pop(); c.append((y, x))
                        for dy in (-1, 0, 1):
                            for dx in (-1, 0, 1):
                                ny, nx = y + dy, x + dx
                                if 0 <= ny < H and 0 <= nx < W and a[ny, nx] and not seen[ny, nx]: seen[ny, nx] = True; st.append((ny, nx))
                    comps.append(c)
        return comps
    for c in components(m):
        if len(c) < 4:
            for y, x in c: m[y, x] = False
    for c in components(~m & keep):
        if len(c) < 4:
            for y, x in c: m[y, x] = True
    return Image.fromarray((m * 255).astype(np.uint8)).resize((W * S, H * S), Image.NEAREST)


def glyph_drought():
    """Drought (391): a blazing sun (ring + rays) over parched ground: the Tremors crack (vanilla ink 54) laid along the
    bottom."""
    im = canvas(); dr = ImageDraw.Draw(im); cx, cy = 20.0, 11.0
    dr.ellipse([(cx - 5.2) * S, (cy - 5.0) * S, (cx + 5.2) * S, (cy + 5.0) * S], fill=255)
    for k in range(12):
        a = math.radians(k * 30); L = 11.5 if k % 2 == 0 else 9.0
        dr.line([((cx + 6.6 * math.cos(a)) * S, (cy + 6.4 * math.sin(a)) * S), ((cx + L * math.cos(a)) * S, (cy + L * 0.97 * math.sin(a)) * S)], fill=255, width=int(1.5 * S))
    crack = vanilla_ink(54).filter(ImageFilter.MaxFilter(3)).rotate(42, resample=Image.BICUBIC, expand=True)
    bb = crack.getbbox(); crack = crack.crop(bb).resize((36 * S, 12 * S), Image.BICUBIC).point(lambda v: 255 if v > 90 else 0)
    paste_max(im, crack, (2 * S, 23 * S))
    return im


def glyph_forge_blast():
    """Forge Blast v3 (user: the city is good, replace what's above it with a HALF-CIRCLE explosion): Gold Rush's own
    city silhouette (icon 45, rows 22-35) under a half-dome blast rising from the skyline - a billowing scalloped rim,
    a black shock-wave arc inside it and a small bright core - with short rays and debris flying off the dome."""
    im = canvas(); dr = ImageDraw.Draw(im); P = lambda pts: [(x * S, y * S) for x, y in pts]
    cx, by, R = 20.0, 23.0, 13.4                                                                         # v4.1: slightly smaller so the rays stay inside the icon
    def rim(R0, amp, n, w):                                                                                  # v4 (user: less solid, more OUTLINE line art)
        pts = []
        for k in range(73):
            a = math.pi * k / 72.0; rr = R0 + amp * abs(math.cos(n * a / 2.0)) ** 0.6
            pts.append((cx + rr * math.cos(a), by - rr * math.sin(a)))
        dr.line(P(pts), fill=255, width=int(w * S), joint="curve")
    rim(R, 1.8, 10, 1.4)                                                                                   # the billowing outer rim (outline)
    rim(R - 5.0, 1.2, 8, 1.1)                                                                              # a second wave inside
    dr.pieslice([(cx - 4.4) * S, (by - 4.4) * S, (cx + 4.4) * S, (by + 4.4) * S], 180, 360, fill=255)      # the bright core
    for k in range(11):                                                                                    # rays bursting out
        a = math.radians(14 + k * 15.2); r0, r1 = R + 2.4, R + 4.6 - (k % 2) * 1.4
        dr.line(P([(cx + r0 * math.cos(a), by - r0 * math.sin(a)), (cx + r1 * math.cos(a), by - r1 * math.sin(a))]), fill=255, width=int(1.0 * S))
    for k in range(9):                                                                                     # short sparks between the waves
        a = math.radians(14 + k * 19.0); r0, r1 = 5.6, R - 6.6
        dr.line(P([(cx + r0 * math.cos(a), by - r0 * math.sin(a)), (cx + r1 * math.cos(a), by - r1 * math.sin(a))]), fill=255, width=int(0.8 * S))
    city = vanilla_ink(45).crop((0, 21, 40, 35)).point(lambda v: 255 if v > 90 else 0).resize((40 * S, 14 * S), Image.NEAREST)
    from PIL import ImageFilter
    halo = Image.new("L", im.size, 0); halo.paste(city.filter(ImageFilter.MaxFilter(int(1.2 * S) | 1)), (0, 21 * S))
    im.paste(0, mask=halo)                                                                                # a clear gap between the blast and the skyline
    paste_max(im, city, (0, 21 * S))
    return im


def glyph_arms_race():
    """Arms Race (Earth/Fire 4): a cogwheel with two crossed swords through it."""
    im = canvas(); dr = ImageDraw.Draw(im)
    cx, cy, R = 20.0, 18.0, 10.5
    dr.ellipse([(cx - R) * S, (cy - R) * S, (cx + R) * S, (cy + R) * S], fill=255)
    for k in range(10):                                                                     # teeth
        a = math.radians(k * 36); ca, sa = math.cos(a), math.sin(a); px, py = -sa, ca
        dr.polygon([((cx + ca * (R - 1) + px * 2.2) * S, (cy + sa * (R - 1) + py * 2.2) * S), ((cx + ca * (R - 1) - px * 2.2) * S, (cy + sa * (R - 1) - py * 2.2) * S),
                    ((cx + ca * (R + 3.2) - px * 1.4) * S, (cy + sa * (R + 3.2) - py * 1.4) * S), ((cx + ca * (R + 3.2) + px * 1.4) * S, (cy + sa * (R + 3.2) + py * 1.4) * S)], fill=255)
    dr.ellipse([(cx - 6.8) * S, (cy - 6.8) * S, (cx + 6.8) * S, (cy + 6.8) * S], fill=0)   # hollow
    # crossed swords (cut as 0 where they cross the ring so they read, drawn solid elsewhere)
    def sword(x0, y0, x1, y1):
        dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy); ux, uy = dx / L, dy / L; px, py = -uy, ux
        blade = [((x0 + px * 1.3) * S, (y0 + py * 1.3) * S), ((x1 - ux * 2.5 + px * 1.3) * S, (y1 - uy * 2.5 + py * 1.3) * S), (x1 * S, y1 * S),
                 ((x1 - ux * 2.5 - px * 1.3) * S, (y1 - uy * 2.5 - py * 1.3) * S), ((x0 - px * 1.3) * S, (y0 - py * 1.3) * S)]
        dr.polygon(blade, fill=255)
        gx, gy = x0 + ux * 5.0, y0 + uy * 5.0                                               # crossguard + grip
        dr.line([((gx + px * 3.6) * S, (gy + py * 3.6) * S), ((gx - px * 3.6) * S, (gy - py * 3.6) * S)], fill=255, width=int(1.6 * S))
        dr.ellipse([(x0 - 1.4) * S, (y0 - 1.4) * S, (x0 + 1.4) * S, (y0 + 1.4) * S], fill=255)
    sword(6.0, 33.0, 34.5, 3.5); sword(34.0, 33.0, 5.5, 3.5)
    return im


def vanilla_ink(iid):
    """The glyph frame (part 1) of a vanilla SpellIcn image as a 40x35 L ink mask (frames are white = clear, black =
    ink, multiply draw mode 1026)."""
    global _VLIB
    if _VLIB is None: _VLIB = ilbcodec.read(open(VANILLA_ILB, "rb").read())
    r, px = frame_pixels(_VLIB, iid, 1)
    im = Image.new("L", (W, H), 0); p = im.load()
    for y in range(min(H, len(px))):
        for x in range(min(W, len(px[0]))):
            c = px[y][x]; p[x, y] = max(0, 255 - max(c[0], c[1], c[2]))
    return im


def ink_component(im, seed, thr=80):
    """Keep only the 8-connected ink blob containing `seed` (x, y)."""
    p = im.load(); keep = set(); stack = [seed]
    while stack:
        x, y = stack.pop()
        if (x, y) in keep or not (0 <= x < W and 0 <= y < H) or p[x, y] < thr: continue
        keep.add((x, y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1): stack.append((x + dx, y + dy))
    out = Image.new("L", (W, H), 0); q = out.load()
    for x, y in keep: q[x, y] = p[x, y]
    return out


def paste_max(dst, src, box=(0, 0)):
    """dst = max(dst, src) at box (L images)."""
    x0, y0 = box; d = dst.load(); sp = src.load()
    for y in range(src.height):
        for x in range(src.width):
            v = sp[x, y]
            if v and 0 <= x0 + x < dst.width and 0 <= y0 + y < dst.height: d[x0 + x, y0 + y] = max(d[x0 + x, y0 + y], v)


def glyph_repent():
    """Repent v19 (2026-10-13): subtler frame - thinner streaks and ring at ~70 % ink - with the longer ethereal
    cross floating in the light."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def L(p0, p1, w, fill=255): dr.line([(p0[0] * S, p0[1] * S), (p1[0] * S, p1[1] * S)], fill=fill, width=max(1, int(w * S)))
    for x0, x1 in ((11.0, 6.5), (29.0, 33.5)):
        L((x0, -0.5), (x1, 25.0), 0.95, 178)
    stroke_ellipse(dr, (4.0 * S, 25.6 * S, 36.0 * S, 33.2 * S), int(0.9 * S), 178)
    cross = Image.new("L", (W * S, H * S), 0); cd = ImageDraw.Draw(cross)
    def P(pts, fill=255): cd.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    P([(18.6, 6.0), (21.4, 6.0), (21.2, 11.4), (21.2, 24.2), (18.8, 24.2), (18.8, 11.4)])
    P([(13.2, 11.2), (26.8, 11.2), (26.4, 13.6), (13.6, 13.6)])
    cross = cross.filter(ImageFilter.GaussianBlur(0.55 * S)).point(lambda v: int(v * 0.62))
    paste_max(im, cross)
    return im


def glyph_harvest():
    """Harvest Souls v47 (2026-10-13, user spec; v48 open-mouth/full-join reverted, user hand-edits the export): the corpse from ANIMATE HERO (icon 86) with the skull from DEATH
    STORM (icon 35) above it, joined by a winding tail that emerges from the corpse's chest and rises into the
    skull's jaw - both pieces lifted 1:1, the tail drawn as a tapered S ribbon in the vanilla weight."""
    im = canvas()
    body = vanilla_ink(86).crop((3, 20, 35, 35)); paste_max(im, body.resize((32 * S, 15 * S), Image.BICUBIC), (2 * S, 20 * S))   # corpse x 2..34, y 20..35
    skull = vanilla_ink(35).crop((14, 1, 27, 15)); paste_max(im, skull.resize((13 * S, 14 * S), Image.BICUBIC), (int(15.5 * S), int(0.8 * S)))   # skull x 15.5..28.5, y 0.8..14.8
    g = Image.new("L", (W * S, H * S), 0); gd = ImageDraw.Draw(g)
    def P(pts, fill=255): gd.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def smooth(ctrl, per=10):
        pts = []
        for i in range(len(ctrl) - 1):
            p0 = ctrl[max(i - 1, 0)]; p1 = ctrl[i]; p2 = ctrl[i + 1]; p3 = ctrl[min(i + 2, len(ctrl) - 1)]
            for kk in range(per):
                t = kk / per; t2 = t * t; t3 = t2 * t
                x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                pts.append((x, y))
        pts.append(ctrl[-1]); return pts
    # winding tail: from the chest (13.5, 21.6) up in an S to the skull's jaw (22, 14)
    pts = smooth([(13.4, 21.8), (12.4, 18.6), (15.0, 16.4), (19.4, 16.8), (22.6, 15.2), (22.2, 13.6)])
    n = len(pts) - 1; L_ = []; R_ = []
    for i, (x, y) in enumerate(pts):
        j = min(i, n - 1); dx, dy = pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]
        d = math.hypot(dx, dy) or 1; nx, ny = -dy / d, dx / d; w = (1.3 + 2.9 * (i / n) ** 0.9) / 2
        L_.append((x + nx * w, y + ny * w)); R_.append((x - nx * w, y - ny * w))
    P(L_ + R_[::-1])
    g = g.filter(ImageFilter.GaussianBlur(0.22 * S))
    paste_max(im, g)
    return im


def glyph_wither():
    """Wither v2 (2026-10-12): a wilted flower - thick stem bending over at the top with a drooping bell head, two
    limp leaves hanging from the stem, petals fallen on the ground.  (v1 bare stalk over cracked ground kept as
    glyph_wither_v1.)"""
    im = canvas(); dr = ImageDraw.Draw(im)
    def P(pts, fill=255): dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def strip(spine, w0, w1):                         # tapered ribbon along a polyline
        n = len(spine) - 1; L = []; Rr = []
        for i, (x, y) in enumerate(spine):
            j = min(i, n - 1); dx, dy = spine[j + 1][0] - spine[j][0], spine[j + 1][1] - spine[j][1]
            d = math.hypot(dx, dy) or 1; nx, ny = -dy / d, dx / d; w = (w0 + (w1 - w0) * i / n) / 2
            L.append((x + nx * w, y + ny * w)); Rr.append((x - nx * w, y - ny * w))
        P(L + Rr[::-1])
    # ground line
    P([(6.0, 29.2), (34.0, 29.2), (34.0, 31.0), (6.0, 31.0)])
    # stem: up from the ground, arching over to the right and down (wilted)
    stem = [(15.0, 29.4), (15.2, 24.0), (15.8, 18.0), (17.2, 12.0), (20.0, 7.8), (23.8, 6.2), (27.4, 7.6), (28.6, 11.0)]
    strip(stem, 2.8, 1.4)
    # drooping bell flower hanging from the stem tip, petals splayed downward
    P([(28.6, 10.6), (32.6, 12.2), (34.6, 18.2), (32.8, 23.0), (28.8, 24.8), (24.8, 23.0), (23.0, 18.2), (25.0, 12.2)])   # bell, hanging
    for x, y in ((24.6, 23.0), (28.8, 25.4), (33.0, 23.0)):                                   # petal tips splayed down
        P([(x - 1.8, y - 2.0), (x + 1.8, y - 2.0), (x, y + 3.2)])
    # two limp leaves hanging down from the stem
    P([(15.4, 20.0), (10.2, 20.6), (6.4, 25.8), (8.8, 27.0), (12.0, 23.4), (15.6, 22.6)])          # left leaf, drooping
    P([(16.0, 15.0), (20.6, 15.6), (22.4, 20.8), (20.2, 21.6), (18.6, 18.0), (16.2, 17.2)])        # right leaf, drooping
    # fallen petals
    for x, y in ((9.4, 28.0), (12.0, 27.4), (31.2, 27.8), (34.0, 28.2)):
        P([(x - 1.6, y), (x + 1.6, y), (x, y + 1.4)])
    return im


def glyph_wither_v1():
    """Wither (Death, 2026-10-12): a drooping dead stalk, its head bent over, one leaf falling, over cracked
    ground (two jagged fissure lines) - solid ink."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def P(pts, fill=255): dr.polygon([(x * S, y * S) for x, y in pts], fill=fill)
    def L(pts, w): dr.line([(x * S, y * S) for x, y in pts], fill=255, width=int(w * S))
    # cracked ground: a flat strip with jagged fissures cut out
    P([(4.0, 28.6), (36.0, 28.6), (36.0, 31.8), (4.0, 31.8)])
    P([(13.0, 28.6), (14.6, 29.9), (13.4, 31.8), (12.2, 31.8), (13.3, 30.0), (12.0, 28.6)], 0)
    P([(26.0, 28.6), (24.8, 30.1), (26.4, 31.8), (27.6, 31.8), (26.1, 30.0), (27.2, 28.6)], 0)
    # stalk rising then bending over to the right, tapering; head drooping down
    spine = [(18.5, 28.6), (18.3, 24.0), (18.6, 19.0), (19.6, 14.0), (21.8, 10.2), (25.2, 8.4), (28.4, 9.6), (29.8, 12.6), (29.4, 15.4)]
    for i in range(len(spine) - 1):
        w = 2.2 - 1.3 * i / (len(spine) - 1)
        L([spine[i], spine[i + 1]], w)
        x, y = spine[i + 1]; dr.ellipse([(x - w / 2) * S, (y - w / 2) * S, (x + w / 2) * S, (y + w / 2) * S], fill=255)
    # drooping head: a limp teardrop hanging from the stalk tip
    P([(29.4, 15.0), (31.6, 16.4), (31.8, 19.4), (29.6, 21.4), (27.6, 19.2), (27.8, 16.6)])
    # withered leaves: one curled on the stalk, one falling
    P([(18.5, 20.5), (13.4, 18.2), (10.8, 19.6), (12.4, 21.6), (16.2, 22.0)])
    P([(10.2, 25.4), (7.2, 24.2), (6.0, 26.0), (8.0, 27.4)])
    return im


def glyph_hellfire():
    """Fiery meteor shower: three meteors streaking from the upper left to the lower right, each a solid head
    with a long tapering flame trail (wavy edges), and a burst of impact rays where the big one lands."""
    im = canvas(); dr = ImageDraw.Draw(im)
    def meteor(hx, hy, r, length, ang=math.radians(-135)):
        """head at (hx, hy) (canvas units), trail of `length` units pointing back along `ang` (up-left)."""
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx                                       # perpendicular
        pts = []
        n = 12
        for i in range(n + 1):                                 # one side of the trail head -> tail
            t = i / n; w = r * (1 - t) * (1 + 0.18 * math.sin(t * 11))
            pts.append(((hx + dx * length * t + px * w) * S, (hy + dy * length * t + py * w) * S))
        for i in range(n, -1, -1):
            t = i / n; w = r * (1 - t) * (1 + 0.18 * math.sin(t * 11 + 2))
            pts.append(((hx + dx * length * t - px * w) * S, (hy + dy * length * t - py * w) * S))
        dr.polygon(pts, fill=255)
        dr.ellipse([(hx - r) * S, (hy - r) * S, (hx + r) * S, (hy + r) * S], fill=255)
    meteor(26.5, 22, 3.4, 28)
    meteor(11, 14, 2.1, 16)
    meteor(33, 8, 1.6, 11)
    # impact under the big meteor: a big jagged starburst (12 spikes, alternating long/short) with a hollow
    # centre, plus flying debris chunks
    cx, cy = 26.5, 30.0
    pts = []
    for k in range(24):
        a = math.radians(k * 15 - 90); r = (11.5 if k % 2 == 0 else 5.2) * (1.0 if k % 4 else 1.25)
        pts.append(((cx + math.cos(a) * r) * S, (cy + math.sin(a) * r * 0.55) * S))
    dr.polygon(pts, fill=255)
    dr.ellipse([(cx - 3.2) * S, (cy - 1.9) * S, (cx + 3.2) * S, (cy + 1.9) * S], fill=0)          # hollow core
    for dx, dy, r in ((-12.5, -4.5, 1.4), (12.8, -5.5, 1.2), (-9.5, -8.5, 1.0), (10.5, -9.5, 0.9), (14.5, -1.5, 1.0)):
        dr.ellipse([(cx + dx - r) * S, (cy + dy - r) * S, (cx + dx + r) * S, (cy + dy + r) * S], fill=255)
    return im


def flame_down(dr, cx, top_y, h, w):
    """Flame with the tip pointing DOWN (falling), round top with little tongues."""
    pts = []
    n = 14
    for i in range(n + 1):
        t = i / n
        y = top_y + h * t
        x = cx - w * (1 - t) * (0.5 + 0.16 * math.sin(t * 8))
        pts.append((x, y))
    for i in range(n, -1, -1):
        t = i / n
        y = top_y + h * t
        x = cx + w * (1 - t) * (0.5 + 0.16 * math.sin(t * 8 + 1.2))
        pts.append((x, y))
    dr.polygon(pts, fill=255)
    # tongues at the top edge
    for k in (-0.35, 0.0, 0.3):
        dr.polygon([(cx + k * w - 0.13 * w, top_y + 0.6 * S), (cx + k * w + 0.13 * w, top_y + 0.6 * S), (cx + k * w, top_y - 0.22 * h)], fill=255)


IMPORT_DIR = os.path.join(GAME, "art import export")
def import_mask(path):
    """A hand-edited glyph PNG -> 40x35 ink levels (white/transparent = 0, black = 255)."""
    im = Image.open(path).convert("RGBA")
    if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
    p = im.load()
    return [[max(0, min(255, int((255 - max(p[x, y][0], p[x, y][1], p[x, y][2])) * p[x, y][3] / 255))) if p[x, y][3] else 0 for x in range(W)] for y in range(H)]


def downsample(im):
    """8x ink canvas -> 40x35 ink levels 0..255 (anti-aliased: vanilla glyphs carry ~60 grey levels, so the
    edges stay smooth instead of jagged; faint ink < 24 is dropped)."""
    sm = im.resize((W, H), Image.LANCZOS)
    p = sm.load()
    return [[(p[x, y] if p[x, y] >= 24 else 0) for x in range(W)] for y in range(H)]


def stroke_ellipse(dr, box, width, fill=255):
    """Outline ellipse (ring) by drawing the ellipse and clearing the inside."""
    x0, y0, x1, y1 = box
    dr.ellipse(box, fill=fill)
    dr.ellipse([x0 + width, y0 + width, x1 - width, y1 - width], fill=0)


GLYPHS = {"bloodbath": glyph_bloodbath, "hellhound": glyph_hellhound, "hellfire": glyph_hellfire,
          "rejuvenate": glyph_rejuvenate, "wither": glyph_wither, "repent": glyph_repent, "harvest": glyph_harvest,
          "martyr": glyph_martyr, "cleansing": glyph_cleansing, "phoenix": glyph_phoenix, "starfire": glyph_starfire,
          "ashes": glyph_ashes,
          "oil_spring": glyph_oil_spring, "lionheart": glyph_lionheart, "forge_blast": glyph_forge_blast, "arms_race": glyph_arms_race,
          "sandstorm": glyph_sandstorm, "implosion": glyph_implosion, "frenzy": glyph_frenzy, "drought": glyph_drought,
          "bloodboil": glyph_bloodboil, "scald": glyph_scald, "steampower": glyph_steampower,
          "direwolf": glyph_direwolf, "rotaway": glyph_rotaway, "werewolf": glyph_werewolf, "threads": glyph_threads3,
          "awaken": glyph_awaken, "forest_blessing": glyph_forest_blessing, "golden_age": glyph_golden_age, "ent": glyph_ent,
          "mammoth": glyph_mammoth, "hurl_boulder": glyph_hurl_boulder, "gravity_well": glyph_gravity_well,
          "slow": glyph_slow, "crocodile": glyph_crocodile, "swampwalk": glyph_swampwalk, "overgrowth": glyph_overgrowth,
          "holywater": glyph_holywater, "bountiful": glyph_bountiful, "blesseddew": glyph_blesseddew, "worldhealer": glyph_worldhealer,
          "soulsiphon": glyph_soulsiphon, "plague": glyph_plague, "blacktide": glyph_blacktide, "hydra": glyph_hydra,
          "mistystep": glyph_mistystep, "flashfreeze": glyph_flashfreeze, "nimue": glyph_nimue, "iceage": glyph_iceage,
          "banshee": glyph_banshee, "suffocate_lungs": glyph_suffocate, "borrowtime": glyph_borrowtime, "succubus": glyph_succubus,
          "chorus": glyph_chorus, "inspire": glyph_inspire, "secondwind": glyph_secondwind, "angelwings": glyph_angelwings, "sanctify": glyph_sanctify, "miracle": glyph_miracle, "undying": glyph_undying, "callofdead": glyph_callofdead, "gust": glyph_gust, "crosswind": glyph_crosswind, "suspend": glyph_suspend, "staticshield": glyph_staticshield, "mendwalls": glyph_mendwalls, "mimic": glyph_mimic3, "lucky": glyph_lucky, "transmutation": glyph_transmutation, "reversalspell": glyph_reversalspell, "essenceshift": glyph_essenceshift, "cityspy": glyph_cityspy, "royalambition": glyph_royalambition, "magicmissile": glyph_magicmissile, "pyroclasm": glyph_pyroclasm, "smokescreen": glyph_smokescreen, "walloflames": glyph_walloflames3, "seaserpent": glyph_seaserpent, "flashflood": glyph_flashflood, "crashingwave": glyph_crashingwave, "riteseas": glyph_riteseas2, "tectonic": glyph_tectonic, "depthsofplenty": glyph_depthsofplenty, "steadfast": glyph_steadfast}


def copied_mask(src_path, src_id):
    """Ink mask (0..255) from frame 1 (black glyph on the 0xFFFF key) of an image in another SpellIcn ILB."""
    src = ilbcodec.read(open(src_path, "rb").read())
    r, px = frame_pixels(src, src_id, 1)
    assert (r["totw"], r["toth"]) == (W, H) and r["size"] == r["cw"] * r["ch"] * 2, r
    m = [[0] * W for _ in range(H)]
    for y in range(r["ch"]):
        for x in range(r["cw"]):
            m[r["cy"] + y][r["cx"] + x] = 255 - min(px[y][x])
    return m


def icon_cloud(lib, name):
    spec = CLOUDS.get(name, "blend")
    if spec == "blend": return blended_cloud(lib)
    if isinstance(spec, tuple): return blended_cloud(lib, spec[0], spec[1])
    r, px = frame_pixels(lib, spec, 0); return px


# ---------------------------------------------------------------- record building
def bbox(mask):
    xs = [x for y in range(H) for x in range(W) if mask[y][x] > 0]; ys = [y for y in range(H) for x in range(W) if mask[y][x] > 0]
    x0, x1, y0, y1 = max(min(xs) - 1, 0), min(max(xs) + 2, W), max(min(ys) - 1, 0), min(max(ys) + 2, H)
    return x0, y0, x1 - x0, y1 - y0


def make_records(template0, template1, name, cloud, mask, pix_off):
    """Two Rec dicts (frame 0 cloud, frame 1 glyph) cloned from the vanilla templates + their pixel bytes."""
    r0 = ilbcodec.Rec(template0); r1 = ilbcodec.Rec(template1)
    nm = name.encode()
    r0.update(name=nm, w=W, h=H, xs=0, ys=0, sub=0, size=W * H * 2, off=pix_off, totw=W, toth=H, cw=W, ch=H, cx=0, cy=0, transp=0xFFFF)
    cx, cy, cw, ch = bbox(mask)
    r1.update(name=nm, w=W, h=H, xs=0, ys=0, sub=0, size=cw * ch * 2, off=pix_off + W * H * 2, totw=W, toth=H, cw=cw, ch=ch, cx=cx, cy=cy, transp=0xFFFF)
    b0 = bytearray()
    for y in range(H):
        for x in range(W):
            v = rgb565(*cloud[y][x])
            if v == 0xFFFF: v = 0xFFDF                           # never the key colour
            b0 += struct.pack("<H", v)
    b1 = bytearray()
    for y in range(cy, cy + ch):
        for x in range(cx, cx + cw):
            ink = mask[y][x]
            if ink <= 0: v = 0xFFFF                                 # key = parchment shows through
            else:
                g = 255 - ink; v = rgb565(g, g, g)
                if v == 0xFFFF: v = 0xFFDF
            b1 += struct.pack("<H", v)
    return r0, r1, bytes(b0) + bytes(b1)


def preview(clouds, masks, out):
    cols = 4; cell = 44; big_h = H * 4 + 6
    sheet = Image.new("RGB", (cols * cell * 2 + 180, len(masks) * big_h), (214, 196, 160))
    dr = ImageDraw.Draw(sheet)
    for row, (name, mask) in enumerate(masks.items()):
        cloud = clouds[name]
        c = Image.new("RGB", (W, H)); cp = c.load()
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gp = g.load()
        for y in range(H):
            for x in range(W):
                cp[x, y] = cloud[y][x]
                if mask[y][x] > 0: gv = 255 - mask[y][x]; gp[x, y] = (gv, gv, gv, 255)
        comp = c.copy(); comp.paste(g, (0, 0), g)
        y0 = row * cell * 2
        sheet.paste(c.resize((W * 2, H * 2), Image.NEAREST), (0, y0))
        sheet.paste(g.resize((W * 2, H * 2), Image.NEAREST), (cell * 2, y0), g.resize((W * 2, H * 2), Image.NEAREST))
        sheet.paste(comp.resize((W * 2, H * 2), Image.NEAREST), (cell * 4, y0))
        big = comp.resize((W * 4, H * 4), Image.NEAREST)
        sheet.paste(big, (cell * 6 + 10, row * big_h))
        dr.text((cell * 4, y0 + H * 2 + 2), name, fill=(0, 0, 0))
    sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
    sheet.save(out); print("preview ->", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--export", action="store_true", help="write every glyph to <game>/art import export/<name>.png (40x35, black ink on white) + <name>_x4.png composite preview")
    a = ap.parse_args()
    bak = bak_path(ILB, BAK_SUFFIX)
    if a.revert:
        if not os.path.exists(bak): print("no backup"); return 1
        shutil.copy2(bak, ILB); print("restored from", bak); return 0
    raw = open(ILB, "rb").read()
    lib = ilbcodec.read(raw)
    assert ilbcodec.write(lib) == raw, "codec round-trip failed on the live ILB"
    clouds = {n: icon_cloud(lib, n) for n in ICONS.values() if n not in COPIES}
    masks = {n: downsample(GLYPHS[n]()) for n in ICONS.values() if n not in COPIES}
    # 2026-10-13: hand-edited art.  <game>/art import export/<name>.png (any size; white = clear, black = ink, grey =
    # anti-aliasing; alpha honoured) OVERRIDES the drawn glyph when present - delete the file to go back to the code.
    for n, (src_path, src_id) in GLYPH_COPIES.items():
        masks[n] = copied_mask(src_path, src_id)
    for n in list(masks):
        p = os.path.join(IMPORT_DIR, n + ".png")
        if os.path.exists(p) and not a.export:
            masks[n] = import_mask(p); print("imported", p)
    if a.export:
        os.makedirs(IMPORT_DIR, exist_ok=True)
        for n, m in masks.items():
            im = Image.new("L", (W, H), 255); p = im.load()
            for y in range(H):
                for x in range(W): p[x, y] = 255 - m[y][x]
            im.save(os.path.join(IMPORT_DIR, n + ".png"))
            comp = Image.new("RGB", (W, H)); cp = comp.load(); cl = clouds[n]
            for y in range(H):
                for x in range(W):
                    k = m[y][x] / 255.0; c = cl[y][x]
                    cp[x, y] = (int(c[0] * (1 - k)), int(c[1] * (1 - k)), int(c[2] * (1 - k)))
            comp.resize((W * 4, H * 4), Image.NEAREST).save(os.path.join(IMPORT_DIR, n + "_x4.png"))
            print("exported", os.path.join(IMPORT_DIR, n + ".png"))
        return 0
    if a.preview:
        preview(clouds, masks, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dual_icons_preview.png")); return 0
    t_img = next(i for i in lib["images"] if i["id"] == DEATH_ID)
    pix = bytearray(lib["pixeldata"])
    # our images are always the LAST records with their pixels at the tail: drop them (and their pixels) first
    STALE = {204}                                        # ids this script once appended and no longer owns (2026-10-12)
    mine = [i for i in lib["images"] if i["id"] in ICONS or i["id"] in STALE]
    if mine:
        cut = min(p["off"] for i in mine for p in i["parts"])
        lib["images"] = [i for i in lib["images"] if i["id"] not in ICONS and i["id"] not in STALE]
        assert all(p["off"] + p["size"] <= cut for i in lib["images"] for p in i["parts"]), "foreign pixels after ours"
        pix = pix[:cut]
        print("rebuilding %d existing icon records" % len(mine))
    added = []
    for iid, name in ICONS.items():
        if name in COPIES:                                   # verbatim copy of an image from another ILB
            src_path, src_id = COPIES[name]
            src = ilbcodec.read(open(src_path, "rb").read()); simg = next(i for i in src["images"] if i["id"] == src_id)
            blob = b""; recs = []
            for p in simg["parts"]:
                r = ilbcodec.Rec(p); r.update(off=len(pix) + len(blob), name=("SI-AoWx-%s.BMP" % name).encode()); recs.append(r)
                blob += src["pixeldata"][p["off"]:p["off"] + p["size"]]
            pix += blob
            lib["images"].append({"id": iid, "composite": simg["composite"], "parts": recs, "empty": False})
            added.append((iid, "copy of %s#%d" % (os.path.basename(src_path), src_id)))
            continue
        r0, r1, blob = make_records(t_img["parts"][0], t_img["parts"][1], "SI-AoWx-%s.BMP" % name, clouds[name], masks[name], len(pix))
        pix += blob
        lib["images"].append({"id": iid, "composite": True, "parts": [r0, r1], "empty": False})
        added.append((iid, r1["cx"], r1["cy"], r1["cw"], r1["ch"]))
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib)
    chk = ilbcodec.read(out)
    assert [i["id"] for i in chk["images"]][-len(ICONS):] == list(ICONS), "re-read failed"
    print("ILB %d -> %d bytes; icons %s" % (len(raw), len(out), added))
    if out == raw: print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bak): shutil.copy2(ILB, bak); print("backup ->", bak)
    open(ILB, "wb").write(out); print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
