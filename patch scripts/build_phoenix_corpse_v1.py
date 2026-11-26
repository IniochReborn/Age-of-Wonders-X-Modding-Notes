#!/usr/bin/env python3
r"""
Phoenix corpse (2026-10-22): unit 271 left the Great Eagle's corpse (its Unitgfx record was cloned from the eagle's,
build_phoenix_unit_v1.py, and only the sprite path was swapped).  User: the corpse should be the colour of the
Phoenix's BASE sprite (no glow).

A unit's corpse = the LAST slot of its Unitgfx tag-5 TImageSequenceList: "UNITS\DEADUNIT.ILB", kind 4 (frames),
delay 9, xs/ys, n image ids.  Eagle 234 and Phoenix 271: ids 130, 131 ("D_Animal.BMP", type 22 = RAW 16-bit 565,
cw*ch words, transparent key word 31406).  DeadUnit.ILB ids are 0..322; no unit references Add_DeadUnit.ilb.

  Images\UNITS\DeadUnit.ILB   + ids 323, 324 ("D_Phoenix.BMP") = copies of 130 / 131 recoloured: each pixel's
       luminance percentile within the corpse -> the colour at the same luminance percentile of the Phoenix base
       sprite (every opaque pixel of the 72 PHNIX.ILB frames, palette colours, glow layer = USHADOW.ILB not
       included), clipped to the 4 %..90 % band (no white-hot / glow highlights); saturated blood-red pixels stay
       blood, darkened.  Appended through ilbcodec (lossless rewrite; existing images untouched).
  Release\Unitgfx.pfs         child 271: corpse ids 130, 131 -> 323, 324 (8 bytes incl. the file CRC).

Run AFTER build_phoenix_unit_v1.py (its unitgfx_record() re-derives 271 from the eagle and would reset the ids):
revert this first before re-running or reverting the phoenix script.
Dry run by default; --apply / --revert; --preview <png> renders eagle corpse | new corpse | a Phoenix base frame.
Backups <game>\backup\...\DeadUnit.ILB.bak_phoenixcorpse + Unitgfx.pfs.bak_phoenixcorpse.
"""
import argparse, bisect, colorsys, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import build_phoenix_unit_v1 as P
from PIL import Image

ilbcodec = P.ilbcodec
DEADUNIT = game_file(os.path.join("Images", "UNITS", "DeadUnit.ILB"))
PHNIX = game_file(os.path.join("Images", "UNITS", "Animals", "PHNIX.ILB"))
UNITGFX = P.UNITGFX
UNIT = 271
NEW = {130: 323, 131: 324}                  # eagle corpse id -> phoenix corpse id
NAME = b"D_Phoenix.BMP"
CORPSE_PATH = b"UNITS\\DEADUNIT.ILB"
BAK = ".bak_phoenixcorpse"
LO, HI = 0.04, 0.90                         # used band of the phoenix luminance distribution
BLOOD_DARK = 0.8


def lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def is_blood(rgb):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return s > 0.55 and (h < 0.04 or h > 0.95) and rgb[0] > 90


def phoenix_colours():
    """Every opaque base-sprite pixel of PHNIX.ILB (palette colours), sorted by luminance."""
    lib = ilbcodec.read(open(PHNIX, "rb").read())
    pal = lib["palettes"][0]
    cols = [tuple(pal[4 * i:4 * i + 3]) for i in range(256)]
    out = []
    for img in lib["images"]:
        if img["empty"]: continue
        for row in P.rle8_decode(lib["pixeldata"], img["parts"][0]):
            out += [cols[v] for v in row if v]
    out.sort(key=lum)
    return out


def ramp_at(pcols, q, win=0.01):
    """Mean colour of the phoenix pixels around luminance percentile q (q in LO..HI)."""
    n = len(pcols); a = int(max(0, (q - win)) * (n - 1)); b = int(min(1, (q + win)) * (n - 1)) + 1
    seg = pcols[a:b]
    return tuple(int(round(sum(c[i] for c in seg) / len(seg))) for i in range(3))


