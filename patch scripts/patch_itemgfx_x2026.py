#!/usr/bin/env python3
r"""
Release\ITEMGFX.PFS: register the 210 I_x2026.ilb icons as Item GFX entries 426..635 (2026-09-21).

ITEMGFX.PFS = magic 1C DF 44 21, `01 00 00`, root table (tag2 byte, tag1 = kids table), kids table
(ctrl 0x86: 6 narrow + nd wide (id u32, off u32) entries, offsets relative to the table end), then one record per
Item GFX: [classid 0x20269][table][data] with tags 1 = uid (u32, editor-era records), 2 = 26 (u32, constant),
3 = global id (u32, == child id), 6 = ILB path (Pascal short string), 7 = frame index in that ILB (u32),
8 = slot byte (0 Head, 1 Body, 2 Attack, 3 Defense, 4 Ring, 6 Use); trailing CRC-32 of everything after the magic.
Vanilla+x2025 end at id 422 (I_X2025 frames 20..96).  New ids 426..635 (423-425 left blank per user), one per
I_x2026 image in library order (attack 33 / body 33 / defense 30 / head 25 / ring 35 / use 54), frame = image index,
slot by section.  Existing records and their order are untouched (only the kids table grows and records are
appended - the game and editor rely on the existing order).  Backup ITEMGFX.PFS.bak_x2026gfx (in <game>\backup\).
Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys, zlib
from bakpath import game_file, bak_path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "old modding tools", "research"))
import ilbcodec  # noqa: E402

PFS = game_file(r"Release\ITEMGFX.PFS")
ILB = game_file(r"Images\Items\I_x2026.ilb")
BAK = ".bak_x2026gfx"
FIRST_ID = 426
CLASSID = 0x20269
PATH = b"ITEMS\\I_X2026.ILB"
SLOT = {"attack": 2, "body": 1, "defense": 3, "head": 0, "ring": 4, "use": 6}
MAGIC = bytes.fromhex("1cdf4421")


def tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F; narrow = []; wide = []
    for _ in range(nb):
        narrow.append((dd[p], dd[p + 1])); p += 2
    for _ in range(nd):
        wide.append(struct.unpack_from('<II', dd, p)); p += 8
    return narrow, wide, p


def record(uid, gid, frame, slot):
    data = struct.pack("<III", uid, 26, gid) + bytes([len(PATH)]) + PATH + struct.pack("<I", frame) + bytes([slot])
    offs = {1: 0, 2: 4, 3: 8, 6: 12, 7: 12 + 1 + len(PATH), 8: 12 + 1 + len(PATH) + 4}
    table = bytes([6]) + b"".join(bytes([t, offs[t]]) for t in (1, 2, 3, 6, 7, 8))
    return struct.pack("<I", CLASSID) + table + data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    bak = bak_path(PFS, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, PFS); print(f"reverted {PFS} from {bak}"); return
    d = open(PFS, "rb").read()
    assert d[:4] == MAGIC and zlib.crc32(d[4:]) & 0xFFFFFFFF == 0x2144DF1C, "not a valid ITEMGFX.PFS (magic/CRC)"
    lib = ilbcodec.read(ILB); names = [im['parts'][0]['name'].decode('latin1') for im in lib['images']]
    assert names[0].startswith("attack") and len(names) >= 210, "I_x2026.ilb is not the v2 library"
    rn, rw, rb = tbl(d, 7)
    root = dict(rn + rw); kt = rb + root[1]
    kn, kw, kb = tbl(d, kt)
    kids = kn + kw; ids = [k for k, _ in kids]
    print(f"target: {PFS} ({len(d)} B): {len(kids)} Item GFX (ids {min(ids)}..{max(ids)}), records @+{kb:#x}")
    if max(ids) >= FIRST_ID:
        have = [k for k in ids if k >= FIRST_ID]
        print(f"  ids >= {FIRST_ID} already present: {have[:5]}.. ({len(have)}) -> {'ALREADY PATCHED' if len(have) == len(names) else 'UNEXPECTED'}")
        if not a.apply:
            print("dry run - nothing written"); return
        sys.exit("refusing")
    uids = set()
    for k, off in kids:
        p = kb + off; n_, w_, b1 = tbl(d, p + 4); f = dict(n_ + w_)
        if 1 in f:
            uids.add(struct.unpack_from("<I", d, b1 + f[1])[0])
    body = d[4:-4]; kids_end_abs = kb; rec_start = kb
    old_len = len(d) - 4 - kb                     # bytes of records (relative offsets max)
    new_recs = []; uid_seed = 0x2026
    for i, nm in enumerate(names):
        slot = SLOT[nm.rstrip("0123456789.bmp")]
        uid = zlib.crc32(b"x2026gfx%d" % i) & 0x0FFFFFFF
        while uid in uids or uid == 0:
            uid = (uid + 0x9E3779B1) & 0x0FFFFFFF
        uids.add(uid)
        new_recs.append((FIRST_ID + i, record(uid, FIRST_ID + i, i, slot)))
    # rebuild: [4..kt] unchanged, new kids table (nd + 210), records (old bytes) + appended records
    rec_bytes = bytearray(d[kb:len(d) - 4])
    extra = []; off = len(rec_bytes)
    for gid, rec in new_recs:
        extra.append((gid, off)); rec_bytes += rec; off += len(rec)
    kt_bytes = bytes([0x80 | len(kn)]) + struct.pack("<I", len(kw) + len(extra))
    kt_bytes += b"".join(bytes([t, o]) for t, o in kn) + b"".join(struct.pack("<II", g, o) for g, o in kw + extra)
    out = d[4:kt] + kt_bytes + bytes(rec_bytes)
    new = MAGIC + out + struct.pack("<I", zlib.crc32(out) & 0xFFFFFFFF)
    assert zlib.crc32(new[4:]) & 0xFFFFFFFF == 0x2144DF1C
    # verify: re-parse, old records byte-identical at their (new) absolute positions, new ones decode
    rn2, rw2, rb2 = tbl(new, 7); kt2 = rb2 + dict(rn2 + rw2)[1]; kn2, kw2, kb2 = tbl(new, kt2)
    assert (kn2 + kw2)[:len(kids)] == kids and kb2 - kt2 == len(kt_bytes)
    for k, o in kids:
        n_, w_, b1 = tbl(d, kb + o + 4); nxt = min([oo for _, oo in kids if oo > o] + [len(d) - 4 - kb])
        assert new[kb2 + o:kb2 + nxt] == d[kb + o:kb + nxt], f"record {k} moved/changed"
    for g, o in extra:
        n_, w_, b1 = tbl(new, kb2 + o + 4); f = dict(n_ + w_)
        assert struct.unpack_from("<I", new, b1 + f[3])[0] == g and new[b1 + f[6] + 1:b1 + f[6] + 1 + len(PATH)] == PATH
    print(f"  adding {len(new_recs)} records: ids {new_recs[0][0]}..{new_recs[-1][0]}, frames 0..{len(names) - 1}, "
          f"slots {dict((s, sum(1 for nm in names if nm.startswith(s))) for s in SLOT)}\n  new size {len(new)} B; CRC ok; existing {len(kids)} records byte-identical")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if not os.path.exists(bak):
        shutil.copy2(PFS, bak); print(f"  backup -> {bak}")
    open(PFS, "wb").write(new); print("applied.")


if __name__ == "__main__":
    main()
