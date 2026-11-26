# -*- coding: utf-8 -*-
"""Harvest the player-start kit (player_kit.pkl, v2).

Sources:
  Slugfest 12P  — root-21 player records (13, parsed to ordered field lists so the
                  generator can rebuild them with a new f30 leader + gold)
  xTemplate S   — the DEFAULT HERO LIBRARY (root 24/44 twins, 195 entries): raw
                  record + race (f12/f8), name (f10), epithet (f11), xp (f7),
                  gender (f15)
  After the Fall — party-unit pool: every 0x20214 record in the 12 player start
                  stacks (raw + type + donor leader name, whose enchant-caster
                  strings get rewritten at generation); one fresh leader record
                  (Graham) as the structural reference; start-city CITY-child tag
                  order (for the f5=owner insertion point)

Format facts (see HSM_Map_Format_Objects.md):
  race ids (HERORES cid order): 0 Human 1 Azrac 2 Lizard 3 Frostling 4 Elf
  5 Halfling 6 Dwarf 7 Highmen 8 DarkElf 9 Orc 10 Goblin 11 Undead
  leader = 0x20233, f8 = 36+race (HERORES leader cid), f12 = race
  CITY child f5 = owning player (absent = independent)
Usage: py harvest_players.py
"""
import struct, zlib, os, pickle

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

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

def parse_fields(dd, tbl_pos, end):
    """[tbl][data] at tbl_pos..end -> ordered [(tag, payload bytes)]."""
    f, base = tbl(dd, tbl_pos)
    fo = sorted(f.items(), key=lambda kv: kv[1])
    out = []
    for j, (t, o) in enumerate(fo):
        st = base + o
        en = base + fo[j+1][1] if j+1 < len(fo) else end
        out.append((t, bytes(dd[st:en])))
    return out

def pascal(b, p):
    return bytes(b[p+1:1+p+b[p]]).decode('latin1')

def load(path):
    return zlib.decompress(open(path, 'rb').read()[5:])

def root_spans(inner):
    rt, bs = tbl(inner, 0x13)
    ro = sorted(rt.items(), key=lambda kv: kv[1])
    spans = {}
    for i, (tg, off) in enumerate(ro):
        end = bs + ro[i+1][1] if i+1 < len(ro) else len(inner)
        spans[tg] = (bs + off, end)
    return rt, bs, spans

def child_table(inner, pos):
    kids, kb = tbl(inner, pos)
    return sorted(kids.items(), key=lambda kv: kv[1]), kb

# ---- 1) Slugfest 12P player records --------------------------------------------
inner = load(r'Scenario\Custom\AoWx - Slugfest (12P).hsm')
rt, bs, spans = root_spans(inner)
a21, e21 = spans[21]
f21, p21 = tbl(inner, a21)
prefix = bytes(inner[a21:p21])
f2_val = inner[p21 + f21[2]]
ko, kb = child_table(inner, p21 + f21[1])
players = []
for i, (pid, off) in enumerate(ko):
    cs = kb + off
    ce = kb + ko[i+1][1] if i+1 < len(ko) else e21
    assert struct.unpack_from('<I', inner, cs)[0] + 1 == 0x20021
    fl = parse_fields(inner, cs + 4, ce)
    players.append([(t, v.hex()) for t, v in fl])
    assert pid == i
print('players:', len(players))

