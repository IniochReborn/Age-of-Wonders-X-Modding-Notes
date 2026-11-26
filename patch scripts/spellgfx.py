#!/usr/bin/env python3
r"""
Spells.pfs tag 0xC (TImageSequenceList) and tag 0xB (sound list) codecs - RE'd from ILPACK.dpl
ImageLib.TImageSequenceList/TImageSequence/TFrameTableList.LoadFromStream (0x552190D8 / 0x55218A60 / 0x55219F1C)
and from the vanilla sound blobs (2026-10-06).

tag 0xC stream:
  u32 count; per slot: u8 flag (0 = a sequence follows, else the slot is EMPTY).
  sequence: u32 len + name (ILB path, relative to Images\); u8 f8; u8 f18; u8 kind; u32 f20; i32 xs; i32 ys;
            if kind in (4, 5): frame table = u32 ft10, u32 n, n x u32 image ids;  (kind 0 = static image, f20 = id)
            u8 chain: nonzero -> another sequence follows and is chained into the SAME slot (recursive).
  Vanilla layout: slot 0.. effect sequences, the SPELLICN.ILB icon (kind 0, f20 = image id), BORDER.ILB x3 last.
tag 0xB stream (sound list):
  01 01 00 | u8 N | 00 00 | (idx, offset) byte pairs for idx>=1 | entries, where an entry is either
  single:  02 00 21 00 01 | 01 00 01 00 00 01 00 21 00 01 | 05 00 len str
  list:    02 00 21 00 02 | 05 00 01 04 01 00 00 00 | u8 n 00 00 (idx, offset) pairs | n x (01 00 21 00 01 05 00 len str)
  Python shape: [entry, ...] with entry = "path" (single) or ["path", ...] (list).

`python spellgfx.py` runs the round-trip self-test over every record of the live Spells.pfs.
"""
import struct, os, sys, zlib
import sys as _sys; _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import game_dir, game_file   # 2026-10-11: de-baked


# ---------------------------------------------------------------- tag 0xC
def _seq_parse(v, o):
    ln = struct.unpack_from("<I", v, o)[0]; o += 4
    s = {"name": v[o:o + ln].decode("latin1")}; o += ln
    s["f8"], s["f18"], s["kind"] = v[o], v[o + 1], v[o + 2]; o += 3
    s["f20"], s["xs"], s["ys"] = struct.unpack_from("<Iii", v, o); o += 12
    if s["kind"] in (4, 5):
        s["ft10"], n = struct.unpack_from("<II", v, o); o += 8
        s["frames"] = list(struct.unpack_from("<%dI" % n, v, o)); o += 4 * n
    chain = v[o]; o += 1
    s["chain"] = None
    if chain:
        s["chain"], o = _seq_parse(v, o)
    return s, o


def seq_parse(v):
    """-> list of slots (None = empty, else sequence dict with optional 'chain')."""
    n = struct.unpack_from("<I", v, 0)[0]; o = 4; slots = []
    for _ in range(n):
        flag = v[o]; o += 1
        if flag:
            slots.append(None); continue
        s, o = _seq_parse(v, o)
        slots.append(s)
    assert o == len(v), "trailing bytes in sequence list (%d of %d)" % (o, len(v))
    return slots


def _seq_build(s):
    nm = s["name"].encode("latin1")
    out = struct.pack("<I", len(nm)) + nm + bytes([s["f8"], s["f18"], s["kind"]]) + struct.pack("<Iii", s["f20"], s["xs"], s["ys"])
    if s["kind"] in (4, 5):
        fr = s["frames"]
        out += struct.pack("<II", s["ft10"], len(fr)) + struct.pack("<%dI" % len(fr), *fr)
    if s.get("chain"):
        out += b"\x01" + _seq_build(s["chain"])
    else:
        out += b"\x00"
    return out


def seq_build(slots):
    out = struct.pack("<I", len(slots))
    for s in slots:
        out += b"\x01" if s is None else b"\x00" + _seq_build(s)
    return out


def seq_entry(name, frames, xs, ys, kind=4, f8=0, f18=0, f20=None, ft10=0):
    """A fresh animated slot (kind 4 = frame sequence, the usual effect kind)."""
    return {"name": name, "f8": f8, "f18": f18, "kind": kind, "f20": len(frames) if f20 is None else f20,
            "xs": xs, "ys": ys, "ft10": ft10, "frames": list(frames), "chain": None}


# ---------------------------------------------------------------- tag 0xB
def _snd_item(path):
    b = path.encode("latin1")
    return b"\x01\x00\x21\x00\x01\x05\x00" + bytes([len(b)]) + b


