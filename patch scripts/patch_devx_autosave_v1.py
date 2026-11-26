#!/usr/bin/env python3
r"""
AoWDevX: toggleable map autosave (2026-10-31).

User: "add a togglable autosave to the editor. it should only apply to hsm/csm maps, never mapsets/rulesets or
anything. it should be a button on the top bar, next to the save icon (push everything else to the right to make
room). it should be able to "press in" like the select object and select eraser button. the icon should be similar
to normal save icon (floppy disc) except with an small hourglass on the bottom right corner of it... in the Options
tab at the top, add a new option called "Autosave Timer" with intervals of 2 minutes, 5 minutes, 10 minutes,
20 minutes, 30 minutes, 1 hour ... the autosaves should alternate between "autosave - [file name].hsm" and
"autosave2 - [file name].hsm"".

  * TMAINFORM DFM (relocated in .xprn @RVA 0xED000): new TSpeedButton 'AutoSaveBtn' in Panel2 right after SaveBtn
    (x 84), SaveBtn's glyph + a small hourglass in the bottom-right of both glyph halves, AllowAllUp + its own
    GroupIndex (GROUP) = a press-in toggle, no OnClick; every Panel2 button right of it moves 40 px right.
  * FormCreate (published method-table entry, table 0x4EB800) -> wrapper (zone .xprn ZONE): original FormCreate,
    then finds AutoSaveBtn in Form.Components, reads General\"Editor Autosave Interval" (index 0..5; default 1 =
    5 minutes) through AoWEPACK TAoWRegistry.rwString (delta via the GetLanguage import, as the theme patch),
    builds Options > Autosave Timer > 2 minutes .. 1 hour (radio items; click = store + registry write), and
    creates a TTimer (10 s, imported ExtCtrls.TTimer).
  * Tick: button Down ([btn+0xC0]) + a map open in the map editor (HSMEdit = form+0x22C, [+0x1BC] loaded, map
    [+0x1C0], file name [+0x1E4] with a folder - "noname.hsm" never autosaves) -> +10 s; at the interval: build
    "<folder>\autosave - <name>" / "autosave2 - <name>" (alternating; original extension .hsm/.csm kept) and call
    the map's own SaveToFile (map VMT+0xAC, exactly what THSMEdit.Save does, with its progress callback) - the
    HSMEdit file name and the map's modified flag ([[map+0x3C]+0x3C] bit 0, cleared only by THSMEdit.Save) are
    NOT touched, so the real file still asks to be saved.  Mapsets/rulesets (THSSEdit) are never involved.
v1.1 (user: "when a mapset is open (release.hss), the autosave icon should be greyed out/inoperable ... when the
autosave occurs, it should not grey out the normal save"): the timer ticks every 1 s and enables the button only while
a map is loaded (TControl.FEnabled +0x45, SetEnabled thunk 0x401550; disabling also pops it out via SetDown 0x402318;
starts disabled); SaveToFile clears the map's modified bit [[map+0x3C]+0x3C] bit 0, which is what enables SaveBtn
(TMainForm.HSMEditUpdateFrame 0x428D7E) and the close prompt -> saved before / OR-ed back after the autosave.
Zones: code .xprn 0x4ECC00..0x4ED000 (tail of patch_devx_text_limits_v1's declared zone, unused), data .xitm
0x4E5240..0x4E5400.  Backup .bak_autosave (whole exe; --revert restores it - re-run later AoWDevX patches after).
Dry-run default; --apply; --revert.
"""
import io, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_devx_terrain_palette_v1 as PAL  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

