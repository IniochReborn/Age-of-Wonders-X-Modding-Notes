"""ilbcodec.py - lossless AoW1 ILB reader/writer (round-trip verified)."""
import struct, io

MAGIC = 0x424C4904
PAL_ID = 0x88801B18
T8 = (1, 2, 3)                      # 8-bit (palette) types
T_CLIP = (2, 3, 17, 18, 22)         # types carrying a clip box + transparent colour
T_CLIPX = (2, 17, 18)               # types carrying the trailing clip_x field

class Rec(dict):
    """One image record (an image, a sub-image of a composite, or an empty)."""
    __getattr__ = dict.get

def read(path_or_bytes):
    d = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes,'rb').read()
    o = 0
    def u32():
        nonlocal o; v = struct.unpack_from('<I', d, o)[0]; o += 4; return v
    def u8():
        nonlocal o; v = d[o]; o += 1; return v
    lib = {'raw_len': len(d)}
    if u32() != MAGIC: raise ValueError("not an ILB")
    lib['someId'] = u32()
    lib['version'] = struct.unpack_from('<f', d, o)[0]; o += 4
    lib['hdrLength'] = u32()
    lib['palettes'] = []
    if lib['hdrLength'] == 24:
        lib['imgDirectory'] = u32(); lib['fileLength'] = u32()
        npal = u32()
        for _ in range(npal):
            if u32() != PAL_ID: raise ValueError("bad palette id")
            lib['palettes'].append(d[o:o+1024]); o += 1024
    elif lib['hdrLength'] == 16:
        lib['v3field'] = u32(); lib['imgDirectory'] = None
    else:
        raise ValueError("unknown hdrLength %d" % lib['hdrLength'])

    def read_part(t):
        r = Rec(type=t)
        r['info'] = u8()
        nl = u32(); r['name'] = d[o:o+nl]; o_adv(nl)
        r['w'], r['h'], r['xs'], r['ys'], r['sub'] = struct.unpack_from('<5I', d, pos()); o_adv(20)
        r['unkA'] = u8(); r['size'] = u32()
        if r['info'] != 1: r['off'] = u32()
        r['totw'] = u32(); r['toth'] = u32()
        if t in T8:
            r['unkB'] = u8()
            if r['info'] == 3: r['unkC'] = u32(); r['unkD'] = u32()
            if r['info'] != 1: r['pal'] = u32()
        else:
            if r['info'] == 3: r['drawMode'] = u32(); r['blendValue'] = u32()
            r['pixFmt'] = u32()
        if t in T_CLIP:
            r['cw'], r['ch'], r['cx'], r['cy'], r['transp'] = struct.unpack_from('<5I', d, pos()); o_adv(20)
        if t in T_CLIPX: r['clip_x'] = u32()
        if r['info'] == 1: r['inline'] = d[pos():pos()+r['size']]; o_adv(r['size'])
        return r
    def pos(): return o
    def o_adv(n):
        nonlocal o; o += n

    images = []
    while True:
        iid = u32()
        if iid == 0xFFFFFFFF: break
        t = u32(); comp = False
        if t == 0x100: comp = True; t = u32()
        img = {'id': iid, 'composite': comp, 'parts': [], 'empty': False}
        if t == 0 and not comp:
            img['empty'] = True; img['filler'] = u32(); images.append(img); continue
        while True:
            if t == 0: break                      # end of composite (no filler, no terminator)
            img['parts'].append(read_part(t))
            if comp: t = u32(); continue
            break
        end = u32()
        if end != 0xFFFFFFFF: raise ValueError("bad terminator %08X after id %d" % (end, iid))
        images.append(img)
    lib['dir_end'] = o
    lib['pixeldata'] = d[o:]                      # verbatim tail (v4: all image data)
    lib['images'] = images
    return lib

def write(lib):
    body = io.BytesIO()                            # directory
    def p32(v): body.write(struct.pack('<I', v))
    def p8(v): body.write(struct.pack('<B', v))
    def put(r):
        p32(r['type']); p8(r['info'])
        p32(len(r['name'])); body.write(r['name'])
        body.write(struct.pack('<5I', r['w'], r['h'], r['xs'], r['ys'], r['sub']))
        p8(r['unkA']); p32(r['size'])
        if r['info'] != 1: p32(r['off'])
        p32(r['totw']); p32(r['toth'])
        if r['type'] in T8:
            p8(r['unkB'])
            if r['info'] == 3: p32(r['unkC']); p32(r['unkD'])
            if r['info'] != 1: p32(r['pal'])
        else:
            if r['info'] == 3: p32(r['drawMode']); p32(r['blendValue'])
            p32(r['pixFmt'])
        if r['type'] in T_CLIP:
            body.write(struct.pack('<5I', r['cw'], r['ch'], r['cx'], r['cy'], r['transp']))
        if r['type'] in T_CLIPX: p32(r['clip_x'])
        if r['info'] == 1: body.write(r['inline'])
    for img in lib['images']:
        p32(img['id'])
        if img['empty']:
            p32(0); p32(img['filler']); continue
        if img['composite']:
            p32(0x100)
            for r in img['parts']: put(r)
            p32(0)                                 # end of composite
        else:
            put(img['parts'][0])
        p32(0xFFFFFFFF)
    p32(0xFFFFFFFF)                                # end of directory
    dirbytes = body.getvalue()

    head = io.BytesIO()
    head.write(struct.pack('<I', MAGIC))
    head.write(struct.pack('<I', lib['someId']))
    head.write(struct.pack('<f', lib['version']))
    head.write(struct.pack('<I', lib['hdrLength']))
    if lib['hdrLength'] == 24:
        palblock = b"".join(struct.pack('<I', PAL_ID) + p for p in lib['palettes'])
        imgdir = 28 + len(palblock) + len(dirbytes) - 4 + 4   # header(24)+npal field(4)+palettes+dir
        imgdir = 24 + 4 + len(palblock) + len(dirbytes)
        total = imgdir + len(lib['pixeldata'])
        head.write(struct.pack('<III', imgdir, total, len(lib['palettes'])))
        head.write(palblock)
    else:
        head.write(struct.pack('<I', lib['v3field']))
    return head.getvalue() + dirbytes + lib['pixeldata']

if __name__ == "__main__":
    import sys, glob, os
    root = sys.argv[1]
    files = []
    for sub in ("Images", "Int"):
        for pat in ("*.ilb", "*.ILB"):
            files += glob.glob(os.path.join(root, sub, "**", pat), recursive=True)
    files = sorted(set(os.path.normpath(f) for f in files))
    ok = same = 0; diffs = []; errs = []
    for f in files:
        try:
            orig = open(f, 'rb').read()
            lib = read(orig); out = write(lib); ok += 1
            if out == orig: same += 1
            else:
                n = min(len(out), len(orig))
                at = next((i for i in range(n) if out[i] != orig[i]), n)
                diffs.append((os.path.basename(f), len(orig), len(out), at))
        except Exception as e:
            errs.append((os.path.basename(f), "%s: %s" % (type(e).__name__, e)))
    print("parsed %d/%d   byte-identical round-trip: %d" % (ok, len(files), same))
    if diffs:
        print("DIFFERENT (%d):" % len(diffs))
        for d_ in diffs[:12]: print("   %-24s orig=%d out=%d first-diff@%d" % d_)
    if errs:
        print("ERRORS (%d):" % len(errs))
        for e_ in errs[:12]: print("   %-24s %s" % e_)
