# -*- coding: utf-8 -*-
"""
AoWx Manual regenerator — builds X/Documentation/AoWx Manual.html straight from the GAME FILES.

Data sources:
  * Release/Unitres.pfs  — unit stats, level, cost, ability tiers (+levels), descriptions (AUTHORITATIVE)
  * abil_names.json      — ability id -> name map (122 ids; derived + verified 2026-07-27)
  * X/Documentation/AoWx Readme.docx — supplements only: alignment, upkeep, portraits, Overview/General text
  * template.html        — page template (hash-routed manual: Home/Overview/General/Races/Spells)

Run from the game root:   py "patch scripts/manual_build/build_manual_from_game.py"
Re-run any time after editing units in the editor — the manual updates to match the game.

PFS/HSS format (cracked 2026-07-27, see memory pfs-unitres-format):
  file = magic 0x2144DF1C, 01 00 00, property table; field 1 = children table (id,offset pairs).
  Property table: [ctrl b; nd=dword if b&0x80; nb=b&0x7F][nb x (tag:byte,off:byte)][nd x (tag:dword,off:dword)],
  offsets relative to table end. Unit record = [classid][table][data]:
  tag 0xA=race str (or name if no 0xB), 0xB=name, 0xE-0x13=ATK/DEF/DMG/HP/Move/RES (255=none),
  0x14=level, 0x1A=description [len32][chars], 0x1B=cost u32,
  0x19/0x1E/0x1F=base/Silver/Gold ability owners (inner tag 2=count word, 3=bitfield; bit i = ability id i;
  leveled entries match regex 02 00 02 0a 00 0b 01 <lvl> <id> 00).
"""
import os, sys
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
HERE=os.path.dirname(os.path.abspath(__file__))

import struct, re, json, zipfile, base64, collections
from xml.etree import ElementTree as ET
d=open('Release/Unitres.pfs','rb').read()
def u32(p): return struct.unpack_from('<I',d,p)[0]
def u16(p): return struct.unpack_from('<H',d,p)[0]
def parse_table(p):
    b=d[p]; p+=1
    nb=b&0x7F; nd=0
    if b&0x80: nd=u32(p); p+=4
    pairs=[]
    for _ in range(nb): pairs.append((d[p],d[p+1])); p+=2
    for _ in range(nd): pairs.append((u32(p),u32(p+4))); p+=8
    return {t:p+o for t,o in pairs}, p, pairs
def sstr(p):
    n=d[p]; return d[p+1:p+1+n].decode('latin1')
def astr(p):
    n=u32(p)
    if not(0<n<3000): return ''
    return d[p+4:p+4+n].decode('latin1','replace')
root,_,_=parse_table(7)
kids,kbase,kp=parse_table(root[1])
LVL_RE=re.compile(rb'\x02\x00\x02\x0a\x00\x0b\x01(.)(.)\x00',re.S)
# Dispel Magic and Healing store their level in ABILITY-SPECIFIC data classes
# whose records carry no explicit id byte (tag 0x0B offset 0 instead of 1), so
# the generic LVL_RE never matches them and the manual showed the bare name.
# Correlation over all of Unitres.pfs (2026-09-01): classid 0x2CD <-> Dispel
# Magic 0x3C (61 records, levels 1-5), classid 0x2AE <-> Healing 0x2F
# (26 records, levels 2-3). Record shape: [classid u32][02][0a 00][0b 00][lvl].
SPEC_LVL={0x2CD:0x3C,0x2AE:0x2F}
SPEC_RE=re.compile(rb'(\xcd\x02|\xae\x02)\x02\x00\x02\x0a\x00\x0b\x00(.)',re.S)
def owner(t,tag,end):
    if tag not in t: return None
    ot,ob,op=parse_table(t[tag])
    out={'ids':[],'lvl':{}}
    if 2 in ot and 3 in ot:
        cnt=u16(ot[2]); nb=(cnt+7)>>3
        bf=d[ot[3]:ot[3]+nb]
        out['ids']=[i for i in range(cnt) if bf[i>>3]>>(i&7)&1]
    for m in LVL_RE.finditer(d[t[tag]:end]):
        lvl,aid=m.group(1)[0],m.group(2)[0]
        if aid in out['ids'] and 1<=lvl<=5: out['lvl'][str(aid)]=lvl
    for m in SPEC_RE.finditer(d[t[tag]:end]):
        aid=SPEC_LVL[struct.unpack('<H',m.group(1))[0]]
        lvl=m.group(2)[0]
        if aid in out['ids'] and 1<=lvl<=5: out['lvl'][str(aid)]=lvl
    return out
game=[]
for cid,rel in kp:
    off=kbase+rel
    t,tb,pp=parse_table(off+4)
    if 10 not in t: continue
    if 11 in t: race=sstr(t[10]); name=sstr(t[11])
    else: race=''; name=sstr(t[10])
    nxt=[r for _,r in kp if r>rel]
    end=kbase+(min(nxt) if nxt else len(d)-kbase)
    offs=sorted(v for v in t.values())
    def oend(tag):
        later=[v for v in offs if v>t[tag]]
        return later[0] if later else end
    stats=[d[t[k]] for k in range(14,20)] if all(k in t for k in range(14,20)) else None
    game.append(dict(id=cid,race=race,name=name,stats=stats,
        gfx=(struct.unpack_from('<I',d,t[8])[0] if 8 in t else cid),
        level=d[t[20]] if 20 in t else None,
        cost=u32(t[27]) if 27 in t else None,
        desc=astr(t[26]) if 26 in t else '',
        base=owner(t,25,oend(25)) if 25 in t else None,
        silver=owner(t,30,oend(30)) if 30 in t else None,
        gold=owner(t,31,oend(31)) if 31 in t else None,
        legend=owner(t,32,oend(32)) if 32 in t else None))   # 1.37.432: Legendary medal owner (tag 0x20)
print('extracted %d units from Unitres.pfs'%len(game))
STAT = ['ATK', 'DEF', 'DMG', 'RES', 'HP', 'Move']   # display order
STAT_IDX = [0, 1, 2, 5, 3, 4]                       # from internal ATK/DEF/DMG/HP/Move/RES
ROMAN = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V'}
DOC = "X/Documentation/AoWx Readme.docx"
OUT = ".AoWx Manual.html"   # game root, dot-prefixed so it sorts to the top of the file list
ANAME = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'abil_names.json'), encoding='utf-8')).items()}
def aname(i, lvl=0):
    n = ANAME.get(i, 'Unknown (0x%02X)' % i)
    return n + (' ' + ROMAN[lvl] if lvl in ROMAN and lvl > 0 else '')

ORDER_RACES = {'Human','Azrac','Lizardman','Frostling','Elf','Halfling','Dwarf','Highmen',
               'Dark Elf','Orc','Goblin','Undead'}
RACE_GROUP = {'Human':'Human','Azrac':'Azrac','Lizardman':'Lizardman','Frostling':'Frostling',
              'Elf':'Elf','Halfling':'Halfling','Dwarf':'Dwarf','Highman':'Highmen',
              'Dark Elf':'Dark Elf','Orc':'Orc','Goblin':'Goblin','Undead':'Undead'}

# ---- doc supplements: alignment/upkeep/portrait by normalized name ----
z = zipfile.ZipFile(DOC)
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
relmap = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="(media/[^"]+)"',
                         z.read('word/_rels/document.xml.rels').decode('utf-8', 'replace')))
