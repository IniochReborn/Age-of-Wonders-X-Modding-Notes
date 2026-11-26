#!/usr/bin/env python3
r"""
AoWDevX.exe editor patch v2 (supersedes patch_devx_prune_unused_v1.py, 2026-09-14):

 1. Developer menu: "Delete Unused Heroes" / "Delete Unused Items" (separator + two items
    after "Remove Leaders"), same caves as v1 - hero: Owner == nil and not TLeader ->
    Deactivate + Release; item: container == nil -> TItemControl.UnRegisterItem (resolved
    from the RegisterItem import + 0x8C, prologue-checked).  Count + Yes/No/Cancel first.
 2. Main toolbar (Panel2), right of "Preview": Fog of War toggle (x=592, GroupIndex 5,
    stays in step with the Developer > Fog of War check mark both ways), "Delete unused
    heroes" (x=652) and "Delete unused items" (x=692).  Glyphs painted by
    make_devx_toolbar_icons.py (assets\devx_*_btn.bmp, 64x32 two-state like the others).
    The three buttons are real TMainForm fields (+0x6AC/+0x6B0/+0x6B4) so the map-open /
    map-close code enables and disables them with the other toolbar buttons.
 3. Map Validation dialog: double-clicking an entry now also plays the shrinking-circle
    centre animation that Go-to uses (patches the CenterView call inside BXL's .vgo cave).
 4. Go-to (items / heroes tabs): an item in an exploration site's treasure, or a hero in a
    site's defender party, has no map location of its own (TItemList.GetLocation and
    TArmy.GetLocation report "nowhere"); Go-to now finds the exploration site whose
    treasure list / defender army holds the object and centres on that site instead.

Mechanics (fixed-base exe):
  * .xprn (the last section, VA 0x4E9000) grows to hold: caves + literals (+0x0000),
    the relocated TMainForm FIELD table (+0x1000, +3 TSpeedButton entries, InstanceSize
    0x6AC -> 0x6B8), the relocated PUBLISHED-METHOD table (+0x2800: FogofWarClick ->
    fog wrapper, + PruneHeroesClick, + PruneItemsClick), and the relocated TMAINFORM DFM
    (+0x4000, resource data entry @file 0x43550 repointed) carrying the new nodes.
  * CODE hooks: 0x42A19C / 0x42A4BF (SetEnabled(PreviewBtn) in the map-close / map-open
    paths -> cave that also does the three new buttons); 0x42CD44 / 0x42CDE0 (the
    `cmp byte [esp],0xFF / je` "no location" test in GotoItemClick / GoToHeroClick ->
    site-search cave); .vgo 0x4E30F0 (`call THSMEdit.CenterView` -> cave that also calls
    TAbstractAoWHSMap.PlayCenterAnimation).
  * AoWEPACK addresses reached from the exe use the rebase delta [IAT AoWHSMap 0x43289C]
    - 0x558FA040: class VMTs TItemExplorationSite 0x557C23BC / TExplorationSite 0x557C1440,
    site fields +0x3C treasure list / +0x34 defender army, TStructureControl = map+0x100
    ([sc+8] node, [node+8] TList: +4 array +8 count), map-object GetX/GetY/GetLevel = VMT
    +0x74/+0x78/+0x7C, class test = walk [[VMT-0x18]] parent cells.

The v1 backup AoWDevX.exe.bak_prune is the pristine base: this script always rebuilds
from it when present (so it is idempotent over v1 or itself).  Dry-run default; --apply;
--revert (restores the backup); --dis.  Needs keystone-engine, capstone.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXE = game_file(r"AoWDevX.exe")
BAK_SUFFIX = ".bak_prune"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x400000
SEC_NAME, SEC_VA = b".xprn", 0x4E9000
OFF_FIELDS, OFF_METHODS, OFF_DFM = 0x1000, 0x2800, 0x4000
SEC_CHARS = 0xE0000060
ASSETS = {k: os.path.join(HERE, "assets", v) for k, v in
          (("fog", "devx_fog_btn.bmp"), ("heroes", "devx_prune_heroes_btn.bmp"), ("items", "devx_prune_items_btn.bmp"))}

# ---- exe facts (verified 2026-09-14) -------------------------------------------------
VMT_MAINFORM   = 0x425D00
MT_ORIG, MT_ORIG_COUNT = 0x4272EE, 132          # published-method table (VMT-0x28)
FT_ORIG, FT_ORIG_COUNT = 0x425D92, 305          # field table (VMT-0x2C)
INSTSIZE_ORIG, INSTSIZE_NEW = 0x6AC, 0x6B8
RES_ENTRY_FO, DFM_RVA, DFM_SIZE = 0x43550, 0x784FC, 0x4AFD5
FOGOFWARCLICK  = 0x42BB64          # TMainForm.FogofWarClick (toggles menu Checked, applies to map)
MSGDLG         = 0x42BBE4
T_GETCOUNT, T_GETHERO, T_ISCLASS = 0x401E60, 0x401E58, 0x401048
T_SETMODIFIED, T_MSGBOX, T_DESELECT = 0x401FF0, 0x401348, 0x402DE8
T_SETENABLED, T_SETDOWN = 0x401550, 0x402318   # TControl.SetEnabled(eax,dl) / TSpeedButton.SetDown(eax,dl)
T_CENTERVIEW, T_PLAYCENTER = 0x402E28, 0x401CF8   # THSMEdit.CenterView / TAbstractAoWHSMap.PlayCenterAnimation (eax,dl=x,cl=y,push level) ret 4
T_GETSELITEM, T_GETSELHERO = 0x403118, 0x403158
MAP_SLOT, TLEADER_SLOT, APP_SLOT = 0x43289C, 0x4328AC, 0x432224
IAT_REGISTERITEM = 0x4326E0
UNREG_DELTA = 0x55794F08 - 0x55794E7C
UNREG_SIG = bytes.fromhex("53568bda8bf0f6431c02")
DLL_MAPVAR = 0x558FA040            # AoWE.AoWHSMap preferred VA (delta source)
VMT_ITEMSITE, VMT_SITE = 0x557C23BC, 0x557C1440
SITE_ARMY, SITE_ITEMS = 0x34, 0x3C
MAP_ITEMCONTROL, MAP_HEROCONTROL, MAP_STRUCTCONTROL = 0xF4, 0xF8, 0x100
F_HSMEDIT, HSMEDIT_GUARD, DISP_PAUSE, DISP_RESUME = 0x22C, 0x1BC, 0x90, 0x94
F_FOGMENU, F_PREVIEWBTN = 0x390, 0x610
F_FOGBTN, F_PHBTN, F_PIBTN = 0x6AC, 0x6B0, 0x6B4
CI_SPEEDBUTTON = 30                # TMainForm class table index of Buttons..TSpeedButton
OWNER_OFF, HERO_DEACTIVATE, HERO_RELEASE = 0x04, 0x188, 0x2C
MENU_CHECKED = 0x2C
MB_YESNOCANCEL_BUTTONS, MT_CONFIRMATION, MR_YES, MB_OK_INFO, MB_OK_WARN = 11, 3, 6, 0x40, 0x30

# CODE hook sites: (VA, old bytes, cave label, exit VA or None)
HOOK_EN_CLOSE = (0x42A19C, bytes.fromhex("8b8310060000e8a973fdff"))
HOOK_EN_OPEN  = (0x42A4BF, bytes.fromhex("8b8310060000e88670fdff"))
HOOK_GOTO_ITEM = (0x42CD44, bytes.fromhex("803c24ff743c"), 0x42CD86)
HOOK_GOTO_HERO = (0x42CDE0, bytes.fromhex("803c24ff743c"), 0x42CE22)
HOOK_VGO = (0x4E30F0, bytes.fromhex("e833fdf1ff"))      # inside BXL's valgoto cave (.vgo)

STRINGS = {
    "cap_heroes": "Delete Unused Heroes", "cap_items": "Delete Unused Items", "pre": "Delete ",
    "one_hero": " unused hero?", "many_hero": " unused heroes?", "none_hero": "No unused heroes to delete.",
    "one_item": " unused item?", "many_item": " unused items?", "none_item": "No unused items to delete.",
    "bad_dll": "AoWEPACK.dll does not match the expected layout; no items were deleted.",
}
MSGBUF_CHARS = 64
NEW_METHODS = ("PruneHeroesClick", "PruneItemsClick")


# ------------------------------------------------------------------ PE helpers
def pe_info(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sec0 = e + 24 + optsz
    secs = []
    for i in range(nsec):
        s = d[sec0 + 40 * i: sec0 + 40 * i + 40]
        vs, va, rs, ra = struct.unpack_from("<IIII", s, 8)
        secs.append(dict(name=s[:8].rstrip(b"\0"), va=va, vs=vs, raw=ra, rs=rs, hdr=sec0 + 40 * i))
    return dict(e=e, nsec=nsec, optsz=optsz, sec0=sec0, secs=secs,
                size_of_image=struct.unpack_from("<I", d, e + 24 + 56)[0])


def va2off(P, va):
    r = va - BASE
    for s in P["secs"]:
        if s["va"] <= r < s["va"] + max(s["vs"], s["rs"]):
            return s["raw"] + (r - s["va"])
    raise ValueError("VA %#x is in no section" % va)


# ------------------------------------------------------------------ Delphi tables
def read_method_table(d, o):
    cnt = struct.unpack_from("<H", d, o)[0]
    p, out = o + 2, []
    for _ in range(cnt):
        sz, code = struct.unpack_from("<HI", d, p)
        nl = d[p + 6]
        assert sz == 7 + nl
        out.append((code, d[p + 7:p + 7 + nl].decode("latin1")))
        p += sz
    return out, p - o


def emit_method_table(entries):
    b = struct.pack("<H", len(entries))
    for code, name in entries:
        nb = name.encode("latin1")
        b += struct.pack("<HI", 7 + len(nb), code) + bytes([len(nb)]) + nb
    return b


def read_field_table(d, o):
    cnt = struct.unpack_from("<H", d, o)[0]
    ctab = struct.unpack_from("<I", d, o + 2)[0]
    p, out = o + 6, []
    for _ in range(cnt):
        off, ci = struct.unpack_from("<IH", d, p)
        nl = d[p + 6]
        out.append((off, ci, d[p + 7:p + 7 + nl].decode("latin1")))
        p += 7 + nl
    return out, ctab, p - o


def emit_field_table(entries, ctab):
    b = struct.pack("<HI", len(entries), ctab)
    for off, ci, name in entries:
        nb = name.encode("latin1")
        b += struct.pack("<IH", off, ci) + bytes([len(nb)]) + nb
    return b


# ------------------------------------------------------------------ DFM (parser after BXL's build_deved_heroprune.py)
def ss(s):
    b = s.encode("latin1")
    assert len(b) < 256
    return bytes([len(b)]) + b


class DfmParser(object):
    def __init__(self, data):
        self.d = data

    def rstr(self, o):
        n = self.d[o]
        return self.d[o + 1:o + 1 + n].decode("latin1"), o + 1 + n

    def value(self, o):
        d = self.d
        vt = d[o]
        o += 1
        if vt == 0:
            return o
        if vt == 2:
            return o + 1
        if vt == 3:
            return o + 2
        if vt == 4:
            return o + 4
        if vt == 5:
            return o + 10
        if vt in (6, 7):
            return self.rstr(o)[1]
        if vt in (8, 9, 13):
            return o
        if vt in (10, 12):
            return o + 4 + struct.unpack_from("<I", d, o)[0]
        if vt == 11:
            while True:
                s, o = self.rstr(o)
                if s == "":
                    return o
        if vt == 1:
            while d[o] != 0:
                o = self.value(o)
            return o + 1
        if vt == 15:
            return o + 4
        if vt in (16, 17):
            return o + 8
        if vt == 18:
            return o + 4 + 2 * struct.unpack_from("<I", d, o)[0]
        if vt == 14:
            while d[o] != 0:
                if d[o] in (2, 3, 4):
                    o = self.value(o)
                assert d[o] == 1
                o += 1
                while d[o] != 0:
                    _s, o = self.rstr(o)
                    o = self.value(o)
                o += 1
            return o + 1
        raise ValueError("valuetype %d @ %#x" % (vt, o - 1))

    def obj(self, o):
        d = self.d
        start = o
        if (d[o] & 0xF0) == 0xF0:
            o += 1
            if d[start] & 0x02:
                o = self.value(o)
        cls, o = self.rstr(o)
        name, o = self.rstr(o)
        props = {}
        while True:
            pn, o2 = self.rstr(o)
            if pn == "":
                o = o2
                break
            vs = o2
            o = self.value(o2)
            props[pn] = (vs, o)
        kids = []
        while d[o] != 0:
            c = self.obj(o)
            kids.append(c)
            o = c["end"]
        return dict(cls=cls, name=name, start=start, props=props, children=kids, end=o + 1)


def find_node(node, name):
    if node["name"] == name:
        return node
    for c in node["children"]:
        r = find_node(c, name)
        if r:
            return r
    return None


def all_names(node, out=None):
    out = [] if out is None else out
    out.append(node["name"])
    for c in node["children"]:
        all_names(c, out)
    return out


def p_int(name, v):
    if -128 <= v <= 127:
        return ss(name) + b"\x02" + struct.pack("<b", v)
    return ss(name) + b"\x03" + struct.pack("<h", v)


def p_str(name, s):
    return ss(name) + b"\x06" + ss(s)


def p_ident(name, s):
    return ss(name) + b"\x07" + ss(s)


def p_bool(name, v):
    return ss(name) + (b"\x09" if v else b"\x08")


def p_bin(name, payload):
    return ss(name) + b"\x0a" + struct.pack("<I", len(payload)) + payload


def speedbutton_node(name, left, hint, bmp, onclick, group=None):
    glyph = struct.pack("<I", len(bmp)) + bmp                 # TBitmap stream: size prefix + BMP file
    b = ss("TSpeedButton") + ss(name)
    b += p_int("Left", left) + p_int("Top", 4) + p_int("Width", 39) + p_int("Height", 38) + p_str("Hint", hint)
    if group is not None:
        b += p_bool("AllowAllUp", True) + p_int("GroupIndex", group)
    b += p_bool("Enabled", False) + p_bool("Flat", True) + p_bin("Glyph.Data", glyph) + p_int("NumGlyphs", 2)
    b += p_ident("OnClick", onclick)
    return b + b"\x00\x00"


def menu_node(name, caption, onclick=None):
    b = ss("TMenuItem") + ss(name) + p_str("Caption", caption)
    if onclick:
        b += p_ident("OnClick", onclick)
    return b + b"\x00\x00"


def build_dfm(orig):
    bmps = {}
    for k, path in ASSETS.items():
        bmp = open(path, "rb").read()
        assert bmp[:2] == b"BM" and struct.unpack_from("<ii", bmp, 18) == (64, 32), path
        bmps[k] = bmp
    blob = orig
    # menu first (it sits after the toolbar in the stream, so offsets before it stay valid)
    root = DfmParser(blob).obj(4)
    anchor = find_node(root, "RemoveLeadersItem")
    at = anchor["end"]
    blob = blob[:at] + menu_node("N_prune", "-") + menu_node("PruneHeroesItem", "Delete Unused Heroes", "PruneHeroesClick") \
        + menu_node("PruneItemsItem", "Delete Unused Items", "PruneItemsClick") + blob[at:]
    root = DfmParser(blob).obj(4)
    anchor = find_node(root, "PreviewBtn")
    at = anchor["end"]
    blob = blob[:at] + speedbutton_node("FogBtn", 592, "Fog of War", bmps["fog"], "FogofWarClick", group=5) \
        + speedbutton_node("PruneHeroesBtn", 652, "Delete unused heroes", bmps["heroes"], "PruneHeroesClick") \
        + speedbutton_node("PruneItemsBtn", 692, "Delete unused items", bmps["items"], "PruneItemsClick") + blob[at:]
    root = DfmParser(blob).obj(4)
    assert root["end"] == len(blob), "DFM walk does not consume the whole stream"
    names = all_names(root)
    dupes = sorted({n for n in names if n and names.count(n) > 1})
    assert not dupes, dupes
    panel2 = find_node(root, "Panel2")
    kids = [c["name"] for c in panel2["children"]]
    assert kids[kids.index("PreviewBtn"):kids.index("PreviewBtn") + 4] == ["PreviewBtn", "FogBtn", "PruneHeroesBtn", "PruneItemsBtn"], kids
    dev = [c["name"] for c in find_node(root, "DeveloperItems")["children"]]
    assert dev[-4:] == ["RemoveLeadersItem", "N_prune", "PruneHeroesItem", "PruneItemsItem"], dev[-5:]
    return blob


# ------------------------------------------------------------------ caves
def assemble(sec_va, L):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    A = []
    a = A.append
    H = lambda v: "0x%X" % v  # noqa: E731  -- keystone reads bare decimals as hex

    # ---- pause / resume (eax=form)
    for nm, slot in (("pause", DISP_PAUSE), ("resume", DISP_RESUME)):
        a("%s:" % nm)
        a("mov  eax, [eax + %s]" % H(F_HSMEDIT)); a("test eax, eax"); a("je   %s_out" % nm)
        a("cmp  byte ptr [eax + %s], 0" % H(HSMEDIT_GUARD)); a("je   %s_out" % nm)
        a("mov  edx, [eax]"); a("call dword ptr [edx + %s]" % H(slot))
        a("%s_out:" % nm); a("ret")

    # ---- confirm(eax=form, ecx=count, edx=desc{one,many,none,cap}) -> eax 1/0
    a("confirm:")
    a("push ebx"); a("push esi"); a("push edi")
    a("mov  esi, eax"); a("mov  ebx, edx"); a("mov  eax, ecx")
    a("test eax, eax"); a("jne  cf_build")
    a("push %s" % H(MB_OK_INFO)); a("mov  ecx, [ebx + 0xC]"); a("mov  edx, [ebx + 0x8]")
    a("mov  eax, [%s]" % H(APP_SLOT)); a("mov  eax, [eax]"); a("call %s" % H(T_MSGBOX))
    a("xor  eax, eax"); a("jmp  cf_out")
    a("cf_build:")
    a("push eax"); a("mov  edi, %s" % H(L["msgbuf"])); a("mov  edx, %s" % H(L["pre"])); a("call copyz")
    a("pop  eax"); a("push eax"); a("xor  ecx, ecx"); a("push ebx"); a("mov  ebx, 0xA")
    a("cf_dig:"); a("xor  edx, edx"); a("div  ebx"); a("add  dl, 0x30"); a("push edx"); a("inc  ecx"); a("test eax, eax"); a("jne  cf_dig")
    a("cf_emit:"); a("pop  eax"); a("mov  [edi], al"); a("inc  edi"); a("dec  ecx"); a("jne  cf_emit")
    a("pop  ebx"); a("pop  eax")
    a("mov  edx, [ebx + 0x4]"); a("cmp  eax, 0x1"); a("jne  cf_suffix"); a("mov  edx, [ebx]")
    a("cf_suffix:"); a("call copyz"); a("mov  byte ptr [edi], 0")
    a("sub  edi, %s" % H(L["msgbuf"])); a("mov  dword ptr [%s], edi" % H(L["msgbuf"] - 4))
    a("push %s" % H(MB_YESNOCANCEL_BUTTONS)); a("push 0"); a("mov  edx, %s" % H(L["msgbuf"]))
    a("mov  cl, %s" % H(MT_CONFIRMATION)); a("mov  eax, esi"); a("call %s" % H(MSGDLG))
    a("cmp  ax, %s" % H(MR_YES)); a("sete al"); a("movzx eax, al")
    a("cf_out:"); a("pop  edi"); a("pop  esi"); a("pop  ebx"); a("ret")

    a("copyz:"); a("mov  al, [edx]"); a("test al, al"); a("je   cz_out"); a("mov  [edi], al"); a("inc  edi"); a("inc  edx"); a("jmp  copyz")
    a("cz_out:"); a("ret")

    for nm, off in (("get_hc", MAP_HEROCONTROL), ("get_ic", MAP_ITEMCONTROL)):
        a("%s:" % nm); a("mov  eax, [%s]" % H(MAP_SLOT)); a("mov  eax, [eax]"); a("test eax, eax"); a("je   %s_out" % nm)
        a("mov  eax, [eax + %s]" % H(off)); a("%s_out:" % nm); a("ret")
    a("set_modified:"); a("mov  eax, [%s]" % H(MAP_SLOT)); a("mov  eax, [eax]"); a("test eax, eax"); a("je   sm_out")
    a("call %s" % H(T_SETMODIFIED)); a("sm_out:"); a("ret")

    # ================= PruneHeroesClick (eax=form, edx=Sender) =================
    a("prune_heroes:")
    a("push ebx"); a("push esi"); a("push edi"); a("mov  esi, eax")
    a("mov  eax, [%s]" % H(MAP_SLOT)); a("mov  eax, [eax]"); a("test eax, eax"); a("je   ph_exit")
    a("mov  eax, esi"); a("call pause")
    a("xor  edi, edi"); a("call get_hc"); a("test eax, eax"); a("je   ph_counted")
    a("call %s" % H(T_GETCOUNT)); a("mov  ebx, eax"); a("dec  ebx"); a("js   ph_counted")
    a("ph_cloop:"); a("call get_hc"); a("mov  edx, ebx"); a("call %s" % H(T_GETHERO)); a("test eax, eax"); a("je   ph_cnext")
    a("cmp  dword ptr [eax + %s], 0" % H(OWNER_OFF)); a("jne  ph_cnext")
    a("mov  edx, [%s]" % H(TLEADER_SLOT)); a("call %s" % H(T_ISCLASS)); a("test al, al"); a("jne  ph_cnext"); a("inc  edi")
    a("ph_cnext:"); a("dec  ebx"); a("jns  ph_cloop")
    a("ph_counted:"); a("mov  eax, esi"); a("mov  ecx, edi"); a("mov  edx, %s" % H(L["desc_heroes"])); a("call confirm")
    a("test eax, eax"); a("je   ph_resume")
    a("call get_hc"); a("test eax, eax"); a("je   ph_resume"); a("call %s" % H(T_GETCOUNT)); a("mov  ebx, eax"); a("dec  ebx"); a("js   ph_mod")
    a("ph_dloop:"); a("call get_hc"); a("mov  edx, ebx"); a("call %s" % H(T_GETHERO)); a("test eax, eax"); a("je   ph_dnext")
    a("cmp  dword ptr [eax + %s], 0" % H(OWNER_OFF)); a("jne  ph_dnext")
    a("mov  edx, [%s]" % H(TLEADER_SLOT)); a("call %s" % H(T_ISCLASS)); a("test al, al"); a("jne  ph_dnext")
    a("call get_hc"); a("mov  edx, ebx"); a("call %s" % H(T_GETHERO)); a("mov  edi, eax"); a("test edi, edi"); a("je   ph_dnext")
    a("mov  eax, edi"); a("mov  edx, [eax]"); a("call dword ptr [edx + %s]" % H(HERO_DEACTIVATE))
    a("mov  eax, edi"); a("mov  edx, [eax]"); a("call dword ptr [edx + %s]" % H(HERO_RELEASE))
    a("ph_dnext:"); a("dec  ebx"); a("jns  ph_dloop")
    a("ph_mod:"); a("call set_modified")
    a("ph_resume:"); a("mov  eax, esi"); a("call resume")
    a("ph_exit:"); a("pop  edi"); a("pop  esi"); a("pop  ebx"); a("ret")

    # ================= PruneItemsClick (eax=form, edx=Sender) ==================
    a("prune_items:")
    a("push ebx"); a("push esi"); a("push edi"); a("mov  esi, eax")
    a("mov  eax, [%s]" % H(MAP_SLOT)); a("mov  eax, [eax]"); a("test eax, eax"); a("je   pi_exit")
    a("mov  eax, esi"); a("call pause")
    a("xor  edi, edi"); a("call get_ic"); a("test eax, eax"); a("je   pi_counted")
    a("mov  ecx, [eax + 0x8]"); a("mov  ebx, [ecx + 0x8]"); a("dec  ebx"); a("js   pi_counted")
    a("pi_cloop:"); a("call get_ic"); a("mov  eax, [eax + 0x8]"); a("mov  eax, [eax + 0x4]"); a("mov  eax, [eax + ebx*4]")
    a("test eax, eax"); a("je   pi_cnext"); a("cmp  dword ptr [eax + %s], 0" % H(OWNER_OFF)); a("jne  pi_cnext"); a("inc  edi")
    a("pi_cnext:"); a("dec  ebx"); a("jns  pi_cloop")
    a("pi_counted:"); a("mov  eax, esi"); a("mov  ecx, edi"); a("mov  edx, %s" % H(L["desc_items"])); a("call confirm")
    a("test eax, eax"); a("je   pi_resume")
    a("mov  edi, [%s]" % H(IAT_REGISTERITEM)); a("add  edi, %s" % H(UNREG_DELTA))
    a("cmp  dword ptr [edi], %s" % H(struct.unpack_from("<I", UNREG_SIG, 0)[0])); a("jne  pi_bad")
    a("cmp  dword ptr [edi + 0x4], %s" % H(struct.unpack_from("<I", UNREG_SIG, 4)[0])); a("jne  pi_bad")
    a("cmp  word ptr [edi + 0x8], %s" % H(struct.unpack_from("<H", UNREG_SIG, 8)[0])); a("jne  pi_bad")
    a("mov  eax, [esi + %s]" % H(F_HSMEDIT)); a("test eax, eax"); a("je   pi_nodesel"); a("call %s" % H(T_DESELECT))
    a("pi_nodesel:"); a("call get_ic"); a("test eax, eax"); a("je   pi_resume")
    a("mov  ecx, [eax + 0x8]"); a("mov  ebx, [ecx + 0x8]"); a("dec  ebx"); a("js   pi_mod")
    a("pi_dloop:"); a("call get_ic"); a("mov  edx, eax"); a("mov  eax, [eax + 0x8]"); a("mov  eax, [eax + 0x4]"); a("mov  eax, [eax + ebx*4]")
    a("test eax, eax"); a("je   pi_dnext"); a("cmp  dword ptr [eax + %s], 0" % H(OWNER_OFF)); a("jne  pi_dnext")
    a("xchg eax, edx"); a("call edi")
    a("pi_dnext:"); a("dec  ebx"); a("jns  pi_dloop")
    a("pi_mod:"); a("call set_modified"); a("jmp  pi_resume")
    a("pi_bad:"); a("push %s" % H(MB_OK_WARN)); a("mov  ecx, %s" % H(L["cap_items"])); a("mov  edx, %s" % H(L["bad_dll"]))
    a("mov  eax, [%s]" % H(APP_SLOT)); a("mov  eax, [eax]"); a("call %s" % H(T_MSGBOX))
    a("pi_resume:"); a("mov  eax, esi"); a("call resume")
    a("pi_exit:"); a("pop  edi"); a("pop  esi"); a("pop  ebx"); a("ret")

    # ================= FogofWarClick wrapper: original, then button Down := menu Checked
    a("fog_click:")
    a("push ebx"); a("mov  ebx, eax"); a("call %s" % H(FOGOFWARCLICK))
    a("mov  eax, [ebx + %s]" % H(F_FOGMENU)); a("test eax, eax"); a("je   fg_out")
    a("mov  dl, [eax + %s]" % H(MENU_CHECKED))
    a("mov  eax, [ebx + %s]" % H(F_FOGBTN)); a("test eax, eax"); a("je   fg_out")
    a("call %s" % H(T_SETDOWN))
    a("fg_out:"); a("pop  ebx"); a("ret")

    # ================= enable/disable hook: replays SetEnabled(PreviewBtn, dl) + the 3 new buttons
    a("enable_hook:")
    a("push edx")
    for f in (F_PREVIEWBTN, F_FOGBTN, F_PHBTN, F_PIBTN):
        a("mov  edx, [esp]"); a("mov  eax, [ebx + %s]" % H(f)); a("test eax, eax"); a("je   en_%x" % f)
        a("call %s" % H(T_SETENABLED)); a("en_%x:" % f)
    a("pop  edx"); a("ret")

    # ================= validation double-click: CenterView + PlayCenterAnimation
    #   entry: eax=THSMEdit, edx=x, ecx=y, [esp+4]=level (ret 4, like CenterView)
    a("vcenter:")
    a("push ebp"); a("mov  ebp, esp"); a("push edx"); a("push ecx")
    a("push dword ptr [ebp + 0x8]"); a("call %s" % H(T_CENTERVIEW))
    a("pop  ecx"); a("pop  edx")
    a("mov  eax, [%s]" % H(MAP_SLOT)); a("mov  eax, [eax]"); a("test eax, eax"); a("je   vc_out")
    a("push dword ptr [ebp + 0x8]"); a("call %s" % H(T_PLAYCENTER))
    a("vc_out:"); a("pop  ebp"); a("ret  4")

    # ================= Go-to hooks.  Replaces `cmp byte [esp],0xFF / je exit`:
    #   [esp]=ret, [esp+4]=x, [esp+5]=y, [esp+6]=level; ebx=grid; esi=form.
    for nm, getsel, mode, exit_va in (("goto_item", T_GETSELITEM, 0, HOOK_GOTO_ITEM[2]),
                                      ("goto_hero", T_GETSELHERO, 1, HOOK_GOTO_HERO[2])):
        a("%s:" % nm)
        a("cmp  byte ptr [esp + 0x4], 0xFF"); a("jne  %s_ok" % nm)
        a("mov  eax, ebx"); a("call %s" % H(getsel)); a("test eax, eax"); a("je   %s_fail" % nm)
        a("mov  edx, %s" % H(mode)); a("lea  ecx, [esp + 0x4]"); a("call find_site")
        a("test al, al"); a("jne  %s_ok" % nm)
        a("%s_fail:" % nm); a("add  esp, 0x4"); a("jmp  %s" % H(exit_va))
        a("%s_ok:" % nm); a("ret")

    # find_site(eax=object, edx=mode 0 item / 1 hero, ecx=out x,y,level bytes) -> al
    a("find_site:")
    a("push ebx"); a("push esi"); a("push edi"); a("push ebp")
    a("mov  ebp, ecx"); a("mov  edi, edx")
    a("mov  esi, [eax + %s]" % H(OWNER_OFF)); a("test esi, esi"); a("je   fs_no")      # container / army
    a("mov  ebx, [%s]" % H(MAP_SLOT)); a("sub  ebx, %s" % H(DLL_MAPVAR))              # AoWEPACK rebase delta
    a("mov  eax, [%s]" % H(MAP_SLOT)); a("mov  eax, [eax]"); a("test eax, eax"); a("je   fs_no")
    a("mov  eax, [eax + %s]" % H(MAP_STRUCTCONTROL)); a("test eax, eax"); a("je   fs_no")
    a("mov  eax, [eax + 0x8]"); a("test eax, eax"); a("je   fs_no")
    a("mov  eax, [eax + 0x8]"); a("test eax, eax"); a("je   fs_no")
    a("mov  ecx, [eax + 0x8]"); a("mov  eax, [eax + 0x4]")                              # count, array
    a("fs_loop:"); a("dec  ecx"); a("js   fs_no")
    a("push eax"); a("push ecx")
    a("mov  eax, [eax + ecx*4]"); a("test eax, eax"); a("je   fs_next")
    a("lea  edx, [ebx + %s]" % H(VMT_ITEMSITE)); a("test edi, edi"); a("je   fs_cls"); a("lea  edx, [ebx + %s]" % H(VMT_SITE))
    a("fs_cls:"); a("call is_class"); a("test ecx, ecx"); a("je   fs_next")
    a("mov  edx, [eax + %s]" % H(SITE_ITEMS)); a("test edi, edi"); a("je   fs_cmp"); a("mov  edx, [eax + %s]" % H(SITE_ARMY))
    a("fs_cmp:"); a("cmp  edx, esi"); a("jne  fs_next")
    a("pop  ecx"); a("pop  ecx"); a("mov  edi, eax")                                    # found: edi = site
    a("mov  edx, [eax]"); a("call dword ptr [edx + 0x74]"); a("mov  [ebp], al")
    a("mov  eax, edi"); a("mov  edx, [eax]"); a("call dword ptr [edx + 0x78]"); a("mov  [ebp + 0x1], al")
    a("mov  eax, edi"); a("mov  edx, [eax]"); a("call dword ptr [edx + 0x7C]"); a("mov  [ebp + 0x2], al")
    a("mov  al, 0x1"); a("jmp  fs_out")
    a("fs_next:"); a("pop  ecx"); a("pop  eax"); a("jmp  fs_loop")
    a("fs_no:"); a("xor  eax, eax")
    a("fs_out:"); a("pop  ebp"); a("pop  edi"); a("pop  esi"); a("pop  ebx"); a("ret")

    # is_class(eax=object, edx=target VMT) -> ecx 1/0; preserves eax, edx
    a("is_class:")
    a("push eax"); a("push esi"); a("mov  eax, [eax]"); a("mov  esi, 0x40")
    a("ic_loop:"); a("cmp  eax, edx"); a("je   ic_yes")
    a("mov  eax, [eax - 0x18]"); a("test eax, eax"); a("je   ic_no"); a("mov  eax, [eax]"); a("test eax, eax"); a("je   ic_no")
    a("dec  esi"); a("jnz  ic_loop")
    a("ic_no:"); a("xor  ecx, ecx"); a("jmp  ic_out")
    a("ic_yes:"); a("mov  ecx, 0x1")
    a("ic_out:"); a("pop  esi"); a("pop  eax"); a("ret")

    text = "\n".join(A)
    try:
        enc, _ = ks.asm(text, sec_va)
    except Exception as ex:                                  # noqa: BLE001
        bad = [ln for ln in A if not ln.endswith(":") and not _asm_ok(ks, ln, sec_va)]
        raise RuntimeError("%s -- offending line(s): %s" % (ex, bad))
    code = bytes(enc)
    labels = {}
    for lab in ("pause", "resume", "confirm", "prune_heroes", "prune_items", "fog_click", "enable_hook",
                "vcenter", "goto_item", "goto_hero", "find_site", "is_class"):
        probe, _ = ks.asm(text + "\nmov eax, %s" % lab, sec_va)
        probe = bytes(probe)
        assert probe[:len(code)] == code and len(probe) == len(code) + 5
        labels[lab] = struct.unpack_from("<I", probe, len(code) + 1)[0]
    return code, labels


def _asm_ok(ks, line, va):
    try:
        ks.asm(line, va)
        return True
    except Exception:                                        # noqa: BLE001
        return False


def build_data(data_va):
    blob, lit = bytearray(), {}

    def align(n):
        while len(blob) % n:
            blob.append(0)
    for key, text in STRINGS.items():
        align(4)
        blob.extend(struct.pack("<ii", -1, len(text)))
        lit[key] = data_va + len(blob)
        blob.extend(text.encode("latin1") + b"\0")
    align(4)
    blob.extend(struct.pack("<ii", -1, 0))
    lit["msgbuf"] = data_va + len(blob)
    blob.extend(bytes(MSGBUF_CHARS))
    align(4)
    lit["desc_heroes"] = data_va + len(blob)
    blob.extend(struct.pack("<IIII", lit["one_hero"], lit["many_hero"], lit["none_hero"], lit["cap_heroes"]))
    lit["desc_items"] = data_va + len(blob)
    blob.extend(struct.pack("<IIII", lit["one_item"], lit["many_item"], lit["none_item"], lit["cap_items"]))
    return bytes(blob), lit


def build_code():
    zero = {k: 0x1000000 for k in list(STRINGS) + ["msgbuf", "desc_heroes", "desc_items"]}
    code0, _ = assemble(SEC_VA, zero)
    code_len = (len(code0) + 15) // 16 * 16
    data, lit = build_data(SEC_VA + code_len)
    code, labels = assemble(SEC_VA, lit)
    assert len(code) == len(code0)
    blob = code + bytes(code_len - len(code)) + data
    assert len(blob) <= OFF_FIELDS, "caves overflow into the field table"
    return blob, labels, code_len, lit


def check_immediates(code):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    got = [int(i.op_str, 0) for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, SEC_VA)
           if i.mnemonic == "push" and (i.op_str.startswith("0x") or i.op_str.isdigit())]
    want = [MB_OK_INFO, MB_YESNOCANCEL_BUTTONS, 0, MB_OK_WARN]
    assert got == want, "push immediates decoded as %s, expected %s" % (got, want)


def jmp5(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def call5(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="AoWDevX v2: prune menu + toolbar buttons + validate/goto centring")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    args = ap.parse_args()
    exe, bak = args.exe, bak_path(args.exe, BAK_SUFFIX)
    if args.revert:
        if not os.path.exists(bak):
            print("no backup - nothing to revert"); return 1
        shutil.copyfile(bak, exe); print("Restored %s from %s" % (exe, bak)); return 0

    cur = open(exe, "rb").read()
    base = open(bak, "rb").read() if os.path.exists(bak) else cur
    src = "backup" if os.path.exists(bak) else "exe"
    d = bytearray(base)
    P = pe_info(d)
    names = [s["name"] for s in P["secs"]]
    # ---- the base must be pristine (pre-prune)
    assert SEC_NAME not in names, "%s already has %s: not a pristine base" % (src, SEC_NAME.decode())
    mt_va = struct.unpack_from("<I", d, va2off(P, VMT_MAINFORM - 0x28))[0]
    ft_va = struct.unpack_from("<I", d, va2off(P, VMT_MAINFORM - 0x2C))[0]
    inst = struct.unpack_from("<I", d, va2off(P, VMT_MAINFORM - 0x1C))[0]
    assert (mt_va, ft_va, inst) == (MT_ORIG, FT_ORIG, INSTSIZE_ORIG), (hex(mt_va), hex(ft_va), hex(inst))
    assert struct.unpack_from("<II", d, RES_ENTRY_FO) == (DFM_RVA, DFM_SIZE), "TMAINFORM resource entry differs"
    assert P["size_of_image"] == SEC_VA - BASE, "SizeOfImage %#x: %s would not be the next section" % (P["size_of_image"], SEC_NAME.decode())
    assert P["sec0"] + 40 * (P["nsec"] + 1) <= P["secs"][0]["raw"], "no room for a section header"
    for va, old in (HOOK_EN_CLOSE, HOOK_EN_OPEN, HOOK_GOTO_ITEM[:2], HOOK_GOTO_HERO[:2]):
        assert bytes(d[va2off(P, va):va2off(P, va) + len(old)]) == old, "unexpected bytes at %#x" % va
    have_vgo = b".vgo" in names and bytes(d[va2off(P, HOOK_VGO[0]):va2off(P, HOOK_VGO[0]) + 5]) == HOOK_VGO[1]
    dll = os.path.join(os.path.dirname(exe), "AoWEPACK.dll")
    if os.path.exists(dll):
        dd = open(dll, "rb").read(); DP = pe_info(dd)
        dbase = struct.unpack_from("<I", dd, DP["e"] + 24 + 28)[0]

        def dva2off(va):
            r = va - dbase
            for s in DP["secs"]:
                if s["va"] <= r < s["va"] + max(s["vs"], s["rs"]):
                    return s["raw"] + (r - s["va"])
        assert dd[dva2off(0x55794E7C + UNREG_DELTA):][:len(UNREG_SIG)] == UNREG_SIG, "AoWEPACK UnRegisterItem prologue differs"
        for vmt, cname in ((VMT_ITEMSITE, b"TItemExplorationSite"), (VMT_SITE, b"TExplorationSite")):
            cn = struct.unpack_from("<I", dd, dva2off(vmt - 0x20))[0]
            o = dva2off(cn)
            assert dd[o + 1:o + 1 + dd[o]] == cname, "AoWEPACK class at %#x is not %s" % (vmt, cname)
        print("AoWEPACK.dll checks: UnRegisterItem prologue OK, site class VMTs OK")

    # ---- build the pieces
    code, labels, code_len, lit = build_code()
    check_immediates(code[:code_len])
    mt, mt_len = read_method_table(d, va2off(P, MT_ORIG))
    assert len(mt) == MT_ORIG_COUNT and "FogofWarClick" in [n for _c, n in mt] and not any(n in NEW_METHODS for _c, n in mt)
    mt2 = [((labels["fog_click"] if n == "FogofWarClick" else c), n) for c, n in mt]
    mt2 += [(labels["prune_heroes"], "PruneHeroesClick"), (labels["prune_items"], "PruneItemsClick")]
    mtb = emit_method_table(mt2)
    ft, ctab, ft_len = read_field_table(d, va2off(P, FT_ORIG))
    assert len(ft) == FT_ORIG_COUNT and max(o for o, _c, _n in ft) < INSTSIZE_ORIG
    ci_btn = struct.unpack_from("<I", d, va2off(P, ctab) + 2 + 4 * CI_SPEEDBUTTON)[0]
    assert ci_btn == 0x432BE4, "class table index %d is %#x, not Buttons..TSpeedButton" % (CI_SPEEDBUTTON, ci_btn)
    assert emit_field_table(ft, ctab) == bytes(d[va2off(P, FT_ORIG):va2off(P, FT_ORIG) + ft_len]), "field table does not round-trip"
    ft2 = ft + [(F_FOGBTN, CI_SPEEDBUTTON, "FogBtn"), (F_PHBTN, CI_SPEEDBUTTON, "PruneHeroesBtn"), (F_PIBTN, CI_SPEEDBUTTON, "PruneItemsBtn")]
    ftb = emit_field_table(ft2, ctab)
    dfm_off = va2off(P, BASE + DFM_RVA)
    dfm = build_dfm(bytes(d[dfm_off:dfm_off + DFM_SIZE]))
    assert len(ftb) <= OFF_METHODS - OFF_FIELDS and len(mtb) <= OFF_DFM - OFF_METHODS
    sec = bytearray(OFF_DFM + len(dfm))
    sec[:len(code)] = code
    sec[OFF_FIELDS:OFF_FIELDS + len(ftb)] = ftb
    sec[OFF_METHODS:OFF_METHODS + len(mtb)] = mtb
    sec[OFF_DFM:] = dfm
    sec_size = (len(sec) + 0x1FF) & ~0x1FF
    sec += bytes(sec_size - len(sec))

    print("base: %s (%d B) | %s @%#x: %d B (code %d + data %d | fields %d B | methods %d B | DFM %d B, +%d)" % (
        src, len(base), SEC_NAME.decode(), SEC_VA, sec_size, code_len, len(code) - code_len, len(ftb), len(mtb), len(dfm), len(dfm) - DFM_SIZE))
    print("caves: " + ", ".join("%s=%#x" % (k, v) for k, v in labels.items()))
    print("validation-centring hook (.vgo): %s" % ("yes" if have_vgo else "SKIPPED - .vgo cave not found"))
    if args.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        byva = {v: k for k, v in labels.items()}
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code[:code_len], SEC_VA):
            if i.address in byva:
                print("    %s:" % byva[i.address])
            print("      %08X  %-22s %-6s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))

    # ---- lay it down (in memory)
    pad = (-len(d)) % 0x200
    d += bytes(pad)
    rawoff = len(d)
    d += sec
    hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", sec_size, SEC_VA - BASE, sec_size, rawoff, 0, 0, 0, 0, SEC_CHARS)
    struct.pack_into("<40s", d, P["sec0"] + 40 * P["nsec"], hdr)
    struct.pack_into("<H", d, P["e"] + 6, P["nsec"] + 1)
    struct.pack_into("<I", d, P["e"] + 24 + 56, SEC_VA - BASE + sec_size)
    struct.pack_into("<I", d, va2off(P, VMT_MAINFORM - 0x28), SEC_VA + OFF_METHODS)
    struct.pack_into("<I", d, va2off(P, VMT_MAINFORM - 0x2C), SEC_VA + OFF_FIELDS)
    struct.pack_into("<I", d, va2off(P, VMT_MAINFORM - 0x1C), INSTSIZE_NEW)
    struct.pack_into("<II", d, RES_ENTRY_FO, SEC_VA + OFF_DFM - BASE, len(dfm))
    for va, old in (HOOK_EN_CLOSE, HOOK_EN_OPEN):
        o = va2off(P, va)
        d[o:o + len(old)] = call5(va, labels["enable_hook"]) + b"\x90" * (len(old) - 5)
    for (va, old, _exit), lab in ((HOOK_GOTO_ITEM, "goto_item"), (HOOK_GOTO_HERO, "goto_hero")):
        o = va2off(P, va)
        d[o:o + len(old)] = call5(va, labels[lab]) + b"\x90" * (len(old) - 5)
    if have_vgo:
        o = va2off(P, HOOK_VGO[0])
        d[o:o + 5] = call5(HOOK_VGO[0], labels["vcenter"])
    out = bytes(d)

    # ---- post-conditions on the image
    P2 = pe_info(out)
    assert P2["nsec"] == P["nsec"] + 1 and P2["secs"][-1]["name"] == SEC_NAME
    mt3, _ = read_method_table(out, va2off(P2, SEC_VA + OFF_METHODS))
    assert mt3[-2:] == [(labels["prune_heroes"], "PruneHeroesClick"), (labels["prune_items"], "PruneItemsClick")]
    assert dict((n, c) for c, n in mt3)["FogofWarClick"] == labels["fog_click"]
    ft3, ctab3, _ = read_field_table(out, va2off(P2, SEC_VA + OFF_FIELDS))
    assert ft3[-3:] == ft2[-3:] and ctab3 == ctab
    root = DfmParser(out[va2off(P2, SEC_VA + OFF_DFM):va2off(P2, SEC_VA + OFF_DFM) + len(dfm)]).obj(4)
    assert root["end"] == len(dfm)
    methods = {n for _c, n in mt3}
    for nm in ("FogBtn", "PruneHeroesBtn", "PruneItemsBtn", "PruneHeroesItem", "PruneItemsItem"):
        node = find_node(root, nm)
        vs, ve = node["props"]["OnClick"]
        handler = dfm[vs + 2:ve].decode("latin1")
        assert handler in methods, "%s.OnClick=%s would not resolve" % (nm, handler)

    if out == cur:
        print("ALL ALREADY PATCHED"); return 0
    if not args.apply:
        print("\nDry run OK (%s -> %d B). Re-run with --apply to write." % (src, len(out))); return 0
    if not os.path.exists(bak):
        shutil.copyfile(exe, bak); print("Backup: %s" % bak)
    tmp = exe + ".tmp_prune"
    open(tmp, "wb").write(out)
    os.replace(tmp, exe)
    print("AoWDevX.exe patched (%d B).  UNTESTED until the editor is launched." % len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
