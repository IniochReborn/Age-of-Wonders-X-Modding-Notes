#!/usr/bin/env python3
r"""
Release.hss: Ziggurat-map compatibility aliases (2026-11-07).

User: "im trying to open the map 'Highpass (Rockfeller_Route).hsm' which was made with ziggurat mod. it crashes with a
bunch of errors when i try to open it in the editor".

Offline scan of the map (every level's hex stream, all object children, unit type indices, classes) against our and
Ziggurat's Release.hss: the ONLY unresolved reference is resource 0x06023E87 x2 (level 1 at (32,12) and (19,71)) =
Ziggurat's UNDERGROUND Ziggurat (their child 701, class 0x2038F, palette page 23 cell 41).  build_underground_structures_
hss_v1 copied that record into ours under a new id 0x5A1A0001, so Ziggurat maps lose both pyramids; a dropped structure
leaves its structure-list entry behind -> the crash after the error dialogs.
Fix: append a copy of OUR record 0x5A1A0001 with ResourceID 0x06023E87 and NO palette fields (EditID / EditIndex
removed - Ziggurat ships such a palette-less record itself, child 1109; ours had none, so it cannot collide with
another (0,0) entry) -> Ziggurat maps load their underground Ziggurats, the palette is unchanged.
Backup <game>\backup\Release\Release.hss.bak_zigalias (restored by --revert).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402

# v2 (user: "redo the fix, except this time keep my defender list, not his"): v1 copied our 0x5A1A0001 record, which is
# Ziggurat's child 701 verbatim incl. HIS defender groups (field 25).  The alias now takes field 25 from OUR surface
# Ziggurat 0x04870B74 (the user's edited guard list; the only content field that differs from Ziggurat's).
ALIASES = [(0x5A1A0001, 0x06023E87, "underground Ziggurat (Ziggurat child 701)")]
GUARDS_FROM, GUARD_FIELD = 0x04870B74, 25
TAG = ".bak_zigalias"


def rid(r):
    fo, td = H.fields(r)
    return struct.unpack_from("<I", r, td + fo[1])[0] if 1 in fo else None


def fdata(rec):
    ents, td = H.table(rec, 4)
    items = sorted([(e[0], e[1]) for e in ents], key=lambda t: t[1])
    out = {}
    for j, (t, o) in enumerate(items):
        e = td + items[j + 1][1] if j + 1 < len(items) else len(rec)
        out[t] = bytes(rec[td + o:e])
    return [t for t, _o in items], out


def alias_rec(src, new_rid, guards):
    order, data = fdata(src)
    data[GUARD_FIELD] = guards
    order = [t for t in order if t not in (2, 3)]
    ents, body = [], bytearray()
    for t in order:
        ents.append([t, len(body), "b"]); body += data[t]
    r = bytearray(src[:4] + H.enc_table(ents) + body)
    fo, td2 = H.fields(r)
    assert 2 not in fo and 3 not in fo
    struct.pack_into("<I", r, td2 + fo[1], new_rid)
    _o2, d2 = fdata(r)
    assert d2[GUARD_FIELD] == guards and all(d2[t] == data[t] for t in order if t != 1)
    return bytes(r)


def build(b):
    A = H.parse(b)
    by_rid = {rid(r): k for k, r in A["recs"].items()}
    have = [new in by_rid for _o, new, _n in ALIASES]
    if all(have):
        return None, []
    assert not any(have), "partially applied"
    assert not any(H.u32(r, 2) is None for r in A["recs"].values()), "a palette-less record already exists"
    guards = fdata(bytes(A["recs"][by_rid[GUARDS_FROM]]))[1][GUARD_FIELD]
    new = [alias_rec(bytes(A["recs"][by_rid[old]]), nr, guards) for old, nr, _n in ALIASES]
    nxt = max(A["recs"]) + 1
    for k, rec in enumerate(new):
        A["recs"][nxt + k] = bytearray(rec)
        A["order"].append(nxt + k)
        A["ce"].append([nxt + k, 0, "d"])
    region = bytearray(); offs = {}
    for cid in A["order"]:
        offs[cid] = len(region); region += A["recs"][cid]
    for e in A["ce"]:
        e[1] = offs[e[0]]
    ct = H.enc_table(A["ce"])
    shift_tbl = len(ct) - (A["cbase"] - A["ctp"])
    growth = len(region) - (A["region_end"] - A["cbase"]) + shift_tbl
    nb = bytearray(b[:A["ctp"]] + ct + region + b[A["region_end"]:-4])
    root = A["root"]
    for x in root:
        if x[1] > A["f5"]:
            x[1] += growth
    rt = H.enc_table(root); assert len(rt) == A["rds"] - 0x37
    nb[0x37:A["rds"]] = rt
    if shift_tbl:
        oe, ods = H.table(nb, A["rds"] + A["f5"])
        for x in oe:
            if x[1] > [e for e in oe if e[0] == 1][0][1]:
                x[1] += shift_tbl
        ot = H.enc_table(oe)
        st = A["rds"] + A["f5"]
        assert len(ot) == ods - st
        nb[st:ods] = ot
    nb += struct.pack("<I", zlib.crc32(bytes(nb)) & 0xFFFFFFFF)
    N = H.parse(bytes(nb))
    assert bytes(nb[N["region_end"]:-4]) == b[A["region_end"]:-4], "tail moved wrongly"
    for k, rec in enumerate(new):
        assert bytes(N["recs"][nxt + k]) == rec
    assert {c: bytes(v) for c, v in N["recs"].items() if c < nxt} == \
           {c: bytes(v) for c, v in H.parse(b)["recs"].items()}
    return bytes(nb), [nxt + k for k in range(len(new))]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(H.OURS, TAG)
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    busy = "AoWx.exe" in r or "AoWDevX.exe" in r
    if revert:
        if busy:
            print("game/editor running - close it first"); return 1
        if os.path.exists(bak):
            shutil.copy2(bak, H.OURS); print("restored", bak)
        return 0
    b = open(H.OURS, "rb").read()
    nb, kids = build(b)
    if nb is None:
        print("already applied"); return 0
    for (old, new, name), k in zip(ALIASES, kids):
        print("alias child %d: %#010x -> %#010x  %s" % (k, old, new, name))
    print("Release.hss %d -> %d B" % (len(b), len(nb)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if busy:
        print("game/editor running - close it first"); return 1
    if not os.path.exists(bak):
        shutil.copy2(H.OURS, bak)
    with open(H.OURS, "r+b") as f:
        f.write(nb); f.truncate()
    assert open(H.OURS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
