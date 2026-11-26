#!/usr/bin/env python3
r"""
Poison-cloud variants - data side (2026-10-30).  Code side: patch_cloud_variants_v1.py (variant = resource name).

1. Art: Images\Effects\SANDSTRM.ILB / SNOWSTRM.ILB / HOLYCLOD.ILB / DEATHCLD.ILB = recoloured PoisnCld.ILB
   (same 10 frames 320x480 type 22, blendValue 70): Death = multiply (drawMode 1026) dark violet; Sand/Snow/Holy =
   brighten (514) tan / pale blue-white / gold.  Built by make_art() from the vanilla ILB (density = how far a pixel
   is from white).
2. Release.hss: 4 TPoisonCloudResource records (class 0x21240) cloned from child 331 ("Poison Cloud", Surface):
   f1 new unique ResourceID, f2 EditID 20 (Surface > Objects grid "ObjectMOR"), f3 EditIndex 8/9/10/11 = the empty
   palette row 3 (user's request), f6 name, f9/f10 image file EFFECTS\POISNCLD.ILB -> the new ILB (same length).
   Appended as children 1143..1146 of the MOR owner (root field 5): children table +32 B (nd count +4), records
   placed at the end of the children region (= start of root field 6 data), root dword fields after field 5 shifted,
   CRC32 (last 4 bytes, zlib, checked by THSEngine.LoadHSS) recomputed.  The Pestilence Storm spell finds the FIRST
   0x21240 resource -> still Poison Cloud.  Not added underground (EditID 22) - ask if wanted.
Backup <game>\backup\Release\Release.hss.bak_cloudvar (+ the ILBs are new files; --revert deletes them).
Dry-run default; --apply; --revert; --art (rebuild only the 4 ILBs).  v4 10/30: 24-frame sequences + swirl art.
"""
import os, random, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

