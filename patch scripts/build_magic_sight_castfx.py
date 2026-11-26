#!/usr/bin/env python3
r"""Magic Sight — cast FX: fade-in/out glowing eye (like Enchant Weapon's sword).

RE'd model: EnchW's cast overlay = one gfx-blob entry `EFFECTS\MAGIC.ILB` with
an explicit FRAME LIST: [path][3B flags][defaultid:u32][xoff][yoff][0][count:u32]
[count x frameid:u32] — 27 frames = 7x 0x3E7 (blank delay) + sword image ids
0x46..0x59 (EnchWpn00-19, fade baked into frame brightness; additive-on-black).

We build a NEW ILB `Images/Effects/MSight.ILB` (touches no vanilla art) with 16
frames of a glowing violet eye, fade baked (ramp in -> hold -> ramp out), 64x64
RAW16 on black.

ILB v4 container (RE'd from ILPACK.dpl TCustomImageLibrary.LoadFromStream
@0x5521A9C0, v4 branch @0x5521AB7E — header dword @8 is a FLOAT version, 4.0):
  header 0x18: ['\x04ILB'][0x40F000][float 4.0][hdrend=0x18][base][filesize]
  record stream (0x18..base, parsed from a memory copy):
    [palette count:u32 = 0]  (TPaletteManager.LoadFromStream reads this first)
    repeat: [image id:u32]
            [classtag:u32 = 0x16]  (mapper 0x5521baac matches a registered
             class by its GetClassTag vcall [+0x68]; 0x16 = plain 16bpp image;
             SPELLICN uses 0x100 = a wrapper class with a nested 0x16 node)
            [0x03][namelen:u32][name][cellw][cellh][12B zeros][0x01]
            [size][doff (rel. to base)][cellw][cellh][02 03 00 00][0x64]
            [pixfmt 0x56509310][subw][subh][xoff][yoff][key:u32]
            [extra:u32 = 0xFFFFFFFF]
    final terminator id: [0xFFFFFFFF]
  pixel data @ base (RAW16 when size == w*h*2).
The first (hang) attempt had garbage prefixes instead of this layout — the
parser read body bytes as ids -> SetLength(garbage)/giant string reads -> hang.

Then Spells.pfs record 210's MAGIC.ILB entry is rewired: path -> EFFECTS\
MSIGHT.ILB, default id 0, frames = 7 delays + ids 0..15 (23 total); record
rebuilt + trailing CRC-32 recomputed (pfs = [0x2144DF1C][payload][crc32]).

Backups: none needed for MSight.ILB (new file; revert = delete);
Spells.pfs handled in place with CRC (previous state = .bak_castfx).
Dry-run; --apply / --revert.
"""
import os, shutil, struct, sys, math, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
NEWILB = os.path.join(GAME, "Images", "Effects", "MSight.ILB")
PFS = os.path.join(GAME, "Release", "Spells.pfs")
PFS_BAK = PFS + ".bak_castfx"

NFRAMES = 16
CELL = 64
DELAYS = 7                       # blank frames before the eye appears (as EnchW)
FADE = [0.16, 0.32, 0.50, 0.68, 0.84, 0.95, 1.0, 1.0,
        1.0, 0.92, 0.80, 0.66, 0.50, 0.35, 0.22, 0.11]
assert len(FADE) == NFRAMES


def rgb565(r, g, b): return ((int(r) >> 3) << 11) | ((int(g) >> 2) << 5) | (int(b) >> 3)