# ---- 2) template hero library ---------------------------------------------------
innT = load(r'Scenario\Custom\xTemplate Small.hsm')
rtT, bsT, spansT = root_spans(innT)
a24, e24 = spansT[24]
a44, e44 = spansT[44]
assert innT[a24:e24] == innT[a44:e44], 'root 24/44 twins differ in template!'
f0, b0 = tbl(innT, a24)
inf, ib = tbl(innT, b0 + f0[20])
ho, hkb = child_table(innT, ib + inf[1])
heroes = []
for i, (hid, off) in enumerate(ho):
    cs = hkb + off
    ce = hkb + ho[i+1][1] if i+1 < len(ho) else e24
    cls = struct.unpack_from('<I', innT, cs)[0] + 1
    assert cls in (0x20231, 0x20233), hex(cls)
    fl = parse_fields(innT, cs + 4, ce)
    fd = dict(fl)
    f8 = fd[8][0] if 8 in fd else 0
    race = fd[12][0] if 12 in fd else (f8 if f8 < 12 else 0)
    heroes.append(dict(
        rec=bytes(innT[cs:ce]).hex(), cls=cls,
        fields=[(t, v.hex()) for t, v in fl],
        race=race, leaderlike=(f8 >= 36 or cls == 0x20233),
        name=pascal(innT, 0) if False else (fd[10][1:1+fd[10][0]].decode('latin1') if 10 in fd else ''),
        epithet=(fd[11][1:1+fd[11][0]].decode('latin1') if 11 in fd else ''),
        xp=(fd[7][0] if 7 in fd else 0),
        gender=(fd[15][0] if 15 in fd else 0)))
import collections
per_race = collections.Counter(h['race'] for h in heroes if not h['leaderlike'])
print('library: %d heroes (%d leader-like), per race: %s' %
      (len(heroes), sum(h['leaderlike'] for h in heroes), dict(sorted(per_race.items()))))
assert all(per_race.get(r, 0) >= 2 for r in range(12)), 'race with <2 heroes'

# ---- 3) AtF party units, leader reference, city tag order ----------------------
innA = load(r'Scenario\Custom\AoWx - After the Fall.hsm')
rtA, bsA, spansA = root_spans(innA)
kidsA, kbA = tbl(innA, bsA + rtA[1])
cs0 = kbA + sorted(kidsA.items(), key=lambda kv: kv[1])[0][1]
cf, cb = tbl(innA, cs0 + 4)
W, H = innA[cb + cf[3]], innA[cb + cf[4]]
lf_all, lkb = tbl(innA, cb + cf[1])
lf, lb = tbl(innA, lkb + lf_all[0] + 4)
s, e = lb + lf[6], lb + lf[1]

party_units = []
leader_ref = None
city_tag_order = None
q, idx = s, 0
while q < e and idx < W * H:
    L = struct.unpack_from('<I', innA, q)[0]
    x, y = idx % W, idx // W
    rec = bytes(innA[q+4:q+4+L])
    q += 4 + L; idx += 1
    if len(rec) <= 60:
        continue
    try:
        hdr, p0 = tbl(rec, 0)
    except Exception:
        continue
    offs = sorted(o for t, o in hdr.items() if t >= 0x32)
    bounds = [p0 + o for o in sorted(hdr.values())] + [len(rec)]
    spans_c = []
    for o in offs:
        cs = p0 + o
        ce = next(b_ for b_ in bounds if b_ > cs)
        spans_c.append((struct.unpack_from('<I', rec, cs)[0] + 1, cs, ce))
    stack = next((sp for sp in spans_c if sp[0] == 0x20218), None)
    if stack is None:
        continue
    sf, sb = tbl(rec, stack[1] + 4)
    nf, np_ = tbl(rec, sb + sf[10])
    if 4 not in nf:
        continue                                   # neutral stack
    owner = rec[np_ + nf[4]]
    city = next((sp for sp in spans_c if sp[0] == 0x20109), None)
    if city is not None and city_tag_order is None:
        fC, bC = tbl(rec, city[1] + 4)
        city_tag_order = [t for t, _ in sorted(fC.items(), key=lambda kv: kv[1])]
    uf, ub = tbl(rec, np_ + nf[1])
    uo = sorted(uf.items(), key=lambda kv: kv[1])
    lname = ''
    urecs = []
    for i, (uid, uoff) in enumerate(uo):
        us = ub + uoff
        ue = ub + uo[i+1][1] if i+1 < len(uo) else stack[2]
        cls = struct.unpack_from('<I', rec, us)[0] + 1
        fl = parse_fields(rec, us + 4, ue)
        fd = dict(fl)
        if cls == 0x20233:
            lname = fd[10][1:1+fd[10][0]].decode('latin1')
            if leader_ref is None or lname == 'Graham':
                leader_ref = dict(rec=bytes(rec[us:ue]).hex(),
                                  fields=[(t, v.hex()) for t, v in fl], name=lname)
        elif cls == 0x20214:
            urecs.append(dict(rec=bytes(rec[us:ue]).hex(),
                              fields=[(t, v.hex()) for t, v in fl],
                              typ=struct.unpack('<I', fd[2])[0]))
    for u in urecs:
        u['caster'] = lname
        party_units.append(u)