def _offtab(items):
    offs, o = [], 0
    for it in items: offs.append(o); o += len(it)
    assert all(x < 256 for x in offs), "sound stream offsets > 255 not supported"
    if not items: return b"\x00"                        # empty list: just the count (vanilla "01 01 00 00")
    return bytes([len(items)]) + b"\x00\x00" + b"".join(bytes([i, offs[i]]) for i in range(1, len(items)))


def _snd_entry(e, idx=1):
    """idx = the entry's sound ID (2026-10-13): TSFXLibrary.Play(lib, n) FINDS the sequence whose ID field (+0xC) == n
    (SoundP 0x5540608C) - it does not index by position.  The dword after `01 04` in a sub-list entry is that ID (vanilla
    second entries carry 1); a third cue must carry 2 or Play never finds it."""
    if isinstance(e, str):
        b = e.encode("latin1")
        return b"\x02\x00\x21\x00\x01" + b"\x01\x00\x01\x00\x00\x01\x00\x21\x00\x01" + b"\x05\x00" + bytes([len(b)]) + b
    items = [_snd_item(s) for s in e]
    return b"\x02\x00\x21\x00\x02" + b"\x05\x00\x01\x04" + struct.pack("<I", idx) + _offtab(items) + b"".join(items)


def snd_build(entries):
    ents = [_snd_entry(e, k) for k, e in enumerate(entries)]
    return b"\x01\x01\x00" + _offtab(ents) + b"".join(ents)


def snd_parse(v):
    """Best-effort decode (for display / self-test): returns the entries shape or raises."""
    assert v[:3] == b"\x01\x01\x00"
    N = v[3]; o = 4 + (2 + 2 * (N - 1) if N else 0); out = []
    for _ in range(N):
        assert v[o:o + 4] == b"\x02\x00\x21\x00"; sub = v[o + 4]; o += 5
        if sub == 1:
            assert v[o:o + 10] == b"\x01\x00\x01\x00\x00\x01\x00\x21\x00\x01"; o += 10
            assert v[o:o + 2] == b"\x05\x00"; ln = v[o + 2]; out.append(v[o + 3:o + 3 + ln].decode("latin1")); o += 3 + ln
        else:
            assert v[o:o + 4] == b"\x05\x00\x01\x04"; o += 8          # 4-byte ID follows (position)
            n = v[o]; o += 3 + 2 * (n - 1); lst = []
            for _k in range(n):
                assert v[o:o + 7] == b"\x01\x00\x21\x00\x01\x05\x00"; ln = v[o + 7]; lst.append(v[o + 8:o + 8 + ln].decode("latin1")); o += 8 + ln
            out.append(lst)
    assert o == len(v)
    return out


# ---------------------------------------------------------------- pfs record access (standalone, for the self-test)
def pfs_tab(d, p):
    b = d[p]; p += 1; nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from("<I", d, p)[0]; p += 4
    pairs = []
    for _ in range(nb): pairs.append((d[p], d[p + 1])); p += 2
    for _ in range(nd): pairs.append(struct.unpack_from("<II", d, p)); p += 8
    return pairs, p


def pfs_fields(d, key_off, next_off):
    tp, tend = pfs_tab(d, key_off)
    ent = sorted([(t, tend + o) for t, o in tp], key=lambda x: x[1])
    out = {}
    for i, (t, vo) in enumerate(ent):
        nxt = ent[i + 1][1] if i + 1 < len(ent) else next_off
        out[t] = d[vo:nxt]
    return out


def selftest(pfs_path):
    d = open(pfs_path, "rb").read()
    pairs, kb = pfs_tab(d, 7)
    idx = {t: kb + o for t, o in pairs}
    ok = 0; bad = []
    for key in sorted(idx):
        nxt = min([v for v in idx.values() if v > idx[key]] + [len(d) - 4])
        f = pfs_fields(d, idx[key], nxt)
        if 0xC in f:
            slots = seq_parse(f[0xC]); assert seq_build(slots) == f[0xC], "gfx round-trip failed for key %d" % key
        if 0xB in f:
            try:
                ents = snd_parse(f[0xB]); assert snd_build(ents) == f[0xB]
            except Exception as e:
                print("  snd: key %d not round-trippable (%s): %s" % (key, type(e).__name__, f[0xB].hex())); bad.append(key); continue
        ok += 1
    print("spellgfx self-test: %d records round-trip OK, %d sound blobs in an unsupported shape %s" % (ok, len(bad), bad))


if __name__ == "__main__":
    selftest(sys.argv[1] if len(sys.argv) > 1 else
             game_file("Release", "Spells.pfs"))
