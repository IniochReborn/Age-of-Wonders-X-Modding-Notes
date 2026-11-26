r"""recolor_crocodile_v1.py - make the Crocodile unit sprite a little darker (2026-10-15, user: "recolor the
crocodile unit sprite to be a little bit darker"; the Crocodile = Unitres child 283, summoned by 381 Summon
Crocodile).

Where the art lives (traced through Release\Unitres.pfs child 283 tag 8 = Unitgfx child 282):
  * Images\UNITS\ADD_NEW_LAGI2\LIZCR.ILB - used by Unitgfx 282 ONLY (no other unit shares it):
      - 72 sprite frames ids 101..112, 201..212, ... 601..612 (6 facings x 12), type 2 = RLE 8-bit, all on the
        file's single palette (transparent key = palette index 0, colour (4,30,252) - never drawn);
      - 2 corpse images ids 0/1 ('croccorpse', 'croccorpse2'), type 17 = RLE 16-bit 565, key 0x00FF.
  * Shadow (UNITS\USHADOW.ILB) and death (UNITS\DEADUNIT.ILB) are shared by ~200 units - NOT touched.
  * Portrait FACES\X2024.ILB index 1 - not touched (the user asked about the sprite).

The edit is IN PLACE (same file size): the 255 visible palette entries are scaled by FACTOR (hue kept, index 0 =
the key left alone), and every non-key 565 pixel word of the two corpse images is scaled the same way (a result
that would equal the key word is nudged by one blue step).  The new bytes are always derived from the ORIGINAL
(the backup once it exists), so re-running is idempotent and FACTOR can be retuned.

  py -3.10 recolor_crocodile_v1.py              dry run (state + what would change)
  py -3.10 recolor_crocodile_v1.py --preview    before/after strip -> C:\Users\<user>\.claude\jobs\47241cad\tmp\croc_preview.png
  py -3.10 recolor_crocodile_v1.py --apply      write (backup backup\Images\UNITS\ADD_NEW_LAGI2\LIZCR.ILB.bak_crocdark)
  py -3.10 recolor_crocodile_v1.py --revert     restore the backup
"""
import argparse, os, shutil, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "old modding tools", "research"))
from bakpath import bak_path, game_file
import ilbcodec

ILB = game_file("Images", "UNITS", "ADD_NEW_LAGI2", "LIZCR.ILB")
SUFFIX = ".bak_crocdark"
FACTOR = 0.82                     # ~18 % darker
PAL_ID = 0x88801B18
PREVIEW = r"C:\Users\<user>\.claude\jobs\47241cad\tmp\croc_preview.png"


def palette_off(d):
    assert struct.unpack_from("<I", d, 12)[0] == 24 and struct.unpack_from("<I", d, 24)[0] == 1, "expected a v4 header with 1 palette"
    assert struct.unpack_from("<I", d, 28)[0] == PAL_ID
    return 32


def dark565(v, key):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    r, g, b = int(r * FACTOR + 0.5), int(g * FACTOR + 0.5), int(b * FACTOR + 0.5)
    n = (r << 11) | (g << 5) | b
    if n == key: n = n + 1 if b < 31 else n - 1
    return n


def rle16_words(d, start, r):
    """Yield the byte offsets of every drawn (non-key) pixel word of a type 17/18 image."""
    back = r["transp"] & 0xFFFF; p = start
    for _y in range(r["ch"]):
        ln = struct.unpack_from("<I", d, p)[0]; p += 4
        n = (ln - 4) // 2; q = p; skip = (n % 2) > 0
        while n > 0:
            v = struct.unpack_from("<H", d, q)[0]
            if v == back:
                q += 4; n -= 2
            else:
                yield q; q += 2; n -= 1
        p = q + (2 if skip else 0)


def darken(orig):
    d = bytearray(orig); lib = ilbcodec.read(bytes(orig)); po = palette_off(d)
    frames = corpses = 0
    for im in lib["images"]:
        for r in im["parts"]:
            if r["type"] == 2:
                assert r["pal"] == 0 and r["transp"] == 0, (im["id"], r.get("pal"), r.get("transp")); frames += 1
            elif r["type"] in (17, 18):
                start = lib["imgDirectory"] + r["off"]; key = r["transp"] & 0xFFFF
                for q in rle16_words(orig, start, r):
                    struct.pack_into("<H", d, q, dark565(struct.unpack_from("<H", orig, q)[0], key))
                corpses += 1
            else:
                raise AssertionError("unexpected image type %d (id %d)" % (r["type"], im["id"]))
    for i in range(1, 256):                                  # index 0 = the transparent key, never drawn
        for c in range(3):
            d[po + i * 4 + c] = int(orig[po + i * 4 + c] * FACTOR + 0.5)
    return bytes(d), frames, corpses