def corpse_words(lib, iid):
    p = next(i for i in lib["images"] if i["id"] == iid)["parts"][0]
    assert p["type"] == 22 and p["size"] == p["cw"] * p["ch"] * 2, (iid, p["type"], p["size"])
    return p, struct.unpack_from("<%dH" % (p["cw"] * p["ch"]), lib["pixeldata"], p["off"])


def recolour(words, tr, pcols):
    body = sorted(lum(P.c565(w)) for w in words if w != tr and not is_blood(P.c565(w)))
    out = []
    for w in words:
        if w == tr: out.append(w); continue
        rgb = P.c565(w)
        if is_blood(rgb):
            new = tuple(int(c * BLOOD_DARK) for c in rgb)
        else:
            q = bisect.bisect_left(body, lum(rgb)) / max(1, len(body) - 1)
            new = ramp_at(pcols, LO + (HI - LO) * q)
        v = P.rgb565(*new)
        out.append(v ^ 1 if v == tr else v)                  # never collide with the transparent key
    return out


def build_ilb(raw, pcols, add=True):
    """DeadUnit.ILB with our two images (re)appended at the tail, or removed (add=False)."""
    lib = ilbcodec.read(raw); pix = bytearray(lib["pixeldata"])
    mine = [i for i in lib["images"] if i["id"] in NEW.values()]
    if mine:
        cut = min(p["off"] for i in mine for p in i["parts"])
        lib["images"] = [i for i in lib["images"] if i["id"] not in NEW.values()]
        assert all(p["off"] + p["size"] <= cut for i in lib["images"] for p in i["parts"]), "foreign pixels after ours"
        pix = pix[:cut]
    assert max(i["id"] for i in lib["images"]) < min(NEW.values()), "ids 323/324 taken by someone else"
    if add:
        for old, new in NEW.items():
            p, words = corpse_words(lib, old)
            r = ilbcodec.Rec(p); r.update(off=len(pix), name=NAME)
            pix += struct.pack("<%dH" % len(words), *recolour(words, p["transp"], pcols))
            lib["images"].append({"id": new, "composite": False, "parts": [r], "empty": False})
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib); chk = ilbcodec.read(out)
    assert [i["id"] for i in chk["images"] if i["id"] in NEW.values()] == (list(NEW.values()) if add else [])
    return out


def corpse_slot(v):
    i = v.find(CORPSE_PATH); assert i > 0 and v.find(CORPSE_PATH, i + 1) < 0, "corpse slot not unique"
    o = i + len(CORPSE_PATH)
    assert v[o + 2] == 4, "corpse slot is not a frame sequence"
    n = struct.unpack_from("<I", v, o + 19)[0]
    return o + 23, struct.unpack_from("<%dI" % n, v, o + 23)


def build_unitgfx(d, ids):
    pf = P.split(d)
    c, f, w = P.rec_fields(pf["recs"][UNIT]); v = bytearray(f[5])
    at, cur = corpse_slot(v)
    assert len(cur) == len(ids), cur
    struct.pack_into("<%dI" % len(ids), v, at, *ids)
    f[5] = bytes(v); pf["recs"][UNIT] = P.rec_build(c, f, w)
    return P.join(pf)


def unitgfx_ids(d):
    c, f, w = P.rec_fields(P.split(d)["recs"][UNIT])
    return corpse_slot(f[5])[1]


