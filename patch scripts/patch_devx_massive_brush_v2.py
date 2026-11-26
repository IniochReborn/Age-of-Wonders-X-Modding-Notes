#!/usr/bin/env python3
r"""
Massive brush v2 (2026-10-31) - on top of patch_devx_massive_brush_v1.

User: "the large brush icon briefly appears solid, then is greyed out (but the outline is too different from the
others, make more similar) ... also do the brush preview" (preview must show the full 13 hexes).
  1. AoWDevX DFM Brush4Btn: Enabled = False (like the other brushes; patch_devx_autosave v1.3 enables it with
     Brush3Btn) + disabled glyph half redrawn in Brush3's exact style (ring (130,130,146), highlight (225,225,225)
     one pixel down-right).
  2. HSEPack: the brush cursor images live in the HSEditModule data module (RCDATA THSEDITMODULE) as THSLibrary
     'HSBrushes' (old v2.0 ILB, hsbrush_ilb.py): images 0/1/2 = 1/3/5-hex outline clusters (3 = Multihex, 4 Army,
     5 MapBag).  New image 6 = the 13-hex cluster, grown ring by ring from image 1 by stamping it at the centre +
     the 6 neighbour offsets (0,+-32) (+-33,+-16) - that exact rule reproduces image 2 from image 1 pixel for pixel.
     The rebuilt DFM goes into a new section '.xbr' and the resource data entry is repointed.
  3. HSEPack code (caves 0x5561CD00 'MBR2', PIC via call/pop; 4th object kept at DATA-page slack G4):
       THSMEdit.Activate 0x556154D6: after the 1..3 loop, G4 = THSLibrary.CreateHS(lib = [HSEditModule]+0x48, 6)
         when still 0;
       the four cursor lookups (v1 sites, now MBR2): size 7 -> G4 (falls back to the large cursor if G4 is 0);
       THSMEdit.DeActivate 0x556155D1: after the free loop, Free(G4), G4 = 0.
Backups .bak_massbrush2 (AoWDevX.exe whole file, HSEPack.dpl whole file).  Dry-run default; --apply; --revert.
"""
import io, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_devx_terrain_palette_v1 as PAL  # noqa: E402
import patch_devx_autosave_v1 as AS  # noqa: E402
import patch_devx_massive_brush_v1 as M1  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import hsbrush_ilb as HB  # noqa: E402

TAG = ".bak_massbrush2"
DEVX, HSE, HBASE = M1.DEVX, M1.HSE, M1.HBASE
RES_RVA, RES_SIZE, RES_ENTRY_FO = 0x487D8, 18337, 0x42DF0
NEW_ID, RADIUS = 6, 6
G4 = 0x5562E700                      # DATA page slack (section VS 0x550; page mapped to 0x5562F000)
LIBVAR = 0x5562E304                  # -> HSEdMod.HSEditModule variable
CREATEHS, TFREE = 0x55611878, 0x556010A0
CAVE, CAVE_END, MAGIC = 0x5561CD00, 0x5561CF00, b"MBR2"
ACT, ACT_ORIG, ACT_BACK = 0x556154D6, bytes.fromhex("c683bc01000001"), 0x556154DD
DEA, DEA_ORIG, DEA_LOOP, DEA_BACK = 0x556155D1, bytes.fromhex("83fe0475e1"), 0x556155B7, 0x556155D6


# ---- AoWDevX glyph / Enabled -----------------------------------------------------------------------------------
def glyph(src_gdata):
    from PIL import Image, ImageDraw
    n = struct.unpack_from("<I", src_gdata, 0)[0]
    bg = Image.open(io.BytesIO(src_gdata[4:4 + n])).convert("RGB").getpixel((0, 31))
    out = Image.new("RGB", (64, 32), bg)
    d = ImageDraw.Draw(out)
    d.ellipse([2, 2, 29, 29], fill=(0, 0, 0))
    d.ellipse([35, 3, 62, 30], outline=(225, 225, 225))
    d.ellipse([34, 2, 61, 29], outline=(130, 130, 146))
    b = io.BytesIO(); out.save(b, "BMP"); bmp = b.getvalue()
    assert len(bmp) == n
    return struct.pack("<I", len(bmp)) + bmp


def devx_build(d):
    import pefile
    pe = pefile.PE(data=d)
    rva, dfm = PAL.mainform_dfm(pe)
    D = PAL.DFM(dfm)
    c = D.get("Brush4Btn")
    pl = SP.props(dfm, c)
    if any(k == "Enabled" for k, _ in pl):
        return None
    g3 = dict(SP.props(dfm, D.get("Brush3Btn")))["Glyph.Data"][5:]
    new = []
    for k, v in pl:
        if k == "Glyph.Data":
            v = SP.vbin(glyph(g3))
        if k == "Flat":
            new.append(("Enabled", b"\x08"))
        new.append((k, v))
    comp = SP.ser_comp(c["cls"], c["name"], new)
    nd = dfm[:c["start"]] + comp + dfm[c["end"]:]
    assert PAL.DFM(nd).get("Brush4Btn")["parent"] == "Panel2"
    return bytes(AS.place_dfm(d, pe, rva, nd))