types = collections.Counter(u['typ'] for u in party_units)
print('party units: %d records, types %s' % (len(party_units), dict(types.most_common())))
print('leader ref:', leader_ref['name'])
print('city child tag order:', city_tag_order)
assert party_units and leader_ref and city_tag_order and 5 in city_tag_order

# ---- 4) Unitres: per-race unit blocks (18 slots) + stats for record construction --
# Unit-type id = race block base + slot. Block order swaps Lizard/Frostling vs the
# race-id order. Shared (raceless) units live at ids >= 216.
du = open(r'Release/Unitres.pfs', 'rb').read()
def utbl(p):
    b = du[p]; p += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from('<I', du, p)[0]; p += 4
    pairs = []
    for _ in range(nb): pairs.append((du[p], du[p+1])); p += 2
    for _ in range(nd):
        pairs.append(struct.unpack_from('<II', du, p)); p += 8
    return {t: p + o for t, o in pairs}, p
uroot, _ = utbl(7)
ub0 = du[uroot[1]]; uq = uroot[1] + 1
und = 0
if ub0 & 0x80: und = struct.unpack_from('<I', du, uq)[0]; uq += 4
ukp = []
for _ in range(ub0 & 0x7F): ukp.append((du[uq], du[uq+1])); uq += 2
for _ in range(und): ukp.append(struct.unpack_from('<II', du, uq)); uq += 8
ukb = uq
unit_stats = {}
for cid, rel in ukp:
    t, tb = utbl(ukb + rel + 4)
    if 10 not in t: continue
    n = du[t[10]]
    name = du[t[10]+1:t[10]+1+n].decode('latin1')
    if 11 in t:
        n2 = du[t[11]]
        name = du[t[11]+1:t[11]+1+n2].decode('latin1')
    if not all(k in t for k in range(14, 20)): continue
    st = [du[t[k]] for k in range(14, 20)]      # ATK DEF DMG HP Move RES
    lvl = du[t[20]] if 20 in t else 1
    unit_stats[cid] = dict(name=name, level=lvl, hp=st[3], move=st[4])
RACE_BASE = {0: 0, 1: 18, 3: 36, 2: 54, 4: 72, 5: 90, 6: 108, 7: 126,
             8: 144, 9: 162, 10: 180, 11: 198}
PARTY_SLOTS = [0, 1, 2, 3]                     # archer, priest, cavalry, infantry
for sl in PARTY_SLOTS:
    missing = [r for r, b_ in RACE_BASE.items() if b_ + sl not in unit_stats]
    assert not missing, (sl, missing)
print('unit_stats: %d entries; party slots %s ok for all 12 races'
      % (len(unit_stats), PARTY_SLOTS))

kit = dict(f21_prefix=prefix.hex(), f2_val=f2_val, players=players,
           heroes=heroes, party_units=party_units, leader_ref=leader_ref,
           city_tag_order=city_tag_order,
           unit_stats=unit_stats, race_base=RACE_BASE, party_slots=PARTY_SLOTS)
out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'player_kit.pkl'))
pickle.dump(kit, open(out, 'wb'))
print('wrote', out)
