#!/usr/bin/env python3
r"""
Underground cave mouths on surface terrain (snow etc.) (2026-10-31).

Community suggestion (via the user): "Cave entrance. From surface snow to dungeon level (dirt) if you place snow
underground on this cave on dungeon level the cave "seems to disappear" but in fact there is simply no ice cave
graphic addressed for snow underground in dungeon."
Cause: TCave.GetTerrainTypeImage (VMT +0x12C, 0x557B361C): surface mouth ([cave+0x30]==1) -> image slot = terrain,
underground mouth -> slot = terrain + 30.  The underground terrains (0xA cave water, 0xB, 0xC dirt) land on slots
40..42, but a surface terrain painted underground (1..5: grass/snow/...) lands on 31..35 = the side-window BORDER
image tags -> a border picture or nothing is drawn.
Fix:
  * AoWEPACK 0x557B361C -> cave 0x558E0400 'CVU1': underground mouth on terrain 1..5 -> slot 50 + terrain;
    everything else unchanged.
  * Release.hss, every TCaveResource (class 0x2037F: the two tunnels + the two PRO_FIRE caves): slots 51..55 =
    copies of the surface slots 1..5 (the terrain's own cave-mouth art: the snow tunnel = the ice cave).
Backups .bak_caveug (AoWEPACK.dll, Release.hss).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_caveug"
HSS = H.OURS
CAVE_CLS = 0x2037F
SITE, ORIG = 0x557B361C, bytes.fromhex("8078300175038bc2c38d421ec3")
CAVE, CAVE_END, MAGIC = 0x558E0400, 0x558E0440, b"CVU1"
UG_BASE = 50


def epk_patches():
    code = OV.asm(f"""
        cmp byte ptr [eax + 0x30], 1
        jne under
        mov eax, edx
        ret
    under:
        lea eax, [edx - 1]
        cmp eax, 4
        ja std
        lea eax, [edx + {UG_BASE}]
        ret
    std:
        lea eax, [edx + 0x1e]
        ret
    """, CAVE + 4)
    z = MAGIC + code
    assert len(z) <= CAVE_END - CAVE
    site = b"\xe9" + struct.pack("<i", CAVE + 4 - (SITE + 5)) + b"\x90" * (len(ORIG) - 5)
    return [(SITE, ORIG, site), (CAVE, bytes(len(z)), z)]


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != CAVE_CLS:
            continue
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        new = copy.deepcopy(lst)
        for t in range(1, 6):
            if lst[t] is not None:
                new[UG_BASE + t] = copy.deepcopy(lst[t])
        if new != lst:
            changed[c] = R.rec_with_list(r, new)
    if not changed:
        return None, []
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb, sorted(changed)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        bk = bak_path(HSS, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, HSS); print("restored", bk)
        return 0
    b = open(HSS, "rb").read(); nb, ch = hss_build(b)
    print("Release.hss", "already applied" if nb is None else "cave records %s" % ch)
    if nb is None and st[0] == "ours":
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    if nb is not None:
        bk = bak_path(HSS, TAG)
        if not os.path.exists(bk):
            shutil.copy2(HSS, bk)
        with open(HSS, "r+b") as fh:
            fh.write(nb); fh.truncate()
        assert open(HSS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
