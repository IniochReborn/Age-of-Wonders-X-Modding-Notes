#!/usr/bin/env python3
r"""
Int\TBWin.ILB: append the images for the taskbar "editor open" lamp (2026-09-21).
Companion of patch_editor_indicator_v1.py (AoWx.exe), which raises the strategic player-indicator frame PInd
from 17 to 23 px and draws a green lamp in a new socket row above each player's race icon.

Vanilla TBWin.ILB (53 images, RLESprite16, transp 0x2981): 0x1D/0x1E/0x1F = PlyrIndL.BMP left cap 2x17 / slot
5x17 / right cap 2x17 (TAoWFrame frHorizLine tiles ILIndexLine, +1, +2); slot rows: 0 dark edge, 1-10 gold icon
window (race icon 4x9 drawn at y+2), 11-15 lamp socket (5x5 lamps 0x2D..0x32 = off..bright, ended-turn lamp
0x32 drawn at y+11), 16 light bottom edge.
Appended (ids = indices):
  0x35 cap-left 2x23, 0x36 slot 5x23, 0x37 cap-right 2x23 = 6 TRANSPARENT rows + the 17-px tiles (the frame
        grows upward but nothing is drawn there; icon at y+8, ended-turn lamp at y+17);
  0x38 editor lamp bright 8x7, 0x39 editor lamp dim 8x7 = self-framed mini socket (dark edge ring, 6-wide gold rim, 4x2
        light in the editor-icon green 0,224,0, shadow row) drawn at (x+1, y+0) only above players whose editor is open
        (v3: v2's 5x6 lamp lacked the right rim - the tile socket borrows it from the next tile);
  0x3A / 0x3B = the same lamp in RED (bright / dim) for the 'second game instance' state (v6 2026-09-22).
Encoding = the game's RLE16 (per row: u32 len, run stream of u16 (transparent run = key, 2*count), pad u16 if the
stream has an odd count; any opaque pixel equal to the key is nudged).  v2 2026-09-21 (v1 drew a full-width socket row).  Backup Int\TBWin.ILB.bak_edlamp (in <game>\backup\).  Dry-run default; --apply;
--revert; --png <out> writes a preview.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "old modding tools", "research"))
import ilbcodec  # noqa: E402

DEFAULT_ILB = game_file(r"Int\TBWin.ILB")
BAK = ".bak_edlamp"
VANILLA_COUNT = 53
NEW_FIRST = 0x35
NEW_N = 8                   # 3 tiles + green bright/dim + red bright/dim (0x35..0x3B) + combat sword 0x3C (2026-11-16)
TRANSP = 0x2981


def rgb(v): return ((v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3)
def to565(r, g, b): return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def decode(lib, idx):
    r = lib['images'][idx]['parts'][0]; px = lib['pixeldata']
    data = px[r['off']:r['off'] + r['size']]; o = 0; back = r['transp']; rows = []
    for y in range(r['h']):
        ln = struct.unpack_from("<I", data, o)[0]; s = data[o + 4:o + ln]; o += ln
        if ((ln - 4) // 2) % 2 == 1:
            o += 2
        row = []; k = 0
        while k + 1 < len(s):
            v = struct.unpack_from("<H", s, k)[0]; k += 2
            if v == back:
                cnt = struct.unpack_from("<H", s, k)[0] // 2; k += 2; row += [None] * cnt
            else:
                row.append(v)
        rows.append(row[:r['w']])
    return rows


def encode(rows):
    out = bytearray()
    for row in rows:
        vals = []; i = 0
        while i < len(row):
            if row[i] is None:
                n = 0
                while i < len(row) and row[i] is None:
                    n += 1; i += 1
                vals += [TRANSP, 2 * n]
            else:
                vals.append((row[i] ^ 1) if row[i] == TRANSP else row[i]); i += 1
        out += struct.pack("<I", 4 + 2 * len(vals)) + b"".join(struct.pack("<H", v) for v in vals)
        if len(vals) % 2 == 1:
            out += struct.pack("<H", TRANSP)
    return bytes(out)


def lum(v):
    r, g, b = rgb(v); return 0.3 * r + 0.59 * g + 0.11 * b


def lamp7(bright, red=False):
    """8x7 self-framed socket: dark edge ring, 6-wide gold rim (= the vanilla socket incl. the rim borrowed from the next tile,
    so it centres on the turn lamp / race icon below), 4x2 green light (editor-icon green 0,224,0), shadow row."""
    D = to565(48, 56, 40); S1 = to565(80, 80, 72); S2 = to565(40, 32, 40)
    if bright:
        GT, GS, GB = to565(216, 204, 112), to565(200, 188, 96), to565(192, 184, 104)
        L1, L2 = (to565(232, 16, 16), to565(255, 48, 32)) if red else (to565(0, 224, 0), to565(16, 240, 16))
    else:
        GT, GS, GB = to565(200, 184, 88), to565(184, 168, 80), to565(176, 160, 80)
        L1, L2 = (to565(120, 0, 0), to565(144, 8, 8)) if red else (to565(0, 112, 0), to565(0, 136, 0))
    return [[D] * 8,
            [D, GT, GT, GT, GT, GT, GT, D],
            [D, GS, L1, L2, L2, L1, GS, D],
            [D, GS, L1, L2, L2, L1, GS, D],
            [D, GB, GB, GB, GB, GB, GB, D],
            [D, S1, S2, S2, S2, S2, S2, D],
            [D] * 8]


def sword():
    """4x9 (race-icon size) 'in combat' marker: steel sword, blade down, on dark red - shown instead of the race icon
    in a ~0.5 s blink while that player is in a battle (patch_editor_indicator_combat_v1.py)."""
    R, r = to565(150, 20, 20), to565(104, 12, 12)
    G, g = to565(240, 200, 72), to565(176, 136, 40)
    S, s, W = to565(232, 236, 244), to565(160, 168, 184), to565(255, 255, 255)
    return [[r, G, g, r],
            [R, g, g, R],
            [G, G, g, g],
            [R, W, s, R],
            [R, S, s, R],
            [R, S, s, R],
            [R, S, s, R],
            [R, S, s, R],
            [r, s, r, r]]


def tall(rows):
    return [[None] * len(rows[0]) for _ in range(6)] + rows[0:17]


def build(lib):
    t1d, t1e, t1f = (tall(decode(lib, i)) for i in (0x1D, 0x1E, 0x1F))
    return [(b"PlyrIndL.BMP", t1d), (b"PlyrIndL.BMP", t1e), (b"PlyrIndL.BMP", t1f),
            (b"EdLamp.BMP", lamp7(True)), (b"EdLamp.BMP", lamp7(False)),
            (b"EdLampR.BMP", lamp7(True, red=True)), (b"EdLampR.BMP", lamp7(False, red=True)),
            (b"CombatSw.BMP", sword())]


def make_record(template, name, rows, off):
    r = ilbcodec.Rec(template)
    r['name'] = name; r['w'] = len(rows[0]); r['h'] = len(rows); r['cw'] = r['w']; r['ch'] = r['h']
    r['cx'] = 0; r['cy'] = 0; r['xs'] = 0; r['ys'] = 0; r['off'] = off
    data = encode(rows); r['size'] = len(data); r['totw'] = r['w']; r['toth'] = r['h']
    return r, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ilb", nargs="?", default=DEFAULT_ILB)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--png")
    a = ap.parse_args()
    ilb = a.ilb; bak = bak_path(ilb, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, ilb); print(f"reverted {ilb} from {bak}"); return
    lib = ilbcodec.read(ilb); n = len(lib['images'])
    print(f"target: {ilb}: {n} images ({'vanilla' if n == VANILLA_COUNT else 'ALREADY PATCHED' if n == VANILLA_COUNT + NEW_N else 'UNKNOWN'})")
    if n not in (VANILLA_COUNT, VANILLA_COUNT + 5, VANILLA_COUNT + 7, VANILLA_COUNT + NEW_N):
        sys.exit("unexpected image count - refusing")
    if n != VANILLA_COUNT:
        src = ilbcodec.read(bak) if os.path.exists(bak) else None
        if src is None:
            print("already applied (no backup to rebuild from)"); return
        lib = src
    tmpl = lib['images'][0x1E]['parts'][0]
    imgs = build(lib); px = bytearray(lib['pixeldata']); recs = []
    for k, (name, rows) in enumerate(imgs):
        r, data = make_record(tmpl, name, rows, len(px)); px += data
        recs.append({'id': NEW_FIRST + k, 'composite': False, 'parts': [r], 'empty': False})
        print(f"  img {NEW_FIRST + k:#x} {name.decode()} {r['w']}x{r['h']} size {r['size']} off {r['off']}")
    if a.png:
        from PIL import Image
        W = 2 + 5 * 14 + 2; H = 23; im = Image.new("RGB", (W, H), (90, 110, 70))
        def blit(rows, x, y):
            for yy, row in enumerate(rows):
                for xx, v in enumerate(row):
                    if v is not None and 0 <= x + xx < W and 0 <= y + yy < H:
                        im.putpixel((x + xx, y + yy), rgb(v))
        blit(imgs[0][1], 0, 0)
        for k in range(14):
            blit(imgs[1][1], 2 + 5 * k, 0)
        blit(imgs[2][1], 72, 0)
        for k in range(6):
            blit(decode(lib, 0x20 + k), 3 + 5 * k, 8)
            if k in (1, 3):
                blit(decode(lib, 0x32), 2 + 5 * k, 17)
            if k in (0, 1):
                blit(imgs[3 + (k & 1)][1], 1 + 5 * k, 0)
            if k in (1, 4):
                blit(imgs[7][1], 3 + 5 * k, 8)
        im.resize((W * 8, H * 8), Image.NEAREST).save(a.png); print("preview ->", a.png)
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    out = dict(lib); out['images'] = list(lib['images']) + recs; out['pixeldata'] = bytes(px)
    blob = ilbcodec.write(out)
    chk = ilbcodec.read(blob); assert len(chk['images']) == VANILLA_COUNT + NEW_N
    if not os.path.exists(bak):
        shutil.copy2(ilb, bak); print(f"  backup -> {bak}")
    open(ilb, "wb").write(blob); print(f"applied: {ilb} now {len(blob)} B, {VANILLA_COUNT + NEW_N} images.")


if __name__ == "__main__":
    main()