HSS = game_file("Release", "Release.hss")
FX = game_file("Images", "Effects")
SRC_ILB = os.path.join(FX, "PoisnCld.ILB")
SRC_CHILD = 331
OLD_IMG = b"EFFECTS\\POISNCLD.ILB"
VARIANTS = [  # name, ilb, edit index, mode, colour, strength
    ("Sandstorm", "SANDSTRM.ILB", 8, "add", (170, 125, 60), 0.85),
    ("Snowstorm", "SNOWSTRM.ILB", 9, "add", (190, 210, 240), 0.8),
    ("Holy Cloud", "HOLYCLOD.ILB", 10, "add", (240, 200, 95), 0.8),
    ("Death Cloud", "DEATHCLD.ILB", 11, "mul", (70, 30, 85), 1.0),
]
EDIT_ID = 20
FRAMES = 48                               # sequence length per variant (vanilla cloud has 10)
UNIQUE = 48                               # unique ILB images (v11 tried 24 = each shown twice; user: looked bad, reverted)
SEQ = [i * UNIQUE // FRAMES for i in range(FRAMES)]
UID_SEED = 0xA0C1D0                       # deterministic ResourceIDs


def table(b, p):
    t = b[p]; p += 1; nd = 0
    if t & 0x80:
        nd = struct.unpack_from("<I", b, p)[0]; p += 4
    ents = []
    for _ in range(t & 0x7F):
        ents.append([b[p], b[p + 1], "b"]); p += 2
    for _ in range(nd):
        i, o = struct.unpack_from("<II", b, p); ents.append([i, o, "d"]); p += 8
    return ents, p


def enc_table(ents):
    for e in ents:                                  # byte entries whose offset/id no longer fits -> dword form
        if e[2] == "b" and (e[1] > 255 or e[0] > 255):
            e[2] = "d"
    bt = [e for e in ents if e[2] == "b"]; dt = [e for e in ents if e[2] == "d"]
    out = bytearray([len(bt) | (0x80 if dt else 0)])
    if dt:
        out += struct.pack("<I", len(dt))
    for i, o, _ in bt:
        out += bytes([i, o])
    for i, o, _ in dt:
        out += struct.pack("<II", i, o)
    return bytes(out)


def make_art():
    """v3 art (cloud_variant_art.py): 2-layer composites (multiply 1026 + additive 770) per frame."""
    sys.path.insert(0, game_file("modding tools"))
    from aowxlib import ilb
    import cloud_variant_art as A
    keys = {"SANDSTRM.ILB": "sand", "SNOWSTRM.ILB": "snow", "HOLYCLOD.ILB": "holy", "DEATHCLD.ILB": "death"}
    out = {}
    for _, fn, *_ in VARIANTS:
        lib = ilb.read(SRC_ILB)
        while len(lib.images) < UNIQUE:                     # vanilla layout has 10 images -> FRAMES
            src_img = lib.images[0]
            lib.images.append(ilb.Image(len(lib.images), [ilb.Record(dict(src_img.primary))], False))
        A.to_ilb(lib, ilb, A.render(keys[fn]))
        out[fn] = ilb.write(lib)
    return out


def build(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[:-4]) & 0xFFFFFFFF, "Release.hss CRC already bad"
    root, rds = table(b, 0x37)
    f5 = [e for e in root if e[0] == 5][0][1]
    own = rds + f5
    oe, ods = table(b, own)
    ctp = ods + [e for e in oe if e[0] == 1][0][1]
    ce, cbase = table(b, ctp)
    ids = {e[0] for e in ce}
    nxt_root = min(o for i, o, k in root if o > f5)          # first root field after field 5
    region_end = rds + nxt_root
    # source record
    so = [e for e in ce if e[0] == SRC_CHILD][0][1]
    sp = cbase + so
    starts = sorted(cbase + e[1] for e in ce)
    send = starts[starts.index(sp) + 1]
    src = b[sp:send]
    assert struct.unpack_from("<I", src, 0)[0] == 0x21240 and src.count(OLD_IMG) == 1
    # existing ResourceIDs
    used = set()
    for e in ce:
        p = cbase + e[1]
        te, td = table(b, p + 4)
        f1 = [x for x in te if x[0] == 1]
        if f1:
            used.add(struct.unpack_from("<I", b, td + f1[0][1])[0])
    rnd = random.Random(UID_SEED)
    recs = []
    for name, fn, idx, *_ in VARIANTS:
        te, td = table(src, 4)
        data = bytearray(src[td:])
        fo = {x[0]: x[1] for x in te}
        while True:
            uid = rnd.randrange(1, 0x0FFFFFFF)
            if uid not in used:
                used.add(uid); break
        struct.pack_into("<I", data, fo[1], uid)
        struct.pack_into("<I", data, fo[2], EDIT_ID)
        struct.pack_into("<I", data, fo[3], idx)
        old_len = data[fo[6]]
        nm = name.encode("latin1")
        data[fo[6]:fo[6] + 1 + old_len] = bytes([len(nm)]) + nm
        delta = len(nm) - old_len
        for x in te:
            if x[1] > fo[6]:
                x[1] += delta
        img = ("EFFECTS\\" + fn).encode()
        assert len(img) == len(OLD_IMG)
        data = bytearray(bytes(data).replace(OLD_IMG, img))
        # frame list (TImageSequence mode 4): name, u8 0, u8 2, u8 mode 4, i32 frame, i32 x, i32 y, u32 0, u32 n, n*u32
        k = data.index(img) + len(img)
        assert data[k:k + 3] == bytes([0, 2, 4]), data[k:k + 3].hex()
        npos = k + 3 + 12 + 4
        n_old = struct.unpack_from('<I', data, npos)[0]
        assert n_old == 10 and list(struct.unpack_from('<10I', data, npos + 4)) == list(range(10))
        data[npos:npos + 4 + 4 * n_old] = struct.pack('<I', FRAMES) + b''.join(struct.pack('<I', i) for i in SEQ)
        fdelta = 4 * (FRAMES - n_old)
        f9 = [x[1] for x in te if x[0] == 9][0]
        for x in te:
            if x[1] > f9:
                x[1] += fdelta
        data = bytes(data)
        recs.append(src[:4] + enc_table(te) + data)
    # children table: + 4 dword entries (offsets relative to the new children base = table end)
    new_ids = list(range(max(ids) + 1, max(ids) + 1 + len(recs)))
    rel = region_end - cbase
    for nid, r in zip(new_ids, recs):
        ce.append([nid, rel, "d"]); rel += len(r)
    new_ct = enc_table(ce)
    grow_tab = len(new_ct) - (cbase - ctp)
    ins = b"".join(recs)
    out = bytearray(b[:ctp] + new_ct + b[cbase:region_end] + ins + b[region_end:-4])
    # root fields after field 5 shift by everything inserted
    shift = grow_tab + len(ins)
    for x in root:
        if x[1] > f5:
            x[1] += shift
    rt = enc_table(root)
    assert len(rt) == rds - 0x37
    out[0x37:rds] = rt
    out += struct.pack("<I", zlib.crc32(bytes(out)) & 0xFFFFFFFF)
    return bytes(out), new_ids


def verify(nb, new_ids):
    root, rds = table(nb, 0x37)
    f5 = [e for e in root if e[0] == 5][0][1]
    oe, ods = table(nb, rds + f5)
    ce, cbase = table(nb, ods + [e for e in oe if e[0] == 1][0][1])
    names = {}
    for e in ce:
        if e[0] in new_ids:
            p = cbase + e[1]
            te, td = table(nb, p + 4)
            fo = {x[0]: x[1] for x in te}
            n = nb[td + fo[6] + 1:td + fo[6] + 1 + nb[td + fo[6]]].decode()
            names[e[0]] = (n, struct.unpack_from("<I", nb, td + fo[2])[0], struct.unpack_from("<I", nb, td + fo[3])[0])
    # root fields after f5 must still point at the same bytes as before (checked by caller)
    return names


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    b = open(HSS, "rb").read()
    bak = bak_path(HSS, ".bak_cloudvar")
    has = b"SANDSTRM.ILB" in b
    print("Release.hss %d B, variants %s" % (len(b), "PRESENT" if has else "absent"))
    if revert:
        if not has:
            print("already reverted"); return 0
        r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
        if "AoWx.exe" in r or "AoWDevX.exe" in r:
            print("game/editor running - close it first"); return 1
        shutil.copy2(bak, HSS)
        for _, fn, *_ in VARIANTS:
            p = os.path.join(FX, fn)
            if os.path.exists(p):
                os.remove(p)
        print("restored", bak); return 0
    if has:
        if "--art" in sys.argv:
            r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
            if "AoWx.exe" in r or "AoWDevX.exe" in r:
                print("game/editor running - close it first"); return 1
            for fn, data in make_art().items():
                with open(os.path.join(FX, fn), "wb") as f:
                    f.write(data)
                print("rewrote", fn, len(data))
            return 0
        print("already applied (use --art to rebuild only the ILBs)"); return 0
    nb, new_ids = build(b)
    names = verify(nb, new_ids)
    # old root lists still at the same content
    root0, rds0 = table(b, 0x37); root1, rds1 = table(nb, 0x37)
    for (i0, o0, _), (i1, o1, _) in zip(root0, root1):
        assert i0 == i1
        if i0 in (6, 7, 0xA, 0xB, 0x11, 0x12):
            assert b[rds0 + o0:rds0 + o0 + 16] == nb[rds1 + o1:rds1 + o1 + 16], hex(i0)
    print("new children", names, "| size %d -> %d" % (len(b), len(nb)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    art = make_art()
    if not os.path.exists(bak):
        shutil.copy2(HSS, bak); print("backup ->", bak)
    for fn, data in art.items():
        with open(os.path.join(FX, fn), "wb") as f:
            f.write(data)
        print("wrote", fn, len(data))
    with open(HSS, "wb") as f:
        f.write(nb)
    chk = open(HSS, "rb").read()
    assert chk == nb and struct.unpack("<I", chk[-4:])[0] == zlib.crc32(chk[:-4]) & 0xFFFFFFFF
    print("Release.hss written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
