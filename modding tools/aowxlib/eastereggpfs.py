#!/usr/bin/env python3
r"""
aowxlib.eastereggpfs - reader/writer for Release\easteregg.pfs (AoWx easter-egg data, 2026-10-19).

Container = the game's own .pfs framing (same as Release\Ability.pfs / Spells.pfs):
    [dword 0x2144DF1C] [payload] [dword CRC-32(payload)]
payload:
    01 00 00                      3 prefix bytes (as in Ability.pfs)
    80                            top-index count byte: 0 small entries, wide entries follow
    dword W                       number of records
    W x (dword KEY, dword OFF)    ascending KEY, OFF relative to the body start
    body                          the records back to back
KEY = (TYPE << 16) | INDEX        -> every record carries its type, so new kinds of easter-egg data can be added
                                     later without touching the old ones (types are listed in TYPES below).
record = a small pfs tag table:
    byte n, n x (byte TAG, byte OFF), values      (OFF relative to the end of the tag table)
    TAG 1 = dword TYPE (same as KEY >> 16)
    TAG 2 = text: dword LEN + LEN bytes (latin-1, no terminator)  - the in-game reader takes tag 2
    further tags may be added per type.

TYPES:
    1 = title-screen flavour quote (AoWx.exe, patch_exe_title_quotes_v1.py picks one at random on every entry to the
        title screen; drawn bottom-left in the version font; <= 480 characters are used)

CLI:
    py -3.10 -m aowxlib.eastereggpfs dump  <easteregg.pfs> [out.txt]     -> "[type N]" sections, one text per line
    py -3.10 -m aowxlib.eastereggpfs build <in.txt> <easteregg.pfs>       (same text layout; lines before the first
                                                                           "[type N]" header are type 1; '#' comments
                                                                           and blank lines are ignored)
"""
import struct, sys, zlib

MAGIC = 0x2144DF1C
PREFIX = b"\x01\x00\x00"
TYPES = {1: "title quote"}
T_TITLE_QUOTE = 1
TAG_TYPE, TAG_TEXT = 1, 2


def build_record(rtype, text):
    t = text.encode("latin-1")
    vals = [(TAG_TYPE, struct.pack("<I", rtype)), (TAG_TEXT, struct.pack("<I", len(t)) + t)]
    data = b""; tab = b""
    for tag, v in vals:
        assert len(data) <= 0xFF
        tab += bytes([tag, len(data)]); data += v
    return bytes([len(vals)]) + tab + data


def parse_record(rec):
    n = rec[0] & 0x7F
    tab = [(rec[1 + 2 * k], rec[2 + 2 * k]) for k in range(n)]
    base = 1 + 2 * n
    out = {}
    for tag, o in tab:
        p = base + o
        if tag == TAG_TYPE:
            out[tag] = struct.unpack_from("<I", rec, p)[0]
        elif tag == TAG_TEXT:
            ln = struct.unpack_from("<I", rec, p)[0]
            out[tag] = rec[p + 4:p + 4 + ln].decode("latin-1")
    return out


def write(entries):
    """entries: list of (type, text) in the wanted order (index = position within its type)."""
    per = {}
    recs = []
    for rtype, text in entries:
        idx = per.get(rtype, 0); per[rtype] = idx + 1
        recs.append(((rtype << 16) | idx, build_record(rtype, text)))
    recs.sort(key=lambda r: r[0])
    body = b""; index = b""
    for key, rec in recs:
        index += struct.pack("<II", key, len(body)); body += rec
    payload = PREFIX + b"\x80" + struct.pack("<I", len(recs)) + index + body
    return struct.pack("<I", MAGIC) + payload + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)


def read(data):
    assert struct.unpack_from("<I", data, 0)[0] == MAGIC, "not a pfs file"
    payload = data[4:-4]
    assert zlib.crc32(payload) & 0xFFFFFFFF == struct.unpack_from("<I", data, len(data) - 4)[0], "pfs CRC invalid"
    p = len(PREFIX); n = payload[p]; p += 1
    small = n & 0x7F; wide = 0
    if n & 0x80:
        wide = struct.unpack_from("<I", payload, p)[0]; p += 4
    p += 2 * small
    keys = [struct.unpack_from("<II", payload, p + 8 * k) for k in range(wide)]
    body = payload[p + 8 * wide:]
    offs = sorted(o for _k, o in keys)
    out = []
    for key, o in keys:
        nxt = [x for x in offs if x > o]
        f = parse_record(body[o:nxt[0] if nxt else len(body)])
        out.append((key >> 16, key & 0xFFFF, f.get(TAG_TEXT, "")))
    return out


def dump_text(entries):
    lines = ["# Release\\easteregg.pfs - one text per line, grouped by type (%s)"
             % ", ".join("%d = %s" % kv for kv in TYPES.items())]
    cur = None
    for rtype, _idx, text in entries:
        if rtype != cur:
            lines.append("[type %d]" % rtype); cur = rtype
        lines.append(text)
    return "\r\n".join(lines) + "\r\n"


def parse_text(txt):
    rtype = T_TITLE_QUOTE; out = []
    for l in txt.splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("[type ") and s.endswith("]"):
            rtype = int(s[6:-1]); continue
        out.append((rtype, s))
    return out


def _main(argv):
    if len(argv) < 2 or argv[0] not in ("dump", "build"):
        print(__doc__); return 2
    if argv[0] == "dump":
        txt = dump_text(read(open(argv[1], "rb").read()))
        if len(argv) > 2:
            open(argv[2], "w", encoding="latin-1", newline="").write(txt); print("dumped ->", argv[2])
        else:
            sys.stdout.write(txt)
        return 0
    if len(argv) < 3:
        print(__doc__); return 2
    ents = parse_text(open(argv[1], encoding="latin-1").read())
    open(argv[2], "wb").write(write(ents)); print("%d records -> %s" % (len(ents), argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
