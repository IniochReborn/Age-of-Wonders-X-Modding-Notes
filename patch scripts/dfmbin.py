r"""
Binary Delphi DFM (TPF0) model with raw-preserving round trip (2026-10-22, for patch_exe_realm_heroes_cols_v1).

parse(data) -> Comp tree; Comp.props = [[name, raw_value_bytes]] (value bytes INCLUDE the type byte), so untouched
properties re-serialize byte-identically.  Helpers encode new int / string / ident values.
"""
import struct


class Comp:
    def __init__(self):
        self.prefix = b""          # optional filer flags byte (+ position value)
        self.cls = ""
        self.name = ""
        self.props = []            # [name, raw value bytes]
        self.children = []

    def get(self, name):
        for k, v in self.props:
            if k == name:
                return v
        return None

    def set(self, name, raw):
        for p in self.props:
            if p[0] == name:
                p[1] = raw
                return
        raise KeyError(name)

    def find(self, name):
        if self.name == name:
            return self
        for c in self.children:
            r = c.find(name)
            if r:
                return r
        return None

    def clone(self):
        c = Comp()
        c.prefix, c.cls, c.name = self.prefix, self.cls, self.name
        c.props = [[k, v] for k, v in self.props]
        c.children = [x.clone() for x in self.children]
        return c


def _ss(b, p):
    n = b[p]
    return b[p + 1:p + 1 + n].decode("latin1"), p + 1 + n


def _skip_value(b, p):
    t = b[p]; p += 1
    if t == 0: return p
    if t == 1:                                      # list
        while b[p] != 0:
            p = _skip_value(b, p)
        return p + 1
    if t == 2: return p + 1
    if t == 3: return p + 2
    if t == 4: return p + 4
    if t == 5: return p + 10
    if t in (6, 7): return p + 1 + b[p]
    if t in (8, 9, 13): return p
    if t == 10: return p + 4 + struct.unpack_from("<I", b, p)[0]
    if t == 11:
        while b[p] != 0:
            p += 1 + b[p]
        return p + 1
    if t == 12: return p + 4 + struct.unpack_from("<I", b, p)[0]
    if t == 14:                                     # collection
        while b[p] != 0:
            while b[p] != 0:
                _, p = _ss(b, p)
                p = _skip_value(b, p)
            p += 1
        return p + 1
    if t == 15: return p + 4 + 2 * struct.unpack_from("<I", b, p)[0]
    raise ValueError("DFM value type %d at %#x" % (t, p - 1))


def _comp(b, p):
    c = Comp()
    f = b[p]
    if f & 0xF0 == 0xF0:
        q = p + 1
        if f & 2:
            q = _skip_value(b, q)
        c.prefix = bytes(b[p:q]); p = q
    c.cls, p = _ss(b, p)
    c.name, p = _ss(b, p)
    while b[p] != 0:
        k, p = _ss(b, p)
        q = _skip_value(b, p)
        c.props.append([k, bytes(b[p:q])]); p = q
    p += 1
    while b[p] != 0:
        ch, p = _comp(b, p)
        c.children.append(ch)
    return c, p + 1


def parse(data):
    assert data[:4] == b"TPF0", "not a binary DFM"
    root, p = _comp(data, 4)
    assert p == len(data), "trailing bytes in DFM (%d of %d)" % (p, len(data))
    return root


def _wss(s):
    s = s.encode("latin1")
    return bytes([len(s)]) + s


def _wcomp(c):
    out = bytearray(c.prefix + _wss(c.cls) + _wss(c.name))
    for k, v in c.props:
        out += _wss(k) + v
    out.append(0)
    for ch in c.children:
        out += _wcomp(ch)
    out.append(0)
    return bytes(out)


def serialize(root):
    return b"TPF0" + _wcomp(root)


def v_int(n):
    if -128 <= n <= 127: return b"\x02" + struct.pack("<b", n)
    if -32768 <= n <= 32767: return b"\x03" + struct.pack("<h", n)
    return b"\x04" + struct.pack("<i", n)


def v_str(s):
    s = s.encode("latin1"); assert len(s) < 256
    return b"\x06" + bytes([len(s)]) + s


def v_ident(s):
    s = s.encode("latin1"); assert len(s) < 256
    return b"\x07" + bytes([len(s)]) + s


def v_strlist(items):
    return b"\x01" + b"".join(v_str(s) for s in items) + b"\x00"


def int_of(raw):
    t = raw[0]
    if t == 2: return struct.unpack_from("<b", raw, 1)[0]
    if t == 3: return struct.unpack_from("<h", raw, 1)[0]
    if t == 4: return struct.unpack_from("<i", raw, 1)[0]
    raise ValueError("not an int value (type %d)" % t)
