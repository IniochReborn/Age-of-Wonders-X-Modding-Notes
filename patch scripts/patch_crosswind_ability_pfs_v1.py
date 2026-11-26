#!/usr/bin/env python3
r"""Release\Ability.pfs: the record for ability 0xC2 'Crosswind' (2026-10-16, Crosswind 213; registered by
patch_crosswind_v1.py's reg cave as a third TBurningAbility instance = combat-only, counts down 3 combat rounds;
GetAttackRA lowers the holder's ranged ATK by 2).  Recipe = patch_undying_ability_pfs_v1.py: record key = id + 10 = 204,
tags 5/7/8/9.  --apply appends 204 (only if absent; it must be the largest key - 203 Undying must already be present).
--revert removes ONLY record 204.  One-time safety copy <game>ackup\Release\Ability.pfs.bak_crosswind.  Dry-run
default.  --pfs <copy> works on a scratch copy.
After applying: append 0xC2 to LADDER in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py
(bound 0xC2 -> 0xC3) and re-run both.
v2 2026-10-16 (user: an enchantment aura on units with Crosswind, like Suspended's spinning particles but shorter):
tag 8 = the 'Crosswind' STATUS OVERLAY (drawn through patch_tc_suspend_overlay_v1.py v3's overlay table, which now
lists 0xC2): DualDF 3550-3597 (xwind_status, 48x80 additive 770: 5 small white motes spiralling up to half the unit's
height over a faint air tint), xs -23 / ys -56, f20 = 4 ticks per frame (Ability.pfs overlay sequences: f20 = ticks per
frame, cf. Fire Halo record 173 f20 5), stored LAST so every u8 offset fits.  An existing OLDER record 204 is REPLACED
IN PLACE (later records 205 Suspended / 206 Static Shield keep their order and bytes; their directory offsets shift by
the size change) - same recipe as patch_suspend_ability_pfs_v1.py v2.  --revert still removes ONLY record 204 (it then
cannot be re-appended in the middle: revert 206 and 205 first, or re-run --apply on a file that still holds 204).
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_crosswind"
RECORDS = [   # (ability id, description)
    (0xC2, "Crosswind (combat only): fierce crosswinds throw this unit's missiles off course - its ranged attacks suffer -2 attack for 3 turns."),
]

import spellgfx as G
OVERLAY = G.seq_build([{"name": "EFFECTS\\DUALDF.ILB", "frames": list(range(3550, 3598)), "kind": 4, "f8": 0, "f18": 0, "f20": 4,
                        "xs": -23, "ys": -56, "ft10": 0, "chain": None}])   # v2: 48x80 canvas, overlay origin = (23, 56), feet ~ y 77


def build_record(desc):
    data = bytearray(); offs = {}
    offs[5] = len(data); data += struct.pack("<I", len(desc)) + desc.encode("latin-1")
    offs[7] = len(data); data += bytes([1, 1, 0, 0])
    offs[9] = len(data); data += struct.pack("<H", 0)
    offs[8] = len(data); data += OVERLAY                                            # v2: tag 8 = the status overlay sequence (LAST)
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


def replace(raw, key, rec):
    """v2: swap record `key`'s body for `rec` in place; every directory offset behind it shifts by the size change."""
    payload, pre, smalls, wides, body = load(raw)
    off = dict(wides)[key]
    later = sorted(o for _i, o in list(wides) + [(t, o) for t, o in smalls] if o > off)
    end = later[0] if later else len(body)
    delta = len(rec) - (end - off)
    new_wides = [(i, o + delta if o > off else o) for i, o in wides]
    new_smalls = [(t, o + delta if o > off else o) for t, o in smalls]
    return assemble(raw, payload, pre, new_smalls, new_wides, body[:off] + rec + body[end:])


def rec_of(raw, key):
    payload, pre, smalls, wides, body = load(raw)
    offs = sorted(o for _i, o in wides); off = dict(wides)[key]
    nxt = [o for o in offs if o > off]
    return body[off:nxt[0] if nxt else len(body)]


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
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
            print("record %d present with OLDER content -> replacing in place (%d B; later records kept)" % (key, len(rec)))
            raw = replace(raw, key, rec); assert rec_of(raw, key) == rec; continue
        assert wides and max(keys) < key, "record %d must be the largest key (highest is %d)" % (key, max(keys))
        raw = assemble(raw, payload, pre, smalls, list(wides) + [(key, len(body))], body + rec)
        assert max(i for i, _ in parse_top(raw[4:-4])[4]) == key
        print("would append record %d (%d B): %r" % (key, len(rec), desc))
    if raw == raw0: print("already applied"); return 0
    load(raw); print("%d -> %d bytes (CRC ok)" % (len(raw0), len(raw)))
    if not apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if PFS == game_file(os.path.join("Release", "Ability.pfs")) and not os.path.exists(b): shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
