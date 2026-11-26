r"""fix_crocodile_shadow_v1.py - re-fit the Crocodile's ground shadow (2026-10-15, user: "crocodile gfx shadow doesnt
seem properly centered or something, its kind of janky").

How a unit's shadow works (RE 10/15):
  * Unitgfx.pfs child tag 5 = the unit's TImageSequenceList (spellgfx format, 31 slots).  Slots 0..23 = sprite
    sequences (idle / walk / attack / death per facing, facing order 4,3,2,1,6,5 = slot k), slots 24..29 = the
    per-facing SHADOW (a still, kind 0, from UNITS\USHADOW.ILB: f20 = image id, xs/ys = offset), slot 30 = corpse.
  * TTacticalCombatUnitHS.ShowShadow (AoWTCPCK 0x422D68) draws slot 0x17 + [hs+0x14] of [[hs+0x10]+0x28]
    (the unit's own list) at the unit's position - shadow and sprite share the same origin, so each shadow slot's
    xs/ys place it relative to that facing's sprite.  USHADOW.ILB holds 27 ground ellipses (ids 0..26: round
    0-13, tilted 14-17 / 18-21, long flat 22-25) shared by ~200 units - NOT edited here.

Root cause: the Crocodile (Unitres 283 -> Unitgfx 282, art Images\UNITS\ADD_NEW_LAGI2\LIZCR.ILB) was built from
the Lizardman Frog Rider (Unitgfx 56): its shadow slots 24..29 are a byte copy of the Frog Rider's (USHADOW 11 at
(-18,-29) (-18,-27) (-19,-28) (-17,-27) (-18,-27) (-16,-31)), placed for a tall rider.  The croc is long and low
(its frames sit at the bottom of the 64x64 canvas), so the shadow floats level with / above its back (vanilla
units: shadow centroid ~4-10 px left of and 3-16 px BELOW the body centroid; croc: dy -0.7 .. -9.1) and is the
wrong shape for the long body.

Fix: Unitgfx 282 slots 24..29 only - per facing, the USHADOW ellipse (ids 0..26) whose overlap with the croc's
body silhouette (union of its idle + walk frames) is best, centred 3 px left of and 3 px below the body centroid
(a flat-lying body: the shadow sits right under it).  Nothing else changes; LIZCR.ILB is not touched, so this
composes freely with recolor_crocodile_v1.py (either order).  --revert writes the Frog Rider values back (an
in-place record edit, never a whole-file restore - Unitgfx.pfs also carries the Phoenix record 271).

  py -3.10 fix_crocodile_shadow_v1.py            dry run
  py -3.10 fix_crocodile_shadow_v1.py --preview  before/after composites -> tmp\croc_shadow_before.png / _after.png
  py -3.10 fix_crocodile_shadow_v1.py --apply    write (safety copy backup\Release\Unitgfx.pfs.bak_crocshadow once)
  py -3.10 fix_crocodile_shadow_v1.py --revert   restore the original six shadow entries
"""
import argparse, os, shutil, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "old modding tools", "research"))
from bakpath import bak_path, game_file
import ilbcodec, spellgfx as G
import build_phoenix_unit_v1 as PH          # Unitgfx split/join + record helpers (read-only use)

UNITGFX = game_file(os.path.join("Release", "Unitgfx.pfs"))
CHILD = 282
SPRITE = "UNITS\\ADD_NEW_LAGI2\\LIZCR.ILB"
SHADOW = "UNITS\\USHADOW.ILB"
SUFFIX = ".bak_crocshadow"
TMP = r"C:\Users\<user>\.claude\jobs\47241cad\tmp"

# slot 24+k: (USHADOW id, xs, ys).  ORIG = vanilla (Frog Rider copy); NEW = fitted 10/15 (shadow_fit.py: best IoU vs
# the body silhouette of slot k idle + slot 6+k walk frames, shadow centroid = body centroid + (-3, +3)).
ORIG = [(11, -18, -29), (11, -18, -27), (11, -19, -28), (11, -17, -27), (11, -18, -27), (11, -16, -31)]
NEW = [(11, -15, -25), (17, -22, -27), (8, -11, -23), (11, -16, -22), (11, -14, -21), (8, -13, -18)]


def load():
    d = open(UNITGFX, "rb").read(); p = PH.split(d)
    cl, f, w = PH.rec_fields(p["recs"][CHILD])
    sl = G.seq_parse(f[5])
    assert G.seq_build(sl) == f[5], "tag-5 round trip failed"
    assert len(sl) == 31 and sl[0]["name"].upper() == SPRITE, (len(sl), sl[0]["name"])
    for k in range(6):
        e = sl[24 + k]; assert e and e["name"].upper() == SHADOW and e["kind"] == 0, (k, e)
    return d, p, cl, f, w, sl


def state(sl):
    cur = [(sl[24 + k]["f20"], sl[24 + k]["xs"], sl[24 + k]["ys"]) for k in range(6)]
    return "vanilla" if cur == ORIG else "applied" if cur == NEW else "OTHER", cur


