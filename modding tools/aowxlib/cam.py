"""
aowxlib.cam - Age of Wonders 1 campaign (.CAM) codec.

The format is a hand-rolled tagged-directory container (the "TAoWDir" scheme):
every structural node is a magic prefix, a table of (FieldID, RelOffset) entries
and a payload area. There is no per-entry size field - a field's length is the
next entry's offset minus its own, and the last entry runs to the end of the node.

Clean-room implementation; verified by rebuilding all 12 campaign files on this
machine byte-for-byte identically.
"""
from __future__ import annotations
import struct

MAGIC_ROOT = b"\x01\x00\x00\x00\x50\x22\x00"     # campaign root
MAGIC_LIST = b"\x01\x01\x00"                     # record list, book chapter
MAGIC_RECORD = b"\x01\x50\x22\x00"               # scenario / counter-action
MAGIC_PAGE = b"\x02\x50\x22\x00"                 # book page

# root fields
F_SETTINGS, F_LIST, F_NAME = 0x07, 0x0A, 0x0C
F_PAD8, F_PAD5, F_TWO, F_ONE, F_STORM = 0x0E, 0x10, 0x11, 0x13, 0x1E
# record fields
F_ID, F_SHORT, F_CSM, F_MUSIC, F_FULL, F_CADESC = 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E
F_X, F_Y, F_PROLOGUE, F_EPILOGUE, F_LINK, F_UNK16 = 0x10, 0x11, 0x13, 0x14, 0x15, 0x16
# page fields
P_TEXT, P_TITLE, P_IMAGE, P_PICNR = 0x0A, 0x0B, 0x0C, 0x0D

PAGES_PER_CHAPTER = 10
MAX_NEXT = 3


# ---------------------------------------------------------------------------
# container primitive
# ---------------------------------------------------------------------------
class Node:
    __slots__ = ("magic", "entries")

    def __init__(self, magic=b"", entries=None):
        self.magic = magic
        self.entries = entries if entries is not None else []   # [fid, payload]

    def get(self, fid, default=None):
        for f, p in self.entries:
            if f == fid:
                return p
        return default

    def has(self, fid):
        return any(f == fid for f, _ in self.entries)

    def set(self, fid, payload):
        for e in self.entries:
            if e[0] == fid:
                e[1] = payload
                return
        # keep ascending FieldID order, as the original writer emits
        i = 0
        while i < len(self.entries) and self.entries[i][0] < fid:
            i += 1
        self.entries.insert(i, [fid, payload])

    def remove(self, fid):
        self.entries = [e for e in self.entries if e[0] != fid]


def parse_node(buf, magic_len):
    magic = buf[:magic_len]
    o = magic_len
    c = buf[o]
    o += 1
    nshort = c & 0x7F
    nlong = 0
    if c & 0x80:
        nlong = struct.unpack_from("<I", buf, o)[0]
        o += 4
    tbl = []
    for _ in range(nshort):
        tbl.append((buf[o], buf[o + 1]))
        o += 2
    for _ in range(nlong):
        fid, off = struct.unpack_from("<ii", buf, o)
        o += 8
        tbl.append((fid, off))
    base = o
    entries = []
    for k, (fid, off) in enumerate(tbl):
        end = tbl[k + 1][1] if k + 1 < len(tbl) else len(buf) - base
        entries.append([fid, buf[base + off:base + end]])
    return Node(magic, entries)


def build_node(node):
    payload = b"".join(e[1] for e in node.entries)
    offs = []
    acc = 0
    for e in node.entries:
        offs.append(acc)
        acc += len(e[1])
    # the original writer uses the 1-byte form whenever the offset fits
    shorts = [(e[0], o) for e, o in zip(node.entries, offs) if o < 0x100 and 0 <= e[0] < 0x100]
    longs = [(e[0], o) for e, o in zip(node.entries, offs)
             if not (o < 0x100 and 0 <= e[0] < 0x100)]
    out = bytearray(node.magic)
    out.append(len(shorts) | (0x80 if longs else 0))
    if longs:
        out += struct.pack("<I", len(longs))
    for fid, o in shorts:
        out += bytes((fid, o))
    for fid, o in longs:
        out += struct.pack("<ii", fid, o)
    return bytes(out) + payload


# ---- scalar codecs ---------------------------------------------------------
def r_int(p, default=0):
    return struct.unpack_from("<i", p, 0)[0] if p and len(p) >= 4 else default


