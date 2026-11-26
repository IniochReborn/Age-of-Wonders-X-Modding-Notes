import struct, sys

def read_dir(b, p, hdr):
    """Returns (entries {id:(off,size)}, data_base, p_after_dir_is_data_base)."""
    if hdr is not None:
        got = b[p:p+len(hdr)]
        if got != hdr: raise ValueError("bad header %s at %d" % (got.hex(), p))
        p += len(hdr)
    cnt = b[p]; p += 1
    nb = cnt & 0x7F
    nd = 0
    if cnt & 0x80:
        nd = struct.unpack_from("<I", b, p)[0]; p += 4
    ids = []
    for _ in range(nb):
        ids.append((b[p], b[p+1])); p += 2
    for _ in range(nd):
        i, o = struct.unpack_from("<II", b, p); p += 8
        ids.append((i, o))
    base = p
    # compute sizes: next offset - this offset (entries stored in file order = ascending offset)
    ent = {}
    srt = sorted(range(len(ids)), key=lambda k: ids[k][1])
    for j, k in enumerate(srt):
        i, o = ids[k]
        if j+1 < len(srt):
            size = ids[srt[j+1]][1] - o
        else:
            size = len(b) - (base + o)
        ent[i] = (base + o, size)
    return ent, base

def sstr(b, o):
    return b[o+1:o+1+b[o]].decode('latin-1')

def parse_chapter(b, off, size):
    blob = b[off:off+size]
    ent, base = read_dir(blob, 0, b"\x01\x01\x00")
    pages = []
    for pid in sorted(ent):
        po, psz = ent[pid]
        pb = blob[po:po+psz]
        pent, pbase = read_dir(pb, 0, b"\x02\x50\x22\x00")
        page = {}
        for fid, (fo, fsz) in pent.items():
            if fid == 0x0B: page['title'] = sstr(pb, fo)
            elif fid == 0x0A:
                ln = struct.unpack_from("<I", pb, fo)[0]
                page['text'] = pb[fo+4:fo+4+ln].decode('latin-1')
            elif fid == 0x0C: page['image'] = sstr(pb, fo)
            elif fid == 0x0D: page['picid'] = struct.unpack_from("<i", pb, fo)[0]
        if page.get('title') or page.get('text') or page.get('image'):
            pages.append((pid, page))
    return pages

def parse_record(b, off, size):
    blob = b[off:off+size]
    ent, base = read_dir(blob, 0, b"\x01\x50\x22\x00")
    rec = {"_kind": "Scenario" if 0x0C in ent else "CounterMeasure", "_fields": sorted(ent)}
    for fid, (fo, fsz) in sorted(ent.items()):
        if fid == 0x09: rec['ID'] = struct.unpack_from("<i", blob, fo)[0]
        elif fid == 0x0A: rec['title_A'] = sstr(blob, fo)
        elif fid == 0x0B: rec['str_B'] = sstr(blob, fo)
        elif fid == 0x0C: rec['str_C'] = sstr(blob, fo)
        elif fid == 0x0D: rec['str_D'] = sstr(blob, fo)
        elif fid == 0x0E: rec['str_E'] = sstr(blob, fo)
        elif fid == 0x10: rec['X'] = struct.unpack_from("<i", blob, fo)[0]
        elif fid == 0x11: rec['Y'] = struct.unpack_from("<i", blob, fo)[0]
        elif fid == 0x13: rec['prologue'] = parse_chapter(blob, fo, fsz)
        elif fid == 0x14: rec['epilogue'] = parse_chapter(blob, fo, fsz)
        elif fid == 0x15:
            n = fsz // 4
            rec['f15'] = list(struct.unpack_from("<%di" % n, blob, fo))
        elif fid == 0x16: rec['b16'] = blob[fo]
        else: rec.setdefault('other', {})[hex(fid)] = blob[fo:fo+min(fsz,32)].hex()
    return rec

def parse_cam(fn, verbose=True, maxrec=None):
    b = open(fn, "rb").read()
    ent, base = read_dir(b, 0, b"\x01\x00\x00\x00\x50\x22\x00")
    print("== %s (%d bytes), top fields: %s" % (fn, len(b), {hex(k): (hex(v[0]), v[1]) for k, v in sorted(ent.items())}))
    # field 7
    if 7 in ent:
        fo, fsz = ent[7]
        blob = b[fo:fo+fsz]
        e7, b7 = read_dir(blob, 0, None)
        print("  field 07 (campaign settings), size %d:" % fsz)
        for fid, (o, s) in sorted(e7.items()):
            print("    %02x @+%02x size %d = %s" % (fid, o-b7, s, blob[o:o+s].hex()))
    if 0x0C in ent: print("  field 0c name: %r" % sstr(b, ent[0x0C][0]))
    for fid in (0x0E, 0x10, 0x11, 0x13, 0x1E):
        if fid in ent:
            o, s = ent[fid]
            print("  field %02x: size %d = %s" % (fid, s, b[o:o+s].hex()))
    # scenario list
    fo, fsz = ent[0x0A]
    blob = b[fo:fo+fsz]
    e, base2 = read_dir(blob, 0, b"\x01\x01\x00")
    print("  field 0a scenario list: %d records; tail after last record..." % len(e))
    recs = []
    for rid in sorted(e):
        ro, rsz = e[rid]
        try:
            rec = parse_record(blob, ro, rsz)
        except Exception as ex:
            print("   rec %d PARSE FAIL at %d: %s ; first bytes %s" % (rid, ro, ex, blob[ro:ro+16].hex()))
            continue
        recs.append((rid, rec))
    if verbose:
        for rid, rec in recs[:maxrec] if maxrec else recs:
            print("  --- record %d: %s fields=%s" % (rid, rec['_kind'], [hex(f) for f in rec['_fields']]))
            for k in ('ID','title_A','str_B','str_C','str_D','str_E','X','Y','f15','b16','other'):
                if k in rec: print("      %s = %r" % (k, rec[k]))
            for ch in ('prologue','epilogue'):
                if rec.get(ch):
                    print("      %s: %d non-empty pages" % (ch, len(rec[ch])))
                    for pid, pg in rec[ch]:
                        t = pg.get('text','')
                        print("        page %d: title=%r image=%r picid=%r text[%d]=%r" % (pid, pg.get('title'), pg.get('image'), pg.get('picid'), len(t), t[:120]))
    return b, ent, recs

if __name__ == "__main__":
    import io, contextlib
    fn = sys.argv[1]
    maxrec = int(sys.argv[2]) if len(sys.argv) > 2 else None
    parse_cam(fn, True, maxrec)
