#!/usr/bin/env python3
r"""
AoWDevX: 4th terrain brush "massive" = 13 hexes wide (2026-10-31).

User: "in the editor, there are terrain brushes (buttons near top bar) that change the size of base terrains being
applied to map. i want to add an additional size (move buttons over to the right to make room). it should be 13 hexes
wide (currently largest brush is 5 hex wide). when hovered over, it should say Select massive brush".
RE: Brush1/2/3BtnClick (0x4296A4/B4/C4) = THSMEdit.SetBrushSize(1/2/3) (HSEPack 0x55612EE4, byte [edit+0x1AC]).
Painting (THSMEdit.DropSelectedPlaceHS) passes radius = size-1 to the map editor -> size 7 = radius 6 = 13 wide.
The brush CURSOR objects are a 3-entry table [edit+0x1B0..0x1B8] (created in THSMEdit.Activate from the
EditBrushes library); +0x1BC is already the map-loaded flag, so a 4th entry is impossible -> the 4 lookups clamp the
index to 3 (the massive brush shows the large brush's cursor; the painted area is the full 13 hexes).
  * AoWDevX DFM: TSpeedButton 'Brush4Btn' after Brush3Btn (+40 px), Hint "Select massive brush", GroupIndex 1 (the
    brush radio group), glyph = a filled dot filling the button (disabled half = ring), OnClick = Brush3BtnClick;
    every Panel2 button right of Brush3Btn moves 40 px right.
  * AoWDevX 0x4296A4..0x4296D4 (the three handlers) rewritten in place: Brush1/2 = size + shared tail; Brush3BtnClick
    picks 7 when Sender != Brush3Btn (field +0x5F8) -> Brush4Btn needs no new published method (table is full).
  * HSEPack: SetBrushSize 0x55612EEC, UpdateFrame 0x55614A43 / 0x55614B6B, DeActivate 0x5561559E (`mov al,[r+1ACh];
    mov r32,[r+eax*4+1ACh]`) -> caves 0x5561CC00.. that clamp al to 3 first.
Backups .bak_massbrush (AoWDevX.exe whole file, HSEPack.dpl).  Dry-run default; --apply; --revert.
"""
import io, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_devx_terrain_palette_v1 as PAL  # noqa: E402
import patch_devx_autosave_v1 as AS  # noqa: E402   (place_dfm, i16)
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_massbrush"
DEVX, HSE, HBASE = game_file("AoWDevX.exe"), game_file("HSEPack.dpl"), 0x55600000
BTN, HINT, SHIFT, SIZE = "Brush4Btn", "Select massive brush", 40, 7
H_BLOCK, H_END = 0x4296A4, 0x4296D4
H_ORIG = bytes.fromhex("b2018b802c020000e81f97fdffc38bc0b2028b802c020000e80f97fdffc38bc0"
                       "b2038b802c020000e8ff96fdffc38bc0")
SETBRUSH, F_BRUSH3 = 0x402DD0, 0x5F8
HCAVE, HCAVE_END, HMAGIC = 0x5561CC00, 0x5561CD00, b"MBR1"
HSITES = [  # (site, original 13 bytes, base reg, dest reg, resume)
    (0x55612EEC, "8a86ac0100008b8486ac010000", "esi", "eax", 0x55612EF9),
    (0x55614A43, "8a86ac0100008b8486ac010000", "esi", "eax", 0x55614A50),
    (0x55614B6B, "8a86ac0100008b9486ac010000", "esi", "edx", 0x55614B78),
    (0x5561559E, "8a83ac0100008b9483ac010000", "ebx", "edx", 0x556155AB),
]


# ---- AoWDevX ---------------------------------------------------------------------------------------------------
def glyph(src_gdata):
    from PIL import Image, ImageDraw
    n = struct.unpack_from("<I", src_gdata, 0)[0]
    im = Image.open(io.BytesIO(src_gdata[4:4 + n])).convert("RGB")
    bg = im.getpixel((0, 31))
    ring = max(((im.getpixel((x, y)), (x, y)) for x in range(32, 64) for y in range(32)
                if im.getpixel((x, y)) != bg and im.getpixel((x, y)) != (255, 255, 255)), default=((128, 128, 140), 0))[0]
    out = Image.new("RGB", (64, 32), bg)
    d = ImageDraw.Draw(out)
    d.ellipse([2, 2, 29, 29], fill=(0, 0, 0))
    d.ellipse([35, 3, 62, 30], outline=(255, 255, 255))
    d.ellipse([34, 2, 61, 29], outline=ring)
    b = io.BytesIO(); out.save(b, "BMP"); bmp = b.getvalue()
    assert len(bmp) == n
    return struct.pack("<I", len(bmp)) + bmp


