#!/usr/bin/env python3
r"""
Surface water <-> cave water and surface ice <-> cave ice fade into each other (2026-11-13).

User: "we currently have cross-level water and ice. they work great, except when placed next to each other, ie:
cave water transitioning into surface water. it creates a shoreline between them, rather than fading into each
other which i would prefer".

Facts: surface water (terrain 0) / ice (6) are TAoWWaterHexagon (Waterhex.ILB / IceHex.ILB); cave water (0xA) and
cave ice (0xD) are ordinary TAoWHexagon tiles.  So the water hexagon saw the cave tile as land -> sand shore pieces
(TAoWWaterHexagon.UpdateTransitions 0x5579AD98 sets the shore bit + per-side base [hex+0x19+dir]), and the cave tile
drew its rocky rim HEXTRANS 0xA3+bl (cave ice 0xD9+bl), displaced, over the water hex above it.
Now (layered on patch_sky_transitions_v2, same wedge idea as water next to Sky):
  * ws2 (hook 0x5579AE30, in front of the sky 'ws' cave): water next to cave water / ice next to cave ice -> side
    base 0x80 ("twin" state 4; below 0xA0, so the cloud overlay and Ziggurat's wave test ignore it).
  * wc2 (hook 0x5579B1C1, replaces the sky 'wc' cave, same per-side drawing): twin side -> fade wedge
    id WEDGE2 0x220 + side*4 + (prev side twin)*2 + (next side twin) = the cave tile texture at the hex edge fading
    into the own tile over ~18 px (shared noise, tapered toward a non-twin neighbour side).  Ice hexes use the
    per-side path only when they have a twin side (Sky sides then draw their single-edge piece).
  * pre (hook 0x5579AA92, in front of the sky rule cave): cave water with surface water above, cave ice with
    surface ice above -> no HEXTRANS rim.
Art: Waterhex.ILB / IceHex.ILB + 24 images each (ids 0x220..0x237).  Water next to cave ICE and ice next to cave
WATER are unchanged (not asked).
Zone AoWEPACK 0x558E1E00..0x558E2000 'WTF1'.  Backups .bak_watertwin (dll + both ILBs).
⚠ Revert before re-running patch_sky_transitions_v2 (hooks / ILBs would be OTHER).  ship Waterhex.ILB + IceHex.ILB.
Dry-run default; --apply; --revert; --preview <png> (offline mock-up).
"""
import copy, os, shutil, struct, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from aowxlib import ilb  # noqa: E402
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import sky_transitions_art2 as ART  # noqa: E402
import patch_sky_transitions_v2 as T2  # noqa: E402

TAG = ".bak_watertwin"
B = 0x55700C00
ZONE, ZONE_END, MAGIC = 0x558E1E00, 0x558E2000, b"WTF1"
WS_OLD, WC_OLD, B2_OLD = 0x558E13A0, T2.WC, 0x558E12C0
TWIN_BASE, WEDGE2 = 0x80, 0x220
FADE_D = 18.0
TWIN = {0: 0xA, 6: 0xD}                         # water class terrain -> its cave twin


