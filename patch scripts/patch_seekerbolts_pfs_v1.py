#!/usr/bin/env python3
r"""Release\Ability.pfs record 68 (ability 0x3A, Seeker Bolts = vanilla 'Shoot Black Javelin', kind-6 projectile via
CreateHurl cl=6) - gold/blue rework (2026-10-18).  Rewrites ONLY tag 7 (sound list) and tag 8 (gfx slot list); tags
5/6/9 and every other record are kept byte for byte (later record offsets shift by the size change).

gfx (DualDF 7000-7061, build_dual_sphere_fx_v1.py rows - see _seekerbolts_integration.txt):
  slot 0  HEAD   7000-7007  64x64 -32/-33  kind-6 head, drawn looped at the path point (TCPCK 0x42E5FC)
  slot 1  TRAIL  7008-7015  64x64 -32/-33  f20 2, frame j at path point pos-4+(7-j)/2 (0x42E85C)
  slot 2  SPIN   7016-7045  72x72 -36/-36  30 frames x 1 tick: kind-0x26 helper at the bolt's launch point
  slot 3  IMPACT 7046-7061  96x96 -48/-48  16 frames x 1 tick: kind-0x26 helper at the bolt's last path point
  (slots 2/3 are only drawn with patch_tc_seekerbolts_v1.py; slots 4-23 keep the vanilla BOLTS entries, 40 = icon)
sound list (Sfx\Zsp, build_dual_sphere_sfx_v1.py): cue 0 SEEKER_CHARGE (unit attack animation, 0x421DDD), cue 1
  [SEEKER_HIT] (each landing, 0x42A0C6), cue 2 [SEEKER_LAUNCH] (release tick, patch_tc_seekerbolts_v1.py).
Without the engine script the record still works: head/trail/impact cue as usual, charge hum at the attack, no spin.

Dry-run default; --apply / --revert (restores the embedded original record exactly); --pfs <copy> = scratch.
Safety copy <game>\backup\Release\Ability.pfs.bak_seeker (once).
"""
import base64, os, shutil, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G
import patch_reversal_ability_pfs_v1 as R

PFS = game_file(os.path.join("Release", "Ability.pfs"))
BAK_SUFFIX = ".bak_seeker"
KEY = 0x3A + 10
B = chr(92)
ILB = "EFFECTS" + B + "DUALDF.ILB"
# the original record 68 (3194 B, live 2026-10-18), zlib + base64 - --revert puts it back verbatim
ORIG_B64 = "eNrtlT9Pg0AUwN8hVKV/ddPpHE0Mk4ODg0CvaZVKw+HfkDQEaW1ai/bq4ODmB/OjuDj6GfCdNTFxctEbkOTHvYR773cPEt4TAQADSvvLByvPqxgnFYA9XJ1JLOaCZgN6nU0e6E08HCVUpOmYDrJU0DiZZQIXOsmmQ3o1EvN4mqRW1axjLiGg4X1Hgy0Zo4LIyIBN3jqPLk+itu9d8F4n6IRNZodt68w+lXs1A4guD/SVsSszOPOYGzLaCvwubR9FzYDZ3T7jnB27rO/6QY/LxZO7ZK1tLAEbSOj6XccOI985xEc8cnwv5FbHcwB0ueclz3OJjNcQE5kiZSRD8F3ALVJF7pAaMkNkkwJpIPPP3HtkHX5i1pSZ1fVcVmYmysyGMrP53/MfmmvKzLoyc0OZuVrA71wvYM9mAWdVEeezuolRKuA/rPJbZvLt+qi6OMhCDY/IG2pfpTpfegeIUwpW"
SOUNDS = ["SFX" + B + "ZSP" + B + "SEEKER_CHARGE.WAV",
          ["SFX" + B + "ZSP" + B + "SEEKER_HIT.WAV"],
          ["SFX" + B + "ZSP" + B + "SEEKER_LAUNCH.WAV"]]


