# -*- coding: utf-8 -*-
"""
AoWx random map generator — v4: v3 terrain/veg/mtn + OBJECTS (cities, structures, resources).

Objects are verbatim records harvested from "After the Fall" (structures/sites — the approved
palette) and Slugfest (raceless neutral cities, proven playable) by harvest_objects.py
(obj_records.pkl). At placement each record is restamped: child x/y coords, hexagon terrain
variant, fresh field-98 instance ids (allocated past the template map's root-38 counter, which
is bumped afterwards), and same-length randomized city names. Cities are all neutral
(race 0xFF, Slugfest-style). Format notes: reference files/BXL/HSM_Map_Format_Objects.md.

PLAYER STARTS (v4.14-17): each player's LEADER is a copy of a same-race hero from
the map's default hero library (root 24/44 twins); copied heroes (and the 15%-case
starting heroes, equal XP for everyone) are removed from that map's library. The
library keeps NO 0x20233 leader entries (v4.17): lib entries mean "free/unplaced"
to the editor and clobber the placed leaders in the Leaders UI — official maps are
placed-stack + player-f30 only (AtF/Slugfest). The template's default "Human"/
"Azrac" pair is dropped. Unit/hero/leader field 47 = OWNING PLAYER NUMBER
(the linkage the engine uses; v4.15 fix).
Parties are rolled once as SLOT indexes into each race's 18-unit Unitres block
(0 archer / 1 priest / 2 cavalry / 3 infantry; Human base 0, Azrac 18, Frostling 36,
Lizard 54, Elf 72, Halfling 90, Dwarf 108, Highmen 126, DarkElf 144, Orc 162,
Goblin 180, Undead 198), so everyone gets equal parties of their OWN race's units.
Players spawn IN an owned city (CITY child f5 = owner) or NEAR an independent city
of their own race — same rolled size for everyone. No small-island starts (< 25
land hexes) except Lizardmen; Dwarves/Dark Elves/Goblins may start on L1 or the
depths. Root 21 player records come from Slugfest 12P with f30 replaced by the
constructed leader; gold scales as 3000/N.

Usage: py "patch scripts/mapgen/generate_map_v4.py" [seed] [S|M|L|XL] [players 1-12]
  (player count omitted -> rolled per size, see _PDIST; races are a random
   no-duplicate draw from all 12 either way — v4.22)

v6.0 (2026-08-04): version renumbered for the AoWxGen portable release; maps are
  named xGen6/xImg6. Includes the shipyard dock-axis rule, dirt-skin fallback,
  and the v4.25 preset/levels/landmass options below.

v4.24 CROSS-LEVEL TERRAIN (Mirrored Oasis of Nathyazik / Athendore style):
  10% of maps put UG terrain on the surface (dirt fields, rare UG-water pond);
  15% put a little surface terrain underground (sunlit pockets at entrances);
  10% open whole UG levels into surface worlds (depths join in 50% of those).
  Engine-safe: Land() treats terrains 1-5/12 as land anywhere; wet stays
  {0,6,9,10,13}. Force with AOW_XLEVEL=dirt,limited|full.
"""
import struct, zlib, random, sys, os, pickle, heapq

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else random.randrange(1 << 30)
SIZE = (sys.argv[2].upper() if len(sys.argv) > 2 else 'S')
NPLAYERS = (max(1, min(12, int(sys.argv[3]))) if len(sys.argv) > 3 else None)

# v4.22: player count rolled per size when not given on the CLI (user spec):
#   S:  40% 2p, 30% 3p, 10% 4p, 10% 5p, 10% spread over 6-12
#   M:  10% 2p, 15% 3p, 15% 4p, 20% 5p, 10% each 6/7/8p, 10% spread over 9-12
#   L:  5/10/15/15/15/5/10/5/10/5/5 % for 2..12p
#   XL: 50% 12p, 50% spread over 2-11
_PDIST = {
    'S':  (list(range(2, 13)), [40, 30, 10, 10] + [10 / 7] * 7),
    'M':  (list(range(2, 13)), [10, 15, 15, 20, 10, 10, 10] + [10 / 4] * 4),
    'L':  (list(range(2, 13)), [5, 10, 15, 15, 15, 5, 10, 5, 10, 5, 5]),
    'XL': (list(range(2, 13)), [5] * 10 + [50]),
}
HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = {
    'S':  'Scenario/Custom/xTemplate Small.hsm',
    'M':  'Scenario/Custom/xTemplate Medium.hsm',
    'L':  'Scenario/Custom/xTemplate Large.hsm',
    'XL': 'Scenario/Custom/xTemplate XLarge.hsm',
}
TEMPLATE = TEMPLATES.get(SIZE, TEMPLATES['S'])
if not os.path.exists(TEMPLATE):
    raise SystemExit('Missing template for size %s: %s' % (SIZE, TEMPLATE))
OUT = 'Scenario/Custom/xGen6 %s.hsm' % SIZE

# image mode (driven by image_to_map.py): terrain/veg/mtn come from a picture, all
# gen5 features (objects, roads, bridges, ice, caves, teleporters) run on top
IMG_OV = None
if os.environ.get('AOW_IMG_OVERRIDE'):
    IMG_OV = pickle.load(open(os.environ['AOW_IMG_OVERRIDE'], 'rb'))
    OUT = 'Scenario/Custom/xImg6 %s.hsm' % SIZE

# diagnostic toggles (comma-separated in AOW_DBG):
#   nolib      — keep the template's default library leader entries, don't append ours
#   donorunits — party units = verbatim AtF donor records instead of constructed ones
DBG = set(filter(None, os.environ.get('AOW_DBG', '').split(',')))

# v4.25 (portable-generator options, all optional env vars):
#   AOW_LEVELS   = 1 surface only | 2 +underground | 3 +depths        (default 3)
#   AOW_LANDMASS = classic | isles (many small islands) | continents  (default classic)
#   AOW_TPRESET  = classic | grasslands | woodlands | arctic | desert | highlands
#                  | marshlands | desolate | apocalyptic              (default classic)
# v6.2:
#   AOW_TPRESET  may be a comma list of up to 3 non-classic presets (e.g.
#                "woodlands,arctic,highlands") — the surface is split into
#                contiguous style regions, one per preset
#   AOW_TSTRENGTH = 1..9 preset strength (default 5 = the classic-at-5 values;
#                lower = subtler deviation from default terrain, higher = extreme)
try:
    LEVELS = max(1, min(3, int(os.environ.get('AOW_LEVELS', '3'))))
except ValueError:
    LEVELS = 3
LANDMASS = os.environ.get('AOW_LANDMASS', 'classic').lower()
_TP_NAMES = ('classic', 'grasslands', 'woodlands', 'arctic', 'desert',
             'highlands', 'marshlands', 'desolate', 'apocalyptic')
TPRESETS = []
for _p in os.environ.get('AOW_TPRESET', 'classic').lower().split(','):
    _p = _p.strip()
    if _p in _TP_NAMES and _p not in TPRESETS:
        TPRESETS.append(_p)
TPRESETS = TPRESETS[:3] or ['classic']
if 'classic' in TPRESETS:           # classic never combines
    TPRESETS = ['classic']
TPRESET = TPRESETS[0]               # single-preset paths keep using this name
try:
    TSTRENGTH = max(1, min(9, int(os.environ.get('AOW_TSTRENGTH', '5'))))
except ValueError:
    TSTRENGTH = 5
_K = TSTRENGTH / 5.0                # 5 = exactly the tuned-preset values
def _scv(thr):                      # climate threshold ~= coverage share
    return max(0.02, min(0.95, thr * _K))
def _sv(v5, neutral=1.0):           # scalar knob: scale deviation from neutral
    return neutral + (v5 - neutral) * _K
def _sq(q5):                        # blight QUANTILE cutoff: scale the coverage
    return max(0.50, min(0.985, 1.0 - (1.0 - q5) * _K))
if TPRESETS != ['classic']:
    print('terrain style: %s | strength %d%s'
          % (' + '.join(TPRESETS), TSTRENGTH,
             '' if TSTRENGTH != 5 else ' (default)'))

# v4.16 FIELD SEMANTICS (from AoWEPACK.dll disassembly, 2026-08-03):
#   unit/hero/leader f2 = ability BIT COUNT, f3 = ability bitmask of ceil(f2/8)
#     bytes (TCustomAbilityList.ReadWrite) — f2 is NOT the unit type!
#   unit f10 = u16 UNIT TYPE (TUnitResourceList index; engine raises
#     "unit resource missing (N)" if invalid; index space = Unitres cid blocks)
#   hero/leader f7 = u32 FACE INDEX (R_FACES.ILB via TFaceResourceList; the old
#     "f7 = XP" write gave every leader the same wrong portrait)
#   hero/leader f8 = HeroResourceIndex (HERORES child: race for heroes, 36+race
#     racial-leader entries for leaders), f24 = u32 EXPERIENCE, f22 = level,
#     f9 = legacy level fallback (only read when f24 == 0) — never written
#   unit f49/f96 enchant pair: the old hardcoded f96 was a TRUNCATED 0x202CF
#     sub-record (no caster name) -> editor access violation (xDiag F/H); fresh
#     units get NO enchant fields (xDiag G proved clean open without them)

VEGREC = {t: [bytes.fromhex(h) for h in v]
          for t, v in pickle.load(open(os.path.join(HERE, 'veg_records.pkl'), 'rb')).items()}
MTNREC = {t: [bytes.fromhex(h) for h in v]
          for t, v in pickle.load(open(os.path.join(HERE, 'mtn_records.pkl'), 'rb')).items()}
OBJ = pickle.load(open(os.path.join(HERE, 'obj_records.pkl'), 'rb'))
PLAYER_KIT = pickle.load(open(os.path.join(HERE, 'player_kit.pkl'), 'rb'))
AB_MASK = pickle.load(open(os.path.join(HERE, 'ab_masks.pkl'), 'rb'))

# v4.18: extra structures harvested from ALL official maps (harvest_extra.py):
# surface arena, blood shrine, more reflecting pools, shipyards (coastal).
_EXTRA = pickle.load(open(os.path.join(HERE, 'obj_extra.pkl'), 'rb'))
for _g, _lst in _EXTRA.items():
    OBJ[_g] = OBJ.get(_g, []) + _lst

# v4.19: STR_BLDM guilds (0x0441CED6 / 0x0DD559CF — mod-added variants) are
# UNWANTED (user). Only vanilla Builder's Guild spawns: STR_BLDG 0x0482CFBC
# (surface) and 0x039F9C6A (underground, via ug_building+pad1 in furnish()).
# Defensive filter in case a harvested record ever references the mod guids:
_BLDM = {0x0441CED6, 0x0DD559CF}
for _g in list(OBJ):
    if _g == '__ugveg__':
        continue
    OBJ[_g] = [e_ for e_ in OBJ[_g]
               if not any(g2 in _BLDM for _, g2 in e_.get('children', []))]
OBJ.pop('building2+pad1', None)

# v4.23: drop harvested entries carrying hex-attached EVENTS (0x2056C, 0x2056E
# Message Event). Events index the SOURCE map's root event/text data, which
# generated maps don't have — the editor dies with "Oh dear, it's the end...."
# + an EngineP.dpl access violation (seen: xImg5 San Andreas seed 106924).
# 0x20101/0x20131 share the TWINKGR marker gfx but are real structures — keep.
_EVENT_CLS = {0x2056C, 0x2056E}
for _g in list(OBJ):
    if _g == '__ugveg__':
        continue
    OBJ[_g] = [e_ for e_ in OBJ[_g]
               if not any(c_ in _EVENT_CLS for c_, _ in e_.get('children', []))]

def tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F; f = {}
    for _ in range(nb):
        f[dd[p]] = dd[p+1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from('<II', dd, p); f[t] = o; p += 8
    return f, p

def tbl_entry_pos(dd, p, want):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F
    for _ in range(nb):
        if dd[p] == want: return ('u8', p + 1)
        p += 2
    for _ in range(nd):
        if struct.unpack_from('<I', dd, p)[0] == want: return ('u32', p + 4)
        p += 8
    return None

# decor field-7 footprint slots -> axial offsets: slot 0 = center, 1..6 = ring 1,
# 7..18 = ring 2; direction order starts NORTH, clockwise (validated against all
# official maps: structures-inside-footprint minimized, and matches the editor's
# footprint highlight). Slot pair (0xFE,0xFE) = hex not covered.
_AXD = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)]   # N NE SE S SW NW
_SLOTS = [(0, 0)] + _AXD[:]
_q, _r = 0, -2
for _i in range(6):
    _wd = _AXD[(2 + _i) % 6]
    for _ in range(2):
        _SLOTS.append((_q, _r))
        _q += _wd[0]; _r += _wd[1]

def load_decor_meta():
    """GUID -> gfx filename, ILB frame index, and FOOTPRINT (field 7 slot mask) for
    decor (0x20167/0x20169) and hexagon variants (0x20153). Frame index (in field 10,
    after the gfx path) keys the ILB image table -> true pixel size."""
    import re
    d = open('Release/Release.hss', 'rb').read()
    root, base = tbl(d, 0x37); f5, b5 = tbl(d, base + root[5]); kids, kb = tbl(d, b5 + f5[1])
    order = sorted(kids.items(), key=lambda kv: kv[1])
    out, frm, foot = {}, {}, {}
    pat = re.compile(rb'[ -~]{3,}\.(?:ILB|BMP|ilb|bmp)')
    for i, (cid, off) in enumerate(order):
        end = order[i+1][1] if i+1 < len(order) else len(d) - kb
        cls = struct.unpack_from('<I', d, kb + off)[0]
        f, b1 = tbl(d, kb + off + 4)
        if 1 not in f: continue
        guid = struct.unpack_from('<I', d, b1 + f[1])[0]
        if cls in (0x20167, 0x20169, 0x20153):
            m = pat.search(d[kb+off:kb+end])
            if m:
                out[guid] = m.group(0).decode('latin1').lower()
                tail = d[kb + off + m.end():kb + end][:12]
                for o2 in range(max(0, len(tail) - 3)):
                    v = struct.unpack_from('<I', tail, o2)[0]
                    if v <= 40:
                        frm[guid] = v; break
        if 7 in f:      # footprints exist on ALL placeable classes (structures too)
            n = struct.unpack_from('<I', d, b1 + f[7])[0]
            if 1 <= n <= 100:
                fp = []
                for k in range(min(n, len(_SLOTS))):
                    a_, b_ = d[b1 + f[7] + 4 + 2*k], d[b1 + f[7] + 5 + 2*k]
                    if (a_, b_) != (0xFE, 0xFE):
                        fp.append(_SLOTS[k])
                foot[guid] = fp
    return out, frm, foot

def load_ilb_frames(path):
    """Widths of the images in an ILB (name-record scan: [len][name.BMP][w][h])."""
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

_ILB_CACHE = {}
def gfx_width(guid):
    """True pixel width of a decor guid's graphic (0 if not an ILB/unknown)."""
    g = decor_gfx.get(guid, '')
    if not g.endswith('.ilb'): return 0
    path = os.path.join('Images', *g.split('\\'))
    if path not in _ILB_CACHE:
        _ILB_CACHE[path] = load_ilb_frames(path)
    ws = _ILB_CACHE[path]
    if not ws: return 0
    fr = decor_frame.get(guid, 0)
    return ws[fr] if fr < len(ws) else max(ws)

def size_class(w):
    """Hex is ~60px wide. 60=1 hex, 93 spills a sliver, 125 covers ring 1,
    188 covers ring 1 + the two x±2 side hexes (and 2 hexes up)."""
    return 'S' if w <= 60 else 'M' if w <= 93 else 'L' if w <= 125 else 'XL'

def load_variants():
    d = open('Release/Release.hss', 'rb').read()
    root, base = tbl(d, 0x37); f5, b5 = tbl(d, base + root[5]); kids, kb = tbl(d, b5 + f5[1])
    var = {}
    for cid, off in sorted(kids.items()):
        cls = struct.unpack_from('<I', d, kb + off)[0]
        if cls not in (0x20153, 0x2073E): continue
        f, b1 = tbl(d, kb + off + 4)
        if 1 not in f or 7 not in f: continue
        if struct.unpack_from('<I', d, b1 + f[7])[0] != 1: continue
        var.setdefault(d[b1 + f[7] + 4], []).append((cls, struct.unpack_from('<I', d, b1 + f[1])[0]))
    for t in (0, 6):
        anim = [v for v in var.get(t, []) if v[0] == 0x2073E]
        if anim: var[t] = anim
    return var

def make_noise(w, h, rnd, octaves, base_cell):
    grids = []
    for o in range(octaves):
        cell = max(2.0, base_cell / (2 ** o))
        gw, gh = int(w / cell) + 3, int(h / cell) + 3
        grids.append((cell, [[rnd.random() for _ in range(gw)] for _ in range(gh)]))
    def sample(x, y):
        v, amp, tot = 0.0, 1.0, 0.0
        for cell, g in grids:
            fx, fy = x / cell, y / cell
            ix, iy = int(fx), int(fy)
            tx, ty = fx - ix, fy - iy
            tx = tx * tx * (3 - 2 * tx); ty = ty * ty * (3 - 2 * ty)
            a = g[iy][ix] + (g[iy][ix+1] - g[iy][ix]) * tx
            b = g[iy+1][ix] + (g[iy+1][ix+1] - g[iy+1][ix]) * tx
            v += (a + (b - a) * ty) * amp
            tot += amp; amp *= 0.5
        return v / tot
    return sample

rnd = random.Random(SEED)
if NPLAYERS is None:
    _pv, _pw = _PDIST.get(SIZE, _PDIST['S'])
    NPLAYERS = rnd.choices(_pv, weights=_pw)[0]
terr_var = load_variants()
decor_gfx, decor_frame, FOOT = load_decor_meta()
LAND_STATIC = {t: [v for v in terr_var[t] if v[0] == 0x20153] for t in terr_var}

raw = open(TEMPLATE, 'rb').read()
inner = bytearray(zlib.decompress(raw[5:]))
root, base = tbl(inner, 0x13)
kids, kb = tbl(inner, base + root[1])
csort = sorted(kids.items(), key=lambda x: x[1])
coff = kb + csort[0][1]
cf, cb = tbl(inner, coff + 4)
W, H = inner[cb + cf[3]], inner[cb + cf[4]]
lvls = sorted(tbl(inner, cb + cf[1])[0].items())
lk, lkb = tbl(inner, cb + cf[1])
loff = lkb + dict(lvls)[0]
lf, lb = tbl(inner, loff + 4)
s, e = lb + 2, lb + lf[1]

# instance-id allocator: read template's root-38 next-id counter (tag 10 = u32)
f38, b38 = tbl(inner, base + root[38])
ID_POS = b38 + f38[10]
next_id = struct.unpack_from('<I', inner, ID_POS)[0]
def fresh_id():
    global next_id
    next_id += 1
    return next_id - 1

# ---- player-start kit (v4.14): hero-library leaders, equal parties -----------------
# Race ids (HERORES cid order): 0 Human 1 Azrac 2 Lizard 3 Frostling 4 Elf 5 Halfling
# 6 Dwarf 7 Highmen 8 DarkElf 9 Orc 10 Goblin 11 Undead
KIT_PLAYERS = [[(t, bytes.fromhex(v)) for t, v in p] for p in PLAYER_KIT['players']]

# v4.22: RANDOM RACE LINEUP — the 12 Slugfest donor player records cover all 12
# races exactly once; draw NPLAYERS distinct races at random and pick each
# slot's donor record BY RACE (colors etc. ride along), restamping f18 = the
# new player number. Previously slots always used donors 1..N in order, so
# every same-count map had an identical race lineup (2p = always Human+Elf).
_donor_by_race = {}
for _dp in range(1, 13):
    _fd = dict(KIT_PLAYERS[_dp])
    _donor_by_race[_fd[2][0] if 2 in _fd else 0] = KIT_PLAYERS[_dp]
_lineup = rnd.sample(sorted(_donor_by_race), NPLAYERS)
KIT_PLAYERS = [KIT_PLAYERS[0]] + [
    [(t, bytes([i]) if t == 18 else v) for t, v in _donor_by_race[r]]
    for i, r in enumerate(_lineup, 1)]
