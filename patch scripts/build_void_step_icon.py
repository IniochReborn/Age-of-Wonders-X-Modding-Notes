#!/usr/bin/env python3
r"""Void Step (ex Warp Self) — spellbook icon: person upper body dissolving
into teleport rings, on the Secret-sphere cloud.

Icon model (see build_magic_sight_icon2.py): image id 52 = pair recs 88/89 in
Images/SPELLICN.ILB. Rec 88 (40x35 cloud, drawn additively) currently holds a
greenish Earth-style cloud — replaced with a copy of the Secret dark
blue-purple cloud (rec 144 = Summon Mermaid's id-88 pair cloud; identical to
Magic Sight's rec 210). Rec 89 (40x35 glyph, colorkey in its header = 0x4148,
non-key pixels drawn as ink) currently holds the placeholder boot — repainted:
head + shoulders/torso silhouette (ragged dissolve at the waist) above three
concentric ellipse rings.

Record headers are untouched (the glyph is painted on the EXISTING colorkey
read from rec 89's header). Backup Images/SPELLICN.ILB.bak_voidstep.
Dry-run default; --apply / --revert. --preview prints ASCII art.
"""
import os, shutil, struct, sys, math

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ILB = os.path.join(GAME, "Images", "SPELLICN.ILB")
BAK = ILB + ".bak_voidstep"

CLOUD_REC, GLYPH_REC = 88, 89      # image id 52 pair (Void Step)
SECRET_CLOUD_REC = 144             # image id 88 pair cloud (Summon Mermaid, Secret)


def ilb_records(d):
    base = struct.unpack_from('<I', d, 0x10)[0]
    recs = []; i = 0
    while True:
        j = d.find(b'\x10\x93\x50\x56', i)
        if j < 0: break
        w, h, sx, sy, key = struct.unpack_from('<5I', d, j+4)
        sz = struct.unpack_from('<I', d, j-0x18)[0]
        doff = struct.unpack_from('<I', d, j-0x14)[0]
        recs.append((w, h, sx, sy, key, sz, base + doff))
        i = j + 4
    return recs


def build_glyph(W=40, H=35):
    """True = ink. Person upper body (head, shoulders, torso) dissolving at the
    waist; three teleport rings below."""
    from PIL import Image, ImageDraw
    S = 8; WW, HH = W*S, H*S
    im = Image.new('L', (WW, HH), 0)
    dr = ImageDraw.Draw(im)
    cx = 20*S
    # head
    hr = 3.4*S
    dr.ellipse([cx-hr, 2.2*S, cx+hr, 2.2*S+2*hr], fill=255)
    # neck + shoulders + torso (narrower, so the arms read beside it)
    dr.polygon([
        (cx-1.8*S, 8.6*S), (cx+1.8*S, 8.6*S),          # neck
        (cx+5.0*S, 10.2*S), (cx+4.2*S, 21.7*S),        # right side, down THROUGH
        (cx-4.2*S, 21.7*S), (cx-5.0*S, 10.2*S),        # ring 1 (dissolve mid-ring)
    ], fill=255)
    # arms: outstretched wide like the Concealment figure, sloping slightly
    # down; hands may reach as wide as the top ring (fine per user)
    for sgn in (-1, 1):
        dr.line([cx+sgn*3.4*S, 10.9*S, cx+sgn*11.6*S, 17.2*S],
                fill=255, width=int(3.2*S))             # spread arm, angled down
        hr2 = 1.35*S                                    # hand blob at the tip
        dr.ellipse([cx+sgn*12.0*S-hr2, 17.6*S-hr2,
                    cx+sgn*12.0*S+hr2, 17.6*S+hr2], fill=255)
    # ragged dissolve at the torso's lower end (mid ring 1)
    for k, nx in enumerate(range(-5, 6, 2)):
        depth = (1.7 if k % 2 == 0 else 0.7) * S
        dr.rectangle([cx+nx*S-0.55*S, 21.7*S-depth, cx+nx*S+0.55*S, 21.8*S+2], fill=0)
    # teleport rings (outlined ellipses, wide->narrow going down)
    LW = max(2, int(1.2*S))
    for cy, rx, ry in ((20.8, 12.5, 2.6), (25.6, 9.0, 2.1), (29.8, 5.2, 1.6)):
        dr.ellipse([cx-rx*S, (cy-ry)*S, cx+rx*S, (cy+ry)*S], outline=255, width=LW)
    sm = im.resize((W, H), Image.LANCZOS)
    p = sm.load()
    m = [[p[x, y] > 110 for x in range(W)] for y in range(H)]
    for y in range(H):                     # enforce left/right symmetry
        for x in range(W//2, W):
            m[y][x] = m[y][W-1-x]
    return m


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, ILB); print("ILB restored"); return 0
        print("no backup"); return 1
    d = bytearray(open(ILB, 'rb').read())
    recs = ilb_records(bytes(d))
    cw, ch, _, _, _, csz, coff = recs[CLOUD_REC]
    sw, sh, _, _, _, ssz, soff = recs[SECRET_CLOUD_REC]
    gw, gh, gx, gy, gkey, gsz, goff = recs[GLYPH_REC]
    assert (cw, ch, csz) == (40, 35, 2800), (cw, ch, csz)
    assert (sw, sh, ssz) == (40, 35, 2800), (sw, sh, ssz)
    assert (gw, gh, gsz) == (40, 35, 2800), (gw, gh, gsz)
    # cloud: Secret dark blue-purple
    d[coff:coff+csz] = d[soff:soff+ssz]
    # glyph: ink silhouette + rings on the record's own colorkey
    glyph = build_glyph(gw, gh)
    ink = 0x0000
    key = gkey & 0xFFFF
    assert ink != key
    for y in range(gh):
        for x in range(gw):
            struct.pack_into('<H', d, goff + (y*gw + x)*2, ink if glyph[y][x] else key)
    if "--preview" in sys.argv:
        for y in range(gh):
            print(''.join('#' if glyph[y][x] else '.' for x in range(gw)))
    print("rec %d cloud <- Secret cloud (rec %d); rec %d glyph repainted (key %04x)"
          % (CLOUD_REC, SECRET_CLOUD_REC, GLYPH_REC, key))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(ILB, BAK); print("Backup ->", os.path.basename(BAK))
    open(ILB, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
