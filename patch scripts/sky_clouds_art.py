#!/usr/bin/env python3
r"""
Sky polish art + reference model (2026-10-31).

User: "add some polish to the sky terrain, make it look nicer with subtle animation; the combat sky shows a water
animation - make it match; add a 'Clear Sky' terrain, more transparent with animated transparent clouds".

Everything here is deterministic (fixed seeds) so the patch scripts can rebuild byte-identical data:
  sky_tiles()    8 strategic Sky tiles (48x32, terrain 0xE): deep twilight blue, faint mottling, a few stars
  clear_tiles()  4 Clear Sky tiles (terrain 0xE too, own ResourceIDs 0x5A1B000x): pale day-sky blue
  cloud_tex()    256x256 periodic cloud density (bytes), sampled in WORLD pixels by the overlay
  luts()         per-kind cloud alpha curve (256 B each) + 64-step twinkle table
  model(...)     integer reference of the AoWEPACK per-pixel overlay (565), used for previews + asm cross-check
  combat_ilbs()  SKYHEX00 / SKYANM00 rebuilt: base tiles = sky_tiles, the water-wave frames -> drifting cloud wisps
--preview <dir> writes tile sheets + animated previews (Firmament over a fake surface, and a plain level).
"""
import math, os, struct, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import ilb  # noqa: E402

W, H = 48, 32
SPANS = [(15 - r, 33 + r) if r < 16 else (r - 16, 64 - r) for r in range(32)]   # Ziggurat's hex row spans
NPIX = sum(e - s for s, e in SPANS)                                               # 1056

# ---- overlay parameters (shared with the asm) -------------------------------------------------------------------
SKY_SURF = 0x30          # Sky: surface weight /256 on the Firmament (Ziggurat had ~0x1D)
CLR_SURF = 0xA0          # Clear Sky: surface weight /256
SKY_CLOUD = (196, 200, 238)
CLR_CLOUD = (246, 248, 252)
CHS_GLOW = (196, 120, 255)  # Chasm: lightning-web colour
CHS_HAZE = (92, 34, 136)    # Chasm: faint violet haze between the black clouds
CHS_WEB2 = (150, 96, 220)   # Chasm: far lightning webs (very faint)
CHS_CGLOW = (150, 92, 205)  # Chasm: black clouds lit by nearby flashes
WEB2_K = 80                 # /256 strength of the far webs
CPULSE_MS = 90              # ms per cloud-pulse step (64 steps = one slow breath)
CP_SKY, CP_CHS = 90, 70     # /256: Sky/Clear clouds up to +35 % opacity, Chasm black clouds up to -27 % darkness
# v3: both cloud layers bilinear-filtered, positions in 1/16 px -> smooth sub-pixel drift.
# layer 1 at 1/2 resolution, layer 2 at 1/4 (pattern period 512 / 1024 world px).
SPEED = dict(ox1=9, oy1=26, ox2=8, oy2=-19, owx=62, owy=-90, owx2=-45, owy2=70)   # ms per 1/16 px (negative = other direction)
TWINKLE_MS = 60          # ms per twinkle-table step
FLASH_MS = 55            # ms per Chasm lightning-flash step
STAR_MIN = 44            # 5/6/5 brightness sum that counts as a star pixel


