#!/usr/bin/env python3
r"""New spell: "Summon Mermaid" (id 0xC9=201) — Secret sphere, level 1.

Background: vanilla Summon Mermaid (spell 0x4E, class TSummonMermaid) was
repurposed by the user into a custom summon ("Greater Spirit Puppet", unit 241
renamed from Mermaid). The real Mermaid still exists as UNIT 219. This adds a
NEW spell that summons unit 219, leaving the custom spell untouched.

Three patches in one script (mirrors the Magic Sight toolchain):

A) AoWEPACK.dll cave @0x55810900, hook = the last `call RegisterSpell` in
   RegisterSummonSpells @0x557E51CF (registers vanilla TSummonMermaid; ebx =
   spell control). Cave: replicate that call, then construct a SECOND
   TSummonMermaid (classref [0x557E3E94], Create @0x557E4FD0) and poke:
   id 0xC9, sphere 7 (Secret), level 1, name "Summon Mermaid" (literal via
   @LStrAsg — the RStr may be translated to the custom spell's name), and the
   summon list [spell+0x38] (TIntegerList: items @+4) entry 0: 0xF1 -> 0xDB
   (unit 219 Mermaid). Then RegisterSpell it. PIC delta (edi).
   The summon machinery (TSummonSpell.Activate/TE) is generic — no effect hook.

B) SPELLICN.ILB: image id 88 (recs 144/145, unused, RAW16 40x35) repainted:
   rec144 = blue water cloud (copied from rec 160) — the glow backdrop frame;
   rec145 = black TRIDENT ink glyph on white — the book ink frame.

C) Spells.pfs: new record key 211 (= spell id + 10) appended = copy of the
   user's key-88 record (a proven summon-record shape: sound + Spawn cast gfx)
   with desc / icon ref 155->88 / cast 5 / sphere tag 7 overridden. Root table
   gains one dword pair; trailing CRC-32 recomputed (pfs = [0x2144DF1C]
   [payload][crc32(payload)]).

Backups: AoWEPACK.dll.bak_mermaid, SPELLICN.ILB.bak_mermaid,
Spells.pfs.bak_mermaid. Dry-run; --apply / --revert.
"""
import os, shutil, struct, sys, math, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
ILB = os.path.join(GAME, "Images", "SPELLICN.ILB")
PFS = os.path.join(GAME, "Release", "Spells.pfs")

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810900, 0x55810A00
REGISTERSPELL = 0x55779B40
MERMAID_CLASSREF = 0x557E3E94
MERMAID_CREATE   = 0x557E4FD0
LSTRASG          = 0x55701150
H_SITE   = 0x557E51CF
H_OLD    = bytes.fromhex("e86c49f9ff")     # call RegisterSpell
SPELL_ID = 0xC9
UNIT_MERMAID = 0xDB                         # unit 219
NAME = b"Summon Mermaid"
DESC = b"Summons a Mermaid, an enchanting creature of the deep."
ICON_ID = 88                                # SPELLICN image id (recs 144/145)
CLOUD_SRC, CLOUD_DST, GLYPH_DST = 160, 144, 145
SRC_KEY, NEW_KEY = 88, 211                  # pfs chassis / new record key


# ================= A) DLL cave =================
class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.rel = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, tgt): self.db(0xE8); self.rel.append((len(self.buf), tgt)); self.buf += b'\0\0\0\0'
    def lea_delta(self, reg, va_or_label):
        self.db(0x8D, 0x87 | (reg << 3))
        if isinstance(va_or_label, str):
            self.fix32.append((len(self.buf), va_or_label)); self.dd(0)
        else: self.dd(va_or_label)
    def resolve(self):
        for off, tgt in self.rel:
            self.buf[off:off+4] = (tgt - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] & 0xFFFFFFFF).to_bytes(4, 'little')


def build_cave():
    a = Asm(CAVE_BASE)
    a.call(REGISTERSPELL)                     # displaced: register vanilla mermaid-slot spell
    a.db(0x56, 0x57)                          # push esi; push edi
    a.call(a.here() + 5)                      # delta trick
    popva = a.here()
    a.db(0x5F)                                # pop edi
    a.db(0x81, 0xEF); a.dd(popva)             # sub edi, preferredVA
    a.db(0x33, 0xC9)                          # xor ecx, ecx
    a.db(0xB2, 0x01)                          # mov dl, 1
    a.db(0x8B, 0x87); a.dd(MERMAID_CLASSREF)  # mov eax, [edi+classref]
    a.call(MERMAID_CREATE)                    # -> eax = new TSummonMermaid
    a.db(0x8B, 0xF0)                          # mov esi, eax
    a.db(0xC7, 0x46, 0x10); a.dd(SPELL_ID)    # id = 0xC9
    a.db(0xC6, 0x46, 0x20, 0x07)              # sphere = Secret
    a.db(0xC6, 0x46, 0x21, 0x01)              # level = 1
    a.db(0x8B, 0x46, 0x38)                    # mov eax, [esi+0x38] (TIntegerList)
    a.db(0x8B, 0x40, 0x04)                    # mov eax, [eax+4]    (items)
    a.db(0xC7, 0x00); a.dd(UNIT_MERMAID)      # mov dword [eax], 219 (replace 0xF1)
    a.lea_delta(2, 'lit')                     # lea edx, [edi+lit]
    a.db(0x8D, 0x46, 0x08)                    # lea eax, [esi+8]
    a.call(LSTRASG)
    a.db(0x8B, 0xD6)                          # mov edx, esi
    a.db(0x8B, 0xC3)                          # mov eax, ebx (control)
    a.call(REGISTERSPELL)
    a.db(0x5F, 0x5E, 0xC3)                    # pop edi; pop esi; ret -> 0x557E51D4
    a.dd(0xFFFFFFFF); a.dd(len(NAME))
    a.label('lit'); a.buf += NAME + b'\x00'
    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf))


