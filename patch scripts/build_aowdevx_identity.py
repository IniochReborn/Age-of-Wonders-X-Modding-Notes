#!/usr/bin/env python3
r"""AoWDevX.exe: title-bar text "AoWEd" -> "AoWDevX" + new icon.

Three in-place patches (no resource shifting anywhere):

1. Title. The .dpr startup does `Application.Title := 'AoWEd'` via a constant
   AnsiString literal at the CODE tail (refcount -1 @0x2e3e0, len 5, chars
   @0x2e3e8 = VA 0x42efe8; single code ref: `mov edx,$42efe8` operand at file
   0x2e25f). The main window title shows this string. "AoWDevX" doesn't fit
   the 5-char literal, so a new constant-format literal is written into the
   16 zero bytes at the very end of CODE's raw data (file 0x2e3f0, VA
   0x42eff0) and the mov operand is repointed to its chars (VA 0x42eff8).
   CODE's VirtualSize is bumped 0x2dff0 -> 0x2e000 so the loader is
   guaranteed to map those tail bytes.

2. Explorer/taskbar icon. MAINICON is a single 32x32 32bpp RT_ICON of exactly
   4264 bytes at file 0x446c4 — ALREADY the intended art (black dragon over
   green hexes, the editor remaster); kept byte-identical (restored from the
   backup if a previous build replaced it).

3. Title-bar icon. The MainForm DFM carries its own Icon.Data (766-byte ICO,
   32x32 4bpp) which Delphi uses for the window; it held the plain red
   dragon — replaced with a 16-color quantized version of the SAME black
   dragon + green hex art, byte-for-byte same size.

4. Title-bar text (the real source). MainForm.Caption does NOT come from
   Application.Title — it is the AoWE unit's Multilizer resourcestring
   AoWEdRStr, whose VALUE ('AoWEd') lives in AoWEPACK.dll's RT_STRING table
   (patching that would also retitle vanilla AoWEd.exe). AoWDevX imports the
   ResStringRec as 'AoWE.AoWEdRStr@04ECFCC5' (IAT slot VA 0x432934) and four
   CODE sites do `lea edx,[ebp-X] / mov eax,[slot] / call load-res-helper`
   into a fresh nil-initialized local AnsiString, then feed the result
   through TranslateRStr (unknown text passes through). Fix: a 7-byte cave
   in the .dlgd slack — `mov dword [edx], <'AoWDevX' chars>; ret` (constant
   literal, refcount -1, so skipping refcounting is correct and the nil dest
   needs no release) — and each of the four call rel32s retargeted to it.
   .dlgd VirtualSize bumped 0x3de -> 0x400 so the tail bytes are mapped.

Usage:
    python build_aowdevx_identity.py            # dry run
    python build_aowdevx_identity.py --apply    # back up + patch
    python build_aowdevx_identity.py --revert   # restore backup
"""
import os, shutil, struct, sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
EXE = os.path.join(GAME, "AoWDevX.exe")
BAK = EXE + ".bak_identity"

# -- title literal --
MOV_OPERAND_OFF = 0x2e25f          # operand of mov edx,$42efe8
OLD_CHARS_VA = 0x42EFE8
CAVE_OFF = 0x2e3f0                 # 16 zero bytes at CODE raw tail
NEW_CHARS_VA = 0x42EFF8
NEW_TITLE = b"AoWDevX"

# -- icons --
RT_ICON_OFF = 0x446c4              # RT_ICON 3/1: 32x32 32bpp, 4264 bytes
RT_ICON_SIZE = 4264
DFM_ICO_SIZE = 766                 # MainForm Icon.Data payload (32x32 4bpp ICO)

# -- caption resourcestring redirect (see docstring pt. 4) --
RSTR_SITES = [0x27a65, 0x29b31, 0x29b8d, 0x29bd5]   # file offs of the IAT-slot
                                                    # operand (a1 34 29 43 00)
RSTR_IAT_SLOT = 0x432934
CAPTION_CAVE_OFF = 0xdcfe0         # .dlgd slack (raw 0xdcc00 + 0x3e0)
CAPTION_CAVE_VA = 0x4E13E0
CAPTION_CAVE = (b"\xc7\x02" + struct.pack("<I", NEW_CHARS_VA)  # mov [edx],chars
                + b"\xc3")                                     # ret


