#!/usr/bin/env python3
r"""
Sky / Clear Sky / Chasm transitions v2 (2026-11-07) - REPLACES v1 (run patch_sky_transitions_v1.py --revert first).

User: "revert the transitions for solid terrain, those were mostly fine. the only thing i dont like about them is the
left tip has a transparent crack, fix that ... i only wanted sky/clear sky/chasm transitions with each other and with
water etc to be improved .. refer to shoreline (when land meets water), except make it ethereal/fading, kind of like
smoke or fog with curves".

Solid terrain vs Sky / Chasm = Ziggurat again (v1's island mask 0x33BE, basalt Chasm lips + cliffs all dropped), except
  * Images\HEXTRANS.ILB cliff faces 0x100..0x1C7: Ziggurat's art had a few pure-black pixels at the top-left (the
    dark crack at an island's left tip) -> inpainted from their neighbours (sky_transitions_art2.fix_black).
Sky-family pairs (Sky / Clear Sky / Chasm with each other):
  * AoWEPACK zone 'STR2' 0x558E1200..0x558E1400: UpdateTransition hook 0x5579AA92 -> rule b2: both Sky-family and a
    different kind -> HEXTRANS 0x70.. + bl (pair_fog: curving, lobed edge, textures cross-fading like fog, mist);
    everything else -> Ziggurat block B (+3).  Clear-paint neighbour refresh (0x5579A90A) kept from v1.
Water / ice next to Sky-family (the water hex draws a shoreline piece per side config, id = side base + piece 0..31):
  * Ziggurat sets side base 0xA0 (Sky) / 0xC0 (Chasm) in TAoWWaterHexagon.UpdateTransitions (hook 0x5579AE30 ->
    0x55850810).  v2 re-points that hook to cave 'wsh': a Sky neighbour whose hexagon is Clear Sky gets base 0xE0
    (new set) - everything else goes to Ziggurat's code unchanged.
  * Images\Waterhex.ILB + IceHex.ILB: 0xA0..0xDF REPLACED and 0xE0..0xFF ADDED = shore_fog: the vanilla land
    shoreline piece k's curvy shape (0x00+k), widened/warped into fog of the sky texture dissolving into the water/ice.
Backups .bak_skytrans2 (AoWEPACK.dll, HEXTRANS.ILB, Waterhex.ILB, IceHex.ILB); HEXTRANS is rebuilt from the
.bak_skytrans original (pre-v1) when present.  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import sky_transitions_art2 as ART  # noqa: E402

TAG, TAG_V1 = ".bak_skytrans2", ".bak_skytrans"
HEXT = game_file(os.path.join("Images", "HEXTRANS.ILB"))
WATERHEX = game_file(os.path.join("Images", "Waterhex.ILB"))
ICEHEX = game_file(os.path.join("Images", "IceHex.ILB"))
ZONE, ZONE_END, MAGIC = 0x558E1200, 0x558E1400, b"STR2"
HOOK, ZIG_B = 0x5579AA92, 0x55850B50
EXIT = 0x5579AC88
NB_CALL, INVALIDATE = 0x5579A90A, 0x5570265C
WHOOK, ZIG_W, ZIG_W_STORE = 0x5579AE30, 0x55850810, 0x5585082D
GETFIELD_THUNK, HSE_GETFIELD = 0x557020DC, 0x556087B8
HSE_TERRAIN_HS, HSE_UPD_NEIGH = 0x556082B4, 0x55607F9C
# v2.9 (user: "the dirt hex between two bridges has a big transparent crack"): a pair fade spills across the edge into
# the UPPER hex (drawn first).  When that upper Sky/Chasm hex hangs cliff faces (Ziggurat block A: land at its UL / top
# / UR / LL) the spill painted sky over the cliff -> such edges use a ONE-SIDED fade (ids ONE_BASE + ..; lives only in
# the lower hex).  hl = "neighbour hangs cliffs" test, cave 0x558E1500..0x558E15C0 (zero, unclaimed).
HL, HL_END = 0x558E1500, 0x558E15C0
# v2.9b: water hexes with any sky side draw per-edge fog wedges (Waterhex ART.WEDGE_BASE..) + single-edge sand
# pieces themselves; the engine's combination pieces are skipped (they colour 2-3 edges with ONE side's kind).
# Hook TAoWWaterHexagon.ShowDynamic shore block 0x5579B1C1 (mov al,[esi+0x14] / test al,al) -> cave WC.
WHOOK2, WHOOK2_RET, SHORE_END = 0x5579B1C1, 0x5579B1C6, 0x5579B546
WC, WC_END = 0x558E15C0, 0x558E16C0
GETIMG = 0x55702934
SINGLE_PACK = 0xD | 0x11 << 5 | 0xF << 10 | 0x17 << 15 | 0xE << 20 | 0x10 << 25   # one-edge sand pieces per side
ONE_DELTA = ART.ONE_BASE - 0x70


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
    fc = ZONE + 0x60                                           # fclear: eax = map field -> 0/1
    # v2.3: ANY object on the field carrying a Clear Sky resource.  v2.2 asked TMapField.GetMaxLevelTerrainHS, which
    # returns the top "terrain" object - a padless teleporter is a TILTerrainMO, so a Clear Sky hex holding one read
    # as plain Sky and its neighbours drew Sky<->Clear blends (the dark patch under Clear Sky teleporters).
    fc_code = OV.asm(f"""
        push esi
        movzx ecx, byte ptr [eax + 0xd]
        mov esi, dword ptr [eax + 0x8]
    fl:
        dec ecx
        js fno
        mov eax, dword ptr [esi + ecx*4]
        cmp eax, 0x10000
        jb fl
        mov eax, dword ptr [eax + 0x8]
        cmp eax, 0x10000
        jb fl
        push ecx
        call {ic:#x}
        pop ecx
        test eax, eax
        jz fl
        pop esi
        ret
    fno:
        xor eax, eax
        pop esi
        ret
    """, fc)
    nc = ZONE + 0x90                                           # nclear: neighbour (x,y at [esp+12]/[esp+16]) clear
    nc_code = OV.asm(f"""
        mov eax, dword ptr [esi + 4]
        mov eax, dword ptr [eax + 4]
        mov edx, dword ptr [esp + 12]
        mov ecx, dword ptr [esp + 16]
        call {GETFIELD_THUNK:#x}
        test eax, eax
        jz z
        jmp {fc:#x}
    z:
        xor eax, eax
        ret
    """, nc)
    b2 = ZONE + 0xC0
    B = ART.BLEND
    b2_code = OV.asm(f"""
        movsx ebp, al
        cmp ebp, 0xe
        je bs
        cmp ebp, 0xb
        jne zig
    bs:
        cmp edi, 0xe
        je both
        cmp edi, 0xb
        jne zig
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
        mov edx, dword ptr [esp + 4]
        mov ecx, dword ptr [esp + 8]
        push eax
        call {HL:#x}
        test eax, eax
        pop eax
        jz lst2
        add al, {ONE_DELTA:#x}
    lst2:
        movzx edx, bl
        mov byte ptr [esi + edx + 0x10], al
    done:
        jmp {EXIT:#x}
    zig:
        jmp {ZIG_B + 3:#x}
    """, b2)
    nb = ZONE + 0x160
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
    ws = ZONE + 0x1A0                                          # water/ice hex: Clear Sky side -> shore set 0xE0
    ws_code = OV.asm(f"""
        cmp byte ptr [edi + 0x14], 0xe
        je sky
        jmp {ZIG_W:#x}
    sky:
        push ecx
        push edx
        mov eax, edi
        call {fc:#x}
        pop edx
        pop ecx
        mov cl, {ART.SHORE_BASE["S"]:#x}
        test eax, eax
        jz lsw
        mov cl, {ART.SHORE_BASE["C"]:#x}
    lsw:
        jmp {ZIG_W_STORE:#x}
    """, ws)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    parts = [(hd, hd_code), (ic, ic_code), (fc, fc_code), (nc, nc_code), (b2, b2_code), (nb, nb_code), (ws, ws_code)]
    for (at, code), nxt in zip(parts, [p[0] for p in parts[1:]] + [ZONE_END]):
        assert at + len(code) <= nxt, (hex(at), len(code))
        o = at - ZONE
        z[o:o + len(code)] = code
    return bytes(z), b2, nb, ws


def build_wc():
    code = OV.asm(f"""
        movzx eax, byte ptr [esi + 0x14]
        test eax, eax
        je {SHORE_END:#x}
        mov edx, dword ptr [esi + 4]
        cmp byte ptr [edx + 0x14], 0
        jne orig
        xor ecx, ecx
    sk:
        call stt
        test eax, eax
        jne any
        inc ecx
        cmp ecx, 6
        jb sk
    orig:
        mov al, byte ptr [esi + 0x14]
        test al, al
        jmp {WHOOK2_RET:#x}
    any:
        xor edi, edi
    lp:
        movzx eax, byte ptr [esi + 0x14]
        bt eax, edi
        jae nx
        mov ecx, edi
        call stt
        test eax, eax
        jne wedge
        movzx edx, byte ptr [esi + edi + 0x1a]
        lea ecx, [edi + edi*4]
        mov eax, {SINGLE_PACK:#x}
        shr eax, cl
        and eax, 0x1f
        add edx, eax
        call draw
        jmp nx
    wedge:
        dec eax
        shl eax, 4
        mov ebx, eax
        lea ecx, [edi + 5]
        cmp ecx, 6
        jb p1
        sub ecx, 6
    p1:
        call stt
        shl eax, 2
        add ebx, eax
        lea ecx, [edi + 1]
        cmp ecx, 6
        jb p2
        sub ecx, 6
    p2:
        call stt
        add ebx, eax
        imul eax, edi, 0x30
        add ebx, eax
        lea edx, [ebx + {ART.WEDGE_BASE:#x}]
        call draw
    nx:
        inc edi
        cmp edi, 6
        jb lp
        jmp {SHORE_END:#x}
    stt:
        movzx eax, byte ptr [esi + 0x14]
        bt eax, ecx
        jae st0
        movzx eax, byte ptr [esi + ecx + 0x1a]
        cmp eax, 0xa0
        jb st0
        sub eax, 0xa0
        shr eax, 5
        inc eax
        ret
    st0:
        xor eax, eax
        ret
    draw:
        mov eax, dword ptr [ebp - 0x1c]
        call {GETIMG:#x}
        test eax, eax
        je dr_x
        mov ecx, dword ptr [ebp - 0x10]
        sub ecx, 0x20
        mov edx, dword ptr [ebp - 0xc]
        sub edx, 0x13
        push ebx
        push dword ptr [ebp + 8]
        mov ebx, dword ptr [eax]
        call dword ptr [ebx + 0x84]
        pop ebx
    dr_x:
        ret
    """, WC)
    assert len(code) <= WC_END - WC, len(code)
    return code + bytes(WC_END - WC - len(code))


def build_hl():
    """edx = x, ecx = y of the neighbour hex -> eax = 1 if it has land (Ziggurat cliff mask 0x103E) at its UL / top /
    UR / LL (the cliff faces it draws hang there); esi = own hexagon (level = [[esi+4]+4]); keeps ebx/esi/edi/ebp"""
    code = OV.asm(f"""
        push ebx
        push edi
        mov edi, edx
        mov ebx, ecx
        lea edx, [edi - 1]
        mov ecx, edi
        and ecx, 1
        lea ecx, [ebx + ecx - 1]
        call land
        test eax, eax
        jnz yes
        lea edx, [edi + 1]
        mov ecx, edi
        and ecx, 1
        lea ecx, [ebx + ecx - 1]
        call land
        test eax, eax
        jnz yes
        mov edx, edi
        lea ecx, [ebx - 1]
        call land
        test eax, eax
        jnz yes
        lea edx, [edi - 1]
        mov ecx, edi
        and ecx, 1
        add ecx, ebx
        call land
        test eax, eax
        jnz yes
        xor eax, eax
        jmp out
    yes:
        mov eax, 1
    out:
        pop edi
        pop ebx
        ret
    land:
        test edx, edx
        js no
        test ecx, ecx
        js no
        mov eax, dword ptr [esi + 4]
        mov eax, dword ptr [eax + 4]
        cmp edx, dword ptr [eax + 0xc]
        jge no
        cmp ecx, dword ptr [eax + 0x10]
        jge no
        call {GETFIELD_THUNK:#x}
        test eax, eax
        jz no
        movsx eax, byte ptr [eax + 0x14]
        cmp eax, 0xf
        ja no
        mov ecx, 0x103e
        bt ecx, eax
        jae no
        mov eax, 1
        ret
    no:
        xor eax, eax
        ret
    """, HL)
    assert len(code) <= HL_END - HL, len(code)
    return code + bytes(HL_END - HL - len(code))


def epk_patches():
    z, b2, nb, ws = build_zone()
    return [
        (ZONE, bytes(len(z)), z),
        (HOOK, b"\xe9" + rel(HOOK, ZIG_B), b"\xe9" + rel(HOOK, b2)),
        (NB_CALL, b"\xe8" + rel(NB_CALL, INVALIDATE), b"\xe8" + rel(NB_CALL, nb)),
        (WHOOK, b"\xe9" + rel(WHOOK, ZIG_W), b"\xe9" + rel(WHOOK, ws)),
        (HL, bytes(HL_END - HL), build_hl()),
        (WC, bytes(WC_END - WC), build_wc()),
        (WHOOK2, bytes([0x8A, 0x46, 0x14, 0x84, 0xC0]), b"\xe9" + rel(WHOOK2, WC)),
    ]


# ------------------------------------------------------------------------------------------------------------ art
def _decode(lib, rec):
    import numpy as np
    w, h, rows = ilb.decode_record(lib, rec)
    return np.array([[q if q else (0, 0, 0, 0) for q in row] for row in rows], np.uint8)


def _src_raw(path):
    for tag in (TAG, TAG_V1):                                  # the pre-v1 / pre-v2 original
        b = bak_path(path, tag)
        if os.path.exists(b):
            return open(b, "rb").read()
    return open(path, "rb").read()


def build_hextrans(gd):
    from PIL import Image
    lib = ilb.read(_src_raw(HEXT))
    by = {im.id: im for im in lib.images}
    assert not any(i in by for i in range(0x70, 0x88)), "HEXTRANS source already has ids 0x70..0x87"
    assert not any(i in by for i in range(ART.ONE_BASE, ART.ONE_BASE + 0x12)), "HEXTRANS source has one-sided ids"
    src = ART.sources(gd)
    tpl = by[0x16].primary
    for (lo, up), base in sorted(ART.BLEND.items(), key=lambda kv: kv[1]):
        for bl in range(3):
            rec = copy.deepcopy(tpl); rec["name"] = "zsky_trans.BMP"
            ilb.encode_image(lib, rec, Image.fromarray(ART.pair_fog(gd, lo, up, bl, src), "RGBA"))
            lib.images.append(ilb.Image(base + bl, parts=[rec]))
            rec = copy.deepcopy(tpl); rec["name"] = "zsky_trans1.BMP"                   # v2.9 one-sided
            ilb.encode_image(lib, rec, Image.fromarray(ART.pair_fog(gd, lo, up, bl, src, one_sided=True), "RGBA"))
            lib.images.append(ilb.Image(base - 0x70 + ART.ONE_BASE + bl, parts=[rec]))
    # v2.8: land lips + cliff faces - fill see-through slits; v2.9: + the cross-piece holes (fill_tip_holes)
    ht, orig = {}, {}
    for i in list(range(0xE6, 0xEC)) + list(range(0x100, 0x1C8)):
        if i in by:
            orig[i] = _decode(lib, by[i].primary)
            ht[i] = ART.fill_gaps(orig[i]) if i < 0x100 else ART.fill_gaps(ART.grow_top(ART.fix_black(orig[i])))
    ART.fill_tip_holes(ht)
    for i, f in ht.items():
        if (f != orig[i]).any():
            ilb.encode_image(lib, by[i].primary, Image.fromarray(f, "RGBA"))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def build_shores(gd, path):
    from PIL import Image
    lib = ilb.read(_src_raw(path))
    by = {im.id: im for im in lib.images}
    if path == ICEHEX:
        # v2.8 (user: "ice on sky etc looks bad. it should look similar to ice on water"): every Sky-family set
        # (0xA0 Sky / 0xC0 Chasm / 0xE0 Clear) = the ice/water edge art on the edges the Ziggurat piece k is for
        wlib = ilb.read(_src_raw(WATERHEX))
        wby = {im.id: im for im in wlib.images}
        wt = {i: _decode(wlib, wby[i].primary) for i in (0x23, 0x24, 0x25)}
        it = {i: _decode(lib, by[i].primary) for i in (0x23, 0x24, 0x25)}
        zig = {k: _decode(lib, by[0xA0 + k].primary) for k in range(32) if 0xA0 + k in by}
        tpl = by[0xA0].primary
        lib.images = [im for im in lib.images if not 0xA0 <= im.id <= 0xFF]
        for base in (0xA0, 0xC0, 0xE0):
            for k, zp in zig.items():
                rec = copy.deepcopy(tpl)
                rec["name"] = "zsky_iceshore.BMP"
                ilb.encode_image(lib, rec, Image.fromarray(ART.ice_teeth(k, zp, wt, it, ice_tile=_decode(lib, by[0x8C].primary)), "RGBA"))
                lib.images.append(ilb.Image(base + k, parts=[rec]))
        lib.images.sort(key=lambda im: im.id)
        return ilb.write(lib)
    import numpy as np
    src = ART.sources(gd)
    own = _decode(lib, by[0x8C].primary)
    tpl = by[0xA0].primary
    lib.images = [im for im in lib.images if not 0xA0 <= im.id <= 0xFF]
    assert not any(im.id >= ART.WEDGE_BASE for im in lib.images), "Waterhex source already has ids >= 0x100"
    # v2.9b: the Sky-family combination sets stay as (transparent) placeholders - the cave draws wedges instead
    blank = np.zeros((ART.SH, ART.SW, 4), np.uint8)
    blank[ART.SOY + 16, ART.SOX + 24] = (0, 0, 0, 0)
    for base in ART.SHORE_BASE.values():
        for k in range(32):
            rec = copy.deepcopy(tpl); rec["name"] = "zsky_none.BMP"
            ilb.encode_image(lib, rec, Image.fromarray(blank, "RGBA"))
            lib.images.append(ilb.Image(base + k, parts=[rec]))
    for side in range(6):
        for st in (1, 2, 3):
            for pv in range(4):
                for nx in range(4):
                    rec = copy.deepcopy(tpl); rec["name"] = "zsky_wedge.BMP"
                    ilb.encode_image(lib, rec, Image.fromarray(ART.wedge_fog(side, st, pv, nx, own, src), "RGBA"))
                    lib.images.append(ilb.Image(ART.WEDGE_BASE + side * 48 + (st - 1) * 16 + pv * 4 + nx, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


FILES = (HEXT, WATERHEX, ICEHEX)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    if d[ZONE - 0x55700C00:ZONE - 0x55700C00 + 4] == b"STR1":
        print("ABORT: v1 is applied - run patch_sky_transitions_v1.py --revert first"); return 1
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK", st, "relocs", bad or "none")
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        for f in FILES:
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    gd = os.path.dirname(HERE)
    want = {HEXT: build_hextrans(gd), WATERHEX: build_shores(gd, WATERHEX), ICEHEX: build_shores(gd, ICEHEX)}
    todo = {f: b for f, b in want.items() if open(f, "rb").read() != b}
    for f in FILES:
        print(os.path.basename(f), "write (%d B)" % len(want[f]) if f in todo else "already applied")
    if not todo and st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    for f, b in todo.items():
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(b); fh.truncate()
        assert open(f, "rb").read() == b
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
