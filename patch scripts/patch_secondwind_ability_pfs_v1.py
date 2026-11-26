#!/usr/bin/env python3
r"""Release\Ability.pfs: the record for ability 0xBF 'Second Wind' (2026-10-16, Second Wind v3; registered by
patch_secondwind_v1.py v3's reg cave as a combat-only TDurationAbility, granted by the Second Wind spell 310 to its
target - a pure marker: the unit cannot be given a second wind again this combat).  Recipe = patch_chorus_ability_pfs_v1.py:
record key = id + 10 = 201, tags 5/7/8/9 (selection 0 = not learnable); the NAME comes from the reg cave (mode 3
appends "(combat only)").
--apply  appends 201 (only if absent; it must be the largest key - 200 Heavenly Chorus must already be present).
--revert removes ONLY record 201.  One-time safety copy <game>\backup\Release\Ability.pfs.bak_secondwind.  Dry-run default.
After applying: append 0xBF to LADDER in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py
(bound 0xBF -> 0xC0) and re-run both.
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_secondwind"
RECORDS = [   # (ability id, description)
    (0xBF, "Second Wind: this unit has received a second wind."),
]


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


def assemble(raw, payload, pre, smalls, wides, body):
    out = bytearray(payload[:pre]) + bytes([0x80 | len(smalls)]) + struct.pack("<I", len(wides))
    for t, o in smalls: out += bytes([t, o])
    for i, o in wides: out += struct.pack("<II", i, o)
    out += body
    return raw[:4] + bytes(out) + struct.pack("<I", zlib.crc32(bytes(out)) & 0xFFFFFFFF)


def load(raw):
    payload = raw[4:-4]
    assert zlib.crc32(payload) & 0xFFFFFFFF == struct.unpack_from("<I", raw, len(raw) - 4)[0], "pfs CRC invalid"
    pre, small, wide, smalls, wides, dend = parse_top(payload)
    return payload, pre, smalls, wides, bytes(payload[dend:])


def remove(raw, key):
    payload, pre, smalls, wides, body = load(raw)
    off = dict(wides)[key]
    later = sorted(o for _i, o in list(wides) + [(t, o) for t, o in smalls] if o > off)
    end = later[0] if later else len(body)
    cut = end - off
    new_wides = [(i, o - cut if o > off else o) for i, o in wides if i != key]
    new_smalls = [(t, o - cut if o > off else o) for t, o in smalls]
    new = assemble(raw, payload, pre, new_smalls, new_wides, body[:off] + body[end:])
    assert key not in [i for i, _ in parse_top(new[4:-4])[4]]
    return new


def rec_of(raw, key):
    payload, pre, smalls, wides, body = load(raw)
    offs = sorted(o for _i, o in wides); off = dict(wides)[key]
    nxt = [o for o in offs if o > off]
    return body[off:nxt[0] if nxt else len(body)]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    raw = open(PFS, "rb").read(); raw0 = raw
    payload, pre, smalls, wides, body = load(raw)
    keys = [i for i, _ in smalls] + [i for i, _ in wides]
    print("Ability.pfs: %d records, highest key %d (id %#x) | %s" % (len(keys), max(keys), max(keys) - 10,
          ", ".join("%d (id %#x) %s" % (a + 10, a, "PRESENT" if a + 10 in keys else "absent") for a, _d in RECORDS)))
    if revert:
        for a, _d in reversed(RECORDS):
            if a + 10 in [i for i, _ in load(raw)[3]]: raw = remove(raw, a + 10); print("record %d removed" % (a + 10))
        if raw == raw0: print("nothing to revert"); return 0
        open(PFS, "wb").write(raw); print("%d -> %d bytes" % (len(raw0), len(raw))); return 0
    for a, desc in RECORDS:
        key = a + 10; rec = build_record(desc)
        payload, pre, smalls, wides, body = load(raw); keys = [i for i, _ in smalls] + [i for i, _ in wides]
        if key in keys:
            if rec_of(raw, key) == rec: print("record %d already applied" % key); continue
            assert all(k <= RECORDS[-1][0] + 10 for k in keys), "record %d is followed by foreign keys - cannot rewrite in place" % key
            print("record %d present with OLDER text -> rewriting" % key)
            for a2, _d2 in reversed(RECORDS):                                     # drop ours from this key upward, re-append below
                if a2 >= a and a2 + 10 in [i for i, _ in load(raw)[3]]: raw = remove(raw, a2 + 10)
            payload, pre, smalls, wides, body = load(raw); keys = [i for i, _ in smalls] + [i for i, _ in wides]
        assert wides and max(keys) < key, "record %d must be the largest key (highest is %d)" % (key, max(keys))
        raw = assemble(raw, payload, pre, smalls, list(wides) + [(key, len(body))], body + rec)
        assert max(i for i, _ in parse_top(raw[4:-4])[4]) == key
        print("would append record %d (%d B): %r" % (key, len(rec), desc))
    if raw == raw0: print("already applied"); return 0
    load(raw); print("%d -> %d bytes (CRC ok)" % (len(raw0), len(raw)))
    if not apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if not os.path.exists(b): shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