# ------------------------------------------------------------------------------------------------------------ code
def build_zone():
    ws2, pre, wc2 = ZONE + 0x10, ZONE + 0x40, ZONE + 0x70
    c_ws = OV.asm(f"""
        mov eax, dword ptr [ebx + 4]
        mov al, byte ptr [eax + 0x14]
        mov ah, byte ptr [edi + 0x14]
        cmp ax, 0x0a00
        je tw
        cmp ax, 0x0d06
        je tw
        jmp {WS_OLD:#x}
    tw:
        mov cl, {TWIN_BASE:#x}
        jmp {T2.ZIG_W_STORE:#x}
    """, ws2)
    c_pre = OV.asm(f"""
        cmp al, 0xa
        jne p1
        test edi, edi
        je {T2.EXIT:#x}
    p1:
        cmp al, 0xd
        jne p2
        cmp edi, 6
        je {T2.EXIT:#x}
    p2:
        jmp {B2_OLD:#x}
    """, pre)
    c_wc = OV.asm(f"""
        movzx eax, byte ptr [esi + 0x14]
        test eax, eax
        je {T2.SHORE_END:#x}
        mov edx, dword ptr [esi + 4]
        mov dl, byte ptr [edx + 0x14]
        test dl, dl
        je w_water
        cmp dl, 6
        jne orig
        xor ecx, ecx
    i_sk:
        call stt
        cmp eax, 4
        je i_any
        inc ecx
        cmp ecx, 6
        jb i_sk
        jmp orig
    i_any:
        push 1
        jmp go
    w_water:
        xor ecx, ecx
    sk:
        call stt
        test eax, eax
        jne w_any
        inc ecx
        cmp ecx, 6
        jb sk
    orig:
        mov al, byte ptr [esi + 0x14]
        test al, al
        jmp {T2.WHOOK2_RET:#x}
    w_any:
        push 0
    go:
        xor edi, edi
    lp:
        movzx eax, byte ptr [esi + 0x14]
        bt eax, edi
        jae nx
        mov ecx, edi
        call stt
        cmp dword ptr [esp], 0
        je s_ok
        cmp eax, 4
        je s_ok
        xor eax, eax
    s_ok:
        test eax, eax
        jne wedge
        movzx edx, byte ptr [esi + edi + 0x1a]
        lea ecx, [edi + edi*4]
        mov eax, {T2.SINGLE_PACK:#x}
        shr eax, cl
        and eax, 0x1f
        add edx, eax
        call draw
        jmp nx
    wedge:
        cmp eax, 4
        je wedge4
        dec eax
        shl eax, 4
        mov ebx, eax
        lea ecx, [edi + 5]
        cmp ecx, 6
        jb p1
        sub ecx, 6
    p1:
        call stt
        cmp eax, 4
        jne p1b
        xor eax, eax
    p1b:
        shl eax, 2
        add ebx, eax
        lea ecx, [edi + 1]
        cmp ecx, 6
        jb p2
        sub ecx, 6
    p2:
        call stt
        cmp eax, 4
        jne p2b
        xor eax, eax
    p2b:
        add ebx, eax
        imul eax, edi, 0x30
        add ebx, eax
        lea edx, [ebx + {ART.WEDGE_BASE:#x}]
        call draw
        jmp nx
    wedge4:
        xor ebx, ebx
        lea ecx, [edi + 5]
        cmp ecx, 6
        jb q1
        sub ecx, 6
    q1:
        call stt
        cmp eax, 4
        jne q1b
        or ebx, 2
    q1b:
        lea ecx, [edi + 1]
        cmp ecx, 6
        jb q2
        sub ecx, 6
    q2:
        call stt
        cmp eax, 4
        jne q2b
        or ebx, 1
    q2b:
        lea edx, [ebx + edi*4 + {WEDGE2:#x}]
        call draw
    nx:
        inc edi
        cmp edi, 6
        jb lp
        add esp, 4
        jmp {T2.SHORE_END:#x}
    stt:
        movzx eax, byte ptr [esi + 0x14]
        bt eax, ecx
        jae st0
        movzx eax, byte ptr [esi + ecx + 0x1a]
        cmp eax, {TWIN_BASE:#x}
        je st4
        cmp eax, 0xa0
        jb st0
        sub eax, 0xa0
        shr eax, 5
        inc eax
        ret
    st4:
        mov eax, 4
        ret
    st0:
        xor eax, eax
        ret
    draw:
        mov eax, dword ptr [ebp - 0x1c]
        call {T2.GETIMG:#x}
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
    """, wc2)
    assert len(c_ws) <= 0x30 and len(c_pre) <= 0x30 and 0x70 + len(c_wc) <= ZONE_END - ZONE, (len(c_ws), len(c_wc))
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    for at, c in ((ws2, c_ws), (pre, c_pre), (wc2, c_wc)):
        z[at - ZONE:at - ZONE + len(c)] = c
    return bytes(z), ws2, pre, wc2


def epk_patches():
    z, ws2, pre, wc2 = build_zone()
    j = lambda at, to: b"\xe9" + T2.rel(at, to)  # noqa: E731
    return [(ZONE, bytes(len(z)), z),
            (T2.WHOOK, j(T2.WHOOK, WS_OLD), j(T2.WHOOK, ws2)),
            (T2.HOOK, j(T2.HOOK, B2_OLD), j(T2.HOOK, pre)),
            (T2.WHOOK2, j(T2.WHOOK2, WC_OLD), j(T2.WHOOK2, wc2))]


# ------------------------------------------------------------------------------------------------------------- art
def twin_tiles():
    import transitions_preview as TP
    t = TP.tiles()
    return {0: t[0xA][0], 6: t[0xD][0]}


def wedge2(side, p4, n4, own, twin):
    """shore-canvas RGBA: the cave twin's tile texture along engine side `side`, fading into the own tile"""
    d, owner, n = ART._wedge_geom()
    e = ART.ENG2HEX[side]
    ep, en = ART.ENG2HEX[(side + 5) % 6], ART.ENG2HEX[(side + 1) % 6]
    out = np.zeros((ART.SH, ART.SW, 4), np.uint8)
    for y in range(32):
        for x in range(48):
            if not ART.MASK[y, x] or owner[y, x] != e:
                continue
            a = 1.0 - float(ART._smooth(0.0, FADE_D, d[e, y, x] + 0.6 * n[y, x]))
            for is4, en_ in ((p4, ep), (n4, en)):
                if not is4:
                    a *= float(ART._smooth(0.0, 9.0, d[en_, y, x] - d[e, y, x]))
            if a < 0.04:
                continue
            col = own[y, x, :3].astype(float) * (1 - a) + twin[y, x, :3].astype(float) * a
            out[ART.SOY + y, ART.SOX + x, :3] = np.clip(np.round(col), 0, 255).astype(np.uint8)
            out[ART.SOY + y, ART.SOX + x, 3] = 255
    return out