def load_original_art():
    """The intended art = the exe's own original MAINICON image (32x32 32bpp
    black dragon over green hexes). Read from the backup when present (a
    previous build of this script overwrote the live copy); returns
    (RGBA image, exact original resource bytes)."""
    src = BAK if os.path.isfile(BAK) else EXE
    d = open(src, "rb").read()
    payload = d[RT_ICON_OFF:RT_ICON_OFF + RT_ICON_SIZE]
    bi = struct.unpack_from("<IiiHH", payload)
    assert bi == (40, 32, 64, 1, 32), f"unexpected RT_ICON header in {src}: {bi}"
    art = Image.new("RGBA", (32, 32))
    px = art.load()
    off = 40
    for row in range(32):
        y = 31 - row
        for x in range(32):
            b, g, r, a = payload[off:off + 4]
            px[x, y] = (r, g, b, a)
            off += 4
    return art, payload


def make_dfm_ico(art):
    """766-byte ICO: 32x32 4bpp + 1bpp mask (same layout as the original)."""
    px = art.load()
    opaque = Image.new("RGB", (32, 32), (0, 0, 0))
    for y in range(32):
        for x in range(32):
            r, g, b, a = px[x, y]
            if a >= 128:
                opaque.putpixel((x, y), (r, g, b))
    q = opaque.quantize(colors=16)
    pal = (q.getpalette() + [0] * 48)[:48]
    qpx = q.load()

    hdr = struct.pack("<IiiHHIIiiII", 40, 32, 64, 1, 4, 0, 0, 0, 0, 0, 0)
    palette = b"".join(bytes((pal[i * 3 + 2], pal[i * 3 + 1], pal[i * 3], 0))
                       for i in range(16))
    pix = bytearray()
    for y in range(31, -1, -1):
        for x in range(0, 32, 2):
            pix.append((qpx[x, y] << 4) | qpx[x + 1, y])
    mask = bytearray()
    for y in range(31, -1, -1):
        row = 0
        for x in range(32):
            if px[x, y][3] < 128:
                row |= 1 << (31 - x)
        mask += struct.pack(">I", row)
    bmp = hdr + palette + bytes(pix) + bytes(mask)
    ico = (b"\x00\x00\x01\x00\x01\x00"
           + struct.pack("<BBBBHHII", 32, 32, 16, 0, 0, 0, len(bmp), 22)
           + bmp)
    assert len(ico) == DFM_ICO_SIZE, len(ico)
    return ico


def code_vsize_field_off(d):
    peoff = struct.unpack_from("<I", d, 0x3C)[0]
    optsz = struct.unpack_from("<H", d, peoff + 20)[0]
    sec0 = peoff + 24 + optsz
    assert d[sec0:sec0 + 8].rstrip(b"\0") == b"CODE"
    return sec0 + 8


def dlgd_vsize_field_off(d):
    peoff = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, peoff + 6)[0]
    optsz = struct.unpack_from("<H", d, peoff + 20)[0]
    sec0 = peoff + 24 + optsz
    for i in range(nsec):
        s = sec0 + i * 40
        if d[s:s + 8].rstrip(b"\0") == b".dlgd":
            return s + 8
    raise SystemExit("!! .dlgd section not found")


def find_dfm_icon(d):
    p = d.find(b"TPF0\x09TMainForm\x08MainForm")
    assert p >= 0, "TMainForm DFM not found"
    i = d.find(b"\x09Icon.Data\x0a", p)
    assert 0 < i < p + 0x200, "MainForm Icon.Data not found"
    ln = struct.unpack_from("<I", d, i + 11)[0]
    assert ln == DFM_ICO_SIZE, f"Icon.Data size {ln} != {DFM_ICO_SIZE}"
    return i + 15  # payload start