EXE = game_file("AoWDevX.exe")
TAG = ".bak_autosave"
ZONE, ZONE_END = 0x4ECC00, 0x4ECFC0          # 0x4ECFC0..0x4ED000 = patch_teleport_firmament_v1 (editor caves)
DATA, DATA_END = 0x4E5240, 0x4E5400
MT = 0x4EB800
FORMCREATE = 0x42841C
GROUP = 0x4D
BTN = "AutoSaveBtn"
HINT = "Autosave (toggle) - interval: Options > Autosave Timer"
SHIFT = 40
CAPTIONS = ["2 minutes", "5 minutes", "10 minutes", "20 minutes", "30 minutes", "1 hour"]
MINUTES = [2, 5, 10, 20, 30, 60]
# imports / helpers (AoWDevX)
IAT = dict(mi_create=0x4324AC, mi_add=0x432490, mi_caption=0x4324A8, mi_checked=0x4324A4, mi_radio=0x43248C,
           mi_class=0x4324BC, tm_class=0x432684, tm_create=0x432678, tm_interval=0x432670, tm_ontimer=0x43266C,
           getlang=0x432E64, hsmsave=0x433360)
LSTRCLR = 0x4010B0
EP_GETLANG, EP_ENGINE, EP_RWSTRING = 0x55704B6C, 0x558FA048, 0x55703D08
HSE_SAVE, HSE_SAVECB = 0x55614ED0, 0x5561509C


# ---- data block ------------------------------------------------------------------------------------------------
def astr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_data():
    v = {}
    blob = bytearray(0x40)                     # state: 0 form, 4 btn, 8 minutes, 0xC elapsed, 0x10 toggle,
    G = dict(form=0, btn=4, mins=8, elap=0xC, tog=0x10, epd=0x14, idx=0x18, wslot=0x1C, sub=0x20, tmp=0x24)

    def add_str(key, s):
        while len(blob) % 4:
            blob.append(0)
        v[key] = DATA + len(blob) + 8           # chars pointer
        blob.extend(astr(s))
    add_str("title", "Autosave Timer")
    for i, c in enumerate(CAPTIONS):
        add_str("cap%d" % i, c)
    add_str("general", "General")
    add_str("valname", "Editor Autosave Interval")
    add_str("btnname", BTN)
    add_str("auto1", "autosave - ")
    add_str("auto2", "autosave2 - ")
    add_str("dig", "0")                        # writable 1-char value string (digit set before each write)
    while len(blob) % 4:
        blob.append(0)
    v["mintab"] = DATA + len(blob)
    blob.extend(struct.pack("<6I", *MINUTES))
    v["captab"] = DATA + len(blob)
    blob.extend(struct.pack("<6I", *[v["cap%d" % i] for i in range(6)]))
    assert DATA + len(blob) <= DATA_END, hex(len(blob))
    for k, o in G.items():
        v["g_" + k] = DATA + o
    return bytes(blob), v