def w_int(v):
    return struct.pack("<i", int(v))


def r_str(p):
    return p[1:1 + p[0]].decode("latin-1") if p else ""


def w_str(s):
    b = s.encode("latin-1", "replace")[:255]
    return bytes((len(b),)) + b


def r_lstr(p):
    if not p or len(p) < 4:
        return ""
    n = struct.unpack_from("<i", p, 0)[0]
    return p[4:4 + n].decode("latin-1")


def w_lstr(s):
    b = s.encode("latin-1", "replace")
    return struct.pack("<i", len(b)) + b


# ---------------------------------------------------------------------------
# typed model
# ---------------------------------------------------------------------------
class Page:
    def __init__(self, node=None):
        self.node = node if node is not None else Node(MAGIC_PAGE, [])

    @property
    def text(self):
        return r_lstr(self.node.get(P_TEXT))

    @text.setter
    def text(self, v):
        self.node.set(P_TEXT, w_lstr(v)) if v else self.node.remove(P_TEXT)

    @property
    def title(self):
        return r_str(self.node.get(P_TITLE))

    @title.setter
    def title(self, v):
        self.node.set(P_TITLE, w_str(v)) if v else self.node.remove(P_TITLE)

    @property
    def image(self):
        return r_str(self.node.get(P_IMAGE))

    @image.setter
    def image(self, v):
        self.node.set(P_IMAGE, w_str(v)) if v else self.node.remove(P_IMAGE)

    @property
    def picnr(self):
        p = self.node.get(P_PICNR)
        return r_int(p) if p else None

    @picnr.setter
    def picnr(self, v):
        self.node.set(P_PICNR, w_int(v)) if v is not None else self.node.remove(P_PICNR)

    @property
    def empty(self):
        return not (self.text or self.title or self.image)

    def build(self):
        return build_node(self.node)


class Chapter:
    def __init__(self, payload=None):
        if payload:
            n = parse_node(payload, len(MAGIC_LIST))
            self.pages = [Page(parse_node(p, len(MAGIC_PAGE))) for _, p in n.entries]
        else:
            self.pages = [Page() for _ in range(PAGES_PER_CHAPTER)]
        while len(self.pages) < PAGES_PER_CHAPTER:
            self.pages.append(Page())

    def build(self):
        n = Node(MAGIC_LIST, [[i, p.build()] for i, p in enumerate(self.pages)])
        return build_node(n)