sizes = {n: z.getinfo(n).file_size for n in z.namelist() if n.startswith('word/media/')}
root = ET.fromstring(z.read('word/document.xml')); body = root.find(W + 'body')
def txt(e): return ''.join(t.text or '' for t in e.iter(W + 't'))
def rows(t): return t.findall(W + 'tr')
def cells(tr): return tr.findall(W + 'tc')
def normn(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
docsup = {}
for ut in root.iter(W + 'tbl'):
    r = rows(ut)
    if not (r and len(cells(r[0])) == 5 and 'Alignment:' in txt(cells(r[0])[0])): continue
    head = txt(cells(r[0])[0])
    dn = re.split(r'\xa0|Alignment', head)[0].strip()
    def g(pat):
        m = re.search(pat + r':\s*([^\xa0]+)', head)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    best = None; bs = -1
    for b in r[0].findall(W + 'tc')[4].iter(A + 'blip'):
        tg = relmap.get(b.get(R + 'embed'), '')
        if tg.endswith('.png') and sizes.get('word/' + tg, 0) > bs:
            bs = sizes['word/' + tg]; best = tg
    img = ''
    if best and bs > 3000:
        try: img = 'data:image/png;base64,' + base64.b64encode(z.read('word/' + best)).decode()
        except: pass
    lu = g('Level / Upkeep')
    docsup[normn(dn)] = dict(align=g('Alignment'), upkeep=(lu.split('/')[1].strip() if '/' in lu else ''),
                             img=img, stats=None, type=g('Type'))
    # doc No-Medal stats for diff report
    nums = [t.text.strip() for t in r[0].findall(W + 'tc')[1].iter(W + 't')
            if t.text and re.fullmatch(r'-?\d+', t.text.strip())]
    docsup[normn(dn)]['stats'] = nums

# ---- positional doc sections (the doc's own roster grouping is authoritative) ----
SECTION_CANON = {'humans':'Human','azracs':'Azrac','lizardmen':'Lizardman','frostlings':'Frostling',
    'elves':'Elf','halflings':'Halfling','dwarves':'Dwarf','high men':'Highmen','highmen':'Highmen',
    'dark elves':'Dark Elf','orcs':'Orc','goblins':'Goblin','the undead':'Undead',
    'other neutral units':'Other Neutral Units','other good units':'Other Good Units',
    'other evil units':'Other Evil Units','builder’s guild':"Builder's Guild",
    "builder's guild":"Builder's Guild",'shipyard':'Shipyard','other machines':'Other Machines'}
def is_unit_tbl(t):
    r = rows(t)
    return len(r) >= 1 and len(cells(r[0])) == 5 and 'Alignment:' in txt(cells(r[0])[0])
docsec = {}          # normname -> ordered unique section list
_seen_ids = set(); _cur = ''
for k in list(body):
    if k.tag != W + 'tbl': continue
    for tr in rows(k):
        uts = [x for x in tr.iter(W + 'tbl') if is_unit_tbl(x)]
        if uts:
            for ut in uts:
                if id(ut) in _seen_ids: continue
                _seen_ids.add(id(ut))
                dn = re.split(r'\xa0|Alignment', txt(cells(rows(ut)[0])[0]))[0].strip()
                if _cur:
                    docsec.setdefault(normn(dn), [])
                    if _cur not in docsec[normn(dn)]: docsec[normn(dn)].append(_cur)
            continue
        rt = re.sub(r'\s+', ' ', txt(tr)).strip().lower().replace('’', "'")
        if rt in SECTION_CANON or rt.replace("'", '’') in SECTION_CANON:
            _cur = SECTION_CANON.get(rt) or SECTION_CANON.get(rt.replace("'", '’'))

PREFIXES = {'human':'Human','azrac':'Azrac','lizardman':'Lizardman','lizard':'Lizardman',
    'frostling':'Frostling','elf':'Elf','elven':'Elf','halfling':'Halfling','dwarf':'Dwarf',
    'dwarven':'Dwarf','highman':'Highmen','darkelf':'Dark Elf','orc':'Orc','goblin':'Goblin',
    'undead':'Undead','guild':"Builder's Guild"}
def unit_groups(u, full):
    gn = normn(full); bn = normn(u['name'])
    if gn in FORCE_GROUP: return FORCE_GROUP[gn]
    s = docsec.get(gn) or docsec.get(bn)
    if not s:  # doc name = race-prefix + game name  (e.g. 'Undead Bone Ram' vs game 'Bone Ram')
        for p in PREFIXES:
            if (p + gn) in docsec: s = docsec[p + gn]; break
    if not s:  # game name = race-prefix + doc name  (e.g. game 'Guild Drill' vs doc 'Drill')
        for p, grp in PREFIXES.items():
            if gn.startswith(p) and gn[len(p):] in docsec:
                s = docsec[gn[len(p):]]
                if grp in s: s = [grp]     # prefer the prefix's own roster
                break
    if s:
        # unit's own race string picks its roster when the name is shared (e.g. Guild Drill)
        pref = PREFIXES.get(normn(u['race'])) if u['race'] else None
        if pref and pref in s and u['race'] not in RACE_GROUP: return [pref]
        return s
    if u['race'] in RACE_GROUP: return [RACE_GROUP[u['race']]]
    for p, grp in PREFIXES.items():        # raceless but race-prefixed name -> that roster
        if gn.startswith(p): return [grp]
    return ['Other Neutral Units']

# ---- game portraits: unit -> gfx(tag8=face) -> FACERES(child: tag5 path, tag6 idx) -> ILB ----
def _pfs_children(path):
    dd = open(path, 'rb').read()
    def _u32(pp2): return struct.unpack_from('<I', dd, pp2)[0]
    def _tbl(pp2):
        b2 = dd[pp2]; pp2 += 1
        nb2 = b2 & 0x7F; nd2 = 0
        if b2 & 0x80: nd2 = _u32(pp2); pp2 += 4
        prs = []
        for _ in range(nb2): prs.append((dd[pp2], dd[pp2+1])); pp2 += 2
        for _ in range(nd2): prs.append((_u32(pp2), _u32(pp2+4))); pp2 += 8
        return {t2: pp2+o2 for t2, o2 in prs}, pp2, prs
    st2 = 7 if _u32(0) == 0x2144DF1C else 3
    rt, _, _ = _tbl(st2)
    _, kb, kpp = _tbl(rt[1])
    out = []
    for cid2, rel2 in kpp:
        t2, tb2, _ = _tbl(kb + rel2 + 4)
        out.append((cid2, t2, dd))
    return out
GFX_FACE = {}      # gfx id -> (face ILB path [tag6], image index [tag8])
for _cid, _t, _dd in _pfs_children('Release/Unitgfx.pfs'):
    if 6 in _t and 8 in _t:
        _n = _dd[_t[6]]
        _pth = _dd[_t[6]+1:_t[6]+1+_n].decode('latin1')
        _ix = struct.unpack_from('<I', _dd, _t[8])[0]
        # custom x-packs (x2022-x2025) index 1-based vs record order; originals 0-based
        _fnu = _pth.upper().split(chr(92))[-1]
        if _fnu.startswith('X20') and not (_fnu == 'X2024.ILB' and _ix <= 4): _ix -= 1
        if _ix >= 0: GFX_FACE[_cid] = (_pth, _ix)
_ILB_CACHE = {}
def _ilb_images(path):
    if path in _ILB_CACHE: return _ILB_CACHE[path]
    fp = 'Images/' + path.replace('\\', '/')
    try: dd = open(fp, 'rb').read()
    except Exception: _ILB_CACHE[path] = None; return None
    bs = struct.unpack_from('<I', dd, 0x10)[0]
    recs = []
    for mm in re.finditer(struct.pack('<I', 0x56509310), dd):
        pp2 = mm.start()
        sz = struct.unpack_from('<I', dd, pp2-0x18)[0]; of = struct.unpack_from('<I', dd, pp2-0x14)[0]
        w2 = struct.unpack_from('<I', dd, pp2-0x10)[0]; h2 = struct.unpack_from('<I', dd, pp2-0xc)[0]
        sw = struct.unpack_from('<I', dd, pp2+4)[0]; sh = struct.unpack_from('<I', dd, pp2+8)[0]
        if 0 < w2 < 512 and 0 < h2 < 512 and sz == w2*h2*2:
            recs.append((w2, h2, bs+of, sz, dd))          # raw 16bpp
        elif 0 < sw < 512 and 0 < sh < 512:
            recs.append((sw, sh, bs+of, sz, dd))          # row-encoded
        else:
            recs.append((0, 0, bs+of, sz, dd))            # keep index alignment
    _ILB_CACHE[path] = recs
    return recs
def _dec_ilb(w2, h2, st2, sz2, dd):
    from PIL import Image as _I
    im2 = _I.new('RGBA', (w2, h2)); px2 = im2.load()
    def _pix(v2): return ((v2 >> 11)*255//31, ((v2 >> 5) & 63)*255//63, (v2 & 31)*255//31, 255)
    if sz2 == w2*h2*2:
        for k2 in range(w2*h2):
            v2 = struct.unpack_from('<H', dd, st2+k2*2)[0]
            if v2 != 0x4D2B: px2[k2 % w2, k2//w2] = _pix(v2)
        return im2
    q2 = st2; e2 = st2+sz2
    for y2 in range(h2):
        if q2+4 > e2: break
        L2 = struct.unpack_from('<H', dd, q2)[0]; S2 = struct.unpack_from('<H', dd, q2+2)[0]
        if L2 < 4: break
        for i2 in range((L2-4)//2):
            x2 = S2+i2
            if x2 >= w2: break
            v2 = struct.unpack_from('<H', dd, q2+4+i2*2)[0]
            if v2 != 0x4D2B: px2[x2, y2] = _pix(v2)
        q2 += (L2+3) & ~3
    return im2
# hand-verified fixes (record names in the packs) for refs scrambled by later file edits
X22 = 'FACES' + chr(92) + 'X2022.ILB'; X24 = 'FACES' + chr(92) + 'X2024.ILB'
FACE_OVERRIDE = {
    'doombat': ('FACES' + chr(92) + 'UNITS.ILB', 0),        # U_Bat.BMP
    'goblinbigbeetle': (X22, 101), 'goblinbutcher': (X22, 110), 'undeadarcher': (X22, 103),
    'direwolf': (X22, 111), 'forestdragon': (X22, 113), 'frostdragon': (X22, 114),
    'shadowdragon': (X22, 115), 'ancientferaldragon': (X22, 116), 'elderdragon': (X22, 117),
    'dwarfminer': (X22, 118), 'hydra': (X22, 119), 'minotaur': (X22, 120),
    'resurrecteddragon': (X22, 121), 'succubus': (X22, 122), 'wildmammoth': (X22, 123),
    'crocodile': (X24, 1), 'elfdruidess': (X24, 2), 'ent': (X24, 3), 'frostblowerram': (X24, 4),
    # 1.37.420 (user): Mammoth Rider showed the Wild Boar - its X2022 ref (7) is the 0-based record index,
    # not the 1-based x-pack convention the generic -1 shift assumes (record 6 = boar, 7 = mammoth rider)
    'frostlingmammothrider': (X22, 7),
}
_PORTRAIT_CACHE = {}
def game_portrait(gfxid, uname=''):
    key = FACE_OVERRIDE.get(uname) or GFX_FACE.get(gfxid)
    if key is None: return ''
    if key in _PORTRAIT_CACHE: return _PORTRAIT_CACHE[key]
    uri = ''
    try:
        recs = _ilb_images(key[0])
        if recs and key[1] < len(recs) and recs[key[1]][0] > 0:
            import io as _io3
            im2 = _dec_ilb(*recs[key[1]])
            im2.thumbnail((128, 152))
            bf = _io3.BytesIO(); im2.save(bf, 'PNG')
            uri = 'data:image/png;base64,' + base64.b64encode(bf.getvalue()).decode()
    except Exception: pass
    _PORTRAIT_CACHE[key] = uri
    return uri
print('gfx-face entries: %d' % len(GFX_FACE))

# ---- merge ----
units = []; ndiff = 0; diffs = []; nogroup = []
ALIAS = {'humanswordsman': 'humaninfantry', 'boneram': 'undeadboneram'}   # game name -> doc name
# map-special duplicates the manual should not show (user 2026-07-27)
EXCLUDE_NAMES = {'humanengineers', 'azracjavelineer', 'azracchariot',
                 'lizardmanspearthrower', 'frostlingspearthrower', 'orcjavelineer',
                 'siegeelephant', 'amc', 'guilddrill'}
FORCE_GROUP = {'catapult': ['Other Machines'], 'ent': ['Other Good Units']}
FORCE_ALIGN = {'ent': 'Good'}
DEDUPE = {'druid', 'demon'}   # 1.37.420: 'Demon' = Unitres ids 205 + 285 (identical clone kept for the editor) - list the first (205) once
GROUP_ORDER = {
  'Other Neutral Units': ['mysteriousfrog', 'mermaid', 'wildboar', 'wolf', 'direwolf', 'wildmammoth',
             'humangreatsword', 'druid', 'firesprite', 'greateagle', 'crocodile', 'seaserpent',
             'minotaur', 'airelemental', 'earthelemental', 'fireelemental', 'waterelemental',
             'hydra', 'elderdragon', 'frostdragon', 'silverdragon', 'syron'],
  "Builder's Guild": ['drill', 'engineers', 'flamethrowerram', 'guildballoon'],
}
WEAK_IDS = set(range(0x51, 0x56)) | set(range(0x85, 0x8A))
def excluded(u, full):
    n = normn(full)
    if n in EXCLUDE_NAMES: return True
    if n == 'stormlord' and u['level'] == 3: return True          # keep only the L4 (transforms to Incarnate)
    if n == 'demon' and not (set(u['base']['ids'] if u['base'] else []) & WEAK_IDS): return True
    return False
LINKED = {'stormlord', 'incarnate'}    # L4 Stormlord transforms into L4 Incarnate
_dedupe_seen = set()
for u in game:
    full = (u['race'] + ' ' + u['name']).strip()
    if excluded(u, full): continue
    if normn(full) in DEDUPE:
        if normn(full) in _dedupe_seen: continue
        _dedupe_seen.add(normn(full))
    sup = (docsup.get(normn(full)) or docsup.get(ALIAS.get(normn(full), ''))
           or docsup.get(normn(u['name'])) or {})
    def tier(o, exclude=None):
        if not o: return []
        out = []
        for i in sorted(o['ids'], key=lambda x: aname(x)):
            lvl = o['lvl'].get(str(i), 0)
            if exclude and i in exclude and exclude[i] >= lvl: continue   # already granted by a lower tier
            out.append(aname(i, lvl))
        return out
    def medal_ab(u):
        # 2026-09-21 (user): a medal tier must not list an ability the unit already has as a base ability
        # (Swordsmen: Strike is base, so it is not a medal upgrade; Archers gain Strike at a medal, so it stays).
        # Leveled upgrades (base Strike I -> medal Strike II) are kept.
        base = u['base'] or {'ids': [], 'lvl': {}}
        had = {i: base['lvl'].get(str(i), 0) for i in base['ids']}
        silver = tier(u['silver'], had)
        if u['silver']:
            for i in u['silver']['ids']:
                had[i] = max(had.get(i, -1), u['silver']['lvl'].get(str(i), 0))
        gold = tier(u['gold'], had)
        if u['gold']:
            for i in u['gold']['ids']:
                had[i] = max(had.get(i, -1), u['gold']['lvl'].get(str(i), 0))
        legend = tier(u.get('legend'), had)      # user 11/07: show Legendary medal abilities too (often none)
        return {'base': tier(u['base']), 'Silver': silver, 'Gold': gold, 'Legendary': legend}
    gimg = game_portrait(u.get('gfx', u['id']), normn(full))
    if gimg: sup = dict(sup, img=gimg)
    st = ['-' if x == 255 else x for x in u['stats']]
    # --- role rank: melee(0) < projectile(1) < ram(2) < specialty(3) ---
    RANGED_IDS = {0x16,0x39,0x3D,0x78,0x79,0x7A,0x7B,0x7C,0x18,0x19,0x2C,0x2D}
    MELEE_KW = ('swordsman','infantry','warrior','axeman','legionary','recruit','spearman',
                'grunt','draugr','longswordsman','cavalry','cavalier','knight','paladin')
    RAM_KW = ('ram','drill','elephant')
    nl = full.lower(); bids = set(u['base']['ids']) if u['base'] else set()
    if any(k in nl for k in RAM_KW) or 0x75 in bids: rank = 2
    elif bids & RANGED_IDS or any(k in nl for k in ('archer','slinger','darter','arbalist','longbowman','necromancer','javelineer','thrower','musketeer','crossbow')): rank = 1
    elif any(k in nl for k in MELEE_KW): rank = 0
    else: rank = 3
    # --- medal stat rows (rank tables @0x558E83C4.. + HP-cap cave formula) ---
    def addv(i, dx):
        v = u['stats'][i]; return '-' if v == 255 else v + dx
    hp = u['stats'][3]
    cap = '-' if hp == 255 else max((hp * (7 - (u['level'] or 1))) >> 1, hp + 6)
    # rank tables: Silver +1 ATK/DEF/RES; Gold +2 ATK/+1 DEF/+1 DMG/+2 RES; HP cave +2/medal.
    # Legendary (capped medal): gold bonuses +1 ATK/+2 RES extra, HP = the unit's cap.
    med = {'No': st,
           'Silver':    [addv(0,1), addv(1,1), addv(2,0), addv(3,2), addv(4,0), addv(5,1)],
           'Gold':      [addv(0,2), addv(1,1), addv(2,1), addv(3,4), addv(4,0), addv(5,2)],
           'Legendary': [addv(0,3), addv(1,1), addv(2,1), ('-' if cap == '-' else str(cap) + '*'), addv(4,0), addv(5,4)]}
    st = [st[i] for i in STAT_IDX]
    med = {k: [v[i] for i in STAT_IDX] for k, v in med.items()}
    typ = sup.get('type', '') if sup else ''
    if not typ and u['race'] in RACE_GROUP: typ = u['race'] + ' Unit'
    groups = unit_groups(u, full)
    if not (docsec.get(normn(full)) or docsec.get(normn(u['name']))): nogroup.append(full)
    for grp in groups:
        _go = GROUP_ORDER.get(grp)
        _ord = _go.index(normn(full)) if _go and normn(full) in _go else 9999
        units.append(dict(name=full, race=grp, level=u['level'], stats=st, med=med, rank=rank, type=typ,
                          ord=_ord, align_ovr=FORCE_ALIGN.get(normn(full), ''),
                          link=1 if normn(full) in LINKED else 0,
                          cost=('- (Spawns from Stormlord)' if normn(full) == 'incarnate'
                                else (u['cost'] if u['cost'] is not None else '')),
                          upkeep=sup.get('upkeep', ''), align=sup.get('align', ''), img=sup.get('img', ''),
                          desc=(u['desc'] or '').strip(), uid=u['id'],
                          ab=medal_ab(u)))
    ds = sup.get('stats')
    if ds and len(ds) >= 6:
        gs = [str(x) for x in u['stats']]
        # doc grid order differs; compare as multiset to detect change
        if sorted(gs) != sorted(ds[:6]):
            ndiff += 1; diffs.append(full)

# 1.37.420: units missing from a GROUP_ORDER list (new units, e.g. Phoenix) used to sink to the end (ord 9999).
# Place each at its level-then-alphabetical spot among the group's listed units instead.
def _place_unordered():
    for grp in GROUP_ORDER:
        listed = sorted((u for u in units if u['race'] == grp and u['ord'] < 9999), key=lambda u: u['ord'])
        for u in [u for u in units if u['race'] == grp and u['ord'] >= 9999]:
            key = (u['level'], u['name'].lower())
            nxt = next((v for v in listed if (v['level'], v['name'].lower()) > key), None)
            if nxt is None:
                u['ord'] = (listed[-1]['ord'] + 0.5) if listed else 9999
            else:
                k = listed.index(nxt)
                u['ord'] = (listed[k - 1]['ord'] + nxt['ord']) / 2.0 if k else nxt['ord'] - 0.5
_place_unordered()

# ---- default Leaders & Heroes (Release/HERORES.PFS; cids 0-11 heroes, 36-47 leaders) ----
HERO_IMG = ''
try:
    import io as _io2
    from PIL import Image as _PImg
    _im = _PImg.open('X/Documentation/portraits/75869780.bmp').convert('RGBA')
    _im.thumbnail((128, 152))
    _buf = _io2.BytesIO(); _im.save(_buf, 'PNG')
    HERO_IMG = 'data:image/png;base64,' + base64.b64encode(_buf.getvalue()).decode()
except Exception as _e:
    print('hero portrait load failed:', _e)
try:
    hd = open('Release/HERORES.PFS', 'rb').read()
    def h_u32(p): return struct.unpack_from('<I', hd, p)[0]
    def h_u16(p): return struct.unpack_from('<H', hd, p)[0]
    def h_table(p):
        b = hd[p]; p += 1
        nb = b & 0x7F; nd = 0
        if b & 0x80: nd = h_u32(p); p += 4
        pairs = []
        for _ in range(nb): pairs.append((hd[p], hd[p+1])); p += 2
        for _ in range(nd): pairs.append((h_u32(p), h_u32(p+4))); p += 8
        return {t: p+o for t, o in pairs}, p
    def h_sstr(p):
        n = hd[p]; return hd[p+1:p+1+n].decode('latin1', 'replace')
    hroot, _ = h_table(7)
    hkids, hkbase = h_table(hroot[1])
    _, _, hkp = (lambda p: (None, None, []))(0)
    # re-parse children pairs
    b = hd[hroot[1]]; q = hroot[1] + 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = h_u32(q); q += 4
    hpairs = []
    for _ in range(nb): hpairs.append((hd[q], hd[q+1])); q += 2
    for _ in range(nd): hpairs.append((h_u32(q), h_u32(q+4))); q += 8
    hbase = q
    HR_RACE = {'lizard': 'Lizardman', 'high men': 'Highmen', 'highman': 'Highmen'}
    hero_cards = []
    for cid, rel in hpairs:
        if not (0 <= cid <= 11 or 36 <= cid <= 47): continue
        off = hbase + rel
        t, tb = h_table(off + 4)
        if 10 not in t or not all(k in t for k in range(15, 21)): continue
        rname = h_sstr(t[10])
        grp = HR_RACE.get(rname.lower(), rname)
        if grp not in ORDER_RACES: continue
        kind = 'Leader' if 36 <= cid <= 47 else 'Hero'
        hst = [hd[t[k]] for k in range(15, 21)]      # ATK DEF DMG HP Move RES
        ab = []
        if 29 in t:
            ot, _ = h_table(t[29])
            if 2 in ot and 3 in ot:
                cnt = h_u16(ot[2]); nby = (cnt+7) >> 3
                bf = hd[ot[3]:ot[3]+nby]
                ab = [i for i in range(cnt) if bf[i >> 3] >> (i & 7) & 1]
        abn = sorted(aname(i) for i in ab)
        dst = ['-' if x == 255 else x for x in hst]
        dst = [dst[i] for i in STAT_IDX]
        hero_cards.append(dict(name='%s %s' % (grp if grp != 'Highmen' else 'Highman', kind),
            race=grp, level=99, stats=dst, med=None, rank=(-2 if kind == 'Leader' else -1),
            type=kind, hero=1, link=0, cost='', upkeep='', align='', img=HERO_IMG, desc='', uid=-cid,
            ab={'base': abn, 'Silver': [], 'Gold': []}))
    units.extend(hero_cards)
    print('added %d default leader/hero cards' % len(hero_cards))
except Exception as e:
    print('HERORES parse failed:', e)

# fill blank alignments with each group's majority (doc-sourced)
_av = {}
for _u in units:
    if _u['align']: _av.setdefault(_u['race'], collections.Counter())[_u['align']] += 1
for _u in units:
    if _u.get('align_ovr'): _u['align'] = _u['align_ovr']
    elif not _u['align'] and _u['race'] in _av:
        _u['align'] = _av[_u['race']].most_common(1)[0][0]

ORDER = ['Human', 'Azrac', 'Lizardman', 'Frostling', 'Elf', 'Halfling', 'Dwarf', 'Highmen',
         'Dark Elf', 'Orc', 'Goblin', 'Undead', 'Other Neutral Units', 'Other Good Units',
         'Other Evil Units', "Builder's Guild", 'Shipyard', 'Other Machines']
present = [r for r in ORDER if any(u['race'] == r for u in units)]
for u in units:
    if u['race'] not in present: present.append(u['race'])

# ---- section text (same as before) ----
_pnodes = [k for k in list(body) if k.tag == W + 'p']
paras = [re.sub(r'\s+', ' ', txt(k)).strip() for k in _pnodes]
def txtbr(k):
    out = []
    for e in k.iter():
        if e.tag == W + 't' and e.text: out.append(e.text)
        elif e.tag == W + 'br': out.append(chr(10))
    s = ''.join(out)
    s = re.sub(r'[ 	]+', ' ', s)
    return chr(10).join(x.strip() for x in s.split(chr(10))).strip()
def _plvl(k):
    _ind = k.find(W + 'pPr/' + W + 'ind')
    if _ind is None: return 0
    def _g(a):
        try: return int(_ind.get(W + a) or 0)
        except ValueError: return 0
    _eff = _g('left') + _g('firstLine') - _g('hanging')   # visual first-line indent
    return max(0, min(3, _eff // 720))
paras_lvl = [_plvl(k) for k in _pnodes]
def find(pred, start=0):
    for i in range(start, len(paras)):
        if pred(paras[i]): return i
    return -1
i_ov = find(lambda t: bool(re.match(r'^I\s*[-–—]\s*Overview\s*:', t)))
i_gc = find(lambda t: 'General Changes' in t, i_ov + 1) if i_ov >= 0 else -1
i_iii = find(lambda t: 'Detailed Unit Tables' in t or bool(re.match(r'^III\b', t)), (i_gc + 1) if i_gc >= 0 else 0)
overview = [t for t in paras[i_ov + 1:i_gc] if t] if 0 <= i_ov < i_gc else []
general = [t for t in paras[i_gc + 1:i_iii] if t] if 0 <= i_gc < i_iii else []
titlep = [re.sub(r'\s+', ' ', txt(k)).strip() for k in list(body)[:4] if k.tag == W + 'p']

# ---- icons from the doc media (stat glyphs, medals, gold) + tinted Legendary medal ----
icons = {}
try:
    import io as _io
    from PIL import Image as PILImage
    def _uri(im):
        buf = _io.BytesIO(); im.save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    def _gif(name):
        return PILImage.open(_io.BytesIO(z.read('word/media/' + name))).convert('RGBA')
    # display order ATK DEF DMG RES Move HP -> sword, shield, star, ankh, boot, heart
    icons['stat'] = [_uri(_gif(n)) for n in
                     ('image8.gif', 'image10.gif', 'image9.gif', 'image11.gif', 'image13.gif', 'image12.gif')]
    icons['silver'] = _uri(_gif('image14.gif'))
    icons['gold'] = _uri(_gif('image15.gif'))
    leg = _gif('image15.gif'); px = leg.load()
    for yy in range(leg.height):
        for xx in range(leg.width):
            r, g, b, a = px[xx, yy]
            if a > 0 and r > 120 and g > 90 and b < 160:   # gold tones -> bronze red
                px[xx, yy] = (min(255, int(r * 1.05)), int(g * 0.5), int(b * 0.35), a)
    icons['leg'] = _uri(leg)
except Exception as e:
    print('icon extraction failed (%s) - falling back to text' % e)


# ================= SPELLS =================
SPHERES = ['Air Magic', 'Earth Magic', 'Water Magic', 'Fire Magic', 'Life Magic', 'Death Magic', 'Cosmos Magic']
def _clean(s): return re.sub(r'\s+', ' ', (s or '').replace('’', "'").replace('�', "'")).strip()
def _dnorm(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())[:48]
# ---- game spell records (Release/Spells.pfs): tag 0xa desc, 0xd cast, 0xf research ----
sp_d = open('Release/Spells.pfs', 'rb').read()
def s_u32(pp2): return struct.unpack_from('<I', sp_d, pp2)[0]
def s_table(pp2):
    b = sp_d[pp2]; pp2 += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = s_u32(pp2); pp2 += 4
    pairs = []
    for _ in range(nb): pairs.append((sp_d[pp2], sp_d[pp2+1])); pp2 += 2
    for _ in range(nd): pairs.append((s_u32(pp2), s_u32(pp2+4))); pp2 += 8
    return {t2: pp2+o2 for t2, o2 in pairs}, pp2
s_root, s_base = s_table(7)
b0 = sp_d[7]; q0 = 8
nb0 = b0 & 0x7F; nd0 = 0
if b0 & 0x80: nd0 = s_u32(q0); q0 += 4
s_pairs = []
for _ in range(nb0): s_pairs.append((sp_d[q0], sp_d[q0+1])); q0 += 2
for _ in range(nd0): s_pairs.append((s_u32(q0), s_u32(q0+4))); q0 += 8
s_kbase = q0
sys.path.insert(0, os.path.dirname(HERE)); import imgseq as _IS
gspells = []
for scid, srel in s_pairs:
    soff = s_kbase + srel
    st2, _ = s_table(soff)
    sdesc = ''
    if 0xa in st2:
        n2 = s_u32(st2[0xa])
        if 0 < n2 < 2000: sdesc = sp_d[st2[0xa]+4:st2[0xa]+4+n2].decode('latin1', 'replace')
    # 2026-10-31 (user: doc icons look janky / mixed glows): spellbook icon = SPELLICN.ILB image id stored in the
    # tag 0x0C image list, u32 3 bytes after the 'SPELLICN.ILB' path (BXL build_ziggurat_manual) - NOT the spell id
    sicon = None
    if 0xc in st2:
        try:
            _ch = [x for x in _IS.parse_list(sp_d, st2[0xc])[0] if x]
            while _ch:
                _x = _ch.pop()
                if _x['name'].upper() == 'SPELLICN.ILB': sicon = _x['frame']; break
                if _x.get('sub'): _ch.append(_x['sub'])
        except Exception: pass
    gspells.append(dict(id=scid, desc=_clean(sdesc), icon=sicon,
                        cast=(s_u32(st2[0xd]) if 0xd in st2 else None),
                        research=(s_u32(st2[0xf]) if 0xf in st2 else None),
                        upkeep=(s_u32(st2[0xe]) if 0xe in st2 else None),
                        slevel=(sp_d[st2[0x11]] if 0x11 in st2 else 0)))
# ---- doc spell tables ----
docspells = []
for k2 in list(body):
    if k2.tag != W + 'tbl': continue
    r2 = rows(k2)
    if not r2: continue
    head0 = txt(cells(r2[0])[0]).strip() if cells(r2[0]) else ''
    if head0 not in SPHERES: continue
    lvl2 = 0
    for tr2 in r2:
        cs2 = cells(tr2)
        rowtxt = _clean(txt(tr2))
        m2 = re.fullmatch(r'Level\s*(\d+)', rowtxt)
        if m2: lvl2 = int(m2.group(1)); continue
        if len(cs2) >= 6 and _clean(txt(cs2[1])) and _clean(txt(cs2[1])) != 'Spell':
            ic2 = ''
            for b2 in tr2.iter(A + 'blip'):
                tg2 = relmap.get(b2.get(R + 'embed'), '')
                if tg2:
                    try:
                        ic2 = 'data:image/png;base64,' + base64.b64encode(z.read('word/' + tg2)).decode()
                    except Exception: pass
                    break
            docspells.append(dict(sphere=head0, level=lvl2, name=_clean(txt(cs2[1])),
                                  cost=_clean(txt(cs2[2])), research=_clean(txt(cs2[3])),
                                  type=_clean(txt(cs2[4])), desc=_clean(txt(cs2[5])), icon=ic2))
# ---- match doc -> game by description ----
SPELL_RENAME = {'Freeze Water': 'Freeze Terrain'}      # in-game renames since the doc (patch_frost_terrain_v1)
import difflib
gd = {_dnorm(g['desc']): g for g in gspells if g['desc']}
gkeys = list(gd)
used_g = set(); spells_out = []
for ds in docspells:
    key = _dnorm(ds['desc']); g = gd.get(key)
    if g is None and key:
        close = difflib.get_close_matches(key, gkeys, n=1, cutoff=0.62)
        if close: g = gd[close[0]]
    if g is not None: used_g.add(g['id'])
    upk = ds['cost'].split('/')[1].strip() if '/' in ds['cost'] else ''
    cast = (str(g['cast']) if g and g['cast'] is not None else ds['cost'].split('/')[0].strip())
    res = (str(g['research']) if g and g['research'] is not None else ds['research'])
    # 2026-11-15 (user: Scorch Terrain shown as L2, is L1 since 1.37.420): the live Spells.pfs level wins over
    # the doc table's "Level N" row, same rule as the dual-sphere spells below
    _lv = g['slevel'] if g and 1 <= (g.get('slevel') or 0) <= 4 else ds['level']
    if _lv != ds['level']: print('spell level: %s doc L%s -> game L%s' % (ds['name'], ds['level'], _lv))
    spells_out.append(dict(sphere=ds['sphere'], level=_lv, name=SPELL_RENAME.get(ds['name'], ds['name']),
                           cast=cast + (' / ' + upk if upk else ''), research=res,
                           type=ds['type'], icon=ds['icon'], gicon=(g['icon'] if g else None),
                           desc=(g['desc'] if g else ds['desc']), matched=bool(g)))
# ---- Secret Magic: AoWx custom spells (pfs records + SPELLICN.ILB icons) ----
SECRET = 'Secret Magic'
SECRET_SPELLS = {          # pfs record key -> (name, SPELLICN image id, type)
    210: ('Magic Sight', 151, 'Enchantment'),
    211: ('Summon Mermaid', 88, 'Summon'),
    212: ('Void Step', 52, 'Combat Range 8'),
    213: ('Summon Silver Dragon', 200, 'Summon'),
}
def _spellicn_icons(wanted, gain=1.0):
    """Composite SPELLICN.ILB icon pairs (RGB565 cloud + colorkeyed glyph)
    into 3x PNG data URIs. Pair = cloud rec (carries the image id in its
    wrapper) + the following glyph rec, MULTIPLY-blended at its sub-offset
    (ink-on-white art: white->transparent, ink->dark, AA edges smooth);
    header-colorkey pixels skipped."""
    import io
    from PIL import Image
    ild = open('Images/SPELLICN.ILB', 'rb').read()
    ibase = struct.unpack_from('<I', ild, 0x10)[0]
    irecs = []; ii = 0
    while True:
        ij = ild.find(b'\x10\x93\x50\x56', ii)
        if ij < 0: break
        iw, ih, isx, isy, ikey = struct.unpack_from('<5I', ild, ij+4)
        isz = struct.unpack_from('<I', ild, ij-0x18)[0]
        idoff = struct.unpack_from('<I', ild, ij-0x14)[0]
        irecs.append((ij, iw, ih, isx, isy, ikey & 0xFFFF, isz, ibase + idoff))
        ii = ij + 4
    idmap = {}
    for ik, ir in enumerate(irecs):
        iwin = ild[max(0, ir[0]-0x80):ir[0]]
        iq = iwin.rfind(b'\xff\xff\xff\xff')
        if iq >= 0:
            iid = struct.unpack_from('<I', iwin, iq+4)[0]
            if iid != 0xFFFFFFFF: idmap[iid] = ik
        elif ik == 0: idmap[0] = 0                     # first record (id 0 = Haste) has no preceding terminator
    def px(v):  # RGB565
        return (((v >> 11) & 31)*255//31, ((v >> 5) & 63)*255//63, (v & 31)*255//31)
    out = {}
    for iid in wanted:
        if iid not in idmap: continue
        ik = idmap[iid]
        _, cw, ch, _, _, _, _, coff = irecs[ik]
        _, gw, gh, gx, gy, gkey, _, goff = irecs[ik+1]
        im = Image.new('RGB', (cw, ch))
        pp = im.load()
        for yy in range(ch):
            for xx in range(cw):
                _c = px(struct.unpack_from('<H', ild, coff + (yy*cw + xx)*2)[0])
                pp[xx, yy] = _c if gain == 1.0 else tuple(min(255, int(v * gain)) for v in _c)
        for yy in range(gh):
            for xx in range(gw):
                v = struct.unpack_from('<H', ild, goff + (yy*gw + xx)*2)[0]
                if v == gkey: continue
                r2, g2, b2 = px(v)
                if 0 <= xx+gx < cw and 0 <= yy+gy < ch:
                    cr, cg, cb = pp[xx+gx, yy+gy]
                    pp[xx+gx, yy+gy] = (cr*r2//255, cg*g2//255, cb*b2//255)
        buf = io.BytesIO()
        im.resize((cw*3, ch*3), Image.NEAREST).save(buf, 'PNG')
        out[iid] = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    return out
try:
    _sicons = _spellicn_icons([v[1] for v in SECRET_SPELLS.values()])
except Exception as _e:
    print('SPELLICN icon extraction failed:', _e); _sicons = {}
for _key, (_nm, _iid, _typ) in sorted(SECRET_SPELLS.items()):
    _g = next((x for x in gspells if x['id'] == _key), None)
    if _g is None:
        print('!! Secret spell record %d missing from Spells.pfs' % _key); continue
    used_g.add(_key)
    _cast = str(_g['cast'] if _g['cast'] is not None else '')
    if _g.get('upkeep'): _cast += ' / %d' % _g['upkeep']
    spells_out.append(dict(sphere=SECRET, level=_g.get('slevel') or 0, name=_nm,
                           cast=_cast, research=str(_g['research'] if _g['research'] is not None else ''),
                           type=_typ, icon=_sicons.get(_iid, ''),
                           desc=_g['desc'], matched=True))
print('secret spells: %d (icons: %d)' % (
    sum(1 for s in spells_out if s['sphere'] == SECRET), len(_sicons)))

# ---- AoWx 1.37.420: custom spells registered by the dual-sphere pipeline (single-sphere ids 204-235 + pair spells
# 300-406). Names/sphere/tier/icon come from patch scripts/patch_dual_sphere_spells_v1.py SPELLS (the engine names
# them from those literals - no mld rows); stats/desc from Spells.pfs (record key = spell id + 10). ----
SPH_ID = {0: 'Cosmos Magic', 1: 'Life Magic', 2: 'Death Magic', 3: 'Earth Magic', 4: 'Air Magic',
          5: 'Fire Magic', 6: 'Water Magic', 7: SECRET}
_SPN = {1: 'Life', 2: 'Death', 3: 'Earth', 4: 'Air', 5: 'Fire', 6: 'Water'}
PAIRS = {9: (1, 3), 10: (1, 4), 11: (1, 5), 12: (1, 6), 13: (2, 3), 14: (2, 4), 15: (2, 5), 16: (2, 6),
         17: (3, 4), 18: (3, 5), 19: (3, 6), 20: (4, 5), 21: (4, 6), 22: (5, 6)}   # patch_dual_sphere_plumbing_v1
for _pid, (_pa, _pb) in PAIRS.items():
    SPH_ID[_pid] = '%s/%s Magic' % (_SPN[_pa], _SPN[_pb])
PAIR_SPHERES = [SPH_ID[_p] for _p in sorted(PAIRS)]
# 1.37.420 (user): Spells-tab pair panes follow the changelog's pair order (Fire/Death, Fire/Life, ...)
try:
    import re as _re_po
    _po_txt = open('X/Documentation/changelogs.txt', 'rb').read().decode('cp1252', 'replace')
    _po = []
    for _m in _re_po.finditer(r'- (Life|Death|Earth|Air|Fire|Water)/(Life|Death|Earth|Air|Fire|Water) spells:', _po_txt):
        _k = frozenset((_m.group(1), _m.group(2)))
        if _k not in _po: _po.append(_k)
    def _po_key(_nm):
        _k = frozenset(_nm.replace(' Magic', '').split('/'))
        return _po.index(_k) if _k in _po else 99
    PAIR_SPHERES.sort(key=_po_key)
except Exception as _e_po:
    print('pair order from changelog failed:', _e_po)
PIPE_SPELLS = {}
try:
    import ast as _ast
    _ptree = _ast.parse(open('patch scripts/patch_dual_sphere_spells_v1.py', encoding='utf-8').read())
    for _n in _ast.walk(_ptree):
        if isinstance(_n, _ast.Call) and getattr(_n.func, 'id', '') == 'dict':
            _kw = {k.arg: k.value for k in _n.keywords if k.arg}
            if 'id' in _kw and 'name' in _kw and 'sphere' in _kw:
                _e = {}
                for _k in ('id', 'name', 'sphere', 'tier', 'icon', 'donor', 'tc_type'):
                    if _k in _kw:
                        try: _e[_k] = _ast.literal_eval(_kw[_k])
                        except Exception: pass
                if 'id' in _e: PIPE_SPELLS[_e['id']] = _e
except Exception as _e:
    print('pipeline spell list failed:', _e)
def _ptype(e):
    dn = e.get('donor') or ''
    if 'Summon' in dn: return 'Summon'
    if e.get('tc_type') is None: return 'Global'
    if dn in ('TWaterWalking', 'TDarkGift'): return 'Enchantment'
    return 'Combat'
try:
    _picons = _spellicn_icons(sorted({(e.get('icon') or e['id']) for e in PIPE_SPELLS.values()}))
except Exception as _e:
    print('pipeline spell icons failed:', _e); _picons = {}
_npipe = 0
for _sid, _e in sorted(PIPE_SPELLS.items()):
    _g = next((x for x in gspells if x['id'] == _sid + 10), None)
    if _g is None or _g['id'] in used_g: continue
    used_g.add(_g['id']); _npipe += 1
    _cast = str(_g['cast'] if _g['cast'] is not None else '')
    if _g.get('upkeep'): _cast += ' / %d' % _g['upkeep']
    spells_out.append(dict(sphere=SPH_ID.get(_e.get('sphere'), 'Other / New'), level=_g.get('slevel') or _e.get('tier') or 0,   # 1.37.423: live Spells.pfs level wins (editor edits)
                           name=_e['name'], cast=_cast,
                           research=str(_g['research'] if _g['research'] is not None else ''),
                           type=_ptype(_e), icon=_picons.get(_e.get('icon') or _sid, ''),
                           desc=_g['desc'], matched=True))
print('pipeline spells: %d listed (icons %d)' % (_npipe, len(_picons)))
# 2026-10-31: vanilla spells too get their icon rendered from SPELLICN.ILB (same renderer as the custom spells)
try:
    _vicons = _spellicn_icons(sorted({s['gicon'] for s in spells_out if s.get('gicon') is not None}))
except Exception as _e:
    print('vanilla spell icons failed:', _e); _vicons = {}
for _s in spells_out:
    _gi = _s.pop('gicon', None)
    if _gi in _vicons: _s['icon'] = _vicons[_gi]
print('vanilla spell icons from SPELLICN.ILB: %d' % len(_vicons))
# 11/01 (user: "for secret spells, their glow is too dim"): Secret-sphere clouds are far darker than the other spheres'
# (90th-percentile luminance 58 vs 94-193) -> re-render them with a cloud gain (the glyph multiply keeps the ink dark)
SECRET_GAIN = 2.0
try:
    _sid = {_nm: _iid for _k, (_nm, _iid, _t) in SECRET_SPELLS.items()}
    _sid.update({_e['name']: (_e.get('icon') or _i) for _i, _e in PIPE_SPELLS.items() if _e.get('sphere') == 7})
    _gi = _spellicn_icons(sorted(set(_sid.values())), gain=SECRET_GAIN)
    _ng = 0
    for _s in spells_out:
        if _s['sphere'] == SECRET and _sid.get(_s['name']) in _gi:
            _s['icon'] = _gi[_sid[_s['name']]]; _ng += 1
    print('secret spell icons brightened: %d' % _ng)
except Exception as _e:
    print('secret glow failed:', _e)

extra_g = [g for g in gspells if g['id'] not in used_g and g['desc']]
for g in extra_g:
    spells_out.append(dict(sphere='Other / New', level=0, name='(unnamed spell #%d)' % g['id'],
                           cast=str(g['cast'] or ''), research=str(g['research'] or ''),
                           type='', icon='', desc=g['desc'], matched=True))
print('spells: doc=%d game=%d matched=%d unmatched-game=%d' % (
    len(docspells), len(gspells), sum(1 for s in spells_out if s['matched'] and s['sphere'] != 'Other / New'), len(extra_g)))
SPHERE_LIST = SPHERES + [SECRET] + [p for p in PAIR_SPHERES if any(x['sphere'] == p for x in spells_out)] + (['Other / New'] if extra_g else [])
raceicons = {}
try:
    for _r in ORDER:
        _fp = os.path.join(HERE, 'race_icons', _r.replace(' ', '_') + '.png')
        if os.path.exists(_fp):
            raceicons[_r] = 'data:image/png;base64,' + base64.b64encode(open(_fp, 'rb').read()).decode()
except Exception as _e:
    print('race icons load failed:', _e)
# non-race group icons = specific units' portraits
GROUP_ICON_UNIT = {'Other Neutral Units': 'mysteriousfrog', 'Other Good Units': 'golddragon',
                   'Other Evil Units': 'werewolf', "Builder's Guild": 'flamethrowerram',
                   'Shipyard': 'dragonship', 'Other Machines': 'catapult'}
for _grp, _un in GROUP_ICON_UNIT.items():
    _u = next((u for u in units if normn(u['name']) == _un and u['img']), None)
    if _u: raceicons[_grp] = _u['img']
homeicons = {}
try:
    for _hk in ('keeper', 'cult', 'swordsman', 'mana', 'abilities',
                'changelog', 'changelog2', 'modding', 'modding2', 'community', 'community2', 'tanaris', 'gb5'):
        _fp = os.path.join(HERE, 'home_icons', _hk + '.png')
        homeicons[_hk] = 'data:image/png;base64,' + base64.b64encode(open(_fp, 'rb').read()).decode()
    homeicons['logo'] = 'data:image/png;base64,' + base64.b64encode(open(os.path.join(HERE, 'brand_logo.png'), 'rb').read()).decode()
except Exception as _e:
    print('home icons failed:', _e)
gcicons = {}
try:
    _GCMAP = {'Relations & Unit Morale': 'relations', 'Economy & Structures': 'city',
              'Magic': 'mana', 'Leaders & Heroes': 'leader', 'Abilities': 'abilities',
              'Vision': 'vision', 'Units': 'swordsman', 'AI': 'ai',
              'Miscellaneous': 'misc', 'Campaigns': 'keeper'}
    for _cat, _fn in _GCMAP.items():
        _fp = os.path.join(HERE, 'home_icons', _fn + '.png')
        gcicons[_cat] = 'data:image/png;base64,' + base64.b64encode(open(_fp, 'rb').read()).decode()
except Exception as _e:
    print('gc icons failed:', _e)
sphicons = {}
try:
    for _s in SPHERES + [SECRET]:
        _fp = os.path.join(HERE, 'sphere_icons', _s.split()[0].lower() + '.png')
        if os.path.exists(_fp):
            sphicons[_s] = 'data:image/png;base64,' + base64.b64encode(open(_fp, 'rb').read()).decode()
    # 1.37.420: dual-sphere pairs = the two sphere icons split along the diagonal (A top-left, B bottom-right)
    from PIL import Image as _PI
    import io as _pio
    for _pid, (_pa, _pb) in PAIRS.items():
        _ia = _PI.open(os.path.join(HERE, 'sphere_icons', _SPN[_pa].lower() + '.png')).convert('RGBA')
        _ib = _PI.open(os.path.join(HERE, 'sphere_icons', _SPN[_pb].lower() + '.png')).convert('RGBA').resize(_ia.size)
        _w, _h = _ia.size
        _mk = _PI.new('L', _ia.size, 0); _mp = _mk.load()
        for _yy in range(_h):
            for _xx in range(_w):
                _mp[_xx, _yy] = 255 if _xx + _yy >= _w else 0
        _im = _ia.copy(); _im.paste(_ib, (0, 0), _mk)
        _bf = _pio.BytesIO(); _im.save(_bf, 'PNG')
        sphicons[SPH_ID[_pid]] = 'data:image/png;base64,' + base64.b64encode(_bf.getvalue()).decode()
except Exception as _e:
    print('sphere icons load failed:', _e)

# ---- Overview: single intro entry + prominent Installation section ----
overviewitems = []
try:
    _ov_idx = list(range(i_ov + 1, i_gc))
    _inst = next(_k for _k in _ov_idx if paras[_k].strip().lower() == 'installation')
    _intro = [txtbr(_pnodes[_k]) for _k in _ov_idx if _k < _inst and paras[_k].strip()]
    overviewitems.append(dict(t='p', x=(chr(10) + chr(10)).join(_intro)))
    overviewitems.append(dict(t='h', x='Installation'))
    for _k in _ov_idx:
        if _k > _inst and paras[_k].strip():
            _xo = txtbr(_pnodes[_k])
            # user 2026-07-27: drop the ZIP-merge sentence
            _xo = re.sub(r'\s*You can simply merge the .Age of Wonders. folder from the ZIP file with your existing one\.', '', _xo)
            if _xo.strip(): overviewitems.append(dict(t='p', x=_xo))
    # Thanks/Acknowledgements (doc pre-section, user 2026-07-27: bottom of Overview)
    _tk = next((_k2 for _k2, _t2 in enumerate(paras)
                if _t2.strip().lower().startswith('thanks/acknowledg')), None)
    if _tk is not None:
        overviewitems.append(dict(t='h', x='Thanks / Acknowledgements'))
        for _k2 in range(_tk + 1, i_ov):
            if paras[_k2].strip():
                _x3 = txtbr(_pnodes[_k2]).replace('and' + chr(10) + 'paving', 'and paving')
                overviewitems.append(dict(t='p', x=_x3))
except StopIteration:
    overviewitems = [dict(t='p', x=x) for x in overview]
# Installation + Thanks superseded (user-maintained, installer era 2026-08-30;
# the doc still holds the old zip-install text and shorter credits list --
# keep only the parsed intro paragraph, hardcode the rest)
if overviewitems:
    overviewitems = overviewitems[:1] + [
        dict(t='h', x='Installation'),
        dict(t='p', html='With Age of Wonders installed, extract and run the <a href="https://aow.heavengames.com/downloads/showfile.php?fileid=1230" target="_blank" rel="noopener">AoWx Installer</a> (from any location, the installer does not need to be placed in game folder). The installer will then guide you through installation steps.'),
        dict(t='p', x='Once AoWx has been successfully installed, the game can be run from AoWx.exe, AoW.exe, or AoWSetup.exe (does not matter which).'),
        # 2026-09-01: Mouse Hotkeys (interactive block, rendered by the template's
        # t='hotkeys' branch) + Cheats (RE'd from TCheatTE.Execute @0x5574AF10)
        dict(t='h', x='Mouse Hotkeys'),
        dict(t='p', x='AoWx builds mouse hotkeys directly into the game engine. Hover over a combination below to highlight the buttons involved on the mouse preview. All hotkeys can be customized in the Mouse tab of AoWSetup.'),
        dict(t='hotkeys', x=''),
        dict(t='h', x='Cheats'),
        dict(t='p', x='Cheats are available in single player only. Enable the Cheat Mode toggle in the Developer tab of AoWSetup, then launch the game with the Play button (equivalent to the vanilla ' + chr(8220) + 'beatrix' + chr(8221) + ' launch argument). In game, press Ctrl+Shift+C (a confirmation sound plays), then type the cheat word. Press Ctrl+Shift+C again before each additional cheat.'),
        dict(t='p', x='- gold: all players receive 1,000 gold'),
        dict(t='p', x='- mana: all players receive 1,000 mana'),
        dict(t='p', x='- explore: toggles the entire map being explored'),
        dict(t='p', x='- fog: toggles fog of war'),
        dict(t='p', x='- spells: toggles all spells being castable (applies to all players)'),
        dict(t='p', x='- research: all spells become researched (all players)'),
        dict(t='p', x='- freemove: toggles unlimited unit movement'),
        dict(t='p', x='- towns: all independent towns join your empire'),
        dict(t='p', x='- win: instantly win the scenario'),
        dict(t='p', x='- lose: instantly lose the scenario'),
        dict(t='h', x='Thanks / Acknowledgements'),
        dict(t='p', x='- Alcedes, Booska, Paradox: Playtesting / Troubleshooting / Creative Input'),
        dict(t='p', x="- Ziggurat Mason aka Bing Xi Lao: Years of collaborative modding and shared knowledge, creative contributions, item GFX, campaign scenarios (Mirrored Oasis of Nathyazik [edited], Desolate Maugogom [edited], Frozen Waters of Seshedut [edited]), and probably more that I've forgotten"),
        dict(t='p', x='- And G: Introducing the AoW community to hex editing engine files and paving the way for the modern modding era'),
        dict(t='p', x='- The Chosen One aka Codyksp: Creative contributions, collaborative modding and shared knowledge'),
        dict(t='p', x='- Lagi: Units GFX, Scroll of Swiftness (the inspiration for AoWx mouse hotkeys)'),
        dict(t='p', x='- Igge: creating/sharing the first AoW Stable Diffusion model for AI generated portraits'),
        dict(t='p', x='- Markucjo: creating and sharing a script to crack map passwords'),
        dict(t='p', x='- The Groll: creative contributions, mapmaking'),
        dict(t='p', x='- Laurentius: Units GFX (various misc)'),
        dict(t='p', x='- Lord_Athos: Unit portrait (Goblin Waste Spewer)'),
        dict(t='p', x='- naru blutwind: Item GFX'),
        dict(t='p', x='- Zarlex: campaign scenario (Mountain Dive [edited])'),
        dict(t='p', x='- The Jerk: campaign scenario (Urgath [edited])'),
        dict(t='p', x='- You: Thank you for playing Age of Wonders X!'),
    ]

# ---- General Changes categories ----
GC_HEADS = {'relations:':'Relations','unit morale:':'Unit Morale','economy:':'Economy',
 'structures:':'Structures','magic:':'Magic','leaders & heroes':'Leaders & Heroes',
 'unit promotions:':'Unit Promotions','ranged attacks:':'Ranged Attacks','abilities:':'Abilities',
 'status effects:':'Status Effects','vision:':'Vision','general unit changes':'General Unit Changes',
 'boats':'Boats','items':'Items','ai:':'AI','other miscellaneous changes':'Miscellaneous',
 'custom campaign':'Campaigns'}
# doc indent attrs mislead for these lines (user: render flush)
GC_LVL_OVERRIDE = {
    '- the highmen and the undead': 0, '- wasteland is hated': 0, '- desert, ice': 0,
    '- all surface terrains': 0, '- all underground terrains': 0, '- racial terrain preferences': 0,
    '- level 1 summon spells': 0, '- level 2 summon spells': 0,
}
generalcats = []
_cur_cat = None
for _pi in range(i_gc + 1, i_iii):
    _pg = paras[_pi]; _lv = paras_lvl[_pi]
    if not _pg:
        if _cur_cat and _cur_cat['items'] and _cur_cat['items'][-1]['t'] != 'gap':
            _cur_cat['items'].append(dict(t='gap', x='', lvl=0))
        continue
    _key = _pg.strip().lower()
    if _key in GC_HEADS:
        _cur_cat = dict(name=GC_HEADS[_key], items=[])
        generalcats.append(_cur_cat)
        continue
    if _cur_cat is None:
        _cur_cat = dict(name='General', items=[])
        generalcats.append(_cur_cat)
    if _pg.startswith('(') and _cur_cat['items'] and _cur_cat['items'][-1]['t'] == 'p':
        _cur_cat['items'][-1]['x'] += chr(10) + txtbr(_pnodes[_pi])   # continuation of previous entry
        continue
    _t = 'h' if (not _pg.startswith('-') and len(_pg) < 70 and not _pg[0].isdigit()) else 'p'
    for _pref, _fl in GC_LVL_OVERRIDE.items():
        if _pg.lower().startswith(_pref): _lv = _fl; break
    _cur_cat['items'].append(dict(t=_t, x=txtbr(_pnodes[_pi]), lvl=_lv))
for _c in generalcats:
    while _c['items'] and _c['items'][-1]['t'] == 'gap': _c['items'].pop()
# Leaders & Heroes: group XP-per-day under a new header; indent stat-cost block
for _c in generalcats:
    if _c['name'] != 'Leaders & Heroes': continue
    _its = _c['items']
    for _j, _it in enumerate(_its):
        if _it['x'].lower().startswith('- heroes gain 3 experience per day'):
            _its.insert(_j, dict(t='p', x='- Leader/Hero XP Gain:', lvl=0))
            break
    for _it in _its:
        if _it['x'].lower().startswith('- heroes gain') and 'experience per day' in _it['x'].lower():
            _it['lvl'] = 1
    _cnt = 0; _on = False
    for _it in _its:
        if _it['x'].lower().startswith('- leader/hero stat increase costs'): _on = True; continue
        if _on and _it['t'] == 'p' and _cnt < 6:
            _it['lvl'] = 1; _cnt += 1
# General Unit Changes: drop the trailing Leadership note + 3 name stubs (user request)
for _c in generalcats:
    if _c['name'] == 'General Unit Changes':
        for _j, _it in enumerate(_c['items']):
            if _it['x'].lower().startswith('- some units have leadership'):
                _c['items'] = _c['items'][:_j]
                break
# AI: indent the 3 lines under 'AI bonus XP increased'; drop the outdated hero-upgrade block
for _c in generalcats:
    if _c['name'] != 'AI': continue
    _its = _c['items']; _out = []
    _skip = 0; _ind = 0
    for _it in _its:
        if _skip: _skip -= 1; continue
        _x = _it['x'].lower()
        if _x.startswith('- ai hero upgrade priorities revised'):
            _skip = 3; continue
        if _ind: _it['lvl'] = 1; _ind -= 1
        if _x.startswith('- ai bonus xp increased'):
            _it['lvl'] = 0; _ind = 3
        _out.append(_it)
    _c['items'] = _out
# 1.37.407 additions (2026-09-01, not yet in the doc): elemental feeding (before the Boats move so they stay in the main unit list)
for _c in generalcats:
    if _c['name'] == 'General Unit Changes':
        _c['items'].extend([
            dict(t='p', x='- Fire Elementals and Fire Sprites are healed by fire damage and lava:', lvl=0),
            dict(t='p', x='- Mixed damage does not heal (ie: Fireball spell, Salamander Strike, etc that do Fire/Physical damage have no healing effect)', lvl=1),
            dict(t='p', x='- Walking over lava heals 1 HP per hex', lvl=1),
            dict(t='p', x='- Does not apply if being transported', lvl=2),
            dict(t='p', x='- Applies in overworld and combat', lvl=2),
            dict(t='p', x='- Water Elementals are healed by water:', lvl=0),
            dict(t='p', x='- Swimming over water heals 1 HP per hex', lvl=1),
            dict(t='p', x='- Does not apply if being transported', lvl=2),
            dict(t='p', x='- Applies in overworld and combat', lvl=2),
            dict(t='p', x='- Water Elementals can no longer cross lava, despite having Fire Immunity, unless enchanted by Wind Walking or transported', lvl=0),
            dict(t='p', x='- Earth Elementals are healed by dirt:', lvl=0),
            dict(t='p', x='- Walking over dirt heals 1 HP per hex', lvl=1),
            dict(t='p', x='- Does not apply if being transported', lvl=2),
            dict(t='p', x='- Applies in overworld and combat', lvl=2),
        ])
# 1.37.410 additions (2026-09-23, not yet in the doc): mage leadership (General Unit Changes) + Legendary abilities (Unit Promotions)
for _c in generalcats:
    if _c['name'] == 'General Unit Changes':
        _c['items'].extend([
        dict(t='p', x='- Mage unit leadership modified:', lvl=0),
        dict(t='p', x='- Mage units that didn’t have Leadership I now gain it', lvl=1),
        dict(t='p', x='- Mage units that had Leadership I instead have Leadership II, etc', lvl=1),
        ])
    if _c['name'] == 'Unit Promotions':
        for _j, _it in enumerate(_c['items']):
            if _it['x'].lower().startswith('- legendary medal added'):
                _k = _j + 1
                while _k < len(_c['items']) and _c['items'][_k]['t'] == 'p' and _c['items'][_k].get('lvl', 0) >= 1: _k += 1
                _c['items'][_k:_k] = [
        dict(t='p', x='- Legendary medal units also gain the following abilities:', lvl=1),
        dict(t='p', x='- Archers/ranged units: additional level of Marksmanship', lvl=2),
        dict(t='p', x='- Mage units and some other units: additional level of multilevel abilities', lvl=2),
        dict(t='p', x='- Most humanoid units: Leadership I, or an additional level of Leadership if already owned', lvl=2),
        dict(t='p', x='- Some other thematic abilities added throughout the unit roster, but generally restrained to the above or similar', lvl=2),
        dict(t='p', x='- “Legendary” is displayed below Exp in the unit window', lvl=1),
                ]
                break
# move Boats into General Unit Changes (bottom, titled)
_gu = next((c for c in generalcats if c['name'] == 'General Unit Changes'), None)
_bo = next((c for c in generalcats if c['name'] == 'Boats'), None)
if _gu and _bo:
    _gu['items'].append(dict(t='h', x='Boats', lvl=0))
    _gu['items'].extend(_bo['items'])
    generalcats.remove(_bo)
# Miscellaneous edits (user 2026-07-27): remove two entries, fix demo-song quote
for _c in generalcats:
    if _c['name'] != 'Miscellaneous': continue
    _c['items'] = [i for i in _c['items'] if not (
        i['x'].startswith('- The city status Enslaved') or
        i['x'].startswith('- Exploration sites can now be explored in Tactical Combat'))]
    for _it in _c['items']:
        if 'In the Company of Elves added' in _it['x']:
            _it['x'] = _it['x'].replace('In the Company of Elves added',
                                        'In the Company of Elves' + chr(8217) + ' added')
    # drop the Scroll of Slickness block (script retired 1.37.406; user 2026-09-01):
    # the header line plus its indented hotkey sub-bullets
    _out = []; _sk = False
    for _it in _c['items']:
        if _it['x'].startswith('- Scroll of Slickness added'):
            _sk = True; continue
        if _sk and _it['t'] == 'p' and _it.get('lvl', 0) >= 1: continue
        _sk = False
        _out.append(_it)
    _c['items'] = _out
# 1.37.402 additions (2026-08-11, not yet in the doc): Miscellaneous
# (placed before the Items merge so they stay inside the Misc section proper)
for _c in generalcats:
    if _c['name'] != 'Miscellaneous': continue
    _c['items'].extend([
        dict(t='p', x='- AoWxGen.exe added ' + chr(8212) + ' standalone RNG Map and Image-to-Map generator:', lvl=0),
        dict(t='p', x='- Random Map Batch, fully customizable Custom RNG Maps (size, levels, players, terrain inversion, landmass and terrain-style presets) and Image-to-Map modes', lvl=1),
        dict(t='p', x='- Generated maps appear in Scenario\\Custom named by their RNG seed, ready to play or open in the editor', lvl=1),
        dict(t='p', x='- New ' + chr(8220) + 'Fullscreen (Optimized)' + chr(8221) + ' graphics setting: fullscreen at the same resolution as windowed mode (ALT+Tab no longer causes colour glitches)', lvl=0),
        dict(t='p', x='- Mouse scroll wheel now works in-game: scenario selection, leader portrait selection, leader customization and hero level-up abilities, event window (map scrolling locks while the cursor is over it), mana power distribution window, unit window for cycling between units (ie: arrows below unit preview) and unit abilities/descriptions', lvl=0),
        dict(t='p', x='- Fixed Out of Sync error when interacting with recruitable independent stacks in LAN', lvl=0),
        dict(t='p', x='- Intro video re-encoded (better Windows 10/11 compatibility, 90mb reduced to 33mb)', lvl=0),
        dict(t='p', x='- Maps auto-update abilities and HP on all units/leaders/heroes (fixes scenarios broken by multi-level abilities; units no longer spawn with partial HP where their HP was updated after map placement)', lvl=0),
        dict(t='p', x='- AoWDevX editor: unit floaters expanded (all units viewable/selectable when modifying productions within release.hss) and fixed some new features not working on other users' + chr(8217) + ' PCs', lvl=0),
    ])
# 1.37.406 + 407 additions (2026-08, not yet in the doc): Miscellaneous (changelog text verbatim)
for _c in generalcats:
    if _c['name'] != 'Miscellaneous': continue
    _c['items'].extend([
        dict(t='p', x='- Added mouse hotkeys to game directly:', lvl=0),
        dict(t='p', x='- Customizable within AoWSetup', lvl=1),
        dict(t='p', x='- Age of Wonders X Launcher retired (used to run AoWx.exe along with separate hotkey script simultaneously, no longer required and removed)', lvl=1),
        dict(t='p', x='- Changed multiplayer lobby default settings:', lvl=0),
        dict(t='p', x='- Customize Leaders now defaults to On', lvl=1),
        dict(t='p', x='- Allow Tactical Combat now defaults to Always', lvl=1),
        dict(t='p', x='- Always View TC now defaults to On', lvl=1),
        dict(t='p', x='- Fixed: end-turn hotkeys didn' + chr(8217) + 't activate end-turn symbol animation', lvl=0),
        dict(t='p', x='- Arrow keys now work when selecting scenarios/saves', lvl=0),
        dict(t='p', x='- Changed load/save timestamp format to YYYY-MM-DD HH-MM-SS', lvl=0),
        dict(t='p', x='- Guard vs Guard Area in-game text now properly differentiates unit behaviors (instead of simply displaying ' + chr(8220) + 'Guarding' + chr(8221) + ' for both)', lvl=0),
        dict(t='p', x='- Fixed: When navigating to own Leader' + chr(8217) + 's unit window via the Event tab portrait or picking up an item (as opposed to clicking unit within a party), the ' + chr(8220) + 'cycle unit' + chr(8221) + ' arrows did not appear below the unit GFX preview. These are now added and are mouse wheel scrollable.', lvl=0),
        dict(t='p', x='- Similar to above, ' + chr(8220) + 'cycle unit' + chr(8221) + ' arrows now added to enemy/independent unit windows, and are gated to prevent revealing concealed units within a party', lvl=0),
        dict(t='p', x='- Multiplayer out of sync fix improved (fixed instances in previous fix that would cause AI unit movement to appear instantaneous/skip movement animations to maintain timing/RNG seed, which could also manifest in single-player)', lvl=0),
        dict(t='p', x='- Modified Mind Decay tactical combat RNG result host/client propagation (should fix multiplayer desyncs)', lvl=0),
        dict(t='p', x='- Bug fix: Rare occurrence where wall damage in auto-combat could cause a dismissible/non-crashing ' + chr(8220) + 'BitError' + chr(8221) + ' pop-up due to mishandling of wall HP bar display', lvl=0),
        dict(t='p', x='- Bug Fix: ' + chr(8220) + 'Exception during Draw' + chr(8221) + ' could occur in very specific instances (ie: when in a city production screen, if the mouse was hovering over specific UI elements and the player was scrolling around to preview the city tactical map, the game would also attempt to scroll a non-scrollable UI element and display an error)', lvl=0),
        dict(t='p', x='- Bug fix (1.37.408): Resuming/reloading a multiplayer saved game (including autosaves) left all players permanently stuck on the ' + chr(8220) + 'Waiting for other players' + chr(8221) + ' screen (the host waited for a leader-customization confirmation that is skipped when loading a game already in progress)', lvl=0),
        dict(t='p', x='- Bug fix (1.37.409): The game froze when a player was defeated while still owning a unit spawned by Recall Spirits or Animate Dead in an earlier combat (the Summoned effect on units that persisted after combat was not linked to its unit, so removing the defeated player' + chr(8217) + 's enchantments never finished). Those effects are now linked correctly, Dispel Magic can remove them, and the engine drops any enchantment it cannot dispel instead of freezing', lvl=0),
        dict(t='p', x='- Group movement fixed/improved:', lvl=0),
        dict(t='p', x='- Pathfinding fixed (individual paths no longer impede each other)', lvl=1),
        dict(t='p', x='- On the overworld/strategic map, group-selected units share a single target hex:', lvl=1),
        dict(t='p', x='- Group-selected stackable units will now move and stack on the target hex', lvl=2),
        dict(t='p', x='- Group-selected non-stackable parties will now maintain grouping and assemble around the target hex (ie: move together to avoid getting split-stacked)', lvl=2),
        dict(t='p', x='- Default player name (editable in the multiplayer pre-lobby menu) is now updated by leader customization as well', lvl=0),
        dict(t='p', x='- Event tab only skips to the bottom when the mouse cursor is not within its display area', lvl=0),
        dict(t='p', x='- Anti-cheat indicators in multiplayer:', lvl=0),
        dict(t='p', x='- In-game indication alerts all players when the editor is open during gameplay (green flashing icon by the turn indicators)', lvl=1),
        dict(t='p', x='- In-game chat notification alerts all players when a saved game (asg file) is open in the editor during gameplay', lvl=1),
        dict(t='p', x='- In-game indication alerts all players when a second instance of the game is running during gameplay (red flashing icon by the turn indicators)', lvl=1),
        dict(t='p', x='- In-game chat notification alerts all players when a second instance of the game is opened during gameplay', lvl=1),
        dict(t='p', x='- Map coordinates (X, Y, Z) now displayed in-game (right end of the taskbar message box)', lvl=0),
        dict(t='p', x='- Mouse wheel scrolling added to the race assignment and preferred race dropdown selections in multiplayer lobbies', lvl=0),
        dict(t='p', x='- Bug fix (1.37.410): Breath attack interactions with partial obstructions have been fixed (ie: using a breath attack in a narrow crypt corridor now targets/hits enemies within range correctly, etc)', lvl=0),
        dict(t='p', x='- Bug fix (1.37.410): Crash when a hero entered combat while carrying an unequipped item with a multi-level ability of a lower level than the same ability granted by a different non-item source (ie: an unequipped item granting Leadership III while a Frost Queen granted Leadership IV)', lvl=0),
        dict(t='p', x='- Bug fix (1.37.410): Poison Plants wasteland terrain GFX added (existed in the vanilla image libraries but wasn’t set correctly)', lvl=0),
        dict(t='p', x='- Bug fix (1.37.410): The Magic management tab now updates dynamically instead of at the beginning of the turn (ie: upgrading Spellcasting mid-research did not update the research timer until the next turn, or until mana distribution was interacted with)', lvl=0),
        dict(t='p', x='- Bug fix (1.37.421): Fixed an Out of Sync instance that could happen when AI was grouping units together', lvl=0),
    ])
# split multi-line entries headed by a ':' line into title + indented sub-lines
for _c in generalcats:
    _out = []
    for _it in _c['items']:
        if _it['t'] == 'p' and chr(10) in _it['x']:
            _ls = _it['x'].split(chr(10))
            if _ls[0].rstrip().endswith(':'):
                _out.append(dict(t='p', x=_ls[0], lvl=_it.get('lvl', 0)))
                for _sub in _ls[1:]:
                    if _sub.strip():
                        _out.append(dict(t='p', x=_sub, lvl=min(3, _it.get('lvl', 0) + 1)))
                continue
        _out.append(_it)
    _c['items'] = _out
# AI spell-logic block: descriptor lines indent under their spell-name lines
for _c in generalcats:
    if _c['name'] != 'AI': continue
    _in_blk = False
    for _it in _c['items']:
        if _it['x'].lower().startswith('- ai combat spell logic modified'): _in_blk = True; continue
        if _in_blk:
            if _it.get('lvl', 0) == 0: _in_blk = False; continue
            if not _it['x'].rstrip().endswith(':'): _it['lvl'] = 2
# 1.37.406 additions: Items fixes (before the merge so they land in the Items subsection)
for _c in generalcats:
    if _c['name'] != 'Items': continue
    _c['items'].extend([
        dict(t='p', x='- Fixed abilities on ' + chr(8220) + 'Use' + chr(8221) + ' slot items (ie: Marksmanship on bows works correctly now, etc)', lvl=0),
        dict(t='p', x='- Fixed Spellcasting on items (now correctly castable without requiring Spellcasting as a base ability)', lvl=0),
        dict(t='p', x='- Fixed Healing on items (now usable outside of combat, and no longer infinite use in combat)', lvl=0),
        dict(t='p', x='- “Use” slot items can now grant stat increases', lvl=0),
        dict(t='p', x='- Items can now grant HP and MP in addition to other stats', lvl=0),
        dict(t='p', x='- Items can now decrease stats', lvl=0),
    ])
# user 2026-09-23: reword the doc's item-GFX line (hundreds now; no credits)
for _c in generalcats:
    if _c['name'] == 'Items':
        for _it in _c['items']:
            if _it['x'].lower().startswith('- dozens of all-new item gfx'): _it['x'] = '- Hundreds of all-new item GFX.'
# merge Items into Miscellaneous (bottom, titled)
_mi = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
_itc = next((c for c in generalcats if c['name'] == 'Items'), None)
if _mi and _itc:
    _mi['items'].append(dict(t='h', x='Items', lvl=0))
    _mi['items'].extend(_itc['items'])
    generalcats.remove(_itc)
# 1.37.407 + 410 additions (2026-09-01 / 2026-09-23, not yet in the doc): Abilities (before the Ranged/Status merges so they stay in the main list)
_abx = next((c for c in generalcats if c['name'] == 'Abilities'), None)
if _abx:
    _abx['items'].extend([
        dict(t='p', x='- Conjurer I/II/III added (5 skill points per level):', lvl=0),
        dict(t='p', x='- I: Reduce research cost of summoning spells by 33%', lvl=1),
        dict(t='p', x='- II: Reduce casting cost of summoning spells by 33%', lvl=1),
        dict(t='p', x='- III: Reduce upkeep of summoning spells by 33%', lvl=1),
        dict(t='p', x='- Enchanter I/II/III added (5 skill points per level):', lvl=0),
        dict(t='p', x='- I: Reduce research cost of unit enchantments by 33%', lvl=1),
        dict(t='p', x='- II: Reduce casting cost of unit enchantments by 33%', lvl=1),
        dict(t='p', x='- III: Reduce upkeep of unit enchantments by 33%', lvl=1),
        dict(t='p', x='- Evoker I/II/III added (5 skill points per level):', lvl=0),
        dict(t='p', x='- I: Reduce research cost of combat spells by 33%', lvl=1),
        dict(t='p', x='- II: Reduce casting cost of combat spells by 33%', lvl=1),
        dict(t='p', x='- III: Reduce casting cost of combat spells by 50%', lvl=1),
        dict(t='p', x='- Ritualist I/II/III added (5 skill points per level):', lvl=0),
        dict(t='p', x='- I: Reduce research cost of global spells by 33%', lvl=1),
        dict(t='p', x='- II: Reduce casting cost of global spells by 33%', lvl=1),
        dict(t='p', x='- III: Reduce upkeep of global spells by 33%', lvl=1),
        dict(t='p', x='- Holy/Unholy Champion I/II/III added (3 skill points per level):', lvl=0),
        dict(t='p', x='- I: +1 ATK / +1 DMG', lvl=1),
        dict(t='p', x='- II: +2 ATK / +2 DMG', lvl=1),
        dict(t='p', x='- III: +3 ATK / +3 DMG', lvl=1),
        dict(t='p', x='- Similarly to Monster/Hero Slaying I/II/III, bonuses apply to short and medium ranged projectiles (but not long range)', lvl=1),
        dict(t='p', x='- Path of Frost modified:', lvl=0),
        dict(t='p', x='- Changes Water to Ice (unchanged)', lvl=1),
        dict(t='p', x='- Changes Lava to Wasteland', lvl=1),
        dict(t='p', x='- Changes surface terrains to Snow (unchanged)', lvl=1),
    ])
# 1.37.410: Leadership others-only rule grouped under the Leadership I-V entry (user: group similar entries)
for _c in generalcats:
    if _c['name'] != 'Abilities': continue
    for _j, _it in enumerate(_c['items']):
        if _it['x'].lower().startswith('- leadership i/ii/iii/iv/v added'):
            _k = _j + 1
            while _k < len(_c['items']) and _c['items'][_k]['t'] == 'p' and _c['items'][_k].get('lvl', 0) >= 1: _k += 1
            _c['items'].insert(_k, dict(t='p', x='- Leadership now only applies to other units in the party (not self)', lvl=1))
            break
# 1.37.410 additions (2026-09-23): Status Effects
_se = next((c for c in generalcats if c['name'] == 'Status Effects'), None)
if _se:
    _se['items'].extend([
        dict(t='p', x='- Lightning damage can inflict Burning status on Machines (same chance roll that would stun a creature; no extra fire damage on the hit)', lvl=0),
    ])
# merge Ranged Attacks + Status Effects into Abilities (as titled subsections)
_ab = next((c for c in generalcats if c['name'] == 'Abilities'), None)
if _ab:
    for _mn in ('Ranged Attacks', 'Status Effects'):
        _mc = next((c for c in generalcats if c['name'] == _mn), None)
        if _mc:
            _ab['items'].append(dict(t='h', x=_mn, lvl=0))
            _ab['items'].extend(_mc['items'])
            generalcats.remove(_mc)
# small doc typo fixes
for _c in generalcats:
    for _it in _c['items']:
        _it['x'] = _it['x'].replace(chr(10) + 'II: +2 ATK', chr(10) + '- II: +2 ATK')
        _it['x'] = _it['x'].replace('(unit is' + chr(10) + 'hidden', '(unit is hidden')
# Unit Promotions: rebuild the stat-increase pseudo-table as a real table
for _c in generalcats:
    if _c['name'] != 'Unit Promotions': continue
    _its = _c['items']
    _keep = []
    _skip_prefixes = ('- silver- gold', '- atk:', '- def:', '- dmg:', '- res:', '- hp:')
    for _it in _its:
        if any(_it['x'].lower().startswith(_s) for _s in _skip_prefixes): continue
        _keep.append(_it)
        if _it['x'].lower().startswith('- unit promotion stat increases'):
            _keep.append(dict(t='table', x='', lvl=0, rows=[
                ['', 'Silver', 'Gold', 'Each +10XP', 'Legendary'],
                ['ATK', '+1 ATK', '+1 ATK', chr(8212), '+1 ATK'],
                ['DEF', '+1 DEF', chr(8212), chr(8212), chr(8212)],
                ['DMG', chr(8212), '+1 DMG', chr(8212), chr(8212)],
                ['RES', '+1 RES', '+1 RES', chr(8212), '+2 RES'],
                ['HP', '+2 HP', '+2 HP', '+2 HP', 'No further HP gain'],
            ]))
    _c['items'] = _keep
# Magic: everything after 'Spell Level & Sphere Changes:' indents one level uniformly
for _c in generalcats:
    if _c['name'] != 'Magic': continue
    _on = False
    for _it in _c['items']:
        if _it['x'].lower().startswith('- spell level & sphere changes'): _on = True; continue
        if _on and _it['t'] == 'p': _it['lvl'] = 1
# arena medal-cost rework (2026-07-27, not yet in the doc): append to Structures
_st = next((c for c in generalcats if c['name'] == 'Structures'), None)
if _st:
    _st['items'].extend([
        dict(t='p', x='- Arena medal training costs revised:', lvl=0),
        dict(t='p', x='- Silver: (1 gold x unit level) per XP', lvl=1),
        dict(t='p', x='- Gold: (2 gold x unit level) per XP', lvl=1),
        dict(t='p', x='- Gold medal units and heroes cannot use Arenas', lvl=1),
    ])
# 1.37.402 additions (2026-08-11, not yet in the doc): Structures + Magic
if _st:
    _st['items'].extend([
        dict(t='p', x='- Spring of Life effects by terrain:', lvl=0),
        dict(t='p', x='- All terrain except wasteland: heals/blesses all living units, no effect on undead', lvl=1),
        dict(t='p', x='- Wasteland: same effect as a poison cloud on living units (no longer heals/blesses), heals/blesses undead', lvl=1),
        dict(t='p', x='- Exploration sites (monster lairs, dungeons, etc) can be entered in tactical combat in multiplayer:', lvl=0),
        dict(t='p', x='- Observing players are pulled into the combat and see exactly what the exploring player sees, revealing the site map as the explorer reveals it', lvl=1),
        dict(t='p', x='- Site defenders engage immediately instead of waiting to be spotted', lvl=1),
    ])
_mg = next((c for c in generalcats if c['name'] == 'Magic'), None)
if _mg:
    _mg['items'].extend([
        dict(t='p', x='- Secret Magic spells added (original secret spells had been moved to Cosmos or repurposed, leaving Wizard Towers preset to random Secret spells empty):', lvl=0),
        dict(t='p', x='- Summon Mermaid (level 1 global, 6 cost / 3 upkeep)', lvl=1),
        dict(t='p', x='- Magic Sight (level 2 enchantment, 5 cost / 1 upkeep): grants the unit Night Vision and True Seeing', lvl=1),
        dict(t='p', x='- Void Step (level 3 combat, 5 cost): teleports the caster to a valid hex up to 8 away (invalid targets warp to the closest valid hex); allows initiating combat against walled structures and bypassing walls in tactical combat', lvl=1),
        dict(t='p', x='- Summon Silver Dragon (level 4 global, 100 cost / 12 upkeep)', lvl=1),
    ])
# 1.37.407 additions (2026-09-01, not yet in the doc): Structures + Magic
if _st:
    _st['items'].extend([
        dict(t='p', x='- Exploration sites now roll unique random results for defenders/prisoners (ie: previously, two Monster Lairs on the same map would roll the same random defenders if set to the same strength, or ' + chr(8220) + 'random' + chr(8221) + ' strength)', lvl=0),
        dict(t='p', x='- Elemental Nodes heal and apply Nature' + chr(8217) + 's Blessing to certain units:', lvl=0),
        dict(t='p', x='- Air Node:', lvl=1),
        dict(t='p', x='- Air Elemental, Frost Queen, Silver Dragon', lvl=2),
        dict(t='p', x='- Earth Node:', lvl=1),
        dict(t='p', x='- Druid, Earth Elemental, Ent, Forest Dragon, Nature Elemental', lvl=2),
        dict(t='p', x='- Fire Node:', lvl=1),
        dict(t='p', x='- Dwarf First Born, Fire Elemental, Fire Sprite, Hell Hound, Yaka Avatar', lvl=2),
        dict(t='p', x='- Water Node:', lvl=1),
        dict(t='p', x='- Frost Queen, Water Elemental', lvl=2),
        dict(t='p', x='- Life Node:', lvl=1),
        dict(t='p', x='- Astra, Gold Dragon, Nature Elemental, Spirit Puppet, Greater Spirit Puppet', lvl=2),
        dict(t='p', x='- Death Node:', lvl=1),
        dict(t='p', x='- Black Dragon, Hell Hound, Resurrected Dragon, Shadow Dragon, Spider Queen, all Undead units', lvl=2),
        dict(t='p', x='- Mana Node:', lvl=1),
        dict(t='p', x='- Elder Dragon, Syron', lvl=2),
    ])
if _mg:
    for _it in _mg['items']:
        if _it['x'].lower().startswith('- leader/hero mana income changed'):
            _it['x'] = '- Leader/Hero mana income changed to (Spellcasting level) x 1.5 x Resistance'
    _mg['items'].extend([
        dict(t='p', x='- Raise Terrain modified:', lvl=0),
        dict(t='p', x='- Now works underground', lvl=1),
        dict(t='p', x='- Creates temporary earth on dirt hexes', lvl=2),
        dict(t='p', x='- Now works on lava', lvl=1),
        dict(t='p', x='- Creates temporary dirt on lava hexes (both surface and underground)', lvl=2),
        dict(t='p', x='- When cast on temporary dirt over lava, creates temporary wasteland mountains (on surface) or temporary earth (underground)', lvl=2),
        dict(t='p', x='- Temporary wasteland mountains and temporary earth revert to permanent dirt (ie: casting Raise Terrain over lava twice permanently turns lava into dirt)', lvl=2),
        dict(t='p', x='- Added magic glow effect to temporary terrain created by Raise Terrain (ie: similar to Freeze Terrain)', lvl=0),
    ])
# 1.37.410 additions (2026-09-23, not yet in the doc): Magic + Structures
if _mg:
    _mg['items'].extend([
        dict(t='p', x='- Town Quake modified:', lvl=0),
        dict(t='p', x='- Before:', lvl=1),
        dict(t='p', x='- 7 ATK / 5 DMG against units', lvl=2),
        dict(t='p', x='- 70% chance to destroy walls', lvl=2),
        dict(t='p', x='- Now:', lvl=1),
        dict(t='p', x='- 7 ATK / 5 DMG against units on the surface (unchanged)', lvl=2),
        dict(t='p', x='- 9 ATK / 5 DMG against units underground if the city has no walls or wood walls', lvl=2),
        dict(t='p', x='- 7 ATK / 5 DMG against units underground if the city has stone walls (unchanged)', lvl=2),
        dict(t='p', x='- 80% chance to destroy wood walls on the surface', lvl=2),
        dict(t='p', x='- 90% chance to destroy wood walls underground', lvl=2),
        dict(t='p', x='- 50% chance to destroy stone walls on the surface', lvl=2),
        dict(t='p', x='- 60% chance to destroy stone walls underground', lvl=2),
        dict(t='p', x='- Vortex modified:', lvl=0),
        dict(t='p', x='- Before:', lvl=1),
        dict(t='p', x='- 8 ATK', lvl=2),
        dict(t='p', x='- 10 DMG against units with Sailing', lvl=2),
        dict(t='p', x='- 7 DMG against units with Swimming', lvl=2),
        dict(t='p', x='- 0 DMG against all other units', lvl=2),
        dict(t='p', x='- Cost: 10', lvl=2),
        dict(t='p', x='- Now:', lvl=1),
        dict(t='p', x='- 10 ATK', lvl=2),
        dict(t='p', x='- 7 DMG and consumes 0-8 MP against units with Sailing', lvl=2),
        dict(t='p', x='- 5 DMG and consumes 0-12 MP against units with Swimming', lvl=2),
        dict(t='p', x='- 2 DMG and consumes 0-6 MP against all other ground units', lvl=2),
        dict(t='p', x='- 0 DMG and never consumes MP against units with Flying, Floating, or Wind Walking', lvl=2),
        dict(t='p', x='- Cost: 15', lvl=2),
        dict(t='p', x='- Ooze now extinguishes flames and removes Burning status', lvl=0),
        dict(t='p', x='- Freeze Water changed to Freeze Terrain:', lvl=0),
        dict(t='p', x='- Changes Water to Ice (unchanged)', lvl=1),
        dict(t='p', x='- Changes Lava to Wasteland', lvl=1),
        dict(t='p', x='- Changes surface terrains to Snow', lvl=1),
        dict(t='p', x='- Ice Storm (including cast from an Altar of Ice) modified:', lvl=0),
        dict(t='p', x='- Changes Water to Ice (unchanged)', lvl=1),
        dict(t='p', x='- Changes Lava to Wasteland', lvl=1),
        dict(t='p', x='- Changes surface terrains to Snow (unchanged)', lvl=1),
        dict(t='p', x='- Level Terrain now spawns terrain-appropriate rocks (and a mix of rocks and cracks underground) instead of bare terrain', lvl=0),
        dict(t='p', x='- Death Storm/Divine Storm/Pestilence (spells and altars) modified:', lvl=0),
        dict(t='p', x='- Vertigo can now be inflicted by storms (previously, storms could only inflict Cursed and Poisoned)', lvl=1),
        dict(t='p', x='- Status effects now roll against RES (previously, all damaged units were automatically inflicted with status effects)', lvl=1),
    ])
if _st:
    _st['items'].extend([
        dict(t='p', x='- Holy/Unholy Woods and Poison Plants modified:', lvl=0),
        dict(t='p', x='- Vertigo/Cursed can now be inflicted by Holy/Unholy Woods (previously, only Poison Plants could inflict Poisoned)', lvl=1),
        dict(t='p', x='- Status effects now roll against RES (previously, all damaged units were automatically inflicted with status effects)', lvl=1),
    ])
# 1.37.405 + 406 additions (2026-08-15/23, not yet in the doc): AI
_ai = next((c for c in generalcats if c['name'] == 'AI'), None)
if _ai:
    _ai['items'].extend([
        dict(t='p', x='- Infinite Range Spell Reaction:', lvl=0),
        dict(t='p', x='- Defenders no longer wait while taking damage (ie: AI would not move until attacker was in range or walls were breached, allowing spells like Swarm to be exploited against the AI while they stood still indefinitely). Now, defenders will react to any damage by charging forward.', lvl=1),
        dict(t='p', x='- Attack/Retreat Reaction:', lvl=0),
        dict(t='p', x='- If an attacker retreats without inflicting any damage, the AI defender will not react (unchanged vanilla behaviour)', lvl=1),
        dict(t='p', x='- If an attacker retreats after inflicting any damage, the AI defender will pursue the attacker on the overworld map and reinitiate combat as the attacker', lvl=1),
        dict(t='p', x='- AI players only (not independents): any stacks within 6 hexes of the retaliating defender will also attempt to join the combat if able', lvl=1),
        dict(t='p', x='- Once the retreating attacker is killed or out of movement range, the AI defender will return to its original location and resume previous behavior', lvl=1),
        dict(t='p', x='- AI Tactical Combat Improvements:', lvl=0),
        dict(t='p', x='- All units are now aware of opportunity strikes from adjacent enemies:', lvl=1),
        dict(t='p', x='- Prior to performing an action, the vanilla AI evaluates available options and assigns each a score based on multiple criteria (own unit combat strength, target combat strength, ability/spell damage potential, etc)', lvl=2),
        dict(t='p', x='- If an action would provoke an opportunity attack, that action' + chr(8217) + 's score is now lowered based on the combat strength of the adjacent enemy, the amount of adjacent enemies, and the remaining HP of the moving unit', lvl=2),
        dict(t='p', x='- AI Leader/Hero passiveness:', lvl=1),
        dict(t='p', x='- Vanilla AI has a self-preservation multiplier for heroes/leaders, which has been reduced as follows:', lvl=2),
        dict(t='p', x='- Heroes lowered from x2 to x1 (removed)', lvl=3),
        dict(t='p', x='- Leaders lowered from x4 to x2', lvl=3),
        dict(t='p', x='- Vanilla AI has a x0.5 multiplier to ' + chr(8220) + 'melee strike' + chr(8221) + ' action score for heroes/leaders which has been increased to x0.8', lvl=2),
        dict(t='p', x='- Fixed AI pathfinding bug:', lvl=0),
        dict(t='p', x='- On rare occasion (or not so rare on huge ' + chr(8220) + 'busy' + chr(8221) + ' maps like Athendore), the AI could get stuck in an infinite loop of failed movement attempts along a valid route that was rendered invalid before it executed, causing the AI to never end its turn. The pathfinding logic will now force a ' + chr(8220) + 'no movement' + chr(8221) + ' condition onto a stuck unit/party following 20 failed movement attempts.', lvl=1),
        dict(t='p', x='- AI Item Interactions:', lvl=0),
        dict(t='p', x='- AI now picks up items from the ground and equips them, and also picks up ' + chr(8220) + 'Use' + chr(8221) + ' slot items if inventory isn' + chr(8217) + 't full', lvl=1),
        dict(t='p', x='- AI now evaluates item strength based on total granted stat/ability cost', lvl=1),
        dict(t='p', x='- AI will switch out equipped items with better found items, and ignore any weaker items', lvl=1),
        dict(t='p', x='- AI Exploration Site Interactions:', lvl=0),
        dict(t='p', x='- AI can now initiate combat against exploration sites', lvl=1),
        dict(t='p', x='- AI evaluates exploration site defender combat strength and ignores if own strength is less than 1.5x stronger', lvl=1),
        dict(t='p', x='- Exploration site target priority scales with AI party combat strength advantage (ie: the stronger the AI party is compared to defenders, the higher the likelihood the AI will attempt exploration)', lvl=1),
    ])
# 1.37.410 additions (2026-09-23, not yet in the doc): AI (tactical combat logic)
if _ai:
    _ai['items'].extend([
        dict(t='p', x='- Tactical combat logic upgrades (1.37.410):', lvl=0),
        dict(t='p', x='- Hero/leader targeting logic modified:', lvl=1),
        dict(t='p', x='- Fear of retaliation against heroes reduced by 50% (ie: AI targets heroes more aggressively)', lvl=2),
        dict(t='p', x='- Fear of retaliation against leaders removed entirely (ie: AI targets leaders much more aggressively)', lvl=2),
        dict(t='p', x='- Status effect recognition (ability score modifier used for action selection, target priority, fear of retaliation, etc):', lvl=1),
        dict(t='p', x='- Melee: Entangle Strike +50% weighting, Lightning Strike +30%, Cold Strike +25%', lvl=2),
        dict(t='p', x='- Ranged: Stunned (Cosmic Breath, Doom Gaze, Lightning Bolts) +50% weighting, Frozen (Cold Breath, Frost Bolts) +25%', lvl=2),
        dict(t='p', x='- Leader/Hero self-preservation modified and “final stand” added:', lvl=1),
        dict(t='p', x='- Most leader/hero actions aside from Spellcasting were restricted while other friendly units still existed. These restrictions are no longer hardlocked.', lvl=2),
        dict(t='p', x='- Self-preservation weighting is now proportional to total friendly unit combat value relative to self-value, with an added modifier based on starting vs current army strength (ie: a heavily guarded leader generally remains conservative but can perform more actions, and gradually becomes more aggressive as its army strength decreases, culminating in desperate behaviour targeting the enemy leader/hero once its army is defeated)', lvl=2),
        dict(t='p', x='- Combat unpredictability:', lvl=1),
        dict(t='p', x='- When comparing melee vs ranged scores, the AI has a 10% chance to select the opposite action (not for level 1 and 2 units, and not if either action scores zero or less)', lvl=2),
        dict(t='p', x='- Every turn, heroes have a 15% chance to lose 50% fear of retaliation and a 10% chance to lose all of it; leaders 10% and 5% respectively', lvl=2),
        dict(t='p', x='- To avoid out-of-sync errors in multiplayer these rolls are not true RNG but a static formula over shared battle state (positions, stats, unit IDs, unit counts, completed actions and turns), identical between host and clients yet practically unpredictable', lvl=2),
        dict(t='p', x='- Leader/hero touch ability priority fixed (a flag was being applied as a 0.01 multiplier; now a mid-mark 0.5 multiplier)', lvl=1),
        dict(t='p', x='- Healing combat priority logic modified:', lvl=1),
        dict(t='p', x='- Units (including leaders/heroes) can now self-heal, rather than only heal other units', lvl=2),
        dict(t='p', x='- Wound weighting changed from (max HP / current HP) to (1 + missing HP / max HP); Poisoned counts as 3 missing HP', lvl=2),
        dict(t='p', x='- Tiered targets: T1 = leader/hero missing at least 40% HP, T2 = leader/hero missing at least the Healing value considered, T3 = everything else. Leaders/heroes weight T1/T2 targets x1.00, self-healing at T1 x2.00, T3 targets x0.25; a T1/T2 target that can move out of enemy reach without attacks of opportunity retreats before healing', lvl=2),
        dict(t='p', x='- Mortal Danger (T3): x1.5 priority if remaining HP is at or below the expected damage from enemies that can reach it; Hopeless: a weak unit in Mortal Danger that healing would not save gets x0.25 instead', lvl=2),
        dict(t='p', x='- Waste avoidance (priority scales down with wasted healing), future-use weighting for high value units, healing reconsidered after every action, multilevel healing values (5/7/10) capped by missing HP', lvl=2),
        dict(t='p', x='- Improved melee vs ranged decision making: a decay is applied to the melee score in proportion to distance from the target, scaling back once the target is within melee range and further with melee strength', lvl=1),
        dict(t='p', x='- Once walls have been breached, the target value of ram units drops to essentially zero', lvl=1),
        dict(t='p', x='- The delay between AI units moving has been reduced significantly, particularly in large battles', lvl=1),
        dict(t='p', x='- Improved projectile logic (Shoot Now vs Move & Shoot):', lvl=1),
        dict(t='p', x='- Before: a partially obstructed shot was compared with other firing hexes on binary logic only (lower obstruction chance: yes/no)', lvl=2),
        dict(t='p', x='- Now: graduated logic (50% vs 40% obstruction yields proportionate multipliers); giving up an available shot to reposition costs a x0.65 penalty (x0.45 against heroes, x0.30 against leaders); Mortal Danger adds a further x0.50 penalty and Hopeless removes the option entirely', lvl=2),
        dict(t='p', x='- Move & Shoot approach is more lax on the landing hex (ie: approaching Archers can settle for a slightly obstructed position rather than moving too close in search of a perfect one)', lvl=2),
        dict(t='p', x='- Leader/Hero level-up logic modified: Marksmanship is gated behind ownership of a ranged attack and its weighting increased from 5/5 to 20/20', lvl=1),
    ])
# 1.37.407 additions (2026-09-01, not yet in the doc): Vision + Campaigns
_vi = next((c for c in generalcats if c['name'] == 'Vision'), None)
if _vi:
    _vi['items'].append(dict(t='p', x='- Underground earth/rock now block vision (ie: can no longer see through walls)', lvl=0))
_cp = next((c for c in generalcats if c['name'] == 'Campaigns'), None)
if _cp:
    _cp['items'][0:0] = [
        dict(t='p', x='- Custom and vanilla campaigns now both playable:', lvl=0),
        dict(t='p', x='- Toggle option in AoWSetup to switch between campaigns', lvl=1),
        dict(t='p', x='- Known issues: both custom and vanilla campaigns need updating (ie: heroes with negative skill points, etc)', lvl=1),
        dict(t='gap', x='', lvl=0),
    ]
# combine categories (user request): Relations+Unit Morale, Economy+Structures, General Unit Changes+Unit Promotions
for _a, _b, _nm in (('Relations', 'Unit Morale', 'Relations & Unit Morale'),
                    ('Economy', 'Structures', 'Economy & Structures'),
                    ('General Unit Changes', 'Unit Promotions', 'Units')):
    _ca = next((c for c in generalcats if c['name'] == _a), None)
    _cb = next((c for c in generalcats if c['name'] == _b), None)
    if _ca and _cb:
        _ca['name'] = _nm
        _ca['items'].append(dict(t='h', x=_b, lvl=0))
        _ca['items'].extend(_cb['items'])
        generalcats.remove(_cb)
# ---- 1.37.420: distribute the newest changelogs.txt release (Version 1.37.420) into the General Changes
# categories. Section -> category: Spells->Magic (summary + general spell changes; the per-spell details live in
# the Spells tab), AI Improvements->AI, Abilities->Abilities, Units->Units, Structures->Economy & Structures,
# Miscellaneous / Map Playlist / Bug Fixes -> Miscellaneous (own sub-headers). ----
try:
    _cl = open('X/Documentation/changelogs.txt', 'rb').read().decode('cp1252', 'replace').split(chr(10))
    _cl = [l.rstrip() for l in _cl]
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.420'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))   # next release date line
    _EMO = re.compile(r'<:[A-Za-z0-9_~]+:\d+>|:[A-Za-z0-9_~]+:')
    _secs = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _secs[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3 if _nsp <= 27 else 4 if _nsp <= 32 else 5
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _secs[_cur].append((_lv, _x if _x.startswith('-') else '- ' + _x))
    def _cat(name):
        return next((c for c in generalcats if c['name'] == name), None)
    def _push(name, lines, header=None):
        c = _cat(name)
        if c is None or not lines: return
        if c['items'] and c['items'][-1]['t'] != 'gap': c['items'].append(dict(t='gap', x='', lvl=0))
        if header: c['items'].append(dict(t='h', x=header))
        for _lv, _x in lines: c['items'].append(dict(t='p', x=_x, lvl=min(_lv, 3)))
    # Spells -> Magic: top-level items, the dual-sphere rules (before the first per-pair list), and a
    # per-sphere name summary built from the pipeline (full details are in the Spells tab)
    _sp = _secs.get('Spells', [])
    _mag = []
    _i = 0
    while _i < len(_sp):
        _lv, _x = _sp[_i]
        if _lv == 0:
            _mag.append((0, _x))
            if _x.lower().startswith('- dual-sphere spells added'):
                _j = _i + 1
                while _j < len(_sp) and _sp[_j][0] > 0:
                    if _sp[_j][0] == 1 and re.search(r'spells:$', _sp[_j][1]): break
                    _mag.append(_sp[_j]); _j += 1
        _i += 1
    _by = collections.OrderedDict()
    for _e in sorted(PIPE_SPELLS.values(), key=lambda e: (e.get('sphere', 99), e.get('tier', 0), e['name'])):
        _by.setdefault(SPH_ID.get(_e.get('sphere'), 'Other'), []).append(_e['name'])
    _sumr = []
    for _sn, _nl in _by.items():
        _sumr.append((1, '- %s: %s' % (_sn.replace(' Magic', ''), ', '.join(_nl))))
    _sing = [t for t in _sumr if '/' not in t[1].split(':')[0]]
    _pair = [t for t in _sumr if '/' in t[1].split(':')[0]]
    _mag2 = []; _k = 0
    while _k < len(_mag):
        _lv, _x = _mag[_k]; _mag2.append((_lv, _x)); _k += 1
        _xl = _x.lower()
        if _lv == 0 and (_xl.startswith('- new spells added') or _xl.startswith('- dual-sphere spells added')):
            while _k < len(_mag) and _mag[_k][0] > 0:      # keep the section's own rules first
                _mag2.append(_mag[_k]); _k += 1
            if _xl.startswith('- new spells added'):
                _mag2 += _sing + [(1, '- See the Spells tab for every new spell' + chr(8217) + 's stats and description')]
            else:
                _mag2 += [(1, '- New dual-sphere spells:')] + [(2, _x2) for _lv2, _x2 in _pair]
    # user 10/20: no 1.37.420 sub-headers; Magic drops the items after Shock Wave (upkeep/cost tweaks stay changelog-only)
    _cut = next((_q for _q, (_lv, _x) in enumerate(_mag2) if _lv == 0 and _x.lower().startswith('- shock wave')), None)
    if _cut is not None: _mag2 = _mag2[:_cut + 1]
    _push('Magic', _mag2, header=None)
    _push('AI', _secs.get('AI Improvements', []), header=None)
    def _blocks(lines):
        out = []
        for _lv, _x in lines:
            if _lv == 0 or not out: out.append([(_lv, _x)])
            else: out[-1].append((_lv, _x))
        return out
    def _items(blk):
        return [dict(t='p', x=_x, lvl=min(_lv, 3)) for _lv, _x in blk]
    # Abilities: main list (before 'Ranged Attacks'), Hurl Skull + Shoot Black Javelin into Ranged Attacks
    _ab4 = _cat('Abilities')
    if _ab4:
        _main = []; _rng = []
        for _blk in _blocks(_secs.get('Abilities', [])):
            _h = _blk[0][1].lower()
            if _h.startswith('- conjurer/enchanter/evoker/ritualist') or _h.startswith('- shoot javelin cost') or 'seeker bolts' in _h and _h.startswith('- new gfx'):
                continue
            if _h.startswith('- hurl skull') or _h.startswith('- shoot black javelin'):
                _rng += _items(_blk)
            else:
                _main += _items(_blk)
        _its = _ab4['items']
        _ri = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Ranged Attacks')
        _si = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Status Effects'), len(_its))
        while _si > 0 and _its[_si - 1]['t'] == 'gap': _si -= 1
        _its[_si:_si] = _rng
        _ins = _ri
        while _ins > 0 and _its[_ins - 1]['t'] == 'gap': _ins -= 1
        _its[_ins:_ins] = _main
    # Units: Phoenix into the Level 3 section; other 1.37.420 unit entries stay changelog-only
    _un4 = _cat('Units')
    if _un4:
        _its = _un4['items']
        _l3 = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'].lower().startswith('general level 3'))
        _e3 = _l3 + 1
        while _e3 < len(_its) and _its[_e3]['t'] == 'p': _e3 += 1
        for _blk in _blocks(_secs.get('Units', [])):
            if _blk[0][1].lower().startswith('- phoenix added'):
                _its[_e3:_e3] = _items(_blk)
    # Structures: merged into the existing list; the Rebuild City entry is updated in place
    _st4 = _cat('Economy & Structures')
    if _st4:
        _its = _st4['items']
        for _it in _its:
            if _it['x'].startswith('- Rebuild City costs'):
                _it['x'] = '- Rebuild City costs 25/50/100/250 gold depending on city size and takes one turn per city hex.'
        _add = []
        for _blk in _blocks(_secs.get('Structures', [])):
            if _blk[0][1].lower().startswith('- rebuilding cities'): continue
            _add += _items(_blk)
        while _its and _its[-1]['t'] == 'gap': _its.pop()
        _its.extend(_add)
    # Miscellaneous: other changes + bug fixes merged above the Items sub-section; Map Playlist dropped
    _mi4 = _cat('Miscellaneous')
    if _mi4:
        _its = _mi4['items']
        _add = []
        for _sec in ('Miscellaneous', 'Bug Fixes'):
            for _blk in _blocks(_secs.get(_sec, [])): _add += _items(_blk)
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
        _its[_ii:_ii] = _add
    print('1.37.420 general distribution: sections', [(k, len(v)) for k, v in _secs.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.420 general distribution failed:', _e)
# ---- 1.37.422: Leaders -> Leaders & Heroes, Miscellaneous -> Miscellaneous (above Items). User 10/22: the
# Spells/Units balance tweaks and the Bug Fixes stay changelog-only. ----
try:
    _cl = open('X/Documentation/changelogs.txt', 'rb').read().decode('cp1252', 'replace').split(chr(10))
    _cl = [l.rstrip() for l in _cl]
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.422'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _EMO = re.compile(r'<:[A-Za-z0-9_~]+:\d+>|:[A-Za-z0-9_~]+:')
    _s22 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s22[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s22[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    _lh = next((c for c in generalcats if c['name'] == 'Leaders & Heroes'), None)
    if _lh and _s22.get('Leaders'):
        while _lh['items'] and _lh['items'][-1]['t'] == 'gap': _lh['items'].pop()
        _lh['items'].extend(_s22['Leaders'])
    _mi5 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    if _mi5 and _s22.get('Miscellaneous'):
        _its = _mi5['items']
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
        _its[_ii:_ii] = _s22['Miscellaneous']
    print('1.37.422 general distribution: sections', [(k, len(v)) for k, v in _s22.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.422 general distribution failed:', _e)
# ---- 1.37.423: Miscellaneous -> Miscellaneous (above Items), as 422.  Bug Fixes stay changelog-only (422 precedent). ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.423'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s23 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s23[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s23[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    _mi6 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    if _mi6 and _s23.get('Miscellaneous'):
        _its = _mi6['items']
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
        _its[_ii:_ii] = _s23['Miscellaneous']
    print('1.37.423 general distribution: sections', [(k, len(v)) for k, v in _s23.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.423 general distribution failed:', _e)
# ---- 1.37.424: changelog-only (user 10/24: the auto-updater line stays out of General Changes). ----
# ---- 1.37.425: Miscellaneous -> Miscellaneous (above Items), as 423.  Spells / Abilities / Bug Fixes stay changelog-only. ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.425'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s25 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s25[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s25[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    _mi7 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    if _mi7 and _s25.get('Miscellaneous'):
        _its = _mi7['items']
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
        _its[_ii:_ii] = _s25['Miscellaneous']
    print('1.37.425 general distribution: sections', [(k, len(v)) for k, v in _s25.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.425 general distribution failed:', _e)
# ---- 1.37.431: Miscellaneous (autosave entry ONLY) -> Miscellaneous (above Items), as 425; Abilities (Construct underground roads) -> Economy & Structures after the bridge block.  Bug Fixes stay changelog-only. ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.431'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s31 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s31[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s31[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    # user 11/04: only the autosave entry (and its sub-lines) goes to General Changes - AoWDevX / Auto-Updater stay changelog-only
    _keep31, _on31 = [], False
    for _x in _s31.get('Miscellaneous', []):
        if _x.get('lvl', 0) == 0: _on31 = _x['x'].startswith('- Autosave expanded')
        if _on31: _keep31.append(_x)
    _s31['Miscellaneous'] = _keep31
    _mi31 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    if _mi31 and _s31.get('Miscellaneous'):
        _its = _mi31['items']
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
        _its[_ii:_ii] = _s31['Miscellaneous']
    # user 11/04: the Construct (underground roads) line goes to General Changes right after the bridge-building block
    _ec31 = next((c for c in generalcats if c['name'] == 'Economy & Structures'), None)
    if _ec31 and _s31.get('Abilities'):
        _its = _ec31['items']
        _bi = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- Bridges can now be constructed')), None)
        if _bi is not None:
            _bj = _bi + 1
            while _bj < len(_its) and _its[_bj]['t'] == 'p' and _its[_bj].get('lvl', 0) > 0: _bj += 1
            _its[_bj:_bj] = [dict(_x) for _x in _s31['Abilities'] if 'Construct' in _x['x']]
    print('1.37.431 general distribution: sections', [(k, len(v)) for k, v in _s31.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.431 general distribution failed:', _e)
# ---- 1.37.427 + 1.37.428 + 1.37.429 + 1.37.430: Bug Fixes only -> changelog-only (422 precedent). ----
# ---- 1.37.426: Items -> Miscellaneous 'Items' sub-section, Abilities -> Hurl Skull cost updated in place (Ranged
# Attacks), Structures -> Economy & Structures, Miscellaneous -> Miscellaneous (above Items).  Bug Fixes stay
# changelog-only (422 precedent). ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.426'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s26 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s26[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s26[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    _mi8 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    if _mi8:
        _its = _mi8['items']
        if _s26.get('Miscellaneous'):
            _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
            while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
            _its[_ii:_ii] = _s26['Miscellaneous']
        if _s26.get('Items'):
            _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), None)
            if _ii is None:
                _its += [dict(t='gap', x='', lvl=0), dict(t='h', x='Items')]; _ie = len(_its)
            else:
                _ie = _ii + 1
                while _ie < len(_its) and _its[_ie]['t'] == 'p': _ie += 1
            _its[_ie:_ie] = _s26['Items']
    _st8 = next((c for c in generalcats if c['name'] == 'Economy & Structures'), None)
    if _st8 and _s26.get('Structures'):
        _its = _st8['items']
        while _its and _its[-1]['t'] == 'gap': _its.pop()
        _its.extend(_s26['Structures'])
    _ab8 = next((c for c in generalcats if c['name'] == 'Abilities'), None)
    if _ab8:
        _its = _ab8['items']
        for _q, _it in enumerate(_its):
            if _it['t'] == 'p' and _it['x'].startswith('- Hurl Skull added'):
                for _r in _its[_q + 1:_q + 4]:
                    if _r['t'] == 'p' and _r['x'].startswith('- Level up cost:'):
                        _r['x'] = '- Level up cost: 25'
    print('1.37.426 general distribution: sections', [(k, len(v)) for k, v in _s26.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.426 general distribution failed:', _e)
# ---- 1.37.432 (user 11/07: "distribute/update throughout the general changes sections. make sure to add to unit
# section too"): Units (Cyclops) -> Units 'General Level 4 changes' after the Ent line, in the list's own wording;
# Spells (summon dispel resistance) -> Magic: the "3 to 7" line updated in place (426 Hurl Skull precedent);
# Miscellaneous: teleporters + Sky/Clear Sky/Chasm transitions -> under 'New map levels added' (after the sky combat
# maps line), the AoWDevX list -> appended into the 'AoWDevX mapmaking QoL improvements' block one level deeper.
# Map Playlist stays changelog-only (General Changes has no per-map list; 420 precedent). ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.432'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s32 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s32[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s32[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    # Units: General Level 4 changes, after the Ent line (fallback: end of the level-4 run of entries)
    _un32 = next((c for c in generalcats if c['name'] == 'Units'), None)
    if _un32 and _s32.get('Units'):
        _its = _un32['items']
        _l4 = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'].lower().startswith('general level 4'))
        _ent = next((_q for _q in range(_l4 + 1, len(_its)) if _its[_q]['t'] == 'p' and _its[_q]['x'].startswith('- Ent added')), None)
        if _ent is None:
            _ent = _l4
            while _ent + 1 < len(_its) and _its[_ent + 1]['t'] == 'p': _ent += 1
        _its[_ent + 1:_ent + 1] = [dict(t='p', x='- Cyclops added (exploration sites, not produceable)', lvl=0)]
    # Magic: summoned-unit dispel resistance updated in place
    _mg32 = next((c for c in generalcats if c['name'] == 'Magic'), None)
    if _mg32:
        _hit = [_it for _it in _mg32['items'] if _it['t'] == 'p' and _it['x'].startswith('- Summoned unit resistance to Dispel Magic')]
        assert len(_hit) == 1, len(_hit)
        _hit[0]['x'] = '- Summoned unit resistance to Dispel Magic (being unsummoned) is (unit level X 2) + 1 for each medal (was 3 in vanilla).'
    # Miscellaneous
    _mi32 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    _ms = _s32.get('Miscellaneous', [])
    if _mi32 and _ms:
        _its = _mi32['items']
        _tele = [dict(_x, lvl=1) for _x in _ms if _x['lvl'] == 0 and ('teleporters added' in _x['x'] or 'terrain transitions' in _x['x'])]
        _dev, _on = [], False
        for _x in _ms:
            if _x['lvl'] == 0: _on = _x['x'].startswith('- AoWDevX improvements'); continue
            if _on: _dev.append(dict(_x, lvl=min(_x['lvl'] + 0, 3)))
        _sk = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- New combat maps for sky'))
        _its[_sk + 1:_sk + 1] = _tele
        _db = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- AoWDevX mapmaking QoL improvements'))
        _de = _db + 1
        while _de < len(_its) and _its[_de]['t'] == 'p' and _its[_de].get('lvl', 0) > 0: _de += 1
        _its[_de:_de] = _dev
    print('1.37.432 general distribution: sections', [(k, len(v)) for k, v in _s32.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.432 general distribution failed:', _e)
# ---- 1.37.433: Spells (independent heroes cast level 1 Cosmos) -> Magic (appended); Miscellaneous: Error Log entry
# (+ sub-lines) -> Miscellaneous above Items (425 pattern), the two Sky lines -> under 'New map levels added' after
# the 432 teleporter/transition lines, the AoWDevX list -> appended into the 'AoWDevX mapmaking QoL improvements'
# block.  Units (Hydra: unit card is generated from the game data), title logo and Bug Fixes stay changelog-only. ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.433'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s33 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s33[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s33[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    _mg33 = next((c for c in generalcats if c['name'] == 'Magic'), None)
    if _mg33 and _s33.get('Spells'):
        _its = _mg33['items']
        _tail = []
        while _its and _its[-1]['t'] == 'gap': _tail.append(_its.pop())
        _its.extend(dict(_x) for _x in _s33['Spells'])
        _its.extend(reversed(_tail))
    _mi33 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    _ms = _s33.get('Miscellaneous', [])
    if _mi33 and _ms:
        _its = _mi33['items']
        _err, _dev, _mode = [], [], None
        for _x in _ms:
            if _x['lvl'] == 0:
                _mode = 'err' if _x['x'].startswith('- Error Log') else 'dev' if _x['x'].startswith('- AoWDevX improvements') else None
                if _mode == 'err': _err.append(dict(_x))
                continue
            if _mode == 'err': _err.append(dict(_x))
            elif _mode == 'dev': _dev.append(dict(_x))
        _sky = [dict(_x, lvl=1) for _x in _ms if _x['lvl'] == 0 and _x['x'].startswith('- Sky terrain')]
        _sk = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- Improved terrain transitions for Sky')), None)
        if _sk is None:
            _sk = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- New combat maps for sky'))
        _its[_sk + 1:_sk + 1] = _sky
        _db = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- AoWDevX mapmaking QoL improvements'))
        _de = _db + 1
        while _de < len(_its) and _its[_de]['t'] == 'p' and _its[_de].get('lvl', 0) > 0: _de += 1
        _its[_de:_de] = _dev
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        while _ii > 0 and _its[_ii - 1]['t'] == 'gap': _ii -= 1
        _its[_ii:_ii] = _err
        print('1.37.433: Error Log lines', len(_err), 'sky', len(_sky), 'AoWDevX', len(_dev))
    print('1.37.433 general distribution: sections', [(k, len(v)) for k, v in _s33.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.433 general distribution failed:', _e)
# ---- 1.37.434: Structures (own-race migration) -> Economy & Structures (appended); Spells -> Magic (appended);
# Abilities: Hurl Skull level-up cost updated in place (25 -> 20) + the AOE half-damage line added under it;
# Items (surrender drops items) -> Miscellaneous 'Items' sub-section end; Miscellaneous lvl-0 lines -> Miscellaneous
# above Items, the AoWDevX list -> 'AoWDevX mapmaking QoL improvements' block; the 433 Error Log entry is updated in
# place (X/Bug Report folder) and gains the two 'Expanded error log system' sub-lines.  Units and the other Bug Fixes
# stay changelog-only. ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.434'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s34 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s34[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s34[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    def _app34(_cat, _new):
        _c = next((c for c in generalcats if c['name'] == _cat), None)
        if not (_c and _new): return
        _its = _c['items']; _tail = []
        while _its and _its[-1]['t'] == 'gap': _tail.append(_its.pop())
        _its.extend(dict(_x) for _x in _new); _its.extend(reversed(_tail))
    _app34('Economy & Structures', _s34.get('Structures'))
    _app34('Magic', _s34.get('Spells'))
    _ab34 = next((c for c in generalcats if c['name'] == 'Abilities'), None)
    if _ab34:
        _its = _ab34['items']
        _q = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- Hurl Skull added'))
        _e = _q + 1
        while _e < len(_its) and _its[_e]['t'] == 'p' and _its[_e].get('lvl', 0) > _its[_q].get('lvl', 0):
            if _its[_e]['x'].startswith('- Level up cost:'): _its[_e]['x'] = '- Level up cost: 20'
            _e += 1
        _its[_e:_e] = [dict(t='p', x='- Deals full damage on target hex only, and AOE hexes deal -50% damage', lvl=_its[_q].get('lvl', 0) + 1)]
    _mi34 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    if _mi34:
        _its = _mi34['items']
        _ms = _s34.get('Miscellaneous', [])
        _gen, _dev, _mode = [], [], None
        for _x in _ms:
            if _x['lvl'] == 0:
                _mode = 'dev' if _x['x'].startswith('- AoWDevX improvements') else None
                if _mode is None: _gen.append(dict(_x))
                continue
            if _mode == 'dev': _dev.append(dict(_x))
        _db = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- AoWDevX mapmaking QoL improvements'))
        _de = _db + 1
        while _de < len(_its) and _its[_de]['t'] == 'p' and _its[_de].get('lvl', 0) > 0: _de += 1
        _its[_de:_de] = _dev
        _eq = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- Error Log text file added'))
        _its[_eq]['x'] = '- Error Log text file added to X/Bug Report folder'
        _ee = _eq + 1
        while _ee < len(_its) and _its[_ee]['t'] == 'p' and _its[_ee].get('lvl', 0) > 0: _ee += 1
        _bf = _s34.get('Bug Fixes', [])
        _xq = next((_q for _q, _x in enumerate(_bf) if _x['x'].startswith('- Expanded error log system')), None)
        _sub = []
        if _xq is not None:
            for _x in _bf[_xq + 1:]:
                if _x['lvl'] == 0: break
                _sub.append(dict(_x))
        _its[_ee:_ee] = _sub
        _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), len(_its))
        _ig = _ii
        while _ig > 0 and _its[_ig - 1]['t'] == 'gap': _ig -= 1
        _its[_ig:_ig] = _gen
        if _s34.get('Items'):
            _ii = next((_q for _q, _it in enumerate(_its) if _it['t'] == 'h' and _it['x'] == 'Items'), None)
            if _ii is None:
                _its += [dict(t='gap', x='', lvl=0), dict(t='h', x='Items')]; _ie = len(_its)
            else:
                _ie = _ii + 1
                while _ie < len(_its) and _its[_ie]['t'] == 'p': _ie += 1
            _its[_ie:_ie] = [dict(_x) for _x in _s34['Items']]
        print('1.37.434: misc', len(_gen), 'AoWDevX', len(_dev), 'error-log sub-lines', len(_sub))
    for _c in generalcats:
        for _it in _c['items']:
            if _it['t'] == 'p' and re.search(r'\bSlow\b|Depths of Plenty|Angel Wings|Hurl Skull|Level up cost: 2|Error Log|urrender|migrat', _it['x']):
                print('   434 check [%s] lvl%d %s' % (_c['name'], _it.get('lvl', 0), _it['x'][:150]))
    print('1.37.434 general distribution: sections', [(k, len(v)) for k, v in _s34.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.434 general distribution failed:', _e)
# ---- 1.37.435 (2026-11-21): Bug Fixes only (Hurl Skull cost data fix, game state reports, manual restore) -> changelog-only,
# like the 434 OoS / Connection Lost handlers; General Changes already says 'Level up cost: 20'. ----
# ---- 1.37.436 (2026-11-21): Bug Fixes only (MP tactical-combat lock-up, patch_combat_remote_tc_purge_v1) -> changelog-only. ----
# ---- 1.37.437 (2026-11-22): Miscellaneous = one AoWDevX list (Map Level Vision tab, fog preview per player, City
# Names tab) -> appended into the 'AoWDevX mapmaking QoL improvements' block (434 pattern); Bug Fixes changelog-only. ----
try:
    _st = next(i for i, l in enumerate(_cl) if l.strip().startswith('Version 1.37.437'))
    _en = next((i for i in range(_st + 1, len(_cl))
                if re.match(r'^[A-Z][a-z]+ \d+(st|nd|rd|th),? \d{4}:?$', _cl[i].strip())), len(_cl))
    _s37 = collections.OrderedDict(); _cur = None
    for _l in _cl[_st + 1:_en]:
        _t = _l.strip()
        if not _t: continue
        if not _t.startswith('.'):
            _cur = _EMO.sub('', _t).replace('*', '').strip().rstrip(':').strip()
            _s37[_cur] = []; continue
        _rest = _t[1:]; _nsp = len(_rest) - len(_rest.lstrip())
        _lv = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
        _x = _EMO.sub('', _rest.strip()).replace('*', '').strip()
        if _cur is not None and _x: _s37[_cur].append(dict(t='p', x=_x if _x.startswith('-') else '- ' + _x, lvl=_lv))
    _mi37 = next((c for c in generalcats if c['name'] == 'Miscellaneous'), None)
    _dev = []; _mode = None
    for _x in _s37.get('Miscellaneous', []):
        if _x['lvl'] == 0:
            _mode = 'dev' if _x['x'].startswith('- AoWDevX improvements') else None
            continue
        if _mode == 'dev': _dev.append(dict(_x))
    if _mi37 and _dev:
        _its = _mi37['items']
        _db = next(_q for _q, _it in enumerate(_its) if _it['t'] == 'p' and _it['x'].startswith('- AoWDevX mapmaking QoL improvements'))
        _de = _db + 1
        while _de < len(_its) and _its[_de]['t'] == 'p' and _its[_de].get('lvl', 0) > 0: _de += 1
        _its[_de:_de] = _dev
    print('1.37.437: AoWDevX lines', len(_dev), 'sections', [(k, len(v)) for k, v in _s37.items()])
except Exception as _e:
    import traceback; traceback.print_exc()
    print('1.37.437 general distribution failed:', _e)
# ---- 1.37.438 (2026-11-26): Bug Fixes (stale spell id on ranged attacks, terrain spells vs Sky/Chasm, Thousand
# Threads single roll) + Map Playlist (Shattered Peaks) -> changelog-only (435/436 and 420 Map Playlist precedents). ----
print('general categories:', [(c['name'], len(c['items'])) for c in generalcats])

# ---- per-race terrain morale modifiers + synopsis (doc: 12 tables in race order) ----
RACE_ORDER12 = ['Human','Azrac','Lizardman','Frostling','Elf','Halfling','Dwarf','Highmen','Dark Elf','Orc','Goblin','Undead']
raceinfo = {}
try:
    _ti = 0
    for _k in root.iter(W + 'tbl'):
        _r = rows(_k)
        if not (_r and cells(_r[0]) and 'Hostile Terrain Morale Modifiers' in txt(cells(_r[0])[0])[:50]): continue
        _dis = []; _hat = []; _syn = []; _mode = 'terr'
        for _tr in _r[1:]:
            _cs = cells(_tr)
            _t0 = re.sub(r'\s+', ' ', txt(_cs[0])).strip() if _cs else ''
            if _t0 == 'Synopsis': _mode = 'syn'; continue
            if _mode == 'terr':
                if 'Disliked' in _t0: continue
                if _t0: _dis.append(_t0)
                if len(_cs) > 1:
                    _t1 = re.sub(r'\s+', ' ', txt(_cs[1])).strip()
                    if _t1: _hat.append(_t1)
            else:
                _sx = txtbr(_tr)
                if _sx: _syn.append(_sx)
        if _ti < len(RACE_ORDER12):
            raceinfo[RACE_ORDER12[_ti]] = dict(disliked=_dis, hated=_hat, synopsis=_syn)
        _ti += 1
    print('race terrain/synopsis tables: %d' % _ti)
except Exception as _e:
    print('raceinfo failed:', _e)

# ---- Relations visuals: colored race matrix (doc table 1) + alignment image ----
rel_matrix = None; rel_img = ''
try:
    def _fill(tc2):
        sh2 = tc2.find(W + 'tcPr/' + W + 'shd')
        return (sh2.get(W + 'fill') or '') if sh2 is not None else ''
    _tb1 = next(k2 for k2 in list(body) if k2.tag == W + 'tbl')
    _rows = []
    for _tr in rows(_tb1):
        _cs = cells(_tr)
        _rows.append([dict(x=re.sub(r'\s+', ' ', txt(_c)).strip(), c=_fill(_c)) for _c in _cs])
    rel_matrix = _rows
    for _k in list(body):
        if _k.tag == W + 'p' and 'Alignment relations' in txt(_k):
            for _b in _k.iter(A + 'blip'):
                _tg = relmap.get(_b.get(R + 'embed'), '')
                if _tg:
                    _raw = z.read('word/' + _tg)
                    _mime = 'image/png' if _tg.endswith('.png') else 'image/gif' if _tg.endswith('.gif') else 'image/jpeg'
                    rel_img = 'data:%s;base64,' % _mime + base64.b64encode(_raw).decode()
            break
    print('relations matrix rows: %d | alignment img: %s' % (len(rel_matrix or []), bool(rel_img)))
except Exception as _e:
    print('relations visuals failed:', _e)

# ---- Abilities tab: desc+skill cost from Release/Ability.pfs (record key = ability id + 10),
# availability computed from unit ability data, ranged ATK/DMG/projectiles from the doc's Ranged Attacks lines ----
abilities = []
try:
    _ad = open('Release/Ability.pfs', 'rb').read()
    def _ab_table(dd, p):
        b = dd[p]; p += 1; nd = 0
        if b & 0x80: nd = struct.unpack_from('<I', dd, p)[0]; p += 4
        nb = b & 0x7F; fields = {}
        for _ in range(nb): fields[dd[p]] = dd[p+1]; p += 2
        for _ in range(nd):
            t, o = struct.unpack_from('<II', dd, p); fields[t] = o; p += 8
        return fields, p
    _aroot, _abase = _ab_table(_ad, 7)
    _adesc = {}; _acost = {}; _ahero = {}
    for _cid, _off in _aroot.items():
        _aid = _cid - 10
        _f, _b1 = _ab_table(_ad, _abase + _off)
        if 5 in _f:
            _ln = struct.unpack_from('<I', _ad, _b1 + _f[5])[0]
            if _ln < 4000:
                _t = _ad[_b1+_f[5]+4:_b1+_f[5]+4+_ln].decode('cp1252', 'replace')
                _adesc[_aid] = _t.replace('\r\n', '\n').strip()
        if 6 in _f:
            _acost[_aid] = struct.unpack_from('<I', _ad, _b1 + _f[6])[0]
        if 9 in _f:
            _v9 = struct.unpack_from('<H', _ad, _b1 + _f[9])[0]
            # TAbilitySelectionTypes set: bit7=astCustomizeLeader, bit8=astHeroUpgrade
            _ahero[_aid] = bool(_v9 & 0x80) and bool(_v9 & 0x100)
    # availability: which units carry each ability (base / Silver / Gold), from the game unit records
    _avail = {}
    _av_seen = set()
    for _u in game:
        _f2 = (_u['race'] + ' ' + _u['name']).strip()
        if excluded(_u, _f2) or normn(_f2) in _av_seen: continue
        _av_seen.add(normn(_f2))
        for _tk, _lbl in (('base', 'base'), ('silver', 'Silver'), ('gold', 'Gold'), ('legend', 'Legendary')):
            _o = _u.get(_tk)
            if _o:
                for _i in _o['ids']:
                    _avail.setdefault(_i, {'base': [], 'Silver': [], 'Gold': [], 'Legendary': []})[_lbl].append(_f2)
    # ranged stats from the doc (Abilities category > Ranged Attacks section)
    _rstats = {}
    _abcat = next((c for c in generalcats if c['name'] == 'Abilities'), None)
    if _abcat:
        _in_ra = False; _pend = None
        for _it in _abcat['items']:
            if _it.get('t') == 'h':
                _in_ra = _it['x'] == 'Ranged Attacks'; continue
            if not _in_ra: continue
            _x = _it['x']
            _m = re.search(r'-\s*(.+?) changed to (?:(.+?) damage, )?(\d+) ATK / (\d+) DMG / (\d+) projectiles?', _x)
            if _m:
                _rstats[_m.group(1).strip()] = ('%s ATK / %s DMG / %s projectile%s' % (
                    _m.group(3), _m.group(4), _m.group(5), 's' if _m.group(5) != '1' else ''),
                    (_m.group(2) or '').strip())
                _pend = None; continue
            if re.match(r'-\s*Cosmic Breath added', _x): _pend = 'Cosmic Breath'; continue
            if 'Seeker Bolts' in _x and 'changed to' in _x: _pend = 'Seeker Bolts'; continue
            _m = re.match(r'(\d+) ATK / (\d+) DMG / (\d+) projectiles?\.?\s*\n?(.*)', _x)
            if _m and _pend:
                _rstats[_pend] = ('%s ATK / %s DMG / %s projectile%s' % (
                    _m.group(1), _m.group(2), _m.group(3), 's' if _m.group(3) != '1' else ''),
                    _m.group(4).replace('Damage', '').strip())
                _pend = None
    for _bn in ('Fire Breath', 'Cold Breath', 'Black Breath', 'Divine Breath', 'Gas Breath'):
        if 'Breath Attacks' in _rstats: _rstats.setdefault(_bn, _rstats['Breath Attacks'])
    _rstats.pop('Breath Attacks', None)
    # 1.37.420 ranged abilities (not in the doc): stats as registered by patch_bxl_ranged_abilities
    _rstats.setdefault('Hurl Skull', ('3 ATK / 8 DMG / 1 projectile (explodes: Fire Ball-sized area)', 'Physical, Fire, Death, Walls'))
    _rstats.setdefault('Shoot Black Javelin', ('8 ATK / 6 DMG / 1 projectile', 'Physical, Death'))
    # Fire Musket / Fire Cannon (not in the doc): read live from their CreateHurl registration in AoWEPACK.dll
    # (`push DMG; push projectiles; push range; ... mov cl, ATK`), fallback = the 10/23 values
    for _gn, _gva, _gcl, _gdef, _gtype in (('Fire Musket', 0x5576F5EF, 0x5576F619, (5, 7, 1), 'Physical'),
                                           ('Fire Cannon', 0x5576F62E, 0x5576F658, (5, 8, 1), 'Physical, Walls')):
        _gv = _gdef
        try:
            _gd = open('AoWEPACK.dll', 'rb').read()
            _go, _gc = _gva - 0x55700C00, _gcl - 0x55700C00
            if _gd[_go] == 0x6A and _gd[_go + 2] == 0x6A and _gd[_gc] == 0xB1:
                _gv = (_gd[_gc + 1], _gd[_go + 1], _gd[_go + 3])
        except Exception as _e3:
            print('gunpowder stat read failed:', _e3)
        _rstats.setdefault(_gn, ('%d ATK / %d DMG / %d projectile%s' % (_gv + ('s' if _gv[2] != 1 else '',)), _gtype))
    # strike status-effect ATK values, read live from AoWEPACK.dll (ExecuteDamageEffectsRole
    # push-pairs [6a type 6a atk e8 ...] + Entangle Strike roll `mov eax,7` in TStrikeCA.Generate)
    _sstat = {}
    try:
        _dll = open('AoWEPACK.dll', 'rb').read()
        _SS_SITES = {0x0E: (0x55781C30, 'Burning'), 0x0F: (0x55781DE6, 'Frozen'),
                     0x10: (0x55781C90, 'Stunned'), 0x11: (0x55781CE2, 'Poisoned'),
                     0x12: (0x55781D34, 'Cursed'), 0x13: (0x55781D86, 'Vertigo')}
        for _sid, (_sva, _snm) in _SS_SITES.items():
            _so = _sva - 0x55700C00
            if _dll[_so] == 0x6A and _dll[_so+2] == 0x6A:
                _sstat[_sid] = (_snm, _dll[_so+3])
        _eo = 0x5576694D - 0x55700C00
        if _dll[_eo] == 0xB8:
            _sstat[0x77] = ('Entangled', _dll[_eo+1])
    except Exception as _e2:
        print('strike status read failed:', _e2)
    print('strike status values:', {hex(k): v for k, v in sorted(_sstat.items())})
    ABNAME_OVR = {0x1E: 'Cosmic Breath'}
    AB_SKIP = {0x9B}          # summoned-upkeep marker, not a real ability
    ABGROUPS = [
        ('Movement', [0x00, 0x01, 0x02, 0x17, 0x3B, 0x03, 0x04, 0x05, 0x2A, 0x24, 0x42]),
        ('Melee & Combat Skills', [0x15, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x77,
                                   0x6F, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x38, 0x70, 0x92, 0x93, 0x33, 0x41]),
        ('Ranged Attacks', [0x16, 0x20, 0x19, 0x18, 0x3D, 0x3E, 0x39, 0x3A, 0x78, 0x79, 0x7A, 0x7B,
                            0x7C, 0x1F, 0x1E, 0x2C, 0x2D, 0x37, 0x56, 0x57, 0x58, 0x59, 0x5A,
                            0xCC, 0xCD]),   # 1.37.420: Hurl Skull, Shoot Black Javelin
        ('Touch & Mind', [0x1B, 0x28, 0x1C, 0x1D, 0x94, 0x23, 0x26, 0x6A, 0xC9]),   # + 1.37.420 Tame Animal
        ('Immunities', [0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x43]),
        ('Protections', [0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D]),
        ('Weaknesses', [0x51, 0x52, 0x53, 0x54, 0x55, 0x85, 0x86, 0x87]),
        ('Vision & Concealment', [0x40, 0x27, 0x29, 0x36, 0x91, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F, 0x90, 0xAA]),
        ('Paths & Trails', [0x45, 0x44, 0x6D, 0x9F, 0x1A, 0x2B]),
        ('Support & Special', [0x2E, 0x25, 0x2F, 0x31, 0x34, 0x3C, 0x7D, 0x32, 0x3F,
                               0xAC, 0xAD, 0xAE, 0xAF, 0xCB]),   # + AoWx caster proficiencies (leader/hero, I-III) + 1.37.420 Channeler I-III
    ]
    for _gt, _ids in ABGROUPS:
        _ids = sorted(_ids, key=lambda x: (ABNAME_OVR.get(x) or aname(x)).replace('', "'").lower())
        for _i in _ids:
            _nm = ABNAME_OVR.get(_i) or aname(_i)
            if _nm.startswith('Unknown'): continue
            _nm = _nm.replace('\x92', "'")
            _av = _avail.get(_i, {'base': [], 'Silver': [], 'Gold': []})
            _rs = _rstats.get(_nm, ('', ''))
            abilities.append(dict(id=_i, name=_nm, group=_gt,
                                  desc=_adesc.get(_i, ''),
                                  cost=_acost.get(_i),
                                  ranged=_rs[0], dtypes=_rs[1],
                                  hero=('Yes' if _ahero.get(_i) else 'No'),
                                  status=('%s: %d ATK' % _sstat[_i] if _i in _sstat else ''),
                                  avail=_av))
    print('abilities tab: %d abilities, %d with ranged stats, %d with cost' % (
        len(abilities), sum(1 for a in abilities if a['ranged']), sum(1 for a in abilities if a['cost'] is not None)))
except Exception as _e:
    import traceback; traceback.print_exc()
    print('abilities tab failed:', _e)

# ---- Changelogs tab: X/Documentation/changelogs.txt (discord-flavored text) ----
changelog = []
try:
    _clt = open('X/Documentation/changelogs.txt', 'rb').read().decode('cp1252', 'replace')
    _cll = [l.rstrip() for l in _clt.split(chr(10))]
    _DATE_RE = re.compile(r'^(?:[A-Z][a-z]+ ' + chr(92) + 'd+(?:st|nd|rd|th),? ' + chr(92) + 'd{4}:?|~[0-9' + chr(92) + '-]+)$')
    _EMOJI_RE = re.compile(r'<:[A-Za-z0-9_~]+:\d+>|:[A-Za-z0-9_~]+:')  # discord <:name:id> + :name:
    _didx = [i for i, l in enumerate(_cll) if _DATE_RE.match(l.strip())]
    for _bi, _di in enumerate(_didx):
        _bend = _didx[_bi+1] if _bi+1 < len(_didx) else len(_cll)
        _date = _cll[_di].strip().rstrip(':')
        _j5 = _di + 1
        while _j5 < _bend and not _cll[_j5].strip(): _j5 += 1
        _btitle = _cll[_j5].strip().rstrip(':') if _j5 < _bend else ''
        _its = []
        for _l5 in _cll[_j5+1:_bend]:
            _st = _l5.strip()
            if not _st:
                if _its and _its[-1]['t'] != 'gap': _its.append(dict(t='gap'))
                continue
            _lvl = 0
            if _st.startswith('.'):
                _rest = _st[1:]
                _nsp = len(_rest) - len(_rest.lstrip())
                _lvl = 0 if _nsp <= 11 else 1 if _nsp <= 17 else 2 if _nsp <= 22 else 3
                _st = _rest.strip()
            elif _st.startswith(chr(92)):
                _m5 = re.match('^' + chr(92) + chr(92) + '(-+)' + chr(92) + 's*(.*)$', _st)
                if _m5:
                    _lvl = min(len(_m5.group(1)) - 1, 3)
                    _st = '- ' + _m5.group(2)
            _st = _EMOJI_RE.sub('', _st).replace(chr(92), '').strip()
            if not _st: continue
            if not _st.startswith('-') and _st.endswith(':'):
                _its.append(dict(t='h', x=_st.rstrip(':').strip()))
                continue
            if _st.startswith('-'): _st = _st[1:].strip()
            if _st: _its.append(dict(t='p', x=_st, lvl=_lvl))
        while _its and _its[-1]['t'] == 'gap': _its.pop()
        while _its and _its[0]['t'] == 'gap': _its.pop(0)
        changelog.append(dict(date=_date, title=_btitle, items=_its))
    print('changelog: %d releases, %d lines' % (len(changelog), sum(len(b['items']) for b in changelog)))
except Exception as _e:
    import traceback; traceback.print_exc()
    print('changelog failed:', _e)

# ---- Modding AoWx + Community tabs (doc sections V & VI, with hyperlinks) ----
moddingpage = []; communitypage = []
try:
    def _esc5(t): return (t or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    _relmap_all = dict(re.findall(r'Id="(rId[0-9]+)"[^>]*Target="([^"]+)"',
                                  z.read('word/_rels/document.xml.rels').decode('utf-8', 'replace')))
    def _rich_para(k):
        parts = []
        def _walk5(e):
            for ch in e:
                if ch.tag == W + 'hyperlink':
                    _rid = ch.get(R + 'id'); _url = _relmap_all.get(_rid, '')
                    _t5 = txt(ch)
                    if _url.startswith('http'):
                        parts.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (_esc5(_url), _esc5(_t5)))
                    else:
                        parts.append(_esc5(_t5))
                elif ch.tag == W + 'r':
                    for rc in ch:
                        if rc.tag == W + 't': parts.append(_esc5(rc.text or ''))
                        elif rc.tag == W + 'br': parts.append('<br>')
                else:
                    _walk5(ch)
        _walk5(k)
        return ''.join(parts).strip()
    _kids5 = list(body)
    _iv = _vi = None
    for _i5, _k5 in enumerate(_kids5):
        if _k5.tag != W + 'p': continue
        _t6 = re.sub(r'[^A-Za-z ]', '', txt(_k5)).strip()
        if _t6 == 'V  Modding AoWx' or _t6 == 'V Modding AoWx': _iv = _i5
        if _t6 == 'VI  Community' or _t6 == 'VI Community': _vi = _i5
    for _dst, _rng in ((moddingpage, range(_iv+1, _vi)), (communitypage, range(_vi+1, len(_kids5)))):
        for _i5 in _rng:
            _k5 = _kids5[_i5]
            if _k5.tag != W + 'p': continue
            _plain = re.sub(r'[  ]+', ' ', txt(_k5)).strip()
            if not _plain: continue
            _bold = any(r.find(W + 'rPr') is not None and r.find(W + 'rPr').find(W + 'b') is not None
                        for r in _k5.findall(W + 'r'))
            _html5 = _rich_para(_k5)
            if not _html5: continue
            if _bold and len(_plain) < 50:
                _dst.append(dict(t='h', html=_esc5(_plain.rstrip(':'))))
            else:
                _dst.append(dict(t='p', html=_html5))
    if communitypage and communitypage[0].get('t') == 'h' and communitypage[0]['html'] == 'Community':
        communitypage.pop(0)
    # 1.37.407 (2026-09-01): modding suite tools below AoWDevX (not in the doc)
    try:
        _mi2 = next(i for i, it in enumerate(moddingpage)
                    if it.get('t') == 'h' and it.get('html', '').strip() == 'AoWDevX')
        while _mi2 + 1 < len(moddingpage) and moddingpage[_mi2 + 1].get('t') == 'p':
            _mi2 += 1
        moddingpage[_mi2 + 1:_mi2 + 1] = [
            dict(t='h', html='AoWx Modding Tools'),
            dict(t='p', html='The <a href="https://aow.heavengames.com/downloads/showfile.php?fileid=1276" target="_blank" rel="noopener">AoWx Modding Tools</a> are a separate download and can be launched from the Modding button in AoWSetup. Tools that are not installed appear greyed out in the launcher.'),
            dict(t='p', html='<b>AoWxGen</b> ' + chr(8212) + ' random map generator. Batch-generates RNG maps, fully customizable custom maps (size, levels, players, terrain inversion, landmass and terrain-style presets), and can convert images into playable maps (Image-to-Map).'),
            dict(t='p', html='<b>AoWxBard</b> ' + chr(8212) + ' custom music tool. Converts your own audio into the game' + chr(8217) + 's music format.'),
            dict(t='p', html='<b>AoWxImg</b> ' + chr(8212) + ' image library import/export tool (modernized ILBMaker). Automatically sets all parameters/settings when adding images to libraries, with image type templates (portrait, item, unit, etc) and no manual ' + chr(8220) + 'image resizing' + chr(8221) + ' required.'),
            dict(t='p', html='<b>AoWxInk</b> ' + chr(8212) + ' language/text editor (modernized MLDEdit). Multi-language auto-translation and typo search with an ' + chr(8220) + 'add to dictionary' + chr(8221) + ' option.'),
            dict(t='p', html='<b>AoWxQuest</b> ' + chr(8212) + ' campaign editor (modernized AoWCGE). Drag-and-drop campaign event placement on the map, extensive event view/hide filtering, flow chart view, book page image previews, typo search with red underlining, and a campaign validator (checks for errors, broken event links, etc).'),
        ]
    except StopIteration:
        pass
    print('modding page: %d items | community page: %d items' % (len(moddingpage), len(communitypage)))
except Exception as _e:
    import traceback; traceback.print_exc()
    print('modding/community failed:', _e)

data = dict(units=units, races=present, stat=STAT, icons=icons, overview=overview, general=general,
            moddingpage=moddingpage, communitypage=communitypage,
            changelog=changelog,
            abilities=abilities,
            generalcats=generalcats, relmatrix=rel_matrix, relimg=rel_img, raceinfo=raceinfo,
            overviewitems=overviewitems,
            spells=spells_out, spheres=SPHERE_LIST, sphicons=sphicons, raceicons=raceicons,
            title=titlep[0] if titlep else 'Age of Wonders X',
            version='Version 1.37.438', lastupdated='Last updated November 26th 2026', homeicons=homeicons, gcicons=gcicons,
            nunits=len(units), source='game')

PAGE = open(os.path.join(HERE,'template.html'), encoding='utf-8').read()
try:
    _fnt = base64.b64encode(open(os.path.join(HERE, 'NeueHammerUnziale.otf'), 'rb').read()).decode()
    PAGE = PAGE.replace('__TITLEFONT__', _fnt)
    _bl = base64.b64encode(open(os.path.join(HERE, 'brand_icon.png'), 'rb').read()).decode()
    PAGE = PAGE.replace('__BRANDICON__', _bl)
except Exception as _e:
    print('title font embed failed:', _e)
html = PAGE.replace('__DATA__', json.dumps(data).replace('</', '<\\/'))
open(OUT, 'w', encoding='utf-8').write(html)
print('WROTE', OUT, '(%d KB)' % (len(html.encode()) // 1024))
print('units:%d  portraits:%d  units-with-desc:%d' % (
    len(units), sum(1 for u in units if u['img']), sum(1 for u in units if u['desc'])))
print('stat-sets differing from doc: %d' % ndiff)
for n in diffs[:25]: print('   *', n)
print('units not positioned by doc (fell back to race/Other): %d' % len(nogroup))
for n in nogroup: print('   ?', n)
