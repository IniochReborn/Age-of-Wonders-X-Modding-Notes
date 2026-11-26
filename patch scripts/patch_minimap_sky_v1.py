#!/usr/bin/env python3
r"""
Minimap: proper Sky / Clear Sky / Chasm textures (2026-11-13).

User: "minimap also needs to improve for sky terrains".

RE (AoWTools.dll, base 0x59700000, loaded by AoWx.exe and AoWDevX.exe as aowtools.dll): TScanner.DrawMap
0x59702C90 fills every explored field with a 64x64 texture from Int\ScanTile.ilb, image index =
terrain (GetTerrain 0x597026A0 = field byte +0x14) when the field has no overlay, else (overlay+1)*16 + terrain
(terrain 0xF and unexplored fields are special).  Sky is terrain 0xE = the old "Coast" texture (looks like water),
Chasm 0xB = the old uWasteland grey, Clear Sky had nothing of its own.
Now:
  * Int\ScanTile.ilb: image 0x0E = night sky (deep blue, faint cloud wisps, a few stars), 0x0B = Chasm (near black
    with violet veins), NEW 0xB6 = Clear Sky (bright blue, white clouds).  Colours taken from the real tiles.
  * AoWTools.dll: DrawMap's GetTerrain call @0x59702F76 -> cave 0x5970A000 'MMS1': terrain 0xE whose field carries a
    Clear Sky resource (any object in the field HS array with resource id >> 16 == 0x5A1B - the same test as the
    AoWEPACK 'fc' cave) -> pseudo terrain 0xB6 -> image 0xB6.  Only DrawMap is hooked; GetTerrain itself unchanged.
Backups .bak_mmsky (AoWTools.dll, ScanTile.ilb).  Ship both.  Dry-run default; --apply; --revert; --preview <png>.
"""
import copy, os, shutil, struct, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from aowxlib import ilb  # noqa: E402
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import sky_clouds_art as SKY  # noqa: E402
import sky_transitions_art2 as ART  # noqa: E402

TAG = ".bak_mmsky"
DLL = game_file("AoWTools.dll")
SCAN = game_file(os.path.join("Int", "ScanTile.ilb"))
BASE, V2F = 0x59700000, 0x59700C00           # CODE: file offset = VA - V2F
CAVE, CAVE_END, MAGIC = 0x5970A000, 0x5970A0C0, b"MMS1"
CALL_AT, GETTERRAIN, GETFIELD_THUNK, MODE_CELL = 0x59702F76, 0x597026A0, 0x59701A54, 0x5970E0E8
# Clear Sky pseudo terrain: its base image id must be free AND every overlay id (overlay+1)*16 + id must be beyond the
# library (max id 0xAC) so a Clear Sky field with an overlay takes DrawMap's own out-of-range path instead of
# showing some other terrain's overlay tile (0x16 would have hit 0x76 / 0x96)
ID_SKY, ID_CHASM, ID_CLEAR = 0x0E, 0x0B, 0xB6


def rel(at, to):
    return struct.pack("<i", to - (at + 5))


def cave_code():
    at = CAVE + 8
    c = OV.asm(f"""
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov edi, ecx
        call {GETTERRAIN:#x}
        cmp al, 0xe
        jne done
        push eax
        call d1
    d1:
        pop eax
        mov eax, dword ptr [eax + 0x11111111]
        mov eax, dword ptr [eax]
        lea ecx, [edi + 6]
        lea edx, [esi + 6]
        cmp dword ptr [eax + 0x11c], 0
        je g
        lea edx, [esi + 8]
    g:
        mov eax, dword ptr [ebx + 0x15c]
        call {GETFIELD_THUNK:#x}
        cmp eax, 0x10000
        jb nc
        mov edx, dword ptr [eax + 8]
        movzx ecx, byte ptr [eax + 0xd]
        cmp edx, 0x10000
        jb nc
    lp:
        dec ecx
        js nc
        mov eax, dword ptr [edx + ecx*4]
        cmp eax, 0x10000
        jb lp
        mov eax, dword ptr [eax + 8]
        cmp eax, 0x10000
        jb lp
        mov eax, dword ptr [eax + 0xc]
        shr eax, 16
        cmp eax, 0x5a1b
        jne lp
        pop eax
        mov al, {ID_CLEAR:#x}
        jmp done
    nc:
        pop eax
    done:
        pop edi
        pop esi
        pop ebx
        ret
    """, at)
    k = c.index(bytes.fromhex("588b8011111111"))                # pop eax / mov eax,[eax+disp32]
    c = c[:k + 3] + struct.pack("<i", MODE_CELL - (at + k)) + c[k + 7:]
    z = MAGIC + bytes(4) + c
    assert len(z) <= CAVE_END - CAVE, len(z)
    return z + bytes(CAVE_END - CAVE - len(z))


def patches():
    z = cave_code()
    return [(CAVE, bytes(len(z)), z),
            (CALL_AT, b"\xe8" + rel(CALL_AT, GETTERRAIN), b"\xe8" + rel(CALL_AT, CAVE + 8))]


# ------------------------------------------------------------------------------------------------------------- art
def _mean(tiles):
    px = np.concatenate([t[..., :3][ART.MASK] for t in tiles]).astype(float)
    return px.mean(0)


def _fbm(seed):
    a = ART._noise(seed, blur=3) * 0.6 + ART._noise(seed + 1, blur=1) * 0.25
    b = ART._noise(seed + 2, n=32, blur=2)
    a = a + np.kron(b, np.ones((2, 2))) * 0.4
    return (a - a.min()) / (a.max() - a.min())


