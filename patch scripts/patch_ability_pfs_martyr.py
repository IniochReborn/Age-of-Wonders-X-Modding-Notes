#!/usr/bin/env python3
r"""
Release\Ability.pfs: the record for the Martyr ability 0xB0 (2026-10-13, see patch_martyr_cleansing_v1.py).

Record key = id + 10 = 186, appended as the largest id (same append recipe as patch_ability_pfs_castercost.py:
+1 wide index entry, body at the payload tail, existing offsets untouched, re-CRC).  Body tags: 5 = description,
7 = 01 01 00 00, 8 = 0, 9 = selection mask 0 (not learnable, not assignable - it is a spell effect).  No tag 6 (no
skill-point cost).  After applying re-run patch_tcablist_ceiling_v1.py and patch_aowx_banner_ceilings_v1.py (their
id ceiling = highest pfs id + 1).
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_martyr"
ABILITIES = [(0xB0, "Martyr: +2 attack, +2 defense, +2 damage and +2 resistance for the rest of the combat. "
                    "The martyr dies when the combat ends.")]


def build_record(desc):
    data = bytearray(); offs = {}
    offs[5] = len(data); data += struct.pack("<I", len(desc)) + desc.encode("latin-1")
    offs[7] = len(data); data += bytes([1, 1, 0, 0])
    offs[8] = len(data); data += bytes(4)
    offs[9] = len(data); data += struct.pack("<H", 0)
    assert all(o <= 0xFF for o in offs.values()), offs
    hdr = bytes([4])
    for t in (5, 7, 8, 9): hdr += bytes([t, offs[t]])
    return hdr + bytes(data)


def parse_top(payload):
    for pre in range(0, 9):
        p = pre; n = payload[p]; p += 1
        small = n & 0x7F; wide = 0
        if n & 0x80:
            if p + 4 > len(payload): continue
            wide = struct.unpack_from("<I", payload, p)[0]; p += 4
        if not (0 < small + wide < 2000): continue
        if p + 2 * small + 8 * wide > len(payload): continue
        smalls = [(payload[p + 2 * k], payload[p + 2 * k + 1]) for k in range(small)]
        p2 = p + 2 * small
        wides = [struct.unpack_from("<II", payload, p2 + 8 * k) for k in range(wide)]
        p2 += 8 * wide
        ids = [i for i, _ in smalls] + [i for i, _ in wides]
        if len(ids) > 3 and all(ids[k] < ids[k + 1] for k in range(len(ids) - 1)):
            return pre, small, wide, smalls, wides, p2
    raise ValueError("could not locate top index")


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    bak = bak_path(PFS, BAK_SUFFIX, create=False)
    if revert:
        if os.path.isfile(bak): shutil.copy2(bak, PFS); print("Ability.pfs restored from", bak)
        else: print("no backup found")
        return 0
    raw = open(PFS, "rb").read()
    payload = raw[4:-4]
    assert zlib.crc32(payload) & 0xFFFFFFFF == struct.unpack_from("<I", raw, len(raw) - 4)[0], "source pfs CRC invalid"
    pre, small, wide, smalls, wides, dend = parse_top(payload)
    ids = [i for i, _ in smalls] + [i for i, _ in wides]
    have = [i for i, _d in ABILITIES if (i + 10) in ids]
    print("Ability.pfs: %d records, highest id %#x" % (len(ids), max(ids) - 10))
    if have:
        print("already present: %s" % [hex(h) for h in have]); return 0
    assert wide > 0 and max(ids) < ABILITIES[0][0] + 10, "new ids must be the largest"
    tail_off = len(payload) - dend
    new_wides, new_bodies = [], bytearray()
    for aid, desc in ABILITIES:
        rec = build_record(desc); new_wides.append((aid + 10, tail_off + len(new_bodies))); new_bodies += rec
    out = bytearray(payload[:pre]) + bytes([0x80 | small]) + struct.pack("<I", wide + len(new_wides))
    for t, o in smalls: out += bytes([t, o])
    for i, o in wides: out += struct.pack("<II", i, o)
    for i, o in new_wides: out += struct.pack("<II", i, o)
    out += payload[dend:] + new_bodies
    new = raw[:4] + bytes(out) + struct.pack("<I", zlib.crc32(bytes(out)) & 0xFFFFFFFF)
    p2 = parse_top(new[4:-4]); assert (p2[5] and max(i for i, _ in p2[4]) == ABILITIES[-1][0] + 10)
    print("would append %d record(s): %s (%d -> %d bytes)" % (len(ABILITIES), [hex(a) for a, _ in ABILITIES], len(raw), len(new)))
    if not apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if not os.path.exists(b): shutil.copy2(PFS, b); print("backup ->", b)
    open(PFS, "wb").write(new); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
