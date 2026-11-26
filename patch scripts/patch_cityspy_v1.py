"""
CITY SPY (spell 229, Cosmos sphere 0, tier 2) - engine half.  AoWEPACK.dll + AoWx.exe.   v2 (2026-10-18)

Spec (user): global spell, city enchantment, research 80, cost 15, upkeep 2: "reveals city income, upgrade level,
status and production".
v2 (user 10/18): "I don't want to be able to 'enter' the city.  I want the STRUCTURE PANEL (right side, above the event
log, when the city is clicked on the overworld) to show the revealed info as it does for own cities"; the eye: fade in,
look left slowly, hold, look right slowly, hold, centre, fade out, pause, repeat; the eye VISIBLE FOR EVERYONE.

Spell object = a TGoldRush clone (patch_dual_sphere_spells_v1.py entry 229): city enchantment TYPE 5 ([spell+0x3C] := 5
-> TCity.ActivateEnchantment 0x557A9968 sets [city+0x5C] |= 0x20; types 0..4 are taken: Fountain / Gold Rush / shell /
Warmonger / Arms Race 375), target flags [spell+0x38] := 2 (only cities NOT owned by the caster - allied cities
included; vanilla Town Quake 71 / Anarchy 72 use the same 2).  The enchantment object City.TCityEnchantment (in the
city's TGlobalEnchantmentList [city+0x58]: inner TList [list+8], items +4, count +8) carries the type at +0x24 and the
CASTER (player index, same space as the city owner [city+0x30] and AoWHSMap viewing player [map+0xA5]) at +0x19.

THE STRUCTURE PANEL = AoWx.exe TIWindow (VMT 0x441930, instance [[0x45A5C4]]; fields InfoWin 0x44 .. MainBtn 0x58 ..
CityPanel 0x9C .. NotYoursPnl 0xD8 .. RazePnl 0x10C .. CityIncomeLbl 0x120 .. ActiveCityActionMemo 0x140 ..).
TMapEvents.TheMapStructureSelected 0x45001C -> TIWindow.ShowStructure 0x443F88: a TPlayerStructure owned by the
viewer ([s+0x30] == [[AoWHSMap]+0xA5] @0x443FE6) - or the debug flag [[0x45DF74]+0x6C] - takes the OWN path
(a TCity: ShowOwnCity 0x443318 = race, level, income, civil status, current production, race-relation icon, MainBtn
'City' (opens the city screen, MainBtnClick 0x442328 has no owner test) and the raze panel); any other owner takes the
FOREIGN path 0x444116 (ShowForeignStructure 0x443DD4: name, owner, 'not yours' memo).
AoWx.exe (zone .xedt 0x62F800..0x62FB00, zero + unreferenced; exe never rebases: DllCharacteristics 0):
  PS  0x443FE6 (8 B `cmp al,[edx+0xA5] / je 0x443FFF`) -> own as before; a FOREIGN TCity carrying the viewer's City Spy
      -> the own path too; everything else -> the foreign path 0x443FEE (the vanilla debug-flag test).
  PF  0x444028 (5 B `call ShowOwnCity`) -> calls ShowOwnCity, then for a FOREIGN spied city hides MainBtn (no way into
      the city screen) and RazePnl, and restores [[0x45A420]+0xB0] (ShowOwnCity makes the shown city the general's
      'current city'; a foreign city must never become it).  Own cities / the debug path: vanilla.
  spychk(ecx = city) -> al: an enchantment of type 5 cast by the viewing player [[ [0x45DF7C] ]+0xA5] in the list.
  v1's city-screen hooks (CL 0x4501DE double-click open, RF 0x43B1EB refresh, the 8 read-only method-table stubs) are
  GONE in v2 - an in-place upgrade restores their vanilla bytes from the v1 zone first.
AoWEPACK.dll (zone 0x5587E000..0x5587E800, zero + reloc-free; PIC call/pop delta, rebase-safe):
  GN  TCityEnchantment.GetName 0x557AE35C: type 5 -> "City Spy" (chained in front of patch_forge_arms_v1 hook E).
  LE  ListEnhancementsInfo epilogue 0x557A9C27: bit 0x20 -> adds "City Spy Enchantment" (in front of
      patch_city_enchant_ui_v1 hook A).
  OV  TCityOverlayHS.Show 0x557A920A: bit 0x20 -> spell 229 gfx slot 1 (the watching eye) above the city for EVERY
      viewer (v2).  Frame = REAL TIME (KUSER InterruptTime / 1 000 000 = 0.1 s steps) mod the slot's list length -
      never the map tick or ShowLooped (draw-count independent: the shared-kind-4 / Wall of Flames lesson).  The slot
      list encodes the whole look-around timeline with repeated image ids (fade in / hold / left / hold / right /
      hold / centre / fade out / hidden pause), so the art holds only the unique frames.
  MV  TCity.MakeVisible call 0x557AA908: the overlay HS joins the scene for a city carrying bit 0x20 whose bits are all
      outside the vanilla overlay mask (the eye would never be drawn otherwise) - every viewer (v2), never twice (plague
      case of city_enchant_ui hook D respected).
LIFO: while applied, patch_forge_arms_v1 (hook E), patch_city_enchant_ui_v1 (hooks A/B/D) see their sites taken ->
revert this first, re-run them, re-apply.  --revert restores the pre-City-Spy bytes exactly from either v1 or v2
(refuses if a site no longer points at us).  Backups <game>\\backup\\AoWEPACK.dll.bak_cityspy2 / AoWx.exe.bak_cityspy2
(the state before this v2 run; v1's .bak_cityspy is left alone).
v3 2026-10-18 (user: eye missing frames / side-to-side too slow / glow looked worse / 2 s pause): only EYE_STEP changes
(0.1 s -> 35 ms per slot-list entry; the 183-entry list + the v1-look ALPHA 258 art live in the pipeline / fx builder);
AoWEPACK zone tag CSPY 3 (v2 zones upgrade in place, exact revert as before; backup .bak_cityspy3).
v4 2026-10-18 (user: "I want to be granted the city's VISION if it has City Spy on it"; the eye opens/closes - art only):
three more AoWEPACK hooks (zone header +0x90/+0x98/+0xA0 hold their originals, code moves to +0xB0):
  UV  TPlayerStructure.UpdateUnfog (TCity VMT+0x204) 0x55761263 (6 B `je 0x55761291 / movsx edx,[ebx+0x30]`): vanilla
      grants the viewer [map+0xA5] the structure's sight when it owns it (je) or is allied (relation 2); a TCity
      (IsClass 0x557010C0 vs [0x557A73B0]) carrying a type-5 enchantment CAST BY THE VIEWER now takes the owner path
      too -> radius = VMT+0x200 sight, unfog + explore through the LOS-filtered fills, cached at +0x38 (fog-off later
      uses the same cache: refcounts stay symmetric).  Every UpdateVisibility / seat change / new-turn rebuild
      re-evaluates it (the LOS patch's broadcast), so vision follows the viewing player in hotseat as well.
  ACT TCity.ActivateEnchantment 0x557A99B5 (6 B `cmp byte [ebx+0x24],2 / jne`): type 5 -> city VMT+0x204 (UpdateUnfog)
      right after the enchantment joined the list + the bits were set -> vision on cast.
  DEA TCity.DeactivateEnchantment 0x557A99E8 (6 B `cmp byte [ebx+0x24],1 / jne`): type 5 -> VMT+0x204 after the
      enchantment left the list + the bits were recalculated -> vision removed when it ends / is dispelled.
  Both calls are skipped while the AoWHSMap global [0x558FA040] is nil.  Vision is the local viewer's display state
  (fog counts / explored bits of [map+0xA5]) - nothing synced changes -> MP-safe.
AoWEPACK zone tag CSPY 4 (v1/v2/v3 zones upgrade in place; their new sites must still be vanilla); backup .bak_cityspy4.
Dry-run default; --apply / --revert / --dis; --dll / --exe for scratch copies.
"""
import argparse, os, shutil, struct, sys
import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SUF = ".bak_cityspy4"                    # v4 10/18 (v3 kept .bak_cityspy3, v2 .bak_cityspy2)
SPELL_ID, ENCH_TYPE, ENCH_BIT = 229, 5, 0x20
# ---------------------------------------------------------------- AoWEPACK
D_BASE, D_V2F = 0x55700000, 0x55700C00
DZ, DZ_END = 0x5587E000, 0x5587E800
GN_SITE, GN_VAN, GN_RESUME = 0x557AE35C, bytes.fromhex("53568bf28bd8"), 0x557AE362
LE_SITE, LE_VAN, LE_RESUME = 0x557A9C27, bytes.fromhex("33c05a5959648910"), 0x557A9C2F
OV_SITE, OV_VAN, OV_RESUME, OV_EXIT = 0x557A920A, bytes.fromhex("8b4e0c807964000f84f3020000"), 0x557A9217, 0x557A950A
MV_SITE, MV_VAN_CALLEE, MASKBYTE = 0x557AA908, 0x5570219C, 0x557AA930
INF_EXPORT = 0x5582BFF0                  # patch_blesseddew_v1 v4 plague test (esi = city -> al); used only if hook D is present
LSTR_ASG, GETSPELL, GETIMAGESEQ, IMAGEEXIST, LIBGET = 0x55701150, 0x55779AC8, 0x557028E4, 0x55702944, 0x55702934
AOWHSMAP, AOWHSSET, SC_OFF = 0x558FA040, 0x558FA044, 0x84
EYE_SLOT = 1
EYE_STEP = 350000                        # v3 10/18: KUSER InterruptTime (100 ns) per timeline step = 35 ms (v2: 0.1 s)
KUSER_LO, KUSER_HI = 0x7FFE0008, 0x7FFE000C
# eye centre per city size 1..4 (hex origin -> just above the Warmonger glow spot (0,-18)/(10,-25)/(-21,-40)/(2,-47) + 16)
EYE_ANCH = [(16, -16), (26, -23), (-5, -38), (18, -45)]
D_GN, D_LE, D_OV, D_MV, D_ANCH, D_LIT1, D_LIT2 = 0x08, 0x10, 0x18, 0x28, 0x30, 0x50, 0x68
D_UV, D_ACT, D_DEA, D_CODE = 0x90, 0x98, 0xA0, 0xB0            # v4: originals of the vision sites; code moved 0x90 -> 0xB0
# v4 vision sites
UV_SITE, UV_VAN, UV_OWN, UV_RESUME = 0x55761263, bytes.fromhex("742c0fbe5330"), 0x55761291, 0x55761269
ACT_SITE, ACT_VAN, ACT_T2, ACT_OUT = 0x557A99B5, bytes.fromhex("807b24027508"), 0x557A99BB, 0x557A99C3
DEA_SITE, DEA_VAN, DEA_T1, DEA_OUT = 0x557A99E8, bytes.fromhex("807b2401750a"), 0x557A99EE, 0x557A99F8
TCITY_CELL, ISCLASS_D, UNFOG_SLOT = 0x557A73B0, 0x557010C0, 0x204
SITES_D = {"gn": GN_SITE, "le": LE_SITE, "ov": OV_SITE, "mv": MV_SITE, "uv": UV_SITE, "act": ACT_SITE, "dea": DEA_SITE}
# ---------------------------------------------------------------- AoWx.exe
X_BASE = 0x400000
XZ, XZ_END = 0x62F800, 0x62FB00
# v1 sites (removed in v2; restored to vanilla on upgrade)
CL_SITE, CL_VAN = 0x4501DE, bytes.fromhex("3a82a50000007518")
RF_SITE, RF_VAN = 0x43B1EB, bytes.fromhex("3a91a5000000740b")
CITYSCREEN_VMT = 0x439F68
RO_NAMES = ("CityBtn1Click", "CityBtn2Click", "CityBtn3Click", "ActivityDoubleClick", "ProductionDoubleClick",
            "LoopQueueBoxChange", "PPrevClick", "PNextClick")
