# -*- coding: utf-8 -*-
"""
Harvest verbatim OBJECT hex-records (structures, sites, neutral cities) from curated maps
into obj_records.pkl for the map generator (v4+).

Sources: "AoWx - After the Fall.hsm" (structure/site palette — the user-approved "legit" set;
dev-only registry objects never appear there) and "AoWx - Slugfest (3P).hsm" (race-0xFF neutral
garrisonless cities, proven playable).

Each harvested entry: the raw record bytes + a patch map of byte offsets to restamp at
placement time:
  hexvar : offset of hexagon child field-1 GUID (u32)  -> dest terrain variant
  coords : [(xoff, yoff)] one per child (1-byte fields 3/4)
  ids    : [offset] of every field-98 instance id (u32) -> fresh ids
  name   : (offset, len) of city name chars (same-length replacement only)
Grouping key = friendly name derived from the record's non-hex children gfx.

Format knowledge: reference files/BXL/HSM_Map_Format_Objects.md
Usage: py "patch scripts/mapgen/harvest_objects.py"
"""
import struct, zlib, os, pickle, collections, re, sys

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
HERE = os.path.dirname(os.path.abspath(__file__))

def make_tbl(dd):
    def tbl(p):
        b = dd[p]; p += 1; nd = 0
        if b & 0x80:
            nd = struct.unpack_from('<I', dd, p)[0]; p += 4
        nb = b & 0x7F; f = {}
        for _ in range(nb):
            f[dd[p]] = dd[p+1]; p += 2
        for _ in range(nd):
            t, o = struct.unpack_from('<II', dd, p); f[t] = o; p += 8
        return f, p
    return tbl

# ---------------- registry: GUID -> (class, gfx, terrain) ----------------
d = open('Release/Release.hss', 'rb').read()
t = make_tbl(d)
root, base = t(0x37)
f5, b5 = t(base + root[5])
kids, kb = t(b5 + f5[1])
order = sorted(kids.items(), key=lambda kv: kv[1])
GFX_RE = re.compile(rb'[ -~]{3,}\.(?:ILB|BMP|ilb|bmp)')
guid2cls, guid2gfx, guid2terr = {}, {}, {}
for i, (cid, off) in enumerate(order):
    end = order[i+1][1] if i+1 < len(order) else len(d) - kb
    cls = struct.unpack_from('<I', d, kb + off)[0]
    f, b1 = t(kb + off + 4)
    if 1 not in f: continue
    guid = struct.unpack_from('<I', d, b1 + f[1])[0]
    guid2cls[guid] = cls
    m = GFX_RE.search(d[kb+off:kb+end])
    guid2gfx[guid] = m.group(0).decode('latin1') if m else ''
    if 7 in f and struct.unpack_from('<I', d, b1 + f[7])[0] == 1:
        guid2terr[guid] = d[b1 + f[7] + 4]     # field 7 = [count u32][terrain byte]
KNOWN_STORED = {cls - 1 for cls in set(guid2cls.values())}

HEX_CLS = (0x20153, 0x2073E)          # hexagon / animated hexagon
DECOR_CLS = (0x20167, 0x20169)        # veg / mountain decor
ROAD_CLS = 0x20165
CROPS_CLS = 0x2036B
SKIP_CLS = {0x20393, 0x20395, 0x203A0, 0x20392, 0x20394, 0x2039F}  # ground-effect overlays

def friendly(gfx):
    n = os.path.basename(gfx).split('.')[0].upper()
    MAP = {'CITY1': 'city1', 'CITY2': 'city2', 'CITY3': 'city3', 'CITY4': 'city4',
           'STR_FARM': 'farm', 'STR_WTWR': 'watchtower', 'STR_TELE': 'teleporter',
           'EPL_DNG2': 'dungeon', 'EPL_MONS': 'lair', 'EPL_ZIG': 'ziggurat',
           'EPL_CASR': 'ruins', 'STR_SANT': 'sanctuary', 'STR_SOL': 'sol',
           'STR_BLDG': 'building', 'STR_RF': 'str_rf', 'MISC_OBJ': 'misc'}
    if n in MAP: return MAP[n]
    if 'NODE' in n or 'NRCK' in n or 'GROV' in n or 'SYRD' in n: return 'node_' + n.lower()
    if n.startswith('A_'): return 'altar_' + n[2:].lower()
    if n.startswith('EPL_'): return 'site_' + n[4:].lower()
    if n.startswith('STR_'): return n[4:].lower()
    return n.lower()

