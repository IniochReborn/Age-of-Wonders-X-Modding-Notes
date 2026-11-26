"""camcodec.py - lossless AoW1 .CAM campaign reader/writer (TAoWDir tagged-directory format)."""
import struct

MAGIC_ROOT     = b"\x01\x00\x00\x00\x50\x22\x00"   # 7
MAGIC_LIST     = b"\x01\x01\x00"                   # 3  (scenario list, book chapter)
MAGIC_RECORD   = b"\x01\x50\x22\x00"               # 4  (scenario / countermeasure)
MAGIC_PAGE     = b"\x02\x50\x22\x00"               # 4  (book page)

class Node:
    __slots__ = ("magic", "entries")               # entries: list of [id, form, payload]
    def __init__(self, magic, entries): self.magic, self.entries = magic, entries
    def get(self, fid):
        for i, f, p in self.entries:
            if i == fid: return p
        return None
    def has(self, fid): return self.get(fid) is not None

def parse_node(buf, magic_len):
    magic = buf[:magic_len]; o = magic_len
    c = buf[o]; o += 1
    nshort = c & 0x7F; nlong = 0
    if c & 0x80:
        nlong = struct.unpack_from("<I", buf, o)[0]; o += 4
    tbl = []
    for _ in range(nshort):
        tbl.append((buf[o], buf[o+1], 'S')); o += 2
    for _ in range(nlong):
        fid, off = struct.unpack_from("<ii", buf, o); o += 8
        tbl.append((fid, off, 'L'))
    base = o
    entries = []
    for k, (fid, off, form) in enumerate(tbl):
        end = tbl[k+1][1] if k + 1 < len(tbl) else len(buf) - base
        entries.append([fid, form, buf[base+off:base+end]])
    return Node(magic, entries)

def build_node(node):
    payload = b"".join(e[2] for e in node.entries)
    offs = []; acc = 0
    for e in node.entries: offs.append(acc); acc += len(e[2])
    shorts = [(e[0], o) for e, o in zip(node.entries, offs) if e[1] == 'S']
    longs  = [(e[0], o) for e, o in zip(node.entries, offs) if e[1] == 'L']
    out = bytearray(node.magic)
    c = len(shorts) | (0x80 if longs else 0)
    out.append(c)
    if longs: out += struct.pack("<I", len(longs))
    for fid, o in shorts: out += bytes((fid, o))
    for fid, o in longs:  out += struct.pack("<ii", fid, o)
    return bytes(out) + payload

def rstr(p):   return p[1:1+p[0]].decode("latin1") if p else ""          # ShortString
def rlstr(p):  return p[4:4+struct.unpack_from("<i",p,0)[0]].decode("latin1") if p else ""
def rint(p):   return struct.unpack_from("<i", p, 0)[0] if p else None

def read_campaign(path):
    data = open(path, "rb").read()
    root = parse_node(data, len(MAGIC_ROOT))
    cam = {"root": root, "raw_len": len(data),
           "name": rstr(root.get(0x0C)),
           "side": "Cult of Storms" if root.has(0x1E) else "Keepers",
           "records": []}
    lst = root.get(0x0A)
    if lst is None: return cam
    listnode = parse_node(lst, len(MAGIC_LIST))
    for fid, form, payload in listnode.entries:
        rec = parse_node(payload, len(MAGIC_RECORD))
        is_scen = rec.has(0x0C)
        link = rec.get(0x15); links = []
        if link:
            vals = list(struct.unpack_from("<%di" % (len(link)//4), link, 0))
            links = vals
        r = {"index": fid, "kind": "scenario" if is_scen else "counter",
             "id": rint(rec.get(0x09)), "short": rstr(rec.get(0x0A)),
             "file": rstr(rec.get(0x0B)), "music": rstr(rec.get(0x0C)),
             "full": rstr(rec.get(0x0D)), "cmdesc": rstr(rec.get(0x0E)),
             "x": rint(rec.get(0x10)), "y": rint(rec.get(0x11)),
             "link": links, "unk16": rec.get(0x16)[0] if rec.get(0x16) else None,
             "chapters": {}}
        for cf, cname in ((0x13, "prologue"), (0x14, "epilogue")):
            cp = rec.get(cf)
            if cp is None: continue
            ch = parse_node(cp, len(MAGIC_LIST)); pages = []
            for pf, pform, ppay in ch.entries:
                pg = parse_node(ppay, len(MAGIC_PAGE))
                pages.append({"title": rstr(pg.get(0x0B)), "text": rlstr(pg.get(0x0A)),
                              "image": rstr(pg.get(0x0C)), "picnr": rint(pg.get(0x0D))})
            r["chapters"][cname] = pages
        cam["records"].append(r)
    return cam

def rewrite(path):
    """Reparse->rebuild every nested node and return the reconstructed bytes."""
    data = open(path, "rb").read()
    root = parse_node(data, len(MAGIC_ROOT))
    for e in root.entries:
        if e[0] == 0x0A:
            lst = parse_node(e[2], len(MAGIC_LIST))
            for le in lst.entries:
                rec = parse_node(le[2], len(MAGIC_RECORD))
                for re_ in rec.entries:
                    if re_[0] in (0x13, 0x14):
                        ch = parse_node(re_[2], len(MAGIC_LIST))
                        for pe in ch.entries:
                            pg = parse_node(pe[2], len(MAGIC_PAGE))
                            pe[2] = build_node(pg)
                        re_[2] = build_node(ch)
                le[2] = build_node(rec)
            e[2] = build_node(lst)
        elif e[0] == 0x07:
            e[2] = build_node(parse_node(e[2], 0))
    return build_node(root)

if __name__ == "__main__":
    import sys, glob, os, hashlib
    root_dir = sys.argv[1]
    files = glob.glob(os.path.join(root_dir, "**", "*.cam"), recursive=True) + \
            glob.glob(os.path.join(root_dir, "**", "*.CAM"), recursive=True)
    seen = {}
    for f in sorted(set(os.path.normpath(x) for x in files)):
        h = hashlib.md5(open(f,'rb').read()).hexdigest()
        seen.setdefault(h, f)
    print("unique .cam files: %d" % len(seen))
    ok = same = 0; errs = []; formrule = True
    for h, f in sorted(seen.items(), key=lambda kv: kv[1]):
        try:
            cam = read_campaign(f); out = rewrite(f); orig = open(f,'rb').read()
            ok += 1
            ident = (out == orig); same += ident
            scen = [r for r in cam["records"] if r["kind"]=="scenario"]
            cm   = [r for r in cam["records"] if r["kind"]=="counter"]
            pages = sum(1 for r in cam["records"] for c in r["chapters"].values()
                        for p in c if p["title"] or p["text"] or p["image"])
            print("%-46s %-15s %-15s scen=%-4d cm=%-4d pages=%-4d  %s" %
                  (os.path.basename(f)[:45], cam["name"][:14], cam["side"],
                   len(scen), len(cm), pages, "IDENTICAL" if ident else "*** DIFFERS ***"))
        except Exception as e:
            errs.append((os.path.basename(f), "%s: %s" % (type(e).__name__, e)))
    print("\nparsed %d/%d   byte-identical rebuild: %d" % (ok, len(seen), same))
    for e in errs: print("   ERROR %-30s %s" % e)
