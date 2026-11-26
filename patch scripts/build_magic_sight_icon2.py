#!/usr/bin/env python3
r"""Magic Sight — icon v2: paint the eye into ILB image id 151 (correct model).

CORRECTED MODEL (v1 got this wrong): SPELLICN.ILB icons are keyed by a per-
record IMAGE ID in the record header (`FF FF FF FF [id:u32] 00 01 00 00 16 00
00 00 03 [namelen] name`), NOT by record ordinal. Each image id = a PAIR of
records (cloud bg + glyph overlay). Spells.pfs icon refs + the editor's picker
both use these ids. v1 painted record ordinals 56/57 = image id 32 (a real
Death-sphere icon — hijacked!) and referenced id 56 which does not exist —
linking a nonexistent id is what killed ALL spell gfx on load.

Unreferenced image ids with real records: 52, 88, 151. **Id 151 = an unused
SI-Secret pair (recs 210/211)** — perfect for Magic Sight:
  rec 210 (40x35 RAW16, 2800B) = Secret blue-purple cloud -> bake the eye in
  rec 211 (35x20 sub @ (2,9), 1400B, key 0xFFFF) -> fill pure white (invisible)
Also restores v1's mispainted recs 56/57 (image id 32) from the backup.

Spells.pfs is NOT touched — assign icon id 151 + description + EnchW-style
side image/effects/sound in the EDITOR (its writer is the real serializer).

Backup Images/SPELLICN.ILB.bak_magicsight (already exists = pristine).
Dry-run; --apply / --revert (revert = restore whole ILB from backup).
"""
import os, shutil, struct, sys, math

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ILB = os.path.join(GAME, "Images", "SPELLICN.ILB")
BACKUP = ILB + ".bak_magicsight"

# HOW THE BOOK DRAWS ICONS (RE'd from screenshot + Concealment pair id 42 =
# rec68 cloud / rec69 glyph): frame 0 (cloud) is drawn ADDITIVELY as a glow
# backdrop (black edges vanish on the parchment), frame 1 (glyph) is drawn with
# WHITE keyed out = black ink on parchment. Earlier versions baked the eye into
# the cloud and blanked the glyph -> dark box, no ink. Correct arrangement:
#   rec 210 (frame 0) = ORIGINAL Secret cloud, untouched (glow backdrop)
#   rec 211 (frame 1) = black eye glyph on white (35x20 sub-frame @ (2,9))
INK = (0, 0, 0)
MISPAINTED = (56, 57)        # v1 targets (image id 32) — restore from backup
CLOUD_REC, OVERLAY_REC = 210, 211   # image id 151 (SI-Secret pair)


def ilb_records(d):
    base = struct.unpack_from('<I', d, 0x10)[0]
    recs = []
    i = 0
    while True:
        j = d.find(b'\x10\x93\x50\x56', i)
        if j < 0: break
        w  = struct.unpack_from('<I', d, j-0x10)[0]; h    = struct.unpack_from('<I', d, j-0xc)[0]
        sz = struct.unpack_from('<I', d, j-0x18)[0]; doff = struct.unpack_from('<I', d, j-0x14)[0]
        recs.append((w, h, sz, base + doff))
        i = j + 4
    return recs


def rgb565(r, g, b): return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def build_glyph(W=35, H=20):
    """Ink-on-white eye glyph for the 35x20 sub-frame — OUTLINE style matching
    the cast gfx: almond outline (sclera = parchment), iris ring, solid pupil,
    3 lash rays above. True = ink."""
    S = 8; WW, HH = W*S, H*S
    from PIL import Image, ImageDraw
    def canvas(): return Image.new('L', (WW, HH), 0)
    cx, cy = WW//2, int(12.4*S)          # eye sits low; lashes get the top
    ew, eh = int(15.5*S), int(6.9*S)
    def almond(scale):
        pts = []
        for t in range(0, 101):
            x = -1 + 2*t/100.0
            pts.append((cx + x*ew*scale, cy - (1 - x*x)*eh*scale))
        for t in range(0, 101):
            x = 1 - 2*t/100.0
            pts.append((cx + x*ew*scale, cy + (1 - x*x)*eh*scale))
        return pts
    outer = canvas(); do = ImageDraw.Draw(outer)   # almond fill
    inner = canvas(); dn = ImageDraw.Draw(inner)   # inner almond (erases fill)
    ink2  = canvas(); d2 = ImageDraw.Draw(ink2)    # ring + pupil + rays
    do.polygon(almond(1.0), fill=255)
    dn.polygon(almond(0.74), fill=255)
    ir = int(4.8*S); pr = int(2.4*S); LW = int(1.7*S)
    d2.ellipse([cx-ir, cy-ir, cx+ir, cy+ir], outline=255, width=LW)
    d2.ellipse([cx-pr, cy-pr, cx+pr, cy+pr], fill=255)
    for ang in (-38, 0, 38):                        # lash rays
        a = math.radians(ang - 90)
        r1 = eh + 1.6*S; r2 = eh + 5.4*S
        d2.line([cx+math.cos(a)*r1*1.35, cy+math.sin(a)*r1,
                 cx+math.cos(a)*r2*1.35, cy+math.sin(a)*r2], fill=255, width=LW)
    def down(im):
        sm = im.resize((W, H), Image.LANCZOS)
        p = sm.load()
        return [[p[x, y] > 115 for x in range(W)] for y in range(H)]
    m_out, m_in, m_ink2 = down(outer), down(inner), down(ink2)
    return [[(m_out[y][x] and not m_in[y][x]) or m_ink2[y][x]
             for x in range(W)] for y in range(H)]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BACKUP):
            shutil.copy2(BACKUP, ILB); print("ILB restored from backup"); return 0
        print("no backup"); return 1
    d = bytearray(open(ILB, 'rb').read())
    bak = open(BACKUP, 'rb').read()
    assert len(d) == len(bak)
    recs = ilb_records(bak)
    # 1) restore v1 mispaint (image id 32)
    for k in MISPAINTED:
        w, h, sz, off = recs[k]
        d[off:off+sz] = bak[off:off+sz]
    # 2) frame 0: restore the ORIGINAL Secret cloud untouched (glow backdrop)
    w, h, sz, off = recs[CLOUD_REC]
    assert (w, h, sz) == (40, 35, 2800), (w, h, sz)
    d[off:off+sz] = bak[off:off+sz]
    # 3) frame 1: black eye glyph on white in the 35x20 sub-frame
    w2, h2, sz2, off2 = recs[OVERLAY_REC]
    assert sz2 == 1400, sz2
    glyph = build_glyph(35, 20)
    ink = rgb565(*INK)
    for y in range(20):
        for x in range(35):
            struct.pack_into('<H', d, off2 + (y*35 + x)*2,
                             ink if glyph[y][x] else 0xFFFF)
    print("restored recs %s + rec %d (original cloud); painted rec %d (ink eye glyph) = image id 151"
          % (MISPAINTED, CLOUD_REC, OVERLAY_REC))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    open(ILB, 'wb').write(d); print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
