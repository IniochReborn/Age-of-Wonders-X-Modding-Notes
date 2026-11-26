#!/usr/bin/env python3
r"""
Release\Ability.pfs: the record for ability 0xB5 'Rot' (2026-10-14; registered by patch_rotaway_v1.py's reg cave,
inflicted on machines by Rot Away 333).

Recipe = patch_ability_pfs_frenzy.py / _oiled.py / _castercost.py (caster-cost-abilities.md 'Ability.pfs writer'):
container [u32 magic][payload][crc32(payload)]; top index = small prefix + directory (u8 n|0x80, u32 widecount, smalls
(u8 key, u8 off), wides (u32 key, u32 off)), offsets relative to the directory END (so adding / removing a wide entry
does not move them).  Record key = id + 10 = 191.  Body tags: 5 = description, 7 = 01 01 00 00, 8 = 0, 9 = selection
mask 0 (not learnable / assignable - a spell effect); no tag 6 (no skill cost).  The ability NAME is not in the pfs
(the reg cave names it 'Rot').

--apply  appends record 191 (only if absent; it must be the largest key, i.e. appended after Frenzied's 189/190).
--revert removes ONLY record 191 (its wide entry and its body; later bodies' offsets shifted back) - never restores a
         whole-file backup, so other mod records added later survive.
Idempotent; CRC checked before and after.  A one-time safety copy <game>\backup\Ability.pfs.bak_rot is taken on the
first --apply (not used by --revert).  Dry-run default.
After applying: append 0xB5 to LADDER in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py and re-run
both (their id bound = highest pfs id + 1 = 0xB6).
"""
import os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_rot"
ROT_ID = 0xB5
KEY = ROT_ID + 10
DESC = "Rot (combat only): this machine is rotting away - each round it may take 1 physical damage (attack 10 against its defence), for 3 rounds (Rot Away)."   # v2 2026-10-14: Rot is now a Burning-like combat status (patch_rotaway_v1.py v3)


# v3 2026-10-14: tag 8 = Rot's combat status overlay (patch_rot_overlay_v1.py draws ability gfx tag 8 slot 0 for 0xB5):
# a dark-green copy of Cursed's SEffect 50-65 (DualDF 1650-1665, drawMode 1026 multiply) with Cursed's own parameters.
import spellgfx as G
OVERLAY = G.seq_build([{"name": "EFFECTS\DUALDF.ILB", "frames": list(range(1650, 1666)), "kind": 4, "f8": 0, "f18": 1, "f20": 13,
                        "xs": -31, "ys": -35, "ft10": 0, "chain": None}])


def build_record(desc):
    data = bytearray(); offs = {}
    offs[5] = len(data); data += struct.pack("<I", len(desc)) + desc.encode("latin-1")
    offs[7] = len(data); data += bytes([1, 1, 0, 0])
    offs[9] = len(data); data += struct.pack("<H", 0)
    offs[8] = len(data); data += OVERLAY                                            # v3: tag 8 = the status overlay sequence (stored LAST so every u8 offset fits)
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


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    raw = open(PFS, "rb").read(); payload = raw[4:-4]
    assert zlib.crc32(payload) & 0xFFFFFFFF == struct.unpack_from("<I", raw, len(raw) - 4)[0], "source pfs CRC invalid"
    pre, small, wide, smalls, wides, dend = parse_top(payload)
    body = bytes(payload[dend:]); keys = [i for i, _ in smalls] + [i for i, _ in wides]
    present = KEY in keys
    print("Ability.pfs: %d records, highest key %d (id %#x) | record %d (id %#x 'Rot') %s" % (
        len(keys), max(keys), max(keys) - 10, KEY, ROT_ID, "PRESENT" if present else "absent"))
    def remove(raw, payload, pre, smalls, wides, body):
        off = dict(wides)[KEY]
        later = sorted(o for _i, o in list(wides) + [(t, o) for t, o in smalls] if o > off)
        end = later[0] if later else len(body)
        cut = end - off
        new_wides = [(i, o - cut if o > off else o) for i, o in wides if i != KEY]
        new_smalls = [(t, o - cut if o > off else o) for t, o in smalls]
        new = assemble(raw, payload, pre, new_smalls, new_wides, body[:off] + body[end:])
        p2 = parse_top(new[4:-4]); assert KEY not in [i for i, _ in p2[4]]
        return new
    if revert:
        if not present: print("nothing to revert"); return 0
        new = remove(raw, payload, pre, smalls, wides, body)
        open(PFS, "wb").write(new); print("record %d removed (%d -> %d bytes)" % (KEY, len(raw), len(new))); return 0
    if present:
        rec_now = bytes(body[dict(wides)[KEY]:])
        if rec_now == build_record(DESC): print("already applied"); return 0
        assert max(keys) == KEY, "record %d is not the last key - cannot rewrite in place" % KEY
        print("record %d present with OLDER text -> rewriting it" % KEY)
        raw = remove(raw, payload, pre, smalls, wides, body); payload = raw[4:-4]
        pre, small, wide, smalls, wides, dend = parse_top(payload); body = bytes(payload[dend:]); keys = [i for i, _ in smalls] + [i for i, _ in wides]
    assert wide > 0 and max(keys) < KEY, "record %d must be the largest key (highest is %d)" % (KEY, max(keys))
    rec = build_record(DESC)
    new = assemble(raw, payload, pre, smalls, list(wides) + [(KEY, len(body))], body + rec)
    p2 = parse_top(new[4:-4]); assert max(i for i, _ in p2[4]) == KEY
    print("would append record %d (%d B): %r (%d -> %d bytes)" % (KEY, len(rec), DESC, len(raw), len(new)))
    if not apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if not os.path.exists(b): shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(new); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