def rebuilt(p, cl, f, w, sl, table):
    for k, (sid, xs, ys) in enumerate(table):
        sl[24 + k]["f20"], sl[24 + k]["xs"], sl[24 + k]["ys"] = sid, xs, ys
    nf = dict(f); nf[5] = G.seq_build(sl)
    assert len(nf[5]) == len(f[5])                       # still-slot fields are fixed-width: same size
    p = dict(p); p["recs"] = dict(p["recs"]); p["recs"][CHILD] = PH.rec_build(cl, nf, w)
    return PH.join(p)


# ---------------------------------------------------------------- preview
def _decode(lib, iid, pal=None):
    from PIL import Image
    im = next(i for i in lib["images"] if i["id"] == iid); r = im["parts"][0]; px = lib["pixeldata"]
    out = Image.new("RGBA", (r["w"], r["h"]), (0, 0, 0, 0)); o = out.load()
    if r["type"] == 2:
        q = r["off"]; tr = r["transp"]
        for y in range(r["ch"]):
            ln = struct.unpack_from("<I", px, q)[0]; s = px[q + 4:q + ln]; q += ln; x = r["cx"]; i = 0
            while i < len(s):
                b = s[i]; i += 1
                if b == tr: x += s[i]; i += 1
                else:
                    if 0 <= x < r["w"]: o[x, r["cy"] + y] = (pal[b * 4], pal[b * 4 + 1], pal[b * 4 + 2], 255)
                    x += 1
    else:                                                # type 17: RLE16, drawn as a translucent black shadow
        q = r["off"]; back = r["transp"] & 0xFFFF
        for y in range(r["ch"]):
            ln = struct.unpack_from("<I", px, q)[0]; n = (ln - 4) // 2; w0 = n; p0 = q + 4; x = r["cx"]
            while n > 0:
                v = struct.unpack_from("<H", px, p0)[0]
                if v == back: x += struct.unpack_from("<H", px, p0 + 2)[0] // 2; p0 += 4; n -= 2
                else:
                    if 0 <= x < r["w"]: o[x, r["cy"] + y] = (0, 0, 0, 110)
                    x += 1; p0 += 2; n -= 1
            q = p0 + (2 if w0 % 2 else 0)
    return out


def preview(sl, table, path):
    from PIL import Image, ImageDraw
    spr = ilbcodec.read(open(game_file(os.path.join("Images", "UNITS", "ADD_NEW_LAGI2", "LIZCR.ILB")), "rb").read())
    shd = ilbcodec.read(open(game_file(os.path.join("Images", "UNITS", "USHADOW.ILB")), "rb").read())
    pal = spr["palettes"][0]; cell = 120; img = Image.new("RGBA", (6 * cell, cell), (96, 120, 70, 255))
    dr = ImageDraw.Draw(img)
    for k in range(6):
        ox, oy = k * cell + 50, 70                       # the unit's origin in this cell
        dr.polygon([(ox - 16, oy), (ox, oy - 9), (ox + 16, oy), (ox, oy + 9)], outline=(70, 90, 50, 255))
        sid, xs, ys = table[k]
        img.alpha_composite(_decode(shd, sid), (ox + xs, oy + ys))
        sq = sl[k]; img.alpha_composite(_decode(spr, sq["frames"][0], pal), (ox + sq["xs"], oy + sq["ys"]))
        dr.text((k * cell + 4, 4), "slot %d %dxx sh %d" % (k, sq["frames"][0] // 100, sid), fill=(255, 255, 0, 255))
    img = img.resize((img.width * 2, img.height * 2), Image.NEAREST); img.save(path); print("preview ->", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    d, p, cl, f, w, sl = load()
    st, cur = state(sl)
    print("%s child %d (%s) shadow slots 24..29: %s | state: %s" % (UNITGFX, CHILD, f.get(7, b"")[1:].decode("latin1"), cur, st))
    if a.preview:
        preview(sl, ORIG, os.path.join(TMP, "croc_shadow_before.png")); preview(sl, NEW, os.path.join(TMP, "croc_shadow_after.png"))
    if st == "OTHER" and (a.apply or a.revert): print("ABORT: the shadow slots hold unknown values"); return 1
    if a.revert:
        if st == "vanilla": print("already vanilla"); return 0
        out = rebuilt(p, cl, f, w, sl, ORIG); open(UNITGFX, "r+b").write(out) if len(out) == len(d) else open(UNITGFX, "wb").write(out)
        assert open(UNITGFX, "rb").read() == out; print("reverted (in place)"); return 0
    if st == "applied": print("already applied"); return 0
    out = rebuilt(p, cl, f, w, sl, NEW)
    print("%d bytes would change (file size %d -> %d)" % (sum(1 for x, y in zip(d, out) if x != y), len(d), len(out)))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(UNITGFX, SUFFIX)
    if not os.path.exists(bak): shutil.copy2(UNITGFX, bak); print("safety copy ->", bak)
    with open(UNITGFX, "r+b" if len(out) == len(d) else "wb") as fh: fh.write(out)
    assert open(UNITGFX, "rb").read() == out; print("written and verified", UNITGFX)
    return 0


if __name__ == "__main__":
    sys.exit(main())