def asm_src(v):
    f = dict(v)
    f.update({k: "0x%x" % a for k, a in IAT.items()})
    f.update(setenabled="0x401550", setdown="0x402318", fc="0x%x" % FORMCREATE, lstrclr="0x%x" % LSTRCLR, epgl="0x%x" % EP_GETLANG, epeng="0x%x" % EP_ENGINE,
             eprws="0x%x" % EP_RWSTRING, hsesave="0x%x" % HSE_SAVE, hsecb="0x%x" % HSE_SAVECB)
    for k in list(f):
        if isinstance(f[k], int):
            f[k] = "0x%x" % f[k]
    return """
wrap:
    push eax
    push edx
    call {fc}
    pop edx
    pop eax
    pushad
    mov dword ptr [{g_form}], eax
    mov ebx, eax
    mov ecx, dword ptr [{getlang}]
    sub ecx, {epgl}
    mov dword ptr [{g_epd}], ecx
    mov esi, dword ptr [ebx + 0x10]
    test esi, esi
    jz nobtn
    mov ecx, dword ptr [esi + 0x8]
    mov esi, dword ptr [esi + 0x4]
findloop:
    test ecx, ecx
    jz nobtn
    mov edi, dword ptr [esi]
    mov eax, dword ptr [edi + 0x8]
    test eax, eax
    jz fnext
    cmp dword ptr [eax - 0x4], 0xb
    jne fnext
    push ecx
    push esi
    push edi
    mov esi, eax
    mov edi, {btnname}
    mov ecx, 0xb
    repe cmpsb
    pop edi
    pop esi
    pop ecx
    jne fnext
    mov dword ptr [{g_btn}], edi
    mov eax, edi
    xor edx, edx
    call {setenabled}
    jmp nobtn
fnext:
    add esi, 0x4
    dec ecx
    jmp findloop
nobtn:
    mov dword ptr [{g_idx}], 0x1
    call readreg
    mov eax, dword ptr [{g_idx}]
    mov eax, dword ptr [{mintab} + eax*4]
    mov dword ptr [{g_mins}], eax
    mov eax, dword ptr [ebx + 0x204]
    test eax, eax
    jz nomenu
    mov dword ptr [{g_tmp}], eax
    mov eax, dword ptr [{mi_class}]
    mov dl, 0x1
    mov ecx, ebx
    call dword ptr [{mi_create}]
    mov dword ptr [{g_sub}], eax
    mov edx, {title}
    call dword ptr [{mi_caption}]
    mov eax, dword ptr [{g_tmp}]
    mov edx, dword ptr [{g_sub}]
    call dword ptr [{mi_add}]
    xor edi, edi
mloop:
    mov eax, dword ptr [{mi_class}]
    mov dl, 0x1
    mov ecx, ebx
    call dword ptr [{mi_create}]
    mov esi, eax
    mov edx, dword ptr [{captab} + edi*4]
    call dword ptr [{mi_caption}]
    mov eax, esi
    mov dl, 0x1
    call dword ptr [{mi_radio}]
    mov dword ptr [esi + 0x60], menuclick
    mov dword ptr [esi + 0x64], edi
    cmp edi, dword ptr [{g_idx}]
    jne mnochk
    mov eax, esi
    mov dl, 0x1
    call dword ptr [{mi_checked}]
mnochk:
    mov eax, dword ptr [{g_sub}]
    mov edx, esi
    call dword ptr [{mi_add}]
    inc edi
    cmp edi, 0x6
    jb mloop
nomenu:
    mov eax, dword ptr [{tm_class}]
    mov dl, 0x1
    mov ecx, ebx
    call dword ptr [{tm_create}]
    mov esi, eax
    mov edx, 0x3e8
    call dword ptr [{tm_interval}]
    push 0x0
    mov ecx, tick
    push ecx
    mov eax, esi
    call dword ptr [{tm_ontimer}]
    popad
    ret

menuclick:
    pushad
    cmp eax, 0x5
    ja mcout
    mov dword ptr [{g_idx}], eax
    mov ecx, dword ptr [{mintab} + eax*4]
    mov dword ptr [{g_mins}], ecx
    mov dword ptr [{g_elap}], 0x0
    mov eax, edx
    mov dl, 0x1
    call dword ptr [{mi_checked}]
    call writereg
mcout:
    popad
    ret

tick:
    pushad
    call {bsync}
    mov ebp, dword ptr [{g_btn}]
    test ebp, ebp
    jz tout
    xor ecx, ecx
    mov eax, dword ptr [{g_form}]
    mov ebx, dword ptr [eax + 0x22c]
    test ebx, ebx
    jz tstate
    cmp byte ptr [ebx + 0x1bc], 0x0
    je tstate
    mov esi, dword ptr [ebx + 0x1c0]
    test esi, esi
    jz tstate
    inc ecx
tstate:
    cmp byte ptr [ebp + 0x45], cl
    je tsame
    push ecx
    mov eax, ebp
    mov edx, ecx
    call {setenabled}
    pop ecx
    test ecx, ecx
    jnz tsame
    mov eax, ebp
    xor edx, edx
    call {setdown}
tsame:
    test ecx, ecx
    jz treset
    cmp byte ptr [ebp + 0xc0], 0x0
    je treset
    mov edi, dword ptr [ebx + 0x1e4]
    test edi, edi
    jz treset
    add dword ptr [{g_elap}], 0x1
    mov eax, dword ptr [{g_mins}]
    imul eax, eax, 0x3c
    cmp dword ptr [{g_elap}], eax
    jb tout
    mov dword ptr [{g_elap}], 0x0
    call dosave
    jmp tout
treset:
    mov dword ptr [{g_elap}], 0x0
tout:
    popad
    ret

dosave:
    push ebp
    mov ebp, esp
    sub esp, 0x220
    mov dword ptr [ebp - 0x220], 0xffffffff
    mov ecx, dword ptr [edi - 0x4]
    cmp ecx, 0x1c0
    ja dsout
    mov edx, ecx
dsfind:
    test edx, edx
    jz dsout
    cmp byte ptr [edi + edx - 0x1], 0x5c
    je dsfound
    dec edx
    jmp dsfind
dsfound:
    mov dword ptr [ebp - 0x10], ecx
    mov dword ptr [ebp - 0xc], edx
    mov dword ptr [ebp - 0x8], esi
    mov esi, edi
    lea edi, [ebp - 0x218]
    mov ecx, edx
    rep movsb
    mov dword ptr [ebp - 0x14], esi
    mov esi, {auto1}
    mov ecx, 0xb
    cmp dword ptr [{g_tog}], 0x0
    je dspfx
    mov esi, {auto2}
    mov ecx, 0xc
dspfx:
    rep movsb
    mov esi, dword ptr [ebp - 0x14]
    mov ecx, dword ptr [ebp - 0x10]
    sub ecx, dword ptr [ebp - 0xc]
    rep movsb
    mov byte ptr [edi], 0x0
    lea eax, [ebp - 0x218]
    sub edi, eax
    mov dword ptr [ebp - 0x21c], edi
    xor dword ptr [{g_tog}], 0x1
    push ebx
    mov eax, dword ptr [{hsmsave}]
    sub eax, {hsesave}
    add eax, {hsecb}
    push eax
    mov eax, dword ptr [ebp - 0x8]
    mov eax, dword ptr [eax + 0x3c]
    mov dword ptr [ebp - 0x18], eax
    xor ecx, ecx
    test eax, eax
    jz dsnomod
    mov cl, byte ptr [eax + 0x3c]
dsnomod:
    mov dword ptr [ebp - 0x1c], ecx
    lea edx, [ebp - 0x218]
    mov eax, dword ptr [ebp - 0x8]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0xac]
    mov eax, dword ptr [ebp - 0x18]
    test eax, eax
    jz dsout
    mov ecx, dword ptr [ebp - 0x1c]
    and cl, 0x1
    or byte ptr [eax + 0x3c], cl
dsout:
    mov esp, ebp
    pop ebp
    ret

readreg:
    mov eax, dword ptr [{g_epd}]
    mov eax, dword ptr [eax + {epeng}]
    test eax, eax
    jz rrout
    mov eax, dword ptr [eax + 0x5c]
    test eax, eax
    jz rrout
    push 0x0
    mov edx, esp
    push edx
    push 0x0
    mov edx, {general}
    mov ecx, {valname}
    mov esi, dword ptr [{g_epd}]
    add esi, {eprws}
    call esi
    mov eax, dword ptr [esp]
    test eax, eax
    jz rrclr
    movzx ecx, byte ptr [eax]
    sub ecx, 0x30
    cmp ecx, 0x5
    ja rrclr
    mov dword ptr [{g_idx}], ecx
rrclr:
    mov eax, esp
    call {lstrclr}
    add esp, 0x4
rrout:
    ret

writereg:
    mov eax, dword ptr [{g_epd}]
    mov eax, dword ptr [eax + {epeng}]
    test eax, eax
    jz wrout
    mov eax, dword ptr [eax + 0x5c]
    test eax, eax
    jz wrout
    mov edx, dword ptr [{g_idx}]
    add edx, 0x30
    mov byte ptr [{dig}], dl
    mov dword ptr [{g_wslot}], {dig}
    push {g_wslot}
    push 0x1
    mov edx, {general}
    mov ecx, {valname}
    mov esi, dword ptr [{g_epd}]
    add esi, {eprws}
    call esi
wrout:
    ret
""".format(**f)