X1_CL, X1_RF, X1_MT = 0x08, 0x10, 0x18                       # v1 zone layout (stored originals)
# v2 sites
PS_SITE, PS_VAN, PS_OWN, PS_FOREIGN = 0x443FE6, bytes.fromhex("3a82a50000007411"), 0x443FFF, 0x443FEE
PF_SITE, PF_VAN = 0x444028, bytes.fromhex("e8ebf2ffff")      # call TIWindow.ShowOwnCity 0x443318
SHOWOWNCITY = 0x443318
IAT_MAP = 0x45DF7C                        # AoWx.exe import slot of AoWE.AoWHSMap (loader-filled -> [[slot]] = the map)
CITY_CLS = 0x45E55C                       # AoWx.exe import slot -> TCity class reference
GENERAL = 0x45A420                        # [[.]] = TGeneral ([+0xB0] = the 'current city')
ISCLASS = 0x401070                        # System.@IsClass(eax = obj, edx = class) -> al
IW_MAINBTN, IW_RAZEPNL, SETVIS = 0x58, 0x10C, 0x6C
X_PS, X_PF, X_CODE = 0x08, 0x10, 0x40
D_MAGIC1, X_MAGIC1 = b"CSPY\x01\x00\x00\x00", b"CSPX\x01\x00\x00\x00"
D_MAGIC2 = b"CSPY\x02\x00\x00\x00"                     # v2 AoWEPACK zone (same layout as v3; only EYE_STEP differs)
D_MAGIC3 = b"CSPY\x03\x00\x00\x00"                     # v3 AoWEPACK zone (originals to +0x90, code at +0x90)
D_MAGIC, X_MAGIC = b"CSPY\x04\x00\x00\x00", b"CSPX\x02\x00\x00\x00"   # v4: AoWEPACK zone tag 4, exe zone unchanged (v2)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005b81ebffffff7f")


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def asm_delta(src, va):
    """`call $D / pop ebx / sub ebx, $D` PIC idiom, every anchor patched with its own VA."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = b.find(ANCHOR); assert k >= 0
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); k = b.find(ANCHOR, k + 12)
    return bytes(b)


def delphi_literal(s):
    b = s.encode("latin1"); return struct.pack("<iI", -1, len(b)) + b + b"\0"


def rel_target(site, b):
    return (site + 5 + struct.unpack_from("<i", b, 1)[0]) & 0xFFFFFFFF


# ---------------------------------------------------------------- AoWEPACK caves
def d_tail(kind, prev):
    """Source that continues where the hooked site would have gone (previous owner's cave or the vanilla bytes)."""
    if kind == "gn":
        if prev[0] == 0xE9: return "jmp %#x" % rel_target(GN_SITE, prev)
        assert prev == GN_VAN, "GetName site: unexpected bytes %s" % prev.hex()
        return "push ebx\npush esi\nmov esi, edx\nmov ebx, eax\njmp %#x" % GN_RESUME
    if kind == "le":
        if prev[0] == 0xE9: return "jmp %#x" % rel_target(LE_SITE, prev)
        assert prev == LE_VAN, "ListEnhancementsInfo site: unexpected bytes %s" % prev.hex()
        return "xor eax, eax\npop edx\npop ecx\npop ecx\nmov dword ptr fs:[eax], edx\njmp %#x" % LE_RESUME
    if kind == "ov":
        if prev[0] == 0xE9: return "jmp %#x" % rel_target(OV_SITE, prev)
        assert prev == OV_VAN, "overlay Show site: unexpected bytes %s" % prev.hex()
        return "mov ecx, [esi+0xc]\ncmp byte ptr [ecx+0x64], 0\nje %#x\njmp %#x" % (OV_EXIT, OV_RESUME)
    if kind == "uv":                                       # flags = cmp al, [ebx+0x30] (not equal here)
        if prev[0] == 0xE9: return "jmp %#x" % rel_target(UV_SITE, prev)
        assert prev == UV_VAN, "UpdateUnfog site: unexpected bytes %s" % prev.hex()
        return "movsx edx, byte ptr [ebx+0x30]\njmp %#x" % UV_RESUME
    if kind == "act":
        if prev[0] == 0xE9: return "jmp %#x" % rel_target(ACT_SITE, prev)
        assert prev == ACT_VAN, "ActivateEnchantment site: unexpected bytes %s" % prev.hex()
        return "cmp byte ptr [ebx+0x24], 2\njne %#x\njmp %#x" % (ACT_OUT, ACT_T2)
    if kind == "dea":
        if prev[0] == 0xE9: return "jmp %#x" % rel_target(DEA_SITE, prev)
        assert prev == DEA_VAN, "DeactivateEnchantment site: unexpected bytes %s" % prev.hex()
        return "cmp byte ptr [ebx+0x24], 1\njne %#x\njmp %#x" % (DEA_OUT, DEA_T1)
    raise ValueError(kind)


def build_dzone(prev, inf_ok):
    """prev = dict gn/le/ov/mv -> the site bytes before us.  inf_ok: hook D (plague) present -> respect its overlay add."""
    z = bytearray(DZ_END - DZ); z[0:8] = D_MAGIC
    z[D_GN:D_GN + 6] = prev["gn"]; z[D_LE:D_LE + 8] = prev["le"]; z[D_OV:D_OV + 13] = prev["ov"]; z[D_MV:D_MV + 5] = prev["mv"]
    z[D_UV:D_UV + 6] = prev["uv"]; z[D_ACT:D_ACT + 6] = prev["act"]; z[D_DEA:D_DEA + 6] = prev["dea"]
    for i, (x, y) in enumerate(EYE_ANCH): struct.pack_into("<ii", z, D_ANCH + 8 * i, x, y)
    l1, l2 = delphi_literal("City Spy"), delphi_literal("City Spy Enchantment")
    z[D_LIT1:D_LIT1 + len(l1)] = l1; z[D_LIT2:D_LIT2 + len(l2)] = l2
    mv_callee = rel_target(MV_SITE, prev["mv"]); assert prev["mv"][0] == 0xE8
    plague = mv_callee != MV_VAN_CALLEE and inf_ok
    P = dict(t=ENCH_TYPE, bit=ENCH_BIT, lit1=DZ + D_LIT1 + 8, lit2=DZ + D_LIT2 + 8, asg=LSTR_ASG, map=AOWHSMAP, set=AOWHSSET,
             sc=SC_OFF, spell=SPELL_ID, getspell=GETSPELL, getseq=GETIMAGESEQ, slot=EYE_SLOT, anch=DZ + D_ANCH, anch4=DZ + D_ANCH + 4,
             exist=IMAGEEXIST, get=LIBGET, step=EYE_STEP, klo=KUSER_LO, khi=KUSER_HI, mask=MASKBYTE, callee=mv_callee, infx=INF_EXPORT,
             own=UV_OWN, cell=TCITY_CELL, isclass=ISCLASS_D, unfog=UNFOG_SLOT)
    where = {}; code = bytearray(); va = DZ + D_CODE

    def place(name, src, delta=True):
        nonlocal va
        b = asm_delta(src, va) if delta and "$D" in src else asm(src, va)
        where[name] = va; code.extend(b); va += len(b)
        while va % 16: code.append(0xCC); va += 1

    # pdraw(eax = seq; stack: x, y, step, surface; ret 0x10) - entry = step mod n (the list holds the timeline), image Draw
    place("pdraw", """
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, [esi+0x1c]
        mov ecx, [edi+8]
        test ecx, ecx
        jz pd_done
        mov eax, [ebp+0x10]
        xor edx, edx
        div ecx
        mov eax, [edi+4]
        mov edx, [eax+edx*4]
        mov edi, edx
        mov eax, [esi+0x10]
        call %(exist)#x
        test al, al
        jz pd_done
        push dword ptr [ebp+0x14]
        mov edx, edi
        mov eax, [esi+0x10]
        call %(get)#x
        mov ecx, [ebp+0xc]
        add ecx, [esi+0x28]
        mov edx, [ebp+8]
        add edx, [esi+0x24]
        mov ebx, [eax]
        call dword ptr [ebx+0x84]
    pd_done:
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10
    """ % P, delta=False)
    P["pdraw"] = where["pdraw"]
    place("gn", """
        cmp byte ptr [eax+0x24], %(t)d
        jne gn_prev
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, edx
        lea edx, [ebx+%(lit1)#x]
        pop ebx
        jmp %(asg)#x
    gn_prev:
    """ % P + d_tail("gn", prev["gn"]))
    place("le", """
        test byte ptr [ebx+0x5c], %(bit)d
        jz le_prev
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        lea eax, [ebp-4]
        lea edx, [ebx+%(lit2)#x]
        call %(asg)#x
        pop ebx
        mov edx, [ebp-4]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x34]
    le_prev:
    """ % P + d_tail("le", prev["le"]))
    # ov: every viewer (v2); real-time step = InterruptTime / EYE_STEP (two-step 64-bit divide, never overflows)
    place("ov", """
        mov ecx, [esi+0xc]
        cmp byte ptr [ecx+0x64], 0
        je ov_prev
        test byte ptr [ecx+0x5c], %(bit)d
        jz ov_prev
        pushal
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(set)#x]
        test eax, eax
        jz ov_out
        mov eax, [eax+%(sc)#x]
        mov edx, %(spell)d
        call %(getspell)#x
        test eax, eax
        jz ov_out
        mov eax, [eax+0x2c]
        test eax, eax
        jz ov_out
        mov edx, %(slot)d
        call %(getseq)#x
        test eax, eax
        jz ov_out
        mov edi, eax
        mov ecx, [esi+0xc]
        mov edx, [ecx+8]
        movzx edx, byte ptr [edx+0x78]
        dec edx
        cmp edx, 3
        jbe ov_sz
        xor edx, edx
    ov_sz:
        push dword ptr [ebp+8]
        push edx
        mov ecx, %(step)d
        mov eax, dword ptr [%(khi)#x]
        xor edx, edx
        div ecx
        mov eax, dword ptr [%(klo)#x]
        div ecx
        pop edx
        push eax
        mov eax, [ebx+edx*8+%(anch4)#x]
        add eax, [ebp-8]
        push eax
        mov eax, [ebx+edx*8+%(anch)#x]
        add eax, [ebp-4]
        push eax
        mov eax, edi
        call %(pdraw)#x
    ov_out:
        popal
    ov_prev:
    """ % P + d_tail("ov", prev["ov"]))
    plague_src = """
        push esi
        mov esi, ebx
        call %(infx)#x
        pop esi
        test al, al
        jnz mv_out
    """ % P if plague else ""
    place("mv", """
        call %(callee)#x
        push edi
        push ebx
        test byte ptr [ebx+0x5c], %(bit)d
        jz mv_out
        call $D
        pop ebx
        sub ebx, $D
        mov al, byte ptr [ebx+%(mask)#x]
        mov ebx, [esp]
        and al, byte ptr [ebx+0x5c]
        jnz mv_out
    """ % P + plague_src + """
        mov eax, [ebx+0x60]
        test eax, eax
        jz mv_out
        mov edx, esi
        mov ecx, [eax]
        call dword ptr [ecx+0xf0]
    mv_out:
        pop ebx
        pop edi
        ret
    """ % P)
    # v4 uv: entered from UpdateUnfog 0x55761263 with the flags of `cmp al, [ebx+0x30]` (al = viewer, ebx = structure).
    # owner -> vanilla own path; a TCity carrying a City Spy cast by the viewer -> the own path too; else vanilla.
    place("uv", """
        je uv_own
        pushal
        movzx edi, al
        mov esi, ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, esi
        mov edx, [ebx+%(cell)#x]
        call %(isclass)#x
        test al, al
        jz uv_no
        mov ecx, [esi+0x58]
        test ecx, ecx
        jz uv_no
        mov ecx, [ecx+8]
        test ecx, ecx
        jz uv_no
        mov edx, [ecx+8]
        mov ecx, [ecx+4]
        test ecx, ecx
        jz uv_no
    uv_loop:
        dec edx
        js uv_no
        mov eax, [ecx+edx*4]
        test eax, eax
        jz uv_loop
        cmp byte ptr [eax+0x24], %(t)d
        jne uv_loop
        movzx eax, byte ptr [eax+0x19]
        cmp eax, edi
        jne uv_loop
        popal
    uv_own:
        jmp %(own)#x
    uv_no:
        popal
    """ % P + d_tail("uv", prev["uv"]))
    # v4 act / dea (esi = city, ebx = the enchantment): a City Spy came / went -> the city's UpdateUnfog (VMT+0x204)
    for nm in ("act", "dea"):
        place(nm, """
        cmp byte ptr [ebx+0x24], %(t)d
        jne %(nm)s_prev
        pushal
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz %(nm)s_skip
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+%(unfog)#x]
    %(nm)s_skip:
        popal
    %(nm)s_prev:
    """ % dict(P, nm=nm) + d_tail(nm, prev[nm]))
    assert DZ + D_CODE + len(code) <= DZ_END, "AoWEPACK zone overflow"
    z[D_CODE:D_CODE + len(code)] = code
    return bytes(z), where, plague


# ---------------------------------------------------------------- AoWx.exe caves
def build_xzone(prev_ps, prev_pf):
    z = bytearray(XZ_END - XZ); z[0:8] = X_MAGIC
    z[X_PS:X_PS + 8] = prev_ps; z[X_PF:X_PF + 5] = prev_pf
    assert prev_ps == PS_VAN and prev_pf == PF_VAN, "exe panel sites not vanilla before us"
    where = {}; code = bytearray(); va = XZ + X_CODE
    P = dict(t=ENCH_TYPE, iat=IAT_MAP, cls=CITY_CLS, isclass=ISCLASS, own=PS_OWN, foreign=PS_FOREIGN, gen=GENERAL,
             show=SHOWOWNCITY, mb=IW_MAINBTN, rz=IW_RAZEPNL, vis=SETVIS)

    def place(name, src):
        nonlocal va
        b = asm(src, va); where[name] = va; code.extend(b); va += len(b)
        while va % 16: code.append(0xCC); va += 1

    # spychk(ecx = city) -> al; keeps every other register
    place("spychk", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        xor eax, eax
        test ecx, ecx
        jz x_out
        mov ebx, dword ptr [%(iat)#x]
        test ebx, ebx
        jz x_out
        mov ebx, [ebx]
        test ebx, ebx
        jz x_out
        movzx edi, byte ptr [ebx+0xa5]
        mov esi, [ecx+0x58]
        test esi, esi
        jz x_out
        mov esi, [esi+8]
        test esi, esi
        jz x_out
        mov ebx, [esi+8]
        mov esi, [esi+4]
        test esi, esi
        jz x_out
    x_loop:
        dec ebx
        js x_no
        mov edx, [esi+ebx*4]
        test edx, edx
        jz x_loop
        cmp byte ptr [edx+0x24], %(t)d
        jne x_loop
        movzx edx, byte ptr [edx+0x19]
        cmp edx, edi
        jne x_loop
        mov al, 1
        jmp x_out
    x_no:
        xor eax, eax
    x_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % P)
    P["spychk"] = where["spychk"]
    # PS (al = owner, edx = map, ebx = edi = structure, esi = panel): own -> own path; a foreign TCity with the viewer's
    # City Spy -> own path; else the vanilla foreign / debug-flag test
    place("ps", """
        cmp al, byte ptr [edx+0xa5]
        je ps_own
        push eax
        push ecx
        push edx
        mov eax, ebx
        mov edx, dword ptr [%(cls)#x]
        call %(isclass)#x
        test al, al
        jz ps_no
        mov ecx, ebx
        call %(spychk)#x
        test al, al
        jz ps_no
        pop edx
        pop ecx
        pop eax
    ps_own:
        jmp %(own)#x
    ps_no:
        pop edx
        pop ecx
        pop eax
        jmp %(foreign)#x
    """ % P)
    # PF (called instead of ShowOwnCity; eax = panel, edx = city): show it, then for a foreign spied city hide MainBtn +
    # RazePnl and give the general back its previous 'current city'
    place("pf", """
        push ebx
        push esi
        mov esi, eax
        mov ebx, edx
        mov ecx, dword ptr [%(gen)#x]
        mov ecx, [ecx]
        push dword ptr [ecx+0xb0]
        call %(show)#x
        mov ecx, dword ptr [%(iat)#x]
        mov ecx, [ecx]
        mov al, byte ptr [ebx+0x30]
        cmp al, byte ptr [ecx+0xa5]
        je pf_keep
        mov ecx, ebx
        call %(spychk)#x
        test al, al
        jz pf_keep
        mov eax, [esi+%(mb)#x]
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx+%(vis)#x]
        mov eax, [esi+%(rz)#x]
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx+%(vis)#x]
        mov ecx, dword ptr [%(gen)#x]
        mov ecx, [ecx]
        pop dword ptr [ecx+0xb0]
        jmp pf_out
    pf_keep:
        add esp, 4
    pf_out:
        pop esi
        pop ebx
        ret
    """ % P)
    assert XZ + X_CODE + len(code) <= XZ_END, "exe zone overflow"
    z[X_CODE:X_CODE + len(code)] = code
    return bytes(z), where


# ---------------------------------------------------------------- file plumbing
def relocs(pe):
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    b = pe.OPTIONAL_HEADER.ImageBase; s = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type: s.add(b + e.rva)
    return s


def method_table(pe, data):
    b = pe.OPTIONAL_HEADER.ImageBase
    def off(va): return pe.get_offset_from_rva(va - b)
    mt = struct.unpack_from("<I", data, off(CITYSCREEN_VMT - 0x28))[0]
    o = off(mt); cnt = struct.unpack_from("<H", data, o)[0]; p = o + 2; ent = {}
    for _ in range(cnt):
        sz = struct.unpack_from("<H", data, p)[0]; n = data[p + 6]; nm = data[p + 7:p + 7 + n].decode("latin1")
        ent[nm] = mt + (p - o) + 2                          # VA of the entry's code-address dword
        p += sz
    return [ent[n] for n in RO_NAMES]


def main():
    ap = argparse.ArgumentParser(); g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true"); g.add_argument("--revert", action="store_true"); g.add_argument("--dis", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWEPACK.dll")); ap.add_argument("--exe", default=game_file("AoWx.exe"))
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    xpe = pefile.PE(a.exe, fast_load=True); x = bytearray(open(a.exe, "rb").read())
    drl, xrl = relocs(pefile.PE(a.dll)), relocs(pefile.PE(a.exe))
    dof = lambda va: va - D_V2F
    xof = lambda va: xpe.get_offset_from_rva(va - X_BASE)
    # ---- reloc / zone checks
    bad = [hex(r) for r in drl if DZ <= r < DZ_END or any(s - 3 < r < s + n for s, n in ((GN_SITE, 6), (LE_SITE, 8), (OV_SITE, 13), (MV_SITE, 5),
                                                                                      (UV_SITE, 6), (ACT_SITE, 6), (DEA_SITE, 6)))]
    bad += [hex(r) for r in xrl if XZ <= r < XZ_END or any(s - 3 < r < s + n for s, n in ((PS_SITE, 8), (PF_SITE, 5), (CL_SITE, 8), (RF_SITE, 8)))]
    if bad: print("ABORT: relocs in a zone / site:", bad); return 1
    dzone = bytes(d[dof(DZ):dof(DZ_END)]); xzone = bytes(x[xof(XZ):xof(XZ_END)])
    live = {"gn": bytes(d[dof(GN_SITE):dof(GN_SITE) + 6]), "le": bytes(d[dof(LE_SITE):dof(LE_SITE) + 8]),
            "ov": bytes(d[dof(OV_SITE):dof(OV_SITE) + 13]), "mv": bytes(d[dof(MV_SITE):dof(MV_SITE) + 5]),
            "uv": bytes(d[dof(UV_SITE):dof(UV_SITE) + 6]), "act": bytes(d[dof(ACT_SITE):dof(ACT_SITE) + 6]),
            "dea": bytes(d[dof(DEA_SITE):dof(DEA_SITE) + 6])}
    mt_va = method_table(xpe, x)
    d_ver = {D_MAGIC: 4, D_MAGIC3: 3, D_MAGIC2: 2, D_MAGIC1: 1}.get(dzone[:8], 0)
    x_ver = 2 if xzone[:8] == X_MAGIC else (1 if xzone[:8] == X_MAGIC1 else 0)
    if not d_ver and any(dzone): print("ABORT: AoWEPACK zone %#x not free" % DZ); return 1
    if not x_ver and any(xzone): print("ABORT: exe zone %#x not free" % XZ); return 1
    prev = ({"gn": dzone[D_GN:D_GN + 6], "le": dzone[D_LE:D_LE + 8], "ov": dzone[D_OV:D_OV + 13], "mv": dzone[D_MV:D_MV + 5]}
            if d_ver else dict(live))
    if d_ver == 4:                                         # v4 zone: the vision sites' originals are stored too
        prev.update(uv=dzone[D_UV:D_UV + 6], act=dzone[D_ACT:D_ACT + 6], dea=dzone[D_DEA:D_DEA + 6])
    else:                                                  # zero / v1-v3 zone: the vision sites are still the live bytes
        prev.update(uv=live["uv"], act=live["act"], dea=live["dea"])
    # ---- exe: the v1 city-screen hooks -> their vanilla bytes (v2 does not use them)
    v1_fix = []                                            # (file offset, bytes) that put the v1 sites back to vanilla
    if x_ver == 1:
        v1_cl, v1_rf = xzone[X1_CL:X1_CL + 8], xzone[X1_RF:X1_RF + 8]
        v1_mt = [struct.unpack_from("<I", xzone, X1_MT + 4 * i)[0] for i in range(len(RO_NAMES))]
        if v1_cl != CL_VAN or v1_rf != RF_VAN: print("ABORT: v1 zone holds unexpected originals"); return 1
        v1_fix = [(xof(CL_SITE), v1_cl), (xof(RF_SITE), v1_rf)] + [(xof(v), struct.pack("<I", o)) for v, o in zip(mt_va, v1_mt)]
    live_ps, live_pf = bytes(x[xof(PS_SITE):xof(PS_SITE) + 8]), bytes(x[xof(PF_SITE):xof(PF_SITE) + 5])
    if x_ver == 2:
        prev_ps, prev_pf = xzone[X_PS:X_PS + 8], xzone[X_PF:X_PF + 5]
    else:
        prev_ps, prev_pf = live_ps, live_pf
    inf_ok = d[dof(INF_EXPORT)] == 0xE9
    try:
        dz_new, dwhere, plague = build_dzone(prev, inf_ok)
        xz_new, xwhere = build_xzone(prev_ps, prev_pf)
    except (AssertionError, ValueError) as ex:
        print("ABORT:", ex); return 1
    want = {"gn": asm("jmp %#x" % dwhere["gn"], GN_SITE) + b"\x90", "le": asm("jmp %#x" % dwhere["le"], LE_SITE) + b"\x90" * 3,
            "ov": asm("jmp %#x" % dwhere["ov"], OV_SITE) + b"\x90" * 8, "mv": asm("call %#x" % dwhere["mv"], MV_SITE),
            "uv": asm("jmp %#x" % dwhere["uv"], UV_SITE) + b"\x90", "act": asm("jmp %#x" % dwhere["act"], ACT_SITE) + b"\x90",
            "dea": asm("jmp %#x" % dwhere["dea"], DEA_SITE) + b"\x90"}
    want_ps = asm("jmp %#x" % xwhere["ps"], PS_SITE) + b"\x90" * 3
    want_pf = asm("call %#x" % xwhere["pf"], PF_SITE)

    def site_state(k):
        if live[k] == want[k]: return "ours"
        if not d_ver or (d_ver < 4 and k in ("uv", "act", "dea") and live[k] == prev[k]): return "free"
        tgt = rel_target(SITES_D[k], live[k]) if live[k][0] in (0xE8, 0xE9) else 0
        return "ours(old)" if DZ <= tgt < DZ_END else "OTHER"

    def xsite(livev, wantv, van, site):
        if livev == wantv: return "ours"
        if livev == van: return "free"
        if livev[0] in (0xE8, 0xE9) and XZ <= rel_target(site, livev) < XZ_END: return "ours(old)"
        return "OTHER"
    st = {k: site_state(k) for k in live}
    xst = {"ps": xsite(live_ps, want_ps, PS_VAN, PS_SITE), "pf": xsite(live_pf, want_pf, PF_VAN, PF_SITE)}
    if x_ver == 1:
        cl_live, rf_live = bytes(x[xof(CL_SITE):xof(CL_SITE) + 8]), bytes(x[xof(RF_SITE):xof(RF_SITE) + 8])
        xst["v1"] = "ours(v1)" if all(c[0] == 0xE9 and XZ <= rel_target(s, c) < XZ_END for s, c in ((CL_SITE, cl_live), (RF_SITE, rf_live))) else "OTHER"
    print("AoWEPACK zone %s | sites %s | prev gn %s le %s ov %s mv-callee %#x | plague-aware %s" % (
        {0: "zero", 1: "v1", 2: "v2", 3: "v3", 4: "v4"}[d_ver], st, prev["gn"][:5].hex(), prev["le"][:5].hex(), prev["ov"][:5].hex(),
        rel_target(MV_SITE, prev["mv"]), plague))
    print("AoWx.exe zone %s | sites %s | caves %s" % ({0: "zero", 1: "v1", 2: "v2"}[x_ver], xst, {k: hex(v) for k, v in xwhere.items()}))
    print("AoWEPACK caves", {k: hex(v) for k, v in dwhere.items()}, " AoWEPACK %d B, exe %d B" % (
        len(dz_new.rstrip(b"\0")), len(xz_new.rstrip(b"\0"))))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for i in md.disasm(dz_new[D_CODE:], DZ + D_CODE): print("  %08X %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        for i in md.disasm(xz_new[X_CODE:], XZ + X_CODE): print("  %08X %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        return 0
    if a.revert:
        if not d_ver and not x_ver: print("already vanilla"); return 0
        if "OTHER" in st.values() or "OTHER" in xst.values():
            print("ABORT: a site no longer points at us (revert that patch first, LIFO)"); return 1
        if d_ver:
            for k, s in SITES_D.items(): d[dof(s):dof(s) + len(prev[k])] = prev[k]
            d[dof(DZ):dof(DZ_END)] = bytes(DZ_END - DZ)
        if x_ver:
            for o, b in v1_fix: x[o:o + len(b)] = b
            if x_ver == 2:
                x[xof(PS_SITE):xof(PS_SITE) + 8] = prev_ps; x[xof(PF_SITE):xof(PF_SITE) + 5] = prev_pf
            x[xof(XZ):xof(XZ_END)] = bytes(XZ_END - XZ)
        open(a.dll, "r+b").write(d); open(a.exe, "r+b").write(x)
        print("reverted"); return 0
    if "OTHER" in st.values() or "OTHER" in xst.values():
        print("ABORT: a site we need belongs to someone else"); return 1
    if (d_ver == 4 and x_ver == 2 and all(v == "ours" for v in st.values()) and all(v == "ours" for v in xst.values())
            and dzone == dz_new and xzone == xz_new):
        print("already applied (v4)"); return 0
    if not a.apply:
        print("Dry run OK%s - rerun with --apply (or --revert)." % (" - in-place upgrade v%d -> v4" % d_ver if 0 < d_ver < 4 else ""))
        return 0
    for path in (a.dll, a.exe):
        bp = bak_path(path, SUF)
        if not os.path.exists(bp): shutil.copy2(path, bp); print("backup ->", bp)
    d[dof(DZ):dof(DZ_END)] = dz_new
    for k, s in SITES_D.items(): d[dof(s):dof(s) + len(want[k])] = want[k]
    for o, b in v1_fix: x[o:o + len(b)] = b
    x[xof(XZ):xof(XZ_END)] = xz_new
    x[xof(PS_SITE):xof(PS_SITE) + 8] = want_ps; x[xof(PF_SITE):xof(PF_SITE) + 5] = want_pf
    open(a.dll, "r+b").write(d); open(a.exe, "r+b").write(x)
    chk_d, chk_x = open(a.dll, "rb").read(), open(a.exe, "rb").read()
    assert chk_d[dof(DZ):dof(DZ_END)] == dz_new and chk_x[xof(XZ):xof(XZ_END)] == xz_new
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
