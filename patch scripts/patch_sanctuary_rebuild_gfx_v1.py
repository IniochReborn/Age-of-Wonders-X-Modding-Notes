#!/usr/bin/env python3
r"""
Magic Sanctuary rebuild animation in the standard slots (2026-10-31).  Companion of patch_sanctuary_raze_v1.

User: "sanctuary rebuild GFX is missing the builders/machines etc".  patch_sanctuary_raze_v1 put the rebuild
sequences (razed floor + the STR_BLDG builder layers) in image-list slots 13..18.  Every vanilla rebuildable
structure (cities, mines, farms, nodes, towers, teleports, altars, guilds, shipyards ...) uses slot 0x19 for
exactly this, so the rebuild image now lives there too:
  * Release.hss, both Sanctuary records: slots 0x19..0x1D = the rebuild sequences of terrain variants 0..4
    (copies of slots 13..17; 13..18 stay, unused);
  * AoWEPACK: new GetTerrainTypeImage at 0x558E0240 'SNC3' (TMagicSanctuary VMT +0x12C repointed from the v1 cave
    0x558E0070): building -> slot 0x19 + min(i, 4) (underground i = 5 uses the wasteland floor = same image as
    i = 4), razed -> slot 6 + i, else TStructure's.
Backups .bak_sanctgfx (AoWEPACK.dll, Release.hss).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402

DLL, BASE, HSS = R.DLL, R.BASE, R.HSS
ZONE, ZONE_END, MAGIC = 0x558E0240, 0x558E02A0, b"SNC3"
OLD_GTI = 0x558E0070
SLOT = R.VMT + 0x12C
NEW_BUILD = 0x19


def dll_patches():
    code = OV.asm(f"""
        mov ecx, edx
        dec ecx
        cmp ecx, 5
        jb gidx
        xor ecx, ecx
        cmp edx, 12
        jne gidx
        mov ecx, 5
    gidx:
        cmp byte ptr [eax + 0x24], 0xff
        je gnb
        cmp ecx, 4
        jbe gb
        mov ecx, 4
    gb:
        lea eax, [ecx + {NEW_BUILD:#x}]
        ret
    gnb:
        test byte ptr [eax + {R.RAZED_BIT_OFF:#x}], 1
        je gorig
        lea eax, [ecx + {R.RAZED_SLOT}]
        ret
    gorig:
        jmp {R.ST_GTI:#x}
    """, ZONE + 0x10)
    z = MAGIC + bytes(12) + code
    assert ZONE + len(z) <= ZONE_END
    return [(SLOT, struct.pack("<I", OLD_GTI), struct.pack("<I", ZONE + 0x10)), (ZONE, bytes(len(z)), z)]


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, r in A["recs"].items():
        if struct.unpack_from("<I", r, 0)[0] != R.SANCT_CLS:
            continue
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        assert lst[R.BUILD_SLOT] is not None, "patch_sanctuary_raze_v1 not applied"
        if lst[NEW_BUILD] is not None:
            continue
        assert all(lst[NEW_BUILD + i] is None for i in range(5)), c
        lst = copy.deepcopy(lst)
        for i in range(5):
            lst[NEW_BUILD + i] = copy.deepcopy(lst[R.BUILD_SLOT + i])
        changed[c] = R.rec_with_list(r, lst)
    if not changed:
        return None
    assert len(changed) == 2
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    N = H.parse(nb)
    old = H.parse(b)["recs"]
    for c, v in N["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if SP.busy():
            print("game/editor running - close it first"); return 1
        for f in (DLL, HSS):
            bk = bak_path(f, ".bak_sanctgfx")
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    d = open(DLL, "rb").read(); pe = pefile.PE(data=d)
    P = dll_patches()
    st, bad = SP.state(d, pe, BASE, P)
    bad = [x for x in bad if x != hex(SLOT)]
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    b = open(HSS, "rb").read()
    nb = hss_build(b)
    print("Release.hss", "already applied" if nb is None else "%d -> %d B" % (len(b), len(nb)))
    if st[0] == "ours" and nb is None:
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    for f in (DLL, HSS):
        bk = bak_path(f, ".bak_sanctgfx")
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
    if st[0] == "vanilla":
        SP.write_bytes(DLL, BASE, P, False)
    if nb is not None:
        with open(HSS, "r+b") as fh:
            fh.write(nb); fh.truncate()
        assert open(HSS, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