def _periodic_noise(n, fx, fy, rng):
    """value noise on an n x n torus with fx x fy lattice cells, smooth (cosine) interpolation"""
    g = rng.random((fy, fx))
    ys = np.arange(n) * fy / n; xs = np.arange(n) * fx / n
    y0 = np.floor(ys).astype(int); x0 = np.floor(xs).astype(int)
    ty = (1 - np.cos((ys - y0) * math.pi)) / 2; tx = (1 - np.cos((xs - x0) * math.pi)) / 2
    y1 = (y0 + 1) % fy; x1 = (x0 + 1) % fx
    a = g[y0][:, x0]; b = g[y0][:, x1]; c = g[y1][:, x0]; d = g[y1][:, x1]
    tx = tx[None, :]; ty = ty[:, None]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def cloud_tex():
    rng = np.random.default_rng(0x5C1E)
    acc = np.zeros((256, 256)); amp = 1.0; tot = 0
    for fx, fy in ((3, 4), (6, 8), (12, 16), (24, 32), (48, 64)):   # a little squashed (iso view)
        acc += amp * _periodic_noise(256, fx, fy, rng); tot += amp; amp *= 0.52
    acc /= tot
    lo, hi = np.percentile(acc, 1), np.percentile(acc, 99)
    return np.clip((acc - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)


def web_tex():
    """256x256 periodic lightning webs: domain-warped Voronoi borders (coarse + fine), only in patches"""
    rng = np.random.default_rng(0x3EB)
    yy, xx = np.mgrid[0:256, 0:256].astype(float)
    wx = xx + 14 * (_periodic_noise(256, 8, 8, rng) - 0.5) + 5 * (_periodic_noise(256, 32, 32, rng) - 0.5)
    wy = yy + 14 * (_periodic_noise(256, 8, 8, rng) - 0.5) + 5 * (_periodic_noise(256, 32, 32, rng) - 0.5)
    out = np.zeros((256, 256))
    for n, width, weight in ((26, 3.2, 1.0), (90, 1.7, 0.75)):
        pts = rng.random((n, 2)) * 256
        d1 = np.full((256, 256), 1e9); d2 = np.full((256, 256), 1e9)
        for px, py in pts:
            for ox in (-256, 0, 256):
                for oy in (-256, 0, 256):
                    d = np.hypot(wx - px - ox, wy - py - oy)
                    d2 = np.where(d < d1, d1, np.minimum(d2, d)); d1 = np.minimum(d1, d)
        e = np.clip(1 - (d2 - d1) / width, 0, 1) ** 1.4 * weight
        out = np.maximum(out, e)
    m = _periodic_noise(256, 4, 4, rng)
    m = np.clip((m - 0.35) / 0.3, 0, 1)
    return np.clip(out * m * 255, 0, 255).astype(np.uint8)


def luts():
    def curve(th, soft, top):
        out = []
        for c in range(256):
            x = (c - th) / soft
            x = 0 if x <= 0 else 1 if x >= 1 else x * x * (3 - 2 * x)
            out.append(int(round(x * top)))
        return bytes(out)

    def ridge(mid, w, top):
        return bytes(int(round(top * max(0.0, 1 - abs(c - mid) / w) ** 2)) for c in range(256))
    tw = []
    for i in range(64):                     # bright most of the time, a soft dip to ~1/4 once per cycle
        d = min(abs(i - 40), 64 - abs(i - 40))
        dip = 0.5 + 0.5 * math.cos(min(d / 9.0, 1.0) * math.pi)
        tw.append(int(round(255 - 190 * dip)))
    flash = [30] * 64                      # dim glow, a double lightning flicker + a smaller one per cycle
    for i, v in ((8, 255), (9, 140), (10, 235), (11, 120), (12, 80), (37, 190), (38, 100), (39, 70)):
        flash[i] = v
    web = bytes(int(round(185 * max(0.0, (c - 40) / 215) ** 1.3)) for c in range(256))
    return {"sky": curve(90, 110, 125), "clear": curve(98, 95, 175), "dark": curve(118, 90, 205), "web": web,
            "haze": bytes(int(round(118 * min(1.0, max(0.0, (120 - c) / 90)))) for c in range(256)),
            "twinkle": bytes(tw), "flash": bytes(flash),
            "cpulse": bytes(int(round(255 * math.sin(i / 64 * math.pi) ** 2)) for i in range(64))}


def _hexmask():
    m = np.zeros((H, W), bool)
    for r, (s, e) in enumerate(SPANS):
        m[r, s:e] = True
    return m


def _q565(a):
    """round-trip an RGB uint8 array through 565 the way the ILB decoder expands it"""
    r = (a[..., 0] >> 3); g = (a[..., 1] >> 2); b = (a[..., 2] >> 3)
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], -1).astype(np.uint8)