LIB = PLAYER_KIT['heroes']              # template map's default 195-entry hero library
UNIT_STATS = PLAYER_KIT['unit_stats']   # Unitres: cid -> name/level/hp/move
RACE_BASE = PLAYER_KIT['race_base']     # race id -> 18-slot unit-block base
PARTY_SLOTS = PLAYER_KIT['party_slots'] # slots valid for all 12 races (0-3)
RACE_UG = {6, 8, 10}                    # Dwarf / Dark Elf / Goblin may start underground
RACE_SWIM = 2                           # Lizardmen may start on small islands

def player_race(p):
    fd = dict(KIT_PLAYERS[p])
    return fd[2][0] if 2 in fd else 0

def enc_tblhdr(pairs):
    """(tag, offset) pairs -> tbl header bytes (byte pairs while both fit, else dword)."""
    bp = [(t, o) for t, o in pairs if t <= 255 and o <= 255]
    dp = [(t, o) for t, o in pairs if not (t <= 255 and o <= 255)]
    out = bytearray([len(bp) | (0x80 if dp else 0)])
    if dp:
        out += struct.pack('<I', len(dp))
    for t, o in bp:
        out += bytes([t, o])
    for t, o in dp:
        out += struct.pack('<II', t, o)
    return bytes(out)

def enc_fields(fields):
    """ordered [(tag, payload)] -> [tbl][data]"""
    pairs, off = [], 0
    for t, v in fields:
        pairs.append((t, off)); off += len(v)
    return enc_tblhdr(pairs) + b''.join(v for _, v in fields)

def enc_record(cls, fields):
    return struct.pack('<I', cls - 1) + enc_fields(fields)

def parse_fields(dd, tbl_pos, end):
    f, fb = tbl(dd, tbl_pos)
    fo = sorted(f.items(), key=lambda kv: kv[1])
    out = []
    for j, (t, o) in enumerate(fo):
        st = fb + o
        en = fb + fo[j+1][1] if j+1 < len(fo) else end
        out.append((t, bytes(dd[st:en])))
    return out

def rec_children(rec):
    hdr, p0 = tbl(rec, 0)
    offs = sorted(o for t, o in hdr.items() if t >= 0x32)
    bounds = [p0 + o for o in sorted(hdr.values())] + [len(rec)]
    out = []
    for o in offs:
        cs = p0 + o
        ce = next(b_ for b_ in bounds if b_ > cs)
        out.append(bytes(rec[cs:ce]))
    return out

def build_hexrec(children):
    pairs, off = [], 0
    for i, c in enumerate(children):
        pairs.append((0x32 + i, off)); off += len(c)
    return enc_tblhdr(pairs) + b''.join(children)

def append_child(rec, childbytes):
    return build_hexrec(rec_children(rec) + [childbytes])

def city_set_owner(rec, owner):
    """Insert CITY-child field 5 = owning player (AtF order: ...,98,5,6,...)."""
    kids = rec_children(rec)
    out = []
    for ch in kids:
        cls = struct.unpack_from('<I', ch, 0)[0] + 1
        if cls == 0x20109:
            fl, fl2 = parse_fields(ch, 4, len(ch)), []
            for t, v in fl:
                fl2.append((t, v))
                if t == 98:
                    fl2.append((5, bytes([owner])))
            ch = enc_record(cls, fl2)
        out.append(ch)
    return build_hexrec(out)

# structural template: the map library's default leader entries carry the exact
# field set/sizes the editor's serializer expects (f7 = u32!, minimal fields,
# enchant-46 f49/f96 pair, f46 = empty 5B list). Clone it, substitute identity.
_LEADER_TPL = dict((t, bytes.fromhex(v))
                   for t, v in next(h for h in LIB if h['leaderlike'])['fields'])

