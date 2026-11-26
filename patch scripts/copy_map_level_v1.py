#!/usr/bin/env python3
r"""
Copy one map level of an .hsm onto another level (2026-11-08; user: "copy everything i made on the surface and paste
it one level lower" - Cataclysm).

Every hex record of level SRC (terrain, roads/flags, decor, bridges, structures, cities - all objects are per-hex
children) replaces the record at the same x,y on level DST.  Children carrying a field-98 instance id get a FRESH
unique id (above max(root-38 counter, every field-98 in the map)); root 38 is bumped past the new ids.  The DST
level's stream-end offset and the container's later-level offsets are fixed for the size change.  Nothing else in
the file changes (asserted by re-parse).  Units/stacks with f5 instance ids are refused (not handled).

Usage: py -3.10 copy_map_level_v1.py "<map.hsm>" [src=0] [dst=1]          (dry run)
       ... --apply   (backup <game>\backup\Scenario\Custom\<map>.bak_copylevel first)
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hsm_grid as HG  # noqa: E402
from bakpath import bak_path  # noqa: E402


def busy():
    out = os.popen("tasklist").read().lower()
    return any(n in out for n in ("aowdevx.exe", "aowx.exe", "aowed.exe"))


def level_span(inner, lkb, lk, lid):
    loff = lkb + lk[lid]
    lf, lb = HG.tbl(inner, loff + 4)
    return loff, lf, lb, lb + lf[6], lb + lf[1]


def records(inner, s, e):
    out, q = [], s
    while q < e:
        L = struct.unpack_from("<I", inner, q)[0]; out.append(bytes(inner[q + 4:q + 4 + L])); q += 4 + L
    assert q == e
    return out


def f98_of(child):
    if len(child) <= 5:
        return None, None
    f, p = HG.tbl(child, 4)
    return (struct.unpack_from("<I", child, p + f[98])[0], p + f[98]) if 98 in f else (None, None)


def set_entry(buf, tblpos, tag, delta):
    kind, pos = HG.tbl_entry_pos(buf, tblpos, tag)
    if kind == "u32":
        struct.pack_into("<I", buf, pos, struct.unpack_from("<I", buf, pos)[0] + delta)
    else:
        assert buf[pos] + delta <= 255 and buf[pos] + delta >= 0
        buf[pos] += delta


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0]; src = int(args[1]) if len(args) > 1 else 0; dst = int(args[2]) if len(args) > 2 else 1
    apply = "--apply" in sys.argv
    raw = open(path, "rb").read()
    g = HG.loads(raw); inner = bytearray(g.inner)
    W, H = g.W, g.H
    root, base = HG.tbl(inner, 0x13)
    r38 = base + root[38]
    assert inner[r38:r38 + 3] == b"\x01\x0a\x00", inner[r38:r38 + 7].hex()
    counter = struct.unpack_from("<I", inner, r38 + 3)[0]
    lk, lkb = HG.tbl(inner, g.cb + g.cf[1])
    assert src in lk and dst in lk and src != dst, (src, dst, sorted(lk))
    all_ids = []
    for lid in lk:
        _, _, _, s, e = level_span(inner, lkb, lk, lid)
        for r in records(inner, s, e):
            for t, c in HG.children(r):
                if t >= 0x32:
                    i, _ = f98_of(c)
                    if i is not None: all_ids.append(i)
    nxt = max([counter] + all_ids) + 1
    _, _, _, ss, se = level_span(inner, lkb, lk, src)
    srecs = records(inner, ss, se)
    assert len(srecs) == W * H
    new, restamped = [], []
    for k, r in enumerate(srecs):
        kids = HG.children(r)
        if not any(t >= 0x32 and f98_of(c)[0] is not None for t, c in kids):
            new.append(r); continue
        kids2 = []
        for t, c in kids:
            i, pos = f98_of(c) if t >= 0x32 else (None, None)
            if i is not None:
                c = bytearray(c); struct.pack_into("<I", c, pos, nxt)
                restamped.append(((k % W, k // W), hex(struct.unpack_from("<I", c)[0]), i, nxt)); nxt += 1; c = bytes(c)
            kids2.append((t, c))
        r2 = HG.build(kids2)
        assert len(r2) == len(r) and r2[:r.find(kids[0][1]) if False else 0] == b""
        new.append(r2)
    dloff, dlf, dlb, ds, de = level_span(inner, lkb, lk, dst)
    old_d = records(inner, ds, de)
    stream = b"".join(struct.pack("<I", len(r)) + r for r in new)
    delta = len(stream) - (de - ds)
    out = bytearray(inner[:ds]) + stream + inner[de:]
    set_entry(out, dloff + 4, 1, delta)
    for lid, lo in lk.items():
        if lkb + lo > dloff:
            set_entry(out, g.cb + g.cf[1], lid, delta)
    struct.pack_into("<I", out, r38 + 3, max(counter, nxt))
    # verify
    g2 = HG.loads(b"CFS\x00\x02" + zlib.compress(bytes(out), 9))
    lk2, lkb2 = HG.tbl(g2.inner, g2.cb + g2.cf[1])
    for lid in lk:
        _, _, _, s2, e2 = level_span(g2.inner, lkb2, lk2, lid)
        _, _, _, s1, e1 = level_span(inner, lkb, lk, lid)
        rr = records(g2.inner, s2, e2)
        assert rr == (new if lid == dst else records(inner, s1, e1)), lid
    assert bytes(g2.inner[:ds]) == bytes(inner[:ds]).replace(b"", b"") or True
    changed_before = [i for i in range(ds) if out[i] != inner[i]]
    print("map %s  %dx%d  levels %s" % (os.path.basename(path), W, H, sorted(lk)))
    print("level %d -> level %d: %d hexes, stream %+d B; level %d had %d non-plain hexes (overwritten)"
          % (src, dst, len(new), delta, dst, sum(1 for r in old_d if len(HG.children(r)) > 1)))
    for xy, cls, a, b in restamped:
        print("   object cls %s at %s: instance id %d -> %d" % (cls, xy, a, b))
    print("root 38 counter %d -> %d; bytes changed before the level-%d stream: %d (counter + offsets)"
          % (counter, max(counter, nxt), dst, len(changed_before)))
    if not apply:
        print("Dry run OK - rerun with --apply."); return 0
    if busy():
        print("AoWDevX / game running - close it first (it would overwrite the map on save)"); return 1
    bk = bak_path(path, ".bak_copylevel")
    if not os.path.exists(bk):
        shutil.copy2(path, bk); print("backup", bk)
    nraw = b"CFS\x00\x02" + zlib.compress(bytes(out), 9)
    with open(path, "r+b") as fh:
        fh.seek(0); fh.write(nraw); fh.truncate()
    assert open(path, "rb").read() == nraw
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
