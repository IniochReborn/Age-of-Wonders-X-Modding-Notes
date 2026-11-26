#!/usr/bin/env python3
r"""New spell: "Summon Silver Dragon" (id 0xCB=203) — Secret sphere, level 4.

Mirrors build_summon_mermaid.py with a TSummonGoldDragon chassis:

A) AoWEPACK.dll cave @0x55810B80, hook = TSummonGoldDragon's RegisterSpell call
   in RegisterSummonSpells @0x557E515C (ebx = spell control). Cave: replicate
   the displaced call, construct a SECOND TSummonGoldDragon (classref
   [0x557E38D8], Create @0x557E4C1C) and poke: id 0xCB, sphere 7 (Secret),
   level 4, name "Summon Silver Dragon", summon list [spell+0x38] entry 0:
   0xD8 -> 0x99 (unit 153 Silver Dragon). Cast points/research stay the gold
   dragon defaults (user tunes in the editor). PIC delta (edi).

B) Images/SPELLICN.ILB: NO free icon pairs remain, so a NEW image id 200 is
   APPENDED: the id-88 (Summon Mermaid) wrapper record (class tag 0x100,
   two nested 40x35 RAW16 nodes, both sz 2800) is byte-cloned into the record
   stream just before the 0xFFFFFFFF terminator, its image id patched to 200
   and its two data offsets pointed at freshly appended pixel blobs:
   frame 0 = Secret dark cloud (copy of rec 144), frame 1 = the Summon Gold
   Dragon glyph (id 64 pair's 30x32 sub-frame rec, composited at its (4,2)
   offset onto a 40x35 white-keyed canvas). Header base/filesize fixed up
   (nested doffs are base-relative, existing records unaffected).

C) Release/Spells.pfs: new record key 213 appended = copy of Summon Gold
   Dragon's record (key 31: summon-circle cast gfx + summon sound) with
   desc / icon id 64 -> 200 / sphere 7 / level 4 overridden.

Backups: AoWEPACK.dll.bak_silverdragon, SPELLICN.ILB.bak_silverdragon,
Spells.pfs.bak_silverdragon. Dry-run; --apply / --revert.
"""
import os, shutil, struct, sys, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
ILB = os.path.join(GAME, "Images", "SPELLICN.ILB")
PFS = os.path.join(GAME, "Release", "Spells.pfs")
SUF = ".bak_silverdragon"

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810B80, 0x55810C80
REGISTERSPELL   = 0x55779B40
GOLD_CLASSREF   = 0x557E38D8
GOLD_CREATE     = 0x557E4C1C
LSTRASG         = 0x55701150
H_SITE = 0x557E515C
H_OLD  = bytes.fromhex("e8df49f9ff")       # call RegisterSpell
SPELL_ID  = 0xCB
UNIT_ID   = 0xFC                            # unit 252 Silver Dragon (153 is empty!)
NAME = b"Summon Silver Dragon"
DESC = b"Summons a Silver Dragon, a majestic guardian of the hidden ways."
SRC_ICON_ID, NEW_ICON_ID = 88, 200          # clone id-88 wrapper -> id 200
SECRET_CLOUD_REC = 144                      # Secret dark cloud pixels
GOLD_GLYPH_ID = 91                          # REAL gold dragon pair (key 35 = Life
                                            # L4; key 31/icon 64 was Fire Sprite!)
                                            # frame 1 = 40x35 dragon silhouette,
                                            # node key 0x4148 = same as our slot
SRC_KEY, NEW_KEY = 35, 213                  # pfs: gold dragon record -> ours


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.rel = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, tgt): self.db(0xE8); self.rel.append((len(self.buf), tgt)); self.buf += b'\0\0\0\0'
    def lea_delta(self, reg, label):
        self.db(0x8D, 0x87 | (reg << 3))
        self.fix32.append((len(self.buf), label)); self.dd(0)
    def resolve(self):
        for off, tgt in self.rel:
            self.buf[off:off+4] = (tgt - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] & 0xFFFFFFFF).to_bytes(4, 'little')


