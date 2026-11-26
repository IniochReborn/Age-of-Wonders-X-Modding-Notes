#!/usr/bin/env python3
r"""
Sky polish + animated clouds + Clear Sky (2026-10-31).

User: "lets add some polish to the sky terrain. make it look nicer with subtle animation. also, the combat map for
sky seems to have a water animation background behind it... make it match the new animation were making for
overworld... lets also add a new type of sky terrain called 'Clear Sky', which should be more transparent and
simply have animated transparent clouds".

Clear Sky is terrain 0xE too (every Sky rule - flyers only, fly up/down, bridges, spell guards, combat - applies);
it is a separate set of tile resources (ResourceIDs 0x5A1B0001..4) that the random tile picker keeps apart.

1. AoWEPACK.dll  - sky overlay (sky_clouds_overlay_asm, zone 0x558CB000..0x558E3000 'SKY2'): the Ziggurat Firmament
   hook 0x55778A60 (jmp 0x558C0200) is re-aimed at the new routine (Ziggurat's surface cache 0x558C0900 reused).
   Every Sky/Clear hexagon on every level: drifting clouds (world-space, timeGetTime), Sky stars twinkle; on the
   Firmament the Surface shows through (Sky 19 %, Clear 62 %).  Unicorn-verified: test_sky_overlay_emu.py.
2. HSEPack.dpl   - Clear Sky brush + tile picker (cave 0x5561C900 'SKP1', flag byte DATA slack 0x5562E5F0):
     THSMEdit.SelectChangeTerrain 0x55613B9C / SelectClearTerrain 0x55613BBC: brush id 0x8E = Clear Sky ->
       flag 1 + id 0xE; any other brush -> flag 0.
     TMORTerrainControl.GetRndResource 0x5560E94C (terrain 0xE only): picks among the resources of the wanted
       class whose 'clear' bit (RID>>16 == 0x5A1B) equals the flag (falls back to vanilla if none).
     TMORTerrainControl.Place fallback pick 0x5560EB2C (new hexagon, no class) -> same filter.
   In the game the flag is always 0 -> random 0xE picks stay plain Sky.
3. AoWDevX.exe   - 'Clear Sky' buttons (Surface tab ClearSkyBtn, Underground tab uClearSkyBtn, free slot
   207,114 of both terrain panels) -> ClearSkyBtnClick 0x4EB600 (= SkyBtnClick with dl 0x8E); method table entry
   appended (0x4EC4C0 -> 0x4EC4D7); Sky button glyphs redrawn with the new art.  DFM grows -> .xprn grows.
4. Release.hss   - the 8 Sky tiles (rids 0x18..0x1F, palette page 11 cells 66-73) get the new art; 4 Clear Sky
   records appended (clones of rid 0x18, rids 0x5A1B0001..4, cells 74-77).
5. Images\SKYHEX00.ILB / SKYANM00.ILB (combat Sky hexagon): base tiles = new Sky tiles; the water-wave animation
   frames -> soft cloud wisps / a faint cloud veil (sky_clouds_art.combat_ilbs).

Order: after patch_firmament_sky_overlay_v1 (its hook is re-aimed), patch_devx_terrain_palette_v1,
build_sky_chasm_combat_v1, build_rndhex_previews_hss_v1 --sky, build_underground_structures_hss_v1.
⚠ re-running any of those (or their --revert) drops parts of this one -> re-run this afterwards.
Backups .bak_skypolish (AoWEPACK.dll, HSEPack.dpl, AoWDevX.exe, Release.hss, both ILBs).
Dry-run default; --apply; --revert.
"""
import io, os, shutil, struct, subprocess, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir, game_file  # noqa: E402
import sky_clouds_art as ART  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import patch_devx_terrain_palette_v1 as PAL  # noqa: E402

TAG = ".bak_skypolish"
EPK, EBASE = game_file("AoWEPACK.dll"), 0x55700000
HSE, HBASE = game_file("HSEPack.dpl"), 0x55600000
DEVX = game_file("AoWDevX.exe")
HSS = H.OURS
ILBS = [game_file(os.path.join("Images", "SKYHEX00.ILB")), game_file(os.path.join("Images", "SKYANM00.ILB"))]

