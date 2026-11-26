#!/usr/bin/env python3
r"""
AoWDevX: Map Screenshot toolbar button (2026-11-07).

User: "add a new button to AoWDevX tool bar. add it after validate map button (push everything after to the right to
make room). make the icon a camera. when pressed, it should bring up a window for screenshot options" (minimap PNG
without the view box / map PNG current view or entire level / current level or all levels / optional frame).

  * TMAINFORM DFM (relocated in .xprn @RVA 0xED000, rewritten in place like patch_devx_autosave_v1): new TSpeedButton
    'ScreenshotBtn' right after ValidateMapBtn (x 176), camera glyph (two-state 64x32 like the others); every Panel2
    button right of ValidateMapBtn moves 40 px right.  No OnClick in the DFM (the method table has no room).
  * FormCreate (published method-table entry, table 0x4EB800; currently -> patch_devx_autosave_v1's wrapper 0x4ECC00)
    -> wrapper 'fcw' (zone .xprn 0x4ECAC0..0x4ECC00 = unused tail of patch_devx_text_limits_v1's declared zone, which
    already reports OTHER since autosave carved its own tail): calls the previous target, then finds 'ScreenshotBtn'
    in Form.Components (TComponent +0x10 list, name +0x8) and sets its OnClick TMethod (TControl +0xA4 code /
    +0xA8 data = the form).
  * click: LoadLibraryA("AoWxShot.dll") + GetProcAddress("Run") once (both borrowed from VCL30's IAT through the
    Forms.TCustomForm.Create import delta, as build_editor_timerres), then Run(form).  Missing DLL -> MessageBoxA.
  * AoWxShot.dll (build_aowxshot.py) is (re)built and written next to the exe by --apply.  ⚠ ship AoWxShot.dll.
v2 (2026-11-07, user: "add a button between validate and screenshot ... an X instead of a checkmark ... display a list
of all resources missing, what theyre called, and where theyre located (right click to center)"):
  * DFM: TSpeedButton 'MissingBtn' (red X in the Validate checkmark's style) right after ValidateMapBtn; the
    ScreenshotBtn and everything after move another 40 px right.
  * the FormCreate stub now only LoadLibrary's AoWxShot.dll and calls its export Init(form): the DLL wires both
    buttons' OnClick itself and installs its in-memory load-error hooks (see aowxshot_missing.py).  No DLL -> the two
    buttons simply do nothing.
Backup .bak_screenshot (whole exe; --revert restores it and deletes AoWxShot.dll - LIFO: re-run later AoWDevX
patches after a revert).  Dry-run default; --apply; --revert.
"""
import io, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_devx_terrain_palette_v1 as PAL  # noqa: E402
import patch_devx_autosave_v1 as AS  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import build_aowxshot as SHOT  # noqa: E402

EXE = game_file("AoWDevX.exe")
TAG = ".bak_screenshot"
ZONE, ZONE_END = 0x4ECAC0, 0x4ECC00
PREV_FC = 0x4ECC00                       # patch_devx_autosave_v1's FormCreate wrapper
BTN = "ScreenshotBtn"
HINT = "Map screenshot (export the minimap or the map as PNG)"
BTN3 = "RegenBtn"
HINT3 = "Regenerate units (rebuild every unit's abilities from its AoWx unit type - asks for confirmation)"
BTN2 = "MissingBtn"
HINT2 = "Missing resources (objects that could not be loaded from this map - right-click an entry to centre on it)"
ANCHOR, SHIFT = "ValidateMapBtn", 40
# v4 (user: "add another sorting button (after sort by level) ... 'U' icon (same font as '1' and 'A') ... sort heroes by
# whether they are 'User' or not (and also sort alphabetically)" + "also add that 'User' sorting for items"):
# a 7th TSpeedButton in HeroPnl / ItemsPnl after the level/type sort button.  The panels are 357 px wide and the six
# existing 50-px buttons already end at 352, so all seven are repacked at width 46 (groups kept: library | edit, add,
# delete | sort name, sort level/type, sort user) - ends at 346.  Click wired by AoWxShot.dll (setclick), the sort
# itself is AoWEPACK mode 2 (patch_devx_hero_sort_user_v1).
USORT = [  # (panel, new button, hint, [existing buttons left->right])
    ("HeroPnl", "SortUserBtn", "Sort on user-made (User heroes first, then by name)",
     ["OpenHeroLibrary", "EditHeroBtn", "AddHeroBtn", "RemoveHeroBtn", "SortNameBtn", "SortLevelBtn"]),
    ("ItemsPnl", "SortItemUserBtn", "Sort on user-made (User items first, then by name)",
     ["OpenItemLibrary", "EditItemBtn", "NewItemBtn", "DeleteItemBtn", "SortItemsName", "SortTypeBtn"]),
]
USORT_LEFT, USORT_W = [2, 58, 104, 150, 208, 254, 300], 46
VCL_CREATE_SLOT, VCL_CREATE = 0x432210, 0x41336300
VCL_LOADLIB, VCL_GETPROC = 0x413E4360, 0x413E43B4


