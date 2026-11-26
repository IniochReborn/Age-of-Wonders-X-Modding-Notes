#!/usr/bin/env python3
r"""Ability.pfs: rewrite the descriptions of the four caster abilities (records 0xB6..0xB9 = id+10) for the
three-level versions (patch_caster_levels_v1 / patch_caster_research_upkeep_v1), 2026-09-21.

The four records were appended at the payload tail by patch_ability_pfs_castercost.py (wide index entries,
offsets relative to the directory end), so they can be rebuilt in place: the tail is replaced, the four wide
offsets are recomputed, the CRC is refreshed.  Record shape unchanged (tags 5 desc / 6 cost / 7 / 8 / 9 mask).
Usage: dry run default; --apply; --revert (restores .bak_casterlevels).
"""
import os, shutil, struct, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch_ability_pfs_castercost as base

PFS = base.PFS
BAK = PFS + ".bak_casterlevels"
COST = 15
DESCS = {
    0xB6: "Evoker: I research cost of combat spells -30%, II casting cost -30%, III casting cost -50%.\r\n",
    0xB7: "Conjurer: I research cost of summoning spells -30%, II casting cost -30%, III summoned units' upkeep -30%.\r\n",
    0xB8: "Enchanter: I research cost of unit enchantments -30%, II casting cost -30%, III enchantment upkeep -30%.\r\n",
    0xB9: "Ritualist: I research cost of other global spells -30%, II casting cost -30%, III global enchantment upkeep -30%.\r\n",
}


def build_record(desc):
    base.COST = COST
    return base.build_record(desc)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.isfile(BAK):
            shutil.copy2(BAK, PFS); print("Ability.pfs restored from", BAK)
        else:
            print("no backup")
        return 0
    raw = open(PFS, "rb").read(); magic = raw[:4]; payload = raw[4:-4]
    assert zlib.crc32(payload) & 0xFFFFFFFF == struct.unpack_from("<I", raw, len(raw) - 4)[0], "CRC invalid"
    pre, small, wide, smalls, wides, dend = base.parse_top(payload)
    idx = {i: k for k, (i, _) in enumerate(wides)}
    missing = [hex(i) for i in DESCS if i not in idx]
    if missing:
        sys.exit(f"records missing: {missing} - run patch_ability_pfs_castercost.py first")
    offs = sorted((wides[idx[i]][1], i) for i in DESCS)
    first_off = offs[0][0]
    # the four must be the last bodies in the payload: nothing may start at/after first_off except them
    others_after = [(i, o) for i, o in wides + [(t, o) for t, o in smalls] if o >= first_off and i not in DESCS]
    if others_after:
        sys.exit(f"other records after ours: {others_after[:3]} - refusing")
    tail_start = dend + first_off
    old_tail = payload[tail_start:]
    print(f"Ability.pfs: {len(raw)} B; rewriting tail records {[hex(i) for _, i in offs]} ({len(old_tail)} B old tail)")
    for _, i in offs:
        o = dend + wides[idx[i]][1]; n = payload[o]; hdr = [(payload[o + 1 + 2 * k], payload[o + 2 + 2 * k]) for k in range(n)]
        body = o + 1 + 2 * n; d5 = dict(hdr)[5]; ln = struct.unpack_from("<I", payload, body + d5)[0]
        print(f"  {i:#x}: old desc = {payload[body + d5 + 4:body + d5 + 4 + ln].decode('latin-1').strip()!r}")
    new_tail = bytearray(); new_off = {}
    for _, i in offs:
        new_off[i] = first_off + len(new_tail); new_tail += build_record(DESCS[i])
    out = bytearray(payload[:pre]); out += bytes([0x80 | small]); out += struct.pack("<I", wide)
    for t, o in smalls:
        out += bytes([t, o])
    for i, o in wides:
        out += struct.pack("<II", i, new_off.get(i, o))
    out += payload[dend:tail_start]; out += new_tail
    newfile = magic + bytes(out) + struct.pack("<I", zlib.crc32(bytes(out)) & 0xFFFFFFFF)
    print(f"  new size {len(newfile)} B")
    if not apply:
        print("dry run (--apply / --revert)"); return 0
    if not os.path.isfile(BAK):
        shutil.copy2(PFS, BAK); print("  backup ->", BAK)
    open(PFS, "wb").write(newfile); print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
