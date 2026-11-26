#!/usr/bin/env python3
r"""
!! SUPERSEDED 2026-09-14 by patch_devx_prune_unused_v2.py (same features + toolbar buttons,
   validation centring, site-aware Go-to; DFM/method-table relocation instead of runtime
   menu creation).  Kept for reference; do not apply on top of v2.  Both share the
   pristine backup AoWDevX.exe.bak_prune.

AoWDevX.exe: Developer menu gains two entries (after a separator, under "Remove Leaders"):

    Delete Unused Heroes   - deletes every hero in the open map's roster that is not
                             placed anywhere (Engine.TEObject.Owner == nil) and is not a
                             TLeader.  Port of BXL's build_deved_heroprune.py (2026-09-08).
    Delete Unused Items    - deletes every item in the open map's item registry that no
                             container holds (item[+4] == nil): not in a hero's kit or
                             backpack, not on the ground, not in a site's treasure.

Both ask "Delete N unused heroes/items?" (TMainForm.MsgDlg, Yes/No/Cancel) first, say
"No unused ... to delete." when N is 0, mark the map modified, and bracket the work with
the map-view render pause/resume that TMainForm.DeleteHeroBtnClick uses.

!! GAMEPLAY NOTE.  In the engine, unplaced roster heroes ARE the "hero offers to join"
   pool (TPlayer.MakeHeroEmerge picks heroes with Owner == nil) and unheld registry items
   ARE the random-treasure pool for item hotspots and exploration sites
   (TItemControl.GenerateItem picks items with refcount 1 = registered only).  Pruning a
   map removes those pools from it.

How it is built (fixed-base exe, no reloc needed):
  * New section .xprn @0x4E9000 (last free section-header slot) holds the caves, the
    string literals, the menu-item descriptors and the message buffer.
  * TMainForm's published-method-table entry for FormCreate (OnCreate) is repointed to
    fc_wrap: runs the original FormCreate, then creates a NewLine separator and two
    TMenuItems at runtime (Menus.TMenuItem.Create/SetCaption/Add are already imported)
    with OnClick = the caves (TMenuItem +0x60 code / +0x64 data) and adds them to
    DeveloperItems ([form+0x358]).  No DFM or method-table relocation needed.
  * Heroes: THeroControl.GetCount/GetHero/@IsClass/SetModified thunks, TLeader class ref,
    hero VMT +0x188 (Deactivate) then +0x2C (Release) - exactly RemoveLeadersMIClick's
    per-victim pair, iterated downward and re-fetched after @IsClass.
  * Items: TItemControl (map+0xF4) list walked inline ([ic+8] = TList, +4 array, +8 count),
    each victim goes through AoWE.TItemControl.UnRegisterItem (what the item grid's own
    DeleteItem does: TList.Remove, clear the registered flag, Release, Changed).  The exe
    does not import UnRegisterItem, so it is resolved at run time as
    [IAT TItemControl.RegisterItem] + 0x8C (AoWEPACK.dll rebases at load) and its first
    ten bytes are checked against the known prologue before it is called; a mismatch
    shows a message and deletes nothing.  THSMEdit.DeselectPlaceHS runs first, like the
    grid's Delete button, so an item being placed cannot be freed under the cursor.

Dry-run default; --apply; --revert (restore the backup); --dis (disassemble the caves).
Backup: AoWDevX.exe.bak_prune
Needs: pip install keystone-engine capstone
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_EXE = game_file(r"AoWDevX.exe")
BAK_SUFFIX = ".bak_prune"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x400000
SEC = (b".xprn", 0x4E9000, 0x1000, 0x1000)          # name, VA, virtual size, raw size
SEC_CHARS = 0xE0000060

# ---- exe facts (verified against AoWDevX.exe 2026-09-14; same CODE as BXL's AoWDevEd) ----
VMT_MAINFORM   = 0x425D00
FORMCREATE     = 0x42841C          # TMainForm.FormCreate (published; OnCreate in the DFM)
MSGDLG         = 0x42BBE4          # TMainForm.MsgDlg(eax=Self, edx=str, cl=type; push buttons, push helpctx) ret 8
T_GETCOUNT     = 0x401E60          # AoWE.THeroControl.GetCount (eax=hc)
T_GETHERO      = 0x401E58          # AoWE.THeroControl.GetHero  (eax=hc, edx=i)
T_ISCLASS      = 0x401048          # System.@IsClass (eax=obj, edx=class) -> al
T_SETMODIFIED  = 0x401FF0          # HSEngine.THSMap.SetModified (eax=map)
T_MSGBOX       = 0x401348          # Forms.TApplication.MessageBox (eax=App, edx=Text, ecx=Caption; push flags) ret 4
T_DESELECT     = 0x402DE8          # HSMEdit.THSMEdit.DeselectPlaceHS (eax=edit)
T_MI_CREATE    = 0x401818          # Menus.TMenuItem.Create (eax=class, dl=1, ecx=owner)
T_MI_SETCAP    = 0x401820          # Menus.TMenuItem.SetCaption (eax=item, edx=AnsiString)
T_MI_ADD       = 0x401850          # Menus.TMenuItem.Add (eax=parent, edx=item)
T_NEWLINE      = 0x401860          # Menus.NewLine -> eax
MAP_SLOT       = 0x43289C          # IAT AoWE.AoWHSMap (variable import: [[slot]] = map)
TLEADER_SLOT   = 0x4328AC          # IAT AoWE..TLeader class ref
APP_SLOT       = 0x432224          # IAT Forms.Application ([[slot]] = TApplication)
TMENUITEM_SLOT = 0x4324BC          # IAT Menus..TMenuItem class ref
IAT_REGISTERITEM = 0x4326E0        # IAT AoWE.TItemControl.RegisterItem@23EDC2EF (0x55794E7C preferred)
UNREG_DELTA    = 0x55794F08 - 0x55794E7C     # TItemControl.UnRegisterItem - RegisterItem = 0x8C
UNREG_SIG      = bytes.fromhex("53568bda8bf0f6431c02")   # push ebx/push esi/mov ebx,edx/mov esi,eax/test byte [ebx+1c],2

F_HSMEDIT, HSMEDIT_GUARD, DISP_PAUSE, DISP_RESUME = 0x22C, 0x1BC, 0x90, 0x94
F_DEVELOPERITEMS = 0x358
MAP_ITEMCONTROL, MAP_HEROCONTROL = 0xF4, 0xF8
OWNER_OFF = 0x04
HERO_DEACTIVATE, HERO_RELEASE = 0x188, 0x2C
MI_ONCLICK_CODE, MI_ONCLICK_DATA = 0x60, 0x64
MB_YESNOCANCEL_BUTTONS, MT_CONFIRMATION, MR_YES = 11, 3, 6
MB_OK_INFO, MB_OK_WARN = 0x40, 0x30

STRINGS = {   # AnsiString literals (refcount -1 header) and PChar literals
    "cap_heroes": "Delete Unused Heroes",
    "cap_items":  "Delete Unused Items",
    "pre":        "Delete ",
    "one_hero":   " unused hero?",
    "many_hero":  " unused heroes?",
    "none_hero":  "No unused heroes to delete.",
    "one_item":   " unused item?",
    "many_item":  " unused items?",
    "none_item":  "No unused items to delete.",
    "bad_dll":    "AoWEPACK.dll does not match the expected layout; no items were deleted.",
}
MSGBUF_CHARS = 64


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


def method_table_entry(d, P, vmt, name):
    """File offset of the code dword of published method `name` in class `vmt`'s table."""
    mt = struct.unpack_from("<I", d, va2off(P, vmt - 0x28))[0]
    o = va2off(P, mt)
    cnt = struct.unpack_from("<H", d, o)[0]
    p = o + 2
    for _ in range(cnt):
        sz, code = struct.unpack_from("<HI", d, p)
        nl = d[p + 6]
        if d[p + 7:p + 7 + nl] == name.encode():
            return p + 2, code
        p += sz
    raise KeyError(name)


