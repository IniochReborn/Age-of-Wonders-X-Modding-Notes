# -*- coding: utf-8 -*-
"""Walk-validate generated maps: every record parses, stream tiles exactly W*H,
bridge records well-formed, mountain size-vs-context distribution."""
import struct, zlib, os, re, collections, sys

# chdir to the game root only when run from its usual spot inside the game tree;
# in the portable exe the launcher has already set cwd to the user's install
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
if os.path.exists(os.path.join(_root, 'Release', 'Release.hss')):
    os.chdir(_root)

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

d = open('Release/Release.hss', 'rb').read()
t = make_tbl(d)
root, base = t(0x37)
f5, b5 = t(base + root[5])
kids, kb = t(b5 + f5[1])
order = sorted(kids.items(), key=lambda kv: kv[1])
GFX_RE = re.compile(rb'[ -~]{3,}\.(?:ILB|BMP|ilb|bmp)')
guid2cls = {}
guid2terr = {}
guid2gfx = {}
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
        guid2terr[guid] = d[b1 + f[7] + 4]
KNOWN_STORED = {cls - 1 for cls in set(guid2cls.values())} | {0x20217}  # unit stacks

def hexdist(a, b):
    q1, r1 = a[0], a[1] - a[0] // 2
    q2, r2 = b[0], b[1] - b[0] // 2
    dq, dr = q1 - q2, r1 - r2
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2

def parse_record(rec):
    tt = make_tbl(rec)
    try:
        hdr, p = tt(0)
    except Exception:
        return None
    offs = sorted(o for t2, o in hdr.items() if t2 >= 0x32)
    allobs = sorted(hdr.values())
    if not offs or offs[0] != 0: return None
    bounds_all = [p + o for o in allobs] + [len(rec)]
    if any(b > len(rec) for b in bounds_all): return None
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
        out.append(dict(cls=stored + 1, f=f, base=b1,
                        guid=(struct.unpack_from('<I', rec, b1 + f[1])[0] if 1 in f else None)))
    return out

def map_meta(path):
    """root 21 players (num, race), root 38 counter, hero library (24/44)."""
    inner = zlib.decompress(open(path, 'rb').read()[5:])
    tm = make_tbl(inner)
    root_m, base_m = tm(0x13)
    ro = sorted(root_m.items(), key=lambda kv: kv[1])
    spans = {}
    for i, (tg, off) in enumerate(ro):
        end = base_m + ro[i+1][1] if i+1 < len(ro) else len(inner)
        spans[tg] = (base_m + off, end)
    f38, b38 = tm(base_m + root_m[38])
    counter = struct.unpack_from('<I', inner, b38 + f38[10])[0]
    f21, b21 = tm(base_m + root_m[21])
    kids, kb = tm(b21 + f21[1])
    pnums, prace = [], {}
    for pid, off in sorted(kids.items(), key=lambda kv: kv[1]):
        pf, pb = tm(kb + off + 4)
        if 18 in pf:
            n = inner[pb + pf[18]]
            pnums.append(n)
            prace[n] = inner[pb + pf[2]] if 2 in pf else 0
    # hero library: 24 must equal 44 bytewise; names + 0x20233 leader entries
    lib_names, lib_leaders, twins = [], [], False
    if 24 in spans and 44 in spans:
        s24 = inner[spans[24][0]:spans[24][1]]
        s44 = inner[spans[44][0]:spans[44][1]]
        twins = (s24 == s44)
        f0, b0 = tm(spans[24][0])
        if 20 in f0:
            inf, ib = tm(b0 + f0[20])
            hk, hkb = tm(ib + inf[1])
            ho = sorted(hk.items(), key=lambda kv: kv[1])
            for i, (hid, off) in enumerate(ho):
                cs = hkb + off
                ce = hkb + ho[i+1][1] if i+1 < len(ho) else spans[24][1]
                cls_ = struct.unpack_from('<I', inner, cs)[0] + 1
                hf, hb = tm(cs + 4)
                nm = ''
                if 10 in hf:
                    n_ = inner[hb + hf[10]]
                    nm = bytes(inner[hb+hf[10]+1:hb+hf[10]+1+n_]).decode('latin1')
                if cls_ == 0x20233:
                    lib_leaders.append(
                        (inner[hb + hf[47]] if 47 in hf else None, nm))
                else:
                    lib_names.append(nm)
    return pnums, prace, counter, lib_names, lib_leaders, twins

