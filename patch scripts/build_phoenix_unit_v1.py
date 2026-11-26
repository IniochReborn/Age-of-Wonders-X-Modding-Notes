#!/usr/bin/env python3
r"""
The Phoenix: unit slot 271 (the unused Azrac "Chariot", gfx 277 Highmen Chariot) becomes the Life/Fire summon
(2026-10-13; v2 same day after the user's review: portrait into Add_UNITS.ILB, phoenix features on sprite + portrait).

  Release\Unitres.pfs  child 271 (TUnitResource 0x20212) rewritten: name "Phoenix" (tag 0xA, no 0xB), gfx id 271,
       stats ATK 6 / DEF 4 / DMG 4 / HP 10 / MV 36 / RES 7, level 3, cost 60, Great Eagle's move type (6) and
       misc bytes; ability owners (tags 0x19/0x1E/0x1F/0x20 = base / silver / gold / legendary: inner tag 2 = count,
       3 = bitfield, bit i = ability i):
         base      Flying, Fire Immunity, Fire Strike, Holy Strike, Strike, Regeneration, Vision, Fearless, Cold Weakness
         silver    Fire Breath        gold  Round Attack        legendary  Extra Strike
       (the old record - Azrac Chariot 5/2/3/10/36/5 with the Highmen Chariot gfx 277 - is in the .bak_phoenix backup;
       gfx 277 itself is untouched, just unreferenced now.)
  Release\Unitgfx.pfs  child 271 ADDED (0x20210) = the Great Eagle's record 234 with the sprite path
       UNITS\ANIMALS\PHNIX.ILB (same length as EAGLE.ILB - the path sits once per animation sequence inside the
       tag-5 blob), face FACES\ADD_UNITS.ILB index FACE_INDEX (v2: appended to the shared add-on face library like
       the other custom units, 0-based = record order), display name "Phoenix"; the eagle's wing/screech sounds kept.
  Images\UNITS\Animals\PHNIX.ILB  = EAGLE.ILB re-coloured to fire (index 0 = the transparent key stays; every other
       palette entry maps by luminance: dark -> crimson, mid -> orange, light -> gold -> white-hot) and, v2, every one
       of the 72 frames (6 directions x 12) repainted: three long phoenix tail plumes streaming down from the tail
       base (lowest body pixel under the body's centre column), swaying with the wing-beat frame, gold at the root ->
       orange -> red at the tips; a small three-tongue flame crest on the head (topmost central body pixels); flame
       flicks off the wing tips (the widest rows); all drawn behind the bird, re-encoded with the game's 8-bit RLE
       (per row u32 length + stream, transparent runs as (0, count), clip box recomputed).  The encoder round-trips
       the untouched EAGLE.ILB byte for byte (asserted).
  Images\FACES\Add_UNITS.ILB  + 1 Picture16 record "Phoenix.bmp" (103x128, drawMode 0 like its neighbours) = the
       eagle portrait (UNITS.ILB image 14) re-coloured (bird by the fire ramp, the sky to a dark ember glow) with a
       flame crest rising from the crown, a glowing gold eye, an orange aura round the bird and drifting embers.
Both pfs files are rebuilt child by child (every other record byte-identical, root/children tables re-serialised in
their original small/wide form, CRC = crc32(payload)); the rebuild of the UNCHANGED file is asserted equal to the
original first.  Backups <game>\backup\Release\Unit{res,gfx}.pfs.bak_phoenix + Images\FACES\Add_UNITS.ILB.bak_phoenix;
--revert restores them and deletes PHNIX.ILB (and the v1 FACES\PHNIX.ILB if still there).  --preview writes
phoenix_preview.png (all 72 frames + the portrait) next to this script.  Summon Phoenix (spell 362) summons unit 271.
"""
import argparse, math, os, random, shutil, struct, sys, zlib
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "old modding tools", "research"))
from bakpath import bak_path, game_file
import ilbcodec

UNIT = 271
UNITRES = game_file(os.path.join("Release", "Unitres.pfs"))
UNITGFX = game_file(os.path.join("Release", "Unitgfx.pfs"))
EAGLE_ILB = game_file(os.path.join("Images", "UNITS", "Animals", "EAGLE.ILB"))
PHNIX_ILB = game_file(os.path.join("Images", "UNITS", "Animals", "PHNIX.ILB"))
FACES_ILB = game_file(os.path.join("Images", "FACES", "UNITS.ILB"))
ADD_FACES = game_file(os.path.join("Images", "FACES", "Add_UNITS.ILB"))
OLD_FACE = game_file(os.path.join("Images", "FACES", "PHNIX.ILB"))        # v1 output, no longer used
BAK_SUFFIX = ".bak_phoenix"
EAGLE_FACE_ID = 14
FACE_NAME = b"Phoenix.bmp"
STATS = dict(atk=6, dfn=4, dmg=4, hp=10, mv=36, res=7, level=3, cost=60)
BASE_AB = [0x01, 0x07, 0x0E, 0x13, 0x15, 0x31, 0x40, 0x43, 0x52]
SILVER_AB, GOLD_AB, LEGEND_AB = [0x56], [0x72], [0x73]
AB_COUNT = 0xB1                       # registered abilities incl. Martyr 0xB0 (bitfield = ceil(count/8) bytes)
DESC = ("The Phoenix is a great firebird of the heavens, born of holy flame. It strikes with fire and holy light, "
        "its inner fire closes its wounds, and it fears nothing - but the cold of the north saps its strength. "
        "Should it fall, its ashes are said to kindle a new bird.")