# ---- DFM ---------------------------------------------------------------------------------------------------------
def hourglass_glyph(gdata):
    from PIL import Image
    n = struct.unpack_from("<I", gdata, 0)[0]
    bmp = gdata[4:4 + n]
    im = Image.open(io.BytesIO(bmp)).convert("RGB")
    assert im.size == (64, 32)
    art = ["WWWWWWWWWWW",
           "DDDDDDDDDDD",
           " G.......G ",
           " G.......G ",
           "  GSSSSSG  ",
           "   GSSSG   ",
           "    GSG    ",
           "     G     ",
           "    GSG    ",
           "   G.S.G   ",
           "  G..S..G  ",
           " G..SSS..G ",
           " GSSSSSSSG ",
           "DDDDDDDDDDD",
           "WWWWWWWWWWW"]
    norm = {"W": (176, 112, 52), "D": (96, 56, 24), "G": (36, 36, 56), ".": (226, 238, 248), "S": (238, 186, 52)}
    dis = {"W": (128, 128, 140), "D": (128, 128, 140), "G": (128, 128, 140), "S": (128, 128, 140),
           ".": (255, 255, 255)}
    px = im.load()
    for half, pal in ((0, norm), (32, dis)):
        ox, oy = half + 20, 17
        for y, row in enumerate(art):
            for x, ch in enumerate(row):
                if ch != " ":
                    px[ox + x, oy + y] = pal[ch]
    assert px[0, 31] == (191, 191, 191)
    b = io.BytesIO(); im.save(b, "BMP")
    nb = b.getvalue()
    assert len(nb) == len(bmp)
    return struct.pack("<I", len(nb)) + nb