class Record:
    """A campaign scenario or counter-action. Type is decided by field 0x0C."""

    def __init__(self, node=None, index=0):
        self.node = node if node is not None else Node(MAGIC_RECORD, [])
        self.index = index
        self.prologue = Chapter(self.node.get(F_PROLOGUE))
        self.epilogue = Chapter(self.node.get(F_EPILOGUE))

    # -- kind ----
    @property
    def is_scenario(self):
        return self.node.has(F_MUSIC)

    @property
    def kind(self):
        return "scenario" if self.is_scenario else "counter"

    # -- simple fields ----
    def _s(self, fid):
        return r_str(self.node.get(fid))

    def _sets(self, fid, v, keep_empty=False):
        if v or keep_empty:
            self.node.set(fid, w_str(v))
        else:
            self.node.remove(fid)

    id = property(lambda s: r_int(s.node.get(F_ID)),
                  lambda s, v: s.node.set(F_ID, w_int(v)))
    short_title = property(lambda s: s._s(F_SHORT),
                           lambda s, v: s._sets(F_SHORT, v, True))
    full_title = property(lambda s: s._s(F_FULL),
                          lambda s, v: s._sets(F_FULL, v))
    scenario_file = property(lambda s: s._s(F_CSM),
                             lambda s, v: s._sets(F_CSM, v))
    music_file = property(lambda s: s._s(F_MUSIC),
                          lambda s, v: s._sets(F_MUSIC, v or "Title.it", True))
    ca_description = property(lambda s: s._s(F_CADESC),
                              lambda s, v: s._sets(F_CADESC, v))
    x = property(lambda s: r_int(s.node.get(F_X)),
                 lambda s, v: s.node.set(F_X, w_int(v)))
    y = property(lambda s: r_int(s.node.get(F_Y)),
                 lambda s, v: s.node.set(F_Y, w_int(v)))

    @property
    def unknown16(self):
        p = self.node.get(F_UNK16)
        return p[0] if p else 0

    @unknown16.setter
    def unknown16(self, v):
        self.node.set(F_UNK16, bytes((int(v) & 0xFF,)))

    # -- link block (six int32) ----
    def _link(self):
        p = self.node.get(F_LINK)
        if not p:
            return []
        return list(struct.unpack_from("<%di" % (len(p) // 4), p, 0))

    @property
    def next_missions(self):
        L = self._link()
        return [v for v in L[2:2 + MAX_NEXT] if v not in (-1, None)] if len(L) >= 5 else []

    @next_missions.setter
    def next_missions(self, ids):
        ids = [int(i) for i in ids][:MAX_NEXT]
        ca = self.counter_action
        vals = [0 if ids else -1, 4] + (ids + [-1] * MAX_NEXT)[:MAX_NEXT] + [ca if ca is not None else -1]
        self.node.set(F_LINK, struct.pack("<%di" % len(vals), *vals))

    @property
    def counter_action(self):
        L = self._link()
        return L[5] if len(L) >= 6 and L[5] != -1 else None

    @counter_action.setter
    def counter_action(self, cid):
        L = self._link()
        if len(L) < 6:
            L = [0, 4, -1, -1, -1, -1]
        L[5] = -1 if cid is None else int(cid)
        self.node.set(F_LINK, struct.pack("<%di" % len(L), *L))

    def build(self):
        if self.node.has(F_PROLOGUE) or any(not p.empty for p in self.prologue.pages):
            self.node.set(F_PROLOGUE, self.prologue.build())
        if self.node.has(F_EPILOGUE) or any(not p.empty for p in self.epilogue.pages):
            self.node.set(F_EPILOGUE, self.epilogue.build())
        return build_node(self.node)


class Campaign:
    def __init__(self):
        self.root = Node(MAGIC_ROOT, [])
        self.records = []
        self.path = None

    # -- header fields ----
    @property
    def name(self):
        return r_str(self.root.get(F_NAME))

    @name.setter
    def name(self, v):
        self.root.set(F_NAME, w_str(v))

    @property
    def replaces_storm(self):
        """Field 0x1E present => this file replaces Cult of Storms, else Keepers."""
        return self.root.has(F_STORM)

    @replaces_storm.setter
    def replaces_storm(self, v):
        if v:
            self.root.set(F_STORM, w_int(1))
        else:
            self.root.remove(F_STORM)

    @property
    def scenarios(self):
        return [r for r in self.records if r.is_scenario]

    @property
    def counter_actions(self):
        return [r for r in self.records if not r.is_scenario]

    def by_id(self, rid):
        for r in self.records:
            if r.id == rid:
                return r
        return None

    @property
    def start_scenario(self):
        """The game implicitly starts at list index 0 - there is no field for it."""
        return self.records[0] if self.records else None

    def move_to_start(self, rec):
        self.records.remove(rec)
        self.records.insert(0, rec)

    def new_record(self, scenario=True, rid=None, x=320, y=240, title="New"):
        r = Record(Node(MAGIC_RECORD, []))
        used = {rr.id for rr in self.records}
        if rid is None:
            rid = 1
            while rid in used:
                rid += 1
        r.id = rid
        r.short_title = title
        r.x, r.y = x, y
        if scenario:
            r.music_file = "Title.it"
            r.scenario_file = ""
        r.unknown16 = 0
        r.next_missions = []
        self.records.append(r)
        return r

    def delete_record(self, rec):
        """Remove a record and scrub every reference to it."""
        rid = rec.id
        self.records.remove(rec)
        for r in self.records:
            if r.counter_action == rid:
                r.counter_action = None
            nm = r.next_missions
            if rid in nm:
                r.next_missions = [i for i in nm if i != rid]

    def build(self):
        # scenarios first, then counter-actions, indices renumbered
        ordered = self.scenarios + self.counter_actions
        lst = Node(MAGIC_LIST, [[i, r.build()] for i, r in enumerate(ordered)])
        self.root.set(F_LIST, build_node(lst))
        if not self.root.has(F_SETTINGS):
            settings = Node(b"", [[0x14, w_int(0x101)], [0x15, w_int(0x101)],
                                  [0x16, w_int(0x101)], [0x17, bytes(8)], [0x1B, w_int(0)]])
            self.root.set(F_SETTINGS, build_node(settings))
        for fid, payload in ((F_PAD8, bytes(8)), (F_PAD5, bytes(5)),
                             (F_TWO, bytes((2,))), (F_ONE, bytes((1,)))):
            if not self.root.has(fid):
                self.root.set(fid, payload)
        if not self.root.has(F_NAME):
            self.root.set(F_NAME, w_str("New Campaign"))
        return build_node(self.root)

    def save(self, path):
        blob = self.build()
        with open(path, "wb") as fh:
            fh.write(blob)
        self.path = str(path)
        return len(blob)


def loads(data: bytes) -> Campaign:
    """Parse a campaign from raw bytes (used for undo snapshots)."""
    cam = Campaign()
    cam.root = parse_node(data, len(MAGIC_ROOT))
    lst = cam.root.get(F_LIST)
    if lst:
        listnode = parse_node(lst, len(MAGIC_LIST))
        for fid, payload in listnode.entries:
            cam.records.append(Record(parse_node(payload, len(MAGIC_RECORD)), fid))
    return cam


def read(path) -> Campaign:
    with open(path, "rb") as fh:
        data = fh.read()
    cam = loads(data)
    cam.path = str(path)
    return cam


def new_campaign(name="New Campaign", storm=False) -> Campaign:
    cam = Campaign()
    cam.name = name
    cam.replaces_storm = storm
    return cam


# ---------------------------------------------------------------------------
# graph helpers (the campaign is a cyclic DAG, not a tree)
# ---------------------------------------------------------------------------
def build_graph(cam: Campaign):
    ids = {r.id for r in cam.records}
    nxt = {}
    for r in cam.scenarios:
        nxt[r.id] = [i for i in r.next_missions if i in ids]
    indeg = {i: 0 for i in ids}
    for a, outs in nxt.items():
        for b in outs:
            indeg[b] = indeg.get(b, 0) + 1
    roots = [r for r in cam.scenarios if indeg.get(r.id, 0) == 0]
    return nxt, indeg, roots


def depths(cam: Campaign):
    """BFS depth of every scenario from the campaign start."""
    nxt, indeg, _roots = build_graph(cam)
    start = [cam.records[0].id] if cam.records else []
    for r in cam.scenarios:
        if indeg.get(r.id, 0) == 0 and r.id not in start:
            start.append(r.id)
    depth = {}
    queue = [(i, 0) for i in start]
    while queue:
        rid, d = queue.pop(0)
        if rid in depth:
            continue
        depth[rid] = d
        for k in nxt.get(rid, []):
            if k not in depth:
                queue.append((k, d + 1))
    for r in cam.scenarios:
        depth.setdefault(r.id, 0)
    return depth, nxt


def branch_from(cam: Campaign, rid, with_counter_actions=True):
    """Everything downstream of `rid`, following next-missions FORWARD only.

    Plain reachability is useless in a real campaign: branch endings loop back
    to an early scenario, which makes the graph strongly connected, so every
    node 'reaches' every other one. Only following edges to a strictly greater
    depth cuts those loop-backs and gives the branch a person means.
    """
    depth, nxt = depths(cam)
    out = set()
    stack = [rid]
    while stack:
        k = stack.pop()
        if k in out:
            continue
        out.add(k)
        for n in nxt.get(k, []):
            if depth.get(n, 0) > depth.get(k, 0):
                stack.append(n)
    if with_counter_actions:
        for k in list(out):
            r = cam.by_id(k)
            if r is not None and r.counter_action is not None:
                out.add(r.counter_action)
    return out


def branch_tree(cam: Campaign, max_nodes=4000):
    """Depth-first projection of the graph. Yields (record, depth, revisit)."""
    nxt, indeg, roots = build_graph(cam)
    start = []
    if cam.records:
        start.append(cam.records[0])
    for r in roots:
        if r not in start:
            start.append(r)
    seen = set()
    out = []

    def walk(rid, depth, path):
        if len(out) >= max_nodes:
            return
        rec = cam.by_id(rid)
        if rec is None:
            return
        revisit = rid in seen
        out.append((rec, depth, revisit))
        if revisit or rid in path:
            return
        seen.add(rid)
        for k in nxt.get(rid, []):
            walk(k, depth + 1, path | {rid})

    for r in start:
        walk(r.id, 0, frozenset())
    for r in cam.scenarios:                      # orphan branches
        if r.id not in seen:
            walk(r.id, 0, frozenset())
    return out
