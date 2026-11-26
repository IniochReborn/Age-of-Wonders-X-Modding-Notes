#!/usr/bin/env python3
r"""Warp Self — cast gfx: give the spell the Warp Party teleport animation.

The stage-2 v6 cave spawns fxCloudPuff (type 0x22) effects tagged with
[fx+0x14]=0x34/[fx+0x18]=0xCA; the type-0x22 NewFrame handler resolves frames
from GetSpell(0xCA)->[spell+0x2C], the image sequence loaded from the spell
record's tag-0x0C blob. Warp Self's blob still clones Call Flames'
(EFFECTS\EXPLTC.ILB explosion). This patch transplants the cast-fx SECTION
from record key 44 (the vanilla teleport spell: EFFECTS\MAGIC.ILB frames
0..0xB = Teleport00-11 — the Warp Party visual) while keeping Warp Self's own
SPELLICN icon + BORDER sections.

Splice point: both blobs contain exactly one cast-fx section before the
SPELLICN.ILB section (which begins with its 0C000000 length dword). Record 212
is the last record in the file, so the record is rebuilt in place (tag offsets
shift) and the trailing CRC-32 recomputed.

Backup: Spells.pfs.bak_warpcastfx. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PFS = os.path.join(GAME, "Release", "Spells.pfs")
BAK = PFS + ".bak_warpcastfx"

SRC_KEY, DST_KEY = 44, 212
MARK = b"\x0c\x00\x00\x00SPELLICN.ILB"
NEWSEQ = b"EFFECTS\\MAGIC.ILB"
OLDSEQ = b"EFFECTS\\EXPLTC.ILB"


def tbl(d, p):
    b = d[p]; p += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from('<I', d, p)[0]; p += 4
    pairs = []
    for _ in range(nb): pairs.append((d[p], d[p+1])); p += 2
    for _ in range(nd): pairs.append(struct.unpack_from('<II', d, p)); p += 8
    return pairs, p


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, PFS); print("restored Spells.pfs"); return 0
        print("no backup"); return 1
    d = bytes(open(PFS, 'rb').read())
    assert zlib.crc32(d[4:-4]) & 0xFFFFFFFF == struct.unpack_from('<I', d, len(d)-4)[0], "src CRC bad"
    pairs, kbase = tbl(d, 7)
    idxl = sorted([(t, kbase + o) for t, o in pairs], key=lambda x: x[1])
    recs = {}
    for i, (k, off) in enumerate(idxl):
        end = idxl[i+1][1] if i+1 < len(idxl) else len(d)-4
        recs[k] = (off, end)
    # record 212 must be the last record (rebuilt in place)
    assert recs[DST_KEY][1] == len(d) - 4, "record 212 not last"

    def tagvals(key):
        off, end = recs[key]
        tp, tend = tbl(d, off)
        ent = sorted([(t, tend + o) for t, o in tp], key=lambda x: x[1])
        vals = []
        for j, (t, vo) in enumerate(ent):
            nxt = ent[j+1][1] if j+1 < len(ent) else end
            vals.append((t, bytearray(d[vo:nxt])))
        return vals

    src0c = dict(tagvals(SRC_KEY))[0x0C]
    vals = tagvals(DST_KEY)
    vmap = dict(vals)
    dst0c = vmap[0x0C]
    if NEWSEQ in dst0c and OLDSEQ not in dst0c:
        print("already applied"); return 0
    bs, bd = src0c.find(MARK), dst0c.find(MARK)
    assert bs > 0 and bd > 0, (bs, bd)
    assert OLDSEQ in dst0c[:bd] and NEWSEQ in src0c[:bs]
    vmap[0x0C] = bytearray(src0c[:bs]) + dst0c[bd:]
    # rebuild the record with stage-1's layout rules (byte pairs while off<=255)
    order = [t for t, _ in vals]
    o2 = 0; bytep = []; dwordp = []
    for t in order:
        (bytep if o2 <= 255 and not dwordp else dwordp).append((t, o2))
        o2 += len(vmap[t])
    rec = bytes([0x80 | len(bytep)]) + struct.pack('<I', len(dwordp))
    for t, o in bytep:  rec += bytes([t, o])
    for t, o in dwordp: rec += struct.pack('<II', t, o)
    for t in order:     rec += bytes(vmap[t])
    body = d[:recs[DST_KEY][0]] + rec
    out = body + struct.pack('<I', zlib.crc32(body[4:]) & 0xFFFFFFFF)
    print("tag 0x0C: cast-fx section %dB (EXPLTC) -> %dB (MAGIC.ILB teleport); record %d -> %dB"
          % (bd, bs, DST_KEY, len(rec)))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(PFS, BAK); print("Backup ->", os.path.basename(BAK))
    open(PFS, 'wb').write(out)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