def parse_stack(rec, c):
    """0x20218 child -> (owner|None, x, y, n_leaders, ids, detail).
    detail: units=[(cls, type, xp, race12, name)] for equality/race checks."""
    tt = make_tbl(rec)
    nf, np_ = tt(c['base'] + c['f'][10])
    owner = rec[np_ + nf[4]] if 4 in nf else None
    sx, sy = rec[np_ + nf[5]], rec[np_ + nf[6]]
    uf, ub = tt(np_ + nf[1])
    uo = sorted(uf.items(), key=lambda kv: kv[1])
    leaders, ids, units = 0, [], []
    bounds = c['base'] + c['f'][10]
    for i, (uid, uoff) in enumerate(uo):
        us = ub + uoff
        cls = struct.unpack_from('<I', rec, us)[0] + 1
        vf, vb = tt(us + 4)
        if cls == 0x20233: leaders += 1
        if 5 in vf: ids.append(struct.unpack_from('<I', rec, vb + vf[5])[0])
        # v4.16 semantics: f10 = u16 unit TYPE (0x20214 only); f2 = ability bit
        # count; hero/leader XP = f24 u32 (f7 is the FACE index, unit f7 = XP u8)
        typ = (struct.unpack_from('<H', rec, vb + vf[10])[0]
               if cls == 0x20214 and 10 in vf else None)
        if cls in (0x20231, 0x20233):
            xp = struct.unpack_from('<I', rec, vb + vf[24])[0] if 24 in vf else 0
        else:
            xp = rec[vb + vf[7]] if 7 in vf else None
        r12 = rec[vb + vf[12]] if 12 in vf else None
        f47 = rec[vb + vf[47]] if 47 in vf else None
        # f3 mask size MUST be ceil(f2/8) — f2 is the ability bit count
        abcnt = struct.unpack_from('<I', rec, vb + vf[2])[0] if 2 in vf else None
        if abcnt is not None and 3 in vf:
            vo = sorted(vf.items(), key=lambda kv: kv[1])
            j3 = [k for k, (t3, _) in enumerate(vo) if t3 == 3][0]
            sz3 = (vo[j3+1][1] - vo[j3][1]) if j3+1 < len(vo) else None
            if sz3 is not None and sz3 != max(1, (abcnt + 7) // 8):
                raise ValueError('f3 size %s != ceil(abcount %d/8)' % (sz3, abcnt))
        nm = ''
        if 10 in vf and cls in (0x20231, 0x20233):
            n_ = rec[vb + vf[10]]
            nm = bytes(rec[vb+vf[10]+1:vb+vf[10]+1+n_]).decode('latin1')
        units.append((cls, typ, xp, r12, nm, f47))
    return owner, sx, sy, leaders, ids, units

def walk_level(path, want_lid):
    inner = zlib.decompress(open(path, 'rb').read()[5:])
    tm = make_tbl(inner)
    root_m, base_m = tm(0x13)
    kids_m, kb_m = tm(base_m + root_m[1])
    csort = sorted(kids_m.items(), key=lambda x: x[1])
    cf, cb = tm(kb_m + csort[0][1] + 4)
    W, H = inner[cb + cf[3]], inner[cb + cf[4]]
    lf_all, lkb = tm(cb + cf[1])
    if want_lid not in lf_all: return None
    lf, lb = tm(lkb + lf_all[want_lid] + 4)
    s, e = lb + lf[6], lb + lf[1]
    recs = []
    q, idx = s, 0
    while q < e and idx < W * H:
        L = struct.unpack_from('<I', inner, q)[0]
        recs.append((idx % W, idx // W, bytes(inner[q+4:q+4+L])))
        q += 4 + L; idx += 1
    return W, H, idx, q, e, recs

# classify every MOUNTAIN-gfx decor guid by TRUE pixel width (ILB frame lookup)
def load_ilb_frames(path):
    try:
        b = open(path, 'rb').read()
    except OSError:
        return []
    out, i = [], 0
    while i < len(b) - 16:
        ln = struct.unpack_from('<I', b, i)[0]
        if 5 <= ln <= 24:
            s = b[i+4:i+4+ln]
            if s[-4:].upper() == b'.BMP' and all(0x20 <= c < 0x7F for c in s):
                w, h = struct.unpack_from('<II', b, i + 4 + ln)
                if 0 < w < 2000 and 0 < h < 2000:
                    out.append(w); i += 12 + ln; continue
        i += 1
    return out

GFX_FRAME = {}
for i, (cid, off) in enumerate(order):
    end = (order[i+1][1] if i+1 < len(order) else len(d) - kb) + kb
    st = kb + off
    if struct.unpack_from('<I', d, st)[0] not in (0x20167, 0x20169): continue
    f, b1 = t(st + 4)
    if 1 not in f: continue
    guid = struct.unpack_from('<I', d, b1 + f[1])[0]
    m = GFX_RE.search(d[st:end])
    if not m: continue
    tail = d[st + m.end():end][:12]
    for o2 in range(max(0, len(tail) - 3)):
        v = struct.unpack_from('<I', tail, o2)[0]
        if v <= 40:
            GFX_FRAME[guid] = v; break

_ILB = {}
def gfx_width(guid):
    g = guid2gfx.get(guid, '').lower()
    if not g.endswith('.ilb'): return 0
    path = os.path.join('Images', *g.split('\\'))
    if path not in _ILB: _ILB[path] = load_ilb_frames(path)
    ws = _ILB[path]
    if not ws: return 0
    fr = GFX_FRAME.get(guid, 0)
    return ws[fr] if fr < len(ws) else max(ws)

GUID_SIZE = {}
for guid, g in guid2gfx.items():
    if guid2cls.get(guid) in (0x20167, 0x20169) and 'MOUNTAIN' in g.upper():
        w = gfx_width(guid)
        GUID_SIZE[guid] = 'S' if w <= 60 else 'M' if w <= 93 else 'L' if w <= 125 else 'XL'

# footprints from registry field 7 (slot order: center, ring1 N-cw, ring2 N-cw)
AXD = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)]
SLOTS = [(0, 0)] + AXD[:]
_q, _r = 0, -2
for _i in range(6):
    _wd = AXD[(2 + _i) % 6]
    for _ in range(2):
        SLOTS.append((_q, _r))
        _q += _wd[0]; _r += _wd[1]
FOOT = {}
for i, (cid, off) in enumerate(order):
    st = kb + off
    cls = struct.unpack_from('<I', d, st)[0]
    f, b1 = t(st + 4)
    if 1 not in f or 7 not in f: continue
    guid = struct.unpack_from('<I', d, b1 + f[1])[0]
    n = struct.unpack_from('<I', d, b1 + f[7])[0]
    if not (1 <= n <= 100): continue
    fp = []
    for k in range(min(n, len(SLOTS))):
        a_, b_ = d[b1 + f[7] + 4 + 2*k], d[b1 + f[7] + 5 + 2*k]
        if (a_, b_) != (0xFE, 0xFE):
            fp.append(SLOTS[k])
    FOOT[guid] = fp

def foot_cells(x, y, fp):
    q0, r0 = x, y - x // 2
    out = []
    for dq, dr in fp:
        tx = q0 + dq
        ty = r0 + dr + tx // 2
        out.append((tx, ty))
    return out

def hexn(x, y):
    out = [(x, y-1), (x, y+1), (x-1, y), (x+1, y)]
    out += [(x-1, y-1), (x+1, y-1)] if x % 2 == 0 else [(x-1, y+1), (x+1, y+1)]
    return out

for mp in sys.argv[1:]:
    print('==', mp)
    pnums, prace, counter, lib_names, lib_leaders, twins = map_meta(mp)
    owned_leaders = collections.Counter()   # owner -> leader stacks across levels
    owned_stacks = {}                       # owner -> (lid, (x,y), units) [leader stacks]
    city_info = {}                          # (lid,x,y) -> (guid, race13, owner5)
    terr0 = {}
    stack_bad = []
    for lid in (0, 1, 2):
        r = walk_level(mp, lid)
        if r is None: continue
        W, H, idx, q, e, recs = r
        bad = 0
        events = []   # v4.23: hex-attached events (0x2056C/0x2056E) crash the editor
        own_bad = []  # v6.0: ownable structure whose f5 owner isn't a declared player
        bridges = collections.Counter()
        mtn_at = {}
        mtn_guid_at = {}
        decor_at = set()      # 33B veg/rock/hill decor records
        obj_at = []
        city_at = []
        road_at = set()
        obj_children = {}
        tele_at = {}          # (x,y) -> (dest x, dest y, dest lvl)
        cell_terr = {}
        cave_objs = set()     # level-transition entrances: graphic carved INTO rock
        for x, y, rec in recs:
            if len(rec) == 14:
                cell_terr[(x, y)] = guid2terr.get(struct.unpack_from('<I', rec, 10)[0])
            if len(rec) > 14:
                ch = parse_record(rec)
                if ch is None:
                    bad += 1; continue
                if len(rec) > 33:
                    obj_at.append((x, y))
                    if any(c['cls'] == 0x20109 for c in ch):
                        city_at.append((x, y))
                    obj_children.setdefault((x, y), []).extend(
                        (c['cls'], c['guid']) for c in ch
                        if c['cls'] not in (0x20153, 0x2073E))
                    if any(c['cls'] == 0x2037F for c in ch):
                        cave_objs.add((x, y))
                for c in ch:
                    if c['cls'] == 0x20109:
                        f_, b_ = c['f'], c['base']
                        city_info[(lid, x, y)] = (
                            c['guid'],
                            rec[b_ + f_[13]] if 13 in f_ else None,
                            rec[b_ + f_[5]] if 5 in f_ else None)
                    if c['cls'] != 0x20218: continue
                    try:
                        own_, sx_, sy_, ldr_, ids_, units_ = parse_stack(rec, c)
                    except Exception:
                        stack_bad.append((lid, (x, y), 'parse')); continue
                    if (sx_, sy_) != (x, y):
                        stack_bad.append((lid, (x, y), 'xy=%d,%d' % (sx_, sy_)))
                    if any(i_ >= counter for i_ in ids_):
                        stack_bad.append((lid, (x, y), 'id>=counter'))
                    if own_ is not None:
                        if own_ not in pnums:
                            stack_bad.append((lid, (x, y), 'owner%d' % own_))
                        owned_leaders[own_] += ldr_
                        if ldr_:
                            owned_stacks[own_] = (lid, (x, y), units_)
                ht_ = next((guid2terr.get(c['guid']) for c in ch
                            if c['cls'] in (0x20153, 0x2073E)), None)
                if ht_ is not None:
                    cell_terr[(x, y)] = ht_
                for c in ch:
                    if c['cls'] in (0x2056C, 0x2056E):
                        events.append((x, y, hex(c['cls'])))
                    # v6.0: TProductionPlace (shipyard/guild) with a source-map
                    # owner outside this map's player list crashes the editor at
                    # load (seed 743784: shipyard f5=4, 3 players; PROVEN by f5
                    # surgery). Pool/tower/shrine tolerate it (probed) — only
                    # the fatal family FAILs here. 0/0xFF = no owner.
                    if c['cls'] in (0x204BF, 0x2092F):
                        f_, b_ = c['f'], c['base']
                        if 5 in f_:
                            v5 = rec[b_ + f_[5]]
                            if v5 not in (0, 0xFF) and v5 not in pnums:
                                own_bad.append((x, y, hex(c['cls']), v5))
                    if c['cls'] == 0x20105:      # teleporter: dest x/y (+level f9)
                        f_, b_ = c['f'], c['base']
                        tele_at[(x, y)] = (rec[b_ + f_[7]], rec[b_ + f_[8]],
                                           rec[b_ + f_[9]] if 9 in f_ else 0)
                ismtn = False
                for c in ch:
                    if c['cls'] == 0x2087B:
                        ht = next((guid2terr.get(cc['guid']) for cc in ch
                                   if cc['cls'] in (0x20153, 0x2073E)), None)
                        bridges[(c['guid'], ht)] += 1
                        road_at.add((x, y))
                    if c['cls'] == 0x20165:
                        road_at.add((x, y))
                    if c['cls'] in (0x20167, 0x20169) and c['guid'] in GUID_SIZE:
                        tag = GUID_SIZE[c['guid']]
                        if c['cls'] == 0x20167: tag = 'h' + tag   # hill
                        mtn_at[(x, y)] = tag
                        mtn_guid_at[(x, y)] = c['guid']
                        ismtn = True
                if len(rec) == 33 and not ismtn:
                    decor_at.add((x, y))
        if lid == 0:
            terr0 = dict(cell_terr)
        # footprint-based rules: no structure/road/bridge/decor inside any footprint
        objset = set(obj_at)
        fpcells = set()
        vio_obj = vio_road = vio_decor = 0
        for p, g in mtn_guid_at.items():
            fp = FOOT.get(g)
            if not fp or len(fp) <= 1: continue
            for c_ in foot_cells(p[0], p[1], fp):
                if c_ == p: continue
                fpcells.add(c_)
                if c_ in objset: vio_obj += 1
                if c_ in road_at: vio_road += 1
                if c_ in decor_at: vio_decor += 1
        # STRUCTURE footprints: no other object/decor inside; roads allowed only
        # inside CITY footprints (roads run to city gates)
        s_obj = s_decor = s_road = s_rock = 0
        cityset = set(city_at)
        sanct_tops = set()
        for p, chl in obj_children.items():
            for cls_, gd_ in chl:
                fp = FOOT.get(gd_)
                if not fp or len(fp) <= 1: continue
                cells = foot_cells(p[0], p[1], fp)
                if 'SANT' in guid2gfx.get(gd_, '').upper():
                    sanct_tops.add(min(cells, key=lambda c_: (c_[1], abs(c_[0]-p[0]))))
                for c_ in cells:
                    if c_ == p: continue
                    fpcells.add(c_)
                    if c_ in objset: s_obj += 1
                    if c_ in decor_at: s_decor += 1
                    if c_ in road_at and p not in cityset: s_road += 1
                    if (lid > 0 and p not in cave_objs
                            and cell_terr.get(c_) not in (12, 1, 2, 3, 4, 5)):
                        s_rock += 1      # UG structure graphic over solid rock/wet
                                         # (v4.24: surface terrain is valid UG floor)
        # teleporter destinations: another teleporter, a sanctuary top, or a clear
        # passable hex (one-way wilderness landings)
        tele_bad = []
        for p, (dx, dy, dl) in tele_at.items():
            if dl != lid:      # cross-level dest: can't resolve here
                continue
            d_ = (dx, dy)
            if d_ in tele_at or d_ in sanct_tops:
                continue
            if d_ not in objset and d_ not in mtn_at and d_ not in fpcells:
                continue       # wilderness landing spot
            tele_bad.append((p, d_))
        violRon = sum(1 for p in road_at if p in mtn_at)   # road ON a mountain/hill hex
        szc = collections.Counter(mtn_at.values())
        ok = 'OK' if (idx == W * H and q == e and bad == 0 and vio_obj == 0
                      and vio_road == 0 and vio_decor == 0 and violRon == 0
                      and s_obj == 0 and s_decor == 0 and s_road == 0
                      and s_rock == 0 and not tele_bad and not events
                      and not own_bad) else 'FAIL'
        print('  L%d: %s tiles=%d/%d streamend=%s badrecs=%d objs=%d'
              ' mtnfp[obj=%d road=%d decor=%d] structfp[obj=%d road=%d decor=%d'
              ' rock=%d] road-on-mtn=%d teles=%d bad-dest=%d sizes=%s' %
              (lid, ok, idx, W * H, q == e, bad, len(obj_at), vio_obj, vio_road,
               vio_decor, s_obj, s_road, s_decor, s_rock, violRon, len(tele_at),
               len(tele_bad), dict(szc)))
        for tb in tele_bad[:5]:
            print('      BAD TELE DEST:', tb)
        for ev in events[:5]:
            print('      EVENT CHILD (editor-crashing):', ev)
        for ob in own_bad[:5]:
            print('      OWNER OUT OF RANGE (editor-crashing):', ob)
        if bridges:
            for (g, ht), n in bridges.items():
                print('    bridge guid=0x%X on hexterr=%s x%d' % (g, ht, n))
        if mtn_at:
            mtn_only = {p: sz for p, sz in mtn_at.items()}   # incl hills (S/M)
            by_ctx = collections.defaultdict(collections.Counter)
            for p, sz in mtn_only.items():
                n_ = sum(1 for q_ in hexn(*p) if q_ in mtn_only)
                by_ctx['iso' if n_ == 0 else ('pair' if n_ == 1 else 'clu')][sz] += 1
            for ctx in ('iso', 'pair', 'clu'):
                if by_ctx.get(ctx):
                    print('    mtn %s: %s' % (ctx, dict(by_ctx[ctx].most_common())))
    if owned_leaders or pnums:
        # v4.14 start invariants (meaningful for generated maps, not official ones)
        errs = ['%s L%d %s' % (m, l_, p_) for l_, p_, m in stack_bad]
        if (sorted(owned_leaders) != sorted(pnums)
                or any(v != 1 for v in owned_leaders.values())):
            errs.append('leader-count %s vs players %s' % (dict(owned_leaders), pnums))
        heroxp, ldrxp, comps_sig, sizes_, nheroes = set(), set(), set(), set(), set()
        land_ = {p2 for p2, t2 in terr0.items() if t2 in (1, 2, 3, 4, 5, 12)}
        RACE_BASE = {0: 0, 1: 18, 3: 36, 2: 54, 4: 72, 5: 90, 6: 108, 7: 126,
                     8: 144, 9: 162, 10: 180, 11: 198}
        for own_, (lid_, pos_, units_) in sorted(owned_stacks.items()):
            race_ = prace.get(own_, 0)
            base_ = RACE_BASE.get(race_, 0)
            slots_ = []
            for cls_, typ_, xp_, r12_, nm_, f47_ in units_:
                if f47_ != own_:
                    errs.append('p%d %s f47=%s != owner'
                                % (own_, hex(cls_), f47_))
                if cls_ == 0x20233:
                    ldrxp.add(xp_)
                    if r12_ is not None and r12_ != race_:
                        errs.append('p%d leader race %s != player %s' % (own_, r12_, race_))
                    if nm_ and nm_ in lib_names:
                        errs.append('p%d leader "%s" still in library' % (own_, nm_))
                elif cls_ == 0x20231:
                    heroxp.add(xp_)
                    if nm_ and nm_ in lib_names:
                        errs.append('p%d hero "%s" still in library' % (own_, nm_))
                elif cls_ == 0x20214:
                    if typ_ >= 216:
                        slots_.append(typ_)          # shared raceless unit
                    elif base_ <= typ_ < base_ + 18:
                        slots_.append(typ_ - base_)  # own-race block slot
                    else:
                        errs.append('p%d unit t%d outside race-%d block'
                                    % (own_, typ_, race_))
            comps_sig.add(tuple(sorted(slots_)))
            nheroes.add(sum(1 for u_ in units_ if u_[0] == 0x20231))
            ci = city_info.get((lid_, pos_[0], pos_[1]))
            if ci is not None:
                if ci[2] is not None and ci[2] != own_:
                    errs.append('p%d stack on city owned by %s' % (own_, ci[2]))
                if lid_ == 0:
                    sizes_.add(ci[0])
            else:
                near = [c2 for (l2, x2, y2), c2 in city_info.items()
                        if l2 == lid_ and hexdist((x2, y2), pos_) <= 4]
                if not any(c2[1] == race_ or c2[2] == own_ for c2 in near):
                    errs.append('p%d: no owned/own-race city within 4' % own_)
                else:
                    for c2 in near:
                        if c2[1] == race_ and lid_ == 0:
                            sizes_.add(c2[0]); break
            if lid_ > 0 and race_ not in (6, 8, 10):
                errs.append('p%d race %d underground' % (own_, race_))
            if lid_ == 0 and race_ != 2 and pos_ in land_:
                comp, stck, seen_ = 0, [pos_], {pos_}
                while stck:
                    p3 = stck.pop(); comp += 1
                    for q3 in hexn(*p3):
                        if q3 in land_ and q3 not in seen_:
                            seen_.add(q3); stck.append(q3)
                if comp < 25:
                    errs.append('p%d on %d-hex island' % (own_, comp))
        if len(comps_sig) > 1: errs.append('party slot mismatch %s' % comps_sig)
        if len(sizes_) > 1: errs.append('start-city sizes differ %s' % sizes_)
        if len(nheroes) > 1: errs.append('hero counts differ %s' % nheroes)
        if len(ldrxp) > 1: errs.append('leader XP differ %s' % ldrxp)
        if len(heroxp) > 1: errs.append('hero XP differ %s' % heroxp)
        if not twins: errs.append('root 24 != root 44')
        if owned_stacks:
            # v4.17: the library must hold NO 0x20233 entries — lib leader
            # entries mean "free/unplaced" to the editor and clobber the placed
            # leaders in the Leaders UI (TLeader.Activate: last one wins).
            # Official structure: placed stack + player f30 only (AtF/Slugfest).
            if lib_leaders:
                errs.append('library holds leader entries %s (must be none '
                            'when leaders are placed)' % lib_leaders)
        st = ('OK' if not errs and owned_leaders else
              'NO STARTS' if not owned_leaders else 'FAIL')
        print('  PLAYERS: %s declared=%s leaders=%s lib=%d%s' %
              (st, pnums, dict(owned_leaders), len(lib_names),
               ('  ERRORS: ' + '; '.join(str(e) for e in errs[:8])) if errs else ''))
