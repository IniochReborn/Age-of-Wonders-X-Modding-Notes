#!/usr/bin/env python3
r"""
AoWxShot.dll module: the editor's  Options -> Map Settings -> "Ban List"  tab (2026-11-20).

User: "add a new tab to Options->Map Settings in the editor, which should be called Ban List.  it should have two
scrollable windows, one for spells and one for abilities, with each listed in alphabetical [order] and an empty toggle
by default" - a ticked entry is banned (the game rules + the storage in the map are other patches).

No byte of AoWDevX.exe changes on disk: like the Missing Resources list, everything lives in AoWxShot.dll and is wired
at editor start by Init(form) -> `baninit`, which patches the running exe IN MEMORY (bytes verified first; both sites
must match or nothing is touched):
  * TMapSettingsDlg published-method table (VMT 0x4220E8, table 0x4226A1): the FormCreate entry's address dword at
    0x4226A5 (0x422FDC) -> `bl_fcwrap`.  The dialog is created anew for every Options -> Map Settings click
    (0x42A960: Create(class [0x4220A8], owner main form) / ShowModal / Free) and its DFM binds OnCreate=FormCreate by
    name, so the wrapper runs once per dialog: original FormCreate (loads everything from the map), then the tab.
  * OKBtnClick 0x4236CC, success branch: `call 0x422C68` (apply the dialog to the map) @0x423730 -> `bl_ok`: the
    original, then the ticks are written back.  Cancel / a failed validation never reach it.

The tab (runtime-created, the item HP/MV rows recipe: ctor = class VMT+0x24 (eax class, dl 1, ecx owner = the form),
SetParent VMT+0x3C, SetBounds VMT+0x4C, SetText thunk 0x401568):
  TTabSheet (class import [0x432C94]) -> ComCtrls.TTabSheet.SetPageControl(sheet, MainPageControl [form+0x1E0]) - not
    imported by the exe: VCL30 module handle + RVA 0x66CC0, first 8 bytes verified - caption "Ban List" (5th tab);
  TLabel "Spells" (12,8) / "Abilities" (236,8) / a hint line (12,372);
  two checklst.TCheckListBox (class import [0x4332EC] - the dialog's own "Races on map" list is one, so the class,
    GetChecked [0x4332E4] (eax box, edx index -> al) and SetChecked [0x4332E8] (eax, edx, cl) are already imported):
    spells at (12,28) 210x338, abilities at (236,28) 210x338; default style (CreateParams forces owner-draw fixed, the
    item height follows the font), vertical scroll bar + mouse wheel are the native list box's.
Contents (read from the live registries, AoWHSSet = [[0x432898]]; +0x84 TSpellControl, +0x80 TAbilityControl; both
keep their objects in a TList at [ctl+8] (+4 items, +8 count) whose index IS the id):
  spells    = every registered spell with a non-empty name [spell+8], ids 0..511;
  abilities = every registered ability with a non-empty name [abil+8], ids 0..255, that can be BOUGHT: skill-point
              cost [abil+0x14] <> 0, or its ExpandCost (VMT+0xC8) is not the base AoWE.TAbility.ExpandCost
              (AoWEPACK RVA 0x4E908 = `mov eax,[eax+0x14]`; multi-level abilities, Turn Undead, Dispel Magic ...
              compute their own cost).  Everything else can never be picked in leader customisation or on a level-up.
  Both are sorted by name (insertion sort, lstrcmpiA) and added with Items.Add (TStrings VMT+0x34); the list index ->
  id tables live in the DLL (g_blsid / g_blaid), so the list boxes' item data is left alone.
Storage interface (another patch): BAN_GET = AoWEPACK RVA 0x1BA200 (VA 0x558BA200), returns eax = 96-byte buffer:
bytes 0..63 spell bits (bit id&7 of byte id>>3), 64..95 ability bits.  If the first dword at BAN_GET is zero (storage
patch not installed) NO tab is created.  On OK each bit set is rewritten from its list (only when that list was
filled); nothing is written on Cancel.
"""
import struct