def reloc_scan(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]; osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8); secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None: continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi: hits.append(fo)
        off += blk
    return hits


# ================= B) icon =================
def ilb_records(d):
    base = struct.unpack_from('<I', d, 0x10)[0]
    recs = []; i = 0
    while True:
        j = d.find(b'\x10\x93\x50\x56', i)
        if j < 0: break
        w  = struct.unpack_from('<I', d, j-0x10)[0]; h    = struct.unpack_from('<I', d, j-0xc)[0]
        sz = struct.unpack_from('<I', d, j-0x18)[0]; doff = struct.unpack_from('<I', d, j-0x14)[0]
        recs.append((w, h, sz, base + doff)); i = j + 4
    return recs


def build_trident():
    """40x35 ink trident glyph over waves. True = ink."""
    S = 8; W, H = 40*S, 35*S
    from PIL import Image, ImageDraw
    g = Image.new('L', (W, H), 0)
    dr = ImageDraw.Draw(g)
    cx = 20*S; LW = int(2.0*S)
    # shaft
    dr.line([cx, 12*S, cx, 26*S], fill=255, width=LW)
    # center prong
    dr.line([cx, 3*S, cx, 12*S], fill=255, width=LW)
    # crossbar
    dr.line([cx-7*S, 11*S, cx+7*S, 11*S], fill=255, width=LW)
    # outer prongs (curve up from crossbar ends)
    dr.line([cx-7*S, 11*S, cx-7*S, 5*S], fill=255, width=LW)
    dr.line([cx+7*S, 11*S, cx+7*S, 5*S], fill=255, width=LW)
    # prong tips (small arrowheads)
    for px in (cx-7*S, cx, cx+7*S):
        tip = 5*S if px != cx else 3*S
        dr.polygon([(px-1.4*S, tip+2.2*S), (px+1.4*S, tip+2.2*S), (px, tip-0.6*S)], fill=255)
    # waves at the bottom (two strokes)
    for yy, x0 in ((29*S, 6*S), (31.5*S, 8*S)):
        pts = []
        for t in range(0, 41):
            x = x0 + t*(28*S - (x0-6*S))/40
            pts.append((x, yy + math.sin(t/40*3.14159*3) * 1.5*S))
        dr.line(pts, fill=255, width=int(1.6*S))
    small = g.resize((40, 35), __import__('PIL.Image', fromlist=['Image']).LANCZOS if False else 1)
    from PIL import Image as PImage
    small = g.resize((40, 35), PImage.LANCZOS)
    px = small.load()
    return [[px[x, y] > 115 for x in range(40)] for y in range(35)]


def paint_icon(d, bak):
    recs = ilb_records(bak)
    for k in (CLOUD_SRC, CLOUD_DST, GLYPH_DST):
        w, h, sz, off = recs[k]
        assert (w, h, sz) == (40, 35, 2800), (k, w, h, sz)
    _, _, _, osrc = recs[CLOUD_SRC]
    _, _, _, odst = recs[CLOUD_DST]
    _, _, _, ogly = recs[GLYPH_DST]
    d[odst:odst+2800] = bak[osrc:osrc+2800]          # water cloud
    glyph = build_trident()
    for y in range(35):
        for x in range(40):
            p = ogly + (y*40 + x)*2
            struct.pack_into('<H', d, p, 0x0000 if glyph[y][x] else 0xFFFF)


# ================= C) pfs record =================
def pfs_table(d, p):
    b = d[p]; p += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from('<I', d, p)[0]; p += 4
    pairs = []
    for _ in range(nb): pairs.append((d[p], d[p+1])); p += 2
    for _ in range(nd): pairs.append(struct.unpack_from('<II', d, p)); p += 8
    return pairs, p