# ------------------------------------------------------------------ the caves
def assemble(sec_va, lit):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    L = lit  # dict name -> VA (0 on the sizing pass)
    A = []
    a = A.append

    # ---- fc_wrap: published as TMainForm.FormCreate.  eax=Self, edx=Sender
    a("fc_wrap:")
    a("push ebx")
    a("mov  ebx, eax")
    a("call 0x%X" % FORMCREATE)
    a("mov  eax, ebx")
    a("call add_menu")
    a("pop  ebx")
    a("ret")

    # ---- add_menu(eax=form): separator + two items appended to DeveloperItems
    a("add_menu:")
    a("push ebx"); a("push esi"); a("push edi")
    a("mov  ebx, eax")
    a("mov  esi, [ebx + 0x%X]" % F_DEVELOPERITEMS)
    a("test esi, esi")
    a("je   am_out")
    a("call 0x%X" % T_NEWLINE)
    a("mov  edx, eax")
    a("mov  eax, esi")
    a("call 0x%X" % T_MI_ADD)
    for cap, handler in (("cap_heroes", "prune_heroes"), ("cap_items", "prune_items")):
        a("mov  ecx, ebx")                                   # owner = the form
        a("mov  dl, 1")
        a("mov  eax, [0x%X]" % TMENUITEM_SLOT)
        a("call 0x%X" % T_MI_CREATE)
        a("mov  edi, eax")
        a("mov  edx, 0x%X" % L[cap])                         # AnsiString literal
        a("call 0x%X" % T_MI_SETCAP)
        a("mov  dword ptr [edi + 0x%X], %s" % (MI_ONCLICK_CODE, handler))
        a("mov  [edi + 0x%X], ebx" % MI_ONCLICK_DATA)
        a("mov  edx, edi")
        a("mov  eax, esi")
        a("call 0x%X" % T_MI_ADD)
    a("am_out:")
    a("pop  edi"); a("pop  esi"); a("pop  ebx")
    a("ret")

    # ---- pause / resume the map view (TMainForm.DeleteHeroBtnClick pattern).  eax=form
    for nm, slot in (("pause", DISP_PAUSE), ("resume", DISP_RESUME)):
        a("%s:" % nm)
        a("mov  eax, [eax + 0x%X]" % F_HSMEDIT)
        a("test eax, eax")
        a("je   %s_out" % nm)
        a("cmp  byte ptr [eax + 0x%X], 0" % HSMEDIT_GUARD)
        a("je   %s_out" % nm)
        a("mov  edx, [eax]")
        a("call dword ptr [edx + 0x%X]" % slot)
        a("%s_out:" % nm)
        a("ret")

    # ---- confirm(eax=form, ecx=count, edx=desc) -> eax = 1 go ahead / 0 stop
    #      desc: dd singular, dd plural, dd none_text(PChar), dd caption(PChar)
    a("confirm:")
    a("push ebx"); a("push esi"); a("push edi")
    a("mov  esi, eax")
    a("mov  ebx, edx")
    a("mov  eax, ecx")
    a("test eax, eax")
    a("jne  cf_build")
    a("push 0x%X" % MB_OK_INFO)
    a("mov  ecx, [ebx + 0xC]")
    a("mov  edx, [ebx + 8]")
    a("mov  eax, [0x%X]" % APP_SLOT)
    a("mov  eax, [eax]")
    a("call 0x%X" % T_MSGBOX)
    a("xor  eax, eax")
    a("jmp  cf_out")
    a("cf_build:")
    a("push eax")
    a("mov  edi, 0x%X" % L["msgbuf"])
    a("mov  edx, 0x%X" % L["pre"])
    a("call copyz")
    a("pop  eax")
    a("push eax")
    a("xor  ecx, ecx")
    a("push ebx")
    a("mov  ebx, 0xA")
    a("cf_dig:")
    a("xor  edx, edx")
    a("div  ebx")
    a("add  dl, 0x30")
    a("push edx")
    a("inc  ecx")
    a("test eax, eax")
    a("jne  cf_dig")
    a("cf_emit:")
    a("pop  eax")
    a("mov  [edi], al")
    a("inc  edi")
    a("dec  ecx")
    a("jne  cf_emit")
    a("pop  ebx")
    a("pop  eax")
    a("mov  edx, [ebx + 4]")                                 # plural
    a("cmp  eax, 1")
    a("jne  cf_suffix")
    a("mov  edx, [ebx]")                                     # singular
    a("cf_suffix:")
    a("call copyz")
    a("mov  byte ptr [edi], 0")
    a("sub  edi, 0x%X" % L["msgbuf"])
    a("mov  dword ptr [0x%X], edi" % (L["msgbuf"] - 4))      # AnsiString length
    a("push 0x%X" % MB_YESNOCANCEL_BUTTONS)
    a("push 0")
    a("mov  edx, 0x%X" % L["msgbuf"])
    a("mov  cl, 0x%X" % MT_CONFIRMATION)
    a("mov  eax, esi")
    a("call 0x%X" % MSGDLG)
    a("cmp  ax, 0x%X" % MR_YES)
    a("sete al")
    a("movzx eax, al")
    a("cf_out:")
    a("pop  edi"); a("pop  esi"); a("pop  ebx")
    a("ret")

    a("copyz:")                                              # edx=src PChar, edi=dest
    a("mov  al, [edx]")
    a("test al, al")
    a("je   cz_out")
    a("mov  [edi], al")
    a("inc  edi")
    a("inc  edx")
    a("jmp  copyz")
    a("cz_out:")
    a("ret")

    # ---- get_hc / get_ic: -> eax = THeroControl / TItemControl of the open map, or 0
    for nm, off in (("get_hc", MAP_HEROCONTROL), ("get_ic", MAP_ITEMCONTROL)):
        a("%s:" % nm)
        a("mov  eax, [0x%X]" % MAP_SLOT)
        a("mov  eax, [eax]")
        a("test eax, eax")
        a("je   %s_out" % nm)
        a("mov  eax, [eax + 0x%X]" % off)
        a("%s_out:" % nm)
        a("ret")

    # ---- set_modified: mark the open map modified
    a("set_modified:")
    a("mov  eax, [0x%X]" % MAP_SLOT)
    a("mov  eax, [eax]")
    a("test eax, eax")
    a("je   sm_out")
    a("call 0x%X" % T_SETMODIFIED)
    a("sm_out:")
    a("ret")

    # ================= prune_heroes (OnClick: eax=form, edx=Sender) =================
    a("prune_heroes:")
    a("push ebx"); a("push esi"); a("push edi")
    a("mov  esi, eax")
    a("mov  eax, [0x%X]" % MAP_SLOT)
    a("mov  eax, [eax]")
    a("test eax, eax")
    a("je   ph_exit")
    a("mov  eax, esi")
    a("call pause")
    # pass 1: count
    a("xor  edi, edi")
    a("call get_hc")
    a("test eax, eax")
    a("je   ph_counted")
    a("call 0x%X" % T_GETCOUNT)
    a("mov  ebx, eax")
    a("dec  ebx")
    a("js   ph_counted")
    a("ph_cloop:")
    a("call get_hc")
    a("mov  edx, ebx")
    a("call 0x%X" % T_GETHERO)
    a("test eax, eax")                                       # the roster can hold nils
    a("je   ph_cnext")
    a("cmp  dword ptr [eax + 0x%X], 0" % OWNER_OFF)            # placed -> keep
    a("jne  ph_cnext")
    a("mov  edx, [0x%X]" % TLEADER_SLOT)
    a("call 0x%X" % T_ISCLASS)
    a("test al, al")                                         # leader -> keep
    a("jne  ph_cnext")
    a("inc  edi")
    a("ph_cnext:")
    a("dec  ebx")
    a("jns  ph_cloop")
    a("ph_counted:")
    a("mov  eax, esi")
    a("mov  ecx, edi")
    a("mov  edx, 0x%X" % L["desc_heroes"])
    a("call confirm")
    a("test eax, eax")
    a("je   ph_resume")
    # pass 2: delete, downward, re-fetching after @IsClass (it clobbers eax)
    a("call get_hc")
    a("test eax, eax")
    a("je   ph_resume")
    a("call 0x%X" % T_GETCOUNT)
    a("mov  ebx, eax")
    a("dec  ebx")
    a("js   ph_mod")
    a("ph_dloop:")
    a("call get_hc")
    a("mov  edx, ebx")
    a("call 0x%X" % T_GETHERO)
    a("test eax, eax")
    a("je   ph_dnext")
    a("cmp  dword ptr [eax + 0x%X], 0" % OWNER_OFF)
    a("jne  ph_dnext")
    a("mov  edx, [0x%X]" % TLEADER_SLOT)
    a("call 0x%X" % T_ISCLASS)
    a("test al, al")
    a("jne  ph_dnext")
    a("call get_hc")
    a("mov  edx, ebx")
    a("call 0x%X" % T_GETHERO)
    a("mov  edi, eax")
    a("test edi, edi")
    a("je   ph_dnext")
    a("mov  eax, edi")
    a("mov  edx, [eax]")
    a("call dword ptr [edx + 0x%X]" % HERO_DEACTIVATE)        # THero.Deactivate
    a("mov  eax, edi")
    a("mov  edx, [eax]")
    a("call dword ptr [edx + 0x%X]" % HERO_RELEASE)           # TAbstractUnit.Release -> Destroy -> UnRegisterHero
    a("ph_dnext:")
    a("dec  ebx")
    a("jns  ph_dloop")
    a("ph_mod:")
    a("call set_modified")
    a("ph_resume:")
    a("mov  eax, esi")
    a("call resume")
    a("ph_exit:")
    a("pop  edi"); a("pop  esi"); a("pop  ebx")
    a("ret")

    # ================= prune_items (OnClick: eax=form, edx=Sender) ==================
    a("prune_items:")
    a("push ebx"); a("push esi"); a("push edi")
    a("mov  esi, eax")
    a("mov  eax, [0x%X]" % MAP_SLOT)
    a("mov  eax, [eax]")
    a("test eax, eax")
    a("je   pi_exit")
    a("mov  eax, esi")
    a("call pause")
    # pass 1: count   (TItemControl: [ic+8] = TList, [TList+4] = array, [TList+8] = count)
    a("xor  edi, edi")
    a("call get_ic")
    a("test eax, eax")
    a("je   pi_counted")
    a("mov  ecx, [eax + 8]")
    a("mov  ebx, [ecx + 8]")
    a("dec  ebx")
    a("js   pi_counted")
    a("pi_cloop:")
    a("call get_ic")
    a("mov  eax, [eax + 8]")
    a("mov  eax, [eax + 4]")
    a("mov  eax, [eax + ebx*4]")
    a("test eax, eax")
    a("je   pi_cnext")
    a("cmp  dword ptr [eax + 0x%X], 0" % OWNER_OFF)            # held by a container -> keep
    a("jne  pi_cnext")
    a("inc  edi")
    a("pi_cnext:")
    a("dec  ebx")
    a("jns  pi_cloop")
    a("pi_counted:")
    a("mov  eax, esi")
    a("mov  ecx, edi")
    a("mov  edx, 0x%X" % L["desc_items"])
    a("call confirm")
    a("test eax, eax")
    a("je   pi_resume")
    # resolve TItemControl.UnRegisterItem from the RegisterItem import and check its prologue
    a("mov  edi, [0x%X]" % IAT_REGISTERITEM)
    a("add  edi, 0x%X" % UNREG_DELTA)
    a("cmp  dword ptr [edi], 0x%X" % struct.unpack_from("<I", UNREG_SIG, 0)[0])
    a("jne  pi_bad")
    a("cmp  dword ptr [edi + 4], 0x%X" % struct.unpack_from("<I", UNREG_SIG, 4)[0])
    a("jne  pi_bad")
    a("cmp  word ptr [edi + 8], 0x%X" % struct.unpack_from("<H", UNREG_SIG, 8)[0])
    a("jne  pi_bad")
    # drop any item the place tool is holding (the grid's Delete button does this too)
    a("mov  eax, [esi + 0x%X]" % F_HSMEDIT)
    a("test eax, eax")
    a("je   pi_nodesel")
    a("call 0x%X" % T_DESELECT)
    a("pi_nodesel:")
    # pass 2: delete, downward (TList.Remove compacts; lower indices are unaffected)
    a("call get_ic")
    a("test eax, eax")
    a("je   pi_resume")
    a("mov  ecx, [eax + 8]")
    a("mov  ebx, [ecx + 8]")
    a("dec  ebx")
    a("js   pi_mod")
    a("pi_dloop:")
    a("call get_ic")
    a("mov  edx, eax")
    a("mov  eax, [eax + 8]")
    a("mov  eax, [eax + 4]")
    a("mov  eax, [eax + ebx*4]")
    a("test eax, eax")
    a("je   pi_dnext")
    a("cmp  dword ptr [eax + 0x%X], 0" % OWNER_OFF)
    a("jne  pi_dnext")
    a("xchg eax, edx")                                       # eax = TItemControl, edx = item
    a("call edi")                                            # UnRegisterItem: remove, Release, Changed
    a("pi_dnext:")
    a("dec  ebx")
    a("jns  pi_dloop")
    a("pi_mod:")
    a("call set_modified")
    a("jmp  pi_resume")
    a("pi_bad:")
    a("push 0x%X" % MB_OK_WARN)
    a("mov  ecx, 0x%X" % L["cap_items_pc"])
    a("mov  edx, 0x%X" % L["bad_dll"])
    a("mov  eax, [0x%X]" % APP_SLOT)
    a("mov  eax, [eax]")
    a("call 0x%X" % T_MSGBOX)
    a("pi_resume:")
    a("mov  eax, esi")
    a("call resume")
    a("pi_exit:")
    a("pop  edi"); a("pop  esi"); a("pop  ebx")
    a("ret")

    # One text, keystone resolves the labels itself (its sym_resolver hook gets PC-relative
    # branches wrong by the displacement width, so it is not used).  Label addresses are
    # recovered by appending a `mov eax, label` probe: nothing before it moves, and the
    # probe's imm32 is the address.
    text = "\n".join(A)
    try:
        enc, _ = ks.asm(text, sec_va)
    except Exception as ex:                                  # noqa: BLE001
        bad = [ln for ln in A if not ln.endswith(":") and not _asm_ok(ks, ln, sec_va)]
        raise RuntimeError("%s -- offending line(s): %s" % (ex, bad))
    code = bytes(enc)
    labels = {}
    for lab in ("fc_wrap", "add_menu", "pause", "resume", "confirm", "copyz", "get_hc",
                "get_ic", "set_modified", "prune_heroes", "prune_items"):
        probe, _ = ks.asm(text + "\nmov eax, %s" % lab, sec_va)
        probe = bytes(probe)
        assert probe[:len(code)] == code and len(probe) == len(code) + 5, "probe moved the code"
        labels[lab] = struct.unpack_from("<I", probe, len(code) + 1)[0]
    return code, labels