def build_cave():
    a = Asm(CAVE_BASE)
    a.call(REGISTERSPELL)                     # displaced: register vanilla gold dragon
    a.db(0x56, 0x57)                          # push esi; push edi
    a.call(a.here() + 5)                      # delta trick
    popva = a.here()
    a.db(0x5F)                                # pop edi
    a.db(0x81, 0xEF); a.dd(popva)             # sub edi, preferredVA -> delta
    a.db(0x33, 0xC9)                          # xor ecx, ecx
    a.db(0xB2, 0x01)                          # mov dl, 1
    a.db(0x8B, 0x87); a.dd(GOLD_CLASSREF)     # mov eax, [edi+classref]
    a.call(GOLD_CREATE)                       # -> eax = new TSummonGoldDragon
    a.db(0x8B, 0xF0)                          # mov esi, eax
    a.db(0xC7, 0x46, 0x10); a.dd(SPELL_ID)    # id = 0xCB
    a.db(0xC6, 0x46, 0x20, 0x07)              # sphere = Secret
    a.db(0xC6, 0x46, 0x21, 0x04)              # level = 4
    a.db(0x8B, 0x46, 0x38)                    # mov eax, [esi+0x38] (summon list)
    a.db(0x8B, 0x40, 0x04)                    # mov eax, [eax+4]    (items)
    a.db(0xC7, 0x00); a.dd(UNIT_ID)           # items[0] = 153 (Silver Dragon)
    a.lea_delta(2, 'lit')                     # lea edx, [edi+lit]
    a.db(0x8D, 0x46, 0x08)                    # lea eax, [esi+8]
    a.call(LSTRASG)
    a.db(0x8B, 0xD6)                          # mov edx, esi
    a.db(0x8B, 0xC3)                          # mov eax, ebx (control)
    a.call(REGISTERSPELL)
    a.db(0x5F, 0x5E, 0xC3)                    # pop edi; pop esi; ret
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


# ================= B) ILB append =================
def ilb_pixel_recs(d):
    base = struct.unpack_from('<I', d, 0x10)[0]
    recs = []; i = 0
    while True:
        j = d.find(b'\x10\x93\x50\x56', i)
        if j < 0: break
        w, h, sx, sy, key = struct.unpack_from('<5I', d, j+4)
        sz = struct.unpack_from('<I', d, j-0x18)[0]
        doff = struct.unpack_from('<I', d, j-0x14)[0]
        recs.append((j, w, h, sx, sy, key & 0xFFFF, sz, base + doff, doff))
        i = j + 4
    return base, recs