# ---------------------------------------------------------------- HSS property-stream helpers
def tab(d, p):
    """Property table at p -> (pairs [(tag, off, wide?)], data base)."""
    ctrl = d[p]; q = p + 1; nd = 0
    if ctrl & 0x80: nd = struct.unpack_from("<I", d, q)[0]; q += 4
    pairs = []
    for k in range(ctrl & 0x7F): pairs.append((d[q], d[q + 1], False)); q += 2
    for k in range(nd): t, o = struct.unpack_from("<II", d, q); pairs.append((t, o, True)); q += 8
    return pairs, q


def tab_bytes(pairs, wide_form):
    small = [(t, o) for t, o, w in pairs if not w]; wide = [(t, o) for t, o, w in pairs if w]
    assert all(o <= 0xFF for _t, o in small)
    out = bytes([(0x80 if wide_form or wide else 0) | len(small)])
    if wide_form or wide: out += struct.pack("<I", len(wide))
    for t, o in small: out += bytes([t, o])
    for t, o in wide: out += struct.pack("<II", t, o)
    return out


def split(d):
    """Unitres/Unitgfx: magic, 01 00 00, root table @7 (tag 2 byte @+0, tag 1 = children table @+1)."""
    assert d[:4] == bytes.fromhex("1cdf4421")
    assert struct.unpack_from("<I", d, len(d) - 4)[0] == (zlib.crc32(d[4:-4]) & 0xFFFFFFFF), "pfs CRC bad"
    root, rb = tab(d, 7); rd = dict((t, o) for t, o, _w in root)
    assert rd == {2: 0, 1: 1}, root
    kids, kb = tab(d, rb + 1)
    order = [cid for cid, _o, _w in kids]
    offs = sorted(set(o for _c, o, _w in kids)); recs = {}
    for cid, o, w in kids:
        nxt = min([x for x in offs if x > o] + [len(d) - 4 - kb])
        recs[cid] = d[kb + o:kb + nxt]
    return {"head": d[:7], "root_wide": bool(d[7] & 0x80), "tag2": d[rb:rb + 1], "kids_wide": bool(d[rb + 1] & 0x80),
            "kid_form": {cid: w for cid, _o, w in kids}, "order": order, "recs": recs}


def join(p):
    blob = bytearray(); offs = {}
    for cid in p["order"]:
        offs[cid] = len(blob); blob += p["recs"][cid]
    pairs = [(cid, offs[cid], p["kid_form"].get(cid, True)) for cid in p["order"]]
    kids = tab_bytes(pairs, p["kids_wide"])
    root = tab_bytes([(2, 0, False), (1, 1, False)], p["root_wide"])
    body = bytes(p["head"]) + root + bytes(p["tag2"]) + kids + bytes(blob)
    return body + struct.pack("<I", zlib.crc32(body[4:]) & 0xFFFFFFFF)


def rec_fields(rec):
    classid = struct.unpack_from("<I", rec, 0)[0]
    pairs, base = tab(rec, 4)
    order = sorted(pairs, key=lambda e: e[1]); f = {}
    for i, (t, o, _w) in enumerate(order):
        e = order[i + 1][1] if i + 1 < len(order) else len(rec) - base
        f[t] = bytes(rec[base + o:base + e])
    return classid, f, bool(rec[4] & 0x80)


def rec_build(classid, f, wide_form):
    order = sorted(f); offs, o = {}, 0
    for t in order: offs[t] = o; o += len(f[t])
    pairs = [(t, offs[t], offs[t] > 0xFF) for t in order]
    return struct.pack("<I", classid) + tab_bytes(pairs, wide_form) + b"".join(f[t] for t in order)


def sstr(s):
    b = s.encode("latin-1"); assert len(b) < 256; return bytes([len(b)]) + b