def i16(v):
    return b"\x03" + struct.pack("<h", v)


def new_dfm(dfm):
    D = PAL.DFM(dfm)
    save = D.get("SaveBtn")
    spl = dict(SP.props(dfm, save))
    p = D.get("Panel2")
    sx = 44
    assert spl["Left"] == b"\x02" + bytes([sx]), spl["Left"]
    edits = []
    for k in p["kids"]:
        if k["cls"] != b"TSpeedButton":
            continue
        pl = SP.props(dfm, k)
        dd = dict(pl)
        lv = dd["Left"]
        left = lv[1] if lv[0] == 2 else struct.unpack_from("<h", lv, 1)[0]
        if left > sx:
            newk = SP.ser_comp(k["cls"], k["name"], [(a, i16(left + SHIFT) if a == "Left" else b) for a, b in pl])
            edits.append((k["start"], k["end"], newk))
    btn = [("Left", i16(sx + SHIFT)), ("Top", spl["Top"]), ("Width", spl["Width"]), ("Height", spl["Height"]),
           ("Hint", SP.vstr(HINT)), ("AllowAllUp", b"\x09"), ("GroupIndex", b"\x02" + bytes([GROUP])),
           ("Flat", spl["Flat"]), ("Glyph.Data", SP.vbin(hourglass_glyph(spl["Glyph.Data"][5:]))),
           ("NumGlyphs", spl["NumGlyphs"])]
    edits.append((save["end"], save["end"], SP.ser_comp(b"TSpeedButton", BTN, btn)))
    out = bytearray(); pos = 0
    for s, e, b in sorted(edits, key=lambda t: (t[0], t[1])):
        out += dfm[pos:s] + b; pos = e
    out += dfm[pos:]
    N = PAL.DFM(bytes(out))
    assert N.get(BTN)["parent"] == "Panel2"
    return bytes(out)


def place_dfm(d, pe, rva, nd):
    secs = pe.sections
    last = max(secs, key=lambda s: s.PointerToRawData)
    assert last.Name.rstrip(b"\0") == b".xprn" and last.PointerToRawData + last.SizeOfRawData == len(d)
    dfm_fo = pe.get_offset_from_rva(rva)
    old_len = struct.unpack_from("<I", d, PAL.RES_ENTRY_FO + 4)[0]
    assert not any(d[dfm_fo + old_len:]), "data after the DFM in .xprn"
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
    return out