def new_dfm(dfm):
    D = PAL.DFM(dfm)
    b3 = D.get("Brush3Btn")
    pl3 = dict(SP.props(dfm, b3))
    lv = pl3["Left"]
    x3 = lv[1] if lv[0] == 2 else struct.unpack_from("<h", lv, 1)[0]
    edits = []
    for k in D.get("Panel2")["kids"]:
        if k["cls"] != b"TSpeedButton":
            continue
        pl = SP.props(dfm, k)
        v = dict(pl)["Left"]
        left = v[1] if v[0] == 2 else struct.unpack_from("<h", v, 1)[0]
        if left > x3:
            edits.append((k["start"], k["end"],
                          SP.ser_comp(k["cls"], k["name"], [(a, AS.i16(left + SHIFT) if a == "Left" else b) for a, b in pl])))
    btn = [("Left", AS.i16(x3 + SHIFT)), ("Top", pl3["Top"]), ("Width", pl3["Width"]), ("Height", pl3["Height"]),
           ("Hint", SP.vstr(HINT)), ("GroupIndex", pl3["GroupIndex"]), ("Flat", pl3["Flat"]),
           ("Glyph.Data", SP.vbin(glyph(pl3["Glyph.Data"][5:]))), ("NumGlyphs", pl3["NumGlyphs"]),
           ("OnClick", b"\x07" + bytes([len("Brush3BtnClick")]) + b"Brush3BtnClick")]
    edits.append((b3["end"], b3["end"], SP.ser_comp(b"TSpeedButton", BTN, btn)))
    out = bytearray(); pos = 0
    for s, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
        out += dfm[pos:s] + b; pos = e
    out += dfm[pos:]
    assert PAL.DFM(bytes(out)).get(BTN)["parent"] == "Panel2"
    return bytes(out)


def handler_block():
    b1 = OV.asm("mov dl, 0x1\njmp 0x4296a8", 0x4296A4)
    common = OV.asm(f"mov eax, dword ptr [eax + 0x22c]\njmp {SETBRUSH:#x}", 0x4296A8)
    b2 = OV.asm("mov dl, 0x2\njmp 0x4296a8", 0x4296B4)
    b3 = OV.asm(f"""
        mov ecx, edx
        mov dl, 0x3
        cmp ecx, dword ptr [eax + {F_BRUSH3:#x}]
        je 0x4296a8
        mov dl, {SIZE:#x}
        jmp 0x4296a8
    """, 0x4296C4)
    blk = bytearray(b"\x90" * (H_END - H_BLOCK))
    for va, c in ((0x4296A4, b1), (0x4296A8, common), (0x4296B4, b2), (0x4296C4, b3)):
        blk[va - H_BLOCK:va - H_BLOCK + len(c)] = c
    assert len(b1) <= 4 and 0x4296A8 + len(common) <= 0x4296B4 and len(b2) <= 0x10 and 0x4296C4 + len(b3) <= H_END
    return bytes(blk)


def devx_build(d):
    import pefile
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - 0x400000)  # noqa: E731
    rva, dfm = PAL.mainform_dfm(pe)
    cur = d[off(H_BLOCK):off(H_END)]
    blk = handler_block()
    if b"\x09Brush4Btn" in dfm:
        assert cur == blk
        return None
    assert cur == H_ORIG, cur.hex()
    out = AS.place_dfm(d, pe, rva, new_dfm(dfm))
    out[off(H_BLOCK):off(H_END)] = blk
    return bytes(out)


# ---- HSEPack ---------------------------------------------------------------------------------------------------
def hse_patches():
    P, at = [], HCAVE + len(HMAGIC)
    blob = bytearray(HMAGIC)
    for site, orig, base, dest, resume in HSITES:
        c = OV.asm(f"""
            mov al, byte ptr [{base} + 0x1ac]
            cmp al, 0x3
            jbe k
            mov al, 0x3
        k:
            mov {dest}, dword ptr [{base} + eax*4 + 0x1ac]
            jmp {resume:#x}
        """, at)
        P.append((site, bytes.fromhex(orig), b"\xe9" + struct.pack("<i", at - (site + 5)) + b"\x90" * 8))
        blob += c; at += len(c)
    assert HCAVE + len(blob) <= HCAVE_END
    P.append((HCAVE, bytes(len(blob)), bytes(blob)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    hd = open(HSE, "rb").read(); hpe = pefile.PE(data=hd)
    HP = hse_patches(); st, bad = SP.state(hd, hpe, HBASE, HP)
    print("HSEPack %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(HSE, HBASE, HP, True); print("reverted HSEPack")
        bk = bak_path(DEVX, TAG)
        if os.path.exists(bk):
            shutil.copy2(bk, DEVX); print("restored", bk, "(re-run later AoWDevX patches)")
        return 0
    d = open(DEVX, "rb").read()
    nd = devx_build(d)
    print("AoWDevX", "already applied" if nd is None else "Brush4Btn + handler block (%d -> %d B)" % (len(d), len(nd)))
    if nd is None and st[0] == "ours":
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(HSE, TAG)
        if not os.path.exists(bk):
            shutil.copy2(HSE, bk)
        SP.write_bytes(HSE, HBASE, HP, False)
    if nd is not None:
        bk = bak_path(DEVX, TAG)
        if not os.path.exists(bk):
            shutil.copy2(DEVX, bk)
        with open(DEVX, "wb") as fh:
            fh.write(nd)
        assert open(DEVX, "rb").read() == nd
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
