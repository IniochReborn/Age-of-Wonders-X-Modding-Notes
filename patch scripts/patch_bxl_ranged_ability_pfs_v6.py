#!/usr/bin/env python3
r"""Release\Ability.pfs record 214 v6 = Hurl Skull (0xCC) DEATHFIRE - 2026-10-19.  User on v5: "the skull is good, the
effects around it are mediocre - vanilla-style FIRE and DEATH: a heavy smooth black glow and a fire glow (skull wrapped
by death wrapped by fire), a long smooth fading deathfire tail; the explosion the SAME as Self-Destruct with death
effects ADDED; the scream is bad - get rid of it".  Tag 8 (gfx) + tag 7 (sounds) change; tags 5 / 6 / 9 untouched.

  slot 0 (the projectile, TfxHS kind 2 - 0x42E5FC draws EVERY chained sequence at the head, frame by tick + phase):
        CHAIN  DUALDF 7624-7635 skull_death_aura  (MULTIPLY 1026: smooth violet-black aura, drawn first)
            -> DUALDF 7612-7623 hurl_skull5       (the v4 bone skull alone, full spin, solid 256)
            -> DUALDF 7636-7647 skull_fire_aura   (ADDITIVE 770: vanilla-colour flames round the black band)
        each with the CURRENT slot 0's kind / f8 / f18 / f20 / anchor (-31/-33) -> the three stay frame-locked.
  slot 2 (the impact helper 0xCC01, kind 0x26 - 0x42F050 walks the chain with the same frame index; the FIRST sequence's
        frame count = the helper's 30-frame lifetime):
        CHAIN  DUALDF 7680-7709 skull_death_burst (MULTIPLY: dark pall + shock ring + black shards + smoke columns,
                                                   274x258 at -131/-142 = drawn UNDER the blast)
            -> EXPLBIG.ILB 0-29 copied verbatim from Self Destruct (record 75 slot 0: vanilla mode / timing / anchor)
  slot 3 (NEW - the trail puff helper 0xCC03 spawned every tick by patch_bxl_ranged_abilities_v5):
        CHAIN  DUALDF 7648-7663 deathfire_puff_smoke (MULTIPLY, 48x48 at -23/-23)
            -> DUALDF 7664-7679 deathfire_puff_fire  (ADDITIVE)       kind 4, f18 1 (2 ticks / frame = 32-tick puff)
  sounds: cue 0 CATAPULT (throw) / cue 1 SKULL_HIT (landing) unchanged; cue 2 SKULL_SCREAM -> SFX\ZSP\SKULL_FLIGHT.WAV
        (the engine v5 plays it at the 2nd path point).
States: v5 / earlier (any record 214 whose slot 2 is not our chain) -> v6; --revert = the exact pre-v6 record, kept in
<game>\backup\Release\Ability.pfs.rec214_pre_v6 at apply.  Needs the DualDF frames (build_dual_sphere_fx_v1.py --apply)
and SKULL_FLIGHT.WAV (build_dual_sphere_sfx_v1.py --apply).  LIFO: revert this before pfs v5 / v4 / v2 (they see v6 as
FOREIGN and refuse).  Dry-run default; --pfs <copy> = scratch.  One-time safety copy .bak_bxlranged6.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_reversal_ability_pfs_v1 as R
import spellgfx as G
from patch_seekerbolts_pfs_v1 import fields, build_record, replace
import patch_bxl_ranged_ability_pfs_v1 as V1

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_bxlranged6"
K_SKULL, K_SELFDESTRUCT = V1.K_SKULL, 0x41 + 10
B = chr(92)
DF = "EFFECTS" + B + "DUALDF.ILB"
BONE, DAURA, FAURA = list(range(7612, 7624)), list(range(7624, 7636)), list(range(7636, 7648))
PSMOKE, PFIRE, BURST = list(range(7648, 7664)), list(range(7664, 7680)), list(range(7680, 7710))
FLIGHT = ["SFX" + B + "ZSP" + B + "SKULL_FLIGHT.WAV"]


def explosion_vanilla(raw):
    s = G.seq_parse(fields(R.rec_of(raw, K_SELFDESTRUCT))[1][8])
    assert s and s[0] and "EXPLBIG" in s[0]["name"].upper(), "record 75 (Self Destruct) slot 0 is not EXPLBIG"
    e = dict(s[0]); e["chain"] = None
    return e


def chain(*seqs):
    head = None
    for s in reversed(seqs):
        s = dict(s); s["chain"] = head; head = s
    return head


def v6_rec(raw, prev):
    order, vals = fields(prev)
    assert order == [5, 6, 7, 8, 9]
    slots = list(G.seq_parse(vals[8]))
    assert len(slots) == 41 and slots[0] and slots[40]
    h = slots[0]
    lay = lambda ids: G.seq_entry(DF, ids, h["xs"], h["ys"], kind=h["kind"], f8=h["f8"], f18=h["f18"], f20=h["f20"])
    slots[0] = chain(lay(DAURA), lay(BONE), lay(FAURA))
    ex = explosion_vanilla(raw)
    burst = G.seq_entry(DF, BURST, ex["xs"], ex["ys"], kind=ex["kind"], f8=ex["f8"], f18=ex["f18"], f20=ex["f20"])
    slots[2] = chain(burst, ex)
    slots[3] = chain(G.seq_entry(DF, PSMOKE, -23, -23, kind=4, f8=0, f18=1, f20=5),
                     G.seq_entry(DF, PFIRE, -23, -23, kind=4, f8=0, f18=1, f20=5))
    snd = G.snd_parse(vals[7])
    assert len(snd) == 3, "record 214 sound list is not 3 cues (%r)" % (snd,)
    snd[2] = FLIGHT
    vals = dict(vals)
    vals[7] = G.snd_build(snd); assert G.snd_parse(vals[7]) == snd
    vals[8] = G.seq_build(slots); assert G.seq_parse(vals[8]) == slots
    return build_record(order, vals)


def is_v6(rec):
    s = G.seq_parse(fields(rec)[1][8])
    return len(s) > 3 and s[2] and s[2]["frames"] == BURST and s[2].get("chain") and "EXPLBIG" in s[2]["chain"]["name"].upper()


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw
    ks = V1.keys(raw)
    if K_SKULL not in ks: print("record 214 absent - apply patch_bxl_ranged_ability_pfs_v1.py first"); return 1
    cur = R.rec_of(raw, K_SKULL)
    live = os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs")))
    side = bak_path(PFS, ".rec214_pre_v6") if live else PFS + ".rec214_pre_v6"   # scratch copies keep their own
    if is_v6(cur):
        if not os.path.exists(side): print("ABORT - v6 record present but no pre-v6 copy %s" % side); return 1
        prev = open(side, "rb").read(); want = v6_rec(raw, prev); st = "v6" if cur == want else "FOREIGN"
    else:
        prev = cur; want = v6_rec(raw, cur); st = "pre-v6"
    print("Ability.pfs record 214: %s (v6: slot 0 aura/bone/fire chain DualDF %d.., slot 2 death burst + EXPLBIG, slot 3 trail puff, cue 2 SKULL_FLIGHT)"
          % (st, BONE[0]))
    if st == "FOREIGN": print("ABORT - record 214 differs from the v6 build of its saved pre-v6 copy"); return 1
    if revert:
        if st != "v6": print("not applied"); return 0
        raw = replace(raw, K_SKULL, prev)
    else:
        if st == "v6": print("already applied"); return 0
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
