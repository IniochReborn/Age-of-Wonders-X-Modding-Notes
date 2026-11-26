import struct, zlib, os, glob, sys
sys.path.insert(0, r'C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts\mapgen')
RACES = ['Humans','Azracs','Lizardmen','Frostlings','Elves','Halflings','Dwarves','High Men','Dark Elves','Orcs','Goblins','Undead']
def tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    f = {}
    for _ in range(b & 0x7F):
        f[dd[p]] = dd[p+1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from('<II', dd, p); f[t] = o; p += 8
    return f, p
def parse_fields(dd, tp, end):
    f, base = tbl(dd, tp); fo = sorted(f.items(), key=lambda kv: kv[1]); out = {}
    for j, (t, o) in enumerate(fo):
        out[t] = bytes(dd[base+o: base+fo[j+1][1] if j+1 < len(fo) else end])
    return out
def races(path):
    inner = zlib.decompress(open(path,'rb').read()[5:])
    rt, bs = tbl(inner, 0x13); ro = sorted(rt.items(), key=lambda kv: kv[1])
    spans = {tg:(bs+off, bs+ro[i+1][1] if i+1<len(ro) else len(inner)) for i,(tg,off) in enumerate(ro)}
    a, e = spans[21]; f21, p21 = tbl(inner, a)
    kids, kb = tbl(inner, p21 + f21[1]); ko = sorted(kids.items(), key=lambda kv: kv[1])
    out = []
    for i,(pid,off) in enumerate(ko):
        cs = kb+off; ce = kb+ko[i+1][1] if i+1<len(ko) else e
        fl = parse_fields(inner, cs+4, ce)
        if 18 not in fl: continue  # neutral
        r = fl[2][0] if 2 in fl else 0
        out.append((fl[18][0], r, fl.get(29, b'\0')[0] if 29 in fl else None))
    return out
MAP_DIR = r'C:\Users\<user>\Desktop\Age of Wonders X - Claude\Scenario\Custom'
if __name__ == '__main__':
    for p in sorted(glob.glob(os.path.join(MAP_DIR, 'AoWx - *.hsm'))):
        n = os.path.basename(p)[7:-4]
        try:
            r = races(p)
            print('%-40s %2d  %s' % (n, len(r), ', '.join(RACES[x] if x < 12 else '?%d' % x for _, x, _ in sorted(r))))
        except Exception as ex:
            print('%-40s ERR %r' % (n, ex))
