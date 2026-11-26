#!/usr/bin/env python3
r"""Build assets\aowx_dark.vsf — Inno's built-in dark wizard style recolored
from blue to red/burgundy accents.

Inno Setup has no accent-color directive; the accents live in the compiled-in
"Windows11 Modern Dark" VCL style inside SetupCustomStyle.e32 (PE resource
VCLSTYLE\WINDOWSMODERNDARK). A .vsf is that same stream saved to disk:
    'VCL_STYLE 2.0' + zlib(inner)
The inner stream holds three raw BGRA glyph atlases (each: len-prefixed UTF-16
name, w:u32, h:u32, w*h*4 pixels) followed by ~300KB of object properties
containing TColor dwords. This script hue-shifts every blue-dominant pixel in
the atlases and every blue-dominant color dword in the property tail to
burgundy (hue ~348deg), then recompresses. Output goes to assets\aowx_dark.vsf,
wired into the iss via WizardStyleFile.

Rerun after an Inno Setup upgrade (resource is located dynamically).
"""
import colorsys, os, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
STUB = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\SetupCustomStyle.e32")

HUE = 348 / 360.0          # burgundy
SAT_BOOST = 1.25           # deeper, richer red
VAL_SCALE = 0.70

# named colors in the style's property tail, stored as UTF-16 '$00BBGGRR'
# strings — patched in place (same length). RGB values here.
STRING_COLORS = {
    "FocusEffect": (0xB0, 0x1E, 0x36),      # focus rings (was #0377D0 blue)
    "ButtonNormal": (0x40, 0x18, 0x24),     # translucent-burgundy button fill
    "ButtonHot": (0x5E, 0x22, 0x33),
    "ButtonPressed": (0x2B, 0x0F, 0x18),
    "ButtonFocused": (0x70, 0x20, 0x38),    # Next/default button: richer burgundy
    "clHighlight": (0x8C, 0x21, 0x38),      # selection highlight
}


