#!/usr/bin/env python3
r"""
Great Eagle's Nest v6 (2026-10-31) - on top of patch_eagle_nest_v5.

User: "make the razed structure still look like a mountain, but broken nest and no birds. builders go on top of
mountain when rebuilding.. also make it so that the structure is like a mountain in the sense that it requires
mountaineering/flying/floating/etc".
  1. Images\PRO_EAGL.ILB + ids 5..7 = eagle_nest_art_v3.map_frames(broken=RAZED_SEEDS): the same crag (grass foot)
     with a collapsed, scattered nest, no eagle.
  2. Release.hss child 282:
       razed slots 0x16..0x18 (were STR_NODE 7, the node ruin)  -> PRO_EAGL 5/6/7 at the crag's offset, no birds;
       rebuild slots 0x19..0x1B (STR_NODE 7 + two STR_BLDG cranes) -> PRO_EAGL 5/6/7 + the cranes moved onto the
       crag top (CRANE_POS) using the high-contrast crane frames (+20, STR_BLDG 30..41, from the Sanctuary work).
  3. Mountain movement: a map hex's overlay = the first object (top-down) whose VMT+0x58 GetOverlay answers >= 0
     (HSEngine TMapField.Initialize 0x5560806C -> [field+0x15]); every move-cost lookup is
     [movecontrol + terrain*16 + overlay + 0x31] (callback 0x557454D8), mountain = overlay 0, structures answer 7.
     TBuildersGuild VMT (0x557CA0DC) +0x58 TStructure.GetOverlay 0x5575EBF0 -> cave 0x558E0340: the Nest
     (ResourceID 0x00E16088 at [[self+8]+0xC]) answers 0, everything else falls through -> the Nest's hex costs
     what a mountain costs for that army (needs Mountaineering / Flying / whatever the cost table allows).
Backups .bak_eagle6 (PRO_EAGL.ILB, Release.hss, AoWEPACK.dll).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_eagle_nest_gfx_v1 as G1  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v5 as V5  # noqa: E402
import eagle_nest_art_v3 as MAP  # noqa: E402

TAG = ".bak_eagle6"
EAGL, HSS = G1.EAGL, G1.HSS
RAZED_IDS = (5, 6, 7)
MAP_POS = (-15, -34)
CRANE_POS = [(-23, -61), (-5, -62)]
CRANE_HC = 20                                   # STR_BLDG high-contrast crane frames = id + 20
VMT, SLOT, OLD = 0x557CA0DC, 0x58, 0x5575EBF0
CAVE, CAVE_END, MAGIC = 0x558E0340, 0x558E0380, b"EGO1"


def build_eagl(gd):
    from PIL import Image
    lib = ilb.read(V5.build_eagl(gd))
    tpl = {im.id: im for im in lib.images}[0].primary
    for i, a in zip(RAZED_IDS, MAP.map_frames(gd, broken=MAP.RAZED_SEEDS)):
        rec = copy.deepcopy(tpl); rec["name"] = "str_eaglr.BMP"
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    assert {im.id for im in ilb.read(out).images} == set(range(8)) | set(G1.BIRD_IDS)
    return out


def nest_list(lst):
    lst = copy.deepcopy(lst)
    for k, slot in enumerate((0x16, 0x17, 0x18)):
        lst[slot] = dict(name="PRO_EAGL.ILB", a=0, b=0, mode=0, frame=RAZED_IDS[k], x=MAP_POS[0], y=MAP_POS[1],
                         sub=None)
    for k, slot in enumerate((0x19, 0x1A, 0x1B)):
        s = lst[slot]
        c1 = s["sub"]; c2 = c1["sub"]
        assert c1["name"].upper() == "STR_BLDG.ILB" and c2["name"].upper() == "STR_BLDG.ILB", slot
        s.update(name="PRO_EAGL.ILB", frames=[RAZED_IDS[k]], x=MAP_POS[0], y=MAP_POS[1])
        for c, (x, y) in zip((c1, c2), CRANE_POS):
            c["x"], c["y"] = x, y
            if min(c["frames"]) < 30:
                c["frames"] = [f + CRANE_HC for f in c["frames"]]
    return lst


def hss_build(b):
    A = H.parse(b)
    r = A["recs"][G1.NEST_CHILD]
    assert struct.unpack_from("<I", r, 0)[0] == G1.NEST_CLS and struct.pack("<I", V2.RID) in bytes(r)
    fo, td = H.fields(r)
    lst = Q.parse_list(r, td + fo[9])[0]
    new = nest_list(lst)
    if new == lst:
        return None
    nr = R.rec_with_list(r, new)
    A["recs"][G1.NEST_CHILD] = bytearray(nr)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (nr if c == G1.NEST_CHILD else bytes(old[c]))
    return nb


def epk_patches():
    code = OV.asm(f"""
        mov ecx, dword ptr [eax + 8]
        test ecx, ecx
        je orig
        cmp dword ptr [ecx + 0xc], {V2.RID:#x}
        jne orig
        xor eax, eax
        ret
    orig:
        jmp {OLD:#x}
    """, CAVE + 4)
    z = MAGIC + code
    assert len(z) <= CAVE_END - CAVE
    return [(VMT + SLOT, struct.pack("<I", OLD), struct.pack("<I", CAVE + 4)), (CAVE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    bad = [x for x in bad if int(x, 16) != VMT + SLOT]          # the VMT slot is a relocated pointer (expected)
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot reloc expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        for f in (EAGL, HSS):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    gd = game_dir()
    ne = build_eagl(gd); ne = None if open(EAGL, "rb").read() == ne else ne
    nh = hss_build(open(HSS, "rb").read())
    files = [(EAGL, ne), (HSS, nh)]
    for f, data in files:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    if all(x is None for _, x in files) and st[0] == "ours":
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    for f, data in files:
        if data is None:
            continue
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