def _tiles(n, seed, base, mott, stars):
    rng = np.random.default_rng(seed)
    big = _periodic_noise(256, 32, 32, rng) * 0.5 + _periodic_noise(256, 64, 64, rng) * 0.5
    out = []
    m = _hexmask()
    for k in range(n):
        ox, oy = (k * 77) % 208, (k * 131) % 224
        f = big[oy:oy + H, ox:ox + W]
        f = (f - f.mean()) / (f.std() + 1e-6)
        img = np.zeros((H, W, 3), float)
        for i in range(3):
            img[..., i] = base[i] + f * mott[i]
        if stars:
            for _ in range(rng.integers(3, 7)):
                x, y = int(rng.integers(6, W - 6)), int(rng.integers(5, H - 5))
                if not m[y, x]:
                    continue
                v = float(rng.uniform(0.55, 1.0))
                img[y, x] = img[y, x] * (1 - v) + np.array([235, 236, 255]) * v
                if v > 0.85:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        img[y + dy, x + dx] = img[y + dy, x + dx] * 0.55 + np.array([170, 175, 235]) * 0.45
        rgb = _q565(np.clip(img, 0, 255).astype(np.uint8))
        rgba = np.zeros((H, W, 4), np.uint8); rgba[..., :3] = rgb; rgba[..., 3] = m * 255
        out.append(rgba)
    return out


def sky_tiles():
    return _tiles(8, 0x51C1, (30, 38, 92), (2, 2, 4), True)


def clear_tiles():
    return _tiles(4, 0xC1EA, (128, 176, 228), (2, 3, 3), False)


def packed(tile):
    """565 words of a tile in hex-span order (the overlay's per-hex pixel index)"""
    out = []
    for r, (s, e) in enumerate(SPANS):
        for x in range(s, e):
            p = tile[r, x]
            out.append(((int(p[0]) >> 3) << 11) | ((int(p[1]) >> 2) << 5) | (int(p[2]) >> 3))
    assert len(out) == NPIX
    return out


# ---- integer reference model (565) --------------------------------------------------------------------------------
def unpack(p):
    return (p >> 11) & 31, (p >> 5) & 63, p & 31


def pack(r, g, b):
    return (r << 11) | (g << 5) | b


