#!/usr/bin/env python3
r"""Warp Self — STAGE 1: register the spell (Call Flames-mechanics clone).

New spell id 0xCA (202) "Warp Self", Secret sphere, level 3, combat-castable,
hex-target with RANGE 8. Stage 1 = full working chassis: casting it in tactical
combat targets a hex up to 8 away and (placeholder) applies Call Flames' fire
effect. Stage 2 will hook the effect and teleport the caster instead.

Three patches:
A) AoWEPACK.dll cave @0x55810A00, hook = last `call RegisterSpell` in
   RegisterCombatSpells @0x557FA83F (ebx = spell control). Cave replicates the
   displaced call, constructs a second TCallFlames (classref [0x557F51D0],
   Create @0x557F8CE4), pokes: id 0xCA, sphere 7 (Secret), level 3, cast cost 8,
   combat param block range byte [spell+0x39] = 8 (Call Flames ships 0xC), name
   "Warp Self" (literal via @LStrAsg). PIC delta (edi).
B) AoWTCPCK.dll: SpellTypes[202] = 7 (file 0x662F4+202) — the combat-cast
   pipeline type (same as EnchW/Call Flames); without it the cast token errors.
C) Spells.pfs: record key 212 = copy of Call Flames' record (key 123) with
   desc / icon -> image id 52 (existing unused pair; placeholder) / cast 8 /
   sphere tag 7 / level tag 3 overridden; root-table append + trailing CRC-32.

Backups: AoWEPACK.dll.bak_warpself, AoWTCPCK.dll.bak_warpself,
Spells.pfs.bak_warpself. Dry-run; --apply / --revert.
"""
import os, shutil, struct, sys, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
TC  = os.path.join(GAME, "AoWTCPCK.dll")
PFS = os.path.join(GAME, "Release", "Spells.pfs")

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810A00, 0x55810B00
REGISTERSPELL   = 0x55779B40
FLAMES_CLASSREF = 0x557F51D0
FLAMES_CREATE   = 0x557F8CE4
LSTRASG         = 0x55701150
H_SITE = 0x557FA83F
H_OLD  = bytes.fromhex("e8fcf2f7ff")
SPELL_ID = 0xCA
NAME = b"Void Step"   # renamed from "Warp Self" 8/10 (build_void_step_rename.py)
DESC = b"Warps the caster instantly to a target hex up to 8 hexes away."
RANGE = 8
CAST = 8
ICON_ID = 52
SPELLTYPES_FILE = 0x3B400          # AoWTCPCK file offset of SpellTypes[0] — the RELOCATED 512-entry table
                                   # at VA 0x43C000 (patch_spelltypes_relocate_v1.py, 2026-10-03).  The old
                                   # 0x662F4 table is only 131 bytes; [202] there is BreathDir, do not use.
SRC_KEY, NEW_KEY = 123, 212        # pfs: Call Flames record -> our record


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
    a.call(REGISTERSPELL)                     # displaced: register the original spell
    a.db(0x56, 0x57)                          # push esi; push edi
    a.call(a.here() + 5)
    popva = a.here()
    a.db(0x5F)                                # pop edi
    a.db(0x81, 0xEF); a.dd(popva)             # edi = load delta
    a.db(0x33, 0xC9)                          # xor ecx, ecx
    a.db(0xB2, 0x01)                          # mov dl, 1
    a.db(0x8B, 0x87); a.dd(FLAMES_CLASSREF)   # mov eax, [edi+classref]
    a.call(FLAMES_CREATE)                     # -> eax = new TCallFlames
    a.db(0x8B, 0xF0)                          # mov esi, eax
    a.db(0xC7, 0x46, 0x10); a.dd(SPELL_ID)    # id = 0xCA
    a.db(0xC7, 0x46, 0x14); a.dd(CAST)        # cast cost
    a.db(0xC6, 0x46, 0x20, 0x07)              # sphere = Secret
    a.db(0xC6, 0x46, 0x21, 0x03)              # level = 3
    a.db(0xC6, 0x46, 0x39, RANGE)             # combat param block: range = 8
    a.lea_delta(2, 'lit')                     # name literal
    a.db(0x8D, 0x46, 0x08)
    a.call(LSTRASG)
    a.db(0x8B, 0xD6)                          # mov edx, esi
    a.db(0x8B, 0xC3)                          # mov eax, ebx (control)
    a.call(REGISTERSPELL)
    a.db(0x5F, 0x5E, 0xC3)
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
    assert NEW_KEY not in idx
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
    struct.pack_into('<I', vmap[0x0C], m + 12 + 3, ICON_ID)
    vmap[0x0D] = bytearray(struct.pack('<I', CAST))
    if 0x10 in vmap and len(vmap[0x10]) == 1: vmap[0x10] = bytearray([0x07])
    if 0x11 in vmap and len(vmap[0x11]) == 1: vmap[0x11] = bytearray([0x03])
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
        for f in (DLL, TC, PFS):
            b = f + ".bak_warpself"
            if os.path.exists(b): shutil.copy2(b, f); print("restored", os.path.basename(f))
        return 0
    # A) DLL
    dll = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_scan(dll, [(h_off, h_off+5), (c_off, c_off+len(cave))])
    assert not hits, [hex(x) for x in hits]
    cur = bytes(dll[c_off:c_off+len(cave)])
    assert cur == bytes(len(cave)) or cur[:1] == b'\xE8'
    dll[c_off:c_off+len(cave)] = cave
    cur = bytes(dll[h_off:h_off+5])
    assert cur == H_OLD or cur[0] == 0xE8, cur.hex()
    dll[h_off:h_off+5] = bytes([0xE8]) + (CAVE_BASE - (H_SITE+5)).to_bytes(4, 'little', signed=True)
    print("DLL: cave %dB @0x%X, hook @0x%X" % (len(cave.rstrip(b'\0')), CAVE_BASE, H_SITE))
    # B) SpellTypes
    tc = bytearray(open(TC, 'rb').read())
    old = tc[SPELLTYPES_FILE + SPELL_ID]
    tc[SPELLTYPES_FILE + SPELL_ID] = 7
    print("TC: SpellTypes[%d] %d -> 7" % (SPELL_ID, old))
    # C) pfs
    pfs = bytearray(open(PFS, 'rb').read())
    assert zlib.crc32(bytes(pfs[4:-4])) & 0xFFFFFFFF == struct.unpack_from('<I', pfs, len(pfs)-4)[0], "src CRC bad"
    newpfs = build_pfs(pfs)
    assert zlib.crc32(newpfs[4:-4]) & 0xFFFFFFFF == struct.unpack_from('<I', newpfs, len(newpfs)-4)[0]
    print("PFS: %d -> %d bytes, key %d added" % (len(pfs), len(newpfs), NEW_KEY))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    for f in (DLL, TC, PFS):
        b = f + ".bak_warpself"
        if not os.path.exists(b): shutil.copy2(f, b); print("Backup ->", os.path.basename(b))
    open(DLL, 'wb').write(dll); open(TC, 'wb').write(tc); open(PFS, 'wb').write(newpfs)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