# ---- stub --------------------------------------------------------------------------------------------------------
def build_zone():
    data = bytearray()
    sym = {}

    def put(name, b):
        sym[name] = ZONE + len(data)
        data.extend(b)
    put("s_dll", b"AoWxShot.dll\0")
    put("s_init", b"Init\0")
    while len(data) % 16:
        data.append(0)
    code_at = ZONE + len(data)
    s = sym
    src = f"""
    fcw:
        push eax
        push edx
        call {PREV_FC:#x}
        pop edx
        pop eax
        pushal
        mov esi, eax
        mov ebx, dword ptr [{VCL_CREATE_SLOT:#x}]
        sub ebx, {VCL_CREATE:#x}
        push {s['s_dll']:#x}
        call dword ptr [ebx + {VCL_LOADLIB:#x}]
        test eax, eax
        jz fo
        push {s['s_init']:#x}
        push eax
        call dword ptr [ebx + {VCL_GETPROC:#x}]
        test eax, eax
        jz fo
        push esi
        call eax
    fo:
        popal
        ret
    probe:
        mov eax, fcw
        mov eax, fcw
    """
    code = OV.asm(src, code_at)
    tail = code[-10:]
    assert tail[0] == 0xB8 and tail[5] == 0xB8
    fcw, click = struct.unpack_from("<I", tail, 1)[0], None
    code = code[:-10]
    assert fcw == code_at, hex(fcw)
    zone = bytes(data) + code
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, fcw, click


# ---- DFM ---------------------------------------------------------------------------------------------------------
CAMERA = [
    '         KKKKKKKK           ',
    '        KHHHHHHHHK          ',
    '  KKK  KKKKKKKKKKKK         ',
    ' KKKKKKKKKKKKKKKKKKKKKKKKKK ',
    'KHHHHHHHHHHHHHHHHHHHHHHHHHHK',
    'KKWWWKKKKKKKKKKKKKKKKKKKRRKK',
    'KKKKKKKKKKKSSSSSSKKKKKKKKKKK',
    'KKKKKKKKKSSGGGGGGSSKKKKKKKKK',
    'KKKKKKKKSGGGGGGGGGGSKKKKKKKK',
    'KKKKKKKSGGLLGGGGGGGGSKKKKKKK',
    'KKKKKKKSGLLLGGGGGGGGSKKKKKKK',
    'KKKKKKSGGLLGGGGGGGGGGSKKKKKK',
    'KKKKKKSGGGGGGGGGGGGGGSKKKKKK',
    'KKKKKKSGGGGGGGGGGGGGGSKKKKKK',
    'KKKKKKKSGGGGGGGGGGGGSKKKKKKK',
    'KKKKKKKSGGGGGGGGGGGGSKKKKKKK',
    'KKKKKKKKSGGGGGGGGGGSKKKKKKKK',
    'KKKKKKKKKSSGGGGGGSSKKKKKKKKK',
    'KKKKKKKKKKKSSSSSSKKKKKKKKKKK',
    'KKKKKKKKKKKKKKKKKKKKKKKKKKKK',
    ' KKKKKKKKKKKKKKKKKKKKKKKKKK ',
]