# ---- HSEPack resource ------------------------------------------------------------------------------------------
def grow(px):
    h, w = len(px), len(px[0])
    W, H = w + 66, h + 64
    out = [[None] * W for _ in range(H)]
    for dx, dy in ((0, 0), (0, -32), (0, 32), (-33, -16), (33, -16), (-33, 16), (33, 16)):
        ox, oy = 33 + dx, 32 + dy
        for y, row in enumerate(px):
            for x, v in enumerate(row):
                if v:
                    out[oy + y][ox + x] = v
    return out


def new_brushes(data):
    hdr, imgs, tail = HB.parse(data)
    assert hdr + b"".join(i["raw"] for i in imgs) + tail == data
    if any(i["id"] == NEW_ID for i in imgs):
        return None
    p1, p2 = HB.decode(imgs[1]), HB.decode(imgs[2])
    assert grow(p1) == p2, "grow rule does not reproduce image 2"
    px = p1
    for _ in range(RADIUS - 1):
        px = grow(px)
    rec = HB.build_image(NEW_ID, b"Brushes.bmp", px, imgs[2])
    return hdr + b"".join(i["raw"] for i in imgs) + rec + tail


def hse_resource(d):
    import pefile
    pe = pefile.PE(data=d)
    ent = struct.unpack_from("<II", d, RES_ENTRY_FO)
    if ent[0] != RES_RVA:
        return None, None
    assert ent[1] == RES_SIZE
    dfm = pe.get_data(RES_RVA, RES_SIZE)
    D = PAL.DFM(dfm)
    c = D.get("HSBrushes")
    pl = SP.props(dfm, c)
    data = dict(pl)["Data"][5:]
    nb = new_brushes(data)
    comp = SP.ser_comp(c["cls"], c["name"], [(k, (b"\x0a" + struct.pack("<I", len(nb)) + nb) if k == "Data" else v)
                                              for k, v in pl])
    nd = dfm[:c["start"]] + comp + dfm[c["end"]:]
    PAL.DFM(nd)
    return nd, pe


def add_section(d, pe, payload, name=b".xbr"):
    out = bytearray(d)
    fa, sa = pe.OPTIONAL_HEADER.FileAlignment, pe.OPTIONAL_HEADER.SectionAlignment
    last = pe.sections[-1]
    assert last.PointerToRawData + last.SizeOfRawData == len(d), "overlay after the last section"
    hdr_off = last.get_file_offset() + 40
    assert hdr_off + 40 <= pe.OPTIONAL_HEADER.SizeOfHeaders and not any(d[hdr_off:hdr_off + 40])
    va = (last.VirtualAddress + max(last.Misc_VirtualSize, last.SizeOfRawData) + sa - 1) // sa * sa
    raw = (len(payload) + fa - 1) // fa * fa
    sh = name.ljust(8, b"\0") + struct.pack("<IIII", len(payload), va, raw, len(d)) + bytes(12) + \
        struct.pack("<I", 0x40000040)
    out[hdr_off:hdr_off + 40] = sh
    nso = pe.FILE_HEADER.get_file_offset() + 2
    struct.pack_into("<H", out, nso, pe.FILE_HEADER.NumberOfSections + 1)
    soi = (va + len(payload) + sa - 1) // sa * sa
    struct.pack_into("<I", out, pe.OPTIONAL_HEADER.get_file_offset() + 56, soi)
    out += payload + bytes(raw - len(payload))
    return out, va


# ---- HSEPack code ----------------------------------------------------------------------------------------------
def pic_asm(src_fn, at):
    """src_fn(deltas) -> asm; every `call Lk / Lk: pop ecx / add ecx, Dk` anchor gets Dk = target - Lk (2 passes)"""
    probe = OV.asm(src_fn(None), at)
    pops = [at + i for i in range(len(probe) - 3) if probe[i] == 0x59 and probe[i + 1:i + 3] == b"\x81\xc1"]
    code = OV.asm(src_fn(pops), at)
    assert len(code) == len(probe)
    return code


