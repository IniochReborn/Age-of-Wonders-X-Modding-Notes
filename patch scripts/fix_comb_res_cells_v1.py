#!/usr/bin/env python3
r"""
comb_res.pfs: give every cloned record its OWN editor palette cell (2026-11-04).

User: "i regularly make changes in AoWDevX, so we will need to fix this so it stops happening".
Every AoWDevX data save re-writes all Release files; the editor's palette keeps ONE resource per (page, cell)
(record field 2 = page / EditID, field 3 = cell / EditIndex) and drops the rest, so the next save loses them
(11/02 and again 11/04: water combat hexagon 0x5A8502 + node centre structure 0x15F5B08 vanished -> water-node battles
on grass with flashing hexes).  Collisions (live 11/04):
    page 34 cell 6 : 0x5A8502 water combat hexagon (vanilla)  + 0xAA0E01 Sky clone  + 0xAA0B01 Chasm clone
    page 38 cell 1 : 0x15F5B08 node centre structure (vanilla) + 0xE1608C Eagle's Nest clone
Fix (u32 rewrite in place, sizes unchanged): Sky -> page 34 cell 2, Chasm -> 34 cell 3, Nest -> 38 cell 5
(all verified free).  The 10/31 editor crash came from a THIRD Sky clone existing (it crashed on any cell) - not from
giving a clone its own cell.  Run repair_comb_res_v1 first if records are missing (this script refuses then).
Backup <game>\backup\Release\comb_res.pfs.bak_cells1.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.argv, _args = sys.argv[:1], sys.argv[1:]
import repair_comb_res_v1 as R  # noqa: E402
import build_sky_chasm_combat_v1 as SC  # noqa: E402
from bakpath import bak_path  # noqa: E402

H = SC.H
MOVES = {0xAA0E01: (34, 6, 2), 0xAA0B01: (34, 6, 3), 0xE1608C: (38, 1, 5)}   # rid: (page, old cell, new cell)


def plan(b):
    order, d = R.by_rid(b)
    assert len(order) == 584 and 0x5A8502 in d and 0x15F5B08 in d, \
        "comb_res is missing records - run repair_comb_res_v1.py --apply first"
    used = {}
    for k in order:
        used.setdefault((H.u32(d[k], 2), H.u32(d[k], 3) or 0), []).append(k)
    ce, cbase, recs = SC.pfs_records(b)
    pos = {}
    for c in sorted(recs):
        s, t = recs[c]
        r = b[s:t]
        fo, td = H.fields(r)
        if 1 in fo and struct.unpack_from("<I", r, td + fo[1])[0] in MOVES:
            assert 3 in fo
            pos[struct.unpack_from("<I", r, td + fo[1])[0]] = s + td + fo[3]
    state = []
    for rid, (page, old, new) in MOVES.items():
        rec = d[rid]
        assert H.u32(rec, 2) == page, hex(rid)
        cur = H.u32(rec, 3)
        if cur == new:
            state.append("ours")
        elif cur == old:
            others = [k for k in used.get((page, new), []) if k != rid]
            assert not others, ("target cell taken", hex(rid), [hex(k) for k in others])
            state.append("vanilla")
        else:
            state.append("OTHER")
    return pos, state


def write(b, pos, to_new):
    out = bytearray(b)
    for rid, (page, old, new) in MOVES.items():
        struct.pack_into("<I", out, pos[rid], new if to_new else old)
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    return bytes(out)


def main():
    apply = "--apply" in _args; revert = "--revert" in _args
    b = open(R.PFS, "rb").read()
    pos, state = plan(b)
    print("cells:", dict(zip([hex(k) for k in MOVES], state)))
    if "OTHER" in state or len(set(state)) != 1:
        print("ABORT"); return 1
    if revert:
        if state[0] == "ours":
            nb = write(b, pos, False)
            open(R.PFS, "r+b").write(nb); print("reverted")
        return 0
    if state[0] == "ours":
        print("already applied"); return 0
    nb = write(b, pos, True)
    _, st2 = plan(nb)
    assert st2 == ["ours"] * 3
    o1, d1 = R.by_rid(b); o2, d2 = R.by_rid(nb)
    assert o1 == o2 and all(d1[k] == d2[k] for k in o1 if k not in MOVES)
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if R.SC.running() if hasattr(R.SC, "running") else False:
        print("game/editor running - close it first"); return 1
    bk = bak_path(R.PFS, ".bak_cells1")
    if not os.path.exists(bk):
        shutil.copy2(R.PFS, bk)
    with open(R.PFS, "r+b") as f:
        f.write(nb); f.truncate()
    assert open(R.PFS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