def _asm_ok(ks, line, va):
    try:
        ks.asm(line, va)
        return True
    except Exception:                                        # noqa: BLE001
        return False


def build_data(data_va):
    """Literals, descriptors and the message buffer, laid out after the code."""
    blob = bytearray()
    lit = {}

    def align(n):
        while len(blob) % n:
            blob.append(0)

    def ansistr(key, text):               # refcount -1, length, chars, NUL; pointer -> chars
        align(4)
        blob.extend(struct.pack("<ii", -1, len(text)))
        lit[key] = data_va + len(blob)
        blob.extend(text.encode("latin1") + b"\0")

    for key, text in STRINGS.items():
        ansistr(key, text)
    lit["cap_items_pc"] = lit["cap_items"]  # same bytes serve as a PChar caption
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


def build_section():
    sec_va = SEC[1]
    # sizing pass: any 32-bit placeholder keeps the encodings identical (imm32 / disp32)
    zero = {k: 0x1000000 for k in list(STRINGS) + ["cap_items_pc", "msgbuf", "desc_heroes", "desc_items"]}
    code0, _ = assemble(sec_va, zero)
    code_len = (len(code0) + 15) // 16 * 16
    data_va = sec_va + code_len
    data, lit = build_data(data_va)
    code, labels = assemble(sec_va, lit)
    assert len(code) == len(code0), "code size changed between passes"
    blob = code + bytes(code_len - len(code)) + data
    assert len(blob) <= SEC[3], "cave too big for the section"
    return blob, labels, len(code), data_va


