"""
aowxlib.ilb - Age of Wonders 1 image library (.ILB) codec.

Clean-room implementation from the format specification (ILB desc.pdf) plus
empirical validation against the retail data:
    689/689 game ILBs parse, 689/689 rebuild byte-identically,
    4161/4161 RLE images re-encode to the original byte stream.

Nothing here is derived from the GPL sources of ILB Maker or AoWCGE.
"""
from __future__ import annotations
import struct, io

MAGIC = 0x424C4904          # "\x04ILB"
PAL_ID = 0x88801B18
PIXFMT_565 = 0x56509310

# ---- image types -----------------------------------------------------------
T_PICTURE08 = 1
T_RLESPRITE08 = 2
T_SPRITE08 = 3
T_PICTURE16 = 16
T_RLESPRITE16 = 17
T_TRANSPRLE16 = 18
T_SPRITE16 = 22

TYPE_NAMES = {
    0: "Empty", 1: "Picture08", 2: "RLESprite08", 3: "Sprite08",
    16: "Picture16", 17: "RLESprite16", 18: "TransparentRLESprite16",
    19: "BitMask", 20: "Shadow", 21: "TransparentPicture16", 22: "Sprite16",
}
TYPES_8BIT = (1, 2, 3)
TYPES_WITH_CLIPBOX = (2, 3, 17, 18, 22)
TYPES_WITH_CLIPX = (2, 17, 18)
TYPES_RLE = (2, 17, 18)

SHOW_MODES = {0: "smOpaque", 1: "smTransparent", 2: "smBlended"}
BLEND_MODES = {0: "bmUser", 1: "bmAlpha", 2: "bmBrighten",
               3: "bmIntensity", 4: "bmShadow", 5: "bmLinearAlpha"}
LOAD_MODES = {0: "lmInstant", 1: "lmWhenUsed", 2: "lmOnDemand", 3: "lmWhenReferenced"}

# clip_x "hack" values observed in retail data. The last three are NOT known to
# ILB Maker, which silently rewrites them to 0 and corrupts those libraries.
CLIPX_NAMES = {
    0x000000: "None",
    0x466214: "Item / Mountain / Structure",
    0x465EEC: "Tactical-combat map",
    0x466014: "ShieldsM",
    0x466344: "Unknown (0x466344)",
    0x465D4C: "Unknown (0x465D4C)",
    0x4673E8: "Unknown (0x4673E8)",
}


def s32(v):
    """clipwide/cliphigh/xshift/yshift are SIGNED; retail data relies on it."""
    return v - 0x100000000 if v >= 0x80000000 else v


def u32(v):
    return v & 0xFFFFFFFF