def camera_glyph(gdata):
    from PIL import Image
    n = struct.unpack_from("<I", gdata, 0)[0]
    bmp = gdata[4:4 + n]
    im = Image.open(io.BytesIO(bmp)).convert("RGB")
    assert im.size == (64, 32)
    px = im.load()
    bg = px[0, 31]
    assert bg == (191, 191, 191), bg
    for y in range(32):                                     # clean slate, both halves
        for x in range(64):
            px[x, y] = bg
    # v1.1 (user: "a black camera, and make it bigger"): 28 x 21 black body, dark glass lens, grey ring
    norm = {"K": (12, 12, 14), "H": (54, 54, 60), "S": (110, 110, 118), "G": (30, 34, 44), "L": (170, 180, 196),
            "W": (210, 210, 214), "R": (200, 40, 36)}
    dis = {"K": (128, 128, 128), "H": (150, 150, 150), "S": (170, 170, 170), "G": (140, 140, 140),
           "L": (255, 255, 255), "W": (255, 255, 255), "R": (150, 150, 150)}
    for half, pal in ((0, norm), (32, dis)):
        ox, oy = half + 2, 6
        for y, row in enumerate(CAMERA):
            for x, ch in enumerate(row):
                if ch != " ":
                    px[ox + x, oy + y] = pal[ch]
    b = io.BytesIO(); im.save(b, "BMP")
    nb = b.getvalue()
    assert len(nb) == len(bmp), (len(nb), len(bmp))
    return struct.pack("<I", len(nb)) + nb