def build_ilb(path, terr, raw=None):
    from PIL import Image
    lib = ilb.read(raw if raw is not None else open(path, "rb").read())
    by = {im.id: im for im in lib.images}
    assert not any(WEDGE2 <= i < WEDGE2 + 24 for i in by), "twin wedges already present"
    own = T2._decode(lib, by[0x8C].primary)
    twin = twin_tiles()[terr]
    tpl = by[0xA0].primary
    for side in range(6):
        for k in range(4):
            rec = copy.deepcopy(tpl); rec["name"] = "ztwin_wedge.BMP"
            ilb.encode_image(lib, rec, Image.fromarray(wedge2(side, k >> 1, k & 1, own, twin), "RGBA"))
            lib.images.append(ilb.Image(WEDGE2 + side * 4 + k, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


FILES = ((T2.WATERHEX, 0), (T2.ICEHEX, 6))
NB = [(0, -2), (1, -1), (1, 1), (0, 2), (-1, 1), (-1, -1)]     # engine sides in half-row coords (dx, dY)


def preview(out):
    """mock-up: left half current look is not reproduced - only the new wedges over plain tiles, x3"""
    from PIL import Image
    tw = twin_tiles()
    img = np.zeros((2 * 300, 520, 3), np.uint8)
    for row, (path, terr) in enumerate(FILES):
        lib = ilb.read(open(path, "rb").read())
        by = {im.id: im for im in lib.images}
        tiles = [T2._decode(lib, by[0x8C + v].primary) for v in range(16) if 0x8C + v in by]
        own = tiles[0]
        grid = {}
        for cx in range(10):
            for cy in range(8):
                Y = 2 * cy + (cx & 1)
                blob = (cx - 4.5) ** 2 + ((Y - 8) * 0.55) ** 2 < 6.5 or (cx >= 7 and cy <= 2)
                grid[(cx, Y)] = "T" if blob else "W"
        for (cx, Y), k in sorted(grid.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            px, py = 20 + 32 * cx, 20 + row * 300 + 16 * Y
            t = tw[terr] if k == "T" else tiles[(cx * 7 + Y * 3) % len(tiles)]
            for y in range(32):
                for x in range(48):
                    if ART.MASK[y, x]:
                        img[py + y, px + x] = t[y, x, :3]
        for (cx, Y), k in grid.items():
            if k != "W":
                continue
            st = [grid.get((cx + dx, Y + dy)) == "T" for dx, dy in NB]
            px, py = 20 + 32 * cx, 20 + row * 300 + 16 * Y
            for s in range(6):
                if st[s]:
                    w = wedge2(s, st[(s + 5) % 6], st[(s + 1) % 6], own, tw[terr])
                    m = w[..., 3] > 0
                    ys, xs = np.nonzero(m)
                    img[py + ys - ART.SOY, px + xs - ART.SOX] = w[ys, xs, :3]
    Image.fromarray(img).resize((520 * 2, 600 * 2), Image.NEAREST).save(out)
    print("preview ->", out)


def main():
    import pefile
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1]); return 0
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches()
    rl = {0x55700000 + r.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for r in b.entries if r.type == 3}
    bad = [hex(r) for r in rl if any(va - 3 <= r < va + len(o) for va, o, _ in P)]
    st = ["vanilla" if d[va - B:va - B + len(o)] == o else "ours" if d[va - B:va - B + len(n)] == n else "OTHER"
          for va, o, n in P]
    print("AoWEPACK zone %#x + 3 hooks: %s | relocs %s" % (ZONE, st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            with open(SP.EPK, "r+b") as fh:
                for va, o, n in P:
                    fh.seek(va - B); fh.write(o)
            print("reverted AoWEPACK")
        for f, terr in FILES:
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                if build_ilb(f, terr, open(bk, "rb").read()) != open(f, "rb").read():
                    print("ABORT: %s changed since this patch" % os.path.basename(f)); return 1
                shutil.copy2(bk, f); print("restored", os.path.basename(f))
        return 0
    todo = {}
    for f, terr in FILES:
        cur = open(f, "rb").read()
        have = any(WEDGE2 <= im.id < WEDGE2 + 24 for im in ilb.read(cur).images)
        print(os.path.basename(f), "already has the twin wedges" if have else "+24 images")
        if not have:
            todo[f] = build_ilb(f, terr, cur)
    if not todo and st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        with open(SP.EPK, "r+b") as fh:
            for va, o, n in P:
                fh.seek(va - B); fh.write(n)
    for f, nb in todo.items():
        shutil.copy2(f, bak_path(f, TAG))
        with open(f, "wb") as fh:
            fh.write(nb)
        assert open(f, "rb").read() == nb
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