class Record(dict):
    """One image record: an image, a sub-image of a composite, or an empty."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    __setattr__ = dict.__setitem__

    @property
    def type_name(self):
        return TYPE_NAMES.get(self.get("type"), str(self.get("type")))

    @property
    def is_8bit(self):
        return self.get("type") in TYPES_8BIT

    @property
    def show_mode(self):
        dm = self.get("drawMode")
        return None if dm is None else dm & 0xFF

    @property
    def blend_mode(self):
        dm = self.get("drawMode")
        return None if dm is None else (dm >> 8) & 0xFF

    def set_draw(self, show, blend):
        self["drawMode"] = (int(show) & 0xFF) | ((int(blend) & 0xFF) << 8)

    @property
    def blank(self):
        """Retail data marks blank images with size 0 and a negative clip box."""
        return self.get("size", 0) == 0 or s32(self.get("cw", 1)) <= 0 or s32(self.get("ch", 1)) <= 0


class Image:
    """An ILB image: one record, or several when it is a composite (layers)."""

    def __init__(self, iid, parts=None, composite=False, empty=False, filler=0):
        self.id = iid
        self.parts = parts if parts is not None else []
        self.composite = composite
        self.empty = empty
        self.filler = filler

    @property
    def primary(self):
        return self.parts[0] if self.parts else None

    def __repr__(self):
        if self.empty:
            return f"<Image #{self.id} empty>"
        return f"<Image #{self.id} {len(self.parts)} part(s) {self.primary.type_name}>"


class IlbLibrary:
    def __init__(self):
        self.someId = 0x0040F000
        self.version = 4.0
        self.hdrLength = 24
        self.v3field = 0
        self.palettes = []          # list of 1024-byte blobs (256 * RGBX)
        self.images = []            # list of Image
        self.pixeldata = b""        # verbatim data section (v4)
        self.path = None

    # -- palette helpers ----------------------------------------------------
    def palette_rgb(self, index=0):
        if index < 0 or index >= len(self.palettes):
            return None
        blob = self.palettes[index]
        return [(blob[i * 4], blob[i * 4 + 1], blob[i * 4 + 2]) for i in range(256)]

    def set_palette_rgb(self, rgb, index=0):
        blob = bytearray(1024)
        for i, (r, g, b) in enumerate(rgb[:256]):
            blob[i * 4:i * 4 + 3] = bytes((r, g, b))
        while len(self.palettes) <= index:
            self.palettes.append(bytes(1024))
        self.palettes[index] = bytes(blob)

    # -- data access --------------------------------------------------------
    def record_bytes(self, rec):
        """Raw encoded pixel bytes for a record."""
        if rec.get("info") == 1:
            return rec.get("inline", b"")
        if rec.get("newdata") is not None:
            return rec["newdata"]
        off = rec.get("off", 0)
        return self.pixeldata[off:off + rec.get("size", 0)]

    def all_records(self):
        for img in self.images:
            for r in img.parts:
                yield img, r


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def read(path_or_bytes) -> IlbLibrary:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        d = bytes(path_or_bytes)
        path = None
    else:
        path = str(path_or_bytes)
        with open(path, "rb") as fh:
            d = fh.read()

    lib = IlbLibrary()
    lib.path = path
    o = 0

    def g32():
        nonlocal o
        v = struct.unpack_from("<I", d, o)[0]
        o += 4
        return v

    def g8():
        nonlocal o
        v = d[o]
        o += 1
        return v

    if g32() != MAGIC:
        raise ValueError("not an ILB file")
    lib.someId = g32()
    lib.version = struct.unpack_from("<f", d, o)[0]
    o += 4
    lib.hdrLength = g32()

    if lib.hdrLength == 24:
        img_dir = g32()
        g32()                                   # fileLength (recomputed on write)
        npal = g32()
        for _ in range(npal):
            if g32() != PAL_ID:
                raise ValueError("bad palette identifier")
            lib.palettes.append(d[o:o + 1024])
            o += 1024
    elif lib.hdrLength == 16:
        lib.v3field = g32()
        img_dir = None
    else:
        raise ValueError(f"unsupported header length {lib.hdrLength}")

    def read_record(t):
        nonlocal o
        r = Record(type=t)
        r["info"] = g8()
        nl = g32()
        r["name"] = d[o:o + nl].decode("latin-1")
        o += nl
        r["w"], r["h"], r["xs"], r["ys"], r["sub"] = struct.unpack_from("<5I", d, o)
        o += 20
        r["loadMode"] = g8()
        r["size"] = g32()
        if r["info"] != 1:
            r["off"] = g32()
        r["totw"] = g32()
        r["toth"] = g32()
        if t in TYPES_8BIT:
            r["unkB"] = g8()
            if r["info"] == 3:
                r["unkC"] = g32()
                r["unkD"] = g32()
            if r["info"] != 1:
                r["pal"] = g32()
        else:
            if r["info"] == 3:
                r["drawMode"] = g32()
                r["blendValue"] = g32()
            r["pixFmt"] = g32()
        if t in TYPES_WITH_CLIPBOX:
            r["cw"], r["ch"], r["cx"], r["cy"], r["transp"] = struct.unpack_from("<5I", d, o)
            o += 20
        if t in TYPES_WITH_CLIPX:
            r["clip_x"] = g32()
        if r["info"] == 1:
            r["inline"] = d[o:o + r["size"]]
            o += r["size"]
        r["newdata"] = None
        return r

    while True:
        iid = g32()
        if iid == 0xFFFFFFFF:
            break
        t = g32()
        composite = False
        if t == 0x100:
            composite = True
            t = g32()
        # A standalone Type-0 image is  id, 0, filler  with NO terminator.
        if t == 0 and not composite:
            lib.images.append(Image(iid, [], False, empty=True, filler=g32()))
            continue
        img = Image(iid, [], composite)
        while True:
            if t == 0:              # end of composite: no filler, no terminator
                break
            img.parts.append(read_record(t))
            if composite:
                t = g32()
                continue
            break
        end = g32()
        if end != 0xFFFFFFFF:
            raise ValueError(f"bad terminator {end:08X} after image #{iid}")
        lib.images.append(img)

    lib.pixeldata = d[o:]
    return lib


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------
def write(lib: IlbLibrary) -> bytes:
    """Serialise. Records whose 'newdata' is set are re-packed into the data
    section; everything else keeps its original bytes, so untouched libraries
    round-trip byte-for-byte."""
    data = io.BytesIO()
    order = []
    for img in lib.images:
        for r in img.parts:
            if r.get("info") == 1:
                continue
            payload = lib.record_bytes(r)
            order.append((r, data.tell(), len(payload)))
            data.write(payload)
    for r, off, size in order:
        r["off"] = off
        r["size"] = size

    body = io.BytesIO()

    def p32(v):
        body.write(struct.pack("<I", u32(v)))

    def p8(v):
        body.write(struct.pack("<B", v & 0xFF))

    def put(r):
        p32(r["type"])
        p8(r["info"])
        nm = r["name"].encode("latin-1", "replace")
        p32(len(nm))
        body.write(nm)
        body.write(struct.pack("<5I", u32(r["w"]), u32(r["h"]),
                               u32(r["xs"]), u32(r["ys"]), u32(r["sub"])))
        p8(r["loadMode"])
        p32(r["size"])
        if r["info"] != 1:
            p32(r["off"])
        p32(r["totw"])
        p32(r["toth"])
        if r["type"] in TYPES_8BIT:
            p8(r.get("unkB", 0))
            if r["info"] == 3:
                p32(r.get("unkC", 1))
                p32(r.get("unkD", 0))
            if r["info"] != 1:
                p32(r.get("pal", 0))
        else:
            if r["info"] == 3:
                p32(r.get("drawMode", 0))
                p32(r.get("blendValue", 0))
            p32(r.get("pixFmt", PIXFMT_565))
        if r["type"] in TYPES_WITH_CLIPBOX:
            body.write(struct.pack("<5I", u32(r["cw"]), u32(r["ch"]),
                                   u32(r["cx"]), u32(r["cy"]), u32(r["transp"])))
        if r["type"] in TYPES_WITH_CLIPX:
            p32(r.get("clip_x", 0))
        if r["info"] == 1:
            body.write(r.get("inline", b""))

    for img in lib.images:
        p32(img.id)
        if img.empty:
            p32(0)
            p32(img.filler)
            continue
        if img.composite:
            p32(0x100)
            for r in img.parts:
                put(r)
            p32(0)
        else:
            put(img.parts[0])
        p32(0xFFFFFFFF)
    p32(0xFFFFFFFF)
    directory = body.getvalue()

    head = io.BytesIO()
    head.write(struct.pack("<I", MAGIC))
    head.write(struct.pack("<I", u32(lib.someId)))
    head.write(struct.pack("<f", lib.version))
    head.write(struct.pack("<I", lib.hdrLength))
    if lib.hdrLength == 24:
        palblock = b"".join(struct.pack("<I", PAL_ID) + p for p in lib.palettes)
        img_dir = 24 + 4 + len(palblock) + len(directory)
        pixels = data.getvalue()
        head.write(struct.pack("<III", img_dir, img_dir + len(pixels), len(lib.palettes)))
        head.write(palblock)
        return head.getvalue() + directory + pixels
    head.write(struct.pack("<I", lib.v3field))
    return head.getvalue() + directory + lib.pixeldata


def save(lib: IlbLibrary, path):
    blob = write(lib)
    with open(path, "wb") as fh:
        fh.write(blob)
    return len(blob)


# ---------------------------------------------------------------------------
# pixel decoding  ->  RGBA tuples
# ---------------------------------------------------------------------------
def _c565(v):
    return (((v >> 11) & 31) * 255 // 31,
            ((v >> 5) & 63) * 255 // 63,
            (v & 31) * 255 // 31)


def to_rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def decode_record(lib: IlbLibrary, rec: Record):
    """Return (width, height, list-of-RGBA-rows) with transparent pixels a=0."""
    w, h = rec["w"], rec["h"]
    px = [[(0, 0, 0, 0)] * w for _ in range(h)]
    if rec.blank:
        return w, h, px
    t = rec["type"]
    data = lib.record_bytes(rec)
    cw, ch = s32(rec.get("cw", w)), s32(rec.get("ch", h))
    cx, cy = s32(rec.get("cx", 0)), s32(rec.get("cy", 0))
    if t not in TYPES_WITH_CLIPBOX:
        cw, ch, cx, cy = w, h, 0, 0
    back = rec.get("transp")
    pal = lib.palette_rgb(rec.get("pal", 0)) if t in TYPES_8BIT else None
    p = 0

    def setpx(x, y, rgb):
        if 0 <= x < w and 0 <= y < h:
            px[y][x] = (rgb[0], rgb[1], rgb[2], 255)

    try:
        if t == T_RLESPRITE08:
            b0 = (back or 0) & 0xFF
            for y in range(cy, cy + ch):
                ln = struct.unpack_from("<I", data, p)[0]
                p += 4
                n = ln - 4
                x = cx
                while n > 0:
                    v = data[p]
                    p += 1
                    n -= 1
                    if v == b0:
                        cnt = data[p]
                        p += 1
                        n -= 1
                        x += cnt
                    else:
                        if pal:
                            setpx(x, y, pal[v])
                        x += 1
        elif t in (T_RLESPRITE16, T_TRANSPRLE16):
            b0 = (back or 0) & 0xFFFF
            for y in range(cy, cy + ch):
                ln = struct.unpack_from("<I", data, p)[0]
                p += 4
                n = (ln - 4) // 2
                pad = (n % 2) > 0
                x = cx
                while n > 0:
                    v = struct.unpack_from("<H", data, p)[0]
                    p += 2
                    n -= 1
                    if v == b0:
                        cnt = struct.unpack_from("<H", data, p)[0]
                        p += 2
                        n -= 1
                        x += cnt // 2
                    else:
                        setpx(x, y, _c565(v))
                        x += 1
                if pad:
                    p += 2
        elif t in (T_PICTURE16, T_SPRITE16):
            b0 = None if back is None else back & 0xFFFF
            for y in range(cy, cy + ch):
                for x in range(cx, cx + cw):
                    v = struct.unpack_from("<H", data, p)[0]
                    p += 2
                    if t == T_SPRITE16 and b0 is not None and v == b0:
                        continue
                    setpx(x, y, _c565(v))
        elif t == T_PICTURE08:
            for y in range(cy, cy + ch):
                for x in range(cx, cx + cw):
                    v = data[p]
                    p += 1
                    if pal:
                        setpx(x, y, pal[v])
        elif t == T_SPRITE08:
            b0 = (back or 0) & 0xFF
            ddx = ((cw + 7) // 8) * 8 if cw >= 0x20 else ((cw + 3) // 4) * 4
            x = cx
            y = cy
            cnt = 0
            col = 0
            for _ in range(ch * ddx):
                if p >= len(data):
                    break
                if cnt == 0:
                    col = data[p]
                    p += 1
                    if col == b0:
                        cnt = data[p] if p < len(data) else 1
                        p += 1
                    else:
                        if pal:
                            setpx(x, y, pal[col])
                        cnt = 1
                cnt -= 1
                x += 1
                if x >= cx + ddx:
                    x = cx
                    y += 1
    except (struct.error, IndexError):
        pass                                    # truncated/odd record: show what we got
    return w, h, px


# ---------------------------------------------------------------------------
# pixel encoding
# ---------------------------------------------------------------------------
def encode_rle8(rows, back):
    """rows: list of rows of palette indices over the clip box."""
    out = bytearray()
    for row in rows:
        line = bytearray()
        run = 0
        for v in row:
            if v == back:
                run += 1
                if run == 255:                  # the run counter is ONE BYTE
                    line += bytes((back, 255))
                    run = 0
            else:
                if run:
                    line += bytes((back, run))
                    run = 0
                line.append(v)
        if run:
            line += bytes((back, run))
        out += struct.pack("<I", len(line) + 4) + line
    return bytes(out)


def encode_rle16(rows, back):
    out = bytearray()
    for row in rows:
        line = bytearray()
        run = 0
        for v in row:
            if v == back:
                run += 1
                if run == 16383:
                    line += struct.pack("<HH", back, 2 * run)
                    run = 0
            else:
                if run:
                    line += struct.pack("<HH", back, 2 * run)
                    run = 0
                line += struct.pack("<H", v)
        if run:
            line += struct.pack("<HH", back, 2 * run)
        nvals = len(line) // 2
        out += struct.pack("<I", 2 * nvals + 4) + line
        if nvals % 2:
            out += struct.pack("<H", back)
    return bytes(out)


def encode_raw16(rows):
    out = bytearray()
    for row in rows:
        for v in row:
            out += struct.pack("<H", v)
    return bytes(out)


def encode_raw8(rows):
    out = bytearray()
    for row in rows:
        out += bytes(row)
    return bytes(out)


def _bbox(rows, back, w, h):
    top, left, bottom, right = h, w, -1, -1
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v != back:
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y
                if x < left:
                    left = x
                if x > right:
                    right = x
    if bottom < 0:
        return 0, 0, 0, 0, True
    return left, top, right - left + 1, bottom - top + 1, False


def encode_image(lib: IlbLibrary, rec: Record, pil_img, transparent_rgb=(255, 0, 255)):
    """Encode a PIL RGB/RGBA image into `rec` (updates size/clip box/data).

    8-bit types map onto the library's existing palette (nearest colour), which
    is what you want when adding frames to an existing unit library. If the
    library has no palette yet, one is built from this image.
    """
    t = rec["type"]
    img = pil_img.convert("RGBA")
    w, h = img.size
    src = img.load()
    rec["w"], rec["h"] = w, h
    rec["totw"], rec["toth"] = w + s32(rec.get("xs", 0)), h + s32(rec.get("ys", 0))

    if t in TYPES_8BIT:
        pal = lib.palette_rgb(rec.get("pal", 0))
        if pal is None:
            q = img.convert("RGB").quantize(colors=255, method=1)
            gp = q.getpalette()[:768]
            pal = [tuple(gp[i * 3:i * 3 + 3]) for i in range(256)]
            pal[0] = transparent_rgb
            lib.set_palette_rgb(pal, 0)
            rec["pal"] = 0
        back_idx = _nearest(pal, transparent_rgb)
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                r, g, b, a = src[x, y]
                row.append(back_idx if a < 128 else _nearest(pal, (r, g, b)))
            rows.append(row)
        rec["transp"] = back_idx
        left, top, cw, ch, blank = _bbox(rows, back_idx, w, h)
        if t in TYPES_WITH_CLIPBOX:
            rec["cx"], rec["cy"], rec["cw"], rec["ch"] = left, top, cw, ch
        if blank:
            rec["newdata"] = b""
            rec["size"] = 0
            return
        crop = [r[left:left + cw] for r in rows[top:top + ch]]
        rec["newdata"] = encode_rle8(crop, back_idx) if t == T_RLESPRITE08 else encode_raw8(crop)
    else:
        back = to_rgb565(*transparent_rgb)
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                r, g, b, a = src[x, y]
                if a < 128:
                    row.append(back)
                else:
                    v = to_rgb565(r, g, b)
                    row.append(back + 1 if v == back else v)
            rows.append(row)
        rec["pixFmt"] = PIXFMT_565
        if t in TYPES_WITH_CLIPBOX:
            rec["transp"] = back
            left, top, cw, ch, blank = _bbox(rows, back, w, h)
            rec["cx"], rec["cy"], rec["cw"], rec["ch"] = left, top, cw, ch
            if blank:
                rec["newdata"] = b""
                rec["size"] = 0
                return
            crop = [r[left:left + cw] for r in rows[top:top + ch]]
            rec["newdata"] = (encode_rle16(crop, back) if t in TYPES_RLE
                              else encode_raw16(crop))
        else:
            rec["newdata"] = encode_raw16(rows)
    rec["size"] = len(rec["newdata"])


def _nearest(pal, rgb):
    r, g, b = rgb
    best = 0
    bd = 1 << 30
    for i, (pr, pg, pb) in enumerate(pal):
        d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if d < bd:
            bd = d
            best = i
            if d == 0:
                break
    return best


def new_record(type_=T_RLESPRITE16, name="new.bmp", info=3):
    r = Record(type=type_, info=info, name=name, w=0, h=0, xs=0, ys=0, sub=0,
               loadMode=1, size=0, off=0, totw=0, toth=0, newdata=b"")
    if type_ in TYPES_8BIT:
        r["unkB"] = 0
        r["unkC"] = 1
        r["unkD"] = 0
        r["pal"] = 0
    else:
        r["pixFmt"] = PIXFMT_565
        if info == 3:
            r["drawMode"] = 0x0100
            r["blendValue"] = 0
    if type_ in TYPES_WITH_CLIPBOX:
        r["cw"] = r["ch"] = r["cx"] = r["cy"] = 0
        r["transp"] = 0
    if type_ in TYPES_WITH_CLIPX:
        r["clip_x"] = 0
    return r
