#!/usr/bin/env python3
r"""
Great Eagle's Nest v3 (2026-10-31) - on top of patch_eagle_nest_v2.

User: "good but the side image sucks, it should be original but in vanilla art style .. combat map is good but get
rid of elemental glow and replace with something more suitable. same with structure UI image".
  1. Images\BORDER.ILB 205..207 = eagle_nest_side_v3 (original painting: dawn sky, flat-topped crag, nest, eagles,
     white gulls, mist + pines).
  2. The "elemental glow" = Nest0000's combat structure object (record tag 0x22051C) -> comb_res child 578
     (TCombatStructureResource 0x22051D, ResourceID 0x015F5B08): ZS_FHOLE.ILB pit + STR_NODE.ILB glow layer.
     New Images\TCOMBAT\STRUCT\ZS_NEST.ILB (eagle_nest_combat_art: id 0 boulder mound + twig nest + perched eagle,
     ids 10..33 white birds circling); comb_res child 581 = clone of 578 with ResourceID NEW_RID and its image list
     (fields 9/10) -> ZS_NEST mound + bird layer; payload CRC fixed.  Footprint etc. stay the node's.
  3. TCMaps\Nest0000.hsm rebuilt from NodeE000 with v2's decor swap + the structure GUID 0x015F5B08 -> NEW_RID.
     The production window's background is drawn from this map, so it changes with it.
  4. Int\Scenes\CityWin.ILB id 69 (window icon, v2) re-made from the v3 painting (eagle_nest_side_v3.window_icon).
Backups .bak_eagle3 (BORDER.ILB, comb_res.pfs, Nest0000.hsm, CityWin.ILB); ZS_NEST.ILB removed by --revert (Nest0000 goes back
to v2's).  ⚠ NEW file ZS_NEST.ILB -> release --add.  ⚠ comb_res child 581 was build_sky_chasm_combat_v1's clone id
(that patch is not applied; it asserts max child 580 and would abort).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import build_sky_chasm_combat_v1 as SC  # noqa: E402  (PFS, pfs_records)
import patch_eagle_nest_gfx_v1 as G1  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import eagle_nest_side_v3 as SIDE  # noqa: E402
import eagle_nest_combat_art as CA  # noqa: E402

TAG = ".bak_eagle3"
BORDER, PFS, NESTMAP, CITYWIN = G1.BORDER, SC.PFS, V2.NESTMAP, V2.CITYWIN
ZSNEST = game_file(os.path.join("Images", "TCOMBAT", "STRUCT", "ZS_NEST.ILB"))
ZS_NAME = "TCOMBAT\\STRUCT\\ZS_NEST.ILB"
SRC_CHILD, NEW_CHILD = 578, 581
OLD_RID, NEW_RID = 0x015F5B08, 0x00E1608C
BIRD_IDS = list(range(10, 10 + CA.BN))
MOUND_POS = (-50, -45)      # node pit centre x ~ +16, its foot ~ +70
BIRD_POS = (-64, -75)


def build_zsnest(gd):
    from PIL import Image
    raw = open(os.path.join(gd, "Images", "TCOMBAT", "STRUCT", "zs_fhole.ILB"), "rb").read()
    tpl = {im.id: im for im in ilb.read(raw).images}[0].primary
    lib = ilb.read(raw); lib.images = []
    rec = copy.deepcopy(tpl); rec["name"] = "z_nest.BMP"
    ilb.encode_image(lib, rec, Image.fromarray(CA.mound(), "RGBA"))
    lib.images.append(ilb.Image(0, parts=[rec]))
    for i, a in zip(BIRD_IDS, CA.bird_frames()):
        r2 = ilb.new_record(name="z_nestbird%02d.BMP" % (i - 10))
        ilb.encode_image(lib, r2, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[r2]))
    out = ilb.write(lib)
    assert {im.id for im in ilb.read(out).images} == {0} | set(BIRD_IDS)
    return out


def build_border(raw):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    for i, a in zip(G1.BORDER_IDS, SIDE.side_images()):
        rec = by[i].primary
        assert (rec["w"], rec["h"]) == (a.shape[1], a.shape[0])
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
    out = ilb.write(lib)
    return None if out == raw else out


def build_citywin(raw):
    from PIL import Image
    lib = ilb.read(raw)
    rec = {im.id: im for im in lib.images}[V2.ICON_ID].primary
    a = SIDE.window_icon()
    assert (rec["w"], rec["h"]) == (a.shape[1], a.shape[0]), a.shape
    ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
    out = ilb.write(lib)
    return None if out == raw else out


def nest_struct_list(lst):
    lst = copy.deepcopy(lst)
    for i, s in enumerate(lst):
        if s is None:
            continue
        assert s["name"].upper() == "TCOMBAT\\STRUCT\\ZS_FHOLE.ILB" and s["sub"]["name"].upper() == "STR_NODE.ILB", i
        s.update(name=ZS_NAME, frame=0, x=MOUND_POS[0], y=MOUND_POS[1])
        s["sub"] = dict(name=ZS_NAME, a=1, b=2, mode=4, frame=(i * 7) % len(BIRD_IDS), x=BIRD_POS[0], y=BIRD_POS[1],
                        z=0, frames=list(BIRD_IDS), sub=None)
    return lst


def build_pfs(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[4:-4]) & 0xFFFFFFFF, "comb_res CRC"
    ce, cbase, recs = SC.pfs_records(b)
    if NEW_CHILD in recs:
        return None
    assert max(recs) == NEW_CHILD - 1, max(recs)
    s, t = recs[SRC_CHILD]
    src = b[s:t]
    fo, td = H.fields(src)
    assert struct.unpack_from("<I", src, 0)[0] == 0x22051D and struct.unpack_from("<I", src, td + fo[1])[0] == OLD_RID
    assert struct.pack("<I", NEW_RID) not in b
    r = bytearray(R.rec_with_list(src, nest_struct_list(Q.parse_list(src, td + fo[9])[0])))
    f2, d2 = H.fields(r)
    struct.pack_into("<I", r, d2 + f2[1], NEW_RID)
    region = bytearray(b[cbase:len(b) - 4])
    ce.append([NEW_CHILD, len(region), "d"])
    region += r
    out = bytearray(b[:0xD]) + H.enc_table(ce) + region
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    ce2, cb2, recs2 = SC.pfs_records(bytes(out))
    for c, (s0, t0) in recs.items():
        assert out[recs2[c][0]:recs2[c][1]] == b[s0:t0], c
    assert bytes(out[recs2[NEW_CHILD][0]:recs2[NEW_CHILD][1]]) == bytes(r)
    return bytes(out)


def build_nestmap():
    src = open(V2.NODE, "rb").read()
    d = bytearray(zlib.decompress(src[5:]))
    n = 0
    for old, new in list(V2.DECOR.items()) + [(OLD_RID, NEW_RID)]:
        p, q = struct.pack("<I", old), struct.pack("<I", new)
        i = d.find(p)
        while i >= 0:
            assert d[i - 4:i] == b"\x03\x04\x04\x05", hex(i)          # object record tag (decor + structure)
            d[i:i + 4] = q; n += 1
            i = d.find(p, i + 4)
    assert d.count(struct.pack("<I", NEW_RID)) == 1
    return b"CFS\x00\x02" + zlib.compress(bytes(d), 9), n


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    if revert:
        for f in (BORDER, PFS, NESTMAP, CITYWIN):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        if os.path.exists(ZSNEST):
            os.remove(ZSNEST); print("removed", ZSNEST)
        return 0
    gd = game_dir()
    nbd = build_border(open(BORDER, "rb").read())
    npf = build_pfs(open(PFS, "rb").read())
    nz = build_zsnest(gd); nz = None if os.path.exists(ZSNEST) and open(ZSNEST, "rb").read() == nz else nz
    nm, nsw = build_nestmap(); nm = None if open(NESTMAP, "rb").read() == nm else nm
    ncw = build_citywin(open(CITYWIN, "rb").read())
    files = [(BORDER, nbd), (PFS, npf), (NESTMAP, nm), (CITYWIN, ncw)]
    for f, data in files:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    print("ZS_NEST.ILB", "already applied" if nz is None else "write (%d B)" % len(nz))
    if all(d is None for _, d in files) and nz is None:
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, data in files:
        if data is None:
            continue
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    if nz is not None:
        with open(ZSNEST, "wb") as fh:
            fh.write(nz)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