def x_glyph(gdata):
    """v2: red X in the style of the Validate checkmark (solid (143,34,29) brush strokes, anti-aliased edge, flared
    ends); disabled half = (133,133,148) outline + (224,224,224) highlight offset (+1,+1), like the checkmark's"""
    from PIL import Image, ImageDraw
    n = struct.unpack_from("<I", gdata, 0)[0]
    bmp = gdata[4:4 + n]
    im = Image.open(io.BytesIO(bmp)).convert("RGB")
    px = im.load()
    bg = px[0, 31]
    assert bg == (191, 191, 191), bg
    S = 8
    m = Image.new("L", (32 * S, 32 * S), 0)
    d = ImageDraw.Draw(m)

    def stroke(p0, p1, w0, w1):
        steps = 64
        for i in range(steps + 1):
            t = i / steps
            x = (p0[0] + (p1[0] - p0[0]) * t) * S
            y = (p0[1] + (p1[1] - p0[1]) * t) * S
            r = (w0 + (w1 - w0) * t) * S / 2
            d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    stroke((7.0, 5.5), (25.0, 26.0), 5.2, 4.2)                # main diagonal (top-left -> bottom-right)
    stroke((26.5, 4.0), (6.5, 26.5), 4.4, 5.0)                # cross stroke (top-right -> bottom-left)
    stroke((5.2, 4.6), (8.0, 6.6), 3.6, 4.2)                  # flared brush tips like the checkmark's
    stroke((27.5, 3.0), (25.6, 5.0), 3.2, 3.8)
    a = m.resize((32, 32), Image.LANCZOS).load()
    red, out_c, hi_c = (143, 34, 29), (133, 133, 148), (224, 224, 224)
    for y in range(32):
        for x in range(64):
            px[x, y] = bg
    cov = [[a[x, y] / 255.0 for x in range(32)] for y in range(32)]
    for y in range(32):
        for x in range(32):
            c = cov[y][x]
            if c > 0.03:
                px[x, y] = tuple(int(round(bg[i] * (1 - c) + red[i] * c)) for i in range(3))
    solid = [[cov[y][x] >= 0.5 for x in range(32)] for y in range(32)]
    edge = [[solid[y][x] and any(not (0 <= y + dy < 32 and 0 <= x + dx < 32 and solid[y + dy][x + dx])
                                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
             for x in range(32)] for y in range(32)]
    for y in range(32):
        for x in range(32):
            if edge[y][x] and y + 1 < 32 and x + 1 < 32 and not solid[y + 1][x + 1]:
                px[32 + x + 1, y + 1] = hi_c
    for y in range(32):
        for x in range(32):
            if edge[y][x]:
                px[32 + x, y] = out_c
    b = io.BytesIO(); im.save(b, "BMP")
    nb = b.getvalue()
    assert len(nb) == len(bmp), (len(nb), len(bmp))
    return struct.pack("<I", len(nb)) + nb


def regen_glyph(gdata):
    """v3: two dark-green refresh arrows (circular), same 64x32 two-state layout; disabled = grey outline + highlight"""
    from PIL import Image, ImageDraw
    import math
    n = struct.unpack_from("<I", gdata, 0)[0]
    bmp = gdata[4:4 + n]
    im = Image.open(io.BytesIO(bmp)).convert("RGB")
    px = im.load()
    bg = px[0, 31]
    assert bg == (191, 191, 191), bg
    S = 8
    m = Image.new("L", (32 * S, 32 * S), 0)
    d = ImageDraw.Draw(m)
    cx, cy, R, w = 16 * S, 16 * S, 10.0 * S, 3.6 * S
    for a0, a1 in ((195, 315), (15, 135)):                     # two arcs with gaps, clockwise
        for t in range(a0, a1 + 1):
            r = math.radians(t)
            x, y = cx + R * math.cos(r), cy + R * math.sin(r)
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
        r = math.radians(a1)                                   # arrow head at the arc end, pointing along it
        hx, hy = cx + R * math.cos(r), cy + R * math.sin(r)
        tx, ty = -math.sin(r), math.cos(r)                     # tangent (direction of travel)
        nx, ny = math.cos(r), math.sin(r)
        L, W = 8.0 * S, 6.8 * S
        d.polygon([(hx + tx * L, hy + ty * L), (hx + nx * W, hy + ny * W), (hx - nx * W, hy - ny * W)], fill=255)
    a = m.resize((32, 32), Image.LANCZOS).load()
    col, out_c, hi_c = (30, 110, 40), (133, 133, 148), (224, 224, 224)
    for y in range(32):
        for x in range(64):
            px[x, y] = bg
    cov = [[a[x, y] / 255.0 for x in range(32)] for y in range(32)]
    for y in range(32):
        for x in range(32):
            c = cov[y][x]
            if c > 0.03:
                px[x, y] = tuple(int(round(bg[i] * (1 - c) + col[i] * c)) for i in range(3))
    solid = [[cov[y][x] >= 0.5 for x in range(32)] for y in range(32)]
    edge = [[solid[y][x] and any(not (0 <= y + dy < 32 and 0 <= x + dx < 32 and solid[y + dy][x + dx])
                                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
             for x in range(32)] for y in range(32)]
    for y in range(32):
        for x in range(32):
            if edge[y][x] and y + 1 < 32 and x + 1 < 32 and not solid[y + 1][x + 1]:
                px[32 + x + 1, y + 1] = hi_c
    for y in range(32):
        for x in range(32):
            if edge[y][x]:
                px[32 + x, y] = out_c
    b = io.BytesIO(); im.save(b, "BMP")
    nb = b.getvalue()
    assert len(nb) == len(bmp), (len(nb), len(bmp))
    return struct.pack("<I", len(nb)) + nb


def add_regen(dfm):
    """v3: RegenBtn right after ScreenshotBtn; every Panel2 button right of it +SHIFT"""
    D = PAL.DFM(dfm)
    anc = D.get(BTN)
    apl = dict(SP.props(dfm, anc))
    lv = apl["Left"]
    ax = lv[1] if lv[0] == 2 else struct.unpack_from("<h", lv, 1)[0]
    p = D.get("Panel2")
    edits = []
    for k in p["kids"]:
        if k["cls"] != b"TSpeedButton":
            continue
        pl = SP.props(dfm, k)
        dd = dict(pl)
        v = dd["Left"]
        left = v[1] if v[0] == 2 else struct.unpack_from("<h", v, 1)[0]
        if left > ax:
            newk = SP.ser_comp(k["cls"], k["name"], [(a, i16(left + SHIFT) if a == "Left" else b) for a, b in pl])
            edits.append((k["start"], k["end"], newk))
    btn = [("Left", i16(ax + SHIFT)), ("Top", apl["Top"]), ("Width", apl["Width"]), ("Height", apl["Height"]),
           ("Hint", SP.vstr(HINT3)), ("Flat", apl["Flat"]), ("Glyph.Data", SP.vbin(regen_glyph(apl["Glyph.Data"][5:]))),
           ("NumGlyphs", apl["NumGlyphs"])]
    edits.append((anc["end"], anc["end"], SP.ser_comp(b"TSpeedButton", BTN3, btn)))
    out = bytearray(); pos = 0
    for st, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
        out += dfm[pos:st] + b; pos = e
    out += dfm[pos:]
    N = PAL.DFM(bytes(out))
    assert N.get(BTN3)["parent"] == "Panel2"
    return bytes(out)


def regen_first(dfm):
    """v3.1 (user: "switch the position of screenshot and regenerate"): RegenBtn takes ScreenshotBtn's slot and vice
    versa (toolbar: Validate, X, Regenerate, Screenshot, ...)"""
    D = PAL.DFM(dfm)
    a, b = D.get(BTN3), D.get(BTN)
    pa, pb = SP.props(dfm, a), SP.props(dfm, b)
    la, lb = dict(pa)["Left"], dict(pb)["Left"]
    val = lambda v: v[1] if v[0] == 2 else struct.unpack_from("<h", v, 1)[0]  # noqa: E731
    if val(la) < val(lb):
        return dfm
    na = SP.ser_comp(a["cls"], a["name"], [(k, lb if k == "Left" else v) for k, v in pa])
    nb = SP.ser_comp(b["cls"], b["name"], [(k, la if k == "Left" else v) for k, v in pb])
    edits = sorted([(a["start"], a["end"], na), (b["start"], b["end"], nb)])
    out = bytearray(); pos = 0
    for st, e, blob in edits:
        out += dfm[pos:st] + blob; pos = e
    out += dfm[pos:]
    return bytes(out)


def u_glyph(gdata):
    """v4: a big 'U' in the purple (68,1,121) of the 'A' / '1' sort glyphs (Arial 28 = their 20-px cap height,
    antialiased onto the (191,191,191) face), 32x32 single-state like SortNameBtn"""
    from PIL import Image, ImageDraw, ImageFont
    n = struct.unpack_from("<I", gdata, 0)[0]
    bmp = gdata[4:4 + n]
    im = Image.open(io.BytesIO(bmp)).convert("RGB")
    assert im.size == (32, 32), im.size
    bg, col = (191, 191, 191), (68, 1, 121)
    assert im.load()[0, 0] == bg
    f = ImageFont.truetype("arial.ttf", 28)
    m = Image.new("L", (32, 32), 0)
    d = ImageDraw.Draw(m)
    bb = d.textbbox((0, 0), "U", font=f)
    d.text(((32 - (bb[2] - bb[0])) // 2 - bb[0], 29 - bb[3]), "U", font=f, fill=255)
    a = m.load()
    out = Image.new("RGB", (32, 32), bg)
    px = out.load()
    for y in range(32):
        for x in range(32):
            c = a[x, y] / 255.0
            if c > 0:
                px[x, y] = tuple(int(round(bg[i] * (1 - c) + col[i] * c)) for i in range(3))
    b = io.BytesIO(); out.save(b, "BMP")
    nb = b.getvalue()
    assert len(nb) == len(bmp), (len(nb), len(bmp))
    return struct.pack("<I", len(nb)) + nb


def add_usort(dfm):
    """v4: SortUserBtn / SortItemUserBtn + repack (idempotent per panel)"""
    for panel, name, hint, olds in USORT:
        if bytes([len(name)]) + name.encode() in dfm:
            continue
        D = PAL.DFM(dfm)
        assert D.get(olds[-1])["parent"] == panel
        edits = []
        for i, on in enumerate(olds):
            k = D.get(on)
            pl = SP.props(dfm, k)
            nk = SP.ser_comp(k["cls"], k["name"], [(a, i16(USORT_LEFT[i]) if a == "Left" else
                                                    i16(USORT_W) if a == "Width" else b) for a, b in pl])
            edits.append((k["start"], k["end"], nk))
        last = D.get(olds[-1])
        lp = dict(SP.props(dfm, last))
        tpl = dict(SP.props(dfm, D.get(olds[-2])))          # name-sort button: 32x32 glyph template
        btn = [("Left", i16(USORT_LEFT[6])), ("Top", lp["Top"]), ("Width", i16(USORT_W)), ("Height", lp["Height"]),
               ("Hint", SP.vstr(hint)), ("Flat", lp["Flat"]), ("Glyph.Data", SP.vbin(u_glyph(tpl["Glyph.Data"][5:])))]
        edits.append((last["end"], last["end"], SP.ser_comp(b"TSpeedButton", name, btn)))
        out = bytearray(); pos = 0
        for st, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
            out += dfm[pos:st] + b; pos = e
        out += dfm[pos:]
        dfm = bytes(out)
        assert PAL.DFM(dfm).get(name)["parent"] == panel
    return dfm


def add_missing(dfm):
    """v2: MissingBtn right after ValidateMapBtn; every Panel2 button right of it (ScreenshotBtn ...) +SHIFT"""
    D = PAL.DFM(dfm)
    anc = D.get(ANCHOR)
    apl = dict(SP.props(dfm, anc))
    lv = apl["Left"]
    ax = lv[1] if lv[0] == 2 else struct.unpack_from("<h", lv, 1)[0]
    p = D.get("Panel2")
    edits = []
    for k in p["kids"]:
        if k["cls"] != b"TSpeedButton":
            continue
        pl = SP.props(dfm, k)
        dd = dict(pl)
        v = dd["Left"]
        left = v[1] if v[0] == 2 else struct.unpack_from("<h", v, 1)[0]
        if left > ax:
            newk = SP.ser_comp(k["cls"], k["name"], [(a, i16(left + SHIFT) if a == "Left" else b) for a, b in pl])
            edits.append((k["start"], k["end"], newk))
    btn = [("Left", i16(ax + SHIFT)), ("Top", apl["Top"]), ("Width", apl["Width"]), ("Height", apl["Height"]),
           ("Hint", SP.vstr(HINT2)), ("Flat", apl["Flat"]), ("Glyph.Data", SP.vbin(x_glyph(apl["Glyph.Data"][5:]))),
           ("NumGlyphs", apl["NumGlyphs"])]
    edits.append((anc["end"], anc["end"], SP.ser_comp(b"TSpeedButton", BTN2, btn)))
    out = bytearray(); pos = 0
    for st, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
        out += dfm[pos:st] + b; pos = e
    out += dfm[pos:]
    N = PAL.DFM(bytes(out))
    assert N.get(BTN2)["parent"] == "Panel2"
    return bytes(out)


def i16(v):
    return b"\x03" + struct.pack("<h", v)


def new_dfm(dfm):
    D = PAL.DFM(dfm)
    anc = D.get(ANCHOR)
    apl = dict(SP.props(dfm, anc))
    lv = apl["Left"]
    ax = lv[1] if lv[0] == 2 else struct.unpack_from("<h", lv, 1)[0]
    p = D.get("Panel2")
    edits = []
    for k in p["kids"]:
        if k["cls"] != b"TSpeedButton":
            continue
        pl = SP.props(dfm, k)
        dd = dict(pl)
        v = dd["Left"]
        left = v[1] if v[0] == 2 else struct.unpack_from("<h", v, 1)[0]
        if left > ax:
            newk = SP.ser_comp(k["cls"], k["name"], [(a, i16(left + SHIFT) if a == "Left" else b) for a, b in pl])
            edits.append((k["start"], k["end"], newk))
    btn = [("Left", i16(ax + SHIFT)), ("Top", apl["Top"]), ("Width", apl["Width"]), ("Height", apl["Height"]),
           ("Hint", SP.vstr(HINT)), ("Flat", apl["Flat"]), ("Glyph.Data", SP.vbin(camera_glyph(apl["Glyph.Data"][5:]))),
           ("NumGlyphs", apl["NumGlyphs"])]
    edits.append((anc["end"], anc["end"], SP.ser_comp(b"TSpeedButton", BTN, btn)))
    out = bytearray(); pos = 0
    for s, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
        out += dfm[pos:s] + b; pos = e
    out += dfm[pos:]
    N = PAL.DFM(bytes(out))
    assert N.get(BTN)["parent"] == "Panel2"
    return bytes(out)


def build(d):
    import pefile
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - 0x400000)  # noqa: E731
    rva, dfm = PAL.mainform_dfm(pe)
    zone, fcw, click = build_zone()
    fe = AS.mt_entry(d, off)
    cur_fc = struct.unpack_from("<I", d, fe)[0]
    if b"\x0dScreenshotBtn" in dfm:                     # update: zone is ours
        assert ZONE <= cur_fc < ZONE_END, hex(cur_fc)
        nd = dfm if b"\x0aMissingBtn" in dfm else add_missing(dfm)
        nd = regen_first(nd if b"\x08RegenBtn" in nd else add_regen(nd))
        nd = add_usort(nd)
        out = AS.place_dfm(d, pe, rva, nd) if nd != dfm else bytearray(d)   # (same-size swaps re-place too)
        out[off(ZONE):off(ZONE_END)] = zone + bytes(ZONE_END - ZONE - len(zone))
        struct.pack_into("<I", out, fe, fcw)
        return (None if bytes(out) == d else bytes(out)), len(zone), len(dfm), len(nd)
    assert cur_fc == PREV_FC, "FormCreate entry is %#x, expected autosave's %#x" % (cur_fc, PREV_FC)
    assert not any(d[off(ZONE):off(ZONE_END)]), "zone not free"
    nd = add_usort(regen_first(add_regen(add_missing(new_dfm(dfm)))))
    out = AS.place_dfm(d, pe, rva, nd)
    out[off(ZONE):off(ZONE) + len(zone)] = zone
    struct.pack_into("<I", out, fe, fcw)
    return bytes(out), len(zone), len(dfm), len(nd)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    bk = bak_path(EXE, TAG)
    if revert:
        if os.path.exists(bk):
            shutil.copy2(bk, EXE); print("restored", bk)
        if os.path.exists(SHOT.OUT):
            os.remove(SHOT.OUT); print("removed", SHOT.OUT)
        return 0
    d = open(EXE, "rb").read()
    out, nz, od, nd = build(d)
    img, info = SHOT.build(os.path.dirname(HERE))
    cur_dll = open(SHOT.OUT, "rb").read() if os.path.exists(SHOT.OUT) else None
    print("AoWDevX.exe: %s | stub %d B @%#x | DFM %d -> %d B" % ("already applied" if out is None else "write", nz, ZONE,
                                                                  od, nd))
    print("AoWxShot.dll: %s (%d B, code %d B)" % ("up to date" if cur_dll == img else "write", len(img), info["code_len"]))
    if out is None and cur_dll == img:
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if out is not None:
        if not os.path.exists(bk):
            shutil.copy2(EXE, bk)
        with open(EXE, "wb") as fh:
            fh.write(out)
        assert open(EXE, "rb").read() == out
    if cur_dll != img:
        with open(SHOT.OUT, "wb") as fh:
            fh.write(img)
        assert open(SHOT.OUT, "rb").read() == img
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
