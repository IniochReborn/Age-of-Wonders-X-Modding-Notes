#!/usr/bin/env python3
r"""
Cataclysm: finish the lower half of the volcano on Caverns (level 1) and Depths (level 2)  (2026-11-21).

User: "finish the bottom half of the volcano on caverns/depths; notice how terrain transitions between levels and
emulate that".  Level rule read from the finished levels (Firmament -> Surface -> Caverns): under the land of the
level above = solid rock/earth; the ring beyond the upper footprint = open wasteland slope with mountains / hills /
decor; lava runs across that ground and its tips stick out over the Chasm (burning) to land on the next level.

What it does (only Chasm hexes, bare rock crumbs and object-free lava are touched; no lava is removed):
  Caverns  south-east lava streams (painted over open Chasm): wasteland between the streams, tips left hanging.
  Depths   south / south-east foot: wasteland shore band between the rock body and the lava lakes, peninsulas
           between the lake lobes, lake bottoms left open; rock crumbs >= 2 hexes outside the Caverns footprint
           -> wasteland (70 %); 2-hex Chasm moat kept to the outer lands.
  both     mountains 10 % / hills 5 % / decor 6 % on the new ground (kinds harvested from the map's own wasteland,
           footprint-checked), fire effect on lava tips (>= 3 Chasm neighbours, half of those with 2).
Hex adjacency = COLUMN parity (mapgen hexn).  Records: hexagon child 11 B, decor/mountain child 17 B (uid,x,y),
fire child 20 B + field tag 4 |= 0x20 (as on every user-placed fire).

Usage: py -3.10 cataclysm_finish_volcano_v1.py            (dry run: PNG previews + out.hsm in the OUT dir)
       ... --apply   (backup <game>\backup\Scenario\Custom\<map>.bak_volcano, then write the map in place)
Env: SEED (default 20261121), FIRE=tips|none|full, SRC=<map path>, OUT=<preview dir, default %TEMP%\cataclysm_volcano>
"""
import os, sys, struct, zlib, re, random, math, collections, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
import hsm_grid as HG  # noqa: E402
from bakpath import bak_path  # noqa: E402

tbl = HG.tbl
W = H = 127
SRC = os.environ.get('SRC') or os.path.join(GAME, 'Scenario', 'Custom', '______Cataclysm - Handover.hsm')
OUT = os.environ.get('OUT') or os.path.join(tempfile.gettempdir(), 'cataclysm_volcano')
SEED = int(os.environ.get('SEED', '20261121'))
FIRE = os.environ.get('FIRE', 'tips')
VOID = (11, 14, 15, None)


def load_resources():
    """(cls, uid) -> terrain list / strings / footprint, from Release.hss."""
    d = open(os.path.join(GAME, 'Release', 'Release.hss'), 'rb').read()
    root, base = tbl(d, 0x37); f5, b5 = tbl(d, base + root[5]); kids, kb = tbl(d, b5 + f5[1])
    order = sorted(kids.items(), key=lambda kv: kv[1])
    pat = re.compile(rb'[ -~]{3,}')
    res = {}
    for i, (cid, off) in enumerate(order):
        end = order[i+1][1] if i+1 < len(order) else len(d) - kb
        cls = struct.unpack_from('<I', d, kb + off)[0]
        f, b1 = tbl(d, kb + off + 4)
        if 1 not in f: continue
        guid = struct.unpack_from('<I', d, b1 + f[1])[0]
        terr = []
        if 7 in f:
            n = struct.unpack_from('<I', d, b1 + f[7])[0]
            if 1 <= n <= 100:
                terr = [(d[b1+f[7]+4+2*k], d[b1+f[7]+5+2*k]) for k in range(n)]
        strs = [m.group(0).decode('latin1') for m in pat.finditer(d[kb+off:kb+end])][:4]
        res.setdefault((cls, guid), dict(terr=terr, strs=strs))
    return res


INFO = load_resources()

# decor field-7 footprint slots -> axial offsets (mapgen load_decor_meta); (0xFE,0xFE) = hex not covered
_AXD = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)]
_SLOTS = [(0, 0)] + _AXD[:]
_q, _r = 0, -2
for _i in range(6):
    _wd = _AXD[(2 + _i) % 6]
    for _ in range(2):
        _SLOTS.append((_q, _r)); _q += _wd[0]; _r += _wd[1]
FOOT = {uid: [_SLOTS[k] for k in range(min(len(v['terr']), len(_SLOTS))) if v['terr'][k] != (0xFE, 0xFE)]
        for (cls, uid), v in INFO.items() if v['terr']}