def hse_patches():
    P, at = [], CAVE + len(MAGIC)
    blob = bytearray(MAGIC)

    def add(fn):
        nonlocal at, blob
        c = pic_asm(fn, at)
        st = at
        blob += c; at += len(c)
        return st

    def D(pops, k, target):
        return 0x11111111 if pops is None else (target - pops[k]) & 0xFFFFFFFF

    for site, orig, base, dest, resume in M1.HSITES:
        def fn(pops, base=base, dest=dest, resume=resume):
            return f"""
                mov al, byte ptr [{base} + 0x1ac]
                cmp al, 0x7
                jne tbl
                push ecx
                call l0
            l0:
                pop ecx
                add ecx, {D(pops, 0, G4):#x}
                mov {dest}, dword ptr [ecx]
                pop ecx
                test {dest}, {dest}
                jnz done
                mov al, 0x3
            tbl:
                cmp al, 0x3
                jbe ok
                mov al, 0x3
            ok:
                mov {dest}, dword ptr [{base} + eax*4 + 0x1ac]
            done:
                jmp {resume:#x}
            """
        e = add(fn)
        P.append((site, b"", b"\xe9" + struct.pack("<i", e - (site + 5)) + b"\x90" * 8))

    def fact(pops):
        return f"""
            push ecx
            call l0
        l0:
            pop ecx
            add ecx, {D(pops, 0, G4):#x}
            cmp dword ptr [ecx], 0x0
            jne a_done
            push ecx
            call l1
        l1:
            pop ecx
            add ecx, {D(pops, 1, LIBVAR):#x}
            mov eax, dword ptr [ecx]
            mov eax, dword ptr [eax]
            mov eax, dword ptr [eax + 0x48]
            mov edx, {NEW_ID:#x}
            call {CREATEHS:#x}
            pop ecx
            mov dword ptr [ecx], eax
        a_done:
            pop ecx
            mov byte ptr [ebx + 0x1bc], 0x1
            jmp {ACT_BACK:#x}
        """
    ea = add(fact)
    P.append((ACT, ACT_ORIG, b"\xe9" + struct.pack("<i", ea - (ACT + 5)) + b"\x90\x90"))

    def fdea(pops):
        return f"""
            cmp esi, 0x4
            jne {DEA_LOOP:#x}
            push ecx
            call l0
        l0:
            pop ecx
            add ecx, {D(pops, 0, G4):#x}
            mov eax, dword ptr [ecx]
            test eax, eax
            jz d_done
            mov dword ptr [ecx], 0x0
            call {TFREE:#x}
        d_done:
            pop ecx
            jmp {DEA_BACK:#x}
        """
    ed = add(fdea)
    P.append((DEA, DEA_ORIG, b"\xe9" + struct.pack("<i", ed - (DEA + 5))))
    assert CAVE + len(blob) <= CAVE_END, hex(len(blob))
    P.append((CAVE, bytes(len(blob)), bytes(blob)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    bk_d, bk_h = bak_path(DEVX, TAG), bak_path(HSE, TAG)
    if revert:
        for f, bk in ((DEVX, bk_d), (HSE, bk_h)):
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        return 0
    d = open(DEVX, "rb").read()
    nd = devx_build(d)
    h = open(HSE, "rb").read(); hpe = pefile.PE(data=h)
    P = hse_patches()
    off = lambda va: hpe.get_offset_from_rva(va - HBASE)  # noqa: E731
    # site original bytes = what v1 left there (jmp MBR1)
    v1 = {s: n for s, o, n in M1.hse_patches()}
    P = [(s, (v1[s] if o == b"" else o), n) for s, o, n in P]
    st, bad = SP.state(h, hpe, HBASE, P)
    print("AoWDevX", "already applied" if nd is None else "Brush4Btn Enabled=False + glyph")
    print("HSEPack code %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad:
        print("ABORT"); return 1
    res, _ = hse_resource(h)
    print("HSEPack resource", "already applied" if res is None else "THSEDITMODULE %d -> %d B (+ image %d, 13 hexes)"
          % (RES_SIZE, len(res), NEW_ID))
    if nd is None and res is None and all(s == "ours" for s in st):
        return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if nd is not None:
        if not os.path.exists(bk_d):
            shutil.copy2(DEVX, bk_d)
        with open(DEVX, "wb") as fh:
            fh.write(nd)
    if not os.path.exists(bk_h):
        shutil.copy2(HSE, bk_h)
    out = bytearray(h)
    for s, o, n in P:
        if h[off(s):off(s) + len(n)] != n:
            out[off(s):off(s) + len(n)] = n
    if res is not None:
        out, va = add_section(bytes(out), pefile.PE(data=bytes(out)), res)
        struct.pack_into("<II", out, RES_ENTRY_FO, va, len(res))
    with open(HSE, "wb") as fh:
        fh.write(out)
    chk = pefile.PE(data=bytes(out))
    rva, size = struct.unpack_from("<II", out, RES_ENTRY_FO)
    PAL.DFM(chk.get_data(rva, size))
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
