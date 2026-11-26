#!/usr/bin/env python3
r"""
Cyclops corpse + portrait install (2026-11-07; user: "ok add them").

  Images\UNITS\DeadUnit.ILB   + ids 325, 326 ("D_Cyclops.BMP"): art import export\cyclops\corpse_A.png / corpse_B.png
       (62x62, render_cyclops_v5.py CYC_CORPSE).  Record = a copy of the troll corpse 100 (type 22: raw RGB565 words
       inside the clip box, transparent key word = the template's transp), clip box recomputed.
  Images\FACES\Add_UNITS.ILB  + 1 Picture16 "Cyclops.bmp" (103x128 RGB565, drawMode 0 like its neighbours) appended
       at the tail = art import export\cyclops\portrait_final.png (build_cyclops_portrait_v1.py, oil version).
       Its 0-based index (= record order) is the Unitgfx face index for the cyclops unit (printed).
Both files rewritten through ilbcodec (lossless: every existing record byte-identical, asserted by re-reading);
re-running replaces our own records in place (they must be the last ones).  The sprite library itself
(Images\UNITS\Monsters\CYCLOPS.ILB) is written by build_cyclops_ilb_v1.py.  No unit references these yet.
Backups <game>\backup\...\*.bak_cyclops.  Dry-run default; --apply; --revert (restores the backups).
"""
import os, shutil, struct, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "old modding tools", "research"))
from bakpath import bak_path, game_file  # noqa: E402
import ilbcodec  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

TAG = ".bak_cyclops"
DEADUNIT = game_file(os.path.join("Images", "UNITS", "DeadUnit.ILB"))
ADDFACES = game_file(os.path.join("Images", "FACES", "Add_UNITS.ILB"))
ART = game_file(os.path.join("art import export", "cyclops"))
CORPSES = {325: "corpse_A.png", 326: "corpse_B.png"}
CORPSE_TEMPLATE = 100                     # troll corpse (type 22, 62x62)
CORPSE_NAME, FACE_NAME = b"D_Cyclops.BMP", b"Cyclops.bmp"


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def corpse_words(png, tr):
    im = Image.open(png).convert("RGBA")
    assert im.size == (62, 62), im.size
    x0, y0, x1, y1 = im.getbbox()
    px = im.load(); words = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a < 128:
                words.append(tr)
            else:
                v = rgb565(r, g, b)
                words.append(v ^ 1 if v == tr else v)        # never collide with the transparent key
    return (x0, y0, x1 - x0, y1 - y0), words


def build_deadunit(raw):
    lib = ilbcodec.read(raw); pix = bytearray(lib["pixeldata"])
    mine = [i for i in lib["images"] if i["id"] in CORPSES]
    if mine:
        assert all(i["parts"][0]["name"] == CORPSE_NAME for i in mine), "ids 325/326 belong to someone else"
        cut = min(p["off"] for i in mine for p in i["parts"])
        lib["images"] = [i for i in lib["images"] if i["id"] not in CORPSES]
        assert all(p["off"] + p["size"] <= cut for i in lib["images"] for p in i["parts"]), "foreign pixels after ours"
        pix = pix[:cut]
    assert max(i["id"] for i in lib["images"]) < min(CORPSES), "ids 325/326 already taken"
    tmpl = next(i for i in lib["images"] if i["id"] == CORPSE_TEMPLATE)["parts"][0]
    assert tmpl["type"] == 22 and (tmpl["w"], tmpl["h"]) == (62, 62), (tmpl["type"], tmpl["w"], tmpl["h"])
    tr = tmpl["transp"]
    for iid, fn in sorted(CORPSES.items()):
        (cx, cy, cw, ch), words = corpse_words(os.path.join(ART, fn), tr)
        r = ilbcodec.Rec(tmpl)
        r.update(name=CORPSE_NAME, off=len(pix), size=2 * len(words), cx=cx, cy=cy, cw=cw, ch=ch)
        pix += struct.pack("<%dH" % len(words), *words)
        lib["images"].append({"id": iid, "composite": False, "parts": [r], "empty": False})
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib)
    chk = ilbcodec.read(out)
    assert [i["id"] for i in chk["images"] if i["id"] in CORPSES] == sorted(CORPSES)
    return out


def face_pixels():
    im = Image.open(os.path.join(ART, "portrait_final.png")).convert("RGB")
    assert im.size == (103, 128), im.size
    p = im.load(); data = bytearray()
    for y in range(128):
        for x in range(103):
            data += struct.pack("<H", rgb565(*p[x, y]))
    return bytes(data)


def build_faces(raw):
    lib = ilbcodec.read(raw)
    pix = bytearray(lib["pixeldata"])
    mine = [i for i in lib["images"] if i["parts"] and i["parts"][0]["name"] == FACE_NAME]
    if mine:
        assert mine == lib["images"][-1:], "Cyclops portrait is not the last record"
        cut = mine[0]["parts"][0]["off"]; lib["images"] = lib["images"][:-1]; pix = pix[:cut]
    tmpl = lib["images"][-1]["parts"][0]
    assert tmpl["type"] == 16 and (tmpl["w"], tmpl["h"]) == (103, 128)
    data = face_pixels()
    rec = ilbcodec.Rec(tmpl)
    rec.update(name=FACE_NAME, w=103, h=128, totw=103, toth=128, size=len(data), off=len(pix), drawMode=0, blendValue=0)
    index = len(lib["images"])
    lib["images"].append({"id": index, "composite": False, "parts": [rec], "empty": False})
    pix += data
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib)
    chk = ilbcodec.read(out)
    assert chk["images"][-1]["parts"][0]["name"] == FACE_NAME and len(chk["images"]) == index + 1
    return out, index


def same_prefix(old_raw, new_raw):
    """every pre-existing record keeps its pixel bytes"""
    a, b = ilbcodec.read(old_raw), ilbcodec.read(new_raw)
    bi = {i["id"]: i for i in b["images"]}
    for i in a["images"]:
        if i["parts"] and i["parts"][0]["name"] in (CORPSE_NAME, FACE_NAME):
            continue
        for pa, pb in zip(i["parts"], bi[i["id"]]["parts"]):
            assert a["pixeldata"][pa["off"]:pa["off"] + pa["size"]] == b["pixeldata"][pb["off"]:pb["off"] + pb["size"]], i["id"]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        for f in (DEADUNIT, ADDFACES):
            b = bak_path(f, TAG)
            if os.path.exists(b):
                shutil.copy2(b, f); print("restored", f)
        return 0
    d_raw, f_raw = open(DEADUNIT, "rb").read(), open(ADDFACES, "rb").read()
    d_new = build_deadunit(d_raw)
    f_new, idx = build_faces(f_raw)
    same_prefix(d_raw, d_new); same_prefix(f_raw, f_new)
    print("DeadUnit.ILB  %d -> %d B (%s)  corpses 325, 326" % (len(d_raw), len(d_new), "same" if d_new == d_raw else "change"))
    print("Add_UNITS.ILB %d -> %d B (%s)  portrait index %d" % (len(f_raw), len(f_new), "same" if f_new == f_raw else "change", idx))
    if d_new == d_raw and f_new == f_raw:
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, new in ((DEADUNIT, d_new), (ADDFACES, f_new)):
        b = bak_path(f, TAG)
        if not os.path.exists(b):
            shutil.copy2(f, b)
        with open(f, "r+b") as fh:
            fh.seek(0); fh.write(new); fh.truncate()
        assert open(f, "rb").read() == new
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
