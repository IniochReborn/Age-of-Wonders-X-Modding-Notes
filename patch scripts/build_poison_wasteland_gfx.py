#!/usr/bin/env python3
r"""
Poison Plants: withered graphic on wasteland (Release\Release.hss data edit, 2026-09-21).

Engine (HSEPack ILTer.TILTerrainMO, parent of AoWE PoisonP.TPoisonPlant): the object's terrain type [+0x18] is
the INDEX into the resource's TImageSequenceList ([res+0x20], TILTerrainMO.GetTerrainTypeImage is identity,
Show @0x55618940 draws sequence [+0x14]); PoisonPlantActive @0x557C3F90 returns false on terrain 3 (snow) and
5 (wasteland).  The two TPoisonPlantResource records in Release.hss carry 13 slots: slot 3 (snow) = single
frame 10 of Images\GND_POIS.ILB (the white frozen plant), slot 5 (wasteland) = the same green frames 0..9 as
grass, so a negated wasteland plant looks live.  GND_POIS.ILB image 11 is an unreferenced withered dark-olive
plant -- the wasteland art that was never wired up.
TImageSequenceList stream (ILPACK TImageSequenceList/TImageSequence.LoadFromStream 0x552190D8/0x55218A60):
u32 count; per slot u8 nil; sequence = string ILB name, u8, u8, u8 mode, i32 frame, i32 xoff, i32 yoff,
[mode 4/5: u32 0, u32 nFrames, nFrames x u32], u8 hasSub.

Edit: in both records, slot 5's frame list [0..9] -> [11]*10 (same length -> no container size fields touched).
Backup Release.hss.bak_poiswaste (in <game>\backup\).  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path

DEFAULT_HSS = game_file(r"Release\Release.hss")
BAK = ".bak_poiswaste"
WASTE_IMG = 11
SITES = [0xA7A2D, 0x1A817E]          # file offsets of slot-5's 10 frame dwords in the two records
ORIG = struct.pack("<10I", *range(10))
NEW = struct.pack("<10I", *([WASTE_IMG] * 10))
CTX = bytes.fromhex("f4ffffffe9ffffff000000000a000000")   # xoff -12, yoff -23, 0, nFrames 10 (just before the frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hss", nargs="?", default=DEFAULT_HSS)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    hss = a.hss
    bak = bak_path(hss, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, hss); print(f"reverted {hss} from {bak}"); return
    data = bytearray(open(hss, "rb").read())
    print(f"target: {hss} ({len(data)} B)")
    states = []
    for o in SITES:
        if bytes(data[o - 16:o]) != CTX or b"GND_POIS.ILB" not in bytes(data[o - 48:o]):
            sys.exit(f"site {o:#x}: unexpected context {bytes(data[o-16:o]).hex()} - refusing")
        cur = bytes(data[o:o + 40])
        st = "vanilla" if cur == ORIG else "ALREADY PATCHED" if cur == NEW else f"UNKNOWN {cur.hex()}"
        states.append(st); print(f"  slot-5 frames @ {o:#x}: {st}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if any(s.startswith("UNKNOWN") for s in states):
        sys.exit("refusing")
    if all(s == "ALREADY PATCHED" for s in states):
        print("already applied"); return
    if not os.path.exists(bak):
        shutil.copy2(hss, bak); print(f"  backup -> {bak}")
    for o in SITES:
        data[o:o + 40] = NEW
    with open(hss, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied: wasteland poison plants now use GND_POIS.ILB image 11 (withered).")


if __name__ == "__main__":
    main()
