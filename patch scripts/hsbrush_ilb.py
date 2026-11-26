#!/usr/bin/env python3
r"""
HSEPack HSEditModule.HSBrushes library (old v2.0 ILB, inline records) - reader / writer + RLE16 codec (2026-10-31).
Layout: 'ILB' header 0x14 B (magic, id, float 2.0, hdrLength 16, v3field) then images:
  id u32, type u32 (17), info u8 (0), name (u32 len + bytes), w h xs ys sub (5 u32), loadMode u8, size u32,
  pixFmt totw toth + 4 zero dwords (28 B), pixel data (size + 4 B: per row u32 byte-length incl. itself, then u16
  values; 0x0000 = transparent, followed by a u16 skip*2; length excludes the padding to 4), terminator 0xFFFFFFFF.  End 0xFFFFFFFF.
"""
import struct


def parse(d):
    hdr = d[:0x14]; o = 0x14; imgs = []
    while True:
        iid = struct.unpack_from("<I", d, o)[0]
        if iid == 0xFFFFFFFF:
            break
        st = o
        t = struct.unpack_from("<I", d, o + 4)[0]; o += 8
        info = d[o]; o += 1
        nl = struct.unpack_from("<I", d, o)[0]; o += 4
        name = d[o:o + nl]; o += nl
        w, h, xs, ys, sub = struct.unpack_from("<5I", d, o); o += 20
        lm = d[o]; o += 1
        size = struct.unpack_from("<I", d, o)[0]; o += 4
        meta = d[o:o + 28]; data = d[o + 28:o + 32 + size]; o += 32 + size
        assert struct.unpack_from("<I", d, o)[0] == 0xFFFFFFFF; o += 4
        imgs.append(dict(id=iid, type=t, info=info, name=name, w=w, h=h, xs=xs, ys=ys, sub=sub, lm=lm, meta=meta,
                         data=data, raw=d[st:o]))
    return hdr, imgs, d[o:]


def decode(img):
    w, h, data = img["w"], img["h"], img["data"]
    px = [[None] * w for _ in range(h)]; p = 0
    for y in range(h):
        if p + 4 > len(data):
            break
        ln = struct.unpack_from("<I", data, p)[0]; end = min(len(data), p + ln); p += 4; x = 0
        while p + 1 < end:
            v = struct.unpack_from("<H", data, p)[0]; p += 2
            if v == 0:
                if p + 1 >= end:
                    break
                x += struct.unpack_from("<H", data, p)[0] // 2; p += 2
            else:
                if x < w:
                    px[y][x] = v
                x += 1
        p = (end + 3) & ~3
    return px


def encode(px):
    out = bytearray()
    for row in px:
        r = bytearray(); x = 0; w = len(row)
        while x < w:
            if row[x] is None:
                n = 0
                while x < w and row[x] is None:
                    n += 1; x += 1
                r += struct.pack("<HH", 0, n * 2)
            else:
                r += struct.pack("<H", row[x]); x += 1
        out += struct.pack("<I", len(r) + 4) + r          # length excludes the padding
        if len(out) % 4:
            out += b"\0" * (4 - len(out) % 4)
    return bytes(out) + bytes(4)                           # + the trailing zero dword the originals carry


def build_image(iid, name, px, tpl):
    h = len(px); w = len(px[0])
    data = encode(px)
    meta = bytearray(tpl["meta"]); struct.pack_into("<II", meta, 4, w, h)
    rec = struct.pack("<II", iid, 17) + bytes([0]) + struct.pack("<I", len(name)) + name
    rec += struct.pack("<5I", w, h, 0, 0, tpl["sub"]) + bytes([tpl["lm"]]) + struct.pack("<I", len(data) - 4)
    rec += bytes(meta) + data + b"\xff\xff\xff\xff"
    return rec
