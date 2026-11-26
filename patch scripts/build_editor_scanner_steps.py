#!/usr/bin/env python3
r"""AoWx -- editor scanner (minimap) progressive redraw: MapDrawSteps 1 -> 8.

ADOPTED 2026-08-31 from the MapDrawSteps half of BXL/Ziggurat's
build_editor_framerate.py (its FrameRate half is moot for us -- our
AoWDevX.exe already ships FrameRate=60, and per BXL's own later measurement
FrameRate cannot pace below the Sleep floor anyway; see
[[aowdevx-binary-notes]]).

WHAT IT IS: `MapDrawSteps` is a published property of the editor's SCANNER
control -- verified 2026-08-31 by reading the DFM around it, whose
neighbouring properties are ScanTiles / ScanHiLites / ScanFog / ScanObj /
ScannerChangeTileBox / ScanWin, i.e. the minimap, NOT the main map view.
Raising it from 1 to 8 makes the scanner rebuild in 8 slices across
successive frames instead of entirely within one, which flattens the
per-frame cost spike.

Interaction with our render gate: with build_editor_rendergate.py pacing
renders at 31 ms, a full scanner refresh now completes in ~8 x 31 ms
= ~0.25 s. That is invisible for a minimap and is exactly the cost being
traded away.

The patch is ONE BYTE in the exe's DFM resource, guarded by the property
name + vaInt8 marker immediately before it (so the offset can never drift
silently). No code, no cave, no reloc concerns.

Usage: dry run default; --apply [--steps N]; --revert.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWDevX.exe")
BAK = EXE + ".bak_scannersteps"

ANCHOR = b"\x0cMapDrawSteps\x02"     # shortstr 'MapDrawSteps' + vaInt8
ORIG_STEPS = 1
NEW_STEPS = 8


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    steps = NEW_STEPS
    if "--steps" in sys.argv:
        steps = int(sys.argv[sys.argv.index("--steps") + 1])
    if not (1 <= steps <= 32):
        print("--steps out of range (1..32)")
        return 1

    d = bytearray(open(EXE, "rb").read())
    hits = []
    i = -1
    while True:
        i = d.find(ANCHOR, i + 1)
        if i == -1:
            break
        hits.append(i + len(ANCHOR))
    if len(hits) != 1:
        print("expected exactly one MapDrawSteps property, found %d - refusing" % len(hits))
        return 1
    off = hits[0]
    cur = d[off]
    want = ORIG_STEPS if revert else steps
    print("  MapDrawSteps @file 0x%X: %d -> %d" % (off, cur, want))
    if cur == want:
        print("nothing to do")
        return 0
    if not (apply or revert):
        print("dry run (--apply [--steps N] / --revert)")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up")
    d[off] = want
    try:
        open(EXE, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe and retry")
        return 1
    print("APPLIED - test: minimap/scanner still refreshes correctly (it now "
          "fills in over ~0.25 s instead of all at once); editor frame cost "
          "is smoother")
    return 0


if __name__ == "__main__":
    sys.exit(main())