def check_immediates(code, sec_va):
    """keystone assembles push 0xFFFF as push -1 silently; read the encoding back."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    got = []
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, sec_va):
        if i.mnemonic == "push" and (i.op_str.startswith("0x") or i.op_str.isdigit()):
            got.append(int(i.op_str, 0))
    want = [MB_OK_INFO, MB_YESNOCANCEL_BUTTONS, 0, MB_OK_WARN]
    assert got == want, "push immediates decoded as %s, expected %s" % (got, want)


def disassemble(code, sec_va, lit, labels):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    inv = {v: k for k, v in lit.items()}
    byva = {v: k for k, v in labels.items()}
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, sec_va):
        if i.address in byva:
            print("    %s:" % byva[i.address])
        note = ""
        for va, nm in inv.items():
            if ("0x%x" % va) in i.op_str:
                note = "   ; -> %s" % nm
        print("      %08X  %-22s %-6s %s%s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str, note))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="AoWDevX: Developer > Delete Unused Heroes / Items")
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

    d = bytearray(open(exe, "rb").read())
    P = pe_info(d)
    names = [s["name"] for s in P["secs"]]
    blob, labels, code_len, data_va = build_section()
    check_immediates(blob[:code_len], SEC[1])
    _, lit = build_data(data_va)

    mt_fo, mt_code = method_table_entry(d, P, VMT_MAINFORM, "FormCreate")
    print("target: %s (%d B, %d sections, SizeOfImage %#x)" % (exe, len(d), P["nsec"], P["size_of_image"]))
    print("%s @%#x: %d B code + %d B data = %d B (%d B free)" % (
        SEC[0].decode(), SEC[1], code_len, len(blob) - code_len, len(blob), SEC[3] - len(blob)))
    print("caves: " + ", ".join("%s=%#x" % (k, v) for k, v in labels.items()))
    print("method table FormCreate dword @file %#x currently -> %#x" % (mt_fo, mt_code))
    if args.dis:
        disassemble(blob[:code_len], SEC[1], lit, labels)

    already = (SEC[0] in names and mt_code == labels["fc_wrap"]
               and bytes(d[P["secs"][names.index(SEC[0])]["raw"]:][:len(blob)]) == blob)
    if already:
        print("ALL ALREADY PATCHED"); return 0
    if SEC[0] in names:
        print("%s exists but content/hook differ - refreshing in place" % SEC[0].decode())
        assert mt_code in (FORMCREATE, labels["fc_wrap"]), "FormCreate entry is %#x - unknown state" % mt_code
    else:
        assert mt_code == FORMCREATE, "FormCreate entry is %#x, expected %#x - another patch owns it" % (mt_code, FORMCREATE)
        assert P["sec0"] + 40 * (P["nsec"] + 1) <= P["secs"][0]["raw"], "no room for a section header"
        assert P["size_of_image"] == SEC[1] - BASE, "SizeOfImage %#x != %#x: section VA would not be next" % (P["size_of_image"], SEC[1] - BASE)
    # the run-time UnRegisterItem delta must hold in the dll that ships beside the exe
    dll = os.path.join(os.path.dirname(exe), "AoWEPACK.dll")
    if os.path.exists(dll):
        dd = open(dll, "rb").read(); DP = pe_info(dd)
        base = struct.unpack_from("<I", dd, DP["e"] + 24 + 28)[0]
        def dva2off(va):
            r = va - base
            for s in DP["secs"]:
                if s["va"] <= r < s["va"] + max(s["vs"], s["rs"]): return s["raw"] + (r - s["va"])
        sig = dd[dva2off(0x55794E7C + UNREG_DELTA):][:len(UNREG_SIG)]
        print("AoWEPACK.dll UnRegisterItem prologue check: %s" % ("OK" if sig == UNREG_SIG else "MISMATCH (%s)" % sig.hex()))
        assert sig == UNREG_SIG
    if not args.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0

    if not os.path.exists(bak):
        shutil.copyfile(exe, bak); print("Backup: %s" % bak)
    if SEC[0] in names:
        s = P["secs"][names.index(SEC[0])]
        assert len(blob) <= s["rs"]
        d[s["raw"]:s["raw"] + s["rs"]] = blob + bytes(s["rs"] - len(blob))
    else:
        pad = (-len(d)) % 0x200; d += bytes(pad)
        rawoff = len(d); d += blob + bytes(SEC[3] - len(blob))
        hdr = SEC[0].ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC[2], SEC[1] - BASE, SEC[3], rawoff, 0, 0, 0, 0, SEC_CHARS)
        struct.pack_into("<40s", d, P["sec0"] + 40 * P["nsec"], hdr)
        struct.pack_into("<H", d, P["e"] + 6, P["nsec"] + 1)
        struct.pack_into("<I", d, P["e"] + 24 + 56, SEC[1] - BASE + SEC[2])
        print("appended %s raw @%#x (%#x B), SizeOfImage -> %#x" % (SEC[0].decode(), rawoff, SEC[3], SEC[1] - BASE + SEC[2]))
    struct.pack_into("<I", d, mt_fo, labels["fc_wrap"])
    print("Patched: method table FormCreate -> fc_wrap %#x" % labels["fc_wrap"])
    tmp = exe + ".tmp_prune"
    open(tmp, "wb").write(d)
    os.replace(tmp, exe)
    print("AoWDevX.exe patched successfully.  UNTESTED until the editor is launched:")
    print("  Developer menu should end with a separator, 'Delete Unused Heroes', 'Delete Unused Items'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
