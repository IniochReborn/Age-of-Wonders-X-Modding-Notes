#!/usr/bin/env python3
r"""Magic Sight — ICON + spell gfx/description (data files, not code).

Spell visuals load from Release/Spells.pfs: record key = spell id + 10, so key
210 = Magic Sight (0xC8). The editor already wrote a stub record 210 (cost etc.)
with an EMPTY gfx tag 0x0C -> blank icon, no side image. Fix = fill it.

gfx tag 0x0C = TImageSequenceList stream. The spellbook icon entry references
SPELLICN.ILB + a record index; icons are 2-frame pairs (cloud background,
ink glyph overlaid with WHITE 0xFFFF as transparency key). Records are 40x35
RGB565; pairs 56/57 are unused (verified: no SPELLICN ref anywhere in
Release/*.pfs, *.ahl, or the binaries) -> we repaint them in place:
  rec 56 = Secret-sphere purple cloud (copied from rec 212) + eye glyph baked
  rec 57 = same eye glyph on pure white (overlay frame)
Baked + overlay covers both draw semantics (single-frame or composite).

Record 210 is the LAST record in Spells.pfs, so it can be rebuilt in place
(truncate + append) without shifting anything. New record keeps the stub's
tags (0B sound?, 0D cast=5, 0E, 10 sphere-ish, 11 tail) and adds:
  tag 0x0A = description
  tag 0x0C = byte-copy of Enchant Weapon's gfx blob (key 26) — cast anim,
             side image, BORDER frames — with its SPELLICN icon index patched
             120 -> 56.
Table uses byte-offset pairs; small values first so every offset fits <=255.

Backups: Images/SPELLICN.ILB.bak_magicsight, Release/Spells.pfs.bak_magicsight.
Revert = restore both backups (--revert). Dry-run by default; --apply.
"""
import os, shutil, struct, sys, math, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ILB = os.path.join(GAME, "Images", "SPELLICN.ILB")
PFS = os.path.join(GAME, "Release", "Spells.pfs")

ICON_ID = 151           # SPELLICN image ID (per-record header id, NOT ordinal!)
                        # 151 = unused SI-Secret pair, painted by icon2 script
ENCHW_KEY, MS_KEY = 26, 210
DESC = b"Enchants a unit with magical sight, granting it Night Vision and True Seeing."
INK = (10, 6, 20)


# ---------- ILB helpers ----------
def ilb_records(d):
    base = struct.unpack_from('<I', d, 0x10)[0]
    recs = []
    i = 0
    while True:
        j = d.find(b'\x10\x93\x50\x56', i)
        if j < 0: break
        w  = struct.unpack_from('<I', d, j-0x10)[0]; h    = struct.unpack_from('<I', d, j-0xc)[0]
        sz = struct.unpack_from('<I', d, j-0x18)[0]; doff = struct.unpack_from('<I', d, j-0x14)[0]
        recs.append((w, h, sz, base + doff))
        i = j + 4
    return recs


def rgb565(r, g, b): return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def build_glyph():
    """40x35 1-bit eye glyph (True = ink). Pure-python supersampled render."""
    S = 8; W, H = 40*S, 35*S
    from PIL import Image, ImageDraw
    g = Image.new('L', (W, H), 255)
    dr = ImageDraw.Draw(g)
    cx, cy = 20*S, 18*S
    ew, eh = 14*S, 7*S
    def almond(scale):
        pts = []
        for t in range(0, 101):
            x = -1 + 2*t/100.0
            pts.append((cx + x*ew*scale, cy - (1 - x*x)*eh*scale))
        for t in range(0, 101):
            x = 1 - 2*t/100.0
            pts.append((cx + x*ew*scale, cy + (1 - x*x)*eh*scale))
        return pts
    dr.polygon(almond(1.0), fill=0)
    dr.polygon(almond(0.82), fill=255)
    ir = int(4.8*S); LW = int(1.6*S)
    dr.ellipse([cx-ir, cy-ir, cx+ir, cy+ir], outline=0, width=LW)
    pr = int(2.1*S)
    dr.ellipse([cx-pr, cy-pr, cx+pr, cy+pr], fill=0)
    for ang in (-35, 0, 35):
        a = math.radians(ang - 90)
        r1 = eh + 2.2*S; r2 = eh + 5.6*S
        dr.line([cx+math.cos(a)*r1*1.35, cy+math.sin(a)*r1,
                 cx+math.cos(a)*r2*1.35, cy+math.sin(a)*r2], fill=0, width=LW)
    small = g.resize((40, 35), Image.LANCZOS).point(lambda v: 0 if v < 140 else 255)
    px = small.load()
    return [[px[x, y] == 0 for x in range(40)] for y in range(35)]


def paint_icon(d):
    recs = ilb_records(d)
    for k in (REC_CLOUD_SRC, REC_F0, REC_F1):
        w, h, sz, off = recs[k]
        assert (w, h) == (40, 35) and sz == 2800, "rec %d not RAW16 40x35" % k
    glyph = build_glyph()
    _, _, _, src = recs[REC_CLOUD_SRC]
    _, _, _, o0  = recs[REC_F0]
    _, _, _, o1  = recs[REC_F1]
    ink = rgb565(*INK)
    for y in range(35):
        for x in range(40):
            p = (y*40 + x) * 2
            cw = struct.unpack_from('<H', d, src + p)[0]
            struct.pack_into('<H', d, o0 + p, ink if glyph[y][x] else cw)
            struct.pack_into('<H', d, o1 + p, ink if glyph[y][x] else 0xFFFF)


