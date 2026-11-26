#!/usr/bin/env python3
r"""
Great Eagle's Nest v2 (2026-10-31) - on top of patch_eagle_nest_gfx_v1.

User: "the nest connecting to the mountain is janky, make the mountain flat top with nest on it. and make the birds
white. and more birds circling... side image is bad, refer to vanilla art style and try again.. also, it needs its
own combat map, maybe similar to nodes (bunch of rocks piled up to form the "nest") ,, and needs its own structure UI
(see screenshot).. also, should not produce income".

The Nest is a TProductionPlace (Builders Guild clone, Release.hss child 282, ResourceID 0x00E16088 = [[s+8]+0xC]).
  1. Images\PRO_EAGL.ILB rebuilt from eagle_nest_art_v2: ids 0..4 flat-topped crag + nest + perched eagle, ids
     10..33 three WHITE birds circling (64x48);  Release.hss child 282 bird layer y -> BIRD_Y (taller canvas).
  2. Images\BORDER.ILB 205..207 (side picture) replaced: vanilla B_ANode (air node) pinnacles + rock shelf + nest.
  3. Structure window icon: Int\Scenes\CityWin.ILB id 69 'I-Eagle' (85x102, cloned from id 66 I-BGuild);
     AoWx.exe 0x43F7E3 `mov edx,0x42` -> .xibn 0x611940: edx = 0x45 when the window's structure ([ebx+0x1E8]) is
     the Nest, else 0x42.
  4. Combat map (= also the structure window's background scene): TCMaps\Nest0000.hsm = NodeE000.HSM with its
     shrubs/trees swapped for rock decor (same-size u32 GUID swap, CFS\0\2 + zlib);  AoWTCPCK switch `je 0x424B78`
     (Builders Guild -> "BGuil000") @0x4249E1 -> cave 0x43EB00 (PIC, the DLL rebases): Nest -> "Nest0000"
     (refcount -1 literal in the cave) -> LStrAsg [ebp-0x40] -> jmp 0x424F31, else -> 0x424B78.
  5. No income: TProductionPlace.GetBaseIncome 0x557BE4E0 -> AoWEPACK cave 0x558E0300: 0 for the Nest (the
     merchandise bonus in GetIncome scales from the base -> also 0), else the vanilla body.
Backups .bak_eagle2 (BORDER.ILB, CityWin.ILB, Release.hss, PRO_EAGL.ILB, AoWx.exe, AoWTCPCK.dll, AoWEPACK.dll);
Nest0000.hsm is removed by --revert.  ⚠ new files PRO_EAGL.ILB + TCMaps\Nest0000.hsm -> release --add.
Dry-run default; --apply; --revert.
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
import patch_eagle_nest_gfx_v1 as G1  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import eagle_nest_art_v2 as ART  # noqa: E402

TAG = ".bak_eagle2"
HSS, BORDER, EAGL = G1.HSS, G1.BORDER, G1.EAGL
CITYWIN = game_file(os.path.join("Int", "Scenes", "CityWin.ILB"))
NODE = game_file(os.path.join("TCMaps", "NodeE000.HSM"))
NESTMAP = game_file(os.path.join("TCMaps", "Nest0000.hsm"))
EXE, TCP = game_file("AoWx.exe"), game_file("AoWTCPCK.dll")
RID = 0x00E16088
ICON_ID, ICON_SRC = 69, 0x42
BIRD_Y_OLD, BIRD_Y = -49, -55
DECOR = {0x4519025: 0x0E7A7B7, 0x4BB34B6: 0xE30193D, 0xE908493: 0x29850C9,     # ZGR_SHRB -> ZGR_SRK small rocks
         0x2559CEC: 0x4250DFE, 0x0B93E31: 0x91FCB65, 0x0C3D489: 0x9EAE2FB}     # shrub / ZGR_TRE -> big rocks


# ---- data files ----------------------------------------------------------------------------------------------------
def build_eagl(gd):
    from PIL import Image
    raw = open(os.path.join(gd, "Images", "PRO_DRGN.ILB"), "rb").read()
    by = {im.id: im for im in ilb.read(raw).images}
    lib = ilb.read(raw); lib.images = []
    for k, a in enumerate(ART.map_frames(gd)):
        rec = copy.deepcopy(by[k].primary); rec["name"] = "str_eagl.BMP"
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(k, parts=[rec]))
    for i, a in zip(G1.BIRD_IDS, ART.bird_frames(len(G1.BIRD_IDS))):
        rec = ilb.new_record(name="eagl_bird%02d.BMP" % (i - 10))
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    return ilb.write(lib)


def build_border(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    assert all(i in by for i in G1.BORDER_IDS), "patch_eagle_nest_gfx_v1 not applied"
    for i, a in zip(G1.BORDER_IDS, ART.side_images(gd)):
        rec = by[i].primary
        assert (rec["w"], rec["h"]) == (a.shape[1], a.shape[0])
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
    out = ilb.write(lib)
    return None if out == raw else out


def build_citywin(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    a = ART.window_icon(gd)
    rec = copy.deepcopy(by[ICON_SRC].primary); rec["name"] = "I-Eagle.BMP"
    assert (rec["w"], rec["h"]) == (a.shape[1], a.shape[0]), (rec["w"], rec["h"])
    ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
    lib.images = [im for im in lib.images if im.id != ICON_ID] + [ilb.Image(ICON_ID, parts=[rec])]
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    return None if out == raw else out


def build_nestmap():
    src = open(NODE, "rb").read()
    assert src[:5] == b"CFS\x00\x02"
    d = bytearray(zlib.decompress(src[5:]))
    n = 0
    for old, new in DECOR.items():
        p, q = struct.pack("<I", old), struct.pack("<I", new)
        i = d.find(p)
        while i >= 0:
            assert d[i - 4:i] == b"\x03\x04\x04\x05", hex(i)       # decor record tag in front of every GUID
            d[i:i + 4] = q; n += 1
            i = d.find(p, i + 4)
    return b"CFS\x00\x02" + zlib.compress(bytes(d), 9), n


def hss_build(b):
    A = H.parse(b)
    r = A["recs"][G1.NEST_CHILD]
    assert struct.unpack_from("<I", r, 0)[0] == G1.NEST_CLS and struct.pack("<I", RID) in bytes(r)
    fo, td = H.fields(r)
    lst = copy.deepcopy(Q.parse_list(r, td + fo[9])[0])
    hit = False
    for i in range(1, 6):
        s = lst[i]["sub"]
        assert lst[i]["name"].upper() == "PRO_EAGL.ILB" and s["name"].upper() == "PRO_EAGL.ILB", i
        if s["y"] == BIRD_Y_OLD:
            s["y"] = BIRD_Y; hit = True
        else:
            assert s["y"] == BIRD_Y
    if not hit:
        return None
    nr = R.rec_with_list(r, lst)
    A["recs"][G1.NEST_CHILD] = bytearray(nr)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (nr if c == G1.NEST_CHILD else bytes(old[c]))
    return nb


# ---- code ----------------------------------------------------------------------------------------------------------
def exe_patches():
    site, orig = 0x43F7E3, bytes.fromhex("ba42000000")
    cave, end, magic = 0x611940, 0x611980, b"EGL1"
    code = OV.asm(f"""
        mov edx, 0x42
        mov eax, dword ptr [ebx + 0x1e8]
        test eax, eax
        je out
        mov eax, dword ptr [eax + 8]
        test eax, eax
        je out
        cmp dword ptr [eax + 0xc], {RID:#x}
        jne out
        mov edx, {ICON_ID:#x}
    out:
        jmp 0x43F7E8
    """, cave + 4)
    z = magic + code
    assert len(z) <= end - cave
    return [(site, orig, b"\xe9" + struct.pack("<i", cave + 4 - (site + 5))), (cave, bytes(len(z)), z)]


def tcp_patches():
    site, orig = 0x4249E1, bytes.fromhex("0f8491010000")          # je 0x424B78 (Builders Guild -> BGuil000)
    cave, end = 0x43EB00, 0x43EC00
    lit = cave + 0xC
    head = b"NST1" + struct.pack("<iI", -1, 8) + b"Nest0000\x00"
    head += bytes(-len(head) % 4)
    code_at = cave + len(head)
    code = OV.asm(f"""
        mov eax, dword ptr [ebp - 0x44]
        test eax, eax
        je vanilla
        mov eax, dword ptr [eax + 8]
        test eax, eax
        je vanilla
        cmp dword ptr [eax + 0xc], {RID:#x}
        jne vanilla
        call here
    here:
        pop edx
        sub edx, here - {lit:#x}
        lea eax, [ebp - 0x40]
        call 0x4010E8
        jmp 0x424F31
    vanilla:
        jmp 0x424B78
    """, code_at)
    z = head + code
    assert len(z) <= end - cave
    return [(site, orig, b"\x0f\x84" + struct.pack("<i", code_at - (site + 6))), (cave, bytes(len(z)), z)]


def epk_patches():
    site, orig = 0x557BE4E0, bytes.fromhex("538bd8807b4801")
    cave, end, magic = 0x558E0300, 0x558E0340, b"EGI1"
    code = OV.asm(f"""
        push ebx
        mov ebx, eax
        mov eax, dword ptr [ebx + 8]
        test eax, eax
        je vanilla
        cmp dword ptr [eax + 0xc], {RID:#x}
        jne vanilla
        xor eax, eax
        pop ebx
        ret
    vanilla:
        cmp byte ptr [ebx + 0x48], 1
        jmp 0x557BE4E7
    """, cave + 4)
    z = magic + code
    assert len(z) <= end - cave
    return [(site, orig, b"\xe9" + struct.pack("<i", cave + 4 - (site + 5)) + b"\x90\x90"), (cave, bytes(len(z)), z)]


BINS = [("AoWx.exe", EXE, 0x400000, exe_patches), ("AoWTCPCK.dll", TCP, 0x400000, tcp_patches),
        ("AoWEPACK.dll", SP.EPK, SP.EBASE, epk_patches)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    code = []
    for name, path, base, fn in BINS:
        d = open(path, "rb").read(); pe = pefile.PE(data=d)
        P = fn(); st, bad = SP.state(d, pe, base, P)
        print("%s %s relocs %s" % (name, st, bad or "none"))
        if "OTHER" in st or bad or len(set(st)) != 1:
            print("ABORT"); return 1
        code.append((name, path, base, P, st[0]))
    if revert:
        for name, path, base, P, st in code:
            if st == "ours":
                SP.write_bytes(path, base, P, True); print("reverted", name)
        for f in (HSS, BORDER, CITYWIN, EAGL):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        if os.path.exists(NESTMAP):
            os.remove(NESTMAP); print("removed", NESTMAP)
        return 0
    gd = game_dir()
    b = open(HSS, "rb").read(); nh = hss_build(b)
    nbd = build_border(open(BORDER, "rb").read(), gd)
    ncw = build_citywin(open(CITYWIN, "rb").read(), gd)
    ne = build_eagl(gd); ne = None if open(EAGL, "rb").read() == ne else ne
    nm, nswap = build_nestmap(); nm = None if os.path.exists(NESTMAP) and open(NESTMAP, "rb").read() == nm else nm
    files = [(HSS, nh), (BORDER, nbd), (CITYWIN, ncw), (EAGL, ne)]
    for f, data in files:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    print("Nest0000.hsm", "already applied" if nm is None else "write (%d decor GUIDs swapped)" % nswap)
    if all(d is None for _, d in files) and nm is None and all(c[4] == "ours" for c in code):
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for name, path, base, P, st in code:
        if st == "vanilla":
            bk = bak_path(path, TAG)
            if not os.path.exists(bk):
                shutil.copy2(path, bk)
            SP.write_bytes(path, base, P, False)
    for f, data in files:
        if data is None:
            continue
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    if nm is not None:
        with open(NESTMAP, "wb") as fh:
            fh.write(nm)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
