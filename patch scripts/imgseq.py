#!/usr/bin/env python3
"""TImageSequenceList stream (Release.hss image-list fields) parser / writer.
List: u32 count; per slot u8 nil flag (0 = present, else nil) [+ sequence].
Sequence: Delphi string ILB name (u32 len + bytes), u8 a, u8 b, u8 mode, i32 frame, i32 xoff, i32 yoff,
[mode 4/5: u32 z, u32 n, n x u32 frames], u8 hasSub (!=0 -> a chained sub-sequence follows)."""
import struct


def parse_seq(b, p):
    n = struct.unpack_from("<I", b, p)[0]; p += 4
    s = dict(name=bytes(b[p:p + n]).decode("latin1")); p += n
    s["a"], s["b"], s["mode"] = b[p], b[p + 1], b[p + 2]; p += 3
    s["frame"], s["x"], s["y"] = struct.unpack_from("<iii", b, p); p += 12
    if s["mode"] in (4, 5):
        z, k = struct.unpack_from("<II", b, p); p += 8
        s["z"] = z
        s["frames"] = list(struct.unpack_from("<%dI" % k, b, p)); p += 4 * k
    has = b[p]; p += 1
    s["sub"] = None
    if has:
        s["sub"], p = parse_seq(b, p)
    return s, p


def parse_list(b, p):
    cnt = struct.unpack_from("<I", b, p)[0]; p += 4
    out = []
    for _ in range(cnt):
        nil = b[p]; p += 1
        if nil:
            out.append(None)
        else:
            s, p = parse_seq(b, p); out.append(s)
    return out, p


def enc_seq(s):
    n = s["name"].encode("latin1")
    out = struct.pack("<I", len(n)) + n + bytes([s["a"], s["b"], s["mode"]]) + struct.pack("<iii", s["frame"], s["x"], s["y"])
    if s["mode"] in (4, 5):
        out += struct.pack("<II", s.get("z", 0), len(s["frames"])) + struct.pack("<%dI" % len(s["frames"]), *s["frames"])
    if s.get("sub"):
        out += b"\x01" + enc_seq(s["sub"])
    else:
        out += b"\x00"
    return out


def enc_list(lst):
    out = struct.pack("<I", len(lst))
    for s in lst:
        out += b"\x01" if s is None else b"\x00" + enc_seq(s)
    return out


def show(lst):
    for i, s in enumerate(lst):
        if s is None:
            continue
        t = s; chain = []
        while t:
            chain.append("%s a%d b%d m%d f%d (%d,%d)%s" % (t["name"], t["a"], t["b"], t["mode"], t["frame"], t["x"], t["y"],
                                                         (" frames=%s" % t["frames"]) if "frames" in t else ""))
            t = t["sub"]
        print("   slot %2d (0x%02x): %s" % (i, i, " | ".join(chain)))