def build_pfs(d):
    ctrl = d[7]
    assert ctrl == 0x81, hex(ctrl)
    nd = struct.unpack_from('<I', d, 8)[0]
    pairs, kbase = pfs_table(d, 7)
    idx = {t: kbase + o for t, o in pairs}
    assert NEW_KEY not in idx, "key 211 already exists"
    # source record (key 88) values
    off = idx[SRC_KEY]
    tp, tend = pfs_table(d, off)
    ent = sorted([(t, tend + o) for t, o in tp], key=lambda x: x[1])
    later = [v for v in idx.values() if v > off]
    src_end = min(later) if later else len(d) - 4
    vals = []
    for i, (t, vo) in enumerate(ent):
        nxt = ent[i+1][1] if i+1 < len(ent) else src_end
        vals.append((t, bytearray(d[vo:nxt])))
    vmap = dict(vals)
    # overrides
    vmap[0x0A] = bytearray(struct.pack('<I', len(DESC)) + DESC)
    m = vmap[0x0C].find(b'SPELLICN.ILB')
    assert m >= 0
    ip = m + 12 + 3
    old = struct.unpack_from('<I', vmap[0x0C], ip)[0]
    assert old == 155, old
    struct.pack_into('<I', vmap[0x0C], ip, ICON_ID)
    vmap[0x0D] = bytearray(struct.pack('<I', 5))     # cast 5
    assert len(vmap[0x10]) == 1
    vmap[0x10] = bytearray([0x07])                   # Secret
    vmap[0x11] = bytearray([0x01])                   # level 1
    # encode record (vanilla shape: values in tag order, byte pairs then dwords)
    order = [t for t, _ in vals]
    o2 = 0; bytep = []; dwordp = []
    for t in order:
        (bytep if o2 <= 255 and not dwordp else dwordp).append((t, o2))
        o2 += len(vmap[t])
    rec = bytes([0x80 | len(bytep)]) + struct.pack('<I', len(dwordp))
    for t, o in bytep:  rec += bytes([t, o])
    for t, o in dwordp: rec += struct.pack('<II', t, o)
    for t in order:     rec += bytes(vmap[t])
    # rebuild root: nd+1, append (211, offset = size of existing records blob)
    recblob = bytes(d[kbase:len(d)-4])
    newpair_off = len(recblob)
    root = bytes([0x81]) + struct.pack('<I', nd + 1)
    p = 12
    root += bytes(d[12:12 + 2])          # the single byte-pair (0x0B, 0x00)
    p = 12 + 2
    for _ in range(nd):
        root += bytes(d[p:p+8]); p += 8
    root += struct.pack('<II', NEW_KEY, newpair_off)
    body = bytes(d[:7]) + root + recblob + rec
    return body + struct.pack('<I', zlib.crc32(body[4:]) & 0xFFFFFFFF)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        for f in (DLL, ILB, PFS):
            b = f + ".bak_mermaid"
            if os.path.exists(b): shutil.copy2(b, f); print("restored", os.path.basename(f))
        return 0
    # --- DLL ---
    dll = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_scan(dll, [(h_off, h_off+5), (c_off, c_off+len(cave))])
    assert not hits, [hex(x) for x in hits]
    cur = bytes(dll[c_off:c_off+len(cave)])
    assert cur == bytes(len(cave)) or cur[:1] == b'\xE8', "cave mismatch"
    dll[c_off:c_off+len(cave)] = cave
    cur = bytes(dll[h_off:h_off+5])
    assert cur == H_OLD or cur[0] == 0xE8, "hook mismatch"
    dll[h_off:h_off+5] = bytes([0xE8]) + (CAVE_BASE - (H_SITE+5)).to_bytes(4, 'little', signed=True)
    print("DLL: cave %dB @0x%X, hook @0x%X, reloc clean" % (len(cave.rstrip(b'\0')), CAVE_BASE, H_SITE))
    # --- ILB ---
    ilb = bytearray(open(ILB, 'rb').read())
    bak_ilb = bytes(ilb)
    paint_icon(ilb, bak_ilb)
    print("ILB: rec %d = water cloud (from %d), rec %d = trident glyph (image id %d)"
          % (CLOUD_DST, CLOUD_SRC, GLYPH_DST, ICON_ID))
    # --- PFS ---
    pfs = bytearray(open(PFS, 'rb').read())
    assert zlib.crc32(bytes(pfs[4:-4])) & 0xFFFFFFFF == struct.unpack_from('<I', pfs, len(pfs)-4)[0], "src CRC bad"
    newpfs = build_pfs(pfs)
    assert zlib.crc32(newpfs[4:-4]) & 0xFFFFFFFF == struct.unpack_from('<I', newpfs, len(newpfs)-4)[0]
    pairs, kbase = pfs_table(newpfs, 7)
    idx = {t: kbase+o for t, o in pairs}
    assert NEW_KEY in idx
    print("PFS: %d -> %d bytes, %d records, key %d added, CRC OK" % (len(pfs), len(newpfs), len(pairs), NEW_KEY))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    for f in (DLL, ILB, PFS):
        b = f + ".bak_mermaid"
        if not os.path.exists(b): shutil.copy2(f, b); print("Backup ->", os.path.basename(b))
    open(DLL, 'wb').write(dll); open(ILB, 'wb').write(ilb); open(PFS, 'wb').write(newpfs)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
