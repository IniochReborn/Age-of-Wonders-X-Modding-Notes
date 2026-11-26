#!/usr/bin/env python3
r"""Release\Ability.pfs: the record for ability 0xC9 'Tame Animal' (2026-10-18; registered by patch_tame_animal_v1.py
as a second TDominateAbility instance).  Record key = id + 10 = 211.

The record is Dominate's (key 38 = 0x1C + 10) with a new description: tag 6 skill-point cost (12), tag 7 the
attack/sound sub-stream (SFX\ATTACK\DOMINATE.WAV), tag 8 the effect gfx (EFFECTS\TWINKGR.ILB twinkle) and tag 9 the
selection mask (0x3FF: unit, items, customize-leader, hero level-up, editor) are copied byte-for-byte from the LIVE
record 38 at apply time, so Tame Animal looks, sounds and is offered exactly like Dominate.
--apply  appends 211 (it must be the largest key AND record 210 (0xC8 Lucky) must already be present).
--revert removes ONLY record 211.  Re-running with a changed description rewrites 211 in place (it is the last key).
One-time safety copy <game>\backup\Release\Ability.pfs.bak_tame.  Dry-run default.  --pfs <copy> = scratch.
After applying: append 0xC9 to LADDER in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py and
re-run both with --apply (bound 0xC9 -> 0xCA).
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_tame"
AB = 0xC9
KEY = AB + 10                       # 211
DONOR = 0x1C + 10                   # 38 = Dominate
PREREQ = 0xC8 + 10                  # 210 = Lucky
DESC = ("Tames a wild creature to fight for this unit. Attack 6/5/4/3 vs level 1/2/3/4 creatures. Cannot tame Fearless "
        "creatures, Spirit Puppets, Djinn, Beholders, Yetis, Fairies, Satyrs, Centaurs, Nymphs, Lady of Pain, Spider Queen "
        "or Shadows." + "\r\n")          # 237 chars (longest existing ability description: 240)


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


def keys_of(raw):
    _p, _pre, smalls, wides, _b = load(raw)
    return [i for i, _ in smalls] + [i for i, _ in wides]


def rec_of(raw, key):
    payload, pre, smalls, wides, body = load(raw)
    offs = sorted(o for _i, o in list(wides) + [(t, o) for t, o in smalls]); off = dict(list(wides) + list(smalls))[key]
    nxt = [o for o in offs if o > off]
    return body[off:nxt[0] if nxt else len(body)]


def remove(raw, key):
    payload, pre, smalls, wides, body = load(raw)
    off = dict(wides)[key]
    later = sorted(o for _i, o in list(wides) + [(t, o) for t, o in smalls] if o > off)
    end = later[0] if later else len(body)
    cut = end - off
    new_wides = [(i, o - cut if o > off else o) for i, o in wides if i != key]
    new_smalls = [(t, o - cut if o > off else o) for t, o in smalls]
    return assemble(raw, payload, pre, new_smalls, new_wides, body[:off] + body[end:])


def rec_tags(r):
    """record table -> {tag: bytes}"""
    b = r[0]; p = 1; nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from("<I", r, p)[0]; p += 4
    pr = []
    for _ in range(nb): pr.append((r[p], r[p + 1])); p += 2
    for _ in range(nd): pr.append(struct.unpack_from("<II", r, p)); p += 8
    base = p; offs = sorted(o for _t, o in pr); out = {}
    for t, o in pr:
        nxt = [x for x in offs if x > o]
        out[t] = r[base + o:base + (nxt[0] if nxt else len(r) - base)]
    return out


def build_record(tags):
    order = sorted(tags); data = bytearray(); offs = {}
    for t in order: offs[t] = len(data); data += tags[t]
    small = [(t, offs[t]) for t in order if offs[t] <= 0xFF and t <= 0xFF]
    wide = [(t, offs[t]) for t in order if (t, offs[t]) not in small]
    assert all(t1 < t2 for (t1, _), (t2, _) in zip(small, wide[:1])), "small tags must precede wide tags"
    hdr = bytearray([(0x80 if wide else 0) | len(small)])
    if wide: hdr += struct.pack("<I", len(wide))
    for t, o in small: hdr += bytes([t, o])
    for t, o in wide: hdr += struct.pack("<II", t, o)
    rec = bytes(hdr) + bytes(data)
    assert rec_tags(rec) == {t: bytes(v) for t, v in tags.items()}
    return rec


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw
    keys = keys_of(raw)
    print("Ability.pfs: %d records, highest key %d (id %#x) | %d (id %#x) %s" % (len(keys), max(keys), max(keys) - 10, KEY, AB,
          "PRESENT" if KEY in keys else "absent"))
    if revert:
        if KEY not in keys: print("nothing to revert"); return 0
        assert max(keys) == KEY, "record %d is followed by foreign keys - revert those first (LIFO)" % KEY
        raw = remove(raw, KEY); open(PFS, "wb").write(raw); print("record %d removed, %d -> %d bytes" % (KEY, len(raw0), len(raw))); return 0
    donor = rec_tags(rec_of(raw, DONOR))
    assert set(donor) == {5, 6, 7, 8, 9} and b"DOMINATE.WAV" in donor[7] and donor[9] == b"\xff\x03", "record %d is not the expected Dominate record" % DONOR
    tags = dict(donor); d = DESC.encode("latin-1"); tags[5] = struct.pack("<I", len(d)) + d
    rec = build_record(tags)
    if KEY in keys:
        if rec_of(raw, KEY) == rec: print("record %d already applied" % KEY); return 0
        assert max(keys) == KEY, "record %d is followed by foreign keys - cannot rewrite in place" % KEY
        print("record %d present with OLDER content -> rewriting" % KEY); raw = remove(raw, KEY); keys = keys_of(raw)
    assert max(keys) < KEY, "record %d must be the largest key (highest is %d)" % (KEY, max(keys))
    assert PREREQ in keys or "--force" in sys.argv, "record %d (0xC8 Lucky) must be present first - apply patch_lucky_ability_pfs_v1.py" % PREREQ
    payload, pre, smalls, wides, body = load(raw)
    raw = assemble(raw, payload, pre, smalls, list(wides) + [(KEY, len(body))], body + rec)
    assert max(keys_of(raw)) == KEY and rec_of(raw, KEY) == rec
    load(raw); print("would append record %d (%d B, Dominate's tags 6-9 + %d-char description); %d -> %d bytes (CRC ok)"
                     % (KEY, len(rec), len(d), len(raw0), len(raw)))
    if not apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