# ---------- PFS helpers ----------
def pfs_table(d, p):
    b = d[p]; p += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from('<I', d, p)[0]; p += 4
    pairs = []
    for _ in range(nb): pairs.append((d[p], d[p+1])); p += 2
    for _ in range(nd): pairs.append(struct.unpack_from('<II', d, p)); p += 8
    return pairs, p


def rebuild_record210(d):
    """Record 210 = byte-for-byte copy of Enchant Weapon's record (key 26):
    real 0x0B sound stream (EnchW cast sound), full 23-slot gfx (cast twinkles
    slots 0-9, icon slot 10, BORDER side/border images slots 11-13), research.
    Only scalar values overridden: 0x0A desc (ours), 0x0C icon id 120->ICON_ID,
    0x0D cast=5, 0x10 sphere byte=7 (Secret).

    THE FORMAT'S MISSING PIECE (why every earlier hand-write failed): the file
    is [0x2144DF1C][payload][crc32(payload)] — trailing CRC-32 over d[4:-4],
    validated at open; a bad/missing tail rejects the WHOLE file (all spells
    lose gfx/stats). The leading dword is the CRC-32 residue constant used as
    a format tag. main() recomputes the tail after splicing."""
    pairs, kbase = pfs_table(d, 7)
    idx = {t: kbase + o for t, o in pairs}
    assert idx[MS_KEY] > max(v for k, v in idx.items() if k != MS_KEY), "210 not last"
    tp, tend = pfs_table(d, idx[ENCHW_KEY])
    ent = sorted([(t, tend + o) for t, o in tp], key=lambda x: x[1])
    vals = []                                # (tag, value bytes) in EnchW's order
    for i, (t, vo) in enumerate(ent):
        nxt = ent[i+1][1] if i+1 < len(ent) else idx_next_record(idx, ENCHW_KEY, len(d))
        vals.append((t, bytearray(d[vo:nxt])))
    vmap = dict(vals)
    assert set(vmap) == {0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11}, sorted(vmap)
    # overrides
    vmap[0x0A] = bytearray(struct.pack('<I', len(DESC)) + DESC)
    m = vmap[0x0C].find(b'SPELLICN.ILB')
    ip = m + len(b'SPELLICN.ILB') + 3
    assert struct.unpack_from('<I', vmap[0x0C], ip)[0] == 120
    struct.pack_into('<I', vmap[0x0C], ip, ICON_ID)
    vmap[0x0D] = bytearray(struct.pack('<I', 5))     # cast cost 5
    assert len(vmap[0x10]) == 1
    vmap[0x10] = bytearray([0x07])                   # sphere byte: Secret
    # encode: same shape as key 26 (ctrl 0x83: 3 byte-pairs, rest dword-pairs)
    order = [t for t, _ in vals]
    off = 0; bytep = []; dwordp = []
    for t in order:
        (bytep if off <= 255 and not dwordp else dwordp).append((t, off))
        off += len(vmap[t])
    rec = bytes([0x80 | len(bytep)]) + struct.pack('<I', len(dwordp))
    for t, o in bytep:  rec += bytes([t, o])
    for t, o in dwordp: rec += struct.pack('<II', t, o)
    for t in order:     rec += bytes(vmap[t])
    return bytes(d[:idx[MS_KEY]]) + rec


def idx_next_record(idx, key, eof):
    """File offset where the record after `key` starts (or EOF)."""
    here = idx[key]
    later = [v for v in idx.values() if v > here]
    return min(later) if later else eof


def main():
    # PFS-only now: the ILB eye art (image id 151) is owned by
    # build_magic_sight_icon2.py — this script no longer touches the ILB.
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        b = PFS + ".bak_magicsight"
        if os.path.exists(b):
            shutil.copy2(b, PFS); print("restored %s" % os.path.basename(PFS)); return 0
        print("no backup found"); return 1

    pfs = bytearray(open(PFS, 'rb').read())
    # verify the source file's own CRC before touching it
    assert zlib.crc32(bytes(pfs[4:-4])) & 0xFFFFFFFF == struct.unpack_from('<I', pfs, len(pfs)-4)[0], \
        "source pfs CRC invalid — refusing to build on a corrupt file"
    newpfs = rebuild_record210(pfs)          # ends after record 210's values (no tail)
    newpfs += struct.pack('<I', zlib.crc32(newpfs[4:]) & 0xFFFFFFFF)   # fresh trailing CRC
    print("PFS: record 210 rebuilt, file %d -> %d bytes (CRC 0x%08X)" % (
        len(pfs), len(newpfs), struct.unpack_from('<I', newpfs, len(newpfs)-4)[0]))
    # sanity: re-parse new pfs
    pairs, kbase = pfs_table(newpfs, 7)
    idx = {t: kbase + o for t, o in pairs}
    tp, tend = pfs_table(newpfs, idx[MS_KEY])
    tmap = {t: tend + o for t, o in tp}
    assert 0x0C in tmap and 0x0A in tmap and 0x0D in tmap
    m = newpfs.find(b'SPELLICN.ILB', idx[MS_KEY])
    iv = struct.unpack_from('<I', newpfs, m + 12 + 3)[0]
    print("  re-parse OK: %d tags, icon idx=%d, desc len=%d, cast=%d" % (
        len(tp), iv, struct.unpack_from('<I', newpfs, tmap[0x0A])[0],
        struct.unpack_from('<I', newpfs, tmap[0x0D])[0]))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    b = PFS + ".bak_magicsight"
    if not os.path.exists(b):
        shutil.copy2(PFS, b); print("Backup -> %s" % os.path.basename(b))
    open(PFS, 'wb').write(newpfs)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