def make_leader(h, race, xp, pnum):
    """Leader (cls 0x20233) = copy of a library hero, in TWO canonical shapes
    sharing one instance id:
      lib form  — minimal, exactly like the template's default library entries
                  (also used for player f30);
      stack form — rich, like AtF's placed leaders (Graham): + f16/f17,
                  f45=7, f46 = 12B current-stats blob.
    v4.16: f7 = u32 FACE (copied from the hero — that IS the hero's portrait
    field), f8 = HERORES racial-leader index 36+race, f24 = u32 EXPERIENCE,
    f22 = level 1, f2/f3 = the hero's ability count/mask. f47 = owner.
    v4.17: the hero's f49 ability-data id list and its 12B sub-records at tag
    id+50 (which hold each multilevel ability's LEVEL, e.g. Spellcasting=52 ->
    f102) are copied and merged with the template's Leadership pair (id 46 ->
    f96) — dropping them left copied multilevel abilities unleveled."""
    fd = dict((t, bytes.fromhex(v)) for t, v in h['fields'])
    uid = struct.pack('<I', fresh_id())
    ids = [46]
    subs = [(96, _LEADER_TPL[96])]                   # Leadership I data
    if 49 in fd:
        n_ = struct.unpack_from('<I', fd[49], 4)[0]
        for hid in struct.unpack_from('<%dI' % n_, fd[49], 8):
            if hid == 46:
                continue
            ids.append(hid)
            if 50 + hid in fd:
                subs.append((50 + hid, fd[50 + hid]))
    f49 = struct.pack('<II', 0, len(ids)) + struct.pack('<%dI' % len(ids), *ids)
    cnt = struct.unpack('<I', fd[2])[0]              # extend mask to cover bit 46
    mask = bytearray(fd[3])
    if cnt < 47:
        cnt = 47
        mask += bytes(6 - len(mask))
    mask[46 // 8] |= 1 << (46 % 8)
    head = [(8, struct.pack('<I', 36 + race)),       # HERORES racial leader
            (2, struct.pack('<I', cnt)),             # ability bit count (u32)
            (3, bytes(mask)),                        # ability mask (variable)
            (49, f49)] + sorted(subs) + [
            (5, uid),
            (6, b'\x5a'),
            (47, bytes([pnum]))]
    if 7 in fd:                                      # face index (u32)
        head.append((7, fd[7][:4].ljust(4, b'\x00')))
    head.append((10, fd[10]))
    race_f = [(12, bytes([race]))] if race else []   # absent = race 0 ("Human")
    lvl = fd.get(22, b'\x01')[:1]                    # leader level = hero's level
    lib = head + race_f + [
        (15, fd.get(15, b'\x00')),
        (22, lvl),
        (24, struct.pack('<I', xp)),                 # experience
        (25, b'\x00'),
        (36, fd.get(36, b'\x01\x01\x00\x00')),
        (37, fd.get(37, b'\x01\x01\x00\x00')),
        (46, _LEADER_TPL[46])]                       # empty current-stats list
    stack = head + race_f + [
        (15, fd.get(15, b'\x00')),
        (16, fd.get(16, b'\x02')),
        (17, fd.get(17, b'\x01')),
        (22, lvl),
        (24, struct.pack('<I', xp)),                 # experience
        (25, b'\x00'),
        (36, fd.get(36, b'\x01\x01\x00\x00')),
        (37, fd.get(37, b'\x01\x01\x00\x00')),
        (45, b'\x07'),
        (46, bytes.fromhex('000700000003030303040401'))]
    return enc_record(0x20233, lib), enc_record(0x20233, stack)

def hero_stack_rec(h, xp, pnum):
    """A library hero placed into a stack: + instance id / hp / owner / XP.
    v4.16: lib f7 (FACE index) is kept VERBATIM — XP goes to f24 (u32),
    inserted after f22 (level) per THero.ReadWrite property order."""
    out = []
    got24 = False
    for t, v in ((t, bytes.fromhex(v)) for t, v in h['fields']):
        if t == 35:
            continue                                  # library ordinal
        if t == 24:                                   # pre-leveled lib hero
            v = struct.pack('<I', xp)
            got24 = True
        if t in (36, 37) and not got24:
            out.append((24, struct.pack('<I', xp)))   # XP goes before f36
            got24 = True
        out.append((t, v))
        if t == 3:
            out += [(5, struct.pack('<I', fresh_id())),
                    (6, b'\x32'), (47, bytes([pnum]))]
    return enc_record(0x20231, out)

# sanity probe: constructed leaders must match the canonical shapes (tag order +
# fixed field sizes) — a size drift here access-violates the editor/army code.
_pl_, _ps_ = make_leader(next(h for h in LIB if not h['leaderlike']
                              and h['race'] == 1
                              and any(t == 7 for t, _ in h['fields'])), 1, 30, 1)
# canonical tag order (ability-data tags 49/52+ float between f3 and f5 and are
# checked only for consistency: every f49-listed id may carry a sub-record)
_CORE_L = [8, 2, 3, 5, 6, 47, 7, 10, 12, 15, 22, 24, 25, 36, 37, 46]
_CORE_S = [8, 2, 3, 5, 6, 47, 7, 10, 12, 15, 16, 17, 22, 24, 25, 36, 37, 45, 46]
_FIXED = {8: 4, 2: 4, 5: 4, 6: 1, 47: 1, 7: 4, 12: 1, 15: 1, 16: 1, 17: 1,
          22: 1, 24: 4, 25: 1, 36: 4, 37: 4, 45: 1}
for _rec, _core_, _sz46 in ((_pl_, _CORE_L, 5), (_ps_, _CORE_S, 12)):
    _pf_ = parse_fields(_rec, 4, len(_rec))
    _fd_ = dict(_pf_)
    assert [t for t, _ in _pf_ if t in set(_core_)] == _core_, [t for t, _ in _pf_]
    assert len(_fd_[46]) == _sz46, len(_fd_[46])
    for _t, _v in _pf_:
        assert _t not in _FIXED or len(_v) == _FIXED[_t], (_t, len(_v))
    _n49 = struct.unpack_from('<I', _fd_[49], 4)[0]
    assert len(_fd_[49]) == 8 + 4 * _n49
    for _t in _fd_:
        if _t >= 52:
            assert len(_fd_[_t]) == 12, (_t, len(_fd_[_t]))
    _cnt_ = struct.unpack('<I', _fd_[2])[0]
    assert len(_fd_[3]) == (_cnt_ + 7) // 8, (_cnt_, len(_fd_[3]))
del _pl_, _ps_, _pf_, _fd_

def make_unit(ty, pnum):
    """Party unit of type `ty` (v4.16). f10 = u16 UNIT TYPE — the field the
    engine resolves the type from (the old f10=0 made EVERY party unit a Human
    Archer). f2 = ability bit count, f3 = ability bitmask (ceil(f2/8) bytes):
    verbatim official per-type mask (ab_masks.pkl) when harvested, else slot
    fallback (0 walking + 22 archery / 20+47 priest / 21 melee / 111 charge).
    f8/f9 = move/hp from Unitres. NO enchant f49/f96 — the old hardcoded f96
    was a truncated 0x202CF sub-record and access-violated the editor."""
    st = UNIT_STATS[ty]
    ab = AB_MASK.get(ty)
    if ab is None:
        sl = ty % 18 if ty < 216 else 3
        ab = {0: [0, 22], 1: [0, 20, 47], 2: [0, 21, 111]}.get(sl, [0, 21])
    mask = bytearray(max(ab) // 8 + 1)
    for b_ in ab:
        mask[b_ // 8] |= 1 << (b_ % 8)
    fields = [(2, struct.pack('<I', max(ab) + 1)),
              (3, bytes(mask)),
              (5, struct.pack('<I', fresh_id())),
              (6, b'\x32'),
              (47, bytes([pnum])),
              (8, bytes([st['move']])),
              (9, bytes([st['hp']])),
              (10, struct.pack('<H', ty))]
    return enc_record(0x20214, fields)

def build_stack(owner, x, y, unit_recs):
    """0x20218 stack child: nested header + unit child table."""
    pairs, off = [], 0
    for i, u in enumerate(unit_recs):
        pairs.append((i, off)); off += len(u)
    unit_table = enc_tblhdr(pairs) + b''.join(unit_recs)
    hdr = [(4, bytes([owner])), (5, bytes([x & 0xFF])), (6, bytes([y & 0xFF])),
           (7, b'\x01'), (8, b'\xff'), (9, b'\xff'), (10, b'\xff'),
           (13, b'\x00'), (11, b'\x00'), (12, b'\x00'), (1, unit_table)]
    return enc_record(0x20218, [(9, b'\x03'), (10, enc_fields(hdr))])

# ---- terrain / veg / mtn (v3 verbatim; v4.25 landmass + terrain presets) ----
SCALE = W / 48.0
# landmass preset: elev noise cell size — smaller cells fragment the land into
# archipelagos, bigger cells merge it into a few continents. SEA is set by
# QUANTILE after the paint mask is known (fixed cutoffs + huge noise cells
# rolled near-all-ocean maps: continents-S 918298 had 13 veg hexes total).
# v6.5 user tune: classic was fragmenting into archipelagos with big oceans.
# It should read as ONE giant landmass cut by large rivers, with real seas only
# some of the time — so the cells grow (land coheres) while the water SHARE
# drops and the river budget rises (see _WQ and _LM_RIV below).
_LM = {'classic': 28.0, 'isles': 9.0, 'continents': 34.0}
_lmc = _LM.get(LANDMASS, _LM['classic'])
SEA = 0.42          # placeholder; finalized right after the paint mask below
elev = make_noise(W, H, rnd, 4, _lmc * SCALE)
clim = make_noise(W, H, rnd, 2, 30.0 * SCALE)
blight = make_noise(W, H, rnd, 2, 16.0 * SCALE)
# v6.2: combined presets — a coarse style field carves the land into one
# contiguous-ish region per preset (equal areas by quantile, cut after the paint
# mask is known). Only rolled for combos so single-preset seeds stay stable.
styn = make_noise(W, H, rnd, 2, 24.0 * SCALE) if len(TPRESETS) > 1 else None
# preset thresholds by QUANTILE of the actual blight histogram — fixed cutoffs
# miss entirely on noise instances whose range runs low (zero-lava apocalyptic)
_bvals = sorted(blight(x, y) for y in range(0, H, 2) for x in range(0, W, 2))
def _bq(q):
    return _bvals[min(len(_bvals) - 1, int(len(_bvals) * q))]
def base_terrain(x, y):
    ev = elev(x, y)
    if ev < SEA: return 0
    bv = blight(x, y)
    cv = clim(x, y)
    tp = PAT(x, y)
    if tp == 'grasslands':      # sparse fertile plains
        return 4 if cv < _scv(0.28) else 1
    if tp == 'woodlands':       # (density comes from the veg pass)
        return 4 if cv < _scv(0.22) else 1
    if tp == 'arctic':          # snow + frozen tundra
        return 3 if cv < _scv(0.58) else (4 if cv < _scv(0.75) else 1)
    if tp == 'desert':          # strength grows the DESERT share (thr shrinks)
        return 4 if cv < max(0.02, min(0.95, 0.22 * (2.0 - _K))) else 2
    if tp == 'highlands':       # rock and moor (mountains come later)
        if bv > _bq(_sq(0.92)): return 5
        return 3 if cv < _scv(0.25) else (4 if cv < _scv(0.55) else 1)
    if tp == 'marshlands':      # mud (UG dirt on the surface) + stagnant pools
        # v6.3 user tune: wider pool band (0.09->0.14 coverage) = more small lakes
        if bv > _bq(_sq(0.74)): return 12
        if bv > _bq(max(0.50, 1.0 - 0.40 * _K)): return 0
        return 4 if cv < 0.25 else 1
    if tp == 'desolate':
        if bv > _bq(_sq(0.88)): return 12
        return 5 if cv < _scv(0.55) else 4
    if tp == 'apocalyptic':     # waste + open lava fields
        if bv > _bq(_sq(0.82)): return 9
        return 5 if cv < _scv(0.60) else (2 if cv > 0.85 else 4)
    # classic
    if bv > 0.80: return 9 if bv > 0.93 else 5
    if cv < 0.33: return 3
    if cv < 0.44: return 4
    if cv > 0.72: return 2
    return 1

paint = [[False] * W for _ in range(H)]
q, idx = s, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    if L == 14 and struct.unpack_from('<H', inner, q + 4 + 3)[0] != 0x0557:
        paint[idx // W][idx % W] = True
    q += 4 + L; idx += 1

# v4.25: sea level by quantile of the actual elevation histogram over the
# paintable area — water share is then a controlled roll per landmass preset
_evals = sorted(elev(x, y) for y in range(H) for x in range(W) if paint[y][x])
_WQ = {'classic': (0.28, 0.44), 'isles': (0.38, 0.55), 'continents': (0.26, 0.44)}
if _evals:
    if LANDMASS == 'classic':
        # v6.5: BIMODAL instead of one flat range, so "sometimes oceans but not
        # always" is actually visible seed to seed rather than averaging out:
        #   ~55% river-continent (barely any open sea)
        #   ~45% a genuine ocean, but still far below the old 28-44% flood.
        _wlo, _whi = (0.09, 0.19) if rnd.random() < 0.55 else (0.21, 0.32)
    else:
        _wlo, _whi = _WQ.get(LANDMASS, _WQ['classic'])
    SEA = _evals[min(len(_evals) - 1, int(len(_evals) * rnd.uniform(_wlo, _whi)))]

# v6.2: PAT(x, y) = the terrain style preset governing this hex. Combos cut the
# style field into equal-area regions (quantiles over the painted hexes).
if styn is not None:
    _stv = sorted(styn(x, y) for y in range(H) for x in range(W)
                  if paint[y][x]) or [0.0]
    _stcuts = [_stv[min(len(_stv) - 1, (len(_stv) * i) // len(TPRESETS))]
               for i in range(1, len(TPRESETS))]
    def PAT(x, y):
        v = styn(x, y)
        for _i, _c in enumerate(_stcuts):
            if v < _c: return TPRESETS[_i]
        return TPRESETS[-1]
else:
    def PAT(x, y): return TPRESET

if IMG_OV:
    og = IMG_OV['grid']
    grid = [[(og[y][x] if og[y][x] is not None else 1) if paint[y][x] else None
             for x in range(W)] for y in range(H)]
else:
    grid = [[(base_terrain(x, y) if paint[y][x] else None)
             for x in range(W)] for y in range(H)]

def smooth(g):
    ng = [row[:] for row in g]
    for y in range(H):
        for x in range(W):
            t = g[y][x]
            if t is None: continue
            cnt = {}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and g[ny][nx] is not None:
                        cnt[g[ny][nx]] = cnt.get(g[ny][nx], 0) + (2 if dx == 0 and dy == 0 else 1)
            ng[y][x] = max(cnt, key=cnt.get)
    return ng
if not IMG_OV:                  # image terrain keeps its pixel-accurate detail
    for _ in range(2):
        grid = smooth(grid)

# hex-grid helpers (adjacency inferred from AtF road offsets: column parity — even x
# also neighbors (x±1, y-1), odd x also neighbors (x±1, y+1))
def hexn(x, y):
    out = [(x, y-1), (x, y+1), (x-1, y), (x+1, y)]
    out += [(x-1, y-1), (x+1, y-1)] if x % 2 == 0 else [(x-1, y+1), (x+1, y+1)]
    return [(nx, ny) for nx, ny in out if 0 <= nx < W and 0 <= ny < H]

def hexdist(a, b):
    # offset -> axial: q = x, r = y - x//2 (verified against the adjacency scheme)
    q1, r1 = a[0], a[1] - a[0] // 2
    q2, r2 = b[0], b[1] - b[0] // 2
    dq, dr = q1 - q2, r1 - r2
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2

def hexline(a, b):
    """Interior hexes of the straight line a->b (cube lerp + rounding)."""
    q1, r1 = a[0], a[1] - a[0] // 2
    q2, r2 = b[0], b[1] - b[0] // 2
    n = max(1, hexdist(a, b))
    out = []
    for i in range(1, n):
        t_ = i / n
        xx = q1 + (q2 - q1) * t_
        zz = r1 + (r2 - r1) * t_
        yy = -xx - zz
        rx, ry, rz = round(xx), round(yy), round(zz)
        if abs(rx - xx) > abs(ry - yy) and abs(rx - xx) > abs(rz - zz): rx = -ry - rz
        elif abs(rz - zz) > abs(ry - yy): rz = -rx - ry
        col = int(rx); row = int(rz) + col // 2
        out.append((col, row))
    return out

# canonical hex direction 0..5 (N NE SE S SW NW), parity-aware
def dirid(x, y, nx, ny):
    dx, dy = nx - x, ny - y
    if dx == 0: return 0 if dy == -1 else 3
    if x % 2 == 0:
        return {(1, -1): 1, (1, 0): 2, (-1, 0): 4, (-1, -1): 5}[(dx, dy)]
    return {(1, 0): 1, (1, 1): 2, (-1, 1): 4, (-1, 0): 5}[(dx, dy)]

def nbr_dirs(x, y):
    """All 6 neighbors in direction order N NE SE S SW NW (may fall off-map)."""
    if x % 2 == 0:
        return [(x, y-1), (x+1, y-1), (x+1, y), (x, y+1), (x-1, y), (x-1, y-1)]
    return [(x, y-1), (x+1, y), (x+1, y+1), (x, y+1), (x-1, y+1), (x-1, y)]

def bridgeable(x, y):
    """Engine rule (THexagonBridge.DirectionValid): a bridge needs SOME opposite-
    neighbor axis with LAND terrain on both ends, else it loads with direction -1
    and THexagonBridge.Show crashes (ImageLib.Get(-1) -> garbage vtable). Found the
    hard way: editor EAccessViolation on a road bridge over a jagged lake neck.
    AoWE.Land() (disasm): NOT land = {0 water, 6 ice, 9 lava, 10 UG water, 13 UG ice}."""
    nb = nbr_dirs(x, y)
    def landt(q_):
        qx, qy = q_
        return (0 <= qx < W and 0 <= qy < H and paint[qy][qx]
                and grid[qy][qx] not in (None, 0, 6, 9, 10, 13))
    return any(landt(nb[d_]) and landt(nb[d_ + 3]) for d_ in range(3))

def foot_cells(x, y, fp):
    """On-map hexes covered by a footprint mask anchored at (x, y)."""
    q0, r0 = x, y - x // 2
    out = []
    for dq, dr in fp:
        tx = q0 + dq
        ty = r0 + dr + tx // 2
        if 0 <= tx < W and 0 <= ty < H:
            out.append((tx, ty))
    return out

# ---- rivers: high ground -> sea; width varies (mostly 1 hex, occasional wider
# stretches that narrow back down — the 1-wide points are where bridges can cross).
# Winding like roads: short straight runs are free, continuing one costs extra, and a
# slow meander-noise field drifts the course sideways.
mnoise = make_noise(W, H, rnd, 2, 9.0 * SCALE)
def flow_river(sx, sy):
    cur, seen, path = (sx, sy), {(sx, sy)}, []
    lastd, run = None, 0
    for _ in range(W * 3):
        path.append(cur)
        if grid[cur[1]][cur[0]] == 0: break          # merged into sea/another river
        opts = []
        for q_ in hexn(*cur):
            if q_ in seen or not paint[q_[1]][q_[0]] or grid[q_[1]][q_[0]] is None:
                continue
            d_ = dirid(cur[0], cur[1], q_[0], q_[1])
            pen = 0.0
            if d_ == lastd and run >= 2: pen += 0.06 * (run - 1)   # forced meander
            if lastd is not None and (d_ - lastd) % 6 == 3: pen += 0.10  # soft no-hairpin
            wob = (mnoise(*q_) - 0.5) * 0.12
            opts.append((elev(*q_) + wob + pen + rnd.random() * 0.05, q_, d_))
        if not opts: break
        opts.sort()
        _, nq, nd = opts[0]
        run = run + 1 if nd == lastd else 1
        lastd = nd
        seen.add(nq); cur = nq
    return path

river = set()
sources = []
_RIVD = {'grasslands': 1.6, 'marshlands': 2.0, 'desert': 0.4, 'apocalyptic': 0.4}
_RIV_SCALE = sum(_sv(_RIVD.get(p, 1.0)) for p in TPRESETS) / len(TPRESETS)
# v6.5: classic now carries most of its water as RIVERS, so it gets a bigger
# river budget and lets sources sit closer together (the >12 spacing capped the
# count well below the budget on anything but XL). Other presets unchanged.
_LM_RIV = {'classic': 2.2}
_LM_SEP = {'classic': 9}
_WIDE_P = 0.20 if LANDMASS == 'classic' else 0.12   # chance a stretch widens
_WIDE_L = 7 if LANDMASS == 'classic' else 6         # how long a wide stretch runs
if not IMG_OV:                  # the picture already defines the waterways
    n_riv = max(2, int((W * H) // 1300 * _RIV_SCALE
                       * _LM_RIV.get(LANDMASS, 1.0))) + rnd.randrange(0, 3)
    _sep = _LM_SEP.get(LANDMASS, 12)
    src_cand = sorted(((elev(x, y), x, y) for y in range(H) for x in range(W)
                       if paint[y][x] and grid[y][x] not in (None, 0, 9)
                       and elev(x, y) > SEA + 0.12), reverse=True)
    for ev_, x, y in src_cand:
        if len(sources) >= n_riv: break
        if all(hexdist((x, y), s_) > _sep for s_ in sources): sources.append((x, y))
for (sx, sy) in sources:
    rpath = flow_river(sx, sy)
    if len(rpath) < 7: continue
    wide, ww = 0, 1
    for i, p in enumerate(rpath):
        river.add(p)
        if wide > 0:
            adds = sorted((q_ for q_ in hexn(*p)
                           if paint[q_[1]][q_[0]] and grid[q_[1]][q_[0]] not in (None, 0)),
                          key=lambda q_: elev(*q_))
            for q_ in adds[:ww]: river.add(q_)
            wide -= 1
        elif rnd.random() < _WIDE_P and 3 < i < len(rpath) - 4:
            wide = rnd.randrange(2, _WIDE_L)         # widened stretch, then back to 1
            if LANDMASS == 'classic':
                # v6.5: "large rivers" — wider and more often, but still always
                # narrowing back to 1 hex in between, because those single-hex
                # points are the ONLY places a bridge/road may cross.
                _r = rnd.random()
                ww = 1 if _r < 0.45 else (2 if _r < 0.85 else 3)
            else:
                ww = 1 if rnd.random() < 0.7 else 2
    last = rpath[-1]
    if grid[last[1]][last[0]] != 0:                  # landlocked: end in a small lake
        for q_ in hexn(*last):
            if paint[q_[1]][q_[0]] and grid[q_[1]][q_[0]] is not None and rnd.random() < 0.6:
                river.add(q_)
for (x, y) in river:
    grid[y][x] = 0

# lava must never touch water: demote shoreline lava to wasteland
for y in range(H):
    for x in range(W):
        if grid[y][x] == 9:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] == 0:
                        grid[y][x] = 5; break
                else:
                    continue
                break

# ---- ice (terrain 6): freeze water near snow — river stretches, lakes, shore
# fringes — while leaving gaps of open water. Ice is NOT land (AoWE.Land) and not
# buildable; roads may cross 1-hex ice via ice bridges (0x56D135E).
icef = make_noise(W, H, rnd, 2, 7.0 * SCALE)
nice = 0
for y in range(H):
    for x in range(W):
        if grid[y][x] != 0 or not paint[y][x]: continue
        sn = ln = 0
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] not in (None, 0, 6, 9):
                    ln += 1
                    if grid[ny][nx] == 3: sn += 1
        if not ln: continue
        frac = sn / ln
        # arctic preset: ice forms far more readily (user: "abundant snow and ice")
        _im, _ib = ((max(0.02, _sv(0.08, 0.22)), _sv(2.0, 1.35))
                    if PAT(x, y) == 'arctic' else (0.22, 1.35))
        if frac > _im and icef(x, y) < frac * _ib - 0.14:
            grid[y][x] = 6
            nice += 1

# ---- v4.24: CROSS-LEVEL TERRAIN (Mirrored Oasis of Nathyazik / Athendore style) --
# Three independent looks, official-map calibrated:
#   SURF_DIRT (10% of maps): UG terrain on the SURFACE — dirt fields (50-500 hexes
#     in Desolate Maugogom / Hamardis Citadel / Spice Archipelago), rarely with a
#     small UG-water pond inside (Athendore/Resurrection use 6-11 hexes of terr 10).
#   UG_SURF 'limited' (15%): sunlit pockets — surface terrain seeps onto the cave
#     floor around entrances, plus a little real vegetation.
#   UG_SURF 'full' (10%): whole UG levels open into surface WORLDS (rock survives
#     only as noise ridges; biomes + UG-water lakes + veg/hill dressing).
# AOW_XLEVEL=dirt / limited / full (comma-separated) forces modes; 'off' disables.
_XL = set(filter(None, os.environ.get('AOW_XLEVEL', '').split(',')))
if _XL:
    SURF_DIRT = 'dirt' in _XL
    UG_SURF = ('full' if 'full' in _XL else
               'limited' if 'limited' in _XL else None)
else:
    SURF_DIRT = rnd.random() < 0.10
    _r = rnd.random()
    UG_SURF = 'limited' if _r < 0.15 else ('full' if _r < 0.25 else None)
SURF_DIRT = SURF_DIRT and not IMG_OV      # the picture owns an image map's surface
ndirt = npond = 0
if SURF_DIRT:
    landish = [(x, y) for y in range(H) for x in range(W)
               if paint[y][x] and grid[y][x] in (1, 2, 3, 4, 5)]
    tgt = max(30, int(len(landish) * rnd.uniform(0.02, 0.05)))
    nblob = rnd.randrange(2, 6 if len(landish) > 6000 else 5)
    for _ in range(nblob):
        if ndirt >= tgt or not landish: break
        seed_ = rnd.choice(landish)
        blob = {seed_}; frontier = [seed_]
        bt = max(12, tgt // nblob)
        while len(blob) < bt and frontier:
            b_ = rnd.choice(frontier)
            opts = [p for p in hexn(*b_)
                    if 0 <= p[0] < W and 0 <= p[1] < H and paint[p[1]][p[0]]
                    and grid[p[1]][p[0]] in (1, 2, 3, 4, 5) and p not in blob]
            if not opts:
                frontier.remove(b_); continue
            p2 = rnd.choice(opts)
            blob.add(p2); frontier.append(p2)
        for (x, y) in blob:
            grid[y][x] = 12
        ndirt += len(blob)
        if rnd.random() < 0.35 and len(blob) >= 20:   # rare interior UG-water pond
            interior = [p for p in blob if all(q_ in blob for q_ in hexn(*p))]
            if interior:
                c0 = rnd.choice(interior)
                for p in [c0] + [q_ for q_ in hexn(*c0) if q_ in interior]:
                    if rnd.random() < 0.75:
                        grid[p[1]][p[0]] = 10; npond += 1

forest = make_noise(W, H, rnd, 3, 8.0 * SCALE)
DENSITY = {1: 0.70, 3: 0.66, 4: 0.62, 2: 0.36, 5: 0.78, 12: 0.62}
def edge_hex(x, y, t):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dx or dy): continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] is not None and grid[ny][nx] != t:
                return True
    return False

buckets = {}
for y in range(H):
    for x in range(W):
        t = grid[y][x]
        if t is None or not VEGREC.get(t) or t in (0, 9): continue
        buckets.setdefault((t, PAT(x, y)), []).append((forest(x, y), x, y))
veg = [[False] * W for _ in range(H)]
if IMG_OV:                      # forests exactly where the picture is dark green
    for (x, y) in IMG_OV.get('veg', ()):
        t = grid[y][x]
        if paint[y][x] and t not in (None, 0, 6, 9) and VEGREC.get(t):
            veg[y][x] = True
else:
    _VSD = {'grasslands': 0.45, 'woodlands': 1.40, 'desert': 0.55,
            'desolate': 0.65, 'marshlands': 1.15, 'apocalyptic': 0.60,
            'arctic': 0.85}
    for (t, _tp), cells in buckets.items():
        cells.sort(reverse=True)
        take = int(len(cells) * min(0.95, DENSITY.get(t, 0.5)
                                    * _sv(_VSD.get(_tp, 1.0))))
        for i, (fv, x, y) in enumerate(cells):
            if i < take and not (edge_hex(x, y, t) and rnd.random() < 0.3):
                veg[y][x] = True

# ---- mountains: mix of standalone peaks and short stacked chains. Official maps run
# 35-48% isolated mountain hexes with clusters mostly pairs/triples — never the dense
# blobs a plain noise threshold produces. Cluster sizes sampled, grown along the ridge.
ridge = make_noise(W, H, rnd, 3, 11.0 * SCALE)
_MTND = {'highlands': 2.3, 'grasslands': 0.55, 'woodlands': 0.7,
         'marshlands': 0.45, 'apocalyptic': 1.3}
_MFRAC = {p: 0.14 * _sv(_MTND.get(p, 1.0)) for p in TPRESETS}
mtn = [[False] * W for _ in range(H)]
def mscore(x, y): return elev(x, y) * 0.6 + ridge(x, y) * 0.4
# apocalyptic: volcanos may rise from the lava itself (official maps carry
# harvested mountain records ON terrain 9 — 5 wl_volc* instances)
def _mban(x, y, t):
    return t == 0 or (t == 9 and PAT(x, y) != 'apocalyptic')
mcells = []
for y in range(H):
    for x in range(W):
        t = grid[y][x]
        if t is None or not MTNREC.get(t) or _mban(x, y, t): continue
        mcells.append((mscore(x, y) + rnd.random() * 0.05, x, y, t))
mcells.sort(reverse=True)
# per-region targets so a highlands region is mountainous while its woodlands
# neighbor stays gentle (single preset = one region = the old global target)
_zcnt = {}
for _sc, x, y, _t in mcells:
    _zp = PAT(x, y); _zcnt[_zp] = _zcnt.get(_zp, 0) + 1
ztarget = {p: int(_zcnt.get(p, 0) * _MFRAC[p]) for p in TPRESETS}
znm = {p: 0 for p in TPRESETS}
target_m = sum(ztarget.values())
mtnset = set()
def m_ok(q_):
    x, y = q_
    if not (0 <= x < W and 0 <= y < H) or not paint[y][x]: return False
    t = grid[y][x]
    return t is not None and not _mban(x, y, t) and bool(MTNREC.get(t))
# fewer lone singles, more substantial ranges (user: scattered mountains felt noisy)
CLUSTER_SIZES = [1] * 50 + [2] * 20 + [3] * 12 + [4] * 7 + [5] * 4 + [6] * 3 + [7, 8] * 2
nm = 0
if IMG_OV:                      # ranges exactly where the picture is brown
    for p in IMG_OV.get('mtn', ()):
        if m_ok(p) and p not in mtnset:
            mtnset.add(p); nm += 1
else:
    for score, x, y, t in mcells:
        if nm >= target_m: break
        _zp = PAT(x, y)
        if znm.get(_zp, 0) >= ztarget.get(_zp, 0): continue
        p = (x, y)
        if p in mtnset or any(q_ in mtnset for q_ in hexn(x, y)): continue
        cur = p; cluster = {p}; mtnset.add(p); nm += 1
        znm[_zp] = znm.get(_zp, 0) + 1
        for _ in range(rnd.choice(CLUSTER_SIZES) - 1):
            # never grow onto a hex touching ANOTHER cluster — keeps them distinct
            opts = [q_ for q_ in hexn(*cur) if m_ok(q_) and q_ not in mtnset
                    and all(r_ in cluster or r_ not in mtnset for r_ in hexn(*q_))]
            if not opts: break
            opts.sort(key=lambda q_: -(mscore(*q_) + rnd.random() * 0.3))
            cur = opts[0]; cluster.add(cur); mtnset.add(cur); nm += 1
            _gp = PAT(*cur); znm[_gp] = znm.get(_gp, 0) + 1
for (x, y) in mtnset:
    mtn[y][x] = True
    veg[y][x] = False

# mountain size variants by TRUE graphic width (ILB frame lookup — behavioral
# classification was inverted: the cluster-happy guids are the SMALL 60px graphic,
# the isolated ones the 188px giant whose skirt covers ring 1 + both x±2 side hexes).
def mtn_rec_guid(r_):
    ct_, cb_ = tbl(r_, 20)              # decor child tbl (child at 16, classid 4B)
    return struct.unpack_from('<I', r_, cb_ + ct_[1])[0]
MTN_BY = {}
for t_, recs_ in MTNREC.items():
    d_ = {}
    for r_ in recs_:
        d_.setdefault(size_class(gfx_width(mtn_rec_guid(r_))), []).append(r_)
    MTN_BY[t_] = d_
SZ_FALLBACK = {'S': ['S', 'M', 'L', 'XL'], 'M': ['M', 'S', 'L', 'XL'],
               'L': ['L', 'M', 'S', 'XL'], 'XL': ['XL', 'L', 'M', 'S']}
# v4.24: single-hex-footprint mountains only — safe as UG 'full' dressing, where
# no footprint pre-pass runs (multi-hex skirts could cover UG structures/decor).
# Guids missing from FOOT are excluded too (unknown skirt = not worth the risk).
MTN_S1 = {t_: [r_ for r_ in recs_
               if len(FOOT.get(mtn_rec_guid(r_), [(0, 0), (0, 0)])) <= 1]
          for t_, recs_ in MTNREC.items()}
# v4.25 apocalyptic: volcano graphics (wl_volcs 60px / wl_volcl) by terrain
VOLCREC = {t_: [r_ for r_ in recs_
                if 'volc' in decor_gfx.get(mtn_rec_guid(r_), '')]
           for t_, recs_ in MTNREC.items()}
# record choice happens in a footprint-aware pre-pass just before the stream write

# ---- object placement ----------------------------------------------------------
land = [(x, y) for y in range(H) for x in range(W)
        if grid[y][x] not in (None, 0, 6, 9, 10, 13) and paint[y][x]]
NLAND = len(land)

placed = {}          # (x,y) -> (group, entry)
obj_foot = set()     # hexes covered by placed structures' graphics (registry field 7)
obj_foot_road = set()  # same minus cities: roads may run INTO a city graphic (gates)
def entry_foot_cells(x, y, entry):
    out = []
    for cls_, gd_ in entry.get('children', []):
        if cls_ in (0x20153, 0x2073E): continue
        fp = FOOT.get(gd_)
        if fp and len(fp) > 1:
            out += foot_cells(x, y, fp)
    return out
def register(x, y, g, entry):
    """Commit an object: no other object may sit inside its graphic's footprint."""
    placed[(x, y)] = (g, entry)
    for c_ in entry_foot_cells(x, y, entry):
        obj_foot.add(c_)
        if not g.startswith('city'):
            obj_foot_road.add(c_)
def foot_clash(x, y, entry, water_ok=False):
    """Blocked if the graphic footprint overlaps placed objects, leaves the map,
    or (v4.19) covers water/unpainted hexes — a size-3 city with two footprint
    hexes on water rendered glitched/invisible. Water-edge structures
    (shipyard) pass water_ok."""
    cells = entry_foot_cells(x, y, entry)
    for cx_, cy_ in cells:
        if not (0 <= cx_ < W and 0 <= cy_ < H):
            return True
        if not water_ok and grid[y][x] != 0 and grid[cy_][cx_] in (None, 0):
            return True
    return any(c_ in placed or c_ in obj_foot for c_ in cells)
def dist2(a, b): return (a[0]-b[0])**2 + (a[1]-b[1])**2
def family(g):
    for fam in ('city', 'farm', 'mine', 'towr', 'node', 'altar', 'cave', 'tele'):
        if fam in g: return fam
    if g in ('dungeon', 'lair', 'ruins', 'ziggurat', 'site_cas2'): return 'site'
    return 'misc'
def free(x, y, spacing, fam):
    """Blocked if same-family object within `spacing`, ANY object within 2, or the
    spot is under another structure's graphic."""
    if (x, y) in obj_foot: return False
    for (px, py), (g, _) in placed.items():
        d2 = dist2((x, y), (px, py))
        if d2 < 4: return False
        if family(g) == fam and d2 < spacing * spacing: return False
    return True

def pick_entry(group, t):
    """Water templates (terr 0, animated hexagon child) only on water; land-on-land."""
    lst = OBJ.get(group, [])
    if t == 0:
        lst = [z for z in lst if z['terr'] == 0]
    else:
        land_lst = [z for z in lst if z['terr'] != 0]
        same = [z for z in land_lst if z['terr'] == t]
        if not same and t == 12:
            # v6.0: no structure was ever harvested on dirt — the old any-terrain
            # fallback dropped SNOW-skinned groves/towers onto mud fields (user:
            # "structures on dirt are glitched"). v6.0b: structures on dirt now
            # sit on a STEPPE hexagon, so steppe skins first, then waste.
            same = ([z for z in land_lst if z['terr'] == 4]
                    or [z for z in land_lst if z['terr'] == 5])
        lst = same or land_lst
    return rnd.choice(lst) if lst else None

def flatness(x, y):
    n = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W:
                if grid[ny][nx] in (None, 0, 6, 9, 10, 13) or mtn[ny][nx]: n += 1
    return n     # 0 = fully open

def near_mtn(x, y):
    # adjacency is fine again: structures may sit right at a mountain's base, the
    # footprint-aware size choice keeps them out from UNDER the graphic
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and mtn[ny][nx]: return True
    return False

def try_place(group, count, spacing, pred=None, among=None):
    got = 0
    fam = family(group)
    cells = among if among is not None else land
    order = cells[:]
    rnd.shuffle(order)
    for (x, y) in order:
        if got >= count: break
        t = grid[y][x]
        if mtn[y][x] or (x, y) in placed: continue
        if pred and not pred(x, y): continue
        if not free(x, y, spacing, fam): continue
        entry = pick_entry(group, t)
        if entry is None or foot_clash(x, y, entry,
                                       water_ok=(group == 'shipyard')):
            continue
        register(x, y, group, entry)
        got += 1
    return got

# ---- player starts, phase A (v4.14): mode rolls, leaders/parties, surface spots --
# Rolled once per map so every player starts equal: city size, in-city vs near an
# independent own-race city, the 15% all-players-get-a-hero case, leader/hero XP,
# and the party composition (same donor records for everyone).
START_SZ = rnd.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]
IN_CITY = rnd.random() < 0.5
HERO_START = rnd.random() < 0.15
LEADER_XP = rnd.choice([0, 5, 10, 20, 40])
HERO_XP = rnd.choice([20, 40, 60, 90])
# party composition = SLOT indexes into each race's 18-unit block, so every player
# gets their own race's equivalents (slot 0 archer, 1 priest, 2 cavalry, 3 infantry)
COMP = rnd.choices(PARTY_SLOTS, weights=[30, 15, 25, 30],
                   k=rnd.choice([2, 3, 3, 4]))
if os.environ.get('AOW_COMP'):                       # diagnostic: force party slots
    COMP = [int(x) for x in os.environ['AOW_COMP'].split(',')]

used_lib = set()
def hero_level(h):
    fd = dict(h['fields'])
    return bytes.fromhex(fd[22])[0] if 22 in fd else 1

# leader level rolled ONCE from the levels every present race can still supply
# (all 12 races have level-1 and level-5 heroes; 2-4 have gaps) — all leaders
# copy a hero of the SAME level so the players start equal (v4.18)
_races_ = [player_race(p) for p in range(1, NPLAYERS + 1)]
_lvls_ = [lv for lv in (1, 2, 3, 4, 5)
          if all(sum(1 for h in LIB if not h['leaderlike']
                     and h['race'] == r_ and hero_level(h) == lv)
                 >= _races_.count(r_) for r_ in set(_races_))] or [1]
LEADER_LVL = rnd.choices(
    _lvls_, weights=[{1: 45, 2: 25, 3: 15, 4: 10, 5: 5}[lv] for lv in _lvls_])[0]

def take_hero(race=None, level=None):
    def pick(r_, lv_):
        return [i for i in range(len(LIB)) if i not in used_lib
                and not LIB[i]['leaderlike']
                and (r_ is None or LIB[i]['race'] == r_)
                and (lv_ is None or hero_level(LIB[i]) == lv_)]
    cand = pick(race, level) or pick(race, None) or pick(None, None)
    i = rnd.choice(cand)
    used_lib.add(i)
    return LIB[i]

leaders, start_party = {}, {}
for p in range(1, NPLAYERS + 1):
    r_ = player_race(p)
    h = take_hero(r_, LEADER_LVL)
    lib_l, stack_l = make_leader(h, r_, LEADER_XP, p)
    leaders[p] = lib_l                  # library entry + player f30 (minimal form)
    party = [stack_l]                   # placed leader (rich form, same id)
    if HERO_START:
        party.append(hero_stack_rec(take_hero(r_), HERO_XP, p))
    if 'donorunits' in DBG:
        for sl in COMP:
            d_ = rnd.choice(PLAYER_KIT['party_units'])
            fl = []
            for t_, v_ in ((t2, bytes.fromhex(v2)) for t2, v2 in d_['fields']):
                if t_ == 5: v_ = struct.pack('<I', fresh_id())
                elif t_ == 47: v_ = bytes([p])
                fl.append((t_, v_))
            party.append(enc_record(0x20214, fl))
    else:
        party += [make_unit(RACE_BASE[r_] + sl, p) for sl in COMP]
    start_party[p] = party

_hasl = dict(lvls)
start_lvl = {}
for p in range(1, NPLAYERS + 1):
    r_ = player_race(p)
    if (r_ in RACE_UG and 1 in _hasl and LEVELS >= 2 and rnd.random() < 0.5):
        start_lvl[p] = 2 if (2 in _hasl and LEVELS >= 3
                             and rnd.random() < 0.25) else 1
    else:
        start_lvl[p] = 0

# landmass sizes for the no-stuck-starts rule (small islands only for Lizardmen)
comp_of, comp_sz = {}, {}
_seen, _landset, _ci = set(), set(land), 0
for c0 in land:
    if c0 in _seen: continue
    comp, stck = [], [c0]
    _seen.add(c0)
    while stck:
        pt = stck.pop(); comp.append(pt)
        for q_ in hexn(*pt):
            if q_ in _landset and q_ not in _seen:
                _seen.add(q_); stck.append(q_)
    for pt in comp: comp_of[pt] = _ci
    comp_sz[_ci] = len(comp); _ci += 1
ISLAND_MIN = 25

def start_cand_ok(x, y, race):
    if grid[y][x] not in (1, 2, 3, 4, 5): return False
    if not (2 <= x < W - 2 and 2 <= y < H - 2): return False
    if mtn[y][x] or flatness(x, y) > 2: return False
    if race != RACE_SWIM and comp_sz.get(comp_of.get((x, y), -1), 0) < ISLAND_MIN:
        return False
    return True

city_race = {}
start_city_at = {}      # (lvl,x,y) -> owning player (IN_CITY mode)
start_stack_at = {}     # (lvl,x,y) -> player whose stack sits there
placed_start = []
start_fallback = []
for p in [p for p in range(1, NPLAYERS + 1) if start_lvl[p] == 0]:
    r_ = player_race(p)
    cands = [c for c in land if start_cand_ok(c[0], c[1], r_)]
    rnd.shuffle(cands)
    cands.sort(key=lambda c: -min((hexdist(c, q_) for q_ in placed_start),
                                  default=9999))
    got = False
    for pos in cands[:800]:
        t = grid[pos[1]][pos[0]]
        entry = gname = None
        for g in ('city%d_r%02x' % (START_SZ, r_), 'city%d_neutral' % START_SZ):
            e_ = pick_entry(g, t)
            if e_ and not foot_clash(pos[0], pos[1], e_):
                entry, gname = e_, g
                break
        if entry is None:
            continue
        register(pos[0], pos[1], gname, entry)
        city_race[pos] = r_
        placed_start.append(pos)
        if IN_CITY:
            start_city_at[(0, pos[0], pos[1])] = p
            start_stack_at[(0, pos[0], pos[1])] = p
        else:
            spot = None
            for c in sorted(land, key=lambda q_: hexdist(q_, pos))[:60]:
                if not 2 <= hexdist(c, pos) <= 3: continue
                if grid[c[1]][c[0]] not in (1, 2, 3, 4, 5) or mtn[c[1]][c[0]]:
                    continue
                if c in placed or c in obj_foot or comp_of.get(c) != comp_of.get(pos):
                    continue
                spot = c
                break
            if spot is None:
                start_city_at[(0, pos[0], pos[1])] = p     # hemmed in: own the city
                spot = pos
            else:
                obj_foot.add(spot)
            start_stack_at[(0, spot[0], spot[1])] = p
        got = True
        break
    if not got:
        start_fallback.append(p)
        print('WARNING: no surface start found for player %d (deferred)' % p)

# ---- cities: region-based races (smooth noise → nearby cities share a race).
# Racial harvested templates carry matching recruit rosters; when a (size, race) template is
# missing, a neutral template is used and its race byte (field 13) is stamped.
AVAIL_RACES = sorted({int(g.split('_r')[1], 16) for g in OBJ
                      if g.startswith('city') and '_r' in g})
racef = make_noise(W, H, rnd, 2, 26.0 * SCALE)
def region_race(x, y):
    if not AVAIL_RACES: return None
    v = min(0.999, max(0.0, (racef(x, y) - 0.25) / 0.5))
    return AVAIL_RACES[int(v * len(AVAIL_RACES))]

n_city = max(2, max(4, NLAND // 260) - len(placed_start))
RNG_CITY_FRAC = 0.20     # fraction of cities left race-0xFF -> game rolls a random race
sizes = rnd.choices([1, 2, 3, 4], weights=[30, 35, 25, 10], k=n_city)
ncities = 0
corder = land[:]
rnd.shuffle(corder)
for (x, y) in corder:
    if ncities >= n_city: break
    t = grid[y][x]
    if mtn[y][x] or (x, y) in placed: continue
    if flatness(x, y) > 2: continue
    if not free(x, y, 7, 'city'): continue
    sz = sizes[ncities]
    race = None if rnd.random() < RNG_CITY_FRAC else region_race(x, y)
    entry = gname = None
    for g in (['city%d_r%02x' % (sz, race)] if race is not None else []) + ['city%d_neutral' % sz]:
        entry = pick_entry(g, t)
        if entry: gname = g; break
    if entry is None or foot_clash(x, y, entry): continue
    register(x, y, gname, entry)
    city_race[(x, y)] = race
    ncities += 1

city_pos = [p for p, (g, _) in placed.items() if g.startswith('city')]
near_city = [(x, y) for (x, y) in land
             if any(dist2((x, y), c) <= 49 for c in city_pos)]
wild = [(x, y) for (x, y) in land
        if all(dist2((x, y), c) > 36 for c in city_pos)]

# city footprints + 1-hex pad (v4.19): farm CROPS and city CROPS must never
# share a hex — a farm (and its crop ring) keeps out of the pad; SIGNS also
# must not sit in it (they replaced city crops)
city_foot_pad = set()
for (_cx, _cy), (_g2, _e3) in placed.items():
    if not _g2.startswith('city'):
        continue
    for c_ in set(entry_foot_cells(_cx, _cy, _e3)) | {(_cx, _cy)}:
        city_foot_pad.add(c_)
        city_foot_pad.update(hexn(*c_))
def farm_ok(x, y):
    return ((x, y) not in city_foot_pad
            and all(q_ not in city_foot_pad for q_ in hexn(x, y)))

nfarm  = try_place('farm+pad1', max(2, ncities), 3, among=near_city, pred=farm_ok)
nmine  = try_place('mine', max(3, NLAND // 400), 5, pred=near_mtn) \
       + try_place('mine', max(1, NLAND // 1200), 6)
ntowr  = try_place('pad1+towr', max(2, NLAND // 400), 7)
nnode  = 0
for g in ('node_str_node', 'node_str_node+pad1', 'node_pro_grov'):
    nnode += try_place(g, max(1, NLAND // 900), 8)
nsite = 0
for g in ('dungeon', 'lair', 'ruins', 'ziggurat', 'site_cas2'):
    nsite += try_place(g, max(1, NLAND // 2000), 8, among=wild)
nmisc = 0
nmisc += try_place('signs', max(2, NLAND // 1000), 8,   # v4.18: contextual texts
                   pred=lambda x, y: (x, y) not in city_foot_pad)
for g in ('sanctuary', 'sol', 'misc', 'altar_lghtn+pad1',
          'altar_life+pad1', 'pad1+watchtower',
          # v4.18: structures that never made the rotation + newly harvested
          'building+pad1', 'blds+pad1', 'pad1+str_rf', 'aren+pad1'):
    nmisc += try_place(g, max(1, NLAND // 1900), 9)
def coastal(x, y):
    return any(grid[ny][nx] == 0 for nx, ny in hexn(x, y))
def shipyard_ok(x, y):
    """v6.0: coastal + the engine's orientation rule. Like bridges (v4.8), a
    shipyard computes its dock direction at load and needs SOME opposite-
    neighbor axis with LAND on both ends; on a peninsula tip (water on 5 of 6
    sides) it gets direction -1 and the editor AVs before the map even shows
    ("Oh dear, it's the end...."). Found by stream-bisecting seed 743784 L,
    fatal record: shipyard at (34,34), land only to the S."""
    if not coastal(x, y):
        return False
    nb = nbr_dirs(x, y)
    def landt(q_):
        qx, qy = q_
        return (0 <= qx < W and 0 <= qy < H and paint[qy][qx]
                and grid[qy][qx] not in (None, 0, 6, 9, 10, 13))
    return any(landt(nb[d_]) and landt(nb[d_ + 3]) for d_ in range(3))
nmisc += try_place('shipyard', max(1, NLAND // 1500), 7, pred=shipyard_ok)

# ---- teleporters: two-way pairs + one-way gates landing on a sanctuary's top hex.
# Child cls 0x20105: f3/4 = own xy, f7/8 = DESTINATION xy, f9 = dest level (absent
# = level 0), f10 = 0. Verbatim official template (After the Fall), guid 0x2B.
TELE_REC = bytes.fromhex(
    '043200330b341c043c520102000101004b8fcf0606010200030100030404051100'
    '0000592d04010200070100030404056206070a080b0a0c2b000000592d33000000'
    '5433000080')
TELE_PATCH = dict(hexvar=16, coords=[(35, 36), (60, 61)], dest=(66, 67), id98=62)
TELE_CHILDREN = [(0x20105, 0x2B)]
def make_tele(x, y, t, dx, dy):
    rec = bytearray(TELE_REC)
    if t == 12:
        t = 4      # v6.0b: steppe hex under surface-dirt structures (teles are L0-only)
    struct.pack_into('<I', rec, TELE_PATCH['hexvar'],
                     rnd.choice(LAND_STATIC.get(t) or terr_var[t])[1])
    for (xo, yo) in TELE_PATCH['coords']:
        rec[xo] = x & 0xFF; rec[yo] = y & 0xFF
    rec[TELE_PATCH['dest'][0]] = dx & 0xFF
    rec[TELE_PATCH['dest'][1]] = dy & 0xFF
    struct.pack_into('<I', rec, TELE_PATCH['id98'], fresh_id())
    return bytes(rec)
def tele_ok(x, y):
    if grid[y][x] in (None, 0, 6, 9) or mtn[y][x] or (x, y) in placed: return False
    if not free(x, y, 6, 'tele'): return False
    return not any(c_ in placed or c_ in obj_foot
                   for c_ in foot_cells(x, y, FOOT.get(0x2B, [(0, 0)])))
def place_tele(x, y, dx, dy):
    register(x, y, 'tele',
             dict(children=TELE_CHILDREN, prebuilt=make_tele(x, y, grid[y][x], dx, dy)))
def sanct_top(px, py, entry):
    """Topmost hex of the structure's footprint (user rule: teleport lands there)."""
    for cls_, gd_ in entry.get('children', []):
        fp = FOOT.get(gd_)
        if fp and len(fp) > 1:
            cells = foot_cells(px, py, fp)
            return min(cells, key=lambda c_: (c_[1], abs(c_[0] - px)))
    return (px, py)
# 15% of all TELEPORTERS are one-way (a pair event yields 2 teles, so the per-event
# one-way probability is 0.26); a one-way lands on a sanctuary top 60% of the time,
# else on a clear far-away hex (protected from later mountain footprints).
ntele = npairs = noneway = 0
tcand = land[:]
rnd.shuffle(tcand)
sancts = [(p_, e_) for p_, (g_, e_) in placed.items() if g_ == 'sanctuary']
tele_land = set()
def landing_spot(src):
    for p_ in tcand:
        if hexdist(p_, src) < 15: continue
        x_, y_ = p_
        if (grid[y_][x_] in (None, 0, 6, 9) or mtn[y_][x_] or p_ in placed
                or p_ in obj_foot or p_ in tele_land): continue
        return p_
    return None
n_target = max(2, NLAND // 800)
queue = tcand[:]
while queue and ntele < n_target:
    a = queue.pop()
    if not tele_ok(*a): continue
    if rnd.random() < 0.26:
        dest = None
        if sancts and rnd.random() < 0.60:
            sp_, se_ = rnd.choice(sancts)
            dest = sanct_top(sp_[0], sp_[1], se_)
        if dest is None:
            dest = landing_spot(a)
            if dest is None: continue
            tele_land.add(dest)
        place_tele(a[0], a[1], dest[0], dest[1])
        ntele += 1; noneway += 1
    else:
        b = next((b_ for b_ in queue if hexdist(a, b_) >= 18 and tele_ok(*b_)), None)
        if b is None: continue
        place_tele(a[0], a[1], b[0], b[1])
        place_tele(b[0], b[1], a[0], a[1])
        ntele += 2; npairs += 1

# ---- cave systems (entrances here; carving in the UG pass). 65% are TUNNELS with
# two entrances, preferring pairs whose surface line crosses mountains/water — the
# cave is a shortcut under the obstacle. The rest are single-entrance pockets.
UG_ELABORATE = rnd.random() < 0.25
n_sys = 0 if LEVELS < 2 else max(2, NLAND // (450 if UG_ELABORATE else 700))
UG_SYSTEMS = []

def cave_spot_ok(x, y):
    t = grid[y][x]
    if t in (None, 0, 6, 9, 10, 13) or mtn[y][x] or (x, y) in placed: return False
    if (x, y) in tele_land: return False       # keep one-way landing hexes clear
    return free(x, y, 8, 'cave')

# -- landmasses separated by water are ALMOST ALWAYS tunnel-joined (90%); the random
#    pair search below additionally links mountain-separated areas sometimes
def landmasses():
    seen, comps, landset = set(), [], set(land)
    for c0 in land:
        if c0 in seen: continue
        comp, stack = [], [c0]
        seen.add(c0)
        while stack:
            p = stack.pop()
            comp.append(p)
            for q_ in hexn(*p):
                if q_ in landset and q_ not in seen:
                    seen.add(q_); stack.append(q_)
        comps.append(comp)
    return comps

comps = [c for c in landmasses() if len(c) >= 12]
if LEVELS < 2:      # v4.25 surface-only: no cave entrances at all
    comps = comps[:1]
for i in range(1, len(comps)):
    best = None
    sa = rnd.sample(comps[i], min(100, len(comps[i])))
    for j in range(i):
        sb = rnd.sample(comps[j], min(100, len(comps[j])))
        for pa in sa:
            for pb in sb:
                d_ = hexdist(pa, pb)
                if best is None or d_ < best[0]: best = (d_, pa, pb, j)
    if best is None or rnd.random() > 0.85: continue     # no distance cap: long is fine
    d_, pa, pb, bj = best
    def near_spot(comp, ref):
        for p in sorted(comp, key=lambda q_: hexdist(q_, ref))[:80]:
            if cave_spot_ok(*p): return p
        return None
    a2 = near_spot(comps[i], pa)
    b2 = near_spot(comps[bj], pb)
    if not a2 or not b2: continue
    ea = pick_entry('cave', grid[a2[1]][a2[0]])
    eb = pick_entry('cave', grid[b2[1]][b2[0]])
    if ea and eb and not foot_clash(*a2, ea) and not foot_clash(*b2, eb):
        register(*a2, 'cave', ea); register(*b2, 'cave', eb)
        UG_SYSTEMS.append(dict(kind='tunnel', ent=[a2, b2], lm=True))

n_lm_tun = sum(1 for s_ in UG_SYSTEMS if s_.get('lm'))
corder2 = land[:]
rnd.shuffle(corder2)
ci2 = 0
while len(UG_SYSTEMS) < n_sys and ci2 < len(corder2):
    a = corder2[ci2]; ci2 += 1
    if not cave_spot_ok(*a): continue
    made = False
    if rnd.random() < 0.65:
        best = None
        for _ in range(70):
            b = (a[0] + rnd.randrange(-22, 23), a[1] + rnd.randrange(-22, 23))
            if not (0 <= b[0] < W and 0 <= b[1] < H): continue
            if not (8 <= hexdist(a, b) <= 22): continue
            if not cave_spot_ok(*b): continue
            obs = sum(1 for p in hexline(a, b)
                      if grid[p[1]][p[0]] in (None, 0, 6, 9) or mtn[p[1]][p[0]])
            score = obs + rnd.random()
            if best is None or score > best[0]: best = (score, b, obs)
        if best and (best[2] >= 2 or rnd.random() < 0.45):
            b = best[1]
            e1_ = pick_entry('cave', grid[a[1]][a[0]])
            e2_ = pick_entry('cave', grid[b[1]][b[0]])
            if (e1_ and e2_ and not foot_clash(*a, e1_) and not foot_clash(*b, e2_)):
                register(*a, 'cave', e1_); register(*b, 'cave', e2_)
                UG_SYSTEMS.append(dict(kind='tunnel', ent=[a, b]))
                made = True
    if not made:
        e1_ = pick_entry('cave', grid[a[1]][a[0]])
        if e1_ and not foot_clash(*a, e1_):
            register(*a, 'cave', e1_)
            UG_SYSTEMS.append(dict(kind='pocket', ent=[a]))
ncave = sum(len(s_['ent']) for s_ in UG_SYSTEMS)

# water objects (templates harvested on water keep their animated hexagon class);
# open water only — not in the middle of a narrow river
def open_water(x, y):
    return sum(1 for q_ in hexn(x, y) if grid[q_[1]][q_[0]] == 0) >= 5
water = [(x, y) for y in range(H) for x in range(W) if grid[y][x] == 0 and paint[y][x]]
nwater = try_place('node_str_nrck', max(1, len(water) // 500), 9, pred=open_water, among=water) \
       + try_place('whirlpool', max(1, len(water) // 350), 8, pred=open_water, among=water)

for (x, y) in placed:
    veg[y][x] = False
    mtn[y][x] = False
for (x, y) in obj_foot:        # nothing under structure graphics either
    veg[y][x] = False
    mtn[y][x] = False
for (x, y) in tele_land:       # one-way landing hexes stay open ground
    veg[y][x] = False
    mtn[y][x] = False

# ---- roads: MST over cities, Dijkstra paths on the hex grid --------------------
ROAD_GUID = {1: 0x26, 2: 0x15, 3: 0x2F, 4: 0x30, 5: 0x31, 12: 0x31}
# bridges = cls-0x2087B child on a wet hex (roads auto-link to them, no road child).
# A road may cross exactly ONE wet hex at a time (wet->wet steps banned in the A*),
# which is precisely what a bridge is. Guids per terrain, from official-map usage.
BRIDGE_GUID = {0: 0xB3AC32, 6: 0x56D135E, 9: 0x9132B58, 10: 0x403557D, 13: 0x815A375}
WET_T = (0, 6, 9)
def hexcost(x, y):
    t = grid[y][x]
    if not paint[y][x] or (x, y) in placed or (x, y) in obj_foot_road: return None
    if mtn[y][x]: return None             # roads never run over a mountain
    if t in WET_T:                        # crossable only as a single-hex bridge,
        return 10.0 if bridgeable(x, y) else None   # and only where a bridge is legal
    if t not in ROAD_GUID: return None
    if veg[y][x]: return 3.0
    return 1.0

road = set()
citylist = [p for p, (g, _) in placed.items() if g.startswith('city')]
mst = []
if len(citylist) >= 2:
    intree = {citylist[0]}
    while len(intree) < len(citylist):
        best = None
        for a in intree:
            for b in citylist:
                if b in intree: continue
                dd = dist2(a, b)
                if best is None or dd < best[0]: best = (dd, a, b)
        mst.append((best[1], best[2]))
        intree.add(best[2])
# straight-run penalty: roads may run 4 hexes straight freely; continuing a 4-run costs
# extra (~"30% chance to curve"), 5+ costs more (~"50%"). Because obstacle hexes already
# cost more (mtn/veg/water), the cheap way to spend a forced curve is around obstacles.
def run_pen(run):
    if run <= 4: return 0.0
    return 0.5 if run == 5 else 1.0
jit = [[rnd.random() * 0.3 for _ in range(W)] for _ in range(H)]   # per-map wiggle

for (a, b) in mst:
    starts = [p for p in hexn(*a)
              if hexcost(*p) is not None and grid[p[1]][p[0]] not in WET_T]
    goals = set(p for p in hexn(*b)
                if hexcost(*p) is not None and grid[p[1]][p[0]] not in WET_T)
    if not starts or not goals: continue
    # A* over states (pos, dir, run) so straight runs carry cost
    dist = {}
    prev = {}
    pq = []
    for p in starts:
        st = (p, -1, 0)
        dist[st] = 0.0
        heapq.heappush(pq, (hexdist(p, b), 0.0, st))
    hit = None
    while pq:
        _, dcur, st = heapq.heappop(pq)
        if dcur > dist.get(st, 1e18): continue
        p, d, run = st
        if p in goals: hit = st; break
        for np_ in hexn(*p):
            c = hexcost(*np_)
            if c is None: continue
            if grid[p[1]][p[0]] in WET_T and grid[np_[1]][np_[0]] in WET_T:
                continue                      # no 2-hex water/lava crossings
            nd_ = dirid(p[0], p[1], np_[0], np_[1])
            nrun = min(run + 1, 6) if nd_ == d else 1
            cc = (c * 0.4 if np_ in road else c) + run_pen(nrun) + jit[np_[1]][np_[0]]
            nst = (np_, nd_, nrun)
            ndist = dcur + cc
            if ndist < dist.get(nst, 1e18):
                dist[nst] = ndist; prev[nst] = st
                heapq.heappush(pq, (ndist + hexdist(np_, b), ndist, nst))
    if hit is None: continue
    st = hit
    while True:
        road.add(st[0])
        if st not in prev: break
        st = prev[st]
for (x, y) in road:
    veg[y][x] = False       # (mountains can't be on road hexes — hexcost bars them)

# ---- standalone bridges at narrow (1-hex) river/lava points, road-less like most
# official-map bridges. A spot qualifies if some opposite-neighbor pair is walkable
# (stricter than the engine's land-only DirectionValid, so always legal).
def walkable(q_):
    x, y = q_
    return (0 <= x < W and 0 <= y < H and paint[y][x]
            and grid[y][x] not in (None, 0, 6, 9, 10, 13) and not mtn[y][x]
            and q_ not in obj_foot)

xbridges = set()
wet_cand = [(x, y) for y in range(H) for x in range(W)
            if grid[y][x] in WET_T and paint[y][x]
            and ((x, y) in river or grid[y][x] == 9)
            and (x, y) not in road and (x, y) not in placed
            and not mtn[y][x]               # v4.25: apocalyptic volcanos sit ON lava
            and (x, y) not in obj_foot]     # never under a structure graphic
rnd.shuffle(wet_cand)
for p in wet_cand:
    wn = sum(1 for q_ in hexn(*p) if grid[q_[1]][q_[0]] in WET_T)
    if not (1 <= wn <= 4): continue               # a channel, not open water
    nb_ = nbr_dirs(*p)
    if not any(walkable(nb_[d_]) and walkable(nb_[d_ + 3]) for d_ in range(3)): continue
    if any(q_ in xbridges or q_ in road for q_ in hexn(*p)): continue
    if rnd.random() < 0.20: xbridges.add(p)

# ---- light vegetation: sprinkle lveg/flowers/rocks/bones on BARE land (keeps the dense
# clusters as-is). Deserts excluded (user preference). Runs after objects+roads so no
# clearing pass is needed.
def veg_kind(rec):
    ct, cbb = tbl(rec, 20)          # decor child tbl (child at 16, classid 4B)
    if 1 not in ct: return 'tree'
    g = decor_gfx.get(struct.unpack_from('<I', rec, cbb + ct[1])[0], '')
    if 'mountain' in g: return 'hill'   # cls-0x20167 MOUNTAIN.ILB = passable HILLS —
                                        # never under/next to structures (user rule)
    if any(k in g for k in ('lveg', 'flwer', 'rocks', 'bones')): return 'light'
    return 'tree'
_VK = {t: [veg_kind(r) for r in v] for t, v in VEGREC.items()}
def _hill_1hex(rec):
    """Hills placed via veg get no footprint pass — only single-hex-footprint ones."""
    ct_, cb_ = tbl(rec, 20)
    return len(FOOT.get(struct.unpack_from('<I', rec, cb_ + ct_[1])[0], [0])) <= 1
LIGHTREC = {t: [r for r, k in zip(v, _VK[t]) if k == 'light'] for t, v in VEGREC.items()}
TREEREC = {t: [r for r, k in zip(v, _VK[t]) if k == 'tree'] for t, v in VEGREC.items()}
HILLREC = {t: [r for r, k in zip(v, _VK[t]) if k == 'hill' and _hill_1hex(r)]
           for t, v in VEGREC.items()}
# wilds pool: hills allowed but at HALF their natural share (non-hill recs doubled) —
# hills use the same 60px MOUNTAIN.ILB art, and too many read as scattered mountains
VEG_WILD = {t: [r for r, k in zip(v, _VK[t]) if k != 'hill'] * 2
               + [r for r, k in zip(v, _VK[t]) if k == 'hill' and _hill_1hex(r)]
            for t, v in VEGREC.items()}
_TD_HL = max(0.005, _sv(0.05, 0.01))       # highlands lone-tree/hill scatter
def TREE_DENSITY_AT(x, y):                 # lone trees in bare areas
    return _TD_HL if PAT(x, y) == 'highlands' else 0.01
LIGHT_D = {t: (rnd.uniform(0.01, 0.05) if t == 2 else rnd.uniform(0.08, 0.16)) for t in VEGREC}
scatter = {}                            # (x,y) -> 'light' | 'tree'
nlight = 0
for y in range(H):
    for x in range(W):
        t = grid[y][x]
        if (t in (None, 0, 6, 9) or not paint[y][x] or veg[y][x] or mtn[y][x]
                or (x, y) in placed or (x, y) in road or (x, y) in obj_foot
                or (x, y) in tele_land):
            continue
        r = rnd.random()
        _td = TREE_DENSITY_AT(x, y)
        if r < _td and TREEREC.get(t):
            scatter[(x, y)] = 'tree'; nlight += 1   # (highlands: half become hills)
        elif r < _td + LIGHT_D.get(t, 0) and LIGHTREC.get(t):
            scatter[(x, y)] = 'light'; nlight += 1

# ---- mountain record choice by TRUE footprint (registry field-7 mask, slot order
# N-clockwise, per guid): the footprint must never cover a structure/road/bridge hex
# (structures may hug the mountain's BASE — anything outside the footprint is fine),
# and any veg/rocks/hills under a footprint are cleared.
blocked_fp = set(placed) | road | xbridges | obj_foot | tele_land
mtn_choice = {}
volc_at = set()
for y in range(H):
    for x in range(W):
        if not mtn[y][x]: continue
        t = grid[y][x]
        n_ = sum(1 for q_ in hexn(x, y) if mtn[q_[1]][q_[0]])
        r_ = rnd.random()
        if n_ == 0:      # standalone: almost always a big graphic
            sz = 'XL' if r_ < 0.55 else 'L' if r_ < 0.90 else 'S'
        elif n_ == 1:    # pairs: big too
            sz = 'L' if r_ < 0.50 else 'XL' if r_ < 0.80 else 'S'
        else:            # ranges: smalls give variety inside the mass, bigs give bulk
            sz = 'S' if r_ < 0.40 else 'L' if r_ < 0.75 else 'XL' if r_ < 0.90 else 'M'
        rec = None
        _apoc = PAT(x, y) == 'apocalyptic'
        # apocalyptic volcanos — try a wl_volc* record first. v6.3 (user-retuned
        # twice): moderate numbers, STAGGERED — the odd adjacent pair is fine
        # but rare (8%), distance 2 at 50%; the hexes between get regular
        # waste/lava mountains of rolled sizes or (waste) lone hills.
        if _apoc and VOLCREC.get(t) and rnd.random() < min(0.70, 0.40 * _K):
            _vd = min((hexdist((x, y), v_) for v_ in volc_at), default=99)
            if _vd > 2 or (_vd == 2 and rnd.random() < 0.50) or \
                    (_vd == 1 and rnd.random() < 0.08):
                cand = rnd.choice(VOLCREC[t])
                if not any(c_ in blocked_fp
                           for c_ in foot_cells(x, y, FOOT.get(mtn_rec_guid(cand),
                                                               [(0, 0)]))):
                    rec = cand
                    volc_at.add((x, y))
        # apocalyptic filler between volcanos: some lone hills for size variety
        # (HILLREC = 1-hex-footprint hill art; lava terrain has none -> mountains)
        if (rec is None and _apoc and HILLREC.get(t) and (x, y) not in blocked_fp
                and rnd.random() < (0.35 if any(q_ in volc_at for q_ in hexn(x, y))
                                    else 0.10)):
            rec = rnd.choice(HILLREC[t])
        if rec is None:
            for s2 in SZ_FALLBACK[sz]:
                pool = MTN_BY[t].get(s2)
                if not pool: continue
                cand = rnd.choice(pool)
                if any(c_ in blocked_fp
                       for c_ in foot_cells(x, y, FOOT.get(mtn_rec_guid(cand), [(0, 0)]))):
                    continue             # footprint would cover a structure/road
                rec = cand
                break
        if rec is None:                  # hemmed in: 1-hex footprint or nothing.
            # v4.25: EVERY lava mountain record (wl_volc* and the lone lava
            # MOUNTAIN.ILB) has a 7-cell footprint, so MTN_S1[9] is empty — the
            # old "S pool is 1-hex" assumption put unchecked 7-cell volcanos
            # over signs/altars (apocalyptic seed 780759). No 1-hex art for
            # this terrain -> no mountain here.
            pool_ = MTN_S1.get(t)
            if not pool_:
                mtn[y][x] = False
                continue
            rec = rnd.choice(pool_)
        mtn_choice[(x, y)] = rec
        for (cx, cy) in foot_cells(x, y, FOOT.get(mtn_rec_guid(rec), [(0, 0)])):
            veg[cy][cx] = False          # no veg/rocks/hills under a mountain graphic
            scatter.pop((cx, cy), None)

# v4.25 safety net: if a chosen record's footprint still covers a placed object,
# downgrade it to a true 1-hex record (and say so — the case should be root-caused)
for (mx, my), rec_ in list(mtn_choice.items()):
    bad_ = [c_ for c_ in foot_cells(mx, my, FOOT.get(mtn_rec_guid(rec_), [(0, 0)]))
            if c_ != (mx, my) and (c_ in placed or c_ in obj_foot)]
    if not bad_:
        continue
    print('MTN-FP REPAIR: (%d,%d) guid 0x%X covered %s -> 1-hex record'
          % (mx, my, mtn_rec_guid(rec_), bad_))
    _t2 = grid[my][mx]
    _pool = MTN_S1.get(_t2)
    if _pool:
        mtn_choice[(mx, my)] = rnd.choice(_pool)
        if (mx, my) in volc_at: volc_at.discard((mx, my))
    else:
        del mtn_choice[(mx, my)]
        mtn[my][mx] = False
        volc_at.discard((mx, my))
if volc_at:
    _vpairs = sum(1 for v_ in volc_at
                  for q_ in hexn(*v_) if q_ in volc_at) // 2
    print('volcanos: %d staggered (%d adjacent pairs)'
          % (len(volc_at), _vpairs))

# ---- underground (level 1) + DEPTHS (level 2) ------------------------------------
# Solid rock stays whatever the template has (EARTHHEX). Carved floor = terrain-12
# hu_ca variants; ponds/corridors = underground water (10) or underground lava (9,
# gfx-filtered hu_la). The depths are lava-heavy and reached via DOWN-entrances:
# paired 0x2037F children at the same coords on L1 floor and L2.
HAS_L1 = 1 in dict(lvls)
HAS_L2 = 2 in dict(lvls)
cave_sites = [p for p, (g, _) in placed.items() if g == 'cave']
cave_set = set(cave_sites)
ugworld, placed_ug, ug_decor = {}, {}, {}
ugworld2, placed_ug2, ug_decor2 = {}, {}, {}
UGB1, UGB2 = set(), set()
nugice1 = nugice2 = 0
# v4.24: walkable UG ground is no longer just carved dirt — 'limited'/'full' modes
# put real surface terrain down there (engine Land() accepts it; Mirrored Oasis /
# Athendore are built exactly this way)
UG_LAND = (12, 1, 2, 3, 4, 5)
nsun = nfill1 = nfill2 = nugdress = nugdress2 = 0
nmush = 0   # v6.4: mushrooms placed on underground grass (limited-inversion groves)
DEPTH_FULL = False

def freeze_ug(world, prob):
    """UG water below surface snow (or beside UG snow, v4.24) -> UG ice (terr 13,
    hu_ic), never beside lava."""
    n_ = 0
    for p, k_ in list(world.items()):
        if k_ != 10: continue
        x, y = p
        if (grid[y][x] == 3 or any(grid[q_[1]][q_[0]] == 3 for q_ in hexn(x, y))
                or any(world.get(q_) == 3 for q_ in hexn(x, y))):
            if not any(world.get(q_) == 9 for q_ in hexn(*p)) and rnd.random() < prob:
                world[p] = 13; n_ += 1
    return n_

def find_ug_bridges(world):
    """U_brdg spots: wet cells (pond arms, corridor-through-floor gaps) with carved
    floor on some opposite-neighbor pair — a walkable 1-hex crossing."""
    out = set()
    wet_ = [p for p, t_ in world.items() if t_ in (9, 10, 13)]
    rnd.shuffle(wet_)
    for p in wet_:
        nb_ = nbr_dirs(*p)
        if not any(world.get(nb_[d_]) in UG_LAND and world.get(nb_[d_ + 3]) in UG_LAND
                   for d_ in range(3)):
            continue
        if any(q_ in out for q_ in hexn(*p)): continue
        if rnd.random() < 0.55: out.add(p)
    return out
UGVEG = [bytes.fromhex(h) for h in OBJ.get('__ugveg__', [])]
# v4.24b (user spec): sunlit-pocket veg = primarily MUSHROOMS (Ug_Vegetation) and
# DEAD TREES (*_dtree, 1-hex footprint only) — not the live surface flora
_MUSHREC = [r_ for r_ in UGVEG
            if 'ug_vegetation' in decor_gfx.get(mtn_rec_guid(r_), '')]
DTREEREC = {t_: [r_ for r_ in v_
                 if 'dtree' in decor_gfx.get(mtn_rec_guid(r_), '') and _hill_1hex(r_)]
            for t_, v_ in VEGREC.items()}
_DTREE_ALL = [r_ for v_ in DTREEREC.values() for r_ in v_]
UG_LAVA_VAR = [v for v in terr_var.get(9, []) if decor_gfx.get(v[1], '').startswith('hu')]
nugobj = nugobj2 = ndown = 0
DEPTH_SYSTEMS = []
DOWN_SET = set()

# Entrance GUID encodes WHICH level-pair it connects (verified across AtF/VBV/Slugfest):
#   0x2C       = surface<->underground (L0+L1 pairs, both sides)
#   0x416D713  = underground<->depths  (L1+L2 pairs, both sides)
# Mixing them leaves half-linked pairs -> "exception during closehsm" in the editor.
def cave_guid(e_):
    for cls_, g_ in e_['children']:
        if cls_ == 0x2037F: return g_
    return None
CAVE_UP_L1 = [e for e in OBJ.get('cave_l1', []) if cave_guid(e) == 0x2C]
CAVE_DEEP  = [e for e in OBJ.get('cave_l1', []) if cave_guid(e) == 0x0416D713]
if 'cave' in OBJ:      # surface pool: only surface-type entrances
    OBJ['cave'] = [e for e in OBJ['cave'] if cave_guid(e) == 0x2C] or OBJ['cave']

def parse_level_paint(lid):
    lt_off = lkb + dict(lvls)[lid]
    lfx, lbx = tbl(inner, lt_off + 4)
    sx, ex = lbx + lfx[6], lbx + lfx[1]
    pm = [[False] * W for _ in range(H)]
    qx, ix = sx, 0
    while qx < ex and ix < W * H:
        Lx = struct.unpack_from('<I', inner, qx)[0]
        if struct.unpack_from('<H', inner, qx + 4 + 3)[0] != 0x0557:
            pm[ix // W][ix % W] = True
        qx += 4 + Lx; ix += 1
    return lt_off, sx, ex, pm

def set_wet(world, p, kind):
    """Assign water(10)/lava(9) without ever putting them adjacent: joins the
    neighbouring body's kind instead, or leaves a floor causeway if both touch."""
    nbk = {world.get(q_) for q_ in hexn(*p)}
    if 9 in nbk and 10 in nbk:
        world[p] = 12; return
    if kind == 9 and 10 in nbk: kind = 10
    elif kind == 10 and 9 in nbk: kind = 9
    world[p] = kind

def carve(systems, okf, world, sid, pond_div, pond_lava, conn_prob, conn_lava):
    def grow(seed_, target):
        blob = {seed_}; frontier = [seed_]
        while len(blob) < target and frontier:
            b_ = rnd.choice(frontier)
            opts = [p for p in hexn(*b_) if okf(*p) and p not in blob]
            if not opts:
                frontier.remove(b_); continue
            np_ = rnd.choice(opts)
            blob.add(np_); frontier.append(np_)
        return blob
    ents_all = set(p for s_ in systems for p in s_['ent'])
    for si, sysd in enumerate(systems):
        ents = sysd['ent']
        cells = set()
        if len(ents) == 2:                               # tunnel: carve a->b + end chambers
            a, b = ents
            # road-like wander: split long runs at jittered waypoints
            def wpts(p, q_, depth=0):
                if hexdist(p, q_) <= 12 or depth > 3: return [p, q_]
                m = ((p[0] + q_[0]) // 2 + rnd.randrange(-4, 5),
                     (p[1] + q_[1]) // 2 + rnd.randrange(-4, 5))
                if not (0 <= m[0] < W and 0 <= m[1] < H and okf(*m)):
                    m = ((p[0] + q_[0]) // 2, (p[1] + q_[1]) // 2)
                    if not (0 <= m[0] < W and 0 <= m[1] < H and okf(*m)):
                        return [p, q_]
                return wpts(p, m, depth + 1)[:-1] + wpts(m, q_, depth + 1)
            path = wpts(a, b)
            cells.add(a)
            cur = a
            for tgt in path[1:]:
                guard = 0
                while cur != tgt and guard < 600:
                    guard += 1
                    opts = [p for p in hexn(*cur) if okf(*p)]
                    if not opts: break
                    opts.sort(key=lambda p: hexdist(p, tgt) + rnd.random() * 1.6)
                    cur = opts[0]
                    cells.add(cur)
                    if rnd.random() < 0.3:
                        for p in hexn(*cur):
                            if okf(*p) and rnd.random() < 0.45: cells.add(p)
            for c0 in ents:
                cells |= grow(c0, rnd.randrange(4, 9))
        else:                                            # pocket: one bigger chamber system
            cells = grow(ents[0], rnd.randrange(20, 45) if UG_ELABORATE
                         else rnd.randrange(12, 26))
        for p in cells:
            world.setdefault(p, 12)
            sid.setdefault(p, si)
    for i in range(len(systems)):                        # flooded corridors between systems
        for j in range(i + 1, len(systems)):
            ai, bj = systems[i]['ent'][0], systems[j]['ent'][0]
            if hexdist(ai, bj) > 20 or rnd.random() > conn_prob: continue
            kind = 9 if (UG_LAVA_VAR and rnd.random() < conn_lava) else 10
            cur, guard, corridor = ai, 0, []
            while guard < 400:
                guard += 1
                opts = [p for p in hexn(*cur) if okf(*p)]
                if not opts: break
                opts.sort(key=lambda p: hexdist(p, bj) + rnd.random() * 1.2)
                cur = opts[0]
                if sid.get(cur) == j: break
                if cur not in world: corridor.append(cur)
            if sid.get(cur) == j:                        # only keep completed corridors
                for p in corridor: set_wet(world, p, kind)
    fc = [p for p, t_ in world.items() if t_ == 12]
    for _ in range(max(1, len(fc) // pond_div)):         # ponds inside systems
        c = rnd.choice(fc)
        if c in ents_all: continue
        kind = 9 if (UG_LAVA_VAR and rnd.random() < pond_lava) else 10
        for p in [c] + hexn(*c):
            if world.get(p) == 12 and p not in ents_all and rnd.random() < 0.7:
                set_wet(world, p, kind)

def fill_ug_world(world, paintm, lavaish):
    """v4.24 'full': open a UG level into a surface-style WORLD (Mirrored Oasis /
    Athendore). Rock survives only as noise-thresholded ridges; the rest gets
    surface biomes, lakes become UG water (lava lakes in the depths). Carved
    system cells (already in `world`) keep their layout. Returns cells added."""
    ev2 = make_noise(W, H, rnd, 4, 20.0 * SCALE)
    cl2 = make_noise(W, H, rnd, 2, 30.0 * SCALE)
    bl2 = make_noise(W, H, rnd, 2, 16.0 * SCALE)
    rk2 = make_noise(W, H, rnd, 3, 13.0 * SCALE)
    keep = rnd.uniform(0.25, 0.40) if lavaish else rnd.uniform(0.18, 0.35)
    vals = sorted(rk2(x, y) for y in range(H) for x in range(W) if paintm[y][x])
    if not vals: return 0
    thr = vals[int(len(vals) * keep)]
    # lake level by QUANTILE, not raw noise value — per-instance noise histograms
    # swing enough that a fixed threshold gave 15-50% water across runs
    evals = sorted(ev2(x, y) for y in range(H) for x in range(W) if paintm[y][x])
    lakelvl = evals[int(len(evals) *
                        (rnd.uniform(0.08, 0.22) if lavaish
                         else rnd.uniform(0.10, 0.28)))]
    n_ = 0
    for y in range(H):
        for x in range(W):
            if not paintm[y][x]: continue
            p = (x, y)
            if p in world: continue          # carved floor/ponds stay as carved
            if rk2(x, y) < thr: continue     # stays solid rock ridge
            n_ += 1
            if ev2(x, y) < lakelvl:          # lakes; set_wet keeps 9/10 apart
                wet = 9 if (lavaish and UG_LAVA_VAR and bl2(x, y) > 0.55) else 10
                set_wet(world, p, wet)
                continue
            bv = bl2(x, y)
            if bv > 0.80:
                if bv > 0.93 and UG_LAVA_VAR:
                    set_wet(world, p, 9)
                else:
                    world[p] = 5
                continue
            cv = cl2(x, y)
            t2 = 3 if cv < 0.30 else 4 if cv < 0.44 else 2 if cv > 0.72 else 1
            if lavaish and t2 == 3: t2 = 5   # the depths run too hot for snow
            world[p] = t2
    # one majority-smooth over the new land so biome borders aren't speckly
    newt = {}
    for p, t_ in world.items():
        if t_ not in (1, 2, 3, 4, 5): continue
        cnt = {t_: 2}
        for q_ in hexn(*p):
            tq = world.get(q_)
            if tq in (1, 2, 3, 4, 5):
                cnt[tq] = cnt.get(tq, 0) + 1
        newt[p] = max(cnt, key=cnt.get)
    world.update(newt)
    return n_

def furnish(world, tgt_placed, ents_all, rich, vast=False):
    """mines/lairs/cities/nodes on a level's cave floor; returns object count.
    vast (v4.24 'full' worlds): surface-like economy instead of dense-cave ratios."""
    got = 0
    floor2 = [p for p, t_ in world.items() if t_ in UG_LAND
              and p not in ents_all and p not in tgt_placed]
    rnd.shuffle(floor2)
    def pl(group, count, spacing):
        nonlocal got
        lst = OBJ.get(group, [])
        if not lst: return
        n_ = 0
        for p in floor2:
            if n_ >= count: break
            if p in tgt_placed: continue
            if any(dist2(p, q_) < spacing * spacing for q_ in tgt_placed): continue
            # the structure's graphic footprint must sit entirely on CARVED floor —
            # never over solid rock (EARTHHEX) or water/lava/ice. Different harvested
            # variants have different footprints, so try a few per spot.
            entry = None
            for cand_ in rnd.sample(lst, min(4, len(lst))):
                if cand_.get('terr') == 0:
                    continue    # water-harvested template (animated hexagon class)
                if all(world.get(c_) in UG_LAND
                       for c_ in entry_foot_cells(p[0], p[1], cand_) if c_ != p):
                    entry = cand_; break
            if entry is None: continue
            tgt_placed[p] = (group, entry)
            n_ += 1; got += 1
    nfloor_ = len(floor2)
    ugc = [g for g in OBJ if g.startswith('ug_city0')]
    if vast:
        # a whole opened WORLD: Mirrored Oasis density (~1 structure / 18 open
        # hexes) and SURFACE-style objects — the reference's UG levels hold real
        # CITY1-4, farms, towers, sites and mines, not just cave fixtures
        for _ in range(max(3, nfloor_ // 62)):            # cities, Mirrored ratio
            sz_ = rnd.choices([1, 2, 3, 4], weights=[45, 25, 18, 12])[0]
            if rnd.random() < RNG_CITY_FRAC:
                grps_ = ['city%d_neutral' % sz_]
            else:
                grps_ = ([g for g in OBJ if g.startswith('city%d_r' % sz_)]
                         or ['city%d_neutral' % sz_])
            pl(rnd.choice(grps_), 1, 7)
        if ugc:                                           # a few cave domes too
            for _ in range(max(1, nfloor_ // 400)):
                pl(rnd.choice(ugc), 1, 7)
        # sites/nodes/towers go BEFORE the farm/mine bulk — placed last with wide
        # spacing they got crowded out (5 of 62 site attempts landed on the L test)
        for _ in range(max(2, nfloor_ // 110)):           # explore sites, mixed
            pl(rnd.choice(('dungeon', 'lair', 'ruins', 'site_cas2', 'ziggurat',
                           'ug_dungeon', 'ug_site_cas2', 'ug_cavemlair')), 1, 5)
        for _ in range(max(2, nfloor_ // 140)):           # power nodes
            pl(rnd.choice(('node_str_node', 'node_str_node+pad1',
                           'ug_node_str_node')), 1, 5)
        for _ in range(max(1, nfloor_ // 270)):           # towers
            pl(rnd.choice(('pad1+towr', 'pad1+watchtower',
                           'ug_pad1+towr', 'ug_pad1+watchtower')), 1, 5)
        pl('farm+pad1', max(2, nfloor_ // 140), 4)
        for g in ('ug_mine', 'mine'):
            pl(g, max(1, nfloor_ // 240), 4)
        pl('ug_building+pad1', max(1, nfloor_ // 350), 8)
        for _ in range(max(1, nfloor_ // 150)):           # misc flavour
            pl(rnd.choice(('misc', 'ug_misc')), 1, 4)
        return got
    pl('ug_mine', max(1, nfloor_ // 18), 4)
    pl('ug_building+pad1', max(1, nfloor_ // 60), 8)   # v4.19: UG Builder's Guild
    if ugc:                             # UG cities on every map, scaled to cave size
        for _ in range(max(1, nfloor_ // (30 if rich else 45))):
            pl(rnd.choice(ugc), 1, 10)
    if rich:
        pl('ug_cavemlair', 1, 10)
        pl('ug_node_str_node', max(1, nfloor_ // 40), 8)
    elif rnd.random() < 0.4:
        pl('ug_cavemlair', 1, 10)
    return got

def ug_dressing(world, wplaced, wdecor):
    """v4.24 'full': vegetation, light scatter and lone (1-hex-footprint) mountains
    on an opened world's land — Mirrored Oasis carries ~550 decors per UG level."""
    fst = make_noise(W, H, rnd, 3, 8.0 * SCALE)
    foots = set()
    for p2, (g2, e2) in wplaced.items():
        foots.update(entry_foot_cells(p2[0], p2[1], e2))
    n_ = 0
    for p, t_ in world.items():
        if p in wplaced or p in foots or p in wdecor: continue
        x, y = p
        if t_ in (1, 2, 3, 4, 5):
            # VEG_WILD, not VEGREC: raw pools hold multi-hex-footprint hills whose
            # skirts would cover neighbouring UG objects/decor (validator mtnfp).
            # Density tuned to Mirrored Oasis (~48% of open land carries decor).
            if VEG_WILD.get(t_) and fst(x, y) > 0.55 and rnd.random() < 0.80:
                wdecor[p] = rnd.choice(VEG_WILD[t_]); n_ += 1
            elif MTN_S1.get(t_) and rnd.random() < 0.05:
                wdecor[p] = rnd.choice(MTN_S1[t_]); n_ += 1
            elif UGVEG and rnd.random() < 0.05:      # cave flora creeps in
                wdecor[p] = rnd.choice(UGVEG); n_ += 1
            elif LIGHTREC.get(t_) and rnd.random() < 0.08:
                wdecor[p] = rnd.choice(LIGHTREC[t_]); n_ += 1
        elif t_ == 12 and UGVEG and rnd.random() < 0.10:
            wdecor[p] = rnd.choice(UGVEG); n_ += 1
    return n_

if LEVELS >= 2 and HAS_L1 and cave_sites:
    l1t_off, s1t, e1t, paint1 = parse_level_paint(1)
    def ug_ok(x, y): return 0 <= x < W and 0 <= y < H and paint1[y][x]
    sysid_of = {}
    carve(UG_SYSTEMS, ug_ok, ugworld, sysid_of, pond_div=30,
          pond_lava=(0.35 if UG_ELABORATE else 0.10),
          conn_prob=(0.6 if UG_ELABORATE else 0.35),
          conn_lava=(0.45 if UG_ELABORATE else 0.30))
    if UG_SURF == 'full':
        nfill1 = fill_ug_world(ugworld, paint1, lavaish=False)
    nugice1 = freeze_ug(ugworld, 0.65)
    nugobj = furnish(ugworld, placed_ug, cave_set, rich=UG_ELABORATE,
                     vast=(UG_SURF == 'full'))
    UGB1 = find_ug_bridges(ugworld)
    if CAVE_UP_L1:
        for site in cave_sites:                          # L1 side of each surface pair
            placed_ug[site] = ('cave_l1', rnd.choice(CAVE_UP_L1))

    # ---- depths (level 2): lava-heavy caves below, reached from L1 down-entrances
    if LEVELS >= 3 and HAS_L2 and CAVE_DEEP:
        l2t_off, s2t, e2t, paint2 = parse_level_paint(2)
        def ug_ok2(x, y): return 0 <= x < W and 0 <= y < H and paint2[y][x]
        DEPTH_FULL = UG_SURF == 'full' and rnd.random() < 0.5
        cand = [p for p, t_ in ugworld.items() if t_ in UG_LAND
                and p not in placed_ug and paint2[p[1]][p[0]]]
        rnd.shuffle(cand)
        n_down = max(1, len(UG_SYSTEMS) * 2 // 3)
        down_sites = []
        for p in cand:
            if len(down_sites) >= n_down: break
            if any(dist2(p, q_) < 64 for q_ in down_sites): continue
            down_sites.append(p)
        used = set()
        for i, a in enumerate(down_sites):               # pair nearby down-holes -> tunnels
            if a in used: continue
            partner = next((b2 for b2 in down_sites[i+1:] if b2 not in used
                            and 8 <= hexdist(a, b2) <= 24 and rnd.random() < 0.6), None)
            if partner:
                used |= {a, partner}
                DEPTH_SYSTEMS.append(dict(kind='tunnel', ent=[a, partner]))
            else:
                used.add(a)
                DEPTH_SYSTEMS.append(dict(kind='pocket', ent=[a]))
        sysid2 = {}
        carve(DEPTH_SYSTEMS, ug_ok2, ugworld2, sysid2, pond_div=20,
              pond_lava=0.75, conn_prob=0.6, conn_lava=0.80)
        if DEPTH_FULL:
            nfill2 = fill_ug_world(ugworld2, paint2, lavaish=True)
        down_set = set(down_sites)
        nugice2 = freeze_ug(ugworld2, 0.40)
        nugobj2 = furnish(ugworld2, placed_ug2, down_set, rich=UG_ELABORATE,
                          vast=DEPTH_FULL)
        UGB2 = find_ug_bridges(ugworld2)
        for p in down_sites:                             # both sides, DEPTHS-type guid
            placed_ug[p] = ('cave_l1', rnd.choice(CAVE_DEEP))
            placed_ug2[p] = ('cave_l1', rnd.choice(CAVE_DEEP))
        ndown = len(down_sites)
        DOWN_SET = set(down_sites)
        if DEPTH_FULL:
            nugdress2 = ug_dressing(ugworld2, placed_ug2, ug_decor2)
        else:
            for p in [p for p, t_ in ugworld2.items() if t_ == 12]:
                if (p not in placed_ug2 and p not in ug_decor2
                        and UGVEG and rnd.random() < 0.14):
                    ug_decor2[p] = rnd.choice(UGVEG)

    if UG_SURF == 'full':
        nugdress = ug_dressing(ugworld, placed_ug, ug_decor)
    elif UG_SURF == 'limited':
        # sunlit pockets: the surface terrain above an entrance seeps onto the cave
        # floor around it (65% of entrances, 4-13 hexes), with a little real veg
        foots_s = set()
        for p2, (g2, e2) in placed_ug.items():
            foots_s.update(entry_foot_cells(p2[0], p2[1], e2))
        ug_grass = []   # v6.4: UG grass cells -> mushroom groves (seed + spread) below
        for site in cave_sites:
            if rnd.random() < 0.35: continue
            blob = {site}; frontier = [site]
            bt = rnd.randrange(5, 14)
            while len(blob) < bt and frontier:
                b_ = rnd.choice(frontier)
                opts = [p2 for p2 in hexn(*b_)
                        if ugworld.get(p2) == 12 and p2 not in blob]
                if not opts:
                    frontier.remove(b_); continue
                p2 = rnd.choice(opts)
                blob.add(p2); frontier.append(p2)
            for p2 in blob:
                if (p2 != site and ugworld.get(p2) == 12
                        and p2 not in placed_ug and p2 not in foots_s):
                    # each hex MIRRORS the surface terrain directly above it
                    # (user spec); wet/void above -> the cave floor stays dirt
                    t0 = grid[p2[1]][p2[0]]
                    if t0 not in (1, 2, 3, 4, 5):
                        continue
                    ugworld[p2] = t0; nsun += 1
                    if t0 == 1:
                        # underground GRASS: mushrooms handled by the grove pass below
                        ug_grass.append(p2)
                        continue
                    # non-grass terrain: occasional mushroom / dead tree (unchanged) —
                    # the sunlight isn't enough for the real thing
                    if rnd.random() < 0.30:
                        dpool = DTREEREC.get(t0) or _DTREE_ALL
                        if _MUSHREC and (rnd.random() < 0.60 or not dpool):
                            ug_decor[p2] = rnd.choice(_MUSHREC)
                        elif dpool:
                            ug_decor[p2] = rnd.choice(dpool)
        # v6.4 (user spec): underground GRASS is mushroom-friendly. Seed mushrooms
        # on grass at a much higher rate than other UG terrain, then let them SPREAD
        # into adjacent/nearby grass so they form dense mushroom groves rather than
        # lone caps.
        if _MUSHREC and ug_grass:
            mush = set()
            for p2 in ug_grass:                        # seeds: ~45% of grass cells
                if p2 in ug_decor or p2 in placed_ug: continue
                if rnd.random() < 0.45:
                    ug_decor[p2] = rnd.choice(_MUSHREC); mush.add(p2)
            for _ in range(4):                         # spread outward into grass
                grew = []
                for p2 in ug_grass:
                    if p2 in mush or p2 in ug_decor or p2 in placed_ug: continue
                    if any(q_ in mush for q_ in hexn(*p2)) and rnd.random() < 0.70:
                        grew.append(p2)
                if not grew: break
                for p2 in grew:
                    ug_decor[p2] = rnd.choice(_MUSHREC); mush.add(p2)
            nmush += len(mush)
    for p in [p for p, t_ in ugworld.items() if t_ == 12 and p not in cave_set]:
        if (p not in placed_ug and p not in ug_decor
                and UGVEG and rnd.random() < 0.14):
            ug_decor[p] = rnd.choice(UGVEG)

# UG footprint hygiene: no decor and no other object inside a UG structure's
# graphic footprint (entrances are immovable — remove the movable offender)
def ug_footfix(world_placed, decor):
    foots = {}
    for p, (g2, e2) in list(world_placed.items()):
        for c_ in entry_foot_cells(p[0], p[1], e2):
            foots.setdefault(c_, p)
    for c_ in foots:
        decor.pop(c_, None)
    for c_, owner in foots.items():
        if c_ in world_placed and c_ != owner:
            if world_placed[c_][0] != 'cave_l1':
                del world_placed[c_]
            elif world_placed.get(owner, ('cave_l1',))[0] != 'cave_l1':
                del world_placed[owner]
ug_footfix(placed_ug, ug_decor)
ug_footfix(placed_ug2, ug_decor2)

# ---- player starts, phase B (v4.14): underground spawns (Dwarf/DarkElf/Goblin) ---
ug_start_race = {}
def ug_place_start(p, lvl):
    world = ugworld if lvl == 1 else ugworld2
    wplaced = placed_ug if lvl == 1 else placed_ug2
    wdecor = ug_decor if lvl == 1 else ug_decor2
    wbridge = UGB1 if lvl == 1 else UGB2
    if not world:
        return False
    r_ = player_race(p)
    floor = [c for c, t_ in world.items() if t_ in UG_LAND
             and c not in wplaced and c not in wbridge]
    rnd.shuffle(floor)
    others = [(x_, y_) for (l_, x_, y_) in start_stack_at if l_ == lvl]
    floor.sort(key=lambda c: -min((hexdist(c, q_) for q_ in others), default=9999))
    pool = [e_ for g in ('ug_city0_r%02x' % r_, 'ug_city0_neutral')
            for e_ in OBJ.get(g, [])]
    for c in floor[:400]:
        if any(dist2(c, q_) < 16 for q_ in wplaced): continue
        if sum(1 for q_ in hexn(*c) if world.get(q_) in UG_LAND) < 3: continue
        entry = None
        for cand_ in rnd.sample(pool, min(6, len(pool))):
            if all(world.get(c_) in UG_LAND
                   for c_ in entry_foot_cells(c[0], c[1], cand_) if c_ != c):
                entry = cand_
                break
        if entry is None: continue
        wplaced[c] = ('ug_city0_start', entry)
        ug_start_race[c] = r_
        for c_ in entry_foot_cells(c[0], c[1], entry):
            wdecor.pop(c_, None)
        if IN_CITY:
            start_city_at[(lvl, c[0], c[1])] = p
            start_stack_at[(lvl, c[0], c[1])] = p
        else:
            wfoot = set(entry_foot_cells(c[0], c[1], entry))
            for q_, (g_, e_) in wplaced.items():
                if q_ != c:
                    wfoot.update(entry_foot_cells(q_[0], q_[1], e_))
            spot = None
            for c2 in sorted(world, key=lambda q_: hexdist(q_, c))[:40]:
                if not 2 <= hexdist(c2, c) <= 3: continue
                if world.get(c2) not in UG_LAND or c2 in wplaced or c2 in wbridge:
                    continue
                if c2 in wfoot: continue    # never under a structure graphic
                spot = c2
                break
            if spot is None:
                start_city_at[(lvl, c[0], c[1])] = p
                spot = c
            else:
                wdecor.pop(spot, None)
            start_stack_at[(lvl, spot[0], spot[1])] = p
        return True
    return False

for p in [p for p in range(1, NPLAYERS + 1) if start_lvl[p] in (1, 2)]:
    lvl = 1 if (start_lvl[p] == 2 and not ugworld2) else start_lvl[p]
    if not ug_place_start(p, lvl):
        if lvl == 2 and ug_place_start(p, 1):
            continue
        start_fallback.append(p)
        print('WARNING: no underground start for player %d, deferring to surface' % p)

# ---- player starts, phase C: late surface fallback -------------------------------
mtn_fp_c = set()
for (mx, my), rec_ in mtn_choice.items():
    mtn_fp_c.update(foot_cells(mx, my, FOOT.get(mtn_rec_guid(rec_), [(0, 0)])))
for p in start_fallback:
    r_ = player_race(p)
    blocked = set(placed) | obj_foot | road | xbridges | tele_land | mtn_fp_c
    cands = [c for c in land if start_cand_ok(c[0], c[1], r_) and c not in blocked]
    rnd.shuffle(cands)
    others = [(x_, y_) for (l_, x_, y_) in start_stack_at if l_ == 0]
    cands.sort(key=lambda c: -min((hexdist(c, q_) for q_ in others), default=9999))
    got = False
    for pos in cands[:400]:
        t = grid[pos[1]][pos[0]]
        entry = gname = None
        for g in ('city%d_r%02x' % (START_SZ, r_), 'city%d_neutral' % START_SZ):
            e_ = pick_entry(g, t)
            if e_ and not foot_clash(pos[0], pos[1], e_) and not any(
                    c_ in blocked or not (0 <= c_[0] < W and 0 <= c_[1] < H)
                    or mtn[c_[1]][c_[0]]
                    for c_ in entry_foot_cells(pos[0], pos[1], e_)):
                entry, gname = e_, g
                break
        if entry is None: continue
        register(pos[0], pos[1], gname, entry)
        city_race[pos] = r_
        for c_ in [pos] + entry_foot_cells(pos[0], pos[1], entry):
            if 0 <= c_[0] < W and 0 <= c_[1] < H:
                veg[c_[1]][c_[0]] = False    # placed after the veg/scatter pass
            scatter.pop(c_, None)
        start_city_at[(0, pos[0], pos[1])] = p
        start_stack_at[(0, pos[0], pos[1])] = p
        got = True
        break
    if not got:
        cand2 = [c for c in land if c not in blocked and not mtn[c[1]][c[0]]
                 and grid[c[1]][c[0]] in (1, 2, 3, 4, 5)]
        pos = rnd.choice(cand2)
        obj_foot.add(pos)
        veg[pos[1]][pos[0]] = False
        scatter.pop(pos, None)
        start_stack_at[(0, pos[0], pos[1])] = p
        print('WARNING: player %d starts without a city' % p)

prebuilt_stacks = {}
for (lvl, x_, y_), p in start_stack_at.items():
    prebuilt_stacks[(lvl, x_, y_)] = build_stack(p, x_, y_, start_party[p])

# ---- record stamping -----------------------------------------------------------
SYL_A = ['bar', 'kel', 'mor', 'tha', 'vel', 'dor', 'ash', 'gal', 'run', 'ista',
         'bel', 'cor', 'dun', 'fal', 'gris', 'hol', 'karn', 'lor', 'nev', 'or']
SYL_B = ['ia', 'or', 'heim', 'wick', 'mar', 'ton', 'dale', 'fell', 'gard', 'lyn',
         'mere', 'os', 'rath', 'stad', 'um', 'wen', 'yr', 'a', 'e', 'il']
def city_name(target_len):
    n = rnd.choice(SYL_A)
    while len(n) < target_len:
        n += rnd.choice(SYL_B)
    return n[:target_len].capitalize()

# city names are pre-rolled so SIGNS can reference them (v4.18); name length is
# pinned by the harvested record (same-length in-place patch)
CITY_NAMES = {}
for (_cx, _cy), (_g, _e) in placed.items():
    if _g.startswith('city') and _e['patch'].get('name'):
        CITY_NAMES[(_cx, _cy)] = city_name(_e['patch']['name'][1])

# v4.20: city WALLS (child f15: 0 none, 1 wood, 2 stone, 3 random —
# City.TCity.SetWallType writes +4C = prop 15) and DEFENDER STRENGTH
# (child f27: 0 none, 1 random, 2 weak, 3 average, 4 strong — the editor's
# DefendersCB writes +74 = prop 27) — randomized per city; every PLAYER SPAWN
# city (all levels) shares ONE roll so starts stay equal. Harvested records
# carried f15=0/f27=3 = the constant "no walls / average" the user saw.
def _roll_wall(): return rnd.choices([0, 1, 2, 3], weights=[25, 25, 20, 30])[0]
def _roll_def():  return rnd.choices([0, 1, 2, 3, 4],
                                     weights=[10, 25, 20, 25, 20])[0]

# v4.21: DEFENDER STRENGTH for defended structures (same value space everywhere:
# 0 none, 1 weak, 2 average, 3 strong, 4 random — GenerateDefenders rolls 1-3
# when it reads 4). Exploration sites (TExplorationSite family) keep it in
# child tag 6; production places (TProductionPlace: Builder's Guild, Shipyard)
# in child tag 9. Rolled per structure at stamp time.
DEF_MODE_TAG = {0x2032B: 6,   # dungeon
                0x2032F: 6,   # monster lair / cave lair
                0x2030B: 6,   # ruins
                0x2039B: 6,   # crypt (EPL_CAS2)
                0x2038F: 6,   # ziggurat / pyramid
                0x2092F: 9,   # builder's guild
                0x204BF: 9}   # shipyard
def _roll_mode(): return rnd.choices([1, 2, 3, 4], weights=[25, 30, 20, 25])[0]
# v6.0: classes whose child f5 = OWNING PLAYER (cities 0x20109 excluded — their
# owner is set deliberately via city_set_owner). Shipyard/guild (TProductionPlace)
# CRASH the editor when the owner isn't a declared player; pool/tower merely
# start pre-owned (unfair) — all get neutralized to 0xFF. 0x2077F (shrine) f5
# semantics unproven (owner-10 maps load fine) — left untouched.
OWNABLE_CLS = (0x204BF, 0x2092F, 0x2043F, 0x2063F)
START_WD = (_roll_wall(), _roll_def())
_spawn_city = set(placed_start) | {(x_, y_) for (l_, x_, y_) in start_city_at
                                   if l_ == 0}
CITY_WD = {}
for (_cx, _cy), (_g, _e) in placed.items():
    if _g.startswith('city'):
        CITY_WD[(0, _cx, _cy)] = (START_WD if (_cx, _cy) in _spawn_city
                                  else (_roll_wall(), _roll_def()))
for _wpl, _lvl in ((placed_ug, 1), (placed_ug2, 2)):
    for (_cx, _cy), (_g, _e) in _wpl.items():
        if 'city' in _g:
            CITY_WD[(_lvl, _cx, _cy)] = (START_WD if _g == 'ug_city0_start'
                                         else (_roll_wall(), _roll_def()))

def compass(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ns = 'north' if dy < 0 else ('south' if dy > 0 else '')
    ew = 'west' if dx < 0 else ('east' if dx > 0 else '')
    if abs(dy) >= 2 * abs(dx) and ns: return ns
    if abs(dx) >= 2 * abs(dy) and ew: return ew
    return (ns + ew) or 'north'

_TERR_SIGN = {
    2: ['Beware: the desert ahead is merciless.',
        'Water is scarce beyond this point.',
        'Sandstorms bury the unwary.'],
    3: ['Bundle up — the frost bites hard past here.',
        'The snows claim careless travellers.',
        'Cold winds ahead. Turn back while you can.'],
    5: ['These wastes are cursed. Tread carefully.',
        'Nothing wholesome grows beyond this marker.',
        'The blight spreads. Keep to the road.'],
    9: ['Turn back — the earth itself burns ahead.',
        'Fire and ash. No road goes further.'],
}
_FAM_SIGN = {
    'mine': ['Miners keep their claims. Trespassers beware.',
             'Ore carts have right of way.'],
    'farm': ['Fresh produce sold at the farmstead.',
             'Keep off the crops!'],
    'towr': ['The tower watches this road.',
             'Travellers must state their business at the tower.'],
    'node': ['Strange energies swirl near this place.',
             'Mages covet the power that dwells here.'],
    'site': ['Danger! Enter the ruins at your own risk.',
             'Many went in. Few came out.'],
    'altar': ['Holy ground — show respect.',
              'Leave an offering, take a blessing.'],
    'misc': ['Rest your horses here.',
             'The old marker stone. Its runes are worn.'],
}
_GENERIC_SIGN = [
    'Bandits roam these parts after dark.',
    'The King\'s law ends here.',
    'Safe travels, stranger.',
    'No tolls for pilgrims.',
    'Lost? So was the one who raised this sign.',
    'Beware of wolves.',
    'Here be monsters.',
    'The old road is safer. This one is faster.',
]

def sign_text(x, y):
    """Location-relevant sign text: nearby city (welcome/direction), nearby
    structure flavor, terrain warnings, generic filler."""
    opts = []
    best = None
    for (cx, cy), nm in CITY_NAMES.items():
        d_ = hexdist((x, y), (cx, cy))
        if best is None or d_ < best[0]:
            best = (d_, (cx, cy), nm)
    if best is not None:
        d_, cpos, nm = best
        if d_ <= 4:
            opts += ['Welcome to %s.' % nm, '%s welcomes the weary.' % nm] * 2
        elif d_ <= 14:
            w_ = compass((x, y), cpos)
            opts += ['%s lies to the %s.' % (nm, w_),
                     'The road to %s runs %s.' % (nm, w_),
                     '%s: %d leagues %s.' % (nm, d_, w_)] * 2
    for (px, py), (g_, _e2) in placed.items():
        if (px, py) == (x, y): continue
        if hexdist((x, y), (px, py)) <= 4:
            fam_ = family(g_)
            if fam_ in _FAM_SIGN:
                opts += _FAM_SIGN[fam_]
    t_ = grid[y][x]
    near_t = {grid[ny][nx] for nx, ny in hexn(x, y)} | {t_}
    for tt_ in near_t:
        if tt_ in _TERR_SIGN:
            opts += _TERR_SIGN[tt_]
    if any(grid[ny][nx] == 0 for nx, ny in hexn(x, y)):
        opts += ['The ferry sank years ago. Swim at your peril.',
                 'High tide drowns this path.']
    opts += _GENERIC_SIGN
    return rnd.choice(opts)

def sign_stamped(entry, x, y, t):
    """Stamp a sign record, then rewrite the 0x20103 child's f7 text (u32
    length-prefixed) with a location-relevant line; record rebuilt because the
    text length changes."""
    rec = stamp(entry, x, y, t)
    kids_ = rec_children(rec)
    out_ = []
    for ch_ in kids_:
        cls_ = struct.unpack_from('<I', ch_, 0)[0] + 1
        if cls_ == 0x20103:
            txt = sign_text(x, y).encode('latin1', 'replace')[:200]
            fl_ = [(t2, struct.pack('<I', len(txt)) + txt if t2 == 7 else v2)
                   for t2, v2 in parse_fields(ch_, 4, len(ch_))]
            ch_ = enc_record(cls_, fl_)
        out_.append(ch_)
    return build_hexrec(out_)

def stamp(entry, x, y, t, race=None, cave_side=None, wd=None):
    """cave_side: 1 = upper level of an entrance pair, 0 = lower level. The cave child's
    field 6 encodes this; a pair with two same-side ends crashes the editor's CloseHSM.
    wd: (wall_type, defenders) pair patched into the CITY child (f15/f27, v4.20)."""
    rec = bytearray(bytes.fromhex(entry['rec']))
    p = entry['patch']
    if cave_side is not None:
        hdr, p0 = tbl(rec, 0)
        for o2 in sorted(o for t2, o in hdr.items() if t2 >= 0x32):
            if struct.unpack_from('<I', rec, p0 + o2)[0] + 1 == 0x2037F:
                f3, b3 = tbl(rec, p0 + o2 + 4)
                if 6 in f3: rec[b3 + f3[6]] = cave_side
                break
    if wd is not None:
        hdr, p0 = tbl(rec, 0)
        for o2 in sorted(o for t2, o in hdr.items() if t2 >= 0x32):
            if struct.unpack_from('<I', rec, p0 + o2)[0] + 1 == 0x20109:
                f3, b3 = tbl(rec, p0 + o2 + 4)
                if 15 in f3: rec[b3 + f3[15]] = wd[0]
                if 27 in f3: rec[b3 + f3[27]] = wd[1]
                break
    # v4.21: randomize defender strength on defended structures (sites f6,
    # production places f9); classes not in DEF_MODE_TAG are untouched.
    # v6.0: OWNABLE structures (shipyard/guild/tower/reflecting pool/shrine)
    # may carry their SOURCE map's owner in child f5 — an owner above this
    # map's player count crashes the editor at load ("Oh dear, it's the
    # end...."; proven by f5 surgery on seed 743784: shipyard f5=4, 3 players).
    # 0xFF = no owner (41 shipyards were harvested that way). Sites' f5 is a
    # UNIT LIST (v4.21), never touched here.
    hdr, p0 = tbl(rec, 0)
    for o2 in sorted(o for t2, o in hdr.items() if t2 >= 0x32):
        cls_ = struct.unpack_from('<I', rec, p0 + o2)[0] + 1
        dtag = DEF_MODE_TAG.get(cls_)
        if dtag:
            f3, b3 = tbl(rec, p0 + o2 + 4)
            if dtag in f3:
                rec[b3 + f3[dtag]] = _roll_mode()
        if cls_ in OWNABLE_CLS:
            f3, b3 = tbl(rec, p0 + o2 + 4)
            if 5 in f3:
                rec[b3 + f3[5]] = 0xFF
    # terrain variant: water objects keep animated water variants (matches the template's
    # animated hexagon child class); land objects get static variants of the dest terrain
    var = terr_var[0] if t == 0 else (LAND_STATIC.get(t) or terr_var[t])
    struct.pack_into('<I', rec, p['hexvar'], rnd.choice(var)[1])
    for (xo, yo) in p['coords']:
        rec[xo] = x & 0xFF; rec[yo] = y & 0xFF
    for off in p['ids']:
        struct.pack_into('<I', rec, off, fresh_id())
    if p['name']:
        off, ln = p['name']
        nm_ = CITY_NAMES.get((x, y))                 # pre-rolled (signs use it)
        if nm_ is None or len(nm_) != ln:
            nm_ = city_name(ln)
        rec[off:off+ln] = nm_.encode('latin1')
    if race is not None and p.get('race13'):
        rec[p['race13']] = race
    return bytes(rec)

# ---- write field stream --------------------------------------------------------
def child(res_cls, uid):
    return struct.pack('<I', res_cls - 1) + b'\x01\x01\x00' + struct.pack('<I', uid)

def place_record(payload, x, y):
    rec = bytearray(payload)
    dc = 16
    ct, cbb = tbl(rec, dc + 4)
    if 3 in ct: rec[cbb + ct[3]] = x & 0xFF
    if 4 in ct: rec[cbb + ct[4]] = y & 0xFF
    return bytes(rec)

new_stream = bytearray()
q, idx, nveg, nmtn, nter, nobj, nroad, nbridge = s, 0, 0, 0, 0, 0, 0, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', inner, q)[0]
    rec = bytes(inner[q + 4:q + 4 + L])
    x, y = idx % W, idx // W
    if paint[y][x]:
        t = grid[y][x]
        if (x, y) in placed:
            g, entry = placed[(x, y)]
            # v6.0b (user): structures on SURFACE dirt keep their surface records
            # but get a STEPPE hexagon beneath — it blends into the dirt field,
            # while the hu_ca cave tile looked glitched under them. (UG-record
            # alternatives would break under Path of Life etc., which repaint
            # surface terrain.) UG levels keep dirt hexes — this is L0 only.
            t_s = 4 if t == 12 else t
            nrec = (entry['prebuilt'] if g == 'tele' else
                    sign_stamped(entry, x, y, t_s) if g == 'signs' else
                    stamp(entry, x, y, t_s, city_race.get((x, y)),
                          cave_side=(1 if g == 'cave' else None),
                          wd=CITY_WD.get((0, x, y))))
            if (0, x, y) in start_city_at:
                nrec = city_set_owner(nrec, start_city_at[(0, x, y)])
            if (0, x, y) in start_stack_at:
                nrec = append_child(nrec, prebuilt_stacks[(0, x, y)])
            new_stream += struct.pack('<I', len(nrec)) + nrec
            nobj += 1
        elif (0, x, y) in start_stack_at:
            hcls, huid = rnd.choice(LAND_STATIC.get(t) or terr_var[t])
            rrec = append_child(b'\x01\x32\x00' + child(hcls, huid),
                                prebuilt_stacks[(0, x, y)])
            new_stream += struct.pack('<I', len(rrec)) + rrec
        elif (x, y) in road or (x, y) in xbridges:
            if t in WET_T:                    # bridge: wet hexagon + 0x2087B child
                hcls, huid = rnd.choice(terr_var[t])
                rrec = (b'\x02\x32\x00\x33\x0b' + child(hcls, huid)
                        + child(0x2087B, BRIDGE_GUID[t]))
                nbridge += 1
            else:
                hcls, huid = rnd.choice(LAND_STATIC.get(t) or terr_var[t])
                rrec = (b'\x02\x32\x00\x33\x0b' + child(hcls, huid)
                        + struct.pack('<I', 0x20164) + b'\x01\x01\x00'
                        + struct.pack('<I', ROAD_GUID[t]))
                nroad += 1
            new_stream += struct.pack('<I', len(rrec)) + rrec
        elif mtn[y][x]:
            new_stream += struct.pack('<I', 33) + place_record(mtn_choice[(x, y)], x, y)
            nmtn += 1
        elif veg[y][x]:
            pool = VEG_WILD.get(t) or VEGREC[t]
            new_stream += struct.pack('<I', 33) + place_record(rnd.choice(pool), x, y)
            nveg += 1
        elif (x, y) in scatter:
            if scatter[(x, y)] == 'tree':
                src = (HILLREC[t] if HILLREC.get(t) and rnd.random() <
                       (min(0.90, _sv(0.50, 0.12))
                        if PAT(x, y) == 'highlands' else 0.12)
                       else TREEREC[t])                          # rare lone hills
            else:
                src = LIGHTREC[t]
            new_stream += struct.pack('<I', 33) + place_record(rnd.choice(src), x, y)
            nveg += 1
        else:
            hcls, huid = rnd.choice(terr_var[t])
            new_stream += struct.pack('<I', 14) + b'\x01\x32\x00' + child(hcls, huid)
        nter += 1
    else:
        new_stream += struct.pack('<I', L) + rec
    q += 4 + L; idx += 1

delta = len(new_stream) - (e - s)
out = bytearray(inner[:s]) + new_stream + inner[e:]
kind, pos = tbl_entry_pos(out, loff + 4, 1)
struct.pack_into('<I', out, pos, struct.unpack_from('<I', out, pos)[0] + delta)
for lid, lo in lvls:
    if lkb + lo > loff:
        k2, p2 = tbl_entry_pos(out, cb + cf[1], lid)
        v = struct.unpack_from('<I', out, p2)[0] if k2 == 'u32' else out[p2]
        if k2 == 'u32': struct.pack_into('<I', out, p2, v + delta)
        else: out[p2] = v + delta

# ---- rewrite level 1 (underground); its bytes all sit after s, shifted by delta --
nfloor = nugdec = nugb1 = 0
delta1 = 0
if HAS_L1 and ugworld:
    l1o = l1t_off + delta
    s1, e1 = s1t + delta, e1t + delta
    ns1 = bytearray()
    q, idx = s1, 0
    while q < e1 and idx < W * H:
        L_ = struct.unpack_from('<I', out, q)[0]
        rec = bytes(out[q+4:q+4+L_])
        x, y = idx % W, idx // W
        pnt = (x, y)
        if pnt in placed_ug:
            g2, entry2 = placed_ug[pnt]
            side = None
            if g2 == 'cave_l1':
                side = 1 if pnt in DOWN_SET else 0   # down-hole = upper end of L1-L2 pair
            t_ug = ugworld.get(pnt)                  # v4.24: match the ground under it
            nr = stamp(entry2, x, y, t_ug if t_ug in (1, 2, 3, 4, 5) else 12,
                       ug_start_race.get(pnt), cave_side=side,
                       wd=CITY_WD.get((1, x, y)))
            if (1, x, y) in start_city_at:
                nr = city_set_owner(nr, start_city_at[(1, x, y)])
            if (1, x, y) in start_stack_at:
                nr = append_child(nr, prebuilt_stacks[(1, x, y)])
            ns1 += struct.pack('<I', len(nr)) + nr
        elif (1, x, y) in start_stack_at:
            t_ug = ugworld.get(pnt)
            hcls, huid = rnd.choice((LAND_STATIC.get(t_ug) or terr_var[t_ug])
                                    if t_ug in (1, 2, 3, 4, 5) else terr_var[12])
            nr = append_child(b'\x01\x32\x00' + child(hcls, huid),
                              prebuilt_stacks[(1, x, y)])
            ns1 += struct.pack('<I', len(nr)) + nr
        elif pnt in UGB1:
            t_ = ugworld[pnt]
            vl = (UG_LAVA_VAR if t_ == 9 else
                  terr_var.get(t_) or terr_var.get(10) or terr_var[12])
            hcls, huid = rnd.choice(vl)
            nr = (b'\x02\x32\x00\x33\x0b' + child(hcls, huid)
                  + child(0x2087B, BRIDGE_GUID[t_]))
            ns1 += struct.pack('<I', len(nr)) + nr
            nugb1 += 1
        elif pnt in ug_decor:
            dv = ug_decor[pnt]
            ns1 += struct.pack('<I', len(dv)) + place_record(dv, x, y)
            nugdec += 1
        elif pnt in ugworld:
            t_ = ugworld[pnt]
            vl = (terr_var[12] if t_ == 12 else
                  UG_LAVA_VAR if t_ == 9 else
                  terr_var.get(t_) or terr_var.get(10) or terr_var[12])
            hcls, huid = rnd.choice(vl)
            ns1 += struct.pack('<I', 14) + b'\x01\x32\x00' + child(hcls, huid)
            nfloor += 1
        else:
            ns1 += struct.pack('<I', L_) + rec
        q += 4 + L_; idx += 1
    delta1 = len(ns1) - (e1 - s1)
    out = bytearray(out[:s1]) + ns1 + out[e1:]
    k1, p1 = tbl_entry_pos(out, l1o + 4, 1)
    struct.pack_into('<I', out, p1, struct.unpack_from('<I', out, p1)[0] + delta1)
    for lid, lo in lvls:                       # levels after L1 (e.g. level 2) shift too
        if lkb + lo > l1t_off:
            k2, p2 = tbl_entry_pos(out, cb + cf[1], lid)
            v = struct.unpack_from('<I', out, p2)[0] if k2 == 'u32' else out[p2]
            if k2 == 'u32': struct.pack_into('<I', out, p2, v + delta1)
            else: out[p2] = v + delta1

# ---- rewrite level 2 (the depths); shifted by both earlier deltas ----------------
nfloor2 = nugdec2 = nugb2 = 0
if HAS_L2 and ugworld2:
    l2o = l2t_off + delta + delta1
    s2, e2 = s2t + delta + delta1, e2t + delta + delta1
    ns2 = bytearray()
    q, idx = s2, 0
    while q < e2 and idx < W * H:
        L_ = struct.unpack_from('<I', out, q)[0]
        rec = bytes(out[q+4:q+4+L_])
        x, y = idx % W, idx // W
        pnt = (x, y)
        if pnt in placed_ug2:
            g2, entry2 = placed_ug2[pnt]
            t_ug = ugworld2.get(pnt)                 # v4.24: match the ground under it
            nr = stamp(entry2, x, y, t_ug if t_ug in (1, 2, 3, 4, 5) else 12,
                       ug_start_race.get(pnt),
                       cave_side=(0 if g2 == 'cave_l1' else None),   # lower end
                       wd=CITY_WD.get((2, x, y)))
            if (2, x, y) in start_city_at:
                nr = city_set_owner(nr, start_city_at[(2, x, y)])
            if (2, x, y) in start_stack_at:
                nr = append_child(nr, prebuilt_stacks[(2, x, y)])
            ns2 += struct.pack('<I', len(nr)) + nr
        elif (2, x, y) in start_stack_at:
            t_ug = ugworld2.get(pnt)
            hcls, huid = rnd.choice((LAND_STATIC.get(t_ug) or terr_var[t_ug])
                                    if t_ug in (1, 2, 3, 4, 5) else terr_var[12])
            nr = append_child(b'\x01\x32\x00' + child(hcls, huid),
                              prebuilt_stacks[(2, x, y)])
            ns2 += struct.pack('<I', len(nr)) + nr
        elif pnt in UGB2:
            t_ = ugworld2[pnt]
            vl = (UG_LAVA_VAR if t_ == 9 else
                  terr_var.get(t_) or terr_var.get(10) or terr_var[12])
            hcls, huid = rnd.choice(vl)
            nr = (b'\x02\x32\x00\x33\x0b' + child(hcls, huid)
                  + child(0x2087B, BRIDGE_GUID[t_]))
            ns2 += struct.pack('<I', len(nr)) + nr
            nugb2 += 1
        elif pnt in ug_decor2:
            dv = ug_decor2[pnt]
            ns2 += struct.pack('<I', len(dv)) + place_record(dv, x, y)
            nugdec2 += 1
        elif pnt in ugworld2:
            t_ = ugworld2[pnt]
            vl = (terr_var[12] if t_ == 12 else
                  UG_LAVA_VAR if t_ == 9 else
                  terr_var.get(t_) or terr_var.get(10) or terr_var[12])
            hcls, huid = rnd.choice(vl)
            ns2 += struct.pack('<I', 14) + b'\x01\x32\x00' + child(hcls, huid)
            nfloor2 += 1
        else:
            ns2 += struct.pack('<I', L_) + rec
        q += 4 + L_; idx += 1
    delta2 = len(ns2) - (e2 - s2)
    out = bytearray(out[:s2]) + ns2 + out[e2:]
    k3, p3 = tbl_entry_pos(out, l2o + 4, 1)
    struct.pack_into('<I', out, p3, struct.unpack_from('<I', out, p3)[0] + delta2)

struct.pack_into('<I', out, ID_POS, next_id)    # id counter, after ALL levels stamped

# ---- root splices (v4.14): players (21) + hero-library twins (24/44) --------------
# Player records from Slugfest 12P with f30 replaced by our constructed leader and
# gold rescaled; the hero library loses every hero copied into a leader or granted
# as a starting hero. Each splice shifts later root fields (u32 table entries).
def splice_root(buf, tag, newbytes):
    r2, base2 = tbl(buf, 0x13)
    o_ = r2[tag]
    later = [oo for oo in r2.values() if oo > o_]
    a_, b_ = base2 + o_, base2 + (min(later) if later else len(buf))
    delta_ = len(newbytes) - (b_ - a_)
    buf2 = bytearray(buf[:a_]) + newbytes + buf[b_:]
    p_ = 0x13
    bb_ = buf2[p_]; p_ += 1
    nd_ = 0
    if bb_ & 0x80:
        nd_ = struct.unpack_from('<I', buf2, p_)[0]; p_ += 4
    for _ in range(bb_ & 0x7F):
        assert buf2[p_ + 1] <= o_, 'byte entry after spliced root field'
        p_ += 2
    for _ in range(nd_):
        t_, oo_ = struct.unpack_from('<II', buf2, p_)
        if oo_ > o_:
            struct.pack_into('<I', buf2, p_ + 4, oo_ + delta_)
        p_ += 8
    return buf2

def child_table_bytes(recs):
    pairs, off_ = [], 0
    for r_ in recs:
        pairs.append(off_); off_ += len(r_)
    return enc_tblhdr(list(enumerate(pairs))) + b''.join(recs)

if start_stack_at:
    gold = max(250, min(1000, 3000 // NPLAYERS))
    # v4.19: player f3 = TPlayerType (0 Human, 1-3 CPU Warrior/Knight/Lord,
    # 4 Independent, 6 CPU King, 7 CPU EMPEROR — always Emperor by default);
    # f29 = TPlayerBehavior (0 Normal, 1 Aggressor, 2 Defender, 3 Expander,
    # 4 Scorcher, 5 Random) — 60% Normal, else 10% each of 1-4 (Slugfest's
    # donors carried f29=1 = the "always Aggressive" the user saw)
    behav = {p: (0 if rnd.random() < 0.6 else rnd.choice([1, 2, 3, 4]))
             for p in range(1, NPLAYERS + 1)}
    precs = []
    for i in range(NPLAYERS + 1):
        fl = []
        for t_, v_ in KIT_PLAYERS[i]:
            if i > 0 and t_ == 3:
                v_ = b'\x07'                 # CPU Emperor
            elif i > 0 and t_ == 5:
                v_ = struct.pack('<I', gold)
            elif i > 0 and t_ == 29:
                v_ = bytes([behav[i]])
            elif i > 0 and t_ == 30:
                v_ = leaders[i][4:]          # leader record minus its class u32
            fl.append((t_, v_))
        precs.append(enc_record(0x20021, fl))
    new21 = (bytes.fromhex(PLAYER_KIT['f21_prefix'])
             + bytes([PLAYER_KIT['f2_val']]) + child_table_bytes(precs))
    # library = remaining heroes ONLY (v4.17). A 0x20233 entry in the library
    # means "free/unplaced leader" to the editor: TLeader.Activate hooks the
    # LAST activated leader into player.Leader, so lib entries (loaded after
    # the map levels) clobbered the placed leaders and the Leaders UI showed
    # every leader as "Free". Official maps never mix the two forms — template
    # = lib-only (Free), AtF/Slugfest = placed stack + f30 only (Used).
    # AOW_DBG=libleaders restores the v4.15/16 append for experiments.
    if 'nolib' in DBG:
        keep = [i for i in range(len(LIB)) if i not in used_lib]
        librecs = [bytes.fromhex(LIB[i]['rec']) for i in keep]
    else:
        keep = [i for i in range(len(LIB))
                if i not in used_lib and not LIB[i]['leaderlike']]
        librecs = [bytes.fromhex(LIB[i]['rec']) for i in keep]
        if 'libleaders' in DBG:
            librecs += [leaders[p] for p in range(1, NPLAYERS + 1)]
    newlib = b'\x01\x14\x00' + b'\x01\x01\x00' + child_table_bytes(librecs)
    out = splice_root(out, 44, newlib)
    out = splice_root(out, 24, newlib)
    out = splice_root(out, 21, new21)
    _RN = ['Human', 'Azrac', 'Lizard', 'Frostling', 'Elf', 'Halfling',
           'Dwarf', 'Highman', 'DarkElf', 'Orc', 'Goblin', 'Undead']
    print('players: %d [%s], gold %d, size-%d %s%s | leader lvl %d'
          ' | party slots %s | heroes used %d -> library %d heroes'
          ' + %d leader entries | UG starts %d'
          % (NPLAYERS, ', '.join(_RN[r] for r in _lineup), gold, START_SZ,
             'IN city' if IN_CITY else 'NEAR own-race city',
             ', +hero each' if HERO_START else '', LEADER_LVL, COMP,
             len(used_lib), len(keep),
             NPLAYERS if 'libleaders' in DBG else 0,
             sum(1 for k in start_stack_at if k[0] > 0)))

blob = b'CFS\x00\x02' + zlib.compress(bytes(out), 9)
open(OUT, 'wb').write(blob)
CH = {0: '~', 1: '.', 2: 'd', 3: '*', 4: ',', 5: 'w', 6: '#', 9: 'L', None: ' ',
      12: ':', 10: 'u'}    # v4.24: surface dirt fields / UG-water ponds
OCH = {'city1+pad1': 'C', 'city2+pad2': 'C', 'city3+pad3': 'C', 'city4+pad4': 'C',
       'farm+pad1': 'f', 'mine': '$', 'pad1+towr': 't'}
print('scatter: %d hexes | densities %s + %.1f%% trees'
      % (nlight, {t: '%.0f%%' % (100*v) for t, v in sorted(LIGHT_D.items())},
         100 * (_TD_HL if 'highlands' in TPRESETS else 0.01)))
ntun = sum(1 for s_ in UG_SYSTEMS if s_['kind'] == 'tunnel')
ntun2 = sum(1 for s_ in DEPTH_SYSTEMS if s_['kind'] == 'tunnel')
ugc1 = sum(1 for g_, _ in placed_ug.values() if 'city' in g_)
ugc2 = sum(1 for g_, _ in placed_ug2.values() if 'city' in g_)
print('ug cities: %d on L1, %d in depths' % (ugc1, ugc2))
print('underground: %s | %d systems (%d tunnels incl %d landmass-links, %d pockets),'
      ' %d entrances, %d carved (%d floor/pond rewrites), %d objects, %d decor'
      % ('ELABORATE' if UG_ELABORATE else 'limited', len(UG_SYSTEMS), ntun, n_lm_tun,
         len(UG_SYSTEMS) - ntun, ncave, len(ugworld), nfloor,
         nugobj + len(cave_sites), nugdec))
print('depths: %d systems (%d tunnels), %d down-entrances, %d carved (%d rewrites),'
      ' %d objects, %d decor'
      % (len(DEPTH_SYSTEMS), ntun2, ndown, len(ugworld2), nfloor2, nugobj2, nugdec2))
print('xlevel: surf-dirt=%s (%d dirt, %d pond) | ug-surface=%s'
      ' (sunlit %d, %d mushroom-grove | L1 world +%d cells dress %d |'
      ' depths world%s +%d cells dress %d)'
      % (SURF_DIRT, ndirt, npond, UG_SURF or 'off', nsun, nmush, nfill1, nugdress,
         '=ON' if DEPTH_FULL else '=off', nfill2, nugdress2))
miso = sum(1 for p in mtnset if mtn[p[1]][p[0]]
           and not any(mtn[q_[1]][q_[0]] for q_ in hexn(*p)))
mleft = sum(1 for p in mtnset if mtn[p[1]][p[0]])
print('rivers: %d (%d hexes) | mountains: %d placed, %d survive, %d isolated (%.0f%%)'
      ' | bridges: %d road + %d standalone surface, %d L1, %d L2'
      % (len(sources), len(river), len(mtnset), mleft, miso,
         (100.0 * miso / mleft if mleft else 0), nbridge - len(xbridges), len(xbridges),
         nugb1, nugb2))
print('ice: %d surface hexes | UG ice: %d L1, %d depths | teleporters: %d'
      ' (%d pairs, %d one-way)'
      % (nice, nugice1, nugice2, ntele, npairs, noneway))
print('seed %d | %dx%d | %d ter %d veg %d mtn %d road | %d objects (%d cities, %d farms,'
      ' %d mines, %d towers, %d nodes, %d sites, %d misc) | ids %d.. | %+d B -> %s'
      % (SEED, W, H, nter, nveg, nmtn, nroad, nobj, ncities, nfarm, nmine, ntowr, nnode,
         nsite, nmisc, next_id, delta, OUT))
for y in range(H):
    row = ''
    for x in range(W):
        if (x, y) in placed:
            row += 'C' if placed[(x, y)][0].startswith('city') else OCH.get(placed[(x, y)][0], 'o')
        elif (x, y) in xbridges or ((x, y) in road and grid[y][x] in WET_T): row += 'B'
        elif (x, y) in road: row += '='
        elif mtn[y][x]: row += '^'
        elif veg[y][x]: row += 'T'
        elif (x, y) in scatter: row += ("'" if scatter[(x, y)] == 'light' else 'T')
        else: row += CH[grid[y][x]]
    print(row)