def draw_frames():
    """16 RGB frames (64x64) of the glowing eye on black, fade baked."""
    from PIL import Image, ImageDraw, ImageFilter
    S = 4; W = CELL * S
    base = Image.new('RGB', (W, W), (0, 0, 0))
    dr = ImageDraw.Draw(base)
    cx = cy = W // 2
    ew, eh = 24 * S, 12 * S
    def almond(scale):
        pts = []
        for t in range(0, 101):
            x = -1 + 2 * t / 100.0
            pts.append((cx + x * ew * scale, cy - (1 - x * x) * eh * scale))
        for t in range(0, 101):
            x = 1 - 2 * t / 100.0
            pts.append((cx + x * ew * scale, cy + (1 - x * x) * eh * scale))
        return pts
    # soft violet glow backdrop
    glow = Image.new('RGB', (W, W), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r, c in ((30 * S, (26, 14, 44)), (22 * S, (52, 28, 86)), (15 * S, (78, 44, 128))):
        gd.ellipse([cx - r, cy - r * 0.72, cx + r, cy + r * 0.72], fill=c)
    glow = glow.filter(ImageFilter.GaussianBlur(6 * S))
    base = Image.blend(base, glow, 1.0)
    dr = ImageDraw.Draw(base)
    LW = int(2.2 * S)
    dr.polygon(almond(1.0), outline=(232, 218, 255), width=LW)
    ir = int(8.2 * S)
    dr.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], outline=(186, 140, 255), width=LW)
    pr = int(3.6 * S)
    dr.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=(255, 250, 255))
    for ang in (-40, 0, 40):
        a = math.radians(ang - 90)
        r1 = eh + 2.5 * S; r2 = eh + 8.5 * S
        dr.line([cx + math.cos(a) * r1 * 1.3, cy + math.sin(a) * r1,
                 cx + math.cos(a) * r2 * 1.3, cy + math.sin(a) * r2],
                fill=(214, 192, 255), width=LW)
    master = base.resize((CELL, CELL), Image.LANCZOS)
    frames = []
    for f in FADE:
        frames.append(master.point(lambda v: int(v * f)))
    return frames


def build_ilb():
    frames = draw_frames()
    NAME = "MSightEy%02d.BMP"
    # body layout after the per-record prefix (cloned from Magic.ILB rec4):
    def body(idx, doff):
        nm = (NAME % idx).encode()
        b = struct.pack('<IB', 0x16, 3)
        b += struct.pack('<I', len(nm)) + nm
        b += struct.pack('<II', CELL, CELL)
        b += b'\0' * 12
        b += b'\x01'
        b += struct.pack('<II', CELL * CELL * 2, doff)
        b += struct.pack('<II', CELL, CELL)
        b += bytes([0x02, 0x03, 0x00, 0x00])
        b += struct.pack('<I', 0x64)
        b += struct.pack('<I', 0x56509310)
        b += struct.pack('<II', CELL, CELL)
        b += struct.pack('<iii', 0, 0, 0)
        return b
    # stream: [palette count=0] + per frame [id][classtag 0x16 + body][extra=-1],
    # final terminator id = -1  (body() emits the 0x16 classtag dword itself)
    hdr = struct.pack('<I', 0)
    for i in range(NFRAMES):
        doff = i * CELL * CELL * 2
        hdr += struct.pack('<I', i) + body(i, doff) + b'\xff\xff\xff\xff'
    hdr += b'\xff\xff\xff\xff'
    base = 0x18 + len(hdr)
    filesize = base + NFRAMES * CELL * CELL * 2
    out = struct.pack('<4sIIIII', b'\x04ILB', 0x40F000, 0x40800000, 0x18, base, filesize)
    out += hdr
    for fr in frames:
        px = fr.load()
        for y in range(CELL):
            for x in range(CELL):
                r, g, b = px[x, y]
                out += struct.pack('<H', rgb565(r, g, b))
    assert len(out) == filesize
    return out


# ---------- pfs record rebuild (same machinery as icon script + entry rewire) --
def pfs_table(d, p):
    b = d[p]; p += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80: nd = struct.unpack_from('<I', d, p)[0]; p += 4
    pairs = []
    for _ in range(nb): pairs.append((d[p], d[p+1])); p += 2
    for _ in range(nd): pairs.append(struct.unpack_from('<II', d, p)); p += 8
    return pairs, p