def orig_record():
    return zlib.decompress(base64.b64decode(ORIG_B64))


def fields(rec):
    tp, tend = G.pfs_tab(rec, 0)
    ent = sorted([(t, tend + o) for t, o in tp], key=lambda x: x[1]); out = {}
    for i, (t, vo) in enumerate(ent):
        out[t] = rec[vo:ent[i + 1][1] if i + 1 < len(ent) else len(rec)]
    return [t for t, _ in ent], out


def build_record(order, vals):
    data = b""; offs = []
    for t in order: offs.append((t, len(data))); data += vals[t]
    small = [(t, o) for t, o in offs if o <= 0xFF]; wide = [(t, o) for t, o in offs if o > 0xFF]
    assert [t for t, _ in small + wide] == order, "a small-offset tag after a wide one"
    hdr = bytes([(0x80 if wide else 0) | len(small)]) + (struct.pack("<I", len(wide)) if wide else b"")
    hdr += b"".join(bytes([t, o]) for t, o in small) + b"".join(struct.pack("<II", t, o) for t, o in wide)
    rec = hdr + data
    assert fields(rec)[1] == vals
    return rec


def new_record(orig):
    order, vals = fields(orig)
    slots = G.seq_parse(vals[8])
    assert len(slots) == 41 and slots[40] and slots[40]["kind"] == 0, "unexpected vanilla slot layout"
    slots[0] = G.seq_entry(ILB, list(range(7000, 7008)), -32, -33, f20=0)
    slots[1] = G.seq_entry(ILB, list(range(7008, 7016)), -32, -33, f20=2)
    slots[2] = G.seq_entry(ILB, list(range(7016, 7046)), -36, -36)
    slots[3] = G.seq_entry(ILB, list(range(7046, 7062)), -48, -48)
    vals = dict(vals); vals[8] = G.seq_build(slots); vals[7] = G.snd_build(SOUNDS)
    assert G.snd_parse(vals[7]) == SOUNDS
    return build_record(order, vals)


def replace(raw, key, rec):
    payload, pre, smalls, wides, body = R.load(raw)
    allo = sorted(o for _i, o in list(smalls) + list(wides)); off = dict(list(smalls) + list(wides))[key]
    nxt = [o for o in allo if o > off]; end = nxt[0] if nxt else len(body)
    dlt = len(rec) - (end - off)
    sh = lambda lst: [(i, o + dlt if o > off else o) for i, o in lst]
    new = R.assemble(raw, payload, pre, sh(smalls), sh(wides), body[:off] + rec + body[end:])
    assert R.rec_of(new, key) == rec
    return new


def main():
    global PFS
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--pfs" in sys.argv: PFS = sys.argv[sys.argv.index("--pfs") + 1]
    raw = open(PFS, "rb").read(); cur = R.rec_of(raw, KEY); orig = orig_record(); new = new_record(orig)
    state = "vanilla" if cur == orig else "applied" if cur == new else "FOREIGN"
    print("Ability.pfs record %d (Seeker Bolts 0x3A): %s (%d B; new %d B)" % (KEY, state, len(cur), len(new)))
    if state == "FOREIGN": print("ABORT - record 68 is neither the captured original nor ours"); return 1
    want = orig if revert else new
    if cur == want: print("nothing to do"); return 0
    out = replace(raw, KEY, want)
    others = [k for k in [i for i, _ in R.load(raw)[2]] + [i for i, _ in R.load(raw)[3]] if k != KEY]
    assert all(R.rec_of(out, k) == R.rec_of(raw, k) for k in others if k > 12), "another record changed"
    print("%d -> %d bytes (CRC ok)" % (len(raw), len(out)))
    if not (apply or revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(PFS, BAK_SUFFIX)
    if PFS == game_file(os.path.join("Release", "Ability.pfs")) and not os.path.exists(b): shutil.copy2(PFS, b); print("safety copy ->", b)
    open(PFS, "wb").write(out); print("written", PFS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
