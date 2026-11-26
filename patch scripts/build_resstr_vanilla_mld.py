#!/usr/bin/env python3
r"""AoWx -- build Dict\ResStrV.mld: our ResStr dictionary with ONLY the
campaign-select strings reverted to vanilla.

WHY NOT JUST SHIP THE VANILLA FILE: `Dict\ResStr.mld` differs from vanilla in
FIFTEEN places, and almost all are AoWx renames that must survive --
"Age of Wonders"->"Age of Wonders X" (x4), Dragon->Monster, Dragon Slaying->
Monster Slaying, Flame Throwing->Cosmic Breath, Rejuvenate->Scorch Terrain,
Shoot Black Javelin->Seeker Bolts, Slow->Hunter's Mark, Summon Mermaid->
Summon Spirit, plus a line-ending fix. Only THREE are campaign-select text.
So the vanilla variant transplants just those three records and leaves every
other byte of our file alone.

WHERE THE TEXT COMES FROM: `TSelFactionWin` fills its labels at RUNTIME from
resourcestrings -- e.g. TopLbl @0x00419041 does `LoadResString([0x0045A3B4])`
-> `AoWE.TranslateRStr` (thunk 0x004021E4) -> `TAOWLabel.SetGText`.
TranslateRStr resolves against AoWEPACK's **ResourceStringDictionary**, whose
file name is assembled in `AoWE.TAoWEngine.UpdateStartupDirectory` from
'Dict\' + 'ResStr' + '.mld' (pushes @0x55798386 / 0x5579838B / 0x55798390).
That is why swapping `Dict\AoW.mld` (the FORM dictionary) changed nothing on
this screen -- confirmed live by the user: the select screen stayed AoWx while
the campaign intro (which comes from the .cam) correctly went vanilla.

.MLD RECORD FORMAT (only what is needed for a splice):
    a record is  <u16 len><original>  then exactly SLOTS translation slots,
    each <u16 len><text>; an EMPTY slot means "no translation", and the engine
    falls back to the original -- which is how vanilla shows "The Keepers"
    while our file overrides the English slot with "A Human Perspective".
    The file header carries a language table and NO content checksum, and the
    records are a flat sequence, so a record may grow or shrink in place.
This script never parses the header: it anchors on the exact bytes of each
target record, parses SLOTS slots forward, and validates that it landed
cleanly on the next record before splicing.

Usage:  py -3.10 build_resstr_vanilla_mld.py [--write]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
OURS = os.path.join(GAME, "Dict", "ResStr.mld")
VANILLA = os.path.join(GAME, "reference files", "AoW 1.36", "Dict", "ResStr.mld")
OUT = os.path.join(GAME, "Dict", "ResStrV.mld")

SLOTS = 7
TARGETS = [b"The Keepers", b"The Cult of Storms", b"Choose a Faction"]
PRINTABLE = set(range(32, 127)) | {9, 10, 13} | set(range(0xC0, 0x100))


def find_record(d, orig):
    """Locate `<u16 len><orig>` + SLOTS slots; return (start, end, slots)."""
    anchor = struct.pack("<H", len(orig)) + orig
    hits = []
    pos = 0
    while True:
        i = d.find(anchor, pos)
        if i < 0:
            break
        pos = i + 1
        j = i + len(anchor)
        slots = []
        ok = True
        for _ in range(SLOTS):
            if j + 2 > len(d):
                ok = False
                break
            n = struct.unpack_from("<H", d, j)[0]
            j += 2
            if n > 400 or j + n > len(d):
                ok = False
                break
            s = d[j:j + n]
            if not all(c in PRINTABLE for c in s):
                ok = False
                break
            slots.append(s)
            j += n
        if not ok:
            continue
        # sanity: the next record must start with a sane length + text
        if j + 2 > len(d):
            continue
        nxt = struct.unpack_from("<H", d, j)[0]
        if nxt > 400 or j + 2 + nxt > len(d):
            continue
        if not all(c in PRINTABLE for c in d[j + 2:j + 2 + nxt]):
            continue
        hits.append((i, j, slots))
    return hits


def main():
    write = "--write" in sys.argv
    for p in (OURS, VANILLA):
        if not os.path.isfile(p):
            print("missing %s" % p)
            return 1
    dm = bytearray(open(OURS, "rb").read())
    dv = open(VANILLA, "rb").read()
    print("ours %d bytes, vanilla %d bytes" % (len(dm), len(dv)))

    plan = []
    for orig in TARGETS:
        ho = find_record(bytes(dm), orig)
        hv = find_record(dv, orig)
        if len(ho) != 1 or len(hv) != 1:
            print("  %-20r ours=%d vanilla=%d matches - AMBIGUOUS, refusing"
                  % (orig.decode(), len(ho), len(hv)))
            return 1
        (si, ei, so), (sv, ev, sv_slots) = ho[0], hv[0]
        print("  %-20r ours @0x%06X..0x%06X   vanilla @0x%06X..0x%06X"
              % (orig.decode(), si, ei, sv, ev))
        print("        ours    English = %r" % so[2].decode("latin1"))
        print("        vanilla English = %r%s" % (sv_slots[2].decode("latin1"),
              "   (empty -> falls back to the original)" if not sv_slots[2] else ""))
        plan.append((si, ei, dv[sv:ev]))

    if not write:
        print("dry run (--write to emit %s)" % OUT)
        return 0

    for si, ei, blob in sorted(plan, key=lambda t: -t[0]):    # back to front
        dm[si:ei] = blob
    open(OUT, "wb").write(bytes(dm))
    print("wrote %s (%d bytes)" % (OUT, len(dm)))
    # re-read and confirm the three records now match vanilla
    chk = open(OUT, "rb").read()
    for orig in TARGETS:
        h = find_record(chk, orig)
        assert len(h) == 1, orig
        print("  verify %-20r English now %r"
              % (orig.decode(), h[0][2][2].decode("latin1")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