def parse_record(rec):
    """-> list of children dicts. Child offsets come from the record HEADER table
    (fields 0x32..0x35 as bytes + overflow entries in its dword section), relative to
    header end — authoritative extents, no field-size guessing. None if malformed."""
    tt = make_tbl(rec)
    try:
        hdr, p = tt(0)
    except Exception:
        return None
    # header tags 0x32.. are children; smaller tags (e.g. 4) are trailer chunks that
    # bound the last child but aren't parsed themselves
    offs = sorted(o for t2, o in hdr.items() if t2 >= 0x32)
    allobs = sorted(hdr.values())
    if not offs or offs[0] != 0:
        return None
    bounds_all = [p + o for o in allobs] + [len(rec)]
    if any(b > len(rec) for b in bounds_all):
        return None
    out = []
    for i in range(len(offs)):
        cs = p + offs[i]
        ce = next(b for b in bounds_all + [len(rec)] if b > cs)
        if ce - cs < 5: return None
        stored = struct.unpack_from('<I', rec, cs)[0]
        if stored not in KNOWN_STORED: return None
        try:
            f, b1 = tt(cs + 4)
        except Exception:
            return None
        fitems = sorted(f.items(), key=lambda kv: kv[1])
        sizes = {}
        for j, (tag, o) in enumerate(fitems):
            sizes[tag] = (fitems[j+1][1] - o) if j+1 < len(fitems) else (ce - (b1 + o))
        out.append(dict(cls=stored + 1, f=f, base=b1, sizes=sizes,
                        guid=(struct.unpack_from('<I', rec, b1 + f[1])[0]
                              if 1 in f and sizes.get(1, 0) >= 4 else None)))
    return out

def walk_level(path, want_lid):
    inner = zlib.decompress(open(path, 'rb').read()[5:])
    tm = make_tbl(inner)
    root_m, base_m = tm(0x13)
    kids_m, kb_m = tm(base_m + root_m[1])
    csort = sorted(kids_m.items(), key=lambda x: x[1])
    cf, cb = tm(kb_m + csort[0][1] + 4)
    W, H = inner[cb + cf[3]], inner[cb + cf[4]]
    lf_all, lkb = tm(cb + cf[1])
    if want_lid not in lf_all: return
    lf, lb = tm(lkb + lf_all[want_lid] + 4)
    s, e = lb + lf[6], lb + lf[1]      # stream = field 6 (level 1 has an extra byte field 5)
    q, idx = s, 0
    while q < e and idx < W * H:
        L = struct.unpack_from('<I', inner, q)[0]
        yield idx % W, idx // W, bytes(inner[q+4:q+4+L])
        q += 4 + L; idx += 1

CAVE_CLS = 0x2037F        # level-transition entrance (STR_CAVE / whirlpool variants)
harvest = collections.defaultdict(list)
ugveg = []                 # 33B underground decor records (Ug_*/ca_* on cave floor)
skipped = collections.Counter()
SOURCES = ("Scenario/Custom/AoWx - After the Fall.hsm",
           "Scenario/Custom/AoWx - Slugfest (3P).hsm",
           "Scenario/Custom/AoWx - Violence Begets Violence.hsm")
