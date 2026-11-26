#!/usr/bin/env python3
r"""
Water teleporters: surface water + underground water variants of the standing-stone teleporter (2026-10-31).

User: "i want to make two new terrain variants for teleporters: surface water and underground/depths water. they
should look slightly different than land teleporters (but still placeable via the same editor object). ships should
be able to use them (base terrain water). also add a new side image".
A structure's map image slot = its terrain (TStructure.TerrainChanged -> GetTerrainTypeImage): water = 0, cave
water = 0xA (slots 0 / 10, unused by the teleporters so far - the same mechanism the water tunnels use).
  1. Images\STR_TELW.ILB (NEW): 0 = surface water ring (tele_water_art.map_frame), 1 = underground water ring.
  2. Images\BORDER.ILB + 208 (B_Telep in water) / 209 (BU_Telep in water) = tele_water_art.portrait.
  3. Release.hss teleporter records 201 (surface) / 218 (underground): slot 0 = STR_TELW 0, slot 10 = STR_TELW 1
     (copies of slot 1's sequence, offsets kept); new side-image slots 40/41/42 = the record's own top/filler border
     images + the water portrait (list grown 33 -> 43).
  4. AoWEPACK: TTeleport VMT 0x557A4A28 +0x138/+0x13C/+0x140 (side-window border getters, TStructure versions read
     tags 0x1E/0x1F/0x20 from [res+0x24]) -> caves 0x558E0800 'TWB1': terrain [self+0x18] 0 or 0xA -> tags
     40/41/42 when the record has them (Divine Gates don't -> normal art), else the TStructure getter.
Ships: like the water tunnels (also structures on water) - a structure hex on water uses the water cost row.
Backups .bak_telewater (Release.hss, BORDER.ILB, AoWEPACK.dll); STR_TELW.ILB removed by --revert.
⚠ NEW file Images\STR_TELW.ILB -> release --add.  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import tele_water_art as ART  # noqa: E402

TAG = ".bak_telewater"
HSS = H.OURS
BORDER = game_file(os.path.join("Images", "BORDER.ILB"))
TELW = game_file(os.path.join("Images", "STR_TELW.ILB"))
RECS = {201: (41, 208, False), 218: (131, 209, True)}          # record: (source portrait, new id, underground)
WTAGS = (40, 41, 42)
VMT = 0x557A4A28
GETTERS = [(0x138, 0x5575EB0C, 40), (0x13C, 0x5575EB58, 41), (0x140, 0x5575EBA4, 42)]
CAVE, CAVE_END, MAGIC = 0x558E0800, 0x558E0900, b"TWB1"
LIST_FIND, LIST_IMG = 0x557028E4, 0x557028A4


def build_telw(gd):
    from PIL import Image
    raw = open(os.path.join(gd, "Images", "STR_TELE.ILB"), "rb").read()
    tpl = {im.id: im for im in ilb.read(raw).images}[0].primary
    lib = ilb.read(raw); lib.images = []
    for i, under in ((0, False), (1, True)):
        rec = copy.deepcopy(tpl); rec["name"] = "str_telw%d.BMP" % i
        ilb.encode_image(lib, rec, Image.fromarray(ART.map_frame(gd, under), "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    return ilb.write(lib)


def build_border(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    want = {nid: ART.portrait(gd, src, under) for src, nid, under in RECS.values()}
    if all(i in by for i in want):
        return None
    assert not any(i in by for i in want)
    for (src, nid, under) in RECS.values():
        rec = copy.deepcopy(by[src].primary); rec["name"] = "B_TelepW.BMP"
        ilb.encode_image(lib, rec, Image.fromarray(want[nid], "RGBA"))
        lib.images.append(ilb.Image(nid, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, (src, nid, under) in RECS.items():
        r = bytes(A["recs"][c])
        assert struct.unpack_from("<I", r, 0)[0] == 0x20105 and b"STR_TELE" in r.upper()
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        new = copy.deepcopy(lst)
        while len(new) < max(WTAGS) + 1:
            new.append(None)
        for slot, fr in ((0, 0), (10, 1)):
            s = copy.deepcopy(lst[1])
            s["name"] = "STR_TELW.ILB"
            if s["mode"] == 0:
                s["frame"] = fr
            else:
                s["frames"] = [fr]; s["frame"] = 0
            new[slot] = s
        new[40] = copy.deepcopy(lst[30]); new[41] = copy.deepcopy(lst[31])
        new[42] = copy.deepcopy(lst[32]); new[42]["frame"] = nid
        if new != lst:
            changed[c] = R.rec_with_list(r, new)
    if not changed:
        return None
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb


def epk_patches():
    P, at = [], CAVE + len(MAGIC)
    blob = bytearray(MAGIC)
    for slot, orig, tag in GETTERS:
        c = OV.asm(f"""
            movsx ecx, byte ptr [eax + 0x18]
            test ecx, ecx
            je w
            cmp ecx, 0xa
            jne o
        w:
            push ebx
            mov ebx, eax
            mov eax, dword ptr [ebx + 0x8]
            mov eax, dword ptr [eax + 0x24]
            test eax, eax
            jz f
            mov edx, {tag:#x}
            call {LIST_FIND:#x}
            test eax, eax
            jz f
            mov eax, dword ptr [ebx + 0x8]
            mov eax, dword ptr [eax + 0x24]
            mov edx, {tag:#x}
            call {LIST_FIND:#x}
            call {LIST_IMG:#x}
            pop ebx
            ret
        f:
            mov eax, ebx
            pop ebx
        o:
            jmp {orig:#x}
        """, at)
        P.append((VMT + slot, struct.pack("<I", orig), struct.pack("<I", at)))
        blob += c; at += len(c)
    assert CAVE + len(blob) <= CAVE_END
    P.append((CAVE, bytes(len(blob)), bytes(blob)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    bad = [x for x in bad if int(x, 16) not in [VMT + s for s, _, _ in GETTERS]]
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot relocs expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        for f in (HSS, BORDER):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        if os.path.exists(TELW):
            os.remove(TELW); print("removed", TELW)
        return 0
    gd = os.path.dirname(HERE)
    nh = hss_build(open(HSS, "rb").read())
    nb = build_border(open(BORDER, "rb").read(), gd)
    nt = build_telw(gd); nt = None if os.path.exists(TELW) and open(TELW, "rb").read() == nt else nt
    files = [(HSS, nh), (BORDER, nb)]
    for f, data in files + [(TELW, nt)]:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    if all(x is None for _, x in files) and nt is None and st[0] == "ours":
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
    if nt is not None:
        with open(TELW, "wb") as fh:
            fh.write(nt)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