def preview(raw_ilb, new_ilb, path):
    old, new = ilbcodec.read(raw_ilb), ilbcodec.read(new_ilb)
    def corpse_img(lib, iid):
        p, words = corpse_words(lib, iid)
        im = Image.new("RGBA", (p["w"], p["h"]), (0, 0, 0, 0)); px = im.load()
        for k, w in enumerate(words):
            if w != p["transp"]: px[p["cx"] + k % p["cw"], p["cy"] + k // p["cw"]] = P.c565(w) + (255,)
        return im
    ph = ilbcodec.read(open(PHNIX, "rb").read()); pal = ph["palettes"][0]
    def phoenix_img(iid):
        r = next(i for i in ph["images"] if i["id"] == iid)["parts"][0]
        im = Image.new("RGBA", (r["w"], r["h"]), (0, 0, 0, 0)); px = im.load()
        for y, row in enumerate(P.rle8_decode(ph["pixeldata"], r)):
            for x, v in enumerate(row):
                if v: px[x, y] = tuple(pal[4 * v:4 * v + 3]) + (255,)
        return im
    rows = [[corpse_img(old, o), corpse_img(new, n), phoenix_img(pid)] for (o, n), pid in zip(NEW.items(), (103, 409))]
    SC = 4; cell = 64 * SC
    sheet = Image.new("RGBA", (3 * (cell + 10) + 10, 2 * (cell + 10) + 10), (64, 92, 40, 255))
    for j, row in enumerate(rows):
        for i, im in enumerate(row):
            sheet.alpha_composite(im.resize((im.width * SC, im.height * SC), Image.NEAREST), (10 + i * (cell + 10), 10 + j * (cell + 10)))
    sheet.save(path)
    print("preview ->", path, "(eagle corpse | phoenix corpse | phoenix base frame 103 / 409)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--preview")
    a = ap.parse_args()
    raw_ilb = open(DEADUNIT, "rb").read(); raw_gfx = open(UNITGFX, "rb").read()
    have = sorted(i["id"] for i in ilbcodec.read(raw_ilb)["images"] if i["id"] in NEW.values())
    ids = unitgfx_ids(raw_gfx)
    print("DeadUnit.ILB %d B, phoenix corpse images %s | Unitgfx 271 corpse ids %s" % (len(raw_ilb), have or "none", list(ids)))
    if a.revert:
        if not have and tuple(ids) == tuple(NEW): print("already reverted"); return 0
        new_ilb = build_ilb(raw_ilb, None, add=False); new_gfx = build_unitgfx(raw_gfx, list(NEW))
        for f, bak, data in ((DEADUNIT, bak_path(DEADUNIT, BAK), new_ilb), (UNITGFX, bak_path(UNITGFX, BAK), new_gfx)):
            if os.path.exists(bak) and open(bak, "rb").read() != data:
                print("note: rebuilt %s differs from its backup (other edits since?) - keeping the rebuild" % os.path.basename(f))
        with open(DEADUNIT, "r+b") as fh: fh.seek(0); fh.write(new_ilb); fh.truncate()
        with open(UNITGFX, "r+b") as fh: fh.seek(0); fh.write(new_gfx); fh.truncate()
        print("reverted"); return 0
    if tuple(ids) not in (tuple(NEW), tuple(NEW.values())):
        print("ABORT: unit 271 corpse ids %s are neither the eagle's nor ours" % list(ids)); return 1
    pcols = phoenix_colours()
    print("phoenix base sprite: %d opaque pixels; ramp %s .. %s" % (len(pcols), ramp_at(pcols, LO), ramp_at(pcols, HI)))
    new_ilb = build_ilb(raw_ilb, pcols); new_gfx = build_unitgfx(raw_gfx, list(NEW.values()))
    dg = sum(x != y for x, y in zip(raw_gfx, new_gfx)) + abs(len(raw_gfx) - len(new_gfx))
    print("DeadUnit.ILB %d -> %d B | Unitgfx.pfs %d -> %d B, %d bytes differ" % (len(raw_ilb), len(new_ilb), len(raw_gfx), len(new_gfx), dg))
    if a.preview: preview(raw_ilb if not have else build_ilb(raw_ilb, None, add=False), new_ilb, a.preview)
    if new_ilb == raw_ilb and new_gfx == raw_gfx: print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply."); return 0
    for f in (DEADUNIT, UNITGFX):
        bak = bak_path(f, BAK)
        if not os.path.exists(bak): shutil.copy2(f, bak); print("backup ->", bak)
    with open(DEADUNIT, "r+b") as fh: fh.seek(0); fh.write(new_ilb); fh.truncate()
    with open(UNITGFX, "r+b") as fh: fh.seek(0); fh.write(new_gfx); fh.truncate()
    print("applied"); return 0


if __name__ == "__main__":
    sys.exit(main())