def offsets(t):
    o = {k: (t // v if v > 0 else -(t // -v)) for k, v in SPEED.items()}
    o["tw"] = t // TWINKLE_MS
    o["tf"] = t // FLASH_MS
    o["tc"] = t // CPULSE_MS
    return o


def bil(tex, u, v, s):
    """bilinear sample; u, v in 1/16 px, texel = 2**s px"""
    fx = (u >> s) & 15; ix = (u >> (s + 4)) & 255
    fy = (v >> s) & 15; iy = (v >> (s + 4)) & 255
    ix1 = (ix + 1) & 255; iy1 = (iy + 1) & 255
    a, b = int(tex[iy, ix]), int(tex[iy, ix1]); c, d = int(tex[iy1, ix]), int(tex[iy1, ix1])
    top = a * 16 + (b - a) * fx; bot = c * 16 + (d - c) * fx
    return (top * 16 + (bot - top) * fy) >> 8


def _mix(r, g, b, col, a):
    cr, cg, cb = col[0] >> 3, col[1] >> 2, col[2] >> 3
    return r + (((cr - r) * a) >> 8), g + (((cg - g) * a) >> 8), b + (((cb - b) * a) >> 8)


def model_pixel(p, kind, sp, wx, wy, t, tex, L, web=None):
    """p = 565 screen pixel (matched a tile), kind 0 Sky / 1 Clear / 2 Chasm, sp = surface 565 or 0, world px"""
    o = offsets(t)
    wxe, wye = wx & ~3, wy & ~1                     # cloud field computed once per 4x2 pixel block
    c1 = bil(tex, wxe * 16 + o["ox1"], wye * 16 + o["oy1"], 1)
    c2 = bil(tex, wxe * 16 + o["ox2"], wye * 16 + o["oy2"], 2)
    c = (c1 + c2) >> 1
    cp = L["cpulse"][((bil(tex, wxe * 16 + o["ox2"], wye * 16 + o["oy2"], 3) >> 2) + o["tc"]) & 63]
    r, g, b = unpack(p)
    if kind == 2:
        h = L["haze"][c]
        hr, hg, hb = CHS_HAZE[0] >> 3, CHS_HAZE[1] >> 2, CHS_HAZE[2] >> 3
        r = r + (((hr - r) * h) >> 8); g = g + (((hg - g) * h) >> 8); b = b + (((hb - b) * h) >> 8)
        ad = L["dark"][c]
        ad -= (((ad * cp) >> 8) * CP_CHS) >> 8
        r -= (r * ad) >> 8; g -= (g * ad) >> 8; b -= (b * ad) >> 8
        ph = int(tex[(wy >> 3) & 255, (wx >> 3) & 255]) >> 2
        fl = L["flash"][(o["tf"] + ph) & 63]
        w2 = int(web[((wy * 32 + o["owy2"]) >> 4) & 255, ((wx * 32 + o["owx2"]) >> 4) & 255])
        a2 = (((L["web"][w2] * L["flash"][(o["tf"] + ph + 21) & 63]) >> 8) * WEB2_K) >> 8   # far webs
        r, g, b = _mix(r, g, b, CHS_WEB2, a2)
        w = int(web[((wy * 16 + o["owy"]) >> 4) & 255, ((wx * 16 + o["owx"]) >> 4) & 255])
        a = (L["web"][w] * fl) >> 8
    else:
        if kind == 0 and (r + (g >> 1) + b) >= STAR_MIN:          # star: twinkle (scale toward black)
            k = L["twinkle"][(((wx >> 1) * 7 + (wy >> 1) * 13) + o["tw"]) & 63]
            r, g, b = (r * k) >> 8, (g * k) >> 8, (b * k) >> 8
        if sp:
            ws = CLR_SURF if kind else SKY_SURF
            sr, sg, sb = unpack(sp)
            r = (r * (256 - ws) + sr * ws) >> 8; g = (g * (256 - ws) + sg * ws) >> 8
            b = (b * (256 - ws) + sb * ws) >> 8
        a = L[("sky", "clear")[kind]][c]
        a += (((a * cp) >> 8) * CP_SKY) >> 8
    cr, cg, cb = (SKY_CLOUD, CLR_CLOUD, CHS_GLOW)[kind]
    cr >>= 3; cg >>= 2; cb >>= 3
    r = r + (((cr - r) * a) >> 8); g = g + (((cg - g) * a) >> 8); b = b + (((cb - b) * a) >> 8)
    return pack(r, g, b)


def chasm_tiles(game_dir):
    """the 15 strategic Chasm tiles (Release.hss Hu_wl, terrain 0xB) as RGBA arrays, in record order"""
    import sky_chasm_combat_art as C
    return [np.array(t.convert("RGBA")) for t in C.zig_tiles(game_dir, "chasm")]


WEB = None


def model_frame(tile_of, surface, t, tex, L, cols=12, rows=8):
    """tile_of(x,y) -> (kind, rgba tile); surface = HxWx3 uint8 or None; returns RGB image of the map"""
    from PIL import Image
    Wp, Hp = cols * 32 + 16, rows * 32 + 16
    scr = np.zeros((Hp, Wp), np.int64)
    kinds = {}
    for x in range(cols):
        for y in range(rows):
            kind, tile = tile_of(x, y)
            px, py = x * 32, y * 32 + (x & 1) * 16
            for r, (s, e) in enumerate(SPANS):
                if py + r >= Hp:
                    continue
                for xx in range(s, min(e, Wp - px)):
                    q = tile[r, xx]
                    scr[py + r, px + xx] = ((int(q[0]) >> 3) << 11) | ((int(q[1]) >> 2) << 5) | (int(q[2]) >> 3)
            kinds[(x, y)] = (kind, packed(tile))
    out = scr.copy()
    for (x, y), (kind, pk) in kinds.items():
        px, py = x * 32, y * 32 + (x & 1) * 16
        k = 0
        for r, (s, e) in enumerate(SPANS):
            for xx in range(s, e):
                sy, sx = py + r, px + xx
                if sy < Hp and sx < Wp and scr[sy, sx] == pk[k]:
                    sp = 0
                    if surface is not None:
                        q = surface[sy % surface.shape[0], sx % surface.shape[1]]
                        sp = ((int(q[0]) >> 3) << 11) | ((int(q[1]) >> 2) << 5) | (int(q[2]) >> 3)
                    out[sy, sx] = model_pixel(int(scr[sy, sx]), kind, sp, sx, sy, t, tex, L, WEB)
                k += 1
    rgb = np.stack([((out >> 11) & 31) << 3, ((out >> 5) & 63) << 2, (out & 31) << 3], -1).astype(np.uint8)
    return Image.fromarray(rgb)


def fake_surface(game_dir):
    """a fake 'surface far below' (grass/water/forest blotches, 60 % scale) for previews"""
    rng = np.random.default_rng(7)
    n = _periodic_noise(256, 6, 6, rng)
    img = np.zeros((256, 256, 3), np.uint8)
    img[...] = (70, 120, 52)
    img[n < 0.38] = (40, 70, 140)
    img[(n > 0.62)] = (38, 82, 40)
    d = _periodic_noise(256, 32, 32, rng)
    img = np.clip(img.astype(int) + ((d - 0.5) * 30)[..., None], 0, 255).astype(np.uint8)
    return img


# ---- combat (comb_res Sky hexagon = Waterhex/WaterAnm layout) -----------------------------------------------------
CLEAR_RAMP = [(0.00, (96, 140, 200)), (0.35, (120, 168, 222)), (0.70, (170, 202, 238)), (1.00, (240, 246, 252))]


def _quiet_anm(lib):
    """every animation frame -> one pixel drawn at 1 % (the overlay animates these hexagons now)"""
    from PIL import Image
    for im in lib.images:
        rec = im.primary
        if not rec.get("size"):
            continue
        w, h, _ = ilb.decode_record(lib, rec)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); img.putpixel((w // 2, h // 2), (30, 38, 92, 255))
        ilb.encode_image(lib, rec, img)
        rec["drawMode"] = 770
        rec["blendValue"] = 1
    return lib


def combat_ilbs(game_dir):
    """Combat Sky / Clear Sky / Chasm hexagon art (comb_res children 581 / 583 / 582).
    HEX: base tiles H_Wa2 = the strategic tiles (Sky 8, Clear 4, Chasm 15; k % n) so the overlay's tile tables match;
         Clear's edge pieces = Waterhex recoloured light blue.  ANM: silenced - the overlay draws the clouds."""
    from PIL import Image
    import sky_chasm_combat_art as C
    out = {}
    hexlib = ilb.read(open(os.path.join(game_dir, "Images", "SKYHEX00.ILB"), "rb").read())
    st = sky_tiles()
    k = 0
    for im in hexlib.images:
        rec = im.primary
        if (rec.get("name") or "").lower().startswith("h_wa2"):
            ilb.encode_image(hexlib, rec, Image.fromarray(st[k % len(st)], "RGBA")); k += 1
    assert k == 16
    out[r"Images\SKYHEX00.ILB"] = ilb.write(hexlib)
    wl = ilb.read(open(os.path.join(game_dir, "Images", "Waterhex.ILB"), "rb").read())
    ct = [Image.fromarray(t, "RGBA") for t in clear_tiles()]
    out[r"Images\CLRHEX00.ILB"] = ilb.write(C.recolour(wl, CLEAR_RAMP, ct))
    src = ilb.read(open(os.path.join(game_dir, "Images", "WaterAnm.ILB"), "rb").read())
    q = ilb.write(_quiet_anm(src))
    for n in ("SKYANM00", "CLRANM00", "CHSANM00"):
        out[r"Images\%s.ILB" % n] = q
    return out


def preview(out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    global WEB
    st, ct, tex, L = sky_tiles(), clear_tiles(), cloud_tex(), luts()
    WEB = web_tex()
    sheet = Image.new("RGBA", (12 * 52, 36), (255, 0, 255, 255))
    for i, t in enumerate(st + ct):
        sheet.alpha_composite(Image.fromarray(t, "RGBA"), (i * 52, 2))
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(os.path.join(out_dir, "tiles.png"))
    Image.fromarray(tex).save(os.path.join(out_dir, "cloudtex.png"))
    surf = fake_surface(gd)
    chs = chasm_tiles(gd)
    rng = np.random.default_rng(3)
    cols, rows = 21, 12
    pick = {(x, y): int(rng.integers(0, 15)) for x in range(cols) for y in range(rows)}

    def sky_of(x, y):
        if x < 7:
            return 0, st[pick[(x, y)] % 8]
        if x < 14:
            return 1, ct[pick[(x, y)] % 4]
        return 2, chs[pick[(x, y)]]
    for t in (0, 440, 3000, 6000):
        f = model_frame(sky_of, None, t, tex, L, cols, rows)
        f.resize((f.width * 2, f.height * 2), Image.NEAREST).save(os.path.join(out_dir, "plain_t%d.png" % t))
    f = model_frame(sky_of, surf, 0, tex, L, cols, rows)
    f.resize((f.width * 2, f.height * 2), Image.NEAREST).save(os.path.join(out_dir, "firm_t0.png"))

if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
