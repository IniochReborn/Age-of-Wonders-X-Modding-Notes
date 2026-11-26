#!/usr/bin/env python3
r"""
Great Eagle's Nest v11 (2026-10-31) - on top of v10.

User: "for the nest GFX, polish the mountain, it looks a bit low quality. and make the flagpole shorter".
  1. Images\PRO_EAGL.ILB rebuilt (map frames 0..4 + razed 5..7) from eagle_nest_art_v3 v4-polish: two layers of
     tall column facets, warm-light / violet-shadow contrast like the vanilla MOUNTAIN.ILB cliffs, soft vegetation
     patches at the foot.
  2. Shorter flag pole: Images\Flags.ilb + id SHORT_ID = the top POLE_H rows of pole id 4 (9x54).  The pole image is
     picked inside TFlagControl.ShowFlag (`mov edx,4` @0x5575A200) / ShowStructureFlag (`xor edx,edx; mov dl,
     [ebp+0Ch]; shr edx,6` @0x5575A364); both run with the caller's EBX (= the structure in TPlayerStructure.Show)
     saved at [ebp-0Ch].  Caves 0x558E04A0: when the return address is the TPlayerStructure.Show call site
     (0x5576101B / 0x55761046, compared PIC via call/pop) and the structure is the Nest (RID 0x00E16088) -> SHORT_ID.
     The Nest's flag y (patch_eagle_nest_v7 cave 'EGF1', two `mov ecx,-69`) -> -69 + (54 - POLE_H) so the foot
     stays on the crag rim.
Backups .bak_eagle11 (PRO_EAGL.ILB, Flags.ilb, AoWEPACK.dll).  ⚠ Flags.ilb is already a shipped --add file.
Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_eagle_nest_gfx_v1 as G1  # noqa: E402
import patch_eagle_nest_v2 as V2  # noqa: E402
import patch_eagle_nest_v6 as V6  # noqa: E402
import patch_eagle_nest_v7 as V7  # noqa: E402

TAG = ".bak_eagle11"
EAGL = G1.EAGL
FLAGS = game_file(os.path.join("Images", "Flags.ilb"))
SHORT_ID, POLE_H = 96, 30
CAVE, CAVE_END, MAGIC = 0x558E04A0, 0x558E0540, b"EGP1"
S1, S1_ORIG, S1_BACK, RET1 = 0x5575A200, bytes.fromhex("ba04000000"), 0x5575A205, 0x5576101B
S2, S2_ORIG, S2_BACK, RET2 = 0x5575A364, bytes.fromhex("33d28a550cc1ea06"), 0x5575A36C, 0x55761046
OLD_Y, NEW_Y = V7.FLAG[1], V7.FLAG[1] + (54 - POLE_H)


def build_flags(raw):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    src = by[4].primary
    w, h, rows = ilb.decode_record(lib, src)
    assert (w, h) == (9, 54)
    img = Image.new("RGBA", (w, POLE_H))
    img.putdata([q or (0, 0, 0, 0) for row in rows[:POLE_H] for q in row])
    rec = copy.deepcopy(src); rec["name"] = "FlagPoleShort.BMP"
    ilb.encode_image(lib, rec, img)
    lib.images = [im for im in lib.images if im.id != SHORT_ID] + [ilb.Image(SHORT_ID, parts=[rec])]
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    return None if out == raw else out


def check(label, ret, delta=0x11111111):
    return f"""
    call {label}_n
{label}_n:
    pop ecx
    add ecx, {delta & 0xFFFFFFFF:#x}
    cmp dword ptr [ebp + 0x4], ecx
    jne {label}_d
    mov ecx, dword ptr [ebp - 0xc]
    test ecx, ecx
    jz {label}_d
    mov ecx, dword ptr [ecx + 0x8]
    test ecx, ecx
    jz {label}_d
    cmp dword ptr [ecx + 0xc], {V2.RID:#x}
    jne {label}_d
    mov edx, {SHORT_ID:#x}
{label}_d:
"""


def epk_patches(d, pe, base):
    def mk(d1=0x11111111, d2=0x11111111):
        return ("    mov edx, 0x4\n" + check("p1", RET1, d1) + f"    jmp {S1_BACK:#x}\n"
                "p2_start:\n    xor edx, edx\n    mov dl, byte ptr [ebp + 0xc]\n    shr edx, 0x6\n"
                + check("p2", RET2, d2) + f"    jmp {S2_BACK:#x}\n")
    probe = OV.asm(mk(), CAVE + 4)                 # pass 1: find the runtime anchors (the `pop ecx` addresses)
    pops = [CAVE + 4 + i for i in range(len(probe) - 3) if probe[i] == 0x59 and probe[i + 1:i + 3] == b"\x81\xc1"]
    assert len(pops) == 2, pops
    src = mk(RET1 - pops[0], RET2 - pops[1])       # PIC: anchor + (ret - anchor_va) = runtime return address
    code = OV.asm(src, CAVE + 4)
    assert len(code) == len(probe)
    z = MAGIC + code
    assert len(z) <= CAVE_END - CAVE
    k = OV.asm(src.split("p2_start:")[0], CAVE + 4)            # offset of p2_start
    p2 = CAVE + 4 + len(k)
    P = [(S1, S1_ORIG, b"\xe9" + struct.pack("<i", CAVE + 4 - (S1 + 5))),
         (S2, S2_ORIG, b"\xe9" + struct.pack("<i", p2 - (S2 + 5)) + b"\x90" * 3),
         (CAVE, bytes(len(z)), z)]
    off = lambda va: pe.get_offset_from_rva(va - base)  # noqa: E731
    z7 = V7.CAVE
    blob = d[off(z7):off(V7.CAVE_END)]
    old = b"\xb9" + struct.pack("<i", OLD_Y); new = b"\xb9" + struct.pack("<i", NEW_Y)
    hits = [i for i in range(len(blob)) if blob[i:i + 5] in (old, new)]
    assert len(hits) == 2, hits
    for i in hits:
        P.append((z7 + i, old, new))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(d, pe, SP.EBASE); st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        for f in (EAGL, FLAGS):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    gd = os.path.dirname(HERE)
    ne = V6.build_eagl(gd); ne = None if open(EAGL, "rb").read() == ne else ne
    nf = build_flags(open(FLAGS, "rb").read())
    files = [(EAGL, ne), (FLAGS, nf)]
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
