"""patch_hexgrid_thick_v1.py - F5 hex grid overlay with 2-px or 3-px lines (2026-10-18; --px 3 added the same day).

F5 (AoWx.exe key switch @0x451409 -> 0x451618) toggles byte [map+0xCA] on the combat map ([0x45EBDC]) or else the
strategic map ([0x45DF7C]).  Both map draws test it (strategic AoWEPACK 0x55778A78, combat AoWTCPCK 0x41BFE7) and call
AoWE.TAbstractAoWHSMap.DrawGrid 0x55772DA8, which blits image 7 of the AoWHSSet [0x558FA044]+0x78 library (+0x10) once
per visible field (fields with terrain 0xF skipped) = Images\Flags.ilb #7 "hexgrid.BMP": Sprite16 (raw 16-bit, colour
key 0xC618), 48x32, clip box 33x32 @ (0,0), drawMode 0x402 (smBlended + bmShadow, blend 50) - a 1-px darkening line on the
hex's top edge and its two left diagonals (the other three edges come from the neighbouring tiles).

Fix (data only, visual, MP-safe): every line pixel gets (px-1) more pixels on the tile's INSIDE - the top edge rows
below it, the diagonals columns to its right - so each hex edge is drawn px wide by exactly one tile (each tile only
thickens into its own hex, so neighbours never double-darken).  Same size record, pixel bytes rewritten in place;
colour, blend mode and blend value unchanged.  The thick image is always rebuilt from the vanilla pixels (the live image
when it is vanilla, else the backup), so 2 <-> 3 switches in place.

Usage:  py -3.10 patch_hexgrid_thick_v1.py [--apply | --revert] [--px 2|3] [--ilb PATH]   (dry-run by default; --px 3 default)
Backup: backup\Images\Flags.ilb.bak_hexgrid
"""
import os, sys, struct, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir

MAGIC_ID = 7                      # hexgrid.BMP
W_CLIP, H_CLIP = 33, 32
KEY = 0xC618                      # colour key (transparent)
SIZE = W_CLIP * H_CLIP * 2        # 2112
VANILLA_INK = 49

def locate(d):
    """Return (file offset of image 7's pixel bytes, record dict) by walking the ILB directory."""
    sys.path.insert(0, os.path.join(game_dir(), "modding tools"))
    from aowxlib import ilb
    lib = ilb.read(d)
    rec = [i for i in lib.images if i.id == MAGIC_ID][0].primary
    assert rec["type"] == 22 and rec["name"] == "hexgrid.BMP", rec
    assert (rec["cw"], rec["ch"], rec["cx"], rec["cy"], rec["size"], rec["transp"]) == (W_CLIP, H_CLIP, 0, 0, SIZE, KEY), rec
    return len(d) - len(lib.pixeldata) + rec["off"], rec

def inkcount(px):
    return sum(1 for (w,) in struct.iter_unpack("<H", px) if w != KEY)

def thicken(px, n):
    """vanilla pixels -> n-px lines"""
    words = list(struct.unpack("<%dH" % (W_CLIP * H_CLIP), px))
    ink = [(x, y) for y in range(H_CLIP) for x in range(W_CLIP) if words[y * W_CLIP + x] != KEY]
    assert len(ink) == VANILLA_INK
    cols = {words[y * W_CLIP + x] for x, y in ink}; assert len(cols) == 1, cols
    col = cols.pop()
    out = words[:]
    for x, y in ink:
        for k in range(1, n):
            nx, ny = (x, y + k) if (y == 0 and x >= 15) else (x + k, y)     # top edge -> rows below, diagonals -> columns right
            if 0 <= nx < W_CLIP and 0 <= ny < H_CLIP:
                out[ny * W_CLIP + nx] = col
    return struct.pack("<%dH" % len(out), *out)

def main():
    a = sys.argv[1:]
    mode = "apply" if "--apply" in a else "revert" if "--revert" in a else "dry"
    px = int(a[a.index("--px") + 1]) if "--px" in a else 3
    assert px in (2, 3), "--px must be 2 or 3"
    path = a[a.index("--ilb") + 1] if "--ilb" in a else os.path.join(game_dir(), "Images", "Flags.ilb")
    bak = bak_path(path, ".bak_hexgrid", create=(mode == "apply"))
    d = open(path, "rb").read()
    off, rec = locate(d)
    cur = d[off:off + SIZE]
    ink = inkcount(cur)
    if ink == VANILLA_INK:
        van = cur
    else:
        assert os.path.exists(bak), "image is not vanilla and there is no backup " + bak
        b = open(bak, "rb").read(); boff, _ = locate(b); van = b[boff:boff + SIZE]
        assert boff == off and inkcount(van) == VANILLA_INK, "backup image is not vanilla"
    states = {thicken(van, 2): "PATCHED (2-px)", thicken(van, 3): "PATCHED (3-px)", van: "VANILLA (1-px)"}
    state = states.get(cur, "UNKNOWN (%d ink px)" % ink)
    print("%s  image 7 pixels @file 0x%X: %s" % (path, off, state))
    assert not state.startswith("UNKNOWN"), "unexpected image state - refusing"
    want = thicken(van, px)
    if mode == "dry":
        if cur != want: print("dry-run: would set %d-px lines (%d -> %d ink px; run with --apply)" % (px, ink, inkcount(want)))
        else: print("dry-run: already %d-px" % px)
        return
    if mode == "apply":
        if cur == want: print("ALREADY PATCHED (%d-px)" % px); return
        if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f: f.seek(off); f.write(want)
        assert open(path, "rb").read()[off:off + SIZE] == want
        print("applied: %s -> %d-px (%d -> %d ink px)" % (state, px, ink, inkcount(want)))
    else:
        if cur == van: print("ALREADY VANILLA"); return
        with open(path, "r+b") as f: f.seek(off); f.write(van)
        print("reverted image 7 pixels to vanilla from", bak)

if __name__ == "__main__":
    main()
