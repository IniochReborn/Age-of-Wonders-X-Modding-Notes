#!/usr/bin/env python3
r"""AoWx -- mint Ability.pfs records for the four caster-cost abilities
(Evoker 0xAC / Conjurer 0xAD / Enchanter 0xAE / Ritualist 0xAF).

Companion to build_caster_cost.py (which registers the abilities in code).
A bit-only ability's LEVEL-UP COST comes from Ability.pfs tag 6 (record id =
ability id + 10; TAbility.ReadWrite loads it into [ability+0x14] after
registration) -- absent record = the ability is FREE at hero level-up.
User cost: 15 each.

Record shape (cloned from our Path of Sand record 169):
  directory: 5 small entries; tags: 5 = u32-len description text,
  6 = u32 cost, 7 = 01 01 00 00, 8 = 00 00 00 00, 9 = u16 selection mask
  (0x03FF -- selectable everywhere incl. hero level-up, like our others).
Ability.pfs container: [u32 magic 0x2144DF1C][payload][crc32(payload)];
top index = directory of (id, offset) entries, offsets relative to index
end; our ids (0xB6..0xB9) are the largest -> entries append at the wide-list
tail and bodies at the payload tail, existing offsets untouched.

Usage: dry run default; --apply; --revert (restores .bak_castercost).
"""
import os
import shutil
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
PFS = os.path.join(GAME, "Release", "Ability.pfs")
BAK = PFS + ".bak_castercost"

COST = 15
ABILITIES = [
    (0xAC, "Reduces the casting cost of combat spells by one third.\r\n"),
    (0xAD, "Reduces the casting cost of summoning spells by one third.\r\n"),
    (0xAE, "Reduces the casting cost of unit enchantments by one third.\r\n"),
    (0xAF, "Reduces the casting cost of global spells by one third.\r\n"),
]


def build_record(desc):
    data = bytearray()
    offs = {}
    offs[5] = len(data)
    data += struct.pack("<I", len(desc)) + desc.encode("latin-1")
    offs[6] = len(data)
    data += struct.pack("<I", COST)
    offs[7] = len(data)
    data += bytes([1, 1, 0, 0])
    offs[8] = len(data)
    data += bytes(4)
    offs[9] = len(data)
    data += struct.pack("<H", 0x03FF)
    assert all(o <= 0xFF for o in offs.values()), offs
    hdr = bytes([5])
    for t in (5, 6, 7, 8, 9):
        hdr += bytes([t, offs[t]])
    return hdr + bytes(data)


def parse_top(payload):
    """top index: [prefix bytes] u8 n (0x80 = wide count follows), smalls,
    wides. Ability.pfs carries a 3-byte prefix (01 00 00) before the
    directory byte; probe prefix lengths and validate by increasing ids."""
    for pre in range(0, 9):
        p = pre
        n = payload[p]; p += 1
        small = n & 0x7F
        wide = 0
        if n & 0x80:
            if p + 4 > len(payload):
                continue
            wide = struct.unpack_from("<I", payload, p)[0]; p += 4
        if not (0 < small + wide < 2000):
            continue
        if p + 2 * small + 8 * wide > len(payload):
            continue
        smalls = [(payload[p + 2 * k], payload[p + 2 * k + 1]) for k in range(small)]
        p2 = p + 2 * small
        wides = [struct.unpack_from("<II", payload, p2 + 8 * k) for k in range(wide)]
        p2 += 8 * wide
        ids = [i for i, _ in smalls] + [i for i, _ in wides]
        if len(ids) > 3 and all(ids[k] < ids[k + 1] for k in range(len(ids) - 1)):
            return pre, small, wide, smalls, wides, p2
    raise ValueError("could not locate top index")


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.isfile(BAK):
            shutil.copy2(BAK, PFS)
            print("Ability.pfs restored from backup")
        else:
            print("no backup found")
        return 0

    raw = open(PFS, "rb").read()
    magic = raw[:4]
    payload = raw[4:-4]
    crc = struct.unpack_from("<I", raw, len(raw) - 4)[0]
    assert zlib.crc32(payload) & 0xFFFFFFFF == crc, "source pfs CRC invalid"

    pre, small, wide, smalls, wides, dend = parse_top(payload)
    ids = [i for i, _ in smalls] + [i for i, _ in wides]
    have = [i for i, _d in ABILITIES if (i + 10) in ids]
    if have:
        print("already present: %s" % [hex(h) for h in have])
        print("nothing to do" if len(have) == len(ABILITIES) else
              "PARTIAL state - investigate")
        return 0
    assert wide > 0, "expected a wide index"
    assert max(ids) < ABILITIES[0][0] + 10, "new ids must be the largest"

    body_base = dend
    tail_off = len(payload) - body_base          # offset of appended bodies
    new_wides = []
    new_bodies = bytearray()
    for aid, desc in ABILITIES:
        rec = build_record(desc)
        new_wides.append((aid + 10, tail_off + len(new_bodies)))
        new_bodies += rec

    # rebuild: prefix + same smalls, wide count +4, wides + new entries,
    # bodies + new
    out = bytearray()
    out += payload[:pre]
    out += bytes([0x80 | small])
    out += struct.pack("<I", wide + len(new_wides))
    for t, o in smalls:
        out += bytes([t, o])
    for i, o in wides:
        out += struct.pack("<II", i, o)
    # the directory GREW by 4*8 bytes -> offsets are relative to directory
    # end, so existing offsets stay valid; new entries use tail offsets.
    for i, o in new_wides:
        out += struct.pack("<II", i, o)
    out += payload[dend:]
    out += new_bodies

    newfile = magic + bytes(out) + struct.pack("<I", zlib.crc32(bytes(out)) & 0xFFFFFFFF)

    print("Ability.pfs: %d -> %d bytes; adding records %s (cost %d, mask 0x3FF)"
          % (len(raw), len(newfile), [i + 10 for i, _ in ABILITIES], COST))
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(PFS, BAK)
        print("backed up")
    open(PFS, "wb").write(newfile)
    print("APPLIED - verify with pfs.py tags Ability.pfs 182 (etc.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
