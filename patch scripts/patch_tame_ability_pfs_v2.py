#!/usr/bin/env python3
r"""Release\Ability.pfs for Tame Animal v2 (2026-10-18; engine = patch_tame_animal_v2.py).

  record 211 (Tame Animal 0xC9): ONLY tag 7 (sound list) and tag 8 (gfx chain) are rewritten; tags 5 / 6 / 9
    (description, skill cost - live value kept, e.g. an editor edit -, selection mask) stay byte for byte.
      tag 7 = SFX\ZSP\TAME_ANIMAL.WAV (build_dual_sphere_sfx_v1.py MIX).
      tag 8 = Dominate's chain re-pointed at DualDF art (every element keeps its f8 / f18 / f20 / xs / ys / frame count,
        so the timing is Dominate's): TWINKGR frame 220+k -> DualDF 7200+k (tame_twinkle, 27 frames), TWINKGR /
        COMBAT frame 99 -> DualDF 340 (blank), COMBAT 130 ('Dominate1' dark mark) -> the paw mark DualDF 7230.. (tame_paw).
  record 212 (Tamed 0xCA, new): Dominated's record 160 shape - tag 5 new description, tag 7 (no sound) and tag 9
    (mask 0: never offered) copied from 160, tag 8 = ONE overlay slot like Charmed's (paw loop DualDF 7230-7241,
    xs -31 / ys -50 = above the head, f8 0 / f18 1 / f20 3).  It must be the largest key.
--revert: removes 212 and restores 211's tags 7/8 from the embedded pre-v2 bytes (captured from the live file
2026-10-18; v1's Dominate copy).  Dry-run default; --pfs <copy> = scratch.  One-time safety copy
<game>\backup\Release\Ability.pfs.bak_tame2.
After applying: LADDER += 0xCA in patch_aowx_banner_ceilings_v1.py and patch_tcablist_ceiling_v1.py, re-run both
with --apply (bound 0xCA -> 0xCB).
"""
import base64, os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record, replace
from patch_tame_ability_pfs_v1 import remove

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_tame2"
KEY_T, KEY_S, DONOR_S = 0xC9 + 10, 0xCA + 10, 0x96 + 10           # 211 Tame Animal, 212 Tamed, 160 Dominated
B = chr(92)
ILB = "EFFECTS" + B + "DUALDF.ILB"
TW, PAW, NPAW, BLANK = 7200, 7230, 12, 340
SOUND = "SFX" + B + "ZSP" + B + "TAME_ANIMAL.WAV"
DESC_S = "The creature has been tamed and loyally follows its new master.\r\n"
# record 211's tag 7 (47 B) + tag 8 (443 B) before v2 (zlib + base64) - --revert puts them back
ORIG78 = ("eNqd0D0OgkAQBeAZsxK0sbCw9gLcYUEwBIFENmJB5028odFSRYyFf3fAt0YTmlVj8SWb3cmbmWUmJmrRkPh5Yn1q0yAL5oVUSnpRMUrjMJHKd3I5"
          "QwVRH/wg8D2VFSoPk2g8dcKJyyw6eDnWdb0BXdmDxQdb2MEeSjhApTPgBGxo1WKhJynRZv1q1YUzXOAKN7gb7kyxbRZCT4HI1T+xuthLY1cqnWaxsF5p"
          "m0bae/flF6YhbXruXjV2t3/4SnoAXRVvEQ==")


def orig78():
    b = zlib.decompress(base64.b64decode(ORIG78)); return b[:47], b[47:]


def map_chain(s):
    """Dominate's TWINKGR/COMBAT chain -> DualDF (same element parameters + frame counts)."""
    out = dict(s); fr = []; paw = 0
    for f in s["frames"]:
        if f == 99: fr.append(BLANK)
        elif s["name"].upper().endswith("TWINKGR.ILB") and 220 <= f <= 246: fr.append(TW + f - 220)
        elif s["name"].upper() == "COMBAT.ILB" and f == 130: fr.append(PAW + paw % NPAW); paw += 1
        else: raise ValueError("unexpected frame %d in %s" % (f, s["name"]))
    out["name"] = ILB; out["frames"] = fr
    out["chain"] = map_chain(s["chain"]) if s.get("chain") else None
    return out


