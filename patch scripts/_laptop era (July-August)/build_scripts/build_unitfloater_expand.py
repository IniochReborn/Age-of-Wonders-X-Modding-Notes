#!/usr/bin/env python3
"""Unit Floater expansion (AoWDevX.exe) - see ../UnitFloater_Expand_Design.md

Three byte-patches, no code caves, no keystone/capstone needed:

P1 race-floater-specials-tabs
    TRaceResourceEditForm.FormCreate (VA 0x4117E3) configures the shared
    TUnitFloater's TUnitSelectionControl with All=1, races=0, specials=0,
    so the floater shown for race unit lists / default city productions has
    only the "All" tab.  Flip `mov byte [eax+0x4A], 0` -> 1 to enable the
    special-category tabs (Humanoid / Creatures / Siege Machines).

P2 floater-clientheight
    TUnitFloater DFM ClientHeight 253 -> 475 so ~8 unit rows are visible
    instead of ~3 (vaInt16 in place, same size).

P3 floater-grid-growdir
    TUnitFloater.UnitSelectionGrid DFM: GrowDirection ilHorizontal ->
    ilVertical.  ILPACK TCustomImageDrawGrid.UpdateDimensions grows COLUMNS
    for ilHorizontal, and the grid's MaxColCount=8 clamps that at 8, so with
    RowCount=20 only 8*20=160 cells ever exist - units past 160 in the All
    tab are unreachable.  ilVertical grows ROWS (MaxRowCount=0 = unlimited,
    ScrollBars=ssVertical already set), so every unit gets a cell.
    The ident is 2 bytes shorter, so the DFM tail is shifted up 2 bytes and
    the block is zero-padded (trailing bytes after the root object are
    ignored by TReader).

Dry-run by default, --apply to write.  Idempotent; verifies bytes before
writing; backs up to AoWDevX.exe.pre-unitfloater_expand on first apply.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWDevX.exe")
BACKUP = TARGET + ".pre-unitfloater_expand"

DFM_START = 0xD6200          # TPF0 TUnitFloater
DFM_END = 0xD6E8A            # end of root object (next TPF0 at 0xD6E8C)

GROW_OFF = 0xD6A4C
GROW_OLD = bytes([13]) + b"GrowDirection" + bytes([7, 12]) + b"ilHorizontal"
GROW_NEW = bytes([13]) + b"GrowDirection" + bytes([7, 10]) + b"ilVertical"

PATCHES = [
    # (name, offset, old bytes, new bytes) - simple in-place patches
    ("P1 race-floater-specials-tabs", 0x10BE3, bytes.fromhex("c6404a00"),
     bytes.fromhex("c6404a01")),
    ("P2 floater-clientheight", 0xD626A,
     bytes([12]) + b"ClientHeight" + bytes([3]) + struct.pack("<h", 253),
     bytes([12]) + b"ClientHeight" + bytes([3]) + struct.pack("<h", 475)),
]


def main():
    apply = "--apply" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    dirty = False
    ok = True

    for name, off, old, new in PATCHES:
        cur = bytes(data[off:off+len(old)])
        if cur == new:
            print("  %-32s already applied" % name)
        elif cur == old:
            print("  %-32s ready @0x%X (%d bytes)" % (name, off, len(old)))
            data[off:off+len(new)] = new
            dirty = True
        else:
            print("  %-32s MISMATCH @0x%X: %s" % (name, off, cur.hex()))
            ok = False

    # P3: shrink ident by 2, shift DFM tail up, pad with zeros
    cur = bytes(data[GROW_OFF:GROW_OFF+len(GROW_OLD)])
    if cur[:len(GROW_NEW)] == GROW_NEW:
        print("  %-32s already applied" % "P3 floater-grid-growdir")
    elif cur == GROW_OLD:
        print("  %-32s ready @0x%X (tail shift %d bytes)"
              % ("P3 floater-grid-growdir", GROW_OFF,
                 DFM_END - (GROW_OFF + len(GROW_OLD))))
        tail = bytes(data[GROW_OFF+len(GROW_OLD):DFM_END])
        block = GROW_NEW + tail + b"\x00\x00"
        assert len(block) == DFM_END - GROW_OFF
        data[GROW_OFF:DFM_END] = block
        dirty = True
    else:
        print("  %-32s MISMATCH @0x%X: %s"
              % ("P3 floater-grid-growdir", GROW_OFF, cur.hex()))
        ok = False

    if not ok:
        print("ABORT: unexpected bytes, nothing written.")
        return 1
    if not dirty:
        print("All patches already applied; nothing to do.")
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply to write.")
        return 0

    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP)
        print("Backup -> %s" % os.path.basename(BACKUP))
    with open(TARGET, "wb") as f:
        f.write(data)
    print("Written %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
