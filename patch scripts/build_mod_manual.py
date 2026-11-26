# -*- coding: utf-8 -*-
"""
build_mod_manual.py — generate a navigable HTML manual for an Age of Wonders 1 mod,
straight from the game's own data files. No source code needed, works on any AoW1 install.

USAGE:  copy this script into your AoW game root (next to AoW.exe) and run:
            py build_mod_manual.py
        output: "Mod Manual.html" (self-contained, portraits embedded, open in any browser)

WHAT IT READS (all optional except Unitres — missing files just skip that section):
    Release/Unitres.pfs   units: race, name, stats, level, cost, description, ability tiers
    Release/Ability.pfs   abilities: description, hero level-up cost, hero availability
    Release/Spells.pfs    spells: description, casting/upkeep, research cost
    Release/Unitgfx.pfs   unit -> face ILB + index (portraits)
    Images/FACES/*.ILB    portrait pixel data (16bpp raw + row-encoded, both handled)

CUSTOMIZING (all optional, place next to this script):
    abil_names.json    {"14": "Fire Strike", ...}  override/extend ability id -> name
    spell_names.json   {"3": "Fireball", ...}      spell id -> name (game files store no names!)
    face_offset.json   {"FACES\\MYPACK.ILB": -1}   per-ILB portrait index correction (see notes .md)

See BUILD-YOUR-MOD-MANUAL.md for the full file-format documentation and gotchas.
Shared by the AoWx project (The Chosen One / Claude), 2026.
"""
import struct, re, os, io, json, base64

