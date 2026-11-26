#!/usr/bin/env python3
r"""
Append every item of a User\*.ail item library to the item list of selected .hsm maps (2026-09-23).

Default job: User\x2026.ail -> every Scenario\Custom\AoWx - *.hsm that already contains an item named
"Aegis of the Dawn" (= the maps that carry the xNew set; maps with their own unique item sets are skipped).
Existing map items are never touched or removed; library items whose NAME already exists in the map are skipped.

Map format (see memory hsm-map-format / aowx-item-hpmv): .hsm = 'CFS\0\x02' + zlib(inner); inner[0x10:] is the
THSMap root node (3-byte magic, tagged table).  Root tag 0x1E = the map's item list: a 0-magic list node whose
entries are keyed 9.. (key 9 = int32 "last assigned item id"; keys 10.. = TItem records, 4-byte magic 68 02 02 00,
TItem.ReadWrite tags).  Importing from a library the editor copies the .ail record verbatim except: tag 0x0A
(TItem+0x45, only read by TCity.Loot) is set to 0 and tag 0x11 = a fresh item id (last id + 1) is inserted before
tag 0x15.  This tool does the same; new list keys continue after the highest existing key; key 9 is bumped.
The root node is spliced, not rebuilt (the shared parser mis-sizes zero-length entries that share an offset);
only the root-table offsets after the item list move.  Backups <game>\backup\Scenario\Custom\<map>.bak_x2026items.
usage: py add_library_items_to_maps.py [--lib PATH] [--marker NAME] [--glob PATTERN] [--apply]
"""
import argparse, glob, os, shutil, struct, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bakpath import game_file, game_dir, bak_path   # noqa: E402
import set_item_hpmv as it                           # noqa: E402

T_ITEMLIST, K_LASTID, T_LOOT, T_ID, T_NAME = 0x1E, 9, 0x0A, 0x11, 8
REC_MAGIC = b"\x68\x02\x02\x00"


def root_table(inner):
    """Return (entries, table_end) for the root node at inner[0x10:]; entries = [tag, off, form, pos_of_off]."""
    o = 0x13; c = inner[o]; o += 1; nl = 0
    if c & 0x80:
        nl = struct.unpack_from("<I", inner, o)[0]; o += 4
    ents = []
    for _ in range(c & 0x7F):
        ents.append([inner[o], inner[o + 1], 'S', o + 1]); o += 2
    for _ in range(nl):
        t, off = struct.unpack_from("<ii", inner, o); ents.append([t, off, 'L', o + 4]); o += 8
    return ents, o


def item_list_span(inner):
    ents, base = root_table(inner)
    e = next(x for x in ents if x[0] == T_ITEMLIST)
    later = sorted(x[1] for x in ents if x[1] > e[1])
    end = base + (later[0] if later else len(inner) - base)
    return ents, base, base + e[1], end


def clone_for_map(rec, new_id):
    r = it.parse_node(it.build_node(rec), 4)             # deep copy
    for e in r.entries:
        if e[0] == T_LOOT:
            e[2] = b"\x00"
    r.entries = [e for e in r.entries if e[0] != T_ID]
    anchor = max((k for k, e in enumerate(r.entries) if e[1] == 'S' and 7 <= e[0] < T_ID), default=None)
    assert anchor is not None, "record without TItem fields"
    r.entries.insert(anchor + 1, [T_ID, 'S', struct.pack("<i", new_id), r.entries[anchor][3] + 0.5])
    return it.build_node(r)


def process(path, lib_recs, marker):
    raw = open(path, "rb").read(); assert raw[:5] == b"CFS\x00\x02", path
    inner = zlib.decompress(raw[5:])
    ents, base, ls, le = item_list_span(inner)
    lst = it.parse_node(inner[ls:le], 0)
    assert it.build_node(lst) == inner[ls:le], "item list does not round-trip"
    recs = {e[0]: it.parse_node(e[2], 4) for e in lst.entries if e[2][:4] == REC_MAGIC}
    names = {it.rstr(r.get(T_NAME)) for r in recs.values()}
    if marker not in names:
        return None
    k9 = next(e for e in lst.entries if e[0] == K_LASTID); last_id = it.rint(k9[2])
    assert last_id == max(it.rint(r.get(T_ID)) for r in recs.values() if r.get(T_ID)), "key 9 != max item id"
    key = max(e[0] for e in lst.entries); added, skipped = [], []
    for _, r in lib_recs:
        nm = it.rstr(r.get(T_NAME))
        if nm in names:
            skipped.append(nm); continue
        key += 1; last_id += 1
        lst.entries.append([key, 'L', clone_for_map(r, last_id), max(e[3] for e in lst.entries) + 1])
        names.add(nm); added.append(nm)
    k9[2] = struct.pack("<i", last_id)
    new_list = it.build_node(lst); delta = len(new_list) - (le - ls)
    out = bytearray(inner[:ls] + new_list + inner[le:])
    old_off = next(x for x in ents if x[0] == T_ITEMLIST)[1]
    for t, off, form, pos in ents:
        if off > old_off:
            assert form == 'L'; struct.pack_into("<i", out, pos, off + delta)
    # verify by re-reading
    ents2, base2, ls2, le2 = item_list_span(bytes(out)); lst2 = it.parse_node(bytes(out[ls2:le2]), 0)
    recs2 = [it.parse_node(e[2], 4) for e in lst2.entries if e[2][:4] == REC_MAGIC]
    assert len(recs2) == len(recs) + len(added) and it.rint(next(e for e in lst2.entries if e[0] == K_LASTID)[2]) == last_id
    assert [x[1] for x in ents2 if x[0] == T_ITEMLIST] == [old_off] and bytes(out[le2:]) == inner[le:] and bytes(out[base2:ls2]) == inner[base:ls]
    ids = [it.rint(r.get(T_ID)) for r in recs2 if r.get(T_ID)]; assert len(ids) == len(set(ids)), "duplicate item ids"
    return dict(added=added, skipped=skipped, before=len(recs), out=b"CFS\x00\x02" + zlib.compress(bytes(out), 9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default=game_file(r"User\x2026.ail"))
    ap.add_argument("--marker", default="Aegis of the Dawn")
    ap.add_argument("--glob", default=os.path.join(game_dir(), "Scenario", "Custom", "AoWx - *.hsm"))
    ap.add_argument("--suffix", default=".bak_x2026items")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    data, root, le, lst, lib_recs = it.load(a.lib)
    assert it.save(a.lib, root, le, lst, lib_recs) == data, "library does not round-trip"
    print(f"library {a.lib}: {len(lib_recs)} items")
    todo = []
    for path in sorted(glob.glob(a.glob)):
        res = process(path, lib_recs, a.marker)
        nm = os.path.basename(path)
        if res is None:
            print(f"  skip  {nm} (no '{a.marker}')"); continue
        print(f"  {'ADD' if res['added'] else 'none'}  {nm}: {res['before']} items, +{len(res['added'])}" + (f", already present {res['skipped']}" if res['skipped'] else ""))
        if res['added']:
            todo.append((path, res))
    if not a.apply:
        print(f"dry run - {len(todo)} maps would change (use --apply)"); return
    for path, res in todo:
        bak = bak_path(path, a.suffix)
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
        open(path, "wb").write(res['out'])
        chk = process(path, lib_recs, a.marker); assert chk is not None and not chk['added'], "post-write verification failed"
    print(f"applied to {len(todo)} maps; backups in {os.path.join(game_dir(), 'backup', 'Scenario', 'Custom')}")


if __name__ == "__main__":
    main()