# ---- HSEPack ------------------------------------------------------------------------------------------------------
HZONE, HZONE_END, HMAGIC = 0x5561C900, 0x5561CB00, b"SKP1"
FLAG = 0x5562E5F0
SCT, SCL = 0x55613B9C, 0x55613BBC
SC_ORIG = bytes.fromhex("8b88d8010000")
GRR, GRR_ORIG = 0x5560E94C, bytes.fromhex("5356575551")
PLF, PLF_LEN = 0x5560EB2C, 17
TLIST_GET, RANDOM = 0x556013EC, 0x55601068
CLEAR_HI = 0x5A1B
BRUSH_CLEAR = 0x8E


def hse_src():
    return f"""
    sct:
        mov ecx, dword ptr [eax + 0x1d8]
        call setflag
        jmp {SCT + 6:#x}
    scl:
        mov ecx, dword ptr [eax + 0x1d8]
        call setflag
        jmp {SCL + 6:#x}
    setflag:
        push ebx
        call sf1
    sf1:
        pop ebx
        sub ebx, sf1
        mov byte ptr [ebx + {FLAG:#x}], 0
        cmp dl, {BRUSH_CLEAR:#x}
        jne sf2
        mov byte ptr [ebx + {FLAG:#x}], 1
        mov dl, 0xe
    sf2:
        pop ebx
        ret

    grr:
        cmp edx, 0xe
        jne grr_orig
        push ebx
        push esi
        push edi
        push ebp
        push eax
        push ecx
        mov eax, dword ptr [eax + 0x10]
        call {TLIST_GET:#x}
        mov esi, eax
        call wantflag
        mov ebp, dword ptr [esp]
        mov edx, -1
        call scan
        test eax, eax
        je grr_fb
        call {RANDOM:#x}
        mov edx, eax
        call scan
        add esp, 8
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    grr_fb:
        pop ecx
        pop eax
        pop ebp
        pop edi
        pop esi
        pop ebx
        mov edx, 0xe
    grr_orig:
        push ebx
        push esi
        push edi
        push ebp
        push ecx
        jmp {GRR + 5:#x}

    pick:
        push ebx
        push esi
        push edi
        push ebp
        mov esi, eax
        cmp edx, 0xe
        jne pk_plain
        call wantflag
        mov ebp, -1
        mov edx, -1
        call scan
        test eax, eax
        je pk_plain
        call {RANDOM:#x}
        mov edx, eax
        call scan
        jmp pk_ret
    pk_plain:
        mov eax, dword ptr [esi + 8]
        call {RANDOM:#x}
        mov edx, dword ptr [esi + 4]
        mov eax, dword ptr [edx + eax*4]
    pk_ret:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret

    wantflag:
        call wf1
    wf1:
        pop ebx
        sub ebx, wf1
        movzx ebx, byte ptr [ebx + {FLAG:#x}]
        ret

    scan:
        push edi
        push edx
        push 0
        xor edi, edi
    sc_loop:
        cmp edi, dword ptr [esi + 8]
        jge sc_end
        mov eax, dword ptr [esi + 4]
        mov eax, dword ptr [eax + edi*4]
        push eax
        cmp ebp, -1
        je sc_cls
        mov eax, dword ptr [eax]
        call dword ptr [eax + 0x24]
        cmp eax, ebp
        jne sc_skip
    sc_cls:
        mov eax, dword ptr [esp]
        mov eax, dword ptr [eax + 0xc]
        shr eax, 16
        xor ecx, ecx
        cmp eax, {CLEAR_HI:#x}
        sete cl
        cmp ecx, ebx
        jne sc_skip
        mov eax, dword ptr [esp + 4]
        cmp eax, dword ptr [esp + 8]
        jne sc_inc
        pop eax
        add esp, 8
        pop edi
        ret
    sc_inc:
        inc dword ptr [esp + 4]
    sc_skip:
        add esp, 4
        inc edi
        jmp sc_loop
    sc_end:
        pop eax
        add esp, 4
        pop edi
        ret
    .long sct
    .long scl
    .long grr
    .long pick
"""


def hse_blob():
    code = OV.asm(hse_src(), HZONE + 0x10)
    ents = struct.unpack("<4I", code[-16:])
    code = code[:-16]
    assert 0x10 + len(code) <= HZONE_END - HZONE
    z = bytearray(HMAGIC) + bytes(12) + code
    return bytes(z), dict(zip(("sct", "scl", "grr", "pick"), ents))


