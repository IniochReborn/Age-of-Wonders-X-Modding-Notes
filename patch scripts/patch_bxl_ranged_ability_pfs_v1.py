#!/usr/bin/env python3
r"""Release\Ability.pfs records 214 / 215 = Hurl Flaming Skull (0xCC) / Shoot Black Javelin (0xCD) - 2026-10-19,
ported from BXL's Ziggurat (his 0xBF 'Hurl Flaming Skull' / 0xBE 'Shoot Bane Javelin', records 201 / 200).
Engine = patch_bxl_ranged_abilities_v1.py.

  214 Hurl Flaming Skull (0xCC): shape = AoWx Hurl Boulder record 34 (tags 5/6/7/8/9).
      tag 5  new description;  tag 6 skill cost 8 (= Hurl Boulder);  tag 7 = record 34's sounds (CATAPULT / A_PUNCH2);
      tag 9  0x3FF (= Hurl Boulder);
      tag 8  41 slots like record 34:  slot 0 = the flying projectile, slot 40 = the attack-panel 'HitIcon'
             = COMBAT.ILB #116 (vanilla's flaming skull icon, xs -15 / ys -28 like the boulder's #110).
             slot 0: DUALDF.ILB 7400-7407 (flaming_skull(), kind 4 / f18 1 / f20 5 / -31 -33 = Hurl Boulder's BALLS
             animation slot) when those images exist in Images\Effects\DualDF.ILB, else a static COMBAT.ILB #116
             (kind 0, -23 / -24 = centred 46x45) - BXL's choice.  Re-running after the art is built upgrades in place.
  215 Shoot Black Javelin (0xCD): shape = AoWx Shoot Javelin record 67 (tags 5/6/7/8/9).
      tag 5  vanilla 1.36 record 68 text ("Fires a long-ranged javelin tainted with death magic.");
      tag 6  skill cost 15 (= Shoot Javelin);  tag 9 0x3FF;
      tags 7 / 8 = vanilla 1.36 record 68 VERBATIM (embedded below): BALLISTA / ARRHIT sounds, ARROW.ILB 300-323
             (the black javelin, 24 flight directions) + slot 40 COMBAT.ILB #123 icon.  (AoWx's record 68 is Seeker
             Bolts now - untouched.)

Appended as new largest keys (213 Channeler must be the current largest).  Loads the LIVE file every run.
--revert removes 215 and 214 (must be the largest keys).  Dry-run default; --pfs <copy> = scratch.
One-time safety copy <game>\backup\Release\Ability.pfs.bak_bxlranged.
After applying: LADDER += 0xCC, 0xCD in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py, re-run both
with --apply (bound 0xCC -> 0xCE).
"""
import base64, os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file, game_dir
import patch_reversal_ability_pfs_v1 as R
import spellgfx as G
from patch_seekerbolts_pfs_v1 import fields, build_record
from patch_tame_ability_pfs_v1 import remove

PFS = game_file(os.path.join("Release", "Ability.pfs"))
DUALDF = game_file(os.path.join("Images", "Effects", "DualDF.ILB"))
BAK_SUFFIX = ".bak_bxlranged"
K_SKULL, K_JAV = 0xCC + 10, 0xCD + 10                     # 214, 215
D_BOULDER, D_JAV, PREV_MAX = 0x18 + 10, 0x39 + 10, 0xCB + 10   # 34, 67, 213 Channeler
B = chr(92)
SKULL_IDS = list(range(7400, 7408))
DESC_SKULL = ("Launches a flaming skull at a long-ranged wall or unit, burning it with fire and death magic.\r\n")
DESC_JAV = "Fires a long-ranged javelin tainted with death magic. \r\n"
COST_SKULL, COST_JAV, MASK = 8, 15, 0x3FF
# vanilla 1.36 Ability.pfs record 68 (Shoot Black Javelin) tag 7 (94 B) + tag 8 (1155 B), zlib + base64
REC68_78 = ("eNqVzLsKwkAQBdCZYBp7EUvLgMb3+zm7KEYjgWRRi/yJP2th6zfEXbEINnIHLlyYM8NMHhEHHjWJmdh213yqZ/tbLsaIPuVK4jjKjIRXuTjo+c"
            "QVS0u8VuKSpofIOBxYQw0bo5OzEpMn6rjTJnMkuYZRrOyuZb88iqJw+a/bkA4h3YF0F9I9SPchPYD0ENIjSI8hPYH0FNIzSM8hvYD0EtIrSK8h"
            "vYH0FtICaQVpXdb8M1R14nP85Xebl6VPx9+ceYsZ")


def rec68_78():
    b = zlib.decompress(base64.b64decode(REC68_78)); return b[:94], b[94:]


def dualdf_has_skull():
    """True when Images\Effects\DualDF.ILB holds the flaming_skull() frames 7400-7407 (fx builder rows applied)."""
    if not os.path.exists(DUALDF): return False
    try:
        sys.path.insert(0, os.path.join(game_dir(), "modding tools"))
        from aowxlib import ilb
        ids = {i.id for i in ilb.read(DUALDF).images if not i.empty}
        return all(k in ids for k in SKULL_IDS)
    except Exception as e:
        print("  (DualDF.ILB not readable: %s - static skull)" % e); return False


