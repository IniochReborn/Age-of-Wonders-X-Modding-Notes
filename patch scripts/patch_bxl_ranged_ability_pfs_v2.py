#!/usr/bin/env python3
r"""Release\Ability.pfs record 214 v2 = Hurl Skull (0xCC) - 2026-10-19 (user on v1: rename to 'Hurl Skull', make it an
AOE, fresh projectile art, explosion on impact with a modified explosion sfx, boulder toss/crunch kept + a mid-flight
scream like Hellfire's).  Engine = patch_bxl_ranged_abilities_v2.py.  Record 215 (Shoot Black Javelin) is untouched
here (its 'crooked and slow' look was an ENGINE bug - see the v2 engine script).

  214  tag 5  new description (AOE text);  tags 6 / 9 unchanged (cost 8, mask 0x3FF)
       tag 7  sounds: cue 0 SFX\ATTACK\CATAPULT.WAV (the boulder toss, unchanged)
                      cue 1 SFX\ZSP\SKULL_HIT.WAV    (landing: the engine plays cue 1 when the lob arrives - explosion
                                                      + boulder crunch mix, build_dual_sphere_sfx_v1)
                      cue 2 SFX\ZSP\SKULL_SCREAM.WAV (mid-flight scream; the v2 engine plays cue 2 at the lob's midpoint)
       tag 8  slot 0  = DUALDF.ILB 7410-7421 hurl_skull() (12-frame tumbling flaming skull; kind 4 / f18 1 / f20 5 /
                        -31 -33 = the BALLS canvas, as v1)
              slot 2  = Self Destruct's explosion verbatim (Ability.pfs record 75 slot 0: EFFECTS\EXPLBIG.ILB 0-29,
                        -131 / -142) - drawn by the engine's kind-0x26 impact helper (marker 0xCC01)
              slot 40 = the attack-panel icon (COMBAT.ILB #116, unchanged)
States: v1 (either skull variant) -> upgraded in place (record replaced, same key/position); v2 -> 'already applied';
absent -> run patch_bxl_ranged_ability_pfs_v1.py --apply first.  v1 is recognised by its description (the live record
differed from v1's build - slot 0 f20 3 instead of 5, an editor tweak - so v2 builds ON the current record and keeps
slot 0's f18 / f20).  The exact pre-v2 record is saved next to the backups (<game>ackup\Release\Ability.pfs.rec214_pre_v2)
and --revert puts it back byte-for-byte.
Dry-run default; --pfs <copy> = scratch.  One-time safety copy <game>\backup\Release\Ability.pfs.bak_bxlranged2.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
import spellgfx as G
from patch_seekerbolts_pfs_v1 import fields, build_record, replace
import patch_bxl_ranged_ability_pfs_v1 as V1

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_bxlranged2"
K_SKULL, K_SELFDESTRUCT = V1.K_SKULL, 0x41 + 10          # 214; Self Destruct ability 0x41 = record 75
B = chr(92)
SKULL2_IDS = list(range(7410, 7422))
DESC = ("Hurls a skull wreathed in flame at a long-ranged wall or unit. It bursts on impact, burning everything "
        "around the target with fire and death magic.\r\n")
SOUNDS = ["SFX" + B + "ATTACK" + B + "CATAPULT.WAV",
          ["SFX" + B + "ZSP" + B + "SKULL_HIT.WAV"],
          ["SFX" + B + "ZSP" + B + "SKULL_SCREAM.WAV"]]


def explosion_slot(raw):
    order, vals = fields(R.rec_of(raw, K_SELFDESTRUCT))
    s = G.seq_parse(vals[8])
    assert s and s[0] and "EXPLBIG" in s[0]["name"].upper(), "record 75 (Self Destruct) slot 0 is not EXPLBIG"
    e = dict(s[0]); e["chain"] = None
    return e


def skull2_rec(raw, v1rec):
    """v2 record built on the CURRENT record 214 (keeps any editor tweaks, e.g. the live slot 0 f18 / f20 timing)."""
    order, vals = fields(v1rec)
    assert order == [5, 6, 7, 8, 9]
    slots = list(G.seq_parse(vals[8]))
    assert len(slots) == 41 and slots[40]
    f18 = slots[0]["f18"] if slots[0] else 1; f20 = slots[0]["f20"] if slots[0] else 5
    slots[0] = G.seq_entry("EFFECTS" + B + "DUALDF.ILB", SKULL2_IDS, -31, -33, kind=4, f8=0, f18=f18, f20=f20)
    slots[2] = explosion_slot(raw)
    d = DESC.encode("latin-1")
    vals = dict(vals)
    vals[5] = struct.pack("<I", len(d)) + d
    vals[7] = G.snd_build(SOUNDS)
    assert G.snd_parse(vals[7]) == SOUNDS
    vals[8] = G.seq_build(slots)
    return build_record(order, vals)


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw
    ks = V1.keys(raw)
    if K_SKULL not in ks: print("record 214 absent - apply patch_bxl_ranged_ability_pfs_v1.py first"); return 1
    cur = R.rec_of(raw, K_SKULL)
    side = bak_path(PFS, ".rec214_pre_v2")                     # the exact pre-v2 record 214 (for --revert)
    o, v = fields(cur)
    is_v2 = v.get(5, b"")[4:].decode("latin-1") == DESC
    is_v1 = v.get(5, b"")[4:].decode("latin-1") == V1.DESC_SKULL
    if is_v2:
        if not os.path.exists(side): print("ABORT - v2 record present but no pre-v2 copy %s" % side); return 1
        prev = open(side, "rb").read()
        want = skull2_rec(raw, prev); st = "v2" if cur == want else "FOREIGN"
    else:
        prev = cur; want = skull2_rec(raw, cur); st = "v1" if is_v1 else "FOREIGN"
    print("Ability.pfs record 214: %s (v2 slot 0 DualDF %d-%d, slot 2 EXPLBIG, cues CATAPULT / SKULL_HIT / SKULL_SCREAM)"
          % (st, SKULL2_IDS[0], SKULL2_IDS[-1]))
    if st == "FOREIGN": print("ABORT - record 214 has other content"); return 1
    if revert:
        if st == "v1": print("not applied (v1 record present)"); return 0
        raw = replace(raw, K_SKULL, prev)
    else:
        if st == "v2": print("already applied"); return 0
        raw = replace(raw, K_SKULL, want)
    R.load(raw)
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in ks if k != K_SKULL and k > 12), "another record changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert" if revert else "apply", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    if not revert:
        with open(side, "wb") as f: f.write(prev)
    with open(PFS, "r+b") as f:
        f.seek(0); f.write(raw); f.truncate(len(raw))
    print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