def hse_patches(d, pe):
    z, e = hse_blob()
    off = lambda va: pe.get_offset_from_rva(va - HBASE)  # noqa: E731
    jmp = lambda at, to, n: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (n - 5)  # noqa: E731
    plf_new = (b"\x8b\xc6" + b"\x0f\xbe\x55\x08" + b"\xe8" + struct.pack("<i", e["pick"] - (PLF + 6 + 5)) +
               b"\x89\x45\xf0" + b"\x90" * 3)
    assert len(plf_new) == PLF_LEN
    vanilla_plf = bytes.fromhex("8b4608e8") + struct.pack("<i", RANDOM - (PLF + 8)) + bytes.fromhex("8b56048b04828945f0")
    return [(SCT, SC_ORIG, jmp(SCT, e["sct"], 6)), (SCL, SC_ORIG, jmp(SCL, e["scl"], 6)),
            (GRR, GRR_ORIG, jmp(GRR, e["grr"], 5)), (PLF, vanilla_plf, plf_new),
            (HZONE, bytes(len(z)), z)]


# ---- AoWEPACK ------------------------------------------------------------------------------------------------------
def epk_patches():
    z = OV.blob()
    old = b"\xe9" + struct.pack("<i", OV.HOOK_ZIG - (OV.HOOK + 5)) + b"\x90"
    new = b"\xe9" + struct.pack("<i", OV.ZONE + 0x10 - (OV.HOOK + 5)) + b"\x90"
    return [(OV.HOOK, old, new), (OV.ZONE, bytes(len(z)), z)]