def mt_entry(d, off):
    n = struct.unpack_from("<H", d, off(MT))[0]
    p = off(MT) + 2
    for _ in range(n):
        sz = struct.unpack_from("<H", d, p)[0]
        nm = d[p + 7:p + 7 + d[p + 6]]
        if nm == b"FormCreate":
            return p + 2
        p += sz
    raise KeyError("FormCreate")


BSYNC_SRC = """
    mov eax, dword ptr [{g_form}]
    test eax, eax
    jz bs_r
    mov ecx, dword ptr [eax + 0x5f8]
    test ecx, ecx
    jz bs_r
    mov edx, dword ptr [eax + 0x10]
    test edx, edx
    jz bs_r
    mov esi, dword ptr [edx + 0x4]
    mov edi, dword ptr [edx + 0x8]
    dec edi
    xor ebx, ebx
bs_l:
    cmp ebx, edi
    jge bs_r
    cmp dword ptr [esi + ebx*4], ecx
    je bs_f
    inc ebx
    jmp bs_l
bs_f:
    mov eax, dword ptr [esi + ebx*4 + 0x4]
    mov dl, byte ptr [ecx + 0x45]
    cmp byte ptr [eax + 0x45], dl
    je bs_r
    call 0x401550
bs_r:
    ret
"""


def with_bsync(data, v):
    """v1.3 (user: 'map brush should be greyed out when the other ones are'): Brush4Btn (patch_devx_massive_brush_v1,
    the component created right after Brush3Btn [form+0x5F8] in Form.Components) copies Brush3Btn.Enabled every tick.
    Lives in the data zone's tail (RWX)."""
    at = DATA + ((len(data) + 3) & ~3)
    code = OV.asm(BSYNC_SRC.format(g_form="0x%x" % v["g_form"]), at)
    assert at + len(code) <= DATA_END, (hex(at), len(code))
    v["bsync"] = at
    return data + bytes(at - DATA - len(data)) + code


def build(d):
    import pefile
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - 0x400000)  # noqa: E731
    rva, dfm = PAL.mainform_dfm(pe)
    data, v = build_data()
    data = with_bsync(data, v)
    code = OV.asm(asm_src(v), ZONE)
    assert len(code) <= ZONE_END - ZONE, hex(len(code))
    if b"\x0bAutoSaveBtn" in dfm:                       # update: code/data zones are ours
        fe = mt_entry(d, off)
        assert struct.unpack_from("<I", d, fe)[0] == ZONE
        out = bytearray(d)
        out[off(ZONE):off(ZONE_END)] = code + bytes(ZONE_END - ZONE - len(code))
        out[off(DATA):off(DATA_END)] = data + bytes(DATA_END - DATA - len(data))
        if bytes(out) == d:
            return None
        return bytes(out), len(code), len(data), len(dfm), len(dfm)
    assert not any(d[off(ZONE):off(ZONE_END)]) and not any(d[off(DATA):off(DATA_END)]), "zones not free"
    fe = mt_entry(d, off)
    assert struct.unpack_from("<I", d, fe)[0] == FORMCREATE, hex(struct.unpack_from("<I", d, fe)[0])
    nd = new_dfm(dfm)
    out = place_dfm(d, pe, rva, nd)
    out[off(ZONE):off(ZONE) + len(code)] = code
    out[off(DATA):off(DATA) + len(data)] = data
    struct.pack_into("<I", out, fe, ZONE)
    return bytes(out), len(code), len(data), len(dfm), len(nd)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    bk = bak_path(EXE, TAG)
    if revert:
        if os.path.exists(bk):
            shutil.copy2(bk, EXE); print("restored", bk)
        return 0
    d = open(EXE, "rb").read()
    r = build(d)
    if r is None:
        print("AoWDevX.exe already applied"); return 0
    out, nc, ndata, od, nd = r
    print("AoWDevX.exe: code %d B @%#x, data %d B @%#x, DFM %d -> %d B" % (nc, ZONE, ndata, DATA, od, nd))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bk):
        shutil.copy2(EXE, bk)
    with open(EXE, "wb") as fh:
        fh.write(out)
    assert open(EXE, "rb").read() == out
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