# ---- AoWDevX.exe (fixed base) -------------------------------------------------------------------------------------
MT_FORMCREATE, FORMCREATE = 0x4226A5, 0x422FDC      # method-table entry (address dword) / TMapSettingsDlg.FormCreate
OK_SITE, OK_SITE_REL, APPLY = 0x423730, 0xFFFFF533, 0x422C68   # `call 0x422C68` in OKBtnClick (e8 33 f5 ff ff)
F_PAGECTL = 0x1E0                                    # TMapSettingsDlg.MainPageControl
IAT_TABSHEET, IAT_LABEL, IAT_CHECKLB = 0x432C94, 0x432654, 0x4332EC       # class imports = the VMT
IAT_GETCHECKED, IAT_SETCHECKED, IAT_HSSET = 0x4332E4, 0x4332E8, 0x432898
T_SETTEXT = 0x401568                                 # jmp [Controls.TControl.SetText]
V_CREATE, V_SETPARENT, V_SETBOUNDS, V_ADD = 0x24, 0x3C, 0x4C, 0x34
LB_ITEMS = 0x118                                     # TCustomListBox.FItems
# ---- VCL30.dpl / AoWEPACK.dll ----------------------------------------------------------------------------------------
SPC_RVA, SPC_B0, SPC_B1 = 0x66CC0, 0xF28B5653, 0x838BD88B     # ComCtrls.TTabSheet.SetPageControl: 53 56 8B F2 8B D8 8B 83
BANGET_RVA, EXPANDCOST_RVA = 0x1BA200, 0x4E908
SET_SPELLS, SET_ABILS, V_EXPANDCOST = 0x84, 0x80, 0xC8
MAX_SPELLS, MAX_ABILS = 512, 256
# ---- layout (the dialog DFM is PixelsPerInch 120, Scaled False; the Diplomacy grid uses 12,8 433x381) ---------------------
COL1, COL2, LBL_TOP, BOX_TOP, BOX_W, BOX_H, HINT_TOP = 12, 236, 6, 44, 210, 322, 372   # 11/20: two-line captions (user wording)
HINT = "Ticked entries are banned for every player on this map."     # TLabel AutoSize: must fit ~430 px

IMPORTS = {"kernel32.dll": ["lstrcmpiA"]}


def _ansi(text):
    b = text.encode("latin1")
    return struct.pack("<ii", -1, len(b)) + b + b"\0"


def data(D):
    for n in ("g_blget", "g_blsbox", "g_blabox", "g_blscnt", "g_blacnt", "g_blexp", "g_blold"):
        D.var(n)
    D.var("g_blent", MAX_SPELLS * 8)
    D.var("g_blsid", MAX_SPELLS * 2)
    D.var("g_blaid", MAX_ABILS * 2)
    D.s("s_blvcl", "VCL30.dpl")
    D.s("s_blaowe", "AoWEPACK.dll")
    D.add("t_blban", _ansi("Ban List"))
    D.add("t_blspells", _ansi("Spells\r\n(remove from Research)"))
    D.add("t_blabils", _ansi("Abilities (remove from\r\ncustomization and level-up)"))
    D.add("t_blhint", _ansi(HINT))


