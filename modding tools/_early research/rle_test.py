import struct, sys, glob, os, collections, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ilbcodec import read, T8, T_CLIP

def decode_indices(d, base, r):
    """Return (grid, back) where grid is a list of rows of raw pixel values over the clip box."""
    t = r['type']; cw, ch = r['cw'], r['ch']
    p = base + r['off'] if r['info'] != 1 else None
    data = r['inline'] if r['info'] == 1 else d[p:p + r['size']]
    back = r['transp']
    rows = []; q = 0
    if t == 2:
        back &= 0xFF
        for y in range(ch):
            ln = struct.unpack_from('<I', data, q)[0]; q += 4; n = ln - 4
            row = []
            while n > 0:
                b = data[q]; q += 1; n -= 1
                if b == back:
                    cnt = data[q]; q += 1; n -= 1; row += [back] * cnt
                else: row.append(b)
            rows.append(row)
    elif t in (17, 18):
        back &= 0xFFFF
        for y in range(ch):
            ln = struct.unpack_from('<I', data, q)[0]; q += 4
            n = (ln - 4) // 2; pad = (n % 2) > 0; row = []
            while n > 0:
                v = struct.unpack_from('<H', data, q)[0]; q += 2; n -= 1
                if v == back:
                    cnt = struct.unpack_from('<H', data, q)[0]; q += 2; n -= 1
                    row += [back] * (cnt // 2)
                else: row.append(v)
            rows.append(row)
            if pad: q += 2
    else:
        return None, None
    return rows, back

def encode(rows, back, t):
    out = bytearray()
    for row in rows:
        line = bytearray(); run = 0
        for v in row:
            if v == back: run += 1
            else:
                if run:
                    if t == 2: line += bytes((back, run))
                    else: line += struct.pack('<HH', back, 2 * run)
                    run = 0
                if t == 2: line.append(v)
                else: line += struct.pack('<H', v)
        if run:
            if t == 2: line += bytes((back, run))
            else: line += struct.pack('<HH', back, 2 * run)
        if t == 2:
            out += struct.pack('<I', len(line) + 4) + line
        else:
            nvals = len(line) // 2
            out += struct.pack('<I', 2 * nvals + 4) + line
            if nvals % 2: out += struct.pack('<H', back)
    return bytes(out)

root = sys.argv[1]
files = []
for sub in ("Images", "Int"):
    for pat in ("*.ilb", "*.ILB"):
        files += glob.glob(os.path.join(root, sub, "**", pat), recursive=True)
files = sorted(set(os.path.normpath(f) for f in files))
random.seed(7); random.shuffle(files); files = files[:120]

stat = collections.Counter(); maxrun = collections.Counter(); bad = []
for f in files:
    try:
        d = open(f, 'rb').read(); lib = read(d)
    except Exception: continue
    base = lib['imgDirectory']
    if base is None: continue
    for img in lib['images']:
        for r in img['parts']:
            if r['type'] not in (2, 17, 18): continue
            try:
                rows, back = decode_indices(d, base, r)
                if rows is None: continue
                orig = r['inline'] if r['info'] == 1 else d[base + r['off']: base + r['off'] + r['size']]
                enc = encode(rows, back, r['type'])
                # longest background run actually present
                for row in rows:
                    run = 0; m = 0
                    for v in row:
                        if v == back: run += 1; m = max(m, run)
                        else: run = 0
                    maxrun[r['type']] = max(maxrun[r['type']], m)
                if enc == orig: stat['exact_%d' % r['type']] += 1
                else:
                    stat['diff_%d' % r['type']] += 1
                    if len(bad) < 6:
                        n = min(len(enc), len(orig))
                        at = next((i for i in range(n) if enc[i] != orig[i]), n)
                        bad.append((os.path.basename(f), r['id'] if 'id' in r else '?', r['type'],
                                    len(orig), len(enc), at, orig[max(0,at-6):at+10].hex(), enc[max(0,at-6):at+10].hex()))
            except Exception as e:
                stat['err'] += 1
                if len(bad) < 6: bad.append((os.path.basename(f), '?', r['type'], 0, 0, -1, str(e)[:50], ''))
print("re-encode results over %d files:" % len(files))
for k in sorted(stat): print("   %-10s %d" % (k, stat[k]))
print("longest background run seen per type:", dict(maxrun))
for b in bad:
    print("   MISMATCH %s type=%s origlen=%d enclen=%d @%d\n      orig=%s\n      enc =%s" % (b[0], b[2], b[3], b[4], b[5], b[6], b[7]))