def owner(ids, count=AB_COUNT):
    bits = bytearray((count + 7) // 8)
    for i in ids:
        assert i < count; bits[i // 8] |= 1 << (i % 8)
    return bytes([2, 2, 0, 3, 4]) + struct.pack("<I", count) + bytes(bits)


# ---------------------------------------------------------------- pfs records
def unitres_record(old):
    classid, f, wide = rec_fields(old)
    assert classid == 0x20212
    nf = dict(f); nf.pop(0xB, None); nf.pop(0x1, None)
    nf[0x2] = struct.pack("<I", 3); nf[0x3] = struct.pack("<I", UNIT); nf[0x8] = struct.pack("<I", UNIT)
    nf[0xA] = sstr("Phoenix")
    nf[0xC] = bytes([6]); nf[0xD] = bytes([0xFF])
    nf[0xE] = bytes([STATS["atk"]]); nf[0xF] = bytes([STATS["dfn"]]); nf[0x10] = bytes([STATS["dmg"]])
    nf[0x11] = bytes([STATS["hp"]]); nf[0x12] = bytes([STATS["mv"]]); nf[0x13] = bytes([STATS["res"]])
    nf[0x14] = bytes([STATS["level"]]); nf[0x15] = bytes([1]); nf[0x16] = bytes([0]); nf[0x17] = bytes([2])
    nf[0x19] = owner(BASE_AB)
    d = DESC.encode("latin-1"); nf[0x1A] = struct.pack("<I", len(d)) + d
    nf[0x1B] = struct.pack("<I", STATS["cost"]); nf[0x1C] = bytes([2]); nf[0x1D] = bytes([1])
    nf[0x1E] = owner(SILVER_AB); nf[0x1F] = owner(GOLD_AB); nf[0x20] = owner(LEGEND_AB)
    return rec_build(classid, nf, True)


USHADOW = game_file(os.path.join("Images", "UNITS", "USHADOW.ILB"))
PAD = 16                    # 10/31 (user: wing tips squared off facing up/down): frames rendered PAD px wider on each side
                            # (96x64; sets 1/4 frames 5-6 reach 7 px past the old 64-px canvas), sequences shifted -PAD
GLOW_BASE_ID, GLOW_XS, GLOW_YS = 104, -16 - PAD, -24   # v16: our own glows, ids 104..109 (one per facing direction, appended to USHADOW.ILB after the
GLOW_NAME = b"UPhoenixGlow.BMP"                  # vanilla ULight 100..103), 64x64 additive like 102 (770 / blend 30), aligned with the sprite frame
GLOW_BLEND = 30


ANIM_GLOW_BASE = 110        # v17: per-frame glows (id = 110 + (dir-1)*GLOW_PER_DIR + frame-1), animated under the sprite
GLOW_PER_DIR = 24           # 11/01: 12 eagle-scheme frames + the 12-frame smooth loop (ids 13..24) -> ids 110..253
LOOP_FIRST, LOOP_COUNT = 13, 12   # 11/01: fly/idle sequences play the smooth loop (phoenix_art LOOP_BASE/LOOP_N)
LOOP_DELAY = 1              # 11/01 (user: 'slightly speed up'): f18 of the loop sequences 2 -> 1 (a frame every 2 ticks: the old 8-frame beat length)
ANIM_GLOW_NAME = b"UPhoenixGlowA.BMP"


def phoenix_frame_glows(frames):
    """One 64x64 RGB glow per sprite frame (6 x 12): that frame's silhouette blurred wide + a brighter core, tinted
    orange - so the glow follows the wings through the beat."""
    import numpy as np
    out = {}
    S = {iid: np.array([[1.0 if v else 0.0 for v in row] for row in a], np.float32) for iid, a in frames.items()}
    for iid, a in frames.items():
        sil = S[iid]
        f = iid % 100
        if LOOP_FIRST <= f < LOOP_FIRST + LOOP_COUNT:       # 11/01: light + sprite are drawn in separate passes, so the
            k = f - LOOP_FIRST                               # light can be a frame ahead/behind ("brief flash") ->
            nb = [iid - f + LOOP_FIRST + (k + j) % LOOP_COUNT for j in (-1, 1)]   # loop glows cover the neighbouring
            core_sil = sil                                   # poses too (union for the wide halo, own pose for the core)
            sil = np.maximum.reduce([sil] + [S[n] * 0.85 for n in nb])
        else:
            core_sil = sil
        im = Image.fromarray((sil * 255).astype(np.uint8), "L")
        wide = np.array(im.filter(ImageFilter.GaussianBlur(6.0))).astype(np.float32) / 255.0
        cim = Image.fromarray((core_sil * 255).astype(np.uint8), "L")
        core = np.array(cim.filter(ImageFilter.GaussianBlur(2.2))).astype(np.float32) / 255.0
        g = np.clip(1.25 * wide + 0.5 * core, 0, 1)
        rgb = np.zeros(sil.shape + (3,), np.float32)
        rgb[:, :, 0] = 255 * g; rgb[:, :, 1] = 95 * g + 60 * g * g; rgb[:, :, 2] = 10 * g + 30 * g * g * g
        out[iid] = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    return out


def phoenix_glows(frames, pal):
    """Six 64x64 RGB glow images from the phoenix's own silhouette: per facing direction the union of its 8 loop
    frames, blurred wide, with a brighter core, tinted orange -> {direction: PIL RGB} (black = nothing, additive)."""
    import numpy as np
    out = {}
    for d in range(1, 7):
        acc = None
        for f in range(8):
            a = frames[d * 100 + f + 1]
            m = np.array([[1.0 if v else 0.0 for v in row] for row in a], np.float32)
            acc = m if acc is None else acc + m
        sil = np.clip(acc / 4.0, 0, 1)                                      # pixels covered by half the frames or more = 1
        im = Image.fromarray((sil * 255).astype(np.uint8), "L")
        wide = np.array(im.filter(ImageFilter.GaussianBlur(7.0))).astype(np.float32) / 255.0
        core = np.array(im.filter(ImageFilter.GaussianBlur(2.5))).astype(np.float32) / 255.0
        g = np.clip(0.75 * wide * 1.6 + 0.55 * core, 0, 1)
        rgb = np.zeros(sil.shape + (3,), np.float32)
        rgb[:, :, 0] = 255 * g; rgb[:, :, 1] = 95 * g + 60 * g * g; rgb[:, :, 2] = 10 * g + 30 * g * g * g
        out[d] = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    return out


def add_anim_glow_images(raw, fglows):
    """Append (or replace) the 72 per-frame glow records (ids 110..181) after the six stills."""
    lib = ilbcodec.read(raw)
    mine = [i for i in lib["images"] if i["parts"] and i["parts"][0]["name"] == ANIM_GLOW_NAME]
    pix = bytearray(lib["pixeldata"])
    if mine:
        assert mine == lib["images"][-len(mine):], "our animated glow records are not the last ones"
        cut = min(i["parts"][0]["off"] for i in mine); lib["images"] = lib["images"][:-len(mine)]; pix = pix[:cut]
    tmpl = next(i for i in lib["images"] if i["id"] == 102)["parts"][0]
    for k, iid in enumerate(sorted(fglows)):
        d, f = iid // 100, iid % 100
        im = fglows[iid]; p = im.load(); data = bytearray()
        pts = [(x, y) for y in range(im.size[1]) for x in range(im.size[0]) if max(p[x, y]) > 6] or [(31, 31)]
        cx, cy = min(q[0] for q in pts), min(q[1] for q in pts); cw = max(q[0] for q in pts) - cx + 1; ch = max(q[1] for q in pts) - cy + 1
        for y in range(cy, cy + ch):
            for x in range(cx, cx + cw):
                v = rgb565(*p[x, y]) if max(p[x, y]) > 6 else 0
                if v == 0 and max(p[x, y]) > 6: v = 0x0821
                data += struct.pack("<H", v)
        rec = ilbcodec.Rec(tmpl); rec.update(name=ANIM_GLOW_NAME, sub=k, size=len(data), off=len(pix), cw=cw, ch=ch, cx=cx, cy=cy, transp=0, blendValue=GLOW_BLEND, drawMode=770)
        lib["images"].append({"id": ANIM_GLOW_BASE + (d - 1) * GLOW_PER_DIR + (f - 1), "composite": False, "parts": [rec], "empty": False}); pix += data
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib); chk = ilbcodec.read(out); assert chk["images"][-1]["id"] == ANIM_GLOW_BASE + 5 * GLOW_PER_DIR + LOOP_FIRST + LOOP_COUNT - 2
    return out


def add_glow_images(raw, glows):
    """Append (or replace) our six glow records at the tail of USHADOW.ILB -> new bytes.  Records copy image 102's
    settings (type 22, info 3, drawMode 770) with blend GLOW_BLEND, key 0x0000 (black = nothing in additive draw)."""
    lib = ilbcodec.read(raw)
    mine = [i for i in lib["images"] if i["parts"] and i["parts"][0]["name"] in (GLOW_NAME, ANIM_GLOW_NAME)]   # strip BOTH of ours (stills + per-frame)
    pix = bytearray(lib["pixeldata"])
    if mine:
        assert mine == lib["images"][-len(mine):], "our glow records are not the last ones"
        cut = min(i["parts"][0]["off"] for i in mine); lib["images"] = lib["images"][:-len(mine)]; pix = pix[:cut]
    tmpl = next(i for i in lib["images"] if i["id"] == 102)["parts"][0]
    for k, d in enumerate(sorted(glows)):
        im = glows[d]; p = im.load(); data = bytearray()
        pts = [(x, y) for y in range(im.size[1]) for x in range(im.size[0]) if max(p[x, y]) > 6]
        cx, cy = min(q[0] for q in pts), min(q[1] for q in pts); cw = max(q[0] for q in pts) - cx + 1; ch = max(q[1] for q in pts) - cy + 1
        for y in range(cy, cy + ch):
            for x in range(cx, cx + cw):
                r_, g_, b_ = p[x, y]; v = rgb565(r_, g_, b_) if max(p[x, y]) > 6 else 0
                if v == 0 and max(p[x, y]) > 6: v = 0x0821
                data += struct.pack("<H", v)
        rec = ilbcodec.Rec(tmpl); rec.update(name=GLOW_NAME, sub=k, size=len(data), off=len(pix), cw=cw, ch=ch, cx=cx, cy=cy, transp=0, blendValue=GLOW_BLEND, drawMode=770)
        lib["images"].append({"id": GLOW_BASE_ID + k, "composite": False, "parts": [rec], "empty": False}); pix += data
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib); chk = ilbcodec.read(out); assert chk["images"][-1]["id"] == GLOW_BASE_ID + 5
    return out