def render(data, ids):
    from PIL import Image
    lib = ilbcodec.read(data); pal = data[32:32 + 1024]; out = []
    for iid in ids:
        img = next(i for i in lib["images"] if i["id"] == iid); r = img["parts"][0]
        im = Image.new("RGBA", (r["w"], r["h"]), (0, 0, 0, 0)); px = im.load(); p = lib["imgDirectory"] + r["off"]
        cx, cy = r["cx"], r["cy"]
        if r["type"] == 2:
            for y in range(cy, cy + r["ch"]):
                ln = struct.unpack_from("<I", data, p)[0]; p += 4; n = ln - 4; x = cx; q = p
                while n > 0:
                    b = data[q]; q += 1; n -= 1
                    if b == r["transp"]:
                        x += data[q]; q += 1; n -= 1
                    else:
                        if 0 <= x < r["w"] and 0 <= y < r["h"]: px[x, y] = (pal[b * 4], pal[b * 4 + 1], pal[b * 4 + 2], 255)
                        x += 1
                p = q
        else:
            back = r["transp"] & 0xFFFF
            for y in range(cy, cy + r["ch"]):
                ln = struct.unpack_from("<I", data, p)[0]; p += 4; n = (ln - 4) // 2; x = cx; q = p; skip = (n % 2) > 0
                while n > 0:
                    v = struct.unpack_from("<H", data, q)[0]; q += 2; n -= 1
                    if v == back:
                        x += struct.unpack_from("<H", data, q)[0] // 2; q += 2; n -= 1
                    else:
                        if 0 <= x < r["w"] and 0 <= y < r["h"]:
                            px[x, y] = (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31, 255)
                        x += 1
                p = q + (2 if skip else 0)
        out.append(im)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    bak = bak_path(ILB, SUFFIX, create=False)
    cur = open(ILB, "rb").read()
    orig = open(bak, "rb").read() if os.path.exists(bak) else cur
    new, frames, corpses = darken(orig)
    assert len(new) == len(orig) and ilbcodec.read(new)["images"] is not None
    state = "already applied" if cur == new else "vanilla" if cur == orig else "OTHER (file differs from both the original and the darkened build)"
    nchg = sum(1 for x, y in zip(cur, new) if x != y)
    print("%s | %d sprite frames (palette) + %d corpse images | FACTOR %.2f | state: %s | %d bytes would change"
          % (ILB, frames, corpses, FACTOR, state, nchg))
    if a.preview:
        from PIL import Image
        ids = [101, 201, 301, 401, 501, 601, 106, 406, 0, 1]
        rows = [render(orig, ids), render(new, ids)]
        S = 3; W = sum(im.width + 4 for im in rows[0])
        strip = Image.new("RGBA", (W * S, 2 * 68 * S), (96, 112, 80, 255))
        for k, row in enumerate(rows):
            x = 0
            for im in row:
                strip.alpha_composite(im.resize((im.width * S, im.height * S), Image.NEAREST), (x * S, (k * 68 + 2) * S)); x += im.width + 4
        strip.save(PREVIEW); print("preview (top = original, bottom = darkened) ->", PREVIEW)
    if a.revert:
        if not os.path.exists(bak): print("no backup - nothing to revert"); return 0
        shutil.copy2(bak, ILB); print("restored", ILB, "from", bak); return 0
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if state == "already applied": print("already applied"); return 0
    if state.startswith("OTHER"): print("ABORT: the ILB was changed by something else"); return 1
    bak = bak_path(ILB, SUFFIX)
    if not os.path.exists(bak): shutil.copy2(ILB, bak); print("backup ->", bak)
    with open(ILB, "r+b") as fh: fh.write(new); fh.truncate()
    assert open(ILB, "rb").read() == new; print("written and verified", ILB)
    return 0


if __name__ == "__main__":
    sys.exit(main())
