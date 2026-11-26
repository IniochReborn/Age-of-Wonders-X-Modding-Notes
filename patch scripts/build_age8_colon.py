#!/usr/bin/env python3
r"""Visible colon glyph in the Age8 font (Int\Fonts\Age8.ILB).

The ':' glyph (image id 58; glyph ids = ASCII codes) is two ISOLATED SINGLE
PIXELS (1x5 bounding box, dots at rows 3 and 7) - effectively invisible in
game, so times like "18:46:09" read as "18 46 09". The '-' (4x1 run) is fine.

Fix: redraw ':' as two 2x1 dots at rows 4 and 7 (x-height + baseline), i.e.
bounding box 2x4 @ (0,4). The RLE08 re-encoding is 24 bytes (4 rows x
[u32 len + payload]; dot row payload = two literal 01 bytes, blank row =
transparent-run pair 00 01) and is written into the old 28-byte slot - no
offset shifting anywhere in the ILB (per-image data offsets are explicit, the
4-byte hole is dead space). Directory ints patched in place: data size 28->24,
wide/advance 2->3 (keeps a 1px gap after the now-2px glyph), totalwide 2->3,
clipwide 1->2, cliphigh 5->4, clipyoff 3->4. Color index 1 = the same ink
every other glyph uses.

RLE08 codec (per IlbMaker source / game): per bounding-box row a u32 length
(including itself), then bytes: a byte equal to the transparent index is
followed by a run count of transparent pixels, anything else is one literal
pixel. Original Age8 rows always carry payload (blank row = "00 01"), so this
patch avoids the untested empty-payload (len=4) row form.

Backup: Age8.ILB.bak_colon. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ILB = os.path.join(GAME, "Int", "Fonts", "Age8.ILB")
BAK = ILB + ".bak_colon"

GLYPH = 58  # ':'

OLD_DATA = bytes.fromhex(
    "0500000001"          # row 3: 1 literal pixel
    "060000000001"        # row 4: blank (run 1)
    "060000000001"        # row 5: blank
    "060000000001"        # row 6: blank
    "0500000001")         # row 7: 1 literal pixel
NEW_DATA = bytes.fromhex(
    "060000000101"        # row 4: 2 literal pixels
    "060000000001"        # row 5: blank
    "060000000001"        # row 6: blank
    "060000000101")       # row 7: 2 literal pixels
NEW_DATA += bytes(len(OLD_DATA) - len(NEW_DATA))   # zero the 4-byte hole
assert len(OLD_DATA) == 28 and len(NEW_DATA) == 28

# (field, old, new) — ints patched in the directory entry
FIELD_PATCH = {"size": (28, 24), "wide": (2, 3), "totalwide": (2, 3),
               "bbw": (1, 2), "bbh": (5, 4), "bby": (3, 4)}


def parse(d):
    """Return (fields->file offset, image data file offset) for glyph 58."""
    o = 0
    def u32():
        nonlocal o
        v = struct.unpack_from("<I", d, o)[0]; o += 4; return v
    def i32():
        nonlocal o
        v = struct.unpack_from("<i", d, o)[0]; o += 4; return v
    def u8():
        nonlocal o
        v = d[o]; o += 1; return v

    assert u32() == 0x424C4904, "not an ILB"
    u32()
    assert struct.unpack_from("<f", d, o)[0] == 4.0; o += 4
    assert u32() == 24
    img_directory = u32(); u32()
    npal = u32()
    for _ in range(npal):
        assert u32() == 0x88801B18
        o += 1024

    while True:
        imgnum = i32()
        assert imgnum != -1, "glyph %d not found" % GLYPH
        t = u32()
        if t == 0:                      # empty image: one filler dword, no -1
            u32(); continue
        assert t == 2, "glyph %d not RLESprite08" % imgnum
        subid = u8()
        assert subid in (2, 3)
        nlen = u32()                    # name (o += after the read: u32
        o += nlen                       #  itself moves o, += would lose it)
        pos = {}
        pos["wide"] = o; i32()
        i32()                           # high
        i32(); i32()                    # x/y shift
        i32()                           # instance
        u8()                            # loadmode
        pos["size"] = o; dsize = i32()
        doff = u32()
        pos["totalwide"] = o; i32()
        i32()                           # totalhigh
        u8()                            # unknownB
        if subid == 3:
            u32(); u32()                # unknownC/D
        i32()                           # palette
        pos["bbw"] = o; i32()
        pos["bbh"] = o; i32()
        pos["bbx"] = o; i32()
        pos["bby"] = o; i32()
        u32()                           # transparent
        u32()                           # clip_x
        assert u32() == 0xFFFFFFFF
        if imgnum == GLYPH:
            assert dsize in (28, 24), dsize
            return pos, img_directory + doff


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, ILB); print("restored Age8.ILB"); return 0
        print("no backup"); return 1

    d = bytearray(open(ILB, "rb").read())
    pos, data_off = parse(d)

    cur = bytes(d[data_off:data_off+28])
    assert cur in (OLD_DATA, NEW_DATA), cur.hex()
    for name, (old, new) in FIELD_PATCH.items():
        v = struct.unpack_from("<i", d, pos[name])[0]
        assert v in (old, new), (name, v)

    d[data_off:data_off+28] = NEW_DATA
    for name, (old, new) in FIELD_PATCH.items():
        struct.pack_into("<i", d, pos[name], new)

    print("Age8.ILB ':' glyph -> two 2x1 dots @ rows 4/7, advance 2->3px "
          "(data @0x%X, 28B in place)" % data_off)
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(ILB, BAK); print("Backup ->", os.path.basename(BAK))
    open(ILB, "wb").write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