ANIMATED_LIGHT = True       # the animated (sequence) light layer, kept in sync by patch_ilpack_glow_sync_v1.py - WORKING in game 10/13 (the earlier "crash" was a MapViewer ShowScene error from a broken intermediate state); --still-glow writes the per-direction stills instead


def add_glow_layer(blob, path):
    r"""Unitgfx tag 5 = a TImageSequenceList stream (spellgfx format): u32 slots; per slot u8 nil-flag then a
    TImageSequence: len32 ILB name, u8 f8 (layer id), u8 f18 (frame delay), u8 kind (0 still: f20 = image id; 4
    frames), i32 f20, i32 xs, i32 ys, [kind 4/5: u32, u32 n, n x u32 frames], u8 hasSub -> a chained sub-sequence.
    The Fire Elemental (child 226, the only glowing vanilla unit) makes each slot's PRIMARY a still light
    (USHADOW.ILB, f18 6, kind 0, f20 = 102) whose SUB is the sprite sequence; ground units carry their shadow the
    same way.  Our 24 sprite slots get the same: a still glow (per facing direction: 104 + dir - 1) as primary, the
    sprite chained under it.  ANIMATED_LIGHT instead writes a kind-4 primary with the 72 per-frame glows - the
    engine's draw loops (TUnitHS.Show / TTacticalCombatUnitHS.Show) walk the chain generically, yet the game
    crashed with it (10/13, cause not found)."""
    out = bytearray(blob[:4]); i = 4; n = 0
    while n < 24:
        assert blob[i] == 0 and struct.unpack_from("<I", blob, i + 1)[0] == len(path) and blob[i + 5:i + 5 + len(path)] == path, "unexpected entry @%d" % i
        o = i + 5 + len(path) + 3
        typ, xs, ys, z, cnt = struct.unpack_from("<iiiiI", blob, o)
        end = o + 20 + 4 * cnt + 1                      # + the sequence's hasSub byte
        ids = struct.unpack_from("<%dI" % cnt, blob, o + 20); d = ids[0] // 100
        new_ids = None
        if cnt == 8 and [x % 100 for x in ids] == list(range(1, 9)):          # fly / idle loop -> smooth 12-frame loop
            new_ids = [d * 100 + LOOP_FIRST + k for k in range(LOOP_COUNT)]
            ids = new_ids; cnt = LOOP_COUNT
            blob = blob[:o - 2] + bytes([LOOP_DELAY]) + blob[o - 1:]      # f18 (frame delay) of this sequence
        if ANIMATED_LIGHT:
            gids = [ANIM_GLOW_BASE + (x // 100 - 1) * GLOW_PER_DIR + (x % 100 - 1) for x in ids]
            hdr3 = bytes([0x7F]) + blob[i + 5 + len(path) + 1:o]          # f8 = 0x7F = glow-sync marker (patch_ilpack_glow_sync_v1.py: the light follows the sub frame); f18/kind copied
            light = (b"\x00" + struct.pack("<I", 17) + b"UNITS\USHADOW.ILB" + hdr3
                     + struct.pack("<iiiiI", typ, GLOW_XS, GLOW_YS, 0, cnt) + struct.pack("<%dI" % cnt, *gids))
        else:
            light = b"\x00" + struct.pack("<I", 17) + b"UNITS\USHADOW.ILB" + b"\x00\x06\x00" + struct.pack("<iii", GLOW_BASE_ID + d - 1, GLOW_XS, GLOW_YS)
        ent = (blob[i + 1:o] + struct.pack("<iiiiI", typ, xs - PAD, ys, z, cnt)     # sprite drawn PAD further left (wider frames)
               + struct.pack("<%dI" % cnt, *ids) + blob[end - 1:end])                # (+ the smooth loop's ids) + hasSub byte
        out += light + b"\x01" + ent; i = end; n += 1
    assert n == 24, n
    out += blob[i:]
    return bytes(out)


def unitgfx_record(eagle, face_index):
    classid, f, wide = rec_fields(eagle)
    assert classid == 0x20210
    nf = dict(f); nf.pop(0x1, None)
    nf[0x3] = struct.pack("<I", UNIT)
    old, new = b"UNITS\\ANIMALS\\EAGLE.ILB", b"UNITS\\ANIMALS\\PHNIX.ILB"
    assert len(old) == len(new) and nf[0x5].count(old) >= 1, nf[0x5].count(old)      # once per animation sequence
    nf[0x5] = add_glow_layer(nf[0x5].replace(old, new), new)   # v14: no sequence rotation (rotated lists skip frames: the engine walks consecutive ids from the first entry; the panel pose = phoenix_art.POSE_SHIFT); v15: + the Fire Elemental's glow layer
    nf[0x6] = sstr("FACES\\ADD_UNITS.ILB"); nf[0x7] = sstr("Phoenix"); nf[0x8] = struct.pack("<I", face_index)
    return rec_build(classid, nf, True)


# ---------------------------------------------------------------- colours
def fire_ramp(lum):
    """0..1 luminance -> (r, g, b): crimson -> orange -> gold -> white-hot."""
    stops = [(0.00, (70, 6, 4)), (0.25, (170, 28, 8)), (0.50, (240, 110, 15)), (0.75, (255, 200, 70)), (1.00, (255, 248, 210))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if lum <= t1:
            k = (lum - t0) / (t1 - t0)
            return tuple(int(round(c0[i] + (c1[i] - c0[i]) * k)) for i in range(3))
    return stops[-1][1]


def lerp3(a, b, k):
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


def c565(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


# ---------------------------------------------------------------- the sprite (8-bit RLE frames)
def rle8_decode(px, r):
    """Record -> 64x64 list of palette indexes (0 = transparent)."""
    a = [[0] * r["w"] for _ in range(r["h"])]; o = r["off"]; tr = r["transp"]
    for y in range(r["ch"]):
        L = struct.unpack_from("<I", px, o)[0]; s = px[o + 4:o + L]; o += L; x = r["cx"]; i = 0
        while i < len(s):
            b = s[i]; i += 1
            if b == tr: x += s[i]; i += 1
            else: a[r["cy"] + y][x] = b; x += 1
    return a


def rle8_encode(a, tr=0):
    """64x64 indexes -> (data, cx, cy, cw, ch): per row u32 length + stream, transparent runs = (tr, count<=255)."""
    pts = [(x, y) for y, row in enumerate(a) for x, v in enumerate(row) if v]
    if not pts: return b"", 0, 0, 0, 0
    cx, cy = min(p[0] for p in pts), min(p[1] for p in pts)
    cw, ch = max(p[0] for p in pts) - cx + 1, max(p[1] for p in pts) - cy + 1
    out = bytearray()
    for y in range(cy, cy + ch):
        s = bytearray(); run = 0
        for x in range(cx, cx + cw):
            v = a[y][x]
            if v == tr:
                run += 1
                if run == 255: s += bytes([tr, 255]); run = 0
            else:
                if run: s += bytes([tr, run]); run = 0
                s.append(v)
        if run: s += bytes([tr, run])
        out += struct.pack("<I", len(s) + 4) + s
    return bytes(out), cx, cy, cw, ch


def nearest(pal, rgb):
    return min(range(1, 256), key=lambda i: sum((pal[i][k] - rgb[k]) ** 2 for k in range(3)))


def plume_points(bx, by, k, frame, L):
    """One tail plume: list of (x, y, t) along a swaying curve hanging from (bx, by)."""
    side = (-1.0, -0.5, 0.0, 0.5, 1.0)[k]; ph = (0.0, 1.3, 2.6, 3.9, 5.2)[k]
    pts = []
    for i in range(L):
        t = i / max(1, L - 1)
        sway = (0.6 + 1.4 * t) * math.sin(t * 3.6 + ph + frame * 0.55)              # ripple that travels with the wing-beat
        x = bx + side * (1.0 + 9.5 * t ** 1.15) + sway                               # v3: five plumes fanning out like a tail
        y = by + t * (L - 1)
        pts.append((x, y, t))
    return pts


def paint_phoenix_frame(a, frame, idx):
    """Add plumes / crest / wing flicks to a decoded frame (list of rows of palette indexes).  `idx` = palette
    indexes {"gold", "orange", "red", "white"}.  Only transparent pixels are painted (the bird stays on top)."""
    H, W = len(a), len(a[0])
    mask = [(x, y) for y in range(H) for x in range(W) if a[y][x]]
    if not mask: return a
    cxm = sum(p[0] for p in mask) / len(mask)
    col = [p for p in mask if abs(p[0] - cxm) <= 6]
    by = max(p[1] for p in col); bx = sum(p[0] for p in col if p[1] >= by - 2) / max(1, len([p for p in col if p[1] >= by - 2]))
    ty = min(p[1] for p in [p for p in mask if abs(p[0] - cxm) <= 8]); top = [p for p in mask if p[1] == ty and abs(p[0] - cxm) <= 8]
    tx = sum(p[0] for p in top) / len(top)
    def put(x, y, i):
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < W and 0 <= yi < H and a[yi][xi] == 0: a[yi][xi] = i
    def shade(t):
        return idx["white"] if t < 0.12 else idx["gold"] if t < 0.4 else idx["orange"] if t < 0.75 else idx["red"]
    # tail plumes (back ones first so the middle one lies on top)
    # v3: the fan starts BEHIND the lower body (6 px above the talons) so it reads as a tail, not as longer legs;
    # the outer plumes are shorter than the middle one; each plume is a solid tapering feather 4 -> 1 px wide
    root_y = by - 6
    L = max(10, min(20, H - 1 - int(root_y)))
    for k, Lk in ((0, L - 6), (4, L - 6), (1, L - 3), (3, L - 3), (2, L)):
        for x, y, t in plume_points(bx, root_y, k, frame, Lk):
            w = 4 if t < 0.25 else 3 if t < 0.5 else 2 if t < 0.8 else 1
            for dx in range(-(w // 2), w - w // 2):
                put(x + dx, y, shade(min(1.0, t + 0.18 * abs(dx))))
    # head crest: three tongues rising from the crown, flickering with the frame
    for j, (ox, h) in enumerate(((-2, 4), (0, 5), (2, 4))):
        hh = h + (1 if (frame + j) % 3 == 0 else 0)
        for i in range(hh):
            t = i / max(1, hh - 1)
            put(tx + ox + 0.6 * math.sin(frame * 0.7 + j), ty - 1 - i, idx["red"] if t > 0.7 else idx["orange"] if t > 0.3 else idx["gold"])
    # wing-tip flicks on the widest rows
    rows = {}
    for x, y in mask: rows.setdefault(y, []).append(x)
    widest = sorted(rows, key=lambda y: max(rows[y]) - min(rows[y]), reverse=True)[:3]
    for n, y in enumerate(widest):
        xl, xr = min(rows[y]), max(rows[y])
        for s in range(1, 3 + ((frame + n) % 2)):
            put(xl - s, y - (s // 2), idx["orange"] if s == 1 else idx["red"])
            put(xr + s, y - (s // 2), idx["orange"] if s == 1 else idx["red"])
    return a


def brown_orange(lum):
    """0..1 luminance -> the phoenix wing colours: dark brown -> brown orange -> orange -> light orange."""
    stops = [(0.0, (74, 22, 8)), (0.3, (140, 58, 18)), (0.55, (190, 96, 26)), (0.8, (226, 128, 38)), (1.0, (244, 170, 70))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if lum <= t1:
            k = (lum - t0) / (t1 - t0)
            return tuple(int(round(c0[i] + (c1[i] - c0[i]) * k)) for i in range(3))
    return stops[-1][1]


WING_SCALE = 1.15          # the eagle's wings, enlarged
GLOW_RGB = (255, 120, 24)  # halo colour
def build_palette(frames_rgba):
    """255 colours (median cut over every opaque pixel of every frame) + index 0 = the transparent key."""
    pix = [p[:3] for im in frames_rgba.values() for p in im.getdata() if p[3]]
    strip = Image.new("RGB", (len(pix), 1)); strip.putdata(pix)
    q = strip.quantize(colors=255, method=Image.MEDIANCUT, dither=Image.NONE)
    pal = q.getpalette()[:255 * 3]
    return [(87, 39, 71)] + [tuple(pal[3 * i:3 * i + 3]) for i in range(255)]


def phoenix_sprite(preview=None):
    """v15 (2026-10-13): the phoenix_art render (eagle-measured wing motion, POSE_SHIFT) as an 8-bit palette sprite
    again (type-2 RLE in the eagle's record skeleton) - the glow is the Fire Elemental's separate LIGHT LAYER in
    the gfx record (add_glow_layer), not a draw mode: the 258/65 attempt showed no glow in game."""
    import numpy as np
    import phoenix_art as PA
    raw = open(EAGLE_ILB, "rb").read()
    lib = ilbcodec.read(raw); assert len(lib["palettes"]) == 1
    PA.FW = 64 + 2 * PAD; PA.CX = 31.5 + PAD
    fr = PA.frames()
    NEWPAL = build_palette(fr); palarr = np.array(NEWPAL[1:], np.float32)
    newpal = bytearray()
    for c in NEWPAL: newpal += bytes(c) + bytes(1)
    out_px = bytearray(); frames = {}
    have = {img["id"]: img for img in lib["images"]}
    for iid in sorted(fr):                                   # 11/01: the smooth loop frames (ids 13..24) get records
        if iid in have: continue
        t = have[iid // 100 * 100 + 1]
        rec = ilbcodec.Rec(t["parts"][0]); rec.update(name=b"PHNIX%03d.BMP" % iid)
        have[iid] = {"id": iid, "composite": False, "parts": [rec], "empty": False}
    lib["images"] = [have[k] for k in sorted(have)]
    for img in lib["images"]:
        if img["empty"]: continue
        r = img["parts"][0]; im = fr[img["id"]]
        arr = np.array(im).astype(np.float32); H, W = arr.shape[:2]
        rgb = arr[:, :, :3].reshape(-1, 3); alpha = arr[:, :, 3].reshape(-1)
        d2 = ((rgb[:, None, :] - palarr[None, :, :]) ** 2).sum(axis=2)
        ix = (d2.argmin(axis=1) + 1); ix[alpha < 128] = 0
        a = ix.reshape(H, W).tolist()
        data, cx, cy, cw, ch = rle8_encode(a, 0)
        r.update(name=b"PHNIX" + r["name"][5:], off=len(out_px), size=len(data), cx=cx, cy=cy, cw=cw, ch=ch, transp=0,
                 w=W, totw=W)
        out_px += data; frames[img["id"]] = a
    lib["palettes"] = [bytes(newpal)]; lib["pixeldata"] = bytes(out_px)
    out = ilbcodec.write(lib); chk = ilbcodec.read(out); assert len(chk["images"]) == len(lib["images"]) and chk["images"][0]["parts"][0]["type"] == 2
    if preview is not None: preview["frames"] = frames; preview["pal"] = NEWPAL
    return out


# ---------------------------------------------------------------- the portrait
FIRE_ILB = game_file(os.path.join("Images", "Effects", "FireLg.ILB"))


def decode_rle16(r):
    """A type-18 (transparent RLE16) record with inline data -> RGBA crop (key = transparent).  Rows: u32 length +
    u16 stream; a key word followed by (byte count / 2) = transparent run; an odd word count pads the row by a word."""
    data = r["inline"]; im = Image.new("RGBA", (r["w"], r["h"]), (0, 0, 0, 0)); p = im.load(); o = 0; tr = r["transp"]
    for y in range(r["ch"]):
        L = struct.unpack_from("<I", data, o)[0]; n = (L - 4) // 2
        words = struct.unpack_from("<%dH" % n, data, o + 4); o += L + (2 if n % 2 else 0)
        x = r["cx"]; i = 0
        while i < len(words):
            w = words[i]; i += 1
            if w == tr: x += words[i] // 2; i += 1
            else:
                if 0 <= x < r["w"]: p[x, r["cy"] + y] = c565(w) + (255,)
                x += 1
    return im.crop((r["cx"], r["cy"], r["cx"] + r["cw"], r["cy"] + r["ch"]))


def eagle_portrait():
    lib = ilbcodec.read(FACES_ILB)
    img = next(i for i in lib["images"] if i["id"] == EAGLE_FACE_ID); r = img["parts"][0]
    assert r["type"] == 16 and r["size"] == r["w"] * r["h"] * 2
    src = lib["pixeldata"][r["off"]:r["off"] + r["size"]]
    im = Image.new("RGB", (r["w"], r["h"])); p = im.load()
    for y in range(r["h"]):
        for x in range(r["w"]):
            p[x, y] = c565(struct.unpack_from("<H", src, 2 * (y * r["w"] + x))[0])
    return im


PHOTO = game_file(os.path.join("art import export", "phoenix.jpg"))


NEWPORTRAIT = game_file(os.path.join("art import export", "newphoenix.png"))


def phoenix_face_pixels():
    """103x128 RGB565 bytes of the portrait = the user's newphoenix.png, centre-cropped to the 103:128 aspect and
    resized with Lanczos (no other processing)."""
    im = Image.open(NEWPORTRAIT).convert("RGB")
    iw, ih = im.size
    if iw / ih > 103 / 128:
        w = int(ih * 103 / 128); im = im.crop(((iw - w) // 2, 0, (iw - w) // 2 + w, ih))
    else:
        h = int(iw * 128 / 103); im = im.crop((0, (ih - h) // 2, iw, (ih - h) // 2 + h))
    im = im.resize((103, 128), Image.LANCZOS)
    W, H = im.size; p = im.load()
    out = [[p[x, y][:3] for x in range(W)] for y in range(H)]
    data = bytearray()
    for y in range(H):
        for x in range(W):
            data += struct.pack("<H", rgb565(*out[y][x]))
    return bytes(data), W, H, out


def add_face(add_raw, pixels, W, H):
    """Append (or replace) the Phoenix record at the tail of Add_UNITS.ILB -> (new bytes, index)."""
    lib = ilbcodec.read(add_raw)
    mine = [i for i in lib["images"] if i["parts"] and i["parts"][0]["name"] == FACE_NAME]
    pix = bytearray(lib["pixeldata"])
    if mine:
        assert mine == lib["images"][-1:], "Phoenix record is not the last one"
        cut = mine[0]["parts"][0]["off"]; lib["images"] = lib["images"][:-1]; pix = pix[:cut]
    tmpl = lib["images"][-1]["parts"][0]
    rec = ilbcodec.Rec(tmpl); rec.update(name=FACE_NAME, w=W, h=H, totw=W, toth=H, size=len(pixels), off=len(pix), drawMode=0, blendValue=0)
    index = len(lib["images"])
    lib["images"].append({"id": index, "composite": False, "parts": [rec], "empty": False}); pix += pixels
    lib["pixeldata"] = bytes(pix)
    out = ilbcodec.write(lib); chk = ilbcodec.read(out); assert chk["images"][-1]["parts"][0]["name"] == FACE_NAME
    return out, index


def write_preview(pv, face, path):
    from PIL import Image
    PAL = pv["pal"]; frames = pv["frames"]; S = 3
    FWp = 64 + 2 * PAD
    sheet = Image.new("RGB", (12 * FWp * S + 103 * 3 + 20, 6 * 64 * S), (70, 96, 60)); p = sheet.load()
    for d in range(6):
        for f in range(12):
            a = frames[(d + 1) * 100 + f + 1]; ox, oy = f * FWp * S, d * 64 * S
            for y in range(64):
                for x in range(FWp):
                    if a[y][x]:
                        for yy in range(S):
                            for xx in range(S): p[ox + x * S + xx, oy + y * S + yy] = PAL[a[y][x]]
    ox = 12 * FWp * S + 10
    for y in range(128):
        for x in range(103):
            for yy in range(3):
                for xx in range(3): p[ox + x * 3 + xx, y * 3 + yy] = face[y][x]
    sheet.save(path); print("preview ->", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--stats", action="store_true", help="also rewrite the Unitres record (OFF by default since 10/31: the user edits the Phoenix's stats/abilities/description in the editor)")
    ap.add_argument("--still-glow", action="store_true", help="write the per-direction STILL glows (104..109) instead of the animated light layer")
    a = ap.parse_args()
    global ANIMATED_LIGHT
    ANIMATED_LIGHT = not a.still_glow
    if a.revert:
        for f in (UNITRES, UNITGFX, ADD_FACES, USHADOW):
            b = bak_path(f, BAK_SUFFIX, create=False)
            if os.path.exists(b): shutil.copy2(b, f); print("restored", f)
            else: print("no backup for", f)
        for f in (PHNIX_ILB, OLD_FACE):
            if os.path.exists(f): os.remove(f); print("deleted", f)
        return 0
    pv = {}
    sprite = phoenix_sprite(pv)
    glows = phoenix_glows(pv["frames"], pv["pal"]); fglows = phoenix_frame_glows(pv["frames"])
    ush_raw = open(USHADOW, "rb").read(); new_ush = add_anim_glow_images(add_glow_images(ush_raw, glows), fglows)
    face_px, W, H, face_rgb = phoenix_face_pixels()
    if a.preview:
        write_preview(pv, face_rgb, os.path.join(os.path.dirname(os.path.abspath(__file__)), "phoenix_preview.png"))
        gs = Image.new("RGB", (6 * 70, 70), (40, 60, 40))
        for d in range(1, 7): gs.paste(glows[d], ((d - 1) * 70, 0))
        gs.resize((gs.width * 3, gs.height * 3), Image.NEAREST).save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "phoenix_glow_preview.png")); return 0
    add_raw = open(ADD_FACES, "rb").read()
    new_add, face_index = add_face(add_raw, face_px, W, H)
    ur = open(UNITRES, "rb").read(); ug = open(UNITGFX, "rb").read()
    pr, pg = split(ur), split(ug)
    assert join(pr) == ur and join(pg) == ug, "round-trip of the unchanged files failed"
    assert UNIT in pr["recs"], "Unitres has no child %d" % UNIT
    if a.stats:
        pr["recs"][UNIT] = unitres_record(pr["recs"][UNIT])
    if UNIT not in pg["recs"]:
        pg["order"] = sorted(pg["order"] + [UNIT]); pg["kid_form"][UNIT] = True
    pg["recs"][UNIT] = unitgfx_record(pg["recs"][234], face_index)
    new_ur, new_ug = join(pr), join(pg)
    for old, new in ((ur, new_ur), (ug, new_ug)):
        p0, p1 = split(old), split(new)
        assert all(p1["recs"][c] == p0["recs"][c] for c in p0["order"] if c != UNIT) and UNIT in p1["recs"]
    c, f, w = rec_fields(split(new_ur)["recs"][UNIT])
    print("Unitres 271: %s lvl %d  %d/%d/%d/%d/%d/%d cost %d, gfx %d, base abilities %s" % (
        f[0xA][1:].decode(), f[0x14][0], f[0xE][0], f[0xF][0], f[0x10][0], f[0x11][0], f[0x12][0], f[0x13][0],
        struct.unpack_from("<I", f[0x1B])[0], struct.unpack_from("<I", f[0x8])[0], [hex(i) for i in BASE_AB]))
    c, f, w = rec_fields(split(new_ug)["recs"][UNIT])
    print("Unitgfx 271: %s sprite %s face %s[%d]" % (f[0x7][1:].decode(), f[0x5][9:9 + 23].decode(), f[0x6][1:].decode(), struct.unpack_from("<I", f[0x8])[0]))
    states = {UNITRES: ur == new_ur, UNITGFX: ug == new_ug, ADD_FACES: add_raw == new_add, USHADOW: ush_raw == new_ush,
              PHNIX_ILB: os.path.exists(PHNIX_ILB) and open(PHNIX_ILB, "rb").read() == sprite,
              OLD_FACE: not os.path.exists(OLD_FACE)}
    print("state: " + ", ".join("%s %s" % (os.path.basename(k), "up to date" if v else "CHANGES") for k, v in states.items()))
    if all(states.values()): print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert / --preview)."); return 0
    for f, cur, new in ((UNITRES, ur, new_ur), (UNITGFX, ug, new_ug), (ADD_FACES, add_raw, new_add), (USHADOW, ush_raw, new_ush)):
        if cur == new: continue
        b = bak_path(f, BAK_SUFFIX)
        if not os.path.exists(b): shutil.copy2(f, b); print("backup ->", b)
        open(f, "wb").write(new); print("written", f)
    open(PHNIX_ILB, "wb").write(sprite); print("written", PHNIX_ILB)
    if os.path.exists(OLD_FACE): os.remove(OLD_FACE); print("deleted", OLD_FACE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