def skull_rec(raw, animated):
    order, vals = fields(R.rec_of(raw, D_BOULDER))
    assert order == [5, 6, 7, 8, 9], "record 34 (Hurl Boulder) has tags %s" % order
    slots = G.seq_parse(vals[8])
    assert len(slots) == 41 and slots[0] and slots[40] and "BALLS" in slots[0]["name"].upper(), "record 34 tag 8 layout changed"
    if animated:
        s0 = G.seq_entry("EFFECTS" + B + "DUALDF.ILB", SKULL_IDS, -31, -33, kind=4, f8=0, f18=1, f20=5)
    else:
        s0 = {"name": "COMBAT.ILB", "f8": 0, "f18": 0, "kind": 0, "f20": 116, "xs": -23, "ys": -24, "chain": None}
    s40 = dict(slots[40]); s40["f20"] = 116; s40["chain"] = None
    slots = list(slots); slots[0] = s0; slots[40] = s40
    d = DESC_SKULL.encode("latin-1")
    vals = dict(vals)
    vals[5] = struct.pack("<I", len(d)) + d
    vals[6] = struct.pack("<I", COST_SKULL)
    vals[8] = G.seq_build(slots)
    vals[9] = struct.pack("<H", MASK)
    return build_record(order, vals)


def jav_rec(raw):
    order, vals = fields(R.rec_of(raw, D_JAV))
    assert order == [5, 6, 7, 8, 9], "record 67 (Shoot Javelin) has tags %s" % order
    t7, t8 = rec68_78()
    sl = G.seq_parse(t8)
    assert len(sl) == 41 and sl[0]["f20"] == 300 and sl[40]["f20"] == 123, "embedded record 68 gfx corrupt"
    d = DESC_JAV.encode("latin-1")
    vals = dict(vals)
    vals[5] = struct.pack("<I", len(d)) + d
    vals[6] = struct.pack("<I", COST_JAV)
    vals[7] = t7; vals[8] = t8
    vals[9] = struct.pack("<H", MASK)
    return build_record(order, vals)


def keys(raw):
    _p, _pre, smalls, wides, _b = R.load(raw)
    return [i for i, _ in smalls] + [i for i, _ in wides]


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw; ks = keys(raw)
    anim = dualdf_has_skull()
    want = {K_SKULL: skull_rec(raw, anim), K_JAV: jav_rec(raw)}
    alt_skull = skull_rec(raw, not anim)                       # the other skull variant = also 'ours' (upgrade path)
    st = {}
    for k, r in want.items():
        if k not in ks: st[k] = "absent"
        elif R.rec_of(raw, k) == r: st[k] = "ours"
        elif k == K_SKULL and R.rec_of(raw, k) == alt_skull: st[k] = "ours-" + ("static" if anim else "animated")
        else: st[k] = "FOREIGN"
    print("Ability.pfs: %d records, highest key %d | 214 Hurl Flaming Skull: %s (slot 0 %s) | 215 Shoot Black Javelin: %s"
          % (len(ks), max(ks), st[K_SKULL], "DualDF 7400-7407" if anim else "static COMBAT #116", st[K_JAV]))
    if "FOREIGN" in st.values():
        print("ABORT - record 214/215 exists with other content (editor resave? compare first)"); return 1
    if revert:
        if st[K_SKULL] == st[K_JAV] == "absent": print("nothing to revert"); return 0
        for k in (K_JAV, K_SKULL):
            if k in keys(raw):
                assert max(keys(raw)) == k, "record %d is followed by foreign keys - revert those first (LIFO)" % k
                raw = remove(raw, k)
    else:
        if st[K_SKULL] == st[K_JAV] == "ours": print("already applied"); return 0
        if st[K_SKULL].startswith("ours-"):                    # static <-> animated skull: rebuild both (LIFO-safe)
            assert max(ks) == K_JAV, "records after 215 - revert those first"
            raw = remove(raw, K_JAV); raw = remove(raw, K_SKULL)
            print("  upgrading record 214 slot 0 in place (%s)" % ("static -> DualDF animation" if anim else "animation -> static"))
        elif st[K_SKULL] != "absent" or st[K_JAV] != "absent":
            print("ABORT - only one of 214/215 present (partial state)"); return 1
        assert max(keys(raw)) == PREV_MAX, "record 213 (Channeler) must be the largest key before 214 is appended (highest %d)" % max(keys(raw))
        for k in (K_SKULL, K_JAV):
            payload, pre, smalls, wides, body = R.load(raw)
            raw = R.assemble(raw, payload, pre, smalls, list(wides) + [(k, len(body))], body + want[k])
            assert R.rec_of(raw, k) == want[k]
    R.load(raw)
    others = [k for k in keys(raw0) if k not in (K_SKULL, K_JAV) and k > 12]
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in others), "another record changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert" if revert else "apply", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    with open(PFS, "r+b") as f:
        f.seek(0); f.write(raw); f.truncate(len(raw))
    print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