for src, lid in [(p, 0) for p in SOURCES] + [(p, 1) for p in SOURCES]:
    for x, y, rec in walk_level(src, lid):
        if len(rec) == 33 and lid == 1:
            # underground decor: hex + decor child; keep if the decor gfx is Ug_/ca_
            try:
                dcf, dcb = make_tbl(rec)(20)
                g = guid2gfx.get(struct.unpack_from('<I', rec, dcb + dcf[1])[0], '')
            except Exception:
                g = ''
            if g.lower().startswith(('ug_', 'ca_')):
                ugveg.append(rec.hex())
            continue
        if len(rec) <= 33:      # plain / veg / mtn / road-only handled by v3 machinery
            continue
        ch = parse_record(rec)
        if ch is None:
            skipped['unparseable'] += 1
            continue
        clss = [c['cls'] for c in ch]
        obj = [c for c in ch if c['cls'] not in HEX_CLS + DECOR_CLS
               and c['cls'] not in (ROAD_CLS, CROPS_CLS)]
        if not obj:
            continue                      # decor/road combos, not an object record
        if any(c['cls'] in SKIP_CLS for c in ch):
            skipped['ground_fx'] += 1
            continue
        if clss[0] not in HEX_CLS:
            skipped['no_hex_first'] += 1
            continue
        # cities: garrisonless only; keep racial ones grouped per race byte (their field-18
        # recruit roster matches the race), raceless (0xFF) as "_neutral"
        city = next((c for c in obj if c['cls'] == 0x20109), None)
        race = None
        if city is not None:
            f, b1, sz = city['f'], city['base'], city['sizes']
            if 5 in f:
                skipped['city_garrison'] += 1; continue
            if 13 not in f:
                skipped['city_no_race_field'] += 1; continue
            race = rec[b1 + f[13]]
        # build patch map
        hexch = ch[0]
        if 1 not in hexch['f']:
            skipped['empty_hexagon'] += 1; continue    # variant-less hexagon: can't restamp terrain
        patch = dict(hexvar=hexch['base'] + hexch['f'][1], coords=[], ids=[], name=None)
        okrec = True
        for c in ch:
            f, b1, sz = c['f'], c['base'], c['sizes']
            if 3 in f and 4 in f and sz.get(3) == 1 and sz.get(4) == 1:
                patch['coords'].append((b1 + f[3], b1 + f[4]))
            if 98 in f:
                if sz.get(98, 0) < 4: okrec = False
                else: patch['ids'].append(b1 + f[98])
            if c['cls'] == 0x20109 and 12 in f:
                slen = rec[b1 + f[12]]
                patch['name'] = (b1 + f[12] + 1, slen)
            if c['cls'] == 0x20109 and 13 in f:
                patch['race13'] = b1 + f[13]
        if not okrec:
            skipped['odd_id98'] += 1; continue
        terr = guid2terr.get(hexch['guid'])
        sig = '+'.join(sorted({friendly(guid2gfx.get(c['guid'], '?')) for c in obj}))
        if city is not None:
            szn = {0x16: 1, 0x39: 2, 0x3A: 3, 0x3B: 4}.get(city['guid'], 0)
            sig = 'city%d_%s' % (szn, 'neutral' if race == 0xFF else 'r%02x' % race)
            if lid == 1:
                sig = 'ug_' + sig
        if any(c['cls'] == CAVE_CLS for c in obj):
            sig = 'cave' if lid == 0 else 'cave_l1'    # paired level-transition entrances
        elif lid == 1:
            sig = 'ug_' + sig if not sig.startswith('ug_') else sig
        harvest[sig].append(dict(rec=rec.hex(), terr=terr, src=os.path.basename(src),
                                 at=(x, y), patch=patch, race=race,
                                 children=[(c['cls'], c['guid']) for c in ch]))

print(f"skipped: {dict(skipped)}")
print(f"\nharvested groups:")
for sig, lst in sorted(harvest.items()):
    terrs = collections.Counter(e['terr'] for e in lst)
    print(f"  {sig:<28} x{len(lst):3d}  terrains={dict(terrs)}  "
          f"lens={sorted({len(e['rec'])//2 for e in lst})[:6]}")
data = dict(harvest)
data['__ugveg__'] = ugveg
out = os.path.join(HERE, 'obj_records.pkl')
pickle.dump(data, open(out, 'wb'))
print(f"\n{len(ugveg)} underground decor records")
print(f"wrote {out}")