def asm(v, a, imp, GD):
    t = lambda n: "%#x" % (int(a(n), 16) + 8)          # noqa: E731   (chars of a Delphi AnsiString literal)
    return f"""
    baninit:
        mov edi, {MT_FORMCREATE:#x}
        cmp dword ptr [edi], {FORMCREATE:#x}
        jne bi_out
        mov esi, {OK_SITE:#x}
        cmp byte ptr [esi], 0xe8
        jne bi_out
        cmp dword ptr [esi + 0x1], {OK_SITE_REL:#x}
        jne bi_out
        lea eax, [ebp + {a('g_blold')}]
        push eax
        push 0x40
        push 0x4
        push edi
        call {imp('VirtualProtect')}
        test eax, eax
        jz bi_out
        lea eax, [ebp + {a('g_blold')}]
        push eax
        push 0x40
        push 0x5
        push esi
        call {imp('VirtualProtect')}
        test eax, eax
        jz bi_out
        lea eax, [ebp + bl_fcwrap]
        mov dword ptr [edi], eax
        lea eax, [ebp + bl_ok]
        sub eax, esi
        sub eax, 0x5
        mov dword ptr [esi + 0x1], eax
    bi_out:
        ret

    bl_fcwrap:
        push ebp
        push ebx
        push esi
        push edi
        mov ebx, eax
        call {GD:#x}
        xor eax, eax
        mov {v('g_blsbox')}, eax
        mov {v('g_blabox')}, eax
        mov {v('g_blscnt')}, eax
        mov {v('g_blacnt')}, eax
        mov eax, ebx
        mov ecx, {FORMCREATE:#x}
        call ecx
        call bl_build
        call lv_build
        call cn_build
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret

    bl_build:
        lea eax, [ebp + {a('s_blaowe')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz bb_out
        lea ecx, [eax + {EXPANDCOST_RVA:#x}]
        mov {v('g_blexp')}, ecx
        lea eax, [eax + {BANGET_RVA:#x}]
        cmp dword ptr [eax], 0x0
        je bb_out
        mov {v('g_blget')}, eax
        lea eax, [ebp + {a('s_blvcl')}]
        push eax
        call {imp('GetModuleHandleA')}
        test eax, eax
        jz bb_out
        lea edi, [eax + {SPC_RVA:#x}]
        cmp dword ptr [edi], {SPC_B0:#x}
        jne bb_out
        cmp dword ptr [edi + 0x4], {SPC_B1:#x}
        jne bb_out
        mov eax, dword ptr [{IAT_HSSET:#x}]
        cmp dword ptr [eax], 0x0
        je bb_out
        mov eax, dword ptr [ebx + {F_PAGECTL:#x}]
        test eax, eax
        jz bb_out
        mov eax, dword ptr [{IAT_TABSHEET:#x}]
        mov dl, 0x1
        mov ecx, ebx
        call dword ptr [eax + {V_CREATE:#x}]
        mov esi, eax
        mov edx, dword ptr [ebx + {F_PAGECTL:#x}]
        call edi
        mov eax, esi
        lea edx, [ebp + {t('t_blban')}]
        mov ecx, {T_SETTEXT:#x}
        call ecx
        push 0xc8
        mov eax, {COL1:#x}
        mov ecx, {LBL_TOP:#x}
        lea edx, [ebp + {t('t_blspells')}]
        call bl_label
        push 0xc8
        mov eax, {COL2:#x}
        mov ecx, {LBL_TOP:#x}
        lea edx, [ebp + {t('t_blabils')}]
        call bl_label
        push 0x1b2
        mov eax, {COL1:#x}
        mov ecx, {HINT_TOP:#x}
        lea edx, [ebp + {t('t_blhint')}]
        call bl_label
        mov eax, {COL1:#x}
        call bl_box
        mov {v('g_blsbox')}, eax
        mov eax, {COL2:#x}
        call bl_box
        mov {v('g_blabox')}, eax
        call {v('g_blget')}
        mov edi, eax
        xor edx, edx
        call bl_collect
        mov {v('g_blscnt')}, eax
        mov esi, {v('g_blsbox')}
        lea ecx, [ebp + {a('g_blsid')}]
        mov edx, edi
        call bl_fill
        mov edx, 0x1
        call bl_collect
        mov {v('g_blacnt')}, eax
        mov esi, {v('g_blabox')}
        lea ecx, [ebp + {a('g_blaid')}]
        lea edx, [edi + 0x40]
        call bl_fill
    bb_out:
        ret

    bl_label:
        push edi
        push eax
        push ecx
        push edx
        mov eax, dword ptr [{IAT_LABEL:#x}]
        mov dl, 0x1
        mov ecx, ebx
        call dword ptr [eax + {V_CREATE:#x}]
        push eax
        mov edx, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETPARENT:#x}]
        mov eax, dword ptr [esp]
        push dword ptr [esp + 0x18]
        push 0x10
        mov ecx, dword ptr [esp + 0x10]
        mov edx, dword ptr [esp + 0x14]
        mov edi, dword ptr [eax]
        call dword ptr [edi + {V_SETBOUNDS:#x}]
        pop eax
        pop edx
        mov ecx, {T_SETTEXT:#x}
        call ecx
        add esp, 0x8
        pop edi
        ret 0x4

    bl_box:
        push edi
        push eax
        mov eax, dword ptr [{IAT_CHECKLB:#x}]
        mov dl, 0x1
        mov ecx, ebx
        call dword ptr [eax + {V_CREATE:#x}]
        push eax
        mov edx, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {V_SETPARENT:#x}]
        mov eax, dword ptr [esp]
        push {BOX_W:#x}
        push {BOX_H:#x}
        mov ecx, {BOX_TOP:#x}
        mov edx, dword ptr [esp + 0xc]
        mov edi, dword ptr [eax]
        call dword ptr [edi + {V_SETBOUNDS:#x}]
        pop eax
        add esp, 0x4
        pop edi
        ret

    bl_collect:
        push ebx
        push esi
        push edi
        push edx
        xor ebx, ebx
        mov eax, dword ptr [{IAT_HSSET:#x}]
        mov eax, dword ptr [eax]
        test eax, eax
        jz bc_sort
        mov ecx, dword ptr [eax + {SET_SPELLS:#x}]
        mov edi, {MAX_SPELLS:#x}
        test edx, edx
        jz bc_ctl
        mov ecx, dword ptr [eax + {SET_ABILS:#x}]
        mov edi, {MAX_ABILS:#x}
    bc_ctl:
        test ecx, ecx
        jz bc_sort
        mov ecx, dword ptr [ecx + 0x8]
        test ecx, ecx
        jz bc_sort
        mov esi, dword ptr [ecx + 0x4]
        mov ecx, dword ptr [ecx + 0x8]
        cmp ecx, edi
        jbe bc_n
        mov ecx, edi
    bc_n:
        test esi, esi
        jz bc_sort
        xor edi, edi
    bc_l:
        cmp edi, ecx
        jae bc_sort
        mov eax, dword ptr [esi + edi*4]
        test eax, eax
        jz bc_next
        mov edx, dword ptr [eax + 0x8]
        test edx, edx
        jz bc_next
        cmp byte ptr [edx], 0x0
        je bc_next
        cmp dword ptr [esp], 0x0
        je bc_take
        cmp dword ptr [eax + 0x14], 0x0
        jne bc_take
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + {V_EXPANDCOST:#x}]
        cmp eax, {v('g_blexp')}
        je bc_next
    bc_take:
        mov dword ptr [ebp + ebx*8 + {a('g_blent')}], edx
        mov dword ptr [ebp + ebx*8 + {int(a('g_blent'), 16) + 4:#x}], edi
        inc ebx
    bc_next:
        inc edi
        jmp bc_l
    bc_sort:
        mov edi, 0x1
    bc_so:
        cmp edi, ebx
        jae bc_done
        push dword ptr [ebp + edi*8 + {int(a('g_blent'), 16) + 4:#x}]
        push dword ptr [ebp + edi*8 + {a('g_blent')}]
        mov esi, edi
    bc_si:
        test esi, esi
        jz bc_put
        push dword ptr [esp]
        push dword ptr [ebp + esi*8 + {int(a('g_blent'), 16) - 8:#x}]
        call {imp('lstrcmpiA')}
        test eax, eax
        jle bc_put
        mov eax, dword ptr [ebp + esi*8 + {int(a('g_blent'), 16) - 8:#x}]
        mov dword ptr [ebp + esi*8 + {a('g_blent')}], eax
        mov eax, dword ptr [ebp + esi*8 + {int(a('g_blent'), 16) - 4:#x}]
        mov dword ptr [ebp + esi*8 + {int(a('g_blent'), 16) + 4:#x}], eax
        dec esi
        jmp bc_si
    bc_put:
        pop dword ptr [ebp + esi*8 + {a('g_blent')}]
        pop dword ptr [ebp + esi*8 + {int(a('g_blent'), 16) + 4:#x}]
        inc edi
        jmp bc_so
    bc_done:
        mov eax, ebx
        pop edx
        pop edi
        pop esi
        pop ebx
        ret

    bl_fill:
        push ebx
        push edi
        push eax
        push ecx
        push edx
        xor ebx, ebx
        test esi, esi
        jz bf_out
    bf_l:
        cmp ebx, dword ptr [esp + 0x8]
        jae bf_out
        mov eax, dword ptr [esi + {LB_ITEMS:#x}]
        mov edx, dword ptr [ebp + ebx*8 + {a('g_blent')}]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ADD:#x}]
        mov edi, dword ptr [ebp + ebx*8 + {int(a('g_blent'), 16) + 4:#x}]
        mov ecx, dword ptr [esp + 0x4]
        mov word ptr [ecx + ebx*2], di
        mov ecx, dword ptr [esp]
        bt dword ptr [ecx], edi
        setb cl
        mov edx, ebx
        mov eax, esi
        call dword ptr [{IAT_SETCHECKED:#x}]
        inc ebx
        jmp bf_l
    bf_out:
        add esp, 0xc
        pop edi
        pop ebx
        ret

    bl_ok:
        push ebp
        push ebx
        push esi
        push edi
        mov ebx, eax
        call {GD:#x}
        mov eax, ebx
        mov ecx, {APPLY:#x}
        call ecx
        cmp {v('g_blget')}, 0x0
        je bo_out
        cmp {v('g_blsbox')}, 0x0
        je bo_out
        call {v('g_blget')}
        mov edi, eax
        mov esi, {v('g_blsbox')}
        mov ecx, {v('g_blscnt')}
        lea edx, [ebp + {a('g_blsid')}]
        mov eax, 0x40
        call bl_store
        add edi, 0x40
        mov esi, {v('g_blabox')}
        mov ecx, {v('g_blacnt')}
        lea edx, [ebp + {a('g_blaid')}]
        mov eax, 0x20
        call bl_store
    bo_out:
        call lv_store
        call cn_store
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret

    bl_store:
        push ebx
        push ecx
        push edx
        test esi, esi
        jz bs_out
        test ecx, ecx
        jz bs_out
        mov ecx, eax
        xor eax, eax
        push edi
        rep stosb
        pop edi
        xor ebx, ebx
    bs_l:
        cmp ebx, dword ptr [esp + 0x4]
        jae bs_out
        mov edx, ebx
        mov eax, esi
        call dword ptr [{IAT_GETCHECKED:#x}]
        test al, al
        jz bs_n
        mov ecx, dword ptr [esp]
        movzx eax, word ptr [ecx + ebx*2]
        bts dword ptr [edi], eax
    bs_n:
        inc ebx
        jmp bs_l
    bs_out:
        add esp, 0x8
        pop ebx
        ret
    """