def find_style_resource(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt_size = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", d, opt)[0]
    ddir_off = opt + (0x60 if magic == 0x10B else 0x70)
    rsrc_rva = struct.unpack_from("<I", d, ddir_off + 16)[0]
    sec0 = opt + opt_size
    secs = []
    for i in range(nsec):
        s = sec0 + i * 40
        vs, va, rs, ro = struct.unpack_from("<IIII", d, s + 8)
        secs.append((va, vs, ro, rs))

    def rva2off(rva):
        for va, vs, ro, rs in secs:
            if va <= rva < va + max(vs, rs):
                return ro + (rva - va)

    base = rva2off(rsrc_rva)
    result = []

    def walk(off, path):
        nnamed, nid = struct.unpack_from("<HH", d, base + off + 12)
        for i in range(nnamed + nid):
            e = base + off + 16 + i * 8
            name_f, data_f = struct.unpack_from("<II", d, e)
            if name_f & 0x80000000:
                noff = base + (name_f & 0x7FFFFFFF)
                ln = struct.unpack_from("<H", d, noff)[0]
                nm = d[noff + 2:noff + 2 + ln * 2].decode("utf-16le", "replace")
            else:
                nm = str(name_f)
            if data_f & 0x80000000:
                walk(data_f & 0x7FFFFFFF, path + [nm])
            else:
                de = base + data_f
                rva, size = struct.unpack_from("<II", d, de)
                result.append(("/".join(path + [nm]), rva2off(rva), size))

    walk(0, [])
    for name, off, size in result:
        if name.startswith("VCLSTYLE/WINDOWSMODERNDARK/"):
            return off, size
    raise SystemExit("!! VCLSTYLE/WINDOWSMODERNDARK resource not found in " + STUB)


def is_blue(r, g, b):
    return b > 90 and b > r + 25 and b > g + 15


def shift(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    r2, g2, b2 = colorsys.hsv_to_rgb(HUE, min(1.0, s * SAT_BOOST), v * VAL_SCALE)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


def transform_pixel(r, g, b, a):
    """Four tiers: strong blue accents -> deep rich red; the slate-teal
    focused-button face -> distinctly richer burgundy; neutral control greys
    (button faces, scrollbar parts) -> subtle translucent-burgundy tint;
    finally the PREMULTIPLIED dark-slate family (stored ~rgb(30,53,64) with
    a~170 -- the Next/default button's stretched 9-patch face, which escapes
    every test above because premultiplication scales r below 30) -> burgundy
    slightly brighter and richer than the neutral Cancel-button tint."""
    if is_blue(r, g, b):
        return shift(r, g, b)
    if b > r + 12 and b > g + 4 and b > 55 and r > 30:          # slate face
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        r2, g2, b2 = colorsys.hsv_to_rgb(HUE, max(0.55, min(1.0, s * 2)), v * 0.85)
        return round(r2 * 255), round(g2 * 255), round(b2 * 255)
    if a > 200 and abs(r - g) < 3 and abs(g - b) < 3 and 40 <= r <= 100:  # neutral
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        r2, g2, b2 = colorsys.hsv_to_rgb(HUE, 0.38, v)
        return round(r2 * 255), round(g2 * 255), round(b2 * 255)
    if b > r + 8 and b >= g and b > 35:                          # premult slate
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        r2, g2, b2 = colorsys.hsv_to_rgb(HUE, max(0.55, min(1.0, s * 1.1)),
                                         min(1.0, v * 1.12))
        # keep the premultiplied invariant (channel <= alpha)
        r2, g2, b2 = (min(round(c * 255), a) for c in (r2, g2, b2))
        return r2, g2, b2
    return None


def is_word_char(inner, off):
    if off < 0 or off + 2 > len(inner):
        return False
    c = inner[off] | (inner[off + 1] << 8)
    return (48 <= c <= 57) or (65 <= c <= 90) or (97 <= c <= 122)


def patch_string_colors(inner, tail_start):
    total = 0
    for name, (r, g, b) in STRING_COLORS.items():
        pat = name.encode("utf-16le")
        newhex = f"$00{b:02X}{g:02X}{r:02X}".encode("utf-16le")
        p = tail_start
        n = 0
        while True:
            i = inner.find(pat, p)
            if i < 0:
                break
            p = i + len(pat)
            # whole-word match only (e.g. don't hit 'CategoryButtonsNormal')
            if is_word_char(inner, i - 2) or is_word_char(inner, i + len(pat)):
                continue
            j = inner.find("$00".encode("utf-16le"), p, p + 400)
            if j < 0:
                continue
            inner[j:j + len(newhex)] = newhex
            n += 1
        print(f"  {name}: {n} occurrence(s) -> #{r:02X}{g:02X}{b:02X}")
        total += n
    return total


def main():
    d = open(STUB, "rb").read()
    off, size = find_style_resource(d)
    blob = d[off:off + size]
    sig = b"VCL_STYLE 2.0"
    assert blob[:len(sig)] == sig, "unexpected style signature"
    inner = bytearray(zlib.decompress(blob[len(sig):]))
    print(f"style stream: {size} bytes, inner {len(inner)}")

    # locate the raw BGRA atlases via their UTF-16 '.png' names
    tail_start = 0
    p = 0
    n_img = 0
    while True:
        i = inner.find(b"\x2e\x00p\x00n\x00g\x00", p)
        if i < 0:
            break
        w, h = struct.unpack_from("<II", inner, i + 8)
        if not (16 <= w <= 4096 and 16 <= h <= 4096):
            p = i + 8
            continue
        px_off = i + 16
        n_pix = w * h
        changed = 0
        for k in range(n_pix):
            o = px_off + k * 4
            b, g, r, a = inner[o], inner[o + 1], inner[o + 2], inner[o + 3]
            res = transform_pixel(r, g, b, a)
            if res is not None:
                r2, g2, b2 = res
                inner[o], inner[o + 1], inner[o + 2] = b2, g2, r2
                changed += 1
        print(f"atlas {n_img}: {w}x{h} at {hex(px_off)}, recolored {changed} px")
        n_img += 1
        tail_start = px_off + n_pix * 4
        p = tail_start
    assert n_img >= 1, "no atlases found"

    print("patching named string colors:")
    patch_string_colors(inner, tail_start)

    # property tail: recolor blue-dominant TColor dwords ($00BBGGRR, LE = rr gg bb 00).
    # A blind byte-scan corrupts structural dwords ("Integer overflow" on load),
    # so this only runs with --tail and takes an optional byte budget to bisect.
    if "--tail" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--tail") + 1]) if sys.argv.index("--tail") + 1 < len(sys.argv) and sys.argv[sys.argv.index("--tail") + 1].isdigit() else len(inner)
        changed = 0
        o = tail_start
        while o < min(len(inner), tail_start + limit) - 4:
            if inner[o + 3] == 0:
                r, g, b = inner[o], inner[o + 1], inner[o + 2]
                if is_blue(r, g, b):
                    r2, g2, b2 = shift(r, g, b)
                    inner[o], inner[o + 1], inner[o + 2] = r2, g2, b2
                    changed += 1
                    o += 4
                    continue
            o += 1
        print(f"property tail: recolored {changed} color dwords (budget {limit})")

    out = sig + zlib.compress(bytes(inner), 9)
    dst = os.path.join(ASSETS, "aowx_dark.vsf")
    open(dst, "wb").write(out)
    print(f"WROTE {dst} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