def build_ilb(d):
    base, recs = ilb_pixel_recs(d)
    fsz = struct.unpack_from('<I', d, 0x14)[0]
    assert fsz == len(d), (fsz, len(d))
    assert struct.unpack_from('<I', d, base-4)[0] == 0xFFFFFFFF, "terminator"
    # map image id -> pixel-rec index (cloud rec carries the id)
    ids = {}
    for k, r in enumerate(recs):
        win = d[max(0, r[0]-0x80):r[0]]
        q = win.rfind(b'\xff\xff\xff\xff')
        if q >= 0:
            iid = struct.unpack_from('<I', win, q+4)[0]
            if iid != 0xFFFFFFFF: ids[iid] = k
    assert NEW_ICON_ID not in ids, "icon id already exists"
    # wrapper slice for SRC_ICON_ID
    stream = d[0x18:base]
    w88 = d.find(struct.pack('<II', SRC_ICON_ID, 0x100), 0x18, base)
    assert w88 > 0
    nxt = len(d[:base])
    for iid, k in ids.items():
        p = d.find(struct.pack('<II', iid, 0x100), 0x18, base)
        if p > w88: nxt = min(nxt, p)
    wend = min(nxt, base - 4)
    clone = bytearray(d[w88:wend])
    struct.pack_into('<I', clone, 0, NEW_ICON_ID)
    # source pair (mermaid): recs k, k+1 with doffs to repoint
    k88 = ids[SRC_ICON_ID]
    for n, rk in enumerate((k88, k88+1)):
        _, w, h, sx, sy, key, sz, absoff, doff = recs[rk]
        assert sz == 2800, (rk, sz)
        pat = struct.pack('<II', sz, doff)
        p = clone.find(pat)
        assert p >= 0, ("doff pattern missing", rk)
        newdoff = (len(d) - base) + n * 2800
        struct.pack_into('<II', clone, p, sz, newdoff)
        assert clone.find(pat, p + 1) < 0, "ambiguous doff pattern"
    # frame 0: Secret cloud pixels
    _, w, h, sx, sy, key, sz, soff, _ = recs[SECRET_CLOUD_REC]
    assert (w, h, sz) == (40, 35, 2800)
    cloud = bytes(d[soff:soff+2800])
    # frame 1: the gold dragon silhouette frame verbatim (id 91's SECOND node:
    # 40x35, 2800B, node colorkey 0x4148 = identical to our cloned slot's)
    gk = ids[GOLD_GLYPH_ID]
    _, gw, gh, gx, gy, gkey, gsz, goff, _ = recs[gk+1]
    assert (gw, gh, gsz) == (40, 35, 2800), (gw, gh, gsz)
    assert gkey == recs[k88+1][5], (hex(gkey), hex(recs[k88+1][5]))
    glyph = bytes(d[goff:goff+2800])
    out = bytearray()
    out += d[:base-4]                 # header + stream (sans terminator)
    out += clone                      # new wrapper record
    out += d[base-4:base]             # terminator
    out += d[base:]                   # original pixel data
    out += cloud + glyph              # new pixel blobs
    struct.pack_into('<I', out, 0x10, base + len(clone))
    struct.pack_into('<I', out, 0x14, len(out))
    return bytes(out), len(clone)


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
    assert d[7] == 0x81
    nd = struct.unpack_from('<I', d, 8)[0]
    pairs, kbase = pfs_table(d, 7)
    idx = {t: kbase + o for t, o in pairs}
    assert NEW_KEY not in idx, "key exists"
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
    vmap[0x0A] = bytearray(struct.pack('<I', len(DESC)) + DESC)
    m = vmap[0x0C].find(b'SPELLICN.ILB')
    assert m >= 0
    ip = m + 12 + 3
    old = struct.unpack_from('<I', vmap[0x0C], ip)[0]
    assert old == GOLD_GLYPH_ID, old
    struct.pack_into('<I', vmap[0x0C], ip, NEW_ICON_ID)
    assert len(vmap[0x10]) == 1 and len(vmap[0x11]) == 1
    vmap[0x10] = bytearray([0x07])                   # Secret
    vmap[0x11] = bytearray([0x04])                   # level 4
    order = [t for t, _ in vals]
    o2 = 0; bytep = []; dwordp = []
    for t in order:
        (bytep if o2 <= 255 and not dwordp else dwordp).append((t, o2))
        o2 += len(vmap[t])
    rec = bytes([0x80 | len(bytep)]) + struct.pack('<I', len(dwordp))
    for t, o in bytep:  rec += bytes([t, o])
    for t, o in dwordp: rec += struct.pack('<II', t, o)
    for t in order:     rec += bytes(vmap[t])
    recblob = bytes(d[kbase:len(d)-4])
    root = bytes([0x81]) + struct.pack('<I', nd + 1) + bytes(d[12:14])
    p = 14
    for _ in range(nd):
        root += bytes(d[p:p+8]); p += 8
    root += struct.pack('<II', NEW_KEY, len(recblob))
    body = bytes(d[:7]) + root + recblob + rec
    return body + struct.pack('<I', zlib.crc32(body[4:]) & 0xFFFFFFFF)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        for f in (DLL, ILB, PFS):
            b = f + SUF
            if os.path.exists(b): shutil.copy2(b, f); print("restored", os.path.basename(f))
        return 0
    dll = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_scan(dll, [(h_off, h_off+5), (c_off, c_off+len(cave))])
    assert not hits, [hex(x) for x in hits]
    cur = bytes(dll[c_off:c_off+len(cave)])
    assert cur == bytes(len(cave)) or cur[:1] == b'\xE8', "cave mismatch"
    dll[c_off:c_off+len(cave)] = cave
    cur = bytes(dll[h_off:h_off+5])
    assert cur == H_OLD or cur[0] == 0xE8, cur.hex()
    dll[h_off:h_off+5] = bytes([0xE8]) + (CAVE_BASE - (H_SITE+5)).to_bytes(4, 'little', signed=True)
    print("DLL: cave %dB @0x%X, hook @0x%X" % (len(cave.rstrip(b'\0')), CAVE_BASE, H_SITE))
    ilb = bytes(open(ILB, 'rb').read())
    newilb, clonelen = build_ilb(ilb)
    print("ILB: id %d appended (wrapper %dB + 2x2800B pixels), %d -> %d bytes"
          % (NEW_ICON_ID, clonelen, len(ilb), len(newilb)))
    pfs = bytearray(open(PFS, 'rb').read())
    assert zlib.crc32(bytes(pfs[4:-4])) & 0xFFFFFFFF == struct.unpack_from('<I', pfs, len(pfs)-4)[0], "src CRC bad"
    newpfs = build_pfs(pfs)
    assert zlib.crc32(newpfs[4:-4]) & 0xFFFFFFFF == struct.unpack_from('<I', newpfs, len(newpfs)-4)[0]
    print("PFS: %d -> %d bytes, key %d added" % (len(pfs), len(newpfs), NEW_KEY))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    for f in (DLL, ILB, PFS):
        b = f + SUF
        if not os.path.exists(b): shutil.copy2(f, b); print("Backup ->", os.path.basename(b))
    open(DLL, 'wb').write(dll); open(ILB, 'wb').write(newilb); open(PFS, 'wb').write(newpfs)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
