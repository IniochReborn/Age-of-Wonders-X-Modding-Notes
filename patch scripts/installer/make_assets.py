#!/usr/bin/env python3
r"""Regenerate the installer art assets in assets\ from game files.

Inputs (game root, two dirs up):
  AoWSetup.exe            398x450 background BMP @0x7eda3, 375x22 2-slot
                          button strip @0x1028fd (embedded Delphi resources)
  .AoWx Manual.html       AoWx logo ("logo" base64 PNG, 367x175)
  Int\Scenes\BPGen.ILB    record 10 = IniochRising.BMP (finish-page panel)
  assets\aowx.ico         AoWx.exe's 32x32 dragon icon (extracted once)

Outputs (assets\):
  setup_bg_aowx.bmp   splash art: registered AoWx logo + 2-slot bar with
                      baked Install/Cancel captions
  btn_install[_hover|_down].bmp   left bar button crop + hover/pressed variants
  btn_cancel[_hover|_down].bmp    right bar button crop + hover/pressed variants
  wizard_side.bmp     164x314 IniochRising crop (hooded figure + tallest tower)
  wizard_small.bmp    55x55 header image: AoWx.exe icon on dark (#2b2b2b)
  aowx_installer.ico  dragon icon + gold gear badge (16/32/48)
"""
import base64, math, os, re, struct
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
ASSETS = os.path.join(HERE, "assets")

BG_OFF, BG_LEN = 0x7eda3, 538254
STRIP_OFF, STRIP_LEN = 0x1028fd, 24870


def load_setup_bmps():
    # AoWSetup.exe's background may itself carry the AoWx logo now
    # (build_aowsetup_logo.py) — composite from the pristine backup if present
    src = os.path.join(GAME, "AoWSetup.exe.bak_logo")
    if not os.path.isfile(src):
        src = os.path.join(GAME, "AoWSetup.exe")
    d = open(src, "rb").read()
    import io
    bg = Image.open(io.BytesIO(d[BG_OFF:BG_OFF + BG_LEN])).convert("RGB")
    strip = Image.open(io.BytesIO(d[STRIP_OFF:STRIP_OFF + STRIP_LEN])).convert("RGB")
    assert bg.size == (398, 450) and strip.size == (375, 22)
    return bg, strip


def load_logo():
    d = open(os.path.join(GAME, ".AoWx Manual.html"), encoding="utf-8", errors="replace").read()
    m = re.search(r'"logo": "data:image/(png|jpeg);base64,([^"]+)"', d)
    import io
    return Image.open(io.BytesIO(base64.b64decode(m.group(2)))).convert("RGBA")