def foot_cells(x, y, fp):
    q0, r0 = x, y - x // 2
    return [(q0 + dq, r0 + dr + (q0 + dq) // 2) for dq, dr in fp]


def hexn(x, y):
    out = [(x, y-1), (x, y+1), (x-1, y), (x+1, y)]
    out += [(x-1, y-1), (x+1, y-1)] if x % 2 == 0 else [(x-1, y+1), (x+1, y+1)]
    return [(nx, ny) for nx, ny in out if 0 <= nx < W and 0 <= ny < H]


def hexdist(a, b):
    q1, r1 = a[0], a[1] - a[0] // 2
    q2, r2 = b[0], b[1] - b[0] // 2
    dq, dr = q1 - q2, r1 - r2
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def bfs(seeds, limit=99):
    d = {p: 0 for p in seeds}; fr = list(seeds); k = 0
    while fr and k < limit:
        k += 1; nf = []
        for p in fr:
            for q in hexn(*p):
                if q not in d: d[q] = k; nf.append(q)
        fr = nf
    return d


# ------------------------------------------------------------------ .hsm level access
def level_span(inner, lkb, lk, lid):
    loff = lkb + lk[lid]
    lf, lb = tbl(inner, loff + 4)
    return loff, lb + lf[6], lb + lf[1]


def read_levels(raw):
    g = HG.loads(raw); inner = g.inner
    assert (g.W, g.H) == (W, H), (g.W, g.H)
    lk, lkb = tbl(inner, g.cb + g.cf[1])
    out = {}
    for lid in sorted(lk):
        loff, s, e = level_span(inner, lkb, lk, lid)
        recs = []; q = s
        while q < e:
            L = struct.unpack_from("<I", inner, q)[0]; recs.append(bytes(inner[q+4:q+4+L])); q += 4+L
        assert q == e and len(recs) == W*H
        out[lid] = recs
    return g, out


def set_entry(buf, tblpos, tag, delta):
    kind, pos = HG.tbl_entry_pos(buf, tblpos, tag)
    if kind == "u32":
        struct.pack_into("<I", buf, pos, struct.unpack_from("<I", buf, pos)[0] + delta)
    else:
        assert 0 <= buf[pos] + delta <= 255
        buf[pos] += delta


def replace_level(raw, lid, newrecs):
    g = HG.loads(raw); inner = g.inner
    lk, lkb = tbl(inner, g.cb + g.cf[1])
    loff, s, e = level_span(inner, lkb, lk, lid)
    stream = b"".join(struct.pack("<I", len(r)) + r for r in newrecs)
    delta = len(stream) - (e - s)
    out = bytearray(inner[:s]) + stream + inner[e:]
    set_entry(out, loff + 4, 1, delta)
    for l2, lo in lk.items():
        if lkb + lo > loff:
            set_entry(out, g.cb + g.cf[1], l2, delta)
    return b"CFS\x00\x02" + zlib.compress(bytes(out), 9)


def kid_info(c):
    cls = struct.unpack_from('<I', c)[0] + 1
    f, p = tbl(c, 4)
    uid = struct.unpack_from('<I', c, p + f[1])[0] if 1 in f and p + f[1] + 4 <= len(c) else None
    return cls, uid


def grids(recs):
    """terrain byte per hex + object list per hex ((cls, uid) or ('tagN', hex))."""
    T, O = [], []
    for r in recs:
        t = None; objs = []
        for tag, c in HG.children(r):
            if tag < 0x32 or len(c) < 6:
                objs.append(('tag%d' % tag, c.hex())); continue
            cls, uid = kid_info(c)
            rr = INFO.get((cls, uid))
            if tag == 0x32: t = rr['terr'][0][0] if rr and rr['terr'] else None
            else: objs.append((cls, uid))
        T.append(t); O.append(objs)
    return T, O


def has_obj(o):
    return any(isinstance(q[0], int) for q in o)


COL = {0: (40, 90, 200), 1: (60, 160, 60), 2: (220, 200, 120), 3: (240, 240, 250), 4: (150, 150, 90), 5: (120, 88, 76),
       6: (170, 220, 240), 7: (90, 60, 30), 8: (70, 70, 70), 9: (255, 90, 0), 10: (20, 50, 120), 11: (40, 0, 60),
       12: (165, 125, 80), 13: (120, 170, 200), 14: (150, 200, 255), 15: (0, 0, 0), None: (255, 0, 255)}


def render(T, O, x0, y0, x1, y1, path, S=14, mark=None):
    """Preview: one square per hex (odd columns half a cell lower); M mountain, h hill, d decor, f fire, C cave,
    B bridge, r road, S structure; cyan outline = hex changed by this script."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    im = Image.new('RGB', ((x1-x0)*S + 22, (y1-y0)*S + S//2 + 14), (0, 0, 0)); d = ImageDraw.Draw(im); f = ImageFont.load_default()
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = y*W + x; t = T[i]
            px = 22 + (x-x0)*S; py = 14 + (y-y0)*S + (S//2 if x & 1 else 0)
            d.rectangle([px, py, px+S-2, py+S-2], fill=COL.get(t, (255, 0, 255)))
            if mark and (x, y) in mark: d.rectangle([px, py, px+S-2, py+S-2], outline=(0, 255, 255))
            lab = ''
            for o in O[i]:
                if isinstance(o[0], int):
                    if o[0] == 0x20167:
                        nm = (INFO.get(o, {}).get('strs') or ['?'])[0]; lab += 'h' if nm == 'Hills' else 'd'
                    else:
                        lab += {0x20169: 'M', 0x20165: 'r', 0x2077f: 'f', 0x2037f: 'C', 0x2087b: 'B', 0x20107: 'p',
                                0x20109: 'T', 0x20105: 't'}.get(o[0], 'S')
            if lab: d.text((px+2, py), lab[:2], fill=(255, 255, 255) if t not in (3, 14, 2) else (0, 0, 0), font=f)
        if y % 2 == 0: d.text((0, 14+(y-y0)*S), str(y), fill=(255, 255, 0), font=f)
    for x in range(x0, x1, 5): d.text((22+(x-x0)*S, 0), str(x), fill=(255, 255, 0), font=f)
    im.save(path)


# ===================================================================== generator
def hexchild(cls, uid):
    return struct.pack('<I', cls - 1) + b'\x01\x01\x00' + struct.pack('<I', uid)


def decorchild(cls, uid, x, y):
    return struct.pack('<I', cls - 1) + bytes.fromhex('03010003040405') + struct.pack('<I', uid) + bytes([x, y])


def firechild(uid, x, y):
    return struct.pack('<I', 0x2077E) + bytes.fromhex('040100030404050606') + struct.pack('<I', uid) + bytes([x, y, 1])


def smooth_noise(rnd, cell=3.0):
    gw = int(W / cell) + 4
    gr = [[rnd.random() for _ in range(gw)] for _ in range(gw)]

    def s(x, y):
        fx, fy = x / cell, (y + 0.5 * (x & 1)) / cell
        ix, iy = int(fx), int(fy); tx, ty = fx - ix, fy - iy
        a = gr[iy][ix] + (gr[iy][ix+1] - gr[iy][ix]) * tx
        b = gr[iy+1][ix] + (gr[iy+1][ix+1] - gr[iy+1][ix]) * tx
        return a + (b - a) * ty
    return s


def harvest(G):
    """Mountain / hill / decor kinds the user placed on wasteland (underground variants for mountains and hills)."""
    mtn, hill, decor = collections.Counter(), collections.Counter(), collections.Counter()
    for lid in (0, 1, 2, 3):
        T, O = G[lid]
        for i in range(W * H):
            if T[i] != 5: continue
            for o in O[i]:
                if not isinstance(o[0], int) or o not in INFO: continue
                nm = INFO[o]['strs'] or ['?']
                terrs = {t for t, _ in INFO[o]['terr'] if t < 16}
                if o[0] == 0x20169:
                    if lid in (1, 2) and terrs == {5}: mtn[o] += 1
                elif o[0] == 0x20167 and nm[0] == 'Hills':
                    if lid in (1, 2) and 5 in terrs: hill[o] += 1
                elif o[0] == 0x20167 and 'Crops' not in nm[0] and 5 in terrs:
                    decor[o] += 1
    return mtn, hill, decor


def build(lid, G, rnd, PAL, sector, downhill, cap_a=None, keepout=None, conv_rock=None, firezone=None,
          pa={1: .95, 2: .62, 3: .22}, pb={1: .9, 2: .5}, delta=2.0, rimf=0.25):
    """New wasteland on Chasm hexes of `sector`: near solid ground (pa by distance) or near lava (pb), but never
    further downhill than (the lowest lava within 3 hexes) - delta, so the lava ends keep hanging over the Chasm."""
    T, O = list(G[lid][0]), G[lid][1]
    P = lambda p: p[1] * W + p[0]
    box = [(x, y) for y in range(40, 99) for x in range(26, 113)]
    solid = {p for p in box if T[P(p)] in (5, 7, 8, 12)}
    lava = {p for p in box if T[P(p)] == 9}
    d_solid, d_lava = bfs(solid, 12), bfs(lava, 6)
    sm = smooth_noise(rnd)
    new = set()
    cand = [p for p in box if sector(*p) and T[P(p)] == 11 and not has_obj(O[P(p)]) and not (keepout and p in keepout)]
    for p in cand:
        a, b = d_solid.get(p, 99), d_lava.get(p, 99)
        pr = max(pa.get(a, 0), pb.get(b, 0))
        if cap_a and a > cap_a: pr = 0
        near = [l for l in lava if hexdist(l, p) <= 3]
        if near and downhill(p) > max(downhill(l) for l in near) - delta:
            pr = pr * rimf if a == 1 else 0
        if pr > 0.6 * sm(*p) + 0.4 * rnd.random(): new.add(p)
    land = lambda q: (q in new) or T[P(q)] not in VOID
    for it in range(2):
        for p in cand:                                   # fill pin-holes
            if p in new: continue
            nl = sum(1 for q in hexn(*p) if land(q))
            near = [l for l in lava if hexdist(l, p) <= 2]
            beyond = near and downhill(p) > max(downhill(l) for l in near) - 1
            if nl >= 5 and not beyond: new.add(p)
        for p in sorted(new):                            # drop most lone specks
            if sum(1 for q in hexn(*p) if land(q)) <= 1 and rnd.random() < 0.8: new.discard(p)
    conv = set()
    if conv_rock:
        for p in box:
            if sector(*p) and T[P(p)] == 8 and not has_obj(O[P(p)]) and conv_rock(p) and rnd.random() < 0.7: conv.add(p)
    for p in new | conv: T[P(p)] = 5
    # ---- decoration
    mtn, hill, decor = PAL
    pick = lambda c: rnd.choices(list(c), weights=list(c.values()))[0]
    objs = {}; used = {p for p in box if has_obj(O[P(p)])}
    order = sorted(new | conv); rnd.shuffle(order)

    def try_place(p, o):
        cells = foot_cells(p[0], p[1], FOOT.get(o[1], [(0, 0)]))
        if any(not (0 <= cx < W and 0 <= cy < H) or T[cy * W + cx] != 5 or (cx, cy) in used for cx, cy in cells): return False
        objs[p] = o; used.update(cells); return True
    for p in order:
        if p in used: continue
        r = rnd.random()
        if r < 0.10:
            if not try_place(p, pick(mtn)): try_place(p, (0x20169, 0x92))
        elif r < 0.15:
            if not try_place(p, pick(hill)): try_place(p, (0x20167, 0xaa29b37))
        elif r < 0.21:
            try_place(p, pick(decor))
    # ---- fire on dripping lava tips
    fires = {}
    if firezone and FIRE != 'none':
        for p in box:
            if T[P(p)] != 9 or not firezone(*p) or has_obj(O[P(p)]): continue
            v = sum(1 for q in hexn(*p) if T[P(q)] in (11, 14))
            if v >= 3 or (v == 2 and rnd.random() < 0.5) or (FIRE == 'full' and rnd.random() < 0.5):
                fires[p] = 0x21 if rnd.random() < 0.55 else 0x59770ef
    return T, new, conv, objs, fires


def apply_level(recs, R, rnd, wl_uids):
    T, new, conv, objs, fires = R
    out = list(recs)
    for p in sorted(set(new) | set(conv) | set(objs) | set(fires)):
        i = p[1] * W + p[0]
        kids = HG.children(recs[i])
        hexk = [k for k in kids if k[0] == 0x32]; low = [k for k in kids if k[0] < 0x32]; other = [k for k in kids if k[0] > 0x32]
        assert len(hexk) == 1 and not other, (p, kids)
        hx = hexk[0][1]
        if p in new or p in conv: hx = hexchild(0x20153, rnd.choice(wl_uids))
        nk = [(0x32, hx)]
        if p in objs: nk.append((0x33, decorchild(objs[p][0], objs[p][1], p[0], p[1])))
        if p in fires:
            nk.append((0x33, firechild(fires[p], p[0], p[1])))
            if any(t == 4 for t, _ in low):
                low = [(t, (c[:1] + bytes([c[1] | 0x20]) + c[2:]) if t == 4 else c) for t, c in low]
            else:
                low = low + [(4, b'\x00\x20')]
        out[i] = HG.build(nk + low)
    return out


def busy():
    out = os.popen("tasklist").read().lower()
    return [n for n in ("aowdevx.exe", "aowx.exe", "aowed.exe") if n in out]


def main():
    do_apply = "--apply" in sys.argv
    raw = open(SRC, 'rb').read()
    g, lv = read_levels(raw)
    G = {lid: grids(lv[lid]) for lid in lv}
    rnd = random.Random(SEED)
    PAL = harvest(G)
    wl_uids = sorted({kid_info(HG.children(lv[l][i])[0][1])[1] for l in (1, 2) for i in range(W * H) if G[l][0][i] == 5})
    print('map %s  seed %d  fire=%s' % (os.path.basename(SRC), SEED, FIRE))
    print('palette: %d mountain kinds, %d hill kinds, %d decor kinds, %d wasteland tiles' % (len(PAL[0]), len(PAL[1]), len(PAL[2]), len(wl_uids)))
    # Caverns: south-east lava streams (they run east / south-east)
    R1 = build(1, G, rnd, PAL, sector=lambda x, y: 78 <= x <= 102 and 72 <= y <= 92,
               downhill=lambda p: p[0] + 0.6 * (p[1] + 0.5 * (p[0] & 1)),
               cap_a=7, firezone=lambda x, y: y >= 72 or x >= 84, delta=2.0)
    # Depths: south + south-east foot (downhill = south, turning east past x 84)
    T2 = G[2][0]
    outer = {(x, y) for y in range(H) for x in range(W) if T2[y*W+x] in (0, 1, 2, 3, 4, 6, 10, 13)
             or (T2[y*W+x] == 12 and x >= 103) or (T2[y*W+x] in (5, 7, 8, 12) and y >= 99)}
    keep = set(bfs(outer, 2))
    cav_solid = {(x, y) for y in range(H) for x in range(W) if R1[0][y*W+x] in (5, 7, 8, 12)}
    d_cav = bfs(cav_solid, 4)
    R2 = build(2, G, rnd, PAL, sector=lambda x, y: 36 <= x <= 106 and 73 <= y <= 98 and (x >= 49 or y >= 84),
               downhill=lambda p: p[1] + 0.5 * (p[0] & 1) + 0.9 * max(0, p[0] - 84),
               keepout=keep, conv_rock=lambda p: d_cav.get(p, 9) >= 2, firezone=lambda x, y: y >= 73,
               pa={1: .97, 2: .8, 3: .45, 4: .15}, pb={1: .92, 2: .6, 3: .25}, delta=1.5, rimf=0.4)
    new_raw = raw
    for lid, R in ((1, R1), (2, R2)):
        T, new, conv, objs, fires = R
        k = collections.Counter(('mountain' if o[0] == 0x20169 else 'hill' if INFO[o]['strs'][0] == 'Hills' else 'decor') for o in objs.values())
        print('level %d: +%d wasteland from chasm, %d rock->wasteland, objects %s, fires %d' % (lid, len(new), len(conv), dict(k), len(fires)))
        new_raw = replace_level(new_raw, lid, apply_level(lv[lid], R, rnd, wl_uids))
    # verify by re-parse: untouched levels / hexes byte-identical, touched terrain as planned
    g2, lv2 = read_levels(new_raw)
    os.makedirs(OUT, exist_ok=True)
    for lid in lv:
        if lid not in (1, 2): assert lv2[lid] == lv[lid]
    for lid, R in ((1, R1), (2, R2)):
        touched = set(R[1]) | set(R[2]) | set(R[3]) | set(R[4])
        for i in range(W * H):
            if (i % W, i // W) not in touched: assert lv2[lid][i] == lv[lid][i]
        Tn, On = grids(lv2[lid])
        assert Tn == R[0]
        assert not any(G[lid][0][p[1]*W+p[0]] == 9 and Tn[p[1]*W+p[0]] != 9 for p in touched)   # no lava removed
        render(Tn, On, 28, 44, 112, 102, os.path.join(OUT, 'new_L%d.png' % lid), mark=touched)
        render(G[lid][0], G[lid][1], 28, 44, 112, 102, os.path.join(OUT, 'old_L%d.png' % lid))
    open(os.path.join(OUT, 'out.hsm'), 'wb').write(new_raw)
    print('re-parse OK; previews + out.hsm in', OUT)
    if not do_apply:
        print('Dry run - rerun with --apply.'); return 0
    b = busy()
    if b:
        print('NOTE: %s is running - if this map is open there, do NOT save it from the editor; reopen it instead.' % ', '.join(b))
    bk = bak_path(SRC, ".bak_volcano")
    if not os.path.exists(bk):
        shutil.copy2(SRC, bk); print('backup', bk)
    with open(SRC, "r+b") as fh:
        fh.seek(0); fh.write(new_raw); fh.truncate()
    assert open(SRC, "rb").read() == new_raw
    shutil.copy2(SRC, bak_path(SRC, ".volcano_v1_result"))
    print('written and verified:', SRC)
    return 0


if __name__ == '__main__':
    sys.exit(main())
