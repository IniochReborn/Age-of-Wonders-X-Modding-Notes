"""patch_hexgrid_option_ilb_v1.py - Flags.ilb data for the in-game "Hex Grid Thickness (F5)" option (2026-10-18).

The F5 grid overlay = Images\Flags.ilb #7 "hexgrid.BMP" (see patch_hexgrid_thick_v1.py for the format notes).  The option
(patch_hexgrid_option_v1.py) makes DrawGrid pick the image id from the setting, so this script keeps #7 VANILLA (1-px,
"Vanilla") and APPENDS two copies of its record:
    #92 "hexgrid2.BMP"  2-px lines  ("Default")
    #93 "hexgrid3.BMP"  3-px lines  ("Extra")
built with patch_hexgrid_thick_v1.thicken() from the vanilla pixels (same record header: Sprite16 48x32, clip 33x32,
colour key 0xC618, drawMode 0x402 / blend 50).  The library's dense id array grows 92 -> 94 entries; ids 92/93 sit past
the old maximum (91), so no existing lookup can land on them.

ORDER: image #7 must be vanilla first -> if patch_hexgrid_thick_v1.py is applied (2/3-px written into #7 in place), run
    py -3.10 patch_hexgrid_thick_v1.py --revert
first.  The engine script falls back to #7 when #92/#93 are missing, so either order of the two option scripts is safe.

Usage:  py -3.10 patch_hexgrid_option_ilb_v1.py [--apply | --revert] [--ilb PATH]   (dry-run by default)
Backup: backup\Images\Flags.ilb.bak_hexgridopt   (--revert rebuilds the file without #92/#93 and checks it equals the
backup byte for byte)
"""
import os, sys, copy, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_dir
import patch_hexgrid_thick_v1 as T

NEW = ((92, 2, "hexgrid2.BMP"), (93, 3, "hexgrid3.BMP"))


def load(d):
    sys.path.insert(0, os.path.join(game_dir(), "modding tools"))
    from aowxlib import ilb
    return ilb, ilb.read(d)


def vanilla_px(ilb, lib):
    img = [i for i in lib.images if i.id == T.MAGIC_ID][0]
    rec = img.primary
    assert rec["type"] == 22 and rec["name"] == "hexgrid.BMP", rec
    px = lib.record_bytes(rec)
    ink = T.inkcount(px)
    assert ink == T.VANILLA_INK, ("image #7 is not vanilla (%d ink px) - run `py -3.10 patch_hexgrid_thick_v1.py "
                                  "--revert` first" % ink)
    return img, px


def build(d):
    """-> (state, applied_bytes, stripped_bytes)"""
    ilb, lib = load(d)
    img7, van = vanilla_px(ilb, lib)
    ids = {i.id for i in lib.images}
    have = [i for i in lib.images if i.id in (92, 93)]
    # stripped = the library without our two images
    base = copy.deepcopy(lib)
    base.images = [i for i in base.images if i.id not in (92, 93)]
    assert max(i.id for i in base.images) < 92, "an image id >= 92 already exists - refusing"
    stripped = ilb.write(base)
    full = copy.deepcopy(base)
    for iid, px, nm in NEW:
        im = copy.deepcopy(img7)
        im.id = iid
        r = im.primary
        r["name"] = nm
        r["newdata"] = T.thicken(van, px)
        full.images.append(im)
    applied = ilb.write(full)
    if not have:
        state = "VANILLA (no #92/#93)"
    elif d == applied:
        state = "APPLIED (#92 2-px, #93 3-px)"
    else:
        state = "UNKNOWN (#92/#93 present but differ)"
    return state, applied, stripped


def main():
    a = sys.argv[1:]
    mode = "apply" if "--apply" in a else "revert" if "--revert" in a else "dry"
    path = a[a.index("--ilb") + 1] if "--ilb" in a else os.path.join(game_dir(), "Images", "Flags.ilb")
    bak = bak_path(path, ".bak_hexgridopt", create=(mode == "apply"))
    d = open(path, "rb").read()
    state, applied, stripped = build(d)
    print("%s: %s" % (path, state))
    assert not state.startswith("UNKNOWN"), "unexpected state - refusing"
    if state.startswith("VANILLA"):
        assert stripped == d, "ILB writer does not round-trip this file - refusing"
    if mode == "dry":
        print("dry-run: %s" % ("already applied" if state.startswith("APPLIED") else
                               "would append #92/#93 (%d -> %d bytes); run with --apply" % (len(d), len(applied))))
        return 0
    if mode == "apply":
        if state.startswith("APPLIED"):
            print("ALREADY APPLIED"); return 0
        if not os.path.exists(bak):
            shutil.copy2(path, bak); print("backup ->", bak)
        open(path, "wb").write(applied)
        assert open(path, "rb").read() == applied
        print("applied: #92 (2-px) + #93 (3-px) appended, %d -> %d bytes" % (len(d), len(applied)))
        return 0
    if state.startswith("VANILLA"):
        print("ALREADY VANILLA"); return 0
    if os.path.exists(bak):
        assert open(bak, "rb").read() == stripped, "backup differs from the stripped library - refusing"
    open(path, "wb").write(stripped)
    print("reverted: #92/#93 removed (%d -> %d bytes)%s" % (len(d), len(stripped), ", equals backup" if os.path.exists(bak) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
