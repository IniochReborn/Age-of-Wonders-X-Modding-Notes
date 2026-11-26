from PIL import Image, ImageDraw, ImageFilter
import numpy as np, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sph_build as SB                       # star_mask(), chunky(), glyph()  (re-running it rewrites the icons; we overwrite after)
D = 'sphere_icons/'
B = '../../backup/'
yy, xx = np.mgrid[0:96, 0:96]; R = np.hypot(yy - 47.5, xx - 47.5); TH = np.arctan2(yy - 47.5, xx - 47.5)
VAN = ['air', 'death', 'earth', 'fire', 'life', 'water']
imgs = {n: np.asarray(Image.open(D + n + '.png').convert('RGBA'), float) for n in VAN}


def lum(o):
    return o[..., :3] @ np.array([0.299, 0.587, 0.114])


# normalised luminance per orb; glyph pixels = clearly darker than the orb's own radial level
N, G = [], []
for n in VAN:
    l = lum(imgs[n]); ref = np.median(l[(R > 30) & (R < 34)])
    ln = l / ref
    prof = np.array([np.median(ln[(R >= k) & (R < k + 1)]) for k in range(49)])
    N.append(ln); G.append((ln < prof[np.clip(R.astype(int), 0, 48)] * 0.72) & (R < 34))
N, G = np.array(N), np.array(G)
# radial profile from non-glyph pixels of all orbs
prof = np.zeros(49)
for k in range(49):
    m = (R >= k) & (R < k + 1)
    v = N[:, m][~G[:, m]]
    prof[k] = np.median(v) if v.size else 1.0
prof[:28] = np.maximum(prof[:28], prof[28] * 0.97)          # vanilla centres are a flat light field (glyphs biased the median)
P = prof[np.clip(R.astype(int), 0, 48)]
# grain residual: mean over orbs where that pixel is non-glyph; holes filled from the 180-degree rotated residual
res = np.where(~G, N - P, np.nan)
grain = np.nanmean(res, 0)
rot = np.rot90(grain, 2)
grain = np.where(np.isnan(grain), rot, grain)
grain = np.where(np.isnan(grain), 0, grain)
cnt = (~G).sum(0)
grain = np.where(cnt < 4, np.clip(grain, -0.05, 0.12) * 0.6, grain)     # glyph-covered centre: no dark mottling
grain = np.asarray(Image.fromarray(((grain + 0.5) * 255).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)), float) / 255 - 0.5
grain = np.clip(grain, -0.25, 0.25) * 0.8
L = np.clip(P + grain, 0, 1.6)
alpha = imgs['air'][..., 3]
dash = (imgs['air'][..., 2] > imgs['air'][..., 0] + 60) & (R > 36)       # vanilla's blue rim dashes


def colourise(dark, mid, light):
    dark, mid, light = (np.array(c, float) for c in (dark, mid, light))
    t = np.clip(L, 0, 1.25)[..., None]
    lo = dark + (mid - dark) * np.clip(t / 0.7, 0, 1)
    hi = mid + (light - mid) * np.clip((t - 0.7) / 0.45, 0, 1)
    rgb = np.where(t < 0.7, lo, hi)
    o = np.zeros((96, 96, 4)); o[..., :3] = rgb; o[..., 3] = alpha
    o[dash] = imgs['air'][dash]
    return o


QREF = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sphere_icons', 'qmark_ref_custom_leader.webp')
QBOX = (1085 + 14, 490 + 14, 1085 + 71, 490 + 74)        # the custom-leader portrait's "?" in the user's screenshot


def qmark(height=60):
    """11/01: the game's own serif '?' (custom leader portrait), lifted from the user's screenshot"""
    a = np.asarray(Image.open(QREF).convert('L').crop(QBOX), float)
    m = Image.fromarray((np.clip((a - 60) / 150, 0, 1) * 255).astype(np.uint8))
    S = 8
    w = round(height * m.width / m.height)
    big = m.resize((w * S, height * S), Image.BICUBIC).filter(ImageFilter.GaussianBlur(S * 0.5))
    big = big.point(lambda v: 255 if v > 120 else 0)
    g = big.resize((w, height), Image.LANCZOS)
    out = Image.new('L', (96, 96), 0); out.paste(g, ((96 - w) // 2, (96 - height) // 2 + 1))
    return out


def vanilla_glyph(o, mk, col):
    """vanilla look: light halo on the orb round the glyph, glyph body with tonal texture, crisp edge"""
    m = np.asarray(mk, float) / 255
    halo = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2)), float) / 255
    o = o.copy()
    o[..., :3] = o[..., :3] + (255 - o[..., :3]) * (halo * (1 - m))[..., None] * 0.45
    tex = 0.75 + 0.5 * np.clip(L - P + 0.5, 0, 1)[..., None]             # orb grain -> glyph tone variation
    body = np.clip(np.array(col, float) * tex * 1.6, 0, 255)
    o[..., :3] = o[..., :3] * (1 - m[..., None]) + body * m[..., None]
    return Image.fromarray(np.clip(o, 0, 255).astype(np.uint8), 'RGBA')


cos = colourise((14, 12, 40), (92, 86, 168), (196, 192, 240))
sm = SB.star_mask(); H = 64; mk = sm.resize((round(H * sm.width / sm.height), H), Image.LANCZOS)
SB.glyph(cos, SB.chunky(mk, 13, 0.5), (22, 18, 44)).save(D + 'cosmos.png')
sec = colourise((22, 22, 28), (120, 120, 132), (222, 222, 230))
vanilla_glyph(sec, qmark(), (26, 24, 32)).save(D + 'secret.png')
sh = Image.new('RGBA', (8 * 100, 100), (230, 220, 200, 255))
for i, n in enumerate(['air', 'cosmos', 'death', 'earth', 'fire', 'life', 'secret', 'water']):
    sh.alpha_composite(Image.open(D + n + '.png'), (i * 100 + 2, 2))
sh.resize((1600, 200), Image.LANCZOS).save(r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-<user>-Desktop-Age-of-Wonders-X---Claude/68556280-d707-4a00-a5ee-7f75589fbb89/scratchpad/sph6.png')
