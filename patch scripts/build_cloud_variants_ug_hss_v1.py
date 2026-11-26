#!/usr/bin/env python3
r"""
Underground copies of the poison-cloud variants (2026-11-13).

User: "we had added new elemental poison cloud variants. i want to be able to use them underground. they can be
added to the 'developer' tab rather than the 'object' tab since that one is full".

Release.hss: the four surface TPoisonCloudResource records (Sandstorm / Snowstorm / Holy Cloud / Death Cloud,
EditID 20 ObjectMOR, build_cloud_variants_hss_v1) are cloned with new unique ResourceIDs, EditID 44
(uDeveloperResourceGrid = the underground Developer tab) and EditIndex 16..19 (its empty row 4).  The vanilla
surface / underground Poison Cloud pair (children 331 / 706) differs only in ResourceID + EditID, so nothing else
changes; names stay the same -> patch_cloud_variants_v1 (variant = resource name) and the art (same ILBs) apply.
Records appended at the end of the children region exactly like the surface ones.
Backup backup\Release\Release.hss.bak_cloudug.  --revert restores it only while the file is still exactly our
output (a later hss patch on top -> revert that first).  Dry-run default; --apply; --revert.
"""
import os, random, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path  # noqa: E402
import build_cloud_variants_hss_v1 as C  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

HSS = C.HSS
TAG = ".bak_cloudug"
NAMES = ["Sandstorm", "Snowstorm", "Holy Cloud", "Death Cloud"]
SRC_EDIT, EDIT_ID, FIRST_IDX = 20, 44, 16
UID_SEED = 0xA0C1D1


def parse(b):
    root, rds = C.table(b, 0x37)
    f5 = [e for e in root if e[0] == 5][0][1]
    oe, ods = C.table(b, rds + f5)
    ctp = ods + [e for e in oe if e[0] == 1][0][1]
    ce, cbase = C.table(b, ctp)
    region_end = rds + min(o for i, o, k in root if o > f5)
    return root, rds, f5, ctp, ce, cbase, region_end


def fields(b, p):
    te, td = C.table(b, p + 4)
    return te, td, {x[0]: x[1] for x in te}


def info(b):
    """{child id: (class, rid, edit id, edit idx, name, record bytes)}"""
    root, rds, f5, ctp, ce, cbase, region_end = parse(b)
    starts = sorted(cbase + e[1] for e in ce) + [region_end]
    out = {}
    for e in ce:
        p = cbase + e[1]
        te, td, fo = fields(b, p)
        if not all(k in fo for k in (1, 2, 3)):
            continue
        nm = b[td + fo[6] + 1:td + fo[6] + 1 + b[td + fo[6]]].decode("latin1") if 6 in fo else ""
        out[e[0]] = (struct.unpack_from("<I", b, p)[0], struct.unpack_from("<I", b, td + fo[1])[0],
                     struct.unpack_from("<I", b, td + fo[2])[0], struct.unpack_from("<I", b, td + fo[3])[0], nm,
                     b[p:starts[starts.index(p) + 1]])
    return out


def build(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[:-4]) & 0xFFFFFFFF, "Release.hss CRC already bad"
    root, rds, f5, ctp, ce, cbase, region_end = parse(b)
    inf = info(b)
    used = {v[1] for v in inf.values()}
    taken = {v[3] for v in inf.values() if v[2] == EDIT_ID}
    rnd = random.Random(UID_SEED)
    recs = []
    for n, name in enumerate(NAMES):
        src = [v for v in inf.values() if v[0] == 0x21240 and v[2] == SRC_EDIT and v[4] == name]
        assert len(src) == 1, (name, len(src))
        assert not [v for v in inf.values() if v[0] == 0x21240 and v[2] == EDIT_ID and v[4] == name], "already there"
        r = bytearray(src[0][5])
        te, td, fo = fields(r, 0)
        while True:
            uid = rnd.randrange(1, 0x0FFFFFFF)
            if uid not in used:
                used.add(uid); break
        assert FIRST_IDX + n not in taken, "palette cell %d of page %d is occupied" % (FIRST_IDX + n, EDIT_ID)
        struct.pack_into("<I", r, td + fo[1], uid)
        struct.pack_into("<I", r, td + fo[2], EDIT_ID)
        struct.pack_into("<I", r, td + fo[3], FIRST_IDX + n)
        recs.append(bytes(r))
    ids = [e[0] for e in ce]
    new_ids = list(range(max(ids) + 1, max(ids) + 1 + len(recs)))
    rel = region_end - cbase
    for nid, r in zip(new_ids, recs):
        ce.append([nid, rel, "d"]); rel += len(r)
    new_ct = C.enc_table(ce)
    grow = len(new_ct) - (cbase - ctp)
    ins = b"".join(recs)
    out = bytearray(b[:ctp] + new_ct + b[cbase:region_end] + ins + b[region_end:-4])
    for x in root:
        if x[1] > f5:
            x[1] += grow + len(ins)
    rt = C.enc_table(root)
    assert len(rt) == rds - 0x37
    out[0x37:rds] = rt
    out += struct.pack("<I", zlib.crc32(bytes(out)) & 0xFFFFFFFF)
    out = bytes(out)
    # verify: every old child byte-identical, root fields after f5 identical, new ones as intended
    oi, ni = info(b), info(out)
    assert all(ni[k] == v for k, v in oi.items()), "old records changed"
    r0, d0 = C.table(b, 0x37)[0], C.table(b, 0x37)[1]
    r1, d1 = C.table(out, 0x37)[0], C.table(out, 0x37)[1]
    tail0 = sorted(o for i, o, k in r0 if o > f5)
    tail1 = sorted(o for i, o, k in r1 if o > f5)
    assert b[d0 + tail0[0]:-4] == out[d1 + tail1[0]:-4], "tail moved wrongly"
    for n, nid in enumerate(new_ids):
        v = ni[nid]
        assert v[0] == 0x21240 and v[2] == EDIT_ID and v[3] == FIRST_IDX + n and v[4] == NAMES[n]
    assert len({v[1] for v in ni.values()}) == len(ni), "duplicate ResourceID"
    return out, [(nid, ni[nid][4], hex(ni[nid][1]), ni[nid][3]) for nid in new_ids]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    b = open(HSS, "rb").read()
    bk = bak_path(HSS, TAG)
    have = [v for v in info(b).values() if v[0] == 0x21240 and v[2] == EDIT_ID]
    if revert:
        if not have:
            print("already reverted"); return 0
        old = open(bk, "rb").read()
        if build(old)[0] != b:
            print("ABORT: Release.hss changed since this patch (revert the later patch first)"); return 1
        if SP.busy():
            print("game/editor running - close it first"); return 1
        shutil.copy2(bk, HSS); print("reverted"); return 0
    if have:
        print("already applied (%s)" % ", ".join(sorted(v[4] for v in have))); return 0
    out, new = build(b)
    print("Release.hss %d -> %d B; new children (id, name, ResourceID, cell on page %d):" % (len(b), len(out), EDIT_ID))
    for r in new:
        print("   ", r)
    if not apply:
        print("Dry run OK - rerun with --apply."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    os.makedirs(os.path.dirname(bk), exist_ok=True)
    shutil.copy2(HSS, bk)
    with open(HSS, "wb") as fh:
        fh.write(out)
    assert open(HSS, "rb").read() == out
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
