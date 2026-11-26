#!/usr/bin/env python3
r"""
Combat-tile art for Sky / Chasm battles (2026-10-31): recoloured copies of the water combat ILBs.

The combat water hexagon resource (comb_res.pfs, TWaterCombatHexagonResource, terrain 0) draws from
Images\Waterhex.ILB + Images\WaterAnm.ILB.  build_sky_chasm_combat_v1 clones it for terrain 0xE / 0xB pointing at
the files written here (same image count, sizes and record types -> identical frame ids):
  Sky   : SKYHEX00.ILB / SKYANM00.ILB   indigo night (Ziggurat's strategic Sky tile 32-41,32-40,65-82) with
          lavender wisps where the water had foam/highlights
  Chasm : CHSHEX00.ILB / CHSANM00.ILB   near-black void (his Chasm tile 8-24,12-32,16-41) with faint violet glints
Base tiles (Waterhex 'H_Wa2' ids 140-155, 48x32) = Ziggurat's own strategic Sky / Chasm tiles read from our
Release.hss (8 H_co / 15 Hu_wl records, applied by build_rndhex_previews_hss_v1 --sky), so battles match the map.
Fish / fish-splash frames (WaterAnm ids 100-131) are reduced to one dark pixel (no leaping fish in the sky).
Every other pixel keeps its alpha; its luminance is mapped through a 3-stop ramp, so the water's wave motion
survives as drifting cloud / mist.  Usage: build(game_dir) -> {name: bytes}; --preview <dir> writes contact sheets.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modding tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import ilb  # noqa: E402

SRC = {"HEX": r"Images\Waterhex.ILB", "ANM": r"Images\WaterAnm.ILB"}
OUT = {"sky": {"HEX": r"Images\SKYHEX00.ILB", "ANM": r"Images\SKYANM00.ILB"},
       "chasm": {"HEX": r"Images\CHSHEX00.ILB", "ANM": r"Images\CHSANM00.ILB"}}
RAMPS = {  # (lum stop, rgb)
    "sky": [(0.00, (14, 14, 38)), (0.35, (36, 36, 76)), (0.70, (88, 84, 150)), (1.00, (205, 200, 245))],
    "chasm": [(0.00, (3, 4, 7)), (0.35, (12, 15, 22)), (0.70, (34, 30, 52)), (1.00, (120, 96, 170))],
}


def ramp(stops, l):
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if l <= b:
            k = (l - a) / (b - a) if b > a else 0
            return tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
    return stops[-1][1]


TERR = {"sky": bytes([0x0E, 0xFE]), "chasm": bytes([0x0B, 0xFE])}


def zig_tiles(game_dir, kind):
    """the strategic Sky / Chasm hexagon tiles (48x32 RGBA) from Release.hss"""
    import struct
    from PIL import Image
    import build_rndhex_previews_hss_v1 as H
    A = H.parse(open(os.path.join(game_dir, "Release", "Release.hss"), "rb").read())
    out = []
    for cid in sorted(A["recs"]):
        r = A["recs"][cid]
        if struct.unpack_from("<I", r, 0)[0] != 0x20153 or H.terr(r) != TERR[kind]:
            continue
        s, e = H.emb_span(r)
        lib = ilb.read(bytes(r[s:e]))
        w, h, rows = ilb.decode_record(lib, lib.images[0].primary)
        t = Image.new("RGBA", (w, h)); t.putdata([p or (0, 0, 0, 0) for row in rows for p in row])
        out.append(t)
    assert out, kind
    return out


def recolour(lib, stops, tiles=None):
    from PIL import Image
    lo, hi = 1e9, -1e9
    frames = []
    for im in lib.images:
        rec = im.primary
        if not rec.get("size"):
            frames.append(None); continue
        w, h, rows = ilb.decode_record(lib, rec)
        frames.append((rec, w, h, rows))
        for row in rows:
            for p in row:
                if p and p[3]:
                    l = 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
                    lo, hi = min(lo, l), max(hi, l)
    span = max(1.0, hi - lo)
    for f in frames:
        if f is None:
            continue
        rec, w, h, rows = f
        name = (rec.get("name") or "").lower()
        if tiles and name.startswith("h_wa2"):
            k = lib.images.index(next(im for im in lib.images if im.primary is rec))
            first = next(i for i, im in enumerate(lib.images) if (im.primary.get("name") or "").lower().startswith("h_wa2"))
            t = tiles[(k - first) % len(tiles)]
            assert t.size == (w, h), (t.size, w, h)
            ilb.encode_image(lib, rec, t)
            continue
        if name.startswith("fish"):
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            img.putpixel((w // 2, h // 2), stops[0][1] + (255,))
            ilb.encode_image(lib, rec, img)
            continue
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        px = img.load()
        for y, row in enumerate(rows):
            for x, p in enumerate(row):
                if p and p[3]:
                    l = (0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] - lo) / span
                    px[x, y] = ramp(stops, l) + (p[3],)
        ilb.encode_image(lib, rec, img)
    return lib


def build(game_dir):
    out = {}
    for kind, files in OUT.items():
        for part, dst in files.items():
            raw = open(os.path.join(game_dir, SRC[part]), "rb").read()
            lib = recolour(ilb.read(raw), RAMPS[kind], zig_tiles(game_dir, kind) if part == "HEX" else None)
            out[dst] = ilb.write(lib)
    return out


def preview(game_dir, out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    blobs = build(game_dir)
    for dst, raw in list(blobs.items()) + [(SRC["ANM"], open(os.path.join(game_dir, SRC["ANM"]), "rb").read())]:
        lib = ilb.read(raw)
        tiles = []
        for im in lib.images[:96]:
            rec = im.primary
            if not rec.get("size"):
                continue
            w, h, rows = ilb.decode_record(lib, rec)
            t = Image.new("RGBA", (w, h))
            t.putdata([p or (0, 0, 0, 0) for row in rows for p in row])
            tiles.append(t)
        W = max(t.size[0] for t in tiles); H = max(t.size[1] for t in tiles)
        cols = 12
        sheet = Image.new("RGBA", (cols * W, ((len(tiles) + cols - 1) // cols) * H), (60, 90, 60, 255))
        for i, t in enumerate(tiles):
            sheet.alpha_composite(t, ((i % cols) * W, (i // cols) * H))
        sheet.save(os.path.join(out_dir, os.path.basename(dst) + ".png"))


if __name__ == "__main__":
    gd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "--preview" in sys.argv:
        preview(gd, sys.argv[sys.argv.index("--preview") + 1])