def load_bpgen(idx):
    dd = open(os.path.join(GAME, r"Int\Scenes\BPGen.ILB"), "rb").read()
    bs = struct.unpack_from("<I", dd, 0x10)[0]
    recs = []
    for mm in re.finditer(struct.pack("<I", 0x56509310), dd):
        p = mm.start()
        sz = struct.unpack_from("<I", dd, p - 0x18)[0]
        of = struct.unpack_from("<I", dd, p - 0x14)[0]
        w = struct.unpack_from("<I", dd, p - 0x10)[0]
        h = struct.unpack_from("<I", dd, p - 0xc)[0]
        if 0 < w < 2048 and 0 < h < 2048 and sz == w * h * 2:
            recs.append((w, h, bs + of))
    w, h, st = recs[idx]
    im = Image.new("RGB", (w, h))
    px = im.load()
    for k in range(w * h):
        v = struct.unpack_from("<H", dd, st + k * 2)[0]
        px[k % w, k // w] = ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)
    return im


def main():
    bg, strip = load_setup_bmps()
    logo = load_logo()
    w, h = bg.size
    px = bg.load()

    # erase the baked vanilla logo: black patch, solid to y142 fading out by y154
    for y in range(14, 154):
        a = 1.0 if y <= 142 else 1.0 - (y - 142) / 12.0
        for x in range(14, w - 14):
            r, g, b = px[x, y]
            px[x, y] = (int(r * (1 - a)), int(g * (1 - a)), int(b * (1 - a)))
    # AoWx logo is the same artwork + X: paste in exact registration over it
    logo_s = logo.resize((round(logo.width * 0.938), round(logo.height * 0.938)), Image.LANCZOS)
    bg.paste(logo_s, (44, 23), logo_s)

    # 2-slot button bar over the old 4-slot bar (strip has stray white edge px)
    spx = strip.load()
    for y in range(strip.height):
        for x in range(strip.width):
            if spx[x, y] == (255, 255, 255):
                spx[x, y] = spx[max(0, x - 1), y] if x > 0 else spx[x + 1, y]
    BAR_X, BAR_Y = 11, 415
    bg.paste(strip, (BAR_X, BAR_Y))
    base = bg.copy()          # caption-free master for per-installer variants

    # AoWSetup's buttons are MS Sans Serif bold @ DFM Font.Height -12. MS Sans
    # Serif is a bitmap font whose bold is GDI's synthetic double-strike, so
    # replicate exactly: micross.ttf (its TrueType-metric twin) at 12px, drawn
    # twice with a 1px x-offset.
    font = None
    for name in ("micross.ttf", "tahoma.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(os.path.join(r"C:\Windows\Fonts", name), 12)
            break
        except OSError:
            pass
    d = ImageDraw.Draw(bg)
    def caption(cx, text):
        bb = d.textbbox((0, 0), text, font=font)
        x = cx - (bb[2] - bb[0] + 1) / 2
        y = BAR_Y + 11 - (bb[3] - bb[1]) / 2 - bb[1]
        d.text((x, y), text, font=font, fill=(20, 8, 4))
        d.text((x + 1, y), text, font=font, fill=(20, 8, 4))   # synthetic bold
    caption(BAR_X + 92, "Install")
    caption(BAR_X + 282, "Cancel")

    bg.save(os.path.join(ASSETS, "setup_bg_aowx.bmp"))

    # button crops + hover (brightened) and pressed (darkened, shifted 1px) variants
    def button_set(box, name, src=None):
        b = (src if src is not None else bg).crop(box)
        b.save(os.path.join(ASSETS, name + ".bmp"))
        ImageEnhance.Brightness(b).enhance(1.18).save(os.path.join(ASSETS, name + "_hover.bmp"))
        dk = b.point(lambda v: int(v * 0.80))
        down = dk.copy()
        down.paste(dk.crop((0, 0, dk.width - 1, dk.height - 1)), (1, 1))
        edge = dk.load()
        for x in range(down.width):
            down.putpixel((x, 0), (24, 12, 8))
        for y in range(down.height):
            down.putpixel((0, y), (24, 12, 8))
        down.save(os.path.join(ASSETS, name + "_down.bmp"))
    button_set((BAR_X, BAR_Y, BAR_X + 184, BAR_Y + 22), "btn_install")
    button_set((BAR_X + 190, BAR_Y, BAR_X + 375, BAR_Y + 22), "btn_cancel")

    # modding-tools installer variant: left button reads "Install Modding Tools"
    # (Cancel is identical, the tools iss reuses btn_cancel*)
    bgt = base.copy()
    dt = ImageDraw.Draw(bgt)
    # fixed y from a descender-free reference so "Modding"'s g doesn't push
    # the whole caption up relative to "Cancel" (ink-box centering artifact)
    _rb = dt.textbbox((0, 0), "Cancel", font=font)
    _cy = BAR_Y + 11 - (_rb[3] - _rb[1]) / 2 - _rb[1]
    def caption_t(cx, text):
        bb = dt.textbbox((0, 0), text, font=font)
        x = cx - (bb[2] - bb[0] + 1) / 2
        dt.text((x, _cy), text, font=font, fill=(20, 8, 4))
        dt.text((x + 1, _cy), text, font=font, fill=(20, 8, 4))   # synthetic bold
    caption_t(BAR_X + 92, "Install Modding Tools")
    caption_t(BAR_X + 282, "Cancel")
    bgt.save(os.path.join(ASSETS, "setup_bg_aowxtools.bmp"))
    button_set((BAR_X, BAR_Y, BAR_X + 184, BAR_Y + 22), "btn_install_tools", bgt)

    # finish-page side panel: IniochRising, crop keeps tallest tower + hooded figure
    scene = load_bpgen(10)                      # 272x372
    scene.crop((36, 0, 230, 372)).resize((164, 314), Image.LANCZOS) \
         .save(os.path.join(ASSETS, "wizard_side.bmp"))

    # header image: the game exe's dragon icon centred on dark (matches dark style)
    ico = Image.open(os.path.join(ASSETS, "aowx.ico")).convert("RGBA")
    small = Image.new("RGB", (55, 55), (20, 20, 20))
    small.paste(ico, ((55 - ico.width) // 2, (55 - ico.height) // 2), ico)
    small.save(os.path.join(ASSETS, "wizard_small.bmp"))

    # installer icon: black dragon + silver gear badge (4x supersampled, hole
    # punched through so the dragon shows behind it)
    S = 4
    cx, cy = 22.5 * S, 22.5 * S
    R_TEETH, R_BODY, R_HOLE = 9.2 * S, 6.6 * S, 3.0 * S
    GOLD, DARK = (206, 210, 222, 255), (42, 44, 52, 255)
    gear = Image.new("RGBA", (32 * S, 32 * S), (0, 0, 0, 0))
    g = ImageDraw.Draw(gear)
    for pad, col in ((1.1 * S, DARK), (0, GOLD)):     # dark outline pass first
        for i in range(8):
            a = i * math.pi / 4 + math.pi / 8
            g.line([(cx + math.cos(a) * (R_BODY - S), cy + math.sin(a) * (R_BODY - S)),
                    (cx + math.cos(a) * (R_TEETH + pad - 1.1 * S + (1.1 * S if col is DARK else 0)),
                     cy + math.sin(a) * (R_TEETH + pad - 1.1 * S + (1.1 * S if col is DARK else 0)))],
                   fill=col, width=int(3.2 * S + 2 * pad))
        r = R_BODY + pad
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    gp = gear.load()
    for y in range(32 * S):                            # punch the hole
        for x in range(32 * S):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 <= R_HOLE ** 2:
                gp[x, y] = (0, 0, 0, 0)
            elif d2 <= (R_HOLE + 1.1 * S) ** 2 and gp[x, y][3] > 0:
                gp[x, y] = DARK
    gear = gear.resize((32, 32), Image.LANCZOS)
    base = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    base.alpha_composite(ico)
    base.alpha_composite(gear)
    out = os.path.join(ASSETS, "aowx_installer.ico")
    base.save(out, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