OUT = 'Mod Manual.html'
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- PFS / HSS parsing
def parse_table(d, p):
    """HSS property table: [ctrl][nd:u32 if ctrl&0x80][nb=ctrl&0x7F x (tag:u8,off:u8)][nd x (tag:u32,off:u32)]
    offsets are relative to the table END (the returned base)."""
    b = d[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', d, p)[0]; p += 4
    nb = b & 0x7F; fields = {}
    for _ in range(nb):
        fields[d[p]] = d[p+1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from('<II', d, p); fields[t] = o; p += 8
    return fields, p

def pfs_root(d):
    """Skip optional magic 0x2144DF1C + version '01 00 00', return root table + data base."""
    p = 4 if d[:4] == struct.pack('<I', 0x2144DF1C) else 0
    assert d[p:p+3] == b'\x01\x00\x00', 'not a PFS/HSS stream'
    return parse_table(d, p + 3)

def sstr(d, p):
    ln = d[p]; return d[p+1:p+1+ln].decode('cp1252', 'replace')

def lstr(d, p):
    ln = struct.unpack_from('<I', d, p)[0]
    if ln > 100000: return ''
    return d[p+4:p+4+ln].decode('cp1252', 'replace')

# ---------------------------------------------------------------- default ability names (VANILLA-ish ids)
# NOTE: some ids are RUNTIME-ASSIGNED by the engine at ability registration and can differ
# between mods (esp. custom/added abilities). Verify against your own mod; override via abil_names.json.
ABIL = {0:"Walking",1:"Flying",2:"Swimming",3:"Forestry",4:"Cave Crawling",5:"Mountaineering",
6:"Magic Immunity",7:"Fire Immunity",8:"Cold Immunity",9:"Lightning Immunity",10:"Poison Immunity",
11:"Death Immunity",12:"Holy Immunity",13:"Physical Immunity",14:"Fire Strike",15:"Cold Strike",
16:"Lightning Strike",17:"Poison Strike",18:"Death Strike",19:"Holy Strike",20:"Magic Strike",
21:"Strike",22:"Archery",23:"Sailing",24:"Hurl Boulder",25:"Hurl Stones",26:"Trail of Darkness",
27:"Web",28:"Dominate",29:"Seduce",30:"Flame Throwing",31:"Call Flames",32:"Marksmanship",
35:"Invoke Death",36:"Wall Climbing",37:"Bard's Skills",38:"Turn Undead",39:"Night Vision",
40:"Entangle",41:"True Seeing",42:"Tunnelling",43:"Ignition",44:"Fire Cannon",45:"Fire Musket",
46:"Leadership",47:"Healing",48:"Seduced",49:"Regeneration",50:"Transport",51:"Cause Fear",
52:"Spellcasting",54:"Invisibility",55:"Doom Gaze",56:"Hero Slaying",57:"Shoot Javelin",
58:"Seeker Bolts",59:"Floating",60:"Dispel Magic",61:"Poison Darts",62:"Venomous Spit",
63:"Monster",64:"Vision",65:"Self Destruct",66:"Pass Wall",67:"Fearless",68:"Path of Decay",
69:"Path of Life",70:"Death Protection",71:"Fire Protection",72:"Holy Protection",
73:"Poison Protection",74:"Lightning Protection",75:"Magic Protection",76:"Cold Protection",
77:"Physical Protection",86:"Fire Breath",87:"Cold Breath",88:"Black Breath",89:"Divine Breath",
90:"Gas Breath",106:"Possess",107:"Possessed",109:"Path of Frost",111:"Charge",
112:"Monster Slaying",113:"Parry",114:"Round Attack",115:"Extra Strike",116:"First Strike",
117:"Wall Crushing",118:"Life Stealing",119:"Entangle Strike",120:"Black Bolts",121:"Magic Bolts",
122:"Frost Bolts",123:"Lightning Bolts",124:"Holy Bolts",125:"Construct",126:"Cosmetic Surgery",
138:"Steppe Concealment",139:"Underground Concealment",140:"Grass Concealment",141:"Snow Concealment",
142:"Desert Concealment",143:"Wasteland Concealment",144:"Water Concealment",145:"Concealment",
146:"Holy Champion",147:"Unholy Champion",148:"Charm",149:"Charmed",150:"Dominated"}
try:
    ABIL.update({int(k): v for k, v in json.load(open(os.path.join(HERE, 'abil_names.json'))).items()})
    print('abil_names.json overrides loaded')
except Exception:
    pass
ROMAN = {1: ' I', 2: ' II', 3: ' III', 4: ' IV', 5: ' V'}
def aname(i, lvl=0):
    return ABIL.get(i, 'Ability 0x%02X' % i) + ROMAN.get(lvl, '')

# ---------------------------------------------------------------- units (Release/Unitres.pfs)
# child record = [classid:4][table][data]. Tags: 0xA race ShortString (or the NAME when 0xB absent
# — independents/monsters have no race), 0xB name, 0xE-0x13 = ATK/DEF/DMG/HP/Move/RES bytes
# (255 = no melee), 0x14 level, 0x1A description (len32 string), 0x1B gold cost u32,
# 0x19/0x1E/0x1F = base/Silver/Gold ability-owner sub-tables (tag2=count word, tag3=bitfield,
# bit i = has ability id i; leveled entries = regex 02 00 02 0a 00 0b 01 <lvl> <id> 00 in the span),
# tag 8 first dword = gfx id for the portrait chain (defaults to the unit's child id).
LVL_RE = re.compile(rb'\x02\x00\x02\x0a\x00\x0b\x01(.)(.)\x00', re.S)
def owner(d, t, b1, tag, end):
    if tag not in t: return None
    ot, ob = parse_table(d, b1 + t[tag])
    out = {'ids': [], 'lvl': {}}
    if 2 in ot and 3 in ot:
        cnt = struct.unpack_from('<H', d, ob + ot[2])[0]; nb = (cnt + 7) >> 3
        bf = d[ob + ot[3]:ob + ot[3] + nb]
        out['ids'] = [i for i in range(cnt) if bf[i >> 3] >> (i & 7) & 1]
    for m in LVL_RE.finditer(d[b1 + t[tag]:end]):
        lvl, aid = m.group(1)[0], m.group(2)[0]
        if aid in out['ids'] and 1 <= lvl <= 5: out['lvl'][aid] = lvl
    return out

units = []
try:
    d = open('Release/Unitres.pfs', 'rb').read()
    root, base = pfs_root(d)
    kids, kbase = parse_table(d, base + root[1])
    kp = sorted(kids.items(), key=lambda x: x[1])
    for i, (cid, rel) in enumerate(kp):
        off = kbase + rel
        end = kbase + (kp[i+1][1] if i + 1 < len(kp) else len(d) - kbase)
        t, b1 = parse_table(d, off + 4)
        if 10 not in t: continue
        if 11 in t: race, name = sstr(d, b1 + t[10]), sstr(d, b1 + t[11])
        else: race, name = '', sstr(d, b1 + t[10])
        st = [d[b1 + t[k]] if k in t else 0 for k in range(0xE, 0x14)]
        gfx = struct.unpack_from('<I', d, b1 + t[8])[0] if 8 in t else cid
        units.append(dict(
            id=cid, race=race, name=name, full=(race + ' ' + name).strip(),
            stats=['-' if x == 255 else x for x in st],
            level=(d[b1 + t[0x14]] if 0x14 in t else 0),
            cost=(struct.unpack_from('<I', d, b1 + t[0x1B])[0] if 0x1B in t else None),
            desc=(lstr(d, b1 + t[0x1A]).strip() if 0x1A in t else ''),
            gfx=gfx,
            base=owner(d, t, b1, 0x19, end), silver=owner(d, t, b1, 0x1E, end),
            gold=owner(d, t, b1, 0x1F, end)))
    print('units: %d' % len(units))
except Exception as e:
    print('units failed:', e)

# ---------------------------------------------------------------- abilities (Release/Ability.pfs)
# root table key = ABILITY ID + 10. Record = table directly (no classid).
# tag5 description (len32), tag6 hero skill-point cost (absent = not learnable),
# tag9 = 2-byte TAbilitySelectionTypes set: bit0 unit, bits1-5 item slots, bit6 use-item,
# bit7 Customize Leader, bit8 Hero Upgrade, bit9 editor.
abilities = []
try:
    d = open('Release/Ability.pfs', 'rb').read()
    root, base = pfs_root(d)
    for cid, off in sorted(root.items()):
        aid = cid - 10
        f, b1 = parse_table(d, base + off)
        desc = lstr(d, b1 + f[5]).replace('\r\n', '\n').strip() if 5 in f else ''
        cost = struct.unpack_from('<I', d, b1 + f[6])[0] if 6 in f else None
        sel = struct.unpack_from('<H', d, b1 + f[9])[0] if 9 in f else 0
        hero = bool(sel & 0x80) and bool(sel & 0x100)
        nm = ABIL.get(aid)
        if not nm and not desc: continue
        abilities.append(dict(id=aid, name=nm or ('Ability 0x%02X' % aid), desc=desc,
                              cost=cost, hero=hero))
    print('abilities: %d' % len(abilities))
except Exception as e:
    print('abilities failed:', e)

# ---------------------------------------------------------------- spells (Release/Spells.pfs)
# root table = spell list, record = table directly. tag 0xA description (len32),
# tag 0xD casting cost ("cast/upkeep" semantics vary), tag 0xF research cost.
# The game files store NO spell names — supply spell_names.json (id -> name) if you want them.
SPELLNAMES = {}
try:
    SPELLNAMES = {int(k): v for k, v in json.load(open(os.path.join(HERE, 'spell_names.json'))).items()}
except Exception:
    pass
spells = []
try:
    d = open('Release/Spells.pfs', 'rb').read()
    root, base = pfs_root(d)
    for cid, off in sorted(root.items()):
        f, b1 = parse_table(d, base + off)
        desc = lstr(d, b1 + f[0xA]).strip() if 0xA in f else ''
        if not desc: continue
        spells.append(dict(id=cid, name=SPELLNAMES.get(cid, 'Spell #%d' % cid), desc=desc,
                           cast=(struct.unpack_from('<I', d, b1 + f[0xD])[0] if 0xD in f else None),
                           research=(struct.unpack_from('<I', d, b1 + f[0xF])[0] if 0xF in f else None)))
    print('spells: %d' % len(spells))
except Exception as e:
    print('spells failed:', e)

# ---------------------------------------------------------------- portraits (Unitgfx.pfs -> face ILBs)
# Unitgfx child (classid 0x20210): tag6 = face ILB path, tag8 = face index within that ILB.
# GOTCHA: index base differs per file — original game face files are 0-based, some custom
# packs are 1-based (subtract 1). Use face_offset.json {"FACES\\PACK.ILB": -1} to correct.
FACE_OFF = {}
try:
    FACE_OFF = json.load(open(os.path.join(HERE, 'face_offset.json')))
except Exception:
    pass
GFX = {}
try:
    d = open('Release/Unitgfx.pfs', 'rb').read()
    root, base = pfs_root(d)
    kids, kbase = parse_table(d, base + root[1])
    for cid, rel in kids.items():
        t, b1 = parse_table(d, kbase + rel + 4)
        if 6 not in t: continue
        path = sstr(d, b1 + t[6])
        idx = struct.unpack_from('<I', d, b1 + t[8])[0] if 8 in t else 0
        GFX[cid] = (path, idx + FACE_OFF.get(path, 0))
except Exception as e:
    print('unitgfx failed:', e)

_ILB = {}
def ilb_frames(path):
    """Enumerate 16bpp frames of an ILB by the 0x56509310 pixel-format marker.
    Relative to marker: -0x18 size, -0x14 data offset, -0x10/-0xC record w/h, +4/+8 sub w/h.
    Raw frame when size == w*h*2 (dims at -0x10/-0xC); otherwise row-encoded (dims at +4/+8).
    File data base = dword at file offset 0x10. Transparent key color = RGB565 0x4D2B."""
    if path in _ILB: return _ILB[path]
    fp = os.path.join('Images', path.replace('\\', os.sep))
    try: d = open(fp, 'rb').read()
    except Exception: _ILB[path] = None; return None
    bs = struct.unpack_from('<I', d, 0x10)[0]
    recs = []
    for m in re.finditer(struct.pack('<I', 0x56509310), d):
        p = m.start()
        sz = struct.unpack_from('<I', d, p-0x18)[0]; of = struct.unpack_from('<I', d, p-0x14)[0]
        w = struct.unpack_from('<I', d, p-0x10)[0]; h = struct.unpack_from('<I', d, p-0xc)[0]
        sw = struct.unpack_from('<I', d, p+4)[0]; sh = struct.unpack_from('<I', d, p+8)[0]
        if 0 < w < 512 and 0 < h < 512 and sz == w*h*2: recs.append((w, h, bs+of, sz, d, True))
        elif 0 < sw < 512 and 0 < sh < 512: recs.append((sw, sh, bs+of, sz, d, False))
        else: recs.append((0, 0, 0, 0, d, True))
    _ILB[path] = recs
    return recs

def decode_frame(w, h, st, sz, d, raw):
    try: from PIL import Image
    except ImportError: return None
    im = Image.new('RGBA', (w, h)); px = im.load()
    def pix(v): return ((v >> 11)*255//31, ((v >> 5) & 63)*255//63, (v & 31)*255//31, 255)
    if raw:
        for k in range(w*h):
            v = struct.unpack_from('<H', d, st+k*2)[0]
            if v != 0x4D2B: px[k % w, k//w] = pix(v)
    else:
        # row-encoded: per row [len:u16][xstart:u16][(len-4)/2 pixels]; STRIDE = len rounded UP to
        # a multiple of 4 (the pad word looks like a pixel — classic decode trap).
        q = st; y = 0
        while q + 4 <= st + sz and y < h:
            L, S = struct.unpack_from('<HH', d, q)
            if L < 4: break
            for i in range((L-4)//2):
                x = S + i
                if x < w:
                    v = struct.unpack_from('<H', d, q+4+i*2)[0]
                    if v != 0x4D2B: px[x, y] = pix(v)
            q += (L + 3) & ~3; y += 1
    return im

_PCACHE = {}
def portrait(gfxid):
    k = GFX.get(gfxid)
    if not k: return ''
    if k in _PCACHE: return _PCACHE[k]
    uri = ''
    try:
        recs = ilb_frames(k[0])
        if recs and 0 <= k[1] < len(recs) and recs[k[1]][0] > 0:
            im = decode_frame(*recs[k[1]])
            if im is not None:
                im.thumbnail((96, 116))
                bf = io.BytesIO(); im.save(bf, 'PNG')
                uri = 'data:image/png;base64,' + base64.b64encode(bf.getvalue()).decode()
    except Exception:
        pass
    _PCACHE[k] = uri
    return uri

nport = 0
for u in units:
    u['img'] = portrait(u['gfx'])
    if u['img']: nport += 1
print('portraits: %d/%d' % (nport, len(units)))

# ---------------------------------------------------------------- assemble page data
def tier(o):
    if not o: return []
    return [aname(i, o['lvl'].get(i, 0)) for i in sorted(o['ids'], key=lambda x: aname(x))]
UD = []
for u in units:
    UD.append(dict(name=u['full'], race=u['race'] or 'Independent', level=u['level'],
                   stats=u['stats'], cost=u['cost'], desc=u['desc'], img=u['img'],
                   ab={'base': tier(u['base']), 'Silver': tier(u['silver']), 'Gold': tier(u['gold'])}))
races = sorted(set(x['race'] for x in UD), key=lambda r: (r == 'Independent', r))
avail = {}
for u in units:
    for tk in ('base', 'silver', 'gold'):
        o = u[tk]
        if o:
            for i in o['ids']:
                avail.setdefault(i, set()).add(u['full'])
for a in abilities:
    a['units'] = sorted(avail.get(a['id'], []))
data = dict(units=UD, races=races, abilities=abilities, spells=spells,
            stat=['ATK', 'DEF', 'DMG', 'HP', 'Move', 'RES'])

TEMPLATE = r'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mod Manual</title><style>
:root{--bg:#12100c;--panel:#1e1a12;--panel2:#262013;--ink:#e9e0c8;--muted:#a99d7e;--gold:#d4af57;--gold2:#b8912f;--line:#3a3122}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#0d0b08,#171309);color:var(--ink);font-family:"Segoe UI",Roboto,Arial,sans-serif;line-height:1.5}
a{color:var(--gold);text-decoration:none;cursor:pointer}
header{position:sticky;top:0;z-index:9;display:flex;gap:6px;align-items:center;padding:10px 18px;background:rgba(18,15,9,.96);border-bottom:2px solid var(--gold2)}
.brand{font-weight:700;color:var(--gold);margin-right:12px}
nav a{padding:6px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);font-size:14px}
nav a:hover{border-color:var(--gold);color:var(--gold)}
main{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
h2{color:var(--gold);border-bottom:2px solid var(--gold2);padding-bottom:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}
.card{padding:18px;border:1px solid var(--line);border-radius:12px;background:var(--panel);text-align:center;cursor:pointer}
.card:hover{border-color:var(--gold);background:var(--panel2)}
.units{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.unit{border:1px solid var(--line);border-radius:12px;background:var(--panel);overflow:hidden}
.uhead{display:flex;gap:12px;padding:12px;border-bottom:1px solid var(--line);background:var(--panel2);align-items:center}
.uhead img{width:56px;height:66px;object-fit:contain;border:1px solid var(--line);border-radius:6px;background:#0c0a06}
.uname{color:var(--gold);font-weight:600}.umeta{font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:5px 4px;text-align:center;border:1px solid var(--line)}
th{color:var(--muted);background:#0e0c08;font-size:11px}
.abil{padding:10px 12px;font-size:13px}.lab{color:var(--gold2);font-weight:600}
.med{color:var(--muted);font-size:12px;margin-top:3px}
.desc{color:var(--muted);font-size:12px;margin-top:6px;font-style:italic;border-top:1px dashed var(--line);padding-top:5px;white-space:pre-line}
.crumb{color:var(--muted);font-size:13px;margin-bottom:12px}
</style></head><body>
<header><span class="brand">Mod Manual</span><nav>
<a onclick="go('home')">Home</a><a onclick="go('races')">Units</a>
<a onclick="go('abilities')">Abilities</a><a onclick="go('spells')">Spells</a></nav></header>
<main id="app"></main>
<script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),app=document.getElementById('app');
const esc=s=>(s==null?'':(''+s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function go(h){location.hash=h}
function home(){return `<h2>Mod Manual</h2><div class="grid">
<div class="card" onclick="go('races')"><h3>Units</h3><p>${D.units.length} units</p></div>
<div class="card" onclick="go('abilities')"><h3>Abilities</h3><p>${D.abilities.length} abilities</p></div>
<div class="card" onclick="go('spells')"><h3>Spells</h3><p>${D.spells.length} spells</p></div></div>`}
function races(){const c={};D.units.forEach(u=>c[u.race]=(c[u.race]||0)+1);
return `<h2>Units</h2><div class="grid">${D.races.map(r=>`<div class="card" onclick="go('race/'+encodeURIComponent(r))"><h3>${esc(r)}</h3><p>${c[r]||0} units</p></div>`).join('')}</div>`}
function unitCard(u){
const img=u.img?`<img src="${u.img}">`:'';
const head=D.stat.map(s=>`<th>${s}</th>`).join(''),vals=u.stats.map(v=>`<td>${esc(v)}</td>`).join('');
const j=a=>a&&a.length?a.map(esc).join(', '):'';
return `<div class="unit"><div class="uhead">${img}<div><div class="uname">${esc(u.name)}</div>
<div class="umeta">Lvl ${esc(u.level)}${u.cost!=null?' &middot; Cost '+esc(u.cost):''}</div></div></div>
<table><tr>${head}</tr><tr>${vals}</tr></table>
<div class="abil"><span class="lab">Abilities:</span> ${j(u.ab.base)||'&#8212;'}
${u.ab.Silver.length?`<div class="med">&#9679; Silver: ${j(u.ab.Silver)}</div>`:''}
${u.ab.Gold.length?`<div class="med">&#9679; Gold: ${j(u.ab.Gold)}</div>`:''}
${u.desc?`<div class="desc">${esc(u.desc)}</div>`:''}</div></div>`}
function racePage(r){const list=D.units.filter(u=>u.race===r).sort((a,b)=>(a.level-b.level)||a.name.localeCompare(b.name));
return `<div class="crumb"><a onclick="go('races')">&#8592; Units</a></div><h2>${esc(r)}</h2><div class="units">${list.map(unitCard).join('')}</div>`}
function abilitiesPage(){return `<h2>Abilities</h2><div class="units">${D.abilities.map(a=>
`<div class="unit"><div class="uhead"><div><div class="uname">${esc(a.name)}</div>
<div class="umeta">Hero Level-Up: ${a.hero?'Yes':'No'}${a.hero&&a.cost!=null?' &middot; '+a.cost+' SP':''}</div></div></div>
<div class="abil"><div class="desc" style="border:none;padding:0;margin:0">${esc(a.desc)}</div>
${a.units.length?`<div class="med">Units (${a.units.length}): ${a.units.map(esc).join(', ')}</div>`:''}</div></div>`).join('')}</div>`}
function spellsPage(){return `<h2>Spells</h2><div class="units">${D.spells.map(s=>
`<div class="unit"><div class="uhead"><div><div class="uname">${esc(s.name)}</div>
<div class="umeta">${s.cast!=null?'Cast '+esc(s.cast):''}${s.research!=null?' &middot; Research '+esc(s.research):''}</div></div></div>
<div class="abil"><div class="desc" style="border:none;padding:0;margin:0">${esc(s.desc)}</div></div></div>`).join('')}</div>`}
function render(){const h=decodeURIComponent(location.hash.replace(/^#/,''))||'home';let x;
if(h==='races')x=races();else if(h==='abilities')x=abilitiesPage();else if(h==='spells')x=spellsPage();
else if(h.startsWith('race/'))x=racePage(h.slice(5));else x=home();
app.innerHTML=x;window.scrollTo(0,0)}
window.addEventListener('hashchange',render);render();
</script></body></html>'''

html = TEMPLATE.replace('__DATA__', json.dumps(data).replace('</', '<\\/'))
open(OUT, 'w', encoding='utf-8').write(html)
print('WROTE %s (%d KB)' % (OUT, len(html.encode()) // 1024))