def main():
    mode = "--apply" if "--apply" in sys.argv else "--revert" if "--revert" in sys.argv else "dry"

    if mode == "--revert":
        if not os.path.isfile(BAK):
            print(f"!! no backup at {BAK}")
            return 1
        shutil.copy2(BAK, EXE)
        print(f"REVERTED {EXE} from {os.path.basename(BAK)}")
        return 0

    d = bytearray(open(EXE, "rb").read())

    # -- title --
    operand = struct.unpack_from("<I", d, MOV_OPERAND_OFF)[0]
    if operand == NEW_CHARS_VA:
        print("title already patched")
        title_todo = False
    else:
        assert operand == OLD_CHARS_VA, f"mov operand is {hex(operand)}, expected {hex(OLD_CHARS_VA)}"
        assert d[MOV_OPERAND_OFF - 1] == 0xBA, "not a mov edx,imm32 site"
        assert d[CAVE_OFF:CAVE_OFF + 16] == b"\x00" * 16, "CODE tail cave not empty"
        title_todo = True
    vs_off = code_vsize_field_off(d)
    vsize = struct.unpack_from("<I", d, vs_off)[0]
    assert vsize in (0x2DFF0, 0x2E000), hex(vsize)

    # -- icons --
    bi = struct.unpack_from("<IiiHH", d, RT_ICON_OFF)
    assert bi == (40, 32, 64, 1, 32), f"RT_ICON header mismatch: {bi}"
    dfm_off = find_dfm_icon(d)

    # -- caption redirect --
    cave_done = bytes(d[CAPTION_CAVE_OFF:CAPTION_CAVE_OFF + len(CAPTION_CAVE)]) == CAPTION_CAVE
    if not cave_done:
        assert d[CAPTION_CAVE_OFF:CAPTION_CAVE_OFF + len(CAPTION_CAVE)] == b"\x00" * len(CAPTION_CAVE), \
            ".dlgd cave not empty"
    site_todo = []
    for o in RSTR_SITES:
        assert d[o - 1] == 0xA1 and struct.unpack_from("<I", d, o)[0] == RSTR_IAT_SLOT, \
            f"site {hex(o)}: expected mov eax,[{hex(RSTR_IAT_SLOT)}]"
        assert d[o + 4] == 0xE8, f"site {hex(o)}: expected call after the mov"
        call_va = 0x401000 + (o + 4 - 0x400)
        cur_tgt = (call_va + 5 + struct.unpack_from("<i", d, o + 5)[0]) & 0xFFFFFFFF
        if cur_tgt != CAPTION_CAVE_VA:
            site_todo.append((o, call_va))
    dvs_off = dlgd_vsize_field_off(d)
    dvs = struct.unpack_from("<I", d, dvs_off)[0]
    assert dvs in (0x3DE, 0x400), hex(dvs)

    art, rt = load_original_art()
    dfm = make_dfm_ico(art)

    print(f"title  : literal 'AoWDevX' -> cave @{hex(CAVE_OFF)} (VA {hex(NEW_CHARS_VA - 8)}), "
          f"mov operand @{hex(MOV_OPERAND_OFF)} {hex(OLD_CHARS_VA)}->{hex(NEW_CHARS_VA)}, "
          f"CODE vsize {hex(vsize)}->0x2e000" + ("" if title_todo else " (already done)"))
    print(f"icon   : RT_ICON @{hex(RT_ICON_OFF)} kept as the original dragon+green-hex art")
    print(f"icon   : MainForm DFM Icon.Data @{hex(dfm_off)} ({DFM_ICO_SIZE} B, in place, same art 16-color)")
    print(f"caption: cave @{hex(CAPTION_CAVE_OFF)} (VA {hex(CAPTION_CAVE_VA)}), "
          f"{len(site_todo)}/{len(RSTR_SITES)} AoWEdRStr call sites to retarget, "
          f".dlgd vsize {hex(dvs)}->0x400")

    if mode == "dry":
        preview = os.path.join(HERE, "installer", "assets", "aowdevx_icon_preview.png")
        art.resize((128, 128), Image.NEAREST).save(preview)
        print(f"icon preview -> {preview}")
        print("\nDRY RUN — rerun with --apply to patch")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print(f"backed up -> {os.path.basename(BAK)}")

    if title_todo:
        d[CAVE_OFF:CAVE_OFF + 16] = (b"\xff\xff\xff\xff"
                                     + struct.pack("<I", len(NEW_TITLE))
                                     + NEW_TITLE + b"\x00")
        struct.pack_into("<I", d, MOV_OPERAND_OFF, NEW_CHARS_VA)
    struct.pack_into("<I", d, vs_off, 0x2E000)
    d[RT_ICON_OFF:RT_ICON_OFF + RT_ICON_SIZE] = rt
    d[dfm_off:dfm_off + DFM_ICO_SIZE] = dfm
    d[CAPTION_CAVE_OFF:CAPTION_CAVE_OFF + len(CAPTION_CAVE)] = CAPTION_CAVE
    for o, call_va in site_todo:
        struct.pack_into("<i", d, o + 5, CAPTION_CAVE_VA - (call_va + 5))
    struct.pack_into("<I", d, dvs_off, 0x400)
    open(EXE, "wb").write(d)
    print(f"WROTE {EXE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