def new_211(cur):
    order, vals = fields(cur)
    t7, t8 = orig78()
    slots = G.seq_parse(t8)
    assert len(slots) == 1 and slots[0]["name"].upper().endswith("TWINKGR.ILB"), "unexpected pre-v2 gfx chain"
    vals = dict(vals); vals[7] = G.snd_build([SOUND]); vals[8] = G.seq_build([map_chain(slots[0])])
    assert G.snd_parse(vals[7]) == [SOUND]
    return build_record(order, vals)


def old_211(cur):
    order, vals = fields(cur); t7, t8 = orig78()
    vals = dict(vals); vals[7] = t7; vals[8] = t8
    return build_record(order, vals)


def new_212(raw):
    order, vals = fields(R.rec_of(raw, DONOR_S))
    assert order == [5, 7, 8, 9] and vals[9] == b"\x00\x00", "record %d is not the expected Dominated record" % DONOR_S
    d = DESC_S.encode("latin-1")
    vals = dict(vals); vals[5] = struct.pack("<I", len(d)) + d
    vals[8] = G.seq_build([G.seq_entry(ILB, list(range(PAW, PAW + NPAW)), -31, -50, f8=0, f18=1, f20=3)])
    return build_record(order, vals)


def keys(raw):
    _p, _pre, smalls, wides, _b = R.load(raw)
    return [i for i, _ in smalls] + [i for i, _ in wides]


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); raw0 = raw; ks = keys(raw)
    assert KEY_T in ks, "record 211 (Tame Animal) missing - apply patch_tame_ability_pfs_v1.py first"
    cur = R.rec_of(raw, KEY_T)
    n211, o211 = new_211(cur), old_211(cur)
    s211 = "v2" if cur == n211 else "v1" if cur == o211 else "FOREIGN"
    rec212 = new_212(raw)
    s212 = ("absent" if KEY_S not in ks else "v2" if R.rec_of(raw, KEY_S) == rec212 else "FOREIGN")
    print("Ability.pfs: highest key %d | 211 Tame Animal: %s | 212 Tamed: %s" % (max(ks), s211, s212))
    if "FOREIGN" in (s211, s212): print("ABORT - unexpected record content (editor resave? compare first)"); return 1
    if revert:
        if s211 == "v1" and s212 == "absent": print("nothing to revert"); return 0
        if s212 != "absent":
            assert max(ks) == KEY_S, "record 212 is followed by foreign keys - revert those first (LIFO)"
            raw = remove(raw, KEY_S)
        if s211 == "v2": raw = replace(raw, KEY_T, o211)
    else:
        if s211 == "v2" and s212 == "v2": print("already applied"); return 0
        if s211 == "v1": raw = replace(raw, KEY_T, n211)
        if s212 == "absent":
            ks2 = keys(raw); assert max(ks2) == KEY_T, "record 211 must be the largest key before 212 is appended (highest %d)" % max(ks2)
            payload, pre, smalls, wides, body = R.load(raw)
            raw = R.assemble(raw, payload, pre, smalls, list(wides) + [(KEY_S, len(body))], body + rec212)
            assert R.rec_of(raw, KEY_S) == rec212
    R.load(raw)
    others = [k for k in keys(raw0) if k not in (KEY_T, KEY_S) and k > 12]
    assert all(R.rec_of(raw, k) == R.rec_of(raw0, k) for k in others), "another record changed"
    print("%s: %d -> %d bytes (CRC ok)" % ("revert" if revert else "apply", len(raw0), len(raw)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if os.path.abspath(PFS) == os.path.abspath(game_file(os.path.join("Release", "Ability.pfs"))) and not os.path.exists(b):
        shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(raw); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