def textures(gd):
    """{id: 64x64x3 uint8}, all tileable"""
    out = {}
    sky = _mean(SKY.sky_tiles())
    cl = _mean(SKY.clear_tiles())
    ch = _mean(SKY.chasm_tiles(gd))
    n = _fbm(0x5C1)
    # night sky: tile colour lifted a little (the map dot is tiny), lavender wisps, sparse stars
    base = sky * 1.15 + np.array([4, 6, 18.0])
    wisp = np.clip((n - 0.55) / 0.45, 0, 1)[..., None]
    t = base[None, None, :] * (0.92 + 0.16 * _fbm(0x5C7)[..., None]) * (1 - 0.45 * wisp) + \
        np.array(SKY.SKY_CLOUD, float)[None, None, :] * 0.45 * wisp
    rng = np.random.default_rng(0x57A2)
    for _ in range(26):
        y, x = rng.integers(0, 64, 2)
        t[y, x] = t[y, x] * 0.35 + np.array([235, 235, 255.0]) * 0.65
    out[ID_SKY] = np.clip(np.round(t), 0, 255).astype(np.uint8)
    # clear sky: bright blue with soft white cloud blotches
    cw = np.clip((_fbm(0xC1E) - 0.48) / 0.3, 0, 1)[..., None]
    t = cl[None, None, :] * (0.96 + 0.08 * n[..., None]) * (1 - 0.7 * cw) + np.array([250, 252, 255.0]) * 0.7 * cw
    out[ID_CLEAR] = np.clip(np.round(t), 0, 255).astype(np.uint8)
    # chasm: near black, violet web
    web = np.abs(_fbm(0xCA5) - 0.5) * 2
    vein = (0.6 * np.clip(1 - web / 0.05, 0, 1))[..., None]
    t = (ch * 0.55)[None, None, :] * (0.8 + 0.4 * n[..., None]) * (1 - vein) + np.array([125, 70, 190.0]) * vein
    out[ID_CHASM] = np.clip(np.round(t), 0, 255).astype(np.uint8)
    return out


def build_scan(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    assert ID_CLEAR not in by, "ScanTile already has the Clear Sky image"
    tex = textures(gd)
    for i in (ID_SKY, ID_CHASM):
        rgba = np.dstack([tex[i], np.full((64, 64), 255, np.uint8)])
        ilb.encode_image(lib, by[i].primary, Image.fromarray(rgba, "RGBA"))
    rec = copy.deepcopy(by[ID_SKY].primary); rec["name"] = "zclearsky.BMP"
    ilb.encode_image(lib, rec, Image.fromarray(np.dstack([tex[ID_CLEAR], np.full((64, 64), 255, np.uint8)]), "RGBA"))
    lib.images.append(ilb.Image(ID_CLEAR, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    chk = ilb.read(out)                                          # round trip: the three images decode to our pixels
    cb = {im.id: im for im in chk.images}
    for i in (ID_SKY, ID_CHASM, ID_CLEAR):
        w, h, rows = ilb.decode_record(chk, cb[i].primary)
        a = np.array([[q[:3] for q in row] for row in rows], np.int32)
        assert (w, h) == (64, 64) and np.abs(a - tex[i]).max() <= 8, (i, np.abs(a - tex[i]).max())
    assert len(chk.images) == len(by) + 1
    return out


def main():
    import pefile
    gd = os.path.dirname(HERE)
    if "--preview" in sys.argv:
        from PIL import Image
        tex = textures(gd)
        img = np.zeros((64, 3 * 68, 3), np.uint8)
        for k, i in enumerate((ID_SKY, ID_CLEAR, ID_CHASM)):
            img[:, k * 68:k * 68 + 64] = tex[i]
        big = Image.fromarray(img).resize((3 * 68 * 4, 256), Image.NEAREST)
        small = Image.fromarray(np.tile(img[:, :64], (1, 1, 1)))
        big.save(sys.argv[sys.argv.index("--preview") + 1]); print("preview written"); return 0
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(DLL, "rb").read(); pe = pefile.PE(data=d)
    assert pe.OPTIONAL_HEADER.ImageBase == BASE and pe.get_offset_from_rva(CAVE - BASE) == CAVE - V2F
    P = patches()
    rl = {BASE + r.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for r in b.entries if r.type == 3}
    bad = [hex(r) for r in rl if any(va - 3 <= r < va + len(o) for va, o, _ in P)]
    st = ["vanilla" if d[va - V2F:va - V2F + len(o)] == o else "ours" if d[va - V2F:va - V2F + len(n)] == n else "OTHER"
          for va, o, n in P]
    raw = open(SCAN, "rb").read()
    have = ID_CLEAR in {im.id for im in ilb.read(raw).images}
    print("AoWTools.dll cave %#x + DrawMap call: %s | relocs %s | ScanTile.ilb: %s"
          % (CAVE, st, bad or "none", "has the sky textures" if have else "to write"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            with open(DLL, "r+b") as fh:
                for va, o, n in P:
                    fh.seek(va - V2F); fh.write(o)
            print("reverted AoWTools.dll")
        bk = bak_path(SCAN, TAG)
        if have and os.path.exists(bk):
            shutil.copy2(bk, SCAN); print("restored ScanTile.ilb")
        return 0
    if have and st[0] == "ours":
        print("already applied"); return 0
    new_scan = None if have else build_scan(raw, gd)
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(DLL, TAG)
        if not os.path.exists(bk):
            shutil.copy2(DLL, bk)
        with open(DLL, "r+b") as fh:
            for va, o, n in P:
                fh.seek(va - V2F); fh.write(n)
    if new_scan is not None:
        bk = bak_path(SCAN, TAG)
        if not os.path.exists(bk):
            os.makedirs(os.path.dirname(bk), exist_ok=True)
            shutil.copy2(SCAN, bk)
        with open(SCAN, "wb") as fh:
            fh.write(new_scan)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