def rewire_entry(blob):
    """Replace the EFFECTS\\MAGIC.ILB entry (sword frames) with our eye."""
    m = blob.find(b'EFFECTS\\MAGIC.ILB')
    assert m >= 0, "no MAGIC.ILB entry in blob"
    lenpos = m - 4
    assert struct.unpack_from('<I', blob, lenpos)[0] == 17
    p = m + 17
    b3 = bytes(blob[p:p+3])                       # flags (04 01 04) — keep
    xoff, yoff = struct.unpack_from('<ii', blob, p+7)
    z = struct.unpack_from('<I', blob, p+15)[0]
    cnt = struct.unpack_from('<I', blob, p+19)[0]
    entry_end = p + 23 + cnt * 4
    newpath = b'EFFECTS\\MSIGHT.ILB'
    frames = [0x3E7] * DELAYS + list(range(NFRAMES))
    ne = struct.pack('<I', len(newpath)) + newpath + b3
    ne += struct.pack('<I', 0)                    # default id 0
    ne += struct.pack('<ii', xoff, yoff)
    ne += struct.pack('<I', z)
    ne += struct.pack('<I', len(frames))
    for f in frames: ne += struct.pack('<I', f)
    return bytes(blob[:lenpos]) + ne + bytes(blob[entry_end:])


def rebuild(d):
    pairs, kbase = pfs_table(d, 7)
    idx = {t: kbase + o for t, o in pairs}
    off = idx[210]
    assert off > max(v for k, v in idx.items() if k != 210)
    tp, tend = pfs_table(d, off)
    ent = sorted([(t, tend + o) for t, o in tp], key=lambda x: x[1])
    vals = []
    for i, (t, vo) in enumerate(ent):
        nxt = ent[i+1][1] if i+1 < len(ent) else len(d) - 4   # exclude CRC tail
        vals.append((t, bytearray(d[vo:nxt])))
    vmap = dict(vals)
    assert 0x0C in vmap
    vmap[0x0C] = bytearray(rewire_entry(vmap[0x0C]))
    order = [t for t, _ in vals]
    o2 = 0; bytep = []; dwordp = []
    for t in order:
        (bytep if o2 <= 255 and not dwordp else dwordp).append((t, o2))
        o2 += len(vmap[t])
    rec = bytes([0x80 | len(bytep)]) + struct.pack('<I', len(dwordp))
    for t, o in bytep:  rec += bytes([t, o])
    for t, o in dwordp: rec += struct.pack('<II', t, o)
    for t in order:     rec += bytes(vmap[t])
    body = bytes(d[:off]) + rec
    return body + struct.pack('<I', zlib.crc32(body[4:]) & 0xFFFFFFFF)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(NEWILB): os.remove(NEWILB); print("MSight.ILB removed")
        if os.path.exists(PFS_BAK): shutil.copy2(PFS_BAK, PFS); print("Spells.pfs restored")
        return 0
    ilb = build_ilb()
    d = bytearray(open(PFS, 'rb').read())
    assert zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF == struct.unpack_from('<I', d, len(d)-4)[0], \
        "source pfs CRC invalid"
    new = rebuild(d)
    assert zlib.crc32(new[4:-4]) & 0xFFFFFFFF == struct.unpack_from('<I', new, len(new)-4)[0]
    m = new.find(b'MSIGHT.ILB')
    print("MSight.ILB: %d bytes, %d frames" % (len(ilb), NFRAMES))
    print("PFS: %d -> %d bytes; entry rewired (MSIGHT @0x%X)" % (len(d), len(new), m))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(PFS_BAK):
        shutil.copy2(PFS, PFS_BAK); print("Backup -> %s" % os.path.basename(PFS_BAK))
    open(NEWILB, 'wb').write(ilb)
    open(PFS, 'wb').write(new)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