# ---- byte-patch helpers ---------------------------------------------------------------------------------------------
def state(d, pe, base, P):
    off = lambda va: pe.get_offset_from_rva(va - base)  # noqa: E731
    st = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        st.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    rl = {base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    return st, bad


def write_bytes(path, base, P, revert):
    import pefile
    pe = pefile.PE(data=open(path, "rb").read(), fast_load=True)
    off = lambda va: pe.get_offset_from_rva(va - base)  # noqa: E731
    with open(path, "r+b") as f:
        for s, o, n in P:
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(path, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)


# ---- AoWDevX -------------------------------------------------------------------------------------------------------
STUB_VA, STUB_SRC, STUB_LEN = 0x4EB600, 0x4EB5A0, 0x2C
MT_VA, MT_END, MT_LIMIT, MT_N = 0x4EB800, 0x4EC4C0, 0x4EC500, 136
NEWBTN = [("ToolbarPnl", "SkyBtn", "ClearSkyBtn"), ("Panel10", "uSkyBtn", "uClearSkyBtn")]
HANDLER = "ClearSkyBtnClick"


def glyph(kind):
    """48x32 24-bit BMP (grey 192 background) of a Sky / Clear Sky hex with a few clouds baked in"""
    from PIL import Image
    tile = (ART.sky_tiles()[1] if kind == 0 else ART.clear_tiles()[0])
    tex, L = ART.cloud_tex(), ART.luts()
    img = Image.new("RGB", (48, 32), (192, 192, 192))
    px = img.load()
    lut = L["clear" if kind else "sky"]
    best = None
    for oy in range(0, 256, 16):                      # the texture window with ~1/4 cloud cover
        for ox in range(0, 256, 16):
            cov = sum(lut[(int(tex[(r + oy) & 255, (x + ox) & 255]) + int(tex[((r + oy) >> 1) & 255,
                      ((x + ox) >> 1) & 255])) >> 1] for r, (s, e) in enumerate(ART.SPANS) for x in range(s, e, 3))
            cov /= ART.NPIX / 3 * 255
            if best is None or abs(cov - 0.22) < best[0]:
                best = (abs(cov - 0.22), ox, oy)
    _, ox, oy = best
    for r, (s, e) in enumerate(ART.SPANS):
        for x in range(s, e):
            q = tile[r, x]
            p = ((int(q[0]) >> 3) << 11) | ((int(q[1]) >> 2) << 5) | (int(q[2]) >> 3)
            o = ART.model_pixel(p, kind, 0, x + ox, r + oy, 0, tex, L)
            px[x, r] = (((o >> 11) & 31) << 3, ((o >> 5) & 63) << 2, (o & 31) << 3)
    b = io.BytesIO(); img.save(b, "BMP")
    bmp = b.getvalue()
    assert len(bmp) == 4662
    return struct.pack("<I", len(bmp)) + bmp


def props(raw, c):
    D = PAL.DFM(raw)
    D.p = c["start"]
    if raw[D.p] & 0xF0 == 0xF0:
        D.p += 1
    D.rs(); D.rs()
    out = []
    while raw[D.p]:
        k = D.rs(); st = D.p; D.val()
        out.append((k.decode(), raw[st:D.p]))
    return out


def ser_comp(cls, name, plist):
    out = bytearray([len(cls)]) + cls + bytes([len(name)]) + name.encode()
    for k, v in plist:
        out += bytes([len(k)]) + k.encode() + v
    return bytes(out) + b"\x00\x00"


def vstr(s):
    return b"\x06" + bytes([len(s)]) + s.encode("latin1")


def vbin(b):
    return b"\x0a" + struct.pack("<I", len(b)) + b


def new_dfm(dfm):
    D = PAL.DFM(dfm)
    gsky, gclr = glyph(0), glyph(1)
    edits = []   # (start, end, replacement)
    for panel, src, name in NEWBTN:
        c = D.get(src)
        pl = props(dfm, c)
        keys = [k for k, _ in pl]
        assert keys == ["Left", "Top", "Width", "Height", "Hint", "AllowAllUp", "GroupIndex", "Flat", "Glyph.Data",
                        "OnClick"], keys
        newsrc = ser_comp(c["cls"], src, [(k, vbin(gsky) if k == "Glyph.Data" else v) for k, v in pl])
        assert len(newsrc) == c["end"] - c["start"], (len(newsrc), c["end"] - c["start"])
        edits.append((c["start"], c["end"], newsrc))
        rep = {"Left": b"\x03" + struct.pack("<h", 207), "Top": b"\x02" + bytes([114]),
               "Hint": vstr("Clear Sky (flying/floating only)"), "Glyph.Data": vbin(gclr), "OnClick": b"\x07" +
               bytes([len(HANDLER)]) + HANDLER.encode()}
        btn = ser_comp(c["cls"], name, [(k, rep.get(k, v)) for k, v in pl])
        p = D.get(panel)
        assert all(D.raw[k["end"] - 1] == 0 for k in p["kids"])
        edits.append((p["end"] - 1, p["end"] - 1, btn))   # before the panel's children terminator
    out = bytearray(); pos = 0
    for s, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
        out += dfm[pos:s] + b; pos = e
    out += dfm[pos:]
    N = PAL.DFM(bytes(out))
    for panel, src, name in NEWBTN:
        assert N.get(name)["parent"] == panel
    return bytes(out)


def devx_build(d):
    import pefile
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - 0x400000)  # noqa: E731
    rva, dfm = PAL.mainform_dfm(pe)
    if b"\x0bClearSkyBtn" in dfm:
        return None, "ours"
    assert b"\x06SkyBtn" in dfm, "patch_devx_terrain_palette_v1 not applied"
    nd = new_dfm(dfm)
    stub = bytearray(d[off(STUB_SRC):off(STUB_SRC) + STUB_LEN])
    assert stub[0x10] == 0x0E and stub[0x1E] == 0x0E and stub[0x17] == 0xE8 and stub[0x25] == 0xE8, stub.hex()
    stub[0x10] = stub[0x1E] = BRUSH_CLEAR
    for at in (0x17, 0x25):
        tgt = STUB_SRC + at + 5 + struct.unpack_from("<i", stub, at + 1)[0]
        struct.pack_into("<i", stub, at + 1, tgt - (STUB_VA + at + 5))
    assert not any(d[off(STUB_VA):off(STUB_VA) + STUB_LEN])
    n = struct.unpack_from("<H", d, off(MT_VA))[0]
    assert n == MT_N and struct.unpack_from("<I", d, off(PAL.VMT - 0x28))[0] == MT_VA, n
    ent = struct.pack("<HI", 7 + len(HANDLER), STUB_VA) + bytes([len(HANDLER)]) + HANDLER.encode()
    assert not any(d[off(MT_END):off(MT_LIMIT)]) and MT_END + len(ent) <= MT_LIMIT
    secs = pe.sections
    last = max(secs, key=lambda s: s.PointerToRawData)
    assert last.Name.rstrip(b"\0") == b".xprn" and last.PointerToRawData + last.SizeOfRawData == len(d)
    dfm_fo = pe.get_offset_from_rva(rva)
    assert not any(d[dfm_fo + len(dfm):]), "data after the DFM in .xprn"
    end = dfm_fo + len(nd)
    new_raw = max(last.SizeOfRawData, ((end - last.PointerToRawData) + PAL.ALIGN - 1) // PAL.ALIGN * PAL.ALIGN)
    new_vs = max(new_raw, last.Misc_VirtualSize)
    sa = pe.OPTIONAL_HEADER.SectionAlignment
    soi = max(pe.OPTIONAL_HEADER.SizeOfImage, (last.VirtualAddress + new_vs + sa - 1) // sa * sa)
    out = bytearray(d[:dfm_fo]) + nd
    out += bytes(last.PointerToRawData + new_raw - len(out))
    sh = last.get_file_offset()
    struct.pack_into("<I", out, sh + 8, new_vs)
    struct.pack_into("<I", out, sh + 16, new_raw)
    struct.pack_into("<I", out, pe.OPTIONAL_HEADER.get_file_offset() + 56, soi)
    assert struct.unpack_from("<I", out, PAL.RES_ENTRY_FO)[0] == rva
    struct.pack_into("<I", out, PAL.RES_ENTRY_FO + 4, len(nd))
    out[off(STUB_VA):off(STUB_VA) + STUB_LEN] = stub
    out[off(MT_END):off(MT_END) + len(ent)] = ent
    struct.pack_into("<H", out, off(MT_VA), n + 1)
    info = "DFM %d -> %d B, .xprn raw %#x -> %#x, SizeOfImage %#x" % (len(dfm), len(nd), last.SizeOfRawData,
                                                                       new_raw, soi)
    return bytes(out), info


# ---- Release.hss ---------------------------------------------------------------------------------------------------
SKY_RIDS = list(range(0x18, 0x20))
CLEAR = [(0x5A1B0001 + k, 74 + k) for k in range(4)]


def tile_ilb(rec, rgba):
    from PIL import Image
    from aowxlib import ilb
    s, e = H.emb_span(rec)
    assert e == len(rec)
    lib = ilb.read(bytes(rec[s:e]))
    assert len(lib.images) == 1
    ilb.encode_image(lib, lib.images[0].primary, Image.fromarray(rgba, "RGBA"))
    w, h, rows = ilb.decode_record(lib, lib.images[0].primary)
    got = [[ilb.to_rgb565(*p[:3]) if p and p[3] else None for p in row] for row in rows]
    want = [[ilb.to_rgb565(*(int(v) for v in rgba[y, x, :3])) if rgba[y, x, 3] else None for x in range(48)]
            for y in range(32)]
    assert got == want, "tile did not round-trip"
    return bytes(rec[:s]) + ilb.write(lib)


def rid(r):
    return H.u32(r, 1)


def hss_rebuild(b, A):
    region = bytearray(); offs = {}
    for cid in A["order"]:
        offs[cid] = len(region); region += A["recs"][cid]
    for e in A["ce"]:
        e[1] = offs[e[0]]
    ct = H.enc_table(A["ce"])
    shift_tbl = len(ct) - (A["cbase"] - A["ctp"])
    growth = len(region) - (A["region_end"] - A["cbase"]) + shift_tbl
    nb = bytearray(b[:A["ctp"]] + ct + region + b[A["region_end"]:-4])
    root = A["root"]
    for x in root:
        if x[1] > A["f5"]:
            x[1] += growth
    rt = H.enc_table(root); assert len(rt) == A["rds"] - 0x37
    nb[0x37:A["rds"]] = rt
    if shift_tbl:
        oe, ods = H.table(nb, A["rds"] + A["f5"])
        first = [e for e in oe if e[0] == 1][0][1]
        for x in oe:
            if x[1] > first:
                x[1] += shift_tbl
        ot = H.enc_table(oe)
        st = A["rds"] + A["f5"]
        assert len(ot) == ods - st
        nb[st:ods] = ot
    nb += struct.pack("<I", zlib.crc32(bytes(nb)) & 0xFFFFFFFF)
    return bytes(nb)


def hss_build(b):
    A = H.parse(b)
    byrid = {rid(r): c for c, r in A["recs"].items()}
    sky, clr = ART.sky_tiles(), ART.clear_tiles()
    want_sky = {}
    for k, r_ in enumerate(SKY_RIDS):
        c = byrid[r_]
        r = A["recs"][c]
        assert struct.unpack_from("<I", r, 0)[0] == 0x20153 and H.terr(r) == b"\x0e\xfe" and H.u32(r, 2) == 11
        want_sky[c] = tile_ilb(r, sky[k])
    tpl = A["recs"][byrid[SKY_RIDS[0]]]
    cells = {H.u32(r, 3) for r in A["recs"].values() if H.u32(r, 2) == 11}
    new = []
    for k, (nr, cell) in enumerate(CLEAR):
        r = bytearray(tile_ilb(tpl, clr[k]))
        fo, td = H.fields(r)
        struct.pack_into("<I", r, td + fo[1], nr)
        struct.pack_into("<I", r, td + fo[3], cell)
        new.append(bytes(r))
    have_clear = [nr in byrid for nr, _ in CLEAR]
    sky_done = all(bytes(A["recs"][c]) == v for c, v in want_sky.items())
    if all(have_clear) and sky_done:
        return None
    assert not any(have_clear), "partial Clear Sky records"
    assert not any(cell in cells for _, cell in CLEAR), "palette cells 74-77 taken"
    for c, v in want_sky.items():
        A["recs"][c] = bytearray(v)
    nxt = max(A["recs"]) + 1
    for k, rec in enumerate(new):
        A["recs"][nxt + k] = bytearray(rec)
        A["order"].append(nxt + k)
        A["ce"].append([nxt + k, 0, "d"])
    nb = hss_rebuild(b, A)
    N = H.parse(nb)
    for k, rec in enumerate(new):
        assert bytes(N["recs"][nxt + k]) == rec
    for c, v in want_sky.items():
        assert bytes(N["recs"][c]) == v
    old = H.parse(b)["recs"]
    assert all(bytes(N["recs"][c]) == bytes(v) for c, v in old.items() if c not in want_sky)
    return nb


# ---- main ----------------------------------------------------------------------------------------------------------
def busy():
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    return "AoWx.exe" in r or "AoWDevX.exe" in r


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if busy():
            print("game/editor running - close it first"); return 1
        for f in [EPK, HSE, DEVX, HSS] + ILBS:
            b = bak_path(f, TAG)
            if os.path.exists(b):
                shutil.copy2(b, f); print("restored", b)
        return 0
    report, todo = [], []
    # AoWEPACK
    d = open(EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = state(d, pe, EBASE, P)
    report.append("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("\n".join(report)); print("ABORT (AoWEPACK)"); return 1
    if st[0] == "vanilla":
        todo.append(("epk", P))
    # HSEPack
    d = open(HSE, "rb").read(); pe = pefile.PE(data=d)
    P = hse_patches(d, pe); st, bad = state(d, pe, HBASE, P)
    foff = pe.get_offset_from_rva(FLAG - HBASE)
    report.append("HSEPack %s relocs %s flag byte %s" % (st, bad or "none", d[foff:foff + 16].hex()))
    if "OTHER" in st or bad or len(set(st)) != 1 or any(d[foff:foff + 16]):
        print("\n".join(report)); print("ABORT (HSEPack)"); return 1
    if st[0] == "vanilla":
        todo.append(("hse", P))
    # AoWDevX
    d = open(DEVX, "rb").read()
    nd, info = devx_build(d)
    report.append("AoWDevX %s" % ("already applied" if nd is None else info))
    if nd is not None:
        todo.append(("devx", nd))
    # Release.hss
    b = open(HSS, "rb").read()
    nb = hss_build(b)
    report.append("Release.hss %s" % ("already applied" if nb is None else "%d -> %d B" % (len(b), len(nb))))
    if nb is not None:
        todo.append(("hss", nb))
    # combat ILBs
    blobs = ART.combat_ilbs(game_dir())
    for f in ILBS:
        nm = "Images\\" + os.path.basename(f)
        same = open(f, "rb").read() == blobs[nm]
        report.append("%s %s" % (nm, "already applied" if same else "rebuild (%d B)" % len(blobs[nm])))
        if not same:
            todo.append(("ilb", (f, blobs[nm])))
    print("\n".join(report))
    if not todo:
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if busy():
        print("game/editor running - close it first"); return 1
    for kind, x in todo:
        f = {"epk": EPK, "hse": HSE, "devx": DEVX, "hss": HSS}.get(kind) or x[0]
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        if kind == "epk":
            write_bytes(EPK, EBASE, x, False)
        elif kind == "hse":
            write_bytes(HSE, HBASE, x, False)
        else:
            data = x if kind in ("devx", "hss") else x[1]
            with open(f, "r+b") as fh:
                fh.write(data); fh.truncate()
            assert open(f, "rb").read() == data
        print("written", f)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
