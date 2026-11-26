#!/usr/bin/env python3
r"""
Sky / Clear Sky / Chasm terrain transitions v1 (2026-11-06).

User: "we also need to improve the transitions between sky/clear sky/chasm with other terrains (without changing any
existing transitions between vanilla terrains). and improve the transition between each other too".

Before (Ziggurat port, patch_sky_chasm_engine_v1 block B @0x55850B50): Sky vs Chasm and Sky vs Clear Sky = hard hex
edges; lava / earth / rock / cave ice next to Sky or Chasm were treated like cave water (crust fringe, no cliff
underside); Chasm used the same brown lips/cliffs as Sky.  Offline mock-ups: transitions_preview.py.

AoWEPACK (zone 0x558E1200..0x558E1400 'STR1', PIC):
  1. UpdateTransition hook 0x5579AA92 (jmp block B) -> new rule block B2, which only acts when Sky (0xE) or Chasm
     (0xB) is involved, then falls through to Ziggurat's block B (+3, after its movsx) -> vanilla pairs unchanged:
       both Sky-family, different kind (Sky / Clear Sky / Chasm) -> blend ids 0x70.. (sky_transitions_art.BLEND),
         Clear-ness = hexagon resource RID>>16 == 0x5A1B (or the combat 0xAA0E02); the neighbour's hexagon =
         HSE TMapField.GetMaxLevelTerrainHS(TMapLevel.GetField(level, nx, ny)) (HSE called through the GetField
         import delta, no new imports);
       Chasm vs 'island' terrain (1-5, 7, 8, 9, 0xC, 0xD) -> basalt lips 0x85 / 0x82 (+bl, displaced);
       Sky vs island terrain -> Ziggurat's lips 0xE9 / 0xE6 (now also for earth, rock, lava, cave ice).
  2. Ziggurat block A cliff faces (Sky/Chasm hex under land): land mask 0x103E -> 0x33BE (+ earth, rock, lava, cave
     ice) @0x5585091E.
  3. TAoWHexagon.ChangeTerrain InvalidateStaticScene call 0x5579A90A -> cave: on a Sky field, first
     HSE TMapField.UpdateNeighbourTerrain(field) - painting Clear Sky over Sky (same terrain, re-picked tile) never
     told the neighbours, so their edges would stay stale.
Images\HEXTRANS.ILB: + ids 0x70..0x87 (blends, basalt lips); Chasm cliff faces 0x180..0x1C7 re-tinted to basalt
(from the .bak originals, so re-runs are idempotent).
Backups .bak_skytrans (AoWEPACK.dll, HEXTRANS.ILB).  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import sky_transitions_art as ART  # noqa: E402

TAG = ".bak_skytrans"
HEXT = game_file(os.path.join("Images", "HEXTRANS.ILB"))
ZONE, ZONE_END, MAGIC = 0x558E1200, 0x558E1400, b"STR1"
HOOK, ZIG_B = 0x5579AA92, 0x55850B50
EXIT = 0x5579AC88
CLIFF_MASK_AT = 0x5585091E
NB_CALL, INVALIDATE = 0x5579A90A, 0x5570265C
GETFIELD_THUNK, HSE_GETFIELD = 0x557020DC, 0x556087B8
HSE_TERRAIN_HS, HSE_UPD_NEIGH = 0x556082B4, 0x55607F9C
ISLAND = 0x33BE


def rel(at, to):
    return struct.pack("<i", to - (at + 5))


def build_zone():
    hd = ZONE + 0x10                                           # hse_delta: eax = HSE runtime - static
    hd_code = (b"\xe8\x00\x00\x00\x00" + b"\x58" + b"\x05" + struct.pack("<i", (GETFIELD_THUNK + 2) - (hd + 5))
               + b"\x8b\x00\x8b\x00" + b"\x2d" + struct.pack("<I", HSE_GETFIELD) + b"\xc3")
    ic = ZONE + 0x30                                           # isclear: eax = resource -> 0/1
    ic_code = OV.asm("""
        test eax, eax
        jz z
        mov eax, dword ptr [eax + 0xc]
        cmp eax, 0xaa0e02
        je one
        shr eax, 16
        cmp eax, 0x5a1b
        je one
    z:
        xor eax, eax
        ret
    one:
        mov eax, 1
        ret
    """, ic)
    nc = ZONE + 0x60                                           # nclear: neighbour hexagon clear flag
    nc_code = OV.asm(f"""
        push ebx
        mov eax, dword ptr [esi + 4]
        mov eax, dword ptr [eax + 4]
        mov edx, dword ptr [esp + 16]
        mov ecx, dword ptr [esp + 20]
        call {GETFIELD_THUNK:#x}
        test eax, eax
        jz z
        mov ebx, eax
        call {hd:#x}
        add eax, {HSE_TERRAIN_HS:#x}
        mov edx, eax
        mov eax, ebx
        call edx
        test eax, eax
        jz z
        mov eax, dword ptr [eax + 8]
        pop ebx
        jmp {ic:#x}
    z:
        xor eax, eax
        pop ebx
        ret
    """, nc)
    b2 = ZONE + 0xB0
    B = ART.BLEND
    b2_code = OV.asm(f"""
        movsx ebp, al
        cmp ebp, 0xe
        je bs
        cmp ebp, 0xb
        jne isl
    bs:
        cmp edi, 0xe
        je both
        cmp edi, 0xb
        jne isl
    both:
        mov ecx, 2
        cmp ebp, 0xb
        je lk1
        mov eax, dword ptr [esi + 8]
        call {ic:#x}
        mov ecx, eax
    lk1:
        push ecx
        mov ecx, 2
        cmp edi, 0xb
        je lk2
        call {nc:#x}
        mov ecx, eax
    lk2:
        pop eax
        cmp eax, ecx
        je done
        lea eax, [eax + eax*2]
        add eax, ecx
        mov dl, {B[("S", "C")]:#x}
        cmp eax, 1
        je lsto
        mov dl, {B[("S", "X")]:#x}
        cmp eax, 2
        je lsto
        mov dl, {B[("C", "S")]:#x}
        cmp eax, 3
        je lsto
        mov dl, {B[("C", "X")]:#x}
        cmp eax, 5
        je lsto
        mov dl, {B[("X", "S")]:#x}
        cmp eax, 6
        je lsto
        mov dl, {B[("X", "C")]:#x}
    lsto:
        mov al, dl
        add al, bl
        movzx edx, bl
        mov byte ptr [esi + edx + 0x10], al
    done:
        jmp {EXIT:#x}
    isl:
        mov edx, {ISLAND:#x}
        cmp ebp, 0xb
        jne i2
        cmp edi, 0xf
        ja zig
        bt edx, edi
        jae zig
        mov al, {ART.CHASM_LIP_LOW_CHASM:#x}
        jmp lstd
    i2:
        cmp edi, 0xb
        jne i3
        cmp ebp, 0xf
        ja zig
        bt edx, ebp
        jae zig
        mov al, {ART.CHASM_LIP_LOW_LAND:#x}
        jmp lstd
    i3:
        cmp ebp, 0xe
        jne i4
        cmp edi, 0xf
        ja zig
        bt edx, edi
        jae zig
        mov al, 0xe9
        jmp lstd
    i4:
        cmp edi, 0xe
        jne zig
        cmp ebp, 0xf
        ja zig
        bt edx, ebp
        jae zig
        mov al, 0xe6
    lstd:
        add al, bl
        movzx edx, bl
        mov byte ptr [esi + edx + 0x10], al
        mov byte ptr [esp], 1
        jmp {EXIT:#x}
    zig:
        jmp {ZIG_B + 3:#x}
    """, b2)
    nb = ZONE + 0x1C0
    nb_code = OV.asm(f"""
        push eax
        push ecx
        push edx
        mov eax, dword ptr [ebx + 4]
        test eax, eax
        jz x
        cmp byte ptr [eax + 0x14], 0xe
        jne x
        push eax
        call {hd:#x}
        add eax, {HSE_UPD_NEIGH:#x}
        mov edx, eax
        pop eax
        call edx
    x:
        pop edx
        pop ecx
        pop eax
        jmp {INVALIDATE:#x}
    """, nb)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    for at, code in ((hd, hd_code), (ic, ic_code), (nc, nc_code), (b2, b2_code), (nb, nb_code)):
        o = at - ZONE
        assert not any(z[o:o + len(code)]), hex(at)
        z[o:o + len(code)] = code
    assert ic - hd >= len(hd_code) and nc - ic >= len(ic_code) and b2 - nc >= len(nc_code) and nb - b2 >= len(b2_code), \
        (len(hd_code), len(ic_code), len(nc_code), len(b2_code))
    assert nb + len(nb_code) <= ZONE_END
    return bytes(z), b2, nb


def epk_patches():
    z, b2, nb = build_zone()
    return [
        (ZONE, bytes(len(z)), z),
        (HOOK, b"\xe9" + rel(HOOK, ZIG_B), b"\xe9" + rel(HOOK, b2)),
        (CLIFF_MASK_AT, struct.pack("<I", 0x103E), struct.pack("<I", ISLAND)),
        (NB_CALL, b"\xe8" + rel(NB_CALL, INVALIDATE), b"\xe8" + rel(NB_CALL, nb)),
    ]


def _decode(lib, rec):
    import numpy as np
    w, h, rows = ilb.decode_record(lib, rec)
    return np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)


def build_hextrans(gd):
    from PIL import Image
    src = bak_path(HEXT, TAG)
    raw = open(src if os.path.exists(src) else HEXT, "rb").read()
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    assert not any(i in by for i in range(0x70, 0x88)), "HEXTRANS source already has ids 0x70..0x87"
    ht = {i: _decode(lib, by[i].primary) for i in list(range(0xE6, 0xEC)) + list(range(0x180, 0x1C8)) if i in by}
    new = ART.all_images(gd, ht)
    cliffs = ART.chasm_cliffs(ht)
    tpl = by[0x16].primary
    for i, a in sorted(new.items()):
        rec = copy.deepcopy(tpl); rec["name"] = "zsky_trans.BMP"
        ilb.encode_image(lib, rec, Image.fromarray(a, "RGBA"))
        lib.images.append(ilb.Image(i, parts=[rec]))
    for i, a in cliffs.items():
        ilb.encode_image(lib, by[i].primary, Image.fromarray(a, "RGBA"))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if "--dis" in sys.argv:
        import capstone
        z, b2, nb = build_zone()
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(z[4:], ZONE + 4):
            print("%08x %s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK", st, "relocs", bad or "none")
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        bk = bak_path(HEXT, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, HEXT); print("restored", bk)
        return 0
    gd = os.path.dirname(HERE)
    nh = build_hextrans(gd)
    cur = open(HEXT, "rb").read()
    nh = None if nh == cur else nh
    print("HEXTRANS.ILB", "already applied" if nh is None else "write (%d B)" % len(nh))
    if nh is None and st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert, --dis)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    if nh is not None:
        bk = bak_path(HEXT, TAG)
        if not os.path.exists(bk):
            shutil.copy2(HEXT, bk)
        with open(HEXT, "r+b") as fh:
            fh.write(nh); fh.truncate()
        assert open(HEXT, "rb").read() == nh
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
