#!/usr/bin/env python3
"""
set_item_hpmv.py - list / edit the HP and MV bonuses of items in an AoW item
library (Release\\ITEMS.PFS or a User\\*.ail).  Companion of
patch_item_hpmv_use_v1.py (engine support: TItem +0x4A HP tag 0x17, +0x4B MV
tag 0x18 - same tags as BXL's Ziggurat, so libraries are interchangeable).

File format (TAoWDir tagged container, see camcodec.py): root node (3-byte
magic 01 00 00) -> field 0x01 = item list (0-byte magic) -> one record per
item (4-byte magic) with the TItem.ReadWrite tags: 7 gfx, 8 name (ShortString),
9 ?, 0x0A rarity, 0x0B atk, 0x0C def, 0x0D dam, 0x0E res, 0x0F type, 0x10 ?,
0x11 id, 0x12 abilities, 0x13 value, 0x14 spell, 0x15 lib id, 0x16 lib name,
0x17 HP, 0x18 MV.  Byte stats are 1-byte signed payloads; a zero stat is
simply absent (that is what the engine's writer does too).

Usage:
  py set_item_hpmv.py list [--file PATH] [--all]
  py set_item_hpmv.py set --name "Boots of Speed" --mv 2 [--hp 0] [--file PATH]
  py set_item_hpmv.py set --id 27 --hp 8
  py set_item_hpmv.py check [--file PATH]          # round-trip self-test only
Default --file: the 410 folder's Release\\ITEMS.PFS.  First write makes
PATH.bak_hpmv.  Item types: 0 head, 1 torso, 2 attack, 3 defense, 4 ring,
5 ?, 6 Use (grants from the backpack).
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_FILE = game_file(r"Release\ITEMS.PFS")
ROOT_MAGIC_LEN, LIST_MAGIC_LEN, REC_MAGIC_LEN = 3, 0, 4
T_GFX, T_NAME, T_RAR, T_ATK, T_DEF, T_DAM, T_RES, T_TYPE, T_ID, T_HP, T_MV = 7, 8, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x17, 0x18
STAT_TAGS = {T_ATK: "atk", T_DEF: "def", T_DAM: "dam", T_RES: "res", T_HP: "hp", T_MV: "mv"}

class Node:
    """entries: [id, form, payload, order]. Table order (= the writer's field
    order) and payload order (= 'order', the original offset) are independent:
    an item record's short table lists 2,3,0x31,7,8,... while the long table
    holds per-ability data records (ids >= 0x80) whose payload sits between
    field 0x31 and field 7.  Lengths therefore come from offsets sorted across
    BOTH tables."""
    def __init__(self, magic, entries): self.magic, self.entries = magic, entries
    def get(self, fid):
        for e in self.entries:
            if e[0] == fid: return e[2]
        return None

def parse_node(buf, magic_len):
    magic = buf[:magic_len]; o = magic_len
    c = buf[o]; o += 1
    nshort = c & 0x7F; nlong = 0
    if c & 0x80: nlong = struct.unpack_from("<I", buf, o)[0]; o += 4
    tbl = []
    for _ in range(nshort): tbl.append((buf[o], buf[o+1], 'S')); o += 2
    for _ in range(nlong):
        fid, off = struct.unpack_from("<ii", buf, o); o += 8; tbl.append((fid, off, 'L'))
    base = o
    starts = sorted(off for _, off, _ in tbl) + [len(buf) - base]
    entries = []
    for fid, off, form in tbl:
        end = starts[starts.index(off) + 1]
        entries.append([fid, form, bytes(buf[base+off:base+end]), off])
    return Node(bytes(magic), entries)

def build_node(node):
    """Rebuild byte-identically: payload laid out by 'order', tables in entry order."""
    layout = sorted(node.entries, key=lambda e: e[3])
    offs = {}; acc = 0
    for e in layout: offs[id(e)] = acc; acc += len(e[2])
    shorts = [(e[0], offs[id(e)]) for e in node.entries if e[1] == 'S']
    longs  = [(e[0], offs[id(e)]) for e in node.entries if e[1] == 'L']
    out = bytearray(node.magic)
    out.append(len(shorts) | (0x80 if longs else 0))
    if longs: out += struct.pack("<I", len(longs))
    for fid, o in shorts:
        assert 0 <= o < 0x100 and 0 <= fid < 0x80, f"short entry overflow (id {fid}, off {o})"
        out += bytes((fid, o))
    for fid, o in longs: out += struct.pack("<ii", fid, o)
    return bytes(out) + b"".join(e[2] for e in layout)

def sbyte(p): return struct.unpack("<b", p)[0] if p else 0
def rstr(p): return p[1:1+p[0]].decode("latin1") if p else ""
def rint(p): return struct.unpack_from("<i", p, 0)[0] if p else None

def load(path):
    data = open(path, "rb").read()
    root = parse_node(data, ROOT_MAGIC_LEN)
    lst_entry = next(e for e in root.entries if e[0] == 1)
    lst = parse_node(lst_entry[2], LIST_MAGIC_LEN)
    recs = [(le, parse_node(le[2], REC_MAGIC_LEN)) for le in lst.entries]
    return data, root, lst_entry, lst, recs

def save(path, root, lst_entry, lst, recs):
    for le, rec in recs: le[2] = build_node(rec)
    lst_entry[2] = build_node(lst)
    return build_node(root)

def set_stat(rec, tag, val):
    """Set a 1-byte signed stat; 0 removes the field (engine writer omits
    zero stats).  Placed where TItem.ReadWrite writes it: right after tag 0x15
    (or the last TItem tag < 0x17 present), both in the table and the payload."""
    rec.entries = [e for e in rec.entries if e[0] != tag]
    if val == 0: return
    assert -128 <= val <= 127, "stat out of signed-byte range"
    anchor = max((k for k, e in enumerate(rec.entries) if e[1] == 'S' and e[0] < tag and e[0] >= 7), default=None)
    assert anchor is not None, "record has no TItem fields"
    pos = anchor + 1
    order = rec.entries[anchor][3] + 0.5   # payload right after the anchor's payload
    rec.entries.insert(pos, [tag, 'S', struct.pack("<b", val), order])

def describe(rec):
    return {"id": rint(rec.get(T_ID)), "name": rstr(rec.get(T_NAME)), "type": (rec.get(T_TYPE) or b"\0")[0],
            **{nm: sbyte(rec.get(t)) for t, nm in STAT_TAGS.items()}}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("list", "set", "check"))
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--name"); ap.add_argument("--id", type=int)
    ap.add_argument("--hp", type=int); ap.add_argument("--mv", type=int)
    ap.add_argument("--all", action="store_true", help="list: show every item, not just those with HP/MV")
    a = ap.parse_args()
    data, root, lst_entry, lst, recs = load(a.file)
    rebuilt = save(a.file, root, lst_entry, lst, recs)
    if rebuilt != data:
        print(f"!! round-trip mismatch on {a.file} ({len(rebuilt)} vs {len(data)} bytes) - refusing to edit"); return 2
    if a.cmd == "check":
        print(f"round-trip OK: {len(recs)} items, {len(data)} bytes"); return 0
    if a.cmd == "list":
        print(f"{'id':>4} {'type':>4} {'atk':>4} {'def':>4} {'dam':>4} {'res':>4} {'hp':>4} {'mv':>4}  name")
        for le, rec in recs:
            d = describe(rec)
            if a.all or d["hp"] or d["mv"]:
                print(f"{str(d['id']):>4} {d['type']:>4} {d['atk']:>4} {d['def']:>4} {d['dam']:>4} {d['res']:>4} {d['hp']:>4} {d['mv']:>4}  {d['name']}")
        return 0
    # set
    if a.hp is None and a.mv is None: print("set: give --hp and/or --mv"); return 1
    hits = [(le, rec) for le, rec in recs
            if (a.id is not None and rint(rec.get(T_ID)) == a.id) or (a.name and rstr(rec.get(T_NAME)).lower() == a.name.lower())]
    if len(hits) != 1: print(f"set: matched {len(hits)} items (need exactly 1): {[describe(r)['name'] for _, r in hits]}"); return 1
    le, rec = hits[0]
    if a.hp is not None: set_stat(rec, T_HP, a.hp)
    if a.mv is not None: set_stat(rec, T_MV, a.mv)
    out = save(a.file, root, lst_entry, lst, recs)
    bak = a.file + ".bak_hpmv"
    if not os.path.exists(bak): shutil.copyfile(a.file, bak); print(f"Backup: {bak}")
    open(a.file, "wb").write(out)
    d = describe(rec); print(f"updated: {d}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
